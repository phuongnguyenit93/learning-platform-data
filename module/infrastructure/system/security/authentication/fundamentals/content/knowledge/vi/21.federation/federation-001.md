# Identity federation — Liên kết xác thực giữa các miền tin cậy

> **Chương:** Federation  
> **Chủ đề:** Identity federation  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách một ứng dụng tin cậy kết quả xác thực từ Identity Provider (IdP), ánh xạ danh tính ngoài vào account nội bộ và duy trì ranh giới tin cậy qua OIDC, SAML, claim, session và quy trình vòng đời tài khoản.

## 1. Identity federation là gì?

**Identity federation (liên kết danh tính)** là mô hình trong đó một hệ thống chấp nhận kết quả xác thực hoặc thuộc tính danh tính do một miền quản lý danh tính khác phát hành, dựa trên một quan hệ tin cậy và giao thức đã được cấu hình. Người dùng có thể xác thực tại **Identity Provider (IdP)**, sau đó truy cập một hoặc nhiều ứng dụng **Relying Party (RP)** mà không cần mỗi ứng dụng tự thu thập và kiểm tra lại mật khẩu của người dùng.

Ví dụ, một trường đại học quản lý tài khoản sinh viên tại IdP của trường. Nền tảng học tập bên ngoài chuyển người dùng tới IdP để đăng nhập. Sau khi xác thực, IdP gửi kết quả qua OpenID Connect (OIDC) hoặc SAML. Nền tảng học tập kiểm tra thông điệp theo cấu hình tin cậy, ánh xạ danh tính sang account nội bộ và tạo session riêng cho ứng dụng.

Federation không có nghĩa ứng dụng giao toàn bộ quyền kiểm soát cho IdP. RP vẫn chịu trách nhiệm kiểm tra giao thức, quyết định có chấp nhận kết quả hay không, ánh xạ đúng account, áp dụng policy nội bộ, quản lý session và phân quyền tài nguyên.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt identity federation, Single Sign-On (SSO), authentication và delegated authorization.
2. Mô tả vai trò của IdP, RP, user agent, assertion, ID token và access token.
3. Giải thích luồng OIDC Authorization Code với PKCE và các kiểm tra bắt buộc.
4. Nhận diện SAML assertion, signature, audience, recipient và thời hạn.
5. Ánh xạ danh tính ngoài vào account nội bộ mà không dựa riêng vào email.
6. Đánh giá claim về phương thức xác thực, MFA và thời điểm xác thực.
7. Thiết kế tenant mapping, provisioning, logout, key rotation và quy trình thu hồi quan hệ tin cậy.
8. Phát hiện token substitution, issuer mix-up, replay, account-linking takeover và confused deputy.

## 2. Các vai trò và ranh giới tin cậy

Một luồng federation thường có các bên:

| Thành phần | Vai trò | Trách nhiệm bảo mật |
| --- | --- | --- |
| **User** | Người dùng muốn truy cập ứng dụng | Bảo vệ authenticator và kiểm tra ngữ cảnh đăng nhập. |
| **User Agent** | Trình duyệt hoặc ứng dụng client | Chuyển hướng và chuyển thông điệp; không phải nguồn tin cậy để tự khai kết quả xác thực. |
| **Identity Provider (IdP)** | Xác thực người dùng và phát hành kết quả | Quản lý credential, MFA, account lifecycle, ký assertion/token và công bố metadata/keys. |
| **Relying Party (RP)** | Ứng dụng nhận kết quả federation | Kiểm tra thông điệp, ánh xạ danh tính, áp dụng policy, tạo session và authorization. |
| **Resource Server** | API hoặc dịch vụ bảo vệ tài nguyên | Kiểm tra access token và quyền truy cập theo tài nguyên. |
| **Trust configuration** | Cấu hình quan hệ giữa IdP và RP | Xác định issuer, endpoints, keys, client ID, redirect URI, audience và policy. |

~~~mermaid
flowchart LR
    U["Người dùng"] --> B["Browser / User Agent"]
    B -->|"Authorization request"| I["Identity Provider"]
    I -->|"Authentication tại IdP"| U
    I -->|"Code / Assertion / Token"| B
    B -->|"Callback / Response"| R["Relying Party"]
    R -->|"Verify + map identity"| P["Principal nội bộ"]
    P --> S["RP session"]
    S --> A["Authorization và API"]
~~~

**IdP xác thực; RP quyết định tin và sử dụng kết quả đó.** IdP có thể nói “subject này đã đăng nhập bằng phương thức X”, nhưng RP vẫn phải xác minh chữ ký, issuer, audience, thời hạn, giao dịch và hợp đồng tin cậy. RP cũng phải quyết định subject đó tương ứng account nào trong hệ thống của mình.

### Trust không tự phát sinh từ redirect

Việc browser quay về một callback URL không chứng minh đăng nhập thành công. Kẻ tấn công có thể điều khiển URL, gửi response giả hoặc tận dụng cấu hình client sai. Chỉ thông điệp được xác minh theo giao thức và đúng giao dịch đang chờ mới được sử dụng để tạo principal.

## 3. Federation, SSO và delegated authorization khác nhau thế nào?

Ba khái niệm thường đi cùng nhau nhưng không đồng nghĩa:

- **Identity federation:** thiết lập quan hệ tin cậy để một miền chấp nhận kết quả danh tính/xác thực từ miền khác.
- **Single Sign-On (SSO):** trải nghiệm người dùng đăng nhập một lần rồi truy cập nhiều ứng dụng mà không phải nhập credential lại trong mỗi ứng dụng. SSO thường được xây trên federation.
- **Delegated authorization:** cho phép một ứng dụng hoặc client truy cập tài nguyên thay mặt người dùng với scope/quyền giới hạn, thường qua OAuth 2.0.

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang chứng minh quyền kiểm soát credential? | IdP xác minh password và passkey. |
| Federation | RP tin kết quả từ miền nào, theo hợp đồng nào? | Ứng dụng tin issuer của trường đại học. |
| SSO | Người dùng có phải đăng nhập lại ở mỗi ứng dụng không? | Một phiên IdP được dùng cho cổng sinh viên và thư viện. |
| Delegated authorization | Client được phép gọi API nào và trong phạm vi nào? | Ứng dụng lịch được cấp scope đọc lịch. |

OAuth 2.0 chủ yếu là framework ủy quyền; nó không tự định nghĩa một chuẩn xác thực người dùng. **OpenID Connect (OIDC)** bổ sung lớp identity trên OAuth 2.0, bao gồm ID Token và các quy tắc xác thực. Không nên dùng một access token OAuth bất kỳ làm bằng chứng danh tính chỉ vì token có subject hoặc được ký.

## 4. OIDC: các thành phần cốt lõi

OIDC sử dụng OAuth 2.0 authorization framework và định nghĩa cách RP nhận kết quả xác thực.

Các khái niệm quan trọng:

- **Issuer (iss):** định danh IdP phát hành token, thường là URL của authorization server.
- **Client ID:** định danh RP đã đăng ký tại IdP.
- **Redirect URI:** callback đã đăng ký, nơi IdP trả browser sau authorization.
- **Subject (sub):** định danh người dùng trong phạm vi issuer.
- **ID Token:** JWT mang các claim xác thực cho client/RP.
- **Access Token:** credential để gọi resource server theo audience/scope; không thay thế ID Token.
- **Authorization Code:** mã ngắn hạn được browser chuyển về RP để RP đổi lấy token ở token endpoint.
- **State:** giá trị do RP tạo để ràng buộc callback với giao dịch browser đang chờ và chống CSRF/login injection.
- **Nonce:** giá trị RP tạo và gắn với authentication request; RP kiểm tra lại trong ID Token để chống replay/substitution theo flow.
- **PKCE:** cơ chế proof key for code exchange, ràng buộc authorization code với client đã khởi tạo giao dịch.

RP cần lấy cấu hình IdP từ issuer đã được quản trị và xác minh, ví dụ discovery metadata, JWKS URI, authorization endpoint, token endpoint và supported signing algorithms. Không nhận một issuer URL tùy ý từ người dùng rồi tự động tin mọi metadata mà URL đó trả về.

## 5. OIDC Authorization Code Flow với PKCE

Đối với ứng dụng web và native app hiện đại, Authorization Code Flow với PKCE là pattern phổ biến. Với confidential web client, RP còn xác thực client tại token endpoint theo cấu hình; PKCE vẫn có thể cung cấp lớp ràng buộc bổ sung.

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant R as RP
    participant I as IdP
    U->>B: Chọn đăng nhập
    B->>R: Bắt đầu login
    R->>R: Tạo state, nonce, code_verifier
    R-->>B: Redirect tới authorization endpoint + code_challenge
    B->>I: Authorization request
    I->>U: Xác thực credential/MFA
    U->>I: Hoàn tất xác thực
    I-->>B: Redirect callback với authorization code + state
    B->>R: Callback
    R->>R: Kiểm tra state và giao dịch pending
    R->>I: Token request + code_verifier
    I-->>R: ID Token + Access Token (theo yêu cầu)
    R->>R: Verify ID Token, nonce, issuer, audience, time
    R->>R: Map (iss, sub) -> internal account
    R->>R: Tạo RP session mới
~~~

### Các bước phía RP

1. Người dùng yêu cầu đăng nhập.
2. RP tạo state ngẫu nhiên, nonce ngẫu nhiên và PKCE code verifier.
3. RP lưu các giá trị này trong giao dịch đăng nhập ngắn hạn, gắn với browser/session khởi tạo.
4. RP chuyển browser tới authorization endpoint của IdP đã cấu hình, kèm client ID, redirect URI chính xác, response type code, scope cần thiết, state, nonce và PKCE code challenge.
5. IdP xác thực người dùng và có thể yêu cầu MFA/step-up theo policy.
6. IdP redirect về callback đã đăng ký với authorization code và state.
7. RP kiểm tra state khớp giao dịch đang chờ, chưa hết hạn và chưa sử dụng.
8. RP gửi code tới token endpoint qua back channel, kèm code verifier và thông tin xác thực client nếu cần.
9. RP xác minh ID Token đầy đủ.
10. RP ánh xạ issuer + subject sang account nội bộ, kiểm tra trạng thái account/tenant và tạo session riêng.

### PKCE bảo vệ điều gì?

RP tạo code verifier ngẫu nhiên và gửi code challenge tương ứng trong authorization request. Khi đổi code, RP gửi verifier. Attacker chỉ lấy được authorization code qua browser mà không có verifier tương ứng sẽ không đổi được code thành token.

PKCE không thay thế state, nonce, redirect URI validation, client authentication hoặc ID Token validation. Mỗi cơ chế xử lý một nhóm rủi ro khác nhau.

## 6. Kiểm tra state, nonce và authorization response

### State

State gắn callback với giao dịch login do RP khởi tạo. Nếu state sai, thiếu, đã hết hạn hoặc không khớp browser transaction, RP phải từ chối callback. Không dùng một state cố định cho mọi người dùng hoặc lưu state chỉ trong một cookie dùng chung mà không có correlation phù hợp.

State không phải bằng chứng xác thực người dùng. Nó giúp chống CSRF và login injection trong giao dịch redirect.

### Nonce

Nonce được RP tạo cho authentication request và kiểm tra trong ID Token. Nó ràng buộc ID Token với lần yêu cầu hiện tại, giúp phát hiện token cũ hoặc token bị chuyển từ giao dịch khác. Nonce phải có entropy, được lưu an toàn và chỉ được chấp nhận trong giao dịch tương ứng.

### Redirect URI

Redirect URI cần khớp chính xác với URI đã đăng ký theo quy tắc của IdP. Tránh wildcard rộng, prefix matching hoặc cho client truyền một URL tùy ý. Open redirect ở RP có thể làm authorization code/token bị chuyển tới domain attacker.

### Response mode và callback

Callback phải xử lý response đúng giao thức, kiểm tra state và lỗi authorization. Không coi mọi request tới callback là đăng nhập thành công. Nếu response chứa code, RP vẫn cần đổi code qua token endpoint và xác minh kết quả.

## 7. Xác minh ID Token

ID Token thường là JWT đã được ký bởi IdP. RP cần kiểm tra toàn bộ các điều kiện theo OIDC, không chỉ decode payload.

Các kiểm tra quan trọng:

| Thành phần | Điều phải xác minh |
| --- | --- |
| **Signature** | Chữ ký hợp lệ bằng key phù hợp từ JWKS tin cậy; algorithm nằm trong allowlist. |
| **iss** | Khớp chính xác issuer đã cấu hình cho client/tenant. |
| **aud** | Có client ID của RP trong audience. |
| **azp** | Khi áp dụng, authorized party phù hợp với client đang nhận token. |
| **exp** | Token chưa hết hạn theo clock-skew policy. |
| **iat** | Thời điểm phát hành hợp lý, không nằm ngoài giới hạn policy. |
| **nonce** | Khớp nonce của giao dịch login đang chờ. |
| **sub** | Có mặt và dùng làm định danh subject trong phạm vi issuer. |
| **auth_time** | Nếu RP yêu cầu xác thực mới, kiểm tra thời điểm thực sự xác thực. |
| **acr / amr** | Chỉ diễn giải theo hợp đồng và policy đã thống nhất với IdP. |

Không chấp nhận thuật toán không mong đợi, ví dụ token tự khai thuật toán không an toàn hoặc cấu hình nhầm thuật toán không ký. Không lấy key từ một URL trong token header rồi tin ngay; JWKS URI phải đến từ cấu hình issuer tin cậy.

### JWKS và key rotation

IdP có thể công bố nhiều public key trong JWKS. RP chọn key dựa trên kid/alg phù hợp, nhưng vẫn cần kiểm tra issuer và algorithm policy. Khi key rotation:
- IdP công bố key mới trước khi ký bằng key đó theo lịch triển khai phù hợp.
- RP làm mới JWKS khi kid chưa biết hoặc cache hết hạn, có giới hạn để tránh attacker gây request storm.
- RP giữ key cũ đủ lâu để xác minh token còn trong thời hạn hợp lệ theo policy.
- Khi key bị compromise, cần quy trình khẩn cấp để loại bỏ key, thu hồi phiên/token và xử lý các assertion bị ảnh hưởng.
- Không giữ JWKS cache vô thời hạn nếu không có cơ chế cập nhật/thu hồi.

### ID Token không phải Access Token

ID Token dành cho client/RP để xác nhận kết quả authentication. Access Token dành cho resource server để truy cập API. Resource server phải kiểm tra audience/scope của chính nó; RP không được dùng access token như ID Token chỉ vì nó là JWT.

## 8. Ánh xạ danh tính: issuer + subject, không chỉ email

Một lỗi phổ biến là tìm account nội bộ bằng email rồi tự động đăng nhập hoặc gộp danh tính. Email có thể thay đổi, được tái cấp, chưa xác minh hoặc trùng giữa nhiều IdP.

Trong OIDC, định danh federation cơ bản là cặp:

~~~text
(issuer, subject)
  = (iss, sub)
~~~

Cùng một giá trị sub từ hai issuer khác nhau có thể là hai người khác nhau. Ngược lại, cùng một người có thể có subject khác nhau ở hai IdP.

Ví dụ bảng liên kết:

~~~sql
CREATE TABLE federated_identities (
    id UUID PRIMARY KEY,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    account_id UUID NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

Bảng này minh họa nguyên tắc unique mapping. Trong hệ thống thật cần thêm trạng thái, tenant/policy nếu cần, audit và quy trình unlink. Không đặt unique trên email thay cho issuer + subject.

### Account linking an toàn

Khi người dùng muốn liên kết một IdP mới với account đã tồn tại:

1. Yêu cầu phiên hiện tại đã xác thực ở mức phù hợp.
2. Có thể yêu cầu step-up bằng authenticator hiện có.
3. Khởi tạo federation flow mới với state/nonce riêng.
4. Xác minh kết quả IdP và lấy issuer + subject.
5. Kiểm tra identity đó chưa được liên kết với account khác.
6. Nếu chính sách cần, yêu cầu xác nhận bằng chứng từ cả account hiện tại và IdP mới.
7. Ghi quan hệ, thời điểm, actor và nguồn tin cậy vào audit.
8. Thông báo thay đổi qua kênh hiện có.

Không tự động gộp account chỉ vì email từ IdP mới giống email nội bộ. Nếu hai account đã tồn tại, quy trình merge phải có policy và kiểm tra xung đột riêng.

## 9. Claim: thuộc tính danh tính và ngữ cảnh xác thực

Claim là dữ liệu được IdP phát hành về subject hoặc sự kiện xác thực. Ví dụ:
- sub: định danh subject trong issuer.
- email/email_verified: địa chỉ email và trạng thái xác minh theo semantics của IdP.
- name, given_name, family_name: thuộc tính profile.
- groups/roles: nhóm hoặc vai trò nếu IdP phát hành theo hợp đồng.
- auth_time: thời điểm IdP xác thực người dùng.
- amr: phương thức xác thực đã sử dụng.
- acr: lớp/ngữ cảnh xác thực.

RP cần áp dụng **claim minimization**: chỉ yêu cầu và lưu các claim thật sự cần. Không yêu cầu profile đầy đủ nếu chỉ cần subject và một thuộc tính liên hệ. Claim có thể là dữ liệu cá nhân và cần chính sách truy cập/lưu giữ.

### email_verified không phải quyền truy cập

Claim email_verified có ý nghĩa theo issuer và thời điểm phát hành. Nó không tự cấp membership vào tenant, không chứng minh email sẽ luôn thuộc cùng một người và không nên dùng làm khóa định danh duy nhất. Với domain doanh nghiệp, cần kiểm soát domain và quy trình membership riêng.

### groups và roles cần ánh xạ

Không sao chép mọi group từ IdP thành quyền ứng dụng. RP cần mapping allowlist từ group/claim đã thỏa thuận sang role nội bộ, giới hạn tenant và scope. Nếu IdP trả role ngoài dự kiến, RP nên bỏ qua hoặc từ chối theo policy, không tự nâng quyền.

## 10. MFA assurance qua federation: acr, amr và auth_time

RP có thể cần biết người dùng đã xác thực bằng phương thức nào và gần đây đến mức nào. OIDC cung cấp claim có thể hỗ trợ việc đó, nhưng **ý nghĩa phải được thỏa thuận giữa IdP và RP**.

- **amr (Authentication Methods References):** chỉ các phương thức xác thực đã sử dụng theo từ vựng/semantics của issuer.
- **acr (Authentication Context Class Reference):** lớp hoặc ngữ cảnh xác thực theo định nghĩa của IdP.
- **auth_time:** thời điểm người dùng được xác thực; hữu ích cho policy freshness nếu được phát hành và kiểm tra đúng.

Không mặc định chuỗi amr chứa “mfa” đồng nghĩa đáp ứng yêu cầu chống phishing. Password + SMS và passkey/WebAuthn có đặc tính khác nhau. RP cần hiểu chính xác acr/amr mà IdP phát hành, phương thức nào nằm sau claim, mức bảo đảm của authenticator, yêu cầu UV và quy trình recovery.

Ví dụ: RP yêu cầu quản trị viên đăng nhập bằng phương thức chống phishing. IdP trả claim cho biết đã dùng password + SMS. Đây có thể là nhiều bước/đa yếu tố, nhưng không chứng minh phishing resistance. RP cần yêu cầu authentication context khác hoặc từ chối thao tác đặc quyền.

### Yêu cầu step-up

RP có thể gửi yêu cầu authentication context phù hợp (ví dụ acr_values hoặc max_age theo khả năng và hợp đồng OIDC). Sau callback, RP phải xác minh ID Token mới và các claim thực tế. Không nâng assurance chỉ vì browser đã redirect qua IdP hoặc IdP trả HTTP success.

## 11. SAML 2.0: assertion và trust

**SAML 2.0** là chuẩn trao đổi authentication/attribute assertion phổ biến trong môi trường doanh nghiệp và giáo dục. Trong mô hình Web Browser SSO:
- **Identity Provider (IdP):** xác thực user và phát hành SAML Response chứa assertion.
- **Service Provider (SP):** ứng dụng tiêu thụ assertion; tương đương vai trò RP ở mức khái niệm.
- **Assertion:** thông điệp có subject, conditions, authentication statement và attribute statement.
- **Metadata:** mô tả entity ID, endpoint, binding và certificate dùng để thiết lập quan hệ tin cậy.

Một luồng SP-initiated phổ biến:

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant SP as Service Provider
    participant IdP as Identity Provider
    U->>SP: Truy cập ứng dụng
    SP->>SP: Tạo AuthnRequest + request ID
    SP-->>B: Redirect/POST tới IdP
    B->>IdP: AuthnRequest
    IdP->>U: Xác thực credential/MFA
    U->>IdP: Hoàn tất
    IdP-->>B: SAML Response
    B->>SP: POST ACS endpoint
    SP->>SP: Verify signature, issuer, audience, recipient, time, InResponseTo
    SP->>SP: Map subject -> internal account
    SP->>SP: Create local session
~~~

### Kiểm tra SAML assertion

SP cần xác minh:
- Chữ ký đúng và certificate ký thuộc IdP đã cấu hình.
- Issuer khớp entity ID tin cậy.
- Destination và Recipient khớp endpoint mong đợi.
- AudienceRestriction chứa entity ID của SP.
- Conditions NotBefore/NotOnOrAfter hợp lệ với clock skew policy.
- SubjectConfirmationData hợp lệ, recipient và thời hạn phù hợp.
- InResponseTo khớp AuthnRequest đang chờ đối với SP-initiated flow.
- Assertion/response ID chưa được sử dụng để chống replay.
- Subject/NameID được ánh xạ theo hợp đồng, không tự coi email là khóa ổn định.

SAML XML Signature cần được xác minh đúng node và đúng nội dung đã được ký. Cẩn thận với **XML Signature Wrapping**: parser có thể xác minh một assertion nhưng ứng dụng lại đọc một assertion khác nếu code không gắn chặt node đã xác minh với node được dùng. Dùng thư viện SAML đã được kiểm chứng, không tự viết XML signature validation.

### SP-initiated và IdP-initiated

SP-initiated flow cho phép SP tạo AuthnRequest và ràng buộc response bằng InResponseTo. IdP-initiated flow bắt đầu từ portal IdP và có thể không có request tương ứng đang chờ ở SP. IdP-initiated có rủi ro login CSRF/unsolicited response cao hơn nếu triển khai không cẩn thận. Chỉ bật khi có nhu cầu, xác minh audience/recipient/signature/time/replay nghiêm ngặt và thiết kế cách ràng buộc user intent phù hợp.

## 12. Federation không thay thế RP session

Sau khi xác minh OIDC ID Token hoặc SAML assertion, RP thường tạo **session cục bộ** của riêng ứng dụng. Không nên giữ nguyên assertion/token từ IdP làm session vô thời hạn.

RP session cần:
- Gắn với internal account ID ổn định.
- Lưu issuer + subject liên kết và thời điểm xác thực.
- Lưu phương thức/assurance context đã được xác minh nếu policy cần.
- Có idle/absolute expiry, cookie security, rotation và revocation.
- Kiểm tra tenant/membership và authorization theo từng request.
- Có quy trình logout và xử lý thay đổi trạng thái account.

IdP session và RP session là hai trạng thái riêng. Người dùng logout khỏi một RP không nhất thiết logout khỏi IdP hoặc các RP khác. Ngược lại, IdP logout không tự động làm mọi RP session biến mất nếu không có cơ chế phối hợp và RP xử lý đúng thông điệp.

### Token refresh không phải xác thực lại

Access token được refresh không có nghĩa người dùng vừa nhập credential. RP cần dùng auth_time hoặc một sự kiện authentication mới đã xác minh để đánh giá độ mới; không suy thời điểm xác thực từ thời điểm phát hành access token.

## 13. Provisioning và deprovisioning account

Federation xác thực danh tính, nhưng ứng dụng còn cần quản lý account và membership.

### Just-in-Time (JIT) provisioning

RP tạo account hoặc membership khi người dùng đăng nhập lần đầu và assertion hợp lệ. JIT tiện lợi nhưng cần policy rõ:
- Chỉ tạo account từ issuer đã được quản trị.
- Ánh xạ subject ổn định và tránh email collision.
- Chỉ lấy claim cần thiết.
- Quyết định tenant, role và trạng thái dựa trên mapping đã cấu hình.
- Không tự cấp admin vì claim group không được kiểm soát.
- Có xử lý khi IdP ngừng phát hành hoặc user không còn đủ điều kiện.

### SCIM và provisioning ngoài luồng đăng nhập

SCIM có thể được dùng để tạo, cập nhật, vô hiệu hóa user/group từ hệ thống quản trị danh tính. Nó giải quyết vòng đời account ở provisioning plane, khác với OIDC/SAML dùng trong authentication flow.

Khi nhân viên rời tổ chức, SCIM deprovisioning có thể vô hiệu account/membership, thu hồi RP sessions và token theo policy. Không chờ người dùng thử đăng nhập lần tiếp theo mới biết họ đã mất quyền.

### Deprovisioning và claim cũ

Một ID Token đã phát hành không tự cập nhật khi group hoặc membership ở IdP thay đổi. RP cần thời hạn token/session hợp lý, cơ chế sync/introspection/event hoặc kiểm tra trạng thái nội bộ cho thao tác nhạy cảm. Claim cũ không được giữ quyền vô thời hạn.

## 14. Tenant federation và ánh xạ tổ chức

Một RP có thể kết nối nhiều IdP, hoặc một IdP có thể phục vụ nhiều tenant. Cần ánh xạ tenant rõ ràng và không để người dùng tự chọn issuer tùy ý.

Ví dụ cấu hình nội bộ:

~~~text
tenant-alpha:
  issuer = https://id.alpha.example
  client_id = learning-alpha
  allowed_domains = [alpha.example]
  role_mapping = { "students" -> LEARNER, "staff" -> INSTRUCTOR }

tenant-beta:
  issuer = https://login.beta.example
  client_id = learning-beta
  allowed_domains = [beta.example]
  role_mapping = { "employees" -> LEARNER }
~~~

Đây là cấu hình minh họa. Trong production cần lưu client secret/private key trong secret manager, không trong file public hoặc source control.

Các nguyên tắc:
- Tenant/issuer mapping do admin cấu hình và xác minh.
- Không chọn issuer chỉ từ email domain do người dùng nhập.
- Kiểm tra issuer, audience, redirect URI và tenant mapping trước khi ánh xạ subject.
- Membership và role nội bộ được kiểm tra độc lập với claim.
- Cùng sub ở hai issuer là hai federation identity khác nhau.
- Nếu một IdP phục vụ nhiều tenant, claim tổ chức phải được xác minh theo hợp đồng; không lấy chuỗi tùy ý làm tenant ID.
- Account switching cần kết thúc hoặc thay đổi context theo quy trình rõ, tránh trộn session/tenant.

## 15. Logout và Single Logout

Logout trong federation có nhiều lớp:
- **RP local logout:** hủy session của ứng dụng hiện tại.
- **IdP logout:** kết thúc phiên tại nhà cung cấp danh tính.
- **Single Logout (SLO):** phối hợp đăng xuất giữa IdP và nhiều RP theo giao thức hỗ trợ.

Không giả định local logout tự kết thúc IdP session. Người dùng có thể đăng nhập lại ngay khi quay về RP vì IdP session vẫn còn. Ngược lại, logout tại IdP không đảm bảo mọi RP nhận được thông điệp hoặc xử lý đúng.

OIDC có các cơ chế như RP-Initiated Logout và front-channel/back-channel logout tùy triển khai. SAML có Single Logout profile. Các cơ chế này có khác biệt về độ tin cậy, trình duyệt, thông điệp, endpoint và khả năng triển khai; cần kiểm tra đặc tả và hỗ trợ của IdP/RP cụ thể.

Dù có SLO, RP vẫn cần:
- Xác minh logout message/token theo giao thức.
- Ràng buộc đúng issuer, client/session và trạng thái.
- Chống replay logout message nếu profile yêu cầu.
- Thu hồi local session và refresh token liên quan.
- Xử lý timeout/IdP unavailable theo policy.
- Không xóa session của account khác chỉ vì nhận logout request không hợp lệ.

## 16. Key, metadata và vòng đời quan hệ tin cậy

Federation phụ thuộc vào cấu hình tin cậy giữa hai miền. Một thay đổi nhỏ ở issuer, signing key, endpoint hoặc redirect URI có thể ảnh hưởng toàn bộ đăng nhập.

### Metadata và cấu hình

Quản lý:
- issuer/entity ID;
- authorization/token/userinfo/JWKS endpoint cho OIDC;
- SAML SSO/ACS/SLO endpoint và binding;
- client ID, redirect URI và audience;
- signing/encryption certificate hoặc JWKS;
- thuật toán được phép;
- claim mapping và assurance contract;
- thời hạn cache metadata và lịch refresh;
- owner, ngày phê duyệt, môi trường và tenant áp dụng.

Không tải metadata từ URL tùy ý do client cung cấp. Discovery metadata cần gắn với issuer đã cấu hình, kiểm tra HTTPS, issuer consistency và policy chống SSRF/redirect không mong đợi.

### Key rotation và compromise

Khi IdP xoay signing key, RP phải cập nhật JWKS/metadata theo lịch, hỗ trợ giai đoạn overlap hợp lý và ngừng tin key cũ khi hết thời hạn hoặc có sự cố. Nếu signing key bị lộ:
1. Xác định issuer, key ID và thời gian ảnh hưởng.
2. Ngừng chấp nhận key bị compromise theo quy trình khẩn cấp.
3. Cập nhật JWKS/trust metadata và cache.
4. Đánh giá token/assertion đã phát hành trong khoảng rủi ro.
5. Thu hồi RP session/refresh token có thể bị ảnh hưởng.
6. Kiểm tra account mapping, role và hành động đã thực hiện.
7. Ghi audit và thông báo theo quy trình incident response.

Không giữ public key cũ vô thời hạn chỉ vì muốn tránh lỗi đăng nhập; nhưng cũng không xóa key cũ quá sớm khi token hợp lệ còn cần xác minh. Lịch overlap phải được quản trị.

## 17. Các kiểu tấn công federation thường gặp

| Tấn công/lỗi | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| **Issuer mix-up** | RP nhầm IdP/issuer cho response hiện tại | Ràng buộc giao dịch với issuer, kiểm tra iss chính xác và cấu hình riêng từng IdP. |
| **Authorization code interception** | Attacker lấy code trong redirect | PKCE, TLS, redirect URI chính xác và code ngắn hạn. |
| **Login CSRF / injection** | Attacker khiến browser nạn nhân nhận response thuộc giao dịch của attacker | State, nonce, browser-bound transaction và callback validation. |
| **Token substitution** | Dùng ID Token/access token từ client, issuer hoặc flow khác | Kiểm tra issuer, audience, azp, nonce, signature và token type/use. |
| **Replay** | Dùng lại code, assertion hoặc token cũ | One-time code, nonce, assertion ID cache, expiry và replay policy. |
| **Open redirect** | Redirect URI hoặc return URL dẫn tới domain attacker | Exact redirect URI, allowlist route và không tin query tùy ý. |
| **Account-linking takeover** | Gộp account chỉ dựa trên email trùng | Mapping issuer + subject, reauthentication và bằng chứng từ account hiện tại. |
| **SAML signature wrapping** | Ứng dụng đọc node khác với node đã xác minh | Thư viện chuẩn, xác minh và sử dụng cùng node đã ký, test XML parser. |
| **Audience/recipient confusion** | Assertion phát cho RP khác được chấp nhận | Kiểm tra audience, recipient, destination và client ID. |
| **Claim privilege escalation** | Group/role ngoài dự kiến được ánh xạ thành admin | Allowlist mapping, least privilege, tenant-scoped role và audit. |
| **Stale claims** | Role/membership đã thu hồi nhưng token/session cũ còn hiệu lực | Token/session expiry, sync, revocation và kiểm tra quyền hiện hành. |
| **Metadata/key compromise** | Trust configuration hoặc signing key bị chiếm | Quản trị thay đổi, key rotation, alert và incident response. |
| **Confused deputy** | RP dùng token/identity của một bên để gọi API vượt scope | Audience/scope đúng, authorization độc lập và delegation rõ ràng. |

### Ví dụ token substitution

RP nhận một JWT có chữ ký hợp lệ từ IdP A nhưng token được phát hành cho client B. Nếu RP chỉ kiểm tra chữ ký và không kiểm tra audience, RP có thể chấp nhận token không dành cho mình. Chữ ký hợp lệ không đồng nghĩa token hợp lệ cho mọi RP.

## 18. Giả mã xử lý callback OIDC ở RP

Ví dụ dưới đây minh họa các trách nhiệm chính, không thay thế thư viện OIDC đã được kiểm chứng:

~~~java
LoginResult handleOidcCallback(Callback callback, BrowserSession browser) {
    PendingLogin pending =
        pendingLoginStore.requireActive(browser, callback.state());

    if (!constantTimeEquals(callback.state(), pending.state())) {
        throw genericLoginFailure();
    }

    TokenResponse tokens = oidcClient.exchangeCode(
        pending.issuerConfiguration(),
        callback.code(),
        pending.redirectUri(),
        pending.pkceCodeVerifier());

    VerifiedIdToken idToken = idTokenVerifier.verify(
        tokens.idToken(),
        pending.expectedIssuer(),
        pending.clientId(),
        pending.nonce(),
        allowedAlgorithms());

    FederatedIdentity identity = new FederatedIdentity(
        idToken.issuer(), idToken.subject());

    Account account = identityStore.findAccount(identity)
        .orElseGet(() -> provisioningPolicy.resolveOrCreate(identity, idToken));

    accountPolicy.requireActive(account);
    tenantPolicy.requireAllowedMembership(account, pending.tenantContext());

    pendingLoginStore.consumeAtomically(pending.id());

    // RP tạo session riêng, không dùng ID Token làm session cookie.
    return sessionService.createFreshSession(
        account.id(), idToken.authenticatedAt(),
        idToken.authenticationMethods(),
        idToken.assuranceContext());
}
~~~

Các điểm cần bổ sung trong production:
- Xử lý error response và authorization denial mà không làm lộ dữ liệu nội bộ.
- Kiểm tra redirect URI đã được cấu hình, không lấy từ callback.
- Xác minh ID Token bằng JWKS tin cậy và đầy đủ claim; code sample chỉ đại diện cho verifier đã làm việc đó.
- Đảm bảo pending login gắn đúng browser transaction, issuer, client, redirect URI và tenant.
- Không tự tạo account chỉ từ claim chưa được policy cho phép.
- Consume giao dịch pending nguyên tử để ngăn callback replay.
- Xử lý account/membership thay đổi giữa lúc callback và lúc commit.
- Không ghi code, token hoặc secret vào log.

## 19. Kiểm thử federation

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| OIDC callback có state đúng, code hợp lệ | Đổi code và xác minh ID Token; tạo RP session mới. |
| State sai hoặc không có pending transaction | Từ chối, không tạo session. |
| Nonce không khớp | Từ chối ID Token. |
| PKCE verifier sai | Token endpoint từ chối code exchange. |
| ID Token sai issuer | Từ chối. |
| Audience không chứa client ID RP | Từ chối. |
| azp không phù hợp khi được yêu cầu | Từ chối. |
| Token hết hạn hoặc iat bất hợp lý | Từ chối theo clock-skew policy. |
| Chữ ký sai hoặc kid không thuộc JWKS tin cậy | Từ chối. |
| Thuật toán ngoài allowlist | Từ chối. |
| Access token bị gửi vào endpoint nhận ID Token | Từ chối do token type/use/audience không phù hợp. |
| Cùng sub nhưng issuer khác | Không gộp account tự động. |
| Email trùng account hiện có nhưng issuer + sub mới | Chạy account-linking policy, không auto-link. |
| Role claim chứa giá trị không được mapping | Không cấp role ngoài allowlist. |
| Claim auth_time quá cũ cho step-up | Yêu cầu xác thực mới hoặc từ chối. |
| amr chỉ thể hiện password + SMS nhưng policy cần phishing resistance | Không coi là đáp ứng policy. |
| SAML audience/recipient/destination sai | Từ chối assertion. |
| SAML InResponseTo không khớp | Từ chối SP-initiated response. |
| SAML assertion ID đã dùng | Từ chối replay. |
| XML chứa signature wrapping attempt | Từ chối; chỉ dùng node đã xác minh theo thư viện. |
| JWKS key rotation | Xác minh key mới theo metadata và ngừng tin key cũ theo lịch. |
| IdP signing key bị compromise | Thực hiện trust/key incident procedure, revoke phiên liên quan. |
| SCIM deprovision user | Vô hiệu account/membership và xử lý session theo SLA. |
| User bị gỡ membership sau khi RP session tạo | Request tenant-scoped bị từ chối theo policy hiện hành. |
| Logout message giả hoặc replay | Không thu hồi session của account khác; xác minh message và correlation. |

### Kiểm thử negative path rất quan trọng

Không chỉ kiểm tra đăng nhập thành công. Cần cố ý thay issuer, audience, nonce, state, redirect URI, tenant, subject, signature và thời hạn. Mỗi lỗi phải dẫn tới từ chối trước khi tạo RP session hoặc cấp quyền. Kiểm tra cả side effect: callback sai không được tạo account, thêm membership, thay đổi role hoặc phát token.

## 20. Vận hành, giám sát và quyền riêng tư

Các chỉ số có ích:
- tỷ lệ login thành công/thất bại theo issuer và protocol;
- lỗi state, nonce, PKCE, signature, issuer/audience và metadata;
- số assertion/token bị từ chối do replay hoặc hết hạn;
- thời gian IdP phản hồi và tỷ lệ timeout;
- số account JIT được tạo, identity được link/unlink và membership được deprovision;
- key rotation age, JWKS refresh failure và certificate expiry;
- tỷ lệ step-up theo acr/amr và kết quả MFA;
- số session bị revoke sau sự kiện IdP/SCIM;
- số lỗi claim mapping hoặc tenant mapping.

Log nên có request/correlation ID, issuer ID đã cấu hình, client ID, kết quả kiểm tra, reason code và account ID nội bộ sau khi đã xác định. Không log authorization code, raw ID/access/refresh token, client secret, private key hoặc assertion nhạy cảm. Claim profile là dữ liệu cá nhân; chỉ lưu phần cần thiết và đặt retention/access policy.

## 21. Bài tập tình huống

Một nền tảng học tập kết nối hai IdP: trường Đại học A và nhà cung cấp SSO của doanh nghiệp B. Cả hai IdP đều có thể phát hành người dùng với email giống nhau. Ứng dụng hiện tìm account bằng email, tự gán tenant theo domain email và ánh xạ mọi group có tên ADMIN thành vai trò quản trị. Ứng dụng chỉ kiểm tra chữ ký JWT, không kiểm tra audience hoặc nonce. Khi người dùng logout, ứng dụng chỉ xóa cookie cục bộ.

**Yêu cầu phân tích:**

1. Vì sao email không đủ để định danh federation?
2. Thiết kế bảng mapping account theo issuer + subject như thế nào?
3. Vì sao audience và nonce phải được kiểm tra dù chữ ký hợp lệ?
4. Cách ánh xạ tenant và group role cần thay đổi ra sao?
5. Cần phân biệt ID Token và Access Token thế nào?
6. Logout local khác SSO/SLO ra sao?
7. Khi nhân viên bị deprovision tại IdP, RP xử lý account/session như thế nào?

**Hướng phân tích:** Dùng (issuer, subject) làm khóa federation; email là claim profile và có thể trùng/thay đổi. Kiểm tra chữ ký, issuer, audience, nonce, thời hạn và các claim cần thiết trước khi map identity. Tenant được xác định từ cấu hình IdP/tenant đã quản trị và membership policy, không chỉ domain email. Group chỉ được map qua allowlist cụ thể theo issuer/tenant. ID Token xác nhận authentication cho RP; Access Token dành cho resource server. Local logout hủy RP session; SLO cần giao thức phối hợp và vẫn phải xử lý timeout/không hỗ trợ. SCIM hoặc event provisioning có thể deprovision account, thu hồi membership/session theo SLA.

## 22. Checklist review

- [ ] Mỗi IdP có issuer/entity ID, endpoints, keys và owner được quản trị rõ.
- [ ] RP không tin issuer hoặc metadata URL tùy ý từ client.
- [ ] OIDC dùng flow phù hợp, ưu tiên Authorization Code với PKCE.
- [ ] State, nonce, code verifier và pending transaction được sinh ngẫu nhiên, ràng buộc và hết hạn.
- [ ] Redirect URI khớp chính xác cấu hình; không có open redirect.
- [ ] ID Token được kiểm tra signature, issuer, audience, azp, expiry, iat, nonce và subject.
- [ ] ID Token và Access Token được dùng đúng mục đích/audience.
- [ ] JWKS/metadata cache và key rotation có policy, refresh và incident path.
- [ ] SAML assertion kiểm tra signature, issuer, audience, recipient, destination, conditions và InResponseTo.
- [ ] XML signature validation dùng thư viện đã kiểm chứng và node đã xác minh.
- [ ] Federation identity được ánh xạ bằng issuer + subject, không chỉ email.
- [ ] Account linking yêu cầu xác thực account hiện tại và audit.
- [ ] Claim/group/role được tối thiểu hóa và ánh xạ qua allowlist.
- [ ] acr/amr/auth_time được diễn giải theo hợp đồng tin cậy, không tự suy MFA/phishing resistance.
- [ ] Tenant và membership được kiểm tra độc lập sau authentication.
- [ ] RP tạo session riêng, có expiry, rotation và revocation.
- [ ] JIT/SCIM provisioning và deprovisioning có vòng đời rõ.
- [ ] Logout/SLO được hiểu đúng, xác minh message và thu hồi local session.
- [ ] Log không chứa code, token, secret hoặc assertion nhạy cảm.
- [ ] Có negative tests cho issuer, audience, nonce, replay, tenant mapping và account linking.

## 23. Ghi nhớ

**Identity federation cho phép một RP dựa vào kết quả xác thực từ IdP khác, nhưng chỉ trong quan hệ tin cậy được cấu hình và kiểm tra đầy đủ.** OIDC và SAML cung cấp giao thức để chuyển kết quả; RP vẫn phải xác minh chữ ký, issuer, audience, thời hạn, giao dịch, claim và replay, rồi ánh xạ subject sang account nội bộ theo chính sách. Sau đó RP tạo session riêng, kiểm tra tenant/membership, áp dụng authorization và quản lý logout/provisioning.

Khi review một luồng federation, hãy hỏi: **RP đang tin issuer nào và vì sao? Response có được ràng buộc với đúng giao dịch, client và audience không? Subject được ánh xạ bằng khóa ổn định nào? Claim MFA có ý nghĩa gì theo hợp đồng? Nếu account bị deprovision hoặc signing key bị lộ, RP ngừng tin session/token cũ bằng cách nào?**
