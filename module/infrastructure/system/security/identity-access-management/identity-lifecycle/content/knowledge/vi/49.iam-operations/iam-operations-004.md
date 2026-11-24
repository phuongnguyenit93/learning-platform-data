# Xử lý Identity Provider lỗi trong IAM: chẩn đoán, ứng phó và phục hồi

## 1. Mục tiêu và phạm vi

**Identity Provider (IdP)** là thành phần xác minh danh tính, áp dụng chính sách xác thực và phát hành các bằng chứng đăng nhập cho ứng dụng dựa vào IdP. Trong hệ thống dùng **Single Sign-On (SSO)**, sự cố IdP có thể khiến nhiều dịch vụ cùng không cho người dùng đăng nhập dù bản thân các ứng dụng đó vẫn hoạt động. Đây là một sự cố có thể ảnh hưởng lớn tới vận hành lẫn bảo mật.

**Xử lý identity provider lỗi** thuộc chương **IAM operations** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Bài này hướng dẫn xác định lỗi ở IdP, đường kết nối SSO, MFA, directory, cấu hình ứng dụng hay các dịch vụ phụ thuộc; duy trì kiểm soát truy cập trong thời gian gián đoạn; phục hồi an toàn và đối soát **vòng đời danh tính Joiner–Mover–Leaver (JML)**.

Một IdP lỗi không chỉ là sự cố “không đăng nhập được”. Nó có thể làm chậm **Joiner** (không tạo/kích hoạt được tài khoản), khiến **Mover** dùng claim/quyền cũ và làm gián đoạn **Leaver** (không thu hồi được quyền kịp thời). Bởi vậy runbook phải liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, session/token, audit** và biện pháp giảm **quyền truy cập tồn dư**.

Sau bài học, người đọc có thể:

1. Phân biệt mất khả dụng IdP với lỗi cấu hình SSO, chặn MFA, lỗi directory, provisioning hoặc authorization.
2. Thu thập tín hiệu, xác định phạm vi ảnh hưởng và cô lập thành phần gây lỗi mà không làm suy yếu bảo mật.
3. Điều phối incident, lựa chọn phương án truy cập khẩn cấp đã phê duyệt và khôi phục theo thứ tự an toàn.
4. Duy trì xử lý JML, đặc biệt chặn truy cập của **Leaver** khi connector/IdP không khả dụng.
5. Xác minh đăng nhập, phiên, token và quyền hiệu lực sau phục hồi; lưu bằng chứng kiểm toán và phòng ngừa tái diễn.

> **Tính chất tài liệu:** Đây là runbook tham chiếu. Không mặc định một sản phẩm IdP cụ thể, không giả định hệ thống có đa vùng, chuyển đổi IdP hoặc tài khoản break-glass. Thời gian phục hồi, quyền khẩn cấp và cơ chế failover phải theo kiến trúc, chính sách và khả năng kiểm thử thực tế của tổ chức.

## 2. IdP tham gia vào vòng đăng nhập như thế nào?

Trong ứng dụng dùng federation, người dùng thường được chuyển tới IdP để xác thực; sau đó ứng dụng sử dụng kết quả SSO để tạo phiên và quyết định quyền. **OIDC** thường dùng authorization flow, ID token, access token và endpoint liên quan; **SAML 2.0** thường sử dụng assertion, metadata, chứng chỉ ký và thời hạn assertion. Thành phần xác thực và ứng dụng có trách nhiệm riêng.

~~~mermaid
flowchart LR
    U[Người dùng] --> SP[Ứng dụng / Service Provider]
    SP -->|OIDC / SAML| IDP[Identity Provider]
    IDP --> CRED[Directory / Credential Store]
    IDP --> MFA[MFA / Risk / Conditional Access]
    IDP --> KEYS[Signing Keys / Metadata]
    IDP -->|Token / Assertion| SP
    SP --> APPSESSION[Session tại ứng dụng]
    HR[HRIS / Nguồn nhà thầu] --> JML[Bộ điều phối vòng đời JML]
    JML --> IDP
    JML -->|SCIM / Connector| SP
    JML --> PAM[PAM / Quản lý đặc quyền]
    IDP --> LOG[Audit / SIEM]
    SP --> LOG
    JML --> LOG
    MFA --> LOG
~~~

### 2.1. Năm lớp cần phân biệt

| Lớp | Chức năng | Ví dụ lỗi |
|---|---|---|
| **Danh tính nguồn và provisioning** | Xác minh người, trạng thái nhân sự, tạo account và quyền | HR event đến muộn, SCIM không tạo user, role sai |
| **IdP / directory** | Kiểm tra thông tin xác thực, trạng thái tài khoản, phát hành bằng chứng | IdP không trả lời, directory timeout, account bị khóa |
| **MFA / chính sách rủi ro** | Đánh giá điều kiện đăng nhập, thiết bị, vị trí, xác thực nhiều yếu tố | MFA push lỗi, policy chặn thiết bị, provider MFA không khả dụng |
| **SSO federation / cryptography** | Trao đổi và xác minh OIDC token hoặc SAML assertion | Sai redirect URI, client secret, signing key, certificate |
| **Ứng dụng / authorization** | Tạo session và kiểm tra RBAC/ABAC, role cục bộ, dữ liệu | IdP trả success nhưng app báo 403, claim thiếu, user chưa được provision |

**Đừng kết luận IdP bị sập từ một thông báo “Login failed”.** Nguyên nhân có thể là chính sách truy cập đúng thiết kế hoặc lỗi riêng của ứng dụng; việc vô hiệu hóa policy để xử lý một lỗi authorization là không phù hợp.

### 2.2. Mặt phẳng xác thực và các quyền đã phát hành

IdP chủ yếu quyết định các lần xác thực và phát hành bằng chứng mới. Ứng dụng có thể tiếp tục chấp nhận **session cookie hoặc access token** đã phát hành trong thời hạn của chúng, tùy cách kiểm tra token, khả năng introspection, revocation, cache khóa và chính sách riêng. Do đó:

- IdP outage **không nhất thiết** làm mọi người đang đăng nhập bị đá ra.
- IdP outage **không đảm bảo** quyền của người đã nghỉ việc lập tức mất hiệu lực ở mọi ứng dụng.
- Không phải ứng dụng nào cũng kiểm tra IdP trong từng request; kiểm soát Leaver có thể cần revoke tại ứng dụng, PAM, VPN và service đích.
- Nếu IdP phục hồi nhưng app còn giữ phiên cũ, cần kiểm tra claim/role thay đổi và thời hạn cache trước khi kết luận quyền đã đúng.

## 3. Phân loại sự cố trước khi can thiệp

| Nhóm sự cố | Triệu chứng thường gặp | Bằng chứng cần xem |
|---|---|---|
| **IdP service unavailable** | Nhiều ứng dụng đều không hoàn tất SSO, endpoint IdP timeout hoặc 5xx | Health/status từ nguồn đáng tin, request ID, latency, tỷ lệ lỗi |
| **Network / DNS / TLS** | Chỉ một khu vực/mạng/thiết bị lỗi, kết nối hoặc chứng chỉ thất bại | DNS, route, proxy, firewall, TLS chain, đồng hồ hệ thống |
| **Federation misconfiguration** | Một ứng dụng lỗi ngay sau thay đổi cấu hình OIDC/SAML | App registration, redirect URI, issuer, audience, metadata, signing cert |
| **Directory / credential backend** | SSO endpoint còn hoạt động nhưng xác thực mật khẩu thất bại/timeout | Directory health, replication, connector, auth logs |
| **MFA / risk provider** | User vượt bước mật khẩu nhưng không qua MFA, nhiều challenge lỗi | MFA provider, risk decision, thiết bị, phương thức và chính sách |
| **Policy / conditional access** | Ứng dụng hoặc nhóm user bị từ chối có điều kiện | Rule ID, kết quả evaluation, thay đổi policy gần nhất |
| **Token / signing key** | Ứng dụng từ chối token/assertion sau rotate key/cert | JWKS/metadata cache, signature, kid, certificate validity |
| **SCIM / provisioning** | IdP login thành công nhưng app báo user not provisioned/inactive | Provisioning job, SCIM state, role/claims và app logs |
| **Ứng dụng đích** | Chỉ một app lỗi, các app khác SSO bình thường | Service Provider logs, session, callback endpoint, authorization |
| **Nghi bị tấn công** | Spike đăng nhập sai, nhiều user, cảnh báo bất thường, tài khoản admin bị nhắm | Security telemetry, sign-in history, SOC analysis |

**Quy tắc triage:** chẩn đoán trên nhiều điểm quan sát độc lập. “Status page xanh” không phủ nhận lỗi ở tenant/khu vực/đường mạng cụ thể; “IdP trả 200” chưa chứng minh endpoint/token đã hoạt động đúng ở ứng dụng.

## 4. Vai trò, mức ưu tiên và điều kiện bảo mật

| Vai trò | Trách nhiệm |
|---|---|
| **Incident Commander** | Điều phối phản ứng, xác định mức ảnh hưởng, ra quyết định thay đổi và thời điểm thông báo |
| **IAM Operations** | Điều tra IdP/SSO/provisioning, khôi phục tài khoản và đối soát quyền |
| **Platform / Network / Directory** | Điều tra DNS, proxy, TLS, directory, mạng và hạ tầng nền |
| **Application Owner** | Kiểm tra luồng SSO tại ứng dụng, các session, account cục bộ và phương án khôi phục đã duyệt |
| **Security Operations (SOC)** | Phân loại tấn công, containment, bảo vệ log, đánh giá rủi ro trước khi phục hồi |
| **HR / Sponsor** | Xác nhận sự kiện JML, ngày hiệu lực và danh tính được phép truy cập |
| **PAM / Break-glass Owner** | Quản lý truy cập đặc quyền khẩn cấp và hậu kiểm |
| **Communications / Support** | Cập nhật tình trạng cho các nhóm bị ảnh hưởng, tránh thu thập secret |

### 4.1. Phân loại ưu tiên tham khảo

| Mức | Tình huống | Điều phối |
|---|---|---|
| **P0** | IdP diện rộng không cấp được phiên mới cho nhiều hệ thống trọng yếu; hoặc lối thu hồi quyền Leaver khẩn cấp bị ảnh hưởng nghiêm trọng | Kích hoạt incident bridge theo quy định, IAM + Platform + SOC |
| **P1** | Một cụm ứng dụng/đơn vị quan trọng mất SSO, hoặc MFA/risk service lỗi trên diện rộng | Owner IdP và ứng dụng phối hợp, giám sát tác động |
| **P2** | Một ứng dụng cụ thể lỗi federation sau thay đổi, có phương án phục hồi đã kiểm chứng | Điều tra cấu hình, rollback/change được duyệt |
| **P3** | Lỗi giới hạn một user hoặc vấn đề không ảnh hưởng dịch vụ quan trọng | Service Desk xử lý theo runbook xác thực/authorization |

Đây chỉ là ví dụ. Mỗi tổ chức cần định nghĩa tác động, thời gian bắt đầu tính SLA, RTO/RPO, ngưỡng cảnh báo và quyền kích hoạt emergency change từ trước.

### 4.2. Bất biến an toàn

1. **Không bỏ qua xác minh danh tính hoặc MFA** chỉ vì IdP gặp sự cố; mọi ngoại lệ phải có phê duyệt, phạm vi và thời hạn.
2. **Không vô hiệu hóa toàn bộ Conditional Access, risk policy hoặc audit** để “cứu đăng nhập” khi chưa đánh giá và được phép.
3. **Không khôi phục account Leaver/Suspended** qua thao tác fix SSO, sync lại directory hoặc chạy job cũ.
4. **Không đổi quyền ứng dụng để chữa lỗi đăng nhập** nếu RBAC/ABAC không phải nguyên nhân.
5. **Không log secret, token, assertion, cookie hay mã MFA thô**; lưu request ID và dữ kiện đã che.
6. **Ưu tiên fail-safe/fail-closed theo chính sách** cho quyền nhạy cảm khi chưa thể xác minh trạng thái; cơ chế duy trì phiên hoặc truy cập khẩn cấp chỉ áp dụng nếu đã được thiết kế và kiểm thử.

## 5. SOP-IDP-01 — Nhận cảnh báo, xác nhận phạm vi và cô lập lỗi

**Trigger:** tỉ lệ sign-in failure tăng, endpoint IdP không truy cập được, cảnh báo SSO/MFA, ứng dụng đồng loạt lỗi đăng nhập hoặc đội hỗ trợ ghi nhận nhiều ticket.

### 5.1. Bước thực thi

1. **Mở incident record:** ghi thời điểm bắt đầu và múi giờ, người phát hiện, IdP tenant/realm, ứng dụng bị ảnh hưởng, severity ban đầu, correlation ID, thay đổi gần nhất và người phụ trách.
2. **Xác thực triệu chứng:** thu thập error code và request ID; kiểm tra endpoint IdP từ vị trí/đường kết nối đã được phê duyệt. Không thực hiện liên tục nhiều lần nhập mật khẩu gây lockout.
3. **So sánh nhiều ứng dụng và nhóm người:** app A/B đều lỗi hay chỉ A? user đang có session khác user đăng nhập mới? nội bộ và từ xa có khác nhau? admin và người dùng thường có cùng triệu chứng?
4. **Phân biệt xác thực với cấp quyền:** IdP đã cấp token/assertion thành công chưa? Nếu rồi mà app từ chối, chuyển điều tra sang Service Provider, SCIM, RBAC/ABAC hoặc session.
5. **Kiểm tra trạng thái IdP và dependencies:** health/status, authentication/authorization endpoints, directory, MFA, DNS, TLS, federation metadata, connector. Lưu thời điểm và nguồn của từng quan sát.
6. **Đánh giá rủi ro bảo mật:** số lần sign-in sai có tăng từ nhiều IP hay account không, có sign-in bất thường thành công, thay đổi role admin hoặc chứng chỉ không dự kiến không? Mời SOC nếu nghi tấn công.
7. **Đặt phạm vi, owner và priority:** xác định bước chặn rủi ro trong khi điều tra; liên lạc đội ứng dụng, directory và hạ tầng tương ứng.
8. **Thông báo đầu tiên:** mô tả triệu chứng được xác nhận, dịch vụ ảnh hưởng và phương án vận hành tạm được phép. Không khẳng định nguyên nhân gốc khi chưa có bằng chứng.

### 5.2. Kiểm thử đối chiếu an toàn

| Phép kiểm | Câu hỏi trả lời |
|---|---|
| Thử luồng đăng nhập chuẩn với tài khoản kiểm thử được phép | Có thể truy cập IdP, thực hiện MFA và nhận phiên mới không? |
| Kiểm tra một ứng dụng dùng cùng IdP | Lỗi có lan tới nhiều Service Provider không? |
| Kiểm tra người đang có phiên hợp lệ | Session hiện tại có tiếp tục đúng chính sách không? |
| Đọc sự kiện sign-in theo correlation ID | Lỗi xảy ra trước hay sau bước phát token/assertion? |
| Kiểm tra endpoint discovery/metadata theo quyền cho phép | Cấu hình issuer, endpoint, signing keys có còn đọc được không? |
| Đối chiếu ứng dụng có local login hoặc alternative IdP đã duyệt | Phương án khẩn cấp có thực sự sẵn sàng hay không? |

**Không dùng tài khoản người dùng bị ảnh hưởng để thử đăng nhập lặp**. Với môi trường sản xuất, test account phải có owner, quyền giới hạn và cơ chế kiểm soát; không dùng token/credential của người dùng khác.

## 6. SOP-IDP-02 — Chẩn đoán sự cố hạ tầng và điểm phụ thuộc

### 6.1. DNS, mạng, proxy và TLS

Nếu endpoint IdP không thể truy cập, xác định hostname, DNS resolution, route, proxy, firewall, certificate chain và độ lệch thời gian trên hệ thống tương ứng. Phân biệt lỗi toàn bộ IdP với lỗi trên một mạng hay vùng. Cần lưu thông tin kết nối cần thiết mà không xuất dữ liệu nhạy cảm.

| Biểu hiện | Kiểm tra ưu tiên | Hướng xử lý |
|---|---|---|
| Không resolve được hostname | DNS resolver, record, TTL, thay đổi gần nhất | Khôi phục cấu hình DNS theo change, xác minh từ nhiều điểm |
| TLS handshake/cert fail | Certificate chain, hostname, hạn hiệu lực, trust store, proxy | Sửa chuỗi tin cậy/cert đúng owner; không tắt TLS validation |
| Chỉ lỗi mạng công ty/VPN | Proxy, route, egress, firewall, split DNS | Đội Network sửa đường kết nối, không mở rộng firewall tùy tiện |
| Lỗi kết nối ngẫu nhiên, latency cao | Capacity, load balancer, backend health, throttling | Giảm tải/retry storm và chuyển lưu lượng theo thiết kế |
| Chỉ một region/tenant lỗi | Region/tenant settings, dependency, tuyến mạng | Cô lập phạm vi và kích hoạt kế hoạch failover nếu đã kiểm thử |

### 6.2. Directory và nguồn thông tin xác thực

IdP có thể hoạt động nhưng phụ thuộc directory hoặc identity store không phản hồi. Kiểm tra connectivity, health, replication, password validation, lockout, thời gian đồng bộ và phiên bản schema. Với hệ thống hybrid, phải xác định **nơi thực hiện xác thực thực tế** trước khi reset/unlock ở một console khác.

Không sửa thuộc tính nhân sự hoặc bật tài khoản chỉ để kiểm tra luồng; mọi thay đổi trạng thái danh tính vẫn phải tôn trọng nguồn chủ quản và JML. Nếu directory bị sai lệch sau phục hồi, đối soát account enablement và role chứ không chỉ kiểm tra login thành công.

### 6.3. MFA provider và chính sách truy cập

Nếu sau khi mật khẩu hợp lệ user không hoàn tất MFA, xem provider health, thiết bị, challenge result, policy/risk evaluation và phương thức đã đăng ký. Có thể là lỗi dịch vụ MFA, mất thiết bị, phishing-resistance policy hoặc điều kiện truy cập bị từ chối đúng thiết kế.

Phương án khôi phục phải dùng **quy trình MFA recovery có identity proofing**. Không gửi recovery code, bypass MFA toàn tenant hoặc bỏ risk policy chỉ để giảm số ticket. Nếu đội Security xác nhận rủi ro cao hoặc có security hold, chỉ mở lại khi điều kiện containment đạt.

### 6.4. Phân biệt outage với tấn công

Spike 401/403, account lockout hoặc challenge MFA thất bại có thể do script lỗi, thói quen retry của ứng dụng, credential stuffing hoặc password spraying. Kết luận cần dựa trên phân bố theo IP, client, thiết bị, tài khoản đích, tỷ lệ success/failure và cảnh báo SOC. Không kết luận mọi thất bại nhiều lần là IdP outage; cũng không xem một IP nội bộ là bằng chứng an toàn.

## 7. SOP-IDP-03 — Điều tra OIDC, OAuth 2.0 và token

**OpenID Connect (OIDC)** xây dựng cơ chế xác thực trên OAuth 2.0. Với một ứng dụng OIDC, người vận hành cần xác định lỗi nằm ở authorize request, đăng nhập/MFA, redirect callback, trao đổi mã lấy token, xác minh token hay tạo session tại ứng dụng.

### 7.1. Sơ đồ điểm lỗi

~~~mermaid
sequenceDiagram
    participant U as User / Browser
    participant A as App / Relying Party
    participant I as IdP
    U->>A: Mở tài nguyên
    A-->>U: Chuyển hướng tới authorize
    U->>I: Authorize request
    I->>I: Authenticate + MFA + Policy
    I-->>U: Redirect code / lỗi
    U->>A: Callback tới redirect URI
    A->>I: Trao đổi code tại token endpoint
    I-->>A: ID token / Access token
    A->>A: Kiểm tra issuer, audience, signature, exp, nonce
    A-->>U: Tạo session / trả thông báo
~~~

### 7.2. Bảng kiểm theo điểm lỗi

| Bước | Dấu hiệu | Kiểm tra |
|---|---|---|
| Authorization endpoint | Timeout, 5xx, quá nhiều redirect | IdP health, routing, endpoint, client registration |
| Đăng nhập/MFA | Invalid credentials, MFA failure, policy block | Sign-in log, directory, MFA và Conditional Access |
| Redirect/callback | Redirect URI mismatch, state mismatch | URI đã đăng ký, scheme/host, proxy, cookie và session state |
| Token endpoint | 401 client authentication, invalid grant, 5xx | Client credential theo vault, cấu hình trust, thời gian và replay |
| Token validation | Invalid signature, issuer/audience/expiry/nonce | JWKS, signing key rotation, clock skew, token validation rules |
| App session/authorization | Token hợp lệ nhưng app 403 hoặc chưa có user | Session management, SCIM, RBAC/ABAC, claim mapping |

**Không sao chép authorization code, access token, ID token, client secret hay cookie vào ticket.** Khi cần đối chiếu, ghi event ID và thông tin cấu hình không nhạy cảm.

### 7.3. Signing key và JWKS

Một đợt rotation khóa ký có thể làm ứng dụng từ chối token nếu ứng dụng không tải được khóa mới, cache JWKS hết hạn sai, thiếu `kid` phù hợp hoặc rollout IdP/app lệch pha. Xác định thời điểm rotation, issuer, thuật toán đã phê duyệt, key ID và cache behavior.

Biện pháp đúng là **khôi phục đồng bộ cấu hình khóa theo kế hoạch được duyệt** và kiểm thử chữ ký hợp lệ; không bỏ qua kiểm tra chữ ký, issuer, audience, expiry hoặc nonce chỉ để “cho đăng nhập”.

### 7.4. Token còn sống khi IdP lỗi

Một số ứng dụng có thể xác minh JWT bằng khóa công khai đã cache và tiếp tục chấp nhận token tới thời điểm hết hạn. Ứng dụng khác yêu cầu gọi introspection hoặc tải metadata/JWKS mới và có thể bị ảnh hưởng ngay. Do đó không đưa ra khẳng định chung rằng IdP outage sẽ ngay lập tức chặn hoặc tiếp tục toàn bộ token.

Với Mover/Leaver, đánh giá khả năng **revoke/deny tại resource server** và thu hồi session phía ứng dụng; không chỉ dựa vào việc IdP ngừng phát token mới.

## 8. SOP-IDP-04 — Điều tra SAML 2.0 federation

Với SAML SSO, ứng dụng dựa vào assertion do IdP ký và các kiểm tra về issuer, audience, destination, recipient, thời hạn, InResponseTo và metadata/certificate. Một lỗi ở một trong những thành phần này có thể giống outage IdP dù endpoint IdP vẫn sẵn sàng.

| Dấu hiệu | Kiểm tra có trọng tâm | Hành động an toàn |
|---|---|---|
| Invalid signature | Chứng chỉ ký, metadata, certificate rollover, key ID nếu áp dụng | Đồng bộ metadata/cert đúng quy trình; không tắt verify signature |
| Audience / recipient mismatch | Entity ID, ACS URL, SP configuration | Sửa cấu hình đúng tenant/environment |
| Assertion expired / not yet valid | Đồng hồ hệ thống, NotBefore, NotOnOrAfter và tolerance hợp lệ | Đồng bộ thời gian; chỉ điều chỉnh skew theo chính sách |
| InResponseTo / session correlation fail | SP session, replay protection, reverse proxy hoặc cookie | Điều tra flow/session; không bỏ kiểm tra chống replay |
| Tên người/thuộc tính lệch | NameID, attribute mapping, account linking | Đối chiếu ID bất biến; sửa mapping, tránh merge theo email |
| IdP SSO hoạt động nhưng SP từ chối | SP logs, provisioning state, quyền ứng dụng | Chuyển app owner và IAM để so actual–desired |

**Ví dụ:** sau khi IdP đổi chứng chỉ ký, một SaaS dùng metadata được cấu hình tĩnh và vẫn tin cậy chứng chỉ cũ. Các ứng dụng khác vẫn hoạt động. Đây là **sự cố cấu hình federation tại một Service Provider**, không đủ bằng chứng để tuyên bố toàn IdP bị ngừng hoạt động. Khắc phục bằng cập nhật trust/cert được phê duyệt, thử trên canary và kiểm tra đăng nhập sau thay đổi.

## 9. SOP-IDP-05 — Giảm tác động trong thời gian IdP không khả dụng

**Mục tiêu:** bảo vệ lối truy cập và duy trì hoạt động thiết yếu theo phương án dự phòng đã được thiết kế, đồng thời tránh tạo bypass thường trực.

### 9.1. Những lựa chọn có thể có và giới hạn

| Phương án | Điều kiện áp dụng | Rủi ro/kiểm soát |
|---|---|---|
| **Session ứng dụng đang còn hợp lệ** | App cho phép theo chính sách, session chưa hết hạn | Không kéo dài phiên tùy tiện; Leaver vẫn cần revoke quyền tại app |
| **Vùng/tenant IdP dự phòng** | Kiến trúc và cấu hình trust có sẵn, chuyển đổi được kiểm thử | Tránh split-brain, kiểm soát đồng nhất user, key, policy và log |
| **Break-glass admin** | Tài khoản/đường quản trị khẩn cấp đã có, bảo quản an toàn | Phê duyệt, MFA phù hợp, thời hạn, ghi log, hậu kiểm, rotation |
| **Local emergency access** | Ứng dụng quan trọng có cơ chế độc lập được phép | Quyền tối thiểu, hạn sử dụng, giám sát, không cho người dùng tự bypass |
| **Read-only/degraded mode** | Sản phẩm hỗ trợ và policy cho phép | Không mở rộng quyền, tránh thay đổi dữ liệu nhạy cảm thiếu kiểm soát |
| **Thao tác thủ công JML tại ứng dụng** | App owner/PAM có quyền được ủy quyền | Ticket, xác minh subject, phê duyệt, audit và reconcile sau khôi phục |

Không tự thiết lập IdP “phụ” trong lúc incident nếu chưa có trust và chính sách quản lý danh tính rõ ràng. Một đường xác thực khẩn cấp thiếu MFA, không ghi log hoặc tự động cấp admin làm tăng rủi ro và có thể kéo dài sau khi IdP hồi phục.

### 9.2. Quy trình kích hoạt phương án dự phòng

1. Incident Commander xác nhận điều kiện kích hoạt và phạm vi ảnh hưởng.
2. IAM/Security xác nhận **ai được phép dùng đường dự phòng, dùng để làm gì, ở hệ thống nào và trong bao lâu**.
3. PAM hoặc owner thực hiện theo change/emergency approval được quy định; tuyệt đối không chia sẻ mật khẩu qua ticket/chat công khai.
4. Ghi event/audit tối thiểu, tách quyền admin khỏi hoạt động người dùng thông thường và giám sát thao tác.
5. Duy trì danh sách người/tài khoản sử dụng bypass để phục hồi đúng trạng thái, revoke sau khi sự cố kết thúc và kiểm tra hoạt động.
6. Chỉ chuyển đổi vùng/tenant nếu các bên đã kiểm chứng khả năng đồng bộ danh tính, policy, signing keys, session và chiều quay về (failback).

### 9.3. Trạng thái fail closed và session tồn tại

Với yêu cầu cấp quyền mới hoặc truy cập đặc quyền mà không thể xác minh danh tính/chính sách, nên **từ chối mặc định** theo nguyên tắc least privilege. Nếu thiết kế cho phép dùng phiên có sẵn để duy trì nghiệp vụ, chỉ duy trì trong giới hạn được xác định; không kéo dài tuổi token, xóa bước MFA hay bỏ kiểm tra chữ ký vì IdP đang lỗi.

## 10. SOP-IDP-06 — Xử lý JML khi IdP hoặc connector gián đoạn

Sự cố IdP có thể ảnh hưởng đồng thời **authentication plane** và **provisioning plane**. Hai plane này có thể hoạt động khác nhau: SSO lỗi trong khi SCIM vẫn đồng bộ, hoặc SSO hoạt động nhưng API provisioning không khả dụng. Cần **kiểm chứng riêng cả hai**.

### 10.1. Joiner: người mới chưa kích hoạt hoặc chưa nhận quyền

1. Xác nhận danh tính, source HR/sponsor, ngày hiệu lực và phê duyệt.
2. Xác định bước nào fail: tạo user ở IdP, MFA enrollment, SSO, SCIM hay cấp role ứng dụng.
3. Với provisioning thất bại, giữ event ở trạng thái chờ có owner; không cấp local admin hoặc tạo tài khoản thứ hai chỉ để chạy tạm.
4. Nếu có đường onboarding dự phòng được duyệt, dùng **quyền tối thiểu, expiry và audit**, sau phục hồi đối soát để tránh tài khoản trùng.
5. Đóng khi IdP, ứng dụng bắt buộc và entitlement thực tế được xác minh.

### 10.2. Mover: quyền cũ và quyền mới có thể lệch nhau

1. Tính `desired state` từ vai trò và thuộc tính mới, kết hợp RBAC/ABAC, approval và SoD.
2. Chụp trạng thái `actual` ở IdP và ứng dụng (group, direct grants, nested roles, session/claim).
3. Nếu IdP lỗi khi cập nhật group/role, không chỉ cấp quyền mới tại ứng dụng rồi bỏ quên **thu hồi quyền cũ**.
4. Với quyền cũ có rủi ro cao, thực hiện thu hồi qua ứng dụng/PAM nếu được phê duyệt; ghi ngoại lệ đến khi đồng bộ xong.
5. Sau phục hồi, xử lý event theo version mới nhất và kiểm chứng quyền hiệu lực; với claim cache, revoke/refresh session phù hợp.

### 10.3. Leaver: ưu tiên chặn truy cập

**Leaver khẩn cấp** có thể không chờ IdP phục hồi mới xử lý. Nếu account đã Terminated nhưng IdP API không phản hồi:

1. Xác thực sự kiện Leaver từ nguồn có thẩm quyền và thời điểm hiệu lực, lập ticket/incident.
2. Chặn lối vào **còn điều khiển được**: ứng dụng đích, VPN, PAM, tài khoản local, cloud resources và điểm truy cập tập trung khác theo quyền được phân công.
3. Revoke session/refresh token/API token/SSH key hoặc deny ở resource server nếu nền tảng hỗ trợ; lưu ý session phát hành trước outage có thể vẫn tồn tại.
4. Ghi các target chưa thể kiểm chứng vào `PENDING_REVOKE` hoặc `EXCEPTION_OPEN`, có owner, mức rủi ro, deadline và biện pháp giảm thiểu.
5. Không replay tự động các event Joiner/Mover cũ làm `active=true` sau khi có Leaver. Dùng source version và lifecycle guard.
6. Sau khi IdP hồi phục, thực thi deprovision, đối soát từng target và xác nhận quyền đã thu hồi. Không ghi “offboarded toàn bộ” khi còn grant chưa xử lý.

### 10.4. Sơ đồ ưu tiên Leaver khi IdP outage

~~~mermaid
flowchart TD
    A[Leaver có hiệu lực] --> B{IdP / SCIM hoạt động?}
    B -->|Có| C[Disable IdP và deprovision targets]
    B -->|Không| D[Đánh dấu target lỗi / mở incident]
    D --> E[Chặn app/VPN/PAM/local access còn khả dụng]
    E --> F[Revoke session, token, key nơi có thể]
    F --> G[Giám sát và giữ ngoại lệ có owner]
    G --> H[IdP phục hồi]
    H --> C
    C --> I[Đối soát actual vs desired]
    I --> J{Còn đường truy cập?}
    J -->|Có| K[Thu hồi tiếp, không đóng incident]
    K --> I
    J -->|Không| L[Đóng bằng evidence]
~~~

## 11. Sự cố với service account và danh tính phi con người

Không phải tất cả workload đều phụ thuộc IdP theo cách người dùng đăng nhập. Một số service dùng client credentials, service principal, managed identity, workload federation, certificate hoặc long-lived secret. Chẩn đoán phải xác định chính xác trust chain.

| Workload pattern | Sự cố khi IdP/token service lỗi | Hướng xử lý |
|---|---|---|
| **Client credentials** | Không lấy được access token mới | Kiểm tra token endpoint, scope, client authentication và retry có giới hạn |
| **OIDC workload federation** | IdP của workload hoặc trust exchange không phản hồi | Kiểm tra issuer/JWKS/trust, retry, ảnh hưởng cache và expiry |
| **Managed identity** | Metadata/token endpoint hoặc platform identity subsystem lỗi | Phối hợp cloud/platform owner; dùng chế độ dự phòng đã thiết kế |
| **Certificate / secret-based** | Secret/cert hết hạn, rotation lệch pha, quyền vault lỗi | Sửa rotation và trust bằng quy trình change; không in secret |
| **Ứng dụng dùng token đã cache** | Token có thể tiếp tục có hiệu lực tới expiry | Đánh giá phạm vi, thời gian sống, revocation và quyền cục bộ |

Các nguyên tắc:

- Xác định **owner kỹ thuật và nghiệp vụ**, vai trò workload, môi trường, criticality và credential dependencies.
- Không chuyển tạm sang token cá nhân/admin cá nhân để vận hành production nếu không có quy trình khẩn cấp được phép; việc này làm mất tính truy vết và tạo quyền quá rộng.
- Đặt bounded retry/backoff để tránh token endpoint quá tải thêm; không retry liên tục bằng secret sai gây lockout.
- Sau khôi phục, kiểm tra rotate/expiry, policy trust, quyền tối thiểu, các phiên bản secret và hành động thực tế của ứng dụng.
- Với service account do nhân viên đã nghỉ tạo ra, chuyển owner và đánh giá lại quyền; không xóa workload production không còn owner một cách mù quáng và cũng không giữ bí mật cá nhân của Leaver.

## 12. SOP-IDP-07 — Phục hồi IdP và đưa dịch vụ trở lại

**Trigger:** đã có giải pháp cho nguyên nhân gốc hoặc nhà cung cấp/hạ tầng xác nhận tình trạng phục hồi. **Mục tiêu:** khôi phục đăng nhập và provisioning bình thường trong khi duy trì chính sách, không để quyền tồn dư hay bypass khẩn cấp.

### 12.1. Chuỗi hành động phục hồi

1. **Xác nhận thay đổi đã được phê duyệt:** rollback cấu hình sai, khôi phục dependency, chuyển vùng/tenant hoặc áp bản vá qua quy trình incident/change hiện hành.
2. **Kiểm tra health của IdP:** endpoint cần thiết, directory, MFA, policy engine, key/metadata, certificate, DNS/TLS, latency và error rate.
3. **Thử canary hạn chế:** dùng account thử nghiệm đúng policy, kiểm chứng luồng login mới cho những kiểu ứng dụng quan trọng (OIDC và SAML nếu có) và MFA/Conditional Access.
4. **Kiểm tra token và claim:** xác minh issuer, audience, signature, expiry, key rotation và session creation; không phát hành token giả hay bypass verification.
5. **Mở lại luồng người dùng theo thứ tự kiểm soát:** canary → một nhóm ứng dụng → phạm vi rộng hơn. Theo dõi 4xx/5xx, tỷ lệ thành công, tốc độ, account lockout và feedback.
6. **Khôi phục provisioning:** xử lý hàng đợi JML bị treo theo **thứ tự và source version**, ưu tiên các yêu cầu chặn truy cập rủi ro theo chính sách; kiểm tra idempotency và không tạo user trùng.
7. **Đối soát actual–desired:** nhất là Leaver, Mover, quyền admin, SCIM disabled state, local grants, API keys, session/token và đối tượng tạo thủ công khi outage.
8. **Thu hồi đường khẩn cấp:** đóng các quyền/local accounts/break-glass grants được cấp có thời hạn; rotate secret khi chính sách hoặc đánh giá sự cố yêu cầu và thực hiện hậu kiểm.
9. **Xác nhận ổn định:** giám sát qua khoảng thời gian đủ bao phủ cả ứng dụng dùng session ngắn và các batch job theo lịch. Không coi một lần canary success là toàn bộ dịch vụ đã phục hồi.
10. **Cập nhật incident:** ghi thời điểm bắt đầu/kết thúc, phạm vi, chứng cứ, ngoại lệ đang mở, owner và follow-up.

### 12.2. Tiêu chí phục hồi dịch vụ

| Điều kiện | Cách kiểm chứng |
|---|---|
| Luồng login mới hợp lệ hoạt động | Canary OIDC/SAML, MFA và sign-in log |
| App tạo session đúng | App owner kiểm tra thông tin phiên và luồng nghiệp vụ trong phạm vi phép thử |
| Policy không bị bypass | Xác minh MFA, Conditional Access, risk/ABAC còn hoạt động |
| JML backlog được xử lý an toàn | Đếm và đối soát event theo version; không có reactivation ngoài chính sách |
| Leaver không còn lối truy cập tồn dư | IdP, SCIM/app, PAM, VPN, local grants và token/session liên quan được kiểm tra |
| Break-glass/emergency path đã đóng | Audit, người dùng, role tạm, secret/key và hạn sử dụng được rà soát |
| Quan sát ổn định | Error rate, latency, sign-in success, lockout và provisioning delay trở về mức bình thường |

## 13. Thứ tự sự kiện JML, hàng đợi và đối soát sau outage

IdP outage khiến sự kiện JML có thể bị lưu hàng đợi, gửi lại, đến sai thứ tự hoặc thành công một phần. Một quy trình phục hồi an toàn cần xử lý trạng thái theo **subject + target**, với ID bất biến, phiên bản nguồn, desired state, actual state và audit.

### 13.1. Các trạng thái theo từng target

| Trạng thái | Ý nghĩa |
|---|---|
| `QUEUED` | Sự kiện được giữ nhưng chưa đủ điều kiện xử lý |
| `IN_PROGRESS` | Connector đang thực hiện |
| `UNKNOWN` | Request timeout; chưa rõ thay đổi đã được áp dụng chưa |
| `RETRYABLE` | Lỗi tạm thời, cần backoff và giới hạn retry |
| `BLOCKED` | Mapping/approval/identity không hợp lệ, không được cấp mới |
| `APPLIED` | API báo thành công, chưa xác minh trạng thái thực |
| `VERIFIED` | Target actual state phù hợp desired state |
| `EXCEPTION_OPEN` | Có lệch trạng thái cần owner, deadline, giảm thiểu |

### 13.2. Pseudocode phục hồi queue

~~~text
recover_jml_backlog(events):
    verify_idp_and_connectors_health()
    for subject in subjects_with_events(events):
        lock_processing_for_subject(subject)
        latest = read_authoritative_lifecycle(subject)
        targets = compute_required_targets(latest)

        for target in targets:
            desired = evaluate_current_policy_and_approvals(latest, target)
            actual = read_target_state(target, subject)

            if identity_mapping_is_ambiguous(subject, target):
                open_exception_and_block_grants(subject, target)
                continue

            plan = diff(actual, desired)
            if plan.is_empty:
                verify_effective_access(target, desired)
                continue

            if could_reactivate_terminated_subject(plan, latest):
                block_and_escalate()
                continue

            apply_idempotently_with_bounded_retry(plan)
            verify_target_state_or_open_exception(target, desired)

        record_audit_for_subject(subject)
~~~

Đây là pseudocode, không phải mã điều khiển production. Trên hệ thống thật cần kiểm soát đồng thời, idempotency key, version guard, rate limit, timeout, retry budget, dead-letter queue và reconciliation job. Một yêu cầu Joiner/Mover cũ không thể được phép ghi đè trạng thái Terminated mới. Timeout khi create không chứng minh chưa tạo tài khoản: phải đọc target trước khi thử tạo lại.

### 13.3. Actual–desired và quyền tồn dư

| Sai lệch | Ví dụ | Hành động |
|---|---|---|
| Thiếu account | Joiner đã Active nhưng SCIM chưa tạo SaaS user | Reconcile với ID bất biến, provision theo approval |
| Thiếu quyền | Mover chưa có role mới | Sửa mapping và cấp role đã duyệt |
| Quyền cũ tồn dư | Mover còn role admin từ đơn vị trước | Thu hồi tại app/PAM, xử lý session còn hiệu lực |
| Leaver còn active | IdP hoặc app không cập nhật trạng thái | Chặn đường còn truy cập, ưu tiên remediation và audit |
| Phiên/token cũ | Access token còn được chấp nhận dù đã disable | Revoke/deny tại ứng dụng hoặc resource server khi hỗ trợ |
| Account tạo bằng đường khẩn cấp | Local identity không liên kết IdP | Link/disable theo chính sách, loại bỏ bypass và chứng minh không còn grant dư |

## 14. Các bẫy kỹ thuật hay gặp

### 14.1. Chỉ một ứng dụng lỗi nhưng kết luận toàn IdP down

Một Service Provider có thể cấu hình sai `redirect_uri`, ACS URL, client secret, certificate, claim mapping hoặc session store. Phép so sánh với ứng dụng khác dùng chung IdP và sign-in log giúp cô lập thành phần. Đổi cấu hình tenant IdP diện rộng khi lỗi chỉ ở một app có thể tạo outage lớn hơn.

### 14.2. Status endpoint hoạt động nhưng đăng nhập vẫn lỗi

Healthcheck hạ tầng có thể chỉ kiểm tra HTTP 200 ở một endpoint, trong khi directory, MFA, token signing hoặc consent/policy engine đã lỗi. Phải kết hợp endpoint health với canary sign-in và telemetry từ các bước thực tế. Không dùng healthcheck đơn lẻ làm điều kiện đóng incident.

### 14.3. Thử đăng nhập liên tục khiến account lockout

Khi IdP chậm hoặc user nhầm credential, retry vô hạn có thể kích hoạt khóa tài khoản hoặc rate limit. Hạn chế test có kiểm soát, phân biệt lỗi mật khẩu với outage, xử lý nguồn retry và giữ tài khoản kiểm thử được quản lý.

### 14.4. Vội rollback cấu hình khóa ký

Rollback signing certificate hoặc JWKS mà không đánh giá token/assertion đã phát hành có thể làm ứng dụng từ chối phiên mới hoặc cũ. Cần kế hoạch rollover/failback rõ ràng, kiểm tra các relying party và lưu bằng chứng đổi cấu hình.

### 14.5. Giữ break-glass quá lâu

Đường khẩn cấp được cấp trong outage có thể trở thành quyền tồn dư sau khi IdP hoạt động lại. Bắt buộc hậu kiểm thời hạn, owner, log hành động, quyền local, phiên, token/secret đã phát hành và rotation phù hợp.

### 14.6. Khôi phục SSO nhưng bỏ quên SCIM/JML

Người dùng đã đăng nhập được nhưng Joiner chưa được provision, Mover còn quyền cũ và Leaver chưa thu hồi phiên; “SSO xanh” không đồng nghĩa quản lý vòng đời đã an toàn. Cần reconciliation và dashboard cho từng loại JML sau outage.

## 15. Giám sát, SLO và phát hiện sự cố IdP

Một dashboard IAM nên phân tách **khả dụng IdP, hiệu quả xác thực, federation, provisioning và quyền truy cập** để không chôn giấu sự cố JML trong con số login success.

| Metric | Ý nghĩa |
|---|---|
| **Authentication success rate** | Tỉ lệ đăng nhập hợp lệ thành công, chia theo ứng dụng, region, loại client |
| **Endpoint availability/latency** | Khả dụng và độ trễ của authorize/token/SSO/metadata endpoints theo đúng luồng |
| **MFA completion/failure** | Tỉ lệ challenge hoàn tất, lỗi provider và policy block |
| **Federation error rate** | Tỉ lệ lỗi issuer, signature, redirect, callback, audience, assertion expiry |
| **Token issuance/rejection** | Số token phát hành, lỗi ký, lỗi xác minh ở ứng dụng theo nguyên nhân |
| **Account lockout rate** | Số subject bị khóa, mức lặp, khác biệt credential vs attack |
| **Provisioning/reconciliation drift** | Số target actual khác desired, tách Joiner, Mover, Leaver |
| **Leaver revocation latency** | Từ thời điểm Leaver hiệu lực đến khi lối truy cập trọng yếu và target được verified |
| **Backlog age / DLQ count** | Độ tuổi sự kiện JML chưa xử lý, lỗi retry và trường hợp bị kẹt |
| **Emergency access usage** | Mức sử dụng break-glass/local emergency access, owner và thời gian tồn tại |

SLO nên mô tả **điều mà người dùng hợp lệ và security cần**: hoàn tất đăng nhập đúng policy, cấp quyền đúng hạn, thu hồi quyền Leaver có xác nhận. Nếu một nhóm người vẫn login được nhờ session cũ, số liệu session success không phản ánh khả năng phát hành đăng nhập mới. Đo riêng hai trạng thái.

Các ngưỡng cảnh báo không có con số cố định áp dụng cho mọi môi trường. Đội vận hành nên xây ngưỡng từ baseline, business criticality, thời gian chờ event và tác động người dùng, kèm đường escalation rõ ràng.

## 16. Mẫu hồ sơ incident và audit

~~~yaml
incident_id: IAM-IDP-EXAMPLE-104
severity: P1
detected_at: "2026-11-23T10:05:00+07:00"
idp_ref: corporate-idp-tenant-a
observed_symptoms:
  - oidc-token-endpoint-latency
  - mfa-challenge-failures
affected_scope:
  applications:
    - employee-portal
    - ticketing-app
  new_login: IMPACTED
  existing_sessions: PARTIALLY_AVAILABLE
correlation_refs:
  - signin-event-5091
  - app-trace-884
security_assessment_ref: soc-review-104
change_approval_ref: emergency-change-104
root_cause_category: IDP_DEPENDENCY_FAILURE
recovery:
  canary_oidc: VERIFIED
  canary_saml: VERIFIED
  mfa_policy: VERIFIED
  app_sessions: VERIFIED
jml_reconciliation:
  joiners_pending: 0
  movers_with_old_grants: 0
  leavers_pending_revoke: 0
emergency_access_review_ref: privileged-review-104
exceptions: []
restored_at: "2026-11-23T11:20:00+07:00"
incident_status: CLOSED
~~~

Các ID, số liệu và thời điểm là **giả lập**. Trong thực tế, lưu liên kết tới log đã bảo vệ: event gốc, request ID, kết quả phân tích, người phê duyệt, thay đổi cấu hình, xác minh canary, kết quả JML và danh sách ngoại lệ. Audit không được chứa mật khẩu, access token, authorization code, ID token, SAML assertion chưa che, cookie phiên hoặc recovery code.

### 16.1. Bằng chứng để đóng incident

1. **Triệu chứng và phạm vi:** log/metrics chứng minh xảy ra gián đoạn gì và ứng dụng/người dùng nào bị ảnh hưởng.
2. **Nguyên nhân và can thiệp:** root cause, change ID, thao tác hoặc provider action, thời gian và người chịu trách nhiệm.
3. **Tính khả dụng đã kiểm chứng:** canary OIDC/SAML, MFA, chính sách và app session trong phạm vi.
4. **Khả năng kiểm soát truy cập:** Leaver, Mover, quyền admin, SCIM, local accounts và session/token liên quan được đối soát.
5. **Quyền khẩn cấp đã đóng:** break-glass/local access có hậu kiểm và không còn tồn dư ngoài phê duyệt.
6. **Ngoại lệ còn mở:** nếu có, owner và hạn khắc phục; tách rõ tình trạng dịch vụ đã phục hồi với tình trạng remediation còn tiếp tục.

## 17. Bài tập tình huống có lời giải định hướng

### Tình huống A — Các ứng dụng đều báo lỗi SSO

Portal, CRM và ticketing đều timeout ở bước redirect tới IdP; DNS hoạt động nhưng authorize endpoint 503 từ nhiều mạng. User đang có session ứng dụng vẫn xem được một số dữ liệu.

**Hướng xử lý:** mở incident IdP, kiểm tra status/health và dependency, đánh giá tác động đăng nhập mới, xem phương án continuity đã phê duyệt. Không cho phép kéo dài mọi phiên vô hạn; bảo đảm có đường xử lý Leaver ở ứng dụng trong thời gian outage. Sau phục hồi, canary sign-in và đối soát JML backlog.

### Tình huống B — Chỉ một SaaS lỗi sau khi đổi signing certificate

Các ứng dụng dùng OIDC bình thường; một SaaS dùng SAML báo invalid signature sau đợt certificate rollover.

**Hướng xử lý:** so metadata/cert hiện tại ở IdP và SaaS, xác nhận issuer/audience, phối hợp application owner cập nhật trust theo change. Kiểm tra SAML assertion được xác minh đúng, tuyệt đối không tắt signature verification hoặc chỉnh tenant toàn cục chỉ vì một app.

### Tình huống C — MFA provider lỗi trên diện rộng

Người dùng nhập mật khẩu đúng nhưng challenge không gửi được. IdP endpoint và directory vẫn khỏe, ứng dụng không tạo được phiên mới.

**Hướng xử lý:** cô lập MFA dependency, kiểm tra risk policy/provider, escalation và kênh khôi phục đã thiết kế. Duy trì MFA/phương thức thay thế được phê duyệt, không tắt yếu tố thứ hai cho toàn bộ tenant. Sau phục hồi kiểm tra cả MFA success lẫn policy enforcement.

### Tình huống D — Leaver khẩn cấp trong lúc IdP API outage

HR ra lệnh chấm dứt ngay; API IdP trả timeout, nhưng SaaS vẫn có local login và API token của người đó.

**Hướng xử lý:** xác minh lệnh từ nguồn có thẩm quyền, chặn local app/VPN/PAM đang điều khiển được, revoke token/session tại target, ghi các đích chưa thể xử lý và owner. Khi IdP hồi phục, disable account, không replay job cũ active=true và kiểm chứng mọi grant/token đã thu hồi.

### Tình huống E — IdP phục hồi nhưng Mover vẫn còn quyền cũ

Sau outage, nhóm mới của nhân viên Finance được gán thành công nhưng nhóm Support cũ không bị gỡ vì event revoke bị kẹt trong queue.

**Hướng xử lý:** không đóng toàn bộ remediation theo trạng thái SSO xanh. Đối soát desired–actual, ưu tiên gỡ quyền Support, kiểm tra nested grants và token/phiên cũ, xác minh SoD và lưu evidence. Sửa queue retry và version guard để tránh tái diễn.

### Tình huống F — Service workload không lấy được token mới

Một batch job dùng workload federation lỗi token exchange, trong khi user SSO trình duyệt không có lỗi. Có người đề nghị thay bằng token admin cá nhân.

**Hướng xử lý:** xác định issuer/trust, token endpoint, credential method, policy workload và secret rotation. Khôi phục bằng service identity đúng owner và least privilege, retry giới hạn, kiểm thử trong phạm vi được phép. Không dùng token cá nhân để bỏ qua service principal hoặc audit.

## 18. Checklist vận hành nhanh

| Giai đoạn | Câu hỏi để nghiệm thu |
|---|---|
| **Intake** | Incident ID, phạm vi, thời điểm, error/correlation ID và severity đã có? |
| **Triage** | Đã phân biệt lỗi IdP, directory, MFA, OIDC/SAML, SCIM và ứng dụng? |
| **Security** | Có dấu hiệu tấn công, account compromise hoặc emergency hold? SOC đã đánh giá khi cần? |
| **Containment** | Quyền nhạy cảm được bảo vệ, Leaver được chặn tại các đích còn điều khiển được? |
| **Continuity** | Nếu dùng failover/break-glass, có approval, scope, expiry và audit? |
| **Recovery** | Đã khôi phục hạ tầng, federation, signing metadata và MFA theo change được phê duyệt? |
| **Canary** | Luồng đăng nhập mới OIDC/SAML, MFA và app session đã xác minh? |
| **JML reconciliation** | Joiner, Mover, Leaver và service identities đã đối soát actual–desired? |
| **Residual access** | Phiên/token, local grant, break-glass và quyền admin cũ đã rà soát? |
| **Closure** | Bằng chứng đủ, monitoring ổn định, ngoại lệ còn mở có owner/deadline? |

## 19. Kết luận thực hành

Một sự cố **Identity Provider** cần được xử lý ở đúng lớp: hạ tầng, directory, MFA, federation OIDC/SAML, token, ứng dụng hay provisioning. Khôi phục đăng nhập chỉ là một phần của mục tiêu. **Runbook IAM operations hoàn chỉnh** còn phải đảm bảo quyết định Joiner–Mover–Leaver vẫn được thực thi đúng, session và quyền truy cập không còn hợp lệ được thu hồi, các đường truy cập khẩn cấp được đóng và kết quả có bằng chứng kiểm toán.

Nguyên tắc cuối cùng là **khôi phục sự sẵn sàng mà vẫn giữ nguyên ranh giới tin cậy**: xác thực đúng chủ thể, áp RBAC/ABAC và MFA theo chính sách, không cho event cũ mở lại Leaver và kiểm chứng actual state tại ứng dụng thay vì dừng ở một thông báo IdP đã hoạt động trở lại.
