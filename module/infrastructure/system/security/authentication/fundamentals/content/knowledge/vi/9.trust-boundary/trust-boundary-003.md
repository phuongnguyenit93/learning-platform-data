# Application và identity provider — Ranh giới tin cậy trong xác thực liên kết

Khi một ứng dụng cung cấp nút **“Đăng nhập với tổ chức”** hoặc **“Đăng nhập bằng nhà cung cấp danh tính”**, ứng dụng thường không trực tiếp kiểm tra mật khẩu, passkey hay MFA của người dùng. Thay vào đó, nó **tin vào một kết quả xác thực được một Identity Provider (IdP) đã cấu hình phát hành**, với các điều kiện kỹ thuật và chính sách cụ thể. Đường nối giữa ứng dụng và IdP là một **trust boundary** quan trọng: thông tin từ một hệ thống khác chỉ có thể trở thành danh tính đăng nhập nội bộ sau khi ứng dụng xác minh đúng nguồn, đúng mục đích, đúng phiên yêu cầu và đúng mức bảo đảm.

Bài học thuộc chủ đề **Trust boundary** của nền tảng **authentication**. Ta sẽ theo dõi toàn bộ đường đi từ credential (mật khẩu, MFA, passkey hoặc chứng chỉ), kết quả xác thực liên kết, token và phiên cho tới liên kết danh tính, khôi phục tài khoản và phòng chống phishing, replay hoặc chiếm quyền truy cập. Trọng tâm là xác định chính xác **ứng dụng cần tin gì, không được tin gì, phải kiểm tra ở đâu và xử lý ra sao khi IdP hoặc luồng liên kết gặp sự cố**.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của ứng dụng, IdP, trình duyệt, authorization server và resource server trong một luồng đăng nhập liên kết.
2. Vẽ sơ đồ **trust boundary** của OIDC và chỉ ra điểm dữ liệu chưa đáng tin trở thành một khẳng định danh tính đã được kiểm chứng.
3. Phân biệt việc **IdP xác thực người dùng** với việc **ứng dụng cấp phiên và quyết định quyền truy cập**.
4. Giải thích luồng **OpenID Connect Authorization Code + PKCE**, mục đích của `state`, `nonce`, redirect URI và các phép kiểm tra ID token.
5. Thiết kế mapping giữa **issuer + subject** của IdP và account ID nội bộ; tránh account takeover do liên kết bằng email hoặc nhận nhầm IdP.
6. Xác định cách giới hạn độ tin cậy với `acr`, `amr`, `auth_time`, chính sách MFA và step-up authentication.
7. Liệt kê và kiểm thử các lỗi như issuer mix-up, token substitution, replay, open redirect, sai audience, chiếm phiên, lạm dụng recovery và cấu hình tin cậy quá rộng.
8. Xây dựng bộ kiểm soát để quản lý vòng đời tích hợp IdP: khóa ký, thay đổi cấu hình, tài khoản bị vô hiệu hóa, logout, outage, log và giám sát.

## 2. Ai làm gì trong kiến trúc?

Hãy dùng ví dụ giả định **LearnHub**: học viên đăng nhập vào cổng học bằng tài khoản trường **CampusID**; LearnHub là ứng dụng có dữ liệu bài học, còn CampusID sở hữu cơ chế xác thực và quản lý credential.

| Thành phần | Vai trò | Phải chịu trách nhiệm |
| --- | --- | --- |
| **Người dùng / claimant** | Khẳng định danh tính và thực hiện thao tác xác thực | Sử dụng credential của mình; có thể bị phishing hoặc mất thiết bị. |
| **User agent (trình duyệt)** | Chuyển hướng giữa LearnHub và CampusID, giữ cookie theo origin | Không phải thành phần mà máy chủ có thể tin tuyệt đối; redirect, URL và dữ liệu client có thể bị tác động. |
| **Application / Relying Party (RP)** | Tin vào IdP đã định cấu hình để xác thực đăng nhập | Khởi tạo request, kiểm tra kết quả, liên kết đúng tài khoản, cấp phiên nội bộ, phân quyền và quản lý logout/recovery của ứng dụng. |
| **Identity Provider / OpenID Provider (OP)** | Xác thực người dùng và phát hành khẳng định danh tính theo OIDC | Quản lý credential/MFA/passkey, chính sách xác thực và ký ID token; duy trì định danh `sub`. |
| **Authorization server** | Phát hành authorization code và token theo OAuth 2.0/OIDC | Kiểm soát client, redirect URI, PKCE, token endpoint và phạm vi. Trong OIDC, OP đảm nhiệm chức năng này. |
| **Resource server / API** | Bảo vệ dữ liệu hoặc nghiệp vụ phía máy chủ | Kiểm tra token/phiên và quyền cho từng request; không chỉ tin UI đã đăng nhập. |
| **Credential store / authenticator** | Chứa hoặc kiểm tra vật liệu xác thực | Có thể thuộc IdP; RP không mặc nhiên được đọc mật khẩu, private key hoặc bí mật MFA. |

**Ba ranh giới cần tách bạch:**

- **Người dùng ↔ IdP:** IdP kiểm tra bằng chứng xác thực, ví dụ mật khẩu kèm TOTP hoặc passkey/WebAuthn. Kết quả phụ thuộc chính sách, credential đã ghi danh và khả năng chống phishing/replay của authenticator.
- **IdP ↔ ứng dụng:** IdP chuyển một **assertion/kết quả xác thực** mà RP chỉ chấp nhận sau khi kiểm tra giao thức, chữ ký, issuer, audience, thời gian và ngữ cảnh yêu cầu.
- **Ứng dụng ↔ tài nguyên:** RP cấp phiên ứng dụng hoặc token theo kiến trúc nội bộ; API xác thực yêu cầu và kiểm tra **authorization** độc lập. Một danh tính đã xác thực không tự có mọi quyền.

Trong **SAML**, ứng dụng thường là **Service Provider (SP)**, IdP phát hành SAML assertion. Trong **OIDC**, ứng dụng là **Relying Party (RP)** và IdP là **OpenID Provider (OP)**. Hai giao thức có cách đóng gói/kiểm tra khác nhau; nguyên lý ranh giới tin cậy là tương tự.

## 3. Vì sao đây là trust boundary?

Dữ liệu đi qua một trust boundary khi được tạo hoặc kiểm soát bởi miền quản trị khác. Việc CampusID phát hành một ID token không khiến LearnHub mặc nhiên tin mọi trường trong token. LearnHub chỉ nên tin token sau khi xác định **CampusID có phải IdP được phép cho luồng này**, token **có được phát hành cho LearnHub**, **đang còn hiệu lực**, **đến từ đúng phiên đăng nhập vừa khởi tạo**, và **đại diện đúng subject cần đăng nhập**.

~~~mermaid
flowchart LR
    U["Người dùng / thiết bị"] -->|"1. Xác thực credential"| OP["CampusID — Identity Provider"]
    B["Trình duyệt"] <-->|"2. Redirect / callback"| RP["LearnHub — Relying Party"]
    B <-->|"Đi tới trang đăng nhập"| OP
    RP -->|"3. Code exchange qua back channel"| OP
    OP -->|"4. ID token / token response"| RP
    RP -->|"5. Kiểm tra token, liên kết account"| DB[("Identity mapping nội bộ")]
    RP -->|"6. Cấp session LearnHub"| B
    B -->|"7. Session hoặc access token"| API["LearnHub API"]
    API -->|"8. Xác thực + kiểm tra quyền"| DATA[("Tài nguyên")]
~~~

Sơ đồ là mô hình logic của **OIDC Authorization Code Flow**, không thể hiện mọi thông điệp và chi tiết triển khai. Ở bước 2, trình duyệt thường mang authorization code qua redirect; ở bước 3–4, ứng dụng có backend đổi code tại token endpoint của OP. Đó là sự phân chia quan trọng: **trình duyệt vận chuyển dữ liệu qua kênh front channel nhưng không được tự xác nhận token hợp lệ hoặc tự tuyên bố đã đăng nhập**.

### 3.1. Những điểm vượt qua ranh giới

| Dữ liệu/giao dịch | Xuất phát | Khi nào RP được tin? |
| --- | --- | --- |
| Nút “Đăng nhập CampusID” | UI/trình duyệt | Chỉ là yêu cầu bắt đầu đăng nhập; chưa có khẳng định danh tính. |
| Authorization response có `code`, `state` | Redirect qua trình duyệt | Sau khi đối chiếu `state` với giao dịch đang chờ, xác định đúng nhà phát hành theo thiết kế đa IdP và dùng code exchange an toàn. |
| ID token | Token endpoint/OP theo luồng hợp lệ | Chỉ sau kiểm tra chữ ký, `iss`, `aud`, thời hạn và các điều kiện OIDC/ngữ cảnh. |
| `sub`, `email`, `name`, `groups` | Claims do OP cung cấp | Chỉ sau xác minh token và **áp chính sách riêng cho từng claim**; mức độ tin không giống nhau. |
| `acr`, `amr`, `auth_time` | Kết quả/phản hồi xác thực của OP | Chỉ khi đúng issuer và RP hiểu ý nghĩa, nguồn gốc, cách kiểm tra của giá trị. |
| App session | RP phát hành | Chỉ tạo sau khi hoàn tất toàn bộ kiểm tra đăng nhập và mapping tài khoản; phải bảo vệ phiên. |
| Quyền đọc/sửa dữ liệu | Backend/API | Chỉ sau kiểm tra authorization cho subject, role, tài nguyên và điều kiện nghiệp vụ. |

**Câu hỏi thực dụng:** “Ai có thể tạo hoặc thay đổi trường này?”. Nếu câu trả lời là **trình duyệt, URL callback, local storage hoặc một IdP chưa được cấp quyền**, RP không được coi giá trị đó là nguồn sự thật.

## 4. Luồng OIDC Authorization Code + PKCE

OIDC bổ sung thông tin **xác thực danh tính** trên nền OAuth 2.0. OAuth 2.0 vốn tập trung vào **ủy quyền truy cập tài nguyên**; có access token không đủ để kết luận người dùng vừa được xác thực là ai. Khi đăng nhập bằng OIDC, ứng dụng xử lý **ID token** và giao thức xác thực riêng; **access token** được dùng cho API/resource server theo đúng audience và scope.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant RP as LearnHub RP
    participant OP as CampusID OP
    U->>B: Chọn đăng nhập với trường
    B->>RP: GET /login/campus
    RP->>RP: Tạo state, nonce, PKCE verifier, giao dịch chờ
    RP-->>B: Redirect tới authorization endpoint
    B->>OP: Yêu cầu authorize (code + PKCE + state + nonce)
    OP->>U: Xác thực credential và MFA theo policy
    OP-->>B: Redirect với code và state
    B->>RP: Callback có code, state
    RP->>RP: Đối chiếu state, client/issuer và giao dịch chờ
    RP->>OP: POST token endpoint (code, redirect_uri, PKCE verifier)
    OP-->>RP: ID token và token response
    RP->>RP: Xác minh ID token, nonce, subject, bảo đảm
    RP->>RP: Tìm/liên kết account, áp chính sách truy cập
    RP-->>B: Cấp session cookie an toàn và redirect nội bộ
    B->>RP: Request kèm session
    RP->>RP: Kiểm tra phiên và quyền
~~~

### 4.1. Trước redirect: khởi tạo đúng giao dịch

RP chọn **issuer/OP từ cấu hình được phép**, rồi tạo dữ liệu ngẫu nhiên khó đoán cho từng giao dịch:

- **`state`**: ràng buộc authorization response với request đã khởi tạo để chống CSRF/login CSRF và lỗi ghép nhầm callback. Lưu server-side hoặc dùng cơ chế bảo vệ toàn vẹn tương đương và so sánh khi callback.
- **`nonce`**: gắn ID token với yêu cầu xác thực tương ứng; khi yêu cầu/cấp nonce, RP cần xác minh giá trị trong ID token đúng giao dịch để chống dùng lại/substitution.
- **PKCE `code_verifier`** và `code_challenge` với **S256**: giúp bảo vệ authorization code nếu bị chặn hoặc bị dùng bởi client khác không có verifier; vẫn cần kiểm tra state, issuer và token.
- **Redirect URI**: dùng URI đã đăng ký tại OP và so khớp chính xác theo yêu cầu giao thức/cấu hình, tránh wildcard rộng hoặc open redirect.
- **Giao dịch chờ**: ghi ngữ cảnh như phiên khởi tạo, IdP đích, target action, thời gian hết hạn, trạng thái chưa dùng và thông tin chống replay.

Không đặt bí mật đăng nhập, mã OTP, private key hoặc client secret trong redirect URL. Với confidential client, **client authentication** tại token endpoint cần thực hiện theo phương thức đã đăng ký; PKCE không tự thay thế yêu cầu xác thực client tương ứng.

### 4.2. Callback: kiểm tra trước khi cấp phiên

Sau redirect, callback là một **điểm tiếp nhận dữ liệu từ bên ngoài**. Một quy trình an toàn ở mức khái niệm:

1. Tìm giao dịch đăng nhập chờ bằng ngữ cảnh server đáng tin; xác minh `state`, tuổi giao dịch, tính duy nhất và đúng IdP đã chọn. Với đa IdP, triển khai biện pháp chống **authorization server mix-up** thích hợp, ví dụ kiểm tra issuer trong authorization response nếu giao thức/hỗ trợ áp dụng và ràng buộc endpoint với issuer cố định.
2. Gửi authorization code tới **token endpoint của issuer đã ghi trong giao dịch**, sử dụng `code_verifier` đúng lần khởi tạo và redirect URI tương ứng.
3. Kiểm tra ID token: thuật toán/chữ ký bằng khóa được chấp nhận từ issuer, **`iss`** đúng issuer, **`aud`** chứa client ID của LearnHub, `exp` còn hạn; xét `iat`, `azp`, `nonce`, `auth_time` và các điều kiện khác theo OIDC/profile triển khai. Không chấp nhận token thiếu chữ ký hoặc thuật toán không được phép.
4. Lấy **`sub`** từ ID token đã xác minh, tra bảng mapping bằng **`(issuer, sub)`**. Kiểm tra tài khoản nội bộ còn hoạt động, được cấp quyền dùng IdP này và không bị khóa bởi chính sách của LearnHub.
5. Kiểm tra chính sách assurance: nếu cần MFA, WebAuthn chống phishing hoặc xác thực gần đây, chỉ chấp nhận khi kết quả và ngữ nghĩa claim đã kiểm chứng đạt yêu cầu; nếu không, yêu cầu step-up hoặc từ chối.
6. **Tiêu thụ giao dịch đăng nhập một lần**, tạo session ứng dụng mới và thiết lập cookie an toàn. Không cho client tự gán role, account ID hoặc session ID.
7. Ghi sự kiện cần thiết để giám sát, nhưng không lưu code, access token, ID token, session secret hoặc thông tin credential trong log.

~~~text
handleOidcCallback(callback, browserSession):
    tx = requirePendingTransaction(browserSession)
    assert constantTimeEqual(callback.state, tx.state)
    assert tx.notExpired and not tx.consumed
    assert callbackIssuerMatchesExpectedIssuer(callback, tx.issuer)
    result = exchangeCodeAtPinnedTokenEndpoint(
        issuer=tx.issuer, code=callback.code,
        redirectUri=tx.redirectUri, pkceVerifier=tx.codeVerifier
    )
    identity = verifyOidcIdToken(result.idToken,
        expectedIssuer=tx.issuer,
        expectedClientId=tx.clientId,
        expectedNonce=tx.nonce)
    account = requireLinkedAndActiveAccount(tx.issuer, identity.sub)
    assert assuranceMeetsPolicy(identity, tx.action)
    consume(tx)
    return createFreshApplicationSession(account.id)
~~~

Pseudocode chỉ mô tả **các bất biến kiểm soát**. Triển khai thật nên dùng thư viện OIDC đã được duy trì và kiểm thử, chú ý điều kiện đặc thù của profile, response mode, client type và cách xử lý lỗi. Nếu giao dịch đã được tiêu thụ, code dùng lại, state sai hoặc issuer không phù hợp, RP phải **không cấp phiên**.

### 4.3. ID token không phải access token

| Nội dung | ID token | Access token |
| --- | --- | --- |
| Mục đích | Đưa khẳng định về sự kiện xác thực và subject tới RP | Cho phép client truy cập resource server trong phạm vi cấp |
| Bên nhận chính | OIDC client/RP, thông qua audience dành cho client | Resource server/API có audience dành cho tài nguyên |
| Kiểm tra trọng tâm | Issuer, client audience, chữ ký, hạn, nonce và điều kiện OIDC | Issuer/authority, audience resource, chữ ký hoặc introspection, hạn, scope/quyền và ràng buộc khác |
| Sai lầm điển hình | Gửi ID token để gọi API như vé truy cập | Dùng access token bất kỳ để khẳng định user đã xác thực |

Một token hợp lệ về mặt chữ ký vẫn có thể **không hợp lệ về mục đích** khi audience sai hoặc được tạo cho client/API khác. Token không nên được chuyển tùy ý giữa các trust boundary.

## 5. Claim và định danh: dữ liệu nào đủ để liên kết tài khoản?

Sự tin cậy với OP **không đồng nghĩa** với việc mọi thuộc tính người dùng do OP đưa ra đều ổn định, duy nhất hoặc phù hợp để cấp quyền.

### 5.1. Vì sao phải liên kết bằng `issuer + subject`?

Trong OIDC, `sub` là subject identifier có ý nghĩa trong phạm vi **issuer**. Hai OP khác nhau có thể dùng cùng chuỗi `sub` nhưng đại diện hai chủ thể khác nhau. Một OP có thể dùng **pairwise subject identifier** khác nhau cho các client/sector theo cấu hình. Vì thế, ánh xạ địa phương nên dùng **cặp `(iss, sub)`** và duy trì account ID nội bộ riêng.

~~~text
Local account: account-314
Linked identities:
  - issuer: https://idp.campus.example
    subject: 00u-campus-user-7
    accountId: account-314
  - issuer: https://login.partner.example
    subject: 99b-partner-user-8
    accountId: account-314
~~~

Các địa chỉ tên miền trên là **ví dụ giả định**. Không dựa vào ID nội bộ của đối tác khi chưa gắn issuer, không giả định `sub` của OP A có nghĩa ở OP B.

**Lỗi nguy hiểm:** Tự động ghép hai tài khoản chỉ vì email trùng nhau. Email có thể chưa được xác minh, thay đổi theo thời gian, được tái cấp cho người khác hoặc bị quản lý bởi miền khác. Ngay cả `email_verified=true` cũng chỉ nói đến cách OP xác minh email theo chính sách của họ; không tự chứng minh người dùng sở hữu tài khoản LearnHub cũ.

### 5.2. Quy tắc cho liên kết, tạo mới và hủy liên kết

- **Đăng nhập bằng liên kết đã biết:** tìm đúng mapping `(issuer, sub)`, kiểm tra trạng thái tài khoản và chính sách.
- **Lần đầu đăng nhập:** tạo tài khoản mới chỉ theo chính sách đăng ký/provisioning; nếu có tài khoản cũ trùng email, yêu cầu quy trình liên kết an toàn thay vì tự sáp nhập.
- **Liên kết thêm IdP:** người dùng phải có phiên hiện tại đã xác thực đủ mạnh và thực hiện giao dịch liên kết mới với IdP đích; gắn kết quả với đúng account/phiên và thông báo cho chủ tài khoản.
- **Hủy liên kết:** xác thực lại khi cần, ngăn xóa credential cuối cùng dẫn tới khóa tài khoản ngoài ý muốn và cân nhắc thu hồi phiên/token.
- **Đổi email hoặc tên:** không thay account mapping chỉ dựa vào thuộc tính hồ sơ; cập nhật theo chính sách riêng.
- **Tài khoản bị vô hiệu hóa ở IdP:** LearnHub cần chiến lược **deprovisioning** hoặc kiểm tra trạng thái theo mức rủi ro; phiên cũ không nhất thiết biến mất ngay khi IdP vô hiệu hóa người dùng.
- **Đồng bộ nhóm/quyền:** claim `groups`/`roles` chỉ được dùng sau khi thống nhất nguồn, ngữ nghĩa và vòng đời; vẫn áp kiểm tra quyền của LearnHub tại API.

### 5.3. Đừng để IdP cấp quyền vượt thiết kế của ứng dụng

CampusID có thể cho biết một người thuộc nhóm “lecturer”, nhưng LearnHub phải định nghĩa nhóm nào được đổi thành role nào, trong điều kiện nào và có cần phê duyệt nội bộ không. Mọi mapping từ **external role** sang **internal permission** là một quyết định ở trust boundary.

Ví dụ kiểm tra:

~~~text
verifiedExternalIdentity = (iss, sub)
localAccount = identityLinkStore.lookup(verifiedExternalIdentity)
assert localAccount.active
assert externalIssuerAllowedForTenant(localAccount.tenant, iss)

roleEvidence = verifiedAndApprovedGroupMapping(iss, claims.groups)
permissions = internalPolicy.evaluate(
    account=localAccount,
    roleEvidence=roleEvidence,
    resource=requestedResource
)
assert permissions.allow(requestedAction)
~~~

Không đọc một trường `role=admin` do browser gửi rồi áp vào session. Nếu OP thay đổi cách phát hành nhóm, ứng dụng phải phát hiện và kiểm tra lại mapping thay vì tự cấp quyền mới.

## 6. Chọn và tin cậy đúng Identity Provider

Ứng dụng có thể hỗ trợ **một OP** hoặc **nhiều OP** cho nhiều trường/khách hàng. Thiết kế đa IdP làm tăng nguy cơ dùng nhầm authority, issuer, client configuration và subject mapping.

### 6.1. Danh sách tin cậy phải rõ ràng

Với mỗi IdP được phép, RP quản lý:

| Thành phần cấu hình | Yêu cầu |
| --- | --- |
| **Issuer** | Danh tính canonical chính xác và ổn định của OP; phải so khớp với `iss` của token. |
| **Client ID và redirect URIs** | Từng client thuộc OP tương ứng; không dùng chung nhầm audience. |
| **Authorization/token/JWKS endpoints** | Lấy từ cấu hình hoặc metadata đáng tin, gắn với issuer; không nhận endpoint tùy ý từ client. |
| **Thuật toán và khóa ký được phép** | Xác minh chữ ký bằng khóa đúng issuer; từ chối thuật toán không được chấp nhận và khóa từ nguồn lạ. |
| **Định nghĩa claim và mức assurance** | Mapping `acr`, `amr`, `auth_time`, nhóm, email và quy tắc provisioning theo hợp đồng với OP. |
| **Quy trình vận hành** | Xoay khóa, khóa client, thu hồi quyền, outage, thay đổi tenant, log và người chịu trách nhiệm. |

### 6.2. Discovery/JWKS là một bề mặt tấn công

OIDC Discovery giúp RP tìm metadata của OP và **JWKS** giúp lấy khóa công khai để kiểm tra chữ ký. Tuy nhiên, nếu RP cho người dùng gửi một URL issuer hoặc JWKS tùy ý mà không xác minh allowlist/tenant, attacker có thể hướng hệ thống đến **IdP giả** hoặc endpoint nội bộ (rủi ro **SSRF**).

Trong sản phẩm cho phép đăng nhập với nhiều tổ chức, quy trình onboarding IdP nên được kiểm soát: xác minh quyền quản trị miền/tenant theo yêu cầu, áp allowlist/chính sách, xác minh TLS, quản lý metadata tin cậy và chống redirect không an toàn. Khóa ký mới có thể xuất hiện do **rotation**; ứng dụng cần hỗ trợ cập nhật khóa theo quy trình được tin cậy nhưng không chấp nhận `jku`, `x5u` hay URL khóa tùy ý bên trong token nếu chưa có chính sách kiểm soát nguồn phù hợp.

### 6.3. Issuer mix-up và confusion

Nếu LearnHub gửi request sang CampusID nhưng xử lý callback bằng cấu hình của PartnerID, authorization code hoặc kết quả có thể bị trao đổi với sai endpoint. **Mix-up** là nhóm lỗi nguy hiểm trong hệ thống nhiều authorization server. RP cần lưu **OP dự kiến cho mỗi giao dịch** và ràng buộc callback/code exchange với issuer đó; khi hỗ trợ, áp cơ chế issuer identification trong authorization response theo chuẩn tương ứng, kết hợp các bảo vệ CSRF/PKCE.

**Quy tắc dễ nhớ:** issuer phải được chọn **trước khi redirect** theo cấu hình đáng tin; **không** để URL callback hoặc một claim chưa kiểm chứng quyết định “nên tin issuer nào”.

## 7. Thông tin mức bảo đảm từ IdP: có thể dựa vào đến đâu?

Một OP có thể hỗ trợ nhiều phương thức: mật khẩu, TOTP, push, khóa bảo mật, passkey với xác minh người dùng hoặc xác thực dựa trên chứng chỉ. RP đôi khi cần mức bảo đảm cao hơn cho hành động nhạy cảm, tức **step-up authentication**.

| Claim/tham số | Công dụng | Giới hạn |
| --- | --- | --- |
| `auth_time` | Thời điểm xác thực người dùng tại OP | Nói đến tính gần đây, không tự chứng minh mức MFA. |
| `acr` | Authentication Context Class Reference mà OP khẳng định | Phải thống nhất ngữ nghĩa giữa RP và OP; không tự gán một mức tùy ý. |
| `amr` | Các phương thức xác thực được dùng | Cần hiểu ý nghĩa thực tế và chính sách của OP; nhãn không thay chứng cứ kỹ thuật. |
| `max_age` | RP yêu cầu tuổi xác thực tối đa trong OIDC | Freshness, không tự bảo đảm phishing resistance. |
| `prompt=login` | Yêu cầu OP tương tác đăng nhập lại | Không tự nâng phương thức yếu lên mức cao. |
| `acr_values` | RP nêu lớp xác thực mong muốn | OP có thể không đáp ứng giá trị yêu cầu; RP phải kiểm tra **kết quả thực tế**. |

**Tình huống:** Giảng viên LearnHub đã đăng nhập qua CampusID bằng mật khẩu. Trước khi xuất dữ liệu nhạy cảm, LearnHub yêu cầu OP thực hiện step-up bằng WebAuthn/passkey phù hợp. LearnHub cần yêu cầu OP theo cấu hình đã thỏa thuận, rồi kiểm tra `auth_time` và `acr`/`amr` có đáng tin, đủ mạnh và đủ mới hay không. Nếu thiếu claim bắt buộc hoặc không đạt policy, API xuất dữ liệu **không được thực thi**.

Chữ ký ID token chứng minh OP ký token đó, **không tự chứng minh** rằng OP đã áp dụng đúng chính sách MFA mà RP muốn. Cần có hợp đồng kỹ thuật, cấu hình, kiểm thử và giám sát chất lượng IdP theo mức rủi ro.

## 8. Phiên của ứng dụng và phiên của IdP là hai phạm vi khác nhau

Người dùng có thể có:

1. **IdP session:** cookie/phiên tại miền CampusID dùng cho Single Sign-On (SSO).
2. **Application session:** cookie/phiên tại miền LearnHub sau khi RP xác minh đăng nhập.
3. **Access token/refresh token:** được phát hành cho client/resource theo phạm vi, có vòng đời riêng.

**Đăng xuất khỏi LearnHub** có thể thu hồi phiên ứng dụng nhưng không kết thúc phiên CampusID. Ngược lại, **đăng xuất khỏi CampusID** không tự động khiến mọi ứng dụng thu hồi phiên nếu chưa triển khai logout notification/coordination phù hợp.

### 8.1. Tạo và bảo vệ application session

Sau khi xác thực liên kết thành công, LearnHub phải phát hành **session ID mới** đủ entropy, tránh session fixation. Với ứng dụng web HTTPS dùng cookie tham chiếu, một cấu hình minh họa:

~~~http
Set-Cookie: __Host-session=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong ví dụ này, `Secure` buộc gửi cookie qua HTTPS, `HttpOnly` hạn chế JavaScript đọc cookie, `SameSite` giảm một số tình huống cookie được gửi qua site khác. Prefix `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain`. Cookie vẫn cần chính sách **idle timeout**, **absolute timeout**, thu hồi, quản lý nhiều thiết bị, chống **CSRF** và **XSS**. SameSite không tự thay thế kiểm soát CSRF cho mọi kiểu request.

Nếu ứng dụng dùng token tự chứa, phải kiểm tra issuer/audience/expiry/scope đúng resource và có chiến lược thu hồi, TTL phù hợp. Không để access token hoặc refresh token trong URL; bảo vệ nơi lưu token theo loại client và mô hình đe dọa.

### 8.2. Logout, session expiry và deprovisioning

- **Local logout:** vô hiệu phiên LearnHub và xóa cookie liên quan; không tuyên bố đã đăng xuất mọi ứng dụng nếu thực tế chưa có cơ chế.
- **Federated logout:** có thể sử dụng các cơ chế logout phù hợp của giao thức/OP, ví dụ OIDC RP-Initiated Logout hoặc Back-Channel Logout khi được hỗ trợ và triển khai đúng. Cần xác minh thông điệp logout trước khi thu hồi phiên.
- **IdP account disabled:** RP không tự động biết ngay ở mọi mô hình. Đối với hệ thống rủi ro cao, thiết kế thông báo vòng đời, đồng bộ trạng thái, session TTL/revalidation và thu hồi nội bộ.
- **Mất mạng hoặc IdP outage:** phiên ứng dụng hiện có có thể được tiếp tục theo chính sách rủi ro, nhưng các luồng login/step-up mới cần OP có thể thất bại an toàn. Không hạ MFA hoặc bỏ qua kiểm tra issuer chỉ vì IdP tạm gián đoạn.
- **Thay đổi tenant/issuer:** yêu cầu quy trình migration và kiểm chứng mapping rõ ràng; không tự ghép token của issuer mới với `sub` của issuer cũ.

## 9. Recovery và credential lifecycle nằm qua nhiều biên

IdP có thể quản lý mật khẩu, MFA, passkey, chứng chỉ và quy trình khôi phục của họ. LearnHub có thể quản lý thêm **account mapping, session, quyền, thông tin liên lạc và phương thức khôi phục nội bộ**. Phải xác định **hệ thống nào có quyền cấp lại loại bằng chứng nào**.

Ví dụ một giáo viên mất passkey CampusID:

- **CampusID** xử lý khôi phục credential theo chính sách của IdP và phát hành kết quả đăng nhập mới khi được phép.
- **LearnHub** chỉ chấp nhận kết quả đăng nhập sau khi xác minh giao thức; nếu tài khoản LearnHub có mức bảo đảm riêng cho sửa điểm, nó phải kiểm tra mức đó thay vì tự cho qua vì vừa có token mới.
- Nếu người dùng muốn **liên kết một IdP khác**, LearnHub cần yêu cầu xác thực đủ mạnh với tài khoản hiện tại và với IdP mới, tránh chiếm quyền qua email trùng hoặc help desk.
- Nếu OP vô hiệu hóa danh tính, LearnHub cần kế hoạch **deprovisioning** để quyền và phiên không kéo dài ngoài chính sách.
- Nếu hỗ trợ can thiệp thủ công, nhân viên hỗ trợ phải có quy trình xác minh và audit tương xứng; **đường khôi phục yếu** có thể vô hiệu lợi ích của MFA hoặc passkey chống phishing.

**Tư duy vòng đời:** không chỉ hỏi “người dùng đăng nhập được không?”, mà còn “ai có quyền ghi danh, đổi, thu hồi, chuyển IdP và khôi phục danh tính, sau đó phiên cũ còn hiệu lực không?”.

## 10. Mô hình đe dọa: những kiểu tấn công qua ranh giới

| Đe dọa | Điểm tấn công | Hậu quả | Kiểm soát cần thiết |
| --- | --- | --- | --- |
| **Phishing tại IdP giả** | Người dùng ↔ trang đăng nhập | Lộ mật khẩu/OTP, chiếm credential | Cấu hình IdP đúng, phương thức chống phishing như WebAuthn, giám sát và bảo vệ recovery. |
| **Login CSRF / session swapping** | Trình duyệt ↔ callback | Nạn nhân bị đăng nhập vào account khác | `state` liên kết giao dịch/phiên, nonce và kiểm tra đúng identity. |
| **Authorization code replay** | Redirect/code exchange | Dùng lại hoặc đánh cắp code | Code một lần, thời hạn ngắn, PKCE, token endpoint và client binding phù hợp. |
| **Issuer mix-up** | RP nhiều IdP ↔ callback | Dùng code/token với sai authority | Ghim issuer theo giao dịch, kiểm tra issuer response khi áp dụng, endpoint cố định theo cấu hình. |
| **ID token substitution** | Token từ client/OP khác | Nhận sai tài khoản hoặc ứng dụng | Chữ ký, `iss`, `aud`, `azp` khi cần, `nonce`, thời hạn và mapping. |
| **Thuật toán/khóa ký không được phép** | Parser token/JWKS | Chấp nhận token giả mạo | Danh sách thuật toán được phép, kiểm tra khóa đúng issuer, quy trình rotation an toàn. |
| **Open redirect / redirect URI quá rộng** | Authorization response | Rò rỉ code/token, chuyển người dùng sang website giả | Redirect URI khớp chính xác, không redirect tùy ý sau callback, allowlist return URL. |
| **SSRF qua discovery/JWKS động** | IdP onboarding/configuration | Truy cập endpoint nội bộ, nhận khóa từ nguồn lạ | Chỉ sử dụng issuer/metadata đã phê duyệt, chặn URL tùy ý, xác minh TLS và nguồn khóa. |
| **Account takeover qua email matching** | External claims → local account | Liên kết sai tài khoản | Mapping `(issuer, sub)`, xác thực lại khi linking, không tự hợp nhất bằng email. |
| **Privilege escalation qua role claim** | IdP groups → app authorization | Được cấp quyền cao trái phép | Mapping theo tenant/issuer đã duyệt, kiểm tra quyền server-side, least privilege. |
| **Assurance downgrade** | IdP step-up ↔ RP | Thao tác nhạy cảm dùng phương thức yếu | Kiểm tra `acr`/`amr`/`auth_time` theo hợp đồng và policy thực tế. |
| **Session hijacking** | Trình duyệt ↔ LearnHub | Bỏ qua lần đăng nhập ban đầu | Cookie an toàn, chống XSS/CSRF, TTL, thu hồi phiên, step-up hành động nhạy cảm. |
| **Logout/deprovisioning gap** | IdP ↔ RP session lifecycle | User đã mất quyền vẫn có phiên hoạt động | Đồng bộ vòng đời, xác minh logout notification, revalidation và TTL phù hợp. |
| **Recovery yếu** | Help desk/IdP recovery → app | Vượt qua MFA/passkey và liên kết lại tài khoản | Bằng chứng recovery tương xứng, cảnh báo và kiểm soát thêm/xóa credential. |

Một **trust boundary có thể thất bại ngay cả khi HTTPS còn nguyên vẹn**: ví dụ RP kiểm tra chữ ký token từ một OP bất kỳ, dùng email thay `sub`, hoặc bỏ qua `aud`. TLS bảo vệ kênh vận chuyển giữa các điểm kết nối; nó không thay thế việc quyết định **nguồn nào được tin cho mục đích nào**.

## 11. Quan sát, kiểm thử và ứng phó sự cố

### 11.1. Những sự kiện nên quan sát

Các sự kiện có ích gồm: bắt đầu đăng nhập federated; callback thành công/thất bại theo mã nguyên nhân; issuer mismatch; sai state/nonce; token signature hoặc audience invalid; tài khoản chưa linked; yêu cầu và kết quả step-up; thêm/xóa IdP link; deprovisioning; logout và session revocation. Nên log timestamp, correlation ID, issuer ID đã chuẩn hóa, account ID nội bộ nếu xác định được, loại sự kiện và kết quả. Tránh ghi credential, authorization code, ID/access/refresh token hoặc dữ liệu cá nhân vượt nhu cầu.

Theo dõi đột biến sai `state`, sai issuer, tăng tỷ lệ đăng nhập thất bại tại một IdP, thay đổi JWKS bất thường, nhiều yêu cầu liên kết tài khoản và tỷ lệ recovery tăng. Hệ thống cảnh báo cần tránh gây false positive khi IdP outage hoặc khi người dùng đổi thiết bị hàng loạt.

### 11.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Callback thiếu hoặc sai `state` | RP từ chối, không cấp phiên. |
| Authorization code đã dùng hoặc hết hạn | Code exchange không thành công; không tạo session. |
| Callback được gắn với IdP A nhưng token trả từ IdP B | RP từ chối do issuer/mapping không đúng. |
| ID token hợp lệ về chữ ký nhưng `aud` của client khác | RP từ chối. |
| ID token có `iss` không khớp IdP đã chọn | RP từ chối. |
| ID token có `exp` quá hạn hoặc sai `nonce` | RP từ chối. |
| ID token dùng thuật toán hoặc khóa từ nguồn chưa được phép | RP từ chối. |
| Hai IdP khác nhau cùng trả `sub=123` | Ánh xạ thành hai danh tính khác nhau nếu chưa liên kết hợp lệ. |
| Email từ IdP mới trùng tài khoản có sẵn | Không tự sáp nhập; yêu cầu liên kết an toàn. |
| Claim `role=admin` từ OP không được cấp quyền role | Không tạo quyền admin LearnHub. |
| Step-up yêu cầu MFA chống phishing nhưng OP trả mức thấp | API nhạy cảm từ chối hoặc yêu cầu phương thức phù hợp. |
| Người dùng đổi email ở IdP nhưng `sub` giữ nguyên | Mapping tài khoản không tự đổi sang người khác. |
| IdP disable user nhưng RP còn session | Ứng dụng xử lý theo chính sách session/deprovisioning đã kiểm thử, không giả định logout tức thì. |
| RP logout thành công | Phiên RP vô hiệu; phạm vi logout với IdP được phản ánh đúng. |
| Request tới admin API với session học viên hợp lệ | Bị từ chối vì authorization, dù authentication thành công. |
| Client tự gửi `userId` hoặc `authenticated=true` | Backend bỏ qua và dựa vào dữ liệu phiên/token đã xác minh. |
| JWKS/discovery URL do client chỉ định đến host nội bộ | RP không fetch nguồn không được cho phép. |
| Hai request cùng tiêu thụ một giao dịch đăng nhập | Tối đa một giao dịch được hoàn tất; replay bị từ chối. |

Khi kiểm thử, dùng môi trường và tài khoản đã được cấp phép. Cố tình mô phỏng token giả hoặc issuer sai bằng fixture/test provider; không gửi credential thật vào log hay công cụ thử nghiệm công khai.

## 12. Bài thực hành tổng hợp: tích hợp CampusID vào LearnHub

**Yêu cầu giả định:** LearnHub chấp nhận đăng nhập từ hai nhà cung cấp: CampusID cho giảng viên/học viên và PartnerID cho đối tác. Chỉ giảng viên có vai trò được xác nhận theo chính sách mới được sửa điểm. Quản trị viên muốn cấp quyền cho người khác phải step-up bằng phương thức chống phishing phù hợp. LearnHub duy trì session riêng và dữ liệu phân quyền nội bộ.

### 12.1. Sản phẩm cần hoàn thành

1. **Sơ đồ kiến trúc:** xác định trình duyệt, LearnHub RP/API, hai OP, kho account mapping, session store và các trust boundary.
2. **Sequence diagram cho login:** ghi nơi tạo/kiểm tra `state`, `nonce`, PKCE, nơi trao đổi code, nơi xác minh ID token và lúc tạo session.
3. **Bảng mapping:** `(issuer, sub) → localAccountId`, chính sách email, tạo mới và liên kết tài khoản có chủ đích.
4. **Chính sách quyền và assurance:** ai được sửa điểm, khi nào yêu cầu step-up, claim nào phải kiểm tra, điều gì xảy ra khi OP không trả `acr` mong muốn.
5. **Vòng đời:** logout LearnHub, logout OP, disable tại OP, link/unlink IdP, recovery và thu hồi session.
6. **Threat model và test cases:** tối thiểu tám tình huống, có kết quả hệ thống kiểm chứng được.

### 12.2. Mẫu bảng kiểm tra theo ranh giới

| Boundary | Dữ liệu qua biên | Điều kiện tin cậy | Nếu không đạt |
| --- | --- | --- | --- |
| Trình duyệt → LearnHub login start | Lựa chọn IdP/tenant | Lựa chọn thuộc danh sách được phép và gắn với tenant | Không redirect tới issuer tùy ý. |
| Trình duyệt → callback | `code`, `state` | Giao dịch chờ hợp lệ, đúng OP, chống CSRF/replay | Không đổi code, không tạo phiên. |
| LearnHub → token endpoint | Authorization code + PKCE | Endpoint thuộc issuer đã ghim, TLS và client auth đúng profile | Không chấp nhận phản hồi không đáng tin. |
| OP → LearnHub | ID token | Chữ ký, issuer, audience, expiry, nonce và policy | Từ chối đăng nhập/step-up. |
| Claims → account mapping | `iss`, `sub`, email, groups | Mapping đã cấp quyền, claim semantics đã duyệt | Không tự ghép email/cấp role. |
| LearnHub → API tài nguyên | Session/token app | Phiên hợp lệ, quyền và assurance đủ cho hành động | HTTP 401/403 hoặc step-up theo contract. |
| IdP → LearnHub lifecycle | Logout/deprovisioning events | Nguồn/phương thức được xác minh và mapping chính xác | Không thu hồi tùy tiện hoặc bỏ qua cảnh báo quan trọng. |

### 12.3. Câu hỏi tự kiểm tra

1. Vì sao ứng dụng không nên dùng access token bất kỳ làm bằng chứng đăng nhập?
2. Đâu là khác biệt giữa **tin một IdP** và **tin tất cả claim do IdP cung cấp**?
3. Vì sao `(issuer, sub)` an toàn hơn email làm khóa liên kết?
4. `state`, `nonce` và PKCE bảo vệ những phần khác nhau nào của luồng?
5. Một ID token có chữ ký đúng nhưng audience sai phải được xử lý ra sao?
6. Khi một hệ thống hỗ trợ nhiều IdP, làm thế nào ngăn **mix-up**?
7. Nếu giảng viên đã có phiên nhưng chưa MFA, yêu cầu sửa điểm có được thực thi không?
8. Logout khỏi IdP có tự động vô hiệu session của RP không? Điều kiện nào khiến nó có thể xảy ra?
9. Vì sao cập nhật JWKS hoặc issuer từ dữ liệu client tùy ý có thể tạo rủi ro?
10. Trong trường hợp mất passkey và phải recovery, đâu là trách nhiệm của OP và đâu là trách nhiệm của RP?

**Tiêu chí hoàn thành:** Người học chỉ ra được ở từng điểm vượt qua trust boundary **ai phát hành dữ liệu, ai được phép tin, phép kiểm tra bắt buộc, tài khoản/quyền nào được ánh xạ và hành động nào phải bị từ chối khi thiếu bằng chứng**. Có thể kiểm thử được mọi điều kiện quan trọng ở backend là dấu hiệu một thiết kế đang đi đúng hướng.

## 13. Tài liệu đọc thêm

- **OpenID Connect Core 1.0**: ID token, `iss`, `sub`, `aud`, `nonce`, `auth_time`, `acr`, `amr` và quy trình xác minh.
- **OAuth 2.0 Security Best Current Practice** và các chuẩn liên quan: bảo vệ authorization request/response, redirect URI, PKCE, issuer mix-up và token.
- **OpenID Connect Discovery, Session/Logout specifications**: metadata, JWKS và các cách phối hợp vòng đời phiên khi OP hỗ trợ.
- **OWASP Authentication Cheat Sheet, Session Management Cheat Sheet, OAuth2 Cheat Sheet và ASVS**: chuyển trust boundary thành yêu cầu triển khai và kiểm thử.
- **NIST SP 800-63**: đánh giá bảo đảm xác thực, liên kết danh tính và yêu cầu khi phụ thuộc hệ thống nhận dạng bên ngoài.
- **W3C WebAuthn/FIDO2**: hiểu kỹ bảo đảm của các phương thức chống phishing được IdP sử dụng.

Khi áp dụng vào sản phẩm thật, hãy đối chiếu **phiên bản chuẩn hiện hành**, cấu hình và cam kết của từng IdP, mô hình client và mức nhạy cảm của tài nguyên. **Ranh giới tin cậy chỉ được bảo vệ khi kiểm tra được triển khai đúng ở nơi dữ liệu được chấp nhận và nơi quyền truy cập được thực thi.**
