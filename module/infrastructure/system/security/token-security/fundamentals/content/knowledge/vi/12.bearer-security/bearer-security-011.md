# Thu hồi sau khi nghi ngờ lộ token

Khi nghi ngờ **access token** hoặc **refresh token** bị lộ, điều nguy hiểm nhất là nghĩ rằng “token có chữ ký nên vẫn an toàn” hoặc “đã logout thì mọi bản sao tự mất hiệu lực”. Với **bearer token**, bất kỳ bên nào có bản sao token hợp lệ đều có thể thử sử dụng nó theo quyền được cấp, cho đến khi Resource Server hoặc Authorization Server (AS) có cơ chế từ chối. Thu hồi token là quá trình **làm mất khả năng sử dụng credential đã cấp**, ngăn phát hành token mới từ grant bị lộ, và xác minh hiệu lực thu hồi tại các điểm thực thi.

Bài học **“Thu hồi sau khi nghi ngờ lộ token”** thuộc chương **Bearer security** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung vận dụng mô hình tin cậy OAuth 2.0/OpenID Connect (OIDC), sự khác nhau giữa JWT và opaque token, access/refresh token, phát hành và kiểm tra issuer, audience, scope, claims, lưu trữ, vòng đời và phòng chống đánh cắp hoặc phát lại.

**Điểm cần nhớ ngay:** thu hồi ở AS **không mặc nhiên** có nghĩa mọi API đang xác minh JWT ngoại tuyến sẽ từ chối token tức thì. Kế hoạch ứng phó phải nói rõ **thu hồi token nào, tại thành phần nào, hiệu lực từ thời điểm nào và API nhận biết trạng thái mới bằng cách nào**.

## 1. “Nghi ngờ lộ token” là tình huống gì?

Một token có thể bị lộ mà chưa có bằng chứng đã bị sử dụng. Vì bearer token là một khả năng truy cập (*capability*), chỉ cần bị sao chép cũng có thể tạo rủi ro.

Các tín hiệu điển hình:

- Access token/refresh token xuất hiện trong log, error report, trace, clipboard, ảnh chụp màn hình, bản ghi hỗ trợ khách hàng hoặc tài liệu có người không đủ quyền truy cập.
- Token được gửi nhầm sang API, miền, proxy, analytics endpoint hoặc webhook không thuộc bên nhận hợp lệ.
- Mã độc, XSS, extension, thiết bị bị mất hoặc sự cố lưu trữ làm token trong browser/native app có thể bị đọc.
- Hệ thống phát hiện **refresh token reuse** sau rotation; một token cũ bị dùng lại ngoài kỳ vọng.
- Một access token được sử dụng từ nhiều nguồn hoặc có hành vi bất thường theo chính sách, ví dụ tăng tốc độ xuất dữ liệu, đổi tenant, gọi endpoint nhạy cảm.
- Client credential hoặc khóa ký liên quan bị lộ, làm xuất hiện khả năng kẻ khác xin/phát hành token trái phép.

**Không cần chờ chứng minh chắc chắn đã có tấn công mới thu hồi credential nghi lộ.** Tuy nhiên, mức xử lý phải dựa trên loại token, scope/audience, thời hạn còn lại, khả năng attacker có cả khóa ràng buộc hay không, mức nhạy cảm dữ liệu và ảnh hưởng tới người dùng.

### Ba mục tiêu của ứng phó

1. **Containment:** chặn token bị nghi ngờ ở nơi có thể dùng, ngăn cấp thêm token qua refresh/grant/client credential liên quan.
2. **Investigation:** bảo toàn bằng chứng và xác định phạm vi thực sự: token nào, client/user/tenant nào, audience, scope, các API đã gọi, thời gian, hành vi đáng ngờ.
3. **Recovery:** cấp lại credential hoặc yêu cầu xác thực lại qua kênh tin cậy, xử lý nguyên nhân lộ và kiểm tra rằng các Resource Server đã thực thi trạng thái mới.

Không đánh đồng **đổi mật khẩu**, **logout**, **hết hạn token**, **thu hồi refresh token**, **thu hồi access token** và **vô hiệu hóa client**; mỗi hành động có điểm tác động khác nhau.

## 2. Trước hết phải phân loại credential bị lộ

| Loại hiện vật | Ai thường chấp nhận? | Rủi ro khi bị sao chép | Hướng ứng phó chính |
|---|---|---|---|
| **Bearer access token** | Resource Server có audience phù hợp | Truy cập API trong scope/thời gian hợp lệ | Chặn token tại API bằng introspection/denylist/state, hạn chế tài nguyên và theo dõi đến hết hạn |
| **Refresh token** | AS token endpoint | Xin thêm access token trong phạm vi grant, có thể kéo dài truy cập | Revoke refresh token/family/grant theo chính sách; ngăn refresh tiếp, xét access token đã phát hành |
| **ID token (OIDC)** | OIDC client được chỉ định | Lộ thông tin định danh trong JWT; có nguy cơ lạm dụng nếu hệ thống nhận sai purpose | Bảo vệ session, kiểm tra nơi nhận/nonce, không coi ID token là access token; xử lý phiên nếu liên quan |
| **Authorization code** | AS token endpoint | Có thể bị đổi thành token nếu attacker thỏa ràng buộc client/PKCE | Code dùng một lần, hạn ngắn, kiểm tra client/redirect/PKCE; hủy giao dịch/code khi nghi lộ |
| **Client secret hoặc private key của client** | AS khi client authentication | Giả mạo confidential client; xin token nếu grant/policy cho phép | Disable/rotate credential, giới hạn client, rà token/grant được cấp qua credential đó |
| **Khóa ký token của AS** | Verifier tin issuer | Có thể giả mạo nhiều token; phạm vi vượt một token đơn lẻ | Quy trình khẩn cấp rotate/distribute signing keys, vô hiệu hóa token liên quan và đánh giá toàn bộ miền tin cậy |

**Định dạng JWT hay opaque không quyết định đây là access hay refresh token.** JWT là định dạng chứa claims có thể được ký/mã hóa; opaque có thể là mã tham chiếu. AS và API cần xác định **purpose** theo hợp đồng bảo mật, không suy đoán từ số dấu chấm hoặc việc Base64url decode được.

Đặc biệt, với **ID token** không được tự suy rằng RFC 7009 sẽ thu hồi nó như một access token. ID token dành cho client OIDC; nếu lộ kèm cookie hoặc access token thì ứng phó phải nhắm vào các hiện vật thực sự bị ảnh hưởng và phiên liên quan.

## 3. Đường đi của token và điểm cần thực thi thu hồi

~~~mermaid
flowchart LR
    U["User / Admin"]
    C["Client: orders-web"]
    AS["Authorization Server"]
    API["Orders Resource Server"]
    STATE[("Token / grant / revocation state")]
    DB[("Orders + ACL")]

    U -->|"Phát hiện / yêu cầu gỡ quyền"| AS
    C -->|"Revoke refresh token (nếu có quyền)"| AS
    AS -->|"Ghi trạng thái revoke"| STATE
    AS -->|"Cấp token chỉ nếu grant hợp lệ"| C
    C -->|"Bearer access token"| API
    API -->|"JWT verifier hoặc introspection"| STATE
    API -->|"Scope + quyền trên order"| DB
~~~

Trong thực tế, API có thể không đọc trực tiếp cùng cơ sở dữ liệu với AS. Nó có thể:

- **Introspect opaque token** từ AS qua kênh tin cậy.
- **Tự xác minh JWT** và tra denylist/token-state/grant-state bổ sung.
- **Nhận tín hiệu revocation** qua cache đồng bộ, event bus hoặc cơ chế back-channel riêng.
- **Chấp nhận token đến lúc hết hạn** nếu kiến trúc không hỗ trợ chặn sớm; đây phải là **giới hạn được nhận diện rõ**, không được mô tả là thu hồi ngay.

**Phân biệt quyết định của AS và API:** AS ngừng cấp token mới không có nghĩa JWT access token đã cấp tự biến mất khỏi bộ nhớ attacker. Chỉ nơi đang kiểm tra request API mới thực sự từ chối được access token đó.

## 4. Đánh giá mức độ khẩn cấp và phạm vi tác động

Không phải mọi sự cố đều cần đăng xuất tất cả người dùng; cũng không phải token ngắn hạn nào cũng có thể bỏ qua. Một bảng triage gợi ý:

| Tín hiệu | Cần xác minh | Hành động containment thường phù hợp |
|---|---|---|
| Access token `orders:read` lộ trong log giới hạn nội bộ | Log đã được ai xem? Token còn hạn? API có kiểm tra revoke? | Cô lập log, chặn token tại API nếu có thể; rà request trong cửa sổ rủi ro |
| Refresh token xuất hiện trong error report gửi bên thứ ba | Ai truy cập được? Token family nào, rotation trạng thái gì? | Thu hồi refresh token/family hoặc grant theo policy; xem xét access token đã phát hành |
| Token có scope xuất dữ liệu/xóa hoặc quyền admin bị lộ | Scope, audience, tenant, hiệu lực và hành động gần đây | Ưu tiên chặn sớm, kiểm tra API nhạy cảm, cô lập client/grant nếu cần |
| Nghi thiết bị user bị chiếm quyền | Cookie phiên, refresh token, DPoP key, mã độc có còn hiện diện? | Chấm dứt phiên liên quan, revoke grant/token, yêu cầu đăng nhập lại trên thiết bị tin cậy |
| Nhiều client/token có dấu hiệu đồng thời | Có lộ secret, signing key, JWKS hoặc môi trường phát hành không? | Mở rộng phạm vi điều tra, rotate credential/keys theo tình huống, dừng phát hành sai |
| Chỉ thấy refresh token reuse trong hai request sát nhau | Có concurrent refresh hợp lệ/race condition? | Tạm cô lập family theo policy, kiểm tra request correlation; không kết luận attacker khi chưa có bằng chứng |

Xác định **blast radius** dựa trên:

- **Token purpose và audience:** bị dùng tại API nào; token API A không nên hợp lệ tại API B.
- **Scope và quyền tài nguyên:** `orders:read`, `orders:export`, quản trị tenant; API vẫn cần ACL/object-level authorization.
- **Subject/client/tenant:** user-delegated grant hay `client_credentials` của service.
- **TTL và trạng thái:** `iat`, `nbf`, `exp`, refresh token family, lần cuối sử dụng và revocation propagation.
- **Kiểu token:** opaque tra trạng thái hay JWT tự xác minh; có denylist/binding hay không.
- **Nguồn nghi lộ:** sao chép nguyên token, mất cả private key/thiết bị, hay chỉ thông tin về claims đã bị đọc.
- **Ảnh hưởng người dùng:** số tài khoản, hệ thống, thao tác đã thực hiện và nghĩa vụ báo cáo theo chính sách/luật áp dụng.

Một token JWS lộ *payload đã decode* không đồng nghĩa kẻ xem có **toàn bộ chuỗi bearer token**. Nhưng việc công khai toàn bộ JWT compact string vẫn là lộ credential có thể bị replay, dù payload không chứa bí mật.

## 5. Playbook khi vừa phát hiện nghi ngờ lộ token

Thứ tự dưới đây là **nguyên tắc vận hành**, không phải một SLA cố định áp dụng cho mọi hệ thống.

1. **Ghi nhận sự cố:** tạo incident ID, thời gian phát hiện UTC, nguồn cảnh báo, hệ thống/tenant nghi ảnh hưởng và người chịu trách nhiệm; không paste nguyên token vào ticket.
2. **Bảo vệ bằng chứng:** khóa quyền xem log chứa token, ngừng việc token tiếp tục bị ghi/sao chép; giữ các bản ghi cần thiết bằng quy trình forensic và kiểm soát truy cập.
3. **Xác định loại credential:** access/refresh/ID/code/client secret/AS signing key; phân biệt JWT, opaque và sender-constrained.
4. **Xác định scope/audience và thời hạn:** từ **metadata đã xác minh** hoặc AS, không suy đoán từ chuỗi tự decode; đối chiếu client, subject và grant.
5. **Chặn đường sử dụng gần nhất:** revoke token/grant/refresh family, đưa access token đang còn hạn vào cơ chế từ chối sớm ở API khi cần, vô hiệu hóa phiên/client theo mức độ sự cố.
6. **Ngăn tái phát hành:** nếu RT hoặc credential client bị lộ, chỉ revoke access token là chưa đủ; phải xử lý refresh grant và khả năng xin token mới.
7. **Kiểm tra propagation:** thử sử dụng token test đã bị thu hồi qua đúng các API/gateway; kiểm tra cache/introspection, node không nhận event, kết quả `401`/`403` đúng policy.
8. **Điều tra việc đã sử dụng:** rà audit log AS/RS bằng token reference, client, scope, audience, tenant, request correlation và cửa sổ thời gian; phân biệt login hợp lệ và hành vi bất thường.
9. **Khôi phục an toàn:** chỉ cấp lại credential/cho user đăng nhập lại sau khi xử lý nguyên nhân rò rỉ, cập nhật secret/key/storage và áp dụng MFA/step-up khi cần.
10. **Kết thúc và cải tiến:** ghi nhận nguyên nhân gốc, tác động thực tế/giới hạn chưa biết, thời gian chặn, người nhận thông báo và kiểm thử phòng ngừa tái diễn.

**Ưu tiên containment trước điều tra kéo dài** khi rủi ro nghiêm trọng. Tuy nhiên, không được xóa toàn bộ bằng chứng hoặc ngừng vận hành một hệ thống lớn mà không có quyết định theo quy trình incident-response của tổ chức.

### Cách xác nhận không còn đường truy cập

Không chỉ nhìn thấy “revoke API trả HTTP 200”. Cần xác minh cả:

- AS không cho refresh token/grant đã bị thu hồi tiếp tục cấp access token mới.
- Mọi Resource Server liên quan đã chặn token nếu policy yêu cầu thu hồi sớm, bao gồm gateway, API instance và downstream resource.
- Cookie phiên/BFF session của thiết bị liên quan đã được xử lý nếu attacker có thể dùng session để xin token mới.
- Không còn client secret/private key bị lộ đang được tin cậy cho flow có thể tái phát hành token.
- Các request đang xử lý dở, cache và worker nền có giới hạn rủi ro được ghi nhận.

## 6. OAuth 2.0 Token Revocation Endpoint — RFC 7009

**RFC 7009** định nghĩa revocation endpoint để client yêu cầu AS thu hồi token. Endpoint này làm việc với **token thuộc hệ thống AS**, không phải API nghiệp vụ, và không có nghĩa bất kỳ người gửi nào cũng được quyền thu hồi token tùy ý.

Ví dụ một confidential client thu hồi **refresh token** của chính nó:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ENCODED_CLIENT_CREDENTIALS>

token=<REFRESH_TOKEN>&token_type_hint=refresh_token
~~~

Giải thích:

- Gửi request bằng **HTTP POST qua HTTPS** với form-url-encoding, không đặt token trong query URL.
- Với confidential client, AS cần xác thực client theo phương thức đã đăng ký; các cơ chế và quyền của public client phụ thuộc policy.
- `token` là **giá trị token cần thu hồi**, phải được bảo vệ khi truyền, không log raw request.
- `token_type_hint=refresh_token` chỉ giúp AS xác định nơi tìm token nhanh hơn; **đó là gợi ý**, không phải bằng chứng token đúng loại.
- AS phải kiểm tra token có thuộc phạm vi client được phép thu hồi; không được để client A revoke token của client B chỉ vì biết chuỗi token.

Ví dụ response thành công:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

Theo RFC 7009, AS có thể trả **HTTP 200 ngay cả khi token đã vô hiệu hoặc không tìm thấy**, để tránh tiết lộ trạng thái tồn tại của token cho caller. Vì thế **`200` không chứng minh mọi Resource Server đã từ chối token**; phải kiểm tra cả trạng thái server và thời gian đồng bộ.

Trường hợp AS không hỗ trợ thu hồi loại token được gửi, có thể có lỗi `unsupported_token_type` theo RFC. Nếu dịch vụ không thể xử lý revocation do lỗi vận hành, caller cần retry/đưa vào hàng đợi theo chính sách; không coi yêu cầu thất bại là đã thu hồi thành công.

### Thu hồi một token hay cả authorization grant?

RFC 7009 có quy tắc và khả năng liên quan **token khác cùng authorization grant**; mức độ tác động phụ thuộc AS, loại token và khả năng thu hồi được hỗ trợ. Ví dụ khi revoke refresh token và AS hỗ trợ revocation access token, AS nên vô hiệu hóa các access token dựa trên cùng grant theo quy tắc RFC. Tuy vậy, **JWT tự xác minh tại API vẫn cần cơ chế nhận biết trạng thái thu hồi**; không thể chỉ dựa vào việc bản ghi grant đã đổi trong cơ sở dữ liệu AS.

**Không đánh đồng** các API sau:

- **Token revocation endpoint (RFC 7009):** client yêu cầu revoke một token theo giao thức.
- **Admin / incident-management revocation:** giao diện hoặc API quản trị của AS để thu hồi toàn bộ grant, client, phiên, token family hoặc nhóm tài khoản; **không có một API chuẩn chung** cho mọi nhà cung cấp.
- **Logout / session termination:** kết thúc phiên người dùng tại app/AS, không tự đồng nghĩa với revoke mọi access token đã phát hành.

## 7. Thu hồi access token: opaque và JWT khác nhau

Phương án cần chọn dựa trên **khả năng AS/RS kiểm tra trạng thái**, không chỉ dựa trên tên định dạng.

| Cách kiểm tra tại API | Cách chặn token nghi lộ | Điểm mạnh | Giới hạn / rủi ro |
|---|---|---|---|
| **Opaque token + introspection** | AS chuyển token sang inactive, RS introspect và nhận `active: false` | Có thể cập nhật trạng thái trung tâm | Cache introspection làm thu hồi bị trễ; AS có thể thành dependency vận hành |
| **JWT tự xác minh, TTL ngắn** | Đợi `exp` hoặc buộc cấp token ngắn hơn từ đầu | Không cần gọi AS mỗi request | **Không chặn ngay** bản sao JWT còn hạn |
| **JWT + denylist theo token ID** | RS tra trạng thái `jti`/reference đã bị revoke | Chặn sớm token cụ thể | Cần lưu trữ, phân phối, TTL và chống lỗi cache/mất đồng bộ |
| **JWT + grant/session state** | RS từ chối nếu grant/user session đã bị revoke hoặc version/epoch không còn hợp lệ | Có thể thu hồi nhóm token | Phức tạp hơn, có thể ảnh hưởng nhiều token/request; đòi hỏi policy rõ |
| **JWT + online introspection/state lookup** | RS kiểm tra trạng thái tại AS/hệ thống tin cậy | Điều khiển động | Latency, availability, rate limit và cache; không còn hoàn toàn stateless |
| **Sender-constrained token (DPoP/mTLS)** | Ngăn dùng token sao chép đơn lẻ nếu thiếu khóa, đồng thời revoke khi nghi lộ | Giảm rủi ro replay | Nếu cả token và private key bị lộ thì vẫn nguy hiểm; không thay việc revoke |

### Với opaque access token

AS có thể trả `active: false` từ endpoint introspection:

~~~http
POST /introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <AUTHENTICATED_RESOURCE_SERVER>

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

~~~json
{
  "active": false
}
~~~

**Resource Server phải từ chối token `active:false`**. Khi cache introspection, nó có thể đang giữ bản ghi `active:true` trước thời điểm thu hồi. Do đó phải xác định **TTL cache tối đa**, có thể hủy cache theo event tin cậy và đo **revocation propagation delay** thực tế.

### Với JWT access token

Giả sử một JWT đã ký, có:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read orders:export",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "access-incident-17"
}
~~~

Ngay cả sau khi AS đánh dấu `jti` bị revoke, **chữ ký JWT vẫn có thể hợp lệ đến `exp`**. Nếu Orders API chỉ verify chữ ký, `iss`, `aud` và thời gian mà **không tra trạng thái revocation**, nó có thể vẫn chấp nhận bản sao token.

Vì vậy, muốn chặn sớm phải có cơ chế rõ ràng ở API: denylist token, kiểm tra grant/user session, tra trạng thái tập trung hoặc tín hiệu revocation được xác thực. **Không nên xoay signing key của cả AS chỉ để thu hồi một access token**; thao tác này có thể vô hiệu hóa rộng và gây gián đoạn, thích hợp hơn trong sự cố khóa ký bị lộ theo kế hoạch riêng.

### Khóa tra denylist có gì cần lưu ý?

- Với JWT `jti`, dùng **issuer + token purpose + token identifier** (và audience/tenant khi cần) làm namespace, tránh vô tình đụng ID giữa issuer hoặc profile.
- Nếu không có `jti` tin cậy, có thể dùng **pseudonym được tính bằng HMAC với khóa bảo mật riêng từ raw token** ở thành phần tin cậy; không lưu bearer token nguyên văn trong log/denylist.
- Chỉ sử dụng claim `jti` và danh tính issuer **sau khi signature và claims cần thiết đã được xác minh**; không để client tùy ý gửi `jti` qua HTTP để tự xác nhận đã revoked.
- Thời gian giữ denylist ít nhất phải bao phủ **khoảng token còn có thể được chấp nhận** (bao gồm policy clock skew nếu có), tránh xóa quá sớm.
- Nếu muốn revoke theo grant/session, token phải có hoặc ánh xạ được tới **grant reference đáng tin cậy**; không tự bịa claim thiếu.

## 8. Độ trễ thu hồi là một yêu cầu bảo mật có thể đo được

Giả sử policy yêu cầu access token nghi lộ ngừng được chấp nhận không muộn hơn **30 giây** sau khi sự kiện revoke có hiệu lực. Chỉ ghi trạng thái ở AS chưa đủ; cần xét toàn bộ đường truyền:

~~~text
T_revoke_request
    -> T_AS_persisted
    -> T_event_published
    -> T_RS_cache_invalidated / introspection refreshed
    -> T_first_rejection_at_each_API_instance
~~~

**Revocation propagation delay** nên được đo từ **thời điểm trạng thái thu hồi có hiệu lực** tới lúc **các điểm nhận liên quan** không còn chấp nhận token. Cần kiểm tra gateway, cache, nhiều node, vùng địa lý, worker nền và service downstream.

Ví dụ cache introspection TTL = 60 giây có thể khiến policy 30 giây **không được bảo đảm**, trừ khi có invalidation đáng tin cậy hoặc phương thức chặn khác. Có thể thiết kế:

- Cache TTL nhỏ hơn giới hạn cần đạt, xét cả độ trễ mạng, đồng bộ, clock skew và các lỗi.
- Event revocation đẩy tới gateway/RS và xác nhận các node đã áp dụng, kèm cơ chế dự phòng.
- Online lookup cho endpoint nhạy cảm, hoặc đưa token có scope xuất/xóa vào denylist nóng.
- **Fail-closed có chủ đích** khi không thể kiểm tra trạng thái tại endpoint rủi ro cao; cân nhắc availability, mức gián đoạn và phương án khôi phục.
- Token TTL đủ ngắn theo threat model để giới hạn rủi ro còn lại nếu chặn sớm chưa được hỗ trợ.

**Không có một “TTL tốt nhất” dùng chung.** Chính sách cần được đánh giá theo quyền token, tải API, tần suất yêu cầu, khả năng AS/RS và hậu quả nếu token bị lạm dụng.

## 9. Refresh token bị lộ: chặn đường tái phát hành token mới

Một refresh token có thể nguy hiểm hơn access token ngắn hạn vì nó cho phép client xin **access token mới** mà không cần người dùng tương tác lại, trong giới hạn grant/policy và cách xác thực client.

Cần xử lý đồng thời:

1. **Revoke refresh token hiện tại** và xác định có rotation/token family hay không.
2. **Vô hiệu hóa family hoặc authorization grant liên quan** theo chính sách nếu có dấu hiệu reuse/chiếm quyền; không chỉ chặn một token cũ đã hết lượt.
3. **Từ chối refresh tại token endpoint** với token đã revoke, grant mất hiệu lực hoặc client không khớp.
4. **Rà những access token đã phát hành từ refresh** và chặn chúng sớm nếu API/AS hỗ trợ hoặc rủi ro yêu cầu.
5. **Xác minh client credential và phiên user:** nếu attacker có khả năng tiếp tục đăng nhập/cấp grant hoặc lấy token từ thiết bị, revoke RT đơn lẻ không ngăn tái xâm nhập.
6. **Đánh giá ảnh hưởng đến người dùng:** yêu cầu xác thực lại trên client/thiết bị tin cậy nếu cần, và không dùng session bị nghi chiếm quyền để xác minh thao tác khôi phục.

### Refresh token rotation và reuse detection

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client hợp lệ
    participant AS as Authorization Server
    participant A as Bên giữ bản sao RT1

    C->>AS: Refresh bằng RT1
    AS->>AS: Kiểm tra RT1 và invalidate RT1
    AS-->>C: Access token mới + RT2
    A->>AS: Thử dùng RT1 lại
    AS->>AS: Detect reuse trên token family
    AS-->>A: invalid_grant
    AS->>AS: Có thể revoke cả family/grant theo policy
~~~

**Cần phân biệt replay thật với race condition.** Hai request refresh hợp lệ được gửi đồng thời có thể cùng dùng RT1 nếu client không đồng bộ. AS cần có quy tắc xử lý an toàn, kết hợp log/timing/client context; đồng thời không được cho phép attacker khai thác khoảng “grace period” để duy trì quyền trái phép.

Với **public client**, các khuyến nghị bảo mật OAuth hiện đại yêu cầu bảo vệ refresh token khỏi replay bằng **rotation hoặc sender-constrained refresh token** tùy trường hợp. Với confidential client, AS vẫn phải xác thực client khi yêu cầu và ràng buộc refresh token với client đã được cấp.

### Revoke RT có đủ không?

Không chắc. Ví dụ:

- RT đã bị chặn nhưng **access token AT2 phát hành trước khi revoke vẫn còn hạn**.
- User còn **AS session hoặc app session** trên thiết bị bị nhiễm mã độc và có thể bắt đầu authorization flow mới.
- Client credential bị lộ làm attacker có thể lấy service token qua `client_credentials`, không phụ thuộc RT.
- API vẫn cache `active:true` cho opaque token hoặc bỏ qua denylist JWT.

Quy trình incident phải xét **từng khả năng cấp và dùng quyền**, không dựa vào một nút “Revoke” để bảo đảm mọi thứ kết thúc.

## 10. Logout, mật khẩu, consent và thu hồi không đồng nghĩa

| Hành động | Tác dụng trực tiếp thường gặp | Không nên mặc định |
|---|---|---|
| **Logout ứng dụng** | Hủy app session/cookie hoặc cache local | AS tự thu hồi mọi AT/RT đã phát hành |
| **Logout tại AS/SSO** | Kết thúc phiên đăng nhập tại AS | Tất cả JWT access token trên các API tự vô hiệu ngay |
| **Đổi/reset mật khẩu** | Thay credential để user xác thực lần sau | Mọi session, refresh token và access token cũ tự bị revoke |
| **Rút consent / revoke grant** | Chặn grant tiếp tục được sử dụng theo policy | API offline đã cập nhật trạng thái mọi token |
| **Revoke refresh token** | Ngăn dùng token đó để refresh (và token liên quan tùy AS) | Mọi access token đã phát hành lập tức bị chặn |
| **Revoke access token** | Chặn credential cụ thể nếu RS nhận biết được | Credential khác và grant bị vô hiệu luôn |
| **Disable client / rotate client secret** | Chặn client dùng credential cũ để xác thực tại AS | API đã chặn mọi AT đang còn hạn |
| **Hết `exp`** | Token không còn hợp lệ theo kiểm tra thời gian | Mọi bản sao token đã được xóa khỏi thiết bị/log |

Nếu sự cố xuất phát từ tài khoản bị chiếm, tổ chức có thể chọn **revoke toàn bộ refresh grants của user, chấm dứt các phiên bị ảnh hưởng, yêu cầu xác thực lại và chặn access token đang còn hạn**. Nhưng đó là **chính sách/quy trình cụ thể của AS/IdP**, không phải tác dụng tự động của việc user đổi mật khẩu.

Không được dùng **ID token** làm access token tại API và cũng không dùng thông tin `sub` từ ID token chưa verify để tự thực hiện revoke. Trong OIDC, client cần áp dụng đúng cách kiểm tra ID token và cơ chế logout nếu dùng; việc thu hồi OAuth token vẫn là bài toán riêng.

## 11. Khi nghi lộ khóa hoặc client credential: phạm vi có thể lớn hơn một token

### Lộ client secret hoặc private key của confidential client

Attacker có thể giả client tại token endpoint bằng phương thức đăng ký, nhất là với `client_credentials` hoặc khi còn grant/code/RT có thể sử dụng. Hành động cần cân nhắc:

- Disable/rotate credential đang nghi lộ tại AS, theo quy trình hỗ trợ cutover và ứng dụng hợp lệ.
- Rà các token được AS phát hành cho client trong cửa sổ nghi lộ, phân loại theo subject, audience, scope, grant type và thiết bị.
- Revoke các grant/refresh token/AT cần thiết, không chỉ đổi client secret rồi bỏ qua token đã cấp.
- Kiểm tra nguồn rò (secret manager, CI/CD log, container image, repo, máy chủ); giới hạn quyền và ghi nhận sử dụng credential.
- Với `private_key_jwt`, ngừng tin khóa công khai tương ứng khi xác nhận khóa riêng bị lộ, triển khai khóa mới và chống replay `jti` cho assertion.

### Nghi lộ khóa ký JWT của Authorization Server

Đây là tình huống **khác hẳn lộ một bearer token**. Attacker có thể tạo token giả với chữ ký trông hợp lệ nếu nắm private signing key và hệ thống verifier vẫn tin public key tương ứng.

Phải kích hoạt quy trình response cấp issuer:

1. Khoanh vùng khóa/`kid`, phạm vi issuer/audience, thời điểm nghi lộ và các verifier đang tin khóa.
2. Ngừng ký bằng khóa nghi lộ, phát hành và phân phối khóa tin cậy mới; điều phối cutover để tránh gián đoạn không kiểm soát.
3. Loại khóa đã lộ khỏi tập được tin cậy theo mức độ khẩn cấp, kiểm tra cache JWKS và các Resource Server chưa cập nhật.
4. Vô hiệu hóa/đổi trạng thái các token bị ảnh hưởng theo policy, kiểm tra nguy cơ forgery và grant/client compromise.
5. Rà audit ký/phát hành token, quyền truy cập HSM/secret store và tiến trình xuất bản JWKS.

**Không xử lý lộ signing key bằng cách chỉ gọi RFC 7009 cho một access token**, vì token giả mới có thể tiếp tục được tạo cho đến khi verifier ngừng tin khóa bị lộ.

## 12. API kiểm tra token sau khi sự cố được ghi nhận

Để revoke có hiệu lực, **Resource Server phải thực sự áp dụng quyết định từ chối**. Ví dụ API đơn hàng nhận:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Các lớp cần thực thi:

1. **Kiểm tra token purpose:** đây là access token đúng profile, không phải ID token, refresh token hoặc client assertion.
2. **Xác minh token:** với JWT kiểm tra chữ ký/thuật toán/issuer/audience/thời gian; với opaque gọi introspection/nguồn trạng thái tin cậy.
3. **Kiểm tra revocation:** `jti`/token reference/grant state/session version hoặc `active:false` theo kiến trúc. Với JWT chỉ verify chữ ký mà không tra trạng thái sẽ **không biết token đã bị revoke**.
4. **Kiểm tra sender constraint** nếu token ràng buộc DPoP/mTLS; không biến token-bound thành bearer thuần bằng cách bỏ proof.
5. **Kiểm tra scope:** token `orders:read` không đồng nghĩa `orders:export`; policy có thể thay đổi sau khi phát hành.
6. **Kiểm tra quyền tài nguyên:** user/service, tenant và ACL có cho phép đọc `order 123` tại thời điểm request không?
7. **Ghi audit an toàn:** lý do `REVOKED_TOKEN` khác `EXPIRED_TOKEN` hoặc `INSUFFICIENT_SCOPE`; không ghi raw token trong log.

~~~text
authenticateApiRequest(request):
    rawAccessToken = extractConfiguredAccessToken(request)
    verified = validateSignatureOrIntrospectionAndClaims(
        rawAccessToken,
        expectedIssuer,
        expectedAudience,
        expectedPurpose = ACCESS_TOKEN
    )
    if verified invalid: reject 401

    if tokenIsRevoked(verified.tokenRef, verified.grantRef):
        reject 401 // invalid_token; không tiếp tục phân quyền

    if verified.isSenderConstrained:
        verifyKeyPossessionForThisRequestOrReject()

    if not hasExactScope(verified.scopes, "orders:read"):
        reject 403

    if not policyMayReadOrder(verified.subject, orderId, tenant):
        reject 403 or 404 according to policy

    return requestedData
~~~

Đây là mã giả, không phải implementation có thể dùng ngay. **Không dùng `jti` chưa được xác minh** để quyết định bỏ qua/áp dụng trạng thái. Nguồn revocation phải do hệ thống tin cậy quản lý; client không được tự khai `revoked=false` hoặc `active=true`.

## 13. Java 17: mô hình kiểm tra revocation theo policy

Ví dụ minh họa một lớp thực thi **sau khi** bộ xác minh access token đã hoàn tất các bước mật mã/issuer/audience/time/type. Mục tiêu là làm rõ cách đưa **quyết định thu hồi** vào đường xử lý API, không phải tự viết thư viện JWT.

~~~java
import java.time.Instant;
import java.util.Set;

public final class RevocationAwareAuthorization {
    private RevocationAwareAuthorization() {}

    // Record này chỉ được lấy từ một token verifier đáng tin cậy.
    public record VerifiedAccess(
            String issuer,
            String audience,
            String tokenReference,
            String grantReference,
            String subject,
            Set<String> scopes,
            Instant expiresAt
    ) {}

    public enum RevocationStatus {
        ACTIVE,
        REVOKED,
        UNKNOWN // ví dụ state store không thể truy cập
    }

    public interface RevocationStatusService {
        RevocationStatus check(VerifiedAccess token);
    }

    public interface OrderPolicy {
        boolean canRead(String subject, String orderId);
    }

    public enum Decision {
        ALLOW,
        INVALID_TOKEN,
        INSUFFICIENT_SCOPE,
        FORBIDDEN
    }

    public static Decision checkSensitiveOrder(
            VerifiedAccess access,
            String orderId,
            RevocationStatusService revocation,
            OrderPolicy orderPolicy,
            Instant now
    ) {
        // Defense-in-depth; verifier trước đó vẫn phải kiểm tra
        // token type, signature/issuer/audience và sender constraint.
        if (!"https://auth.example.test".equals(access.issuer())
                || !"https://orders-api.example.test"
                        .equals(access.audience())
                || !access.expiresAt().isAfter(now)) {
            return Decision.INVALID_TOKEN;
        }

        RevocationStatus status = revocation.check(access);

        // Policy cho endpoint nhạy cảm: fail-closed nếu trạng thái
        // thu hồi không xác định. Endpoint khác có thể có SLA khác.
        if (status != RevocationStatus.ACTIVE) {
            return Decision.INVALID_TOKEN;
        }

        if (!access.scopes().contains("orders:read")) {
            return Decision.INSUFFICIENT_SCOPE;
        }

        if (!orderPolicy.canRead(access.subject(), orderId)) {
            return Decision.FORBIDDEN;
        }

        return Decision.ALLOW;
    }
}
~~~

Giới hạn bắt buộc hiểu đúng:

- `VerifiedAccess` chỉ là **hợp đồng đã xác minh**. Không tạo instance từ JWT Base64url decode hoặc nội dung client tự gửi. Cần middleware/verifier tin cậy thực hiện JWS/JWE/opaque validation, đúng purpose, issuer, audience, thời gian.
- `tokenReference`/`grantReference` không phải bearer token thô. Dịch vụ trạng thái phải biết cách xác thực nguồn và trả `ACTIVE`/`REVOKED`/`UNKNOWN`, không tự tin dữ liệu client khai.
- Ví dụ dùng **fail-closed** cho endpoint nhạy cảm khi kết quả `UNKNOWN`. Hệ thống thật cần chiến lược vận hành khi state store lỗi: timeout, retry, circuit breaker, cache TTL an toàn, metrics và thông báo phù hợp; không biến `UNKNOWN` thành `ACTIVE` một cách âm thầm.
- Nếu verifier xử lý nhiều audience, cần policy xác minh danh sách audience theo chuẩn; ví dụ so sánh một string chỉ biểu diễn một cấu hình API cụ thể.
- Hàm này chưa kiểm tra tenant, quyền export, rate limit hay DPoP/mTLS proof; các lớp đó phải được triển khai ở những điểm thích hợp.
- Quyết định trả `INVALID_TOKEN` không tự sinh HTTP response; API map sang `401` với Bearer challenge khi áp dụng, trong khi thiếu scope thường trả `403`.

Không chạy đoạn mã trên như một **cách revocation hoàn chỉnh**: việc cập nhật trạng thái AS, phân phối tới RS, auditing, xử lý error và race conditions vẫn phải do hệ thống thực tế đảm nhận.

## 14. Timeline sự cố: revoke xong nhưng token vẫn có thể còn tác dụng

Giả sử `orders-web` có access token JWT **AT1** cấp lúc **10:00 UTC**, hết hạn **10:15 UTC**, scope `orders:read orders:export`. Client còn refresh token **RT1**.

| Thời điểm UTC | Sự kiện | Trạng thái đáng chú ý |
|---|---|---|
| **10:00** | AS cấp AT1 và RT1 theo grant hợp lệ | AT1 còn hạn 15 phút |
| **10:04** | Một bản sao AT1 và RT1 nghi xuất hiện trong log bên thứ ba | Chưa chắc attacker đã dùng, nhưng đã có nguy cơ |
| **10:05** | Security team xác nhận phạm vi nghi lộ, cô lập log và kích hoạt incident | Chưa được tính là token đã bị chặn |
| **10:06:00** | AS revoke RT1/grant, đánh dấu AT1 trong denylist | Không được refresh RT1 nữa; trạng thái chặn đã ghi tại AS |
| **10:06:10** | Gateway A nhận cập nhật denylist | Request AT1 tại Gateway A bắt đầu bị từ chối |
| **10:06:25** | Resource Server B vẫn dùng cache trạng thái cũ hoặc chưa nhận event | AT1 **có thể vẫn được chấp nhận** ở B nếu không có kiểm tra bổ sung |
| **10:06:40** | Resource Server B nhận trạng thái và bắt đầu từ chối AT1 | Khi đó mới có bằng chứng chặn tại B |
| **10:15** | AT1 hết `exp` | JWT hết hạn ngay cả nếu bộ kiểm tra chặn sớm chưa thấy revocation |

Nếu policy yêu cầu mọi RS từ chối trong **30 giây** sau **10:06:00**, ví dụ trên **không đạt yêu cầu** vì B đến **10:06:40** mới từ chối. Điều này cho thấy cần đo từ **revocation effective time tới thời điểm từ chối tại từng điểm nhận**, không đo từ lúc operator bấm nút đến lúc AS trả `200`.

### Một sự cố còn đường tái phát hành

Giả sử attacker còn giữ phiên web trên thiết bị bị nhiễm mã độc. Dù RT1 đã bị revoke, kẻ đó có thể cố dùng session để chạy flow mới nếu AS/app chưa chấm dứt phiên liên quan. Vì vậy, khi nguồn rò là **compromised device/session**, containment có thể phải kết hợp **revoke grant + terminate session + yêu cầu authentication lại trên thiết bị sạch**, không chỉ revoke token family.

### Với opaque token

Nếu AT1 là opaque và tất cả API gọi introspection tại AS cho mỗi request, sau khi `active:false`, khả năng chặn có thể nhanh. Nhưng khi API cache `active:true` 60 giây, vẫn có độ trễ tương tự. **Định dạng token không tự hứa bảo đảm revocation realtime.**

## 15. Phát hiện replay, xác minh tác động và lưu bằng chứng

Sau containment, cần điều tra **token có bị sử dụng trái phép chưa** dựa trên bằng chứng từ thành phần tin cậy, không chỉ từ client.

### Nguồn dữ liệu nên đối chiếu

| Nguồn | Dữ liệu có ích | Giới hạn |
|---|---|---|
| AS token issuance/refresh/revocation audit | Client ID, grant ref, token ref/family, scope, audience, time, outcome | Không biết toàn bộ API usage nếu JWT được xác minh offline |
| RS/Gateway authorization audit | Token reference pseudonym, route template, `ALLOW/DENY`, reason, tenant, request ID | Cần tránh lộ raw token/PII; audit coverage có thể thiếu |
| Introspection/denylist access logs | Trạng thái token, cache hit, node, độ trễ áp dụng | Không nhất thiết ghi mọi request; cache có thể che hoạt động |
| Refresh rotation/reuse alerts | Token family, lần refresh và dấu hiệu dùng lại | Cần phân biệt race request hợp lệ |
| IAM/endpoint telemetry | Thiết bị/session, thay đổi credential, nghi malware | Có thể không kết luận được hành vi trên API |
| Data-plane audit | Những bản ghi đã đọc/sửa/xóa/xuất, số lượng và tenant | Phải đối chiếu object policy và phân quyền theo thời điểm |

**Không log raw** `Authorization` header, full access/refresh/ID token, client secret, private key, authorization code, PKCE verifier hoặc session cookie vào SIEM/ticket. Dùng `token_ref` do AS cấp hoặc pseudonym HMAC từ dữ liệu tin cậy theo chính sách, và xác thực ai có quyền xem dữ liệu liên kết.

### Tín hiệu cần cảnh báo

- `REFRESH_REUSE_DETECTED` với token family đã rotation.
- `ACCESS_AFTER_REVOKE`: API `ALLOW` sau thời điểm revoke có hiệu lực cộng ngưỡng độ trễ cho phép.
- `INVALID_AUDIENCE` tăng đột ngột, token gửi qua API không được cấp.
- Token reference có spike request hoặc truy cập endpoints nhạy cảm ngoài mẫu.
- Nhiều `INVALID_TOKEN` hoặc `REVOKED_TOKEN` liên tiếp sau response revoke.
- Resource Server/gateway không nhận được event revocation hoặc introspection cache vượt TTL.
- Client secret/private key bị sử dụng từ môi trường không hợp lệ hoặc token issuance tăng không phù hợp.

Cảnh báo không tự là bằng chứng phạm tội/tấn công; cần điều tra lỗi cấu hình, request retry, queue và đồng bộ thời gian. **Audit phải phân biệt “token đã bị nghi lộ”, “đã revoke tại AS” và “đã bị API từ chối”.**

## 16. Kế hoạch kiểm thử thu hồi trước khi gặp sự cố

Một cơ chế revoke chỉ đáng tin khi đã kiểm thử **hành vi thực** tại AS và các API.

| Test case | Thao tác kiểm thử | Kết quả mong đợi |
|---|---|---|
| **T1 — Revoke RT** | Revoke refresh token hợp lệ | Không refresh được nữa; AS trả lỗi grant phù hợp cho lần dùng sau |
| **T2 — Revoke token không tồn tại** | Gửi chuỗi không hợp lệ vào endpoint RFC 7009 đúng quyền | Phản hồi tránh lộ trạng thái theo chuẩn; không tạo quyền mới |
| **T3 — Cross-client revocation** | Client B thử revoke token của A | AS không cho B tác động token A |
| **T4 — JWT access token còn hạn** | Revoke AT rồi thử trên mọi RS/gateway | Nếu policy yêu cầu chặn sớm, tất cả RS từ chối trong SLA |
| **T5 — Opaque introspection** | Đánh dấu inactive, gọi API | Introspection trả `active:false` và API từ chối sau propagation cho phép |
| **T6 — Cache cũ** | Giữ cache `active:true` trước khi revoke | API không vượt quá độ trễ được phép; cache invalidation hoạt động |
| **T7 — Token family reuse** | Refresh RT1 → RT2, sau đó thử RT1 | AS phát hiện reuse và xử lý family theo policy |
| **T8 — Concurrent refresh** | Hai request hợp lệ dùng RT1 gần đồng thời | Không tạo đường dùng lại vô hạn; giảm false positive theo design |
| **T9 — Scope-sensitive endpoint** | Dùng token nghi lộ tại API xuất/xóa | Phương án chặn sớm được áp dụng theo policy rủi ro |
| **T10 — User session persists** | Revoke RT nhưng vẫn còn app/AS session | Kiểm thử rõ session có được hủy khi policy yêu cầu không |
| **T11 — Sender constraint** | Chỉ đánh cắp DPoP/mTLS-bound access token, không có khóa | API từ chối request thiếu proof/chứng chỉ |
| **T12 — Key also compromised** | Mô phỏng token và proof key bị lộ trong staging | Revoke/binding remediation ngăn tiếp tục truy cập |
| **T13 — Denylist state store unavailable** | Ngắt dịch vụ trạng thái ở API nhạy cảm | Fail-closed và quan sát lỗi theo thiết kế; không ngầm cho phép |
| **T14 — Multi-region propagation** | Revoke tại một region, thử toàn bộ region | Đo được propagation và phát hiện node nhận event muộn |
| **T15 — Secret compromise** | Thu hồi credential client và thử cấp token mới | Secret/key cũ không còn xác thực; token cũ được xử lý theo policy |
| **T16 — Audit privacy** | Kích hoạt revoke/deny trong môi trường test | Log có token ref/reason, không có raw credential |

Cần **test bằng credential giả an toàn tại staging**, không cố thử token nghi lộ thật trên production ngoài quy trình điều tra được phê duyệt. Với sự cố thực, kiểm chứng nên dựa trên log/trạng thái được quyền truy cập và các probe được thiết kế không làm lộ token.

## 17. Kế hoạch vận hành và giao tiếp khi phải thu hồi rộng

Thu hồi toàn bộ grant hoặc chấm dứt nhiều phiên có thể gây lỗi hàng loạt cho người dùng hợp lệ. Vì vậy kế hoạch cần tính đến:

1. **Chủ sở hữu quyết định:** ai được revoke token, grant, client hoặc khóa ký; cơ chế phê duyệt khẩn cấp và lưu dấu vết.
2. **Mức ảnh hưởng:** bao nhiêu user, client, API, tenant, background job; có đường rollback an toàn không và điều gì không được rollback?
3. **Hành vi người dùng:** app xử lý `401 invalid_token`, hướng dẫn đăng nhập lại, không tự refresh vô hạn hoặc lặp OAuth redirect.
4. **Thông báo phù hợp:** mô tả rõ yêu cầu đăng nhập lại, tài khoản/dữ liệu có thể bị ảnh hưởng, hành động cần thiết và kênh hỗ trợ; không gửi token vào email/ticket.
5. **Đồng bộ liên đội:** identity/IAM, security, app, API/gateway, SRE và chủ hệ thống dữ liệu hiểu trạng thái thực thi.
6. **Khôi phục credential:** cấp mới chỉ khi đã xử lý nơi lộ; nếu thiết bị hoặc backend còn compromise, token mới có thể bị lấy tiếp.
7. **Hậu kiểm:** đo phát hiện → revoke AS → chặn tại RS, tính đúng/sai cảnh báo, missed events, audit coverage và tác động availability.

Không yêu cầu người dùng **cung cấp mật khẩu hoặc dán token để xác minh sự cố**. Việc hỗ trợ nên dùng giao diện bảo mật chính thức và định danh tham chiếu an toàn.

## 18. Checklist kỹ thuật: thu hồi sau nghi ngờ lộ token

1. **Xác định credential bị ảnh hưởng:** access, refresh, ID, code, client credential hay signing key; JWT hay opaque chỉ là định dạng.
2. **Khoanh phạm vi:** issuer, audience, client, subject, scope, tenant, grant, thời gian, số token và đường lưu trữ đã lộ.
3. **Ưu tiên containment:** khóa nguồn rò tiếp diễn, giữ bằng chứng cần thiết và revoke token/grant/token family theo policy.
4. **Dùng RFC 7009 đúng vai trò:** token endpoint revocation qua TLS, client auth và quyền sở hữu phù hợp; HTTP 200 không chứng minh RS đã đồng bộ.
5. **Ngăn tái phát hành:** vô hiệu refresh grant/family và client credential hoặc session liên quan khi sự cố đòi hỏi.
6. **Chặn access token thực sự tại API:** opaque introspection, JWT denylist/grant-state hoặc cơ chế tương đương; không tin JWT signature tự biểu thị trạng thái revoke.
7. **Theo dõi propagation:** xác định effective time, cache TTL, node/region, tối đa chậm bao lâu và điều kiện fail-closed.
8. **Đừng bỏ qua token purpose và audience:** API chỉ nhận access token của chính nó, không ID token hoặc RT.
9. **Bảo vệ DPoP/mTLS:** nếu token bị sao chép đơn lẻ, xác minh key binding; nếu khóa cũng lộ, phải revoke và thay khóa.
10. **Không nhầm logout với thu hồi:** xử lý user/app/AS session riêng khi cần.
11. **Không dùng rotation signing key cho sự cố một token:** cân nhắc chỉ khi khóa ký hoặc tập token rộng bị compromise theo quy trình issuer.
12. **Audit an toàn:** ghi token reference, grant/client, decision/reason/time, không raw token/secret.
13. **Xác nhận kết quả ở nơi thực thi:** AS từ chối refresh; RS từ chối token theo chính sách; không chỉ nhìn response revoke.
14. **Kiểm thử lại sau sự cố:** rotation/replay, cache, multi-region, BOLA/scope, logging và user reauthentication.
15. **Ghi giới hạn còn lại:** nếu không hỗ trợ revoke JWT tức thì, nêu rõ thời hạn phơi nhiễm tối đa và kế hoạch cải thiện.

**Kết luận:** khi nghi ngờ lộ bearer token, “thu hồi” chỉ có ý nghĩa bảo mật khi **đường dùng token ở Resource Server bị chặn**, đồng thời **đường cấp token mới tại AS không còn bị lợi dụng**. Một thiết kế tốt phải phân biệt access/refresh/grant/session, dùng RFC 7009 hoặc cơ chế quản trị phù hợp, tính đến JWT tự xác minh, cache/introspection và đo độ trễ revoke bằng bằng chứng thực tế — không mặc định logout hoặc một phản hồi HTTP 200 có thể làm vô hiệu mọi bản sao token.

### Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): ý nghĩa bearer token và các đe dọa liên quan.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): cách yêu cầu thu hồi token và hành vi revocation endpoint.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra `active` và thuộc tính token qua AS.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các biện pháp với refresh token, rotation và OAuth security.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token, issuer/audience/claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT, bảo vệ chống token confusion.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token và cơ chế proof.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc token với certificate.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): quản lý token và phòng ngừa OAuth threats.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log bảo mật, bảo vệ credential và bằng chứng điều tra.
