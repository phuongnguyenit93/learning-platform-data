# Audit việc cấp và sử dụng scope

Trong OAuth 2.0/OIDC, **scope** mô tả phạm vi truy cập mà một client xin và được phép sử dụng. Để đảm bảo tính bảo mật và khả năng giải trình, hệ thống không chỉ cần **kiểm tra scope** khi gọi API mà còn phải biết **ai xin, ai hoặc chính sách nào chấp thuận, Authorization Server (AS) đã cấp những quyền nào, token được dùng ở đâu và kết quả phân quyền ra sao**.

Đó là mục tiêu của **audit việc cấp và sử dụng scope**: tạo dấu vết có thể kiểm chứng xuyên suốt vòng đời authorization grant, access token, refresh token, Resource Server và quá trình thu hồi. Audit phục vụ phát hiện lạm quyền, phân tích sự cố, điều tra việc token bị đánh cắp/phát lại, rà soát **least privilege**, đồng thời cung cấp dữ liệu cho cải tiến chính sách.

Bài học thuộc chương **Scope** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Ngoài audit scope, cần nắm mô hình tin cậy giữa user, client, AS và API; phân biệt JWT/opaque, access/refresh token, kiểm tra issuer, audience, claims, thời gian, lưu trữ, thu hồi và bảo vệ bearer token. Các ví dụ dùng hệ thống giả định `orders-web`, `auth.example.test` và `orders-api`, không đại diện một hệ thống triển khai thật.

> **Nguyên tắc cốt lõi:** *Audit là bằng chứng về một quyết định hoặc hành vi đã xảy ra; nó không thay thế kiểm tra authorization tại thời điểm request.* Một bản ghi `scope_granted` không tự chứng minh token hiện tại hợp lệ hay user được xem một đối tượng cụ thể.

## 1. Audit scope trả lời những câu hỏi gì?

Một bộ audit có ích cần trả lời được các câu hỏi ở ba lớp:

| Lớp | Câu hỏi điều tra | Bằng chứng cần có |
|---|---|---|
| **Cấp quyền (grant)** | Client nào xin những scope gì? User/admin/policy nào đã cho phép hoặc từ chối? | Authorization request, quyết định grant/consent, tập scope requested/granted, lý do và chính sách |
| **Phát hành token (issuance)** | AS cấp token cho client nào, subject nào, audience/API nào, thời hạn bao lâu, trên grant nào? | Token metadata, grant reference, `client_id`, `iss`, `aud`, scope được cấp, TTL, loại grant và kết quả |
| **Sử dụng (enforcement)** | API nào đã chấp nhận/từ chối token, endpoint nào được gọi, scope nào được yêu cầu và quyền tài nguyên đã được xét ra sao? | Authenticated token context, route template, required scope, decision, reason code và request correlation |
| **Thay đổi, thu hồi** | Quyền nào bị mở rộng/thu hẹp, grant bị hủy lúc nào, token sau đó còn được chấp nhận không? | Grant change, revoke, refresh, introspection/revocation state và API decision sau đó |

Ví dụ: ứng dụng báo cáo chỉ cần `orders:read` nhưng AS từng cấp thêm `orders:export`. Bản ghi grant cho biết **quyền đã cấp**; bản ghi API cho biết **quyền có được dùng**. Kết hợp hai nguồn mới có thể phát hiện scope quá rộng hoặc hành vi xuất dữ liệu đáng ngờ.

**Không đồng nhất ba trạng thái:** quyền *đã yêu cầu*, quyền *được cấp* và quyền *được sử dụng thực tế*.

## 2. Ranh giới và luồng bằng chứng đầu cuối

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / Admin
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    participant A as Audit Pipeline / SIEM

    C->>AS: Authorization request + requested scopes
    AS->>AS: Xác minh client, redirect, user/grant, policy
    AS->>U: Xin consent nếu chính sách yêu cầu
    U-->>AS: Cho phép hoặc từ chối
    AS->>A: authz.grant.decided (requested, granted, outcome)
    alt Grant hợp lệ
        AS-->>C: Authorization code
        C->>AS: Token request + PKCE / client authentication
        AS->>A: token.issued (client, audience, granted scope, TTL)
        AS-->>C: Access token (+ refresh token nếu có)
        C->>RS: API request với access token
        RS->>RS: Verify token + scope + object policy
        RS->>A: api.authorization.decided (scope, allow/deny, route)
        RS-->>C: 2xx / 401 / 403 / 404 tùy kết quả
    else Bị từ chối
        AS-->>C: Authorization error
    end
    U->>AS: Thu hồi quyền sau đó (nếu có)
    AS->>A: grant.revoked / token.revoked
~~~

Điểm cần lưu ý:

- **AS biết quyết định cấp quyền**, nhưng không nhất thiết biết toàn bộ thao tác thật sự tại API nếu access token là JWT tự xác minh.
- **Resource Server biết quyết định phân quyền request**, nhưng không nên tự đoán consent hoặc grant từ một chuỗi `scope` chưa được xác minh.
- **Client không phải nguồn audit đáng tin duy nhất**, vì client có thể bị chiếm quyền hoặc cố tình bỏ log hành vi.
- **Audit pipeline** nhận bản ghi có xác thực nguồn, đồng bộ thời gian, bảo vệ tính toàn vẹn và có chính sách truy cập phù hợp.
- **Resource ownership/tenant policy** cần được kiểm tra độc lập với `scope`. Audit quyết định scope và quyết định object-level ở mức đủ để điều tra mà không làm lộ dữ liệu nhạy cảm.

Đối với confidential client, public client, delegated user grant hoặc `client_credentials`, thông tin về **actor và subject** không giống nhau. Không được tự khẳng định có người dùng thực nếu token được phát hành cho danh tính service.

## 3. Những sự kiện cần audit trong vòng đời scope

Không cần mọi sản phẩm sử dụng cùng tên sự kiện, nhưng nên có một **taxonomy ổn định, có phiên bản**. Tên ví dụ dưới đây là hợp đồng nội bộ gợi ý:

| Event type | Nguồn tạo | Khi nào ghi? | Thuộc tính quan trọng |
|---|---|---|---|
| `authz.request.received` | AS | Nhận yêu cầu cấp quyền | Client, request ID, requested scopes, resource |
| `authz.grant.decided` | AS | Chính sách/consent quyết định cho phép hoặc từ chối | Requested scopes, granted scopes, decision, policy version, actor type |
| `authz.grant.changed` | AS | Grant tăng/giảm quyền hoặc điều kiện | Before/after scope set, grant ref, người/nguồn thay đổi |
| `token.issued` | AS | Cấp access token hoặc refresh token | Grant/client ref, token type, audience, scope, expiry, issuance method |
| `token.refresh.decided` | AS | Refresh thành công/thất bại | Grant/client ref, token family ref, outcome, reason (reuse, expired, revoked...) |
| `token.revoked` | AS | Token bị thu hồi theo cơ chế hỗ trợ | Token ref, actor, reason, effective time |
| `authz.grant.revoked` | AS | User/admin/policy hủy grant | Grant ref, scope set trước thu hồi, reason |
| `api.token.validation` | RS | Token được chấp nhận hoặc từ chối ở lớp authentication | Issuer/audience/result, failure category |
| `api.authorization.decided` | RS | Áp dụng scope, client/user và quyền tài nguyên | Route template, required scopes, granted scopes hoặc scope reference, decision |
| `security.scope.anomaly` | Detection/SIEM | Phát hiện dấu hiệu nguy cơ | Rule ID/version, liên kết sự kiện, độ tin cậy, trạng thái điều tra |

**Không yêu cầu log từng bước kỹ thuật không có ý nghĩa** nếu gây trùng lặp lớn; thay vào đó cần bảo đảm các điểm kiểm soát quan trọng có bằng chứng. Một request có thể sinh cả sự kiện token validation và authorization decision, nhưng phải liên kết được và tránh đếm chúng thành hai lần sử dụng.

### Các nhóm kết quả cần chuẩn hóa

Sử dụng `outcome` và `reason_code` có tập giá trị được quản lý, ví dụ:

- `ALLOW` / `DENY` / `ERROR`: quyết định hoặc kết quả thực hiện, phân biệt authorization decision với lỗi hệ thống.
- `SCOPE_GRANTED`, `SCOPE_REDUCED`, `USER_DENIED`, `POLICY_DENIED`.
- `INVALID_TOKEN`, `INVALID_AUDIENCE`, `EXPIRED_TOKEN`, `INSUFFICIENT_SCOPE`.
- `OBJECT_POLICY_DENIED`, `TENANT_BOUNDARY_DENIED`, `REVOKED_GRANT`, `REFRESH_REUSE_DETECTED`.
- `AUDIT_SINK_UNAVAILABLE` là sự kiện vận hành khi không thể ghi bằng chứng theo chính sách.

Không nên chỉ ghi `HTTP 403` rồi suy ra nguyên nhân là thiếu scope. `403` có thể do ACL, tenant, policy hoặc điều kiện nghiệp vụ; `404` cũng có thể được dùng để che giấu sự tồn tại của tài nguyên không được phép.

## 4. Thiết kế schema audit: đủ để điều tra, không rò bí mật

Một bản ghi audit tốt phải **có cấu trúc**, có khả năng liên kết qua các dịch vụ, nhưng không trở thành bản sao token hoặc kho dữ liệu nhạy cảm.

| Nhóm dữ liệu | Field gợi ý | Lý do |
|---|---|---|
| **Định danh sự kiện** | `event_id`, `event_type`, `schema_version` | Khử trùng lặp, truy vết hợp đồng và phân biệt phiên bản |
| **Thời gian** | `occurred_at`, `observed_at` | Phân biệt lúc hành động xảy ra và lúc hệ thống nhận log |
| **Nguồn** | `source_service`, `environment`, `issuer` | Truy nguồn AS/RS đáng tin |
| **Liên kết** | `correlation_id`, `trace_id`, `grant_ref`, `token_ref` | Ghép issuance/usage/revocation không cần lưu token gốc |
| **Chủ thể** | `actor_type`, `actor_ref`, `subject_ref`, `client_id` | Phân biệt user, admin, service, client và user được đại diện |
| **Quyền** | `requested_scopes`, `granted_scopes`, `required_scopes` | Kiểm tra scope cấp và dùng có đúng không |
| **Nơi nhận** | `audience`, `resource_server`, `route_template` | Chống nhầm token của API khác và hỗ trợ thống kê |
| **Kết quả** | `outcome`, `reason_code`, `policy_version` | Biết được vì sao cho phép/từ chối tại thời điểm đó |
| **Bảo mật và vận hành** | `token_type`, `grant_type`, `expires_at`, `assurance_ref` | Làm rõ ngữ cảnh và vòng đời token |
| **Ngữ cảnh có kiểm soát** | `tenant_ref`, `resource_type`, `request_risk_band` | Điều tra quyền tài nguyên mà hạn chế dữ liệu riêng tư |

**Phân biệt ba mốc thời gian:** thời điểm sự kiện, thời điểm hệ thống log thu nhận, và thời điểm token/authorization grant có hiệu lực hoặc hết hạn. Đồng bộ đồng hồ qua nguồn tin cậy và lưu UTC theo ISO 8601 để điều tra thứ tự.

### Tuyệt đối tránh đưa gì vào log?

- **Không lưu raw access token, refresh token, ID token, authorization code, client secret, mật khẩu, PKCE `code_verifier` hay cookie phiên.**
- Không log `Authorization` header, nguyên URL có query chứa bí mật, hoặc toàn bộ token response.
- Không lưu payload JWT nguyên bản chỉ vì đã Base64url decode được; nó có thể chứa PII và claim nhạy cảm.
- Hạn chế email, IP đầy đủ, user agent chi tiết, tên file, số đơn hàng, định danh nội bộ nhạy cảm nếu không thực sự cần cho mục tiêu audit. Cân nhắc pseudonymization, phân lớp quyền đọc và thời hạn lưu.
- Không để log chứa chuỗi do người dùng kiểm soát mà chưa được canonicalize/escape, để tránh log injection hoặc làm hỏng định dạng.

Thay vào đó, dùng **định danh tham chiếu được AS/RS tạo** và, khi cần liên kết mà không lộ ID gốc, **pseudonym có kiểm soát**. Chẳng hạn `grant_ref` là định danh nội bộ thay vì authorization code; `token_ref` có thể là mã tham chiếu an toàn từ AS hoặc HMAC của token ID với khóa chỉ dùng cho tương quan. Không dùng hash của mật khẩu/secret hoặc dùng cùng một pseudonym cho mọi hệ thống vô thời hạn nếu không cần.

Nếu dùng HMAC tạo token reference từ giá trị có thể bị đoán, khóa HMAC phải nằm trong dịch vụ được tin cậy và được quản lý theo chính sách. Hash không khóa của một ID entropy thấp **không** đủ bảo vệ khỏi việc dò ngược.

## 5. Các bản ghi audit mẫu

### 5.1. AS ghi quyết định cấp quyền

Ví dụ ứng dụng `orders-web` xin `orders:read` và `orders:export`, nhưng chính sách chỉ chấp thuận đọc:

~~~json
{
  "schema_version": 1,
  "event_id": "ev-authz-102",
  "event_type": "authz.grant.decided",
  "occurred_at": "2026-11-23T10:01:05Z",
  "source_service": "authorization-server",
  "correlation_id": "req-flow-8f2",
  "actor_type": "user",
  "actor_ref": "usr-pseudo-71",
  "subject_ref": "usr-pseudo-71",
  "client_id": "orders-web",
  "grant_ref": "grant-ref-68",
  "audience": "https://orders-api.example.test",
  "requested_scopes": ["orders:read", "orders:export"],
  "granted_scopes": ["orders:read"],
  "outcome": "ALLOW",
  "reason_code": "SCOPE_REDUCED",
  "policy_version": "orders-authz-v4"
}
~~~

**Quan trọng:** log cả phạm vi **đã xin** và **đã cấp**; không đánh đồng chúng. `outcome=ALLOW` có nghĩa grant giới hạn đã được chấp thuận, không có nghĩa toàn bộ requested scopes được cấp.

Nếu user từ chối hoặc policy bác bỏ toàn bộ, bản ghi phải có `outcome=DENY`, reason phù hợp và **không** ghi rằng access token đã được cấp.

### 5.2. AS ghi phát hành token

~~~json
{
  "schema_version": 1,
  "event_id": "ev-token-213",
  "event_type": "token.issued",
  "occurred_at": "2026-11-23T10:01:07Z",
  "source_service": "authorization-server",
  "correlation_id": "req-flow-8f2",
  "client_id": "orders-web",
  "grant_ref": "grant-ref-68",
  "token_ref": "tok-pseudo-213",
  "token_type": "access_token",
  "grant_type": "authorization_code",
  "audience": "https://orders-api.example.test",
  "granted_scopes": ["orders:read"],
  "expires_at": "2026-11-23T10:11:07Z",
  "outcome": "ALLOW",
  "reason_code": "TOKEN_ISSUED"
}
~~~

`token_ref` chỉ là mã liên kết audit, **không phải access token thật**. Token endpoint có thể cấp refresh token theo chính sách riêng; nếu cần audit lần cấp refresh token, tạo sự kiện tách biệt với token type phù hợp và không lưu giá trị refresh token.

### 5.3. API ghi sử dụng scope

~~~json
{
  "schema_version": 1,
  "event_id": "ev-api-901",
  "event_type": "api.authorization.decided",
  "occurred_at": "2026-11-23T10:02:00Z",
  "source_service": "orders-api",
  "correlation_id": "api-req-55a",
  "issuer": "https://auth.example.test",
  "client_id": "orders-web",
  "subject_ref": "usr-pseudo-71",
  "grant_ref": "grant-ref-68",
  "token_ref": "tok-pseudo-213",
  "audience": "https://orders-api.example.test",
  "http_method": "GET",
  "route_template": "/orders/{orderId}",
  "resource_type": "order",
  "tenant_ref": "tenant-pseudo-4",
  "required_scopes": ["orders:read"],
  "verified_scopes": ["orders:read"],
  "outcome": "ALLOW",
  "reason_code": "SCOPE_AND_OBJECT_POLICY_PASSED",
  "policy_version": "orders-resource-v8"
}
~~~

Bản ghi này phải phát sinh từ **Resource Server sau khi xác minh token và chính sách quyền**, không từ header `scope` do client tự tạo. Không đưa `/orders/123?token=...` vào trường URL; dùng route template `/orders/{orderId}` và resource type để giảm rủi ro lộ dữ liệu hoặc cardinality quá cao.

### 5.4. API từ chối thao tác thiếu scope

~~~json
{
  "schema_version": 1,
  "event_id": "ev-api-902",
  "event_type": "api.authorization.decided",
  "occurred_at": "2026-11-23T10:03:00Z",
  "source_service": "orders-api",
  "correlation_id": "api-req-56b",
  "client_id": "orders-web",
  "token_ref": "tok-pseudo-213",
  "http_method": "POST",
  "route_template": "/orders/export",
  "required_scopes": ["orders:export"],
  "verified_scopes": ["orders:read"],
  "outcome": "DENY",
  "reason_code": "INSUFFICIENT_SCOPE",
  "http_status": 403,
  "policy_version": "orders-resource-v8"
}
~~~

Bốn JSON trên chỉ là mô hình minh họa, chưa phải schema tiêu chuẩn bắt buộc. Ở hệ thống thật, `grant_ref` có thể không được đưa tới API hoặc token không mang thông tin đó. Khi không có nguồn liên kết đáng tin cậy, **ghi thiếu tham chiếu thay vì bịa ra hoặc dựa trên dữ liệu client tự khai**.

## 6. Ghép chuỗi: grant → token → API → thu hồi

Audit scope thường thất bại vì log của AS và log của API không có cách liên kết.

~~~mermaid
flowchart LR
    A["authz.grant.decided\n(grant_ref)"] --> B["token.issued\n(token_ref, grant_ref)"]
    B --> C["api.authorization.decided\n(token_ref hoặc mapping tin cậy)"]
    B --> D["token.refresh.decided\n(token family ref)"]
    D --> E["token.issued mới"]
    F["authz.grant.revoked\n(grant_ref)"] --> G["Kiểm tra request sau thu hồi"]
    E --> G
    C --> G
~~~

Một bộ correlation nên hỗ trợ:

1. **Authorization transaction ID** liên kết `state`/PKCE và kết quả quyết định ở AS, nhưng **không ghi bản thân `state`/`code_verifier`** nếu không cần và không ghi authorization code.
2. **Grant reference** cho biết quyền ủy quyền nào đã tạo điều kiện phát hành token.
3. **Token reference** giúp phân biệt token cụ thể; dùng ID do AS cấp hoặc pseudonym được bảo vệ, không ghi raw token.
4. **Refresh token family reference** nếu AS có rotation để lần theo chuỗi refresh và xử lý reuse.
5. **Request/trace correlation ID** qua gateway, API và dịch vụ downstream, có giới hạn tin cậy và độ dài, để liên kết quyết định.
6. **Issuer/audience/client_id** để phân biệt cùng một user đăng nhập nhiều AS/client/API.

Không phải mọi token đều có `jti`, và `jti` có thể không ổn định hoặc không có ý nghĩa ngoài profile. Với opaque token, API có thể biết token reference thông qua introspection/mapping tin cậy. Nếu không thể đối chiếu token cụ thể, audit vẫn có thể theo grant/client/audience/request nhưng phải **nêu rõ giới hạn điều tra**.

**Tránh nhầm correlation ID với bằng chứng bảo mật.** Request ID do client gửi có thể bị trùng, giả mạo hoặc dùng để làm sai lệch log. Gateway/service nên tạo ID đáng tin cậy hoặc chỉ chấp nhận header với kiểm tra phù hợp. Correlation không thay thế xác minh JWT/introspection.

## 7. Audit ở Authorization Server: yêu cầu, quyết định và cấp token

AS là nơi có bằng chứng gốc về **quyền đã xin** và **quyền đã được cấp**.

### Authorization grant có user

Tại authorization endpoint, audit:

- Client đã đăng ký nào gửi request; phương thức/response type nào và redirect URI đã hợp lệ hay bị bác.
- Requested scopes, resource/audience mong muốn và các ràng buộc authorization details nếu hệ thống dùng RAR.
- User/tenant/admin hoặc nguồn policy có thẩm quyền, **không sao chép dữ liệu xác thực nhạy cảm**.
- Quyết định `ALLOW`/`DENY`, granted scopes, lý do giảm scope, policy/consent version và thời điểm.
- Có yêu cầu xác thực lại/MFA và đã được xử lý theo policy chưa, bằng mã mức đảm bảo hoặc reference an toàn thay vì dữ liệu credential.

Nếu một người dùng chỉ có quyền đối với tenant A, AS không được vì màn hình consent mà cấp quyền vượt giới hạn tổ chức. Audit phải chỉ ra chính sách nào đã áp dụng và phạm vi nào **thực sự được phép**.

### Token endpoint

Khi đổi authorization code, refresh token hoặc client credentials thành access token:

- Ghi `grant_type`, client identity đã xác thực, token type, audience, scopes được cấp, thời hạn.
- Với `authorization_code`, liên kết về grant/authorization transaction; **không log code hoặc PKCE verifier**.
- Với `refresh_token`, theo dõi rotation/reuse theo token-family reference; nếu grant bị giảm scope hoặc thu hồi, ghi quyết định và kết quả.
- Với `client_credentials`, **không gán user actor giả**. Token đại diện quyền client/service theo chính sách.
- Với token exchange/on-behalf-of, ghi subject/actor/client/audience mới và chính sách chống tăng quyền; không tự giả định token downstream có cùng scope.

Nếu một token response cấp scope **khác** scope client yêu cầu, theo OAuth 2.0 AS phải phản ánh phạm vi thực tế trong token response khi phù hợp. Audit phải luôn lưu **granted scopes thực tế**, không chỉ các scope của request.

### Deny và lỗi

Không chỉ log thành công. Những sự kiện như `invalid_client`, `invalid_grant`, `invalid_scope`, từ chối consent hoặc refresh token reuse là dữ liệu điều tra quan trọng. Tuy nhiên, nếu có các lần thử credential rất lớn, cần chống log flooding bằng quy tắc vận hành thích hợp **mà không làm mất sự kiện bảo mật bắt buộc**.

## 8. Audit ở Resource Server: không chỉ là HTTP status

Resource Server phải xác minh token trước khi dựa vào scope.

| Thứ tự kiểm tra | Bằng chứng audit phù hợp | Điều cần tránh |
|---|---|---|
| **Token được cung cấp đúng cách?** | Có/không, loại credential, outcome; không raw token | Ghi `Authorization` header |
| **Token hợp lệ?** | Issuer được tin cậy, audience phù hợp, chữ ký/`active`/thời gian, reason nếu lỗi | Tin `scope` từ JWT chưa verify |
| **Đúng token profile?** | Access token vs ID token, bearer vs sender-constrained | Dùng ID token thay access token |
| **Đủ scope?** | Verified scopes hoặc reference, required scopes, scope decision | Substring match, tự kế thừa `write` thành `read` |
| **Đủ quyền object/tenant?** | Policy/decision, tenant ref, resource type | Chỉ kiểm tra scope rồi bỏ ACL/BOLA |
| **Kết quả cuối?** | `ALLOW`/`DENY`/`ERROR`, http status, reason code, policy version | Gộp lỗi business, thiếu scope và hết hạn vào một lý do |

Ví dụ API nhận JWT đúng chữ ký/issuer nhưng có `aud` là Billing API. API Orders **phải từ chối**; bản ghi nên có `INVALID_AUDIENCE` chứ không phải `INSUFFICIENT_SCOPE` vì token chưa được chấp nhận để xét scope tại Orders.

Với **opaque token**, API lấy `active`/scope/audience từ introspection được xác thực. Nếu API cache kết quả introspection, cần audit/đo được chính sách cache và độ trễ thu hồi; **cache dài có thể làm token bị thu hồi tiếp tục được chấp nhận**.

Một request bị từ chối vì chủ thể không sở hữu đối tượng nên ghi `OBJECT_POLICY_DENIED` hoặc `TENANT_BOUNDARY_DENIED`, không mặc nhiên `INSUFFICIENT_SCOPE`.

### Thành công có cần log toàn bộ?

Đây là quyết định dựa trên yêu cầu điều tra và chi phí:

- Đối với endpoint nhạy cảm (xuất dữ liệu hàng loạt, thay đổi quyền, xóa, thanh toán), thường cần **bằng chứng đầy đủ và đáng tin cậy** theo policy.
- Với đọc dữ liệu khối lượng rất lớn, có thể dùng thống kê tổng hợp/sampling cho **telemetry** nhưng **không được thay thế những log audit bắt buộc**.
- Nếu phát hiện log sink lỗi, hành vi **fail closed** hay **fail open kèm hàng đợi bền vững và cảnh báo** phải được định nghĩa riêng cho mức rủi ro nghiệp vụ; không mặc định bỏ qua âm thầm.

## 9. Audit khác monitoring và tracing như thế nào?

| Thuộc tính | Audit | Monitoring / metrics | Distributed tracing |
|---|---|---|---|
| Mục tiêu chính | Bằng chứng ai/quyền gì/đã làm gì/quyết định nào | Xu hướng, tỷ lệ lỗi, sức khỏe hệ thống, bất thường | Theo dấu request qua các hop |
| Dữ liệu | Sự kiện có ngữ nghĩa bảo mật, provenance và reason | Counter, histogram, aggregate | Span ID, timing, service edges |
| Độ đầy đủ | Theo yêu cầu chính sách, không được mất sự kiện trọng yếu | Có thể sampling/aggregate có kiểm soát | Thường sampling |
| Bảo vệ | Kiểm soát truy cập chặt, retention, bất biến/tamper evidence | Theo yêu cầu vận hành | Có thể chứa thuộc tính nhạy cảm, cũng cần kiểm soát |
| Có thay nhau được không? | Không | Không | Không |

Một trace có `spanId` và latency không nói rõ user đã **được cấp** `orders:export` hay không. Một dashboard `HTTP 403 tăng` không cho biết nguyên nhân thiếu scope hay vi phạm ACL. Audit cần **trường reason_code và nguồn quyết định đáng tin**, rồi có thể liên kết sang trace/metrics để điều tra sâu hơn.

## 10. Phát hiện overgrant, misuse và token replay qua audit

Sau khi có dữ liệu đáng tin, xây các quy tắc/phân tích có thể giải thích:

| Tín hiệu | Điều kiện ví dụ | Hành động điều tra |
|---|---|---|
| **Overgrant / least privilege** | Nhiều client được cấp `orders:export` nhưng không có API usage tương ứng trong giai đoạn quan sát | Rà soát có nên thu hẹp scope; cân nhắc tính mùa vụ |
| **Bất thường khi cấp quyền** | User/client vừa nhận scope nhạy cảm hoặc admin grant ngoài quy trình bình thường | Đối chiếu request/approval/policy version |
| **Từ chối thiếu scope liên tiếp** | `INSUFFICIENT_SCOPE` tăng mạnh tại endpoint nhạy cảm | Kiểm tra bug client, scope probing hoặc hành vi tấn công |
| **Dùng token sai audience** | Nhiều `INVALID_AUDIENCE` từ một client hoặc tuyến API | Kiểm tra cấu hình audience/token forwarding và token confusion |
| **Dùng lại sau thu hồi** | API ghi `ALLOW` cho token/grant sau thời điểm hiệu lực thu hồi | Điều tra độ trễ cache, JWT tự xác minh hoặc lỗi sync |
| **Refresh token reuse** | AS thấy refresh token rotation token cũ được trình lại | Xác minh cạnh tranh request hợp lệ hay token bị sao chép |
| **Truy cập ngoài mẫu** | Scope nhạy cảm được dùng đột ngột trên API/tenant hiếm gặp | Phân tích thời gian, danh tính thiết bị/service, context; không kết luận chỉ từ một tín hiệu |
| **Token nghi bị đánh cắp** | Token reference có tần suất, nguồn mạng hoặc hành vi bất thường | Điều tra chiếm quyền, giới hạn/thắt chặt token, cân nhắc sender-constrained |
| **Thay đổi policy gây mất quyền** | `DENY` tăng sau deployment policy version mới | So sánh với thay đổi policy và contract API |

**Không kết luận mọi request sau logout là tấn công.** Một JWT bearer còn hạn có thể chưa bị thu hồi tại API; có thể có request in-flight hoặc cache introspection. Cần xác định chính xác **thời điểm thu hồi hiệu lực**, cơ chế xác minh và giới hạn trễ được chấp nhận.

### Truy vấn phân tích scope đã cấp nhưng chưa dùng

Mô hình SQL khái niệm (cần điều chỉnh theo kho dữ liệu và cách lưu scopes):

~~~sql
-- Ví dụ giả định có bảng scope_grants và api_scope_usage đã được ETL
-- từ các audit events đáng tin cậy, gồm từng cặp grant_ref + scope.
SELECT
    g.client_id,
    g.scope_name,
    COUNT(DISTINCT g.grant_ref) AS active_grants_without_usage
FROM scope_grants AS g
LEFT JOIN api_scope_usage AS u
    ON u.grant_ref = g.grant_ref
   AND u.scope_name = g.scope_name
   AND u.used_at >= TIMESTAMP '2026-10-01 00:00:00'
   AND u.used_at <  TIMESTAMP '2026-11-01 00:00:00'
WHERE g.is_active = TRUE
  AND g.granted_at < TIMESTAMP '2026-11-01 00:00:00'
  AND u.grant_ref IS NULL
GROUP BY g.client_id, g.scope_name
ORDER BY active_grants_without_usage DESC;
~~~

Kết quả **không chứng minh scope vô ích**: có thể dùng theo mùa vụ, request bị chặn ở tầng gateway, hoặc audit chưa bao phủ hết các API. Cần xác minh **coverage** trước khi thu hồi tự động.

### Phát hiện truy cập được phép sau thu hồi

~~~text
For each api.authorization.decided where outcome = ALLOW:
    find trusted revocation event for same grant/token reference
    if revocation effective_at < API decision occurred_at:
        account for clock skew, in-flight request and cache policy
        if beyond permitted propagation window:
            alert with linked grant, client, audience and policy versions
~~~

Đây là **logic phát hiện**, không phải quy tắc có thể tự chặn mọi request. Chặn thực tế phải được thực thi tại API bằng cơ chế trạng thái/thu hồi phù hợp. Trước khi cảnh báo, phải chắc chắn các tham chiếu tương quan đáng tin và đồng hồ được đồng bộ.

## 11. Bảo vệ audit log khỏi rò rỉ và sửa đổi

Hệ thống audit có giá trị điều tra chỉ khi bản ghi đáng tin cậy và người không có quyền khó xóa/sửa.

### Thu thập và chuyển tải

1. Log ở **các điểm quyết định được tin cậy**: AS, gateway xác minh token, middleware authorization và dịch vụ quyết định object policy.
2. Sử dụng **schema có version**, field được allowlist, enum reason code và validation.
3. Gửi log qua kênh có TLS và xác thực service; hạn chế ai có quyền giả nguồn gửi log.
4. Có hàng đợi/buffer bền vững, retry, phát hiện mất/nhân đôi event bằng `event_id` và kiểm soát backpressure.
5. Dùng `occurred_at` và `observed_at` để nhận ra trễ thu nhận; monitor độ lệch đồng hồ.
6. Thiết lập cảnh báo khi audit sink ngừng ghi, throughput giảm bất thường hoặc xuất hiện lỗ hổng chuỗi sự kiện.

### Lưu trữ, quyền truy cập và tính toàn vẹn

- Sử dụng storage hạn chế sửa/xóa (append-only/immutable hoặc WORM tùy yêu cầu), tách quyền đọc/ghi/quản trị và có quy trình xuất chứng cứ.
- Có thể dùng cơ chế ký/hàm băm chuỗi/tamper-evident có quản lý khóa để phát hiện sửa đổi; **đừng tự xây mật mã** khi giải pháp lưu trữ có chứng nhận hoặc cơ chế đáng tin đã tồn tại.
- Áp dụng encryption at rest, giới hạn người truy cập theo công việc, kiểm tra và **audit mọi lần truy cập vào audit log**.
- Xác định retention theo luật, nhu cầu điều tra, hợp đồng và chính sách tổ chức; không tự đặt một số ngày “chuẩn chung”.
- Hết retention phải xóa/hủy đúng quy trình; với dữ liệu cần legal hold, áp dụng quy tắc lưu giữ đặc biệt có kiểm soát.
- Không dùng audit log như một cơ chế xác thực lại. Dữ liệu có thể thiếu hoặc trễ, không thích hợp để quyết định cấp quyền tức thời thay cho AS/RS.

**Privacy by design:** dữ liệu audit như actor, tenant, thời gian, IP hoặc chuỗi hành vi có thể giúp tái định danh. Cần giảm tối thiểu, phân tách danh tính khỏi dữ liệu sự kiện nếu khả thi, quy định ai có thể thực hiện re-identification, và có chính sách bảo vệ dữ liệu cá nhân.

## 12. Java: phát sự kiện audit sau quyết định tin cậy

Ví dụ Java 17 minh họa nguyên tắc: **không trích scope từ JWT chưa xác minh**, không log raw token, phát event khi chính sách đã trả quyết định.

~~~java
import java.time.Instant;
import java.util.Set;

public final class ScopeAuditExample {

    // Đối tượng này phải được tạo bởi middleware xác minh token tin cậy.
    public record VerifiedAccess(
            String issuer,
            String clientId,
            String tokenReference,
            Set<String> grantedScopes
    ) {}

    public record ScopeAuditEvent(
            String eventType,
            Instant occurredAt,
            String correlationId,
            String clientId,
            String tokenReference,
            String routeTemplate,
            Set<String> requiredScopes,
            Set<String> verifiedScopes,
            String outcome,
            String reasonCode
    ) {}

    public interface AuditSink {
        void emit(ScopeAuditEvent event);
    }

    public static boolean authorizeScope(
            VerifiedAccess verified,
            Set<String> requiredScopes,
            String correlationId,
            String routeTemplate,
            AuditSink auditSink
    ) {
        // Chỉ kiểm tra scope; object policy/tenant vẫn cần được kiểm tra riêng.
        boolean hasScopes = verified.grantedScopes()
                .containsAll(requiredScopes);

        auditSink.emit(new ScopeAuditEvent(
                "api.scope.decided",
                Instant.now(),
                correlationId,
                verified.clientId(),
                verified.tokenReference(),
                routeTemplate,
                Set.copyOf(requiredScopes),
                Set.copyOf(verified.grantedScopes()),
                hasScopes ? "ALLOW" : "DENY",
                hasScopes ? "SCOPE_CHECK_PASSED" : "INSUFFICIENT_SCOPE"
        ));

        return hasScopes;
    }
}
~~~

**Giới hạn rõ ràng của đoạn code:**

- `VerifiedAccess` là hợp đồng minh họa; trong hệ thống thực tế nó phải được tạo **sau khi** kiểm tra signature/issuer/audience/thời hạn hoặc introspection, không tạo từ payload do client gửi.
- `tokenReference` là mã pseudonym đáng tin, **không phải** bearer token/JWT nguyên văn hoặc refresh token.
- Method này chỉ ghi **scope decision**, chưa phải authorization cuối cùng. Nếu object policy tiếp tục từ chối, phải ghi event quyết định cuối với reason phù hợp; không coi `SCOPE_CHECK_PASSED` là `api.authorization.decided ALLOW`.
- `AuditSink` cần triển khai queue/retry/đảm bảo delivery, privacy và quy tắc xử lý khi không thể ghi; gọi `emit` thành công về mặt method không đồng nghĩa bản ghi đã bền vững.
- `correlationId` và `routeTemplate` phải được cấp/chuẩn hóa bởi thành phần tin cậy, không đưa raw URL, header hoặc dữ liệu người dùng chưa xử lý vào log.

Trong framework thực tế, nên đặt audit ở **điểm quyết định chung** (middleware authorization, policy enforcement point, authorization endpoint, token endpoint) thay vì chèn log rời rạc ở mọi controller dẫn tới bỏ sót hoặc sự kiện mâu thuẫn.

## 13. Case study: scope bị cấp rộng và dấu hiệu lạm dụng

Ứng dụng `reporting-client` cần đọc đơn hàng định kỳ. Hai API scope của Orders là `orders:read` và `orders:export`.

### Mốc sự kiện giả định

| UTC | Bằng chứng | Kết quả và ý nghĩa |
|---|---|---|
| 10:00 | `authz.request.received` xin `orders:read orders:export` | Chỉ là yêu cầu, chưa chứng minh đã được cấp |
| 10:01 | `authz.grant.decided` cấp **`orders:read`** | Policy giảm quyền; cần ghi cả requested/granted |
| 10:02 | `token.issued` token A, `aud=orders-api`, scope `orders:read`, exp 10:12 | Phát hành thành công; không lưu raw token |
| 10:04 | `api.authorization.decided` GET `/orders/{id}` = ALLOW | API xác minh token, scope và quyền trên đơn |
| 10:05 | `api.authorization.decided` POST `/orders/export` = DENY / `INSUFFICIENT_SCOPE` | Client cố dùng scope không được cấp |
| 10:07 | Nhiều DENY tương tự | Điều tra lỗi UI/client, scope probing hoặc misuse |
| 10:08 | User/admin thu hồi grant | Ghi `authz.grant.revoked` với effective time |
| 10:09 | API nhận token A | Phải kiểm tra chính sách thu hồi hoặc giải thích được lý do còn/chưa còn được chấp nhận |

**Cách điều tra theo từng lớp:**

1. Xem `authz.grant.decided`: scope `orders:export` chỉ được **xin**, không được **cấp**. Không gọi đây là tình huống AS đã “cấp quyền export”.
2. Đối chiếu `token.issued`: token A có audience Orders API và scope thực tế `orders:read`.
3. Đối chiếu log API: GET được phép nếu user có quyền object; POST export bị từ chối vì `INSUFFICIENT_SCOPE`. Hai kết quả này thống nhất với grant.
4. Khi nhiều request export xuất hiện, kiểm tra phiên bản client, lần triển khai gần đây, loại grant, policy và nguồn request trong phạm vi được phép thu thập dữ liệu.
5. Sau thu hồi, kiểm tra API có introspection, denylist, phiên server hoặc chỉ verify JWT tại chỗ; xác định time window chấp nhận được trước khi phân loại là lỗi bảo mật.
6. Nếu nghi token bị sao chép, phản ứng bằng quy trình sự cố: hạn chế client/grant, thu hồi refresh token, dùng cơ chế chặn token khi cần, bảo vệ khóa và giữ bằng chứng bất biến.

### Chỉ số nên theo dõi

| Chỉ số | Mục đích | Cảnh báo khi diễn giải |
|---|---|---|
| **Grant approval rate** | Tỷ lệ yêu cầu được chấp thuận trong nhóm request hợp lệ | Phân biệt policy deny, user deny và lỗi kỹ thuật |
| **Scope reduction rate** | Tỷ lệ grant cấp ít scope hơn đã xin | Có thể là least privilege hoạt động tốt, không mặc nhiên lỗi |
| **Scope usage coverage** | Tỷ lệ scope được cấp có API usage tương ứng trong cửa sổ quan sát | Cần audit coverage, đủ thời gian/mùa vụ |
| **Insufficient-scope deny rate** | Tỷ lệ API requests hợp lệ bị từ chối vì thiếu scope | Đừng gộp với token sai hoặc object policy deny |
| **Unauthorized object deny rate** | Phát hiện quyền tài nguyên ngoài scope | Không dùng như bằng chứng scope cấp sai |
| **Revocation propagation delay** | Khoảng từ revocation effective đến khi các verifier từ chối | Phụ thuộc kiến trúc JWT/opaque/cache và clock skew |
| **Refresh reuse alerts** | Chỉ dấu token theft hoặc race refresh | Điều tra client concurrency trước kết luận xâm nhập |
| **Audit ingestion lag / gap rate** | Độ tin cậy của bằng chứng audit | Nếu mất log, các chỉ số sử dụng scope sẽ thiếu tin cậy |

Với mọi KPI, định nghĩa **tử số, mẫu số, nguồn dữ liệu và cửa sổ thời gian** rõ ràng. Nếu chỉ log các request bị từ chối, không thể dùng dữ liệu đó để đo chính xác toàn bộ tỷ lệ sử dụng scope. Nếu một API chưa triển khai audit, không được kết luận scope ít dùng chỉ vì không có bản ghi.

## 14. Kịch bản kiểm thử audit trong CI và vận hành

Tạo test cases không chỉ kiểm tra HTTP response, mà còn kiểm tra **sự kiện audit đúng, đầy đủ và không chứa bí mật**.

| Kịch bản | Kết quả bảo mật mong đợi | Sự kiện audit cần quan sát |
|---|---|---|
| AS nhận request xin `read export` nhưng chỉ cho `read` | Client chỉ nhận quyền `read` | `authz.grant.decided` lưu requested/granted khác nhau |
| User từ chối consent | Không cấp code/token cho yêu cầu đó | `DENY` / `USER_DENIED`; không có `token.issued` tương ứng |
| Client dùng token `read` gọi endpoint export | API từ chối `403`/`insufficient_scope` | `api.authorization.decided DENY`, required scope export |
| JWT sai chữ ký hoặc issuer | API từ chối `401` | `api.token.validation DENY` / `INVALID_TOKEN` |
| JWT hợp lệ nhưng sai `aud` | API từ chối | `INVALID_AUDIENCE`, không ghi ALLOW |
| Token có scope đọc nhưng user không sở hữu order | API từ chối theo object policy | `OBJECT_POLICY_DENIED`, không ghi thiếu scope sai |
| Refresh token bị dùng lại sau rotation | AS xử lý theo policy, có thể thu hồi family | `token.refresh.decided DENY` và sự kiện cảnh báo |
| Grant bị thu hồi | Không cấp token mới theo grant; API đáp ứng chính sách thu hồi | `authz.grant.revoked`; log API giúp kiểm tra độ trễ |
| Audit sink bị lỗi | Hành vi theo fail-safe đã định nghĩa | Telemetry/cảnh báo mất audit; không im lặng |
| Client gửi token/secret trong header | Hệ thống không ghi giá trị nhạy cảm | Test kiểm tra log không chứa raw `Authorization`/token |

**Test âm tính đặc biệt quan trọng:** người dùng thêm ký tự xuống dòng vào một field, gửi URL có token trong query, client tự khai `scope=admin` trong body, hoặc dùng `x-request-id` giả. Audit pipeline phải escape/canonicalize và **không biến dữ liệu untrusted thành sự kiện quyền được cấp**.

Trong môi trường staging, có thể kiểm tra luồng cấp quyền và sử dụng scope bằng token giả an toàn (không phải credential production), rồi truy vấn các event liên quan bằng `correlation_id` để xác nhận đầy đủ các bước.

## 15. Checklist triển khai audit scope

1. **Định nghĩa mục tiêu audit:** cần giải trình việc cấp quyền, sử dụng tại API, phát hiện lạm quyền hay tuân thủ nghĩa vụ nào?
2. **Chốt taxonomy và schema có version:** `grant.decided`, `token.issued`, `api.authorization.decided`, `grant.revoked` và lý do chuẩn hóa.
3. **Ghi cả requested và granted scopes:** không coi scope đã xin là quyền đã cấp.
4. **Ghi nguồn quyết định đáng tin:** actor type, client, issuer, policy version và thời điểm; không để client tự khai authoritative role/scope.
5. **Phân biệt grant/issuance/usage:** token đã phát hành chưa chắc được dùng; API request có thể bị từ chối dù token có scope.
6. **Liên kết có kiểm soát:** grant ref, token ref, correlation ID, audience và token family ref; không log raw token/secret.
7. **Audit tại AS và RS:** bảo đảm không chỉ log bên cấp hoặc chỉ log bên sử dụng.
8. **Ghi quyết định scope và object policy chính xác:** phân biệt `INSUFFICIENT_SCOPE`, `INVALID_AUDIENCE` và `OBJECT_POLICY_DENIED`.
9. **Bảo vệ pipeline:** xác thực nguồn, TLS, event ID, retry/queue, đồng bộ thời gian, giám sát mất log, append-only/tamper evidence.
10. **Bảo vệ riêng tư:** tối thiểu hóa PII, pseudonymize, hạn chế truy cập và retention theo chính sách.
11. **Theo dõi vòng đời:** refresh/rotation, revoke, thay đổi scope, JWT/opaque, cache introspection và độ trễ thu hồi.
12. **Xây cảnh báo có kiểm chứng:** overgrant, scope probing, sai audience, token reuse, post-revoke allow; tránh kết luận từ dữ liệu thiếu.
13. **Kiểm thử bảo mật và kiểm thử log:** không rò token, không log injection, có đủ event ở cả allow/deny, không có sự kiện “đã cấp” giả.
14. **Rà soát định kỳ:** điều chỉnh scope quá rộng, khắc phục audit gap và kiểm tra quyền truy cập vào log.

**Điểm cần nhớ:** audit scope có ý nghĩa khi nối được **quyền được yêu cầu → quyết định cấp quyền → token được phát hành → API sử dụng thực tế → thu hồi hoặc hết hạn** bằng bằng chứng từ những thành phần tin cậy. Phải giữ được khả năng phân biệt scope, audience, quyền object/tenant và trạng thái token, đồng thời không biến chính audit log thành nơi rò rỉ access token hay dữ liệu riêng tư.

### Tài liệu chuẩn và hướng dẫn tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scope, authorization grant, client và token issuance.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bảo vệ bearer token, `invalid_token` và `insufficient_scope`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái token, audience và scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token và các claim liên quan.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): các thực hành bảo mật OAuth hiện đại.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thiết kế logging bảo mật, bảo vệ dữ liệu và tính toàn vẹn.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): các rủi ro quyền đối tượng, xác thực và cấu hình API cần theo dõi.
