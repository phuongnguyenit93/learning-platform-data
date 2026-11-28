# Identity-aware proxy: kiểm soát truy cập ứng dụng theo danh tính trong Zero Trust Network Access

Một nhân viên làm việc từ xa cần mở trang quản trị nội bộ, một kỹ sư hỗ trợ cần truy cập API vận hành và một đối tác chỉ được xem báo cáo của riêng mình. Cách triển khai truyền thống có thể cấp VPN rồi cho người dùng đi vào cả một dải mạng nội bộ. Khi đó, dù ứng dụng có thêm login, **bề mặt mạng được mở cho thiết bị sau VPN có thể rộng hơn quyền mà công việc thực sự yêu cầu**. Nếu thông tin đăng nhập bị đánh cắp hoặc máy khách bị xâm nhập, khả năng dò tìm dịch vụ và di chuyển ngang trong mạng trở thành vấn đề.

**Identity-aware proxy (IAP)** là một **điểm trung gian kiểm soát truy cập** được đặt trên đường vào tài nguyên; nó quyết định có chấp nhận kết nối hoặc request hay không dựa trên **danh tính đã xác thực, tài nguyên được yêu cầu và các điều kiện chính sách** như nhóm/quyền, tình trạng thiết bị, mức xác thực hoặc ngữ cảnh rủi ro nếu có nguồn tín hiệu đáng tin. Sau khi cho phép, proxy **chuyển tiếp chỉ tới ứng dụng/đích được cấp quyền**, thay vì mặc nhiên cấp quyền đi lại trong cả một mạng.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề này nằm trong chương **Zero Trust Network Access** và kết nối trực tiếp với phân đoạn mạng, firewall, VPN, TLS/mTLS, PKI, DNS, IDS/IPS, Kubernetes/cloud networking, xác thực kết nối và giám sát xâm nhập. Đối tượng nghiên cứu là **identity-aware proxy như một điểm thực thi chính sách của kiến trúc Zero Trust**, không phải mọi reverse proxy hoặc một trang đăng nhập SSO đều tự trở thành ZTNA.

> **Thông điệp trung tâm:** “Đăng nhập thành công” không đồng nghĩa “được truy cập mọi ứng dụng”. IAP phải xác minh **đúng principal, đúng ứng dụng/đường dẫn/hành động, đúng điều kiện ngữ cảnh tại thời điểm quyết định**, và hạ tầng phải ngăn **đường đi vòng tới origin**. Quyết định ALLOW tại proxy không thay authorization ở backend theo **user, tenant và dữ liệu cụ thể**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mục đích của **Identity-aware proxy** và mối liên hệ với các nguyên tắc **Zero Trust Network Access (ZTNA)**.
2. Phân biệt IAP với **VPN cấp quyền mạng, reverse proxy thuần túy, SSO portal, WAF, API gateway, service mesh và firewall**.
3. Mô tả các vai trò **Policy Enforcement Point (PEP), Policy Decision Point (PDP), Policy Information Point (PIP), identity provider (IdP)** và ứng dụng được bảo vệ.
4. Phân tích hành trình **client → proxy → IdP/policy → ứng dụng**, bao gồm định danh, xác thực, điều kiện thiết bị và quyết định truy cập.
5. Hiểu các thành phần của **OIDC/OAuth 2.0**, token validation, cookie/session, MFA và các sai sót phổ biến như **nhầm ID token với access token**, thiếu kiểm tra audience/issuer hoặc tin header tự do.
6. Thiết kế policy **least privilege** theo principal, resource, action và context, đồng thời xử lý các trường hợp **DENY/UNKNOWN** rõ ràng.
7. Ngăn truy cập thẳng tới **origin/backend** qua IP, DNS, LoadBalancer, NodePort, VPN hoặc peering khiến IAP bị bypass.
8. Đánh giá TLS/mTLS ở từng hop, reverse proxy identity headers, delegated authorization và bảo vệ credentials.
9. Xem xét các giao thức **HTTP, gRPC, WebSocket, SSH/TCP** và giới hạn khi áp identity-aware policy.
10. Thiết kế HA/fail-closed, observability, quyền riêng tư, incident runbook và **ma trận kiểm thử tích cực/tiêu cực**.

## 2. Zero Trust không đồng nghĩa “không tin ai”

Zero Trust là cách thiết kế trong đó **vị trí mạng nội bộ không được xem là bằng chứng đủ để cấp quyền**. Tổ chức phải xác định người dùng/workload/thiết bị, chỉ cấp quyền cần thiết và liên tục quản trị rủi ro theo **policy**. Mức độ kiểm tra lại có thể khác nhau tùy request, thời hạn phiên và khả năng sản phẩm; **không có nghĩa thực hiện MFA trên từng gói tin**.

### Ba quan điểm nền tảng

- **Verify explicitly:** dùng bằng chứng danh tính và ngữ cảnh có nguồn gốc đáng tin, không tin vì thiết bị nằm trong subnet công ty.
- **Least-privilege access:** cấp quyền tới ứng dụng và hành động cụ thể, trong khoảng thời gian/điều kiện phù hợp, tránh mở cả mạng.
- **Assume breach:** hệ thống phải chịu được khả năng một credential, endpoint hoặc thành phần nội bộ bị xâm nhập; hạn chế lateral movement và tăng khả năng phát hiện.

### IAP phục vụ phần nào?

IAP chủ yếu nằm ở **điểm truy cập ứng dụng/tài nguyên**, nơi có thể buộc xác thực và ra quyết định trước khi lưu lượng chạm backend. Zero Trust rộng hơn IAP: nó còn gồm **asset inventory, device security, microsegmentation, workload identity, mã hóa, data protection, monitoring, IAM lifecycle** và điều tra sự cố.

**IAP là thành phần của kiến trúc Zero Trust, không phải bằng chứng tổ chức đã hoàn tất Zero Trust** chỉ vì một ứng dụng có URL đăng nhập qua proxy.

## 3. Từ cấp quyền mạng sang cấp quyền ứng dụng

Hãy xét hai mô hình truy cập khác nhau.

~~~text
MÔ HÌNH VPN CẤP MẠNG

Remote laptop
      |
   VPN tunnel + account authentication
      |
  Corporate CIDR / subnet
      |
   +---- App A :443
   +---- App B :8443
   +---- Admin :22
   +---- Other reachable services

Hiệu lực truy cập thực tế còn phụ thuộc firewall,
ACL và authentication của từng dịch vụ.
~~~

~~~text
MÔ HÌNH IDENTITY-AWARE APPLICATION ACCESS

Remote laptop
      |
      | HTTPS / protected application protocol
      v
   Identity-aware proxy [PEP]
      |  - authenticate identity
      |  - evaluate policy
      |  - deny or permit resource
      v
   App A / authorized route

  App B, Admin SSH, database:
    không tự reachable chỉ vì đã vào App A.
~~~

**VPN không mặc nhiên kém an toàn**, vì VPN có thể được kết hợp với firewall, identity-based ACL, posture checks và các chính sách truy cập hẹp. Điểm khác biệt trong thiết kế là **đối tượng quyền chính**: IAP hướng tới ứng dụng/tài nguyên cụ thể; VPN cơ bản thường cung cấp một khả năng kết nối mạng rồi cần thêm chính sách để giới hạn.

### Không đồng nhất đường đi với quyền truy cập

| Câu hỏi | Kiểm soát thích hợp |
|---|---|
| Thiết bị có route tới IP không? | VPN/route table/cloud firewall |
| Client có thể gửi gói tới origin không? | SG/NACL/firewall/NetworkPolicy |
| Người dùng là ai? | IdP, MFA, credential/device binding |
| Phiên có quyền mở ứng dụng không? | IAP policy tại PEP/PDP |
| API method hoặc dữ liệu cụ thể có được phép không? | API/application authorization |
| Truy cập có phù hợp posture/risk hiện tại không? | Device trust/conditional access với tín hiệu được kiểm chứng |

## 4. Identity-aware proxy khác các thành phần lân cận

| Thành phần | Vai trò thường gặp | Không nên suy diễn |
|---|---|---|
| **Reverse proxy** | Terminate/forward HTTP/TLS, load balancing, routing | Không nhất thiết có xác thực và access policy |
| **SSO portal** | Đăng nhập một lần, liên kết các ứng dụng | Chưa chắc chặn truy cập trực tiếp tới backend |
| **Identity-aware proxy** | Enforce quyết định truy cập ở proxy theo identity/context | Không tự bảo đảm backend object authorization |
| **ZTNA connector/broker** | Tạo đường private tới ứng dụng cho client đã được cấp quyền | Không phải mọi sản phẩm hỗ trợ mọi giao thức |
| **VPN** | Tạo tunnel giữa client và mạng/đầu cuối | Không mặc nhiên giới hạn tới một application |
| **WAF** | Phân tích/giới hạn traffic HTTP theo quy tắc ứng dụng | Không thay IAM/SSO/object-level auth |
| **API gateway** | API routing, auth, quotas, transformations | Chỉ thực thi user policy nếu cấu hình và bảo vệ đường bypass |
| **Firewall/NetworkPolicy** | Chặn/cho gói theo mạng, port, workload | Không tự hiểu token/nhóm/user và resource |
| **Service mesh mTLS** | Xác thực workload và mã hóa giữa proxies/workloads | Workload identity không đồng nghĩa end-user quyền |

Một sản phẩm thực tế có thể kết hợp **nhiều chức năng trong cùng hệ thống**. Không phân loại bảo mật chỉ theo tên thương mại: cần xác định **enforcement point, identity proof, policy scope và đường truy cập ngoài thiết kế**.

## 5. Các thành phần PEP, PDP, PIP và IdP

Một kiến trúc IAP điển hình gồm:

~~~text
                  Identity Provider (IdP)
                     OIDC / MFA
                         ^
                         |
Client -> [IAP / PEP] ---+---> [PDP / Policy Engine]
             |                        ^
             |                        |
             |                   [PIP / Context]
             |                 groups, device, risk
             |
             | ALLOW only
             v
      [Protected origin]
       App / API / service
~~~

Đây là **sơ đồ logic**, không phải yêu cầu mọi sản phẩm phải có 4 server vật lý khác nhau. Các chức năng PEP, PDP và PIP có thể chạy cùng service, được phân tán hoặc là dịch vụ managed cloud.

### Định nghĩa nhiệm vụ

| Thành phần | Trách nhiệm | Rủi ro nếu sai |
|---|---|---|
| **Client/User** | Yêu cầu truy cập và cung cấp bằng chứng xác thực | Credential compromise, session hijack |
| **IdP** | Xác thực principal; cấp token/claims theo cơ chế | Mis-issued token, stale group, MFA bypass |
| **PEP** | Chặn request, xác định context, áp kết quả ALLOW/DENY | Bypass origin, header spoofing, fail-open |
| **PDP** | Tính quyết định dựa trên policy và context | Over-broad policy, decision cache sai |
| **PIP** | Cung cấp tín hiệu như nhóm, device posture, resource sensitivity | Tín hiệu cũ, không đáng tin hoặc giả mạo |
| **Origin app** | Tiếp nhận request sau policy; tự kiểm tra quyền nghiệp vụ | Trust proxy sai, IDOR/BOLA, tenant leak |
| **Audit/monitoring** | Ghi quyết định và phát hiện bất thường | Ghi token/PII hoặc thiếu bằng chứng |

**PEP là điểm thực thi**: khi PDP báo DENY hoặc không trả lời theo chính sách fail-closed, PEP phải không chuyển tiếp request được yêu cầu bảo vệ. Không được cho phép truy cập trực tiếp origin nếu đã trông đợi PEP thực thi policy.

## 6. Ví dụ kiến trúc IAP bảo vệ ứng dụng nội bộ

Giả sử công ty có ba dịch vụ:

- **hr-web**: nhân viên được xem dữ liệu của chính mình.
- **finance-admin**: chỉ một nhóm nhỏ được quản trị tài chính.
- **metrics**: chỉ đội vận hành/collector được phép xem.

~~~text
                          Remote employee
                                |
                           HTTPS :443
                                |
                                v
                    +-----------------------+
                    | Identity-aware proxy  |
                    | Policy + OIDC session |
                    +-----------+-----------+
                                |
                   +------------+-------------+
                   |            |             |
                   v            v             v
               hr-web       finance-admin    metrics
               private       private         private
               :8080         :8443           :9090

           Private origins NOT directly exposed
           to arbitrary Internet or VPN clients.
~~~

### Ma trận quyền tối thiểu

| Principal | hr-web | finance-admin | metrics |
|---|---|---|---|
| Nhân viên thông thường | ALLOW ứng dụng; app giới hạn hồ sơ cá nhân | DENY | DENY |
| Finance admin đủ điều kiện | ALLOW theo ứng dụng | ALLOW khi đáp ứng MFA/device/risk policy | DENY trừ khi có quyền khác |
| Operator | ALLOW nếu có tư cách nhân viên | DENY trừ khi được cấp | ALLOW theo role/policy |
| Đối tác bên ngoài | Chỉ những route được ký hợp đồng | DENY | DENY |
| Tài khoản không xác thực | Chuyển tới login hoặc DENY theo policy | DENY | DENY |

**Nhóm “finance-admin” không có nghĩa được xem mọi báo cáo, mọi tenant.** Sau khi IAP cho vào ứng dụng, backend vẫn phải kiểm tra **operation và resource owner**.

## 7. Hành trình một request được phép

~~~text
(1) User -> IAP GET https://finance.example.test/
         |
(2) IAP chưa có session hợp lệ
         |
(3) Redirect tới IdP/authorization endpoint
         |
(4) User xác thực, MFA khi policy yêu cầu
         |
(5) IdP trả authorization response về callback đã đăng ký
         |
(6) IAP kiểm tra state, token, issuer, audience, nonce
    và liên hệ identity với session theo flow đang dùng
         |
(7) PEP yêu cầu quyết định PDP:
    principal + resource + action + posture + context
         |
    DENY ----------------------> Không forward tới origin
         |
    ALLOW
         |
(8) IAP chuyển tiếp theo route đã duyệt tới finance origin
         |
(9) App kiểm tra user/tenant/object authorization
         |
(10) Response trả về qua IAP, có audit và giới hạn session
~~~

**Không phải tất cả request đều redirect lại IdP**. Một session hợp lệ có thể được sử dụng trong một khoảng thời gian theo policy; việc **đánh giá lại** có thể thực hiện mỗi request, theo TTL, sau sự kiện thay đổi posture hoặc trên những hành động nhạy cảm. Khi đánh giá kiến trúc phải biết **lúc nào policy thực sự được tính lại**, không mặc định có kiểm tra liên tục ở mọi lớp.

### Quan hệ giữa login, admission và application auth

1. **Authentication:** principal đã được xác thực phù hợp.
2. **IAP authorization:** principal có được vào application/route với context hiện tại?
3. **Application authorization:** principal có quyền làm hành động cụ thể trên object/tenant?
4. **Session lifecycle:** quyền có còn hợp lệ khi nhóm, thiết bị hoặc rủi ro thay đổi?

## 8. OIDC, OAuth 2.0 và giao thức xác thực liên quan

IAP dùng nhiều phương thức nhận diện; với trình duyệt và ứng dụng hiện đại, **OpenID Connect (OIDC)** trên nền OAuth 2.0 là lựa chọn thường gặp. Cần phân biệt mục đích:

- **OAuth 2.0:** framework ủy quyền để cấp **access token** tới resource/API theo cơ chế.
- **OIDC:** lớp **xác thực** bổ sung identity information, đặc biệt **ID token** cho relying party.
- **SAML 2.0:** một mô hình SSO liên kết danh tính khác, phổ biến trong nhiều môi trường doanh nghiệp.
- **LDAP/Kerberos:** có thể là nguồn định danh hoặc phương thức chứng thực trong kiến trúc phù hợp, nhưng không tự tạo một IAP.

### Phân biệt ba credential/token phổ biến

| Đối tượng | Mục đích | Cảnh báo |
|---|---|---|
| **ID token** | Chứng minh sự kiện xác thực cho OIDC client được định danh | Không tự dùng như access token cho mọi backend API |
| **Access token** | Cấp quyền gọi resource server theo audience/scope/policy | Resource server phải xác minh token đúng cho chính mình |
| **Proxy session cookie** | Duy trì session tại IAP/browser theo TTL/chính sách | Không được biến cookie thành quyền vĩnh viễn |

Một số sản phẩm có cách đóng gói session/token khác nhau. **Không suy một JWT có trường email thì là token đáng tin**; cần kiểm tra signature, issuer, audience và các điều kiện bổ sung.

## 9. Authorization Code Flow, PKCE và redirect an toàn

Với browser-based IAP dùng OIDC, **Authorization Code Flow** kèm **PKCE** là một mô hình phổ biến để giảm nguy cơ mã authorization code bị đổi chủ hoặc dùng ngoài luồng hợp lệ.

~~~text
Browser         IAP / OIDC Client               IdP
  |                    |                         |
  | GET protected app  |                         |
  |------------------->|                         |
  |                    | Generate state/nonce,    |
  |                    | PKCE code_verifier       |
  |<--- redirect ------|                         |
  |--------- authorize ------------------------->|
  |                    |                         |
  |<--------- redirect with code and state ------|
  |--- callback ------>|                         |
  |                    | Verify state; exchange  |
  |                    | code + code_verifier    |
  |                    |------------------------>|
  |                    |<-- tokens / response ---|
  |                    | Verify identity/claims  |
  |<-- secured session |                         |
~~~

### Các kiểm tra tối thiểu

1. **redirect_uri** phải khớp giá trị đã đăng ký, tránh open redirect hoặc code exfiltration.
2. **state** gắn yêu cầu xác thực với browser session và hỗ trợ bảo vệ CSRF/login CSRF.
3. **nonce** được dùng và xác minh theo ngữ nghĩa OIDC flow/token để ngăn replay/substitution liên quan.
4. **PKCE code_verifier/challenge** phải được tạo/kiểm tra đúng flow, không dùng giá trị cố định.
5. Bảo vệ **client secret** nếu có và dùng client authentication phù hợp; PKCE không thay xác thực client khi client thuộc loại confidential.
6. Kiểm tra **issuer, signing keys, ID token audience, timestamps** và những điều kiện OIDC áp dụng.
7. Không trả **access token hoặc session cookie** qua query string, log, referer hay HTML không cần thiết.
8. Có session fixation protection và logout/revocation design.

**PKCE không thay MFA, không thay quyền truy cập tài nguyên và không giải quyết origin bypass.** Nó chỉ giải quyết một nhóm rủi ro trong authorization code flow.

## 10. Xác minh token: token hợp lệ là đúng token cho ai?

Nếu IAP hoặc backend nhận JWT/OIDC claims, xác minh chữ ký chỉ là một điều kiện.

### Checklist JWT validation

| Kiểm tra | Vì sao quan trọng |
|---|---|
| **Token type/purpose** | Không dùng ID token làm access token hoặc ngược lại |
| **Issuer (iss)** | Chỉ nhận đúng IdP/issuer theo trust policy |
| **Audience (aud)** | Token phải được cấp cho IAP/resource phù hợp, không reuse từ ứng dụng khác |
| **Signature/key (JWKS)** | Xác minh với khóa đáng tin gắn issuer; không tự tin header jku/kid tùy ý |
| **Algorithm allowlist** | Không chấp nhận downgrade/algorithm confusion |
| **Expiry (exp) / not-before (nbf)** | Giới hạn thời gian; clock skew có kiểm soát |
| **Subject (sub)** | Danh tính ổn định theo issuer, không dựa duy nhất vào email display |
| **Authorized party / nonce / auth_time** | Kiểm tra khi OIDC client/flow và policy yêu cầu |
| **Groups/roles/scopes** | Claims phải đúng nguồn, đúng audience và freshness policy |
| **Revocation/session status** | Token còn hiệu lực theo cơ chế revoke/refresh được hệ thống hỗ trợ |

### Ví dụ claim set giả lập

~~~json
{
  "iss": "https://idp.example.test/tenant-company",
  "sub": "user-example-013",
  "aud": "iap-finance-client",
  "exp": 1795858200,
  "iat": 1795854600,
  "amr": ["pwd", "mfa"],
  "groups": ["finance-readonly"]
}
~~~

Đây là **JSON mô phỏng**, không phải JWT đã được ký, không có giá trị đăng nhập. **amr/groups** không phải mọi IdP đều phát giống nhau hoặc luôn đủ để chứng minh **mức xác thực gần đây**; phải hiểu hợp đồng claim, thời điểm kiểm tra và cách quản lý nhóm.

### Opaque tokens và introspection

Không phải access token nào cũng là JWT tự chứa. **Opaque token** có thể đòi kiểm tra ở authorization server/token introspection endpoint. Lựa chọn giữa validation cục bộ, introspection, cache và token exchange phải cân bằng **độ mới quyền, độ trễ, độ sẵn sàng IdP và bảo vệ dữ liệu**; không cho token tùy ý qua chỉ vì IdP timeout.

## 11. MFA, step-up authentication và quyền nhạy cảm

Với một app công khai chỉ đọc, mức xác thực có thể khác với quyền **phê duyệt chuyển tiền, tạo admin API key hoặc xem hồ sơ nhân sự nhạy cảm**.

### Chính sách mẫu theo độ nhạy

| Resource/action | Yêu cầu minh họa |
|---|---|
| **hr-web: xem hồ sơ bản thân** | Login đã xác thực và session còn hiệu lực |
| **finance-report: đọc báo cáo theo vai trò** | Nhóm finance được duyệt, device posture theo policy |
| **finance-admin: thay cấu hình thanh toán** | Nhóm admin + MFA/step-up gần đây + thiết bị đáp ứng policy |
| **production-support: vào console** | Just-in-time approval, session giới hạn và audit |
| **unknown actor: mọi route nhạy cảm** | DENY, không chuyển tới backend |

**MFA/step-up** bổ sung bằng chứng xác thực mạnh hơn theo rủi ro, nhưng **không tự chứng minh thiết bị lành mạnh hoặc user có quyền với object cụ thể**. Một phiên từng hoàn tất MFA có thể bị đánh cắp, hoặc người dùng bị dụ chấp nhận yêu cầu MFA. Với quyền rất nhạy cảm, cân nhắc **phishing-resistant authentication**, bảo vệ session và giới hạn thời gian theo policy.

### Bắt buộc xác thực lại khi nào?

- Vào route có độ nhạy cao hơn.
- Device posture chuyển từ compliant sang unknown/noncompliant.
- Có tín hiệu credential compromise hoặc hành vi rủi ro bất thường.
- Quyền hoặc nhóm bị thu hồi.
- Session vượt thời hạn tuyệt đối hoặc thời gian không hoạt động.

**Không tự đặt cùng một chu kỳ re-auth cho mọi tổ chức.** Phải dựa trên risk model, usability, khả năng thu thập tín hiệu và hợp đồng SLA.

## 12. Device posture: thiết bị nào được coi là đáp ứng chính sách?

Nguyên tắc truy cập dựa trên danh tính thường kết hợp trạng thái thiết bị (*device posture*), ví dụ thiết bị có được quản lý, mã hóa, bật kiểm soát endpoint hoặc cập nhật phiên bản tối thiểu hay không.

### Tín hiệu có thể dùng

| Tín hiệu | Có thể hỗ trợ quyết định gì? | Điểm cần kiểm chứng |
|---|---|---|
| **Managed/enrolled device** | Thiết bị được đăng ký trong hệ thống quản lý | Chứng cứ enrollment có được bảo vệ/thu hồi đúng? |
| **OS security update** | Còn hỗ trợ và đáp ứng bản vá tối thiểu | Dữ liệu kiểm kê có cập nhật và khớp máy không? |
| **Disk encryption** | Giảm nguy cơ lộ dữ liệu khi mất máy | Trạng thái đến từ nguồn quản trị đáng tin? |
| **Endpoint protection/EDR** | Đánh giá kiểm soát đầu cuối đang hoạt động | Không coi “agent running” là luôn sạch malware |
| **Device certificate** | Ràng buộc thiết bị theo credential được cấp | Issuance, expiry, revocation và key protection |
| **Browser/agent attestation** | Xác nhận môi trường trình duyệt/agent theo khả năng | Phụ thuộc sản phẩm và chống giả mạo tín hiệu |
| **Risk/event state** | Thắt quyền sau tín hiệu nghi xâm nhập | Độ trễ cập nhật, false positives và cơ chế khôi phục |

**User identity và device identity là hai khái niệm khác nhau.** Đăng nhập bằng user có MFA không chứng minh thiết bị an toàn; thiết bị compliant cũng không tự cấp quyền của người dùng hiện tại.

### Không tin header do client tự khai

~~~text
Untrusted client claims:
  X-Device-Compliant: true

IAP must NOT trust this as posture proof
unless a trusted system verifies and binds
the evidence to the current device/session.
~~~

Nếu một client có thể tự gửi “compliant=true” qua header hay JSON không có attestation, điều kiện posture không còn ý nghĩa bảo mật. Tín hiệu cần có **nguồn tin cậy, tính mới, xác thực và mối liên hệ với session/device**.

### Khi posture chưa xác định

Một hệ thống an toàn phân biệt **COMPLIANT, NONCOMPLIANT và UNKNOWN/STALE**, không quy mọi UNKNOWN thành ALLOW. Với ứng dụng nhạy cảm, policy có thể **DENY hoặc yêu cầu xác minh lại**; với ứng dụng ít nhạy cảm, có thể cho degraded/read-only mode nếu được phê duyệt. Quyết định phải có owner và audit.

## 13. Ngữ cảnh truy cập và các tín hiệu rủi ro

Identity-aware proxy có thể cân nhắc thêm **nguồn mạng, thời gian, session age, mức xác thực, vị trí địa lý ước lượng, threat intelligence và hành vi bất thường**. Tuy nhiên, các tín hiệu này có **độ tin cậy và tác động quyền riêng tư khác nhau**.

| Context | Dùng hợp lý | Không nên suy |
|---|---|---|
| **Source IP / ASN** | Điều kiện rủi ro bổ sung, giới hạn region/corporate egress | IP là danh tính người dùng bền vững |
| **Geolocation** | Cảnh báo bất thường, step-up nếu policy cho phép | IP location luôn chính xác hoặc không dùng VPN |
| **Time of day** | JIT window hoặc ca hỗ trợ | Giờ lạ luôn là tấn công |
| **Authentication age** | Quyết định cần step-up hay re-auth | Có MFA một lần là đủ mãi mãi |
| **Role/group** | Phân nhóm truy cập theo owner duyệt | Nhóm nào cũng có quyền mọi object |
| **Device health** | Giảm rủi ro endpoint nhiễm mã độc | Agent báo xanh nghĩa không thể bị xâm nhập |
| **Risk score** | Tăng xác thực hoặc từ chối theo ngưỡng đã hiệu chuẩn | Điểm số là bằng chứng pháp lý/định danh tuyệt đối |

**Tín hiệu động không đồng nghĩa được phép suy đoán nhạy cảm về người dùng.** Chỉ thu thập dữ liệu cần thiết, công khai mục đích, giới hạn retention và xử lý false positives/appeal theo quy định tổ chức.

### “Continuous verification” nên hiểu thực tế thế nào?

Có nhiều mức:

1. Kiểm tra ở **bước login và tạo session**.
2. Kiểm tra **mỗi request/đường route** bằng policy và context cache.
3. Kiểm tra theo **TTL của session/policy/device claim**.
4. **Event-driven re-evaluation** khi IdP thu hồi quyền, EDR báo thiết bị không compliant hoặc risk engine phát hiện sự kiện.
5. Với long-lived connections, có cơ chế **re-auth/reconnect/terminate** khi điều kiện đổi.

**Không hứa “thu hồi quyền tức thì” nếu sản phẩm chỉ kiểm tra mỗi 30 phút hoặc chỉ khi user đăng nhập lại**. Phải đo **revocation latency** từ sự kiện đến khi PEP chặn truy cập.

## 14. Policy least privilege: principal, resource, action, context

Một quyết định IAP nên dựa trên ít nhất bốn thành phần:

~~~text
ACCESS REQUEST =
  subject   : who is calling?
  resource  : which protected app or route?
  action    : read / administer / invoke method?
  context   : device, auth strength, risk, time, location?

DECISION = ALLOW | DENY | REQUIRE_STEP_UP | UNKNOWN
~~~

Đây là **mô hình logic**, không phải output cố định của sản phẩm. Thực tế PDP có thể trả **Permit/Deny/Indeterminate/NotApplicable** hoặc danh mục khác; thiết kế phải quy định **cách PEP xử lý từng trạng thái**.

### Chính sách dạng bảng

| Principal | Resource | Action | Context | Decision |
|---|---|---|---|---|
| Employee thuộc HR | hr-web | Đọc hồ sơ bản thân | Session hợp lệ | IAP ALLOW; app kiểm tra owner |
| Finance admin | finance-admin | Mở console | MFA gần đây, thiết bị compliant | ALLOW |
| Finance admin | finance-admin | Mở console | Posture UNKNOWN | STEP_UP/DENY theo policy |
| Contractor | finance-admin | Mở console | Bất kỳ | DENY |
| Operator JIT | production-support | Truy cập hỗ trợ | Approval còn hiệu lực | ALLOW trong window |
| Workload chưa có identity | internal-api | Invoke | Không xác định principal | DENY |

**Một quyết định được tính tại proxy không thay được RBAC/ABAC ở backend** nếu IAP không quan sát payload hoặc quyền theo object. Đặt policy theo ứng dụng, API route và action ở những điểm hiểu được ngữ cảnh; giữ **object-level authorization** tại service.

### Ví dụ pseudocode định nghĩa policy, không phụ thuộc vendor

~~~text
function decide(request, identity, posture, entitlements):
    if identity.notAuthenticated:
        return DENY("unauthenticated")

    if request.resource not in approvedResourceRegistry:
        return DENY("unknown_resource")

    if entitlements.notFresh:
        return DENY_OR_REAUTH("entitlements_stale")

    if request.resource == "finance-admin":
        if "finance-admin" not in entitlements.groups:
            return DENY("missing_role")
        if posture != COMPLIANT:
            return DENY_OR_STEP_UP("device_posture")
        if identity.authAge > allowedAuthAgeForAdmin:
            return REQUIRE_STEP_UP("auth_age")

    if not explicitGrant(identity, request.resource, request.action):
        return DENY("no_matching_grant")

    return ALLOW("explicit_grant")
~~~

**Mã minh họa không có xử lý đầy đủ** về concurrency, policy version, token verification, audit, risk engine, timeout hay race khi quyền bị thu hồi. Production cần policy engine có kiểm thử, chủ sở hữu và quy trình rollback.

## 15. Default deny và trạng thái Indeterminate/UNKNOWN

Khi không thể xác minh danh tính, lấy dữ liệu nhóm hoặc kiểm tra policy, **“không có quyết định” không phải ALLOW**.

| Trạng thái | Cách xử lý phù hợp ở tài nguyên nhạy cảm |
|---|---|
| **No matching permission** | DENY |
| **Authentication failed** | DENY hoặc chuyển sang login flow hợp lệ |
| **Token signature/issuer/audience invalid** | DENY, không chuyển tiếp |
| **Required posture unknown** | DENY/step-up theo policy |
| **PDP timeout/error** | Fail closed, không forward |
| **IdP unavailable nhưng session đã xác minh còn hiệu lực** | Quyết định theo TTL và rủi ro đã phê duyệt; không tự gia hạn vô hạn |
| **Policy cache stale/expired** | Revalidate hoặc DENY theo hợp đồng |
| **Backend origin unavailable** | Trả lỗi availability; không mở direct origin bypass |

### Fail closed không đồng nghĩa “trả HTTP 403 cho mọi lỗi”

Khi **chưa đăng nhập**, proxy có thể redirect sang IdP hoặc trả **401** cho API client. Khi **đã xác thực nhưng thiếu quyền**, **403** thường phù hợp. Khi dependency của proxy không khỏe, **503** hoặc thông báo sự cố có thể phù hợp mà **không chuyển tiếp tới backend**. HTTP status phụ thuộc contract và giao thức; điều quan trọng là **không cấp quyền trái chính sách**.

### Caching decisions có giới hạn

Một PDP remote với mỗi request có thể tốn latency; proxy đôi khi dùng cache. Cache chỉ an toàn khi key và TTL bao phủ những thuộc tính quyết định, ví dụ:

~~~text
cache_key:
  issuer + subject
  target application/route/action
  tenant/context identity
  required auth strength
  policy version
  device posture version/time

cache_entry:
  ALLOW/DENY + expiry + policy origin
~~~

Không cache một quyết định **“user được vào HR”** để dùng cho **finance-admin**, hay cache quyền của **tenant A** cho **tenant B**. Khi có revocation, yêu cầu **invalidate hoặc TTL đủ ngắn** theo độ nhạy, đồng thời đo độ trễ thay đổi quyền.

## 16. Session management: cookie không phải token bất tử

Sau OIDC login, IAP có thể tạo **session cookie** chứa session ID tham chiếu ở server hoặc một phần state đã ký/mã hóa theo thiết kế. Bảo vệ cookie và lifecycle là điều kiện không thể bỏ qua.

### Thực hành quan trọng

| Kiểm soát | Mục đích |
|---|---|
| **Secure cookie** | Chỉ gửi qua HTTPS theo semantics browser |
| **HttpOnly** | Giảm khả năng JavaScript truy cập trực tiếp cookie |
| **SameSite phù hợp** | Giảm một số nguy cơ CSRF trong các request cross-site |
| **Host-only / Domain hạn chế** | Tránh chia sẻ cookie sang subdomain không cần |
| **Narrow Path khi phù hợp** | Hạn phạm vi browser gửi cookie theo route |
| **Session rotation on login** | Giảm nguy cơ session fixation |
| **Idle + absolute timeout** | Không để phiên sống vô hạn |
| **Logout/revocation** | Chấm dứt hoặc làm mất hiệu lực phiên theo cơ chế |
| **CSRF protections** | Bảo vệ các thao tác thay đổi trạng thái |
| **Binding/replay defenses** | Giảm rủi ro cookie/token bị sao chép nếu công nghệ hỗ trợ |

**SameSite không tự thay CSRF token/Origin checks cho mọi ứng dụng**, và HttpOnly không khắc phục XSS ở backend. Không lưu cookie, refresh token hoặc bearer token trong URL/log.

### SSO session và app session

Một người dùng có thể có **IdP session**, **IAP session** và **backend application session** cùng lúc. Logout ở một lớp chưa chắc revoke tất cả các lớp còn lại ngay. Cần xác định:

1. Khi IdP thu hồi tài khoản, IAP nhận sự kiện hay đợi token/session hết hạn?
2. Khi IAP deny, backend session cookie cũ còn dùng được qua đường bypass không?
3. Session cố định ở browser hay được gắn với thiết bị/credential phù hợp?
4. Khi chuyển tenant hoặc nâng quyền, có rotate/re-authorize và chống session confusion không?
5. Có ngăn **open redirect** để không chuyển session/login artifacts tới domain ngoài ý định không?

## 17. Header identity: nguồn tin có thể bị giả mạo

Một reverse proxy/IAP có thể chuyển **danh tính đã xác minh** tới backend qua header chuyên dụng, ví dụ **X-Authenticated-User** hoặc identity token do proxy ký. **Header HTTP bản thân không phải bằng chứng danh tính**: client cũng có thể tự gửi header cùng tên nếu proxy không xóa/ghi đè trước khi forward.

~~~text
Untrusted request:
  GET /admin
  X-Authenticated-User: finance-admin@example.test

Unsafe origin:
  trusts the header directly -> escalation risk

Safe boundary requires:
  1. Origin reachable only from approved proxy/network.
  2. Proxy strips untrusted identity headers.
  3. Proxy sets authenticated identity from verified session.
  4. Origin verifies signed identity assertion or
     mutually authenticated proxy identity when appropriate.
  5. Origin checks resource-level authorization.
~~~

### Nguyên tắc xử lý header

- Không tin **X-Forwarded-User**, **X-Forwarded-Email**, **X-Forwarded-Groups**, **X-Forwarded-For** hoặc các header tùy biến nếu có thể đi thẳng từ client.
- Proxy phải **xóa mọi bản do client tự gửi** trước khi ghi giá trị đã xác thực; phải tính duplicate header/canonicalization và các trường hợp khác nhau về chữ hoa/chữ thường.
- Nếu dùng **signed identity assertion**, backend xác minh issuer, signature, audience, expiry, replay constraints và binding với route/resource.
- Nếu dùng **mTLS proxy → origin**, backend xác minh đúng proxy/service identity thay vì tin mọi client trong subnet.
- Với chuỗi nhiều proxy, cần xác định **proxy nào cuối cùng có quyền đặt header**, và chỉ tin X-Forwarded-* từ trust boundary đã cấu hình.

**Không lấy email trong header làm khóa phân quyền duy nhất**: email có thể đổi, trùng ngữ cảnh hoặc không định danh ổn định giữa các IdP. Dùng principal định danh ổn định theo issuer, kết hợp tenant/realm khi cần.

## 18. Backend origin bypass: kiểm soát quan trọng nhất

Nếu backend vẫn truy cập được trực tiếp qua **public IP, DNS khác, LoadBalancer, NodePort, VPN, peering hoặc port mở trên host**, attacker/caller có thể bỏ qua proxy và đến ứng dụng mà không qua IAP policy.

~~~text
Expected:
  Client -> Identity-aware proxy -> App origin

Bypass:
  Client -----------------------> App public IP
  Partner VPN ------------------> App private IP
  Untrusted Pod ----------------> App Pod IP
  Legacy LB --------------------> App admin port
~~~

### Nguyên tắc bảo vệ origin

1. Origin chỉ nhận từ **IAP/proxy hoặc trusted connector** trên đường đã duyệt; không public trực tiếp nếu không có yêu cầu riêng.
2. Áp **cloud security group/firewall/NACL/NetworkPolicy** ở đúng subnet/Pod/instance.
3. Xóa/restrict **legacy ingress, management listener, NodePort, LoadBalancer, DNS route** không còn cần thiết. Với Kubernetes **hostNetwork**, Pod dùng mạng node nên phải kiểm soát **node IP, host firewall và cloud security group**, không giả định mọi NetworkPolicy dành cho Pod thông thường sẽ bao phủ đường này.
4. Dùng **TLS/mTLS từ proxy tới origin**, kiểm tra danh tính máy chủ và caller.
5. Backend không được tin **identity headers không có nguồn xác thực**, ngay cả khi traffic đi từ IP private.
6. Kiểm tra **IPv4 và IPv6**, vùng HA/DR và các đường private connectivity.
7. Với trường hợp backend bắt buộc phải cho các caller nội bộ khác vào, mỗi đường đó cần **policy tương đương**, không mặc nhiên exempt khỏi bảo mật.

### Vì sao chỉ “xóa DNS record” chưa đủ?

Một IP hoặc hostname cũ có thể còn trong cache, tài liệu, cấu hình hoặc log. Ngay cả khi không còn DNS, **route và firewall vẫn có thể cho gói tới origin qua IP**. Cần đóng đường truy cập ở **network boundary và backend trust verification**; DNS chỉ là cơ chế tìm tên.

### Origin isolation và health checks

Load balancer/proxy cần health checks và đôi khi quản lý certificate. Phải cho phép **đúng nguồn và port cần thiết**, không mở all-sources để “đảm bảo health”. Kiểm tra health không thay mTLS/service authorization cho traffic người dùng.

## 19. Private connector, outbound tunnel và brokered access

Nhiều hệ thống ZTNA/IAP tránh mở một cổng inbound public trên origin bằng cách chạy **connector trong mạng private**, tạo kết nối **outbound đã được xác thực** tới control/data plane/broker của dịch vụ truy cập.

~~~text
Remote user ---- HTTPS ----> ZTNA / IAP edge
                              |
                      authenticated route
                              |
                    broker / secure channel
                              ^
                              |
               outbound connector tunnel
                              |
                           Private App
                       (no public inbound)
~~~

### Những điều cần hiểu

- Connector outbound **giảm nhu cầu public inbound**, nhưng không tự chặn mọi private lateral path tới origin.
- Connector cần **identity, key lifecycle, least-privilege outbound access, patching và monitoring**.
- Nếu connector có thể truy cập nhiều subnets/ports, compromise của connector có **blast radius** lớn; giới hạn đường đích theo policy.
- Cần xác minh **routing/broker mapping** để request được phép cho App A không được tái sử dụng để đi tới App B hoặc metadata service.
- Tách **control plane outage** khỏi **data plane tunnel health**; không đồng nhất tunnel UP với app/user authorization.
- Với nhà cung cấp ZTNA cloud, cần đánh giá **địa điểm xử lý dữ liệu, lưu logs, trust model và rủi ro phụ thuộc provider**.

**Outbound connector không phải bảo đảm “Zero Trust tự động”**. Nó chỉ là một phương án nối đường; identity, policy enforcement, backend protection và audit vẫn phải được thiết kế.

## 20. TLS/mTLS qua IAP: bảo vệ từng hop

Trong nhiều hệ thống, IAP terminate TLS từ browser rồi tạo một kết nối mới tới origin.

~~~text
User browser
     |
     | TLS Hop A: browser -> IAP
     v
Identity-aware proxy
     |
     | TLS/mTLS Hop B: IAP -> origin
     v
Protected app
     |
  App authorization
~~~

**TLS Hop A và Hop B là hai kết nối khác nhau** nếu proxy terminate/tái mã hóa. Mã hóa browser → IAP không chứng minh proxy → origin được mã hóa; proxy có thể xem nội dung HTTP sau giải mã và thường phải bảo vệ dữ liệu nhạy cảm trong memory/logs.

### Câu hỏi bảo mật

| Hop | Điều cần xác minh |
|---|---|
| **Browser → IAP** | Server certificate, hostname, TLS version, HSTS/cookie policy phù hợp |
| **IAP ↔ IdP** | TLS, OIDC issuer/redirect, token verification và secret handling |
| **IAP ↔ PDP/PIP** | Identity của policy service, TLS/mTLS, timeout/fail closed |
| **IAP → Origin** | Origin certificate/SAN, mTLS proxy identity nếu cần, private routing |
| **Origin → các backend khác** | Service-to-service auth/mTLS và authorization riêng |

Không tắt **TLS certificate verification** để tránh lỗi kết nối hoặc dùng HTTP cleartext qua nhiều vùng mạng mà không có threat model và kiểm soát tương đương được duyệt.

### TLS passthrough giới hạn khả năng ra quyết định

Nếu IAP chỉ **passthrough TLS** mà không giải mã HTTP, nó có thể không nhìn **URL path, method, cookie/session hoặc JSON claims** để áp L7 policy; sản phẩm có thể yêu cầu client agent, pre-auth tunnel hoặc cơ chế khác. Không tuyên bố một TCP proxy passthrough có thể tự áp chính sách object-level HTTP như một reverse proxy giải mã request.

## 21. Ứng dụng cần kiểm tra quyền độc lập với IAP

IAP trả lời câu hỏi **“principal này được đi vào ứng dụng hoặc route nào?”**. Backend phải tiếp tục trả lời **“principal này được làm gì đối với đối tượng dữ liệu cụ thể?”**

### Ví dụ IDOR/BOLA sau khi IAP ALLOW

~~~text
User A: tenant = A, role = employee
IAP: ALLOW /hr/ application

Request:
  GET /api/employees/employee-of-tenant-B

Unsafe app:
  checks only user has entered via IAP
  -> returns tenant B record

Correct app:
  verifies employee/tenant ownership and action
  -> DENY unless explicitly authorized
~~~

Một user hợp lệ có thể cố gọi API không được phép hoặc lợi dụng lỗi backend. IAP không tự hiểu quan hệ ownership nếu không có ngữ cảnh nghiệp vụ hoặc policy phù hợp. Kể cả IAP có route-level authorization, backend vẫn cần **server-side authorization theo object**.

### End-user identity khác service identity

Nếu IAP/gateway dùng mTLS để gọi backend, backend thấy **IAP workload identity** của kết nối. Nó vẫn cần **user identity được truyền an toàn, được xác minh và ràng buộc với request** để ra quyết định tenant. Đừng gán mọi request qua gateway thành **superuser** chỉ vì gateway có certificate tin cậy.

### Quyền theo action, không chỉ theo URL

| Tầng | Quyết định mẫu |
|---|---|
| **IAP app-level** | User được vào finance portal |
| **IAP route-level** | User được gọi GET /reports, không POST /admin |
| **App API-level** | Finance user được tạo report nhưng không thay quyền |
| **Object-level** | User chỉ xem report được chia sẻ cho đúng tenant |
| **Data-level** | Database role chỉ đọc bảng/record đúng phạm vi |

**Không bao giờ tin client chỉ vì request đã đi qua proxy**; cần ràng buộc danh tính và quyền tại đúng tài nguyên.

## 22. IAP cho trình duyệt, mobile, CLI và machine-to-machine

Một cổng truy cập được thiết kế cho trình duyệt và OIDC redirect có thể không phù hợp với **CLI automation, service account, webhook, gRPC client hoặc mobile app**. Thiết kế phải phân loại **principal và luồng giao thức**.

| Loại client | Phương pháp thường cân nhắc | Rủi ro cần xét |
|---|---|---|
| **Browser** | OIDC Authorization Code + PKCE, cookie session | CSRF, XSS, session theft, redirect URI |
| **Native/mobile app** | OIDC/OAuth với system browser/PKCE theo platform | Token storage, deep-link interception, device binding |
| **CLI tương tác** | Browser login hoặc device authorization flow nếu sản phẩm hỗ trợ | Phishing, token cache, shared terminal |
| **Service-to-service** | Workload identity, OAuth client credentials, mTLS, token exchange | Long-lived secrets, wrong audience, broad roles |
| **Webhook từ đối tác** | Signed payload, mTLS/token theo hợp đồng | Replay, spoofed source IP, signature validation |
| **SSH/RDP client** | Brokered/session gateway hoặc client agent hỗ trợ protocol | Direct origin path, recorded session, user mapping |
| **Legacy TCP client** | Application-aware tunnel hoặc connector được thiết kế | Tầng proxy không nhìn operation/tenant |

### Tránh biến user credential thành máy chủ chung

Một job tự động không nên dùng cookie SSO của nhân viên hoặc mật khẩu cá nhân lưu trong CI chỉ để đi qua proxy. Cần **machine identity riêng**, có owner, thời hạn, scope và audit, với cơ chế rotation phù hợp. Nếu job phải hành động thay người dùng, thiết kế **delegation/on-behalf-of/token exchange** theo contract thay vì cố gắng giả mạo user header.

### Audience và confused deputy

~~~text
Token issued for: reporting-api
Request sent to: finance-admin

Unsafe finance-admin:
  accepts any token signed by company IdP

Safe finance-admin:
  validates audience/scope/issuer
  and verifies caller is entitled to finance-admin.
~~~

**Chữ ký IdP hợp lệ không đủ để dùng token tại mọi resource server**. Mỗi ứng dụng/proxy phải xác minh token được phát hành **đúng cho nó hoặc cho mục đích được chấp thuận**.

## 23. gRPC, WebSocket và long-lived sessions

IAP có thể xử lý nhiều giao thức ứng dụng, nhưng hành vi xác thực/ủy quyền với **kết nối dài** khác request HTTP ngắn.

### HTTP và gRPC

- **HTTP:** proxy có thể kiểm tra từng request/method/path nếu terminate/parse HTTP.
- **HTTP/2/gRPC unary:** proxy L7 có thể đọc service/method và headers, nhưng cần hiểu **grpc-status trong trailers**, không chỉ HTTP/2 status.
- **gRPC streaming:** một kết nối/stream có thể truyền nhiều thông điệp dài; không tự re-authorize từng message nếu proxy không hiểu payload hoặc chính sách không yêu cầu.
- **Client-side retries:** nếu session hết hạn, client không nên retry vô hạn hoặc gửi lại thao tác không idempotent.

### WebSocket và streaming

~~~text
Browser -> IAP HTTP Upgrade / WebSocket handshake
          |
          +-- initial session/policy check
          |
          v
     Long-lived WebSocket
        data frames...
~~~

**Kiểm tra lúc handshake không mặc nhiên thu hồi một WebSocket đang mở khi quyền bị gỡ**. Nếu hệ thống yêu cầu revocation nhanh, cần cơ chế **connection termination, session refresh, maximum connection age hoặc kiểm tra theo sự kiện**.

### Bốn câu hỏi khi chọn sản phẩm

1. IAP có hỗ trợ **WebSocket/gRPC streaming** với TLS/HTTP semantics phù hợp không?
2. Policy được đánh giá **mỗi request, mỗi stream hay chỉ lúc mở TCP connection**?
3. Khi user bị revoke, **connection đang mở** có bị cắt hoặc buộc xác thực lại không?
4. Authenticated principal có được truyền **an toàn và đúng scope** qua các message không?

**Không gọi một TCP tunnel là “L7 identity-aware filtering” chỉ vì kết nối khởi tạo dùng SSO**; chính sách thực tế có thể chỉ kiểm tra ở thời điểm cấp tunnel.

## 24. SSH, RDP và truy cập quản trị phi HTTP

Với SSH/RDP/database clients, IAP kiểu reverse proxy HTTP thuần túy không xử lý trực tiếp toàn bộ giao thức. Một giải pháp ZTNA có thể dùng **broker/gateway, short-lived certificates, client agent, PAM/JIT access hoặc giao thức proxy đặc thù**.

### Ví dụ quản trị máy chủ

~~~text
Engineer workstation
       |
  User auth + MFA + device posture
       |
       v
  Access broker / PEP
       |
  JIT approval + session policy
       |
       v
  SSH gateway / bastion
       |
  Host authentication + account authorization
       |
       v
  Approved server :22
~~~

### Điều không được bỏ qua

- **SSH host key verification** phải đúng; broker không thay xác minh host identity.
- Người dùng được vào một máy không tự có **root/sudo** hoặc quyền xem secret.
- Privileged sessions có thể yêu cầu **approval, recording, command restriction, expiry** theo pháp lý và policy.
- Không dùng credential dùng chung giữa mọi kỹ sư; cần attribution tới người dùng thực.
- Ngăn **direct SSH/RDP via VPN/management subnet** nếu tổ chức yêu cầu mọi truy cập qua broker.
- Khi tunnel đang hoạt động mà JIT permission hết hạn, phải biết **cơ chế đóng/kiểm tra lại session**.

**Tên “identity-aware proxy” có thể là sản phẩm cụ thể hoặc thuật ngữ kiến trúc**, nhưng phải đánh giá hỗ trợ thật cho từng protocol, chứ không assume mọi IAP bảo vệ được SSH/UDP/RDP.

## 25. DNS, SNI, Host header và định tuyến đến đúng origin

Một IAP thường dùng **hostname/path/virtual host** để chọn ứng dụng. Nếu chọn upstream hoặc policy sai, có thể làm traffic tới tài nguyên ngoài ý định.

### Những điểm phải kiểm soát

| Thuộc tính | Vai trò | Rủi ro nếu sai |
|---|---|---|
| **DNS** | Client tìm tên IAP; proxy tìm origin | DNS rebinding/split-horizon/route sai, origin bypass |
| **SNI** | Client chỉ định tên server TLS trong handshake | SNI không phải bằng chứng user identity |
| **Host / :authority** | HTTP virtual host/request routing | Host confusion, wrong tenant/app policy |
| **URL path** | Route hoặc operation yêu cầu | Encoding/normalization mismatch với backend |
| **Forwarded headers** | Ghi nhận client/proxy context khi có trust | Header spoofing, IP identity confusion |
| **Upstream target** | Đích private được proxy forward | SSRF-like routing, proxy-to-metadata access |

### Rủi ro policy không khớp routing

~~~text
Request:
  Host: finance.example.test
  Path: /admin%2fsettings

PEP sees: path form A
Origin sees: decoded/canonicalized path form B

If policy checks A while backend routes B,
a method/path boundary may be bypassed.
~~~

Ví dụ cho thấy cần **canonicalization nhất quán** và test các biến thể path, encoding, case sensitivity và HTTP method, chứ không phải hướng dẫn thử lỗi trên hệ thống ngoài phạm vi.

**Không cho client tự chỉ định arbitrary upstream URL/IP** trong một proxy đáng lẽ chỉ phục vụ danh mục ứng dụng được duyệt. Nếu proxy có tính năng forward tới dynamic target, cần strict allowlist, bảo vệ metadata/link-local/private ranges và phân tách quyền.

## 26. Multi-tenant applications và phân quyền theo dữ liệu

Một IAP dùng chung cho nhiều tenant có thể cấp quyền vào **cùng application hostname**, nhưng không biết người dùng thuộc tenant nào nếu thông tin không được xác minh và truyền an toàn.

### Các lớp tenant context

~~~text
Authentication:
  issuer + subject -> user principal

Entitlement:
  user belongs to tenant A

IAP:
  ALLOW access to reporting application

Application:
  request report_id=R-123
  verifies report belongs to tenant A

Database:
  tenant-aware query / row-level control
~~~

### Những lỗi thường gặp

- Dùng **email domain** làm bằng chứng tenant mà không có mapping được quản trị.
- Tin **tenant_id** client gửi trong header/query mà không ràng buộc với principal.
- Cache policy ALLOW theo **user** nhưng bỏ **tenant/resource**, dẫn đến cross-tenant cache.
- Một IdP multi-tenant phát token với **iss/tenant khác** nhưng backend chỉ kiểm chữ ký bằng cùng một key.
- Dùng chung **origin identity header** cho nhiều upstream nhưng không có audience binding.
- IAP ALLOW trên dashboard che việc application đã có **BOLA/IDOR**.

**Tài nguyên nhạy cảm cần policy theo object và tenant tại backend**, bất kể proxy được quản trị tốt đến đâu.

## 27. Break-glass và truy cập khẩn cấp

Khi IdP hoặc IAP gặp sự cố, cần phương án khôi phục dịch vụ vận hành, nhưng **không biến “emergency access” thành một bypass không kiểm toán**.

### Thiết kế break-glass

1. Định nghĩa **tài nguyên tối thiểu** cần tiếp cận khi hệ thống identity mất sẵn sàng.
2. Dùng **tài khoản/cơ chế đặc biệt được bảo vệ** với kiểm soát đa người, lưu ký và xác thực mạnh phù hợp.
3. Giới hạn nguồn, thời hạn, hành động và đường mạng; không mở toàn bộ application origins ra Internet.
4. Bắt buộc **incident ticket, approval, audit và hậu kiểm**.
5. Có cách thu hồi khẩn cấp ngay khi IdP/IAP phục hồi.
6. Diễn tập định kỳ trong phạm vi an toàn để bảo đảm vẫn dùng được nhưng không bị lạm dụng.

**Không lưu mật khẩu break-glass trong wiki công khai, ứng dụng chat hoặc các log mà không giới hạn quyền**. Với tổ chức có yêu cầu chứng cứ nghiêm ngặt, thiết kế **dual control, PAM và session recording** theo tiêu chuẩn nội bộ.

## 28. High availability và fail-safe behavior

IAP trở thành **điểm bắt buộc** trên đường vào nhiều ứng dụng; nếu mọi truy cập phụ thuộc một instance/proxy hoặc một IdP vùng duy nhất, sự cố có thể ảnh hưởng lớn.

### Các failure domains

| Thành phần lỗi | Tác động | Kiểm soát dự phòng |
|---|---|---|
| **IAP proxy instance** | Không tiếp nhận/forward request | Replicas, LBs, health checks, autoscaling có giới hạn |
| **IdP authorization/token endpoint** | Login mới/refresh thất bại | IdP HA, policy cache có TTL, kiểm thử outage |
| **PDP/PIP** | Không đánh giá permission hoặc posture | HA, bounded timeout, fail closed |
| **Origin backend** | IAP đã ALLOW nhưng app unavailable | App HA, timeout/circuit breaker |
| **Connector/private tunnel** | Không tới được private origin | Redundant connectors, path monitoring |
| **Certificate/secret rotation** | TLS session/new handshake lỗi | Certificate expiry alerts, trust rollout |
| **Policy distribution** | Proxies dùng rules khác nhau | Config version monitoring, canary, rollback |
| **DNS/route/SG** | Client không đến proxy hoặc proxy không đến origin | Dual-path testing, route/flow telemetry |

### IAP outage không phải lý do cho phép direct origin

Nếu identity decision service không phản hồi, một thiết kế nhạy cảm nên **không forward request không được xác thực/ủy quyền**. Có thể phục vụ request đã có session còn hiệu lực theo **TTL đã phê duyệt**, nhưng không gia hạn quyền vô hạn hoặc biến mọi auth error thành ALLOW.

### Load, rate limiting và DoS

- Giới hạn **request rate và số lần login/refresh** để tránh khuếch đại tải IdP.
- Bảo vệ PDP/PIP bằng **timeouts, bulkhead, circuit breaker có fail-closed semantics**.
- Rate limit theo **principal/session/tenant**, không chỉ IP NAT chung.
- Giới hạn **long-lived tunnels và concurrent sessions**.
- Theo dõi p95/p99 latency do auth, policy và origin.
- Phân biệt **HTTP 429/quota** với **policy DENY** và **origin 503**.

**IAP không thay anti-DDoS/WAF**. Khi các gói volumetric chưa đến PEP, cần edge/network capacity và dịch vụ phòng vệ phù hợp.

## 29. Quản lý thay đổi chính sách và tránh privilege drift

Một tài khoản mới được thêm vào nhóm **finance-admin**, một app đổi URL/path, một proxy thêm route hoặc một connector mở subnet mới đều có thể làm **effective access** rộng hơn.

### Policy lifecycle

~~~text
Business owner identifies access need
             |
       Resource inventory
             |
      Approved grant / expiry
             |
       Policy as Code change
             |
       Static validation / review
             |
      Lab ALLOW and DENY tests
             |
       Canary / staged rollout
             |
    Effective decision observation
             |
       Review / revoke / audit
~~~

### Những trường nên quản trị

| Trường | Ý nghĩa |
|---|---|
| **Policy ID/version** | Truy xuất quyết định nào tạo ALLOW/DENY |
| **Resource owner** | Ai phê duyệt người dùng/nhóm được vào |
| **Principal/role source** | IdP/groups/trust domain có authority nào |
| **Allowed app/actions** | Phạm vi quyền tường minh |
| **Required auth/device context** | Điều kiện MFA, posture, risk |
| **Grant expiry** | Tránh giữ quyền tạm vĩnh viễn |
| **Exception record** | Ngoại lệ legacy/break-glass có owner và TTL |
| **Expected denial tests** | Bằng chứng quyền ngoài phạm vi bị chặn |
| **Origin topology** | Route/SG/connector cho backend |

**Policy as Code đúng cú pháp không đồng nghĩa thực thi đúng**. Cần kiểm tra policy hiện hành trên proxy, nguồn entitlement, route thực tế và bảo vệ origin, không chỉ CI linter.

## 30. Chỉ số quan sát và quyết định truy cập

Mỗi request qua IAP có thể được phân loại theo **xác thực, policy, context, origin và kết quả ứng dụng**. Nếu chỉ ghi “403 count” sẽ khó biết đó là lỗi cấu hình hay truy cập trái quyền bị chặn đúng.

| Metric/event | Ý nghĩa |
|---|---|
| **Authenticated principal rate** | Tỷ lệ request/session có identity hợp lệ |
| **Policy ALLOW/DENY by app/action** | Quyền được cấp/thực thi theo resource |
| **Unknown/Indeterminate count** | Nơi PDP/PIP/identity không đủ bằng chứng |
| **MFA/step-up challenge rate** | Tần suất xác thực bổ sung, ảnh hưởng trải nghiệm |
| **Device posture failures/stale** | Thiết bị bị chặn, nguồn signals có bị lỗi không |
| **Session age and revocation latency** | Quyền bị rút mất bao lâu để PEP chặn |
| **Denied direct-to-origin attempts** | Dấu hiệu bypass test hoặc truy cập ngoài quyền |
| **PDP latency/timeouts/cache hit rate** | Hiệu năng và độ mới quyết định |
| **IdP errors/failed callbacks** | Login failure, OIDC issues hoặc attack signals |
| **Origin response errors** | Backend 401/403/5xx/timeout, tách với proxy deny |
| **Access by source/zone/tenant** | Bất thường theo hành vi và mức ảnh hưởng |
| **TLS/certificate health** | Trust/rotation trên các hop liên quan |

### Mẫu log đã che dữ liệu

~~~text
timestamp=2026-11-28T14:00:00+07:00
environment=staging
request_id=example-req-019
proxy=iap-edge-a
policy_version=finance-policy-v7
principal_issuer=https://idp.example.test/company
principal_subject=user-example-013
application=finance-admin
requested_route=/reports
requested_action=GET
identity_result=AUTHENTICATED
mfa_context=VERIFIED_FOR_POLICY
device_posture=COMPLIANT
policy_decision=ALLOW
decision_source=PDP
origin=finance-private-service
origin_http_status=200
total_latency_ms=145
authorization_header=[NOT_LOGGED]
session_cookie=[NOT_LOGGED]
device_identifier=[REDACTED]
~~~

Đây là **log giả lập**, không phải format của một nhà cung cấp. Không ghi full tokens/cookies/PII, dữ liệu sinh trắc học hoặc fingerprint thiết bị không cần thiết; bảo vệ access logs bằng **RBAC, retention, masking và audit**, đặc biệt khi chứa principal/tenant/nhóm quyền.

### Đo đúng tỷ lệ bảo vệ

Một dashboard “100% request qua IAP được xác thực” không chứng minh toàn bộ truy cập app đều qua IAP. Cần có **tập origin interfaces và routes** để xác minh không còn đường direct access hoặc traffic bypass ngoài mẫu đo.

**Coverage = phạm vi được bảo vệ trên mọi đường thực**, không chỉ tổng số request đã được proxy nhìn thấy.

## 31. Case study 1: origin public khiến người dùng bypass IAP

**Bối cảnh giả định:** Đội vận hành đặt IAP trước **hr-web**, dùng OIDC và MFA. Trên URL chính, người chưa login sẽ bị redirect. Nhưng ứng dụng còn một **public LoadBalancer IP** từng dùng trước khi triển khai IAP; backend nhận request trực tiếp và tin header **X-Authenticated-User**.

### Bằng chứng giả lập

~~~text
Expected path:
  https://hr.example.test -> IAP -> private hr-web

Unexpected path:
  https://legacy-hr.example.test -> public LB -> hr-web

Network policy:
  backend allows direct public LB ingress

App authorization:
  trusts X-Authenticated-User from arbitrary HTTP clients
~~~

### Phân tích

1. IAP có thể **xác thực và áp chính sách đúng** trên đường chính.
2. Backend **vẫn có đường không qua PEP**, nên kiểm soát bị mất hiệu lực trên đường phụ.
3. Tin identity header không có xác thực cho phép request tự khai danh tính.
4. Metrics tại IAP có thể không thấy request trên đường legacy, tạo cảm giác coverage đầy đủ giả.

### Cách sửa theo lớp

- Kiểm kê **mọi public/private endpoint** trỏ tới ứng dụng, gồm DNS cũ, LB, node, VPN và IPv6.
- Hạn origin ingress chỉ từ **IAP/connector identity hoặc mạng proxy đã duyệt**; thu hồi legacy route qua change control.
- Bảo vệ hop proxy→origin bằng **mTLS/signed assertion**, chuẩn hóa và ghi đè identity headers.
- Backend xác thực assertion và kiểm tra quyền đối với user/tenant/object.
- Test từ một nguồn không đi qua IAP: **direct origin DENY**; qua IAP với user có quyền: **ALLOW**; user thiếu quyền: **DENY**.

**Bài học:** Một IAP được cấu hình tốt vẫn bị vô hiệu nếu ứng dụng có **đường bypass** hoặc backend chấp nhận danh tính do client tự khai.

## 32. Case study 2: token đúng chữ ký nhưng sai audience

**Bối cảnh giả định:** Công ty dùng chung IdP cho **reporting-api** và **finance-admin**. Một nhóm phát triển chỉ kiểm chữ ký/JWKS, expiry và email, không kiểm **aud** cho finance-admin. Một client có token hợp lệ được cấp cho reporting API mang tới finance proxy.

### Mô hình lỗi

~~~text
Token:
  iss = trusted IdP
  aud = reporting-api
  exp = not expired
  signature = valid

Requested resource:
  finance-admin

Unsafe validator:
  "Issuer trusted + signature valid -> ALLOW"

Correct validator:
  "Token audience NOT finance-admin
   -> DENY or use approved token exchange"
~~~

**Không phải một token được ký bởi IdP tin cậy là “vé toàn hệ thống”.** Trong OAuth/OIDC, audience và scope/purpose giới hạn token được sử dụng ở đâu. IAP có thể dùng **ID token cho session của chính mình** và **access token có audience đúng** khi chuyển tiếp tới API; không hoán đổi tùy tiện.

### Khắc phục

1. Xác định **token type** mà mỗi thành phần phải nhận.
2. Xác minh **iss, aud, signature, algorithm, exp, nbf và authorization claims** đúng contract.
3. Nếu cần gọi API B từ API A, dùng **delegation/token exchange** được phê duyệt để cấp token có audience của B.
4. Thêm test **wrong audience**, **wrong issuer**, **expired**, **wrong token type** và **valid token/no authorization**.
5. Không lưu token thật vào ticket/test report.

**Bài học:** Authentication token verification phải gắn với **resource và purpose cụ thể**, không phải chỉ “đã có chữ ký hợp lệ”.

## 33. Case study 3: thiết bị mất tuân thủ nhưng session vẫn giữ quyền

**Bối cảnh giả định:** Finance-admin chỉ cho truy cập từ thiết bị có EDR và mã hóa ổ đĩa. IAP kiểm tra posture **một lần khi login**; một phiên được cấp sống 12 giờ. Sau đó EDR báo thiết bị mất tuân thủ nhưng IAP không nhận sự kiện và session vẫn ALLOW các request nhạy cảm.

### Timeline giả lập

~~~text
08:00  User authenticated + MFA.
08:01  Device posture COMPLIANT.
08:02  IAP session issued, valid up to 12 hours.
10:00  EDR marks device NONCOMPLIANT.
10:01  Session policy cache still says ALLOW.
12:00  User can access finance-admin without fresh posture.
~~~

### Những điều cần đo

- Nguồn posture có gửi **event hoặc version changes** tới PDP/IAP không?
- Session hoặc policy cache có **TTL** bao lâu?
- Có **step-up/re-auth/terminate active connection** khi posture thay đổi không?
- Những route nào được coi là high-risk và yêu cầu đánh giá lại?
- Thiết bị **UNKNOWN** do nguồn telemetry lỗi được xử lý thế nào?

### Thiết kế phục hồi

1. Xác định **maximum acceptable revocation latency** cho finance-admin.
2. Dùng **event-driven invalidation** hoặc TTL policy ngắn hơn theo thiết kế.
3. Khi posture không đạt, chặn action nhạy cảm, có thể chuyển sang read-only hoặc DENY theo risk policy.
4. Báo trạng thái rõ ràng cho user và có quy trình khắc phục compliant device.
5. Kiểm thử bằng tín hiệu giả lập trong lab, không tự can thiệp EDR/endpoint thật.
6. Audit những action xảy ra **sau thời điểm posture thay đổi**.

**Bài học:** “Continuous evaluation” cần có **độ mới dữ liệu và cơ chế thu hồi quyền đo được**; login MFA thành công trước đó không bảo đảm quyền nên tồn tại vô hạn.

## 34. Case study 4: IAP cho HTTP nhưng bỏ sót WebSocket admin channel

**Bối cảnh giả định:** Portal quản trị có route HTTPS qua IAP và dùng **WebSocket** cho tác vụ real-time. Reverse proxy bảo vệ GET /admin bằng OIDC nhưng bỏ qua policy trên endpoint **/ws/admin** hoặc chỉ kiểm tra khi kết nối được mở, không cắt connection khi session bị revoke.

### Hai kiểu sai

~~~text
Case A: Unprotected route
  HTTPS /admin -> IAP authentication/authorization
  WS /ws/admin -> forwarded without equivalent policy

Case B: Stale long-lived session
  WS handshake at 09:00 -> ALLOW
  Role removed at 09:30
  Existing WS continues until disconnected
~~~

### Cách khắc phục

- Inventory **mọi protocol, route và upgrade path**, không chỉ các URL được browser hiển thị.
- Buộc authentication và authorization tại **WebSocket handshake**; ứng dụng kiểm tra quyền từng command/message nhạy cảm khi cần.
- Giới hạn **connection lifetime, idle timeout, concurrency** và có cách terminate khi session bị revoke.
- Không tin cookie/session như quyền cho **mọi loại lệnh** được gửi trong stream.
- Kiểm thử **direct origin**, client không có session, client có session nhưng thiếu role và client bị revoke khi connection đang mở.

**Bài học:** Một proxy hiểu HTTP nhưng không bảo vệ upgrade/stream có thể tạo lỗ hổng, ngay cả khi trang admin yêu cầu MFA.

## 35. Case study 5: nhóm IdP thay đổi nhưng policy cache giữ quyền cũ

**Bối cảnh giả định:** Nhân viên rời phòng tài chính. IdP thu hồi group **finance-admin**, nhưng IAP cache quyết định ALLOW theo subject trong 24 giờ và không có invalidation. Người dùng vẫn còn session hoạt động trên portal.

### Sai ở đâu?

- Group membership đã thay đổi nhưng **entitlement freshness** không được quản trị.
- Cache key/TTL không gắn đủ **policy version, group version hoặc revocation event**.
- IAP chỉ đánh giá lần đầu truy cập mà không giới hạn session.
- Không có alert cho sự lệch giữa IdP group state và effective access.

### Khắc phục

1. Xác định SLO thu hồi quyền với finance-admin.
2. Điều chỉnh **cache TTL/invalidation** theo mức nhạy cảm, không tái sử dụng ALLOW khi context hết hạn.
3. Hỗ trợ **session revocation** hoặc giới hạn thời gian phiên đã được cấp.
4. Kiểm tra phiên đang mở, browser mới, API token cũ và tài khoản truy cập qua mobile/CLI.
5. Kết hợp owner review của entitlement và access logs sau sự kiện thu hồi.

**Bài học:** **Danh tính được xác thực** và **quyền hiện hành** là hai dữ kiện khác nhau. Một token/session còn hợp lệ về mặt thời gian không có nghĩa mọi role từng có vẫn được cấp.

## 36. Runbook: phân loại lỗi login, policy deny và origin unavailable

Khi user báo “không truy cập được ứng dụng”, đừng bắt đầu bằng việc **tắt MFA, bỏ authorization hoặc public origin**. Mỗi lớp có nguyên nhân và owner khác nhau.

### Giai đoạn 1 — Thu bối cảnh

1. Thời điểm, ứng dụng, route, source network, user/tenant ID đã pseudonymize và request ID.
2. Client loại nào: browser, CLI, mobile, service-to-service, SSH broker?
3. Kết quả là **DNS failure, TCP timeout, TLS alert, login redirect loop, 401, 403, 429 hay 503**?
4. Thiết bị có compliant và IdP có trả **đúng issuer/audience/auth strength** không?
5. Gần đây có đổi **IdP/JWKS, group, device posture, policy, certificate, route/SG, connector, origin release** không?

### Giai đoạn 2 — Tách tầng

~~~text
User cannot access protected application
                 |
             DNS/TCP/TLS?
              /       \
            FAIL      PASS
             |          |
      Edge/DNS/route   Has valid IAP session?
                        /              \
                      No              Yes
                      |                |
                 IdP/OIDC/PKCE      PDP decision?
                 callback/cookie    /      \
                                 DENY     ALLOW
                                   |       |
                            groups/MFA/   Origin route?
                            posture/TTL    /      \
                                        FAIL      PASS
                                         |         |
                                  connector/SG    App authz/
                                  origin/TLS      HTTP/gRPC
~~~

### Giai đoạn 3 — Kiểm tra bằng chứng

| Triệu chứng | Nơi điều tra trước | Không nên vội làm |
|---|---|---|
| **Redirect loop** | Cookies, redirect_uri, session state, OIDC callback | Disable cookie security vô điều kiện |
| **State/nonce mismatch** | Session handling, multi-replica state, proxy cookie | Bỏ state/nonce validation |
| **Invalid issuer/audience** | IdP config, token type, clock/JWKS | Cho mọi issuer/audience |
| **Device posture denied** | PIP freshness, device management, risk policy | Gán posture compliant thủ công |
| **PDP timeout** | Policy service HA, network/TLS, cache TTL | Fail-open app nhạy cảm |
| **Proxy ALLOW, origin 503** | Connector, DNS, SG, route, origin readiness | Quy lỗi cho identity |
| **Proxy ALLOW, app 403** | Backend user/tenant/resource policy | Mở rộng IAP role |
| **Direct origin reachable** | LB/SG/NACL/NodePort/NetworkPolicy | Tin login portal đã bảo vệ đủ |
| **WS/gRPC token expiry** | Stream lifetime, refresh/re-auth semantics | Retry vô hạn hoặc bỏ token verification |

### Giai đoạn 4 — Khôi phục có kiểm soát

- Ưu tiên **sửa nguyên nhân gốc** ở IdP, cookie/OIDC, policy, network hoặc backend.
- Có **change ticket, owner, blast radius, rollback** và giám sát negative tests.
- Nếu cần quyền khẩn, dùng **break-glass đã định nghĩa**, không dùng public-origin workaround.
- Nếu nghi token/session bị lộ, **revoke và điều tra**, không chỉ tăng session TTL.
- Khi backend bị lỗi, IAP có thể trả 503 theo policy mà vẫn bảo vệ origin; đừng chuyển tiếp không kiểm soát.

### Giai đoạn 5 — Nghiệm thu

Một incident chưa thể đóng chỉ vì **một user đã login lại được**. Phải kiểm tra **principal có quyền ALLOW, principal ngoài quyền DENY, posture không đạt bị chặn, ứng dụng backend bảo vệ object/tenant, origin không bypass và logs ghi đủ quyết định**. Nếu lỗi liên quan token hoặc CA, cần kiểm tra rotation/refresh và các vùng HA.

## 37. Lab an toàn: kiểm tra thiết kế IAP bằng policy và read-only probes

Lab sử dụng **địa chỉ ví dụ thuộc .test** hoặc endpoint staging đã được tổ chức cho phép. Không tạo tài khoản ngoài quyền, không thử bypass trên hệ thống không thuộc phạm vi và không xuất token/cookie thật ra console logs.

### 37.1. Chuẩn bị

~~~text
Protected applications:
  hr.example.test       -> private hr-web
  finance.example.test  -> private finance-admin

Identities:
  employee-test: can open hr-web
  finance-test: can open finance-admin after MFA
  contractor-test: cannot open finance-admin

Device states:
  compliant
  noncompliant
  unknown

Test source networks:
  approved client to IAP
  approved lab probe testing direct-origin DENY
~~~

### 37.2. Bài tập giấy: suy quyết định policy

| Test | Principal | Tài nguyên | Context | Quyết định kỳ vọng |
|---|---|---|---|---|
| L1 | employee-test | hr-web | Session hợp lệ | ALLOW ở IAP, app còn kiểm tra dữ liệu |
| L2 | employee-test | finance-admin | Không thuộc role | DENY |
| L3 | finance-test | finance-admin | MFA mới, posture compliant | ALLOW |
| L4 | finance-test | finance-admin | Posture noncompliant | DENY/STEP_UP theo policy |
| L5 | contractor-test | finance-admin | Bất kỳ | DENY |
| L6 | Anonymous | hr-web | Không có session | Login flow hoặc 401, không forward |
| L7 | finance-test | origin IP trực tiếp | Bỏ qua IAP | DENY tại network/origin trust boundary |
| L8 | finance-test | report thuộc tenant khác | IAP ALLOW | App DENY |

### 37.3. Kiểm tra HTTPS endpoint staging được phép

~~~bash
# Chỉ một HEAD request tới hostname staging được phê duyệt.
# Không dùng -k/--insecure để bỏ qua certificate validation.
curl --head --silent --show-error \
  --connect-timeout 3 --max-time 8 \
  https://hr.example.test/
~~~

Kết quả có thể là redirect **302/303** tới IdP, **401/403**, hoặc status khác theo thiết kế. **Không có một HTTP status duy nhất chứng minh IAP được cấu hình đúng**. Nếu có redirect, chỉ quan sát vị trí/host được phép; **không tự theo mọi Location** vì có thể đến dịch vụ ngoài phạm vi lab.

### 37.4. Quan sát certificate public tại edge

~~~bash
# Chỉ dùng hostname thuộc phạm vi test có quyền.
openssl s_client \
  -connect hr.example.test:443 \
  -servername hr.example.test \
  -verify_hostname hr.example.test \
  -verify_return_error \
  -brief
~~~

Lệnh trên chỉ hỗ trợ đánh giá **TLS server identity tới IAP edge**, không kiểm chứng token, MFA, PDP, origin route, mTLS proxy→origin hoặc application authorization. Không dùng nó như bằng chứng toàn bộ ZTNA đã PASS.

### 37.5. Kiểm chứng đường origin trong lab

Thay vì quét public IP, dùng một **approved synthetic probe** từ đúng nguồn được cấp phép để kiểm tra **direct origin DENY**. Chủ hệ thống cung cấp FQDN/IP lab đã duyệt. Ghi lại:

- Source network/identity của probe.
- Destination origin IP/hostname/port **chính xác**.
- Route và SG/NetworkPolicy áp dụng.
- Kết quả TCP/TLS/application.
- Bằng chứng DENY từ firewall/proxy/origin theo khả năng.

**Đừng coi timeout là chứng cứ duy nhất của IAP isolation**: route sai hoặc origin ngừng chạy cũng tạo timeout. Test cần **positive path qua IAP** hoạt động, negative path bị chặn tại ranh giới phù hợp và origin đang khỏe.

### 37.6. Phiếu nghiệm thu

~~~text
Lab ID:                IAP-ZTNA-001
Environment:           authorized staging/lab
Application:           [app ID, owner]
IAP route:             [approved hostname/path]
Origin boundary:       [private address/connector]
Principal:             [pseudonymous issuer + sub]
Device posture:        [compliant/noncompliant/unknown]
Authentication:        [OIDC/mTLS/other, not secret]
MFA/step-up:           [policy satisfied/not]
Token validation:      [iss/aud/expiry/nonce when relevant]
Policy version:        [ID and version]
Requested action:      [route/method]
Expected IAP decision: [ALLOW/DENY/STEP_UP]
Observed IAP decision: [source and result]
Origin reachable direct:[YES/NO/UNKNOWN, with evidence]
Backend authorization: [ALLOW/DENY/NOT_TESTED]
IPv4/IPv6 coverage:    [where applicable]
Session revocation:    [tested/not tested]
Telemetry/audit:       [request ID, redacted]
Verdict:               [PASS/FAIL/INCONCLUSIVE]
Owner/change record:   [team and reference]
~~~

**INCONCLUSIVE** phù hợp khi không xác minh được một đường direct origin, chưa biết token audience hoặc không quan sát được PDP decision; không được chuyển thành PASS chỉ để kết thúc lab.

## 38. Ma trận kiểm thử Identity-aware proxy và ZTNA

Ma trận này yêu cầu **đường hợp lệ hoạt động** và **đường không được phép bị chặn**, đồng thời phân biệt lỗi identity/policy với lỗi DNS, TLS, mạng và ứng dụng. Chỉ thực hiện phép thử được chủ dịch vụ phê duyệt, ưu tiên tài khoản giả lập và dữ liệu không nhạy cảm trong lab.

| Test ID | Tình huống | Kỳ vọng |
|---|---|---|
| **IAP-01** | User chưa login mở ứng dụng được bảo vệ | Redirect tới login hợp lệ hoặc 401, không forward tới origin |
| **IAP-02** | User có session hợp lệ vào app được quyền | IAP ALLOW và app xử lý thành công theo quyền |
| **IAP-03** | User được xác thực nhưng không thuộc nhóm app | Policy DENY |
| **IAP-04** | User thuộc nhóm nhưng thiếu điều kiện MFA | Step-up hoặc DENY theo policy |
| **IAP-05** | User thuộc nhóm, posture noncompliant | DENY hoặc degraded mode đã duyệt |
| **IAP-06** | Posture UNKNOWN/STALE tới ứng dụng nhạy cảm | Không được tự ALLOW |
| **IAP-07** | IdP trả response với state sai | Callback bị từ chối |
| **IAP-08** | OIDC ID token có nonce sai khi flow yêu cầu | Token/session bị từ chối |
| **IAP-09** | Authorization code flow thiếu hoặc sai PKCE verifier | Không cấp session hợp lệ |
| **IAP-10** | redirect_uri không khớp giá trị được đăng ký | Không redirect/đổi code ngoài policy |
| **IAP-11** | Token ký bởi issuer khác | DENY |
| **IAP-12** | Token sai audience | DENY, không cấp quyền vì chữ ký hợp lệ |
| **IAP-13** | ID token bị dùng như access token cho API | Từ chối token sai mục đích |
| **IAP-14** | JWT dùng thuật toán không được cho phép | DENY theo algorithm allowlist |
| **IAP-15** | Token hết hạn/chưa có hiệu lực | DENY hoặc refresh theo flow an toàn |
| **IAP-16** | Token JWKS được xoay khóa hợp lệ | Validator cập nhật trust có kiểm soát |
| **IAP-17** | Opaque token không introspect được | Fail closed theo chính sách |
| **IAP-18** | Nhóm tài khoản bị thu hồi | Quyền IAP bị thu hồi trong SLO quy định |
| **IAP-19** | Session quá hạn idle/absolute | Phải xác thực lại theo policy |
| **IAP-20** | Session bị revoke trong khi WebSocket đang mở | Connection bị ngắt/kiểm soát lại trong SLO |
| **IAP-21** | Cookie không có Secure/HttpOnly theo chuẩn áp dụng | Cấu hình bị policy lint bắt |
| **IAP-22** | Request thay đổi trạng thái từ cross-site | CSRF/Origin policy bảo vệ |
| **IAP-23** | Client tự gửi X-Authenticated-User | IAP xóa/ghi đè, backend không tin giá trị giả |
| **IAP-24** | Header duplicated/case variant ở ingress | Không thay đổi principal hoặc bypass policy |
| **IAP-25** | Truy cập origin trực tiếp qua public IPv4 | DENY tại network/origin boundary |
| **IAP-26** | Truy cập origin qua IPv6 public ngoài ý định | DENY theo chính sách tương đương |
| **IAP-27** | Origin reachable qua VPN/peering cũ | Chặn/điều kiện tương đương, không bypass IAP |
| **IAP-28** | Kubernetes NodePort/Pod IP direct route | Không tạo đường bỏ qua authn/authz |
| **IAP-29** | Connector private tunnel tới đúng app | ALLOW chỉ resource và port được duyệt |
| **IAP-30** | Connector cố tới subnet/port ngoài inventory | DENY bởi network/connector policy |
| **IAP-31** | Proxy→origin mTLS sai SAN/trust | Kết nối bị từ chối; không tắt verify |
| **IAP-32** | Browser→IAP TLS hợp lệ nhưng origin TLS sai | Không coi TLS edge là đã bảo vệ mọi hop |
| **IAP-33** | HTTP Host/SNI/path không khớp route | Không chuyển tới upstream ngoài danh mục |
| **IAP-34** | Request path có encoded/canonicalized variant | PEP và backend không bất đồng quyền |
| **IAP-35** | gRPC client có bearer token đúng audience | Authn/authz và grpc-status được đo đúng |
| **IAP-36** | gRPC streaming dài sau quyền bị thu hồi | Re-evaluation/termination theo chính sách |
| **IAP-37** | WebSocket upgrade route không có policy | Phát hiện và chặn đường ngoài quyền |
| **IAP-38** | SSH broker cấp quyền JIT ngắn hạn | Truy cập đúng máy, quyền và thời hạn |
| **IAP-39** | SSH direct origin không qua broker | DENY hoặc policy tương đương |
| **IAP-40** | Service job dùng cookie user trong CI | Policy phát hiện yêu cầu machine identity riêng |
| **IAP-41** | Backend nhận request user tenant A tới object B | App object-level DENY dù IAP ALLOW |
| **IAP-42** | PDP không phản hồi/timeout | PEP fail closed, không forward tới origin |
| **IAP-43** | Policy cache còn ALLOW sau revoke | Invalidation/TTL trong SLO, không quyền tồn tại quá hạn |
| **IAP-44** | IdP tạm không sẵn sàng | Login mới fail safe; session cũ theo TTL đã duyệt |
| **IAP-45** | IAP instance lỗi ở một vùng | HA giữ dịch vụ và chính sách bảo mật |
| **IAP-46** | Origin lỗi 503 sau IAP ALLOW | Không nhầm với policy DENY; runbook đúng owner |
| **IAP-47** | MFA push/account risk bị nghi compromise | Session containment/re-auth đúng policy |
| **IAP-48** | Break-glass được kích hoạt có phép | Có owner, TTL, audit và tự thu hồi |
| **IAP-49** | Log/test chứa cookie/token giả | Credential không được lưu/hiển thị |
| **IAP-50** | Sau policy deployment ở HA regions | Positive/negative tests, policy version và origin isolation đúng |

### Kết luận kiểm thử

- **PASS:** có bằng chứng cho đúng principal/resource/context; IAP xử lý ALLOW/DENY phù hợp, backend/route/TLS được xác minh theo phạm vi.
- **FAIL:** đã chứng minh một caller trái quyền vào được ứng dụng hoặc dữ liệu, một đường direct origin bypass, hoặc caller hợp lệ bị từ chối ngoài policy.
- **INCONCLUSIVE:** thiếu identity/token validation evidence, không biết enforcement point, nguồn test sai, không quan sát được policy/route hoặc kết quả bị che bởi outage.
- **NOT_APPLICABLE:** một tính năng không được triển khai (ví dụ không có WebSocket/SSH/IPv6), có ghi lý do và người xác nhận.

**Không tuyên bố IAP “an toàn” dựa duy nhất trên test user hợp lệ có thể mở ứng dụng.** Các negative tests là bằng chứng thiết yếu của least privilege.

## 39. Những hiểu nhầm và lỗi thiết kế phổ biến

| Nhận định sai | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| “Zero Trust nghĩa không tin bất kỳ người nào” | Zero Trust dựa vào kiểm chứng và policy, không phải chặn mọi truy cập | Verify explicitly, least privilege |
| “Đã cài IAP là hoàn thành Zero Trust” | Còn workload identity, data, network, device security | Defense-in-depth |
| “VPN luôn không an toàn” | VPN có thể áp IAM/segmentation rất hẹp | So sánh policy scope và hiệu lực thật |
| “Ở trong văn phòng là trusted” | Network location không chứng minh danh tính | Identity/context evaluation |
| “Reverse proxy có TLS là identity-aware proxy” | Chưa có xác thực, policy PEP/PDP | Xác định enforcement và identity |
| “Có SSO portal nghĩa không thể bypass ứng dụng” | Origin có thể mở trực tiếp | Origin network isolation |
| “MFA xong một lần là quyền vĩnh viễn” | Session bị lộ, posture/role thay đổi | Session expiry, re-auth, event revocation |
| “Thiết bị compliant nghĩa không thể nhiễm mã độc” | Tín hiệu posture có giới hạn | Layered endpoint detection |
| “Client gửi X-Device-Compliant=true là đủ” | Header có thể tự tạo | Trusted, bound device attestation |
| “Token ký bởi IdP thì dùng được ở mọi app” | Audience/type/purpose khác nhau | iss/aud/expiry/signature validation |
| “ID token là access token dùng cho API” | Mục đích và audience khác | Dùng credential đúng contract |
| “Email là unique stable identity toàn công ty” | Email thay đổi, nhiều issuers/tenants | issuer + stable subject |
| “JWT signed là mọi group claim hiện tại” | Token/cache có TTL và stale entitlement | Freshness/revocation management |
| “Không cần state nếu có PKCE” | Hai cơ chế bảo vệ rủi ro khác nhau | State/nonce/PKCE theo OIDC flow |
| “SameSite cookie loại hết CSRF” | Không bảo vệ mọi thiết kế/đường | CSRF token/Origin khi cần |
| “IdP logout tự logout mọi app ngay” | Nhiều session/caches có vòng đời riêng | End-to-end logout design |
| “Một policy ALLOW cho app tức được đọc mọi object” | App còn tenant/user resource ownership | Object-level authorization |
| “Header X-Authenticated-User là bằng chứng danh tính” | Client có thể giả mạo | Strip/overwrite hoặc signed assertion |
| “X-Forwarded-For luôn là IP user thật” | Proxy chain và spoofing | Trusted proxy chain parsing |
| “Origin không có DNS nghĩa không truy cập được” | Direct IP/legacy LB/VPN còn route | Chặn tại firewall/SG/origin |
| “Chỉ kiểm tra IPv4 là đủ” | IPv6 có thể có đường khác | Dual-stack negative tests |
| “Connector outbound thì không cần firewall” | Connector có quyền tới origin, lateral risk | Least-privilege connector access |
| “TLS ở edge bảo vệ hết backend” | TLS có thể terminate ở proxy | Verify từng hop |
| “mTLS proxy→origin tự xác thực end-user” | Proxy identity khác user identity | User assertion và app auth |
| “L7 policy được thực thi cả trong TLS passthrough” | Proxy có thể không thấy HTTP payload | Kiểm tra enforcement point |
| “WebSocket được xác thực lúc bắt đầu là mãi an toàn” | Quyền có thể revoke trong phiên dài | Max age/revalidation/termination |
| “SSH broker có quyền root tự động” | SSH authentication và host authorization riêng | PAM/JIT and host controls |
| “PDP lỗi thì cho phép để giữ uptime” | Availability failure biến thành security bypass | Fail closed and HA |
| “Cache key chỉ cần user ID” | Tài nguyên, tenant, action và context khác nhau | Context-bound decisions/cache |
| “Một 403 chứng minh hacker bị chặn bởi IAP” | 403 có thể từ backend hoặc policy khác | Log decision source |
| “Không có IAP log là không có bypass” | Traffic direct origin không đi qua IAP | Origin/flow telemetry |
| “Mở all-sources vào origin giúp health checks khỏe” | Mở rộng bề mặt tấn công | Allow verified proxy/health sources |
| “Policy IaC đúng là production chắc chắn an toàn” | Runtime route/cache/config drift | Runtime attestation/tests |
| “Thay role trong IdP sẽ revoke tức thì” | Token/session/cache có TTL | Measure revocation latency |
| “Bỏ MFA giúp sửa lỗi đăng nhập” | Phá an ninh, che root cause | Điều tra OIDC/cookies/policy |
| “IAP là WAF/DDoS shield đầy đủ” | Chức năng khác nhau | Edge anti-DDoS/WAF và rate controls |
| “Chỉ test ALLOW là đủ nghiệm thu” | Không biết đường trái quyền có mở không | ALLOW + DENY + bypass tests |

## 40. Câu hỏi tự kiểm tra

1. Identity-aware proxy giải quyết vấn đề gì mà mô hình VPN mở dải mạng chưa chắc giải quyết?
2. Vì sao IAP là thành phần của Zero Trust nhưng không đại diện cho toàn bộ kiến trúc Zero Trust?
3. Phân biệt **PEP, PDP, PIP, IdP** theo nhiệm vụ và loại quyết định.
4. Principal được mạng cho phép tới IP có đồng nghĩa được vào ứng dụng không? Vì sao?
5. IAP khác reverse proxy, API gateway, WAF và service mesh mTLS như thế nào?
6. Một request IAP cho phép gồm những bước từ browser đến backend?
7. OAuth 2.0 khác OIDC về mục đích gì? Access token khác ID token?
8. Vì sao cần kiểm tra **issuer và audience** chứ không chỉ JWT signature?
9. Những điều kiện nào cần xác minh trong Authorization Code Flow với **PKCE, state và nonce**?
10. Khi IdP dùng opaque access token, kiểm tra token khác JWT thế nào?
11. Vì sao không nên xác định principal dựa duy nhất vào email?
12. MFA khác device posture ra sao và vì sao hai điều kiện cần được tách biệt?
13. Có thể tin **X-Device-Compliant: true** từ browser không? Vì sao?
14. Context **UNKNOWN** nên được xử lý thế nào ở finance-admin?
15. “Continuous access evaluation” cần những cơ chế nào để không chỉ là khẩu hiệu?
16. Vì sao policy cache keyed chỉ bằng user ID có thể gây cross-tenant privilege leak?
17. Cần những thuộc tính nào cho policy **subject, resource, action, context**?
18. Fail closed khi PDP timeout nghĩa là gì? Nó khác trả 503 như thế nào?
19. Session cookie cần những thuộc tính/giới hạn thời gian nào?
20. Vì sao logout ở IdP chưa chắc đã revoke ngay backend session?
21. Vì sao backend không được tin header **X-Authenticated-User** nếu client có thể tự gửi?
22. Nếu proxy có mTLS với backend, vì sao backend vẫn cần end-user authorization?
23. Nêu ít nhất bốn đường có thể **bypass IAP** để truy cập origin.
24. Vì sao chỉ xóa DNS record của origin không đủ để ngăn direct access?
25. Private connector outbound giảm loại bề mặt nào, và vẫn còn rủi ro gì?
26. Khi TLS terminate ở IAP, cần xác minh những TLS hops nào?
27. Một TCP proxy passthrough có thể áp mọi HTTP method-level policy không? Vì sao?
28. IAP có thể hỗ trợ gRPC/WebSocket khác HTTP request ngắn như thế nào?
29. Nếu user bị revoke khi WebSocket vẫn mở, proxy cần làm gì để đáp ứng SLO revocation?
30. Với SSH/RDP, những điểm khác của broker-based ZTNA so với HTTP reverse proxy là gì?
31. Vì sao user được vào finance portal chưa chắc được xem báo cáo tenant B?
32. Trong case study origin public, lỗi ở proxy hay ở ranh giới backend?
33. Trong case study wrong audience, vì sao chữ ký đúng vẫn phải DENY?
34. Trong case study posture stale, cần đo những loại TTL/latency nào?
35. Những trường telemetry nào giúp phân biệt **login failure, policy deny, origin 503 và app 403**?
36. Vì sao một bản ghi IAP ALLOW không tự chứng minh truy cập data hợp lệ?
37. Khi IdP hoặc PDP không khỏe, làm sao giữ availability mà không biến thành fail-open?
38. Break-glass có những yêu cầu owner/TTL/audit nào?
39. Hãy thiết kế test matrix cho employee, finance-admin và contractor với compliant/noncompliant devices.
40. Sau khi áp IAP, cần những bằng chứng nào để kết luận **không còn direct origin bypass**?

## 41. Ghi nhớ trọng tâm

**Identity-aware proxy là điểm thực thi chính sách truy cập theo danh tính và ngữ cảnh trước khi cho request tới ứng dụng được bảo vệ.** Trong kiến trúc **Zero Trust Network Access**, IAP có thể thay việc cấp quyền mạng rộng bằng **truy cập theo từng ứng dụng, resource hoặc action**. Mô hình gồm **IdP để xác thực, PEP để thực thi, PDP để quyết định, PIP để cung cấp context**, kèm session management, audit và backend authorization.

Thiết kế an toàn phải phân biệt **xác thực, IAP authorization và object-level application authorization**. Với OIDC/OAuth, xác minh đúng **issuer, audience, chữ ký, token type, expiry, state/nonce/PKCE**; với session/cookie, có TTL, chống CSRF, logout và revocation; với posture, dùng **tín hiệu đáng tin và đủ mới**, không tin header client tự khai. Quyền có thể yêu cầu MFA/step-up theo độ nhạy, nhưng chính sách không được xem **một lần login thành công** là quyền truy cập vô thời hạn.

**Điều kiện quyết định là toàn bộ đường truy cập tới origin phải được bảo vệ**, không chỉ URL chính qua proxy. Cần khóa **public/private direct paths, legacy LoadBalancer, VPN/peering, Kubernetes Pod/NodePort và IPv6**, bảo vệ hop proxy→origin bằng TLS/mTLS và không tin identity header chưa xác thực. Chú ý **HTTP/gRPC/WebSocket/SSH**, các session kéo dài, quyền machine-to-machine, multi-tenant, connector blast radius và sự khác biệt giữa proxy identity với user identity.

Nghiệm thu phải ghép **policy version, token/session/device evidence, proxy ALLOW/DENY, origin isolation, TLS từng hop, application tenant authorization, revocation latency và logs bảo vệ quyền riêng tư**. Phép thử đúng phải chứng minh **người đủ quyền vào được đúng ứng dụng, người hoặc thiết bị không đủ điều kiện bị từ chối, resource trái quyền không bị lộ và không có đường bypass**. **IAP không thay firewall, mTLS, WAF, endpoint security hoặc application authorization; nó làm những lớp đó phối hợp theo danh tính và nguyên tắc ít đặc quyền.**
