# Phân quyền theo nhóm người dùng VPN

**Phân quyền theo nhóm người dùng VPN** là cách tổ chức giới hạn quyền truy cập tài nguyên khi người dùng kết nối vào mạng từ xa thông qua **Virtual Private Network (VPN)**. Thay vì cho mọi tài khoản đã kết nối VPN đi đến toàn bộ mạng nội bộ, hệ thống xác định người dùng thuộc **nhóm, vai trò hoặc điều kiện truy cập** nào, sau đó chỉ cấp những kết nối cần thiết tới đúng dịch vụ, cổng, vùng mạng và thời điểm.

Ví dụ, một nhân viên chăm sóc khách hàng có thể cần truy cập ứng dụng CRM qua HTTPS nhưng không được kết nối trực tiếp đến database; kỹ sư vận hành có thể cần vào bastion để quản trị theo quy trình được phê duyệt; nhà thầu chỉ được vào một ứng dụng kiểm thử trong thời hạn hợp đồng. Tất cả đều có thể dùng cùng một hạ tầng VPN nhưng **không được nhận cùng quyền truy cập**.

Trong chương **VPN và truy cập từ xa** thuộc module **SECURITY_NETWORK_SECURITY**, phân quyền VPN là cầu nối giữa **xác thực danh tính, phân đoạn mạng, firewall, bảo vệ ứng dụng, giám sát IDS/IPS và kiến trúc cloud an toàn**. Thiết kế đúng phải trả lời được ba câu hỏi độc lập: **ai đang kết nối, họ được phép tới đâu, và hệ thống nào thực sự thực thi quyết định đó?**

> **Nguyên tắc nền tảng:** Kết nối VPN thành công **không đồng nghĩa** người dùng có quyền vào mọi dịch vụ bên trong. Đẩy route hoặc cấp địa chỉ IP cho client cũng **không phải** cơ chế thực thi quyền truy cập hoàn chỉnh.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **authentication**, **authorization**, **accounting** và quyền ở tầng ứng dụng.
2. Thiết kế mô hình **Role-Based Access Control (RBAC)** cho các nhóm Employee, Developer, Finance, IT Admin, Contractor và SOC.
3. Giải thích cách VPN gateway nhận thông tin danh tính/nhóm từ **IdP, Active Directory/LDAP, RADIUS, SAML hoặc OIDC** tùy nền tảng.
4. Xây dựng ma trận **nhóm → tài nguyên → giao thức/cổng → điều kiện** với nguyên tắc **least privilege** và **deny by default**.
5. Xác định nơi thực thi chính sách: **VPN gateway, firewall, microsegmentation, bastion, ứng dụng**.
6. Xử lý trường hợp một người thuộc nhiều nhóm, nhóm lồng nhau, nhóm hết hạn, thay đổi vai trò hoặc phiên VPN chưa hết hạn.
7. Kết hợp MFA, chứng thư thiết bị, trạng thái bảo mật endpoint và **quyền tạm thời có phê duyệt**.
8. Phân tích rủi ro từ split tunneling, định tuyến IPv4/IPv6, DNS, NAT, kết nối cloud và các đường truy cập không đi qua VPN.
9. Kiểm thử quyền hợp lệ và quyền bị từ chối, đọc log và xây dựng runbook khi phát hiện cấp quyền sai.

## 2. Xác thực khác phân quyền như thế nào?

Trong truy cập VPN, bốn khái niệm thường bị nhầm lẫn:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Authentication (AuthN)** | Người hoặc thiết bị là ai? | Tài khoản được IdP xác thực bằng mật khẩu và MFA, hoặc xác thực chứng thư theo chính sách |
| **Authorization (AuthZ)** | Người/thiết bị này được làm gì, với tài nguyên nào? | Thành viên nhóm Finance chỉ được vào ứng dụng kế toán qua HTTPS |
| **Accounting / audit** | Ai đã truy cập, thời điểm nào, kết quả ra sao? | Log phiên VPN, thay đổi group, rule allow/deny và sự kiện ứng dụng |
| **Application authorization** | Trong ứng dụng, người dùng được xem/sửa dữ liệu nào? | Người dùng CRM chỉ xem khách hàng của bộ phận mình |

Ví dụ, người dùng đã hoàn thành MFA với VPN gateway nhưng không thuộc nhóm **Finance**. Gateway nên từ chối lưu lượng từ phiên đó tới dịch vụ kế toán nếu chính sách yêu cầu nhóm Finance; ứng dụng kế toán vẫn phải tự kiểm tra vai trò và quyền trên dữ liệu.

### 2.1. “Đã vào mạng” không phải “đã được cấp quyền”

Một VPN có thể tạo đường hầm mã hóa và cấp cho client một địa chỉ trong VPN address pool. Hai bước này giúp **vận chuyển gói tin và nhận diện phiên**, nhưng không tự quyết định người dùng có được SSH, RDP, gọi API nội bộ hay truy vấn database hay không.

Nếu gateway gán mọi người vào cùng subnet và firewall chỉ có quy tắc **VPN subnet → Internal any**, một tài khoản quyền thấp có thể tiếp cận nhiều dịch vụ hơn mức cần thiết, dù những dịch vụ vẫn có lớp xác thực riêng.

### 2.2. Tại sao cần phòng vệ nhiều lớp?

- **Gateway** chặn những luồng không được phép ngay tại điểm truy cập từ xa.
- **Firewall/microsegmentation** giữ giới hạn giữa VPN zone và Application/Data/Management zone.
- **Bastion hoặc PAM** tạo đường quản trị có kiểm soát thay cho SSH/RDP trực tiếp tới nhiều máy.
- **Ứng dụng/API** xác thực và phân quyền theo danh tính người dùng hoặc service account ở tầng nghiệp vụ.
- **IDS/IPS, DNS logging và SIEM** phát hiện hoạt động bất thường sau kết nối.

Các lớp này bổ sung nhau; **không dùng VPN group như bằng chứng thay thế hoàn toàn quyền ở hệ thống đích**.

## 3. Group, role và attribute: chọn mô hình nào?

### 3.1. Nhóm danh tính (identity group)

**Group** là tập hợp tài khoản được hệ thống danh tính quản lý, ví dụ nhóm trong Active Directory, LDAP hoặc IdP cloud. Nhóm thường biểu diễn phòng ban, vai trò vận hành hoặc quyền truy cập một hệ thống cụ thể.

Ví dụ các nhóm:

- **VPN-Employees:** nhân viên được phép sử dụng VPN cho những ứng dụng công việc chung.
- **VPN-Developers:** kỹ sư phát triển cần môi trường phát triển và công cụ nội bộ.
- **VPN-Finance:** người được phê duyệt sử dụng hệ thống tài chính.
- **VPN-IT-Admins:** tài khoản có quyền vào đường quản trị có kiểm soát.
- **VPN-Contractors:** nhà thầu được truy cập dịch vụ đã ký hợp đồng.
- **VPN-SOC:** nhân sự an ninh cần dashboard, log và một số công cụ điều tra.

Tên chỉ mang tính minh họa. **Không nên biến mọi phòng ban thành quyền mạng quá rộng**: nhóm “AllEmployees” thường chỉ nên mở những dịch vụ phổ biến, không tự cho phép kết nối tới Data hoặc Management zone.

### 3.2. RBAC – phân quyền theo vai trò

**Role-Based Access Control (RBAC)** gom những quyền liên quan vào role rồi gán role cho người dùng. Role có thể được ánh xạ từ một hoặc nhiều nhóm trong IdP.

~~~mermaid
flowchart LR
    U["Người dùng"] --> G["Identity group / thuộc tính"]
    G --> R["VPN role"]
    R --> P["Chính sách theo tài nguyên"]
    P --> F["Gateway / firewall / app enforcement"]
    F --> A["Ứng dụng được phép"]
    F -. "Từ chối mặc định" .-> D["Tài nguyên ngoài phạm vi"]
~~~

Ưu điểm: dễ kiểm tra, tái sử dụng và rà soát quyền. Nhược điểm: nếu tạo nhiều nhóm kết hợp trùng nhau hoặc một nhóm quá rộng, chính sách dễ khó hiểu và nảy sinh **role explosion**.

### 3.3. ABAC – phân quyền theo thuộc tính

**Attribute-Based Access Control (ABAC)** còn xét những điều kiện như trạng thái quản lý thiết bị, loại ứng dụng, mức nhạy cảm tài sản, thời điểm truy cập hoặc tín hiệu rủi ro từ IdP/EDR.

Ví dụ: thành viên Finance chỉ được truy cập Finance Portal **nếu dùng thiết bị công ty đang đáp ứng kiểm soát bảo mật**. Điều kiện thiết bị là tín hiệu bổ sung, không thay thế group hoặc xác thực người dùng.

### 3.4. Quyền tối thiểu và theo thời gian

**Least privilege** đòi hỏi người dùng chỉ nhận quyền tối thiểu cho nhiệm vụ, trong phạm vi thời gian cần thiết. Một tài khoản hỗ trợ đối tác cần truy cập tạm thời không nên được giữ nhóm VPN-IT-Admins vô hạn.

**Just-in-Time (JIT)** hoặc quyền có thời hạn và phê duyệt giúp giảm thời gian quyền đặc biệt tồn tại. Cần bảo đảm cơ chế thu hồi có hiệu lực trên **phiên VPN đang hoạt động**, không chỉ sau lần đăng nhập tiếp theo.

## 4. Luồng xác thực và quyết định quyền truy cập

Một kiến trúc điển hình gồm **VPN client, VPN gateway, Identity Provider (IdP), nơi thực thi policy và tài nguyên nội bộ**:

~~~mermaid
sequenceDiagram
    participant U as Người dùng / thiết bị
    participant V as VPN gateway
    participant I as IdP / AAA
    participant P as Chính sách / firewall
    participant A as Ứng dụng
    U->>V: Bắt đầu phiên VPN
    V->>I: Yêu cầu xác thực / xác minh danh tính
    I-->>V: Kết quả, nhóm và thuộc tính theo cơ chế được hỗ trợ
    Note over V: Kiểm tra quyền dùng VPN và điều kiện thiết bị
    V-->>U: Thiết lập tunnel nếu được phép
    U->>V: Gửi yêu cầu tới dịch vụ nội bộ
    V->>P: Kiểm tra nhóm/role, tài nguyên và policy
    alt Được phép
      P-->>V: Allow
      V->>A: Chuyển tiếp kết nối
      Note over A: Ứng dụng kiểm tra quyền nghiệp vụ riêng
    else Không được phép
      P-->>V: Deny
      V-->>U: Chặn lưu lượng, có thể trả lỗi/timeout
    end
~~~

Đây là **sơ đồ logic**, không khẳng định mọi VPN phải có một máy policy engine tách rời. Một số giải pháp đánh giá role ngay trên gateway, một số đẩy group vào firewall, nhiều hệ thống tích hợp SASE/ZTNA hoặc truy cập theo ứng dụng.

### 4.1. Các bước cần kiểm soát

1. **Xác minh người dùng:** IdP/RADIUS/chứng thư/mật khẩu và MFA theo cấu hình.
2. **Xác minh thiết bị:** nếu yêu cầu, gateway hoặc endpoint agent kiểm tra chứng thư, quản lý thiết bị và trạng thái bảo mật.
3. **Nhận thông tin nhóm/role:** bảo đảm kết quả đến từ **nguồn tin cậy**, không từ chuỗi do client tự khai.
4. **Đánh giá quyền đăng nhập VPN:** tài khoản còn hiệu lực, được phép dùng VPN, chưa bị khóa, không hết thời hạn hợp đồng.
5. **Thiết lập phiên và gắn ngữ cảnh:** session ID, user ID, role, posture và địa chỉ tunnel được hệ thống quản lý liên kết.
6. **Thực thi quyền theo tài nguyên:** đối chiếu đích, ứng dụng, giao thức, cổng, vùng mạng và điều kiện thời gian.
7. **Tạo log và rà soát:** xác định từng quyết định allow/deny dựa trên chính sách và danh tính nào.

**Không coi group trong JWT, SAML assertion hoặc RADIUS attribute là đáng tin chỉ vì nó có mặt.** Thành phần nhận phải xác minh chữ ký/kênh, issuer, audience, thời hạn và chính sách cần thiết theo giao thức; đồng thời chống việc client tự cung cấp dữ liệu quyền.

## 5. Thiết kế ma trận nhóm → tài nguyên

Giả sử doanh nghiệp dùng các mạng **IPv4 private chỉ để minh họa**:

| Zone | Dải mạng ví dụ | Tài nguyên |
| --- | --- | --- |
| VPN client pool | 10.60.0.0/24 | Địa chỉ cấp cho thiết bị từ xa |
| Shared Applications | 10.20.10.0/24 | CRM, Intranet, ticket portal |
| Development | 10.20.20.0/24 | Dev portal, Git, CI |
| Finance | 10.20.30.0/24 | Finance Portal |
| Management | 10.20.90.0/24 | Bastion, công cụ quản trị |
| Data | 10.20.40.0/24 | Database, message broker |

**Ma trận quyền mẫu** (mọi ô không liệt kê được hiểu là **deny**):

| Nhóm | Tài nguyên | Giao thức/cổng | Điều kiện |
| --- | --- | --- | --- |
| VPN-Employees | Intranet | HTTPS/TCP 443 | Tài khoản hợp lệ, chính sách endpoint đạt |
| VPN-Employees | Ticket Portal | HTTPS/TCP 443 | Tài khoản hợp lệ |
| VPN-Developers | Dev Portal, Git | HTTPS/TCP 443 | Thiết bị được quản lý, MFA |
| VPN-Finance | Finance Portal | HTTPS/TCP 443 | MFA, thiết bị đạt kiểm soát, quyền nghiệp vụ tại ứng dụng |
| VPN-IT-Admins | Bastion | SSH/TCP 22 hoặc RDP/TCP 3389 **chỉ tới bastion phù hợp** | Tài khoản đặc quyền riêng, MFA mạnh, JIT/PAM |
| VPN-Contractors | Partner Test App | HTTPS/TCP 443 | Hợp đồng còn hiệu lực, đúng dự án, thiết bị và giờ được duyệt |
| VPN-SOC | Security Dashboard | HTTPS/TCP 443 | MFA, logging, quyền ứng dụng tương ứng |

Người dùng đã kết nối VPN không vì thế được truy cập trực tiếp **10.20.40.0/24 (Data)**. Những dịch vụ như CRM hoặc Finance Portal tự truy cập database bằng danh tính dịch vụ ở backend theo quy trình được cấp quyền **riêng**, không dùng quyền VPN của người dùng.

### 5.1. Vì sao giới hạn theo ứng dụng tốt hơn mở cả subnet?

Một rule cho **VPN-Finance → 10.20.30.0/24:any** có thể vô tình mở cả dịch vụ quản trị, database, agent debug hoặc máy phụ trong cùng subnet. Nếu chỉ cần Finance Portal, nên giới hạn **đúng IP/VIP/FQDN được chính sách hỗ trợ và cổng 443**, kết hợp kiểm tra quyền ngay trong ứng dụng.

Các rule dựa trên FQDN hoặc ứng dụng phụ thuộc tính năng gateway/firewall; không phải mọi firewall tự động theo dõi mọi IP thay đổi của FQDN hay mọi luồng HTTPS theo cùng cách. Cần xác minh hỗ trợ và kiểm thử thực tế.

### 5.2. Vì sao vẫn cần phân quyền ở ứng dụng?

Một rule allow TCP 443 tới Finance Portal chỉ xác định người dùng được **tạo kết nối mạng**. Ứng dụng vẫn phải quyết định họ được đọc báo cáo nào, xuất dữ liệu hay phê duyệt khoản thanh toán nào.

Ví dụ hai người cùng nhóm VPN-Finance có thể có **quyền nghiệp vụ khác nhau** trong ứng dụng. Không nên dịch tất cả quyền nghiệp vụ thành firewall rule theo IP.

## 6. Nhiều nhóm, nhóm lồng nhau và thứ tự ưu tiên

Một nhân viên có thể đồng thời thuộc **VPN-Employees**, **VPN-Developers** và một nhóm tạm thời **VPN-Project-A**. Cần xác định rõ cách hệ thống hợp nhất quyền:

- **Union:** người dùng nhận tập hợp quyền của các nhóm hợp lệ; thuận tiện nhưng có thể mở rộng quyền ngoài mong đợi.
- **Intersection/conditional:** phải đồng thời thỏa nhiều điều kiện, ví dụ thuộc Finance **và** thiết bị quản lý **và** có MFA.
- **Explicit deny:** một số hệ thống hỗ trợ deny có độ ưu tiên cao; thứ tự áp dụng tùy nền tảng.
- **Role priority / first-match:** một số VPN chỉ chọn một role hoặc một chính sách đầu tiên khớp.

**Không giả định mọi sản phẩm xử lý group overlap giống nhau.** Phải kiểm tra tài liệu của sản phẩm, giải thích rule precedence và thử với tài khoản thuộc nhiều nhóm.

### 6.1. Cần chính sách xung đột rõ ràng

Ví dụ tài khoản thuộc:

- **VPN-Contractors**: chỉ vào Partner Test App.
- **VPN-Employees**: vào Intranet.
- **VPN-IT-Admins**: vào Bastion theo quyền đặc biệt.

Nếu chỉ hợp nhất các allow rule mà không xét nguồn cấp, một nhà thầu bị gán nhầm VPN-Employees có thể nhận quyền nội bộ không phù hợp. Với quyền nhạy cảm như quản trị, nên yêu cầu **vai trò đặc quyền riêng và điều kiện bổ sung** thay vì thừa hưởng tự động từ nhóm rộng.

### 6.2. Group nesting và claim quá lớn

Trong AD/LDAP, một nhóm có thể chứa nhóm khác; trong IdP cloud, nhóm có thể được đồng bộ, tính động hoặc được gửi qua claims. **Không phải mọi VPN gateway đều mở rộng nested group** hoặc xử lý group claim vượt giới hạn kích thước giống nhau.

Cần xác minh:

1. Nguồn xác định membership cuối cùng là hệ thống nào?
2. Gateway nhận group bằng tên, ID bất biến, SID hay một ánh xạ riêng?
3. Nested membership có được tính không, có giới hạn độ sâu không?
4. Claim thiếu, quá lớn hoặc đồng bộ trễ thì **deny hay fallback sang quyền rộng**?
5. Có ghi được **group/role thực tế áp dụng cho phiên** để điều tra không?

Đặt **quyền tối thiểu** làm hành vi mặc định khi không xác định chắc nhóm.

## 7. Nguồn danh tính và tích hợp AAA

VPN thường tích hợp với một hoặc nhiều hệ thống:

| Công nghệ | Vai trò thường gặp | Lưu ý phân quyền |
| --- | --- | --- |
| **Active Directory / LDAP** | Lưu tài khoản, nhóm, thuộc tính, trạng thái user | Group membership, nested group và sync phải được xử lý rõ |
| **RADIUS** | AAA cho truy cập mạng, chuyển kết quả xác thực và thuộc tính theo sản phẩm | Các attribute như Filter-Id hoặc vendor-specific có thể mang policy/role, phải kiểm tra hỗ trợ |
| **SAML 2.0** | Liên kết đăng nhập (federation), chuyển assertion tới service provider | Xác thực issuer, chữ ký, audience, thời hạn; chỉ tin group claim được cấu hình |
| **OpenID Connect (OIDC)** | Giao thức danh tính dựa trên OAuth 2.0, có ID token và claims | Kiểm tra token, issuer, audience, nonce/flow theo nền tảng; không tin claims do client tự đặt |
| **Chứng thư client / PKI** | Xác minh danh tính thiết bị hoặc người dùng tùy thiết kế | Kiểm soát cấp phát, private key, thời hạn và thu hồi |
| **SCIM / đồng bộ danh tính** | Cấp phát, cập nhật và thu hồi user/group tới hệ thống đích | Đồng bộ trễ, mapping và lỗi provisioning ảnh hưởng quyền |

**SAML/OIDC không tự định nghĩa tập quyền network giống nhau trên mọi VPN**. Chính sách VPN dùng group claim nào, thuộc tính nào và ánh xạ ra role nào là trách nhiệm của cấu hình hệ thống nhận.

### 7.1. Quy tắc ánh xạ nên dùng định danh ổn định

Tên hiển thị của nhóm có thể đổi từ **Finance-VPN** thành **Accounting-VPN**, trong khi group ID không đổi. Ánh xạ theo **định danh bất biến được IdP bảo đảm** thường dễ kiểm toán hơn so với so chuỗi tên có thể đổi hoặc trùng nhau. Tùy sản phẩm, không phải giao thức nào cũng chuyển group ID theo một kiểu; phải kiểm tra hợp đồng dữ liệu và danh sách giá trị cho phép.

### 7.2. Không tin dữ liệu nhóm từ endpoint

Client không nên tự chọn gửi header hoặc chuỗi **role=admin** để có quyền. Gateway cần tin kết quả **đã xác minh** của IdP/AAA qua kênh và giao thức phù hợp, rồi gắn ngữ cảnh đó với phiên VPN đã xác thực.

### 7.3. Xử lý khi IdP không sẵn sàng

Một sự cố IdP có thể khiến người dùng mới không đăng nhập VPN được. Không nên tự chuyển sang **allow-all** khi hệ thống không xác minh được quyền. Thiết kế cần xem xét HA, phiên đã xác thực còn được tiếp tục trong bao lâu và cơ chế khẩn cấp có phê duyệt.

**Fail closed về quyền mới** là mục tiêu an toàn khi thiếu dữ liệu tin cậy, nhưng phải đánh giá riêng tác động tới tính liên tục của những phiên đang hoạt động.

## 8. Nơi thực thi quyền VPN

**Quyền chỉ có hiệu lực khi có một thành phần chặn/cho traffic thật sự dựa trên quyền đó.** Những vị trí thường gặp:

### 8.1. VPN gateway

Gateway có thể đánh giá role khi người dùng đăng nhập và gắn ACL/firewall policy hoặc danh sách application resources vào session. Một số gateway phân người dùng vào những address pool hoặc tunnel khác nhau theo group.

Điều phải kiểm tra: policy được **gắn với danh tính/phiên thực tế** hay chỉ đổi route ở phía client? Gateway có kiểm tra cả chiều đi và chiều về? Có xử lý IPv6 và reauthentication không?

### 8.2. Firewall tại ranh giới VPN zone

Một kiến trúc khác cho traffic VPN đi qua firewall hoặc NGFW có thể sử dụng **user/group identity mapping**, source zone, destination zone và application policy. Nếu firewall không biết identity, có thể dùng address pool theo nhóm **khi việc ánh xạ pool/phiên được kiểm soát chắc chắn**.

Không được giả định một source IP trong pool luôn thuộc đúng một user, bởi IP có thể được cấp lại và NAT có thể che nhiều phiên. Nếu dùng IP–identity mapping, cần bảo vệ cơ chế đồng bộ và thu hồi ánh xạ đúng thời điểm.

### 8.3. Microsegmentation và workload policy

Khi ứng dụng nằm trên nhiều subnet, container, VM hoặc cloud VPC/VNet, microsegmentation bổ sung lớp **deny theo workload**, tránh để một VPN session có khả năng kết nối ngang giữa các tài sản chỉ vì tuyến đã thông.

### 8.4. Bastion / jump host / privileged access management

Thay vì cho nhóm IT Admin kết nối SSH/RDP trực tiếp tới mọi máy, có thể bắt buộc đi qua **bastion/PAM** với tài khoản đặc quyền, MFA, ghi nhật ký và quyền được duyệt. Gateway chỉ cho tới bastion; bastion hoặc hệ thống quản trị mới quyết định người quản trị được truy cập máy nào.

### 8.5. Authorization trong ứng dụng

Ứng dụng/API tiếp tục kiểm tra danh tính, quyền vai trò và bản ghi dữ liệu. VPN không tự ngăn **Broken Object Level Authorization (BOLA)** hoặc lỗi truy cập dữ liệu giữa người dùng trong cùng một ứng dụng.

## 9. Thiết kế kiến trúc phân đoạn cho truy cập từ xa

~~~mermaid
flowchart TD
    U["Nhân viên / nhà thầu / quản trị viên"] -->|"Tunnel được xác thực"| V["VPN Gateway"]
    V -->|"AuthN / group / MFA"| I["IdP / AAA"]
    V -->|"Session identity / role"| P["Policy enforcement"]
    P --> F["Firewall / VPN access zone"]
    F -->|"Employees: HTTPS"| A["Intranet và Ticket Portal"]
    F -->|"Developers: HTTPS"| DEV["Dev Portal / Git"]
    F -->|"Finance: HTTPS"| FIN["Finance Portal"]
    F -->|"Admins có JIT/MFA"| B["Bastion / PAM"]
    F -->|"Contractor theo hợp đồng"| C["Partner Test App"]
    F -. "Không truy cập trực tiếp" .-> DB[("Data zone / Database")]
    P -. "Session và access logs" .-> SOC["SIEM / SOC"]
    B -. "Privileged audit logs" .-> SOC
    FIN -. "App authorization logs" .-> SOC
~~~

**Đường chấm đến Data zone là deny theo nguyên tắc**, không phải một đường chuyển tiếp thực tế. Các server trong Application zone có thể truy cập Data zone bằng những policy và danh tính dịch vụ riêng đã được phê duyệt.

### 9.1. Một chính sách mẫu

Giả sử Alice thuộc nhóm **VPN-Developers**, kết nối từ laptop được quản lý. Chính sách cho phép Alice vào Dev Portal qua TCP 443. Nếu Alice cố mở kết nối TCP 5432 trực tiếp tới database, gateway/firewall phải **deny**, kể cả khi route đến subnet Data tồn tại trên thiết bị.

Nếu Alice chuyển sang nhóm **VPN-Finance** theo quy trình HR/IAM, quyền mới chỉ có hiệu lực theo chính sách đồng bộ và thời gian cập nhật; quyền cũ cần được thu hồi ở cả **IdP và những phiên đang hoạt động** theo yêu cầu.

### 9.2. Không chỉ dựa vào quy tắc nguồn IP

Một rule **10.60.0.0/24 → 10.20.0.0/16:any allow** tạo rủi ro lớn vì toàn bộ pool được cấp cùng quyền. Nếu không thể truyền identity tới firewall, hãy sử dụng cách thiết kế thay thế được kiểm soát như pool riêng cho role hoặc gateway policy, kèm giám sát chống trộn pool và kiểm thử thu hồi.

## 10. Split tunneling, full tunneling và phạm vi chính sách

**Full tunnel** thường đưa phần lớn hoặc toàn bộ IP traffic qua đường VPN theo cấu hình, trong khi **split tunnel** chỉ chuyển những route/ứng dụng được định nghĩa qua VPN và để traffic khác đi trực tiếp ra mạng hiện tại.

| Khía cạnh | Full tunnel | Split tunnel |
| --- | --- | --- |
| Đường đi traffic | Phần lớn/tất cả theo tunnel tùy cấu hình | Chỉ route/ứng dụng được định nghĩa đi tunnel |
| Quan sát ở VPN gateway | Nhiều traffic hơn có thể được kiểm tra tại trung tâm | Gateway chỉ thấy traffic đi vào tunnel |
| Băng thông gateway | Có thể cần công suất lớn hơn | Có thể giảm tải cho gateway |
| Rủi ro | Nút nghẽn trung tâm, vấn đề hiệu năng/riêng tư | Traffic ngoài tunnel không đi qua kiểm soát tập trung tương ứng |
| Quyền truy cập tài nguyên nội bộ | Vẫn phải áp dụng ACL/firewall | Vẫn phải áp dụng ACL/firewall |

**Quan trọng:** split tunnel là quyết định định tuyến và quan sát; **không phải** cơ chế tự cấp/thu hồi quyền. Nếu client có route tới một mạng nội bộ nhưng gateway không cho phép, traffic cần bị chặn. Ngược lại, không có route trên client lúc này không đảm bảo policy bảo mật đủ chặt nếu client hoặc đường đi có thể thay đổi.

### 10.1. Route push không thay thế firewall

Nhiều VPN client nhận route do gateway cấu hình. Người dùng có thể thấy route đến một subnet trong bảng định tuyến dù không được phép truy cập từng dịch vụ ở subnet đó.

Đẩy route chỉ quyết định **gói đi đâu**; thành phần thực thi chính sách phải quyết định **gói có được đi tiếp hay không**. Không dùng việc “không đẩy route đến Finance” làm lớp phân quyền duy nhất.

### 10.2. Split DNS và DNS leak

VPN có thể cung cấp DNS resolver nội bộ và split DNS theo namespace. Nếu cấu hình sai, tên hệ thống nội bộ có thể:

- Không phân giải được dù kết nối mạng tới ứng dụng đã được phép.
- Bị gửi tới resolver ngoài mong muốn, làm lộ metadata tên miền hoặc gây sai kết quả.
- Trả về IP khác với route/zone mà chính sách VPN dự kiến.

DNSSEC xác thực dữ liệu DNS được ký trong phạm vi phù hợp; DoH/DoT bảo vệ kênh client–resolver khi cấu hình đúng. **DNS không quyết định quyền truy cập ứng dụng**, vì vậy vẫn cần firewall và application authorization.

### 10.3. IPv6 và dual stack

Thiết kế chỉ chặn IPv4 nhưng không xét IPv6 có thể để lại đường đến dịch vụ qua address family khác nếu hạ tầng hỗ trợ. Phải kiểm tra:

- VPN client và gateway có chở IPv6 không?
- Có route IPv6 nội bộ và DNS AAAA hay không?
- Firewall/ACL cho IPv6 có tương đương chính sách nhóm IPv4 không?
- Traffic IPv6 nằm trong hay ngoài tunnel theo cấu hình nào?

Không suy rằng tắt IPv6 ở một interface bất kỳ sẽ tự sửa mọi sai lệch hoặc an toàn hơn. Cần chính sách dual stack nhất quán theo nền tảng.

### 10.4. NAT, overlapping CIDR và cloud

Nếu mạng nhà người dùng trùng CIDR với subnet nội bộ, route có thể đi sai hướng dù quyền hợp lệ. NAT cũng có thể làm nhiều phiên xuất hiện cùng source IP ở điểm quan sát sau gateway.

Trong cloud/hybrid, quyền VPN nên được thực thi đồng thời với VPC/VNet route policy, security group/firewall và quyền IAM. **Route được công bố qua BGP/VPN không mặc nhiên cho phép truy cập an toàn** tới mọi subnet trong cloud.

## 11. MFA, chứng thư thiết bị và posture

**MFA** giúp giảm rủi ro khi mật khẩu bị lộ, nhưng không tự giới hạn người dùng tới đúng tài nguyên. Người dùng có thể hoàn thành MFA và vẫn cần bị từ chối kết nối tới database hoặc management zone nếu không có role tương ứng.

### 11.1. Điều kiện an toàn thường kết hợp

| Điều kiện | Mục tiêu | Giới hạn |
| --- | --- | --- |
| MFA, ưu tiên phương thức chống phishing khi khả thi | Bảo vệ bước đăng nhập | Không thay thế resource authorization |
| Chứng thư client / device identity | Nhận diện thiết bị đã đăng ký | Không tự xác định người dùng có quyền nghiệp vụ nào |
| MDM compliance | Kiểm tra một số điều kiện cấu hình thiết bị | Tín hiệu có thể trễ hoặc thiếu; cần quy trình xử lý ngoại lệ |
| EDR posture | Đánh giá tình trạng bảo vệ endpoint | Không phải bảo đảm tuyệt đối máy không bị chiếm |
| JIT/PAM | Giảm thời gian quyền đặc biệt có hiệu lực | Cần thu hồi phiên/role thực tế khi hết hạn |
| Conditional access | Kết hợp người dùng, thiết bị, rủi ro, tài nguyên | Phải kiểm tra tích hợp gateway và các điều kiện thật sự được thực thi |

### 11.2. Tài khoản đặc quyền

Với nhóm **VPN-IT-Admins**, nên áp dụng:

1. **Tài khoản quản trị riêng** nếu chính sách tổ chức yêu cầu, không dùng một tài khoản thường cho mọi hoạt động.
2. **MFA mạnh** và thiết bị tin cậy/phê duyệt; cân nhắc privileged access workstation (PAW).
3. **Bastion hoặc PAM** thay vì SSH/RDP thẳng vào mọi server.
4. Quyền có thời hạn, ticket và người phê duyệt cho thao tác nhạy cảm.
5. Log hành động quản trị phù hợp quy định, tránh thu thập bí mật không cần thiết.

### 11.3. Thiết bị không đạt posture

Nếu thiết bị không có chứng thư, chưa được MDM quản lý hoặc không đạt kiểm soát bắt buộc, chính sách có thể **từ chối VPN** hoặc chỉ cho vào vùng remediation được thiết kế riêng. Không mở truy cập nhạy cảm chỉ vì người dùng thuộc đúng group.

## 12. Quyền theo phiên, hiệu lực thay đổi và thu hồi

Nhóm trong IdP có thể thay đổi **trong lúc phiên VPN vẫn còn hoạt động**. Một số gateway đọc membership chỉ khi đăng nhập; một số hỗ trợ reauthorization, reauthentication hoặc nhận sự kiện thu hồi gần thời gian thực.

### 12.1. Joiner–Mover–Leaver (JML)

| Sự kiện | Tác vụ IAM | Tác vụ VPN/policy |
| --- | --- | --- |
| **Joiner** – người mới | Tạo tài khoản, gán nhóm tối thiểu | Chỉ cho VPN và tài nguyên đã được duyệt |
| **Mover** – đổi phòng ban/dự án | Gỡ nhóm cũ, thêm nhóm mới theo phê duyệt | Thu hồi quyền cũ, đánh giá phiên đang mở |
| **Leaver** – nghỉ việc/hết hợp đồng | Khóa/thu hồi tài khoản và credential liên quan | Chấm dứt hoặc vô hiệu hóa phiên, loại bỏ quyền truy cập |
| **Temporary escalation** – quyền tạm | Gán JIT có thời hạn và ticket | Giới hạn phạm vi và xác minh thu hồi khi hết hạn |
| **Incident containment** – phản ứng sự cố | Vô hiệu quyền theo quy trình | Chấm dứt session/token hoặc policy quyền ở điểm thực thi |

**Không được xem việc gỡ khỏi group là bằng chứng mọi quyền đã bị thu hồi tức thì.** Cần biết token/session cache, group sync interval, VPN lease, firewall identity mapping và thời gian duy trì phiên.

### 12.2. Cửa sổ trễ và token cache

Giả sử một người bị loại khỏi nhóm Finance lúc 14:00, nhưng phiên VPN có thời hạn đến 18:00 và role được chụp tại thời điểm login. Nếu gateway không nhận thay đổi hoặc không buộc reauthentication, người đó có thể còn truy cập Finance Portal ở tầng mạng đến khi phiên bị cập nhật/chấm dứt.

Hệ thống nên có **giới hạn tuổi phiên, cơ chế thu hồi chủ động theo năng lực**, nhật ký sự kiện và SLA thu hồi tùy mức nhạy cảm. Với tài khoản đặc quyền, yêu cầu thu hồi thường chặt hơn quyền ứng dụng phổ thông.

### 12.3. Break-glass

Tài khoản **break-glass** cho khẩn cấp phải có chủ sở hữu, MFA/kiểm soát khác phù hợp, giám sát và thời hạn sử dụng. Không tạo một nhóm **VPN-Emergency-All-Access** vô hạn rồi coi đó là phương án duy trì hoạt động.

## 13. Chính sách mẫu trung lập với nhà cung cấp

Đoạn YAML sau mô tả **ý định phân quyền**, không phải cú pháp cấu hình có thể áp dụng trực tiếp trên một thiết bị VPN, firewall, SASE hoặc IdP cụ thể.

~~~yaml
vpnAccessPolicy:
  name: remote-access-group-authorization
  environment: synthetic-training
  defaults:
    vpnLogin: deny-unless-explicitly-entitled
    resourceAccess: deny
    unknownGroup: deny
    missingIdentityClaim: deny
    unmanagedDevice: deny-sensitive-resources
  identity:
    source: approved-enterprise-idp
    groupMappingKey: stable-group-identifier
    validateIssuerAudienceAndSignature: true
    verifyAccountActive: true
    multiGroupHandling: explicitly-defined-by-platform
  session:
    requireMfa: true
    bindIdentityToTunnelSession: true
    recordSessionAndPolicyVersion: true
    recheckOnRoleChangeWhereSupported: true
    limitSessionLifetimeByRisk: true
  roles:
    - name: employees
      sourceGroups: [VPN-Employees]
      access:
        - service: intranet
          destination: 10.20.10.10/32
          protocol: tcp
          port: 443
        - service: ticket-portal
          destination: 10.20.10.20/32
          protocol: tcp
          port: 443
    - name: developers
      sourceGroups: [VPN-Developers]
      conditions: [managed-device, mfa]
      access:
        - service: dev-portal
          destination: 10.20.20.10/32
          protocol: tcp
          port: 443
    - name: finance
      sourceGroups: [VPN-Finance]
      conditions: [managed-device, mfa, app-authorization]
      access:
        - service: finance-portal
          destination: 10.20.30.10/32
          protocol: tcp
          port: 443
    - name: admins
      sourceGroups: [VPN-IT-Admins]
      conditions: [privileged-identity, approved-device, strong-mfa, jit-approved]
      access:
        - service: bastion
          destination: 10.20.90.10/32
          protocol: tcp
          port: 22
    - name: contractors
      sourceGroups: [VPN-Contractors]
      conditions: [active-contract, project-approved, mfa]
      access:
        - service: partner-test-app
          destination: 10.20.20.50/32
          protocol: tcp
          port: 443
  explicitDeny:
    - direct-vpn-user-to-database
    - unmanaged-device-to-management
    - unknown-group-to-internal-services
  observability:
    logAuthenticationAndAuthorization: true
    logDeniedConnections: true
    redactSensitiveFields: true
    correlateWithIdpAndApplicationLogs: true
  governance:
    requireRoleOwner: true
    requireChangeTicket: true
    reviewMembershipPeriodically: true
    expireTemporaryAccess: true
    testRevocation: true
~~~

Các giá trị như **privileged-identity**, **jit-approved** hoặc **validateIssuerAudienceAndSignature** là yêu cầu mô hình hóa: việc chúng được hỗ trợ và thi hành cụ thể phải được xác minh trong sản phẩm thật. Đặc biệt, trường **sourceGroups** không tự thực thi nhóm nếu gateway không có cơ chế ánh xạ hợp lệ.

### 13.1. Vì sao mẫu không cho trực tiếp tới database?

Nếu Finance Portal hoặc Dev Portal cần dữ liệu ở database, kết nối từ **server ứng dụng** tới DB phải dùng policy dịch vụ riêng, không phải kéo quyền TCP 5432 trực tiếp tới client VPN. Điều này giảm khả năng client bị chiếm có thể giao tiếp trực tiếp với Data zone.

### 13.2. Chứng minh quyền bằng kết quả chặn

Một chính sách “deny unknown” chỉ có giá trị khi kiểm thử cho thấy **tài khoản không nhóm, claim lỗi và phiên không đủ điều kiện thật sự không đến được đích**. Không dùng việc file YAML có dòng deny làm bằng chứng sản phẩm đang thực thi chính sách.

## 14. Ghi log và tương quan sự kiện truy cập

Trong môi trường VPN, phân quyền là bài toán có **nhiều thành phần ghi log**. Một alert trên firewall ghi source IP chưa chắc xác định được ai đang dùng địa chỉ đó nếu VPN gateway cấp lại IP, có NAT hoặc mapping đã hết hạn.

### 14.1. Những trường cần theo dõi

| Nguồn log | Trường quan trọng | Công dụng |
| --- | --- | --- |
| IdP/AAA | User ID bất biến, nhóm/role, MFA, token/assertion event, thời gian | Xác minh danh tính và kết quả group mapping |
| VPN gateway | Session ID, user ID, client identity, tunnel IP, thiết bị, thời gian đăng nhập/đăng xuất | Ghép lưu lượng vào phiên VPN |
| Policy/firewall | Rule ID, decision allow/deny, source/destination, port, role, policy version | Kiểm chứng thực thi quyền ở mạng |
| EDR/MDM | Device ID, compliance, thời điểm cập nhật posture | Xác nhận điều kiện thiết bị |
| Bastion/PAM | Phiên đặc quyền, người phê duyệt, tài sản đích | Rà soát truy cập quản trị |
| Application/API | Authenticated user, business role, resource action, outcome | Xác nhận quyền tại ứng dụng |
| SIEM | Correlation ID, thời điểm chuẩn hóa, incident/ticket | Ghép nhiều nguồn, phát hiện mẫu bất thường |

**Không ghi token, cookie phiên, OTP, private key hoặc mật khẩu** vào log để “dễ điều tra”. Những dữ liệu nhạy cảm cần được che, giới hạn quyền xem và có thời gian lưu giữ phù hợp.

### 14.2. Log JSON giả lập

~~~json
{
  "timestamp": "2026-11-28T15:20:00+07:00",
  "event": "vpn_resource_access",
  "vpn_session_id": "lab-vpn-session-0812",
  "user_id": "employee-lab-022",
  "device_id": "managed-lab-laptop-09",
  "assigned_role": "developers",
  "source_tunnel_ip": "10.60.0.22",
  "destination_ip": "10.20.40.10",
  "destination_port": 5432,
  "transport": "tcp",
  "policy_id": "deny-direct-vpn-to-data",
  "decision": "deny",
  "mfa_verified_at_login": true,
  "application_access_confirmed": false,
  "dataset": "synthetic-training-data"
}
~~~

Log cho thấy gateway/firewall đã **từ chối một kết nối từ phiên Developers tới database**. Nó không chứng minh có ý định tấn công: người dùng có thể nhập nhầm đích hoặc chạy phần mềm bị cấu hình sai. Mặt khác, nếu thấy allow, cũng chưa chứng minh người dùng được ứng dụng cho phép xem dữ liệu.

### 14.3. Tránh gán danh tính từ IP đơn lẻ

Địa chỉ tunnel IP có thể được tái sử dụng; tại egress NAT, nhiều user có thể dùng cùng source IP. Khi điều tra cần gắn **thời điểm + session ID + user ID + source IP + policy version** hoặc mapping đã được gateway ghi nhận.

## 15. Giám sát và đánh giá chất lượng phân quyền

Một hệ thống có policy đúng trên giấy vẫn có thể cấp sai quyền do đồng bộ nhóm trễ, định tuyến vòng ngoài, cấu hình rule quá rộng hoặc gateway không áp dụng identity như dự kiến.

### 15.1. Những chỉ số cần theo dõi

- Số phiên VPN theo role, vùng mạng và loại thiết bị.
- Tỷ lệ đăng nhập bị từ chối do không có quyền sử dụng VPN.
- Số sự kiện truy cập tài nguyên bị deny theo nhóm/đích.
- Tần suất truy cập đích nhạy cảm từ nhóm không được cấp phép.
- Số account có **nhiều nhóm xung đột** hoặc nhóm đặc quyền chưa hết hạn.
- Thời gian từ khi HR/IAM thu hồi quyền đến khi **phiên đang hoạt động mất quyền thực tế**.
- Tỷ lệ policy update thất bại, identity mapping stale hoặc group claim thiếu.
- Tỷ lệ client hợp lệ không vào được ứng dụng do false positive.
- Khả năng giám sát IPv6, split tunnel và các tuyến cloud/hybrid.

### 15.2. Các câu hỏi kiểm toán

1. Ai là **chủ sở hữu** của mỗi nhóm VPN?
2. Thành viên nào có quyền truy cập Management/Data, tại sao?
3. Nhóm “AllEmployees” có vô tình được cấp quyền quá rộng không?
4. Một nhà thầu hết hạn vẫn còn phiên VPN hoặc group mapping nào không?
5. Firewall nào chặn lưu lượng VPN tới Data zone?
6. Nếu IdP hoặc đồng bộ nhóm không hoạt động, quyền truy cập thay đổi ra sao?
7. Một người chuyển phòng ban có bị giữ quyền cũ trong phiên VPN?
8. Thiết bị không được quản lý có thể dùng cùng nhóm để tới tài nguyên nhạy cảm không?

Các câu hỏi này nên được kiểm tra bằng **cấu hình và kết quả thử nghiệm**, không chỉ bằng danh sách group được xuất từ IdP.

## 16. Kiểm thử phân quyền VPN trong lab được cấp phép

Chỉ dùng **tài khoản giả lập, tài nguyên thử nghiệm hoặc môi trường được tổ chức cho phép**. Không sử dụng quyền của người khác và không thử truy cập trái phép ứng dụng production để “chứng minh” firewall có lỗ hổng.

### 16.1. Ma trận test

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T-01 | Employee hợp lệ, MFA đầy đủ, thiết bị đạt kiểm soát | Kết nối VPN và mở Intranet/Ticket Portal được phép |
| T-02 | Employee cố truy cập trực tiếp Data zone | Kết nối bị deny tại policy enforcement |
| T-03 | Developer mở Dev Portal qua HTTPS | Allow đúng resource và log session/role |
| T-04 | Developer yêu cầu TCP 5432 tới database | Deny, dù client có route tới subnet đích |
| T-05 | Finance dùng laptop chưa đạt posture | Deny VPN hoặc chặn Finance Portal theo chính sách |
| T-06 | IT Admin vào bastion với MFA/JIT và thiết bị phù hợp | Allow đúng bastion, vẫn deny kết nối trực tiếp tới mọi server không được cấp |
| T-07 | Contractor hết hạn hợp đồng | Không tạo phiên mới; phiên cũ được xử lý theo SLA thu hồi |
| T-08 | Người thuộc hai nhóm có quyền chồng lấn | Role/rule precedence đúng thiết kế, không mở quyền ngoài ý muốn |
| T-09 | Thiếu hoặc sai group claim từ IdP | Không fallback sang role toàn quyền, ghi lỗi xác định |
| T-10 | Người bị gỡ Finance giữa phiên | Phiên bị reauthorize/terminate theo SLA; không giữ quyền vô hạn |
| T-11 | Truy cập Finance Portal qua IPv6 nếu hệ thống có dual stack | Chính sách deny/allow tương đương IPv4 |
| T-12 | Split tunnel và DNS nội bộ | Chỉ lưu lượng dự kiến đi tunnel; firewall vẫn chặn tài nguyên ngoài quyền |
| T-13 | IdP/AAA lỗi trong lab | Hành vi fail mode đúng thiết kế; không cấp quyền mặc định rộng |
| T-14 | Một client bị NAT hoặc IP pool tái sử dụng | Log vẫn tương quan đúng user–session–time, không gán sai danh tính |

### 16.2. Phép kiểm tra kết nối vô hại

Trong lab do bạn quản lý, có thể dùng phép kiểm tra **kết nối TCP thông thường** để xác nhận một dịch vụ đang được allow hoặc deny; không cần mô phỏng khai thác:

~~~powershell
# Windows: dùng địa chỉ/dịch vụ lab đã được cho phép kiểm thử.
Test-NetConnection -ComputerName 10.20.20.10 -Port 443
Test-NetConnection -ComputerName 10.20.40.10 -Port 5432
~~~

~~~bash
# Linux/macOS nếu có nc phù hợp: kiểm tra khả năng mở TCP tới endpoint lab.
nc -vz -w 3 10.20.20.10 443
nc -vz -w 3 10.20.40.10 5432
~~~

**Một kết nối thất bại không tự chứng minh rule deny hoạt động**: dịch vụ có thể đang tắt, đường mạng lỗi hoặc DNS/route sai. Cần kiểm tra **firewall/gateway logs** cho chính xác rule và action, đồng thời bảo đảm dịch vụ lab đang hoạt động.

**Một kết nối TCP thành công cũng không chứng minh quyền ứng dụng đúng**: cần kiểm tra ứng dụng riêng bằng account lab và vai trò nghiệp vụ tương ứng.

### 16.3. Kiểm tra hiệu lực quyền theo thời gian

Với một tài khoản lab thuộc Finance, có thể thực hiện chuỗi an toàn:

1. Đăng nhập VPN bằng tài khoản đã được phép thử nghiệm.
2. Ghi session ID, role, policy và kết nối Finance Portal được phép.
3. Nhóm IAM gỡ membership theo kịch bản lab và ghi thời điểm.
4. Theo dõi cơ chế đồng bộ, reauthorization hoặc hết hạn session theo thiết kế.
5. Xác nhận **quyền truy cập Finance Portal thực sự bị thu hồi**, không chỉ membership trong IdP đã thay đổi.
6. Đánh giá tổng thời gian từ thay đổi danh tính tới khi enforcement có hiệu lực.

Đây là phép kiểm thử quan trọng vì nhiều lỗ hổng phân quyền VPN nằm ở **khoảng trễ thu hồi**, không phải cấu hình allow/deny ban đầu.

## 17. Quy trình ứng phó khi phát hiện cấp quyền VPN sai

Giả sử SOC thấy tài khoản thuộc nhóm **VPN-Contractors** có lưu lượng tới Management zone không nằm trong ma trận được phê duyệt. Cần điều tra theo bằng chứng và phạm vi.

### Giai đoạn 1 – Xác minh

1. Thu thập **session ID, user ID, nhóm/role, thời điểm, IP tunnel và thiết bị** từ VPN.
2. Đọc event tại firewall: rule ID nào đã allow, policy version nào đang áp dụng?
3. Đối chiếu IdP group, chính sách đã duyệt, thay đổi gần nhất và trạng thái contract/JIT.
4. Kiểm tra kết nối có thực sự đi tới tài nguyên hay chỉ là một log candidate/truy cập thử.
5. Xác định những account/phiên khác cùng rule có thể bị ảnh hưởng.

### Giai đoạn 2 – Giảm thiểu

1. Nếu xác nhận quyền sai và có rủi ro, **thu hồi role hoặc chặn tại điểm enforcement** theo quy trình ứng phó.
2. Khi cần, chấm dứt các phiên VPN liên quan và thu hồi token/credential theo chính sách.
3. Sửa rule quá rộng, lỗi identity mapping hoặc pool binding; ghi ticket và người duyệt.
4. Tránh xóa toàn bộ policy hoặc chặn tất cả nhân viên nếu chưa đánh giá tác động tới dịch vụ.

### Giai đoạn 3 – Xác minh và phòng ngừa tái diễn

1. Chạy lại **negative test**: Contractor phải bị deny Management; Employee/Finance hợp lệ vẫn truy cập đúng đích.
2. Xác minh IPv4/IPv6, split tunnel và những đường cloud không bypass policy.
3. Kiểm tra mapping sau khi user đổi nhóm hoặc VPN reconnect.
4. Ghi timeline, nguồn lỗi, khối ảnh hưởng và kế hoạch giám sát.

**Không coi có log đến Management là bằng chứng người dùng đã đọc dữ liệu nhạy cảm.** Cần ứng dụng/bastion logs và đánh giá tác động cụ thể.

## 18. Tình huống tổng hợp: quyền nhà thầu bị mở rộng sau thay đổi nhóm

Một nhà thầu dự án A có tài khoản trong nhóm **VPN-Contractors**. Nhà thầu được phép vào **Partner Test App (HTTPS)**. Sau một lần thay đổi IdP, tài khoản bị thêm nhầm vào **VPN-Employees**. VPN gateway cấu hình **union of group permissions** nên nhà thầu có thêm quyền đến Intranet và Ticket Portal.

### 18.1. Phân tích nguyên nhân

1. **Nguồn quyền:** IdP đã phát group membership không đúng; gateway ánh xạ nhiều nhóm theo union.
2. **Thiếu kiểm soát xung đột:** hệ thống không hạn chế contractor identity khi được gán nhóm employee.
3. **Thiếu giám sát thay đổi:** không có cảnh báo khi tài khoản nhà thầu nhận role mới hoặc khả năng truy cập vượt hợp đồng.
4. **Khoảng trễ thu hồi:** ngay cả khi IAM sửa group, phiên đang hoạt động có thể còn giữ quyền tới khi được cập nhật.

### 18.2. Phương án khắc phục

- IAM gỡ nhóm sai và kiểm soát người có quyền thay membership.
- VPN policy có **điều kiện chặn quyền rộng** cho danh tính contractor chưa chuyển loại chính thức.
- Gateway/firewall áp dụng quyền hẹp theo role và resource, không cho cả VPN subnet vào mạng nội bộ.
- Triển khai session reauthorization hoặc terminate có kiểm soát khi group thay đổi.
- SOC theo dõi sự kiện **contractor → employee/admin role** và cảnh báo quyền tăng bất thường.
- Ứng dụng vẫn yêu cầu quyền nghiệp vụ riêng, nên việc mở cổng HTTPS không tự cho xem mọi dữ liệu.

### 18.3. Chứng minh đã sửa

Dùng tài khoản lab tương tự, trước/sau thay đổi:

- **Partner Test App:** vẫn truy cập khi hợp đồng còn hiệu lực.
- **Intranet:** bị từ chối nếu chính sách không cho phép contractor.
- **Finance Portal:** bị từ chối.
- **Bastion:** bị từ chối.
- **Role trong phiên:** phản ánh đúng sau thay đổi và không giữ quyền cũ quá SLA.

**Bài học:** Phân quyền theo nhóm chỉ vững khi **quy trình gán nhóm, xử lý nhóm chồng lấn và thực thi phiên** cùng tuân thủ nguyên tắc quyền tối thiểu.

## 19. Những sai lầm cần tránh

| Sai lầm | Rủi ro | Cách làm phù hợp |
| --- | --- | --- |
| “Ai kết nối VPN được thì vào hết nội bộ” | Mở rộng khả năng di chuyển ngang | Deny-by-default, nhóm/role và resource allowlist |
| Chỉ push route để phân quyền | Route có thể thay đổi; không phải cơ chế chặn | Enforcement tại gateway/firewall/app |
| Dựa vào source IP mà không gắn phiên/identity | IP tái sử dụng hoặc NAT làm gán sai quyền | Session-aware mapping, log identity đáng tin |
| Group AllEmployees được phép any-to-internal | Tăng bề mặt tấn công cho tài khoản phổ thông | Chỉ mở Intranet, Ticket Portal và dịch vụ thực sự cần |
| Cho VPN-IT-Admins truy cập trực tiếp mọi server | Mở rộng đường quản trị | Bastion/PAM, JIT, role đặc quyền tách biệt |
| Chỉ kiểm tra MFA mà không xét role | Người không có quyền vẫn tới tài nguyên | AuthN và AuthZ độc lập |
| Không xử lý nested/overlapping group | Quyền có thể cộng dồn ngoài ý muốn | Chính sách precedence, nhóm xung đột và negative tests |
| Tin group claim do client tự gửi | Có thể giả mạo vai trò | Xác minh token/AAA và nguồn nhóm được duyệt |
| Thu hồi membership nhưng để session sống vô hạn | Người nghỉ việc/đổi vai trò giữ quyền cũ | Reauthorization, session TTL, terminate theo SLA |
| IdP lỗi thì fallback allow-all | Mất kiểm soát danh tính/nhóm | Thiết kế fail mode an toàn và HA |
| Bỏ qua IPv6/split tunnel/cloud | Có đường đi ngoài kiểm soát dự kiến | Kiểm kê address families, routing và policy toàn tuyến |
| Không kiểm tra ứng dụng sau kết nối | VPN allow bị nhầm là quyền đọc dữ liệu | Authorization độc lập tại dịch vụ |
| Ghi token/OTP trong log VPN | Rò rỉ bí mật khi phân tích sự cố | Redaction, RBAC log và retention |
| Chỉ test luồng được phép | Không biết quyền thừa có bị từ chối | Positive + negative test cho từng nhóm |

## 20. Câu hỏi tự kiểm tra

### Câu hỏi 1

Tại sao đăng nhập VPN thành công không đồng nghĩa người dùng được kết nối tới database?

**Gợi ý:** xác thực người dùng và quyền theo tài nguyên là hai bước khác nhau. VPN tạo đường kết nối; gateway/firewall quyết định traffic được đi đến đâu, ứng dụng quyết định quyền nghiệp vụ.

### Câu hỏi 2

Trong RBAC, khác biệt giữa **identity group**, **VPN role** và **firewall rule** là gì?

**Gợi ý:** group ghi nhận membership từ IdP; role là cách nhóm quyền; firewall/gateway rule là cơ chế thực thi đối với lưu lượng.

### Câu hỏi 3

Một tài khoản thuộc cả VPN-Contractors và VPN-IT-Admins. Vì sao phải biết cơ chế hợp nhất quyền của sản phẩm?

**Gợi ý:** union/priority/explicit deny khác nhau có thể gây leo thang quyền; tài khoản đặc quyền phải có điều kiện độc lập và phê duyệt.

### Câu hỏi 4

Đẩy route chỉ tới Intranet xuống client có đủ để ngăn truy cập Finance Portal không?

**Gợi ý:** không. Routing không phải enforcement; phải có kiểm soát tại gateway/firewall/app.

### Câu hỏi 5

Một người bị xóa khỏi group Finance nhưng phiên VPN đang mở vẫn tới Finance Portal. Bạn cần kiểm tra gì?

**Gợi ý:** token/session cache, group sync, mapping, reauthentication/reauthorization, quyền ứng dụng và chính sách thu hồi.

### Câu hỏi 6

MFA có thay thế phân quyền VPN theo nhóm được không?

**Gợi ý:** không. MFA tăng độ tin cậy danh tính, không định nghĩa người đó được vào dịch vụ nào.

### Câu hỏi 7

Vì sao source IP sau NAT không đủ để biết chính xác user đã truy cập một tài nguyên?

**Gợi ý:** nhiều user có thể cùng IP, IP pool được cấp lại; cần session ID và mapping theo thời gian.

### Câu hỏi 8

Nếu có split tunneling, những traffic nào SOC có thể không quan sát được ở VPN gateway?

**Gợi ý:** traffic đi trực tiếp ra mạng hiện tại không qua tunnel; không nên suy điều đó đã được gateway kiểm tra.

### Câu hỏi 9

Thiết kế test nào giúp xác định VPN group thực sự giới hạn quyền tới Database zone?

**Gợi ý:** negative test ở lab, xác minh deny log tại điểm thực thi và bảo đảm dịch vụ đích đang hoạt động.

### Câu hỏi 10

Tại sao nên đưa IT Admin qua bastion/PAM thay vì mở SSH/RDP toàn mạng?

**Gợi ý:** giảm phạm vi kết nối trực tiếp, giới hạn đích và thời gian, ghi nhật ký quyền đặc biệt.

### Bài tập thiết kế

Doanh nghiệp có **Employee, Developer, Finance, IT Admin, Contractor và SOC**; tài nguyên gồm **Intranet, Git, Finance Portal, Bastion, Security Dashboard và Database**. VPN phục vụ nhân sự làm việc từ xa, kết nối các vùng mạng qua firewall. Hãy:

1. Lập ma trận **nhóm → ứng dụng → giao thức/cổng**; mặc định từ chối những kết nối không có trong ma trận.
2. Vẽ sơ đồ từ **IdP → VPN gateway → policy/firewall → tài nguyên** và đánh dấu nơi thực thi quyền.
3. Nêu cách xử lý một tài khoản thuộc hai nhóm và một tài khoản có group claim không hợp lệ.
4. Thiết kế chính sách MFA, managed device và JIT/PAM cho Finance và IT Admin.
5. Viết ít nhất **sáu phép kiểm thử**, gồm kết nối hợp lệ, truy cập bị deny, thay đổi group trong phiên, client không đạt posture, IPv6 và cloud route.
6. Thiết kế log correlation theo user ID, session ID, tunnel IP, policy version và application outcome.
7. Đề xuất SLA thu hồi cho người chuyển nhóm, nghỉ việc và hợp đồng nhà thầu hết hạn.
8. Nêu những phần VPN không giải quyết thay application authorization, firewall segmentation, DNS protection và IDS/IPS.

**Tiêu chí đạt:** mọi quyền có người sở hữu, được cấp theo nhu cầu có thể giải thích, được thực thi tại điểm kiểm soát và được xác minh bằng cả **allow test** lẫn **deny test**.

## 21. Những điều cần ghi nhớ

- **Phân quyền VPN theo nhóm tách authentication khỏi authorization**: được phép kết nối tunnel không đồng nghĩa có quyền truy cập mọi tài nguyên.
- **RBAC/ABAC, least privilege và deny by default** giúp mỗi nhóm chỉ vào đúng dịch vụ, cổng và điều kiện cần thiết.
- **Group và role phải xuất phát từ IdP/AAA đã được xác minh**; cách xử lý group lồng nhau, chồng lấn hoặc thiếu claim phải được định nghĩa rõ.
- **Quyền phải được thực thi thật tại VPN gateway, firewall, microsegmentation hoặc ứng dụng**, không chỉ bằng route push hay source IP.
- **MFA, posture, chứng thư và JIT/PAM bổ sung bảo mật**, nhất là với Finance, IT Admin và các tài khoản bên ngoài.
- **Gỡ khỏi nhóm chưa chắc thu hồi ngay quyền của phiên VPN đang mở**: cần quản lý session/token cache, reauthorization và thời gian thu hồi.
- **Split tunnel, IPv6, DNS, NAT, cloud/VPN routing** có thể tạo đường đi hoặc điểm quan sát khác dự kiến; phải kiểm thử toàn tuyến.
- **Log phải liên kết đúng danh tính, phiên và chính sách**, đồng thời không ghi bí mật đăng nhập; luôn kiểm tra tác động tại dịch vụ.
- **Phòng vệ nhiều lớp vẫn cần thiết:** VPN nhóm không thay thế phân quyền ứng dụng, bảo vệ dữ liệu, firewall, DNS, IDS/IPS hoặc quy trình quản trị tài khoản.
