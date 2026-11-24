# Idempotent revoke request

Một OAuth client gửi yêu cầu thu hồi **refresh token RT-17** đến Authorization Server. Máy chủ đã đánh dấu token bị thu hồi, nhưng đường truyền đứt trước khi client nhận HTTP response. Client không biết yêu cầu đã thành công hay chưa, nên gửi lại cùng token. Authorization Server nên làm gì?

**Với yêu cầu thu hồi hợp lệ của đúng client, lần gọi lại phải an toàn:** token đã bị thu hồi thì **giữ trạng thái bị thu hồi**, không phát sinh một grant mới, không tái kích hoạt token, và thông thường trả **HTTP 200 OK** giống trường hợp một token không còn hợp lệ. Đó là tinh thần **idempotent revoke request** trong **OAuth 2.0 Token Revocation (RFC 7009)**.

Điều này không có nghĩa “bất kỳ ai gửi một chuỗi token nào cũng phải được HTTP 200” hoặc “HTTP 200 bảo đảm mọi Resource Server lập tức từ chối token”. Authorization Server vẫn phải **xác thực hoặc nhận diện client phù hợp, kiểm quyền thu hồi, tuân thủ loại token được hỗ trợ**, và thiết kế trạng thái cùng cơ chế lan truyền revocation đúng đắn.

Bài học thuộc chương **Revocation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung đặt tính idempotent của revoke vào mô hình tin cậy OAuth 2.0/OIDC, phân biệt JWT, opaque token, access token, refresh token, Authorization Server/Resource Server, scope/audience/claims, lưu trữ, chống token bị đánh cắp, phát lại và xử lý sự cố.

Sau bài học, bạn có thể thiết kế endpoint revoke cho phép retry an toàn, phân biệt revoke trùng với revoke trái phép, áp dụng trạng thái nguyên tử trên nhiều instance, tránh side effect lặp, kết nối với introspection/cache, lập kế hoạch thu hồi JWT và viết ma trận kiểm thử bao gồm lỗi mạng, concurrent requests và revocation propagation.

## 1. Idempotent nghĩa là gì trong thao tác thu hồi token?

**Idempotence** mô tả một thao tác mà khi thực hiện nhiều lần với cùng dữ liệu trong cùng ngữ cảnh, **trạng thái đích sau các lần thực hiện** tương đương với việc thực hiện một lần.

Với một token **T** trong hệ thống lưu trạng thái:

~~~text
Trước:      T.status = ACTIVE
revoke(T):   T.status = REVOKED
revoke(T):   T.status = REVOKED     (không đổi)
revoke(T):   T.status = REVOKED     (không đổi)
~~~

Một phép mô hình hóa đơn giản:

\[
R(R(S,T),T)=R(S,T)
\]

Trong đó **S** là trạng thái quản lý token, **T** là token bị thu hồi và **R** là phép chuyển trạng thái revoke. Phương trình này nói về **hiệu ứng thu hồi cuối cùng**, không khẳng định mọi request HTTP của cùng client ở mọi thời điểm luôn có cùng status nếu **quyền client, credential hoặc trạng thái AS** đã thay đổi.

| Tình huống | Trạng thái token sau request | Kết quả HTTP thông thường khi request hợp lệ |
|---|---|---|
| T còn ACTIVE, client có quyền revoke | Chuyển thành REVOKED | **200 OK** |
| T đã REVOKED, client gọi lại | Vẫn REVOKED | **200 OK** |
| T đã EXPIRED hoặc không còn hiệu lực | Vẫn không hiệu lực | **200 OK** với token invalid theo RFC 7009 |
| T không được AS nhận biết | Không có token nào thay đổi | **200 OK** đối với yêu cầu hợp lệ chứa token không hợp lệ |
| Caller không xác thực được theo yêu cầu AS | Không được phép thay đổi | **Lỗi xác thực**, không dùng idempotence để bỏ qua |
| Token thuộc client khác và caller không có quyền revoke | Không được phép thu hồi token của bên khác | **Từ chối theo kiểm tra quyền** |
| AS không hỗ trợ revocation cho loại token cần xử lý | Không được tuyên bố đã xử lý thành công | Lỗi **unsupported_token_type** theo trường hợp RFC 7009 |

**Idempotent không có nghĩa API trả mã 200 bất kể lý do.** Nó ngăn thao tác revoke hợp lệ bị biến thành lỗi nghiệp vụ chỉ vì client không biết token đã được xử lý trước đó.

## 2. RFC 7009: một endpoint chuẩn cho token revocation

**RFC 7009** định nghĩa **OAuth 2.0 Token Revocation**. Client gửi token cần thu hồi đến **revocation endpoint** của Authorization Server bằng **HTTP POST** với body **application/x-www-form-urlencoded**. Endpoint phải được bảo vệ bởi **TLS** và xác thực/ủy quyền client phù hợp.

Một request minh họa của confidential client:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.org
Authorization: Basic <client-authentication>
Content-Type: application/x-www-form-urlencoded

token=<refresh-token-RT17>&token_type_hint=refresh_token
~~~

Các chuỗi trong dấu ngoặc nhọn là **placeholder**, không phải token hoặc credential thật. Trong request thực, các tham số được **form-URL-encode**. Không gửi raw token trong query string, URL của trình duyệt hay logs.

| Thành phần | Vai trò |
|---|---|
| **token** | Giá trị access token hoặc refresh token mà client yêu cầu thu hồi; **tham số bắt buộc** |
| **token_type_hint** | Gợi ý **access_token** hoặc **refresh_token**, giúp AS tìm nhanh hơn; **không phải chứng cứ loại token** |
| **Client authentication** | Confidential client xác thực theo phương thức đã đăng ký, ví dụ client_secret_basic, private_key_jwt hoặc mTLS |
| **Client binding/ownership** | AS bảo đảm client có quyền thu hồi token đang được đề cập |
| **Revocation policy** | AS quyết định có thu hồi thêm token/grant liên quan không và cách truyền trạng thái tới RS |

Theo RFC 7009, AS **phải hỗ trợ thu hồi refresh token** và **nên hỗ trợ thu hồi access token**. Khi thực thi, cần kiểm chính xác khả năng endpoint và chính sách của AS đang dùng; không suy rằng mọi deployment đều có thể lập tức vô hiệu mọi JWT access token đã phát.

### Phân biệt ba endpoint

| Endpoint | Client/RS gửi gì? | Mục đích |
|---|---|---|
| **Token endpoint** | Authorization code, refresh token, client credentials hoặc grant được hỗ trợ | **Phát access token mới** khi grant hợp lệ |
| **Revocation endpoint** | Token cần revoke, client authentication phù hợp | **Chấm dứt hiệu lực token** theo policy |
| **Introspection endpoint** | Token cần kiểm, caller được phép introspect | **Hỏi trạng thái và metadata** token, ví dụ active=true/false |

**Revoke không phải refresh**: token bị thu hồi không được dùng để xin token mới. **Revoke cũng không phải introspection**: câu trả lời 200 của revocation không chứa một bản đánh giá scope/audience cho RS.

## 3. Vì sao RFC 7009 trả 200 cho token đã không hợp lệ?

Trong RFC 7009, **HTTP 200 OK** là response thành công khi token đã được thu hồi **hoặc khi client gửi một token không hợp lệ**. Response thường không cần body có nội dung; client không được coi nội dung body là nguồn xác minh danh tính/token status.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Content-Length: 0
~~~

Tại sao không trả lỗi **“token already revoked”**?

1. **Mục tiêu đã đạt:** client muốn token không còn hiệu lực; nếu token vốn đã invalid thì không cần một thao tác nghiệp vụ khác.
2. **Cho phép retry sau timeout:** client không cần tìm hiểu request đầu đã thực hiện hay chưa chỉ để quyết định có gửi lại.
3. **Giảm token-status oracle:** không công khai việc một chuỗi token có từng tồn tại hay vừa bị revoke, đặc biệt khi response có thể bị quan sát bởi bên không được phép.
4. **Đơn giản hóa client:** client không cần phân nhánh “revoked now” với “already revoked” để xác định mục tiêu thu hồi.

### Điều HTTP 200 không chứng minh

**HTTP 200 không phải receipt chứng minh token từng tồn tại**, không phải lời bảo đảm “mọi access token liên quan đã bị revoke”, không thay một phép kiểm trạng thái thời gian thực tại RS, và không phải bằng chứng một tài khoản đã logout mọi thiết bị.

AS nên tránh các phản hồi như:

~~~json
{
  "token_exists": true,
  "revoked_now": false,
  "owner_user_id": "user-42"
}
~~~

Những field này **không thuộc response thành công chuẩn** và có nguy cơ tiết lộ token/account metadata. Với revocation request hợp lệ, **không cần tiết lộ token từng tồn tại hay chưa**.

## 4. Idempotence không được biến thành lỗ hổng thu hồi token của người khác

Trước khi thay đổi token state, AS cần xác định **client đang gọi có quyền revoke token này không**. Một confidential client phải xác thực theo phương thức đã đăng ký. Public client không thể giữ một shared secret dài hạn an toàn như confidential client; AS cần **client identification, binding và các điều kiện bảo vệ thích hợp** theo loại client/profile.

~~~mermaid
flowchart TD
    A["POST /revoke"] --> B{"Request/TLS/format hợp lệ?"}
    B -->|Không| X["Reject"]
    B -->|Có| C["Xác thực/nhận diện client theo policy"]
    C --> D{"Client hợp lệ và được phép revoke?"}
    D -->|Không| X
    D -->|Có| E["Tìm token theo digest/type hint có kiểm soát"]
    E --> F{"Token được biết và thuộc client này?"}
    F -->|Không có token hợp lệ| G["Trả 200: invalid/no-op"]
    F -->|Token thuộc client khác| X
    F -->|Đúng client| H{"Token còn active?"}
    H -->|Không| G
    H -->|Có| I["Atomic ACTIVE -> REVOKED"]
    I --> J["Ghi audit/outbox đúng một lần"]
    J --> K["Commit"]
    K --> G
~~~

Đây là **luồng minh họa**. Đối với một token string không biết đến, AS có thể trả **200 không tiết lộ sự tồn tại** theo RFC 7009; với token xác định thuộc client khác, không được xóa token ấy. Cách chuẩn hóa **error response** phải theo hợp đồng bảo mật và yêu cầu xác thực/ủy quyền, tránh tạo oracle quá chi tiết.

### Hai sai lầm đối lập

**Sai lầm A — quá dễ dãi:** bất kỳ caller nào biết token string đều có thể gọi revoke và tắt token người khác. Đây là **denial of service và unauthorized revocation**.

**Sai lầm B — quá phân biệt:** token không tồn tại trả 404, token đã revoke trả 409, token còn active trả 200, kèm metadata chủ sở hữu. Điều đó tạo **oracle** cho bên thăm dò và làm client retry phức tạp.

Giải pháp là **đặt authentication/ownership trước thay đổi trạng thái**, rồi áp dụng tính idempotent trong phạm vi **request revoke đã hợp lệ**.

## 5. token_type_hint là gợi ý, không phải quyền điều khiển việc thu hồi

RFC 7009 cho phép client cung cấp **token_type_hint** với hai giá trị thường gặp:

~~~text
token_type_hint=access_token
token_type_hint=refresh_token
~~~

AS có thể dùng hint để tìm token nhanh hơn trong kho riêng cho access/refresh tokens. Tuy nhiên:

- **Không tin hint để bỏ kiểm loại token thực.** Một refresh token không tự trở thành access token vì caller viết access_token.
- Nếu không tìm thấy token theo hint, AS phải mở rộng tìm kiếm trên các loại token nó hỗ trợ theo RFC 7009.
- Giá trị hint không được nhận diện nên được xử lý như **hint không giúp tra cứu**, không tự tiết lộ loại token thật.
- **unsupported_token_type** liên quan đến việc server **không hỗ trợ thu hồi loại token đó**, không phải giấy phép chấp nhận bừa các hint do caller tự khai.
- Không đưa hint vào cache key hay audit như bằng chứng đã xác minh token thuộc một loại cụ thể.

| Request | Điều cần kiểm | Kết quả đúng về nguyên tắc |
|---|---|---|
| RT17 + hint refresh_token | Tìm đúng record RT17 theo client binding | Thu hồi RT17 nếu đang active |
| RT17 + hint access_token | Không thấy trong kho access, phải xét các token types hỗ trợ | Không được bỏ qua RT17 chỉ vì hint sai |
| RT17 + không hint | AS vẫn tra cứu đúng token | Có thể revoke |
| Chuỗi không tồn tại + hint bất kỳ | Không có token để thay đổi | 200 trong trường hợp request revoke hợp lệ |
| Token thuộc client khác | Kiểm ownership của record thực | Không thu hồi token của client khác |

**Idempotence không được dựa vào việc client gửi hint đúng.** Tính an toàn phải dựa trên **token đã được AS nhận diện và ràng buộc với đúng client**.

## 6. State machine: active, revoked, expired và unknown

Một mô hình đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: AS phát token
    ACTIVE --> REVOKED: Revoke hợp lệ
    ACTIVE --> EXPIRED: Thời gian hiệu lực kết thúc
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Đây là **mô hình khái niệm**. Token **không tìm thấy** không có state, và các hệ thống còn có thể lưu **grant revoked, token family compromised, rotated, consumed** hoặc trạng thái khác. Điểm quan trọng là:

~~~text
revoke(ACTIVE)  => REVOKED
revoke(REVOKED) => REVOKED
revoke(EXPIRED) => vẫn invalid
revoke(UNKNOWN) => không tạo state/token mới
~~~

Một **revoked token không được quay trở lại ACTIVE** do retry, tái phát request, event đến sai thứ tự hoặc rollback thao tác khác. Nếu client muốn được cấp quyền mới, phải thực hiện **một grant/token issuance flow hợp lệ**, không “undo revoke” trên cùng credential.

### Token và grant không cùng state

Nếu hệ thống lưu:

~~~text
grant G1:
  RT1 (refresh token)
  AT1 (access token)
  AT2 (access token)
~~~

thì thao tác revoke RT1 có thể:

- Chỉ khiến RT1 không thể dùng refresh theo chính sách.
- Thu hồi cả grant G1 và những token liên quan nếu AS áp dụng policy đó.
- Kích hoạt các bước vô hiệu hóa AT1/AT2 qua introspection, denylist hoặc kiểm trạng thái.

**Không được tự khẳng định revoke RT1 luôn tức thì làm AT1/AT2 invalid.** Phạm vi revocation là quyết định chính sách và khả năng của AS; cần tài liệu hóa rõ và kiểm thử bằng chính môi trường triển khai.

## 7. Ba lần gửi cùng request: ví dụ request/response

Giả sử confidential client **orders-bff** có refresh token RT17, đang ACTIVE. Ở lần gọi đầu:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.org
Authorization: Basic <orders-bff-credentials>
Content-Type: application/x-www-form-urlencoded

token=<RT17>&token_type_hint=refresh_token
~~~

Authorization Server cập nhật RT17 thành REVOKED, trả:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Content-Length: 0
~~~

Nếu HTTP response **bị mất trên mạng**, orders-bff gửi lại:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.org
Authorization: Basic <orders-bff-credentials>
Content-Type: application/x-www-form-urlencoded

token=<RT17>&token_type_hint=refresh_token
~~~

AS thấy RT17 đã REVOKED, **không tạo side effect thu hồi lần hai**, và tiếp tục có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Length: 0
~~~

Nếu client gửi **một token ngẫu nhiên không tồn tại**, sau khi request/client được xử lý hợp lệ, RFC 7009 cũng quy định **200 OK** cho invalid token. Client **không được suy từ 200 rằng token đã từng tồn tại**.

### Phân biệt lỗi xác thực client

Nếu client secret, mTLS credential hoặc JWT client assertion đã sai/hết hạn, AS **không bỏ qua xác thực chỉ để giữ response 200**. Khi đó endpoint trả lỗi phù hợp như **invalid_client**, có thể HTTP 401/challenge theo cách client authentication được sử dụng. Idempotence không làm một caller chưa được xác thực có quyền quản trị token.

## 8. Retry sau timeout: cái gì an toàn và cái gì không?

Sự cố mạng tạo ra tình huống **ambiguous completion**:

~~~text
10:00:00  Client gửi revoke(RT17)
10:00:01  AS commit trạng thái REVOKED
10:00:01  Response 200 bị mất
10:00:03  Client timeout
10:00:04  Client retry revoke(RT17)
10:00:05  AS thấy RT17 đã REVOKED, trả 200
~~~

Trong trường hợp này, **retry có giới hạn** có thể an toàn vì revoke idempotent. Nhưng “an toàn với duplicate” **không đồng nghĩa được phép retry vô hạn**.

Hướng dẫn cho client:

1. Dùng **TLS** và đúng revocation endpoint được AS cấu hình/metadata tin cậy.
2. Nếu không nhận được response do timeout/connection reset/503 tạm thời, thực hiện retry **bounded** với backoff và jitter khi chính sách phù hợp.
3. Không retry thô một request có **client authentication thất bại**, token/request bị malformed hoặc loại token không được hỗ trợ; cần sửa nguyên nhân trước.
4. Không thay một token bằng **token khác** trong cùng retry logic mà không có quyết định nghiệp vụ mới.
5. Với logout/disconnect, **dừng sử dụng token ở client ngay** theo chính sách; không tuyên bố AS đã revoke thành công khi chỉ có timeout.
6. Nếu cần retry sau local logout, phải cân bằng việc xóa token khỏi thiết bị với nhu cầu gửi lại: dùng quy trình server-side đáng tin hoặc lưu credential trong một vùng bảo vệ ngắn hạn có giới hạn, **không gửi nó vào queue/log không mã hóa**.
7. Khi nhận HTTP 200, xử lý response như **yêu cầu revoke đã hoàn tất theo hợp đồng**, không cố introspect để tìm “200 loại nào”.

### Trường hợp đặc biệt: 503 Service Unavailable

RFC 7009 có mô tả khả năng AS trả **HTTP 503** khi revocation service tạm không khả dụng. Client có thể retry sau khoảng trì hoãn thích hợp, có giới hạn và theo tín hiệu như Retry-After nếu có. **Không được xem 503 là đã revoke**; token có thể vẫn đang hoạt động.

### Revoke và thanh toán không giống nhau

Không áp dụng logic “POST nào cũng idempotent” từ revocation sang API thanh toán, cấp token hay tạo đơn hàng. **Idempotence ở đây đến từ ngữ nghĩa revoke một credential**, không phải do phương thức POST tự thân idempotent.

## 9. Concurrent revoke: tránh read-then-write không nguyên tử

Hai request revoke RT17 có thể đến **hai AS instances** cùng lúc. Cách triển khai nguy hiểm:

~~~text
Request A: SELECT RT17 -> ACTIVE
Request B: SELECT RT17 -> ACTIVE
Request A: UPDATE RT17 -> REVOKED, phát sự kiện và tăng counter
Request B: UPDATE RT17 -> REVOKED, phát sự kiện lần hai và tăng counter
~~~

**Trạng thái token cuối cùng** vẫn REVOKED, nhưng side effects có thể lặp: gửi hai thông báo, tạo hai job revoke, xóa sai token family, đếm đôi một incident hoặc race với phiên giao dịch mới.

Một cách thực hiện **atomic conditional update**:

~~~sql
UPDATE oauth_tokens
SET status = 'REVOKED',
    revoked_at = CURRENT_TIMESTAMP,
    revision = revision + 1
WHERE token_digest = :digest
  AND client_id = :authenticated_client_id
  AND status = 'ACTIVE';
~~~

Nếu cập nhật **1 hàng**, đây là transition ACTIVE → REVOKED; có thể tạo **một outbox event** trong cùng transaction. Nếu **0 hàng**, cần xác định một cách tin cậy liệu token **đã invalid/unknown** (no-op) hay **thuộc client khác/validation failure**. Không tự xem mọi 0-row là chứng minh quyền client hợp lệ, cũng không trả về thông tin chủ sở hữu cho caller.

**Lưu ý:** câu SQL chỉ minh họa điều kiện cập nhật. Hệ thống thật phải kiểm loại token, grant binding, trạng thái client, policy liên quan và có transaction/locking phù hợp. Nếu token nằm ở nhiều bảng theo loại, cần thống nhất cách tìm token để tránh sai ownership khi caller gửi hint không đúng.

### Tính nguyên tử phải phủ cả side effects quan trọng

Khi một transition xảy ra, có thể muốn:

~~~text
transaction:
    update token state to REVOKED (once)
    insert outbox event TOKEN_REVOKED (once)
commit
~~~

Worker sau đó publish event theo **at-least-once**, các consumer phải **idempotent**. Nếu DB commit nhưng process chết trước khi publish, outbox giúp gửi lại sau. Nếu event bị gửi hai lần, RS/gateway không được cho token đã REVOKED quay lại ACTIVE.

**Idempotent revoke là thuộc tính của toàn bộ workflow**, không chỉ một UPDATE. Cần xem token state, grant state, token family, events, caches và audit.

## 10. Token family và việc thu hồi refresh token

Trong OAuth 2.0, **refresh token** có thể giúp client xin access token mới khi grant còn hiệu lực. Với **refresh token rotation**, AS phát RT2 và vô hiệu RT1 sau lần refresh hợp lệ; nếu RT1 bị dùng lại tại **token endpoint**, đó có thể là tín hiệu **refresh token replay**.

Ví dụ:

~~~text
Grant G1 / refresh token family F1
    RT1 (rotated/invalid)
      -> RT2 (rotated/invalid)
          -> RT3 (ACTIVE)

User chọn "Ngắt kết nối":
    revoke(RT3) -> token family/underlying grant theo policy
~~~

### Không trộn revoke retry với refresh replay

| Hành động | Endpoint | Ý nghĩa lần gửi lại |
|---|---|---|
| **revoke(RT3)** lần 1 | Revocation endpoint | Làm RT3 không còn hợp lệ |
| **revoke(RT3)** lần 2 | Revocation endpoint | No-op idempotent; không nên coi là token family replay attack chỉ vì revoke lặp |
| **refresh(RT3)** sau khi RT3 bị rotate/revoke | Token endpoint | Có thể là **refresh-token reuse/replay** và kích hoạt biện pháp token family |
| **introspect(RT3)** | Introspection endpoint cho caller đủ quyền | Hỏi trạng thái; không phải cấp token |
| **dùng RT3 làm Bearer vào Orders API** | Resource Server | Sai loại credential; phải từ chối |

**Không xử lý hai lần revoke bằng cách kích hoạt cảnh báo “refresh token reuse” không phân biệt ngữ cảnh**. Một lần refresh sai có thể có hậu quả bảo mật nghiêm trọng; một lần revoke trùng do timeout là điều workflow cần hỗ trợ bình thường.

### Phạm vi revoke phải được ghi rõ

Một AS có thể:

- Revoke **refresh token cụ thể**.
- Revoke **cả refresh token family** khi có dấu hiệu compromise hoặc theo policy.
- Revoke **underlying authorization grant** để chặn tiếp tục cấp token.
- Tìm và revoke các **access tokens liên quan** nếu hỗ trợ.

Tùy AS, các hành động này có thể khác nhau. **RFC 7009 không biến mọi lần revoke một RT thành bảo đảm mọi AT hiện hành mất hiệu lực ngay trên mọi Resource Server**.

## 11. Access token revocation: opaque và JWT khác gì về khả năng quan sát?

Một **opaque access token** thường được Resource Server kiểm qua **introspection RFC 7662**. Khi AS chuyển AT1 sang REVOKED, introspection hợp lệ của AT1 có thể trả **active=false**.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: POST /revoke token=AT1
    AS->>AS: Commit AT1=REVOKED
    AS-->>C: HTTP 200 OK
    RS->>AS: Introspect AT1
    AS-->>RS: HTTP 200, active=false
    RS-->>C: Reject AT1
~~~

Tuy nhiên, nếu RS đã cache **active=true**, nó có thể tiếp tục tin trạng thái cũ cho tới khi TTL hết hoặc nhận invalidation. Đây là **độ trễ lan truyền thu hồi**, không mâu thuẫn với việc revoke request của AS đã xử lý idempotently.

**JWT access token tự chứa** có thể được RS kiểm hoàn toàn bằng chữ ký, **iss, aud, exp, nbf**, scope và policy. Nếu RS **không truy vấn trạng thái thu hồi**, một JWT đã revoke ở AS **có thể vẫn được chấp nhận tới exp**.

| Token/kiến trúc | Revoke ở AS thay đổi điều gì? | RS biết khi nào? |
|---|---|---|
| **Opaque AT + introspection mỗi request** | Token state active → false | Khi RS introspect sau thay đổi |
| **Opaque AT + positive cache** | AS đã inactive | Khi cache hết TTL hoặc invalidation đến |
| **JWT AT + offline validation** | AS ghi nhận revoked/grant disabled | Không tự biết nếu chỉ kiểm chữ ký và exp |
| **JWT AT + denylist/epoch/introspection** | AS có thể đánh dấu trạng thái và phát sự kiện | Khi RS kiểm/nhận state theo thiết kế |
| **Refresh token tại AS** | Chặn refresh token exchange | Token endpoint thực thi trạng thái |

**Đừng coi “HTTP 200 revoke” là tín hiệu tự xoay public signing key**. Revocation thông thường là chấm dứt **một token/grant**, không phải thay đổi niềm tin với mọi JWT của issuer. Nếu **private signing key AS bị xâm phạm**, cần quy trình khẩn cấp khác.

## 12. Idempotence và ngữ nghĩa “đã thu hồi thành công”

Để không trả 200 quá sớm, hãy phân biệt ba thời điểm:

~~~text
T1: AS nhận request revoke hợp lệ.
T2: AS ghi/commit trạng thái token bị thu hồi bền vững.
T3: Các RS/caches nhận biết trạng thái mới.
~~~

**T2 là ranh giới quan trọng để AS tuyên bố đã thực thi revocation tại nguồn trạng thái của mình.** Nếu database transaction chưa commit, không nên trả “thành công” rồi để token có thể tiếp tục refresh bình thường do rollback/crash. Nếu endpoint chỉ xếp một job vào queue mà job có thể thất bại vĩnh viễn, **không được coi việc enqueue đơn thuần là thu hồi hoàn tất** trừ khi kiến trúc có nghĩa vụ thực thi bền vững tương ứng và hợp đồng rất rõ.

**T3** có thể trễ so với T2 do cache, replication, offline JWT hoặc AS/RS state propagation. Đó là **SLO về hiệu lực thu hồi**, cần được đánh giá riêng với idempotence ở endpoint.

### Thế nào là một kết quả revoke idempotent tốt?

- Retry không tạo nhiều lần chuyển trạng thái.
- Token đã invalid không bị **khôi phục hoặc tái cấp** chỉ vì retry.
- Cập nhật grant/token family không bị tăng quyền hoặc xóa nhầm.
- Audit/notification có thể được deduplicate theo **event/revision**, không theo mỗi HTTP request.
- Caller không học được token tồn tại hay không qua success body.
- AS không thông báo thành công khi chưa bảo đảm trạng thái thu hồi theo hợp đồng.
- Các RS có **giới hạn độ trễ nhận biết** đã được công bố/đánh giá, không bị hiểu nhầm với semantics HTTP 200.

## 13. Transaction, outbox và event consumers phải cùng giữ idempotence

Trong hệ thống thật, revoke không chỉ là **UPDATE oauth_tokens**. Nó thường có các tác vụ:

~~~text
Commit grant/token revoked
  |
  +--> Ghi audit event
  +--> Phát event xóa cache introspection
  +--> Vô hiệu refresh token family nếu policy yêu cầu
  +--> Thông báo tới hệ thống phiên/thiết bị
  +--> Cập nhật denylist hoặc grant epoch
~~~

Nếu code gọi từng service trực tiếp sau khi kiểm token ACTIVE rồi không có kiểm soát idempotence, retry request có thể lặp lại toàn bộ chuỗi.

### Outbox pattern

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Revocation API
    participant DB as Token DB + Outbox
    participant W as Outbox Publisher
    participant RS as Resource Server
    C->>AS: Revoke RT17
    AS->>DB: Transaction: conditional revoke + outbox event
    DB-->>AS: Commit success
    AS-->>C: 200 OK
    W->>DB: Đọc event chưa gửi
    W->>RS: TOKEN_REVOKED event có revision
    RS->>RS: Invalidate cache / cập nhật epoch
    W->>DB: Đánh dấu event đã publish
    C->>AS: Retry revoke RT17
    AS->>DB: RT17 đã REVOKED, no-op
    AS-->>C: 200 OK
~~~

Outbox giúp hạn chế lỗi **DB commit thành công nhưng process chết trước khi publish event**. Nhưng message broker thường chỉ cho delivery kiểu **at-least-once**; consumer phải tự chống event lặp.

Một event nội bộ có thể mang:

~~~json
{
  "event_id": "evt-example-701",
  "event_type": "TOKEN_REVOKED",
  "issuer_ref": "auth-main",
  "token_ref": "token-record-17",
  "grant_ref": "grant-example-9",
  "revision": 4,
  "reason_code": "CLIENT_REQUEST",
  "recorded_at": "2026-11-23T09:30:00Z"
}
~~~

Đây là **schema minh họa**, không phải format RFC 7009. Token reference phải là định danh nội bộ có bảo vệ, **không phải raw refresh/access token**. Một hệ thống có thể chuyển fingerprint/epoch qua các bên theo hợp đồng và quyền truy cập cụ thể.

### Consumer idempotent

~~~text
receive TOKEN_REVOKED(tokenRef, revision=4):
    knownRevision = store.getLastAppliedRevision(tokenRef)
    if knownRevision >= 4:
        acknowledge without re-applying
        return
    markTokenRevokedInLocalIndex(tokenRef)
    store.setLastAppliedRevision(tokenRef, 4)
    invalidateMatchingIntrospectionEntries(tokenRef)
~~~

Trong môi trường nhiều node, việc kiểm và ghi **lastAppliedRevision** phải đủ nhất quán. Không để event cũ có trạng thái “active” ghi đè event revoked phiên bản mới. Đặc biệt, nếu request introspection bắt đầu trước khi revoke rồi trả **active=true** muộn, RS cần **generation fencing** hoặc giới hạn TTL để ngăn stale repopulation.

## 14. Khi revocation gặp cache tại Resource Server

**RFC 7662** cho phép RS introspect token để biết nó còn active hay không. Nếu RS cache kết quả **active=true** quá lâu, AS xử lý revoke đúng vẫn không đạt mục tiêu ngừng truy cập nhanh.

~~~text
10:00:00  RS introspect AT1: active=true
10:00:00  RS cache kết quả active trong 20 phút
10:02:00  Client revoke AT1 thành công ở AS
10:02:00  AS introspect AT1 từ giờ trả active=false
10:03:00  Attacker dùng AT1 ở RS -> cache hit active=true
10:20:00  Cache hết hạn -> RS hỏi lại AS và từ chối
~~~

**Khoảng stale 18 phút** này là rủi ro cần thiết kế, không phải thành công của revocation end-to-end.

### Giới hạn TTL bằng policy và exp

Một nguyên tắc:

\[
TTL_{\text{active}} =
\max\left(0,\min\left(T_{\text{policy}},T_{\text{exp}}-T_{\text{now}}-\Delta_{\text{safety}}\right)\right)
\]

Trong đó **T_policy** là trần thời gian cache dương theo nguy cơ, **T_exp** là thời điểm hết hạn token, **T_now** là thời gian hiện tại, **Δ_safety** là biên đồng hồ/rounding. Nếu thiếu **exp** hoặc không có hợp đồng hết hạn đáng tin, mặc định **không cache positive** là lựa chọn an toàn.

Hệ thống nên dùng **hard/fixed expiration**, không **sliding TTL** gia hạn mỗi lần token được sử dụng. Có thể kết hợp **event invalidation đáng tin** với TTL ngắn làm trần dự phòng; event có thể mất, sai thứ tự hoặc đến trễ.

**HTTP 200 của revocation không tự xóa cache ở RS.** Nếu API có SLO nhận biết revoke trong **5 giây**, một positive cache TTL **10 phút** không đạt yêu cầu cho dù endpoint revoke idempotent.

### Fail closed khi AS không khả dụng

Khi cached active đã hết hạn và AS/introspection endpoint lỗi, RS **không được mặc định cho phép** chỉ vì token từng active. Xử lý dependency failure phù hợp; việc stale-while-revalidate hoặc stale-if-error đối với kết quả **active=true** phải có đánh giá ngoại lệ cụ thể, không bật mặc định cho API nhạy cảm.

## 15. Idempotency key: có cần thiết cho OAuth revocation không?

Các API nghiệp vụ thường dùng **Idempotency-Key** để không thực hiện lại một thao tác khi client retry. Nhưng **RFC 7009 không yêu cầu Idempotency-Key**. Revoke đã có ngữ nghĩa idempotent ở **trạng thái token** và chuẩn hóa response.

Ví dụ:

~~~text
POST /revoke token=RT17
POST /revoke token=RT17
POST /revoke token=RT17

=> Token RT17 không trở lại ACTIVE và AS không tạo thêm grant.
~~~

Nếu một tổ chức xây một **orchestration API riêng** như “đăng xuất tất cả thiết bị của user-42”, họ có thể cần **idempotency key** hoặc **command ID** để bảo vệ side effects như gửi thông báo, ghi lịch sử hoặc tạo job. Nhưng:

- Không chuyển yêu cầu này thành một tham số chuẩn bắt buộc của RFC 7009.
- Không dùng idempotency key do caller tự khai làm bằng chứng client có quyền revoke token khác.
- Không lưu **raw token** trong bảng idempotency để phục vụ retry.
- Không cache một **200 giả** khi transaction thu hồi thực tế đã rollback hoặc chưa bền vững.
- Không kéo dài retention của token/credential chỉ để giữ khả năng so sánh request.

**Tại revocation endpoint chuẩn, cái cần idempotent trước hết là state transition, client authorization và side effects.**

## 16. Logout, disconnect, revoke grant và end-user session

Người dùng có thể bấm **Đăng xuất** khỏi ứng dụng hoặc **Ngắt kết nối** OAuth client. Hai hành động ấy có thể dẫn tới nhiều thao tác khác nhau:

| Hành động | Điều nó trực tiếp thay đổi | Điều không tự được bảo đảm |
|---|---|---|
| Xóa token khỏi ứng dụng (local logout) | Ứng dụng ngừng sử dụng credential local | AS/RS đã vô hiệu token đang nằm ở nơi khác |
| Revoke refresh token tại AS | Chặn dùng RT đó theo grant/policy | Mọi access token cũ bị RS từ chối tức thì |
| Revoke access token tại AS | Đánh dấu AT inactive nếu AS hỗ trợ | Một JWT self-contained bị RS offline từ chối ngay |
| Revoke entire grant/consent | Ngừng cơ sở cấp token theo policy | Dữ liệu bên thứ ba đã tải xuống bị xóa |
| Kết thúc OIDC login session | Ảnh hưởng phiên đăng nhập theo giao thức/sản phẩm | Tự revoke mọi OAuth tokens của mọi clients |
| Xóa browser cookie | Xóa trạng thái trình duyệt tương ứng | Mọi device, CLI, BFF và service token đồng thời hết hiệu lực |

### Thiết kế nút “Ngắt kết nối”

Một workflow an toàn có thể:

1. Người dùng xác thực và chọn **đúng client/kết nối** cần dừng.
2. Ứng dụng vô hiệu hóa sử dụng token local và yêu cầu AS revoke RT/grant theo cơ chế được cấp phép.
3. AS ghi durable state, bảo đảm **retry không kích hoạt side effects sai**.
4. AS phát sự kiện invalidation hoặc cung cấp introspection/epoch để RS nhận biết token bị ảnh hưởng.
5. UI hiển thị kết quả đúng mức bảo đảm: **“Đã ngắt kết nối tại ứng dụng”** khác với **“Mọi phiên/token trên tất cả API đã bị vô hiệu tức thì”**.

Nếu mạng lỗi, client có thể đã xóa token local mà AS chưa revoke. Hãy dùng ngôn ngữ UI đúng sự thật, cơ chế retry server-side có kiểm soát hoặc hướng dẫn người dùng tới trang quản lý grant, **không tuyên bố thành công tuyệt đối từ một timeout**.

## 17. Public client và confidential client: bảo vệ revoke ra sao?

Một confidential web backend có thể xác thực với revocation endpoint bằng **client_secret_basic, private_key_jwt hoặc mTLS** theo registration. Một public client như SPA/native app **không thể bảo vệ shared secret như server**; nó dùng phương thức định danh/ràng buộc mà AS cho phép, kết hợp bảo vệ token và grant.

| Kiểu client | Lợi thế / hạn chế | Điều phải bảo đảm |
|---|---|---|
| **Confidential BFF/backend** | Có thể giữ secret/private key ở server | Xác thực đúng client; revoke chỉ token/grant nó được phép |
| **Mobile public client** | App có thể bị reverse engineer, secret không đáng tin | Không dựa vào hard-coded secret; AS kiểm client/token binding theo policy |
| **SPA public client** | Môi trường browser chịu XSS/extension risk | Chỉ dùng endpoint CORS/flow được AS cho phép; không đưa token qua URL/log |
| **Service client-credentials** | Không có end-user consent screen thông thường | Revoke token thuộc service principal, không sửa quyền service khác |

**Public client không có client_secret vẫn cần bảo vệ khỏi unauthorized token revocation**, nhưng khả năng chống việc người giữ cả raw token và client_id cố ý thu hồi có giới hạn tùy thiết kế. AS nên áp dụng client binding, chính sách rate limit/abuse, sender-constraining khi phù hợp và không cấp quyền revoke vượt trust model.

Không gửi token cần revoke qua **GET/query** từ browser chỉ để tránh cấu hình CORS. Nếu web client không được phép gọi revocation endpoint trực tiếp, sử dụng **BFF/server-side workflow** hoặc cơ chế do AS hỗ trợ, không đặt client secret server vào JavaScript bundle.

## 18. Java: xử lý revoke idempotent ở Authorization Server

Ví dụ dưới đây là **mô hình kiến trúc Java/Spring**, không phải Authorization Server có thể dùng trực tiếp trong production. Các lớp **TrustedClient, TokenStore, TokenRecord, OutboxRepository** chỉ là giao diện khái niệm.

~~~java
@Service
public final class RevocationService {
    private final TokenStore tokens;
    private final OutboxRepository outbox;
    private final TokenFingerprint fingerprints;
    private final Clock clock;

    public RevocationService(
            TokenStore tokens,
            OutboxRepository outbox,
            TokenFingerprint fingerprints,
            Clock clock
    ) {
        this.tokens = tokens;
        this.outbox = outbox;
        this.fingerprints = fingerprints;
        this.clock = clock;
    }

    @Transactional
    public void revoke(
            TrustedClient authenticatedClient,
            String rawToken,
            String untrustedTokenTypeHint
    ) {
        // Request parser/controller phải kiểm TLS, client authentication,
        // form body, kích thước token, rate limits và các chính sách khác.
        // Hint chỉ giúp chọn nơi tìm; KHÔNG chứng minh loại token.
        String digest = fingerprints.hmac(rawToken);
        TokenRecord token = tokens.findAcrossSupportedTypesForUpdate(
                digest, untrustedTokenTypeHint
        );

        if (token == null) {
            // RFC 7009: token không hợp lệ/không tồn tại là success no-op
            // khi request và client context hợp lệ.
            return;
        }

        if (!token.issuedTo(authenticatedClient.id())) {
            // Không để client khác revoke token này.
            // Mapping lỗi công khai phụ thuộc security contract.
            throw new UnauthorizedTokenRevocation();
        }

        if (!token.isActive(clock.instant())) {
            // Đã revoked/expired, không tạo token mới hay event transition.
            return;
        }

        token.markRevoked(clock.instant());
        tokens.save(token);

        // Outbox event được ghi CÙNG transaction với state change.
        // Unique event key theo transition/revision để chống lặp.
        outbox.insertOnce(
                token.revocationEventId(),
                token.revocationEventWithoutRawCredential()
        );
    }
}
~~~

**Những điều code mẫu cố ý chưa làm**: hỗ trợ từng profile revocation, phân loại lỗi OAuth/HTTP, xác minh confidential/public client chi tiết, transaction isolation, phương thức lookup/digest, refresh token family policy, thu hồi grant rộng hơn, token lineage, mô hình phân tán và kiểm thử framework.

### Các ràng buộc triển khai thực tế

1. **Không dùng plain hash cho token yếu entropy**. Access/refresh tokens phải đủ entropy; với token handle, HMAC có key được quản lý tốt giúp tránh raw credential trong index/log.
2. **@Transactional không tự bảo đảm tính nguyên tử** nếu repository không khóa/cập nhật có điều kiện hoặc dùng kho trạng thái phân tán không tham gia transaction.
3. **findAcrossSupportedTypesForUpdate** cần kiểm token type thật và ownership, kể cả caller cố tình gửi token_type_hint sai.
4. **Không trả 200 khi transaction đã rollback**. Response chỉ được viết sau khi commit thành công.
5. **Outbox insertOnce** cần uniqueness thật trên event ID/transition, không chỉ kiểm bằng một biến Java local.
6. **Đã revoked không có nghĩa xóa sạch lịch sử kiểm ownership**. Nếu record bị purge, request có token cũ sẽ trở thành unknown và vẫn có thể nhận 200 sau client validation; không dùng dữ liệu thiếu để suy quyền tồn tại.
7. **Không để error message chứa rawToken** trong exception, logs, APM, debugger snapshot hoặc HTTP response.

### Một controller HTTP về nguyên tắc

~~~text
POST /oauth2/revoke:
    parse application/x-www-form-urlencoded
    require token parameter
    authenticate client when applicable
    identify client under AS policy
    check request size, TLS and abuse limits
    service.revoke(client, token, token_type_hint)
    if transaction committed or token invalid/no-op:
        return 200 with empty response
    else:
        return appropriate OAuth error/dependency status
~~~

**Không đặt raw token ở URL path**, không phản hồi metadata về token trong success body. Nếu client có lỗi xác thực, đừng gọi tiếp service để xóa token rồi mới trả lỗi.

## 19. Java: unit test của phép chuyển trạng thái idempotent

Để hiểu tính idempotent ở mức cơ bản, có thể dùng **AtomicReference** trong unit test. Đây chỉ là mô hình **một tiến trình**, không thay được transaction database khi AS chạy nhiều instance.

~~~java
import java.util.concurrent.atomic.AtomicReference;

final class InMemoryRevocationState {
    enum Status { ACTIVE, REVOKED }

    private final AtomicReference<Status> status =
            new AtomicReference<>(Status.ACTIVE);

    // true nghĩa là request này đã thực hiện transition;
    // false nghĩa là không còn transition để làm.
    boolean revoke() {
        return status.compareAndSet(Status.ACTIVE, Status.REVOKED);
    }

    boolean isRevoked() {
        return status.get() == Status.REVOKED;
    }
}
~~~

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class InMemoryRevocationStateTest {
    @Test
    void revokeTwiceHasOnlyOneStateTransition() {
        InMemoryRevocationState state = new InMemoryRevocationState();
        assertTrue(state.revoke());
        assertFalse(state.revoke());
        assertFalse(state.revoke());
        assertTrue(state.isRevoked());
    }
}
~~~

**Đừng triển khai AS nhiều node dựa vào AtomicReference trong bộ nhớ một node**. Lỗi nguy hiểm không nằm ở việc lệnh Java update một biến hai lần, mà ở **hai tiến trình cùng đọc trạng thái cũ, ghi grant/token family và publish events trái nhau**.

### Integration test cần chạy qua endpoint thật

~~~text
Given:
  AS có RT17 ACTIVE, thuộc client C1.
  C1 có client authentication hợp lệ.

When:
  C1 gọi revoke(RT17) và nhận 200.
  C1 gọi lại revoke(RT17) nhiều lần, kể cả hai requests song song
  tới các AS instances khác nhau.

Then:
  RT17 vẫn REVOKED.
  Token endpoint không cho refresh(RT17).
  Số transition ACTIVE -> REVOKED bằng 1.
  Các event thu hồi mang một revision/transition hợp lệ.
  Không có grant mới/refresh token mới từ RT17.
  Không lộ raw RT17 trong telemetry.
~~~

Test không được chỉ assert **HTTP 200 hai lần**: một AS có thể trả 200 trong khi refresh token vẫn đang ACTIVE hoặc một event chưa commit.

## 20. Xử lý lỗi, HTTP semantics và privacy

| Tình huống | HTTP/OAuth xử lý dự kiến | Có được thay đổi token không? |
|---|---|---|
| Client hợp lệ, token active thuộc client | **200 OK** sau xử lý thành công | Có, ACTIVE → REVOKED |
| Client hợp lệ, token đã revoked | **200 OK** | Không, no-op |
| Client hợp lệ, token hết hạn/không biết | **200 OK** | Không, no-op |
| Confidential client sai credential | **invalid_client**/HTTP error phù hợp | **Không** |
| Request thiếu token parameter | **invalid_request** | **Không** |
| Token thuộc client khác | Từ chối theo quyền và bảo vệ thông tin | **Không** thu hồi token bên khác |
| Token type AS không hỗ trợ revocation | **unsupported_token_type** trong trường hợp áp dụng | Không giả vờ thành công |
| Backend trạng thái không commit được | Lỗi server/dependency, có thể 5xx | Không trả thành công giả |
| Revocation service tạm unavailable | **503** phù hợp RFC 7009; client retry có giới hạn | Không khẳng định đã revoke |
| Sai CORS/transport, client chưa có quyền endpoint | Từ chối đúng transport/policy | Không bypass client auth |

### Response lỗi minh họa

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "unsupported_token_type"
}
~~~

Không suy mọi loại token server không tìm được đều là **unsupported_token_type**: token **không tồn tại/invalid** có ngữ nghĩa **200** sau khi request hợp lệ được xử lý; **unsupported_token_type** chỉ hợp lý khi loại token thực sự không thể được hỗ trợ bởi revocation service theo hợp đồng.

### Thời gian và side-channel

Trả cùng HTTP status nhưng thời gian xử lý rất khác nhau giữa token tồn tại và token không tồn tại có thể tạo **timing oracle** trong một số bối cảnh. Không hứa hệ thống luôn constant-time qua database/network (thực tế khó), nhưng nên:

- Giới hạn thông tin response, headers và nội dung lỗi.
- Áp dụng rate limiting/abuse controls.
- Không in token ID/subject/client thực ra response công khai.
- Cân nhắc hành vi tra cứu/độ trễ khác biệt lớn nếu threat model cần.
- Lưu audit an toàn để điều tra, không thay response bằng “token tồn tại” chỉ cho mục đích debug.

**Token giá trị ngẫu nhiên được gửi trong revoke request vẫn là credential nhạy cảm**. Việc endpoint chỉ dùng nó để xóa quyền không làm raw token trở thành dữ liệu có thể log công khai.

## 21. Audit và quan sát: phân biệt attempt với state transition

Trong vận hành, cần ghi nhận hai loại sự kiện:

1. **Revoke request/attempt**: một request đến endpoint, có thể timeout, invalid, retry hoặc bị từ chối.
2. **Revocation state transition**: một token/grant thật sự đổi từ ACTIVE sang REVOKED.

Ví dụ:

~~~text
Request r-101: revoke RT17 -> transition 1, HTTP 200
Request r-102: retry RT17 -> no transition, HTTP 200
Request r-103: retry RT17 -> no transition, HTTP 200

Metrics:
  revocation_requests_total       = 3
  revocation_state_transitions    = 1
  revocation_public_response_200  = 3
~~~

**Không ép requests_total bằng transitions_total**. Các lần retry là request thật có thể cần ghi metrics, nhưng **không phải ba lần token bị thu hồi**.

Một event an toàn:

~~~json
{
  "event_type": "TOKEN_REVOKED",
  "request_id": "req-example-701",
  "issuer_ref": "auth-main",
  "client_ref": "orders-bff",
  "token_ref": "token-record-17",
  "grant_ref": "grant-example-9",
  "state_transition": "ACTIVE_TO_REVOKED",
  "revision": 4,
  "source": "OAUTH_REVOCATION_ENDPOINT"
}
~~~

**token_ref** ở đây là tham chiếu nội bộ, không phải bearer token hoặc refresh token thật. Nếu cần tương quan raw token, dùng **HMAC fingerprint** bằng khóa được quản lý tốt và giới hạn quyền truy cập; không đưa fingerprint/token/account ID vào metric labels công khai hay log debug không cần thiết.

### Những chỉ số vận hành hữu ích

| Metric | Điều đo | Ý nghĩa |
|---|---|---|
| **revocation_requests_total** | Số request qua endpoint | Nhận diện retry/traffic bất thường |
| **revocation_state_transitions_total** | Lần token từ active sang revoked | Kiểm idempotence |
| **revocation_error_total** | 400/401/503/5xx theo nhóm nguyên nhân | Phân biệt lỗi client với AS outage |
| **revoke_commit_latency** | Thời gian từ request hợp lệ tới durable commit | Đo hiệu năng tại AS |
| **revoke_propagation_latency** | Từ AS commit tới RS biết token invalid | Đo freshness SLO end-to-end |
| **invalidation_delivery_lag** | Độ trễ outbox/event tới RS | Phát hiện node/cache chậm |
| **repeat_revoke_attempts** | Số request no-op sau revoke | Có thể do retry bình thường; không tự kết luận attack |
| **refresh_after_revoke_denials** | Số request refresh bằng RT đã revoke | Kiểm hậu quả tại token endpoint |

Để đo propagation chính xác, phải biết AS đã **commit** revoke khi nào, RS sử dụng cơ chế introspection/cache ra sao, và nếu có JWT offline thì kết quả policy mong đợi là gì.

## 22. Tình huống thực tế: ngắt kết nối ứng dụng Sales Report

Giả sử:

~~~text
Authorization Server: https://auth.example.org
Client: sales-report-bff (confidential)
User: user-42
Grant: G1
Refresh token: RT17
Access token: AT51 (aud=orders-api, scope=orders:read)
RS: Orders API
~~~

### Trường hợp A — Người dùng bấm Ngắt kết nối

1. BFF xác thực người dùng theo session và xác định **đúng grant G1**.
2. BFF gửi **revoke RT17** với client authentication hợp lệ.
3. AS commit RT17 REVOKED, cập nhật grant theo policy và trả HTTP 200.
4. BFF xóa token đã lưu trong session/server-side storage và ngừng gọi Orders API.
5. Nếu policy yêu cầu revoke cả AT51, AS/RS dùng cơ chế trạng thái phù hợp để khiến AT51 không còn được chấp nhận.

**Idempotent** ở đây giúp user bấm **Ngắt kết nối** hai lần không làm trạng thái grant mâu thuẫn.

### Trường hợp B — Response mất, BFF retry

Request revoke đầu đã commit nhưng response bị mất. BFF retry RT17. AS trả **200** mà không phát sự kiện transition thứ hai. **Tính idempotent giải quyết ambiguity của request**, không yêu cầu người dùng đăng nhập lại chỉ để “xóa thêm một lần”.

### Trường hợp C — Attacker giữ AT51

Dù RT17 bị revoke, AT51 có thể còn hợp lệ tại Orders API nếu:

- AS không thu hồi AT51 theo policy;
- AT51 là JWT tự chứa và RS chỉ kiểm chữ ký/exp;
- hoặc RS đã cache introspection active trước khi revoke.

Khi nghiệp vụ yêu cầu dừng truy cập sớm, cần **AT revocation, TTL ngắn, introspection/denylist/epoch và cache invalidation**. BFF xóa RT local không đủ chặn bearer AT51 đang nằm ngoài thiết bị.

### Trường hợp D — Một client khác cố thu hồi RT17

Client **billing-worker** gửi raw RT17 nhưng không sở hữu grant. AS **không được revoke RT17** chỉ vì token string đúng. Đòi hỏi **client authentication/ownership** không mâu thuẫn với idempotence; đó là điều kiện để revoke hợp lệ.

### Trường hợp E — Đổi tài khoản hoặc tenant

User-42 có quyền với tenant-A và tenant-B, nhưng BFF chỉ được kết nối grant G1 của tenant-A. Không dùng request “ngắt tenant-A” để revoke mọi token/grant của tenant-B chỉ vì cùng subject. Cần định nghĩa scope của thao tác, actor authority và audit phù hợp.

## 23. Ma trận kiểm thử Idempotent revoke request

Mỗi test dùng **test tokens, test clients và một AS thật trong môi trường kiểm thử**. Kiểm cả HTTP response, token state, grant/token family, event outbox và hành vi Resource Server.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| **S01** | Client hợp lệ revoke RT đang ACTIVE | **200**, token thành REVOKED |
| **S02** | Cùng client revoke RT đã REVOKED | **200**, không tạo transition thứ hai |
| **S03** | Client revoke chuỗi token unknown | **200** khi request hợp lệ, không tiết lộ tồn tại |
| **S04** | Client revoke token đã EXPIRED | **200**, không hồi sinh token |
| **S05** | Revoke access token loại AS hỗ trợ | AT inactive theo policy, response thành công |
| **S06** | Revoke không có token_type_hint | AS vẫn xử lý token đúng |
| **S07** | Hint sai, RT thực bị gửi kèm hint access_token | AS tìm qua các types hỗ trợ và xử lý đúng |
| **F01** | Thiếu token parameter | **invalid_request**, không thay token state |
| **F02** | Confidential client sai secret/client assertion | **invalid_client** hoặc lỗi tương ứng, không revoke |
| **F03** | Caller không có quyền revoke RT của client khác | Không revoke token bên khác |
| **F04** | Header/auth method bị hạ cấp hoặc bỏ xác thực | Không bypass client authentication |
| **F05** | Token type thật không được server hỗ trợ revoke | Lỗi phù hợp, không giả vờ thu hồi thành công |
| **F06** | Caller gửi hint ngẫu nhiên | Không tin hint làm bằng chứng loại token |
| **F07** | Attacker gửi token trong URL query | Transport/policy không chấp nhận rò credential |
| **F08** | Raw token xuất hiện trong access logs/APM | Test phát hiện lỗi rò secrets |
| **F09** | Response HTTP 200 chứa token_exists hoặc user info | Test phát hiện lộ trạng thái/metadata |
| **F10** | Response 200 bị mất rồi client retry | Token vẫn REVOKED, retries an toàn |
| **F11** | Hai AS nodes revoke cùng RT đồng thời | Tối đa một ACTIVE→REVOKED transition |
| **F12** | 100 requests revoke đồng thời | Không tạo 100 token-family jobs hoặc side effects lặp |
| **F13** | DB transaction rollback sau conditional update | Không trả thành công giả; token state nhất quán |
| **F14** | DB commit nhưng publisher chết trước khi gửi event | Outbox gửi lại được; event không mất vĩnh viễn |
| **F15** | Consumer nhận TOKEN_REVOKED hai lần | Idempotent apply, không tái kích hoạt token |
| **F16** | Event cũ đến sau revision mới | Không overwrite revoked bằng active |
| **F17** | Response introspection active=true cũ đến sau invalidate | Không repopulate stale true khi policy yêu cầu fencing |
| **F18** | AS revoke AT, RS cache active quá SLO | Test phát hiện stale acceptance vượt giới hạn |
| **F19** | JWT AT đã revoke nhưng RS chỉ kiểm signature/exp | Test bộc lộ giới hạn; không khẳng định revoke tức thì |
| **F20** | Revoke RT nhưng AT chưa bị AS revoke | RS hành xử đúng trạng thái AS/policy, không mặc định AT inactive |
| **F21** | RT đã revoked được dùng làm grant refresh | Token endpoint từ chối cấp token mới |
| **F22** | Revoke RT lặp bị hiểu là refresh replay | Test phát hiện phân loại nhầm endpoint/sự kiện |
| **F23** | AS trả 503 hoặc network timeout | Client retry có giới hạn, không tự coi revoke đã thành công |
| **F24** | AS trạng thái unavailable nhưng gateway trả 200 | Test phát hiện fail-open hoặc success giả |
| **F25** | Client đã logout local, server revoke chưa chắc thành công | UI/monitoring không tuyên bố all-session revoke sai |
| **F26** | Token active có aud=orders-api nhưng được gửi sang payments-api | RS từ chối sai audience, độc lập với revoke |
| **F27** | ID token hoặc refresh token gửi như Bearer đến API | RS từ chối sai loại credential |
| **F28** | Token còn active nhưng thiếu scope hoặc sai tenant | RS từ chối theo authorization policy |
| **F29** | User ngắt một grant của tenant-A, tenant-B còn grant riêng | Không revoke nhầm ngoài phạm vi |
| **F30** | Client secret bị thu hồi giữa hai revoke requests | Request sau phải qua auth lại; idempotence không bypass |
| **F31** | Một token không tồn tại bị thử nhiều lần với rate cao | Rate limit và chống token-status oracle hoạt động |
| **F32** | Client gửi revocation từ browser không được AS cho phép | Không lách CORS/auth bằng GET/query |
| **F33** | Thời điểm AS commit và RS bắt đầu từ chối được đo | Revocation freshness đạt SLO đã công bố |
| **F34** | Token đã revoked nhưng sự kiện outbox bị redeliver | No-op không tạo event transition mới |
| **F35** | BFF đã xóa raw RT rồi muốn retry sau outage | Không log/lưu credential trái phép; có khôi phục an toàn hoặc thông báo giới hạn |
| **F36** | AT và RT cùng grant, AS policy yêu cầu thu hồi cả hai | Thực hiện đúng lineage và bảo đảm không bỏ sót token liên quan |

### Test 1: revoke hai lần sau response loss

~~~text
Given:
  RT17 ACTIVE, thuộc đúng client C1 đã xác thực.
When:
  Request A: revoke RT17, AS commit nhưng response bị chặn.
  Request B: retry revoke RT17.
Then:
  B nhận 200 nếu AS khỏe và request hợp lệ.
  RT17 vẫn REVOKED, không refresh được.
  Có đúng một token state transition và một event transition.
  Không có access/refresh token mới do retry revoke.
~~~

### Test 2: hai node cùng revoke

~~~text
Given:
  RT17 ACTIVE trong kho trạng thái chia sẻ.
  AS node A và node B xử lý cùng client/token.
When:
  Hai request đồng thời bắt đầu.
Then:
  Chỉ một conditional update thắng transition ACTIVE->REVOKED.
  Side effects xuất phát từ một transition (outbox unique).
  Cả hai request hợp lệ có thể nhận 200.
  Không có record trạng thái ACTIVE được phục hồi sau race.
~~~

### Test 3: HTTP 200 không đồng nghĩa RS đã nhận biết revoke

~~~text
Given:
  Opaque AT51 được RS cache active=true với hard TTL 20 giây.
When:
  AS revoke chính AT51 và trả 200 sau commit.
  RS tiếp tục nhận request với AT51 trong các khoảng thời gian tiếp theo.
Then:
  Nếu có invalidation: token bị từ chối sớm theo contract.
  Nếu chỉ TTL: RS từ chối muộn nhất theo policy freshness.
  Không có cache hit nào gia hạn hard TTL.
  Không tuyên bố revoke tức thì nếu triển khai không bảo đảm.
~~~

## 24. Checklist trước khi triển khai revocation endpoint

1. **RFC 7009:** Đúng POST/form body, tham số token bắt buộc, phản hồi 200 cho token đã invalid trong ngữ cảnh request hợp lệ?
2. **Client auth:** Confidential client có xác thực đúng phương thức; public client có ràng buộc/abuse policy phù hợp?
3. **Ownership:** Client chỉ có thể revoke token/grant mà nó được phép, không vì biết raw token mà xóa của client khác?
4. **Token types:** AS phân biệt AT/RT thực, không tin token_type_hint; xử lý unsupported_token_type đúng hợp đồng?
5. **HTTP privacy:** Không lộ token existence, owner, grant, raw token trong success body hoặc error detail?
6. **Transport:** Revocation endpoint qua TLS; không chấp nhận token ở URL/query/log?
7. **Idempotence:** Revoke ACTIVE, REVOKED, EXPIRED, UNKNOWN có state/response phù hợp; không tạo token mới?
8. **Atomicity:** State change dùng transaction/locking/CAS trên mọi AS instances; không read-then-write race?
9. **Commit:** Không trả 200 trước khi transition được commit bền vững theo hợp đồng?
10. **Outbox:** State change và event được ghi nhất quán; consumers idempotent với duplicate event?
11. **Ordering:** Event đến trễ/sai thứ tự không hồi sinh token hoặc làm cache active trở lại?
12. **Refresh family:** Quyết định rõ revoke RT đơn lẻ, cả family, underlying grant hay AT liên quan?
13. **Replay:** Revoke lặp không bị nhầm là refresh-token reuse tại token endpoint?
14. **JWT:** RS biết giới hạn thu hồi sớm của self-contained JWT; có denylist/epoch/introspection nếu cần?
15. **Opaque:** Introspection trả active=false đúng và positive cache TTL không vượt freshness policy?
16. **Audience/scope:** Resource Server luôn kiểm iss/aud/exp/scope và quyền đối tượng, không chỉ token active?
17. **Logout:** Xóa local credential, AS revoke và RS propagation được phân biệt trong UX/SLO?
18. **Retry:** Client có timeout/backoff/jitter/attempt budget, không retry credential lỗi hoặc infinite loop?
19. **AS outage:** 503/5xx không biến thành success giả; có khả năng sửa/retry và giám sát?
20. **Audit:** Tách request attempts khỏi state transitions; log internal refs, không raw secrets?
21. **Testing:** Có unknown-token, already-revoked, wrong-client, hint mismatch, rollback, concurrency, outbox, JWT/opaque và cache tests?
22. **Incident response:** Có quy trình revoke grant/AT/RT, xác định token lineage và đánh giá thời gian tiếp tục truy cập sau revoke?

## 25. Câu hỏi tự đánh giá

**1. Idempotent revoke request nghĩa là gì?** Gọi lại thao tác revoke hợp lệ trên cùng token không được làm token sống lại hoặc tạo chuyển trạng thái và quyền mới; token đã invalid vẫn invalid.

**2. RFC 7009 trả gì nếu client gửi token không tồn tại?** Với revocation request hợp lệ, **HTTP 200 OK** để không biến endpoint thành oracle và vì mục tiêu token không còn hợp lệ đã đạt.

**3. Một client bất kỳ có được revoke token của client khác chỉ vì biết token không?** Không. AS phải xác minh client và quyền đối với token/grant; idempotence không bỏ qua authentication/authorization.

**4. token_type_hint=refresh_token có chứng minh giá trị gửi lên là refresh token không?** Không. Hint chỉ hỗ trợ tra cứu; AS phải xác định loại token thật từ dữ liệu tin cậy.

**5. Vì sao hai request revoke đồng thời vẫn cần atomicity nếu state cuối cùng đều REVOKED?** Vì hai request có thể kích hoạt **outbox events, notification, family revocation hoặc counters** lặp/khác nhau; cần một transition duy nhất theo policy.

**6. Nếu response 200 đầu bị mất, client có thể retry không?** Có thể retry bounded theo policy; request revoke hợp lệ được thiết kế idempotent. Không retry vô hạn hoặc bỏ qua client authentication.

**7. HTTP 200 có chứng minh tất cả JWT access token của grant bị vô hiệu tại RS ngay không?** Không. JWT self-contained có thể còn được chấp nhận tới exp nếu RS không kiểm trạng thái revoke; opaque introspection cache cũng tạo độ trễ.

**8. Revoke refresh token hai lần có phải refresh-token replay attack không?** Không. Revoke endpoint là thao tác kết thúc hiệu lực; refresh-token replay liên quan việc dùng RT đã rotate/revoke ở **token endpoint** để xin token mới.

**9. Khi AS timeout và client chưa nhận response, có thể tuyên bố server đã revoke thành công không?** Không. Có thể đã commit hoặc chưa; cần retry có kiểm soát hoặc workflow phục hồi đáng tin và mô tả trạng thái chính xác.

**10. Vì sao cần outbox hoặc cơ chế tương đương?** Để state revoke đã commit không bị mất thông báo tới RS khi process chết; consumer vẫn cần idempotent vì event có thể được gửi lại.

**11. Một cached active=true tại API có được giữ nguyên 30 phút sau revoke không?** Không mặc định. TTL phải theo freshness SLO và không vượt exp; có thể cần invalidation hoặc kiểm trạng thái mỗi request cho API nhạy cảm.

**12. Đăng xuất local có đồng nghĩa thu hồi token ở AS không?** Không. Xóa credential local, revoke token/grant và Resource Server nhận biết trạng thái là những bước khác nhau.

**13. Có cần thêm Idempotency-Key vào mọi request RFC 7009 không?** Không. Ngữ nghĩa revoke đã idempotent theo token state; một orchestration API riêng có thể dùng command ID nếu cần chống side effects lặp.

**14. Kiểm thử nào quan trọng nhất?** Revoke cùng token sau mất response và đồng thời trên nhiều AS nodes; xác nhận **một transition bền vững**, token không thể refresh/được dùng trái policy, và kết quả tại RS phù hợp SLO.

**Ghi nhớ:** **Idempotent revoke request** trong OAuth 2.0 nghĩa là một yêu cầu thu hồi **hợp lệ** có thể được gửi lại mà không làm token sống lại, không tạo token/grant mới và không thực hiện side effects sai; **RFC 7009 trả HTTP 200 cả khi token đã không hợp lệ**. Tính idempotent luôn đi kèm **xác thực client, kiểm quyền thu hồi, atomic state transition và audit/event deduplication**. Sau khi AS thu hồi token, **introspection cache, JWT offline validation và Resource Server authorization** vẫn quyết định thời điểm quyền truy cập thực sự dừng. Không đồng nhất **200 OK** với **thu hồi tức thì toàn hệ thống**; hãy thiết kế và kiểm thử riêng **revocation freshness SLO**.
