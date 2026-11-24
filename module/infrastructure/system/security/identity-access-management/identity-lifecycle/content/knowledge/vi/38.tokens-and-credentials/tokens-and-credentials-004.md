# Client secret trong OAuth/OIDC: xác thực ứng dụng và quản lý vòng đời credential trong IAM

**Client secret** là **giá trị bí mật được chia sẻ giữa OAuth 2.0 client và Authorization Server (AS)**, có thể được sử dụng để **xác thực client** trong những tương tác phù hợp, nhất là tại **token endpoint**. Trong một ứng dụng backend, batch job hoặc service-to-service integration, secret giúp AS kiểm tra bên gọi có đang nắm credential được đăng ký cho client đó hay không. Secret **không phải danh tính của một người dùng**, **không phải access token** và **không tự cho phép client truy cập mọi tài nguyên**.

Ví dụ, dịch vụ `billing-etl-prod` đăng ký OAuth client `client-billing-prod` với IdP/Authorization Server. Khi job cần gọi `finance-api` theo quyền máy–máy, backend xác thực bằng một phương thức được AS hỗ trợ, có thể là **client ID + client secret**, để xin **access token** được giới hạn audience, scope và thời gian. API đích nhận **access token**, kiểm tra token và áp **RBAC/ABAC**; nó **không cần biết client secret**. Khi một developer chuyển nhóm, secret bị nghi lộ hoặc job retired, tổ chức phải rà soát **owner, bản sao credential, các quyền của OAuth client, các token còn sống và mọi đường cấp quyền liên quan**.

Bài thuộc chương **Token và credential** trong module **Security — Identity and Access Management (IAM) — Identity Lifecycle**. Trọng tâm của module là **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo account, cấp quyền tới rà soát và thu hồi khi quan hệ/vai trò thay đổi, kết nối **IdP, SSO, SCIM, RBAC/ABAC, service account, workload identity và kiểm toán**. Với client secret, JML của **người sở hữu/quản trị ứng dụng** và lifecycle của **machine identity** phải được quản trị liên kết nhưng **không đồng nhất**.

> **Điểm cốt lõi:** `client_id` dùng để **nhận diện client**, `client_secret` có thể dùng để **chứng minh bên gọi nắm credential của client**; **access token** thể hiện một authorization grant có điều kiện. Nếu một secret được sao chép, AS có thể khó phân biệt service hợp lệ với người đang giữ bản sao. Vì vậy **bảo mật, giới hạn quyền, rotation, revocation và audit** đều cần thiết.

## 1. Các thành phần liên quan đến client secret

Một hệ thống OAuth/OIDC thường có những vai trò sau:

| Thành phần | Vai trò | Có nên thấy client secret? |
| --- | --- | --- |
| **OAuth client** | Ứng dụng/service xin token hoặc khởi tạo flow theo cấu hình. | Chỉ thành phần **confidential** được bảo vệ và được phép giữ secret. |
| **Authorization Server (AS)** | Đăng ký client, xác thực client theo phương thức được hỗ trợ, phát token và thực thi chính sách. | Có quyền quản lý/kiểm tra secret; cách lưu trữ tùy AS. |
| **Resource Owner / End User** | Người hoặc chủ thể có quyền mà một flow đại diện, nếu flow có end-user context. | Không cần biết client secret của ứng dụng. |
| **Resource Server (RS)** | API/dịch vụ nhận access token và thực thi authorization. | Thông thường **không nhận client secret**. |
| **Identity Provider (IdP)** | Hệ thống xác thực người/workload; có thể kiêm AS trong triển khai OIDC. | Có thể quản lý client registration và secrets nếu kiêm AS. |
| **Service/technical owner** | Chịu trách nhiệm quản trị client, scopes, rotation, môi trường, incident. | Không nhất thiết được phép đọc plaintext secret để làm owner. |
| **Secrets manager / vault** | Lưu/phân phối secret theo identity và policy. | Có thể chứa credential nhưng không quyết định thay target authorization. |

### 1.1. Một client không phải luôn đại diện cho một người

Client có thể là:
- Backend web application xử lý Authorization Code flow cho người dùng.
- Machine-to-machine service dùng Client Credentials grant.
- Batch/ETL job hoặc scheduled automation.
- CI/CD service integration.
- Server-side gateway hoặc Backend for Frontend (BFF).
- Một ứng dụng công khai như SPA/mobile app, **thường không thể giữ client secret đáng tin**.

**Không đồng nhất OAuth client với service account của hệ điều hành**. Một service có thể có OS account, workload identity và một hoặc nhiều OAuth client registrations khác nhau. Ngược lại, một OAuth client dùng chung cho quá nhiều workload tạo khó khăn về owner, credential rotation và attribution.

### 1.2. Hai thuộc tính cần phân biệt

~~~text
OAuth client registration:
  client_id:     client-billing-prod           # thường là identifier công khai
  client_secret: <secret-placeholder>         # bí mật, không in/log
  allowed_grant: client_credentials
  allowed_scope: finance:summary.write
  intended_api:  finance-api
  owner:         finance-data-platform
  environment:   production
~~~

Ví dụ chỉ mang tính khái niệm; cơ chế khai báo scope/audience/owner và tên trường có thể khác tùy AS. **Tên client hay client ID không nên dùng làm credential**; chính sách tài nguyên vẫn phải xét token/role/action.

## 2. Client secret là gì và không phải là gì?

| Vật thể | Mục đích chính | Người nhận phù hợp | Rủi ro nếu bị lộ |
| --- | --- | --- | --- |
| **Client ID** | Chỉ ra đăng ký client. | AS, client và cấu hình khác. | Thường không phải bí mật; có thể hỗ trợ reconnaissance nhưng không tự xác thực. |
| **Client secret** | Một phương thức xác thực **confidential client**. | AS qua kênh bảo mật; runtime của client được phép. | Kẻ nắm secret có thể mạo danh client ở các flow/endpoint mà AS cho phép. |
| **Authorization code** | Mã tạm thời để đổi token trong Authorization Code flow. | Client và AS, gắn redirect URI/PKCE theo policy. | Có thể bị lạm dụng nếu thiếu ràng buộc/kiểm tra liên quan. |
| **Access token** | Cho resource server biết grant có quyền gọi API trong phạm vi/hạn nhất định. | Client → resource server. | Bên giữ token bearer có thể dùng token trước khi hết hạn/thu hồi. |
| **Refresh token** | Xin access token mới theo grant và chính sách của AS. | Client → AS. | Có thể duy trì truy cập lâu nếu bị đánh cắp, cần rotation/binding/revocation. |
| **OIDC ID token** | Đưa thông tin xác thực end user cho relying party. | OIDC client/relying party. | Có rủi ro xác thực/riêng tư; **không dùng làm API access token**. |
| **Private key** | Chứng minh possession trong phương thức bất đối xứng, ký client assertion hoặc mTLS. | Giữ bí mật tại client, không chuyển plaintext cho AS. | Có thể mạo danh principal cho tới khi key/trust bị revoke. |
| **Session cookie** | Duy trì phiên ứng dụng sau login. | Browser/application theo thiết kế. | Có thể gây session hijacking, khác với client secret. |

### 2.1. Secret chứng minh “đang nắm bí mật”, không chứng minh “là đúng process”

Vì là **shared secret**, bất kỳ ai có bản sao hợp lệ có thể đưa cùng secret tới AS. Không nên suy “token được phát bằng client secret ⇒ request chắc chắn tới từ Pod hợp lệ”. Những lớp bổ sung như **workload federation, workload attestation, trusted execution path, audience restriction hoặc mTLS** có thể giúp giới hạn trust, tùy thiết kế.

### 2.2. Lộ client secret không đồng nghĩa mọi user access token đã lộ

Mức ảnh hưởng tùy:
- Client được phép dùng **grant types** nào.
- Client có quyền **application-only** hay cần user consent/authorization code.
- Có PKCE, redirect URI validation, client authentication và các ràng buộc khác không.
- AS đã phát tokens nào, những scopes/roles/audiences nào.
- Có **refresh tokens**, token exchange hoặc quyền quản trị khác không.
- Attackers còn nắm authorization code/user credential hay không.

Lộ secret của app-only client có thể cho phép kẻ tấn công **xin access token mới trong quyền ứng dụng**. Với backend Authorization Code client, secret một mình thường **chưa đủ để có tokens của mọi người dùng**; nhưng vẫn là sự cố nghiêm trọng cần đánh giá.

## 3. Confidential client và public client

### 3.1. Confidential client

**Confidential client** là client có khả năng duy trì tính bí mật của credential hoặc sử dụng cách xác thực client có mức tin cậy tương ứng theo deployment và AS policy.

Ví dụ điển hình:
- Backend server do tổ chức kiểm soát.
- Service chạy trong hạ tầng server/cluster được bảo vệ.
- BFF giữ tokens và credentials phía server, không gửi vào JavaScript browser.
- Job chạy trên runner được quản trị, nếu secret được phân phối an toàn.

**Confidential không có nghĩa không thể bị tấn công**: secret vẫn có thể lộ qua repo, log, CI runner, memory dump, backup hoặc insider. Confidentiality là đặc tính thiết kế/threat model, không phải một nhãn tự bảo đảm.

### 3.2. Public client

**Public client** không thể giữ bí mật một credential dùng chung đáng tin đối với người dùng/attacker có quyền truy cập bản sao ứng dụng.

Ví dụ:
- JavaScript Single-Page Application (SPA) chạy trong browser.
- Native mobile/desktop app phân phối cho người dùng.
- CLI đã được cài trên máy người dùng, nếu ứng dụng chứa secret đóng gói chung.

**Không nhúng client secret vào frontend bundle, APK/IPA, desktop executable hoặc repository công khai**, kể cả đã obfuscate hoặc mã hóa với key nằm cùng ứng dụng. Một giá trị được đóng gói cho mọi người dùng có thể bị trích xuất và **không là client authentication secret hiệu quả**.

### 3.3. Bảng quyết định nhanh

| Kiến trúc | Có nên dùng static client secret? | Cách tiếp cận |
| --- | --- | --- |
| Backend web app giữ secrets server-side. | Có thể, nếu AS hỗ trợ và policy cho phép. | Vault, TLS, rotation, scoped grant, cân nhắc cơ chế mạnh hơn. |
| Service-to-service trong cloud. | Có thể, nhưng không nhất thiết là tốt nhất. | Ưu tiên managed identity/federation/short-lived assertion nếu khả thi. |
| Browser SPA thuần. | **Không**. | Authorization Code + PKCE, client registration kiểu public. |
| Mobile/native app phân phối cho người dùng. | **Không** nếu secret được nhúng chung. | Authorization Code + PKCE hoặc flow thích hợp. |
| BFF có browser frontend. | **Có thể ở backend BFF**, không ở browser. | BFF bảo vệ client auth và tokens phía server, cookie/session controls. |
| CI/CD runner. | Cần tránh khi có federation phù hợp. | OIDC workload federation hoặc secret vault có isolation/rotation. |
| Legacy integration chỉ hỗ trợ secret. | Có thể cần dùng tạm theo policy. | Scope hẹp, inventory, owner, rotation và migration plan. |

### 3.4. PKCE không phải một client secret

**PKCE (Proof Key for Code Exchange)** bảo vệ quá trình đổi authorization code bằng `code_verifier/code_challenge`, đặc biệt quan trọng với public clients. PKCE **không biến browser thành confidential client** và **không tạo ra shared secret lâu dài**.

Với server-side confidential client, PKCE cũng là một lớp bảo vệ bổ sung theo thiết kế và chính sách hiện đại. **Đừng chọn giữa PKCE và client authentication như thể hai cơ chế có chức năng hoàn toàn tương đương**.

## 4. Client secret xuất hiện ở đâu trong OAuth 2.0?

### 4.1. Token endpoint là vị trí thường gặp

Trong OAuth, client có thể xác thực với AS tại **token endpoint** khi:
- Đổi **authorization code** thành tokens.
- Dùng **client credentials** để xin app-only access token.
- Dùng **refresh token** để xin access token mới.
- Các grant/endpoint khác nếu profile và AS có quy định.

**Không gửi client secret tới Resource Server chỉ để gọi API.** RS thường kiểm **access token**, không xác thực OAuth client bằng client secret gốc.

### 4.2. Client Credentials grant

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Confidential client
    participant AS as Authorization server / IdP
    participant RS as Resource server
    C->>AS: POST token endpoint, client authentication + grant_type=client_credentials
    AS->>AS: Validate secret/method, allowed scope, client registration
    AS-->>C: Access token with limited audience/scope/expiry
    C->>RS: Authorization: Bearer access_token
    RS->>RS: Validate token and RBAC/ABAC/resource policy
    RS-->>C: Permit or Deny
~~~

Client Credentials grant đại diện cho **quyền của chính ứng dụng/client**, không tự gắn end-user identity. Các token/scopes do AS phát phải đáp ứng policy; client không được tự ghi `role=GlobalAdmin` trong request rồi mặc nhiên nhận quyền đó.

### 4.3. Authorization Code flow và OIDC

Một backend web app có thể:
1. Redirect user đến authorization endpoint của IdP.
2. User xác thực (MFA/SSO tùy chính sách).
3. IdP trả authorization code tới redirect URI đã đăng ký.
4. Backend đổi code thành tokens tại token endpoint, **có thể xác thực bằng client secret** và ràng buộc PKCE.
5. Backend xác minh OIDC ID token cho Authentication; dùng access token theo API/grant.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as End user
    participant B as Browser
    participant APP as Backend confidential client
    participant AS as OIDC Authorization server
    U->>B: Open application
    B->>APP: Start login
    APP-->>B: Redirect with state, PKCE challenge, OIDC nonce as appropriate
    B->>AS: Authorization request
    AS->>U: Authentication / MFA / consent if required
    AS-->>B: Redirect to registered URI with code + state
    B->>APP: Deliver code
    APP->>AS: Token request with code, PKCE verifier and client authentication
    AS-->>APP: ID token, access token; maybe refresh token
    APP->>APP: Validate state/nonce, issuer, audience and session
    APP-->>B: Server-side app session
~~~

**Không đẩy client secret vào redirect URI/browser**. `client_secret` không phải `state`, `nonce` hoặc `code_verifier`; chúng giải quyết các bài toán khác nhau.

### 4.4. Access token không trở thành client secret

Một bearer token đã được phát được dùng để **truy cập API** tới khi hết hạn/thu hồi theo policy. Client secret là thông tin dùng để **xác thực client khi xin hoặc trao đổi tokens**; lifecycle độc lập. Đổi secret **không tự bảo đảm** mọi access token đã phát bị vô hiệu hóa ngay.

## 5. Các phương thức xác thực client tại token endpoint

Các phương thức phổ biến tùy OAuth AS/OIDC provider:

| Phương thức | Cơ chế | Điểm cần biết |
| --- | --- | --- |
| **client_secret_basic** | Gửi client ID và secret bằng HTTP Basic Authentication tại token endpoint. | Thường được hỗ trợ; chỉ qua TLS, bảo vệ Authorization header/log. |
| **client_secret_post** | Gửi client ID và secret trong form body. | Không gửi qua URL query; body vẫn phải bảo vệ khỏi log/tracing. |
| **client_secret_jwt** | Tạo signed client assertion bằng HMAC dựa trên shared secret. | Cùng bản chất secret đối xứng, cần kiểm `iss/sub/aud/exp/jti` theo profile. |
| **private_key_jwt** | Client ký assertion bằng private key; AS kiểm bằng public key đã đăng ký. | Không trao plaintext private key cho AS; quản lý JWK/key rotation. |
| **tls_client_auth / self_signed_tls_client_auth** | Client authentication bằng certificate/mTLS theo profile hỗ trợ. | Kiểm chứng cert mapping, trust, PoP và lifecycle. |
| **none** | Không có client authentication theo cấu hình public client. | Phải dùng controls phù hợp: PKCE, redirect URI và các ràng buộc khác. |

Tên phương thức phổ biến của OIDC/OAuth client metadata được nêu để **hiểu khái niệm**, không giả định mọi AS đều hỗ trợ tất cả hoặc có cách cấu hình giống nhau. Phải đọc metadata/contract của **provider đang dùng** và không tự chuyển phương thức khi server không cho phép.

### 5.1. Ví dụ client_secret_basic

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.invalid
Authorization: Basic <base64-of-encoded-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=finance%3Asummary.write
~~~

- `Authorization: Basic` mang **client credential trong giá trị mã hóa Base64**, **không phải encryption**. Bắt buộc bảo vệ đường truyền bằng TLS và không ghi giá trị header trong log.
- Theo cơ chế OAuth Basic, **client ID và secret được form-encode trước khi tạo chuỗi Basic**, đặc biệt quan trọng khi có ký tự đặc biệt. Không tự nối tùy ý rồi giả định mọi secret đều chỉ có ASCII an toàn.
- `scope` là request bị **giới hạn bởi quyền đăng ký/chính sách**, không phải quyền client tự chọn tùy ý.
- Dùng endpoint minh họa; đường dẫn thực tế do provider công bố.

### 5.2. Ví dụ client_secret_post

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.invalid
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&client_id=client-billing-prod&client_secret=<percent-encoded-secret-placeholder>&scope=finance%3Asummary.write
~~~

**Không dùng query string** kiểu `GET /token?client_secret=...`. URL thường bị ghi vào web server logs, proxy access logs, monitoring và browser history. Cả header lẫn body vẫn cần **redaction** và hạn chế quyền xem trace.

### 5.3. Ví dụ response

~~~json
{
  "access_token": "<access-token-placeholder>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "finance:summary.write"
}
~~~

Đây là **response minh họa**, không bảo đảm mọi AS trả đủ/đúng các field này hoặc dùng cùng định dạng token. Các resource servers cần kiểm **issuer/audience, signature hoặc introspection, expiry và permission/resource-level policy** theo mô hình token thực tế.

### 5.4. Khi client auth thất bại

Các tình huống cần phân biệt:
- Sai secret hoặc secret đã bị revoke/expired.
- Sai `client_id`, tenant/issuer hoặc token endpoint.
- Dùng `client_secret_post` trong khi client bị cấu hình Basic-only.
- Client bị disable, grant type không được phép.
- Scope/resource không hợp lệ.
- Đồng hồ/issuer/key của phương thức assertion sai.
- Rate limit, outage hoặc TLS/network error.

**Không tự động fallback sang một client secret cũ đã bị thu hồi vì lỗi token endpoint**, và không log plaintext secret để debug.

## 6. Chọn secret hay phương thức chứng thực khác

Static client secret là một **shared credential**: dễ tích hợp nhưng khó bảo đảm không bị sao chép. Khi hệ thống hỗ trợ, có thể cân nhắc lựa chọn khác:

| Cơ chế | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- |
| **Client secret** | Tương thích rộng, dễ triển khai với confidential client. | Secret theft/reuse; phân phối/rotation và bản sao cần quản trị. |
| **private_key_jwt** | Client không cần gửi private key; có thể bảo vệ key bằng HSM/KMS. | Quản lý key pair, issuer/jti/audience và rotation. |
| **mTLS client authentication** | Chứng minh possession private key qua TLS, có thể gắn cert với client. | Certificate issuance, trust chain, proxy topology và revocation. |
| **Workload identity federation** | Giảm static cross-cloud secrets; exchange assertion/tokens ngắn hạn. | Trust policy/issuer/subject/audience phải chặt, bootstrap bị compromise vẫn nguy hiểm. |
| **Managed identity** | Platform xử lý phần lớn credential distribution/rotation theo capability. | Cloud/platform-specific; grants vẫn phải least privilege. |
| **Public client + PKCE** | Phù hợp SPA/mobile không thể giữ secret. | Không phải client auth mạnh như confidential client; cần safeguards cho redirect/authorization. |

**Không có phương án nào miễn kiểm RBAC/ABAC, token validation và owner lifecycle.** Một workload token thời hạn ngắn nhưng trust policy cho mọi pipeline trong org vẫn có thể cấp quyền quá rộng.

### 6.1. Chỉ dùng client secret khi có thể giữ bí mật

Câu hỏi trước khi chọn:
1. Client chạy ở đâu? Browser, mobile, server, CI runner hay Kubernetes?
2. Có thể bảo vệ secret khỏi người dùng cuối và khỏi process không được phép không?
3. Có hỗ trợ managed identity, mTLS, private-key JWT hoặc federation không?
4. Cần bảo đảm client attestation hay chỉ possession của một shared value?
5. Có rotation/rollover không gián đoạn?
6. Có thể hạn chế network, target, scope và environment không?
7. Có owner thực và cơ chế decommission không?

### 6.2. Không gọi mọi giải pháp là “passwordless”

Một client dùng `private_key_jwt` có thể không còn static **password-like shared secret**, nhưng vẫn dựa vào **private key** cần bảo vệ. Một managed identity giảm công việc lưu secret tại ứng dụng, nhưng vẫn có trust bootstrap/token issuance và quyền có thể bị lạm dụng nếu runtime bị chiếm.

## 7. Client registration: phát hành secret theo identity và policy

Một client secret chỉ có ý nghĩa trong **client registration** tương ứng ở AS. Đăng ký có thể gồm:

| Nhóm metadata | Ví dụ | Vì sao quan trọng? |
| --- | --- | --- |
| **Client identity** | `client_id`, tên hiển thị, owner, service catalog reference. | Attribution và quản trị vòng đời. |
| **Client type/auth method** | confidential và `client_secret_basic`. | Tránh dùng secret sai ngữ cảnh. |
| **Allowed grant types** | `client_credentials` hoặc `authorization_code`. | Giới hạn cách xin token. |
| **Redirect URI** | Callback chính xác cho Authorization Code. | Ngăn token/code bị chuyển tới endpoint trái phép. |
| **Scopes/resources** | Quyền ứng dụng/API và resource audience. | Least privilege theo action/resource. |
| **Environment/tenant** | Production, staging, tenant-vn. | Tránh secret dev có quyền prod. |
| **Secret lifecycle** | Issue time, expiry, rotation plan. | Giảm thời gian credential sống vô hạn. |
| **Approval/risk** | Owner, Security approval với quyền nhạy cảm. | Tránh tự tạo app-only GlobalAdmin. |
| **Status** | Active, Suspended, Retired. | Revoke client access khi không còn căn cứ. |

### 7.1. Service identity và OAuth client không nhất thiết 1–1

Có thể:
- Một workload có **một client registration riêng cho từng target API/trust boundary**, hoặc
- Một client đăng ký được dùng bởi nhiều instances cùng logical service nếu được thiết kế hợp lý.

Không dùng **một client secret chung cho development và production** hoặc cho unrelated services chỉ để đỡ tạo registration. Nếu nhiều services chia sẻ một secret, khó phân biệt actor và khó rotate khi một workload bị xâm nhập.

### 7.2. Không tự cho developer xin scopes tùy ý

Một developer có quyền tạo OAuth app không nhất thiết được cấp `payments:refund-all`, `directory:write-all` hay quyền quản trị mọi người dùng. **Application permission assignment**, admin consent hoặc role grant phải được **risk-based approval/SoD** theo policy, tách biệt với việc tạo client ID/secret.

## 8. Tạo secret: entropy, random và khả năng dự đoán

Client secret cần được sinh bằng **cryptographically secure random generator** hoặc qua cơ chế của AS/secret management platform. Đừng chọn:
- Tên service + năm hiện tại.
- Chuỗi `secret123` hoặc ID được hash.
- Một password dùng chung cho nhiều clients.
- Một giá trị lưu nguyên trong source code và nhân bản qua môi trường.
- Chuỗi dễ đoán được tự tạo từ timestamp/hostname.

### 8.1. Không có độ dài chung cho mọi provider

Mức entropy/định dạng phụ thuộc AS, client authentication method và yêu cầu security. Dùng **provider-generated high-entropy secrets** và cấu hình độ dài/thuộc tính theo policy; không suy một độ dài cố định là đủ cho mọi nền tảng.

### 8.2. Client secret không nhất thiết phải con người ghi nhớ

Một machine client có thể nhận secret từ vault bằng workload identity. Không cần secret ngắn hoặc dễ gõ. Nếu người phải copy secret vào UI, đó là một **distribution/operational risk** cần hạn chế và theo dõi.

### 8.3. One-time display và secret reference

Nhiều hệ thống chỉ hiển thị secret plaintext **một lần lúc tạo**. Điều này phù hợp với cách vận hành an toàn nhưng khiến mất secret phải **tạo credential mới/rotate**, không trông chờ “show again” hoặc backup plaintext không quản lý.

~~~text
Credential metadata (có thể lưu):
  credentialId: cred-billing-v3
  clientId: client-billing-prod
  createdAt: 2026-11-20T03:00:00Z
  expiresAt: 2027-02-20T03:00:00Z
  vaultRef: secret://finance/billing/oauth-client-v3
  ownerTeam: finance-data-platform

KHÔNG đưa vào inventory/log:
  client_secret plaintext
  access_token đầy đủ
  private key / full session cookie
~~~

`secret://...` chỉ là **tham chiếu minh họa**, không phải URI chuẩn cho mọi vault.

## 9. Lưu trữ và phân phối client secret

### 9.1. Nguồn lưu ưu tiên

Tùy hạ tầng, dùng:
- Secrets manager/vault có IAM, audit, access policies.
- Secret store tích hợp với orchestrator, có bảo vệ encryption-at-rest và quyền runtime.
- Platform-managed client credentials.
- HSM/KMS khi cần tạo/chứng thực bằng khóa thay vì shared secret.

**Vault không tự bảo đảm secret an toàn** nếu workload có `secrets:read-all`, mọi developer đều export được plaintext hoặc secret được copy vào log.

### 9.2. Không lưu ở những nơi không dành cho secret

- Repository Git hoặc template IaC chứa plaintext.
- Frontend JavaScript, mobile/desktop app package.
- Dockerfile/image layer và build artifact công khai.
- Ticket, email, chat và tài liệu wiki không có secret controls.
- Log request/response, APM span và crash dump.
- URL query string, bookmark hoặc clipboard tự động chia sẻ.
- CI/CD variable không được bảo vệ, có thể in trong logs/forked pipelines.
- File backup hoặc snapshot không có encryption/access control phù hợp.

### 9.3. Environment variable: tiện nhưng không phải vault

Ứng dụng có thể đọc secret qua environment variable sau khi platform phân phối. Tuy nhiên giá trị vẫn có thể lộ qua:
- Process inspection/debug.
- Crash dump hoặc diagnostic tooling.
- Lệnh in environment.
- Child process inheritance.
- CI output hoặc logs khi bật verbose.
- Cấu hình không được bảo vệ.

Dùng env var chỉ là **một phương tiện phân phối tới runtime**; vẫn cần **nguồn vault, access restrictions, rotation, least privilege và redaction**.

### 9.4. Kubernetes Secrets không tự giải quyết mọi bài toán

Kubernetes Secret có thể chứa credential để Pod sử dụng, nhưng:
- Quyền đọc Secret cần giới hạn bằng Kubernetes RBAC.
- Cần encryption-at-rest/etcd protection theo cấu hình.
- Workloads/containers có thể đọc Secret đã mount.
- CI/CD và operator có thể lộ secret qua YAML/lệnh debug.
- Đổi Secret không đồng nghĩa mọi process đã tải lại và AS đã rotate.
- ServiceAccount/Pod permissions có thể mở đường đọc Secret khác.

Với workload federation/managed identity phù hợp, có thể **tránh phải phân phối static client secret** qua cluster.

## 10. CI/CD, Java backend và cấu hình runtime

### 10.1. Pipeline nên nhận identity thay vì secret của nhân viên

Không dùng OAuth client secret chứa trong profile của một engineer để deploy production. Khi người đó Mover/Leaver, pipeline có thể bị gián đoạn hoặc vẫn giữ credential đã biết. Thay vào đó:
- Dùng workload identity/federation cho CI runner khi hỗ trợ.
- Nếu phải dùng secret, lấy từ vault theo môi trường và job identity.
- Chỉ cho protected branches/environments/workflows nhận production credentials.
- Cần independent approval trước deployment nếu SoD policy yêu cầu.
- Không cho build từ fork/PR không tin cậy đọc secrets.
- Redact log, disable unneeded command tracing và giới hạn artifact retention.

### 10.2. Ví dụ cấu hình Spring Security OAuth client

~~~yaml
# application.yml - sơ đồ cấu hình minh họa, không chứa secret thật
spring:
  security:
    oauth2:
      client:
        registration:
          billing-api:
            provider: internal-idp
            client-id: "<runtime-client-id>"
            client-secret: "<runtime-injected-secret>"
            authorization-grant-type: client_credentials
        provider:
          internal-idp:
            token-uri: "https://idp.example.invalid/oauth2/token"
~~~

Trong ứng dụng Java/Spring thực, hai giá trị `client-id` và `client-secret` nên được **bind qua runtime configuration/secret store có quyền kiểm soát**, không commit giá trị thật vào YAML. Cấu hình client authentication method (Basic/Post hoặc cơ chế khác) phải phù hợp provider và phiên bản framework. Đoạn trên **không đủ để chạy** nếu thiếu cấu hình HTTP client, resource scopes, connection/TLS và runtime secret injection.

### 10.3. Mã Java minh họa đọc secret

~~~java
// Pseudocode Java: ví dụ về ranh giới trách nhiệm,
// không dùng để in secret hoặc tự triển khai OAuth protocol.
String clientId = runtimeConfig.require("BILLING_OAUTH_CLIENT_ID");
SecretHandle secret = secretsManager.open("finance/billing/oauth-client");

try {
    oauthClient.authenticateAtTokenEndpoint(
        clientId,
        secret,
        requestedScopes,
        tokenEndpointFromTrustedProviderMetadata
    );
} finally {
    secret.close();
}
~~~

**`SecretHandle`, `secretsManager` và `oauthClient` là API giả định**, không phải class JDK/Spring có sẵn. Trong thực tế nên dùng **OAuth client library đã được duy trì** để xử lý encoding, token caching, TLS, refresh, retry, log redaction và endpoint authentication. Không tự viết parser hoặc ghép URL chứa secret.

### 10.4. Bảo vệ HTTP logging

Ngay cả với thư viện chuẩn, middleware có thể log request body/header. Khi debug `invalid_client`:
- Chỉ log `client_id`, credential reference/version, endpoint identifier, error code và correlation ID.
- Không log `Authorization` header chứa Basic.
- Không log `client_secret` trong form body.
- Không log toàn bộ token response.
- Kiểm tra APM/proxy/tracing middleware có redaction thật sự.
- Giới hạn quyền truy cập log và retention.

### 10.5. Debug mà không copy secret vào chat

Một hướng điều tra an toàn:
1. Xác nhận client ID và đúng AS/tenant.
2. Xác nhận credential **version/expiry/status** qua metadata.
3. Xác nhận phương thức client authentication cấu hình.
4. Kiểm tra clock/TLS/network/AS status.
5. Kiểm tra grant type và scope được phép.
6. Dùng test với secret đã được bảo vệ trong runtime, không đưa plaintext vào ticket.
7. Nếu nghi lộ, chuyển sang incident response/rotation.

## 11. Rotation client secret: thay credential mà không ngừng dịch vụ

**Rotation** là quá trình tạo secret mới, chuyển các workloads sang secret mới và **thu hồi secret cũ**, có kiểm chứng. Thường khó nhất không phải nút “Generate secret” mà là **xác định mọi nơi đang sử dụng**.

### 11.1. Kế hoạch xoay vòng có kiểm soát

1. **Inventory** client ID, owner, target AS, các replicas/jobs/environments và credential references.
2. Kiểm tra AS có hỗ trợ **nhiều active secrets** hoặc grace period không.
3. Tạo secret mới với entropy và expiry theo policy.
4. Lưu secret mới trong vault, gán credential/version ID.
5. Phân phối tới workloads đích qua pipeline đáng tin.
6. Chuyển từng nhóm instances và xác minh token acquisition thành công.
7. Kiểm tra API authorization với scope/resource **hợp lệ**.
8. Theo dõi AS sign-in/token issuance bằng credential version nếu provider có telemetry.
9. Đảm bảo không workload được phê duyệt nào còn dùng secret cũ.
10. Thu hồi secret cũ và kiểm tra **old secret không được AS chấp nhận**.
11. Reconcile grants/tokens còn sống và cập nhật inventory/audit.

~~~mermaid
flowchart TD
    A["Credential V1 đang active"] --> B["Tạo V2 trong AS + vault"]
    B --> C["Phân phối V2 tới workloads đã xác minh"]
    C --> D["Canary/rollout + token endpoint test"]
    D --> E{"Tất cả instances hợp lệ dùng V2?"}
    E -->|Không| F["Remediate dependencies; không xóa V1 bừa"]
    F --> D
    E -->|Có| G["Disable/revoke V1"]
    G --> H["Readback: V1 rejected, V2 works"]
    H --> I["Audit, owner acknowledgement, next rotation"]
~~~

### 11.2. Khi AS chỉ cho một secret active

Nếu provider chỉ hỗ trợ một secret mà không có overlap:
- Cần **maintenance/cutover plan**, sự chuẩn bị ở mọi consumers và rollback policy.
- Cân nhắc tạo client registration mới rồi chuyển từng workload nếu quyền/grants cho phép và đáp ứng risk.
- Không âm thầm dừng production rồi tuyên bố rotation là “zero downtime”.
- Thực hiện test trong staging hoặc môi trường cô lập tương ứng.

### 11.3. Không giữ secret cũ mãi để “rollback”

Một secret cũ active vô hạn làm tăng attack surface. Rollback phải có **thời hạn, owner và phương án xử lý**. Nếu V1 đã bị nghi lộ, **không khôi phục V1** để sửa lỗi rollout; tạo credential mới và khôi phục trong giới hạn an toàn.

### 11.4. Rotation không chỉ là expiry metadata

AS có thể lưu `expiresAt` cho secret, nhưng runtime có thể cache secret cũ, hoặc một bản sao khác chưa cập nhật. Cần kiểm tra:
- Credential cũ thực sự bị AS từ chối.
- Ứng dụng hợp lệ dùng V2.
- Không có shadow clients/secrets ngoài inventory.
- Các tokens cũ còn sống được xử lý theo risk.
- Quyền target không bị mở rộng ngoài scope khi chuyển registration.

## 12. Expiration, revocation, disable client và token validity

Bốn thay đổi khác nhau:

| Thao tác | Tác động chính | Không được suy ra |
| --- | --- | --- |
| **Secret expires** | AS ngừng chấp nhận secret đã quá hạn theo cấu hình. | Mọi access token đang sống bị chặn ngay. |
| **Secret revoked/deleted** | Secret cũ không còn được dùng cho client authentication. | Client không còn credential khác hoặc không còn token cũ. |
| **Client disabled/registration removed** | AS hạn chế/ngừng tương tác của client theo policy. | RS ở mọi nơi ngừng chấp nhận JWT tự chứa tức thì. |
| **Token/session revoked** | Hủy một grant/token/session theo khả năng. | Mọi resource server offline đều lập tức nhận sự kiện. |
| **Entitlement grant removed** | Client/principal không còn quyền tại resource/policy. | Token/authorization cache cũ chắc chắn đã hết. |

### 12.1. Một tình huống dư quyền

~~~text
09:00 Client dùng secret V1 xin access token có exp=10:00
09:10 Security phát hiện V1 bị lộ
09:12 AS revoke V1
09:15 Kẻ tấn công thử dùng V1 xin token mới -> invalid_client
09:20 Access token đã phát lúc 09:00 vẫn được RS chấp nhận,
      nếu RS chỉ kiểm chữ ký/exp và không re-evaluate quyền.
10:00 Token mới hết hạn
~~~

**Revoke client secret ngăn một đường xin token mới**, nhưng có thể cần **revoke access/refresh tokens, điều chỉnh target authorization và session control** để dừng quyền đã phát. Khả năng hủy JWT ngay phụ thuộc kiến trúc token, AS/RS và cache.

### 12.2. Token TTL và kiểm soát quyền runtime

Giảm access-token lifetime có thể giới hạn cửa sổ tồn dư, nhưng không thay:
- Introspection hoặc authorization check hiện hành khi thích hợp.
- Event-driven role revocation.
- Session invalidation.
- Audience/scope enforcement.
- Resource/tenant-level ABAC.
- Detection và containment khi client identity bị xâm nhập.

### 12.3. Đừng hiểu `invalid_client` là ứng dụng đã bị xóa

`invalid_client` ở token endpoint có thể do secret sai, auth method sai, client bị disable hoặc vấn đề registration khác. Cần phân biệt **authentication failure** với **authorization denial** như scope/permissions không đủ, và với lỗi mạng/rate limiting.

## 13. Phát hiện và ứng phó khi client secret bị lộ

Các nguồn lộ phổ biến:
- Commit Git, pull request, artifact và dependency cache.
- CI log/terminal output.
- Kubernetes Secret/Pod environment bị đọc trái phép.
- Server log, APM trace, support bundle.
- Ticket/chat/email hoặc screenshot.
- Developer laptop bị compromise.
- Memory/core dump.
- Docker image layer hoặc infrastructure template.
- Shared credential được copy giữa đội/environments.

### 13.1. Xử lý theo thứ tự ưu tiên

~~~mermaid
flowchart TD
    L["Suspected client secret exposure"] --> I["Identify client, AS, owner, credential version"]
    I --> R["Assess grants, scopes, tenants, token issuance and blast radius"]
    R --> C["Contain: revoke/disable affected secret and access path"]
    C --> N["Issue clean replacement via protected channel"]
    N --> A["Rotate workloads, verify token acquisition and API behavior"]
    A --> T["Review existing access/refresh tokens, sessions and target grants"]
    T --> H["Hunt misuse: anomalous token requests, new apps/roles, resources"]
    H --> V["Readback, audit, incident closure and root-cause fixes"]
~~~

Trong tình huống khẩn, containment có thể được kích hoạt ngay sau khi xác định credential, **không chờ inventory hoàn hảo**. Nếu revoke làm dừng một dịch vụ trọng yếu, người điều phối incident phải cân bằng **ngăn lạm dụng và an toàn vận hành**, theo playbook có owner và quyền quyết định rõ.

### 13.2. Những câu hỏi điều tra

1. Secret của client nào, môi trường và tenant nào?
2. Secret thực sự hiện diện ở đâu và từ khi nào?
3. AS còn chấp nhận secret không, hay đã revoke?
4. Client có `client_credentials` và quyền app-only nhạy cảm không?
5. Có token requests bất thường theo IP, vùng, thời gian, agent hoặc source workload không?
6. Scopes/permissions có bị mở rộng hay client registration bị chỉnh?
7. Có access/refresh tokens hoặc sessions đã phát trước containment còn hoạt động không?
8. API target có log hành động ngoài business purpose không?
9. Secret được copy sang workloads khác hoặc shadow CI pipelines không?
10. Có compromise của runtime/issuer trust khiến attacker xin credential mới dù đã rotation không?

### 13.3. Rotation không giải quyết attacker đang chiếm workload

Nếu kẻ tấn công vẫn kiểm soát runtime/CI runner và có quyền đọc vault, họ có thể lấy **V2** ngay khi được cấp. Cần xử lý **initial access, host/container compromise, vault permissions, deployment/trust policy và secrets distribution**, không chỉ thay một chuỗi.

### 13.4. Không “sửa log” để che lộ secret

Nếu secret đã xuất hiện trong repository hoặc logs, phải coi nó **đã có khả năng bị lộ** theo risk, thực hiện rotation/revocation cần thiết và xử lý artifacts/permissions/retention theo policy. Không xóa audit evidence của sự cố một cách trái quy trình; cần redaction/bảo vệ logs đúng thẩm quyền.

## 14. Machine identity, service account và quyền sở hữu client secret

Một OAuth client thường gắn với một **non-human identity** hoặc một backend app:

~~~text
Service catalog entry:   billing-etl
Logical workload ID:     workload-billing-etl-prod
Cloud/OS account:        workload runtime principal
OAuth registration:      client-billing-prod
Credential metadata:     billing-client-secret-v3
Vault reference:         finance/billing/oauth-client
Target application:      finance-api
Owner team:              finance-data-platform
Approver:                finance-api/resource owner
~~~

Bản đồ này giúp trả lời **ai có quyền đổi secret**, ai vận hành job và ai xác nhận role/scope có căn cứ. Không dựa duy nhất vào display name hoặc email người tạo client.

### 14.1. Người “tạo secret” không mặc nhiên là owner vĩnh viễn

Một nhân viên có thể tạo registration trong giai đoạn khởi tạo. Khi họ chuyển công việc, service vẫn hoạt động. Ownership nên gắn **team/service catalog**, với người chịu trách nhiệm thực và quyền quản trị được cập nhật theo JML.

### 14.2. Ai được xem secret?

**Owner không mặc nhiên cần quyền đọc plaintext secret.** Có thể cho owner:
- Được xem metadata/expiry/usage.
- Yêu cầu rotation theo policy.
- Phê duyệt thay đổi quyền.
- Theo dõi vault audit.
- Triển khai qua pipeline mà không bao giờ thấy giá trị thực.

Điều này giảm nguy cơ credential bị copy bởi người quản trị, nhất là khi owner Mover/Leaver.

### 14.3. Tránh dùng human password thay client secret

Không cho automation dùng username/password của developer làm credential thường xuyên để xin token. Điều đó biến human account thành dependency vận hành, phá MFA/SSO/JML và làm mất attribution của workload. Hãy dùng **client/workload identity riêng** và cơ chế client authentication phù hợp.

## 15. Joiner: người mới và secret của workload

Khi một kỹ sư Joiner vào team Finance:
- HRIS/contractor registry xác nhận identity và effective assignment.
- IAM/IdP tạo named human account, gán MFA/SSO và quyền hỗ trợ tối thiểu.
- Engineer có thể được cấp quyền **xem metadata client, deploy hoặc yêu cầu rotation** theo role.
- Quyền đọc/export secret production cần kiểm soát đặc biệt và không phải mặc định.
- Không gửi secret qua chat như cách “onboarding nhanh”.
- Nếu cần vận hành production, dùng PAM/JIT hoặc CI workflow có phê duyệt, tránh human trực tiếp giữ secret.
- Có audit người nào tạo/đổi credential, thông qua request nào.

### 15.1. Machine Joiner là lifecycle khác

Một service mới phải:
1. Có **business/service owner** và purpose.
2. Đăng ký workload/client theo environment, tenant, app API.
3. Định nghĩa grant type, scopes, role và token method.
4. Tạo credential phù hợp hoặc federation trust.
5. Lưu/phân phối secret an toàn nếu dùng.
6. Test token acquisition và API authorization.
7. Đăng ký rotation, expiry và access recertification.
8. Xác minh **negative permissions** ngoài scope bị chặn.

**Human Joiner không đồng nghĩa tự động được phép đọc client secret** của mọi service trong team.

## 16. Mover: thay đổi owner, service role và quyền quản trị

**Mover** thay đổi vị trí, phòng ban, team hoặc dự án. Khi một engineer phụ trách `billing-etl` chuyển nhóm, cần tách hai luồng:

| Luồng | Hành động phù hợp |
| --- | --- |
| **Human Mover** | Thu hồi quyền cá nhân ở vault, IdP admin, OAuth registration management, CI/CD, cloud IAM nếu hết căn cứ. |
| **Service continuity** | Giữ OAuth client đang phục vụ job hợp lệ, nhưng xác nhận owner/team mới. |
| **Credential exposure review** | Đánh giá người cũ có thể đã xem/copy secret không; rotate nếu cần theo risk. |
| **Entitlement review** | Scopes/role và target còn phù hợp với service không? |
| **Approval route change** | Thay approver/sponsor nếu người cũ không còn authority. |
| **Audit/reconciliation** | Kiểm tra quyền người cũ đã mất, client/app access đúng desired state. |

### 16.1. Không chờ cấp quyền mới mới gỡ quyền cũ

Nếu engineer không còn có nhiệm vụ quản trị production secrets, gỡ vault access theo **Mover effectiveAt**, không giữ quyền cũ cho đến khi manager mới approve role khác. Nếu cần bàn giao, tạo exception hẹp/time-bound riêng có authority.

### 16.2. Service chuyển môi trường

Nếu workload chuyển từ staging sang production:
- Không copy secret staging rồi tăng scope thành production.
- Đánh giá registration/client identity riêng theo trust boundary.
- Gắn owner và approval đúng production.
- Tách credential/vault/issuer/tenant.
- Thu hồi staging grants không còn cần sau cutover.
- Kiểm tra token audience, resource scope và negative tests.

## 17. Leaver: nhân viên nghỉ không đồng nghĩa service ngừng

Khi người từng quản lý client secret rời tổ chức:
1. Disable human IdP/SSO và privileged accounts theo chính sách.
2. Gỡ quyền người đó ở vault, app registration, CI/CD, deployment, cloud roles và monitoring.
3. Thu hồi personal access tokens, SSH keys và delegated approvals.
4. Xác định họ **từng có khả năng biết/export secret nào**.
5. Rotate/revoke secrets có rủi ro cùng kế hoạch giữ dịch vụ hoạt động.
6. Bàn giao owner/team, escalation và rotation authority.
7. Kiểm tra access tokens/sessions/target grants có liên quan.
8. Đối soát quyền quản trị trực tiếp/gián tiếp và audit sau Leaver.

### 17.1. Đừng xóa client registration đang dùng chỉ vì creator nghỉ

Client `billing-etl-prod` vẫn có thể là một machine identity hợp lệ. Xóa registration đột ngột sẽ làm service không xin được token và có thể ngừng xử lý giao dịch. Hành động đúng là **offboard người**, đánh giá exposure và quản lý service owner riêng.

### 17.2. Khi client/service thật sự retired

Nếu `billing-etl` ngừng hoạt động:
- Disable application/client credential ở AS.
- Revoke all secrets, client assertions/trust bindings và OAuth grants cần thu hồi.
- Thu hồi app-only roles, resource permissions và direct grants tại target.
- Ngừng CI pipelines, scheduled tasks và secret synchronization có thể tái cấp credential.
- Xử lý tokens/sessions còn sống theo risk và khả năng.
- Readback desired vs actual và kiểm tra không xin token mới hoặc gọi API trái scope được.
- Giữ audit evidence theo retention policy.

### 17.3. Rehire không dùng lại secret cũ

Kỹ sư tái tuyển chỉ được cấp role quản trị dựa trên assignment mới và approval hiện tại. Không tự khôi phục quyền vào client secrets đã từng biết, hoặc trạng thái vault role từ lần làm việc trước.

## 18. IdP, SSO, SCIM và OAuth client credential

### 18.1. IdP/SSO và client authentication

IdP có thể đồng thời:
- Xác thực human users qua SSO/OIDC/SAML.
- Là OAuth/OIDC Authorization Server cho backend apps.
- Quản lý client registration, client secrets và access/refresh tokens.
- Phát hành workload assertions hoặc hỗ trợ federation.
- Cấp role/groups/claims theo policy.

**Client secret không phải SSO password của người dùng.** Trong Client Credentials grant, không nhất thiết có browser, redirect hay human session; còn trong Authorization Code, người dùng xác thực qua IdP nhưng **backend client authentication** là lớp riêng.

### 18.2. SCIM không phải chuẩn chung để rotate OAuth client secret

**SCIM 2.0** chuẩn hóa những thao tác provisioning phổ biến cho **User/Group**, kèm extension theo provider. Nó **không chuẩn hóa chung quy trình tạo/rotate/revoke client secret của mọi OAuth client**. Việc quản trị OAuth registrations thường qua **Authorization Server admin API/console, dynamic client registration theo capability, secret manager và workflow riêng**.

Một User/Group bị SCIM deprovision không tự khiến client secret khác của một service bị revoke. Phải inventory và xử lý **đúng credential source**.

### 18.3. Application assignment khác client secret

Một user có thể được assign ứng dụng qua IdP/SSO; một service OAuth client lại có **app-only roles/scopes** độc lập. Gỡ user khỏi app group chưa chắc gỡ quyền application-only của service. Ngược lại, revoke client secret có thể làm service ngừng gọi API nhưng không chặn SSO của user trên app.

## 19. RBAC/ABAC: client secret không thay thế authorization

Một AS xác thực đúng client rồi có thể phát access token theo **allowed grants**. Resource Server vẫn phải đánh giá:
- Token issuer và audience đúng.
- Token expiry/signature hoặc introspection hợp lệ.
- Scopes/app roles do AS cấp có quyền action không.
- Resource/tenant/object thuộc phạm vi nào.
- Subject/client có đang active, service còn cần quyền không.
- Policy ABAC theo environment, classification và context.
- SoD/transaction constraints khi có.
- Grant có bị revoke hoặc token/session đã bị vô hiệu hóa không.

~~~text
permitWriteSummary =
    authenticatedClientId == "client-billing-prod"
    AND token.issuer == trustedAS
    AND token.audience == "finance-api"
    AND token.scope contains "finance:summary.write"
    AND resource.tenantId == "tenant-vn"
    AND resource.table == "monthly_summary"
    AND clientLifecycleState == ACTIVE
    AND currentPolicyAllows("summary:write", resource)
~~~

Đây là **pseudocode khái niệm**. Trong thực tế không nên tin client-supplied `tenantId` hoặc `role` chỉ từ header/body; phải lấy context/claims từ nguồn đáng tin và kiểm resource bên server.

### 19.1. Không tự nâng scope bằng request token

Nếu đăng ký chỉ cho `report:read`, gửi `scope=finance:admin` không phải bằng chứng quyền admin. AS phải giới hạn token dựa trên **grant/role đã phê duyệt**, không theo ý muốn client.

### 19.2. Least privilege khi cấp application permission

- Tách `finance:summary.read` và `finance:summary.write`.
- Không cấp `directory:write-all` cho một job chỉ đọc báo cáo.
- Giới hạn production vs staging và tenant.
- Tránh secret có quyền mint tokens cho nhiều resources không liên quan.
- Kiểm tra direct grants/resource policies ngoài OAuth scope.
- Dùng thời hạn và review cho đặc quyền tạm.
- Xét khả năng client tự tạo secret mới hoặc tự gán role; đó là đường privilege escalation.

### 19.3. SoD trong app-only automation

Một pipeline có client secret cho cả **build, approve release, deploy production và chỉnh IAM policy** có thể tự hoàn thành chuỗi hành động nhạy cảm. Cần phân tách identities/authorities và independent approval theo risk. Một token machine-to-machine không miễn kiểm SoD chỉ vì không có end user.

## 20. Quản trị đặc quyền: PAM, JIT và client secret

### 20.1. PAM chủ yếu kiểm soát privileged use, không chỉ secret storage

Secrets manager/vault giúp lưu secret; **PAM** có thể thêm checkout, approval, session controls, JIT activation, rotation và audit cho privileged workflows tùy sản phẩm. Nếu client secret có khả năng xin **cloud-admin app-only tokens**, đây là một privileged credential đáng được quản trị nghiêm ngặt.

### 20.2. Đặc quyền tạm phải có hạn thật sự

Một secret dùng dài hạn cho service có thể vẫn được phép giữ trong vault theo policy, nhưng quyền `GlobalAdmin` dành cho một incident nên được cấp **time-bound** bằng JIT/grant/policy riêng, không đổi cả ứng dụng sang standing admin rồi quên hạ quyền.

Khi incident đóng:
- Revoke temporary app role/grant.
- Hạ quyền client nếu đã được mở rộng.
- Revoke/rotate credential nếu có exposure hoặc policy yêu cầu.
- Kiểm tra access token/session còn cho privileged action không.
- Readback target and audit.

### 20.3. Break-glass không phải phát client secret admin qua chat

Khi IdP/SSO/PAM outage, đường recovery cần được **thiết kế và kiểm thử trước**, có credential custody, người thực sự dùng được nhận diện, logging hoặc evidence dự phòng. Không gửi OAuth admin client secret vào nhóm chat để “cả đội tạm dùng”. Nếu recovery workflow dùng non-human identity, vẫn phải có owner, scope, duration, audit và post-use credential controls.

## 21. Tách môi trường, tenant và resource audience

Một secret production bị lộ trong dev environment sẽ tạo đường tấn công xuyên môi trường nếu registration/trust/scope dùng chung.

| Thuộc tính | Development | Production |
| --- | --- | --- |
| Client registration | `client-billing-dev` | `client-billing-prod` |
| Secret/vault path | Dev-scoped. | Protected production secret store. |
| Token issuer/tenant | Dev issuer/tenant theo thiết kế. | Prod issuer/tenant tin cậy. |
| API audience | Dev finance API. | Prod finance API. |
| Scopes | Test/data giả lập. | Chỉ production resources được approve. |
| CI job authority | Dev pipeline/runner. | Protected production environment/workflow. |
| Approval/rotation | Dev owner. | Production owner, Security khi risk yêu cầu. |
| Audit | Development telemetry. | Protected production audit. |

### 21.1. Một tên có đuôi “prod” chưa tạo security boundary

Nếu dev secret vẫn có thể xin token cho production resource server do misconfigured issuer/trust, tên hiển thị không bảo vệ được. Cần **issuer, audience, registration, permission và resource-side tenant policy** thực sự tách biệt.

### 21.2. Multi-tenant applications

Một backend có thể phục vụ nhiều tenants. Client authentication thành công chưa cho phép nó đọc mọi tenant. Phải xác định:
- Client được phép xử lý tenant nào.
- Flow app-only hay delegated on-behalf-of user.
- Token audience/scopes có đủ không.
- Resource ownership và object-level policy.
- Tenant context có được xác minh server-side không.
- Nếu client đóng vai trò deputy cho user, user authorization có được kiểm tra không.

## 22. Rủi ro confused deputy và client secret của backend

Một backend có secret app-only mạnh có thể trở thành **confused deputy** nếu nó dùng quyền của mình để thực hiện yêu cầu của user mà không kiểm tra user authorization.

Ví dụ:
- Lan chỉ được xem `document-1`.
- `portal-api` giữ secret xin access token `documents:read-all`.
- Frontend gửi `documentId=document-999`.
- Backend dùng app-only token để đọc tài liệu mà **không kiểm quyền của Lan**.

**Client secret đúng và access token hợp lệ không ngăn được lỗi này.**

### 22.1. Phương án kiểm soát

- Resource API kiểm authorization theo **end-user context** khi thao tác có ủy quyền người dùng.
- Dùng delegated/OBO flow hoặc token exchange khi được hỗ trợ và đúng trust policy.
- Giới hạn app-only permissions tới nhiệm vụ backend thực sự cần.
- Kiểm object/tenant permission tại resource, không chỉ gateway.
- Không tin `userId` hoặc `tenantId` do browser tự khai.
- Audit **actor workload** và **actor human** khi cả hai liên quan.

### 22.2. App-only không phải luôn sai

Một batch ETL độc lập thực hiện báo cáo định kỳ có thể chính đáng dùng app-only token, không có người dùng cuối. Điều quan trọng là **đúng authorization model**, chứ không phải yêu cầu mọi request của máy đều mang một user token.

## 23. State machine cho credential và OAuth client

**Client registration**, **client secret**, **token** và **service lifecycle** có thể có những trạng thái độc lập:

| Đối tượng | State minh họa | Ý nghĩa |
| --- | --- | --- |
| Client registration | REGISTERED, ACTIVE, DISABLED, RETIRED | Client còn có thể xin token theo policy không. |
| Client secret | CREATED, ACTIVE, ROTATING, REVOKED, EXPIRED | Credential cụ thể còn được AS chấp nhận không. |
| Workload/service | DEPLOYED, CHANGED, SUSPENDED, RETIRED | Service có còn căn cứ kinh doanh không. |
| Access token | ISSUED, VALID, EXPIRED, REVOKED/INVALID | Resource server còn chấp nhận token theo cơ chế không. |
| Entitlement | REQUESTED, APPROVED, PROVISIONED, REMOVED, VERIFIED | Quyền hiện có tại target có đúng desired state không. |
| JML human owner | JOINER, MOVER, LEAVER | Ai còn thẩm quyền quản lý registration/secret. |

Đây là các **state khái niệm**, không phải enum chuẩn OAuth, OIDC, SCIM hoặc một sản phẩm.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> ACTIVE: securely issued to confidential client
    ACTIVE --> ROTATING: issue replacement V2
    ROTATING --> ACTIVE: V2 works; V1 retired
    ACTIVE --> SUSPENDED: compromise/control failure
    SUSPENDED --> REVOKED: permanent revoke
    ACTIVE --> REVOKED: decommission or emergency
    ACTIVE --> EXPIRED: expiry time reached
    EXPIRED --> [*]
    REVOKED --> [*]
~~~

**Không suy secret ở trạng thái REVOKED ⇒ client và mọi tokens đều VERIFIED_CLOSED**. Phải theo dõi **tất cả** credential versions và hiệu lực access tokens, target grants nếu cần.

## 24. Audit và detection cho client secret

### 24.1. Những event nên có

| Event | Metadata nên ghi | Không ghi |
| --- | --- | --- |
| Client registered | Client ID, owner, actor, grant types, policy, timestamp. | Plaintext secret. |
| Secret generated | Credential reference/version, actor, expiry, vault path. | Giá trị secret. |
| Secret read/checkout | Actor/workload identity, source, purpose, vault audit ID. | Plaintext secret trong log. |
| Token request | Client ID, grant type, requested/issued scopes, method, result, source signals. | Authorization Basic header, raw body secret, full token. |
| Failed client auth | Error code, client ID nếu xác định được, correlation ID, risk signal. | Secret thử nghiệm và body raw. |
| Credential rotated | Old/new credential refs, approver, execution time, target outcome. | V1/V2 plaintext. |
| Client disabled | Owner, reason, policy, approvals, resulting status. | Sensitive incident payload không cần. |
| Grant changed | Role/scope/resource diff, actor, risk approval. | Raw tokens. |
| Target verification | Desired/actual permission, test/evidence ref, timestamp. | Test credentials. |

### 24.2. Cảnh báo có giá trị

- Token requests bất thường từ **nguồn ngoài runtime đã đăng ký**.
- Client credentials dùng trong thời gian app đã retired.
- Nhiều lần `invalid_client` sau rotation (workload cũ chưa migrate hoặc brute-force).
- App-only client bất ngờ xin scope mới/quyền admin.
- Secret bị tạo/đổi bởi nhân sự không còn owner authority.
- Vault reads từ workstation/developer không thuộc approved runbook.
- Secret production xuất hiện trong CI logs/repository scanning.
- Nhiều clients dùng cùng secret nếu provider cho phép điều tra.
- Credential hết hạn hoặc sắp hết hạn nhưng không có owner/rotation plan.
- Kẻ tấn công dùng token còn sống sau secret revocation.
- Client được tái tạo bởi automation cũ sau disable/deprovision.

### 24.3. Không overclaim từ log

Một token request bằng client ID hợp lệ không chứng minh workload gốc thực hiện. Nên đối chiếu **workload identity, network/context, issuer, credential version, trusted runtime telemetry và target actions**. IP alone không phải bằng chứng định danh chắc chắn khi có NAT/proxies/ephemeral infrastructure.

## 25. JSON hồ sơ quản trị client secret minh họa

~~~json
{
  "clientRegistrationId": "client-billing-prod",
  "identityType": "CONFIDENTIAL_OAUTH_CLIENT",
  "serviceCatalogRef": "billing-etl",
  "ownerTeamRef": "finance-data-platform",
  "environment": "production",
  "tenant": "tenant-vn",
  "authorizationServerRef": "internal-idp-prod",
  "authentication": {
    "tokenEndpointMethod": "client_secret_basic",
    "allowedGrantTypes": ["client_credentials"],
    "credentialRefs": [
      {
        "credentialId": "billing-secret-v3",
        "status": "ACTIVE",
        "vaultRef": "finance/billing/oauth-client/v3",
        "rotateBefore": "2027-02-01T03:00:00Z"
      }
    ]
  },
  "authorization": {
    "intendedAudience": "finance-api",
    "allowedScopes": ["finance:summary.write"],
    "approvalPolicyRef": "finance-api-app-permissions"
  },
  "lifecycle": {
    "status": "ACTIVE",
    "reviewPolicyRef": "nhi-prod-quarterly"
  },
  "verification": {
    "validCredentialRef": "billing-secret-v3",
    "apiPermissionScope": "VERIFIED_SCOPED"
  }
}
~~~

Đây là **schema nội bộ minh họa**, không phải schema chuẩn OIDC Dynamic Client Registration hoặc SCIM. Không lưu plaintext secret ở record; `vaultRef` chỉ là tham chiếu. Một record `VERIFIED_SCOPED` cần evidence target thực tế, không được tự suy từ metadata.

### 25.1. Event khi rotation

~~~json
{
  "eventType": "OAUTH_CLIENT_SECRET_ROTATED",
  "clientId": "client-billing-prod",
  "oldCredentialRef": "billing-secret-v2",
  "newCredentialRef": "billing-secret-v3",
  "actorIdentityId": "person-901",
  "ownerTeamRef": "finance-data-platform",
  "decisionRef": "ROT-2026-041",
  "execution": {
    "newCredentialWorks": true,
    "oldCredentialRejected": true
  },
  "verifiedAt": "2026-11-23T09:25:00+07:00"
}
~~~

Timestamp và ID minh họa. Trong hệ thống thật, log rotation nên gắn **correlationId, AS target, token endpoint test scope và evidence reference**, không đưa cả request header/secret value.

## 26. Pseudocode: lựa chọn cách xác thực OAuth client

~~~text
function chooseClientAuthentication(application):
    if application.runsInBrowserOrDistributedNativeApp:
        return PUBLIC_CLIENT_WITH_PKCE_AND_NO_EMBEDDED_SECRET

    if application.platformSupportsManagedIdentityOrFederation:
        return WORKLOAD_FEDERATION_WITH_SCOPED_SHORT_LIVED_CREDENTIAL

    if application.platformSupportsPrivateKeyJwtOrMutualTLS:
        return EVALUATE_ASYMMETRIC_CLIENT_AUTHENTICATION

    if application.canProtectSecretServerSide
       and authorizationServerSupportsClientSecretAuthentication:
        return CONFIDENTIAL_CLIENT_WITH_VAULT_ROTATION_AND_MONITORING

    return REDESIGN_OR_REJECT_INSECURE_CREDENTIAL_ARCHITECTURE
~~~

Đây là **quy tắc quyết định gợi ý**, không khẳng định một phương thức luôn tốt nhất cho mọi threat model. Lựa chọn cụ thể cần xét AS/RS interoperability, standards profile, trust, availability, cost và rotation.

## 27. Pseudocode: sử dụng secret an toàn trong workload

~~~text
function requestAppOnlyToken(workload, targetResource):
    require workload.identityIsRegisteredAndActive
    require workload.ownerTeamExists
    require targetResource in workload.approvedResources

    credential = vault.getCredentialForCurrentRuntimeIdentity(
        workload.identityId,
        workload.environment
    )

    request = oauthLibrary.buildClientCredentialsRequest(
        tokenEndpoint = trustedProviderMetadata.tokenEndpoint,
        clientId = workload.oauthClientId,
        authMethod = workload.registeredTokenEndpointAuthMethod,
        credentialHandle = credential,
        scope = workload.approvedMinimalScopeFor(targetResource)
    )

    token = oauthLibrary.requestTokenOverValidatedTLS(request)

    require token.issuerIsTrusted
    require token.audienceMatches(targetResource)
    require token.expiresWithinPolicy
    require token.scopeDoesNotExceedApprovedGrant

    return token
~~~

Ở đây các hàm là **pseudocode**, không có sẵn ở Java/JDK. Trong sản phẩm thật, **đừng tự giải mã JWT rồi tin claim client trả về mà bỏ kiểm signature/issuer/audience**; kiểm tra ở resource server mới là ranh giới ủy quyền cuối cùng. Không lưu plaintext credential qua debug logs.

### 27.1. Token caching và secret rotation

Một client có thể cache access token đã phát đến khi `exp`. Khi rotate secret:
- Những request API vẫn có thể dùng token cũ hợp lệ.
- Lần xin token mới cần secret V2.
- Worker cũ có thể tiếp tục dùng cached V1 secret nếu chưa redeploy.
- Readiness/health check nên phân biệt **API success nhờ cached token** với **token acquisition bằng V2**.

**Không kết luận rotation thành công chỉ vì API vẫn trả 200 trong vài phút đầu**, vì token cache có thể che lỗi client authentication.

## 28. Tình huống A: chuyển client secret ra khỏi source code

**Bối cảnh:** `order-service` dùng OAuth Client Credentials để gọi `inventory-api`. Developer trước đây đặt client ID/secret vào `application-prod.yml` rồi commit.

### 28.1. Vấn đề

- Secret bị lưu trong Git history và có thể vào build artifacts.
- Ai có quyền read repo có thể lấy credential.
- Secret xuất hiện trong staging khi copy config.
- Khó biết có bao nhiêu runtime đang dùng.
- Người tạo app có thể đã chuyển team.
- Rotation dễ làm dịch vụ ngừng nếu client IDs/secrets không tách môi trường.

### 28.2. Cách xử lý

1. Xác định client registration, AS, scopes và owner.
2. Đánh giá exposure và đưa secret cũ vào quy trình revoke/rotation, không chỉ xóa dòng khỏi HEAD.
3. Tạo credential mới bằng AS/provider và lưu trong vault.
4. Cấp quyền lấy secret cho đúng production workload identity.
5. Runtime injection an toàn và redact logs.
6. Canary test **xin token mới** với V2, không chỉ test API cached token.
7. Thu hồi V1 và xác minh AS từ chối V1.
8. Kiểm tra tokens và API permissions còn tồn dư.
9. Rà soát Git/build logs/backups, xử lý truy cập theo policy.
10. Cập nhật service owner, rotation schedule và alert khi secret xuất hiện lại.

### 28.3. Khi nào cần thay client ID?

Không phải mọi rotation phải đổi client ID. Nếu AS hỗ trợ rotate secret trên cùng registration và grants vẫn đúng, có thể giữ client ID. Tuy nhiên, khi registration/trust bị compromise nghiêm trọng hoặc quyền được thiết kế sai, cần đánh giá **đăng ký client mới, giảm scopes/roles hoặc thay trust boundary**.

## 29. Tình huống B: owner Leaver nhưng ETL vẫn hoạt động

**Bối cảnh:** Lan tạo OAuth client `billing-etl-prod` để job hàng đêm cập nhật summary. Lan nghỉ việc ngày 02/12. Job vẫn cần chạy và secret V2 có hạn còn ba tháng.

### 29.1. Điều không nên làm

- Gửi client secret V2 vào nhóm chat để “bàn giao”.
- Để Lan vẫn có quyền xem vault vì “người tạo client”.
- Xóa client registration ngay và làm job production ngừng.
- Tin rằng disable Lan ở IdP tự động revoke secret của service.
- Gia hạn secret V2 mãi vì owner mới chưa nhận trách nhiệm.

### 29.2. Quy trình phù hợp

| Bước | Hành động | Bằng chứng |
| --- | --- | --- |
| **Human offboarding** | Disable SSO, thu hồi vault/CI/CD/app admin/PAM roles của Lan. | HRIS event, IdP/PAM readback. |
| **Owner transfer** | Bổ nhiệm Finance Data owner/team mới. | Service catalog và approver route cập nhật. |
| **Credential exposure** | Xác định Lan có đọc/copy V2 hay không. | Vault/audit records; nếu không chắc, risk assessment. |
| **Secret rotation** | Rotate nếu có risk hoặc theo policy, chuyển job an toàn. | V3 token acquisition, V2 rejection. |
| **Entitlement review** | Job vẫn chỉ cần `summary.write` trên tenant-vn. | Approved scopes/target verification. |
| **Audit** | Lưu decision, owner, AS event và kiểm tra token/session residual. | Correlation IDs/evidence. |

### 29.3. Kết quả mong đợi

Lan không còn đường quản trị OAuth client/secret; `billing-etl` vẫn chạy với account/credential hợp lệ, owner mới rõ ràng và không có app-only quyền dư thừa. **Leaver của người** khác với **retirement của machine identity**.

## 30. Tình huống C: secret lộ nhưng access token cũ còn hiệu lực

**Bối cảnh:** Security phát hiện secret của `report-exporter` trong CI log lúc 09:10. AS đã revoke secret lúc 09:15, nhưng resource server vẫn chấp nhận token được phát trước đó.

### 30.1. Vì sao?

Một số access tokens là self-contained và được RS xác minh signature/expiry mà không tra AS ở mỗi request. Secret revocation làm **token endpoint** từ chối client credential trong tương lai nhưng **không tự sửa thông tin của token đã phát**.

### 30.2. Cần xử lý thế nào?

- Đánh giá audience/scopes/token TTL và resource impact.
- Revoke tokens/sessions nếu AS và RS hỗ trợ; hoặc dùng resource-side deny/re-evaluate current grants khi phù hợp.
- Giảm quyền/disable client registration khi cần containment.
- Kiểm tra logs token issuance và target actions.
- Rotate credential nhưng **không mở lại quyền rộng cũ**.
- Xử lý nguồn lộ CI log và runner trust.
- Đo **thời điểm actual access cuối cùng còn được phép**, không chỉ giờ revoke secret.
- Chỉ đóng khi có bằng chứng target chặn hành động trái căn cứ.

## 31. Tình huống D: public SPA cố “giấu” client secret

Một SPA đặt `client_secret` vào biến `REACT_APP_SECRET`, sau đó dùng bundler/minifier rồi tin nó đã được che.

### 31.1. Lỗi cốt lõi

Trình duyệt phải có đủ code/data để chạy ứng dụng, nên người dùng/attacker có thể trích xuất secret từ bundle, runtime hoặc network. Base64 encoding, obfuscation hay mã hóa bằng key cũng nằm trong app **không biến SPA thành confidential client**.

### 31.2. Sửa kiến trúc

- Dùng client registration **public** với Authorization Code + PKCE và redirect URI controls, hoặc
- Đưa confidential client authentication sang **backend/BFF** có khả năng bảo vệ credential, giữ token/secret phía server và bảo vệ browser session.

Không chuyển secret sang localStorage/sessionStorage rồi gọi đó là “secure vault”. Cần thực hiện frontend/session security, CSRF/XSS mitigation và token handling phù hợp, bên cạnh OAuth flow.

## 32. Ma trận kiểm thử Client secret

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **T1** | Client ID hợp lệ, secret đúng, auth method đúng. | AS xác thực client; chỉ phát token trong grants đã được phép. |
| **T2** | Client ID đúng, secret sai. | `invalid_client` hoặc lỗi auth tương ứng; không phát token. |
| **T3** | Secret đã hết hạn/revoke. | Không được dùng để xin token mới. |
| **T4** | Secret V2 mới, token acquisition thật. | Xin token thành công với V2, không chỉ API cached token. |
| **T5** | Secret V1 sau rotation. | AS từ chối V1 đúng deadline. |
| **T6** | SPA/browser bundle chứa secret. | Security review fail; không deploy credential dạng đó. |
| **T7** | Backend dùng Client Credentials xin app-only token. | Không giả end-user session; đúng audience/scopes. |
| **T8** | Backend Authorization Code + PKCE. | Client auth và PKCE code binding đều đạt theo policy. |
| **T9** | Gửi client secret trong URL query. | Chặn/linter/detection; không ghi raw secret. |
| **T10** | Proxy/APM bật debug HTTP. | Header/body/token response được redaction. |
| **T11** | CI từ untrusted fork cố đọc prod secret. | Không có permission truy cập. |
| **T12** | Dev secret dùng xin token production. | Deny do tenant/issuer/trust boundary. |
| **T13** | Client có scope đọc cố xin admin scope. | Deny/giới hạn theo app grants. |
| **T14** | App-only client gọi resource tenant khác. | Target RBAC/ABAC từ chối nếu không có grant. |
| **T15** | Client secret lộ, AS đã revoke, token cũ còn dùng được. | Phát hiện residual access, triển khai containment. |
| **T16** | Owner Mover và mất vault role. | Không còn đọc/rotate secret trái căn cứ; service vẫn chạy. |
| **T17** | Owner Leaver, job cần hoạt động. | Human access revoked, owner mới, credential risk review. |
| **T18** | Service retired, client still active. | Closure failed; deprovision/reconciliation. |
| **T19** | OAuth app tự cấp `directory:write-all`. | Approval/SoD/permission governance chặn. |
| **T20** | Secret rotation thiếu consumer ẩn. | Phát hiện trước/canary hoặc remediation an toàn. |
| **T21** | Workload bị chiếm và đọc secret V3 sau rotation. | Root-cause runtime/vault trust được xử lý, không chỉ rotate. |
| **T22** | Redirect URI bị đổi trái phép cho confidential web client. | Change governance/monitoring, registered redirect validation. |
| **T23** | Client secret gửi tới Resource Server. | Thiết kế lỗi; RS chỉ nhận token/credential đúng giao thức. |
| **T24** | OAuth client bị disable nhưng JWT cũ chưa hết hạn. | Kiểm tra resource-side revocation/authorization theo SLA. |
| **T25** | Provider chỉ chấp nhận Basic, client dùng Post. | Auth failure được phân loại; không log secret khi sửa. |
| **T26** | Một secret chia sẻ giữa production và staging. | Risk review fail, tách registrations/credentials. |

### 32.1. Test đúng cả AuthN, AuthZ và lifecycle

- **Client AuthN:** đúng credential/method/client registration.
- **Token issuance:** grant, scope, token expiry và audience chính xác.
- **Target AuthZ:** API cho đúng action/resource/tenant, từ chối ngoài scope.
- **Rotation:** V2 thật sự xin token, V1 bị AS từ chối.
- **Revocation:** token/session/grants không còn usable trái policy.
- **JML:** người quản trị cũ mất quyền, workload có owner hợp lệ.
- **Audit:** có evidence nhưng **không có secret plaintext**.

Không kiểm thử bằng cách sử dụng secret thật trên máy cá nhân/endpoint không được phép; dùng **môi trường và tài khoản thử nghiệm được ủy quyền**, synthetic credential và automation do owner kiểm soát.

## 33. KPI vận hành và rủi ro tồn dư

| KPI | Ý nghĩa | Cạm bẫy |
| --- | --- | --- |
| **Client inventory coverage** | OAuth registrations đã được map tới service owner. | Bỏ SaaS apps, shadow clients và tenant khác. |
| **Owner coverage** | Client có owner/team đang hiệu lực. | Creator đã Leaver không là owner hợp lệ. |
| **Secret expiry compliance** | Credentials được rotate/trước hạn. | Expiry không đảm bảo token đã phát bị revoke. |
| **Secret age** | Tuổi của static secrets theo risk class. | Secret trẻ nhưng quyền `admin-all` vẫn nguy hiểm. |
| **Static secret reduction** | Tỷ lệ clients chuyển sang federation/managed auth. | Trust policy rộng vẫn tạo rủi ro. |
| **High-privilege app-only clients** | Số clients có roles/scopes nhạy cảm. | Không chỉ nhìn tên app; cần target grants. |
| **Credential read anomalies** | Secret đọc từ source ngoài runtime hợp lệ. | Owner có thể rotate mà không cần thấy plaintext. |
| **Rotation success** | V2 hoạt động, V1 bị từ chối, consumers đầy đủ. | API 200 bằng cached token che lỗi rotation. |
| **Residual token exposure** | Token/session vẫn dùng được sau revocation deadline. | Không đo bằng trạng thái secret-only. |
| **Provisioned-without-approval** | App-only grants không có authorization hợp lệ. | Đây là lỗi governance quan trọng. |
| **Owner Leaver remediation** | Time to revoke human control + review secrets. | Không xóa luôn service đang chạy. |
| **Stale client rate** | Clients không còn service/business purpose mà vẫn active. | Một DR client ít dùng vẫn có thể hợp lệ. |
| **Credential incident response** | Thời gian contain credential và related access. | Rotation một secret không xử lý compromised runtime. |
| **Effective-access verification** | Chứng minh target permissions khớp desired state. | Token request success không đủ chứng minh least privilege. |

Đặt ngưỡng theo **mức nhạy cảm, môi trường, phạm vi quyền, khả năng AS/RS và chính sách tổ chức**, không có một thời hạn client secret phổ quát cho mọi ứng dụng.

## 34. Anti-patterns cần tránh

| Anti-pattern | Tại sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Đặt client secret trong SPA/mobile source. | Không giữ bí mật trước user/attacker. | Public client + PKCE hoặc BFF. |
| Dùng client ID như credential. | Identifier không chứng minh possession. | Client auth đúng method. |
| Nhầm client secret với access token. | Gửi secret đến API hoặc public frontend. | AS token endpoint nhận secret, RS nhận token. |
| Log HTTP Authorization Basic. | Base64 có thể giải mã lại ra secret. | Redaction và protected tracing. |
| Gửi secret qua URL query. | Rò rỉ access logs/history. | Header/body theo method, TLS. |
| Commit secret vào Git rồi chỉ xóa khỏi HEAD. | Secret còn trong history/artifacts. | Revoke/rotate và xử lý exposure. |
| Dùng một secret cho dev/prod và nhiều services. | Blast radius, attribution và rotation kém. | Tách theo trust boundary. |
| Giữ secret V1 active vô hạn làm rollback. | Đường credential cũ không kiểm soát. | Hạn cutover và revoke V1. |
| Chỉ kiểm API 200 sau rotation. | Cached access token che client auth lỗi. | Test token endpoint bằng V2 và reject V1. |
| Disable human owner rồi cho là secret service đã revoked. | Workload client còn active. | Service lifecycle và human JML riêng. |
| Xóa client đang dùng khi creator Leaver. | Dừng dịch vụ hợp lệ. | Owner transfer, exposure review, rotation. |
| Tin rotate secret tự vô hiệu hóa mọi JWT. | Residual access. | Token/session/target policy checks. |
| Cấp GlobalAdmin cho app-only client vì “bot không có người”. | Overprivilege và SoD bypass. | Least privilege, independent approvals. |
| Cho service tự tạo secret hoặc nâng role không kiểm soát. | Privilege escalation/persistence. | Separate IAM admin authority, audit. |
| Copy secret vào ticket khi debug `invalid_client`. | Rò rỉ credential qua support systems. | Credential reference/metadata only. |
| Chỉ kiểm SCIM group khi retire client. | OAuth registration/grant còn tồn tại. | AS client + target entitlement inventory. |
| Token audience/tenant không được kiểm tại API. | Cross-resource/tenant misuse. | Resource-side validation và ABAC. |
| Rotation mà workload runtime bị attacker chiếm. | Kẻ tấn công lấy secret mới. | Contain runtime, vault trust, redeploy. |
| Không có owner cho shadow OAuth clients. | Orphaned credentials. | Discovery, recertification, retirement. |
| Không cân nhắc federation do “secret đơn giản hơn”. | Long-lived credential tồn dư. | Đánh giá lifecycle/risk của managed auth. |

## 35. Checklist triển khai và vận hành

### 35.1. Khi đăng ký OAuth client

- [ ] Đã xác định client là confidential hay public bằng deployment threat model.
- [ ] Public SPA/mobile không chứa client secret.
- [ ] Có client ID, service owner, environment, tenant và business purpose rõ.
- [ ] Allowed grant types/scopes/audiences được phê duyệt.
- [ ] Redirect URIs, PKCE và OIDC state/nonce đúng flow khi áp dụng.
- [ ] Client authentication method khớp AS và không downgrade tùy ý.
- [ ] Không cấp app-only admin scope nếu không có approval/risk justification.
- [ ] Có least privilege RBAC/ABAC và SoD theo target.
- [ ] Có audit client registration, secret creation và owner authority.

### 35.2. Khi lưu và sử dụng secret

- [ ] Secret được AS/crypto-secure source tạo với entropy phù hợp.
- [ ] Không đặt secret thật vào Git, image, frontend, logs, URL hoặc ticket.
- [ ] Lưu ở vault/secret store với scoped runtime permissions.
- [ ] Runtime truy xuất secret theo managed identity/credential hợp lệ.
- [ ] TLS được xác minh khi gọi token endpoint; không bỏ certificate checks.
- [ ] App dùng OAuth client library đã được duy trì.
- [ ] Token endpoint auth method Basic/Post/asymmetric đúng contract.
- [ ] Authorization header, form body và token response được redaction.
- [ ] Có credential ID/version, expiry, rotation owner và alert.
- [ ] Resource Server kiểm token, audience/scope/resource/tenant policy.

### 35.3. Khi rotate, compromise hoặc retire

- [ ] Có inventory mọi workload/instance/job sử dụng client.
- [ ] Có rotation/cutover plan theo capability nhiều secrets hay không.
- [ ] Đã test token acquisition bằng V2, không chỉ cached API token.
- [ ] Secret cũ bị AS từ chối sau cutover và có audit evidence.
- [ ] Khi lộ, đã đánh giá tokens/sessions và related grants còn sống.
- [ ] Đã kiểm runtime/vault/CI/Git/log là nguồn rò rỉ.
- [ ] Human Mover/Leaver không còn quyền đọc/quản trị secret trái căn cứ.
- [ ] Machine identity có service owner mới nếu nhân sự cũ rời.
- [ ] Client/service retired: disable registration, revoke secrets/grants/tokens.
- [ ] Readback target effective access và ngăn tự re-provision.
- [ ] Chỉ đánh dấu `VERIFIED_CLOSED` khi mọi đường truy cập cần thu hồi đã được kiểm chứng.

## 36. Bài tập tự kiểm tra

### 36.1. Bài A — Client ID và secret

Một developer chia sẻ `client_id` trong README nhưng không chia secret. Điều gì thay đổi khi lộ `client_secret`? Vì sao `client_id` thường không được coi là bí mật?

### 36.2. Bài B — SPA và PKCE

Một SPA nhúng secret vào bundle rồi dùng `Authorization Code + PKCE`. PKCE có biến client thành confidential không? Đề xuất đăng ký public client hoặc BFF, nêu nơi secret được phép lưu.

### 36.3. Bài C — Client Credentials và user context

Job `billing-etl` dùng `grant_type=client_credentials`. Token đó đại diện ai? Có thể suy human manager ID từ token app-only không? Thiết kế owner audit riêng.

### 36.4. Bài D — client_secret_basic vs post

Một proxy log toàn bộ HTTP headers, trong khi client dùng Basic. Vì sao Base64 không phải encryption? Sửa log policy thế nào và có thể cần rotate secret nào?

### 36.5. Bài E — Rotation với token cache

Sau khi tạo V2 và deploy, API vẫn trả 200. V1 bị AS revoke nhưng job chỉ xin token mỗi 60 phút. Làm sao xác minh V2 thực sự hoạt động và V1 không còn dùng được mà không làm gián đoạn dịch vụ?

### 36.6. Bài F — Owner Mover/Leaver

Lan tạo `billing-etl-prod`, sau đó chuyển team rồi nghỉ. Hãy phân biệt thu hồi quyền con người ở vault/IdP/CI với lifecycle OAuth client còn phục vụ job. Khi nào cần rotate và ai phê duyệt quyền mới?

### 36.7. Bài G — Secret leaked in Git

Secret production xuất hiện trong pull request 10 phút rồi bị xóa. Có thể coi an toàn vì file HEAD đã sửa không? Mô tả containment, scan Git history, rotation, token/session review và audit.

### 36.8. Bài H — OAuth ID token và access token

Một backend dùng ID token để gọi `finance-api`. Vì sao sai ngữ nghĩa? Phân biệt client secret, ID token, access token và phương thức client authentication.

### 36.9. Bài I — Dev/prod separation

Một service dev và prod dùng chung client ID/secret. Khi dev runner bị compromise, attacker có thể xin production token. Nêu cách tách issuer/registration, audience, permission và resource policy.

### 36.10. Bài J — Lộ secret nhưng token cũ vẫn chạy

AS revoke secret lúc 09:00, nhưng access token cũ hết hạn 10:00. API không có introspection. Nêu residual-access window và biện pháp target-side policy/revocation/containment phù hợp.

### 36.11. Bài K — SoD cho pipeline

Một OAuth client có quyền đổi code, phê duyệt release và deploy production. Vì sao dùng machine identity không miễn phân tách nhiệm vụ? Thiết kế roles/permissions, owner và independent approval.

### 36.12. Bài L — Secret vs private_key_jwt/mTLS

Nêu ưu/nhược điểm khi chuyển từ client secret sang `private_key_jwt` hoặc mTLS; vì sao vẫn cần bảo vệ private key, key rotation, issuer/audience và app-only authorization?

### 36.13. Bài M — SCIM có đủ để retire không?

SCIM deactivates User đại diện cho service account, nhưng OAuth client registration và secret vẫn ACTIVE. Hãy lập danh sách source-of-authority APIs và bằng chứng target cần để VERIFIED_CLOSED.

### 36.14. Bài N — Dashboard governance

Tổ chức có 100% client secrets “chưa hết hạn”, nhưng nhiều shadow OAuth apps không có owner và 20 app-only clients giữ GlobalAdmin. Có thể kết luận governance tốt không? Đề xuất KPI inventory, owner, privilege, rotation và effective-access verification.

**Điểm cần ghi nhớ:** **Client secret** là một **credential dùng cho xác thực OAuth confidential client**, không phải identity của người, access token, refresh token hay ID token. Cần xác định **client type, grant và token-endpoint authentication method**, giữ secret **server-side** qua secret store/vault, không nhúng trong public clients, và giới hạn scopes/resources tại **AS và Resource Server**. Trong IAM **Joiner–Mover–Leaver**, người quản trị ứng dụng có thể thay đổi hoặc rời đi nhưng workload có lifecycle và owner riêng; phải **rotate/revoke đúng secret, thu hồi app grants/tokens/sessions khi cần và đọc lại quyền hiệu lực**, có **audit/reconciliation** để tránh **credential bị lộ, client mồ côi và đặc quyền tồn dư**.

