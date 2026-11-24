# Authorization Server trong OAuth và OIDC: trung tâm cấp quyền, phát hành token và quản lý vòng đời truy cập

**Authorization Server (AS – máy chủ ủy quyền)** là thành phần trong hệ sinh thái **OAuth 2.0** có trách nhiệm xử lý các yêu cầu ủy quyền hợp lệ và **phát hành access token cho client** sau khi các điều kiện áp dụng đã được đáp ứng. Tùy loại luồng, AS có thể cần xác thực người dùng, lấy quyết định chấp thuận, kiểm tra client, giới hạn phạm vi truy cập, quản lý refresh token và cung cấp những endpoint để các hệ thống kiểm tra hoặc thu hồi token.

Trong **OpenID Connect (OIDC)**, một Authorization Server có hỗ trợ OIDC đóng vai trò **OpenID Provider (OP)**, bổ sung khả năng phát hành **ID token** và cung cấp thông tin xác thực người dùng cho **Relying Party** theo giao thức. Tuy nhiên, **OAuth chủ yếu là giao thức ủy quyền truy cập**, không tự đồng nghĩa với giao thức đăng nhập; và **access token không phải ID token**.

Bài học thuộc chương **OAuth và OIDC** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trong mô hình **Joiner–Mover–Leaver (JML)**, AS phối hợp với **IdP/SSO, SCIM, RBAC/ABAC, ứng dụng và API**, góp phần bảo đảm một danh tính đã xác minh chỉ được sử dụng những tài nguyên và phạm vi hợp lệ. Khi người dùng đổi vai trò hoặc rời tổ chức, quyền, phiên và token liên quan cần được đánh giá và thu hồi thích hợp để hạn chế **quyền truy cập tồn dư**.

**Ý tưởng trọng tâm:** AS quyết định **có phát hành token hay không, cho client nào, tài nguyên/phạm vi nào và trong điều kiện gì**. Nhưng việc token có được chấp nhận cho một hành động cụ thể còn phụ thuộc **Resource Server** và chính sách nghiệp vụ. Phát hành token thành công **không tự động đồng nghĩa mọi quyền truy cập đều hợp lệ trong suốt thời hạn token**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Authorization Server**, **Resource Server**, **Client**, **Resource Owner**, **IdP/OP** và hệ thống quản trị vòng đời danh tính.
2. Mô tả Authorization Code flow với **PKCE**, các endpoint và kiểm tra mà AS thực hiện.
3. Giải thích sự khác biệt giữa **authorization code, access token, refresh token, ID token** và **session**.
4. Hiểu AS kiểm soát **client registration, redirect URI, scope, audience/resource, consent, policy và thời hạn token**.
5. Mô tả Client Credentials flow cho **service account/workload** mà không nhầm với đăng nhập một người dùng.
6. Nhận diện vai trò của **OIDC discovery, JWKS, introspection, revocation** và giới hạn của từng cơ chế.
7. Phân tích tấn công liên quan redirect, code, token, giả mạo client, phishing, khóa ký và cấu hình không an toàn.
8. Liên hệ AS với **Joiner–Mover–Leaver, IdP/SSO/SCIM, RBAC/ABAC, MFA, kiểm toán và xử lý quyền tồn dư**.

## 2. Những vai trò cơ bản trong OAuth 2.0

OAuth 2.0 phân chia trách nhiệm thành những vai trò logic. Chúng có thể được triển khai trên các dịch vụ hoặc máy chủ khác nhau; không bắt buộc mỗi vai trò tương ứng một máy vật lý.

| Vai trò | Trách nhiệm chính | Ví dụ |
|---|---|---|
| **Resource Owner** | Thực thể có khả năng cho phép truy cập tài nguyên được bảo vệ | Người dùng sở hữu dữ liệu; trong một số luồng không có người dùng tương tác |
| **Client** | Ứng dụng yêu cầu quyền truy cập tài nguyên theo giao thức OAuth | Web app, mobile app, backend service |
| **Authorization Server (AS)** | Xử lý yêu cầu ủy quyền, xác thực client khi áp dụng, phát hành token theo chính sách | Dịch vụ OAuth/OIDC của tổ chức |
| **Resource Server (RS)** | Máy chủ/API bảo vệ tài nguyên; kiểm tra token và thực thi quyền truy cập | API CRM, API báo cáo |
| **Identity Provider (IdP) / OP** | Xác thực danh tính người dùng; OP cung cấp chức năng OIDC | Nền tảng đăng nhập doanh nghiệp |
| **IAM/IGA lifecycle** | Quản lý danh tính, tài khoản, trạng thái JML, role và entitlement | Đồng bộ trạng thái HR/VMS, cấp/thu hồi nhóm và quyền |

### 2.1. Authorization Server khác Resource Server

**AS** chủ yếu cấp token khi đã có quyết định ủy quyền hợp lệ. **RS** nhận token từ client và quyết định **request cụ thể** có được phép hay không.

Ví dụ: AS cấp access token có phạm vi `reports.read` cho ứng dụng. RS vẫn phải kiểm tra **báo cáo thuộc dự án nào, người dùng có quyền với dự án đó không, token dành cho đúng API không và tài khoản có còn đủ điều kiện hay không**. Chỉ có `reports.read` không mặc nhiên cho phép đọc báo cáo của mọi tenant hoặc khu vực.

### 2.2. Authorization Server khác IdP như thế nào?

Một sản phẩm có thể triển khai **cả AS và IdP/OP**, nhưng về mặt khái niệm:

- **AS của OAuth:** Cấp access token dựa trên loại grant, client, quyền và chính sách.
- **IdP:** Xác thực người dùng và quản trị phương thức xác thực theo khả năng hệ thống.
- **OP của OIDC:** Cung cấp giao thức xác thực liên kết dựa trên OAuth, bao gồm **ID token** và các quy tắc xử lý claim.

Trong **Client Credentials flow**, AS có thể cấp token cho **client là workload** sau khi xác thực client và kiểm tra quyền, **không có một người dùng tương tác đăng nhập**. Vì vậy, không thể định nghĩa AS là “máy chủ luôn hỏi mật khẩu người dùng”.

## 3. AS tham gia vào kiến trúc IAM như thế nào?

~~~mermaid
flowchart LR
    H["HR / VMS<br/>Joiner–Mover–Leaver"] --> I["IAM / IGA<br/>Identity + entitlement"]
    I --> D["IdP / OP<br/>Xác thực người dùng, MFA"]
    I --> AS["Authorization Server<br/>Quyết định grant và cấp token"]
    D --> AS
    C["Client<br/>Web / Mobile / Workload"] --> AS
    AS --> C
    C --> R["Resource Server<br/>API + RBAC/ABAC"]
    R --> I
    R --> L["Audit / monitoring"]
    AS --> L
    I --> P["SCIM / API provisioning"]
    P --> R
~~~

Sơ đồ rút gọn: các chức năng IdP và AS có thể cùng nằm trong một nền tảng; quản trị entitlement có thể qua token claim, chính sách tại RS hoặc kho dữ liệu phân quyền. **SCIM không phải giao thức phát hành access token**, và AS không phải nơi duy nhất quyết định mọi quyền nghiệp vụ.

**Dòng chảy cần phân biệt:**

1. **Lifecycle:** Nguồn HR/VMS quyết định cá nhân có quan hệ hợp lệ; IAM tính quyền và account đích.
2. **Authentication:** IdP xác minh chủ thể theo chính sách nếu luồng cần người dùng.
3. **Authorization grant:** AS xác nhận client, người dùng/chủ thể, phạm vi và điều kiện grant.
4. **Token issuance:** AS cấp token với audience/scope/thời hạn phù hợp.
5. **Resource access:** RS kiểm chứng token và thực thi quyền trên request thực tế.
6. **Reconciliation:** IAM/RS/AS lưu dấu vết, phát hiện quyền không còn căn cứ và xử lý các biến cố Mover/Leaver.

## 4. Những endpoint thường gặp của Authorization Server

Một AS có thể công bố nhiều endpoint tùy chuẩn và cấu hình sản phẩm. Không phải tất cả đều luôn hiện diện hoặc được mở cho mọi client.

| Endpoint | Mục đích | Ai dùng thường xuyên? |
|---|---|---|
| **Authorization endpoint** | Tiếp nhận yêu cầu ủy quyền qua user agent trong các luồng tương tác, thường xử lý đăng nhập/consent và trả code | Trình duyệt, client khởi tạo redirect |
| **Token endpoint** | Đổi authorization code lấy token hoặc cấp token theo grant khác | Client được phép sử dụng grant |
| **Revocation endpoint** | Cho phép thu hồi token được hỗ trợ khi client có quyền | Client và thành phần quản trị theo thiết kế |
| **Introspection endpoint** | Trả trạng thái/metadata của token cho bên được phép hỏi | RS/API gateway hoặc hệ thống bảo mật |
| **JWKS endpoint** | Công bố khóa công khai để kiểm chữ ký khi dùng token ký | RP, RS, các thành phần xác minh |
| **Authorization Server metadata / OIDC discovery** | Công bố issuer, endpoint và khả năng hỗ trợ | Client, RP, RS theo cấu hình tin cậy |
| **UserInfo endpoint (OIDC, nếu hỗ trợ)** | Cung cấp claim về người dùng theo access token phù hợp | RP/OIDC client |
| **Logout / end-session endpoint (OIDC, tùy hỗ trợ)** | Hỗ trợ một số luồng kết thúc phiên liên kết | RP và trình duyệt |

**Lưu ý:** JWKS là nơi công bố **khóa công khai**; không được xuất private signing key. OIDC discovery là **cấu hình giao thức**, không phải bằng chứng tự động rằng mọi issuer/tenant được phép tin cậy. **Endpoint revocation/introspection có thể là tính năng tùy chọn và hành vi cụ thể cần được xác minh ở hệ thống đang sử dụng.**

## 5. Authorization Code flow với PKCE: luồng phổ biến cho ứng dụng có người dùng

Trong ứng dụng web/mobile hiện đại, **Authorization Code flow với PKCE** là lựa chọn nền tảng quan trọng. Client chuyển người dùng đến AS qua trình duyệt, AS xử lý xác thực/ủy quyền rồi trả **authorization code**; client đổi code thành token qua token endpoint trong giao dịch được bảo vệ.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Client / RP
    participant A as Authorization Server + OP
    participant R as Resource Server / API

    U->>B: Mở ứng dụng
    B->>C: Yêu cầu chức năng
    C-->>B: Redirect đến authorization endpoint
    B->>A: client_id, redirect_uri, state, PKCE challenge
    A->>A: Kiểm tra client, redirect, policy
    A->>U: Đăng nhập/MFA hoặc dùng phiên hợp lệ khi cần
    U->>A: Hoàn tất kiểm tra
    A->>A: Đánh giá grant, scope, resource, consent khi áp dụng
    A-->>B: Redirect callback chứa code + state
    B->>C: Gửi code + state đến callback
    C->>C: Kiểm chứng state và giao dịch
    C->>A: Đổi code bằng code_verifier và client auth khi áp dụng
    A->>A: Kiểm tra code, client, PKCE, thời hạn và reuse
    A-->>C: Access token và token khác nếu đủ điều kiện
    C->>R: Gọi API kèm access token
    R->>R: Kiểm token + quyền API / tài nguyên
    R-->>C: Kết quả trong phạm vi được phép
~~~

Sơ đồ minh họa **confidential web client**; luồng của **public mobile/browser client** khác ở cách bảo vệ token và thực hiện client authentication. PKCE hữu ích cho cả public lẫn confidential client; **client secret không được coi là bí mật nếu nhúng trong mã nguồn mobile hoặc frontend**.

### 5.1. Client khởi tạo yêu cầu

Các tham số quen thuộc:

| Tham số | Ý nghĩa |
|---|---|
| `response_type=code` | Client yêu cầu authorization code |
| `client_id` | Định danh client đã đăng ký |
| `redirect_uri` | Callback đã được AS chấp nhận/đăng ký |
| `scope` | Các phạm vi client muốn yêu cầu, ví dụ `openid reports.read` |
| `state` | Giá trị liên kết request–response, giúp chống CSRF và nhầm giao dịch theo thiết kế |
| `code_challenge` | Dẫn xuất từ `code_verifier` của giao dịch PKCE |
| `code_challenge_method=S256` | Cách tạo challenge bằng SHA-256 |
| `nonce` (OIDC khi dùng) | Ràng buộc ID token với phiên/giao dịch theo OIDC |
| `resource` / audience request nếu được hỗ trợ | Thể hiện RS/đối tượng nhận token mà client muốn truy cập |

Ví dụ **hình thức URL giả lập**:

~~~http
GET https://auth.example.test/oauth2/authorize?
  response_type=code
  &client_id=report-portal
  &redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback
  &scope=openid%20profile%20reports.read
  &state=RANDOM_PER_TRANSACTION_STATE
  &nonce=RANDOM_PER_TRANSACTION_NONCE
  &code_challenge=DERIVED_S256_CHALLENGE
  &code_challenge_method=S256
~~~

Đây là ví dụ để đọc tham số, **không phải một URL nguyên dạng để gửi**; trong HTTP thực tế các tham số thuộc cùng một request URL đã mã hóa đúng. Giá trị `state`, `nonce` và `code_verifier` phải được tạo ngẫu nhiên, lưu an toàn riêng từng giao dịch. Không dùng chuỗi cố định trong ví dụ làm giá trị thật.

### 5.2. AS kiểm tra yêu cầu và người dùng

AS cần xác nhận **client đã được đăng ký**, redirect URI phù hợp chính sách, grant type/response type được phép, scope được yêu cầu hợp lệ và các điều kiện giao dịch. Nếu luồng cần người dùng, AS/IdP kiểm tra **account có đang hợp lệ, người dùng đã xác thực ở mức yêu cầu và có cần MFA/step-up không**.

Không phải lần nào người dùng cũng phải nhập lại mật khẩu: nếu IdP có phiên còn hợp lệ và đáp ứng chính sách, có thể tái sử dụng phiên; hành động nhạy cảm có thể yêu cầu xác thực bổ sung.

Nếu có **consent**, giao diện chấp thuận phải diễn đạt quyền client xin, ứng dụng nhận và phạm vi truy cập một cách chính xác. Trong doanh nghiệp, **chính sách quản trị hoặc ủy quyền quản trị** có thể thay cho consent người dùng; không nên mặc định người dùng có thẩm quyền tự cho phép client truy cập dữ liệu của toàn tổ chức.

### 5.3. AS phát hành authorization code

Khi các điều kiện grant đạt, AS chuyển trình duyệt về **redirect URI đã đăng ký**, kèm `code` và `state`. Authorization code:

- Ngắn hạn, chỉ dành cho client/giao dịch tương ứng.
- Phải được đổi ở token endpoint và không được dùng để gọi API.
- Nên được thiết kế sử dụng một lần; AS từ chối mã đã dùng, hết hạn hoặc không khớp giao dịch.
- Được ràng buộc với các điều kiện client, redirect và PKCE phù hợp.

**Authorization code không phải bằng chứng quyền tài nguyên sử dụng lâu dài.** Nếu một mã bị lộ, PKCE giúp giảm nguy cơ kẻ khác đổi nó thành token khi không biết verifier hợp lệ.

### 5.4. Client đổi code thành token

Ví dụ token request:

~~~http
POST /oauth2/token
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback&
client_id=report-portal&
code_verifier=PRIVATE_PKCE_VERIFIER
~~~

AS kiểm tra **mã đúng giao dịch, còn hiệu lực, chưa sử dụng, khớp client và PKCE**. Confidential client phải thực hiện **client authentication** theo cơ chế đã đăng ký; không phải cứ có `client_id` là đã xác thực client. Public client không có khả năng giữ client secret dài hạn an toàn.

### 5.5. AS trả token và client/RS kiểm chứng

AS có thể trả `access_token`, `token_type`, `expires_in` và, nếu chính sách cho phép, `refresh_token`. Khi yêu cầu OIDC `openid` hợp lệ, OP có thể trả **`id_token`**.

- **RP** kiểm chứng ID token theo OIDC để xác định sự kiện đăng nhập và subject.
- **RS** kiểm chứng access token được phép dành cho mình và áp authorization trên mỗi hành động.
- **Client** bảo vệ token, quản lý phiên và không đưa token vào log, URL hoặc kênh không an toàn.
- **IAM** tiếp tục quản lý account và entitlement khi trạng thái JML thay đổi.

## 6. Các loại token và authorization code

| Thành phần | Phát hành bởi / dùng ở đâu? | Công dụng | Sai lầm cần tránh |
|---|---|---|---|
| **Authorization code** | AS trả về client trong luồng code | Đổi lấy token theo giao dịch được bảo vệ | Dùng như access token hoặc lưu làm phiên dài hạn |
| **Access token** | AS cấp cho client để gửi RS | Cho phép RS xét yêu cầu truy cập theo scope/audience/policy | Dùng làm ID token đăng nhập |
| **Refresh token** | AS cấp khi được phép | Xin access token mới theo điều kiện client/token | Coi như phiên vô thời hạn, lưu công khai |
| **ID token (OIDC)** | OP cấp cho RP | Cung cấp claim về sự kiện xác thực và subject | Dùng làm bearer token gọi API tùy ý |
| **Session cookie** | IdP hoặc ứng dụng theo thiết kế | Duy trì trạng thái phiên | Coi logout một ứng dụng là đã thu hồi mọi token |
| **API key / PAT** | Có thể do ứng dụng hoặc AS/sản phẩm cấp | Xác thực/ủy quyền theo cơ chế riêng | Tin rằng mọi key đều được quản lý bởi OAuth AS |

**Quy tắc phân biệt audience:** Trong OIDC, `aud` của **ID token** thường hướng tới **client/RP**. `aud` của **access token kiểu JWT** (khi được sử dụng) phải thể hiện **RS/API thích hợp** theo profile và chính sách. Không chuyển ID token sang API như thể nó là access token chỉ vì token có chữ ký đúng.

## 7. AS quyết định cấp token dựa trên những điều kiện nào?

AS không nên chỉ kiểm tra “client gửi đúng request”. Một quyết định cấp token có thể cần nhiều lớp:

1. **Client:** Đã đăng ký, còn active, grant type, redirect URI và phương thức xác thực phù hợp?
2. **Người dùng/chủ thể:** Nếu luồng cần người, danh tính đã được liên kết đúng, account/engagement đang hợp lệ và mức xác thực đạt chính sách?
3. **Grant/consent:** Có sự chấp thuận/căn cứ ủy quyền hợp lệ theo mô hình sản phẩm?
4. **Scope:** Client có quyền yêu cầu các scope đó không? Người dùng hoặc chính sách có cho phép những scope này không?
5. **Resource/audience:** Token nhằm tới API nào và API đó có nằm trong phạm vi client được phép?
6. **Thời gian:** Token phải sống bao lâu, có cấp refresh token không, điều kiện tuyệt đối/không hoạt động nào áp dụng?
7. **Rủi ro:** Có yêu cầu MFA/step-up, thiết bị phù hợp, chính sách mạng hoặc dấu hiệu gian lận không?
8. **Ràng buộc token:** Token mang tính bearer hay được ràng buộc với khóa/certificate khi nền tảng hỗ trợ?
9. **Trạng thái vòng đời:** Account bị đình chỉ, contractor hết hạn, vai trò bị thu hồi hoặc token/consent đã bị revoke chưa?

Một ví dụ quyết định minh họa:

~~~text
Client:        report-portal
Grant:         authorization_code + PKCE
Subject:       P-2048 (employee đang active)
Requested:     reports.read, reports.export
Allowed by app registration: reports.read, reports.export
Allowed by policy and current role: reports.read

Result:
  Không cấp reports.export nếu chưa có căn cứ/quy trình phù hợp.
  Có thể từ chối request hoặc giảm scope theo chính sách/giao thức.
  Không dùng scope được yêu cầu làm bằng chứng rằng đã được phê duyệt.
~~~

### 7.1. Scope không giống role, entitlement hoặc permission trên từng bản ghi

- **Scope OAuth:** Phạm vi client được AS cấp token, ví dụ `reports.read`.
- **Role RBAC:** Nhóm quyền theo trách nhiệm, ví dụ `finance_analyst`.
- **Attribute ABAC:** Điều kiện như `department`, `projectId`, `region`, `engagementStatus`.
- **Permission ở RS:** Quyết định thật cho hành động, tài nguyên và ngữ cảnh.

Một access token với `reports.read` không tự chứng minh người dùng có thể đọc **báo cáo của tất cả khách hàng**. RS cần kiểm tra quyền với **tài nguyên cụ thể**, phân vùng dữ liệu, SoD và chính sách ứng dụng.

### 7.2. Có nên nhúng toàn bộ quyền vào token?

Một số hệ thống đưa scope/role/claim vào JWT để RS tự kiểm. Ưu điểm là ít phải gọi AS khi nhận request; hạn chế là **claim có thể lỗi thời** nếu Mover/Leaver diễn ra sau khi token đã phát hành.

Một giải pháp khác là RS kiểm tra thông tin hiện hành qua policy service, entitlement store hoặc **introspection** nếu kiến trúc cho phép. Mỗi mô hình có chi phí độ trễ, tính sẵn sàng và khả năng thu hồi khác nhau; không có đáp án duy nhất.

## 8. Client registration và client authentication

Trước khi cấp quyền, AS cần biết client nào đang yêu cầu. **Client registration** thường xác lập:

| Cấu hình | Ý nghĩa |
|---|---|
| `client_id` | Định danh client được AS công nhận |
| Client type | **Public** hoặc **confidential**, theo khả năng bảo vệ credential |
| Allowed grant types | Authorization code, client credentials… theo thiết kế |
| Redirect URI | Callback được phép, đối chiếu chính xác theo đặc tả |
| Client authentication method | Client secret, private-key JWT, mTLS… khi phù hợp |
| Allowed scopes/resources | Phạm vi và API có thể xin token |
| Token policy | Thời hạn, refresh token, rotation, binding và chính sách khác |
| Owner | Nhóm/cá nhân chịu trách nhiệm vận hành client và credential |
| Environment | Development, staging, production phải được tách ranh giới phù hợp |

### 8.1. Public client và confidential client

**Public client** là ứng dụng không thể giữ client credential bí mật một cách tin cậy, ví dụ mã chạy trên trình duyệt hoặc ứng dụng native. Không được xem một chuỗi `client_secret` nhúng trong ứng dụng mobile là bí mật thật.

**Confidential client** có môi trường có thể bảo vệ credential, ví dụ backend server. Nó vẫn cần quản lý secret/khóa an toàn, rotation và quyền tối thiểu.

**PKCE không thay thế hoàn toàn client authentication** của confidential client. Hai cơ chế giải quyết các vấn đề khác nhau: PKCE ràng buộc code với bên khởi tạo giao dịch; client authentication xác minh danh tính confidential client ở token endpoint.

### 8.2. Đăng ký redirect URI an toàn

AS cần bảo vệ danh sách redirect URI; với luồng web, tránh **wildcard, open redirect hoặc URI do người dùng đưa tùy ý**. Các profile client native có thể có quy tắc callback khác, phải áp đặc tả tương ứng. Khi redirect URI thay đổi, cần quy trình quản lý cấu hình và kiểm tra chéo.

**Đừng biến AS thành nơi cấp token cho mọi client cùng hostname**. Client ID, redirect và policy phải ràng buộc tới **đúng ứng dụng và đúng môi trường**.

## 9. Token endpoint và vòng đời refresh token

Token endpoint không chỉ phục vụ authorization code. Tùy grant được phép, nó xử lý yêu cầu token và các chính sách tương ứng.

### 9.1. Khi client dùng refresh token

Refresh token cho phép client xin access token mới mà không bắt người dùng thực hiện đầy đủ luồng đăng nhập ở mỗi lần sử dụng. AS phải kiểm tra:

- Refresh token đúng client/đúng grant và chưa bị thu hồi/hết hiệu lực.
- Client authentication hoặc token binding theo yêu cầu.
- Grant/consent và chính sách liên quan còn được phép.
- Quy tắc **rotation**, phát hiện tái sử dụng và xử lý chuỗi token khi áp dụng.
- Thời hạn tuyệt đối và điều kiện không hoạt động theo thiết kế.

**Rotation** có thể làm refresh token cũ mất hiệu lực sau khi token mới được cấp. Nếu token cũ xuất hiện lại, đó có thể là dấu hiệu rò rỉ hoặc lỗi đồng thời ở client; cần xử lý dựa trên chính sách và khả năng server.

### 9.2. Không nhầm thời hạn access token với refresh token

| Loại | Thời hạn thường được thiết kế thế nào? | Kiểm soát quan trọng |
|---|---|---|
| **Access token** | Tương đối ngắn theo mức rủi ro/khả năng RS | Audience, scope, expiry, validation, revocation strategy |
| **Refresh token** | Có thể dài hơn nhưng bị ràng buộc bởi policy | Lưu trữ an toàn, rotation, binding, expiry, thu hồi |
| **Authorization code** | Rất ngắn, dùng một lần | Client/redirect/PKCE, ngăn replay |
| **ID token** | Theo chính sách và OIDC, không phải phiên API | Kiểm `iss`, `aud`, `exp`, nonce khi áp dụng |

Không áp một thời lượng chung cho mọi hệ thống. Token dùng cho API nhạy cảm hoặc public client có thể cần chính sách chặt hơn token trong môi trường ít rủi ro; mô hình vẫn phải đáp ứng khả năng vận hành.

## 10. JWT access token và opaque access token

AS có thể cấp access token ở nhiều dạng. Định dạng quyết định cách RS kiểm chứng và mức độ phụ thuộc vào AS khi nhận request.

| Thuộc tính | JWT tự chứa | Token opaque |
|---|---|---|
| Hình thức | Có cấu trúc claim và chữ ký thích hợp | Chuỗi tham chiếu không cần có ý nghĩa với client |
| Kiểm chứng ở RS | Có thể xác minh chữ ký/claim cục bộ theo profile | Thường hỏi AS/token service qua introspection hoặc kho dữ liệu |
| Tính mới của trạng thái | Claim có thể cũ đến hết hạn nếu không có kiểm tra bổ sung | Có thể tra trạng thái hiện tại, phụ thuộc thiết kế |
| Hiệu năng | Ít gọi về AS hơn khi hợp lệ | Có chi phí mạng/cache/availability tùy thiết kế |
| Thu hồi tức thời | Không được bảo đảm chỉ bằng việc disable user | Có thể thuận lợi hơn khi AS kiểm trạng thái, nhưng không tự bảo đảm mọi nơi |
| Quyền riêng tư | Claim có thể đọc được nếu token bị lộ, dù có chữ ký | Nội dung không nhất thiết lộ cho bên nhận chuỗi |

**JWT được ký không đồng nghĩa được mã hóa.** Không đặt thông tin cá nhân/nhạy cảm không cần thiết vào access token, ID token hoặc log. RS phải **kiểm token đúng audience, issuer, thuật toán, thời hạn và mục đích**; client không được dùng token dành cho API A để gọi API B trái policy.

### 10.1. Ví dụ JWT access token ở mức claim

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "person-P-2048",
  "aud": "https://api.example.test/reports",
  "client_id": "report-portal",
  "scope": "reports.read",
  "iat": 1790000000,
  "exp": 1790000900,
  "jti": "example-token-id"
}
~~~

Đây **không phải JWT hoàn chỉnh** (thiếu header/chữ ký) và không thể sử dụng để truy cập thật. Các claim khác nhau phụ thuộc profile token và sản phẩm; không phải OAuth 2.0 bắt buộc mọi access token có chính xác cấu trúc trên.

**`sub` cũng cần diễn giải đúng:** Trong delegated access nó có thể đại diện người dùng; trong Client Credentials flow có thể đại diện client hoặc workload tùy profile. Không dựa vào `sub` mà suy ra chắc chắn luôn có một nhân viên đã đăng nhập.

## 11. JWKS, issuer, audience và federation metadata

Khi dùng JWT ký hoặc OIDC, AS/OP có thể công bố **metadata/discovery** và **JWKS** để các bên kiểm chứng.

Ví dụ cấu hình OIDC rút gọn:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/.well-known/jwks.json",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Bên tiêu thụ cần xác minh **issuer đã được tin cậy chính xác**, URL và khóa được phép, lựa chọn thuật toán phù hợp và quy tắc OIDC/OAuth áp dụng. Một JWT có header `kid` không được tự ý quyết định URL khóa để ứng dụng tải; chỉ chọn khóa từ nguồn đã cấu hình.

### 11.1. Đổi signing key không đồng nghĩa đổi client secret

- **Signing private key của AS:** Dùng ký token hoặc thông điệp tương ứng; phải được bảo vệ.
- **JWKS/public key:** Dùng kiểm chữ ký, có thể công bố công khai.
- **Client secret/private key:** Dùng xác thực confidential client với AS khi áp dụng.
- **TLS certificate:** Bảo vệ kênh HTTPS; vòng đời riêng.
- **Encryption key:** Nếu hệ thống mã hóa token/dữ liệu, vai trò khác với khóa ký.

Một thay đổi certificate/TLS không mặc nhiên đổi khóa ký JWT. Trong **key rollover**, AS cần công bố khóa mới có kiểm soát, bảo đảm RP/RS tải/cập nhật được, chuyển sang ký bằng khóa mới, rồi gỡ khóa cũ khi chính sách và thời hạn token cho phép. Nếu khóa bị lộ, cần quy trình **incident response** thay vì chỉ đợi cache tự hết hạn.

## 12. Introspection và revocation: kiểm tra hoặc thu hồi token

### 12.1. Token introspection

**Introspection** là cơ chế để một RS hoặc bên được phép hỏi AS về trạng thái và metadata của một token, khi AS hỗ trợ. Kết quả có thể cho biết token có đang **active** cùng một số thuộc tính kiểm tra như scope, client, subject, audience hoặc expiry theo khả năng giao thức.

Ví dụ phản hồi minh họa:

~~~json
{
  "active": true,
  "client_id": "report-portal",
  "sub": "person-P-2048",
  "scope": "reports.read",
  "aud": "https://api.example.test/reports",
  "exp": 1790000900
}
~~~

**`active=true` không tự chứng minh user có quyền đọc mọi đối tượng**. RS vẫn cần kiểm tra tài nguyên và ngữ cảnh hiện hành. Ngoài ra, kết quả introspection có thể được cache; cần xác định **giới hạn độ mới và chiến lược fail-closed/fallback** phù hợp rủi ro.

### 12.2. Token revocation

**Revocation endpoint** cho phép client hoặc thành phần có quyền yêu cầu AS vô hiệu hóa token được hỗ trợ. Thu hồi refresh token và access token có thể có tác động khác nhau; chính sách thực tế phụ thuộc token type, mối liên hệ giữa token và kiến trúc AS/RS.

**Điểm cần hiểu:** Revocation được AS chấp nhận **không tự chấm dứt ngay mọi access token JWT mà RS đang xác minh ngoại tuyến**. Nếu RS không hỏi lại AS và token chưa hết hạn, nó có thể tiếp tục chấp nhận token theo thiết kế. Để giảm độ trễ thu hồi, có thể cần token ngắn hạn, introspection, danh sách thu hồi, kiểm tra trạng thái phiên/account ở RS hoặc cơ chế khác.

### 12.3. Logout không thay thế revocation

Logout tại ứng dụng có thể kết thúc **local session** mà không thu hồi access token độc lập. Logout tại IdP có thể không xóa session của mọi RP. Leaver đòi hỏi xem xét **tất cả những đường truy cập đã cấp**, bao gồm local account, session, PAT, refresh token, API key và quyền trực tiếp.

## 13. Client Credentials flow cho service account và workload

Một backend service cần gọi API mà không có người dùng tương tác có thể sử dụng **Client Credentials grant** nếu AS và client được cấu hình phù hợp.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload / Client
    participant A as Authorization Server
    participant R as Resource Server / API

    W->>A: Client authentication + grant_type=client_credentials
    A->>A: Kiểm tra client, grant, scope, resource, policy
    A-->>W: Access token cho workload
    W->>R: Gọi API bằng token phù hợp
    R->>R: Kiểm chữ ký/trạng thái + scope/audience + quyền
    R-->>W: Phản hồi cho hành động được phép
~~~

Ví dụ request dạng khái niệm:

~~~http
POST /oauth2/token
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=invoice.read
~~~

Client phải thực hiện **client authentication được AS chấp nhận** bằng phương thức phù hợp, chẳng hạn private-key JWT, mTLS hoặc secret được bảo vệ; ví dụ cố tình không chứa credential thật. `client_id` đơn thuần không phải chứng cứ client đã xác thực.

### 13.1. Trách nhiệm đối với workload identity

- Có **workload ID / client ID ổn định**, không dùng tài khoản nhân viên chung.
- Có **service owner** và ứng dụng/tác vụ cụ thể.
- Giới hạn **scope, audience, môi trường, mạng** phù hợp nhiệm vụ.
- Quản lý key/certificate/secret trong nền tảng an toàn, không nhúng vào repo hoặc log.
- Theo dõi phát hành token, sử dụng và cảnh báo bất thường.
- Có quy trình **rotate/revoke** khi secret lộ, owner thay đổi hoặc workload ngừng hoạt động.

**Client Credentials không phải “đăng nhập thay cho một người dùng”.** Nếu API cần quyết định dựa trên danh tính người đang thao tác, phải có mô hình delegated access, token exchange hoặc thiết kế ủy quyền phù hợp; không tự chèn một `userId` vào request của workload để mạo danh.

## 14. MFA, step-up và quyết định của AS

Trong luồng có người dùng, AS/OP có thể kết hợp IdP và **Multi-Factor Authentication (MFA)**:

- **Knowledge factor:** Mật khẩu/PIN trong ngữ cảnh phù hợp.
- **Possession factor:** Authenticator giữ khóa, khóa bảo mật, phương tiện tạo OTP.
- **Inherence factor:** Sinh trắc trong thiết kế phù hợp, thường giúp mở khóa authenticator.
- **Step-up:** Yêu cầu phương thức/mức xác thực bổ sung hoặc mới hơn trước một tài nguyên/hành động nhạy cảm.

Khi AS xử lý grant, nó có thể kiểm tra **mức bảo đảm, phương thức xác thực, độ mới của xác thực** theo các claim và policy được hỗ trợ (chẳng hạn `acr`, `amr`, `auth_time` trong ngữ cảnh OIDC).

**MFA không thay thế authorization.** Nhân viên xác thực bằng passkey vẫn không được tự động có quyền export dữ liệu tài chính nếu role, project hoặc SoD không cho phép. AS cũng không thể buộc RS thực thi quyền đúng nếu API chỉ kiểm chữ ký token mà bỏ qua policy nghiệp vụ.

## 15. Authorization Server trong Joiner–Mover–Leaver

### 15.1. Joiner: tài khoản và quyền phải sẵn sàng trước khi cấp token

Một nhân viên mới cần:

1. **Identity proofing:** Xác minh đúng người theo rủi ro.
2. **Nguồn có thẩm quyền:** HR/VMS xác nhận engagement và mốc hiệu lực.
3. **Account provisioning:** Tạo account tại IdP, ứng dụng qua SCIM/API hoặc cơ chế phù hợp.
4. **Authenticator enrollment:** Đăng ký MFA/passkey và phương thức khôi phục an toàn.
5. **Authorization policy:** Tính role, scope được phép và audience/tài nguyên cần sử dụng.
6. **Token issuance:** AS chỉ phát hành token khi client, người dùng và điều kiện grant hợp lệ tại thời điểm đó.
7. **Resource enforcement:** API kiểm chứng token và quyền với từng request.

**Chuẩn bị account trước ngày bắt đầu** không đồng nghĩa được cấp access token vào dữ liệu công việc trước mốc hiệu lực. AS/IdP/RS cần tôn trọng trạng thái account và chính sách có thẩm quyền.

### 15.2. Mover: thay role nhưng token cũ vẫn có thể còn hiệu lực

Ví dụ nhân viên An chuyển từ Sales sang Finance. IAM thu hồi `crm.customer.export`, cấp `invoice.read` theo vai trò mới. AS cần cập nhật **chính sách phát token mới**, nhưng một **access token cũ** có thể vẫn mang `crm.customer.export` cho tới khi hết hạn nếu RS chỉ tin token tự chứa.

Các cơ chế cần cân nhắc:

- Thu hồi grant/refresh token không còn hợp lệ.
- Giới hạn tuổi access token và cách kiểm tra trạng thái tại RS.
- Làm mới role/entitlement ở ứng dụng và RS, xử lý cache.
- Step-up hoặc thay yêu cầu MFA khi vào dữ liệu nhạy cảm.
- Đọc lại quyền hiệu dụng, không chỉ kiểm tra claim token mới.

### 15.3. Leaver: dừng phát token mới chưa đủ

Một contractor kết thúc hợp đồng, account bị disable ở IdP. Việc **AS ngừng cấp token mới** là quan trọng nhưng chưa chắc đủ:

- Refresh token có thể vẫn nằm ở client và cần bị thu hồi.
- Access token có thể còn thời hạn và được RS kiểm cục bộ.
- Ứng dụng có thể còn local session không phụ thuộc IdP.
- Personal access token/API key có thể do ứng dụng phát hành riêng.
- Role hoặc ACL trực tiếp tại RS có thể vẫn cho phép đường truy cập khác.

Vì vậy, cần quy trình **deprovisioning và verification** tại IdP/AS/SCIM/API/RS, xử lý session/token theo chính sách và lưu bằng chứng readback để giảm quyền truy cập tồn dư.

### 15.4. Rejoiner và nhiều engagement

Một người quay lại tổ chức có thể dùng identity ổn định nhưng cần đánh giá lại authenticator, grant, quyền cũ và điều kiện kích hoạt. Nếu contractor vẫn còn engagement B sau khi engagement A kết thúc, AS và RS phải phân biệt **quyền A cần thu hồi** với **quyền B có căn cứ còn hiệu lực**; không coi account đang active là lý do giữ mọi scope cũ.

## 16. Rủi ro bảo mật đặc thù tại Authorization Server

| Mối đe dọa | Hậu quả có thể | Biện pháp kiểm soát |
|---|---|---|
| **Redirect URI không kiểm soát** | Code hoặc thông tin giao dịch bị chuyển tới endpoint độc hại | Đăng ký redirect chính xác, chống open redirect |
| **Authorization code interception** | Bên thứ ba cố đổi code lấy token | PKCE S256, code dùng một lần/ngắn hạn, client/redirect checks |
| **CSRF/login mix-up** | Client nhầm giao dịch hoặc đăng nhập sai subject | `state`, kiểm issuer/giao dịch, thư viện an toàn |
| **Client impersonation** | Client giả yêu cầu token vượt policy | Client authentication phù hợp; public client có kiểm soát riêng |
| **Scope escalation** | Xin token có phạm vi lớn hơn được phép | Kiểm client registration, consent, policy và owner |
| **Token substitution** | Token dành cho API khác được dùng trái phép | Kiểm issuer, audience, token type và mục đích |
| **Key compromise** | Kẻ tấn công có thể phát token giả nếu chiếm signing key | Bảo vệ khóa, rotation, incident response, giám sát |
| **Refresh token theft/reuse** | Xin token mới trái phép | Bảo vệ storage, rotation, binding, phát hiện tái sử dụng |
| **Credential stuffing/phishing** | Chiếm quyền tài khoản người dùng trước grant | MFA chống phishing, chống thử đoán, bảo vệ recovery |
| **Stale entitlement/token** | Quyền cũ tồn tại sau Mover/Leaver | Policy hiện hành, token lifetime, RS checks, revoke/reconcile |
| **Metadata/JWKS injection** | Tin khóa hoặc issuer giả | Pin issuer và nguồn JWKS, SSRF protection, allowlist |
| **Overly long bearer token** | Token bị đánh cắp có thể bị dùng lâu | Giới hạn hạn/scope, kiểm soát revocation |
| **M2M credential leak** | Workload giả lấy token qua Client Credentials | Secret manager, mTLS/private key, giới hạn client grant |
| **Authorization Server outage** | Không phát token/không introspect được | Thiết kế HA, cache có chính sách và phương án khôi phục |

**Không nên chữa lỗi kết nối bằng cách bỏ kiểm chứng issuer, audience, chữ ký hay cho client lấy scope tự do.** Làm vậy có thể khôi phục đăng nhập bề ngoài nhưng phá vỡ các ranh giới tin cậy.

### 16.1. Luồng không nên chọn làm mặc định

Trong thiết kế mới, nên ưu tiên **Authorization Code với PKCE** cho các client tương tác theo profile và nền tảng. Những mô hình từng phổ biến như **Implicit grant** hoặc **Resource Owner Password Credentials grant** có các hạn chế an ninh đáng kể và không nên là lựa chọn mặc định cho ứng dụng mới.

Đặc biệt, yêu cầu client trực tiếp thu thập **mật khẩu IdP của người dùng** để đổi token phá vỡ lợi thế phân tách tin cậy của đăng nhập liên kết. Cần dùng các flow được AS/ứng dụng hỗ trợ theo khuyến nghị an toàn hiện hành.

## 17. Quy trình kiểm chứng token tại Resource Server

AS phát hành token; **RS là điểm chặn truy cập thực tế**. Tùy token type, RS có thể kiểm JWT tại chỗ hoặc hỏi AS qua introspection.

Một mô hình khái niệm:

~~~mermaid
flowchart TD
    A["API nhận request + access token"] --> B{"Token có đúng loại<br/>và nguồn tin cậy?"}
    B -->|Không| X["Từ chối"]
    B -->|Có| C{"Chữ ký hoặc trạng thái<br/>token hợp lệ?"}
    C -->|Không| X
    C -->|Có| D{"Issuer, audience, thời hạn,<br/>scope và token binding đạt?"}
    D -->|Không| X
    D -->|Có| E{"Identity/client và<br/>entitlement hiện hành hợp lệ?"}
    E -->|Không| Y["Từ chối hành động"]
    E -->|Có| F{"RBAC/ABAC cho<br/>tài nguyên cụ thể đạt?"}
    F -->|Không| Y
    F -->|Có| G["Cho phép trong phạm vi"]
~~~

Cần kiểm đúng **token dành cho RS**; không nhận ID token chỉ vì nó có `sub` và chữ ký. Với token introspection, phải xác thực kênh/RS trước khi trả metadata nhạy cảm, kiểm `active` cùng các trường phù hợp và đối chiếu dữ liệu quyền hiện hành.

### 17.1. Mã giả minh họa

~~~python
# Pseudocode mô tả trách nhiệm RS; không triển khai mật mã thủ công.
def can_read_report(request, trusted_token_validator, policy_engine):
    token = extract_bearer_token(request)

    if token is None:
        return deny_unauthenticated()

    claims = trusted_token_validator.validate_access_token(
        token,
        expected_issuer="https://auth.example.test",
        expected_audience="https://api.example.test/reports"
    )

    if not claims.is_active_or_valid:
        return deny_unauthenticated()

    if "reports.read" not in claims.scopes:
        return deny_forbidden()

    # Quyết định cuối cần thuộc tính và trạng thái hiện hành.
    allowed = policy_engine.evaluate(
        subject_or_client=claims.subject,
        action="report.read",
        resource_id=request.report_id,
        context=request.authorized_context
    )

    if not allowed:
        return deny_forbidden()

    return serve_authorized_report(request.report_id)
~~~

Mã giả không xử lý đầy đủ kiểm chữ ký/JWKS, token types, DPoP/mTLS, tenant, lỗi hạ tầng, log, idempotency, policy cache và các kiểu quyền khác. Hệ thống thật nên dùng **middleware/thư viện phù hợp với tiêu chuẩn token đã chọn** và chính sách bảo mật được kiểm định.

## 18. Các tình huống thực hành

### 18.1. Tình huống A: Access token hợp lệ nhưng API trả 403

**Bối cảnh:** Ứng dụng có access token `reports.read` do AS phát hành, chữ ký và thời hạn đều hợp lệ. Người dùng gọi API đọc báo cáo thuộc dự án khác và nhận `403 Forbidden`.

**Giải thích:** Token hợp lệ chứng minh client đã được cấp một phạm vi truy cập có điều kiện, **không cấp quyền với mọi bản ghi**. RS kiểm tra ABAC theo `projectId` và từ chối là hành vi có thể hoàn toàn đúng. Không sửa bằng cách tăng scope thành `reports.admin` hoặc tắt kiểm tra project.

### 18.2. Tình huống B: AS disable account nhưng token cũ còn sống

**Bối cảnh:** Nhà thầu kết thúc hợp đồng lúc 18:00. IAM disable IdP và AS không phát token mới. Một client vẫn còn access token JWT với `exp` muộn hơn mốc Leaver và RS đang kiểm chứng token ngoại tuyến.

**Câu hỏi:** Leaver đã hoàn tất chưa?

**Phân tích:** Chưa đủ căn cứ nếu token cũ vẫn cho phép truy cập ngoài mốc chính sách. Cần xác định cơ chế thu hồi/token validity tại RS, session, refresh token, local account và direct grants. Có thể cần kiểm trạng thái account/quyền hiện hành ở RS, token ngắn hạn hoặc biện pháp chặn riêng. Ghi kết quả readback và thời điểm quyền thực sự mất hiệu lực.

### 18.3. Tình huống C: Client Credentials dùng mật khẩu nhân viên

**Bối cảnh:** Một job chạy hàng đêm dùng mật khẩu của nhân viên quản trị để lấy token từ AS và truy cập API sản xuất.

**Phân tích:** Đây là thiết kế khó truy vết và phụ thuộc vòng đời cá nhân. Nếu nhân viên nghỉ việc, job có thể dừng; nếu mật khẩu bị lộ, API bị truy cập trái phép. Cần chuyển sang **workload identity/client riêng**, client authentication phù hợp, scope tối thiểu, owner kỹ thuật, quản lý credential và rotation.

### 18.4. Tình huống D: Mover và scope cũ

**Bối cảnh:** Một nhân viên chuyển từ Sales sang Finance. Token mới do AS cấp không còn scope CRM cũ, nhưng một token đã cấp trước đó vẫn còn hiệu lực.

**Phân tích:** AS đã cập nhật chính sách **cho lần phát hành tiếp theo**, nhưng trạng thái truy cập thực tế còn phụ thuộc RS. Phải xác minh hiệu lực token cũ, role/ACL ứng dụng, phiên và cách RS kiểm quyền mới, rồi đối soát theo yêu cầu Mover.

### 18.5. Tình huống E: Client yêu cầu token cho nhầm API

**Bối cảnh:** Client của ứng dụng Portal có token cho API Reports nhưng cố dùng cùng token gọi API Payments.

**Phân tích:** Payments RS phải kiểm **audience** và từ chối nếu token không dành cho mình, dù chữ ký đúng. AS và client cần thiết kế yêu cầu resource/scope phù hợp; không được chia sẻ token chung “dùng mọi API” chỉ để giảm số request.

## 19. Vận hành và kiểm toán Authorization Server

### 19.1. Những sự kiện nên theo dõi

| Nhóm sự kiện | Bằng chứng hữu ích | Thông tin không nên ghi |
|---|---|---|
| **Authorization request** | Thời điểm, client ID, grant/response type, policy và kết quả | Authorization code, session secret |
| **Authentication step** | Phương thức/mức xác thực và quyết định MFA theo policy | Password, OTP, PIN, dữ liệu sinh trắc thô |
| **Token issuance** | Token ID/hash tham chiếu, client, subject/workload, scope, audience, expiry | Access/refresh token nguyên văn |
| **Token refresh** | Client, chain/session reference, thời điểm và kết quả | Giá trị refresh token có thể dùng |
| **Revocation/introspection** | Bên yêu cầu, mục đích, kết quả, correlation ID | Credential bí mật hoặc token nguyên văn |
| **Client management** | Owner, thay đổi redirect, grant/scope, credential rotation | Client secret hoặc private key |
| **JML** | Identity/engagement status, thời điểm thay đổi và quyền bị tác động | Hồ sơ cá nhân vượt mục đích |
| **Signing key** | Key ID, lịch rollover, người duyệt và tình trạng | Signing private key |
| **Security anomaly** | Login/consent/token anomaly, cảnh báo và triage | Dữ liệu nhạy cảm không cần cho điều tra |

Mục tiêu kiểm toán là **truy vết quyết định cấp quyền và sử dụng token**, không tạo một kho bí mật có thể bị đánh cắp. Dữ liệu log cần phân quyền, bảo vệ toàn vẹn, thời hạn lưu và quy trình xử lý sự cố.

### 19.2. Các chỉ số gợi ý

- **Token issuance success rate:** Tỷ lệ cấp token cho yêu cầu hợp lệ, tách theo grant và client.
- **Authorization denial reasons:** Sai redirect, scope không được phép, client auth lỗi, user không còn eligible…
- **Token validation/introspection latency:** Ảnh hưởng tới trải nghiệm API và khả năng chịu lỗi.
- **Refresh token reuse detection:** Tín hiệu chuỗi refresh token bị dùng không hợp lệ.
- **Key rollover readiness:** Tỷ lệ RS/RP đã nhận khóa ký mới và xác minh thành công.
- **Unowned/unused clients:** Client không có owner hoặc không còn workload/ứng dụng hợp lệ.
- **Stale scope after Mover:** Trường hợp quyền hiệu dụng còn chứa grant hết căn cứ.
- **Time to verified revocation after Leaver:** Từ mốc chấm dứt tới khi các đường truy cập bắt buộc thực sự bị chặn.
- **Audience policy violations:** Token dùng sai API hoặc client xin scope vượt policy.
- **Residual session/token findings:** Token, PAT và session còn hiệu lực trái chính sách sau deprovision.

Không có một mục tiêu thời gian chung cho mọi hệ thống. Giá trị của chỉ số phụ thuộc độ nhạy tài nguyên, loại token, grant, mô hình cache, chính sách doanh nghiệp và khả năng vận hành.

## 20. Câu hỏi tự kiểm tra

**Câu 1:** Một OAuth Authorization Server có luôn xác thực người dùng bằng mật khẩu trước khi cấp token không?

**Gợi ý:** Không. Với Client Credentials flow, AS cấp token cho client/workload sau khi xác thực client và kiểm tra policy, không có người dùng tương tác bắt buộc.

**Câu 2:** Vì sao authorization code không được dùng thay access token để gọi API?

**Gợi ý:** Code là kết quả trung gian ngắn hạn, dùng một lần và được đổi tại token endpoint; access token là credential được RS xử lý theo đúng audience/scope.

**Câu 3:** Client đã gửi `scope=reports.admin`. AS có bắt buộc cấp scope đó không?

**Gợi ý:** Không. AS phải kiểm registration, grant, chính sách, consent hoặc quyền chủ thể; có thể từ chối hoặc giảm scope theo giao thức/chính sách.

**Câu 4:** ID token có chữ ký đúng, vậy gửi ID token tới API Payments có được không?

**Gợi ý:** Không tự động. ID token hướng tới RP và xác thực sự kiện đăng nhập; API cần access token dành cho RS cùng authorization phù hợp.

**Câu 5:** Khi Mover, AS đã phát token mới không có quyền cũ. Quyền cũ đã thu hồi hoàn toàn chưa?

**Gợi ý:** Chưa chắc. Kiểm token đã phát, session, role/ACL thực tế và logic authorization ở RS.

**Câu 6:** Tại sao `client_id` không đủ để xác thực một confidential client?

**Gợi ý:** `client_id` là thông tin định danh có thể công khai; confidential client cần cơ chế client authentication đã đăng ký, chẳng hạn secret/khóa/certificate phù hợp.

**Câu 7:** Revocation của refresh token có chắc khiến JWT access token trước đó mất hiệu lực ngay ở mọi RS không?

**Gợi ý:** Không. Nếu RS kiểm JWT offline và không có cơ chế cập nhật trạng thái, token có thể còn hợp lệ đến hạn. Cần phương án riêng theo yêu cầu thu hồi.

**Câu 8:** RS nhận token có `reports.read` nhưng người dùng không thuộc dự án của báo cáo. Ai phải ngăn thao tác?

**Gợi ý:** RS/API phải áp RBAC/ABAC và điều kiện tài nguyên. Scope là một điều kiện, không phải quyền đọc mọi dữ liệu.

## 21. Checklist thiết kế Authorization Server trong IAM

- [ ] **Vai trò rõ ràng:** AS, IdP/OP, client, RS và IAM/IGA được phân chia trách nhiệm đúng?
- [ ] **Nguồn có thẩm quyền:** Account/engagement trạng thái JML có ảnh hưởng đến quyết định cấp token?
- [ ] **Client registration:** Client ID, type, owner, grant, redirect, scope và resource được quản trị?
- [ ] **Client authentication:** Confidential client dùng credential có bảo vệ; public client không giả định secret là bí mật?
- [ ] **Luồng tương tác:** Authorization Code + PKCE S256, `state`, redirect và nonce OIDC khi áp dụng được xử lý đúng?
- [ ] **User auth:** IdP/OP thực thi yêu cầu MFA, step-up và độ mới phiên theo rủi ro?
- [ ] **Authorization grant:** AS kiểm tra scope, audience, client, consent/quyền và điều kiện policy, không tin chỉ yêu cầu của client?
- [ ] **Token types:** Code, ID token, access token, refresh token, session được phân biệt và sử dụng đúng mục đích?
- [ ] **RS enforcement:** API kiểm issuer, audience, thời hạn/chữ ký hoặc introspection và quyền RBAC/ABAC trên tài nguyên?
- [ ] **M2M:** Client Credentials có workload ID, owner kỹ thuật, scope/audience tối thiểu và credential lifecycle?
- [ ] **Token lifecycle:** Expiry, refresh token rotation, revocation, token binding khi hỗ trợ và session control đã thiết kế?
- [ ] **Metadata/keys:** Issuer, JWKS, thuật toán, signing key, rollover và nguồn tin cậy được xác minh?
- [ ] **Least privilege:** Client không xin hoặc nhận scope rộng hơn nhu cầu; RS không tự coi scope là toàn bộ entitlement?
- [ ] **Joiner:** Không cấp token vào tài nguyên công việc trước khi đủ điều kiện account/engagement?
- [ ] **Mover:** Quyền mới được áp, quyền cũ trong claim/token/cache và app được đối soát?
- [ ] **Leaver:** Disable login, chặn cấp token mới, xử lý refresh/access token, session/PAT và quyền tại RS?
- [ ] **Audit:** Có correlation ID, chính sách, client/subject, quyết định, thời điểm và kết quả nhưng không lộ secret?
- [ ] **Readback:** Không chỉ kiểm AS trả mã thành công; có bằng chứng quyền truy cập thực tế đúng ở RS và ứng dụng?
- [ ] **Chủ sở hữu:** Client, signing key, kết nối federation và service account đều có owner, thay đổi và expiry phù hợp?
- [ ] **Quyền tồn dư:** Có kiểm tra định kỳ token/quyền còn hiệu lực sau Mover/Leaver và xử lý ngoại lệ?

**Ghi nhớ:** **Authorization Server là thành phần cấp quyền và phát hành token của OAuth/OIDC**, chứ không phải cơ chế tự động cho phép mọi thao tác. Một thiết kế an toàn phải kiểm tra **client, grant, người dùng hoặc workload, scope, audience, thời hạn, token và khóa**, còn **Resource Server thực thi quyền theo RBAC/ABAC trên từng hành động**. Khi kết nối với **IdP/SSO, SCIM, service account, kiểm toán và các biến cố Joiner–Mover–Leaver**, tổ chức có thể quản lý cả **việc cấp mới lẫn việc chấm dứt quyền thực tế**, giảm nguy cơ quyền truy cập tồn dư.
