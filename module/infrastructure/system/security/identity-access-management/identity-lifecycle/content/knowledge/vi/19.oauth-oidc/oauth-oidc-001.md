# OAuth2 trong IAM: Ủy quyền truy cập, token và vòng đời danh tính

**OAuth 2.0** là một khung giao thức **ủy quyền (authorization)** cho phép ứng dụng nhận quyền truy cập có giới hạn vào một tài nguyên hoặc API mà không cần thu thập mật khẩu của chủ tài nguyên. Thay vì chia sẻ mật khẩu doanh nghiệp cho nhiều ứng dụng, một **Authorization Server (AS)** có thể phát hành **access token** với phạm vi, đối tượng nhận và thời gian hiệu lực thích hợp; **Resource Server (RS)** kiểm tra token và chính sách trước khi cung cấp dữ liệu.

Bài học **“OAuth2 trong IAM”** thuộc chương **OAuth và OIDC** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module tìm hiểu quản lý vòng đời danh tính theo mô hình **Joiner–Mover–Leaver (JML)**: từ xác minh danh tính, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Trong bức tranh đó, OAuth 2.0 cần được kết nối với **Identity Provider (IdP), Single Sign-On (SSO), OpenID Connect (OIDC), SCIM, RBAC/ABAC, danh tính dịch vụ, kiểm toán** và cơ chế giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Một nhân viên dùng ứng dụng quản lý chi phí để xem các hóa đơn được phân công. Ứng dụng chuyển người dùng tới IdP để đăng nhập, xin quyền gọi API hóa đơn và nhận access token. API vẫn phải kiểm tra token, vai trò, tenant và từng hóa đơn. Nếu người dùng chuyển bộ phận hoặc nghỉ việc, **token và phiên còn sống** có thể trở thành đường truy cập tồn dư nếu thiết kế thu hồi chỉ dừng ở việc gỡ nhóm IdP.

## 1. OAuth 2.0 giải quyết vấn đề nào?

Trước OAuth, một ứng dụng tích hợp có thể được yêu cầu giữ mật khẩu của người dùng hoặc dùng một tài khoản dùng chung để truy cập API. Cách làm này có nhiều rủi ro:

- Ứng dụng bên thứ ba phải giữ **credential nhạy cảm** ngoài phạm vi kiểm soát của IdP.
- Khó giới hạn quyền theo **ứng dụng**, **tài nguyên** và **mục đích**.
- Khó thu hồi riêng quyền của một client mà không đổi mật khẩu của người dùng.
- Khó quản lý phiên, thời hạn credential, phê duyệt và bằng chứng kiểm toán.
- Khi nhân viên Mover/Leaver, khó xác định ứng dụng nào vẫn còn giữ đường truy cập.

OAuth 2.0 cung cấp mô hình **ủy quyền dựa trên token** với các điểm kiểm soát như client registration, scopes, grant, token lifetime, audience và revocation. Mỗi quyết định vẫn phải phụ thuộc khả năng và chính sách của Authorization Server, Resource Server và hệ thống IAM.

**OAuth 2.0 không tự định nghĩa giao thức đăng nhập người dùng hoàn chỉnh.** Nếu ứng dụng cần biết người dùng là ai theo một quy trình đăng nhập được chuẩn hóa, thường dùng **OpenID Connect (OIDC)** xây trên OAuth 2.0. Đây là khác biệt quan trọng nhất cần nhớ.

## 2. Bốn vai trò của OAuth 2.0

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có thẩm quyền cho phép truy cập tài nguyên theo mô hình và chính sách tương ứng. | Người dùng hoặc chủ sở hữu nghiệp vụ. |
| **Client** | Ứng dụng yêu cầu token để gọi API. | Ứng dụng web, mobile, backend service. |
| **Authorization Server (AS)** | Xác thực/đánh giá điều kiện khi cần, cấp token sau khi grant hợp lệ. | IdP có chức năng OAuth/OIDC authorization server. |
| **Resource Server (RS)** | API chứa hoặc bảo vệ tài nguyên; kiểm token và quyết định truy cập. | API hóa đơn, CRM API, kho dữ liệu. |

~~~mermaid
flowchart LR
    U["Người dùng / Resource Owner"] --> C["Client App"]
    C -->|"Yêu cầu ủy quyền"| AS["Authorization Server / IdP"]
    U -->|"Xác thực và đồng ý/phê duyệt theo policy"| AS
    AS -->|"Access token"| C
    C -->|"Access token + API request"| RS["Resource Server / API"]
    RS -->|"Kiểm token + RBAC/ABAC + tài nguyên"| PDP["Policy / Identity data"]
    RS -->|"Dữ liệu được phép"| C
~~~

Các vai trò là **vai trò logic**, không nhất thiết là bốn máy chủ. IdP có thể đồng thời triển khai Authorization Server; ứng dụng và API có thể cùng một sản phẩm nhưng cần giữ ranh giới bảo mật giữa **client** và **resource server**.

### Không nhầm vai trò với danh tính người dùng

Trong luồng ủy quyền có người dùng, access token có thể phản ánh quyền mà client được phép thực hiện trong một ngữ cảnh gắn với người dùng. Trong luồng **client credentials**, token có thể chỉ đại diện cho chính **client/workload**, **không có người dùng tương tác**. API không được tự suy rằng mọi token đều đại diện cho một nhân viên.

## 3. OAuth 2.0, OIDC, SSO và phân quyền: khác nhau ở đâu?

| Cơ chế | Câu hỏi giải quyết | Thành phần điển hình | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **OAuth 2.0** | Client được phép truy cập API nào với phạm vi nào? | AS, access token, RS, scopes. | Không tự cung cấp danh tính người dùng đã xác thực theo mô hình OIDC. |
| **OIDC** | Người dùng đã được xác thực là ai, trong ngữ cảnh nào? | ID token, UserInfo, nonce, auth_time, acr/amr khi có. | ID token không phải access token để gọi API tùy tiện. |
| **SSO** | Người dùng có thể dùng phiên xác thực tập trung để vào nhiều ứng dụng không? | IdP, OIDC hoặc SAML, session. | SSO không tự đảm bảo quyền và account tại mọi ứng dụng được cập nhật. |
| **SCIM** | Tạo, cập nhật, vô hiệu hóa user và group ở hệ thống đích ra sao? | SCIM Users/Groups, provisioning connector. | Không phải luồng đăng nhập hoặc phát access token. |
| **RBAC/ABAC** | Subject được thực hiện hành động gì trên tài nguyên cụ thể? | Policy Decision/Enforcement Point. | Một scope rộng hoặc token hợp lệ không tự thay thế authorization mức đối tượng. |
| **JML governance** | Quyền và account thay đổi ra sao khi gia nhập, chuyển vai trò, nghỉ việc? | HRIS, IAM/IGA, IdP, connector và audit. | Không thể coi token tự hết hạn là chiến lược thu hồi duy nhất cho mọi trường hợp. |

### Hai token thường gặp với OIDC

- **Access token** dành cho **resource server**; client gửi khi gọi API. Có thể là chuỗi opaque hoặc token có cấu trúc như JWT tùy hệ thống.
- **ID token** do OIDC cấp cho **client/relying party**, mang các khẳng định về sự kiện xác thực của end-user. Ứng dụng phải xác minh ID token theo OIDC và không dùng nó như credential thay access token tại API.

**Ví dụ sai:** ứng dụng thấy một access token có trường email hoặc tên người dùng rồi coi đó là bằng chứng đăng nhập đáng tin. Access token có thể không được thiết kế để client tự phân tích, có thể không chứa user, và không nhất thiết mang các thuộc tính đủ để xác thực danh tính ở client. Khi cần login, dùng **OIDC theo profile phù hợp**.

## 4. Các khái niệm: grant, scope, audience và token

| Khái niệm | Ý nghĩa | Lưu ý bảo mật |
| --- | --- | --- |
| **Grant** | Cơ sở/luồng ủy quyền cho phép client yêu cầu access token. | Chỉ dùng grant type phù hợp client và rủi ro. |
| **Scope** | Phạm vi quyền API được cấp ở mức mà AS/RS đã thỏa thuận. | Scope không tự quyết quyền trên từng bản ghi hay tenant. |
| **Audience / resource** | API hoặc hệ thống nhận token một cách hợp lệ. | RS không được chấp nhận token dành cho API khác. |
| **Access token** | Credential client gửi để truy cập tài nguyên. | Phải bảo vệ như bí mật nếu là bearer token; giới hạn hạn dùng. |
| **Refresh token** | Credential cho client lấy access token mới khi được AS cho phép. | Không gửi tới RS; bảo vệ mạnh, có thể bị thu hồi/luân chuyển. |
| **Authorization code** | Mã tạm thời client đổi lấy token trong Authorization Code flow. | Không phải access token; một lần, thời hạn ngắn, gắn client/redirect/PKCE. |
| **Client ID** | Định danh đã đăng ký của client. | Không phải bí mật; không dùng làm yếu tố xác thực client. |
| **Client secret** | Bí mật xác thực của confidential client khi áp dụng. | Không được nhúng vào JavaScript frontend hoặc ứng dụng mobile. |
| **Consent** | Chấp thuận cấp một số quyền theo mô hình AS. | Có thể được thay bằng/đi cùng admin approval theo chính sách doanh nghiệp. |

**Scope mang nghĩa do API định nghĩa**: ví dụ invoice.read, invoice.write hoặc payment.approve. Việc AS cấp invoice.read không đồng nghĩa user được xem **tất cả hóa đơn**. RS còn phải kiểm tra owner, tổ chức, tenant, trạng thái hồ sơ và các quy định nghiệp vụ.

## 5. Chọn authorization grant phù hợp

| Luồng/grant | Khi sử dụng | Bên được đại diện | Yêu cầu và lưu ý |
| --- | --- | --- | --- |
| **Authorization Code + PKCE** | Web app, SPA, mobile hoặc ứng dụng có người dùng. | Client hành động trong một ngữ cảnh ủy quyền có user. | Dùng PKCE, redirect URI đã đăng ký, state/correlation; bảo vệ token. |
| **Client Credentials** | Server-to-server, batch job, workload không có user tương tác. | Bản thân client/workload. | Xác thực client, scope/audience hẹp, credential rotation hoặc federation. |
| **Refresh Token** | Gia hạn access token khi AS đã phát refresh token phù hợp. | Client giữ grant đã được cho phép. | Bảo vệ, rotation/sender constraint khi phù hợp và revoke khi có sự kiện. |
| **Device Authorization Grant** | Thiết bị có khả năng nhập liệu/trình duyệt hạn chế. | User phê duyệt qua thiết bị khác theo flow thiết kế. | User code, verification URI, expiry/polling, phòng phishing và chiếm thiết bị. |
| **Authorization Code không PKCE** | Có trong các triển khai lịch sử. | Phụ thuộc client. | Không nên chọn làm thiết kế mới khi PKCE hỗ trợ; áp dụng hướng dẫn bảo mật hiện hành. |
| **Implicit Grant** | Luồng lịch sử trả token qua authorization endpoint. | Client browser cũ. | Tránh cho thiết kế mới vì các rủi ro token trong front channel. |
| **Resource Owner Password Credentials** | Luồng lịch sử trao trực tiếp username/password cho client. | Client giữ password người dùng. | Không dùng trong thiết kế mới; làm mất lợi ích tách mật khẩu và hỗ trợ MFA/federation. |

Nhiều triển khai còn có **extension grant** (ví dụ token exchange hoặc JWT bearer) cho những trường hợp chuyên biệt. Chúng đòi hỏi hợp đồng tin cậy và threat model riêng, không phải mặc định an toàn hơn một luồng được thiết kế đúng.

### Public client khác confidential client

- **Public client** không thể giữ bí mật client lâu dài một cách đáng tin, như mobile app hoặc JavaScript chạy trong browser. Client secret nhúng trong ứng dụng phân phối tới người dùng **không phải bí mật**.
- **Confidential client** có thể xác thực an toàn với AS bằng client secret, private key hoặc mTLS trong môi trường server được bảo vệ.
- **PKCE không thay thế client authentication** đối với confidential client; nó ràng buộc authorization code với transaction/holder của code verifier.

Không suy độ an toàn dựa vào nhãn “backend” hay “mobile” đơn lẻ: cần đánh giá vị trí giữ credential, threat model và hình thức triển khai.

## 6. Authorization Code + PKCE: luồng khuyến nghị cho người dùng

**PKCE (Proof Key for Code Exchange)** giúp chặn việc đổi authorization code bị lấy cắp bằng cách ràng buộc code với một **code verifier** do client tạo cho transaction. Trong triển khai hiện đại, phương thức thử thách **S256** nên được dùng.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant C as Client
    participant AS as Authorization Server / IdP
    participant RS as Resource Server / API
    U->>C: Mở ứng dụng
    C->>C: Sinh state và PKCE code_verifier
    C-->>B: Redirect authorize + code_challenge
    B->>AS: Authorization request
    AS->>U: Đăng nhập/MFA nếu chính sách yêu cầu
    AS->>AS: Xác minh client, scope, consent/approval
    AS-->>B: Redirect về client với authorization code + state
    B->>C: Callback đã đăng ký
    C->>C: Kiểm state và transaction
    C->>AS: POST token: code + code_verifier
    AS->>AS: Kiểm code, client, redirect_uri và PKCE
    AS-->>C: Access token (+ ID token/refresh token khi có)
    C->>RS: API request với access token
    RS->>RS: Kiểm token, audience, scope, RBAC/ABAC
    RS-->>C: Kết quả được phép
~~~

Luồng chi tiết:

1. **Client đăng ký trước:** AS biết client ID, redirect URI được phép, grant type, cách xác thực client (nếu confidential) và policy scopes.
2. **Sinh transaction:** client tạo state khó đoán và **code_verifier ngẫu nhiên, có entropy đủ mạnh**. Với PKCE S256, code_challenge là giá trị base64url của SHA-256(code_verifier).
3. **Chuyển tới authorization endpoint:** request chứa client_id, response_type=code, redirect_uri, scope, state, code_challenge và code_challenge_method=S256.
4. **AS xác minh người dùng khi cần:** sử dụng IdP/SSO, MFA và bước phê duyệt phù hợp; authorization không phải chỉ kiểm mật khẩu.
5. **AS chuyển hướng về client:** trả code ngắn hạn, sử dụng một lần, cùng state về redirect URI đã được kiểm soát.
6. **Client kiểm state:** liên kết callback với transaction do chính mình khởi tạo, chống CSRF/login injection; không trao code ở callback nhầm phiên.
7. **Client gọi token endpoint:** gửi code và code_verifier qua kênh bảo vệ; confidential client cũng xác thực theo cách đã đăng ký.
8. **AS kiểm PKCE và các ràng buộc:** chỉ holder đúng code_verifier mới đổi code; code không được dùng lại.
9. **Client gọi API:** đính kèm access token trong Authorization header; RS tự xác minh và kiểm quyền.

Với **OIDC**, client còn cần tuân thủ các kiểm tra ID token và **nonce khi luồng/thiết kế yêu cầu**, không mặc định chỉ state là đủ cho mọi profile. OIDC có thể trả ID token để thiết lập phiên đăng nhập của client, trong khi OAuth access token chỉ phục vụ truy cập API.

### PKCE giải quyết và không giải quyết điều gì?

- Giảm rủi ro **authorization code interception**: người khác có code nhưng không có code_verifier khó đổi được token.
- Không thay thế **redirect URI validation**, **state**, kiểm **issuer** để chống authorization server mix-up hoặc việc bảo vệ token sau khi được phát.
- Không tự ngăn attacker đã chiếm được ứng dụng/thiết bị, secret store hoặc session người dùng.
- Không cấp quyền nghiệp vụ cho API: chỉ hỗ trợ bảo vệ quá trình cấp token.

## 7. Ví dụ HTTP: authorization và đổi code lấy token

Ví dụ bên dưới dùng endpoint giả định, **không phải request production** và không có credential sử dụng được.

~~~http
GET /oauth2/authorize?
    response_type=code&
    client_id=expense-portal&
    redirect_uri=https%3A%2F%2Fexpense.example.org%2Fcallback&
    scope=invoice.read%20openid%20profile&
    state=RANDOM_TRANSACTION_STATE&
    code_challenge=BASE64URL_SHA256_OF_RANDOM_VERIFIER&
    code_challenge_method=S256 HTTP/1.1
Host: idp.example.org
~~~

Phần request GET được xuống dòng **chỉ để dễ đọc**; khi gửi thực, các query parameters nằm trong một URL đúng encoding. Với OAuth thuần, không cần scope openid; khi có **openid**, client đang yêu cầu luồng OIDC nếu AS hỗ trợ.

Sau khi người dùng xác thực, AS chuyển browser tới redirect URI đã đăng ký:

~~~http
HTTP/1.1 302 Found
Location: https://expense.example.org/callback?code=ONE_TIME_CODE&state=RANDOM_TRANSACTION_STATE
~~~

Client kiểm state và đổi code lấy token:

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <confidential-client-auth-if-applicable>

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fexpense.example.org%2Fcallback&
code_verifier=ORIGINAL_RANDOM_CODE_VERIFIER
~~~

Ở public client, **không gửi client secret được nhúng trong frontend/mobile**; thông tin định danh client cần được gửi theo hợp đồng AS, ví dụ client_id tại token endpoint. Đối với confidential client, phương thức xác thực phải phù hợp cấu hình, không nhất thiết dùng Basic trong mọi triển khai.

Response minh họa:

~~~json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN_NOT_REAL",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "invoice.read",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN_NOT_REAL",
  "id_token": "OPTIONAL_OIDC_ID_TOKEN_NOT_REAL"
}
~~~

**Refresh token và ID token không luôn được cấp.** ID token chỉ thuộc luồng OIDC phù hợp, không tự có trong OAuth 2.0 thuần. Thời hạn 900 giây là minh họa, không phải quy định bắt buộc của chuẩn.

Client có thể gọi API:

~~~http
GET /api/v1/invoices?status=approved HTTP/1.1
Host: finance-api.example.org
Authorization: Bearer <access-token-for-finance-api>
Accept: application/json
~~~

**Không đưa access token vào query string, local log, URL điều hướng hoặc ticket hỗ trợ.** Bearer token có thể được sử dụng bởi bất kỳ bên nào nắm giữ nó nếu không có ràng buộc sender-constrained bổ sung.

## 8. Phân biệt Authorization Server, IdP và API authorization

Một IdP thường kiêm Authorization Server, nhưng quyết định cấp token **không phải** quyết định cuối cùng cho mọi tài nguyên.

| Bước | Hệ thống chủ trì | Kết quả |
| --- | --- | --- |
| Identity proofing / enrollment | HRIS, IAM/IGA, quy trình proofing. | Xác định đúng danh tính và authenticator. |
| Authentication / SSO | IdP. | Phiên xác thực, MFA hoặc context tin cậy. |
| OAuth grant evaluation | Authorization Server. | Client/scope/resource được cho phép theo policy. |
| Access token validation | Resource Server/gateway. | Token đúng nguồn, audience, hiệu lực và ràng buộc. |
| Object-level authorization | API/ứng dụng hoặc PDP/PEP. | Subject có thể đọc/sửa **đối tượng cụ thể** không. |
| Provisioning/deprovisioning | IAM/IGA, SCIM/connector. | Account và entitlement của hệ thống đích đúng JML. |

**Ví dụ:** AS cấp scope invoice.read. API Finance vẫn phải xác minh nhân viên thuộc tenant hiện hành và chỉ được đọc hóa đơn có trạng thái/đơn vị phù hợp. API không được bỏ kiểm tra tenant chỉ vì access token chứa scope invoice.read.

## 9. Access token: opaque, JWT và audience

Access token có thể là:

- **Opaque token:** chuỗi không có cấu trúc mà RS phải kiểm tra thông qua cơ chế đã được thiết kế, chẳng hạn **token introspection** hoặc gateway/trust service.
- **JWT access token:** một token có cấu trúc và chữ ký, cho phép RS kiểm tính toàn vẹn và các claims cục bộ **nếu AS/RS thỏa thuận profile tương ứng**.
- **Sender-constrained token:** token có ràng buộc với bằng chứng sở hữu khóa/chứng chỉ client (chẳng hạn DPoP hoặc mTLS khi được triển khai), giảm tác động nếu chuỗi token bị đánh cắp nhưng không có khóa tương ứng.

**Không bao giờ suy rằng mọi access token là JWT.** Client thường nên coi access token là chuỗi opaque dành cho RS; không giải mã tùy ý để quyết định người dùng hoặc quyền.

### JWT Access Token minh họa

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "person-4821",
  "aud": "https://finance-api.example.org",
  "exp": 1795000000,
  "iat": 1794999100,
  "jti": "access-example-284",
  "scope": "invoice.read",
  "client_id": "expense-portal"
}
~~~

Payload là **dữ liệu giả** để giải thích các trường, không phải token ký thật. Một token thực tế có thể dùng tên claim khác hoặc không có mọi claim nêu trên. Khi xác minh JWT access token, RS cần:

1. Kiểm chữ ký bằng **khóa/thuật toán được cho phép** của issuer đã trust; không tin thuật toán hoặc khóa do token tự chỉ định tùy tiện.
2. Kiểm **issuer**, **audience**, **expiration**, **not-before** khi có, các yêu cầu profile và thời gian cho phép.
3. Kiểm **loại token**, client và scope/resource theo hợp đồng API; không chấp nhận nhầm ID token, refresh token hoặc token dành cho API khác.
4. Kiểm sender constraint như DPoP/mTLS nếu token thuộc loại có ràng buộc này.
5. Kiểm **trạng thái subject, quyền hiệu lực và đối tượng tài nguyên** theo chính sách ứng dụng.
6. Có cơ chế cập nhật/thu hồi trong thời hạn yêu cầu; chữ ký hợp lệ không đồng nghĩa quyền hiện hành còn tồn tại.

**JWKS** hoặc metadata public key của Authorization Server phải được lấy và cache theo nguồn đáng tin. Việc một JWT mang trường kid không cho phép RS dùng bất kỳ URL khóa do token gợi ý mà chưa áp trust policy.

### Token confusion và sai audience

Một token hợp lệ dành cho CRM không nên được Finance API chấp nhận. Nếu API chỉ kiểm chữ ký và bỏ qua aud, attacker có thể chuyển token từ ứng dụng này sang ứng dụng khác (**token substitution/confused deputy**). Vì vậy mỗi RS phải kiểm audience/resource và phạm vi thích hợp, đồng thời có cơ chế xác thực token độc lập với client.

## 10. Scope không thay thế RBAC/ABAC

Trong IAM, **scope** thường diễn tả **khả năng mà client được cấp trên một API**. Nhưng điều kiện truy cập có thể phụ thuộc cả người dùng, quyền nghiệp vụ, trạng thái nhân sự và tài nguyên.

Ví dụ:

| Lớp kiểm soát | Dữ liệu minh họa | Câu hỏi |
| --- | --- | --- |
| OAuth token | scope=invoice.read | Client được phép xin đọc API hóa đơn không? |
| IAM role | FINANCE_INVOICE_READER | Người dùng có chức năng đọc hóa đơn không? |
| ABAC subject | tenant=vn, department=Finance | Thuộc tính hiện hành có phù hợp không? |
| ABAC resource | invoice.tenant=vn, status=APPROVED | Đối tượng này có trong phạm vi được phép không? |
| Lifecycle | employmentStatus=ACTIVE | Người dùng còn đủ điều kiện truy cập không? |
| Session assurance | MFA/reauthentication context | Tác vụ này có cần xác thực mạnh hơn không? |

Một chính sách ở backend:

~~~yaml
policyId: finance-invoice-read
token:
  requiredAudience: finance-api
  requiredScope: invoice.read
subject:
  employmentStatus: ACTIVE
  role: FINANCE_INVOICE_READER
resource:
  tenantMustMatchSubject: true
  statusAllowed:
    - APPROVED
action: READ
fallback: DENY
~~~

YAML là **mô hình nghiệp vụ minh họa**, không phải cấu hình của một sản phẩm thực tế. Các kiểm tra role, tenant và trạng thái nhân sự phải đến từ **nguồn đáng tin**, không dựa vào header hoặc body mà client tự đặt.

### Quyền có thể thay đổi trong khi token còn hạn

Nhân viên vừa Mover khỏi phòng Finance có thể vẫn giữ access token chứa scope invoice.read. Khi đó API cần kiểm **quyền hiện hành** hoặc áp cơ chế token revocation/version/TTL đã được thiết kế. Không được coi scope được cấp ở đầu phiên là giấy phép sử dụng quyền cũ vô thời hạn.

## 11. Thiết kế client bảo mật: redirect URI, state, PKCE và secret

Các rủi ro thường xuất hiện ngay ở phần triển khai client:

| Bề mặt | Lỗi thường gặp | Cách bảo vệ |
| --- | --- | --- |
| **Redirect URI** | Cho phép wildcard hoặc chuyển hướng tới domain do attacker điều khiển. | Đăng ký và so khớp URI chính xác theo profile; chỉ ngoại lệ được chuẩn hóa cho native app. |
| **state** | Không kiểm hoặc không gắn với phiên/transaction. | Sinh ngẫu nhiên, lưu server-side hoặc bảo vệ tương đương, kiểm một lần và TTL. |
| **PKCE** | Dùng verifier cố định, bỏ code_verifier hoặc cho dùng phương thức yếu không cần thiết. | Sinh verifier mới mỗi transaction, dùng S256, chặn code replay. |
| **Client secret** | Nhúng secret trong SPA/mobile/ứng dụng phát hành cho người dùng. | Public client không dựa vào bí mật có thể trích xuất; confidential client giữ credential phía server. |
| **Authorization code** | Log callback URL hoặc dùng code lại. | Không log code, đổi một lần, TTL ngắn và bảo vệ callback. |
| **Bearer access token** | Đặt token vào localStorage không có threat model, URL, analytics hoặc log. | Ưu tiên mô hình lưu phù hợp; cân nhắc backend-for-frontend và cookie an toàn. |
| **Refresh token** | Lưu lâu dài, không rotation/revoke và không bảo vệ client. | Quản lý token lifecycle; rotation hoặc sender constraint phù hợp nền tảng. |
| **Issuer mix-up** | Client nhận response từ AS khác với AS đã bắt đầu transaction. | Ràng buộc issuer và AS với transaction; kiểm thông tin issuer theo profile. |
| **CSRF / login CSRF** | Attacker ép callback xác thực với phiên của họ vào browser nạn nhân. | state hoặc cơ chế tương đương đã được ràng buộc và kiểm đúng theo profile. |

### SPA và Backend-for-Frontend (BFF)

Với browser client, JavaScript chạy trong browser có thể bị tác động bởi XSS và extension độc hại. Một mô hình **Backend-for-Frontend** giữ OAuth token ở backend, dùng cookie session an toàn cho trình duyệt, giúp giảm mức token bị lộ trực tiếp cho JavaScript. Tuy nhiên BFF vẫn phải bảo vệ **CSRF, XSS, cookie, session fixation, backend token storage và authorization**.

Nếu SPA trực tiếp giữ token, phải có threat model rõ, sử dụng Authorization Code + PKCE và hạn chế nơi, thời gian và phạm vi token tồn tại. **Không có một cách lưu token trong browser bảo đảm an toàn tuyệt đối trước XSS**.

## 12. Refresh token, rotation và thu hồi quyền

Access token thường có thời hạn ngắn để giảm cửa sổ bị lộ. **Refresh token** giúp client lấy access token mới mà không nhất thiết yêu cầu user đăng nhập lại, nhưng cũng tạo ra credential giá trị cao cần quản lý riêng.

### Vòng đời refresh token

~~~mermaid
flowchart LR
    A["AS cấp access token và refresh token khi policy cho phép"] --> B["Client dùng access token gọi API"]
    B --> C{"Access token sắp/hết hạn?"}
    C -->|Có| D["Client trình refresh token tại token endpoint"]
    D --> E{"Grant, client, token còn hợp lệ?"}
    E -->|Có| F["AS cấp access token mới; rotate refresh token nếu cấu hình"]
    E -->|Không| G["Từ chối, xóa local grant, có thể yêu cầu login lại"]
    F --> B
~~~

Các kiểm soát:

1. Chỉ cấp refresh token cho client và grant thực sự cần thiết.
2. Giới hạn thời gian, phạm vi, audience, device/session và inactivity theo chính sách.
3. **Refresh token rotation** có thể phát hành token mới và vô hiệu token cũ; phát hiện reuse của token cũ là tín hiệu nguy cơ compromise.
4. Với client không thể giữ secret, dùng rotation hoặc cơ chế **sender constraint** phù hợp với yêu cầu bảo mật đang áp dụng.
5. Bảo vệ kho lưu refresh token; không gửi nó tới API Resource Server.
6. Thu hồi refresh token/grant khi user đổi trạng thái, mất thiết bị, rời tổ chức hoặc có sự cố.
7. Kiểm soát lỗi mạng và xử lý race condition để không tự dùng lại refresh token đã rotate.

**Refresh token không luôn có trong OAuth response**; còn phụ thuộc grant, client, AS policy và scope/điều kiện. OAuth 2.0 **Token Revocation** và **Token Introspection** là các cơ chế mở rộng thường được dùng để kiểm soát credential, nhưng cách hỗ trợ phụ thuộc nền tảng.

### Khóa tài khoản IdP có lập tức vô hiệu mọi JWT access token không?

Không mặc định. Nếu resource server kiểm JWT tự chứa bằng chữ ký, expiry và scopes nhưng không kiểm trạng thái hiện hành hoặc denylist, token có thể tiếp tục được chấp nhận tới khi hết hạn. Cần một hoặc nhiều cơ chế:

- Access token TTL ngắn phù hợp SLA.
- Introspection hoặc truy vấn trạng thái grant/account khi kiến trúc hỗ trợ.
- Revocation list, token version hoặc kiểm trạng thái quyền hiện hành đối với API nhạy cảm.
- Thu hồi refresh token để chặn cấp **token mới**, đồng thời xử lý access token và session đã phát.
- Từ chối ngay tại gateway/RS khi có sự kiện nghiêm trọng nếu chính sách yêu cầu.

**Không coi refresh token revoke là bằng chứng access token hiện tại đã bị RS từ chối**. Muốn đóng workflow Leaver phải có readback hoặc kiểm chứng effective access ở điểm thực thi.

## 13. Client Credentials: OAuth 2.0 cho service account và workload

Nhiều tương tác IAM không có người dùng mở trình duyệt: job gửi dữ liệu giữa hai hệ thống, dịch vụ đồng bộ HRIS vào IGA, CI/CD gọi API triển khai. Với các trường hợp này, **Client Credentials Grant** có thể cho client được xác thực yêu cầu access token đại diện cho **chính client**, không thay mặt một nhân viên.

~~~mermaid
sequenceDiagram
    participant W as Workload / Service client
    participant AS as Authorization Server
    participant RS as Resource Server
    W->>AS: POST token: client_credentials + client authentication
    AS->>AS: Kiểm client, scope, audience, chính sách
    AS-->>W: Access token cho workload
    W->>RS: API request + access token
    RS->>RS: Kiểm issuer/audience/scope + workload policy
    RS-->>W: Kết quả được cấp phép
~~~

Request minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <confidential-client-credential-placeholder>

grant_type=client_credentials&scope=invoice.sync
~~~

Trong một số nền tảng, client có thể xác thực bằng **private_key_jwt, mTLS** hoặc **workload identity federation** thay cho client secret tĩnh. Cách gửi yêu cầu và các trường bổ sung phụ thuộc cấu hình AS. **Không đưa bí mật thật vào mã nguồn hoặc tài liệu.**

### Phân biệt client identity và user identity

| Thuộc tính | Authorization Code gắn user | Client Credentials |
| --- | --- | --- |
| Có người dùng tương tác | Thường có. | Không. |
| Ai được cấp quyền | Client trong ngữ cảnh grant có resource owner. | Chính workload/client. |
| Authenticator chính | User authentication ở AS/IdP, và client authentication khi áp dụng. | Client authentication / workload proof. |
| Token có thể mang subject user | Có thể theo profile. | Không tự giả định có user. |
| Kiểm quyền | Scope **và** user/role/resource policy. | Scope **và** workload/service/tenant/resource policy. |
| Thu hồi theo JML | Đánh giá user grant, session và account. | Đánh giá owner, client credential, trust policy và service lifecycle. |

**Không tạo một tài khoản nhân viên giả để chạy job** rồi bật MFA tương tác theo kiểu “người dùng phải nhấn Push mỗi lần cron chạy”. Với workload, cần danh tính kỹ thuật có owner, phạm vi tối thiểu, credential ngắn hạn/luân chuyển, audit và phương án thu hồi.

### Client Credentials và quyền tối thiểu

Ví dụ service invoice-sync chỉ cần đọc hóa đơn đã duyệt của tenant VN và ghi trạng thái đồng bộ. Nếu AS cấp scope invoice.sync, RS vẫn phải áp **client allowlist, tenant boundary và tài nguyên**, không cho client đọc toàn bộ bảng lương hoặc tạo payment approval.

Credential client bị lộ có thể giúp attacker lấy token mới, nên cần bảo vệ khóa trong vault/HSM hoặc hệ thống danh tính workload, phát hiện tần suất lấy token bất thường và có phương án **revoke client credential/trust** nhanh chóng.

## 14. Tích hợp OAuth 2.0 với IdP, OIDC và SSO

Trong một tổ chức, Authorization Server thường gắn với IdP để tận dụng **đăng nhập tập trung, MFA, lifecycle account và chính sách truy cập**. Khi client cần xác minh danh tính người dùng, luồng được triển khai theo **OIDC**.

~~~mermaid
flowchart LR
    HR["HRIS / nguồn danh tính"] --> IAM["IAM / IGA"]
    IAM --> IDP["IdP + OAuth Authorization Server"]
    IAM --> SCIM["SCIM provisioning"]
    SCIM --> APP["Ứng dụng / API"]
    USER["Người dùng"] --> CLIENT["OIDC client / ứng dụng"]
    CLIENT --> IDP
    IDP -->|"ID token + access token theo flow"| CLIENT
    CLIENT -->|"Access token"| API["Resource Server"]
    API --> POLICY["RBAC / ABAC / JML state"]
    IDP --> AUDIT["Audit"]
    API --> AUDIT
~~~

### ID token và UserInfo

OIDC bổ sung **ID token** với các claims chuẩn như issuer, subject, audience, expiration và thời điểm phát hành; có thể kèm **auth_time, acr, amr, nonce** theo điều kiện/flow. Client phải kiểm **chữ ký, issuer, audience, expiry, nonce và các yêu cầu OIDC khác** phù hợp với loại client và flow. **UserInfo** có thể cung cấp các thuộc tính user được phép, nhưng cũng cần bảo vệ và kiểm tra subject nhất quán với ID token theo profile.

ID token dành cho **relying party/client**, không phải token để RS API tự coi như quyền truy cập. Ngược lại, access token dành cho RS, client không nên dùng nó như một định dạng hồ sơ danh tính có thể đọc tự do.

### SSO không đồng nghĩa có quyền API

Một người đăng nhập thành công vào cổng SSO chưa chắc:

- Đã được phê duyệt dùng mọi ứng dụng.
- Có scopes được cấp cho client đó.
- Có RBAC role trên API đang gọi.
- Có thể xem dữ liệu của tenant khác.
- Còn quan hệ lao động hợp lệ nếu trạng thái đã đổi nhưng session chưa được kiểm tra lại.

Đây là lý do **IdP authentication**, **OAuth grant**, **API authorization** và **JML deprovisioning** phải được kiểm soát riêng, dù nằm trong cùng một nền tảng IAM.

## 15. Authorization scope, consent và phê duyệt trong doanh nghiệp

Trong ứng dụng tiêu dùng, người dùng có thể đồng ý cho client đọc dữ liệu của mình. Trong IAM doanh nghiệp, **resource owner và người dùng cuối không luôn có quyền tự quyết mọi grant**. Quy định có thể yêu cầu admin consent, business owner approval, SoD hoặc data classification.

Một cấu trúc quản trị có thể gồm:

| Loại yêu cầu | Ai quyết định? | Kiểm soát bổ sung |
| --- | --- | --- |
| Ứng dụng lịch cá nhân xin scope cơ bản | AS policy và người dùng theo mô hình dịch vụ. | Least privilege, hiển thị phạm vi, revoke grant. |
| Ứng dụng SaaS xin đọc dữ liệu Finance | Business owner và IAM/IGA theo chính sách. | Tenant restriction, approval, audit, contract với vendor. |
| Service client xin scope quản trị | Owner workload, security approver. | Client authentication mạnh, giới hạn môi trường, hạn hiệu lực. |
| Client muốn mở rộng scope đã có | Workflow change/consent mới khi cần. | Không lặng lẽ nâng quyền chỉ qua cấu hình UI. |
| Tác vụ nguy cơ cao | Resource policy và assurance policy. | Recent authentication/step-up và SoD. |

**Một consent screen không thay thế phân quyền nghiệp vụ.** Người dùng có thể đồng ý cho client dùng scope invoice.read, nhưng không được cấp quyền đọc hóa đơn của người khác nếu business policy cấm. Ngược lại, IdP/AS không nên tự cấp scope nhạy cảm chỉ vì client yêu cầu chuỗi scope trong URL.

### Scope creep

Client có thể dần tích lũy scopes không cần thiết. Định kỳ cần rà soát:

1. Client nào còn đang hoạt động và có owner hợp lệ?
2. Những scopes nào đã được cấp, đang thực sự sử dụng và có giải trình?
3. Có API/resource/audience nào ngoài mục đích đăng ký không?
4. Grant của người đã Mover/Leaver có được thu hồi không?
5. Có thể hạ scope, tách client theo môi trường hoặc thay bằng workload identity không?

## 16. OAuth và Joiner–Mover–Leaver

OAuth trong IAM không chỉ là trao token lúc đăng nhập. **Nguồn HR/IGA và trạng thái subject** phải ảnh hưởng đến việc phát token mới, cho phép refresh và quyết định ở API.

| Sự kiện | Tài khoản và grant | Token/session | Authorization thực tế |
| --- | --- | --- | --- |
| **Joiner** | Xác minh danh tính, tạo account đúng người, đăng ký client/quyền cần thiết. | Chỉ phát/cho dùng token khi đủ điều kiện ngày hiệu lực, authentication và policy. | Cấp scope/role tối thiểu theo phê duyệt; không mở dữ liệu trước ngày bắt đầu. |
| **Mover** | Cập nhật group/role, scopes/grants không còn phù hợp, áp SoD. | Revoke hoặc giới hạn grant và phiên bị ảnh hưởng; xử lý token cũ theo SLA. | API kiểm quyền vai trò mới, không cho dùng quyền cũ từ token còn hạn. |
| **Leaver** | Disable account/IdP, revoke grant và ứng dụng liên quan, deprovision qua SCIM/API. | Revoke refresh token, session và xử lý access token đang lưu hành. | RS từ chối quyền sau mốc thu hồi; kiểm các app/API key độc lập. |
| **Rehire** | Gắn lại danh tính theo nguồn tin cậy, cấp quyền mới sau xét duyệt. | Không khôi phục các grant/refresh token cũ không còn hợp lệ. | Không tự đưa về quyền của lần làm việc trước. |
| **Compromise** | Đánh giá user/client/account, tạm chặn hoặc thu hồi trust. | Revoke tokens và rotate credential, điều tra các phiên/API. | Chặn hành động nguy cơ cao, theo dõi sử dụng trái phép. |

### Joiner: không phát token chỉ vì account được tạo

HRIS có thể tạo hồ sơ nhân viên trước ngày bắt đầu. IAM/IGA có thể chuẩn bị account và SCIM user ở trạng thái inactive, nhưng AS/RS không nên cấp/nhận quyền nghiệp vụ chỉ vì tài khoản đã tồn tại. Điều kiện có thể bao gồm **identity proofing, ngày hiệu lực, trạng thái active, MFA enrollment và approval**.

### Mover: thay scope thôi chưa đủ

Tường chuyển từ Sales sang Finance. IdP gỡ nhóm Sales nhưng một client trước đó còn refresh token với grant CRM scope customer.export. Nếu AS vẫn cho refresh hoặc RS chỉ nhìn JWT cũ, Tường có thể tiếp tục xuất dữ liệu ngoài nhiệm vụ.

Khi Mover cần:

- Cập nhật desired entitlement, nhóm và scope/grant đang cho phép.
- Revoke hoặc ràng buộc lại refresh token/grant bị ảnh hưởng, không phát token mới với quyền cũ.
- Đảm bảo API kiểm entitlement hiện hành và các tài nguyên theo người dùng/tenant.
- Xác định cửa sổ access token cũ có thể còn hiệu lực, xử lý theo SLA.
- Kiểm SoD trước khi cấp quyền mới có xung đột với quyền cũ.

### Leaver: access token có thể tồn tại sau khi IdP disable

Đối với một JWT bearer token tự chứa, việc chặn login IdP và revoke refresh token **không tự xóa token đã phát**. Một RS kiểm mỗi chữ ký và exp sẽ có thể chấp nhận token đến hạn. Tổ chức phải xác định **latency chấp nhận được**, chọn cơ chế revocation/current-state check và **kiểm chứng đường API thực tế**.

Nếu người dùng vẫn còn **personal access token**, account cục bộ, session SaaS hay quyền vault, các đường đó cần xử lý riêng trong deprovisioning. OAuth không thay thế inventory và đối soát tài khoản.

## 17. Java pseudocode: xác minh access token và quyền tại API

Trong Spring Security hoặc một nền tảng resource server tương đương, nên sử dụng thành phần thư viện chuẩn để kiểm token. Mã sau là **pseudocode phục vụ tư duy**, không phải API production đầy đủ:

~~~java
// Token đã được một verifier tin cậy kiểm chữ ký hoặc introspection.
// Không tự tin claim từ JSON client gửi.
InvoiceDto getInvoice(TrustedAccessToken token, String invoiceId) {
    if (!token.isValid()
            || !token.issuerEquals("https://idp.example.org")
            || !token.hasAudience("finance-api")
            || !token.hasScope("invoice.read")) {
        throw new AccessDeniedException("invalid_or_insufficient_token");
    }

    // Chặn token dùng sai loại hoặc từ client không phù hợp.
    if (!token.isAccessToken()
            || !clientPolicy.isApprovedForApi(token.clientId(), "finance-api")) {
        throw new AccessDeniedException("client_not_allowed");
    }

    WorkforceIdentity subject = identityRegistry.current(token.subjectId());
    if (subject == null || !subject.isActive()) {
        throw new AccessDeniedException("identity_not_active");
    }

    Invoice invoice = invoiceRepository.requireById(invoiceId);
    if (!authorizationPolicy.hasRole(subject, "FINANCE_INVOICE_READER")
            || !authorizationPolicy.sameTenant(subject, invoice)
            || !authorizationPolicy.mayReadInvoice(subject, invoice)) {
        throw new AccessDeniedException("resource_not_authorized");
    }

    audit.recordInvoiceRead(
        subject.id(), token.clientId(), invoice.id(), token.safeReference());
    return invoiceMapper.toAllowedDto(invoice);
}
~~~

Khi token đại diện **workload** theo Client Credentials, không nên gọi identityRegistry.current(token.subjectId()) như thể subject là nhân viên. Backend phải có **policy branch riêng** cho service principal, workload identity, tenant, API scope và tài nguyên. Đây là lý do **token type/grant/client identity và user context** cần được mô hình hóa rõ ràng.

### Tách các bước kiểm soát

~~~text
Authentication/Token Validation:
  đúng issuer + signature/introspection + audience + expiry
  đúng loại token + client binding/sender constraint khi cần

OAuth Grant Evaluation:
  client được cấp scope tương ứng với resource
  grant chưa bị thu hồi, audience được phép

Business Authorization:
  subject/workload còn hợp lệ + role/ABAC + object/tenant
  SoD, hạn hiệu lực, điều kiện giao dịch

Lifecycle:
  trạng thái Joiner/Mover/Leaver mới nhất
  không chấp nhận quyền đã thu hồi dù token từng hợp lệ
~~~

Một access token được xác minh thành công không đồng nghĩa **request phải được chấp nhận**. Token validation và business authorization phải là hai lớp có thể kiểm thử và giám sát độc lập.

## 18. Java pseudocode: điều phối thu hồi grant khi Leaver

Mục tiêu của luồng Leaver là **ngăn cấp token mới và xử lý cả token đang lưu hành**:

~~~java
// Pseudocode: trạng thái nhân sự/IGA đến từ nguồn đã được xác minh.
RevocationReport onLeaver(TrustedLifecycleEvent event) {
    lifecyclePolicy.assertTrusted(event);
    WorkforceState current = hrRepository.currentState(event.subjectId());

    if (!current.isLeaverEffective()
            || event.revision() < lifecycleLedger.currentRevision(event.subjectId())) {
        return RevocationReport.blocked("not_effective_or_stale");
    }

    // Không chỉ disable login: thu hồi grants và refresh tokens.
    idp.disableInteractiveLogin(event.subjectId());
    authorizationServer.revokeAffectedGrants(event.subjectId());
    authorizationServer.invalidateRefreshTokens(event.subjectId());
    sessionService.revokeSessions(event.subjectId());

    // SCIM/connector xử lý account/role trên các ứng dụng.
    provisioningCoordinator.deprovisionRequiredTargets(event.subjectId());

    // Kiểm các Resource Server theo cơ chế được thiết kế:
    // introspection, denylist, current entitlement checks, token TTL...
    RevocationReport report = revocationVerifier.checkEffectiveAccess(
        event.subjectId(), event.effectiveAt());

    if (!report.allMandatoryTargetsVerified()) {
        incidentWorkflow.scheduleRemediation(report);
    }
    audit.persistWithoutSecrets(report);
    return report;
}
~~~

Đây chỉ là **sơ đồ logic**. API thật của IdP/AS có thể không hỗ trợ revoke mọi loại access token đã phát; cần biểu diễn **coverage gap** và cơ chế kiểm soát bù trừ thay vì tự báo đã thu hồi tức thì. Trạng thái **VERIFIED** chỉ được chốt sau khi có bằng chứng hiệu lực theo chính sách, không chỉ sau khi gọi thành công API.

## 19. Threat model: các lỗi bảo mật OAuth 2.0 phổ biến

| Mối đe dọa/lỗi | Hệ quả | Kiểm soát phù hợp |
| --- | --- | --- |
| **Authorization code interception** | Kẻ tấn công lấy code trên redirect. | PKCE S256, callback URI đúng, code một lần và TTL ngắn. |
| **Redirect URI lỏng** | Code/token bị chuyển sang domain không tin cậy. | Exact redirect matching theo profile, kiểm callback và chống open redirect. |
| **CSRF/login CSRF** | Browser nhận authorization result không thuộc transaction của mình. | state và transaction binding, cookie/session protection. |
| **Authorization server mix-up** | Client đổi code/token với AS không đúng nguồn. | Gắn transaction với issuer/AS dự kiến và kiểm issuer response. |
| **Client impersonation** | Dùng client ID công khai như secret. | Confidential client authentication; PKCE cho public clients. |
| **Token leakage** | Bearer token lộ qua URL, log, analytics, browser hoặc repo. | TLS, không đặt token trong URL, secret handling, sender constraints. |
| **Token substitution/audience confusion** | Token của CRM được API Finance chấp nhận. | Kiểm aud, issuer, token type, scope và trust theo RS. |
| **JWT validation yếu** | Chấp nhận token giả hoặc token sai issuer. | Thư viện chuẩn, alg allowlist, JWKS đúng trust và claim validation. |
| **Overbroad scopes** | Client có quyền vượt nhu cầu tích hợp. | Least privilege, admin approval, review và revoke grant. |
| **Broken object authorization** | Có invoice.read rồi xem hóa đơn tenant khác. | Kiểm RBAC/ABAC và đối tượng ở backend/PEP. |
| **Refresh token replay** | Attacker dùng token bị đánh cắp lấy nhiều access token mới. | Rotation hoặc sender constraint, reuse detection, revoke family theo policy. |
| **Stale token sau Mover/Leaver** | Quyền cũ tồn tại dù HR/IGA đã đổi trạng thái. | Current-state check, TTL, introspection/revocation và readback. |
| **ROPC/implicit legacy** | Mất mật khẩu hoặc token xuất hiện ở front channel. | Di chuyển sang Authorization Code + PKCE và cơ chế thích hợp. |
| **Client secret trong SPA** | Bất kỳ ai cũng trích xuất secret rồi giả client. | Không đặt secret ở client phân phối; dùng mô hình public client/BFF. |
| **Service principal không có owner** | Grant/khoá sống lâu sau khi ứng dụng ngừng dùng. | Inventory, review owner, rotation/decommissioning. |

**Không quy tất cả tấn công thành “bị lộ mật khẩu”.** OAuth có ranh giới tin cậy giữa client, Authorization Server, Resource Server, browser, token và nguồn IAM; lỗi ở bất kỳ ranh giới nào đều có thể làm suy giảm kiểm soát.

### Khi nào chọn sender-constrained token?

Bearer token có thể được trình bởi ai giữ chuỗi token. **DPoP** hoặc **OAuth mTLS** có thể gắn token với khóa/chứng chỉ của client trong những kiến trúc hỗ trợ, làm giảm nguy cơ token bị phát lại bởi kẻ chỉ có chuỗi token. Đổi lại, cần quản lý khóa, time/replay window, proof validation và tương thích client. Chúng **không loại trừ** rủi ro ứng dụng đã bị chiếm quyền điều khiển hoặc API authorization sai.

## 20. Audit, monitoring và reconciliation

Với OAuth trong IAM, audit hữu ích cần nối được **người dùng hoặc workload → client → grant → token → API → tài nguyên** và ngược lại đến sự kiện HR/IGA.

| Nguồn log | Metadata nên thu thập | Câu hỏi kiểm toán |
| --- | --- | --- |
| **Client registration** | Client ID, owner, môi trường, redirect URIs, credential type, allowed grants/scopes. | Ai đăng ký và chịu trách nhiệm cho client này? |
| **Authorization request** | Transaction ID, issuer, client, scope/resource, kết quả policy. | Client xin quyền nào, theo ngữ cảnh nào? |
| **Authentication/SSO** | Subject ID, auth_time, phương thức/assurance đã được xác minh, result. | User có được xác thực đúng theo policy không? |
| **Token issuance** | Client, grant type, audience, scopes, token reference, thời điểm và TTL. | AS đã phát credential với phạm vi gì? |
| **Refresh/revocation** | Token family/metadata, kết quả rotate/revoke, reason và timestamp. | Vì sao token vẫn được cấp mới hoặc bị chặn? |
| **Resource access** | Subject/workload, client, audience, action, resource ref, allow/deny, policy version. | API dựa trên quyền và tài nguyên nào để quyết định? |
| **JML changes** | HR event, effectiveAt, revision, roles before/after, deprovision readback. | Khi Mover/Leaver, những đường quyền nào còn tồn? |
| **Service identity** | Owner, workload, secret/certificate reference, rotation/expiry, scope. | Có credential không còn chủ sở hữu hoặc quá hạn không? |

**Không log access token, refresh token, client secret, authorization code, PKCE verifier, password hoặc session cookie bản thật.** Với token, dùng ID/tham chiếu an toàn (khi profile cho phép) hoặc hash tham chiếu được bảo vệ để tương quan, không biến log thành kho credential.

### Các chỉ số vận hành hữu ích

- **Token issuance by client/grant:** số lượng và biến động phát token, phân biệt client_credentials với user-facing flow.
- **Unexpected scope growth:** clients/grants có thêm scopes nhạy cảm ngoài baseline.
- **Invalid audience/issuer attempts:** số API từ chối token sai issuer hoặc không dành cho API.
- **PKCE/redirect validation failures:** rủi ro authorization flow cấu hình sai hoặc bị tấn công.
- **Refresh token reuse signals:** sự kiện phát hiện token rotation bị sử dụng lại.
- **Client credential age:** các secrets/certificates sắp hết hạn hoặc không có owner.
- **Lifecycle revocation latency:** thời gian từ Mover/Leaver effectiveAt tới khi RS không còn cho phép quyền cũ.
- **Orphaned grants:** grant/token/client liên kết với user hoặc workload không còn hợp lệ.
- **Deprovisioning verification coverage:** tỷ lệ API và hệ thống đích có bằng chứng thu hồi.

Một dashboard chỉ theo dõi số token bị revoke **không chứng minh an toàn**: nếu RS vẫn nhận JWT cũ hoặc còn API key ngoài OAuth, deprovisioning chưa đạt mục tiêu.

## 21. Tình huống thực tế: tích hợp ứng dụng Finance và xử lý Mover

### Bối cảnh

Công ty triển khai ứng dụng **Expense Portal** để nhân viên xem hóa đơn được duyệt. Người dùng đăng nhập tập trung bằng OIDC; backend nhận access token OAuth để gọi **Finance API**. Ngành Tài chính có yêu cầu không cho đọc tài liệu tenant khác và không cho người không có nhiệm vụ phê duyệt thanh toán.

### Bước 1 – Đăng ký client và chính sách

Nhóm IAM đăng ký client expense-portal, redirect URI chính xác, Authorization Code + PKCE, scopes invoice.read và profile xác thực phù hợp. Client secret (nếu có) chỉ nằm ở confidential backend. API Finance chấp nhận token đúng issuer và aud, rồi đánh giá RBAC/ABAC.

### Bước 2 – Joiner

Lan gia nhập Finance. HRIS gửi subject ID, ngày hiệu lực và role; IAM/IGA xác minh và cấp account IdP cùng entitlement được duyệt. Ứng dụng có thể pre-provision user qua SCIM, nhưng không cho truy cập trước ngày hiệu lực. Lan đăng ký MFA/passkey qua enrollment được bảo vệ.

### Bước 3 – Đăng nhập và lấy token

Lan mở Expense Portal; client sinh state, PKCE verifier, gửi authorization request. IdP yêu cầu xác thực theo policy và cấp code. Client đổi code có PKCE lấy token; với OIDC, client kiểm ID token để lập phiên và gửi access token đúng audience tới Finance API.

API yêu cầu scope invoice.read **và** role Finance phù hợp, kiểm hóa đơn đúng tenant. Nếu Lan cố gọi API hóa đơn của tenant khác bằng một token hợp lệ, API phải từ chối.

### Bước 4 – Mover sang bộ phận khác

Sau vài tháng, Lan chuyển sang Sales. IAM/IGA gỡ role Finance, thay các entitlement bằng role Sales, rà soát grant OAuth của Expense Portal. Một access token Finance còn hạn có thể vẫn tồn tại trong trình duyệt/ứng dụng. Vì vậy:

1. AS chặn cấp mới/refresh grant không còn được phép.
2. RS kiểm entitlement hiện hành và trạng thái người dùng theo SLA.
3. Session và token bị ảnh hưởng được thu hồi/giới hạn khi nền tảng hỗ trợ.
4. SCIM/connector cập nhật Finance SaaS; IAM đọc lại role và effective access.
5. Kiểm thử có kiểm soát xác nhận API Finance không còn trả dữ liệu cho Lan.

**Không chỉ đổi group ở IdP rồi ghi Mover hoàn tất.**

### Bước 5 – Leaver

Khi Lan nghỉ việc, HRIS phát sự kiện Leaver. IAM disable IdP, revoke các grants/refresh token liên quan, thu hồi phiên, deprovision các ứng dụng và yêu cầu RS chặn truy cập. Sau đó thực hiện readback đối với các tài khoản, quyền, local sessions và API credentials trong inventory.

### Bước 6 – Audit kết quả

Nhóm IAM lưu ID sự kiện nhân sự, mốc hiệu lực, mapping user/client, số lượng grants bị thu hồi, kết quả kiểm quyền tại Finance API, thời điểm verifiedAt và mọi ngoại lệ chưa xử lý. Nếu API vẫn nhận một token cũ hoặc có tài khoản ngoài OAuth, hồ sơ còn trạng thái cần khắc phục.

## 22. Bộ kiểm thử OAuth 2.0 trong IAM

| ID | Tình huống kiểm thử | Kết quả kỳ vọng |
| --- | --- | --- |
| O01 | Authorization Code + PKCE S256 hợp lệ, state và redirect đúng. | Client đổi code một lần, RS nhận token hợp lệ theo audience. |
| O02 | Client gửi code nhưng code_verifier sai. | Token endpoint từ chối. |
| O03 | Dùng lại authorization code đã đổi token. | Từ chối code replay. |
| O04 | Callback mang state khác transaction ban đầu. | Client không tiếp tục đổi code/lập session. |
| O05 | Redirect URI không nằm trong danh sách đăng ký. | AS từ chối authorization request theo chính sách. |
| O06 | Public SPA gửi client secret nhúng trong bundle và coi là confidential. | Thiết kế bị đánh giá không an toàn; không dựa vào secret có thể trích xuất. |
| O07 | API Finance nhận token có audience dành cho CRM. | RS từ chối dù chữ ký issuer hợp lệ. |
| O08 | JWT access token sai chữ ký, issuer hoặc đã hết hạn. | RS từ chối. |
| O09 | Client gửi ID token thay access token tới Finance API. | RS từ chối sai token type/audience. |
| O10 | Client gửi access token vào query string. | Thiết kế/test bảo mật báo lỗi; dùng Authorization header hoặc cơ chế chuẩn. |
| O11 | Token có scope invoice.read nhưng user không có role Finance. | RS từ chối hành động. |
| O12 | User Finance có role nhưng truy cập hóa đơn tenant khác. | Resource-level ABAC từ chối. |
| O13 | Client xin scope payment.approve chưa được duyệt. | AS không cấp scope ngoài policy. |
| O14 | Refresh token bị rotate và token cũ được sử dụng lại. | Áp reuse detection/revocation theo policy, không phát token trái phép. |
| O15 | User bị disable nhưng còn access token JWT tự chứa. | RS chặn quyền theo cơ chế revocation/current-state/SLA đã thiết kế; ghi bằng chứng. |
| O16 | Event Mover cũ đến sau Leaver. | Không tạo lại grant hoặc role; kiểm revision và trạng thái HR mới nhất. |
| O17 | Client Credentials token được xử lý như token user và gán user ID giả. | Chặn kiểu suy diễn sai; dùng workload policy riêng. |
| O18 | Service client xin token với scope vượt phạm vi môi trường staging. | AS/RS từ chối quyền production không được duyệt. |
| O19 | Client secret bị rotate hoặc revoked. | Credential cũ không đổi được token mới; credential hợp lệ mới được chấp nhận. |
| O20 | BFF nhận callback đúng nhưng cookie session thiếu bảo vệ CSRF. | Kiểm thử security không đạt cho tới khi sửa CSRF/session policy. |
| O21 | AS trả response từ issuer khác với issuer đã chọn cho transaction. | Client phát hiện mix-up và từ chối. |
| O22 | SCIM disable user nhưng API key riêng của ứng dụng vẫn hoạt động. | Deprovision chưa đạt; revoke key và xác minh. |
| O23 | API nhận token opaque và thử parse JWT trực tiếp. | Không thiết kế như vậy; dùng introspection/trust path phù hợp. |
| O24 | JWT với alg hoặc key tham chiếu ngoài allowlist. | Verifier từ chối; không tự lấy khóa từ nguồn do token kiểm soát. |
| O25 | User đăng nhập SSO nhưng chưa đến ngày hiệu lực Joiner. | Không cho quyền nghiệp vụ; gating lifecycle vẫn áp dụng. |

### Positive control và negative test

Trước khi kết luận một token bị từ chối vì audience hoặc quyền, cần xác nhận API đang hoạt động bằng **positive control được phép**. HTTP 404/503 do URL sai hoặc dịch vụ ngừng không chứng minh OAuth validation đúng. Log kiểm thử nên ghi **mã lý do và metadata an toàn**, không lưu token thật.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** OAuth 2.0 có phải giao thức đăng nhập người dùng hoàn chỉnh không?

**Trả lời:** Không. OAuth 2.0 là khung ủy quyền truy cập tài nguyên. **OIDC** bổ sung lớp xác thực người dùng được chuẩn hóa bằng ID token, UserInfo và các điều kiện kiểm tra phù hợp.

**Câu 2.** Một access token có scope invoice.read có cho phép đọc mọi hóa đơn trong công ty không?

**Trả lời:** Không. Scope chỉ là một phần trong quyền API được cấp. Resource Server còn phải kiểm tra subject/client, tenant, role, thuộc tính hóa đơn và policy nghiệp vụ.

**Câu 3.** PKCE giúp giải quyết vấn đề gì? Nó có thay thế state hay redirect URI validation không?

**Trả lời:** PKCE ràng buộc authorization code với code_verifier, giảm nguy cơ kẻ đánh cắp code đổi được token. Nó **không thay thế** kiểm state, redirect URI, issuer và bảo vệ token/session.

**Câu 4.** Vì sao không nên đưa client secret vào ứng dụng mobile hoặc SPA?

**Trả lời:** Mã/ứng dụng được phân phối tới người dùng nên secret có thể bị trích xuất; không thể coi đó là credential bí mật cho confidential client. Cần mô hình public client + PKCE hoặc backend bảo vệ secret.

**Câu 5.** Access token và ID token khác nhau thế nào?

**Trả lời:** Access token dành để gọi **Resource Server** được ủy quyền. ID token của **OIDC** dành cho client xác nhận kết quả xác thực user. Không dùng ID token như access token API.

**Câu 6.** Tại sao Leaver đã bị khóa IdP nhưng một JWT access token vẫn có thể dùng được?

**Trả lời:** Nếu API chỉ kiểm chữ ký và exp, token tự chứa còn hạn vẫn có thể được chấp nhận. Cần cơ chế thu hồi/kiểm trạng thái hiện hành theo SLA và kiểm chứng quyền tại RS.

**Câu 7.** Client Credentials có nghĩa là service account đang đăng nhập thay cho một nhân viên cụ thể không?

**Trả lời:** Không. Client Credentials chủ yếu đại diện cho **chính client/workload**; phải có quyền kỹ thuật và lifecycle riêng. Không tự gán user role cho token workload.

**Câu 8.** OAuth 2.0 có thay thế SCIM trong Joiner–Mover–Leaver không?

**Trả lời:** Không. OAuth cấp token để truy cập API; SCIM/connector đồng bộ account và group. IAM vẫn cần quản lý grants, sessions, entitlements và quyền thực tế ở từng hệ thống đích.

**Câu 9.** Nếu refresh token của người nghỉ việc đã bị revoke, có thể đánh dấu mọi access token đã bị thu hồi không?

**Trả lời:** Chưa. Thu hồi refresh token chặn cấp access token mới theo grant đó, nhưng access token đã phát có thể còn được chấp nhận. Cần kiểm đường RS/session và các credential độc lập.

**Câu 10.** Vì sao token JWT có chữ ký hợp lệ từ AS vẫn bị từ chối tại Finance API?

**Trả lời:** Token có thể sai audience, scope, loại token, trạng thái nhân sự hoặc không đủ quyền trên tài nguyên cụ thể. Chữ ký hợp lệ chỉ là một điều kiện của việc chấp nhận request.

## 24. Checklist triển khai và nguồn tiêu chuẩn nên tra cứu

Checklist trước khi đưa OAuth 2.0 vào production:

1. **Định nghĩa mục đích:** ứng dụng cần ủy quyền API thuần hay cũng cần login người dùng bằng OIDC?
2. **Kiểm kê vai trò:** client, AS, RS, chủ thể, workload và các nguồn trust.
3. **Chọn grant:** ưu tiên Authorization Code + PKCE cho user-facing; Client Credentials cho workload phù hợp; không chọn luồng legacy yếu cho hệ thống mới.
4. **Đăng ký client:** redirect URI, scope, audience, client authentication và owner theo môi trường.
5. **Bảo vệ flow:** state, PKCE S256, exact redirect, issuer binding, code single-use và thời hạn ngắn.
6. **Xác minh token:** issuer, audience, signature/introspection, expiry, scopes, token type, sender constraint khi có.
7. **Tách business authorization:** RBAC/ABAC, SoD, tenant/resource và trạng thái user/workload.
8. **Quản lý credential:** access/refresh token, client secret/key, rotation, incident response và revoke.
9. **Gắn JML:** account/grant phát sinh khi Joiner, sửa và thu hồi quyền cũ khi Mover, chặn mọi đường còn hiệu lực khi Leaver.
10. **Đối soát và audit:** lưu evidence an toàn, đo revocation latency và kiểm thử đường truy cập API thật có kiểm soát.

Các tài liệu chuẩn nền tảng hữu ích khi cần đối chiếu yêu cầu kỹ thuật:

| Tài liệu | Chủ đề |
| --- | --- |
| **RFC 6749** | OAuth 2.0 Authorization Framework. |
| **RFC 6750** | Bearer Token Usage. |
| **RFC 7636** | Proof Key for Code Exchange (PKCE). |
| **RFC 8252** | OAuth 2.0 for Native Apps. |
| **RFC 8414** | Authorization Server Metadata. |
| **RFC 9700** | OAuth 2.0 Security Best Current Practice. |
| **RFC 7009** | OAuth 2.0 Token Revocation. |
| **RFC 7662** | OAuth 2.0 Token Introspection. |
| **RFC 9068** | JWT Profile for OAuth 2.0 Access Tokens. |
| **OpenID Connect Core 1.0** | Authentication layer trên OAuth 2.0, ID token và UserInfo. |

Khi triển khai sản phẩm hoặc tuân thủ tiêu chuẩn, cần **đọc yêu cầu chính thức, cập nhật phiên bản thư viện và kiểm tra profile của nhà cung cấp**, không thay thế bằng đoạn ví dụ ngắn trong bài học.

---

**Ghi nhớ:** **OAuth 2.0 quản lý ủy quyền cho client truy cập API bằng token; OIDC bổ sung xác thực danh tính người dùng.** Hệ thống IAM phải bảo vệ cả **luồng cấp token (Authorization Code + PKCE hoặc Client Credentials theo nhu cầu), token validation, scope/audience, RBAC/ABAC, lifecycle của grant/session/credential và kiểm toán**. Trong **Joiner–Mover–Leaver**, mục tiêu không chỉ là phát token đúng lúc mà còn **ngăn quyền cũ tiếp tục có hiệu lực ở Resource Server sau khi vai trò hay quan hệ với tổ chức đã thay đổi**.
