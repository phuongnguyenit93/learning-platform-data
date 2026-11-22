# Thay đổi quyền khi session hoặc access token còn hiệu lực trong Spring Security

## 1. Tình huống mở đầu: admin thu hồi quyền, người dùng vẫn truy cập được

Alice đăng nhập vào ứng dụng quản trị báo cáo lúc 09:00 và được quyền `reports:read`. Hệ thống lưu `Authentication` vào HTTP session, hoặc Authorization Server cấp access token có scope `reports:read`.

Lúc 09:10, quản trị viên thu hồi quyền đọc của Alice. Nhưng HTTP session vẫn tồn tại và JWT access token chưa hết hạn lúc 10:00.

Nếu endpoint chỉ kiểm tra authority đã được chụp lúc đăng nhập hoặc lúc cấp token:

```java
@PreAuthorize("hasAuthority('SCOPE_reports:read')")
public String readReport(long reportId) {
    return reportRepository.read(reportId);
}
```

thì **token JWT cũ vẫn có `SCOPE_reports:read`**. Tương tự, **session cũ có thể tiếp tục lưu `Authentication` mang quyền trước khi thu hồi**. Cập nhật một hàng trong bảng users/roles không tự động sửa mọi session và mọi access token đã phát hành.

Đây là vấn đề **thời điểm có hiệu lực của thay đổi quyền** (*permission change propagation*), không chỉ là câu chuyện “đăng nhập thành công hay chưa”.

Bài Knowledge thuộc nhóm **Quyền từ OAuth2**, mục **Thay đổi quyền khi session hoặc access token còn hiệu lực**, module *Spring Security – authorization*.

Kết thúc bài, bạn sẽ:

1. Phân biệt **session đang sống**, **JWT access token đang sống**, **opaque access token**, **refresh token** và quyền trong database.
2. Giải thích vì sao thay đổi role/scope trên Authorization Server hoặc database **không tự sửa** quyền đã đóng gói trong session/JWT.
3. Lựa chọn giữa **chờ hết hạn**, **thu hồi session**, **token revocation**, **introspection**, **denylist**, **policy version/epoch** và **live authorization**.
4. Thiết kế được mục tiêu về **độ trễ thu hồi quyền**, xác định nơi nào cần đồng bộ ngay và nơi nào cho phép độ trễ.
5. Cấu hình Spring Security 6.5 / Spring Boot 3.5.x cho JWT Resource Server, method security và **kiểm tra phiên bản quyền hiện hành**.
6. Hiểu `SecurityContextRepository`, `HttpSession`, `SecurityContextHolder`, `SessionRegistry` và Spring Session khi cần làm mới hoặc thu hồi session.
7. Phân biệt HTTP `401` do token/session không xác thực với `403` do không đủ quyền và `404` để tránh lộ resource.
8. Chạy ví dụ **Java 17 chuẩn thư viện**, không cần Spring, có stdout xác định mô phỏng revoke/regrant.
9. Hiểu ví dụ Spring Boot **Servlet Resource Server** gồm JWT `authz_ver`, directory quyền, tenant-scoped service và MockMvc tests.
10. Kiểm thử lại cùng **access token chưa hết hạn** sau revoke và sau regrant.
11. Thiết kế cache, multi-node, refresh, long-running jobs, WebSocket/SSE và update DB để tránh stale authorization.
12. Tránh các “giải pháp” nguy hiểm: xóa cookie trên một máy, đổi khóa JWT đại trà, mặc định allow khi PDP lỗi, tin claims do client tự khai hoặc chỉ sửa nút trên frontend.

**Tư tưởng chính:** Identity/session/token chứng minh **ai đang gọi và thông tin grant đã được cấp vào thời điểm nào**. Quyền có còn hiệu lực **tại thời điểm thao tác hiện tại** là một câu hỏi khác. Với quyền dễ bị thu hồi hoặc thao tác nhạy cảm, cần một cơ chế kiểm tra **trạng thái quyền hiện hành** hoặc một phiên bản policy được kiểm soát.

---

## 2. Trước hết phải phân biệt năm “thứ còn hiệu lực”

| Thành phần | Được tạo khi nào? | Thông tin quyền thường ở đâu? | Sau khi admin đổi role? |
| --- | --- | --- | --- |
| HTTP session | Khi đăng nhập và tạo session | `SecurityContext` có `Authentication` | Có thể vẫn giữ authority cũ đến khi refresh/invalidate |
| JWT access token | Khi Authorization Server phát token | Scope/roles/permissions claims được ký | Nội dung JWT cũ **không tự thay đổi** |
| Opaque access token | Khi Authorization Server phát | Metadata trạng thái/scopes tại AS hoặc introspection service | Có thể thấy `active=false`/thông tin mới **nếu** introspection state cập nhật và không bị cache sai |
| Refresh token | Khi AS cấp offline/long-lived grant | Token dùng lấy access token mới | Revoke refresh **không đảm bảo** access token đã phát bị từ chối ngay |
| Policy/ACL/membership store | Khi admin đổi cấu hình quyền | Database, IAM, PDP hoặc directory | Có thể là **nguồn sự thật mới nhất**, nếu các thành phần thực sự truy vấn nó |

**Phân biệt authentication và authorization:**

- **Authentication:** Alice là ai, credential/token hợp lệ không?
- **Authorization:** Alice có được đọc report #101 của tenant T1 **bây giờ** không?
- **Token validity:** JWT signature/`iss`/`aud`/`exp` hợp lệ chưa chắc các grants bên trong vẫn được chấp nhận theo policy mới.
- **Data policy:** Scope `reports:read` không tự cho phép đọc report tenant khác hoặc document đã chuyển owner.

Ví dụ hai thời điểm:

```text
09:00  Authorization Server tạo JWT:
       sub=alice
       scope="reports:read"
       authz_ver=7
       exp=10:00

09:10  Admin thu hồi quyền READ của Alice:
       policy store grants={}
       authz_ver=8

09:11  Alice gọi GET /api/reports/101 bằng JWT cũ:
       JWT signature hợp lệ
       exp chưa hết
       scope vẫn là "reports:read"
       nhưng authz_ver=7 != current 8
```

Nếu Resource Server chỉ nhìn `JwtGrantedAuthoritiesConverter` -> `SCOPE_reports:read`, request có thể vượt qua kiểm tra scope. Nếu thêm **version check** hoặc **live grant lookup**, request bị từ chối.

**Không nhầm:** `authz_ver` chỉ là **claim tự thiết kế trong ví dụ**, không phải một claim OAuth2/JWT bắt buộc theo chuẩn. Cả Authorization Server lẫn Resource Server phải đồng thuận contract này.

---

## 3. HTTP session: cập nhật user/role không tự sửa `Authentication` đã lưu

Spring Security Servlet lưu/đọc `SecurityContext` bằng một `SecurityContextRepository`; triển khai phổ biến cho session là `HttpSessionSecurityContextRepository`.

Ở lần đăng nhập:

```text
Credentials -> AuthenticationManager
            -> Authentication(principal, authorities)
            -> SecurityContext
            -> SecurityContextRepository / HttpSession
            -> các request sau khôi phục Authentication này
```

Ví dụ snapshot ban đầu:

```text
Session ABC:
  principal = alice
  authorities = [ROLE_USER, REPORT_READ]
  authenticated = true
```

Admin sửa database:

```text
user_grants[alice] = [ROLE_USER]
```

**Session ABC không tự biết thay đổi này.** Nếu request sau khôi phục `Authentication` cũ và code chỉ kiểm tra `.hasAuthority("REPORT_READ")`, Alice có thể còn đọc được.

### 3.1. Có những phương án nào cho session?

**Phương án A — Buộc đăng nhập lại:** tìm các session của Alice, invalidate chúng. Request sau không có session hợp lệ, phải đăng nhập lại để tạo `Authentication` mới.

**Phương án B — Làm mới Authentication:** tải lại grants từ nguồn authoritative, tạo authentication mới **qua cơ chế đáng tin**, thay `SecurityContext` và lưu ngược vào `SecurityContextRepository`.

**Phương án C — Kiểm tra quyền động mỗi request:** session chỉ chứng minh identity; method/service truy vấn grant store/PDP để quyết định; không chỉ nhìn authorities snapshot.

**Phương án D — Session có `authzVersion`:** lưu phiên bản grant vào session lúc đăng nhập; mỗi request đối chiếu với phiên bản hiện hành. Nếu khác, deny/reauthenticate/refresh.

Các hệ thống rủi ro cao thường kết hợp A hoặc D với C cho thao tác nhạy cảm. Hệ thống chỉ có kiểm tra token/session validity mà không xét current grants phải chấp nhận **cửa sổ quyền cũ** cho đến lúc session kết thúc.

### 3.2. `SecurityContextHolderFilter` và explicit save

Trong Spring Security 6, cơ chế mặc định đọc `SecurityContext` từ repository, còn code **tự thay** context trong custom authentication flow phải có trách nhiệm **lưu** lại nếu muốn thay đổi tồn tại giữa requests.

Mảnh code minh họa khi đã có một `Authentication fresh` được xác minh:

```java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(fresh);
SecurityContextHolder.setContext(context);

// Cần repository phù hợp với SecurityFilterChain đang dùng.
securityContextRepository.saveContext(
    context, request, response
);
```

**Đây là mảnh tích hợp, không phải file độc lập:** `fresh`, `securityContextRepository`, `request`, `response` phải đến từ luồng xác thực hợp lệ. Không dùng:

```java
UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest, "ignored",
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

để tự tạo quyền mới từ input client. Việc refresh authorities phải dựa vào trusted identity + directory/authorization provider đã kiểm tra.

### 3.3. Invalidate một session không phải invalidate mọi session

Gọi:

```java
request.getSession(false).invalidate();
```

chỉ có thể invalidates **session gắn với request đó** nếu nó tồn tại; không tự thu hồi các session khác của Alice trên điện thoại, browser thứ hai hay các node khác.

Với nhiều thiết bị và nhiều instance, bạn cần:

- Registry hoặc session store chia sẻ.
- Ánh xạ principal/stable subject -> active session IDs.
- Quyền xóa/invalidate tất cả sessions liên quan.
- Invalidation propagation tới mọi node.
- Cách xử lý request **đã vào** trước thời điểm thu hồi.
- Audit ai đã revoke, lúc nào, nguyên nhân gì.

### 3.4. `SessionRegistry` và Spring Session

Mảnh ý tưởng với `SessionRegistry`:

```java
// MẢNH CODE; principal phải đúng object/identity
// mà SessionRegistry lưu; cấu hình concurrent
// session control/expiry filter phải hoạt động.
for (SessionInformation item :
        sessionRegistry.getAllSessions(principal, false)) {
    item.expireNow();
}
```

`expireNow()` đánh dấu session hết hạn trong registry; nó **không tự xóa mọi cookie hoặc ngắt tức thì mọi request đang chạy**. Cơ chế session expiry phải được cấu hình đúng để request kế tiếp bị chặn.

Với Spring Session, `FindByIndexNameSessionRepository` có thể hỗ trợ tìm sessions theo principal để xóa theo ID (khi cấu hình index phù hợp). Đây là phương án hữu ích cho hệ thống nhiều instance dùng Redis/JDBC session store; không có chuyện một lệnh xóa trong JVM tự đảm bảo mọi node đã cập nhật nếu backend/cache replication chưa đồng bộ.

### 3.5. Logout trên thiết bị đang dùng khác với revoke toàn bộ

`SecurityContextLogoutHandler` trong Spring Security mặc định xử lý invalidate HTTP session hiện tại và clear `SecurityContext`. `/logout` trong app session-based là tính năng quan trọng nhưng **không đồng nghĩa** đã revoke mọi OAuth2 access token mà người dùng có.

Nếu API khác nhận Bearer JWT không liên quan tới session cookie của app, JWT đó vẫn có thể được chấp nhận trừ khi có revocation/expiry/live policy riêng.

---

## 4. JWT access token: claim đã ký bất biến trong thời hạn token

Một JWT self-contained có payload:

```json
{
  "iss": "https://issuer.example.invalid/tenant",
  "sub": "alice",
  "aud": ["reports-api"],
  "scope": "reports:read",
  "authz_ver": 7,
  "iat": 1799996400,
  "exp": 1800000000,
  "jti": "token-abc-001"
}
```

Đây là **JSON mô tả claim**, không phải JWT đã ký. Giá trị thời gian chỉ minh họa, không mang ý nghĩa token đang hợp lệ tại ngày soạn bài.

Resource Server thường xác minh:

- Signature với key/algorithm được tin.
- `iss` thuộc issuer đáng tin.
- `aud` có audience dành cho API.
- `exp`/`nbf` theo thời gian và clock skew được cấu hình.
- Các claims khác theo validators trong ứng dụng.

Sau decode, `JwtGrantedAuthoritiesConverter` có thể tạo `SCOPE_reports:read` từ `scope="reports:read"`. Nếu quyền bị thu hồi ở database, claim scope đã ký trong JWT **không bị sửa** và `JwtDecoder` mặc định **không gọi IAM database mỗi request để hỏi role có còn hay không**.

### 4.1. “Token chưa hết hạn” không có nghĩa “quyền còn hiệu lực”

Ba kiểm tra khác nhau:

```text
JWT.validSignatureAndTime(token)     -> true
JWT.scopeContains("reports:read")    -> true
CURRENT_POLICY.allows(alice, report) -> false
```

Một authorization decision an toàn cho resource nhạy cảm:

```text
ALLOW =
  JWT được xác minh đúng issuer/audience/thời hạn
  AND granted scope đủ cho action
  AND account hiện tại còn enabled
  AND authz version/epoch còn được chấp nhận
  AND tenant membership/ACL/resource policy cho phép
```

Những điều kiện này có thể do nhiều thành phần thực hiện, nhưng **không được tự bỏ qua** điều kiện cập nhật quyền chỉ vì JWT được ký hợp lệ.

### 4.2. Có nên chờ JWT tự hết hạn?

Đây là phương án có thể chấp nhận nếu:

- Scope có rủi ro thấp, không chứa dữ liệu nhạy cảm.
- Token TTL ngắn.
- Chính sách sản phẩm **cho phép quyền cũ tồn tại tối đa khoảng TTL**.
- Không có yêu cầu thu hồi tức thời sau khi mất việc, lộ token, hủy membership hoặc incident.

Nếu token còn 55 phút, cửa sổ quyền cũ có thể kéo dài tới 55 phút **khi Resource Server chỉ tin claims trong token**. JWT TTL ngắn hạn chế cửa sổ, nhưng không làm nó bằng 0.

### 4.3. Không dùng thay key ký JWT như cơ chế revoke một user

Xóa/rotate một signing key có thể khiến **rất nhiều tokens** dùng key đó bị mất khả năng verify, ảnh hưởng người dùng khác. Hơn nữa Resource Servers có JWK caches và rollover behavior. Key rotation dùng cho quản lý khóa/incident compromise theo runbook, **không phải cơ chế thông thường để thu hồi role của Alice**.

### 4.4. Logout frontend không làm JWT biến mất khỏi server khác

Một frontend xóa access token khỏi local storage/cookie sẽ ngăn **client đó** dùng token nữa, nhưng người đã copy Bearer token còn có thể thử gọi Resource Server.

Muốn server từ chối, cần token expiry, denylist, introspection, policy-version check hoặc cơ chế revoked sessions/grants được Resource Server áp dụng.

---

## 5. Opaque token và introspection: có kiểm tra trạng thái hiện hành

OAuth2 token introspection theo RFC 7662 cho phép Resource Server hỏi Authorization Server:

```http
POST /oauth2/introspect
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-credentials>

token=opaque-token-value
```

Đây là **minh họa HTTP**, không phải endpoint/credentials thật.

Response khái niệm:

```json
{
  "active": false
}
```

Nếu Authorization Server đã đánh dấu token revoked/inactive, Resource Server cấu hình introspection đúng sẽ không cho token ấy tạo Authentication hợp lệ.

Spring Security Servlet Resource Server hỗ trợ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://issuer.example.invalid/introspect
          client-id: reports-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Và DSL:

```java
http.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
);
```

Đây là **mảnh cấu hình thay thế JWT Resource Server**; không ghép nguyên vào ứng dụng JWT sample mà không chủ ý.

### 5.1. Introspection không tự đảm bảo scope mới đã cập nhật

Nếu AS trả:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports:read"
}
```

thì Resource Server vẫn có thể tạo authority `SCOPE_reports:read`. Khi admin sửa role, cần biết **Authorization Server có cập nhật scope trong introspection response hay chỉ trả snapshot grant lúc token phát hành?** `active=true` thường nghĩa token chưa revoked, không chứng minh grant động trong domain còn hiệu lực.

Nếu chính sách cần quyền cập nhật ngay, bạn có thể:

- Revoke token và để introspection trả `active=false`.
- Cấu hình AS trả thông tin quyền động theo hợp đồng được kiểm soát.
- Giữ introspection cho token validity, đồng thời Resource Server hỏi policy/ACL store **cho object/action hiện tại**.

### 5.2. Introspection còn chịu caching và availability

Khi cache introspection response `active=true` trong 60 giây, revoke ngay ở AS có thể chưa thấy ở Resource Server cho tới khi cache hết hạn hoặc bị invalidated. Cache across nodes làm tăng các failure modes.

SLA cần tính cả:

```text
revoke propagation delay
+ introspection cache TTL / invalidation lag
+ policy-store consistency lag
+ request/in-flight processing time
```

Khi introspection endpoint down, **không fallback sang `permitAll`**. Với thao tác nhạy cảm, fail closed; với tính sẵn sàng cao, cần thiết kế một offline policy rõ ràng, được đánh giá rủi ro và giới hạn thời gian.

### 5.3. Có thể introspect cả JWT không?

Có. Opaque-token support của Spring Security có thể **gửi bất kỳ chuỗi token nào cho introspection**; nó không nhất thiết yêu cầu format opaque. Dùng introspection cho JWT khi muốn hỏi AS liệu token đã revoked hay chưa.

Lúc ấy chiến lược validation là **online introspection**, không phải đường JWT local decoder mặc định. Cần kiểm tra các claims/metadata và resource authorization theo contract của introspection service, không tự coi việc “JWT có dấu chấm” là đã được xác thực cryptographically.

---

## 6. Token revocation (RFC 7009) và refresh token

### 6.1. Revocation endpoint làm gì?

RFC 7009 mô tả endpoint để client gửi token tới Authorization Server yêu cầu thu hồi:

```http
POST /oauth2/revoke
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <oauth-client-credentials>

token=<REFRESH_OR_ACCESS_TOKEN>&token_type_hint=refresh_token
```

Đây là cú pháp minh họa theo RFC; endpoint, client authentication và token type thực tế do Authorization Server triển khai.

**Ranh giới quan trọng:**

- Thu hồi **refresh token** thường ngăn dùng refresh token đó lấy **access token tương lai**.
- Access token **đã phát** có thể vẫn dùng được cho đến expiry nếu Resource Server chỉ verify JWT offline và không nhận tín hiệu revoke.
- Một số AS có thể thu hồi cả những tokens liên quan cùng grant; phải kiểm chứng policy/implementation, không mặc định.
- Thu hồi access token cần Resource Servers **nhận biết trạng thái thu hồi** bằng introspection, denylist hoặc phiên bản grant.

### 6.2. Refresh token rotation có sửa token cũ không?

Không. Khi client dùng refresh token để lấy access token mới, AS có thể tính lại scopes/claims theo current grants, nhưng **JWT access token cũ không bị thay đổi**. Việc xoay refresh token giảm rủi ro reuse/replay; nó không tự biến các JWT đã phát trước đó thành invalid tại mọi Resource Server.

Ví dụ:

```text
09:00 AT1(scope=read, exp=10:00) + RT1
09:10 revoke READ tại IAM
09:11 AT1 vẫn tồn tại trên thiết bị/client
09:20 client refresh RT1
09:20 AS cấp AT2(scope=none) hoặc từ chối refresh
09:21 Client dùng AT2 không có READ, nhưng AT1 có thể
      vẫn được chấp nhận nếu RS không có live revoke
```

**Không dựa vào việc frontend tự thay token đúng hạn** như một security boundary: attacker giữ AT1 có thể tiếp tục gửi AT1 trực tiếp.

### 6.3. ID token, session cookie và OAuth access token khác nhau

Một OIDC app có thể có đồng thời:

- Session cookie của **chính ứng dụng**.
- ID token để client xác nhận sự kiện đăng nhập.
- OAuth access token để gọi API.
- Refresh token để xin token mới.
- Session riêng tại Identity Provider.

Logout tại một nơi không mặc định thu hồi tất cả. Muốn “log out everywhere”, cần phối hợp session invalidation, OAuth token revocation và IdP session logout/back-channel logout nếu hệ thống hỗ trợ. Kiểm tra từng kênh rõ ràng.

---

## 7. Chọn chiến lược dựa trên độ trễ thu hồi quyền

| Chiến lược | Cách hoạt động | Cửa sổ quyền cũ / tradeoff |
| --- | --- | --- |
| Token TTL ngắn | Chờ `exp`, cấp token mới với claims mới | Tối đa gần TTL còn lại; đơn giản, rủi ro stale |
| Invalidate sessions | Xóa/expire session được index theo user | Request mới phải auth lại; cần shared store và xử lý in-flight |
| Recreate Authentication | Tải lại authorities và lưu SecurityContext | Phải cập nhật tất cả sessions/đường auth, đồng bộ cache |
| JWT `jti` denylist | RS kiểm tra issuer+jti ở denylist | Tra cứu mỗi request, TTL ít nhất tới `exp`, HA và consistency |
| Token/user `authzVersion` | So token/session version với current store | Token cũ bị deny ngay khi store đổi, cần lookup/cache version |
| Opaque introspection | RS hỏi AS về active/claims | Network latency, AS availability, cache freshness |
| Live policy/ACL lookup | RS kiểm tra quyền trên actor+resource+action | Chính xác theo DB policy, nhưng có chi phí truy vấn/race |
| Admin change event | Push invalidation qua bus/cache | Event delivery/replay/reconciliation, vẫn có độ trễ |
| Forced re-authentication | Client phải đăng nhập lại | Cần phát hiện và chặn tokens/sessions cũ ở server |
| Short TTL + live checks | Cả coarse và fine-grained | Phù hợp API nhạy cảm, thêm vận hành/observability |

**Không có một lựa chọn duy nhất cho mọi ứng dụng.** Nên phân loại operations:

- `GET` thông tin công khai/ít rủi ro: có thể chấp nhận quyền cũ rất ngắn.
- Đọc dữ liệu khách hàng/tenant: nên có live tenant/ACL lookup.
- Duyệt giao dịch, đổi role, xóa, chuyển tiền: version check + transaction guard và cơ chế revoke nhanh.
- Dịch vụ streaming: cần policy per-subscriber và cơ chế hủy stream sau revoke.
- Sự cố compromise: token/session kill switch theo account/client/tenant là yêu cầu vận hành độc lập.

Định nghĩa SLA rõ ràng:

```text
Critical revoke: request mới phải bị từ chối trong X giây.
Noncritical revoke: cho phép trễ tối đa Y phút.
In-flight write: không được commit nếu grant đã bị thu hồi
                 trước điểm được định nghĩa trong transaction.
```

Không đặt con số X/Y chỉ theo cảm tính; lấy từ risk assessment, data sensitivity, consistency model và khả năng đo lường thực tế.

---

## 8. Phiên bản quyền (`authzVersion`) như một cơ chế đơn giản và rõ ràng

Một policy store có thể lưu:

```text
User: issuer=https://issuer.example.invalid/tenant, sub=alice
Tenant: T1
Enabled: true
Scopes/current permissions: [reports:read]
authzVersion: 7
```

Khi admin thu hồi:

```text
Scopes/current permissions: []
authzVersion: 8
```

Khi cấp access token, Authorization Server có thể đưa `authz_ver=7` vào JWT. Resource Server, sau khi verify token, hỏi store:

```text
token.authz_ver == store.authzVersion ?
```

Nếu khác -> **reject token/deny operation** theo contract. Nếu bằng -> tiếp tục kiểm tra **current grants, tenant và object permission**.

### 8.1. Vì sao phải tăng version cả khi cấp lại quyền?

Giả sử revoke tăng version 7 → 8, sau đó grant lại tăng 8 → 9. JWT cũ version 7 vẫn có scope READ. Nếu chỉ so sánh “user hiện tại có READ” mà không xét version, token cũ có thể **đột nhiên được dùng lại** sau khi grant. Với version strict, old token không tự sống lại.

```text
t1  JWT1 version=7, scope=read -> ALLOW
t2  revoke, store version=8       -> DENY JWT1
t3  regrant, store version=9      -> JWT1 VẪN DENY
t4  issue JWT2 version=9          -> ALLOW nếu current policy cho phép
```

**Chú ý:** Version là một thiết kế app-specific. Nó có thể gắn với user, user+tenant, grant family, client hoặc session tùy mức độ chi tiết cần revoke. Key nên gồm issuer/tenant/client khi các namespace ID trùng nhau.

### 8.2. `iat` hay `authzVersion`?

Có thể đặt `revokedBefore`/`notBeforeEpoch` trên user và yêu cầu `iat` lớn hơn ngưỡng đó. Cách này hiệu quả nhưng cần xử lý:

- Chính xác timestamp theo giây hay mili-giây.
- Clock skew giữa AS và RS.
- Tokens phát đồng thời lúc admin revoke.
- Token không có `iat` hoặc có `iat` giả (trước khi chữ ký được xác thực).
- Một thay đổi quyền chỉ áp cho một tenant/client, không nhất thiết mọi token.

Một **version monotonic** rõ ràng thường dễ test hơn cho user grant changes. Với token-specific kill, dùng `jti` denylist riêng.

### 8.3. Cache version nhưng phải hiểu độ trễ

Nếu Resource Server cache current version trong 30 giây, JWT cũ có thể tiếp tục được cho phép cho tới khi cache bị invalidated. Nếu requirement là “thu hồi trong 2 giây” thì cache 30 giây không đáp ứng.

Cần:

- Version lookup có HA và timeout.
- Invalidate cache tới mọi node khi admin đổi grant.
- Metrics `policy_version_mismatch`, cache age, revoke propagation.
- TTL tối đa đã được review theo SLA.
- Fail closed trên thao tác nhạy cảm khi không đọc được version hiện hành.

### 8.4. `authzVersion` vẫn không thay object-level policy

Version user khớp **không đủ** nếu report đã chuyển tenant/owner sau khi token được phát hoặc ACL của object thay đổi. Cần kiểm tra resource-specific facts ở repository/transaction.

---

## 9. Ví dụ Java 17 chuẩn thư viện: quan sát quyền cũ và version check

Ví dụ này **chạy được bằng JDK 17**, không cần Spring, JWT key hay mạng. Nó mô phỏng session và access token snapshots để thể hiện thời điểm quyền thay đổi.

**Giới hạn:** `AccessToken` trong ví dụ là **record Java mô phỏng**, **không phải JWT có chữ ký**, không có khả năng xác minh token thật. Cơ chế authentication/signature verification của production phải do Spring Security Resource Server/Authorization Server đảm nhận.

### 9.1. Tạo file `PermissionChangeDemo.java`

```java
import java.util.HashSet;
import java.util.Set;

public class PermissionChangeDemo {

    private static final String READ = "reports:read";

    record SessionSnapshot(
            Set<String> authorities,
            long issuedVersion,
            boolean active) {

        SessionSnapshot {
            authorities = Set.copyOf(authorities);
        }
    }

    record AccessToken(
            Set<String> scopes,
            long issuedVersion,
            long expiresAtEpochSecond) {

        AccessToken {
            scopes = Set.copyOf(scopes);
        }
    }

    static final class Directory {

        private final Set<String> current = new HashSet<>();
        private long version = 1;

        Directory() {
            current.add(READ);
        }

        long version() {
            return version;
        }

        boolean has(String scope) {
            return current.contains(scope);
        }

        Set<String> snapshot() {
            return Set.copyOf(current);
        }

        void revokeRead() {
            current.remove(READ);
            version++;
        }

        void restoreRead() {
            current.add(READ);
            version++;
        }
    }

    static boolean sessionSnapshotAllows(
            SessionSnapshot session) {
        return session.active()
            && session.authorities().contains(READ);
    }

    static boolean tokenSnapshotAllows(
            AccessToken token, long now) {
        return now < token.expiresAtEpochSecond()
            && token.scopes().contains(READ);
    }

    static boolean sessionLiveAllows(
            SessionSnapshot session, Directory directory) {
        return sessionSnapshotAllows(session)
            && session.issuedVersion() == directory.version()
            && directory.has(READ);
    }

    static boolean tokenLiveAllows(
            AccessToken token, Directory directory, long now) {
        return tokenSnapshotAllows(token, now)
            && token.issuedVersion() == directory.version()
            && directory.has(READ);
    }

    public static void main(String[] args) {
        long now = 100L;
        Directory directory = new Directory();

        SessionSnapshot sessionV1 = new SessionSnapshot(
            directory.snapshot(), directory.version(), true);

        AccessToken tokenV1 = new AccessToken(
            directory.snapshot(), directory.version(), 200L);

        System.out.println("SESSION_INITIAL: "
            + sessionSnapshotAllows(sessionV1));
        System.out.println("TOKEN_INITIAL: "
            + tokenSnapshotAllows(tokenV1, now));

        directory.revokeRead();

        System.out.println("SESSION_STALE_AFTER_REVOKE: "
            + sessionSnapshotAllows(sessionV1));
        System.out.println("TOKEN_STALE_AFTER_REVOKE: "
            + tokenSnapshotAllows(tokenV1, now));
        System.out.println("SESSION_LIVE_AFTER_REVOKE: "
            + sessionLiveAllows(sessionV1, directory));
        System.out.println("TOKEN_LIVE_AFTER_REVOKE: "
            + tokenLiveAllows(tokenV1, directory, now));

        AccessToken tokenV2 = new AccessToken(
            directory.snapshot(), directory.version(), 200L);

        System.out.println("NEW_TOKEN_AFTER_REVOKE: "
            + tokenLiveAllows(tokenV2, directory, now));

        directory.restoreRead();

        System.out.println("OLD_TOKEN_AFTER_REGRANT: "
            + tokenLiveAllows(tokenV1, directory, now));

        AccessToken tokenV3 = new AccessToken(
            directory.snapshot(), directory.version(), 200L);

        System.out.println("NEW_TOKEN_AFTER_REGRANT: "
            + tokenLiveAllows(tokenV3, directory, now));

        System.out.println("NEW_TOKEN_EXPIRED: "
            + tokenLiveAllows(tokenV3, directory, 201L));
    }
}
```

### 9.2. Biên dịch và chạy

Tại thư mục chứa `PermissionChangeDemo.java`:

```bash
javac -encoding UTF-8 PermissionChangeDemo.java
java PermissionChangeDemo
```

**Output chính xác theo chương trình:**

```text
SESSION_INITIAL: true
TOKEN_INITIAL: true
SESSION_STALE_AFTER_REVOKE: true
TOKEN_STALE_AFTER_REVOKE: true
SESSION_LIVE_AFTER_REVOKE: false
TOKEN_LIVE_AFTER_REVOKE: false
NEW_TOKEN_AFTER_REVOKE: false
OLD_TOKEN_AFTER_REGRANT: false
NEW_TOKEN_AFTER_REGRANT: true
NEW_TOKEN_EXPIRED: false
```

Đọc ý nghĩa:

- Hai snapshot ban đầu chứa READ, nên `true`.
- Revoke ở directory **không sửa** session/token đã tạo: snapshot-only checks vẫn trả `true`.
- Live checks đối chiếu version và current permission nên trả `false`.
- Access token mới sau revoke không có READ.
- Khi cấp lại READ, JWT version cũ **vẫn không hợp lệ theo contract version strict**.
- JWT mới version 3 được phép, nhưng qua `expiresAt` thì hết hiệu lực.

**Đây là stdout được tính từ mã nguồn, chưa phải bằng chứng đã chạy chương trình ở máy người học.** Chạy lệnh để tự xác nhận và sửa lỗi môi trường Java nếu có.

### 9.3. Vì sao dùng `Set.copyOf`?

Session/token snapshot phải **bất biến** trong ví dụ; nếu code giữ `Set` mutable tham chiếu đến directory, cập nhật `directory.current` có thể làm snapshot thay đổi một cách tình cờ. Điều đó sẽ che giấu đúng vấn đề bài muốn minh họa: **token/session cũ mang quyền cũ**.

Trong JWT thật, claims được ký và không thay đổi khi IAM database đổi. Session Authentication thường là một object trong session; code có thể thay nó, nhưng cần cơ chế cập nhật/persist/replication rõ ràng.

---

## 10. Demo Spring Security 6.5: JWT cũ bị deny dù chữ ký và thời hạn chưa bị loại

Dự án sau có:

- `Spring Boot 3.5.8`, Java 17, Servlet Resource Server JWT.
- `@EnableMethodSecurity` và `@PreAuthorize`.
- JWT được ánh xạ scope `reports:read` thành `SCOPE_reports:read`.
- `GrantDirectory` chứa **current authorities + authzVersion**.
- `LiveReportPolicy` kiểm tra JWT scope, trusted issuer/audience, `authz_ver`, user enabled và tenant/resource.
- `ReportService` trả báo cáo đã được method-security bảo vệ.
- `MockMvc` tests dùng **Bearer header** và `JwtDecoder` test-only để kiểm tra thật đường đi JWT-claims -> authorities -> method policy.
- Thay quyền trực tiếp trên directory trong một test, rồi gửi lại **cùng Bearer token**.

**Phân biệt production và test:** Ở bản chạy thật, Spring Security phải dùng `JwtDecoder` với signature/issuer/time/audience validators. Trong tests, một fake decoder chỉ mô phỏng JWT đã giải mã nhằm kiểm tra logic **quyền thay đổi**, không phải mật mã JWT.

### 10.1. Cấu trúc thư mục

```text
live-permissions-resource-server/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── LivePermissionsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── GrantDirectory.java
    │   │   ├── ReportStore.java
    │   │   ├── LiveReportPolicy.java
    │   │   ├── ReportService.java
    │   │   └── ReportController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        └── PermissionChangeSecurityTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'live-permissions-resource-server'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ dùng Servlet web starter cho demo này. Nếu ứng dụng dùng Spring WebFlux, phải chuyển sang `ServerHttpSecurity`/`SecurityWebFilterChain` và reactive policy lookups, không copy nguyên `HttpSecurity` này.

### 10.4. `application.yml`

**`src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/tenant
          audiences:
            - reports-api
```

`issuer.example.invalid` là địa chỉ mẫu cố ý **không hoạt động**, không phải Identity Provider thật. Bản chạy main sẽ yêu cầu issuer hợp lệ có JWK endpoints tương ứng. Tests có fake decoder trong test source nên không phụ thuộc issuer thật.

**Production bắt buộc validate** signature, issuer, audience, `exp`, `nbf`. Contract `authz_ver` bổ sung **sau** những bước đó, không thay chúng.

### 10.5. Application

**`src/main/java/demo/LivePermissionsApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LivePermissionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            LivePermissionsApplication.class, args
        );
    }
}
```

### 10.6. Spring Security configuration

**`src/main/java/demo/SecurityConfig.java`:**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**"
                ).hasAuthority("SCOPE_reports:read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Mặc định JWT `scope="reports:read"` trở thành authority `SCOPE_reports:read`. HTTP check làm **coarse scope guard**. Method security bên dưới làm **live version/tenant check**.

**CSRF:** Dự án demo chỉ expose HTTP GET; không disable CSRF. Với API có POST/DELETE và dùng browser cookie/session, phải đánh giá CSRF rõ. Một API chỉ dùng bearer header và hoàn toàn stateless có mô hình khác, nhưng không áp blanket CSRF disable cho mọi kiến trúc.

**`STATELESS` không tự có nghĩa token mất hiệu lực khi role đổi**. Nó chỉ nói Resource Server không sử dụng HTTP session để giữ authentication theo cơ chế này; vẫn phải áp policy hiện hành.

### 10.7. Grant store có version

**`src/main/java/demo/GrantDirectory.java`:**

```java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class GrantDirectory {

    public static final String ISSUER =
        "https://issuer.example.invalid/tenant";

    public record Grant(
            String tenantId,
            long version,
            boolean enabled,
            Set<String> permissions) {

        public Grant {
            permissions = Set.copyOf(permissions);
        }
    }

    private final Map<String, AtomicReference<Grant>> grants =
        Map.of(
            "alice", new AtomicReference<>(
                new Grant(
                    "T1", 1L, true, Set.of("reports:read")
                )
            ),
            "bob", new AtomicReference<>(
                new Grant(
                    "T2", 1L, true, Set.of("reports:read")
                )
            )
        );

    public Grant find(String issuer, String subject) {
        if (!ISSUER.equals(issuer)) {
            return null;
        }

        AtomicReference<Grant> value = grants.get(subject);
        return value == null ? null : value.get();
    }

    public void revokeRead(String subject) {
        AtomicReference<Grant> reference = require(subject);

        reference.updateAndGet(old -> new Grant(
            old.tenantId(),
            old.version() + 1,
            old.enabled(),
            Set.of()
        ));
    }

    public void restoreRead(String subject) {
        AtomicReference<Grant> reference = require(subject);

        reference.updateAndGet(old -> new Grant(
            old.tenantId(),
            old.version() + 1,
            old.enabled(),
            Set.of("reports:read")
        ));
    }

    private AtomicReference<Grant> require(String subject) {
        AtomicReference<Grant> value = grants.get(subject);

        if (value == null) {
            throw new IllegalArgumentException(
                "Unknown trusted principal"
            );
        }
        return value;
    }
}
```

`GrantDirectory` là in-memory store **chỉ dành cho demo**. Nó cố tình có các method `revokeRead`/`restoreRead` để test event đổi quyền, **không được export các method này thành API công khai**.

Ở production:

- Sử dụng database/IAM/authorization policy service có consistency contract.
- Khóa identity nên bao gồm **issuer + stable subject**, cùng tenant/client nếu scope gắn theo chúng.
- `version` phải monotonic và không reset khi restart.
- Grant update và version increment nên là **một transaction nguyên tử**.
- Cache invalidation phải tới mọi instance.
- Mọi endpoint cấp quyền/thu hồi quyền phải có kiểm tra quản trị và audit.
- Không tin một JSON `authz_ver` do client gửi; chỉ đọc từ **JWT đã verified**.

### 10.8. Resource store bất biến trong demo

**`src/main/java/demo/ReportStore.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.stereotype.Repository;

@Repository
public class ReportStore {

    public record Report(
            long id,
            String tenantId,
            String title) {
    }

    private final Map<Long, Report> reports = Map.of(
        100L, new Report(100L, "T1", "Quarterly-T1"),
        200L, new Report(200L, "T2", "Quarterly-T2")
    );

    public Report find(long id) {
        return reports.get(id);
    }
}
```

Store bất biến giúp tập trung vào thay đổi **grant**. Trong ứng dụng thật, quyền có thể phụ thuộc trạng thái và owner của resource; query/transaction phải cùng phản ánh dữ liệu hiện tại.

### 10.9. Policy kiểm tra cả claims và current grants

**`src/main/java/demo/LiveReportPolicy.java`:**

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("livePolicy")
public class LiveReportPolicy {

    private final GrantDirectory directory;
    private final ReportStore reports;

    public LiveReportPolicy(
            GrantDirectory directory,
            ReportStore reports) {
        this.directory = directory;
        this.reports = reports;
    }

    public boolean canRead(
            Authentication authentication, long reportId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()) {
            return false;
        }

        boolean scopeGranted = authentication.getAuthorities()
            .stream()
            .anyMatch(a ->
                "SCOPE_reports:read".equals(a.getAuthority())
            );

        if (!scopeGranted) {
            return false;
        }

        var jwt = jwtAuth.getToken();

        String issuer = jwt.getClaimAsString("iss");

        if (!GrantDirectory.ISSUER.equals(issuer)
                || !jwt.getAudience().contains("reports-api")) {
            return false;
        }

        Object rawVersion = jwt.getClaim("authz_ver");

        if (!(rawVersion instanceof Number version)) {
            return false;
        }

        GrantDirectory.Grant current =
            directory.find(issuer, jwt.getSubject());

        ReportStore.Report report = reports.find(reportId);

        if (current == null || report == null) {
            return false;
        }

        return current.enabled()
            && current.version() == version.longValue()
            && current.permissions().contains("reports:read")
            && current.tenantId().equals(report.tenantId());
    }
}
```

**Cốt lõi:**

1. JWT đã qua Resource Server Authentication flow mới được đưa tới `LiveReportPolicy`.
2. Scope `SCOPE_reports:read` được kiểm tra theo authorities đã map.
3. Policy kiểm tra issuer/audience thêm lần nữa như **defense in depth**; production phải có decoder validators thực sự.
4. `authz_ver` phải là number theo hợp đồng; thiếu hoặc sai type -> deny.
5. Directory tìm current grant từ trusted issuer+sub.
6. Nếu user disabled, version mismatch hoặc READ bị thu -> deny.
7. Nếu report thuộc tenant khác -> deny.
8. Không có dữ liệu -> deny, không tự fallback sang role cũ.

Trong hệ thống thật, version check cần được cache/đọc với freshness phù hợp SLA; khi policy store down, thiết kế phải quyết định **fail closed** cho hành động nhạy cảm. Mã demo không có remote call nên không mô phỏng lỗi network.

**Cảnh báo TOCTOU:** Sau check, report/tenant/permission có thể đổi trước khi DB action. Với report read bất biến của demo, không có race resource; với write hoặc data mutable, thêm DB guards và locking/version.

### 10.10. Method security tại service

**`src/main/java/demo/ReportService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportStore reports;

    public ReportService(ReportStore reports) {
        this.reports = reports;
    }

    @PreAuthorize(
        "@livePolicy.canRead(authentication, #p0)"
    )
    public String read(long reportId) {
        return reports.find(reportId).title();
    }
}
```

`#p0` tham chiếu argument đầu tiên của method, không phụ thuộc Java reflection parameter names. `@EnableMethodSecurity` từ `SecurityConfig` bật interceptor.

**Đây là điểm quan trọng để test:** `ReportService` phải được gọi qua Spring-managed proxy (`@Service` inject từ controller); `new ReportService(...)` hoặc `this.read()` từ method cùng bean có thể bypass Spring AOP. Trong production, bảo vệ domain/repository vẫn phải đủ mạnh ngay cả khi có nhiều entry points.

`reports.find(...).title()` chỉ an toàn trong ví dụ vì `LiveReportPolicy` đã check report tồn tại và store bất biến. Khi resource thay đổi concurrent, không viết như vậy cho dữ liệu thật; lấy resource theo tenant/permission trong transaction hoặc query authoritative.

### 10.11. Controller

**`src/main/java/demo/ReportController.java`:**

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/api/reports/{id}")
    public String read(@PathVariable long id) {
        return service.read(id);
    }
}
```

Controller không nhận `sub`, role hay tenant từ request body để tự cấp quyền. Spring Resource Server xác thực Bearer token, rồi service áp current grants.

---

## 11. Kiểm thử: cùng JWT cũ, quyền đã đổi

Test dưới đây không giả mạo `SCOPE_` authorities trực tiếp; nó gửi `Authorization: Bearer ...` qua Spring Security filters và để `JwtAuthenticationConverter` thật đọc `scope`/`authz_ver` của JWT test fixture.

**Không dùng `JwtDecoder` giả trong production.** Các token strings `alice-v1` và `alice-v3` bên dưới **chỉ tồn tại trong test fixture**. Chúng không phải JWT thật có signature.

### 11.1. `src/test/java/demo/PermissionChangeSecurityTest.java`

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(PermissionChangeSecurityTest.DecoderForTest.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class PermissionChangeSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    GrantDirectory grants;

    @TestConfiguration(proxyBeanMethods = false)
    static class DecoderForTest {

        @Bean
        @Primary
        JwtDecoder jwtDecoder() {
            return raw -> switch (raw) {
                case "alice-v1" -> issue(
                    raw, "alice", "reports:read", 1, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "alice-v3" -> issue(
                    raw, "alice", "reports:read", 3, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "alice-no-scope" -> issue(
                    raw, "alice", "profile", 1, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "bob-v1" -> issue(
                    raw, "bob", "reports:read", 1, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "alice-wrong-aud" -> issue(
                    raw, "alice", "reports:read", 1, "other-api",
                    GrantDirectory.ISSUER
                );
                case "alice-wrong-issuer" -> issue(
                    raw, "alice", "reports:read", 1, "reports-api",
                    "https://untrusted.example.invalid"
                );
                case "alice-no-version" -> Jwt
                    .withTokenValue(raw)
                    .header("alg", "RS256")
                    .claim("iss", GrantDirectory.ISSUER)
                    .claim("sub", "alice")
                    .claim("aud", List.of("reports-api"))
                    .claim("scope", "reports:read")
                    .build();
                default -> throw new BadJwtException(
                    "Invalid token in test fixture"
                );
            };
        }

        private static Jwt issue(
                String token,
                String sub,
                String scope,
                int version,
                String audience,
                String issuer) {

            return Jwt.withTokenValue(token)
                .header("alg", "RS256")
                .claim("iss", issuer)
                .claim("sub", sub)
                .claim("aud", List.of(audience))
                .claim("scope", scope)
                .claim("authz_ver", version)
                .build();
        }
    }

    private static String bearer(String raw) {
        return "Bearer " + raw;
    }

    @Test
    void sameOldTokenIsDeniedAfterRevoke()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Quarterly-T1"));

        // Admin operation ở test tác động tới CURRENT store.
        grants.revokeRead("alice");

        // Token fixture alice-v1 vẫn có scope "reports:read".
        // HTTP scope guard có thể pass, nhưng live policy DENY.
        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isForbidden());

        grants.restoreRead("alice");

        // Regrant không được làm JWT version 1 sống lại.
        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isForbidden());

        // Token mới version 3, current grant đã có READ.
        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v3")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Quarterly-T1"));
    }

    @Test
    void currentScopeStillRequiresCurrentTenant()
            throws Exception {

        mvc.perform(get("/api/reports/200")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/200")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("bob-v1")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Quarterly-T2"));
    }

    @Test
    void tokenWithoutReadScopeIsForbidden()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-no-scope")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void tokenMissingVersionIsForbidden()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-no-version")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongIssuerOrAudienceIsNotAuthorized()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-wrong-aud")
                ))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-wrong-issuer")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenGetsUnauthorized()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("not-a-token")
                ))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingTokenGetsUnauthorized()
            throws Exception {

        mvc.perform(get("/api/reports/100"))
            .andExpect(status().isUnauthorized());
    }
}
```

### 11.2. Tại sao test này kiểm đúng vấn đề?

- Test đầu tiên gửi **cùng chuỗi Bearer `alice-v1`** trước và sau revoke. Nó không phát token mới bằng phép thử khác.
- Resource Server xử lý Bearer header và dùng **JwtAuthenticationConverter thật** để tạo `SCOPE_reports:read`.
- HTTP scope guard cho token cũ vẫn có thể thành công; **`LiveReportPolicy` đối chiếu current version** rồi từ chối.
- Regrant version 3 vẫn từ chối JWT version 1, phát mới version 3 thì thành công.
- Test Alice đọc report T2 bị deny, Bob/T2 đọc được.
- Test thiếu scope, thiếu `authz_ver`, sai issuer/audience bị deny.
- Test token không decode được và không có token trả 401 theo Bearer entry point.

**Ranh giới kiểm thử quan trọng:** Fake decoder trong `@TestConfiguration` không test signature, `exp`, `nbf`, issuer/audience validators thật. Nhánh kiểm tra issuer/audience trong `LiveReportPolicy` cho 403 trong test, nhưng **production decoder đúng phải từ chối token sai issuer/audience ở bước authentication**, thường dẫn tới 401. Cần test riêng với `NimbusJwtDecoder` thật, JWK fixture và đồng hồ giả để chứng minh tính đúng của crypto/time validators.

### 11.3. Chạy Gradle tests

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có Gradle Wrapper, dùng Gradle phù hợp để tạo wrapper trước, hoặc chạy `gradle test` với Gradle đã cài.

**Kết quả mong đợi:** bảy integration tests trong `PermissionChangeSecurityTest` pass. Đây là kỳ vọng dựa trên mã nguồn, **không phải tuyên bố đã biên dịch hoặc chạy thật** trong môi trường viết tài liệu.

Để chạy API main qua `./gradlew bootRun`, cần cấu hình Authorization Server **thật** thay `issuer.example.invalid`. Khi không có IdP thật, project sample chỉ định danh đường cấu hình và có thể chạy tests bằng fake decoder.

---

## 12. Đường làm mới quyền ở session-based application

Ví dụ Resource Server ở mục 10 là **stateless JWT**, không dùng HTTP session để giữ auth. Trong một **ứng dụng khác** có form-login/session, bạn có thể làm mới authorities theo một số cách.

### 12.1. Option 1 — expire các sessions liên quan

Khi admin update role:

```text
Transaction thay grants + tăng policyVersion
             |
             v
Commit database
             |
             v
Emit "UserGrantsChanged" event
             |
             +--> Expire/delete sessions theo issuer+subject
             |
             +--> Invalidate caches ở mọi app nodes
             |
             +--> Audit, metrics, retry event
```

Request sau với session cũ bị buộc đăng nhập lại hoặc áp version gate để từ chối ngay. Nếu chỉ gửi event và xóa session async, vẫn có một **cửa sổ propagation**; với nhiệm vụ nhạy cảm, thêm lookup version/policy ngay tại use case.

### 12.2. Option 2 — reload `Authentication` và lưu SecurityContext

Mảnh code:

```java
Authentication fresh =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            verifiedUsername, verifiedCredential
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(fresh);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context, request, response
);
```

**Không phải file độc lập:** các beans/request và verified credentials cần từ authentication flow thật. Nếu không có credential để reauthenticate, có thể dùng trusted directory/provider để làm mới authorities dựa vào một principal đã verified theo một cơ chế riêng, nhưng không tự tạo token authenticated từ user ID trong body.

Lưu session context mới cũng chưa cập nhật **những sessions khác**. Muốn revoke toàn bộ, cần đánh dấu version hoặc tìm/xóa từng session.

### 12.3. Option 3 — tách identity session khỏi live permissions

Thay vì coi toàn bộ authorities trong session là nguồn sự thật:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "@liveGrantService.canRead(authentication, #p0)"
)
public ReportView read(long reportId) {
    // Repository kiểm tra tenant/ACL thật.
}
```

Mảnh code cho **session-based application**; `liveGrantService` phải xử lý cả `UsernamePasswordAuthenticationToken`/principal thích hợp, không chỉ `JwtAuthenticationToken` như demo JWT.

Cách này có ưu điểm thay role không đòi cập nhật mọi `Authentication` snapshots. Nhưng phải có lookup latency/availability/caching policy rõ ràng và chặn khi service policy không phản hồi.

### 12.4. Option 4 — session chứa `policyVersion`

Trong session lưu:

```text
userId = alice
sessionPolicyVersion = 7
```

Khi current version lên 8, request mới có thể bị chặn **ngay trước** khi thực hiện method nhạy cảm. Sau reauth/refresh session, version mới được lưu. Tạo một custom filter/AuthorizationManager với trusted session identity; tránh dựa duy nhất vào `@PreAuthorize` ở một endpoint và bỏ quên endpoints khác.

---

## 13. Denylist token `jti` và thu hồi theo token/user/tenant

Nếu yêu cầu thu hồi chính xác **một access token** mà không buộc tất cả tokens của user đăng nhập lại, một denylist có thể lưu:

```text
key: revoked:{issuer}:{jti}
value: revoked
expiry: token.exp + allowedClockSkew
```

Khi nhận JWT đã verify, Resource Server lookup denylist theo trusted issuer+jti. Nếu có key, từ chối.

### 13.1. Ưu điểm và giới hạn

- Có thể revoke một token/session cụ thể, ví dụ token bị lộ.
- Không phải bump mọi user policy version khi chỉ cần kill một token.
- Nhưng phải có `jti` unique theo issuer/tenant/grant family hoặc dùng fingerprint an toàn.
- Phải giữ denylist tới khi token chắc chắn hết hiệu lực, tính cả clock skew.
- Multi-node cache/repl phải nhất quán theo SLA.
- Khi Redis/denylist store unavailable, fail-closed cho operations nhạy cảm hoặc có degraded-mode policy được phê duyệt.
- Mọi validation signature/issuer/audience/time vẫn phải thực hiện trước khi đọc `jti` như một key bảo mật.

Không lưu raw access token trong logs hoặc denylist nếu không cần. Trường hợp token thiếu `jti`, cần có phương án riêng được thiết kế: có thể hash token bằng thuật toán phù hợp, hoặc dùng authzVersion cho whole-user revoke. Đừng dựa vào string `jti` do client đặt ở query để quyết định quyền.

### 13.2. Khác nhau giữa revoke user và revoke token

- **Revoke user grants:** user không được READ nữa; version/policy store làm các tokens cũ không được READ.
- **Revoke one token:** chỉ token `jti=x` bị từ chối; một token hợp lệ khác của cùng user có thể vẫn dùng được.
- **Disable account:** thường yêu cầu chặn mọi phiên/token của subject theo identity store, kể cả tokens có scope thấp.
- **Revoke tenant membership:** chỉ những operations thuộc tenant tương ứng bị chặn; key/version có thể là user+tenant nếu cần tinh vi.
- **Compromised client:** có thể cần thu hồi cả client grants/token families, không chỉ một người dùng.

Phân biệt các phạm vi để không dùng một lệnh revoke quá rộng hoặc quá hẹp.

---

## 14. Race condition: quyền bị thu hồi giữa check và DB commit

Ngay cả khi Resource Server hỏi current policy mỗi request:

```text
T1: GET current grant -> reports:approve = ALLOW
T2: Admin revoke reports:approve
T3: Service UPDATE report sang APPROVED
T4: Transaction COMMIT
```

Một authorization check trước business method không tạo transaction nguyên tử cùng lúc với việc đổi grants.

### 14.1. Conditional mutation

Ví dụ database guard:

```sql
UPDATE reports
SET status = 'APPROVED',
    approved_by = :trustedSubject,
    version = version + 1
WHERE id = :reportId
  AND tenant_id = :trustedTenantId
  AND status = 'PENDING'
  AND version = :expectedVersion;
```

**SQL này bảo vệ resource facts** như tenant/state/version, nhưng nếu permission bị quản lý trong bảng grant khác, vẫn cần một cơ chế đồng bộ permission/authorization version tương ứng với transaction ghi.

### 14.2. Khi grant cũng ở database

Có thể dùng transaction/locking chung hoặc version check được đồng bộ:

1. Đọc user/tenant grant version trong transaction.
2. Đọc resource row với điều kiện tenant/owner/ACL.
3. Kiểm tra permission current và invariants.
4. UPDATE với `WHERE version = :expectedVersion` hoặc lock row theo thứ tự nhất quán.
5. Đảm bảo transaction **revocation** tham gia cùng locking/version protocol nếu requirement là revoke tức thì so với commit.

Nếu revoker chỉ cập nhật Redis còn writer chỉ lock report row ở SQL, hai locks **không** tự ràng buộc nhau. Định nghĩa cụ thể “revoke có hiệu lực từ lúc commit grant store” hay “từ sau khi event tới mọi RS”.

### 14.3. Không dựa vào một `@PostAuthorize` cho lệnh ghi

`@PostAuthorize` có thể đánh giá sau khi method đã thực hiện side effect. Nó không phải thay thế cho `@PreAuthorize` và conditional DML/transaction guard trong việc duyệt/xóa/chuyển tiền.

### 14.4. Background jobs và streaming

Session/token có thể hết hạn hoặc permission bị revoke khi:

- Message consumer đang xử lý task vài phút sau request HTTP.
- Batch job sử dụng delegated token.
- WebSocket/SSE stream còn nối hàng giờ.
- File download đã bắt đầu nhưng dữ liệu còn phát nhiều chunks.

Không coi một ALLOW lúc kết nối là grant vĩnh viễn. Thiết kế job identity, policy refresh, per-item/batch recheck và cancellation theo mức độ dữ liệu nhạy cảm. Khi stream đã gửi một phần response, không phải lúc nào cũng có thể chuyển status thành 403; cần cancel stream và ghi audit.

---

## 15. Cache, sự cố mạng và SLA thu hồi quyền

Các caches ảnh hưởng trực tiếp đến độ trễ:

| Cache | Nội dung | Rủi ro |
| --- | --- | --- |
| JWT decoder/JWK cache | Public keys/metadata | Không thay thế grant lookup; key rotation không target one user |
| Session cache | SecurityContext/authorities | Không thấy role mới nếu session chưa refresh |
| Introspection cache | `active=true`, scopes | Token đã revoke vẫn có thể được chấp nhận cho tới expiry cache |
| User/grant cache | Roles/permissions/epoch | Version mismatch có thể bị bỏ sót |
| ACL cache | Object-level permissions | Owner/tenant/ACL thay đổi chưa kịp propagate |
| Response/data cache | Kết quả đã được authorize | Dùng lại xuyên users/tenants, có thể lộ dữ liệu |

**Cache key cho authorization** thường cần:

```text
issuer, subject, tenant, action,
resourceType, resourceId, resourceVersion,
policyVersion / authzVersion
```

Không cache boolean `canRead` chỉ theo `reportId`; Alice và Bob có identity/tenant khác nhau.

Nếu policy là multi-node:

```text
Admin revoke
    |
    +--> update authoritative store atomically
    |
    +--> publish invalidation event
    |       +--> Node A local cache
    |       +--> Node B local cache
    |       +--> Node C local cache
    |
    +--> metrics/alerts for propagation lag
```

Cần có fallback hoặc reconciliation nếu node bỏ lỡ event; chỉ push event một lần không đủ đảm bảo. Với quyền cực nhạy cảm, có thể phải đọc directly from strongly consistent store hoặc chặn khi không chắc latest version.

### 15.1. `fail closed` là mặc định cho nguy cơ cao

Nếu policy lookup timeout:

```java
// CỐ TÌNH SAI:
try {
    return policyService.canApprove(actor, report);
} catch (Exception ex) {
    return true;
}
```

Code trên biến sự cố PDP thành cấp quyền. Phải chọn error/deny theo hệ thống, ví dụ:

```java
// MẢNH CODE, cần policyService và exception mapping riêng.
try {
    return policyService.canApprove(actor, report);
} catch (PolicyUnavailableException unavailable) {
    return false;
}
```

Nếu muốn ứng dụng hoạt động offline, phải có policy snapshot/TTL và phạm vi operations được phê duyệt; không vô tình `allow` trong catch block.

### 15.2. TTL ngắn + introspection có thể chưa đủ

Độ trễ thực tế nên được đo với tình huống:

```text
09:10:00 admin commit revoke
09:10:01 Node A denies request with old token
09:10:07 Node B still accepts old token from stale cache
09:10:11 Node B cache refreshed, starts denying
```

Nếu SLA cho quyền admin là 3 giây, hệ thống này **vi phạm SLA** dù average latency rất tốt. Đo p95/p99, multi-node skew, cache invalidation lag, in-flight work, không chỉ “token expired after 5 min”.

---

## 16. 401, 403 và 404: tránh báo sai nguyên nhân

| Tình huống | HTTP status phổ biến | Nên sửa chỗ nào? |
| --- | --- | --- |
| Không có access token khi endpoint private | 401 | Authentication/client token |
| Token invalid signature, expired, wrong issuer/audience | 401 | Decoder trust/validator, AS |
| Token có scope nhưng `authz_ver` cũ | 403 ở policy layer, hoặc 401 nếu coi token bị revoke ở authentication | Version gate và contract |
| Session bị expire/invalidate | 401 hoặc redirect login | Session authentication entry point |
| Token hợp lệ nhưng thiếu `SCOPE_reports:read` | 403 | Scope grant/mapping |
| Tenant hiện hành khác tenant report | 403 hoặc 404 | Data authorization |
| Account disabled nhưng token còn hạn | 403/401 theo vị trí kiểm tra | Current account state |
| Introspection endpoint unreachable | Không cho thực hiện operation; mã lỗi tùy error contract | Fail-closed, retry/deadline |
| Access token được refreshed nhưng old token còn sống | Có thể vẫn truy cập nếu không revoke | Revocation/version/introspection |

**Đừng sửa tất cả 403 bằng cách tắt `@PreAuthorize` hoặc đổi `.hasAuthority(...)` thành `.authenticated()`.** Trước hết phân biệt lỗi token validity, authority mapping, current grants, tenant/ACL và domain state.

Khi cần ép người dùng refresh/re-authenticate sau role change, API có thể chuẩn hóa một error code ứng dụng như `AUTHZ_VERSION_STALE`; client sẽ xin token mới hoặc redirect login. Nhưng **server phải từ chối old token**, không chỉ yêu cầu frontend tự refresh.

Không để message tiết lộ quá nhiều về account khác tenant, object existence, role internal, policy engine hay JWK config.

---

## 17. Ma trận kiểm thử sau khi thay đổi quyền

| Case | Điều cần chứng minh |
| --- | --- |
| Session lúc login có READ | Hoạt động trước revoke |
| Admin revoke READ khi session còn sống | Session stale không được đọc sau SLA |
| Invalidate session hiện tại | Request sau phải auth lại |
| User có nhiều sessions/devices | Revoke áp cho tất cả scope liên quan |
| JWT version 1 có READ | GET thành công trước revoke |
| Cùng JWT version 1 sau revoke | Phải DENY dù token chưa hết hạn |
| Regrant READ thành version 3 | JWT v1 vẫn không tự được phép lại |
| JWT mới version 3 | ALLOW khi current grants/tenant khớp |
| JWT không có `authz_ver` | DENY nếu contract version là bắt buộc |
| JWT scope thiếu READ | DENY, dù version mới |
| JWT sai issuer/audience | Token phải bị từ chối từ decoder trong production |
| JWT không verify được/expired | 401 theo Bearer auth |
| Token `jti` trong denylist | DENY trước khi dùng protected resource |
| Opaque introspection `active=false` | DENY |
| Introspection cache stale `active=true` | Test propagation lag và TTL |
| Policy cache stale | Không vượt revoke SLA |
| Policy service lỗi/timeout | Không fallback allow |
| User T1 cầm token READ, biết ID T2 | DENY hoặc 404, không lộ dữ liệu |
| Owner/ACL thay đổi giữa check và use | Mutation DB bị chặn theo consistency contract |
| Refresh token revoked | Không mint new access token bằng RT cũ |
| AT cũ sau revoke RT | Được từ chối nếu hệ thống **có** access-token revoke |
| Multi-node A/B | Mọi node hội tụ theo SLA |
| Background job sau revoke | Re-authorize ở lúc thực hiện |
| WebSocket/SSE sau revoke | Cancel hoặc per-item check theo policy |

Một test suite nên bao gồm cả **ALLOW trước revoke**, **DENY sau revoke**, **ALLOW với token mới** và **DENY old token sau regrant**. Nếu chỉ test deny sau revoke, một manager luôn trả false cũng có thể làm test pass nhưng hệ thống không còn dùng được.

---

## 18. Các sai lầm thường gặp

| Lỗi | Tại sao sai? | Giải pháp |
| --- | --- | --- |
| “Đổi role trong DB thì session tự cập nhật” | Session có Authentication snapshot | Refresh/invalidate session hoặc live policy |
| “JWT ký đúng nghĩa là role còn đúng” | Signature chứng thực token lúc phát, không truy vấn current grant | AuthzVersion/denylist/introspection/live ACL |
| “Xóa cookie là revoke token” | Token có thể đã bị copy | Server-side revocation |
| “Revoke refresh token đã revoke access token” | AT đã phát có thể tiếp tục sống | AT-specific revocation policy |
| “`exp` còn 1 giờ không sao” | Cửa sổ quyền cũ dài | Short TTL + dynamic check theo rủi ro |
| Dùng `iat` không xử lý clock skew | Race/timestamp precision | Monotonic version và tests |
| Cấp lại READ làm token cũ sống lại | Chỉ kiểm tra current grant | Strict version check |
| Chỉ cache version theo `userId` trùng giữa issuers | Cross-issuer confusion | Issuer + subject + tenant |
| Chỉ test unit `hasAuthority` | Không kiểm tra converter/HTTP path | MockMvc Bearer integration |
| Fake JwtDecoder để trong main | Không verify chữ ký | Test-only decoder, prod Nimbus decoder |
| Introspection cache quá lâu | Active token stale sau revoke | TTL/invalidation phù hợp SLA |
| Policy service down -> ALLOW | Fail-open | Deny/fail operation |
| `SessionRegistry.expireNow` được coi là xóa tức thì | Đánh dấu expire, còn cần filter/lifecycle | Cấu hình expiry, test multi-node |
| Logout một session và nghĩ logout everywhere | Nhiều sessions/tokens khác vẫn tồn tại | Shared session registry + token revoke |
| JWT scope đủ -> đọc mọi tenant | Scope chỉ quyền chức năng | Tenant + ACL/data guard |
| In-memory ACL kiểm tra rồi UPDATE unscoped | TOCTOU/cross-tenant | Conditional DML/transaction |
| JWT roles từ client-supplied JSON | Trust boundary sai | Only verified token + trusted issuer |
| Bump version nhưng không commit atomically | Race cấp token so với policy update | Transactional grant/version |
| Chỉ gửi invalidate event, không retry | Node bỏ lỡ event | Reconciliation + max TTL |
| WebSocket có ALLOW lúc connect là đủ | Quyền có thể revoke khi streaming | Recheck/cancel |
| Ghi token vào log debug | Lộ Bearer credentials | Hash/correlation IDs, redact |
| Đổi JWT signing key để revoke 1 role | Tác động diện rộng và cache vấn đề | Per-user version/jti denylist |

---

## 19. Câu hỏi tự đánh giá

### Câu 1. Session đang sống nhưng role bị xóa

Session của Alice lưu `ROLE_MANAGER`; admin xóa role trong database. Nếu code chỉ kiểm tra authorities có sẵn trong `SecurityContext`, điều gì có thể xảy ra?

**Đáp:** Alice có thể vẫn được coi là manager cho tới khi Authentication/session được refresh/invalidate hoặc policy hiện hành được kiểm tra.

### Câu 2. JWT có `SCOPE_reports:read` nhưng admin thu quyền

Token chưa hết hạn, chữ ký hợp lệ. `hasAuthority("SCOPE_reports:read")` đơn lẻ có đủ không?

**Đáp:** Không nếu yêu cầu revoke có hiệu lực trước token expiry. Cần version/denylist/introspection/current policy.

### Câu 3. Revoke refresh token

Client revoke RT, còn AT1 chưa hết hạn. AT1 tự bị từ chối ở JWT decoder offline không?

**Đáp:** Không mặc định. Cần cơ chế access-token revocation được Resource Server thực hiện.

### Câu 4. Một opaque token `active=false`

Introspection trả `active=false`; Resource Server nên tạo Authentication granted không?

**Đáp:** Không. Token inactive không được chấp nhận.

### Câu 5. `active=true` nhưng quyền đã đổi

Có thể coi `active=true` là được mọi hành động như scope cũ không?

**Đáp:** Không. Active chỉ nói token hiện được AS coi là active theo contract; vẫn cần action scope/current grant/tenant/resource policy.

### Câu 6. So version sau regrant

Token v1 READ, revoke thành v2, grant lại v3. V1 còn được dùng không?

**Đáp:** Không nếu thiết kế strict authzVersion: 1 != 3. Cần token/session mới.

### Câu 7. Denylist bằng `jti`

Tại sao phải lưu denylist đến ít nhất expiry+skew?

**Đáp:** Token đã revoked có thể vẫn chưa hết hạn; xóa denylist quá sớm có thể khiến token được chấp nhận lại.

### Câu 8. SessionRegistry `expireNow()`

Gọi `expireNow()` có chắc mọi request đang chạy lập tức bị hủy không?

**Đáp:** Không. Nó đánh dấu trạng thái expire; filter/request lifecycle và multi-node consistency phải được thiết kế.

### Câu 9. Có nên dùng JWT scope để tìm tenant?

JWT scope `reports:read` có chứng minh người dùng thuộc T2 không?

**Đáp:** Không. Tenant membership cần từ nguồn đáng tin hoặc claims được verify và kiểm tra theo policy; resource cũng cần tenant scope.

### Câu 10. Vì sao phải test old token sau regrant?

**Đáp:** Để phát hiện một giải pháp chỉ nhìn current permission có thể cho JWT cũ sống lại khi READ được cấp trở lại.

### Câu 11. Policy service timeout

Có thể cho phép thao tác xóa vì “hệ thống đang lỗi” không?

**Đáp:** Không nếu policy yêu cầu fail closed. Hệ thống phải từ chối/không thực hiện mutation hoặc dùng một offline policy đã được phê duyệt theo SLA.

### Câu 12. Một tài liệu đổi owner giữa authorization và UPDATE

JWT đúng scope, version user vẫn mới. Có cần kiểm tra lại không?

**Đáp:** Có. Token/user version không thay thế current resource/ACL/owner check và transaction guard.

### Câu 13. Sai audience

JWT được ký bởi issuer đáng tin nhưng `aud` dành cho API khác. Có nên tin `scope` không?

**Đáp:** Không. Decoder phải validate audience của Resource Server trước khi cấp Authentication.

### Câu 14. Chỉ một thiết bị logout

Alice logout browser A, browser B và một CLI vẫn giữ tokens/sessions. Có tự bị logout không?

**Đáp:** Không mặc định. Cần “logout everywhere” protocol cho sessions, token families và IdP nếu yêu cầu.

### Câu 15. `authzVersion` nằm ở đâu?

Có phải Spring Security bắt buộc mọi JWT đều có `authz_ver` không?

**Đáp:** Không. Đây là claim ứng dụng tự thiết kế, phải được Authorization Server phát từ trusted policy version và Resource Server validate theo cùng contract.

### Câu 16. Chỉ giảm JWT TTL có đáp ứng revoke trong 1 giây không?

**Đáp:** Không nếu token TTL còn hơn 1 giây; cần kiểm tra trạng thái hiện hành hoặc token revocation propagation trong SLA.

---

## 20. Checklist triển khai và vận hành

### Authentication / token validity

- [ ] Chỉ chấp nhận token từ issuer đã tin.
- [ ] Verify signature/key/algorithm, `exp`, `nbf`, `iss`, `aud`.
- [ ] Không sử dụng ID token thay OAuth2 access token.
- [ ] Không tin claims đọc từ payload trước verification.
- [ ] Phân biệt user token và client-credentials/machine token.
- [ ] Có kế hoạch JWK rotation và incident response.

### Current grants / revocation

- [ ] Xác định ai là authoritative source cho roles/scopes/ACL.
- [ ] Chọn SLA thu hồi quyền theo loại action.
- [ ] Hiểu session Authentication snapshots và cơ chế refresh/invalidation.
- [ ] Với JWT, chọn TTL, `authzVersion`, denylist hoặc introspection theo rủi ro.
- [ ] Với opaque, kiểm tra introspection semantics, cache TTL và outage.
- [ ] Refresh token revocation được phối hợp với access-token revocation nếu cần.
- [ ] Grant change + version bump là atomic.
- [ ] Có invalidation events/retry/reconciliation và multi-node tests.
- [ ] Fail closed khi không xác minh được current permission cho action nhạy cảm.

### Data authorization

- [ ] Scope/role chỉ là coarse-grained gate.
- [ ] Tenant membership và account enabled được lấy từ trusted source.
- [ ] Repository query có tenant/owner/resource policy phù hợp.
- [ ] DML bảo vệ state/version, tránh TOCTOU.
- [ ] Khi grant bị sửa đồng thời, transaction/locking consistency được định nghĩa.
- [ ] Cache authZ không chia sẻ sai giữa users/tenants.

### Tests và observability

- [ ] Test ALLOW trước revoke và DENY cùng token/session sau revoke.
- [ ] Test old token sau regrant vẫn DENY nếu dùng strict version.
- [ ] Test token mới với current version ALLOW.
- [ ] Test 401/403/404 đúng theo contract.
- [ ] Test JWT invalid signature/issuer/audience/expiry qua decoder thật.
- [ ] Test session logout, multi-device, Spring Session multi-node.
- [ ] Test introspection `active=false`, timeout, stale cache.
- [ ] Test policy store outage không tạo fail-open.
- [ ] Audit actor, action, resource, current version, token version, revoke time, decision, mutation outcome.
- [ ] Không log bearer token, refresh token, password hay credentials.

---

## 21. Tài liệu chính thức

1. [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, session persistence, explicit save và session management.
2. [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): `SecurityContextLogoutHandler`, invalidate HTTP session, clear context và CSRF logout.
3. [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContextHolder` và `GrantedAuthority`.
4. [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT verification, issuer/expiry validation và scope authority mapping.
5. [Spring Security 6.5 – OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection, `active` và scope mapping.
6. [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, bảo vệ service.
7. [Spring Security – Session Registry API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/session/SessionRegistry.html): tra cứu session theo principal.
8. [Spring Session – Reference](https://docs.spring.io/spring-session/reference/): distributed session repository và tìm session theo principal.
9. [Spring Security – Testing OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `MockMvc`, JWT test helpers và authorities.
10. [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation protocol và token families.
11. [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, metadata và introspection caching.
12. [RFC 7519 – JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `iat`, `jti`, signature-related token structure.
13. [RFC 9068 – JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims và validation trong access tokens.
14. [OAuth 2.0 Security Best Current Practice – RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): refresh token security, rotation và OAuth threat models.
15. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và object-level checks.

**Kết luận:** Khi quyền thay đổi nhưng session hoặc OAuth2 access token còn hiệu lực, không được giả định thay đổi sẽ tự xuất hiện trong `Authentication`/JWT cũ. Session cần được refresh/invalidate hoặc thêm current-grant check; JWT cần policy về TTL, revocation, denylist, introspection hoặc `authzVersion`; refresh token rotation không tự thu hồi mọi access token đã phát. Quan trọng nhất, Resource Server phải phân biệt **token hợp lệ** với **quyền hiện hành**, kết hợp scope với trusted user/tenant/ACL và bảo vệ DB mutation theo transaction/conditional update. Hãy kiểm thử cùng token cũ trước–sau revoke, sau regrant và qua nhiều node để chứng minh SLA thu hồi quyền thực sự được đáp ứng.