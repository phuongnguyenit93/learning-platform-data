# Audit access token usage

Trong hệ thống OAuth 2.0 và OpenID Connect (OIDC), **audit access token usage** là việc ghi nhận có kiểm soát cách access token được phát hành, trình bày và sử dụng để truy cập tài nguyên. Audit trail giúp trả lời các câu hỏi: token nào đã được dùng, bởi client hoặc subject nào, tại service nào, để thực hiện hành động gì, vào thời điểm nào, quyết định authorization ra sao và kết quả cuối cùng là gì.

Access token là credential dạng bearer hoặc credential theo cơ chế sender-constrained. Vì vậy, audit phải cung cấp đủ bằng chứng để điều tra việc sử dụng token nhưng không tạo thêm nơi lưu token có thể bị đánh cắp. Hệ thống cần ghi metadata đã xác minh và định danh token theo cách an toàn; không ghi nguyên văn access token, refresh token hoặc header `Authorization` vào log.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, audit usage nối các khâu phát hành, xác minh claims, scope, audience, lưu trữ và thu hồi token với hoạt động thực tế tại resource server. Nó cũng hỗ trợ kiểm soát truy cập, điều tra sự cố, chứng minh việc thực thi chính sách và đáp ứng yêu cầu kiểm toán theo phạm vi pháp lý áp dụng.

## 1. Audit access token usage là gì?

Audit access token usage là một tập sự kiện bảo mật có cấu trúc, ghi lại các lần token được cấp và sử dụng cùng những quyết định liên quan. Một bản ghi audit tốt cho biết:

- **Ai hoặc thành phần nào:** user subject, service account, OAuth client và actor đại diện nếu có.
- **Token thuộc ngữ cảnh nào:** issuer, token type, audience/resource và scope đã được xác minh.
- **Khi nào:** thời điểm sự kiện xảy ra và thời điểm hệ thống nhận được sự kiện.
- **Ở đâu:** service, route hoặc loại tài nguyên được truy cập.
- **Làm gì:** hành động nghiệp vụ hoặc nhóm thao tác được yêu cầu.
- **Quyết định nào:** token hợp lệ hay không, policy cho phép hay từ chối, lý do chuẩn hóa.
- **Kết quả gì:** request bị từ chối, thao tác hoàn tất, thất bại hoặc chưa xác định.
- **Liên kết điều tra:** event ID, request ID, trace ID và phiên bản policy.

Audit trail có thể bao gồm nhiều loại sự kiện:

| Sự kiện | Nơi phát sinh | Mục đích |
|---|---|---|
| `access_token.issued` | Authorization server | Ghi nhận token được cấp cho client/subject, audience và scope nào. |
| `access_token.presented` | API gateway/resource server | Ghi nhận token được trình bày trong request. |
| `access_token.validation_failed` | Authentication middleware | Ghi nhận token bị từ chối do chữ ký, issuer, audience, thời hạn hoặc trạng thái. |
| `access_token.authorization_denied` | Authorization layer | Ghi nhận token hợp lệ nhưng không đủ quyền hoặc bị policy từ chối. |
| `access_token.resource_accessed` | Resource server/business service | Ghi nhận hành động truy cập tài nguyên và kết quả nghiệp vụ. |
| `access_token.introspected` | Authorization server/introspection service | Ghi nhận việc kiểm tra trạng thái opaque token hoặc token theo policy. |
| `access_token.revoked` | Authorization server | Ghi nhận token hoặc grant bị thu hồi. |
| `access_token.exchange_issued` | Authorization server | Ghi nhận token mới được phát hành qua Token Exchange và quan hệ delegation. |

Không phải hệ thống nào cũng cần phát mọi loại event. Hãy xác định nguồn sự thật và yêu cầu audit trước khi chọn phạm vi ghi nhận. Ví dụ, resource server là nguồn phù hợp để ghi việc token được dùng truy cập API; authorization server là nguồn phù hợp để ghi việc token được phát hành hoặc thu hồi.

## 2. Phân biệt audit log, application log, metric và trace

Các loại telemetry phục vụ những câu hỏi khác nhau:

| Loại dữ liệu | Câu hỏi chính | Đặc điểm |
|---|---|---|
| Audit log | Ai đã truy cập hoặc thực hiện hành động nào, theo quyết định nào? | Có cấu trúc, có nguồn phát, cần tính toàn vẹn, retention và khả năng truy xuất. |
| Application log | Ứng dụng đã xử lý và gặp lỗi gì? | Hữu ích cho debug; có thể chứa thông tin kỹ thuật chi tiết nhưng phải redact bí mật. |
| Metric | Sự kiện xảy ra bao nhiêu lần và xu hướng ra sao? | Tổng hợp theo thời gian, cardinality thấp, không lưu lịch sử từng token/request. |
| Trace | Một request đi qua những service nào và mất bao lâu? | Liên kết các span trong một luồng xử lý; không phải bằng chứng đầy đủ cho mọi lần truy cập. |

Không dùng metric hoặc trace thay cho audit log nếu yêu cầu kiểm toán cần biết từng lần truy cập. Metric có thể tổng hợp 1.000 request thành một time series; trace có thể được sampling. Audit cần có chính sách coverage riêng và không được âm thầm sampling các sự kiện bắt buộc phải lưu.

Một request có thể tạo ra cả audit event, metric increment và trace span. Các bản ghi này nên liên kết qua request/trace ID, nhưng mỗi loại dữ liệu cần giữ đúng mục đích và quyền truy cập của nó.

## 3. Những trường thông tin nên có trong audit event

Một schema audit cần có phiên bản để có thể thay đổi theo thời gian mà không làm mất khả năng đọc dữ liệu cũ.

### Nhóm định danh sự kiện

- `event_id`: ID duy nhất để chống xử lý trùng và tra cứu.
- `event_type`: loại sự kiện như `access_token.presented` hoặc `access_token.authorization_denied`.
- `schema_version`: phiên bản schema.
- `event_time`: thời điểm sự kiện xảy ra theo UTC.
- `observed_time`: thời điểm collector hoặc audit store nhận sự kiện.
- `producer`: service phát sinh event.
- `environment`: dev, staging hoặc production.

### Nhóm principal và client

- `issuer`: authorization server đã phát hành token, nếu đã xác minh.
- `client_id`: OAuth client được xác định từ token đã xác minh hoặc grant đáng tin cậy.
- `subject_ref`: tham chiếu subject đã được pseudonymize theo chính sách.
- `actor_ref`: actor/service đại diện nếu có delegation hoặc on-behalf-of.
- `tenant_ref`: tenant context đã được xác minh, chỉ ghi khi cần và có kiểm soát truy cập.

`sub` không phải lúc nào cũng là con người. Với Client Credentials Grant, subject có thể là service account hoặc client principal. Trong Token Exchange, subject và actor có thể khác nhau. Audit schema cần phân biệt hai vai trò thay vì luôn gọi `sub` là user.

### Nhóm token và authorization context

- `token_type`: JWT access token, opaque access token hoặc loại đã chuẩn hóa.
- `token_ref`: fingerprint/pseudonymous reference của token, không phải token gốc.
- `audience`: resource hoặc API đích đã được xác minh.
- `scope`: tập scope có liên quan đến quyết định, theo chính sách tối thiểu cần lưu.
- `issued_at` và `expires_at`: thời điểm token nếu đã xác minh và cần cho điều tra.
- `token_status`: valid, expired, revoked, inactive hoặc invalid theo kết quả kiểm tra.
- `validation_reason`: mã lý do chuẩn hóa nếu validation thất bại.

Với JWT, chỉ dùng claim sau khi chữ ký và các điều kiện xác minh cần thiết đã thành công. Với opaque token, lấy metadata từ introspection hoặc token registry đáng tin cậy. Không giải mã JWT chưa xác minh rồi ghi `sub`, `client_id`, `aud` hoặc scope từ payload không tin cậy vào audit như dữ kiện đúng.

### Nhóm request và tài nguyên

- `service`: resource server hoặc gateway xử lý request.
- `http_method`: method đã chuẩn hóa.
- `route`: route template, ví dụ `/api/accounts/{accountId}`.
- `resource_type`: loại tài nguyên như account, invoice hoặc inventory item.
- `action`: hành động nghiệp vụ như read, create, update, delete hoặc export.
- `resource_ref`: tham chiếu tài nguyên đã được giảm thiểu/pseudonymize nếu cần.
- `request_id` và `trace_id`: liên kết với log/trace.
- `source_context`: thông tin nguồn ở mức cần thiết như network zone hoặc client application; cần cân nhắc dữ liệu cá nhân.

### Nhóm quyết định và kết quả

- `authentication_result`: valid, invalid hoặc not_evaluated.
- `authorization_decision`: allow hoặc deny.
- `decision_reason`: reason code hữu hạn, ví dụ `INSUFFICIENT_SCOPE`, `TENANT_INACTIVE`.
- `policy_id` và `policy_version`: policy đã tạo ra quyết định.
- `http_status`: status cuối cùng của API nếu có.
- `operation_result`: succeeded, failed hoặc unknown.
- `error_class`: nhóm lỗi đã chuẩn hóa, không phải exception message tùy ý.

Không nên gộp `authorization_decision=allow` với `operation_result=succeeded`. Một request có thể được cho phép nhưng database timeout khiến thao tác thất bại. Audit nên phân biệt quyết định quyền với kết quả thực thi.

## 4. Ví dụ audit event

Ví dụ một request đọc tài nguyên được xác thực và cho phép:

```json
{
  "event_id": "evt-01J8Y6M2K7",
  "event_type": "access_token.resource_accessed",
  "schema_version": "1.0",
  "event_time": "2026-11-23T10:30:12.481Z",
  "observed_time": "2026-11-23T10:30:12.493Z",
  "producer": "accounts-api",
  "environment": "production",
  "identity": {
    "issuer": "https://auth.example.com",
    "client_id": "web-portal",
    "subject_ref": "subref:v3:7c9a...",
    "tenant_ref": "tenantref:v2:19bd..."
  },
  "token": {
    "type": "jwt_access_token",
    "token_ref": "hmac-sha256:v2:8f3d...",
    "audience": ["accounts-api"],
    "scope": ["accounts.read"],
    "issued_at": "2026-11-23T10:25:00Z",
    "expires_at": "2026-11-23T10:35:00Z",
    "status": "valid"
  },
  "request": {
    "request_id": "req-7a19",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "service": "accounts-api",
    "method": "GET",
    "route": "/api/accounts/{accountId}",
    "resource_type": "account",
    "action": "read"
  },
  "decision": {
    "authentication_result": "valid",
    "authorization_decision": "allow",
    "decision_reason": "SCOPE_AND_POLICY_MATCH",
    "policy_id": "account-read-policy",
    "policy_version": "17"
  },
  "result": {
    "http_status": 200,
    "operation_result": "succeeded"
  }
}
```

Các ID, fingerprint và timestamp trên chỉ là dữ liệu minh họa. Trong thực tế, schema có thể phẳng hoặc lồng tùy nền tảng log; điều quan trọng là tên trường có ý nghĩa ổn định và dữ liệu được giảm thiểu.

Ví dụ một request bị từ chối do token thiếu scope:

```json
{
  "event_id": "evt-01J8Y6N8A1",
  "event_type": "access_token.authorization_denied",
  "schema_version": "1.0",
  "event_time": "2026-11-23T10:31:02.105Z",
  "producer": "payments-api",
  "identity": {
    "issuer": "https://auth.example.com",
    "client_id": "reporting-client",
    "subject_ref": "subref:v3:7c9a..."
  },
  "token": {
    "type": "opaque_access_token",
    "token_ref": "hmac-sha256:v2:51a0...",
    "audience": ["payments-api"],
    "scope": ["payments.read"],
    "status": "valid"
  },
  "request": {
    "service": "payments-api",
    "method": "POST",
    "route": "/api/payments/{paymentId}/refund",
    "resource_type": "payment",
    "action": "refund"
  },
  "decision": {
    "authentication_result": "valid",
    "authorization_decision": "deny",
    "decision_reason": "INSUFFICIENT_SCOPE",
    "required_scope": ["payments.refund"]
  },
  "result": {
    "http_status": 403,
    "operation_result": "not_executed"
  }
}
```

Với token không hợp lệ, không ghi claims chưa xác minh như thể chúng là danh tính thật. Chỉ ghi kết quả validation và reason code. Nếu cần liên kết các lần trình bày cùng một token không hợp lệ, có thể tính fingerprint HMAC từ chuỗi nhận được mà không lưu chuỗi gốc, theo chính sách đã phê duyệt.

## 5. Không ghi access token và bí mật vào audit log

Access token là bearer credential: ai có token có thể sử dụng nó trong phạm vi quyền và thời hạn của token. Ghi nguyên token vào log biến hệ thống logging thành một kho credential thứ hai, thường có nhiều người và hệ thống truy cập hơn resource server.

Không ghi các giá trị sau:

- Header `Authorization: Bearer ...` hoặc token trong cookie.
- Raw JWT, opaque access token hoặc refresh token.
- Authorization code, PKCE verifier hoặc client assertion.
- Client secret, private key, private certificate material hoặc session secret.
- Toàn bộ request/response body nếu có thể chứa credential hoặc dữ liệu cá nhân.
- Exception message chứa URL, header hoặc body chưa redact.

Không dùng cách che token bằng cách chỉ ghi vài ký tự cuối nếu giá trị đó vẫn có thể bị dùng để nhận diện hoặc ghép nối ngoài ý muốn. Cần một cơ chế tham chiếu được thiết kế rõ ràng.

### Token fingerprint bằng HMAC

Nếu cần biết nhiều request có sử dụng cùng một token hay không, có thể tính fingerprint bằng HMAC-SHA-256 với một khóa riêng dành cho audit:

```text
token_ref = HMAC-SHA-256(audit_fingerprint_key, raw_access_token)
```

Chỉ lưu fingerprint đã rút gọn theo định dạng được thống nhất, kèm phiên bản khóa như `hmac-sha256:v2`. Không lưu `raw_access_token` hoặc khóa HMAC trong audit event.

HMAC có các đặc điểm hữu ích:

- Cùng token và cùng phiên bản khóa tạo cùng fingerprint để liên kết sự kiện.
- Người chỉ có audit log không thể tự tính fingerprint cho một token phỏng đoán nếu không có khóa HMAC.
- Có thể xoay khóa và phiên bản fingerprint theo kế hoạch.

Fingerprint vẫn là dữ liệu có thể liên kết hoạt động của một credential và cần được bảo vệ như dữ liệu pseudonymous. Giới hạn người có thể truy vấn theo fingerprint, thời gian lưu và mục đích sử dụng. Không dùng một khóa HMAC chung cho nhiều môi trường hoặc nhiều mục đích không liên quan.

Với JWT có `jti`, có thể lưu một tham chiếu đã pseudonymize nếu hệ thống cần tra cứu theo ID token. `jti` không phải bí mật thay thế token, nhưng vẫn có thể liên kết hoạt động và không nên công khai không cần thiết. Với opaque token không có `jti` đọc được, fingerprint HMAC là một lựa chọn nhất quán.

## 6. Xác minh claims trước khi ghi audit

Audit event phải phân biệt dữ liệu đã xác minh với dữ liệu do caller cung cấp.

Với JWT access token, trước khi ghi claims vào trường tin cậy, resource server cần thực hiện các kiểm tra phù hợp với token profile:

1. Kiểm tra cấu trúc token và thuật toán ký nằm trong allowlist.
2. Xác minh chữ ký bằng public key tin cậy từ issuer/JWKS đã cấu hình.
3. Kiểm tra `iss` đúng issuer được tin cậy.
4. Kiểm tra `aud` chứa resource server hoặc audience được phép.
5. Kiểm tra `exp`, `nbf` và các giới hạn thời gian cần thiết.
6. Kiểm tra token type/profile, tránh dùng nhầm ID token làm access token.
7. Đọc `scope`, `client_id`, `sub` và các claim cần thiết sau khi token đã hợp lệ.
8. Áp dụng authorization policy cho resource và action cụ thể.

Với opaque token, resource server lấy metadata từ introspection response được xác thực và kiểm tra `active`. Nếu introspection timeout hoặc response sai định dạng, ghi nhận dependency failure; không tự kết luận token `invalid` nếu chưa có kết quả xác minh.

Không dùng tenant ID, user ID hoặc role lấy từ header/query parameter của client để ghi vào trường identity đã xác minh. Nếu cần ghi giá trị caller yêu cầu để điều tra, đặt tên riêng như `requested_tenant_ref` và đánh dấu rõ là untrusted input.

## 7. Ghi nhận các giai đoạn trong vòng đời token

Một audit trail đầy đủ có thể theo dõi token từ khi cấp đến khi không còn được chấp nhận.

### Phát hành token

Authorization server có thể ghi `access_token.issued` với:

- issuer và client đã xác thực;
- subject hoặc service principal theo grant;
- audience/resource và scope được cấp;
- token type, `issued_at`, `expires_at`;
- grant type và request/correlation ID;
- kết quả policy, consent hoặc delegation có liên quan.

Không ghi raw token response. Nếu token được cấp qua Token Exchange, ghi thêm subject/actor relationship và audience/scope mới theo mức cần thiết để điều tra delegation.

### Token được trình bày tại resource server

Resource server ghi nhận `access_token.presented` hoặc event kết quả tương đương. Event nên phản ánh:

- token có được xác minh thành công không;
- client/subject đã xác minh là ai;
- token có đúng audience không;
- request nhắm tới route, resource type và action nào;
- authorization decision là allow hay deny;
- reason code nếu bị từ chối.

Nếu ứng dụng ghi một event `presented` và event `resource_accessed`, cần có quy ước để phân biệt việc nhận token với việc hành động nghiệp vụ thực sự được thực hiện. Không được hiểu event presented là dữ liệu đã được đọc hoặc thay đổi thành công.

### Introspection và revocation

Với opaque token hoặc kiến trúc có introspection, có thể ghi sự kiện kiểm tra trạng thái và kết quả `active`. Nếu token bị thu hồi, authorization server ghi event revocation với token reference, grant/client context, lý do chuẩn hóa và thời điểm.

Không phát sinh event revocation giả chỉ vì token hết hạn tự nhiên. Hết hạn và thu hồi trước hạn là hai sự kiện khác nhau.

### Refresh và Token Exchange

Refresh token không phải access token. Nếu audit cần theo dõi refresh, ghi event riêng như `refresh_token.used`, `refresh_token.rotated` hoặc `refresh_token.reuse_detected`; không ghi refresh token gốc.

Token Exchange tạo token mới với audience/scope và quan hệ delegation có thể khác token nguồn. Audit cần giữ liên kết giữa subject token context, actor và token mới bằng reference an toàn, đồng thời ghi rõ token mới được cấp cho resource nào.

## 8. Theo dõi quyết định truy cập và kết quả nghiệp vụ

Một bản ghi audit hữu ích cần cho biết hành động có thực sự xảy ra hay không. Hãy phân biệt ít nhất ba lớp:

| Lớp | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Authentication | JWT signature valid, token active | Credential có được chấp nhận không? |
| Authorization | Scope và policy cho phép read | Principal có được phép thực hiện hành động không? |
| Resource operation | Database trả bản ghi thành công | Hành động thực tế hoàn tất hay thất bại? |

Ví dụ:

- Token hợp lệ, scope đúng, nhưng database timeout: authentication valid, authorization allow, operation failed.
- Token hợp lệ nhưng thiếu scope: authentication valid, authorization deny, operation not executed.
- Token sai chữ ký: authentication invalid, authorization not evaluated, operation not executed.

Nếu API trả `200` nhưng business operation chỉ được đưa vào queue, audit nên ghi trạng thái `accepted` hoặc `queued` thay vì `completed`. Khi worker hoàn tất, event riêng ghi kết quả cuối cùng. Cách này tránh audit trail tuyên bố thao tác đã xong khi nó chỉ mới được tiếp nhận.

## 9. Correlation giữa audit, trace và request

Một incident có thể đi qua API gateway, nhiều resource server và service downstream. Để nối các sự kiện, cần correlation ID ổn định nhưng không dùng credential làm ID.

Các trường thường hữu ích:

- `event_id`: định danh duy nhất cho từng audit event.
- `request_id`: định danh request tại một service hoặc gateway.
- `trace_id`: liên kết distributed trace.
- `correlation_id`: liên kết một luồng nghiệp vụ qua nhiều request.
- `parent_event_id`: liên kết event phát sinh từ event trước, nếu có.
- `token_ref`: fingerprint pseudonymous để nối các lần dùng cùng token.
- `grant_ref`: tham chiếu grant hoặc authorization transaction nếu cần.

Không dùng access token, refresh token, `Authorization` header hoặc client secret làm correlation ID. Không đưa `request_id`, `trace_id` hoặc `token_ref` thành label metric có cardinality cao.

### Đồng bộ thời gian

Audit cần thời gian đủ chính xác để dựng lại thứ tự sự kiện. Service nên đồng bộ clock bằng cơ chế thời gian tin cậy, lưu timestamp ở UTC và giữ cả:

- `event_time`: thời điểm nguồn phát sinh sự kiện;
- `observed_time`: thời điểm audit collector nhận event.

Chênh lệch giữa hai thời điểm giúp nhận biết queue delay hoặc collector chậm. Khi các service có clock skew, không nên chỉ dựa vào timestamp để suy luận thứ tự nhân quả; dùng event relationship, sequence/version hoặc trace context khi có.

## 10. Audit trong kiến trúc nhiều tenant

Trong SaaS multi-tenant, access token thường chứa hoặc liên kết với tenant context. Audit cần chứng minh request đã được thực hiện trong tenant nào và tránh ghi nhầm tenant do caller tự khai báo.

Các nguyên tắc:

- Lấy tenant context từ claim đã xác minh hoặc mapping tin cậy phía server.
- So khớp tenant trong token với tenant của tài nguyên được truy cập.
- Ghi tenant reference đã pseudonymize hoặc ID theo chính sách kiểm toán.
- Ghi rõ tenant context mismatch hoặc tenant inactive bằng reason code riêng.
- Giữ ranh giới truy vấn audit để người quản trị tenant chỉ xem được dữ liệu thuộc phạm vi được ủy quyền.
- Không cho phép caller thay đổi tenant filter của audit API để đọc log tenant khác.

Một người dùng có thể thuộc nhiều tenant. Audit cần ghi tenant context của request cụ thể, không suy luận rằng user chỉ có một tenant mặc định. Với Token Exchange, cần phân biệt tenant context của subject, actor và resource đích nếu chúng khác nhau.

### Ví dụ phát hiện truy cập chéo tenant

Nếu token được cấp cho `tenant-A` nhưng request truy cập tài nguyên của `tenant-B`, resource server phải từ chối theo policy. Audit event cần ghi:

- tenant context đã xác minh;
- tenant/resource context được yêu cầu;
- reason `TENANT_CONTEXT_MISMATCH`;
- decision `deny`;
- route/action và correlation ID.

Không ghi toàn bộ dữ liệu tài nguyên hoặc thông tin người dùng tenant khác chỉ để giải thích lý do từ chối.

## 11. Bảo vệ tính toàn vẹn và tính sẵn sàng của audit trail

Audit log có giá trị khi người có quyền không thể âm thầm sửa hoặc xóa lịch sử. Cần thiết kế bảo vệ từ lúc event được tạo đến khi lưu trữ và truy xuất.

### Thu thập và lưu trữ

- Gửi event qua kênh mã hóa và xác thực giữa producer với collector.
- Phân quyền riêng cho quyền ghi, đọc, export và quản trị retention.
- Dùng storage có append-only hoặc immutability/WORM nếu yêu cầu kiểm toán cần.
- Tách quyền quản trị audit store khỏi quyền quản trị ứng dụng được audit.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Bảo vệ backup, replica và export giống như audit store chính.
- Có cơ chế phát hiện event bị thiếu, trùng hoặc đến sai thứ tự.

### Kiểm tra tính toàn vẹn

Tùy mức độ rủi ro, có thể sử dụng:

- Hash chaining giữa các batch/event.
- Chữ ký số cho batch audit hoặc manifest định kỳ.
- Storage retention lock/immutable bucket.
- Checkpoint được ký và lưu ở hệ thống độc lập.
- Kiểm tra định kỳ checksum và khả năng khôi phục backup.

Hash chain đơn giản có thể biểu diễn:

```text
H0 = trusted_initial_checkpoint
Hn = SHA-256(Hn-1 || canonicalize(event_n))
```

Đây là mô hình minh họa. Hash chain chỉ phát hiện sửa đổi khi checkpoint hoặc giá trị hash được bảo vệ độc lập; nếu attacker có thể sửa toàn bộ log và tính lại toàn bộ chain, cơ chế đó không đủ. Có thể ký checkpoint theo lịch và lưu ở trust domain riêng.

### Xử lý khi audit sink không sẵn sàng

Nếu audit collector hoặc storage bị lỗi, hệ thống cần có chính sách theo mức độ nhạy cảm:

- Với thao tác nhạy cảm hoặc bắt buộc audit đồng bộ, có thể từ chối thao tác nếu không thể ghi nhận audit an toàn.
- Với request thông thường, có thể ghi vào durable local buffer hoặc message queue có giới hạn, rồi gửi lại khi sink phục hồi.
- Không giữ event vô hạn trong memory hoặc retry không giới hạn làm cạn tài nguyên.
- Phát metric/alert khi buffer tăng, event drop hoặc delivery lag vượt ngưỡng.
- Nếu phải drop event, ghi nhận sự cố audit gap ở kênh độc lập và có quy trình xử lý.

Không có một lựa chọn fail-open/fail-closed đúng cho mọi hệ thống. Chính sách phải phân loại hành động, yêu cầu compliance, mức rủi ro và khả năng buffering. Không được âm thầm bỏ qua audit failure đối với sự kiện bắt buộc lưu.

### Transactional outbox

Khi một thao tác nghiệp vụ và audit event cần nhất quán, có thể dùng transactional outbox: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng transaction; worker đọc outbox rồi chuyển event đến audit pipeline. Consumer cần idempotent theo `event_id` vì delivery có thể lặp.

Outbox giúp tránh tình huống dữ liệu đã thay đổi nhưng event audit không được phát do process crash giữa hai thao tác. Với truy cập chỉ đọc, có thể dùng durable audit buffer hoặc pipeline đồng bộ theo yêu cầu, vì không phải mọi read request đều có transaction dữ liệu để ghép outbox.

## 12. Privacy, data minimization và retention

Audit log có thể chứa định danh người dùng, tenant, client, IP hoặc lịch sử truy cập. Dù không lưu token gốc, dữ liệu này vẫn có thể nhạy cảm và có khả năng liên kết một cá nhân với hành vi.

Các nguyên tắc cần áp dụng:

1. Chỉ ghi trường cần thiết để đáp ứng mục đích audit, security investigation hoặc nghĩa vụ pháp lý.
2. Ưu tiên subject reference pseudonymous thay vì email, tên đầy đủ hoặc username nếu không cần.
3. Chỉ ghi IP, user agent hoặc network location khi có mục đích rõ ràng và retention phù hợp.
4. Không ghi request body mặc định; nếu cần, chỉ ghi trường allowlist đã được xem xét.
5. Phân quyền theo vai trò và tenant boundary; mọi truy vấn/export audit nhạy cảm cũng nên được audit.
6. Xác định retention theo quy định, hợp đồng, loại dữ liệu và mục đích; không giữ vô thời hạn theo mặc định.
7. Có quy trình legal hold, export và xóa/ẩn danh khi hết thời hạn được phép.

Thời hạn lưu audit không có một con số chung áp dụng cho mọi quốc gia, ngành và loại dữ liệu. Chủ hệ thống cần xác định thời hạn theo nghĩa vụ pháp lý, chính sách nội bộ, hợp đồng và yêu cầu điều tra. Nếu có legal hold, cần ghi nhận lý do và người phê duyệt.

Pseudonymization không đồng nghĩa anonymization. Nếu hệ thống có thể ánh xạ `subject_ref` về người dùng, dữ liệu vẫn cần được bảo vệ như dữ liệu cá nhân. Việc xóa khóa HMAC hoặc mapping cũng cần có quy trình, tránh làm mất khả năng kiểm toán khi đang có legal hold.

## 13. Ai được truy cập audit log?

Audit trail thường chứa dữ liệu nhạy cảm về hành vi và quyền truy cập. Không nên cho mọi developer hoặc tenant admin đọc toàn bộ log production.

Một mô hình phân quyền tham khảo:

| Vai trò | Quyền phù hợp |
|---|---|
| Security auditor | Đọc và truy vấn sự kiện trong phạm vi audit được phê duyệt; không sửa/xóa log gốc. |
| Incident responder | Truy cập dữ liệu cần thiết cho incident, có thời hạn và được ghi audit. |
| Tenant administrator | Chỉ xem audit thuộc tenant và chức năng được ủy quyền. |
| Application operator | Xem trạng thái pipeline/health và log kỹ thuật đã giảm thiểu; không mặc định xem toàn bộ identity data. |
| Audit platform administrator | Quản trị storage/pipeline theo phân tách nhiệm vụ; thao tác quản trị được ghi lại ở trust domain riêng. |
| Compliance officer | Truy xuất báo cáo theo phạm vi pháp lý và mục đích đã được phê duyệt. |

Nên dùng least privilege, MFA cho truy cập quản trị, approval cho export lớn, session timeout và periodic access review. Việc đọc, tìm kiếm, export, thay đổi retention hoặc tạo legal hold cũng có thể cần audit event riêng.

## 14. Phân tích sự kiện và phát hiện hành vi bất thường

Audit access token usage có thể hỗ trợ phát hiện nhiều kiểu rủi ro. Không nên chỉ cảnh báo theo một event đơn lẻ; hãy kết hợp baseline, context và nhiều tín hiệu.

### Token bị đánh cắp hoặc replay

Dấu hiệu có thể gồm:

- Cùng `token_ref` xuất hiện từ các network context rất khác nhau trong khoảng thời gian ngắn.
- Một token được sử dụng đồng thời ở các client/device không phù hợp với mô hình hoạt động.
- Token tiếp tục được trình bày sau khi đã ghi nhận revocation.
- Request rate hoặc hành động nhạy cảm tăng bất thường với cùng token reference.
- Token có sender-constraining nhưng proof/certificate binding không khớp.

Địa chỉ IP khác nhau không tự chứng minh token bị đánh cắp; mobile network, NAT, proxy và roaming có thể làm thay đổi nguồn truy cập. Cần đánh giá cùng thời gian, thiết bị, client, audience, hành vi và mức độ nhạy cảm của action.

### Scope và audience bất thường

- Client thường chỉ gọi `inventory.read` nhưng đột nhiên dùng scope quản trị.
- Token có audience không phù hợp với service nhưng vẫn được gửi đến nhiều API.
- Token Exchange tạo audience downstream ngoài mô hình delegation đã phê duyệt.
- Một client bắt đầu truy cập resource type mà trước đó chưa từng sử dụng.

### Truy cập sau khi thu hồi hoặc disable

- Token reference vẫn xuất hiện sau thời điểm revoke.
- Client disabled tiếp tục gọi API hoặc thực hiện refresh/exchange.
- Tenant/membership đã inactive nhưng token cũ vẫn được chấp nhận.
- Resource server chưa nhận event invalidation hoặc cache status đã stale.

### Hành vi truy cập chéo tenant

- Tenant context trong token khác tenant của tài nguyên.
- Một subject truy cập nhiều tenant bất thường so với membership được cấp.
- Request bị từ chối lặp lại với `TENANT_CONTEXT_MISMATCH`.

### Không biến audit thành cơ chế profiling quá mức

Phát hiện bất thường phải có mục đích bảo mật rõ ràng, tiêu chí minh bạch, quyền truy cập giới hạn và quy trình xử lý false positive. Không nên suy luận hành vi xấu chỉ từ quốc gia, IP hoặc một lần 401/403. Hạn chế dữ liệu vị trí/thiết bị ở mức thực sự cần thiết.

## 15. Báo cáo và truy vấn audit

Audit API hoặc công cụ truy vấn cần hỗ trợ lọc theo thời gian, service, client, subject reference, token reference, audience, action, decision và reason code. Các bộ lọc phải được phân quyền ở server; không tin tenant filter hoặc client filter do caller tự đặt.

Ví dụ truy vấn logic:

```sql
SELECT
    event_time,
    service,
    client_id,
    subject_ref,
    audience,
    action,
    authorization_decision,
    decision_reason,
    http_status
FROM access_token_audit
WHERE event_time >= :from_time
  AND event_time < :to_time
  AND token_ref = :token_ref
ORDER BY event_time ASC;
```

Truy vấn trên là minh họa. Cần giới hạn khoảng thời gian, phân trang, kiểm soát quyền xem `subject_ref`/`token_ref` và audit thao tác truy vấn nếu dữ liệu có độ nhạy cảm cao. Không cung cấp endpoint tìm kiếm cho phép người dùng dò token bằng raw token.

Một báo cáo compliance có thể tổng hợp:

- Số lượt access token được trình bày theo service và loại resource.
- Số lần authentication fail theo reason code.
- Số lần authorization deny theo policy.
- Token bị dùng sau revocation hoặc sau client/tenant disable.
- Các lần truy cập tài nguyên nhạy cảm.
- Audit pipeline delay, dropped event và thời gian lưu trữ.
- Người đã truy cập hoặc export audit data.

## 16. Kiểm soát chất lượng audit event

Audit event cần được kiểm tra giống như một phần của hệ thống bảo mật.

- **Schema validation:** kiểm tra field bắt buộc, kiểu dữ liệu, enum và `schema_version`.
- **Identity provenance:** xác định trường nào lấy từ token đã xác minh, introspection, client registry hoặc request context.
- **Completeness:** đảm bảo các route nhạy cảm và luồng grant quan trọng có phát event.
- **Uniqueness/idempotency:** `event_id` duy nhất; consumer xử lý event lặp an toàn.
- **Ordering:** ghi event time và observed time; không giả định message bus luôn giữ thứ tự toàn cục.
- **Delivery:** đo queue lag, retry, dead-letter và event drop.
- **Integrity:** kiểm tra immutable storage, signature/checkpoint và backup.
- **Privacy:** tự động phát hiện token/header/secret trong payload và từ chối hoặc redact.
- **Access control:** kiểm tra người dùng chỉ xem được phạm vi audit được cấp.
- **Retention:** kiểm tra lifecycle policy, legal hold và deletion workflow.

Nên có kiểm thử định kỳ với token hợp lệ, token hết hạn, token sai audience, thiếu scope, token revoked, client disabled, tenant inactive và lỗi introspection. Mỗi test xác nhận event có đúng reason, identity provenance, decision và không chứa raw credential.

## 17. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Ghi nguyên access token vào log | Log trở thành nơi lưu bearer credential có thể bị replay. | Chỉ ghi token fingerprint HMAC hoặc reference an toàn. |
| Ghi toàn bộ Authorization header | Credential có thể xuất hiện trong application, proxy và SIEM log. | Redact header ở mọi tầng; dùng allowlist trường audit. |
| Ghi claims trước khi xác minh JWT | Attacker có thể đưa subject/client/audience giả vào audit. | Chỉ đánh dấu claims là verified sau khi validation thành công. |
| Coi `sub` luôn là người dùng | Audit sai actor đối với client credentials hoặc delegation. | Phân biệt subject, client và actor. |
| Gộp authorization allow với operation success | Báo cáo cho rằng thao tác đã hoàn tất dù database/worker thất bại. | Ghi decision và operation result riêng. |
| Chỉ ghi 401/403, không ghi reason | Khó phân biệt token invalid, thiếu scope và tenant inactive. | Dùng reason code hữu hạn, đã chuẩn hóa. |
| Sampling audit event bắt buộc | Mất bằng chứng về một số lần truy cập. | Xác định coverage; không sampling sự kiện bắt buộc. |
| Dùng trace/metric thay audit | Trace có thể sampling; metric không có chi tiết từng lần truy cập. | Duy trì audit store riêng theo yêu cầu. |
| Không ghi audit khi token bị từ chối | Mất dấu hiệu tấn công, token replay hoặc sai cấu hình. | Ghi event validation/authorization failure với dữ liệu an toàn. |
| Lưu raw user ID/email không cần thiết | Tăng rủi ro riêng tư và phạm vi dữ liệu nhạy cảm. | Pseudonymize và áp dụng data minimization. |
| Không bảo vệ audit store | Log có thể bị sửa/xóa bởi người vận hành ứng dụng. | Append-only/immutable storage, phân tách nhiệm vụ và integrity checkpoint. |
| Không theo dõi audit pipeline drop | Sự cố mất event không được phát hiện. | Theo dõi delivery lag, retry, dead-letter và audit gap. |
| Retention không có thời hạn | Lưu dữ liệu quá lâu hoặc không đáp ứng nghĩa vụ. | Đặt retention, legal hold và deletion policy được phê duyệt. |

## 18. Ma trận kiểm thử tình huống

| Tình huống | Audit event mong đợi |
|---|---|
| JWT hợp lệ, đúng audience/scope, đọc tài nguyên thành công | Event access decision allow và operation succeeded; có token reference an toàn. |
| JWT sai chữ ký | Validation failed với reason `INVALID_SIGNATURE`; không ghi claims chưa xác minh. |
| JWT hết hạn | Validation failed với reason `TOKEN_EXPIRED`. |
| JWT sai issuer/audience | Validation failed với reason tương ứng; không thực thi action. |
| Opaque token introspection `active=false` | Validation failed/inactive; không ghi như dependency error. |
| Introspection timeout | Dependency failure; không kết luận token invalid. |
| Token hợp lệ nhưng thiếu scope | Authentication valid, authorization deny `INSUFFICIENT_SCOPE`, operation not executed. |
| Tenant context mismatch | Authorization deny `TENANT_CONTEXT_MISMATCH`; không lộ dữ liệu tenant khác. |
| Token đã revoke vẫn được trình bày | Ghi token status/revocation context và request bị từ chối; phát hiện propagation gap nếu có. |
| Token Exchange thành công | Ghi client, subject/actor context, audience/scope mới và token reference mới. |
| Client credentials token được dùng bởi service | Phân biệt service principal/client với user subject. |
| Request được cho phép nhưng database timeout | Authorization allow, operation failed; không ghi succeeded. |
| Audit sink tạm thời không khả dụng | Durable buffer hoặc policy block; phát hiện delivery lag/gap theo thiết kế. |
| Event được giao lặp | Consumer idempotent; không tạo bản ghi nghiệp vụ trùng. |
| Audit user export dữ liệu | Ghi event truy cập/export audit với actor, phạm vi và thời điểm. |

Test nên xác nhận cả schema, field provenance, event count, correlation ID và nội dung nhạy cảm. Có thể thêm kiểm tra tự động tìm mẫu JWT, Bearer header, refresh token hoặc client secret trong audit payload để ngăn rò rỉ credential.

## 19. Checklist triển khai

**Nguồn phát và nội dung event**

- Xác định event cần ghi tại authorization server, gateway, resource server và worker.
- Phân biệt token issuance, token presentation, authentication, authorization và operation result.
- Có schema version, event ID, event time, producer và reason code chuẩn hóa.
- Chỉ ghi claims từ token đã xác minh hoặc metadata từ nguồn tin cậy.
- Phân biệt user subject, client principal và actor delegation.

**Bảo vệ credential và dữ liệu**

- Không ghi raw access token, refresh token, authorization header hoặc client secret.
- Dùng token fingerprint HMAC nếu cần liên kết sự kiện; quản lý khóa riêng và version.
- Pseudonymize subject/tenant/resource reference khi phù hợp.
- Kiểm soát label và field có cardinality cao.
- Có quyền truy cập, retention, legal hold và deletion policy rõ ràng.

**Tính toàn vẹn và vận hành**

- Gửi event qua kênh xác thực và mã hóa.
- Dùng append-only/immutable storage khi yêu cầu cần.
- Có integrity checkpoint, backup và kiểm tra khôi phục.
- Có durable buffer/outbox, retry có giới hạn và dead-letter handling.
- Theo dõi event drop, queue lag, duplicate và audit gap.
- Audit cả việc đọc, tìm kiếm, export và thay đổi chính sách audit.

**Kiểm thử và phát hiện**

- Kiểm thử valid, expired, invalid, revoked, insufficient scope và dependency failure.
- Kiểm thử client/tenant disable, Token Exchange và multi-tenant isolation.
- Xác minh không ghi claims chưa xác minh hoặc raw credential.
- Xác minh event allow/deny riêng với kết quả thao tác.
- Có use case phát hiện replay, token sau revoke và truy cập chéo tenant.

## 20. Kết luận

Audit access token usage tạo bằng chứng có cấu trúc về việc token được phát hành, trình bày, xác minh và sử dụng để truy cập tài nguyên. Audit trail có giá trị khi xác định đúng client, subject, actor, audience, scope, action, decision và kết quả; đồng thời liên kết được các service trong một request hoặc luồng nghiệp vụ.

Nguyên tắc quan trọng nhất là bảo vệ credential trong chính hệ thống audit: không ghi token gốc, chỉ sử dụng fingerprint/reference an toàn, không tin claims trước khi xác minh và giới hạn dữ liệu cá nhân theo mục đích. Kết hợp schema ổn định, event delivery bền vững, storage chống sửa đổi, retention có kiểm soát và kiểm thử đầy đủ giúp audit hỗ trợ điều tra bảo mật và kiểm toán mà không tạo thêm rủi ro cho vòng đời token.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi bearer access token và các lỗi xác thực tài nguyên.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, scope, client và token endpoint.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token và xử lý token liên quan.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token qua introspection.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject token, actor token và token được phát hành qua exchange.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claim liên quan.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): quản lý log bảo mật, lưu trữ, bảo vệ và phân tích.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thực hành ghi log, dữ liệu không nên ghi và bảo vệ log.
