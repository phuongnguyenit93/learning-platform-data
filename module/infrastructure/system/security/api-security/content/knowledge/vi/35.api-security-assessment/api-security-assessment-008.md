# Bằng chứng test tái lập được

Một kết quả kiểm thử bảo mật chỉ hữu ích khi người khác có thể hiểu chính xác điều gì đã được kiểm tra, tái tạo điều kiện ban đầu, chạy lại các bước và quan sát cùng một hành vi. Ảnh chụp màn hình ghi `403` hoặc một dòng mô tả “có thể truy cập dữ liệu tenant khác” chưa đủ để xác nhận một lỗ hổng. Bằng chứng cần chỉ ra endpoint, principal, resource, trạng thái hệ thống, request đã gửi, response thực tế, kết quả mong đợi, tác động và cách kiểm chứng độc lập.

Trong module `SECURITY_API_SECURITY`, đánh giá bảo mật API phải bám theo endpoint, object, property và luồng nghiệp vụ. Bài này hướng dẫn xây dựng evidence package có thể tái lập, an toàn và có thể kiểm tra: từ xác định scope, tạo fixture, chạy test, thu thập artifact, che dữ liệu nhạy cảm, bảo toàn tính toàn vẹn đến viết báo cáo và xác minh bản sửa.

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt kết quả test, bằng chứng quan sát được và kết luận về lỗ hổng.
- Viết test case có precondition, bước chạy, expected result và actual result rõ ràng.
- Chuẩn bị environment và dữ liệu kiểm thử có thể tạo lại.
- Ghi nhận request/response HTTP đủ để tái lập mà không lưu credential.
- Chứng minh lỗi authorization bằng actor, tenant, object và property cụ thể.
- Thu thập log, trace, timestamp, request ID và artifact hỗ trợ.
- Redact secret/PII mà vẫn giữ được giá trị kỹ thuật của bằng chứng.
- Tạo manifest, hash và chain of custody cho evidence package.
- Phân biệt lỗi có thể tái lập, lỗi phụ thuộc môi trường và kết quả chưa đủ bằng chứng.
- Xác minh regression sau remediation bằng cùng test case và fixture.

## 1. Bằng chứng test tái lập được là gì?

### 1.1. Từ phát hiện đến bằng chứng

Một phát hiện bảo mật cần có chuỗi lập luận:

1. **Điều kiện:** hệ thống, endpoint, principal và dữ liệu đang ở trạng thái nào?
2. **Hành động:** tester gửi request hoặc kích hoạt workflow nào?
3. **Quan sát:** server trả status, body, side effect và telemetry gì?
4. **So sánh:** hành vi thực tế khác expected security behavior ở điểm nào?
5. **Tác động:** attacker có thể đọc, sửa, xóa, kích hoạt hoặc làm cạn tài nguyên nào?
6. **Tái lập:** người khác có thể lặp lại với fixture và bước chạy được cung cấp không?

Ví dụ, câu “API có IDOR” là kết luận, chưa phải bằng chứng. Một bằng chứng tốt mô tả User A thuộc Tenant A, User B thuộc Tenant B, file `file-b-canary` thuộc Tenant B, token của User A được dùng để gọi `GET /api/files/file-b-canary`, server trả `200` cùng nội dung canary của Tenant B, trong khi policy yêu cầu từ chối. Người đánh giá có thể tạo lại hai user và hai file test rồi chạy đúng request.

### 1.2. Ba khái niệm cần tách biệt

| Khái niệm | Nội dung | Ví dụ |
|---|---|---|
| Test result | Kết quả thực thi một test | `FAIL`: endpoint trả 200 thay vì 404 |
| Evidence | Artifact cho phép kiểm tra kết quả | Request/response đã redact, fixture manifest, trace ID |
| Finding | Kết luận có phân tích về security impact | User Tenant A đọc được file riêng của Tenant B |

Một test có thể fail vì fixture sai, token hết hạn hoặc môi trường không sẵn sàng. Không biến mọi test failure thành security finding. Ngược lại, một finding có thể được chứng minh bởi nhiều test result và nhiều loại artifact.

### 1.3. Tiêu chí của evidence tốt

Evidence có chất lượng khi:

- **Có nguồn gốc:** biết ai chạy, lúc nào, trên build/environment nào.
- **Có ngữ cảnh:** biết principal, role, tenant, object và trạng thái trước test.
- **Có thể tái lập:** có lệnh/script hoặc bước thao tác cụ thể.
- **Có thể đối chiếu:** expected và actual được trình bày cạnh nhau.
- **Có tính toàn vẹn:** artifact không bị sửa âm thầm sau khi thu thập.
- **An toàn:** không chứa password, token, secret hoặc dữ liệu thật không cần thiết.
- **Tối thiểu nhưng đủ:** chỉ lưu những gì cần để chứng minh và điều tra.

Evidence không cần phức tạp. Một test case nhỏ với hai fixture và hai HTTP request chính xác thường thuyết phục hơn một video dài không thể xác định trạng thái ban đầu.

## 2. Xác định scope trước khi chạy test

### 2.1. Ghi rõ mục tiêu và phạm vi

Mỗi test phải ghi:

- Tên hệ thống/service và environment.
- Base URL, API version, hostname hoặc gateway route.
- Endpoint, HTTP method và operation đang đánh giá.
- Loại kiểm soát: authentication, function authorization, object authorization, property authorization, validation, SSRF, rate limit, business flow hoặc logging.
- Principal/role/tenant cần dùng.
- Object/property và dữ liệu test liên quan.
- Những hành động được phép thực hiện và giới hạn dừng.

Không dùng một nhãn chung như “test API production” làm scope. Ghi rõ host, route và account được ủy quyền. Nếu scope không rõ hoặc endpoint có thể thuộc hệ thống bên thứ ba, dừng và xác nhận quyền kiểm thử trước khi gửi request.

### 2.2. Phân loại mức ảnh hưởng của thao tác

| Loại thao tác | Ví dụ | Cách kiểm thử ưu tiên |
|---|---|---|
| Read-only | Đọc profile, file canary, order test | Dùng synthetic data, xác nhận không truy cập dữ liệu thật |
| Reversible write | Cập nhật display name test | Ghi snapshot trước, có reset/rollback |
| Business side effect | Gửi email, tạo invoice, refund, payment | Sandbox/mock provider, idempotency key và giới hạn số lần |
| Resource intensive | Export lớn, search rộng, upload | Payload nhỏ, quota thấp, concurrency giới hạn |
| External callback/SSRF | Fetch URL, webhook | Dùng callback collector do đội kiểm thử kiểm soát, không dò metadata/private network |
| Destructive/admin | Xóa user, purge, disable tenant | Chỉ dùng fixture riêng và approval rõ; tránh production |

Test tái lập được phải có giới hạn an toàn. Không cần chứng minh impact bằng cách xóa dữ liệu thật, gửi hàng nghìn email hoặc làm quá tải hệ thống.

### 2.3. Đặt mã test case ổn định

Dùng mã không phụ thuộc thời gian hoặc thứ tự chạy, ví dụ:

```text
API-AUTHZ-OBJ-004  Cross-tenant file read is denied
API-AUTHZ-FUNC-002 Non-admin cannot invoke user disable
API-INPUT-SSRF-003 Callback cannot reach private address
API-FLOW-REPLAY-001 Duplicate payment request is idempotent
```

Mã test giúp liên kết test run, finding, regression test và release report. Không nhúng tên user, token hoặc tenant thật vào mã.

## 3. Chuẩn bị environment có thể tái tạo

### 3.1. Ghi nhận build và cấu hình

Kết quả test có thể thay đổi theo phiên bản ứng dụng, gateway policy, WAF rules, database schema hoặc feature flag. Evidence manifest nên ghi:

- Git commit hoặc source revision.
- Build/version và immutable image digest nếu có.
- API contract/OpenAPI version.
- Gateway/ingress policy revision.
- WAF/rule-set version nếu liên quan.
- Environment, region và deployment slot.
- Feature flags liên quan.
- Database schema/migration version.
- Test tool/runtime version.
- Thời điểm chạy theo UTC.

Không đưa secret, environment variable nhạy cảm hoặc toàn bộ config production vào manifest. Ghi version/fingerprint của cấu hình, không ghi giá trị credential.

### 3.2. Ghi nhận network path

Một request có thể đi qua CDN, WAF, load balancer, gateway, service mesh hoặc direct origin. Ghi đường đi dự kiến và đường đi thực tế nếu khác nhau. Nếu test qua gateway, đừng tái lập bằng cách gọi thẳng application mà không ghi rõ; hai đường có thể áp dụng policy khác nhau.

Các thông tin hữu ích:

- DNS hostname và API route.
- Proxy/VPN/test runner location ở mức cần thiết.
- Gateway route ID hoặc ingress class.
- TLS termination point.
- Có/không có retry hoặc redirect.
- Request ID/trace ID do hệ thống cấp.

Không ghi IP nội bộ hoặc topology nhạy cảm vào report gửi rộng rãi nếu không cần. Có thể lưu chi tiết trong evidence package hạn chế quyền.

### 3.3. Clock và thời gian

Ghi timestamp UTC với timezone rõ, ví dụ `2026-11-18T13:45:22Z`. Đồng bộ clock của test runner và hệ thống bằng time service. Với duration, dùng monotonic timer ở test harness; timestamp wall-clock dùng để đối chiếu log giữa các host.

Nếu test phụ thuộc expiry, OTP, JWT `nbf`/`exp`, rate-limit window hoặc scheduled job, ghi thời điểm tạo credential và thời điểm gửi request. Không copy token vào evidence chỉ để chứng minh thời gian.

### 3.4. Môi trường test phải cô lập

Ưu tiên staging, ephemeral environment hoặc security test tenant. Môi trường nên có:

- Dữ liệu synthetic, không dùng hồ sơ khách hàng thật.
- Tài khoản và role riêng cho test.
- Mail/SMS/payment provider giả lập hoặc sandbox.
- Object storage bucket riêng.
- Queue/topic và database namespace riêng khi cần.
- Rate/concurrency limit phù hợp để không ảnh hưởng workload khác.
- Cách reset fixture và cleanup sau test.

Nếu chỉ có thể kiểm tra trên production, dùng read-only/low-impact verification đã được phê duyệt, giới hạn số request và không tạo side effect ngoài dự kiến. Ghi rõ hạn chế này trong kết luận.

## 4. Fixture và precondition

### 4.1. Fixture là một phần của bằng chứng

Fixture là dữ liệu/trạng thái được chuẩn bị trước để test có đầu vào xác định. Với API security, fixture thường gồm principal, role, tenant, object ownership, trạng thái workflow và permission.

Ví dụ fixture cho object-level authorization:

| Fixture | Tenant | Principal | Object | Quyền mong đợi |
|---|---|---|---|---|
| `user-a` | `tenant-a` | User thường | `file-a-canary` | Đọc file A |
| `user-a` | `tenant-a` | User thường | `file-b-canary` | Không được đọc file B |
| `user-b` | `tenant-b` | User thường | `file-b-canary` | Đọc file B |
| `admin-a` | `tenant-a` | Tenant admin | `file-a-canary` | Theo policy admin Tenant A |

Tên fixture là alias. Manifest fixture có thể lưu synthetic ID thực tế, nhưng không lưu token. Nội dung file canary nên là chuỗi vô hại, ví dụ `CANARY-TENANT-B-DO-NOT-USE-REAL-DATA`.

### 4.2. Precondition phải kiểm chứng được

Trước khi chạy, xác nhận:

- Các account tồn tại và có đúng role.
- Account A và B thuộc tenant khác nhau.
- File/order/resource thuộc đúng owner.
- Object đang ở trạng thái mà endpoint cho phép xử lý.
- Không có sharing grant hoặc admin override ngoài dự kiến.
- Token còn hiệu lực, đúng issuer/audience/scope.
- Dữ liệu test chưa bị test run trước thay đổi.

Không chỉ ghi “đã chuẩn bị user A/B”. Hãy lưu kết quả fixture setup hoặc query/seed reference đủ để người khác xác minh.

### 4.3. Tạo fixture idempotent

Setup script nên có thể chạy nhiều lần mà không tạo dữ liệu trùng hoặc làm fixture lệch. Dùng stable test namespace và upsert có kiểm soát; tạo object với marker nhận diện rõ; không dùng ID của dữ liệu khách hàng.

Ví dụ pseudocode:

```text
ensure tenant-a and tenant-b exist in test namespace
ensure user-a belongs only to tenant-a
ensure user-b belongs only to tenant-b
ensure file-a-canary belongs to tenant-a
ensure file-b-canary belongs to tenant-b
assert no sharing grant exists between user-a and file-b-canary
```

Ghi version của fixture setup script và kết quả assertion. Nếu setup không đạt, không chạy test chính vì expected result sẽ không còn đáng tin.

### 4.4. Teardown và reset

Ghi rõ cách dọn dữ liệu, thời điểm cleanup và ai chịu trách nhiệm. Với test cần giữ evidence, không xóa fixture trước khi artifacts được hash và lưu đúng nơi. Sau khi evidence được bảo toàn, cleanup chỉ xóa dữ liệu thuộc test namespace; không dùng wildcard hoặc lệnh xóa rộng có thể tác động tenant khác.

## 5. Thiết kế test case tái lập

### 5.1. Cấu trúc tối thiểu

Mỗi test case nên có các phần:

1. ID và title.
2. Mục tiêu/kiểm soát đang kiểm tra.
3. Scope và environment.
4. Preconditions/fixture.
5. Principal và permission context.
6. Steps hoặc command theo thứ tự.
7. Expected result.
8. Actual result.
9. Evidence/artifact references.
10. Cleanup/reset.
11. Hạn chế hoặc yếu tố có thể ảnh hưởng kết quả.

### 5.2. Expected result phải cụ thể

Không viết expected result như “API an toàn” hoặc “request bị chặn”. Hãy chỉ rõ:

- HTTP status mong đợi.
- Response schema/error code.
- Không được có field/dữ liệu nào trong response.
- Database/object state phải giữ nguyên hay thay đổi thế nào.
- Side effect nào không được xảy ra.
- Log/audit event nào cần được tạo.
- Rate counter/quota/lock có thay đổi hay không.

Ví dụ: User A gọi file của Tenant B phải bị từ chối theo anti-enumeration policy; response không chứa filename, size, ETag hoặc file bytes; storage access log không ghi successful read; audit có authorization denial với request ID.

### 5.3. Một test chỉ thay đổi một biến chính

Để kết luận nguyên nhân, giữ các yếu tố khác cố định. Khi kiểm tra role, dùng cùng resource và thay principal. Khi kiểm tra tenant boundary, giữ action và object type giống nhau nhưng đổi tenant. Khi kiểm tra property authorization, giữ user/object/action và chỉ thay field được gửi.

Nếu một request đồng thời đổi role, tenant, object ID và payload, kết quả khó xác định yếu tố nào tạo ra khác biệt.

### 5.4. Positive và negative control

Một test authorization tốt nên có:

- Positive control: owner hoặc principal được phép thực hiện thành công.
- Negative control: principal không có quyền bị từ chối.
- Cross-boundary control: principal thuộc tenant khác không truy cập được object.

Positive control chứng minh endpoint và fixture hoạt động. Nếu cả request hợp lệ lẫn không hợp lệ đều trả 500, đó có thể là environment/test setup failure, không phải bằng chứng authorization.

## 6. Thu thập HTTP request/response

### 6.1. Những gì cần lưu

Một artifact HTTP đủ dùng thường gồm:

- Method, scheme/host đã sanitize, path và query đã redact.
- Header cần thiết để tái lập semantics.
- Body synthetic hoặc fixture reference.
- Status line và response headers liên quan.
- Response body đã redact hoặc canary.
- Timestamp UTC, duration, request ID và trace ID nếu có.
- Principal alias/role/tenant alias được dùng.
- Lệnh/script tạo request và exit code.

Không lưu raw `Authorization`, cookie, API key, refresh token, password, signed URL hoặc secret header. Khi replay, lấy credential mới từ test secret store hoặc login flow của test harness.

### 6.2. Redaction có ý nghĩa

Redaction phải giữ được semantics của request. Ví dụ:

```http
GET /api/files/file-b-canary HTTP/1.1
Host: api.test.example
Authorization: <REDACTED: bearer token for fixture user-a>
X-Request-ID: req-test-004
Accept: application/json
```

Ghi chú alias cho credential bị che: `user-a` thuộc `tenant-a`, scope `file:read`, token được cấp bởi test issuer và còn hiệu lực tại thời điểm chạy. Không ghi token prefix/suffix nếu chúng có thể hỗ trợ khôi phục hoặc nhận diện secret ngoài nhu cầu.

Nếu cần chứng minh hai request dùng hai identity khác nhau, ghi principal alias và token fingerprint đã HMAC bằng khóa kiểm thử được bảo vệ; không dùng hash đơn giản cho secret entropy thấp hoặc lưu token thật trong report.

### 6.3. Giữ response đủ để chứng minh impact

Với test IDOR, response body có thể chứa synthetic canary. Lưu đúng phần field chứng minh truy cập chéo tenant; không cần lưu toàn bộ hồ sơ. Với test property-level, lưu field bị lộ/sửa và trạng thái trước/sau. Với lỗi validation, lưu status, error code và một phần response đã redact.

Nếu response chứa dữ liệu thật ngoài dự kiến, dừng test, không sao chép thêm, bảo vệ artifact theo quy trình incident và báo người phụ trách. Không đưa dữ liệu đó vào ví dụ hoặc ticket có quyền truy cập rộng.

### 6.4. Redirect, compression và body framing

Ghi rõ client có follow redirect không, có tự giải nén response không và request/response có content encoding nào. Nếu dùng `curl -L`, lưu redirect chain hoặc chạy lại không follow để ghi từng hop. Không so sánh body đã giải nén với `Content-Length` của wire representation.

Với multipart/file, lưu metadata cần thiết như content type, size, checksum của fixture và upload/download status; không đính kèm file nhạy cảm không cần thiết.

## 7. Ví dụ tái lập lỗi object-level authorization

### 7.1. Mục tiêu và fixture

Test case `API-AUTHZ-OBJ-004` kiểm tra user Tenant A có thể đọc file canary của Tenant B hay không.

Preconditions:

- `user-a` thuộc `tenant-a`, chỉ có `file:read` trên file được chia sẻ/thuộc tenant A.
- `user-b` thuộc `tenant-b` và sở hữu `file-b-canary`.
- Không có sharing grant giữa `user-a` và `file-b-canary`.
- Token lấy từ test identity provider; token thật không lưu vào artifact.
- Endpoint test là `GET /api/files/{fileId}` trong staging.

### 7.2. Positive control

Request của owner `user-b`:

```http
GET /api/files/file-b-canary HTTP/1.1
Host: api.test.example
Authorization: Bearer <TOKEN_FROM_TEST_SECRET_STORE>
Accept: application/json
```

Expected: `200 OK`, body có `fileId=file-b-canary` và canary marker của Tenant B. Nếu request owner không thành công, kiểm tra fixture, scope và endpoint trước khi chạy negative test.

### 7.3. Negative test

Dùng credential của `user-a` cho cùng object:

```bash
curl --silent --show-error \
  --request GET \
  --config "${CURL_AUTH_CONFIG}" \
  --header "Accept: application/json" \
  --dump-header evidence/user-a-response.headers \
  --output evidence/user-a-response.body \
  --write-out 'http_code=%{http_code}\ntime_total=%{time_total}\n' \
  "${API_BASE_URL}/api/files/file-b-canary"
```

`CURL_AUTH_CONFIG` là file cấu hình curl tạm thời do secret store/test runner cấp, chỉ user chạy test đọc được (ví dụ permission `0600`) và chứa header bearer cho `user-a`. Không đưa nội dung file vào evidence, shell history hoặc log. Script chỉ chạy trong environment và scope đã được phê duyệt.

Expected: `403` hoặc `404` theo anti-enumeration contract; body không chứa canary, filename hoặc metadata nhạy cảm; không có successful storage read. Actual phải được ghi nguyên status/body đã redact.

Nếu server trả `200` cùng canary marker, có bằng chứng user A đọc file tenant B. Chụp lại response tối thiểu, request ID, trace ID và audit event. Không tiếp tục enumeration các file khác; một canary đủ để chứng minh lỗi.

### 7.4. Kết quả và tác động

Một báo cáo có thể ghi:

```text
Expected: 404, no file metadata or bytes.
Actual:   200, fileId=file-b-canary, marker=CANARY-TENANT-B.
Impact:   Authenticated user in tenant-a can read a private file in tenant-b.
Scope:    One synthetic canary object in staging.
```

Phân biệt rõ điều đã chứng minh và điều chưa chứng minh. Một file canary chứng minh cross-tenant read trên route được test; chưa tự chứng minh mọi endpoint hoặc mọi loại file đều bị ảnh hưởng.

## 8. Ví dụ test property authorization và mass assignment

### 8.1. Xác định field được phép sửa

Giả sử user thường được phép đổi `displayName` nhưng không được sửa `role`, `tenantId`, `isAdmin` hoặc `billingStatus`.

Fixture:

```json
{
  "userId": "user-a",
  "tenantId": "tenant-a",
  "role": "USER",
  "displayName": "Test User",
  "isAdmin": false
}
```

Gửi update có field được phép và field bị cấm trong cùng một test case có chủ đích:

```http
PATCH /api/profile HTTP/1.1
Content-Type: application/json
Authorization: Bearer <TOKEN_FOR_USER_A>

{
  "displayName": "Updated Test User",
  "role": "ADMIN",
  "tenantId": "tenant-b",
  "isAdmin": true
}
```

Expected phải được định nghĩa theo contract: server có thể từ chối toàn bộ request `400/403`, hoặc chỉ cập nhật field allowlisted và bỏ qua field ngoài phạm vi. Dù chọn cách nào, `role`, `tenantId`, `isAdmin` phải giữ nguyên.

### 8.2. Bằng chứng trước/sau

Lưu:

- Snapshot field trước test.
- Request body synthetic.
- Response status/body.
- Snapshot field sau test từ API quản trị test hoặc database fixture verifier.
- Audit event nếu có.

Không chỉ dựa vào response `200`. Một API có thể trả success nhưng vẫn thay đổi field cấm ở database. Ngược lại, response có thể echo request body trong khi database không thay đổi. Cần xác minh state thực tế qua nguồn kiểm chứng được phép.

## 9. Ví dụ test business flow và replay

### 9.1. Ghi lại trạng thái trước và sau

Với luồng tạo payment/invoice/order, evidence phải mô tả state transition. Ví dụ:

```text
Before: payment=AUTHORIZED, capture_count=0
Action: POST /payments/{id}/capture with idempotency key test-capture-001
Expected: one capture operation, stable result for duplicate request
After first request: capture_count=1
After duplicate request: capture_count remains 1
```

Chạy trong payment sandbox hoặc mock provider. Không dùng thẻ thật, tài khoản thật hoặc gửi giao dịch thật chỉ để chứng minh replay. Dùng idempotency key riêng cho từng test run và ghi fixture/provider transaction reference.

### 9.2. Tái lập duplicate request

Gửi cùng method, resource, body và idempotency key hai lần theo trình tự có kiểm soát. Ghi request ID riêng cho từng HTTP call, cùng business idempotency key và kết quả provider. Expected là side effect chỉ xảy ra một lần; response duplicate có thể là kết quả cũ hoặc status theo contract.

Không dùng trace ID làm idempotency key. Trace mô tả quan sát; idempotency key thuộc business operation và cần được kiểm tra/persist ở server.

### 9.3. Async job

Với job bất đồng bộ, ghi:

- Job ID và correlation ID.
- Event/message ID và schema version.
- Producer identity/actor alias.
- Thời điểm enqueue, dequeue, attempt và terminal state.
- Queue/topic alias và consumer version.
- Request ID/trace ID của submit request và consumer trace nếu có.
- Result object reference và authorization khi download.

Đừng chỉ ghi `202 Accepted`. Cần polling theo deadline có giới hạn, ghi trạng thái cuối và xác minh side effect/output. Nếu job còn `RUNNING` sau timeout, kết quả là inconclusive hoặc timeout theo test policy, không tự kết luận pass.

## 10. Ví dụ test SSRF an toàn và có thể tái lập

### 10.1. Dùng callback collector kiểm soát

Nếu API có tính năng fetch URL hoặc gửi webhook, dùng một HTTP collector do đội kiểm thử sở hữu. Tạo URL duy nhất cho test run, ví dụ `https://ssrf-test.example/callback/{runId}`. Collector chỉ ghi nhận request đến, timestamp, method và một correlation token vô hại.

Không dùng endpoint metadata cloud, localhost, private subnet hoặc hệ thống bên thứ ba làm mục tiêu kiểm thử. Không dò dải mạng. Mục tiêu là chứng minh server có/không thực hiện request tới destination được cho phép và policy có chặn URL ngoài allowlist.

### 10.2. Evidence cần thu

- Request tạo job/webhook với URL collector.
- DNS/redirect behavior của domain test nếu liên quan.
- Response API và job state.
- Collector event với unique run ID.
- Egress/proxy log nếu được phép.
- Expected allow/deny theo policy.

Nếu test URL bị từ chối, ghi status và error code. Nếu collector nhận request, đối chiếu run ID để chứng minh outbound fetch. Không suy ra SSRF tới mạng nội bộ chỉ từ việc server gọi được một URL công khai; kết luận phải giới hạn theo evidence.

## 11. Test rate limit và resource abuse có giới hạn

### 11.1. Xác định ngưỡng dừng trước

Trước test, ghi:

- Route và identity/tenant test.
- Rate/concurrency limit dự kiến.
- Số request tối đa.
- Khoảng thời gian chạy.
- Dấu hiệu cần dừng: latency tăng, error rate vượt ngưỡng, queue backlog, CPU hoặc alert.
- Người theo dõi hệ thống nếu test trên shared staging.

Không dùng flood traffic để “xem hệ thống chịu được bao nhiêu” nếu chưa có load-test authorization và capacity plan.

### 11.2. Bằng chứng

Ghi sequence request với timestamp/attempt, status, `Retry-After` nếu có, request ID, rate-limit headers, counter/metric trước và sau. Expected là policy chặn hoặc throttle sau ngưỡng được cấu hình; các request trong scope khác không bị ảnh hưởng ngoài dự kiến.

Một `429` đơn lẻ chưa chứng minh quota hoạt động đúng. Cần xác minh key scope (user, API key, tenant, IP hoặc route) và reset window theo policy.

## 12. Evidence package và cấu trúc thư mục

### 12.1. Gợi ý cấu trúc

```text
evidence/
  API-AUTHZ-OBJ-004/
    README.md
    manifest.json
    test-case.yaml
    fixture-manifest.json
    commands.txt
    request-redacted.http
    response-headers.txt
    response-body-redacted.json
    application-log-redacted.jsonl
    gateway-log-redacted.jsonl
    trace-summary.json
    state-before.json
    state-after.json
    screenshots/
    checksums.sha256
```

Không phải test nào cũng cần tất cả file. Chỉ giữ artifact có giá trị chứng minh. Tránh tạo thư mục chứa raw token hoặc bản dump database chỉ vì muốn evidence đầy đủ.

### 12.2. Manifest

Manifest mô tả nguồn gốc và môi trường:

```json
{
  "evidence_id": "API-AUTHZ-OBJ-004-run-03",
  "test_case": "API-AUTHZ-OBJ-004",
  "service": "files-api",
  "environment": "staging",
  "base_url_alias": "api.test.example",
  "build": "git:8f31c2a",
  "image_digest": "sha256:example-digest",
  "api_contract_version": "v2.4",
  "started_at": "2026-11-18T13:45:22Z",
  "tester": "security-test-runner",
  "fixture_version": "fixtures-2026-11-18.2",
  "principal_alias": "user-a",
  "tenant_alias": "tenant-a",
  "result": "FAIL",
  "redaction_profile": "security-evidence-v2"
}
```

Các giá trị là ví dụ. Không lưu access token, password, private key, customer ID hoặc config secret vào manifest. Dùng alias cho hostname/tenant khi report có audience rộng.

### 12.3. Test case metadata

```yaml
id: API-AUTHZ-OBJ-004
title: User from tenant-a cannot read tenant-b file
category: object-authorization
severity_candidate: high
environment: staging
endpoint:
  method: GET
  route: /api/files/{fileId}
preconditions:
  - user-a belongs to tenant-a
  - file-b-canary belongs to tenant-b
  - no sharing grant exists
expected:
  status: [403, 404]
  body_must_not_contain:
    - tenant-b canary marker
  side_effects: none
actual:
  status: 200
  evidence:
    - response-body-redacted.json
    - gateway-log-redacted.jsonl
    - trace-summary.json
cleanup:
  - remove test fixture namespace after evidence is sealed
```

`severity_candidate` chỉ là đánh giá sơ bộ. Severity cuối cần xem data classification, exploit preconditions, reachable attack surface và business impact; không suy ra chỉ từ status code.

## 13. Integrity, timestamp và chain of custody

### 13.1. Hash artifact

Sau khi redact và hoàn tất evidence package, tạo SHA-256 checksum cho từng file. Hash giúp phát hiện artifact thay đổi sau thời điểm manifest được tạo.

Ví dụ trên Linux/macOS:

```bash
find evidence/API-AUTHZ-OBJ-004-run-03 -type f \
  ! -name checksums.sha256 -print0 \
  | sort -z \
  | xargs -0 sha256sum > evidence/API-AUTHZ-OBJ-004-run-03/checksums.sha256
```

Trên PowerShell:

```powershell
Get-ChildItem -File -Recurse .\evidence\API-AUTHZ-OBJ-004-run-03 |
  Where-Object { $_.Name -ne 'checksums.sha256' } |
  Sort-Object FullName |
  ForEach-Object {
    Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
  } | Format-Table -AutoSize
```

Lưu ý: output PowerShell trên để hiển thị/đối chiếu; nếu cần manifest checksum machine-readable, serialize `Path` và `Hash` theo format cố định. Không đưa checksum file vào chính checksum file vì sẽ tạo vòng lặp.

### 13.2. Hash không chứng minh nguồn gốc

Hash chứng minh bytes hiện tại giống bytes đã được hash, nhưng không tự chứng minh ai tạo file, file được lấy từ đâu hoặc timestamp có thật. Với evidence quan trọng:

- Ghi tester/runner identity và run ID.
- Ghi thời điểm thu thập theo UTC.
- Lưu manifest cùng checksum.
- Upload vào storage có access control và retention phù hợp.
- Bật immutable/versioned retention nếu quy trình yêu cầu.
- Ghi mọi lần redact, transform, export hoặc chuyển giao.

Nếu cần chứng minh chain of custody chặt hơn, ký manifest/checksum bằng signing key của evidence pipeline và lưu audit event cho thao tác upload/download. Không tự tuyên bố một file có tính pháp chứng chỉ vì đã chạy SHA-256.

### 13.3. Giữ raw và redacted evidence

Thông thường chỉ lưu bản đã redact trong ticket/report. Nếu tổ chức có lý do hợp lệ cần giữ raw artifact, lưu riêng trong vault/evidence store hạn chế quyền, mã hóa và retention ngắn theo policy. Ghi rõ ai có thể truy cập và cách xóa.

Không gửi raw evidence qua email/chat hoặc đính kèm vào ticket có nhiều người xem. Không để raw token trong shell history, CI log hoặc command line artifact.

## 14. Redaction và data minimization

### 14.1. Những dữ liệu cần loại bỏ hoặc thay thế

| Dữ liệu | Xử lý trong evidence |
|---|---|
| Bearer/access/refresh token | Xóa hoàn toàn; ghi principal alias và scope |
| Password/OTP/reset token | Không thu thập |
| Cookie/session ID | Xóa; ghi auth mechanism/fixture alias |
| API key/client secret/private key | Xóa; ghi key ID hoặc credential alias nếu cần |
| Email/phone/address | Dùng synthetic value hoặc mask theo policy |
| Customer/order/payment data | Dùng canary/test object; nếu lộ ngoài dự kiến, không sao chép thêm |
| Presigned URL | Xóa signature/query nhạy cảm; giữ host/path alias và expiry nếu cần |
| Internal IP/hostname | Alias trong report rộng; giữ chi tiết ở restricted evidence nếu cần |
| Query string | Chỉ giữ parameter cần thiết, redact value nhạy cảm |

### 14.2. Redact phải nhất quán

Nếu cùng một principal xuất hiện trong request, log và trace, dùng cùng alias `user-a` để người đọc nối các artifact. Không che một chỗ thành `user-a`, chỗ khác thành `user-b` gây sai quan hệ. Có thể dùng mapping file riêng trong restricted store nếu cần ánh xạ về fixture thật.

Không thay đổi giá trị làm thay đổi logic test. Ví dụ, nếu test kiểm tra `tenant-a` khác `tenant-b`, redaction phải giữ quan hệ khác nhau. Nếu cần che ID thật, thay bằng alias ổn định và ghi mapping trong evidence store được kiểm soát.

### 14.3. Screenshots không phải bằng chứng duy nhất

Screenshot hữu ích để thể hiện UI hoặc cấu hình, nhưng thường thiếu headers, raw status, timestamps và có thể bị crop. Kèm request/response text, log hoặc trace export đã redact. Screenshot phải cho thấy ngữ cảnh đủ nhận diện environment và test run nhưng không lộ credential hoặc dữ liệu thật.

## 15. Tái lập bằng script và automation

### 15.1. Script nên có contract rõ

Một script test có thể tái lập cần:

- Kiểm tra biến cấu hình bắt buộc.
- Lấy credential từ secret store/runtime injection.
- Không echo secret hoặc bật shell tracing với biến nhạy cảm.
- Dùng fixture ID cố định hoặc do setup script tạo.
- Gửi request theo thứ tự xác định.
- Ghi status, timing và artifact vào thư mục run riêng.
- Exit code phản ánh pass/fail/inconclusive.
- Cleanup theo namespace cụ thể.

Ví dụ shell tối giản:

```bash
#!/usr/bin/env bash
set -euo pipefail
set +x  # Disable inherited shell tracing before reading secret paths or values.

: "${API_BASE_URL:?API_BASE_URL is required}"
: "${CURL_AUTH_CONFIG:?secure curl config file is required}"
test -r "${CURL_AUTH_CONFIG}"

mkdir -p evidence/run-03

status=$(curl --silent --show-error \
  --config "${CURL_AUTH_CONFIG}" \
  --output evidence/run-03/body.json \
  --dump-header evidence/run-03/headers.txt \
  --write-out '%{http_code}' \
  "${API_BASE_URL}/api/files/file-b-canary")

printf 'http_status=%s\n' "$status" > evidence/run-03/result.txt

if grep -Fq 'CANARY-TENANT-B' evidence/run-03/body.json; then
  echo 'Unexpected tenant-b canary content in response' >&2
  exit 1
fi

if [ "$status" = "404" ] || [ "$status" = "403" ]; then
  exit 0
fi

if [ "$status" = "200" ]; then
  echo 'Unexpected successful cross-tenant read' >&2
  exit 1
fi

echo 'Inconclusive: unexpected status; inspect environment and response' >&2
exit 2
```

Ví dụ giả định `CURL_AUTH_CONFIG` là file cấu hình curl tạm thời do secret store/test runner cấp, chỉ user chạy test đọc được (ví dụ permission `0600`) và chứa header bearer cho `user-a`. Không đưa nội dung file vào evidence, shell history hoặc log. Response body trong ví dụ là synthetic; production harness cần redact headers/body trước khi lưu, kiểm tra canary marker chứ không chỉ status, ghi request ID/trace ID và xử lý redirect/timeout rõ ràng. Không dùng `set -x` với secret.

### 15.2. Exit code và kết quả inconclusive

Nên phân biệt:

| Exit code | Ý nghĩa |
|---:|---|
| `0` | Test đạt expected security behavior |
| `1` | Test phát hiện hành vi vi phạm expected behavior |
| `2` | Inconclusive: setup, network, token hoặc status không nằm trong tập dự kiến |
| `3` | Harness/evidence collection error |

Quy ước có thể khác giữa CI systems, nhưng không nên gom mọi lỗi thành `FAIL`. Một timeout hoặc 500 không tự chứng minh lỗ hổng cũng không chứng minh an toàn.

### 15.3. Không hardcode credential

Credential test phải được cấp tạm thời và scope hẹp. Dùng CI secret store, workload identity hoặc test identity provider. Không commit `.env`, token hoặc private key. Xóa/rotate credential sau test run theo policy.

## 16. Phân tích kết quả và tránh kết luận quá mức

### 16.1. Các kết quả có thể gặp

| Kết quả | Diễn giải | Hành động |
|---|---|---|
| Pass | Actual khớp expected và precondition được xác nhận | Lưu evidence, ghi giới hạn coverage |
| Finding reproduced | Vi phạm security expectation với fixture hợp lệ | Lưu evidence tối thiểu, đánh giá impact và báo cáo |
| Inconclusive | Setup hoặc environment không đủ điều kiện | Sửa fixture/environment rồi chạy lại |
| Flaky | Kết quả thay đổi giữa các lần chạy | Ghi run IDs, concurrency, timing và xác định race/dependency |
| Not applicable | Endpoint/feature không tồn tại hoặc không nằm trong scope | Ghi lý do và nguồn xác nhận |
| Blocked | Thiếu quyền, approval hoặc dependency | Dừng và xin điều phối; không vượt scope |

### 16.2. Lặp lại có kiểm soát

Với finding có thể tái lập, chạy lại số lần tối thiểu đủ xác nhận tính ổn định, không spam endpoint. Giữ nguyên build, fixture và request. Nếu thay đổi một điều kiện, tạo run ID mới và ghi delta.

Với race condition, ghi concurrency, timing barrier, sequence và số lần thành công/thất bại. Một lần không tái hiện không chứng minh lỗi đã hết; cần ghi xác suất quan sát và giới hạn.

### 16.3. Không nhầm absence of evidence với evidence of absence

Không tìm thấy log không chứng minh request không xảy ra; có thể sampling, retention hoặc collector làm mất event. Không thấy dữ liệu trong response không chứng minh database không thay đổi; cần state verifier. Không thấy alert không chứng minh monitoring hoạt động; cần kiểm thử alert path riêng.

Kết luận phải nêu nguồn nào đã kiểm tra và nguồn nào không có. Nếu không thể truy cập database audit hoặc gateway logs, ghi đó là limitation.

## 17. Báo cáo finding từ evidence

### 17.1. Cấu trúc báo cáo

Một finding nên có:

- ID/title ngắn và endpoint/operation.
- Summary một đoạn nêu hành vi và tác động.
- Severity/risk rationale và assumptions.
- Affected component/version/environment.
- Preconditions và test fixture.
- Steps to reproduce theo thứ tự.
- Expected vs actual result.
- Evidence references và checksum/manifest.
- Impact đã chứng minh và impact chưa chứng minh.
- Remediation recommendation.
- Regression test ID và retest result sau sửa.

### 17.2. Ví dụ finding rút gọn

```text
ID: API-AUTHZ-OBJ-004
Title: User from tenant-a can read a file owned by tenant-b
Endpoint: GET /api/files/{fileId}
Environment: staging, build 8f31c2a
Precondition: user-a belongs to tenant-a; file-b-canary belongs to tenant-b;
              no sharing grant exists.
Steps:
  1. Authenticate as user-a using test identity provider.
  2. Request /api/files/file-b-canary.
Expected: 403 or 404; no file metadata or bytes.
Actual: 200; body contains CANARY-TENANT-B.
Impact: Cross-tenant read demonstrated for one synthetic file.
Evidence: manifest.json, request-redacted.http,
          response-body-redacted.json, trace-summary.json.
Limitations: Staging only; one file route and one object type tested.
Retest: Pending remediation.
```

Không nâng phạm vi impact vượt quá điều đã quan sát. Nếu chỉ test một route, không kết luận tất cả API trong service đều có lỗi tương tự khi chưa kiểm tra.

### 17.3. Severity không chỉ dựa vào HTTP status

`200` không tự động có nghĩa critical; `403` không tự động có nghĩa an toàn. Đánh giá cần xét dữ liệu, actor cần có quyền gì, attacker cần điều kiện nào, có thể mở rộng phạm vi không, side effect và business impact. Evidence chứng minh hành vi; severity là phân tích dựa trên behavior và context.

## 18. Xác minh remediation và regression

### 18.1. Giữ test case, cập nhật expected nếu contract thay đổi

Sau khi sửa, chạy lại cùng test case, cùng fixture và cùng request để so sánh. Nếu endpoint contract hoặc expected behavior thay đổi hợp lệ, cập nhật test case version và ghi lý do; không sửa expected chỉ để test xanh.

### 18.2. Thu thập bằng chứng trước/sau

Retest nên ghi:

- Build/version trước và sau.
- Commit hoặc change reference.
- Fixture version.
- Cùng principal/resource/action.
- Actual status/body/state sau sửa.
- Log/audit evidence cho authorization decision nếu có.
- Test result và checksum mới.

Với IDOR, sau remediation User A phải bị từ chối và User B vẫn đọc được file của mình. Positive control bảo đảm fix không chặn nhầm mọi user.

### 18.3. Kiểm tra regression ở các đường vào khác

Nếu lỗi nằm trong service method, kiểm tra cả public API, internal endpoint, GraphQL/gRPC hoặc worker/job path dùng chung resource. Nếu fix ở gateway, kiểm tra direct-origin route và alternate ingress. Không kết luận toàn hệ thống đã được sửa chỉ vì một đường gọi không còn tái hiện.

## 19. Checklist evidence trước khi đóng finding

- [ ] Scope, host, route, environment và quyền kiểm thử được ghi rõ.
- [ ] Build/config version và timestamp UTC có trong manifest.
- [ ] Principal, role, tenant, object và state fixture được xác nhận.
- [ ] Setup script idempotent và có teardown an toàn.
- [ ] Positive control và negative control được chạy khi phù hợp.
- [ ] Steps có thể chạy lại; command/script và tool version được lưu.
- [ ] Expected result cụ thể về status, body, state và side effect.
- [ ] Actual result có request/response hoặc artifact quan sát được.
- [ ] Request ID/trace ID/log references được lưu nếu có.
- [ ] Credential, secret, PII và dữ liệu khách hàng được redact.
- [ ] Redaction giữ được quan hệ giữa principal, tenant và object.
- [ ] Không có thao tác phá hoại hoặc traffic vượt scope.
- [ ] Evidence manifest và checksum được tạo sau khi hoàn thiện artifact.
- [ ] Access control/retention của evidence phù hợp mức nhạy cảm.
- [ ] Finding nêu rõ impact đã chứng minh và limitation.
- [ ] Retest dùng cùng test case và có positive control.
- [ ] Regression được kiểm tra trên các đường gọi liên quan.
- [ ] Evidence/report không chứa token hoặc raw secret trong screenshot, shell history hay CI log.

## Kết luận

Bằng chứng test tái lập được là một chuỗi có thể kiểm tra từ precondition tới request, response, side effect và kết luận. Fixture synthetic, expected result cụ thể, request/response đã redact, telemetry correlation và manifest có checksum giúp người khác chạy lại mà không cần tin vào lời mô tả của tester. Hãy phân biệt finding với lỗi môi trường, ghi rõ giới hạn của điều đã chứng minh và dùng cùng test case để xác minh remediation. Một evidence package tốt vừa đủ chi tiết để tái lập, vừa hạn chế dữ liệu và tác động ngoài phạm vi kiểm thử.
