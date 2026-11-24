# Token validation test

**Token validation test** là hoạt động kiểm thử xác minh một hệ thống chỉ chấp nhận token đúng nguồn phát hành, đúng đối tượng nhận, đúng thời hạn, đúng mục đích và đáp ứng chính sách mật mã trước khi sử dụng claims để tạo principal hoặc quyết định quyền. Một token có cấu trúc hợp lệ hoặc chữ ký đúng vẫn có thể không được chấp nhận nếu issuer, audience, token type, scope, trạng thái thu hồi hay proof-of-possession không phù hợp.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. Token là bằng chứng được phát hành trong một trust relationship; kiểm thử validation phải xác minh toàn bộ ranh giới đó từ issuer và key tới resource server, application và hành động được yêu cầu.

Điểm cốt lõi: **kiểm thử token phải chứng minh cả trường hợp hợp lệ được chấp nhận lẫn trường hợp không hợp lệ bị từ chối**. Chỉ kiểm thử một JWT có chữ ký đúng là chưa đủ. Cần kiểm tra sai chữ ký, sai thuật toán, sai issuer/audience, token hết hạn, key không tin cậy, token bị revoke, replay, parser edge cases và cách hệ thống xử lý khi dependency xác minh không khả dụng.

## 1. Mục tiêu và phạm vi của token validation test

Mục tiêu là xác minh validator và resource server thực thi đúng hợp đồng token. Bài kiểm thử cần trả lời:
- Token được phát hành bởi authority nào?
- Chữ ký hoặc bằng chứng token được xác minh bằng key/trust anchor nào?
- Token dành cho resource/client nào?
- Token có còn trong khoảng thời gian hợp lệ không?
- Token thuộc đúng profile và mục đích sử dụng không?
- Claims được parse và diễn giải nhất quán không?
- Quyền trong token có đủ cho resource/action không?
- Trạng thái revoke, session hoặc credential có được kiểm tra theo policy không?
- Khi JWKS, introspection hoặc network lỗi, hệ thống có giữ đúng security behavior không?
- Lỗi validation có bị lộ chi tiết nhạy cảm hoặc ghi token vào log không?

### 1.1. Validation khác authentication và authorization

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Token validation** | Token có đáng tin và được phép dùng trong context này không? | Kiểm tra signature, issuer, audience, expiry, token type. |
| **Authentication** | Token chứng minh principal nào theo protocol? | Xác định subject từ access token đã xác minh. |
| **Authorization** | Principal có được thực hiện hành động trên resource này không? | Scope không đủ hoặc resource thuộc tenant khác. |
| **Session management** | Trạng thái truy cập được duy trì và thu hồi thế nào? | Logout, idle timeout, refresh rotation, revoke. |

Một token hợp lệ không có nghĩa người dùng được phép truy cập mọi resource. Ngược lại, authorization không được chạy trên claims từ token chưa được validate.

### 1.2. Phạm vi token

Bài viết tập trung vào JWT access token ký bằng JWS, opaque/reference access token được xác minh qua introspection, OIDC ID Token trong luồng đăng nhập, token có sender constraint như DPoP hoặc mTLS-bound token, refresh token và token family ở mức lifecycle/revocation, claims/scopes/roles và token validation trong gateway, API, service, federation.

Không phải mọi token đều là JWT. Không được áp dụng parser hoặc quy tắc JWT cho opaque token, API key, SAML assertion hay certificate.

## 2. Xác định token profile trước khi viết test

Validator phải biết token thuộc profile nào. Cùng một chuỗi JWT có thể mang ý nghĩa khác nhau trong các protocol hoặc service.

### 2.1. Access token và ID Token

| Thuộc tính | Access token | OIDC ID Token |
| --- | --- | --- |
| Mục đích | Cấp quyền truy cập resource server. | Truyền kết quả authentication tới OIDC client. |
| Audience | Resource/API được phép nhận token. | OIDC client ID. |
| Consumer | Resource server. | OIDC relying party/client. |
| Claims | Scope, client, subject, resource context theo profile. | Issuer, subject, audience, auth time, nonce và claims identity. |
| Dùng thay nhau? | Không. | Không gửi ID Token tới API thay access token. |

Test phải xác minh API từ chối ID Token khi endpoint yêu cầu access token. Kiểm tra chữ ký đúng mà không kiểm tra token purpose có thể cho phép token substitution.

### 2.2. JWT và opaque token

JWT thường chứa header và claims được serialize, ký hoặc mã hóa. Opaque token thường là reference không thể diễn giải đáng tin ở client; resource server gọi introspection hoặc dùng cơ chế đã thỏa thuận.

Test suite cần tách hai đường:
- JWT: parse có giới hạn, kiểm tra profile, thuật toán, key, signature và claims.
- Opaque: introspection, active state, audience/resource, scope, expiry và failure behavior.

Không cố giải mã opaque token hoặc coi chuỗi có dấu chấm là bằng chứng JWT hợp lệ.

### 2.3. Viết validation contract

Trước khi viết test, ghi rõ issuer allowlist, audience/resource identifier, token type/profile, thuật toán ký được phép, nguồn key và quy trình rotation, required claims và semantics, clock skew, scope/role mapping, revocation/introspection policy và sender constraint nếu có.

Contract là tiêu chuẩn để tạo expected result. Không suy đoán profile từ một token sample đơn lẻ.

## 3. JWT validation pipeline cần kiểm thử

Một pipeline tham khảo:

    Receive token
       |
       v
    Enforce size and syntax limits
       |
       v
    Parse protected header safely
       |
       v
    Select trusted issuer and key source
       |
       v
    Enforce algorithm allowlist
       |
       v
    Verify cryptographic signature
       |
       v
    Validate issuer, audience and token profile
       |
       v
    Validate time and required claims
       |
       v
    Check revocation / sender constraint if required
       |
       v
    Build principal and continue authorization

Thứ tự và cách tổ chức nội bộ có thể khác, nhưng không được sử dụng claims để ra quyết định tin cậy trước khi signature và profile validation hoàn tất.

### 3.1. Header không đáng tin trước khi verify

JWT header là input do bên gửi cung cấp. Trước khi signature được xác minh, không tin các trường **alg**, **kid**, **jku**, **x5u**, **crit** hoặc bất kỳ giá trị nào để thay đổi trust configuration.

**kid** có thể được dùng như một chỉ mục tìm key trong JWKS đã được cấu hình tin cậy. Nó không phải URL, không phải đường dẫn file và không được nối trực tiếp vào query tùy ý.

### 3.2. Claims không đáng tin trước khi verify

Không dùng **sub**, **role**, **scope**, **tenant**, **email** hoặc **is_admin** để cấp quyền trước khi xác minh chữ ký và profile. Token unsigned hoặc signature invalid không thể tạo principal đáng tin.

## 4. Kiểm thử chữ ký và thuật toán

### 4.1. Signature hợp lệ

Positive test cần chứng minh:
- Token được ký bằng private key test tương ứng với public key trong trusted JWKS.
- Validator chọn đúng key theo **kid** hoặc profile.
- Chữ ký được xác minh trên đúng signing input.
- Token chỉ được chấp nhận với thuật toán được cấu hình.
- Principal và claims sau validation khớp fixture mong đợi.

Dùng key test riêng, không dùng private key production hoặc token thật của người dùng.

### 4.2. Signature không hợp lệ

Negative test nên gồm:
- Thay đổi một byte trong payload sau khi ký.
- Thay đổi header mà không ký lại.
- Thay đổi signature.
- Dùng public key khác.
- Dùng token ký bởi issuer khác.
- Token bị cắt hoặc segment rỗng.
- Signature encoding không hợp lệ.
- Key type không tương thích với thuật toán.
- Token có **kid** không tồn tại.

Mỗi trường hợp phải bị từ chối và không được tạo authenticated principal.

### 4.3. Algorithm confusion

Validator phải có allowlist thuật toán theo trust configuration. Test tối thiểu:
- Từ chối **alg: none**.
- Từ chối thuật toán ngoài allowlist.
- Không chấp nhận HS256 khi profile chỉ cho RS256/ES256.
- Không diễn giải public key RSA như HMAC secret.
- Không cho header tự chọn thuật toán không tương thích với key type.
- Kiểm tra cấu hình key rotation không vô tình mở rộng allowlist.

Không chọn thuật toán chỉ từ token header. Header là untrusted input; cấu hình verifier quyết định thuật toán được phép.

### 4.4. Key type và curve

Với RSA, EC hoặc OKP, kiểm tra key type tương ứng thuật toán, RSA modulus/key size đạt policy, EC curve được hỗ trợ và đúng profile, key material có format hợp lệ, key không bị dùng sai mục đích và public key không có duplicate/conflicting metadata gây chọn sai.

Không chỉ kiểm thử thuật toán thành công; cần kiểm tra key yếu, key malformed và key type mismatch bị từ chối.

## 5. Issuer, audience và token purpose

### 5.1. Issuer (iss)

Test:
- Issuer đúng và khớp chính xác cấu hình.
- Issuer khác một ký tự.
- Issuer dùng scheme/host/path khác.
- Issuer không có trong allowlist.
- Issuer từ tenant khác.
- Issuer bị thay đổi nhưng token được ký bởi key không thuộc authority đó.

Không chuẩn hóa issuer tùy tiện để hai URL khác nhau trở thành cùng một authority. Mapping issuer phải rõ và chính xác theo trust configuration.

### 5.2. Audience (aud)

Test:
- Audience đúng resource server.
- Audience chỉ dành cho client khác.
- Audience thiếu.
- Audience sai kiểu dữ liệu.
- Audience là array có và không có expected value.
- Token có nhiều audience theo profile.
- Token dành cho API A được gửi tới API B.

Resource server phải kiểm tra audience của chính nó. Chữ ký hợp lệ không cho phép sử dụng token ở mọi API.

### 5.3. Authorized party và client context

Với profile có **azp**, **client_id** hoặc client context, kiểm tra semantics đúng protocol:
- Client được phép nhận token.
- **azp** phù hợp khi ID Token có nhiều audience theo OIDC rules.
- Không dùng client ID thay audience resource.
- Không lấy client context từ header do caller tự khai.
- Tenant/client mapping không bị nhầm giữa môi trường.

### 5.4. Token type và substitution

Kiểm tra:
- Access token được chấp nhận ở API đúng profile.
- ID Token bị từ chối ở resource endpoint.
- Refresh token không được dùng như access token.
- Token dành cho một protocol không được tái sử dụng ở protocol khác.
- **typ** hoặc profile marker được kiểm tra khi profile yêu cầu.
- JWT có cấu trúc hợp lệ nhưng sai purpose vẫn bị reject.

Với JWT access token theo profile cụ thể, kiểm tra type marker theo contract, ví dụ **at+jwt** khi áp dụng RFC 9068. Không áp đặt marker này cho mọi JWT không dùng profile đó.

## 6. Kiểm thử thời gian và claims bắt buộc

### 6.1. exp, nbf, iat

Các test thời gian:
- Token còn hạn.
- Token vừa hết hạn.
- Token hết hạn quá xa.
- **nbf** ở tương lai.
- **iat** ở tương lai ngoài clock skew.
- Thiếu **exp** khi profile yêu cầu.
- **exp**, **nbf**, **iat** sai kiểu dữ liệu.
- Thời gian âm, tràn số hoặc định dạng không hợp lệ.
- Token có lifetime vượt policy.
- Boundary đúng tại thời điểm hết hạn.

Dùng clock có thể điều khiển trong test thay vì chờ thời gian thực.

### 6.2. Clock skew

Một khoảng clock skew nhỏ có thể cần cho máy chủ có sai lệch thời gian. Test token nằm trong skew cho phép, token vượt skew, verifier clock bị lệch tiến/lùi, node trong cluster có clock không đồng bộ, NTP/clock source lỗi và token expiry ở sát boundary.

Không đặt skew quá rộng để che lỗi đồng bộ clock hoặc kéo dài token lifetime ngoài policy.

### 6.3. Required claims và claim type

Kiểm tra các claim bắt buộc theo profile:
- **iss**, **sub**, **aud**, **exp**, **iat**.
- **jti** nếu hệ thống dùng identifier hoặc replay tracking.
- **scope**/**scp** theo access token contract.
- **client_id**, **azp**, **auth_time**, **acr**, **amr**, **nonce** khi protocol yêu cầu.
- **cnf** khi token sender-constrained.

Test claim thiếu, null, sai kiểu, rỗng, quá dài, duplicate hoặc cấu trúc lồng sâu bất thường. Parser và validator phải có semantics nhất quán; không âm thầm chuyển kiểu để chấp nhận input sai.

### 6.4. Subject và identity mapping

**sub** chỉ có ý nghĩa trong issuer namespace. Test:
- Cùng **sub** từ hai issuer khác nhau phải là hai identity khác nhau nếu mapping không nói khác.
- Không merge account chỉ vì email trùng.
- Subject thiếu hoặc không hợp lệ bị xử lý theo profile.
- Tenant/resource mapping khớp issuer và audience.
- Claim email chưa verified không được dùng làm proof of ownership nếu policy yêu cầu verified email.

Principal nên được định danh theo cặp issuer-subject hoặc mapping ổn định đã được xác minh, không dựa riêng vào display name/email.

## 7. Scope, role và authorization claims

Token validation và authorization liên quan nhưng là hai bước riêng. Test cần chứng minh validator không biến claim bất kỳ thành quyền.

### 7.1. Scope

- Scope đủ cho endpoint.
- Scope thiếu.
- Scope chỉ có quyền đọc nhưng request yêu cầu ghi.
- Scope sai format hoặc duplicate.
- Scope thuộc resource khác.
- Scope bị parser diễn giải không nhất quán.
- Scope được cấp rộng hơn policy dự kiến.

API phải từ chối action không có quyền, thường trả lỗi authorization thích hợp sau khi token đã validate.

### 7.2. Role và group claims

Test role hợp lệ trong issuer/tenant đúng, role từ tenant khác, role claim do client tự thêm vào token giả, role name sai case nếu contract phân biệt, group list quá lớn hoặc bị truncate, role đã bị thu hồi nhưng token cũ còn chứa claim và mapping role-to-permission thay đổi.

Token có thể phản ánh snapshot quyền tại thời điểm phát hành. Với quyền nhạy cảm, cần authorization freshness/version check hoặc server-side policy thay vì tin role cũ vô thời hạn.

### 7.3. Tenant isolation

Dùng hai tenant fixture:
- Token tenant A truy cập resource A: theo policy cho phép.
- Token tenant A truy cập resource B: từ chối.
- Subject trùng nhưng issuer/tenant khác: không nhầm principal.
- Header tenant do client gửi không được ghi đè tenant đã xác minh trong token.
- Query/database lookup phải ràng buộc tenant từ trusted principal.

## 8. JWKS và key rotation tests

### 8.1. Trusted JWKS source

Test JWKS lấy từ issuer đã cấu hình, TLS/hostname validation hoạt động, không theo **jku**/**x5u** do token tự cung cấp nếu profile không cho phép rõ ràng, không cho token chỉ định URL tùy ý để fetch key, **kid** được tra trong trusted key set, JWKS response malformed hoặc quá lớn bị từ chối an toàn và key trùng **kid** hoặc metadata mâu thuẫn được xử lý theo policy an toàn.

Không fetch key từ URL tùy ý trong token vì có thể tạo SSRF, trust substitution hoặc đưa attacker-controlled key vào validator.

### 8.2. Rotation bình thường

Test kịch bản:
1. JWKS có key K1.
2. Token ký bằng K1 được chấp nhận.
3. Issuer công bố K2 cùng thời gian overlap.
4. Token K2 được chấp nhận sau khi verifier cập nhật key.
5. Token K1 được xử lý theo rotation policy trong thời gian overlap.
6. K1 bị retire; token K1 cũ bị từ chối sau giới hạn policy.
7. Cache refresh và propagation giữa replica được xác minh.

Test cả cold start và warm cache. Không chỉ kiểm thử một instance.

### 8.3. Unknown kid và endpoint outage

- Token có **kid** mới kích hoạt refresh có giới hạn.
- JWKS endpoint timeout không làm verifier chấp nhận token.
- Retry có backoff, không tạo request storm.
- Unknown **kid** sau refresh vẫn bị reject.
- Cache quá hạn xử lý theo stale policy.
- Emergency key revocation có thể invalidate cache.
- Cache không bị giữ vô thời hạn do refresh lỗi.

### 8.4. Key compromise

Giả lập key bị compromise:
- Emergency deny/revoke key được phân phối.
- Mọi verifier nhận trạng thái trong thời gian mục tiêu.
- Token ký bởi key bị thu hồi bị từ chối.
- Cache cũ không ghi đè emergency deny.
- Incident log/audit ghi nhận hành động mà không chứa private key.
- Quy trình rotate sang key mới hoạt động.

## 9. Opaque token và introspection tests

### 9.1. Positive introspection

Kiểm tra response **active** đúng, issuer/resource/audience, scope, client, subject và expiry theo contract. Resource server chỉ tạo principal từ response đã xác thực và gắn với đúng token/request.

### 9.2. Negative introspection

Test:
- **active: false**.
- Token không tồn tại.
- Token hết hạn.
- Token bị revoke.
- Response thiếu field bắt buộc.
- Response sai kiểu hoặc malformed.
- Introspection endpoint trả 401/403/5xx.
- Timeout, DNS/TLS failure.
- Response đến sau request timeout.
- Response từ issuer không tin cậy.

Không biến timeout thành **active: true**. Không sử dụng response cũ vượt stale window được phê duyệt.

### 9.3. Introspection cache

Kiểm thử positive cache trong TTL, negative cache theo policy, cache hết hạn, revoke event invalidates cache, stale-if-error trong giới hạn, cache key không log raw bearer token và concurrent miss không gây request storm.

Với action nhạy cảm, cache TTL có thể cần ngắn hơn hoặc bỏ qua cache. Test phải phản ánh policy theo resource.

## 10. Revocation, replay và token lifecycle

### 10.1. Revocation

Test:
- Token/session bị revoke trước request.
- Revoke event được truyền tới verifier.
- Token family bị revoke sau refresh token reuse.
- Logout revoke session theo contract.
- Account disabled hoặc authenticator compromise kích hoạt policy tương ứng.
- JWT offline validation có giới hạn revocation window đã biết.
- Revoke propagation delay được đo.

Revoke refresh token không nhất thiết làm access JWT đã phát hành mất hiệu lực ngay. Test phải xác minh kiến trúc thực tế: introspection, denylist, session version, token epoch hoặc expiry.

### 10.2. Replay

Token bearer có thể được replay bởi bất kỳ bên nào lấy được token trong thời gian token còn hiệu lực. Test:
- Dùng lại token ở request khác trong cùng audience theo semantics bearer.
- Dùng token ở audience khác.
- Dùng one-time token/authorization code lần thứ hai.
- Dùng **jti** đã consume nếu hệ thống có replay store.
- Gửi request trùng do retry.
- Replay proof-of-possession với nonce cũ.

Không giả định **jti** tự chống replay. Chỉ khi verifier lưu và kiểm tra trạng thái sử dụng một lần hoặc có cơ chế tương đương thì mới có replay protection.

### 10.3. DPoP và mTLS-bound token

Nếu token có sender constraint:
- Proof signature khớp public key được token bind.
- **htu**/**htm** khớp URL/method theo protocol.
- **iat** nằm trong cửa sổ hợp lệ.
- **jti** proof không bị replay theo replay cache.
- Nonce được kiểm tra khi yêu cầu.
- **ath** gắn đúng access token nếu profile yêu cầu.
- Key thumbprint khớp claim **cnf**.
- mTLS certificate đúng binding và trust chain.

Test proof sai key, sai URL/method, proof cũ, nonce sai, certificate khác và token không có binding. Không coi token sender-constrained là hợp lệ nếu proof bị thiếu hoặc sai khi policy yêu cầu.

## 11. Token parser và malformed input

Parser là bề mặt tấn công. Test phải giới hạn kích thước và tránh parser differential giữa gateway và backend.

### 11.1. Cấu trúc JWT

Test:
- Thiếu segment hoặc có quá nhiều segment.
- Base64url malformed.
- Header/payload rỗng hoặc quá lớn.
- JSON không hợp lệ.
- JSON có duplicate claim name.
- Claim có kiểu dữ liệu không mong đợi.
- Nested object/array quá sâu.
- Unicode edge cases.
- Padding hoặc encoding không đúng profile.
- Signature có độ dài sai.

### 11.2. Header đặc biệt

Test **crit**, **b64**, **cty**, **typ**, **kid** và các extension theo profile:
- Extension không hỗ trợ phải bị từ chối nếu được đánh dấu critical.
- Không bỏ qua **crit** mà validator không hiểu.
- Không tự giải nén hoặc xử lý nested token ngoài policy.
- Không chấp nhận header mâu thuẫn giữa các parser.
- Không tin key URL hoặc certificate URL không được cấu hình.

### 11.3. Parser differential

Nếu gateway và backend dùng thư viện khác nhau, cùng một token có thể được diễn giải khác. Test end-to-end đảm bảo cùng issuer/audience, duplicate claim handling, algorithm allowlist, time semantics và scope/role interpretation.

Ưu tiên một thư viện validation chuẩn hóa hoặc chia sẻ contract test giữa các thành phần.

## 12. Test error handling và side effects

Một token bị từ chối phải dừng trước khi tạo side effect.

Kiểm tra:
- Không tạo session hoặc principal cho token invalid.
- Không ghi audit event giả rằng authentication thành công.
- Không thực hiện database write trước khi validation hoàn tất.
- Không gửi notification hoặc job với subject chưa xác minh.
- Không leak stack trace, key ID nội bộ hoặc chi tiết parser cho caller.
- Error response không tiết lộ token có tồn tại hay account cụ thể nếu điều đó tạo enumeration risk.
- Log có reason code an toàn nhưng không có raw token/header.
- Retry không biến token invalid thành accepted.

Phân biệt lỗi nội bộ và response bên ngoài. Có thể log reason chi tiết cho operator có phân quyền trong khi client nhận lỗi chuẩn hóa.

### 12.1. Error taxonomy

Một taxonomy tham khảo:
- malformed_token
- invalid_signature
- unsupported_algorithm
- unknown_key
- invalid_issuer
- invalid_audience
- expired_token
- not_yet_valid
- invalid_token_type
- insufficient_scope
- revoked_token
- introspection_unavailable
- proof_invalid
- replay_detected

Reason code phải là enum hữu hạn. Không thêm raw claim, token hoặc user input vào label/log.

## 13. Test fixtures và cách tạo token an toàn

### 13.1. Fixture theo mục đích

Tạo fixture rõ ràng:
- Valid access token cho API A.
- Valid ID Token cho client B.
- Token issuer không tin cậy.
- Token sai audience.
- Token expired và not-yet-valid.
- Token ký sai key/algorithm.
- Token có unknown kid.
- Token revoked.
- Token thiếu scope.
- Token sender-constrained có proof hợp lệ/sai.
- Opaque token active/inactive.

Mỗi fixture có expected outcome và lý do. Không dùng một token test duy nhất rồi sửa thủ công ngẫu nhiên để đại diện mọi case.

### 13.2. Test key

- Dùng private key sinh riêng cho test.
- Không commit production key, secret hoặc token.
- Có thể tạo key fixture ephemeral trong test setup.
- Không dùng key test ở production configuration.
- Đặt key size/curve đủ phù hợp để test thư viện thực tế.
- Xóa fixture private key sau khi test nếu được tạo trong runtime.
- Nếu dùng static fixture, chỉ dùng dữ liệu giả và repository test-only.

### 13.3. Token builder

Một token builder test nên cho phép cấu hình header, claims, key, algorithm và clock để tạo cả token hợp lệ lẫn token sai có chủ đích. Builder không được xuất hiện trong production path.

Tránh dùng thư viện test builder để ký token bằng key yếu rồi vô tình reuse trong integration/staging. Tách namespace, configuration và secret store của test.

## 14. Unit, integration, contract và end-to-end tests

### 14.1. Unit test

Kiểm tra validator độc lập: signature and algorithm, issuer/audience/time/profile, required claims and type, scope/role mapping, parser limits, error taxonomy và clock skew.

Unit test nhanh và xác định nhưng không đủ để chứng minh JWKS, introspection, TLS hoặc gateway wiring đúng.

### 14.2. Integration test

Kết nối validator với test issuer/JWKS endpoint, test introspection endpoint, session/revocation store, API gateway hoặc middleware, clock provider, cache và key refresh worker.

Giả lập timeout, 5xx, malformed JWKS, key rotation và revoke event delay.

### 14.3. Contract test

Issuer và resource server cần thống nhất token profile, required claims, audience, algorithm/key metadata, scope semantics, expiry/skew, error responses và rotation/revocation behavior.

Contract test giúp phát hiện issuer thay đổi claim hoặc algorithm làm verifier hỏng. Không tự động nới validation để “fix” token mới mà chưa review trust contract.

### 14.4. End-to-end test

Thực hiện flow thực:
1. User/client xác thực với test IdP.
2. IdP phát token theo profile.
3. Client gửi token tới resource API.
4. API validate và tạo principal.
5. Authorization kiểm tra quyền.
6. Revoke hoặc expire token/session.
7. Request tiếp theo bị từ chối đúng policy.

Test login thành công không đủ; phải test sau logout, revoke, account disable và key rotation.

## 15. Property-based, fuzz và mutation testing

### 15.1. Property-based testing

Các property hữu ích:
- Token sai chữ ký không bao giờ tạo principal.
- Token sai issuer/audience không được chấp nhận.
- Token hết hạn ngoài skew không được chấp nhận.
- Thay đổi payload mà không ký lại làm validation thất bại.
- Token type sai không được dùng ở endpoint khác profile.
- Token có scope thiếu không thực hiện action cần scope đó.
- Cùng fixture và clock cho kết quả xác định.
- Validation failure không gây side effect.

Sinh nhiều biến thể claim/header trong giới hạn kích thước. Ghi seed để tái hiện lỗi.

### 15.2. Fuzzing

Fuzz parser/header/payload/base64url/JSON/JWKS và introspection response:
- Kích thước cực lớn.
- Nested JSON sâu.
- Unicode/invalid UTF-8.
- Duplicate fields.
- Numeric overflow.
- Array/object thay scalar.
- Segment bị cắt.
- Key metadata mâu thuẫn.

Mục tiêu là không crash, không treo, không tiêu thụ tài nguyên không giới hạn và không chấp nhận token sai. Fuzz trong môi trường cô lập với synthetic data.

### 15.3. Mutation testing

Có thể sửa có chủ đích validator trong test branch:
- Bỏ kiểm tra audience.
- Bỏ kiểm tra expiry.
- Chấp nhận alg none.
- Bỏ signature verification.
- Bỏ scope check.
- Bỏ revoke lookup.

Test suite tốt phải thất bại khi các kiểm tra trọng yếu bị loại bỏ. Mutation testing giúp phát hiện test chỉ chạy code nhưng không thực sự bảo vệ invariant.

## 16. Clock, concurrency và distributed behavior

Token validation trong hệ thống phân tán chịu ảnh hưởng của clock drift, cache và race.

### 16.1. Clock control

Inject clock abstraction vào validator. Test boundary trước/sau exp, nbf và skew, node clock drift, clock adjustment theo platform, token issue time từ issuer lệch verifier và clock source unavailable.

Không phụ thuộc sleep dài trong unit test; dùng fixed/mutable clock để kiểm soát thời gian.

### 16.2. Concurrency

Test:
- Nhiều request cùng validate một token trong lúc JWKS refresh.
- Cache miss đồng thời chỉ tạo số fetch giới hạn.
- Revocation xảy ra trong lúc request đang validate.
- Refresh token rotation đồng thời từ nhiều client.
- Replay store atomic khi hai request dùng cùng proof.
- Cache invalidation không bị ghi đè bởi response cũ.
- Request cũ không phục hồi principal/session sau logout.

Cần định nghĩa linearization point hoặc consistency guarantee cho revoke/one-time consume. Không giả định eventual cache invalidation là tức thời.

### 16.3. Cluster và multi-region

Chạy contract/integration test qua nhiều verifier:
- Tất cả node dùng cùng issuer/audience policy.
- Key rotation được propagate.
- Emergency key revoke không bị node cũ bỏ qua.
- Revocation state có độ trễ trong giới hạn.
- Clock và cache age được quan sát.
- Failover không đổi issuer trust hoặc audience.
- Region partition không tạo đường fail-open.

## 17. Performance, reliability và dependency failure tests

### 17.1. Performance

Đo signature verification throughput, JWT parse/validation latency, JWKS cache hit/miss, introspection latency và concurrency, revocation lookup cost, memory allocation/GC pressure, token size impact và p50/p95/p99.

Dùng token size và key type gần với production profile nhưng fixture giả. Kiểm tra input quá lớn bị từ chối trước khi gây CPU/memory exhaustion.

### 17.2. Dependency failure

Test JWKS timeout/5xx, introspection timeout/5xx, DNS failure, TLS certificate invalid, cache backend unavailable, revocation store unavailable, clock source unhealthy và network partition giữa verifier với issuer.

Kết quả phải theo policy: không biến lỗi dependency thành xác thực thành công. Có thể tiếp tục bằng cache còn hợp lệ cho resource được cho phép; nếu không đủ bằng chứng thì fail closed.

### 17.3. Resource exhaustion

Test token cực lớn, JSON lồng sâu, nhiều request với unknown kid, nhiều token invalid trong burst, introspection storm, JWKS refresh storm và replay cache tăng bất thường.

Giới hạn size, concurrency, rate và memory. Alert theo bounded reason code và không log payload.

## 18. Ma trận kiểm thử token validation

| Nhóm | Test case | Kết quả mong đợi |
| --- | --- | --- |
| Signature | Chữ ký đúng với trusted key | Accept nếu mọi policy khác đúng. |
| Signature | Payload/header/signature bị sửa | Reject, không tạo principal. |
| Algorithm | alg none hoặc thuật toán ngoài allowlist | Reject. |
| Key | Unknown kid | Refresh bounded; vẫn unknown thì reject. |
| Issuer | iss khác allowlist | Reject. |
| Audience | aud không chứa resource hiện tại | Reject. |
| Purpose | ID Token gửi tới API access-token endpoint | Reject. |
| Time | exp đã qua ngoài skew | Reject. |
| Time | nbf ở tương lai ngoài skew | Reject. |
| Claims | Thiếu claim bắt buộc/sai type | Reject theo profile. |
| Scope | Scope thiếu cho action | Token có thể valid nhưng action bị deny. |
| Tenant | Token tenant A truy cập tenant B | Deny. |
| JWKS | Endpoint timeout, cache hợp lệ | Chỉ tiếp tục theo stale/freshness policy. |
| JWKS | Key bị emergency revoke | Reject trên mọi verifier theo propagation target. |
| Introspection | active false | Reject. |
| Introspection | Timeout không có cache hợp lệ | Fail closed. |
| Replay | One-time code/proof được dùng lại | Reject duplicate. |
| DPoP/mTLS | Proof/certificate không khớp binding | Reject. |
| Revocation | Session/token đã revoke | Reject theo enforcement contract. |
| Parser | Segment/JSON/base64url malformed | Reject an toàn, không crash. |
| Logging | Validation error | Không ghi raw token hoặc secret. |
| Side effect | Token invalid | Không tạo session, job hoặc write. |
| Concurrency | Revoke và request đồng thời | Kết quả tuân theo consistency guarantee đã định. |
| Performance | Burst token invalid/unknown kid | Bị giới hạn, không gây exhaustion. |

## 19. Tình huống thực hành: JWT có chữ ký đúng nhưng sai audience

**Bối cảnh:** Một tổ chức có hai API: Billing API và Profile API. Authorization server phát JWT access token dành cho Billing API. Một client gửi token đó tới Profile API. Chữ ký token hợp lệ, issuer nằm trong allowlist chung và token chưa hết hạn. Profile API chỉ kiểm tra signature và expiry nên chấp nhận request.

**Phân tích:**

1. Chữ ký đúng chứng minh token được ký bởi key tương ứng, không chứng minh token dành cho Profile API.
2. Issuer đúng không có nghĩa mọi resource server đều là audience hợp lệ.
3. Nếu Profile API dùng claims từ token, token có thể được dùng ngoài intended resource.
4. Đây là lỗi audience validation và có thể trở thành token substitution/confused deputy.

**Cách kiểm thử và sửa:**

- Tạo token fixture có aud chỉ chứa Billing API.
- Gửi token tới Billing API: accept nếu các điều kiện khác đúng.
- Gửi cùng token tới Profile API: reject.
- Tạo token aud chứa Profile API theo contract và kiểm tra accept.
- Kiểm tra multi-audience behavior theo profile, không dùng substring match.
- Xác minh middleware kiểm tra audience trước khi tạo principal.
- Thêm integration test tại gateway và backend để tránh một tầng bỏ sót.
- Log reason invalid_audience, không ghi raw token.
- Thêm regression test để ngăn thay đổi cấu hình bỏ audience check.

**Câu hỏi:** Nếu hai API cùng trust một issuer thì có thể bỏ audience check không? Không. Trust issuer chỉ xác nhận nguồn phát hành; audience ràng buộc token với resource dự kiến.

## 20. Checklist xây dựng token validation test suite

- [ ] Viết validation contract cho từng issuer, audience, token type và resource.
- [ ] Phân biệt access token, ID Token, refresh token và opaque token.
- [ ] Kiểm thử positive path bằng key và fixture test riêng.
- [ ] Kiểm thử signature invalid, malformed token và key mismatch.
- [ ] Enforce algorithm allowlist; từ chối none và algorithm confusion.
- [ ] Kiểm tra issuer chính xác và audience của resource server.
- [ ] Kiểm tra token purpose/type và không dùng ID Token thay access token.
- [ ] Kiểm tra exp, nbf, iat, clock skew và lifetime.
- [ ] Kiểm tra required claims, type, duplicate field và claim size.
- [ ] Kiểm tra subject mapping theo issuer và tenant isolation.
- [ ] Kiểm tra scope/role ở bước authorization riêng.
- [ ] Kiểm thử JWKS trusted source, unknown kid, cache, rotation và emergency revoke.
- [ ] Kiểm thử introspection active/inactive, timeout, malformed response và cache.
- [ ] Kiểm tra revocation, logout, account disable và token family behavior.
- [ ] Kiểm thử replay và sender constraint DPoP/mTLS nếu được sử dụng.
- [ ] Fuzz parser, header, payload, JSON, base64url và JWKS.
- [ ] Kiểm thử không side effect khi token invalid.
- [ ] Kiểm tra error response/log không làm lộ token, key hoặc identity.
- [ ] Dùng controllable clock và test concurrency/cache invalidation.
- [ ] Chạy contract/integration test trên gateway, API và nhiều verifier.
- [ ] Kiểm tra dependency failure không tạo fail-open.
- [ ] Đo latency, throughput, allocation và khả năng chống resource exhaustion.
- [ ] Dùng synthetic token/account; không commit hoặc log credential production.
- [ ] Dùng mutation test để xác nhận suite bắt được khi bỏ signature/audience/expiry/scope checks.
- [ ] Gắn test với CI và review mọi thay đổi issuer/profile/key policy.

## 21. Câu hỏi tự kiểm tra

**1. Token validation test nhằm xác minh điều gì?**  
Xác minh token đúng nguồn, đúng key, đúng audience, purpose, thời hạn, claims và trạng thái theo trust policy trước khi tạo principal.

**2. Chữ ký JWT hợp lệ có đủ để chấp nhận token không?**  
Không. Còn phải kiểm tra issuer, audience, token type, thời gian, claims bắt buộc, revocation và sender constraint nếu có.

**3. Vì sao API phải kiểm tra audience?**  
Để token dành cho resource A không bị sử dụng ở resource B chỉ vì cả hai cùng trust một issuer.

**4. ID Token có thể dùng làm access token không?**  
Không. ID Token dành cho OIDC client; access token dành cho resource server và phải được validate theo profile tương ứng.

**5. Có thể tin kid hoặc jku từ header không?**  
Không. Header là input chưa được xác minh. kid chỉ được tra trong key set từ issuer đã cấu hình; URL tùy ý có thể gây SSRF và trust substitution.

**6. Khi JWKS endpoint lỗi, unknown kid có được chấp nhận không?**  
Không. Nếu không có public key tin cậy để verify signature, token phải bị từ chối.

**7. Introspection timeout có nghĩa token active không?**  
Không. Timeout là không có kết quả xác minh; chỉ cache còn hiệu lực theo policy mới có thể được dùng.

**8. jti tự chống replay được không?**  
Không. Validator phải lưu/kiểm tra trạng thái sử dụng một lần hoặc dùng cơ chế replay protection tương đương.

**9. Revoke refresh token có làm JWT access token cũ mất hiệu lực tức thì không?**  
Không nhất thiết. Cần introspection, denylist, version/epoch check hoặc expiry ngắn để giới hạn cửa sổ.

**10. Vì sao cần negative test và mutation test?**  
Negative test chứng minh input sai bị từ chối; mutation test chứng minh suite thất bại nếu một kiểm tra bảo mật trọng yếu bị loại bỏ.

**Ghi nhớ:** Token validation là ranh giới trust giữa issuer và resource server. Test suite phải kiểm tra chữ ký cùng issuer, audience, token type, thời gian, claims, scope, key lifecycle, revocation và replay. Hãy dùng fixture/key test, clock có thể điều khiển, test âm, fuzz và integration test; không cho token invalid tạo principal hoặc side effect, và không để dependency outage biến thành fail-open.
