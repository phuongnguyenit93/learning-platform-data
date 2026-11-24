# OIDC federation trong quản lý vòng đời danh tính IAM

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **OpenID Connect (OIDC) federation** là gì, nó khác đăng nhập cục bộ, OAuth 2.0 authorization, SSO và account provisioning như thế nào.
- Nhận diện các vai trò **OpenID Provider (OP/IdP)**, **Relying Party (RP/OIDC client)**, người dùng, ứng dụng và tài nguyên API; mô tả quan hệ tin cậy giữa chúng.
- Trình bày luồng **Authorization Code Flow kết hợp PKCE**, các bước khám phá cấu hình, chuyển hướng đăng nhập, trao đổi mã và kiểm tra ID token.
- Phân biệt **ID token, access token, refresh token, phiên RP và phiên IdP**; xác định điều gì phải được kiểm tra trước khi ứng dụng tin vào danh tính được liên kết.
- Thiết kế an toàn việc **ánh xạ issuer + subject, account linking, claim, group/role, RBAC/ABAC** khi sử dụng một hoặc nhiều IdP.
- Liên hệ OIDC federation với **Joiner–Mover–Leaver (JML), SCIM, IdP, SSO, xác minh danh tính, service/workload identity, đối soát và kiểm toán**, tránh duy trì quyền truy cập tồn dư.
- Nhận biết các rủi ro phổ biến: sai issuer/audience, mã đăng nhập bị đánh cắp, login CSRF, nhầm tài khoản, token replay, logout không toàn diện và tin tưởng claim không đúng nguồn.

## 1. OIDC federation là gì?

**OIDC federation** là cách một ứng dụng hoặc hệ thống **dựa vào một nhà cung cấp định danh được tin cậy** để xác thực người dùng thông qua **OpenID Connect**, thay vì tự quản lý toàn bộ quy trình đăng nhập và thông tin xác thực. Kết quả xác thực có thể được chuyển đến ứng dụng trong một **ID token**, cùng các thông tin cần thiết để thiết lập phiên ứng dụng.

Trong một môi trường doanh nghiệp, nhân viên có thể đăng nhập vào cổng báo cáo, công cụ phát triển và ứng dụng SaaS qua cùng một **Identity Provider (IdP)**. Ứng dụng chỉ cần biết nó có quan hệ tin cậy hợp lệ với IdP nào, cách xác minh kết quả và cách ánh xạ chủ thể đã đăng nhập với account cùng quyền của ứng dụng.

Từ **federation** nhấn mạnh **quan hệ tin cậy vượt qua ranh giới quản lý danh tính**: một bên xác thực và đưa ra thông tin về người dùng, bên còn lại kiểm tra thông tin đó và quyết định có thiết lập phiên hay cho phép truy cập hay không. Quan hệ này có thể tồn tại giữa doanh nghiệp với ứng dụng SaaS, giữa hai tổ chức hoặc giữa một ứng dụng với nhiều IdP.

**OIDC là một lớp xác thực danh tính xây trên các cơ chế của OAuth 2.0.** OAuth 2.0 tập trung vào việc ủy quyền truy cập tài nguyên; OIDC bổ sung các thành phần như **ID token** để RP có thể xác định kết quả xác thực của người dùng.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, OIDC federation kết nối quá trình **xác minh và kích hoạt danh tính ở Joiner**, thay đổi thuộc tính/quyền ở **Mover** và chặn hoặc thu hồi truy cập ở **Leaver**. Tuy nhiên, OIDC **không tự quản lý vòng đời tài khoản ở ứng dụng đích**; các cơ chế như **SCIM/API, RBAC/ABAC, access review và reconciliation** vẫn cần được thiết kế riêng.

### 1.1. Một ví dụ ngắn

Công ty dùng IdP doanh nghiệp, nhân viên truy cập ứng dụng quản lý hóa đơn:

1. Ứng dụng phát hiện chưa có phiên đăng nhập hợp lệ.
2. Ứng dụng chuyển trình duyệt tới IdP qua luồng OIDC phù hợp.
3. IdP xác thực nhân viên theo chính sách, có thể yêu cầu MFA.
4. Ứng dụng nhận authorization code qua redirect URI đã đăng ký, đổi code lấy các token qua kênh được bảo vệ.
5. Ứng dụng xác minh **ID token**, xác định đúng chủ thể và tạo phiên của riêng nó.
6. Khi người dùng mở hóa đơn, ứng dụng kiểm tra **role, thuộc tính và quyền truy cập thực tế**.

**Bước 5 chỉ xác nhận một danh tính đã đăng nhập đáng tin theo hợp đồng liên kết.** Nó không chứng minh người dùng có quyền đọc mọi hóa đơn ở bước 6.

## 2. Phân biệt federation, SSO, authentication và provisioning

| Khái niệm | Câu hỏi chính | Liên quan tới OIDC |
| --- | --- | --- |
| **Authentication** | Người dùng có chứng minh được mình kiểm soát phương thức xác thực đã đăng ký không? | IdP thực hiện và công bố kết quả xác thực |
| **Federation** | Một ứng dụng có thể tin kết quả xác thực từ miền danh tính khác bằng cách nào? | RP kiểm chứng token/thông tin từ OP đã được thiết lập tin cậy |
| **Single Sign-On (SSO)** | Một lần đăng nhập ở IdP có giúp người dùng vào nhiều ứng dụng không? | Có thể đạt SSO khi các RP cùng dựa vào phiên IdP |
| **OAuth 2.0 authorization** | Một client được quyền gọi API với phạm vi nào? | Access token và scope phục vụ authorization tới resource server |
| **OIDC authentication** | RP biết chủ thể được xác thực là ai qua IdP bằng cách nào? | ID token cùng yêu cầu và kiểm chứng theo OIDC |
| **Identity proofing** | Danh tính trong hồ sơ có được xác minh đủ tin cậy không? | Là bước thiết lập danh tính trước hoặc ngoài lúc đăng nhập |
| **Provisioning** | Tài khoản/nhóm/quyền được tạo, đổi, vô hiệu hóa tại ứng dụng thế nào? | SCIM/API hoặc quy trình khác; không do OIDC tự đảm nhận |
| **Authorization** | Sau khi xác thực, người dùng được thao tác với tài nguyên gì? | RBAC/ABAC và policy ở ứng dụng/API |
| **Reconciliation** | Account và quyền thực tế có khớp trạng thái được phép không? | Kiểm tra độc lập với việc người dùng đã đăng nhập thành công |

**OIDC federation có thể tạo trải nghiệm SSO, nhưng hai khái niệm không hoàn toàn đồng nhất.** Một ứng dụng có thể dùng OIDC với một IdP riêng mà không có SSO liên ứng dụng; một môi trường SSO khác có thể dùng giao thức federation không phải OIDC.

**OIDC authentication không đồng nghĩa provisioning.** Một ứng dụng có thể tạo tài khoản khi đăng nhập đầu tiên (*Just-in-Time provisioning*) nếu có cấu hình, nhưng khả năng này là **hành vi của ứng dụng**, không phải nghĩa vụ tự động của mọi triển khai OIDC.

## 3. Các vai trò và ranh giới tin cậy

| Vai trò | Trách nhiệm | Thông tin không nên tự suy diễn |
| --- | --- | --- |
| **End User / Subject** | Người cần đăng nhập | Có tài khoản IdP không tự chứng minh còn quan hệ làm việc |
| **OpenID Provider (OP/IdP)** | Xác thực và phát hành ID token cho RP | Không nhất thiết là nguồn có thẩm quyền về mọi quyền nghiệp vụ |
| **Relying Party (RP/OIDC client)** | Yêu cầu đăng nhập, kiểm tra kết quả, tạo phiên | Không được tin token chỉ vì trông giống JWT |
| **Authorization Server** | Cung cấp authorization endpoint và token endpoint | Không phải mọi access token đều là JWT |
| **Resource Server / API** | Thực thi truy cập dựa trên access token và policy | Không nên chấp nhận ID token như access token |
| **HRIS / nguồn hợp đồng** | Quản lý dữ liệu nhân sự, trạng thái, ngày hiệu lực | Không tự chứng minh phiên SSO hiện tại còn hợp lệ |
| **IGA/Identity Registry** | Liên kết identity, quản trị vòng đời và phê duyệt | Không thể giả định mọi ứng dụng đã thu hồi account |
| **Ứng dụng đích** | Account, phiên, role và entitlement tại tài nguyên của nó | Group ở IdP không tự đồng nghĩa quyền hiệu lực tại đây |

**OP** và **RP** là hai bên của quan hệ OIDC. Một doanh nghiệp có thể vận hành OP nội bộ, dùng dịch vụ IdP được quản lý, hoặc tin cậy IdP của đối tác theo hợp đồng kỹ thuật và chính sách.

### 3.1. Ranh giới cần bảo vệ

- **Trình duyệt ↔ RP:** phiên ứng dụng, cookie, redirect, chống CSRF và session fixation.
- **RP ↔ OP:** client registration, issuer, metadata, token endpoint, client authentication và trust configuration.
- **OP ↔ Người dùng:** phương thức xác thực, MFA, recovery và bảo vệ phiên IdP.
- **RP ↔ API:** access token đúng audience/scope, authorization thực tế và kiểm soát tài nguyên.
- **HRIS/IGA ↔ OP/ứng dụng:** dữ liệu danh tính, lifecycle state và provisioning; đây không phải mặc nhiên là đường trao đổi OIDC.

Không bên nào nên vượt quá phạm vi tin cậy: OP có thể khẳng định **người dùng được xác thực**, nhưng chỉ ứng dụng/tài nguyên mới quyết định **hành động nào được phép** dựa trên chính sách hiện hành.

## 4. Kiến trúc OIDC federation cho doanh nghiệp

~~~mermaid
flowchart LR
    HR["HRIS / nguồn hợp đồng"] --> IGA["Identity registry / IGA"]
    IGA -->|"Provision / cập nhật / revoke"| IdP["OpenID Provider / IdP"]
    IGA -->|"SCIM/API và entitlement"| App["Relying Party / SaaS"]
    User["Người dùng"] -->|"Mở ứng dụng"| App
    App -->|"Authorization request"| IdP
    IdP -->|"Xác thực, MFA"| User
    IdP -->|"Code / token response qua luồng tin cậy"| App
    App -->|"Access token đúng scope"| API["Resource Server / API"]
    IGA -->|"RBAC/ABAC policy, approval"| App
    App --> OBS["Audit và observed access"]
    IdP --> OBS
    API --> OBS
    OBS --> REC["Reconciliation"]
    REC --> IGA
~~~

Sơ đồ minh họa những **đường logic**; authorization code có thể qua trình duyệt, còn việc đổi code ở token endpoint thường thực hiện trên kênh back-channel của client phù hợp. Token và user data phải được bảo vệ theo từng môi trường triển khai.

**Hai đường độc lập quan trọng:**

1. **Federation/authentication path:** RP ↔ OP xác định ai đang đăng nhập theo giao thức.
2. **Lifecycle/provisioning path:** HRIS/IGA ↔ IdP/ứng dụng kiểm soát ai đáng lẽ có account và quyền nào.

Nếu chỉ xây federation path mà bỏ lifecycle path, người dùng đã nghỉ vẫn có thể giữ local account hoặc session tại ứng dụng.

## 5. Thiết lập quan hệ tin cậy OIDC

Trước khi một RP cho phép đăng nhập, cần cấu hình và quản trị quan hệ với OP.

### 5.1. Các thành phần cấu hình

| Cấu hình | Ý nghĩa | Kiểm soát |
| --- | --- | --- |
| **Issuer URL (iss)** | Định danh chính xác của OP | So khớp issuer trong metadata và ID token theo quy tắc OIDC |
| **Client ID** | Định danh RP tại OP | Đăng ký đúng client/tenant |
| **Client secret hoặc phương thức xác thực client** | Cách confidential client xác thực với token endpoint | Bảo vệ secret/khóa; public client không dùng secret như bằng chứng bí mật |
| **Redirect URI** | Nơi RP nhận kết quả authorization | Đăng ký và so khớp chặt; không dùng redirect mở |
| **Authorization endpoint** | Điểm bắt đầu yêu cầu authorization | Lấy từ cấu hình tin cậy |
| **Token endpoint** | Điểm đổi authorization code lấy token | Kênh TLS, client authentication nếu cần |
| **JWKS URI** | Nơi lấy khóa công khai xác minh chữ ký | Ràng buộc với OP tin cậy, quản lý rotation |
| **Scopes** | Những phạm vi dữ liệu/quyền yêu cầu | Dùng openid để kích hoạt OIDC; giảm yêu cầu claim không cần |
| **Claim mapping** | Cách ánh xạ subject/email/group/attribute | Phân biệt định danh với dữ liệu hiển thị và quyền |
| **Logout / session policy** | Cách kết thúc phiên và chặn truy cập | Không giả định logout liên ứng dụng tự hoạt động |

Một RP có thể dùng **OIDC Discovery** từ tài liệu metadata của OP, thường tại đường dẫn chuẩn dựa trên **.well-known/openid-configuration**, để lấy endpoint, thuật toán hỗ trợ và các capability. Không nên lấy endpoint hoặc JWKS từ tham số tùy ý do người dùng chưa tin cậy cung cấp.

### 5.2. Những bước vận hành quan hệ tin cậy

1. Chọn OP được tổ chức **chấp thuận** và xác định phạm vi người dùng/tenant được phép.
2. Đăng ký RP với redirect URI chính xác và loại client phù hợp (public/confidential).
3. Cấu hình **Authorization Code Flow + PKCE** theo loại client và thư viện được chấp nhận.
4. Kiểm tra issuer, metadata, thuật toán/ký số và cơ chế cập nhật khóa.
5. Định nghĩa **issuer + subject** là cơ sở liên kết danh tính; xác định cách xử lý pairwise subject.
6. Chỉ cho phép scopes/claims cần thiết, có hợp đồng về nguồn và độ mới của thuộc tính.
7. Xác định login, reauthentication, step-up, phiên, logout và xử lý lỗi.
8. Thiết kế nguồn account/entitlement ngoài đăng nhập như SCIM, API hoặc JIT có kiểm soát.
9. Có quy trình giám sát, kiểm toán, thay đổi cấu hình và ngừng tin cậy OP khi cần.

**Đăng ký client thành công không đồng nghĩa một đối tác đã đáp ứng yêu cầu identity proofing hay bảo mật của doanh nghiệp.** Độ tin cậy nghiệp vụ phải được đánh giá và thể hiện trong chính sách.

## 6. Authorization Code Flow + PKCE cho đăng nhập OIDC

Với ứng dụng web/mobile hiện đại, luồng **Authorization Code Flow** kết hợp **PKCE (Proof Key for Code Exchange)** thường được ưu tiên so với việc đưa token trực tiếp qua front channel. Luồng cụ thể và cách xác thực client còn phụ thuộc mô hình ứng dụng.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as Relying Party
    participant B as Trình duyệt
    participant OP as OpenID Provider

    U->>RP: Truy cập ứng dụng
    RP->>RP: Tạo state, nonce, PKCE verifier/challenge
    RP-->>B: Redirect tới authorization endpoint
    B->>OP: Request scope=openid, code_challenge
    OP->>U: Xác thực, MFA nếu cần
    U-->>OP: Hoàn thành xác thực
    OP-->>B: Redirect về RP với authorization code và state
    B->>RP: Chuyển code và state
    RP->>RP: Xác minh state và redirect context
    RP->>OP: Đổi code + code_verifier (và client auth nếu cần)
    OP-->>RP: ID token + access token (tùy scopes)
    RP->>RP: Xác minh ID token, nonce, issuer, audience, exp
    RP-->>U: Thiết lập phiên đăng nhập RP
~~~

### 6.1. Bước 1 – Tạo yêu cầu

RP tạo các giá trị ngẫu nhiên và liên kết chúng với phiên đăng nhập bắt đầu từ phía ứng dụng:

- **state:** gắn response với yêu cầu ban đầu, giúp chống login CSRF và lẫn yêu cầu.
- **nonce:** ràng buộc ID token với yêu cầu xác thực nếu dùng; RP kiểm tra claim nonce theo yêu cầu đã phát.
- **code_verifier:** giá trị bí mật ngẫu nhiên chỉ được client biết trong transaction PKCE.
- **code_challenge:** thường tính theo S256 từ code_verifier và gửi ở authorization request.
- **redirect_uri:** URL đã được đăng ký cho client/OP.

Trong OIDC, **scope chứa openid** là dấu hiệu của yêu cầu xác thực OIDC; các scope khác như profile, email chỉ nên yêu cầu khi cần.

### 6.2. Bước 2 – Người dùng xác thực ở OP

OP áp chính sách xác thực, có thể tận dụng phiên SSO có sẵn hoặc yêu cầu xác thực lại/step-up. RP không nên tự suy ra **mức MFA** từ việc có redirect thành công; nếu ứng dụng cần assurance/freshness cụ thể, phải sử dụng tín hiệu/contract thích hợp và **kiểm tra kết quả trả về**.

### 6.3. Bước 3 – Nhận code và đổi lấy token

OP trả authorization code về redirect URI qua trình duyệt. RP kiểm tra state, sau đó gửi code tới token endpoint cùng code_verifier và cơ chế xác thực client khi áp dụng.

**PKCE bảo vệ khỏi một số dạng đánh cắp/chặn mã authorization code** nhờ yêu cầu bên đổi code chứng minh có code_verifier. PKCE không thay thế việc kiểm tra issuer, redirect URI, state, TLS, ID token hoặc account linking.

### 6.4. Bước 4 – Xác minh kết quả và tạo phiên

RP xác minh ID token theo profile OIDC trước khi tạo phiên đáng tin:

- Token đến từ **issuer được chấp thuận** và đúng tenant/OP của transaction.
- **Chữ ký/thuật toán** được hỗ trợ và đúng khóa tin cậy.
- **Audience** chứa đúng client ID; khi có nhiều audience, kiểm tra các quy tắc liên quan đến authorized party (azp) theo OIDC.
- **exp, iat, nbf nếu có** và các giới hạn thời gian phù hợp.
- **nonce** khớp nếu đã gửi; auth_time và assurance claim nếu policy yêu cầu.
- **Subject (sub)** tồn tại và được liên kết đúng với identity của ứng dụng.
- Kết quả thuộc đúng authorization flow ban đầu, không bị dùng lại cho phiên khác.

Sau đó RP tạo phiên của riêng mình với cookie/cơ chế được bảo vệ; **ID token không phải session cookie tự động**, và thời gian hết hạn ID token không luôn bằng thời hạn phiên ứng dụng.

## 7. Ví dụ yêu cầu OIDC và token

### 7.1. Authorization request minh họa

~~~text
GET https://idp.example.com/authorize
  ?response_type=code
  &client_id=finance-portal
  &redirect_uri=https%3A%2F%2Ffinance.example.com%2Fcallback
  &scope=openid%20profile
  &state=SERVER_GENERATED_OPAQUE_STATE
  &nonce=SERVER_GENERATED_OPAQUE_NONCE
  &code_challenge=SERVER_GENERATED_PKCE_CHALLENGE
  &code_challenge_method=S256
~~~

Đây là **hình dạng yêu cầu minh họa**, không có giá trị chạy trực tiếp. URL, client ID, state, nonce và challenge phải được cấu hình/sinh an toàn trong triển khai thật. OP có thể yêu cầu thêm tham số theo hợp đồng đã thỏa thuận.

### 7.2. Một payload ID token minh họa

~~~json
{
  "iss": "https://idp.example.com",
  "sub": "2bf8a24c-identity-subject",
  "aud": "finance-portal",
  "exp": 1795500000,
  "iat": 1795496400,
  "auth_time": 1795496380,
  "nonce": "SERVER_GENERATED_OPAQUE_NONCE",
  "acr": "urn:example:assurance:workforce-mfa",
  "email": "employee@example.com",
  "email_verified": true
}
~~~

Đây là **payload JSON ví dụ**, không phải token đã ký và cũng không chứng minh một OP nào đạt mức bảo đảm nhất định. Một ID token thật thường là JWT có cấu trúc header, payload và chữ ký; kiểm tra payload hiển thị **không thay thế xác minh chữ ký**.

**Lưu ý:** email có thể đổi, email_verified có thể phản ánh việc OP đã xác minh quyền kiểm soát email theo quy trình của OP, nhưng **không chứng minh quan hệ làm việc, quyền ở công ty hay việc hai account thuộc cùng một người**. Không dùng email làm khóa định danh duy nhất khi linking.

### 7.3. Pseudocode xác minh và liên kết

~~~text
function completeOidcLogin(callback, browserSession):
    transaction = loadPendingOidcTransaction(browserSession)

    require callback.state == transaction.state
    require callback.code is present

    response = exchangeAuthorizationCode(
        trustedTokenEndpoint(transaction.issuer),
        callback.code,
        transaction.codeVerifier,
        registeredRedirectUri(transaction.clientId)
    )

    idToken = validateIdTokenWithOidcLibrary(
        response.idToken,
        expectedIssuer = transaction.issuer,
        expectedClientId = transaction.clientId,
        expectedNonce = transaction.nonce
    )

    require idToken.auth_time satisfies requestedFreshnessIfAny
    require idToken.acr satisfies requiredAssuranceIfAny

    accountLink = findVerifiedLink(idToken.iss, idToken.sub)
    if accountLink is missing:
        return approvedFirstLoginLinkingOrProvisioningFlow()

    currentIdentity = loadCurrentEnterpriseIdentity(accountLink.identityId)
    require identityAndApplicationAccessAllowed(currentIdentity)

    createProtectedRelyingPartySession(accountLink.identityId)
    auditAuthenticationAndLinkingOutcome()
~~~

Đây là **mã giả giáo dục**, không phải triển khai OIDC hoàn chỉnh. Hệ thống sản xuất nên dùng **OIDC library đã được kiểm chứng** và cấu hình chặt, không tự viết trình xác minh JWT/giao thức từ đầu. Cần xử lý CSRF, code reuse, đồng hồ, cache JWKS, client authentication, network timeout và thông báo lỗi an toàn.

## 8. ID token, access token, refresh token và session khác nhau thế nào?

| Thành phần | Dành cho ai / mục đích | Điều cần kiểm soát |
| --- | --- | --- |
| **ID token** | RP biết kết quả xác thực danh tính người dùng từ OP | iss, aud, signature, thời hạn, sub, nonce, auth_time/assurance nếu dùng |
| **Access token** | Client gọi API/resource server theo phạm vi cấp | Audience, scope/permission, expiry, xác minh tại API; có thể opaque |
| **Refresh token** | Client yêu cầu token mới theo chính sách OP | Lưu trữ an toàn, rotation/revoke khi hỗ trợ, rủi ro lộ token |
| **RP session** | Ứng dụng duy trì trạng thái đăng nhập của người dùng | Cookie, TTL, revocation, CSRF, kiểm quyền hiện hành |
| **OP/IdP session** | IdP biết người dùng đã xác thực và có thể phục vụ SSO | Timeout, step-up, logout, chính sách thiết bị và bảo mật |
| **SCIM account state** | User/group resource của ứng dụng quản lý tài khoản | Không tự phản ánh tuổi phiên hoặc mọi API token |
| **Role/entitlement** | Quyền nghiệp vụ tại ứng dụng/API | RBAC/ABAC, approval, nguồn và kiểm tra drift |

### 8.1. ID token không phải access token

Một API không nên dùng **ID token dành cho RP** làm căn cứ ủy quyền gọi API nếu không có thiết kế đặc biệt và kiểm chứng phù hợp. Resource server cần xác minh **access token dành cho chính API** và áp chính sách trên tài nguyên.

Ngay cả khi cả hai được mã hóa dưới dạng JWT, **mục đích và audience khác nhau**. Việc token có định dạng JWT không biến nó thành loại token phù hợp cho mọi endpoint.

### 8.2. Hết hạn token không đồng nghĩa logout tức thì

- ID token hết hạn: RP không nên dùng nó như bằng chứng mới vô hạn; nhưng một phiên ứng dụng được tạo hợp lệ trước đó có thể vẫn tồn tại theo chính sách RP.
- Access token hết hạn: API từ chối token đó khi kiểm tra; refresh token hoặc phiên khác có thể cho phép lấy token mới.
- IdP disabled: chặn một số đăng nhập/cấp token mới, nhưng **không mặc nhiên xóa mọi phiên/tokens đã phát ở tất cả ứng dụng**.
- SCIM User.active = false: vô hiệu hóa user ở phạm vi provider hỗ trợ; không tự xử lý mọi phiên hoặc quyền cục bộ.

Bởi vậy, **Leaver** phải có chiến lược riêng cho account, entitlement, session và token.

## 9. Account linking: dùng issuer + subject, không dùng email

**Account linking** là quá trình gắn danh tính được OP khẳng định với account/identity mà ứng dụng đang quản lý. Đây là một trong những bước nhạy cảm nhất của federation.

### 9.1. Khóa liên kết an toàn

Trong OIDC, **sub (subject identifier)** là định danh chủ thể do OP phát hành. Nó cần được diễn giải **trong phạm vi issuer (iss)**. Hai OP khác nhau có thể phát cùng giá trị sub cho hai người hoàn toàn khác nhau.

Một khóa liên kết thường cần dạng:

~~~text
externalIdentityKey = (
  issuer = "https://idp.example.com",
  subject = "2bf8a24c-identity-subject"
)

linkedTo:
  internalIdentityId = "person-1042"
  targetAppAccountId  = "finance-user-719"
  linkStatus          = VERIFIED
~~~

**Không dùng chỉ sub, chỉ email hoặc chỉ domain để merge account.** Tên người dùng và email có thể thay đổi, bị tái sử dụng hoặc do OP khác xác minh theo tiêu chí khác.

### 9.2. Public và pairwise subject

Một số OP hỗ trợ **pairwise subject identifiers**: cùng một người có thể được cấp các giá trị sub khác nhau cho những RP hoặc nhóm RP khác nhau nhằm giảm khả năng liên kết hoạt động giữa các ứng dụng.

Vì vậy, không nên kỳ vọng một giá trị sub của ứng dụng A luôn dùng được để tìm account ứng dụng B. Doanh nghiệp cần **identity registry và bản đồ linking** được thiết lập theo nguồn/tenant, với các bằng chứng cần thiết.

### 9.3. First login và JIT provisioning

Ở lần đăng nhập đầu tiên, RP có thể:

1. Từ chối và yêu cầu account được provision trước qua SCIM/API.
2. Tạo account **Just-in-Time (JIT)** nếu hợp đồng và chính sách cho phép.
3. Yêu cầu luồng xác minh liên kết thủ công hoặc có phê duyệt khi không thể xác định chắc chắn chủ thể.

Một JIT flow an toàn nên kiểm tra **issuer được phép, sub, điều kiện nghiệp vụ, workerType, trạng thái quan hệ làm việc, tenant, policy và quyền tối thiểu**. Không tự cấp role Admin chỉ vì ID token chứa địa chỉ email với domain nội bộ.

### 9.4. Rehire và email được cấp lại

Nhân viên A nghỉ việc, email được cấp lại cho nhân viên B. Nếu RP tìm account theo email, B có thể bị liên kết nhầm tài khoản của A, thừa hưởng role hoặc dữ liệu cũ.

Cần dùng identityId ổn định, lịch sử quan hệ làm việc, mapping issuer+sub và quy trình JML. Khi rehire, quyết định tái sử dụng account phải dựa trên **xác minh đúng chủ thể và policy hiện hành**, không tự động mở quyền trước đó.

## 10. Claims, thuộc tính và RBAC/ABAC trong federation

OIDC có các claim danh tính như sub và, tùy phạm vi yêu cầu/cấu hình, name, email, email_verified; môi trường doanh nghiệp có thể cung cấp thêm nhóm, vai trò hoặc thuộc tính tổ chức qua cơ chế riêng.

**OIDC không bắt buộc một schema nhóm/role doanh nghiệp thống nhất giữa mọi IdP.** Nếu RP dựa trên claim nhóm, phải có **hợp đồng rõ** về tên, nguồn, ngữ nghĩa, thời gian cập nhật và cách xử lý khi claim thiếu.

| Claim hoặc thuộc tính | Có thể dùng để | Cần tránh |
| --- | --- | --- |
| **iss + sub** | Xác định và liên kết subject từ OP | Suy luận quyền nghiệp vụ chỉ từ subject |
| **email** | Hiển thị/liên hệ theo mục đích được phép | Dùng làm khóa account hoặc chứng cứ nhân viên ACTIVE |
| **email_verified** | Nhận biết OP đã xác nhận email theo quy trình của mình | Coi là proofing danh tính ngoài đời hoặc quyền công ty |
| **name, preferred_username** | Hiển thị hoặc hỗ trợ người dùng | Dùng để merge account tự động |
| **groups/roles (custom)** | Là đầu vào authorization nếu hợp đồng cho phép | Giả định nhóm ở mọi OP mang cùng quyền |
| **department/organization** | Là đầu vào ABAC có kiểm soát | Tin thuộc tính cũ trong token khi Mover |
| **acr/amr/auth_time** | Đánh giá assurance và freshness | Tin nhãn phương thức mà không xác minh ngữ nghĩa |

### 10.1. Từ claim đến quyền

Một chính sách minh họa:

~~~text
PERMIT invoice.read WHEN
    identity.accountLinkVerified == TRUE
    AND identity.lifecycleStatus == ACTIVE
    AND identity.hasApprovedEntitlement("FINANCE_INVOICE_READ")
    AND identity.department == resource.department
    AND session.assuranceSatisfies(policy.requiredAssurance)
ELSE DENY
~~~

Đây chỉ là **mã giả**, không phải ngôn ngữ chuẩn của OIDC/RBAC/ABAC. Ứng dụng phải quản lý nguồn, độ mới và thứ bậc policy; **claim có nhóm Finance không đồng nghĩa mọi hóa đơn đều được đọc**.

### 10.2. Role đến từ đâu?

Có hai lựa chọn phổ biến:

- **Role do ứng dụng quản lý:** OIDC cung cấp xác thực, còn role được provision qua SCIM/API hoặc phê duyệt nội bộ.
- **Role dẫn xuất từ IdP claim:** ứng dụng ánh xạ group/claim đáng tin sang role, nhưng phải theo dõi mapping, quyền thực tế và sự kiện thay đổi.

Hai cách có thể cùng tồn tại, nhưng cần quy định **nguồn có thẩm quyền cho từng entitlement** để tránh một hệ thống gỡ quyền rồi hệ thống khác cấp lại vì dữ liệu cũ.

## 11. Federation trong vòng đời Joiner–Mover–Leaver

### 11.1. Joiner: xác minh, tạo account và đăng nhập lần đầu

Một Joiner an toàn thường đi qua:

1. HRIS/nguồn hợp đồng xác nhận quan hệ việc làm, ngày bắt đầu và người quản lý.
2. Identity proofing thiết lập đủ tin cậy rằng đúng chủ thể được gắn với hồ sơ.
3. Identity registry tạo hoặc liên kết **identityId ổn định**.
4. IdP tạo/kích hoạt account và đăng ký authenticator phù hợp, ví dụ MFA/passkey.
5. RP được đăng ký trust với IdP; ứng dụng tạo account qua SCIM/API hoặc JIT có kiểm soát.
6. Quyền được tính theo RBAC/ABAC, least privilege, SoD và approval.
7. Reconciliation xác minh account và entitlement thực tế, không chỉ kiểm tra đăng nhập OIDC.

**OIDC login có thể thành công trước khi quyền nghiệp vụ được provision hoàn chỉnh.** Ứng dụng cần hiển thị trạng thái thiếu quyền/đang chờ, không cấp tạm đặc quyền để che lỗi tích hợp.

### 11.2. Mover: claim mới và quyền cũ

Nhân viên chuyển từ Support sang Finance; employment status có thể vẫn ACTIVE. Khi đó:

- HRIS cập nhật department/manager/job.
- IGA tính lại desired entitlements và yêu cầu gỡ quyền Support.
- IdP có thể thay group hoặc claim, ứng dụng có thể cập nhật SCIM/API.
- Token được phát trước Mover có thể còn claim cũ cho tới khi hết hạn/được thay thế.
- Session tại RP có thể giữ cache role hoặc quyền cũ nếu không có cơ chế kiểm tra lại.
- Reconciliation đối soát các entitlement, role trực tiếp và khả năng phiên tồn dư.

**Chỉ cập nhật claim ở IdP không đảm bảo role cũ trong ứng dụng đã mất.** Khi chuyển vai trò đặc quyền, có thể cần hủy phiên hoặc yêu cầu đăng nhập lại/step-up, nhưng phải **gỡ entitlement** theo đúng vòng đời.

### 11.3. Leaver: federation không tự chấm dứt mọi phiên

Khi HRIS/nguồn hợp đồng xác nhận nghỉ việc có hiệu lực:

1. Điều phối Leaver chặn đường đăng nhập mới ở IdP theo chính sách.
2. Thu hồi quyền và vô hiệu hóa account tại ứng dụng bằng SCIM/API hoặc quy trình phù hợp.
3. Xử lý refresh token, session, khóa, chứng chỉ hoặc API key theo khả năng từng hệ thống.
4. Kiểm tra RP session độc lập có còn hợp lệ và còn cho phép API không.
5. Đối soát desired/observed state, ghi lỗi và tiếp tục remediation.
6. Giữ audit chứng minh thời điểm yêu cầu, áp dụng và xác minh thu hồi.

**Một IdP account bị disabled không thể được coi là bằng chứng mọi RP đã logout tức thời.** Một ứng dụng có thể duy trì phiên riêng, token đã phát còn hạn hoặc quyền local. Khi cần dừng ngay, cần kiểm soát session/revocation rõ ràng, thời hạn token phù hợp và kiểm tra trạng thái quyền hiện hành tại backend.

### 11.4. Tạm nghỉ, khóa bảo mật và rehire

- **Tạm nghỉ:** nguồn nhân sự vẫn có thể ghi quan hệ làm việc hợp lệ nhưng quyền nhạy cảm cần hạn chế; không mặc định mọi ON_LEAVE là Leaver.
- **Khóa do sự cố:** HRIS ACTIVE không được tự mở lại tài khoản bị chặn do an ninh.
- **Rehire:** có thể liên kết lại identity nếu xác minh đúng người, nhưng không tự kích hoạt role/token cũ; entitlement phải tính mới.
- **Nhiều quan hệ làm việc:** một người kết thúc quan hệ A nhưng còn hợp đồng B; cần đánh giá quyền theo relationship thay vì vô hiệu hóa toàn bộ khi không thích hợp.

## 12. Session, logout và thu hồi trong federation

Trong OIDC federation, có thể tồn tại ít nhất **phiên IdP**, **phiên RP** và **token truy cập API**. Chúng có lifecycle khác nhau.

### 12.1. Những kiểu logout cần phân biệt

| Hành động | Mục tiêu | Giới hạn |
| --- | --- | --- |
| **Local RP logout** | Xóa/vô hiệu hóa phiên tại một ứng dụng | Không tự đăng xuất khỏi IdP hoặc mọi RP |
| **RP-Initiated Logout** | RP đề nghị OP kết thúc phiên OP theo tính năng được hỗ trợ | Phụ thuộc capability và cấu hình OP |
| **Front-channel logout** | Thông báo qua trình duyệt tới RP tham gia | Phụ thuộc trình duyệt, cookie và cơ chế tích hợp |
| **Back-channel logout** | OP gửi thông báo server-to-server tới RP hỗ trợ | RP phải kiểm chứng và xử lý logout token |
| **Token revocation** | Thu hồi token khi hệ thống hỗ trợ | Token self-contained có thể vẫn được chấp nhận cho tới hạn nếu API không có cơ chế kiểm tra lại |
| **Ứng dụng deprovision** | Vô hiệu hóa account/role tại đích | Không đảm bảo mọi token/session bị loại bỏ |
| **Session TTL ngắn** | Hạn chế cửa sổ truy cập khi không có revocation tức thời | Chỉ là biện pháp giảm rủi ro, không thay thế thu hồi theo chính sách |

Không phải mọi OP và RP đều hỗ trợ tất cả hình thức logout. Thiết kế phải khảo sát **khả năng thực tế của từng bên**, không chỉ dựa vào thuật ngữ trong tài liệu giao thức.

### 12.2. Nếu logout không truyền được thì sao?

Một RP không xử lý back-channel logout có thể tiếp tục cho phép phiên cũ. Hệ thống nên có biện pháp:

- Kiểm tra account/entitlement hiện hành trước tác vụ nhạy cảm.
- Dùng phiên và access token có tuổi thọ phù hợp rủi ro.
- Hỗ trợ revoke/terminate session tại RP khi có tích hợp.
- Có thể chủ động kiểm tra tình trạng phiên hoặc token tại nguồn phù hợp theo kiến trúc.
- Ghi ngoại lệ và xử lý thủ công khi đích không hỗ trợ thu hồi tự động.
- Định kỳ đối soát account, role, token/phiên có thể quan sát.

**Không gọi kết thúc phiên thành công khi chỉ gửi thông báo logout nhưng RP chưa có bằng chứng đã xử lý.**

## 13. Federation với nhiều IdP và tổ chức đối tác

Một ứng dụng có thể chấp nhận đăng nhập từ **IdP doanh nghiệp**, **IdP của đối tác**, hoặc một số OP khác theo chính sách. Điều này tăng tính linh hoạt nhưng cũng mở thêm ranh giới tin cậy.

### 13.1. Mỗi issuer là một miền tin cậy

Ví dụ hai OP có thể cùng phát subject có giá trị giống nhau:

~~~text
Issuer A:
  iss = https://identity.partner-a.example
  sub = user-1007

Issuer B:
  iss = https://identity.partner-b.example
  sub = user-1007

Hai external identities khác nhau.
Không được gộp chỉ vì sub hoặc email trùng nhau.
~~~

RP phải **gắn transaction đăng nhập với issuer được chọn**, kiểm tra response đến đúng OP và không bị mix-up khi nhiều authorization server cùng được cấu hình.

### 13.2. Tài khoản đối tác và B2B federation

Với đối tác, doanh nghiệp nên có:

- Hợp đồng trust và phạm vi người dùng/tenant được phép.
- Chủ thể hoặc sponsor chịu trách nhiệm về quyền truy cập bên RP.
- Phương pháp account linking đủ tin cậy; không chỉ email domain.
- Yêu cầu proofing và assurance phù hợp với tài nguyên.
- Ngày bắt đầu/kết thúc hợp đồng và cách đối tác thông báo Leaver.
- Cơ chế review định kỳ hoặc thu hồi khi nguồn đối tác trễ dữ liệu.
- Giới hạn quyền theo tổ chức, dự án, tài nguyên, tránh một tenant nhìn dữ liệu tenant khác.

**Federation làm giảm việc RP phải quản lý mật khẩu của đối tác**, nhưng không chuyển toàn bộ trách nhiệm authorization và offboarding cho IdP đối tác. Đội IAM vẫn cần owner và khả năng thu hồi quyền phía mình.

### 13.3. Thay đổi nhà cung cấp danh tính

Khi chuyển OP, issuer/sub thường thay đổi. Không nên tự merge account bằng email rồi xóa liên kết cũ. Cần migration plan:

1. Kiểm kê RP, client và account mapping hiện tại.
2. Xây dựng bằng chứng liên kết chủ thể giữa OP cũ/mới từ nguồn có thẩm quyền.
3. Chạy song song có kiểm soát, gắn account link mới và xác minh quyền.
4. Vô hiệu hóa trust/credentials cũ theo lịch sau khi xác minh.
5. Kiểm tra logout/session, JML event và quyền tồn dư.
6. Lưu audit và cơ chế rollback không khôi phục quyền không hợp lệ.

## 14. Step-up và mức bảo đảm qua OIDC

OIDC có thể hỗ trợ RP yêu cầu **mức hoặc ngữ cảnh xác thực** theo cơ chế của OP, ví dụ một số tham số/claim:

| Tín hiệu | Ý nghĩa | Điều cần chú ý |
| --- | --- | --- |
| **acr** | Authentication Context Class Reference | Giá trị do OP khẳng định; nghĩa cụ thể cần contract |
| **amr** | Các phương thức xác thực đã dùng | Không mặc nhiên đủ để suy ra phishing resistance |
| **auth_time** | Thời điểm xác thực | Kiểm tra độ mới theo policy |
| **acr_values** | Các giá trị ACR RP muốn OP áp dụng | Yêu cầu không phải bằng chứng OP đã thực thi |
| **max_age** | Tuổi xác thực tối đa chấp nhận được | Có thể yêu cầu reauthentication nhưng không tự nâng phương thức |
| **prompt=login** | Yêu cầu OP xác thực lại | Không đồng nghĩa MFA mạnh hơn |

Ví dụ RP có thể yêu cầu một context phù hợp trước thao tác quản trị; sau đó **kiểm tra kết quả thực** và xác minh role vẫn hợp lệ. Nếu người dùng vừa Leaver, step-up thành công **không làm họ được quyền truy cập trở lại**.

**Step-up là điều kiện thực thi quyền đã được phê duyệt**, không thay thế authorization. Một ứng dụng có role Admin sai cần sửa role/provisioning và reconciliation, không chỉ đặt thêm hộp thoại MFA.

## 15. Rủi ro và biện pháp bảo vệ OIDC federation

| Rủi ro | Cơ chế gây lỗi | Kiểm soát |
| --- | --- | --- |
| **Tin sai issuer** | RP chấp nhận token từ OP không được phép | Allowlist issuer, kiểm metadata và iss chính xác |
| **Sai audience** | ID token dành cho client khác được chấp nhận | Kiểm aud và azp khi áp dụng |
| **Bỏ qua xác minh chữ ký/thuật toán** | JWT bị sửa hoặc dùng thuật toán không mong muốn | Thư viện OIDC tin cậy, allowlist thuật toán, khóa theo OP |
| **JWKS bị thay nguồn** | Lấy khóa xác minh từ URL chưa đáng tin | Ràng buộc JWKS với metadata OP đã tin cậy |
| **Authorization code bị chặn** | Kẻ tấn công đổi code lấy token | PKCE, TLS, bảo vệ redirect và client auth phù hợp |
| **Login CSRF / session swapping** | Callback bị liên kết với phiên không phải bên yêu cầu | state, session binding, nonce và cookie bảo vệ |
| **Open redirect** | Redirect tới URL do kẻ tấn công điều khiển | Exact redirect registration, không dùng redirect tùy ý |
| **Mix-up giữa nhiều OP** | RP nhầm response OP A với OP B | Ràng buộc issuer/transaction, xử lý multi-OP chuẩn |
| **Account takeover do email** | Gắn account cũ cho người có email được tái sử dụng | Link issuer+sub, xác minh và review ngoại lệ |
| **Tin group claim quá mức** | Claim bị hiểu sai hoặc stale | Policy, role mapping có owner, recheck và reconcile |
| **Token bị lộ trong browser/log** | Token xuất hiện ở URL, log hoặc local storage không an toàn | Authorization code flow, server-side handling, lưu trữ bảo vệ |
| **Phiên RP còn sau Leaver** | RP không nhận logout/deprovision | Session control, revoke, TTL và kiểm quyền hiện hành |
| **IdP account ACTIVE làm mở khóa bảo mật** | Đồng bộ trạng thái ghi đè security block | Tách policy chặn bảo mật khỏi HR lifecycle |
| **Recovery yếu** | Kẻ tấn công chiếm tài khoản IdP rồi đăng nhập RP | Recovery/proofing, MFA phù hợp, cảnh báo |
| **Trust OP/connector không có owner** | Cấu hình lỗi thời, client secret không rotate | Inventory, owner, expiration, review và decommission |

### 15.1. Không tự viết lại trình xác minh giao thức

Đối với ứng dụng thực tế, sử dụng thư viện OIDC/OAuth được bảo trì phù hợp môi trường, áp cấu hình **issuer, client ID, redirect, TLS, state/nonce, PKCE** và xử lý lỗi theo mô hình tài liệu của thư viện.

Các đoạn mã giả trong bài nhằm giải thích kiến trúc. Tự xử lý JWT bằng cách chỉ decode base64, hoặc chỉ kiểm một claim rồi tạo phiên, là **không an toàn**.

### 15.2. Chống lộ token và dữ liệu cá nhân

Token có thể chứa claim nhận dạng và đôi khi thuộc tính nghiệp vụ. Không ghi **ID/access/refresh token, client secret, code_verifier, khóa riêng, cookie phiên** vào log hoặc ticket. Hạn chế claim được chia sẻ theo mục đích và quy tắc bảo vệ dữ liệu.

**JWT được mã hóa dạng base64url và ký không đồng nghĩa nội dung đã được mã hóa bí mật.** Những bên đọc được token có thể giải mã phần payload nếu token không được mã hóa theo cơ chế bảo mật riêng.

## 16. Tài khoản dịch vụ, workload identity và OIDC federation

OIDC ban đầu thường được dùng cho **xác thực người dùng** ở RP, nhưng trong hạ tầng cloud/CI/CD, một số nền tảng dùng **OIDC token do issuer tin cậy phát hành** để thiết lập federation cho workload với cơ chế trao đổi lấy credential đích ngắn hạn.

Đây là trường hợp cần phân biệt với luồng người dùng trình duyệt:

| Trường hợp | Subject | Mục tiêu | Kiểm soát đặc thù |
| --- | --- | --- | --- |
| **Người dùng đăng nhập RP** | Human identity | Xác thực người dùng và lập phiên ứng dụng | MFA/passkey, account linking, JML |
| **CI/CD workload federation** | Job/pipeline/workload identity | Chứng minh workload từ môi trường tin cậy để xin credential API/cloud | Issuer, aud, subject/claims, repo/environment, TTL |
| **Service account truyền thống** | Principal phi con người | Gọi API không tương tác | Owner, secret/key rotation, scope và revocation |

Không nên coi một **OIDC ID token cho người dùng** là credential có quyền quản trị cloud hoặc API, cũng không dùng OTP nhân viên trong pipeline. Workload federation phải được **nền tảng đích hỗ trợ và cấu hình trust theo issuer/audience/subject cụ thể**, kèm điều kiện môi trường và vai trò tối thiểu.

### 16.1. Ví dụ thiết kế workload federation

Một pipeline triển khai có thể nhận token do nền tảng CI/CD phát hành. Nền tảng cloud chỉ tin token nếu:

- **Issuer** đúng bên đã cấu hình.
- **Audience** dành cho dịch vụ nhận credential.
- **Subject/claims** khớp repository, branch, environment và job được cho phép.
- Token còn hiệu lực, chữ ký hợp lệ và không bị dùng sai audience.
- Role cloud được gán cho workload có **scope hẹp**, thời hạn ngắn và audit.
- Nguồn pipeline, người quản trị repo và quyền sửa workflow được bảo vệ.

Nếu nhân viên phụ trách pipeline Mover/Leaver, IAM cần **chuyển ownership, gỡ quyền quản trị của người đó và kiểm tra trust/credential của workload**, thay vì xóa workload vẫn phục vụ sản xuất.

## 17. Kiểm toán và đối soát federation

### 17.1. Dữ liệu cần có trong audit trail

| Nhóm | Trường/bằng chứng thường cần | Mục đích |
| --- | --- | --- |
| **Trust configuration** | issuer, clientId, policy/trust version | Xác định RP tin OP nào tại thời điểm đó |
| **Login request** | request/correlation ID, thời điểm, redirect, loại flow | Truy lại chuỗi giao thức mà không lưu secret |
| **Kết quả xác thực** | issuer, subject reference, auth_time, assurance có thể kiểm chứng | Biết ai đã xác thực và theo chính sách nào |
| **Account linking** | internal identityId, RP accountId, method, review | Truy lại quyết định gắn danh tính |
| **Authorization** | role/entitlement, policy version, resource, decision | Giải thích vì sao được hoặc bị từ chối |
| **JML event** | nguồn HRIS, relationship, effectiveAt, version | Liên kết với ngày gia nhập/đổi vai trò/nghỉ việc |
| **Provisioning** | SCIM/API request, trạng thái, targetAccountId | Kiểm tra quyền được áp dụng |
| **Session/logout** | session reference, logout/revoke request và kết quả | Đánh giá khả năng truy cập sau Leaver |
| **Reconciliation** | desired/observed, verifiedAt, gaps và owner | Phát hiện quyền tồn dư hoặc account mồ côi |

Không lưu token thô, cookie, mã authorization hoặc bí mật client. Với subject trong log, có thể dùng ID hoặc tham chiếu nội bộ được bảo vệ để giảm lan truyền dữ liệu cá nhân.

### 17.2. Những câu hỏi đối soát quan trọng

- Account RP nào không còn identity/owner hợp lệ?
- Có ứng dụng nào sử dụng issuer/tenant ngoài allowlist không?
- Người đã Leaver còn local account, role hoặc phiên RP hoạt động không?
- Người Mover còn group/entitlement cũ ở ứng dụng dù claim IdP đã cập nhật không?
- RP nào không hỗ trợ logout/revocation nhưng chứa dữ liệu nhạy cảm?
- Account nào được tạo qua JIT nhưng không có trong inventory IGA?
- Có claim nhóm/role nào dẫn đến quyền ngoài approval hoặc xung đột SoD?
- Service/workload trust nào còn hoạt động dù owner hoặc pipeline đã ngừng?

**Reconciliation là cách kiểm tra trạng thái thật, không chỉ ghi nhận rằng đăng nhập OIDC trước đó thành công.**

## 18. Tình huống thực tế: một doanh nghiệp, hai IdP và ba giai đoạn JML

Giả sử doanh nghiệp sử dụng **IdP-A** cho nhân viên, **IdP-B** của đối tác cho nhà thầu. Ứng dụng báo cáo chấp nhận cả hai issuer, nhưng mọi quyền dữ liệu đều phải do bộ phận quản lý tài nguyên phê duyệt.

### 18.1. Joiner: nhà thầu bắt đầu làm việc

Một nhà thầu mới có hồ sơ hợp đồng và sponsor. IdP-B xác thực thành công và phát ID token. RP kiểm issuer+sub, nhưng không tìm thấy account link:

- RP không tự tạo account FinanceAdmin dựa trên email đối tác.
- IGA kiểm tra sponsor, hợp đồng, ngày hiệu lực, proofing/assurance theo policy.
- Account JIT (nếu được phép) hoặc SCIM/API tạo user với quyền tối thiểu.
- RP liên kết issuer+sub với identity và kiểm tra đúng tenant.
- Reconciliation xác minh role/report access đúng scope và ngày hết hạn.

### 18.2. Mover: nhân viên đổi phòng ban

Nhân viên ở IdP-A chuyển Support sang Finance. IdP cập nhật claim department, nhưng RP còn phiên cũ và role SupportReader cục bộ:

- IGA tính desired mới và yêu cầu gỡ SupportReader.
- RP không được dùng claim hoặc local cache cũ để tiếp tục cho đọc dữ liệu Support.
- Nếu thao tác Finance nhạy cảm, ứng dụng có thể yêu cầu step-up, nhưng vẫn phải kiểm entitlement mới.
- Reconciliation phát hiện EXTRA_ACCESS nếu role cũ còn tồn tại, tiếp tục remediation.

### 18.3. Leaver: nhà thầu hết hạn

Hợp đồng nhà thầu hết hiệu lực. Doanh nghiệp ngừng quyền RP theo hợp đồng, kể cả khi IdP-B chưa khóa account:

- IGA vô hiệu hóa/thu hồi tài khoản và role của ứng dụng theo policy.
- Phiên RP đã tạo trước đó được chặn/thu hồi theo khả năng hệ thống.
- OP đối tác có thể vẫn cho người dùng đăng nhập các dịch vụ khác của họ; điều đó **không phải căn cứ** để RP của doanh nghiệp cấp tiếp quyền.
- Đối soát xác nhận tài khoản, entitlement và đường truy cập liên quan đã được xử lý.

**Bài học:** OP xác thực chủ thể, nhưng tổ chức sở hữu tài nguyên vẫn phải quyết định **chủ thể còn cơ sở nghiệp vụ và quyền truy cập hay không**.

## 19. Chỉ số vận hành OIDC federation

| Chỉ số | Điều cần theo dõi | Giá trị |
| --- | --- | --- |
| **Federated login success/failure** | Kết quả theo issuer, RP và loại lỗi | Phát hiện cấu hình sai, gián đoạn |
| **ID token validation errors** | Sai iss, aud, nonce, signature, expiry | Theo dõi trust và nguy cơ tấn công |
| **Account-linking exception rate** | RP không tìm được link hoặc link mơ hồ | Giảm nhầm chủ thể và JIT account trùng |
| **JIT/SCIM provisioning mismatch** | Login thành công nhưng account/role chưa đúng | Theo dõi khoảng cách auth–provisioning |
| **Claim freshness/drift** | Thuộc tính IdP/RP khác nguồn có thẩm quyền | Phát hiện quyền cũ sau Mover |
| **Leaver session residual** | Người đã nghỉ còn phiên/role trong scope | Giảm quyền tồn dư |
| **Logout propagation coverage** | RP nào có cơ chế và bằng chứng logout | Nhận biết giới hạn thu hồi |
| **Unknown issuer/client count** | Trust không có owner hoặc không được phê duyệt | Giảm shadow federation |
| **Trust/secret rotation compliance** | Client secret, key và owner theo chính sách | Giảm cấu hình lỗi thời |
| **Workload federation owner coverage** | Trust workload có người/nhóm chịu trách nhiệm | Ngăn principal phi con người mồ côi |

Không nên coi tỷ lệ đăng nhập thành công cao là bằng chứng governance tốt. Một RP có thể đăng nhập trơn tru nhưng vẫn cấp quyền sai hoặc không thu hồi khi Leaver.

## 20. Bảng kiểm tra khi thiết kế OIDC federation

| Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| OP/issuer có được doanh nghiệp chấp thuận không? | Trust inventory, owner, phạm vi tenant |
| Client và redirect URI có đăng ký đúng không? | Client ID và redirect allowlist chính xác |
| Có dùng luồng phù hợp cùng PKCE không? | Authorization Code + PKCE theo mô hình client |
| Có kiểm tra state, nonce và transaction binding không? | Dữ liệu ngẫu nhiên ở server, replay/CSRF controls |
| Có xác minh ID token bằng thư viện tin cậy không? | Issuer, signature, aud/azp, exp, nonce và policy |
| JWKS/discovery có bị lấy từ nguồn tùy ý không? | Metadata gắn OP allowlist, kiểm soát rotation |
| Có phân biệt ID token, access token và RP session không? | Audience/scope và lưu token đúng mục đích |
| Có link issuer+sub thay vì email không? | Account map, chính sách pairwise/reuse/rehire |
| Có quản lý đa OP và mix-up không? | Issuer gắn với transaction và tenant |
| Role/group claim có nghĩa thống nhất không? | Contract, nguồn, TTL và policy mapping |
| Có kiểm tra authorization ở backend/API không? | RBAC/ABAC, SoD, approval và scope tài nguyên |
| Có thiết kế SCIM/API/JIT riêng OIDC không? | Provisioning ownership, tránh account trùng |
| Có xử lý Joiner với proofing và effectiveAt không? | Identity link, ngày bắt đầu, quyền tối thiểu |
| Mover có gỡ quyền cũ/đổi phiên không? | Desired vs observed và session controls |
| Leaver có chặn RP access độc lập IdP không? | Account, token, phiên và reconciliation evidence |
| Có hiểu logout protocol được hỗ trợ thực tế không? | RP-Initiated/front-/back-channel capability |
| Có chính sách step-up cho quyền nhạy cảm không? | Assurance, freshness và recheck authorization |
| Danh tính workload có vòng đời riêng không? | Issuer/audience/subject trust, owner, TTL |
| Audit có đủ phục vụ điều tra mà không chứa token không? | Correlation ID, nguồn, quyết định, verifiedAt |
| Có thể phát hiện trust lỗi thời và shadow RP không? | Inventory, monitoring, review và decommission |

## 21. Những nhầm lẫn thường gặp

1. **“OIDC là OAuth 2.0, nên access token chính là ID token.”** Hai loại có mục đích và audience khác nhau.
2. **“Ứng dụng đã dùng OIDC thì không cần SCIM/provisioning.”** OIDC xác thực; quyền/tài khoản ở đích cần quản lý riêng.
3. **“SSO đăng nhập thành công nghĩa là người đó còn làm việc.”** RP phải kết hợp trạng thái nghiệp vụ và chính sách hiện hành.
4. **“Chỉ cần decode JWT là đã xác minh.”** Phải kiểm chữ ký, issuer, audience, thời hạn và ràng buộc giao thức.
5. **“Email đã verified là định danh ổn định.”** Email có thể đổi/tái sử dụng; linking nên dựa issuer+sub và bằng chứng.
6. **“sub duy nhất trên toàn thế giới.”** sub có ý nghĩa trong phạm vi issuer và có thể pairwise theo RP.
7. **“OIDC chỉ cần redirect và nhận token; không cần state hay PKCE.”** Phải bảo vệ transaction, CSRF và code interception.
8. **“ID token hết hạn là RP đã logout.”** RP session có lifecycle riêng.
9. **“Khóa IdP là mọi SaaS tự kết thúc phiên.”** Logout/deprovision có giới hạn và cần đối soát.
10. **“Đổi group IdP thì role ứng dụng tự đúng ngay.”** Claim cũ, cache và quyền local có thể tồn tại.
11. **“OIDC claim nhóm đủ để cấp role admin.”** Cần RBAC/ABAC, SoD và approval.
12. **“Workload federation giống đăng nhập trình duyệt của nhân viên.”** Workload có issuer/audience/subject và vòng đời khác.
13. **“Nhà thầu đăng nhập được bằng IdP của họ nghĩa là RP phải cấp quyền.”** Ứng dụng doanh nghiệp vẫn kiểm hợp đồng và entitlement.
14. **“Một RP login đúng thì toàn bộ federation đã an toàn.”** Cần inventory các OP/RP, token validation, logout và governance đầu cuối.

## 22. Câu hỏi tự đánh giá

1. OIDC federation khác SSO và SCIM provisioning ở điểm nào? Vì sao cần đủ cả ba trong nhiều doanh nghiệp?
2. OP/IdP và RP có trách nhiệm gì? Resource server khác RP ra sao?
3. Trình bày các bước Authorization Code Flow + PKCE và vai trò của state, nonce, code_verifier.
4. Vì sao cần kiểm iss, aud và chữ ký của ID token, không chỉ tin payload đã decode?
5. Khác nhau giữa ID token, access token, refresh token, RP session và OP session là gì?
6. Vì sao cặp issuer+sub phù hợp làm khóa linking hơn email? Pairwise subject ảnh hưởng ra sao?
7. Nếu ứng dụng có nhiều IdP, điều gì ngăn response từ IdP-B bị xử lý như IdP-A?
8. Khi HRIS thay department nhưng RP vẫn có token và role cũ, những bước Mover nào cần thực hiện?
9. Một nhân viên đã Leaver nhưng còn local RP session. Khóa IdP có chắc dừng ngay mọi truy cập không?
10. OIDC có tự quyết định quyền tài chính theo RBAC/ABAC không? Ai chịu trách nhiệm approval và SoD?
11. Nếu ứng dụng hỗ trợ JIT provisioning, cần kiểm tra gì để tránh account takeover hoặc role quá rộng?
12. auth_time, acr và amr hỗ trợ step-up thế nào? Vì sao không thể suy ra kết quả chỉ từ acr_values?
13. Khi dùng OIDC workload token để xin credential cloud, cần kiểm issuer, audience, subject và điều kiện workload nào?
14. Những dấu vết kiểm toán nào chứng minh đã ngừng truy cập của một nhà thầu dùng IdP đối tác?
15. Nêu ba dấu hiệu cho thấy federation vẫn đăng nhập được nhưng quản trị vòng đời danh tính chưa an toàn.

## 23. Ghi nhớ

**OIDC federation** cho phép một **Relying Party** dựa vào kết quả xác thực từ **OpenID Provider** đã được tin cậy. Để an toàn, RP phải thiết lập **issuer/client/redirect trust** rõ ràng, dùng luồng phù hợp như **Authorization Code + PKCE**, kiểm tra chặt **state, nonce, ID token, issuer, audience, chữ ký và thời hạn**, đồng thời liên kết tài khoản bằng **issuer + sub** thay vì email đơn thuần.

Trong vòng đời **Joiner–Mover–Leaver**, OIDC/SSO hỗ trợ xác thực, còn **HRIS/identity proofing** xác lập chủ thể và quan hệ nghiệp vụ, **SCIM/API/JIT có kiểm soát** quản lý tài khoản, **RBAC/ABAC** quyết định quyền, **audit và reconciliation** kiểm tra thực thi. Khi người dùng đổi vai trò hoặc nghỉ việc, phải xử lý **entitlement, local account, token và session** theo khả năng thực tế; **IdP logout hoặc disabled không tự chứng minh mọi ứng dụng đã mất quyền truy cập**. Danh tính dịch vụ và workload federation cần quy tắc issuer/audience/subject, owner và vòng đời riêng.
