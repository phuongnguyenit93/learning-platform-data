# Mô phỏng incident rồi thực hiện revoke

Trong dự án thực hành này, bạn sẽ điều tra một access token có dấu hiệu bị đánh cắp, xác định refresh token đã bị replay, thu hồi token family và xác minh các Resource Server ngừng chấp nhận credential bị ảnh hưởng. Bài tập đi qua toàn bộ vòng phản ứng: phát hiện, bảo toàn evidence, khoanh vùng, revoke, kiểm tra propagation và lập báo cáo sau sự cố.

Dự án thuộc chương **Dự án thực hành** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung thực hành với JWT, opaque access token, refresh token rotation, OAuth 2.0 revocation và token introspection. Toàn bộ bài tập sử dụng dữ liệu giả trong môi trường local/lab cô lập; không dùng token, tài khoản hoặc endpoint production.

## 1. Mục tiêu và kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Nhận diện các sự kiện cho thấy token có thể bị đánh cắp hoặc phát lại.
- Liên kết access token với subject, client, session và refresh-token family bằng fingerprint an toàn.
- Phân biệt token hết hạn, token bị revoke và token bị từ chối vì sai audience/scope.
- Thực hiện revoke refresh token hoặc token family tại Authorization Server.
- Giải thích vì sao revoke refresh token không tự động làm mọi JWT access token đang phát hành mất hiệu lực tức thì.
- Kiểm tra trạng thái revoke qua introspection hoặc cơ chế denylist/version check.
- Xác minh mọi Resource Server instance và cache đã nhận trạng thái thu hồi.
- Viết incident report có timeline, phạm vi ảnh hưởng, hành động và bằng chứng xác minh.

**Điều kiện hoàn thành:** token bị compromise không thể tiếp tục được dùng theo chính sách revoke của lab; refresh token cũ không thể phát hành access token mới; các service đích từ chối credential bị ảnh hưởng; evidence không chứa bearer token dạng rõ.

## 2. Kịch bản incident

Một người dùng giả lập `user-1042` đăng nhập vào ứng dụng `web-client`. Authorization Server cấp access token và refresh token thuộc session `session-77`, token family `family-77`.

1. Người dùng dùng refresh token `RT-01` để xin access token mới. Authorization Server rotation thành công, đánh dấu `RT-01` đã sử dụng và cấp `RT-02`.
2. Một request khác dùng lại `RT-01` sau rotation từ nguồn mạng lạ. Đây là refresh-token reuse.
3. `orders-api` ghi nhận access token của session này được dùng từ hai nguồn có hành vi không tương thích; một số request truy cập dữ liệu nhạy cảm.
4. Đội vận hành phải xác định phạm vi, revoke token family, xử lý access token đã phát hành và xác minh các API không còn chấp nhận credential bị ảnh hưởng.

Các giá trị ID, IP, thời gian và token trong lab đều là dữ liệu giả. Dùng fingerprint để liên kết sự kiện; không lưu hoặc đưa token thật vào log, ticket hay báo cáo.

## 3. Mô hình lab

| Thành phần | Trách nhiệm |
| --- | --- |
| Authorization Server (AS) | Phát hành access/refresh token, quản lý token family, rotation và revocation |
| orders-api | Resource Server nhận access token và kiểm tra quyền đọc đơn hàng |
| billing-api | Resource Server thứ hai để kiểm tra revoke propagation trên nhiều service |
| Event store / audit log | Lưu security event đã redact, timeline và kết quả điều tra |

~~~mermaid
flowchart LR
    U["Lab client"] -->|"Login / refresh"| AS["Authorization Server"]
    AS -->|"Access token"| U
    U -->|"Bearer token"| O["orders-api"]
    U -->|"Bearer token"| B["billing-api"]
    AS -->|"Introspection / revoke state"| O
    AS -->|"Introspection / revoke state"| B
    AS --> E["Security events"]
    O --> E
    B --> E
    E --> IR["Incident response"]
~~~

### Trạng thái token trong lab

| Đối tượng | Trạng thái ban đầu | Sau rotation | Sau incident revoke |
| --- | --- | --- | --- |
| `RT-01` | ACTIVE | ROTATED/USED | REVOKED hoặc REUSE_DETECTED |
| `RT-02` | Chưa tồn tại | ACTIVE | REVOKED cùng family |
| Access token AT-01 | ACTIVE | Có thể còn hiệu lực đến exp | REVOKED theo policy của lab |
| Access token AT-02 | Chưa tồn tại | ACTIVE | REVOKED theo policy của lab |
| `family-77` | ACTIVE | ACTIVE | REVOKED |
| `session-77` | ACTIVE | ACTIVE | REVOKED |

Trạng thái cụ thể phụ thuộc cách Authorization Server quản lý token. Khi phát hiện reuse của refresh token đã rotation, lab áp dụng policy cho cả family vì server không thể mặc nhiên biết request nào là chủ hợp pháp và request nào là kẻ đánh cắp.

## 4. Chuẩn bị môi trường và quy tắc an toàn

Trước khi bắt đầu:

- Dùng Authorization Server, Resource Server và event store chạy local hoặc môi trường sandbox riêng.
- Tạo user, OAuth client, signing key và refresh token chỉ dành cho lab.
- Dùng HTTPS local/test nếu lab hỗ trợ TLS; không gửi credential qua mạng công cộng.
- Tắt tích hợp với issuer, database hoặc API production.
- Không dùng access token/refresh token từ tài khoản thật.
- Không ghi raw token, Authorization header, client secret hoặc private key vào log.
- Chuẩn bị thao tác reset dữ liệu lab để có thể chạy lại từ trạng thái ban đầu.

Nếu lab dùng JWT, tạo token bằng signing key test và giữ private key ngoài source control. Nếu lab dùng opaque token, lưu token ngẫu nhiên và chỉ lưu fingerprint/HMAC trong audit event.

### Dữ liệu giả lập

| Thuộc tính | Giá trị lab |
| --- | --- |
| Subject | `user-1042` |
| OAuth client | `web-client` |
| Session | `session-77` |
| Refresh-token family | `family-77` |
| Refresh token đầu | `RT-01` |
| Refresh token sau rotation | `RT-02` |
| Resource servers | `orders-api`, `billing-api` |
| Access scopes | `orders:read`, `billing:read` |
| Incident ID | `INC-2026-0077` |

`RT-01` và `RT-02` chỉ là nhãn tham chiếu. Khi thực hành, chương trình phải sinh token ngẫu nhiên thực tế; không dùng các chuỗi nhãn này làm bearer credential.

## 5. Bước 1 — Tạo phiên và token ban đầu

Đăng nhập user giả lập qua Authorization Code Flow với PKCE hoặc dùng helper cấp token dành riêng cho test. Ghi nhận:

- Subject và client đã xác thực.
- Session ID và refresh-token family ID.
- Access token audience và scope.
- Thời điểm phát hành, thời hạn access token và refresh token.
- Token fingerprint/HMAC để đối chiếu event.

Ví dụ metadata access token JWT sau khi được xác minh:

~~~json
{
  "iss": "https://as.lab.example/",
  "sub": "user-1042",
  "aud": ["orders-api", "billing-api"],
  "client_id": "web-client",
  "scope": "orders:read billing:read",
  "iat": 1795400000,
  "exp": 1795400900,
  "jti": "at-01",
  "sid": "session-77"
}
~~~

Payload chỉ là ví dụ đã giải mã, không phải bằng chứng xác thực. Resource Server phải xác minh chữ ký, issuer, audience, thời gian, loại token và quyền theo cấu hình. Không tin payload chỉ vì có thể decode.

Gọi thử hai API:

~~~http
GET /api/orders HTTP/1.1
Host: orders.lab.example
Authorization: Bearer <LAB_ACCESS_TOKEN>
~~~

~~~http
GET /api/billing/summary HTTP/1.1
Host: billing.lab.example
Authorization: Bearer <LAB_ACCESS_TOKEN>
~~~

Kết quả ban đầu phải thành công nếu token và scope được cấu hình đúng. Ghi lại request ID, kết quả, service và token fingerprint; redact header Authorization trước khi log.

## 6. Bước 2 — Rotation refresh token

Dùng refresh token đầu tiên để xin access token mới. Authorization Server thực hiện rotation:

1. Xác minh refresh token, client binding, session và trạng thái token family.
2. Đánh dấu refresh token cũ đã được sử dụng.
3. Phát hành refresh token mới thuộc cùng family.
4. Phát hành access token mới theo audience/scope được phép.
5. Ghi security event cho lần rotation.

Request minh họa:

~~~http
POST /oauth/token HTTP/1.1
Host: as.lab.example
Authorization: Basic <LAB_CLIENT_AUTH>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<LAB_REFRESH_TOKEN_RT_01>
~~~

Response mẫu:

~~~json
{
  "access_token": "<LAB_ACCESS_TOKEN_AT_02>",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "<LAB_REFRESH_TOKEN_RT_02>"
}
~~~

Sau response, client phải lưu refresh token mới một cách nguyên tử và loại bỏ bản cũ khỏi state đang sử dụng. Không cho nhiều thread hoặc tab đồng thời refresh cùng một token nếu ứng dụng chưa có cơ chế đồng bộ.

Kiểm tra audit event cho thấy:

- Family vẫn là `family-77`.
- `RT-01` được đánh dấu USED/ROTATED.
- `RT-02` trở thành refresh token hiện hành.
- Không có raw token trong log.

## 7. Bước 3 — Mô phỏng dấu hiệu compromise

Tạo hai sự kiện trong lab.

**Sự kiện A: replay refresh token cũ.** Gửi lại `RT-01` sau khi đã rotation thành công. Authorization Server phải nhận diện token đã dùng và phát hiện reuse.

~~~http
POST /oauth/token HTTP/1.1
Host: as.lab.example
Authorization: Basic <LAB_CLIENT_AUTH>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<LAB_REFRESH_TOKEN_RT_01>
~~~

Kết quả mong đợi: request bị từ chối theo policy, thường là lỗi grant không hợp lệ; server phát event `refresh.reuse_detected` và liên kết với `family-77`. Không tiết lộ token còn hợp lệ hay không cho bên gọi.

**Sự kiện B: access token có hành vi bất thường.** Gửi request đến Resource Server với AT-01 hoặc AT-02 từ một client test giả lập nguồn khác. Tạo event với:

- Cùng token fingerprint nhưng nguồn mạng/thiết bị khác baseline.
- Request ID và thời điểm khác nhau.
- API và hành động được gọi.
- Kết quả xác thực và authorization.

Không cần tạo lưu lượng lớn. Chỉ tạo vài request có kiểm soát để chứng minh correlation và cảnh báo.

## 8. Bước 4 — Điều tra và bảo toàn evidence

Trước khi revoke, lập timeline từ các event có liên quan. Không sao chép bearer token vào báo cáo.

| Thời điểm | Event | Evidence cần kiểm tra |
| --- | --- | --- |
| T0 | User login | Subject, client, session, family, issuer, audience |
| T1 | Refresh rotation thành công | Fingerprint cũ/mới, trạng thái USED/ACTIVE, request ID |
| T2 | Refresh token cũ được gửi lại | Reuse detection, client auth, nguồn request, family ID |
| T3 | Access token được dùng từ nguồn bất thường | Fingerprint, service, source context, scope, hành động |
| T4 | Incident được mở | Incident ID, owner, mức độ rủi ro, phạm vi ban đầu |

### Câu hỏi điều tra

1. Refresh token cũ có thực sự đã rotation trước lần sử dụng lại không?
2. Hai request có cùng token family và client không?
3. Có thể là retry đồng thời hoặc race condition từ client hợp lệ không?
4. Access token nào được phát hành từ family/session bị ảnh hưởng?
5. Service nào đã chấp nhận các token đó và trong khoảng thời gian nào?
6. Token có được dùng để truy cập tenant hoặc dữ liệu ngoài phạm vi thông thường không?
7. Có dấu hiệu client secret, private key hoặc session cookie cũng bị lộ không?

Refresh token reuse sau rotation là tín hiệu mạnh, nhưng cần xem xét concurrency và retry behavior. Khi policy yêu cầu containment ngay, hãy revoke family và điều tra tiếp sau; không trì hoãn biện pháp bảo vệ chỉ để hoàn tất mọi câu hỏi.

## 9. Bước 5 — Thực hiện revoke

Chọn phạm vi revoke dựa trên evidence và khả năng liên kết token:

| Phạm vi | Khi dùng | Hành động |
| --- | --- | --- |
| Một access token | Chỉ một token cụ thể bị lộ và có thể định danh | Revoke token hoặc chặn theo jti/fingerprint |
| Một refresh token | Một refresh token bị lộ nhưng policy không cần thu hồi cả family | Revoke token; kiểm tra token mới liên quan |
| Refresh-token family | Phát hiện reuse sau rotation hoặc nghi compromise cả phiên | Revoke family và mọi refresh token còn hoạt động trong family |
| Session/grant | Cần chấm dứt phiên ủy quyền của user/client | Revoke session/grant theo chính sách AS |
| Client credential | Client secret/private key của workload bị lộ | Disable/rotate credential, kiểm tra grant và token liên quan |

Trong kịch bản này, chọn **revoke toàn bộ `family-77` và `session-77`** vì refresh token cũ đã bị replay sau rotation. Authorization Server cần đánh dấu RT-01 và RT-02 không còn sử dụng được, chặn cấp token mới từ family đó và ghi audit event.

### Gọi OAuth 2.0 Token Revocation Endpoint

RFC 7009 định nghĩa revocation endpoint. Client được xác thực theo yêu cầu của Authorization Server và gửi token cần revoke qua HTTPS:

~~~http
POST /oauth/revoke HTTP/1.1
Host: as.lab.example
Authorization: Basic <LAB_CLIENT_AUTH>
Content-Type: application/x-www-form-urlencoded

token=<LAB_REFRESH_TOKEN_RT_02>&token_type_hint=refresh_token
~~~

Response thành công thường là:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Theo RFC 7009, response 200 không cho client biết token trước đó có hợp lệ hay đã được revoke hay chưa; endpoint tránh tiết lộ trạng thái token. Cách revoke toàn bộ family/session khi một refresh token bị revoke phụ thuộc policy Authorization Server. Nếu AS hỗ trợ revoke family/session riêng, dùng API quản trị nội bộ đã được bảo vệ và audit; không giả định một lần gọi RFC 7009 luôn tự động revoke mọi token liên quan.

Trong lab, thực hiện cả hai phần theo policy:

1. Revoke refresh token hiện hành và family `family-77`.
2. Thu hồi session `session-77` và ngăn cấp refresh token mới từ session đó.
3. Đánh dấu các access token đã phát hành từ family/session bị ảnh hưởng để Resource Server có thể từ chối theo cơ chế đã chọn.
4. Ghi actor vận hành, incident ID, lý do, thời điểm và phạm vi revoke.

Không đưa token thật vào command history hoặc shell transcript nếu môi trường có thể lưu lịch sử. Dùng fixture/secret injection của lab.

## 10. Bước 6 — Xử lý access token đã phát hành

Đây là bước dễ bị bỏ sót. Revoke refresh token ngăn việc xin access token mới bằng refresh token đó. Nó **không tự động làm mọi JWT access token tự chứa đang được Resource Server xác minh offline mất hiệu lực ngay lập tức**.

Chọn cơ chế theo loại access token:

### Opaque access token

Resource Server gọi introspection endpoint hoặc kiểm tra trạng thái qua cơ chế được Authorization Server cung cấp. Sau revoke, response phải thể hiện token không còn active:

~~~json
{
  "active": false
}
~~~

Nếu Resource Server cache kết quả introspection, phải xác định TTL và cách invalidate cache; nếu không, token có thể còn được chấp nhận trong khoảng cache stale.

### JWT access token tự chứa

JWT có thể được xác minh offline bằng chữ ký, issuer, audience và thời gian. Nếu Resource Server không kiểm tra trạng thái bên ngoài, token đã ký vẫn có thể được chấp nhận cho đến exp.

Để revoke sớm, kiến trúc có thể dùng một hoặc kết hợp các cơ chế:

- Denylist theo jti hoặc token fingerprint tại Resource Server.
- Session/authorization version check theo sid hoặc subject/session state.
- Event revoke được phát tới gateway và mọi Resource Server, kèm cache invalidation.
- Introspection hoặc authorization-state check cho endpoint nhạy cảm.
- Access token lifetime ngắn để giới hạn cửa sổ còn hiệu lực khi không thể revoke tức thì.

Không coi việc xóa signing key hoặc xoay toàn bộ issuer key là cách revoke một token thông thường; hành động đó có thể làm vô hiệu hàng loạt token và gây outage. Chỉ thực hiện key rotation khẩn cấp khi private signing key thực sự bị compromise, theo quy trình riêng.

### Ví dụ kiểm tra denylist

Logic minh họa ở Resource Server sau khi JWT đã được xác minh:

~~~java
public void rejectIfRevoked(Jwt verifiedJwt) {
    String jwtId = verifiedJwt.getId();
    String sessionId = verifiedJwt.getClaimAsString("sid");

    if (jwtId != null && revocationStore.isTokenRevoked(jwtId)) {
        throw new InvalidBearerTokenException("Token revoked");
    }

    if (sessionId != null && revocationStore.isSessionRevoked(sessionId)) {
        throw new InvalidBearerTokenException("Session revoked");
    }
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thật, `revocationStore` cần có tính sẵn sàng, cache TTL rõ ràng, key namespace an toàn và kiểm soát lỗi. Nếu không truy cập được store, quyết định fail-open/fail-closed phải được xác định theo mức độ nhạy cảm của API; không để từng service tự chọn khác nhau.

## 11. Bước 7 — Xác minh revoke propagation

Sau khi AS báo revoke thành công, không kết thúc incident ngay. Kiểm tra từng đường truy cập và từng instance:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Dùng RT-01 để refresh | Bị từ chối; reuse event được ghi |
| Dùng RT-02 để refresh | Bị từ chối vì family/session đã revoke |
| Dùng AT-01 gọi orders-api | Bị từ chối theo revoke policy |
| Dùng AT-02 gọi orders-api | Bị từ chối theo revoke policy |
| Dùng AT-01 gọi billing-api | Bị từ chối theo revoke policy |
| Dùng AT-02 gọi billing-api | Bị từ chối theo revoke policy |
| Introspection opaque token liên quan | active=false |
| Kiểm tra denylist/session state | Token/session được đánh dấu revoked |
| Kiểm tra cache trên các instance | Không còn kết quả active cũ vượt quá SLA propagation |
| Login/session mới | Người dùng phải xác thực lại trước khi có token mới |

Nếu một instance vẫn chấp nhận token, ghi nhận instance, cache key, thời điểm event revoke đến và nguyên nhân. Không chỉ kiểm tra gateway; cần xác minh cả service có thể được gọi trực tiếp trong mạng nội bộ.

Đặt một SLA revoke propagation cụ thể cho hệ thống, ví dụ vài giây cho API nhạy cảm, và đo từ thời điểm AS xác nhận revoke đến khi mọi Resource Server từ chối token. Con số thực tế phải dựa trên kiến trúc, cache TTL và yêu cầu nghiệp vụ; không dùng giá trị ví dụ như cam kết mặc định.

## 12. Bước 8 — Hoàn tất incident và báo cáo

Sau khi containment và propagation được xác minh, ghi incident report tối thiểu:

~~~text
Incident ID: INC-2026-0077
Status: CONTAINED
Affected subject: user-1042
OAuth client: web-client
Session: session-77
Refresh-token family: family-77
Detection: refresh token reuse after rotation + unusual access-token use
Actions:
  - Revoked refresh-token family
  - Revoked session/grant
  - Invalidated related access-token state
  - Verified orders-api and billing-api reject affected tokens
Evidence:
  - Event IDs and request IDs
  - HMAC token fingerprints
  - Revoke timestamp and propagation checks
Secrets recorded: none
Follow-up:
  - Review client refresh concurrency
  - Review browser/device token storage
  - Review access-token lifetime and revoke cache policy
~~~

Không đưa raw token, client secret, private key hoặc session cookie vào report. Chỉ dùng ID tham chiếu, fingerprint đã bảo vệ và event ID.

Việc khôi phục có thể yêu cầu user đăng nhập lại, kiểm tra thiết bị, đổi credential nếu có bằng chứng lộ secret và xác nhận không còn request đáng ngờ. Không tự động mở lại session cũ sau khi đã revoke.

## 13. Các lỗi thường gặp khi thực hiện revoke

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ revoke refresh token hiện hành | Token family hoặc session liên quan vẫn có thể còn credential hoạt động | Áp dụng family/session policy khi phát hiện reuse |
| Nghĩ revoke JWT ở AS sẽ lập tức chặn mọi API | Resource Server offline có thể vẫn chấp nhận JWT đến exp | Denylist, introspection, version check hoặc lifetime ngắn |
| Chỉ kiểm tra một Resource Server | Service khác vẫn chấp nhận token | Kiểm tra tất cả API và instance trong phạm vi |
| Cache introspection quá lâu | Token revoked vẫn được chấp nhận | TTL ngắn và cache invalidation theo event |
| Ghi raw token để tìm trong log | Log trở thành nơi chứa bearer credential | Dùng HMAC fingerprint và request ID |
| Revoke toàn bộ user khi chỉ một client bị ảnh hưởng | Tác động lan rộng, khóa nhầm phiên khác | Khoanh vùng theo client/session/family và mở rộng khi evidence yêu cầu |
| Không xử lý refresh concurrency | Client hợp lệ có thể tự kích hoạt reuse detection | Single-flight refresh và atomic token replacement |
| Không kiểm tra token sau revoke | Không biết containment đã có hiệu lực ở API hay chưa | Chạy propagation verification trên từng Resource Server |

## 14. Bộ kiểm thử nghiệm thu

Chạy các ca kiểm thử sau trong lab sau khi reset dữ liệu:

| ID | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| LAB-01 | Login và gọi API bằng access token hợp lệ | 200 theo scope |
| LAB-02 | Rotate refresh token một lần | Token cũ chuyển USED/ROTATED, token mới ACTIVE |
| LAB-03 | Reuse refresh token cũ | Bị từ chối và phát hiện reuse |
| LAB-04 | Revoke token family/session | Mọi refresh token còn hoạt động trong family bị vô hiệu hóa |
| LAB-05 | Dùng refresh token mới sau revoke | Không cấp access token mới |
| LAB-06 | Dùng opaque access token đã revoke | Introspection trả active=false |
| LAB-07 | Dùng JWT access token đã revoke | Resource Server từ chối theo denylist/version/introspection policy |
| LAB-08 | Gọi hai Resource Server sau revoke | Cả hai đều từ chối token bị ảnh hưởng |
| LAB-09 | Gọi một instance có cache stale | Cache được invalidate trong SLA; không tiếp tục chấp nhận token |
| LAB-10 | Kiểm tra audit/log | Có timeline và actor, không có raw token/secret |
| LAB-11 | Đăng nhập phiên mới sau containment | Chỉ token mới từ phiên được xác thực lại mới được chấp nhận |
| LAB-12 | Mô phỏng revoke endpoint nhận token không hợp lệ | Response không tiết lộ token có tồn tại hay không theo RFC 7009 |

### Tiêu chí nghiệm thu

- Không có refresh token cũ hoặc mới trong family bị revoke nào có thể phát hành token mới.
- Resource Server áp dụng đúng chính sách với access token liên quan; cửa sổ propagation được đo và nằm trong SLA.
- Không có log, trace, report hoặc metric nào chứa bearer token dạng rõ.
- Incident report có đủ event ID, request ID, fingerprint, hành động và kết quả.
- Có thể reset lab và chạy lại toàn bộ kịch bản.

## 15. Dọn dẹp lab

Sau khi hoàn thành:

1. Revoke toàn bộ token, session và grant giả lập.
2. Xóa user/client fixture và dữ liệu test theo cơ chế reset của lab.
3. Xóa private key/certificate test khỏi thư mục tạm theo quy trình.
4. Xác minh không còn token trong log, shell history, screenshot hoặc artifact được lưu ngoài ý muốn.
5. Giữ lại incident report đã redact và kết quả test để phục vụ review.

Không dùng token test sau khi reset. Nếu lab dùng key ký test dùng chung cho nhiều bài, chỉ xóa khi không còn bài nào phụ thuộc; không thay đổi key ngoài phạm vi lab này.

## 16. Tài liệu chuẩn tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation endpoint, request và response.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): kiểm tra trạng thái token tại Resource Server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token rotation, reuse detection và biện pháp bảo vệ OAuth.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): sử dụng và bảo vệ Bearer access token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): xác minh JWT access token tại Resource Server.
