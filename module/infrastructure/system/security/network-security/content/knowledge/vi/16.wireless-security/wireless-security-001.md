# Wi-Fi security boundary: xác định và bảo vệ ranh giới tin cậy của mạng không dây

Một văn phòng có ba mạng Wi-Fi: `Company-Staff` cho nhân viên, `Company-Guest` cho khách và `Company-IoT` cho thiết bị điều khiển. Cả ba SSID có thể được phát từ cùng một access point (AP) và sử dụng chung cáp uplink. Vậy thiết bị khách có thể truy cập máy chủ nội bộ không? Không thể trả lời chỉ bằng tên SSID, mật khẩu Wi-Fi hay số VLAN: cần xem **thiết bị được xác thực thế nào, được ánh xạ vào security zone nào, lưu lượng đi qua thiết bị nào và rule nào thực sự chặn đường không được phép**.

**Wi-Fi security boundary** là tập hợp các ranh giới tin cậy và điểm thực thi chính sách trải dài từ môi trường sóng vô tuyến, quá trình tham gia mạng 802.11, xác thực người dùng/thiết bị, cấp địa chỉ và định tuyến, tới dịch vụ nội bộ và control plane. Chủ đề thuộc chương **Wireless security** của module **SECURITY_NETWORK_SECURITY**, liên hệ trực tiếp với phân đoạn mạng, firewall, VPN/ZTNA, NAC, IDS/IPS, DHCP/DNS, bảo mật cloud và mô hình hóa mối đe dọa.

**Thông điệp chính:** phạm vi phát sóng không trùng với phạm vi tin cậy; **SSID không phải security boundary hoàn chỉnh**, còn mã hóa Wi-Fi chỉ bảo vệ một phần đường truyền. Cần nhiều lớp độc lập từ access layer tới ứng dụng và dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Phân biệt **radio coverage, SSID, BSSID, association, authentication, authorization, VLAN/VRF, IP routing** và quyền truy cập ứng dụng.
2. Vẽ sơ đồ trust boundary từ thiết bị Wi-Fi qua AP/controller, RADIUS/NAC, DHCP/DNS, firewall tới server.
3. Lựa chọn mô hình bảo vệ phù hợp cho **employee, guest, BYOD, IoT và management**; không coi một PSK chung là định danh thiết bị.
4. Diễn giải đúng vai trò của **WPA2, WPA3, 802.1X/EAP-TLS, PMF, OWE, captive portal** và các giới hạn tương ứng.
5. Thiết kế và kiểm thử các rule **cho phép đúng nhu cầu, từ chối mặc định truy cập chéo vùng**, kể cả IPv6.
6. Nhận biết rủi ro **rogue AP, evil twin, cấu hình sai chứng chỉ, giả mạo địa chỉ, tấn công làm gián đoạn sóng và sai mapping VLAN**.
7. Đọc telemetry để phân biệt lỗi RF, xác thực, DHCP, DNS, routing, firewall và ứng dụng; triển khai thay đổi có rollback.

## 2. “Boundary” của Wi-Fi thực chất nằm ở đâu?

Sóng Wi-Fi truyền trong không gian và có thể được thu bên ngoài ranh giới vật lý của tòa nhà. Tường, cửa và vùng phủ sóng **không đủ làm chính sách cấp quyền**. Cần phân biệt nhiều lớp:

| Ranh giới | Câu hỏi phải trả lời | Kiểm soát tiêu biểu | Không được suy ra |
|---|---|---|---|
| **Không gian vô tuyến (RF)** | Ai có thể phát/thu tín hiệu trong vùng sóng? | Quy hoạch công suất, kênh, kiểm tra hiện trường, phát hiện AP lạ | Người đứng ngoài tòa nhà không thể nghe thấy beacon |
| **802.11 association** | Station (STA) đang liên kết với BSSID/AP nào? | Chính sách SSID/BSSID, association management, PMF khi thích hợp | Đã kết nối nghĩa là danh tính đã được xác thực mạnh |
| **Link security** | Dữ liệu trên liên kết vô tuyến được mã hóa/xác thực bằng cơ chế nào? | WPA2/WPA3, CCMP/GCMP theo chế độ, khóa phiên | Dữ liệu được mã hóa end-to-end tới ứng dụng |
| **Network access / NAC** | Người dùng/thiết bị nào được vào mạng với vai trò gì? | 802.1X/EAP, RADIUS, chứng chỉ, chính sách posture khi có | Cùng SSID luôn cùng quyền |
| **L2/L3 segmentation** | Thiết bị vào VLAN/VRF/subnet nào; qua gateway nào? | VLAN, VRF, ACL, DHCP snooping, firewall | Chỉ khác VLAN là đã chặn mọi đường chéo |
| **Egress / DNS / service access** | Client truy cập resolver, Internet, ứng dụng nào? | Gateway firewall, DNS policy, proxy, quota, WAF | DNS trả tên nội bộ nghĩa là đã được truy cập nội bộ |
| **Ứng dụng và dữ liệu** | Chủ thể có được đọc/sửa tài nguyên cụ thể không? | MFA, mTLS, AuthN/AuthZ, kiểm tra tenant/object | Đã xác thực vào Wi-Fi nghĩa là được cấp quyền ứng dụng |
| **Control/management plane** | Ai được cấu hình AP, controller, RADIUS, switch? | RBAC, MFA, admin network, audit, backup | Management plane được bảo vệ chỉ vì SSID có mật khẩu |

Một mạng có thể bảo vệ lớp RF và association rất tốt nhưng vẫn sai **firewall rule guest → server**. Ngược lại, một mạng khách dùng mã hóa đường truyền hạn chế vẫn có thể được cô lập chặt ở L3/L4 và ứng dụng, nhưng phải xét rủi ro người dùng trước khi chọn công nghệ.

### 2.1. Thuật ngữ quan trọng

- **STA (station):** thiết bị tham gia mạng không dây; thường là laptop, điện thoại, cảm biến.
- **AP (access point):** thiết bị cung cấp kết nối 802.11, có thể chuyển traffic về switch hoặc controller.
- **SSID:** tên mạng logic mà người dùng thường thấy khi chọn Wi-Fi; có thể được nhiều AP quảng bá.
- **BSSID:** định danh BSS ở lớp 802.11, thường biểu diễn bằng địa chỉ MAC liên quan tới AP/radio; không phải chứng cứ nguồn đáng tin tuyệt đối.
- **ESS:** một tập các BSS/AP vận hành cùng mạng logic để hỗ trợ vùng phủ và roaming.
- **Supplicant:** thành phần client tham gia 802.1X/EAP.
- **Authenticator:** thành phần kiểm soát truy cập ở cổng mạng, thường là AP hoặc hệ thống WLAN.
- **AAA/RADIUS:** hạ tầng xác thực, ủy quyền và ghi nhận hoạt động theo kiến trúc; có thể trả policy role/VLAN nếu được hỗ trợ.
- **Data plane:** đường chuyển traffic của client; **control plane:** đường quản lý, cấu hình, đăng nhập và điều phối AP/controller.

SSID có thể giống tên trên một AP giả; địa chỉ MAC/BSSID cũng có khả năng bị giả mạo. Vì vậy **nhìn tên mạng hoặc BSSID không chứng minh đang nói chuyện với hạ tầng của doanh nghiệp**.

## 3. Vẽ đường đi của Wi-Fi qua các trust boundary

Giả sử doanh nghiệp có AP quản lý tập trung, switch access và firewall phân đoạn:

~~~mermaid
flowchart TB
    subgraph RF["TB1: Vùng sóng - môi trường không tin cậy"]
      EMP["Laptop nhân viên"]
      GUEST["Điện thoại khách"]
      IOT["Cảm biến IoT"]
    end
    subgraph ACCESS["TB2: Access layer"]
      AP["AP / SSID và chính sách WLAN"]
      SW["Switch / trunk VLAN và gateway"]
    end
    subgraph CTRL["TB3: Authentication & control"]
      AAA["RADIUS / NAC / Identity"]
      WLC["Controller / AP management"]
    end
    subgraph ROUTE["TB4: Phân đoạn và đường mạng"]
      FW["Firewall / VRF / policy"]
      DNS["DHCP, DNS và hạ tầng nền"]
    end
    subgraph SERVICES["TB5: Dịch vụ và dữ liệu"]
      API["Business API / AuthZ"]
      DB[("Database / tài nguyên nhạy cảm")]
      WEB["Internet / Public WAF"]
    end
    EMP --> AP
    GUEST --> AP
    IOT --> AP
    AP --> SW
    AP -.->|"EAP/RADIUS khi dùng"| AAA
    AP -.->|"Management / provisioning"| WLC
    SW --> FW
    FW --> DNS
    FW --> API
    FW --> WEB
    API --> DB
~~~

Sơ đồ **khái niệm**, không phải khẳng định mọi sản phẩm đều chuyển client traffic qua switch theo đúng đường này. Với **centralized tunneling**, traffic có thể đi trong tunnel từ AP tới controller/gateway; với **local switching**, AP đưa traffic vào VLAN tại switch/site. Vị trí chặn guest → server phải đặt theo **đường data plane thực tế**, không chỉ theo đường management của AP.

### 3.1. Những ranh giới không được trộn lẫn

1. **STA → AP:** quyết định thiết bị tham gia mạng không dây và cơ chế bảo vệ liên kết.
2. **AP/authenticator → AAA:** quyết định danh tính hoặc chính sách mạng theo dữ liệu xác thực và quyền đã cấp.
3. **SSID/role → VLAN/VRF:** ánh xạ traffic vào miền mạng; phải bảo đảm không bị lệch khi roam hoặc AP lỗi.
4. **Zone → zone:** firewall/ACL quyết định kết nối được phép theo nguồn, đích, dịch vụ và ngữ cảnh.
5. **Client → ứng dụng:** ứng dụng xác thực và kiểm tra quyền tài nguyên dù kết nối đến từ Wi-Fi nhân viên.
6. **Operator → AP/controller:** quyền quản trị khác hoàn toàn quyền dùng Wi-Fi bình thường.

## 4. Các cơ chế bảo vệ Wi-Fi cần hiểu đúng

### 4.1. WPA2/WPA3, Personal và Enterprise

| Cơ chế | Danh tính/khóa thường gặp | Điểm mạnh | Giới hạn và lưu ý |
|---|---|---|---|
| **Open Wi-Fi** | Không có bảo vệ mã hóa liên kết theo chế độ open thông thường | Kết nối rộng rãi | Không có tính bí mật của link Wi-Fi; cần TLS và biện pháp bổ sung |
| **Enhanced Open (OWE)** | Thương lượng mã hóa link không dựa trên shared password | Giúp chống nghe lén thụ động trên liên kết trong một số kịch bản open | **Không xác thực hạ tầng như mạng doanh nghiệp**; không thay TLS/identity |
| **WPA2-Personal (PSK)** | Mật khẩu dùng chung cho một SSID/nhóm | Triển khai đơn giản với thiết bị tương thích | Shared secret khó thu hồi riêng từng thiết bị; phụ thuộc chất lượng mật khẩu và chính sách |
| **WPA3-Personal (SAE)** | Cơ chế SAE dùng mật khẩu để xác thực và thiết lập khóa | Tăng khả năng bảo vệ so với nhiều điểm yếu của PSK truyền thống | Vẫn cần bảo vệ mật khẩu, bảo vệ AP/controller, xác minh tương thích client |
| **WPA2-Enterprise** | 802.1X/EAP với backend AAA, thường qua RADIUS | Có thể xác thực theo user/thiết bị, kiểm soát quyền và thu hồi | Cần kiểm tra chứng chỉ server, EAP method, cấp quyền đúng |
| **WPA3-Enterprise** | Cơ chế Enterprise với yêu cầu bảo mật phù hợp chế độ triển khai | Hỗ trợ môi trường quản lý danh tính và chính sách mạnh | Yêu cầu về chứng chỉ/client/PMF và các chế độ Enterprise phụ thuộc tiêu chuẩn, sản phẩm |

Không nên coi “WPA3” là lời bảo đảm rằng không thể có rogue AP, lỗ hổng ứng dụng hay traffic từ tài khoản hợp lệ bị lạm dụng. **Phiên bản, chế độ tương thích, cấu hình client, firmware và nơi enforce policy** quan trọng không kém tên cơ chế.

Đối với mạng doanh nghiệp có hạ tầng quản lý endpoint, **802.1X với EAP-TLS và xác minh chứng chỉ đúng** thường là lựa chọn tốt cho nhân viên/thiết bị được quản lý. Trong mạng IoT có thiết bị không hỗ trợ 802.1X, có thể dùng cơ chế credential riêng cho từng thiết bị khi nền tảng hỗ trợ, đồng thời giữ IoT trong vùng quyền tối thiểu.

### 4.2. PMF (Protected Management Frames)

**PMF**, gắn với 802.11w trong các tài liệu triển khai, bảo vệ một số **robust management frames** sau khi liên kết và thiết lập cơ chế bảo vệ phù hợp. Nó giúp giảm rủi ro giả mạo một số thông điệp quản lý như deauthentication/disassociation trong phạm vi được bảo vệ.

PMF **không**:

- Mã hóa mọi beacon hoặc mọi frame trước association.
- Ngăn thiết bị phát sóng gây nhiễu/jamming ở tầng RF.
- Thay xác thực server RADIUS hoặc phân quyền ứng dụng.
- Bảo đảm người dùng không kết nối nhầm AP giả trong mọi chế độ.

Các profile WPA3 thường yêu cầu PMF; với hỗ trợ pha trộn/transition và thiết bị cũ, cần kiểm tra yêu cầu thực tế của từng SSID và client. **Không nói “đã bật WPA3 nên không thể bị ngắt kết nối”**.

### 4.3. WEP, TKIP, WPS và SSID ẩn

- **WEP/TKIP** là những cơ chế cũ, không phù hợp làm bảo vệ mặc định cho mạng mới; tránh dùng trừ trường hợp cô lập di sản có kiểm soát và kế hoạch thay thế rõ.
- **WPS** có thể mở thêm phương thức đăng ký thiết bị; nếu không cần, nên tắt hoặc hạn chế theo khả năng thiết bị và policy.
- **Ẩn SSID** không cung cấp ranh giới bảo mật mạnh. Client vẫn cần cơ chế tìm/trao đổi thông tin để liên kết; không dùng hidden SSID thay cho xác thực hoặc phân đoạn.
- **MAC allowlist** có ích cho kiểm kê ở một số ngữ cảnh nhưng không phải authentication mạnh. MAC có thể ngẫu nhiên hóa/giả mạo; client có thể thay đổi địa chỉ theo chính sách riêng tư.

### 4.4. Captive portal là lớp nào?

Captive portal thường chặn/chuyển hướng một phần truy cập ứng dụng để yêu cầu đồng ý điều khoản, đăng nhập hoặc nhập voucher. Nó có thể dùng với guest Wi-Fi, nhưng:

1. Portal **không tự mã hóa** những frame của một mạng Wi-Fi open.
2. Một trang đăng nhập đẹp **không chứng minh AP là hợp lệ**.
3. Portal có thể áp policy sau khi thiết bị đã nhận IP; giai đoạn trước đăng nhập vẫn cần giới hạn quyền.
4. Một số client, ứng dụng, VPN và cơ chế HTTPS/HSTS có hành vi đặc biệt khi gặp redirect; cần kiểm thử khả năng tương thích.
5. Portal là kiểm soát truy cập theo ứng dụng/kịch bản, không thay firewall, isolation và bảo vệ danh tính.

## 5. 802.1X/EAP: từ xác thực đến quyền ở wireless edge

Trong mạng Enterprise, AP hoặc WLAN infrastructure thường đóng vai **authenticator**, chuyển trao đổi EAP giữa client (supplicant) và backend AAA; máy chủ AAA thực hiện kiểm tra theo chính sách.

~~~mermaid
sequenceDiagram
    participant STA as Supplicant (laptop)
    participant AP as AP / Authenticator
    participant R as RADIUS / EAP server
    participant GW as L3 gateway / firewall
    STA->>AP: Association với SSID Enterprise
    AP->>STA: Yêu cầu bắt đầu EAP/802.1X
    STA->>AP: Trao đổi EAP theo phương thức cấu hình
    AP->>R: Đóng gói EAP trong RADIUS theo luồng AAA
    R-->>AP: EAP server response chứa chứng chỉ khi phương thức áp dụng
    AP-->>STA: Chuyển EAP server response cho supplicant
    Note over STA: Client xác minh CA, danh tính server, policy chứng chỉ
    STA->>AP: Chứng minh credential/chứng chỉ theo EAP method
    AP->>R: Chuyển dữ liệu xác thực phù hợp
    R-->>AP: Kết quả auth + attributes được cấp khi thành công
    AP-->>STA: Hoàn tất bảo vệ link / cấp quyền theo role
    STA->>GW: DHCP/IP traffic trong miền đã được cấp
~~~

Sơ đồ rút gọn để biểu diễn **ranh giới tin cậy**; số lượng và thứ tự thông điệp EAP thực tế tùy phương thức và nền tảng, và không nên dùng nó thay packet trace chính thức. Khóa phiên và 4-way handshake chỉ được diễn giải ở mức logic trong bài, không phải hướng dẫn tự triển khai giao thức mã hóa.

### 5.1. EAP-TLS và xác thực hai phía

Với **EAP-TLS**, client và server có thể sử dụng chứng chỉ số để xác thực theo thiết kế PKI. Để mô hình này thực sự có giá trị:

- Client phải **xác minh chứng chỉ của authentication server**, chuỗi CA đáng tin và danh tính/tên máy chủ mong đợi; không được nhấn “Accept any certificate”.
- Chứng chỉ client cần cơ chế cấp phát theo thiết bị/người dùng, rotation, thu hồi và quản lý khi thiết bị bị mất.
- Authentication server cần kiểm tra tính hợp lệ của chứng chỉ và ánh xạ đúng sang danh tính/role được phê duyệt.
- Hệ thống phải xử lý đúng ngày giờ, expiration, lỗi trust chain và các điều kiện xác thực thất bại.
- Quyền truy cập vẫn cần **authorization**: chứng chỉ hợp lệ cho nhà thầu không tự biến người đó thành administrator.

**EAP method khác nhau có tính chất bảo mật khác nhau**. Nếu dùng phương thức dựa trên mật khẩu, cần kiểm tra cấu hình outer tunnel/server validation và chính sách credential; không coi mọi chế độ “802.1X Enterprise” là tương đương EAP-TLS.

### 5.2. Sau RADIUS Access-Accept thì điều gì xảy ra?

Một AAA response thành công có thể chứa thuộc tính cho role, VLAN, ACL hoặc chính sách khác **nếu AP/controller/switch hỗ trợ và được cấu hình đúng**. Sau đó thiết bị chuyển vào data plane đã được cấp, nhận IP từ phạm vi DHCP tương ứng.

~~~text
Managed employee laptop
  -> WLAN: Company-Staff
  -> EAP-TLS validation PASS
  -> RADIUS assigns role "employee-managed"
  -> AP/controller maps to employee VLAN/zone
  -> DHCP: 10.60.10.0/24
  -> Firewall: allow approved business apps, deny admin zone
  -> Application: session + object-level authorization
~~~

Ví dụ trên là **mẫu logic**, không phải cú pháp RADIUS policy. Nếu mapping sai và laptop được đẩy sang VLAN quản trị, lỗi nằm ở **authorization/policy enforcement**, không phải vì “Wi-Fi đã bị giải mã”.

### 5.3. Trạng thái không xác thực và fail mode

Phải thiết kế rõ trường hợp AAA/RADIUS hoặc mạng tới AAA không khả dụng:

- Có cho phép thiết bị mới vào mạng không?
- Những phiên đã xác thực đang hoạt động được xử lý thế nào?
- Có dùng VLAN cách ly/restricted role không; có đủ DHCP/DNS để hiển thị hướng dẫn sửa lỗi không?
- Nếu cho phép cache hay chế độ dự phòng, phạm vi và thời hạn tin cậy là gì?
- Khi AAA trở lại, client và policy có được cập nhật đúng không?

Chọn **fail-open** bừa bãi cho SSID đặc quyền có thể làm nhiều thiết bị không xác thực vào zone nhạy cảm. Nhưng **fail-closed** toàn bộ cũng có thể ảnh hưởng dịch vụ quan trọng. Quyết định cần theo threat model, quy định vận hành và kiểm thử tình huống lỗi.

## 6. Thiết kế SSID-to-zone: mô hình doanh nghiệp mẫu

Giả sử tổ chức quản lý khối IPv4 nội bộ `10.60.0.0/16` và muốn tách:

| SSID/loại client | Xác thực gợi ý | Zone/VLAN mẫu | Prefix mẫu | Quyền tối thiểu |
|---|---|---|---|---|
| `Company-Staff` | WPA2/WPA3-Enterprise, EAP-TLS khi hỗ trợ | Employee / VLAN 110 | `10.60.10.0/24` | Business apps, DNS, egress theo policy |
| `Company-Guest` | OWE hoặc guest onboarding/captive portal theo yêu cầu | Guest / VLAN 120 | `10.60.20.0/23` | Internet được phép, không vào server/management |
| `Company-IoT` | 802.1X nếu có; credential riêng hoặc PPSK khi được hỗ trợ | IoT / VLAN 130 | `10.60.30.0/24` | Chỉ collector/endpoint cần thiết |
| Quản trị AP/controller | Admin identity/MFA, quản trị bằng đường riêng | Management / VLAN 150 | `10.60.50.0/26` | Chỉ control plane được phê duyệt |
| Thiết bị chưa đạt posture hoặc auth thất bại | Restricted policy khi có hỗ trợ | Quarantine / VLAN 160 | `10.60.60.0/26` | Chỉ remediation, DNS/IdP cần thiết |

Đây là **bảng thiết kế minh họa**, không phải cấu hình bắt buộc. Bảng có thể được điều chỉnh khi cùng SSID dùng dynamic VLAN/role từ RADIUS hoặc khi nhiều site dùng nhiều subnet cho một zone. Nguồn địa chỉ được bảo vệ bởi DHCP relay/scope/IPAM; firewall phải thực thi policy độc lập với việc client nhận được IP.

### 6.1. SSID không phải security boundary hoàn chỉnh

Nếu hai SSID được bridge vào cùng VLAN, client có thể ở chung miền L2 dù hiển thị hai tên mạng. Ngược lại, **một SSID** có thể đưa client vào nhiều role/VLAN nhờ AAA/RADIUS và WLAN policy.

Đặt câu hỏi về **data plane sau association**:

1. Client được ánh xạ vào VLAN/VRF nào và ở interface nào?
2. DHCP scope nào cấp IP và gateway nào xử lý L3?
3. Lưu lượng east–west trong cùng VLAN có qua firewall không?
4. AP có **client isolation** không? Điều đó áp cùng AP, cùng SSID, cùng VLAN hoặc toàn bộ fabric trong phạm vi nào?
5. Với central tunneling, traffic bị kiểm tra ở controller/gateway hay ở switch access?
6. IPv6 có cùng vùng và chính sách thực thi như IPv4 không?

### 6.2. Client isolation có tác dụng nhưng có giới hạn

**Wireless client isolation / peer-to-peer blocking** có thể ngăn hoặc giảm liên lạc trực tiếp giữa những STA qua AP trong phạm vi mà sản phẩm hỗ trợ. Điều này hữu ích cho guest, nhưng **không mặc định ngăn**:

- Một client Wi-Fi kết nối với thiết bị có dây trong cùng VLAN.
- Traffic được route qua gateway đến IP của một client khác.
- Giao tiếp giữa client gắn trên AP khác nếu policy chỉ áp cục bộ.
- Tấn công tại gateway, DNS hoặc ứng dụng được phép truy cập.
- Tất cả các kiểu broadcast/multicast/IPv6 ND trên mọi sản phẩm.

Vì vậy hãy kiểm thử **peer isolation, L2 ACL, inter-VLAN firewall** trên toàn bộ hệ thống, không chỉ đánh dấu checkbox trên controller rồi kết luận toàn diện.

## 7. Policy mạng sau khi client được cấp quyền

Một ma trận tối thiểu:

| Nguồn → đích | Dịch vụ/mục đích | Quy tắc logic |
|---|---|---|
| Employee → internal DNS/IdP | Tên nội bộ và xác thực | ALLOW hẹp theo resolver/endpoint được quản lý |
| Employee → business API | Công việc đã phê duyệt | ALLOW theo đích/service, ứng dụng tiếp tục AuthZ |
| Employee → management plane | Quản trị thiết bị mạng | DENY mặc định; chỉ role admin qua bastion/ZTNA |
| Guest → Internet | Web/DNS theo policy | ALLOW egress có kiểm soát, logging phù hợp |
| Guest → Employee/IoT/Server/Management | Không có nhu cầu | DENY, bao gồm IPv4/IPv6 và đường định tuyến khác |
| IoT → telemetry collector | Gửi trạng thái/điều khiển hợp lệ | ALLOW theo nguồn/đích/port và identity khi có |
| IoT → workstation/management | Không có nhu cầu | DENY mặc định |
| Quarantine → remediation/IdP | Cập nhật hoặc đăng ký thiết bị | ALLOW các luồng tối thiểu, thời hạn/owner rõ |
| Admin/ZTNA → AP/controller | Quản trị có kiểm soát | ALLOW đúng jump host, MFA, audit; DENY từ guest |

**Phân biệt được IP không có nghĩa được cấp quyền.** Một người lạ tự đặt IP trùng employee subnet có thể làm phát sinh xung đột hoặc traffic giả mạo; cần thiết kế switchport/VLAN, anti-spoofing, NAC, DHCP snooping, ACL và firewall để không tin duy nhất địa chỉ nguồn.

### 7.1. DHCP, DNS và default gateway nằm trong ranh giới nào?

Client Guest có thể nhận `10.60.20.55/23`, gateway `10.60.20.1`, DNS do doanh nghiệp chỉ định. Điều đó không được dùng để mở quyền tới DNS management nội bộ hoặc các vùng dữ liệu.

- **DHCP:** bảo vệ đường relay, switch trusted ports, scope mapping và rogue DHCP; DHCP option gateway/DNS sai có thể đưa client vào đường ngoài ý định.
- **DNS:** kiểm soát resolver được phép, split-horizon DNS và quyền truy cập private record; DNS answer không tự cấp quyền network.
- **IPv6:** RA/SLAAC có thể cấp địa chỉ không qua DHCPv4, cần IPv6 firewall, RA Guard khi phù hợp, chặn route bypass.
- **mDNS/SSDP/multicast:** discovery trong Wi-Fi (máy in, Chromecast, IoT) có thể cần service gateway được phép. Việc mở multicast rộng giữa zone để tiện sử dụng có thể tăng bề mặt lộ dịch vụ.

### 7.2. Wi-Fi guest phải cách ly cả hai chiều

Không chỉ thử “guest không ping được server”. Cần kiểm tra:

- Guest không thể thiết lập TCP/UDP tới ứng dụng nội bộ ngoài danh sách cho phép, cả IPv4/IPv6.
- Server/Employee không tùy ý khởi tạo phiên tới guest nếu policy không cho phép.
- Lưu lượng guest Internet không bất ngờ đi qua tunnel VPN doanh nghiệp hoặc proxy nội bộ thiếu cách ly.
- DNS, captive portal, authentication và các ngoại lệ cần thiết không tạo đường truy cập rộng tới management plane.
- Client guest không thể truy cập **AP/controller management IP** hay sửa cấu hình DHCP/DNS.

ICMP echo có thể bị chặn riêng nên **ping thất bại không chứng minh mọi TCP/UDP đều bị deny**. Kiểm tra đúng dịch vụ và cổng theo danh sách được phê duyệt, dựa trên firewall logs và kết quả kết nối.

## 8. Các loại client và giới hạn của một chính sách chung

### 8.1. Nhân viên và thiết bị được quản lý

Mạng nhân viên nên có cách gắn danh tính người dùng hoặc thiết bị vào phiên truy cập. Với EAP-TLS, PKI/MDM có thể hỗ trợ cấp chứng chỉ, profile Wi-Fi và kiểm tra server certificate trên endpoint được quản lý.

Khuyến nghị:

- Không cho client tự lựa chọn chế độ **không kiểm tra chứng chỉ RADIUS** chỉ để dễ kết nối.
- Tách quyền employee thường khỏi quyền quản trị; không dùng một SSID “staff” như quyền admin toàn hệ thống.
- Dùng device compliance/posture có kiểm chứng khi chính sách yêu cầu, nhưng không coi một lần kiểm tra là quyền vĩnh viễn.
- Giới hạn kết nối nội bộ theo ứng dụng và danh tính; lưu audit phù hợp.

### 8.2. BYOD và nhà thầu

Thiết bị cá nhân/nhà thầu có thể không đủ điều kiện cài chứng chỉ thiết bị doanh nghiệp hoặc MDM. Có thể cấp **onboarding riêng**, credential có thời hạn, portal xác thực hoặc VPN/ZTNA vào ứng dụng cụ thể. Không gộp mặc định với nhân viên được quản lý chỉ vì họ biết mật khẩu Wi-Fi chung.

Phải xác định: người dùng được sử dụng **dịch vụ nào, trong bao lâu, trên thiết bị nào**, và thu hồi quyền khi hợp đồng hết hạn. Tránh thu thập quá mức thông tin cá nhân từ thiết bị BYOD.

### 8.3. IoT/thiết bị cũ

Một số IoT không hỗ trợ EAP-TLS/WPA3, buộc dùng WPA2-Personal hoặc cơ chế credential khác. Cách giảm rủi ro:

1. Chỉ đưa IoT vào **zone riêng với default-deny east–west**.
2. Ưu tiên credential riêng thiết bị hoặc nhóm nhỏ nếu AP/controller hỗ trợ **PPSK/DPSK/MPSK**; tính năng và cách mapping theo vendor.
3. Giới hạn thiết bị chỉ tới collector, broker, DNS/NTP và endpoint cập nhật được phép.
4. Kiểm kê firmware, chủ sở hữu, thời điểm thay, MAC randomization/chính sách thiết bị, khả năng thu hồi.
5. Không để việc thiếu hỗ trợ WPA3 trở thành lý do tắt bảo vệ cho toàn bộ mạng nhân viên.
6. Có kế hoạch thay thiết bị không còn nhận cập nhật bảo mật.

**Private/individual PSK** giúp thu hồi và phân loại dễ hơn PSK chung, nhưng bản thân secret vẫn có thể bị lộ/được chuyển giao; không thay danh tính thiết bị ở ứng dụng hay firewall.

### 8.4. Guest và captive portal

Guest thường không cần truy cập LAN doanh nghiệp. Cấu hình nên ưu tiên Internet egress được phép, client isolation có kiểm chứng, hạn chế phát hiện tên dịch vụ nội bộ, bảo vệ portal và dữ liệu cá nhân. Captive portal có thể có voucher/điều khoản, nhưng **WPA/OWE và HTTPS** vẫn cần được đánh giá độc lập.

Với môi trường khách đông người (hội nghị, trường học, sân bay), lưu ý NAT đông, rate limit theo IP có thể chặn nhiều người hợp lệ và DHCP pool/IPv6 phải đủ tải.

## 9. Wireless security boundary có liên quan gì tới radio/roaming?

### 9.1. Ranh giới vật lý luôn không hoàn hảo

Tín hiệu Wi-Fi có thể lọt ra ngoài cửa, tường hoặc khuôn viên. Hạn chế công suất/hướng anten, quy hoạch AP và đo vùng phủ có thể giảm phơi bày không cần thiết nhưng **không bảo đảm giới hạn RF trùng hàng rào vật lý**.

Đừng giảm công suất quá mức chỉ để “an toàn”: client có thể tăng retry/roaming, hạ chất lượng dịch vụ hoặc gắn vào AP lạ mạnh hơn. Tối ưu sóng phải đồng thời cân bằng coverage, capacity, interference và security.

### 9.2. Roaming giữa nhiều AP

Client di chuyển từ BSSID này sang BSSID khác trong cùng ESS. Các tính năng liên quan roaming (ví dụ các cơ chế 802.11k/v/r khi được hỗ trợ) có thể giúp tìm AP phù hợp hoặc giảm chi phí tái xác thực.

Nhưng roaming tạo ra các kiểm tra về boundary:

- AP mới có áp **cùng identity/role/VLAN policy** với AP cũ không?
- Session/authentication state được chuyển hoặc tái xác thực đúng không?
- Có trường hợp roaming **giữa site/VLAN** dẫn tới đổi IP, DHCP hoặc route không?
- Khi mất AAA, client đang roam bị fail-open vào role đặc quyền hay fail-closed theo thiết kế?
- Chuyển AP có thay đổi đường đi qua controller, firewall và IDS/IPS không?

Không áp một cấu hình fast roaming cho mọi IoT nếu thiết bị không hỗ trợ. Đặc biệt với những client cũ, có thể cần SSID riêng có quyền hạn hẹp thay vì làm giảm chế độ bảo mật chung.

### 9.3. Công suất, nhiễu và DoS tầng RF

Sự cố Wi-Fi có thể đến từ quá nhiều client, nhiễu cùng kênh, thiết bị điện tử, AP cấu hình sai hoặc hành vi gây nhiễu. Không phải mọi đợt mất kết nối đều là tấn công.

Các công cụ phòng vệ có thể giám sát **channel utilization, retry, noise floor, association failures và deauth events**. PMF giúp chống một số loại frame giả mạo nhưng **không chống được jamming RF**. Khi thấy nhiều lần disassociation, cần đối chiếu RF và lý do kết nối, không kết luận chỉ từ một bộ đếm.

## 10. Threat modeling: các đường vượt boundary

| ID | Kịch bản rủi ro | Boundary bị thử thách | Dấu hiệu/nguồn kiểm chứng | Kiểm soát phòng vệ |
|---|---|---|---|---|
| W01 | **Rogue AP** cắm vào cổng LAN doanh nghiệp | Wired access → wireless edge | Inventory AP, switchport/802.1X, WIDS và kiểm tra hiện trường | NAC/port policy, inventory, xử lý thiết bị lạ có phép |
| W02 | **Evil twin** quảng bá SSID giống mạng thật | RF → client trust | Client profile/cert validation, cảnh báo AP mới | EAP server certificate validation, hướng dẫn người dùng |
| W03 | Client chấp nhận RADIUS certificate không hợp lệ | STA → AAA identity | EAP failure/unknown server, cấu hình supplicant | PKI, pinned expected server identity, MDM policy |
| W04 | PSK chung bị chia sẻ ngoài phạm vi | Link access → zone membership | Nhiều thiết bị lạ, credential lifecycle | EAP-TLS/credential riêng, rotation, NAC, segmentation |
| W05 | Guest SSID gắn nhầm employee VLAN | AP/controller → L2/L3 | Lease subnet, role/VLAN logs, firewall path | Config review, dynamic VLAN tests, deny chéo zone |
| W06 | Client isolation chỉ áp trong một AP | Peer-to-peer/L2 | Test client ở hai AP, wired peer trong cùng zone | L2 ACL/fabric enforcement, firewall khi đi L3 |
| W07 | Management plane reachable từ guest | Client → AP/controller | Kết nối TCP/HTTPS tới admin interfaces | Admin VRF, management ACL, MFA, audit |
| W08 | IoT bị chiếm truy cập data zone | IoT → trusted services | Flow logs, DNS anomalies, EDR/IDS | IoT zone, allowlist destination, service auth |
| W09 | IPv6 RA/route ngoài dự kiến tạo bypass | Wi-Fi → L3 security | A/AAAA, RA, routes, IPv6 counters | RA Guard khi phù hợp, IPv6 ACL/firewall |
| W10 | Captive portal bị coi là thay thế WPA | Guest RF → session | Hành vi TLS/captive portal, cấu hình WLAN | OWE/WPA khi phù hợp, HTTPS, hạn chế guest |
| W11 | Deauth/disassoc giả hoặc RF interference | Management frames / availability | Deauth reason, RF utilization, retry | PMF khi hỗ trợ, RF monitoring, điều tra hiện trường |
| W12 | Roam sang AP cấu hình khác role | AP1 → AP2 trust | RADIUS accounting, controller role change | Policy đồng bộ, positive/negative roaming tests |
| W13 | DHCP/DNS giả cấp gateway/resolver sai | L2 access → dịch vụ nền | DHCP offer, DNS resolver, rogue server logs | DHCP snooping, trusted ports, DNS policy |
| W14 | AP firmware/controller credential bị lộ | Control plane → nhiều SSID | Admin audit, firmware alerts, config change | MFA/RBAC, patching, management isolation, backup |
| W15 | Shared proxy/NAT che danh tính client | WLAN → logging/SIEM | Nhiều client chung IP, missing session ID | Correlation AAA/lease/controller với quyền riêng tư |
| W16 | Direct access tới ứng dụng dù DNS/SSID bị ẩn | Network → application/data | Firewall/WAF logs, direct IP route | Segmentation, AuthN/AuthZ, kiểm tra nguồn độc lập |

**Không biến mọi dấu hiệu thành một nhãn “đang bị tấn công”.** Ví dụ AP mới xuất hiện có thể là thiết bị hàng xóm; deauth nhiều có thể do sóng yếu hoặc client firmware; traffic IoT tới DNS có thể do thiết bị lỗi retry. Phân tích context, chủ sở hữu và bằng chứng trước khi phản ứng.

### 10.1. Rogue AP khác evil twin

- **Rogue AP** thường chỉ AP không được tổ chức cho phép nhưng có kết nối/ảnh hưởng tới hạ tầng được bảo vệ; rủi ro cao nếu nó mở một đường không kiểm soát vào mạng có dây.
- **Evil twin** là AP giả mạo hoặc mô phỏng mạng mà client tin là hợp lệ; có thể nhằm lừa người dùng liên kết hoặc nhập thông tin.
- Một AP **không nằm trong inventory** không mặc nhiên là rogue có dây: nó có thể thuộc doanh nghiệp bên cạnh. Cần chứng cứ về **kết nối, vị trí, chủ sở hữu và hành vi**.
- Không phát deauth hoặc tự động tấn công vào AP lân cận để “chống rogue” khi chưa được ủy quyền; cơ chế WIPS chủ động có thể gây gián đoạn và cần đánh giá pháp lý/quy định vô tuyến.

### 10.2. Xử lý sự cố theo trust boundary

~~~mermaid
flowchart TD
    A["Cảnh báo hoặc người dùng báo lỗi"] --> B{"RF hay authentication?"}
    B -->|"RF / association"| R["Kiểm tra AP health, channel, RSSI, retries, PMF events"]
    B -->|"Auth / AAA"| E["Kiểm tra EAP/RADIUS, server cert, role mapping"]
    R --> C["Đối chiếu AP/BSSID, client, thời gian và site"]
    E --> C
    C --> D{"Đã được cấp IP đúng zone?"}
    D -->|"Không"| H["Kiểm tra VLAN, relay, DHCP scope, RA"]
    D -->|"Có"| F["Kiểm tra DNS, firewall, routing, app authorization"]
    H --> G["Khoanh vùng nguyên nhân và thay đổi có phê duyệt"]
    F --> G
    G --> T["Kiểm thử regression + giám sát + rollback nếu cần"]
~~~

## 11. Management plane: boundary dễ bị bỏ sót

Một kẻ có quyền admin trên controller/AP có thể thay SSID, giảm mức mã hóa, chuyển VLAN, tạo tài khoản quản trị, thay RADIUS server hoặc xuất dữ liệu nhạy cảm. Vì vậy bảo mật control plane không kém quan trọng so với WPA.

### 11.1. Nguyên tắc bảo vệ

1. **Đặt AP/controller management vào vùng riêng**, chỉ mở tới hệ thống quản trị/automation đã được phê duyệt.
2. Sử dụng MFA, RBAC/least privilege cho tài khoản quản trị; phân biệt read-only/operations/security admin.
3. Không để giao diện quản trị AP lộ trực tiếp tới guest Wi-Fi hoặc Internet nếu không có giải pháp truy cập được bảo vệ.
4. Quản lý chứng chỉ, thông tin đăng nhập và khóa kết nối AP/controller; xoay vòng, thu hồi khi thiết bị mất.
5. Cập nhật firmware/OS có kiểm soát; kiểm tra tương thích WPA/EAP/PMF với client trước rollout diện rộng.
6. Backup cấu hình WLAN, AAA mapping, VLAN, policy và lưu diff/audit cho mọi thay đổi.
7. Kiểm tra AP/controller vẫn hoạt động theo chính sách khi mất kết nối cloud management.
8. Bảo vệ kênh control/data AP-controller theo thiết kế nhà cung cấp; **không giả định mọi tunnel mặc định đều mã hóa và xác thực toàn bộ traffic**.

### 11.2. Control-plane topology làm thay đổi nơi chặn

| Triển khai | Đường client data có thể đi | Điều phải kiểm tra |
|---|---|---|
| **Local bridging** | AP → switch VLAN/site gateway | Trunk allowed VLAN, ACL tại L2/L3, DHCP relay, local firewall |
| **Central tunneling** | AP → WLAN controller/tunnel gateway → core | Tunnel endpoint, encryption/auth khi áp dụng, role và firewall tại nơi breakout |
| **Cloud-managed AP** | Management qua cloud, client data có thể breakout local hoặc qua tunnel | Tách control plane khỏi client traffic, dependency khi mất cloud |
| **Distributed/fabric WLAN** | Traffic được gắn role và thực thi tại nhiều node | Policy synchronization, roaming/role consistency, traffic bypass |

Không lấy tên “cloud-managed” để suy rằng mọi packet của khách được chuyển tới cloud. Các nền tảng khác nhau có cách truyền data khác nhau; cần xác minh **packet path thực tế** khi vẽ DFD và đặt firewall.

## 12. Quan sát và giám sát ranh giới Wi-Fi

### 12.1. Những dữ liệu hữu ích

| Nguồn | Trường/thước đo | Dùng để phát hiện |
|---|---|---|
| **AP/RF telemetry** | SSID, BSSID, radio, channel, RSSI/SNR, retry, association/deauth count | Vấn đề phủ sóng, nhiễu, một số dạng bất thường RF |
| **802.1X/RADIUS** | Result, EAP method, server identity, policy ID, role/VLAN được cấp, reason code | Xác thực sai, chứng chỉ lỗi, role mapping sai |
| **WLAN controller** | Client session, AP change/roam, role, tunnel state, policy version | Roaming chéo quyền, cấu hình AP không đồng nhất |
| **DHCP/DNS** | IP lease interval, VLAN/VRF, resolver, DNS query errors | Gán nhầm subnet hoặc mất DNS |
| **Firewall/NGFW** | Zone, source/dest, action, rule hit, session state | Chặn/cho phép chéo zone và direct access |
| **IDS/IPS/WIDS/WIPS** | Signature, sensor/PoP, severity, source evidence | Điều tra hành vi mạng/WLAN bất thường, không chỉ số cảnh báo |
| **Application/IdP** | Login success/failure, MFA, 403/429, quyền nghiệp vụ | Lạm dụng sau khi Wi-Fi đã cho phép kết nối |
| **Change/audit logs** | Operator, thời gian, WLAN/VLAN/AAA diff | Tìm cấu hình gây gián đoạn hoặc mở sai quyền |

### 12.2. Privacy và nhận diện client

Wireless telemetry có thể chứa MAC (kể cả MAC ngẫu nhiên), username, chứng chỉ, IP lease, vị trí AP, khoảng thời gian di chuyển hoặc mức tín hiệu. Đây có thể là thông tin nhạy cảm về người dùng. Chỉ thu những gì cần để bảo mật/vận hành, hạn chế truy cập và lưu giữ, đồng bộ đồng hồ và ghi audit khi tra cứu.

**MAC không phải ID người dùng cố định**, nhất là khi client bật private/randomized MAC. Để điều tra, phải ghép bằng chứng một cách có trách nhiệm từ RADIUS session, lease time, AP association và firewall logs; không tuyên bố chính xác danh tính chỉ vì một MAC trong một log.

### 12.3. Chỉ số thành công của chính sách Wi-Fi

Không đánh giá theo “số AP phát hiện được” hoặc “số lần chặn” đơn thuần. Các chỉ số nên gồm:

- Tỷ lệ xác thực thành công cho thiết bị hợp lệ theo SSID và EAP method.
- Tỷ lệ gán role/VLAN đúng, lỗi DHCP/DNS sau authentication.
- Số kết nối guest → management/server bị từ chối theo thiết kế và các trường hợp truy cập hợp lệ thành công.
- Sự kiện rogue/evil twin đã được xác minh, không chỉ tên SSID trùng.
- Roaming success, latency, packet loss, client retry, tác động thay đổi WPA/PMF.
- Cảnh báo admin config drift, firmware thiếu cập nhật, RADIUS/tunnel unavailable.
- False positive từ WIDS/WIPS hoặc NAC khiến người dùng/IoT hợp lệ bị ngắt.

## 13. Thực hành quan sát an toàn và xác minh ranh giới

Chỉ thực hiện trên thiết bị/mạng do bạn quản lý hoặc được cấp quyền. Bài tập tập trung **đọc cấu hình và kiểm thử quyền**, không dùng công cụ tạo AP giả, phát deauthentication hoặc thu thập traffic của người khác.

### 13.1. Lệnh chỉ đọc trên Windows

~~~powershell
# Xem kết nối WLAN hiện tại: SSID, BSSID, radio, tín hiệu...
netsh wlan show interfaces

# Xem interface mạng, IP, gateway và DNS đã được cấu hình.
Get-NetIPConfiguration
Get-DnsClientServerAddress

# Xem tuyến IPv4/IPv6 hiện tại, không đổi hệ thống.
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias
~~~

Lệnh có thể cho biết đang gắn vào SSID/BSSID nào, nhưng **không chứng minh AP hợp lệ hoặc RADIUS certificate đã được xác minh**. Một số thông tin còn phụ thuộc driver và phiên bản Windows. Không dán nguyên log chứa địa chỉ/danh tính nội bộ vào kênh công khai.

### 13.2. Lệnh chỉ đọc trên Linux

~~~bash
# Chỉ liệt kê các interface wireless, nếu hệ thống có tiện ích iw.
iw dev

# Kiểm tra IP và route được sử dụng thực tế.
ip -br address
ip -4 route show
ip -6 route show

# Xem resolver nếu máy dùng systemd-resolved.
resolvectl status
~~~

Không phải hệ thống Linux nào cũng cài `iw` hoặc `resolvectl`. Những lệnh này không chụp packet của người khác và không thay chính sách WLAN. Với laptop doanh nghiệp, vẫn cần dữ liệu **controller/RADIUS logs** mới xác nhận role và VLAN được cấp.

### 13.3. Mẫu biểu mô tả policy (không phải cấu hình sản phẩm)

~~~yaml
# Pseudo-policy để review kiến trúc, không có tác dụng cấu hình AP/firewall.
wirelessNetwork:
  ssid: Company-Guest
  expectedProtection: OWE-or-approved-guest-onboarding
  clientIdentity: guest-session-when-available
  dataPlane:
    zone: guest
    vlan: 120
    ipv4Prefix: 10.60.20.0/23
    ipv6Policy: explicit-guest-only
  access:
    allow:
      - approved-dns
      - approved-internet-egress
    deny:
      - employee-zone
      - iot-zone
      - server-zone
      - management-zone
  peerIsolation:
    required: true
    validation: cross-ap-and-wired-peer-tests
  management:
    adminFromGuest: false
    auditRequired: true
  verification:
    - guest-successfully-reaches-approved-public-service
    - guest-cannot-reach-internal-services
    - ipv6-does-not-bypass-segmentation
    - captive-portal-not-treated-as-link-encryption
~~~

**Đây là đặc tả để thảo luận**; không copy vào bộ điều khiển WLAN hay firewall như file cấu hình chạy được. Kiểm tra cách sản phẩm ánh xạ SSID/VLAN/role, khả năng OWE và client isolation, cũng như đường data thực tế trước khi viết policy có hiệu lực.

### 13.4. Ma trận positive và negative tests

| ID | Điểm kiểm thử | Kỳ vọng | Bằng chứng nên có |
|---|---|---|---|
| P01 | Laptop managed kết nối `Company-Staff` | EAP/cert PASS, đúng employee role và DHCP scope | Supplicant + RADIUS + controller + lease logs |
| N01 | Laptop có RADIUS server certificate không tin cậy | Auth thất bại theo chính sách; không silently accept | Endpoint policy và RADIUS failure reason |
| P02 | Guest kết nối `Company-Guest` | Nhận guest IP/DNS và Internet theo policy | WLAN session, DHCP, firewall egress |
| N02 | Guest thử kết nối server/management qua IPv4 | Bị từ chối theo rule | Firewall log/connection result |
| N03 | Guest thử cùng mục tiêu qua IPv6 | Không tạo đường bypass | RA/IPv6 routes, firewall logs |
| N04 | Hai guest ở AP khác nhau thử liên lạc peer | Bị từ chối theo phạm vi isolation đã chọn | AP policy, kết quả kết nối |
| N05 | Guest truy cập AP/controller admin endpoint | Không được truy cập | Management ACL + audit |
| P03 | IoT được phê duyệt gửi telemetry | Chỉ đến collector/broker hợp lệ | Role, lease, allow rule, application result |
| N06 | IoT thử tới workstation hoặc data zone | Bị từ chối | Inter-zone firewall/ACL logs |
| P04 | Employee roam sang AP khác | Giữ đúng role/segmentation, ứng dụng hoạt động | WLAN roam, RADIUS accounting, data-plane path |
| N07 | Auth server không sẵn sàng trong lab | Hành vi fail mode đúng thiết kế, không mở admin role | Test plan, policy và logs |
| P05 | Admin qua kênh quản trị được phép | MFA/role hoạt động, có audit | IdP, controller audit |
| N08 | User Wi-Fi thường thử quản trị WLAN | Không có quyền đổi SSID/AAA/VLAN | RBAC/admin audit |
| P06 | Thay đổi WPA/PMF ở canary AP | Client tương thích vẫn hoạt động, lỗi được ghi | Authentication, retry/roaming metrics |

Trong các test “deny”, phải kiểm tra **đích thật sự hoạt động trên đường hợp lệ**; nếu server đích đang tắt, connection timeout không chứng minh firewall đã chặn đúng. Nên có test đối chứng từ role được phép và quan sát rule/action tại điểm enforcement.

## 14. Quy trình triển khai và hardening WLAN

### Bước 1 — Vẽ trust boundary theo luồng thật

Thu thập SSID, AP, BSSID, coverage, cáp uplink, VLAN/trunk, gateway, controller, AAA/RADIUS, DHCP/DNS, firewall, ứng dụng, Internet egress và cloud management. Ghi **đường dữ liệu** riêng với đường **quản trị**.

### Bước 2 — Phân loại người dùng và thiết bị

Tách managed employee, BYOD, contractor, guest, IoT, admin và thiết bị chưa đủ posture. Mỗi nhóm cần owner, phương thức onboarding, credential lifecycle và danh sách dịch vụ được phép.

### Bước 3 — Chọn cơ chế bảo vệ link và identity

Đánh giá WPA3/WPA2 Enterprise với EAP-TLS cho managed device, OWE/guest policy nơi thích hợp, phương án riêng cho IoT/legacy. Kiểm tra server certificate validation, PMF, WPA3 transition mode và WPS; đừng giảm cấu hình chung chỉ để một client cũ kết nối.

### Bước 4 — Ánh xạ zone và thực thi quyền

Tạo mapping SSID/role tới VLAN/VRF/subnet, DHCP/DNS phù hợp và firewall **default deny** giữa các zone. Xác định local switching/central tunneling, client isolation scope và IPv6 path. Khóa management plane.

### Bước 5 — Kiểm thử quan sát trước khi mở rộng

Trên canary AP/site, thực hiện positive/negative tests, roaming, mất AAA, mất controller, đổi VPN/DNS, hết hạn certificate và khác biệt firmware/client. Không dùng thành công association làm proxy cho thành công authorization.

### Bước 6 — Rollout có đo lường và rollback

Giới hạn phạm vi thay đổi, backup policy/config, có owner phê duyệt và tiêu chí rollback (xác thực lỗi tăng, role lệch, guest vào nội bộ, IoT mất kết nối, roaming suy giảm). Theo dõi ít nhất trọn chu kỳ nghiệp vụ liên quan, không chỉ vài phút ngay sau đổi cấu hình.

### Bước 7 — Review liên tục

Kiểm kê rogue/unknown AP, firmware, chứng chỉ, credential, SSID cũ, quyền management, RADIUS policy, DHCP pool, IPv6 và log access. Khi mở văn phòng, thuê nhà thầu hoặc thêm thiết bị IoT, review boundary trước khi cho phát SSID/đổi VLAN.

## 15. Bài tập tình huống: một SSID sai, nhiều hệ thống bị ảnh hưởng

**Bối cảnh:** Tòa nhà có hai tầng, 14 AP, một controller và hai SSID `Office-Staff`/ `Office-Guest`. Nhân viên dùng EAP-TLS; khách dùng guest onboarding. Một đợt thay cấu hình cho phép SSID Guest trên AP tầng 2 nhưng ánh xạ nhầm VLAN `110` (Employee) thay vì `120`. Firewall đang cho phép Employee vào một số business API. Ngoài ra, một nhóm IoT vẫn dùng mật khẩu Wi-Fi chung và hệ thống giám sát nhận nhiều sự kiện deauth vào buổi trưa.

**Dữ kiện giả định:**

| Quan sát | Đặt câu hỏi |
|---|---|
| Khách tầng 2 nhận IP `10.60.10.77/24` thay vì `10.60.20.0/23` | Lỗi nằm ở portal, DHCP, AP/controller mapping hay relay? |
| Khách tầng 1 vẫn nhận guest subnet đúng | Policy áp cục bộ theo AP/site hay có drift cấu hình? |
| Một số TCP connection tới business API thành công | Firewall có đang phân loại theo zone gán sai hay API vẫn có AuthZ? |
| Wi-Fi có nhiều event deauth | Do roaming, RF, firmware hay frame giả? PMF hỗ trợ tới mức nào? |
| Một IoT không hỗ trợ WPA3 | Có nên hạ mức bảo mật của mọi nhân viên hay cô lập IoT? |
| Nhân viên nhận cảnh báo chứng chỉ RADIUS không đúng | Cần xử lý thế nào để không khuyến khích bỏ qua validation? |

**Câu hỏi thực hành:**

1. Hãy vẽ ít nhất **năm trust boundary** từ điện thoại khách đến business API và chỉ ra vị trí mapping sai.
2. Tại sao portal thành công hoặc SSID tên `Office-Guest` không chứng minh thiết bị ở guest zone?
3. Cần điều tra những dữ liệu nào để xác định lỗi nằm tại AP/controller, RADIUS, VLAN, relay hoặc DHCP?
4. Hãy lập ba kiểm thử **positive** và ba kiểm thử **negative** cho quá trình rollback.
5. Nếu IoT không hỗ trợ EAP-TLS/WPA3, đề xuất giải pháp giảm blast radius mà không giảm bảo mật employee.
6. Nên giải thích và xử lý những sự kiện deauth ra sao trước khi kết luận có kẻ tấn công?

**Gợi ý đối chiếu:**

- Trust boundaries: điện thoại ↔ sóng/association, AP ↔ WLAN role, role ↔ VLAN/SSID data path, VLAN ↔ DHCP/gateway/firewall, gateway ↔ business API AuthN/AuthZ. Lỗi VLAN ở AP tầng 2 có thể khiến guest được xử lý như employee ở network layer nếu policy kiểm tra nguồn dựa trên mapping đó.
- Xác minh **role và VLAN thực tế theo client session** ở controller, AP profile/group, trunk allowed VLAN, DHCP lease/relay, firewall zone của traffic. Guest portal không xác thực EAP-TLS thay cho nhân viên và không tự enforce mọi ACL.
- Kết quả IP `10.60.10.77` thuộc employee /24 là bằng chứng đáng điều tra, nhưng không tự chứng minh toàn bộ API đã bị truy cập trái quyền. Kiểm tra application authorization ở từng endpoint và log truy cập.
- Positive: Employee vẫn được cấp employee role và làm việc được; Guest tầng 1/tầng 2 nhận guest subnet; IoT đã được phê duyệt gửi đúng telemetry. Negative: Guest không tới Employee/Server/Management qua IPv4, guest không bypass qua IPv6, user Wi-Fi không quản trị controller/AP.
- Giữ IoT ở SSID/zone riêng, dùng credential riêng nếu hỗ trợ, chỉ allow collector/những endpoint tối thiểu, có kế hoạch nâng firmware/thay thiết bị. Không hạ cấu hình chung của `Office-Staff`.
- Phân tích thời gian, BSSID, RSSI, roaming, kênh, lý do disassociation, PMF status và controller firmware. **Nhiều deauth không đồng nghĩa chắc chắn là giả mạo**; PMF không bảo vệ trước mọi gián đoạn RF.

## 16. Checklist rà soát Wi-Fi security boundary

- [ ] Đã xác định phạm vi sóng, loại AP/controller, SSID/BSSID, data plane và management plane.
- [ ] Phân biệt association, authentication, authorization, DHCP/IP và quyền ứng dụng.
- [ ] Không dựa vào SSID ẩn, MAC allowlist, captive portal hoặc IP được cấp như bằng chứng xác thực mạnh.
- [ ] Managed employee dùng 802.1X/EAP-TLS và **xác minh server certificate** khi phù hợp với chính sách/hạ tầng.
- [ ] WPA2/WPA3/OWE, PMF, WPS và client compatibility được chọn theo từng nhóm thiết bị.
- [ ] Legacy IoT có zone và quyền riêng; không hạ cơ chế bảo vệ của toàn bộ nhân viên để hỗ trợ nó.
- [ ] SSID/role-to-VLAN/VRF mapping, DHCP scope, DNS và IPv4/IPv6 được kiểm tra end-to-end.
- [ ] Các rule guest → employee/server/management và IoT → data zone được deny theo nhu cầu, không chỉ tách subnet.
- [ ] Client isolation được thử cả cùng AP, khác AP, wired peer và inter-VLAN routing.
- [ ] Đã bảo vệ control plane AP/controller, RADIUS/IdP, admin UI, firmware và quyền đổi WLAN policies.
- [ ] Có phương án rõ cho AAA/controller failure, roaming và cách xử lý session/role khi failover.
- [ ] DHCP snooping, RA Guard, DNS policy và chống IP spoofing được đánh giá cho access layer.
- [ ] Có telemetry RADIUS, WLAN, DHCP, firewall, DNS, WIDS/IPS và application correlation.
- [ ] Không coi mọi unknown AP là rogue có dây, mọi deauth là tấn công hoặc PMF là giải pháp chống jamming.
- [ ] Không chủ động gây nhiễu/deauth hoặc điều tra AP của bên khác ngoài phạm vi được phép.
- [ ] Có ma trận kiểm thử positive/negative, canary rollout, change review, rollback và kiểm tra drift.
- [ ] Log liên quan MAC, identity, AP location và session được bảo vệ theo chính sách riêng tư.

**Ghi nhớ:** **Wi-Fi là một đường vào mạng qua môi trường vô tuyến, không tự tạo ranh giới tin cậy đủ mạnh bằng tên SSID hoặc mật khẩu.** Một thiết kế an toàn phải nối đúng **link protection → xác thực và quyền → zone/VLAN/VRF → DHCP/DNS → firewall → ứng dụng**, đồng thời bảo vệ management plane, quan sát được các thay đổi và kiểm thử cả những đường truy cập không được phép.
