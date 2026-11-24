# First-party consent — Sự chấp thuận với ứng dụng nội bộ/chính chủ

## 1. First-party consent là gì và tại sao dễ hiểu sai?

Trong chương **Consent** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, bài **First-party consent** xem xét việc một tổ chức phát hành access token cho **client do chính tổ chức đó sở hữu hoặc kiểm soát**. Ví dụ, công ty vận hành cả ứng dụng `employee-portal`, authorization server `https://auth.example.test` và resource server `hr-api`. Khi nhân viên Alice đăng nhập vào portal, tổ chức có thể xem đây là luồng **first-party** và cho phép AS xử lý authorization theo chính sách đã phê duyệt, không nhất thiết hiện màn hình “Bạn có cho phép ứng dụng truy cập dữ liệu của mình?” ở **mọi** lần đăng nhập.

Tuy nhiên, ba mệnh đề sau **không tương đương**:

1. **First-party client:** một ứng dụng thuộc hoặc được bên quản trị tài nguyên/AS kiểm soát trong ngữ cảnh tin cậy cụ thể.
2. **Pre-authorized client:** AS có quyết định chính sách đã thiết lập, cho phép client xin **một bộ quyền được giới hạn** mà không cần một consent screen tương tác mới.
3. **Consent của end-user:** người dùng hoặc resource owner chấp thuận một phạm vi truy cập theo một cơ chế hợp lệ; có thể được thu thập từ trước, hoặc không cần màn hình OAuth consent riêng vì cơ sở cấp quyền/chính sách khác được áp dụng.

Một ứng dụng được dán nhãn `first-party` **không tự động có quyền** lấy tất cả scopes, thay mặt mọi user, truy cập mọi tenant hoặc nhận refresh token vô hạn. Việc không hiện OAuth consent screen **không chứng minh** đã đáp ứng mọi yêu cầu về quyền riêng tư, thông báo xử lý dữ liệu hoặc sự chấp thuận theo pháp luật áp dụng.

> **Nguyên tắc trung tâm:** First-party là một thuộc tính **của quan hệ tin cậy/quản trị**, không phải OAuth 2.0 grant type, scope đặc biệt hay quyền vượt mọi chính sách. AS có thể bỏ bước xin lại consent qua UI cho **client đã được phê duyệt, scopes đã được phép và ngữ cảnh phù hợp**, nhưng vẫn phải xác thực principal và thực thi client/resource/tenant policy; RS phải phân quyền độc lập.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Xác định **ai được phép gọi client là first-party** và cách quản trị registered client.
- Phân biệt **user authentication**, **OAuth authorization/consent**, **consent UI**, **admin pre-authorization** và **quyền riêng tư**.
- Thiết kế flow **Authorization Code + PKCE** cho portal/BFF/native first-party mà không biến “trusted client” thành quyền admin.
- Đánh giá khi nào nên cho **silent/pre-authorized scope**, khi nào cần **consent mới, step-up hoặc explicit approval**.
- Tách OIDC `openid`/`profile`/`offline_access`, OAuth API scopes và audience của resource server.
- Quản lý consent lifecycle, refresh-token rotation, revocation và quyền của user thay đổi.
- Triển khai chính sách trong Java/Spring Authorization Server và kiểm thử các đường privilege escalation.

Các tên miền `example.test`, scope, client ID và token trong bài đều là **dữ liệu giả định**. Không sử dụng chúng làm production endpoint/credential.

## 2. Các vai trò OAuth và ý nghĩa “chính chủ”

OAuth 2.0 xác định **resource owner**, **client**, **authorization server (AS)** và **resource server (RS)**. First-party nói về mối quan hệ quản trị các thành phần này, **không hợp nhất** chúng thành một vai trò.

| Vai trò | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Resource Owner (RO)** | Alice — người có quyền đối với dữ liệu nhân sự của mình | Cho phép ủy quyền trong những trường hợp cần, không thể tự cấp quyền vượt chính sách |
| **Client** | `employee-portal` — web app của công ty | Yêu cầu scopes, dẫn user đi xác thực, nhận token theo grant đã đăng ký |
| **AS / OP** | `https://auth.example.test` | Xác thực user khi cần; kiểm tra client registration, grant, scope, audience, consent/policy; cấp token |
| **RS** | `hr-api` | Xác minh access token, audience, scope và quyền đọc/sửa từng bản ghi |

Ví dụ:

~~~text
Client:          employee-portal
Owned by:        Example Company, same approved operating unit
Issuer/AS:       https://auth.example.test
Resource:        hr-api
Requested scope: profile.read
Registered scope: profile.read
User context:    Alice, tenant=company-a
Granted scope:   profile.read
Audience:        hr-api
~~~

Nhân viên Alice có thể sử dụng portal để xem **hồ sơ của chính mình** mà không gặp thêm consent screen mỗi lần. Điều này không cho Alice xem hồ sơ Bob, cũng không cho portal scope `payroll.admin` chỉ vì portal thuộc cùng công ty.

### 2.1. First-party là mối quan hệ, không là biến `trusted=true` do client gửi

Một AS có thể nhận nhiều OAuth clients: ứng dụng nội bộ, ứng dụng do đối tác phát triển, plugin của người dùng, mobile app phát hành ra công chúng. Để tin một client là first-party, cần có **client registration và nguồn quản trị đáng tin**:

- Chủ sở hữu kỹ thuật/nghiệp vụ được phê duyệt.
- Đúng môi trường và tổ chức/tenant được phép hoạt động.
- Redirect URIs, origins, client authentication và grant types được quản lý.
- Scope/resource allowlist và mức quyền nhạy cảm được duyệt.
- Quy trình kiểm tra bản phát hành, secret/key lifecycle, access reviews và audit.

**Không** tin `first_party=true` từ query parameter, HTTP header, `client_id` dễ đoán hay `Referer`. Cùng sở hữu một domain không đủ nếu attacker có thể self-register client, chiếm subdomain hoặc lạm dụng redirect.

### 2.2. Cùng công ty chưa chắc cùng ranh giới tin cậy

Đặc biệt trong hệ thống multi-tenant hoặc tập đoàn:

~~~text
Company owns:
  employee-portal  → HR employee self-service
  payroll-admin    → Payroll operations
  sales-dashboard  → CRM sales data
~~~

Cả ba là “first-party” theo pháp nhân, nhưng **không có cùng quyền**. Portal chỉ cần `hr.profile.read`; không có lý do cấp sẵn `payroll.export` hoặc `crm.customers.write`. User thuộc tenant A cũng không được truy cập tenant B chỉ vì cùng nền tảng AS.

Hệ thống nên đánh giá **first-party theo client registration + resource + scope + tenant + mục đích**, thay vì một cờ tin cậy toàn cục.

### 2.3. First-party cũng có thể là public client

Ứng dụng mobile chính thức của công ty là **first-party về quyền sở hữu**, nhưng thường vẫn là **public OAuth client** vì secret nhúng trong binary có thể bị trích xuất. Public vs confidential liên quan **khả năng giữ credential**, không liên quan việc tổ chức tự viết app.

| Client | First-party? | OAuth client type | Hàm ý |
| --- | --- | --- | --- |
| BFF nội bộ do công ty vận hành | Có theo chính sách | Confidential nếu thực sự giữ secret/private key | Authorization Code + PKCE, client auth và server-side token store |
| Mobile app chính thức | Có theo chính sách | Thường public | Authorization Code + PKCE qua external browser, không tin secret nhúng |
| SPA chính thức | Có theo chính sách | Public ở phần JS/browser | PKCE, chống XSS, RT policy; cân nhắc BFF |
| App đối tác đã được phê duyệt | Không nhất thiết first-party | Public hoặc confidential | Consent/admin policy tùy registration, quyền hẹp |
| Batch job nội bộ | Có theo chính sách | Confidential workload identity | Client Credentials cho quyền **service**, không giả làm user |

First-party **không phải** cách xác thực client; nó cũng không tự chứng minh một public app trên thiết bị là bản phân phối chính hãng.

## 3. Phân biệt bốn loại “đồng ý” và cơ sở cấp quyền

Trong trao đổi kỹ thuật, từ *consent* thường bị dùng cho nhiều sự kiện khác nhau.

| Khái niệm | Câu hỏi thực sự | Ai đánh giá? | Có nhất thiết là OAuth consent screen? |
| --- | --- | --- | --- |
| **User authentication** | Ai vừa đăng nhập, với mức bảo đảm nào? | AS/OP và RP xác minh kết quả OIDC | **Không** |
| **OAuth authorization/consent** | Client được phép truy cập phạm vi tài nguyên nào thay RO? | AS, RO/admin và chính sách đã phê duyệt | **Không bắt buộc hiển thị mỗi lần** |
| **Admin pre-authorization** | Tổ chức đã cho client dùng những scopes nào trong tenant nào? | Administrator/IAM policy | Không nhất thiết, tùy mô hình |
| **Privacy/legal consent hoặc notice** | Xử lý dữ liệu cá nhân với mục đích nào, trên cơ sở nào, có rút được không? | Chính sách tổ chức và nghĩa vụ pháp luật áp dụng | **Không thể suy ra từ việc ẩn hoặc hiện OAuth screen** |

RFC 6749 quy định quá trình AS có thể cần resource owner approval, nhưng **không chuẩn hóa** một consent UI phải hiện mỗi lần. AS có thể áp chính sách cấp quyền cho client nội bộ, lưu approval đã có hoặc cho phép admin quyết định theo thẩm quyền. Dù vậy, không được suy “bỏ màn hình OAuth consent = được phép bỏ thông báo/đồng ý xử lý dữ liệu theo pháp luật”.

### 3.1. “Skip consent” có nghĩa hẹp

Trong một AS product, cờ `requireAuthorizationConsent(false)` thường diễn giải là **không buộc user xác nhận màn hình OAuth consent** cho authorization request phù hợp. Nó **không** có nghĩa:

- Bỏ user authentication và OIDC ID-token validation.
- Bỏ client registration, `redirect_uri` hoặc PKCE.
- Cấp mọi scope client tự xin, kể cả quyền chưa được duyệt.
- Bỏ expected audience khi phát token.
- Bỏ yêu cầu quyền sở hữu object/tenant ở RS.
- Bỏ các quy tắc `offline_access` hoặc rủi ro dữ liệu nhạy cảm.

### 3.2. User đã sử dụng app cũng không phải bằng chứng bất biến

Một ứng dụng first-party có thể không cần hỏi “Cho phép app truy cập dữ liệu của chính nó?” cho tác vụ self-service rất rõ. Nhưng khi app **đổi mục đích sử dụng dữ liệu**, xin scope mới, truy cập ứng dụng/bên nhận khác, thực hiện chia sẻ nhạy cảm hoặc mở offline access, cần **đánh giá lại** thông báo, consent và bảo vệ tương xứng.

Không biến thao tác đăng nhập `openid` thành chấp thuận vĩnh viễn đối với mọi xử lý dữ liệu không liên quan đến login.

## 4. Mô hình tin cậy: AS quyết định grant, RS quyết định quyền tài nguyên

Luồng first-party an toàn vẫn giữ ranh giới:

~~~mermaid
flowchart LR
    U["Alice / Resource Owner"] -->|"Authentication tại OP; policy/consent khi cần"| AS["AS / OpenID Provider"]
    C["employee-portal / First-party client"] -->|"Scope + resource + PKCE"| AS
    P["Client registration + approved policy"] -->|"Allowlist"| AS
    AS -->|"Access token aud=hr-api; scope=hr.profile.read"| C
    C -->|"Bearer AT"| RS["hr-api / Resource Server"]
    RS -->|"Scope + object/tenant ACL"| D["Hồ sơ Alice được phép xem"]
    RS -.->|"JWKS/introspection tin cậy"| AS
~~~

Client first-party có thể được **pre-authorized cho `hr.profile.read`**, nhưng AS vẫn phải kiểm tra Alice là subject hợp lệ và có thể dùng grant đó. RS tiếp tục xác minh Alice có quyền đọc **record cụ thể**.

### 4.1. Các tập quyền không được xem là đồng nhất

Gọi:

- \(R_c\): scopes/resource mà **client registration** cho phép.
- \(R_u\): quyền của **resource owner/principal** theo tenant/domain policy.
- \(R_p\): phạm vi mà **AS policy hoặc approval** cho phép trong giao dịch.
- \(R_q\): phạm vi client **yêu cầu**.
- \(R_g\): granted scope/resource hợp lệ trong token.

Một phép chặn trên tư duy:

\[
R_g \subseteq R_q \cap R_c \cap R_p
\]

và quyền ứng dụng thực hiện ở RS còn phải nằm trong \(R_u\) cùng các chính sách đối tượng/thao tác. Đây là **mô hình tư duy**, không phải công thức RFC buộc tất cả AS xử lý scope giống nhau; AS có thể từ chối toàn bộ yêu cầu thay vì cấp phần giao. Quan trọng là **không có đường nào chỉ từ requested scope hoặc cờ first-party sang quyền cao hơn chính sách**.

### 4.2. Consent screen không làm thay authorization

Giả sử Alice chấp thuận `hr.profile.read` và `payroll.read` qua UI, nhưng client chỉ được đăng ký `hr.profile.read`. AS không được cấp `payroll.read` chỉ vì có click “Allow”. Ngược lại, một AS bỏ UI cho portal vẫn phải giới hạn đúng scope allowlist; **có/không có màn hình** không phải yếu tố duy nhất quyết định token được cấp.

### 4.3. Cần ràng buộc audience/resource

Một issuer có thể ký token cho cả `hr-api`, `payroll-api`, `crm-api`. Token first-party:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["hr-api"],
  "client_id": "employee-portal",
  "scope": "hr.profile.read",
  "exp": 1893456000
}
~~~

không được `payroll-api` chấp nhận. **Chữ ký đúng và client first-party không thay audience validation.** Với opaque access token, RS cần introspection metadata hoặc resource binding đáng tin để biết token dành cho chính nó; `active=true` cũng không phải quyền universal.

## 5. Khi nào không cần hiện lại consent UI, khi nào phải hỏi?

First-party consent là **quyết định chính sách tùy ngữ cảnh**, không phải một biểu đồ “first-party = skip, third-party = show” bất biến.

| Tình huống | Hướng xử lý thường hợp lý | Vì sao |
| --- | --- | --- |
| Nhân viên dùng portal nội bộ để xem hồ sơ của mình; scope đã được quản trị cho phép | Có thể pre-authorize, **không hiện consent UI mỗi login** | Mục đích rõ, client/scopes/resource/tenant được giới hạn |
| User đăng nhập OIDC `openid` vào ứng dụng do tổ chức vận hành | Có thể thực hiện login theo SSO policy không có màn hình đồng ý OAuth riêng | Authentication khác API authorization; không tự bỏ privacy notice |
| Portal xin thêm `payroll.export` lần đầu | Yêu cầu chính sách/approval rõ, có thể tương tác và step-up | Quyền nhạy cảm mới không nằm trong baseline |
| Client nội bộ yêu cầu `offline_access`/RT dài hạn | Đánh giá OIDC consent/RT policy và cơ sở chấp thuận phù hợp | Offline grant kéo dài khả năng truy cập khi user vắng mặt |
| Client nhận một resource/audience mới | AS phải duyệt audience/resource và client grant, có thể yêu cầu consent mới | Token không được tự chuyển từ `hr-api` sang `payments-api` |
| Đối tác bên ngoài xin dữ liệu user | Consent/admin approval theo product, scope và policy | Độc lập với độ tin cậy của client nội bộ |
| Tổ chức triển khai app mới trong tenant khác | Không kế thừa approval theo tenant A | Tenant boundary và chính sách khác nhau |
| User đã rút quyền/consent | Không silent re-grant để “đỡ phiền” | Quyền của user/admin đã thay đổi |
| Workload chạy theo client credentials | **Không có human OAuth consent UI** trong grant đó | App-only authority khác user delegation |

### 5.1. Consent lần đầu và những lần sau

Một hệ thống có thể ghi nhận rằng client đã được cấp `orders.read` trong tenant A. Ở lần authorization tiếp theo, AS kiểm tra:

~~~text
same trusted issuer?
same registered client and approved owner?
same principal / tenant / organization policy?
requested scopes/resources ⊆ allowed/pre-authorized permissions?
grant/session still active, no revocation?
no required new interaction or step-up?
~~~

Nếu tất cả điều kiện thỏa theo AS policy, việc **không lặp màn hình** có thể là trải nghiệm phù hợp. Nếu app yêu cầu scope mới hoặc principal/tenant khác, không dùng approval cũ không tương ứng.

### 5.2. `prompt=none` không phải lệnh “bỏ consent”

Trong OIDC, `prompt=none` yêu cầu OP xử lý **không có UI tương tác**. Nếu user chưa có session phù hợp, cần consent mới hoặc phải xác thực lại, OP trả lỗi như `login_required`, `consent_required` hoặc `interaction_required` theo ngữ cảnh.

**Không** cho client tự gửi `prompt=none` để vượt policy. Silent flow chỉ thành công khi các điều kiện authorization/consent đã được thỏa mãn từ trước; không thành công thì client chuyển sang flow tương tác hợp lệ, không downgrade sang password grant.

## 6. Authorization Code + PKCE cho first-party portal

Một ví dụ first-party user-delegated flow: nhân viên Alice truy cập `employee-portal` (backend/BFF), đăng nhập tại OP và nhận quyền đọc hồ sơ của chính mình.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant BFF as employee-portal / First-party RP
    participant AS as Authorization Server / OP
    participant RS as hr-api / Resource Server
    U->>BFF: Truy cập trang hồ sơ
    BFF->>BFF: Sinh state, PKCE verifier/challenge, OIDC nonce khi cần
    BFF-->>U: 302 tới /authorize (openid + hr.profile.read)
    U->>AS: Authorization request
    AS->>AS: Xác minh client, redirect, scopes, resource, tenant
    AS->>U: Login/SSO; consent UI nếu chính sách yêu cầu
    AS->>AS: Quyết định grant theo user + pre-authorized policy
    AS-->>U: Redirect code + state
    U->>BFF: Callback code + state
    BFF->>BFF: Verify state/issuer; lấy đúng PKCE verifier
    BFF->>AS: POST /token: code + verifier + client authentication
    AS-->>BFF: ID token + AT (RT chỉ nếu được cấp)
    BFF->>BFF: Verify ID token, tạo session an toàn
    BFF->>RS: GET /profiles/me + AT aud=hr-api
    RS->>RS: Verify token, scope, tenant, ownership
    RS-->>BFF: Hồ sơ Alice được phép
~~~

**Chú ý:** Luồng trên có OIDC RP và API RS. Tùy OP/AS, access token phục vụ `/userinfo` và token dành cho `hr-api` có thể khác nhau. Phải thiết kế **resource/audience issuance** rõ, không mặc định một access token dùng được tại mọi API hoặc UserInfo.

### 6.1. Authorization request

~~~http
GET /oauth2/authorize?response_type=code&client_id=employee-portal&redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20hr.profile.read&state=<random-state>&nonce=<random-nonce>&code_challenge=<s256-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Các tham số là ví dụ:

- `openid`: yêu cầu OIDC authentication; **không** là quyền đọc hồ sơ nhân sự.
- `hr.profile.read`: OAuth API scope theo policy của `hr-api`.
- `state`: ràng buộc callback với authorization transaction/CSRF defense.
- `nonce`: ràng buộc ID token với authentication transaction khi dùng/được yêu cầu.
- `code_challenge` + `S256`: ràng buộc authorization code redemption với PKCE verifier.
- `client_id`, `redirect_uri`: phải khớp registered first-party client.

Nếu AS hỗ trợ Resource Indicators (RFC 8707), RP có thể gửi thêm `resource=https://hr.example.test/`. Resource request vẫn phải qua **client/resource allowlist và user policy**, không tự cấp audience từ URL bất kỳ.

### 6.2. AS quyết định có hiện consent UI không

Giả sử AS lưu chính sách:

~~~text
registeredClient = employee-portal
clientOwner      = company-security-team
authorizationGrantType = authorization_code
trustedIssuer    = https://auth.example.test
approvedResources = [hr-api]
approvedScopes   = [openid, hr.profile.read]
approvedTenants  = [company-a]
consentUiPolicy  = PREAUTHORIZED_FOR_BASELINE
stepUpPolicy     = require on sensitive scope/action
~~~

Nếu Alice thuộc tenant A và request nằm trong baseline, AS có thể xử lý mà không hiện lại consent UI. Nếu request chứa `payroll.export`, policy phải **từ chối hoặc áp quy trình ủy quyền bổ sung**; không đưa scope đó vào token chỉ vì portal đã được gắn nhãn first-party.

### 6.3. Token request vẫn cần PKCE và client binding

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <registered-confidential-client-auth>

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=<original-pkce-verifier>
~~~

Header Basic chỉ minh họa client đã được đăng ký dùng `client_secret_basic`; AS cũng có thể hỗ trợ `private_key_jwt` hoặc mTLS. Đối với **public first-party client** (SPA/native), không dùng client secret nhúng làm bí mật; client phải tuân thủ public-client PKCE và redirect requirements.

Việc pre-authorize scope **không biến authorization code thành token dùng nhiều lần**, không cho phép bỏ redirect/client binding hay tái sử dụng verifier. Single-use code phải được AS tiêu thụ nguyên tử.

### 6.4. Token response không phải phiếu miễn quyền

~~~json
{
  "access_token": "<token-for-hr-api>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "hr.profile.read",
  "id_token": "<oidc-id-token-for-employee-portal>"
}
~~~

Nếu AT là JWT:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["hr-api"],
  "client_id": "employee-portal",
  "scope": "hr.profile.read",
  "exp": 1893456000
}
~~~

Đây là payload minh họa, **không phải JWT có chữ ký thật**; những timestamp chỉ để học. `hr-api` phải xác minh token profile, chữ ký/issuer, audience `hr-api`, thời hạn, scope và object/tenant ACL. Một AT đúng `hr.profile.read` cũng không cho Alice xem hồ sơ của Bob.

## 7. First-party consent theo loại client

### 7.1. Backend/BFF confidential client

Đây là kiến trúc phù hợp khi ứng dụng first-party có backend đáng tin và muốn **giữ access/refresh token ngoài JavaScript browser**. BFF:

1. Tạo PKCE transaction và giữ `code_verifier` phía server.
2. Dẫn browser đến OP/AS và nhận callback đúng redirect.
3. Đổi code tại token endpoint bằng client authentication đã đăng ký.
4. Lưu AT/RT trong protected server-side token store, browser dùng application session cookie.
5. Gọi API bằng AT dành cho đúng audience và scope, kiểm tra domain authorization.

Không mặc định bỏ consent UI chỉ vì BFF có thể giữ secret. Consent là chính sách client/user/resource; confidential authentication chỉ chứng minh **client**.

### 7.2. SPA first-party vẫn là public client

SPA của cùng công ty có thể được pre-authorized baseline scopes, nhưng:

- `client_secret` hardcode trong JS không phải bí mật.
- Authorization Code + PKCE và kiểm tra `state`/issuer/nonce (OIDC) vẫn cần.
- JavaScript độc hại do XSS có thể lấy token/verifier hoặc gửi request trong phiên.
- RT cho browser cần chính sách bảo vệ, rotation/sender constraint, expiry/revocation; cân nhắc BFF nếu rủi ro cao.
- AS không được chỉ dựa vào `Origin` hay CORS để cấp quyền API: non-browser callers không bị browser CORS enforcement.

Consent UI có thể ít xuất hiện, nhưng **security requirements đối với public client không hề giảm**.

### 7.3. Mobile/native first-party

Ứng dụng iOS/Android chính thức thường dùng **Authorization Code + PKCE qua external user-agent** theo RFC 8252, không nhúng static secret hoặc embedded webview thu mật khẩu. Vì app chạy trên thiết bị của người dùng, các rủi ro như app giả, redirect URI hijack, backup/token extraction vẫn tồn tại.

Nếu AS chọn bỏ consent UI cho `mobile-employee-app`, vẫn phải giới hạn scopes/redirects/issuer, bảo vệ credential và cho user biết quyền truy cập nhạy cảm theo policy. App ownership khác **device attestation**; không suy app luôn là phiên bản chính hãng chỉ từ `client_id`.

### 7.4. Machine-to-machine first-party

Job `inventory-sync` dùng **Client Credentials** để gọi `inventory-api` bằng quyền **của service**. Không có Alice đang consent tại browser trong grant này. AS phải kiểm tra workload/client authentication, scopes và audience; RS kiểm tra service principal/domain policy.

**Sai lầm:** scheduler tự lấy `client_credentials` token `users.admin` rồi đọc mọi dữ liệu do một user yêu cầu, với lập luận “service cùng công ty là first-party”. Nếu thao tác **thay mặt user**, phải kiểm tra quyền user/actor hoặc dùng delegation/token exchange theo policy, không nâng quyền bằng app-only token.

### 7.5. Đối tác tích hợp không trở thành first-party chỉ vì dùng SSO chung

Một partner app có thể đăng nhập qua cùng OP, cùng tenant hoặc cùng tên miền liên kết, nhưng vẫn do pháp nhân khác quản trị và có data handling khác. **Tách client registrations, owners, scopes, consent policies và audit**; không dùng thuộc tính “đăng nhập được bằng SSO công ty” làm tiêu chí duy nhất để bỏ consent cho partner.

## 8. Scope, consent, audience và domain permission phải tách lớp

Xét `employee-portal` yêu cầu:

~~~text
requested: openid hr.profile.read hr.profile.write payroll.export
~~~

Trong chính sách:

~~~text
registered client allowed: openid hr.profile.read hr.profile.write
pre-authorized baseline:   openid hr.profile.read
user's allowed actions:    view own profile, edit own phone
sensitive operation:       payroll.export requires special admin policy
resource binding:          hr-api, not payroll-api
~~~

AS không được cấp `payroll.export`. Đối với `hr.profile.write`, AS có thể yêu cầu thêm approval/step-up/interaction hoặc từ chối theo policy. Đối với `hr.profile.read`, AS có thể dùng pre-authorization. RS vẫn kiểm tra **profile ID** và **trường được sửa**, không chỉ xem token scope.

### 8.1. Bảng quyết định cấp scope

| Request | Client allowlist? | Pre-authorized? | User/domain? | Kết luận |
| --- | --- | --- | --- | --- |
| `openid` | Có | Có thể | User authentication theo OIDC | Login được nếu OP/flow hợp lệ |
| `hr.profile.read` | Có | Có | Alice chỉ được đọc hồ sơ mình | AT có thể được cấp, RS check object |
| `hr.profile.write` | Có | Không baseline | User được sửa một số trường | AS có thể cần approval mới, RS chặn fields không được sửa |
| `payroll.export` | Không | Không | Alice không là payroll admin | Không được cấp |
| `crm.customers.read` ở audience khác | Không | Không | Không thuộc grant | Không được cấp |
| `offline_access` không được đăng ký | Không | Không | Consent chưa có | Không được tự cấp RT |

### 8.2. API scopes không phải OIDC scopes

`openid` yêu cầu xác thực user; `profile`/`email` xin nhóm claims; `hr.profile.read` là quyền API theo hợp đồng tổ chức. Chỉ vì một first-party RP đã có `openid profile` không có nghĩa nó có scope nghiệp vụ `hr.profile.read`.

Tương tự `email_verified=true` hoặc claim `groups` trong ID token **không** tự cấp quyền đọc bảng lương. Cần ánh xạ roles/tenant từ nguồn được xác minh và kiểm tra object-level authorization.

### 8.3. Audience độc lập với mức độ first-party

Một token `aud=hr-api` không được gửi tới `payroll-api`. Bỏ audience validation trong hệ thống “toàn API nội bộ” có thể gây **cross-resource token substitution/confused deputy**. Nếu backend cần gọi downstream thay user, thiết kế token exchange/OBO (RFC 8693) với subject/actor/resource policy, hoặc app-only grant riêng cho tác vụ hệ thống đã được phép.

### 8.4. Multi-tenant phải chặn cross-tenant grant inheritance

Một partner vận hành multi-tenant platform có thể đăng ký client cùng ID (hoặc các registrations tương tự) tại tenant A và tenant B. Consent/approval tại A **không tự áp cho B**:

~~~text
tenant=company-a, principal=alice, client=portal, scope=hr.read
→ Không tương đương
tenant=company-b, principal=bob, client=portal, scope=hr.read
~~~

Khóa approval và policy cần phân biệt tổ chức, client registration, principal hoặc service context, resource, scopes và policy version. Không ghi một cờ `consent=true` toàn cục theo client_id.

## 9. OpenID Connect `openid`, claims và offline access với first-party

First-party OIDC login có thể yêu cầu:

~~~text
scope=openid profile email
~~~

Trong đó:

- `openid` là scope bắt buộc của **OIDC Authentication Request**.
- `profile` và `email` xin những nhóm end-user claims; OP có thể không cung cấp tất cả.
- `address`, `phone` có thể xin thêm data nhưng cần mục đích/consent/privacy policy phù hợp.
- `offline_access` xin khả năng truy cập khi end-user không hiện diện, thường có liên hệ với refresh token và quy tắc consent riêng.

### 9.1. ID token dành cho RP, AT dành cho resource server

ID token thường có `aud=employee-portal`, còn AT phục vụ `hr-api` có `aud=hr-api`. Một RS không được nhận ID token làm API credential chỉ vì cả hai do cùng OP ký.

OP có thể trả user claims ở ID token hoặc qua **UserInfo Endpoint** theo flow/policy. Nếu RP lấy UserInfo, nó phải xác minh `sub` trong UserInfo Response **khớp chính xác ID token `sub`**. Không dùng email làm khóa định danh bất biến; nên dùng cặp **`(iss, sub)`** khi mapping external identity.

### 9.2. First-party `offline_access` cần đánh giá riêng

Trong OIDC Core, `offline_access` không mặc nhiên được cấp chỉ vì app thuộc cùng tổ chức. OP phải có cơ sở consent phù hợp cho offline access và áp quy tắc request/response type của OIDC; trong các điều kiện thông thường, `prompt=consent` được sử dụng khi xin offline access nếu không có điều kiện khác cho phép xử lý yêu cầu. **Không được hiểu pre-authorized baseline scopes là giấy phép chung để cấp RT vô hạn cho mọi first-party client.**

Ví dụ:

~~~http
GET /oauth2/authorize?response_type=code&client_id=employee-portal&scope=openid%20offline_access%20hr.profile.read&prompt=consent&state=<random-state>&code_challenge=<s256-challenge>&code_challenge_method=S256&redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback HTTP/1.1
Host: auth.example.test
~~~

`prompt=consent` là yêu cầu tương tác; **không chứng minh** user đã approve. Client registration, OP policy, consent, RT rotation/sender constraint và TTL còn quyết định RT có được cấp hay không. Hành động offline như đồng bộ hồ sơ phải dừng theo revocation/user disable policy khi yêu cầu.

### 9.3. Không tự nâng scope khi refresh

RT được cấp dưới grant `hr.profile.read` không cho phép client tự gửi refresh request xin `payroll.export`. AS phải giới hạn scope trong grant và client/user policy; refresh-token rotation/reuse detection và sender constraint (khi có) giải quyết **credential replay**, không tự thêm quyền.

### 9.4. Consent cho contact claims không thay quyền xử lý PII

Ví dụ RP xin `openid email` để hiển thị địa chỉ email. Việc `email` xuất hiện và `email_verified=true` không tự cho phép công ty chia sẻ nó cho bên thứ ba, gửi quảng cáo hay giữ vô hạn. Cần policy về **mục đích, tối thiểu hóa, retention, thông báo/consent phù hợp và quyền rút lại**, độc lập với kỹ thuật scope issuance.

## 10. Mô hình policy và consent record có thể kiểm toán

Không nên lưu duy nhất:

~~~json
{"client_id":"employee-portal","consent":true}
~~~

Record này không cho biết ai đã quyết định, phạm vi nào, tenant và resource nào, có hết hạn hoặc bị rút quyền hay không. Với first-party, **cơ sở pre-authorization** cần có nguồn quản trị và phiên bản; với user consent, dữ liệu approval cần gắn vào principal/grant đúng ngữ cảnh.

### 10.1. Policy baseline do tổ chức quản trị

Ví dụ **policy nội bộ** (không phải định dạng OAuth hoặc Spring chuẩn):

~~~yaml
policy_id: employee-portal-baseline
policy_version: 7
client_registration_id: employee-portal-prod
client_owner: workforce-identity-team
classification: FIRST_PARTY_APPROVED
eligible_tenants: [company-a]
allowed_grants: [authorization_code]
allowed_resources: [hr-api]
preauthorized_scopes: [openid, hr.profile.read]
requires_interaction_scopes: [hr.profile.write]
blocked_scopes: [payroll.export]
offline_access:
  permitted: false
review_status: APPROVED
~~~

Đây là dữ liệu minh họa: các quyết định thật phải được thực thi bởi **AS policy engine, client registration và domain authorization**. `classification` chỉ hợp lệ nếu được cập nhật qua luồng quản trị có quyền, không phải từ query parameter hay header do client gửi.

### 10.2. Consent record với user/admin

~~~json
{
  "consent_id": "approval-894",
  "issuer": "https://auth.example.test",
  "registered_client_id": "partner-reporting-app",
  "subject": "alice",
  "tenant_id": "company-a",
  "resources": ["hr-api"],
  "granted_scopes": ["hr.profile.read"],
  "approval_source": "USER_INTERACTIVE",
  "policy_version": 7,
  "approved_at": "2026-11-23T02:00:00Z",
  "expires_at": "2026-12-23T02:00:00Z",
  "revoked_at": null
}
~~~

`approval_source` có thể biểu diễn `USER_INTERACTIVE`, `ADMIN_POLICY` hoặc `PREAUTHORIZED_FIRST_PARTY` tùy mô hình IAM, nhưng **không gán nhãn “user consent” giả** cho quyết định do admin hoặc policy đưa ra. Việc giữ audit phải đáp ứng yêu cầu bảo vệ dữ liệu cá nhân.

### 10.3. Ranh giới cache và version

Khóa logic đánh giá có thể bao gồm:

~~~text
issuer
+ registered_client_id
+ principal_or_service_context
+ tenant_id
+ audience/resource
+ granted_scopes
+ policy_version
~~~

Đây là **gợi ý thiết kế**, không phải khóa bảng cố định. Vấn đề cần ngăn là việc một approval của Alice tại tenant A bị dùng cho Bob ở tenant B hoặc cho một API khác. Khi policy version thay đổi, quyết định cache cần được invalidate/đánh giá lại theo quy tắc đã xác định.

### 10.4. Audit không làm lộ credential

~~~text
event=oauth_authorization_decision
decision=ALLOW
source=PREAUTHORIZED_FIRST_PARTY
registered_client=employee-portal-prod
principal_ref=<non-secret-reference>
tenant=company-a
resource=hr-api
granted_scope=hr.profile.read
policy_version=7
interaction_required=false
correlation_id=<opaque-correlation-id>
~~~

Không log raw access token, refresh token, authorization code, PKCE verifier, client secret, password hoặc toàn bộ UserInfo PII. Audit cần trả lời **vì sao grant được cấp**, không trở thành kho chứa credential.

## 11. Consent lifecycle: thay đổi policy, rút quyền và thu hồi token

First-party pre-authorization và user consent là **những quyết định có vòng đời**, không phải cờ `true` vĩnh viễn.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: New client/scope/resource request
    PENDING --> APPROVED: User/admin/policy authorization hợp lệ
    PENDING --> DENIED: User từ chối hoặc policy không cho phép
    APPROVED --> REEVALUATE: Scope/tenant/owner/risk thay đổi
    REEVALUATE --> APPROVED: Điều kiện vẫn thỏa
    REEVALUATE --> DENIED: Điều kiện không còn thỏa
    APPROVED --> REVOKED: Approval bị rút
    APPROVED --> EXPIRED: Approval hết hạn theo policy
    DENIED --> [*]
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Sơ đồ chỉ mô tả **application/AS policy state**, không phải cấu trúc trạng thái bắt buộc trong RFC. Nhiều hệ thống lưu registered client policy, OAuth consent, user session, token grant và AT/RT trong các kho dữ liệu khác nhau.

### 11.1. Trước khi silent/pre-authorized issuance

~~~text
require trusted issuer and registered client owner
require client grant type / redirect / PKCE / authentication
require requested scopes/resources within approved policy
require correct principal, tenant and user account status
require grant not revoked and policy version still current
require no mandatory interaction / consent / step-up outstanding

if requirements pass:
    MAY skip interactive OAuth consent UI
    issue AT/ID token only within approved scope/audience
else:
    DENY or initiate policy-approved interactive authorization
~~~

Một cờ UI không thay thế các điều kiện này. Không chuyển yêu cầu `payroll.admin` thành “first-party baseline” vì client tự thêm scope mới.

### 11.2. User rút approval

Trong những luồng mà user có quyền rút grant:

1. Giao diện cho user xem **client, scopes/resources và thời điểm cấp**, phù hợp data privacy policy.
2. AS/IAM đánh dấu grant/consent bị rút và chặn phát hành token mới từ grant không còn hợp lệ.
3. Thu hồi RT hoặc toàn bộ grant bằng RFC 7009/AS revocation mechanism theo khả năng.
4. Xử lý AT đang sống theo SLA; thông báo ý nghĩa thực tế của việc rút quyền.
5. Invalidate approval/token caches, ghi audit và phát hiện client tiếp tục thử silent re-grant.

Nếu baseline first-party là **mandatory organizational policy**, user có thể không có một OAuth user-consent grant độc lập để rút. Hệ thống cần mô tả trung thực quyền và cách quản lý/giải quyết khiếu nại theo quy định, **không thiết kế nút “Rút” giả rồi tự cấp lại ngay**.

### 11.3. Logout khác consent withdrawal

| Sự kiện | Tác động thường có | Không tự bảo đảm |
| --- | --- | --- |
| **RP logout** | Xóa local app session/token cache | OP session/RT/AT đều bị thu hồi |
| **OP logout** | Kết thúc phiên xác thực OP theo profile | Mọi OAuth consent/grant mất hiệu lực |
| **Withdraw consent/grant** | AS không cấp token mới theo grant bị rút | JWT AT còn hạn lập tức bị RS chặn |
| **Revoke RT** | RT không dùng để xin AT mới được | AT đang sống tự động hết hạn |
| **Disable user/client** | Nguồn principal hoặc registration không còn hợp lệ | RS kiểm tra trạng thái tức thì khi chỉ verify JWT offline |

### 11.4. JWT và opaque token khi đổi quyền

Với **JWT AT** xác minh offline, AS thu hồi consent tại `T1` không nhất thiết làm token đã cấp tại `T0` bị chặn trước `exp`. RS cần denylist/state-check hoặc domain ACL nếu SLA yêu cầu thu hồi tức thì.

Với **opaque AT**, RS introspect ở AS có thể nhận `active=false`, nhưng cache `active=true` còn gây trễ. Khi introspection timeout, không được fail open cho token chưa được xác minh. Thiết kế freshness/cache theo mức độ nhạy cảm và SLA.

### 11.5. Refresh token sau first-party consent

Không mặc định cấp RT vô hạn chỉ vì first-party. Nếu AS cấp RT, áp lifetime, rotation/sender constraint, reuse detection, thu hồi, user/client/tenant policy khi refresh và single-flight tránh race đa tab/Pod. **Consent withdrawal hoặc client policy change không được bị bỏ qua chỉ vì RT còn đúng về mặt mã hóa.**

## 12. Threat model: khi first-party trở thành lối tắt tăng quyền

### 12.1. Giả mạo thuộc tính first-party

~~~http
GET /authorize?client_id=unknown-app&scope=payroll.admin&first_party=true HTTP/1.1
Host: auth.example.test
~~~

Nếu AS tin `first_party=true` do caller cung cấp, attacker có thể bypass UI/approval. Chỉ tin **server-side registered client classification** đã được phê duyệt. Cùng tên hiển thị hoặc email đăng ký không đủ để một client trở thành first-party.

### 12.2. Dynamic client registration và tên gần giống

Attacker self-register client tên `Employee Portal` với redirect URL attacker. Nếu policy first-party khớp theo display name thay vì immutable registration/owner, AS có thể preapprove scopes cho client giả.

Phòng vệ: tách **quyền tạo trusted first-party registrations** khỏi self-service registrations, xác minh domain/owner, exact redirect allowlist, client authentication, scopes, resource grants và review theo phiên bản.

### 12.3. Redirect URI takeover và code interception

Một first-party client dùng wildcard redirect `https://*.example.test/callback`; attacker chiếm subdomain cũ và lấy code. Nếu vì trusted client mà tắt PKCE, nguy cơ càng tăng. Dùng strict redirect registration, Authorization Code + PKCE S256, `state`/issuer binding, client auth khi confidential và TLS.

### 12.4. Silent consent laundering

Ứng dụng baseline `hr.profile.read` trong bản cập nhật âm thầm xin `payroll.export`. Nếu AS chỉ thấy “client first-party” rồi cấp, user đã bị mở rộng quyền mà không có review hay approval. Phòng vệ: allowlist theo **scope/resource/policy version**, sensitive scopes yêu cầu review/interaction hoặc bị từ chối.

### 12.5. Cross-tenant grant reuse

Approval tại tenant A không được dùng cho tenant B, kể cả client dùng cùng `client_id`. Consent cache phải phân biệt tenant, principal, issuer, resource, scopes và registration; RS phải kiểm tra object tenant từ dữ liệu đáng tin.

### 12.6. Cross-resource confused deputy

Token `aud=hr-api` được chuyển sang `payroll-api` vì cả hai dùng cùng issuer/JWKS. Nếu payroll chỉ verify signature, token substitution có thể dẫn đến truy cập trái quyền. Mỗi RS kiểm tra expected `aud` và domain policy. Khi cần downstream delegation, dùng token exchange/OBO với actor/subject policy được AS phê duyệt.

### 12.7. App-only token thay user authorization

Backend có `payments.admin` từ Client Credentials và dùng nó để refund do Alice yêu cầu, bất kể Alice không có quyền. Đây là **confused deputy**: app-only authority bị dùng thay delegated user permission. Phải kiểm tra domain rights của Alice hoặc dùng grant delegation phù hợp, không fallback sang service token quyền cao.

### 12.8. Consent UI giả và quyền riêng tư

Một ứng dụng quảng bá “first-party nên không cần consent” nhưng chia sẻ PII với đối tác không được nêu trong mục đích ban đầu. OAuth UI suppression **không thay** privacy assessment, notice, data minimization, retention và quyền user theo pháp luật áp dụng. Không tự tuyên bố legal compliance từ một cờ OAuth.

### 12.9. Bearer token theft dù consent đã đúng

Token có thể lộ qua XSS/browser storage, APM, proxy logs hoặc redirect; attacker có thể replay AT còn hạn. Dùng TLS, hạn chế log, server-side token store/BFF khi thích hợp, AT TTL, RT rotation/revocation và DPoP/mTLS binding khi risk yêu cầu. PKCE bảo vệ **code redemption**, không chặn mọi replay sau issuance.

### 12.10. Denied consent không được đổi grant để lách

AS trả `access_denied` hoặc `consent_required`; client chuyển sang `client_credentials` quyền admin để vẫn đọc dữ liệu user. Đây là việc **đổi nguồn quyền để bypass quyết định**, không phải error recovery hợp lệ. Client phải từ chối hoặc bắt đầu authorization flow được phê duyệt.

## 13. Java/Spring Authorization Server: giới hạn của `requireAuthorizationConsent(false)`

Spring Authorization Server cung cấp registered client settings để kiểm soát có yêu cầu **authorization consent UI** hay không. Ví dụ sau minh họa **web backend first-party** đã được IAM owner phê duyệt với baseline `openid` + `hr.profile.read`. Không sử dụng nó như một cơ chế gắn trusted flag cho mọi client hoặc mọi resource.

### 13.1. RegisteredClient first-party

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

class EmployeePortalClientRegistration {
    static RegisteredClient create(
            PasswordEncoder passwordEncoder,
            String secretFromProtectedStore) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
                .clientId("employee-portal")
                .clientSecret(
                        passwordEncoder.encode(secretFromProtectedStore))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri(
                        "https://portal.example.test/login/oauth2/code/company")
                .scope(OidcScopes.OPENID)
                .scope("hr.profile.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(false)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .refreshTokenTimeToLive(Duration.ofHours(8))
                        .reuseRefreshTokens(false)
                        .build())
                .build();
    }
}
~~~

Đây là snippet minh họa API **Spring Authorization Server các phiên bản hỗ trợ**; để chạy cần dependency/import và AS configuration thực tế. Những TTL 5 phút/8 giờ là **giá trị giả định để giảng giải**, không phải khuyến nghị cố định cho mọi tổ chức. `secretFromProtectedStore` là secret runtime được inject từ secret manager; **không hardcode hoặc in vào log**.

**Đọc đúng ý nghĩa các settings:**

| Cấu hình | Tác dụng | Không có nghĩa |
| --- | --- | --- |
| `requireProofKey(true)` | Yêu cầu PKCE trong Authorization Code flow theo hỗ trợ của AS | Bỏ client authentication hoặc redirect validation |
| `requireAuthorizationConsent(false)` | Không ép UI user consent cho registered client này trong cơ chế chuẩn tương ứng | Client có mọi scope/resource/tenant quyền |
| `scope(OidcScopes.OPENID)` | Cho đăng ký xin OIDC authentication scope | Có thể dùng ID token làm AT tại `hr-api` |
| `scope("hr.profile.read")` | Registration cho phép scope này theo policy | Alice được đọc hồ sơ mọi nhân viên |
| `accessTokenTimeToLive(...)` | TTL AT do AS policy áp vào token phát hành | AT bị revoke ngay khi user logout |
| `reuseRefreshTokens(false)` | Bật rotation behavior trên refresh token settings tương ứng | Không còn nguy cơ RT replay hay race |

**Quan trọng:** Spring `RegisteredClient` scope allowlist hạn chế những scope client được đăng ký, nhưng **không thay** user entitlement/tenant policy, audience issuance hay pháp lý data consent. Với quyền nhạy cảm, hãy triển khai authorization policy riêng, không chỉ dựa vào `requireAuthorizationConsent(false)`.

### 13.2. Client nhạy cảm hoặc bên thứ ba

Một registration khác có thể yêu cầu UI:

~~~java
RegisteredClient thirdParty = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("partner-reporting")
        .clientSecret(passwordEncoder.encode(partnerSecretFromStore))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://partner.example.test/callback")
        .scope("hr.profile.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

Đây chỉ minh họa **hai registrations khác chính sách**; không mặc định mọi third-party bắt buộc có popup hoặc mọi first-party được skip. Quyết định phải căn cứ client owner, cấp quyền, loại dữ liệu, user/admin consent, luật áp dụng và risk policy.

### 13.3. Consent service là dữ liệu khác client classification

Spring Authorization Server có abstraction `OAuth2AuthorizationConsentService` để quản lý consent khi cần:

~~~java
OAuth2AuthorizationConsent existingConsent =
        consentService.findById(
                registeredClient.getId(),
                principalName);

if (existingConsent != null) {
    boolean allowedRead =
            existingConsent.getAuthorities().contains(
                    new SimpleGrantedAuthority(
                            "SCOPE_hr.profile.read"));
    // Chỉ là một dữ kiện phục vụ policy; không thay tenant/aud/ACL.
}
~~~

Snippet minh họa các object đã được inject vào cùng context. **Không** hiểu rằng mọi first-party pre-authorized request buộc phải có một bản ghi `OAuth2AuthorizationConsent`: khi UI consent không được yêu cầu, AS có thể dựa trên registration/policy mà không tạo persisted user consent như trong ví dụ. Ngược lại, bản ghi consent tồn tại **không tự** cho phép request sau này vượt scope/audience/policy phiên bản mới.

### 13.4. Policy engine hẹp theo tenant, scope, resource

Một evaluator domain Java 17 độc lập, đặt **sau bước AS đã xác minh client/transaction**:

~~~java
import java.util.Set;

record FirstPartyPolicy(
        String registeredClientId,
        Set<String> eligibleTenants,
        Set<String> allowedResources,
        Set<String> allowedScopes,
        Set<String> preauthorizedScopes,
        int version) {}

record AuthorizationRequestContext(
        String registeredClientId,
        String tenantId,
        String resource,
        Set<String> requestedScopes) {}

enum UiDecision { PREAUTHORIZED, REQUIRE_APPROVAL, DENY }

final class FirstPartyConsentPolicy {
    UiDecision evaluate(
            FirstPartyPolicy policy,
            AuthorizationRequestContext context) {

        if (!policy.registeredClientId()
                .equals(context.registeredClientId())) {
            return UiDecision.DENY;
        }
        if (!policy.eligibleTenants()
                .contains(context.tenantId())) {
            return UiDecision.DENY;
        }
        if (!policy.allowedResources()
                .contains(context.resource())) {
            return UiDecision.DENY;
        }
        if (!policy.allowedScopes()
                .containsAll(context.requestedScopes())) {
            return UiDecision.DENY;
        }
        return policy.preauthorizedScopes()
                .containsAll(context.requestedScopes())
                ? UiDecision.PREAUTHORIZED
                : UiDecision.REQUIRE_APPROVAL;
    }
}
~~~

**Giới hạn có chủ đích:** Code trên chỉ là **quyết định khả năng bỏ UI**, không phải complete OAuth authorization provider. Trước khi gọi evaluator, AS vẫn phải xác thực user/client, kiểm tra registration, redirect, PKCE, grant, resource owner/session, requested scope syntax và risk. Sau khi trả `REQUIRE_APPROVAL`, AS phải triển khai luồng approval **thực sự có thẩm quyền**; approval UI không được cho phép những hành động user vốn không thể cấp.

`registeredClientId` trong context phải đến từ **client registration đã được AS giải quyết**, không phải request field `first_party`. Policy version/owner/revocation state cần được kiểm tra ngoài snippet. Với app chỉ có một user-specific resource, quyền object phải do RS kiểm tra trên dữ liệu thật.

### 13.5. Khi cần consent UI động, không chỉ một cờ boolean

`requireAuthorizationConsent(false)` là setting **theo registered client** và không tự biểu diễn rule “chỉ skip cho scope A, hỏi lại scope B”. Nếu nhu cầu thay đổi theo scope/tenant/risk, có các lựa chọn kiến trúc cần đánh giá:

1. **Tách client registrations** theo tính nhạy cảm, resource và consent policy.
2. Dùng **policy-driven custom authorization/consent flow** trong AS, gắn với client registration và transaction đã verify.
3. Từ chối grant vượt baseline và yêu cầu client dùng một luồng/registration được duyệt cho quyền nhạy cảm.

Không chỉnh `RegisteredClient` trong database theo ý user chỉ để tắt UI, không override các authentication providers mà bỏ qua scope/client checks. Với Spring Authorization Server, customization phải tích hợp đúng extension point **của phiên bản framework** và có test bảo mật.

## 14. Spring OAuth2 Login và Resource Server vẫn phải bảo vệ token

### 14.1. Ứng dụng first-party là OIDC client

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-op:
            issuer-uri: https://auth.example.test
        registration:
          employee-portal:
            provider: company-op
            client-id: employee-portal
            client-secret: INJECT_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - hr.profile.read
~~~

`INJECT_FROM_SECRET_MANAGER` là placeholder, không được commit secret thật. Nếu app thực hiện OIDC login, Spring Security phải verify ID token (expected issuer, audience/client ID, signature/time/nonce theo profile), dùng `(iss, sub)` cho external identity mapping và không dùng ID token làm bearer AT gọi API.

Một BFF có thể giữ OAuth tokens phía server; browser chỉ dùng application session cookie `HttpOnly`/`Secure` và CSRF/XSS defenses. **Consent policy của AS không quyết định token storage** ở client.

### 14.2. Resource Server kiểm tra audience độc lập

~~~java
@Bean
JwtDecoder hrJwtDecoder() {
    String issuer = "https://auth.example.test";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(issuer)
            .build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);
    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("hr-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Token not issued for hr-api",
                            null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    standard, audience));
    return decoder;
}
~~~

Ví dụ dùng Spring Security 6.x và cần imports/bean wiring phù hợp phiên bản. Production phải bổ sung access-token type/profile, JWS algorithm allowlist, issuer/JWKS trust, tenant/principal policy và kiểm soát key rotation. Không cho RS tự lấy JWKS URL từ token header `jku` không tin cậy.

### 14.3. Quyền nghiệp vụ phải được kiểm tra tại API

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_hr.profile.read') " +
    "and @employeePolicy.canRead(authentication, #employeeId)")
public EmployeeProfile getEmployeeProfile(String employeeId) {
    return employeeRepository.findById(employeeId)
            .map(EmployeeProfile::from)
            .orElseThrow();
}
~~~

`employeePolicy`, `employeeRepository` và `EmployeeProfile` là domain abstractions, cần triển khai riêng. `@EnableMethodSecurity`, tên method parameter và Spring Security expression setup phải được cấu hình đúng phiên bản. `employeePolicy.canRead(...)` phải kiểm tra authenticated subject, tenant, owner/HR role và record được tra từ nguồn đáng tin; không chỉ dùng `employeeId` từ URL làm bằng chứng quyền.

Nếu access token thuộc **Client Credentials** service principal, không ép `sub` làm end-user; ứng dụng cần service-specific policy tách user-delegated access.

### 14.4. Tại sao không nên dựa vào `hasAuthority("SCOPE_openid")` ở API?

`openid` chỉ yêu cầu OIDC authentication. Nếu route payroll dùng:

~~~java
// SAI VỀ NGỮ NGHĨA CHO API PAYROLL
.requestMatchers("/payroll/**")
    .hasAuthority("SCOPE_openid")
~~~

thì bất kỳ AT được mapping `openid` có thể qua một điều kiện không đại diện quyền payroll. Phải yêu cầu **API-specific scope** được cấp thật như `payroll.read`, expected audience `payroll-api` và quyền theo nhân viên/tenant/record.

### 14.5. 401/403 và tương tác lại

| Phản hồi | Khả năng lỗi | Cách xử lý |
| --- | --- | --- |
| `login_required`/`interaction_required` tại OP | Silent SSO không đủ điều kiện | Chuyển sang interactive OIDC flow hợp lệ |
| `consent_required` tại OP | Cần approval mới | Hiển thị UX/consent theo chính sách, không tự skip |
| `access_denied` | User/policy từ chối grant | Dừng hành động hoặc xin quyền theo quy trình hợp lệ |
| `401 invalid_token` tại RS | AT sai/hết hạn/không xác minh được | Dùng grant hợp lệ để lấy AT khác nếu được phép |
| `403 insufficient_scope` tại RS | AT hợp lệ nhưng không đủ scope | Không refresh mù quáng cùng scope; xin quyền mới khi policy cho |
| `403/404` từ object ACL | User không có quyền record | Không dùng first-party flag hoặc admin token để vượt quyền |

**Không** biến lỗi consent thành lý do downgrade sang password grant hay client credentials quyền rộng hơn. Phục hồi phải tuân theo grant, principal và policy đã đăng ký.

## 15. Ma trận kiểm thử first-party consent (50 ca)

Môi trường test nên có một AS/OP với **ít nhất hai first-party registrations**, một partner registration, nhiều tenants, user scopes, session/consent repository và hai resource servers. Token test phải sử dụng issuer/keys **chỉ cho môi trường test**. Mỗi negative test cần một positive control tương ứng để không báo đạt chỉ vì AS/RS luôn từ chối do sai JWKS, network hoặc registration.

| ID | Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| C01 | Registered first-party portal xin `openid hr.profile.read` đúng baseline | AS có thể cấp grant mà không hiện consent UI mới |
| C02 | Client first-party chưa đăng nhập user nhưng gọi user-delegated flow | AS yêu cầu authentication hợp lệ; không mint token mù |
| C03 | Client tự gửi `first_party=true` nhưng registration không tin cậy | AS không thay classification theo request |
| C04 | Unknown client dùng display name giống portal chính thức | Không hưởng preauthorized policy |
| C05 | Dynamic registration self-service cố gắn nhãn trusted | IAM policy chặn nâng quyền classification |
| C06 | Portal xin scope ngoài allowed registration | AS từ chối hoặc thu hẹp grant theo policy |
| C07 | Portal xin `hr.profile.read` đúng scope nhưng resource `payroll-api` | AS từ chối audience trái allowlist |
| C08 | Client đổi redirect sang attacker-owned domain | AS từ chối authorization request |
| C09 | Callback `state` sai transaction | RP từ chối, không đổi code |
| C10 | PKCE `code_verifier` sai | AS từ chối code redemption |
| C11 | Authorization code đã được dùng một lần | AS không đổi code lần hai |
| C12 | Confidential first-party client có client secret/private-key assertion sai | AS từ chối dù policy baseline cho phép scope |
| C13 | Mobile first-party không có client secret nhưng đăng ký public, dùng PKCE đúng | Không đòi secret nhúng, tuân public-client policy |
| C14 | Public SPA nhúng secret rồi xin client_credentials user data | AS không cho app-only grant vượt policy |
| C15 | Partner client đăng nhập qua cùng OP và xin baseline của portal | Không được kế thừa quyền first-party |
| C16 | Existing approval chỉ có `hr.profile.read`, client xin `hr.profile.write` | Cần approval/step-up theo policy hoặc bị từ chối |
| C17 | Sensitive `payroll.export` bị đánh dấu blocked dù user nhấn Allow | Không cấp quyền trái client/domain policy |
| C18 | Browser request `prompt=none` khi chưa có OP session | OP trả `login_required`/interaction error phù hợp |
| C19 | `prompt=none` khi scope mới cần consent | OP trả `consent_required` hoặc lỗi interaction phù hợp |
| C20 | Scope vẫn baseline, OP session và policy hợp lệ | Silent grant có thể thành công mà không bypass validation |
| C21 | Request `openid`, Code + PKCE thành công | RP nhận và verify ID token theo OIDC |
| C22 | Request không chứa `openid` nhưng app coi như OIDC login | RP không tự đòi/nhận ID token theo OIDC |
| C23 | ID token `aud=employee-portal` được gửi tới `hr-api` | RS từ chối token purpose/audience |
| C24 | ID token có `iss` khác OP được tin | RP từ chối |
| C25 | UserInfo `sub` khác ID token `sub` | RP từ chối sử dụng UserInfo |
| C26 | Scope `email` được xin nhưng user không cho disclosure | OP tuân consent/policy, RP xử lý claim thiếu |
| C27 | Client xin `offline_access` nhưng policy baseline không cho | Không tự cấp RT |
| C28 | Client xin offline access hợp lệ, consent/OP policy phù hợp | RT chỉ được cấp khi grant/profile cho phép |
| C29 | RT bị revoke rồi client refresh | AS từ chối token issuance mới |
| C30 | RT rotation xảy ra, RT cũ bị dùng lại | AS xử lý reuse theo policy, không mint AT tùy tiện |
| C31 | User rút consent nhưng client cố silent re-grant qua cùng grant | Không tự cấp lại trái withdrawal policy |
| C32 | Admin giảm quyền baseline tại policy version mới | Token issuance mới theo version/approval mới |
| C33 | JWT AT cũ còn hạn sau đổi policy | RS thực thi revocation/domain ACL theo SLA, không giả định mất hiệu lực tự động |
| C34 | Opaque AT introspection `active=false` | RS từ chối |
| C35 | Introspection timeout hoặc TLS certificate sai | RS không fail open khi không xác minh được |
| C36 | User Alice tenant A dùng approval trên tenant B | AS/RS từ chối cross-tenant |
| C37 | Bob cùng tenant dùng persisted user consent của Alice | Không được cấp quyền từ approval sai principal |
| C38 | Cùng client nhưng đổi audience từ HR sang payroll | Token cache/AS policy không tái sử dụng approval sai resource |
| C39 | Client mới trùng tên nhưng registration ID khác | Không được mượn policy/consent của client cũ |
| C40 | Access token ký đúng nhưng sai `aud` | RS từ chối |
| C41 | AT đúng issuer/audience/scope, nhưng hồ sơ thuộc nhân viên khác | RS từ chối object-level ACL |
| C42 | AT có `scope=openid` nhưng không có `hr.profile.read` | RS từ chối API authorization |
| C43 | User/admin từ chối scope nhạy cảm, backend fallback service token admin | Test phát hiện và cấm confused deputy |
| C44 | Token `aud=hr-api` forward sang `payroll-api` | Payroll từ chối cross-resource token substitution |
| C45 | First-party app giữ RT trong browser local storage, bị mô phỏng XSS | Threat test phát hiện exposure; yêu cầu mitigation/BFF/rotation |
| C46 | Token issuer/JWKS được client cung cấp qua `jku` attacker | RP/RS chỉ tin configured issuer/JWKS |
| C47 | User logout RP nhưng OP session còn | Test phân biệt RP logout/OP logout, không khẳng định tất cả grants bị revoke |
| C48 | Privacy data xuất ra APM logs dù OAuth scopes đúng | Data minimization/log redaction tests thất bại |
| C49 | Consent UI ẩn nhưng audit bị gắn nhãn `USER_INTERACTIVE` sai | Audit ghi nguồn `PREAUTHORIZED_FIRST_PARTY` trung thực |
| C50 | Policy rollback từ version mới về version cũ có scope rộng hơn | Không tự phục hồi approval nhạy cảm nếu review/revocation policy không cho |

### 15.1. Test cô lập đúng ranh giới bảo mật

Để chứng minh **scope policy** hoạt động, giữ client, user, redirect, PKCE, issuer, resource và session đều hợp lệ:

~~~text
Test dương:
  client=employee-portal
  scope=openid hr.profile.read
  resource=hr-api
  tenant=company-a
  result=ALLOW theo baseline

Test âm:
  giống hệt test dương, chỉ thêm payroll.export
  result=DENY hoặc approval policy không thể cấp ngoài allowlist
~~~

Nếu cả hai đều thất bại vì client secret sai, test không chứng minh pre-authorization scope check. Tương tự, test audience cần một AT đúng audience được RS chấp nhận và AT sai audience bị RS từ chối khi mọi claims/keys khác đều hợp lệ.

### 15.2. Test consent state theo hai chiều

Một first-party baseline policy không nhất thiết tạo persisted **user consent record**; trong khi partner flow có thể yêu cầu một record explicit approval. Test phải kiểm tra theo **nguồn authorization thực tế**:

~~~text
First-party baseline:
  policy allows hr.profile.read
  → no required UI
  → audit source PREAUTHORIZED_FIRST_PARTY
  → no invented USER_INTERACTIVE record

Partner app:
  no existing consent for Alice, hr.profile.read
  → consent UI if policy requires
  → Alice approves
  → correct approval persisted
  → later requests still check policy and resource
~~~

Không dùng một test “không có consent DB row = thất bại” cho mọi first-party scenario. Ngược lại, không cho partner self-registration mặc định hưởng trusted policy.

### 15.3. Kiểm thử đồng thời khi thu hồi

Chạy các request đồng thời:

~~~text
Thread A: admin revokes approval / disables client.
Thread B: client attempts refresh.
Thread C: client attempts new code authorization.
Thread D: RS handles a still-valid JWT AT.
~~~

Kết quả phải phù hợp với **linearization/transaction policy** của AS và SLA thu hồi ở RS:

- New grants/RT refresh sau thời điểm revoke có hiệu lực không được cấp trái policy.
- Không để cache approval stale tự cấp quyền lại.
- AT đang sống được RS chặn theo TTL/denylist/status-check và policy đã cam kết.
- Audit ghi quyết định dựa trên policy version và thời điểm rõ; không ghi token raw.

Đừng dùng một `synchronized` lock trong một JVM làm bằng chứng concurrency an toàn cho AS nhiều node. Cần test database/CAS/transaction và cache invalidation thật.

### 15.4. Kiểm thử UI và khả năng hiểu của người dùng

Consent UX không chỉ là thử nút Allow/Deny:

1. Tên client/owner đáng tin và resource được yêu cầu hiển thị rõ.
2. Scopes được diễn giải bằng hành động user có thể hiểu, không chỉ technical names.
3. Quyền nhạy cảm/RT offline có giải thích phạm vi và thời hạn.
4. Không có dark pattern “Allow” là lựa chọn duy nhất khi user được phép từ chối.
5. Có cách xem/rút quyền khi policy cho phép, cùng thông tin hiệu lực thu hồi.
6. Mobile/SPA/BFF hiển thị consent đúng ngữ cảnh, không đánh tráo user bằng session mix-up.

Nếu policy là organizational mandatory access, UX phải **nói rõ** chứ không giả vờ đó là lựa chọn có thể rút.

## 16. Bốn tình huống thực tế

### Tình huống A: Employee portal không hỏi consent mỗi lần login

Tổ chức sở hữu portal/AS/HR API, đã đánh giá scope `hr.profile.read` là baseline cho nhân viên xem hồ sơ của chính họ. AS không hiển thị OAuth consent screen lặp lại ở mỗi lần SSO.

**Kết luận:** Đây có thể là first-party pre-authorization hợp lý nếu client registration, tenant, scope, audience, user authentication và policy được thực thi. AT vẫn phải bị `hr-api` giới hạn theo hồ sơ của user. Privacy notice/data retention vẫn là việc riêng, không được “coi là hoàn tất” chỉ do bỏ UI.

### Tình huống B: Ứng dụng nội bộ tự xin thêm payroll scope

Bản cập nhật portal muốn xuất bảng lương và thêm `payroll.export` vào authorization request. Developer nghĩ cùng công ty nên tự động cấp, không cần approval.

**Vấn đề:** First-party đã bị biến thành blanket trust. Scope mới nhạy cảm, có thể dành cho API khác và role khác.

**Giải pháp:** AS so request với registered scopes/resource/approval version. Từ chối hoặc yêu cầu admin review/explicit user interaction nếu user có khả năng cấp quyền; RS kiểm tra role/tenant/record. Không phát token payroll chỉ vì client display name là Portal.

### Tình huống C: First-party mobile app không có secret

Mobile app chính thức là public client và dùng `client_id` chung trong binary. Developer muốn AS bỏ PKCE vì công ty tự phát triển app và không hiển consent.

**Vấn đề:** Sở hữu ứng dụng không chứng minh client instance hay khả năng giữ secret. Attacker có thể extract client ID/redirect scheme và can thiệp authorization code.

**Giải pháp:** Authorization Code + PKCE S256 qua system browser/external user-agent, state/issuer binding, redirect URI native theo RFC 8252, secure token storage và registration policy. Có thể áp baseline preauth **riêng**, không bỏ client/security controls.

### Tình huống D: User rút quyền nhưng JWT vẫn được chấp nhận

Alice rút quyền `hr.profile.read` của một ứng dụng, AS revoke RT và consent record. Tuy nhiên một JWT AT đã cấp trước đó vẫn còn `exp` sau 4 phút; `hr-api` chỉ verify chữ ký offline và vẫn cho truy cập.

**Vấn đề:** Revocation của grant/RT không nhất thiết thu hồi ngay JWT AT. Nếu product hứa “rút quyền có hiệu lực tức thì”, triển khai đang vi phạm SLA.

**Giải pháp:** Chọn revocation model từ đầu: TTL ngắn phù hợp, state/denylist hoặc domain ACL check khi yêu cầu chặn ngay, opaque introspection freshness/cache giới hạn, và thông báo rõ hiệu lực cho user. Không dùng sự hiện diện của consent screen làm bằng chứng mọi AT được thu hồi.

## 17. Vận hành: đo lường sự an toàn của first-party policy

Một hệ thống dùng pre-authorized first-party consent thường cải thiện UX nhưng tăng trách nhiệm quản trị AS. Không nên đánh giá thành công chỉ bằng việc “giảm số lần popup”. Cần đo cả **tính phù hợp grant** và **khả năng phát hiện quyền bị mở rộng**.

### 17.1. Metrics có ích

| Tín hiệu | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| `oauth_authorize_allowed_total` theo client/scope/resource/policy decision | Số grant được cấp | Theo dõi scopes mới hoặc tăng đột biến ở client |
| `oauth_authorize_denied_total` theo reason | Grant bị từ chối | Tăng do policy rollout, attack hay lỗi client cần phân tích riêng |
| `consent_interaction_required_total` | Số request đòi approval mới | Giúp thấy luồng sensitive scopes có hiện UI đúng |
| `consent_withdrawal_total` | Số approvals/grants bị rút | Đánh giá hành vi client tiếp tục xin token sau withdrawal |
| `refresh_token_reuse_detected_total` | Tín hiệu RT replay/rotation race | Phân biệt tấn công và concurrency bug; không log RT |
| `resource_audience_rejected_total` | AT sai API | Phát hiện cross-resource forwarding hoặc token substitution |
| `authorization_policy_version_mismatch_total` | Cache/approval bị stale | Xác minh rollout/invalidation hiệu quả |
| `revocation_propagation_latency` | Độ trễ từ revoke đến RS từ chối | Đối chiếu SLA cho API nhạy cảm |

Tên metrics mang tính **minh họa**, không phải metric chuẩn Spring/OAuth. Phân chia nhãn theo tenant/subject cần tránh PII hoặc cardinality quá cao; dùng correlation IDs an toàn và sampling phù hợp.

### 17.2. Alert khi có thay đổi bất thường

Một số alert đáng cân nhắc:

- First-party client bắt đầu xin **scope/resource mới** không thuộc allowlist.
- Một registration bị đổi redirect URI, owner, client auth method hoặc grant type ngoài change window.
- Tỉ lệ `prompt=none` thất bại do `consent_required` tăng mạnh sau rollout.
- Refresh requests tiếp tục dù grant đã bị revoke.
- Một service token app-only dùng ở endpoint user-delegated thường xuyên.
- RS báo nhiều `invalid_token` do sai audience hoặc tăng cross-tenant 403.
- Policy rollback đưa scope nhạy cảm quay lại mà không có approval/version review.

Tập trung vào **sự kiện có thể hành động**, không dùng dashboard thu thập raw JWT, email, telephone hay credential.

### 17.3. Quy trình thay đổi baseline

Trước khi thêm `hr.profile.write` vào pre-authorized scopes:

1. Xác nhận **mục đích nghiệp vụ và người có quyền** đề xuất.
2. Phân tích dữ liệu/tác vụ nhạy cảm và giới hạn tenant/resource.
3. Xác định user/domain rights và liệu có cần step-up hoặc consent mới.
4. Review registered client, redirect, scope, grants, public/confidential type.
5. Đánh giá privacy notice/consent, retention và cách rút quyền theo luật/chính sách áp dụng.
6. Thử negative tests với scope cũ/mới, user có/không có quyền và các API khác.
7. Tăng policy version, rollout có giám sát, invalidate cache khi cần.
8. Có rollback an toàn **không tự khôi phục quyền đã bị revoke**.

### 17.4. Quy trình xử lý sự cố token bị lộ

Nếu phát hiện first-party AT/RT bị rò:

- Cô lập nguồn rò (logs, XSS, proxy, secret store), ngăn phát tán thêm.
- Revoke RT/grants hoặc credentials theo scope incident; đổi client keys/secrets khi cần.
- Xác định AT còn sống, affected audiences/scopes/tenants và chặn bằng denylist/domain policy nếu SLA yêu cầu.
- Điều tra audit theo token fingerprint/correlation metadata **không ghi raw token**.
- Kiểm tra liệu “trusted first-party” đã bị lạm dụng để xin scopes rộng, chuyển token sang resource sai hay không.
- Thông báo và khắc phục theo incident/privacy obligations của tổ chức; cập nhật baseline risk model.

Việc tắt consent popup sau sự cố **không giải quyết** token theft; cần giải quyết credential, trust boundary và revocation.

## 18. Checklist production cho first-party consent

### 18.1. Registration và nguồn quyền

1. **Ownership:** Có bằng chứng client thuộc tổ chức và owner được phê duyệt, không chỉ display name/domain?
2. **Client type:** Đã phân biệt first-party ownership với public/confidential credential capability?
3. **Grant types:** User-delegated Authorization Code + PKCE có được sử dụng đúng; app-only Client Credentials có scope riêng?
4. **Redirects:** Exact registered redirects, HTTPS/native profile, state/issuer/PKCE và client auth đúng?
5. **Tenant/resource:** Preauthorized policy có allowlist tenant/audience và scope theo từng client registration?
6. **Scope baseline:** Có approved version, change-control và sensitive-scope exclusions?
7. **Source:** Policy/approval được ghi trung thực là admin, user interactive hay pre-authorized first-party?

### 18.2. User interaction và quyền riêng tư

8. **Skip consent UI:** Chỉ bỏ khi client/subject/resource/scope/tenant/risks đã được policy cho phép?
9. **New permissions:** Scope mới, audience mới hoặc sử dụng dữ liệu với mục đích mới có quy trình xem xét?
10. **Silent OIDC:** `prompt=none` chỉ thành công khi đủ điều kiện; `consent_required`/`login_required` được xử lý đúng?
11. **OIDC:** `openid` phục vụ authentication, `profile`/`email` phục vụ claim disclosure, không thay API scopes?
12. **Offline access:** `offline_access`/RT có consent/policy riêng và thời hạn/rotation hợp lý?
13. **Privacy:** Có notice, mục đích, minimization, retention và withdrawal theo nghĩa vụ phù hợp, tách khỏi OAuth UI?
14. **UX:** Consent screen khi có hiện đúng app owner, scopes, resource, data recipients và lựa chọn hợp lệ?

### 18.3. Token issuance và validation

15. **AS issuance:** Không cấp scope/resource vượt registration, user/admin policy và grant thực tế?
16. **ID token:** RP xác minh OIDC issuer/audience/nonce/time; không gửi ID token tới API?
17. **AT audience:** RS kiểm tra đúng `aud` của chính API kể cả issuer chung?
18. **JWT/opaque:** Chữ ký/JWKS hoặc trusted introspection, `exp`, token type/status đúng profile?
19. **Domain ACL:** Tenant/owner/role và quyền từng object được RS kiểm tra?
20. **RT lifecycle:** Rotation/sender constraint, replay detection, expiry và single-flight phù hợp?
21. **Revocation:** Withdrawal/logout/user disable có SLA và cơ chế chặn AT còn hạn rõ?
22. **Token exchange:** Không forward sai audience hoặc fallback app-only admin khi user bị từ chối?

### 18.4. Vận hành/QA

23. **Monitoring:** Có metrics theo registration/scope/audience/decision source và alert policy drift?
24. **Audit:** Policy version, approved actor, principal, tenant, resource được lưu an toàn; không ghi raw credential/PII?
25. **Regression:** Test first-party UI skip, third-party consent, scope escalation, tenant reuse, revoke/refresh và RS ACL?
26. **Key/config lifecycle:** Client secret/private keys, signing keys, redirects, ownership được rotation/review?
27. **Fail closed:** Consent cache/AS policy/issuer discovery/introspection lỗi không tạo quyền chưa được xác minh?
28. **Change control:** Thay đổi baseline yêu cầu review, canary, negative tests và rollback không tái cấp quyền cũ trái phép?

## 19. Câu hỏi tự kiểm tra

**Câu 1. First-party client có nghĩa AS phải bỏ OAuth consent screen không?**

Không. First-party mô tả quan hệ tin cậy/ownership. AS **có thể** pre-authorize baseline scopes theo policy và bỏ UI, nhưng không có quy tắc OAuth bắt buộc “first-party = skip”.

**Câu 2. Nếu `requireAuthorizationConsent(false)`, có được bỏ kiểm tra client, PKCE và scope không?**

Không. Setting chỉ liên quan bước UI consent trong Spring Authorization Server; client registration, redirect URI, grant, client authentication, PKCE, user, audience và domain permissions vẫn phải được kiểm tra.

**Câu 3. Một SPA chính thức có thể coi secret nhúng trong JavaScript là bí mật không?**

Không. SPA/browser là public client ở phần JS. First-party ownership không làm nó thành confidential; phải dùng Authorization Code + PKCE, XSS controls và policy token storage phù hợp.

**Câu 4. Người dùng đã đăng nhập OIDC `openid` có mặc nhiên chấp thuận `payroll.export` không?**

Không. `openid` xin OIDC authentication, không phải quyền bảng lương. Scope nhạy cảm cần đúng AS client/user/admin policy, audience và RS authorization.

**Câu 5. Có cần lưu persisted `OAuth2AuthorizationConsent` cho mọi first-party baseline grant không?**

Không mặc định. Một AS có thể sử dụng registered client pre-authorization/organizational policy mà không có user interactive consent record. Nguồn quyết định phải được audit trung thực, không tạo user-consent giả.

**Câu 6. User consent đã có `hr.profile.read`, client có thể tự thêm `hr.profile.write` ở lần sau không?**

Không. Scope mới phải được AS đánh giá với registration, policy và quyền resource owner. Có thể cần approval/step-up hoặc bị từ chối.

**Câu 7. Client first-party có được dùng AT `aud=hr-api` tại `payroll-api` vì cùng issuer không?**

Không. Mỗi RS xác minh expected audience, token type và scope/ACL. Chữ ký chung không biến token thành credential phổ quát.

**Câu 8. `prompt=none` có ép OP thực hiện silent consent không?**

Không. Khi thiếu session/consent hoặc cần tương tác, OP trả lỗi phù hợp; client phải xử lý interactive flow, không tắt policy.

**Câu 9. Tại sao `offline_access` phải được xem xét riêng cho app nội bộ?**

Vì RT/offline grant có thể kéo dài quyền truy cập khi user không hiện diện. OIDC quy định consent/offline access semantics; first-party không tự cho RT vô hạn hay bỏ rotation/revocation.

**Câu 10. Sau khi user rút approval, JWT AT đang sống có lập tức hết hiệu lực không?**

Không nhất thiết. Nếu RS chỉ verify JWT offline, nó có thể chấp nhận đến `exp`. Cần TTL/denylist/status check/domain policy theo SLA.

**Câu 11. Nếu không có consent screen, công ty tự động đã đáp ứng yêu cầu privacy consent chưa?**

Không. OAuth consent UI và nghĩa vụ data privacy/legal notice là vấn đề riêng. Cần policy/thẩm định phù hợp mục đích xử lý dữ liệu, không suy từ cờ AS.

**Câu 12. Một app của cùng tập đoàn có thể dùng consent ở tenant A để đọc tenant B không?**

Không. Policy/consent phải phân vùng theo tenant/principal/client/resource/scope; RS vẫn xác minh object-level tenant quyền.

**Câu 13. Backend có service token admin có được dùng để xử lý request của Alice khi Alice từ chối consent không?**

Không. Dùng quyền service mạnh thay delegated user permission là confused deputy/authorization bypass, trừ khi tác vụ hệ thống có policy độc lập và được phép riêng.

**Câu 14. Một first-party client dùng `client_credentials` có cần user consent UI không?**

Không có user tương tác trong Client Credentials grant. Quyền app-only do service registration/IAM policy, và **không được hiểu** là user-delegated access.

**Câu 15. Điều gì cần log khi AS bỏ qua consent UI?**

Ghi policy/client ID, decision source, principal/tenant/resource/scope, policy version, timestamp/correlation ID an toàn; **không** ghi token raw hoặc giả vờ user vừa click Allow.

## 20. Tài liệu chuẩn và nguồn học tiếp

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò, authorization grant, client registration, scopes và resource-owner approval.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ OAuth, tránh ROPC/implicit, refresh token replay và sender constraint.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc authorization code và client transaction.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): public native clients, external browser và redirect security.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token cho resource/audience và tránh cross-resource substitution.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegation và actor/subject trust trong multi-hop services.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer AT, token theft/replay và HTTP error semantics.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile và claims issuer/audience/client/scope.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token status, `active` và introspection trust.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token, giới hạn đối với issued AT và grant lifecycle.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens giảm token replay.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `openid`, user authentication, `prompt=none`, `offline_access`, ID token, UserInfo và consent.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer/OP metadata.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, ClientSettings, OAuth2AuthorizationConsent/ConsentService, TokenSettings.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization endpoint, consent handling và extension points.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) và [Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): OIDC client login và API token validation.

**Điểm cần ghi nhớ:** **First-party consent không phải grant type hay quyền tự động bỏ mọi bước ủy quyền.** Với client do tổ chức kiểm soát, AS **có thể** không hiện lại OAuth consent UI cho các **scopes/resources/tenants đã được phê duyệt** khi user/session/policy hợp lệ. Tuy nhiên, `requireAuthorizationConsent(false)` không loại bỏ client authentication, PKCE, issuer/audience checks, user entitlement hoặc object ACL. **Scope mới, offline access, quyền nhạy cảm và thay đổi mục đích xử lý dữ liệu** cần được đánh giá theo đúng consent/admin/privacy policy. Revocation, token TTL, refresh rotation, issuer trust và audit quyết định liệu quyền đã rút có thực sự ngừng được sử dụng hay không.
