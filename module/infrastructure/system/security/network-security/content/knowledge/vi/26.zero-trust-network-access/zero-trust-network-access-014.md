# Các giới hạn khi áp dụng Zero Trust

Một công ty chuyển từ VPN truyền thống sang **Zero Trust Network Access (ZTNA)**. Sau khi triển khai, đội vận hành ghi nhận người dùng phải đăng nhập SSO, thực hiện MFA, thiết bị được kiểm tra tình trạng bảo mật và quyền truy cập chỉ mở tới những ứng dụng đã cấp phép. Công ty bắt đầu xem Zero Trust là lớp bảo vệ có thể ngăn hầu hết sự cố nội bộ.

Vài tuần sau, một tài khoản nhân viên hợp lệ bị chiếm phiên đăng nhập. Kẻ tấn công dùng chính quyền mà nhân viên đã có để tải dữ liệu được phép xem. Đồng thời, một API vẫn có lỗ hổng **Broken Object Level Authorization (BOLA)**, còn máy chủ cũ vẫn mở đường truy cập trực tiếp qua một tuyến VPN chưa được gỡ. ZTNA có thể vẫn hoạt động **đúng theo cấu hình của nó** nhưng tổ chức vẫn bị mất dữ liệu.

Ví dụ này nêu ra một ranh giới quan trọng: **Zero Trust là chiến lược kiểm soát tin cậy và truy cập, không phải phép bảo đảm mọi hành vi của chủ thể đã xác thực đều an toàn**. Nó giảm sự tin tưởng ngầm vào vị trí mạng, thúc đẩy xác minh danh tính/ngữ cảnh, cấp quyền tối thiểu và theo dõi quyết định truy cập. Tuy nhiên, để hiệu quả, tổ chức phải phối hợp Zero Trust với bảo vệ thiết bị, ứng dụng, dữ liệu, hạ tầng mạng, con người và quy trình vận hành.

Bài thuộc chương **Zero Trust Network Access** của module **SECURITY_NETWORK_SECURITY**, đặt Zero Trust trong bối cảnh phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, bảo mật mạng không dây, cloud, xác thực kết nối, giám sát và mô hình hóa mối đe dọa.

> **Thông điệp cốt lõi:** **Zero Trust không có nghĩa “không bao giờ tin ai” hoặc “bật một sản phẩm là an toàn”**. Quyết định cho phép phải được xây trên bằng chứng phù hợp, nhưng **bằng chứng có giới hạn về độ tin cậy và thời gian**, và mỗi cơ chế chỉ bảo vệ được những đường truy cập nằm trong phạm vi thực thi của nó.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Phân biệt **chiến lược Zero Trust**, **kiến trúc Zero Trust (ZTA)** và **sản phẩm ZTNA**.
2. Giải thích vì sao Zero Trust **giảm một số rủi ro** nhưng không loại bỏ tấn công sử dụng identity hợp lệ, thiết bị bị chiếm quyền, lỗi ứng dụng hoặc mất dữ liệu.
3. Nhận diện các giới hạn của **IdP, MFA, device posture, continuous verification, session revocation, PDP và PEP**.
4. Phát hiện **đường đi vòng qua enforcement point**, đặc biệt với VPN cũ, direct origin, IPv6, tài nguyên cloud và kết nối service-to-service.
5. Phân biệt **quyền vào ứng dụng** với **quyền thực hiện hành động và truy cập từng đối tượng dữ liệu**.
6. Đánh giá các ràng buộc với **legacy apps, BYOD, OT/IoT, non-HTTP protocols, workloads/CI và môi trường hybrid**.
7. Phân tích **availability, performance, privacy, quan sát, chi phí và tính phụ thuộc nhà cung cấp** khi triển khai Zero Trust.
8. Đề xuất **compensating controls**, ma trận kiểm thử negative/positive, quy trình di chuyển từng bước và chỉ số đánh giá hiệu quả.

## 2. Zero Trust là nguyên tắc kiến trúc, không phải một hộp sản phẩm

Một cách tiếp cận Zero Trust hiện đại thường nhấn mạnh:

- **Không tin cậy ngầm theo network location:** cùng VPC, cùng VLAN hoặc có VPN IP không tự đồng nghĩa được quyền.
- **Xác minh rõ chủ thể và yêu cầu:** identity, entitlement, thiết bị, ứng dụng, ngữ cảnh và mức rủi ro theo khả năng xác minh.
- **Least privilege:** chỉ cấp quyền cần thiết tới tài nguyên/hành động phù hợp trong khoảng thời gian được quản trị.
- **Giả định có thể xảy ra compromise:** thiết kế giảm blast radius, giám sát bất thường, thu hồi và phục hồi.
- **Đánh giá lại khi có bằng chứng mới:** không mặc định phiên hoặc thiết bị luôn duy trì trạng thái tốt.

**Zero Trust Architecture (ZTA)** là cách tổ chức ghép những nguyên tắc này vào toàn bộ hệ thống: identity, endpoint, network, application, data, telemetry và operations. **Zero Trust Network Access (ZTNA)** là một tập khả năng cụ thể giúp cấp quyền truy cập tới ứng dụng/dịch vụ theo chính sách, thường dựa trên danh tính và ngữ cảnh.

| Lớp | Giải quyết điều gì? | Không tự giải quyết |
|---|---|---|
| **Identity / IdP** | Ai đăng nhập? Mức đảm bảo xác thực nào? | Hành vi của user đã đăng nhập có đúng nghiệp vụ không? |
| **Device security / posture** | Thiết bị có tín hiệu compliance tại thời điểm đo? | Thiết bị chắc chắn không có malware hoặc zero-day? |
| **ZTNA / PDP / PEP** | Ai được thiết lập đường vào tài nguyên nào theo policy? | Backend có BOLA, SQL injection hay sai phân quyền tenant? |
| **Network segmentation / firewall** | Đường kết nối L3/L4 nào có thể tồn tại? | Identity người dùng và quyền từng bản ghi dữ liệu? |
| **mTLS / service identity** | Hai endpoint giao tiếp có danh tính/kênh được xác minh? | Service có quyền thực hiện thao tác kinh doanh cụ thể? |
| **Application AuthN/AuthZ** | User/workload được thực hiện hành động nào với object nào? | Bảo vệ thiết bị host, route bypass và mọi lớp network? |
| **Data security / DLP** | Phân loại, mã hóa, hạn chế sao chép, audit dữ liệu | Chặn tuyệt đối việc người được phép xem tự chép dữ liệu? |
| **Detection / response** | Nhận diện bất thường, điều tra, cô lập và khôi phục | Bảo đảm không có tấn công chưa phát hiện? |

### 2.1. Ba kết luận quá mức cần tránh

1. **“Đã có MFA nên tài khoản không thể bị chiếm.”** MFA có thể giảm nguy cơ, nhưng session cookies, tokens, endpoint malware và social engineering vẫn đáng lo.
2. **“Đã bật ZTNA nên không thể truy cập mạng nội bộ trái phép.”** Mọi direct origin, VPN route, SSH, IPv6 hoặc service connection ngoài PEP vẫn cần kiểm soát.
3. **“Đã có microsegmentation nên dữ liệu an toàn.”** Nếu một workload được phép gọi API nhưng API trả dữ liệu không đúng quyền, network segmentation không kiểm tra được object-level authorization.

## 3. Khung phân tích giới hạn: biết ranh giới rồi mới chọn giải pháp

Đối với mỗi tài nguyên, hãy hỏi:

1. **Protect:** tài sản nào? API, database, SSH host, dashboard, secrets, dữ liệu khách hàng?
2. **Principal:** ai yêu cầu? User, service account, container, CI runner, thiết bị IoT?
3. **Evidence:** có bằng chứng identity/posture nào, ai cấp, mới đến đâu, có thể bị giả hoặc đánh cắp không?
4. **Decision:** chính sách allow/deny/step-up do thành phần nào quyết định?
5. **Enforcement:** traffic thật có đi qua điểm thực thi đó không, kể cả đường phụ?
6. **Blast radius:** nếu principal hợp lệ bị chiếm, nó làm được gì?
7. **Response:** phát hiện và thu hồi ra sao, phiên đang mở có bị cắt không?
8. **Failure:** nếu IdP/PEP/connector/DNS/CA hoặc telemetry hỏng, hệ thống fail closed hay fail open?

~~~mermaid
flowchart LR
    SUB["User / device / workload"] --> PEP["Policy Enforcement Point"]
    PEP -->|"Quyền tới resource đã cấp"| APP["Application"]
    PEP -.->|"Xin quyết định"| PDP["Policy Decision Point"]
    PDP -.-> IDP["IdP + roles"]
    PDP -.-> POST["Posture / risk signals"]
    APP --> DATA[("Dữ liệu / giao dịch")]
    SUB -.->|"Đường bypass nếu không bị khóa"| DIRECT["Legacy VPN / direct origin / IPv6"]
    DIRECT -.-> APP
    ATT["Compromised valid identity"] -.->|"Lạm dụng quyền đã cho"| SUB
    AUTH["Application AuthZ"] -.-> APP
    FIRE["Network firewall / segmentation"] -.-> DIRECT
~~~

Sơ đồ chỉ là kiến trúc khái niệm. Một số nền tảng đặt PDP/PEP tại endpoint client, gateway, cloud edge hoặc connector; không có yêu cầu mọi gói tin phải đi qua control plane. Điểm cốt yếu là **mọi đường truy cập được bảo vệ phải thực sự chịu chính sách có thể kiểm chứng**.

## 4. Giới hạn 1 — Identity xác thực đúng vẫn có thể bị lạm dụng

**Xác thực (AuthN)** chứng minh người/thiết bị/workload đang sử dụng một credential được chấp nhận. Nó không chứng minh rằng mọi hành động sau đó đều do người chủ có chủ ý thực hiện hoặc không gây hại.

### 4.1. Các trường hợp phổ biến

| Tình huống | Hệ thống có thể thấy gì? | Giới hạn của Zero Trust |
|---|---|---|
| Người dùng đăng nhập đúng rồi bị lừa thực hiện thao tác | Session và MFA hoàn toàn hợp lệ | Không tự biết mục đích nghiệp vụ của user |
| Browser bị XSS hoặc extension độc hại | Cookie/session của browser được dùng từ môi trường đã cấp | Không tự khắc phục lỗ hổng browser/app |
| Máy đã enroll MDM bị malware điều khiển | Device identity hợp lệ, posture có thể vẫn “compliant” | Tín hiệu posture có thể không phát hiện compromise |
| Workload có mTLS certificate bị chiếm runtime | Service identity và TLS peer hợp lệ | Attacker hành động trong scope được allow |
| CI token có quyền deploy bị lộ | Token/role hợp lệ đối với control plane | Quyền quá rộng vẫn dẫn đến tác động lớn |
| Nội gián có quyền truy cập thực | PDP cho phép đúng chính sách | Có thể cần DLP, transaction controls, dual approval |

**Câu hỏi thực tế:** nếu một tài khoản được cấp phép cho bảng dữ liệu khách hàng bị chiếm, **giới hạn thực sự là gì?** Nếu tài khoản có thể export toàn bộ bảng, Zero Trust đã giảm các đường không cần thiết nhưng không chặn hành động nằm trong quyền sẵn có.

### 4.2. Biện pháp bù trừ

- **Phishing-resistant MFA** (như passkeys/FIDO2 phù hợp) ở tài nguyên nhạy cảm, kết hợp chống session theft và quản lý browser.
- Access tokens ngắn hạn/đúng audience/scope và proof-of-possession khi client/resource server hỗ trợ.
- **Least privilege theo resource, action, tenant và object**, không chỉ nhóm “employee”/“admin”.
- Just-in-time (JIT) access, privileged access management (PAM), approval nhiều bước cho thao tác nguy hiểm.
- Anomaly detection theo hành vi, rate limit, transaction validation, session revocation có kiểm chứng.
- EDR/endpoint hardening, cập nhật bản vá, bảo vệ Secrets và kiểm soát supply chain.

**Không có “zero-risk identity”**. Mục tiêu là giảm quyền bị lạm dụng, phát hiện sớm và giảm thời gian kẻ tấn công sử dụng được quyền đó.

## 5. Giới hạn 2 — MFA không bảo vệ mọi thứ sau thời điểm đăng nhập

MFA giảm phụ thuộc vào mật khẩu, nhưng không đủ cho:

- **Session hijacking:** đánh cắp cookie/access token sau khi user đã xác thực.
- **Adversary-in-the-middle phishing:** một số phương thức MFA có thể bị phishing để lấy phiên.
- **MFA fatigue:** người dùng xác nhận yêu cầu push bất thường.
- **Account recovery yếu:** kẻ tấn công chiếm quy trình reset, helpdesk hoặc phương thức dự phòng.
- **Stolen device / malware:** credential hoặc phiên bị lạm dụng ngay trên endpoint tin cậy.
- **Long-lived machine secrets:** không có người dùng tương tác để cung cấp MFA mỗi lần.

### 5.1. MFA theo mức rủi ro thay vì mọi packet

MFA khi login có thể được tái sử dụng trong một thời gian theo chính sách. Một thao tác nhạy cảm mới có thể yêu cầu **step-up** hoặc authentication freshness cao hơn. Không có nghĩa nhắc OTP trước mỗi TCP packet hoặc mỗi GET request.

| Thao tác | Mức bảo đảm có thể phù hợp | Rủi ro nếu làm quá ít hoặc quá nhiều |
|---|---|---|
| Xem ứng dụng nội bộ ít nhạy cảm | SSO còn hạn, entitlement hợp lệ | Nếu scope rộng vẫn lộ dữ liệu |
| Đọc dữ liệu khách hàng nhạy cảm | MFA, posture, app AuthZ | Token bị lộ vẫn có thể bị replay |
| Đổi quyền production | JIT/PAM, step-up, dual approval | Nếu xác thực lại liên tục gây fatigue và bypass |
| Job service-to-service | Short-lived workload identity/mTLS | Không có chỗ cho human OTP |
| Phiên SSH/RDP quản trị | Host verification, PAM/session policy | Revocation phiên đang mở có thể chậm |

### 5.2. Giới hạn của bearer token

Nếu API dùng một JWT tự chứa có `exp` còn hiệu lực, resource server không có introspection hoặc revoke integration thì việc IdP khóa user **có thể chưa đủ để API từ chối token ngay**. Chính sách bảo mật phải mô tả rõ TTL, expiry, refresh, token binding và khả năng thu hồi.

**MFA thành công không đồng nghĩa session sẽ an toàn cho tới khi logout**, đặc biệt khi browser hoặc thiết bị bị chiếm quyền sau login.

## 6. Giới hạn 3 — Device posture là tín hiệu không hoàn hảo

Nhiều hệ thống ZTNA đánh giá các điều kiện như thiết bị thuộc MDM, EDR đang chạy, ổ đĩa được mã hóa, OS được vá hoặc chứng chỉ thiết bị còn hạn. Đây là tín hiệu hữu ích nhưng có những vấn đề:

1. **Độ trễ:** MDM/EDR có thể ghi nhận trạng thái từ vài phút hoặc lâu hơn trước.
2. **Khoảng trống quan sát:** EDR không phát hiện mọi kỹ thuật tấn công, zero-day hoặc malware memory-only.
3. **Bypass/tampering:** tiến trình đặc quyền hoặc host compromise có thể giả mạo/che khuất một số signals.
4. **Offline/signal unavailable:** thiết bị mất kết nối MDM không có nghĩa tự động an toàn hoặc chắc chắn bị tấn công.
5. **Bảo mật ≠ tuân thủ:** máy đúng bản vá và bật disk encryption vẫn có thể bị user lừa cấp quyền.
6. **Quyền riêng tư:** thu quá nhiều telemetry thiết bị cá nhân có thể gây vấn đề dữ liệu và niềm tin người dùng.

### 6.1. BYOD, thiết bị không quản lý và người dùng ngoài tổ chức

Một công ty có thể không có quyền cài agent/EDR trên laptop nhà thầu. Cấm tuyệt đối mọi BYOD có thể ảnh hưởng hoạt động, nhưng cho BYOD quyền quản trị đầy đủ cũng tạo rủi ro.

Các phương án theo tầng có thể bao gồm:

- Chỉ cho **ứng dụng ít nhạy cảm** qua browser kèm MFA và session controls.
- Dùng **browser isolation/VDI** nếu có và phù hợp với dữ liệu.
- Cấp quyền read-only hoặc tính năng giới hạn, hạn chế export/download theo app.
- Buộc **managed device và JIT approval** cho production admin, database hoặc secrets.
- Theo dõi phiên và hết hạn quyền nhà thầu cùng hợp đồng.

Không phải mọi ZTNA product cung cấp đầy đủ browser isolation hoặc DLP. **Phải kiểm tra khả năng thật** trước khi thiết kế một policy dựa trên tính năng chưa có.

### 6.2. Độ mới của posture cần được định nghĩa

~~~text
Thiết bị được xác minh compliant ở thời điểm T0.
Ứng dụng nhạy cảm được truy cập ở thời điểm T1.

Nếu T1 - T0 vượt giới hạn freshness đã phê duyệt:
  - yêu cầu refresh posture,
  - step-up hoặc remediation,
  - hoặc deny theo sensitivity/risk tier.

Không suy:
  "T0 từng compliant" => "T1 chắc chắn compliant".
~~~

**Giới hạn quan trọng:** policy có thể chỉ được đánh giá khi mở **phiên mới**; nếu platform không có continuous signals/active-session enforcement, việc thay đổi posture chưa chắc cắt kết nối đang mở.

## 7. Giới hạn 4 — “Continuous verification” không nhất thiết là tức thời

Trong thực tế có nhiều thành phần với vòng đời riêng:

- IdP login/SSO session.
- ZTNA access grant và policy decision cache.
- Browser cookie hoặc access token của ứng dụng.
- TCP/TLS/gRPC/WebSocket/SSH/RDP connection đã tồn tại.
- Device posture signal được MDM/EDR cập nhật định kỳ.
- IAM/role membership và application authorization cache.

Một user bị disable trong IdP có thể bị chặn **khi tạo phiên ZTNA mới**, nhưng **phiên TCP hiện có**, JWT chưa hết hạn hoặc ứng dụng sử dụng session riêng có thể tiếp tục nếu không có cơ chế thu hồi phù hợp.

### 7.1. Đo chuỗi revoke thực tế

~~~mermaid
sequenceDiagram
    participant E as EDR / IdP / IAM
    participant P as PDP / policy engine
    participant G as PEP / connector
    participant A as Application / backend
    E->>P: T0→T1: sự kiện user disabled hoặc posture thay đổi
    P->>P: T1→T2: đánh giá lại entitlement/risk
    P->>G: T2→T3: deny/restrict/revoke grant
    G-->>A: T3: ngắt hoặc chặn luồng theo capability
    A->>A: T4: kết thúc session/token/transaction theo app policy
~~~

Các mốc cần đo: **T1−T0** (truyền tín hiệu), **T2−T1** (ra quyết định), **T3−T2** (thực thi) và khoảng tới **T4** (backend nhất quán). Không cam kết "revoke ngay" nếu chưa kiểm tra cả **long-lived sessions** và cache.

### 7.2. Token, cache và session làm tăng trade-off

| Cơ chế | Lợi ích | Giới hạn |
|---|---|---|
| Cached PDP allow decision | Giảm latency và phụ thuộc IdP | Policy đổi nhưng cache có thể còn hiệu lực |
| JWT access token | API verify locally, ít phải hỏi IdP | Revoke trước `exp` cần cơ chế riêng |
| Opaque session + introspection | Dễ kiểm tra trạng thái trung tâm | Thêm dependency, latency, HA/caching |
| Short-lived tokens | Rút ngắn replay window | Tăng renewal, cần quản lý refresh |
| Push revocation events | Có thể phản ứng nhanh | Delivery/offline/replay/ordering không hoàn hảo |
| PEP cắt tunnel | Thu hồi network path | App cookie, direct origin hoặc side channel có thể còn |
| App invalidate session | Chặn business API | Phiên network hoặc ứng dụng khác có thể chưa bị thu hồi |

### 7.3. Sai lầm thiết kế

- Thấy user **không đăng nhập mới được** rồi kết luận mọi access cũ đã bị revoke.
- Chỉ test HTTP request mới mà không kiểm tra **WebSocket/SSH/RDP/DB sessions đang tồn tại**.
- Dùng một TTL rất dài cho token đặc quyền mà không có reauth/revoke.
- Dùng một TTL quá ngắn cho tất cả luồng và tạo **MFA fatigue** hoặc outage liên tục.

**Thiết kế tốt cần nói rõ thời gian hội tụ**, không quảng cáo một cơ chế re-evaluation chung cho mọi protocol và vendor.

## 8. Giới hạn 5 — PEP không thể bảo vệ những đường không đi qua nó

Đây là giới hạn kiến trúc thường gây thất bại nhất khi triển khai ZTNA. Giả sử một ứng dụng có gateway kiểm tra SSO/MFA, nhưng **origin server** còn reachable từ:

- Public IPv4/IPv6 hoặc Load Balancer cũ.
- Site-to-site VPN hay remote-access VPN cấp route rộng.
- Cloud VPC peering, transit network hoặc ExpressRoute/Interconnect.
- NodePort, Kubernetes Ingress/Gateway khác, hostNetwork hoặc direct Pod/VM IP.
- Management network, SSH/RDP port, database listener hoặc internal proxy.
- Một API hostname/service endpoint phụ không nằm trong application catalog.

Khi kẻ tấn công có một đường khác tới origin, quyết định deny ở ZTNA portal **không đủ**.

### 8.1. Sơ đồ đường bypass

~~~mermaid
flowchart TD
    U["Client / workload"] --> Z["ZTNA PEP: AuthN + AuthZ"]
    Z -->|"Chỉ phiên được duyệt"| APP["Protected app / origin"]
    U -.->|"IPv6/public IP/VPN cũ"| LEG["Legacy route"]
    LEG -.-> APP
    FW["Cloud/host firewall, private ingress, ACL"] -.->|"Chặn direct origin path"| LEG
    APP --> AUTH["App AuthZ"]
~~~

**Kiểm soát bù trừ:** giới hạn origin chỉ nhận lưu lượng từ những gateway/connectors được xác thực; thiết kế TLS peer identity tại hop PEP→origin; kiểm tra cả IPv4/IPv6, public/private DNS, route, firewall, cloud security groups và listener phụ.

### 8.2. DNS trả private IP chưa chứng minh an toàn

Một laptop giải tên app ra `10.x.x.x` chỉ chứng minh **một câu trả lời DNS**, không chứng minh:

- Origin không còn public IP/hostname khác.
- Traffic thực đi qua PEP có policy.
- Firewall từ chối nguồn ngoài ý định.
- TLS certificate đúng peer.
- App phân quyền đúng user/tenant.

Thêm nữa, browser DoH, split DNS, IPv6 AAAA records, cached DNS hoặc proxy có thể tạo đường khác với lệnh kiểm tra thông thường.

### 8.3. ZTNA và NetworkPolicy/firewall nên phối hợp

ZTNA có thể cấp quyền theo user/app/session; **NetworkPolicy, SG/NSG, host firewall, segmentation** hạn chế L3/L4 và bảo vệ những nguồn không có ZTNA client. Không coi một công cụ là bản sao hoàn chỉnh của công cụ kia.

## 9. Giới hạn 6 — Quyền truy cập ứng dụng không phải quyền với dữ liệu

Một ZTNA policy thường trả lời: **user này có được mở đường vào `orders-api` không?** Nó không tự biết:

- User được xem **order ID nào**.
- Người dùng tenant A có được đọc object của tenant B không.
- Ai được phê duyệt chuyển tiền, thay cấu hình hoặc xóa dữ liệu.
- Request có input hợp lệ, gây SQL injection/SSRF hay không.
- Một service có được dùng credential của tài khoản DB quản trị hay không.

### 9.1. BOLA/IDOR không thể sửa chỉ bằng ZTNA

Ví dụ hai user đều có quyền dùng Orders Portal:

~~~text
User A: được xem /orders/1001
User B: được xem /orders/2002

ZTNA:
  A và B đều có quyền truy cập Orders Portal.

Ứng dụng phải kiểm tra:
  A GET /orders/2002 => DENY nếu A không sở hữu/được ủy quyền.
~~~

Nếu backend chỉ kiểm tra "user đã login" rồi trả mọi `orderId` được cung cấp, **một kết nối ZTNA hoàn toàn hợp lệ vẫn dẫn đến lộ dữ liệu**.

### 9.2. Phối hợp các quyết định độc lập

| Lớp quyết định | Câu hỏi | Ví dụ kết quả |
|---|---|---|
| ZTNA policy | User A được vào Orders Portal? | Allow |
| TLS/mTLS | Endpoint nào đang nói chuyện? | Xác minh peer |
| API authentication | User A có token hợp lệ dành cho API? | Allow |
| API authorization | User A có được đọc order 2002? | **Deny** |
| Database role | App DB account có được truy cập bảng cần thiết? | Giới hạn theo role |
| Data protection | Export/download có giới hạn/cảnh báo? | Rate limit, DLP, audit |

**Không chấp nhận raw `X-User: admin` do client gửi** làm bằng chứng identity. Nếu app dựa vào gateway identity headers, PEP cần strip/overwrite dữ liệu không tin cậy và origin chỉ chấp nhận kênh từ gateway đã xác minh, hoặc dùng signed assertion/token thích hợp.

## 10. Giới hạn 7 — Legacy applications không dễ chuyển thành per-app access

Nhiều ứng dụng hiện có không được thiết kế cho đăng nhập SSO/OIDC hoặc mô hình client → reverse proxy HTTPS. Một số ví dụ:

- Ứng dụng **client/server** dùng TCP custom hoặc địa chỉ IP hardcoded.
- Cơ sở dữ liệu với driver riêng và long-lived sessions.
- SSH, RDP, SMB và các giao thức không phải HTTP; một số cần nhiều port hoặc kết nối ngược.
- Middleware cũ tin **IP nguồn** và không có session identity riêng.
- Ứng dụng đòi **Kerberos/NTLM**, integrated authentication hoặc client certificate theo cách đặc thù.
- Hệ thống yêu cầu broadcast/multicast, UDP hoặc phát hiện dịch vụ bằng protocol không phù hợp proxy.
- Thiết bị công nghiệp/OT, cảm biến IoT, thiết bị y tế có vòng đời nâng cấp dài.

**Không phải mọi ZTNA product đều hỗ trợ mọi giao thức.** Một sản phẩm có thể rất mạnh với web apps nhưng hạn chế khi cần làm gateway cho SSH, RDP, database, SIP, UDP, SMB hoặc ứng dụng có nhiều kết nối phụ.

### 10.1. Ba mô hình di chuyển thường gặp

| Mô hình | Cách dùng | Điểm yếu cần đánh giá |
|---|---|---|
| **Browser/reverse-proxy access** | Gateway xác thực user và chuyển HTTPS vào app | Identity header trust, cookies, CORS, WebSocket, complex redirects |
| **Client/agent-based private access** | ZTNA client/tunnel chỉ tạo đường tới app được phép | Client compatibility, OS support, DNS/routing, offline policy |
| **Bastion/VDI/PAM** | User vào môi trường trung gian rồi thao tác legacy host/app | Session recording, clipboard/file transfer, credential injection, availability |

Với ứng dụng không thể tích hợp AuthN/AuthZ hiện đại, ZTNA **có thể thu hẹp đường vào** nhưng không làm hệ thống legacy tự hiểu quyền từng user. Đôi khi cần **modernization, application proxy hoặc privilege management** bổ sung.

### 10.2. OT/ICS/IoT: availability và safety là ràng buộc

Ở mạng vận hành công nghiệp, yêu cầu an toàn vận hành (*safety*) và liên tục hoạt động có thể quan trọng hơn việc triển khai agent, certificate rotation hoặc policy động trên thiết bị.

Không:

- Cài agent ZTNA vào PLC/thiết bị không hỗ trợ hoặc chưa có thẩm định của nhà sản xuất.
- Đổi route/firewall giữa phiên điều khiển quy trình mà chưa thử failover và ảnh hưởng safety.
- Mặc định tất cả thiết bị có thể dùng browser SSO/MFA.
- Vô hiệu kết nối khẩn cấp hoặc đường bảo trì đã được phê duyệt mà không có phương án thay thế.

Đường phù hợp có thể là **segmented OT zone, industrial DMZ, protocol-aware gateway, jump host, PAM, allowlist đường quản trị, giám sát thụ động và change control nghiêm ngặt**. Zero Trust được triển khai theo ranh giới bảo vệ có thể kiểm chứng, không ép từng thiết bị có tương tác MFA như laptop.

## 11. Giới hạn 8 — Service-to-service, máy tự động và CI không có “người dùng nhập MFA”

Zero Trust không chỉ là login người dùng vào portal. Trong cloud/Kubernetes, nhiều request phát sinh từ **workload, scheduled jobs, CI runners, serverless functions, service mesh proxies**.

Các workload này cần **machine/workload identity** và quyền scoped theo dịch vụ. Nhưng:

- Service account có thể bị cấp quyền quá rộng.
- Static API keys có thể tồn tại lâu hoặc bị commit vào source/image/log.
- Một node/container bị chiếm quyền có thể dùng chứng chỉ/service identity hợp lệ.
- Workload identity issuer hoặc Kubernetes API control plane bị lạm dụng có thể cấp danh tính sai.
- Session của workload có thể là gRPC/TCP kéo dài, không giống browser cookie.
- Máy tự động không phù hợp quy trình người dùng nhận OTP/push.

### 11.1. Thiết kế thay thế phù hợp

- Chọn **short-lived tokens/certificates** hoặc workload identities được cấp dựa trên attestation khi nền tảng hỗ trợ.
- Giới hạn `principal → service → operation`; không dùng shared account giữa mọi microservice.
- TLS/mTLS xác minh peer, quản lý trust domain và certificate rotation.
- Phân đoạn Pod/node/VPC với CNI NetworkPolicy hoặc firewall tương ứng, ngăn đường ngoài policy engine.
- Bảo vệ secrets, image supply chain, admission, service account token projection và quyền CI/CD.
- Xác minh dữ liệu/đối tượng ở ứng dụng ngay cả khi service-to-service mTLS đã thành công.

**Một certificate hợp lệ chứng minh peer theo cơ chế đã thiết kế**, không chứng minh process đang sử dụng cert đó chưa bị compromise hay mọi lời gọi của nó đều có mục đích đúng.

### 11.2. Tài khoản “break-glass” và automation

Automation quản trị hoặc quy trình khẩn cấp đôi khi cần hoạt động khi IdP/PDP không sẵn sàng. Tạo exception vô hạn hoặc shared admin key là rủi ro lớn. Nếu cần break-glass:

1. Xác định trường hợp được phép sử dụng, owner và approval.
2. Giới hạn resource/action, nguồn, thời gian, tần suất và người giám sát.
3. Ghi audit độc lập, có thể hậu kiểm, chống thay đổi trái phép.
4. Rotate/seal credentials theo quy trình và kiểm thử định kỳ.
5. Tự thu hồi ngoại lệ sau sự kiện.

**Break-glass không phải một cổng hậu cố định bỏ qua toàn bộ Zero Trust.**

## 12. Giới hạn 9 — Không thể nhìn và kiểm soát mọi thứ qua kênh mã hóa

TLS/mTLS/SSH và các đường hầm được mã hóa giúp bảo vệ dữ liệu trên đường truyền. Nhưng mã hóa cũng có thể hạn chế **khả năng IDS/IPS và các thiết bị mạng thấy nội dung ứng dụng**.

| Phương pháp quan sát | Có thể nhìn thấy | Không chắc nhìn thấy |
|---|---|---|
| L3/L4 flow logs | IP, port, protocol, thời lượng/bytes, verdict | User intent, HTTP path/body, object-level AuthZ |
| TLS handshake metadata | Một số thông tin protocol/cert/SNI khi có thể quan sát | Plaintext payload, mọi hostname khi ECH/QUIC hoặc tunnel |
| Gateway/PEP access logs | Principal, app/resource ID, policy decision nếu gateway biết | Mọi thao tác sau khi đi qua đường opaque tunnel |
| Application audit logs | User, API action, object/resource, result | Những connection không tới ứng dụng hoặc bị chặn ở mạng |
| EDR/runtime telemetry | Process/host activity trong phạm vi agent | Hành vi hoàn toàn trên thiết bị không quản lý |
| DLP/casb/browser controls | Một số download/upload và thao tác được hỗ trợ | Sao chép bằng kênh khác hoặc dữ liệu được xem hợp lệ |

### 12.1. TLS inspection có đánh đổi

Giải mã/kiểm tra nội dung tại gateway có thể giúp áp một số chính sách L7, nhưng:

- Gateway trở thành **điểm kết thúc TLS** và điểm có khả năng đọc dữ liệu nhạy cảm.
- Cần quản lý certificate, trust store và bảo vệ private keys.
- Một số ứng dụng có certificate pinning, mTLS riêng hoặc giao thức E2E không phù hợp interception.
- Quyền riêng tư, quy định địa phương, dữ liệu cá nhân và chính sách người lao động cần được đánh giá.
- Thêm latency, chi phí xử lý và điểm lỗi; nếu gateway down có thể ảnh hưởng nhiều apps.

Không dùng khái niệm Zero Trust làm lý do mặc định **thu thập toàn bộ payload của người dùng**. Thiết kế telemetry theo mục đích, minimization và role-based access.

### 12.2. Không thấy nội dung không đồng nghĩa không kiểm soát được quyền

Ngay cả khi dùng SSH/tunnel opaque, PEP vẫn có thể quyết định **ai được kết nối tới tài nguyên/protocol nào và trong bao lâu**. Nhưng không thể tự kết luận người dùng thực hiện **câu lệnh SQL hoặc nghiệp vụ nào** sau khi kênh được mở nếu không có PAM, database audit hoặc application controls.

## 13. Giới hạn 10 — Bảo vệ mạng không thay bảo vệ dữ liệu

Một nhân viên được phép xem hồ sơ khách hàng có thể vô tình hoặc cố ý:

- Xuất file CSV chứa dữ liệu được cấp quyền.
- Gửi ảnh chụp màn hình cho người khác.
- Copy dữ liệu sang ứng dụng SaaS không được phép.
- Truy cập từ thiết bị tin cậy nhưng lưu file cục bộ thiếu mã hóa.
- Chia sẻ qua email hoặc lưu vào nơi không có retention policy.

ZTNA có thể hạn chế **đường vào hệ thống**, nhưng **không bảo đảm ngăn mọi kênh dữ liệu rời ứng dụng**.

### 13.1. Các lớp cần phối hợp

| Lớp | Kiểm soát cần đánh giá |
|---|---|
| **Data inventory/classification** | Dữ liệu nào nhạy cảm, thuộc tenant nào, lưu ở đâu? |
| **Application AuthZ** | Quyền trên từng object/row/field và từng hành động |
| **Least privilege and JIT** | Quyền export/report/admin chỉ khi cần |
| **DLP/managed browser/endpoint** | Kiểm soát download, clipboard, file transfer khi sản phẩm hỗ trợ |
| **Encryption at rest/in transit** | Bảo vệ dữ liệu trên lưu trữ/kênh truyền đúng threat model |
| **Audit/UEBA** | Phát hiện download hoặc truy xuất bất thường có điều kiện |
| **Backups/recovery** | Khôi phục dữ liệu sau mã độc hoặc thay đổi sai |
| **Retention/privacy** | Giới hạn thời gian, mục đích và quyền xem dữ liệu |

Không hứa **ngăn mọi exfiltration** nếu một user có thể đọc nội dung hợp lệ. Với một số ứng dụng, hạn chế download là khả thi; với trường hợp khác, người dùng vẫn có thể chụp ảnh màn hình bằng điện thoại. Cần **chọn kiểm soát thực tế**, đo mức giảm thiểu rủi ro và giải thích rủi ro còn lại.

## 14. Giới hạn 11 — False positives/false negatives của tín hiệu rủi ro

Zero Trust thường dùng ngữ cảnh như posture, rủi ro đăng nhập, vị trí, hành vi và lịch sử phiên. Những tín hiệu này **không tuyệt đối**.

### 14.1. False positive: người hợp lệ bị chặn

Ví dụ:

- Người dùng đi công tác, mạng/IP thay đổi bất thường.
- MDM vừa mất liên lạc nhưng máy vẫn an toàn.
- IdP nhận diện impossible travel do VPN/proxy và geolocation sai.
- Certificate rotation chậm làm client hợp lệ bị từ chối.
- Dữ liệu risk provider bị lỗi khiến nhiều người vào app production bị step-up.

Hậu quả: gián đoạn công việc, helpdesk quá tải, MFA fatigue và xu hướng người dùng tìm bypass.

### 14.2. False negative: attacker không bị phát hiện

Ví dụ:

- Attacker dùng đúng browser/device đã compromise.
- Đăng nhập diễn ra từ địa điểm quen thuộc nhưng do malware điều khiển.
- Token hợp lệ được replay trong môi trường không có token binding.
- Người có quyền thực vượt phạm vi nhiệm vụ nhưng hành vi trông bình thường trong telemetry.
- Tín hiệu posture chưa cập nhật tại thời điểm request.

### 14.3. Điều chỉnh theo ứng dụng và bằng chứng

Một policy tốt phân biệt:

- **Hard constraints:** không có entitlement, account disabled, token invalid → deny.
- **Adaptive signals:** mức rủi ro đăng nhập, thiết bị offline, location unusual → step-up/remediation theo policy.
- **Critical actions:** thay firewall, quản trị production, cấp quyền cao → yêu cầu xác thực/phê duyệt bổ sung.
- **Low-risk access:** không tạo quá nhiều chướng ngại gây bypass.

**Không biến risk score thành identity**, cũng không suy “score thấp” là chắc chắn an toàn. Ghi nhận lý do quyết định và review false positive/negative cùng người sở hữu ứng dụng.

## 15. Giới hạn 12 — Availability và sự phụ thuộc control plane

Một hệ thống Zero Trust có thể thêm phụ thuộc:

- IdP, MFA/SSO và hệ thống federation.
- PDP/policy engine, role/entitlement store và MDM/EDR posture API.
- PEP/gateway/connectors, service discovery/DNS.
- PKI/CA, certificate rotation, trust bundle.
- Cloud control plane, overlay network/tunnel và audit pipeline.
- Application origin và các reverse proxies riêng.

Một lỗi ở **dịch vụ chia sẻ** có thể tác động nhiều ứng dụng dù từng ứng dụng vẫn khỏe.

### 15.1. Fail-open và fail-closed đều có giá

| Tình huống | Fail-closed có lợi gì? | Rủi ro về availability |
|---|---|---|
| Không truy vấn được IdP khi mở phiên mới | Không cấp quyền không có bằng chứng identity | User không thể vào app dù password đúng |
| MDM posture provider unavailable | Không coi missing signal là compliant | Một số BYOD/managed devices bị chặn |
| PDP mất kết nối | Không tự tạo access grant mới ngoài policy | Phiên mới không được cấp |
| PEP/connector hỏng | Không tự mở direct origin path | Nhiều app có thể ngừng truy cập |
| CA/trust bundle lỗi | Không chấp nhận peer chưa xác minh | Các kết nối TLS/mTLS mới có thể lỗi |
| Risk service lỗi | Không bỏ qua mọi điều kiện ở ứng dụng nhạy cảm | Tăng step-up, cần degraded-mode rõ |

**Fail-closed** hợp lý cho nhiều ranh giới đặc quyền nhưng không đồng nghĩa **tắt mọi luồng hiện có ngay lập tức trong mọi outage**. Một số phiên cũ có thể tiếp tục theo **cấu hình cache/TTL được chủ sở hữu rủi ro phê duyệt**. Mỗi resource tier cần chính sách riêng, test rõ ràng và không đòi 100% availability từ một thành phần đơn lẻ.

### 15.2. Bài toán “đường cứu hộ” trong sự cố

Khi IdP hoặc PEP có sự cố, đội SRE vẫn cần khôi phục hệ thống. Nếu **mọi** đường quản trị phụ thuộc đúng thành phần vừa hỏng, có nguy cơ không thể sửa nó.

Cần một **break-glass path**:

- Thực sự **tách dependency** khỏi thành phần có thể lỗi.
- Được kiểm soát mạnh, lưu kín credentials, MFA/approval nếu khả thi.
- Giới hạn nguồn, tài nguyên, thời gian và người sử dụng.
- Được kiểm thử phục hồi định kỳ, ghi audit/hậu kiểm.
- Không tự mở public admin endpoint trong khi chưa xác minh quyền.

**Đường cứu hộ cần tồn tại có chủ đích**, không phải một tuyến bypass thường trực không được giám sát.

### 15.3. HA, DR và kiểm thử lỗi cần thiết

- PEP/connector chạy nhiều instance, region/AZ khi kiến trúc và nhà cung cấp hỗ trợ.
- Khóa và trust bundles được đồng bộ trong vùng bảo vệ phù hợp.
- Đo **thời gian áp policy**, latency đăng nhập và mTLS handshakes.
- Kiểm tra session behavior khi một connector hoặc policy engine restart.
- Xác định tính nhất quán giữa nhiều PEP và policy versions.
- Chạy outage test đối với IdP/PDP/MDM/CA ở lab; kiểm tra nguồn hợp lệ và nguồn bị deny.
- Không rollback bằng cách vô hiệu MFA hoặc mở `0.0.0.0/0` cho production app.

## 16. Giới hạn 13 — Chi phí, hiệu năng và vận hành có thể tăng

Zero Trust có thể giảm chi phí điều tra và rủi ro, nhưng triển khai đầy đủ không miễn phí:

| Nhóm chi phí | Ví dụ |
|---|---|
| **Bản quyền / dịch vụ** | Số user, device, app, connector, lưu lượng hoặc tier sản phẩm |
| **Network/data** | Gateway processing, cross-region traffic, private connectivity, egress |
| **Endpoint management** | MDM, EDR, posture integrations, agent lifecycle |
| **Identity governance** | Directory cleanup, role design, PAM/JIT, joiner/mover/leaver |
| **Engineering** | Migration legacy apps, DNS, routing, certs, protocol compatibility |
| **Operations** | Helpdesk, SRE on-call, policy review, incident response, log retention |
| **Performance** | Proxy hops, TLS setup, session checks, identity service requests |
| **Audit/compliance** | Evidence correlation, privacy reviews, exceptions and reporting |

### 16.1. Tác động lên ứng dụng

Một thêm hop PEP/connector có thể ảnh hưởng:

- Latency p50/p95/p99, đặc biệt nếu traffic hairpin qua region xa.
- Streaming/WebSocket/gRPC, long-lived sessions và timeouts.
- Upload/download file lớn hoặc protocols dùng multiple connections.
- DNS resolution/split-horizon, TLS termination, mTLS/PKI compatibility.
- Mobile apps, browsers và client agents không cùng phiên bản.
- Khả năng quan sát/trace context qua gateway.

Không gán một con số overhead cố định cho mọi giải pháp. Đo baseline **trên workload thật và region/network tương đương production**, rồi so với SLO, số kết nối, tải peak và chi phí.

### 16.2. Complexity là một rủi ro bảo mật

Quá nhiều policy exceptions, gateway rules, agent versions và IAM roles không có owner sẽ tăng:

- Config drift giữa các region và app.
- Helpdesk workarounds mở network/allow-all.
- Tokens/certificates bị giữ lâu hơn cần thiết.
- Khó xác định ai đang có quyền effective.
- Chậm thu hồi quyền khi nhân viên rời tổ chức.

**Zero Trust cần governance và tự động hóa có kiểm toán**, không chỉ triển khai thêm sản phẩm.

## 17. Giới hạn 14 — Vendor lock-in và môi trường hybrid/multi-cloud

Các nhà cung cấp có thể dùng mô hình khác nhau về:

- Định nghĩa "app", "session", "device posture" và "trusted user".
- Cách PDP/PEP phân phối và áp policy, caching và revoke.
- Giao thức hỗ trợ (HTTPS, TCP, UDP, SSH, RDP) và client agents.
- Integration với cloud IAM, OIDC/SAML, MDM/EDR, PKI và proxies.
- Audit fields, decision IDs, telemetry export và API quản trị.
- HA/multi-region, dữ liệu được xử lý ở vị trí nào, data residency và privacy.
- License model, quotas, lock-in của connectors/tunnels và policy expressions.

### 17.1. Cách giảm phụ thuộc

1. Quản lý **nguồn sự thật** của identity, application inventory và quyền truy cập trong hệ thống có owner rõ ràng.
2. Ưu tiên standards và giao thức được hỗ trợ khi phù hợp, nhưng **không tự suy mọi policy vendor chuyển đổi được một-một**.
3. Lưu policy-as-code ở mức **resource/action/risk requirement**, tách khỏi cú pháp triển khai đặc thù.
4. Kiểm thử export logs/decisions và migration path trước khi phụ thuộc sâu.
5. Thiết kế connector deployment, DNS và route không tạo một failure domain không thể thay thế.
6. Khi dùng nhiều clouds, xác minh **trust domain/federation**, không dùng chung broad privilege chỉ vì tên group tương tự.

### 17.2. Chia sẻ trách nhiệm với cloud/SaaS

Nếu ZTNA gateway chạy trên cloud, nhà cung cấp có thể chịu trách nhiệm phần hạ tầng dịch vụ, nhưng doanh nghiệp thường vẫn phải quản lý:

- User/group entitlements, MFA và access policies.
- Connector routes, origin firewall, DNS và certificates.
- Device posture sources và account lifecycle.
- Logs, retention, privacy và ứng cứu sự cố.
- Backend application permissions, tenant data và compliance.

**“Dịch vụ managed Zero Trust” không có nghĩa nhà cung cấp đã cấu hình least privilege, app AuthZ hoặc chặn tất cả bypass paths giúp bạn.**

## 18. Giới hạn 15 — Zero Trust không phải điểm kết thúc của giám sát và incident response

Một chính sách có thể deny những yêu cầu đã biết, nhưng vẫn cần phát hiện:

- Identity hợp lệ đang truy cập với **tốc độ hoặc khối lượng bất thường**.
- Kẻ tấn công khai thác lỗi ứng dụng sau khi đã được cấp đường.
- Token/session reuse, impossible travel hoặc thiết bị đột nhiên mất EDR.
- Thay đổi policy, role, connector routes, public exposure và break-glass grants.
- Data access vượt baseline, object enumeration, export hoặc lạm dụng API.
- Internal service-to-service connections ngoài thông lệ, cloud lateral movement.

### 18.1. Những gì cần quan sát

| Data source | Tín hiệu | Giới hạn |
|---|---|---|
| IdP / SSO | Sign-in, MFA, failures, account state | Không nhìn đầy đủ việc app dùng dữ liệu |
| ZTNA PDP | Decision allow/deny/step-up, role, policy version | Quyết định chưa chứng minh traffic thật đã qua PEP |
| PEP/connector | Session start/end, app route, principal, revoke | Một số protocols opaque không lộ action |
| EDR/MDM | Posture, alert, integrity signals | Không phát hiện mọi malware, có độ trễ |
| Network/firewall/DNS | Direct-origin attempts, IPv6, VPN bypass, flows | Không biết quyền user/tenant theo object |
| Application audit | User, action, resource, authorization result | Có thể thiếu những request bị chặn trước app |
| DB/data logs | Query/data export volume, actor, access anomalies | Dữ liệu nhạy cảm, cần quản lý retention |
| CI/IaC/cloud audit | Ai thay roles/routes/policy, lúc nào | Không nói riêng traffic đã bị chặn |

### 18.2. “Không có log bất thường” không đồng nghĩa an toàn

Thiếu logs có thể do đường bypass không được instrument, ingestion lỗi, sampling, clock skew, retention quá ngắn hoặc vendor API chưa export được. Kiểm tra **coverage của telemetry** bằng controlled tests và so sự kiện ở IdP, PDP, PEP, firewall và application.

Không bật logging toàn bộ payload chỉ để có thêm visibility: điều này có thể gây lộ tokens, thông tin khách hàng và dữ liệu nhạy cảm. Hạn chế trường, redaction và quyền truy cập là yêu cầu bảo mật.

## 19. Bảng ranh giới và kiểm soát bù trừ

Không có một danh sách sản phẩm có thể thay thế việc xác định **rủi ro nào còn tồn tại sau ZTNA**. Ví dụ:

| Giới hạn | Zero Trust/ZTNA có thể giúp | Kiểm soát bù trừ | Bằng chứng nên thu |
|---|---|---|---|
| Credential/session bị đánh cắp | Giới hạn app scope, reauth, session grant | Phishing-resistant MFA, token PoP, EDR, app rate limits | Invalid/replayed token decisions, session revocations |
| Thiết bị malware nhưng posture tốt | Thêm ngữ cảnh và expiry | EDR, OS hardening, least privilege, transaction monitoring | Endpoint alerts, user actions, data access |
| User có quyền nhưng lạm dụng | Ràng buộc tài nguyên và thời gian | App AuthZ, dual approval, DLP, UEBA | Per-object access, export audit |
| Public origin bypass | Hạn chế qua PEP nếu mọi đường đều bắt buộc | Firewall, private ingress, route controls, host security | Network negative tests từ nguồn ngoài |
| Service không hỗ trợ agent/protocol | Giới hạn một số đường truy cập | Bastion, PAM/VDI, segmentation, modernization | Protocol-specific tests |
| Token revoke không tức thời | Re-evaluation theo thiết kế | Short TTL, introspection, event-driven revoke | T0–T4, active connection tests |
| IdP/PDP/PEP outage | Enforce access decisions | HA, cache policy, break-glass, DR | Outage tabletop/lab results |
| Encrypted traffic opaque | Biết access session/resource | App logs, DB audit, endpoint telemetry | L7 app authorization test |
| Cloud workload bị compromise | Workload identity + scope | K8s RBAC, NetworkPolicy, admission, secret manager | Effective permissions, workload flow evidence |
| IoT/OT không hỗ trợ modern auth | Kiểm soát jump host/gateway | OT segmentation, vendor-approved safety process | Zones, maintenance-session logs |
| Policy drift và quyền tồn đọng | Central policies và audit | IaC/review, access recertification, expiry | Diff, role entitlements, exception inventory |
| Vendor-specific assumptions | Có thể tập trung quản trị | Protocol standards, independent architecture inventory | Cross-platform proof, migration tests |

### 19.1. Nguyên tắc Defense in Depth

~~~mermaid
flowchart LR
    PR["Principal / device"] --> ID["Identity, MFA, posture"]
    ID --> Z["ZTNA per-app grant / PEP"]
    Z --> NET["Network firewall / segmentation"]
    NET --> SVC["Service mTLS / API identity"]
    SVC --> AUTH["Application object-level AuthZ"]
    AUTH --> DATA["Data permissions, DLP, audit"]
    SEC["Incident response & telemetry"] -.-> ID
    SEC -.-> Z
    SEC -.-> NET
    SEC -.-> AUTH
~~~

Sơ đồ diễn tả **các lớp ra quyết định**, không phải thứ tự packet traversal bắt buộc. Trong nhiều thiết kế, firewall chặn trước PEP; mTLS có thể ở hop giữa proxy và backend; ứng dụng có thể có gateway riêng. Mục tiêu là **các kiểm soát độc lập và có thể kiểm thử**, không phải thêm càng nhiều hop càng tốt.

## 20. Threat modeling: 24 tình huống Zero Trust chưa giải quyết hết

| ID | Tình huống | Điều có thể diễn ra dù đã có ZTNA | Kiểm soát/bằng chứng |
|---|---|---|---|
| L01 | **Session hijacking** | Kẻ tấn công dùng cookie/token của user đã MFA | PoP khi phù hợp, session TTL/revoke, EDR, anomaly logs |
| L02 | **Insider misuse** | Nhân viên xuất dữ liệu nằm trong quyền của mình | App least privilege, DLP, volume limits, audit |
| L03 | **BOLA/IDOR** | User hợp lệ đọc tài nguyên user khác | Object-level AuthZ tests, backend decision logs |
| L04 | **Shared admin account** | Không xác định người thực hiện thao tác | Individual identities, PAM/JIT, session recording |
| L05 | **Posture stale** | Máy bị nhiễm sau lần compliant check | Signal freshness, risk re-evaluation, endpoint hardening |
| L06 | **MDM/EDR offline** | PDP tin trạng thái cũ quá lâu | Offline fallback policy, time-bound grants |
| L07 | **Origin direct bypass** | VPN/private route đi vòng PEP | Firewall/private ingress, negative origin tests |
| L08 | **IPv6/public secondary endpoint** | IPv4 bị chặn nhưng AAAA/IPv6 vẫn vào | Dual-stack firewall/DNS, source-specific probes |
| L09 | **Identity header spoofing** | Client tự gửi `X-Forwarded-User` | Strip/overwrite, trusted origin path, signed assertion |
| L10 | **JWT audience confusion** | Token app A được dùng ở app B | Signature/issuer/audience/scope checks |
| L11 | **JWT revocation gap** | User bị khóa nhưng token chưa hết hạn | Short TTL, introspection/events, active session tests |
| L12 | **Long-lived SSH/RDP** | Kết nối tiếp tục sau revoke | PAM/PEP terminate, expiry and kill-session verification |
| L13 | **Legacy protocol bypass** | App TCP custom không qua gateway web | Protocol-aware client/bastion + host segmentation |
| L14 | **Workload identity misuse** | Pod bị chiếm dùng cert mTLS hợp lệ | NetworkPolicy, service AuthZ, K8s RBAC, token rotation |
| L15 | **OT agent incompatibility** | Thêm client ZTNA gây gián đoạn thiết bị | OT DMZ, vendor validation, safety approval |
| L16 | **IdP outage** | Không còn nguồn xác thực để mở phiên | HA, fail policy, emergency access review |
| L17 | **PDP/PEP policy drift** | Gateway region A và B khác effective rules | Central IaC, policy version audit, cross-region tests |
| L18 | **Policy quá rộng** | “All employees → all internal apps” | Per-app entitlements, deny-by-default |
| L19 | **False positive risk** | User hợp lệ bị chặn, helpdesk cấp bypass rộng | Risk tier, canary, exception TTL, UX measurement |
| L20 | **False negative risk** | Attacker dùng đúng máy/địa điểm quen thuộc | Behavioral + app data telemetry, transaction controls |
| L21 | **Opaque encrypted protocol** | PEP không thấy query hay nội dung file | Database/app audit, safe L7 enforcement |
| L22 | **Data export authorized** | Dữ liệu nhạy cảm được tải hợp lệ và chia sẻ ngoài | Classification, DLP, watermark, audit, user training |
| L23 | **Vendor/connector compromise** | Một gateway có đường tới nhiều mạng | Scoped connectors, privileged RBAC, HA, trust verification |
| L24 | **Emergency bypass quên thu hồi** | Break-glass account vẫn tồn tại quyền lớn | Time-bound approvals, audit, periodic recertification |

### 20.1. Đánh giá mức độ ưu tiên

Không xếp rủi ro chỉ theo độ “mới” của công nghệ. Với mỗi mục, đánh giá:

- **Likelihood:** attacker cần điều kiện gì, hệ thống đang exposure đến đâu?
- **Impact:** quyền vượt khỏi một user, một app, cả tenant hay toàn hạ tầng?
- **Coverage:** ZTNA có thực sự xử lý đường truy cập liên quan?
- **Detectability:** log nào sẽ phản ánh hành động, có retention và correlation không?
- **Recovery:** có thể rotate/revoke/rebuild trong bao lâu, ảnh hưởng SLO và dữ liệu gì?

Một **origin bypass** hoặc **connector có quyền rộng** có thể là ưu tiên số một dù bảng dashboard báo mọi user đều đã MFA. Một **BOLA trên API nhiều dữ liệu** cũng có thể nghiêm trọng hơn việc chưa cài ZTNA client trên một ứng dụng không nhạy cảm.

## 21. Policy mô tả rủi ro còn lại (pseudocode, không dùng để triển khai)

Để không nhầm **mục tiêu chính sách** với **khả năng sản phẩm**, có thể lập một tài liệu có thể review:

~~~yaml
# PSEUDO-POLICY CHO THIẾT KẾ, KHÔNG PHẢI SCHEMA CỦA ZTNA VENDOR.
resource:
  id: production-orders-admin
  owner: platform-operations
  dataClassification: restricted
  protocols:
    - HTTPS
  exposure:
    onlyViaApprovedPEP: true
    denyDirectOrigin: true
    verifyOriginTlsPeer: true

identityRequirements:
  user:
    source: corporate-idp
    activeAccount: required
    resourceEntitlement: required
    phishingResistantMfa: required
    recentAuthentication: required
  device:
    managedDevice: required
    postureEvidenceSource: trusted-mdm-edr
    maximumPostureAge: approved-by-risk-owner
  workload:
    allowedServiceIdentities: []

sessionPolicy:
  scope: this-application-only
  maximumDuration: approved-by-risk-owner
  inactivityTimeout: approved-by-risk-owner
  evaluateBeforeNewAccessGrant: true
  evaluateOnPostureOrPrivilegeChange: true
  revokeActiveConnection: verify-product-capability
  denyOnMissingEntitlement: true
  onIdpUnavailable: deny-new-privileged-grants
  emergencyAccess:
    requiresApproval: true
    expiresAutomatically: true
    separateFromBrokenDependency: true

applicationControls:
  validateEndUserIdentity: true
  enforceObjectLevelAuthorization: true
  requireTransactionApprovalWhereNeeded: true
  auditSensitiveExports: true

observability:
  include:
    - principal-id
    - resource-id
    - decision-reason
    - effective-policy-version
    - session-lifecycle
    - revocation-timeline
  exclude:
    - raw-access-token
    - session-cookie
    - private-key
    - customer-record-body

rollout:
  firstStage: lab-and-approved-canary
  negativeTestsRequired: true
  preserveRecoveryPath: true
  exceptionsNeedOwnerAndExpiry: true
~~~

**Đọc đúng ví dụ:**

1. Các giá trị `approved-by-risk-owner` là **placeholder**, không phải default TTL an toàn.
2. `revokeActiveConnection: verify-product-capability` yêu cầu **chứng minh** nền tảng thực sự ngắt được phiên có sẵn.
3. `denyDirectOrigin` phải được thực thi bằng **network controls thật**, không phải chỉ khai báo trong portal.
4. `enforceObjectLevelAuthorization` là nhiệm vụ của backend/API/DB, ZTNA không tự áp trên mỗi hàng dữ liệu.
5. `workload.allowedServiceIdentities` rỗng trong ví dụ vì tài nguyên được thiết kế cho người dùng; không suy mọi app đều chỉ cho user.
6. Không copy trực tiếp cấu trúc này vào Terraform, gateway hoặc Kubernetes: nó không phải syntax triển khai của sản phẩm.

### 21.1. Template bằng chứng thiết kế

| Câu hỏi | Dữ liệu cần lưu |
|---|---|
| Ai có quyền? | User/workload principals, roles, approval owner, scope |
| Quyền tới đâu? | Resource ID, app hostname/protocol/port, action |
| Xác minh bằng gì? | IdP, MFA assurance, device attestation, auth freshness |
| Dựa vào quyết định nào? | Policy version, allow/deny/step-up reason, event ID |
| Ai thực thi? | PEP/connector ID, origin firewall rule, backend AuthZ |
| Hiệu lực trong bao lâu? | Token/decision/session TTL, idle timeout, renew |
| Khi bị revoke? | Event T0, PDP T1/T2, PEP T3, backend T4 |
| Khi gặp lỗi? | Fail policy, HA, emergency path, on-call owner |
| Giới hạn còn lại? | Threat scenarios, compensating controls, accepted risks |

**Có bảng này chưa chứng minh vận hành đúng:** tất cả thông tin phải đối chiếu với **effective config và positive/negative tests**.

## 22. Ma trận kiểm thử giới hạn Zero Trust

Các test phải được thực hiện trên **tài khoản/môi trường đã được cho phép**, tránh truy cập dữ liệu người khác, chiếm phiên thật hoặc gây gián đoạn production. Mỗi negative test cần **positive control** để phân biệt bị chặn bởi chính sách với đích đang lỗi.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | Nhân viên đúng role + MFA + managed device → app A | Phiên được cấp đúng app | IdP + PDP + PEP + app logs |
| N01 | User chưa xác thực → app A | Không tạo grant | AuthN deny và không có PEP session |
| N02 | User SSO hợp lệ nhưng sai role → app A | PDP/resource deny | Resource entitlement evidence |
| N03 | User có quyền app A thử mở app B | Deny nếu app B không được cấp | App ID, separate decision |
| P02 | User cần step-up, MFA phù hợp hoàn tất | Phiên chỉ cấp sau step-up | Assurance/freshness logs |
| N04 | User không hoàn tất step-up | Deny, không cấp phiên đặc quyền | Decision reason |
| N05 | Managed device non-compliant | Deny/remediate theo risk tier | Trusted posture record/timestamp |
| N06 | Device posture quá cũ hoặc mất tín hiệu | Không tự coi compliant vô hạn | Freshness policy decision |
| P03 | Nhà thầu còn hiệu lực → low-risk wiki | Allow đúng tài nguyên | Contractor entitlement |
| N07 | Nhà thầu có quyền wiki thử production DB | Deny đường production | PDP+firewall deny |
| N08 | User dùng token/cookie sai audience hoặc hết hạn | Resource server/PEP từ chối | Token validation reason |
| N09 | Client tự gửi `X-User: admin` | Không nâng quyền | PEP header sanitization/backend verification |
| P04 | App A user hợp lệ đọc dữ liệu của mình | App AuthZ allow | Object authorization log |
| N10 | App A user hợp lệ đọc dữ liệu tenant khác | **Application AuthZ deny** | Object-level decision |
| N11 | User bị disable khi còn JWT chưa hết hạn | Deny sau độ trễ revoke đã thiết kế | T0–T4 timeline |
| N12 | SSH/WebSocket phiên đang mở bị thu hồi | Ngắt/restrict theo capability đã cam kết | Active session probe |
| N13 | Client thử origin public IPv4 trực tiếp | Network deny | Firewall verdict + origin healthy control |
| N14 | Client thử origin IPv6/AAAA trực tiếp | Network deny khi policy yêu cầu | Dual-stack route/firewall evidence |
| N15 | Client thử VPN route/peering cũ | Không bypass PEP | Network path test, asset inventory |
| P05 | PEP tới origin với đúng TLS peer | Successful authorized traffic | Valid SAN/SNI/chain and app result |
| N16 | Origin có certificate sai | TLS client từ chối, không bỏ verify | TLS error logs |
| P06 | Workload identity đúng → service được phép | mTLS/AuthZ hợp lệ | Principal and service policy |
| N17 | Service identity khác trong cùng trust domain | Deny nếu không entitlement | Service-to-service AuthZ |
| N18 | CI/service account quyền deploy quá rộng trong review | Phát hiện và thu hẹp theo policy | IAM role audit, negative permissions |
| N19 | IdP offline trong lab | Không cấp grant mới trái policy | Outage decision + metrics |
| N20 | PDP/PEP connector down | Không tự mở direct origin | Fail-closed and recovery evidence |
| P07 | Break-glass hợp lệ, đúng owner/TTL | Mở hạn chế và audit | Approval, session start/end |
| N21 | Break-glass hết hạn | Tự thu hồi, không còn quyền thường trực | Expiry + revocation |
| N22 | Cloud/PEP region khác dùng policy cũ | Detect drift và chặn quyền sai | Policy version + regression |
| P08 | Low-risk app không bị MFA prompts quá mức | Truy cập đúng SLA/UX policy | Reauth rate, user outcomes |
| N23 | Risk signal false positive trong canary | Có review/remediation, không bypass bừa | Decision appeals + policy audit |
| N24 | Traces/logs có raw tokens/PII | Logging policy redacts đúng | Sanitized log sample |
| P09 | Policy cập nhật có canary + rollback | App hợp lệ không mất quá mức SLO | Success/error/latency metrics |
| N25 | Hành vi export data quá lớn bởi user hợp lệ | DLP/app monitoring phát hiện/giới hạn khi hỗ trợ | Data audit, rate limits |
| N26 | Legacy TCP/UDP app không qua gateway web | Compensating control hoạt động | Bastion/network ACL and flow evidence |

### 22.1. Không nhầm nguyên nhân thất bại

- **TCP timeout** không chứng minh PDP deny nếu server chưa khởi động hoặc route hỏng.
- **HTTP 403** có thể đến từ application AuthZ, WAF, PEP hay backend; cần phân biệt nguồn quyết định.
- **SSO/MFA success** không chứng minh user có entitlement cho từng app hoặc data object.
- **PDP deny** không chứng minh direct origin không reachable qua VPN khác.
- **JWT signature hợp lệ** không chứng minh token dành cho API đó, chưa bị revoke hoặc không bị đánh cắp.
- **User disable thành công** không chứng minh SSH/RDP session đã đóng.
- **DNS trả private IP** không chứng minh app chỉ cho traffic từ PEP.

### 22.2. Đo hiệu quả thay vì chỉ đếm số thiết bị đã cài agent

| KPI/đo lường | Ý nghĩa | Cách diễn giải cẩn thận |
|---|---|---|
| % ứng dụng quan trọng có enforced per-app access | Coverage theo tài sản | Không chỉ số app catalog; cần test origin bypass |
| % user/workload principals có least-privilege mapping | Độ chính xác entitlement | Cần review quyền thực và expiry |
| Median/p95 access grant latency | Trải nghiệm và hiệu năng | Phân nhóm app/region/network |
| % high-risk sessions dùng assurance phù hợp | Identity controls | Không tự bảo đảm chống session hijack |
| Revocation latency T0→T4 | Khả năng thu hồi | Đo cả active sessions/legacy protocols |
| Direct-origin paths còn reachable | Bề mặt bypass | Kiểm tra nhiều nguồn và dual-stack |
| Unknown/unmanaged device access attempts | Coverage posture | Tín hiệu không chứng minh mọi device an toàn |
| Policy exceptions quá hạn | Governance drift | Xem owner, business impact, rủi ro |
| App AuthZ failures/data export alerts | Quyền dữ liệu | Đối chiếu false positives và business workflows |
| IdP/PDP/PEP SLO + outage results | Resilience | Một số outage fail-closed là đúng policy |
| Audit coverage / log correlation | Investigation readiness | Thiếu log không tự nghĩa không có tấn công |
| Access support tickets/reauth rate | Usability | MFA fatigue/bypass risk nếu tăng bất thường |

Chỉ số phải có baseline, chủ sở hữu, mục tiêu và phương pháp thu thập. **“100% users đã bật MFA” không phải KPI duy nhất chứng minh Zero Trust hiệu quả.**

## 23. Kiểm tra an toàn: phân biệt bằng chứng mạng với bằng chứng identity

Các ví dụ dưới đây chỉ dùng trên **máy hoặc môi trường thuộc quyền quản lý/được cho phép kiểm tra**. Phần lệnh quan sát không mở cổng, thay firewall, thay identity policy, lấy token hoặc tạo traffic đến tài nguyên không được phê duyệt.

### 23.1. Windows — đọc DNS, route và interface

~~~powershell
# Xác định interface, DNS và route hiện có; không thay đổi cấu hình.
Get-NetIPConfiguration
Get-DnsClientServerAddress
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric

# Tên miền .test là minh họa: chỉ có answer nếu lab cấu hình DNS.
Resolve-DnsName -Name "admin.example.test" -Type A
Resolve-DnsName -Name "admin.example.test" -Type AAAA
~~~

Những thông tin này giúp tìm đường IPv4/IPv6 và DNS, nhưng **không chứng minh PDP/PEP đang xác thực đúng user, phiên có scope phù hợp hoặc backend bảo vệ dữ liệu**. Một laptop có VPN và DNS private vẫn có thể nhận **deny** theo chính sách và đó là kết quả đúng.

### 23.2. Linux — chỉ đọc đường định tuyến và resolver

~~~bash
# Quan sát trạng thái mạng hiện tại, không tạo đường truy cập mới.
ip -br address
ip -4 route show
ip -6 route show
ip rule show

# Tên .test chỉ là placeholder lab, không phải public service thật.
getent ahostsv4 admin.example.test
getent ahostsv6 admin.example.test

# Nếu hệ thống có systemd-resolved:
resolvectl status
~~~

Một số ZTNA clients dùng per-application proxy hoặc tunnel nên **route table của OS không phản ánh toàn bộ đường đi thật của tiến trình**. Cần xem effective client/PEP/connector configuration cùng log theo ứng dụng.

### 23.3. Quan sát TLS ở một lab endpoint

~~~bash
# Chỉ dùng với TLS lab server do bạn quản lý và CA lab hợp lệ.
# Không tắt hostname/certificate verification khi kiểm tra.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername admin.example.test \
  -verify_hostname admin.example.test \
  -verify_return_error \
  -CAfile /path/to/lab-root-ca.pem \
  -brief
~~~

Lệnh trên kiểm tra **TLS peer identity** của một endpoint tại `127.0.0.1:8443` có hostname lab, **không chứng minh ZTNA identity verification, device posture, user permissions hoặc app AuthZ**. Nếu không có lab TLS server, lệnh sẽ thất bại và không cần cố “sửa” bằng `verify=false`.

### 23.4. Lệnh đọc không thể kiểm tra toàn bộ Zero Trust

Một phép đọc DNS, route hoặc TLS **không thể khẳng định**:

- ZTNA client thực sự đã qua PEP.
- PDP quyết định cho đúng user/resource/action.
- Device posture assertion được MDM/EDR ký và còn mới.
- Session/grant có TTL và được revoke đúng.
- Origin không có bypass path.
- App từ chối BOLA hoặc data export sai quyền.

Với ZTNA, phần bằng chứng thiết yếu thường ở **IdP sign-in logs, PDP decision logs, PEP/connector session logs, endpoint posture, network/firewall evidence và application audit**. Các API/câu lệnh quản trị là **vendor-specific**; không nên bịa một lệnh CLI "chung" rồi xem kết quả là bằng chứng chính sách.

## 24. Phương pháp triển khai theo rủi ro thay vì thay toàn mạng ngay

### Bước 1 — Xây inventory và data-flow diagram

Liệt kê ứng dụng, APIs, SSH/RDP/database, cloud resources, OT/IoT, users, service accounts, DNS, ingress/proxies, VPN/routes, public/private addresses và đặc tính dữ liệu. Xác định ai sở hữu từng ứng dụng và tác vụ nào cần quyền.

**Đầu ra cần review:** bảng `principal → resource → action → protocol → security tier`, cả đường truy cập dự kiến và đường legacy.

### Bước 2 — Chọn những ranh giới dễ bảo vệ và đo baseline

Ưu tiên một vài **web applications** có owner, IdP integration, ít giao thức đặc biệt và khả năng rollback tốt. Đo login latency, sign-in success, app SLO, helpdesk tickets, rule exceptions và network paths hiện có.

Không chọn ngay toàn bộ production SSH/database hoặc OT safety-critical devices làm pilot nếu chưa có thiết kế riêng.

### Bước 3 — Chuẩn hóa identity lifecycle

- Kết nối IdP, federation, contractor directory, PAM và user-role ownership.
- Bật MFA mức phù hợp, ưu tiên phishing-resistant cho tài nguyên quan trọng.
- Giảm account chia sẻ, role quá rộng, API keys không hết hạn.
- Chuẩn hóa quy trình joiner–mover–leaver và kiểm tra thực tế khi role bị đổi.

**Một ZTNA policy không thể bù cho directory groups sai** nếu nó lấy group đó làm bằng chứng entitlement.

### Bước 4 — Thiết kế posture và quyền riêng tư

Xác định lớp thiết bị (managed, BYOD, partner, IoT), nguồn attestation, độ mới, handling offline và thông tin nào thực sự cần thu. Có chính sách khác nhau theo mức độ nhạy cảm; không mặc định đòi toàn bộ telemetry của thiết bị cá nhân.

### Bước 5 — Chặn origin bypass bằng các lớp mạng

Đưa ingress qua connectors/gateways được kiểm soát; áp firewall, private endpoints, segmentation, DNS và origin TLS; xử lý dứt điểm public IPv4/IPv6, VPN cũ, peering và alternative listeners.

**Chỉ khi negative tests xác minh bypass thực sự không dùng được** mới có cơ sở nói ứng dụng đã được bảo vệ bởi PEP trên những đường được xét.

### Bước 6 — Áp per-app authorization và session lifecycle

Ghi rõ các điều kiện user/role, device, action, risk, TTL, step-up và revocation. Backend tiếp tục app AuthZ. Kiểm tra long-lived sessions, IdP outage/degraded-mode và các grant trong cache.

### Bước 7 — Thiết kế compensating controls cho phần không chuyển đổi được

Với SSH/RDP/DB/legacy/OT, dùng bastion/PAM/VDI, network segmentation, protocol-specific gateway, host firewall và logging được sản phẩm hỗ trợ. Ghi **accepted risk**, chủ sở hữu và ngày review, không giấu ứng dụng khỏi inventory vì nó không hỗ trợ ZTNA client.

### Bước 8 — Canary, positive/negative tests và audit

Triển khai cho nhóm users, subnet và applications giới hạn. Chạy ma trận ở mục 22, kiểm tra cả nguồn được cấp và không được cấp, cả app healthy control, IPv4/IPv6, regional PEPs và active revoke.

### Bước 9 — Rollout với SLO và rollback

Đặt ngưỡng dừng: sign-in failure rate, p95 login latency, app 5xx, helpdesk escalations, token refresh failures, policy drift, connector health và session revoke latency. Rollback phải **khôi phục availability mà không mở lại đường public bypass không kiểm soát**.

### Bước 10 — Recertification và ứng cứu dài hạn

Định kỳ rà soát roles, contractor access, policy exceptions, device posture coverage, origin paths, connector permission, break-glass grants, certificate rotations và backups/DR. Thu hồi quyền khi không còn nhu cầu.

## 25. Xử lý sự cố khi Zero Trust vẫn bị vượt qua

Nếu phát hiện dữ liệu bị xuất trái phép dù ZTNA dashboard cho thấy phiên hợp lệ, **đừng kết luận ngay rằng ZTNA “không chạy”**. Phân loại điểm thất bại:

~~~mermaid
flowchart TD
    A["Phát hiện truy cập đáng ngờ"] --> B{"Phiên thật có đi qua PEP?"}
    B -->|"Không"| BY["Kiểm tra origin bypass, VPN/routes, cloud public endpoints"]
    B -->|"Có"| C{"IdP/PDP đã xác minh và allow identity đúng?"}
    C -->|"Không"| ID["Kiểm tra token validation, identity/header spoofing, policy drift"]
    C -->|"Có"| D{"Chủ thể/thiết bị bị compromise?"}
    D -->|"Có thể"| SEC["Cô lập endpoint, revoke phiên/tokens, điều tra"]
    D -->|"Chưa rõ"| E{"App AuthZ/tenant/resource đúng?"}
    E -->|"Không"| APP["Khoanh BOLA/business logic/data permissions"]
    E -->|"Có"| DATA["Kiểm tra quyền export, misuse và data telemetry"]
    BY --> OUT["Thu thập evidence + giảm blast radius + remediation"]
    ID --> OUT
    SEC --> OUT
    APP --> OUT
    DATA --> OUT
~~~

### 25.1. Runbook phản ứng

1. **Khoanh phạm vi:** principal, device, session, app, token/credential, host, tenant, data objects.
2. **Thu bằng chứng:** IdP events, PDP/PEP decisions, connector flow, EDR alerts, app/DB audit, cloud/VPN/host firewall, thời gian được đồng bộ.
3. **Containment:** disable/restrict compromised principal, thu hồi grants/token theo khả năng, đóng active sessions, cô lập máy/host và ngăn direct origin.
4. **Kiểm tra lateral movement:** các ứng dụng khác user/service account có quyền, VPN/peering routes và cloud IAM roles.
5. **Giảm quyền còn lại:** thu hẹp app/DB authorizations, rotate credentials, đánh giá group entitlements và JIT approvals.
6. **Khôi phục:** thiết bị/ứng dụng sạch, certificate/token rotation có kiểm soát, kiểm tra app BOLA và firewall paths.
7. **Xác minh:** chạy lại positive/negative tests, đo session revocation latency và kiểm tra app data logs.
8. **Hậu kiểm:** cập nhật threat model, policy-as-code, observability, exception review, training và SLO.

Không yêu cầu log raw cookies, passwords, access tokens hay private keys để chứng minh identity; bằng chứng như session correlation ID, policy decision ID và issuer/audience validation result thường thích hợp hơn.

### 25.2. Sự cố availability cần được tách khỏi sự cố access bypass

| Loại | Dấu hiệu | Ưu tiên |
|---|---|---|
| **Identity outage** | Người hợp lệ không login, IdP unavailable | HA/degraded-mode/break-glass theo policy |
| **Policy regression** | Sau thay policy, app hợp lệ bị deny | Diff và rollback hẹp, không mở allow-all |
| **Origin bypass** | Client đi thẳng app dù PEP deny | Khóa route/firewall, điều tra exposure |
| **Credential compromise** | Token/session đúng nhưng hành vi lạ | Revoke, rotate, EDR, app audit |
| **Application AuthZ flaw** | User được vào portal nhưng đọc sai tenant | Fix backend object-level checks, audit phạm vi lộ |
| **Data misuse** | Export nhiều dữ liệu bằng quyền thật | DLP, volume limits, approval, incident response |

Mỗi loại cần **đúng nhóm owner**: IAM, network/platform, endpoint, app team, SOC, DBA hoặc OT safety. Zero Trust không làm mất nhu cầu phân công trách nhiệm.

## 26. Bài tập tình huống: ZTNA chạy đúng nhưng dữ liệu vẫn rò rỉ

**Bối cảnh giả định:** một doanh nghiệp có ba dịch vụ:

- **Portal bán hàng:** HTTPS app, đã đặt sau ZTNA gateway, nhân viên SSO và MFA.
- **Database reporting:** chạy trên máy ảo, từng truy cập qua VPN network-wide, chưa chuyển hết.
- **Payment service:** API nội bộ có mTLS giữa workloads, được gọi bởi Orders service.

Doanh nghiệp áp chính sách:

- Nhân viên `sales` được vào Portal khi có managed device/compliant posture.
- DBA có JIT quyền tới database reporting từ bastion.
- Orders workload có mTLS identity hợp lệ để gọi Payment API.

Một ngày xuất hiện ba dấu hiệu:

1. User bán hàng đăng nhập hợp lệ, xem nhiều order nhưng app không kiểm tra ownership ở endpoint `GET /orders/{id}`.
2. Khi user này bị disable, một phiên WebSocket còn tồn tại, trong khi một JWT access token tự chứa vẫn chưa hết `exp`.
3. Một máy nhà thầu từ remote VPN cũ gọi được database reporting trực tiếp qua IPv6, không đi qua ZTNA gateway.

### 26.1. Phân tích theo ranh giới

| Dấu hiệu | Ranh giới bị lỗi/thiếu | Zero Trust/ZTNA có thể đã làm đúng phần nào? |
|---|---|---|
| Xem order không thuộc quyền | **Application object-level AuthZ** | Cấp đúng đường vào Portal cho user có role |
| WebSocket vẫn mở sau disable | **Session revocation/long-lived connection handling** | Chặn phiên ZTNA mới nhưng chưa cắt phiên cũ |
| JWT còn hạn sau disable | **Token lifecycle/resource server revocation** | IdP đã khóa user, nhưng token self-contained còn được API chấp nhận |
| Nhà thầu tới DB qua IPv6 VPN | **Origin bypass / network segmentation** | ZTNA PEP đã chặn app catalog nhưng không nằm trên đường này |
| Orders mTLS tới Payment | **Workload peer identity** | Xác minh service, nhưng chưa chứng minh mọi business action hợp lệ |

### 26.2. Câu hỏi

1. Vì sao login MFA hợp lệ không đủ bảo vệ endpoint `GET /orders/{id}`?
2. Quyền nào phải được kiểm tra ở **ZTNA**, quyền nào phải kiểm tra **trong ứng dụng**?
3. Làm thế nào đo thời gian từ disable account đến lúc PEP và app thực sự chặn mọi active sessions?
4. Nếu JWT đã được ký đúng và còn hạn, API có thể kiểm soát thu hồi sớm bằng những cách nào?
5. Vì sao thêm một deny rule trong ZTNA portal không tự chặn đường IPv6 qua VPN cũ?
6. Thêm lớp nào để bảo vệ database reporting mà vẫn hỗ trợ bảo trì khẩn cấp?
7. mTLS xác thực Orders service có chứng minh Orders được phép tạo mọi payment transaction không?
8. Hãy thiết kế ba positive và năm negative tests với nguồn, đích, expected decision và evidence.
9. Phân tích một kịch bản fail-closed làm đứt truy cập đúng và cách khôi phục không làm yếu chính sách.
10. Chọn ít nhất ba **KPI có thể đo** để đánh giá hiệu quả sau remediation.

### 26.3. Gợi ý trả lời

- API phải xác thực user và **đối chiếu từng object/tenant**. ZTNA cấp phiên tới Portal không thay quyền đọc `orderId`.
- Khi user disable, cần liên kết **IdP event → PDP decision → PEP revoke → application session/token state**, đo T0–T4 cả WebSocket/TCP và token refresh.
- JWT self-contained có thể cần TTL ngắn, introspection, session denylist hoặc event-driven revoke theo architecture; không hứa revoke tức thời khi không có integration.
- Database cần firewall/IPv6 dual-stack rules, chặn VPN direct origin hoặc chuyển qua **bastion/PAM/connector** phù hợp giao thức, JIT và audit.
- mTLS xác thực **workload peer**, Payment API vẫn cần service authorization, idempotency, business validation và quyền dữ liệu.
- Positive tests: sales hợp lệ xem order thuộc quyền; DBA JIT vào DB qua bastion; Orders hợp lệ gọi Payment. Negative: sales đọc order tenant khác; user disabled không renew; WebSocket bị terminate trong SLO; nhà thầu IPv6 VPN không tới DB; workload không entitlement gọi Payment bị deny.
- KPI có thể gồm **% origin bypass paths đóng**, **p95 revocation latency**, **% critical apps có object-level AuthZ tests**, **% exception grants hết hạn đúng**, hoặc **policy-related availability incidents**.

## 27. Checklist: áp dụng Zero Trust với kỳ vọng đúng

- [ ] Có phân biệt **chiến lược Zero Trust**, **ZTA** và **một sản phẩm ZTNA**.
- [ ] Đã xác định ứng dụng, dữ liệu, user/workload identities, protocol, owner và trust boundaries.
- [ ] Không coi “VPN IP nội bộ”, “MFA thành công”, “MDM compliant” hoặc “certificate hợp lệ” là bằng chứng toàn bộ phiên an toàn.
- [ ] Mỗi ứng dụng/tài nguyên có entitlement theo least privilege, không dùng group `all-employees` cho mọi dịch vụ.
- [ ] Có ứng phó session/cookie/token theft sau MFA, không chỉ xử lý password compromise.
- [ ] Xác minh JWT issuer/audience/signature/expiry/scope và có cơ chế revoke phù hợp risk tier.
- [ ] Session IdP, ZTNA, TCP/TLS và application được phân biệt, có TTL/renew/revoke rõ.
- [ ] Đo độ trễ thu hồi phiên đang mở (WebSocket, SSH/RDP, DB) nếu protocol liên quan.
- [ ] Device posture có nguồn tin cậy, signal freshness và chính sách khi offline/missing.
- [ ] Có chính sách BYOD/contractor không mặc định thu thập mọi telemetry hoặc cấp production admin.
- [ ] PEP nằm trên tất cả đường truy cập cần bảo vệ và origin chỉ tin các gateway/connector đã được kiểm chứng.
- [ ] Có negative tests cho public/private IPv4, IPv6, DNS, VPN cũ, peering, host/network paths và listener phụ.
- [ ] Xác minh TLS server peer identity ở client→PEP và PEP→origin; không dùng `verify=false`.
- [ ] Backend không tin headers identity tự khai, trừ khi đã được gateway xác thực/ghi đè trên trust boundary đúng.
- [ ] NetworkPolicy, cloud SG/NSG, host firewall, IAM/RBAC và segmentation bổ sung cho ZTNA.
- [ ] Application có object-level/tenant AuthZ, validation, business controls và DB permissions.
- [ ] Workload identities/CI tokens có scope nhỏ, xoay vòng và không dùng human MFA không phù hợp.
- [ ] Legacy/OT/IoT/non-HTTP apps được đánh giá khả năng hỗ trợ giao thức và compensating controls.
- [ ] Có kế hoạch cho các đường encrypted/opaque mà gateway không quan sát được nội dung.
- [ ] Có data classification, DLP hoặc app data controls phù hợp rủi ro export/copy dữ liệu.
- [ ] Risk score/geo/device signals không được coi là tuyệt đối; đo false positives/false negatives.
- [ ] IdP/PDP/PEP/MDM/CA outage được kiểm thử; biết trạng thái fail-open/fail-closed thực tế.
- [ ] Emergency/break-glass access có scope, approval, TTL, audit và đường độc lập khỏi failure domain cần khôi phục.
- [ ] Đã đo latency/CPU/network/data processing, license và helpdesk overhead.
- [ ] Có policy-as-code, versioning, review, exception inventory, owner và deadline thu hồi ngoại lệ.
- [ ] Không phụ thuộc hoàn toàn vào proprietary claims hoặc một connector không có HA/migration plan.
- [ ] Audit liên kết IdP, PDP, PEP, endpoint, firewall, app và database, nhưng không lộ bearer tokens, cookies hoặc dữ liệu cá nhân không cần thiết.
- [ ] Có positive/negative tests với nguồn hợp lệ và không hợp lệ, resource khỏe mạnh và evidence tại đúng enforcement point.
- [ ] Theo dõi độ phủ ứng dụng, số bypass còn mở, revocation p95, SLO, policy drift và data AuthZ anomalies.
- [ ] Triển khai canary, rollback, runbook, incident response và review định kỳ.
- [ ] Ghi nhận rủi ro còn lại: **identity hợp lệ có thể bị lạm dụng, telemetry không tuyệt đối và chính sách chỉ có tác dụng trên đường được thực thi**.

**Ghi nhớ:** **Giới hạn lớn nhất của Zero Trust không phải một tính năng thiếu trên dashboard, mà là nhầm phạm vi một quyết định truy cập với bảo mật của toàn hệ thống.** ZTNA có thể quyết định **ai được thiết lập phiên tới ứng dụng nào trong điều kiện nào**; nó không tự chứng minh **người đó luôn có ý định đúng, thiết bị không bao giờ bị compromise, dữ liệu được phân quyền từng object, phiên cũ đã bị cắt hoặc mọi đường truy cập đều đi qua PEP**. Kiến trúc vững cần **identity và posture đủ tin cậy, kiểm tra ứng dụng/dữ liệu, segmentation và origin hardening, telemetry, khả năng thu hồi thực, HA và quy trình vận hành có kiểm chứng**. Mục tiêu là **giảm và kiểm soát rủi ro còn lại**, không tuyên bố đã đạt trạng thái “an toàn tuyệt đối”.
