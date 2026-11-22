# Canary, rollback và policy migration

Thay đổi API security thường có tác động rộng hơn một lần deploy ứng dụng. Một policy mới có thể cho phép hoặc từ chối quyền truy cập khác trước; một thay đổi JWT claim có thể làm service cũ không xác minh được token; một cấu hình gateway có thể chặn nhầm traffic hợp lệ hoặc vô tình mở route nhạy cảm. Nếu triển khai đồng loạt, lỗi có thể ảnh hưởng mọi tenant và mọi client cùng lúc.

Canary deployment giúp đưa thay đổi tới một phần nhỏ traffic hoặc một nhóm tenant trước khi mở rộng. Rollback đưa hệ thống về trạng thái vận hành an toàn khi có sự cố. Policy migration chuyển dần từ mô hình quyền/cấu hình cũ sang mô hình mới mà vẫn giữ tính nhất quán giữa gateway, service, worker và dữ liệu. Ba kỹ thuật cần được thiết kế cùng nhau: triển khai theo từng bước, đo đúng tín hiệu bảo mật và có đường quay lui không làm sống lại quyền đã bị thu hồi.

Trong API Security, mục tiêu không chỉ là giữ uptime. Rollout phải bảo đảm authentication, function authorization, object authorization, tenant isolation, token revocation và audit tiếp tục có hiệu lực ở mọi phiên bản đang chạy.

## 1. Canary deployment là gì?

Canary là cách triển khai phiên bản hoặc policy mới tới một phạm vi nhỏ trước, quan sát kết quả rồi mở rộng theo từng bước. Phạm vi canary có thể được xác định theo:

- Tỷ lệ request, ví dụ 1%, 5%, 10% rồi tăng dần.
- Một nhóm tenant thử nghiệm đã được đồng ý.
- Một nhóm client/API key hoặc service identity.
- Một vùng/cluster/availability zone.
- Một nhóm endpoint hoặc operation ít rủi ro hơn.
- Một loại policy cụ thể, ví dụ chỉ thay đổi quyền đọc trước khi thay đổi quyền ghi.

Canary khác với deploy đồng loạt ở chỗ phạm vi tác động ban đầu được giới hạn và có tiêu chí rõ để tiếp tục, tạm dừng hoặc rollback. Tuy nhiên, canary không tự bảo đảm an toàn: nếu nhóm canary chứa tenant lớn nhất hoặc endpoint nhạy cảm nhất, rủi ro vẫn có thể cao. Phải chọn cohort phù hợp với mục tiêu kiểm chứng và có khả năng cô lập.

## 2. Vì sao API security cần rollout theo giai đoạn?

Một thay đổi bảo mật có thể gây ra nhiều loại lỗi:

| Thay đổi | Rủi ro khi rollout |
|---|---|
| Thêm scope bắt buộc cho endpoint | Client cũ nhận `403` dù nghiệp vụ trước đó hợp lệ |
| Thay đổi claim `tenant_id` hoặc audience | Token đang phát hành không còn được service mới chấp nhận |
| Chuyển từ role sang permission/ABAC | Mapping sai làm cấp thừa quyền hoặc từ chối nhầm |
| Thêm object-level authorization | Query thiếu quan hệ grant có thể chặn nhầm user được chia sẻ hợp lệ |
| Thay đổi gateway route/auth policy | Gateway và backend có thể không đồng bộ |
| Thu hồi API key hoặc OAuth grant | Integration đang hoạt động có thể ngừng đột ngột |
| Thay đổi cache key hoặc policy cache | Quyền cũ có thể tồn tại trong cache hoặc cache miss gây tải tăng |
| Thay đổi webhook signature/key version | Event hợp lệ bị từ chối hoặc key cũ tiếp tục được chấp nhận quá lâu |
| Thay đổi rate limit/cost budget | Một tenant hoặc operation có thể bị throttle ngoài dự kiến |

Với hệ thống multi-tenant, lỗi authorization có thể làm lộ dữ liệu chéo tenant hoặc làm gián đoạn một nhóm khách hàng. Rollout có kiểm soát giúp phát hiện sớm khác biệt giữa policy dự kiến và quyết định thực tế.

## 3. Phân biệt rollout ứng dụng và rollout policy

Hai loại thay đổi có liên quan nhưng cần quan sát riêng:

- **Application rollout:** thay binary/container, route, schema, query hoặc business logic.
- **Policy rollout:** thay rule, role/permission mapping, tenant condition, token claim requirement, gateway policy hoặc authorization data.

Một release có thể thay cả hai, nhưng nếu có thể hãy tách chúng thành các bước tương thích để xác định nguyên nhân khi có lỗi. Ví dụ, deploy service có khả năng đọc cả claim cũ và claim mới trước; sau đó chuyển issuer sang claim mới; cuối cùng mới bỏ hỗ trợ claim cũ.

Không để policy mới chỉ tồn tại ở gateway trong khi service vẫn dùng policy cũ, hoặc ngược lại. Xác định nguồn quyết định authoritative cho từng loại kiểm soát và cách các lớp đồng bộ version.

## 4. Chuẩn bị trước khi canary

Trước khi triển khai, tạo một release record có thể review:

| Hạng mục | Nội dung cần xác định |
|---|---|
| Change ID/version | Mã release, phiên bản ứng dụng và policy bundle |
| Security intent | Quyền nào được thêm, bỏ hoặc thay đổi; endpoint/object nào bị ảnh hưởng |
| Affected callers | Browser, mobile, partner, service account, worker hoặc webhook |
| Tenant cohort | Tenant nội bộ/test/early adopter và lý do chọn |
| Expected decisions | Một số trường hợp allow/deny đại diện trước và sau thay đổi |
| Compatibility | Token, client, database schema, cache và message version có tương thích không |
| Metrics | Authentication failure, authorization allow/deny, latency, error, tenant impact |
| Stop conditions | Ngưỡng tự động dừng hoặc rollback |
| Rollback plan | Phiên bản code/config quay về và các giới hạn an toàn |
| Owner/approver | Người chịu trách nhiệm kỹ thuật, security và vận hành |

Ghi rõ những quyền nào là nhạy cảm: admin, export, refund, role management, tenant configuration, secret access và dữ liệu cá nhân. Những thay đổi này cần cohort nhỏ hơn, kiểm tra thủ công và approval phù hợp.

## 5. Chọn canary cohort có kiểm soát

Không nên chọn cohort chỉ bằng cách lấy ngẫu nhiên một phần request nếu request thuộc nhiều tenant và mức độ rủi ro khác nhau. Cần cân nhắc:

- Tenant thử nghiệm có dữ liệu giả lập hoặc đã đồng ý tham gia.
- Quy mô và kiểu traffic đại diện cho các trường hợp thật.
- Không đưa tenant nhạy cảm hoặc tenant có yêu cầu compliance cao vào canary đầu tiên nếu chưa có phê duyệt.
- Có thể xác định request thuộc cohort bằng identity/tenant context đã xác minh, không dùng header do client tự gửi.
- Một tenant không thể tự bật canary cho tenant khác bằng cách gửi `X-Canary: true`.
- Có thể loại trừ endpoint thao tác không thể đảo ngược trong giai đoạn đầu.

Canary theo tenant phù hợp để kiểm tra policy và data migration vì quyền thường gắn với tenant. Canary theo tỷ lệ traffic phù hợp để kiểm tra hiệu năng hoặc độ ổn định của binary. Có thể kết hợp cả hai, nhưng cần tránh cùng một request được đánh giá bởi hai policy khác nhau trong một transaction.

## 6. Progressive delivery theo từng bước

Một lịch rollout minh họa:

| Giai đoạn | Phạm vi minh họa | Điều kiện chuyển bước |
|---|---:|---|
| Internal validation | Test tenant và synthetic traffic | Security regression, contract và smoke test pass |
| Canary 1 | 1% hoặc một nhóm tenant nhỏ | Không có critical security regression; metric trong ngưỡng |
| Canary 2 | 5% | Không có cross-tenant access; deny/allow delta được giải thích |
| Canary 3 | 10–25% | Latency, error, quota và audit ổn định |
| Expansion | 50% | Các cohort và client chính đã được kiểm tra |
| General availability | 100% | Owner xác nhận; cảnh báo và rollback vẫn hoạt động |

Các tỷ lệ chỉ là ví dụ. Một thay đổi permission nhạy cảm có thể cần rollout theo tenant allowlist thay vì phần trăm traffic. Một thay đổi parser không liên quan quyền có thể dùng tỷ lệ request. Không mở rộng chỉ vì đã hết thời gian chờ; phải đánh giá tín hiệu và kiểm tra dữ liệu thực tế.

Giữ mỗi bước đủ lâu để quan sát traffic đại diện. Nếu API chỉ được gọi theo lịch hàng ngày hoặc cuối tháng, một canary kéo dài vài phút không chứng minh tương thích.

## 7. Đo cả availability lẫn security correctness

Canary API security cần theo dõi hai nhóm tín hiệu.

### Reliability và performance

- Request rate, success/error rate và status code.
- Latency p50/p95/p99.
- Timeout, retry, circuit breaker và queue depth.
- CPU, memory, thread/connection pool và database query latency.
- Gateway/backend 5xx và dependency failure.

### Security decision và data boundary

- Authentication success/failure theo issuer/client type.
- Authorization allow/deny theo policy version, action và endpoint.
- Chênh lệch quyết định giữa policy cũ và policy mới.
- Cross-tenant/object authorization denial và test canary.
- Token revocation propagation time.
- Request tới route không còn được công bố.
- Số lần dùng credential cũ hoặc claim version cũ.
- Rate-limit rejection và cost theo tenant/operation.
- Audit event bị thiếu, trễ hoặc không ghi được.

Không đưa bearer token, email, raw object ID hoặc dữ liệu cá nhân vào metric label. Dùng route template, policy version, action class và tenant reference đã được kiểm soát. Với điều tra chi tiết, dùng audit log có quyền truy cập và retention phù hợp.

## 8. Shadow evaluation trước khi thay policy

Khi thay đổi authorization policy, có thể chạy policy mới ở chế độ *shadow* trước khi dùng nó để quyết định thật:

1. Policy cũ vẫn là nguồn quyết định cho request.
2. Service tính thêm kết quả của policy mới trên cùng context đáng tin cậy.
3. Ghi nhận kết quả cũ/mới và lý do khác biệt ở dạng an toàn.
4. Không để kết quả shadow tạo side effect hoặc thay đổi response.
5. Phân loại chênh lệch: quyền cần thu hồi, quyền mới hợp lệ, mapping thiếu, dữ liệu ACL chưa migrate hoặc lỗi policy.
6. Sửa policy/data và chạy lại test trước khi chuyển sang enforcement.

Ví dụ:

| Caller/action/object | Policy cũ | Policy mới | Việc cần làm |
|---|---|---|---|
| Alice đọc invoice của mình | Allow | Allow | Không có chênh lệch |
| Alice đọc invoice được chia sẻ | Allow | Deny | Kiểm tra migration grant/relationship |
| Bob đọc invoice tenant khác | Allow | Deny | Có thể là lỗ hổng cũ; không giữ allow chỉ để giảm lỗi |
| Finance user export report | Allow | Allow | Kiểm tra scope và quota mới |
| User thường refund payment | Deny | Allow | Dừng rollout, kiểm tra mapping quyền |

Shadow mode không được ghi payload hoặc credential vào log. Chỉ ghi policy ID/version, action, decision, reason code và reference phù hợp.

Không sử dụng shadow result để “học” tự động rồi mở quyền. Các chênh lệch cần được owner/security review và xác định rõ quyết định mong muốn.

## 9. Policy migration: chuyển từ role sang permission hoặc ABAC

Một migration phổ biến là chuyển từ role coarse-grained sang permission chi tiết hoặc policy dựa trên attribute/relationship. Ví dụ trước đây:

```text
ROLE_FINANCE -> được đọc, export và refund mọi invoice
```

Sau migration:

```text
invoices:read    -> đọc invoice trong tenant được phép
invoices:export  -> export tập invoice được phép
payments:refund  -> refund khi object và business state cho phép
```

Không nên thay role cũ bằng permission mới trong một lần deploy nếu dữ liệu membership, client token và service policy chưa sẵn sàng. Chuyển đổi cần có mapping được review:

| Role cũ | Permission mới | Điều kiện bổ sung |
|---|---|---|
| `FINANCE_VIEWER` | `invoices:read` | Tenant membership và object grant |
| `FINANCE_ANALYST` | `invoices:read`, `reports:read` | Chỉ dữ liệu thuộc tenant được phép |
| `FINANCE_EXPORTER` | `invoices:read`, `invoices:export` | Export quota và field masking |
| `PAYMENT_OPERATOR` | `payments:read`, `payments:refund` | Approval, amount limit và payment state |
| `TENANT_ADMIN` | `tenant:manage`, `members:manage` | Chỉ tenant hiện hành; không tự cấp quyền platform admin |

Bảng trên chỉ minh họa. Một role có thể không map một-một sang permission vì policy mới có thể thêm object/tenant/business condition. Không chuyển role thành một danh sách quyền rộng mà bỏ qua các điều kiện này.

## 10. Expand–migrate–contract

Mô hình expand–migrate–contract giúp code và dữ liệu tương thích trong thời gian chuyển đổi.

**Expand:** triển khai code có thể đọc cả cấu trúc cũ và mới; thêm schema/column/permission registry mới nhưng chưa xóa dữ liệu cũ. Kiểm tra mọi service và worker có thể xử lý cả hai dạng.

**Migrate:** backfill dữ liệu quyền, membership, relationship hoặc claim mapping theo batch có thể retry. So sánh số lượng, checksum/aggregate và policy decision. Xử lý record lỗi trong quarantine thay vì tự cấp quyền mặc định.

**Enforce:** chuyển một cohort sang policy mới; theo dõi allow/deny delta và security metric. Mở rộng sau khi owner xác nhận.

**Contract:** khi không còn client/service dùng cấu trúc cũ, ngừng phát claim/role cũ, xóa code compatibility và dọn schema/permission cũ theo retention.

Không xóa cột hoặc role cũ ngay khi code mới được deploy. Có thể còn instance cũ, worker cũ, message trong queue hoặc token chưa hết hạn.

## 11. Dual-read và dual-write cần có quy tắc nhất quán

Trong giai đoạn migration, ứng dụng có thể đọc cả role cũ và permission mới. Tuy nhiên, cách kết hợp kết quả phải được định nghĩa rõ.

Với authorization, quy tắc an toàn thường là:

- Policy mới có thể thu hẹp quyền ngay khi đã được xác nhận là yêu cầu bảo mật.
- Không dùng phép OR giữa policy cũ và mới nếu policy cũ có thể cấp quyền mà policy mới đã thu hồi.
- Nếu cần compatibility tạm thời, chỉ giữ quyền cũ cho cohort và action được phê duyệt, có deadline và audit.
- Không để một lỗi đọc policy mới tự động chuyển sang allow theo policy cũ.
- Khi policy source không khả dụng hoặc dữ liệu chưa xác định, thao tác nhạy cảm phải fail closed.

Dual-write có thể giúp đồng bộ dữ liệu role và permission trong thời gian migration, nhưng cần transaction/outbox, idempotency và reconciliation. Nếu hai store không thể commit nguyên tử, xác định nguồn authoritative và cách phát hiện divergence. Không để hai nguồn cùng được xem là quyền quyết định cuối cùng mà không có precedence rõ.

## 12. JWT claim và token compatibility

Thay đổi claim là một phần dễ bị bỏ sót trong policy migration. Ví dụ issuer đổi từ:

```json
{
  "sub": "user-123",
  "roles": ["FINANCE_VIEWER"],
  "tenant": "tenant-A"
}
```

sang:

```json
{
  "sub": "user-123",
  "permissions": ["invoices:read"],
  "tenant_id": "tenant-A",
  "policy_version": "2026-11"
}
```

Service mới có thể không hiểu token cũ; service cũ có thể bỏ qua claim mới. Cần:

- Xác định issuer, audience và resource server nào tiêu thụ claim.
- Deploy consumer hỗ trợ claim mới trước khi issuer phát claim mới.
- Trong thời gian chuyển tiếp, xác định rõ cách xử lý token cũ và cohort nào còn được chấp nhận.
- Không tự động suy ra permission rộng nếu claim thiếu.
- Đặt thời hạn kết thúc compatibility ngắn và có metric theo token version.
- Thu hồi token/refresh token khi thay đổi là do compromise hoặc quyền cần bị thu hồi ngay.
- Không coi claim trong JWT là dữ liệu authorization luôn mới; membership/ACL có thể thay đổi trước khi token hết hạn.

Nếu cần thu hồi quyền nhanh, dùng introspection/revocation state, token ngắn hạn hoặc kiểm tra entitlement hiện tại tại service tùy mức rủi ro. JWT stateless có thể còn hiệu lực đến `exp` nếu không có cơ chế revoke/denylist phù hợp.

## 13. Đồng bộ policy giữa gateway, service và worker

Một policy có thể được thực thi ở nhiều lớp. Cần xác định version và nguồn authoritative:

| Thành phần | Trách nhiệm trong migration |
|---|---|
| Identity provider | Phát claim/scope đúng version; quản lý signing key và token lifetime |
| API Gateway | Route/scope coarse-grained, rate limit và identity propagation |
| Domain service | Function/object/tenant authorization cuối cùng |
| Policy store/engine | Phân phối policy version, cache và invalidation |
| Database | Lưu entitlement/relationship có schema tương thích và constraint phù hợp |
| Queue/worker | Đọc job/event version, xác minh workload identity và tenant/object scope |
| Admin portal | Quản lý grant/role theo cùng policy contract và audit |
| Observability | Ghi decision version và phát hiện policy drift |

Không triển khai gateway policy mới trước khi backend có khả năng xử lý request tương ứng. Cũng không để gateway là lớp duy nhất enforce quyền object. Với async job, request đã qua gateway không cấp quyền vĩnh viễn; worker cần xác minh lại theo policy tại thời điểm thực thi hoặc theo snapshot/ủy quyền đã được định nghĩa.

## 14. Rollback không được khôi phục quyền đã bị thu hồi

Rollback code hoặc cấu hình có thể vô tình đưa hệ thống về một policy cũ rộng hơn. Đây là điểm đặc biệt quan trọng trong API Security.

Ví dụ policy mới phát hiện user không còn quyền `payments:refund` và đã thu hồi grant. Nếu rollback toàn bộ database/policy snapshot về trạng thái trước đó, quyền refund có thể sống lại.

Thiết kế rollback theo nguyên tắc:

- Rollback binary không đồng nghĩa rollback mọi security data.
- Không khôi phục grant/revocation đã bị thu hồi chỉ để tương thích code cũ.
- Revocation/tombstone phải có semantics bền vững và được ưu tiên hơn grant cũ.
- Nếu code cũ không hiểu policy mới, dùng adapter/compatibility layer an toàn hoặc roll forward; không mở quyền để giữ uptime.
- Giữ schema tương thích với phiên bản trước trong thời gian rollback window.
- Kiểm tra token/key đã revoke không được chấp nhận lại sau rollback.
- Nếu cần rollback policy bundle, chỉ dùng version đã được review và chứng minh không làm sống lại quyền bị cấm.

Một quy tắc có thể biểu diễn:

```text
DENY nếu có revocation/tombstone hợp lệ
ELSE đánh giá grant và policy hiện hành
Nếu policy/identity không xác định -> DENY với thao tác nhạy cảm
```

Quy tắc precedence thực tế phụ thuộc mô hình policy, nhưng revocation không được bị ghi đè bởi dữ liệu grant cũ hoặc cache stale.

## 15. Rollback ứng dụng và policy theo từng loại lỗi

| Sự cố | Hành động phù hợp |
|---|---|
| Latency/5xx tăng do binary mới | Dừng rollout; rollback binary nếu schema và policy vẫn tương thích |
| Authorization deny tăng bất thường | Dừng mở rộng; phân tích policy/data mismatch; chỉ rollback policy nếu phiên bản cũ không cấp lại quyền nguy hiểm |
| Có dấu hiệu cross-tenant allow | Dừng rollout/disable route hoặc action; ưu tiên containment và sửa policy; không chờ canary tiếp theo |
| Token claim mới không tương thích | Dừng issuer migration; giữ consumer compatibility; rotate/reissue token theo kế hoạch |
| Revocation propagation chậm | Dừng rollout; kiểm tra cache, introspection và worker; không bật lại grant cũ |
| Gateway/service policy version lệch | Dừng mở rộng; đồng bộ version hoặc chặn route có rủi ro |
| Audit event bị mất | Dừng thay đổi nhạy cảm nếu không thể truy vết; khôi phục durable audit pipeline |
| Database migration lỗi một phần | Dừng batch; dùng checkpoint/reconciliation; không rollback dữ liệu revocation đã commit |
| Client cũ bị `403` | Xác minh đó là quyền bị thu hồi hay mapping thiếu; không tự cấp quyền rộng để giảm lỗi |

Với sự cố bảo mật nghiêm trọng, ưu tiên containment và bảo toàn bằng chứng. Rollback không phải lúc nào cũng là hành động đầu tiên; đôi khi cần tắt một operation, revoke credential hoặc chặn tenant/object cụ thể trong khi giữ các chức năng an toàn khác.

## 16. Feature flag và kill switch cho policy

Feature flag có thể điều khiển rollout nhưng cũng là một phần của security control plane. Hãy thiết kế:

- Flag được lưu ở hệ thống quản trị tin cậy, có authentication và audit.
- Chỉ role vận hành/security phù hợp được thay đổi.
- Flag gắn với tenant/operation/cohort cụ thể và có expiry/owner.
- Giá trị mặc định khi không đọc được flag phải an toàn.
- Không cho client truyền header/query để bật policy hoặc bypass authorization.
- Thay đổi flag có version, actor, timestamp và reason.
- Có cảnh báo khi flag nhạy cảm bị thay đổi hoặc tồn tại quá hạn.

Kill switch nên vô hiệu hóa chức năng rủi ro cụ thể, ví dụ export hoặc refund, và giữ lại thao tác đọc/health cần thiết nếu an toàn. Không dùng kill switch kiểu “tắt toàn bộ authorization” để phục hồi dịch vụ. Nếu policy engine lỗi, quyết định mặc định cho thao tác nhạy cảm phải fail closed.

## 17. Cache, propagation và consistency

Policy có thể được cache trong gateway, service, authorization engine hoặc worker. Khi thay đổi quyền, cache stale có thể tiếp tục cho phép request sau khi grant đã bị revoke.

Hãy xác định:

- Cache key gồm principal, tenant, action, object và policy version nào.
- TTL tối đa cho dữ liệu quyền và thời gian propagation mục tiêu.
- Cách invalidate khi role, membership, grant hoặc tenant state thay đổi.
- Cách xử lý event invalidation bị mất hoặc đến sai thứ tự.
- Worker có cache quyền lâu hơn request hay không.
- Token claim có thể cũ đến khi nào và khi nào phải introspect/recheck.

Với thao tác rủi ro cao, không chỉ dựa vào cache quyền dài hạn. Có thể yêu cầu kiểm tra entitlement hiện tại hoặc revocation state trước side effect. Khi cache/invalidation service không khả dụng, đánh giá theo risk: dữ liệu công khai có thể có fallback phù hợp; refund, admin, export dữ liệu nhạy cảm và thay đổi tenant phải fail closed.

## 18. Database migration cho authorization data

Thay đổi schema entitlement cần tránh làm mất hoặc mở rộng quyền ngoài ý muốn:

1. Thêm bảng/cột mới mà code cũ vẫn chạy được.
2. Backfill theo batch nhỏ, có checkpoint và idempotency.
3. Ghi số record nguồn, record đích, lỗi và mapping không rõ.
4. Đối chiếu grant/revocation theo tenant và subject.
5. Không tự map record thiếu dữ liệu sang role admin hoặc permission rộng.
6. Chạy shadow policy trên dữ liệu đã migrate.
7. Canary enforcement và theo dõi decision delta.
8. Chuyển nguồn authoritative sau khi xác nhận.
9. Chỉ contract schema cũ sau rollback window và khi không còn consumer cũ.

Nếu migration có thể chạy lại, thao tác cần idempotent. Nếu một batch thất bại, có thể tiếp tục từ checkpoint mà không tạo duplicate grant. Với revocation, giữ tombstone hoặc audit record đủ lâu để bản ghi grant cũ không được khôi phục do reimport/restore.

## 19. Canary và policy migration cho API version

Khi chuyển từ API v1 sang v2, hai version có thể tồn tại đồng thời. Không mặc định v2 an toàn hơn hoặc v1 không còn được dùng.

- Mỗi version có owner, support window và policy contract.
- Authentication/audience phải giới hạn đúng resource và version khi cần.
- Function/object authorization phải tương đương hoặc được thay đổi có chủ đích.
- Không để v1 có quyền rộng hơn v2 chỉ vì client cũ không gửi claim mới.
- Route v1 cần metric traffic, client identity và deprecation date.
- Canary v2 theo client/tenant đã chọn; so sánh kết quả nghiệp vụ và policy.
- Khi sunset v1, kiểm tra cả gateway, direct backend, alias và async integration.

Nếu v1 có lỗ hổng nghiêm trọng, có thể phải chặn ngay thay vì duy trì compatibility. Quyết định cần cân nhắc mức độ phơi lộ và có phương án migration khẩn cấp cho client.

## 20. Automated stop và manual approval

Có thể tự động dừng canary khi metric vượt ngưỡng, nhưng không nên tự động rollback mọi policy change mà không xem xét hậu quả bảo mật.

Ví dụ điều kiện stop:

- Có một confirmed cross-tenant authorization allow ngoài policy.
- Security regression test bắt đầu fail.
- Tỷ lệ 5xx/timeout vượt SLO trong thời gian đủ mẫu.
- Authorization deny tăng đột biến ngoài cohort dự kiến.
- Revocation propagation vượt SLA.
- Policy version giữa gateway/service không đồng nhất.
- Audit pipeline mất event hoặc không ghi được decision quan trọng.

Đối với security critical event, tự động chặn rollout hoặc disable operation có thể phù hợp. Rollback policy cần được review để chắc chắn không cấp lại quyền đã bị thu hồi. Đặt manual approval trước khi mở rộng các quyền admin, refund, secret access hoặc cross-tenant capability.

## 21. Ví dụ release manifest

Một manifest minh họa có thể ghi rõ cohort, policy version và tiêu chí dừng:

```yaml
release:
  id: api-authz-2026-11
  applicationVersion: 4.8.0
  policyVersion: authz-v3
  mode: canary
  cohort:
    type: tenant-allowlist
    tenants:
      - tenant-security-test
      - tenant-internal-qa
  stages:
    - name: canary
      duration: 30m
      maxErrorRate: 0.01
      maxP95LatencyMs: 500
    - name: expansion
      duration: 2h
      approvalRequired: true
  stopConditions:
    crossTenantAllow: 0
    revocationLagSeconds: 60
    auditDeliveryFailures: 0
  rollback:
    applicationVersion: 4.7.3
    policyRollbackRequiresReview: true
    preserveRevocations: true
```

Đây là cấu trúc minh họa, không phải schema chuẩn của Kubernetes hay một công cụ delivery cụ thể. Các trường cần được validate và thực thi bởi pipeline/control plane. Danh sách tenant phải đến từ cấu hình được phê duyệt, không lấy trực tiếp từ request client. Không để manifest chứa token, secret hoặc dữ liệu cá nhân.

## 22. Kiểm thử trước và trong rollout

Một release API security cần nhiều lớp kiểm tra:

| Giai đoạn | Test cần chạy |
|---|---|
| Unit/policy test | Allow/deny matrix, role-to-permission mapping, tenant/object conditions |
| Contract test | JWT claim, audience, scope, API version và error contract |
| Integration test | Gateway + service + database + policy engine |
| Cross-tenant test | Principal A không đọc/ghi object tenant B |
| Revocation test | Grant/token/API key đã revoke không được chấp nhận qua cache hoặc worker |
| Compatibility test | Instance cũ/mới và message/token version cùng hoạt động trong giai đoạn expand |
| Shadow comparison | Policy old/new decision delta được giải thích |
| Canary test | Metric, stop condition, audit và rollback path thực sự hoạt động |
| Recovery test | Rollback binary không làm sống lại grant/revocation cũ |
| Post-deploy verification | Gateway, service, worker và policy version đồng nhất |

Test cả allow và deny. Một policy migration chỉ có test “user hợp lệ vẫn truy cập được” sẽ bỏ sót lỗi cấp quyền thừa. Cần negative test cho user cùng tenant khác owner, tenant khác, role cũ đã bị thu hồi, token cũ, service account sai audience và job được thực thi sau khi quyền thay đổi.

## 23. Checklist vận hành

- [ ] Release có change ID, owner, policy version, security intent và affected endpoints.
- [ ] Canary cohort được chọn từ identity/tenant đáng tin cậy và có phạm vi giới hạn.
- [ ] Có baseline, success criteria, stop conditions và thời gian quan sát phù hợp traffic.
- [ ] Theo dõi availability/performance cùng authorization decision và tenant isolation.
- [ ] Có shadow evaluation trước policy migration khi phù hợp; shadow không tạo side effect.
- [ ] Role/permission mapping được review; không map thiếu dữ liệu thành quyền rộng.
- [ ] Expand–migrate–contract giữ code/schema/token tương thích trong rollback window.
- [ ] Dual-read/write có nguồn authoritative, precedence và reconciliation rõ.
- [ ] JWT claim migration triển khai consumer trước issuer; có hạn kết thúc compatibility.
- [ ] Gateway, service, worker và policy store dùng policy version được xác định.
- [ ] Revocation/tombstone không bị ghi đè bởi grant cũ, cache hoặc rollback snapshot.
- [ ] Feature flag/kill switch có access control, audit, expiry và default an toàn.
- [ ] Cache policy có TTL/invalidation và kiểm tra quyền hiện tại cho thao tác nhạy cảm.
- [ ] Rollback binary tách biệt với rollback security data; không mở lại quyền đã thu hồi.
- [ ] Có test cross-tenant, negative authorization, token/key revocation và rollback.
- [ ] Post-deploy verification xác nhận route, claim, policy, audit và telemetry đồng bộ.

## Kết luận

Canary giới hạn phạm vi tác động khi triển khai code hoặc policy mới; shadow evaluation giúp nhìn thấy khác biệt authorization trước khi enforce; expand–migrate–contract giữ tương thích trong quá trình chuyển dữ liệu và claim; rollback khôi phục khả năng vận hành mà không làm sống lại quyền đã bị thu hồi. Với API security, cần theo dõi cả performance lẫn quyết định allow/deny, tenant isolation, revocation và audit. Mỗi bước mở rộng phải dựa trên bằng chứng và tiêu chí đã định. Khi policy version, identity context, cache và worker được quản lý nhất quán, hệ thống có thể thay đổi bảo mật từng phần mà vẫn giữ được ranh giới quyền truy cập.
