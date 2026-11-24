# Relying party — Bên tiếp nhận và tin cậy kết quả xác thực liên kết

> **Chương:** Federation  
> **Chủ đề:** Relying party (RP)  
> **Phạm vi:** Security Authentication Fundamentals — vai trò của ứng dụng tiếp nhận danh tính từ Identity Provider (IdP), thiết lập quan hệ tin cậy, kiểm chứng assertion/token, liên kết tài khoản, quản lý phiên và phân quyền an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Relying Party (RP)** là gì và phân biệt RP với Identity Provider, OAuth client và resource server.
2. Mô tả quan hệ tin cậy giữa RP và IdP trong OpenID Connect (OIDC) và Security Assertion Markup Language (SAML).
3. Thiết kế cấu hình federation gồm issuer/entity ID, redirect URI/ACS URL, audience, khóa ký, metadata và chính sách xác thực.
4. Kiểm chứng ID token hoặc SAML response/assertion đúng giao thức, đúng RP, đúng giao dịch, còn hạn và chưa bị replay.
5. Liên kết danh tính federated với tài khoản nội bộ mà không dựa duy nhất vào email hoặc claim do người dùng tự khai.
6. Xử lý provisioning, session, logout, key rotation, thu hồi và các tình huống IdP bị xâm phạm.
7. Xây dựng kiểm thử cho token/assertion sai issuer, audience, chữ ký, thời hạn, recipient, state, nonce và replay.

## 1. Relying party là gì?

**Relying Party (RP)** là ứng dụng hoặc dịch vụ dựa vào một bên thứ ba đáng tin cậy để xác thực người dùng hoặc cung cấp thông tin danh tính. Thay vì tự kiểm tra mật khẩu của người dùng, RP chuyển người dùng tới **Identity Provider (IdP)** hoặc chấp nhận kết quả xác thực được IdP phát hành. RP phải kiểm chứng kết quả đó trước khi tạo phiên đăng nhập hoặc liên kết với tài khoản nội bộ.

Ví dụ: Nhân viên đăng nhập cổng quản lý bằng tài khoản doanh nghiệp. IdP của công ty xác thực nhân viên bằng passkey/MFA rồi gửi kết quả về ứng dụng. Ứng dụng là RP: nó tin IdP trong phạm vi đã cấu hình, kiểm tra kết quả và quyết định có tạo phiên cho tài khoản nào.

Trong SAML, vai trò tương ứng thường được gọi là **Service Provider (SP)**. Trong OIDC, ứng dụng đăng ký với OpenID Provider (OP) và được gọi là **Relying Party**. Hai giao thức có thuật ngữ và định dạng thông điệp khác nhau, nhưng cùng có bài toán: ứng dụng tiếp nhận kết quả từ một miền tin cậy khác và phải xác minh chính xác kết quả ấy.

### RP không phải là IdP

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| **User / Subject** | Người hoặc chủ thể cần đăng nhập | Nhân viên Lan |
| **Identity Provider (IdP)** | Xác thực chủ thể và phát hành kết quả liên kết | IdP doanh nghiệp |
| **Relying Party (RP)** | Tiếp nhận, kiểm chứng kết quả và tạo ngữ cảnh ứng dụng | Cổng nhân sự |
| **OAuth Client** | Ứng dụng yêu cầu access token để truy cập resource | Backend của cổng nhân sự |
| **Resource Server** | API bảo vệ tài nguyên và kiểm tra access token | HR API |
| **Federation authority / trust administrator** | Quản lý quan hệ tin cậy, metadata, khóa và chính sách | Đội IAM doanh nghiệp |

Một ứng dụng có thể đồng thời là OIDC RP, OAuth client và giao diện gọi resource server. Tuy vậy, mỗi vai trò có quyết định riêng: RP kiểm chứng sự kiện đăng nhập; OAuth client nhận token theo grant; resource server xác minh access token và quyền trên API.

### Luồng tổng quát

`````````mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as Relying Party
    participant IdP as Identity Provider
    participant API as Resource API
    U->>RP: Chọn đăng nhập bằng tài khoản doanh nghiệp
    RP->>RP: Tạo transaction, state/nonce và lưu ngữ cảnh
    RP-->>U: Chuyển tới IdP
    U->>IdP: Xác thực bằng credential/MFA
    IdP-->>U: Trả authorization response/assertion
    U->>RP: Callback về redirect URI/ACS
    RP->>RP: Kiểm chứng giao thức, issuer, recipient/audience, thời hạn, replay
    RP->>RP: Ánh xạ subject tới tài khoản và kiểm tra trạng thái
    RP-->>U: Tạo session nếu policy đạt
    U->>API: Gọi API bằng access token/session
    API->>API: Xác minh token và authorization
`````````

RP không được coi việc browser quay về từ IdP là bằng chứng đăng nhập thành công. Kết quả chỉ đáng tin sau khi được kiểm chứng đầy đủ theo giao thức và transaction đã khởi tạo.

## 2. Quan hệ tin cậy giữa RP và IdP

Federation tạo ra một **trust relationship**: RP chấp nhận một số kết quả do IdP cụ thể phát hành, với điều kiện nội dung, chữ ký, người nhận, mục đích và thời hạn đáp ứng policy.

Quan hệ tin cậy cần xác định:

- **Issuer / entity ID:** định danh chính xác của IdP;
- **RP/client identifier:** định danh ứng dụng tại IdP;
- **Callback endpoints:** redirect URI của OIDC hoặc Assertion Consumer Service (ACS) URL của SAML;
- **Signing keys/certificates:** khóa công khai được RP dùng để xác minh thông điệp;
- **Protocol/profile:** OIDC, SAML 2.0 và các binding/flow được cho phép;
- **Claims/attributes:** những thuộc tính nào được nhận và cách ánh xạ;
- **Authentication policy:** yêu cầu MFA, freshness, assurance và cách diễn giải claim;
- **Lifecycle:** ai có thể thêm IdP, rotate key, disable federation và xử lý sự cố.

**Tin cậy IdP không có nghĩa tin mọi dữ liệu mà browser gửi.** RP phải xác minh thông điệp đến từ issuer đã cấu hình, được gửi cho RP, thuộc đúng giao dịch và không bị sửa hoặc dùng lại.

### Ranh giới tin cậy

`````````mermaid
flowchart LR
    subgraph IDP["Miền IdP"]
        AUTH["Credential / MFA verifier"]
        ASSERT["Assertion hoặc ID token issuer"]
        AUTH --> ASSERT
    end
    subgraph RP["Miền Relying Party"]
        CALLBACK["OIDC callback / SAML ACS"]
        VERIFY["Protocol verifier"]
        MAP["Identity mapping"]
        SESSION["Local session issuer"]
        CALLBACK --> VERIFY --> MAP --> SESSION
    end
    ASSERT -->|"Token/assertion qua front channel hoặc back channel"| CALLBACK
`````````

RP cần bảo vệ callback như một điểm vào có dữ liệu không tin cậy. Dù thông điệp được cho là do IdP phát hành, nó vẫn phải qua parser, giới hạn kích thước, xác minh chữ ký và kiểm tra ngữ nghĩa trước khi dùng.

## 3. Thiết lập federation trước khi nhận đăng nhập

Một RP an toàn cần thiết lập quan hệ tin cậy có kiểm soát trước khi cho phép người dùng đăng nhập bằng IdP.

### Thông tin cấu hình

| Thuộc tính | OIDC | SAML 2.0 |
| --- | --- | --- |
| Định danh IdP | Issuer URL | IdP entity ID |
| Định danh RP | Client ID | SP entity ID |
| Callback | Redirect URI | ACS URL |
| Khóa xác minh | JWKS/public signing keys | X.509 signing certificate/public key |
| Kết quả xác thực | ID token và/hoặc authorization response | SAML Response chứa Assertion |
| Audience | Client ID trong ID token; resource identifier trong access token tùy profile | SP entity ID trong AudienceRestriction |
| Metadata | Discovery document, JWKS và client registration | SAML metadata mô tả entity, endpoints và key descriptors |

Các định danh phải được cấu hình từ nguồn đáng tin cậy. Không lấy issuer, JWKS URL, ACS URL hoặc chứng chỉ tùy ý từ callback của người dùng rồi tự động tin.

### Registration và metadata

Trong OIDC, RP đăng ký client với OP, cấu hình redirect URI và lấy discovery metadata/JWKS từ issuer được tin cậy. Trong SAML, SP và IdP trao đổi metadata về entity ID, SSO endpoint, ACS, binding và chứng chỉ.

Metadata có thể được lấy tự động, nhưng **tự động tải không đồng nghĩa tự động tin**. Quy trình cần xác minh nguồn, TLS, chữ ký metadata nếu được dùng, phạm vi tenant và quy trình phê duyệt thay đổi.

### Exact matching

- Redirect URI phải khớp URI đã đăng ký theo quy tắc của giao thức; tránh wildcard rộng hoặc redirect dựa trên chuỗi con.
- SAML ACS URL và Destination/Recipient phải khớp endpoint được cấu hình.
- SAML AudienceRestriction phải bao gồm SP entity ID đúng.
- OIDC issuer phải khớp chính xác issuer được cấu hình.
- Client ID và RP ID không được nhầm với audience của API.

Một cấu hình federation có thể hợp lệ về cú pháp nhưng vẫn sai về trust nếu endpoint hoặc khóa thuộc tenant khác.

## 4. RP trong OpenID Connect

OIDC thêm lớp xác thực người dùng trên OAuth 2.0. RP thường khởi tạo **Authorization Code Flow**, nhận authorization code tại redirect URI, đổi code ở token endpoint rồi kiểm chứng ID token.

### Luồng Authorization Code + PKCE

1. RP tạo giá trị **state** ngẫu nhiên và lưu cùng browser/session transaction.
2. RP tạo **nonce** nếu flow/profile yêu cầu, gắn với transaction.
3. RP tạo PKCE code verifier ngẫu nhiên và code challenge.
4. RP chuyển browser tới authorization endpoint của issuer đã cấu hình với client ID, redirect URI, response type, scope và PKCE challenge.
5. Người dùng xác thực tại IdP.
6. IdP trả authorization code và state về redirect URI.
7. RP so khớp state với transaction đã lưu; từ chối callback không gắn với giao dịch.
8. RP gửi code cùng code verifier tới token endpoint qua kênh phù hợp.
9. RP kiểm chứng ID token và các response liên quan trước khi tạo session.

### Các kiểm tra ID token

- **Chữ ký:** dùng thuật toán được phép và khóa lấy từ JWKS của issuer tin cậy; không chấp nhận thuật toán do token tự chọn ngoài allowlist.
- **Issuer:** claim iss khớp chính xác issuer đã cấu hình.
- **Audience:** aud chứa client ID của RP; áp dụng quy tắc azp khi cần theo OIDC.
- **Thời gian:** exp còn hiệu lực; kiểm tra iat/nbf nếu profile và policy yêu cầu, có clock skew giới hạn.
- **Nonce:** nếu RP gửi nonce, claim nonce trong ID token phải khớp transaction.
- **Transaction:** code, state và callback thuộc đúng browser/session transaction; code không được dùng lại.
- **Token profile:** kiểm tra claim bắt buộc và kiểu dữ liệu theo OIDC/profile được triển khai.
- **Key lifecycle:** xử lý kid, JWKS refresh và key rotation an toàn; không tải khóa từ URL tùy ý do token cung cấp.

### Pseudocode OIDC

`````````
handleOidcCallback(response, browserSession):
    txn = loadPendingTransaction(browserSession, response.state)
    require(txn is not null and not txn.expired and not txn.consumed)
    require(response.issuerContext == txn.expectedIssuerContext)

    tokenResponse = exchangeCodeAtConfiguredTokenEndpoint(
        response.code,
        txn.pkceVerifier,
        txn.redirectUri
    )

    idToken = verifyJwtWithTrustedIssuerKeys(tokenResponse.id_token)
    require(idToken.iss == txn.expectedIssuer)
    require(rpClientId in normalizeAudience(idToken.aud))
    require(validAuthorizedPartyIfRequired(idToken))
    require(not expired(idToken.exp))
    require(nonceMatchesIfSent(idToken.nonce, txn.nonce))

    consumeTransactionAtomically(txn)
    identity = mapFederatedSubject(idToken.iss, idToken.sub)
    return completeLoginOnlyIfAccountActive(identity)
`````````

Đây là pseudocode khái niệm. RP cần dùng thư viện OIDC đã được kiểm chứng, tuân thủ đầy đủ các quy tắc của flow và profile đang dùng. Không tự triển khai parser/token verifier để thay thư viện giao thức.

### ID token và access token

ID token được phát hành để RP biết kết quả xác thực. Access token được dùng để gọi resource server. Nếu RP gửi ID token tới API hoặc API chấp nhận ID token thay access token, hệ thống có thể mắc lỗi token substitution/cross-JWT confusion.

RP phải lưu session ứng dụng theo policy riêng. Không cần đưa toàn bộ ID token hoặc access token vào browser storage chỉ để giữ trạng thái đăng nhập.

## 5. RP trong SAML 2.0

Trong SAML, RP thường đóng vai trò **Service Provider (SP)**. SP gửi AuthnRequest tới IdP, người dùng xác thực và IdP trả SAML Response tới ACS endpoint.

### Luồng SP-initiated

1. Người dùng mở ứng dụng SP và yêu cầu đăng nhập.
2. SP tạo request ID, lưu transaction, relay state ngẫu nhiên và thời hạn.
3. SP gửi AuthnRequest tới SSO endpoint của IdP qua binding được cấu hình.
4. IdP xác thực người dùng và tạo SAML Response/Assertion.
5. Browser chuyển response tới ACS URL của SP.
6. SP kiểm chứng chữ ký, issuer, destination, recipient, audience, thời hạn, InResponseTo và trạng thái replay.
7. SP ánh xạ NameID/attributes sang tài khoản nội bộ.
8. SP tạo session nếu tài khoản và policy cho phép.

### Checklist kiểm chứng SAML Response

1. **Parser:** chỉ chấp nhận định dạng và binding được cấu hình; giới hạn kích thước, chống XML entity expansion/XXE và xử lý an toàn XML.
2. **Signature:** xác minh chữ ký bằng chứng chỉ/khóa của IdP đã được tin cậy; xác định rõ Response, Assertion hoặc cả hai phải được ký theo policy.
3. **Signed element:** bảo đảm ứng dụng sử dụng đúng Assertion/Response đã được xác minh chữ ký; chống XML Signature Wrapping và không lấy một node khác chưa ký để tạo principal.
4. **Issuer:** issuer của Response/Assertion khớp IdP đã cấu hình.
5. **Destination:** Destination của Response khớp ACS endpoint dự kiến.
6. **Recipient:** SubjectConfirmationData Recipient khớp ACS URL.
7. **Audience:** AudienceRestriction bao gồm SP entity ID.
8. **InResponseTo:** với SP-initiated flow, ID phản hồi khớp request đang chờ và chưa tiêu thụ.
9. **Time conditions:** NotBefore/NotOnOrAfter và SubjectConfirmationData NotOnOrAfter được kiểm tra với clock skew giới hạn.
10. **Subject confirmation:** phương thức và điều kiện subject confirmation đáp ứng binding/profile được dùng.
11. **Replay:** Response ID và Assertion ID chưa từng được chấp nhận; lưu replay cache trong khoảng thời gian cần thiết.
12. **RelayState:** chỉ khôi phục trạng thái từ giá trị do SP tạo/lưu; không dùng RelayState như URL redirect tùy ý.

### SP-initiated và IdP-initiated

SP-initiated flow giúp SP gắn response với AuthnRequest đang chờ qua InResponseTo và transaction state. IdP-initiated (unsolicited response) có thể được hỗ trợ trong một số hệ thống, nhưng RP không có request vừa khởi tạo để đối chiếu.

Nếu cho phép IdP-initiated:

- Chỉ chấp nhận từ IdP đã đăng ký;
- Kiểm tra chữ ký, issuer, audience, destination, recipient, thời gian và replay đầy đủ;
- Có chính sách chống login CSRF/account confusion phù hợp;
- Không cho RelayState tùy ý chuyển người dùng tới URL ngoài allowlist;
- Đánh giá kỹ việc chọn account và liên kết danh tính;
- Ưu tiên SP-initiated khi nghiệp vụ và đối tác hỗ trợ.

### Pseudocode SAML

`````````
handleSamlAcs(encodedResponse, relayState):
    xml = parseWithSecureXmlSettings(encodedResponse)
    response = validateTrustedSignatureAndSignedNode(xml, configuredIdpKeys)
    require(response.issuer == configuredIdpEntityId)
    require(response.destination == configuredAcsUrl)
    assertion = selectVerifiedAssertion(response)
    require(configuredSpEntityId in assertion.audienceRestrictions)
    require(assertion.recipient == configuredAcsUrl)
    require(assertion.timeConditionsValid(clockSkewPolicy))
    require(not replayCache.contains(response.id, assertion.id))
    require(inResponseToMatchesPendingRequestIfSpInitiated(response))
    require(relayStateMapsToStoredTransaction(relayState))

    atomicallyRecordReplayIds(response.id, assertion.id)
    identity = mapFederatedSubject(assertion.issuer, assertion.nameId)
    return completeLoginOnlyIfAccountActive(identity)
`````````

Đây là mô hình kiểm tra, không thay thế thư viện SAML đã được kiểm chứng. Cần cấu hình chính xác yêu cầu ký Response/Assertion, binding và profile; không giả định mọi IdP luôn ký cùng một phần tử.

## 6. Liên kết danh tính federated với tài khoản nội bộ

Sau khi xác minh thông điệp, RP cần ánh xạ danh tính bên ngoài thành tài khoản nội bộ. Đây là bước nhạy cảm vì lỗi mapping có thể dẫn tới **account takeover**.

### Khóa định danh nên dùng

Với OIDC, cặp **(issuer, subject)** là định danh federated ổn định trong phạm vi issuer. Với SAML, có thể dùng kết hợp IdP entity ID và NameID theo format/semantics đã thỏa thuận. Không nên dùng email đơn lẻ làm khóa định danh chính.

Lý do:

- Email có thể đổi hoặc được tái cấp cho người khác;
- Hai IdP có thể phát cùng một email cho hai chủ thể khác nhau;
- Email có thể chưa được xác minh hoặc claim email_verified không được RP diễn giải đúng;
- Quy tắc viết hoa/thường, alias và domain có thể khác nhau;
- Một tài khoản có thể có nhiều email hoặc nhiều IdP liên kết.

### Mô hình dữ liệu

`````````yaml
federated_identity:
  provider_id: corporate-oidc
  issuer: https://identity.example.com
  subject: subject-8d31
  local_account_id: account-1042
  linked_at: "2026-11-22T06:00:00Z"
  status: active
`````````

Đây là ví dụ metadata. RP nên có unique constraint cho định danh federated trong phạm vi provider/issuer và audit mọi lần link, unlink hoặc thay đổi mapping.

### Account linking an toàn

1. Người dùng đã đăng nhập vào tài khoản nội bộ hiện tại bằng phương thức đáng tin.
2. Người dùng chủ động yêu cầu liên kết IdP mới.
3. RP tạo transaction link riêng, có state/nonce và mục đích rõ ràng.
4. Người dùng xác thực tại IdP; RP kiểm chứng response theo giao thức.
5. RP kiểm tra subject chưa liên kết với tài khoản nội bộ khác.
6. RP yêu cầu step-up nếu thao tác có rủi ro cao.
7. RP lưu liên kết và thông báo qua kênh hiện có.

Không tự động gộp hai tài khoản chỉ vì email trùng nhau. Nếu subject đã liên kết với một local account khác, cần quy trình xử lý xung đột có xác minh và audit.

## 7. Claims và attributes: chỉ tin trong phạm vi đã thỏa thuận

IdP có thể gửi tên, email, nhóm, phòng ban, vai trò hoặc mức xác thực. RP phải xác định **claim nào được tin, nguồn nào được tin và dùng cho quyết định nào**.

| Claim/attribute | Có thể dùng cho | Cần thận trọng |
| --- | --- | --- |
| Subject/NameID | Liên kết danh tính federated | Phải gắn với issuer/provider |
| Email | Liên hệ hoặc hiển thị | Không tự động dùng làm khóa liên kết |
| Email verified | Một tín hiệu về xác minh email theo IdP | Phải tin issuer và hiểu semantics |
| Display name | Hiển thị | Không dùng làm authorization |
| Group/department | Mapping vai trò nếu có thỏa thuận | Claim có thể cũ, quá rộng hoặc không đồng nhất |
| Role | Có thể ánh xạ quyền nếu IdP là nguồn quyền được ủy quyền | Cần allowlist, tenant context và policy |
| Authentication time | Đánh giá freshness | Cần kiểm tra nguồn và đơn vị thời gian |
| ACR/AMR | Mức hoặc phương thức xác thực theo hợp đồng | Không tự suy ra assurance chỉ từ tên chuỗi |

Không nên lấy mọi group/role từ IdP rồi cấp quyền trực tiếp. RP cần mapping rõ giữa external group và quyền nội bộ, có giới hạn tenant, thời gian hiệu lực và quy trình thu hồi.

### ACR, AMR và freshness

OIDC có thể truyền claim như **acr** (Authentication Context Class Reference), **amr** (Authentication Methods References) và **auth_time**. RP chỉ nên dùng chúng khi có thỏa thuận với IdP về ngữ nghĩa, cách phát hành và mức đảm bảo.

Ví dụ, RP yêu cầu xác thực chống phishing gần đây trước khi thay đổi thông tin thanh toán. RP cần biết IdP hỗ trợ yêu cầu đó bằng cách nào, claim nào phản ánh kết quả và freshness được đo ra sao. Không được tự coi mọi giá trị amr chứa chữ mfa là cùng một mức bảo vệ.

## 8. Provisioning và deprovisioning

Federation login xác nhận người dùng tại thời điểm đăng nhập. Nó không tự đồng bộ đầy đủ vòng đời nhân sự hoặc trạng thái tài khoản nội bộ.

### Just-in-time provisioning

RP có thể tạo local account lần đầu người dùng đăng nhập thành công qua IdP. Trước khi tạo:

- Kiểm tra issuer/provider được phép tạo account;
- Kiểm tra subject duy nhất;
- Áp dụng domain/tenant hoặc invitation policy;
- Xác định attribute nào được phép ghi;
- Không cấp role đặc quyền chỉ dựa vào email hoặc display name;
- Ghi audit việc tạo tài khoản và nguồn provisioning.

### SCIM và provisioning ngoài luồng login

SCIM hoặc cơ chế provisioning khác có thể tạo, cập nhật, disable và xóa assignment tại RP trước khi người dùng đăng nhập. Khi dùng provisioning:

- Xác thực nguồn đồng bộ và phân quyền endpoint;
- Chống replay hoặc xử lý idempotent;
- Theo dõi version/sequence và lỗi đồng bộ;
- Phân biệt disable tại IdP với xóa local data theo retention;
- Không cho một event cũ kích hoạt lại account đã bị disable bởi quyết định mới hơn.

### Deprovisioning

Khi nhân viên rời tổ chức hoặc quyền truy cập bị thu hồi, RP cần áp dụng trạng thái disable, thu hồi session/token và gỡ quyền nội bộ theo SLA. Việc IdP vẫn xác thực thành công không buộc RP phải cho phép truy cập nếu local account đã bị disable.

## 9. Session tại RP sau khi federation thành công

RP tạo **local session** sau khi đã xác minh kết quả federated và kiểm tra account/policy. Session của RP có vòng đời riêng; không nhất thiết tồn tại cùng thời gian với phiên tại IdP.

Các kiểm soát:

- Tạo session ID mới sau authentication để chống session fixation;
- Cookie Secure, HttpOnly, SameSite phù hợp và phạm vi Domain/Path hẹp;
- Idle timeout và absolute timeout theo rủi ro;
- Reauthentication/step-up cho thao tác nhạy cảm;
- Thu hồi session khi logout, account disable, unlink identity hoặc phát hiện compromise;
- Không ghi token/assertion/cookie thô vào log;
- Kiểm tra CSRF cho endpoint thay đổi trạng thái.

### Logout có nhiều lớp

- **RP local logout:** kết thúc session tại ứng dụng;
- **IdP logout:** kết thúc session tại IdP nếu giao thức/hệ thống hỗ trợ;
- **Federated single logout:** phối hợp logout giữa RP và IdP hoặc các SP liên quan.

Không nên giả định local logout tự kết thúc phiên tại IdP. Tương tự, một thông điệp single logout bị giả mạo hoặc replay không được phép kết thúc session của tài khoản khác. Logout protocol cần xác minh issuer, signature, session reference và trạng thái tương ứng.

## 10. Quản lý khóa, metadata và thay đổi IdP

RP phụ thuộc vào khóa công khai của IdP để xác minh chữ ký. Nếu khóa bị thay đổi hoặc bị compromise, toàn bộ trust relationship có thể bị ảnh hưởng.

### Key rotation

1. IdP công bố khóa mới qua JWKS hoặc SAML metadata theo quy trình đã thỏa thuận.
2. RP tải metadata từ nguồn đã xác minh và kiểm tra tính toàn vẹn.
3. RP chấp nhận khóa mới trong cửa sổ overlap có kiểm soát.
4. IdP chuyển sang ký bằng khóa mới.
5. RP ngừng tin khóa cũ khi hết thời hạn hoặc khi có sự cố compromise.
6. Ghi audit thời điểm tải, kích hoạt, ngừng tin khóa và các lỗi xác minh.

Không tải JWKS hoặc chứng chỉ từ URL tùy ý trong token/assertion. Với JWT, kid chỉ giúp chọn khóa trong bộ khóa của issuer đã tin; nó không phải chỉ thị cho RP truy cập một URL bất kỳ.

### Khi IdP bị compromise

- Tạm ngừng hoặc hạn chế federation từ issuer bị ảnh hưởng;
- Chặn khóa ký bị compromise và xử lý token/assertion đã phát hành;
- Đánh giá local session được tạo từ kết quả của IdP trong khoảng thời gian rủi ro;
- Thu hồi session/token nội bộ theo mức ảnh hưởng;
- Thông báo và phối hợp với chủ sở hữu IdP;
- Chỉ mở lại trust sau khi xác minh khóa, metadata và chính sách mới;
- Ghi lại các quyết định và phạm vi thời gian bị ảnh hưởng.

RP cần có khả năng **disable một federation connection** mà không làm hỏng mọi phương thức đăng nhập khác của hệ thống.

## 11. Ranh giới tenant và nhiều IdP

Một RP có thể hỗ trợ nhiều tổ chức, mỗi tổ chức dùng một IdP riêng. Điều này tạo nguy cơ nhầm issuer hoặc liên kết nhầm account nếu tenant context không được ràng buộc.

### Các nguyên tắc

- Mỗi federation connection có provider ID, issuer/entity ID và endpoints riêng.
- Người dùng hoặc tenant context được xác định trước khi chọn IdP, theo cơ chế đã kiểm soát.
- Callback phải ánh xạ về đúng connection đã khởi tạo; không tin tham số provider do client tự đổi.
- Subject được định danh trong namespace của issuer; không dùng sub đơn lẻ trên toàn hệ thống.
- Group/role mapping được cấu hình theo tenant và không được chia sẻ ngoài phạm vi.
- Không cho issuer A tạo hoặc đăng nhập vào tenant B chỉ vì email domain giống nhau.

### Ví dụ

Hai công ty Alpha và Beta cùng có người dùng tên lan@example.com. IdP Alpha phát subject A-100, IdP Beta phát subject B-200. Dù email giống nhau, RP phải xem đây là hai danh tính federated khác nhau trừ khi có quy trình link được xác minh.

## 12. Threat model: RP có thể bị tấn công như thế nào?

| Rủi ro | Mô tả | Kiểm soát |
| --- | --- | --- |
| **Issuer confusion** | Token từ IdP khác được chấp nhận | Issuer exact match và trust connection rõ |
| **Audience confusion** | Token không dành cho RP/API được chấp nhận | Kiểm tra aud/entity ID đúng profile |
| **State/CSRF attack** | Attacker gắn callback vào browser transaction khác | State ngẫu nhiên, ràng buộc session và kiểm tra một lần |
| **Nonce replay/substitution** | ID token được đưa vào transaction khác | Nonce transaction-bound, expiry và replay checks |
| **SAML replay** | Response/assertion được gửi lại | Replay cache theo Response ID/Assertion ID |
| **XML Signature Wrapping** | Parser dùng assertion khác với phần tử đã ký | Secure XML parser và xác minh đúng signed node |
| **Open redirect** | RelayState/return URL đưa người dùng tới domain độc hại | Chỉ dùng state đã lưu hoặc allowlist URL |
| **Account linking takeover** | Email trùng khiến tài khoản bị tự động gộp | Link bằng issuer+subject, step-up và unique constraint |
| **Claim over-trust** | Group/role từ IdP cấp quyền quá rộng | Attribute mapping và authorization policy phía RP |
| **Weak recovery** | Recovery nội bộ yếu hơn federation login | Recovery assurance tương xứng, audit và notification |
| **Key compromise** | Khóa ký IdP bị lộ | Key rotation/revocation và incident procedure |
| **Session fixation/theft** | Session RP bị chiếm sau login | Regenerate ID, cookie flags, XSS/CSRF defense, revocation |
| **Tenant mix-up** | Callback của tenant này bị gắn sang tenant khác | Transaction-bound provider/tenant context |

### Fail closed khi không xác minh được

Nếu RP không thể xác minh chữ ký, không tải được khóa tin cậy, không xác định được issuer hoặc không đối chiếu được transaction, không nên tạo session dựa trên kết quả chưa rõ. Nếu hệ thống hỗ trợ phương thức đăng nhập khác, có thể cho người dùng chọn phương thức đó theo policy.

## 13. Tình huống thiết kế: cổng nhân sự dùng nhiều IdP

Một SaaS nhân sự phục vụ ba khách hàng. Mỗi khách hàng có IdP doanh nghiệp riêng; người dùng có thể đăng nhập bằng OIDC hoặc SAML. SaaS cần tạo local session, ánh xạ phòng ban và cấp quyền xem hồ sơ.

### Thiết kế ban đầu có vấn đề

1. Callback nhận tham số tenant từ query string và dùng nó để chọn IdP.
2. Ứng dụng decode ID token, lấy email rồi tìm local account.
3. Không kiểm tra nonce hoặc state với transaction lưu trong browser session.
4. SAML ACS kiểm tra chữ ký Response nhưng dùng Assertion đầu tiên trong XML mà không xác nhận đó là node được ký.
5. Ứng dụng lấy mọi group từ IdP và ánh xạ thẳng thành role quản trị.
6. Local session vẫn hoạt động sau khi account bị disable do provisioning.

### Thiết kế lại

1. Người dùng bắt đầu từ tenant context đã được RP xác minh; connection ID được lưu trong transaction server-side.
2. RP tạo state, nonce và PKCE cho OIDC; hoặc request ID và RelayState ngẫu nhiên cho SAML.
3. Callback chỉ được xử lý bằng connection đã gắn với transaction, không chọn issuer theo tham số tùy ý.
4. OIDC verifier kiểm tra signature, iss, aud, azp khi cần, exp, nonce và transaction.
5. SAML verifier kiểm tra signature trên đúng node, issuer, destination, recipient, audience, time conditions, InResponseTo và replay.
6. Identity mapping dùng (issuer, subject) hoặc provider namespace + NameID đã thỏa thuận.
7. Group/department được ánh xạ qua allowlist theo tenant; quyền nhạy cảm cần phê duyệt nội bộ.
8. Trước khi phát session, RP kiểm tra local account active và policy.
9. Provisioning disable thu hồi session/token theo SLA; dashboard ghi nhận propagation.

### Kết quả mong đợi

- Một IdP không thể đăng nhập vào tenant khác bằng email trùng;
- Token/assertion sai audience hoặc sai recipient bị từ chối;
- Callback không có state/nonce/request hợp lệ không tạo session;
- Assertion replay hoặc XML wrapping không tạo principal;
- Group claim không tự cấp quyền quản trị ngoài mapping;
- Account disabled không thể đăng nhập lại dù IdP vẫn xác thực thành công.

## 14. Bộ kiểm thử chấp nhận

| Trường hợp | Đầu vào/cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Issuer đúng** | ID token/assertion từ issuer đã cấu hình | Tiếp tục kiểm tra các điều kiện khác |
| **Issuer sai** | Token được ký bởi IdP khác | Từ chối |
| **Audience sai** | ID token không dành cho RP hoặc SAML audience không chứa SP entity ID | Từ chối |
| **Redirect/ACS sai** | Callback/recipient/destination không khớp | Từ chối |
| **Chữ ký sai** | Payload bị sửa hoặc dùng key không tin cậy | Từ chối |
| **JWT alg không cho phép** | Header yêu cầu thuật toán ngoài allowlist | Từ chối |
| **OIDC state sai** | Callback dùng state không gắn transaction | Từ chối |
| **OIDC nonce sai** | ID token nonce khác giá trị đã lưu | Từ chối |
| **OIDC code replay** | Dùng lại authorization code | Từ chối |
| **OIDC ID token nhầm API token** | Gửi ID token tới resource server | Resource server từ chối |
| **SAML InResponseTo sai** | Response gắn request ID khác | Từ chối trong SP-initiated flow |
| **SAML replay** | Gửi lại Response/Assertion ID đã tiêu thụ | Từ chối |
| **SAML signature wrapping** | Thêm assertion không ký và làm parser chọn nhầm node | Từ chối |
| **SAML time invalid** | Assertion ngoài NotBefore/NotOnOrAfter | Từ chối |
| **RelayState open redirect** | Gửi URL ngoài allowlist | Không chuyển hướng ra ngoài |
| **Email collision** | Hai issuer phát cùng email cho hai subject khác nhau | Không tự động gộp account |
| **Tenant mix-up** | Callback của tenant A dùng connection B | Từ chối |
| **Role injection** | Claim group/role không nằm trong mapping | Không cấp quyền tương ứng |
| **Account disabled** | IdP xác thực thành công nhưng local account disabled | Không tạo session |
| **IdP key rotation** | JWKS/metadata có key mới và key cũ trong overlap | Xác minh theo quy trình rotation |
| **IdP key compromise** | Đánh dấu khóa bị compromise | Ngừng tin khóa và xử lý session liên quan |
| **Provisioning delay** | Disable event đến chậm hoặc sai thứ tự | Reconcile phát hiện; account không được mở lại bởi event cũ |

Kiểm thử phải chạy tại RP callback/ACS và tại resource API sau khi session/token được tạo. Chỉ kiểm tra giao diện chuyển hướng thành công không chứng minh federation an toàn.

## 15. Audit và giám sát federation

RP cần ghi nhận những sự kiện giúp truy nguyên việc thiết lập trust, đăng nhập, liên kết và thay đổi trạng thái.

| Event | Trường gợi ý |
| --- | --- |
| federation.connection.created/updated | Provider ID, issuer/entity ID, tenant, actor, change ID |
| federation.metadata.refreshed | Source, version/hash, thời điểm, kết quả |
| federation.key.activated/revoked | Key ID/fingerprint, issuer, thời điểm, reason |
| federation.login.started | Transaction ID, provider ID, protocol, tenant |
| federation.response.rejected | Reason code: issuer, audience, signature, state, nonce, replay, time |
| federation.login.succeeded | Provider ID, subject reference, local account reference, assurance context |
| federation.identity.linked/unlinked | Issuer, subject reference, local account, actor, approval |
| federation.provisioning.changed | External subject, local account, status version, source |
| federation.session.revoked | Local session reference, reason, propagation time |
| federation.logout.received | Issuer, session reference, signature/validation result |

Không ghi ID token, SAML assertion, authorization code, RelayState secret, session cookie hoặc access token thô. Subject/email có thể là dữ liệu cá nhân; dùng reference/pseudonymized value và retention theo chính sách.

### Chỉ số vận hành

- **Federation success rate:** giao dịch thành công theo provider/protocol, có tách lỗi người dùng và lỗi verifier.
- **Invalid response rate:** tỷ lệ callback bị từ chối theo reason code.
- **State/nonce mismatch count:** phát hiện CSRF, callback sai transaction hoặc client bug.
- **Audience/recipient mismatch count:** token/assertion bị gửi sai RP.
- **Replay rejection count:** response/assertion/code đã dùng lại.
- **Key rotation convergence:** thời gian các node cập nhật khóa tin cậy.
- **Provisioning propagation latency:** thời gian từ disable tại nguồn tới chặn local session/API.
- **Account linking conflict rate:** số lần subject đã được liên kết hoặc email collision.
- **Post-disable session acceptance:** số request còn được chấp nhận sau thời điểm disable có hiệu lực.

Tỷ lệ callback thất bại cao không tự chứng minh tấn công; có thể do IdP outage, cấu hình redirect URI hoặc thay đổi chứng chỉ. Cần phân tích theo provider, phiên bản cấu hình và reason code.

## 16. Checklist triển khai RP

- **Trust setup:** Issuer/entity ID, client ID/SP entity ID, redirect URI/ACS, khóa và protocol profile có được xác minh/phê duyệt?
- **Transaction:** State, nonce, request ID, PKCE và RelayState có ngẫu nhiên, lưu server-side, ràng buộc transaction và dùng một lần?
- **OIDC:** Chữ ký, issuer, audience, azp khi cần, exp, nonce, state và code exchange được kiểm tra đầy đủ?
- **SAML:** Chữ ký đúng node, issuer, destination, recipient, audience, InResponseTo, time conditions và replay được kiểm tra?
- **Parser:** XML/JSON parser an toàn, giới hạn kích thước và không xử lý external entity tùy tiện?
- **Key lifecycle:** JWKS/metadata refresh, overlap, rotation, compromise và disable connection có quy trình?
- **Identity mapping:** Dùng issuer+subject hoặc provider namespace+NameID; không auto-link bằng email?
- **Claims:** Attribute/group/role có mapping allowlist, tenant context và policy nội bộ?
- **Provisioning:** JIT/SCIM có xác minh nguồn, idempotency, version và deprovisioning?
- **Session:** Regenerate session ID, cookie flags, timeout, step-up và revoke có đầy đủ?
- **Logout:** Local logout và federated logout có được phân biệt, xác minh và kiểm thử?
- **Tenant isolation:** Callback chỉ dùng federation connection đã gắn với transaction/tenant?
- **Recovery:** Recovery nội bộ không yếu hơn assurance mà RP yêu cầu?
- **Audit:** Có reason code và correlation ID mà không lưu token/assertion/secret thô?
- **Testing:** Đã kiểm tra issuer/audience/recipient sai, replay, state/nonce, signature wrapping, account collision và disable?

### Câu hỏi tự kiểm tra

1. Relying Party khác Identity Provider ở trách nhiệm nào?
2. Vì sao một browser callback từ IdP chưa đủ để tạo session?
3. OIDC state và nonce bảo vệ các mối đe dọa nào? PKCE bổ sung lớp bảo vệ gì?
4. Trong SAML, vì sao phải xác minh đúng Assertion node đã ký chứ không chỉ thấy XML có một chữ ký hợp lệ?
5. Vì sao cặp issuer+subject đáng tin hơn email để liên kết tài khoản?
6. Audience của ID token khác audience của access token như thế nào?
7. Nếu IdP xác thực thành công nhưng local account đã disabled, RP phải làm gì?
8. Tại sao provisioning/deprovisioning cần cơ chế riêng ngoài login federation?

## Kết luận

**Relying Party là nơi tiếp nhận và kiểm chứng kết quả xác thực từ một miền danh tính khác trước khi tạo phiên hoặc liên kết tài khoản.** RP chỉ nên tin issuer/IdP đã cấu hình và phải xác minh đúng giao thức, chữ ký, audience/recipient, thời hạn, transaction, state/nonce, replay và token profile. Sau đó, RP ánh xạ danh tính bằng định danh federated ổn định, kiểm tra local account, tenant, claims và quyền theo policy. Federation không chuyển giao toàn bộ trách nhiệm bảo mật cho IdP: RP vẫn phải quản lý session, recovery, provisioning, logout, key rotation và authorization. Một quan hệ federation an toàn cần trust configuration có kiểm soát, kiểm chứng nghiêm ngặt ở callback/ACS và khả năng thu hồi khi IdP hoặc tài khoản bị xâm phạm.
