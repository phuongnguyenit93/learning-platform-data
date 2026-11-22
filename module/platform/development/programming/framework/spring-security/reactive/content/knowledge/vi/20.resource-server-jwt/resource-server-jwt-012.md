# Giới hạn của JWT tự chứa khi cần thu hồi quyền tức thời

## 1. Bối cảnh và mục tiêu

Bài học thuộc phần **Resource Server JWT** của **Spring Security - reactive / Spring WebFlux**.

**JWT tự chứa (self-contained JWT)** là access token mang claims như `sub`, `scope`, `roles`, `aud`, `iss`, `iat`, `nbf`, `exp` và có chữ ký số. Một Resource Server có khóa xác minh đúng có thể tự kiểm tra chữ ký, issuer, thời gian sống và các quyền ghi trong claims **mà không cần gọi Authorization Server trên mỗi request**. Đây là ưu điểm lớn về hiệu năng, độ sẵn sàng và khả năng scale.

Tuy nhiên, khi quyền của người dùng bị thay đổi hoặc tài khoản phải bị khóa **ngay**, JWT đã phát thường **không tự cập nhật claims**. Dù backend mới xóa role `ADMIN` trong database, một access token có `scope=reports:approve` được ký hợp lệ vẫn chứa scope cũ cho tới khi hết hạn hoặc bị Resource Server từ chối bằng một **cơ chế trạng thái bổ sung**.

Mục tiêu:

1. Giải thích chính xác sự khác nhau giữa **JWT hợp lệ về mật mã** và **quyền truy cập còn hợp lệ theo chính sách hiện tại**.
2. Phân biệt thu hồi **một access token**, thu hồi **toàn bộ token của một account**, thay đổi **role/permission**, khóa tài khoản, logout, thu hồi **refresh token** và xoay khóa ký.
3. Hiểu vì sao `exp` ngắn **giảm cửa sổ rủi ro** nhưng không bảo đảm thu hồi tức thời.
4. So sánh **denylist theo `jti`**, **authz/version check**, **introspection với opaque token hoặc JWT**, **central PDP**, token TTL và event-driven caches.
5. Thiết kế điểm kiểm tra trạng thái sau bước xác minh chữ ký/issuer/audience, tránh để lookup chặn event loop trong Spring WebFlux.
6. Tạo ví dụ **Java 17+, Spring Boot 3.3.5, Spring Security 6.3.x**, gồm `ReactiveJwtDecoder` có thêm revocation check và endpoint thu hồi **chính access token hiện tại**.
7. Kiểm thử bằng `StepVerifier` cho decoder và `WebTestClient` cho HTTP authorization, biết test nào **thực sự đi qua decoder** và test nào dùng mock.
8. Đánh giá tính nhất quán phân tán, TTL, outage, fail-open/fail-closed, race conditions, bảo mật logs và khả năng đáp ứng yêu cầu “ngay lập tức”.
9. Chọn thiết kế phù hợp theo mức độ rủi ro của từng thao tác thay vì mặc định “JWT luôn stateless nên không thu hồi được”.

**Cảnh báo:** Bài có denylist lưu bằng `ConcurrentHashMap` chỉ để minh họa trên **một JVM**. Đây không phải giải pháp thu hồi an toàn cho nhiều instance production. Muốn thay đổi quyền có hiệu lực trên toàn hệ thống phải có nguồn trạng thái chia sẻ, policy về consistency và các test phù hợp.

## 2. JWT tự chứa hoạt động như thế nào?

Ví dụ payload access token minh họa:

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-42",
  "aud": ["inventory-api"],
  "jti": "access-7c6f",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000600,
  "scope": "reports:read reports:approve"
}
```

Các timestamp và IDs là **giá trị giả dùng giải thích**, không phải token sống cần chạy được. Một JWT có dạng `header.payload.signature` sau khi Base64URL encode và ký bằng thuật toán được issuer/resource server tin cậy. **Base64URL không phải mã hóa bí mật**: bên nhận token có thể đọc claims, nên không đặt mật khẩu, bí mật nội bộ hay PII không cần thiết trong access token.

Ở Spring Security Resource Server reactive, chuỗi xử lý điển hình:

```text
HTTP Authorization: Bearer <jwt>
           |
           v
AuthenticationWebFilter / Bearer token conversion
           |
           v
ReactiveJwtAuthenticationManager
           |
           v
ReactiveJwtDecoder
    +--> parse JWT an toàn
    +--> kiểm tra chữ ký/alg/khóa
    +--> kiểm tra iss, exp, nbf
    +--> audience và policy bổ sung nếu cấu hình
           |
           v
JwtAuthenticationConverter
    +--> scope/scp -> SCOPE_* authorities
           |
           v
ServerHttpSecurity.authorizeExchange(...)
    +--> Authentication / authorities
           |
           v
Controller/Service -> business data
```

Với cấu hình issuer-uri chuẩn, Spring Security xác minh JWT bằng public keys đã công bố, kiểm tra `iss`, `exp` và `nbf`, ánh xạ scope thành authority có prefix `SCOPE_`. **Audience `aud` phải được đánh giá theo yêu cầu của API; đừng giả định mọi cấu hình mặc định đã bắt buộc audience bạn mong muốn.** Nếu app không tự áp rule về `aud`, nó có thể nhận token được phát cho resource server khác cùng issuer.

Sau khi kiểm tra chữ ký đúng, `scope=reports:approve` vẫn là chuỗi đã được **issuer ký tại thời điểm phát hành**. Việc user có còn được phê duyệt báo cáo **tại thời điểm request** không là một câu hỏi **khác**.

### “Chữ ký hợp lệ” nói lên điều gì?

- Claims đã được một khóa tin cậy ký, theo algorithm policy của server.
- Claims không bị sửa tùy ý kể từ khi được ký.
- `iss`, `aud`, thời gian và loại token hợp lệ **nếu các validators liên quan được cấu hình đúng**.

Chữ ký **không tự chứng minh**:
- Account hiện vẫn enabled/unlocked.
- User hiện còn role/permission mà token mô tả.
- Session ở Authorization Server vẫn hoạt động.
- Access token chưa nằm trong danh sách thu hồi.
- Refresh token còn hiệu lực.
- Resource này vẫn thuộc về user (ownership).
- Hệ thống chưa phát chính sách khẩn cấp mới.

## 3. Vấn đề “quyền đã đổi nhưng token vẫn đúng”

Timeline:

```text
09:00  Authorization Server cấp JWT:
       sub=user-42, scope=reports:approve, exp=09:15

09:03  Resource Server nhận JWT:
       signature ✓   iss ✓   exp ✓   SCOPE_reports:approve ✓
       -> Cho phép phê duyệt

09:04  Admin thu hồi quyền approve của user-42 trong database

09:05  Cùng JWT được gửi lại:
       signature ✓   iss ✓   exp ✓   claim scope vẫn y nguyên
       -> Nếu chỉ tin JWT claims: VẪN CHO PHÉP

09:15  JWT hết hạn:
       exp không còn hợp lệ -> từ chối
```

Đây là rủi ro **stale authorization claims**: quyền thực tế đã thay đổi nhưng token độc lập vẫn mô tả snapshot cũ.

**Phân biệt:** JWT chữ ký hợp lệ không phải bug của Spring Security. Resource Server đang kiểm tra đúng thứ được giao: **claims đã ký**. Nếu yêu cầu của sản phẩm là “thay role phải có hiệu lực trước request kế tiếp”, thiết kế phải thêm nguồn quyết định **trạng thái hiện tại**.

### Trường hợp cần quan tâm

| Sự kiện | JWT cũ có thể tiếp tục? | Lý do |
| --- | --- | --- |
| Admin xóa role của user | Có, nếu token chứa role/scope cũ | Claims đã ký không đổi |
| User bị disable/lock | Có, nếu RS không kiểm tra account state | `exp`/signature vẫn đúng |
| User logout khỏi app | Có thể | Logout session/UI không revoke bearer token tự động |
| Refresh token bị thu hồi | Access token hiện tại vẫn có thể còn hiệu lực | Hai token có lifecycle khác nhau |
| Admin thu hồi **một** access token | Có, nếu RS không biết revocation event | JWT vẫn tự xác minh được |
| Khóa ký bị rotate bình thường | Có thể | Key cũ có thể vẫn được chấp nhận trong khoảng rollover |
| Key bị loại bỏ khẩn cấp | Nhiều JWT cùng key có thể bị từ chối | Biện pháp rất rộng, không tinh chỉnh theo user |
| Quyền ownership của tài nguyên thay đổi | Có thể | Token không thay dữ liệu ownership hiện tại |

**Sai lầm nguy hiểm:** “Đã xóa refresh token nên access token cũ lập tức vô hiệu”. Thu hồi refresh token chủ yếu **ngăn xin token mới**; để từ chối access token hiện tại cần thêm enforcement trên Resource Server/introspection hoặc chờ token expire.

## 4. “Tức thời” cần được định nghĩa theo hợp đồng

Trong hệ phân tán, từ “ngay lập tức” cần chuyển thành **SLA bảo mật đo được**:

- **Từ thời điểm nào?** Admin nhấn nút, transaction revoke commit, hay event được tất cả nodes xử lý?
- **Ở đâu?** Một instance Resource Server, mọi API gateway, mọi region, cache/CDN và worker service?
- **Với request nào?** Những request bắt đầu **sau** commit, hay cả request đã đi qua authorization trước commit?
- **Thời gian tối đa?** 0 ms lý tưởng, p99 dưới 1 giây, hay tối đa 30 giây?
- **Khi kho policy outage?** Từ chối mọi request nhạy cảm (fail closed) hay cho tiếp tục theo JWT (fail open)?
- **Khi cache còn dữ liệu cũ?** TTL tối đa bao nhiêu? Có event invalidation/revision?
- **Với side effects đã thực thi?** Không thể hoàn tác một chuyển tiền đã hoàn thành bằng cách thu hồi token sau đó.

Khi nhu cầu là **không có request mới nào sau commit được phê duyệt bằng quyền cũ**, bạn cần đọc từ một nguồn trạng thái có **đảm bảo consistency đủ mạnh**, không cache kết quả cho phép quá lâu và định nghĩa rõ in-flight requests. JWT tự chứa **không tự cung cấp thuộc tính này**.

Trong thực tế, một hệ thống có thể chấp nhận quyền cũ tồn tại thêm 5 phút cho tác vụ đọc báo cáo công khai, nhưng **không** cho phép điều đó với approve payment hoặc cấp quyền quản trị. Áp dụng mức độ kiểm soát theo rủi ro từng endpoint.

## 5. Các chiến lược thu hồi: so sánh đầy đủ

| Chiến lược | Có check trạng thái mới mỗi request? | Độ trễ thu hồi | Ưu/nhược điểm |
| --- | --- | --- | --- |
| JWT với TTL ngắn | Không | Cho đến hết `exp` (cộng skew/policy) | Dễ scale; không có tức thời thật |
| Chặn cấp refresh token mới | Không đối với access token cũ | Access token cũ sống tới expiry | Giảm lâu dài; không giải quyết ngay |
| Denylist theo `iss+jti` | Có nếu check mỗi request | Theo store visibility và lookup | Thu hồi chọn lọc; thêm state/latency |
| Denylist theo token digest | Có nếu check mỗi request | Theo store visibility | Hữu ích khi không có `jti`; cần giữ digest an toàn |
| Per-user `authz_version` | Có nếu RS tra version hiện hành | Theo consistency/version lookup | Thu hồi hàng loạt quyền cũ; vẫn stateful |
| Per-user `not_before`/revokedAfter | Có nếu tra thời điểm cutoff | Theo store consistency, clock skew | Có thể vô hiệu nhiều tokens; cẩn thận độ phân giải thời gian |
| Resource ownership/policy DB check | Có tại business operation | Theo freshness của dữ liệu | Phù hợp quyền theo resource; tăng DB/PDP load |
| Opaque token introspection | Có nếu không cache quá lâu | Theo OP/introspection phản hồi | Thu hồi tập trung; thêm network/availability |
| JWT qua introspection | Có nếu OP hỗ trợ | Theo OP phản hồi | Giữ JWT format nhưng validation chuyển sang online |
| Token event push + cache invalidation | Có/không tùy cache design | Event propagation + cache TTL | Rất nhanh nhưng không bảo đảm tức thời tuyệt đối |
| Ký token bằng key mới và hủy key cũ | Thường ở JWT key validation | Phụ thuộc key cache/rotation | Rất rộng, ảnh hưởng nhiều tokens |
| Central Policy Decision Point | Có theo kiến trúc | Theo consistency/PDP response | Phù hợp hành động nhạy cảm; tăng latency & ops |

**Không có “một kích thước cho mọi ứng dụng”.** Có thể dùng token ngắn cho endpoints thông thường và thêm central authorization check cho giao dịch rủi ro cao.

## 6. Chiến lược A — Access token ngắn hạn

Giảm `exp` từ một giờ xuống 5–15 phút sẽ làm cửa sổ sử dụng token cũ ngắn hơn. Ví dụ:

```text
Token A được cấp 12:00, exp=12:05
Role bị xóa 12:01
Không check revocation -> token vẫn có thể được chấp nhận đến 12:05
```

**Ưu điểm:**
- Resource Server chỉ verify chữ ký/time/audience, không cần gọi database mỗi request.
- Hạn chế mức độ thiệt hại của token bị lộ hoặc claim stale.
- Dễ scale qua nhiều nodes.

**Giới hạn:**
- Không bảo đảm quyền thay đổi có hiệu lực tức thì.
- Giảm TTL quá mức làm tăng tải cấp token/refresh, có thể ảnh hưởng UX và availability.
- Clock skew/leeway có thể nới giới hạn chấp nhận `exp` đôi chút.
- Refresh token còn hoạt động có thể cấp token mới nếu Authorization Server không áp policy mới; phải kiểm soát refresh.

**Kết luận:** TTL ngắn là biện pháp giảm rủi ro, **không phải giải pháp đủ** khi sản phẩm yêu cầu “admin revoke → request kế tiếp bị từ chối”.

## 7. Chiến lược B — Denylist theo `jti` hoặc token digest

`jti` (JWT ID) là claim định danh một token. Với access token có `jti` độc nhất đủ ngẫu nhiên do Authorization Server cấp, bạn có thể lưu trạng thái **revoked** trong Redis/database dùng chung:

```text
POST /revoke (ở dịch vụ có thẩm quyền)
    |
    v
Xác thực + authorize thao tác revoke
    |
    v
Lưu revoked(issuer, jti) đến ít nhất exp + allowed skew
    |
    v
Mọi Resource Server trên mọi node:
    xác minh JWT -> tra revoked(iss,jti)
          |
        true --> 401 invalid_token
        false -> tiếp tục authorize theo scope/resource policy
```

### Đừng lưu raw bearer token nếu không cần

Khóa denylist có thể là `issuer + jti` hoặc một digest được tính an toàn từ raw token, tùy threat model. `jti` cần đủ uniqueness, không để client tự đặt; nếu hệ thống multi-tenant/multi-issuer, **scope theo issuer/audience/tenant** đúng chính sách. Lưu raw JWT có thể làm lộ claims/credential khi store bị rò rỉ.

Nếu issuer **không** cấp `jti`, không nên tự dùng token value làm khóa database/log. Có thể lưu hash/digest/HMAC ổn định của token, nhưng phải quản lý salt/key thích hợp, collision/format và retention.

### Giới hạn quan trọng

- Store phải **chia sẻ giữa tất cả Resource Servers**; `ConcurrentHashMap` chỉ phù hợp demo.
- Nếu revocation được viết vào replica nhưng các readers ở region khác chưa thấy, có cửa sổ chấp nhận token cũ. Chọn consistency theo SLA.
- TTL của denylist nên kéo dài đến khi token **không thể được chấp nhận nữa**, thường `exp + clock skew + propagation margin`. Xóa quá sớm có thể vô tình làm token hợp lệ trở lại trong vùng chấp nhận skew.
- Có thể cần audit event người thu hồi/quyền thu hồi mà không ghi raw token.
- Chỉ check `jti` theo token hiện tại; nếu user có 20 token thì muốn “revoke toàn account” cần biết tất cả `jti` hoặc dùng user-level version.
- Không dùng cache kết quả `not revoked` quá lâu nếu muốn latency revoke thấp. Negative cache có thể khiến node vẫn cho phép trong TTL.
- Nếu store không truy cập được, quyết định fail-open/fail-closed **có chủ đích**. Đối với hành động nhạy cảm, fail closed thường là lựa chọn an toàn hơn.
- Những request đã được authorize trước khi admin revoke có thể vẫn đang thực thi. Bảo vệ transaction/side-effect bằng policy check gần thời điểm commit khi cần.

## 8. Chiến lược C — Version quyền, account state và resource authorization

### 8.1. `authz_version`

Authorization Server nhúng version quyền vào token:

```json
{
  "sub": "user-42",
  "aud": ["inventory-api"],
  "authz_version": 17,
  "scope": "reports:approve"
}
```

Database/quyết định trạng thái hiện hành:

```text
current authz_version(user-42) = 18
```

Resource Server kiểm tra:
1. JWT signature/iss/exp/aud hợp lệ.
2. Đọc user/tenant-level version hiện hành từ store có freshness phù hợp.
3. Chỉ cho phép nếu `token.authz_version == current_version` (hoặc áp rule đã được thiết kế).
4. Nếu khác, từ chối token và yêu cầu lấy token mới theo policy.

Khi admin xóa role, tăng version trong cùng transaction cập nhật permission. **Toàn bộ JWT mang version cũ** bị từ chối mà không cần lưu từng `jti`.

**Điều kiện:** Version phải được kiểm tra **ở Resource Server trên mỗi request nhạy cảm hoặc với freshness bound rõ**. Nếu RS chỉ đọc version một lần lúc login rồi cache vô hạn, stale claim vẫn là vấn đề cũ.

Dùng key theo `issuer + subject + tenant` nếu multi-tenant; không trộn user IDs giữa tenants. Một user có quyền khác nhau trên từng resource có thể cần version theo resource/tenant/policy chứ không chỉ global user version.

### 8.2. `iat` và thời điểm thu hồi

Một biến thể lưu `tokens_valid_after` hoặc `revoked_before` của user. Access token có `iat` trước cutoff bị từ chối.

Rủi ro:
- `iat` có độ phân giải giây, nhiều token có thể cùng mốc.
- Đồng hồ phân tán/clock skew, thay đổi vào giữa giây và hành vi so sánh `<`/`<=` có thể gây sai.
- Các issuer khác nhau có semantics riêng, không mặc nhiên đồng bộ clock.
- Replay từ token trước cutoff phải được chặn trên mọi node.

Version số nguyên tăng dần có thể dễ kiểm toán hơn timestamp, nhưng cả hai đều yêu cầu **online state check**.

### 8.3. Quyền theo resource không nên chỉ nằm trong JWT

Ví dụ token chứa `scope=invoice:approve` không đồng nghĩa user được approve **mọi hóa đơn**. Business logic còn phải kiểm tra:
- Invoice thuộc tenant nào?
- User có quyền trên invoice/project hiện tại không?
- Invoice đã bị khóa/hủy/duyệt chưa?
- Policy có yêu cầu separation of duties không?
- Có xung đột quyền hoặc trạng thái tài khoản vừa đổi không?

JWT scope là **quyền hành động tổng quát**; resource ownership/ABAC thường đòi hỏi truy cập dữ liệu hiện hành. Nếu thao tác cực kỳ nhạy cảm, kiểm tra lại policy **trong cùng transaction nghiệp vụ** hoặc tại boundary gần side effect hơn.

## 9. Chiến lược D — Opaque token introspection và JWT introspection

**OAuth 2.0 Token Introspection (RFC 7662)** cho phép Resource Server hỏi Authorization Server/Introspection Endpoint một access token **có active hay không** và lấy thông tin liên quan. Opaque token thường là một chuỗi không tự giải mã được, nhưng **cơ chế introspection cũng có thể áp dụng cho JWT** nếu OP/Authorization Server hỗ trợ.

Trong Spring Security reactive có OAuth2 Resource Server opaque token support. Cấu hình mẫu:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Đây là **phương án thay thế cho demo JWT decoder phần 11**, không ghép đồng thời hai cấu hình rồi suy đoán chain nào được chọn.

Nếu dùng resource-server opaque token flow:
1. Resource Server nhận Bearer token.
2. `ReactiveOpaqueTokenIntrospector` gọi endpoint với client credentials hợp lệ.
3. OP trả `active=true/false` và claims/metadata.
4. Spring Security chuyển active token thành Authentication/authorities.
5. Resource Server tiếp tục authorization.

**Lợi ích:** OP có thể trả `active=false` ngay khi token bị revoke, nếu hệ thống OP có semantics/consistency đáp ứng yêu cầu và RS **không cache introspection result quá lâu**.

**Đổi lại:** Mỗi request hoặc lần cache miss có thể tạo network call, gây latency, tải OP và điểm phụ thuộc availability. Circuit breaker, timeout, connection pools, caching, outage policy và metrics phải được thiết kế.

### Introspection với JWT

Khi API yêu cầu trạng thái thu hồi trung tâm nhưng Authorization Server vẫn phát JWT, bạn có thể chọn **introspection cho chính JWT** thay vì local signature-only validation. Khi đó JWT format vẫn là JWT, nhưng phương pháp xác nhận acceptance là online.

**Không nhầm:** “Token được ký và có `exp`” không có nghĩa endpoint introspection sẽ phản hồi active nếu nó đã bị revoke; **OP phải thực sự hỗ trợ revocation semantics**. Kiểm tra provider docs và test thực.

### RFC 7009 khác RFC 7662

- **RFC 7009 — Token Revocation:** client/đơn vị có quyền yêu cầu AS thu hồi token; chi tiết hiệu lực và ảnh hưởng token liên quan tùy AS.
- **RFC 7662 — Token Introspection:** Resource Server hỏi AS xem token hiện **active** hay không.
- **JWT local validation:** chỉ kiểm tra claims và chữ ký cục bộ, không tự hỏi AS về revocation.
- **OIDC Logout:** kết thúc session OP/RP, không tự bảo đảm mọi OAuth access token bị thu hồi.

## 10. Nguyên tắc thiết kế API Spring WebFlux

### 10.1. Authentication vs authorization

Trong Resource Server:
- Token invalid/expired/revoked → thường **401 Unauthorized** với Bearer challenge phù hợp.
- Token hợp lệ nhưng thiếu authority/scope → thường **403 Forbidden**.
- Token và scope hợp lệ nhưng resource không thuộc user → 403 hoặc 404 tùy API privacy policy, **không** mặc định 200.
- Cơ sở trạng thái revocation bị lỗi → request **không được tự động cho phép**; response có thể 5xx hoặc 401 generic theo cách hệ thống phân loại và log nội bộ, nhưng không trả chi tiết token/store.

Không dùng `onErrorResume(e -> Mono.just(jwt))` cho lookup revocation: nó biến database/Redis outage thành **fail open**.

### 10.2. Không blocking trên Netty event loop

Spring WebFlux dùng Reactor. Khi check Redis/database:
- Dùng reactive client `ReactiveRedisTemplate`, R2DBC hoặc WebClient tương ứng.
- Không gọi JDBC sync, `Thread.sleep`, `block()` trong `ReactiveJwtDecoder.decode(...)`.
- Nếu buộc tích hợp thư viện blocking, cô lập bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` có giới hạn, monitoring và timeout.
- Không tự `subscribe()` trong auth pipeline; trả `Mono<Jwt>` hoặc `Mono<Boolean>` cho Spring quản lý.
- Sử dụng timeout, retry thận trọng; retry vô hạn khi auth store outage có thể khiến request treo và khuếch đại DoS.

### 10.3. Phải xác minh token **trước** tra jti

Không tin `jti`, `sub`, `iss` đọc từ JWT chưa xác minh chữ ký. Nếu attacker có thể gửi token giả với `jti` tùy ý và kích hoạt lookup, họ có thể gây enumeration/tải store. Luồng đúng: **verify cryptographic claims trước → đọc claims đáng tin → kiểm tra state**.

### 10.4. Đừng chỉ dựa vào `jti` khi điều kiện là thu hồi toàn bộ quyền

Denylist một token cụ thể chỉ thu hồi token đó. Nếu user có token B, C hay token cho API khác, thay đổi quyền của user không tự ghi tất cả jti vào denylist. Với global permission change, cân nhắc user/tenant version, current state lookup hoặc introspection. Có thể kết hợp per-token denylist cho logout current token và authz version cho khóa tài khoản/quyền thay đổi.

## 11. Ví dụ chạy được: Java 17+, Spring Boot 3.3.5, WebFlux

Dự án minh họa **Resource Server JWT** có denylist với token ID. Yêu cầu:
- Authorization Server/IdP test cấp **signed JWT access token** có `iss`, `sub`, `aud=inventory-api`, `jti`, `exp`, `scope`.
- Resource Server nhận Bearer token, verify cryptographic validity rồi kiểm tra revocation.
- Endpoint `POST /api/token/revoke-current` cho một authenticated principal thu hồi **chính bearer token đó**, không cho arbitrary jti từ client.
- Sau khi endpoint trả 204 và revocation visible, request mới dùng **cùng token** bị từ chối.
- `GET /api/reports` cần `SCOPE_reports:read`; `GET /api/me` chỉ cần authentication.
- Denylist trong **bộ nhớ một JVM** chỉ dành cho demo; production bắt buộc store chia sẻ.

### 11.1. Cấu trúc dự án

```text
reactive-jwt-revocation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/jwtrevoke/
    │   │   ├── JwtRevocationApplication.java
    │   │   ├── ReactiveRevocationStore.java
    │   │   ├── InMemoryRevocationStore.java
    │   │   ├── RevocationAwareJwtDecoder.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/dev/example/jwtrevoke/
        ├── RevocationAwareJwtDecoderTests.java
        └── JwtApiHttpTests.java
```

### 11.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-jwt-revocation-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` kéo theo các thành phần cần thiết để Resource Server kiểm tra JWT JOSE theo dependency management của Boot. Không thêm `spring-boot-starter-web` để tránh Spring Boot chuyển sang Servlet/MVC khi mục tiêu là WebFlux.

### 11.3. `application.yml`

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

app:
  security:
    issuer-uri: ${JWT_ISSUER_URI}
    audience: inventory-api
```

Cần biến môi trường `JWT_ISSUER_URI` là **issuer URI thực của Authorization Server thử nghiệm** công bố OIDC/OAuth metadata và JWK Set. Trong ví dụ, decoder được khai báo `@Bean` với issuer này nên **có thể cần truy cập discovery endpoint lúc app khởi động**. Đây không phải một service sinh JWT giả; muốn E2E thực bạn phải có issuer phù hợp.

Đừng nhận JWT ký từ một issuer bất kỳ. Cấu hình trusted issuer/alg/audience phải do server quản lý; không lấy issuer từ request header/query do người dùng gửi.

### 11.4. Main class

`src/main/java/dev/example/jwtrevoke/JwtRevocationApplication.java`:

```java
package dev.example.jwtrevoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtRevocationApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtRevocationApplication.class, args);
    }
}
```

### 11.5. Hợp đồng ReactiveRevocationStore

`src/main/java/dev/example/jwtrevoke/ReactiveRevocationStore.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import reactor.core.publisher.Mono;

public interface ReactiveRevocationStore {

    Mono<Boolean> isRevoked(String issuer, String jti);

    Mono<Void> revoke(String issuer, String jti, Instant expiresAt);
}
```

Đây là **business abstraction**: Resource Server cần biết token có bị thu hồi hay không. Nó không phải Spring Security built-in interface. Production triển khai bằng reactive Redis/database hoặc một policy service với consistency phù hợp.

### 11.6. Store chỉ dành cho demo một JVM

`src/main/java/dev/example/jwtrevoke/InMemoryRevocationStore.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class InMemoryRevocationStore
        implements ReactiveRevocationStore {

    private record TokenKey(String issuer, String jti) {
    }

    private final ConcurrentHashMap<TokenKey, Instant> denied =
            new ConcurrentHashMap<>();

    @Override
    public Mono<Boolean> isRevoked(String issuer, String jti) {
        return Mono.fromSupplier(() -> {
            TokenKey key = new TokenKey(issuer, jti);
            Instant until = denied.get(key);

            if (until == null) {
                return false;
            }
            if (Instant.now().isAfter(until)) {
                denied.remove(key, until);
                return false;
            }
            return true;
        });
    }

    @Override
    public Mono<Void> revoke(
            String issuer, String jti, Instant expiresAt) {

        return Mono.fromRunnable(() -> {
            // Giữ deny entry thêm 120 giây sau exp:
            // demo margin cho clock skew/propagation.
            Instant until = expiresAt.plusSeconds(120);
            TokenKey key = new TokenKey(issuer, jti);
            denied.merge(key, until,
                    (oldUntil, newUntil) ->
                            oldUntil.isAfter(newUntil)
                                    ? oldUntil : newUntil);
        }).then();
    }
}
```

**Giải thích quan trọng:**
- Key là cặp `(issuer, jti)`, không dùng raw JWT.
- Entry giữ đến `exp + 120s` để tránh xóa quá sớm trong khoảng clock skew. **120 giây chỉ là tham số demo**, production tính theo accepted clock skew, propagation và policy thật.
- `Mono.fromSupplier`/`Mono.fromRunnable` không gọi I/O blocking: map in-memory truy cập nhanh.
- `ConcurrentHashMap` chỉ chia sẻ trong **một JVM**; restart làm mất entries và nhiều replicas không thấy nhau. **Không dùng triển khai này để cam kết logout/revocation production.**
- TTL purge ở đây là lazy khi lookup; một production store nên có expiry/TTL tự động, giới hạn memory và monitoring.
- Store luôn phát `Boolean`; một store production không được trả `Mono.empty()` âm thầm khi lookup thất bại.

### 11.7. Decoder thêm kiểm tra trạng thái **sau** xác minh JWT

`src/main/java/dev/example/jwtrevoke/RevocationAwareJwtDecoder.java`:

```java
package dev.example.jwtrevoke;

import java.net.URI;
import java.time.Instant;

import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

public final class RevocationAwareJwtDecoder
        implements ReactiveJwtDecoder {

    private final ReactiveJwtDecoder delegate;
    private final ReactiveRevocationStore store;
    private final String expectedAudience;

    public RevocationAwareJwtDecoder(
            ReactiveJwtDecoder delegate,
            ReactiveRevocationStore store,
            String expectedAudience) {
        this.delegate = delegate;
        this.store = store;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public Mono<Jwt> decode(String rawToken) {
        // Chỉ xử lý claims SAU delegate.decode xác minh chữ ký,
        // issuer và thời gian theo decoder đã cấu hình.
        return delegate.decode(rawToken)
                .flatMap(jwt -> validateCurrentState(jwt));
    }

    private Mono<Jwt> validateCurrentState(Jwt jwt) {
        if (!jwt.getAudience().contains(expectedAudience)) {
            return Mono.error(new BadJwtException(
                    "JWT audience is not accepted"));
        }

        URI issuer = jwt.getIssuer();
        String jti = jwt.getId();
        Instant expiresAt = jwt.getExpiresAt();

        if (issuer == null || jti == null || jti.isBlank()
                || expiresAt == null) {
            return Mono.error(new BadJwtException(
                    "Required token claims are missing"));
        }

        return store.isRevoked(issuer.toString(), jti)
                .flatMap(revoked -> Boolean.TRUE.equals(revoked)
                        ? Mono.<Jwt>error(new BadJwtException(
                                "Access token has been revoked"))
                        : Mono.just(jwt))
                // Không coi trạng thái không xác định là "not revoked".
                .switchIfEmpty(Mono.error(new BadJwtException(
                        "Revocation status unavailable")));
    }
}
```

Điểm cần chú ý:
1. `delegate.decode(rawToken)` do Spring Security JWT decoder thực hiện, phải xác minh **cryptographic signature + issuer + exp/nbf** theo trusted policy. Không tự parse base64 rồi tin `jti`.
2. Sau đó decoder kiểm tra `audience == inventory-api` và bắt buộc có `iss`, `jti`, `exp`. Đây là policy cụ thể của API demo, không phải bộ claims bắt buộc của mọi JWT hợp lệ.
3. `store.isRevoked(iss,jti)` được gọi **trên mỗi Bearer JWT request** đi qua decoder.
4. Nếu revoked, ném `BadJwtException`; Resource Server thường chuyển authentication failure thành **401** cho request mới.
5. Nếu store phát `Mono.empty()`, code fail closed thay vì cho qua. Nếu store phát error thật, error được truyền tiếp; không có `onErrorResume(... -> jwt)` biến outage thành allow.
6. Không log `rawToken`, raw claims hay error message chứa token. Error trả client cần generic.
7. Wrapper không tự giải quyết **thay đổi role của tất cả JWT của user**; nó chỉ thu hồi đúng các `jti` có trong store.
8. In-flight requests đã qua decoder trước revoke có thể tiếp tục. Nếu action cần pre-commit guarantee, phải kiểm tra policy gần transaction boundary.

**Tùy chọn khác:** Với yêu cầu chỉ thay role chứ không revoke từng token, triển khai kiểm tra `authz_version` trong wrapper hoặc business policy service; không cố tìm toàn bộ token của một user từ JWT nếu issuer không duy trì session/token index.

### 11.8. Spring Security chain

`src/main/java/dev/example/jwtrevoke/SecurityConfig.java`:

```java
package dev.example.jwtrevoke;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.issuer-uri}") String issuer,
            @Value("${app.security.audience}") String audience,
            ReactiveRevocationStore store) {

        ReactiveJwtDecoder verifiedDecoder =
                ReactiveJwtDecoders.fromIssuerLocation(issuer);

        return new RevocationAwareJwtDecoder(
                verifiedDecoder, store, audience);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Chỉ demo API stateless dùng Authorization: Bearer,
                // KHÔNG dùng cookie/browser session authentication.
                .csrf(csrf -> csrf.disable())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports:read")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST,
                                "/api/token/revoke-current")
                            .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

**Cảnh báo CSRF:** Đoạn `csrf.disable()` chỉ phù hợp cho **API stateless dùng Bearer token gửi rõ trong `Authorization` header, không dùng cookie/session tự động**. Nếu ứng dụng hỗn hợp browser/OIDC login/session hoặc nhận credentials tự động trong cookie, hãy giữ/bật CSRF và cấu hình riêng security chains phù hợp. Không copy disable này vào ứng dụng browser session chỉ để POST chạy.

`ReactiveJwtDecoders.fromIssuerLocation(issuer)` có thể truy cập issuer metadata để lấy JWK Set URI; app thật phải có issuer HTTPS tin cậy. Đừng thay decoder này bằng `Jwt.withTokenValue(...)` từ test trong production: builder test không xác minh signature.

### 11.9. Controller với endpoint thu hồi **chính token hiện tại**

`src/main/java/dev/example/jwtrevoke/DemoController.java`:

```java
package dev.example.jwtrevoke;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final ReactiveRevocationStore store;

    public DemoController(ReactiveRevocationStore store) {
        this.store = store;
    }

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports-read-ok");
    }

    @PostMapping("/api/token/revoke-current")
    public Mono<ResponseEntity<Void>> revokeCurrent(
            @AuthenticationPrincipal Jwt jwt) {

        return store.revoke(
                        jwt.getIssuer().toString(),
                        jwt.getId(),
                        jwt.getExpiresAt())
                .thenReturn(ResponseEntity
                        .status(HttpStatus.NO_CONTENT)
                        .<Void>build());
    }
}
```

**Scope của chức năng revoke demo:** Bearer JWT hiện tại đã qua authentication và có `jti`; caller chỉ có thể yêu cầu thu hồi **chính token đó**. Client **không** được gửi arbitrary `jti`, user ID hay raw token khác để tự xóa quyền của người khác.

HTTP 204 chỉ chứng minh **store đã hoàn thành ghi entry trong quá trình request**. Đối với store production, định nghĩa độ bền ghi và visibility giữa các replicas; không tự hứa tất cả nodes đã thấy ngay. Sau revoke, client không nên tái sử dụng token; app có thể xóa token khỏi memory/storage theo flow phù hợp.

Với dữ liệu nghiệp vụ thật, không expose token ID, raw claims hoặc permissions không cần thiết trong `/api/me`. Trả DTO đã allowlist field.

## 12. Chạy app với Authorization Server thử nghiệm

Bạn cần JWT được cấp bởi **issuer thử nghiệm** tương ứng `JWT_ISSUER_URI` và chứa claims:

- `iss` đúng issuer.
- `aud` chứa `inventory-api`.
- `jti` unique và `exp` tương lai.
- `sub` là subject.
- `scope` có `reports:read` khi muốn GET /api/reports trả 200.
- Signed algorithm/key được Resource Server tin qua issuer/JWK metadata.

**Không thể tạo JWT hợp lệ chỉ bằng cách sửa chuỗi payload ở trên:** phải được Authorization Server ký bằng private key hợp lệ và cung cấp JWKS có public key tương ứng.

Đặt biến môi trường bằng secret/config management của môi trường bạn đang dùng rồi chạy:

```bash
gradle bootRun
```

Nếu dùng Gradle Wrapper, chạy `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Dùng HTTPS trong production. Không chép access token thật vào shell history, URL query hoặc hỗ trợ chat.

### 12.1. Thử với cURL — không in token thật

Trong bài lab, đặt một biến môi trường tạm cho test token từ issuer (ví dụ `ACCESS_TOKEN`), tránh in giá trị ra terminal/log. Các lệnh dưới đây giả định biến đã được cấp an toàn:

```bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/api/me

curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me

curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports

curl -i -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/token/revoke-current

curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me
```

**Dự kiến khi token hợp lệ và store một JVM:**
1. `/public` không Bearer → 200, `public-ok`.
2. `/api/me` không Bearer → 401.
3. `/api/me` với token chưa revoked → 200, JSON subject.
4. `/api/reports` cần scope `reports:read`; nếu có → 200, nếu thiếu → 403.
5. POST `/api/token/revoke-current` với token hợp lệ → **204 No Content**, ghi deny entry.
6. GET `/api/me` **lại với cùng token** → **401** (nếu store đã ghi/đọc entry).

Kết quả trên là **kỳ vọng theo code**, không phải báo cáo đã chạy với issuer thật. Trong production, một client đã revoke nên bỏ token và thực hiện flow login/refresh theo policy; test ở đây gửi lại token chỉ để xác nhận denylist hoạt động.

### 12.2. Vì sao không đưa token vào URL?

Bearer token là credential: bất kỳ ai sở hữu nó có thể thử dùng nó trong thời hạn và phạm vi cho phép. Query param dễ lọt vào browser history, access logs, Referrer, analytics và monitor. Dùng `Authorization: Bearer` trên TLS; redaction ở gateway/logging.

## 13. Unit tests cho RevocationAwareJwtDecoder

Test **không dùng Authorization Server thật**. Ta cung cấp một **fake delegate** trả một `Jwt` đã dựng để kiểm thử **logic policy sau decode**, không giả vờ rằng fake delegate đã xác minh chữ ký. Để kiểm thử signature/issuer/time thật phải có signed test JWT + public keys/JWKS test.

Tệp `src/test/java/dev/example/jwtrevoke/RevocationAwareJwtDecoderTests.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RevocationAwareJwtDecoderTests {

    private static final String ISSUER =
            "https://issuer.example.test";

    private Jwt jwt(String jti, String audience) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("signed-jwt-fixture")
                .header("alg", "RS256")
                .issuer(ISSUER)
                .subject("alice")
                .audience(List.of(audience))
                .jti(jti)
                .issuedAt(now.minusSeconds(2))
                .expiresAt(now.plusSeconds(300))
                .claim("scope", "reports:read")
                .build();
    }

    private RevocationAwareJwtDecoder decoder(
            Jwt fixture, InMemoryRevocationStore store) {

        // Fake delegate: đã giả lập bước crypto verification.
        ReactiveJwtDecoder verifiedFake =
                ignoredToken -> Mono.just(fixture);

        return new RevocationAwareJwtDecoder(
                verifiedFake, store, "inventory-api");
    }

    @Test
    void allowsValidNonRevokedToken() {
        var store = new InMemoryRevocationStore();
        Jwt fixture = jwt("jti-101", "inventory-api");

        StepVerifier.create(
                decoder(fixture, store).decode("test-token"))
                .assertNext(value ->
                        assertEquals("jti-101", value.getId()))
                .verifyComplete();
    }

    @Test
    void rejectsSameTokenAfterRevocation() {
        var store = new InMemoryRevocationStore();
        Jwt fixture = jwt("jti-102", "inventory-api");
        var target = decoder(fixture, store);

        StepVerifier.create(target.decode("test-token"))
                .expectNextCount(1)
                .verifyComplete();

        StepVerifier.create(store.revoke(
                ISSUER, fixture.getId(), fixture.getExpiresAt()))
                .verifyComplete();

        StepVerifier.create(target.decode("test-token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void doesNotRevokeOtherJtiForSameIssuer() {
        var store = new InMemoryRevocationStore();
        Jwt revoked = jwt("jti-103", "inventory-api");
        Jwt other = jwt("jti-104", "inventory-api");

        StepVerifier.create(store.revoke(
                ISSUER, revoked.getId(), revoked.getExpiresAt()))
                .verifyComplete();

        StepVerifier.create(decoder(other, store).decode("other"))
                .expectNextCount(1)
                .verifyComplete();
    }

    @Test
    void rejectsJwtForAnotherAudience() {
        var store = new InMemoryRevocationStore();
        Jwt anotherApi = jwt("jti-105", "payments-api");

        StepVerifier.create(
                decoder(anotherApi, store).decode("token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void rejectsTokenWithoutJti() {
        var store = new InMemoryRevocationStore();
        Instant now = Instant.now();

        Jwt missingJti = Jwt.withTokenValue("fixture")
                .header("alg", "RS256")
                .issuer(ISSUER)
                .subject("alice")
                .audience(List.of("inventory-api"))
                .expiresAt(now.plusSeconds(120))
                .build();

        StepVerifier.create(
                decoder(missingJti, store).decode("token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void rejectsWhenTrustedDelegateRejectsSignature() {
        var store = new InMemoryRevocationStore();
        ReactiveJwtDecoder badSignature =
                ignoredToken -> Mono.error(
                        new BadJwtException("Invalid signature"));

        var target = new RevocationAwareJwtDecoder(
                badSignature, store, "inventory-api");

        StepVerifier.create(target.decode("forged-token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void sameJtiUnderAnotherIssuerIsIndependent() {
        var store = new InMemoryRevocationStore();
        Jwt fixture = jwt("jti-106", "inventory-api");

        StepVerifier.create(store.revoke(
                "https://another-issuer.example.test",
                "jti-106", fixture.getExpiresAt()))
                .verifyComplete();

        StepVerifier.create(decoder(fixture, store).decode("token"))
                .expectNextCount(1)
                .verifyComplete();
    }
}
```

Dự kiến **7 test thành công**, không cần issuer mạng. Đây chỉ là test logic bổ sung sau bước decoding/crypto đã **được fake delegate mô phỏng**; nó **không xác minh** chữ ký JWT, issuer discovery, JWKS rotation hoặc access token do OP phát thật.

### Tại sao việc kiểm thử chữ ký cần bộ test khác?

Một JWT được dựng bằng `Jwt.withTokenValue(...)` không phải signed access token hợp lệ. Unit test giả lập decoder thành công giúp tập trung kiểm tra:
- `aud` có đúng API không?
- `jti` có bắt buộc không?
- Store đã bị revoke thì decode trả error chưa?
- Chỉ đúng jti/issuer bị từ chối chưa?
- Decoder delegate ném `BadJwtException` có bị nuốt hay không?

Còn cryptographic verification phải được kiểm thử bằng key fixtures/signed JWT với `NimbusReactiveJwtDecoder` và test issuer/JWKS, hoặc integration test với Authorization Server thử nghiệm. Không dùng `mockJwt()` để tuyên bố “đã kiểm chứng revocation”: mockJwt bypass đường decode theo thiết kế.

## 14. HTTP tests bằng WebTestClient — phân biệt mock với real decoder

Spring Security test cho phép giả lập `ReactiveJwtDecoder` để kiểm tra routing/authorization nhanh mà không cần issuer. Các HTTP tests dưới đây cố ý **mock decoder**, nên chỉ xác nhận 200/401/403 ở tầng HTTP. Nó **không** xác nhận revocation filter của `RevocationAwareJwtDecoder` đang được gọi, vì bean decoder đã bị mock.

Tệp `src/test/java/dev/example/jwtrevoke/JwtApiHttpTests.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@TestPropertySource(properties = {
        "app.security.issuer-uri=https://issuer.example.test",
        "app.security.audience=inventory-api"
})
class JwtApiHttpTests {

    @Autowired
    WebTestClient client;

    // MockBean hợp lệ trong Spring Boot 3.3.5; thay decoder @Bean,
    // KHÔNG chạy JWT signature verification hay revocation wrapper.
    @MockBean
    ReactiveJwtDecoder decoder;

    private Jwt jwt(String jti, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("mock-" + jti)
                .header("alg", "RS256")
                .issuer("https://issuer.example.test")
                .subject("alice")
                .audience(List.of("inventory-api"))
                .jti(jti)
                .issuedAt(now.minusSeconds(1))
                .expiresAt(now.plusSeconds(300))
                .claim("scope", scope)
                .build();
    }

    @BeforeEach
    void setup() {
        when(decoder.decode(anyString()))
                .thenReturn(Mono.error(
                        new BadJwtException("Invalid token")));

        when(decoder.decode("reader-token"))
                .thenReturn(Mono.just(
                        jwt("http-101", "reports:read")));

        when(decoder.decode("no-scope-token"))
                .thenReturn(Mono.just(
                        jwt("http-102", "profile:read")));
    }

    @Test
    void publicGetDoesNotNeedBearerToken() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateGetWithoutTokenIs401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validMockJwtCanReadOwnSubject() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void scopeAllowsReports() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("reports-read-ok");
    }

    @Test
    void missingScopeReturns403() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("no-scope-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void decoderRejectedTokenReturns401() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("invalid-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void revokeEndpointReturns204ForAuthenticatedRequest() {
        client.post().uri("/api/token/revoke-current")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isNoContent();
    }
}
```

Dự kiến **7 HTTP tests thành công** với Boot 3.3.5. Chúng kiểm tra mapping từ bearer Authentication tới status/authority và controller. **Không** có một assertion “revoke xong reader-token sẽ 401” trong suite này, vì mock decoder **vẫn trả một Jwt cho reader-token ở mọi lần gọi**. Điều đó sẽ là một test sai nếu được quảng cáo như kiểm thử revocation.

### Chạy tests

```bash
gradle test
```

Dự kiến tổng cộng **14 tests** (7 `StepVerifier` + 7 `WebTestClient`) chạy thành công. Đây là **kết quả kỳ vọng theo code**, không phải báo cáo đã chạy Gradle. Chạy trong IDE hoặc terminal của dự án thật và kiểm tra report test để xác nhận.

### Kiểm thử end-to-end revocation thật

Để chứng minh JWT đã được **cryptographically verified và bị revoke trên request thật**, cần thêm integration test:
1. Dùng một issuer/JWKS test có signed JWT chuẩn hoặc một private/public key fixture trong môi trường thử.
2. Giữ `RevocationAwareJwtDecoder` thật, **không mock decoder**.
3. Gửi GET /api/me với signed token valid → 200.
4. Gửi POST /api/token/revoke-current với cùng token → 204.
5. Gửi lại GET /api/me với **cùng signed token** → 401.
6. Gửi token khác của user/issuer phù hợp → outcome theo policy, không vô tình revoke tất cả.
7. Nếu có nhiều app instances, thực hiện request cuối tới **instance khác** và xác minh denylist shared store đã visible.
8. Simulate store timeout/outage và kiểm tra **không có fail-open**.

Đây là test còn cần thực hiện với môi trường/kho store phù hợp; không suy từ unit/mock tests rằng cluster production có immediate revocation.

## 15. Thay store một JVM bằng Redis/reactive DB ở production

Hợp đồng `ReactiveRevocationStore` không buộc phải đổi; phần implementation phải chuyển sang nguồn có thể được **tất cả nodes** nhìn thấy.

Một sơ đồ Redis:

```text
Admin/Auth Service ---- revoke(iss,jti) ----> Redis primary / durable store
                                                |
                         +----------------------+----------------+
                         |                                       |
                    RS instance A                           RS instance B
                    read revoked                            read revoked
                         |                                       |
                    deny token                               deny token
```

### TTL và key

- Key nên gồm issuer + jti (hoặc token digest có kiểm soát); tránh collision giữa issuer/tenant.
- TTL đến ít nhất `exp + accepted clock skew + propagation margin`.
- Các khóa Redis đặt prefix namespace và tránh chứa raw token/PII trong key/logs.
- Nếu Redis không đảm bảo durability theo SLA hoặc chạy read replicas có lag, không thể hứa revocation immediate global.
- Một revoke event phải idempotent; cùng token revoke nhiều lần không gây bất thường.
- Ghi/log audit event (ai, tại sao, policy) **không ghi raw bearer token**.
- TTL và size phải có monitoring; revoke list có thể lớn khi số lượng token cao.

### Caching và negative lookup

Nếu dùng local cache “not revoked” trong 30 giây, người dùng vừa bị revoke vẫn có thể truy cập trong 30 giây đó. Để đạt “effective before next authorized request” cần loại bỏ stale allow caches hoặc giới hạn TTL phù hợp, kết hợp push invalidation với consistency thật.

**Event-driven invalidation đơn lẻ không cung cấp strong guarantee:** một event có thể đến chậm, mất, xử lý lại hoặc không tới instance vừa thêm vào cluster. Cần fallback/sync/reconciliation và giới hạn cửa sổ stale.

### Outage policy

Chọn một trong các chính sách rõ:
- **Fail closed:** store unavailable → không cấp phép thao tác cần kiểm tra revocation; tăng false denies/availability cost nhưng hạn chế rủi ro security.
- **Fail open:** store unavailable → tạm tin JWT; giúp availability nhưng vô hiệu hóa mục tiêu immediate revocation trong outage.
- **Risk-tiered:** GET ít nhạy cảm có thể degrade theo policy, POST phê duyệt/giao dịch luôn yêu cầu fresh check.

Không triển khai fallback bằng một `onErrorResume` im lặng và sau đó tuyên bố “revoke instant”.

### Tối ưu chi phí

- TTL access token ngắn vừa đủ để denylist có thời gian lưu ngắn.
- Dùng per-user/tenant version cho các sự kiện thay đổi quyền hàng loạt.
- Tách check trạng thái theo độ nhạy endpoint thay vì thêm lookup nặng vào mọi route công khai.
- Sử dụng reactive drivers, connection pooling, timeout và bulkhead để giữ event loop lành mạnh.
- Kiểm soát consistency và độ trễ P95/P99; đo từ revoke commit đến request đầu tiên bị deny ở mọi region.

## 16. Thu hồi quyền theo user khác với thu hồi một token

Với ví dụ endpoint `/api/token/revoke-current`, chỉ token gọi endpoint bị đánh dấu revoked. Nếu một người dùng có token khác trên thiết bị khác, token đó **chưa** bị deny.

Khi admin xóa role `reports:approve`:
- Nếu có danh sách mọi active jtis của user: có thể revoke từng token, nhưng index phải đáng tin và đồng bộ.
- Nếu không có token index: dùng `authz_version` hoặc `tokens_valid_after` để invalidate một lớp token lớn, cần current-state check.
- Nếu quyền phụ thuộc invoice/project: check resource state/ABAC tại business layer, không chỉ role claim.
- Nếu có Authorization Server introspection đáng tin: RS có thể hỏi token active/permissions current, nhưng phải thống nhất semantics với OP.

Một hybrid pattern:

```text
1. JWT signature/issuer/aud/exp local validation
2. Denylist jti cho logout/revoke token cụ thể
3. User/tenant authz_version check cho role/lockout
4. Resource ownership/policy check gần transaction
5. Token TTL ngắn + refresh policy thích hợp
```

Mỗi lớp giải quyết một phạm vi rủi ro khác nhau; độ trễ và availability phải được tính toán. Không mặc định bước 2 đủ để xử lý mọi permission changes.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Admin xóa role nhưng JWT vẫn vào được | Scope trong JWT cũ vẫn được tin | Thêm current-policy/version check hoặc introspection |
| Logout rồi JWT vẫn gọi API được | Local logout/refresh token revoke không ảnh hưởng access token | Revoke access token hoặc chờ TTL |
| RS chấp nhận token của API khác | Thiếu `aud` validator | Validate expected audience |
| Role trong claim là ADMIN nhưng policy đòi SCOPE_ADMIN | Mapping roles/scopes sai | Kiểm tra `JwtGrantedAuthoritiesConverter` và claim source |
| Denylist làm việc trên node A nhưng B cho qua | In-memory store hoặc replication lag | Shared store + consistency test |
| Restart server khiến revoked token dùng lại | Entries chỉ nằm RAM | Durable/shared store có TTL |
| Token valid lại gần exp | Denylist entry hết hạn quá sớm so với clock skew | Retain đến exp + margin phù hợp |
| Store timeout gây 200 | Có fail-open fallback | Fail-closed trên API nhạy cảm |
| Response 403 thay vì 401 | Token đã authenticated nhưng thiếu authority | Phân biệt authentication vs authorization |
| Resource Server event loop chậm | Sync DB/blocking call trong decoder | Reactive driver hoặc boundedElastic có kiểm soát |
| `jti` trống khiến revoke không hiệu lực | AS không cấp jti hoặc RS không reject | Bắt buộc jti theo contract hoặc digest strategy |
| `mockJwt()` test PASS nhưng production revoke fail | Mock bypass decoder | Thêm signed-token integration test |
| Access token vẫn hiệu lực sau RFC 7009 revoke refresh | Access token không tự bị revoke | Kiểm tra AS policy + introspection/denylist |
| JWT JWKS key rotation làm mọi user logout | Rotate/delete keys không phải per-user revoke | Chọn strategy đúng granularity |
| Permissions stale qua local cache | Cache authz_version/not revoked quá lâu | Invalidation + bounded freshness |
| User “disabled” nhưng JWT vẫn được cho | RS không kiểm tra current user state | User state/version/introspection |
| Claims lộ PII trong logs | Log full JWT/Authorization | Redact credentials, không đưa PII vào token |
| Race revoke vs transaction | Request đã qua check trước commit revoke | Enforcement gần side effect, consistency/locking khi cần |

## 18. Checklist review production

1. JWT verifier dùng issuer/JWKS/algorithm được tin cậy, không chấp nhận `alg=none` hoặc keys từ token chưa xác thực.
2. `iss`, `exp`, `nbf` và `aud` được validate; token type/scope theo API contract.
3. Authorization phân biệt user role/scope với quyền trên resource/tenant.
4. Đã định nghĩa **revocation SLA** từ commit đến mọi node nhìn thấy.
5. Token TTL phù hợp threat model, không gọi nó là instant revoke.
6. Với revoke một token, `jti` là ID độc nhất đủ random hoặc có digest strategy.
7. Denylist không lưu raw token; TTL bao gồm accepted clock skew.
8. Store chia sẻ mọi replicas/regions; kiểm tra consistency và durability.
9. Không cache “not revoked” vượt cửa sổ cho phép.
10. Store outage policy được định nghĩa; không âm thầm fail-open.
11. Lock account, role change, tenant removal có **per-user/resource policy check**, không chỉ denylist một jti.
12. Access token và refresh token revocation được xử lý riêng theo OP policy.
13. Bearer token chỉ truyền qua HTTPS/header và được redact khỏi logs/URLs/APM.
14. Reactive code không dùng `block()` trong event loop.
15. 401 cho invalid/revoked token; 403 cho valid token thiếu scope; error response không làm lộ nguyên nhân bí mật.
16. Unit tests fake decoder được phân biệt rõ với signed-token cryptographic tests.
17. HTTP tests cover 200/401/403 và CSRF chính xác theo client authentication model.
18. Đã test old token sau revoke ở instance khác và sau restart/hạ tầng failover.
19. In-flight requests/side effects được xét trong threat model.
20. Rollout có metrics: revoke lag, store latency, error rate, p95/p99, cache hit/staleness.
21. IDP/Authorization Server policies về token lifetime/introspection/revocation được xác nhận bằng provider docs.
22. Có phương án incident cho token leakage/key compromise và privacy của security logs.

## 19. Câu hỏi tự kiểm tra

**1. Vì sao JWT self-contained có thể vẫn dùng sau khi role bị thu hồi?**  
Vì token chứa snapshot claims đã được ký; verify signature và exp không tự truy vấn quyền hiện tại.

**2. JWT có `exp` 5 phút có phải revoke tức thời không?**  
Không. Nó chỉ thu hẹp thời gian token cũ có thể được chấp nhận.

**3. Xóa refresh token có ngăn access token cũ ngay không?**  
Không mặc định; access token còn hiệu lực cần enforcement riêng.

**4. 401 khác 403 thế nào?**  
401 cho authentication token invalid/revoked/expired; 403 cho principal đã xác thực nhưng thiếu quyền.

**5. Denylist theo `jti` giải quyết phạm vi nào?**  
Thu hồi **token cụ thể** đã biết ID, nếu mọi Resource Server kiểm tra shared store với freshness phù hợp.

**6. Vì sao phải lưu denylist tới `exp+clockSkew`?**  
Để tránh xóa entry trong khi verifier còn chấp nhận token do leeway/skew.

**7. `authz_version` giải quyết trường hợp nào?**  
Cho phép invalidate tất cả token mang version cũ khi quyền của user/tenant bị cập nhật, nếu RS tra version mới.

**8. Nếu local cache `authz_version` 60 giây, quyền có “tức thời” không?**  
Không; cache có thể cho phép quyền cũ tới 60 giây nếu không được invalidated chắc chắn.

**9. Introspection chỉ dùng được với opaque token không?**  
Không. Spring Security có thể introspect cả token định dạng JWT khi Authorization Server hỗ trợ; phương pháp validation là online.

**10. Revocation RFC 7009 có tự động khiến Resource Server JWT local decoder biết token revoked không?**  
Không. RS cần state lookup/introspection hoặc một cách nhận thông tin mới.

**11. Tại sao không check `jti` trước chữ ký?**  
Vì claims chưa xác minh có thể bị giả mạo, gây wrong decisions và lookup abuse.

**12. `@AuthenticationPrincipal Jwt` trong controller có phải nguồn permission cuối cùng không?**  
Không. Jwt chứa claims đã xác minh nhưng business authorization có thể cần current user/resource state.

**13. `ConcurrentHashMap` denylist dùng production multi-node được không?**  
Không. Restart và các nodes khác sẽ mất/không thấy entries.

**14. Nếu Redis outage, trả 200 theo claims JWT có an toàn cho approve payment không?**  
Thông thường không nếu contract cần revoke ngay; phải thiết kế fail-closed/risk policy.

**15. `mockJwt()` test có kiểm chứng decoder cryptographic signature không?**  
Không, nó giả lập authentication, phù hợp test authorization nhưng không chứng minh revocation pipeline.

**16. Token bị revoke sau khi request bắt đầu có thể đã gây side effect không?**  
Có thể, nếu request đã vượt authorization; cần policy enforcement gần transaction commit khi yêu cầu nghiêm ngặt.

**17. JWT signature “đúng” chứng minh gì?**  
Claims không bị thay đổi kể từ khi được issuer/key được tin ký; không chứng minh role/account hiện tại.

**18. Khi API có nhiều tenants, cần chú ý gì?**  
Key state và claims theo issuer/subject/tenant/resource; không trộn danh tính hoặc permission giữa tenants.

### Bài tập thực hành

1. Chạy `RevocationAwareJwtDecoderTests` và diễn giải tại sao sau `store.revoke` cùng `jti` bị reject nhưng `jti` khác vẫn được chấp nhận.
2. Viết test cho store trả `Mono.empty()` và xác nhận wrapper không biến trạng thái không rõ thành allow.
3. Thêm custom claim `authz_version` và một `ReactiveUserVersionStore` giả; test version trong token thấp hơn version hiện tại bị deny.
4. Chuyển denylist demo sang Redis dùng reactive driver và TTL = exp + margin; test hai instances đọc cùng entry.
5. Mô phỏng store outage; xác minh không có `onErrorResume` khiến request nhạy cảm được accept.
6. Dùng một authorization server test phát JWT với `aud` sai; xác nhận decoder từ chối trước authorization.
7. Tạo signed test JWT/JWKS fixture và integration test thật với initial 200 → POST revoke 204 → same token 401.
8. Viết HTTP test cho valid token thiếu `reports:read` và phân biệt 403 với revoked 401.
9. Giả lập user bị disable trong database, so kết quả khi chỉ dùng local JWT với khi dùng current state check.
10. So sánh 5 phút TTL và 30 giây introspection cache: mức stale tối đa từng phương án là gì?
11. Kiểm thử khi revoke và business write chạy đồng thời; đề xuất check policy ở transaction boundary.
12. Viết policy cho ba mức: đọc public, đọc private, approve payment, với SLA revoke phù hợp.
13. Kiểm tra log/gateway đã redact `Authorization`, token value và raw claims.
14. Giải thích tại sao ký JWT bằng key mới và xóa key cũ là thao tác rộng, không thích hợp thay denylist từng token.

## 20. Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): xác minh chữ ký, issuer/exp/nbf, `ReactiveJwtDecoder`, scope mapping và validators.
- [Spring Security — Reactive Opaque Token Introspection](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`, active flag, khả năng introspection cả JWT.
- [Spring Security — Reactive OAuth2 Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` và giới hạn của mock authentication.
- [Spring Security 6.3 Jwt.Builder API](https://docs.spring.io/spring-security/site/docs/6.3.8-SNAPSHOT/api/org/springframework/security/oauth2/jwt/Jwt.Builder.html): `jti`, `audience`, `issuer`, `expiresAt` trong fixtures.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT registered claims `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thuật toán, validation và các lỗ hổng JWT cần tránh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): cấu trúc và yêu cầu cho JWT access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation semantics.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh `active` và metadata tại AS.
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): denylist, token storage và revocation considerations.
- [Spring Security — Reactive WebFlux](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` và reactive HTTP security.

**Ghi nhớ:** **JWT self-contained mang một snapshot quyền đã ký; chữ ký và `exp` hợp lệ không chứng minh quyền hiện tại chưa bị thu hồi.** Khi cần có hiệu lực ngay trên mọi Resource Server, phải bổ sung **state check có consistency phù hợp** (denylist `jti`, `authz_version`, resource authorization, introspection/PDP), thiết kế TTL/caches/outage và kiểm thử từ revoke commit đến request mới. TTL ngắn hữu ích nhưng **không đồng nghĩa thu hồi tức thời**.