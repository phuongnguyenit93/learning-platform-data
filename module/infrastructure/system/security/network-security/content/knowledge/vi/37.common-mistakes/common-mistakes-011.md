# Phụ thuộc vào IP thay vì identity — Sai lầm trong bảo mật mạng hiện đại

Một công ty cho phép dải `10.20.0.0/16` truy cập cơ sở dữ liệu vì cho rằng “đó là mạng của đội ứng dụng”. Sau vài tháng, subnet này chứa thêm máy CI, Pod Kubernetes, máy thử nghiệm và một workstation bị chiếm quyền. Firewall vẫn cho phép toàn bộ dải tới TCP/5432, mặc dù chỉ dịch vụ `orders-api` có nhu cầu nghiệp vụ. Khi xảy ra truy cập bất thường, log chỉ hiển thị IP nguồn của NAT gateway; nhóm điều tra không xác định được **workload nào** đã mở kết nối.

Ở ví dụ khác, doanh nghiệp yêu cầu “chỉ IP văn phòng mới vào được trang quản trị”. Nhân viên làm việc từ xa phải đi qua VPN có địa chỉ egress chung; một tài khoản bị đánh cắp dùng cùng VPN exit IP cũng được firewall cho qua. Cùng lúc, một nhân viên hợp lệ đổi mạng Wi-Fi và bị từ chối dù đã xác thực MFA thành công. **Quy tắc theo IP vừa có thể quá rộng, vừa có thể chặn sai người.**

Sai lầm cốt lõi là **lấy địa chỉ định tuyến làm bằng chứng danh tính hoặc quyền truy cập**. IP là thông tin hữu ích cho chuyển tiếp gói, phân đoạn mạng, phát hiện bất thường và kiểm soát tiền xác thực; nhưng IP **không tự chứng minh ai đang dùng thiết bị, ứng dụng nào tạo kết nối, tài khoản có quyền hay request được phép làm gì**.

Trong chương **Sai lầm thường gặp** thuộc module **SECURITY_NETWORK_SECURITY**, bài này giúp thiết kế phòng vệ nhiều lớp: vẫn giữ firewall/ACL, VPN, network segmentation, DNS protection, IDS/IPS, cloud networking và logging, nhưng thêm **user/device/workload identity đã được xác minh, authorization theo tài nguyên, chính sách tối thiểu và giám sát liên tục**.

> **Nguyên tắc quan trọng:** **IP trả lời “traffic đến từ/đi tới đâu theo một điểm quan sát”; identity đã xác thực giúp trả lời “chủ thể nào”; authorization trả lời “chủ thể đó được làm gì với tài nguyên nào, trong điều kiện nào”.** Ba câu hỏi liên quan nhưng không thể thay thế nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **IP không phải identity**, nhưng vẫn là thành phần quan trọng của security telemetry và network enforcement.
2. Phân biệt **network address, hostname, user identity, device identity, workload identity, service account, tenant, role, resource identity** và **request context**.
3. Phân tích các rủi ro do **NAT/CGNAT, VPN, proxy, load balancer, DHCP, IPv6, dual-stack, cloud IP reassignment, containers, Kubernetes và CDN** gây ra cho IP allowlisting.
4. Hiểu ranh giới tin cậy của **TLS/mTLS, certificate/SAN, SPIFFE/SVID, OIDC/OAuth tokens, MFA, 802.1X/NAC và device posture**.
5. Thiết kế **least-privilege policy** dựa trên subject, resource, action và context, không suy quyền chỉ vì cùng subnet.
6. Giải thích cách phối hợp **L3/L4 firewall, microsegmentation, workload identity, identity-aware proxy/Zero Trust Network Access và application authorization**.
7. Chỉ ra các trường hợp **X-Forwarded-For, HTTP Host, TLS SNI, DNS name, source IP** không được xem là danh tính đã được xác thực.
8. Thiết kế **migration** từ allowlist IP rộng sang identity-aware access theo giai đoạn, có fallback an toàn và rollback.
9. Dựng **audit/correlation chain** từ principal → device/workload → session → flow → resource/action để điều tra đúng sau NAT và proxies.
10. Áp dụng threat model, ma trận kiểm thử positive/negative, runbook và checklist vào môi trường on-premises, cloud và Kubernetes.

## 2. Địa chỉ mạng, danh tính và quyền hạn là ba lớp khác nhau

### 2.1. Các câu hỏi hệ thống phải trả lời

| Câu hỏi | Dữ liệu/kiểm soát phù hợp | Những gì không đủ |
|---|---|---|
| Packet đi đâu? | IP, route, FIB, NAT, zone, VPN tunnel | Email/user ID không giúp router chuyển gói nếu thiếu địa chỉ |
| Kết nối đến từ điểm nào? | Source IP:port, interface, VRF, NAT mappings, flow logs | Một IP sau NAT không xác định duy nhất client |
| Ai đang đăng nhập? | IdP authentication, session, MFA, principal và token validation | IP văn phòng hoặc VPN exit IP |
| Thiết bị nào? | Managed device identity, certificate, registration, posture signal | IP LAN, hostname tự khai, MAC trên mạng không tin cậy |
| Workload nào? | Workload identity certificate/SVID, service account, cloud workload principal | Pod IP có thể thay hoặc dùng chung egress |
| Được làm gì? | Authorization policy theo resource/action/tenant/attributes | TLS handshake thành công, chung subnet |
| Có đang an toàn để cấp quyền? | Risk signals, session freshness, revocation và policy checks | Chỉ “đăng nhập thành công từ trước” |
| Ai đã thực hiện tác vụ? | App audit, principal/session/request ID nối với flow/process | Chỉ firewall IP log hoặc ASN |

**Identity** không đồng nghĩa với một username tùy ý do client gửi. Một identity có giá trị bảo mật phải đi kèm **bằng chứng xác thực, nguồn cấp đáng tin cậy, vòng đời và ngữ cảnh đủ để thực hiện authorization**.

### 2.2. Sơ đồ từ network locator đến hành động

~~~mermaid
flowchart LR
    U["User / Workload"] --> A["Authentication: IdP / mTLS / attestation"]
    A --> P["Verified principal + attributes"]
    P --> Z["Authorization: resource, action, context"]
    Z --> R["Application / Database"]
    U --> N["IP / routing / NAT / firewall path"]
    N --> R
    T["Telemetry: identity + flow + decision + request"] -.-> A
    T -.-> Z
    T -.-> N
~~~

Đường dữ liệu thực tế vẫn cần mạng, nhưng **việc gói tin tới đúng IP** và **việc request được phép** là hai bước kiểm soát khác nhau. Một firewall có thể chặn sớm trước authentication; một ứng dụng vẫn phải kiểm tra quyền sau khi network path được mở.

### 2.3. Identity không phải một trường duy nhất

Trong môi trường doanh nghiệp thường có ít nhất:

- **Human identity:** tài khoản người dùng do IdP quản lý; subject, group, entitlement.
- **Device identity:** thiết bị đã đăng ký, có credential/certificate phù hợp và trạng thái quản lý.
- **Workload identity:** service/container/VM được xác thực qua SPIFFE, cloud IAM, service account hoặc PKI.
- **Service/resource identity:** API, database, queue, server có identity được client xác minh.
- **Application/tenant identity:** quyền thuộc một tenant, project, customer hoặc organization.
- **Session/request identity:** thông tin xác thực hiện tại gắn vào một request, không phải chỉ nguồn mạng.

Một người dùng hợp lệ trên **thiết bị không tuân thủ posture** có thể bị từ chối truy cập dữ liệu nhạy cảm. Một workload hợp lệ có mTLS có thể vẫn bị từ chối một thao tác xóa dữ liệu vì thiếu quyền ở application layer.

## 3. Vì sao quy tắc “allow IP X” dễ gây sai lầm?

### 3.1. IP là locator/context, có vòng đời

Một địa chỉ IP có thể:

- Được DHCP cấp lại cho thiết bị khác sau lease expiration.
- Là private IP trùng giữa hai VPC/VNet hoặc VRF độc lập.
- Là public egress NAT của hàng nghìn người dùng, máy chủ hay Pods.
- Là proxy, ZTNA gateway, CDN edge hoặc load balancer, không phải origin.
- Đổi theo cloud scaling, failover, rolling deployment hoặc pod rescheduling.
- Có phiên bản IPv4/IPv6 song song; IPv6 privacy addresses có thể xoay vòng.
- Được cloud provider thu hồi và cấp cho một tenant khác sau khi release.
- Bị spoof ở một số ngữ cảnh packet/UDP hoặc khi client gửi dữ liệu header không tin cậy.

Vì vậy, IP cần được gắn với **thời điểm, điểm quan sát, network zone/VRF, NAT translation và owner**; ngay cả khi biết đầy đủ các yếu tố đó, IP vẫn không tự xác minh quyền người dùng.

### 3.2. Một IP cho nhiều chủ thể (many-to-one)

~~~mermaid
flowchart LR
    A["Developer laptop"] --> NAT["VPN / NAT gateway"]
    B["Compromised endpoint"] --> NAT
    C["CI runner"] --> NAT
    NAT -->|"Public source 203.0.113.50"| FW["Destination firewall: IP allowlist"]
    FW --> API["Internal API"]
~~~

Nếu firewall chỉ kiểm `source IP = 203.0.113.50`, ba nguồn có thể được xử lý như nhau. Một tài khoản và thiết bị không còn được tin cậy vẫn có thể đi ra bằng cùng gateway.

**Số lượng kết nối từ một NAT IP không chứng minh một người dùng duy nhất**, và IP allowlist ở đích không chứng minh MFA/device posture đã được kiểm tra.

### 3.3. Một chủ thể có nhiều IP (one-to-many)

Một nhân viên đi từ văn phòng sang Wi-Fi gia đình rồi mạng di động có thể lần lượt dùng nhiều source IP. Một ứng dụng Kubernetes khi reschedule có thể dùng Pod IP mới; khi đi ra Internet lại được SNAT thành Node IP hoặc NAT gateway IP.

Nếu quyền truy cập buộc chặt với IP, tổ chức thường mắc hai lỗi trái ngược:

1. **Mở allowlist quá rộng** để “đỡ phải cập nhật” — tăng blast radius.
2. **Chặn nhầm workload/user hợp lệ** khi địa chỉ thay — giảm availability, tạo động lực dùng ngoại lệ nguy hiểm.

### 3.4. Cùng IP đích không có nghĩa cùng ứng dụng

Một IP CDN/load balancer có thể phục vụ nhiều tên miền và tenants, chọn virtual host theo TLS SNI, HTTP Host hoặc routing config. Việc allow IP đó **không phân biệt tenant nào** và có thể bao gồm các endpoint ngoài mục đích.

Ngược lại, một application hostname có thể resolve thành nhiều A/AAAA records, CNAME chain, anycast edges và private endpoints. **Một lần lookup IP không phải danh tính dịch vụ đáng tin cậy hoặc lịch sử cố định của nó**.

### 3.5. IP spoofing có giới hạn, đừng nói quá

Trong TCP connection chuẩn trên Internet, spoofing source IP một chiều thường **không đủ** để hoàn tất handshake và nhận phản hồi nếu attacker không kiểm đường đi. Tuy nhiên:

- Các protocol không kết nối như UDP có thể bị source spoofing nếu mạng không ngăn.
- Một actor trong cùng network segment hoặc có quyền trên routing path có thể gây giả mạo/poisoning tùy điều kiện.
- Proxy headers như `X-Forwarded-For` có thể bị client tự ghi nếu gateway không sanitize.
- Compromised VPN account/endpoint có thể dùng **IP được phép thực**, không cần spoof IP.

**Sai lầm lớn không chỉ là spoofing IP**, mà là coi một địa chỉ quan sát được như bằng chứng mật mã về identity và authorization.

## 4. Bốn lớp kiểm soát cần phối hợp

| Lớp | Kiểm soát | Giá trị | Hạn chế |
|---|---|---|---|
| **Network isolation** | VLAN/VRF, routing, firewall, security groups, NetworkPolicy | Giảm reachable surface và chặn sớm | Thường thiếu user/resource identity |
| **Connection/device auth** | VPN/ZTNA, 802.1X/EAP-TLS, device certificate/posture | Chứng thực endpoint/thiết bị theo chính sách | Không tự trao quyền trên từng API/object |
| **Workload/server auth** | TLS/mTLS, SPIFFE/SVID, cloud workload identity | Xác thực peer/service nếu kiểm đúng | Không chứng minh workload chưa bị xâm nhập |
| **Application authorization** | IAM roles, scopes, RBAC/ABAC/ReBAC, tenant isolation | Quyết định từng hành động/tài nguyên | Không thay network DoS controls hoặc routing |

Đây là các **lớp bổ sung**, không phải cuộc cạnh tranh “chọn IP hay identity”.

### 4.1. Mô hình kiểm soát cho một API

~~~text
1. Router/FW:
   Cho phép traffic đi tới approved gateway/service;
   chặn lateral paths rõ ràng.

2. TLS endpoint:
   Xác minh certificate/hostname/server identity
   và peer workload identity nếu có mTLS.

3. Application gateway:
   Kiểm token/session, issuer, audience, lifetime, scopes.

4. API/DB:
   Kiểm quyền đối với operation, tenant và object.

5. Monitoring:
   Ghép principal/session/request IDs với flow/NAT context.
~~~

Nếu bước 1 cho phép kết nối, **bước 3–4 vẫn có thể deny**. Nếu bước 3–4 cho phép nhưng mạng từ Internet đã bypass firewall bắt buộc, kiến trúc vẫn có thể vi phạm yêu cầu phòng vệ nhiều lớp.

## 5. Những ví dụ người học thường hiểu sai

### 5.1. “IP văn phòng là trusted”

IP văn phòng chỉ mô tả **điểm thoát mạng**. Máy bị nhiễm malware hoặc khách kết nối mạng khách có thể đi qua dải liên quan nếu network segmentation yếu. Để cấp quyền admin cần **human identity, MFA, device trust, per-resource authorization và audit**.

### 5.2. “VPN vào được là được phép dùng mọi thứ”

VPN thiết lập một kênh truy cập mạng/nhận dạng theo khả năng sản phẩm, nhưng **VPN connectivity không phải application authorization**. Không nên trao full subnet reachability cho mọi VPN users khi chỉ cần vài ứng dụng. Dùng per-resource ZTNA/identity-aware access hoặc ACLs theo role/asset được kiểm chứng.

### 5.3. “IP máy chủ bằng identity của service”

Một VM có thể chạy nhiều services; Pod IP có thể thay; một compromised process có thể phát request bằng network stack của máy hợp lệ. Cần **workload identity credential và authorization theo API/service**, cộng với process/host integrity monitoring.

### 5.4. “DNS hostname đáng tin hơn IP nên đủ”

Hostname giúp định danh logic nhưng **DNS answer/HTTP Host/TLS SNI là thông tin định tuyến hoặc tự khai**, không tự chứng minh remote service sở hữu private key hoặc caller được phép. Với HTTPS cần **hostname validation và certificate chain**, còn API cần application authorization.

### 5.5. “Có mTLS nghĩa là app hoàn toàn an toàn”

mTLS giúp hai peer xác thực identities theo trust model, nhưng **không tự ngăn một workload hợp lệ bị chiếm quyền**, không thay resource-level access control, và không xác thực user cuối trong mọi mô hình proxy. Mỗi identity phải có **phạm vi quyền**, revocation/rotation và audit.

### 5.6. “Allowlist IP dễ hơn quản lý danh tính”

Trong hệ nhỏ, IP allowlist có thể dễ triển khai ban đầu. Nhưng khi có cloud autoscaling, NAT, remote users và nhiều tenants, chi phí ngoại lệ/stale rules/audit thường tăng. Hệ thống tốt cân bằng **identity-aware policy** với **đơn giản vận hành, availability và khả năng kiểm chứng**, không chuyển hết sang một IdP single point of failure mà thiếu recovery plan.

## 6. Danh tính nào cần được xác minh ở đâu?

Một kiến trúc có thể có nhiều principal cùng hiện diện:

~~~mermaid
flowchart LR
    HUMAN["Alice: human principal"] --> DEV["Managed laptop: device identity"]
    DEV --> GW["ZTNA / reverse proxy"]
    GW --> SVC["orders-api: workload principal"]
    SVC --> DB["orders-db: resource/server identity"]
    IDP["IdP: authentication / attributes"] -.-> HUMAN
    NAC["NAC/posture provider"] -.-> DEV
    PKI["Workload CA / SPIFFE trust"] -.-> SVC
    AUTH["Authorization policies"] -.-> GW
    AUTH -.-> SVC
    AUTH -.-> DB
~~~

Đăng nhập của Alice, trạng thái quản lý laptop, credential của `orders-api` và danh tính server DB là **những bằng chứng khác nhau**. Chúng có thể tạo thành policy đa điều kiện, nhưng không nên được nhập nhằng thành một chuỗi ký tự username hoặc IP.

### 6.1. Human identity

Một người có thể được xác thực qua SSO/IdP bằng mật khẩu, passkey, MFA hoặc phương pháp được tổ chức chấp nhận. Kiểm soát cần xem:

- Principal ID ổn định, có **issuer/namespace**, tránh đụng username.
- Session age, MFA assurance, device/risk context khi policy yêu cầu.
- Group/role membership có **nguồn đáng tin** và thời hạn cập nhật.
- Trạng thái vô hiệu tài khoản, quyền vừa bị thu hồi và phiên cũ.
- Quyền trên ứng dụng/tài nguyên cụ thể, không chỉ “được VPN”.

MFA làm giảm rủi ro nhiều kiểu đánh cắp tài khoản, nhưng **không đảm bảo session hiện tại không bị hijack** hoặc endpoint không bị compromise.

### 6.2. Device identity

Device identity thường dựa trên đăng ký thiết bị, certificate/key bảo vệ phù hợp, MDM/endpoint management hoặc một cơ chế attestation. Tuy nhiên:

- Có certificate **không có nghĩa posture hiện còn tuân thủ**.
- Posture có thể cần kiểm disk encryption, cập nhật bảo mật, EDR và policy state.
- Thông tin client tự khai như hostname, MAC hay HTTP User-Agent **không đủ** nếu thiếu cơ chế tin cậy.
- Một managed device không tự trao quyền cho mọi người dùng trên máy đó.

Device identity là điều kiện bổ sung tốt cho truy cập nhạy cảm, không phải thay user identity.

### 6.3. Workload identity

Workload identity trả lời **ứng dụng/service nào đang gọi**, có thể qua:

- **X.509 mTLS certificates** với URI SAN/service identity theo PKI.
- **SPIFFE ID / SVID** do một hệ thống cấp phát danh tính workload phát hành.
- Cloud provider IAM/workload federation với role binding tới VM, service hoặc Pod.
- Kubernetes ServiceAccount làm nguồn danh tính trong một mô hình trust đã được cấu hình.
- Signed identity tokens có issuer/audience và phương pháp xác minh phù hợp.

Không dùng **Pod IP** như định danh lâu dài: Pod reschedule thay IP; một IP có thể được tái sử dụng; Node/NAT egress IP có thể đại diện nhiều workloads.

### 6.4. Resource identity

Client cũng phải biết mình đang nói chuyện với **đúng server**. Với TLS:

- Kiểm chain tới trust anchor được phép.
- Kiểm hostname/server identity trong SAN theo quy tắc phù hợp.
- Kiểm certificate validity và key usage/EKU theo policy.
- Không bỏ xác minh bằng tùy chọn tương đương `--insecure` hoặc bỏ hostname verification.
- Với private PKI/service mesh, kiểm trust domain và identity mapping.

**Một IP đích đúng không chứng minh server identity** khi có NAT, shared hosting, DNS poisoning hoặc TLS termination ở proxy.

## 7. Authentication và authorization khác nhau ra sao?

### 7.1. Một công thức tư duy

\[
\text{Access decision} =
f(\text{verified subject},\ \text{resource},\ \text{action},\ \text{context},\ \text{policy})
\]

Đây là khung mô tả, không phải công thức số học. **IP có thể là một thuộc tính context**, nhưng không được tự động thay `verified subject`.

### 7.2. Chính sách sai và chính sách tốt hơn

**Sai:**

~~~yaml
# PSEUDO-POLICY KHÔNG DÙNG CHO PRODUCTION.
when: "sourceIp in 10.20.0.0/16"
then: "allow all database actions"
reason: "all machines in app subnet are trusted"
~~~

**Hướng thay thế:**

~~~yaml
# Mô hình policy để thảo luận, KHÔNG phải cú pháp thực thi.
subject:
  type: workload
  identity: spiffe://prod.example/ns/orders/sa/orders-api
  authenticatedBy: trusted-workload-pki
resource:
  service: orders-db
  database: orders
action:
  - connect
  - execute-approved-queries
conditions:
  environment: production
  sourceZone: application
  targetZone: data
  tlsPeerValidated: true
  sessionNotRevoked: true
  additionalBusinessAuthorization: required
decision: allow-only-matching
default: deny
owner: orders-platform-security
~~~

**Không tự động** triển khai cú pháp này vào firewall hoặc mesh. Đây là yêu cầu chính sách; mỗi enforcement platform hỗ trợ **tập attributes/decisions khác nhau**, và database/app vẫn phải tự thực hiện kiểm tra quyền của mình.

### 7.3. Chứng thực không đồng nghĩa cấp mọi quyền

Ví dụ:

1. Client có một certificate hợp lệ trong trust domain của công ty.
2. mTLS handshake PASS; peer được nhận diện là `billing-worker`.
3. Client gửi request xóa đơn hàng của một tenant khác.
4. Application phải **deny** nếu peer không có quyền thao tác với đối tượng đó, dù TLS/authentication đã thành công.

**Quyền của identity** cần có scope, hành động cụ thể, tài nguyên, tenant và thời điểm; không coi “đã vào được mạng nội bộ” là mọi thao tác đều được phép.

### 7.4. RBAC, ABAC và ReBAC

| Mô hình | Quyết định dựa trên | Ví dụ | Giới hạn |
|---|---|---|---|
| **RBAC** | Roles được cấp cho principal | Support chỉ được xem ticket | Role explosion/cấp quá rộng |
| **ABAC** | Attributes của subject/resource/context | Workload thuộc environment prod, resource cùng tenant | Nguồn attributes phải xác minh và cập nhật |
| **ReBAC** | Quan hệ giữa subject và resource | User là thành viên project sở hữu secret | Cần graph và kiểm quyền nhất quán |
| **Network zone policy** | Subnet/zone/port/protocol | App zone chỉ tới DB/5432 | Không đủ end-user/object authorization |

Có thể kết hợp các mô hình: **RBAC cho vai trò**, **ABAC cho device posture/tenant**, **network policy để giảm reachable surface**, và **application permission** cho hành động nghiệp vụ.

## 8. Token và phiên đăng nhập: đọc claims chưa phải xác thực

### 8.1. OAuth 2.0 / OIDC trong một hệ thống identity-aware

Trong truy cập API:

- **OIDC** có thể dùng để xác thực user với ứng dụng và phát hành ID token theo luồng chuẩn.
- **OAuth 2.0 access token** được API dùng cho authorization delegation theo trust model; **access token có thể là JWT hoặc opaque**, tùy issuer.
- **ID token** không được tự dùng thay access token để gọi một API chỉ vì nó cũng có trường `sub`.
- **Session cookies** phải được kiểm theo ứng dụng, có vòng đời, CSRF controls khi phù hợp.

Điều quan trọng không phải token “trông hợp lệ” vì decode được Base64, mà là **server kiểm chữ ký/issuer/audience/lifetime/authorization semantics hoặc introspection đúng chuẩn**.

### 8.2. Những kiểm tra thường bị bỏ quên

| Kiểm tra | Tại sao cần |
|---|---|
| **Signature / issuer** | Token đến từ trusted authority, không chỉ JSON tự khai |
| **Audience** | Token có được cấp cho API này không? |
| **Expiry / not-before / clock skew** | Token còn hợp lệ theo policy không? |
| **Scopes / permissions** | Quyền trên operation được yêu cầu |
| **Tenant / resource ID** | Không truy cập chéo organization/data |
| **Token type/use** | ID token, access token, refresh token có mục đích khác nhau |
| **Revocation/session state** | Quyền vừa bị thu hồi và phiên cũ |
| **Proof-of-possession / channel binding** | Giảm rủi ro bearer token bị replay khi deployment hỗ trợ |
| **Trusted gateway-to-backend hop** | Không tin headers do client tự dựng |

Không đưa raw bearer tokens, refresh tokens, private keys hoặc cookies vào firewall/SIEM logs chỉ để thêm identity context.

### 8.3. Bearer token bị đánh cắp không cần spoof IP

Nếu application chỉ xác minh source IP nằm trong allowlist, một attacker đã chiếm laptop hoặc VPN account có thể đi qua **cùng IP được phép**. Nếu chỉ có bearer token mà không có session protection/revocation/resource authorization, attacker có thể replay token trong phạm vi nó có hiệu lực.

Phòng vệ nhiều lớp có thể gồm **short-lived tokens, MFA, device/session context, least-privilege scopes, anomaly detection, revocation và proof-of-possession** khi thích hợp. Nhưng không có một yếu tố nào tự loại bỏ mọi rủi ro.

## 9. Workload identity, SPIFFE và mTLS

### 9.1. Một định danh workload có cấu trúc

Ví dụ:

~~~text
spiffe://prod.example/ns/orders/sa/orders-api
  \______/ \__________/ \_______/ \__/ \________/
   scheme   trust domain   namespace    workload identity path

Ví dụ minh họa identity format; trust domain/path conventions
phải do hệ thống cấp phát và policy của tổ chức xác định.
~~~

**SPIFFE ID** là định danh workload theo trust domain. **SVID** là tài liệu/credential xác nhận identity này theo profile như X.509 hoặc JWT, được phát hành và kiểm qua trust mechanism phù hợp. Việc một string chứa `spiffe://` **không có giá trị xác thực** nếu chưa kiểm credential/trust bundle/issuer.

### 9.2. Mô hình service-to-service

~~~mermaid
sequenceDiagram
    participant A as Orders workload
    participant C as Workload identity provider
    participant P as Service mesh proxy / TLS endpoint
    participant D as Billing service
    A->>C: Obtain short-lived workload credential (authorized)
    C-->>A: Identity material via secured mechanism
    A->>P: Call billing service
    P->>D: mTLS with peer verification
    D-->>P: Validated server identity
    Note over P,D: AuthZ policy checks caller principal and resource
    P-->>A: Response or deny per policy
~~~

Sơ đồ mang tính khái niệm: trong thực tế credential có thể được cấp trực tiếp tới proxy/agent, và trách nhiệm TLS termination/authorization thay đổi theo sidecar, ambient, gateway hoặc application TLS.

### 9.3. Các điều kiện tin cậy tối thiểu

- Credential được phát cho **đúng workload** theo một phương thức bootstrap/attestation được bảo vệ.
- Private key được bảo vệ theo khả năng nền tảng; certificate/key lifecycle có **rotation và revocation**.
- Peer xác minh chain/trust domain/SAN hoặc claims tương ứng.
- Chính sách identity-to-permission được review và **default deny** khi phù hợp.
- Cloud/Kubernetes identities không bị cấp quyền wildcard chỉ vì cùng namespace.
- Logs ghi **verified principal** cùng decision, không chỉ IP và SNI.
- Có kế hoạch khi identity issuer/CA/control plane không khả dụng.

**mTLS xác thực các endpoints của một TLS connection** theo trust model; nó không tự xác thực mọi user cuối cùng hoặc bảo đảm workload không bị attacker điều khiển.

### 9.4. Lỗi hay gặp: trộn server cert và client cert

Với HTTPS thông thường, client thường kiểm **server certificate**; không mặc định có client certificate. Khi dùng mTLS, cả hai phía có thể xác thực bằng credentials phù hợp. Tuy nhiên:

- Một server certificate có SAN `api.example.test` **không xác thực caller**.
- Một workload client certificate không tự trao mọi API permissions.
- Nếu TLS terminate tại ingress gateway, application phía sau cần **cơ chế chuyển tiếp principal đáng tin cậy** và tự kiểm operation/tenant.
- TLS 1.3 certificate handshake messages thường được mã hóa; passive PCAP thông thường không trích được peer cert chỉ bằng packet decoding.

## 10. Device identity và 802.1X/NAC

### 10.1. Vì sao MAC/IP allowlist yếu ở mạng truy cập?

Ethernet MAC có thể bị thay đổi trong nhiều ngữ cảnh và thường chỉ có ý nghĩa trên một local link/segment; địa chỉ IP có thể do DHCP cấp lại. Việc gán policy mạng chỉ bằng một trong hai thuộc tính không đủ chứng minh thiết bị đã được doanh nghiệp quản lý.

Với môi trường thích hợp, **802.1X/EAP-TLS** có thể xác thực thiết bị/user vào mạng ở access edge, thông qua switch/AP, supplicant và authentication server. Sau đó NAC có thể áp VLAN/ACL/dynamic roles theo kết quả xác thực và posture.

### 10.2. 802.1X không thay IAM của ứng dụng

Một laptop được xác thực vào mạng nhân viên không tự có quyền đọc database khách hàng. Vẫn phải có **user login, application authorization, resource-specific controls**.

Một thiết bị được cấp certificate hợp lệ có thể bị mất cắp, key compromise hoặc không còn tuân thủ security posture. Vì vậy cần **lifecycle/revocation, inventory, posture, network segmentation và giám sát**.

### 10.3. Phương án fallback cho thiết bị legacy

Không phải thiết bị IoT/OT/printer nào hỗ trợ 802.1X/EAP-TLS. Có thể dùng:

- Isolated VLAN/VRF và **narrow allowlist** tới đúng services.
- Inventory/owner, lifecycle management và passive telemetry.
- NAC exceptions với expiry, physical port controls và monitoring.
- Gateway/proxy authenticating thay cho device khi kiến trúc cho phép, có ghi hạn chế assurance.

**MAC Authentication Bypass (MAB)** có thể được dùng cho thiết bị không hỗ trợ 802.1X, nhưng **MAC không phải proof-of-possession mật mã**; nên coi đó là tín hiệu yếu cần segmentation và risk review, không tương đương EAP-TLS.

## 11. Proxy, load balancer và header tin cậy

### 11.1. Source IP trên application có thể chỉ là proxy

~~~mermaid
flowchart LR
    C["Client 198.51.100.50"] --> CD["CDN / WAF"]
    CD --> L["Load balancer / reverse proxy"]
    L -->|"Source IP = proxy address"| APP["Application"]
    I["Verified user/workload principal"] -.-> APP
    H["Forwarded client-IP metadata"] -.-> L
~~~

Nếu ứng dụng chỉ xem `REMOTE_ADDR` hoặc TCP peer IP, nó thường thấy **load balancer/proxy**. Điều này không xác định human/device/workload ban đầu. Để audit cần log correlation ở các hops và application-level principal đã xác thực.

### 11.2. X-Forwarded-For không phải danh tính đã xác thực

Headers như `X-Forwarded-For`, `Forwarded`, `X-Real-IP` có thể biểu diễn **client network address qua proxy chain**. Nhưng một client Internet có thể tự gửi header cùng tên. Nếu ứng dụng tin giá trị client đưa vào trước khi một trusted gateway chuẩn hóa, attacker có thể khiến hệ thống:

- Log nhầm source IP, làm sai incident attribution.
- Vượt IP-based rate limit hoặc allowlist nếu app dùng header cho quyết định bảo mật.
- Gây nhầm lẫn giữa nhiều proxies, private ranges và address families.
- Tạo inconsistencies giữa WAF, gateway và backend.

**Thiết kế đúng:** chỉ tin metadata do **trusted proxy/hop** phát hành theo cấu hình cụ thể; gateway phải remove/overwrite untrusted headers, áp trusted hop list rõ, giới hạn network route vào backend. Những thông tin này hỗ trợ **source attribution**, không thay user/workload authentication.

### 11.3. HTTP Host và TLS SNI cũng không phải caller identity

- **HTTP Host / :authority** xác định virtual host/request authority, nhưng do client gửi và thường nằm trong TLS encryption.
- **TLS SNI** là tên client khai trong ClientHello khi quan sát được, giúp endpoint chọn certificate/route.
- **ECH** có thể che inner SNI; outer name không chắc là target.
- **Certificate SAN** mô tả danh tính mà certificate có thể xác thực khi validation đúng; không chứng minh caller được cấp quyền.
- **HTTP path** cũng do client yêu cầu, không phải xác minh action authorization.

Một yêu cầu tới host có tên “internal” **không tự là nội bộ hoặc đáng tin** nếu thiếu authentication/trust boundary.

### 11.4. Mô hình truyền verified identity qua proxy

~~~text
Client → Trusted gateway (authenticates user)
         ↓ signed/context-bound identity propagation
Backend (accepts identity only from gateway + verifies trust)
         ↓ checks operation, resource and tenant
Database/resource policy

Không tin:
  "X-User: admin" do Internet client tự gửi.

Không đủ:
  "X-Forwarded-For: 10.20.1.7" và suy caller là nhân viên.
~~~

“Signed/context-bound” là **yêu cầu thiết kế**, có thể là token được ký, mTLS-bound identity, internal gateway authentication hoặc cơ chế đáng tin khác. Không tự invent custom cryptographic headers nếu platform có chuẩn đáng dùng; phải kiểm **issuer, audience, key rotation, expiry và backend trust**.

## 12. Network identity correlation qua NAT và nhiều hop

### 12.1. Chỉ IP và port cũng cần timestamp

Ví dụ:

~~~text
Client workstation:
  user:     alice@example.test
  private:  10.30.10.25:50120

VPN edge:
  authenticated session: vpn-session-734
  tunnel source: 10.200.10.8

Cloud NAT:
  translated source: 203.0.113.50:62004

Destination firewall:
  observed source: 203.0.113.50:62004
  destination: 198.51.100.20:443

Application:
  request-id: req-lab-012
  verified principal: Alice's IdP subject
  authorization: DENY for resource tenant-B
~~~

Địa chỉ và identities đều giả định để minh họa; **phải có timestamp, trust provenance và logs** mới nối được các events. Nếu chỉ nhìn `203.0.113.50`, không thể khẳng định Alice tạo request nào.

### 12.2. Correlation chain

~~~mermaid
flowchart LR
    AUTH["IdP authentication event"] --> SESSION["Verified session ID"]
    SESSION --> APP["App request ID + resource/action"]
    END["Endpoint/process event"] --> FLOW["Private 5-tuple"]
    FLOW --> NAT["NAT translation ID + time"]
    NAT --> EDGE["Public flow: IP/port/time"]
    EDGE --> APP
    POLICY["Authorization decision"] -.-> APP
~~~

**Cạnh correlation phải có bằng chứng**, không chỉ match gần thời điểm. Các source có thể lệch đồng hồ, NAT ports tái sử dụng và request IDs không propagate qua mọi hop.

### 12.3. Những trường tối thiểu trong log

| Loại log | Field gợi ý | Lưu ý |
|---|---|---|
| **Authentication** | Issuer, principal ID, auth method/assurance, session ID, time | Không log credentials/OTP/token |
| **Device/posture** | Stable device ID, attestation/posture decision/time | Không tin raw MAC/IP như proof |
| **Workload identity** | Verified trust domain/principal, cert/key version, time | Không nhầm SAN/subject tự khai với verified peer |
| **Firewall/flow** | Source/dest IP+ports, protocol, interface/zone, action, time | Biết vantage trước/sau NAT |
| **NAT** | Pre/post translation, ports, time range, translation ID | Thiếu NAT logs thì attribution có giới hạn |
| **Proxy/gateway** | Trusted client context, upstream ID, TLS/auth result, request ID | Sanitized forwarded headers |
| **Application** | Principal, tenant/resource/action, authz decision, correlation ID | Privacy/data minimization |
| **Security detection** | Rule, confidence, event/ingest timestamps, sensor source | Không tự suy rule im lặng nghĩa không có traffic |

Một ID do client tự chọn (ví dụ `X-Request-ID`) có thể được dùng để tracing nếu gateway chuẩn hóa và không dùng làm security proof. **Security principal phải được xác minh riêng**.

### 12.4. IP attribution vẫn hữu ích

IP/source subnet rất hữu ích để:

- Tìm network path/routing/zone và nơi firewall có thể enforce.
- Xác định các luồng bất thường, scans, DDoS, connection counts.
- Ánh xạ bằng NAT/flow logs tới assets khi có đủ context.
- Hỗ trợ IR containment tạm thời khi chưa thể dùng identity-based enforcement.

Nhưng kết luận **“user X đã truy cập dữ liệu Y”** cần application/identity audit, không được nâng từ một IP duy nhất.

## 13. Khi nào IP-based policy vẫn đúng?

**Không phải mọi IP rule đều sai.** Những ví dụ hợp lý:

| Tình huống | Vì sao IP còn giá trị | Điều phải bổ sung |
|---|---|---|
| **Chặn traffic ở L3/L4 trước authentication** | Router/firewall không có application principal trước khi mở TLS | Least privilege, protocol/service scope, log |
| **DDoS/rate limiting ở edge** | Cần bảo vệ tài nguyên trước app auth | NAT/shared-IP fairness, nhiều tín hiệu, tránh chặn nhầm |
| **Segmentation theo subnet/VRF** | Hạn chế reachability và lateral movement | App/workload auth cho critical services |
| **Management OOB restricted network** | Giảm exposure của control plane | MFA, AAA, RBAC, device auth và audit |
| **Partner egress allowlisting** | Hệ thống đối tác chỉ hỗ trợ IP filtering | Contract, lifecycle/owner, mTLS/token khi có |
| **OT/legacy equipment** | Không hỗ trợ SSO/mTLS và khó nâng cấp | Isolation, narrow ACL, gateway, monitoring |
| **Bootstrap trust** | Ban đầu cần định tuyến/tường lửa tới IdP/PKI | Strict trust anchor, least privilege, recovery |
| **Network forensic filtering** | Phân tích 5-tuple hiệu quả | Correlate principal/process/NAT |

### 13.1. IP là tín hiệu bổ sung, không phải “chìa khóa”

Một policy hợp lý có thể là:

~~~text
Allow request WHEN:
  authenticated principal is orders-api
  AND destination resource is orders-db
  AND action is permitted
  AND workload identity credential is valid
  AND connection arrives via approved network zone/path
  AND risk/session policy allows

Network zone/IP is a constraint.
It is NOT the sole proof of caller identity.
~~~

Ở các platform không thể kiểm mọi điều kiện trong cùng PEP, hãy **phân bổ trách nhiệm**: firewall hạn chế network path, gateway kiểm principal, application kiểm object/tenant, telemetry ghép decisions.

### 13.2. Vì sao không nên bỏ toàn bộ IP controls?

- Identity provider có thể **không khả dụng** khi network outage; vẫn cần bảo vệ service ở L3/L4.
- Authentication/authorization xảy ra **sau một số network exchange**; DDoS trước xác thực cần controls khác.
- Có các protocols/legacy services không hỗ trợ identity-aware authentication.
- Firewall/segmentation ngăn một compromised workload liên hệ các tài sản không cần thiết.
- Network routes/NAT/vantage vẫn cần thiết cho kiểm toán và forensic.

**Zero Trust không có nghĩa không có mạng phân đoạn hoặc không có firewall**. Nó có nghĩa vị trí mạng **không tự tạo lòng tin ngầm**.

## 14. Thiết kế Zero Trust Network Access (ZTNA)

### 14.1. Từ “có VPN thì thấy subnet” sang “được dùng đúng ứng dụng”

~~~mermaid
flowchart LR
    USER["User + managed device"] --> PEP["ZTNA policy enforcement point"]
    IDP["IdP + MFA + session status"] --> PDP["Policy decision point"]
    MDM["Device posture source"] --> PDP
    PDP -->|"Allow/deny for resource"| PEP
    PEP --> APP["Approved application"]
    APP --> DATA["Resource-level authorization"]
    LOG["Access/audit telemetry"] -.-> PDP
    LOG -.-> PEP
~~~

Nhiều kiến trúc có các thành phần **policy engine/decision/administration/enforcement** dưới tên khác nhau. Vai trò mô tả ở đây chỉ để hiểu luồng, không là yêu cầu phải mua một sản phẩm nhất định.

### 14.2. Quy trình quyết định

1. Client yêu cầu ứng dụng/tài nguyên cụ thể.
2. Trusted access service xác minh **principal** và session authentication.
3. Policy xét device posture, role, group, tenant, resource sensitivity và context liên quan.
4. Chỉ cấp đúng path/operation cần thiết khi **được phép**, không tự mở entire network.
5. Access events được ghi với principal+device/resource+decision.
6. Khi quyền bị thu hồi hoặc rủi ro thay đổi, session và policy được đánh giá theo cơ chế revocation đã thiết kế.

### 14.3. Tránh hiểu “continuous verification” thành phép màu

Một số hệ thống chỉ reevaluate khi session/tokens refresh, có caching và thời gian propagation. Không khẳng định quyền bị revoke thì tất cả TCP sessions lập tức ngắt ở mọi nền tảng.

Để thiết kế:

- Chọn **session lifetime/revalidation** theo sensitivity và availability.
- Kiểm **token revocation, group changes, device quarantine** có tác động tới phiên đang mở không.
- Giữ **break-glass/OOB** để xử lý IdP outage một cách có kiểm soát.
- Không để ZTNA service là điểm lỗi chung duy nhất của monitoring/recovery.
- Giám sát fail-open/fail-closed semantics và không vô hiệu enforcement để “fix kết nối”.

## 15. Microsegmentation và identity-based workload policy

### 15.1. Tại sao rule “app subnet → DB subnet” quá rộng?

Một subnet thường không đồng nhất về chức năng: có API, CI runner, debug VM, test workload hoặc compromised node. Chỉ có **một** dịch vụ cần DB. Identity-aware policy có thể **thu hẹp principal được phép** dù các workloads cùng mạng.

### 15.2. Ba cấp chính sách

| Cấp | Ví dụ | Giới hạn |
|---|---|---|
| **Subnet/zone L3/L4** | App zone → DB zone TCP/5432 | Mọi chủ thể trong zone có thể bị gộp nếu quá rộng |
| **Workload-level L3/L4** | Pod có labels hoặc tags đúng được tới DB port | Labels/tags phải được bảo vệ; không tự là cryptographic identity |
| **Service-to-service L7/identity** | Verified workload principal `orders-api` được gọi `orders-db` | Cần trust PKI/IdP, proxy/PEP coverage; app vẫn kiểm quyền data |

Giải pháp mạnh thường sử dụng **cả ba**, không chỉ một. CNI policy có thể giảm network exposure; mTLS/mesh hoặc application kiểm principal; DB/app xác thực quyền trong request.

### 15.3. Kubernetes labels và ServiceAccounts khác nhau

Trong Kubernetes:

- **Labels** là metadata dùng để select Pods/Namespaces; nếu tác nhân có quyền thay labels, policy dựa vào labels có thể bị ảnh hưởng.
- **ServiceAccount** là đối tượng identity cho Pods trong cơ chế được cấu hình; token/certificate có thể được dùng để nhận dạng theo trust model.
- **Namespace** giúp tổ chức RBAC/resources nhưng không mặc định cách ly network.
- **NetworkPolicy chuẩn** có allowed ingress/egress cộng dồn khi nhiều policies chọn một Pod; không có explicit deny ưu tiên.
- **CNI phải hỗ trợ/enforce NetworkPolicy**; object được API chấp nhận không chứng minh dataplane đã chặn.

Một identity-aware mesh có thể dùng ServiceAccount-derived workload identity, nhưng phải xác minh **issuer, namespace/cluster trust và credential propagation** chứ không chỉ đọc chuỗi `serviceAccountName`.

### 15.4. Identity-aware cloud controls

Cloud security groups/NSGs thường kiểm network metadata: protocol, ports, CIDR, resource/interface attachments hoặc security-group references theo capability nền tảng. Dù tham chiếu **resource SG/tag** thay IP tĩnh:

- Nó có thể hạn chế network scope tốt hơn CIDR rộng.
- Nhưng **không nhất thiết tương đương mTLS workload authentication**.
- Rule và attachment có thể gắn nhiều instances/services.
- Cross-VPC/region/account behavior khác nhau theo provider; cần đọc semantics/limits.
- Application IAM/RBAC vẫn cần kiểm quyền nghiệp vụ.

**Không gọi mọi “tag-based firewall” là cryptographic identity-based policy** nếu điều kiện chỉ là metadata được một controller cấp.

## 16. Ví dụ Kubernetes: thu hẹp network path trước khi thêm workload identity

Tình huống lab:

- Namespace `orders` chạy Pod có label `app=orders-api`.
- Namespace `data` có Pod database `app=orders-db`, lắng nghe TCP/5432.
- Mục tiêu: chỉ cho phép network ingress từ Orders API tới DB trên TCP/5432.

Ví dụ NetworkPolicy lab:

~~~yaml
# LAB ONLY — KHÔNG kubectl apply trực tiếp lên production.
# CNI phải hỗ trợ NetworkPolicy; các policy khác vẫn cộng dồn allow.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-db-allowed-sources
  namespace: data
spec:
  podSelector:
    matchLabels:
      app: orders-db
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

**Điều NetworkPolicy này làm được:** Trong các cluster/CNI phù hợp, khi policy chọn DB Pods, nó thêm một allowed ingress flow từ Pods khớp namespace/Pod selectors tới TCP/5432.

**Điều nó không tự làm:**

- Không xác minh certificate của `orders-api` hay token ứng dụng.
- Không chắc ngăn mọi nguồn nếu **NetworkPolicies khác** cũng allow DB Pods.
- Không xác thực user cuối/tenant hoặc thao tác SQL.
- Không luôn áp như kỳ vọng cho traffic hostNetwork, nodes, Service meshes hoặc datapath đặc thù; cần kiểm theo CNI.
- Không khẳng định labels do một principal đáng tin sở hữu nếu RBAC/admission policy bị cấu hình rộng.
- Không tự ngăn egress từ `orders-api` tới destinations khác; egress isolation là lớp riêng.

### 16.1. Kiểm tra lab chỉ đọc trước khi thay policy

~~~bash
# Chỉ xem trên cluster lab được cấp quyền, không thay resources.
kubectl config current-context
kubectl get namespaces --show-labels
kubectl get networkpolicy -n data
kubectl get pods -n data -o wide --show-labels
kubectl get pods -n orders -o wide --show-labels
kubectl get serviceaccounts -n orders
~~~

Một ServiceAccount tồn tại trong API **không chứng minh** workload đang sử dụng credential được cấp an toàn hoặc authorization policy đang enforce. Để kết luận, phải đối chiếu **workload configuration, certificate/token issuance, mTLS handshake/PEP logs và actual flow tests**.

### 16.2. Bước tiếp theo là xác minh workload principal

Với nền tảng hỗ trợ mTLS service identity, policy ở endpoint DB/gateway có thể yêu cầu:

~~~text
IF verified peer SPIFFE identity is
   spiffe://cluster.local/ns/orders/sa/orders-api
AND target service is
   orders-db
AND network path and port are approved
THEN allow the connection.

DEFAULT: deny connections that cannot satisfy policy.
~~~

Đây là **logic**, không phải manifest universal. Nếu database không có mTLS proxy hoặc policy enforcement point, chuỗi identity không tự được xác minh chỉ vì có trong YAML mô tả.

### 16.3. Mesh AuthorizationPolicy minh họa (trong lab có Istio phù hợp)

~~~yaml
# CHỈ MINH HỌA LAB: kiểm tra Istio version/trust domain/proxy mode.
# Policy ALLOW khi có peer principal khớp, cho workload app=orders-db.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-db-allow-orders-api
  namespace: data
spec:
  selector:
    matchLabels:
      app: orders-db
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - spiffe://cluster.local/ns/orders/sa/orders-api
      to:
        - operation:
            ports:
              - "5432"
~~~

Các **điều kiện tiên quyết quan trọng**:

1. Istio/workload networking mode và version phải thực sự **enforce** policy tại traffic path; môi trường ambient có L4/L7 coverage khác nhau và có thể cần waypoint/gateway cho thuộc tính L7.
2. Caller principal phải đến từ **mTLS peer identity được xác minh**, không phải một header tự khai.
3. Trust domain `cluster.local` trong ví dụ phải khớp thiết kế identity thật, không dùng nguyên trong mọi cluster.
4. Việc có một ALLOW policy chọn workload có thể làm thay đổi default behavior với các requests đi vào workload theo Istio semantics; cần xem **toàn bộ DENY/ALLOW/CUSTOM policies**, selector/targetRefs và namespace/root-level policies.
5. Nếu DB đang không có proxy/mesh enrollment, manifest được API chấp nhận vẫn **không bảo đảm traffic được kiểm soát**.
6. Khi bật strict mTLS hoặc thu hẹp principals, phải kiểm client hợp lệ không bị cắt và có rollback; **không áp rộng trên production chỉ để thử**.
7. Application/DB vẫn phải xác minh database identity, user/account và quyền SQL tương ứng.

**Đánh giá đúng:** vừa có **network boundary** ở CNI/firewall, vừa có **workload identity enforcement** ở mesh/app, vừa có **resource authorization** ở database. Không thay thế các lớp này bằng một IP allowlist.

## 17. Từ IP ACL sang identity policy: kế hoạch chuyển đổi

Một lỗi triển khai phổ biến là **xóa toàn bộ IP allowlists ngay khi bật IdP**. Nếu PEP/identity source không bao phủ tất cả paths, sẽ tạo outage hoặc đường bypass. Nên chuyển đổi theo từng luồng kinh doanh với test.

### 17.1. Mô hình chuyển đổi theo giai đoạn

~~~mermaid
flowchart TD
    I["Inventory current IP rules + actual usage"] --> O["Map owners, users, devices, workloads"]
    O --> E["Establish trusted identity issuance and enforcement"]
    E --> S["Shadow evaluation of identity policy"]
    S --> C["Canary group / service"]
    C --> T{"Positive + negative tests PASS?"}
    T -->|"Có"| P["Expand rollout + narrow IP rules"]
    T -->|"Không"| R["Rollback/repair with evidence"]
    P --> D["Remove stale broad exceptions"]
    D --> A["Drift/revocation/session monitoring"]
~~~

### 17.2. Bước 1 — Inventory IP controls

Liệt kê:

- CIDR/host/IP allowlists, source/destination, protocol/port.
- Owner, ticket, business justification và review/expiry.
- Những Luồng thực tế đang match rule, bao gồm IPv4/IPv6.
- NAT, VPN, proxy, load balancer, split-horizon DNS và cloud egress.
- Các exception “temporary” chưa từng được gỡ.
- Thiết bị legacy/OT/partner API không hỗ trợ identity-aware access.

Không nên xóa rule chỉ vì **hit count thấp**: một luồng backup/DR theo lịch hiếm khi phát sinh vẫn có thể quan trọng. Cần hỏi owner và kiểm dependency thực.

### 17.3. Bước 2 — Gắn principal với flow

Thiết kế cách nối:

~~~text
human user / managed device / workload principal
          ↓ authenticated session or credential
application or proxy request ID
          ↓ bound to source process/connection
5-tuple at host and before NAT
          ↓ translation metadata
5-tuple after NAT
          ↓ resource and action in application logs
authorization verdict
~~~

Không có evidence đầy đủ thì ghi **“IP-only attribution”** với giới hạn, không tự gắn username từ cùng subnet.

### 17.4. Bước 3 — Xác lập trust anchors, cấp và thu hồi danh tính

Một identity platform cần:

- Quy trình join/attest đối tượng và quyền cấp credential ban đầu.
- Key protection, trust anchors/issuer, rotation và revocation.
- Principals ổn định, namespaces/trust domains, tránh collision.
- Identity-to-resource policy, owner và approval.
- Tính sẵn sàng, backup, break-glass và behavior khi IdP/CA/control plane lỗi.
- Audit đủ để xác định **ai được cấp, ai đã dùng và quyền nào được phép**.

Nếu không thể tin việc **cấp identity**, việc thay IP bằng một token/cert string cũng chỉ đổi từ sai lầm này sang sai lầm khác.

### 17.5. Bước 4 — Shadow mode và canary

Trước khi bắt buộc deny:

1. Đánh giá policy identity ở **report-only/shadow** nếu platform có hỗ trợ; tuyệt đối không giả định mọi sản phẩm đều có.
2. So các principals từ logs với IP rules hiện tại; tìm unmanaged clients, service dependencies.
3. Thử với **một nhóm người dùng/workload** có owner và rollback.
4. Positive: người/service có quyền còn vào đúng tài nguyên.
5. Negative: source cùng IP nhưng **khác principal** không được cấp quyền ngoài ý định.
6. Test session revocation, certificate rotation, IdP outage và dual-stack.
7. Quan sát SLO, error rates, TLS handshake failures và audit pipeline.
8. Chỉ mở rộng khi enforcement behavior đã được xác minh.

### 17.6. Bước 5 — Giảm dần quyền IP rộng

Sau khi identity-aware enforcement hoạt động:

- Thu nhỏ IP allowlists thành **approved proxy/PEP/network paths** thay vì all subnet.
- Hạn chế direct origin access làm bypass identity gateway.
- Xóa stale CIDR/object groups theo approved change.
- Áp least-privilege egress/ingress cho cloud workloads.
- Giữ IP-based controls cho bootstrap/DoS/legacy cần thiết, có owner/expiry.
- Đo **policy drift** và asset rotation; đừng giả định một lần migrate là xong.

### 17.7. Rollback migration không được khôi phục broad access vô hạn

Nếu canary bị outage do IdP/CA:

- Ưu tiên **sửa trust/availability issue** hoặc giảm scope có kiểm soát.
- Nếu cần fallback, chỉ cho đúng service/principal/owner/thời gian với audit.
- Không mở `0.0.0.0/0` tới management/DB để “khôi phục kết nối”.
- Giữ những revocations/security fixes đã có.
- Xác minh both positive/negative tests sau rollback.

**Rollback tốt phải khôi phục trạng thái an toàn**, không chỉ phục hồi network reachability bằng mọi giá.

## 18. Chính sách động theo identity: những lỗi mới có thể xuất hiện

Chuyển từ IP sang identity làm giảm một loại rủi ro, nhưng tạo phụ thuộc mới. Phải threat-model:

| Thành phần | Failure mode | Kiểm soát |
|---|---|---|
| **IdP** | Outage, compromised admin, group misassignment | HA, constrained privileges, break-glass, audit |
| **Workload issuer/CA** | Wrong SVID issued, trust bundle drift | Attestation, short lifetimes, rotation, review |
| **Device posture** | Stale posture, bypass report-only | Freshness policy and quarantine |
| **Policy engine** | Fail-open/incorrect attribute mapping | Fail-safe behavior, test deny and fallback |
| **PEP/proxy** | Bypass direct origin route | Network isolation and ingress restrictions |
| **Token verification** | Wrong audience/issuer, accepted expired token | Standards-based validation and negative tests |
| **Role attributes** | Group/tenant membership stale | Revocation propagation/session recheck |
| **Service mesh** | Policy not enforced in one datapath mode | Workload coverage, gateway/waypoint tests |
| **Logs** | Identity not correlated with flow due NAT | Trusted principal logging, NAT mapping |
| **Secret handling** | Long-lived credentials leak | Rotation, secure stores, no log of secrets |
| **Break-glass** | Permanent unreviewed bypass | Scope, expiry, oversight and access audit |

### 18.1. Fail-closed, fail-open và cached decisions

Không có một lựa chọn duy nhất cho mọi service:

- Với admin/secret systems, **fail-closed** khi không kiểm được identity thường bảo vệ tốt hơn khỏi unauthorized access, nhưng có thể gây outage nếu IdP lỗi.
- Với safety-critical/availability-sensitive systems, cần design riêng, **không mặc định mở quyền**; có thể dùng local verified credentials, redundancy hoặc break-glass có kiểm soát.
- Cached identity/authorization decisions cần **TTL, freshness, revocation bounds và audit**.
- Cần kiểm **existing sessions** khi principal bị disable; việc chặn đăng nhập mới không chắc cắt TCP/TLS sessions cũ.

Một policy “allow nếu IdP timeout để tránh gián đoạn” có thể tạo **security bypass**. Nếu chọn exception trong bối cảnh đặc biệt, phải có risk acceptance, scope tối thiểu, monitoring và expiry.

### 18.2. Clock/time và certificate expiry

Identity certificates/tokens có `NotBefore`, `NotAfter` hoặc tương đương. Clock skew có thể gây lỗi xác thực trên toàn cụm, dẫn tới áp lực bật bypass. Hãy:

- Duy trì NTP/time sync và monitor sai lệch.
- Diễn tập certificate rotation/trust bundle rollover.
- Test failure khi token/cert hết hạn, revoked hoặc sai audience.
- Có kế hoạch service recovery không cần vô hiệu xác minh certificate.

### 18.3. Key compromise và workload identity laundering

Một attacker chiếm credential của `orders-api` có thể được PEP nhìn như đúng workload nếu credential vẫn hợp lệ. Do đó phải:

- Bảo vệ keys/tokens khỏi exposure trong images, logs, environment và CI artifacts.
- Giảm lifetime, rotate và revoke theo risk.
- Hạn chế privileges của principal, không cấp wildcard database rights.
- Kiểm process/workload integrity, runtime behavior và application authorization.
- Kết hợp network anomaly detection dù identity checks PASS.

**Identity-aware** không có nghĩa miễn nhiễm credential theft hay supply-chain compromise.

## 19. Threat model: 30 sai lầm khi đồng nhất IP với danh tính

| ID | Rủi ro | Hậu quả | Biện pháp/quan sát xác minh |
|---|---|---|---|
| I01 | **Tin dải IP văn phòng là trusted users** | Compromised/guest hosts được cấp cùng quyền | MFA, per-user AuthZ, segmentation |
| I02 | **Tin VPN egress IP thay user identity** | Một tài khoản mất cắp vào được mọi app | VPN identity + per-app authorization |
| I03 | **NAT chung nhiều principals** | Gán sai user/workload hoặc allow quá rộng | Pre/post NAT mapping + session IDs |
| I04 | **Dynamic DHCP/cloud IP reassignment** | IP cấp lại cho chủ khác vẫn còn được phép | Ownership/time bounds, policy review |
| I05 | **Pod IP đổi khi reschedule** | App bị mất quyền hoặc allowlist nới rộng | Workload identity + CNI controls |
| I06 | **CDN/shared IP đích** | Cho phép dịch vụ/tenant ngoài ý định | Hostname validation, L7 resource controls |
| I07 | **Chỉ kiểm IPv4** | IPv6 bypass policy | Dual-stack mapping and tests |
| I08 | **IP sau proxy được coi client thật** | Attribution sai, app audit thiếu | Trusted proxy context and session linkage |
| I09 | **Tin X-Forwarded-For từ Internet** | IP ACL/rate-limit bypass qua header giả | Strip/overwrite at trusted edge |
| I10 | **Dùng HTTP Host/SNI như principal** | Đánh đồng virtual host với caller identity | mTLS/IdP-authenticated subject |
| I11 | **DNS record như authentication** | DNS poisoning/misrouting đưa tới endpoint sai | TLS hostname validation/trust |
| I12 | **Server cert bị dùng như client identity** | Cho bất kỳ caller nào có TLS tới server vào app | Distinguish TLS roles, require caller auth |
| I13 | **mTLS PASS = mọi API actions ALLOW** | Authorized workload truy cập sai tenant | Resource/action-level AuthZ |
| I14 | **Group/role cấp quá rộng** | Quyền identity trở thành allow-all kiểu mới | Least privilege, owner/review |
| I15 | **Issuer/audience token không kiểm** | Token dành cho app khác bị chấp nhận | Standards-based token validation |
| I16 | **ID token dùng thay access token** | Sai security semantics | Correct OAuth/OIDC token purpose |
| I17 | **Bearer tokens bị lộ** | Attacker replay bằng quyền của principal | Short lifetime, PoP, revocation |
| I18 | **Device identity không kiểm posture** | Compromised managed device vẫn có quyền | Fresh posture and runtime monitoring |
| I19 | **MAB/MAC như cryptographic proof** | Impersonation tại access edge | 802.1X/EAP-TLS hoặc isolated legacy zone |
| I20 | **Kubernetes label bị đổi** | Workload mạo nhóm được phép | RBAC/admission, trusted identity |
| I21 | **NetworkPolicy khác vẫn allow** | Xóa rule hẹp nhưng traffic chưa deny | Policy union + CNI dataplane tests |
| I22 | **Cloud tag/SG reference gọi là user auth** | Network metadata bị coi là danh tính user | Add mTLS/app authorization |
| I23 | **Mesh policy không enforce ở một path** | Bypass qua node/ambient/alternate ingress | PEP coverage and flow verification |
| I24 | **IdP outage gây fail-open** | Không xác minh được nhưng vẫn cho truy cập | Fail-safe/recovery design, audit |
| I25 | **Stale credentials/cached sessions** | Revoked principal còn dùng quyền | Session revocation/freshness tests |
| I26 | **Workload CA/attestation cấp nhầm identity** | Impersonation với credential hợp lệ | Issuance policies, trust audit |
| I27 | **Direct origin bypass ZTNA** | Bỏ qua MFA/posture/policy gateway | Origin firewall allow PEP only |
| I28 | **Audit chỉ có IP** | Không xác định ai gọi object nào | Verified principal+request+NAT correlation |
| I29 | **Bỏ toàn bộ IP controls** | DoS/pre-auth exposure/lateral reachability | Layered L3/L4 + identity controls |
| I30 | **Rollback identity migration mở lại any-any** | Security exception sống vô hạn | Scoped recovery, owner/expiry, tests |

### 19.1. Rủi ro nào thường nghiêm trọng nhất?

Phụ thuộc môi trường:

- **Admin plane:** chỉ allow office IP có thể dẫn tới truy cập trái phép trên thiết bị có quyền đổi routing/firewall.
- **Database/multi-tenant API:** gộp principal theo NAT hoặc subnet có thể làm truy cập chéo dữ liệu.
- **Kubernetes/cloud:** Workload thay IP liên tục khiến đội vận hành mở allowlist quá rộng.
- **OT/legacy:** Không thể thêm MFA/mTLS trực tiếp trên thiết bị, nên segmentation và gateway identity quan trọng.
- **Workload PKI compromise:** identity đáng tin trên giấy nhưng private key bị chiếm, cần rotation và detection.

Không chấm severity chỉ từ ID; cần đánh giá **exposure, tài sản, khả năng khai thác, blast radius và hiện trạng kiểm soát**.

## 20. Ma trận kiểm thử positive và negative

Toàn bộ phép thử nên thực hiện ở **lab/staging hoặc tài sản được cấp quyền**, có owner, phạm vi, thời gian, source identities và rollback. Những test nhằm xác minh **policy decisions**, không brute force tài khoản hay khai thác các dịch vụ của bên khác.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | Alice login qua IdP+MFA hợp lệ | Authenticated principal được ghi | IdP/session audit |
| N01 | User không xác thực cùng IP văn phòng | DENY resource access | PEP/authz verdict |
| N02 | Revoked VPN user dùng cùng exit IP | Không có quyền ứng dụng | VPN/app authorization log |
| P02 | Managed device compliant và user có quyền | ALLOW đúng app/resource | Device+user claims verified |
| N03 | Unmanaged device cùng public IP | DENY theo posture policy | PEP device decision |
| N04 | Device posture trở thành noncompliant | Session xử lý theo recheck policy | Posture/session events |
| P03 | Orders workload có mTLS identity đúng | Peer auth PASS | Workload trust/handshake logs |
| N05 | Workload khác cùng Pod subnet | DENY DB theo identity policy | Authz + network verdict |
| N06 | Principal hợp lệ gọi API sai tenant | DENY resource/action | App/DB audit |
| N07 | Client certificate thiếu trust/invalid SAN | TLS verification FAIL | TLS endpoint logs |
| P04 | Access token issuer/audience/expiry đúng | API kiểm token và quyền | Verification+authz evidence |
| N08 | Token sai audience | DENY | Token validation error |
| N09 | Token hết hạn/chưa có hiệu lực | DENY | Clock-aware validation |
| N10 | ID token dùng tại API cần access token | DENY | Token type/use check |
| N11 | Token unsigned/forged hoặc invalid signature | DENY | Cryptographic validator |
| N12 | Bearer token vừa revoke nhưng session còn | Gap được phát hiện/giới hạn | Revocation/session logs |
| P05 | EAP-TLS device credential valid | Network access theo NAC policy | RADIUS/NAC logs |
| N13 | MAC giống thiết bị hợp lệ nhưng không có credential | Không có cùng quyền EAP-TLS | NAC auth result |
| P06 | Firewall giảm reachability của untrusted zone | DENY network path | Firewall verdict |
| N14 | Cloud SG allow broader than policy | Detected by semantic review | Effective SG/route inventory |
| N15 | CNI có NetworkPolicy nhưng dataplane không enforce | Không gọi network isolation PASS | Flow verifier |
| N16 | Another NetworkPolicy still allows DB | Detect additive union | Full policy inventory + deny test |
| P07 | App request principal nối với network flow | Audit đúng user/workload/time | Request ID+NAT/EDR |
| N17 | Nhiều users chung NAT egress IP | Không gán cả traffic cho một user | Translation/session evidence |
| N18 | Client tự gửi forged X-Forwarded-For | Gateway không tin raw header | Header sanitation |
| N19 | Client tự gửi X-User=admin | Backend không coi là authenticated | Gateway/app auth checks |
| N20 | HTTP SNI/Host là tên internal nhưng caller lạ | Authz DENY | TLS/app logs |
| P08 | TLS server identity valid với hostname | Client validation PASS | Trust/hostname result |
| N21 | DNS trỏ IP proxy lạ, cert hostname mismatch | Client reject | TLS verification result |
| N22 | IPv4 policy deny nhưng IPv6 path mở | Gap được phát hiện | Dual-stack probes/flow |
| P09 | IP edge rate limiting ở approved lab | Preauth resource pressure giảm | Rate metrics và fairness |
| N23 | Shared NAT IP bị chặn gây collateral damage | Monitoring phát hiện/rollback | Per-identity error rates |
| P10 | Scoped emergency legacy exception | Owner/expiry/logging rõ | Exception register |
| N24 | Temporary any-any rule thiếu expiry | Policy governance chặn | Change review |
| P11 | Workload certificate rotation đúng | Allowed sessions khôi phục an toàn | CA/peer audit |
| N25 | Revoked/expired workload cert dùng lại | DENY | mTLS validation |
| N26 | IdP timeout ở admin endpoint | Theo fail-safe policy, không âm thầm allow-all | Decision/incident logs |
| P12 | Break-glass workflow được phê duyệt | Access hẹp, audit, review | Privileged access logs |
| N27 | Break-glass shared credential được dùng hằng ngày | Flag policy violation | AAA/secret access audit |
| P13 | Cloud/mesh policy chọn đúng resource | Verified principal only | PEP/flow logs |
| N28 | Direct origin bypass identity proxy | Network deny | Origin firewall logs |
| N29 | Source đổi cloud IP sau reschedule | Identity policy vẫn đúng | Workload/cert evidence |
| N30 | Static IP cũ cấp cho tenant khác | Old allowlist được review/xóa | Allocation/change logs |
| P14 | Security negative tests sau migration | Forbidden principal denied | Multi-layer enforcement evidence |
| N31 | Rollback làm tái mở source-subnet-wide DB access | Rollback gate fail | Semantic diff + deny test |
| N32 | SIEM chỉ có IP và không có principal | Audit gap được báo chính xác | Sensor/schema coverage |
| P15 | Monitoring correlation có UTC và identity | Incident timeline dựng được | Auth/app/NAT/flow records |
| N33 | App log “username” tự khai không có auth | Không quy thành verified identity | Audit provenance |
| N34 | Service A mTLS nhưng action-level AuthZ mất | Unauthorized operation vẫn DENY ở app | API test |
| P16 | Default-deny/resource-specific recovery | Luồng hợp lệ ALLOW, trái quyền DENY | Business+security controls |

**50 kịch bản kiểm thử:** 16 positive (P01–P16) và 34 negative (N01–N34). Không cần chạy tất cả trên mỗi thay đổi; chọn theo threat model, scope và platform. Nhưng **đối chứng quan trọng** là hai chủ thể **cùng source IP nhưng quyền khác nhau** phải nhận kết quả tương ứng với verified identity và authorization.

### 20.1. Định nghĩa “identity-based policy PASS”

Một test đạt khi:

1. Principal được xác thực bằng **nguồn/trust model phù hợp**, không chỉ username/header/IP tự khai.
2. Điều kiện policy match **đúng resource/action/tenant/context**.
3. Nguồn có quyền được ALLOW, nguồn không có quyền **bị DENY tại đúng PEP**.
4. Không tồn tại **alternate/bypass path** đến origin/data plane.
5. Network controls vẫn làm giảm reachable surface.
6. Telemetry nối được identity quyết định với flow/session/request.

### 20.2. Negative evidence cần positive control

Nếu unauthenticated client timeout khi gọi DB, có thể do DNS hỏng hoặc route blackhole, không phải mTLS AuthZ đúng. Cần một **allowed client chứng minh endpoint khỏe**, policy verdict và evidence tại enforcement point.

Nếu client nhận HTTP `403`, có thể đó là application gateway deny hoặc resource RBAC deny; để quy lý do phải xem **trusted decision logs**, không chỉ status code.

### 20.3. Test revocation và existing sessions

Một principal có thể đã bị disable nhưng **existing VPN, TLS, proxy hoặc database sessions** còn tiếp tục theo semantics sản phẩm. Bài test cần:

- New login/connection bị từ chối như policy.
- Existing session có bị terminate/recheck trong thời gian mục tiêu không.
- Token/cache lifetime và policy propagation được ghi.
- Khi không đáp ứng kỳ vọng, có compensating control/containment và incident process.

**Không tuyên bố revoke “ngay lập tức”** nếu chưa kiểm platform/session lifecycle.

## 21. Case study: một NAT IP hợp lệ nhưng caller trái quyền

### 21.1. Mô hình hư cấu

~~~mermaid
flowchart LR
    A["Orders API workload"] --> NAT["Egress NAT 203.0.113.50"]
    B["CI runner bị chiếm quyền"] --> NAT
    NAT --> FW["Firewall: allow 203.0.113.50 to DB"]
    FW --> DB["Customer DB / API"]
    IAM["IdP/PKI/Workload issuer"] -.-> A
    IAM -.-> B
    APPAUTH["Resource-level authz"] -.-> DB
~~~

Cả Orders API và CI runner đều nằm trên cùng cloud NAT gateway. Firewall cho phép public source IP `203.0.113.50` truy cập DB gateway. CI runner có network path nhưng **không có lý do nghiệp vụ** để gọi DB.

### 21.2. Dấu hiệu điều tra

| Dữ kiện | Có thể kết luận | Chưa đủ để kết luận |
|---|---|---|
| DB firewall log: source `203.0.113.50` | Flow đi qua egress NAT IP | Orders API là caller duy nhất |
| NAT mapping có source `10.2.4.17` | Một internal host/Pod tạo translation | User/process thực nếu thiếu endpoint logs |
| CNI record gắn workload `ci-runner` | Flow có thể liên quan CI runner | Credential đã bị đánh cắp hay không |
| DB gateway log thiếu verified principal | Authorization identity không quan sát được | Không tự kết luận dữ liệu đã bị đọc |
| App log ghi SQL actions và principal hợp lệ | Có thêm evidence về data access | Không chứng minh caller không bị compromise |

### 21.3. Lỗ hổng thiết kế

- Security decision nằm ở **source IP sau NAT**.
- Source IP này được dùng chung bởi workloads có quyền khác nhau.
- DB/app không kiểm workload identity đầy đủ hoặc policy quá rộng.
- Logs không nối được egress flow với request identity.

### 21.4. Hướng kiến trúc sửa

1. Inventory source workloads và dependencies, không xóa rule mù quáng.
2. Tạo network path/segmentation hẹp, nếu cần riêng gateway/private endpoint cho database.
3. Cấp workload identities theo service account/PKI, xác minh mTLS hoặc identity-aware gateway.
4. App/DB chỉ cấp permissions cho đúng principal/service và operations.
5. Test positive Orders API và negative CI runner **cùng NAT IP**.
6. Kiểm pre/post NAT mapping và app authorization logs cho incident attribution.
7. Migrate theo canary, giữ rollback safe và thu hẹp IP allowlist rộng.

### 21.5. Kết luận có bằng chứng

> “Egress NAT IP dùng chung đã cho CI runner đường kết nối mạng tới DB gateway. Điều đó cho thấy network-based policy thiếu phân biệt workloads, nhưng chưa đủ để khẳng định dữ liệu đã bị trích xuất. Cần xác minh request/DB audit và credential use. Mục tiêu thiết kế mới là chỉ verified Orders workload principal được thực hiện các thao tác DB được duyệt, trong khi CI runner bị từ chối dù đi qua cùng IP.”

**Không đánh đồng exposure và confirmed data breach**. Nếu có dấu hiệu compromise thật, chuyển sang incident response với data/app owners và lưu evidence hợp pháp.

## 22. Runbook A — Thu hẹp IP allowlist cho admin portal

### 22.1. Trước khi thay đổi

Một admin portal hiện chỉ kiểm `sourceIp in office-egress-addresses`. Mục tiêu là chuyển sang:

~~~text
Verified human identity
  + MFA assurance
  + managed/compliant device (nếu policy yêu cầu)
  + admin role cụ thể
  + resource-level authorization
  + network access chỉ qua trusted gateway
  + audit đầy đủ
~~~

**Preflight:**

- Có owner của portal, network policy và IdP.
- Biết các luồng hợp lệ từ office, VPN, remote users và automation.
- Kiểm proxy/cloud firewall đang ở đâu, portal có **direct origin bypass** không.
- Xác nhận IdP issuer, MFA policy, device posture và role mapping đã tin cậy.
- Có break-glass/OOB cho trường hợp IdP outage, không phụ thuộc portal đang được thay.
- Có bản sao cấu hình, security positive/negative tests và change window.

### 22.2. Thử theo giai đoạn

| Test | Nguồn | Expected |
|---|---|---|
| A1 | Admin có MFA và device hợp lệ, ở office | ALLOW đúng resource |
| A2 | Admin tương tự trên mạng di động được phép | ALLOW nếu policy không đòi office network |
| A3 | Non-admin ở cùng office IP | DENY admin actions |
| A4 | Revoked admin qua VPN exit IP | DENY |
| A5 | Client tự đặt `X-Forwarded-For` = office IP | Không tạo quyền |
| A6 | Đường trực tiếp tới origin IP bỏ qua proxy | DENY |
| A7 | Identity provider mất kết nối | Tuân theo safe fallback policy, không âm thầm allow |

### 22.3. Kết thúc

1. Bật identity enforcement trên canary group/portal trước.
2. Giám sát auth failures, SLO và source/role mismatches.
3. Thu hẹp origin firewall chỉ cho trusted PEP hoặc path được phép.
4. Gỡ allowlist IP rộng khi all gates PASS và owner chấp thuận.
5. Giữ audit và review fallback accounts, session expiry, revocation.

**Không đóng ticket** nếu remote admin vào được nhưng non-admin cùng office IP vẫn thực hiện admin action.

## 23. Runbook B — Chuyển Kubernetes API→DB sang workload identity

### 23.1. Kiến trúc ban đầu

~~~text
source: app-subnet /16
destination: db-subnet /24
port: TCP/5432
policy: allow
caller identity: not checked at network gateway
~~~

Một subnet chứa Orders API, CI runners và debug Pods. Để chuyển đổi:

1. Inventory Pods/namespaces/ServiceAccounts/owners và luồng thật.
2. Xem CNI/NetworkPolicy hỗ trợ gì; kiểm cả các policies additive.
3. Thiết kế **network policy chỉ cho Orders API source** tới DB, dưới RBAC/admission đảm bảo labels.
4. Cấp short-lived workload identities và tin cậy PKI/trust domain.
5. Enforce mTLS peer authentication và **workload principal authorization** ở chỗ có khả năng enforce.
6. DB/app xác minh operation/resource permissions, không cho toàn SQL actions.
7. Positive test từ Orders workload; negative từ CI runner **cùng subnet, cùng NAT gateway**.
8. Kiểm HA/failover, Pod reschedule, certificate rotation, IdP/CA outages.
9. Thu hẹp app-subnet allowlist rộng và rollback chỉ trong scope có phê duyệt.
10. Ghi provenance: Pod UID, ServiceAccount, verified SPIFFE ID, NAT flow, authorization decision.

### 23.2. Điều không được bỏ qua

- **Pod IP mới** không làm principal thay nếu identity bootstrapping đúng.
- **Label hoặc ServiceAccount name** chưa đủ nếu workload có thể bị mạo hoặc credential bị cấp sai.
- **Ingress traffic** từ node/hostNetwork/mesh gateway có thể có semantics khác.
- **mTLS STRICT** có thể gây outage nếu còn client chưa enrolled; cần rollout/canary.
- **Database account** vẫn cần least privileges, không dùng shared superuser.
- **NetworkPolicy deny** không thay application cross-tenant authorization.

### 23.3. Rollback safety

Nếu identity issuer gặp sự cố:

- Không lập tức khôi phục `any app-subnet → DB any`.
- Kiểm CA/issuer health và có thể dùng trusted cached credentials còn hợp lệ theo policy.
- Nếu cần exception, chỉ source Orders, đúng DB, đúng port, thời hạn và owner rõ.
- Xác minh CI runner/guest workloads không có quyền, kể cả connections cũ.

## 24. Runbook C — Ứng phó khi log chỉ có shared NAT IP

### 24.1. Tình huống

SOC thấy egress volume bất thường từ `203.0.113.50` đến một external API. IP này là NAT gateway của nhiều workloads. Không nên tuyên bố “Orders API exfiltrated” chỉ vì tên đó là ứng dụng quan trọng nhất trong subnet.

### 24.2. Điều tra theo bằng chứng

1. Bảo toàn firewall/flow logs với **5-tuple và UTC timestamps**.
2. Thu NAT translation logs theo source/destination ports/time window nếu có quyền.
3. Đối chiếu private source IP/Pod UID/node/ENI/process theo CNI/EDR.
4. Kiểm verified workload identities/service account/session IDs tương ứng.
5. Đối chiếu proxy/app request IDs và authorization outcomes; tách dữ liệu nhạy cảm.
6. Đánh giá DNS/SNI/Host/certificate context nhưng **không dùng chúng như caller identity**.
7. Nếu chứng cứ cho thấy compromise, phối hợp incident commander để containment có phạm vi.
8. Đo false positives do shared IP, CDN/multi-tenant và resource ownership.

### 24.3. Khi telemetry thiếu

Không tự điền “unknown” thành một principal do suy đoán. Ghi:

> “Đã quan sát flow từ public NAT IP theo sensor X tại T; log hiện có không đủ để ánh xạ chắc tới một workload/user. Cần NAT/EDR/application identity evidence để kết luận nguồn và tác động.”

Sự trung thực này giúp đội vận hành nhận ra **lỗ hổng observability** thay vì đưa ra attribution sai.

## 25. Troubleshooting identity-aware access

| Triệu chứng | Khả năng cần phân biệt | Điều phải kiểm chứng |
|---|---|---|
| User hợp lệ đổi Wi-Fi rồi bị deny | IP allowlist còn áp trong chain | Policy gates theo IP và identity |
| Cùng VPN exit IP, user bị disable vẫn vào được | App chỉ dựa IP, session chưa revoke | Authz/session/PEP logs |
| Orders API lỗi sau reschedule | IP allowlist stale, identity issuer lỗi | Pod identity và network flow |
| mTLS PASS nhưng API trả 403 | Resource authorization deny | App decision, role/tenant |
| Proxy log XFF khác firewall IP | Headers không trusted hoặc NAT/proxy chain | Trusted proxy topology |
| Cloud source tags khớp nhưng principal sai | Network metadata không phải mTLS proof | Token/cert identity |
| Group membership vừa thu hồi, phiên cũ còn | Cache/token/session lifetime | Revocation propagation |
| Server cert SAN đúng nhưng client bị deny | Client credential sai hoặc app RBAC | Distinct TLS/authz logs |
| Workload cert còn hạn nhưng trust lỗi | CA rotation/chain/trust domain | Issuer/keys/clock and trust bundle |
| Token decode được nhưng API deny | Signature/audience/expiry/permission sai | Standards-based validation |
| IPv4 source bị deny nhưng vẫn có traffic | IPv6/alternate route/VPN/peering | Dual-stack flow inventory |
| NetworkPolicy đã apply nhưng traffic vẫn cho qua | CNI missing, other allow policies, hostNetwork | Dataplane verdict và selectors |
| ZTNA proxy deny nhưng origin vẫn reachable | Direct origin/public IP bypass | Origin firewall and paths |
| Admin portal outage khi IdP down | Single point of failure/fail-closed | HA, constrained break-glass |
| NDR báo source IP nhưng không có principal | NAT/proxy/identity log gap | Correlation provenance |
| TLS SNI hostname thay đổi | ECH/proxy/virtual hosting | Not caller identity; endpoint logs |
| Device cert hợp lệ, posture fail | Managed state changed, stale attestation | Device posture time/source |
| Rate limiting theo IP chặn user hợp lệ | CGNAT/shared proxy | Multi-signal/user-scoped quotas |
| Migrated policy vẫn allow CI runner | Broad IP rule remains, PEP bypass | Effective policy and negative test |

### 25.1. Không ép hệ thống bỏ xác thực để có HTTP 200

Khi mTLS/token/IdP lỗi:

- Không tắt certificate validation, audience verification hoặc MFA để giảm báo lỗi.
- Không set “allow-all” rồi quên gỡ.
- Không dùng raw `X-User` hoặc `X-Forwarded-For` làm thay verified principal.
- Không clear toàn bộ active sessions hoặc reboot production không có impact review.
- Không ghi raw access tokens/private keys vào ticket.

Đánh giá root cause ở **identity issuance, trust validation, policy mapping, enforcement coverage, network path, application authorization** rồi khôi phục theo runbook phù hợp.

## 26. Metrics đánh giá rủi ro IP-dependence

| Chỉ số | Định nghĩa gợi ý | Diễn giải |
|---|---|---|
| **IP-only privileged paths** | Số/tỷ lệ tài nguyên nhạy cảm được bảo vệ chỉ bằng source IP | Cần scope/owner và risk ranking |
| **Shared-IP trust exposure** | Số principals khác quyền dùng cùng allowlisted NAT IP | Cần identity correlation |
| **Stale IP allowlist entries** | Rules có IP/resource không còn thuộc owner | Reassignment/expiry review |
| **Identity enforcement coverage** | % critical resources có verified principal + authz decision | Không chỉ đếm IdP users |
| **Negative test pass rate** | % unauthorized principals bị deny tại PEP | Cần test actual bypass paths |
| **Cross-tenant denial coverage** | % multi-tenant API operations có authz checks | Rủi ro data isolation |
| **Device posture freshness** | Tuổi posture assessment khi ra quyết định | Cache có thể stale |
| **Workload credential rotation** | Mức độ hoạt động của cấp/rotate/revoke | Có cert không có nghĩa lifecycle khỏe |
| **Session revocation delay** | Từ disable/revoke tới khi không còn quyền | Phải đo existing sessions |
| **Identity-to-flow correlation** | % high-value flows nối principal đáng tin tới 5-tuple | Không dùng IP inference làm “verified” |
| **Direct-origin bypass count** | Paths tránh identity gateway | Cần effective route/SG checks |
| **IdP/PEP availability & recovery** | SLO và break-glass drills | Không hy sinh security để đạt uptime |
| **Emergency exception overdue** | IP-only bypass quá hạn | Owner/review/cleanup |
| **False positive from IP blocking** | Người hợp lệ bị ảnh hưởng bởi CGNAT/shared IP | Kiểm rate/deny theo principal/context |

### 26.1. Đừng dùng KPI “càng ít IP rule càng tốt”

Một tổ chức có thể giảm số IP rules bằng cách mở một `any-any` lớn; đó không phải cải thiện. Một hệ thống khác có thể có nhiều IP rules hẹp cần thiết cho DDoS hoặc OT. Chỉ số tốt phải đo **effective reachability, principal authorization, negative test coverage, incident attribution và operational recovery**.

### 26.2. Không chỉ đếm người dùng có MFA

100% nhân viên dùng MFA không có nghĩa 100% workloads đã xác thực, DB đã kiểm cross-tenant authorization hoặc source IP log đủ quy user. Nên đo theo **tài nguyên và luồng rủi ro**, không chỉ theo danh sách accounts.

## 27. Bài tập vận dụng: so sánh hai phương án kiến trúc

### 27.1. Phương án A — Chỉ cho IP văn phòng

~~~text
Admin portal:
  Public IP: 198.51.100.20
  Firewall allow source: 203.0.113.50 (office NAT)
  Application auth: shared admin password
  MFA: disabled
  Device posture: not evaluated
  Authorization: all admins have full access
  Logs: source IP + HTTP status only
~~~

Điểm mạnh: rule network đơn giản, có một lớp chặn trước application và có thể giới hạn exposure thô.

Điểm yếu: NAT IP không phân biệt nhân viên/thiết bị, shared password không có accountability, thiếu MFA/resource authorization; nếu một máy bên trong đi qua office egress, nó có thể tiếp cận login và tấn công account.

### 27.2. Phương án B — Identity-aware và phân lớp

~~~text
Admin portal:
  Origin network: reachable only from approved ZTNA gateway
  User auth: trusted IdP + MFA
  Device trust: managed / posture requirements
  Policy: admin role AND specific resource/action
  Session: expiry/revocation and high-risk recheck
  Emergency: controlled, auditable break-glass
  Logs: principal + device ID + request/action + proxy/flow
  Network controls: restricted gateway and management paths
~~~

Điểm mạnh: nhiều users chung NAT IP vẫn có thể phân quyền khác nhau; remote workers không cần luôn đi ra từ cùng office IP; audit có principal và resource/action.

Đổi lại: phụ thuộc IdP/PEP/PKI, policy complexity, device enrollment và operational recovery. Nếu ZTNA proxy có direct-origin bypass hoặc fail-open, kiến trúc B có thể không đạt mục tiêu dù danh mục tính năng dài.

### 27.3. Câu hỏi thảo luận

1. Nếu office NAT IP bị cấp lại, phương án A chịu rủi ro gì?
2. Một nhân viên hợp lệ dùng laptop không compliant có được dùng admin portal ở phương án B không?
3. Với phương án B, cần chặn **direct origin** bằng cách nào ở lớp mạng?
4. Vì sao access token đúng issuer/audience vẫn chưa đủ khi user sửa tài nguyên tenant khác?
5. Nếu IdP hỏng, chọn allow-all có phải phương án availability tốt không?
6. Cần dữ liệu gì để điều tra ai đã xóa một admin user?
7. Một tường lửa chỉ có IP/port có thể đóng góp kiểm soát nào ở phương án B?
8. Nếu buộc phải giữ IP allowlist cho partner legacy, nên bổ sung gì và review theo chu kỳ ra sao?
9. Những positive/negative tests nào chứng minh hai users ở cùng IP được xử lý khác quyền?
10. Một rule dùng tag cloud thay CIDR có tự chứng minh workload possession of private key không?

### 27.4. Đáp án định hướng

Thiết kế B được ưu tiên cho privileged access khi có **enforcement thực**, backend bảo vệ direct origin, sessions/credentials được quản trị và có recovery. Không bỏ L3/L4; firewall có thể chỉ cho traffic tới gateway hoặc từ approved management network, còn **user identity/RBAC** do IdP/PEP/app xử lý. **Trust decisions phải được chứng minh bằng tests**, không chỉ bằng sơ đồ.

## 28. Thực hành thiết kế test lab không khai thác

### 28.1. Mục tiêu lab

Xây một môi trường mô phỏng (không cần thực thi lệnh thực tế lên production) với:

- Hai workload `orders-api` và `ci-runner` dùng chung NAT egress.
- Một DB gateway/HTTP test service sau firewall hoặc mesh policy.
- Hai workload có identity credentials khác nhau.
- Cùng một destination IP/port cho cả hai clients.
- Một policy chỉ ALLOW `orders-api` làm thao tác cụ thể.
- Một hệ thống log lưu **verified identity**, session/request ID và firewall 5-tuple.

**Giả thuyết:** IP-only policy không phân biệt hai workloads, nhưng identity-aware policy có thể ALLOW `orders-api` và DENY `ci-runner` dù dùng cùng NAT IP.

### 28.2. Bảng kết quả mẫu kỳ vọng

| Nguồn | IP sau NAT | Verified principal | Network reachability | App/service authorization |
|---|---|---|---|---|
| Orders API | `203.0.113.50` | `orders-api` | ALLOW | ALLOW operation được duyệt |
| CI runner | `203.0.113.50` | `ci-runner` | Có thể tới PEP, tùy policy | DENY protected operation |
| Không có credential | `203.0.113.50` | Unknown | Có thể tới PEP, tùy policy | DENY |
| Orders API token đã revoke | `203.0.113.50` | Revoked | Có thể tới PEP | DENY theo revocation policy |
| Orders API nhưng sai tenant | `203.0.113.50` | `orders-api` | ALLOW network | DENY trái resource boundary |

Các quyết định **network reachability** và **application authorization** là kết quả riêng. Trong kiến trúc có mTLS ngay tại gateway, các kết nối thiếu credential có thể bị từ chối **trước lớp HTTP**.

### 28.3. Các đối chứng bắt buộc

1. Kiểm Orders API sử dụng credential đã được cấp và DB/test service khỏe.
2. Kiểm CI runner không có quyền thực hiện protected operation, **không dùng lỗi DNS/route làm bằng chứng**.
3. Thay source IP lab trong scope mà không đổi identity — policy chủ yếu dựa identity không nên cấp quyền bất ngờ.
4. Thay identity nhưng giữ cùng NAT IP — policy phải xử lý khác.
5. Test expired/revoked/wrong-audience credentials.
6. Test TLS hostname/chain validation, không tắt security để làm test PASS.
7. Test direct origin bypass, IPv6 và alternate path nếu nằm trong thiết kế.
8. Xác minh logs không chứa raw tokens/private keys và có attribution hợp lệ.

### 28.4. Điều không được thử ngoài scope

Không brute force tài khoản, giả mạo access tokens để đột nhập production, scan public CIDR/CDN, khai thác thiết bị legacy, tắt certificate verification hoặc mở broad firewall rule “để test”. Chỉ dùng test identities, lab endpoints và permission phù hợp.

## 29. Các câu hỏi phỏng vấn và lỗi lập luận

### 29.1. Câu hỏi

1. IP address là danh tính hay network locator? Có thể là attribute trong authorization policy không?
2. Vì sao cùng NAT IP có thể đại diện nhiều principals?
3. Vì sao một user có thể đổi IP mà không mất identity?
4. Phân biệt source IP, HTTP Host, TLS SNI, verified client certificate SAN và authenticated principal.
5. Khi nào IP allowlisting vẫn cần thiết?
6. Vì sao một FQDN allowlist không phải workload authentication?
7. Nếu certificate hết hạn nhưng connection còn established, server sẽ hành xử thế nào? Điều gì cần kiểm theo platform?
8. Một verified `orders-api` workload có thể đọc mọi tenant data không?
9. OAuth ID token khác access token thế nào trong authorization của API?
10. Vì sao JWT decode được không chứng minh token hợp lệ?
11. Cần kiểm những claims/bằng chứng nào để API chấp nhận token?
12. SPIFFE ID có ý nghĩa gì? Việc chỉ có string `spiffe://` đã đủ an toàn chưa?
13. Một Kubernetes ServiceAccount name có tương đương verified workload identity không?
14. Tại sao NetworkPolicy chuẩn không thể mô tả một explicit deny có priority như một số vendor firewall?
15. Hai NetworkPolicies cùng chọn Pod có thể tạo kết quả ra sao?
16. Vì sao một cloud security-group reference không tự chứng minh người dùng cuối đã MFA?
17. Kỹ thuật nào hỗ trợ device authentication ở wired/Wi-Fi enterprise? Giới hạn của MAC filtering là gì?
18. Làm sao phòng một client tự gửi `X-Forwarded-For: 10.0.0.1` để vượt allowlist?
19. Nếu application chỉ thấy proxy IP thì log identity nên được thiết kế ra sao?
20. Làm sao điều tra source workload sau NAT khi source IP public dùng chung?
21. Tại sao fail-open khi IdP lỗi có thể gây rủi ro lớn?
22. Khi một principal bị disable, session cũ có bị kết thúc tức thì không?
23. Tại sao mTLS không chứng minh workload chưa bị compromise?
24. Bài kiểm thử nào chứng minh cùng IP nhưng khác principal vẫn được phân quyền đúng?
25. Làm sao đo tiến trình giảm lệ thuộc IP mà không chỉ đếm số ACL còn lại?

### 29.2. Gợi ý trả lời trọng tâm

- **IP là locator/context:** có thể dùng để giảm reachability nhưng không thay authenticated principal.
- **NAT/CGNAT:** nhiều hosts/users đi chung IP, cần translation/session/identity audit.
- **Zero Trust:** không cấp lòng tin chỉ theo location; kết hợp PEP, IdP, device/workload identity và per-resource AuthZ.
- **mTLS/SPIFFE:** xác thực peer theo credential/trust chain; không thay object-level authorization và runtime integrity.
- **OAuth/OIDC:** token đúng mục đích, xác minh issuer/audience/signature/lifetime/permissions; không tin raw JSON.
- **Kubernetes:** NetworkPolicy labels là matchers, CNI phải enforce; ServiceAccount identity cần trust mechanism, additive policy có thể mở đường ngoài ý định.
- **Proxy:** chỉ tin forwarded metadata từ trusted/sanitizing proxy; client-supplied headers không là identity.
- **Fail-safe:** chuẩn bị IdP/CA HA, constrained break-glass và session revocation tests; tránh broad fail-open.
- **Kiểm thử:** same-IP/different-principal positive/negative controls, không chỉ ping/curl success.

## 30. Checklist tránh sai lầm “phụ thuộc vào IP thay vì identity”

### 30.1. Khi thiết kế policy

- [ ] Phân biệt **network location** với authenticated user/device/workload principal.
- [ ] Xác định owner, resource, action, tenant, sensitivity và security boundary.
- [ ] IP/subnet rules được dùng cho **network scope**, không tự cấp tất cả quyền.
- [ ] Không coi office/VPN IP hoặc proxy/CDN IP là người dùng tin cậy.
- [ ] Có inventory NAT/CGNAT, VPN, proxies, cloud gateways, IPv4/IPv6 và IP lifecycle.
- [ ] Có kế hoạch khi DHCP/cloud/Pod IP thay hoặc bị tái cấp.
- [ ] Không coi DNS/CNAME/HTTP Host/SNI là cryptographic identity.
- [ ] Chọn human IdP+MFA, device identity/posture và workload identity phù hợp.
- [ ] Resource/API kiểm authorization cho từng action/tenant khi cần.
- [ ] Không coi mTLS hay VPN thành công là quyền truy cập mọi database/object.
- [ ] Network L3/L4 controls vẫn chặn paths không cần thiết và DoS tiền xác thực.
- [ ] Direct origin/alternate route không được bypass identity enforcement point.

### 30.2. Khi xác thực và cấp quyền

- [ ] Token/certificate được kiểm **issuer/trust, audience, validity và intended use**.
- [ ] Không dùng ID token thay access token hoặc decode JWT thay xác minh.
- [ ] Không dùng raw user/role/IP headers từ Internet làm verified claims.
- [ ] Trusted proxies có strip/overwrite headers và backend trust được kiểm.
- [ ] SPIFFE trust domains/SVID/key rotation được quản lý theo owner.
- [ ] Device identity không bị nhầm với posture hoặc quyền của human.
- [ ] Kubernetes ServiceAccount/labels được quản lý RBAC/admission, không coi là bằng chứng mật mã khi thiếu trust.
- [ ] CNI/service mesh/PEP thực sự enforce trên mọi data paths liên quan.
- [ ] RBAC/ABAC/ReBAC policy có principal/resource/action/context cụ thể.
- [ ] Có session freshness, credential revocation, rotation và cache TTL policy.
- [ ] IdP/PKI/PEP outage có response, không mặc định cho phép mọi thứ.
- [ ] Break-glass có least privilege, MFA/compensating oversight khi khả thi, audit và expiry.

### 30.3. Khi migrate từ IP-based access

- [ ] Có inventory owner và actual hit/flow usage của allowlists.
- [ ] Đã xử lý legacy/OT/partner dependencies, tránh xóa rules đột ngột.
- [ ] Thiết lập trusted identity issuance và resource policy trước cắt IP rules.
- [ ] Có shadow evaluation/canary khi platform hỗ trợ, không tự giả định.
- [ ] Có positive/negative test từ principals khác nhau **cùng NAT IP**.
- [ ] Có tests IPv4/IPv6, direct origin, shared proxy, VPN và cloud routes.
- [ ] Có test certificate rotation, revoked principal và IdP outage.
- [ ] Có rollback safe state và monitoring, không nới any-any khi lỗi.
- [ ] Đã thu hẹp IP rules cũ theo PEP/source identity và gỡ ngoại lệ hết hạn.
- [ ] Desired/running/effective config được kiểm tra; có owner cho drift.

### 30.4. Khi giám sát và ứng phó

- [ ] Logs có **verified principal** và source/issuer, không chỉ một trường username tự khai.
- [ ] Có source/destination 5-tuple và NAT translations theo thời gian/ports.
- [ ] Có request/session/resource ID và authorization verdict từ application/PEP.
- [ ] Clock/timezone và event-vs-ingest time được chuẩn hóa.
- [ ] Privacy: không lưu bearer tokens, private keys, passwords hoặc PII thừa.
- [ ] Phân biệt **same-IP correlation** với evidence thực quy về user/workload.
- [ ] Monitoring có thể phát hiện certificate expiration, IdP/PEP outage và revoke failures.
- [ ] Nếu một flow bất thường chỉ có IP, báo **attribution uncertainty**, không tự quy actor.
- [ ] Có incident path khi credential compromise hoặc unauthorized access được xác minh.
- [ ] Remediation được xác nhận bằng business ALLOW và security DENY ở đúng enforcement point.

## 31. Tóm tắt quyết định cho kiến trúc sư

Trước khi chấp nhận một rule “allow IP X”, hãy hỏi:

1. **Địa chỉ này thuộc ai ở thời điểm nào, và có dùng chung qua NAT/proxy/CDN không?**
2. **Rule đang kiểm network reachability hay đang vô tình đóng vai trò user/workload authentication?**
3. **Chủ thể được phép thực sự là human, device, workload hay một tenant/resource?**
4. **Credential/identity được cấp, xác minh, rotate và revoke thế nào?**
5. **Ở đâu thực thi authorization cho operation và data object?**
6. **Có IPv6/VPN/peering/direct-origin path bỏ qua PEP không?**
7. **Điều gì xảy ra khi IdP/CA/PEP lỗi, khi user bị thu hồi hoặc source IP đổi?**
8. **Logs có thể nối một flow sau NAT với verified principal và action không?**
9. **Đã test cùng IP khác quyền và khác IP cùng identity hay chưa?**
10. **IP control được giữ vì lý do L3/L4/DoS/legacy nào, và có owner/review không?**

**Ghi nhớ:** **Địa chỉ IP không phải danh tính đã được xác thực.** IP vẫn cần cho định tuyến, phân đoạn, firewall, giảm exposure trước xác thực và điều tra mạng, nhưng **không nên là điều kiện duy nhất để cấp quyền cho người dùng hay workload truy cập tài nguyên nhạy cảm**. Kiến trúc tốt kết hợp **verified human/device/workload identity, least-privilege resource authorization, L3/L4 segmentation, certificate/token lifecycle, trusted proxy handling, session revocation, cross-layer telemetry và kiểm thử cả ALLOW lẫn DENY**. Khi cùng một NAT IP phục vụ các chủ thể khác quyền, **quyết định truy cập phải dựa trên danh tính và hành động có chứng cứ — không phải nơi gói tin xuất hiện**.
