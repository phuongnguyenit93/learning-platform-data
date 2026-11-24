# B2B federation trong quản lý vòng đời danh tính (IAM)

## 1. B2B federation là gì?

**B2B federation (Business-to-Business identity federation)** là cơ chế để một tổ chức cho phép người dùng của tổ chức khác đăng nhập vào ứng dụng hoặc tài nguyên của mình thông qua **quan hệ tin cậy giữa các hệ thống định danh**. Thay vì yêu cầu mọi nhân viên đối tác tạo và nhớ một mật khẩu riêng tại tổ chức cung cấp dịch vụ, ứng dụng có thể dựa vào bằng chứng xác thực do **Identity Provider (IdP)** được ủy thác phát hành.

Ví dụ: Công ty A vận hành nền tảng đặt hàng; Công ty B là nhà phân phối. Nhân viên B truy cập cổng của A, được chuyển đến IdP của B để xác thực, rồi quay về cổng A. A kiểm tra thông tin xác thực đã nhận và quyết định có cấp phiên đăng nhập không. Sau đó A vẫn phải kiểm tra **nhân viên này có được xem đơn hàng, thuộc tenant và dự án nào**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, B2B federation liên kết trực tiếp với việc quản lý vòng đời danh tính **Joiner–Mover–Leaver**:

- **Joiner:** xác minh doanh nghiệp đối tác, thiết lập trust với IdP, liên kết người dùng, duyệt quyền và tạo membership.
- **Mover:** thay đổi người dùng, nhóm, hợp đồng, đối tác, role hoặc chính IdP; kiểm tra và điều chỉnh quyền.
- **Leaver:** vô hiệu hóa quan hệ hoặc principal, thu hồi quyền tại ứng dụng đích, xử lý phiên, token và cấu hình trust.

Federation giúp giảm số lượng mật khẩu rời rạc, tạo trải nghiệm **Single Sign-On (SSO)** và cho phép đối tác quản lý hoạt động xác thực của nhân viên họ. Tuy nhiên, **xác thực liên kết không chuyển giao trách nhiệm phân quyền dữ liệu**: A vẫn là bên quyết định ai được làm gì trên tài nguyên của A.

### Thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Identity Provider (IdP) | Nguồn xác thực người dùng và phát hành chứng cứ danh tính | IdP của B |
| Service Provider (SP) | Ứng dụng tiêu thụ SAML assertion | Cổng quản lý đơn hàng A |
| Relying Party (RP) | Ứng dụng dùng OIDC để xác thực người dùng | Web app của A |
| Authorization Server (AS) | Phát hành OAuth token theo cấu hình đã đăng ký | Nền tảng xác thực của B hoặc bên được A tin cậy |
| Federation trust | Cấu hình kỹ thuật và chính sách tin cậy giữa hai bên | Issuer, khóa ký, audience, endpoint, policy |
| Assertion / ID token | Chứng cứ danh tính được phát hành và xác minh | SAML assertion hoặc OIDC ID token |
| Local principal | Bản ghi đại diện cho người dùng tại A | External user ID 7451 |
| Partner membership | Quan hệ giữa principal và tổ chức/tenant/dự án | User 7451 thuộc partner B |
| Entitlement / grant | Quyền được cấp trên tài nguyên cụ thể | orders.read tại tenant B |
| Provisioning | Tạo/cập nhật/vô hiệu hóa bản ghi và nhóm | SCIM, lời mời, JIT provisioning |

**Phân biệt B2B federation với B2C social login:** cả hai có thể dùng OIDC, nhưng B2B thường yêu cầu xác minh tổ chức, quản lý trust cho từng đối tác, tenant isolation, sponsor, hợp đồng, quyền ủy quyền và quy trình offboarding cấp tổ chức. Social login cho khách hàng cá nhân có bài toán consent và tài khoản khách hàng khác.

## 2. Những ranh giới tin cậy không được đánh đồng

Một đăng nhập B2B đi qua ít nhất ba lớp kiểm tra:

1. **Business trust:** đối tác B là tổ chức nào, có được xác minh, hợp đồng nào còn hiệu lực, ai là sponsor tại A và phạm vi hợp tác là gì?
2. **Identity trust:** A có nhận chứng cứ xác thực từ đúng IdP/issuer được phê duyệt cho B không? Chữ ký, khóa, audience, thời gian, flow và endpoint có hợp lệ không?
3. **Authorization:** principal cụ thể đã được duyệt truy cập ứng dụng, tenant, dự án và hành động đang yêu cầu chưa? Role và điều kiện còn hiệu lực không?

Một SAML assertion hoặc OIDC ID token hợp lệ chỉ có thể làm cơ sở cho bước **authentication** và liên kết danh tính. Chúng không tự chứng minh hợp đồng còn hiệu lực hoặc nhân viên có quyền xem dữ liệu của tổ chức khác.

Ví dụ: Hai nhân viên B đều đăng nhập hợp lệ qua IdP B. Người thứ nhất có grant đọc báo cáo dự án P42, người thứ hai chưa được sponsor của A phê duyệt. A phải cho người thứ nhất xem báo cáo P42 và từ chối người thứ hai. Nếu người thứ nhất thử mở dự án của C, A tiếp tục từ chối vì sai tenant.

### Vì sao email không đủ?

Email là thuộc tính liên lạc và có thể đổi, tái sử dụng hoặc có domain được dùng chung. Trong OIDC, nên liên kết người dùng bằng **cặp (iss, sub)** sau khi xác thực ID token đúng quy tắc. Với SAML, dùng định danh ổn định từ đúng issuer, chẳng hạn persistent NameID hoặc thuộc tính định danh bất biến đã được hai bên thỏa thuận. Phải quản lý ánh xạ nguồn định danh tới **partner_id** và local principal, không tự ghép hai tài khoản chỉ vì email bằng nhau.

Một doanh nghiệp cũng có thể có nhiều IdP, hoặc nhiều doanh nghiệp dùng chung một nhà cung cấp IdP. **Định danh tổ chức đối tác khác với issuer**; hệ thống cần mối quan hệ ánh xạ được quản trị và kiểm chứng.

## 3. Kiến trúc tổng thể

~~~mermaid
flowchart LR
    subgraph B["Tổ chức B"]
      U["Nhân viên B"]
      IDP["IdP của B"]
      PROV["Provisioning service B"]
      U --> IDP
    end
    subgraph A["Tổ chức A"]
      APP["Ứng dụng / RP / SP"]
      IAM["External identity registry"]
      TRUST["Partner & trust registry"]
      POLICY["RBAC / ABAC + tenant policy"]
      DATA["Tài nguyên tenant B, C..."]
      AUDIT["Audit / access review"]
      APP --> POLICY
      POLICY --> IAM
      POLICY --> TRUST
      POLICY --> DATA
      APP --> AUDIT
      IAM --> AUDIT
    end
    IDP <-->|"OIDC hoặc SAML"| APP
    PROV -->|"SCIM nếu tích hợp"| IAM
    OWNER["Sponsor / resource owner A"] -->|"Duyệt quyền và trust"| TRUST
    OWNER --> IAM
~~~

Các luồng có chức năng khác nhau:

- **SSO bằng OIDC hoặc SAML:** user chứng minh danh tính thông qua IdP; app A xác nhận kết quả và tạo phiên theo chính sách của A.
- **SCIM:** khi được triển khai, đồng bộ trạng thái user/group giữa nguồn provisioning và hệ thống đích.
- **RBAC/ABAC:** ràng buộc role, tenant, hợp đồng, dự án và điều kiện truy cập tại A.
- **Audit và access review:** phát hiện truy cập bất thường, thay đổi quyền, tài khoản mồ côi và quyền tồn dư.

SSO, SCIM và quyền tài nguyên là **ba vấn đề riêng**. Bật SSO không tự động tạo cơ chế deprovision; bật SCIM không tự động vô hiệu hóa mọi phiên hoặc khóa API đang sống.

### Federation hub hoặc broker

Khi A có hàng trăm đối tác, mỗi đối tác có IdP khác nhau, một **identity broker** có thể nhận đăng nhập từ các IdP rồi phát hành kết quả xác thực nhất quán cho ứng dụng A. Điều này giảm cấu hình riêng tại từng ứng dụng nhưng tạo ra một điểm tin cậy quan trọng: broker phải định danh đúng IdP nguồn, giữ ngữ cảnh issuer/subject, áp dụng policy mapping và chống nhầm tenant. Không nên để broker làm mất dấu nguồn gốc danh tính.

## 4. Chọn giao thức: OIDC hay SAML?

| Khía cạnh | OIDC | SAML 2.0 |
|---|---|---|
| Mô hình chính | Lớp xác thực trên OAuth 2.0 | Liên kết xác thực dựa trên XML assertion |
| Bên nhận | Relying Party / OIDC Client | Service Provider |
| Bằng chứng đăng nhập | ID token dạng JWT và luồng OIDC | SAML Response/Assertion có chữ ký hợp lệ |
| Transport phổ biến | HTTPS redirect + token endpoint | Browser redirect/POST; có thể dùng metadata |
| Cấu hình trust | Issuer, discovery, JWKS, client registration, redirect URI | EntityID, SSO endpoint, signing certificate, ACS URL, metadata |
| Danh tính ổn định | Subject gắn với issuer | NameID/thuộc tính ổn định gắn issuer |
| API access | OAuth access token là cơ chế riêng nhưng thường kết hợp | SAML không trực tiếp là access token cho API |
| Thường phù hợp | Ứng dụng web hiện đại, mobile, dịch vụ OIDC | Nhiều hệ thống doanh nghiệp/SaaS lâu năm |

Hai giao thức đều có thể phù hợp cho B2B SSO. Lựa chọn dựa trên tính năng IdP đối tác, ứng dụng nhận, chính sách bảo mật, vận hành và khả năng quản lý trust. **Không suy rằng OIDC tự an toàn hơn SAML hoặc ngược lại**: kết quả phụ thuộc cấu hình, xác minh và quy trình vận hành.

Trong cả hai mô hình, ứng dụng phải tách:

- Chứng minh danh tính của con người;
- Tạo phiên tại ứng dụng của A;
- Quyết định quyền theo local principal và chính sách A;
- Xử lý vòng đời bản ghi/nhóm ở hệ thống đích;
- Thu hồi phiên và quyền khi Leaver.

## 5. Luồng OIDC B2B với Authorization Code Flow

Với ứng dụng web, một mẫu triển khai phổ biến là **OIDC Authorization Code Flow**; **PKCE** nên được sử dụng phù hợp với loại client và chính sách an ninh, đặc biệt bắt buộc cho public clients trong các cấu hình hiện đại.

~~~mermaid
sequenceDiagram
    actor U as Người dùng B
    participant APP as Ứng dụng A / RP
    participant IDP as IdP B / OP
    participant IAM as IAM / policy A
    U->>APP: Yêu cầu đăng nhập
    APP->>APP: Tạo state, nonce, PKCE verifier/challenge
    APP-->>U: Redirect authorization request
    U->>IDP: Xác thực tại IdP B
    IDP-->>U: Redirect callback với authorization code + state
    U->>APP: Gửi callback
    APP->>APP: Kiểm tra state và callback
    APP->>IDP: Đổi code tại token endpoint + PKCE verifier
    IDP-->>APP: ID token (và token phù hợp)
    APP->>APP: Xác minh issuer, signature, audience, expiry, nonce...
    APP->>IAM: Lookup (issuer, subject), partner, grant, status
    IAM-->>APP: Allow hoặc deny
    APP-->>U: Tạo phiên ứng dụng hoặc từ chối
~~~

Các bước cốt lõi:

1. **Tìm đúng IdP:** A xác định IdP B từ invitation, partner context hoặc cơ chế khám phá tổ chức được thiết kế an toàn; không chọn tùy ý issuer theo dữ liệu chưa xác minh trong request.
2. **Bắt đầu yêu cầu đăng nhập:** RP chuẩn bị state chống CSRF và ràng buộc response với request, nonce cho OIDC ID token khi áp dụng, PKCE verifier/challenge cho luồng authorization code.
3. **Người dùng xác thực tại IdP B:** IdP thực hiện MFA hoặc chính sách xác thực tương ứng, sau đó trả authorization code qua redirect đã đăng ký.
4. **A kiểm tra callback:** state khớp phiên yêu cầu, redirect đúng và code thuộc luồng đang xử lý.
5. **A đổi code lấy token:** trao đổi qua kênh bảo mật với đúng token endpoint, dùng client authentication nếu là confidential client và PKCE verifier khi đã dùng.
6. **A xác minh ID token:** chữ ký từ khóa đáng tin, issuer đúng, audience chứa client được đăng ký, thời gian hiệu lực, nonce khi có, các điều kiện liên quan azp/auth_time nếu áp dụng; chống nhầm issuer và token substitution.
7. **A liên kết danh tính và phân quyền:** tìm local principal theo (iss, sub), xác minh partner/membership còn active và grants còn hiệu lực; tạo phiên A nếu thỏa chính sách.

### Những trường trong ID token

Ví dụ chỉ để minh họa payload, **chưa phải một JWT có chữ ký hợp lệ**:

~~~json
{
  "iss": "https://login.partner.example/tenant-b",
  "sub": "external-subject-7b3",
  "aud": "rp-client-a-portal",
  "iat": 1794570000,
  "exp": 1794570300,
  "nonce": "nonce-for-this-login",
  "email": "worker@partner.example"
}
~~~

Giá trị email chỉ là thuộc tính bổ sung; local principal phải được liên kết từ nguồn đã xác minh. A không được xem bất kỳ JWT nào có trường role hoặc aud là token đăng nhập hợp lệ. **ID token dùng để xác thực người dùng tại RP**; API cần **access token** có issuer/audience/scope phù hợp và policy kiểm tra ở resource server. Không nên gửi ID token như bearer token để truy cập tài nguyên API.

### Lưu ý bảo mật OIDC

- Đăng ký chính xác redirect URI; từ chối redirect mở hoặc không nằm trong danh sách cho phép.
- Lấy JWKS từ endpoint đáng tin của issuer đã cấu hình; không tùy ý làm theo URL khóa do token không đáng tin chỉ định.
- Giới hạn thuật toán chữ ký được chấp nhận; không chấp nhận token unsigned hoặc thuật toán bị đổi bất ngờ.
- Dùng state, nonce và PKCE phù hợp luồng để chống các dạng giả mạo/tấn công vào callback.
- Với nhiều authorization server, chống **authorization server mix-up** bằng cách liên kết request, callback và issuer/AS được chọn.
- Kiểm soát cookie session của ứng dụng A bằng Secure, HttpOnly, SameSite phù hợp luồng; bảo vệ chống session fixation và CSRF theo loại request.
- Không lưu ID token, access token hoặc refresh token vào log; lưu tham chiếu/tín hiệu audit phù hợp.
- Hạn phiên ứng dụng A có thể khác thời hạn phiên IdP B. Đăng xuất khỏi IdP B không mặc định làm mọi phiên ứng dụng A biến mất.

## 6. Luồng SAML 2.0 B2B

Một tích hợp SAML phổ biến dùng **SP-initiated SSO**:

~~~mermaid
sequenceDiagram
    actor U as Người dùng B
    participant SP as Ứng dụng A / SP
    participant IDP as IdP của B
    participant IAM as IAM / policy A
    U->>SP: Truy cập ứng dụng
    SP->>SP: Tạo AuthnRequest + request ID
    SP-->>U: Redirect đến IdP B
    U->>IDP: Đăng nhập theo chính sách B
    IDP-->>U: SAML Response/Assertion
    U->>SP: POST tới Assertion Consumer Service
    SP->>SP: Xác minh chữ ký, issuer, audience, timing, destination...
    SP->>IAM: Lookup subject, partner, grants
    IAM-->>SP: Allow hoặc deny
    SP-->>U: Phiên ứng dụng hoặc từ chối
~~~

Các thành phần kỹ thuật:

| Thành phần | Vai trò |
|---|---|
| SP EntityID | Định danh SP mà assertion dành cho |
| IdP EntityID | Định danh nguồn assertion tin cậy |
| SSO Endpoint | Điểm người dùng được chuyển tới để xác thực |
| Assertion Consumer Service (ACS) URL | Endpoint nhận SAML Response ở SP |
| Signing certificate / metadata | Cơ sở kiểm tra chữ ký và cấu hình liên thông |
| NameID hoặc subject attribute | Định danh user trong phạm vi issuer |
| AudienceRestriction | Giới hạn assertion cho SP dự kiến |
| Conditions / SubjectConfirmationData | Hạn thời gian, recipient, InResponseTo và các điều kiện liên quan |

**SP phải thực sự xác minh chữ ký và cấu trúc assertion** theo cấu hình đã phê duyệt; không chỉ giải mã Base64 rồi tin nội dung. Cần kiểm tra issuer, audience, recipient/destination, thời gian với độ lệch đồng hồ hợp lý, SubjectConfirmation, InResponseTo cho luồng SP-initiated, replay protection và định danh nguồn. Cần xử lý các trường hợp XML signature wrapping bằng thư viện đáng tin cậy và gắn đúng đối tượng đã được xác minh chữ ký với dữ liệu đưa vào ứng dụng.

Với IdP-initiated SSO, việc thiếu request ID từ SP thay đổi bề mặt bảo mật. Chỉ bật khi hiểu rõ rủi ro, có điều kiện ràng buộc và cơ chế chống replay/login CSRF thích hợp. Khi có thể, ưu tiên luồng SP-initiated để dễ liên kết request với response.

### Federation trust và key rotation

A thường nhập metadata hoặc cấu hình do B cung cấp qua kênh đã xác minh, gồm issuer/entityID, endpoint, public signing certificate/JWKS, phương thức đăng nhập và các chính sách. Nên:

1. Xác nhận người đại diện B có thẩm quyền yêu cầu cấu hình hoặc đổi khóa.
2. Ghi nhận khóa/certificate nào được phép, thời hạn và người phê duyệt.
3. Chuẩn bị giai đoạn chấp nhận khóa cũ/mới được giới hạn để xoay khóa có kiểm soát.
4. Kiểm thử chữ ký, issuer, audience, login đúng/sai trước khi cutover.
5. Thu hồi trust cũ sau chuyển đổi và theo dõi lỗi đăng nhập bất thường.

Certificate hết hạn không đồng nghĩa quan hệ hợp tác kết thúc; ngược lại, hợp đồng kết thúc phải kích hoạt thu hồi truy cập kể cả khi certificate vẫn còn giá trị kỹ thuật.

## 7. Khởi tạo quan hệ B2B federation (Partner Joiner)

Quy trình onboarding nên bắt đầu từ **quan hệ tổ chức**, rồi đến các **người dùng và entitlement**. Điều này ngăn việc chỉ cần nhân viên B đăng nhập là được tạo quyền tùy ý tại A.

### 7.1. Xác minh và đăng ký đối tác

Các dữ liệu thường cần:

- Partner ID nội bộ ổn định, pháp nhân/đầu mối đã được xác minh;
- Hợp đồng, loại tài nguyên, mục đích sử dụng dữ liệu, tenant/dự án được chia sẻ;
- Sponsor và resource owner của A;
- Issuer/entityID và IdP owner phía B;
- Ngày kích hoạt, hạn quan hệ, điều kiện MFA và ngày review;
- Nguồn lifecycle event và người chịu trách nhiệm thông báo rời tổ chức;
- Quy trình xử lý sự cố, support và thay đổi IdP.

Một partner có thể dùng nhiều IdP nhưng mỗi quan hệ trust phải được đăng ký rõ. Không quyết định partner_id từ email do người dùng tự gửi hoặc từ tên doanh nghiệp trong claim chưa được A thẩm định.

### 7.2. Cấu hình trust theo nguyên tắc tối thiểu

Mẫu cấu hình logic (không phải định dạng bắt buộc):

~~~yaml
partner:
  id: "partner-B"
  status: "active"
  sponsor: "owner-A-17"
  valid_until: "2026-12-31"
  allowed_tenants:
    - "tenant-B"
  federation:
    protocol: "oidc"
    issuer: "https://login.partner.example/tenant-b"
    client_id: "rp-client-a-portal"
    require_mfa_for_sensitive_access: true
  provisioning:
    mode: "invitation-and-scim"
    default_role: "none"
  access_review:
    next_due: "2026-12-01"
~~~

Các điểm cần đảm bảo:

1. **Deny by default:** partner hoặc principal chưa duyệt không có quyền dữ liệu.
2. Trust chỉ dành cho issuer/SP hoặc RP cụ thể đã được đăng ký; không cho IdP B tùy ý thay redirect, audience hoặc khóa.
3. Role mapping được A quản lý; claim từ B là đầu vào, không phải quyết định cấp admin.
4. Grant được giới hạn bởi tenant, hợp đồng, dự án, môi trường và thời hạn.
5. Có kênh nhận sự kiện thay đổi nhân sự và kế hoạch reconciliation nếu đồng bộ thất bại.

### 7.3. Kiểm thử chấp nhận trước production

Kiểm thử cả ca **được phép** và **bị từ chối**:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
 Người B đúng issuer, có lời mời và grant hợp lệ | Xác thực và truy cập đúng scope |
 Người B đăng nhập thành công nhưng chưa được duyệt | Không được cấp quyền tài nguyên |
 Token từ issuer khác hoặc sai audience | Từ chối ngay ở lớp xác thực |
 Token hết hạn, chữ ký sai, response bị replay | Từ chối |
 User thuộc B yêu cầu dữ liệu tenant C | Từ chối ở backend |
 Hết hạn partner hoặc grant | Từ chối truy cập mới theo policy |
 Claim nhóm bất ngờ yêu cầu quyền admin | Không tự nâng quyền |
 SCIM/JIT lỗi hoặc cung cấp user chưa được duyệt | Không tạo quyền rộng mặc định |

## 8. Identity linking, JIT provisioning và SCIM

Ba quá trình này có thể phối hợp nhưng làm ba việc khác nhau:

| Quá trình | Mục đích | Rủi ro khi thiết kế sai |
|---|---|---|
 Identity linking | Liên kết external subject từ IdP với local principal tại A | Ghép nhầm người, chiếm tài khoản qua email |
 Just-in-time (JIT) provisioning | Tạo hoặc cập nhật local principal khi user đăng nhập | Bất kỳ ai có SSO được tự cấp quyền |
 SCIM provisioning | Đồng bộ tạo/cập nhật/vô hiệu hóa user và group | Đồng bộ trễ/lỗi, quyền ngoài SCIM còn tồn tại |

### 8.1. Liên kết danh tính an toàn

Với OIDC, một local user có thể lưu:

~~~json
{
  "local_principal_id": "external-7451",
  "partner_id": "partner-B",
  "federated_subject": {
    "issuer": "https://login.partner.example/tenant-b",
    "subject": "external-subject-7b3"
  },
  "status": "active",
  "membership": {
    "tenant_id": "tenant-B",
    "project_id": "P42",
    "role": "report_viewer",
    "expires_at": "2026-12-31T00:00:00Z"
  }
}
~~~

Nếu người dùng đổi email nhưng (issuer, subject) vẫn ổn định, IAM có thể cập nhật thuộc tính email qua nguồn đáng tin mà không tạo tài khoản mới. Nếu B đổi IdP dẫn tới issuer/subject mới, A cần **quy trình xác minh và chuyển ánh xạ có kiểm soát**, không tự gộp tài khoản theo email.

### 8.2. JIT provisioning có chặn quyền mặc định

JIT có lợi khi B có nhiều nhân viên ít đăng nhập. Tuy nhiên, quá trình tạo user khi đăng nhập **không nên tự động gán role tài nguyên nhạy cảm**. Hệ thống có thể chỉ tạo bản ghi ở trạng thái pending hoặc no-access, sau đó đợi lời mời hợp lệ, sponsor phê duyệt và chính sách tenant xác nhận.

Nếu ánh xạ group B sang role tại A, phải định nghĩa mapping có kiểm soát. Ví dụ group partner-B-auditors chỉ có thể nhận role auditor_readonly trong tenant B; không nhận quyền global_admin dù IdP gửi claim tương tự.

### 8.3. SCIM và deprovisioning

SCIM dùng để truyền thay đổi user/group giữa các hệ thống đã tích hợp. Ví dụ PATCH mô tả thao tác vô hiệu hóa local user:

~~~http
PATCH /scim/v2/Users/7451 HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "Replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Tài khoản phía A cần được liên kết đúng đối tác và nguồn provisioning. Phải xác thực client SCIM, giới hạn phạm vi các thao tác và xử lý lỗi có retry, cảnh báo, chống cấp lại nhầm khi partner đã offboarded.

**SCIM active=false không tự hủy phiên ứng dụng A hoặc làm vô hiệu ngay JWT đã cấp.** Đặc biệt, quyền chia sẻ trực tiếp ở một app downstream có thể vẫn còn nếu không được đồng bộ. IAM cần đối soát quyền thực tế sau khi deprovision.

## 9. Mover: thay đổi vai trò, hợp đồng và IdP

Một external user có thể chuyển đội, đổi dự án hoặc được trao nhiệm vụ mới. Ở cấp doanh nghiệp, B có thể thay đổi pháp nhân, sáp nhập, phân tách tenant, chuyển sang IdP khác hoặc gia hạn hợp đồng. Các sự kiện đó đều có thể thay đổi tính hợp lệ của federation và quyền truy cập.

| Sự kiện Mover | Điều cần đánh giá | Hành động phù hợp |
|---|---|---|
 Người B chuyển từ dự án P42 sang P51 | Grant P42 còn hợp lệ không? P51 thuộc tenant nào? | Thu hồi P42 không cần, xét duyệt P51 theo owner mới |
 B đổi nhân sự phụ trách hợp đồng | Ai có quyền yêu cầu và duyệt quyền? | Cập nhật contact/sponsor, rà soát grants |
 B thay tên miền email | Có đổi định danh ổn định không? | Cập nhật thuộc tính có xác minh; không tự đổi partner |
 B chuyển sang IdP mới | Issuer/khóa mới có được tin cậy không? | Phê duyệt trust mới, migrate subject mapping, gỡ trust cũ |
 B sáp nhập hoặc tách công ty | Quan hệ hợp đồng và tenant còn tương ứng không? | Xác minh tổ chức mới, duyệt lại scope, chuyển quyền có kiểm soát |
 Gia hạn nhưng thu hẹp phạm vi | Quyền ngoài hợp đồng mới là gì? | Xóa grant không còn được phép, cập nhật hạn đúng phần còn hiệu lực |
 Role từ đối tác thay đổi | Có làm tăng đặc quyền tại A không? | Ánh xạ role được A duyệt; cần approval nếu tăng quyền |

### 9.1. Quy trình Mover cấp cá nhân

1. Nhận tín hiệu thay đổi từ IdP/provisioning của B, sponsor A hoặc hệ thống quản lý hợp đồng.
2. So sánh quyền hiện tại với quyền cần cho nhiệm vụ mới; xét role, scope, tenant, dữ liệu và thời hạn.
3. Thu hồi quyền thừa đồng thời hoặc trước khi cấp quyền mới; yêu cầu phê duyệt lại khi tăng đặc quyền.
4. Cập nhật local membership, entitlement và các hệ thống downstream.
5. Kiểm tra API thực thi chính sách mới, ghi lại người duyệt và quyền trước/sau.

**Privilege creep** xuất hiện khi chỉ thêm quyền P51 mà không gỡ P42. Điều này dễ xảy ra nếu nhóm từ IdP B được đồng bộ nhưng IAM A không kiểm tra trạng thái hợp đồng và grant ở ứng dụng đích.

### 9.2. Thay đổi IdP và tránh chiếm đoạt danh tính

Khi B chuyển từ IdP-Old sang IdP-New:

1. **Xác minh yêu cầu** qua người đại diện B đã được đăng ký hoặc kênh độc lập đáng tin cậy.
2. **Đăng ký trust mới** gồm issuer/entityID, signing key, endpoint, client/ACS và chính sách phiên; review rủi ro theo tổ chức.
3. **Thử nghiệm cô lập** với tài khoản kiểm thử có scope tối thiểu, gồm cả các ca token sai nguồn và ánh xạ tenant sai.
4. **Liên kết chủ thể cũ–mới bằng bằng chứng được phê duyệt**; không auto-link bằng email hoặc display name.
5. **Đối soát grants và phiên**, rồi chuyển người dùng theo kế hoạch được giám sát.
6. **Vô hiệu hóa trust cũ và khóa không còn hợp lệ** theo cửa sổ chuyển đổi đã được duyệt; ghi audit đầy đủ.

Nếu hai IdP cùng hoạt động trong giai đoạn chuyển đổi, phải hạn chế thời gian và biết rõ bản ghi nào được phép xác thực qua mỗi nguồn. Một email giống nhau ở hai nguồn **không tự chứng minh** hai chủ thể là cùng một người.

## 10. Leaver: offboarding người dùng, đối tác và cấu hình trust

Leaver trong B2B federation có thể xuất phát từ nghỉ việc ở B, kết thúc dự án, hết hợp đồng, sponsor rút quyền, sự cố tài khoản hoặc tổ chức B chấm dứt hợp tác với A.

**Leaver cấp người dùng** và **Leaver cấp đối tác** có phạm vi khác nhau:

| Phạm vi | Việc cần thu hồi | Việc cần bảo toàn |
|---|---|---|
 Một user B rời dự án P42 | Membership/grant P42, phiên liên quan, chia sẻ trực tiếp | User B khác và các dự án user còn có quyền hợp lệ |
 Một user B nghỉ việc hoàn toàn | Local principal hoặc toàn bộ membership thuộc B, session/refresh token, grants ở các app | Bằng chứng và các principal B khác |
 Một ứng dụng tích hợp B kết thúc | OAuth client, API token, secret/certificate và service-account grants | Các tích hợp khác còn được phép |
 Hợp đồng A–B kết thúc | Mọi grants phát sinh từ hợp đồng, SSO/JIT/provisioning phù hợp, workload liên quan | Log, dữ liệu và nghĩa vụ lưu trữ theo chính sách |
 Toàn bộ B offboarded | Partner registry, IdP trust, user/workload access và quyền downstream | Audit evidence và dữ liệu cần lưu hợp pháp |

### 10.1. Vì sao khóa IdP B chưa đủ?

Khi IdP B vô hiệu hóa một người dùng, A có thể chỉ biết việc đó **ở lần xác thực kế tiếp**. Người dùng có thể đang có:

- Phiên của ứng dụng A với cookie riêng;
- Access token còn hiệu lực mà API vẫn chấp nhận;
- Refresh token hoặc credential còn hoạt động tại một dịch vụ;
- Local role, group hoặc share còn lưu ở một ứng dụng đích;
- API key/service account không gắn đúng với lifecycle người dùng;
- Phiên đặc quyền trên hạ tầng được khởi tạo trước khi khóa tài khoản.

Vì vậy, **đăng nhập mới bị từ chối không đồng nghĩa toàn bộ quyền đã được thu hồi**. Việc revocation phụ thuộc kiến trúc phiên, khả năng thu hồi token, TTL, kiểm tra trạng thái tại resource server và tích hợp downstream.

### 10.2. Thứ tự thu hồi tham khảo

1. **Xác nhận sự kiện và phạm vi:** sự kiện nghỉ việc, hợp đồng hết hạn, đình chỉ khẩn cấp hay một role cần gỡ? Ai phê duyệt, thời điểm hiệu lực?
2. **Chặn cấp truy cập mới:** đánh dấu principal, membership hoặc partner relationship là suspended/revoked; chặn JIT provisioning và grant mới trái trạng thái.
3. **Gỡ quyền ở nguồn và hệ thống đích:** group, role, project membership, chia sẻ dữ liệu, ACL, SaaS, cloud role và quyền ứng dụng.
4. **Thu hồi phiên/refresh token nếu nền tảng hỗ trợ:** kết thúc session phía A, xử lý các session broker/ứng dụng; với access token đã phát hành dùng TTL ngắn, introspection hoặc kiểm tra trạng thái phù hợp.
5. **Thu hồi danh tính workload:** API key, OAuth client, service account, certificate, webhook và các tích hợp còn phụ thuộc vào hợp đồng.
6. **Xử lý cấu hình federation/SCIM:** nếu quan hệ B đã hoàn toàn kết thúc, vô hiệu hóa trust đúng scope và bảo đảm nguồn provisioning cũ không tái tạo quyền.
7. **Đối soát quyền thực tế:** kiểm tra từng hệ thống đích, ghi lỗi, retry hoặc remediation và xác minh lại.
8. **Lưu bằng chứng và xử lý dữ liệu:** audit trail, hồ sơ phê duyệt, yêu cầu trả/xóa/lưu dữ liệu theo chính sách và hợp đồng.

### 10.3. Sơ đồ vòng đời liên kết

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Đề nghị mời hoặc tạo quan hệ
    Pending --> Active: Xác minh + trust + grant được duyệt
    Pending --> Rejected: Không đủ điều kiện
    Active --> Active: Mover / review / đổi role
    Active --> Suspended: Hết hạn tạm, rủi ro, cần xác minh
    Suspended --> Active: Được phê duyệt lại
    Active --> Revoked: Leaver / hết hợp đồng
    Suspended --> Revoked: Chấm dứt hoặc không tái duyệt
    Rejected --> [*]
    Revoked --> [*]
~~~

Khi thực thi, cần phân biệt **trạng thái local principal**, **trạng thái partner relationship** và **trạng thái phiên/token**. Một principal active nhưng relationship hết hạn vẫn phải bị từ chối quyền phụ thuộc quan hệ đó.

## 11. Phân quyền RBAC/ABAC và cô lập tenant

### 11.1. Xác thực từ IdP không phải quyền truy cập dữ liệu

**Role-Based Access Control (RBAC)** ánh xạ vai trò sang quyền. Ví dụ:

- partner_report_viewer: xem báo cáo được gán;
- partner_order_operator: đọc đơn và thay đổi trạng thái đơn trong dự án được duyệt;
- partner_auditor_readonly: xem hồ sơ kiểm toán phù hợp;
- partner_delegated_admin: quản lý thành viên B trong phạm vi B được A ủy quyền.

**Attribute-Based Access Control (ABAC)** xét thêm trạng thái partner, hợp đồng, tenant, dự án, mức nhạy cảm, môi trường, thời gian và ngữ cảnh xác thực. Trong SaaS nhiều tenant, role chung không đủ để phân quyền đối tượng.

Ví dụ: user B có vai trò report_viewer. Nếu API chỉ kiểm tra role rồi chấp nhận resource_id do caller gửi, user B có thể thử ID báo cáo thuộc tenant C. Backend phải kiểm tra **resource.tenant_id thuộc đúng grant/membership được duyệt**, bất kể giao diện có ẩn tài nguyên C hay không.

### 11.2. Chính sách truy cập minh họa

~~~text
authorize(identity, request, context):
    if not context.authentication_valid: DENY
    if identity.status != "active": DENY

    partner = load_partner(identity.partner_id)
    if partner.status != "active": DENY

    membership = load_membership(identity, request.tenant_id)
    if membership is missing: DENY
    if membership.status != "active": DENY
    if now >= membership.expires_at: DENY

    relationship = load_relationship(partner.id, request.project_id)
    if relationship.status != "active": DENY
    if now >= relationship.expires_at: DENY

    grant = load_grant(identity, request.resource_id)
    if grant is missing: DENY
    if request.action not in grant.allowed_actions: DENY
    if request.resource.tenant_id != membership.tenant_id: DENY
    if not satisfies_risk_and_data_policy(identity, request, context): DENY

    ALLOW
~~~

Đây là mã giả minh họa, không phải chuẩn ngôn ngữ của một policy engine cụ thể. Ứng dụng phải kiểm tra quyền ở điểm thực thi (API/backend/resource server) chứ không dựa vào nút hoặc menu đang hiển thị.

### 11.3. Claim group và quyền delegated admin

Khi B gửi claim nhóm từ IdP, A cần một mapping rõ ràng:

| Claim nhóm B | Mapping được A phê duyệt | Scope |
|---|---|---|
 B-Report-Read | partner_report_viewer | Chỉ tenant B và dự án được gán |
 B-Orders-Operate | partner_order_operator | Chỉ đơn hàng thuộc quan hệ A–B |
 B-Partner-Admins | partner_delegated_admin | Quản trị user B trong trần quyền đã duyệt |
 B-Global-Admins | Không tự cấp quyền | Yêu cầu quy trình đặc biệt nếu có nhu cầu |

Một đối tác không được tự nâng quyền truy cập tài nguyên A bằng việc đổi tên group trong IdP. Nếu A cho phép **delegated administration**, mọi tác vụ phải nằm trong scope ủy quyền, có audit và không vượt được giới hạn quyền do A đặt.

### 11.4. Khi một người thuộc nhiều đối tác

Một người có thể cộng tác cho B và C hoặc dùng nhiều federation identities. Không nên hợp nhất entitlement của các partner vào một quyền toàn cục. Hệ thống phải chọn rõ ngữ cảnh tenant/partner trong request, kiểm tra membership tương ứng và ngăn trộn dữ liệu. Trường hợp account linking cần được thẩm định, nhất là khi người dùng đổi đối tác hoặc doanh nghiệp sáp nhập.

## 12. Chính sách MFA, phiên và kiểm soát truy cập thích ứng

B2B federation giúp A tận dụng xác thực của B, nhưng mức bảo đảm của từng phiên không luôn như nhau. Một đăng nhập với mật khẩu đơn có thể không đáp ứng chính sách truy cập dữ liệu tài chính hoặc quyền production.

Những câu hỏi A cần làm rõ với B:

- B có bật MFA cho nhóm được liên kết không, phương thức nào được cho phép?
- Khi A cần xác thực mạnh hơn cho thao tác nhạy cảm, B có hỗ trợ **step-up authentication** hoặc cung cấp bằng chứng mức xác thực thích hợp không?
- Các claim **acr**, **amr** hoặc SAML AuthnContext có ý nghĩa cụ thể thế nào trong cấu hình giữa hai bên?
- Ai chịu trách nhiệm thiết bị, phát hiện bất thường và khóa user khi mất tài khoản?
- Khi nhân viên B rời tổ chức, A được thông báo qua kênh nào và với độ trễ nào?

Không nên xem một claim MFA bất kỳ là đáng tin nếu không được phát hành bởi IdP đã xác minh và có hợp đồng/cấu hình xác định cách diễn giải. Có thể kiểm soát thêm theo loại dữ liệu, thiết bị, địa điểm, mức độ rủi ro và quyền đặc biệt. **Zero Trust IAM** nhấn mạnh đánh giá quyền theo bối cảnh truy cập, thay vì mặc nhiên tin cậy một kết nối VPN hay lần đăng nhập trước đó.

### Thời hạn phiên và logout

Các thời hạn sau có thể khác nhau:

| Đối tượng | Ai kiểm soát chủ yếu? | Cần làm gì khi Leaver? |
|---|---|---|
 Phiên tại IdP B | B | Disable user, kết thúc phiên nếu có hỗ trợ |
 Phiên ứng dụng A | A | Invalidate session/cookie, đánh giá lại trạng thái principal |
 OIDC access token của API | Authorization server và resource server liên quan | TTL phù hợp, introspection/revocation hoặc kiểm tra trạng thái khi triển khai |
 Refresh token | Bên phát hành token và client giữ token | Thu hồi hoặc xóa khi có hỗ trợ |
 Grant tại app downstream | Chủ ứng dụng A | Gỡ và đối soát actual entitlement |

SAML Single Logout và OIDC logout có các khả năng và giới hạn theo sản phẩm. **Không mặc định single logout hoạt động xuyên mọi ứng dụng** nếu chưa thiết kế và kiểm thử đầy đủ. Một hệ thống có thể chặn login mới nhưng vẫn cần đóng phiên nội bộ khi user bị thu hồi.

## 13. Audit, access review và phát hiện quyền tồn dư

### 13.1. Dấu vết cần giữ

Chỉ ghi lần login thành công là chưa đủ. Một triển khai B2B federation cần có audit của:

| Nhóm sự kiện | Trường hữu ích |
|---|---|
 Tạo/duyệt partner trust | Partner ID, issuer/entityID, resource owner, thời điểm, người duyệt |
 Thay signing key/metadata | Cấu hình trước–sau, nguồn yêu cầu, thời điểm cutover |
 Đăng nhập federation | Partner, issuer, local principal, kết quả, correlation ID |
 JIT/SCIM provisioning | Nguồn, bản ghi được tạo/đổi/tắt, trạng thái, lỗi |
 Cấp/thay/thu hồi entitlement | Tenant, project, role, lý do, người yêu cầu/người duyệt |
 Access request/API call | Subject/client, tài nguyên, action, allow/deny |
 Access review | Reviewer, kết quả giữ/gỡ, ngày và bằng chứng |
 Leaver/offboarding | Nguồn sự kiện, hệ thống đích, thời gian thu hồi, lỗi còn mở |

Log cần được bảo vệ tính toàn vẹn, giới hạn người xem và áp dụng thời hạn lưu giữ theo chính sách. **Không ghi password, private key, access token hoặc dữ liệu cá nhân vượt mục đích audit.** Dùng correlation ID để lần theo yêu cầu từ hệ thống IAM/SSO đến resource server.

### 13.2. Access review

Reviewer phía A cần trả lời:

1. Partner B và hợp đồng có còn active? Sponsor còn hợp lệ?
2. Những user nào vẫn thuộc B, đang làm đúng dự án được giao?
3. Từng role và tenant/project scope có còn phù hợp công việc?
4. Có user không đăng nhập lâu ngày, tài khoản không có owner hoặc grant hết hạn?
5. Có đặc quyền admin hoặc delegated admin vượt phạm vi?
6. Các ứng dụng downstream có cùng trạng thái với IAM hay không?
7. Có workload/service account nào phục vụ B nhưng không được quản lý cùng relationship?

Tần suất review phụ thuộc độ nhạy của tài nguyên và mức rủi ro, không có một chu kỳ chung cho mọi tổ chức. Ngoài review định kỳ, Mover, sự cố và thay đổi hợp đồng phải kích hoạt kiểm tra theo chính sách.

### 13.3. Reconciliation giữa desired và actual state

**Desired state** là danh sách quyền đáng lẽ còn hiệu lực theo hồ sơ IAM và hợp đồng; **actual state** là quyền thực tế trong ứng dụng, API, ACL, nhóm và phiên. Có thể xuất hiện chênh lệch do lỗi đồng bộ, quyền được cấp thủ công hoặc một hệ thống không nhận sự kiện Leaver.

~~~text
for partner in partner_registry:
    expected = compute_approved_access(
        partner.status,
        valid_relationships,
        approved_grants
    )
    actual = collect_access_from_relevant_systems(partner.id)
    differences = compare(expected, actual)
    if differences:
        alert_responsible_owner(differences)
        remediate_and_verify(differences)
~~~

Đây là mã giả vận hành. Với hệ thống không cung cấp API truy xuất quyền, cần kiểm tra thủ công hoặc cách kiểm chứng phù hợp và ghi nhận giới hạn của quá trình đối soát.

### 13.4. Chỉ số vận hành

- Thời gian từ sự kiện Leaver đến xác nhận revoke trên các hệ thống đích;
- Số principal thuộc partner hết hợp đồng nhưng còn active;
- Số người dùng không có sponsor, hết hạn mà vẫn có grant;
- Tỷ lệ access review hoàn thành đúng hạn và tỷ lệ quyền bị gỡ sau review;
- Số lỗi SCIM/JIT/provisioning chưa xử lý và số sai lệch IAM–ứng dụng;
- Số lần đăng nhập thất bại vì trust/issuer/audience hoặc key rotation;
- Số external user có quyền đặc biệt và số phiên JIT/PAM được cấp.

Các ngưỡng, SLA và lịch review cần được xác định theo rủi ro, trách nhiệm hợp đồng và khả năng kiểm chứng thực tế.

## 14. Threat model và những lỗi phổ biến

| Rủi ro / lỗi | Cơ chế dẫn đến lỗi | Biện pháp |
|---|---|---|
 Tin bất kỳ issuer được khai trong request | Chấp nhận token do nguồn không được ủy thác phát hành | Pin issuer/entityID theo partner và ứng dụng |
 Không kiểm tra audience | Token dành cho ứng dụng khác bị dùng lại | Validate audience/client binding |
 Không xác minh chữ ký token/assertion | Dữ liệu danh tính có thể bị giả mạo | Trust key đúng nguồn, kiểm tra chữ ký bằng thư viện đáng tin |
 Thiếu state/nonce/flow binding | Login CSRF, callback giả mạo, nhầm luồng | Sử dụng state, nonce, PKCE theo giao thức/luồng |
 SAML assertion bị replay | Assertion cũ bị tái dùng | Kiểm tra thời gian, Recipient/InResponseTo và cache replay |
 Chấp nhận nhóm admin từ B không kiểm soát | B có thể nâng quyền tại A | Mapping do A duyệt, trần quyền và scope |
 Tự ghép account bằng email | Có thể chiếm local account hoặc mang quyền cũ sai người | Subject ổn định và quy trình account linking |
 Bỏ kiểm tra tenant trong API | Truy cập dữ liệu đối tác khác | Authorization theo object/tenant ở backend |
 IdP B disable nhưng session A còn | Quyền thực tế tồn dư | Session revoke, TTL và kiểm tra trạng thái tại ứng dụng |
 SCIM lỗi nhưng không giám sát | Quyền desired khác actual | Retry, cảnh báo và reconciliation |
 Đổi issuer/key chỉ theo email yêu cầu | Kẻ tấn công chiếm quan hệ tin cậy | Xác minh ngoài băng, phê duyệt thay đổi |
 Hết hợp đồng nhưng trust vẫn active | Người dùng hoặc JIT có thể tiếp tục vào A | Partner state check, offboarding và audit |

Mục tiêu không phải phụ thuộc vào một lớp duy nhất. Khi có sự cố federation, IAM cần xác định liệu vấn đề nằm ở **trust configuration, authentication, provisioning, authorization hay session**, rồi xử lý đúng lớp.

## 15. Kịch bản thực tế: hai đối tác B và C dùng chung cổng của A

Giả sử A cung cấp một cổng vận hành B2B đa tenant. B phụ trách phân phối tại miền Nam, C phụ trách miền Bắc. Hai đối tác có IdP riêng, nhưng dùng cùng ứng dụng A. A có registry như sau:

| Thông tin | Đối tác B | Đối tác C |
|---|---|---|
| Partner ID | partner-B | partner-C |
| IdP | OIDC issuer B | SAML entityID C |
| Tenant | tenant-B | tenant-C |
| Resource scope | Các dự án giao cho B | Các dự án giao cho C |
| Sponsor | Quản lý kênh B phía A | Quản lý kênh C phía A |
| Lifecycle | SCIM + access review | Invitation + review định kỳ |

### Ngày 1 — Đưa B vào hoạt động

A xác minh hợp đồng, đầu mối B và issuer OIDC B. Sau khi cấu hình trust, A mời user U của B, liên kết (issuer B, subject U) với local principal, cấp role report_viewer cho dự án P42 thuộc tenant-B và thời hạn hợp lệ.

User U truy cập cổng. A gửi user đến đúng IdP B, nhận authorization code, kiểm tra state/PKCE, đổi code lấy ID token, xác minh issuer/audience/signature/expiry/nonce và liên kết danh tính. Policy cho phép U đọc báo cáo thuộc P42.

### Ngày 10 — Thử truy cập sai tenant

U thay URL để yêu cầu báo cáo thuộc tenant-C. Dù SSO thành công và role viewer vẫn active, **backend A từ chối** vì đối tượng không thuộc membership/scope của U. Log ghi principal, partner, tài nguyên, hành động và kết quả deny.

### Ngày 30 — U chuyển dự án

B thông báo U không còn phụ trách P42 mà chuyển sang P51. A nhận thay đổi, sponsor xét duyệt P51 và IAM gỡ P42. Đối soát với ứng dụng xác nhận U không còn đọc được báo cáo P42.

### Ngày 45 — B thay IdP

B đề xuất chuyển sang issuer mới. A xác minh yêu cầu qua đầu mối tin cậy đã đăng ký, cấu hình IdP mới trong môi trường kiểm thử, liên kết subject U theo quy trình được duyệt và kiểm tra lại quyền. Sau cutover, A loại trust cũ đúng thời hạn.

### Ngày 90 — Hợp đồng B kết thúc

A đánh dấu relationship B hết hiệu lực, chặn phiên mới và JIT provisioning; thu hồi grant, session có thể thu hồi, quyền downstream và OAuth clients phục vụ B. A đối soát trạng thái ở các ứng dụng. Hợp đồng C vẫn còn hiệu lực, vì vậy người dùng C tiếp tục đăng nhập SAML và hoạt động bình thường.

**Bài học:** Việc vô hiệu hóa trust B phải giới hạn đúng partner và quan hệ liên quan. Thiết kế tốt không để việc offboard B vô tình chặn C hoặc để token cũ của B tiếp tục được phép truy cập tài nguyên.

## 16. Chẩn đoán sự cố B2B federation

Khi user nói “đăng nhập B2B không được”, cần xác định lỗi ở giai đoạn nào để tìm đúng owner và đúng hệ thống.

| Dấu hiệu | Nhóm nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
 Không chuyển tới đúng IdP | Sai partner discovery, invitation, issuer mapping | Kiểm tra partner context và trust registry |
 Redirect loop | Cookie/session, callback, clock skew, state hoặc cấu hình nhiều IdP | Xem correlation ID và luồng request/response |
 OIDC invalid issuer/audience | Token đến từ issuer/client khác | Kiểm tra trust config, client_id, token validation |
 OIDC nonce/state mismatch | Session không khớp hoặc callback bị giả mạo | Kiểm tra flow binding và cách lưu session |
 SAML signature invalid | Certificate không khớp hoặc metadata/rotation lỗi | Kiểm tra khóa đang được chấp nhận và assertion được ký |
 SAML Recipient/InResponseTo invalid | Sai ACS hoặc response không thuộc request | Kiểm tra SP config và replay protection |
 Đăng nhập thành công nhưng “Access denied” | Chưa được provision, thiếu membership/grant, hết hợp đồng | Kiểm tra local principal, partner state và policy decision |
 Đúng vai trò nhưng không thấy báo cáo | Sai tenant/project scope hoặc dữ liệu đã chuyển | Kiểm tra resource ownership và entitlement |
 User đã rời B nhưng vẫn truy cập được | Session A, token hoặc quyền app chưa thu hồi | Kiểm tra Leaver pipeline và actual state |
 User bị tạo hai lần | Identifier mapping không ổn định, đổi IdP/email | Xác minh issuer/subject và quy trình linking |
 SCIM không cập nhật group | Lỗi credential, mapping, retry hoặc app đích | Kiểm tra provisioning log và reconciliation |

### Nguyên tắc điều tra

1. **Không vô hiệu hóa kiểm tra chữ ký/audience để “sửa nhanh”** vì như vậy phá ranh giới tin cậy.
2. Kiểm tra trạng thái quan hệ B và grant trước khi thay đổi cấu hình xác thực.
3. So sánh request ID, issuer, client ID, ACS, correlation ID và thời gian ở hai bên nhưng tránh đưa token/assertion nhạy cảm vào ticket công khai.
4. Nếu một issuer hoặc key thay đổi ngoài quy trình, xử lý như một sự kiện cần xác minh danh tính nguồn.
5. Khi nghi ngờ xâm nhập, có thể tạm đình chỉ quyền theo chính sách, thu hồi phiên và phối hợp với chủ tài nguyên/đầu mối B.

## 17. Checklist thiết kế và triển khai

### Quan hệ và danh tính

- [ ] Partner được xác minh, có partner_id, sponsor, hợp đồng, phạm vi, trạng thái và ngày hết hạn.
- [ ] Có ánh xạ issuer/entityID đến đúng partner, không suy từ email hoặc tên hiển thị.
- [ ] Local principal được liên kết với external subject ổn định; account linking có quy trình phê duyệt.
- [ ] Có nguồn sự kiện Joiner–Mover–Leaver, đầu mối chịu trách nhiệm và lịch review.

### Federation và SSO

- [ ] OIDC/SAML trust được xác minh trước khi mở cho production.
- [ ] Có kiểm tra chữ ký, issuer, audience, thời gian, recipient/redirect và các điều kiện của luồng.
- [ ] Có state/nonce/PKCE khi phù hợp cho OIDC; anti-replay, InResponseTo và SubjectConfirmation cho SAML.
- [ ] Có quy trình xoay key/certificate, đổi IdP, metadata và xử lý trust bị thu hồi.
- [ ] MFA, step-up, quản lý phiên và yêu cầu thiết bị/rủi ro được xác định theo dữ liệu cần bảo vệ.

### Phân quyền và vòng đời

- [ ] SSO thành công không tự gán quyền dữ liệu; grant cần sponsor/resource owner và scope rõ.
- [ ] Role mapping từ IdP đối tác do A kiểm soát, không cho phép tự nâng admin.
- [ ] RBAC/ABAC kiểm tra tenant, object, project, contract và expiry ở backend.
- [ ] JIT/SCIM có hạn quyền, chống tạo lại người dùng đã bị revoke và xử lý lỗi đồng bộ.
- [ ] Mover thu hồi quyền cũ, cấp quyền mới có phê duyệt và kiểm chứng.
- [ ] Leaver xử lý principal, session, token, downstream grants và workload identity liên quan.

### Vận hành và kiểm chứng

- [ ] Có audit các sự kiện login, provisioning, thay trust, role, review và offboarding.
- [ ] Có reconciliation giữa quyền IAM dự kiến và quyền thực tế trong ứng dụng đích.
- [ ] Có ca kiểm thử cross-tenant, token/assertion sai, partner hết hạn và revoke session.
- [ ] Có chỉ số về quyền tồn dư, lỗi đồng bộ và thời gian thu hồi theo rủi ro.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Nhân viên B đăng nhập thành công qua OIDC. Có được tự động xem tất cả báo cáo của B không?

**Trả lời:** Không. Ứng dụng A phải liên kết đúng principal và kiểm tra grant, membership, hợp đồng, project/tenant, hành động và điều kiện còn hiệu lực trước khi cấp quyền.

**Câu 2.** Vì sao cùng một email không đủ để ghép danh tính từ hai IdP?

**Trả lời:** Email có thể đổi hoặc tái sử dụng, không chứng minh hai issuer xác thực cùng một con người. Cần quy trình linking có xác minh và định danh ổn định theo nguồn, chẳng hạn cặp (iss, sub) trong OIDC.

**Câu 3.** SCIM đã chuyển user sang inactive nhưng user vẫn dùng được ứng dụng A. Nguyên nhân có thể là gì?

**Trả lời:** Phiên ứng dụng còn sống, access token chưa hết hạn, resource server không kiểm tra trạng thái local, hoặc quyền ACL nằm ngoài SCIM chưa bị gỡ. Cần kiểm tra và đối soát từng lớp.

**Câu 4.** Token OIDC có chữ ký đúng nhưng trường audience là ứng dụng khác. Ứng dụng A nên làm gì?

**Trả lời:** Từ chối token vì không được phát hành cho RP/ứng dụng A; kiểm tra đúng audience là điều kiện cốt lõi của token validation.

**Câu 5.** B gửi claim group với tên Global-Admin. A nên xử lý thế nào?

**Trả lời:** Không tự cấp quyền admin. A áp dụng mapping và phê duyệt do mình kiểm soát, giới hạn tenant/project/expiry và chỉ trao đặc quyền khi có căn cứ rõ.

**Câu 6.** Sau khi B đổi IdP, có nên giữ issuer cũ và mới cùng được phép vĩnh viễn để tránh gián đoạn?

**Trả lời:** Không. Cần cửa sổ chuyển đổi được phê duyệt, ánh xạ danh tính có kiểm soát, kiểm thử, theo dõi và thu hồi trust cũ khi hết nhu cầu.

**Câu 7.** Một người B có role viewer nhưng yêu cầu báo cáo tenant C. Điều gì quyết định việc từ chối?

**Trả lời:** Backend phải kiểm tra object ownership/tenant và membership/grant tương ứng. Role viewer chung không đủ để cho phép truy cập một object ngoài phạm vi.

**Câu 8.** Khi chấm dứt toàn bộ quan hệ A–B, tại sao không chỉ xóa cấu hình SSO?

**Trả lời:** Local sessions, grants, SCIM records, API clients và quyền trực tiếp ở ứng dụng đích có thể còn. Cần offboarding có kiểm chứng ở cả cấp partner, người dùng, workload và resource server.

## Kết luận

**B2B federation** cho phép tổ chức khai thác **IdP và SSO** của đối tác để xác thực, đồng thời giữ quyền kiểm soát **local principal, RBAC/ABAC, tenant isolation, hợp đồng và resource authorization** ở bên sở hữu tài nguyên. Trong quản lý vòng đời danh tính **Joiner–Mover–Leaver**, federation cần phối hợp với **SCIM hoặc provisioning, access review, audit, quản lý phiên và deprovisioning** để tránh quyền còn tồn tại sau khi người dùng đổi vai trò, rời doanh nghiệp hoặc quan hệ hợp tác kết thúc. Một triển khai an toàn luôn kiểm tra đúng nguồn xác thực, đúng người, đúng phạm vi tài nguyên và đúng thời điểm.
