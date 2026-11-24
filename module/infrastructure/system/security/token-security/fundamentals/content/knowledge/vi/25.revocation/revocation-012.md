# Kiểm thử token trước và sau revoke

**Kiểm thử revocation không kết thúc ở việc gọi thành công endpoint `/revoke`.** Mục tiêu bảo mật cần chứng minh là: **một token được cấp hợp lệ và sử dụng được trước khi thu hồi phải bị từ chối sau khi thu hồi có hiệu lực theo chính sách**, đồng thời hệ thống **không vô tình từ chối những token không liên quan**. Giữa hành động revoke và kết quả thực tế tại API tồn tại nhiều lớp: trạng thái grant/token tại authorization server (AS), introspection, bộ nhớ đệm, độ trễ đồng bộ, cách resource server (RS) xác minh JWT hoặc opaque token và quy tắc phân quyền của từng endpoint.

Ví dụ, dịch vụ `orders-api` cho client `storefront-web` đọc đơn hàng bằng opaque access token `A1` có scope `orders:read`. Khi người dùng ngắt kết nối ứng dụng:

```text
Trước revoke
  AS token/grant status = ACTIVE
  Introspection(A1)    = {"active": true, ...}
  GET /orders with A1  = 200 (nếu quyền tài nguyên cũng cho phép)

Gọi revoke
  POST /revoke(A1)     = 200, request được xử lý theo RFC 7009
  AS status           = REVOKED (theo scope revoke được định nghĩa)

Sau revoke và sau giới hạn propagation đã công bố
  Introspection(A1)    = {"active": false}
  GET /orders with A1  = 401 invalid_token (hoặc denial hợp đồng)
  Token khác không liên quan vẫn hoạt động theo quyền riêng của nó
```

**Cần phân biệt:** `POST /revoke` có thể trả HTTP 200 ngay cả với một token **không tồn tại**; response này không chứng minh token đã active trước đó. Và một JWT access token **được RS kiểm tra hoàn toàn offline** có thể vẫn qua chữ ký và `exp` sau revoke, nếu RS không có cơ chế kiểm trạng thái mới. Vì vậy bộ kiểm thử phải đánh giá **điểm quan sát thực** thay vì chỉ assert một mã HTTP.

Bài thuộc chương **Revocation** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Module nghiên cứu mô hình tin cậy và vòng đời JWT/opaque token, access/refresh token trong xác thực, phân quyền và OAuth 2.0/OIDC; phát hành, kiểm tra claims, scope/audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại. Chủ đề trực tiếp ở đây là **kiểm thử token trước và sau revoke** một cách có thể lặp lại, phân biệt lỗi giao thức, lỗi cache/consistency và lỗi authorization.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế test có **baseline trước revoke**, **revoke được xác nhận**, **trạng thái introspection** và **kết quả API sau revoke**.
2. Xây dựng **test oracle** cho HTTP `200`, `401`, `403`, introspection `active=true/false` và lỗi AS.
3. Hiểu **RFC 7009** (revocation), **RFC 7662** (introspection) và **RFC 6750** (Bearer token usage), không coi mã `200` là bằng chứng cuối.
4. Phân loại token **access/refresh/ID**, **JWT/opaque**, **bearer/sender-constrained**, và xác định endpoint nào được kiểm.
5. Xác định rõ **phạm vi thu hồi**: một access token, refresh token, token family, authorization grant, user/session, client hoặc tenant.
6. Xây test **positive và negative**: token đã revoke bị từ chối, nhưng token khác đúng quyền vẫn được chấp nhận.
7. Kiểm đúng **issuer, audience, scope, token type, lifetime, subject/tenant và resource-level authorization**; không nhầm `403` thiếu quyền với revoke.
8. Đo **revocation propagation delay**, mô phỏng cache `active=true` cũ, replica lag, outage và races giữa revoke, refresh, API.
9. Dùng ví dụ **Java/JUnit/Spring Security**, HTTP fixtures và test doubles để triển khai test theo từng tầng.
10. Đưa revocation tests vào CI và vận hành bằng dữ liệu giả, không lộ token/secret, có runbook khi test thất bại.

## 2. Bốn điểm quan sát của một test revoke đáng tin cậy

Một integration test tốt không kiểm một điểm duy nhất:

| Điểm quan sát | Thực hiện | Câu hỏi được trả lời |
| --- | --- | --- |
| **A. Trước revoke** | Dùng token còn hiệu lực và đúng quyền gọi RS, introspect khi hỗ trợ | Token thật sự hoạt động trước khi thử? |
| **B. Yêu cầu revoke** | Client có quyền gọi revocation endpoint hoặc user/admin rút grant | AS đã xử lý yêu cầu theo chính sách? |
| **C. Trạng thái tại AS** | Introspect sau revoke hoặc đọc test-only state được cấp quyền | AS đang tính token/grant là active hay inactive? |
| **D. Thực thi tại RS** | Gọi API bằng **cùng token bytes** sau revoke, chờ đến bound đã định nếu có | RS còn chấp nhận token cũ không? |

Nên thêm **E. Isolation check**: token khác không thuộc phạm vi revoke vẫn có thể dùng đúng tài nguyên. Nếu test chỉ chứng minh API trả 401 sau revoke, có thể API đã bị tắt hoàn toàn, backend outage hoặc policy đổi khiến **mọi token** đều bị từ chối. Isolation test giúp phân biệt **thu hồi chính xác** với **sự cố toàn hệ thống**.

### 2.1. Ví dụ test sai: chỉ kiểm revocation endpoint

```java
// SAI: status 200 không chứng minh RS đã từ chối token.
assertEquals(200, revokeEndpoint.revoke(accessToken).status());
```

RFC 7009 chủ đích hạn chế lộ token existence và có thể trả 200 cả với token không hợp lệ. Test trên chỉ kiểm **HTTP transport/response**, không kiểm token thực tế được AS/RS coi là gì.

### 2.2. Ví dụ test tối thiểu đúng về ý nghĩa

```text
issueTokenForTest()         -> access_token A
requestRs(A)               -> 200 (baseline)
introspect(A).active       -> true (nếu profile hỗ trợ)
revoke(A)                  -> success per RFC 7009
waitUntilIntrospect(A)     -> active=false by deadline
waitUntilRsRequest(A)      -> deny by deadline
requestRs(unrelatedToken)  -> 200 (isolation check)
```

Lệnh `waitUntil...` **không đồng nghĩa sleep tùy tiện**. Nó cần deadline, timeout, backoff, tỷ lệ request nhỏ và thu thập timestamp để xác định khi nào trạng thái mới thực sự xuất hiện. Với hệ thống không hứa revoke gần tức thì, cần test theo **security contract** thay vì áp một SLA tùy ý.

## 3. Chuẩn bị test oracle: thế nào là “đúng”?

Để test có thể quyết định PASS/FAIL, phải xác định:

- **Token type:** access token hay refresh token? JWT hay opaque? Bearer hay ràng buộc sender?
- **Issuer:** AS nào cấp? Môi trường `test` hay `production`?
- **Recipient:** token được phép dùng ở RS nào (`aud`)? Có một hay nhiều audience?
- **Permission:** scope và tài nguyên cụ thể; 200/403 baseline được dự kiến theo chính sách nào?
- **Revocation scope:** token cụ thể, cả refresh family, toàn grant, consent, user session hay client registration?
- **Time boundary:** revoke lúc nào tính là committed? Độ trễ tối đa RS phải deny là bao lâu?
- **Cache/replication model:** introspection per request, positive cache TTL, JWT offline denylist, event propagation?
- **Failure contract:** AS timeout dẫn tới 503/401 hay fallback đã được an ninh phê duyệt? **Không tự allow** khi mất bằng chứng.
- **Unrelated controls:** token nào phải được giữ nguyên quyền khi revoke một token khác?

### 3.1. Bảng oracle minh họa

| Tình huống | Introspection | RS gọi endpoint đọc đúng audience/scope | Ý nghĩa |
| --- | --- | --- | --- |
| Access token active | `active=true` | `200` nếu resource policy cho phép | Baseline thành công |
| Access token đã revoke, state đã propagated | `active=false` | `401`/deny token theo RS contract | Kỳ vọng revocation |
| Access token hết hạn | `active=false` hoặc time-check deny | `401` | **Không chứng minh revoke** |
| Token hợp lệ nhưng thiếu scope | Có thể `active=true` | `403` | Authorization denial, không phải token invalid |
| Token hợp lệ nhưng sai audience | Có thể `active=true` tại AS | `401`/deny token | Không chứng minh token đã revoke |
| Token active nhưng sai tenant/resource | `active=true` | `403` | Resource policy denial |
| Introspection endpoint trả 401 | Không có authenticated introspection result | **Deny**, có thể 503 theo contract | RS credential/config error |
| AS không phản hồi | Không có dữ liệu active đáng tin | **Deny/fail closed** hoặc fallback đã đánh giá | Outage, không phải xác nhận revoked |
| JWT offline còn `exp` nhưng grant revoked | AS có thể trả inactive | RS **có thể vẫn 200** nếu không kiểm revoke | Phơi bày architecture gap |

**Chốt:** `401` sau revoke là quan sát cần có, nhưng **tự nó không đủ**. Phải có baseline và test nguyên nhân. Tương tự, `active=false` không tự chứng minh do user revoke: token có thể sai, hết hạn, không tồn tại hoặc caller không được xem trạng thái.

## 4. Đường đi của test qua AS và RS

```mermaid
sequenceDiagram
    participant T as Test runner
    participant AS as Authorization Server
    participant S as Token / Grant Store
    participant RS as Resource Server
    T->>AS: Test-only grant/token issuance
    AS->>S: Persist ACTIVE token/grant
    AS-->>T: Opaque access token A (không log)
    T->>RS: GET /orders + Bearer A
    RS->>AS: POST /introspect(A) [khi RS dùng introspection]
    AS-->>RS: active=true, aud/scope/exp
    RS-->>T: 200 (baseline)
    T->>AS: POST /revoke(A) + authenticated client
    AS->>S: Mark REVOKED / grant invalidated
    S-->>AS: Commit
    AS-->>T: 200 (không tiết lộ token tồn tại)
    T->>AS: POST /introspect(A)
    AS-->>T: active=false (theo token state/permissions)
    T->>RS: GET /orders + same Bearer A
    RS->>AS: POST /introspect(A) hoặc kiểm cache/revocation state
    AS-->>RS: active=false
    RS-->>T: 401 / deny
```

Trong test thực tế, **test runner không luôn được quyền introspect**; một hệ thống giới hạn introspection chỉ cho RS. Khi đó có thể:

1. Dùng một **test-only protected resource/introspection client** đã được AS ủy quyền trong môi trường cô lập; hoặc
2. Quan sát qua RS và một **test control plane** có quyền xem grant/token state mà không truy xuất raw secret.

**Không mở public introspection endpoint chỉ vì test dễ làm hơn** và không dùng production client credential để lấy metadata thật.

## 5. Hợp đồng RFC 7009: revoke request và idempotency

Client có quyền gửi request revocation qua TLS:

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_CLIENT_AUTH_TEST_ONLY
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_TEST_ONLY&token_type_hint=access_token
```

Ở đây các chuỗi là **placeholder**, không phải credential thật. Form body phải dùng `application/x-www-form-urlencoded`; `token` bắt buộc và `token_type_hint` tùy chọn, chỉ là **gợi ý**. Client phải authenticate khi profile yêu cầu và AS kiểm quyền/affiliation đối với token.

### 5.1. Không suy từ HTTP 200 rằng revoke đã tác động token

RFC 7009 cho phép trả **HTTP 200 khi token không tồn tại/đã không hợp lệ**, nhằm tránh tạo token existence oracle. Vì vậy test cần phân biệt:

```text
POST /revoke(token_known_active)  -> 200
POST /revoke(token_already_revoked) -> 200
POST /revoke(token_unknown)      -> 200

Three HTTP responses may look identical.
Only separate state + RS enforcement tests prove the first case.
```

Nếu AS cần thời gian xử lý revoke hoặc endpoint lỗi (ví dụ 503), test phải xử lý theo hợp đồng của AS và RFC; **không tự quy lỗi server thành thành công**.

### 5.2. Vì sao cần test gọi revoke lần hai?

**Idempotent behavior** là đặc điểm quan trọng: gọi revoke lặp với cùng token không nên làm sống lại token, cấp quyền mới hoặc tiết lộ thông tin phân biệt token tồn tại.

```text
revoke(A) -> 200
revoke(A) -> 200
introspect(A) -> active=false
RS(A) -> deny
```

Nếu client có quyền nhưng token vốn không thuộc nó, AS có thể che existence hoặc trả lỗi quyền theo policy/profile. Test phải phân biệt **authenticated caller** với **unauthenticated caller**; không bắt AS trả 200 cho một request thiếu/sai client authentication.

### 5.3. Revocation scope cần biết trước

Theo RFC 7009 và provider policy:

- Revoke **refresh token** có thể kéo theo access tokens cùng authorization grant; RFC 7009 khuyến nghị AS hỗ trợ access-token revocation thì nên xử lý các access token cùng grant theo hướng đó.
- Revoke một **access token** có thể ảnh hưởng refresh token/authorization grant tùy policy.
- Revoke **một grant/session/client/tenant** là logic rộng hơn một token riêng lẻ.
- Token đã hết hạn hoặc unknown có thể cùng response 200 nhưng không có active-state transition mới.

**Không viết một test cứng rằng “revoke access A luôn làm refresh R inactive” nếu AS không cam kết điều đó.** Hãy cấu hình expectation theo phạm vi revoke được công bố.

## 6. Hợp đồng RFC 7662: trước và sau revoke

Resource server có thể dùng RFC 7662 introspection để hỏi AS trạng thái token:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_RS_INTROSPECTION_AUTH_TEST_ONLY
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=ACCESS_TOKEN_TEST_ONLY&token_type_hint=access_token
```

### 6.1. Trước revoke

```json
{
  "active": true,
  "token_type": "Bearer",
  "client_id": "storefront-web",
  "sub": "test-user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iss": "https://id.example.test",
  "exp": 1800000600,
  "iat": 1800000000
}
```

Response là **fixture**; thời gian chỉ minh họa và sẽ không được dùng như một token còn hiệu lực vào mọi ngày. Theo RFC 7662, ngoài `active`, các fields khác **tùy chọn**; việc RS cần `aud`/`iss`/scope bắt buộc phải được giải quyết bằng AS–RS contract đáng tin.

### 6.2. Sau revoke

```json
{
  "active": false
}
```

Response `active=false` được AS dùng khi token không active hoặc AS không cung cấp thông tin cho caller. **Không trả thêm subject, scope, nguyên nhân revoke hoặc token existence nếu không có chính sách/chuẩn phù hợp**, bởi điều đó có thể tiết lộ metadata nhạy cảm.

### 6.3. Những khẳng định test quan trọng

- `active` phải là **Boolean**, không được chấp nhận `"true"` (string) hoặc chỉ kiểm HTTP `200`.
- Nếu response thiếu `active` hoặc JSON sai, RS **fail closed**.
- Nếu introspection trả HTTP `401/403` do RS credential sai, đó là **lỗi xác thực caller**, không phải cách chuẩn để báo token inactive.
- Nếu AS trả `active=true` nhưng `aud` sai, thiếu scope hoặc token thuộc loại không được RS hỗ trợ, RS **vẫn từ chối**.
- Với token bị revoke, test **không nên yêu cầu một reason field** (ví dụ `revocation_reason`) trong response public; lý do có thể chỉ có ở audit nội bộ.

### 6.4. Một oracle không được nhầm 401 với 403

RS dùng Bearer authentication (RFC 6750) thường phân biệt:

| RS response | Ví dụ | Kỳ vọng test |
| --- | --- | --- |
| **`401 Unauthorized` / `invalid_token`** | Missing, expired, revoked, invalid issuer/audience/type | Token không hợp lệ để xác thực API |
| **`403 Forbidden` / `insufficient_scope`** | Token active nhưng thiếu `orders:write` | Authorization denied, không chứng minh revoke |
| **`403` theo policy tài nguyên** | Token active, user ở tenant A cố đọc order tenant B | Resource denial, không phải revoke |
| **`503`/5xx bảo vệ** | AS introspection outage, RS không thể xác minh active | **Không allow**; failure diagnosis tùy contract |

Không bắt buộc mọi framework map network error giống nhau; nhưng **không có đường error nào được vô tình nâng thành allow**.

## 7. Trước revoke: baseline phải hợp lệ thật

Một bài test dễ cho kết quả “PASS giả” nếu token chưa bao giờ hoạt động. Ví dụ test nhận 401 sau revoke, nhưng token đã hết hạn từ trước.

### 7.1. Thiết lập token test hợp lệ

- AS test được cấu hình đúng issuer và client registration.
- Client/subject được cấp access token có `aud=orders-api` và `scope=orders:read`.
- `exp` đủ xa để thực hiện cả trước/sau trong cửa sổ test; không dùng token sống 1 giây với runner chậm.
- RS `GET /v1/orders/fixture-42` có tài nguyên **thuộc đúng user/tenant** và policy cho phép.
- Token được lưu chỉ trong bộ nhớ fixture, không in stdout, curl verbose, CI logs.
- Hệ thống đồng hồ và fixtures không dùng timestamp cứng đã qua hạn.

### 7.2. Các assertion trước revoke

```text
Before:
  grant.status == ACTIVE
  token.exp > test_now + safety_margin
  introspection.active == true  (if supported by contract)
  introspection.aud includes orders-api
  introspection.scope includes orders:read
  GET fixture using token == 200
  response data belongs to intended test tenant
```

**Nếu baseline thất bại, test phải dừng ở trạng thái SETUP_FAILED**, không tiếp tục revoke rồi nhận 401 và gọi đó là thành công. Ghi rõ lý do setup: thiếu scope, wrong aud, endpoint lỗi hay token hết hạn.

### 7.3. Không lấy 200 từ endpoint public làm baseline

Nếu `GET /health` là public, request có hay không có token đều trả 200. Test trên endpoint này **không chứng minh token đã được xác minh**. Chọn endpoint bắt buộc authentication và có authorization policy kiểm được, kèm request **không token** phải 401.

### 7.4. Không dùng expired test credentials

Những JWT/opaque strings được trình bày bằng mẫu tĩnh trong tài liệu chỉ để minh họa cú pháp. Hệ thống test thật phải **phát token mới trong isolated test environment**, dùng identity/secret giả do fixture quản lý.

## 8. Sau revoke: tiêu chí “token không còn được dùng”

Các bước kiểm chứng:

1. **Revoke đúng token/grant:** gửi token thực đã dùng ở baseline, với authenticated caller có thẩm quyền.
2. **Ghi mốc:** xác định thời điểm AS đã commit revoke nếu test harness có nguồn tin cậy; không chỉ dùng mốc client nhận HTTP 200.
3. **Quan sát AS:** introspection chuyển sang `active=false`, theo latency/security contract.
4. **Quan sát RS:** cùng token được gửi vào **cùng endpoint và cùng tài nguyên** như baseline, RS từ chối.
5. **Kiểm unrelated token:** token `B` không trong revoke scope vẫn được RS chấp nhận theo đúng quyền riêng.
6. **Kiểm cấp mới:** nếu revoke grant/refresh family, refresh token không thể xin access token mới từ grant đã thu hồi.
7. **Kiểm audit:** có sự kiện revoke và denial lý do an toàn, không in raw token.

### 8.1. Test state transition, không chỉ test trạng thái cuối

```text
Token A:
    known-active BEFORE
    revoke(A) accepted
    inactive AFTER

Token B:
    known-active BEFORE
    outside revocation scope
    active AFTER
```

Một script chỉ gửi token rác tới introspection rồi nhận false **không kiểm revocation**; nó kiểm lookup của unknown token.

### 8.2. Test sự kiện revoke không được khôi phục

Gọi revoke hai lần, restart RS, clear cache, thậm chí failover AS vùng khác, rồi kiểm token `A` **không tự trở lại active**. Với grant terminally revoked, một replica cũ không được hồi sinh nó sau đồng bộ/restart trái policy.

### 8.3. Kỳ vọng “ngay lập tức” cần định nghĩa được

Ví dụ:

```text
Security objective:
  token A must stop authorizing new API requests
  within 10 seconds after authoritative revoke commit,
  across all production RS regions.
```

Số **10 giây chỉ là ví dụ**, không phải giới hạn RFC bắt buộc. Test phải đo thực tế và so với **SLA do hệ thống lựa chọn**, có tolerance cho đồng hồ/network/load trong thiết kế test.

## 9. JWT tự kiểm tra và opaque introspection: test khác nhau

| Mô hình RS | Trước revoke | Sau revoke | Test cần chứng minh |
| --- | --- | --- | --- |
| Opaque + introspection mỗi request | AS `active=true`, RS allow | AS `active=false`, RS deny | RS thực sự dùng trạng thái mới |
| Opaque + cache positive | RS allow từ response hoặc cache | Có thể còn allow tới hết TTL/invalidation | Window stale nằm trong security objective |
| JWT chỉ verify offline | Chữ ký/`exp`/`aud`/scope hợp lệ | **Vẫn có thể allow** sau AS revoke | Phát hiện gap giữa revoke và RS enforce |
| JWT + AS introspection | JWT hợp lệ, AS active | AS inactive, RS deny theo cache/latency | Introspection có đọc trạng thái revoke của JWT |
| JWT + local denylist/grant version | JWT hợp lệ, grant active | `jti`/grant bị deny ở RS | Distribution/version/staleness đúng |
| Sender-constrained token | Token + proof/cert đúng được allow | Revoke phải deny kể cả proof đúng | Revocation độc lập proof-of-possession |

### 9.1. Revoking JWT không làm hỏng chữ ký

Ví dụ JWT access token còn `exp` 15 phút. AS nhận revoke lúc 11:02. Đến 11:03, RS validate offline và vẫn thấy signature đúng. Nếu không có denylist, grant-status lookup, introspection hoặc expiry sát:

```text
JWT cryptographic checks: PASS
Authorization grant now REVOKED: UNKNOWN TO RS
RS result: may still allow
```

**Không nên viết test đòi RS offline từ chối ngay nếu thiết kế chưa hứa điều đó.** Nhưng nếu yêu cầu nghiệp vụ là revoke trong 10 giây, kết quả allow phải được coi là **design/implementation gap**, chứ không chấp nhận vì “JWT đúng chữ ký”.

### 9.2. Khi nào dùng short-lived token thay check trạng thái?

Token TTL ngắn hạn chế cửa sổ replay nhưng không bảo đảm revocation tức thì. Ví dụ access JWT sống 5 phút, revoke tại phút đầu vẫn có thể dùng thêm gần 4 phút. **SLA revocation cần phù hợp TTL và cache** hoặc phải thêm stateful enforcement.

### 9.3. Không nhầm refresh token với access token

Refresh token được dùng ở **token endpoint** để xin access token mới, không được chấp nhận tại RS như access token. Test cần gửi nhầm refresh token tới API và kỳ vọng deny, kể cả nếu introspection API nội bộ còn coi refresh token active.

### 9.4. OIDC ID token và logout

OIDC ID token dùng để RP xác minh authentication result, không là bearer access token cho API. Logout RP/OP không tự đồng nghĩa revoke tất cả access JWT đã phát. Khi test “logout thì hết quyền”, cần **chỉ rõ** hệ thống có revoke grant/refresh/access hay chỉ xóa session cookie.

## 10. Scope revoke: một token hay cả family/grant?

Một authorization grant có thể phát nhiều access/refresh token:

```text
Grant G (subject=user-42, client=storefront-web)
  |
  +-- Refresh R1 (rotated, no longer usable)
  +-- Refresh R2 (current)
  +-- Access  A1 (orders-api, orders:read)
  +-- Access  A2 (profile-api, profile:read)

Unrelated Grant H (same user, different client)
  |
  +-- Access  B1 (orders-api, orders:read)
```

### 10.1. Test từng phạm vi riêng

| Revoke action | Những điều cần kiểm | Điều không được đoán |
| --- | --- | --- |
| Revoke `A1` riêng | `A1` deny; R2/A2 tùy policy | Không tự giả định cả grant bị revoke |
| Revoke `R2` | Refresh bằng R2 không cấp mới; access tokens theo cascade policy | Không mặc định A1/A2 còn hoặc mất giống mọi AS |
| Revoke **grant G** | Mọi issuance dựa trên G bị chặn; các token G deny theo contract | Không đụng grant H nếu ngoài scope |
| Revoke **refresh family** do reuse | Các thành viên family và access liên quan theo policy | Không suy mọi family của user đều revoke |
| Disable client | Xin token mới bị chặn; existing tokens theo policy | Disable không tự xóa chữ ký JWT đã phát |
| User “logout” | RP/OP session và token/grant actions theo design | Không tự gắn nghĩa all-device revoke |
| Password reset/account lock | Phạm vi token/session chịu ảnh hưởng theo security policy | Không mặc định mọi token type đều hết hiệu lực ngay |

### 10.2. Isolation không chỉ bảo vệ availability

Nếu revoke `G` vô tình revoke cả `H`, người dùng/ứng dụng hợp lệ khác có thể mất khả năng làm việc. Một token family rộng hơn dự kiến còn gây logout hàng loạt. **Test unaffected grants** là kiểm correctness, least privilege và containment, không chỉ kiểm UX.

### 10.3. Không “hồi sinh” refresh token cũ

Khi một refresh token đã rotate hoặc revoke, nó không được trở thành active lần nữa chỉ vì grant được reauthorized. Một authorization mới nên phát token family mới. Test:

```text
R1 rotated -> R2
R1 reused  -> detected according to AS policy
R1 remains unusable
R2/family status follows documented reuse response
```

Trong môi trường có network retry/race, AS cần policy rõ để tránh false positive và replay, không chỉ dựa vào một boolean ở client.

## 11. Những test case âm tính phải chạy trước khi đo revoke

Để phân biệt revoke với policy/format failures, nên test có đối chứng:

| Trường hợp | Tình trạng token | Kết quả dự kiến |
| --- | --- | --- |
| Không gửi Bearer | Không có token | 401 |
| Chuỗi token giả | Không được AS cấp | 401 |
| Token đã hết hạn | `exp` trong quá khứ | 401 |
| Token đúng chữ ký, sai issuer | Không thuộc AS tin cậy | 401 |
| Token đúng issuer, sai audience | Dành RS khác | 401 hoặc deny token |
| Token active, thiếu scope | Không đủ quyền endpoint | 403 |
| Token active, sai tenant/ownership | Resource policy deny | 403 |
| ID token vào API | Token sai mục đích | 401/deny |
| Refresh token vào API | Token sai loại | 401/deny |
| Token có malformed signature/JWT | Không thể xác minh | 401 |
| DPoP/mTLS-bound token thiếu sender proof | Proof sai/thiếu | 401/deny theo profile |

Nếu các negative tests này thất bại trước revoke, RS đã có **lỗ hổng validation/authorization** độc lập với revocation, cần sửa trước khi coi kết quả revoke là đáng tin.

## 12. Thiết kế test environment và fixtures

Không chạy các bài revocation test phá hủy dữ liệu trên token/người dùng production. Cần một môi trường **cô lập, có issuer/keys/test clients riêng**, cho phép phát hành và thu hồi token dùng cho test một cách có kiểm soát.

### 12.1. Những thành phần tối thiểu

```text
Test runner (JUnit/CI)
  |
  +-- AS test issuer: https://id.test.example
  |     /oauth2/token
  |     /oauth2/revoke
  |     /oauth2/introspect
  |     test-only provisioning / grant fixture
  |
  +-- RS test audience: orders-api
  |     GET /v1/orders/fixture-42   (requires orders:read)
  |     POST /v1/orders/fixture-42  (requires orders:write)
  |
  +-- Test database/clock/secret manager
  +-- Controlled cache, replica/region simulator when needed
```

`/oauth2/token`, `/oauth2/revoke` và `/oauth2/introspect` là các endpoint OAuth có thể có đường dẫn khác tùy AS. `test-only provisioning` là abstraction phục vụ môi trường test, **không phải endpoint chuẩn OAuth** và **không được mở công khai trong production**.

### 12.2. Bộ fixtures đề nghị

| Fixture | Đặc điểm | Mục đích |
| --- | --- | --- |
| `A1` | Opaque access token, active, `aud=orders-api`, `orders:read` | Test pre/post revoke trực tiếp |
| `A2` | Access token active, cùng grant hoặc khác grant theo testcase | Kiểm cascade revocation |
| `B1` | Token active thuộc **unrelated grant/client** | Kiểm không revoke quá rộng |
| `R1` | Refresh token đang active | Test refresh token revoke |
| `R2` | Refresh token sau rotation từ R1 | Kiểm family/reuse policy |
| `J1` | JWT access token có `jti`, expiry trong tương lai | Test offline vs revocation-aware RS |
| `E1` | Token đã `exp` | Test expiry không bị nhầm revoke |
| `W1` | Token đúng issuer nhưng sai audience | Test token validation |
| `S1` | Sender-constrained token | Test proof và revoke độc lập |

**Mỗi fixture phải có giá trị sinh ngẫu nhiên/được AS phát mới**, không dùng literal `A1` làm bearer credential. Có thể đặt tên test reference nội bộ nhưng không ghi raw token vào báo cáo CI.

### 12.3. Sơ đồ test metadata riêng token material

```java
// Các record mô hình hóa dữ liệu test, không phải OAuth library API.
record TestToken(
    String privateTokenValue,
    String safeFixtureLabel,
    String expectedAudience,
    String expectedScope,
    String grantReference
) {}

record TestCaseContext(
    String issuer,
    String resourceServer,
    String scope,
    String revocationScope,
    java.time.Duration maxPropagation
) {}
```

`privateTokenValue` không được in bởi `toString()` sinh tự động của record trong Java nếu đối tượng bị log! **Ví dụ này nêu rủi ro**, vì Java record tạo `toString()` chứa mọi trường. Trong code thật nên dùng một secret wrapper có `toString()` được redacted, không ghi các object mang token vào logs, hoặc tách token bytes khỏi report metadata hoàn toàn.

### 12.4. Đồng hồ và thời hạn

Để test expiry và revoke riêng:

- Token dành cho revoke baseline nên có expiry đủ dài để không hết hạn ngay giữa test.
- Test expiry sử dụng **fake clock/test issuer** phù hợp, không giả lập bằng cách sửa `exp` trong JWT đã ký.
- Đo khoảng thời gian bằng **monotonic clock**, chẳng hạn `System.nanoTime()`, không dùng wall clock để tính duration nếu hệ thống có NTP adjustments.
- Sự kiện audit trên nhiều máy dùng server timestamps có đồng bộ/offset được công bố và trace/request ID, không đo latency bằng cách trừ hai timestamp chưa được hiệu chỉnh.

## 13. Kịch bản test E2E chuẩn: cấp → dùng → revoke → dùng lại

Đây là kịch bản nên được ưu tiên cho opaque access token hoặc một access token được AS hỗ trợ revocation-aware introspection.

### 13.1. Arrange: cấp và xác minh baseline

1. Tạo user/client registration test theo policy.
2. Phát `A1` với `aud=orders-api`, scope `orders:read`, expiry còn xa.
3. Gọi `GET /v1/orders/fixture-42` **không token** → 401.
4. Gọi cùng endpoint bằng `A1` → 200, kiểm dữ liệu thuộc đúng test tenant.
5. Introspect `A1` bằng test RS/introspector có quyền → `active=true`.
6. Nếu có `A2`/`B1`, xác minh chúng active và đúng quyền trước revoke.

### 13.2. Act: revoke chính xác

7. Gọi `POST /revoke` bằng client có thẩm quyền với **chính xác raw bytes của `A1`** đã dùng baseline.
8. Kiểm mã phản hồi theo RFC 7009; nếu 200, không kết luận ngay RS đã từ chối.
9. Nếu test harness biết thời điểm AS commit revoke, ghi `revokeCommittedAt` **bằng metadata an toàn**.

### 13.3. Assert: AS và RS thay đổi

10. Poll introspection cho `A1` với bounded wait đến khi `active=false`.
11. Poll `GET /v1/orders/fixture-42` bằng `A1` đến khi bị từ chối đúng kiểu invalid token.
12. Kiểm `A1` không được dùng ở resource khác; **đừng cho phép 403 thiếu scope được coi là bằng chứng revoke** nếu test dự kiến 401.
13. Gọi lại API bằng `B1` (unrelated grant) → vẫn 200.
14. Gọi revoke `A1` lần nữa → xử lý idempotent; introspection vẫn false/RS deny.
15. Kiểm logs/audit không có raw `A1`, refresh token hay client secret.

### 13.4. Test status nên có nhiều nhãn hơn PASS/FAIL

```text
SETUP_FAILED:
  Baseline token was never valid, or test endpoint public.

REVOKE_CALL_FAILED:
  Revocation request was not accepted under expected contract.

AS_STATE_FAILED:
  Token remains introspectable as active past AS deadline.

RS_ENFORCEMENT_FAILED:
  AS inactive, but RS still accepts token beyond propagation SLA.

ISOLATION_FAILED:
  Unrelated grant/token unexpectedly lost authorization.

PASS:
  Before valid; revoke accepted; AS inactive;
  RS denied within SLA; unrelated controls unaffected.
```

Những nhãn này là **gợi ý cho test reporting**, không phải OAuth error codes. Chúng giúp kỹ sư phân vùng lỗi thay vì chỉ thấy “expected 401, got 200”.

## 14. HTTP mẫu: kiểm cùng token trước và sau revoke

Các mẫu dưới đây minh họa cách gọi endpoint trong môi trường **test cô lập**. Không copy credential sản xuất vào terminal/CI. Tránh `curl -v`, shell history lộ secret, process list, APM HTTP dumps; cân nhắc dùng test framework giữ token trong process memory thay vì truyền qua command line.

### 14.1. API trước revoke

```http
GET /v1/orders/fixture-42 HTTP/1.1
Host: orders.test.example
Authorization: Bearer ACCESS_TOKEN_A1_TEST_ONLY
Accept: application/json
```

Kết quả theo đúng RS fixture:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"fixture-42","owner":"test-user-42"}
```

### 14.2. Revoke A1

```http
POST /oauth2/revoke HTTP/1.1
Host: id.test.example
Authorization: Basic CLIENT_AUTH_TEST_ONLY
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_A1_TEST_ONLY&token_type_hint=access_token
```

Kết quả thường:

```http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Length: 0
```

### 14.3. Introspection sau revoke

```http
POST /oauth2/introspect HTTP/1.1
Host: id.test.example
Authorization: Basic RS_INTROSPECTION_AUTH_TEST_ONLY
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=ACCESS_TOKEN_A1_TEST_ONLY&token_type_hint=access_token
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

### 14.4. API sau revoke

```http
GET /v1/orders/fixture-42 HTTP/1.1
Host: orders.test.example
Authorization: Bearer ACCESS_TOKEN_A1_TEST_ONLY
Accept: application/json
```

Một kết quả RS theo RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Đừng khẳng định một body error JSON hoặc wording `WWW-Authenticate` cụ thể là universal cho mọi API/framework; **test contract phải được xác định theo RS**.

### 14.5. Không trộn raw token vào kết quả test

Chỉ nên xuất báo cáo:

```json
{
  "test_name": "revoke_opaque_access_token",
  "fixture": "A1",
  "baseline_rs_status": 200,
  "revocation_http_status": 200,
  "after_introspection_active": false,
  "after_rs_status": 401,
  "propagation_within_bound": true,
  "unrelated_token_status": 200
}
```

**Không đưa `access_token`, `refresh_token`, `Authorization` header hoặc raw request form chứa token vào JSON report.**

## 15. Java/JUnit: test oracle cho revocation flow

Để tránh phụ thuộc vào một AS cụ thể, tách test harness thành các phương thức domain. Phần dưới là **JUnit 5 test pseudocode**; `OAuthTestHarness` và các record response là abstraction do dự án/test fixtures triển khai, **không phải class có sẵn của Spring**.

### 15.1. Test hành vi trước và sau

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class AccessTokenRevocationIT {
    private final OAuthTestHarness harness = OAuthTestHarness.forSandbox();

    @Test
    void revokedAccessTokenBecomesUnusableAtResourceServer() {
        var a1 = harness.issueAccessToken(
            "storefront-web", "test-user-42",
            "orders-api", "orders:read");
        var b1 = harness.issueUnrelatedAccessToken(
            "other-web-client", "test-user-42",
            "orders-api", "orders:read");

        // Baseline trước revoke phải hợp lệ thật.
        assertEquals(401, harness.getOrdersWithoutToken().status());
        assertTrue(harness.introspect(a1).active());
        assertEquals(200, harness.getOrders(a1).status());
        assertEquals(200, harness.getOrders(b1).status());

        // Revoke chỉ token A1 theo policy của test environment.
        assertEquals(200, harness.revokeAccessToken(a1).status());

        harness.awaitIntrospectionInactive(
            a1, java.time.Duration.ofSeconds(10));
        harness.awaitResourceServerDenies(
            a1, java.time.Duration.ofSeconds(10));

        assertFalse(harness.introspect(a1).active());
        assertEquals(401, harness.getOrders(a1).status());

        // Không phá quyền của token thuộc grant khác.
        assertEquals(200, harness.getOrders(b1).status());

        // Gọi revoke lại không hồi sinh token.
        assertEquals(200, harness.revokeAccessToken(a1).status());
        assertEquals(401, harness.getOrders(a1).status());
    }
}
```

Trong đoạn mã này, `Duration.ofSeconds(10)` là **ví dụ deadline theo test policy**, không phải SLA tiêu chuẩn OAuth. Nếu AS revoke A1 dẫn tới revoke cả grant theo hợp đồng, fixture `b1` phải thật sự nằm ngoài phạm vi đó. `await...` phải có timeout/bounded polling, phân loại errors, không flood AS.

### 15.2. Chỉ assert 401 chưa đủ

Mã sau **không phải** bài test revocation đúng:

```java
@Test
void falsePositiveTest() {
    var token = "UNKNOWN_TOKEN_STRING";
    harness.revokeAccessToken(token);
    assertEquals(401, harness.getOrders(token).status());
}
```

Nó có thể PASS vì token chưa từng hợp lệ. Vì vậy **bắt buộc có baseline 200 hoặc bằng chứng valid trước revoke** và cùng token/endpoint được kiểm sau revoke.

### 15.3. Test tách chức năng revocation và authorization

```java
@Test
void activeButInsufficientScopeIsNotRevocation() {
    var readOnly = harness.issueAccessToken(
        "storefront-web", "test-user-42",
        "orders-api", "orders:read");

    assertTrue(harness.introspect(readOnly).active());
    assertEquals(200, harness.getOrders(readOnly).status());
    assertEquals(403, harness.deleteOrder(readOnly).status());

    // 403 này đến từ thiếu quyền write/delete,
    // không chứng minh token đã bị revoke.
}
```

### 15.4. Test unknown token và idempotency

```java
@Test
void revokingUnknownOrAlreadyRevokedTokenDoesNotLeakExistence() {
    var valid = harness.issueAccessToken(
        "storefront-web", "test-user-42",
        "orders-api", "orders:read");

    assertEquals(200, harness.revokeAccessToken(valid).status());
    assertEquals(200, harness.revokeAccessToken(valid).status());

    var unknown = harness.randomUnknownToken();
    assertEquals(200, harness.revokeUnknownTokenAsAuthorizedClient(
        unknown).status());
    assertFalse(harness.introspect(valid).active());
}
```

Đây là kỳ vọng theo **hợp đồng RFC 7009 cho một request authenticated hợp lệ**. Không áp test này cho client hoàn toàn không được xác thực/được phép gọi endpoint.

### 15.5. Không dùng một token cố định giữa các lần chạy

JUnit tests chạy song song hoặc lặp lại có thể trùng token/subject/client và gây **shared-state flakes**. Mỗi test cần grant/fixture riêng, isolation hoặc cleanup thích hợp, unique test account/context và không lẫn `A1` từ lần chạy hôm trước.

## 16. Java: bounded polling và đo độ trễ

Để kiểm revoke propagation, test phải **chờ có hạn**. Không dùng `Thread.sleep(30000)` rồi kết luận “30 giây chắc đủ”, vì tốc độ AS/RS khác nhau và test không biết thực sự token bị deny lúc nào.

### 16.1. Hàm chờ generic dùng monotonic clock

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

public final class TestPolling {
    private TestPolling() {}

    public static Duration awaitUntil(
        BooleanSupplier condition,
        Duration maxWait,
        Duration interval
    ) throws InterruptedException {
        if (maxWait.isNegative() || maxWait.isZero()
            || interval.isNegative() || interval.isZero()) {
            throw new IllegalArgumentException("Durations must be positive");
        }

        long started = System.nanoTime();
        long deadline = started + maxWait.toNanos();

        while (true) {
            if (condition.getAsBoolean()) {
                return Duration.ofNanos(System.nanoTime() - started);
            }
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0L) {
                throw new AssertionError("Revocation propagation deadline exceeded");
            }
            long nap = Math.min(remaining, interval.toNanos());
            TimeUnit.NANOSECONDS.sleep(nap);
        }
    }
}
```

Đây là helper test đơn giản; trong test suite lớn có thể dùng **Awaitility** hoặc test scheduler/fake clock. Cần xử lý exception từ network probe, jitter/backoff để tránh herd và giới hạn số request. Không dùng polling helper này trong luồng business request production.

### 16.2. Đo hai giai đoạn khác nhau

```text
revokeCommit -> AS introspection active=false
revokeCommit -> RS stops accepting token
```

AS state có thể chuyển inactive trước khi RS positive cache hết hạn. Ghi cả hai khoảng thời gian thay vì chỉ báo “revoke took 8 seconds”.

Ví dụ dữ liệu giả:

| Mốc | Sự kiện |
| --- | --- |
| T0 | AS revoke committed |
| T0 + 0,2 s | AS introspection trả inactive |
| T0 + 6 s | RS X lần đầu deny |
| T0 + 9 s | RS Y lần đầu deny |

**Đó chỉ là dữ liệu minh họa, không phải số đo thực tế.** Nếu SLA là 5 giây trên **mọi RS**, test này FAIL tại cả X/Y hoặc ít nhất tại vùng còn accept quá hạn. Không cộng trừ timestamps từ máy chưa đồng bộ mà xem như đo độ trễ chính xác.

### 16.3. Tránh đo nhầm bằng revoked token đã expired

Nếu `exp` xảy ra giữa lúc chờ, API có thể deny vì **expiry**, không phải revoke. Test nên bảo đảm thời gian hết hạn nằm ngoài cửa sổ đo hoặc ghi nhận riêng token expiration. Nếu không, kết quả nên là **INCONCLUSIVE**.

## 17. Test Spring Security Resource Server

Một Resource Server dựa vào **opaque introspection** thường ánh xạ `active=false` thành token không hợp lệ. Tầng test controller/Spring có thể dùng `MockMvc` và mock introspector để kiểm enforcement; test riêng với AS thật kiểm giao thức.

### 17.1. Cấu hình minh họa

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.test.example/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: PLACEHOLDER_FROM_TEST_SECRET_MANAGER
```

Secret/URI này là **fixture**. Không hardcode production secret. Trong triển khai thật, RS còn phải có trusted issuer/audience/profile validation, scope, tenant và resource-level policies. **Chỉ `active=true` không đủ.**

### 17.2. Filter chain scope enforcement

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.opaqueToken(
                Customizer.withDefaults()
            ));

        return http.build();
    }
}
```

Đoạn này minh họa **scope filter**, chưa có toàn bộ security config; nếu là stateless REST API, cần xác định CSRF/session model và audience/token-type validation riêng. Đừng vô hiệu CSRF của hệ thống có cookie session chỉ vì đang viết token test.

### 17.3. Mock introspector trả active rồi inactive

Ví dụ **mã kiểm thử minh họa** cho Spring Boot/Spring Framework phiên bản hỗ trợ `@MockitoBean`. Với phiên bản cũ, cách đăng ký mock test bean có thể khác. Endpoint `/v1/orders/fixture-42` phải có trong test fixture và trả 200 khi chính sách cho phép.

```java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerRevocationWebTest {
    @Autowired MockMvc mvc;
    @MockitoBean OpaqueTokenIntrospector introspector;

    @Test
    void sameTokenAllowedThenDeniedWhenIntrospectionBecomesInactive()
        throws Exception {
        String testToken = "FAKE_OPAQUE_A1_FOR_MOCK_ONLY";
        var attrs = Map.<String, Object>of(
            "sub", "test-user-42",
            "iss", "https://id.test.example",
            "aud", List.of("orders-api"),
            "scope", "orders:read"
        );
        var principal = new DefaultOAuth2AuthenticatedPrincipal(
            "test-user-42",
            attrs,
            List.of(new SimpleGrantedAuthority("SCOPE_orders:read"))
        );

        when(introspector.introspect(testToken))
            .thenReturn(principal)
            .thenThrow(new BadOpaqueTokenException("inactive token"));

        mvc.perform(get("/v1/orders/fixture-42")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken))
            .andExpect(status().isOk());

        mvc.perform(get("/v1/orders/fixture-42")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken))
            .andExpect(status().isUnauthorized());
    }
}
```

**Giới hạn:** test này chỉ chứng minh **Spring RS từ chối khi introspector chuyển từ principal hợp lệ sang lỗi token**. Nó **không kiểm RFC 7009, AS persistence, introspection HTTP response hoặc cache/propagation** vì introspector đã bị mock. Phải bổ sung E2E test ở `13` để chứng minh revoke thật.

### 17.4. Tại sao cần test riêng audience?

Trong Spring Security, chỉ cấu hình `issuer-uri` (JWT) hoặc introspection URI (opaque) **không bảo đảm** audience của API được kiểm theo mọi phiên bản/profile. Cần validator/resource policy cho `aud=orders-api`:

```text
Introspection: active=true, aud=["payments-api"]
RS: orders-api

Expected:
  401/invalid_token or equivalent denial, never 200
```

Không được bỏ audience check chỉ để test mock principal có thể qua filter; test sản xuất cần policy đầy đủ.

### 17.5. Negative test fail-closed

Test Spring RS khi:

- Introspection trả inactive → không có authenticated principal.
- JSON `active` sai kiểu/thiếu → deny.
- AS trả HTTP 401 do RS introspection secret sai → **không allow**.
- AS timeout/5xx → **không allow**, HTTP có thể 503 theo service contract.
- Token active thiếu scope → 403.
- Sender-constrained proof sai → deny dù AS nói active.

Tùy framework, network failure có thể vào handler 5xx chứ không 401; test điều quan trọng nhất là **không có business side effects trái quyền**.

## 18. Test cache `active=true` cũ

Introspection có thể được cache để giảm latency lên AS. Nhưng một cache `active=true` tạo cửa sổ token revoked còn được dùng.

### 18.1. Timeline có thể kiểm

```text
T=00:00  AS issues A1; RS introspects -> active=true
T=00:01  RS caches result for 30 seconds
T=00:05  AS revokes A1; introspection server now active=false
T=00:06  RS cache hit -> may still accept A1
T=00:31  RS cache expires; query AS -> active=false; deny
```

Đây là **timeline minh họa**. Thời điểm cache TTL được tính từ insertion/expiration cụ thể và propagation phụ thuộc chính sách. Đừng suy mọi AS/RS đều có cache 30 giây.

### 18.2. Tiêu chí PASS/FAIL phụ thuộc hợp đồng

- Nếu hệ thống **cho phép stale allow tối đa 30 giây**, test phải đảm bảo không vượt bound đó và có audit/monitoring thích hợp.
- Nếu mục tiêu **revoke trong 2 giây**, positive cache 30 giây không đủ nếu không có **event-driven invalidation** hoặc đường check mạnh hơn.
- Nếu token hết hạn trong 5 giây, TTL cache 30 giây **không được vượt `exp`**; RS phải tiếp tục time-check dù cache active.
- Nếu RS đã biết token revoked, không dùng replica/cache cũ để **khôi phục active** trái thiết kế.

### 18.3. Negative cache không biến outage thành grant

Cache `active=false` có thể giúp chống token scanning nhưng cần TTL hợp lý. Một network error hoặc AS authentication failure **không được cache như `active=true`**; nếu dùng negative fallback, phải phân biệt **"revoked/unknown"** với **"introspection unavailable"** trong telemetry.

### 18.4. Shared cache và nhiều RS

Một cache shared giữa `orders-api` và `payments-api` cần cô lập **issuer, resource audience, token type/policy context**; không dùng response introspection active cho orders để payments cũng accept. Raw token cũng không nên nằm trong debug key/metrics; nếu dùng digest/HMAC để đặt key cần threat model và secret management riêng.

### 18.5. Event invalidation không miễn test TTL

AS có thể phát revoke event để evict cache. Test nên mô phỏng:

1. Event đến đúng, cache bị xóa, request tiếp theo deny.
2. Event bị mất, TTL vẫn giúp eventually recheck.
3. Event đến trễ hoặc lặp, token không hồi sinh.
4. Event của grant H không xóa nhầm mọi token không liên quan.
5. Invalidator bị tấn công/không có quyền, RS không tự allow.

## 19. Test multi-region và eventual consistency

AS, token store và RS có thể ở nhiều vùng. Một request sau revoke đi qua region A có thể nhận inactive, trong khi region B dùng replica cũ trả active.

### 19.1. Ma trận vùng

| AS intro region | RS region | Trước revoke | Sau revoke trước bound | Sau security bound |
| --- | --- | --- | --- | --- |
| A | A | Active / API allow | Có thể chuyển dần theo architecture | Inactive / API deny |
| A | B | Active / API allow | Cache B có thể cũ | Inactive / API deny |
| B | A | Active / API allow | Replica B có thể trễ | Inactive / API deny |
| B | B | Active / API allow | Replica + cache có thể trễ | Inactive / API deny |

Test nên chạy **theo tất cả đường định tuyến được hỗ trợ**, không chỉ đường runner gần AS primary. Khi có failover, cũng cần kiểm revoked marker/version còn tồn tại.

### 19.2. Monotonicity test

```text
Observed:
  A1 inactive in region-A at T1
  A1 active in region-B at T2 > T1

Question:
  Does security contract allow this temporary inconsistency?
  If not, monotonicity/replica gating has failed.
```

Không tự tuyên bố bất cứ `active=true` tạm thời nào là violation nếu hệ thống đã công bố một bounded eventual-consistency SLA. Nhưng **sau bound**, tất cả RS paths phải deny. Với hệ thống yêu cầu monotonic denial, thiết kế state/version phải chặn việc active lại kể cả trong cửa sổ đồng bộ.

### 19.3. Test failover/restart

1. Revoke `A1`, xác minh inactive ở primary.
2. Chuyển reads sang standby/replica có policy được kiểm.
3. Khởi động lại AS/RS/cache node phù hợp môi trường test.
4. Introspect lại `A1` và gọi RS; phải deny khi policy yêu cầu.
5. Kiểm grant version/denylist được persist, không mất qua restart.

**Không thực hiện disruptive failover test trên production nếu chưa có change control và isolation.**

## 20. Concurrency: race giữa revoke, refresh và API request

Các sự kiện có thể xảy ra đồng thời. Test không nên giả định mọi request được xử lý theo thứ tự nhìn thấy ở terminal.

### 20.1. Revoke và API authorization đồng thời

```text
T1: RS authenticates A1, introspection active=true
T2: AS commits revoke A1
T3: Business operation previously authorized completes
```

Không thể đòi revoke tại T2 tự **rollback** operation đã qua authorization trước đó. Nếu yêu cầu nghiệp vụ nhạy cảm phải chặn thao tác ngay sát commit, thiết kế có thể cần **re-check authorization at business commit**/transaction lock, độc lập với một lượt introspection lúc request entry.

### 20.2. Revoke và refresh đồng thời

```text
Client refresh R1  --------\
                           > AS transaction ordering / lock / CAS
Admin revokes grant G -----/
```

Cần định nghĩa **linearization/commit semantics**:

- Nếu revoke G được commit trước khi refresh được xét cuối, refresh không được cấp token dựa trên grant đã revoked.
- Nếu refresh được commit trước revoke, access token vừa cấp cũng phải tuân theo **cascade/expiry/deny** của grant mới bị revoked.
- Không tạo tình trạng token “orphan” sau revoke do hai worker cùng update store không atomic.

Test chạy nhiều lần với controlled barriers/latches và assertion trên **toàn bộ tokens phát từ grant**, không chỉ request cuối.

### 20.3. Refresh-token rotation và reuse detection

Giả sử:

```text
R1 --refresh--> R2 + A2
Attacker/client retries R1
AS detects reuse according to policy
AS revokes family F
```

Test:

1. R1 được đánh dấu rotated, không còn dùng để xin token theo rotation policy.
2. R2 là current khi flow thành công.
3. Reuse R1 dẫn đến `invalid_grant`/reuse handling tương ứng, không phát token mới trái policy.
4. Nếu chính sách revoke cả family, R2 cũng không còn refresh được.
5. Những access tokens family liên quan bị RS từ chối theo **đã công bố**; test introspection/local denylist/expiry theo thiết kế.
6. Token ngoài family F không bị revoke ngoài ý muốn.

**Lưu ý retry hợp lệ:** mạng có thể làm client không nhận response refresh dù AS đã rotate. Các AS có thể dùng giải pháp xử lý retry/idempotency hoặc grace policy đặc thù; phải test vừa chống attacker reuse vừa không tạo false-positive family revoke quá mức.

### 20.4. Revoke và code exchange đồng thời

Một authorization code thuộc grant G chưa được đổi, user/admin rút quyền, sau đó client gửi `POST /token`. Test cần xác minh AS **không cấp access token dựa trên grant đã vô hiệu** nếu đây là security contract. Code vẫn có thể là chuỗi syntactically valid, nhưng authorization state đã đổi.

### 20.5. Không tạo lỗi race bằng test teardown

Nếu cleanup test grant xảy ra trước assertions, RS có thể trả 401 do teardown chứ không do revoke step. Giữ lifecycle fixtures độc lập và **cleanup sau khi kiểm đầy đủ**; khi chạy song song, mỗi testcase có grant ID riêng.

## 21. Chẩn đoán test thất bại theo vị trí

| Kết quả quan sát | Khả năng nguyên nhân | Kiểm tiếp |
| --- | --- | --- |
| Baseline đã 401 | Token không hợp lệ, issuer/aud sai, expired, RS config | Kiểm issuance, policy, fixture time |
| Baseline 403 | Thiếu scope, tenant/resource policy | Chọn endpoint/quyền baseline đúng |
| `/revoke` HTTP 401 | Client authentication sai | Kiểm registration, secret/key, TLS |
| `/revoke` HTTP 200 nhưng introspection active | Revoke chưa persisted, token khác, replica lag, scope không đúng | Kiểm token reference, grant status, AS consistency |
| Introspection inactive nhưng RS 200 | Positive cache stale, JWT offline, policy bypass, public endpoint | Kiểm RS enforcement path/cache/token type |
| RS 401 nhưng introspection active | Token sai audience/type/exp hoặc RS misconfig | Không đánh đồng 401 với revoked |
| AS timeout, RS 200 | **Fail-open security bug** hoặc explicit fallback có lỗ hổng | Kiểm exception handlers/circuit breaker |
| Revoke A làm token B 401 | Cascade scope quá rộng hoặc test token chung grant | So sánh grant/family/registration |
| Sau restart token active lại | Revocation state không persist hoặc stale replica | Kiểm DB/denylist version, cache hydration |
| CI xanh nhưng production revoke chậm | Mock thay AS, thiếu multi-region/caches | E2E latency test với topology tương đương |
| Token test hết hạn giữa bài | Fixture lifetime quá ngắn, clock skew | Phát token mới, safety margin, fake clock |
| Chỉ ghi “200 revoke” vào report | Test oracle thiếu RS negative check | Thêm introspection+RS+isolation |

### 21.1. Ba câu hỏi để định vị lỗi nhanh

1. **Trước revoke token có thực sự hợp lệ cho endpoint không?** Nếu không, test không chứng minh gì về revoke.
2. **AS đã chuyển token/grant sang inactive chưa?** Nếu chưa, kiểm revocation persistence và policy.
3. **RS có đọc và enforce trạng thái inactive mới nhất không?** Nếu chưa, kiểm cache/JWT offline/replication/authorization filters.

### 21.2. Không “sửa test” bằng cách nới security

Không tắt audience validation, bỏ signature/JWKS, đổi exception thành allow, tăng cache TTL vô hạn hoặc thêm `sleep(60000)` để test xanh. Phải chỉnh **nguyên nhân**: token fixture, grant scope, AS state transition, RS revocation path và giới hạn propagation.

## 22. Ma trận kiểm thử revocation toàn diện

Ma trận này phân biệt **trước revoke**, **hành động**, **trạng thái kỳ vọng** và **đường RS thực thi**. Điều kiện “AS inactive” chỉ áp dụng khi token/grant thực sự nằm trong phạm vi revoke và AS cung cấp introspection phù hợp.

| # | Test case | Hành động | Kỳ vọng cốt lõi |
| --- | --- | --- | --- |
| 1 | Opaque access token hợp lệ | Baseline `GET` và introspect | `active=true`, RS 200 đúng scope |
| 2 | Revoke opaque access A1 | `POST /revoke(A1)` | AS inactive, RS deny trong bound |
| 3 | Revoke unknown token | Gửi random unknown token từ client authenticated | HTTP 200 theo RFC 7009, không lộ tồn tại |
| 4 | Revoke A1 lần hai | Revoke lại sau inactive | Idempotent, token không sống lại |
| 5 | Revoke khi A1 đã expired | Gọi revoke token quá hạn | Không nhầm expiry với revoke thành công |
| 6 | Revoke thiếu token parameter | POST form thiếu `token` | AS báo lỗi request, không cấp quyền |
| 7 | Revoke với hint sai | `token_type_hint=refresh_token` cho access A1 | AS xử lý hint theo contract, không đổi token type |
| 8 | Revoke không có client auth | Caller không xác thực | Không thể revoke trái phép |
| 9 | Revoke bằng client credential sai | Basic/keys invalid | Error appropriate, không effect ngoài policy |
| 10 | Client khác revoke token | Caller không có authority | AS bảo vệ token ownership/existence |
| 11 | Access token không cùng grant | Revoke A1; giữ B1 | B1 vẫn active/200 |
| 12 | Revoke một access trong grant | Revoke A1, kiểm A2/R1 | Chỉ cascade đúng provider policy |
| 13 | Revoke refresh token R1 | Sau revoke thử refresh R1 | Không mint token mới bằng R1 |
| 14 | Revoke refresh token R1 cùng grant A1 | Test access token cascade | Theo documented AS scope, không tự giả định |
| 15 | Revoke cả grant G | Revoke grant từ UI/admin | Không mint tokens từ G; RS deny theo bound |
| 16 | Revoke consent user | Disconnect client app | New token issuance không vượt revoked consent |
| 17 | User logout RP | Xóa local session | Không nhầm với revoke grant nếu logout policy không làm |
| 18 | OP logout | Kết thúc SSO | Test token behavior theo OIDC/logout policy |
| 19 | Disable client registration | Admin disable client | Không xin token mới; access tokens theo policy |
| 20 | Account lock/password reset | Security event | Token/grant/session scope đúng chính sách |
| 21 | Revoke refresh family do reuse | Replay rotated R1 | Reuse detection, family state theo policy |
| 22 | Refresh retry bị mất response | Client gửi lại request hợp lệ | Policy giải quyết retry không tự cấp vô hạn |
| 23 | JWT offline bị revoke ở AS | RS chỉ chữ ký/exp | Phát hiện stale-allow gap như đã thiết kế |
| 24 | JWT revocation-aware | Introspection/denylist sau revoke | RS deny trước exp theo bound |
| 25 | JWT sai chữ ký từ đầu | Không revoke | RS deny; không tính là chứng minh revoke |
| 26 | Token sai issuer | Gửi token AS khác | RS deny independent of revocation |
| 27 | Token sai audience | Active token dùng RS khác | RS deny; không coi là revoked |
| 28 | Token thiếu scope | Active token gọi write API | 403, không nhầm với revoke |
| 29 | Token sai tenant | Active token truy cập tenant khác | 403/policy deny |
| 30 | Refresh token gửi RS | Dùng token R1 làm bearer API | RS từ chối |
| 31 | ID token gửi RS | OIDC ID token làm access token | RS từ chối |
| 32 | DPoP-bound token thiếu proof | Không gửi proof/ký sai | RS deny dù introspection active |
| 33 | mTLS-bound token sai cert | Gửi cert không khớp `cnf` | RS deny |
| 34 | DPoP/mTLS token đã revoke, proof đúng | Gửi proof hợp lệ cùng revoked token | RS vẫn deny |
| 35 | AS introspection trả `active=false` | HTTP 200 + JSON false | RS deny, không chỉ dựa HTTP 200 |
| 36 | AS introspection trả `"false"` string | JSON sai kiểu | Parser fail closed |
| 37 | JSON thiếu `active` | Response sai hợp đồng | RS deny, không default true |
| 38 | JSON malformed | Syntax lỗi/HTML error page | RS deny, alert |
| 39 | AS introspection 401 | RS Basic/cert sai | RS không allow, alert integration |
| 40 | AS introspection 5xx | Backend outage | RS fail closed hoặc fallback có giới hạn rõ |
| 41 | AS timeout | Không có response | Không bypass authentication |
| 42 | Introspection endpoint public | Không có client auth | AS không leak token metadata |
| 43 | Introspection token scanning | Random tokens/rate burst | Rate limiting, không log raw tokens |
| 44 | Introspection token thuộc RS khác | Caller là RS không được xem | Không leak protected metadata |
| 45 | RS positive cache 30s | Revoke khi cache active | Time-to-deny không vượt SLA |
| 46 | RS negative cache | Nhiều token unknown | Không tạo cache DoS/allow |
| 47 | Cached active quá `exp` | Token hết hạn khi cache còn | RS deny do expiry |
| 48 | Cache shared giữa API | Orders cache dùng ở Payments | Không cross-audience allow |
| 49 | Revoke event bình thường | AS publish invalidate | Cache được evict, RS deny |
| 50 | Revoke event mất | Không nhận invalidate | TTL/reconcile vẫn giới hạn stale-allow |
| 51 | Revoke event trùng/đảo thứ tự | Old event đến sau new state | Không hồi sinh token |
| 52 | AS region A/B lệch | Revoke tại A, introspect tại B | Tất cả deny trước/đúng bound |
| 53 | RS region X/Y lệch | X cache cũ, Y mới | Đo max propagation mọi RS |
| 54 | Failover AS sau revoke | Đổi leader/replica | Token không active trở lại |
| 55 | Restart RS sau revoke | Rehydrate cache | Không nạp stale active trái policy |
| 56 | Revoke và refresh đồng thời | Barrier cho hai giao dịch | Token output theo linearization/policy |
| 57 | Revoke và GET đồng thời | Auth decision trước/sau commit | Phân biệt in-flight với new request |
| 58 | Revoke và code exchange | Code pending khi grant revoked | Không mint trái grant liveness policy |
| 59 | Double revoke concurrent | Hai requests cùng token | Idempotent, no grant resurrection |
| 60 | Grant revoke đồng thời cleanup | Teardown test | Không gây false-positive deny |
| 61 | Token leakage trong logs | App/proxy/APM ở DEBUG | Sentinel test báo lỗi nếu raw credential xuất hiện |
| 62 | Revoke xong B1 bị từ chối | B1 thuộc grant khác | FAIL: revocation scope quá rộng |
| 63 | AS inactive nhưng RS 200 quá SLA | Request hậu revoke | FAIL: enforcement/cache/propagation |
| 64 | Revoke API 200 nhưng AS state active quá SLA | Query authoritative state | FAIL: persist/lookup/policy |

### 22.1. Nhóm test nào chạy ở đâu?

- **Unit:** token/grant state machine, scope calculations, response parsing, error mapping, authorization rules, cache key isolation.
- **Component:** Spring `OpaqueTokenIntrospector`, controller guards, JWKS/denylist adapters, HTTP/TLS client integration với AS giả lập.
- **Integration:** AS thật + test database/store, revocation endpoint, introspection endpoint, refresh/token family semantics.
- **End-to-end:** AS + RS + gateway + cache + network path; cùng token trước và sau.
- **Resilience/chaos trong môi trường cách ly:** AS/Redis outage, replica lag, failover, concurrent revoke/refresh, event loss.
- **Security:** unauthenticated revoke/introspection, token leakage, issuer/audience substitution, replay và sender-proof mismatch.

Không coi một bài MockMvc test green là thay thế cho E2E revoke: mock có thể trả inactive mà AS thật chưa hề persist revoke.

## 23. Thiết kế test property/invariant

Ngoài từng test case, có thể định nghĩa **invariants** để property-based testing hoặc state-machine testing sinh nhiều chuỗi sự kiện khác nhau.

### 23.1. Invariant 1 — Revoked token không được cấp quyền ngoài policy

```text
For any token T and protected endpoint E:
  if T is revoked in the authoritative grant model
  and the configured propagation bound has elapsed
  and E is required to enforce this revoke state,
  then E must not authorize a new request using T.
```

Không dùng ký hiệu **“revoked means any in-flight transaction must rollback”** nếu nghiệp vụ không có enforcement tại commit. Tách **new request authorization** khỏi **business transaction đã được chấp thuận trước revoke**.

### 23.2. Invariant 2 — Revoke không cấp quyền mới

```text
revoke(T) does not:
  create new access/refresh token,
  widen scope/audience,
  restore another revoked token,
  or grant access to a different subject/tenant.
```

Test các chuỗi revoke lặp, cache invalidation, restore client registration và reauthorization.

### 23.3. Invariant 3 — Revoke không ngoài scope

```text
Given token A in grant G and token B outside affected scope:
  revoke(A or G) must not invalidate B
  unless an explicit higher-level policy requires it.
```

Nếu một admin chọn **“revoke all sessions of this user”**, scope có thể rộng hơn; test phải phản ánh action đó và không coi mọi B là unrelated.

### 23.4. Invariant 4 — Error không biến thành authenticated principal

```text
introspection_error
OR malformed_response
OR missing_required_metadata
OR revoked_state
=> No authorization based on this token alone.
```

Ngoại lệ fallback có kiểm soát phải được **mô hình hóa riêng** với bounded staleness và giới hạn endpoint; không viết catch-all `allow()`.

### 23.5. Invariant 5 — Scope không tự mở rộng qua refresh

```text
scopes(access_token_from_refresh) subset_of approved_grant_scopes
resource/audience subset_of authorized_client_grant_policy
```

Revoke/grant change đồng thời refresh phải không tạo token mới với quyền từ trạng thái cũ ngoài security policy.

### 23.6. State-machine fuzzing

Một test generator có thể chọn chuỗi:

```text
ISSUE -> INTROSPECT -> RS_GET -> REVOKE -> RS_GET
ISSUE -> REFRESH -> REVOKE_GRANT -> REFRESH_AGAIN
ISSUE -> REVOKE -> REVOKE -> RESTART_AS -> INTROSPECT
ISSUE -> CACHE_POSITIVE -> REVOKE -> LOSE_EVENT -> WAIT_TTL -> RS_GET
ISSUE -> ROTATE_R1_TO_R2 -> REUSE_R1 -> RS_GET
```

Đừng dùng fuzzing với token/credential production. Sinh fixtures trong sandbox, giới hạn request rate và bảo đảm cleanup.

## 24. CI pipeline và độ tin cậy của kiểm thử

### 24.1. Thứ tự chạy được đề nghị

```text
1. Static/config checks
   -> issuer, audience, scopes, token TTL, endpoints from trusted config

2. Unit tests
   -> state transitions, revocation scope, parsers, failure behavior

3. Component tests
   -> Spring RS auth filters, token type, audience/scope

4. AS integration tests
   -> RFC 7009 revoke, RFC 7662 introspection, refresh/family

5. E2E pre/revoke/post
   -> AS + RS + cache/gateway, negative and isolation

6. Topology/resilience tests (scheduled or pre-release)
   -> cache lag, multi-region, failover, concurrent refresh/revoke

7. Security checks
   -> credential redaction, logs, SSRF, token scanning, rate limits
```

Không cần chạy multi-region chaos trên mỗi commit nếu quá đắt hoặc gây mất ổn định; nhưng release gate cần có bằng chứng phù hợp với **revocation security objective**.

### 24.2. Tách fail do môi trường khỏi fail security

Trong CI report nên phân biệt:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **PASS** | Baseline hợp lệ và revoke/AS/RS/isolation đều đúng contract |
| **SETUP_FAILED** | Không phát token được, fixture/AS test chưa sẵn sàng |
| **SECURITY_FAILED** | RS vẫn allow sau bound hoặc fail-open, revoke vượt scope |
| **INTEGRATION_FAILED** | RS/AS schema, credentials, protocol contract sai |
| **TIMING_INCONCLUSIVE** | Token hết hạn tự nhiên, clock/lifecycle làm test không còn phân biệt được revoke |
| **ENVIRONMENT_UNAVAILABLE** | Sandbox AS/network/store outage, không đo được revocation objective |

Không đánh đồng `ENVIRONMENT_UNAVAILABLE` với PASS. Một **security gate** có thể chặn release khi không có bằng chứng, nhưng lỗi hạ tầng cần được phân loại để điều tra đúng nơi.

### 24.3. Loại bỏ test flakiness

- Cấp token/refresh family riêng theo test case.
- Không chạy revoke trên shared client session/tenant state của test khác.
- Tránh hardcoded wall-clock `exp` đã qua.
- Bounded polling với deadline, không phụ thuộc một `sleep` duy nhất.
- Không assert thời điểm đồng bộ gần zero nếu architecture eventual consistency.
- Không dùng test API endpoint public và không tạo business writes thật.
- Khi chạy parallel, dùng unique grant/fixture identifier, teardown isolation và test-only data.
- Không retry tới khi test xanh nếu nó chỉ làm ẩn stale-allow vượt SLA.

### 24.4. Báo cáo kỹ thuật có thể đọc được

```json
{
  "case_id": "REV-E2E-OPAQUE-01",
  "issuer_ref": "test-issuer-A",
  "resource_ref": "orders-api",
  "token_fixture": "A1",
  "revocation_scope": "ACCESS_TOKEN_ONLY",
  "baseline_api_status": 200,
  "revoke_endpoint_status": 200,
  "introspection_after": "INACTIVE",
  "api_after_status": 401,
  "unrelated_fixture_status": 200,
  "propagation_target_ms": 10000,
  "propagation_observed_ms": 1400,
  "result": "PASS"
}
```

Các con số **giả định** cho minh họa. `token_fixture` là label an toàn, **không chứa raw token**. Không ghi `sub`/tenant PII nếu không cần; quyền đọc báo cáo và retention phải phù hợp.

## 25. Các bẫy bảo mật khi viết test revocation

### 25.1. Test code vô tình in token ra stdout

Framework HTTP client thường có log request/response mặc định ở DEBUG. Nếu test in:

```text
POST /revoke token=eyJhbGciOi...
Authorization: Bearer eyJhbGciOi...
Authorization: Basic ...
```

thì **pipeline đã tạo một sự cố token leakage**. Kiểm redaction trong app, proxy, APM, test runner và issue tracker. Chỉ dùng safe fixture labels, không trích prefix/suffix token để “đối chiếu”.

### 25.2. Test harness được phép revoke bất kỳ user?

Một test-only admin utility có quyền revoke grant có thể nguy hiểm nếu lộ ra production. Thiết kế:

- Chỉ bind trong sandbox/CI và kiểm network/identity authorization.
- Có policy và audit cho test controls.
- Đảm bảo token issuance/revoke không dùng real user/tenant data.
- Xóa/tắt test-only endpoints khỏi production artifact khi có thể.

### 25.3. Introspection endpoint là một oracle

Nếu bất kỳ ai có token string đều hỏi `/introspect` và nhận `sub`, `scope`, `aud`, endpoint trở thành nơi dò token existence/metadata. Test unauthorized introspection và response `active=false` tối thiểu; áp dụng caller authentication, rate limits và scope restrictions.

### 25.4. AS issuer URL từ input chưa tin cậy

RS nhận JWT có untrusted `iss` hoặc `jku` rồi gửi raw token tới URL trong claim → nguy cơ **SSRF và token exfiltration**. Test chỉ issuer/endpoint từ **trusted config**, không cho token lựa chọn nơi introspect.

### 25.5. Revoke không thay audience/scope validation

Ngay trước revoke, một token active **dành cho API khác** vẫn phải bị từ chối ở RS này. Nếu test chỉ dùng status 401 làm “post-revoke PASS”, có thể không phát hiện API đang bỏ audience check vì token test đã sai audience từ đầu.

### 25.6. Sender-constrained token cũng phải bị revoke

mTLS/DPoP-bound access token hạn chế replay khi attacker chỉ có bản sao token, nhưng **không biến token thành không thể revoke**. Test cùng một token với **proof/cert đúng** trước/sau revoke; nếu sau revoke vẫn allow, sender constraint không thay thế trạng thái authorization.

### 25.7. Không dùng brute force tokens để “test existence”

Security testing về rate limiting/introspection privacy phải dùng **chuỗi giả được sinh trong sandbox với tốc độ giới hạn**, không thử tokens thật/đoán token người khác, tránh DoS và vi phạm quyền riêng tư.

## 26. Bài thực hành

### Bài A — Nhận diện false positive

Test sau được báo “PASS”:

```text
token = "NOT_A_REAL_TOKEN"
POST /revoke(token) -> 200
GET /orders with token -> 401
```

Vì sao **không chứng minh revocation**? Thiết kế lại với bước phát token, baseline 200, introspection trước/sau và isolation token B.

### Bài B — Giải thích HTTP 200 ở hai endpoint

```text
POST /revoke(A1)       -> 200
POST /introspect(A1)   -> 200 {"active":false}
```

Hai `200` này có nghĩa khác nhau thế nào? Nếu `/introspect` trả `200 {"active":true}` sau revoke, cần điều tra những lớp nào trước khi kết luận lỗi?

### Bài C — Test JWT offline

AS cấp JWT `J1` với `exp` còn 20 phút. Admin revoke grant tại phút thứ nhất. RS chỉ kiểm chữ ký, issuer, audience và expiry. Dự đoán RS xử lý `J1` trong 19 phút tiếp theo. Đề xuất ba chiến lược giảm window: introspection/denylist, grant-version event, hoặc TTL ngắn. Nêu trade-off availability/latency.

### Bài D — Revoke refresh family

```text
R1 -> rotate -> R2 + A2
Replay R1 detected -> AS revokes family F
```

Viết test trước/sau cho R1/R2/A2 và một token B1 ngoài family, với assumption rõ **family revoke cascade** của AS. Vì sao không được khẳng định mọi AS có hành vi giống nhau?

### Bài E — Multi-region

AS primary vùng A commit revoke lúc T0. Replica vùng B trễ tối đa 4 giây; RS vùng X cache active tối đa 20 giây. SLA bắt buộc time-to-deny dưới 5 giây.

Đề xuất cải tiến và cách đo. Vì sao một cache 20 giây có thể vi phạm SLA dù primary đã trả `active=false` ngay? Làm sao test tất cả đường RS/AS?

### Bài F — Scope và tenant

Introspection trả `active=true`, `aud=orders-api`, `scope=orders:read` cho user A. User gọi:

```text
POST /v1/orders/42/delete
resource.tenant = tenant-B
user.tenant = tenant-A
```

API phải trả gì và vì sao **không thể dùng kết quả này làm post-revoke evidence**? Hãy thay bằng một `GET`/resource đúng quyền baseline.

### Bài G — AS outage

Một developer viết:

```java
// Anti-pattern: fail open.
try {
    return introspector.isActive(token);
} catch (Exception ex) {
    return true;
}
```

Sửa theo fail-closed, giới hạn retry, alert, optional 503 và security-approved bounded fallback. Định nghĩa test khi AS trả 401/5xx/timeout/JSON malformed.

### Bài H — Race giữa revoke và API

Một request `DELETE /orders/42` đã được authorize trước khi revoke, nhưng transaction DB commit sau revoke. Có nhất thiết rollback được không? Nếu business cần bảo đảm không commit sau revoke, thiết kế **re-check tại commit** và test thứ tự bằng barrier.

### Bài I — Spring Security MockMvc

Từ `ResourceServerRevocationWebTest` ở phần 17:

1. Mock `OpaqueTokenIntrospector` trả principal có `SCOPE_orders:read`, gọi GET nhận 200.
2. Thay mock bằng `BadOpaqueTokenException`, cùng token gọi GET phải 401.
3. Mock active principal sai audience, thêm audience validator để chặn.
4. Mock valid principal thiếu scope cho POST, nhận 403.
5. Giải thích tại sao vẫn cần E2E với AS thật và `/revoke` thật.

### Bài J — Isolation và phạm vi grant

Hai tokens A1 và B1 thuộc hai grant khác nhau nhưng cùng subject và scope. Chỉ revoke A1. Kết quả:

```text
A1 => 401
B1 => 401
```

Khi nào đây là bug revoke quá rộng? Khi nào lại là hành vi đúng vì hành động thực tế là **“revoke all sessions/user grants”**? Viết test expectations dựa trên scope đã xác định trước.

### Bài K — Token đã hết hạn giữa test

Baseline `A1` có `exp` trong 3 giây, AS revoke sau 2 giây, RS deny tại giây thứ 4. Vì sao không thể kết luận revoke propagation thành công? Cách thiết kế fixture/clock để phép đo có ý nghĩa?

### Bài L — Bảng kết quả kiểm thử

Tự xây báo cáo CI với:

```text
case_id
expected_revocation_scope
token_fixture_label
baseline_status
revoke_http_status
as_introspection_before/after
rs_status_before/after
propagation_bound
observed_delay
unrelated_token_status
classification
```

Không có trường raw token/header/secret. Với case FAIL, yêu cầu giải thích nguyên nhân nghi ngờ và log reason code an toàn.

## 27. Checklist kiểm thử trước khi phát hành

- [ ] Test chạy trong **môi trường cô lập**, không dùng tokens, clients hoặc users production.
- [ ] Mỗi test sinh token/grant riêng và có cleanup sau assertions, tránh shared-state flakiness.
- [ ] Xác định rõ action revoke **access token, refresh, family, grant, client, session hay user**.
- [ ] Baseline dùng endpoint bắt buộc xác thực, đúng issuer/audience/scope/tenant; **200 trước revoke** hoặc bằng chứng authorization tương đương.
- [ ] Không dùng token đã hết hạn/unknown ở baseline rồi coi 401 hậu revoke là PASS.
- [ ] Revoke request đúng RFC 7009: HTTPS POST form-urlencoded, token, hint tùy chọn, client authentication/authority.
- [ ] Test idempotency: revoke lặp token không làm token active trở lại và không lộ token existence.
- [ ] Revoke response 200 **không là assertion cuối**; kiểm AS token/grant state riêng.
- [ ] Với introspection, `active` là **Boolean**, trước active và sau false theo RFC 7662/AS contract.
- [ ] Test AS introspection 401/403/5xx/timeout/malformed response **không tạo allow**.
- [ ] Test RS dùng **cùng token bytes, cùng endpoint/tài nguyên** trước và sau revoke.
- [ ] RS sau revoke từ chối token trong propagation bound được thiết kế; không chấp nhận status 200 ở endpoint public làm bằng chứng.
- [ ] Token khác ngoài revoke scope vẫn hoạt động theo đúng quyền; không revoke lan rộng ngoài policy.
- [ ] Refresh token đã revoke không cấp access token mới; family/reuse/rotation theo chính sách được test.
- [ ] Token sai audience/issuer/type/scope/tenant được RS từ chối **độc lập** với revocation.
- [ ] JWT offline có security objective/TTL hoặc revocation-aware mechanism tương ứng; test không giả định signature mất hiệu lực.
- [ ] Opaque introspection có cache TTL/invalidation hợp lý, không vượt `exp` và propagation SLA.
- [ ] Multi-region/replica/failover/restart không làm token terminally revoked sống lại.
- [ ] Các race revoke–refresh, revoke–API, revoke–code-exchange có thứ tự/linearization được xác định.
- [ ] Sender-constrained tokens vẫn bị từ chối sau revoke **ngay cả khi proof hợp lệ**.
- [ ] RS không dùng introspection URL từ untrusted token metadata; có TLS, caller auth và rate limits.
- [ ] Test logs, metrics, APM, CI artifacts không chứa raw access/refresh/ID token, code, secret hoặc HTTP auth headers.
- [ ] Bounded polling, controlled clock, time-to-deny measurements và reason codes được thiết lập.
- [ ] Test failures được phân loại SETUP/AS_STATE/RS_ENFORCEMENT/ISOLATION/TIMING, không tự đổi thành PASS.
- [ ] Có test/diễn tập incident response khi revoke không propagate trong SLA.

## 28. Câu hỏi tự kiểm tra

**1. Vì sao `POST /revoke` trả 200 chưa đủ chứng minh revocation?** RFC 7009 có thể trả 200 cả với token invalid/unknown và response không đo việc RS đã từ chối.

**2. Cần ít nhất quan sát những gì?** Token hoạt động trước revoke, request revoke, trạng thái AS/introspection sau revoke, RS deny sau revoke và preferably unrelated token isolation.

**3. Một token chưa từng hợp lệ, sau revoke API 401, có phải test PASS không?** Không. Thiếu baseline và state transition.

**4. Introspection `active=false` chứng minh user vừa nhấn revoke?** Không. Token có thể expired, unknown hoặc không thể tiết lộ metadata.

**5. Introspection HTTP 200 + `active=false` có nên cho API qua không?** Không. RS phải từ chối.

**6. Introspection HTTP 401 là “token inactive” theo RFC 7662 sao?** Không. Nó thường biểu thị caller/RS authentication hoặc authorization error; RS vẫn fail closed.

**7. API trả 403 vì thiếu scope sau revoke có đủ làm bằng chứng revoke không?** Không. Token có thể vẫn active nhưng thiếu quyền ngay từ đầu.

**8. Vì sao phải dùng cùng endpoint/tài nguyên trước và sau revoke?** Để tránh thay đổi policy/resource làm sai nguyên nhân của denial.

**9. Tại sao cần token B1 ngoài revoke scope?** Để chứng minh AS/RS không vô tình khóa quyền của grants không liên quan.

**10. JWT còn chữ ký hợp lệ sau revoke có bất thường không?** Không. Chữ ký ký byte token; revoke là trạng thái authorization riêng.

**11. JWT offline validation tự biết grant revoked không?** Không nếu không có denylist, introspection, grant check hoặc cơ chế revocation-aware khác.

**12. Opaque token tự bảo đảm revoke ngay lập tức không?** Không. Positive cache và replica lag có thể trì hoãn RS deny.

**13. Time-to-deny đo từ đâu đến đâu?** Từ thời điểm revoke authoritative commit đến khi RS không còn chấp nhận token theo security objective, với đồng hồ/telemetry đo được.

**14. Có cần test tất cả vùng RS/AS không?** Nếu hệ thống có nhiều đường định tuyến/vùng, cần bảo đảm propagation bound trên tất cả đường quan trọng.

**15. Vì sao hardcoded `Thread.sleep(30000)` không phải kiểm chứng tốt?** Không cho biết thời điểm thực tế và gây flaky/chậm; nên bounded polling và deadline.

**16. Một access token active có `aud=profile-api` gọi orders API được không?** Không. Sai audience phải deny dù chưa revoke.

**17. Revoke refresh token có luôn revoke mọi access token cùng user không?** Không. Phạm vi cascade tùy RFC/provider policy và authorization grant.

**18. Replay refresh token cũ sau rotation kiểm điều gì?** Reuse detection, family policy, chống mint mới và ảnh hưởng tokens liên quan.

**19. Nếu AS outage RS nên tự allow vì mạng nội bộ không?** Không. Fail closed hoặc bounded fallback đã qua security review; không có catch-all allow.

**20. RS đã authorize trước revoke thì transaction nghiệp vụ phải tự rollback không?** Không mặc định. Cần thiết kế re-check/commit control riêng cho mục tiêu đó.

**21. Unit test MockMvc với mock introspection có chứng minh revoke endpoint thật hoạt động?** Không. Nó chỉ kiểm RS phản ứng với trạng thái do mock đưa ra.

**22. Token hết hạn tự nhiên giữa test làm mất bằng chứng gì?** Không thể tách denial do `exp` khỏi denial do revoke.

**23. Vì sao phải test malformed `active` và HTTP errors?** Để ngăn parser/exception vô tình biến response không đáng tin thành authenticated principal.

**24. Dữ liệu nào nên xuất trong báo cáo?** Safe fixture label, request ID, HTTP statuses, active flag, bound/observed latency, result/reason code; không raw credentials.

**25. PASS đầy đủ nên chứng minh gì?** Baseline valid, revoke accepted theo scope, AS inactive, RS deny trong bound, token khác không liên quan vẫn đúng quyền và không có token leakage.

## 29. Tài liệu tiêu chuẩn tham khảo

- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation endpoint, response idempotency, access/refresh token revocation, token type hint và caller authentication.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active` semantics, POST, protected metadata và introspection client authentication.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization grants, client authentication, token endpoint, refresh token và scope.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer access tokens, `invalid_token`, `insufficient_scope`, 401/403 và bảo vệ credential.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access token, issuer/audience/expiry/client claims và resource-server validation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay, refresh token rotation, sender-constraining và security guidelines.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** kiểm code exchange độc lập revoke.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** audience/resource-targeted access tokens và token separation.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client authentication và sender constraint qua mTLS.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof-of-possession, sender-bound access token và replay protection.
- **OpenID Connect Core 1.0:** ID token, OP/RP login và phân biệt OIDC session với OAuth access/refresh token.
- **OpenID Connect RP-Initiated Logout / Back-Channel Logout:** mô hình logout khi liên kết với AS grant/token revoke.
- **Spring Security OAuth2 Resource Server documentation:** opaque token introspection, Bearer authentication, JWT validation, authority mapping và testing.
- **Spring Authorization Server documentation:** revocation/introspection endpoints, token state, grants và persistence adapters.
- **JUnit 5 User Guide:** integration test lifecycle, assertions, test isolation và execution.

**Kết luận:** **Một bài kiểm thử revocation đáng tin phải chứng minh chuyển trạng thái “token dùng được trước revoke” sang “chính token đó không còn cấp quyền sau revoke”, với giới hạn thời gian và phạm vi rõ ràng.** RFC 7009 trả lời cách yêu cầu thu hồi, RFC 7662 giúp quan sát `active`, còn RS là nơi quyết định thực tế API có từ chối token hay không. **JWT offline, opaque introspection cache, replication, refresh family và concurrent requests** khiến hai thời điểm này có thể khác nhau. Vì thế hãy luôn kiểm **baseline → revoke → introspection → RS denial → unaffected token**, đo revocation propagation, test fail-closed và giữ mọi token/secret ngoài log/CI artifacts. Một HTTP 200 ở `/revoke` hay một HTTP 401 không có baseline **không thay thế được bằng chứng end-to-end** rằng token đã bị thu hồi đúng và không thể bị phát lại để lấy quyền ngoài chính sách.
