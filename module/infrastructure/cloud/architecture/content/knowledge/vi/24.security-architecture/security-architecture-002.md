# Zero Trust và phòng vệ nhiều lớp

> **Chương:** Kiến trúc bảo mật  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào Zero Trust và phòng vệ nhiều lớp để bảo vệ danh tính, workload, mạng, dữ liệu và chuỗi cung ứng; đồng thời cân bằng bảo mật với độ tin cậy, hiệu năng, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích nguyên tắc Zero Trust và lý do không thể coi mạng nội bộ, VPN hay vị trí workload là bằng chứng tin cậy.
2. Mô hình hóa trust boundary, tài sản, danh tính, luồng dữ liệu và đường tấn công trong kiến trúc cloud.
3. Áp dụng xác minh rõ ràng, quyền tối thiểu và giả định có thể đã bị xâm nhập cho người dùng, service, workload và thiết bị.
4. Thiết kế phòng vệ nhiều lớp ở identity, network, application, compute, data, supply chain và control plane.
5. Chọn kiểm soát xác thực, phân quyền, segmentation, mã hóa, quản lý secret, logging và detection theo rủi ro.
6. Đánh giá tác động bảo mật tới availability, hiệu năng, chi phí và vận hành; kiểm chứng bằng threat modeling, security testing và incident exercise.

## 1. Tại sao cần Zero Trust?

Ứng dụng cloud không còn nằm trong một mạng doanh nghiệp khép kín. Người dùng có thể truy cập từ thiết bị cá nhân, văn phòng, mạng di động hoặc nhà cung cấp bên ngoài. Workload có thể chạy ở nhiều region, account/subscription, cluster và nền tảng SaaS. Microservice giao tiếp qua mạng; dữ liệu được sao chép tới cache, queue, backup và hệ thống phân tích.

Trong môi trường đó, giả định "request đến từ mạng nội bộ thì an toàn" không còn đủ cơ sở. Một tài khoản có thể bị đánh cắp, container có thể bị xâm nhập, cấu hình firewall có thể sai hoặc một dependency đáng tin cậy có thể bị compromise.

**Zero Trust** là cách tiếp cận thiết kế trong đó không tự động tin cậy người dùng, thiết bị, workload hay kết nối chỉ vì chúng ở trong một mạng hoặc đã được xác thực trước đó. Mỗi yêu cầu truy cập tài nguyên phải được quyết định dựa trên danh tính, quyền, ngữ cảnh và chính sách phù hợp.

Zero Trust không phải một sản phẩm, appliance hay một lần bật MFA. Nó là tập nguyên tắc và kiến trúc kiểm soát liên tục:

- Xác minh danh tính và ngữ cảnh truy cập.
- Cấp quyền tối thiểu, giới hạn phạm vi và thời gian.
- Phân đoạn để giới hạn di chuyển ngang.
- Bảo vệ từng workload và dữ liệu.
- Ghi nhận, phát hiện và phản ứng với hành vi bất thường.
- Kiểm tra lại giả định khi trạng thái thiết bị, danh tính hoặc rủi ro thay đổi.

### 1.1. Perimeter truyền thống và Zero Trust

| Khía cạnh | Perimeter-based security | Zero Trust approach |
| --- | --- | --- |
| Ranh giới tin cậy | Chủ yếu dựa vào mạng nội bộ/biên ngoài | Ranh giới quanh tài nguyên, danh tính và luồng |
| Truy cập nội bộ | Thường tin cậy hơn sau VPN/firewall | Mỗi truy cập xác minh theo policy |
| Danh tính | Có thể tập trung ở login/network entry | User, device, workload và service identity |
| Quyền | Có thể rộng theo subnet/role | Least privilege, scoped và time-bound |
| Mạng | Tập trung phòng thủ ở perimeter | Segmentation và policy giữa các thành phần |
| Giám sát | Tập trung gateway/firewall | Telemetry xuyên identity, endpoint, workload và data |

Zero Trust không loại bỏ firewall, VPN hay network perimeter. Những kiểm soát đó vẫn hữu ích, nhưng không được xem là bằng chứng duy nhất để cấp quyền.

### 1.2. Ba nguyên tắc nền tảng

1. **Verify explicitly — xác minh rõ ràng:** quyết định truy cập dựa trên danh tính, thiết bị, tài nguyên, hành động và ngữ cảnh có liên quan.
2. **Use least privilege — quyền tối thiểu:** chỉ cấp quyền cần thiết, trong phạm vi và thời gian cần thiết; ưu tiên quyền tạm thời.
3. **Assume breach — giả định có thể đã bị xâm nhập:** thiết kế để phát hiện, cô lập và giảm thiệt hại ngay cả khi một thành phần đã bị compromise.

Ba nguyên tắc bổ sung cho nhau. MFA mà vẫn cấp quyền admin vĩnh viễn không phải least privilege. Network segmentation mà không xác thực service identity vẫn có thể cho phép workload giả mạo. Logging mà không có quy trình phản ứng không giúp giới hạn blast radius.

## 2. Mô hình hóa trust boundary và tài sản

Trước khi chọn công nghệ, phải biết điều gì cần bảo vệ, ai truy cập, dữ liệu đi đâu và điểm nào chuyển từ miền tin cậy này sang miền khác.

### 2.1. Xác định tài sản

Tài sản không chỉ là database:

- Dữ liệu khách hàng, thông tin thanh toán, hồ sơ định danh và dữ liệu tenant.
- Credential, API key, certificate, signing key, encryption key và token.
- Source code, container image, package, build artifact và pipeline.
- Workload identity, service account, cloud role và quyền control plane.
- API, queue, topic, object storage, backup, log và analytics export.
- DNS, domain, certificate, configuration, infrastructure-as-code và deployment workflow.
- Khả năng truy cập và vận hành hệ thống trong sự cố.

Đánh giá tài sản theo tính bảo mật (confidentiality), toàn vẹn (integrity), tính sẵn sàng (availability), nguồn gốc (provenance) và nghĩa vụ lưu trữ/xóa.

### 2.2. Trust boundary

Trust boundary là điểm mà dữ liệu, request hoặc quyền đi qua một miền có chính sách bảo mật khác. Ví dụ: Internet tới edge, edge tới application, service tới database, cloud account A tới account B, pipeline build tới production registry, hoặc production tới SaaS bên ngoài.

~~~mermaid
flowchart TB
    U["Người dùng / thiết bị"] --> EDGE["Edge: WAF / API gateway"]
    subgraph APP["Trust boundary: application"]
      API["Booking API"]
      WORKER["Background worker"]
    end
    subgraph DATA["Trust boundary: data"]
      DB[("Booking database")]
      OBJ[("Object storage")]
      Q["Message broker"]
    end
    IDP["Identity provider"] --> EDGE
    EDGE --> API
    API --> DB
    API --> Q
    Q --> WORKER
    WORKER --> DB
    WORKER --> OBJ
    EXT["External payment provider"] <--> API
~~~

Sơ đồ khái niệm. Mỗi luồng cần chỉ rõ chủ thể (user, workload, service, automation), tài nguyên (API, row, object, queue, secret), hành động (read, write, delete, publish, deploy, administer), ngữ cảnh (device posture, environment, risk, thời gian, tenant) và quyết định (allow, deny, step-up, limit hoặc require approval).

### 2.3. Phân loại dữ liệu và luồng

| Phân loại ví dụ | Kiểm soát thường cần |
| --- | --- |
| Public | Integrity, chống thay thế nội dung, availability |
| Internal | Authentication, authorization, encryption phù hợp |
| Confidential | Least privilege, encryption, audit, retention và hạn chế export |
| Restricted/regulated | Kiểm soát tăng cường, phân vùng, key management, data residency và quy trình phê duyệt |

Tên cấp độ trên chỉ là ví dụ. Tổ chức cần dùng taxonomy và yêu cầu pháp lý/hợp đồng được phê duyệt của mình.

Data flow mapping nên ghi nguồn, đích, protocol, classification, identity, encryption, nơi lưu log/backup và mục đích. Một bản sao trong data lake hoặc DLQ cũng chịu yêu cầu bảo vệ theo nội dung thực tế.

## 3. Identity-first: xác minh người dùng, thiết bị và workload

### 3.1. Human identity

Người dùng và quản trị viên nên được xác thực qua identity provider tập trung nếu phù hợp. Kiểm soát có thể gồm:

- MFA hoặc phương thức xác thực chống phishing phù hợp mức rủi ro.
- Single sign-on và lifecycle provisioning/deprovisioning.
- Conditional access theo danh tính, trạng thái thiết bị và risk signal.
- Step-up authentication cho thao tác nhạy cảm.
- Session lifetime, refresh token rotation và thu hồi phiên.
- Privileged access management và quyền admin tạm thời.
- Tách tài khoản thường dùng khỏi tài khoản quản trị.

Đăng nhập thành công chỉ chứng minh một mức độ kiểm soát danh tính tại thời điểm xác thực. Nó không có nghĩa user được phép truy cập mọi dữ liệu hoặc session tồn tại vô thời hạn.

### 3.2. Workload và service identity

Các service cần danh tính riêng, không nên dùng một credential dùng chung cho mọi workload. Có thể dùng managed identity, workload identity federation, service account hoặc certificate theo khả năng nền tảng.

Ví dụ:
- Booking API được quyền đọc secret cần thiết và ghi vào Booking DB.
- Notification worker chỉ đọc topic booking-events và gửi thông báo qua provider.
- Pipeline deploy được quyền cập nhật workload production theo phạm vi repo/environment đã phê duyệt.
- Backup job được quyền đọc dữ liệu cần backup và ghi vào backup vault; không có quyền tùy tiện sửa dữ liệu nguồn.

Không đặt cloud access key dài hạn trong image, file cấu hình, biến môi trường không được bảo vệ hoặc repository.

### 3.3. Token và claim không thay thế authorization

Token có thể mang subject, audience, issuer, expiry, scope, role và claim khác. Service phải xác minh issuer, signature, audience, expiry và điều kiện cần thiết trước khi tin claim. Không chấp nhận token chỉ vì nó được gửi trong mạng nội bộ.

Authorization phải kiểm tra hành động trên tài nguyên cụ thể. Vai trò authenticated không đồng nghĩa được đọc mọi booking. Tenant ID trong request body cũng không chứng minh người dùng có quyền với tenant đó.

### 3.4. Ví dụ luồng xác thực workload

~~~mermaid
sequenceDiagram
    participant W as Booking workload
    participant ID as Cloud identity provider
    participant API as Target service
    participant POL as Authorization policy
    W->>ID: Xin token theo workload identity
    ID-->>W: Short-lived access token
    W->>API: Request + token
    API->>API: Verify issuer, audience, expiry
    API->>POL: Evaluate subject, action, resource
    POL-->>API: Allow / Deny
    API-->>W: Kết quả có audit context
~~~

Flow chỉ minh họa khái niệm. Cơ chế token exchange, mTLS, federation và policy evaluation khác nhau theo nền tảng.

## 4. Least privilege và quản lý quyền

Least privilege có nghĩa chủ thể chỉ có quyền tối thiểu để hoàn thành công việc cụ thể. Áp dụng cho user, application, service account, deployment pipeline, support staff và automation.

### 4.1. RBAC, ABAC và policy-based access

| Mô hình | Cách quyết định | Khi hữu ích | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| RBAC | Theo role được gán | Quyền theo chức năng/nhóm | Role tích lũy quá nhiều quyền |
| ABAC | Theo thuộc tính subject, resource, action, context | Quy tắc theo tenant, classification, environment | Attribute sai/thiếu hoặc khó kiểm thử |
| ReBAC | Theo quan hệ chủ thể và tài nguyên | Chia sẻ dự án, tổ chức, quan hệ sở hữu | Quan hệ lan truyền ngoài ý muốn |
| Policy-based | Đánh giá policy tập trung | Quyết định phức tạp, cần audit | Policy quá phức tạp hoặc khó vận hành |

Có thể kết hợp các mô hình. RBAC quản lý vai trò cơ bản; ABAC bổ sung điều kiện như tenant_id, data classification hoặc environment.

### 4.2. Ví dụ policy khái niệm

~~~text
ALLOW read booking
WHEN
  subject.role IN ["booking-support", "booking-owner"]
  AND subject.tenant_id == resource.tenant_id
  AND resource.classification <= subject.clearance
  AND request.environment == "production"

DENY delete booking
UNLESS
  subject has approved break-glass grant
  AND approval is valid
  AND action is audited
~~~

Đây là pseudo-policy để giải thích. Triển khai thực tế cần cú pháp, semantics, thứ tự deny/allow, xử lý default-deny và test case theo policy engine được chọn.

### 4.3. Quyền tạm thời và break-glass

Quyền quản trị nên được cấp theo yêu cầu, có thời hạn, người phê duyệt và audit. Break-glass dành cho tình huống khẩn cấp khi quy trình bình thường không dùng được. Nó cần tài khoản/đường truy cập được bảo vệ đặc biệt, MFA mạnh, phạm vi quyền và thời hạn rõ, cảnh báo khi sử dụng, review sau sự cố và thu hồi credential nếu cần.

Không nên tạo một tài khoản super-admin vĩnh viễn dùng chung cho cả đội.

## 5. Phòng vệ nhiều lớp (Defense in Depth)

Defense in depth nghĩa là nhiều kiểm soát bổ sung bảo vệ tài sản ở các lớp khác nhau. Nếu một lớp bị vượt qua, lớp khác vẫn có thể phát hiện, chặn hoặc giảm hậu quả.

~~~mermaid
flowchart TB
    L1["1. Identity: MFA, workload identity, authorization"]
    L2["2. Edge: WAF, DDoS, rate limit, API validation"]
    L3["3. Network: segmentation, private endpoints, egress control"]
    L4["4. Workload: hardened image, runtime policy, patching"]
    L5["5. Application: input validation, secure session, secrets"]
    L6["6. Data: encryption, access policy, backup, audit"]
    L7["7. Detection & response: logs, alerts, incident playbooks"]
    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7
~~~

Các lớp không phải lúc nào cũng đi theo trình tự request. Defense in depth cũng không có nghĩa phải mua thật nhiều sản phẩm. Kiểm soát trùng lặp nhưng không có owner, không tích hợp log hoặc tạo false positive cao có thể tăng chi phí mà không tăng hiệu quả.

| Lớp | Mục tiêu | Ví dụ kiểm soát |
| --- | --- | --- |
| Identity | Đúng chủ thể, đúng quyền | MFA, federation, short-lived token, RBAC/ABAC |
| Edge | Lọc request và traffic độc hại | WAF, DDoS protection, rate limit, bot policy |
| Network | Giới hạn đường đi | VPC/VNet segmentation, private endpoint, firewall, egress policy |
| Workload | Giảm bề mặt runtime | Hardened image, patching, non-root, seccomp, admission policy |
| Application | Bảo vệ logic và session | Input validation, output encoding, CSRF protection, authorization |
| Data | Bảo vệ nội dung và tính toàn vẹn | Encryption, key management, row/object policy, backup |
| Detection/response | Nhận biết và giới hạn sự cố | Audit, SIEM, alerting, incident response |

Mỗi kiểm soát cần owner, policy, phương pháp kiểm thử và bằng chứng hiệu lực. WAF có thể chặn payload phổ biến nhưng không thay thế authorization theo tenant ở application.

## 6. Network segmentation và kiểm soát east-west traffic

### 6.1. North-south và east-west

- **North-south traffic:** lưu lượng đi vào/ra hệ thống, ví dụ client tới API gateway hoặc ứng dụng tới partner API.
- **East-west traffic:** giao tiếp giữa service, workload, database, broker và thành phần nội bộ.

Firewall perimeter giúp kiểm soát north-south, nhưng cần segmentation cho east-west. Nếu một pod bị chiếm quyền và mọi subnet/port đều mở, attacker có thể di chuyển ngang tới database hoặc control plane.

### 6.2. Mô hình phân đoạn

Có thể phân đoạn theo environment, trust level, workload identity, data classification, tenant/cell, region/account/subscription và môi trường DR.

~~~mermaid
flowchart TB
    INTERNET["Internet"] --> WAF["WAF / public ingress"]
    WAF --> APPNET["Application network"]
    subgraph APP["Application workloads"]
      API["Public API"]
      WORKER["Private worker"]
    end
    WAF --> API
    API --> DATA["Restricted data network"]
    WORKER --> DATA
    subgraph DATAS["Data services"]
      DB[("Database")]
      STORE[("Object storage")]
      BROKER["Broker"]
    end
    DATA --> DB
    DATA --> STORE
    DATA --> BROKER
    ADMIN["Privileged admin path"] --> MGMT["Management plane"]
~~~

Mạng chỉ là một lớp segmentation. Cần xác minh identity và authorization tại dịch vụ đích; không tự động cho phép truy cập DB chỉ vì source IP thuộc subnet ứng dụng.

### 6.3. Default deny và egress control

Chính sách phù hợp thường bắt đầu bằng deny-by-default giữa các miền nhạy cảm, sau đó mở những luồng cụ thể đã có owner. Egress control hạn chế workload gọi tùy tiện ra Internet, giảm nguy cơ exfiltration và command-and-control.

Cần lập allowlist theo domain/IP/protocol khi phù hợp, private endpoint cho dịch vụ cloud, DNS policy, logging và quy trình cập nhật. Tránh allowlist IP cứng nếu provider dùng dải động mà không có cơ chế duy trì.

Network policy cần test cả traffic được phép lẫn bị chặn. Default-deny sai có thể làm gián đoạn DNS, telemetry, secret retrieval hoặc backup.

## 7. Bảo vệ application và API

Network controls không thể thay thế kiểm soát tại tầng ứng dụng. Application là nơi hiểu business semantics, ownership và quyền trên từng đối tượng.

Các kiểm soát cần có:
- Authentication và authorization cho từng endpoint/resource.
- Server-side validation; không tin dữ liệu hoặc quyền do client tự gửi.
- Output encoding và parameterized queries để giảm injection.
- Chống CSRF khi dùng cookie-based browser session, theo mô hình ứng dụng.
- Session/token lifecycle, cookie Secure/HttpOnly/SameSite phù hợp.
- Rate limit theo danh tính/tenant/endpoint và chống abuse.
- Idempotency cho thao tác tạo side effect.
- CORS chỉ mở origin/method/header cần thiết; CORS không phải authorization.
- Error response không để lộ stack trace, secret hoặc cấu trúc nội bộ.
- Dependency validation và security headers phù hợp.

### 7.1. API authorization theo object

Một lỗi phổ biến là kiểm tra user đã login nhưng không kiểm tra user đó có quyền với object ID được yêu cầu. Ví dụ GET /bookings/123 có thể bị khai thác để đọc booking của khách hàng khác nếu chỉ dựa vào ID.

Quyết định truy cập cần kiểm tra subject, action, resource ownership/tenant, classification và trạng thái business. Test phải bao gồm:
- User A đọc object A: allow.
- User A đọc object B thuộc tenant khác: deny.
- Service role không được phép thực hiện action nhạy cảm: deny.
- Token hết hạn hoặc sai audience: deny.
- Tenant context bị sửa từ client: không làm thay đổi quyền.

### 7.2. API gateway là điểm kiểm soát, không phải ranh giới duy nhất

Gateway có thể áp dụng authentication sơ bộ, routing, TLS, rate limit và WAF. Service đích vẫn phải kiểm tra authorization ở phạm vi dữ liệu/nghiệp vụ. Nếu gateway bị cấu hình sai hoặc một service được gọi trực tiếp, policy ở application mới bảo vệ được object.

## 8. Bảo vệ workload, container và compute

Workload cần được coi là một principal có danh tính và một môi trường có thể bị xâm nhập.

- Chạy container non-root và không cấp privileged mode nếu không có lý do được duyệt.
- Drop Linux capabilities không cần; giới hạn syscall bằng seccomp hoặc cơ chế tương đương.
- Dùng read-only root filesystem và volume ghi rõ mục đích.
- Pin image theo digest hoặc version bất biến; xác minh provenance/signature khi pipeline hỗ trợ.
- Quét image và dependency; có SLA xử lý vulnerability theo risk.
- Hạn chế metadata service access và credential exposure.
- Dùng workload identity thay credential dùng chung.
- Segment network và giới hạn egress.
- Áp resource requests/limits, quota và isolation theo workload.
- Patch base image, runtime, node OS và control plane theo trách nhiệm shared responsibility.

### 8.1. Admission và runtime policy

Trong Kubernetes, có thể dùng Pod Security Standards/admission controls, policy engine hoặc cơ chế tương đương để từ chối workload có cấu hình nguy hiểm: privileged container, hostPath không được phép, chạy root, host network hoặc image từ registry không tin cậy.

Policy cần baseline rõ ràng, ngoại lệ có owner/thời hạn, CI validation trước deploy, enforcement ở production admission, audit khi vi phạm và quy trình cập nhật an toàn tránh chặn nhầm toàn bộ deployment.

Managed application platform có thể cung cấp abstraction khác; hãy xác minh giới hạn runtime thay vì giả định có cùng khả năng cấu hình Kubernetes.

## 9. Bảo vệ dữ liệu và quản lý khóa

### 9.1. Encryption in transit và at rest

Mã hóa khi truyền giúp bảo vệ dữ liệu trên đường mạng; mã hóa khi lưu giúp giảm nguy cơ lộ dữ liệu khi storage bị truy cập trái phép. Tuy nhiên encryption không thay thế authorization: workload có quyền đọc dữ liệu và key vẫn có thể giải mã nội dung.

Thiết kế cần làm rõ TLS/mTLS giữa client, gateway, service, database, broker và provider; encryption at rest cho DB, object storage, queue, snapshot, backup và log; ai sở hữu và quản lý key; key rotation, revocation, recovery; separation of duties và cách vận hành khi KMS unavailable.

### 9.2. Key management

Key management cần lifecycle đầy đủ: tạo, phân quyền, sử dụng, rotation, backup/recovery theo policy, thu hồi và audit. Không tự triển khai thuật toán mã hóa hoặc lưu key trong source code.

Envelope encryption thường dùng data encryption key (DEK) để mã hóa dữ liệu và key-encryption key (KEK) được quản lý bởi KMS/HSM để bảo vệ DEK. Chi tiết phụ thuộc dịch vụ và chuẩn tổ chức.

### 9.3. Backup và immutable recovery

Backup là tài sản bảo mật quan trọng; attacker có thể xóa hoặc mã hóa backup cùng production nếu cùng quyền quản trị. Cân nhắc tách account/project/vault và quyền xóa; immutable/WORM retention; MFA/approval cho thao tác phá hủy; mã hóa, audit; restore test; bảo vệ metadata, catalog và cấu hình cần phục hồi.

Backup không được coi là dùng được chỉ vì job báo success. Phải chứng minh restore và ứng dụng có thể đọc/ghi đúng sau phục hồi.

## 10. Secrets, certificate và credential lifecycle

Secret có thể là password, API key, signing key, database credential, certificate private key hoặc token. Mọi secret cần owner, purpose, quyền đọc, nơi lưu, hạn dùng/rotation và phương thức thu hồi.

Nguyên tắc:
- Dùng secret manager hoặc vault; không commit secret vào repository.
- Cấp secret lúc runtime qua identity, tránh bake vào image.
- Dùng credential riêng cho mỗi service/environment.
- Ưu tiên short-lived token/certificate thay key dài hạn.
- Rotation có overlap hợp lệ để rollout không gây downtime.
- Không ghi secret vào log, trace, exception hay CI artifact.
- Audit secret retrieval và phát hiện truy cập bất thường.
- Có quy trình revoke khẩn cấp và thay credential sau sự cố.

Certificate lifecycle cũng cần tự động hóa renew, expiry monitoring, trust chain và kiểm tra client-to-edge lẫn edge-to-origin/service-to-service. Certificate hết hạn là lỗi bảo mật lẫn availability.

## 11. Bảo mật supply chain và CI/CD

Pipeline build/deploy có thể thay đổi production nên là mục tiêu giá trị cao. Nếu attacker chiếm source repository, build runner, registry hoặc deployment credential, họ có thể phát hành image chứa mã độc.

### 11.1. Các lớp bảo vệ

1. **Source:** branch protection, code review, MFA, quyền repo tối thiểu và dependency policy.
2. **Build:** runner cô lập, ephemeral khi phù hợp, secret scope hẹp và pin toolchain/dependency.
3. **Artifact:** SBOM, provenance, image scanning, signing và immutable digest.
4. **Registry:** private access, retention, replication policy và audit pull/push.
5. **Deployment:** workload identity ngắn hạn, environment approval theo risk, policy-as-code.
6. **Runtime:** chỉ cho phép artifact/registry tin cậy, admission verification nếu hỗ trợ.
7. **Response:** thu hồi token, khóa pipeline, quarantine artifact, redeploy known-good version và kiểm tra blast radius.

~~~mermaid
flowchart LR
    SRC["Source commit"] --> REVIEW["Review + branch protection"]
    REVIEW --> BUILD["Isolated build"]
    BUILD --> TEST["Unit / integration / security tests"]
    TEST --> SBOM["SBOM + provenance"]
    SBOM --> SIGN["Sign artifact"]
    SIGN --> REG["Private registry"]
    REG --> APPROVE["Policy + environment approval"]
    APPROVE --> DEPLOY["Deploy by immutable digest"]
    DEPLOY --> VERIFY["Runtime verification + telemetry"]
~~~

Không để build runner có quyền admin toàn bộ cloud account. Tách identity build/test/deploy và giới hạn thời gian credential giúp giảm hậu quả khi job bị compromise.

### 11.2. Dependency và software composition

Dependency scanner giúp phát hiện package có CVE, license hoặc nguồn không mong muốn. Số lượng CVE không đủ để quyết định: cần xem exploitability, runtime reachability, exposure, data sensitivity và mitigating controls. Ngoại lệ phải có owner, lý do, thời hạn và kế hoạch xử lý.

## 12. Bảo vệ cloud control plane và configuration

Control plane quản lý resource, identity, network, key, logging, cluster và chính sách. Một tài khoản có quyền thay đổi control plane có thể vô hiệu hóa nhiều lớp bảo vệ.

Các kiểm soát:
- Root/owner account bảo vệ đặc biệt, MFA mạnh và hạn chế sử dụng thường ngày.
- Tách account/project/subscription theo môi trường, team hoặc trust boundary khi có lợi.
- Quyền IAM theo least privilege, role assumption và short-lived access.
- Audit thay đổi quan trọng; cảnh báo khi logging, encryption, network policy hoặc backup bị tắt.
- Infrastructure as Code được review, test, version control và drift detection.
- SCP/organization policy hoặc guardrail tương đương để ngăn cấu hình vượt chính sách.
- Break-glass có kiểm soát; không khóa đường khôi phục hợp lệ.
- Kiểm soát quota, region allowlist, public resource exposure và quyền chia sẻ cross-account.

Một cấu hình an toàn có thể bị làm yếu bởi một lần thay đổi console ngoài quy trình. IaC và drift detection giúp làm rõ trạng thái mong muốn và thực tế.

## 13. Detection, logging và response

Zero Trust và defense in depth yêu cầu phát hiện hành vi bất thường, không chỉ chặn request. Telemetry cần nối được danh tính, workload, resource và hành động.

### 13.1. Log cần có gì?

- Authentication success/failure, MFA/step-up, session và token events.
- Authorization decision, policy version và resource classification phù hợp.
- IAM/role/key/secret changes và privileged access.
- Network policy, WAF, firewall, DNS và egress events.
- Deployment, image digest, provenance, admission decision và configuration change.
- Data access/export/delete, backup/restore và security-relevant events.
- Detection finding, incident timeline và response action.

Log phải tránh lưu password, raw token, private key hoặc PII không cần thiết. Phân quyền log store, retention, integrity và vị trí lưu cũng phải được thiết kế.

### 13.2. Detection use cases

| Tín hiệu | Điều có thể chỉ ra | Hành động điều tra |
| --- | --- | --- |
| User login từ ngữ cảnh bất thường | Credential compromise hoặc hành vi hợp lệ cần xác minh | Risk evaluation, MFA step-up, session review |
| Workload đọc secret ngoài pattern | Compromised service hoặc policy quá rộng | Kiểm tra identity, deploy, trace, secret usage |
| Một service gọi port/topic ngoài dependency map | Lateral movement hoặc cấu hình sai | Deny/contain, kiểm tra flow và workload |
| Thay đổi IAM admin hoặc tắt audit | Privilege escalation hoặc thao tác nguy hiểm | Escalate, preserve evidence, verify change owner |
| Data export tăng đột biến | Data exfiltration hoặc tác vụ hợp lệ bất thường | Data owner review, query/job audit |
| Image digest ngoài pipeline tin cậy | Supply-chain compromise | Block/quarantine, tìm nơi đã deploy |
| Backup deletion/retention change | Tấn công phá khả năng khôi phục | Protect vault, break-glass review, incident response |

### 13.3. Incident response

Runbook nên mô tả:
1. Phân loại severity và người có thẩm quyền chỉ huy.
2. Xác nhận scope: user, workload, account, data, region và dependency.
3. Containment: revoke token, disable principal, isolate workload, block egress hoặc freeze deployment.
4. Preserve evidence và giữ audit/log theo quy định.
5. Eradication: rebuild image, rotate secrets/keys, fix policy/config và remove persistence.
6. Recovery: deploy known-good artifact, restore data nếu cần, verify identity/network/data controls.
7. Post-incident: đánh giá blast radius, notification/legal obligations, lessons và remediation owner.

Containment cần cân bằng availability và tính toàn vẹn. Thu hồi key dùng chung có thể làm hàng trăm service ngừng hoạt động; cần biết phạm vi ảnh hưởng và có đường rotation an toàn.

## 14. Threat modeling để chọn kiểm soát đúng

Threat modeling giúp nhóm xem xét có hệ thống cách hệ thống có thể bị tấn công. Có thể dùng STRIDE, attack tree hoặc phương pháp nội bộ.

### 14.1. Các bước

1. Xác định tài sản và mục tiêu an ninh.
2. Vẽ data flow và trust boundary.
3. Liệt kê chủ thể, entry point, protocol và quyền.
4. Xác định threat theo confidentiality, integrity, availability và nghĩa vụ khác.
5. Đánh giá likelihood/impact và kiểm soát hiện có.
6. Chọn mitigation; ghi residual risk, owner và deadline.
7. Kiểm thử và cập nhật khi kiến trúc thay đổi.

### 14.2. Ví dụ threat model cho API đặt chỗ

| Threat | Tài sản/đường tấn công | Kiểm soát |
| --- | --- | --- |
| Spoofing | Giả danh client/service | MFA, token validation, workload identity, mTLS |
| Tampering | Sửa booking hoặc event | Authorization, integrity checks, signed artifact/event khi phù hợp |
| Repudiation | Không xác định ai đổi trạng thái | Audit có actor, correlation ID và integrity |
| Information disclosure | Đọc booking tenant khác | Object-level authorization, DB policy, cache isolation |
| Denial of service | Flood API hoặc worker queue | WAF/rate limit, quota, backpressure, capacity |
| Elevation of privilege | Workload lấy quyền admin | Least privilege, short-lived identity, admission/runtime controls |

STRIDE giúp phân loại threat, nhưng không tự đưa ra xác suất hay mức rủi ro. Cần xem implementation và bối cảnh thực.

### 14.3. Security test phải kiểm tra đường bị từ chối

Ngoài happy path, cần kiểm tra truy cập tài nguyên tenant khác; token sai audience/issuer, hết hạn hoặc bị thu hồi; workload gọi dependency không được phép; pod/image chạy privilege ngoài policy; API dùng method/parameter bất thường; secret bị rotate; artifact không có provenance hợp lệ; log/export không lộ dữ liệu nhạy cảm.

## 15. Tình huống thực tế: SaaS đặt chỗ đa tenant trên cloud

Một SaaS phục vụ nhiều doanh nghiệp có web/mobile client qua CDN/WAF/API gateway; Booking, Inventory, Payment và Notification services; database giao dịch, object storage, broker; Kubernetes cho một số workload và managed container platform cho worker; CI/CD, registry, secret manager và SaaS bên ngoài.

Yêu cầu: ngăn truy cập chéo tenant; giới hạn tác động khi service bị compromise; cho phép đội vận hành xử lý production có audit; giữ booking hoạt động khi notification provider gặp lỗi.

~~~mermaid
flowchart TB
    USER["User + device context"] --> IDP["Identity provider / MFA"]
    IDP --> EDGE["WAF + API gateway"]
    EDGE --> AUTHZ["Application authorization"]
    AUTHZ --> BK["Booking service identity"]
    BK --> INV["Inventory service identity"]
    BK --> PAY["Payment boundary"]
    BK --> DB[("Tenant-aware booking data")]
    BK --> OUT["Outbox"]
    OUT --> BR["Private broker"]
    BR --> NOTI["Notification worker identity"]
    NOTI --> MSG["Email/SMS provider"]
    SEC["Security monitoring / SIEM"] -. "Identity, network, data, deployment logs" .-> OBS["Central audit and response"]
    BK -.-> OBS
    INV -.-> OBS
    PAY -.-> OBS
    NOTI -.-> OBS
~~~

### 15.1. Kiểm soát theo luồng

| Luồng | Kiểm soát |
| --- | --- |
| User → API | MFA/SSO theo policy, TLS, WAF, rate limit và token validation |
| API → Booking service | Service identity, authorization và trace correlation |
| Booking → Inventory | mTLS/identity, quyền reservation API, timeout |
| Booking → Database | Private endpoint, DB identity, quyền schema/operation tối thiểu |
| Booking → Broker | Producer-only permission trên topic cần thiết |
| Worker → Broker | Consumer-only permission, tenant context được kiểm soát |
| Worker → Email/SMS | Egress allowlist, secret riêng, quota |
| Operator → Production | JIT privilege, approval, MFA, session/audit |
| CI/CD → Runtime | Artifact provenance, image digest, deploy identity scoped |

### 15.2. Kiểm chứng

- User tenant A không thể đọc/sửa booking tenant B qua API hoặc query path.
- Notification outage không làm mất booking đã commit; outbox được retry an toàn.
- Booking service không thể đọc secret Payment hoặc quản trị cluster.
- Image ngoài pipeline tin cậy bị từ chối triển khai.
- Thao tác break-glass phát cảnh báo, được audit và thu hồi đúng hạn.
- Egress không cần thiết từ worker bị chặn; telemetry vẫn hoạt động.
- Restore backup có thể đọc bằng identity phục hồi đã phê duyệt.

## 16. Đánh đổi: bảo mật, availability, hiệu năng và chi phí

| Quyết định | Lợi ích | Đánh đổi/rủi ro |
| --- | --- | --- |
| MFA/step-up cho hành động nhạy cảm | Giảm rủi ro credential compromise | Thêm bước tương tác, recovery và hỗ trợ |
| Short-lived token | Giảm thời gian credential bị lộ có thể bị lạm dụng | Phụ thuộc identity service/refresh flow |
| mTLS/service identity | Xác minh workload hai chiều | Certificate lifecycle và troubleshooting |
| Default-deny egress | Giảm data exfiltration | Cần quản lý allowlist và dependency |
| Strict network segmentation | Giới hạn lateral movement | Tăng phức tạp DNS, connectivity và policy |
| Centralized logging | Tăng khả năng điều tra | Chi phí, privacy, retention và access control |
| Image verification/admission | Chặn artifact không tin cậy | Pipeline/registry outage có thể chặn deploy |
| Multi-account isolation | Giảm blast radius | Thêm IAM, network và vận hành liên account |

### 16.1. Tránh tạo một điểm lỗi chung mới

Central identity, KMS, policy engine và logging có giá trị nhưng cũng có thể trở thành dependency quan trọng. Thiết kế phải xem:
- Điều gì xảy ra khi identity provider hoặc KMS unavailable?
- Workload đang chạy có tiếp tục với token/secret đã cấp trong giới hạn an toàn không?
- Có cơ chế cache/renewal hợp lệ và thời hạn rõ không?
- Có break-glass cho quản trị khẩn cấp nhưng không mở quyền thường ngày không?
- Policy engine lỗi thì default-deny hay degraded behavior nào được phép?
- Log collector lỗi có làm request nghiệp vụ thất bại không?

Không bypass bảo mật để giữ uptime. Hãy xác định thao tác nào cần fail closed, thao tác nào có thể dùng trạng thái đã xác minh trong thời gian giới hạn và thao tác nào có thể xếp hàng chờ.

## 17. Đo lường hiệu quả bảo mật

| Mục tiêu | Chỉ số ví dụ | Cách diễn giải |
| --- | --- | --- |
| Identity | MFA coverage, stale account, privileged standing access | Chủ thể nào chưa theo policy? |
| Least privilege | Excess permission, unused privilege, JIT duration | Quyền có rộng/dài hơn cần thiết? |
| Workload | Image provenance coverage, vulnerability remediation age | Artifact nào chưa xác minh hoặc còn lỗ hổng? |
| Network | Unknown flows, denied egress anomalies, exposed endpoints | Có luồng bất thường hoặc public resource không mong muốn? |
| Data | Encryption coverage, access anomalies, retention exceptions | Dữ liệu được bảo vệ và truy cập có đúng? |
| Detection | Time to detect, time to contain, incident recurrence | Phát hiện và giới hạn sự cố có hiệu quả? |
| Recovery | Restore success, key recovery test, backup immutability | Có thể phục hồi đáng tin cậy? |
| Delivery | Policy violations in pipeline, emergency bypass count | Kiểm soát có tích hợp vào delivery? |

Không tối ưu metric bằng cách giảm số alert bằng mọi giá. Cần đo chất lượng detection, false positive, coverage tài sản quan trọng và sự cố không được phát hiện. Metric phải có định nghĩa, nguồn, owner và kỳ đo.

## 18. Architecture Decision Record mẫu

~~~markdown
# ADR-072: Áp dụng Zero Trust cho service-to-service trong nền tảng đặt chỗ

Trạng thái: Đề xuất / chấp thuận có điều kiện
Decision owner: Security Architect + Platform + Application owner
Ngày: YYYY-MM-DD

Bối cảnh:
- Nhiều service và workload chạy trên các nền tảng khác nhau.
- Mạng nội bộ hiện được xem là vùng tương đối tin cậy.
- Một số workload dùng credential chung và quyền rộng.
- SaaS có dữ liệu đa tenant.

Mục tiêu:
- Xác minh workload identity cho luồng nhạy cảm.
- Giới hạn quyền theo service, tenant, resource và action.
- Giảm lateral movement và credential lifetime.
- Ghi audit để phát hiện và điều tra.

Phương án:
A. Tiếp tục dựa chủ yếu vào network perimeter.
B. Workload identity + least privilege + segmentation từng bước.
C. Buộc chuyển toàn bộ traffic sang service mesh ngay.

Quyết định đề xuất:
- Chọn B; ưu tiên Booking, Payment, database và broker.
- Dùng short-lived identity, policy cụ thể và default-deny
  có kiểm thử cho từng trust boundary.
- Bổ sung telemetry và runbook trước khi mở rộng.

Đánh đổi:
- Cần certificate/token lifecycle, policy ownership và migration.
- Lỗi identity/policy có thể ảnh hưởng availability.

Bằng chứng nghiệm thu:
- Negative authorization tests và cross-tenant tests.
- Workload không đọc secret/endpoint ngoài phạm vi.
- Key/credential rotation không gây outage.
- Incident exercise chứng minh containment và audit.

Điều kiện xem xét lại:
- Workload/tenant mới, threat model thay đổi,
  policy false positive cao hoặc SLO bị ảnh hưởng.
~~~

ADR cần đính kèm data flow, threat model, policy owner, security test results và kế hoạch rollback. Không triển khai thay đổi identity/network rộng khắp cùng lúc nếu chưa biết dependency.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tin mạng nội bộ/VPN là an toàn | Lateral movement sau khi thiết bị/workload bị chiếm | Xác minh danh tính và quyền từng tài nguyên |
| Bật MFA rồi coi đã áp dụng Zero Trust | Quyền rộng và workload identity không được kiểm soát | Kết hợp verify explicitly, least privilege, assume breach |
| Gateway xác thực rồi service bỏ authorization | BOLA/cross-tenant data exposure | Kiểm tra object/tenant/action ở service/data layer |
| Dùng một credential cho nhiều workload | Khó truy vết và blast radius lớn | Identity riêng, short-lived credential |
| Chỉ mã hóa storage | Dữ liệu vẫn bị principal có quyền rộng đọc | Authorization, key governance và audit |
| Default-deny không có dependency map | DNS, telemetry, secret hoặc backup bị chặn | Inventory luồng, test allow/deny và change process |
| Mua nhiều security tool rời rạc | Alert fatigue và log phân mảnh | Tích hợp telemetry và owner cho từng control |
| Không bảo vệ CI/CD và registry | Artifact độc hại được deploy với quyền hợp lệ | Isolated build, provenance, signing và scoped deploy identity |
| Backup cùng quyền admin production | Attacker phá cả bản sao phục hồi | Tách vault/account, immutability và approval |
| Log lưu raw token/PII | Hệ thống audit trở thành nguồn rò rỉ | Redaction, access/retention policy |
| Fail closed mọi tình huống mà không phân tích | Identity/KMS outage gây gián đoạn rộng | Degraded behavior theo risk và action |
| Fail open để giữ availability | Truy cập trái phép khi policy service lỗi | Default policy rõ; fail closed cho thao tác nhạy cảm |
| Không test negative path | Chỉ chứng minh user hợp lệ hoạt động | Test deny, expired token, tenant mismatch và privilege abuse |
| Không có owner/policy lifecycle | Policy drift và ngoại lệ tồn tại vô thời hạn | Owner, review date, expiry và audit |

## 20. Bài tập thực hành

Một nền tảng SaaS đặt chỗ chạy trên cloud có nhiều tenant. Kiến trúc gồm API gateway, Booking service, Payment service, Inventory service, database, object storage, broker, Kubernetes cluster, CI/CD và SaaS bên ngoài. Hiện các service dùng một số credential chia sẻ; subnet ứng dụng có thể truy cập database và broker khá rộng; support engineer có quyền production cố định. Product cần duy trì checkout, Security yêu cầu giảm nguy cơ truy cập chéo tenant.

Hãy thực hiện:

1. Liệt kê tài sản, data classification và trust boundary; vẽ data flow giữa client, gateway, services, database, broker và SaaS.
2. Viết threat model theo STRIDE hoặc phương pháp tương đương; ưu tiên ít nhất sáu threat có owner.
3. Thiết kế human identity, workload identity, token validation và JIT privileged access.
4. Định nghĩa RBAC/ABAC policy cho đọc booking theo tenant; viết ít nhất năm test case allow/deny.
5. Thiết kế network segmentation, egress allowlist và service-to-service authentication; nêu cách triển khai tránh outage.
6. Chọn kiểm soát cho container image, registry, CI/CD, secrets, certificate và cloud control plane.
7. Thiết kế encryption/key lifecycle, backup isolation, data retention và audit.
8. Mô tả detection use cases và incident response khi workload bị compromise hoặc secret bị lộ.
9. Đánh giá identity provider/KMS unavailable; xác định hành vi fail-closed/degraded theo mức rủi ro.
10. Đề xuất metrics và phép thử chứng minh Zero Trust cải thiện bảo mật mà không phá SLO checkout.
11. Viết ADR gồm lựa chọn, đánh đổi, residual risk, migration order, rollback và điều kiện xem xét lại.

**Tiêu chí tự đánh giá:** giải pháp tốt không chỉ thêm firewall, MFA hoặc service mesh. Nó xác định chủ thể, tài nguyên, quyền và trust boundary; kiểm tra đường cho phép lẫn đường bị từ chối; giảm quyền và blast radius; có detection/response; và chứng minh hoạt động đúng khi có lỗi.

## 21. Checklist rà soát Zero Trust và defense in depth

- [ ] Tài sản, data classification, owner và source of truth được xác định.
- [ ] Data flow/trust boundary gồm user, device, workload, partner và control plane.
- [ ] Không có quyền truy cập chỉ vì request đến từ mạng nội bộ.
- [ ] Human identity có MFA/conditional access phù hợp; lifecycle account rõ.
- [ ] Mỗi workload có identity riêng, credential ngắn hạn và least privilege.
- [ ] Token kiểm tra issuer, signature, audience, expiry và scope cần thiết.
- [ ] Authorization kiểm tra action, resource, ownership/tenant và classification.
- [ ] Quyền admin JIT/break-glass có approval, audit, expiry và review.
- [ ] East-west segmentation, egress control và default-deny có kiểm thử.
- [ ] Application/API có validation, object-level authorization và rate limiting.
- [ ] Container/runtime được harden; image có provenance và vulnerability policy.
- [ ] CI/CD, registry, artifact signing và deploy identity được bảo vệ.
- [ ] Secret/certificate/key có lifecycle, rotation, revocation và audit.
- [ ] Data encryption, backup isolation, retention và restore được kiểm chứng.
- [ ] Cloud control plane có guardrails, audit và drift detection.
- [ ] Logs được redaction, phân quyền, bảo vệ integrity và lưu đúng vùng.
- [ ] Detection use case, incident runbook và escalation owner đã rõ.
- [ ] Threat model và negative security tests cập nhật theo thay đổi kiến trúc.
- [ ] Dependency identity/KMS/policy có kế hoạch availability và degraded mode.
- [ ] ADR ghi đánh đổi, residual risk, rollout/rollback và trigger review.

## Ghi nhớ

**Zero Trust** yêu cầu xác minh từng chủ thể và quyền truy cập theo ngữ cảnh; **defense in depth** bố trí nhiều lớp kiểm soát bổ sung để ngăn chặn, phát hiện và giảm hậu quả khi một lớp thất bại. Mạng nội bộ, VPN, gateway, Kubernetes hay cloud provider không tự tạo ra niềm tin tuyệt đối.

Một kiến trúc bảo mật cloud tốt kết hợp **identity, least privilege, segmentation, application authorization, workload hardening, data protection, supply-chain security, detection và response**. Mọi kiểm soát phải gắn với tài sản và threat cụ thể, có owner và được kiểm chứng trong điều kiện vận hành thật. Bảo mật chỉ bền vững khi đồng thời giữ được tính đúng đắn, độ sẵn sàng, hiệu năng, khả năng mở rộng và chi phí chấp nhận được.
