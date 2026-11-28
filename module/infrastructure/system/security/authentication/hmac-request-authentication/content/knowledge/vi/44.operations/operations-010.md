# Kiểm tra sau triển khai hệ thống xác thực HTTP request bằng HMAC

## 1. Mục tiêu: deployment thành công không đồng nghĩa xác thực an toàn

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, mỗi request HTTP được xác thực bằng **HMAC với shared secret** trên một **canonical request** do client và server thống nhất. Tùy hợp đồng ký, canonical request có thể chứa method, URI, header và/hoặc digest của body. Hệ thống còn cần **timestamp/nonce chống replay**, quản lý **key rotation/revocation**, chạy đúng qua **proxy/gateway** và phân biệt **authentication** với **authorization**.

Chương **Operations** đặt trọng tâm vào việc giữ các bảo đảm trên khi phần mềm thực sự vận hành. Bài **Kiểm tra sau triển khai** (*post-deployment verification*) hướng dẫn đánh giá một bản phát hành vừa được đưa vào staging hoặc production: **dịch vụ có hoạt động đúng, có tiếp tục từ chối request không hợp lệ, và các ranh giới tin cậy có nhất quán trên mọi instance hay không?**

Một health check HTTP 200 chỉ chứng minh tiến trình hoặc endpoint health đang phản hồi. Nó **không chứng minh**:

- Gateway chuyển tiếp đúng path/query/header/body mà client đã ký.
- Một HMAC signature hợp lệ có thể đi qua filter mới, key lookup, timestamp và nonce store.
- Một signature **sai** hoặc key bị revoke **không** được chấp nhận.
- Hai request cùng nonce trên hai replica không thể thực hiện nghiệp vụ hai lần.
- Một principal xác thực đúng nhưng thiếu quyền vẫn bị chặn bởi authorization.
- Khi secret store hoặc nonce store lỗi, verifier vẫn **fail closed**.

Vì vậy, một rollout an toàn cần **security smoke tests**, metrics, audit, dấu hiệu lệch cấu hình, tiêu chí dừng rollout và quy trình rollback **không làm sống lại credential đã bị thu hồi**.

**Sau bài học, người học có thể:** lập checklist post-deploy có thứ tự, chuẩn bị synthetic principal, viết probe Java 17 chỉ dùng credential test, xác nhận expected HTTP status và side effect, thiết lập canary gates cùng ngưỡng quan sát, kiểm tra sự đồng nhất đa replica và chọn rollback/forward-fix phù hợp.

> Các câu lệnh, endpoint, thời gian và ngưỡng trong bài là **ví dụ minh họa**, không phải cấu hình mặc định của Spring Security/HMAC. Trước khi chạy trên production, phải có synthetic endpoint, credential, quyền và lượng tải đã được phê duyệt. Không dùng request thử nghiệm để tạo thanh toán, gửi tiền hoặc truy cập dữ liệu thật.

## 2. Đường đi phải được xác minh từ ngoài vào trong

~~~mermaid
flowchart TD
    A[Synthetic client với secret test] --> B[Public ingress / TLS]
    B --> C[Gateway / WAF / proxy rewrite]
    C --> D[HTTP parser + route matcher]
    D --> E[HMAC authentication filter]
    E --> F[Header/canonical request + body digest]
    F --> G[Key resolution + validity + MAC verification]
    G --> H[Timestamp / atomic nonce claim]
    H --> I[Authenticated principal]
    I --> J{Authorization}
    J -- Đủ quyền --> K[Read-only synthetic handler]
    J -- Không đủ quyền --> L[403; không thực thi handler]
    E --> M[401 khi credential sai]
    G --> N[503 khi không thể kiểm tra key]
    H --> O[503 khi nonce store unavailable]
~~~

Trong diagram, timestamp được đặt sau MAC để minh họa ranh giới tin cậy. Một triển khai có thể **kiểm tra cú pháp/timestamp sớm** để giảm lookup đắt, miễn contract quy định rõ kết quả, MAC vẫn bắt buộc trước authentication, và **nonce chỉ được claim sau khi signature đã hợp lệ**.

### 2.1. Bốn lớp kiểm tra khác nhau

| Lớp | Câu hỏi kiểm chứng | Bằng chứng |
|---|---|---|
| **Deployment/infra** | Pod có ready, kết nối TLS, route có hoạt động? | Deployment status, readiness, gateway logs |
| **Cryptographic contract** | Server và client tạo cùng canonical bytes, đúng key/profile? | Golden vector, signed synthetic request |
| **Security semantics** | Sai MAC, replay, revoke và thiếu quyền có bị chặn? | Negative probes, audit event, no side effect |
| **Operational behavior** | Khi lỗi phụ thuộc/đổi rollout, hệ thống có fail closed và phục hồi? | Health, metrics, fault injection có kiểm soát, rollback test |

Một triển khai chỉ đạt yêu cầu khi cả bốn lớp đều có bằng chứng thích hợp. **Không lấy mức 2xx cao làm thước đo duy nhất**: nếu một filter bị vô hiệu hóa và nhận cả request không có chữ ký, tỷ lệ thành công có thể tăng nhưng bảo mật đã thất bại.

## 3. Quy trình post-deployment theo các cổng kiểm soát

Trình tự đề xuất cho một deployment có ảnh hưởng HMAC:

~~~mermaid
flowchart TD
    A[Preflight: version, policy, key, rollback] --> B[Deploy canary nhỏ]
    B --> C[Smoke hợp lệ qua ingress thực]
    C --> D[Negative probes đã được phê duyệt]
    D --> E[Replay / key / authz invariants]
    E --> F[Kiểm tra metrics, logs và regional drift]
    F --> G{Security gate và SLO gate PASS?}
    G -- Có --> H[Tăng traffic từng nấc]
    H --> F
    G -- Không --> I[Freeze rollout + mitigate]
    I --> J{Rollback có an toàn theo key policy?}
    J -- Có --> K[Rollback phiên bản phần mềm]
    J -- Không --> L[Forward-fix / isolate / disable route an toàn]
    H --> M[Ổn định + ghi nhận kết quả]
~~~

Các nấc traffic 1%, 5%, 25%, 100% chỉ là **ví dụ canary**. Mức phân bổ, thời gian quan sát và điều kiện dừng phải dựa trên traffic thật, số replica, thời gian cache TTL, lịch batch client và rủi ro endpoint. Chạy một probe duy nhất trên một pod không đủ để kết luận cả region đã an toàn.

### 3.1. Preflight trước khi deployment

Cần xác nhận:

1. **Version cụ thể**: image digest, build ID, SHA release, cấu hình security chain, gateway route version, feature flags và thay đổi database/secret store.
2. **Contract ký**: signature profile được chấp nhận, method, public URI, query, signed headers, raw body/digest, charset, newline, timestamp format, nonce rules.
3. **Key policy**: key ID được phép, vòng đời active/overlap/revoked, secret storage/cache/invalidation và chính sách tenant.
4. **Anti-replay**: nonce store endpoint, atomic operation, TTL, partition scope, deadline và fail-closed.
5. **Authorization**: yêu cầu authority/tenant/resource cho từng protected route; không có `permitAll` fallback ngoài dự kiến.
6. **Synthetic test tenant**: identity/credential test, endpoint **read-only hoặc no-op**, không chứa dữ liệu thật; quyền hạn tối thiểu.
7. **Observability**: dashboard, alert, audit reason enum, trace/correlation ID đáng tin, baseline SLO.
8. **Quyền thực hiện**: người cho phép canary, người chịu trách nhiệm an toàn thông tin, kênh khẩn cấp và chiến lược rollback.

Nếu một trong các điểm **cốt lõi** như credential, nonce store, policy revoke hoặc route mapping chưa rõ, đừng coi “service ready” là bằng chứng sẵn sàng tăng tải.

## 4. Thiết kế synthetic identity và endpoint kiểm tra

Production security probe không được vô tình thực hiện tác vụ nghiệp vụ. Một bộ fixture an toàn có thể gồm:

| Thành phần | Ví dụ | Ràng buộc |
|---|---|---|
| Principal | `synthetic-hmac-probe` | Không phải tài khoản khách hàng thật |
| Key ID | `synthetic-probe-v2` | Chỉ thuộc tenant/namespace test |
| Secret | Lấy từ secret manager theo quyền hạn | Không hardcode vào source/log/CI output |
| Authority | `probe:read` | Không có quyền thanh toán/ghi dữ liệu |
| Endpoint thành công | `GET /public/health/signed-probe` | Không side effect, yêu cầu HMAC thực |
| Endpoint thiếu quyền | `GET /public/health/admin-probe` | Yêu cầu authority mà principal không có |
| Nonce | Random, mới mỗi request | Không dùng lại giữa positive/negative test trừ replay test |
| Timestamp | UTC hiện hành theo contract | Đồng hồ probe được đồng bộ với server |
| Correlation | Request ID do hệ thống kiểm soát | Dùng để đối chiếu audit, **không** làm metric tag |

Synthetic principal **không được bypass HMAC**. Nếu probe route được đánh dấu `permitAll` hoặc filter chỉ mock trả 200, kết quả không xác thực được đường đi HMAC thực tế. Đầu ra thành công có thể là HTTP 204 kèm metadata không nhạy cảm; không cần phản hồi lại key ID, MAC hay raw canonical.

### 4.1. Production probe và staging fault injection khác nhau

**Production probes** nên:

- Chạy read-only/no-op, số lượng thấp có rate-limit, được đánh dấu trong audit bằng nguồn tin cậy.
- Dùng key test có khả năng revoke ngay; không cấp quyền thao tác dữ liệu thật.
- Thực hiện negative probes ở mức được phê duyệt, tránh bắn hàng nghìn malformed requests làm kích hoạt WAF, lockout hoặc chiếm quota partner thật.
- Không cố tình tắt Redis/secret manager/KMS để test fail-closed trong giờ cao điểm.

**Staging/pre-production** mới là nơi thích hợp cho fault injection: ngắt key store, làm chậm nonce store, kiểm thử race đa replica, key revocation, clock skew lớn và gateway rewrite bất thường. Chỉ chạy fault injection production khi có chương trình chaos được phê duyệt và blast-radius kiểm soát.

## 5. Smoke test dương: request hợp lệ phải đi qua toàn bộ security chain

Một smoke test cơ bản gửi request có:

~~~http
GET /public/health/signed-probe?check=postdeploy HTTP/1.1
Host: api.example.test
X-Key-Id: synthetic-probe-v2
X-Timestamp: 2026-11-28T10:00:00Z
X-Nonce: 74f2601e-20e7-449f-a4b8-592e2c339d69
X-Signature: <base64-hmac-mac>
~~~

Server dùng key record của synthetic client để xác minh chữ ký. Chỉ khi MAC đúng, timestamp còn trong window và nonce được claim mới tạo `Authentication` và cho đi tiếp. Nếu route yêu cầu `probe:read`, principal cần đúng quyền mới nhận 2xx/204 theo contract.

**Expected evidence**:

- HTTP status/latency trong ngưỡng đã thỏa thuận.
- Ghi nhận chính xác route ID/region/build version đã phục vụ request.
- Counter `authn_accepted` tăng tương ứng, không có lỗi MAC/replay/key unavailable ngoài dự kiến.
- Probe handler được gọi **một lần**, **không có thao tác ghi**.
- Không in shared secret, expected MAC, signed canonical body hay nonce trong log.

Không coi 200 từ gateway cache là thành công: signed probe endpoint nên được cấu hình **không cache response** và đánh giá chắc chắn request đã tới verifier của phiên bản mới. Nếu gateway có health endpoint riêng, đo riêng, không thay thế synthetic HMAC test.

### 5.1. Golden vector có ích sau triển khai

Thử nghiệm nên có **golden vector độc lập** của signature profile hiện hành. Ví dụ hợp đồng giả định ký:

~~~text
HMAC-V1
<METHOD_UPPERCASE>
<TRUSTED_PUBLIC_RAW_PATH>
<TRUSTED_PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_EXACT_BODY_BYTES>
~~~

Canonical được nối LF, mã hóa UTF-8, không thêm LF cuối. **Đây chỉ là một contract minh họa**; nếu API thực dùng signed headers/version khác, probe phải dùng đúng hợp đồng của API. Golden vector nên được xác nhận bởi hai implementation độc lập (ví dụ SDK client và server) để phát hiện cả hai phía cùng mắc một bug bỏ query khỏi chữ ký.

## 6. Negative probes: từ chối sai mà không cho handler chạy

Đừng chỉ gửi request hợp lệ. Một deployment có thể vô tình bỏ filter hoặc bật fallback, khi đó request không có chữ ký cũng nhận 2xx.

| Probe | Cách tạo | Expected |
|---|---|---|
| Thiếu signature | Bỏ header chữ ký trên protected probe route | **401** theo contract, không handler |
| HMAC sai | Ký A, gửi request B nhưng giữ MAC của A | **401**, không handler |
| Query bị đổi | Ký `check=postdeploy`, gửi `check=other` | **401** nếu query thuộc contract |
| Path bị đổi | Ký route A, gửi route B đều protected | **401** nếu path được ký |
| Body bị đổi | Ký body A, gửi bytes B | **401** nếu body digest thuộc contract |
| Timestamp hết cửa sổ | Timestamp cũ nhưng MAC hợp lệ | **401**, không gọi handler |
| Nonce replay | Gửi lại request đã được chấp nhận | **401**, không handler lần hai |
| Key revoked | Ký bằng key test đã được revoke | **401**, không xác thực |
| Thiếu authority | MAC đúng, principal không có quyền | **403**, không handler |
| Key/nonce store unavailable | Fault injection staging | **503** minh họa, fail closed |
| Body vượt hạn mức | Dữ liệu test có giới hạn, staging | **413** theo HTTP policy |

**Cần phân biệt các nguyên nhân 401.** Nếu test thay query nhưng dùng một nonce **đã claim**, 401 có thể do replay chứ không phải do MAC kiểm tra query. Mỗi negative case có nonce mới; tạo MAC của dữ liệu gốc theo nonce mới, rồi chỉ thay một signed field. Test replay mới cố ý dùng lại đúng nonce.

**Không bắn negative probes không giới hạn lên production.** Dùng endpoint synthetic, key test, cadence thấp, phối hợp với WAF/on-call; nếu hệ thống có lockout hoặc rate-limit theo key ID, ghi rõ các probe được phép và cách xác định kết quả.

### 6.1. HTTP status không chứng minh toàn bộ hành vi

Một 401 sau khi controller đã ghi DB vẫn là thất bại bảo mật. Với staging/integration tests, assert thêm:

~~~text
given: protected handler + synthetic key + event/database spy
when: send invalid MAC / replay / insufficient authority
then:
  HTTP status = expected rejection
  handler invocation = 0 for rejected requests
  database writes = 0
  events published = 0
  downstream commands = 0
~~~

Ở production probe no-op, có thể đếm invocation trong synthetic handler và audit thay vì đo DB thật; **đừng tạo side effect thực rồi cố rollback chỉ để kiểm tra**.

## 7. Kiểm tra canonical request qua gateway/proxy

Đường đi triển khai có thể chứa TLS termination, WAF, path rewrite, query normalization, Content-Encoding transformation hoặc thêm/bỏ header. Những thay đổi đó có thể làm client và verifier tạo canonical khác nhau.

| Biến đổi gateway | Test post-deploy | Rủi ro |
|---|---|---|
| Public path → internal path | Sign public path, gửi qua ingress thật | Verifier dùng sai internal URI và từ chối request hợp lệ |
| Query reorder/percent encoding | Tạo vector raw/canonical theo hợp đồng | MAC sai hoặc verifier/handler diễn giải khác |
| Strip/append signed header | Probe với đúng tập signed headers | Authn fail hoặc hợp đồng ký bị thu hẹp |
| Normalize double slash/dot segments | Staging matrix path ambiguity | Security matcher và router không cùng operation |
| Body decode/serialize | Probe body bytes cố định | Digest sai hoặc body được xử lý khác nội dung ký |
| Forwarded metadata | Gửi giả `X-Original-URI` từ client test | Header giả không thay được signed public target |
| HTTP/2 ↔ HTTP/1.1 | Test client protocol khác nhau | `:path`/request target không đổi nghĩa |
| Routing giữa nhiều region | So sánh cùng vector ở từng ingress | Drift cấu hình, key/policy khác nhau |

**Không lấy `X-Forwarded-*`/`X-Original-URI` do client tự khai làm dữ kiện tin cậy**. Nếu service phải khôi phục public target, chỉ dùng metadata do gateway đáng tin phát hành, ingress đã strip/overwrite giá trị từ client và hop tới service có kiểm soát (network identity/mTLS hoặc tương đương). Kiểm tra route mapping để không xác minh chữ ký cho endpoint A nhưng xử lý endpoint B.

Một direct-to-service probe có thể giúp cô lập lỗi, nhưng **không thay thế** smoke test đi qua chính đường ingress/edge mà đối tác sử dụng. Việc direct bypass gateway thường phải bị network policy chặn trong production.

## 8. Timestamp, clock skew và nonce chống replay

### 8.1. Freshness theo UTC

Ví dụ hợp đồng cho phép timestamp nằm trong `now ± W` với `W = 300 giây` và chấp nhận hai biên. Quy tắc:

~~~text
timestamp < now - W -> expired
timestamp > now + W -> future
otherwise           -> freshness valid
~~~

Trong post-deploy:

- So sánh sức khỏe NTP/time synchronization của các node/region, clock drift và sự khác biệt kết quả giữa replica.
- Kiểm tra format UTC/offset đúng hợp đồng; không tự giả định giờ địa phương.
- Dùng `Clock.fixed` trong test staging để kiểm tra đúng biên; production probes dùng thời gian tin cậy đang chạy.
- Kiểm tra metric `expired` và `future` theo route, nhưng không coi timestamp do client tự gửi là bằng chứng danh tính.
- Không mở rộng window bừa bãi để làm giảm 401; window rộng tăng khoảng thời gian replay tiềm năng.

### 8.2. Nonce phải được claim atomically

Một MAC hợp lệ **không chặn replay** nếu request được dùng lại. Nonce store chung cho nhiều replica phải có thao tác tương đương:

~~~text
SET hmac:nonce:<trusted-scope>:<hash(nonce)> 1 NX PX <ttl-ms>
~~~

Ví dụ Redis `NX` + `PX` trong **một thao tác atomic**; không `GET` rồi `SET` vì hai request đồng thời có thể cùng thấy “chưa tồn tại”. Nonce scope phải dựa trên client/key identity **đã được xác thực**, không để header key ID chưa tin cậy quyết định identity. TTL phải bao phủ toàn bộ thời gian request/signature còn có thể được chấp nhận; với window đối xứng, cần xét khoảng tối đa gần `2W` từ lần nhận sớm nhất, không mặc định TTL `W` là đủ.

**Post-deploy multi-replica test ở staging**:

~~~text
Client sends identical valid HMAC + nonce N concurrently
       ├──> Service replica A ──┐
       └──> Service replica B ──┴──> shared nonce store

Expected:
  exactly one atomic nonce claim succeeds
  at most one protected handler invocation
  the other request is rejected as replay
~~~

Nếu cả hai request bị 401 vì timestamp sai, test chưa chứng minh atomicity. Cần baseline hợp lệ và quan sát claim result. Nếu store không khả dụng, tất cả request không thể xác minh replay phải **fail closed** thay vì tự nhận nonce là mới.

## 9. Kiểm tra vòng đời key và tính nhất quán của key cache

Key lookup có thể được cache ở từng pod; bản phát hành mới có thể vô tình dùng cache sai hoặc trì hoãn thu hồi key. Post-deploy cần đối chiếu **key state** với policy.

| Tình huống | Kiểm tra |
|---|---|
| Key mới được kích hoạt | Các replica nhận key theo thời điểm `notBefore` đã thỏa thuận |
| K1/K2 overlap được phép | Key còn active ký đúng profile vẫn được chấp nhận |
| K1 đã revoke | Không replica nào dùng K1 vượt quá giới hạn revocation propagation |
| Key hết `notAfter` | Từ chối dù cache entry còn TTL |
| Key ID không tồn tại | Trả lỗi credential chung, không leak existence |
| Key store timeout | Trả lỗi không thể xác minh; không cache timeout thành NOT_FOUND |
| Secret manager rotation | Verifier chọn đúng secret/key version, không thử mọi secret |
| HMAC profile deprecation | Không fallback algorithm cũ khi profile mới sai |

**Không thử revoke một key production đang phục vụ đối tác chỉ để làm smoke test.** Dùng synthetic key riêng trong staging, hoặc key test production có phạm vi hạn chế và quy trình revoke được duyệt.

### 9.1. Kiểm tra cache invalidation

Một test có giá trị:

~~~text
1. Prime cache ở replica A và B bằng key K đang active.
2. Revoke K trong kho key test.
3. Phát invalidation/policy update theo thiết kế.
4. Gửi request ký bằng K tới mọi replica.
5. Kiểm tra K bị từ chối trong giới hạn đã công bố.
6. Simulate một replica bị mất invalidation (staging).
7. Xác minh fallback không chấp nhận key stale trái policy.
~~~

Cache TTL **chỉ giới hạn độ cũ**, không bảo đảm revoke tức thời. Một rollback ứng dụng cũng không được tự cho phép key đã revoked trở lại. Nếu hệ thống không thể xác minh trạng thái key đủ tin cậy thì chọn **fail closed**.

## 10. Đảm bảo authorization vẫn độc lập với HMAC

Xác thực thành công chứng minh request được ký bằng secret thuộc key/client được phép; **không đồng nghĩa** người gọi có quyền trên mọi route hoặc tenant.

Post-deploy phải thử:

1. Principal có `probe:read` gọi protected read-only probe: authn đúng, authz cho phép.
2. Principal đó gọi route yêu cầu `probe:admin`: MAC vẫn đúng nhưng **403 Forbidden**.
3. Hai synthetic tenants: MAC của tenant A đúng **không** cho phép thao tác trên resource tenant B.
4. Route có method khác (GET/POST) và alias path: không có đường đi bỏ qua HMAC chain hoặc policy.
5. Nếu API dùng method-level security, thay đổi cấu hình không làm các annotation/authorization manager ngừng hoạt động.

Không dùng `@WithMockUser` để thay thế kiểm tra xác thực HMAC trong integration tests; mock principal có thể che bug filter. Cũng không lấy `X-Tenant-Id` hoặc `X-Role` client tự gửi làm authority mà không kiểm tra ràng buộc với key record.

**Kết quả HTTP** cần phân biệt: 401 vì chưa xác thực/credential sai; 403 sau khi đã xác thực nhưng không đủ quyền. Lỗi authorization nên không tạo business side effect.

## 11. Fail-closed và dependency health

Các tình huống phải xem là **điều kiện chặn rollout** nếu xảy ra trong phạm vi được bảo vệ:

- Không có key store nhưng request vẫn được chấp nhận vì code `catch(Exception) { return true; }`.
- Nonce store lỗi nhưng filter bỏ qua `claimOnce`.
- Request quá lớn được nhận và buffer không giới hạn.
- HMAC filter vắng mặt ở một protected route hay một replica.
- Key đã revoke tiếp tục được dùng do cache stale ngoài policy.
- Gateway hoặc middleware tạo `Authentication` từ header chưa được xác thực.

Khi dependency lỗi, cần **từ chối request an toàn** (ví dụ HTTP 503), không “giảm bảo mật để giữ uptime”.

| Dependency | Failure injection ở staging | Kỳ vọng |
|---|---|---|
| Trusted key repository | Timeout, 5xx, network partition | Không coi là key unknown; 503/fail closed |
| Secret manager/HSM | Quota, timeout, unavailable | Không thử key tùy ý hoặc bypass MAC |
| Nonce store | Redis down, high latency | Không cho qua nonce khi không claim được |
| Policy/config store | Không xác minh được allowed profile/revoke | Không cấp quyền bằng policy stale ngoài giới hạn |
| Gateway trust metadata | Header bị giả, route không xác định | Không chấp nhận signed target giả |
| Time synchronization | Lệch clock trên một replica | Không nhận/từ chối không nhất quán vượt cửa sổ cho phép |

**Production post-deploy** chủ yếu xác nhận dependency readiness và hành vi qua **probes an toàn**. Fault injection có tính phá hoại phải được kiểm thử ở staging hoặc một vùng thử riêng được phê duyệt.

## 12. Quan sát sau rollout: metrics, traces, logs và audit

Một dashboard sau triển khai không chỉ hiển thị số lượng request. Cần kiểm tra **đúng nguyên nhân và đúng mẫu số**.

| Tín hiệu | Mục tiêu | Dấu hiệu đáng chú ý |
|---|---|---|
| Tổng request vào protected route | Biết volume và phân phối traffic | Canary traffic chưa tới pod mới |
| Authn accepted/rejected/unavailable | Đo hành vi xác thực | Tăng accepted bất thường khi filter bị bỏ |
| Signature invalid / timestamp expired/future | Phát hiện sai hợp đồng/clock | Spike sau gateway deploy |
| Replay rejected | Quan sát nonces trùng | Tăng bất ngờ khi retry/client lỗi |
| Key lookup error/timeout | Phân biệt 401 và 503 | Secret manager/cache gặp sự cố |
| Nonce claim latency/error | Theo dõi chống replay | p99 tăng, backlog hoặc 503 |
| HTTP 401/403/413/429/503 | Phân loại lỗi và tải | 403 giảm bất thường do policy bị bỏ |
| Authn/HTTP p50/p95/p99 | Độ trễ và tail latency | Chậm do key/nonce hoặc body |
| Key rotation/revocation propagation | Chính sách trên các replica | Pod cũ chấp nhận key revoked |
| Business side effect audit | Không xử lý request bị từ chối | Sự kiện write sau authn failure |

### 12.1. Ví dụ PromQL

Giả sử hệ thống xuất counter `hmac_auth_requests_total` với nhãn **hữu hạn** `service`, `route`, `outcome` và `reason`.

Tốc độ từ chối do signature:

~~~promql
sum by (service, route) (
  rate(hmac_auth_requests_total{
    outcome="rejected",
    reason="signature_invalid"
  }[5m])
)
~~~

Tỷ lệ lỗi xác thực (không gộp 503 với credential rejection nếu policy tách `unavailable`):

~~~promql
sum by (service, route) (
  rate(hmac_auth_requests_total{outcome="rejected"}[5m])
)
/
clamp_min(
  sum by (service, route) (
    rate(hmac_auth_requests_total[5m])
  ),
  1e-9
)
~~~

Đây là **tỷ lệ trên những attempt được counter định nghĩa**, không nhất thiết bằng tỷ lệ trên mọi request tới gateway. Chỉ dùng alert tỷ lệ khi có mẫu số đủ lớn; không kết luận từ vài request synthetic. Mỗi metric phải có tài liệu về stage đo, tránh đếm một request nhiều lần qua filter, gateway và global exception handler.

### 12.2. Nhãn nào không được đưa vào metrics?

Không dùng các giá trị sau làm metric tag:

- Raw `X-Key-Id` chưa được xác thực, raw tenant ID/client ID hoặc header version tự do.
- Nonce, timestamp, full HMAC signature, body hash, canonical request.
- Raw URI/query, request ID/trace ID, IP tùy client hoặc user agent tùy ý.

Chúng có thể chứa dữ liệu nhạy cảm hoặc tạo **cardinality explosion** khi attacker gửi input ngẫu nhiên. Dùng route ID/template từ server, enum reason/outcome, environment, region và deployment version có số lượng giá trị được kiểm soát. Thông tin chi tiết cần điều tra được lưu trong log bảo vệ quyền truy cập với redaction và retention phù hợp.

### 12.3. So sánh baseline và canary

Đừng so raw count của pod canary 5% với pod cũ 95%. Cần chuẩn hóa theo QPS, loại route, phiên bản signature, body size và thời gian lấy mẫu. So sánh trước/sau còn phải xem:

- Client batch ít traffic có xuất hiện trong cửa sổ quan sát không?
- Một region có clock lệch hoặc gateway config khác không?
- Cache key/nonce có warm-up khác nhau giữa pod mới/cũ không?
- Có deployment độc lập tại edge/WAF/secret manager cùng thời gian không?
- Có tăng load hoặc thay đổi mix request chứ không phải bug crypto không?

Nếu canary không có đủ **positive probes** và **negative probes** trên phiên bản mới, chưa được tuyên bố security gate PASS chỉ vì metric 401 không tăng.

## 13. Java 17: một synthetic signed-request smoke client

Ví dụ dưới minh họa probe read-only. Nó **không phải protocol HMAC chuẩn có sẵn**; chỉ áp dụng nếu server dùng đúng canonical contract giả định tại mục 5, với HMAC-SHA256, body GET rỗng, path/query raw và các header đã chỉ định. Trong production phải thay bằng SDK signer đã được kiểm thử độc lập theo profile thực.

Biến môi trường `HMAC_PROBE_SECRET_B64` chỉ chứa **secret test dành riêng cho probe** và nên được inject từ secret manager. Không log environment, secret hoặc MAC.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacPostDeployProbe {
    private static final String KEY_ID = "synthetic-probe-v2";
    private static final String PATH = "/public/health/signed-probe";
    private static final String QUERY = "check=postdeploy";

    private static String sign(byte[] secret, String canonical)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return Base64.getEncoder().encodeToString(
                mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected exactly one approved HTTPS origin");
        }
        URI origin = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(origin.getScheme())
                || origin.getHost() == null
                || (origin.getRawPath() != null
                    && !origin.getRawPath().isEmpty()
                    && !"/".equals(origin.getRawPath()))
                || origin.getRawQuery() != null
                || origin.getRawFragment() != null
                || origin.getRawUserInfo() != null) {
            throw new IllegalArgumentException("Invalid probe origin");
        }

        String encodedSecret = System.getenv("HMAC_PROBE_SECRET_B64");
        if (encodedSecret == null || encodedSecret.isBlank()) {
            throw new IllegalStateException(
                    "Probe secret must be provided by secret manager");
        }
        byte[] secret = Base64.getDecoder().decode(encodedSecret);
        String timestamp = Instant.now().toString();
        String nonce = UUID.randomUUID().toString();
        byte[] emptyBody = new byte[0];
        String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(emptyBody));

        String canonical = String.join("\n",
                "HMAC-V1",
                "GET",
                PATH,
                QUERY,
                KEY_ID,
                timestamp,
                nonce,
                digest);

        String signature = sign(secret, canonical);
        String originText = origin.toString();
        if (originText.endsWith("/")) {
            originText = originText.substring(0, originText.length() - 1);
        }
        URI uri = URI.create(originText + PATH + "?" + QUERY);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Key-Id", KEY_ID)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .header("Cache-Control", "no-store")
                .GET()
                .build();

        // Không tắt TLS certificate/hostname verification.
        HttpResponse<Void> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.discarding());

        // API synthetic ví dụ trả 204, không cache và không side effect.
        if (response.statusCode() != 204) {
            throw new IllegalStateException(
                    "HMAC probe failed; HTTP status="
                    + response.statusCode());
        }
        System.out.println("HMAC synthetic probe: PASS (HTTP 204)");
    }
}
~~~

**Không chạy code mẫu trực tiếp trên một API có contract khác.** Nếu V2 dùng HMAC-SHA512 hoặc ký thêm `Content-Type`/`Host`, chữ ký trên sẽ sai và phải đổi code theo **hợp đồng thật**. Chuỗi `synthetic-probe-v2` trong ví dụ là tên key test, **không mặc định tuyên bố đang dùng profile V2**. Nên lưu key ID/profile theo cấu hình trusted thay vì suy algorithm từ suffix.

Một probe production có thể dùng một binary/SDK chuyên dụng phát hành cùng contract vectors thay vì code tự chế. Hãy giới hạn nguồn chạy probe, quyền truy cập secret, tần suất gọi và route đích; tránh cung cấp công cụ ký request tùy ý cho một key có scope rộng.

### 13.1. Kiểm tra failure không làm lộ secret

Khi status không phải 204, probe chỉ in status và mã tương quan không nhạy cảm. Không in:

~~~text
HMAC_PROBE_SECRET_B64
X-Signature
canonical request có raw query/body nhạy cảm
nonce + toàn bộ header từ request production
~~~

CI/CD log có retention và quyền xem khác nhau; vì vậy “chỉ là probe” không làm secret an toàn khi bị in ra. Nếu cần debug ký sai, dùng golden vector với secret giả và test harness cô lập.

## 14. Cổng canary: pass/fail phải có tiêu chí rõ

Một bảng **go/no-go** nên được chốt **trước** khi rollout, không tự nới ngưỡng sau khi thấy lỗi:

| Gate | PASS khi | STOP khi |
|---|---|---|
| Deployment identity | Đúng artifact + security config + gateway version | Version drift hoặc thiếu config |
| Positive HMAC probe | Đúng code mới trả expected 2xx/204 qua ingress | Request đúng contract bị từ chối |
| Negative MAC/unsigned | Protected route trả 401, không handler | Request sai/thiếu MAC có 2xx |
| Replay protection | Replay bị chặn, nonces atomic | Hai request cùng nonce có thể thực thi |
| Key/revoke policy | Key revoked bị từ chối trong SLA policy | Key stale vẫn active ngoài giới hạn |
| Authorization | Principal thiếu quyền nhận 403 | Thiếu quyền nhưng được xử lý |
| Fail-closed | Không bỏ verifier khi store không sẵn sàng | Bất kỳ fail-open/bypass nào |
| Gateway canonical | Public method/path/query/header/body đúng | Proxy làm verifier và handler khác nghĩa |
| Errors/latency | Nằm trong ngưỡng so với baseline | 401/503/p99 tăng bền vững quá ngưỡng |
| Fleet consistency | Tất cả vùng/replica đã thử đều đúng | Có pod/region vẫn chấp nhận policy cũ |

**Security invariants là hard stop.** Không tăng rollout nếu kiểm tra MAC bị bypass, nonce replay được chấp nhận, route thiếu authz hoặc key revoked vẫn được xác thực. Với lỗi chỉ liên quan latency/availability, IC/release owner có thể cân nhắc rollback hay giới hạn traffic theo runbook; nhưng **không được hạ bảo mật để đổi lấy 2xx**.

### 14.1. Ngưỡng quan sát chỉ là ví dụ

Ví dụ một team đặt trước:

~~~text
- HMAC positive synthetic probes: 100% trong các region được kiểm tra
- Negative unsigned/MAC/replay/authz probes: 0 bypass
- Authn p99: không vượt ngưỡng SLO đã được phê duyệt
- Key/nonce store unavailable: không có fail-open
- 401/503 rate: không tăng ngoài baseline + allowance đã định
- Mỗi canary stage: đủ volume và đủ thời gian để thấy cache refresh
~~~

Không áp một ngưỡng 401 chung cho API có pattern khác nhau. Client gọi sai chữ ký có thể làm 401 tăng mà không liên quan release; ngược lại bypass filter có thể làm 401 giảm. Kết hợp **probe có kỳ vọng**, traffic thực, audit và diff cấu hình.

## 15. Rollback và forward-fix phải bảo toàn trạng thái bảo mật

Rollback code không giống rollback mọi chính sách. **Key revocation, migration sang profile mạnh hơn và nonce history** có thể đã thay đổi kể từ trước deployment.

### 15.1. Những thứ có thể rollback

- Binary/filter/handler khi phiên bản cũ **vẫn đáp ứng** contract bảo mật hiện hành.
- Gateway route/config nếu quay về public target mapping đúng hợp đồng.
- Feature flag **không làm giảm kiểm soát bảo mật** và có đánh giá impact.
- Thay đổi cache tuning không làm hỏng revoke/secret management.

### 15.2. Những thứ không tự ý rollback

- Kích hoạt lại key đã revoke do nghi compromise.
- Chấp nhận lại HMAC signature profile V1 khi client đã buộc `v2-required`.
- Xóa nonce đã claim, reset replay protection hoặc giảm TTL để “dễ retry”.
- Bỏ xác minh signed path/query/body/headers để vượt qua proxy 401.
- Chuyển protected endpoint sang `permitAll` hoặc bỏ authorization.

Một rollback binary có thể **không an toàn** nếu bản cũ không biết profile mới, thiếu kiểm tra nonce hoặc không nắm trạng thái revoke. Khi đó phải **forward-fix**, cô lập route, giảm traffic hoặc tạm từ chối an toàn theo chính sách; không “rollback bằng mọi giá”.

### 15.3. Sau rollback vẫn phải kiểm tra lại

Chạy lại positive HMAC probes, negative unsigned/MAC, replay, revoke, authz và gateway mapping, trên **tất cả vùng đã rollback**. Đối chiếu deploy manifests và policy/secret state thực tế để không tạo “split-brain” giữa pod cũ và mới.

## 16. Quy trình xử lý khi cổng kiểm tra thất bại

Một bảng hướng dẫn triage:

| Triệu chứng | Giả thuyết ban đầu | Kiểm tra phân biệt | Hành động an toàn |
|---|---|---|---|
| Positive HMAC 401 sau deploy | Canonical mismatch | So golden vector qua gateway; public/raw URI | Freeze rollout; sửa route/contract |
| 401 `expired/future` tăng | Clock skew/queue | Đồng hồ replica, NTP, gateway latency | Sửa time sync/queue; không nới window tùy tiện |
| 401 `signature_invalid` tăng một route | Proxy rewrite/header/body | Signed target và raw body hash | So sánh contract, rollback proxy nếu an toàn |
| Replay request nhận 2xx hai lần | Nonce store race/bypass | Atomic claim, shared scope, handler spy | Stop rollout/isolate; điều tra side effects |
| V2 key không hoạt động | Key/policy cache chưa sync | Key state và profile allowlist từng replica | Đồng bộ policy, không thử secret bất kỳ |
| Key revoked vẫn accepted | Stale cache/revoke failure | Per-replica key status; invalidation events | Hard stop, disable route an toàn |
| 403 không xuất hiện khi thiếu quyền | Authz matcher bị bỏ | Security chain order, route policy | Hard stop, sửa policy |
| 503 trên nhiều request | Key/nonce store unavailable | Dependency metrics, connection/timeout | Fail closed, khôi phục phụ thuộc |
| 2xx tăng bất thường sau deploy | Có thể filter bị bypass | Negative unsigned/MAC probes | Hard stop nếu bypass |
| p99 tăng nhưng authn metrics bình thường | Gateway/body/handler bottleneck | Trace critical path + QPS | Tối ưu sau khi xác minh bảo mật |

**Đừng phân loại mọi 401 là “HMAC sai”.** Lỗi timestamp, key revoked, nonce replay và gateway canonical mismatch có đường điều tra khác nhau. Phản hồi bên ngoài có thể dùng 401 chung để hạn chế oracle, nhưng event nội bộ phải có reason code cố định được bảo vệ.

### 16.1. Thu thập evidence có kiểm soát

Cần lưu:

- Release/build/config identifier và thời điểm rollout UTC.
- Region/replica/route ID, synthetic test vector ID và expected outcome.
- Canary metrics trong cùng cửa sổ, baseline và query/dashboard tham chiếu.
- Audit events với reason enum; đã xác minh signed fields và authz checks hay chưa.
- Kết quả probes (PASS/FAIL, status, latency), không chứa secret hoặc full MAC.
- Quyết định freeze/rollback/forward-fix, owner và timestamp.
- Kết quả test lại sau mitigation.

Không đưa raw request production, secret, full signature, token, nonce hoặc payload tài chính vào ticket chung. Khi cần phân tích byte canonical, dùng dữ liệu giả trong môi trường có quyền, tách khỏi thông báo bên ngoài.

## 17. Ví dụ một ca triển khai thay đổi gateway

**Tình huống giả định:** release mới đổi ingress mapping từ `/public/v1/payments` sang `/payments` và nâng SDK signer lên profile mới. Sau triển khai 5% canary, một số request HMAC trả 401.

### 17.1. Thực hiện các bước

1. **Xác minh artifact:** đúng image/config, tất cả canary pod dùng cùng HMAC profile và route matcher.
2. **Positive probe qua ingress:** ký `GET /public/health/signed-probe?check=postdeploy` bằng synthetic key. Nếu 204 thành công, chưa thể kết luận route payments cũng đúng; cần vector riêng cho route này ở staging.
3. **Negative probe:** thiếu signature phải 401; nếu nhận 2xx thì dừng rollout ngay vì filter bị bỏ.
4. **So sánh canonical:** client ký public path nhưng verifier đang lấy internal path `/payments`. Kiểm tra metadata gateway đáng tin và contract của profile hiện hành.
5. **Kiểm tra timestamp/key/nonce:** loại trừ 401 do clock skew, key activation/rotation hoặc nonce replay.
6. **Điều chỉnh hoặc rollback gateway:** chỉ khi vẫn giữ đúng public-target binding, key state và security policy.
7. **Kiểm tra authorization:** HMAC đúng nhưng principal thiếu `payments:write` vẫn trả 403.
8. **Quan sát fleet:** 401 về baseline, probes qua các region mới/cũ thành công, không có unsigned request được chấp nhận.
9. **Ghi timeline/notice:** nếu ảnh hưởng đối tác, thông báo bằng dữ kiện xác minh; không khuyên tắt HMAC.

### 17.2. Kết quả vận hành mong muốn

~~~text
Release ID: release-hmac-2026-11-28-b
Canary: 5% (mức giả định)
Observed:
  signed positive probe: PASS
  unsigned negative probe: PASS
  payments path golden vector via gateway: FAIL
  nonce/replay negative probe: PASS
Decision:
  STOP rollout
  Correct trusted public path reconstruction
  Repeat authn/authz + gateway probes before expanding
~~~

Không đánh dấu rollout PASS vì 3/4 probes đạt: **canonical route binding là một điều kiện bắt buộc**. Nếu server không thể xác minh đúng path được ký, một workaround bỏ path khỏi canonical là **không chấp nhận được**.

## 18. Ma trận kiểm thử sau triển khai theo phạm vi

| Kiểm tra | CI/unit | Staging | Production an toàn | Ghi chú |
|---|---|---|---|---|
| Golden vector crypto | Có | Có | Có thể qua synthetic read-only probe | Không tiết lộ secret thật |
| Positive signed request | Có | Có | Có, read-only/no-op | Qua ingress thật |
| Missing/wrong MAC | Có | Có | Có, với synthetic key/cadence thấp | Không kích hoạt lockout client thật |
| Changed signed path/query/body | Có | Có | Chọn vài case an toàn | Không gửi malformed traffic ồ ạt |
| Timestamp boundaries | Clock fixed | Có | Theo telemetry an toàn | Không thay đồng hồ production |
| Concurrent nonce replay | Có (fake atomic) | Có (Redis/multi-replica) | Chỉ trong chương trình được phê duyệt | Không phá store |
| Key rotation/revoke | Có | Có | Key test scope riêng, có approval | Không revoke customer key |
| Key/nonce store unavailable | Fake failure | Fault injection | Theo health/incident signals, chaos có phép | Không tắt Redis live tùy tiện |
| Gateway rewrite/header spoofing | Test adapter | Proxy thật | Spot-check được phê duyệt | Quan sát raw path tại hop đúng |
| Authn vs authz | Có | Có | Synthetic read/admin probe | 401 khác 403 |
| Tenant isolation | Có | Có | Chỉ test tenants giả | Không truy cập resource thật |
| p95/p99 và error rates | Benchmark | Load test | Passive canary observation | Có baseline và volume |
| Rollback security invariants | Test migration | Staging rollback | Xác minh sau rollback thật | Không revive key revoked |

**Không có một probe nào thay thế được tất cả các mức test.** CI chứng minh logic, staging chứng minh race/fault injection, production chứng minh behavior thực tế của cấu hình và network đang phục vụ khách hàng.

## 19. Checklist trực chiến post-deployment

### 19.1. Trước rollout

- [ ] Chốt build/image, security config, gateway routes và policy version có thể truy vết.
- [ ] Đã có golden vectors cho các HMAC profile/key versions đang được chấp nhận.
- [ ] Có synthetic key/tenant với quyền tối thiểu và read-only/no-op probe route thực sự yêu cầu HMAC.
- [ ] Không đưa real customer secret vào smoke script hoặc CI/CD log.
- [ ] Xác minh key store/nonce store, cluster topology, timestamp policy và clock sync health.
- [ ] Có baseline authn 401/403/503, latency p95/p99 và route-level traffic.
- [ ] Có người phụ trách freeze, rollback/forward-fix và kênh escalation.
- [ ] Định nghĩa security hard stops và SLO gates từ trước.

### 19.2. Sau canary

- [ ] Signed probe thành công **qua public ingress** trên bản canary, không bị gateway cache.
- [ ] Thiếu signature/wrong MAC/changed signed field bị từ chối, không handler.
- [ ] HMAC request mới vẫn kiểm tra timestamp và nonce; replay không qua trên test đa replica phù hợp.
- [ ] Key revoked/expired và profile bị cấm không được chấp nhận theo policy.
- [ ] Principal xác thực đúng nhưng thiếu quyền nhận 403, không side effect.
- [ ] Public path/query/header/body đã ký khớp với effective handler sau proxy rewrite.
- [ ] Không có route alias hoặc `permitAll` fallback vào protected business handler.
- [ ] Metrics/reasons không có secret/high-cardinality input tags; audit có correlation an toàn.
- [ ] So sánh baseline và canary sau khi loại trừ khác biệt traffic mix, cache warm-up và clock.
- [ ] Các region/replica quan trọng đều được kiểm tra, không chỉ một canary pod.
- [ ] Không có dấu hiệu fail-open khi key/nonce/policy store không thể xác minh.

### 19.3. Khi mở rộng và kết thúc rollout

- [ ] Tăng traffic theo nấc có thời gian quan sát phù hợp và đủ volume.
- [ ] Chạy lại positive/negative probes trên fleet đã mở rộng, kiểm tra batch client quan trọng.
- [ ] Bất kỳ hard stop nào → freeze rollout, containment, chỉ rollback nếu security-safe.
- [ ] Sau rollback/forward-fix phải chạy lại probes, không coi rollback thành công là đủ.
- [ ] Ghi nhận release decision, owner, evidence, dashboard và thời điểm UTC.
- [ ] Nếu khách hàng/đối tác bị ảnh hưởng, gửi incident notice qua kênh đã phê duyệt.
- [ ] Lưu kết quả, cập nhật runbook và tạo bài kiểm thử regression nếu phát hiện sai khác.

## 20. Kết luận

**Kiểm tra sau triển khai** đối với HMAC là kiểm tra **toàn bộ ranh giới bảo mật đang hoạt động trong môi trường thực**, không phải chỉ thấy pod `Ready` hay HTTP 200. Cần chứng minh request được ký đúng **được chấp nhận**, còn request thiếu/sai MAC, replay, key revoked và principal thiếu quyền **bị từ chối trước mọi side effect**.

Một quy trình đáng tin gồm **preflight → canary → signed synthetic smoke → negative security probes → quan sát fleet → go/no-go → xác minh sau rollback hoặc mở rộng**. Mọi bước phải tôn trọng canonical request, timestamp/nonce, key rotation/revocation, gateway trust và authorization. **Bảo mật là hard gate:** không được đổi lấy tỷ lệ 2xx hoặc p99 đẹp bằng cách bỏ HMAC, bỏ nonce, chấp nhận key cũ hay mở quyền trái chính sách.
