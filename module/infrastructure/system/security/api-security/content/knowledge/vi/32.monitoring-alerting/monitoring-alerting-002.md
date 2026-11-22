# Phát hiện 401, 403, 404 và 429 bất thường

## 1. Vì sao cần phát hiện bất thường theo HTTP status?

Các mã HTTP 401, 403, 404 và 429 xuất hiện thường xuyên trong hoạt động bình thường của API. Một user nhập sai mật khẩu, một client gửi token hết hạn, một người dùng mở resource đã bị xóa hoặc một ứng dụng vượt quota đều có thể tạo response tương ứng.

Tuy nhiên, thay đổi đột ngột về số lượng, tỷ lệ hoặc phân bố các status này có thể là tín hiệu sớm của tấn công hoặc lỗi cấu hình:

- Nhiều 401 trong thời gian ngắn có thể là credential stuffing, password spraying, token replay hoặc client đang dùng secret cũ.
- Nhiều 403 tập trung vào một tenant hoặc một nhóm object có thể là hành vi dò quyền, BOLA/IDOR probing hoặc policy bị cấu hình sai.
- Nhiều 404 trên các route không tồn tại có thể là endpoint scanning; nhiều 404 trên object ID hợp lệ có thể là enumeration hoặc client stale.
- Nhiều 429 có thể cho thấy abuse, bot traffic, retry storm hoặc rate limit quá thấp so với traffic thật.

Chỉ đếm tổng số status code là chưa đủ. Một API có hàng triệu request mỗi phút có thể có hàng nghìn 401 bình thường; một API ít traffic có thể bị tấn công chỉ với vài chục request. Cần xem xét baseline, tỷ lệ, tốc độ tăng, danh tính caller, route, tenant, IP/network context, kết quả xác thực, thời điểm và tác động nghiệp vụ.

Trong phạm vi **SECURITY_API_SECURITY**, monitoring cần nối được quyết định authentication/authorization với endpoint, object và business flow. Mục tiêu là phát hiện tín hiệu có ý nghĩa, giảm false positive, bảo vệ dữ liệu trong telemetry và giúp đội vận hành phản ứng có bằng chứng.

Sau bài học này, người học có thể:

1. Diễn giải đúng ý nghĩa bảo mật của 401, 403, 404 và 429.
2. Xây dựng baseline theo route, principal type, tenant và traffic pattern.
3. Thiết kế metric, log và trace có thể phục vụ detection mà không lộ secret.
4. Phát hiện credential abuse, permission probing, resource enumeration và rate-limit abuse.
5. Kết hợp rate, ratio, cardinality, sequence và context để giảm cảnh báo sai.
6. Viết alert có severity, owner, runbook và hành động rõ ràng.
7. Điều tra, xử lý và xác minh một bất thường sau khi alert kích hoạt.

## 2. Ý nghĩa bảo mật của bốn status code

Các status code này biểu thị những trạng thái khác nhau. Không nên gộp chúng thành một nhóm “request lỗi” vì mỗi loại phản ánh một điểm khác trong trust boundary.

| Status | Ý nghĩa HTTP | Tín hiệu cần quan sát |
|---|---|---|
| 401 | Request thiếu credential hợp lệ hoặc credential không được chấp nhận | Token/key invalid, expired, missing; login failure; issuer/audience mismatch |
| 403 | Server hiểu request nhưng từ chối thực hiện | Authenticated principal thiếu permission, scope, tenant hoặc policy |
| 404 | Không tìm thấy resource hoặc server cố ý không tiết lộ resource tồn tại | Route scanning, object enumeration, stale client, hidden-resource behavior |
| 429 | Caller gửi quá nhiều request trong một khoảng thời gian theo policy | Quota exhaustion, brute force, bot, retry storm hoặc rate-limit misconfiguration |

### 2.1. 401 không đồng nghĩa user nhập sai mật khẩu

401 có thể xuất hiện khi:

- Không có Authorization header ở endpoint yêu cầu authentication.
- Bearer token sai chữ ký hoặc không nằm trong trust chain.
- Token hết hạn hoặc chưa có hiệu lực.
- Issuer, audience hoặc token type không phù hợp.
- API key không tồn tại, đã revoke hoặc sai environment.
- mTLS client certificate không hợp lệ hoặc mapping identity thất bại.
- Session cookie thiếu hoặc hết hạn.
- Client gửi credential theo format sai.

Nếu endpoint login dùng 401 cho thông tin đăng nhập không hợp lệ, telemetry cần phân biệt login failure với API token validation failure. Hai trường hợp có cách điều tra và phản ứng khác nhau.

### 2.2. 403 phản ánh authorization decision

403 thường có nghĩa caller đã được xác thực hoặc request đã đến bước policy nhưng không có quyền thực hiện hành động. Các nguyên nhân có thể là:

- Thiếu role, scope hoặc permission.
- Tenant context không khớp.
- Không sở hữu object hoặc không thuộc quan hệ được phép.
- Resource đang ở trạng thái không cho phép thao tác.
- Policy engine từ chối.
- Workload identity thiếu quyền gọi service.
- Endpoint chỉ dành cho admin hoặc internal client.

Không phải mọi 403 đều là tấn công. User thường xuyên truy cập chức năng không được cấp có thể là dấu hiệu UX hoặc role mapping lỗi. Tuy nhiên, một principal thử nhiều object/tenant hoặc nhiều action nhạy cảm có thể là permission probing.

### 2.3. 404 có thể che giấu resource bị cấm

Một số API cố ý trả 404 thay vì 403 để không tiết lộ resource có tồn tại hay không. Ví dụ user A truy cập tài liệu của user B có thể nhận 404.

Điều này có thể đúng về bảo mật, nhưng làm monitoring phức tạp: 404 có thể là typo, resource đã xóa, enumeration hoặc access concealment. Cần log nội bộ outcome cụ thể như RESOURCE_NOT_FOUND hoặc RESOURCE_HIDDEN_BY_POLICY, nhưng không nhất thiết expose lý do đó cho caller.

### 2.4. 429 có thể là bảo vệ đang hoạt động

429 cho biết rate limit hoặc quota đã được áp dụng. Một đợt tăng 429 có thể chứng minh guardrail đang chặn tải, nhưng cũng có thể chỉ ra:

- Caller đang bị abuse.
- Một client mới có retry loop.
- Một dependency chậm khiến request retry dồn dập.
- Quota cấu hình thấp hơn nhu cầu thực.
- Nhiều user hợp lệ chia sẻ cùng IP và bị limit theo IP.
- Bot hoặc credential bị lạm dụng.

Theo dõi cả số request bị limit, tỷ lệ 429, key/tenant/route bị ảnh hưởng và trạng thái capacity. Đừng coi mọi 429 là sự cố bảo mật hoặc bỏ qua chúng vì “rate limiter đã chặn”.

## 3. Định nghĩa detection objective trước khi tạo alert

Mỗi alert nên trả lời một câu hỏi bảo mật hoặc vận hành cụ thể. Ví dụ:

- Có phải một nguồn đang thử nhiều credential khác nhau?
- Một principal có đang thử truy cập nhiều object không thuộc quyền của nó?
- Có scanner đang dò nhiều route không tồn tại?
- Một client đang retry quá nhanh sau 429?
- Một tenant có tỷ lệ authorization deny tăng đột biến sau thay đổi policy?
- Một đợt 401 đồng loạt có liên quan đến issuer/JWKS hoặc secret rotation?
- Một endpoint có 404/403 bất thường sau deploy hoặc route migration?

Tránh alert chỉ có tên “401 tăng cao” mà không có ngữ cảnh. Alert tốt xác định:

1. Đối tượng đo: service, route, principal type, tenant tier hoặc client.
2. Điều kiện kích hoạt: count, rate, ratio, deviation hoặc sequence.
3. Cửa sổ thời gian và cách so sánh baseline.
4. Severity và mức tin cậy.
5. Owner và runbook.
6. Hành động an toàn khi xác minh.

### 3.1. Phân biệt security signal và service health signal

Một spike 401 có thể do attacker, nhưng cũng có thể do identity provider outage hoặc signing key rotation lỗi. Một spike 404 có thể do route deploy sai. Một spike 429 có thể do capacity hoặc quota config.

Alert cần gợi ý cách phân biệt:

- Security signal: tập trung vào principal, IP, credential identifier, object/tenant probing hoặc sequence đáng ngờ.
- Service health signal: nhiều user/tenant cùng bị ảnh hưởng, cùng thời điểm, cùng dependency hoặc cùng deployment.
- Product/contract signal: client cũ gọi route/version đã thay đổi hoặc gửi token theo contract cũ.

Có thể tạo alert riêng cho security và reliability, nhưng dùng chung telemetry đã chuẩn hóa.

## 4. Xây dựng baseline có ngữ cảnh

Baseline là hành vi bình thường của hệ thống trong điều kiện traffic và nghiệp vụ cụ thể. Không dùng một ngưỡng global cho mọi route.

Các yếu tố ảnh hưởng baseline:

- Endpoint và HTTP method.
- Giờ trong ngày, ngày trong tuần, kỳ thanh toán hoặc batch window.
- Principal type: human user, service account, API key, anonymous.
- Tenant tier và quy mô tenant.
- Client/app version.
- Authentication mechanism.
- Public vs internal route.
- Traffic volume và seasonality.
- Số lượng resource hợp lệ và tỷ lệ resource đã bị xóa.
- Thay đổi gần đây ở gateway, identity provider hoặc policy.

Ví dụ login endpoint có 401 cao hơn endpoint đọc profile; một endpoint search có thể tạo 404 bình thường khi user tìm ID cũ; API tích hợp theo batch có traffic tăng vào cuối tháng.

### 4.1. Baseline theo route template

Dùng route template như /v1/orders/{orderId} thay vì raw path chứa object ID. Điều này giúp so sánh hành vi theo operation và tránh tạo metric label với cardinality rất cao.

Không gộp tất cả route vào một nhóm. Login, export, admin, object read và health endpoints có profile status khác nhau.

### 4.2. Baseline theo principal type

Một service account gọi một endpoint 10.000 lần/ngày có thể là bình thường; một human user gọi cùng endpoint với tốc độ đó có thể bất thường. Phân nhóm theo loại principal và client đã xác minh, không dựa vào header do caller tự khai.

### 4.3. Baseline theo tenant

Tenant lớn và tenant nhỏ có volume khác nhau. Theo dõi tenant tier hoặc cohort phù hợp. Khi cần điều tra một tenant cụ thể, dùng log/event có kiểm soát thay vì đưa raw tenant ID vào mọi metric label.

### 4.4. Baseline phải thích nghi có kiểm soát

Rolling average, median, percentile, EWMA hoặc seasonal baseline có thể giúp phát hiện thay đổi. Tuy nhiên, không để model tự học một cuộc tấn công kéo dài như traffic bình thường.

- Dùng baseline từ khoảng thời gian được xem là sạch.
- Có minimum traffic threshold.
- Giới hạn tốc độ cập nhật baseline.
- Đánh dấu maintenance, load test và deploy window.
- Review drift định kỳ.
- Giữ ngưỡng tuyệt đối cho các sự kiện rất rủi ro.

## 5. Telemetry: metric, log và trace

Ba loại telemetry bổ sung nhau:

| Loại | Dùng để | Không nên dùng để |
|---|---|---|
| Metric | Trend, rate, ratio, alert và capacity | Lưu raw user ID, token hoặc object ID làm label |
| Log/event | Điều tra từng decision và principal cụ thể | Lưu raw secret, payload nhạy cảm hoặc dữ liệu không cần thiết |
| Trace | Nối gateway, auth, policy, service và dependency | Là nguồn duy nhất vì sampling có thể bỏ sót request |

### 5.1. Event schema cho security decision

Một event có thể gồm:

```json
{
  "timestamp": "2026-11-18T10:15:30Z",
  "service": "orders-api",
  "environment": "production",
  "route_template": "/v1/orders/{orderId}",
  "method": "GET",
  "http_status": 403,
  "outcome": "AUTHORIZATION_DENIED",
  "principal_type": "user",
  "principal_ref": "pseudonymous-ref",
  "tenant_ref": "pseudonymous-tenant",
  "authn_method": "oauth2_bearer",
  "policy_id": "order-read-v4",
  "reason_code": "OBJECT_SCOPE_MISMATCH",
  "client_id": "web-portal",
  "source_network": "trusted-edge",
  "request_id": "req-7f31",
  "trace_id": "trace-a91d"
}
```

Đây là schema minh họa. principal_ref và tenant_ref nên là identifier pseudonymous hoặc reference có kiểm soát; không ghi access token, API key, cookie, raw Authorization header hay nội dung resource.

### 5.2. Chuẩn hóa outcome

Không chỉ dựa vào HTTP status. Một 404 có thể là ROUTE_NOT_FOUND, RESOURCE_NOT_FOUND hoặc RESOURCE_HIDDEN_BY_POLICY. Một 401 có thể là TOKEN_EXPIRED, API_KEY_REVOKED, MISSING_CREDENTIAL hoặc LOGIN_INVALID.

Dùng reason code ổn định ở telemetry nội bộ, nhưng tránh tiết lộ quá nhiều chi tiết cho public response vì có thể hỗ trợ attacker phân biệt trạng thái credential/resource.

### 5.3. Ghi nhận cả request và decision

Cần biết:

- Request đã đến gateway hay application?
- Authentication có chạy không?
- Principal nào được xác minh?
- Authorization policy nào được đánh giá?
- Decision là allow hay deny?
- Business side effect có xảy ra không?
- Response cuối do application, gateway hay WAF tạo?

Nếu gateway trả 429 trước application, application log có thể không thấy request. Nếu auth middleware trả 401 trước controller, controller log không đủ. Telemetry cần được thu ở đúng enforcement point và có correlation ID xuyên suốt.

## 6. Thiết kế metric với cardinality có kiểm soát

Metric nên dùng label có tập giá trị hữu hạn hoặc được quản lý.

Ví dụ label phù hợp:

- service
- environment
- route_template
- method
- status_class hoặc status_code
- principal_type
- authn_method
- outcome
- reason_code
- client_tier
- region

Cần thận trọng với:

- Raw user ID.
- Raw tenant ID.
- API key.
- Token subject không giới hạn.
- Raw path chứa object ID.
- IP address làm label.
- User-Agent đầy đủ.
- Arbitrary query parameter.

Các trường high-cardinality có thể lưu trong security event/log với access control và retention riêng.

### 6.1. Counter và histogram cơ bản

Ví dụ Prometheus metrics:

```text
api_http_responses_total{
  service="orders-api",
  route="/v1/orders/{orderId}",
  method="GET",
  status="403",
  outcome="AUTHORIZATION_DENIED"
}

api_authentication_failures_total{
  service="orders-api",
  authn_method="oauth2_bearer",
  reason="TOKEN_EXPIRED"
}

api_authorization_decisions_total{
  service="orders-api",
  action="order.read",
  decision="DENY"
}

api_rate_limit_rejections_total{
  service="orders-api",
  policy="per-client"
}
```

Dùng counter cho số lần xảy ra; histogram cho latency hoặc payload size; gauge cho số upload/session/connection đang hoạt động. Đặt tên và label nhất quán giữa service.

### 6.2. Đếm status ở một điểm duy nhất

Nếu gateway và application cùng emit response counter, có thể đếm một request hai lần. Chọn một nguồn canonical cho HTTP response metrics, hoặc phân biệt edge_response và application_response.

Khi phân tích 429, xác định status do WAF, gateway, application rate limiter hay downstream trả về. Mỗi lớp có owner và ý nghĩa khác nhau.

## 7. Phát hiện 401 bất thường

401 tập trung có thể là dấu hiệu credential abuse hoặc lỗi identity integration.

Các pattern cần quan sát:

- Nhiều username/account bị thử từ một nguồn.
- Một account bị thử từ nhiều nguồn.
- Một client ID hoặc API key ID tạo nhiều invalid token.
- Một service account bắt đầu gửi credential hết hạn.
- Một issuer/audience mismatch tăng trên nhiều route.
- Tỷ lệ 401 tăng đồng loạt sau key rotation hoặc IdP/JWKS change.
- Nhiều lần refresh token thất bại.
- 401 tăng trước một chuỗi login success bất thường.

### 7.1. Credential stuffing

Credential stuffing dùng username/password bị lộ ở nơi khác để thử đăng nhập. Dấu hiệu có thể là:

- Nhiều account khác nhau được thử với ít password/source pattern.
- Một số account có success sau nhiều failure.
- Request phân tán qua proxy hoặc botnet.
- User-Agent hoặc client fingerprint lặp lại.
- Tỷ lệ failure tăng ở login/token endpoint.

Không chỉ group theo IP; attacker có thể phân tán IP. Cần xem account, client, device/risk signal và sequence success sau failure.

### 7.2. Password spraying

Password spraying thử một hoặc vài password phổ biến trên nhiều account để tránh lockout theo một account. Theo dõi số account distinct được thử theo source/client trong cửa sổ thời gian và tỷ lệ 401 trên login endpoint.

Alert cần có threshold theo volume và tỷ lệ; một công ty có SSO rollout hoặc password expiry campaign có thể tạo nhiều failure hợp lệ.

### 7.3. Token/key misuse

Với API token, phát hiện:

- Token expired bất thường do client không refresh.
- Token signature invalid tăng trên một client.
- Token cùng subject xuất hiện từ vị trí/ASN/device khác thường.
- API key ID revoked tiếp tục được thử.
- Audience/scope sai trên nhiều resource server.
- Một principal gửi token đến route mà trước đó chưa dùng.

Không ghi raw token để làm fingerprint. Dùng token ID hoặc fingerprint một chiều được thiết kế an toàn, nếu cần và được policy cho phép.

### 7.4. IdP hoặc rotation incident

Nếu nhiều service cùng báo 401, kiểm tra:

- IdP availability và issuer metadata.
- JWKS refresh/cache.
- Signing key rotation và key overlap.
- Clock skew.
- Audience configuration.
- Secret rollout giữa các deployment.
- Certificate/trust bundle.

Một alert bảo mật không nên tự động khóa toàn bộ user khi nguyên nhân là IdP outage hoặc deploy sai.

## 8. Phát hiện 403 bất thường

403 tăng có thể chỉ ra permission probing, privilege escalation attempt hoặc policy regression.

Pattern đáng chú ý:

- Một principal truy cập nhiều object thuộc owner/tenant khác.
- Một user thử nhiều action admin hoặc write.
- Một client đổi liên tục resource ID nhưng vẫn nhận deny.
- Một service account gọi operation ngoài scope.
- Nhiều deny từ cùng token sau khi role bị thu hồi.
- 403 tăng đột ngột sau thay đổi RBAC/ABAC policy.
- Nhiều user hợp lệ bị deny cùng route/tenant.

### 8.1. BOLA/IDOR probing

Một caller có thể thử lần lượt object ID hoặc tenant ID để tìm resource không thuộc quyền. Dấu hiệu:

- Số object ID distinct lớn trong một cửa sổ ngắn.
- Tỷ lệ 403/404 cao trên một route object.
- Một principal thử nhiều owner/tenant context.
- Request sequence có ID tăng dần hoặc pattern enumeration.
- Nhiều deny sau một request thành công vào object của chính caller.

Không dùng raw object ID làm metric label. Ghi event có principal reference, route template, reason code và object classification/owner mismatch đã được kiểm soát.

### 8.2. Privilege probing

Một user bình thường thử admin endpoint, role management, export hoặc policy configuration có thể là hành vi dò quyền. Theo dõi action nhạy cảm và số permission family bị deny theo principal.

Cần phân biệt user click vào UI bị ẩn sai với request được tạo bằng script. User-agent không đủ để chứng minh intent; dùng context và sequence.

### 8.3. Authorization regression

Nếu 403 tăng đồng loạt sau deploy, có thể policy mapping, role claim hoặc tenant context bị sai. So sánh theo release version, policy ID và route. Alert reliability nên kích hoạt khi nhiều user/tenant bị ảnh hưởng; security alert có thể ưu tiên khi chỉ một principal có pattern dò object.

### 8.4. Không log quá nhiều chi tiết cho caller

Response 403 nên có error code đủ cho client xử lý, nhưng không trả policy expression, role nội bộ, object owner hoặc danh sách quyền của user khác. Chi tiết để điều tra nằm trong security event được kiểm soát.

## 9. Phát hiện 404 bất thường

404 có hai nhóm lớn:

1. Route không tồn tại.
2. Resource không tồn tại hoặc bị cố ý che giấu.

Cần phân biệt trong telemetry để phát hiện endpoint scanning và object enumeration.

### 9.1. Route scanning

Dấu hiệu:

- Một source thử nhiều route template không tồn tại.
- Nhiều path chứa tên admin/debug/backup/config phổ biến.
- Method bất thường trên route.
- Tỷ lệ 404 cao trên hostname hoặc service mới.
- Nhiều request tới endpoint cũ đã retire.
- Một client scan nhiều service trong cùng environment.

WAF có thể phát hiện một số pattern, nhưng application/gateway inventory mới biết route nào hợp lệ. So sánh path đã normalize với route registry.

### 9.2. Object enumeration

Một caller thử nhiều ID trên một route hợp lệ có thể tạo 404 liên tục. Nếu hệ thống che giấu object không được phép bằng 404, cần reason code nội bộ để phân biệt RESOURCE_NOT_FOUND với RESOURCE_HIDDEN_BY_POLICY.

Theo dõi số object distinct, số tenant/owner mismatch và sequence. Không log nội dung resource hoặc ID nhạy cảm nếu không cần.

### 9.3. Stale client và migration

404 tăng sau release có thể do frontend gọi route cũ, mobile app chưa nâng cấp hoặc SDK mismatch. Phân tích theo client version, route version và release window trước khi kết luận scanning.

Nếu API đã deprecated, 404/410 có thể là behavior dự kiến. Dùng lifecycle status và known client migration window để giảm false positive, nhưng vẫn theo dõi credential cũ gọi route đã sunset.

## 10. Phát hiện 429 bất thường

429 có thể phản ánh rate limit đang hoạt động hoặc một client gây tải bất thường.

Pattern cần xem xét:

- Một principal hoặc API key bị limit liên tục.
- Một IP/NAT lớn tạo nhiều 429 cho nhiều user.
- Một tenant chiếm phần lớn quota.
- Một client có retry loop sau 429.
- Nhiều route cùng bị limit do shared quota.
- 429 tăng sau khi giảm threshold hoặc thay đổi quota.
- Request rate cao nhưng 429 thấp bất thường vì limiter bị bypass.
- Rate limiter không phân biệt tenant/principal và gây noisy-neighbor.

### 10.1. Theo dõi Retry-After và retry behavior

Nếu server trả Retry-After, client nên tôn trọng thời gian đó và dùng backoff có jitter. Client retry ngay có thể tạo vòng lặp:

1. Request vượt limit.
2. Server trả 429.
3. Client retry tức thì.
4. Retry tiếp tục vượt limit.
5. Traffic tăng dù operation không thành công.

Theo dõi request sau 429 theo client/principal và correlation ID. Không coi retry là traffic mới không liên quan.

### 10.2. Phân biệt rate limit với capacity limit

429 thường là policy rate limiting; 503 thường thể hiện service tạm không thể xử lý. Một số hệ thống có thể dùng 429 cho quota hoặc 503 cho overload. Contract phải nhất quán.

Kiểm tra limiter dimension: per-IP, per-user, per-token, per-tenant, per-route hay global. Nếu một proxy/NAT đại diện nhiều user, per-IP-only limit có thể chặn nhầm.

### 10.3. Abuse và legitimate burst

Batch job, import, report generation và mobile reconnect có thể tạo burst hợp lệ. Cần quota theo business plan, endpoint cost và principal type; dùng concurrency limit hoặc queue khi phù hợp thay vì chỉ tăng threshold vô hạn.

## 11. Kết hợp rate, ratio và absolute count

Một alert vững chắc thường kết hợp nhiều tín hiệu.

### 11.1. Absolute count

Đếm số 401/403/404/429 trong cửa sổ thời gian. Dễ hiểu nhưng phụ thuộc traffic volume.

### 11.2. Error ratio

Tỷ lệ status trên tổng request cùng route hoặc operation:

\[
\text{ratio}_{401} =
\frac{\text{401 responses}}{\text{all responses}}
\]

Tỷ lệ cao với sample size rất nhỏ có thể không có ý nghĩa. Đặt minimum request volume trước khi alert theo ratio.

### 11.3. Rate of change

So sánh rate hiện tại với baseline cùng giờ/ngày hoặc rolling window. Ví dụ tăng 5 lần có thể đáng chú ý, nhưng nếu baseline gần 0 thì tỷ lệ tăng không ổn định; cần thêm absolute threshold.

### 11.4. Distinct identities và targets

Với 401, xem số account/client distinct bị thử. Với 403/404, xem số object/tenant distinct được truy cập. Với 429, xem số principal bị limit và concentration theo tenant/client.

Distinct count nên được tính ở hệ thống analytics/log query có kiểm soát, không tạo metric label cho từng identity hoặc object.

### 11.5. Sequence và correlation

Một chuỗi có thể đáng ngờ hơn từng status riêng lẻ:

- Nhiều 401 rồi một login success từ cùng client/source.
- Một 200 trên object hợp lệ rồi nhiều 403/404 trên object khác.
- Nhiều 404 route scan rồi một request vào endpoint nhạy cảm.
- Nhiều 429 rồi retry storm.
- Một credential revoked tiếp tục thử nhiều endpoint.

Correlation nên dùng request ID, principal reference, client ID và time window. Không ghép sự kiện chỉ dựa trên IP vì NAT, proxy và shared egress có thể gom nhiều user.

## 12. Ví dụ PromQL cho monitoring

Các truy vấn dưới đây minh họa cách xây dựng alert trên Prometheus. Tên metric/label phải khớp instrumentation thực tế.

### 12.1. Tỷ lệ 401 theo route

```promql
sum by (service, route) (
  rate(api_http_responses_total{status="401"}[5m])
)
/
clamp_min(
  sum by (service, route) (
    rate(api_http_responses_total[5m])
  ),
  0.001
)
```

Kết quả là tỷ lệ 401 theo service/route. Alert thực tế cần thêm điều kiện request volume tối thiểu và baseline theo route.

### 12.2. 403 tăng đột biến

```promql
sum by (service, route) (
  increase(api_http_responses_total{status="403"}[10m])
)
```

Đếm 403 trong 10 phút. Dùng với baseline hoặc absolute threshold; không áp một ngưỡng chung cho tất cả endpoint.

### 12.3. 404 route scanning

```promql
sum by (service, route) (
  rate(api_http_responses_total{
    status="404",
    outcome="ROUTE_NOT_FOUND"
  }[5m])
)
```

Chỉ có thể dùng nếu route not found được phân loại riêng và label có cardinality thấp. Không đưa raw path vào label.

### 12.4. 429 theo policy

```promql
sum by (service, route, policy) (
  rate(api_rate_limit_rejections_total[5m])
)
```

Theo dõi policy dimension để biết limiter nào đang từ chối. Đối chiếu với total request rate, client retries và capacity.

### 12.5. Cẩn thận với phép chia khi không có traffic

Nếu denominator bằng 0 hoặc sample quá nhỏ, ratio có thể không có ý nghĩa. Dùng clamp_min, minimum volume gate và for duration phù hợp. Không để một request đơn lẻ tạo alert ratio 100% kéo dài.

## 13. Thiết kế alert rule và severity

Alert nên phản ánh mức độ rủi ro, độ tin cậy và phạm vi ảnh hưởng.

Ví dụ phân cấp:

| Severity | Ví dụ | Hành động |
|---|---|---|
| Critical | Nhiều account bị thử credential và có login success bất thường; revoked key tiếp tục được dùng trên nhiều resource | Incident response ngay, containment theo runbook |
| High | Một principal dò nhiều object/tenant hoặc nhiều route nhạy cảm | Security triage khẩn, xem xét khóa/revoke có chọn lọc |
| Medium | 401/403/404/429 tăng rõ nhưng chưa có bằng chứng compromise | Điều tra trong giờ làm việc hoặc theo SLA |
| Low/Info | Một client stale hoặc quota burst có owner xác nhận | Theo dõi, sửa client/policy, không page on-call |

### 13.1. Ví dụ điều kiện alert

Một rule có thể kích hoạt khi đồng thời:

- 401 ratio vượt baseline theo route.
- Absolute count vượt minimum threshold.
- Số principal/account distinct vượt ngưỡng.
- Tình trạng kéo dài qua một khoảng for.
- Không trùng với maintenance hoặc IdP incident đã biết.

Một alert BOLA probing có thể yêu cầu:

- Cùng principal reference.
- Một route object-sensitive.
- Nhiều owner/tenant mismatch.
- Nhiều object distinct trong một cửa sổ.
- Tỷ lệ 403/404 cao.
- Không phải service account batch đã đăng ký.

Các con số cụ thể phải được hiệu chỉnh theo traffic và risk appetite; ví dụ trong bài không phải production default.

### 13.2. Alert deduplication và grouping

Nếu 10.000 request cùng một cuộc tấn công tạo 10.000 alert, on-call sẽ bị quá tải. Group theo service, route, principal reference hoặc attack campaign phù hợp; giữ event count và sample evidence để điều tra.

Không gộp các tenant khác nhau vào một alert nếu cần containment riêng. Cũng không group chỉ theo IP khi nhiều user hợp lệ dùng chung NAT.

### 13.3. Alert có owner và runbook

Mỗi rule cần:

- Owner service/security.
- Severity.
- Description có câu hỏi cần trả lời.
- Link dashboard.
- Runbook.
- Query/evidence.
- Điều kiện resolve.
- Escalation path.
- Thời gian review và tuning.

## 14. Giảm false positive

False positive xuất hiện khi traffic hợp lệ bị coi là tấn công. Một alert quá nhạy sẽ bị bỏ qua hoặc bị tắt.

Nguồn false positive phổ biến:

- Login rollout, password expiry hoặc SSO outage.
- Token refresh bug sau deploy.
- Mobile client cũ gọi endpoint đã thay đổi.
- User mở bookmark tới resource đã xóa.
- Search workflow cố tình thử ID không tồn tại.
- Tenant mới import dữ liệu lớn.
- Batch job chạy theo lịch.
- Shared NAT làm nhiều user trông như một source.
- Rate limit threshold thay đổi.
- WAF/gateway bắt đầu log thêm status trước đó không được instrument.

Cách giảm:

1. Baseline riêng theo route/principal type.
2. Dùng absolute count cùng ratio.
3. Yêu cầu minimum sample size.
4. Dùng for duration để lọc spike ngắn.
5. Correlate với deploy, IdP, gateway và policy changes.
6. Allowlist có expiry cho known automation đã xác minh.
7. Tạo alert riêng cho service health và security behavior.
8. Review false positive theo chu kỳ.

Không allowlist IP hoặc user agent rộng chỉ để làm dashboard sạch. Exception phải có owner, scope, lý do và expiry.

## 15. Dashboard cho security operations

Dashboard nên giúp người trực trả lời “điều gì thay đổi, ở đâu, ai bị ảnh hưởng và có tác động gì?”.

Các panel gợi ý:

- Tổng request và tỷ lệ 2xx/4xx/5xx.
- 401 rate/ratio theo service và route.
- 401 theo authentication method và reason.
- 403 theo action/policy/reason code.
- 404 phân biệt route not found và resource not found/hidden.
- 429 theo limiter policy, route và client tier.
- Top principal reference có deny/failure tăng cao trong log view có kiểm soát.
- Distinct account/object/tenant trong cửa sổ thời gian.
- Login success sau nhiều failure.
- Retry sau 429.
- Deploy, IdP, JWKS, gateway và policy change timeline.
- Latency và dependency health để phân biệt outage.

### 15.1. Không hiển thị secret trong dashboard

Dashboard cần tránh raw token, API key, cookie, email đầy đủ hoặc payload. Dùng pseudonymous identifier và drill-down có access control. Không đưa object ID nhạy cảm vào panel công khai.

### 15.2. Dashboard không thay alert

Dashboard giúp con người khám phá; alert giúp gọi người đúng lúc. Một panel có số liệu đỏ nhưng không có owner hoặc action không phải detection workflow hoàn chỉnh.

## 16. Correlate với gateway, WAF, identity provider và application

Một request có thể bị từ chối ở nhiều lớp. Cần biết response cuối cùng đến từ đâu.

Ví dụ:

- WAF trả 403 do rule chặn.
- API gateway trả 429 do quota.
- Authentication middleware trả 401.
- Authorization service trả 403.
- Application trả 404 cho object không tồn tại.
- Reverse proxy trả 404 vì route không được cấu hình.

Nếu tất cả được ghi chung thành http_status=403, detection không biết đó là WAF block hay business authorization deny.

Chuẩn hóa thêm:

- response_origin: waf, gateway, auth middleware, application, upstream.
- decision_stage: routing, authentication, authorization, business, rate_limit.
- outcome và reason_code.
- policy_id/rule_id.
- deployment_version.

Không tin header do client tự gửi để xác định source hoặc principal. Forwarded headers chỉ được tin từ proxy nằm trong trusted proxy chain.

## 17. Điều tra alert 401/403/404/429

Một quy trình triage nên đi từ phạm vi đến bằng chứng:

1. Xác nhận alert không phải duplicate hoặc metric instrumentation bug.
2. Xác định service, route template, method và response origin.
3. Xem thời điểm bắt đầu, duration, volume và baseline.
4. Kiểm tra deploy, config, IdP, gateway, WAF và policy changes.
5. Xác định principal/client/tenant bị ảnh hưởng bằng reference đã kiểm soát.
6. Phân tích source network, client version và request sequence.
7. Xem reason code và decision stage.
8. Kiểm tra có request thành công hoặc business side effect sau các failure không.
9. Xác định phạm vi dữ liệu/object có thể bị dò hoặc truy cập.
10. Chọn containment có phạm vi nhỏ nhất phù hợp và lưu evidence.

### 17.1. Câu hỏi cho 401

- Đây là login failure hay API token validation failure?
- Credential ID nào được dùng?
- Có nhiều account/client bị thử không?
- Có success sau chuỗi failure không?
- IdP/JWKS/clock skew có lỗi không?
- Secret hoặc key vừa rotate/revoke không?

### 17.2. Câu hỏi cho 403

- Principal đã authenticated chưa?
- Policy nào từ chối và vì sao?
- Có object/tenant mismatch không?
- Có nhiều object hoặc action nhạy cảm bị thử không?
- Có deploy/policy regression không?
- Request có gây side effect dù bị deny không? Nếu có, đây là vấn đề nghiêm trọng cần điều tra.

### 17.3. Câu hỏi cho 404

- Route không tồn tại hay object không tồn tại/được che?
- Path đã normalize và match route registry chưa?
- Có nhiều route khác nhau bị scan không?
- Có ID enumeration trên một route object không?
- Client version nào đang gọi?
- Có endpoint cũ vừa sunset hoặc migration không?

### 17.4. Câu hỏi cho 429

- Limiter nào trả 429?
- Dimension là IP, principal, client, tenant, route hay global?
- Có retry loop và Retry-After bị bỏ qua không?
- Một tenant có chiếm quota của tenant khác không?
- Có capacity issue hoặc dependency chậm không?
- Rate limit đang bảo vệ hệ thống hay đang chặn nhầm traffic hợp lệ?

## 18. Response và containment

Hành động phải dựa trên độ tin cậy và blast radius. Không tự động khóa account hoặc block IP chỉ từ một spike status.

Các biện pháp có thể cân nhắc:

- Revoke API key/token cụ thể đã xác minh bị lộ.
- Thu hồi refresh token family hoặc session.
- Tạm giảm scope hoặc disable client integration.
- Step-up authentication hoặc yêu cầu re-auth.
- Tăng rate limit protection theo principal/route có chọn lọc.
- Chặn source network khi có bằng chứng và đánh giá NAT/shared-client impact.
- Tắt endpoint hoặc feature flag nếu đang có exploit.
- Tạm khóa object export hoặc operation nhạy cảm.
- Rollback policy/deployment gây authorization regression.
- Điều chỉnh retry/backoff của client gây 429 storm.

Mỗi action cần có owner, thời điểm, lý do, audit event và tiêu chí rollback. Giữ bằng chứng cần thiết theo retention/incident policy.

### 18.1. Không để alert tự tạo denial of service

Auto-block sai có thể khóa user hợp lệ hoặc chặn NAT của cả tổ chức. Nếu tự động containment, bắt đầu với action có thể đảo ngược và scope hẹp: giảm tốc độ, revoke credential cụ thể hoặc challenge thêm. Với action ảnh hưởng lớn, cần confidence cao và approval theo incident runbook.

### 18.2. Xác minh sau containment

Sau khi xử lý:

- Failure/deny rate có trở về baseline không?
- Credential đã revoke còn được chấp nhận không?
- Có request thành công đáng ngờ trước containment không?
- Có side effect hoặc data exposure không?
- Client hợp lệ có phục hồi không?
- Rate limiter có đang gây collateral damage không?
- Có cần rotation, patch, policy fix hoặc notification không?

## 19. Privacy, retention và integrity của telemetry

Security monitoring cần đủ dữ liệu để điều tra nhưng cũng tạo ra kho thông tin nhạy cảm.

Nguyên tắc:

- Không log raw password, access token, refresh token, API key, cookie hoặc private key.
- Không log toàn bộ request body chỉ để phân tích status.
- Pseudonymize principal/tenant/object reference khi có thể.
- Giới hạn quyền truy cập log và dashboard.
- Mã hóa khi truyền và lưu.
- Đặt retention theo mục đích, quy định và incident needs.
- Audit việc đọc/export telemetry.
- Chống log injection bằng cách escape/control characters.
- Đồng bộ clock và giữ timestamp đủ chính xác.
- Bảo vệ log pipeline khỏi mất dữ liệu, sửa đổi hoặc drop event im lặng.

### 19.1. Không dùng IP như danh tính duy nhất

IP có thể thay đổi, dùng chung qua NAT, proxy, VPN hoặc mobile carrier. Kết hợp IP/network context với authenticated principal, client ID, device/session reference và behavior. Không kết luận một người dùng chỉ từ IP.

### 19.2. Sampling có chủ đích

Sampling trace hoặc debug log có thể làm mất bằng chứng của một đợt tấn công ít request. Có thể giữ 100% security decision events với schema nhỏ và sampling có chọn lọc cho trace/payload. Không log payload nhạy cảm để bù cho sampling.

### 19.3. Đảm bảo log failure không làm mất decision

Nếu security event là bắt buộc cho audit, cần thiết kế durable queue/outbox hoặc fallback phù hợp. Không để logging service lỗi làm request authorization fail-open. Quyết định allow/deny phải độc lập với khả năng ghi dashboard; nhưng các thao tác nhạy cảm có thể yêu cầu audit durability theo policy.

## 20. Ví dụ cấu trúc event trong Java

Một record nội bộ có thể chuẩn hóa decision event:

```java
public record ApiSecurityEvent(
        Instant timestamp,
        String service,
        String routeTemplate,
        String method,
        int httpStatus,
        String responseOrigin,
        String decisionStage,
        String outcome,
        String reasonCode,
        String principalRef,
        String tenantRef,
        String clientId,
        String policyId,
        String requestId,
        String traceId
) {}
```

Tạo event sau khi đã có thông tin principal và decision đáng tin cậy. Không lấy principalRef từ header do caller tự khai. routeTemplate phải là route đã match, không phải raw path chứa ID.

Có thể phát metric từ cùng event schema nhưng chỉ chọn các dimension cardinality thấp. Event đầy đủ được gửi vào log/security analytics với retention và access policy riêng.

## 21. Những lỗi thiết kế thường gặp

1. **Alert theo count global.** Không xét route, traffic volume và principal type.
2. **Chỉ alert theo ratio.** Một request lỗi trên một request tạo tỷ lệ 100% nhưng không có ý nghĩa.
3. **Không có minimum volume.** Sample nhỏ tạo false positive.
4. **Không phân biệt login 401 và token 401.** Khó xác định credential stuffing hay IdP issue.
5. **Gộp mọi 403.** WAF block, policy deny và role misconfiguration bị trộn.
6. **Gộp mọi 404.** Route scan và resource miss không thể phân biệt.
7. **Coi mọi 429 là tấn công.** Quota burst và retry bug cũng tạo 429.
8. **Chỉ group theo IP.** NAT và proxy làm nhiều caller hợp lệ bị gộp.
9. **Dùng user/object ID làm metric label.** Cardinality bùng nổ và lộ dữ liệu.
10. **Không correlate với deploy/IdP changes.** Incident cấu hình bị nhầm thành attack.
11. **Không ghi response origin.** Không biết WAF, gateway hay application trả status.
12. **Không ghi reason code nội bộ.** Điều tra phải suy đoán từ response công khai.
13. **Chỉ dùng trace sampling.** Sự kiện bảo mật quan trọng có thể bị bỏ sót.
14. **Alert không có owner/runbook.** On-call không biết hành động.
15. **Auto-block quá rộng.** Có thể tạo denial of service cho user hợp lệ.
16. **Không kiểm tra success sau failure.** Bỏ lỡ dấu hiệu credential compromise.
17. **Không xem business side effect.** Có thể có data access dù status là deny.
18. **Không review false positive.** Alert fatigue làm mất hiệu quả detection.
19. **Không bảo vệ telemetry.** Log trở thành nơi lưu token, PII và object reference.
20. **Không kiểm tra rate limiter dimension.** Shared IP hoặc shared quota gây collateral damage.

## 22. Checklist thiết kế monitoring và alerting

Trước khi đưa detection vào production, hãy xác nhận:

- [ ] 401, 403, 404 và 429 được định nghĩa rõ theo API contract.
- [ ] Có phân loại login failure và API credential failure.
- [ ] Có phân biệt route-not-found, resource-not-found và hidden-by-policy trong telemetry.
- [ ] Có phân biệt rate-limit policy, quota và capacity response origin.
- [ ] Baseline được chia theo route, principal type và traffic context.
- [ ] Detection kết hợp absolute count, rate, ratio và minimum volume.
- [ ] Có detection cho distinct identities, objects, tenants và sequence đáng ngờ.
- [ ] Có correlation với deploy, IdP, JWKS, gateway, WAF và policy changes.
- [ ] Metric labels có cardinality được kiểm soát.
- [ ] Security event có principal/client reference và reason code đã xác minh.
- [ ] Không log password, token, key, cookie hoặc payload nhạy cảm.
- [ ] Gateway và application không đếm trùng response.
- [ ] Alert có severity, owner, runbook, dashboard và resolve criteria.
- [ ] Có deduplication/grouping để tránh alert storm.
- [ ] False-positive exception có owner, scope và expiry.
- [ ] Triage kiểm tra success sau failure và business side effect.
- [ ] Containment có scope nhỏ, audit và rollback plan.
- [ ] Log/event pipeline có retention, access control, integrity và loss monitoring.
- [ ] Có test cho credential stuffing, password spraying, BOLA probing, route scan và retry storm.
- [ ] Dashboard và alert được review sau deploy, thay đổi traffic và incident.

## 23. Kết luận

401, 403, 404 và 429 là tín hiệu hữu ích khi được diễn giải theo đúng giai đoạn của request. 401 thường phản ánh authentication failure; 403 phản ánh authorization deny; 404 cần phân biệt route và resource behavior; 429 cho biết rate limit hoặc quota đang được áp dụng. Mỗi status đều có thể xuất hiện trong hoạt động bình thường và không tự chứng minh có tấn công.

Detection hiệu quả cần baseline theo route, principal type, tenant và thời gian; kết hợp absolute count, rate, ratio, distinct identity/target và request sequence. Metric dùng label cardinality thấp, còn log/security event lưu reference đã kiểm soát, decision stage và reason code mà không ghi secret hoặc payload nhạy cảm.

Alert phải có owner, severity, runbook và cách phân biệt security behavior với lỗi IdP, deploy, gateway hoặc client. Khi triage, hãy kiểm tra request thành công sau failure, object/tenant scope và business side effect trước khi containment. Cách tiếp cận này giúp phát hiện credential abuse, permission probing, resource enumeration và rate-limit abuse sớm hơn mà vẫn hạn chế alert fatigue và tác động nhầm đến người dùng hợp lệ.

