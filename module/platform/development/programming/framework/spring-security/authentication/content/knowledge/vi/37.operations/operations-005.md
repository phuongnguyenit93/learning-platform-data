# Timeout, giới hạn kết nối và ứng xử khi nguồn danh tính ngoài gặp lỗi

> **Bối cảnh:** Ứng dụng Spring Security phải xác minh người dùng hoặc token thông qua một hệ thống nằm ngoài tiến trình ứng dụng: LDAP/Active Directory qua LDAPS, nhà cung cấp danh tính (IdP) OAuth2/OIDC, dịch vụ introspection của opaque token, API hồ sơ/quyền hoặc kho người dùng từ xa. Khi hệ thống này chậm, quá tải hay không truy cập được, ứng dụng vẫn cần **giữ bí mật xác thực, từ chối quyền chưa chứng minh được, phản hồi trong thời gian có giới hạn và tránh làm sập chính mình vì chờ kết nối**. Bài tập trung vào timeout, giới hạn kết nối, lỗi hạ tầng và vận hành; ví dụ lấy Spring Boot 3.x / Spring Security 6.x và Java 17+ làm nền.

## 1. Mục tiêu học tập

Sau bài này, bạn cần phân biệt và thực hiện được:

1. Phân loại **sai mật khẩu/token**, **tài khoản bị khóa/vô hiệu**, **lỗi kết nối**, **timeout**, **TLS/PKI**, **IdP HTTP 429/5xx**, **sai cấu hình** và **lỗi kho dữ liệu**.
2. Chọn timeout cho DNS/connect/TLS/read/pool-acquire, request tổng thể và caller deadline; tránh hiểu nhầm một timeout riêng là bảo đảm toàn bộ operation hoàn tất đúng hạn.
3. Giới hạn số connection và **số operation xác thực đồng thời** (bulkhead), queue/pool wait, retry budget và circuit breaker để tránh queue vô hạn.
4. Biết khi nào **không được fail open** và cách phân biệt 401/403 với 429/503 trong lớp HTTP, không tiết lộ thông tin tài khoản.
5. Cấu hình timeout LDAP/JNDI và các điểm cân nhắc khi dùng Spring Security LDAP, OIDC discovery/JWKS hoặc opaque token introspection.
6. Thiết kế hành vi khi upstream không sẵn sàng: login mới, request thuộc session đã tồn tại, token JWT đã xác minh độc lập và operation cần tra cứu quyền realtime.
7. Kiểm thử latency, hết pool, retry storm, DNS/TLS lỗi, cache stale, failover, phục hồi và audit; tạo dashboard và runbook.
8. Hiểu ranh giới giữa **bằng chứng danh tính được xác minh** và **giá trị đã từng được cache**, không dùng dữ liệu cũ để lén bỏ qua xác thực.

**Nguyên tắc gốc:** Khi nguồn danh tính không trả lời, kết quả là **“chưa thể xác minh”** chứ không phải “mật khẩu sai” và càng không phải “người dùng hợp lệ”. Phân loại đúng giúp bảo mật, hỗ trợ người dùng, cảnh báo và SLA đều chính xác.

## 2. Bản đồ các nguồn danh tính ngoài và điểm phụ thuộc

| Nguồn | Cách giao tiếp | Điều được xác minh | Rủi ro khi lỗi |
| --- | --- | --- | --- |
| LDAP/Active Directory | LDAP/LDAPS, search, bind | User DN, password hoặc thuộc tính/group | Bind chậm, DC unreachable, referrals, TLS, stale pool |
| OIDC Login / OAuth2 Client | Discovery, authorization endpoint, token endpoint, UserInfo nếu dùng | Protocol state, code/token/claims theo cấu hình | Login redirect lỗi, token exchange timeout, mất SSO |
| OAuth2 opaque token | HTTP introspection | Token active, scope, issuer/subject theo trust contract | API request phụ thuộc IdP trong thời gian thực |
| JWT Resource Server | Xác minh chữ ký bằng khóa công khai/JWKS | Signature, `iss`, `aud`, `exp`, scope | Discovery/JWK refresh lỗi, unknown `kid`, cache hết hạn |
| DB hoặc REST UserDetailsService | JDBC/HTTP/RPC | Account state, password hash, quyền | Pool cạn, dead connection, replica lag |
| MFA external service | HTTP/gRPC hoặc push challenge | Yếu tố độc lập, nonce/challenge | Không được coi MFA thành công khi upstream timeout |
| Policy/authorization service | REST/gRPC, LDAP groups, entitlement DB | Có được thực thi một action cụ thể không | Quyền có thể không được xác minh tại thời điểm request |

Mỗi nguồn cần quyết định **tính criticality riêng**. Ví dụ endpoint resource server đã có chữ ký JWT và khóa xác minh hợp lệ trong bộ nhớ có thể không cần gọi IdP trên **mỗi** request, nhưng nếu mỗi request bắt buộc gọi introspection hoặc chính sách quyền realtime, upstream outage trực tiếp ảnh hưởng quyết định hiện tại.

Đừng dùng một quy tắc duy nhất “IdP down thì tất cả thành công/thất bại”. Hãy phân tích từng **trust boundary**: credential nào được xác minh ở đâu, bằng chứng có TTL gì, cần thu hồi tức thời hay không, và dữ liệu nào có thể tạm sử dụng theo chính sách đã duyệt.

## 3. Chuỗi thời gian thực tế của một lần đăng nhập

~~~text
Caller / Browser
    |
    |-- HTTP request nhận tại gateway
    |     |- queue/wait trước app (nếu có)
    |     |- WAF/rate limit và connection budget
    |
    v
Spring Security AuthenticationManager
    |
    |-- acquire bulkhead permit / connection từ pool
    |-- DNS lookup
    |-- TCP connect
    |-- TLS handshake + trust/hostname verification
    |-- LDAP bind / HTTP token exchange / introspection request
    |-- wait response bytes / LDAP response
    |-- parse + verify identity/claims + group lookup
    |
    v
Authentication outcome
    |
    +-- VERIFIED       -> principal/authorities tin cậy
    +-- INVALID        -> từ chối credential
    +-- UNAVAILABLE    -> lỗi hạ tầng, chưa xác minh
    +-- OVERLOADED     -> giới hạn tài nguyên, chưa xác minh
~~~

**Connect timeout** chỉ giới hạn một pha mở kết nối; **read/response timeout** giới hạn chờ dữ liệu hoặc phản hồi; **pool acquire timeout** giới hạn thời gian chờ slot; **overall deadline** giới hạn toàn bộ hành trình ở một mức cao hơn. Một thư viện có thể thêm thời gian cho DNS, TLS, redirect, nhiều LDAP URLs, retry hoặc parsing mà không thuộc cùng một timeout.

Hãy phân biệt:

- **Server-side inbound deadline:** app cho phép request login tồn tại tối đa bao lâu trước khi từ chối.
- **Upstream operation deadline:** tổng giới hạn cho một lần xác minh ngoài.
- **Per-attempt timeout:** giới hạn cho mỗi lần gọi cụ thể tới upstream.
- **Caller timeout:** client/gateway có thể bỏ cuộc trước khi backend ngừng xử lý.
- **Idle/read timeout:** không nhất thiết là hard wall-clock deadline nếu response liên tục nhỏ giọt.
- **Pool wait:** nếu không lấy được connection/permit, cần phản hồi sớm thay vì chờ vô hạn.
- **Queueing:** hàng đợi có thể làm timeout tổng bị vượt dù socket hoạt động nhanh.

Một request đã bị caller hủy vẫn có thể tiếp tục chạy ở backend nếu không có cancellation/timeout propagation; phải kiểm thử và có ngân sách tài nguyên độc lập.

## 4. Phân biệt lỗi credentials với lỗi hạ tầng

| Sự kiện có bằng chứng từ nguồn | Nhóm nội bộ | Authentication | HTTP gợi ý theo loại endpoint |
| --- | --- | --- | --- |
| LDAP bind trả invalid credentials, IdP từ chối token rõ ràng | `INVALID_CREDENTIALS` | Reject | Form login: failure redirect chung; API: 401 |
| Unknown username theo repository đã truy vấn thành công | `UNKNOWN_SUBJECT` | Reject | Public response chung để chống enumeration |
| Account disabled/locked được xác nhận | `ACCOUNT_NOT_ALLOWED` | Reject | Public response chung; không cấp phiên |
| Network connect refused, DNS failure, upstream reset | `UPSTREAM_UNAVAILABLE` | **Chưa thể xác minh** | 503/5xx theo policy, không 200 |
| Socket/read/operation deadline | `UPSTREAM_TIMEOUT` | **Chưa thể xác minh** | 503 hoặc 504 ở gateway theo kiến trúc |
| Không lấy được permit/pool connection | `AUTH_CAPACITY_EXHAUSTED` | **Chưa thể xác minh** | 503 hoặc 429 theo nguồn giới hạn |
| IdP trả 429, `Retry-After` | `UPSTREAM_RATE_LIMITED` | **Chưa thể xác minh** | 503/429 theo hợp đồng, tôn trọng retry budget |
| IdP trả 500/502/503, JSON lỗi, phản hồi thiếu trường | `UPSTREAM_PROTOCOL_FAILURE` | **Chưa thể xác minh** | 503/5xx; cảnh báo |
| TLS certificate expired, hostname không khớp, untrusted CA | `TRUST_FAILURE` | **Chưa thể xác minh** | 5xx + alert khẩn; tuyệt đối không tắt TLS |
| Caller gửi token JWT sai signature/issuer/audience/expiry | `INVALID_TOKEN` | Reject | 401; không liên quan IdP downtime |
| JWT dùng `kid` chưa có và JWKS fetch lỗi | `KEY_MATERIAL_UNAVAILABLE` | **Chưa thể xác minh** | Không được accept token chưa xác minh |
| Quyền yêu cầu không có trong claims/authority đã xác minh | `INSUFFICIENT_AUTHORITY` | Authenticated, deny operation | 403 |

**Không có bằng chứng ≠ bằng chứng không hợp lệ.** Một `SocketTimeoutException` không chứng minh password sai; một LDAP timeout không chứng minh user không tồn tại. Cũng không được chuyển mọi `NamingException` thành `BadCredentialsException`. Phân loại ở adapter kết nối, ghi reason category an toàn và trả kết quả không làm lộ username/secret.

**HTTP status phụ thuộc protocol:** Browser form login thường redirect khi credentials sai; REST authentication endpoint thường trả 401; API gateway có thể dùng 502/503/504 khi upstream outage. Bảng chỉ nêu gợi ý, không khẳng định Spring mặc định map chính xác mọi trường hợp. Cần cấu hình error boundary và kiểm thử ứng dụng thực tế.

## 5. Đặt timeout như một “ngân sách” chứ không rải số tùy ý

Ví dụ chính sách **minh họa**, không phải best practice mặc định:

| Thành phần | Ngân sách minh họa |
| --- | ---: |
| Gateway tổng request | 3.000 ms |
| App tổng authentication deadline | 2.400 ms |
| Chờ bulkhead/pool slot | Tối đa 100 ms |
| Kết nối tới upstream | Tối đa 400 ms |
| Đợi upstream response | Tối đa 1.200 ms |
| Xử lý parse, map account và commit session | Khoảng 200 ms |
| Phần dự phòng cho scheduling/TLS/DNS | Phần ngân sách còn lại |

Các khoản không luôn cộng tuần tự đơn giản: một số pha chồng nhau, một số thư viện áp dụng timeout trên từng địa chỉ/attempt. Do đó phải thiết kế **overall deadline** và truyền thời gian còn lại xuống từng operation. Nếu gateway chờ 3 giây mà client chờ 2 giây, backend có thể phí tài nguyên chạy sau khi người dùng đã bỏ cuộc.

### Công thức quyết định tổng

~~~text
remaining = overallDeadline - now()

if remaining <= 0:
    return UPSTREAM_TIMEOUT

acquirePermit(wait <= min(poolWaitCap, remaining))
connectTimeout = min(connectCap, remainingAfterAcquire)
readTimeout    = min(readCap, remainingAfterConnect)
parseAndCommit only if enough remaining and verification succeeded
~~~

Đây là **pseudocode điều phối**; Java `HttpClient.connectTimeout(...)` và `HttpRequest.timeout(...)` có semantics riêng, không tự thay thế một deadline xuyên toàn bộ Spring filter, LDAP referrals và giao dịch DB. Với blocking APIs không hỗ trợ cancellation đúng, cần thêm bulkhead và tài nguyên worker được giới hạn, không tin một `Future.cancel(true)` luôn cắt được I/O đã kẹt.

### Chọn ngưỡng theo dữ liệu

- Đo p50/p95/p99 latency trên đường mạng thực, kể cả lỗi và connection setup, ở từng vùng/IdP.
- Giữ timeout dài đủ tránh false outage trong giờ cao điểm, nhưng ngắn đủ không tích tụ hàng nghìn request.
- Đặt gateway/client/app/upstream deadlines **có thứ bậc**; tránh nhiều timeout sát nhau gây hỗn loạn chẩn đoán.
- Tính startup, pool cold, DNS miss, TLS handshake, LDAP multiple URLs, failover và cold JWKS fetch.
- Tránh một giá trị “30 giây” cài cho mọi bước: pool 30 giây * concurrent requests có thể làm hết thread.
- Test khi upstream phản hồi chậm nhưng không timeout để phát hiện queue và p99 trước khi outage.

## 6. Giới hạn kết nối không đồng nghĩa giới hạn xác thực đồng thời

Một pool có `maxTotal=20` **không tự đảm bảo** chỉ có 20 request login đang chạy. Request có thể đang chờ pool, parse dữ liệu, xử lý password encoder, chờ DNS, chờ retries hoặc gọi upstream khác. Cần phân biệt:

1. **Connection pool max:** số kết nối mở tới LDAP/HTTP/DB/IdP.
2. **Max concurrent authentication operations:** số attempt nhận được permit qua bulkhead.
3. **Pool-acquire timeout:** request được đợi slot bao lâu.
4. **Pending queue capacity:** bao nhiêu operation có thể xếp hàng; queue phải hữu hạn.
5. **Per-identity/source rate limit:** nguồn gửi request quá nhanh có bị giới hạn trước khi tính password hay gọi IdP không.
6. **Remote provider quota:** IdP có rate limit/cost trên mỗi bind hoặc introspection.
7. **Worker thread capacity:** servlet/virtual-thread executor, socket/event-loop và hạ tầng đệm.
8. **Global budget cho nhiều instance:** 20 connections * 15 pods = 300 connections tại IdP, có thể vượt quota mà một pod không nhận ra.

### Little’s Law để trực giác hóa

~~~text
in_flight_operations ≈ arrival_rate_per_second × average_duration_seconds
~~~

Nếu app nhận 100 authentication requests/giây và mỗi request chờ upstream 1 giây, trung bình có thể có xấp xỉ 100 operation in flight. Khi upstream chậm lên 5 giây, với cùng lưu lượng, xấp xỉ 500 operation sẽ tích tụ nếu hệ thống không giới hạn. Kết quả là cạn connections/threads/memory dù app không có lỗi code.

**Bulkhead** bảo vệ vùng xác thực: nếu số operation đồng thời đạt trần, từ chối nhanh với error category `AUTH_CAPACITY_EXHAUSTED`/503, không xếp hàng vô hạn. Ngưỡng phải dựa trên p99, throughput, khả năng IdP và số pod. Cần cân nhắc công bằng: một botnet không được chiếm mọi permit khiến user hợp lệ không thể đăng nhập; edge rate limiting và ưu tiên traffic đã xác định tin cậy có thể giúp, nhưng không được tạo “đường đặc quyền” chỉ bằng header do client tự khai.

### Pool cho LDAP bind có rủi ro đặc thù

Các connection có thể mang trạng thái xác thực/bind. Không tái sử dụng mù quáng một connection đã bind dưới tài khoản A để xác thực B. Chính sách pooling khác giữa **service-account search context** và **per-user bind**. Xem semantics của Spring LDAP context source/JNDI pool, giới hạn lifetime/idle, kiểm tra stale connections, không giữ plaintext password trong cache, và đảm bảo mỗi phép xác thực được thực thi bằng identity đúng.

## 7. Chính sách ứng xử: fail closed nhưng không tự tạo outage dây chuyền

**Fail closed** nghĩa là **không cấp quyền mới khi không có bằng chứng hợp lệ**; nó không có nghĩa mọi endpoint của hệ thống phải trả 503 vô thời hạn.

| Hoàn cảnh | Quy tắc bảo mật | Phương án availability |
| --- | --- | --- |
| Đăng nhập mới bằng LDAP khi LDAP down | Không cấp Authentication từ dữ liệu cũ chưa được phép dùng | Trang báo lỗi tạm thời, retry sau, alert |
| Kết thúc MFA từ external MFA provider đang down | Không tự đánh dấu factor đã thành công | Cho thử lại có giới hạn hoặc flow recovery được xác minh |
| OIDC authorization-code callback khi token endpoint down | Không coi code chưa trao đổi thành access token | Giữ flow state trong TTL, cho khởi động lại login |
| Opaque token introspection down | Không đoán token `active=true` | Cache kết quả hợp lệ chỉ nếu chính sách revocation/TTL cho phép; nếu không reject |
| JWT với key, issuer/audience/expiry đã được verify local | Có thể chấp nhận theo validator đang hoạt động | Không bắt buộc gọi IdP mỗi request nếu thiết kế local verify |
| JWT có unknown `kid` và JWKS unavailable | Không verify được signature -> không accept | 5xx/503 theo decoder/error policy, alert key fetch |
| User đã có session local hợp lệ từ trước | Tùy policy: giữ session tới TTL nếu không cần external check mỗi request | Không âm thầm mở rộng TTL/permissions; revoke/step-up nếu chính sách yêu cầu |
| Operation phải tra quyền realtime từ external policy engine | Không cho thao tác nếu không xác minh được quyền | Chế độ read-only hạn chế khi được phê duyệt, hoặc 503 |
| Health/status endpoint public | Có thể trả tình trạng degraded không chứa secrets | Giữ monitoring/incident route theo RBAC |

**Một lần đăng nhập không phải toàn bộ phiên:** Nếu user có session đã được xác thực và lưu local, việc LDAP down sau đó không nhất thiết có nghĩa phải invalidate ngay toàn bộ session; quyết định này phụ thuộc chính sách **account disable/revocation freshness**. Nếu hợp đồng yêu cầu mỗi request phải kiểm tra account active từ LDAP, outage khiến quyết định chưa hoàn tất; cần ứng xử chặt. Không dùng “user từng đúng password” để mở **phiên mới** bằng một cache xác minh cũ mà chưa được thiết kế cho mục đích đó.

### JWT/JWKS khác opaque token introspection

- Với JWT ký đúng, `JwtDecoder` có thể xác minh chữ ký, hạn, issuer/audience **tại chỗ** nếu có key tin cậy trong cache. Outage IdP không phải lúc nào làm API ngừng nhận JWT.
- Khi key mới xuất hiện hoặc cache hết hạn, resource server có thể cần fetch JWKS. Không tắt signature verification, không chấp nhận mọi `kid`/algorithm và không cache khóa công khai vô thời hạn không có chiến lược rotate.
- Với opaque token introspection, quyết định `active` thường cần response từ authorization server. Cache introspection có thể làm revocation chậm; TTL/circuit behavior phải được thỏa thuận.
- Với OIDC Login, authorization code exchange, `state`/nonce và ID token validation phải hoàn tất; IdP outage không cho phép biến một code chưa verify thành user đã đăng nhập.

## 8. LDAP/LDAPS: timeout JNDI mà người vận hành cần biết

JDK default JNDI LDAP provider hiểu các environment properties:

| Property | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | milliseconds, dạng String | Giới hạn chờ tạo kết nối LDAP/TCP |
| `com.sun.jndi.ldap.read.timeout` | milliseconds, dạng String | Giới hạn chờ phản hồi thao tác LDAP |
| `Context.PROVIDER_URL` | URL(s) | Nguồn LDAP/LDAPS; có thể có nhiều URL |
| `Context.SECURITY_AUTHENTICATION` | `simple` hoặc cơ chế khác | Phương thức bind |
| `Context.SECURITY_PRINCIPAL` | Distinguished Name/identity | Danh tính bind |
| `Context.SECURITY_CREDENTIALS` | Secret | Không log/copy vào audit |
| `java.naming.referral` | Chính sách referral | Có thể làm thêm round trips/đường mạng |

Giá trị timeout phải **lớn hơn 0**; giá trị 0 hoặc âm có thể có ý nghĩa chờ theo mặc định hay vô hạn tùy property. Nếu để trống `read.timeout`, LDAP operation có thể chờ rất lâu. Oracle lưu ý với danh sách nhiều LDAP URLs, connect timeout có thể được áp cho **từng URL**; vì vậy tổng thời gian failover có thể dài hơn một connect timeout.

### Mảnh Java cấu hình JNDI/LDAPS (không chạy độc lập)

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

// Mảnh code nằm trong một method và có credentials được cấp an toàn.
// TLS certificate + hostname verification phải được cấu hình đúng.
Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY, "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://directory.example.test:636");
env.put("com.sun.jndi.ldap.connect.timeout", "800");
env.put("com.sun.jndi.ldap.read.timeout", "1500");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL, userDnFromTrustedLookup);
env.put(Context.SECURITY_CREDENTIALS, passwordFromLogin);

DirContext ctx = null;
try {
    ctx = new InitialDirContext(env);
    // Bind thành công chỉ chứng minh directory chấp nhận credentials.
    // Ứng dụng vẫn phải kiểm tra trạng thái account và quyền theo policy.
} finally {
    if (ctx != null) {
        ctx.close();
    }
}
~~~

Đoạn trên **không phải file compilable độc lập** vì biến `userDnFromTrustedLookup` và `passwordFromLogin` phải đến từ một flow đã được kiểm soát. Không nối trực tiếp username chưa kiểm tra thành DN hoặc LDAP filter vì có nguy cơ LDAP injection; dùng search filter escaping/parameterization phù hợp. Không in credentials trong exception, dump Hashtable hoặc log `env`.

### LDAPS/StartTLS và phân loại lỗi

- Dùng LDAPS hoặc StartTLS đúng chính sách, **kiểm tra certificate chain và hostname**; đừng đặt trust-all socket factory để chữa lỗi certificate.
- Connection timeout, read timeout, SSL handshake failure, certificate expired và LDAP referral lỗi là **sự cố kết nối/trust**, không phải invalid password.
- Khi directory trả **invalid credentials rõ ràng** từ bind, mới phân loại credential sai theo adapter. Kết quả `NameNotFound` do search DN không đồng nghĩa với network timeout; lý do có thể là unknown account hoặc sai base DN.
- Nếu dùng một tài khoản service để search rồi bind bằng user, tách lỗi service bind (secret cấu hình hỏng) khỏi user bind sai password; đừng khóa user vì service-account hết hạn.
- Kiểm thử domain controller failover, DNS, referral, stale pooled connection và TLS rotation, vì connect/read timeout không bao trùm mọi phụ thuộc.

## 9. Spring Security LDAP: vai trò của lớp xác thực và context

Spring Security LDAP có `BindAuthenticator`/LDAP authentication provider để kiểm tra credentials thông qua bind, và `LdapContextSource` (từ Spring LDAP) để quản lý thông tin kết nối. Một cấu hình hoặc adapter phải gắn đúng:

- Endpoint `ldaps://...`, base DN, service credentials (nếu dùng), pool strategy.
- JNDI connect/read timeout ở môi trường context source, hoặc connection settings của provider LDAP đã chọn.
- Quản lý referral/search/attribute lookup và filter escaping.
- Việc tạo `Authentication` thành công **chỉ sau khi** LDAP xác minh và chính sách account/group được kiểm tra.
- Phân loại lỗi: unknown user/invalid password, LDAP unavailable, timeout, TLS trust failure, service-account failure.
- Limits: bulkhead/queue/connection pool bao quanh **toàn bộ LDAP bind/search path**, không chỉ một method.

**Không coi `BindAuthenticator` tự đảm bảo circuit breaker, per-account retry budget hoặc nguồn thư mục HA.** Những cơ chế này cần kiến trúc hoặc thư viện resilience khác. Khi dùng `LdapContextSource` với pool, kiểm tra connection reuse và identity binding semantics; connection của service-account search có lifecycle khác một per-user bind. Spring Security/LDAP/Boot release khác nhau có thể có DSL và property names khác; đối chiếu Javadoc và dependency version thực tế trước khi paste cấu hình.

### Lựa chọn kiến trúc search + bind

~~~text
Login: username/password
    |
    +-- Normalize/validate username (không LDAP filter injection)
    +-- Search user DN qua service-account connection
    |       |-- timeout/infra lỗi -> AUTH_SOURCE_UNAVAILABLE
    |       +-- not found -> generic auth failure
    |
    +-- LDAP user bind với password
            |-- invalid credentials -> BAD_CREDENTIALS
            |-- timeout/TLS/referral -> AUTH_SOURCE_UNAVAILABLE
            +-- success -> user DN/identity xác thực
    |
    +-- Group/role lookup
            |-- nếu bắt buộc cho permission, lỗi -> chưa hoàn tất quyền
            +-- success -> Authentication với authorities đã chứng minh
~~~

Nếu group lookup fail sau khi bind đúng password, không tự cấp `ROLE_ADMIN` theo cache vô hạn. Có thể phân biệt “password verified, authorization unavailable”, nhưng chỉ cấp quyền nếu policy nguồn entitlement cho phép và freshness đáp ứng. Một số ứng dụng có role cache với TTL, invalidation và revocation SLA; đó là một **quyết định security riêng**, không phải fallback mặc định.

## 10. OIDC/OAuth2: discovery, token exchange, JWKS và introspection

### OIDC Login / OAuth2 Client

Login qua OIDC có thể cần các cuộc gọi tới:

1. Provider discovery/metadata (tùy cấu hình và thời điểm).
2. Authorization endpoint qua browser.
3. Token endpoint để đổi authorization code.
4. JWKS để xác minh ID token/access token.
5. UserInfo endpoint nếu ứng dụng cần dữ liệu từ đó.
6. Logout/revocation endpoints theo hợp đồng.

Mỗi bước có timeout, retry/callback validity và error mapping riêng. Một lỗi 5xx tại token endpoint **không chứng minh authorization code sai hay user sai password**. Ngược lại, `invalid_grant` được IdP trả một cách hợp lệ không tự động là network outage.

**Cẩn trọng retry token exchange:** Authorization code thường có tính dùng một lần. Nếu token exchange trả timeout sau khi IdP đã xử lý, gửi lại code có thể gặp `invalid_grant`; phải xử lý outcome không rõ, protocol state và retry policy của provider. Đừng retry mù quáng theo vòng lặp trong login filter. Với OIDC browser, callback state/nonce vẫn phải được kiểm tra và hết hạn đúng policy.

### JWT Resource Server

Ví dụ cấu hình minh họa Boot resource server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
~~~

Đây là các URI **minh họa**, phải thay bằng issuer và JWKS endpoint thực của provider. Khi khai báo `jwk-set-uri` trực tiếp cùng `issuer-uri`, resource server có thể khởi động mà không cần ping discovery endpoint, trong khi vẫn validate claim `iss` theo cấu hình. Điều đó giảm phụ thuộc **startup** chứ không loại bỏ nhu cầu tải/cập nhật JWK khi xác minh token sử dụng key chưa có.

**Không nhầm cache key với bỏ xác thực.** Token có signature/issuer/audience/exp sai vẫn phải bị từ chối. Nếu JWKS không tải được và không có key tương ứng, không cho phép token với `kid` mới chỉ vì IdP down. Đặt cache TTL/refresh phù hợp key rotation và revocation expectations; không tin claims mà chưa verify.

### Opaque token introspection

Nếu API dựa trên endpoint introspection, mỗi request hoặc cache miss có thể phải gọi HTTP để xác định `active`. Khi IdP down:

- Không tự biến kết quả chưa biết thành `active=true`.
- Không gán lại scopes theo request header do client cung cấp.
- Nếu cache kết quả `active=true`, phải định nghĩa TTL, scope, revocation SLA, clock/expiry và key theo token digest an toàn.
- Nếu privacy/security yêu cầu revocation gần realtime, cache positive quá dài có thể vi phạm policy.
- Phân biệt introspection 401 do **client credentials của resource server sai** với một token thật sự inactive; đây là lỗi cấu hình/upstream chứ không phải mọi người dùng tự nhiên sai password.

## 11. HTTP client Java 17: timeout kết nối và timeout request khác nhau

Mảnh Java sau cho thấy cách cấu hình **thời gian kết nối** tại `HttpClient` và **thời gian request** tại `HttpRequest`. Nó dùng endpoint `https://...example.test` minh họa, không phải chương trình gọi thực tế hoàn chỉnh và **không gửi bất kỳ token/secret nào**.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://idp.example.test/health"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();

// Phần gửi/parse response và contract auth thực tế phải do adapter
// triển khai: không coi HTTP 200 tự động là identity verified.
~~~

**Khi gửi introspection/token request thực tế**, phải có authentication client theo chuẩn IdP, TLS, redirect policy, encoding và secret management; không đưa access token/refresh token vào URL query, logs hay metrics. `HttpConnectTimeoutException`/`HttpTimeoutException` thuộc nhóm hạ tầng, không phải bad credentials. `InterruptedException` cần khôi phục interrupt flag nếu dùng blocking `send(...)` và trả lỗi đúng. Đừng log request body/header chứa token khi debug.

**Không tự hiểu “request timeout = end-to-end login timeout”.** HTTP call còn nằm trong filter, token parsing, LDAP group mapping, DB session persistence và có thể nhiều redirects/retries. Tổng deadline phải được quản lý ở tầng workflow.

## 12. Retry, backoff và retry storm

**Mặc định không retry vô điều kiện một phép xác thực.** Một password bind lặp lại có thể tăng failed-attempt count, gây khóa account hoặc tăng tải LDAP. Một token exchange có thể không idempotent. Một MFA challenge có thể bị consume ở upstream dù app nhận timeout.

| Operation | Retry có thể phù hợp? | Rủi ro/cần kiểm soát |
| --- | --- | --- |
| Fetch OIDC metadata qua GET | Có thể, rất hạn chế, theo deadline | Có cache/ETag, tránh bão truy vấn |
| Fetch JWKS qua GET | Có thể có backoff/cache/single-flight | Unknown `kid` không được chấp nhận khi thất bại |
| LDAP search/read-only | Phụ thuộc provider và state, rất hạn chế | Pool saturation, referrals, duplicate work |
| LDAP user bind password | Tránh retry mù quáng | Account lockout, password spray amplification |
| OAuth2 authorization-code exchange | Thường không retry mù quáng | Code dùng một lần, timeout outcome không chắc |
| Opaque token introspection | Nếu provider contract cho phép, budget ngắn | Tải mỗi request, cache revocation |
| MFA verification/challenge consume | Không retry nếu thiếu idempotency | Chống replay và attempt counters |
| Đổi mật khẩu/revoke token | Chỉ retry với idempotency key và policy | Có thể đã commit ở nguồn ngoài |
| TLS certificate/hostname failure | Không | Không chữa bằng retry hoặc bỏ TLS verification |
| Explicit invalid credentials/invalid token | Không | Không thể thành đúng sau vài milliseconds |

### Retry budget

Một cơ chế phù hợp có thể cho **0 hoặc 1 retry** với operation read-only/idempotent, exponential backoff + jitter nhỏ, chỉ khi còn tổng deadline và circuit vẫn cho phép. Không dùng 3 retry mặc định trên cả 10 pods và 5 endpoints vì upstream chậm sẽ nhận tải nhân lên gấp nhiều lần.

~~~text
maxAttempts = 1 hoặc 2 (tùy operation)
for each attempt:
    if deadline exhausted or circuit open: stop
    if permission/credential invalid: stop
    if TLS trust error: stop
    if transient upstream error and operation safe to retry:
         wait bounded jitter outside request thread when possible
         retry within remaining deadline
    else: stop
~~~

**Retry-after** do IdP trả phải được diễn giải trong giới hạn tổng deadline và tránh đồng bộ toàn bộ fleet retry cùng lúc. Nếu response `429` được trả với `Retry-After` lớn hơn thời gian client còn chờ, đừng giữ request mở chỉ để chờ; trả lỗi tạm thời với thông tin công khai phù hợp.

### Circuit breaker và bulkhead khác nhau

- **Circuit breaker** theo dõi lỗi upstream và từ chối sớm khi tỷ lệ lỗi vượt ngưỡng. Nó giảm tải IdP đang hỏng, có trạng thái closed/open/half-open.
- **Bulkhead** giới hạn số operation đồng thời để không làm cạn servlet threads/connections hoặc khiến login ảnh hưởng request khác.
- **Rate limiter** giới hạn tốc độ incoming source/account, chặn bot trước khi chúng làm tốn operation.
- **Timeout** hạn chế một attempt kéo dài.
- **Retry** có thể làm tăng tải; chỉ dùng trong ngân sách và operation an toàn.

Mỗi cơ chế cần có metrics, tình huống reset/hysteresis và kiểm thử **thử lại nửa-mở**. Không chỉ đặt breaker quanh network call rồi bỏ qua pool acquisition, DNS, group lookup hoặc serialization bị treo.

## 13. Java 17 chạy độc lập: phân loại upstream và giới hạn song song

Chương trình này là **mô phỏng chính sách vận hành**, không gọi LDAP/IdP thật, không kiểm tra password và không cấp Spring `Authentication`. Nó giúp thấy khác biệt giữa **credential invalid**, **upstream unavailable**, **timeout** và **bulkhead exhausted**, đồng thời chứng minh permit được release bằng `finally`.

Tệp `ExternalIdentityPolicyDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public final class ExternalIdentityPolicyDemo {

    enum UpstreamResult {
        VERIFIED, INVALID_CREDENTIALS, TIMEOUT, TLS_FAILURE
    }

    enum Decision {
        AUTHENTICATED, UNAUTHORIZED,
        TEMPORARILY_UNAVAILABLE, OVERLOADED
    }

    static Decision classify(UpstreamResult upstream) {
        return switch (upstream) {
            case VERIFIED -> Decision.AUTHENTICATED;
            case INVALID_CREDENTIALS -> Decision.UNAUTHORIZED;
            case TIMEOUT, TLS_FAILURE ->
                    Decision.TEMPORARILY_UNAVAILABLE;
        };
    }

    static final class AuthBulkhead {
        private final Semaphore permits = new Semaphore(2, true);

        Decision verify(UpstreamResult upstream) {
            if (!permits.tryAcquire()) {
                return Decision.OVERLOADED;
            }
            try {
                // Giả lập adapter đã có outcome từ provider.
                return classify(upstream);
            } finally {
                permits.release();
            }
        }

        boolean holdForTest() {
            return permits.tryAcquire();
        }

        void releaseForTest() {
            permits.release();
        }
    }

    public static void main(String[] args) {
        AuthBulkhead bulkhead = new AuthBulkhead();

        System.out.println("verified: " +
                bulkhead.verify(UpstreamResult.VERIFIED));
        System.out.println("bad credentials: " +
                bulkhead.verify(UpstreamResult.INVALID_CREDENTIALS));
        System.out.println("timeout: " +
                bulkhead.verify(UpstreamResult.TIMEOUT));
        System.out.println("tls failure: " +
                bulkhead.verify(UpstreamResult.TLS_FAILURE));

        boolean first = bulkhead.holdForTest();
        boolean second = bulkhead.holdForTest();
        System.out.println("slots held: " + first + "/" + second);
        System.out.println("pool exhausted: " +
                bulkhead.verify(UpstreamResult.VERIFIED));

        bulkhead.releaseForTest();
        System.out.println("after one release: " +
                bulkhead.verify(UpstreamResult.VERIFIED));
        bulkhead.releaseForTest();
    }
}
~~~

Biên dịch/chạy với **JDK 17+**, không cần Spring:

~~~bash
javac ExternalIdentityPolicyDemo.java
java ExternalIdentityPolicyDemo
~~~

Stdout **chính xác**:

~~~text
verified: AUTHENTICATED
bad credentials: UNAUTHORIZED
timeout: TEMPORARILY_UNAVAILABLE
tls failure: TEMPORARILY_UNAVAILABLE
slots held: true/true
pool exhausted: OVERLOADED
after one release: AUTHENTICATED
~~~

**Bài học:** Lỗi timeout/TLS không biến thành `UNAUTHORIZED`. Khi hai permit bị giữ, yêu cầu thứ ba bị chặn nhanh thay vì queue vô hạn; khi trả một permit, operation mới có thể tiến hành. `Semaphore` chỉ giới hạn trong **một JVM**, không thay thế quotas của IdP cho toàn cụm.

**Những phần cố ý không làm trong demo:** timeout thực tế (outcome `TIMEOUT` là dữ liệu giả), HTTP connection pooling, circuit breaker, retry, cancellation, user lookup, mật mã hoặc phát session. Trong production, phải bao quanh network call thật, dùng `try/finally`, shared quotas nếu cần, breaker metrics, admission policy và thu thập số request bị reject. Không tự gọi `classify(VERIFIED)` từ request parameter do client truyền: trạng thái VERIFIED phải do **adapter tin cậy** trả sau khi xác minh credential hoàn chỉnh.

## 14. Spring Security: lỗi nào nên được bọc ở adapter?

Ở layer authentication provider, Spring Security thường dùng `AuthenticationException` và các lớp cụ thể:

| Exception/category | Ngữ nghĩa gợi ý |
| --- | --- |
| `BadCredentialsException` | Nguồn **đã phản hồi xác nhận credential không hợp lệ** |
| `UsernameNotFoundException` | User lookup từ repository đã hoàn thành và không tìm thấy |
| `LockedException` / `DisabledException` | Nguồn dữ liệu/account policy xác nhận account không được đăng nhập |
| `AuthenticationServiceException` | Lỗi xảy ra trong dịch vụ authentication không thuộc lỗi credential |
| `InternalAuthenticationServiceException` | Một dạng lỗi nội bộ/service trong authentication provider |
| `AuthenticationException` custom có category | Dùng khi cần phân tách `UPSTREAM_TIMEOUT`, `TLS_FAILURE`, `POOL_EXHAUSTED` rõ ràng |

Các lớp cụ thể có thể thay đổi theo provider, đặc biệt LDAP/REST/IdP. **Không bắt mọi exception và trả `BadCredentialsException`**, không tạo principal “anonymous nhưng authenticated”, và không lưu credential/token trong message/cause được đưa ra logs công khai.

Một contract adapter minh họa:

~~~java
public interface ExternalIdentityVerifier {

    // Kết quả VERIFIED chỉ khi nguồn đáng tin đã xác minh hoàn chỉnh.
    VerifiedPrincipal verify(UserCredentials credential)
            throws IdentitySourceUnavailableException;

    // Các kiểu dưới là hợp đồng do ứng dụng định nghĩa.
    record UserCredentials(String username, char[] password) {}
    record VerifiedPrincipal(String stableUserId) {}
}

public class IdentitySourceUnavailableException extends RuntimeException {
    public IdentitySourceUnavailableException(String reason) {
        super(reason);
    }
}
~~~

Các lớp này là **mảnh interface**, không phải file Java độc lập; trong dự án thực tế nên tránh đặt nhiều public top-level types vào cùng một tệp và không để error reason chứa raw password/DN/URL có secret. Adapter thực tế phải giải mã/chuẩn hóa LDAP/OIDC responses và phân biệt invalid credentials với unavailable. Provider tạo `Authentication` sau VERIFIED, hoặc ném lỗi nội bộ thích hợp, không tự động dựa trên boolean do client cung cấp.

### AuthenticationManager có thể giấu sự cố trong luồng form login

Một `AuthenticationFailureHandler` mặc định có thể đưa nhiều `AuthenticationException` tới cùng `/login?error`. Điều này giúp tránh lộ account, nhưng **không đồng nghĩa** telemetry có thể gộp `BadCredentials` và `LDAP_TIMEOUT`. Hệ thống cần:

- Public response chung cho sai credential/unknown account/locked theo threat model.
- Error handling 5xx/503 hoặc trang “dịch vụ tạm thời không sẵn sàng” cho outage, theo hợp đồng HTTP.
- Audit category riêng: BAD_CREDENTIALS, ACCOUNT_DISABLED, UPSTREAM_TIMEOUT, TLS_FAILURE, POOL_EXHAUSTED.
- Không tăng bad-password lockout counter từ request **chưa được kiểm tra credential** vì IdP down.
- Không chuyển người dùng sang fallback yếu hơn (ví dụ local default password) chỉ vì LDAP không trả lời.
- Quy tắc phiên/MFA đầy đủ mới cho phép truy cập protected routes.

Nếu xây custom AuthenticationProvider, kiểm thử vị trí catch/translation: một lỗi runtime có thể bị framework biến thành 500 nếu không mapping, hoặc bị failure handler đưa về redirect chung. Không có một status mặc định đúng cho mọi phiên bản; phải viết integration tests cho **SecurityFilterChain thật**.

## 15. Lỗi thư mục và trạng thái account: khi nào mới được nói “sai mật khẩu”?

Với user lookup và bind:

~~~text
1) user lookup/search:
   - found -> xác định DN/canonical ID từ nguồn
   - not found -> unknown account (public response chung)
   - timeout/network error -> chưa biết user có tồn tại

2) user bind:
   - explicit LDAP invalidCredentials -> sai password theo bind
   - bind successful -> password factor verified
   - timeout/TLS/referral/service unavailable -> chưa biết password có đúng

3) authorities/group lookup:
   - succeeded -> quyền đã được xác minh
   - unavailable -> không tự cấp role cao, phải theo policy
~~~

Hãy dùng provider-specific exception mapping được kiểm thử qua test container/fake LDAP chứ không suy đoán dựa trên substring của exception message. LDAP service-account hết hạn có thể gây lỗi trên **mọi user**; nếu logic coi đó là sai password, hàng nghìn account sẽ bị khóa và tạo sự cố DoS thứ cấp.

### Thông báo public không cần tiết lộ nội bộ

- Credential sai: “Không thể đăng nhập. Hãy kiểm tra thông tin hoặc thử lại.”
- Nguồn danh tính unavailable: “Dịch vụ đăng nhập tạm thời không sẵn sàng. Vui lòng thử lại sau.”
- Không nói “user A có trong AD nhưng mật khẩu sai”; không đưa DN, hostname, stack trace, client secret hoặc JWT raw vào response.
- Với API, status 503 có thể kèm `Retry-After` nếu có cơ sở để ước lượng; không hứa thời gian khôi phục mà chưa biết.
- Lỗi hạ tầng nên phát alarm; không gửi một email cho **mỗi** login thất bại gây notification storm.

**Kiểm tra side channel:** Nếu unknown user, bad password và disabled có response body/status/timing quá khác nhau, attacker có thể dò account. Có thể trả response chung cho account-state cases trong khi phân biệt outage hạ tầng theo incident; bản vá/framework code và test timing vẫn cần được xem xét.

## 16. Cache và fallback: điều gì được phép giữ khi IdP lỗi?

Không có một câu trả lời chung “cache là tốt” hoặc “cache là sai”. Đánh giá theo **loại chứng cứ**:

| Dữ liệu | Có thể cache trong điều kiện nào? | Rủi ro |
| --- | --- | --- |
| OIDC discovery metadata | TTL/validation theo provider, nguồn cấu hình tin cậy | Metadata đổi, endpoint/key rotation |
| JWKS public keys | TTL/version và verify signature/`iss`/`aud`/`exp` | Key revoked/rotated; unknown `kid` |
| User profile display name | TTL và fallback có ràng buộc | Hiển thị thông tin cũ, ít nhạy cảm hơn auth |
| Group/permissions | Chỉ nếu revocation SLA và TTL chấp nhận | Cấp quyền vượt thời gian thu hồi |
| Previous successful LDAP bind | **Không dùng mặc định để đăng nhập mới** | Biến mật khẩu cũ/cache thành yếu tố xác thực |
| Opaque token introspection positive result | TTL ngắn và chính sách revocation rõ | Token bị thu hồi vẫn có thể được chấp nhận |
| Session local đã được phát hợp lệ | Có thể tiếp tục theo session TTL/policy | Account bị offboard chưa được phát hiện |
| Rate limit/account lock state | Store chia sẻ với TTL, nguyên tử | Data stale có thể bỏ bảo vệ hoặc khóa oan |

Nếu sản phẩm hỗ trợ **offline authentication**, đó là tính năng bảo mật được thiết kế/kiểm định riêng với cryptographic local verifier, device binding, TTL, revocation và policy; không tự bật bằng cách giữ raw username/password hoặc cache `Authentication` từ lần đăng nhập trước. Cache JWKS public key khác hoàn toàn cache raw token hoặc password.

**Phục hồi sau outage:** Có thể nhiều request đồng thời phát hiện JWKS hết cache và cùng gọi IdP, gây thundering herd. Dùng cache stampede protection/single-flight, bounded refresh và jitter; không một request đến sau timeout nào được chấp nhận nếu signature không được verify.

## 17. Health checks, readiness và circuit health

Không nên gắn một LDAP/IdP call thật vào **mọi** request liveness probe:

- **Liveness:** tiến trình có còn sống và có thể tiến bộ? Upstream down không nhất thiết nghĩa app cần restart liên tục.
- **Readiness:** pod có đủ phụ thuộc để nhận traffic chức năng yêu cầu không? Có thể dùng dependency status đã được cache trong thời gian ngắn theo chính sách.
- **Functional auth health:** kiểm tra độ trễ và khả năng liên lạc của identity source bằng *synthetic* account/service identity bảo vệ riêng, với tần suất có giới hạn.
- **SLO:** đo phần trăm login hoàn tất đúng hạn và lỗi auth hạ tầng, không gộp user gõ sai password vào upstream availability SLO.

Một read probe không nên liên tục thử bind password sai khiến synthetic account bị lock hoặc gây tải AD. Dùng credential dành riêng, scope tối thiểu, secret manager và kiểm soát tần suất. TLS monitor phải phát hiện certificate sắp hết hạn và hostname chain; DNS và route connectivity cần test độc lập.

Nếu mọi pod cùng thấy IdP down và readiness chuyển false, có thể khiến toàn hệ thống mất tuyến phục vụ cả endpoint không cần IdP. Cần **thiết kế readiness theo chức năng** hoặc giữ service hoạt động degraded có kiểm soát. Liveness luôn restart do upstream down dễ gây restart storm và làm outage dài hơn.

### Circuit breaker operational state

~~~text
CLOSED: nhận call bình thường
   |
   | lỗi timeout/network vượt ngưỡng trong window
   v
OPEN: không gọi upstream, trả nhanh UNAVAILABLE
   |
   | wait duration hữu hạn
   v
HALF_OPEN: cho một số probe có kiểm soát
   |
   +-- success ổn định -> CLOSED
   +-- continued failure -> OPEN
~~~

Circuit breaker tính **lỗi hạ tầng** khác explicit BAD_CREDENTIALS. Nếu nó coi sai mật khẩu của người dùng là lỗi upstream, một cuộc password spraying có thể mở circuit và chặn login của toàn bộ user: đây là dạng **DoS do phân loại sai**. Test condition này bắt buộc.

## 18. Quan sát và nhật ký mà không rò thông tin danh tính

Metrics nên dùng labels ít cardinality:

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `identity_upstream_requests_total{source,result}` | Requests theo nguồn, VERIFIED/INVALID/TIMEOUT/UNAVAILABLE |
| `identity_upstream_duration_seconds{source,operation}` | p50/p95/p99 latency search/bind/token/JWKS |
| `identity_bulkhead_inflight{source}` | Operation hiện đang chiếm permit |
| `identity_bulkhead_rejected_total{source}` | Số request bị từ chối vì full |
| `identity_connection_pool_wait_seconds{source}` | Thời gian chờ connection |
| `identity_connection_pool_active{source}` | Connections đang sử dụng |
| `identity_connection_pool_pending{source}` | Waiters đang chờ |
| `identity_circuit_state{source}` | Closed/open/half-open |
| `identity_auth_infra_errors_total{category}` | DNS/TLS/timeout/5xx/429/parse |
| `identity_retry_attempts_total{operation}` | Retry rate tránh storm |
| `jwt_jwks_cache_miss_total{issuer}` | Cache refresh và key rotation |
| `login_completed_total{method,outcome}` | Kết quả login end-to-end, không gộp provider events |

Các tên trên chỉ là **quy ước thiết kế gợi ý**, không phải metric Spring tự xuất đúng y hệt. `issuer` label cần là alias hữu hạn đã allowlist; không đưa raw URL/token/username/session ID/IP/device fingerprint thành metric labels.

**Audit** phải ghi event ID, thời gian UTC, identity source alias, outcome category, request/trace correlation ID, latency bucket và policy decision. Với invalid credentials, tránh log password, OTP, token, raw LDAP DN, bearer header, Authorization/Cookie. Với LDAP errors, giữ sanitized error code/exception class, **không** log toàn Hashtable môi trường JNDI chứa password hoặc refresh token.

**Cảnh báo hữu ích:**

- Tăng đột biến p99 bind/HTTP introspection latency.
- Đa số login trả `UPSTREAM_TIMEOUT` thay vì `BAD_CREDENTIALS`.
- Pool pending/permit rejected vượt ngưỡng trước khi tất cả request timeout.
- TLS certificate 7/3/1 ngày nữa hết hạn hoặc JWKS refresh fail/unknown `kid` tăng.
- Một region có timeout nhưng region khác bình thường (network partition).
- Retry attempts tăng nhanh hơn traffic inbound (retry amplification).
- Circuit mở lâu, half-open không phục hồi; synthetics lỗi nhưng liveness vẫn ổn.
- Fallback đang hoạt động ngoài chính sách hoặc cache entitlement quá TTL.

## 19. Runbook: IdP/LDAP ngừng phản hồi trong giờ cao điểm

### A. Phát hiện và khoanh vùng

1. Xác định ảnh hưởng: chỉ login mới, MFA challenge, JWT validation, opaque introspection, hay mọi API.
2. Kiểm tra lỗi theo **loại**: connect timeout, read timeout, pool exhaustion, 429, DNS, certificate, 5xx.
3. Đối chiếu latency trước/ sau sự cố, số pod, số connection tới DC/IdP, quota provider, retry rate.
4. Kiểm tra một vài synthetic probes có giới hạn, từ đúng vùng xảy ra sự cố; không spam binds vào directory.
5. Xác định certificate/secret rotation hoặc deployment mới có thay truststore, DNS, proxy, pooling hoặc host names không.
6. Bảo vệ audit: logging kết nối chậm không được làm treo thread thêm; không bật debug in secrets.

### B. Giảm tải trong khi sự cố tiếp diễn

1. Giữ **fail closed** ở các quyết định chưa được xác minh.
2. Dùng gateway throttling, giới hạn in-flight và circuit breaker để giảm call vào IdP đang yếu.
3. Nếu có nhiều DC/IdP endpoints được trust và quản trị hợp lệ, failover theo policy; **không** chuyển sang server không kiểm TLS hay identity source dự phòng không đồng nhất.
4. Tắt hoặc giảm **retry cho operation không idempotent**, tránh nhân tải 10 lần.
5. Ưu tiên phục vụ endpoint không cần nguồn ngoài, giữ health/incident UX hữu ích.
6. Người dùng đã có phiên hợp lệ có thể tiếp tục theo policy hiện hành; không tự cấp session mới bằng cache password cũ.
7. Với JWT đã có key và claims verified, duy trì local verification nếu thiết kế cho phép; nếu unknown `kid`, từ chối token chưa verify.
8. Thông báo tình trạng dịch vụ chung; không cho client biết account nào hợp lệ hoặc DC cụ thể để khai thác.

### C. Phục hồi và hậu kiểm

1. Xác minh IdP/LDAP healthy, TLS trust đúng, pool hồi phục và connections không leak.
2. Circuit half-open probe có giới hạn rồi đóng; không để toàn fleet retry đồng loạt ngay khi upstream vừa hồi.
3. Kiểm tra login mới thành công bằng test account, sai password vẫn bị từ chối, locked/disabled không bị mở.
4. Kiểm tra MFA, session persistence, JWT/JWKS refresh và opaque token flows riêng.
5. Đối chiếu audit/metrics để ước lượng số login thất bại do hạ tầng, không cộng chúng vào failed-password counts.
6. Điều chỉnh ngưỡng từ measured p99, wait time, saturation và provider quota, không tăng timeout vô hạn như cách “chữa nhanh”.
7. Viết postmortem với timeline, source-specific error categories, queue growth, retry amplification, blast radius và action items.

## 20. Kiểm thử bắt buộc trước khi đưa vào production

### Test đơn vị và policy

| Input từ adapter | Expected decision | Hành vi audit/rate counter |
| --- | --- | --- |
| Explicit credential reject | UNAUTHORIZED | Ghi BAD_CREDENTIALS, tăng counter đúng một lần |
| Explicit account locked | DENIED | Không coi là sai password mới |
| Correct credentials, permissions verified | AUTHENTICATED | Cấp principal/authority đúng, session theo policy |
| DNS failure / connect refused | TEMPORARILY_UNAVAILABLE | Không tăng bad-password counter |
| Read timeout sau khi gửi bind/token request | TEMPORARILY_UNAVAILABLE | Không retry mù quáng vì outcome chưa rõ |
| TLS certificate/hostname failure | TRUST_FAILURE / unavailable | Alert, không disable validation |
| Pool acquire timeout hoặc full bulkhead | OVERLOADED | Không giữ thread vô hạn hoặc làm counter user tăng |
| IdP HTTP 429 | UPSTREAM_RATE_LIMITED | Tôn trọng retry budget, không thundering herd |
| IdP HTTP 500/502/503 | UPSTREAM_UNAVAILABLE | Không tạo authenticated principal |
| JWKS unknown `kid` và fetch lỗi | UNVERIFIED | Không chấp nhận JWT mới chưa verify |
| JWT signed/claims valid bằng cached key | VERIFIED theo contract | Không tự gọi IdP nếu không cần |
| Group lookup fails sau LDAP bind success | INCOMPLETE_AUTHORIZATION | Không tự cấp role còn thiếu |

### Integration test Spring Security + fake upstream

- **Fake LDAP** trả invalid credentials: form failure chung, không cấp session; audit đúng.
- Fake LDAP chậm hơn `read.timeout`: phản hồi kết thúc theo ngân sách; không tăng password-failure count.
- LDAP service search timeout nhưng user bind chưa được thử: không giả là unknown account.
- LDAPS certificate expired/untrusted: không fallback sang insecure `ldap://`.
- Pool full: request bị reject/503 có giới hạn, app không hết servlet threads; permit được release sau mọi nhánh lỗi.
- Test 10 requests đồng thời, max in-flight 2: 8 request còn lại rejected/queued hữu hạn đúng contract, không vượt quota.
- OIDC discovery timeout lúc startup: nếu cấu hình `issuer-uri` only, có thể cần xử lý phụ thuộc discovery; `jwk-set-uri` trực tiếp giảm ping startup nhưng không bỏ issuer verification.
- Authorization-code token exchange timeout: không tạo login completed, không retry code mù quáng.
- JWT local valid khi IdP down: nếu cached trust material hợp lệ và claims đúng, request tiếp tục theo policy.
- JWT unknown `kid` khi JWKS down: fail closed, không được authenticated.
- Opaque token introspection down: không accept unknown token; cache TTL/revocation theo policy.
- Rate limiter/circuit breaker test: 100 bad credentials **không được** tính thành 100 upstream outages và mở circuit.
- Session đã tồn tại: IdP down nhưng app local session policy không yêu cầu check mỗi request thì hành vi phải đúng hợp đồng; không tự tạo session mới.
- Backend timeout sau verify nhưng trước persist session: không báo login completed khi session chưa commit.
- MockMvc/formLogin với provider thật và wiremock/mock LDAP hoặc mock HTTP transport: kiểm tra HTTP boundary, không chỉ method pure.
- Service recovery: half-open probes có giới hạn và pool kết nối không rò.
- Cấu hình endpoint fallback: không có anonymous admin, “allow all” filter hoặc ROLE_ADMIN từ cache hỏng.

### Load/chaos test và phát hiện DoS thứ cấp

1. Giả lập p99 tăng gấp năm và lưu lượng login tăng đồng thời: đo in-flight, rejected, queue/heap.
2. Giả lập cạn toàn bộ LDAP DC hoặc IdP endpoints, DNS fail, TLS failure, network packet loss và connection reset.
3. Multi-node: mỗi pod pool 20, 15 pods -> budget provider có thể là 300; kiểm tra quota global/fairness.
4. Tắt audit backend trong lúc IdP down: error handling không đẩy thêm thread/queue vô hạn.
5. Đổi client secret hoặc TLS certificate khi đang có connections pooled; phát hiện stale/revocation.
6. Diễn tập IdP gửi 429 kèm `Retry-After` và tất cả pods sắp hết deadline; không retry storm.
7. Random usernames/bot traffic: per-source limit không dùng backend password hash/LDAP bind không giới hạn.
8. Kiểm tra 503 UX vs invalid-password UX không lộ thông tin account/secret; metric phân biệt loại lỗi chính xác.
9. Kiểm tra worker-thread pool/executor saturation không cản endpoints không liên quan tới identity.
10. Đo thời gian phục hồi sau khi upstream trở lại, tránh tất cả circuit breakers đóng cùng lúc gây herd.

## 21. Lỗi phổ biến và cách sửa

| Lỗi triển khai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không đặt LDAP read timeout | Request có thể treo rất lâu | Cấu hình connect/read timeout dương và overall budget |
| Tăng timeout từ 3s lên 60s khi IdP chậm | Tích tụ hàng nghìn request/threads | Bounded bulkhead, hạn thời gian và đo latency |
| Pool max=100 nhưng 20 pods | IdP nhận tới 2.000 connections | Tính global capacity và provider quota |
| Không có pool-acquire timeout | Request chờ slot vô hạn | Bounded wait/queue, từ chối nhanh |
| Retry mọi lỗi login ba lần | Account lockout, IdP overload | Retry có điều kiện, chỉ safe/idempotent operations |
| Gộp `NamingException` thành bad password | Khóa account khi LDAP down | Phân biệt explicit invalid credentials với hạ tầng |
| LDAP bind user A rồi reuse connection cho B | Sai danh tính/bảo mật | Pooling theo đúng bind identity semantics |
| Trust-all TLS hoặc fallback HTTP | Credentials/claims bị lộ hoặc MITM | Certificate + hostname validation chuẩn |
| IdP down thì cho login bằng password từng cache | Fail open, mở đường takeover | Không cấp danh tính khi chưa xác minh mới |
| JWKS không tải được thì accept unknown `kid` | Signature bypass | Reject unverified token, alert |
| Cache group entitlement vô thời hạn | Quyền bị thu hồi vẫn có tác dụng | TTL/invalidations theo revocation SLA |
| Thấy HTTP 200 từ IdP là user authenticated | Không kiểm nội dung/token claims | Xác minh schema, status, issuer, audience, signature |
| Circuit breaker tính bad credentials là upstream error | Password spray gây outage cho toàn hệ | Metrics và breaker chỉ tính lỗi hạ tầng |
| Health liveness phụ thuộc IdP | Pod restart storm | Liveness theo tiến trình, readiness theo chức năng |
| Rate limit chỉ theo IP | Botnet đổi IP dễ bypass | Account + source + endpoint budgets |
| Log LDAP env hoặc Authorization header | Lộ service password/token | Field allowlist, secret redaction |
| Gửi warning email mỗi lần timeout | Notification flooding | Debounce/batch, alert qua ops channel |
| Session đang hoạt động bị revoke ngẫu nhiên khi LDAP tạm down | Người dùng bị DoS dù đã login hợp lệ | Session policy rõ theo trust freshness |
| Đo p50 mà bỏ p99/pool pending | Sự cố bị phát hiện quá muộn | P95/P99, queue wait, rejection và breakers |
| Không test lỗi sau khi upstream đã nhận request | Retry non-idempotent gây sai state | Test “response lost after commit”, idempotency |

## 22. Checklist triển khai vận hành

**Đặc tả và bảo mật**

- [ ] Đã phân loại LDAP/LDAPS, OIDC Login, JWT/JWKS, opaque introspection, UserDetails DB, MFA và policy services.
- [ ] Mỗi nguồn có deadline, retry budget, TLS trust, owner, rate limit và error taxonomy riêng.
- [ ] Không gộp invalid credentials với unavailable; không cấp session/role khi chưa chứng minh danh tính và quyền.
- [ ] Không bỏ TLS, không chuyển sang identity source yếu hơn hoặc login từ cache password cũ để “duy trì uptime”.
- [ ] Đã quy định rõ session hiện có vs login mới, entitlement freshness và revocation SLA.

**Giới hạn tài nguyên**

- [ ] Connect/read/request/pool wait/overall deadline đều có giá trị và mối quan hệ rõ.
- [ ] LDAP/JNDI environment properties đã kiểm chứng theo provider, có test multiple URLs/referrals.
- [ ] Max in-flight, max connections, queue capacity và per-pod/global quota đủ rõ, không chờ vô hạn.
- [ ] Retry/backoff/jitter chỉ cho operation phù hợp; có circuit breaker, bulkhead và rate limit trước auth.
- [ ] Không giữ servlet thread bằng `Thread.sleep` nhiều giây; có cancellation/finally-release.
- [ ] Health probes không spam LDAP binds hoặc làm restart storm khi IdP down.

**Vận hành, QA và phản ứng sự cố**

- [ ] Có dashboards p95/p99, pool pending, in-flight, quota rejected, timeout category, 429/5xx, circuit state.
- [ ] Không ghi password, token, LDAP env, session cookie, key, raw header vào log hoặc metrics.
- [ ] Test invalid credentials vs read timeout vs TLS error vs 429 vs 5xx vs unknown `kid`.
- [ ] Test app nhiều instance, upstream outage, recover, half-open, connection leak, retry storm.
- [ ] Test JWT verified locally hoạt động theo policy và opaque introspection fail closed.
- [ ] Có runbook chẩn đoán DNS/TLS/IdP/LDAP/pool, tránh giảm bảo mật khi khôi phục.
- [ ] Có quy trình rollout, canary, rollback và đánh giá lại ngưỡng khi thay provider/quota.

**Kết luận:** Nguồn danh tính ngoài chậm hoặc mất kết nối tạo **trạng thái không thể xác minh**, không tạo bằng chứng mật khẩu sai và tuyệt đối không tự tạo identity đúng. Bảo vệ Spring Security bằng **timeout phân tầng, giới hạn connection/in-flight, retry có ngân sách, circuit breaker, phân loại lỗi, TLS chuẩn và kiểm thử nhiều node**. Một hệ thống khả dụng không phải hệ thống luôn cho đăng nhập bằng mọi giá, mà là hệ thống từ chối an toàn, giải thích đúng loại lỗi, không làm sập các dịch vụ khác và phục hồi có kiểm soát khi upstream trở lại.

## Tài liệu chính thức

- [Oracle Java — LDAP connect/read timeouts](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html)
- [Oracle Java — JNDI LDAP connection creation và nhiều URLs](https://docs.oracle.com/javase/tutorial/jndi/ldap/create.html)
- [Oracle Java SE 17 — java.naming module](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/module-summary.html)
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT/JWK startup, cache và timeouts](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Opaque Token Introspection](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — AuthenticationServiceException Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationServiceException.html)
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
