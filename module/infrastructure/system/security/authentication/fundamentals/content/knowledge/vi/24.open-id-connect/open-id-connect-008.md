# OIDC validation — Xác minh token và kết quả xác thực OpenID Connect

> **Chương:** OpenID Connect  
> **Chủ đề:** OIDC validation

**OIDC validation** là tập hợp kiểm tra mà một ứng dụng thực hiện trước khi tin kết quả xác thực do OpenID Provider (OP) phát hành. Ứng dụng không thể chỉ giải mã JWT rồi đọc claim; nó phải xác minh chữ ký theo khóa tin cậy, issuer, audience, thời hạn, nonce và các ràng buộc của giao dịch đăng nhập. Sau đó, ứng dụng mới ánh xạ subject vào tài khoản nội bộ, tạo session và áp dụng authorization.

OpenID Connect (OIDC) bổ sung lớp authentication trên OAuth 2.0. **ID token** mang thông tin về sự kiện xác thực và dành cho client/Relying Party (RP); **access token** dành cho resource server để truy cập API; **refresh token** dùng để xin token mới. Ba loại token có mục đích và quy tắc xác minh khác nhau. Nhầm lẫn chúng là một trong những nguyên nhân phổ biến dẫn tới chấp nhận sai token hoặc cấp session cho nhầm danh tính.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối credential, MFA, passkey, token, session, liên kết danh tính và khôi phục tài khoản. Trọng tâm là xác minh OIDC theo đúng issuer và client đã cấu hình, bảo vệ callback, chống token substitution/replay, xử lý JWKS/key rotation và giữ ranh giới giữa authentication với authorization.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt ID token, access token và refresh token, xác định thành phần nào có trách nhiệm xác minh từng loại.
2. Xác minh chữ ký JWT bằng khóa công khai lấy từ JWKS của issuer đã tin cậy.
3. Kiểm tra issuer, audience, authorized party, subject, thời hạn và nonce của ID token.
4. Xác minh access token theo loại token và hợp đồng resource server, không dùng ID token thay thế.
5. Xử lý an toàn discovery metadata, JWKS cache, unknown key ID và signing-key rotation.
6. Ràng buộc callback với đúng authorization transaction bằng state, nonce và PKCE.
7. Kiểm tra UserInfo response và liên kết subject với ID token.
8. Nhận diện token substitution, issuer mix-up, algorithm confusion, replay, open redirect và lỗi claim mapping.
9. Xây dựng test plan cho token hợp lệ, token giả, token sai audience, token hết hạn và key rotation.

## 2. OIDC validation nằm ở đâu trong luồng đăng nhập?

OIDC validation diễn ra sau khi RP nhận authorization response và đổi authorization code lấy token response, hoặc khi RP nhận ID token qua một flow được giao thức cho phép. Trong Authorization Code flow, RP thường thực hiện việc đổi code tại token endpoint ở backend, rồi xác minh ID token trước khi tạo session ứng dụng.

~~~mermaid
sequenceDiagram
    participant U as User / Browser
    participant R as RP
    participant O as OpenID Provider
    participant J as JWKS endpoint
    U->>R: Bắt đầu đăng nhập
    R->>R: Tạo state, nonce, PKCE verifier
    R-->>U: Redirect authorization request
    U->>O: Authorization request
    O->>U: Xác thực credential và MFA nếu cần
    O-->>U: Redirect về RP với authorization code + state
    U->>R: Callback
    R->>R: Kiểm tra state và transaction
    R->>O: Đổi code + PKCE verifier tại token endpoint
    O-->>R: ID token, access token, có thể refresh token
    R->>J: Lấy public key nếu cache chưa có key phù hợp
    J-->>R: JWKS
    R->>R: Verify chữ ký và kiểm tra claim ID token
    R->>R: Ánh xạ issuer + subject
    R->>R: Tạo session cục bộ
    R-->>U: Đăng nhập thành công
~~~

Sơ đồ mô tả Authorization Code flow. Với implicit hoặc hybrid flow, token có thể đi qua front channel và có thêm các kiểm tra như hash claim; không nên chọn flow cũ chỉ để đơn giản hóa tích hợp. Ứng dụng mới thường ưu tiên Authorization Code + PKCE theo cấu hình OIDC/OAuth hiện hành.

### 2.1. Ranh giới trách nhiệm

| Thành phần | Trách nhiệm xác minh |
| --- | --- |
| **RP / OIDC client** | Authorization response, state, code exchange, ID token, nonce và ánh xạ subject |
| **Authorization server / OP** | Credential, MFA, client registration, code, PKCE và phát hành token |
| **Resource server** | Access token dành cho API của nó: issuer, audience, signature/introspection, expiry, scope |
| **UserInfo endpoint** | Token truy cập phù hợp và subject response khớp subject trong ID token |
| **Application authorization** | Membership, tenant, action, resource và quyền hiện tại |

Không chuyển trách nhiệm xác minh cho browser chỉ vì browser nhận callback. Với web confidential client, phần đổi code và xác minh token nên diễn ra ở backend. Public client phải tuân thủ PKCE và lưu token theo khả năng bảo vệ của nền tảng.

## 3. Phân biệt ID token, access token và refresh token

| Token | Người tiêu thụ chính | Dùng để làm gì? | Không dùng để |
| --- | --- | --- | --- |
| **ID token** | RP/client OIDC | Xác minh sự kiện authentication và subject | Gọi API thay access token |
| **Access token** | Resource server/API | Truy cập API trong audience/scope được cấp | Tự động tạo session đăng nhập RP nếu không có giao thức riêng |
| **Refresh token** | Client tại token endpoint | Xin access token mới theo policy | Gửi tới resource server hoặc browser URL |

ID token thường là JWT có chữ ký. Access token có thể là JWT hoặc opaque string; RP không nên giả định định dạng access token nếu hợp đồng không quy định. Refresh token thường là credential opaque và phải được bảo vệ như bí mật.

### 3.1. Vì sao không dùng access token làm ID token?

Audience của access token thường là API/resource server, trong khi audience của ID token là client ID của RP. Hai token có mục đích khác nhau. Nếu RP chấp nhận một access token làm bằng chứng đăng nhập mà không có profile xác minh thích hợp, token dành cho API khác có thể bị dùng để tạo session sai ứng dụng.

Tương tự, resource server không nên nhận ID token chỉ vì nó là JWT có chữ ký hợp lệ. ID token không được phát hành để cấp quyền truy cập API.

### 3.2. Token không phải session

ID token là bằng chứng về một sự kiện xác thực; RP thường tạo session riêng sau khi xác minh. Session có thể tồn tại theo chính sách ứng dụng và được thu hồi độc lập với thời hạn ID token. Access token có vòng đời và audience riêng. Logout cần xử lý session/token theo thiết kế, không chỉ xóa ID token khỏi client.

## 4. Nguồn trust: issuer và discovery metadata

Trước khi xác minh token, RP phải biết chính xác **issuer nào được tin cậy**. Issuer là định danh của OP, thường là URL HTTPS. RP nên lấy cấu hình OIDC discovery từ issuer đã được đăng ký và xác minh, không lấy issuer tùy ý từ token chưa xác minh.

### 4.1. Discovery document

OIDC Discovery cung cấp metadata như:

- issuer;
- authorization_endpoint;
- token_endpoint;
- userinfo_endpoint;
- jwks_uri;
- end_session_endpoint nếu được hỗ trợ;
- supported response types và subject types;
- signing algorithms được hỗ trợ;
- token endpoint authentication methods;
- các tính năng và policy liên quan.

RP phải kiểm tra trường issuer trong discovery metadata **khớp chính xác** issuer đã cấu hình. Endpoint phải dùng HTTPS và thuộc trust configuration được chấp nhận. Không tự động tin một metadata document chỉ vì nó tải được qua mạng.

### 4.2. Không để token điều khiển nơi tải khóa

JWT header có thể chứa các trường như kid, alg và đôi khi các URL tham chiếu khóa. RP không được dùng jku/x5u hoặc URL do token tự khai để tải khóa bất kỳ. Khóa xác minh phải đến từ JWKS endpoint đã được ràng buộc với issuer tin cậy. Điều này giúp tránh SSRF, key substitution và issuer confusion.

### 4.3. Nhiều issuer

Nếu RP hỗ trợ nhiều IdP, mỗi transaction phải gắn với một issuer/client configuration cụ thể. Không chỉ đọc claim iss từ token chưa xác minh rồi chọn cấu hình tương ứng. Quy trình cần:

1. Chọn IdP từ tenant/trust registry đã được xác minh;
2. Lưu issuer, client ID, redirect URI và transaction ID ở server-side;
3. Ràng buộc callback với transaction đó;
4. Xác minh token bằng key thuộc issuer đã chọn;
5. Kiểm tra iss trong token khớp issuer của transaction.

## 5. Xác minh chữ ký ID token

RP phải xác minh chữ ký trước khi tin các claim. Giải mã header/payload của JWT chỉ là thao tác đọc dữ liệu, không chứng minh token được OP phát hành.

### 5.1. Các bước xác minh

1. Đọc JWT theo parser an toàn, giới hạn kích thước và định dạng.
2. Kiểm tra thuật toán ký nằm trong allowlist đã cấu hình cho issuer/client.
3. Đọc kid và chọn khóa phù hợp từ JWKS đã tin cậy.
4. Kiểm tra loại khóa, thuật toán, use/key_ops và các thuộc tính cần thiết.
5. Xác minh chữ ký bằng thư viện JWT/OIDC đã được kiểm chứng.
6. Nếu không có khóa phù hợp, thực hiện refresh JWKS theo cơ chế có giới hạn rồi xác minh lại.
7. Nếu chữ ký không hợp lệ hoặc vẫn không tìm được khóa tin cậy, từ chối token.

Không tự viết thuật toán chữ ký. Không bỏ qua xác minh khi JWKS endpoint lỗi. Không chấp nhận thuật toán none hoặc thuật toán ngoài allowlist.

### 5.2. Allowlist thuật toán

RP nên cấu hình thuật toán ký được chấp nhận dựa trên metadata, thư viện và chính sách của tổ chức. Không để token tự quyết định thuật toán. Kiểm tra tương thích giữa alg trong header và key type/thuộc tính JWK.

Ví dụ, không dùng RSA public key như HMAC secret do nhầm lẫn giữa thuật toán bất đối xứng và đối xứng. Không cho phép thuật toán không được hỗ trợ hoặc đã bị tổ chức loại bỏ.

### 5.3. Chọn khóa qua kid

kid là gợi ý để chọn khóa trong JWKS, không phải bằng chứng rằng khóa đó đáng tin. RP phải tìm kid trong JWKS của issuer đã cấu hình và kiểm tra key metadata. Nếu nhiều key cùng kid hoặc key không rõ mục đích, không được tùy tiện chọn một khóa.

Nếu token không có kid và JWKS có nhiều khóa phù hợp, hành vi phải theo profile/thư viện được cấu hình; không thử mọi khóa không giới hạn. Cấu hình rõ ràng giúp tránh ambiguity và giảm nguy cơ DoS.

## 6. Kiểm tra các claim bắt buộc của ID token

Sau khi chữ ký hợp lệ, RP tiếp tục kiểm tra claim theo OIDC Core và transaction context.

| Claim | Điều cần kiểm tra | Ý nghĩa |
| --- | --- | --- |
| **iss** | Khớp chính xác issuer đã cấu hình | Token đến từ OP được tin cậy |
| **sub** | Có mặt, là định danh subject hợp lệ theo profile | Khóa subject trong phạm vi issuer |
| **aud** | Chứa client ID của RP | Token dành cho client này |
| **exp** | Thời điểm hiện tại trước hạn, có clock skew nhỏ theo policy | Token chưa hết hạn |
| **iat** | Thời điểm phát hành hợp lý theo policy | Phát hiện token bất thường/quá cũ |
| **nonce** | Khớp nonce đã lưu nếu RP gửi nonce | Ràng buộc ID token với authentication transaction |
| **azp** | Kiểm tra khi có nhiều audience và theo yêu cầu OIDC | Xác định authorized party |
| **auth_time** | Kiểm tra khi yêu cầu max_age/recent authentication | Thời điểm người dùng thực sự xác thực |
| **acr/amr** | Diễn giải theo hợp đồng với OP | Authentication context/method |

### 6.1. Issuer

So sánh iss theo giá trị chính xác, gồm scheme, host, path và dấu slash cuối nếu issuer định nghĩa như vậy. Không chỉ so sánh domain hoặc dùng phép so khớp chuỗi con. Ví dụ issuer của tenant A không được coi là issuer tenant B chỉ vì cùng hostname.

### 6.2. Subject

sub là định danh ổn định trong phạm vi issuer. RP nên dùng cặp **iss + sub** làm khóa liên kết OIDC, thay vì email hoặc tên hiển thị. Subject có thể là pairwise subject; không giả định cùng một người luôn nhận cùng sub ở mọi client/sector.

Không dùng sub từ token trước khi token được xác minh đầy đủ. Không cho phép client tự gửi sub riêng trong body rồi ghi đè danh tính đã xác minh.

### 6.3. Audience

aud có thể là chuỗi hoặc mảng. RP phải xác minh client ID của chính nó nằm trong audience. Nếu token có nhiều audience, áp dụng kiểm tra azp theo OIDC và policy. Không chấp nhận token chỉ vì audience chứa một API hoặc ứng dụng khác.

### 6.4. Authorized party

Khi aud chứa nhiều giá trị, azp có thể xác định client được ủy quyền. Nếu azp hiện diện, kiểm tra nó khớp client ID của RP theo quy tắc OIDC. Nếu thiếu azp trong trường hợp giao thức yêu cầu, từ chối.

### 6.5. Thời gian

exp phải còn hiệu lực. iat cần hợp lý; token có iat trong tương lai vượt clock skew hoặc quá cũ bất thường nên bị từ chối theo policy. Nếu RP gửi max_age, cần kiểm tra auth_time và xác nhận lần xác thực gần nhất đáp ứng yêu cầu.

Cho phép clock skew nhỏ để xử lý chênh lệch đồng hồ, nhưng không mở rộng thời hạn quá mức. Hệ thống cần đồng bộ thời gian bằng NTP và giám sát clock drift.

## 7. Nonce và ràng buộc authorization transaction

Nonce là giá trị do RP tạo trong authorization request và lưu gắn với transaction. Khi nhận ID token, RP so sánh nonce trong token với giá trị đã lưu. Nếu không khớp, token không thuộc giao dịch đang xử lý và phải bị từ chối.

### 7.1. Vòng đời nonce

- Sinh nonce ngẫu nhiên bằng CSPRNG;
- Gắn với browser session/login transaction, issuer và client;
- Không để client tự chọn nonce không được server lưu;
- Đưa nonce vào authorization request;
- Xác minh claim nonce trong ID token;
- Tiêu thụ transaction một lần và xóa nonce sau khi xử lý;
- Hết hạn transaction nếu callback không tới trong thời gian cho phép.

Nonce không thay thế state. State bảo vệ callback và liên kết browser transaction; nonce ràng buộc ID token với authentication request. Cả hai nên được dùng đúng mục đích.

### 7.2. State và PKCE

RP cần kiểm tra state trả về khớp transaction đã tạo, chưa được sử dụng và gắn với browser context phù hợp. PKCE ràng buộc authorization code với code verifier. Những kiểm tra này giảm login CSRF, code interception và transaction mix-up.

Không chấp nhận callback chỉ vì có code. Không đổi code tại token endpoint nếu state/transaction không hợp lệ. Không dùng một state cố định cho mọi lần đăng nhập.

### 7.3. Token substitution và replay

Attacker có thể cố gắng gắn ID token từ một lần đăng nhập khác vào callback hiện tại. Kiểm tra state, nonce, issuer, audience, thời hạn và transaction binding giúp từ chối token sai ngữ cảnh. Authorization code phải được dùng một lần và có thời hạn ngắn; transaction đã hoàn tất không được tái sử dụng.

## 8. Kiểm tra các claim tùy chọn và authentication context

Không phải claim tùy chọn nào cũng cần được kiểm tra trong mọi ứng dụng. RP phải xác định claim nào cần cho policy và không tự diễn giải claim ngoài hợp đồng.

### 8.1. auth_time và max_age

Nếu RP yêu cầu xác thực gần đây bằng max_age, OP cần cung cấp auth_time. RP kiểm tra khoảng thời gian từ auth_time đến hiện tại không vượt quá max_age theo clock policy. Không dùng iat thay auth_time: iat là lúc token được phát hành, không nhất thiết là lúc người dùng nhập credential hoặc hoàn tất MFA.

### 8.2. acr và amr

acr biểu thị authentication context class theo thỏa thuận; amr mô tả phương thức xác thực đã dùng. Giá trị chỉ có ý nghĩa khi RP hiểu mapping và tin cậy OP phát hành. Không tự kết luận một chuỗi amr chứa "mfa" đồng nghĩa với MFA chống phishing hoặc đạt assurance cụ thể.

Với thao tác nhạy cảm, RP có thể yêu cầu acr cụ thể hoặc step-up. Sau khi nhận token, RP phải kiểm tra kết quả thực tế; việc gửi acr_values không tự chứng minh OP đã đáp ứng.

### 8.3. at_hash và c_hash

Trong một số response type/flow có ID token đi kèm access token hoặc authorization code ở front channel, OIDC định nghĩa at_hash/c_hash để ràng buộc giá trị tương ứng với ID token. Chỉ kiểm tra khi flow và response type yêu cầu; dùng đúng thuật toán hash theo signing algorithm và quy tắc OIDC. Không tự bỏ qua claim khi profile đang sử dụng yêu cầu kiểm tra.

### 8.4. Các claim profile

Claim như name, email, picture, locale hoặc preferred_username là thuộc tính hồ sơ. Chúng không phải khóa danh tính bền vững và không nên tự động trở thành role/permission. Nếu dùng email, kiểm tra email_verified theo policy và hiểu rằng email có thể thay đổi hoặc được tái cấp.

## 9. Xác minh access token tại resource server

RP xác minh ID token để đăng nhập; **resource server** xác minh access token để quyết định request API có được tiếp tục hay không. Cùng một JWT library có thể được dùng, nhưng validation profile phải đúng loại token và audience.

### 9.1. Access token dạng JWT

Nếu authorization server phát hành JWT access token theo một profile đã thỏa thuận, resource server cần kiểm tra:

1. Chữ ký bằng khóa tin cậy của issuer;
2. Thuật toán và key type nằm trong allowlist;
3. Issuer đúng authorization server đã cấu hình;
4. Audience dành cho API/resource server này;
5. exp và nbf còn hiệu lực, có clock skew giới hạn;
6. Token type/profile đúng (ví dụ access-token profile yêu cầu typ phù hợp);
7. Scope/permissions và client/subject claims theo hợp đồng;
8. Trạng thái/revocation hoặc sender constraint nếu kiến trúc yêu cầu.

Không chấp nhận ID token chỉ vì issuer và chữ ký đúng; audience và token purpose phải phù hợp API.

### 9.2. Access token opaque

Nếu access token là opaque, resource server thường dùng introspection endpoint hoặc cơ chế xác minh do authorization server cung cấp. Cần xác minh:

- introspection response đến từ endpoint tin cậy qua TLS và client authentication phù hợp;
- token đang active;
- issuer/client/subject/audience/scope và thời hạn theo policy;
- cache kết quả introspection có TTL phù hợp với yêu cầu thu hồi;
- không ghi token nguyên dạng vào log.

Không cố decode opaque token rồi tự suy luận claim. Không giả định mọi authorization server đều dùng cùng cấu trúc introspection.

### 9.3. Audience của API

Access token dành cho API A không được API B chấp nhận chỉ vì cùng issuer ký. Resource server phải kiểm tra audience chính xác theo cấu hình. Điều này ngăn token substitution giữa các API hoặc microservice.

### 9.4. Scope không thay thế authorization

Scope là quyền/ủy quyền được token biểu diễn theo hợp đồng. API vẫn cần kiểm tra tenant, resource ownership, trạng thái tài khoản và policy nghiệp vụ. Một scope rộng không được bỏ qua kiểm tra quyền trên từng tài nguyên.

## 10. UserInfo endpoint và subject consistency

UserInfo endpoint trả thuộc tính về người dùng khi client trình bày access token hợp lệ. RP phải gọi UserInfo bằng access token phù hợp và xác minh response theo TLS/giao thức.

**Claim sub trong UserInfo phải khớp sub trong ID token đã xác minh.** Nếu không khớp, RP phải từ chối dữ liệu UserInfo và điều tra. Không dùng email để thay thế việc so khớp subject.

UserInfo có thể trả thêm email, name, groups hoặc profile theo scope và consent. RP chỉ yêu cầu và lưu những thuộc tính cần thiết. Không tin role/group nếu chúng không thuộc hợp đồng authorization đã được kiểm tra.

## 11. JWKS cache và signing-key rotation

OP công bố public key qua JWKS endpoint. RP cần cache để tránh gọi endpoint cho mỗi token, nhưng phải có cách cập nhật khi key thay đổi.

### 11.1. Cách quản lý JWKS

- Lấy jwks_uri từ discovery metadata đã xác minh;
- Tải qua HTTPS và xác minh TLS hostname;
- Kiểm tra định dạng JWKS, giới hạn kích thước và số lượng khóa;
- Chỉ chấp nhận key type/use/alg phù hợp;
- Cache theo policy và HTTP cache metadata khi phù hợp;
- Không tải lại JWKS vô hạn khi nhận token kid ngẫu nhiên;
- Refresh khi unknown kid theo cơ chế giới hạn và chống request storm.

### 11.2. Khi gặp unknown kid

Một token có kid không có trong cache có thể là dấu hiệu IdP vừa xoay khóa, nhưng cũng có thể là request giả nhằm ép RP tải JWKS liên tục.

Quy trình hợp lý:

1. Kiểm tra token header có định dạng hợp lệ và kích thước giới hạn;
2. Nếu kid chưa có, thực hiện tối đa một lần refresh JWKS cho issuer trong cửa sổ kiểm soát;
3. Tìm lại khóa sau refresh;
4. Nếu vẫn không có khóa phù hợp, từ chối token;
5. Rate limit và ghi nhận sự kiện unknown kid để phát hiện abuse.

Không bỏ qua chữ ký khi không tìm được kid. Không tải URL khóa từ header token.

### 11.3. Rotation overlap

IdP có thể công bố khóa mới trước khi ký token bằng khóa đó và giữ khóa cũ trong một khoảng để các token cũ còn xác minh được. RP cần refresh JWKS và giữ cache theo policy, đồng thời có quy trình khi khóa cũ bị compromise. Không pin cứng một public key duy nhất mà không có cơ chế cập nhật.

Nếu khóa ký bị lộ, chỉ chờ token hết hạn có thể không đủ. Cần cập nhật trust, loại bỏ khóa compromise, thu hồi session/token có liên quan và đánh giá token giả có thể đã được sử dụng.

## 12. Validation trong môi trường nhiều tenant và nhiều IdP

Một RP có thể phục vụ nhiều tổ chức, mỗi tổ chức có issuer riêng. Việc chọn issuer phải dựa trên trust registry đã được xác minh, không dựa trên claim chưa xác minh.

### 12.1. Trust registry

Mỗi cấu hình tenant/IdP nên ràng buộc:

- tenant hoặc organization ID;
- issuer URL chính xác;
- client ID và redirect URI;
- discovery metadata/JWKS trust source;
- signing algorithms được chấp nhận;
- subject mapping và policy account linking;
- authentication assurance mapping;
- trạng thái active/suspended và lịch sử thay đổi.

### 12.2. Không gộp account theo email

Khóa liên kết danh tính OIDC thường là cặp issuer + sub. Email có thể thay đổi, trùng giữa tenant hoặc được tái cấp cho người khác. Dù email_verified là true, RP vẫn cần policy liên kết tài khoản rõ ràng và xác thực lại khi người dùng muốn nối một IdP mới.

### 12.3. Tenant isolation

Token từ issuer/tenant A không tự tạo quyền truy cập tenant B. Sau authentication, RP ánh xạ subject vào account và kiểm tra membership/role hiện tại cho resource. Không lấy tenant ID từ query/body làm căn cứ duy nhất.

## 13. Session, logout và thu hồi sau OIDC validation

Khi ID token hợp lệ, RP thường tạo session riêng. Session có thể tồn tại lâu hơn ID token theo policy, nhưng cần quản lý expiry, revocation, account state và step-up.

### 13.1. ID token không phải logout token

ID token không tự thông báo logout. Nếu RP hỗ trợ OIDC RP-Initiated Logout hoặc Back-Channel Logout, cần xác minh logout request/token theo profile tương ứng. Logout token có claim và quy tắc riêng; không xử lý nó như ID token đăng nhập.

### 13.2. Thu hồi token

Refresh token có thể bị thu hồi tại authorization server. Access token JWT tự chứa có thể còn hiệu lực tới exp nếu API không kiểm tra trạng thái hoặc denylist. RP/API phải định nghĩa rõ thời gian thu hồi và không tuyên bố logout tức thời nếu kiến trúc chưa thực hiện được.

### 13.3. Account state

Token hợp lệ không đảm bảo account vẫn active. Sau khi xác minh token, ứng dụng cần kiểm tra trạng thái tài khoản, tenant membership và chính sách hiện tại trước khi cấp session hoặc cho phép hành động nhạy cảm.

## 14. Những lỗi validation thường gặp

| Lỗi | Hậu quả | Cách phòng ngừa |
| --- | --- | --- |
| Chỉ decode JWT | Tin token giả hoặc bị sửa | Xác minh chữ ký bằng key tin cậy |
| Chấp nhận alg do token tự chọn | Algorithm confusion hoặc none | Allowlist thuật toán theo issuer/client |
| Tin issuer từ token chưa xác minh | Issuer mix-up và tải key sai | Issuer registry/transaction binding |
| Bỏ kiểm tra audience | Token của client/API khác được chấp nhận | Kiểm tra aud và azp đúng profile |
| Bỏ nonce | ID token từ transaction khác có thể bị gắn vào callback | Lưu và so nonce theo transaction |
| Không kiểm tra state | Login CSRF/callback injection | State ngẫu nhiên, transaction-bound, one-time |
| Dùng ID token gọi API | Nhầm token purpose và audience | Resource server chỉ nhận access token phù hợp |
| Chấp nhận access token làm ID token | Tạo session từ token sai mục đích | Validation profile riêng |
| Tin email làm khóa account | Account linking nhầm hoặc takeover | Issuer + sub và linking có xác thực |
| Tải jku/x5u tùy ý | SSRF/key substitution | Chỉ dùng JWKS đã cấu hình |
| Unknown kid gây refresh liên tục | DoS JWKS endpoint | Cache, rate limit và single-flight refresh |
| Bỏ kiểm tra UserInfo sub | Ghép profile của subject khác | So sub với ID token |
| Tin acr/amr không có hợp đồng | Đánh giá sai MFA assurance | Mapping rõ với OP và policy |
| Clock skew quá rộng | Token cũ còn được chấp nhận lâu | Đồng bộ thời gian, skew nhỏ |
| Logout chỉ xóa cookie | Session/token cũ tiếp tục dùng | Server-side session/token revocation |

## 15. Ví dụ xuyên suốt: nền tảng học tập đa tenant

Một nền tảng học tập cho phép giảng viên đăng nhập bằng IdP của trường. RP dùng OIDC Authorization Code + PKCE. API điểm số chỉ chấp nhận access token dành riêng cho resource server.

### 15.1. Đăng nhập

1. Giảng viên chọn trường A; RP tra trust registry lấy issuer và client configuration đã được duyệt.
2. RP tạo state, nonce và PKCE verifier, lưu transaction có thời hạn.
3. Browser được chuyển tới authorization endpoint của issuer A.
4. IdP xác thực password/passkey và MFA theo policy.
5. IdP trả authorization code về redirect URI đã đăng ký.
6. RP kiểm tra state, đổi code kèm PKCE verifier tại token endpoint.
7. RP lấy khóa từ JWKS của issuer A và xác minh chữ ký ID token.
8. RP kiểm tra iss, sub, aud, azp khi áp dụng, exp, iat, nonce và authentication context.
9. RP ánh xạ issuer + sub vào account, kiểm tra membership trường A và tạo session.

### 15.2. Gọi API điểm số

Browser/app gửi access token tới API. API xác minh token theo profile đã thống nhất, kiểm tra issuer, audience, expiry, scope và trạng thái. Sau đó API kiểm tra giảng viên có quyền xem/sửa điểm của lớp học cụ thể hay không. ID token không được dùng thay access token.

### 15.3. Khóa ký vừa được xoay

RP nhận ID token có kid mới. Nếu JWKS cache chưa có khóa, RP refresh JWKS một lần theo cơ chế có giới hạn. Nếu khóa mới được công bố và phù hợp, chữ ký được xác minh; nếu không tìm được khóa tin cậy, login bị từ chối và sự kiện được ghi nhận. RP không bỏ qua chữ ký để duy trì đăng nhập.

### 15.4. Người dùng đổi tenant

Giảng viên đăng nhập trường B. RP chọn issuer B từ trust registry và xác minh token theo issuer B. Dù email giống tài khoản trường A, RP không tự động gộp hai danh tính; account linking cần quy trình xác thực và xác nhận riêng.

## 16. Pseudocode validation tham khảo

### 16.1. ID token

~~~text
validate_id_token(id_token, transaction, provider_config):
    require transaction exists and is not consumed
    require transaction.issuer == provider_config.issuer

    header = parse_jwt_header_with_size_limits(id_token)
    require header.alg in provider_config.allowed_id_token_algorithms
    key = find_key_in_trusted_jwks(provider_config.jwks, header.kid)
    if key is missing:
        refresh_jwks_once_with_rate_limit(provider_config)
        key = find_key_in_trusted_jwks(provider_config.jwks, header.kid)
    require key is suitable for header.alg
    verify_jwt_signature(id_token, key)

    claims = parse_verified_claims(id_token)
    require claims.iss == provider_config.issuer
    require claims.sub is present and valid
    require provider_config.client_id in claims.aud
    validate_azp_if_required(claims, provider_config.client_id)
    require claims.exp is valid with bounded_clock_skew
    validate_iat_policy(claims.iat)
    validate_nonce_if_sent(claims.nonce, transaction.nonce)
    validate_auth_time_if_max_age_requested(claims, transaction)

    atomically_consume_transaction(transaction.id)
    return verified_identity(issuer=claims.iss, subject=claims.sub)
~~~

Đây là pseudocode giải thích trách nhiệm, không phải mã thư viện dùng trực tiếp. Thư viện OIDC đã được kiểm chứng thường xử lý thêm các điều kiện đặc thù của flow, response type, encryption và hash claim.

### 16.2. Access token tại resource server

~~~text
validate_access_token(token, api_config):
    if token_profile_is_opaque(api_config):
        result = introspect_over_authenticated_tls(token)
        require result.active == true
        claims = validated_introspection_result(result)
    else:
        claims = verify_jwt_using_trusted_issuer_keys(token)
        require claims.iss == api_config.issuer
        require api_config.audience in claims.aud
        require claims.exp is valid
        require claims.nbf is valid if present
        require token_type_matches_access_token_profile(token)

    require required_scope in claims.scope
    require principal_is_active(claims.subject)
    authorize_subject_for_resource(claims.subject, request.resource)
~~~

Resource server cần dùng profile access token đã thỏa thuận, chẳng hạn JWT access token profile nếu được OP phát hành. Không áp dụng máy móc claim của ID token cho access token hoặc ngược lại.

## 17. Kiểm thử OIDC validation

Test trong môi trường RP/OP thử nghiệm, dùng issuer, client và key riêng. Không sử dụng token production trong fixture.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Signature | ID token có chữ ký hợp lệ từ JWKS tin cậy | Được tiếp tục kiểm tra claim |
| Tampering | Sửa payload hoặc signature | Từ chối |
| Algorithm | alg none hoặc thuật toán ngoài allowlist | Từ chối |
| Key type | JWK không tương thích với alg | Từ chối |
| Unknown kid | kid không có trong JWKS sau refresh có giới hạn | Từ chối và ghi event |
| Issuer | iss sai hoặc issuer tenant khác | Từ chối |
| Audience | aud không chứa client ID của RP | Từ chối |
| Multiple audience | aud nhiều giá trị, azp sai hoặc thiếu khi cần | Từ chối |
| Subject | sub thiếu hoặc không hợp lệ | Từ chối |
| Expiry | exp đã qua hoặc nbf ở tương lai | Từ chối theo clock policy |
| Clock skew | iat/auth_time vượt ngưỡng | Từ chối theo policy |
| Nonce | nonce thiếu/sai khi RP đã gửi nonce | Từ chối |
| State | Callback có state sai hoặc đã tiêu thụ | Từ chối |
| PKCE | Code verifier sai | Token endpoint từ chối |
| Replay | Dùng lại authorization code/transaction | Từ chối |
| UserInfo | sub không khớp ID token | Từ chối profile response |
| Access token | Token audience dành cho API khác | Resource server từ chối |
| Token type | ID token được gửi tới API | Từ chối |
| Opaque token | Introspection inactive hoặc sai issuer/audience | Từ chối |
| JWKS rotation | Key mới được công bố, key cũ overlap | Xác minh đúng trong giai đoạn chuyển đổi |
| JWKS outage | Endpoint không truy cập được và cache không có key phù hợp | Fail closed cho token không xác minh được |
| Tenant | Subject hợp lệ nhưng không có membership tenant | Authentication có thể thành công; authorization DENY |
| Logging | Bật debug/error reporting | Không log raw token, code, cookie hoặc secret |

### 17.1. Kiểm tra bất biến bảo mật

- Không tạo session từ JWT chỉ được decode;
- Chỉ issuer đã cấu hình và đúng transaction mới được tin;
- ID token phải dành cho đúng client;
- Access token phải dành cho đúng resource server;
- Nonce/state/PKCE được kiểm tra theo đúng mục đích và transaction;
- Unknown kid không làm verifier bỏ qua chữ ký hoặc tải URL tùy ý;
- UserInfo subject khớp ID token subject;
- Authentication không tự cấp quyền tenant/resource;
- Token, authorization code và session credential không xuất hiện trong log.

## 18. Checklist production

1. **Issuer trust:** Issuer được đăng ký trước, HTTPS và discovery issuer khớp chính xác?
2. **Client registration:** Client ID, redirect URI, token endpoint authentication và PKCE đúng cấu hình?
3. **Transaction:** State, nonce, PKCE verifier và request context được sinh ngẫu nhiên, lưu an toàn, hết hạn và tiêu thụ một lần?
4. **Signature:** JWT được xác minh bằng thư viện chuẩn, allowlist alg và JWKS của issuer tin cậy?
5. **Key selection:** kid, kty, use, key_ops và alg được kiểm tra; unknown kid có refresh giới hạn?
6. **ID token claims:** iss, sub, aud, azp, exp, iat, nonce và auth_time được kiểm tra khi áp dụng?
7. **Flow-specific claims:** at_hash/c_hash và các điều kiện response type được xử lý đúng flow?
8. **Access token:** Resource server phân biệt JWT/opaque, kiểm tra audience, scope, expiry và token profile?
9. **UserInfo:** sub khớp ID token; chỉ lấy profile cần thiết?
10. **Identity mapping:** Dùng issuer + sub, không tự gộp theo email?
11. **Authorization:** Membership, tenant, resource và trạng thái account được kiểm tra riêng?
12. **Session/logout:** Session RP có expiry/revocation; logout và token revocation có semantics rõ?
13. **Key lifecycle:** JWKS cache, rotation, compromise response và metadata change có owner?
14. **Resilience:** Clock sync, JWKS outage, introspection outage và rate limit có chính sách?
15. **Privacy:** Token, code, assertion, cookie và profile nhạy cảm không bị log dư thừa?
16. **Testing:** Có test tampering, wrong issuer/audience, replay, nonce/state, unknown kid và tenant isolation?

## 19. Bài tập tình huống

Một ứng dụng web dùng OIDC. Callback nhận ID token rồi decode payload, đọc email và tạo session. Đội phát triển kiểm tra exp nhưng không kiểm tra chữ ký, issuer, audience hoặc nonce. API điểm số nhận cùng ID token làm bearer credential. Khi IdP xoay khóa, ứng dụng tải URL jku từ JWT header để lấy public key. Người dùng có cùng email ở hai trường được tự động gộp vào một tài khoản.

**Yêu cầu:**

1. Chỉ ra ít nhất **tám lỗi** trong token validation, key trust, token purpose và identity mapping.
2. Thiết kế lại ID token validation với issuer, audience, signature, nonce và transaction binding.
3. Đề xuất cách resource server xác minh access token đúng audience.
4. Thiết kế JWKS cache và unknown-kid refresh chống request storm.
5. Đề xuất account linking cho người dùng có cùng email ở hai tenant.
6. Viết test chứng minh token giả, token của API khác và ID token không thể tạo quyền gọi API điểm số.

**Gợi ý đối chiếu:** decode không phải verify; JWKS phải đến từ issuer đã cấu hình; ID token dành cho RP; access token dành cho API; kiểm tra issuer/audience/nonce/state/PKCE; dùng issuer + sub; tenant authorization là bước riêng.

## 20. Ghi nhớ

- **OIDC validation** xác minh kết quả authentication theo issuer, client và transaction đã được tin cậy; decode JWT không phải xác minh.
- **ID token** dành cho RP; **access token** dành cho resource server; **refresh token** dành cho token endpoint. Không dùng thay thế lẫn nhau.
- ID token cần kiểm tra chữ ký, thuật toán, iss, sub, aud, azp khi áp dụng, exp, iat, nonce và auth_time khi policy yêu cầu.
- JWKS phải được lấy từ issuer đã cấu hình. kid chỉ giúp chọn khóa; unknown kid cần refresh có giới hạn và không được làm verifier bỏ qua chữ ký.
- State, nonce và PKCE bảo vệ các phần khác nhau của authorization transaction; phải kiểm tra đúng transaction và tiêu thụ một lần.
- UserInfo sub phải khớp ID token sub. Liên kết danh tính dựa trên issuer + subject, không tự gộp theo email.
- Resource server xác minh access token dành cho chính API; authentication thành công vẫn phải qua authorization theo tenant, resource và trạng thái hiện tại.
- Session của RP, token expiry, logout và revocation có vòng đời riêng; cần định nghĩa rõ cách thu hồi.

OIDC an toàn khi RP xác minh **ai phát hành token, token dành cho client nào, token thuộc giao dịch nào, khóa nào được tin và subject được ánh xạ ra sao**. Resource server tiếp tục xác minh access token và quyền trên tài nguyên của mình, nhờ đó kết quả đăng nhập liên kết không trở thành lối tắt vượt qua ranh giới bảo mật.
