# Checklist deprecation, revoke và audit evidence

API và credential đều có vòng đời. Một API version có thể cần thời gian để consumer chuyển sang version mới; một API key có thể cần rotate theo lịch; một access token hoặc certificate có thể phải revoke ngay khi bị lộ. Nếu chỉ tắt giao diện hoặc gửi thông báo mà không kiểm tra mọi đường truy cập, endpoint cũ và credential cũ vẫn có thể hoạt động. Ngược lại, revoke thiếu kế hoạch có thể làm gián đoạn integration hợp lệ, job định kỳ hoặc quy trình khôi phục sau thảm họa.

**Deprecation** là thông báo và quản lý giai đoạn một API, endpoint, field hoặc integration sắp ngừng hỗ trợ. **Revocation** là vô hiệu hóa quyền sử dụng credential, token, certificate hoặc grant trước khi hết hạn tự nhiên. **Audit evidence** là bằng chứng có thể kiểm tra được cho thấy quyết định, thay đổi, thông báo, lần revoke và bước xác minh đã thực sự diễn ra.

Trong phạm vi `SECURITY_API_SECURITY`, checklist triển khai phải gắn với endpoint, object, caller, tenant và luồng nghiệp vụ. Cần biết consumer nào dùng API, credential nào đại diện cho consumer, dữ liệu/action nào có thể bị ảnh hưởng và cách chứng minh endpoint/credential đã ngừng hoạt động. Deprecation không tự thu hồi credential; revoke một key không tự loại bỏ route cũ; và ticket ghi “đã revoke” chưa đủ làm bằng chứng nếu chưa xác minh từ đường truy cập thực tế.

## 1. Phân biệt deprecation, disable, revoke và sunset

Các từ này liên quan nhưng không đồng nghĩa:

| Hành động | Ý nghĩa | Ví dụ |
|---|---|---|
| Deprecation | Công bố một API/field/version sẽ ngừng hỗ trợ; bắt đầu migration window | Thông báo version 1 sẽ sunset vào ngày đã công bố |
| Disable | Tạm dừng một route, client hoặc credential theo cấu hình | Tắt integration trong khi điều tra |
| Revoke | Thu hồi hiệu lực credential/grant đã cấp | Revoke API key bị lộ hoặc refresh token |
| Expire | Credential hết hạn theo thời gian đã đặt | Access token hết hạn sau thời lượng ngắn |
| Sunset/retirement | Kết thúc hỗ trợ và ngừng phục vụ API/version | Xóa route cũ khỏi gateway và service |
| Rotate | Thay credential cũ bằng credential mới theo quy trình overlap | Phát hành API key mới rồi revoke key cũ |

Deprecation thường có kế hoạch và thông báo trước; revoke có thể cần thực hiện ngay khi có compromise hoặc thay đổi quyền. Disable có thể tạm thời và có thể bật lại; revoke là hành động bảo mật có audit và thường cần cấp credential mới nếu muốn khôi phục quyền. Sunset loại bỏ endpoint khỏi đường phục vụ, còn revoke credential ngăn một identity cụ thể tiếp tục sử dụng.

### 1.1. Ví dụ phân biệt

- API /v1/orders được deprecate vì consumer cần chuyển sang /v2/orders; trong migration window, version cũ vẫn hoạt động nhưng phải tuân thủ security policy hiện hành.
- API key của một integration bị lộ; key đó cần revoke ngay, kể cả endpoint mà nó gọi chưa bị deprecate.
- Một tenant chấm dứt hợp đồng; client credentials và grants của tenant cần disable/revoke theo quy trình, sau đó xử lý data retention và route riêng nếu có.
- Một endpoint debug không có consumer hợp lệ; endpoint cần được gỡ khỏi gateway/runtime, không chỉ thêm nhãn deprecated.

## 2. Phạm vi tài sản cần quản lý vòng đời

Đừng chỉ nghĩ deprecation là việc đổi URL. Một API system có nhiều loại tài sản cần inventory và trạng thái lifecycle:

| Tài sản | Ví dụ | Hành động vòng đời |
|---|---|---|
| API version/endpoint | /v1/payments, legacy route | Deprecate, migrate consumer, sunset |
| Request/response field | Field cũ, field nhạy cảm | Deprecate, stop accepting/returning, remove |
| OAuth client/integration | Partner app, service client | Disable client, rotate secret, revoke grant |
| API key | Key theo integration hoặc tenant | Rotate, revoke, xác minh key cũ bị từ chối |
| Access/refresh token | JWT, opaque token | Expire, revoke, introspection/denylist |
| Signing/encryption key | Webhook signing key, KMS key | Rotate, revoke/disable version, re-sign nếu cần |
| TLS/mTLS certificate | Gateway, workload identity | Rotate, revoke certificate, cập nhật trust |
| Service account/role grant | Workload permission, support grant | Thu hồi scope/role, disable identity |
| Webhook subscription | Callback URL và signing secret | Disable subscription, rotate secret, ngừng delivery |
| Network/gateway policy | Route, allow-list, ingress mapping | Remove route/rule, verify runtime |
| SDK/client configuration | Mobile app, partner SDK | Publish migration, stop old behavior |

Mỗi tài sản nên có identifier không bí mật, owner, environment, tenant/client scope, purpose, ngày tạo, ngày hết hạn hoặc review, trạng thái, dependency và bằng chứng thay đổi. Không ghi secret value vào inventory.

## 3. Inventory và xác định owner trước khi deprecate

Không thể sunset an toàn nếu chưa biết ai đang dùng endpoint hoặc credential. Kết hợp nhiều nguồn để tránh bỏ sót consumer ít hoạt động:

- API gateway/ingress route và access logs.
- OpenAPI/contract registry và API catalog.
- OAuth client registry, API key store, certificate inventory và service account list.
- Usage ledger, rate-limit records và audit events.
- Distributed traces, job scheduler và batch configuration.
- Partner integration register, support ticket và owner metadata.
- Source code/SDK versions và deployment manifests.
- Webhook subscriptions, callback delivery logs và retry queues.

### 3.1. Endpoint/consumer inventory

| Trường | Mục đích |
|---|---|
| Service/API/version | Xác định API đang được quản lý |
| Host, route template, method | Xác định đường truy cập thực tế |
| Consumer/client ID | Xác định integration đã đăng ký |
| Tenant/account | Xác định phạm vi dữ liệu và quota |
| Owner/contact | Người chịu trách nhiệm migration |
| Credential ID/key ID | Liên kết credential mà không lưu secret |
| Last seen/usage window | Đánh giá mức sử dụng |
| Operation/data scope | Xác định side effect và độ nhạy cảm |
| Replacement/version | Hướng chuyển đổi |
| Deprecation/sunset date | Mốc lifecycle |
| Status/evidence reference | Theo dõi tiến độ và bằng chứng |

### 3.2. Đừng kết luận “không dùng” chỉ từ một cửa sổ ngắn

Consumer có thể chỉ chạy cuối tháng, cuối quý, khi đối soát hoặc khi disaster recovery. Mobile app cũ cũng có thể hoạt động không thường xuyên. Trước khi đánh dấu endpoint/credential không còn dùng:

1. Chọn usage window bao phủ chu kỳ nghiệp vụ phù hợp.
2. Xem cả success, denied, retry và asynchronous delivery.
3. Đối chiếu lịch batch, webhook và job vận hành.
4. Hỏi owner/partner nếu consumer còn hợp đồng hoặc SLA.
5. Kiểm tra có traffic qua gateway khác hoặc gọi backend trực tiếp không.
6. Ghi nhận mức độ tin cậy của kết luận và nguồn dữ liệu.

Không có traffic trong logs không chứng minh endpoint không reachable hoặc không có consumer. Runtime route inventory và network exposure vẫn phải được kiểm tra.

## 4. Lập kế hoạch deprecation

Một kế hoạch deprecation cần xác định mục tiêu, phạm vi, người bị ảnh hưởng, mốc thời gian và tiêu chí hoàn tất. Không dùng một ngày sunset chung cho mọi API nếu consumer, hợp đồng và rủi ro khác nhau.

### 4.1. Các quyết định trước khi thông báo

- Endpoint/version/field nào bị deprecate?
- Vì sao thay đổi: security, compatibility, performance, product lifecycle hay compliance?
- Replacement API/field là gì?
- Consumer nào đang sử dụng và ai là owner?
- Có thay đổi authentication, scope, tenant behavior hoặc response field không?
- API cũ có lỗ hổng cần disable ngay hay có thể duy trì trong migration window?
- Ngày thông báo, ngày deprecation có hiệu lực và ngày sunset?
- Consumer cần thời gian phát triển, test và release bao lâu?
- Có SDK, sample code và migration guide không?
- Tiêu chí nào cho phép chuyển sang bước sunset?

### 4.2. Migration window theo rủi ro

Thời gian deprecation nên dựa trên số lượng consumer, tần suất sử dụng, độ phức tạp schema, khả năng thay credential, tác động downtime, SLA, security risk và yêu cầu hợp đồng/pháp lý. Không có một khoảng thời gian cố định phù hợp cho mọi API.

Nếu endpoint cũ có cross-tenant access hoặc cho phép action trái quyền, cần sửa/disable ngay theo incident process; không giữ lỗ hổng đến ngày sunset chỉ để bảo đảm tương thích.

### 4.3. Thông báo deprecation

Thông báo cần nêu endpoint/version/field bị ảnh hưởng, thời điểm deprecation và sunset theo múi giờ rõ ràng, replacement và migration steps, thay đổi authentication/permission/schema/error/rate limit, cách test sandbox, owner hỗ trợ và hành vi sau sunset.

Có thể dùng các HTTP header phù hợp như Deprecation, Sunset và Link với quan hệ rel="deprecation" nếu API contract và gateway hỗ trợ. Header là tín hiệu bổ sung; không thay thông báo trực tiếp tới consumer hoặc tài liệu migration.

Ví dụ response header minh họa:

~~~http
Deprecation: @1780272000
Sunset: Wed, 30 Jun 2027 00:00:00 GMT
Link: <https://api.example.com/docs/migrate-v1>; rel="deprecation"
~~~

Giá trị thời gian chỉ minh họa định dạng; hãy dùng ngày thực tế đã được phê duyệt và kiểm tra parser của client. Không tự suy ra ngày sunset từ thời điểm deploy.

## 5. Checklist deprecation theo giai đoạn

### 5.1. Trước khi công bố

- [ ] Endpoint/version/field và môi trường bị ảnh hưởng được xác định chính xác.
- [ ] Security review đánh giá liệu endpoint cũ có thể tiếp tục phục vụ an toàn trong migration window.
- [ ] Inventory consumer, tenant, client ID, owner và credential ID đã được cập nhật.
- [ ] Usage window đủ bao phủ batch, webhook và consumer ít hoạt động.
- [ ] Replacement API và migration guide đã sẵn sàng.
- [ ] Contract/OpenAPI và SDK documentation đã được cập nhật.
- [ ] Ngày thông báo, ngày deprecation và sunset được phê duyệt.
- [ ] Error behavior sau sunset đã được định nghĩa.
- [ ] Monitoring/dashboard và alert cho traffic version cũ đã sẵn sàng.
- [ ] Có rollback/forward-fix plan và người chịu trách nhiệm.

### 5.2. Trong migration window

- [ ] Consumer nhận thông báo qua kênh đã đăng ký.
- [ ] Deprecation metadata được trả đúng theo contract nếu có.
- [ ] Traffic cũ và mới được đo riêng theo route/version/client.
- [ ] Consumer đã chuyển đổi được xác minh qua telemetry hoặc owner confirmation.
- [ ] Authentication/authorization của endpoint cũ vẫn được enforce.
- [ ] Không có field nhạy cảm hoặc security bypass chỉ tồn tại ở version cũ.
- [ ] Error rate, retry và support issue được theo dõi.
- [ ] Consumer không hoạt động được liên hệ theo lịch nghiệp vụ phù hợp.
- [ ] Exception gia hạn có owner, lý do, phạm vi và expiry.
- [ ] Không gia hạn chỉ vì không có số liệu usage đủ tin cậy.

### 5.3. Trước ngày sunset

- [ ] Owner xác nhận consumer đã migrate hoặc exception được phê duyệt.
- [ ] Usage trong cửa sổ cuối không cho thấy consumer hợp lệ chưa được xử lý.
- [ ] Gateway, ingress, CDN và service route removal đã được chuẩn bị.
- [ ] Test xác nhận endpoint mới hoạt động cho các consumer cần thiết.
- [ ] Test endpoint cũ không còn thực hiện business side effect sau sunset.
- [ ] Cache, SDK, webhook retry và scheduled job có kế hoạch xử lý.
- [ ] Support/on-call có runbook và thông điệp cho request còn gọi endpoint cũ.
- [ ] Audit evidence và change approval đã được lưu.

### 5.4. Sau sunset

- [ ] Gateway mapping và backend handler cũ đã bị gỡ hoặc vô hiệu hóa.
- [ ] Không còn direct backend/alternate host route phục vụ endpoint cũ.
- [ ] Request cũ nhận response đã công bố, không fallback sang implementation yếu hơn.
- [ ] Không có database mutation, outbox event, queue job hoặc downstream call từ request sunset.
- [ ] CDN/proxy/client cache không tiếp tục trả dữ liệu cũ trái policy.
- [ ] Telemetry ghi nhận consumer còn gọi và route đến owner phù hợp.
- [ ] Credential chỉ dùng cho endpoint cũ được revoke nếu không còn purpose hợp lệ.
- [ ] API catalog, contract registry và SDK docs phản ánh trạng thái retired.
- [ ] Evidence pack có kết quả xác minh runtime và người phê duyệt closure.

## 6. Kế hoạch revoke credential và grant

Revoke có thể ảnh hưởng trực tiếp đến availability và business operation. Trước khi revoke, xác định credential nào, identity nào, scope nào và resource nào bị ảnh hưởng. Khi credential bị compromise, containment thường quan trọng hơn migration window; không trì hoãn revoke chỉ để chờ consumer phản hồi.

### 6.1. Các trường hợp cần revoke

- Secret/key/token bị lộ hoặc nghi ngờ bị lộ.
- Nhân viên/service account/partner không còn nhu cầu truy cập.
- Tenant/account bị đóng hoặc bị suspend theo policy.
- Scope/role/grant được cấp sai hoặc quá rộng.
- Certificate bị compromise hoặc workload identity không còn tin cậy.
- Integration bị thay thế và credential cũ không còn dùng.
- Có dấu hiệu abuse, credential sharing hoặc usage không phù hợp.
- Credential vượt quá thời hạn review/rotation theo policy.

### 6.2. Phân loại revoke

| Loại | Hành động | Lưu ý |
|---|---|---|
| API key | Đánh dấu key ID revoked tại nơi xác minh key | Xác minh mọi gateway/backend replica nhận trạng thái mới |
| OAuth client secret | Disable secret cũ, phát hành secret mới hoặc revoke client | Kiểm tra overlap và client credentials grant |
| Access token opaque | Revoke/introspection state | Cache introspection phải có TTL/invalidation phù hợp |
| JWT access token | Denylist theo jti, revoke session/grant hoặc giảm lifetime | JWT tự chứa thường không tự mất hiệu lực khi database thay đổi |
| Refresh token | Revoke token/family/session | Ngăn refresh tạo access token mới |
| Signing key | Ngừng tin key ID, rotate key và xử lý token/event đã ký | Phân biệt key ký token, webhook và key mã hóa |
| TLS/mTLS certificate | Revoke certificate/identity và cấp mới | Kiểm tra trust store, CRL/OCSP hoặc workload CA behavior |
| Service account/grant | Disable identity hoặc thu hồi role/scope | Kiểm tra job và workload phụ thuộc |
| Webhook secret | Rotate signing secret, từ chối signature cũ theo policy | Hỗ trợ overlap có thời hạn nếu không phải compromise |

### 6.3. JWT và giới hạn thu hồi tức thời

JWT access token tự chứa có thể tiếp tục được resource server chấp nhận đến khi hết hạn nếu verifier chỉ kiểm tra chữ ký và claim. Đổi trạng thái user hoặc revoke refresh token không tự động làm mọi access JWT đã phát hành mất hiệu lực.

Các lựa chọn gồm access token lifetime ngắn; token introspection/session lookup với cache TTL có kiểm soát; denylist theo jti hoặc token/session identifier; key rotation/revocation khi signing key bị compromise; và sender-constrained token hoặc workload certificate khi phù hợp.

Không đưa raw token vào denylist/log. Dùng identifier hoặc hash an toàn theo thiết kế. Cần đo propagation delay giữa revoke store, gateway cache và resource server.

### 6.4. Rotation có overlap và revoke có thời điểm rõ

Với rotation định kỳ, có thể phát hành credential mới, cập nhật consumer, xác minh traffic bằng credential mới rồi revoke credential cũ. Overlap cần có start/end time, credential ID cũ/mới, consumer owner, scope, kế hoạch nếu migration thất bại và điều kiện revoke credential cũ.

Nếu key cũ bị compromise, không kéo dài overlap chỉ vì integration chưa sẵn sàng. Dùng containment plan, cấp credential mới qua kênh an toàn và phối hợp owner theo incident process.

## 7. Revoke runbook: từ quyết định đến xác minh

Một quy trình revoke đáng tin cậy gồm các bước:

1. **Xác định đối tượng:** credential/grant ID, principal, client, tenant, environment và scope.
2. **Xác định lý do:** compromise, owner departure, contract end, overprivilege, routine rotation hoặc incident.
3. **Đánh giá blast radius:** endpoint, service, job, webhook, data access và downstream dependency bị ảnh hưởng.
4. **Phê duyệt theo policy:** ghi actor yêu cầu, approver và emergency exception nếu có.
5. **Containment:** disable/revoke ở source of truth và các verifier cần thiết.
6. **Propagate:** invalidate cache/session, cập nhật gateway/mesh/resource server hoặc trust store.
7. **Verify negative path:** thử credential cũ qua mọi entry point liên quan và xác nhận bị từ chối.
8. **Verify no side effect:** không tạo job, mutation, event hoặc downstream call.
9. **Issue replacement nếu cần:** cấp credential mới với least privilege và expiry phù hợp.
10. **Monitor:** tìm usage tiếp tục bằng credential cũ, lỗi consumer và dấu hiệu credential reuse.
11. **Close:** lưu evidence, cập nhật inventory và ghi người xác nhận.

Với credential compromise, containment và revoke cần được ưu tiên; việc liên hệ consumer có thể diễn ra song song. Không chờ đủ audit report mới vô hiệu hóa credential bị lộ.

### 7.1. Xác minh revoke qua mọi đường

Kiểm tra public API gateway và mọi region/zone; internal gateway hoặc alternate hostname; direct backend path trong network test zone được phép; service mesh/workload path; API key validation cache và token introspection cache; background worker, batch job và message consumer; webhook delivery/retry queue; credential được copy trong secret store, deployment hoặc old replica.

Một lần request nhận 401 ở gateway chưa đủ nếu backend có thể bị gọi trực tiếp hoặc một region chưa nhận revoke event. Bằng chứng nên cho thấy credential cũ bị từ chối ở các verifier có liên quan.

### 7.2. Không vô tình revoke nhầm credential dùng chung

Nếu nhiều integration dùng chung một key/service account, revoke có thể ảnh hưởng nhiều tenant. Đây là dấu hiệu thiết kế credential scope chưa tốt. Trước khi revoke, xác định dependency; nếu compromise đang diễn ra, vẫn cần containment nhưng phải theo incident plan. Sau đó tách credential theo client/tenant/workload để lần sau có thể revoke có chọn lọc.

## 8. Audit evidence: cần chứng minh điều gì?

Audit evidence không chỉ là một dòng log “revoke succeeded”. Nó phải cho phép reviewer tái dựng ai quyết định, tài sản nào bị ảnh hưởng, thay đổi nào được áp dụng và kết quả đã được xác minh ra sao.

Một evidence record tốt trả lời:

- **Who:** ai yêu cầu, phê duyệt, thực hiện và xác minh?
- **What:** endpoint/version/credential/grant nào bị thay đổi?
- **Why:** lý do và ticket/incident/change reference nào?
- **When:** thời điểm yêu cầu, phê duyệt, thực thi và xác minh theo UTC?
- **Where:** environment, region, gateway, service và verifier nào?
- **How:** policy/config/API operation nào đã thực hiện?
- **Result:** thành công, thất bại, partial hay pending?
- **Verification:** credential/route cũ đã bị từ chối và không còn side effect chưa?
- **Exception:** có ngoại lệ, overlap hoặc rollback không; ai chịu trách nhiệm và khi nào hết hạn?

### 8.1. Evidence tối thiểu cho deprecation

- Approved deprecation plan và owner.
- Inventory consumer/tenant/client bị ảnh hưởng.
- Bản thông báo đã gửi, thời điểm và danh sách recipient/channel.
- Contract/OpenAPI/SDK version trước và sau.
- Usage report trong migration window.
- Migration confirmation hoặc exception được phê duyệt.
- Sunset change/deployment record.
- Test result cho route cũ, route mới và side effect.
- Runtime/gateway verification sau deploy.
- Closure approval và residual risk.

### 8.2. Evidence tối thiểu cho revoke

- Credential/grant ID không bí mật và principal/client liên quan.
- Revoke reason, incident/change ticket và approver.
- Timestamp yêu cầu, thời điểm source of truth đổi trạng thái.
- Revoke operation result từ identity/key/certificate provider.
- Cache/session/replica propagation status.
- Negative test với credential cũ.
- Test qua các entry point cần thiết.
- Bằng chứng không có side effect sau khi bị từ chối.
- Replacement credential ID nếu có, không kèm secret.
- Monitoring kết quả sau revoke và người xác minh.

### 8.3. Evidence cho audit integrity

Audit trail cần được bảo vệ khỏi sửa/xóa trái phép:

- Ghi append-only hoặc dùng storage có immutability/WORM khi yêu cầu.
- Đồng bộ thời gian và ghi timestamp UTC.
- Gắn actor, operation ID, correlation ID và change reference.
- Phân quyền đọc/xuất audit riêng với quyền sửa cấu hình.
- Theo dõi việc thay đổi retention, export và deletion.
- Có checksum/signature hoặc chain/integrity control khi threat model yêu cầu.
- Backup và kiểm thử khả năng truy xuất evidence.
- Ghi nhận log pipeline drop, ingestion delay và storage failure.

Không lưu secret/token raw trong audit evidence. Với credential, lưu key ID, certificate serial/thumbprint hoặc token/session identifier phù hợp; không lưu private key, API key value hoặc bearer token.

## 9. Mẫu audit event và change record

Ví dụ structured audit event:

~~~json
{
  "eventType": "api.credential.revoked",
  "eventId": "evt-01J...",
  "occurredAt": "2026-11-18T13:00:00Z",
  "actor": {
    "id": "operator-17",
    "type": "human"
  },
  "subject": {
    "clientId": "partner-reporting",
    "tenantId": "tenant-15"
  },
  "credential": {
    "type": "api_key",
    "credentialId": "key-42",
    "version": 3
  },
  "action": "revoke",
  "reasonCode": "SUSPECTED_COMPROMISE",
  "changeReference": "SEC-4821",
  "environment": "production",
  "result": "success",
  "verification": {
    "oldCredentialRejected": true,
    "entryPointsChecked": 4,
    "sideEffectsObserved": 0
  }
}
~~~

Đây là ví dụ minh họa; schema cần phù hợp audit platform. Không đưa secret, raw token, private key hoặc toàn bộ request vào event. Trường entryPointsChecked chỉ là số lượng; report chi tiết nên tham chiếu evidence artifact có quyền truy cập hạn chế.

### 9.1. Mẫu change record

~~~yaml
change:
  id: SEC-4821
  type: credential-revocation
  environment: production
  owner: api-platform
  approver: security-on-call
  reason: suspected-compromise
  target:
    client_id: partner-reporting
    credential_id: key-42
    credential_type: api-key
  requested_at: "2026-11-18T12:55:00Z"
  executed_at: "2026-11-18T13:00:00Z"
  verification:
    old_credential_rejected: true
    direct_backend_checked: true
    side_effects_observed: 0
  evidence:
    - audit-event: evt-01J...
    - test-run: run-2026-11-18-042
  status: closed
~~~

Mẫu không phải cấu hình revoke có thể chạy trực tiếp. Thay identifier, owner, approval và timestamp bằng giá trị thực của change; không ghi credential value.

## 10. Evidence retention, privacy và access control

Audit evidence có thể chứa user ID, tenant ID, IP, endpoint, business reference và incident detail. Cần lưu đủ để điều tra nhưng không giữ dữ liệu không cần thiết vô thời hạn.

Thiết kế retention:

- Xác định loại evidence và mục đích: security audit, compliance, billing, operational troubleshooting.
- Áp retention theo policy/pháp lý và data classification.
- Phân biệt raw logs, summarized audit events và evidence artifact.
- Redact token, secret, password, request body và PII không cần thiết.
- Mã hóa at rest/in transit và giới hạn role đọc.
- Audit cả việc truy cập/export evidence.
- Legal hold/incident hold có owner, scope và expiry/review.
- Xóa hoặc archive theo policy, giữ chain-of-custody nếu cần.

Không dùng retention dài để bù cho schema audit kém. Evidence cần cấu trúc, có timestamp và correlation ID để truy xuất mà không cần lưu toàn bộ payload nhạy cảm.

## 11. Revoke và deprecation có liên quan đến cache, replica và asynchronous work

Thay đổi trạng thái ở một database không bảo đảm mọi component nhận ngay. Credential có thể nằm trong cache gateway, JWKS cache, introspection cache, secret mount, environment variable, worker process hoặc queue.

Kiểm tra TTL/invalidation của API key cache; JWKS/key cache và hành vi khi key bị remove; token introspection cache và session revocation propagation; secret rotation/reload trong pod và worker; certificate trust store, CRL/OCSP và mesh certificate refresh; CDN/gateway route cache và DNS propagation; retry queue, scheduled job, delayed message và in-flight request đã xác thực trước thời điểm revoke.

### 11.1. In-flight request

Một request đã vượt qua authentication trước khi revoke có thể vẫn đang xử lý. Policy cần xác định revoke chỉ chặn request mới hay phải hủy cả operation đang chạy. Với action tài chính, admin hoặc export dữ liệu nhạy cảm, có thể cần kiểm tra authorization gần thời điểm commit/side effect và hỗ trợ cancellation.

Không thể giả định revoke credential sẽ rollback một payment hoặc database transaction đã commit. Nếu action đã xảy ra, cần reconciliation/compensation theo workflow; audit phải phân biệt request được chấp nhận trước revoke với request bị từ chối sau revoke.

### 11.2. Async job và webhook

Job đã enqueue có thể chạy sau khi credential nguồn bị revoke. Cần xác định job được ủy quyền tại thời điểm enqueue hay phải kiểm tra lại grant khi thực thi. Với webhook, subscription bị disable cần dừng retry/delivery theo contract; secret rotate cần xác minh receiver đã chuyển key. Không để queue giữ payload nhạy cảm lâu hơn policy.

## 12. Emergency revoke và incident response

Khi có dấu hiệu credential compromise, ưu tiên containment và giảm blast radius. Quy trình khẩn cấp cần được chuẩn bị trước:

1. Xác minh credential ID/principal/tenant bị ảnh hưởng mà không chia sẻ secret.
2. Tìm scope, endpoint, region và service đã được credential sử dụng.
3. Disable/revoke credential tại source of truth.
4. Invalidate cache/session và propagate đến verifier.
5. Chặn đường alternate/direct backend nếu có.
6. Kiểm tra activity từ thời điểm compromise nghi ngờ: success, denied, export, mutation và downstream action.
7. Xác định dữ liệu bị đọc hoặc thay đổi; kích hoạt incident response phù hợp.
8. Cấp credential mới qua secret manager/kênh đã xác minh nếu integration còn hợp lệ.
9. Theo dõi usage của credential cũ và attempts tiếp tục sử dụng.
10. Lưu audit evidence, timeline, approver và verification.
11. Review nguyên nhân: secret exposure, shared credential, overly broad scope hoặc thiếu rotation.

Không gửi credential mới trong email/chat không bảo mật hoặc ghi vào ticket. Dùng secret manager hoặc kênh trao đổi được phê duyệt. Không bật lại credential cũ chỉ vì client chưa kịp cập nhật.

## 13. Rollback và exception an toàn

Rollback deprecation và rollback revoke có mức rủi ro khác nhau:

- Một route sunset có thể cần khôi phục tạm thời nếu migration gây outage; route khôi phục vẫn phải giữ security policy hiện hành, giới hạn thời gian và có owner.
- Credential đã revoke do compromise không nên được kích hoạt lại. Cấp credential mới với scope tối thiểu và điều tra nguyên nhân.
- Nếu revoke nhầm credential hợp lệ, thực hiện quy trình cấp mới; không nhất thiết phục hồi cùng secret cũ.
- Temporary exception cần người phê duyệt, mục tiêu, tenant/client scope, expiry, monitoring và kế hoạch gỡ bỏ.

Trước khi rollback route, kiểm tra liệu API cũ có policy yếu hơn API mới, có field nhạy cảm hoặc endpoint khác đã thay đổi business invariant không. Rollback không được tái mở một security bypass đã biết.

## 14. Test plan và bằng chứng xác minh

Không chỉ kiểm tra configuration file đã thay đổi. Cần test behavior qua runtime.

| Scenario | Expected result | Evidence cần lưu |
|---|---|---|
| Deprecated endpoint trong migration window | Hoạt động theo policy hiện hành và phát deprecation metadata | Request/response đã redact, contract version |
| Endpoint sau sunset | Không đến business handler; status theo contract | Gateway/runtime test, side-effect assertion |
| Credential cũ sau revoke | Bị từ chối ở mọi verifier cần thiết | Negative test, audit event, propagation status |
| Credential mới sau rotation | Chỉ hoạt động với scope đã cấp | Positive test và credential ID |
| JWT đã revoke | Bị từ chối theo cơ chế revoke đã chọn | Introspection/denylist test và timestamp |
| Key cache chưa refresh | Không tạo cửa sổ cho credential compromise vượt policy | Cache invalidation/TTL evidence |
| Direct backend path | Không bypass gateway authentication | Network test và backend decision |
| Cross-tenant request | Không đọc/sửa object tenant khác | Test principal/object fixture |
| Async job sau revoke | Hành vi theo policy enqueue-time/execute-time | Queue/worker audit và operation status |
| Webhook secret rotation | Signature key mới được nhận; key cũ bị từ chối sau overlap | Delivery test và receiver confirmation |
| Certificate revoke/rotate | Workload cert cũ không được trust theo policy | mTLS test, serial/identity evidence |
| Audit pipeline unavailable | Durable fallback hoặc action nhạy cảm bị dừng theo policy | Failure injection và recovery record |
| Evidence export | Chỉ role được phép truy cập; không chứa secret | Access audit và redaction scan |

### 14.1. Negative test cho credential cũ

Với mỗi credential bị revoke, gửi request đến endpoint đại diện qua public gateway; thử route/version liên quan khác nếu credential có scope rộng; kiểm tra region/replica khác; kiểm tra service-to-service path nếu credential được dùng nội bộ; xác minh response deny và không có side effect; kiểm tra log/audit không ghi raw credential.

Dùng test credential đã được chuẩn bị, không sao chép secret production vào test script hoặc report.

### 14.2. Test deprecation và sunset

- Consumer cũ nhận thông báo đúng.
- Consumer đã migrate hoạt động với API mới.
- Route cũ không tạo side effect sau sunset.
- API cũ không trở thành fallback sau khi API mới trả 401/403.
- Field cũ bị loại bỏ khỏi mọi response path.
- Gateway, application và cache đều có trạng thái phù hợp.
- Traffic sau sunset được ghi nhận và route đến owner.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ thông báo deprecation, không sunset route | Endpoint cũ tiếp tục hoạt động vô thời hạn | Owner, deadline, traffic gate và runtime verification |
| Chỉ xóa UI/SDK call | API vẫn có thể gọi trực tiếp | Gỡ/disable route ở gateway và backend |
| Revoke key ở một gateway | Region/backend khác vẫn chấp nhận key | Xác minh mọi verifier, cache và direct path |
| Nghĩ JWT revoke tự động có hiệu lực ngay | Token tự chứa vẫn hợp lệ đến expiry | Short lifetime, introspection hoặc denylist |
| Revoke refresh token nhưng bỏ access token | Access token hiện tại tiếp tục hoạt động | Xác định access-token revocation strategy |
| Rotation không có overlap/owner | Integration downtime hoặc giữ key cũ quá lâu | Kế hoạch overlap, verify và revoke deadline |
| Shared API key cho nhiều tenant | Không revoke chọn lọc, blast radius lớn | Credential riêng theo client/tenant/workload |
| Chỉ lưu ticket “done” làm evidence | Không chứng minh runtime đã từ chối credential cũ | Audit event và negative test |
| Audit log chứa raw secret | Evidence store trở thành nơi rò rỉ credential | Chỉ lưu ID/thumbprint/hash phù hợp |
| Không kiểm tra async queue | Job tiếp tục chạy sau revoke ngoài policy | Recheck grant hoặc define enqueue-time authorization |
| Re-enable credential compromise để rollback | Attacker có thể tiếp tục truy cập | Cấp credential mới và giữ old credential revoked |
| Usage window quá ngắn | Bỏ sót batch/DR consumer | Chọn cửa sổ theo chu kỳ nghiệp vụ |

## 16. Checklist tổng hợp trước khi đóng change

### Deprecation/sunset

- [ ] Endpoint/version/field và consumer scope đã được xác định.
- [ ] Owner, tenant/client và credential dependency đã được ghi nhận.
- [ ] Usage window đủ dài và có đối chiếu lịch batch/webhook.
- [ ] Replacement API, migration guide và thông báo đã sẵn sàng.
- [ ] Deprecation/sunset dates được phê duyệt và dùng UTC/múi giờ rõ.
- [ ] Endpoint cũ vẫn enforce security baseline trong migration window.
- [ ] Consumer migration hoặc exception đã được xác nhận.
- [ ] Gateway/backend/cache/alternate route removal đã được triển khai.
- [ ] Negative test chứng minh route cũ không còn tạo side effect.
- [ ] API catalog/contract/SDK/inventory đã cập nhật trạng thái.

### Credential revoke/rotation

- [ ] Credential ID, principal, client, tenant, scope và environment được xác định.
- [ ] Revoke reason, requester, approver và change/incident reference được ghi.
- [ ] Blast radius và async/in-flight operation được đánh giá.
- [ ] Source of truth đã revoke/disable credential.
- [ ] Cache, replica, gateway, mesh, worker và verifier đã nhận thay đổi.
- [ ] Credential cũ bị từ chối qua mọi entry point liên quan.
- [ ] Không có database mutation, job, event hoặc downstream side effect trái policy.
- [ ] Credential thay thế có least privilege, expiry và owner nếu cần.
- [ ] Shared credential và dependency không được bỏ sót.
- [ ] Monitoring không còn success traffic bằng credential cũ.

### Audit evidence và closure

- [ ] Evidence trả lời who/what/why/when/where/how/result/verification.
- [ ] Audit event có timestamp UTC, actor, target ID, operation/change reference.
- [ ] Có test result và runtime verification, không chỉ config diff.
- [ ] Evidence không chứa token, secret, private key hoặc PII không cần thiết.
- [ ] Storage có access control, integrity protection và retention policy.
- [ ] Exception/rollback có owner, expiry, approval và residual risk.
- [ ] Người xác minh độc lập hoặc reviewer phù hợp đã xác nhận kết quả.
- [ ] Inventory, API catalog, credential registry và runbook đã cập nhật.
- [ ] Closure record liên kết được tới evidence artifact và test run.

## 17. Mẫu closure record

Một change chỉ nên đóng khi có bằng chứng phù hợp:

~~~yaml
closure:
  change_id: SEC-4821
  target:
    api: orders
    version: v1
    endpoint: /v1/orders/{orderId}
    credential_ids:
      - key-42
  lifecycle_action:
    deprecation_announced: true
    sunset_completed: true
    credentials_revoked: true
  verification:
    gateway_route_removed: true
    backend_route_unreachable: true
    old_credential_rejected: true
    cross_tenant_test_passed: true
    no_side_effect_observed: true
  evidence:
    change_record: SEC-4821
    test_run: run-2026-11-18-042
    audit_event_ids:
      - evt-01J...
  residual_risk:
    accepted: false
    exceptions: []
  reviewed_by: security-reviewer
  closed_at: "2026-11-18T15:00:00Z"
  status: closed
~~~

Đây là cấu trúc minh họa, không phải schema bắt buộc. Giá trị true chỉ được ghi khi có evidence tương ứng. Nếu backend route vẫn reachable qua một network path, không được ghi backend_route_unreachable là true chỉ vì public gateway mapping đã bị xóa.

## 18. Nguyên tắc đóng vòng đời an toàn

Deprecation quản lý thay đổi có thời hạn; revoke thu hồi một quyền đã cấp; audit evidence chứng minh thay đổi đã diễn ra và được xác minh. Ba việc cần được liên kết nhưng không thể thay thế nhau. Khi triển khai, hãy bắt đầu từ inventory và owner, xác định consumer/credential/data scope, thông báo và migration theo rủi ro, thực thi sunset hoặc revoke tại mọi verifier, rồi kiểm tra negative path và side effect ở runtime.

Một change chưa hoàn tất nếu chỉ có cấu hình mới mà chưa xác minh gateway, backend, cache, worker và alternate path. Tương tự, một audit record không đủ nếu không có actor, timestamp, target ID và kết quả kiểm thử. Checklist chỉ nên được đánh dấu hoàn thành khi evidence có thể truy xuất, không chứa secret và đủ để reviewer độc lập xác nhận endpoint/credential cũ không còn quyền truy cập ngoài policy.
