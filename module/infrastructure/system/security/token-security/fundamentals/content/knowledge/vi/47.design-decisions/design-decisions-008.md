# Chọn lifetime theo risk

Trong OAuth 2.0 và OpenID Connect (OIDC), **token lifetime** là khoảng thời gian một token được phép sử dụng kể từ khi phát hành cho đến thời điểm hết hạn. Chọn lifetime là một quyết định bảo mật và vận hành: token sống càng lâu thì client càng ít phải xin token mới, nhưng credential bị đánh cắp cũng có thể bị lạm dụng trong thời gian dài hơn. Token sống quá ngắn làm giảm cửa sổ rủi ro nhưng tăng tải lên authorization server, độ phức tạp refresh và khả năng gián đoạn request.

Không có một TTL cố định phù hợp cho mọi loại token, client và API. Authorization server cần chọn thời hạn dựa trên độ nhạy cảm của dữ liệu, mức độ quyền, khả năng token bị lộ, cách resource server xác minh token, tốc độ thu hồi và yêu cầu sẵn sàng của hệ thống. Đây là chính sách của hệ thống; các RFC OAuth/JWT quy định cách biểu diễn và sử dụng thời hạn, không đưa ra một con số lifetime chung cho mọi triển khai.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, quyết định lifetime phải được đặt cùng với audience, scope, loại token, nơi lưu trữ, cơ chế sender constraint, refresh/rotation và revocation. TTL ngắn là một lớp giảm thiểu rủi ro; nó không thay thế least privilege, xác minh token đúng cách hoặc khả năng thu hồi khi có sự cố.

## 1. Lifetime là gì và áp dụng cho token nào?

Lifetime là thời gian token còn được chấp nhận theo chính sách. Với JWT, claim `exp` biểu diễn thời điểm hết hạn tuyệt đối dưới dạng NumericDate. Với token response OAuth, `expires_in` thường cho biết thời lượng sống tính bằng giây. Với opaque token, thời hạn có thể được lưu trong token registry và được trả về qua introspection nếu authorization server cung cấp.

Không nên coi mọi credential trong OAuth/OIDC có cùng vòng đời:

| Loại | Mục đích | Quyết định lifetime cần quan tâm |
|---|---|---|
| Access token | Truy cập resource server | TTL phải phù hợp với độ nhạy cảm của API, scope, audience và khả năng thu hồi. |
| Refresh token | Xin access token mới | Cần idle lifetime, absolute lifetime, rotation và reuse detection theo loại client. |
| ID token | Xác nhận sự kiện authentication cho OIDC client | `exp` giới hạn thời gian chấp nhận assertion; không dùng ID token làm access token gọi API. |
| Authorization code | Đổi lấy token qua token endpoint | Thời hạn ngắn, dùng một lần, ràng buộc client, redirect URI và PKCE khi áp dụng. |
| Client assertion | Xác thực client, ví dụ `private_key_jwt` | Thời gian hiệu lực ngắn, audience đúng token endpoint và chống replay. |
| Session | Duy trì trạng thái đăng nhập của ứng dụng/IdP | Idle timeout, absolute timeout và yêu cầu re-authentication độc lập với access token. |

Một access token sống 5 phút không có nghĩa phiên đăng nhập chỉ sống 5 phút. Ngược lại, phiên đăng nhập còn hiệu lực cũng không có nghĩa mọi access token cũ phải tiếp tục được chấp nhận. Client có thể xin access token mới khi grant, session và chính sách vẫn cho phép.

### `exp` và `expires_in`

- `exp` là thời điểm hết hạn tuyệt đối trong JWT. Resource server phải kiểm tra token còn hiệu lực tại thời điểm xác minh.
- `expires_in` là thời lượng sống do authorization server trả trong token response. Client nên dùng giá trị này để lập lịch sử dụng/refresh.
- Thời gian truyền response và xử lý ở client làm giảm thời hạn thực còn lại. Không nên đợi đúng giây `expires_in` mới bắt đầu xin token mới.
- Opaque token có thể không để lộ `exp` cho client; client dùng `expires_in` nếu được trả và resource server dựa vào introspection hoặc trạng thái server-side.

RFC 6749 mô tả `expires_in` trong token response nhưng không quy định mọi access token phải sống bao nhiêu giây. JWT profile cho OAuth access token tại RFC 9068 yêu cầu claim thời gian cần thiết theo profile, bao gồm `exp`; con số cụ thể vẫn do authorization server quyết định.

## 2. Vì sao lifetime phải dựa trên risk?

Lifetime quyết định cửa sổ mà token có thể bị sử dụng nếu bị lộ hoặc nếu quyền của principal thay đổi. Một access token chỉ đọc danh mục công khai có hậu quả khác token có quyền hoàn tiền, xuất dữ liệu cá nhân hoặc thay đổi cấu hình bảo mật.

Khi chọn TTL, cần đánh giá ít nhất các nhóm yếu tố sau:

1. **Tác động nếu bị lạm dụng:** dữ liệu công khai, dữ liệu cá nhân, tiền, quyền quản trị, thao tác không thể đảo ngược hoặc khả năng tạo thêm credential.
2. **Phạm vi quyền:** scope hẹp hay rộng, một audience hay nhiều API, một tenant hay nhiều tenant.
3. **Khả năng token bị lộ:** browser, thiết bị di động, workload server, log, máy dùng chung, môi trường CI hoặc hệ thống bên thứ ba.
4. **Loại client:** public client, confidential client, service account, BFF, ứng dụng native hoặc workload trong hạ tầng kiểm soát.
5. **Cơ chế ràng buộc token:** bearer thuần, DPoP hoặc mutual TLS sender-constrained token.
6. **Cách resource server xác minh:** JWT offline, opaque token với introspection, denylist hoặc trạng thái authorization trực tuyến.
7. **Tốc độ thu hồi mong muốn:** hệ thống cần ngăn token cũ trong vài giây, vài phút hay có thể chờ đến khi hết hạn tự nhiên.
8. **Yêu cầu vận hành:** độ sẵn sàng của authorization server, latency, lưu lượng, kết nối mạng và thời gian chạy của job.
9. **Phiên và grant nền tảng:** token có được phát hành thay mặt user, actor hay một workload có vòng đời riêng không.
10. **Nghĩa vụ quản trị:** yêu cầu re-authentication, kiểm soát privileged action, audit và chính sách retention.

Đánh giá risk không chỉ là chấm điểm xác suất. Một sự kiện ít xảy ra nhưng có tác động nghiêm trọng vẫn có thể yêu cầu TTL ngắn và kiểm tra trạng thái trực tuyến. Ngược lại, API đọc ít nhạy cảm có thể dùng TTL dài hơn nếu audience/scope hẹp, token được bảo vệ tốt và khả năng thu hồi đáp ứng yêu cầu.

## 3. Phân loại mức rủi ro của quyền truy cập

Một cách thực tế là phân loại theo hậu quả của hành động và dữ liệu, sau đó kết hợp với exposure của token.

| Mức rủi ro | Ví dụ tài nguyên/hành động | Định hướng lifetime |
|---|---|---|
| Thấp | Đọc dữ liệu công khai, catalog không nhạy cảm, health/read-only endpoint. | Có thể dùng TTL dài hơn trong giới hạn policy; vẫn giới hạn audience và scope. |
| Trung bình | Đọc dữ liệu nội bộ, hồ sơ người dùng, thao tác nghiệp vụ có thể khôi phục. | TTL ngắn đến vừa; kiểm soát refresh, session và revocation rõ ràng. |
| Cao | Dữ liệu cá nhân nhạy cảm, thanh toán, export, thay đổi quyền hoặc thao tác có tác động lớn. | TTL ngắn; scope/audience rất hẹp; ưu tiên kiểm tra trạng thái và yêu cầu re-authentication cho hành động quan trọng. |
| Rất cao/đặc quyền | Quản trị IAM, tạo credential, thay đổi signing key, cấp quyền quản trị, hành động phá hủy. | Token/ủy quyền ngắn hạn, quyền tạm thời, step-up authentication, phê duyệt và audit chuyên biệt. |

Đây là phân loại tham khảo, không phải chuẩn pháp lý. Một endpoint chỉ đọc vẫn có thể có rủi ro cao nếu dữ liệu nhạy cảm hoặc lượng dữ liệu có thể trích xuất lớn. Một thao tác ghi có thể có rủi ro thấp nếu phạm vi nhỏ và dễ đảo ngược. Hãy phân loại theo tác động thực tế.

### Rủi ro của token không chỉ đến từ scope

Một token có scope `orders.read` nhưng audience là toàn bộ hệ thống và thời hạn dài vẫn có thể bị lạm dụng rộng hơn dự kiến nếu nhiều API cùng chấp nhận. Thiết kế cần kết hợp:

- audience/resource cụ thể;
- scope tối thiểu;
- thời hạn phù hợp;
- token binding nếu có thể;
- kiểm tra tenant/membership hiện tại khi cần;
- cơ chế thu hồi và giám sát.

TTL ngắn không bù được một token có quyền quá rộng. Nếu token chỉ cần đọc một API, hãy thu hẹp audience và scope trước khi kéo dài hoặc rút ngắn TTL.

## 4. Ma trận lựa chọn lifetime theo risk

Bảng sau đưa ra các dải thời gian minh họa để bắt đầu thảo luận chính sách. Đây không phải con số bắt buộc từ OAuth, OIDC hay NIST. Mỗi tổ chức cần kiểm chứng bằng threat model, khả năng của authorization server và SLO thu hồi.

| Mức rủi ro | Ví dụ access token TTL khởi điểm | Kiểm soát bổ sung nên cân nhắc |
|---|---:|---|
| Thấp | 15–60 phút | Audience/scope hẹp, HTTPS, xác minh đầy đủ, theo dõi bất thường. |
| Trung bình | 5–15 phút | Refresh có kiểm soát, revoke grant, introspection hoặc version check theo nhu cầu. |
| Cao | 1–5 phút | Audience chuyên biệt, scope tối thiểu, kiểm tra trạng thái nhanh, step-up cho hành động nhạy cảm. |
| Rất cao/đặc quyền | Vài phút hoặc ngắn hơn theo tác vụ | Token tạm thời, sender constraint, approval, re-authentication và audit chi tiết. |

Các dải này chỉ là ví dụ chính sách ban đầu. Một hệ thống có token offline, workload dài và không có revocation channel có thể cần thiết kế khác. Không nên sao chép nguyên bảng vào production mà chưa đo tải, đánh giá threat model và xác định thời gian thu hồi tối đa chấp nhận được.

### Điều chỉnh theo exposure của client

Nếu hai token có cùng scope và audience nhưng được lưu ở nơi khác nhau, risk vẫn khác nhau:

- Token dùng trong backend workload được bảo vệ bằng secret manager, network policy và workload identity có thể có exposure thấp hơn token lưu trong JavaScript browser.
- Token trên thiết bị di động có thể bị ảnh hưởng bởi mất thiết bị, backup không an toàn hoặc thiết bị đã jailbreak/root.
- Token được dùng trong CI/CD có thể xuất hiện trong build log, artifact hoặc environment của job nếu pipeline cấu hình sai.
- Token được chuyển qua hệ thống bên thứ ba có thêm trust boundary và log retention ngoài quyền kiểm soát của tổ chức.

Khi exposure tăng, nên rút ngắn TTL, tăng mức sender constraint, giảm scope và audience, cải thiện nơi lưu trữ và khả năng thu hồi. Không chỉ dựa vào TTL để xử lý vấn đề lưu token không an toàn.

## 5. Chọn lifetime theo loại token

### 5.1. Access token

Access token là credential được resource server dùng để quyết định quyền truy cập. TTL nên phản ánh:

- mức độ nhạy cảm của API;
- quyền và audience được cấp;
- mức độ tin cậy của client;
- token có thể bị replay đến đâu;
- resource server có kiểm tra trạng thái hiện tại không;
- hệ thống có thể cấp token mới nhanh và ổn định không.

Với access token có quyền cao, TTL ngắn làm giảm khoảng thời gian token bị đánh cắp có thể được sử dụng. Tuy nhiên, nếu attacker có thể liên tục lấy token mới bằng refresh token hoặc client credential đã bị lộ, chỉ rút ngắn access token TTL không đủ. Phải xử lý cả nguồn cấp token và grant nền tảng.

Access token không nên sống lâu chỉ vì ứng dụng muốn tránh gọi token endpoint. Hãy tối ưu bằng cache an toàn, refresh có kiểm soát và token exchange theo audience thay vì kéo dài TTL vượt mức risk chấp nhận được.

### 5.2. Refresh token

Refresh token thường có lifetime dài hơn access token vì mục đích là duy trì khả năng xin access token mới mà không yêu cầu user đăng nhập lại liên tục. Tuy nhiên, refresh token có giá trị cao: người lấy được refresh token có thể tiếp tục xin access token trong thời gian grant còn hiệu lực.

Chính sách refresh token nên xác định riêng:

- **Idle lifetime:** token hết hiệu lực nếu không được sử dụng trong một khoảng thời gian.
- **Absolute lifetime:** grant hoặc token family hết hiệu lực sau một thời điểm tối đa, kể cả vẫn được sử dụng.
- **Rotation:** mỗi lần refresh cấp token mới và vô hiệu hóa token cũ theo policy.
- **Reuse detection:** phát hiện token cũ đã bị dùng lại; có thể thu hồi token family.
- **Binding:** ràng buộc với client và có thể với sender-constrained mechanism.
- **Revocation:** logout, user disable, client disable, password/security event hoặc admin action có thể thu hồi grant.

Không nên dùng sliding expiration vô hạn, trong đó mỗi lần refresh lại kéo dài grant mãi mãi. Cần có absolute lifetime và yêu cầu xác thực lại sau thời hạn tối đa. Với public client, RFC 9700 khuyến nghị biện pháp bảo vệ refresh token như rotation hoặc sender constraint để giảm nguy cơ replay.

Client Credentials Grant thường không cần refresh token: confidential client có thể xác thực lại với authorization server để lấy access token mới. Không nên mặc định cấp refresh token cho mọi service account.

### 5.3. ID token

ID token là assertion của OpenID Provider dành cho OIDC client về một sự kiện xác thực. Nó không phải credential để gọi resource API. `exp` của ID token giới hạn thời gian client chấp nhận assertion; session của ứng dụng có thể có lifetime riêng.

Khi chọn lifetime ID token, cần xét thời điểm xác thực, yêu cầu freshness, rủi ro replay và quy trình tạo session. Nếu ứng dụng cần xác thực lại gần đây cho thao tác nhạy cảm, nên dùng `auth_time`/`max_age` và step-up authentication theo OIDC thay vì giả định ID token còn hạn là bằng chứng user vừa xác thực.

### 5.4. Authorization code và client assertion

Authorization code nên có thời hạn ngắn và chỉ dùng một lần; phải ràng buộc với client và redirect URI, đồng thời dùng PKCE khi phù hợp. Client assertion cũng nên có thời gian hiệu lực ngắn, audience đúng token endpoint và cơ chế chống replay như `jti`/lưu trạng thái theo hợp đồng triển khai.

Các giá trị này không nên được dùng thay access token hoặc giữ lâu trong browser storage. Nếu chúng xuất hiện trong URL callback hoặc log, cần xử lý như credential nhạy cảm.

## 6. JWT và opaque token ảnh hưởng quyết định lifetime thế nào?

Định dạng token không tự quyết định TTL, nhưng cách resource server xác minh ảnh hưởng trực tiếp đến khả năng thu hồi.

| Đặc điểm | JWT access token | Opaque access token |
|---|---|---|
| Cách xác minh | Resource server xác minh chữ ký và claims, có thể offline. | Thường gọi introspection hoặc kiểm tra registry qua authorization server. |
| Trạng thái thu hồi | Verifier offline không tự biết token bị thu hồi. | Authorization server có thể trả `active: false` ngay khi trạng thái được cập nhật. |
| Phụ thuộc mạng | Có thể không cần gọi authorization server trên từng request. | Introspection tạo phụ thuộc mạng, trừ khi có cache hoặc cơ chế khác. |
| Cửa sổ rủi ro | Token có thể còn được chấp nhận đến `exp` nếu không có kiểm tra bổ sung. | Phụ thuộc introspection/cache và khả năng cập nhật trạng thái. |
| Ảnh hưởng TTL | TTL ngắn thường quan trọng hơn nếu cần giới hạn thời gian thu hồi. | Có thể linh hoạt hơn khi trạng thái được kiểm tra trực tuyến, nhưng vẫn cần giới hạn lifetime. |

### JWT được xác minh offline

Nếu resource server chỉ xác minh chữ ký và `exp`, access token đã cấp có thể tiếp tục được chấp nhận cho đến khi hết hạn, kể cả user, client hoặc tenant bị disable sau đó. Trong mô hình này, TTL cần phù hợp với thời gian tối đa tổ chức chấp nhận để token cũ còn hoạt động.

Có thể giảm cửa sổ này bằng introspection, denylist theo `jti`, authorization version hoặc kiểm tra trạng thái client/tenant trực tuyến. Khi thêm các cơ chế đó, phải tính cả độ trễ cache và event propagation.

### Opaque token với introspection

Opaque token thường cho phép authorization server phản ánh trạng thái thu hồi tập trung. Resource server gọi introspection theo RFC 7662 và từ chối khi `active=false`. Nếu cache response `active=true`, token có thể tiếp tục được chấp nhận đến khi cache hết hạn hoặc bị invalidation.

Vì vậy, TTL token và TTL cache introspection phải được thiết kế cùng nhau. Cache càng dài thì giảm tải càng tốt nhưng độ trễ thu hồi càng lớn. Với API nhạy cảm, cân nhắc cache ngắn hoặc kiểm tra trực tuyến thường xuyên hơn.

## 7. Lifetime phải phù hợp với mục tiêu revocation

Trước khi chọn TTL, hãy trả lời câu hỏi: sau khi token bị đánh cắp hoặc quyền bị thu hồi, hệ thống chấp nhận token cũ còn hoạt động tối đa bao lâu?

### Mô hình JWT offline

Nếu không có denylist, introspection hoặc trạng thái trực tuyến, thời gian còn lại đến `exp` là giới hạn tự nhiên của token. Khi token vừa được phát hành rồi quyền bị thu hồi, cửa sổ có thể gần bằng toàn bộ TTL cộng dung sai đồng hồ mà verifier cho phép.

### Mô hình introspection có cache

Nếu resource server cache trạng thái active, độ trễ thu hồi có thể gồm thời gian phát sự kiện, invalidation và phần TTL cache còn lại. Cần đo propagation thực tế, không chỉ xem cấu hình cache.

### Mô hình authorization version

Token có thể chứa `client_authz_version`, `tenant_authz_version` hoặc `membership_version` tùy thiết kế. Khi quyền thay đổi, hệ thống tăng version và resource server so sánh với trạng thái hiện tại. Claim version không có tác dụng nếu resource server không lấy được version hiện tại từ nguồn tin cậy.

### Chọn TTL từ revocation SLO

Ví dụ tổ chức đặt mục tiêu: token của thao tác quản trị không được tiếp tục hoạt động quá 2 phút sau khi quyền bị thu hồi. Nếu resource server xác minh JWT hoàn toàn offline và không có denylist/version check, TTL và clock skew phải được giới hạn để đáp ứng mục tiêu đó. Nếu TTL 15 phút, kiến trúc hiện tại không thể đáp ứng SLO 2 phút chỉ bằng `exp`.

Nếu yêu cầu thu hồi trong vài giây, rút TTL xuống vài giây có thể gây tải và độ phức tạp lớn. Thường cần trạng thái trực tuyến, introspection/cache invalidation hoặc authorization decision ngắn hạn thay vì chỉ tiếp tục giảm TTL.

## 8. Công thức giới hạn thời hạn token mới

Authorization server có thể tính thời hạn token mới từ TTL policy và các mốc quyền nền tảng. Một cách biểu diễn:

```text
candidate_exp = issued_at + policy_ttl

new_exp = min(
  candidate_exp,
  session_exp,
  grant_exp,
  subject_token_exp,
  actor_token_exp,
  delegation_exp
)
```

Đây là mẫu chính sách, không phải công thức bắt buộc của RFC. Chỉ đưa vào phép tính các mốc thực sự áp dụng. Ví dụ không có `actor_token` thì không có `actor_token_exp`; một workload service-to-service không có user session thì không có `session_exp` tương ứng.

Khi token mới đại diện cho quyền được ủy quyền từ subject hoặc actor token, hệ thống thường nên bảo đảm token mới không sống lâu hơn quyền ủy quyền còn hiệu lực, trừ khi có grant độc lập và chính sách cho phép rõ ràng. Không dùng Token Exchange để vô tình kéo dài một quyền đã hết hạn.

### Ví dụ tính thời hạn

Giả sử authorization server cần cấp access token cho Payments API:

| Giới hạn | Thời điểm |
|---|---:|
| Thời điểm phát hành | 10:00:00 |
| TTL policy cho Payments API | 5 phút |
| Hết hạn theo TTL policy | 10:05:00 |
| Subject token hết hạn | 10:03:00 |
| Session/grant hết hạn | 10:20:00 |
| Thời hạn actor/delegation | 10:04:00 |

Nếu policy yêu cầu quyền token mới không vượt quá subject token và delegation, `new_exp` là 10:03:00. Token chỉ sống khoảng 3 phút, dù TTL tối đa của Payments API là 5 phút.

Nếu subject token còn hạn đến 10:30:00 và các giới hạn khác đều cho phép, token mới có thể hết hạn lúc 10:05:00. `expires_in` trong response phải phản ánh thời lượng thực tế được cấp, không phải TTL tối đa cấu hình.

## 9. Lifetime cho các mô hình client khác nhau

### Browser và SPA

Browser là môi trường public client; không thể giữ client secret an toàn trong JavaScript. Token có thể bị lộ qua XSS, extension, dependency bên thứ ba hoặc storage. Cần cân nhắc:

- Access token ngắn hạn và scope/audience hẹp.
- Authorization Code Flow với PKCE.
- BFF để giữ access/refresh token phía server nếu kiến trúc phù hợp.
- Nếu SPA giữ refresh token, áp dụng rotation/reuse detection hoặc sender constraint theo khả năng provider.
- Tránh lưu token dài hạn trong `localStorage` nếu threat model không chấp nhận XSS đọc token.
- Không đặt token trong URL, fragment, analytics hoặc browser history.

Rút access token TTL mà vẫn để XSS lấy refresh token có thể không giảm nhiều rủi ro. Cần bảo vệ cả token cấp mới và nơi lưu refresh token.

### Ứng dụng native/mobile

Thiết bị di động có thể offline, mất thiết bị hoặc bị compromise. Cần dùng Authorization Code Flow với PKCE, secure storage do hệ điều hành cung cấp, refresh token rotation/sender constraint khi hỗ trợ và cơ chế phát hiện thiết bị/rủi ro. TTL cần cân bằng giữa trải nghiệm offline và thời gian credential có thể bị lạm dụng nếu thiết bị mất.

### Backend confidential client

Backend có thể xác thực client bằng secret, private key hoặc mTLS. Access token thường được cấp theo nhu cầu và cache trong bộ nhớ hoặc kho an toàn với TTL. Không nên nhúng client secret vào code hoặc log. Nếu credential client bị lộ, attacker có thể liên tục lấy token mới; cần rotation/disable client chứ không chỉ giảm access token TTL.

### Service-to-service và workload

Workload thường có thể lấy token mới tự động bằng Client Credentials hoặc workload identity. Điều này cho phép access token ngắn hạn mà không yêu cầu user tương tác. Cần:

- Audience riêng cho từng service hoặc resource.
- Scope tối thiểu theo công việc.
- TTL ngắn phù hợp với mức nhạy cảm.
- Credential/workload identity có rotation và quản lý vòng đời.
- Cache token theo `client + audience + scope` để tránh gọi token endpoint quá thường xuyên.
- Không chia sẻ token giữa workload không cùng trust boundary.

Job kéo dài nhiều giờ không cần một access token sống nhiều giờ. Worker có thể lấy token mới trước khi token hiện tại hết hạn, miễn grant và workload identity còn hợp lệ.

## 10. Lifetime và sender-constrained token

Bearer token có thể được sử dụng bởi bất kỳ bên nào sở hữu chuỗi token. Sender-constrained token như DPoP hoặc mTLS ràng buộc token với một khóa hoặc certificate, giúp giảm khả năng attacker dùng token bị đánh cắp ở môi trường khác.

Sender constraint có thể cho phép risk assessment khác với bearer thuần, nhưng không làm token miễn nhiễm:

- Private key hoặc certificate có thể bị đánh cắp cùng token.
- Thiết bị hoặc workload có thể bị kiểm soát.
- Proof có thể bị triển khai sai hoặc replay nếu không kiểm tra đúng.
- Token vẫn có scope/audience quá rộng hoặc lifetime không phù hợp.

Vì vậy, sender constraint là một yếu tố giảm risk, không phải lý do tự động kéo dài TTL. Hãy đánh giá khả năng bảo vệ khóa, cách lưu trữ, replay protection và mức độ kiểm soát thiết bị/workload.

## 11. Clock skew và thời điểm refresh

Các service có thể lệch đồng hồ vài giây do đồng bộ thời gian, network hoặc runtime. Resource server có thể cho phép một khoảng clock skew nhỏ khi kiểm tra `exp`/`nbf`, nhưng cần thống nhất và giới hạn.

Nguyên tắc:

- Đồng bộ đồng hồ bằng NTP hoặc cơ chế thời gian được quản trị.
- Chọn clock skew nhỏ theo sai lệch đo được; không dùng dung sai lớn để kéo dài token.
- Client refresh sớm hơn thời điểm hết hạn với một safety margin.
- Không tính `exp` bằng đồng hồ client không đáng tin cậy.
- Không chấp nhận token hết hạn chỉ vì một service cache kết quả validation quá lâu.

Ví dụ client nhận `expires_in=300` giây. Có thể lập lịch refresh trước hạn một khoảng an toàn dựa trên network latency và jitter; không nên cố định một con số lớn hơn TTL hoặc refresh liên tục khi còn nhiều thời gian.

Với nhiều request đồng thời, client nên dùng single-flight hoặc cơ chế đồng bộ để chỉ một luồng refresh token. Nếu mọi request cùng refresh, có thể xảy ra race với refresh token rotation và token cũ bị đánh dấu reuse.

## 12. Token cache và hiệu năng

TTL ngắn làm tăng tần suất cấp token. Cần thiết kế cache phù hợp nhưng không biến cache thành lý do giữ token quá hạn.

Cache key nên bao gồm các thuộc tính quyết định quyền, ví dụ:

```text
cache_key = client_id + audience + normalized_scope + subject_context
```

Không dùng chung token nếu audience, scope, tenant hoặc subject context khác nhau. Cache entry cần có thời điểm hết hạn, eviction và bảo vệ bộ nhớ. Khi token bị revoke hoặc client/tenant bị disable, hệ thống cần invalidation theo policy.

Không cache access token lâu hơn `exp`/`expires_in`. Nếu cache token trong nhiều service, phải tính cả thời gian đồng bộ và khả năng token bị lộ trong memory dump, diagnostic snapshot hoặc heap dump.

### Backoff và jitter

Nếu mọi workload cùng khởi động và token cùng hết hạn một lúc, authorization server có thể nhận một đợt request lớn. Client có thể thêm jitter vào thời điểm refresh sớm, nhưng không được sử dụng token sau thời điểm hết hạn. Khi token endpoint lỗi, retry phải có giới hạn, backoff và tôn trọng lỗi grant/client; không retry vô hạn với refresh token đã bị tiêu thụ.

## 13. Lifetime cho thao tác đặc quyền và step-up authentication

Một user có session hợp lệ không có nghĩa mọi thao tác đều nên dùng cùng một access token và cùng một mức assurance.

Đối với thao tác nhạy cảm như thay đổi phương thức MFA, cấp quyền admin, tạo client secret hoặc thay đổi thông tin thanh toán, có thể yêu cầu:

- Xác thực lại gần thời điểm thao tác.
- Step-up authentication với yếu tố mạnh hơn.
- Kiểm tra `auth_time` và `max_age` theo OIDC khi phù hợp.
- Quyền tạm thời/JIT access thay vì role admin thường trực.
- Access token có scope/audience riêng và TTL ngắn.
- Phê duyệt bổ sung và audit event chi tiết.

Không nên chỉ dựa vào việc access token còn hạn để kết luận user vừa xác thực gần đây. Token có thể được phát hành trước đó và còn hiệu lực dù phiên đăng nhập đã cũ. Freshness của authentication là một thuộc tính riêng với token lifetime.

## 14. Lifetime trong Token Exchange và delegation

Token Exchange có thể tạo access token mới dành cho resource downstream. Token mới có lifetime do authorization server quyết định theo audience, scope, subject, actor và policy delegation.

Khi thiết kế:

- TTL của token downstream không vượt quá giới hạn delegation/session/grant liên quan nếu quyền phụ thuộc vào chúng.
- Mỗi audience có thể có TTL khác nhau theo risk của resource.
- Scope của token mới không rộng hơn quyền được ủy quyền.
- Actor token và subject token phải còn hợp lệ tại thời điểm exchange.
- Exchange lại phải kiểm tra trạng thái client, tenant và grant hiện tại.
- Không tạo chuỗi exchange để kéo dài quyền vô hạn qua nhiều service.

Ví dụ: Gateway nhận token cho phép đọc đơn hàng và exchange sang token chỉ dành cho Shipping API. Shipping token có thể có TTL ngắn hơn token nguồn vì thao tác downstream có risk cao. Việc token nguồn còn 20 phút không buộc token mới phải sống 20 phút.

## 15. Quy trình ra quyết định lifetime

Một quy trình nhất quán giúp tránh chọn TTL chỉ dựa trên thói quen hoặc một giá trị mặc định cũ.

1. **Xác định mục đích token:** access, refresh, ID token, client assertion hay token exchange.
2. **Xác định resource và hành động:** API nào, dữ liệu nào, read/write/admin/export hay thao tác đặc quyền.
3. **Phân loại tác động:** hậu quả nếu token bị đánh cắp, replay hoặc tiếp tục hoạt động sau khi quyền bị thu hồi.
4. **Đánh giá exposure:** loại client, nơi lưu token, network boundary, logging và khả năng bảo vệ khóa.
5. **Xác định revocation objective:** token cũ được phép tiếp tục hoạt động tối đa bao lâu sau revoke/disable.
6. **Chọn cơ chế xác minh:** JWT offline, introspection, denylist, authorization version hoặc kết hợp.
7. **Đề xuất TTL và refresh policy:** chọn giá trị khởi điểm, idle/absolute lifetime và rotation.
8. **Kiểm tra năng lực vận hành:** token endpoint throughput, latency, cache, network failure và job duration.
9. **Kiểm thử threat scenarios:** token theft, replay, expiry boundary, revoke, refresh race, client/tenant disable.
10. **Đo lường và phê duyệt:** theo dõi issuance/refresh/error, ghi rationale và owner của policy.
11. **Rà soát định kỳ:** cập nhật khi scope, resource, client type, threat model hoặc yêu cầu pháp lý thay đổi.

### Mẫu quyết định

| Trường | Ví dụ cần ghi |
|---|---|
| Token type | JWT access token |
| Client type | Confidential backend workload |
| Audience | `payments-api` |
| Scope | `payments.read` |
| Risk tier | Cao |
| Exposure | Token trong memory của workload, secret manager bảo vệ client credential |
| Validation mode | JWT offline + client authorization version |
| Revocation objective | Chặn token cũ trong tối đa 2 phút |
| Access token TTL | Giá trị được phê duyệt sau khi kiểm thử SLO |
| Refresh policy | Client Credentials re-authentication; không cấp refresh token nếu không cần |
| Clock skew | Dung sai nhỏ theo sai lệch đồng hồ đo được |
| Owner/review date | Service owner và security reviewer |

Mẫu này giúp người review hiểu vì sao TTL được chọn và điều kiện nào khiến phải xem xét lại.

## 16. Quan sát và vận hành lifetime policy

Sau khi triển khai, cần đo liệu lifetime có đang tạo ra mức bảo vệ và chi phí vận hành mong muốn hay không.

Metric hữu ích:

- Số access token được cấp theo client, audience và grant type ở mức cardinality được kiểm soát.
- Phân bố `expires_in` hoặc TTL được cấp theo policy tier.
- Tỷ lệ request bị từ chối do token hết hạn.
- Tỷ lệ refresh thành công/thất bại và refresh token reuse detection.
- Latency và error rate của token endpoint, introspection và JWKS.
- Cache hit/miss, token refresh concurrency và số lần retry.
- Thời gian từ revoke/disable đến khi resource server cuối cùng từ chối token.
- Số request được xác minh bằng token cũ sau khi policy version thay đổi.

Không đưa raw token, `jti`, user ID hoặc client secret vào metric label. Dùng nhóm service, grant type, risk tier và reason code hữu hạn. Nếu cần điều tra token cụ thể, dùng audit reference hoặc fingerprint an toàn.

### Dấu hiệu TTL quá dài

- Token vẫn được chấp nhận quá lâu sau khi user/client/tenant bị disable.
- Token bị lộ có thể truy cập nhiều API hoặc scope trong thời gian dài.
- Revocation objective không đáp ứng do JWT offline.
- Token cache giữ credential vượt thời hạn.

### Dấu hiệu TTL quá ngắn

- Token endpoint nhận request tăng đột biến.
- Client thường xuyên gặp 401 do token hết hạn giữa request.
- Refresh race/reuse detection tăng.
- API latency tăng vì introspection hoặc token acquisition.
- Job dài bị gián đoạn dù workload identity và grant vẫn hợp lệ.

Điều chỉnh TTL cần đi cùng thay đổi cache, refresh scheduling, audience/scope hoặc revocation architecture. Không chỉ tăng TTL để xử lý token endpoint quá tải nếu nguyên nhân là client refresh đồng loạt hoặc cache sai.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng một TTL cho mọi API và client | Token quyền cao có cửa sổ lạm dụng quá dài; API ít nhạy cảm có thể refresh quá thường xuyên. | Phân loại theo risk, client và resource. |
| Chọn TTL chỉ để giảm tải token endpoint | Credential bị lộ có thể tồn tại quá lâu. | Tối ưu cache và refresh concurrency; giữ TTL theo risk. |
| Nghĩ JWT có chữ ký thì không cần TTL ngắn | JWT offline có thể được chấp nhận đến `exp` sau revoke. | Kết hợp TTL với introspection/version/denylist theo yêu cầu. |
| Nghĩ opaque token luôn thu hồi tức thời | Cache introspection có thể giữ trạng thái active cũ. | Đặt cache TTL và invalidation theo revocation objective. |
| Rút access token TTL nhưng để refresh token vô hạn | Attacker có refresh token vẫn lấy access token mới. | Idle/absolute lifetime, rotation, reuse detection và revoke grant. |
| Dùng access token làm session lifetime | Session có thể bị kéo dài hoặc kết thúc sai kỳ vọng. | Quản lý session idle/absolute lifetime độc lập. |
| Dùng ID token gọi API | Nhầm mục đích và audience; resource server có thể chấp nhận sai token. | Chỉ dùng access token dành cho API. |
| Clock skew quá lớn | Token hết hạn vẫn được chấp nhận lâu hơn dự kiến. | Đồng bộ clock và dung sai nhỏ có giới hạn. |
| Không tính thời hạn subject/actor khi exchange | Token downstream có thể kéo dài quyền ủy quyền ngoài dự kiến. | Áp dụng giới hạn session/grant/delegation phù hợp. |
| Token scope rộng và TTL ngắn | Quyền vẫn quá rộng trong cửa sổ ngắn. | Thu hẹp audience và scope trước, sau đó chọn TTL. |
| Sender-constrained token được coi là không thể bị đánh cắp | Khóa hoặc thiết bị vẫn có thể bị compromise. | Bảo vệ khóa, kiểm tra proof và vẫn đặt TTL phù hợp. |
| Client refresh đồng thời | Rotation race, reuse detection hoặc tải tăng đột biến. | Single-flight, cache và jitter có kiểm soát. |
| Không có metric lifetime | Không biết TTL có đáp ứng risk và SLO không. | Theo dõi TTL cấp ra, expiry, refresh và revocation delay. |

## 18. Ma trận kiểm thử lifetime

| Tình huống | Kết quả mong đợi |
|---|---|
| Token còn hạn và đúng issuer/audience/scope | Được chấp nhận nếu policy hiện tại cho phép. |
| Token đã đạt/vượt `exp` | Bị từ chối theo quy tắc thời gian và clock skew đã cấu hình. |
| Token có `nbf` trong tương lai | Bị từ chối cho đến khi có hiệu lực. |
| Token sắp hết hạn | Client chủ động refresh/re-auth trước hạn theo safety margin. |
| `expires_in` nhỏ hơn TTL tối đa do subject token sắp hết hạn | Client nhận và tuân theo thời hạn thực tế được cấp. |
| Refresh token hết idle lifetime | Token endpoint từ chối refresh. |
| Refresh token vượt absolute lifetime | Không cấp access token mới; yêu cầu xác thực lại theo policy. |
| Refresh token bị dùng lại sau rotation | Reuse detection và token family revocation hoạt động theo policy. |
| JWT offline bị revoke trước `exp` | Resource server từ chối theo denylist/version/status check hoặc cửa sổ residual TTL được đo. |
| Opaque token bị revoke | Introspection trả inactive; cache không vượt revocation objective. |
| Introspection timeout | Hành vi fail-closed hoặc policy đã phê duyệt; không giả định token valid. |
| Client/tenant bị disable | Không refresh/exchange/cấp token mới; token cũ bị chặn theo cơ chế đã chọn. |
| Token Exchange từ subject/actor sắp hết hạn | Token mới bị giới hạn bởi policy delegation/session/grant. |
| Hai request refresh đồng thời | Client không tạo race không kiểm soát; xử lý single-flight/rotation đúng. |
| Đồng hồ service lệch trong giới hạn | Token hợp lệ không bị từ chối ngoài dự kiến. |
| Đồng hồ lệch quá giới hạn | Hệ thống cảnh báo và không mở rộng thời hạn vô hạn. |
| Job chạy dài hơn access token TTL | Workload lấy token mới khi grant còn hợp lệ; job không cần token sống suốt nhiều giờ. |

Kiểm thử nên bao gồm biên thời gian ngay trước, đúng tại và ngay sau `exp`, `nbf`, idle timeout và absolute timeout. Dùng clock có thể điều khiển trong test thay vì chờ thời gian thực.

## 19. Checklist phê duyệt lifetime policy

**Risk và quyền**

- Đã phân loại dữ liệu và hành động theo tác động nếu token bị lạm dụng.
- Audience/resource và scope được thu hẹp đến mức cần thiết.
- Đã đánh giá client type, token storage và khả năng bị lộ.
- Đã xem xét sender constraint nếu phù hợp.

**Thời hạn và vòng đời**

- Access token TTL có rationale theo risk.
- Refresh token có idle và absolute lifetime.
- Rotation/reuse detection được áp dụng khi cần.
- Session lifetime được quản lý độc lập với access token.
- Token Exchange không kéo dài quyền delegation ngoài dự kiến.
- Clock skew nhỏ, được đo và cấu hình nhất quán.

**Thu hồi và vận hành**

- Revocation objective được xác định bằng thời gian tối đa chấp nhận.
- JWT offline có TTL hoặc cơ chế bổ sung để đáp ứng objective.
- Introspection cache và event propagation có giới hạn độ trễ rõ ràng.
- Token cache không vượt hạn và không trộn audience/scope/tenant.
- Có metric expiry, refresh, issuance, revocation và dependency health.
- Có owner và lịch review khi threat model hoặc quyền thay đổi.

**Kiểm thử**

- Có test boundary `exp`/`nbf`, refresh idle/absolute và rotation.
- Có test revoke, client/tenant disable và Token Exchange.
- Có test clock skew, token endpoint outage và concurrent refresh.
- Có test job dài, token cache và behavior khi token gần hết hạn.

## 20. Kết luận

Chọn lifetime theo risk là quyết định cân bằng giữa thời gian token có thể bị lạm dụng, khả năng thu hồi, mức độ bảo vệ client và chi phí vận hành. Access token cho quyền nhạy cảm cần thời hạn ngắn và phạm vi hẹp; refresh token cần idle/absolute lifetime, rotation và reuse detection; ID token, session, authorization code và client assertion có mục đích và vòng đời riêng.

TTL phải được chọn cùng với cách xác minh token. JWT xác minh offline thường cần TTL ngắn hơn hoặc cơ chế thu hồi bổ sung; opaque token với introspection có thể phản ánh trạng thái tập trung nhưng vẫn bị ảnh hưởng bởi cache. Token Exchange cần giữ giới hạn delegation. Cuối cùng, hãy đo lường expiry, refresh, revocation delay và lỗi thực tế để xác nhận policy đáp ứng risk và SLO đã phê duyệt.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token response, `expires_in`, refresh token và grant.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sử dụng bearer token và nguy cơ khi token bị lộ.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim `exp`, `nbf`, `iat` và NumericDate.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi access token và refresh token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): truy vấn trạng thái token và thuộc tính `active`.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject token, actor token và token được phát hành qua exchange.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claim bắt buộc.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token bằng DPoP.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, client và thực hành OAuth 2.0 hiện hành.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `auth_time`, `max_age` và authentication freshness.
