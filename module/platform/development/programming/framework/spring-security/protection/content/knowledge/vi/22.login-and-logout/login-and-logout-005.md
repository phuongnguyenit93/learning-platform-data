# Ranh giới của Spring Security với kiểm soát tần suất đăng nhập

## Mục tiêu bài học

**Spring Security bảo vệ cơ chế xác thực và các ranh giới HTTP/trình duyệt**, nhưng một ứng dụng dùng Spring Security **không mặc nhiên được bảo vệ đầy đủ trước việc thử đăng nhập hàng loạt**. Khi kẻ tấn công gửi hàng nghìn yêu cầu POST /login, Spring Security có thể xác minh đúng từng mật khẩu, áp dụng CSRF và quản lý session chính xác, nhưng hệ thống vẫn có thể cạn tài nguyên tính password hash, bị password spraying, credential stuffing hoặc bị lạm dụng để khóa tài khoản người dùng thật.

Trong chương **Đăng nhập và đăng xuất** của module **SPRING_SECURITY_HTTP_PROTECTION**, bài này giải thích **ranh giới trách nhiệm** giữa **Spring Security**, hệ thống **rate limiting/anti-abuse**, reverse proxy/WAF, authentication provider và đội vận hành. Cách tiếp cận áp dụng cho **Servlet/Spring MVC** và **Reactive/Spring WebFlux**, đồng thời liên hệ với CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session.

Sau bài học, bạn có thể:

1. Nêu chính xác Spring Security **cung cấp** những gì cho login và những gì **không tự động giới hạn tần suất**.
2. Phân biệt **rate limiting**, **account lockout**, **authentication backoff**, **password spraying detection**, **credential stuffing defense**, **concurrency limiting** và **throttling ở gateway**.
3. Chọn loại tín hiệu, khóa giới hạn và thuật toán **fixed window, sliding window, token bucket** theo mục tiêu bảo vệ.
4. Thiết kế **nhiều lớp giới hạn** ở edge và ứng dụng, không tin mù quáng IP hoặc forwarded headers từ client.
5. Tích hợp bộ quyết định rate limit vào **Servlet OncePerRequestFilter** và **Reactive WebFilter** mà không bỏ qua CSRF, authentication, CORS hoặc event auditing.
6. Dùng **kho trạng thái phân tán/atomic operations** cho nhiều instance, quản lý TTL, chi phí bộ nhớ, race conditions, outages và chính sách fail-open/fail-closed.
7. Chọn phản hồi HTTP **429 Too Many Requests**, Retry-After và UX phù hợp, tránh **account enumeration** và cơ chế khóa tài khoản bị lạm dụng.
8. Kiểm thử **MockMvc, WebTestClient**, môi trường staging với store thật, quan sát Redis/gateway, DevTools và những lỗi thường gặp khi triển khai.

## 1. Bắt đầu từ một hệ thống “đã bật Spring Security” nhưng vẫn bị lạm dụng

Giả sử ứng dụng tại **https://accounts.example.com** dùng:

- Spring Security form login, PasswordEncoder mạnh.
- HttpSession cookie Secure, HttpOnly, SameSite=Lax.
- CSRF token cho POST /login và POST /logout.
- CORS chỉ cho phép frontend được duyệt.
- CSP, HSTS, X-Content-Type-Options, Referrer-Policy.
- HTTP firewall chặn những URL/method bất thường.

Nhưng mỗi lần gửi credential không đúng, backend vẫn chạy:

~~~text
POST /login
  → CSRF và các HTTP/security filters
  → AuthenticationManager
  → UserDetailsService / database
  → PasswordEncoder.matches(...)
  → AuthenticationFailureHandler
  → 401 hoặc redirect /login?error
~~~

Nếu **không có chính sách kiểm soát số lần thử**, người gửi có thể tiếp tục gây tải hoặc phân phối yêu cầu qua nhiều IP. Password hashing đủ mạnh chống brute-force trên dữ liệu hash bị lộ, nhưng chính chi phí CPU/memory của nó cũng khiến **login endpoint trở thành mục tiêu tiêu thụ tài nguyên**.

### 1.1. Hai mô hình tấn công điển hình

**Credential stuffing** là việc thử các cặp username/password đã bị lộ từ nguồn khác trên ứng dụng hiện tại. Mỗi request có thể thử một user khác nhau hoặc rất nhiều cặp; số lần sai của **mỗi tài khoản riêng lẻ** đôi khi không cao.

**Password spraying** là việc thử một hoặc một số mật khẩu phổ biến trên nhiều tài khoản. Một giới hạn “5 lỗi mỗi username” có thể không phát hiện nếu attacker chỉ thử mỗi username 1–2 lần nhưng dàn trải ra hàng nghìn account.

Ngoài ra còn có:

| Kiểu lạm dụng | Đặc điểm | Vì sao bảo vệ theo một user là chưa đủ? |
| --- | --- | --- |
| **Brute-force có mục tiêu** | Thử nhiều mật khẩu cho một identifier. | Cần giới hạn user/identifier nhưng tránh gây lockout DoS. |
| **Password spraying** | Một số mật khẩu qua nhiều username. | Mỗi user có rất ít lần sai; cần tín hiệu nguồn/tập mẫu/rủi ro. |
| **Credential stuffing** | Nhiều cặp credential lấy từ dữ liệu bị lộ. | Phân tán qua nhiều nguồn và user; cần phát hiện bất thường đa chiều. |
| **Distributed login abuse** | Nhiều IP, proxy hoặc thiết bị. | Giới hạn theo IP đơn lẻ dễ bị né. |
| **Account lockout abuse** | Gửi login sai có chủ đích để khóa người dùng khác. | Counter theo username có thể trở thành công cụ tấn công user hợp lệ. |
| **Authentication resource exhaustion** | Tăng request để làm quá tải password encoder, DB, LDAP/IdP. | Cần hạn chế lưu lượng/concurrency trước thao tác đắt. |
| **Account enumeration** | Dò user tồn tại qua status/throttle/timing. | Rate limiter cấu hình sai có thể tự tiết lộ existence. |

### 1.2. Tác hại không chỉ là đoán trúng mật khẩu

Một chiến dịch login abuse có thể:

- Dẫn tới truy cập trái phép nếu credential reuse thành công.
- Gây chậm authentication cho người dùng thật.
- Khiến database/LDAP/IdP bị quá tải hoặc vượt quota.
- Tăng chi phí CPU/RAM do password hash verification.
- Tạo hàng loạt session/challenge/log records hoặc phát sinh chi phí CAPTCHA/SMS.
- Kích hoạt khóa tài khoản hàng loạt.
- Tiết lộ account existence qua response 401/429/timing khác nhau.
- Tạo dashboard/alert noise che lấp sự cố khác.

**Phòng chống brute-force không đồng nghĩa bảo đảm account không bao giờ bị chiếm**, và một rate limiter đơn giản không thể tự phát hiện tất cả chiến thuật phân tán.

## 2. Ranh giới trách nhiệm của Spring Security

### 2.1. Spring Security làm gì tốt?

Với cấu hình thích hợp, Spring Security cung cấp hoặc tích hợp:

| Thành phần | Vai trò chính | Có tự giới hạn số lần POST /login theo IP/user không? |
| --- | --- | --- |
| **SecurityFilterChain / SecurityWebFilterChain** | Định tuyến các lớp kiểm tra HTTP. | **Không**, trừ khi bạn tích hợp filter/limiter riêng. |
| **AuthenticationManager / AuthenticationProvider** | Xác minh credential, account policy và kết quả authentication. | **Không có rate limiter tổng quát mặc định** cho các request login. |
| **PasswordEncoder** | Hash/verify password an toàn. | **Không**, dù password verification có chi phí tài nguyên. |
| **CsrfFilter / CsrfWebFilter** | Chống request unsafe bị trình duyệt thực hiện ngoài ý định. | **Không**; client hợp lệ có CSRF token vẫn thử nhiều lần được. |
| **CORS integration** | Kiểm soát cross-origin browser access. | **Không**; CORS không chặn HTTP client trực tiếp. |
| **AuthenticationFailureHandler** | Chọn redirect/status/error body khi login thất bại. | **Không**, nhưng có thể phối hợp audit/decision. |
| **Session management** | Session fixation protection, concurrency/session policies. | **Không** phải bộ đếm login attempts. |
| **SessionRegistry / maximumSessions** | Kiểm soát số phiên đồng thời theo cấu hình. | **Không** giới hạn số lần nhập sai password. |
| **Remember-me / logout** | Quản lý persistence và kết thúc trạng thái xác thực. | **Không** giải quyết credential stuffing. |
| **StrictHttpFirewall / ServerWebExchangeFirewall** | Kiểm tra request HTTP bất thường/đường dẫn nguy hiểm. | **Không** phải IP/user request-rate limiter. |
| **Security headers / CSP / HSTS** | Bảo vệ trình duyệt, kênh truyền và tài nguyên. | **Không** chặn thử credential tự động. |
| **AuthorizationFilter / authorization rules** | Kiểm tra quyền tài nguyên sau/độc lập authentication. | **Không** kiểm soát số lần gửi form login. |
| **Authentication events** | Điểm tích hợp ghi nhận thành công/thất bại. | **Không** tự duy trì rate counters hoặc quota nếu chưa cấu hình. |

**Kết luận:** Spring Security là nền tảng xây dựng **authentication/authorization và web security**, không phải một dịch vụ rate limiting phân tán được bật mặc định chỉ bằng formLogin hoặc oauth2Login.

### 2.2. Tự triển khai, tích hợp hoặc giao cho edge

Hệ thống có thể thêm một hay nhiều lớp:

~~~mermaid
flowchart LR
    B["Browser / HTTP client"] --> E["CDN / WAF / reverse proxy"]
    E --> G["API Gateway / edge rate limit"]
    G --> F["Spring HTTP filter / WebFilter"]
    F --> C["CSRF + Authentication + authorization"]
    F --> D["Atomic limit store (Redis, service)"]
    C --> U["User store / IdP / PasswordEncoder"]
    C --> A["Audit + risk detection"]
    A --> R["Alert / response policy"]
~~~

- **Edge/CDN/WAF** chặn phần lưu lượng rõ ràng bất thường sớm, giảm chi phí mạng và ứng dụng. Edge có thể thiếu thông tin account status hoặc session.
- **API gateway** áp chính sách ở những endpoint công khai, giới hạn tổng lưu lượng và đôi khi theo identity đã được xác minh.
- **Application-level filter** có thể tính đến route, login context, user identifier đã chuẩn hóa hoặc trạng thái session; cần cẩn thận để không tạo enumeration oracle.
- **Authentication events/risk engine** đánh giá kết quả thật, phát hiện chiến thuật phân tán và hỗ trợ step-up.
- **Distributed store** đồng bộ bộ đếm/quota qua nhiều instance, bảo đảm thao tác atomic và TTL.
- **Operations/security** đặt ngân sách/ràng buộc, giám sát false positive và thay đổi policy khi có chiến dịch tấn công.

Đây là **kiến trúc minh họa**; tổ chức có thể gộp tầng nhưng vẫn phải nắm rõ nơi nào chặn request, nơi nào ghi nhận sự kiện và tầng nào là nguồn xác thực.

### 2.3. Vì sao firewall và CORS không phải rate limiter?

**HTTP firewall** quyết định request có được chấp nhận theo cấu trúc/path/method phù hợp hay không; nó không đếm “username X đã thử 20 lần”. Một request POST /login hoàn toàn hợp lệ về cú pháp có thể vẫn là một phần của credential stuffing.

**CORS** quy định khả năng browser JavaScript truy cập cross-origin, đặc biệt quyền đọc response và một số bước preflight. Kẻ tấn công có thể dùng HTTP client ngoài browser, hoặc gửi HTML form cross-origin theo điều kiện phù hợp. Vì thế CORS **không thể là rào cản chống automation**.

**CSRF token** giúp chống login CSRF hoặc các request unsafe do browser tự gửi credential ngoài ý định. Một bot có thể tự tạo session, lấy CSRF token hợp lệ rồi thử nhiều cặp credential trong giới hạn hệ thống. Rate limiting **bổ sung**, không thay thế, CSRF.

### 2.4. Authentication failure events khác rate counters

Sự kiện login failed có thể ghi nhận nguyên nhân nội bộ; một listener có thể gửi event tới limiter/risk store. Nhưng chỉ lắng nghe event **sau khi password verification đã chạy** không ngăn được chi phí CPU của request hiện tại, và không giới hạn các request **trước khi** tới authentication provider.

Vì vậy thường cần:

1. **Pre-auth admission control**: kiểm tra ngân sách nguồn/endpoint trước việc xác thực tốn tài nguyên.
2. **Post-auth observation**: ghi nhận kết quả success/failure chính xác để phục vụ rủi ro và quyết định kế tiếp.
3. **Adaptive policy**: thay đổi quota, challenge hoặc yêu cầu step-up theo tín hiệu có kiểm soát.
4. **Audit và hỗ trợ phục hồi**: nhận biết người dùng thật bị false positive.

Không nên chỉ thêm một failure handler làm tăng counter rồi tuyên bố đã giải quyết distributed brute-force.

## 3. Phân biệt rate limiting, lockout, backoff và concurrency limiting

Các cơ chế có mục tiêu khác nhau và dễ tạo tác dụng phụ nếu trộn lẫn.

| Cơ chế | Đối tượng | Khi nào thường áp dụng? | Rủi ro |
| --- | --- | --- | --- |
| **Request rate limiting** | Số request theo key/time window. | Trước authentication hoặc ở gateway. | Chặn người dùng chung IP; dễ né nếu chỉ IP. |
| **Failed-attempt tracking** | Số lần xác thực sai theo identifier/source. | Sau khi provider trả kết quả. | Rò existence hoặc bị dùng để khóa user. |
| **Account lockout** | Trạng thái account bị khóa tạm/thật. | Theo policy identity lifecycle. | Attacker có thể gây DoS cho account khác. |
| **Progressive backoff** | Thời gian chờ/challenge tăng theo rủi ro. | Sau chuỗi thất bại có căn cứ. | Giảm UX, tạo timing oracle hoặc tốn thread. |
| **Concurrency limiting** | Số tác vụ auth cùng lúc. | Trước các thao tác CPU/IO đắt. | Bảo vệ tài nguyên nhưng không giới hạn tổng request theo thời gian. |
| **Adaptive risk detection** | Phân tích IP/device/user/địa lý/mẫu hành vi. | Trong pipeline hoặc ngoài băng. | Đòi dữ liệu, giám sát false positive và bảo vệ quyền riêng tư. |
| **MFA/step-up** | Thêm yếu tố/chứng minh sở hữu. | Khi login có rủi ro cao hoặc sau password factor. | Không thay kiểm soát tần suất, có thể bị lạm dụng gửi OTP. |
| **CAPTCHA/challenge** | Giảm automation ở một số request. | Theo risk/traffic policy. | Có thể bị giải thuê, giảm accessibility và tạo oracle. |

### 3.1. Account lockout có thể phản tác dụng

Chính sách “sai 5 lần thì khóa tài khoản 24 giờ” dễ hiểu nhưng attacker chỉ cần **biết username** để gây gián đoạn kéo dài cho người thật.

Hướng xử lý phù hợp hơn có thể gồm:

- Throttle ngắn hạn theo **nhiều tín hiệu**, không chỉ một account.
- Backoff/challenge có kiểm soát, không khóa vĩnh viễn vì input không xác thực.
- Bổ sung **MFA/WebAuthn** và phát hiện credential stuffing.
- Gửi cảnh báo cho kênh liên hệ đã được xác minh, có cơ chế hỗ trợ/phục hồi.
- Không công khai “account đang bị khóa” cho người chưa chứng minh quyền.
- Ghi nhận false positives và tác động đến người dùng qua chỉ số vận hành.

Không có một ngưỡng khóa account phù hợp mọi ứng dụng; cần đánh giá mô hình đe dọa, giá trị tài khoản và mức độ hỗ trợ người dùng.

### 3.2. Một limiter theo IP không đủ cho mạng NAT và botnet

Giả sử **một văn phòng hoặc mạng di động** có nhiều người dùng cùng IP public. Giới hạn 10 request/phút/IP quá thấp có thể khóa gần như cả nhóm người dùng thật. Nhưng một botnet với hàng nghìn IP có thể gửi 1–2 request/IP và tránh ngưỡng đó.

Giải pháp thường dùng **layered limits**:

~~~text
Lớp 1: Global /login concurrency và total RPS budget
Lớp 2: Edge source/IP hoặc network reputation
Lớp 3: Identifier-normalized budget (không lộ existence)
Lớp 4: Source + identifier combination
Lớp 5: Credential-stuffing / spraying risk detection
Lớp 6: User verification, MFA/challenge/recovery khi phù hợp
~~~

Các lớp cần phối hợp và có chính sách **bypass đáng tin** cho health checks/operations đã xác thực, nhưng **không** dựa trên query header do client tùy ý đặt để bỏ limit.

## 4. Chọn thuật toán giới hạn: fixed, sliding, token bucket và concurrency

### 4.1. Fixed window counter

Ví dụ: tối đa 5 POST /login cho một key trong 60 giây.

~~~text
Cửa sổ [12:00:00, 12:01:00):
  A A A A A → đủ 5
  A thứ 6   → chặn

Cửa sổ [12:01:00, 12:02:00):
  Counter bắt đầu lại
~~~

Ưu điểm: triển khai đơn giản bằng counter+TTL/slot thời gian. Nhược điểm: **window boundary burst** — requester có thể gửi sát cuối và đầu hai cửa sổ để tạo nhiều request trong thời gian ngắn.

### 4.2. Sliding window counter/log

Một rolling window xét **60 giây gần nhất** thay vì bắt đầu tại phút cố định. Có hai kiểu thường gặp:

- **Sliding log**: lưu timestamp các request, loại sự kiện quá hạn, đếm phần còn lại; chính xác hơn nhưng tốn bộ nhớ theo lưu lượng.
- **Sliding window counter**: kết hợp số đếm của những khoảng thời gian kề nhau với trọng số hoặc nhiều buckets nhỏ, ít dữ liệu hơn nhưng là phép xấp xỉ.

Ưu điểm: hạn chế burst ở ranh giới fixed window. Nhược điểm: tốn nhiều thao tác/bộ nhớ hơn và cần đồng bộ atomic.

### 4.3. Token bucket

Bucket chứa token và được nạp dần theo tốc độ định trước:

~~~text
Capacity: 10 token
Refill:   1 token / 6 giây

Request mới cần 1 token:
  còn token → cho phép, trừ 1
  hết token → từ chối hoặc chuyển sang challenge
~~~

Token bucket cho phép **burst có kiểm soát** nhưng giới hạn thông lượng trung bình. Phù hợp một số user journey có vài request liên tiếp. Khi phân tán trên nhiều instance, phép tính refill và trừ token cần **atomic**, dựa trên thời gian đáng tin hoặc chiến lược đồng bộ rõ ràng.

### 4.4. Concurrency limit

Một semaphore có thể cho tối đa N tác vụ password verification đồng thời. Nó giúp bảo vệ CPU/IdP threads ngay cả khi mỗi source giữ dưới ngưỡng request/minute.

Nhưng:

- Concurrency limit không thay request-rate limit: requester vẫn có thể gửi nhiều request tuần tự.
- Một semaphore cục bộ ở mỗi pod **không** giới hạn toàn cluster trừ khi tính ngân sách theo tổng số pod.
- Với WebFlux, tuyệt đối không dùng khóa chờ **blocking** trên event loop để thực hiện giới hạn; cần quyết định **bất đồng bộ/nonblocking** và kiểm soát backpressure.
- Đừng để waiting queue vô hạn khiến request giữ socket/connection và tăng DoS; nên có timeout, queue size và fallback rõ.

### 4.5. Bảng so sánh thuật toán

| Loại | Ưu điểm | Hạn chế | Khi cân nhắc |
| --- | --- | --- | --- |
| **Fixed window** | Dễ hiểu, số phép toán ít. | Burst ở biên cửa sổ. | Giới hạn cơ bản ở edge với sai số chấp nhận được. |
| **Sliding log** | Chính xác theo rolling window. | Chi phí lưu timestamp cao. | Lưu lượng thấp/nhạy cảm, audit chi tiết đã kiểm soát. |
| **Sliding counter** | Gần rolling window, chi phí vừa. | Có sai số do bucket. | RPS/attempt limits nhiều key. |
| **Token bucket** | Burst nhỏ, refill liên tục. | Cần atomic state/time. | API login và request patterns burst ngắn. |
| **Leaky bucket/queue** | Làm mượt tốc độ xử lý. | Độ trễ/queue có thể tăng. | Backpressure trong pipeline có ngân sách rõ. |
| **Concurrency semaphore** | Hạn chế tác vụ đắt đồng thời. | Không quản lý tổng request theo cửa sổ. | Hash verification/LDAP/IdP có giới hạn tài nguyên. |

**Thuật toán không thay chính sách**: chất lượng giới hạn còn phụ thuộc khóa định danh, vị trí kiểm tra, loại request nào bị tính, cách chia sẻ trạng thái và xử lý lỗi.

## 5. Thiết kế khóa giới hạn: ai đang dùng hết ngân sách?

Một bộ giới hạn cần trả lời bốn câu: **key đại diện cho ai/cái gì, yêu cầu nào bị tính, thời gian/thuật toán nào được dùng, và chính sách trả lời khi vượt ngưỡng là gì?**

### 5.1. Các khóa phổ biến

| Key | Ví dụ ý nghĩa | Tác dụng | Hạn chế |
| --- | --- | --- | --- |
| **IP nguồn đã xác minh** | login:source:<hmac-ip> | Hạn chế một nguồn gửi nhiều requests. | NAT/CGNAT, VPN, IPv6 privacy addresses và botnet. |
| **Định danh đăng nhập đã chuẩn hóa** | login:id:<hmac-normalized-id> | Phát hiện brute-force vào một account/name. | Có thể dùng để DoS/khóa tài khoản khác; enumeration qua quota. |
| **IP + định danh** | login:pair:<hmac-source-id> | Phân biệt một nguồn tấn công một user. | Mỗi cặp có quota riêng nên password spraying nhiều user dễ né. |
| **Network/subnet/ASN** | login:network:<derived-id> | Phân tích những nguồn cùng hạ tầng. | False positive; cần tránh phân biệt đối xử không hợp lý. |
| **Anonymous browser/session** | login:session:<opaque-id> | Giảm thử nhiều lần trong cùng browser session. | Attacker tự tạo nhiều phiên, session fixation và cookie lifecycle. |
| **Endpoint/global** | login:global | Bảo vệ ngân sách tổng CPU/IO. | Người dùng thật có thể bị ảnh hưởng trong sự cố lớn. |
| **Device/risk fingerprint** | login:risk:<opaque-key> | Bổ sung tín hiệu dựa trên hành vi thiết bị. | Bị né giả lập; liên quan quyền riêng tư và không dùng làm auth. |

Một chiến lược thực tế có thể **kiểm tra đồng thời nhiều ngân sách**; nếu một ngân sách bị vượt, phản hồi theo policy. Không có tỷ lệ giới hạn chuẩn cố định cho mọi ứng dụng.

### 5.2. Chuẩn hóa login identifier là việc nghiệp vụ, không phải phép cắt chuỗi tùy tiện

Nếu form nhận email, chuẩn hóa identifier dùng để tính limiter nên nhất quán với hệ thống đăng nhập: loại bỏ khoảng trắng biên theo policy, Unicode normalization/case-folding khi hệ thống đã quy định, không tự đổi quy tắc địa chỉ email. Ví dụ **không** được mặc định bỏ dấu chấm hoặc phần +tag của mọi email vì không phải nhà cung cấp email nào cũng coi chúng tương đương.

Nếu account identity phụ thuộc **tenant**, chính sách key cần cân nhắc tenant có được chứng minh chưa: một tham số tenant do user anonymous tự đặt **không tự có giá trị xác thực**. Tránh một key quá rộng khiến login của các tổ chức khác ảnh hưởng lẫn nhau.

### 5.3. Giảm lưu dữ liệu định danh

Không cần lưu plaintext email/password trong Redis key:

~~~text
Không nên:
  login:email:person@company.example
  login:ip:203.0.113.8
  login:password:guess123

Có thể cân nhắc:
  login:id:<HMAC(secret, normalized-identifier)>
  login:source:<HMAC(secret, trusted-ip)>
  login:pair:<HMAC(secret, trusted-ip + separator + normalized-identifier)>
~~~

**HMAC** với secret được bảo vệ phù hợp hơn một hash thường cho dữ liệu có không gian đoán nhỏ, nhưng nó **không tự miễn trừ nghĩa vụ bảo vệ dữ liệu cá nhân**. Cần quản lý key rotation, không log input/secret, không làm lộ key trên metrics và có TTL cho rate-limit state.

Không bao giờ dùng mật khẩu làm thành phần limiter key: điều này vừa rò dữ liệu credential vừa khiến attacker có thêm không gian tạo khóa vô hạn.

### 5.4. Cardinality: chi phí của một identifier do attacker kiểm soát

Một vấn đề ít được chú ý: attacker có thể gửi **hàng triệu username khác nhau**. Nếu mỗi username tạo một key mới trong Redis không có TTL, bộ đếm sẽ làm cạn bộ nhớ trước khi kẻ tấn công đoán trúng một mật khẩu.

Các cách giảm rủi ro:

- Giới hạn độ dài/định dạng identifier **trước khi tạo key**; từ chối input quá lớn sớm.
- Dùng **TTL bắt buộc** cho mọi key, capacity limit/eviction policy được vận hành có chủ đích.
- Đặt **global/source budgets** để chặn trước khi phát sinh quá nhiều identifier keys.
- Giới hạn số key unique theo nguồn/ngữ cảnh nếu hạ tầng hỗ trợ.
- Dùng metric về **distinct keys, memory footprint, evictions, latency**.
- Không lưu toàn bộ request body hoặc email không cần thiết vào Redis.
- Nếu cần thống kê theo campaign, sử dụng dữ liệu tổng hợp với retention/RBAC thích hợp.

### 5.5. Proxy và IP đáng tin

Trong production:

~~~text
Browser/HTTP client
  → CDN/WAF
  → Reverse proxy
  → Spring Boot instance
~~~

Khi đó **request.getRemoteAddr()** trên Servlet có thể chỉ trả IP reverse proxy. Nhưng **request.getHeader("X-Forwarded-For")** không được coi là IP người dùng nếu edge chưa **xóa/ghi đè header do client tự khai** và ứng dụng chưa cấu hình tin một tập proxy cụ thể.

Nguyên tắc:

1. Cấu hình **trusted proxy chain/network boundary** rõ ràng; backend không cho client trực tiếp bypass proxy nếu limiter dựa trên proxy.
2. Chỉ tin forwarded headers được edge chuẩn hóa và kiểm soát.
3. Xác minh đúng **scheme, host và client IP** theo chuỗi proxy; không chỉ lấy phần tử đầu tiên của X-Forwarded-For bằng split tùy tiện.
4. Không tạo **bypass quota** khi user gửi X-Internal-Client hoặc X-RateLimit-Exempt bất kỳ.
5. Kiểm thử với header giả, nhiều proxy, NAT, IPv4/IPv6 và IP không parse được.
6. Quy định fallback khi không có IP đáng tin, thay vì âm thầm cho **mọi** request vào một key sai hoặc cho qua toàn bộ.

Với IPv6, địa chỉ privacy có thể thay đổi; nếu gộp prefix /64 thì cũng cần hiểu tính đa dạng của mạng người dùng và nguy cơ false positive. Không có một cách gộp subnet cố định đúng cho mọi nhà cung cấp.

### 5.6. Không biến quota theo username thành account enumeration

Một anti-pattern:

~~~text
if username tồn tại:
    kiểm tra counter và có thể trả 429
else:
    trả 401 ngay

Kết quả:
  429 → attacker biết username tồn tại
  401 → attacker suy ra username không tồn tại
~~~

Chính sách limiter nên có thể áp dụng **cho identifier được nhập, dù account có tồn tại hay không**, và giữ **phản hồi công khai đồng nhất trong những tình huống cần bảo vệ account existence**. Nội bộ vẫn có thể có tín hiệu rủi ro theo account, nhưng không được phát hành thành oracle qua status, Retry-After, latency, CAPTCHA hoặc số lần còn lại.

Vì **429 khác 401 theo bản chất lỗi**, việc xuất hiện 429 phải được quyết định bởi chính sách áp dụng công bằng cho cả identifiers hợp lệ/không hợp lệ, hoặc dựa trên nguồn/global budgets, không chỉ bởi kết quả tìm user trong database.

## 6. Vị trí kiểm tra trong login pipeline

### 6.1. Pre-auth admission versus post-auth observation

Một luồng có nhiều lớp:

~~~mermaid
sequenceDiagram
    participant C as Browser / HTTP client
    participant E as Edge quota
    participant S as Spring Security
    participant D as Limiter store
    participant A as AuthenticationProvider
    participant L as Audit / risk engine

    C->>E: POST /login + credential
    E->>E: Global/source budget
    alt Edge không còn quota
        E-->>C: 429 hoặc challenge
    else Edge còn quota
        E->>S: Request đi tiếp
        S->>S: CORS/CSRF và HTTP safety theo chain
        S->>D: Admission check theo key(s)
        alt Quota ứng dụng bị vượt
            D-->>S: DENY + wait hint
            S-->>C: 429 Too Many Requests
        else Admission được phép
            D-->>S: ALLOW
            S->>A: Xác thực credential
            A-->>S: success / failure
            S->>L: Authentication result event
            S-->>C: Login response theo contract
        end
    end
~~~

Thứ tự tương đối giữa edge, CSRF, rate limit và form login **phụ thuộc security chain cụ thể**. Ví dụ khi custom filter đặt ngay trước **UsernamePasswordAuthenticationFilter** trong Servlet, **CsrfFilter** của Spring Security thường đã chạy trước đó. Như vậy request POST thiếu CSRF có thể bị từ chối trước limiter ứng dụng, nhưng edge vẫn có thể bảo vệ tổng lưu lượng.

### 6.2. Có nên tính mọi request POST /login?

Phân biệt **request attempts** với **authentication failures**:

- **Attempt budget**: kiểm tra trước password hashing, bảo vệ tài nguyên. Có thể tính mọi request đi tới bước admission, kể cả login thành công và login sai.
- **Failed-login budget**: chỉ tăng khi authentication provider đã từ chối credential, hữu ích cho tín hiệu rủi ro theo user.
- **Success handling**: có thể giảm/đặt lại một số state theo policy, nhưng nếu mọi login thành công làm xóa hết counter nguồn, attacker có một account thật để “rửa” quota.
- **Malformed/CSRF-invalid request**: có thể được edge/global anomaly policy tính nhưng không nên mặc định tính là password failure của identifier, nhất là khi chưa đến provider.
- **MFA failure**: cần quota riêng theo factor và channel, không chỉ mật khẩu.
- **OAuth2/OIDC callback failure**: cơ chế state/PKCE validation riêng; không coi mọi callback là một username/password attempt.

**Đừng tăng fail counter cho một tài khoản khi request bị chặn ở CsrfFilter** nếu điều đó giúp attacker khóa account của người khác chỉ bằng POST thiếu token.

### 6.3. Đặt filter quá sớm hoặc quá muộn

**Quá sớm**: limiter truy cập login form body trước khi request được giới hạn kích thước, cố parse identifier trên mọi request, hoặc chặn CORS preflight/GET /csrf khiến browser không thể login.

**Quá muộn**: chỉ kiểm tra quota trong failure handler sau khi BCrypt/Argon2, LDAP hoặc IdP đã làm xong công việc đắt tiền. Lúc đó quota có thể giảm số request kế tiếp nhưng **không bảo vệ chi phí request hiện tại**.

Một bố trí hợp lý với Servlet:

~~~text
Edge quota → HTTP firewall / CORS / CSRF
       → Custom admission filter (chỉ POST /login)
       → UsernamePasswordAuthenticationFilter
       → AuthenticationManager/Provider
       → Success/Failure handler + audit
~~~

Với WebFlux, **WebFilter** dùng Mono/Flux không được block event loop và không nên đọc/consume request body một cách không có quy trình cache phù hợp.

### 6.4. Chỉ matcher endpoint login thật

Không đánh đồng:

~~~text
GET /login                → HTML login page
GET /csrf                 → Cấp token cho anonymous browser
OPTIONS /login            → CORS preflight nếu cross-origin
POST /login               → Form credential authentication
POST /api/auth/token      → Có thể là API auth riêng
POST /oauth2/authorization? ...  → Tùy luồng, thường redirect qua GET
GET /login/oauth2/code/*  → OIDC/OAuth2 callback thường GET
POST /mfa/verify          → Xác minh yếu tố bổ sung
POST /password/reset      → Recovery
~~~

Các endpoint có threat model khác nhau. Filter giới hạn **POST /login** không tự bảo vệ **token issuance, password reset, OTP verification hoặc IdP callback**; mỗi mục cần quota/throttle và validation tương ứng.

Đặc biệt, **OPTIONS preflight không phải một lần thử đăng nhập**. Chặn OPTIONS như login attempt có thể làm SPA lỗi trước khi authentication diễn ra.

## 7. HTTP 429, Retry-After và hợp đồng lỗi

### 7.1. 429 không phải authentication failure

Một response minh họa khi vượt quota:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json; charset=UTF-8
Cache-Control: no-store
Retry-After: 30

{"code":"TOO_MANY_REQUESTS","message":"Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau."}
~~~

**Retry-After: 30** là một gợi ý chờ **30 giây** cho trường hợp cụ thể của ứng dụng, **không phải ngưỡng chuẩn**. Retry-After có thể là số giây hoặc HTTP-date. Thời gian chờ phải dựa trên policy limiter; không lấy giá trị do client tự khai.

Không trả những field như **userExists, accountLockedUntil, passwordAttemptsRemaining, accountRiskScore** cho request chưa xác thực chỉ vì limiter biết dữ liệu đó.

### 7.2. Phân loại 401/403/429/5xx

| Response | Ý nghĩa thường gặp | Phòng vệ |
| --- | --- | --- |
| **401 Unauthorized** | Credential không hợp lệ hoặc client chưa được xác thực theo API contract. | Thông báo công khai chung, không lộ account status. |
| **302 → /login?error** | Form HTML login thất bại theo Spring Security mặc định hoặc tùy chỉnh. | Redirect chung, không mang identifier/exception. |
| **403 Forbidden** | CSRF token invalid/missing hoặc thiếu quyền theo authorization. | Phân biệt tầng lỗi trong logs, không tắt CSRF. |
| **429 Too Many Requests** | Chính sách giới hạn request không còn quota. | Hints không tạo enumeration, hỗ trợ retry công bằng. |
| **503 Service Unavailable** | Dependency limiter/IdP/database hoặc service quá tải theo thiết kế. | Public response tổng quát, phân loại lỗi vận hành. |
| **5xx khác** | Sự cố hệ thống không mong đợi. | Không log lộ credential, không biến thành thông báo account existence. |

Chỉ trả 429 khi **đã có quyết định quota hợp lệ**. Một exceptions from Redis không nên bị chuyển tự động thành 429 nếu không có bằng chứng quota vượt, bởi điều đó vừa sai semantics vừa che sự cố.

### 7.3. RateLimit headers

API có thể cung cấp rate-limit metadata (như các trường RateLimit theo chuẩn áp dụng và phiên bản được hỗ trợ) để client kiểm soát retry. Nhưng trên **login chưa xác thực**, metadata quá chi tiết theo account có thể làm lộ tài khoản đang chịu hạn chế.

Cân nhắc chỉ công bố thông tin **thô theo nguồn/global quota** hoặc Retry-After phù hợp, tránh phản hồi số lần thử mật khẩu còn lại cho một username bất kỳ.

Các header RateLimit của các hệ thống khác nhau có thể dùng chuẩn/phiên bản và cách đặt tên khác nhau; không tự suy ra một bộ header mặc định do Spring Security luôn phát hành.

### 7.4. UX cho người dùng thật

- Thông báo rõ việc **tạm thời không thể gửi thêm yêu cầu** và có lựa chọn thử lại khi phù hợp.
- Không xóa toàn bộ dữ liệu form cần thiết khi một request bị 429, nhưng **không lưu password vào URL, analytics hoặc localStorage**.
- Không tự động gửi lại password vô hạn sau một HTTP 429.
- Nếu có Retry-After, client có thể vô hiệu hóa nút gửi trong khoảng hợp lý, vẫn cho phép truy cập trợ giúp/recovery.
- Khi chặn người dùng thật do NAT hoặc incident, có quy trình hỗ trợ/step-up thay vì chặn không có hồi đáp.
- Nếu cần giải thích account bị khóa, sử dụng kênh đã xác minh; một identifier được nhập không chứng minh quyền sở hữu.
- Đảm bảo accessibility: thông báo có vai trò phù hợp (chẳng hạn role=alert) và không đẩy người dùng vào vòng lặp CAPTCHA.

### 7.5. Cache, cookie và phản hồi 429

Các response liên quan login nên đặt **Cache-Control: no-store** phù hợp để proxy/browser không cache sai status/token theo session. Bộ giới hạn không nên tự đặt lại session cookie hoặc CSRF token chỉ vì vượt quota trừ khi có thiết kế rõ.

Một 429 có thể xuất hiện trước authentication; frontend không được suy ra tài khoản **đã tồn tại, đã sai mật khẩu, đã logout hay đã bị khóa** chỉ từ status.

## 8. Phân tán bộ đếm trên nhiều instance

### 8.1. Vì sao một ConcurrentHashMap trong mỗi pod không đủ?

Giả sử có bốn instances sau load balancer:

~~~text
Client → Load Balancer
          ├── Spring A → local counter A
          ├── Spring B → local counter B
          ├── Spring C → local counter C
          └── Spring D → local counter D
~~~

Nếu mỗi instance cho **10 attempts/phút/key**, người gửi có thể đạt tổng cộng nhiều hơn **10 attempts/phút** khi traffic phân bố qua các instance. Sticky session có thể giúp một số request đi cùng instance, nhưng **không là bảo đảm toàn cluster**; autoscaling, failover và nhiều client sessions khiến quota không nhất quán.

Một shared limiter có thể dùng Redis hoặc dịch vụ quota tập trung, với các điều kiện:

1. **Atomic read-modify-write** cho counter/bucket state.
2. **TTL/expiration** cho keys và bounded memory.
3. **Clock/time window** nhất quán hoặc chiến lược xử lý sai lệch rõ.
4. **Request/key idempotency** nếu architecture có retry/at-least-once delivery.
5. **Monitoring** về latency, unavailable, memory evictions, rejected/allowed.
6. **Fail-open/fail-closed/degraded behavior** có căn cứ threat model.
7. **Không lưu password/credential** trong limiter store.

### 8.2. Redis INCR rồi EXPIRE không phải lúc nào cũng atomic

Chống mẫu:

~~~text
GET current value
IF current < limit:
  INCR counter
  EXPIRE counter 60 seconds
ALLOW
~~~

Nếu hai requests chạy đồng thời, chúng có thể cùng thấy value thấp rồi cùng cho phép. Nếu tăng counter thành công nhưng tiến trình chết trước khi đặt TTL, key có thể tồn tại ngoài ý định.

Một **Redis Lua script** có thể thực hiện một chuỗi tăng counter + đặt TTL + so quota như **một operation atomic**:

~~~lua
-- KEYS[1]: key đã chuẩn hóa/HMAC và gồm scope chính sách.
-- ARGV[1]: TTL theo mili-giây, ví dụ 60000.
-- ARGV[2]: số lượng tối đa trong cửa sổ.
local total = redis.call("INCR", KEYS[1])

if total == 1 then
    redis.call("PEXPIRE", KEYS[1], tonumber(ARGV[1]))
end

local ttl = redis.call("PTTL", KEYS[1])
local allowed = 0

if total <= tonumber(ARGV[2]) then
    allowed = 1
end

return { allowed, ttl, total }
~~~

Đây là **minh họa một cửa sổ bắt đầu từ request đầu tiên** (first-hit window), **không phải sliding-window chính xác** hay calendar-aligned fixed window. TTL phải được quản lý theo chính sách cụ thể. Lua đảm bảo chuỗi thao tác Redis atomic với các request khác trên cùng primary, nhưng không tự giải quyết failover, replication lag, network timeout, multi-region partition hay identity spoofing.

**Rủi ro cần cân nhắc:** Lệnh INCR vẫn tăng counter cho request đã vượt quota. Một key chỉ tồn tại trong TTL và không được refresh TTL sau mọi request chặn, tránh việc spam liên tục vô tình khóa một source vĩnh viễn. Nếu muốn policy “thời gian phạt tăng theo số vi phạm”, phải thiết kế riêng và đánh giá DoS.

### 8.3. Atomic multi-key limits

Khi một POST /login phải qua quota **source**, **identifier**, **source+identifier** và **global**, vấn đề không chỉ là gọi lần lượt các limiter:

~~~text
ALLOW source -> tiêu tốn 1 token
DENY identifier -> request cuối cùng không được authentication

Kết quả: source token đã bị tiêu dù request bị chặn ở budget khác.
~~~

Điều này có thể **được chấp nhận** nếu policy có chủ đích tính mọi admission attempts ở các lớp, nhưng cần ghi rõ. Nếu yêu cầu **all-or-nothing** giữa nhiều buckets, phải xem xét atomic multi-key scripts/transactions, Redis Cluster key-slot constraints và distributed consistency.

Không coi việc gọi **hai Redis commands liên tiếp** là transaction tự nhiên. Khi storage nhiều shard hoặc nhiều region, không thể hứa strict global quota nếu không thiết kế cơ chế đồng bộ mạnh hơn và chấp nhận độ trễ.

### 8.4. Chọn Fail-open, fail-closed hay degraded mode

Giả sử limiter store tạm thời không phản hồi. Có ba phương án thường gặp:

| Chính sách | Hành vi | Rủi ro |
| --- | --- | --- |
| **Fail-open** | Cho request đi tiếp khi limiter unavailable. | Có thể tạo cơ hội lạm dụng đúng lúc dịch vụ gặp sự cố. |
| **Fail-closed** | Từ chối request khi không xác minh quota. | Có thể làm người dùng thật hoàn toàn không đăng nhập được khi Redis lỗi. |
| **Degraded mode** | Áp giới hạn cục bộ/global hoặc cơ chế emergency protection. | Cần cap, TTL, metrics và thiết kế nhất quán; quota không chính xác như shared store. |

Không có lựa chọn chung cho mọi ứng dụng. Ví dụ dịch vụ có rủi ro cao có thể chọn fail-closed trên kênh rủi ro, nhưng cần cơ chế hỗ trợ; dịch vụ availability-critical có thể chọn giới hạn cục bộ tạm thời kèm alert.

Phân biệt **limiter unavailable** với **quota DENIED** trong logs/metrics. Đừng trả cùng một lý do “user thử quá nhiều” khi Redis đang lỗi.

### 8.5. Timeout, connection pool và chi phí mới do limiter tạo ra

Một limiter cũng có thể trở thành điểm nghẽn:

- Redis network timeout giữ quá nhiều threads/coroutines.
- Mỗi request tạo nhiều keys/transactions; bot tạo cardinality rất lớn.
- Quota service bị quá tải khiến mọi login chậm.
- Retry tự động của limiter driver vô tình nhân nhiều operations.
- Metrics gắn label username/IP gây high cardinality và rò dữ liệu.
- Counter TTL quá dài giữ dữ liệu cá nhân lâu hơn cần.
- Redis eviction khiến quotas biến mất ngẫu nhiên; phải hiểu memory policy.
- Một gateway/edge limiter đã chặn nhưng application vẫn truy cập store do routing sai.

Đặt **timeout/ngân sách/connection pool/circuit breaker** phù hợp. Trên WebFlux, client của limiter phải **nonblocking end-to-end**, không gọi driver Redis blocking trong event loop.

## 9. Servlet: tích hợp pre-auth rate limiter vào Spring Security

Mục tiêu ví dụ: **chặn những POST /login vượt quota trước khi UsernamePasswordAuthenticationFilter xử lý credential**, nhưng vẫn để **CsrfFilter**, formLogin, session fixation protection và failure handling hoạt động.

### 9.1. Tách giao diện admission khỏi backend

Java 17+ minh họa một hợp đồng nhỏ:

~~~java
// AdmissionDecision.java
public record AdmissionDecision(
        boolean allowed,
        long retryAfterSeconds) {

    public static AdmissionDecision allow() {
        return new AdmissionDecision(true, 0);
    }

    public static AdmissionDecision reject(long waitSeconds) {
        return new AdmissionDecision(false, Math.max(1, waitSeconds));
    }
}

// LoginAdmissionService.java
public interface LoginAdmissionService {
    AdmissionDecision tryAcquire(String key);
}

// ClientSourceResolver.java
import jakarta.servlet.http.HttpServletRequest;

public interface ClientSourceResolver {
    String sourceKey(HttpServletRequest request);
}
~~~

Các kiểu trên **chỉ là interface/record**, chưa có Redis implementation hoặc Bean wiring. Trong production:

- **LoginAdmissionService** phải dùng shared/atomic quota store hoặc policy tương đương.
- **ClientSourceResolver** phải chọn source qua trusted proxy config và có thể HMAC/pseudonymize key.
- Không trả thông tin account existence từ một quyết định quota.
- Service có policy về **backend timeout và unavailable**, không chỉ hai trạng thái ALLOW/DENY.
- Đặt key prefix rõ môi trường/route/policy version để tránh một dịch vụ chiếm quota dịch vụ khác.

Với ứng dụng chỉ có một instance test, có thể dùng fake in-memory limiter để kiểm thử **routing/HTTP contract**, nhưng không gọi nó là giải pháp phân tán production.

### 9.2. OncePerRequestFilter chỉ giới hạn POST /login

~~~java
import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginAdmissionFilter extends OncePerRequestFilter {

    private final LoginAdmissionService admission;
    private final ClientSourceResolver sourceResolver;

    public LoginAdmissionFilter(
            LoginAdmissionService admission,
            ClientSourceResolver sourceResolver) {
        this.admission = admission;
        this.sourceResolver = sourceResolver;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        boolean loginPost =
                "POST".equalsIgnoreCase(request.getMethod())
                && "/login".equals(request.getServletPath());

        if (!loginPost) {
            chain.doFilter(request, response);
            return;
        }

        String sourceKey = sourceResolver.sourceKey(request);
        AdmissionDecision decision = admission.tryAcquire(
                "login:source:" + sourceKey);

        if (!decision.allowed()) {
            response.setStatus(429);
            response.setContentType("application/json;charset=UTF-8");
            response.setHeader("Cache-Control", "no-store");
            response.setHeader(
                    "Retry-After",
                    Long.toString(Math.max(1, decision.retryAfterSeconds())));
            response.getWriter().write(
                    "{\"code\":\"TOO_MANY_REQUESTS\","
                    + "\"message\":\"Bạn đã gửi quá nhiều yêu cầu. "
                    + "Vui lòng thử lại sau.\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

Điểm an toàn của bộ lọc minh họa:

1. Chỉ áp dụng cho **POST /login**, không tính GET /login, GET /csrf hay OPTIONS /login.
2. Không đọc **request body**, không log password, không tự phân tích username trong filter.
3. Không tự thực hiện authentication, không gọi password encoder hay tạo authenticated principal.
4. Khi vượt quota, phản hồi **429** và dừng chain; khi còn quota, chuyển request vào Spring Security.
5. Không tạo user session hay clear cookie chỉ vì 429.
6. Bỏ ngỏ backend limiter thông qua interface, tránh nhầm một ConcurrentHashMap local với distributed rate limiting.

**Giới hạn của ví dụ:** getServletPath() có thể cần điều chỉnh theo servlet mapping, application context, proxy path rewriting hoặc custom loginProcessingUrl. Đây là filter cho **một form login endpoint cụ thể**, không phải matcher tổng quát có thể copy nguyên sang mọi ứng dụng.

### 9.3. Thêm filter trước UsernamePasswordAuthenticationFilter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
        .UsernamePasswordAuthenticationFilter;

@Configuration
class ServletLoginRateLimitSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LoginAdmissionService admission,
            ClientSourceResolver sourceResolver) throws Exception {

        LoginAdmissionFilter limiter =
                new LoginAdmissionFilter(admission, sourceResolver);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/csrf", "/assets/**")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .csrf(Customizer.withDefaults())
                .addFilterBefore(
                        limiter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

**Không đồng thời đăng ký LoginAdmissionFilter thành một servlet filter toàn cục** qua @Component/FilterRegistrationBean và thêm nó qua addFilterBefore, nếu không muốn filter có thể chạy ngoài security chain hoặc chạy hai lần. Trong ví dụ, filter được **tạo riêng trong cấu hình security chain**.

Với thứ tự chuẩn của Spring Security Servlet, CsrfFilter thường ở trước UsernamePasswordAuthenticationFilter; filter được đặt ngay trước login filter sẽ kiểm tra quota **sau bước CSRF**, nhưng **trước bước xác minh credential**. Do đó:

~~~text
POST /login thiếu CSRF
  → CsrfFilter từ chối
  → Có thể không chạm admission counter trong filter này

POST /login có CSRF hợp lệ, nhưng vượt quota
  → LoginAdmissionFilter trả 429
  → Không chạy PasswordEncoder verification

POST /login có CSRF hợp lệ, còn quota
  → UsernamePasswordAuthenticationFilter xử lý credential
  → Failure/success handlers hoạt động bình thường
~~~

**Edge/global quota** vẫn nên bảo vệ tổng request kể cả request bị chặn do thiếu CSRF. Nếu ứng dụng dùng custom authentication filter hoặc nhiều SecurityFilterChain, thứ tự thực tế phải được kiểm thử; không giả định chỉ vì đã khai addFilterBefore là mọi cơ chế auth khác đều được giới hạn.

### 9.4. Nguồn IP: ví dụ chỉ cho môi trường test

~~~java
// Chỉ minh họa cục bộ; production phải dùng trusted proxy policy.
ClientSourceResolver localSource =
        request -> request.getRemoteAddr();
~~~

Khi phía trước ứng dụng có reverse proxy, remote address có thể là IP proxy và khiến nhiều người dùng chia sẻ quota. Nhưng thay bằng request.getHeader("X-Forwarded-For") một cách mù quáng còn nguy hiểm hơn vì header này có thể bị attacker làm giả.

Phương án production phải có **trusted forwarding configuration tại edge**, xác định source đáng tin, IP normalization/HMAC và fallback rõ. Không lưu raw IP vô hạn vào metrics hoặc Redis.

### 9.5. Nếu cần giới hạn theo username?

Dùng IP/source ở pre-auth filter là cách tránh đọc form body. Muốn kiểm tra theo identifier:

- Trong **Servlet**, request.getParameter("username") có thể đọc form parameter, nhưng phải xem giới hạn request body, content type, encoding và body caching của stack. Không log raw request parameters.
- Trong **WebFlux**, đọc DataBuffer/formData trực tiếp trong WebFilter có thể **consume request body** trước authentication và phá pipeline; nên dùng integration layer đã quản lý body caching hoặc quan sát credential outcome ở provider/failure event.
- Không dùng **username chưa xác thực** để kết luận account tồn tại.
- Chuẩn hóa identifier nhất quán với authentication provider.
- Áp dụng quota cho **cả identifier tồn tại lẫn không tồn tại** để hạn chế enumeration.
- Một limiter theo identifier nên là **lớp bổ sung** cạnh source/global counters, không thay thế.

Có thể xây một **custom authentication manager/provider wrapper** để ghi nhận và kiểm tra thêm policy tại điểm biết identifier, nhưng phải tránh chạy password hashing trước khi kiểm tra quota và không tự làm hỏng session strategy/các authentication events.

### 9.6. Failed-login events sau provider

Spring Security có cơ chế **authentication failure events** ở một số cấu hình; có thể dùng để ghi audit hoặc cập nhật failure counters. Cần xác minh application đang phát events và các loại exceptions được map đúng.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event
        .AuthenticationFailureBadCredentialsEvent;
import org.springframework.stereotype.Component;

@Component
class LoginFailureObserver {

    private final LoginRiskRecorder recorder;

    LoginFailureObserver(LoginRiskRecorder recorder) {
        this.recorder = recorder;
    }

    @EventListener
    void onBadCredentials(AuthenticationFailureBadCredentialsEvent event) {
        // Không log raw credentials hoặc Authentication.toString().
        recorder.recordFailure(
                event.getAuthentication().getName());
    }
}

// Interface minh họa; implementation cần chuẩn hóa, HMAC và TTL.
interface LoginRiskRecorder {
    void recordFailure(String submittedIdentifier);
}
~~~

**Cảnh báo:** Listener minh họa nhận identifier từ Authentication object là dữ liệu **chưa chứng minh quyền sở hữu**. Implementation không được ghi nguyên văn email/password hoặc dùng counter chưa xác minh để khóa vĩnh viễn một account. Nếu việc ghi Redis trong synchronous event listener chậm/lỗi, nó có thể làm chậm hoặc ảnh hưởng login; cân nhắc xử lý bất đồng bộ có giới hạn, queue semantics và monitoring.

Đừng chỉ dựa vào event này để hạn chế CPU: **PasswordEncoder có thể đã chạy xong** khi failure event được phát. Pre-auth admission vẫn cần thiết.

## 10. WebFlux: rate limiting không chặn event loop

Trong **Spring WebFlux/Reactive**, request đi qua các **WebFilter** trong SecurityWebFilterChain. Bộ kiểm tra quota cần trả **Mono<AdmissionDecision>** hoặc một Publisher bất đồng bộ tương đương, tránh driver blocking hoặc Thread.sleep.

### 10.1. Interface reactive

~~~java
import reactor.core.publisher.Mono;

public interface ReactiveLoginAdmissionService {
    Mono<AdmissionDecision> tryAcquire(String key);
}

public interface ReactiveSourceResolver {
    String sourceKey(
            org.springframework.web.server.ServerWebExchange exchange);
}
~~~

Có thể tái sử dụng **AdmissionDecision** (record) ở mục Servlet vì nó chỉ là dữ liệu; **không tái sử dụng HttpServletRequest hoặc OncePerRequestFilter** trong WebFlux.

Một backend Redis reactive, API quota riêng hoặc nonblocking cache là lựa chọn phù hợp tùy hệ thống. **Một Mono.just(blockingRedisCall()) không biến thao tác blocking thành nonblocking** — blocking call đã chạy trước khi tạo Mono.

### 10.2. WebFilter cho POST /login

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class ReactiveLoginAdmissionWebFilter implements WebFilter {

    private final ReactiveLoginAdmissionService admission;
    private final ReactiveSourceResolver sourceResolver;

    public ReactiveLoginAdmissionWebFilter(
            ReactiveLoginAdmissionService admission,
            ReactiveSourceResolver sourceResolver) {
        this.admission = admission;
        this.sourceResolver = sourceResolver;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        boolean loginPost =
                exchange.getRequest().getMethod() == HttpMethod.POST
                && "/login".equals(exchange.getRequest()
                        .getPath().pathWithinApplication().value());

        if (!loginPost) {
            return chain.filter(exchange);
        }

        String key = "login:source:"
                + sourceResolver.sourceKey(exchange);

        return admission.tryAcquire(key).flatMap(decision -> {
            if (decision.allowed()) {
                return chain.filter(exchange);
            }

            ServerHttpResponse response = exchange.getResponse();
            response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
            response.getHeaders().setContentType(
                    MediaType.APPLICATION_JSON);
            response.getHeaders().setCacheControl("no-store");
            response.getHeaders().set(
                    "Retry-After",
                    Long.toString(Math.max(
                            1, decision.retryAfterSeconds())));

            byte[] body = (
                    "{\"code\":\"TOO_MANY_REQUESTS\","
                    + "\"message\":\"Bạn đã gửi quá nhiều yêu cầu.\"}"
                    ).getBytes(StandardCharsets.UTF_8);

            return response.writeWith(Mono.just(
                    response.bufferFactory().wrap(body)));
        });
    }
}
~~~

WebFilter này **không đọc request body**, chỉ xử lý POST /login và trả Mono. Khi quota còn, nó chuyển cho **chain.filter(exchange)**; khi vượt, viết response 429 và không tiếp tục authentication. Exception từ admission service **chưa được xử lý trong đoạn code**: cần policy fail-open/closed/degraded rõ ràng ở service hoặc tầng xử lý lỗi thay vì im lặng chuyển mọi exception thành DENY.

### 10.3. Đăng ký vào đúng SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server
        .SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveLoginRateLimitSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveLoginAdmissionService admission,
            ReactiveSourceResolver sourceResolver) {

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/csrf", "/assets/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .addFilterBefore(
                        new ReactiveLoginAdmissionWebFilter(
                                admission, sourceResolver),
                        SecurityWebFiltersOrder.FORM_LOGIN)
                .build();
    }
}
~~~

Đây là ví dụ cho **Reactive formLogin**, không phải code áp dụng cho Servlet. **Đừng đồng thời đăng ký cùng bộ lọc như một WebFilter toàn cục** và thêm vào SecurityWebFilterChain nếu không muốn nó chạy trùng hoặc ngoài ranh giới mong đợi.

Với cấu hình hiện hành, phải kiểm thử thứ tự **CORS, CSRF, admission filter, form login**. Nếu ứng dụng dùng JSON login custom, SSO/OIDC login hoặc một path khác, hãy đặt bộ lọc trước **cơ chế xác thực thật** theo security order và matcher phù hợp.

### 10.4. Không tạo bộ đếm bằng blocking call trên event loop

Chống mẫu:

~~~java
// KHÔNG đưa driver Redis blocking vào WebFilter event loop.
long count = blockingRedisTemplate.opsForValue()
        .increment("login:source:...");
return Mono.just(count <= 10);
~~~

Trong WebFlux, điều này có thể làm tắc event loop và tăng latency cho các request không liên quan, đúng lúc login endpoint đang bị tấn công.

Tốt hơn là dùng **ReactiveRedisTemplate**, reactive Redis connection hoặc service nonblocking trả Mono và có timeout/risk policy. Nếu bắt buộc tích hợp thư viện blocking, chỉ chuyển lên bounded scheduler **khi đã đánh giá kỹ concurrency, queue size và overload behavior**; không tự coi subscribeOn là một giải pháp rate limiter hoàn chỉnh.

### 10.5. Đừng chặn GET /csrf hoặc OPTIONS như password attempts

Một SPA gọi API khác origin có thể cần:

~~~text
GET /csrf          → Cấp token cho browser chưa xác thực
OPTIONS /login     → Browser hỏi CORS preflight
POST /login        → Login attempt thực
~~~

Limiter của mục 10.2 chỉ tính POST /login. Nhưng GET /csrf cũng có thể bị lạm dụng tạo nhiều anonymous sessions, nên **edge/global quota riêng** có thể bảo vệ endpoint đó. Phải phân biệt **abuse của token issuance** với **failed password attempts**, không tự khóa account do GET /csrf.

### 10.6. WebFlux và trạng thái theo context

Nếu cần ghi kết quả failed-login để cập nhật risk score:

- Không lấy principal từ Reactor Context khi request chưa được xác thực rồi coi nó là account owner.
- Giữ identity từ credential **đã được chuẩn hóa và bảo vệ dữ liệu**, không truyền raw password qua event/log.
- Chọn điểm hook phù hợp trong ReactiveAuthenticationManager/failure handler và tránh duplicate event counting.
- Bảo đảm Mono error/cancel semantics không làm rơi việc giải phóng concurrency permits.
- Nếu policy có delayed backoff, không block; dùng scheduling có giới hạn và không giữ connection vô hạn.
- Phân biệt HTTP 429 do admission với login failure 401 và CSRF 403.

## 11. Tương tác với CSRF, CORS, session và security headers

Giới hạn tần suất chỉ là **một lớp phòng vệ bổ sung**. Nếu thêm limiter làm sai CSRF, cookie/session hoặc CORS, ứng dụng có thể vừa khó sử dụng vừa không ngăn được tấn công.

### 11.1. Login CSRF khác credential stuffing

**Login CSRF**: website ngoài cố ép browser nạn nhân thực hiện **POST /login vào tài khoản attacker** hoặc một trạng thái đăng nhập không chủ ý. Tính chất chính là **request không có ý định hợp lệ từ user**, không nhất thiết số request lớn.

**Credential stuffing**: nhiều lần thử cặp credential để tìm cặp hợp lệ. Nó có thể đến từ HTTP client không bị giới hạn SOP/CORS và có khả năng lấy CSRF token hợp lệ nếu endpoint /csrf công khai cho anonymous session.

Vì vậy:

~~~text
CSRF token → giảm request unsafe giả mạo từ browser
Rate limiting → kiểm soát tần suất/nguồn/rủi ro request
Authentication → xác minh credential
Authorization → kiểm tra quyền của authenticated principal
Session controls → bảo vệ và kết thúc phiên
~~~

Không dùng rate limiting thay CsrfFilter và không dùng CsrfFilter như bộ đếm brute-force.

### 11.2. Một bot có thể lấy CSRF token rồi login hợp lệ về mặt request

Giả sử backend cho anonymous:

~~~text
GET /csrf     → token + anonymous session cookie
POST /login   → mang session cookie + token + credential
~~~

Đây là một hợp đồng cần thiết cho form/SPA dùng session cookie. Một HTTP client có thể làm đúng các bước này và thử credential, nên **CSRF không tự chứng minh request do con người thực hiện**.

Thay vì chặn hoàn toàn GET /csrf, hãy áp **ngân sách riêng cho anonymous session issuance** ở edge khi phù hợp, giới hạn số session creation toàn cục và theo nguồn. Không khiến người dùng thật không lấy được token trước login; một quota /csrf quá chặt có thể phá form login hoàn toàn.

### 11.3. OPTIONS preflight không phải login attempt

Một SPA ở **https://app.example.com** có thể gọi API ở **https://api.example.com**:

~~~http
OPTIONS /login HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Preflight thường **không mang session cookie** và không chứa password. Nếu limiter đếm OPTIONS như một lần login failure hoặc chặn OPTIONS vì thiếu authentication, browser có thể không gửi POST thực.

CORS cần được xử lý trước những filters/gateway rules phụ thuộc cookie. Limiter login chỉ đánh giá **POST thực**; edge có thể bảo vệ OPTIONS flood bằng một budget riêng mà không làm nhiễu failed-login counters.

### 11.4. 429 từ gateway cũng phải có CORS đúng khi frontend cần đọc

Giả sử Spring backend xử lý CORS chính xác, nhưng CDN/WAF trả **429 trước khi request tới Spring**, không kèm:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

Browser có thể từ chối cho JavaScript đọc response 429. Frontend thấy **CORS error hoặc network error** thay vì mã TOO_MANY_REQUESTS, dẫn đến retry không cần thiết.

Nếu API thật sự hỗ trợ **credentialed cross-origin SPA**, edge trả lỗi cũng cần policy CORS phù hợp **cho origin được phép**, không phản chiếu Origin vô điều kiện và không dùng wildcard Allow-Origin cùng credentials.

### 11.5. CORS Servlet chỉ mở đúng frontend

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletLoginCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/csrf", config);
        source.registerCorsConfiguration("/login", config);
        return source;
    }
}
~~~

Với HttpSecurity, tích hợp source vào chain bằng **cors(Customizer.withDefaults())**, hoặc cách đăng ký phù hợp kiến trúc. Ví dụ không thay filter rate limiter, không mở CORS cho mọi endpoint và không cấp credentials cho wildcard origin.

### 11.6. CORS Reactive dùng source của WebFlux

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive
        .UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveLoginCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/csrf", config);
        source.registerCorsConfiguration("/login", config);
        return source;
    }
}
~~~

Trong SecurityWebFilterChain:

~~~java
// Bổ sung cho ServerHttpSecurity của ứng dụng Reactive:
http.cors(cors -> cors.configurationSource(corsConfigurationSource()));
~~~

**Không trộn lớp CORS của Servlet với gói reactive**. Nếu CORS đã được quản lý ở gateway hoặc Spring WebFlux, kiểm tra response thực từ các tầng để tránh header trùng và các chính sách mâu thuẫn.

### 11.7. SameSite, Secure, HttpOnly và session fixation

Một cookie session mẫu:

~~~http
Set-Cookie: __Host-APPSESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính giúp bảo vệ phiên, nhưng:

- **Secure** và **HSTS** bảo vệ kênh HTTPS theo điều kiện browser, không giảm số POST /login do HTTP client gửi.
- **HttpOnly** ngăn JavaScript thông thường đọc cookie session, không chặn browser tự gửi cookie đủ điều kiện.
- **SameSite** giúp giảm một số request cross-site dùng cookie, nhưng không thay CSRF token và không phân biệt người dùng thật với automation.
- **Session fixation protection** đổi/kiểm soát session ID khi authentication thành công, không giới hạn password attempts.
- **Maximum concurrent sessions** kiểm soát số session authenticated cùng lúc theo policy, không chặn việc kẻ tấn công gửi hàng nghìn password sai.

Một limiter không được dựa vào **sự tồn tại của session cookie** để kết luận request đã xác thực: anonymous session có thể được tạo chỉ để cấp CSRF token.

### 11.8. CSP, clickjacking và XSS không giải quyết password spraying

CSP trên **HTML login document** có thể dùng chính sách phù hợp:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; form-action 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
~~~

Đây là policy minh họa, cần tinh chỉnh khi login form/SSO redirect hoặc assets hợp lệ liên quan origin khác. **frame-ancestors** hạn chế clickjacking, **form-action** giới hạn nơi form trên chính document được gửi đến; chúng không ngăn HTTP client thử credential hàng loạt.

**CSP không thay CSRF token, cũng không phải rate limiter.** Nếu có XSS cùng origin, script có thể gửi request với ngữ cảnh người dùng; cần xử lý input/output, script trust và authorization riêng.

### 11.9. HTTP firewall/URL normalization

Spring Security **StrictHttpFirewall** và cơ chế firewall reactive tương ứng nhằm từ chối request path/method bất thường. Một attacker có thể cố **lách endpoint matcher** qua path encoding hoặc proxy rewriting:

~~~text
POST /login
POST //login
POST /login/
POST /app/login
POST /login%2F...
~~~

Không phải mọi URL trên đều được Spring cho phép; ví dụ chỉ minh họa khả năng **khác biệt normalization giữa gateway, servlet container, firewall và limiter**. Nếu limiter chỉ match một dạng nhưng authentication filter chấp nhận một dạng khác, request có thể tránh quota.

Thiết kế cần:

- Dùng **cùng canonical endpoint/method** giữa edge và app.
- Kiểm tra path rewriting/context path, trailing slash, query string, case sensitivity, encoded separators.
- Giữ HTTP firewall phù hợp; không nới đường dẫn nguy hiểm chỉ để matcher “chạy được”.
- Test **đường dẫn bị từ chối** không được lén chạy authentication.
- Không dựa vào query parameter redirectUri, tenant hoặc scope chưa xác minh để miễn rate limiting.

## 12. Kiểm thử Servlet: quota và security chain không phá nhau

**MockMvc** phù hợp kiểm tra filter routing/status và các tương tác Servlet security. Nhưng muốn kiểm tra **thực sự phân tán/atomic**, cần integration test kho quota và môi trường nhiều instance.

### 12.1. Ma trận hành vi cần có

| Kịch bản | Mong đợi |
| --- | --- |
| GET /login | Hiển thị login page, không tiêu POST-login attempt quota. |
| GET /csrf | Cho anonymous lấy token theo policy; không được tính là failed password. |
| OPTIONS /login hợp lệ | Không tiêu login attempts; CORS preflight được xử lý. |
| POST /login không có CSRF | Bị CsrfFilter từ chối nếu chain áp dụng; không tạo authenticated principal. |
| POST /login có CSRF + quota còn | Request tiếp tục tới authentication filter. |
| POST /login có CSRF + quota hết | Trả **429**; authentication provider/password hash không được gọi. |
| Identifier có thật và không có | Quota/public response không vô tình lộ sự tồn tại của account. |
| POST /logout | Không bị bộ lọc chỉ dành cho POST /login tính nhầm. |
| Một IP dùng nhiều user | Source budget hạn chế quá nhiều attempts dù identifier khác nhau. |
| Một identifier từ nhiều IP | Identifier budget/risk engine phát hiện pattern khi policy yêu cầu. |
| Nhiều instance đồng thời | Quota shared/atomic được thực thi nhất quán trong mức bảo đảm đã định. |
| Redis timeout | Fail-open/closed/degraded đúng policy; log phân biệt lỗi store với quota exceeded. |
| Browser SPA bị 429 ở gateway | Actual response có CORS hợp lệ nếu frontend cần đọc status. |
| GET /login sau 429 | Vẫn có lối retry/help/recovery theo UX, không tự khóa user thật vĩnh viễn. |

### 12.2. Test 429 với fake limiter

Một cấu hình test đơn giản cho **các lớp Java ở mục 9**:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
class DenyAllLoginAdmissionTestConfig {

    @Bean
    @Primary
    LoginAdmissionService denyAllLoginAttempts() {
        return key -> AdmissionDecision.reject(30);
    }
}
~~~

Chỉ trong **test configuration**, bean này trả DENY cho mọi POST /login. Nó **không phải limiter production** và không nên được đưa vào application runtime thông thường.

Một lớp MockMvc dùng filter chain ở mục 9:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(DenyAllLoginAdmissionTestConfig.class)
class ServletLoginAdmissionMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void validCsrfButQuotaExceededReturns429() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "test-user")
                .param("password", "test-secret"))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().string("Retry-After", "30"));
    }

    @Test
    void missingCsrfIsRejectedBeforeAdmission() throws Exception {
        mvc.perform(post("/login")
                .param("username", "test-user")
                .param("password", "test-secret"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginPageIsNotSubjectToPostLimiter() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }
}
~~~

**Giả định quan trọng**:

- Test application dùng form login generated page hoặc **GET /login** hợp lệ trả 200; nếu có custom login page/redirect, sửa assertion GET.
- Có bean ClientSourceResolver được cấu hình trong test; nếu chưa có, cần thêm test implementation.
- Chain thực đặt CsrfFilter trước custom limiter như mục 9 và **không có filter/gateway khác chặn trước**.
- @Primary bean chỉ thay LoginAdmissionService nếu bean thật được quản lý theo cách tương thích.
- Test chỉ chứng minh **đường gọi limiter và HTTP status**, chưa chứng minh provider không bị gọi. Dùng spy/metrics integration test để xác nhận request bị chặn **trước password verification**.
- Trong test, **with(csrf())** là helper do spring-security-test cấp, không đại diện đầy đủ cho browser/session cookie lifecycle.

### 12.3. Test cho allow và deny trong cùng chuỗi

Ngoài DENY-only test, cần một fake limiter có counter deterministic:

~~~text
Quota cho một test key: 2 attempts
Request 1 + CSRF hợp lệ → được phép vào authentication
Request 2 + CSRF hợp lệ → được phép vào authentication
Request 3 + CSRF hợp lệ → 429
Request 4 sau khi test clock vượt cửa sổ → được phép
~~~

Dùng **test clock có thể điều khiển**, không Thread.sleep để chờ TTL. Tách assertions:

1. Bộ đếm thật không tăng với GET/OPTIONS.
2. Counter đã được tiêu bởi POST attempt hợp lệ theo policy.
3. Request bị DENY không gọi AuthenticationManager/PasswordEncoder.
4. Success/failure handler vẫn hoạt động khi ALLOW.
5. 429 body/header không chứa username, exception hoặc account status.
6. 403 CSRF không bị chuyển thành 429 trong vị trí filter đã chọn.

### 12.4. Test phê duyệt quota trên nhiều keys

Nếu hệ thống kiểm tra cả IP/source và identifier:

~~~text
Nguồn A thử account test-1, test-2, test-3:
  → Source budget phải có hiệu lực.

Account test-1 bị thử từ nguồn A, B, C:
  → Identifier/risk policy phải thấy tổng pattern (theo thiết kế).

Identifier không có thật bị thử tương tự account có thật:
  → Không trả public code/throttle khác nhau chỉ vì existence.
~~~

Thực hiện với dữ liệu test **không phải tài khoản thật**. Tránh test gây lockout ở môi trường production hoặc gửi số lượng request có thể gây DoS.

## 13. Kiểm thử WebFlux và kiểm thử distributed store

### 13.1. WebTestClient cho 429 và CSRF

Với Spring Security Test WebFlux:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

// Đoạn minh họa trong test đã bind WebTestClient vào ứng dụng.
// ReactiveLoginAdmissionService test luôn trả reject(30).

webTestClient
    .mutateWith(csrf())
    .post().uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(
            "username", "test-user")
            .with("password", "test-secret"))
    .exchange()
    .expectStatus().isEqualTo(HttpStatus.TOO_MANY_REQUESTS)
    .expectHeader().valueEquals("Retry-After", "30");

webTestClient
    .post().uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(
            "username", "test-user")
            .with("password", "test-secret"))
    .exchange()
    .expectStatus().isForbidden();
~~~

**Điều kiện:** Bộ limiter test được inject bằng fake reactive service; CsrfWebFilter chạy trước admission filter và security chain áp dụng POST /login như mong đợi. Nếu ứng dụng dùng custom order/filters khác, status có thể khác và cần test theo cấu hình thực.

WebTestClient mock csrf() **không tự chứng minh** Redis atomic quota, cookie policy hoặc CORS browser. Cần kiểm thử riêng trong staging.

### 13.2. Reactive test phải chứng minh không block event loop

Ngoài kiểm tra status, dùng test/metrics để đánh giá:

- Rate limiter dùng **nonblocking Redis client** và không gọi driver blocking trên event loop.
- Redis slow/unavailable không gây treo các request không liên quan.
- Cancellation/error path vẫn giải phóng permits/connection nếu dùng concurrency limit.
- Không gọi blocking sleeps trong reactive chain.
- Không tích lũy hàng nghìn pending Monos vô hạn dưới overload.
- Timeouts và degraded decisions được báo cáo đúng trong logs/metrics.
- Test 429 response vẫn được viết hoàn tất khi publisher phát DENY.

Một fake Mono.just(reject) chỉ xác minh **flow control**, không đo tính nonblocking của driver production.

### 13.3. Redis integration test

Khi có kho quota Redis thực hoặc môi trường container test được phép, kiểm thử:

1. Tạo key test có prefix riêng, TTL ngắn, không ghi PII.
2. Gửi số attempt **được giới hạn** vào cùng key song song qua nhiều workers.
3. Xác minh số ALLOW không vượt quota trong mức bảo đảm atomic đã định.
4. Xác minh TTL được đặt ngay lần đầu, không có key tồn tại vô hạn.
5. Chờ qua thời điểm hết hạn bằng **fake clock khi thuật toán hỗ trợ**, hoặc test TTL có khoảng chờ nhỏ được kiểm soát trong integration test.
6. Kiểm tra key cardinality và memory khi identifier khác nhau; không tạo dữ liệu vô hạn.
7. Thử Redis unavailable/timeout và quan sát fail-open/closed/degraded behavior.
8. Thử nhiều Spring instances sau load balancer để phát hiện quota bị nhân theo pod.
9. Nếu có failover/replication, ghi rõ tính nhất quán được bảo đảm, không mặc định strict global quota.
10. Xác minh số liệu reject/allow/error và latency được export không mang username/IP raw làm metric labels.

Với script Lua ở mục 8, phép kiểm tra atomic áp dụng **trên cùng Redis primary và key policy nhất quán**. Test trên một instance không chứng minh behavior cross-region.

### 13.4. Test browser thật với DevTools

Trong **Network** và **Application/Storage**:

1. Mở login page, xác minh form có CSRF token hợp lệ.
2. Thử login test bằng credential sai trong giới hạn cho phép; quan sát **401 hoặc 302** theo contract.
3. Khi test limiter có chủ ý đưa quota về trạng thái exhausted, quan sát **429** và Retry-After, không có authenticated session mới.
4. Kiểm tra 429 có CORS actual response phù hợp nếu SPA khác origin.
5. Xem có OPTIONS preflight trước POST hay không; OPTIONS không được tính là password attempt.
6. Kiểm tra cookie session/CSRF đúng Secure, HttpOnly, SameSite, Path, Domain.
7. Nếu login thành công sau khi quota hồi phục, xác minh principal qua endpoint bảo vệ như **GET /api/me**.
8. Sau login, nếu POST nghiệp vụ nhận 403, phân biệt **CSRF token cũ** với quota; refresh token hợp lệ theo flow.
9. Với nhiều tab, xác minh giới hạn nguồn/global hoạt động nhất quán và trạng thái UI không vượt qua quyền server.
10. Không chụp/lưu screenshot có password, session ID hoặc token nhạy cảm trong báo cáo.

### 13.5. curl preflight là công cụ xem HTTP, không thay browser

Ví dụ kiểm tra OPTIONS trên môi trường test:

~~~bash
curl -i -X OPTIONS "https://api.example.com/login" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Dùng thêm origin không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/login" \
  -H "Origin: https://outside.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

**curl không áp dụng SOP, SameSite, CORS hay CSP như browser.** Header Origin có thể được HTTP client tự đặt. Đừng suy từ curl có thể gửi POST thành công rằng JavaScript ở mọi origin đọc được response hoặc rằng CSRF đã bị vô hiệu hóa.

Muốn test password login trên backend có CSRF, phải dùng **token/cookie jar hợp lệ từ GET /csrf**, không chỉ POST credential và thấy 403. Mọi thử nghiệm tải/quota chỉ nên thực hiện trong môi trường được phép, với mức lưu lượng nhỏ và stop condition rõ ràng.

## 14. Vận hành limiter: đo đúng, thay đổi an toàn và phản ứng khi bị tấn công

Rate limiting không phải một lần viết code là xong. Chính sách phải sống cùng lưu lượng thật, cơ chế triển khai, tài nguyên auth và trải nghiệm người dùng.

### 14.1. Đặt ngân sách theo dữ liệu

Không sao chép một ngưỡng bất kỳ như “5 request/phút” thành tiêu chuẩn chung. Hãy thu thập trong môi trường được phép:

- Phân phối số POST /login theo IP nguồn đã chuẩn hóa, giờ, phiên, khu vực/ngữ cảnh.
- Lưu lượng trong giờ cao điểm và dịp ra mắt/sự kiện.
- Số users chung IP ở văn phòng, trường học, ISP hoặc CGNAT.
- Latency của password encoder, IdP/LDAP, DB/session/Redis theo p50/p95/p99.
- Tổng concurrency có thể chịu được trước khi service chậm.
- Tỷ lệ **login thất bại bình thường** do người dùng gõ sai.
- Tần suất password reset/MFA challenge, tác động của CAPTCHA và khả năng phục hồi.
- Tỷ lệ rejected traffic thực sự bất thường so với **false positives**.

Sau đó chọn ngân sách theo **bottleneck và acceptance criteria**. Một tầng global có thể dùng ngưỡng khác tầng source hoặc identifier; ngưỡng giới hạn API login cũng có thể khác password reset/OTP.

### 14.2. Metrics hữu ích nhưng không làm lộ dữ liệu

Gợi ý nhóm metrics:

| Metric | Mục đích | Tránh |
| --- | --- | --- |
| **login_admission_allowed_total** | Số request qua admission control. | Gắn raw username làm label. |
| **login_admission_rejected_total** | Theo dõi 429 và policy quá chặt. | Gắn IP hoặc email không giới hạn cardinality. |
| **limiter_store_errors_total** | Phân biệt kho quota lỗi với quota exceeded. | Gộp thành số “bad credentials”. |
| **limiter_decision_latency** | Phát hiện Redis/quota service chậm. | Bỏ qua tail latency p99. |
| **authentication_failed_total** | Theo dõi credential verification failures. | Lưu password hoặc principal PII trong label. |
| **authentication_success_total** | So sánh traffic và success rate. | Dùng nó làm chứng minh rate limiter an toàn. |
| **login_csrf_rejections_total** | Phân biệt bot spam POST thiếu token. | Gộp vào account lock counter. |
| **login_cors_preflight_rejections_total** | Phân biệt browser config lỗi. | Gộp vào password spraying detection. |
| **active_auth_verifications** | Theo dõi concurrency chi phí hash/IdP. | Chỉ nhìn RPS mà bỏ CPU/IO. |
| **login_rate_limit_override_total** | Audit policy exceptions. | Bypass bằng query/header do client tự đặt. |

Có thể dùng **low-cardinality labels** như policy, endpoint, outcome, instance/region đã được duyệt. Nếu cần điều tra nguồn cụ thể, dùng audit store có RBAC/retention thay vì tạo hàng triệu metric time series với IP/email.

### 14.3. Audit success/failure không lưu credential

Một sự kiện audit mẫu:

~~~json
{
  "event": "LOGIN_ADMISSION_REJECTED",
  "requestId": "test-correlation-id-42",
  "policy": "LOGIN_SOURCE_BUCKET",
  "outcome": "DENIED",
  "retryHintSeconds": 30,
  "timestamp": "2026-11-26T12:00:00Z"
}
~~~

Đây chỉ là ví dụ dữ liệu giả. Không ghi:

- Raw password, OTP, recovery code.
- Authorization/Cookie/Set-Cookie headers đầy đủ.
- Session ID, CSRF token hoặc refresh token.
- Toàn bộ form request body.
- Raw email/username/IP nếu không có mục đích/kiểm soát riêng tư cụ thể.
- Redis secrets, HMAC keys, password hashes.

Một **requestId** giúp liên kết logs của gateway–Spring–Redis nhưng không nên encode IP, username hoặc thông tin account existence.

### 14.4. Giảm false positives và lockout DoS

Khi có nhiều người dùng chung IP, một source budget quá chặt có thể gây gián đoạn tập thể. Khi attacker chọn username của nạn nhân, account-based threshold quá thấp có thể biến thành **cơ chế khóa user hợp lệ**.

Các hướng cân bằng:

1. Dùng **nhiều tín hiệu** thay vì chỉ IP hoặc username.
2. Cho phép burst nhỏ hợp lệ, kiểm soát trung bình theo thời gian.
3. Dùng challenge/step-up có xác minh khi rủi ro cao, nhưng đừng tiết lộ trạng thái account trước auth.
4. Có đường recovery/helpdesk được bảo vệ khỏi spam.
5. Theo dõi tỷ lệ successful login bị chặn và báo cáo từ người dùng thật.
6. Không cập nhật account failed-attempt counter chỉ vì một request bị CsrfFilter từ chối.
7. Với account-based lockout, phân biệt **temporary throttle** và **administrative lock** có quy trình xác minh.
8. Tránh một request thành công bằng tài khoản attacker khiến mọi source/global quota được xóa.
9. Tránh tạo bypass theo tên user “admin” hoặc header “internal” không được xác thực.
10. Có cơ chế rollback policy khi false positives tăng đột biến.

### 14.5. Canary rollout và thay đổi policy

Một lộ trình triển khai:

~~~text
Giai đoạn 1: Shadow mode
  → Tính quota, đo quyết định giả định, chưa chặn
  → Phát hiện false positives, cardinality, tải Redis

Giai đoạn 2: Giới hạn nguồn rõ ràng
  → Bật quota ở edge hoặc Spring với ngưỡng bảo thủ
  → Theo dõi 429, success rate và incident

Giai đoạn 3: Lớp identifier/risk
  → Thêm chính sách phân tán có audit
  → Thử account enumeration và lockout abuse

Giai đoạn 4: Tối ưu đa vùng, autoscale, IdP outage
  → Kiểm tra consistency, degraded mode và runbook
~~~

**Shadow mode** không có nghĩa phải lưu mọi identifier dưới dạng plaintext. Thử nghiệm vẫn cần privacy controls và key cardinality/TTL. Chính sách có thể được version hóa để rollout/rollback; đừng thay thuật toán/quota mà không biết phải xử lý các keys cũ ra sao.

### 14.6. Một runbook cho Redis limiter gặp sự cố

Ví dụ team nhận cảnh báo **limiter store unavailable**:

1. Xác minh lỗi nằm ở Redis/quota service hay network, DNS, TLS, pool.
2. Kiểm tra metrics latency/timeouts, error counts và request queue.
3. Xác định policy đã chọn là fail-open, fail-closed hay degraded.
4. Nếu degraded, kiểm tra local limits có bounded memory và timeout không.
5. Đảm bảo fallback không tắt authentication, CSRF, authorization hay session protection.
6. Giới hạn mức thử nghiệm/lưu lượng theo hướng dẫn vận hành; không vô tình tạo một load test production.
7. Kiểm tra người dùng thật có bị 429/503 trên diện rộng không, có đường trợ giúp không.
8. Theo dõi credential stuffing signals từ WAF/edge nếu limiter app không khả dụng.
9. Khi store phục hồi, kiểm tra TTL/key initialization không gây một **thời gian khóa bất thường**.
10. Rà soát logs để tránh lộ credentials trong lúc debug.

### 14.7. Kiểm soát tương tác với password hashing

Một hệ thống muốn chống brute-force có thể tăng cost factor PasswordEncoder. Điều này làm đoán offline khó hơn, nhưng **tăng chi phí mỗi lần login thật** và làm login abuse dễ gây nghẽn CPU hơn.

Cần có ngân sách cho:

- Số xác minh đồng thời tối đa.
- Thời gian hash và memory mỗi verification.
- Kết nối database và IdP.
- Batching/queue, nhưng không giữ hàng đợi vô hạn.
- Autoscaling và limit khi pod mới chưa sẵn sàng.
- Phát hiện dấu hiệu quá tải để trả lỗi dịch vụ đúng, không báo user “sai mật khẩu” khi chưa xác minh.

**Đừng giảm cost password hashing dưới mức an toàn chỉ để chịu nổi tấn công**. Hãy bổ sung admission/concurrency controls, capacity planning và risk response phù hợp.

## 15. Bảng chẩn đoán: nguyên nhân thực sự ở tầng nào?

| Triệu chứng | Khả năng cần kiểm tra | Hành động phù hợp |
| --- | --- | --- |
| **Spring form login hoạt động nhưng brute-force tiếp tục không giới hạn.** | Chưa có rate limit/anti-abuse layer. | Thêm edge/app limiter, shared store và audit; Spring Security không mặc nhiên giới hạn attempts. |
| **GET /login trả 429 sau vài lần mở trang.** | Filter match mọi method hoặc edge quota quá rộng. | Chỉ tính đúng loại request, tách page/token budgets. |
| **OPTIONS /login trả 429 hoặc 401.** | Preflight bị limit/auth như login attempt. | CORS xử lý OPTIONS; quota riêng khi có preflight abuse. |
| **POST /login thiếu token trả 403 thay vì 429.** | CsrfFilter chạy trước limiter app. | Đây có thể là thứ tự đúng; test admission trên request có token hợp lệ. |
| **POST có CSRF hợp lệ nhưng luôn 429.** | Key quá rộng, quota quá thấp, TTL không xóa, fake limiter còn trong prod. | Kiểm tra key/TTL/policy version/bean wiring. |
| **POST sai mật khẩu vẫn trả 200 HTML.** | Redirect đến login page rồi fetch coi response cuối 200 là success. | Thống nhất JSON/status API hoặc xử lý redirects đúng. |
| **POST 429 nhưng browser báo CORS error.** | Gateway trả 429 thiếu CORS actual response. | Đặt allowlist CORS nhất quán tại edge/app cho allowed origin. |
| **Mọi user chung một công ty bị chặn.** | Nhiều người dùng chia sẻ public IP. | Điều chỉnh source budget, multi-signal policy, hỗ trợ false positives. |
| **Botnet vẫn thử nhiều user dù quota theo IP.** | Phân tán IP, mỗi IP dưới ngưỡng. | Thêm identifier/risk/global constraints và hành vi password spraying. |
| **Account bị khóa chỉ với vài POST sai CSRF.** | Đếm request bị CSRF reject là password failures. | Tách các lớp counters, không khóa user vì request chưa vào provider. |
| **429 chỉ có với username tồn tại.** | Kiểm tra account existence trước limiter hoặc account lockout oracle. | Áp policy cho identifiers bất kể tồn tại, rà timing/status/headers. |
| **Một request login được tính hai lần.** | Filter vừa là @Component global vừa addFilterBefore; hoặc gateway app cùng dùng một key. | Kiểm tra filter registration/order và scope mỗi layer. |
| **Quota nhân theo số pod.** | In-memory limiter ở từng instance. | Shared/atomic distributed store hoặc xác định global quota tại edge. |
| **Counters không bao giờ hết hạn.** | TTL không được set atomic hoặc wrong prefix/rotation. | Test script atomic+TTL, cleanup monitoring và memory bounds. |
| **Redis lỗi, user nhận 429 như thể đã thử quá nhiều.** | Limiter errors bị map sai thành DENY. | Tách store errors, chọn fail-open/closed/degraded và trả lỗi phù hợp. |
| **Reactive login latency tăng mạnh khi Redis chậm.** | Blocking Redis call trên Netty event loop. | Reactive driver, timeout, nonblocking pipeline, bounded queue. |
| **Limiter không chặn custom JSON login.** | Filter chỉ match POST /login formLogin; JSON endpoint ở path khác. | Xác định endpoint/method authentication thật và security order. |
| **Encoded path lách quota.** | Gateway/app/limiter khác nhau về URL normalization. | HTTP firewall và canonicalization nhất quán, test bypass paths. |
| **X-Forwarded-For thay đổi làm reset quota.** | Tin forwarded header do client tự khai. | Trusted proxy chain, edge overwrite và IP normalization. |
| **Metrics bùng cardinality khi bị attack.** | Username/IP làm metric label hoặc lưu keys không TTL. | Giảm labels, HMAC/TTL, global budget và memory protection. |
| **Login thành công, POST nghiệp vụ 403.** | CSRF token trước login bị xóa; không liên quan login quota. | Refresh CSRF token theo authenticated session. |
| **Login thành công nhưng user bị từ chối API.** | Authorization/session principal, không phải limiter. | Kiểm tra SecurityContext và quyền tài nguyên. |
| **IdP/OIDC trả lỗi liên tục.** | Upstream outage hoặc state/PKCE correlation, không phải mọi lỗi là password attempts. | Phân tích giao thức, limit auth initiation/callback riêng. |
| **CSP chặn fetch /login.** | HTML frontend connect-src/form-action không cho API origin. | Kiểm tra policy của HTML document, không nới wildcard thiếu kiểm soát. |
| **WAF chặn toàn bộ request trong giờ cao điểm.** | Quota global quá thấp hoặc false positive edge rule. | Canary/rollback policy, phân tích tải thật, hỗ trợ người dùng. |

### 15.1. Trình tự điều tra gọn

1. Xác định **request nào bị từ chối, tại tầng nào**: CDN/WAF, gateway, custom filter, CsrfFilter, AuthenticationProvider hay AuthorizationFilter.
2. Xem **method/path/status**, không tự coi mọi 403/429 là sai credential.
3. Kiểm tra **CORS preflight** và actual response nếu browser SPA báo lỗi.
4. Kiểm tra cookie/session và CSRF token có đúng trước POST login.
5. Với 429, xem **key scope, quota, TTL, source resolution, policy version**.
6. Với 401/302, xem **AuthenticationFailureHandler/provider**, không suy account existence từ message.
7. Kiểm tra **shared store** trên nhiều instance, timeout, failover và concurrency.
8. Tìm dấu hiệu **account enumeration, lockout DoS, NAT false positive và botnet bypass**.
9. Kiểm tra metrics/logs không chứa username/password hoặc raw IP ở nơi không được phép.
10. Sửa đúng tầng; không tắt CSRF/CORS/HTTP firewall hoặc giảm password hashing để che vấn đề quota.

### 15.2. Ranh giới chính sách edge và Spring phải thống nhất

Một tình huống phức tạp:

~~~text
WAF:
  POST /login vượt source quota → 429

Spring:
  POST /login với CSRF sai → 403
  POST /login với quota ứng dụng hết → 429
  POST /login credential sai → 401 hoặc 302
  POST /login thành công → session/redirect theo hợp đồng
~~~

Có thể có nhiều điểm trả 429, nhưng cần biết **tầng nào** đã trả và **đã tiêu quota nào** để user không bị phạt hai lần ngoài ý muốn. Một response header nội bộ/correlation ID có thể giúp logs phân biệt tầng, nhưng **không trả thông tin account status/policy bí mật** ra public response.

Nếu Spring còn nằm sau reverse proxy, đảm bảo **429 ở gateway không bị cache sai**, HTTPS/redirect được cấu hình đúng và các forwarded headers không thể bị người ngoài điều khiển để né quota.

### 15.3. Phân biệt quota enforcement với quyền đăng nhập

Ngay cả khi limiter ALLOW, request vẫn cần:

- CSRF token hợp lệ nếu dựa vào cookie/session và unsafe method.
- Credential đúng và account policy cho phép.
- MFA/step-up theo risk policy.
- Session fixation protection và quản lý SecurityContext.
- Authorization riêng cho các API nhạy cảm.
- Logout/session revocation đúng vòng đời.

**ALLOW trong limiter không bao giờ là “user đã được xác thực”**; **DENY không tự chứng minh mật khẩu sai hoặc user có tài khoản**. Đây là ranh giới cốt lõi để xây dựng hệ thống tránh nhầm bảo mật với kiểm soát lưu lượng.

## 16. Bài tập tình huống: xác định đúng ranh giới trách nhiệm

### Tình huống A — Đã dùng Spring Security thì tự chống brute-force?

Một ứng dụng bật formLogin, CSRF, HttpSession, HSTS và CSP. Không có limiter. Developer cho rằng Spring Security mặc định chặn login sau năm lần thử sai. Nhận định có đúng không?

**Đáp án:** Không. Spring Security cung cấp authentication/authorization và các lớp bảo vệ HTTP/trình duyệt, **không mặc định có một chính sách rate limiting tổng quát theo IP/username cho mọi formLogin**. Cần tích hợp limiter/risk controls riêng và kiểm thử thực tế.

### Tình huống B — CSRF token hợp lệ nghĩa là người thật?

Một bot tạo anonymous session, gọi GET /csrf rồi gửi POST /login với token hợp lệ hàng trăm lần. CSRF có nghĩa bot không thể làm vậy không?

**Đáp án:** Không. CSRF chứng minh request có token hợp lệ theo cơ chế server, **không chứng minh người dùng là con người** hoặc hạn chế tần suất. Cần admission quota, risk detection và bảo vệ endpoint token issuance.

### Tình huống C — CORS đã chỉ cho frontend chính thức

API /login chỉ trả Access-Control-Allow-Origin cho app.example.com. Một HTTP client bên ngoài vẫn gửi POST thử credential. Có phải CORS đã thất bại?

**Đáp án:** Không. CORS quản lý browser cross-origin access, không chặn HTTP client ngoài browser. Dùng authentication và rate limits ở edge/app; không biến Origin header thành chứng cứ xác thực.

### Tình huống D — Dùng StrictHttpFirewall như rate limiter

Nhóm cấu hình StrictHttpFirewall để chặn URL xấu nhưng không đếm attempts. Có thể coi đây là bảo vệ password spraying không?

**Đáp án:** Không. Firewall kiểm tra cấu trúc/phạm vi request, **không thay quota theo thời gian**. Một POST /login hợp lệ vẫn có thể được gửi hàng loạt.

### Tình huống E — Một IP, nhiều user thật

Trường học có hàng trăm học sinh dùng cùng IP public. Quota 5 POST /login/phút/IP làm cả lớp bị 429. Nguyên nhân và cách xử lý?

**Đáp án:** NAT/CGNAT khiến một source IP đại diện cho nhiều user. Cần điều chỉnh ngưỡng theo dữ liệu, kết hợp nhiều tín hiệu và cơ chế hỗ trợ/challenge; không chỉ tăng vô hạn hoặc tắt bảo vệ.

### Tình huống F — Một user, nhiều IP

Một account bị thử password từ nhiều mạng khác nhau, mỗi IP chỉ một lần nên IP limiter không chặn. Cần thêm gì?

**Đáp án:** Identifier/risk signals và phát hiện phân tán, cùng chính sách chống lockout DoS. Không dùng account-based quota duy nhất để tránh attacker gây khóa user thật.

### Tình huống G — Password spraying qua hàng nghìn username

Kẻ tấn công chỉ thử một mật khẩu với mỗi identifier nên không ai vượt ngưỡng 5 lỗi/user. Hệ thống có cần thiết kế khác không?

**Đáp án:** Có. Cần phát hiện pattern **nhiều identifiers từ cùng nguồn/campaign**, kết hợp source/global budgets và risk detection; đếm lỗi theo user đơn lẻ không đủ.

### Tình huống H — Account lockout thành công cụ tấn công

Bất kỳ ai nhập năm lần sai cho email của người khác đều làm tài khoản đó bị khóa 24 giờ. Rủi ro gì?

**Đáp án:** **Account lockout DoS**. Cân nhắc temporary throttle/step-up/nguồn rủi ro, cơ chế phục hồi và không công khai trạng thái locked trước ownership verification.

### Tình huống I — 429 chỉ cho account có thật

Backend chỉ tạo counter nếu lookup user thành công. Username tồn tại vượt quota trả 429, username không tồn tại luôn 401. Điều gì xảy ra?

**Đáp án:** 429 trở thành **account enumeration oracle**. Admission policy nên áp dụng không phụ thuộc user existence ở tầng công khai, hoặc có cách mapping rủi ro không tiết lộ existence.

### Tình huống J — Đổi X-Forwarded-For để né quota

Ứng dụng lấy phần đầu X-Forwarded-For từ request bất kỳ để tạo IP key; client tự đổi header ở mỗi lần thử. Cần sửa gì?

**Đáp án:** Chỉ tin IP qua **trusted proxy chain** được edge làm sạch/ghi đè và backend không bị bypass. Không dùng IP do client tự khai làm key tin cậy.

### Tình huống K — Bốn instances có bốn quota

Mỗi instance dùng ConcurrentHashMap cho phép 10 request/phút. Qua load balancer, source gửi được nhiều hơn 10 request/phút. Lý do?

**Đáp án:** Quota **per-instance**, không phải shared toàn cluster. Cần shared atomic store như Redis hoặc quota tập trung tại edge; sticky sessions không thay consistency guarantee.

### Tình huống L — INCR rồi EXPIRE tách rời

Code tăng Redis counter, sau đó EXPIRE ở một lệnh riêng. Nếu tiến trình chết giữa hai lệnh, key có thể không hết hạn. Hướng xử lý?

**Đáp án:** Dùng một cơ chế **atomic** (script/transaction phù hợp) đặt TTL khi khởi tạo counter, và kiểm thử TTL/memory. Không chỉ tin vì cả hai lệnh thường chạy nhanh.

### Tình huống M — Fixed window cho burst ở ranh giới

Limiter cho 5 attempts/phút, attacker gửi 5 gần cuối phút và 5 ngay đầu phút sau. Có phải thuật toán sai?

**Đáp án:** Đây là **window boundary burst** của fixed window, không nhất thiết là lỗi code. Nếu threat model cần tránh burst này, cân nhắc sliding window hoặc token bucket với capacity/refill phù hợp.

### Tình huống N — Token bucket có 10 token

User gửi 8 requests liên tiếp và vẫn được phép dù refill rate chỉ 1 token mỗi 6 giây. Đó có phải bug?

**Đáp án:** Không nhất thiết. Token bucket cho phép **burst đến capacity** khi bucket đang đầy và kiểm soát tốc độ trung bình bằng refill. Cần hiểu capacity khác refill rate.

### Tình huống O — Limiter đặt sau PasswordEncoder

Custom failure handler kiểm tra quota chỉ sau khi PasswordEncoder.matches hoàn tất. Nó đã ngăn CPU exhaustion chưa?

**Đáp án:** Chưa đầy đủ. Nó có thể giảm attempts sau đó nhưng request hiện tại đã tiêu CPU. Cần **pre-auth admission** hoặc concurrency protection trước bước verify đắt, kết hợp post-auth observation.

### Tình huống P — OPTIONS bị tính là login

SPA gửi custom header CSRF nên browser preflight OPTIONS, limiter tăng failed-login counter và cuối cùng khóa account. Có phù hợp không?

**Đáp án:** Không. OPTIONS chỉ hỏi CORS policy, không chứa password. Bộ đếm POST login attempts phải bỏ qua OPTIONS; nếu cần bảo vệ OPTIONS flood, dùng quota mạng riêng.

### Tình huống Q — POST thiếu CSRF không tới limiter app

Filter đặt ngay trước UsernamePasswordAuthenticationFilter, CsrfFilter từ chối request thiếu token trước đó. Tester nói limiter không hoạt động. Nhận định chính xác không?

**Đáp án:** Không. Đây có thể là **thứ tự bảo vệ đúng**. Test quota với POST có CSRF hợp lệ; edge/global quota có thể bảo vệ tổng request kể cả request sai CSRF.

### Tình huống R — 429 từ WAF bị CORS chặn

Backend có CORS đúng, nhưng WAF trả 429 mà không có Access-Control-Allow-Origin cho frontend. SPA thấy Network/CORS error rồi liên tục retry. Cách giải quyết?

**Đáp án:** Cấu hình **CORS cho actual error response tại edge** theo allowed origin/credentials, không mở wildcard. Frontend phải phân biệt 429 và lỗi mạng, tôn trọng Retry-After và không retry vô hạn.

### Tình huống S — Redis lỗi nhưng server trả “thử quá nhiều”

Limiter store bị timeout, code bắt mọi exception và tạo AdmissionDecision.reject(3600). Có hợp lý không?

**Đáp án:** Không nên map mọi lỗi store thành **quota exceeded**. Chọn fail-open/closed/degraded rõ; báo lỗi vận hành phù hợp, ghi metrics riêng, tránh chặn user dài hạn vì Redis outage.

### Tình huống T — Reactive WebFilter dùng RedisTemplate blocking

Một WebFlux limiter gọi RedisTemplate đồng bộ trong WebFilter; dưới tải, login và những request khác đều tăng latency. Vấn đề?

**Đáp án:** Blocking call trên **event loop**. Dùng reactive client, async admission, timeouts và bounded concurrency; không chỉ bọc blocking call bằng Mono.just.

### Tình huống U — Một request bị đếm hai lần

Một LoginAdmissionFilter vừa được đánh dấu @Component, vừa được thêm bằng addFilterBefore trong HttpSecurity; mỗi POST bị trừ hai token. Vì sao?

**Đáp án:** Có thể bị đăng ký **hai đường filter execution**. Chọn một điểm đăng ký chính xác, kiểm tra filter order và test request count.

### Tình huống V — Bật CORS wildcard để thấy lỗi 429

Để SPA đọc 429, team đặt Access-Control-Allow-Origin: * cùng Allow-Credentials: true. Có hợp lệ không?

**Đáp án:** Không phù hợp credentialed CORS browser. Cần **origin allowlist cụ thể**, trả CORS headers đúng tại cả gateway và backend cho response thực.

### Tình huống W — Email trong Redis key và metrics

Limiter lưu login:email:person@company.example và dùng email làm Prometheus label, tạo millions time series khi bị spam. Vấn đề?

**Đáp án:** Vừa rò **dữ liệu cá nhân** vừa gây **high cardinality/cạn bộ nhớ**. Dùng HMAC key/TTL theo mục đích, metrics labels low-cardinality, giới hạn key creation và có retention.

### Tình huống X — Login thành công nhưng POST profile bị 403

Sau login, SPA POST /api/profile dùng CSRF token cũ và bị 403. Developer tăng quota rồi thử lại. Có đúng hướng không?

**Đáp án:** Không. Token trước login có thể đã bị xóa theo authentication strategy. Lấy token mới từ phiên authenticated và phân biệt **CSRF 403** với **limiter 429**.

### Tình huống Y — Custom JSON login không được giới hạn

Limiter chỉ match POST /login của formLogin mặc định, nhưng app còn POST /api/auth/signin đọc JSON. Tấn công vào JSON endpoint không bị quota. Cần gì?

**Đáp án:** Thống kê và bảo vệ **tất cả authentication entry points** bằng matcher/order phù hợp, không chỉ path mặc định. Giữ CSRF nếu JSON endpoint dùng cookie/session tự gửi.

### Tình huống Z — Tăng hash cost để chống brute-force

Team tăng BCrypt cost mạnh rồi bỏ rate limiter, dẫn đến CPU 100% khi nhiều POST login. Vì sao?

**Đáp án:** Password hashing mạnh chống **offline cracking**, nhưng làm mỗi lần verification tốn tài nguyên hơn; nó **không hạn chế số lần request**. Cần admission control, concurrency protection, risk detection và capacity planning.

## 17. Checklist triển khai an toàn

### 17.1. Phân định trách nhiệm

- [ ] Có tài liệu nói rõ **Spring Security không mặc định cung cấp login rate limiting tổng quát**.
- [ ] Xác định ai sở hữu **edge/WAF quota, app quota, failed-attempt tracking, account lockout, risk detection**.
- [ ] Phân biệt **HTTP firewall/CSRF/CORS** với request-rate limiting; không dùng một lớp làm thay mọi lớp khác.
- [ ] Xác định tất cả entry points: **formLogin, custom JSON login, SSO initiation/callback, MFA, password reset**.
- [ ] Định nghĩa thuật ngữ **attempt, failure, blocked-before-auth, challenge, verified success**.
- [ ] Phân biệt ngân sách pre-auth admission với signals phát sinh sau authentication provider.
- [ ] Giữ session fixation protection, security context và authorization cho tài nguyên sau login.
- [ ] Không coi limiter ALLOW là bằng chứng identity hoặc quyền.

### 17.2. Khóa, thuật toán và quota

- [ ] Có **source/global/identifier/composite policies** theo threat model, không lệ thuộc một IP.
- [ ] Source IP được lấy theo **trusted proxy configuration**, không tin X-Forwarded-For tùy ý.
- [ ] Identifier normalization nhất quán với authentication; không tự thay quy tắc email/tenant.
- [ ] Không lưu plaintext password, session/CSRF token trong limiter keys/logs.
- [ ] Hạn chế PII trong Redis bằng HMAC/TTL và kiểm soát secret rotation/retention.
- [ ] Chặn identifier quá dài/không hợp lệ và **unique-key cardinality attacks**.
- [ ] Đã chọn fixed/sliding/token bucket dựa trên traffic, burst behavior và chi phí lưu trữ.
- [ ] Có ngân sách **global concurrency** cho CPU password hashing/IdP nếu cần.
- [ ] Không để queue/waiting requests vô hạn khi overload.
- [ ] Quota có cơ chế kiểm thử bằng **test clock** hoặc fixtures ổn định.
- [ ] Chính sách account lockout không cho attacker dễ dàng khóa user khác vĩnh viễn.
- [ ] Source/identifier quota không vô tình tiết lộ account existence qua 429/status/headers/timing.

### 17.3. Servlet và Spring MVC

- [ ] Dùng **SecurityFilterChain/HttpSecurity** và đặt admission filter **trước authentication filter thật**.
- [ ] LoginAdmissionFilter match đúng POST login, không tính GET /login, GET /csrf hoặc OPTIONS như password attempts.
- [ ] Custom filter không được đăng ký toàn cục trùng với addFilterBefore ngoài ý định.
- [ ] POST /login vẫn qua CsrfFilter khi dùng cookie/session; permitAll không tắt CSRF.
- [ ] Admission DENY trả 429, Retry-After phù hợp, no-store và không tạo authenticated session.
- [ ] Admission ALLOW tiếp tục vào AuthenticationManager/Provider và failure/success handlers.
- [ ] Không đọc request body/password trong source-only limiter filter.
- [ ] Khi dùng username key, có validation/normalization, anti-enumeration và body-handling đúng.
- [ ] Authentication events/failure handler cập nhật risk store an toàn, không ghi raw credential.
- [ ] Khi có nhiều SecurityFilterChain, thứ tự/matcher đã được test để không bỏ qua limiter.

### 17.4. Reactive/WebFlux

- [ ] Dùng **SecurityWebFilterChain/ServerHttpSecurity**, không trộn HttpServletRequest/OncePerRequestFilter.
- [ ] Reactive limiter **trả Mono/Publisher thực sự nonblocking**, không dùng blocking RedisTemplate trong event loop.
- [ ] CORS/CSRF, admission và formLogin filters có thứ tự phù hợp.
- [ ] WebFilter chỉ xử lý POST login và không tự consume request body.
- [ ] Mọi error/cancellation path dọn concurrency permit và connection khi cần.
- [ ] Có timeout, bounded queue và overloaded behavior rõ ràng.
- [ ] Response 429 được ghi đúng theo reactive API và CORS policy.
- [ ] Kiểm thử WebTestClient cả 429, 403 CSRF và authentication outcomes.
- [ ] Custom ReactiveAuthenticationManager không bỏ qua risk policy/session lifecycle.
- [ ] WebSession không được dùng như proof-of-human và không tự trở thành rate limiter.

### 17.5. Distributed store và availability

- [ ] Quota **atomic** trên nhiều instances, không phụ thuộc ConcurrentHashMap mỗi pod.
- [ ] Redis counter/token bucket có **TTL hoặc expiration** được thiết kế đúng và test.
- [ ] Nếu dùng nhiều keys, xác định semantics partial-consume so với all-or-nothing.
- [ ] Đánh giá consistency khi failover, replication, sharding hoặc multi-region.
- [ ] Quota service có timeout/connection pool/circuit breaker/budget phù hợp.
- [ ] Xử lý limiter unavailable bằng **fail-open/closed/degraded policy** được phê duyệt.
- [ ] Không map Redis error thành 429 “thử quá nhiều” khi không có quota decision.
- [ ] Có bounded memory, eviction/TTL monitoring và giới hạn số key từ attacker input.
- [ ] Metrics latency/errors/rejections không gắn raw username/IP labels.
- [ ] Có kế hoạch khôi phục khi Redis bị mất dữ liệu hoặc counter reset giữa chiến dịch.

### 17.6. Browser, HTTP và phản hồi lỗi

- [ ] CSRF token hợp lệ được cấp trước POST /login, không tắt CSRF để tránh 403.
- [ ] Session cookie có Secure/HttpOnly/SameSite/Path/Domain phù hợp.
- [ ] CORS cho /csrf và /login có allowed origins/methods/headers, tránh wildcard với credentials.
- [ ] **OPTIONS preflight không tiêu password-attempt quota**.
- [ ] **429 ở gateway** cũng có CORS actual response hợp lệ cho frontend được duyệt.
- [ ] **Cache-Control: no-store** được dùng khi thích hợp cho login/CSRF/error responses.
- [ ] Retry-After không lộ trạng thái khóa của một account cụ thể.
- [ ] Login page CSP và HSTS hỗ trợ browser security nhưng không được ghi nhận như rate limiter.
- [ ] HTTP firewall/URL normalization ở proxy và Spring nhất quán để tránh path bypass.
- [ ] 401/403/429/503 được phân loại đúng; frontend không retry credential vô hạn.
- [ ] Lỗi login giữ thông báo công khai tổng quát, không lộ user-existence, exception hoặc password.
- [ ] Sau login thành công frontend lấy CSRF token mới nếu token cũ đã bị dọn.

### 17.7. Kiểm thử âm tính và vận hành

- [ ] Mẫu brute-force một account từ một source được phát hiện theo policy.
- [ ] Password spraying nhiều accounts từ một source được kiểm soát.
- [ ] Distributed low-rate attempts không hoàn toàn né mọi tín hiệu/risk monitoring.
- [ ] Shared-IP/NAT scenario không gây false-positive trầm trọng ở tải hợp lệ.
- [ ] Account lockout abuse không thể dễ dàng khóa vĩnh viễn một user chỉ bằng input anonymous.
- [ ] Known/unknown user không có 429/password failure oracle theo existence.
- [ ] GET/OPTIONS và CSRF-invalid requests không làm hỏng counters theo policy.
- [ ] POST có token CSRF hợp lệ, quota hết, trả 429 trước authentication provider.
- [ ] Khi quota còn, login success/failure và session protections vẫn đúng.
- [ ] Test nhiều requests đồng thời qua nhiều instances với Redis atomic quota.
- [ ] Redis outage, timeout, eviction và degraded mode đều có kịch bản.
- [ ] API Gateway/WAF và Spring không vô tình double-count hoặc conflict policies.
- [ ] Metrics/alerts theo dõi 401/403/429/5xx, auth latency và limiter errors riêng.
- [ ] Logs không chứa raw credentials, CSRF/session/refresh tokens hoặc PII ngoài mục đích.
- [ ] Runbook có bước rollback policy, incident triage và hỗ trợ người dùng thật.
- [ ] Không chạy thử credential stuffing trên tài khoản/production không được phép; dùng fixtures và traffic nhỏ trong môi trường kiểm thử.

## 18. Ghi nhớ

1. **Spring Security không mặc nhiên giới hạn số lần thử đăng nhập theo IP/user.** Spring Security cung cấp authentication, authorization, CSRF, CORS integration, session protection, firewall và headers; **rate limiting là chính sách bổ sung** ở edge, ứng dụng hoặc một dịch vụ khác.
2. **Rate limiting không thay CSRF**, và CSRF không phân biệt bot với người thật. Một client có thể lấy token hợp lệ rồi thử nhiều credentials, vì vậy cần nhiều lớp phòng vệ.
3. **Credential stuffing, password spraying, brute-force, account lockout abuse và resource exhaustion** có mô hình khác nhau; một counter theo username hoặc IP không giải quyết tất cả.
4. **Pre-auth admission** hạn chế request trước thao tác password verification tốn tài nguyên; **post-auth observation** ghi kết quả thật phục vụ risk/monitoring. Cần cả hai khi threat model yêu cầu.
5. **Fixed window, sliding window, token bucket và concurrency limit** có tradeoffs khác nhau. Chọn dựa trên burst, tài nguyên, false positives và tính nhất quán.
6. **IP nguồn phải đến từ trusted proxy chain**, không tin X-Forwarded-For do client tự khai. Identifier chưa xác thực có thể là attacker input, không dùng nó làm bằng chứng user/account.
7. **Bộ đếm phân tán cần atomic operations, TTL, bounded memory và policy khi store unavailable.** Một ConcurrentHashMap mỗi pod không thực hiện quota toàn cluster.
8. **429 Too Many Requests** là quyết định quota, khác 401 credential failure, 403 CSRF/authorization và 503 service outage. Retry-After/headers không được tạo account enumeration.
9. Với **Servlet**, có thể thêm **OncePerRequestFilter** trước UsernamePasswordAuthenticationFilter; với **WebFlux**, thêm WebFilter **nonblocking** vào SecurityWebFilterChain ở vị trí phù hợp. Không trộn Servlet API với Reactive hoặc đăng ký bộ lọc hai lần.
10. **CORS preflight không phải password attempt**, và 429 ở gateway phải có response headers cho frontend hợp lệ khi cần. CORS không tự chặn HTTP client hay brute-force.
11. **Bảo vệ session, HSTS, CSP, HTTP firewall, MFA, CAPTCHA và PasswordEncoder** là những lớp bổ trợ có mục tiêu riêng. Không giảm password hash security hoặc tắt CSRF để chữa nghẽn login.
12. **Kiểm thử cốt lõi:** request vượt quota bị chặn trước provider, request còn quota vẫn xác thực đúng; GET/OPTIONS/CSRF không bị đếm nhầm; quota nhất quán nhiều instance; có xử lý Redis outage; không lộ danh tính hay khóa nhầm user thật.

## Tài liệu tham khảo định hướng

Đối chiếu **Spring Security Reference theo phiên bản dự án** khi triển khai, và kiểm tra tài liệu thuật toán/Redis client theo phiên bản thực tế. Những liên kết dưới đây giúp tra cứu các lớp nền tảng mà bài sử dụng; rate limiter cụ thể là phần mở rộng hoặc dịch vụ ngoài Spring Security:

- [Spring Security Reference — Servlet Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html)
- [Spring Security Reference — Reactive Web Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security Reference — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security Reference — Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html)
- [Redis — Rate Limiting Patterns](https://redis.io/learn/develop/java/spring/rate-limiting/fixed-window)

**Nguyên tắc kết thúc bài:** Chỉ khi tách rõ **ai xác minh mật khẩu, ai quyết định quota, ai ghi nhận rủi ro, ai bảo vệ HTTP/browser và ai xử lý sự cố**, hệ thống Spring Security mới có thể vừa bảo vệ endpoint đăng nhập trước lạm dụng vừa duy trì đường đăng nhập hợp lệ cho người dùng thật.
