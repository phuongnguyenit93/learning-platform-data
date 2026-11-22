# Test authentication, token và key rotation

Authentication, token và key rotation là một chuỗi kiểm soát liên quan trực tiếp đến việc API xác định caller, giới hạn quyền và thu hồi credential khi cần. Một endpoint có thể kiểm tra JWT đúng ở trường hợp bình thường nhưng vẫn chấp nhận token sai audience, token đã hết hạn do clock skew, ID token thay cho access token hoặc token được ký bằng key đã bị thu hồi. Tương tự, key rotation có thể làm API ngừng xác thực người dùng hợp lệ nếu public key mới chưa được phân phối, hoặc tiếp tục chấp nhận token giả mạo nếu public key cũ bị giữ quá lâu sau khi private key bị lộ.

Kiểm thử cần bao phủ toàn bộ vòng đời: cấp credential, xác minh, sử dụng, refresh, hết hạn, thu hồi, xoay vòng key và xử lý sự cố. Mục tiêu là chứng minh hệ thống chỉ chấp nhận credential đúng nguồn, đúng mục đích, đúng thời hạn và đúng phạm vi; đồng thời có thể chuyển key mà không tạo khoảng thời gian xác thực sai hoặc làm mất khả năng thu hồi.

Trong phạm vi bảo mật API, cần kiểm tra cả authentication tại gateway/resource server lẫn authorization tại endpoint, object và workflow. Token hợp lệ chỉ xác nhận một danh tính hoặc client theo issuer; nó không tự chứng minh caller có quyền đọc mọi object, gọi mọi chức năng hay thực hiện mọi chuyển trạng thái nghiệp vụ.

## 1. Mục tiêu và phạm vi kiểm thử

Một kế hoạch kiểm thử nên trả lời được các câu hỏi:

- API có từ chối request thiếu credential, credential sai định dạng hoặc credential không hợp lệ không?
- Token có được xác minh bằng issuer, audience, thuật toán và key đã cấu hình không?
- Token hết hạn, chưa có hiệu lực, bị thu hồi hoặc dùng sai loại có bị từ chối không?
- Scope, role, tenant và object authorization có được kiểm tra ở đúng endpoint không?
- Refresh token có rotation, chống replay và thu hồi session không?
- API key có được lưu, giới hạn và thu hồi an toàn không?
- Certificate/mTLS có được xác minh theo chain, identity và trạng thái hiệu lực không?
- Key rotation có overlap đúng, cập nhật cache và loại bỏ key cũ đúng thời điểm không?
- Khi key hoặc secret bị compromise, hệ thống có thể chặn credential cũ nhanh và có thể kiểm chứng không?
- Log, trace, error response và test artifact có tránh lộ token hoặc key không?

### 1.1. Phân biệt các khái niệm

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Caller là ai hoặc workload nào? | Xác minh JWT, API key, session hoặc client certificate |
| Authorization | Caller được làm gì trên resource nào? | Scope, role, tenant/object policy |
| Token validation | Credential có đúng cấu trúc, chữ ký, issuer, audience và thời hạn? | Kiểm tra JWT access token |
| Token lifecycle | Credential được cấp, refresh, thu hồi và hết hạn ra sao? | Refresh token rotation |
| Key management | Key được tạo, lưu, phân phối, xoay vòng và thu hồi thế nào? | JWKS và signing key version |

Một test suite chỉ xác minh token signature là chưa đủ. Nó có thể bỏ sót lỗi phân quyền, token replay, refresh-token reuse, key cache cũ hoặc credential vẫn được chấp nhận sau khi thu hồi.

## 2. Lập inventory authentication trước khi test

Liệt kê từng loại endpoint và cơ chế xác thực áp dụng. Không giả định toàn bộ API dùng cùng một loại token.

| Loại endpoint | Cơ chế thường gặp | Nội dung cần kiểm tra |
|---|---|---|
| Public/read-only | Anonymous hoặc API key giới hạn | Rate limit, dữ liệu công khai, không có quyền ghi ngoài chủ đích |
| User API | OAuth 2.0 access token/JWT hoặc opaque token | Issuer, audience, expiry, scope, user/tenant context |
| Admin API | User token có role/scope đặc biệt, step-up/MFA | Privilege boundary, session age, audit |
| Service-to-service | Client credentials, workload identity hoặc mTLS | Client identity, audience, scope, certificate binding |
| Webhook ingress | HMAC/asymmetric signature, timestamp | Raw body, signature, replay và key rotation |
| Legacy integration | API key hoặc Basic authentication qua TLS | Key storage, expiry, restriction và migration |

Với mỗi nhóm, ghi rõ issuer/provider, audience/resource server, thuật toán hoặc loại credential, thời hạn, cơ chế thu hồi, nguồn key, cache policy và owner. Inventory cũng cần chỉ ra endpoint nào được phép anonymous, endpoint nào cần user identity và endpoint nào chỉ nhận workload identity.

### 2.1. Xây dựng test principal

Chuẩn bị các identity kiểm thử đại diện:

- Anonymous caller.
- User đã xác thực nhưng không có permission.
- User có quyền đọc nhưng không có quyền ghi.
- User thuộc tenant A và user thuộc tenant B.
- Tenant administrator và system administrator.
- API client chỉ có scope đọc.
- Workload identity của service A và service B.
- Credential đã hết hạn, bị thu hồi hoặc thuộc môi trường khác.

Không dùng tài khoản production thật hoặc token production trong automated test. Tạo identity và key riêng cho môi trường test, có thể tái tạo và thu hồi sau mỗi đợt kiểm thử.

## 3. Kiểm thử authentication ở HTTP boundary

Kiểm tra các trường hợp request cơ bản trước khi đi sâu vào claim hoặc chữ ký.

| Tình huống | Kết quả mong đợi |
|---|---|
| Không có Authorization header ở endpoint cần auth | Từ chối theo contract, thường là 401 |
| Header không có scheme hoặc thiếu credential | Từ chối; không tự suy đoán loại token |
| Dùng scheme không được hỗ trợ | Từ chối |
| Bearer token rỗng hoặc chỉ có khoảng trắng | Từ chối |
| Header bị lặp hoặc có nhiều credential mâu thuẫn | Từ chối theo quy tắc parser rõ ràng |
| Token bị cắt, thêm ký tự hoặc sai encoding | Từ chối |
| Credential gửi qua query string | Không chấp nhận nếu contract không cho phép; tránh token trong URL |
| Token trong cookie ở endpoint chỉ nhận Bearer header | Không tự động coi cookie là credential hợp lệ |
| Header kích thước quá lớn | Từ chối có giới hạn; không gây tiêu thụ tài nguyên không kiểm soát |

Không để parser chọn credential đầu tiên hoặc cuối cùng khi có nhiều Authorization header. Proxy và application phải có cách xử lý nhất quán đối với duplicate header, khoảng trắng, comma và header normalization.

### 3.1. Kiểm tra authentication failure không gây side effect

Với mọi request không xác thực được:

- Không tạo, sửa hoặc xóa domain object.
- Không enqueue job nghiệp vụ.
- Không gọi provider bằng credential server-side.
- Không ghi nhận operation như đã thành công.
- Không trả dữ liệu riêng tư trong response.
- Ghi audit/security event ở mức cần thiết, không lưu token nguyên văn.

Kiểm tra cả đường đi qua gateway và đường gọi trực tiếp application nếu kiến trúc có thể để lộ origin. Nếu gateway đã xác thực rồi truyền identity header, application phải xác minh nguồn gateway và không tin header do client tự gửi.

## 4. Kiểm thử JWT access token

JWT thường gồm header, payload và signature. Việc decode payload thành công không có nghĩa token hợp lệ. Resource server phải xác minh chữ ký và các claim bắt buộc theo contract.

### 4.1. Kiểm tra signature và thuật toán

Tạo test case cho:

- Token có chữ ký hợp lệ bằng key được tin cậy.
- Token bị sửa một byte ở header, payload hoặc signature.
- Token ký bằng key không thuộc issuer đã cấu hình.
- Token dùng thuật toán không nằm trong allowlist.
- Token dùng thuật toán `none` hoặc thiếu signature khi API yêu cầu chữ ký.
- Token tạo nhầm kiểu thuật toán đối xứng/bất đối xứng.
- Token có `kid` không tồn tại.
- Token có `kid` hợp lệ nhưng key thuộc issuer khác.
- Token chứa header `jku` hoặc `x5u` trỏ đến URL do attacker kiểm soát.
- Token có JSON header/payload bất thường, duplicate claim hoặc cấu trúc quá lớn.

Resource server phải pin thuật toán được chấp nhận theo cấu hình tin cậy. Không chọn thuật toán chỉ vì header JWT yêu cầu. `kid` chỉ được dùng để tìm key trong JWKS/keystore của issuer đã cấu hình; không được dùng để tạo đường dẫn file, secret path hoặc URL tùy ý.

Không tải key từ `jku`/`x5u` do token gửi đến trừ khi protocol và trust model được thiết kế riêng, có allowlist và kiểm soát SSRF chặt chẽ. Với OAuth/OIDC thông thường, JWKS URI phải đến từ cấu hình issuer tin cậy hoặc metadata được xác minh.

### 4.2. Kiểm tra claim bắt buộc

| Claim | Test âm | Kết quả mong đợi |
|---|---|---|
| `iss` | Issuer sai hoặc thiếu khi bắt buộc | Từ chối |
| `aud` | Audience không chứa API hiện tại | Từ chối |
| `exp` | Token đã hết hạn | Từ chối sau clock skew được cho phép |
| `nbf` | Token chưa đến thời điểm hiệu lực | Từ chối |
| `iat` | Issued-at ở tương lai bất hợp lý | Từ chối theo policy |
| `sub` | Subject thiếu hoặc sai kiểu khi bắt buộc | Từ chối |
| `scope`/`scp` | Scope thiếu hoặc sai định dạng | Xác thực có thể thành công, authorization phải từ chối action cần scope |
| `client_id`/`azp` | Client không được phép | Từ chối theo policy |
| `jti` | Token có ID bị phát lại khi protocol yêu cầu chống replay | Từ chối hoặc phát hiện duplicate |
| `typ`/token-use | Dùng ID token thay access token | Từ chối |

Không phải mọi claim đều bắt buộc trong mọi profile JWT. Test phải dựa trên contract của issuer và loại token. Ví dụ, `scope` thường liên quan authorization; token có thể được xác thực nhưng không được phép gọi endpoint yêu cầu scope đó.

### 4.3. Token confusion

Một hệ thống có thể phát hành nhiều loại JWT: access token, ID token, password reset token, email verification token hoặc service token. Không để một loại token được dùng thay loại khác chỉ vì cùng được ký bởi một issuer.

Kiểm tra:

- ID token không được dùng như access token cho API.
- Password reset token không được dùng để gọi endpoint nghiệp vụ.
- Token dành cho API A không được dùng cho API B nếu audience khác.
- Token user không được dùng làm workload identity.
- Token test/staging không được chấp nhận ở production.
- Token có claim `token_use` hoặc `typ` không đúng bị từ chối.

Phân tách issuer, audience, key set hoặc token profile khi cần. Đừng chỉ dựa vào tên claim do client tự cung cấp; claim phải nằm trong token đã được xác minh và được diễn giải theo profile tin cậy.

### 4.4. Scope hợp lệ không đồng nghĩa có quyền trên mọi object

Sau khi token hợp lệ, test authorization riêng:

- Token có scope đọc không gọi được endpoint ghi.
- Token có role tenant admin chỉ tác động object thuộc tenant.
- Token của user A không đọc được object của user B nếu policy không cho phép.
- Tenant claim không được dùng nếu membership đã bị thu hồi theo yêu cầu consistency.
- Thay object ID trong URL/body không vượt qua object-level authorization.

## 5. Kiểm thử opaque token và token introspection

Opaque token không chứa claim có thể tự xác minh như JWT; resource server thường gọi authorization server/introspection endpoint hoặc dùng gateway có trạng thái xác minh.

Kiểm tra:

- Token active hợp lệ được chấp nhận.
- Token inactive, expired hoặc revoked bị từ chối.
- Introspection response thiếu field bắt buộc hoặc sai kiểu bị xử lý an toàn.
- Introspection endpoint timeout/5xx có fallback đúng policy.
- Client không thể giả mạo introspection response.
- Cache introspection có TTL phù hợp và invalidation khi revoke.
- Token của issuer/client khác không được chấp nhận.
- Scope/audience/resource được kiểm tra theo endpoint.

Nếu introspection service không khả dụng, không tự coi token là active. Có thể dùng kết quả cache còn hạn trong một khoảng thời gian được phê duyệt cho action rủi ro thấp; action nhạy cảm cần fail closed hoặc step-up theo policy. Ghi rõ maximum staleness vì cache dài làm chậm thu hồi.

## 6. Kiểm thử access token và refresh token lifecycle

Access token thường có thời hạn ngắn để giới hạn tác động khi bị lộ. Refresh token có thời hạn dài hơn và quyền đổi lấy access token mới, vì vậy cần được bảo vệ chặt hơn.

### 6.1. Access token

Kiểm tra:

- TTL đúng với profile và môi trường.
- `exp`, `nbf`, `iat` được xử lý đúng.
- Token không được chấp nhận trước `nbf` hoặc sau `exp` ngoài clock skew.
- Token bị thu hồi hoặc session version cũ bị từ chối theo policy.
- Logout/disable account có hiệu lực theo SLA thu hồi đã công bố.
- Token có audience khác không dùng được ở API hiện tại.
- Token không chứa dữ liệu nhạy cảm không cần thiết.
- Token bị copy sang client hoặc log không được lộ qua response/debug.

JWT access token có thể được xác minh offline nên khó thu hồi tức thời nếu không có denylist, session version, introspection hoặc access token ngắn hạn. Hãy kiểm tra hành vi thực tế thay vì giả định logout tự động vô hiệu hóa mọi JWT đã phát hành.

### 6.2. Refresh token rotation

Với refresh token rotation, mỗi lần sử dụng hợp lệ sẽ phát hành refresh token mới và vô hiệu hóa token cũ. Điều này giảm rủi ro replay token đã bị đánh cắp.

Test:

1. Refresh token hiện hành đổi được access token mới và refresh token mới.
2. Refresh token cũ bị từ chối sau khi đã dùng.
3. Gửi lại refresh token cũ phát hiện reuse theo policy.
4. Reuse có thể thu hồi toàn bộ token family/session liên quan.
5. Hai request refresh đồng thời không tạo hai nhánh token hợp lệ ngoài chủ đích.
6. Refresh token hết hạn hoặc bị revoke không thể tạo access token mới.
7. Logout/revoke session làm refresh token không còn hiệu lực.
8. Client mất response sau khi server rotate phải có cách xử lý an toàn, không mở lại token cũ vô thời hạn.

### 6.3. Refresh token reuse detection

Nếu token cũ được dùng lại sau khi rotation, có thể token đã bị sao chép. Server nên ghi security event và áp dụng policy thu hồi phù hợp. Không chỉ trả lỗi rồi tiếp tục chấp nhận token family hiện tại.

Test cả trường hợp retry mạng hợp lệ: client gửi refresh, server rotate thành công nhưng response bị mất. Thiết kế cần xác định có grace window, idempotency hoặc client recovery flow nào được hỗ trợ. Grace window phải hẹp, ràng buộc với client/session và không cho phép attacker replay tùy ý.

### 6.4. Lưu refresh token

Nếu server lưu refresh token, nên lưu hash hoặc verifier phù hợp thay vì token nguyên văn khi kiến trúc cho phép. Gắn token với family/session, client, thời điểm cấp, expiry, trạng thái revoked và thông tin phát hiện reuse. Không log token trong audit hoặc exception.

## 7. Kiểm thử API key

API key thường đại diện cho application/client hoặc tích hợp, không nhất thiết đại diện cho người dùng cuối. Một API key hợp lệ vẫn cần scope, quota, tenant mapping và object policy thích hợp.

Các test:

- Key đúng được chấp nhận trong đúng môi trường.
- Key sai, thiếu, hết hạn hoặc revoked bị từ chối.
- Key của tenant A không truy cập dữ liệu tenant B.
- Key chỉ đọc không thực hiện thao tác ghi.
- Key bị giới hạn IP/network hoặc endpoint nếu policy yêu cầu.
- Key cũ bị vô hiệu sau rotation.
- Key không xuất hiện trong URL, log, trace hoặc error response.
- Key không được trả lại sau lần tạo ban đầu nếu quy trình yêu cầu one-time reveal.
- Thay prefix/key ID không làm hệ thống đọc nhầm credential khác.

### 7.1. Lưu trữ API key

API key có entropy cao nên có thể lưu dạng hash/HMAC để so sánh khi nhận request; không cần lưu plaintext để hiển thị lại. Một thiết kế thường dùng:

- Public identifier/prefix để tìm record.
- Secret portion có entropy đủ cao.
- Hash hoặc HMAC có server-side pepper được quản lý riêng.
- Metadata về owner, scope, tenant, created-at, expiry và last-used.
- Trạng thái active/revoked và version.

Nếu dùng HMAC pepper, bảo vệ pepper trong KMS/secret manager và có kế hoạch rotation. So sánh verifier theo cách phù hợp; không ghi key vào database plaintext chỉ để tiện hiển thị.

### 7.2. API key rotation

Cho phép phát hành key mới, cập nhật client, xác minh sử dụng key mới, rồi thu hồi key cũ. Có thể hỗ trợ một overlap window ngắn với hai key cùng hợp lệ. Theo dõi last-used của từng key để xác nhận không còn client sử dụng key cũ trước khi revoke.

Không giữ key cũ vô thời hạn vì một client chưa được nâng cấp. Nếu buộc phải có overlap dài, cần owner, deadline và alert rõ ràng.

## 8. Kiểm thử mTLS và certificate-based authentication

mTLS xác thực client ở tầng TLS bằng certificate. Với API service-to-service, cần kiểm tra cả certificate chain lẫn identity mà certificate đại diện.

Test:

- Certificate hợp lệ, chain đến CA được tin cậy và đúng SAN/identity được chấp nhận.
- Certificate tự ký hoặc CA không tin cậy bị từ chối.
- Certificate hết hạn hoặc chưa đến thời điểm hiệu lực bị từ chối.
- SAN không khớp service identity bị từ chối.
- Certificate có EKU/key usage không phù hợp bị từ chối.
- Certificate bị revoke được xử lý theo CRL/OCSP hoặc cơ chế revocation được triển khai.
- Certificate của staging không được dùng cho production.
- Proxy không được giả mạo identity header nếu không có mTLS/workload identity hợp lệ.

### 8.1. Certificate rotation

Quy trình rotation thường gồm:

1. Cấp certificate mới với identity/SAN phù hợp.
2. Cập nhật trust bundle hoặc allowlist nếu CA/issuer thay đổi.
3. Triển khai certificate mới đến workload.
4. Xác minh handshake và identity trên tất cả instance/region.
5. Theo dõi lỗi handshake và traffic dùng certificate cũ.
6. Thu hồi hoặc ngừng tin certificate cũ sau overlap window.

Nếu CA root/intermediate được thay đổi, cần phân phối trust anchor mới trước khi chuyển client certificate. Không tắt peer verification để vượt qua lỗi rotation.

## 9. Key rotation cho JWT/JWKS

Key rotation là thay signing key hoặc encryption key theo lịch, khi key gần hết vòng đời hoặc khi có dấu hiệu compromise. Với JWT ký bất đối xứng, issuer giữ private key để ký; resource server thường chỉ cần public key để xác minh.

### 9.1. Rotation bình thường theo giai đoạn

Quy trình tham khảo:

1. Tạo key pair mới trong KMS/HSM hoặc hệ thống quản lý key.
2. Công bố public key mới trong JWKS với `kid` mới.
3. Chờ các resource server refresh JWKS và xác nhận key mới đã được nhận.
4. Bắt đầu ký token mới bằng private key mới.
5. Giữ public key cũ trong JWKS trong khoảng overlap.
6. Chờ token ký bằng key cũ hết hạn theo maximum token lifetime, clock skew, JWKS cache TTL và propagation margin.
7. Gỡ public key cũ khỏi JWKS.
8. Xác minh token mới vẫn hợp lệ và token cũ hết hạn bị từ chối.
9. Lưu audit về key version, actor, thời điểm và kết quả.

Không xóa public key cũ ngay khi bắt đầu ký bằng key mới, vì token cũ còn hợp lệ có thể bị từ chối sớm. Ngược lại, không giữ key cũ lâu hơn cần thiết vì nó kéo dài khả năng chấp nhận token được ký bằng private key cũ.

### 9.2. Tính overlap window

Overlap cần đủ cho token hợp lệ đã phát hành trước thời điểm chuyển. Hãy tính từ lần cuối issuer ký token bằng key cũ:

`overlap >= maximum access-token lifetime + accepted clock skew + JWKS cache/propagation margin`

Đây là cách ước lượng cho rotation bình thường, không phải công thức cố định cho mọi hệ thống. Cần tính thêm thời gian rollout, cache của CDN/proxy, vùng mạng chậm và quy tắc token đặc biệt. Nếu access token có TTL khác nhau theo client, dùng giới hạn lớn nhất được phép.

### 9.3. Kiểm tra JWKS cache

Resource server thường cache JWKS để tránh gọi issuer cho mỗi request. Kiểm tra:

- Cache refresh theo Cache-Control/TTL hoặc policy đã định.
- Key mới được nhận trong thời gian rollout.
- Khi gặp `kid` chưa biết, verifier có thể refresh JWKS có giới hạn.
- Unknown `kid` không gây request storm đến issuer.
- Cache không giữ public key đã bị thu hồi quá thời hạn cho phép.
- Nhiều instance/region cập nhật nhất quán.
- JWKS endpoint timeout/5xx có fallback an toàn.
- JWKS response sai schema hoặc chứa key trùng `kid` được xử lý an toàn.

Không cho mỗi token có `kid` ngẫu nhiên kích hoạt một lần fetch không giới hạn. Có thể throttle refresh, negative-cache unknown key trong thời gian ngắn và giới hạn concurrency. Negative cache cũng cần TTL ngắn để key mới vừa được publish không bị từ chối quá lâu.

### 9.4. Kiểm tra key selection

- `kid` phải được tra cứu trong JWKS của issuer đã cấu hình.
- Key phải có `kty`, `use`, `key_ops` và thuật toán phù hợp với policy.
- Không chấp nhận key có mục đích encryption nếu endpoint chỉ xác minh signature.
- Không chọn key theo URL hoặc filesystem path do token cung cấp.
- Không chấp nhận key trùng `kid` gây mơ hồ.
- Không suy đoán thuật toán từ key hoặc header token.

## 10. Emergency rotation khi signing key bị compromise

Rotation bình thường ưu tiên overlap để tránh gián đoạn. Khi private signing key bị lộ, mục tiêu đổi khác: chặn token giả mạo càng sớm càng tốt. Không giữ key bị compromise chỉ để chờ hết TTL.

Runbook khẩn cấp cần:

1. Xác nhận key ID/version bị ảnh hưởng và phạm vi issuer.
2. Dừng ký bằng key bị compromise.
3. Thu hồi hoặc đánh dấu key không còn được tin cậy trong resource server.
4. Phát hành key pair mới và công bố public key mới.
5. Invalidate JWKS cache hoặc kích hoạt cơ chế emergency deny theo `kid`.
6. Thu hồi session/refresh token hoặc token family có nguy cơ.
7. Đánh giá token đã phát hành trong khoảng thời gian compromise.
8. Theo dõi các request dùng key ID cũ và từ chối chúng.
9. Xác minh mọi instance/region đã nhận emergency policy.
10. Điều tra nguồn lộ key và lưu audit/incident evidence.

Nếu attacker có private key, họ có thể ký JWT giả với claim tùy ý. Chỉ xóa key khỏi JWKS không đủ nếu resource server đang giữ cache cũ. Cần cơ chế truyền thay đổi khẩn cấp và xác minh trạng thái thực tế của cache/instance.

### 10.1. Key revocation và token revocation là hai việc khác nhau

Thu hồi signing key có thể làm mọi token được ký bằng key đó mất hiệu lực, kể cả token hợp lệ. Thu hồi một session/token cụ thể cần cơ chế khác như token denylist, session version, introspection hoặc refresh-token family revocation.

Chọn biện pháp theo phạm vi sự cố:

| Sự cố | Biện pháp |
|---|---|
| Một refresh token bị đánh cắp | Revoke token/family và phát hiện reuse |
| Một user bị khóa | Revoke session/token theo user hoặc kiểm tra account state |
| API key bị lộ | Revoke key cụ thể và cấp key mới |
| Một signing private key bị lộ | Emergency key revocation, cache invalidation và đánh giá token đã ký |
| KMS/HSM hoặc issuer bị xâm nhập | Incident response diện rộng, rotate key, kiểm tra issuer trust và token/session |

## 11. Clock skew, cache và trạng thái phân tán

Token validation phụ thuộc thời gian. Nếu các node lệch đồng hồ, cùng một token có thể hợp lệ ở region này nhưng hết hạn ở region khác.

Kiểm thử:

- Đồng hồ nhanh/chậm trong giới hạn cho phép.
- `exp` vừa qua thời điểm hiện tại.
- `nbf` vừa vượt qua thời điểm hiện tại.
- Token có `iat` ở tương lai.
- NTP/time source mất kết nối.
- Node/region có clock drift khác nhau.
- JWKS cache refresh chậm.
- Revocation event bị trễ giữa các region.

Chỉ cho phép clock skew nhỏ, được định nghĩa rõ và giám sát. Không tăng skew lớn để che lỗi đồng bộ thời gian. Các action nhạy cảm cần trạng thái thu hồi mới nhất nên có cơ chế kiểm tra tập trung hoặc fail closed khi dữ liệu quá stale.

### 11.1. Cache revocation

Nếu resource server cache trạng thái token/session, cần xác định:

- TTL tối đa.
- Invalidation khi logout/disable account.
- Propagation lag giữa các region.
- Hành vi khi revocation store lỗi.
- Cách xác minh cache đã nhận key/session revoke.

Test sau khi revoke token: gọi ngay, gọi sau khi cache refresh, gọi qua instance khác và gọi qua region dự phòng. Ghi rõ thời gian tối đa token còn được chấp nhận sau revoke; đây là một security SLO cần được thống nhất.

## 12. Kiểm thử authorization sau authentication

Một token hợp lệ không đồng nghĩa mọi request đều được phép. Với mỗi endpoint, test riêng:

- Principal không có function permission.
- Scope chỉ đọc gọi endpoint ghi.
- User thuộc tenant A thay ID sang object tenant B.
- User bị thu hồi membership nhưng token cũ vẫn còn hạn.
- Role thay đổi trong khi access token cũ còn hiệu lực.
- API client gọi endpoint dành cho user hoặc ngược lại.
- Token có claim tenant không còn khớp membership hiện tại.
- Workflow state không cho phép action dù caller có role.

Nếu role/permission nằm trong JWT, cần quyết định chấp nhận độ trễ cập nhật đến hết TTL hay có session version/introspection. Không mặc định claim trong token luôn phản ánh trạng thái mới nhất.

## 13. Kiểm thử trong Spring Security

Spring Security cung cấp test support để kiểm tra authentication context và authorization rule. Cần hiểu mỗi cách test đang xác minh lớp nào.

### 13.1. Mock JWT cho authorization test

Ví dụ dùng MockMvc:

~~~java
mockMvc.perform(get("/api/invoices")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoice:read"))))
    .andExpect(status().isOk());

mockMvc.perform(post("/api/invoices")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoice:read"))))
    .andExpect(status().isForbidden());
~~~

Test này hữu ích để xác minh endpoint mapping và authorization dựa trên authorities. Tuy nhiên, request post-processor `jwt()` tạo authentication cho test; nó không kiểm tra chữ ký JWT thật, JWKS, issuer hoặc key rotation. Không dùng nó làm bằng chứng rằng cryptographic validation hoạt động.

### 13.2. Test JWT signature thực

Với test tích hợp decoder/resource server:

- Tạo RSA/EC test key pair riêng trong test.
- Ký JWT bằng private test key.
- Cấu hình decoder chỉ tin public test key/JWKS test.
- Gửi token qua HTTP Authorization header thực.
- Thay payload sau khi ký và xác nhận bị từ chối.
- Ký token bằng key khác và xác nhận bị từ chối.
- Thay issuer/audience/expiry và xác nhận validator từ chối.
- Cập nhật JWKS test endpoint để mô phỏng rotation và cache refresh.

Không dùng private key production hoặc gọi JWKS production trong CI. Có thể dùng mock JWKS server nội bộ hoặc test fixture deterministic.

### 13.3. Test AuthenticationEntryPoint và error response

Xác minh:

- Token thiếu/sai/hết hạn trả status theo contract.
- Bearer challenge được giữ nguyên qua gateway.
- Response không chứa raw token hoặc exception chi tiết.
- Authentication failure không bị chuyển thành 403 một cách nhầm lẫn.
- Authorization denial trả status phù hợp nhưng không lộ object ngoài tenant.

### 13.4. Test API key và mTLS

MockMvc đơn thuần không xác minh TLS handshake. Với mTLS, cần integration test ở server/proxy thực hoặc test harness có client certificate để kiểm tra trust chain, SAN, expiry và revocation. API key cần test qua filter thực tế với key hash trong test store, bao gồm rotation và revoke.

## 14. Ma trận test tổng hợp

| Nhóm | Test case | Kết quả mong đợi |
|---|---|---|
| HTTP authentication | Missing/malformed/duplicate credential | Bị từ chối rõ ràng |
| JWT signature | Modified payload/signature | Bị từ chối |
| Algorithm | `none`, algorithm ngoài allowlist, key-type confusion | Bị từ chối |
| Issuer/audience | Issuer/audience sai | Bị từ chối |
| Time claims | Expired, future `nbf`/`iat` | Bị từ chối theo skew policy |
| Token type | ID token hoặc reset token gọi API | Bị từ chối |
| Scope | Token hợp lệ thiếu scope | Authentication thành công, authorization từ chối |
| Opaque token | Inactive/revoked/introspection timeout | Không mặc định active |
| Refresh | Refresh token reuse/concurrent refresh | Phát hiện replay, không tạo nhiều family hợp lệ |
| API key | Wrong/expired/revoked/cross-tenant | Bị từ chối |
| mTLS | Wrong CA/SAN/expired/revoked certificate | Handshake hoặc authentication bị từ chối |
| JWKS rotation | New key publish, old key overlap, old key removal | Token mới hợp lệ, token cũ hợp lệ đúng cửa sổ |
| JWKS failure | Timeout, malformed response, unknown `kid` flood | Không fail open; refresh có giới hạn |
| Emergency revoke | Compromised `kid` và stale cache | Token ký bằng key bị chặn trong SLA |
| Clock | Drift giữa instance/region | Quyết định nhất quán theo skew policy |
| Authorization | BOLA, role/scope, stale membership | Không truy cập ngoài quyền |
| Logging | Token/key trong exception/trace | Không có credential plaintext |

## 15. Kiểm thử hiệu năng và khả năng chịu lỗi

Authentication và key management nằm trên đường đi của request nên cần kiểm tra cả độ trễ và khả năng chịu lỗi:

- JWKS refresh không xảy ra trên mọi request.
- Unknown `kid` không tạo request storm.
- Introspection cache giảm latency nhưng không vượt maximum staleness.
- Secret manager/KMS outage không làm resource server tự chấp nhận token.
- Rotation nhiều key không làm verifier tải key không giới hạn.
- Token quá lớn bị giới hạn trước khi parse tốn tài nguyên.
- Certificate chain quá sâu hoặc bất thường không gây CPU exhaustion.
- Concurrent refresh không tạo race condition.
- Revocation event được phân phối trong thời gian mục tiêu.

Đặt timeout, connection pool, retry budget và circuit breaker cho JWKS/introspection/KMS dependency. Không retry vô hạn hoặc chuyển sang chế độ bỏ qua chữ ký khi dependency lỗi.

## 16. Audit, logging và monitoring

Theo dõi:

- Authentication success/failure theo issuer, client và endpoint template.
- Token validation reason code ở mức không tiết lộ dữ liệu nhạy cảm.
- Unknown `kid`, JWKS fetch, cache age và refresh failure.
- Token expired/issuer/audience mismatch.
- Refresh token reuse và family revocation.
- API key created/rotated/revoked và last-used.
- Certificate expiry, handshake failure và trust bundle version.
- Signing key version, rotation event và propagation lag.
- Emergency denylist/cache invalidation status.
- Authorization denial và access attempt cross-tenant.

Không ghi access token, refresh token, API key, private key hoặc toàn bộ Authorization header. Nếu cần correlation, ghi token ID/jti đã giả danh hóa hoặc fingerprint an toàn theo policy, không ghi credential gốc. Audit key management cần actor, key ID/version, action, thời điểm, approval/change reference và kết quả.

### 16.1. Alert cần có

- Token được ký bằng `kid` không còn được tin cậy.
- Unknown `kid` tăng bất thường.
- JWKS cache vượt maximum staleness.
- Resource server không nhận key version mới.
- Refresh token reuse vượt baseline.
- API key cũ vẫn được dùng sau rotation deadline.
- Certificate sắp hết hạn hoặc bị revoke nhưng vẫn xuất hiện traffic.
- Một issuer đột ngột có audience mismatch tăng mạnh.
- Emergency revoke chưa lan đến mọi instance/region.
- Authentication failure tăng sau deployment hoặc config change.

## 17. Quy trình kiểm thử key rotation

### 17.1. Rotation định kỳ

1. Dùng test issuer và key pair mới.
2. Publish public key mới vào JWKS.
3. Xác nhận tất cả verifier nhận key mới.
4. Phát token mới bằng key mới.
5. Xác nhận token mới hợp lệ ở mọi instance/region.
6. Xác nhận token cũ vẫn hợp lệ trong overlap.
7. Chờ token cũ hết hạn cộng skew/cache margin.
8. Remove key cũ khỏi JWKS.
9. Xác nhận token cũ bị từ chối sau khi cache cập nhật.
10. Xác nhận token mới vẫn hợp lệ và audit đầy đủ.

### 17.2. Rotation khi compromise

1. Đánh dấu key cũ compromised trong test environment.
2. Ngừng ký bằng key cũ.
3. Kích hoạt emergency deny theo `kid`.
4. Invalidate JWKS cache trên các verifier.
5. Publish key mới và chuyển issuer.
6. Gọi API qua mọi instance/region bằng token ký key cũ.
7. Xác nhận token cũ bị từ chối trong SLA.
8. Xác nhận token mới được chấp nhận.
9. Thu hồi session/refresh token liên quan theo incident policy.
10. Kiểm tra log/audit không chứa private key hoặc token plaintext.

Không dùng overlap thông thường trong bài test compromise nếu điều đó khiến key đã lộ tiếp tục được tin cậy.

## 18. Những sai lầm thường gặp

- **Chỉ decode JWT:** payload đọc được nhưng chữ ký/claim chưa được xác minh.
- **Tin thuật toán trong header:** attacker có thể khai thác algorithm confusion.
- **Tin `kid` hoặc URL trong token:** có thể tạo key lookup ngoài trust boundary hoặc SSRF.
- **Không kiểm tra audience:** token dành cho service khác được chấp nhận.
- **Dùng ID token làm access token:** token confusion giữa các protocol.
- **Không kiểm tra expiry/nbf/clock skew:** token hết hạn hoặc chưa hiệu lực vẫn được dùng.
- **Dựa hoàn toàn vào JWT offline:** logout/disable account không thu hồi token ngay.
- **Không rotate refresh token:** refresh token bị đánh cắp có thể tái sử dụng lâu dài.
- **Không phát hiện refresh-token reuse:** bỏ qua dấu hiệu replay.
- **Giữ API key plaintext:** database/log bị lộ làm lộ credential trực tiếp.
- **Chia sẻ key giữa môi trường:** token staging có thể được chấp nhận ở production.
- **Xóa public key quá sớm:** token hợp lệ đang lưu hành bị từ chối.
- **Giữ public key compromise quá lâu:** token giả mạo tiếp tục được chấp nhận.
- **JWKS cache không có giới hạn:** key cũ được tin vô thời hạn.
- **Unknown `kid` gây fetch vô hạn:** attacker tạo tải lên issuer.
- **Chỉ dùng Mock JWT test:** không kiểm tra signature, JWKS hoặc rotation thật.
- **Không test mọi region:** một số instance vẫn giữ key hoặc revocation state cũ.
- **Log Authorization header:** token bị lộ trong hệ thống quan sát.

## 19. Checklist trước khi phát hành

- [ ] Inventory endpoint và authentication mechanism đã được lập.
- [ ] Test missing, malformed, duplicate và credential sai.
- [ ] JWT signature được xác minh bằng thuật toán allowlist.
- [ ] Issuer, audience, expiry, not-before và token type được kiểm tra.
- [ ] `kid` chỉ lookup trong key set của issuer tin cậy; không dùng URL tùy ý từ token.
- [ ] Test ID token/access token confusion và cross-environment token.
- [ ] Scope/function/object/tenant authorization được test riêng.
- [ ] Opaque token introspection có timeout, cache TTL và fail-safe rõ ràng.
- [ ] Refresh token rotation, reuse detection, concurrent refresh và logout được test.
- [ ] API key lưu verifier/hash, có scope, owner, expiry, rotation và revoke.
- [ ] mTLS kiểm tra chain, SAN, EKU, expiry và revocation.
- [ ] JWKS key mới được publish trước khi bắt đầu ký token mới.
- [ ] Overlap tính đến token TTL, clock skew, JWKS cache và propagation.
- [ ] Key cũ bị gỡ sau cửa sổ hợp lệ; compromise dùng emergency revoke riêng.
- [ ] JWKS unknown `kid`, cache invalidation và multi-region propagation được test.
- [ ] Clock skew và revocation propagation có giới hạn được giám sát.
- [ ] Test thực tế qua decoder/gateway; phân biệt test mock authorization với crypto integration test.
- [ ] Không dùng production key/token trong CI hoặc test fixture.
- [ ] Log/trace/error không chứa token, API key hoặc private key.
- [ ] Có audit và alert cho key rotation, refresh reuse, key compromise và stale cache.
- [ ] Có runbook định kỳ và khẩn cấp, bao gồm xác minh mọi instance đã nhận policy.

Kiểm thử authentication, token và key rotation phải chứng minh cả hai trạng thái: credential hợp lệ tiếp tục hoạt động trong giới hạn đã định, còn credential sai, hết hạn, bị thu hồi hoặc được ký bằng key không còn tin cậy đều bị từ chối. Khi test bao phủ HTTP boundary, token profile, refresh/replay, API key, mTLS, JWKS cache, rotation bình thường và emergency revocation, API sẽ có bằng chứng tốt hơn rằng danh tính và trust key được duy trì an toàn trong suốt vòng đời.
