# Rate limit overload

## 1. Rate limit overload là gì?

**Rate limit overload** là tình huống lưu lượng request vượt quá mức mà dịch vụ xác thực có thể xử lý an toàn, khiến tài nguyên bị bão hòa hoặc các request hợp lệ bị chậm và thất bại. Rate limiting giới hạn tốc độ hoặc số lượng request; overload control bảo vệ năng lực xử lý còn lại bằng backpressure, admission control và load shedding.

Trong authentication, một request đăng nhập có thể tiêu tốn nhiều tài nguyên hơn một request đọc thông thường. Server có thể phải chuẩn hóa định danh, đọc credential verifier, chạy Argon2id/bcrypt, truy vấn risk engine, tạo MFA challenge, gọi IdP hoặc ghi session. Attacker có thể tận dụng chi phí này để làm cạn CPU, memory, database connection, thread pool hoặc quota của nhà cung cấp SMS/push.

Ví dụ: một bot gửi hàng chục nghìn lần đăng nhập sai trong thời gian ngắn. Nếu mọi request đều chạy password hash với cost cao trước khi kiểm soát tải, CPU authentication service có thể bão hòa. Người dùng hợp lệ cũng không đăng nhập được, dù attacker không đoán được password nào.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, rate limit overload là kiểm soát availability của credential, MFA, token, session và account recovery. Mục tiêu là giữ đủ năng lực cho người dùng hợp lệ, hạn chế chi phí do request độc hại và tránh để cơ chế bảo vệ tự tạo ra denial of service.

## 2. Phân biệt rate limiting, overload control và account lockout

Ba cơ chế này thường bị nhầm lẫn:

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Rate limiting** | Giới hạn số request hoặc chi phí request theo một khóa và cửa sổ thời gian. | Một account hint chỉ được thử một số lần trong một khoảng thời gian. |
| **Overload control** | Giữ hệ thống trong giới hạn năng lực và ưu tiên công việc quan trọng. | Từ chối request trước khi KDF queue hoặc connection pool cạn. |
| **Account lockout** | Tạm ngăn một account đăng nhập sau một điều kiện nhất định. | Tạm khóa hoặc cooldown sau nhiều lần xác thực thất bại. |

Rate limit thường áp dụng cho nguồn, principal, tenant, endpoint hoặc toàn hệ thống. Overload control quan tâm tới tài nguyên thực tế như CPU, memory, queue depth và dependency latency. Account lockout tác động trực tiếp tới một tài khoản và có thể bị attacker lợi dụng để khóa tài khoản nạn nhân.

Không nên chỉ dùng account lockout để bảo vệ hệ thống khỏi overload. Attacker có thể cố ý gửi password sai cho tài khoản mục tiêu để gây gián đoạn dịch vụ của người dùng hợp lệ.

## 3. Vì sao authentication dễ bị overload?

Một số bước trong luồng xác thực có chi phí cao hoặc phụ thuộc dịch vụ bên ngoài:

| Thành phần | Chi phí hoặc giới hạn | Hậu quả khi quá tải |
| --- | --- | --- |
| Password hashing | CPU và memory; cost cố ý cao để chống offline guessing. | CPU bão hòa, memory pressure và request queue tăng. |
| Credential database | Connection, IOPS, lock và query capacity. | Login chậm, pool cạn hoặc database failover. |
| Risk engine | CPU, feature store và truy vấn tín hiệu. | Tăng latency hoặc bỏ lỡ đánh giá rủi ro. |
| MFA push/SMS | Quota nhà cung cấp, chi phí gửi và callback capacity. | Prompt spam, chi phí tăng hoặc OTP delivery chậm. |
| Email recovery | Provider quota, queue và deliverability. | Password reset chậm hoặc bị lạm dụng gửi hàng loạt. |
| Token endpoint | Cryptographic signing, database và grant processing. | Không cấp hoặc refresh token kịp thời. |
| Session store | Read/write throughput và replication. | Không tạo, đọc hoặc thu hồi session. |
| Introspection/policy service | Network round-trip và backend query. | API downstream bị chậm theo dependency. |
| Logging/telemetry | Event volume, serialization và ingest capacity. | Log pipeline chậm hoặc làm tăng latency đường request. |

Password hashing là ví dụ quan trọng: cost cao bảo vệ password verifier khi database bị lộ, nhưng cũng khiến mỗi lần thử online tốn tài nguyên server. Kẻ tấn công không cần password đúng để tiêu thụ CPU; họ chỉ cần gửi đủ request tới bước hashing.

## 4. Threat model và mục tiêu availability

Attacker có thể:

- Gửi nhiều request từ một IP hoặc phân tán qua nhiều IP/proxy.
- Thử nhiều username trên một nguồn hoặc một username từ nhiều nguồn.
- Tạo nhiều challenge MFA, SMS, email reset hoặc recovery request.
- Gửi request có body lớn, định danh rất dài hoặc dữ liệu gây tốn công parse.
- Tạo nhiều token refresh, introspection hoặc federation request.
- Khai thác retry tự động từ browser, SDK, gateway và service khác.
- Tạo tải đồng thời để làm cạn KDF worker, database pool hoặc queue.
- Dùng một tenant/client để ảnh hưởng tới các tenant khác.

Phòng thủ cần:

1. Giới hạn request trước khi bước xử lý tốn tài nguyên bắt đầu.
2. Bảo vệ cả quota theo caller lẫn năng lực tổng của từng dependency.
3. Duy trì fairness để một tenant hoặc nguồn không chiếm hết năng lực.
4. Giữ đường xử lý cho admin khẩn cấp và người dùng hợp lệ theo policy.
5. Trả lỗi có thể retry an toàn, không khuyến khích retry storm.
6. Không tiết lộ trạng thái account, quota nội bộ hoặc tín hiệu phát hiện bot.
7. Giữ nguyên yêu cầu authentication/MFA/authorization khi hệ thống suy giảm.

Availability không có nghĩa là mọi request phải được chấp nhận. Khi hệ thống gần quá tải, từ chối sớm một phần request có thể giữ dịch vụ hoạt động cho phần còn lại.

## 5. Đặt giới hạn ở nhiều lớp

Một lớp giới hạn đơn lẻ dễ bị né hoặc có thể chặn nhầm. Kiến trúc nên phối hợp:

| Lớp | Ví dụ khóa hoặc tín hiệu | Mục đích |
| --- | --- | --- |
| Edge/WAF | IP, network prefix, connection, endpoint, bot signal | Chặn burst và request rác trước khi vào ứng dụng. |
| API gateway | Client, tenant, route, request cost | Chia quota và bảo vệ backend. |
| Authentication service | Account hint, device/session, auth flow | Giới hạn thử credential và challenge. |
| KDF worker pool | Concurrent hash jobs, CPU/memory budget | Ngăn password hashing chiếm hết tài nguyên. |
| Dependency client | IdP, MFA, email, SMS, database pool | Bảo vệ từng dependency và quota nhà cung cấp. |
| Global service | Tổng request, concurrency và queue depth | Giữ hệ thống trong capacity đã kiểm thử. |

Edge limit giúp loại bỏ request rõ ràng bất thường, nhưng không thay thế quota theo account. Per-account limit giúp chống brute force nhưng không ngăn password spraying trên nhiều tài khoản. Global limit bảo vệ dịch vụ nhưng cần fairness để một tenant không chiếm toàn bộ quota.

## 6. Rate limit theo nhiều chiều

Đối với authentication, nên xem xét các chiều:

- **Per source:** IP, network prefix hoặc nguồn đã được edge xác minh.
- **Per account hint:** định danh đã chuẩn hóa, kể cả khi account không tồn tại.
- **Per device/session:** tín hiệu thiết bị hoặc pre-auth session đã được tạo an toàn.
- **Per tenant/client:** giới hạn tải của một tổ chức hoặc ứng dụng.
- **Per endpoint/flow:** login, token, MFA, password reset, recovery, enrollment.
- **Per challenge/factor:** số lần thử OTP, push hoặc recovery code.
- **Global:** toàn bộ auth service, KDF pool và từng dependency.

Không nên phụ thuộc vào IP duy nhất: nhiều nhân viên có thể dùng chung NAT/VPN, còn attacker có thể đổi IP. Device fingerprint cũng có thể sai hoặc bị giả mạo; chỉ dùng như một tín hiệu kết hợp.

### 6.1. Account hint và privacy

Hệ thống thường cần giới hạn theo username/email trước khi biết account có tồn tại. Có thể chuẩn hóa định danh theo quy tắc đăng nhập rồi tạo khóa đếm bằng HMAC với secret phía server.

Ví dụ khái niệm:

~~~text
normalized = normalize(accountIdentifier, tenant)
counterKey = HMAC(rateLimitKey, tenant || normalized)
~~~

Cách này tránh lưu email/username thô trong kho rate limit. Cần quản lý rotation của HMAC key và tránh thay đổi quy tắc chuẩn hóa khiến một account có nhiều counter ngoài ý muốn.

Áp dụng quota cho cả account hint không tồn tại để tránh tạo khác biệt hoặc bỏ qua chi phí cho các request enumeration. Không trả về trạng thái “account đã bị rate limit” theo cách tiết lộ account có tồn tại hay không.

## 7. Thuật toán rate limiting

Các thuật toán thường dùng:

| Thuật toán | Cách hoạt động | Điểm cần cân nhắc |
| --- | --- | --- |
| Fixed window | Đếm request trong từng cửa sổ cố định. | Đơn giản nhưng có thể tạo burst ở ranh giới hai cửa sổ. |
| Sliding window | Đếm request trong khoảng thời gian trượt. | Chính xác hơn nhưng có thể tốn state hoặc chi phí tính toán. |
| Token bucket | Token được bổ sung theo tốc độ; mỗi request tiêu thụ token. | Cho phép burst có giới hạn và kiểm soát tốc độ trung bình. |
| Leaky bucket | Xử lý request theo tốc độ ổn định. | Làm phẳng tải nhưng cần chính sách queue hoặc reject. |
| Concurrency limit | Giới hạn số request đang xử lý cùng lúc. | Bảo vệ worker, connection và dependency khỏi bị chiếm hết. |
| Cost-based quota | Request tiêu thụ số đơn vị tài nguyên theo trọng số. | Hữu ích khi endpoint có chi phí khác nhau. |

Không có thuật toán nào phù hợp với mọi endpoint. Login/password verification cần bảo vệ concurrency và KDF budget; gửi SMS cần quota theo số lần gửi và chi phí; JWKS refresh cần single-flight; introspection cần giới hạn số call đồng thời.

### 7.1. Token bucket

Token bucket có hai tham số chính:

- **Refill rate:** số token được bổ sung mỗi giây.
- **Burst capacity:** số token tối đa có thể tích lũy.

Một request chỉ được tiếp tục nếu bucket có đủ token. Khi burst kết thúc, hệ thống chỉ cho phép request theo tốc độ refill.

Token bucket phù hợp khi cần cho phép một ít burst hợp lệ, ví dụ người dùng đăng nhập đồng thời lúc bắt đầu ca làm việc. Burst capacity phải được chọn theo capacity test và quota tổng, không dựa trên cảm tính.

### 7.2. Cost-based limiting

Một request có thể tiêu thụ nhiều đơn vị tài nguyên hơn request khác. Ví dụ:

- Kiểm tra session cache hit có chi phí thấp.
- Password hash verification có chi phí CPU/memory cao.
- Tạo SMS OTP có chi phí nhà cung cấp.
- Token exchange có thể gọi authorization server và ký token.

Thay vì tính mọi request bằng một token, hệ thống có thể áp dụng trọng số theo operation. Trọng số phải được hiệu chỉnh bằng benchmark thực tế và không được để client tự khai chi phí.

## 8. Bảo vệ password hashing và KDF worker

Password hashing cần đủ chậm để chống offline cracking, nhưng không nên cho phép request vô hạn chiếm CPU/memory. Một số kiểm soát:

1. Giới hạn kích thước body và độ dài account/password trước khi xử lý sâu.
2. Chuẩn hóa và kiểm tra định dạng input với chi phí thấp.
3. Áp dụng source/account/tenant/global quota trước khi chạy KDF.
4. Dùng bounded worker pool và giới hạn concurrency của password hashing.
5. Không đưa số lượng request vô hạn vào queue chờ KDF.
6. Dùng admission control theo CPU, memory và queue depth.
7. Đo latency và cost theo thuật toán/cost parameter đang triển khai.
8. Không giảm cost password hashing tự động chỉ vì hệ thống quá tải.

Nếu KDF worker pool đầy, server nên từ chối sớm với phản hồi tạm thời phù hợp. Để request chờ quá lâu có thể giữ connection, memory và thread, khiến tình trạng quá tải nặng hơn.

Không dùng một dummy hash nhanh hơn verifier thật cho username không tồn tại. Ngoài timing side-channel, nhánh account miss cũng cần được tính vào budget và rate limit.

## 9. Bảo vệ MFA, OTP và recovery khỏi spam

Các luồng MFA/recovery có thể bị lạm dụng để tiêu thụ quota hoặc gây phiền nhiễu:

- Push fatigue: gửi liên tục prompt tới người dùng.
- SMS pumping: gửi OTP tới số điện thoại có chi phí cao hoặc vùng cước đắt.
- Email bombing: gửi nhiều password reset message.
- OTP guessing: thử nhiều mã trên một challenge.
- Recovery abuse: tạo nhiều yêu cầu hỗ trợ hoặc thử recovery code.

Kiểm soát:

- Giới hạn số challenge được tạo theo account, source, device và tenant.
- Giới hạn số lần gửi SMS/email trong cửa sổ và theo ngân sách.
- Dùng cooldown và chống gửi trùng khi người dùng bấm nhiều lần.
- Gắn OTP với challenge, purpose, principal và expiry.
- Giới hạn số lần thử mỗi challenge và tiêu thụ mã thành công một lần.
- Có cancel/deny cho push và cảnh báo khi prompt không do người dùng khởi tạo.
- Không cho fallback yếu hơn tự động mở khi factor chính lỗi.
- Theo dõi chi phí và volume theo provider, tenant và destination pattern.

Không tiết lộ tài khoản có tồn tại trong phản hồi gửi OTP. Với account không tồn tại, trả thông báo chung và không gửi message thật.

## 10. Tránh account lockout gây denial of service

Khóa cứng account sau một số lần sai có thể khiến attacker tự khóa tài khoản của nạn nhân. Để giảm rủi ro:

- Ưu tiên throttling tăng dần và cooldown có thời hạn.
- Kết hợp account limit với source/device/global signal.
- Không cho một nguồn không đáng tin khóa vĩnh viễn account.
- Cho phép người dùng hợp lệ phục hồi qua kênh đã xác minh.
- Dùng step-up hoặc CAPTCHA như tín hiệu bổ sung, không phải giải pháp duy nhất.
- Tách hạn chế tốc độ của một nguồn khỏi trạng thái account toàn cục.
- Ghi nhận false positive và có quy trình support an toàn.

Nếu policy yêu cầu tạm ngưng account khi có rủi ro cao, cần có điều kiện rõ, thời hạn, thông báo phù hợp và quy trình mở khóa đã xác minh. Không để lockout vô thời hạn chỉ vì một số lần request thất bại.

## 11. Overload control: admission, backpressure và load shedding

Rate limit theo quota không đủ nếu request hợp lệ đến đồng thời vượt capacity. Overload control cần theo dõi tài nguyên và quyết định nhận thêm công việc hay không.

- **Admission control:** chỉ nhận request khi còn đủ capacity hoặc quota.
- **Backpressure:** làm chậm producer hoặc báo consumer giảm tốc độ.
- **Load shedding:** từ chối sớm một phần request để bảo vệ hệ thống còn hoạt động.
- **Bulkhead:** tách worker/connection pool cho các dependency hoặc nhóm tác vụ.
- **Circuit breaker:** ngừng gọi dependency đang lỗi liên tục.
- **Queue bound:** giới hạn số lượng và thời gian chờ của công việc chưa xử lý.

~~~mermaid
flowchart TD
    A["Authentication request"] --> B["Edge quota"]
    B --> C["Gateway tenant/client limit"]
    C --> D["Auth service admission control"]
    D --> E{"KDF capacity available?"}
    E -->|No| F["Early reject / Retry-After"]
    E -->|Yes| G["Bounded KDF worker pool"]
    G --> H["MFA / token / session dependencies"]
    H --> I["Authentication result"]
    F --> J["Metrics and abuse telemetry"]
    I --> J
~~~

Queue không phải nơi chứa vô hạn request. Một queue lớn chỉ trì hoãn overload và làm tăng memory, latency cùng thời gian xử lý request đã hết hạn. Với login tương tác, reject sớm thường tốt hơn chờ lâu trong queue.

## 12. Distributed rate limiting

Khi auth service chạy trên nhiều instance, counter trong RAM của từng instance không thể bảo đảm quota toàn hệ thống. Attacker có thể phân phối request để mỗi node chỉ nhìn thấy một phần lưu lượng.

Các lựa chọn:

| Thiết kế | Ưu điểm | Trade-off |
| --- | --- | --- |
| Shared atomic counter | Quota nhất quán giữa instance. | Counter store có thể thành dependency nóng. |
| Gateway centralized limiter | Một nơi áp dụng policy cho nhiều service. | Cần HA và capacity cho gateway. |
| Sharded counters | Phân tán tải theo key. | Cần tính sai số và hot key. |
| Local emergency limiter | Bảo vệ từng instance khi shared store lỗi. | Không bảo đảm quota global. |
| Hierarchical quota | Kết hợp global, tenant và local budget. | Policy và accounting phức tạp hơn. |

Với shared counter, cập nhật phải nguyên tử để hai instance không cùng đọc quota còn lại rồi cùng chấp nhận vượt ngưỡng. TTL giúp dọn state cũ. Cần giới hạn cardinality để attacker không tạo hàng triệu key bằng username ngẫu nhiên.

Local limiter có thể làm lớp bảo vệ khẩn cấp khi shared store lỗi, nhưng không được báo rằng quota global vẫn được bảo đảm. Ghi rõ mode đang hoạt động và mức giới hạn gần đúng.

## 13. Khi rate limiter gặp sự cố

Rate limiter cũng là dependency và có thể timeout, mất kết nối hoặc trả kết quả cũ. Cần định nghĩa hành vi theo loại endpoint:

| Endpoint | Khi shared limiter không khả dụng |
| --- | --- |
| Login/password | Dùng local emergency budget và concurrency cap bảo thủ; nếu không bảo vệ được KDF capacity, từ chối tạm thời. |
| MFA/SMS send | Không gửi không giới hạn; dùng quota local/provider budget hoặc từ chối tạm thời. |
| Password reset/email | Giữ giới hạn local và queue budget; không mở flood gửi email. |
| Token/introspection | Dùng cache/limit đã phê duyệt; bảo vệ dependency và không bỏ qua token validation. |
| Public metadata | Có thể phục vụ cache nếu dữ liệu không nhạy cảm và còn hạn. |

Không có câu trả lời fail-open/fail-closed duy nhất cho mọi endpoint. Quyết định phải dựa trên chi phí request, rủi ro abuse và năng lực fallback. Nếu local limiter cũng không thể bảo vệ KDF hoặc provider, từ chối có kiểm soát tốt hơn xử lý vô hạn.

## 14. Fairness và ưu tiên traffic

Một tenant hoặc nhóm caller không nên chiếm hết capacity của toàn bộ authentication service. Có thể dùng:

- Quota riêng theo tenant/client.
- Global reserve cho traffic thiết yếu.
- Weighted fair queuing cho các nhóm request.
- Concurrency budget riêng cho login, token, MFA và recovery.
- Admission policy cho admin/break-glass theo quy trình khẩn cấp.
- Per-tenant dashboard và alert để phát hiện noisy neighbor.

Ưu tiên không được trở thành bypass authentication. Break-glass hoặc admin traffic vẫn cần credential, factor, approval và audit theo policy; chỉ có thể được cấp capacity reserve khi đã xác thực đúng nguồn/flow.

Không dựa vào header `X-Priority` do client gửi để ưu tiên request. Priority phải do gateway hoặc policy engine có thẩm quyền xác định từ identity và loại công việc đã xác minh.

## 15. Phản hồi HTTP và hướng dẫn retry

Status code nên phân biệt quota và overload ở mức cần thiết:

| Tình huống | Phản hồi thường dùng | Ý nghĩa |
| --- | --- | --- |
| Caller vượt quota riêng | `429 Too Many Requests` | Request bị giới hạn theo policy. |
| Service đang quá tải, không thể nhận request | `503 Service Unavailable` | Tạm thời không có capacity. |
| Dependency timeout hoặc lỗi tạm thời | Có thể `503` hoặc lỗi gateway phù hợp | Request chưa thể hoàn tất do dependency. |
| Credential sai | Phản hồi authentication failure chung | Không nhầm với quota/overload. |

`Retry-After` có thể hướng dẫn thời điểm thử lại nếu hệ thống biết thời gian hợp lý. Không tiết lộ chính xác quota bí mật, account state hoặc risk score. Với endpoint đăng nhập, response body cần tránh account enumeration.

Client nên:

- Tôn trọng `Retry-After` nếu có.
- Dùng exponential backoff và jitter.
- Không retry song song cùng một request đăng nhập.
- Không retry lỗi credential sai như thể đó là lỗi mạng.
- Giới hạn tổng thời gian và số lần retry.
- Tránh tự động tạo nhiều MFA challenge khi request trước chưa rõ kết quả.

## 16. Chống retry storm từ client và service

Khi dịch vụ trả lỗi, nhiều browser, SDK hoặc service có thể retry đồng loạt. Nếu mỗi tầng retry nhiều lần, một request ban đầu có thể tạo ra nhiều request downstream.

Biện pháp:

1. Chỉ một tầng chịu trách nhiệm retry cho mỗi dependency.
2. Dùng exponential backoff với jitter.
3. Đặt retry budget theo client/tenant và dependency.
4. Dùng idempotency key cho operation có side effect.
5. Giới hạn thời gian request tổng thể.
6. Dừng retry khi circuit breaker open hoặc quota đã vượt.
7. Không retry invalid credential, invalid signature hoặc wrong audience.
8. Với token exchange hoặc refresh timeout có kết quả không xác định, xử lý theo semantics của protocol/provider.

Không retry một request gửi SMS hoặc tạo reset token một cách mù quáng sau timeout. Provider có thể đã thực hiện side effect; cần idempotency hoặc kiểm tra trạng thái trước khi gửi lại.

## 17. Giám sát capacity và overload

Theo dõi cả traffic lẫn tài nguyên:

- Request rate, concurrent requests và rejected requests theo endpoint.
- Tỷ lệ 429, 503, timeout và latency p50/p95/p99.
- CPU, memory, GC, KDF worker utilization và queue depth.
- Password hash verification count và thời gian xử lý theo algorithm/cost.
- Database connection pool, query latency, lock wait và error rate.
- MFA/SMS/email volume, provider quota và chi phí.
- Per-tenant quota consumption và noisy-neighbor signals.
- Shared limiter latency, error rate, key cardinality và local fallback mode.
- Retry count, circuit breaker state và request shed rate.
- Login success/failure để phân biệt tấn công với traffic hợp lệ.

Alert cần kết hợp nhiều tín hiệu. CPU cao đơn lẻ có thể do peak traffic hợp lệ; tỷ lệ password failure tăng cùng với KDF saturation và nhiều account hint mới là dấu hiệu đáng điều tra.

Không ghi password, OTP, recovery code, API key, token hoặc session cookie vào metrics/log. Dùng định danh giả danh hoặc HMAC key khi cần phân tích theo principal.

## 18. Ví dụ pseudocode: admission control cho login

~~~ts
async function handleLogin(request) {
  validateBodySize(request);
  validateIdentifierAndPasswordLength(request);

  const keys = buildRateLimitKeys({
    tenantId: request.tenantId,
    accountHint: request.account,
    trustedSource: request.edgeVerifiedSource,
    deviceKey: request.preAuthDeviceKey
  });

  const decision = await limiter.consumeAtomically(keys, {
    operation: "password-login"
  });

  if (!decision.allowed) {
    return genericThrottledResponse(decision.retryAfter);
  }

  const slot = await kdfAdmission.tryAcquire();
  if (!slot) {
    return serviceOverloadedResponse();
  }

  try {
    return await verifyCredentialsAndContinue(request);
  } finally {
    slot.release();
  }
}
~~~

Đây là pseudocode minh họa. trustedSource chỉ được lấy từ proxy/edge tin cậy; không tin forwarding header do client tự gửi. Hàm limiter phải áp dụng quota theo tenant, principal hint, source và global budget. KDF admission phải có giới hạn concurrency và không xếp queue vô hạn. Response cần giữ semantics chung để không tiết lộ account tồn tại.

## 19. Ví dụ: bot làm cạn KDF capacity

Một cổng đăng nhập có bốn instance. Mỗi request password sai đều chạy Argon2id. Một bot phân tán gửi nhiều username ngẫu nhiên và khiến CPU tăng cao; người dùng hợp lệ bắt đầu gặp timeout.

**Cách xử lý:**

1. Edge áp dụng burst limit theo source/network và chặn request có kích thước bất thường.
2. Gateway áp dụng quota theo tenant/client và global request budget.
3. Authentication service chuẩn hóa account hint, dùng HMAC counter và áp dụng per-principal limit kể cả account không tồn tại.
4. KDF worker pool giới hạn concurrency theo CPU/memory capacity đã benchmark.
5. Khi KDF pool đầy, request bị từ chối sớm với phản hồi tạm thời; không đưa vô hạn request vào queue.
6. Shared limiter lỗi thì local emergency limiter hoạt động với budget bảo thủ; hệ thống cảnh báo mode suy giảm.
7. MFA và password reset có quota riêng để attacker không chuyển sang endpoint phụ.
8. Client nhận hướng dẫn retry có giới hạn, dùng backoff và jitter.
9. SOC theo dõi nguồn, tenant, account-hint cardinality và tỷ lệ login success/failure để xác định phạm vi.
10. Khi traffic giảm, hệ thống phục hồi concurrency dần và kiểm tra latency, queue depth cùng provider health.

Kết quả mong muốn là giữ được capacity cho request hợp lệ và ngăn KDF queue tăng vô hạn. Không giảm cost password hashing để giải quyết overload vì điều đó làm yếu lớp bảo vệ offline cracking.

## 20. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ rate limit theo IP | Bot phân tán nguồn để né giới hạn; NAT có thể bị chặn nhầm. | Kết hợp principal, source, tenant, device và global budget. |
| Chỉ giới hạn số request, không xét chi phí | Endpoint KDF/SMS tiêu tốn tài nguyên nhiều hơn endpoint đọc. | Cost-based quota và concurrency limit theo dependency. |
| Chạy password hash trước admission control | Request rác vẫn tiêu thụ CPU/memory. | Cheap validation và quota trước KDF. |
| Queue KDF không giới hạn | Memory/thread bị chiếm và latency tăng vô hạn. | Bounded worker pool, queue bound và early reject. |
| Giảm password hash cost khi overload | Làm yếu bảo vệ password verifier. | Điều tiết admission và capacity, giữ cost theo security policy. |
| Khóa account cứng sau vài lần sai | Attacker có thể gây DoS cho nạn nhân. | Progressive throttling, cooldown và recovery an toàn. |
| Không rate limit MFA/recovery | SMS pumping, push fatigue và email bombing. | Quota riêng theo challenge, account, destination, tenant và provider. |
| Counter chỉ nằm trong RAM mỗi instance | Tổng quota bị vượt khi request phân tán. | Shared atomic limiter hoặc hierarchical quota. |
| Limiter lỗi thì fail open toàn bộ | Attacker có thể làm cạn KDF/provider. | Local emergency budget, concurrency cap hoặc controlled reject. |
| Retry tự động ở nhiều tầng | Retry storm khuếch đại overload. | Một retry owner, budget, backoff, jitter và idempotency. |
| Dùng header priority từ client | Attacker tự nâng mức ưu tiên. | Xác định priority từ identity/policy đã xác minh. |
| Chỉ giám sát CPU | Không biết endpoint, tenant hoặc dependency nào gây tải. | Correlate traffic, queue, KDF, provider, limiter và login outcome. |

## 21. Checklist rate limit overload

Trước khi đưa authentication service vào production, hãy kiểm tra:

1. Có capacity budget riêng cho login, KDF, token, MFA, recovery, session và introspection không?
2. Request có được kiểm tra kích thước/định dạng trước bước tốn tài nguyên không?
3. Rate limit có nhiều chiều: source, account hint, device, tenant, endpoint, challenge và global không?
4. Account hint được chuẩn hóa và bảo vệ trong counter bằng HMAC/pseudonymous key không?
5. Có quota cho cả account không tồn tại để tránh enumeration và abuse không?
6. KDF worker có concurrency limit, memory budget, bounded queue và early reject không?
7. Cost-based quota có phản ánh chi phí password hashing, SMS, email và token exchange không?
8. MFA/OTP/recovery có giới hạn challenge, resend, retry và one-time use không?
9. Account lockout có tránh bị attacker lợi dụng để gây denial of service không?
10. Shared limiter có atomic update, HA, TTL và kiểm soát key cardinality không?
11. Có local emergency limiter và policy rõ khi shared limiter lỗi không?
12. Admission control, backpressure, load shedding, bulkhead và circuit breaker có được áp dụng đúng chỗ không?
13. Queue có giới hạn số lượng, thời gian chờ và xử lý message trùng không?
14. 429/503 và Retry-After có semantics rõ, không tiết lộ trạng thái account không?
15. Client/service có retry budget, exponential backoff, jitter và idempotency không?
16. Có fairness giữa tenant và capacity reserve cho công việc thiết yếu theo policy không?
17. Metrics có theo dõi KDF utilization, queue depth, provider quota, limiter health và 429/503 không?
18. Có kiểm thử bot phân tán, NAT dùng chung, hot key, shared limiter outage, KDF saturation, SMS spam và retry storm không?

**Kết luận:** Rate limit overload trong authentication cần kết hợp quota nhiều chiều với admission control và giới hạn tài nguyên thực tế. Bảo vệ KDF worker, MFA/recovery provider, token endpoint và database trước khi chúng bị bão hòa; dùng queue có giới hạn, load shedding, fairness và retry budget để giữ availability. Không dùng account lockout cứng hoặc fail-open toàn hệ thống làm giải pháp chính. Khi quá tải, từ chối sớm và có kiểm soát thường an toàn hơn nhận request vượt capacity rồi để toàn bộ luồng xác thực sụp đổ.
