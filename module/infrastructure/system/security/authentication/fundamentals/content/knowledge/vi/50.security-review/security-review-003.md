# Protocol review

## 1. Protocol review là gì?

**Protocol review (rà soát giao thức)** là quá trình phân tích có hệ thống cách các bên trao đổi message để xác thực danh tính, thiết lập session, phát hành credential hoặc ủy quyền truy cập. Review kiểm tra cả thiết kế, thứ tự message, dữ liệu được ký/mã hóa, cách kiểm tra claim, xử lý lỗi và hành vi khi hệ thống gặp sự cố.

Một giao thức có thể dùng thuật toán mật mã mạnh nhưng vẫn không an toàn nếu các bên xác minh sai ngữ cảnh. Ví dụ, chữ ký JWT hợp lệ không đủ nếu resource server không kiểm tra audience; authorization code được bảo vệ bằng TLS vẫn có thể bị đánh cắp nếu redirect URI hoặc PKCE không được ràng buộc đúng; một assertion SSO có chữ ký hợp lệ vẫn có thể bị replay nếu không kiểm tra thời hạn và trạng thái sử dụng.

Protocol review tìm câu trả lời cho các câu hỏi:

- Các bên tham gia có được xác thực đúng không?
- Mỗi bên đang tin ai, dựa trên bằng chứng nào?
- Message có được ràng buộc với đúng phiên, người dùng, client, resource và mục đích không?
- Attacker có thể sửa, phát lại, tráo, trì hoãn hoặc chuyển message sang một luồng khác không?
- Có đường downgrade sang phương thức yếu hơn không?
- Các lỗi và trạng thái không xác định có làm lộ thông tin hoặc tạo quyền ngoài dự kiến không?

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, protocol review giúp người học nối các chủ đề credential, MFA, passkey, federation, token, session và account recovery thành một quy trình đánh giá bảo mật. Review phải xem xét toàn bộ luồng và các trust boundary, không chỉ đọc tên thuật toán hoặc xác nhận một endpoint trả về token.

## 2. Khi nào cần protocol review?

Nên thực hiện review khi:

- Thiết kế một login flow hoặc thay đổi cách phát hành session.
- Tích hợp một IdP, identity broker, social login hoặc enterprise federation mới.
- Thêm OAuth client, API resource server, token exchange hoặc delegated access.
- Thay đổi signing key, thuật toán, issuer, audience, certificate hoặc trust metadata.
- Thêm passkey/WebAuthn, MFA factor, recovery method hoặc step-up authentication.
- Thay đổi redirect URI, callback, deep link, device authorization hoặc logout flow.
- Chuyển từ opaque token sang JWT hoặc ngược lại.
- Thêm service-to-service authentication hoặc truyền user context qua message queue.
- Thay đổi cách xử lý timeout, retry, revocation, session expiry hoặc key rotation.
- Điều tra một sự cố liên quan đến token replay, account takeover hoặc federation.

Review càng sớm càng tốt, trước khi giao thức trở thành contract được nhiều client và service phụ thuộc. Thay đổi protocol sau khi phát hành có thể ảnh hưởng tương thích, key lifecycle, session hiện tại và dữ liệu audit.

## 3. Xác định phạm vi và security objective

Trước khi đọc message flow, cần xác định giao thức phải bảo vệ điều gì. Một protocol có thể đáp ứng authentication nhưng không đáp ứng authorization hoặc account linking.

| Security objective | Câu hỏi review |
| --- | --- |
| Authentication | Bên nhận xác minh được principal và bằng chứng xác thực không? |
| Integrity | Attacker có thể sửa message, claim hoặc tham số mà không bị phát hiện không? |
| Confidentiality | Credential, token, assertion hoặc dữ liệu nhạy cảm có bị lộ trên đường truyền/log không? |
| Freshness | Message có thời hạn, nonce, counter hoặc trạng thái chống replay không? |
| Audience restriction | Credential/assertion chỉ dùng được cho đúng client/resource không? |
| Session binding | Kết quả xác thực có được gắn với đúng browser/device/session transaction không? |
| Authorization | Quyền được cấp có đúng subject, actor, tenant, resource và action không? |
| Availability | Attacker có thể làm cạn tài nguyên hoặc khóa tài khoản bằng cách lạm dụng protocol không? |
| Privacy | Message có tiết lộ định danh, factor, tenant hoặc hành vi vượt mục đích không? |
| Auditability | Có thể dựng lại ai xác thực, ai nhận quyền và hành động nào đã xảy ra không? |

Phạm vi review nên ghi rõ protocol version, client type, server/resource, môi trường, luồng chính, luồng lỗi và các phương thức fallback. Không chỉ review happy path.

## 4. Liệt kê actor, asset và trust boundary

### 4.1. Actor

Tùy giao thức, actor có thể gồm:

- End user.
- Browser, mobile app hoặc desktop client.
- Relying Party (RP) hoặc OAuth client.
- Identity Provider (IdP) hoặc Authorization Server (AS).
- Resource Server/API.
- Identity broker hoặc federation gateway.
- MFA provider, authenticator hoặc device.
- Session/token store.
- Help desk hoặc recovery operator.
- Service/workload trung gian.

Với mỗi actor, ghi rõ ai kiểm soát nó, nó có thể bị compromise theo cách nào và actor khác dựa trên bằng chứng nào để tin nó.

### 4.2. Asset

Các asset thường cần bảo vệ:

- Password, passkey private key, TOTP seed và recovery code.
- Authorization code, access token, refresh token, ID Token và session cookie.
- Signing key, encryption key, client secret và certificate private key.
- User identifier, tenant membership, role và account recovery channel.
- Federation metadata, issuer configuration, redirect URI và JWKS.
- Authentication event, session record, audit log và policy decision.

### 4.3. Trust boundary

Trust boundary là nơi dữ liệu hoặc quyền đi từ miền kiểm soát này sang miền khác. Ví dụ:

- Browser sang application server.
- Application sang IdP.
- IdP sang relying party qua federation assertion.
- Backend service sang resource server.
- Public network sang private service network.
- Production workload sang secret manager.
- Human support process sang account recovery system.

Mỗi boundary cần xác định cơ chế authentication, integrity, confidentiality, audience, authorization và logging. Không mặc định hai service cùng VPC, cluster hoặc tenant có thể tin nhau.

## 5. Mô hình hóa message flow

Viết lại protocol thành các bước có thứ tự. Với mỗi message, ghi:

- Sender và receiver.
- Transport/channel.
- Các field và claim.
- Nguồn tạo ra từng giá trị.
- Field nào được ký, MAC, mã hóa hoặc ràng buộc với TLS.
- Receiver kiểm tra gì trước khi thực hiện side effect.
- State được tạo, tiêu thụ hoặc xóa.
- Timeout, retry và kết quả khi response bị mất.

Ví dụ, một luồng login không nên chỉ ghi “user đăng nhập, nhận token”. Cần thể hiện browser tạo authorization request, client tạo state/nonce/PKCE verifier, IdP xác thực user, callback mang code, client đổi code, rồi xác minh token và tạo session.

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant C as OAuth Client
    participant AS as Authorization Server
    participant API as Resource Server
    U->>B: Bắt đầu đăng nhập
    B->>C: Mở login
    C->>C: Tạo state, nonce, PKCE verifier
    C->>B: Redirect authorization request + challenge
    B->>AS: Authorization request
    AS->>U: Xác thực user và consent nếu cần
    U->>AS: Hoàn tất authentication
    AS-->>B: Redirect callback + authorization code + state
    B->>C: Gửi callback
    C->>C: Kiểm tra state
    C->>AS: Token request + code + PKCE verifier
    AS->>AS: Kiểm tra code, client, redirect URI và PKCE
    AS-->>C: Token response
    C->>C: Xác minh ID Token theo OIDC nếu được yêu cầu
    C->>B: Tạo session an toàn
    C->>API: Access token dành cho API
    API->>API: Xác minh token và authorization
~~~

Sơ đồ là ví dụ khái niệm cho Authorization Code Flow. Chi tiết request/response phải tuân theo profile và phiên bản chuẩn thực tế; không dùng sơ đồ khái niệm thay cho protocol specification.

## 6. Kiểm tra cryptographic design

Review phải xác định chính xác primitive và cách sử dụng, không chỉ ghi “dùng encryption”.

### 6.1. Chữ ký và MAC

Kiểm tra:

- Thuật toán có nằm trong allowlist và còn được khuyến nghị không?
- Key có đúng mục đích, đúng issuer và đúng trust domain không?
- Có kiểm tra key ID theo nguồn metadata tin cậy không?
- Có chống algorithm confusion hoặc chấp nhận thuật toán không an toàn không?
- Canonicalization/serialization có nhất quán giữa signer và verifier không?
- Receiver có xác minh toàn bộ phần dữ liệu cần được bảo vệ không?
- Có xử lý key rotation, overlap, compromise và revocation không?

Với JWT, không tin claim trước khi xác minh chữ ký hoặc cơ chế bảo vệ tương ứng. Không lấy key URL tùy ý từ header token. Không chấp nhận thuật toán none hoặc tự động tin thuật toán do token yêu cầu.

### 6.2. Encryption và key agreement

Nếu protocol cần confidentiality:

- Dùng TLS đúng cấu hình cho transport.
- Xác minh hostname/server identity và certificate chain.
- Chọn AEAD hoặc profile mã hóa đã được chuẩn hóa khi cần bảo vệ message-level.
- Không tự thiết kế cipher suite hoặc key derivation.
- Kiểm tra nonce/IV uniqueness theo yêu cầu thuật toán.
- Bảo vệ private key và secret trong KMS/HSM/secret manager phù hợp.

TLS bảo vệ một hop. Nếu message đi qua proxy, queue hoặc broker rồi lưu trữ, cần đánh giá liệu transport encryption có đủ hay cần message-level protection.

### 6.3. Randomness và entropy

State, nonce, PKCE verifier, authorization code, session ID và recovery token cần được sinh bằng cryptographically secure random generator với entropy phù hợp. Không dùng timestamp, sequential ID, username hoặc PRNG không bảo mật cho bí mật.

Review cần kiểm tra độ dài, uniqueness, scope, expiry và cách lưu verifier. Một nonce ngẫu nhiên nhưng không được kiểm tra ở receiver không tạo ra replay protection.

## 7. Freshness, replay và message binding

Replay xảy ra khi attacker thu được một message hợp lệ và gửi lại để tái sử dụng quyền hoặc trạng thái đã xác minh.

Các cơ chế thường gặp:

- Nonce dùng một lần hoặc có state tracking.
- Timestamp/expiry với clock skew giới hạn.
- Sequence number/counter.
- Challenge-response.
- One-time authorization code hoặc recovery code.
- Request signature ràng buộc method, URI, body hash và thời điểm.
- Token sender-constraining hoặc channel binding theo profile.

Review cần hỏi:

1. Message được gắn với đúng protocol transaction chưa?
2. Nonce/state có được kiểm tra và tiêu thụ một cách nguyên tử không?
3. Cửa sổ thời gian có đủ ngắn không?
4. Một message có thể được dùng ở endpoint, client, tenant hoặc resource khác không?
5. Khi hai request giống nhau đến đồng thời, có thể cả hai cùng được chấp nhận không?
6. Retry sau timeout có thể lặp side effect không?

Chỉ kiểm tra timestamp không đủ chống replay nếu message có thể được gửi nhiều lần trong thời hạn. Với one-time token, server cần lưu trạng thái tiêu thụ hoặc có cơ chế tương đương.

## 8. Audience, issuer, subject và actor

Credential hoặc token cần được ràng buộc với đúng nguồn và đúng đích:

- **Issuer (iss):** ai phát hành assertion/token?
- **Audience (aud):** bên nào được phép nhận và sử dụng?
- **Subject (sub):** token/assertion nói về principal nào?
- **Actor/client:** ứng dụng hoặc service nào đang hành động?
- **Tenant:** principal đang hoạt động trong phạm vi tổ chức nào?
- **Scope/authorization details:** quyền nào được cấp?

Một chữ ký hợp lệ không bảo đảm token dành cho service hiện tại. Resource server phải kiểm tra audience chính xác, issuer được cấu hình, token type, thời hạn và các claim bắt buộc theo profile.

Không dùng ID Token thay cho access token khi gọi API. ID Token dành cho client để xác minh authentication event; access token dành cho resource server theo OAuth.

Với federation, subject phải được hiểu trong namespace của issuer. Không liên kết hai tài khoản chỉ vì email hoặc display name giống nhau nếu chưa có quy trình xác minh và account-linking an toàn.

## 9. Kiểm tra OAuth và OpenID Connect

Khi review OAuth/OIDC, xác định rõ client type, grant/response type, resource, redirect URI và threat model. Các điểm quan trọng:

### 9.1. Authorization Code Flow và PKCE

- Dùng Authorization Code Flow cho ứng dụng tương tác theo profile hiện hành.
- Dùng PKCE, đặc biệt cho public client; verifier đủ entropy và được giữ bí mật trong transaction.
- Authorization code ngắn hạn, dùng một lần và gắn với client/redirect URI.
- Kiểm tra redirect URI chính xác theo đăng ký; tránh wildcard rộng hoặc open redirect.
- Dùng TLS cho authorization và token endpoint.
- Client secret không được coi là bí mật trong native app hoặc SPA public client.

### 9.2. State, nonce và CSRF

- State gắn callback với transaction do client khởi tạo và chống login CSRF.
- Nonce gắn ID Token với authentication request trong OIDC.
- Kiểm tra giá trị trả về với giá trị đã lưu, đúng browser/session và đúng thời hạn.
- Không chấp nhận callback thiếu state khi profile yêu cầu.
- Không tái sử dụng transaction state giữa nhiều tab hoặc user session mà không có thiết kế rõ.

PKCE, state và nonce giải quyết các rủi ro liên quan nhưng không thay thế lẫn nhau. Review cần xác minh từng cơ chế được tạo, truyền và kiểm tra đúng nơi.

### 9.3. Redirect URI và mix-up

Kiểm tra:

- Redirect URI khớp chính xác URI đã đăng ký.
- Không cho phép open redirect dẫn code/token tới domain ngoài.
- Client phân biệt đúng issuer khi hỗ trợ nhiều IdP.
- Callback được gắn với issuer/authorization server đã chọn trong transaction.
- Có kiểm tra issuer identifier trong response theo profile hỗ trợ.
- Không dùng một callback mơ hồ khiến response từ IdP A bị xử lý như response từ IdP B.

Authorization server mix-up có thể khiến client gửi code hoặc credential tới endpoint sai. Multi-issuer client cần lưu issuer trong transaction và kiểm tra lại khi nhận callback.

### 9.4. Token validation

Với ID Token, kiểm tra tối thiểu theo OIDC profile:

- Chữ ký và thuật toán.
- Issuer đúng issuer đã chọn.
- Audience chứa client ID dự kiến và xử lý authorized party khi cần.
- Expiry, issued-at và các claim thời gian.
- Nonce nếu request đã gửi nonce.
- Authentication time, assurance class và authentication methods nếu policy yêu cầu mức assurance hoặc thời điểm xác thực.

Với access token, resource server kiểm tra issuer, audience, thời hạn, token type/profile, scope và sender constraint nếu có. Không suy diễn rằng mọi access token đều là JWT hoặc mọi JWT đều là access token.

## 10. Kiểm tra SAML và federation assertion

Với SAML, review cần kiểm tra:

- Signature được xác minh bằng key từ metadata/trust configuration đã xác thực.
- Chữ ký bao phủ đúng assertion/response mà ứng dụng sử dụng.
- Issuer, destination, recipient và audience restriction phù hợp với SP/IdP.
- Not-before và not-on-or-after được kiểm tra với clock skew nhỏ.
- In-response-to khớp AuthnRequest khi dùng SP-initiated flow.
- Subject confirmation data được kiểm tra đúng binding và recipient.
- Assertion ID hoặc response ID có chống replay trong thời hạn.
- XML parser an toàn, tắt external entity và chống XML signature wrapping.
- Relay state không trở thành open redirect hoặc nơi chứa dữ liệu nhạy cảm.

Không xác minh chữ ký trên một XML node rồi đọc claim từ node khác. Cần bảo đảm chính assertion được ứng dụng sử dụng là đối tượng đã được xác minh chữ ký và ràng buộc.

Với mọi federation protocol, metadata, signing key, certificate expiry, rotation và trust establishment đều là một phần của security review.

## 11. Passkey và WebAuthn protocol review

Khi review WebAuthn/passkey, kiểm tra cả registration và authentication ceremony.

### 11.1. Registration

- Challenge do server sinh bằng CSPRNG và gắn với transaction.
- Client data type đúng loại ceremony.
- Challenge khớp và chưa được sử dụng.
- Origin đúng allowlist.
- RP ID hash và RP ID phù hợp.
- Xác minh attestation theo policy; không yêu cầu attestation mạnh nếu không có nhu cầu và khả năng quản lý trust chain.
- Kiểm tra user presence/user verification theo policy.
- Lưu credential public key, credential ID và metadata cần thiết an toàn.
- Ràng buộc credential với đúng account sau khi user đã được xác minh.

### 11.2. Authentication

- Challenge mới, ngẫu nhiên, có expiry và one-time use.
- Kiểm tra origin, RP ID hash và ceremony type.
- Xác minh chữ ký assertion bằng public key đã đăng ký.
- Kiểm tra user handle/credential association và account mapping.
- Áp dụng user verification requirement theo assurance policy.
- Kiểm tra signature counter hoặc tín hiệu clone theo cách tương thích với authenticator sync/passkey; không dùng counter như bằng chứng duy nhất cho mọi loại authenticator.
- Không cho phép credential của RP khác được dùng chỉ vì chữ ký hợp lệ.

Review cũng cần kiểm tra account recovery và factor replacement. Passkey an toàn không giúp được nếu attacker có thể thêm passkey mới qua help desk yếu hoặc recovery channel dễ chiếm.

## 12. MFA protocol và factor binding

MFA cần bảo đảm factor được gắn với đúng user, transaction và purpose:

- TOTP seed được provision qua kênh an toàn và chỉ hiển thị theo quy trình có kiểm soát.
- OTP có thời hạn, giới hạn số lần thử và chống replay.
- Push approval có transaction context, number matching hoặc xác nhận rõ ràng.
- WebAuthn challenge gắn với origin/RP ID và transaction.
- Recovery code có entropy cao, lưu verifier an toàn và dùng một lần.
- Factor enrollment/removal yêu cầu re-authentication và audit.
- Fallback không được làm giảm assurance vượt policy.

Không coi “hai bước” tự động là MFA mạnh. Hai yếu tố có thể cùng dựa trên một secret hoặc cùng bị phishing trong một transaction. Review cần phân tích independence và khả năng chống relay của từng factor.

## 13. Session, cookie và logout protocol

Sau khi authentication hoàn tất, ứng dụng thường tạo session. Review cần kiểm tra:

- Session identifier có đủ ngẫu nhiên và được xoay sau login/step-up không?
- Session được lưu server-side hay self-contained; revocation hoạt động ra sao?
- Cookie có Secure, HttpOnly, SameSite và Path/Domain phù hợp không?
- CSRF protection có phù hợp với cookie-based session không?
- Idle timeout và absolute lifetime có rõ không?
- Session có bị ràng buộc với account state, assurance và device/risk policy khi cần không?
- Logout có revoke server-side session hoặc token family không?
- Concurrent session, password change, factor reset và account disable có chính sách thu hồi không?

Xóa cookie ở browser không đồng nghĩa session phía server đã bị thu hồi. Với JWT tự chứa, token có thể còn hiệu lực đến expiry nếu resource server không kiểm tra revocation/version.

## 14. Error handling, privacy và downgrade

Protocol review phải kiểm tra phản hồi trong mọi nhánh:

- Invalid credential.
- Unknown account.
- Expired/replayed code hoặc assertion.
- Invalid issuer/audience/signature.
- MFA timeout, deny hoặc provider unavailable.
- Recovery request không hợp lệ.
- Rate limit, overload và dependency failure.
- Consent denied hoặc client misconfiguration.

Phản hồi công khai không nên tiết lộ account tồn tại, factor đã đăng ký, trạng thái khóa hoặc lý do nội bộ nhạy cảm. Tuy nhiên, cần giữ semantics chuẩn của giao thức và phân biệt lỗi tạm thời với lỗi credential khi điều đó an toàn.

Kiểm tra downgrade:

- Có thể bỏ MFA bằng cách chọn fallback yếu không?
- Có endpoint cũ vẫn chấp nhận password-only không?
- Client có thể yêu cầu thuật toán yếu hơn hoặc token audience rộng hơn không?
- Có thể dùng session cũ sau khi step-up thất bại không?
- Một IdP yếu hơn có thể được chọn thay cho issuer mạnh hơn không?
- Recovery có thể bỏ qua assurance mà login thông thường yêu cầu không?

Không được tự động chuyển sang phương thức yếu hơn chỉ để tăng tỷ lệ thành công hoặc availability. Fallback phải có policy, scope, approval và audit.

## 15. Authorization và confused deputy

Authentication protocol có thể phát hành token hợp lệ nhưng downstream service vẫn có thể dùng sai quyền.

Review cần xác minh:

- Scope và resource được yêu cầu có tối thiểu không?
- Audience có hẹp theo API/resource không?
- Subject và actor có được phân biệt khi delegation không?
- Tenant/resource ID có được ràng buộc với principal đã xác minh không?
- Token exchange có thể nâng quyền ngoài policy không?
- Service trung gian có dùng credential quyền rộng để thay người dùng làm việc vượt quyền không?
- Resource server có tự kiểm tra ownership, relationship và trạng thái resource không?

Không tin X-User-Id, X-Role, X-Tenant-Id hoặc trace header do client gửi. Nếu dùng identity context nội bộ, gateway phải xóa header ngoài, xác minh caller và tạo context mới trên kênh tin cậy.

## 16. Key lifecycle và protocol versioning

Một protocol có thể an toàn lúc triển khai nhưng mất an toàn khi key hoặc metadata thay đổi:

- Signing/encryption key có owner, purpose và algorithm rõ ràng không?
- Key được lưu ở KMS/HSM hoặc secret manager phù hợp không?
- Rotation có overlap đủ cho token/assertion còn hiệu lực không?
- Có quy trình emergency revoke khi key compromise không?
- JWKS/metadata refresh có timeout, cache TTL và issuer allowlist không?
- Certificate expiry được giám sát trước khi hết hạn không?
- Protocol version có cơ chế loại bỏ phiên bản yếu không?
- Client/server có xử lý unknown critical parameter an toàn không?
- Có tương thích ngược nào vô tình bật lại flow cũ không?

Version negotiation là điểm dễ bị downgrade. Nếu client và server hỗ trợ nhiều version, phải xác định version tối thiểu, thuật toán được phép và cách từ chối version yếu. Không để attacker thay đổi negotiation message để ép hai bên dùng profile cũ.

## 17. Failure mode, retry và idempotency

Luồng authentication có thể timeout sau khi server đã tiêu thụ code, phát token hoặc tạo session. Review cần phân biệt:

- Request chưa đến server.
- Server chưa xử lý.
- Server đã xử lý nhưng response bị mất.
- Server trả response nhưng client không nhận được.
- Event revoke đã phát nhưng một số consumer chưa xử lý.

Kiểm tra:

- Timeout và deadline cho từng dependency.
- Retry có giới hạn, backoff và jitter.
- Authorization code, OTP và recovery code có one-time use nguyên tử không?
- Session/token creation có idempotency hoặc transaction state không?
- Revoke timeout có được xác nhận qua trạng thái hoặc reconciliation không?
- JWKS/cache stale window có giới hạn và không chấp nhận key chưa xác minh không?
- Dependency failure có tạo fail-open ngoài ý muốn không?

Không coi timeout là invalid credential hoặc thành công. Không retry vô hạn một operation có side effect. Không dùng dependency outage làm lý do bỏ qua authentication, MFA hoặc authorization.

## 18. Logging, privacy và evidence

Protocol cần tạo đủ dữ liệu để điều tra nhưng không biến log thành nơi chứa credential:

- Ghi request/correlation ID, issuer, client, resource, tenant và outcome theo policy.
- Ghi authentication method, assurance, factor event và session/token reference.
- Ghi decision, actor, subject và target resource cho hành động đặc quyền.
- Ghi key ID hoặc token ID tham chiếu nếu cần; không ghi token value.
- Không log password, OTP, recovery code, authorization code, refresh token, cookie hoặc private key.
- Hạn chế dữ liệu cá nhân, pseudonymize identifier khi có thể.
- Bảo vệ log integrity, access control, retention và time synchronization.
- Giữ thông tin lỗi chi tiết trong audit nội bộ; response công khai dùng thông báo phù hợp.

Review cũng nên xác định ai có thể đọc log, ai có thể thay đổi retention, và liệu admin có thể xóa dấu vết của chính hành động mình không.

## 19. Quy trình thực hiện protocol review

Một review thực tế có thể đi theo các bước:

1. **Chốt scope:** xác định protocol, version, client, issuer, resource, deployment và luồng cần review.
2. **Thu thập artifact:** specification, sequence diagram, sample request/response đã loại secret, configuration, threat model và error behavior.
3. **Liệt kê actor/asset/trust boundary:** xác định chủ thể, quyền kiểm soát và nơi chuyển giao trust.
4. **Vẽ message flow:** bao gồm happy path, failure path, retry, logout, recovery và key rotation.
5. **Xác minh cryptographic binding:** chữ ký, MAC, encryption, randomness, nonce, audience và channel binding.
6. **Kiểm tra protocol-specific rules:** OAuth/OIDC, SAML, WebAuthn, certificate hoặc custom protocol profile.
7. **Phân tích abuse case:** replay, mix-up, CSRF, redirect, downgrade, token leakage, enumeration và confused deputy.
8. **Đánh giá lifecycle:** token, session, factor, key, certificate, account linking và revocation.
9. **Đánh giá failure/availability:** timeout, partial failure, rate limit, retry storm và degraded mode.
10. **Kiểm tra audit/privacy:** log coverage, secret redaction, retention và incident evidence.
11. **Xác thực bằng test:** negative tests, integration tests, protocol conformance và security tests trong môi trường được phép.
12. **Ghi findings:** mô tả điều kiện, impact, evidence, severity, remediation, owner và trạng thái retest.

Review không kết thúc khi tìm được một lỗi đầu tiên. Cần rà soát các luồng liên quan và xác nhận remediation không mở ra downgrade hoặc regression mới.

## 20. Mẫu ghi nhận finding

Mỗi finding nên có:

| Trường | Nội dung |
| --- | --- |
| ID/title | Mã và tên ngắn gọn. |
| Affected flow | Login, token exchange, federation, MFA, recovery hoặc logout. |
| Preconditions | Điều kiện attacker cần có. |
| Observation | Message, claim, response hoặc hành vi thực tế. |
| Expected behavior | Yêu cầu protocol/security control đúng. |
| Impact | Confidentiality, integrity, authentication, authorization, privacy hoặc availability bị ảnh hưởng. |
| Severity | Mức độ theo risk methodology của tổ chức. |
| Evidence | Request/response đã redacted, trace, test case và timestamp. |
| Recommendation | Thay đổi cụ thể và lý do. |
| Owner/status | Người chịu trách nhiệm, deadline và kết quả retest. |

Ví dụ finding:

**Title:** Authorization code callback không ràng buộc với browser transaction.

**Observation:** Client nhận code nhưng không kiểm tra state với transaction đã lưu trước khi đổi code.

**Impact:** Attacker có thể tìm cách gắn callback của một phiên khác vào browser nạn nhân, gây login CSRF hoặc account confusion tùy luồng.

**Recommendation:** Sinh state ngẫu nhiên, lưu gắn với browser session, kiểm tra một lần ở callback và từ chối response không khớp. Dùng PKCE và kiểm tra issuer/redirect URI theo profile.

Finding phải mô tả điều đã quan sát; không khẳng định khai thác thành công nếu mới chỉ có giả thuyết.

## 21. Ví dụ: review OIDC Authorization Code Flow

Một ứng dụng web dùng OIDC để đăng nhập nhân viên qua IdP doanh nghiệp.

**Phạm vi:**

- Client là confidential web application.
- IdP là issuer đã được cấu hình.
- Callback là redirect URI cố định.
- Ứng dụng cần ID Token để tạo session và access token cho một API nội bộ.

**Các điểm review:**

1. Client tạo state, nonce và PKCE verifier bằng CSPRNG; lưu transaction state ở server và gắn với browser session.
2. Authorization request dùng response type/code, redirect URI khớp chính xác và PKCE S256.
3. Client xác minh issuer/authorization server đã chọn; không cho callback từ IdP khác dùng chung transaction.
4. Callback kiểm tra state, expiry và transaction chưa được tiêu thụ.
5. Token request gửi code, redirect URI, client authentication phù hợp và PKCE verifier.
6. Authorization server xác minh code chưa dùng, đúng client, redirect URI và PKCE challenge.
7. Client xác minh ID Token: signature, issuer, audience, authorized party khi cần, expiry, issued-at và nonce.
8. Client kiểm tra assurance/authentication time nếu policy yêu cầu MFA hoặc re-auth.
9. Client tạo session ID mới sau login, đặt cookie an toàn và không lưu token trong URL/browser storage không phù hợp.
10. Access token được dùng cho đúng API audience; API xác minh token và authorization độc lập.
11. Logout và account disable có cơ chế thu hồi session/token phù hợp với kiến trúc.
12. Error response không tiết lộ account state; log không chứa code, token hoặc cookie.

**Negative test cần có:**

- State thiếu, sai, hết hạn hoặc đã dùng.
- Nonce không khớp.
- PKCE verifier sai.
- Redirect URI khác registered URI.
- Issuer hoặc audience sai.
- ID Token hết hạn hoặc chữ ký không hợp lệ.
- Callback từ issuer khác với issuer của transaction.
- Authorization code được replay.
- Token có audience dành cho API khác.
- Session ID cũ được giữ lại sau authentication.

Kết quả review cần nêu rõ profile/standard version áp dụng, cấu hình client/IdP và những giả định chưa được xác minh.

## 22. Các lỗi protocol review thường gặp

| Lỗi review | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đọc happy path | Bỏ sót lỗi callback, timeout, retry và recovery. | Vẽ cả success, failure và lifecycle flow. |
| Chỉ kiểm tra thuật toán | Chữ ký mạnh vẫn có thể bị dùng sai audience hoặc transaction. | Review message binding, claims và receiver validation. |
| Tin token vì chữ ký hợp lệ | Token có thể sai issuer, audience, type hoặc hết hạn. | Kiểm tra toàn bộ claim/profile cần thiết. |
| Gộp state, nonce và PKCE thành một kiểm soát | Mỗi cơ chế có mục đích và điểm kiểm tra khác nhau. | Kiểm tra độc lập theo protocol. |
| Bỏ qua multi-issuer mix-up | Code/assertion có thể bị gửi tới sai issuer. | Gắn issuer với transaction và kiểm tra callback. |
| Không kiểm tra one-time use | Code, OTP hoặc assertion có thể replay. | Atomic consume, expiry và replay cache. |
| Bỏ qua account recovery | Đường yếu có thể vượt qua login mạnh. | Review recovery/factor enrollment như protocol đặc quyền. |
| Chỉ tin private network/header | Caller có thể giả mạo identity context. | Xác thực workload và bảo vệ context tại từng boundary. |
| Không review key lifecycle | Rotation/compromise làm hệ thống từ chối hoặc tin key sai. | Review publish, overlap, revoke và emergency procedure. |
| Bỏ qua error timing/privacy | Response có thể tạo account/factor enumeration. | Review body, status, headers, redirects và timing. |
| Không thử lỗi phân tán | Timeout có thể tạo session/token trùng hoặc revoke không chắc chắn. | Test unknown outcome, retry, idempotency và reconciliation. |
| Findings không có evidence | Khó ưu tiên, sửa và retest. | Ghi precondition, observation, impact và test evidence. |

## 23. Checklist protocol review

Trước khi phê duyệt một protocol hoặc thay đổi authentication, hãy kiểm tra:

1. Scope, protocol version, actor, asset và trust boundary đã được ghi rõ chưa?
2. Có message sequence cho happy path, failure path, retry, logout và recovery không?
3. Mỗi bên xác minh đúng peer, issuer, audience và protocol role không?
4. Signature/MAC/encryption dùng primitive, key và algorithm allowlist phù hợp không?
5. Randomness, nonce, state, challenge, timestamp và one-time use có đúng không?
6. Message có chống replay, mix-up, CSRF, redirect abuse và downgrade không?
7. Subject, actor, client, tenant, resource và scope có được phân biệt/ràng buộc không?
8. OAuth/OIDC có PKCE, state, nonce, redirect URI và token validation đúng profile không?
9. SAML assertion có signature coverage, audience, recipient, time condition và replay protection không?
10. WebAuthn có kiểm tra challenge, origin, RP ID, signature và user verification không?
11. MFA/factor enrollment/recovery có binding, rate limit và fallback policy phù hợp không?
12. Session/cookie/logout/revocation có lifecycle và anti-CSRF phù hợp không?
13. Key, certificate, metadata và protocol version có rotation, expiry và emergency revoke không?
14. Error response, timing, privacy và log redaction có được đánh giá không?
15. Timeout, retry, idempotency, partial failure và degraded mode có an toàn không?
16. Authorization có chống confused deputy, cross-tenant access và quyền vượt scope không?
17. Có negative tests, conformance tests và test cho race/replay không?
18. Findings có evidence, impact, owner, remediation và retest status không?

**Kết luận:** Protocol review phải đánh giá cách các bên trao đổi và xác minh message trong toàn bộ vòng đời authentication, từ khởi tạo request tới token, session, logout, recovery và key rotation. Hãy mô hình hóa actor/trust boundary, kiểm tra cryptographic binding, freshness, issuer/audience, replay, downgrade, error handling và authorization ở resource đích. Một thuật toán mạnh hoặc một chữ ký hợp lệ không đủ để chứng minh toàn giao thức an toàn; kết luận cần dựa trên message flow, cấu hình thực tế, negative tests và evidence có thể kiểm tra.
