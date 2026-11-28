# Log security event của API gateway

> **Chương:** API và network service security  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Phạm vi:** Ghi nhận, chuẩn hóa, bảo vệ và phân tích các sự kiện an ninh tại API gateway trong kiến trúc nhiều lớp gồm DNS, TLS/mTLS, CDN/WAF, reverse proxy, load balancer, VPN, firewall, IDS/IPS, workload identity, các dịch vụ cloud và backend.  
> **Trọng tâm:** Log phải giúp chứng minh **điều gì đã được kiểm tra, quyết định nào được thực thi, tại điểm nào và đối với danh tính nào**, mà không tiết lộ credential hoặc làm sai lệch kết luận khi một request không đi tới backend.

## 1. Log security event của API gateway là gì?

**API gateway** là điểm vào điều phối và kiểm soát request tới một hay nhiều dịch vụ. Ngoài định tuyến và cân bằng tải, gateway có thể thực thi **TLS, xác thực token/API key/mTLS, phân quyền theo route/scope, giới hạn tốc độ, quota, WAF/API schema validation, kiểm soát địa chỉ nguồn và chính sách egress** tùy sản phẩm.

**Security event log** ghi lại một sự kiện hoặc quyết định có ý nghĩa bảo mật: token hết hạn, chữ ký JWT không hợp lệ, quyền gọi route không đủ, client certificate sai trust domain, rate-limit bị vượt, WAF chặn yêu cầu, một rule chuyển chế độ, hoặc một quản trị viên thay policy. Event phải có đủ ngữ cảnh để phân tích **ai/đối tượng nào, hành động gì, ở đâu, khi nào, kết quả gì và dựa trên policy nào**.

Ví dụ hai yêu cầu đều trả **HTTP 403**:

- Gateway từ chối request vì **mTLS client identity** không nằm trong allowlist.
- Backend chấp nhận mạng và token nhưng trả 403 do **đối tượng dữ liệu không thuộc tenant của user**.

Nếu chỉ ghi status=403 mà không có **decision_source, reason_code, enforcement_point và request_id**, SOC có thể nhầm lớp tạo quyết định, tìm sai hệ thống và mở ngoại lệ nguy hiểm.

**Thông điệp cốt lõi:** Một HTTP access log cho biết **request đi qua ra sao**. Security event log cho biết **biện pháp bảo vệ đã đánh giá và thực thi điều gì**. Hai loại log bổ sung cho nhau nhưng không đồng nghĩa; log đầy đủ cũng không tự khẳng định hệ thống đang có chính sách bảo mật đúng.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **access log, security decision event, audit/config event và trace**.
2. Thiết kế sự kiện cho **AuthN, AuthZ, JWT/OAuth2, API key, mTLS, WAF, validation, rate limit và bot/abuse**.
3. Chuẩn hóa **event ID, request ID, trace/span, actor, client IP đáng tin, tenant, policy ID, action, reason và HTTP status**.
4. Thiết kế collection pipeline và SIEM phát hiện tấn công nhưng không ghi **token, cookie, khóa, body hoặc PII** ngoài nhu cầu.
5. Phân biệt **401/403/429/502/503, WAF BLOCK/COUNT/CHALLENGE và app-level deny**.
6. Xây dựng detection có tính đến **false positive, NAT, retries, CDN cache, multi-region và clock skew**.
7. Kiểm thử end-to-end, xây dashboard, thực hiện runbook sự cố và kiểm chứng độ toàn vẹn log.

## 2. Sơ đồ đường đi và các điểm ghi sự kiện

~~~mermaid
flowchart LR
    U[Web / Mobile / Partner Client] --> E[CDN / TLS Edge]
    E --> W[WAF / Bot Protection]
    W --> G[API Gateway]
    G --> A[Identity / Token Validator]
    G --> R[Rate Limit / Quota]
    G --> S[Service / Backend]
    S --> D[DB / Dependency]
    E -. Edge event .-> Q[Telemetry Pipeline]
    W -. WAF security event .-> Q
    G -. Auth / AuthZ / Route events .-> Q
    A -. IdP / JWKS / Revocation events .-> Q
    R -. Counter / Throttle events .-> Q
    S -. Business authorization logs .-> Q
    Q --> L[SIEM / Log Analytics / Alerting]
~~~

**Không phải mọi request đều tới backend.** Request bị WAF BLOCK, gateway từ chối token, thiếu scope, bị rate-limit hoặc được CDN trả từ cache có thể **không có application log tương ứng**. Trái lại, một API call có thể tới nhiều backend vì fan-out/retry; phải dùng ID và ngữ cảnh theo lần thử.

| Lớp | Quyết định/log thường thấy | Giới hạn quan sát |
|---|---|---|
| **CDN/Edge** | TLS, host, cache, edge ID, deny ở edge | Có thể không thấy backend authorization |
| **WAF/WAAP** | Signature/rule match, anomaly score, count/challenge/block | Match một rule chưa chắc đã block |
| **API gateway** | AuthN, API key, JWT, mTLS, scope/route ACL, quota, routing | Không tự hiểu quyền object-level trong backend nếu chưa được tích hợp |
| **IdP/OAuth authorization server** | Token issuance, login/MFA, key rotation, revocation | Gateway cần mapping, không mặc định mọi event login tạo API request |
| **Backend** | Permission từng đối tượng, tenant, business action | Có thể không thấy request bị chặn ở edge |
| **Firewall/NDR/IDS** | Network allow/deny, flow, peer TLS metadata | Không mặc định đọc HTTP headers trong TLS |
| **SIEM** | Tương quan event/alert theo actor, policy, trace | Phải tính sampling, ingestion gap, quyền truy cập và time skew |

**Các lớp cần có ranh giới tin cậy rõ ràng.** Nếu backend public cho phép bỏ qua gateway, log gateway không còn đại diện cho toàn bộ traffic đi tới API. Cần bảo vệ origin/backend bằng security group, firewall, service mesh mTLS hoặc network policy thích hợp.

## 3. Access log, security event, audit log và trace khác nhau thế nào?

| Loại telemetry | Tập trung vào | Ví dụ |
|---|---|---|
| **HTTP access log** | Một request/response, phương thức, route, status, duration, upstream | GET /v1/items → 200, 47 ms |
| **Security decision event** | Một quyết định kiểm soát truy cập hoặc bảo vệ | AUTHZ_DENY do thiếu scope orders:write |
| **Security detection event** | Phát hiện hoặc tín hiệu nguy cơ, chưa chắc chặn | WAF RULE_MATCH ở chế độ COUNT |
| **Control-plane audit event** | Người/quy trình nào sửa security policy, key, role, gateway config | Admin đổi rate-limit policy, phiên bản v4 → v5 |
| **Distributed trace** | Quan hệ nhân quả/độ trễ giữa các span | Gateway → Orders → Inventory |
| **Metric** | Số lượng, tỷ lệ và phân bố theo thời gian | Tỷ lệ 401, p99 gateway latency, số WAF blocks |
| **Incident/alert** | Kết luận hoặc giả thuyết từ rule phân tích nhiều events | Alert credential abuse có bằng chứng và severity |

**Một request có thể tạo nhiều security events**: JWT hợp lệ, scope được allow, WAF match nhưng chỉ COUNT và cuối cùng rate-limit deny. Không nên gộp mọi event thành một status hoặc coi sự kiện "rule matched" là kết quả cuối.

### 3.1. Event khác alert

Một **event** là dữ kiện nguồn, ví dụ token validation thất bại. Một **alert** là tín hiệu phân tích rằng tập events có thể cần điều tra, ví dụ số lượng token sai tăng bất thường theo client/tenant. Một event không đồng nghĩa một cuộc tấn công; user cấu hình sai, lệch đồng hồ, token hết hạn hoặc ứng dụng retry cũng có thể sinh sự kiện.

### 3.2. Control-plane không giống data-plane

**Data-plane events** ghi các request thực được gateway kiểm tra. **Control-plane audit events** ghi ai thay đổi policy, secret reference, route, trust store, IdP config hoặc chế độ WAF. Một incident có thể bắt nguồn từ một thay đổi config dù traffic logs chỉ cho thấy mức 403/200 biến động. Cần giữ **policy_version/config_revision/change_id** trong cả hai nhóm để đối chiếu.

## 4. Phân loại security event theo quyết định

| Nhóm | Event type đề xuất | Khi nào ghi | Quyết định thường gặp |
|---|---|---|---|
| **TLS** | TLS_HANDSHAKE_REJECTED | TLS protocol/cert validation thất bại ở gateway | REJECT |
| **mTLS** | CLIENT_CERT_REJECTED | Thiếu, hết hạn, sai identity/EKU/trust theo policy | REJECT |
| **Authentication** | AUTHN_FAILED | Credential/token không hợp lệ hoặc không có | DENY/CHALLENGE |
| **Authentication** | AUTHN_SUCCEEDED | Danh tính đã được xác thực | ALLOW_AT_AUTHN_LAYER |
| **Authorization** | AUTHZ_DENIED | Không có role/scope/permission tới route | DENY |
| **Authorization** | AUTHZ_GRANTED | Route permission đã được đánh giá và cấp | ALLOW_AT_AUTHZ_LAYER |
| **API key** | API_KEY_REJECTED | Key không hợp lệ/thu hồi/không thuộc consumer | DENY |
| **Quota/rate-limit** | RATE_LIMIT_EXCEEDED | Vượt ngân sách request theo policy | THROTTLE/DENY |
| **WAF** | WAF_RULE_MATCHED | Rule/signature/anomaly kiểm tra thấy match | COUNT/BLOCK/CHALLENGE theo final action |
| **Schema** | REQUEST_SCHEMA_INVALID | Body/parameters/content type không đáp ứng contract | REJECT |
| **Network policy** | SOURCE_POLICY_DENIED | Source/zone không được phép qua gateway | DENY |
| **Bot/abuse** | AUTOMATION_SUSPECTED | Tín hiệu bot/abuse theo engine | DETECT/CHALLENGE/BLOCK |
| **Configuration** | SECURITY_POLICY_CHANGED | Thay đổi ACL, route policy, rule, IAM mapping | AUDIT |
| **Key/trust** | JWKS_REFRESH_FAILED | Không tải được key material theo policy | ERROR; tác động auth tùy cấu hình |
| **Availability** | SECURITY_CONTROL_UNAVAILABLE | Rate limiter/WAF/auth provider không khả dụng | FAIL_OPEN/FAIL_CLOSED nếu sản phẩm ghi được |

Tên event ở đây là **schema tham chiếu do bài học đề xuất**, không phải danh sách mặc định của một vendor. Thực tế phải ánh xạ events của mỗi nhà cung cấp vào taxonomy chung mà **không đánh mất mã lỗi gốc**.

### 4.1. Final disposition và rule evaluation

Đề xuất tách ba thuộc tính:

- **rule_match**: kiểm tra nào phát hiện điều kiện?
- **policy_action**: cấu hình của rule là count, block, challenge, allow, skip?
- **final_disposition**: request thực sự được forward, chặn hay xử lý bằng cơ chế nào?

Một request có thể match ba WAF rules nhưng chỉ **final_disposition=ALLOW** vì policy đang ở chế độ monitor. Ghi "BLOCK" chỉ vì rule match sẽ làm sai báo cáo sự cố.

## 5. Một security event tốt phải trả lời được sáu câu hỏi

1. **When:** thời điểm sự kiện và timestamp của nguồn, theo UTC/offset.
2. **Where:** ingress, gateway ID, cloud region, environment, route, backend/zone nếu có.
3. **Who:** danh tính client/user/workload đã xác thực, API consumer/tenant theo quyền được phép; không lấy header tự khai thay identity.
4. **What:** loại hành động/request và security check đang thực thi.
5. **Outcome:** match, action, final disposition, HTTP/gRPC status và reason code.
6. **Why/how:** policy/rule ID, config version, source control plane và correlation IDs.

### 5.1. Trường tối thiểu đề xuất

| Trường | Loại | Nội dung |
|---|---|---|
| event_id | String unique | ID của **bản ghi event**, không dùng rule_id thay thế |
| event_time | UTC timestamp | Thời điểm event xảy ra |
| ingest_time | UTC timestamp (tại collector) | Thời điểm pipeline nhận event |
| schema_version | String | Phiên bản hợp đồng log |
| event_type | Enum/string chuẩn hóa | AUTHN_FAILED, WAF_RULE_MATCHED... |
| security_control | Enum | jwt, mtls, api_key, waf, rate_limit, route_acl... |
| gateway_id / service | String | Nguồn event và điểm thực thi |
| request_id / trace_id | String có giới hạn format | Liên kết với HTTP access log/trace |
| actor_type / actor_id | String scoped | User, client application, service hoặc anonymous |
| tenant_id | String scoped | Khi ứng dụng multi-tenant và đã xác minh nguồn |
| route_template / http_method | String đã chuẩn hóa | Không log URL/query thô mặc định |
| decision / final_disposition | Enum | ALLOW, DENY, BLOCK, CHALLENGE, COUNT... |
| reason_code | Enum | Mã lý do máy đọc được, không chứa secret |
| policy_id / rule_id / policy_version | String | Kiểm soát gây quyết định |
| http_status / grpc_status | Number/string hoặc null | Kết quả tại lớp tương ứng |
| trusted_client_ip | IP hoặc null | Chỉ khi biết rõ trusted proxy chain |
| source_context_trust | Enum | verified_gateway, trusted_edge, untrusted |

**Không cần mọi event đều có tất cả trường.** Một lỗi TLS handshake có thể xảy ra **trước khi có HTTP request ID/route/user**, trong khi audit thay cấu hình không liên quan HTTP request nào. Dùng null hoặc field absent với semantics rõ.

## 6. Schema JSON mẫu cho security decision event

~~~json
{
  "schema_version": "1.0",
  "event_id": "evt-628de4",
  "event_time": "2026-11-28T09:05:14.213Z",
  "event_type": "AUTHZ_DENIED",
  "security_control": "route_authorization",
  "environment": "production",
  "gateway_id": "api-gw-02",
  "region": "region-a",
  "service": "orders-api",
  "request_id": "a9c31d6e5b4c4ed29cbd095a70ab8e11",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "actor_type": "oauth_client",
  "actor_id": "consumer-orders-web",
  "tenant_id": "tenant-demo",
  "identity_verified": true,
  "method": "POST",
  "route_template": "/v1/orders",
  "client_ip": "192.0.2.18",
  "client_ip_source": "trusted_edge",
  "decision": "DENY",
  "final_disposition": "DENY",
  "reason_code": "INSUFFICIENT_SCOPE",
  "required_permission": "orders:write",
  "policy_id": "api-authz-orders",
  "policy_version": "v7",
  "http_status": 403,
  "upstream_attempt_count": 0,
  "sensitive_fields_redacted": true
}
~~~

Toàn bộ giá trị là **dữ liệu minh họa**. Không có field chứa JWT, API key, Authorization/Cookie hoặc body. **required_permission** trong ví dụ là tên scope, không phải scope token được lấy từ dữ liệu chưa kiểm chứng.

### 6.1. Ý nghĩa của decision so với HTTP status

- **decision=DENY** nói rằng control hiện tại đã từ chối.
- **http_status=403** mô tả response tại gateway, không nhất thiết status sẽ giống ở tất cả proxies trước nó.
- **upstream_attempt_count=0** giải thích vì sao backend không có request log.
- **actor_id** chỉ nên được điền khi identity đã được xác minh; khi token không hợp lệ, dùng actor_type=unknown hoặc anonymous và tách giá trị chưa được tin cậy.

### 6.2. Schema cho một event chưa xác thực

~~~json
{
  "event_id": "evt-628de5",
  "event_time": "2026-11-28T09:05:15.008Z",
  "event_type": "AUTHN_FAILED",
  "security_control": "jwt_validation",
  "request_id": "782a70e3ed3e4ebba123d76ed8ccf27d",
  "route_template": "/v1/orders",
  "actor_type": "unknown",
  "actor_id": null,
  "identity_verified": false,
  "reason_code": "TOKEN_SIGNATURE_INVALID",
  "decision": "DENY",
  "http_status": 401,
  "policy_id": "jwt-validator-v3"
}
~~~

**Không ghi subject, tenant hay quyền được khai trong một JWT sai chữ ký thành identity đã xác thực.** Nếu cần nghiên cứu mẫu credential không hợp lệ, dùng phân loại reason an toàn và metadata tối thiểu theo chính sách điều tra.

## 7. Authentication events: token, session và OAuth2

API gateway thường phải xác định **có chứng thực phù hợp** trước khi chuyển request tới backend. Các cơ chế bao gồm OAuth 2.0 bearer token, JWT hoặc opaque access token, API key, session cookie, mTLS và các cơ chế cấp danh tính khác.

| Event reason | Điều gì đã xảy ra? | Không nên suy ra |
|---|---|---|
| MISSING_CREDENTIAL | Không có credential theo policy | Chưa đủ kết luận hành vi ác ý |
| TOKEN_EXPIRED | Thời hạn token không còn phù hợp | Không chứng minh user cố tình tấn công |
| TOKEN_NOT_YET_VALID | Token chưa tới thời điểm hợp lệ theo policy | Có thể là clock skew/client lỗi |
| TOKEN_SIGNATURE_INVALID | Không xác minh được chữ ký token | Không tin claims bên trong token |
| TOKEN_ISSUER_INVALID | Issuer không nằm trong danh sách được tin | Không tự đổi allowlist theo giá trị nhận được |
| TOKEN_AUDIENCE_INVALID | Audience không dành cho API này | Không chấp nhận token của dịch vụ khác |
| TOKEN_REVOKED | Token/session bị thu hồi theo hệ thống hỗ trợ | Cần kiểm tra freshness của cơ chế revocation |
| API_KEY_INVALID | API key không hợp lệ/thu hồi | Không log key để "debug" |
| MTLS_CLIENT_CERT_INVALID | Client identity không hợp lệ theo chain/SAN/EKU/trust policy | Không thay bằng trust-all |
| AUTH_PROVIDER_UNAVAILABLE | Hệ thống xác thực phụ trợ không khả dụng | Phân biệt security failure với outage |

### 7.1. HTTP 401 và HTTP 403

Theo semantics HTTP, **401 Unauthorized** thường gắn với request thiếu hoặc có credential không được chấp nhận ở cơ chế xác thực thích hợp, có thể cần **WWW-Authenticate** challenge. **403 Forbidden** thường biểu thị server đã hiểu request nhưng từ chối thực hiện; cả nguồn từ chối và cách ánh xạ status phụ thuộc gateway/ứng dụng.

Một token JWT có chữ ký hợp lệ **nhưng không đủ scope** thường phù hợp với event **AUTHZ_DENIED**; HTTP status cụ thể phải theo contract/API và tiêu chuẩn bearer-token liên quan. Tránh đồng nhất mọi trường hợp 401/403 với credential bị đánh cắp.

### 7.2. Event sau MFA hoặc IdP login

Gateway có thể thấy request hợp lệ nhờ access token, nhưng **MFA challenge/login** có thể diễn ra ở IdP. Không tự giả định gateway có thể xác minh MFA chỉ vì nhận một JWT có chuỗi text bất kỳ. Cần dùng **claims/cơ chế đã ký và policy xác thực bởi IdP**, đồng thời tương quan với IdP logs theo session/actor khi được phép.

## 8. JWT validation security events

Một JWT access token cần được kiểm tra theo hồ sơ triển khai: **chữ ký và thuật toán được phép, issuer, audience, thời gian, token type, key ID/JWKS và các claims bắt buộc**. Cần tuân theo hướng dẫn thực hành JWT, không để dữ liệu từ token tự quyết định cách kiểm tra.

### 8.1. Những trường nên log

- **validation_result**: thành công/thất bại.
- **reason_code**: EXP, NBF, INVALID_SIGNATURE, UNKNOWN_KID, BAD_ISS, BAD_AUD hoặc mã tương đương.
- **issuer_config_id** (nếu được phép) và **JWKS source/cache state**.
- **algorithm_policy_version**, không cần log JWT header/payload thô.
- **scope/role đã xác thực** ở mức cần thiết cho audit, không phơi toàn bộ claims.
- **latency / cache hit / timeout** khi validator gọi JWKS/introspection.

### 8.2. Phân biệt ba nhóm lỗi

| Nhóm | Biểu hiện | Hành động điều tra |
|---|---|---|
| **Credential không hợp lệ** | Token signature, issuer, audience hoặc time fail | Giữ DENY, xác minh client/version và nguồn phát |
| **Validator/config lỗi** | JWKS URI sai, trust cache lỗi, key rotation thiếu đồng bộ | Kiểm tra IdP/JWKS config/change logs |
| **Hạ tầng không khả dụng** | JWKS/introspection timeout, DNS/TLS error, clock drift | Kiểm tra dependency health và failure policy |

**Không tự động kết luận hàng loạt UNKNOWN_KID là tấn công.** IdP đổi signing key nhưng gateway chưa refresh JWKS có thể gây sự cố diện rộng; dù vậy vẫn phải **từ chối token không xác minh được**, rồi khắc phục trust synchronization.

### 8.3. Không đưa JWT vào log

JWT có thể chứa thông tin nhận dạng và access token có thể được dùng lại như bearer credential. **Không ghi Authorization, token string, refresh token, cookie hay secret**. Hash thông thường của secret giá trị thấp hoặc token ngắn có thể tạo rủi ro liên kết/đoán; nếu thực sự cần fingerprint điều tra, dùng **HMAC với khóa bảo vệ và scope/retention được duyệt**, không log giá trị gốc.

## 9. Authorization events: từ route ACL đến object-level

Gateway có thể thực hiện **route authorization** dựa trên scope, role, consumer, tenant, mTLS client identity hoặc resource allowlist. Tuy nhiên nhiều lỗi API nguy hiểm nằm **bên trong ứng dụng**: BOLA (Broken Object Level Authorization), BFLA (Broken Function Level Authorization), quyền theo thuộc tính hoặc tenant boundary.

### 9.1. Vì sao AuthN thành công không đủ?

Một user có token hợp lệ để GET /v1/orders có thể **không được đọc một đơn hàng thuộc user/tenant khác**. Gateway chỉ biết route tổng quát, trừ khi đã được cấp ngữ cảnh đáng tin và tích hợp mô hình authorization từng object. Backend vẫn phải kiểm tra **subject → action → object/tenant**.

~~~mermaid
flowchart TD
    A[API Request] --> G[Gateway AuthN/Route AuthZ]
    G -->|Invalid credential/route scope| X[Gateway DENY + security event]
    G -->|Pass| B[Backend]
    B --> P{Object/tenant/business authorization}
    P -- Deny --> Y[App-level DENY + business audit event]
    P -- Allow --> Z[Execute business operation]
    G -. Request/trace ID .-> L[SIEM]
    Y -. Request/trace + app reason .-> L
~~~

**Nếu app trả 403**, không tự ghi **gateway AUTHZ_DENIED**. Gateway đã pass một lớp còn app tạo quyết định ở lớp sau. Schema cần **decision_source=backend_application** và **event_origin** tương ứng để tránh đổ lỗi sai.

### 9.2. Điều không nên ghi vào event

Tránh log full object ID khi có thể là PII hoặc bí mật; ưu tiên **resource_type, action, tenant mismatch reason** và định danh pseudonymous theo chính sách. Không log toàn bộ path/query để phân loại BOLA nếu path chứa customer IDs.

### 9.3. Policy change và hiệu lực của quyền

Khi quyền bị đổi giữa session, gateway có thể dùng cached policy hoặc token đã cấp trước đó. Log nên có **policy_version, token validation time, cache age** nếu hữu ích, nhưng không tiết lộ nội dung credential. Quan sát event không đủ để khẳng định quyền đã được thu hồi tức thì; cần kiểm chứng **session/token revocation, policy refresh và backend authorization**.

## 10. API key, consumer identity và lifecycle

API key là một cơ chế nhận diện/kiểm soát API consumer theo sản phẩm. Nó thường **không thay được user authentication** và có thể bị lộ nếu nhúng vào ứng dụng public/mobile không được bảo vệ.

| Event | Ý nghĩa | Dữ liệu nên ghi |
|---|---|---|
| API_KEY_REJECTED | Key không hợp lệ hoặc đã thu hồi | Reason, consumer_id nếu đã được xác minh, key reference không nhạy cảm |
| API_KEY_QUOTA_EXCEEDED | Consumer vượt quota | Plan/quota ID, bucket, giới hạn, thời gian áp dụng |
| API_KEY_ROTATED | Key được thay thế theo change | Key alias, owner, actor quản trị, time, policy version |
| API_KEY_REVOKED | Key bị vô hiệu hóa | Owner, reason_code, effective time và admin event |
| API_KEY_USAGE_ANOMALY | Mẫu sử dụng khác baseline | Service/route, region, count, false-positive context |

**Không ghi API key ở path, query, log headers hoặc ticket.** Nếu hệ thống dùng key ID tách khỏi secret thì key ID có thể dùng để tra audit theo quyền phù hợp; đừng dùng **hash của key yếu** như một lựa chọn mặc định mà không đánh giá rủi ro.

### 10.1. Truy cập theo consumer không thay user authorization

Một API key đối tác có thể chỉ cho phép gọi **/v1/partner/report**. Backend vẫn cần xác minh user/tenant và loại dữ liệu được phép xuất. Mô hình **consumer identity → route policy → application authorization** phải có log đủ liên kết để xử lý nghi vấn vượt quyền.

## 11. mTLS, certificate identity và security event

Trong API-to-API traffic, gateway có thể yêu cầu **mutual TLS (mTLS)** và kiểm tra client certificate. Event hữu ích gồm:

- Thiếu certificate khi route yêu cầu mTLS.
- Certificate hết hạn, chưa hiệu lực, sai chain/trust bundle hoặc danh tính SAN không khớp.
- Trust domain/URI SAN không được phép đối với service đích.
- Certificate hợp lệ nhưng **client workload không được gọi route**.
- Session/peer identity khác với IAM authorization context được kỳ vọng.

### 11.1. Một event TLS có thể không có HTTP request

Nếu handshake thất bại trước HTTP, gateway có thể chỉ biết **IP peer, SNI trong giới hạn, TLS alert, listener, certificate metadata có thể quan sát và time**; không có route, user hay request ID. Ghi **event_stage=tls_handshake** thay vì tạo request ID giả hoặc suy đoán API path.

### 11.2. Không lấy CN làm service identity mặc định

Với DNS server identity, xác minh SAN theo hostname kỳ vọng. Với workload dùng SPIFFE, xác minh **URI SAN, trust domain và exact SPIFFE ID** theo authorization policy. Chỉ vì client cert được ký bởi root CA tin cậy không có nghĩa nó được phép gọi mọi API.

### 11.3. Certificate metadata trong log

Issuer, serial, fingerprint và identity SAN có thể dùng cho điều tra nhưng vẫn có thể nhạy cảm; giữ mức tối thiểu, RBAC và retention. Không log **private key, raw certificate chain không cần thiết hoặc token bảo mật** chỉ để chứng minh mTLS.

## 12. WAF, WAAP và schema validation events

WAF/API protection có thể kiểm tra HTTP method, path, header, body schema, signature, anomaly score, bot classification hoặc quy tắc tuỳ chỉnh. Tùy product, WAF đứng trước gateway hoặc tích hợp vào gateway.

### 12.1. Rule match không phải final decision

~~~json
{
  "event_type": "WAF_RULE_MATCHED",
  "request_id": "a9c31d6e5b4c4ed29cbd095a70ab8e11",
  "waf_event_id": "waf-evt-91",
  "rule_id": "waf-managed-420",
  "rule_mode": "COUNT",
  "matched": true,
  "final_disposition": "ALLOW",
  "http_status": null,
  "policy_version": "waf-v8"
}
~~~

Event trên chỉ biểu thị **điều kiện detection**. Client có thể nhận HTTP 200 từ backend sau đó. Nếu muốn đếm security blocks thực tế, lọc **final_disposition=BLOCK** tại điểm tạo quyết định, không đếm mọi match.

### 12.2. Các loại tín hiệu

| Tín hiệu | Ý nghĩa có thể có | Điều cần phân biệt |
|---|---|---|
| REQUEST_SCHEMA_INVALID | Payload không đúng OpenAPI/JSON Schema/gateway contract | Client lỗi version và dữ liệu độc hại có thể giống nhau |
| METHOD_NOT_ALLOWED | Phương thức không cho route | Gateway 405 vs backend 405 tùy thiết kế |
| BODY_SIZE_LIMIT | Body vượt giới hạn | Upload hợp lệ, client bug hoặc abuse |
| CONTENT_TYPE_MISMATCH | Content type ngoài contract | Client SDK version sai hoặc cố tạo input bất thường |
| WAF_SIGNATURE_MATCH | Mẫu request trùng rule | False positive và rule mode |
| BOT_SCORE_LOW | Engine đánh giá khả năng automation cao | Score phụ thuộc nền tảng và không phải sự thật tuyệt đối |
| SOURCE_IP_POLICY_DENY | Gateway từ chối theo nguồn đã xác minh | NAT/proxy/VPN có thể làm sai attribution nếu trust chain sai |
| REQUEST_HEADER_INVALID | Header không đúng syntax hoặc vượt giới hạn | Client bug, proxy rewrite hoặc abuse |

**Không log payload thô để phân tích signature nếu chưa có phê duyệt đặc biệt.** Một body có thể chứa mật khẩu, dữ liệu thanh toán, thông tin bệnh nhân hoặc dữ liệu khách hàng. Ưu tiên **rule ID, field name được allowlist, size, schema error code, validated route và event action**.

### 12.3. Phân biệt gateway validation với ứng dụng

Gateway kiểm tra schema giúp giảm traffic không hợp lệ, nhưng không thể thay **validation nghiệp vụ** như giá trị đặt hàng, quyền sửa object, tính nhất quán giao dịch hoặc kiểm tra dữ liệu từ dependency. Application phải ghi security events riêng khi phát hiện vi phạm ranh giới này.

## 13. Rate limit, quota và sự kiện 429

**Rate limiting** hạn chế tốc độ request trong một khoảng thời gian theo một khóa xác định, còn **quota** có thể đại diện ngân sách dài hơn theo consumer, tenant hoặc plan. Tùy policy, gateway có thể trả HTTP 429 hoặc cách báo lỗi khác.

### 13.1. Một rate-limit event nên có gì?

~~~json
{
  "event_type": "RATE_LIMIT_EXCEEDED",
  "event_time": "2026-11-28T09:05:18Z",
  "request_id": "c44a84d985454d5caa96595b7b720b6a",
  "security_control": "consumer_rate_limit",
  "rate_limit_policy": "partner-standard-v2",
  "subject_type": "verified_consumer",
  "subject_id": "partner-042",
  "window_seconds": 60,
  "limit": 120,
  "observed_count_at_decision": 121,
  "decision": "DENY",
  "http_status": 429,
  "retry_after_seconds": 30
}
~~~

Thông số giả định và **observed_count** chịu semantics của implementation, đồng hồ cửa sổ, phân tán counter và tính nhất quán giữa regions; không lấy JSON này làm hợp đồng tuyệt đối cho token bucket/sliding window của mọi hãng.

### 13.2. Khóa rate limit phải đáng tin

| Key | Khi phù hợp | Rủi ro |
|---|---|---|
| **Verified user ID** | Đã xác thực user và cần fair-use theo user | Một user có thể dùng nhiều device, cần bảo vệ privacy |
| **Verified consumer/API key alias** | API dành cho đối tác/server-to-server | Nếu key bị chia sẻ/rò rỉ, nhiều nguồn vào cùng bucket |
| **Tenant ID đã xác thực** | Quota theo tenant | Không lấy tenant từ query/header chưa kiểm tra |
| **Trusted client IP** | Request anonymous trước xác thực | NAT/CGNAT/proxy; dễ false positive |
| **Device/workload identity** | mTLS hoặc managed device | Cần tính rotation, certificate mapping |

**Không dùng X-Forwarded-For tự khai làm khóa rate limit tin cậy.** Nếu attacker đổi header để né bucket, log và enforcement cùng bị sai. Với distributed gateway, đồng bộ hoặc chia sẻ rate-limit state cần được thiết kế và giám sát.

### 13.3. 429 tăng có phải tấn công?

Chưa chắc. Có thể do mobile SDK retry sai, batch job lịch, burst sau downtime, thay quota, NAT nhiều user hoặc bot thực sự. Cần đối chiếu **route, consumer, thời điểm deploy, success rate, WAF signals và traffic baseline** trước khi chặn nguồn rộng.

## 14. Bot, enumeration, abuse và DDoS ở tầng API

API gateway/WAF có thể phát hiện dấu hiệu **credential stuffing, endpoint enumeration, scraping vượt chính sách, bot automation, request floods và abuse của token hợp lệ**. Đây là nhóm tín hiệu có **false positive** đáng kể; cần dữ liệu thống kê và business context.

### 14.1. Các mẫu thường cần điều tra

- 401/403 tăng nhanh theo **verified consumer/source context** và route.
- Nhiều request tới các route không tồn tại hoặc không thuộc danh sách client được phép.
- 429/503 tăng cùng traffic surge, latency hoặc exhausted backend connections.
- Một API key hợp lệ đột ngột xuất hiện trên nhiều khu vực/nền tảng không theo baseline.
- Một tenant dùng endpoint xuất dữ liệu với số lượng/rate ngoài ngưỡng được duyệt.
- WAF block/challenge tăng sau khi bật rule mới hoặc bot engine đổi phiên bản.
- Auth token validation error tăng đồng thời với **JWKS/IdP outage**.

**Không coi một fingerprint, IP hoặc user-agent string là định danh chắc chắn.** Mobile networks, NAT, VPN, IPv6 privacy addresses và automation hợp lệ tạo nhiều trường hợp khó phân biệt.

### 14.2. DDoS volumetric khác L7 abuse

Một sự cố băng thông/packet-per-second ở uplink có thể khiến request **không tới API gateway** nên security event count tại gateway thấp. Ngược lại, một L7 request flood có thể tạo nhiều 429/503 tại gateway dù uplink chưa nghẽn. Cần kết hợp **ISP/CDN traffic, WAF/LB, firewall flows, APIM metrics và backend SLI**.

**Gateway logs không đại diện cho gói tin đã bị chặn upstream.** Khi phân tích DDoS, xác định điểm quan sát và những traffic bị loại trước nơi log.

## 15. Trusted client IP, proxy chain và mối nguy header spoofing

Gateway thường nằm sau CDN/reverse proxy hoặc trước service mesh. Một request có thể mang **Forwarded**, **X-Forwarded-For**, **X-Real-IP**, **X-Forwarded-Proto** và các header riêng của CDN.

~~~text
Client 192.0.2.24
  -> CDN/Edge 198.51.100.10
  -> API gateway 198.51.100.20
  -> Backend 10.20.30.20

Backend socket peer thường là gateway.
Client IP chỉ được gán là trusted nếu proxy chain đã xác thực.
~~~

### 15.1. Quy tắc trust boundary

1. Xác định **socket peer** và những CDN/proxy nằm trong allowlist theo kiến trúc.
2. **Loại bỏ hoặc ghi đè** forwarded headers do client Internet tự gửi tại điểm thích hợp.
3. Khôi phục client IP qua logic **trusted proxy chain** theo sản phẩm, không mặc định chọn phần tử đầu tiên của XFF.
4. Ghi thêm **client_ip_source, trusted_hop_count/proxy_chain_version** khi hữu ích và đáng tin.
5. Giới hạn client access trực tiếp đến origin/gateway/backends bằng firewall, security group, mTLS, private endpoint hoặc tương đương.
6. Test **IPv4/IPv6, proxy protocol, NAT, failover và cloud ingress đổi kiến trúc**.

### 15.2. Hai trường IP khác nhau

- **network_peer_ip:** địa chỉ peer TCP/QUIC/TLS ở điểm log.
- **trusted_client_ip:** địa chỉ client được suy ra bằng chuỗi proxy đã xác minh, có thể null nếu không đủ bằng chứng.

Đây là phân biệt cần thiết để phát hiện spoofing và giải thích **một nguồn NAT tạo hàng nghìn 401**. Tuy nhiên IP vẫn có thể là dữ liệu cá nhân; cần RBAC và retention phù hợp.

## 16. Request ID, event ID, trace ID và WAF event ID

Một request có thể tạo nhiều security events nhưng vẫn cùng **request ID**.

~~~mermaid
flowchart TD
    R[HTTP Request ID R] --> E1[Event ID E1 / JWT VALIDATED]
    R --> E2[Event ID E2 / SCOPE DENIED]
    R --> E3[Event ID E3 / GATEWAY 403]
    R --> T[Trace ID T nếu được instrument]
    T --> S1[Span gateway]
    T --> S2[Span downstream nếu forwarded]
    E2 --> P[Policy ID + version]
~~~

| ID | Phạm vi | Quy tắc |
|---|---|---|
| **event_id** | Một event cụ thể | Sinh riêng; hỗ trợ dedup ingestion theo nguồn |
| **request_id** | Một HTTP request theo chiến lược ingress | Giữ qua các hop hoặc có mapping |
| **trace_id** | Distributed trace | Không đảm bảo mọi request có trace vì sampling/instrumentation |
| **span_id** | Một hoạt động trong trace | Không dùng một span ID cho mọi hop |
| **waf_event_id** | Sự kiện đánh giá WAF cụ thể | Không phải rule ID |
| **policy_id/rule_id** | Bộ quy tắc gây quyết định | Có thể lặp lại cho nhiều request |
| **edge_request_id** | Request ID do nhà cung cấp CDN tạo | Cần log mapping tới gateway request ID |
| **attempt_id** | Một upstream forwarding attempt | Một request có thể có nhiều attempt |

### 16.1. Sinh ID ở trusted ingress

Không tin **X-Request-ID** do client Internet tự khai. Ở điểm vào được kiểm soát, gateway/CDN có thể **sinh một ID ngẫu nhiên đủ duy nhất**, validate format, giới hạn độ dài và ghi mapping nếu vendor có ID riêng. Các hop downstream tiếp tục ID đã được tin thay vì tự ghi đè liên tục.

### 16.2. W3C Trace Context và untrusted metadata

**traceparent** chứa trace ID/parent span ID/flags theo W3C, dùng để nối distributed trace; **tracestate** và **baggage** có thể mang metadata. Tất cả có thể do client tự gửi, nên **không dùng làm bằng chứng danh tính, quyền, MFA, tenant hoặc bypass WAF**. Tại boundary, validate kích thước/cú pháp, có thể tạo trace mới theo policy; không ghi baggage chứa credential/PII.

### 16.3. Một request bị block vẫn phải có ID

Nếu security policy từ chối request **trước khi backend chạy**, log gateway/WAF vẫn nên có **request_id, event_id, policy_id, decision và final status**. Không đòi backend tạo log cho một request chưa từng được forward.

## 17. Bảo vệ bí mật, PII và dữ liệu kinh doanh trong security logs

Nhật ký bảo mật vừa là công cụ điều tra vừa là **kho dữ liệu có giá trị cao**. Nếu ghi body hoặc credential để debug, một compromise ở SIEM có thể ảnh hưởng nhiều khách hàng hơn sự cố API ban đầu.

| Dữ liệu | Nguy cơ | Cách ghi an toàn hơn |
|---|---|---|
| **Authorization: Bearer ...** | Lộ access token có thể sử dụng lại | Không log token; chỉ validation result/reason |
| **Refresh token, session cookie** | Lộ session, chiếm quyền | Không log; dùng session reference đã kiểm soát nếu cần |
| **API key, client secret** | Giả danh consumer | Log key alias/ref không nhạy cảm, không log secret |
| **Request/response body** | Mật khẩu, PII, thông tin tài chính, dữ liệu riêng | Không ghi mặc định; metadata size/schema error là đủ cho đa số sự kiện |
| **Full URL/query string** | Token, email, số đơn, dữ liệu nhạy cảm | Route template, query keys allowlisted nếu thật sự cần |
| **Raw JWT claims** | Identity/scope/tenant chưa xác thực hoặc dữ liệu cá nhân | Chỉ dùng claims sau validation, tối thiểu theo mục tiêu |
| **Client IP/device ID** | Dữ liệu cá nhân, địa điểm/sự kiện truy cập | Restrict access, retention, purpose limitation |
| **WAF matched payload/snippet** | Payload có thể chứa secret hoặc dữ liệu khách | Chỉ giữ signature/rule ID, length, field category đã làm sạch |
| **TLS certificate Subject/SAN** | Có thể tiết lộ hệ thống nội bộ/danh tính | Giữ alias/fingerprint có kiểm soát nếu cần |
| **Exception stack trace** | Đường dẫn, SQL, secret, nội dung nội bộ | Error code và stack chỉ ở vùng log hạn chế/đã redact |

**Redaction phải thực hiện càng gần nguồn càng tốt**, trước khi event vào collector hoặc kho tìm kiếm. Không chỉ dựa vào dashboard ẩn trường sau khi secret đã được lưu nguyên bản.

### 17.1. Các cấp hiển thị

- **Security telemetry vận hành:** event type, route, decision, policy, service, reason, pseudonymous actor, IP khi cần.
- **Incident investigation có phê duyệt:** metadata chi tiết hơn, evidence references và retention hạn chế.
- **Secret/raw payload:** không lưu mặc định; nếu có ngoại lệ cực hạn thì cần quy trình bảo mật độc lập, phạm vi và xóa đúng hạn.

### 17.2. Pseudonymization không mặc định là ẩn danh

Hash của email, số điện thoại hoặc user ID thuộc tập giá trị dễ đoán **có thể bị đảo qua thử nghiệm/dictionary**. Nếu cần liên kết sự kiện mà giảm lộ identity, cân nhắc **tokenization hoặc HMAC có khóa bí mật, scope, rotation và chính sách truy cập** phù hợp; bản ghi vẫn có thể là dữ liệu cá nhân theo chính sách/pháp luật áp dụng.

## 18. Log injection, dữ liệu giả và tính toàn vẹn của audit trail

Security events không chỉ đến từ hệ thống đáng tin. Nhiều trường như URL path, User-Agent, request header và thậm chí một phần lỗi JSON có thể bắt nguồn từ **client không đáng tin**. Nếu nối raw value thành dòng log, attacker có thể tạo **newline, control characters, ký tự phá JSON hoặc chuỗi gây nhầm parser**.

### 18.1. Quy tắc xử lý đầu vào

1. **Không dùng string concatenation để tạo JSON log**; dùng serializer đảm bảo escaping đúng.
2. **Giới hạn chiều dài và charset** của request ID, trace context, header name/value và các field lấy từ request.
3. Chuẩn hóa **route template** từ router config thay vì ghi path động chứa thông tin khách hàng.
4. Chuyển **reason code** về enum do server chọn; không đưa raw exception message vào lý do an ninh hiển thị công khai.
5. Nếu cần giữ giá trị chưa được tin, đặt vào **raw_untrusted_context** trong vùng lưu hạn chế, không dùng để join actor/quyết định.
6. Không dùng request header làm **index name, table name, metric label hoặc lệnh truy vấn SIEM**.

### 18.2. Chống sửa/xóa log

| Biện pháp | Mục tiêu | Giới hạn |
|---|---|---|
| **mTLS/IAM giữa producer–collector** | Xác thực nguồn gửi log | Không tự bảo đảm producer đã ghi sự thật |
| **Append-only/immutable retention** | Giảm khả năng thay hoặc xóa event đã lưu | Cần kiểm soát quyền admin và chính sách retention |
| **Checksum/signature/sequence khi thiết kế** | Hỗ trợ phát hiện mất/sửa chuỗi event | Không thay kiểm tra nguồn và clock |
| **Phân quyền ghi/đọc/xóa riêng** | Giảm blast radius | Chính sách IAM phải được audit liên tục |
| **Centralization ngoài gateway node** | Tránh mất log khi node hỏng/compromise | Có thể trễ hoặc mất nếu pipeline quá tải |
| **Config/audit log độc lập** | Truy được ai tắt security logging | Nếu admin có quyền cả hai hệ sẽ còn rủi ro |
| **Retention + legal hold theo nhu cầu** | Giữ bằng chứng đúng thời gian | Không phải giữ vô hạn mọi PII |

**Bản ghi đã được ký không chứng minh nguồn dữ liệu đầu vào là thật.** Nếu gateway nhận X-Forwarded-For giả rồi ghi vào log đã ký, chữ ký chỉ chứng minh record không đổi, không chứng minh địa chỉ do client tự khai là đáng tin.

### 18.3. Giám sát chính việc logging

Tắt, giảm hoặc làm mất log security events phải được xem là **sự kiện vận hành bảo mật**. Theo dõi cấu hình logging, agent/collector health, số event/second, queue depth, dropped count, ingestion lag và thay đổi quyền ghi log.

## 19. Dòng thời gian: event time, ingest time và đồng hồ phân tán

Một event có thể phát ở gateway tại **09:05:14 UTC**, nhưng collector chỉ nhận lúc **09:05:22 UTC** do queue/retry. IdP có thể ghi token revoke tại một region khác, WAF ghi request blocked sớm hơn và backend gửi log trễ hơn. Nếu phân tích chỉ theo thời gian nhập kho, SOC có thể đảo ngược nguyên nhân/kết quả.

| Khái niệm | Ý nghĩa | Tránh nhầm |
|---|---|---|
| **event_time** | Thời điểm producer cho biết event xảy ra | Đồng hồ nguồn có thể lệch |
| **ingest_time** | Lúc hệ thống nhận/đọc được event | Pipeline latency không phải thời gian xử lý request |
| **request_start_time** | Lúc gateway nhận request | Không đồng nghĩa lúc app bắt đầu |
| **decision_time** | Lúc security check đưa ra quyết định | Có thể có nhiều quyết định trong một request |
| **response_complete_time** | Lúc gateway hoàn tất response/log | Có thể sau backend log hoặc lâu với streaming |
| **duration_ms** | Khoảng thời gian do một hop đo | Nên lấy monotonic timer tại cùng process khi có |

### 19.1. NTP và cửa sổ tương quan

- Đồng bộ thời gian NTP/chrony hoặc hệ thống phù hợp, theo dõi offset và lỗi nguồn thời gian.
- Ghi timezone rõ ràng (UTC hoặc ISO 8601 có offset).
- Với correlation đa region, dùng **request ID/trace/span + causal relationships**; thời gian chỉ là một tín hiệu bổ sung.
- Cửa sổ phân tích có thể phải cho phép **late arrivals và clock skew**, tránh đánh mất event khi hệ thống vừa failover.
- Ghi **event/ingest latency** để phát hiện pipeline chậm và đánh giá độ tin cậy của cảnh báo real-time.

### 19.2. Một request nhiều lần kiểm tra

~~~text
09:05:14.100 Gateway nhận request R
09:05:14.104 JWT validation SUCCESS (event E1)
09:05:14.107 Route authorization DENY (event E2)
09:05:14.109 Gateway trả 403 (access event E3)
09:05:14.450 Collector nhận E2
09:05:14.610 Collector nhận E1
09:05:15.010 Collector nhận E3

Không sắp xếp E1/E2 chỉ theo ingest_time để suy ra quyết định.
~~~

## 20. Control-plane audit events: policy, secrets và vai trò quản trị

Không ít sự cố API đến từ **thay đổi cấu hình hợp lệ về mặt cú pháp nhưng sai phạm vi**: một admin chuyển WAF từ BLOCK sang COUNT, cập nhật route ACL sang allow-all, xóa rate limit cho đối tác hoặc thêm một CA/trust bundle không đúng.

### 20.1. Audit record phải khác data-plane request

~~~json
{
  "schema_version": "1.0",
  "event_id": "audit-8c6f",
  "event_time": "2026-11-28T09:10:01Z",
  "event_type": "SECURITY_POLICY_CHANGED",
  "event_domain": "control_plane",
  "gateway_id": "api-gw-cluster",
  "actor_type": "verified_admin",
  "actor_id": "admin-pseudonym-17",
  "actor_authn_method": "sso_mfa",
  "change_id": "chg-demo-104",
  "resource_type": "waf_policy",
  "resource_id": "orders-waf",
  "before_version": "v8",
  "after_version": "v9",
  "change_summary": "rule action changed",
  "approval_ref": "approved-change-demo",
  "result": "APPLIED"
}
~~~

Đây là JSON minh họa. **Không ghi API secret, private key, policy token hoặc config có secrets ở trạng thái before/after**. Nếu phải lưu diff, tách dữ liệu an toàn khỏi secrets và quản lý quyền chi tiết.

### 20.2. Những thay đổi phải audit

| Sự kiện | Nguy cơ | Liên kết cần có |
|---|---|---|
| Thay API route/auth mode | Bypass AuthN/AuthZ | Change ID, review, old/new policy version |
| WAF chuyển BLOCK → COUNT | Request độc hại không còn bị chặn | Rule ID, reason, owner, expiry |
| Tắt rate limit | Abuse vượt quota | Consumer group, route, change window |
| Thêm JWT issuer/audience | Token từ bên khác có thể được tin | Verified admin, validation policy version |
| Thêm CA/trust bundle mTLS | Mở rộng danh tính có thể được xác nhận | Scope, approval, rollback |
| Tạo/rotate/revoke API key | Tiếp tục hoặc cắt quyền consumer | Key alias, consumer owner, effective time |
| Cập nhật logging config | Mất visibility sự kiện bảo mật | Who/when, pipeline heartbeat, canary |
| Đổi IAM/permission quản trị | Tăng quyền thay chính sách | Admin IAM audit, MFA, approval |
| Cấu hình fail-open/fail-closed | Thay behavior khi dependency down | Service SLO, risk acceptance, rollback |

**Không dùng event từ data plane để thay một audit trail do control plane ký/ghi riêng**. Nếu người vận hành tắt security check, event "ALLOW" có thể biến mất và không nêu được ai đã tắt.

## 21. Pipeline thu thập log, độ tin cậy và xử lý lỗi

~~~mermaid
flowchart LR
    G[Gateway Pods / Instances] --> F[Local Agent / Forwarder]
    W[CDN / WAF Logs] --> F2[Vendor Export / Connector]
    A[IdP / Admin Audit] --> F3[Audit Export]
    F --> Q[Buffer / Queue]
    F2 --> Q
    F3 --> Q
    Q --> V[Parser / Schema Validation / Redaction]
    V --> S[SIEM Search + Immutable Archive]
    Q -. Queue depth / drops .-> H[Pipeline Health]
    V -. Parse/reject counts .-> H
    S -. Ingest lag / access audit .-> H
~~~

### 21.1. Vì sao logging pipeline cần kiến trúc riêng?

Một API gateway phục vụ hàng chục nghìn request/giây có thể tạo khối lượng event lớn. **Ghi đồng bộ từng event trực tiếp vào SIEM** trên đường trả response sẽ tăng latency và làm phụ thuộc availability của gateway vào log backend. Ngược lại, đẩy event hoàn toàn bất đồng bộ không có buffer/health sẽ làm mất dữ liệu khi node hỏng.

Thiết kế cần cân bằng:

1. **Availability:** request chính không bị treo do collector chậm trong chế độ vận hành được phê duyệt.
2. **Audit integrity:** những security events quan trọng không bị mất âm thầm.
3. **Backpressure:** buffer và queue depth có giới hạn, giám sát dropped events.
4. **Security:** producer–collector transport được xác thực/mã hóa theo ranh giới.
5. **Privacy:** redaction, RBAC, retention và region restrictions trước/tại storage.
6. **Recovery:** có replay/idempotent ingest, dedup khi collector retry và runbook khi storage unavailable.

### 21.2. Không hứa exactly-once nếu nền tảng không hỗ trợ

Một collector có thể retry gửi một batch sau timeout. Hệ SIEM nhận **bản ghi trùng**; ngược lại việc gateway crash trước khi flush có thể tạo **event missing**. Cần **event_id, source_id, sequence/offset khi có, duplicate-detection và telemetry coverage**. Không mặc định mọi hệ thống log có exactly-once semantics.

### 21.3. Security check fail-open vs logging fail-open

Đây là **hai quyết định độc lập**:

- Nếu **JWT validator/authorization provider** unavailable, chính sách truy cập có thể từ chối để tránh cấp quyền khi chưa xác minh hoặc dùng phương án được thiết kế rõ.
- Nếu **log exporter** unavailable, việc gateway tiếp tục xử lý hay ngừng nhận request phải theo **audit requirements, regulatory constraints, criticality và risk acceptance**, không tự dùng cùng một rule cho mọi hệ.

Phải ghi nhận **dạng lỗi, hành vi thực và thời gian diễn ra**. Không tự coi "log pipeline down" là lý do cho phép mọi request vượt AuthN/ACL.

## 22. Cloud, multi-region, serverless và dịch vụ quản lý

API gateway có thể chạy on-prem, Kubernetes, managed cloud gateway hoặc phối hợp CDN/WAF cloud. Mỗi môi trường có nguồn log và phạm vi kiểm soát khác nhau.

### 22.1. Ma trận triển khai

| Môi trường | Nguồn security event | Rủi ro nổi bật |
|---|---|---|
| **Self-hosted Nginx/Envoy gateway** | Access/error logs, auth plugins, filter decisions, sidecar | Config logging không nhất quán, log node mất khi container bị xóa |
| **Kubernetes ingress/API gateway** | Proxy logs, controller audit, policy CRD changes | Pod churn, context propagation, namespace trust |
| **Managed API gateway cloud** | Provider access/execution/audit logs, WAF, IAM | Field/retention/coverage phụ thuộc dịch vụ/tier |
| **Multi-region CDN/WAF** | Edge request IDs, WAF actions, geo/POP/region, sampled logs | Clock skew, rule version drift, vendor log delays |
| **Serverless API** | API gateway decision và function logs | Cold start, invocation ID, backend log thiếu khi chặn ở gateway |
| **VPN/private endpoint API** | VPN/IAM logs, private DNS, mTLS, gateway authorization | Khó xác định original actor nếu mọi request qua NAT |
| **Service mesh** | mTLS identity, policy deny, Envoy access logs, distributed spans | Không phải mọi service đều nằm trong mesh hoặc ở strict mTLS |

**Không khẳng định một cloud vendor luôn xuất đầy đủ log identity/raw payload**. Tên trường, tính năng bật/tắt, quota và sampling có thể khác theo product/version. Khi triển khai, dùng tài liệu vendor hiện hành, ghi rõ log source, version và những quyết định chỉ backend mới biết.

### 22.2. Data residency và tenant isolation

Khi logs từ nhiều region/tenant về một SIEM, cần đánh giá **quyền truy cập xuyên vùng, chính sách lưu trữ, thông tin cá nhân và log ownership**. Một security analyst không mặc nhiên được xem mọi yêu cầu của mọi tenant chỉ vì có quyền tìm request ID.

### 22.3. Multi-region consistency

Một policy mới có thể được áp ở region A trước region B. Event cần có **gateway/region/config_revision**, giúp SOC phân biệt một chiến dịch tấn công với **configuration drift**. Kiểm tra cả IPv4/IPv6, primary/failover và các edge POP khác nhau.

## 23. HTTP, gRPC, GraphQL, WebSocket và sự kiện bảo mật khác biệt

### 23.1. HTTP status không luôn phản ánh ứng dụng

Gateway trả 200 chỉ nói HTTP layer đã trả thành công theo semantics của lớp đó. Có thể backend trả lỗi nghiệp vụ trong body, hoặc một API gateway trả 200 từ cache mà backend không tham gia. Khi cần security monitoring, phải ghi **decision_source** và application outcome riêng.

### 23.2. gRPC

Nhiều gRPC calls dùng HTTP/2 status 200 và mã lỗi thực tế nằm ở **grpc-status** trong trailers. Security event nên tách:

~~~json
{
  "event_type": "AUTHZ_DENIED",
  "protocol": "grpc",
  "rpc_service": "orders.v1.OrdersService",
  "rpc_method": "CreateOrder",
  "http_status": 200,
  "grpc_status": "PERMISSION_DENIED",
  "decision_source": "gateway_grpc_authz"
}
~~~

Đây là **ví dụ thiết kế log**; không áp cứng rằng mọi gRPC unauthorized request luôn trả HTTP 200 — một gateway có thể chặn ngay ở HTTP/TLS layer mà không tạo đầy đủ gRPC exchange.

### 23.3. GraphQL

GraphQL thường dùng một HTTP endpoint như **POST /graphql**, bên trong có nhiều field/operation. Nếu chỉ nhóm theo HTTP route, SOC không nhìn thấy những permission khác nhau ở resolver.

Nên ghi **operation name hoặc operation type đã được chuẩn hóa**, query complexity/cost, authorization decisions và resource category. Không mặc định log toàn bộ **GraphQL query/variables** vì có thể chứa ID khách hàng, token hoặc dữ liệu nhạy cảm. Persisted queries/operation allowlist có thể hỗ trợ giảm rủi ro và cardinality.

### 23.4. WebSocket và streaming

Khi upgrade WebSocket, gateway có thể ghi handshake 101 rồi kết nối kéo dài. Các security checks có thể diễn ra ở **handshake**, trong từng message hoặc ở backend; nếu chỉ có access log khi kết nối đóng, incident khó thấy thời điểm vượt quyền.

Thiết kế **connection/session ID, authenticated principal, message action category, policy decision, close reason, duration và sampling/redaction** phù hợp. Không ghi toàn bộ WebSocket payload mặc định.

### 23.5. SSE, HTTP/3 và non-browser clients

SSE/streaming có response dài, còn HTTP/3/QUIC dùng cách multiplexing khác TCP HTTP/1.1. Không coi connection 5-tuple là request identity duy nhất. Một số client SDK không tự gửi trace headers; gateway vẫn cần tạo **request ID đáng tin** và có log đủ để tìm request.

## 24. Tương quan gateway, WAF, IdP, backend và firewall

Mục tiêu không phải nhét mọi log vào một record khổng lồ mà là xây **khóa nối và mối quan hệ được chứng minh**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant E as Edge / WAF
    participant G as API Gateway
    participant I as Identity Provider
    participant A as Backend
    participant S as SIEM
    C->>E: Request
    E->>G: Request ID R + trusted metadata
    G->>I: Validate/introspect if policy requires
    I-->>G: Identity/validation result
    G->>G: AuthN/Route AuthZ/Rate/WAF decision
    G->>A: Forward R if ALLOW
    A-->>G: App response / business AuthZ
    E-->>S: edge_id ↔ R, final edge outcome
    G-->>S: security event_id + R + policy + final disposition
    I-->>S: token/IdP audit metadata
    A-->>S: R + app event + trace/span
~~~

Sơ đồ mô tả request **được cho phép tới backend**; với WAF BLOCK hoặc AuthN DENY, có thể không có bước tới backend. Với JWT tự xác minh offline, gateway **không nhất thiết gọi IdP trên mỗi request**, nên SIEM không được đòi một IdP event tương ứng cho tất cả các request hợp lệ.

### 24.1. Tại sao không chỉ join theo client IP?

Một IP sau **NAT, CDN, VPN hoặc mobile carrier** có thể phục vụ nhiều người, trong khi một user có thể đổi IP giữa các request. Đối chiếu ưu tiên **request_id/trace_id, verified actor/tenant, exact time, endpoint và event source**; IP là ngữ cảnh bổ sung.

### 24.2. Correlation gap không luôn là lỗ hổng

- **WAF BLOCK** → không có backend log là đúng.
- **CDN cache HIT** → không có origin request là bình thường.
- **JWT offline verification** → không có IdP lookup theo request.
- **Trace sampling** → không có span không đồng nghĩa không có request.
- **Ingestion lag/outage** → event đến muộn hoặc thiếu cần điều tra telemetry health.

**Không tự tạo event backend giả** để lấp chuỗi; hãy ghi lý do thiếu và mức độ chắc chắn của phân tích.

## 25. Truy vấn SIEM để điều tra security events

Các ví dụ dưới dùng bảng giả định **normalized_api_security_events** và SQL khái niệm; cần chỉnh cú pháp/timestamp functions, index, IAM và field mapping theo hệ kho log thực. Chỉ truy vấn dữ liệu thuộc phạm vi đã được phép.

### 25.1. Tìm chuỗi theo request ID

~~~sql
SELECT event_time, ingest_time, event_id, event_type,
       gateway_id, region, security_control,
       request_id, actor_id, decision, final_disposition,
       reason_code, policy_id, policy_version, http_status
FROM normalized_api_security_events
WHERE request_id = 'a9c31d6e5b4c4ed29cbd095a70ab8e11'
ORDER BY event_time, event_id;
~~~

Nếu không thấy event từ backend, xem **final_disposition, cache_status, upstream_attempt_count** trước khi cho rằng log bị mất.

### 25.2. Đếm AuthN failures theo route và reason

~~~sql
SELECT route_template, reason_code, gateway_id,
       COUNT(*) AS failure_events
FROM normalized_api_security_events
WHERE event_time >= TIMESTAMP '2026-11-28 09:00:00'
  AND event_time <  TIMESTAMP '2026-11-28 10:00:00'
  AND event_type = 'AUTHN_FAILED'
GROUP BY route_template, reason_code, gateway_id
ORDER BY failure_events DESC;
~~~

**COUNT(*) ở đây đếm events, không nhất thiết đếm client requests duy nhất**. Nếu gateway tạo nhiều events cho cùng request, cần distinct request_id hoặc dedup theo event_id/schema. Nếu pipeline duplicate events do retry, phải xử lý tại ingest hoặc trong query.

### 25.3. Phân biệt WAF match và block

~~~sql
SELECT rule_id, policy_version, final_disposition,
       COUNT(DISTINCT request_id) AS request_count
FROM normalized_api_security_events
WHERE event_type = 'WAF_RULE_MATCHED'
  AND event_time >= TIMESTAMP '2026-11-28 09:00:00'
GROUP BY rule_id, policy_version, final_disposition
ORDER BY request_count DESC;
~~~

**Không tổng các rule counts rồi suy ra tổng requests:** một request có thể match nhiều rules. Cũng phải xem field **final_disposition** có được log ở event match hay cần join với gateway decision event.

### 25.4. Kiểm tra sự thay đổi chính sách trước khi tăng 403

~~~sql
SELECT event_time, actor_id, resource_id,
       before_version, after_version, change_id, result
FROM normalized_gateway_admin_audit
WHERE event_type = 'SECURITY_POLICY_CHANGED'
  AND event_time >= TIMESTAMP '2026-11-28 08:00:00'
  AND event_time <  TIMESTAMP '2026-11-28 10:00:00'
ORDER BY event_time;
~~~

Đối chiếu với events data-plane theo **policy_version + gateway/region + event_time**; đừng mặc định một thay đổi đã triển khai đồng thời trên mọi POP/gateway instance.

### 25.5. Kiểm tra ingestion lag

~~~sql
SELECT gateway_id, region,
       COUNT(*) AS events_received,
       MAX(ingest_time) AS latest_ingest
FROM normalized_api_security_events
WHERE ingest_time >= TIMESTAMP '2026-11-28 09:00:00'
GROUP BY gateway_id, region;
~~~

Query này chỉ là một phần của health check. Khi **producer hoàn toàn không gửi event**, không có row trong bảng không tự chỉ ra nguyên nhân; phải dùng **heartbeat, expected traffic/control events và exporter health metrics** độc lập.

## 26. Detection engineering: từ event tới cảnh báo có căn cứ

Một detection rule tốt thường có:

1. **Mục tiêu cụ thể:** cảnh báo điều gì (ví dụ token validation failures đột biến, revoke key dùng lại, gateway policy chuyển chế độ trái phép)?
2. **Nguồn sự kiện và coverage:** nguồn nào đủ tin, region/gateway nào chưa gửi?
3. **Đơn vị nhóm:** verified consumer, tenant, actor, route hoặc trusted IP tùy loại hành vi.
4. **Baseline/threshold:** theo lượng request hợp lệ, giờ trong ngày, workload và kỳ vọng.
5. **Exclusions có owner và expiry:** deployment, health check, canary hoặc pentest có phép.
6. **Output:** severity, evidence IDs, time window, triage guidance và confidence.
7. **Validation:** replay dữ liệu đã làm sạch/lab event, đo precision/recall hợp lý.

### 26.1. Một số giả thuyết phát hiện

| Detection | Dữ liệu chính | Giải thích khác cần loại trừ |
|---|---|---|
| **401 spike** | AUTHN_FAILED theo route/consumer/time | Token hết hạn hàng loạt, SDK lỗi, clock skew |
| **Unknown JWKS kid surge** | TOKEN_KID_UNKNOWN + validator health | Signing key rotation chưa đồng bộ |
| **403 spike** | AUTHZ_DENIED theo policy_version/gateway | Deploy rule mới, thay IAM scopes |
| **WAF BLOCK surge** | final_disposition BLOCK, rule_id, route | Managed rule update gây false positive |
| **API key reused unusually** | Verified consumer, region/device context | Traffic chạy qua multi-region/VPN đúng thiết kế |
| **Rate-limit exceed burst** | RATE_LIMIT_EXCEEDED, quota subject, response | Batch hợp lệ, app retries, NAT shared |
| **Scope expansion** | Admin audit change to allow/mode | Change đã được phê duyệt và có expiration |
| **Logging gap** | heartbeat, expected traffic, ingest lag, dropped events | Collector maintenance/outage hoặc route không phát request |
| **mTLS identity mismatch** | CLIENT_CERT_REJECTED, trust domain, route | CA migration/trust bundle drift |
| **Export API anomaly** | Verified user/tenant, export count, data classification | Báo cáo định kỳ được owner duyệt |

### 26.2. Mẫu cảnh báo chuẩn hóa

~~~json
{
  "alert_id": "alert-1048",
  "detector": "authn_failure_spike",
  "severity": "medium",
  "confidence": "moderate",
  "window_start": "2026-11-28T09:00:00Z",
  "window_end": "2026-11-28T09:05:00Z",
  "source": "api-gateway-security-events",
  "grouping": {
    "route": "/v1/orders",
    "gateway_region": "region-a"
  },
  "reason_distribution": {
    "TOKEN_EXPIRED": 110,
    "TOKEN_SIGNATURE_INVALID": 6
  },
  "policy_version": "jwt-v3",
  "triage_note": "Check token refresh deployment and IdP/JWKS health",
  "sample_event_ids": ["evt-101", "evt-102"]
}
~~~

Mọi số trong JSON chỉ minh họa. **Token expired spike** có thể là lỗi ứng dụng hàng loạt, không phải bằng chứng attacker. Alert nên mô tả **giả thuyết và độ tin cậy**, không ghi kết luận chắc chắn trước điều tra.

## 27. False positive, false negative và giới hạn nhìn thấy

### 27.1. False positive

- Quản trị viên bật WAF rule mới làm tăng block ở khách hợp lệ.
- Client cũ gửi JWT thiếu audience theo validation policy mới.
- NAT nhiều người làm source-IP rate limit nhầm một nhóm.
- Batch upload tăng content-size rejects nhưng không phải tấn công.
- Đổi routing/failover làm event volume khác giữa gateway instances.

### 27.2. False negative

- Backend có **đường direct-to-origin**, request không qua gateway.
- Security logging bị tắt ở một instance/route, collector drop events.
- Gateway chỉ ghi 5xx mà không log authz denials hoặc admin changes.
- WAF match ở chế độ COUNT nhưng detection dashboard chỉ đếm BLOCK.
- Payload/API abuse xảy ra sau gateway tại object-level, gateway không đủ ngữ cảnh.
- Tracing sampling khiến chuỗi span không có, trong khi gateway event vẫn tồn tại.

### 27.3. Độ phủ logging phải đo được

Không nên đặt mục tiêu "100% requests có trace đầy đủ" nếu sampling đã được chọn theo thiết kế. Thay vào đó:

- **Data-plane security decisions trọng yếu** phải có logging theo mức độ yêu cầu/coverage được cam kết.
- **Control-plane changes** phải có audit trail độc lập.
- **Traces và access logs** bổ sung cho phân tích nhân quả/latency, có thể sampling theo policy.
- **Heartbeat/agent metrics** cần cho biết chỗ không phát ra event, không chỉ dựa vào tổng số events.

**Ít sự kiện DENY không có nghĩa hệ thống an toàn hơn**; có thể do traffic ít, rules sai hoặc không có logging.

## 28. Pseudocode policy: log events tại API gateway

Ví dụ mô tả **ý định chính sách**, không phải cấu hình chạy trực tiếp cho Kong, Envoy, Nginx, Apigee, AWS API Gateway, Azure API Management hoặc dịch vụ cloud khác.

~~~yaml
api_gateway_security_logging:
  schema_version: "1.0"
  owner: "Network Security / API Platform"
  environment: "production"
  trusted_entrypoint:
    generate_or_validate_request_id: true
    ignore_untrusted_client_identity_headers: true
    trusted_proxy_configuration_required: true

  security_events:
    authentication:
      include: ["AUTHN_FAILED", "AUTHN_SUCCEEDED"]
      reasons: ["MISSING", "EXPIRED", "INVALID_SIGNATURE", "BAD_ISS", "BAD_AUD"]
    authorization:
      include: ["AUTHZ_DENIED", "AUTHZ_GRANTED"]
      attach_policy_version: true
    mtls:
      include: ["CLIENT_CERT_REJECTED"]
      log_certificate_metadata_only: true
    waf:
      include: ["WAF_RULE_MATCHED"]
      record_matched_rule_and_final_disposition: true
    throttling:
      include: ["RATE_LIMIT_EXCEEDED"]
      verified_consumer_bucket: true
    schema_validation:
      include: ["REQUEST_SCHEMA_INVALID"]
      store_request_body: false
    control_plane:
      include: ["SECURITY_POLICY_CHANGED", "API_KEY_REVOKED"]
      independent_audit_export: true

  required_context:
    - "event_id"
    - "event_time"
    - "gateway_id"
    - "event_type"
    - "decision"
    - "reason_code"
    - "policy_id"
    - "policy_version"
  optional_context:
    - "request_id"
    - "trace_id"
    - "verified_actor_id"
    - "verified_tenant_id"
    - "trusted_client_ip"
    - "route_template"
    - "http_status"

  privacy:
    allow_request_body_logging: false
    forbid_authorization_header: true
    forbid_cookie_and_api_key: true
    forbid_raw_jwt_and_refresh_token: true
    sanitize_untrusted_fields: true
    redact_before_export: true

  delivery:
    encrypted_authenticated_transport: true
    buffer_with_bounded_retention: true
    deduplicate_by_event_id_when_possible: true
    monitor_drops_and_ingestion_lag: true
    destination: "approved-security-telemetry-store"

  governance:
    access_control: "role-and-tenant-scoped"
    auditable_policy_changes: true
    retention: "approved-by-data-governance"
    negative_security_tests_required: true
    rollback_plan_required: true
~~~

**Không sao chép pseudocode vào production.** Mỗi nền tảng có định nghĩa field, mức logging, quyền bật event, dữ liệu có thể thấy khi TLS chưa hoàn tất và chi phí khác nhau. Phải map tới đúng **vendor/version**, xác minh raw output, làm sạch dữ liệu và kiểm tra performance.

## 29. Dashboard và chỉ số SLO cho security logging

Dashboard tốt phải cho biết **API gateway có đang bảo vệ đúng không**, **người dùng hợp lệ có bị ảnh hưởng không** và **pipeline giám sát có còn đủ dữ liệu để kết luận không**.

### 29.1. Các nhóm biểu đồ gợi ý

| Nhóm | Metric gợi ý | Cách diễn giải |
|---|---|---|
| **AuthN** | AUTHN_FAILED/s theo reason, route, region | Cần baseline; token expired surge có thể do SDK lỗi |
| **AuthZ** | AUTHZ_DENIED/request theo policy/role | Tăng sau policy deploy có thể là misconfiguration |
| **WAF** | Rule matches, final BLOCK/CHALLENGE/COUNT | Không nhầm rule matched với request blocked |
| **Rate limiting** | Throttle count, 429 rate, bucket utilization | Phân biệt bot/abuse và quota không phù hợp |
| **TLS/mTLS** | Invalid client cert, unknown CA, handshake failure rate | Theo certificate rotation và trust store changes |
| **Config audit** | Security policy changes theo actor/route/change window | Cảnh báo thay đổi ngoài approval |
| **Availability** | Gateway 5xx, auth dependency failures, latency p95/p99 | Kiểm soát bảo mật không được làm outage ngoài mong đợi |
| **Logging health** | Event ingestion lag, parser rejects, queue depth, drops | Ít events có thể do thiếu telemetry |
| **Identity coverage** | % decisions có verified_actor/consumer khi kỳ vọng | Anonymous events hợp lệ vẫn tồn tại trước AuthN |
| **Correlation coverage** | % eligible request có request ID, policy ID, source | Không mặc định TLS handshake đã có HTTP request ID |

### 29.2. Tỷ lệ lỗi phải có mẫu số đúng

Ví dụ **tỷ lệ request bị WAF BLOCK** nên tính trên tập **request thực được WAF đánh giá** trong khoảng đo, không chia trên tổng số **rule match events** nếu một request có nhiều matches. Với tỷ lệ 401, phải xác định đó là **gateway final responses**, không đơn thuần số authentication checks. Dashboard cần nêu **định nghĩa metrics**.

### 29.3. Metrics không nên chứa request_id/user_id làm nhãn

**request_id, trace_id, raw URL, user ID, token ID hoặc unbounded client IP** có độ đa dạng cao, gây nổ cardinality trong Prometheus/monitoring. Dùng các nhãn được kiểm soát như **service, route template, region, event_type, reason_code, status class, policy family**; tra định danh cụ thể trong logs/traces với RBAC.

### 29.4. Kiểm tra counter trên nhiều instance

Một region có nhiều gateway instances có thể ghi cùng một request ở nhiều lớp/hops hoặc nhiều retries. Đừng cộng tất cả event counts rồi gọi đó là "số client requests". Lấy số request ở **điểm ingress được xác định**, hoặc dedup theo khóa đã thiết kế.

## 30. Chẩn đoán an toàn và kiểm chứng log tại API gateway

Các thao tác bên dưới dành cho **endpoint và log được tổ chức quản lý**, không dùng với khách hàng/địa chỉ bên ngoài khi chưa được phép. Không tạo brute force, spam rate limit hay cố vượt WAF trong production.

### 30.1. Đọc response metadata

~~~bash
# Kiểm tra response HTTPS của một endpoint kiểm thử được cấp phép.
# Thay hostname/path bằng tài sản thuộc test plan.
curl --silent --show-error --head \
  https://api.example.com/health

# Xem response headers và status code, không gửi credential.
curl --silent --show-error --output /dev/null \
  --dump-header - https://api.example.com/health
~~~

**Lưu ý:** response header **X-Request-ID** nếu có có thể hỗ trợ user báo ticket, nhưng nó **không chứng minh security event đã được ghi hoặc backend đã xử lý**. Chỉ kiểm tra thông qua SIEM/gateway log với quyền phù hợp.

### 30.2. Đọc log JSON đã được làm sạch

~~~bash
# File dưới đây là bản xuất security events đã được phê duyệt và redacted.
# Không tạo hay xuất log chứa token/cookie để chạy ví dụ này.
jq -c 'select(.event_type == "AUTHZ_DENIED") |
  {event_time, event_id, request_id, reason_code,
   policy_id, gateway_id, final_disposition}' \
  sanitized-api-security-events.jsonl
~~~

Đây là **lệnh chỉ đọc** trên file JSON Lines được phép truy cập, không có tác dụng sửa policy. Nếu log là định dạng khác, cần điều chỉnh parser; một JSONL record lỗi phải được xử lý như **parse error** thay vì bỏ qua âm thầm.

### 30.3. Với Kubernetes hoặc managed gateway

Không nên mặc định đọc raw pod logs là đủ: gateway có thể ghi **decision events** vào một audit exporter riêng. Khi truy vấn controller/cluster, phải tách **application logs, ingress proxy logs, policy CRD/audit events và service mesh deny logs**. Dùng công cụ read-only phù hợp RBAC; không mở rộng quyền service account hoặc bật debug payload logging toàn cluster chỉ để khắc phục một ticket.

### 30.4. Bằng chứng tối thiểu cho một quyết định

Một case "API bị 403" nên có **gateway final status, decision_source, security event ID, policy/rule ID, request ID, timestamp, auth context đã xác minh, upstream_attempt_count và backend status nếu thực sự có upstream**. Nếu thiếu, ghi rõ **không đủ bằng chứng** thay vì khẳng định request bị WAF hay bị backend từ chối.

## 31. Runbook triển khai security event logging

### Bước 1 — Inventory và threat model

Liệt kê gateway, CDN/WAF, backend, IdP, rate limiter, mTLS terminator, cloud regions, log exporters, kho SIEM, kết nối VPN/private endpoint, route public/private. Xác định ranh giới mạng và **đường direct-to-origin** có thể bỏ qua gateway.

### Bước 2 — Phân loại sự kiện cần ghi

Chọn AuthN/AuthZ, JWT/mTLS/API key, WAF, quota, schema validation, gateway fail-open/closed và control-plane changes. Với mỗi event, xác định **owner, impact, criticality, retention và điều tra cần trường nào**.

### Bước 3 — Thiết kế schema và trust boundary

Xác định **event_id/request_id/trace_id**, source của client IP, scope identity/tenant, policy IDs, reason codes, event vs ingest timestamp và schema version. Thiết kế log **null** cho dữ liệu chưa có, không tự điền actor từ token chưa được xác thực.

### Bước 4 — Bảo vệ dữ liệu và đường vận chuyển

Thiết lập **redaction trước export**, transport được xác thực/mã hóa, collector IAM, RBAC theo vai trò, retention, storage region, immutable archive khi có yêu cầu và audit truy vấn. Không bật raw request/response logging trong production như một mặc định.

### Bước 5 — Instrument và kiểm thử ở staging

Thử request allow, thiếu token, token expired trong lab, thiếu scope, WAF COUNT/BLOCK, rate limit nhỏ dành riêng test, mTLS mismatch, JWKS outage mô phỏng và admin policy change. Kiểm tra **event type, decision source, reason, HTTP status, upstream/no-upstream**.

### Bước 6 — Kết nối SIEM và đo mất dữ liệu

Chuẩn hóa field mapping, dedup, event/ingest time, parse-error handling, drop counters và producer heartbeat. Tạo truy vấn mẫu theo request_id, reason_code, policy_version và test RBAC cho analyst/tenant.

### Bước 7 — Canary và rollout có rollback

Áp dụng từng service/region/route. Đo gateway p95/p99 latency, collector load, disk/buffer, event counts, ingest lag, auth availability và ảnh hưởng người dùng. Nếu logging gây gián đoạn, rollback theo policy đã duyệt nhưng vẫn phải **giữ các quyết định AuthN/AuthZ/WAF**.

### Bước 8 — Regression và audit định kỳ

Kiểm tra lại khi thay JWT issuer/JWKS, WAF rules, quota, plugin/gateway version, DNS/TLS, ingress, cloud region, failover hoặc authorization layer. Review quyền xem log, retention và thay đổi schema/cấu hình.

~~~mermaid
flowchart TD
    A[Inventory entrypoints + policy owners] --> B[Event taxonomy + schema]
    B --> C[Trusted identity + redact secrets]
    C --> D[Instrument gateway/WAF/IdP/audit]
    D --> E[Exporter + collector + SIEM + health]
    E --> F[Staging allow/deny/config tests]
    F --> G{Event correct, privacy clean, no pipeline loss?}
    G -- No --> H[Fix schema/headers/exporter; retry tests]
    H --> D
    G -- Yes --> I[Canary production rollout]
    I --> J[Dashboards, alerts, regression, audit]
~~~

## 32. Runbook điều tra tăng đột biến 401/403/429

### Giai đoạn 1 — Xác định ảnh hưởng và phạm vi

1. Ghi **incident ID, event window, timezone, gateway/region, route, tenant/consumer grouping, thay đổi gần đây**.
2. Tách **401 (AuthN), 403 (AuthZ/WAF/app) và 429 (rate/quota)** theo **decision_source**, không chỉ gộp là "client errors".
3. Đo **tổng requests, tỷ lệ thành công, p95/p99 latency, downstream SLI** và lượng người dùng hợp lệ bị ảnh hưởng.
4. Kiểm tra **logging pipeline health**, vì một đợt sụt log đồng thời có thể làm sai tỷ lệ.

### Giai đoạn 2 — Phân biệt lỗi hệ thống và hoạt động đáng ngờ

| Dấu hiệu | Kiểm tra trước |
|---|---|
| TOKEN_EXPIRED tăng trên nhiều client | Token refresh SDK, IdP availability, client clock |
| INVALID_SIGNATURE hoặc UNKNOWN_KID tăng | JWKS key rotation, cache freshness, cấu hình issuer |
| AUTHZ_DENIED sau deploy | Scope/role policy, gateway version, backend authorization |
| WAF BLOCK tăng sau rule update | Managed/custom rule changes, endpoint false positive |
| 429 tăng sau marketing/batch job | Quota budget, traffic burst, NAT shared, retry policies |
| mTLS failures tại một region | CA/trust bundle rotation, certificate expiry, SNI/hostname |
| Chỉ một client/consumer bị deny | Consumer permissions, compromised credentials, client bug |

Không kết luận "tấn công" khi chỉ có một ngưỡng thống kê. Xem **nhiều nguồn**: gateway events, WAF action, control-plane changes, IdP/JWKS health, firewall flows và app logs có quyền.

### Giai đoạn 3 — Giảm thiểu phù hợp

- Nếu phát hiện **key/identity bị lộ hoặc abuse rõ ràng**, phối hợp IAM/SOC để **revoke/rotate credential, hạn quyền consumer, giảm quota hợp lý, áp rule hẹp** theo phê duyệt.
- Nếu do **policy deployment sai**, ưu tiên **rollback đúng version** hoặc exception scope hẹp có owner và expiration.
- Nếu do **IdP/JWKS outage**, xử lý source/caching/reachability, không tắt JWT signature validation để làm API trả 200.
- Nếu rate limit chặn user hợp lệ, chỉnh bucket/key theo **verified identity và nhu cầu dịch vụ**, không tin XFF client tự khai.
- Không bật **ALLOW_ALL**, tắt WAF toàn bộ hoặc log raw bearer tokens chỉ để debug.

### Giai đoạn 4 — Xác minh và hậu kiểm

Chạy test cả **request hợp lệ được allow** và **request thiếu quyền bị deny**; đối chiếu source of decision, log coverage, end-user SLI và configuration drift trên các region. Bổ sung detection, owner và regression matrix, ghi rõ **những giả thuyết đã loại trừ**.

## 33. Runbook khi security events không đến SIEM

### Tình huống

Dashboard AUTHN_FAILED giảm gần về 0 trong lúc traffic tổng và số 401 ở CDN vẫn bình thường. Đây có thể là **mất telemetry** chứ không có nghĩa hệ thống hết lỗi bảo mật.

### Bước 1 — Phân biệt request không có và logging không có

So **trusted ingress request count**, gateway HTTP statuses, event exporter heartbeat, collector metrics và last-ingest-time theo **gateway ID/region/route**. Xác định các sự kiện hiện tại có xuất tại source nhưng không đến storage không.

### Bước 2 — Kiểm tra health pipeline

Kiểm tra agent process, buffer/queue depth, disk quota, network/TLS giữa exporter–collector, service account IAM, schema parsing errors và SIEM quota. Không copy raw logs chứa PII/credential sang hệ thống khác ngoài quy trình.

### Bước 3 — Khôi phục đúng mức

- Nếu collector lỗi, phục hồi consumer/queue và replay **trong giới hạn retention**.
- Nếu gateway logging config bị thay, điều tra admin audit và rollback thay đổi trái phép.
- Nếu parser từ chối schema mới, sửa schema mapping, giữ raw redacted copy theo yêu cầu và chạy lại regression.
- Nếu mất log không thể khôi phục, ghi **data gap rõ phạm vi/thời điểm** vào incident và điều chỉnh kết luận về traffic trong khoảng đó.
- Không hy sinh **AuthN/AuthZ enforcement** chỉ để phục hồi telemetry.

### Bước 4 — Xác minh và cải tiến

Thử tạo **canary security decision có phép** (ví dụ request test thiếu credential tới route test) và theo dõi **event ID từ gateway đến SIEM**. Bổ sung heartbeat độc lập, alert ingestion lag, giới hạn buffer và cảnh báo khi audit logging bị tắt.

## 34. Các tình huống thực tế

### Tình huống A — JWT sai chữ ký nhưng log ghi nhầm subject

**Triệu chứng:** security log hiển thị subject "admin" lấy từ payload JWT, dù validation thất bại.

**Vấn đề:** claims trong token chưa được xác minh bị đưa vào **verified_actor_id**, gây sai attribution và có thể ảnh hưởng detection/rate limiting.

**Xử lý:** chỉ điền actor_id sau validation; với invalid token dùng **unknown/unverified context** hoặc không ghi claims. Kiểm tra token validation logic và schema mapping, không sửa bằng cách lưu raw JWT để đối chiếu.

### Tình huống B — WAF báo hàng nghìn sự kiện nhưng khách không bị chặn

**Triệu chứng:** dashboard hiển thị nhiều rule matches; help desk không nhận ticket 403.

**Giải thích:** WAF đang ở **COUNT/monitor mode** hoặc một rule match không phải final disposition. Đếm matched_rule và blocked_requests riêng; không tuyên bố một chiến dịch đã bị chặn khi chỉ quan sát.

### Tình huống C — User hợp lệ bị 429 vì NAT nhà mạng

**Triệu chứng:** hàng trăm user di động chia sẻ địa chỉ public IP, bucket rate limit theo IP làm nhiều người bị chặn.

**Xử lý:** với user đã xác thực, cân nhắc bucket theo **verified user/consumer/tenant**, kết hợp giới hạn anonymous theo trusted IP. Không dựa vào XFF do client tự khai để tách bucket.

### Tình huống D — Sau JWKS rotation, 401 tăng toàn region

**Triệu chứng:** nhiều clients hợp lệ bị TOKEN_KID_UNKNOWN cùng thời điểm IdP thay signing key.

**Giải thích:** key distribution/JWKS cache chưa đồng bộ, không nhất thiết là tấn công. Giữ validation chặt, khắc phục refresh/config theo hướng dẫn nền tảng, kiểm thử tokens hợp lệ và token sai trước khi đóng incident.

### Tình huống E — Gateway 403, backend không có log

**Triệu chứng:** đội ứng dụng không tìm thấy request ID trong app log.

**Giải thích:** gateway từ chối **AUTHZ_DENIED** trước upstream. Cần log request_id, policy, 403, upstream_attempts=0 và log tương ứng ở gateway; absence của backend log không phải lỗi bắt buộc.

### Tình huống F — Backend 403 nhưng gateway authn thành công

**Triệu chứng:** Gateway ghi AUTHN_SUCCEEDED, app trả 403 khi user mở dữ liệu thuộc tenant khác.

**Giải thích:** đây có thể là **object-level authorization đúng ở backend**. Gateway không được tự gán AUTHZ_DENIED cho một rule chưa thực thi. Cần correlation ID và app-level audit event, không mở quyền toàn tenant ở gateway.

### Tình huống G — Control plane tắt security logging

**Triệu chứng:** log deny sụt đột ngột trên một gateway instance ngay sau một thay đổi IAM.

**Nguy cơ:** mất visibility hoặc có hành vi cố tình che dấu. Xem **admin audit, exporter heartbeat, config diff, IAM rights** và event rate từ ingress, không vội kết luận không còn request độc hại.

### Tình huống H — SIEM ghi nhầm mọi event là cùng một request

**Triệu chứng:** một client gửi X-Request-ID cố định, gateway tin nguyên giá trị rồi ghép hàng nghìn request thành một transaction.

**Giải pháp:** trusted ingress tạo/validate request ID và giới hạn nguồn tin cậy. Traces/IDs do client gửi chỉ là context **không phải định danh có thẩm quyền**.

### Tình huống I — Một security event xuất hiện hai lần

**Triệu chứng:** alert count tăng gấp đôi sau khi pipeline queue retry.

**Giải thích:** collector phát lại cùng event sau timeout. Cần **event_id + producer/source ID** để dedup phù hợp; không đếm ingested records là requests duy nhất.

### Tình huống J — mTLS vẫn hợp lệ nhưng client không nên dùng API

**Triệu chứng:** workload staging có cert hợp lệ từ trust bundle chung và gateway cho phép vào API production.

**Nguy cơ:** gateway chỉ kiểm tra chain, không kiểm tra **exact SPIFFE/service identity, environment hoặc allowlist**. Sửa AuthZ policy và trust-domain boundary; ghi event VALID_CERT_BUT_UNAUTHORIZED_IDENTITY theo taxonomy phù hợp.

### Tình huống K — 502 tại gateway bị báo là WAF block

**Triệu chứng:** incident dashboard gộp mọi non-2xx thành security deny.

**Giải thích:** 502 có thể do gateway không kết nối upstream, không phải WAF. Cần **status_source, upstream_error, WAF final disposition**; sửa rules query để tách availability events khỏi security decisions.

### Tình huống L — GraphQL 200 che dấu lỗi permission

**Triệu chứng:** GraphQL HTTP 200 chứa error cho một field người dùng không được đọc, nhưng gateway dashboard chỉ ghi success.

**Giải thích:** HTTP status không đủ phản ánh permission của resolver. Backend cần có **operation/field-level security events** được thiết kế bảo vệ PII; gateway có thể tương quan theo request/trace ID.

## 35. Ma trận kiểm thử security event logging

**Chỉ thử nghiệm trên hệ thống và tài khoản kiểm thử được cấp quyền.** Không dò quét route thật, không brute-force token, không tự gây DDoS hay thay policy production ngoài change approval.

| ID | Kịch bản | Kết quả kỳ vọng | Bằng chứng |
|---|---|---|---|
| **T-01** | Request hợp lệ được xác thực | AuthN/route decision đúng, access success | Gateway event, backend log |
| **T-02** | Route test thiếu credential | AUTHN_FAILED hoặc challenge phù hợp | Reason, status, upstream=0 |
| **T-03** | Token test hết hạn | TOKEN_EXPIRED, không ghi token | JWT validator event |
| **T-04** | Token test có chữ ký sai trong lab | SIGNATURE_INVALID, actor không xác minh | Security log, validator |
| **T-05** | Token có issuer/audience sai | DENY đúng policy | Policy/reason, không upstream |
| **T-06** | Consumer có AuthN nhưng thiếu scope | AUTHZ_DENIED đúng route | Reason, policy_version |
| **T-07** | App object-level deny | Backend event, không gán nhầm gateway deny | Request ID, app audit |
| **T-08** | API key test bị thu hồi | API_KEY_REJECTED; không lộ secret | Key reference, event |
| **T-09** | mTLS test client hợp lệ | Peer identity đúng và role allow | TLS/gateway + backend |
| **T-10** | mTLS test client sai trust/identity | CLIENT_CERT_REJECTED tại đúng stage | Certificate validation metadata |
| **T-11** | TLS handshake bị lỗi trước HTTP | Event không có fabricated route/user/request ID | TLS event schema |
| **T-12** | WAF COUNT trong lab | Rule match nhưng final disposition không bị báo BLOCK | Matched/action fields |
| **T-13** | WAF BLOCK trên test rule | Gateway/WAF event có final BLOCK, backend không cần log | Rule/event/request ID |
| **T-14** | WAF CHALLENGE flow test | Log challenge không đồng nghĩa final block | WAF state events |
| **T-15** | Rate-limit test bucket thấp | 429 + verified subject + rule | Counter event, status |
| **T-16** | Multiple users qua NAT lab | Không nhầm actor; bucket policy đúng | Trusted identity/IP logs |
| **T-17** | Client tự gửi X-Forwarded-For | Không thể giả trusted client IP | Peer/proxy trust validation |
| **T-18** | Client tự gửi X-Request-ID | Trusted ingress overwrite/validate đúng | Request ID at edge/backend |
| **T-19** | Header có ký tự điều khiển trong lab | Parser an toàn, không log injection | Structured logs/validator |
| **T-20** | Request chứa test marker trong query/cookie | Không lưu token/cookie/query nhạy cảm | Redaction audit |
| **T-21** | Event AuthN không thành công | Không ghi unverified claims như actor_verified | Schema/identity fields |
| **T-22** | Thay WAF rule trong staging | Có control-plane audit + policy version | Change log và traffic test |
| **T-23** | Key rotation được mô phỏng | Có event quản trị, không lộ key | Key lifecycle audit |
| **T-24** | IdP/JWKS timeout trong lab | Event phụ thuộc unavailable và failure policy rõ | Auth service metrics |
| **T-25** | CDN cache HIT | Không đòi backend event từ request không tới origin | Edge/cache log |
| **T-26** | Backend 403 sau gateway ALLOW | Hai quyết định có source đúng | Correlation trace/log |
| **T-27** | Gateway 502/504 vì upstream | Không nhầm network error với WAF block | Status source, upstream |
| **T-28** | GraphQL application deny | Backend security event tương ứng | Operation/trace, authz |
| **T-29** | gRPC PERMISSION_DENIED | Có grpc_status, không chỉ HTTP 200 | Gateway/gRPC metadata |
| **T-30** | WebSocket/streaming test | Log lifecycle và decisions đúng | Connection ID/status |
| **T-31** | Collector lag/outage được mô phỏng | Phát hiện lag/drop và replay/dedup nếu hỗ trợ | Pipeline metrics |
| **T-32** | Exporter logging bị tắt trái policy trong lab | Phát hiện config drift/heartbeat gap | Control plane audit |
| **T-33** | Multi-region config rollout | Log có gateway/region/policy_version | Edge region comparison |
| **T-34** | Request retries/fan-out | Event/request/attempt IDs không double count | Correlation graph |
| **T-35** | Analyst tìm request ID của tenant khác | RBAC/tenant scope ngăn lộ logs | Access audit |
| **T-36** | SIEM ingest một event hai lần | Dedup tránh alert count sai | event_id/source |
| **T-37** | Security metrics theo route/event_type | Không có ID ngẫu nhiên làm metric label | Cardinality report |
| **T-38** | Rollback policy sau test | ALLOW hợp lệ và DENY bất hợp lệ vẫn đúng | Positive/negative regression |

### 35.1. Mỗi test phải xác minh cả behavior và evidence

Ví dụ, request thiếu token bị 401 **chưa đủ** nếu security log lại ghi AUTHN_SUCCEEDED hoặc chứa raw Authorization. Ngược lại, một event AUTHZ_DENIED xuất hiện nhưng client vẫn được backend cho phép là **mismatch cần điều tra**. Kết quả chính sách, status cuối, data path và log record phải được đối chiếu cùng nhau.

### 35.2. Test khắc phục không được vô hiệu hóa bảo mật

Khi negative test thất bại, không dùng cách **disable certificate verification, bỏ JWT signature check, mở API route any/any hoặc tắt WAF** để làm test xanh. Cần xác định sai ở schema, ingress header, policy engine, trust, exporter hay app authorization.

## 36. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| **"Mọi HTTP access log đều là security event."** | Access log và security decision/audit là các tín hiệu có mục đích khác nhau. |
| **"Một 403 luôn do API gateway chặn."** | Có thể do WAF, gateway AuthZ hoặc backend object-level authorization. |
| **"WAF rule match nghĩa là request bị block."** | Có thể là COUNT/CHALLENGE, phải xem final disposition. |
| **"JWT sai chữ ký vẫn lấy được subject tin cậy."** | Claims chưa xác minh không được dùng như verified identity. |
| **"401 spike nghĩa là attacker đang tấn công."** | Có thể do token expiry, SDK lỗi, JWKS rotation hoặc clock drift. |
| **"API key là user identity."** | API key thường đại diện consumer/client; user authorization là lớp khác. |
| **"Có mTLS cert hợp lệ thì mọi service được gọi."** | Phải xác minh exact identity, trust domain và route/API authorization. |
| **"Lấy XFF đầu tiên là địa chỉ khách thật."** | Client có thể giả XFF; cần trusted proxy chain. |
| **"Request ID là bằng chứng được phép xem log."** | Request ID là correlation metadata, không phải credential. |
| **"Một event ID tương đương một request."** | Một request có thể tạo nhiều events; retry pipeline còn gây duplicate. |
| **"Không có backend log là lỗi."** | WAF BLOCK, gateway deny và cache HIT có thể không gọi backend. |
| **"Mọi API gateway thấy được BOLA."** | Object-level authorization thường cần backend context. |
| **"HTTP 200 ở gRPC là thành công."** | Cần xem grpc-status khi có gRPC exchange. |
| **"Nếu log JSON thì không còn log injection."** | Vẫn phải escape, giới hạn và validate input untrusted. |
| **"Log càng nhiều payload càng bảo mật."** | Raw token/body có thể tạo rủi ro lớn; ghi metadata tối thiểu. |
| **"Token có hash thì luôn an toàn để log."** | Hash có thể bị đoán/liên kết; cần risk review và kỹ thuật phù hợp. |
| **"SIEM không có event nghĩa là không có request."** | Có thể mất log, sampling, cache hoặc block trước nguồn quan sát. |
| **"Log signed nghĩa là forwarded IP đúng."** | Tính toàn vẹn record không xác minh dữ liệu client tự khai. |
| **"Mọi thay đổi policy đều có request ID."** | Control-plane changes không nhất thiết liên quan một HTTP request. |
| **"Security events tự thay firewall/WAF/AuthZ."** | Logging quan sát/điều tra; enforcement vẫn cần policy đúng. |

## 37. Checklist triển khai production

- [ ] Có inventory API gateways, CDN/WAF, IdP, service mesh, backends, regions và network boundaries.
- [ ] Xác định **data-plane security decisions** khác **access logs và control-plane audit logs**.
- [ ] Taxonomy có AuthN, AuthZ, JWT, API key, mTLS, WAF, rate limit, schema và policy changes.
- [ ] Mỗi event có **event_id, timestamp, event_type, decision, source, reason_code, policy_id/version** khi áp dụng.
- [ ] Có quy tắc null cho sự kiện trước HTTP handshake hoặc trước khi identity được xác minh.
- [ ] Không dùng unverified JWT claims làm actor_id/tenant_id đáng tin.
- [ ] Không dùng raw X-Forwarded-For, X-Request-ID, traceparent hoặc baggage để cấp quyền.
- [ ] Trusted ingress xác định/protect client IP, request ID và source trust theo kiến trúc.
- [ ] Ghi **rule match/action/final disposition** riêng; không báo mọi WAF count như block.
- [ ] Phân biệt 401, 403, 429, 502/504 và HTTP vs gRPC status theo decision source.
- [ ] Biết gateway có thể từ chối trước upstream; không đòi backend log trong mọi trường hợp.
- [ ] Backend ghi object-level/tenant authorization riêng, liên kết request ID/trace.
- [ ] Kiểm soát API key lifecycle và IAM/MFA; log alias, không log key secret.
- [ ] mTLS kiểm tra chain, identity, trust domain và authorization theo policy.
- [ ] Có event khi auth provider/JWKS/cert validator/rate limiter unavailable và biết fail behavior.
- [ ] Chuẩn hóa **schema version, reason codes, event/ingest time, route template**.
- [ ] Không ghi Authorization, Cookie, raw JWT, refresh token, private key hoặc body mặc định.
- [ ] Redaction trước export, log input escaping/size limits để ngăn injection.
- [ ] Bảo vệ export bằng TLS/mTLS/IAM, RBAC, retention và audit truy vấn log.
- [ ] Dùng storage có yêu cầu chống sửa/xóa khi incident/audit policy cần.
- [ ] Có heartbeat, ingestion lag, drop/error/replay/dedup metrics của log pipeline.
- [ ] Control-plane audit ghi ai thay WAF/ACL/JWKS/quota/logging và policy before/after version an toàn.
- [ ] Dashboard tách matched WAF rules và final blocked requests; đếm đúng mẫu số.
- [ ] Metrics không gắn request ID/trace ID/user ID vào nhãn high-cardinality.
- [ ] Alert có baseline, business context, false-positive handling và evidence references.
- [ ] Log schema, policy và quyền truy cập được kiểm tra giữa các region, IPv4/IPv6 và failover.
- [ ] Có test 401/403/429, WAF count/block, gateway timeout, mTLS, gRPC, GraphQL, async.
- [ ] Có negative tests cho header spoofing, sensitive data redaction và cross-tenant log access.
- [ ] Có runbook khi tăng deny events và khi log exporter/collector outage.
- [ ] Mỗi change có owner, approval, test plan, canary, rollback và regression.
- [ ] Chỉ sử dụng dữ liệu và endpoint được phê duyệt trong thực hành; không dò quét khách hàng.

## 38. Câu hỏi tự kiểm tra

**1. Security event log khác access log như thế nào?**  
Security event tập trung vào một kiểm tra/điều kiện/điều khiển bảo mật và quyết định của nó; access log tập trung request/response đã được một lớp xử lý. Hai loại có thể cùng request ID nhưng không thay thế nhau.

**2. Vì sao API gateway cần ghi event khi request bị WAF BLOCK?**  
Vì request không đi tới backend; nếu chỉ ghi log ở app thì SOC không thấy dấu vết chặn. Event cần request ID, WAF rule/action/final disposition và policy version.

**3. Có được ghi subject của JWT sai chữ ký làm verified user không?**  
Không. Claims chưa xác minh là dữ liệu untrusted, có thể bị giả mạo và làm sai attribution.

**4. AuthN thành công nhưng backend 403 có phải gateway thất bại không?**  
Không nhất thiết. Gateway có thể xác thực đúng, còn backend từ chối quyền đối tượng/tenant theo business authorization.

**5. Vì sao một WAF rule match chưa chắc là một block?**  
Vì rule có thể ở chế độ COUNT/monitor, hoặc có nhiều rule evaluations; phải xem final disposition.

**6. Một request có thể tạo mấy security events?**  
Có thể nhiều: token validated, scope denied, rate-limit checked, WAF matched hoặc gateway final decision. Event ID khác request ID.

**7. Có nên lấy X-Forwarded-For bên trái nhất để biết khách hàng?**  
Không mặc định. Phải dùng trusted proxy chain và network peer; nếu không client Internet có thể giả source.

**8. Log rate-limit theo IP có thể sai trong tình huống nào?**  
Nhiều user chia NAT/CGNAT hoặc cùng reverse proxy, gây chung bucket; cần đánh giá verified consumer/user identity và false-positive impact.

**9. Tại sao log 429 không tự là bằng chứng DDoS?**  
429 có thể do quota thấp, batch hợp lệ, SDK retry hoặc traffic surge. Cần baseline và upstream/network context.

**10. Vì sao mTLS certificate hợp lệ vẫn cần authorization?**  
Certificate chứng minh identity theo trust policy, nhưng không cấp quyền gọi mọi route/API hoặc đọc mọi dữ liệu.

**11. Một lỗi TLS handshake có luôn có HTTP request ID không?**  
Không. TLS có thể bị từ chối trước khi tạo request HTTP, route hoặc actor context.

**12. Tại sao không log raw token để truy vấn trùng lặp?**  
Token có thể là bearer credential và chứa PII; lộ log có thể dẫn tới chiếm quyền. Dùng validation result, reason và metadata không nhạy cảm.

**13. Khi SIEM không có log AUTHN_FAILED, cần kiểm tra gì?**  
Kiểm tra request volume, gateway event source, config audit, exporter heartbeat, queue, dropped count, parser và ingest lag trước khi kết luận không còn lỗi.

**14. Tại sao cần event_time và ingest_time riêng?**  
Vì logs có thể đến muộn qua buffer/retry; ingest order không luôn phản ánh thời gian quyết định bảo mật.

**15. Vì sao không dùng request ID làm Prometheus label?**  
Định danh gần như duy nhất gây high-cardinality và chi phí/tải storage lớn; dùng route template/reason/status class làm nhãn.

**16. Khi phát hiện token hết hạn tăng đột biến, cần kiểm tra yếu tố nào ngoài attacker?**  
Token refresh SDK, IdP/JWKS, clock skew, policy update, thay đổi client release và ảnh hưởng người dùng.

**17. Những quyết định nào cần audit ngoài request logs?**  
Thay AuthN/AuthZ, issuer/JWKS/trust bundle, WAF mode, quota, API keys, logging configuration và quyền quản trị.

**18. Test một log system đạt yêu cầu phải xem những gì?**  
Behavior thật (ALLOW/DENY), event type/reason đúng, final status, event/request IDs, log không lộ secrets, pipeline nhận đủ và truy vấn log được RBAC bảo vệ.

## 39. Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thiết kế security logs, trường dữ liệu, dữ liệu không nên log, chống injection và phân quyền.
- [OWASP API Security Top 10 — 2023](https://owasp.org/API-Security/editions/2023/en/0x00-header/): các nhóm rủi ro API như BOLA, broken authentication, BFLA và resource consumption.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): bảo vệ REST API, xác thực, token, input và dịch vụ.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): authorization mặc định từ chối, kiểm tra mọi request và object-level permissions.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa HTTP status, methods và các semantics giao thức.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): mã trạng thái HTTP 429 Too Many Requests.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens và mô hình báo lỗi/challenge.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc và claims JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các nguy cơ và thực hành xác thực/kiểm tra JWT.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): header Forwarded và chuỗi proxy.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, tracestate và phân biệt trace/span IDs.
- [W3C Baggage](https://www.w3.org/TR/baggage/): metadata truyền theo request và giới hạn bảo mật.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): mô hình sự kiện log và trace correlation.
- [OpenTelemetry — Documentation](https://opentelemetry.io/docs/): logs, traces, metrics và context propagation.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): quản trị log an ninh, phân tích, retention và bảo vệ bằng chứng.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): xác thực/authorization theo danh tính và không tin cậy mặc định dựa trên vị trí mạng.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): các nhóm kiểm soát audit, access control, system monitoring và bảo vệ dữ liệu.
- [gRPC — Status Codes](https://grpc.github.io/grpc/core/md_doc_statuscodes): các mã trạng thái riêng của gRPC cần phân biệt với HTTP transport status.

**Ghi nhớ:** Log security event của API gateway chỉ có giá trị khi mỗi record phản ánh đúng **sự kiện, điểm kiểm soát, identity đã được xác minh, policy/rule, lý do và quyết định cuối**, được gắn **event/request/trace IDs** phù hợp, có thời gian và nguồn đáng tin. Phải phân biệt **request bị chặn trước backend** với ứng dụng từ chối, **rule match** với **final BLOCK**, **AuthN thành công** với **AuthZ đúng** và **sự cố security** với **lỗi cấu hình/khả dụng**. Giữ log có cấu trúc, không rò credential/PII, bảo vệ pipeline và audit control plane; kết hợp **WAF, IAM, TLS/mTLS, firewall/segmentation, SIEM/OpenTelemetry và kiểm thử âm tính** để có khả năng giám sát và ứng phó thực sự.
