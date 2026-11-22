# Phản hồi đăng nhập thất bại và giới hạn tiết lộ thông tin tài khoản

## 1. Mục tiêu, phạm vi và tình huống thực tế

Khi người dùng nhập sai thông tin đăng nhập, server phải **từ chối xác thực** nhưng đồng thời tránh vô tình tiết lộ thông tin như “username này có tồn tại”, “tài khoản đang khóa”, “email có đăng ký” hay “mật khẩu đúng nhưng thiếu bước khác”. Bài học này thuộc phần **Đăng nhập và đăng xuất** của **Spring Security - fundamentals**, tập trung vào **phản hồi đăng nhập thất bại** và cách hạn chế **account enumeration** (liệt kê tài khoản).

Sau khi học, bạn có thể:

1. Giải thích vì sao thông báo đăng nhập thất bại có thể trở thành kênh tiết lộ thông tin tài khoản.
2. Phân biệt phản hồi cho **sai credentials**, **thiếu credentials**, **không đủ quyền**, **CSRF không hợp lệ** và **rate limit**, không trộn tất cả thành một lỗi tùy tiện.
3. Hiểu luồng xác thực thất bại qua `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `AuthenticationFailureHandler` và mặc định `/login?error` của Spring Security Servlet.
4. Chọn thông báo công khai phù hợp với browser form và JSON API; giữ nguyên tắc “thông điệp, status, URL và metadata không được tiết lộ user tồn tại”.
5. Nhận ra **timing side channel**, username-not-found exception, sự khác nhau về redirect, response size, email/sms recovery, MFA và lockout.
6. Thiết kế bảo vệ chống brute-force/password spraying/credential stuffing bằng throttling theo nhiều tín hiệu và giám sát an toàn, không gây account-lockout DoS.
7. Chạy ứng dụng Java 17 + Spring Boot 3.5.12, kiểm thử cùng phản hồi công khai cho username không tồn tại, sai password và tài khoản disabled; test CSRF 403 và login thành công.

**Phạm vi kỹ thuật:** phần chạy được dùng **Spring MVC/Servlet**, `HttpSecurity` và `SecurityFilterChain`, với `formLogin` mặc định. Spring WebFlux dùng `SecurityWebFilterChain`/`ServerHttpSecurity` và các thành phần reactive tương ứng; nguyên tắc bảo vệ dữ liệu giống nhau nhưng không dùng lớp Servlet trực tiếp trong WebFlux.

## 2. Vì sao lỗi đăng nhập là một lỗ hổng về quyền riêng tư?

Giả sử một hệ thống có tài khoản `alice`. Kẻ tấn công gửi hai yêu cầu:

```text
POST /login   username=alice    password=wrong
POST /login   username=made-up  password=wrong
```

Nếu server trả:

```text
alice     → "Sai mật khẩu!"
made-up   → "Không tồn tại người dùng!"
```

thì kẻ tấn công biết `alice` là một tài khoản thật mà **không cần đăng nhập thành công**. Danh sách username/email hợp lệ có thể được dùng để thử mật khẩu, lừa đảo có mục tiêu, credential stuffing hoặc khai thác thông tin riêng tư khác.

Ngay cả khi màn hình hiển thị cùng dòng chữ **“Tên đăng nhập hoặc mật khẩu không đúng”**, vẫn có thể tồn tại các khác biệt bên ngoài:

- **HTTP status:** ví dụ 401 cho user có thật và 404 cho user không tồn tại.
- **Redirect/Location:** `/login?bad-password` khác `/login?unknown-user`.
- **Response body/length/headers:** lượng HTML, JSON, thông tin `WWW-Authenticate`, cookie hay header khác nhau.
- **Thời gian phản hồi:** tài khoản tồn tại phải kiểm tra hash mật khẩu (tốn CPU), còn user không tồn tại kết thúc quá nhanh.
- **Thời gian nhận email/sms:** password recovery chỉ gửi thư cho account có thật, hoặc API trả lời khác nhau.
- **Rate limiting/lockout:** chỉ tên có thật được tính số lần thất bại rồi trả “đang khóa”.
- **MFA/SSO flow:** ứng dụng chỉ hiện màn hình bước tiếp theo khi tên đăng nhập hợp lệ, vô tình tiết lộ account.
- **Side effect quan sát được:** captcha, chính sách mật khẩu, trang hỗ trợ, mã trạng thái API hoặc thông báo “Tài khoản chưa kích hoạt”.

**Mục tiêu thiết kế:** với cùng lớp tình huống *đăng nhập không thành công*, người ngoài **không phân biệt đáng tin** tài khoản có tồn tại hay không chỉ bằng response và các hành vi quan sát được. Mục tiêu này cần kết hợp nhiều biện pháp; một thông báo chung chỉ là bước đầu.

### Account enumeration khác brute force thế nào?

| Kiểu tấn công | Mục tiêu chính | Ví dụ |
| --- | --- | --- |
| **Username/account enumeration** | Xác định định danh tài khoản hợp lệ | So sánh phản hồi cho email có/không tồn tại |
| **Brute-force password** | Đoán mật khẩu của một account | Thử nhiều password cho `alice` |
| **Password spraying** | Thử cùng một số mật khẩu phổ biến trên nhiều accounts | `Password123` với nhiều usernames |
| **Credential stuffing** | Thử cặp username/password từ vụ rò rỉ khác | Đưa bộ credentials bị lộ vào form login |

Giảm account enumeration không thay thế rate limit/MFA. Ngược lại, hạn chế brute-force ở mọi lớp cũng giúp giảm tốc độ enumeration.

## 3. Thông báo nên nói gì và không nên nói gì?

**Thông báo công khai phù hợp:**

> Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra lại thông tin hoặc sử dụng chức năng khôi phục tài khoản.

Với ứng dụng phù hợp, có thể dùng câu ngắn **“Tên đăng nhập hoặc mật khẩu không đúng.”** Thông báo phải nhất quán cho tài khoản không tồn tại và sai mật khẩu. Với account locked/disabled, thiết kế có thể cân bằng UX và privacy; nếu mục tiêu là chống enumeration, không trả lý do đặc thù cho client chưa được xác thực.

**Các thông báo không nên trả trực tiếp cho request chưa xác thực:**

```text
"Email alice@example.com đã đăng ký nhưng mật khẩu sai."
"Không tìm thấy user có tên alice."
"Tài khoản này có thật nhưng đã bị quản trị viên khóa."
"Tài khoản này đang chờ kích hoạt."
"Tên đăng nhập đúng, vui lòng nhập OTP."   // nếu bước này tiết lộ user hợp lệ
"Không tìm thấy user trong bảng users."
"org.springframework.security.authentication.BadCredentialsException: ..."
```

Cũng không nên trả stack trace, tên class nội bộ, SQL, bean identifiers, session IDs, token, tên nhóm nội bộ, hoặc phân biệt `reason=user_not_found` và `reason=password_wrong` trong JSON.

### Ma trận phản hồi khi chưa biết danh tính

| Tình huống trong hệ thống | Thông điệp công khai dự kiến | Hành động nội bộ |
| --- | --- | --- |
| Username không tồn tại | Lỗi đăng nhập chung | Theo dõi thất bại, tăng các giới hạn phù hợp |
| Username tồn tại nhưng password sai | **Cùng** lỗi chung | Theo dõi thất bại, tăng giới hạn |
| Account disabled/locked theo chính sách | **Cùng** lỗi chung khi chống enumeration | Ghi lý do nội bộ, hỗ trợ khôi phục an toàn |
| User đúng và password đúng | Xác thực thành công | Tạo/cập nhật session theo cơ chế login |
| Request thiếu CSRF token | 403, không xử lý như password sai | Chặn bởi CSRF filter, hướng dẫn tải lại form hợp lệ nếu phù hợp |
| Request bị throttling | 429 hoặc cơ chế challenge có cùng nguyên tắc bảo vệ | Kiểm soát tốc độ và ghi audit |
| Backend identity store không khả dụng | Lỗi dịch vụ 5xx chung, không giả vờ “sai mật khẩu” | Fail closed, giám sát sự cố |

**Lưu ý:** không phải mọi thất bại HTTP đều phải cùng một status. CSRF là lỗi bảo vệ request, rate limit là điều kiện lưu lượng, còn identity provider bị lỗi là sự cố dịch vụ. Yêu cầu an toàn là **không để thông tin user có/không tồn tại điều khiển phản hồi khác nhau trong cùng đường đăng nhập**. Đừng vô tình trả 429 chỉ cho username có thật hoặc trả 500 kèm stack trace cho username không có thật.

## 4. Spring Security xử lý form login thất bại ở đâu?

Trong cấu hình Servlet `formLogin`, luồng điển hình là:

```text
POST /login + username/password + CSRF
       │
       ▼
CsrfFilter
  ├─ token thiếu/sai → chặn 403, không thử password
  └─ hợp lệ
       │
       ▼
UsernamePasswordAuthenticationFilter
       │
       └─ AuthenticationManager
             │
             ├─ xác thực thành công
             │     ├─ Authentication đã xác thực
             │     ├─ SessionAuthenticationStrategy / SecurityContext
             │     └─ AuthenticationSuccessHandler → trang đích
             │
             └─ xác thực thất bại
                   ├─ xóa SecurityContext của lần thử thất bại
                   ├─ thông báo RememberMeServices.loginFail (nếu có)
                   └─ AuthenticationFailureHandler
                         └─ mặc định redirect /login?error
```

**Quan trọng:** `AuthenticationFailureHandler` xử lý *xác thực thất bại* sau khi filter xác thực bắt được `AuthenticationException`. Nó không nhất thiết chạy khi `CsrfFilter` đã chặn request, khi một route bị authorization 403, hay khi reverse proxy từ chối request trước khi vào ứng dụng.

### Mặc định Spring Security thường làm gì?

Với cấu hình `formLogin(Customizer.withDefaults())` hoặc DSL tương đương:

- `GET /login` được Spring Security tạo trang login mặc định nếu bạn không cấu hình trang riêng.
- `POST /login` nhận form có hai tham số `username` và `password` (có thể cấu hình tên khác).
- Xác thực sai sẽ gọi `AuthenticationFailureHandler`, thường `SimpleUrlAuthenticationFailureHandler` chuyển hướng tới **`/login?error`**.
- Trang login mặc định hiển thị thông điệp lỗi chung; không nên hiển thị nguyên văn exception do framework lưu trong request/session.
- Form login thường có CSRF protection; form hợp lệ cần token trong POST.
- Một lần POST sai thường trả **302 Redirect**, sau đó browser GET `/login?error` nhận HTML. Đây là **hai HTTP responses** khác nhau.

Điểm cuối cần phân biệt: **302 không có nghĩa login thành công**, vì cả login thành công và login thất bại đều có thể redirect. Phải xét Location/đích đến và security context theo cấu hình, không chỉ kiểm tra 3xx.

### Đặt failureUrl và failureHandler

Spring Security cung cấp hai mức tùy biến:

```java
.formLogin(form -> form
    .failureUrl("/login?error")
    .permitAll()
)
```

Đây là một **fragment** bên trong `HttpSecurity`. `failureUrl` dùng khi browser dự kiến nhận redirect sau xác thực thất bại. Đó cũng là giá trị mặc định của form login tiêu chuẩn; ghi tường minh giúp người đọc xác định contract.

Nếu muốn JSON API hoặc logging có cấu trúc, dùng `AuthenticationFailureHandler` phù hợp. Nhưng **đừng chuyển mọi exception sang URL khác nhau** như `?reason=unknown`, `?reason=disabled`. Dù UI hiển thị thông báo chung, URL/headers vẫn bị client quan sát.

## 5. UsernameNotFoundException, BadCredentialsException và thông tin lộ ra

Spring Security có những loại lỗi xác thực cụ thể, ví dụ:

- `UsernameNotFoundException`: user store không tìm thấy username.
- `BadCredentialsException`: credentials không hợp lệ.
- `DisabledException`: tài khoản disabled.
- `LockedException`: tài khoản locked.
- `AccountExpiredException` và `CredentialsExpiredException`: các điều kiện thời hạn tài khoản/credentials.

Các class trên **hữu ích cho xử lý nội bộ**. Không nên dùng tên class hoặc nội dung `exception.getMessage()` để tạo thông điệp khác biệt cho client public.

`AbstractUserDetailsAuthenticationProvider` có cấu hình `hideUserNotFoundExceptions`, với hành vi mặc định thông thường **ẩn sự phân biệt giữa username không tồn tại và password sai bằng cách phát `BadCredentialsException`**. Tùy biến `setHideUserNotFoundExceptions(false)` có thể làm lộ khác biệt nội bộ; càng nguy hiểm nếu failure handler trả exception message ra ngoài. Mặc dù vậy, việc ẩn exception **không tự xử lý timing side channel** hoặc những luồng reset-password/MFA.

**Không lấy exception type làm tài nguyên public.** Một endpoint JSON như:

```json
{"error": "INVALID_CREDENTIALS"}
```

tốt hơn kiểu:

```json
{"error": "USER_NOT_FOUND", "usernameExists": false}
```

Tuy nhiên, quyết định chính sách phải xét cả status, headers, size, thời gian và rate limiting. Hai response JSON giống nhau không đủ bảo đảm không có side channel.

### Không lưu “last failure reason” để render thẳng cho người lạ

Một số failure handlers có thể lưu `AuthenticationException` vào session/request để trang login truy cập. Phải kiểm soát cách view sử dụng giá trị này: không đưa raw `SPRING_SECURITY_LAST_EXCEPTION.message` cho người dùng nếu nó mang thông tin account state hoặc nội bộ. Với UI tùy biến, chỉ dựa trên flag `error` để hiện lỗi chung; chi tiết có thể ghi audit nội bộ theo mức độ cần thiết.

## 6. Trạng thái HTTP: 302, 401, 403, 429 và 5xx

Đừng có một hàm chung biến mọi lỗi thành “401” hoặc “403”; ý nghĩa HTTP khác nhau.

| Mã thường gặp | Tình huống hợp lý | Điều cần tránh |
| --- | --- | --- |
| **302/303** | Browser form login gửi redirect tới `/login?error` khi thất bại | Redirect tới URL riêng theo username tồn tại |
| **401 Unauthorized** | API authentication thất bại hoặc cần credentials, tùy mechanism/entry point | Lẫn 401 với 403 chỉ vì account có/không tồn tại |
| **403 Forbidden** | User đã xác thực nhưng thiếu quyền; hoặc CSRF bị từ chối | Gọi mọi 403 là sai password |
| **429 Too Many Requests** | Throttling/rate limiting | Trả 429 chỉ cho tên user thật và làm lộ account |
| **500/503** | Lỗi identity store hoặc sự cố hạ tầng | Trả stack trace hoặc che sự cố thành thông báo “user không tồn tại” |

**HTTP Basic:** authentication entry point có thể phát `401` cùng `WWW-Authenticate`. **Browser form login:** failure handler mặc định thường phát redirect 302 thay vì 401 tại POST `/login`. Hai mô hình đều có thể đúng nếu contract được xác định rõ. Một API password-login do bạn tự xây có thể chọn `401` với JSON chung; không nên kỳ vọng Spring form login tự trả JSON.

Khi user đã đăng nhập nhưng truy cập `/admin` không có role, 403 thường do **authorization**; đó không phải “lần đăng nhập thất bại” để tăng login failure counter. Khi CSRF token sai, 403 thường do **CSRF validation**, cũng không nên ghi là password sai.

### Tách internal reason khỏi external response

Một kiến trúc có thể ánh xạ:

```text
INTERNAL_REASON                     PUBLIC_RESPONSE
unknown_username                  ┐
password_mismatch                 ├── /login?error
account_disabled                  │   thông báo chung
account_locked                    ┘
                                   (cùng status/location/UX hợp lý)

CSRF_INVALID                       → 403 Forbidden (không kiểm mật khẩu)
TOO_MANY_REQUESTS                  → 429 hoặc challenge thống nhất
IDENTITY_STORE_UNAVAILABLE         → 503 lỗi dịch vụ chung
```

Chỉ những người vận hành được cấp quyền mới xem internal reason qua audit logs có bảo vệ. Không gửi reason qua cookie public, URL query parameter, response header hay các thẻ HTML ẩn rồi hi vọng UI không hiển thị.

## 7. Timing side channel: khi hai câu trả lời giống nhau vẫn tiết lộ user

Giả sử database không có user, service trả về ngay sau `findByUsername`. Nếu có user, server phải chạy một lần kiểm tra password hash (ví dụ BCrypt) khá tốn CPU. Sau đủ mẫu, kẻ tấn công có thể thống kê thời gian phản hồi và đoán username có thật.

```text
Không có user ──────> DB lookup → lỗi chung (nhanh)
Có user, sai pass ──> DB lookup → BCrypt verify → lỗi chung (lâu hơn)
```

Đây là *timing discrepancy* — response body giống nhau nhưng processing path khác nhau.

Biện pháp giảm thiểu:

1. Dùng `PasswordEncoder` phù hợp, có chi phí kiểm tra mật khẩu đáng kể và không lưu plaintext hoặc hash nhanh như SHA-256 không salt cho password.
2. Cân nhắc thực hiện **một phép kiểm tra password hash có chi phí tương đương** cho trường hợp username không tồn tại (ví dụ dummy hash được chuẩn bị trước), trong cơ chế authentication được thiết kế an toàn.
3. Tránh tách branch response, URL, cache và database quá khác biệt cho account có/không tồn tại.
4. Áp dụng throttling/monitoring phù hợp để giảm khả năng thu thập nhiều mẫu phản hồi.
5. Kiểm thử latency theo thống kê trong môi trường tương đương production; **không tuyên bố constant-time chỉ vì dùng BCrypt hoặc ẩn exception**.

Spring Security có xử lý nội bộ cho một số trường hợp username không tồn tại tùy provider/version. **Không tự kết luận framework bảo đảm độ trễ giống nhau hoàn toàn**: database, cache, password encoder, account status, MFA, network và custom code vẫn có thể tạo khác biệt.

**Không khuyến khích “random sleep” như giải pháp duy nhất.** Độ trễ ngẫu nhiên không sửa nhánh xử lý khác nhau và có thể gây tiêu tốn tài nguyên khi bị tấn công. Giải pháp kết hợp bao gồm mã hóa mật khẩu đúng, xử lý đường xác thực hợp lý, hạn chế lưu lượng và quan sát.

## 8. Lockout và rate limiting: chống đoán mật khẩu mà không tạo lộ thông tin mới

### Các loại giới hạn

- Theo **tài khoản/định danh mục tiêu**: giảm brute force dồn vào một username, nhưng có thể tạo cơ hội *account lockout DoS* nếu ai cũng có thể khóa tài khoản người khác.
- Theo **IP/subnet/ASN**: giảm lưu lượng lớn nhưng có thể phạt nhầm nhiều người cùng NAT/VPN; kẻ tấn công có thể phân tán IP.
- Theo **thiết bị/session/challenge**: thêm tín hiệu phòng vệ nhưng cookie/device ID tự báo không đáng tin tuyệt đối.
- Theo **tỷ lệ tổng thể/global**, hành vi/điểm rủi ro: phát hiện password spraying/credential stuffing qua nhiều usernames.
- **Backoff/challenge/MFA:** yêu cầu bước xác minh hoặc tăng độ trễ ở mức chấp nhận được, dựa trên đánh giá rủi ro.

Không có một ngưỡng cố định phù hợp mọi hệ thống. Chọn chính sách theo tải bình thường, độ nhạy cảm tài khoản, khả năng bot phân tán, yêu cầu UX và hỗ trợ người dùng.

### Cẩn thận với account enumeration qua lockout

Ví dụ nguy hiểm:

```text
username="alice"      → HTTP 429 "Account locked"
username="made-up"    → HTTP 302 "/login?error"
```

Nếu chỉ tên có thật dẫn tới 429 khác biệt, rate-limit logic **chính là kênh enumeration mới**. Cần thiết kế tập khóa/thời gian phản hồi/biểu hiện công khai giảm chênh lệch; không để client chưa xác thực đọc được trạng thái lockout của account.

**Account lockout DoS:** nếu khóa cứng user sau 3 lần sai bất kỳ ai cũng tạo được, kẻ tấn công có thể khiến hàng loạt user không vào hệ thống. Nên cân nhắc rate limit mềm, challenge tăng dần, cơ chế mở khóa an toàn và policy dựa trên nhiều tín hiệu. Việc gửi thông báo cho **kênh đã được xác minh** của chủ tài khoản có thể hữu ích, nhưng không nên dùng response HTTP public để xác nhận username.

### HTTP 429 và Retry-After

Một API có rate limiting có thể trả `429 Too Many Requests`, đôi khi kèm `Retry-After`. Hãy bảo đảm status/thời hạn công khai không khác biệt có hệ thống giữa account có thật và không tồn tại trong những tình huống tương đương. `Retry-After` không được chứa identifier hoặc trạng thái nội bộ nhạy cảm. Spring Security **không tự cung cấp giải pháp chống bot hoàn chỉnh** chỉ vì bạn bật `formLogin`.

## 9. Password reset, đăng ký và MFA cũng có thể tiết lộ tài khoản

Nếu form login an toàn nhưng chức năng `/forgot-password` trả “Email này chưa đăng ký”, attacker vẫn có thể enumerate tài khoản qua luồng khác.

### Khôi phục mật khẩu

**Phản hồi nên theo cùng một lời hứa có điều kiện:**

> Nếu địa chỉ phù hợp với một tài khoản trong hệ thống, chúng tôi sẽ gửi hướng dẫn khôi phục theo chính sách bảo mật.

Tránh trả:

```text
"Email không tồn tại" / "Đã gửi email"   // khác nhau theo existence
```

Quy trình khôi phục phải có token ngẫu nhiên, hết hạn ngắn, dùng một lần, không tiết lộ token trong logs, có rate limit phù hợp và kiểm tra thuộc tính bảo mật tài khoản. Với account chưa tồn tại, tránh khác biệt về thời gian phản hồi do chỉ thực hiện email workflow ở một nhánh; có thể dùng async job nhưng vẫn phải xem timing và observable effects.

### Đăng ký tài khoản

“Email đã được sử dụng” có thể tiết lộ danh tính. Nhiều ứng dụng phải cân bằng UX và chống enumeration tùy sản phẩm; với hệ thống yêu cầu quyền riêng tư cao, cung cấp cùng một thông báo chung và gửi hướng dẫn qua kênh email đã xác minh là lựa chọn đáng cân nhắc.

### MFA và nhiều bước đăng nhập

Luồng username-first hoặc xác thực bước đầu có thể bật kênh enumeration nếu chỉ user thật nhìn thấy bước tiếp theo. Đừng hiển thị số điện thoại bị che, email khôi phục, loại MFA, membership hoặc quyền role cho người chưa qua bước xác thực thích hợp. Sau khi đã xác minh một yếu tố tin cậy, có thể cung cấp UX rõ hơn dựa trên đánh giá rủi ro; tách **mức độ tin cậy của người gọi** khỏi việc client chỉ gõ đúng tên.

### OAuth2/OIDC

Nếu ứng dụng chuyển login cho Identity Provider, một phần phản hồi thất bại, account state và recovery sẽ nằm ở **IdP**, không phải Spring form login. Cần thống nhất chính sách disclosure ở RP/client, IdP và API. Không tự in toàn bộ OAuth2 exception, `state`, authorization code hoặc token lên trang lỗi.

## 10. Ví dụ runnable Java 17: form login thất bại có phản hồi thống nhất

Ứng dụng mẫu dùng **Java 17+**, **Spring Boot 3.5.12**, **Spring Security 6.x**, **Gradle 8.4+**, Spring MVC và `BCryptPasswordEncoder`.

Kịch bản:

- `alice`: tài khoản hợp lệ, active, role `USER`, mật khẩu demo `DemoPass123!`.
- `disabled`: tài khoản có thật nhưng `disabled(true)`; có cùng password demo để kiểm tra thông báo công khai không lộ trạng thái.
- `ghost`: username không có trong `InMemoryUserDetailsManager`.
- `GET /public`: endpoint công khai.
- `GET /account`: endpoint yêu cầu đăng nhập.
- `POST /login`: Spring Security xử lý form credentials và CSRF, không viết controller login riêng.
- **Cả ba** trường hợp *sai password / username không tồn tại / disabled* sẽ đi tới `/login?error`.
- `GET /login?error`: trang đăng nhập mặc định thông báo chung; không trả exception internal ra public.

Dự án này phục vụ minh họa **response consistency của form login**. Chưa có rate limiter, IdP, email recovery hoặc timing-mitigation production-grade; phần kiến trúc thực tế đã phân tích bên trên.

### 10.1. Cấu trúc tệp

```text
login-failure-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/loginfailure/
    │   ├── LoginFailureApplication.java
    │   ├── SecurityConfiguration.java
    │   └── AccountController.java
    └── test/java/com/example/loginfailure/
        └── LoginFailureSecurityTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'login-failure-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Bản Spring Boot 3.5 dùng Java 17+ và hỗ trợ Gradle 8.x tương thích (từ 8.4 trở lên theo tài liệu 3.5); nếu dùng Gradle 9 hoặc Boot 4, phải kiểm tra lại yêu cầu tương thích của version đó. Lệnh `javac`/`java` trần không có classpath Spring sẽ không biên dịch được ứng dụng; dùng Gradle như hướng dẫn ở mục 10.5.

### 10.2. Main

**`src/main/java/com/example/loginfailure/LoginFailureApplication.java`**

```java
package com.example.loginfailure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginFailureApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFailureApplication.class, args);
    }
}
```

### 10.3. SecurityConfiguration: URL thất bại là một contract chung

**`src/main/java/com/example/loginfailure/SecurityConfiguration.java`**

```java
package com.example.loginfailure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/account").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/account", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout.permitAll())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("DemoPass123!"))
            .roles("USER")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("DemoPass123!"))
            .roles("USER")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(alice, disabled);
    }
}
```

**Giải thích từng quyết định:**

1. `formLogin` kích hoạt login page/filter tiêu chuẩn; không tạo controller `POST /login` nên tránh trùng handler.
2. `failureUrl("/login?error")` đưa các loại `AuthenticationException` của form login về cùng đường dẫn công khai. Nó không gắn nội dung exception/username vào URL.
3. `defaultSuccessUrl("/account", true)` chỉ dành cho bài demo để success redirect có đích cố định dễ test. Không dùng đường thành công để suy luận lỗi; một lần login thất bại không được đưa vào `/account`.
4. `permitAll()` trên form login cấp quyền tới các endpoint phục vụ login/failure page, không đồng nghĩa cấp quyền đọc `/account`.
5. `anyRequest().denyAll()` chặn endpoint chưa được phân loại. Nếu bạn thêm actuator, static assets hay API khác, hãy cập nhật danh sách công khai/bảo vệ theo nhu cầu, không dùng `/**.permitAll()`.
6. `BCryptPasswordEncoder` băm password demo ngay khi khởi tạo user store. Khác với `{noop}`, password không nằm dưới dạng rõ bên trong `UserDetails`, nhưng source code bài tập vẫn có password ví dụ; **không triển khai tài khoản demo lên production**.
7. `.disabled(true)` cung cấp account có thật nhưng không được đăng nhập; test xác minh phản hồi public không tiết lộ account state.
8. **Không tắt CSRF**: helper form login của Spring Security Test sẽ gửi CSRF token hợp lệ; POST không có token phải bị chặn ở CSRF filter, trước khi xác thực.
9. Lưu ý khi chuyển sang production: cần bảo vệ password reset, multi-factor, khóa tài khoản, HTTPS, session cookie và rate limits; cấu hình trên là mô hình dạy học, không phải bộ phòng thủ hoàn chỉnh.

### 10.4. Controller: không để handler lộ thông tin user tồn tại

**`src/main/java/com/example/loginfailure/AccountController.java`**

```java
package com.example.loginfailure;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "welcome " + principal.getName();
    }
}
```

`/account` chỉ dùng `Principal` khi security đã xác thực thành công, trả `welcome alice` cho account demo. Endpoint này không có `/users/exists` hay `/users/{username}/status` cho người chưa xác thực vì chúng có thể tạo kênh enumeration.

### 10.5. Chạy ứng dụng và thử bằng browser

Máy cần **JDK 17+**, **Gradle 8.4+** tương thích. Tại thư mục `login-failure-demo`:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper tương thích, dùng `./gradlew test` / `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat test` / `gradlew.bat bootRun` (Windows).

Trình tự:

1. Mở `http://localhost:8080/public`. Kết quả **200**, body `public`.
2. Mở `http://localhost:8080/account` khi chưa login. Trình duyệt thường được chuyển tới `/login`.
3. Nhập `alice` với password sai bất kỳ. POST /login có CSRF token, nên phản hồi **302 Location: /login?error**; browser hiển thị trang login với thông báo lỗi chung.
4. Nhập `ghost` với mật khẩu bất kỳ. Client vẫn thấy **cùng URL lỗi** và trang login chung; không có thông báo “username không tồn tại”.
5. Nhập `disabled` với `DemoPass123!`. Tài khoản bị disable không được đăng nhập và client vẫn được đưa về **`/login?error`**.
6. Nhập `alice` / `DemoPass123!`. Login thành công chuyển tới `/account`; body sau GET là `welcome alice`.
7. Với DevTools Network, so sánh HTTP method/status/Location/body/headers cho ba loại thất bại. Chỉ vì UI giống nhau **không kết luận đã loại bỏ toàn bộ timing khác biệt**; có thể cần thêm đo kiểm production.

### 10.6. Vì sao không dùng curl -d username/password đơn giản?

Ứng dụng giữ CSRF mặc định; POST /login thiếu CSRF token phù hợp thường nhận **403** và không vào luồng kiểm tra password. Ví dụ này không hợp lệ để khẳng định account đã bị từ chối bởi password:

```bash
curl -i -X POST http://localhost:8080/login \
  -d 'username=alice&password=wrong'
```

Dòng trên có thể trả 403 vì thiếu CSRF. Để test form login với curl chuẩn, bạn phải lấy cookie/CSRF token từ GET /login, giữ cookie jar và gửi token đúng cách, hoặc sử dụng `MockMvc` như phần tiếp theo. **Không tắt CSRF chỉ để làm request thử đăng nhập trông thuận tiện.**

Với ứng dụng thật, đảm bảo HTTPS khi gửi credentials; HTTP localhost ở ví dụ này chỉ cho môi trường học tập cục bộ.

### 10.7. Test MockMvc: failure response giống nhau, không sai lý do

**`src/test/java/com/example/loginfailure/LoginFailureSecurityTests.java`**

```java
package com.example.loginfailure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFailureSecurityTests {

    @Autowired
    MockMvc mvc;

    private MvcResult failedLogin(String username, String password)
            throws Exception {
        return mvc.perform(formLogin().user(username).password(password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andReturn();
    }

    @Test
    void anonymousCanSeeLoginPage() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }

    @Test
    void protectedPageRedirectsAnonymousToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void wrongPasswordAndUnknownUsernameHaveSamePublicResponse()
            throws Exception {
        MvcResult wrongPassword = failedLogin("alice", "incorrect");
        MvcResult unknownUsername = failedLogin("ghost", "incorrect");

        assertEquals(
            wrongPassword.getResponse().getStatus(),
            unknownUsername.getResponse().getStatus()
        );
        assertEquals(
            wrongPassword.getResponse().getHeader("Location"),
            unknownUsername.getResponse().getHeader("Location")
        );
    }

    @Test
    void disabledAccountGetsSameFailureRedirect() throws Exception {
        MvcResult disabled = failedLogin("disabled", "DemoPass123!");
        MvcResult wrong = failedLogin("alice", "incorrect");

        assertEquals(
            wrong.getResponse().getHeader("Location"),
            disabled.getResponse().getHeader("Location")
        );
    }

    @Test
    void failedLoginPageCanBeRenderedWithoutInternalReason()
            throws Exception {
        mvc.perform(get("/login").param("error", ""))
            .andExpect(status().isOk());
    }

    @Test
    void missingCsrfIsNotAUsernameOrPasswordFailure()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "DemoPass123!"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCredentialsCreateUsableAuthenticatedSession()
            throws Exception {
        MvcResult success = mvc.perform(
                formLogin().user("alice").password("DemoPass123!")
            )
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) success.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("welcome alice"));
    }
}
```

**Các điểm test thể hiện:**

- `formLogin()` từ `spring-security-test` gửi POST login với **CSRF token hợp lệ**; do đó test kiểm tra đúng nhánh authentication failure, không bị 403 trước khi thử password.
- `wrongPasswordAndUnknownUsernameHaveSamePublicResponse` so sánh status và `Location`; `disabledAccountGetsSameFailureRedirect` so thêm tài khoản disabled.
- `missingCsrfIsNotAUsernameOrPasswordFailure` chứng minh lỗi CSRF dẫn tới 403 và không nên bị ghi nhận là password sai.
- `validCredentialsCreateUsableAuthenticatedSession` chứng minh success tạo session xác thực có thể sử dụng cho request `/account` kế tiếp.
- Test **không chứng minh constant-time** vì `MockMvc` không phải môi trường đo thống kê độ trễ production. Bộ test cũng chưa thay thế rate-limiter security tests, XSS/cookie tests, recovery/MFA tests.

### 10.8. Một điều chỉnh test nếu entry point/redirect khác

Trong Spring Security Servlet, `GET /account` chưa đăng nhập thường trả redirect tới trang login (có thể là URL đầy đủ như `http://localhost/login` trong `MockHttpServletResponse`). Với custom entry point/host/proxy/context path, giá trị `Location` có thể khác; khi test app khác, nên kiểm tra matcher redirect một cách có chủ đích thay vì gắn cứng URL sai. Ví dụ `redirectedUrl("http://localhost/login")` dựa trên hành vi redirect mặc định trong môi trường MockMvc; khi dùng phiên bản/chiến lược redirect khác, giữ test ý nghĩa “đưa tới trang login” chứ không thay đổi production policy để làm test pass.

## 11. Khi cần JSON thay vì redirect: AuthenticationFailureHandler riêng

Ứng dụng browser form dùng redirect hợp lý. Nhưng API login dùng JSON có thể cần response **401 + JSON ổn định**, thay vì 302 sang HTML:

```json
{"error":"invalid_credentials"}
```

Một **fragment tùy chọn**, tách khỏi demo runnable ở mục 10:

```java
.formLogin(form -> form
    .failureHandler((request, response, exception) -> {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.getWriter().write(
            "{\"error\":\"invalid_credentials\"}"
        );
    })
)
```

Đây **không phải một REST/JWT login API hoàn chỉnh** và không nên ghép đè vào `SecurityConfiguration.java` mẫu mà không cập nhật tests. Fragment chỉ diễn tả cách chuẩn hóa **public failure response**. Không dùng `exception.getMessage()`, `exception.getClass().getSimpleName()` hoặc `request.getParameter("username")` trong JSON trả về.

Với API, nên cân nhắc cơ chế login/OAuth2/OIDC theo kiến trúc thật, response Content-Type nhất quán, chính sách CSRF nếu credentials được browser tự gửi, rate limit, no-store và cách client xử lý UX. Nếu endpoint login JSON cần khác biệt với browser form, nên xác định rõ `SecurityFilterChain`, matcher và entry point phù hợp thay vì dùng một handler ngẫu nhiên cho mọi request.

**HTTP Basic không giống POST form login:** API dùng `httpBasic()` thường phản hồi authentication failure qua `AuthenticationEntryPoint`/`WWW-Authenticate`, không qua `formLogin.failureHandler(...)`. Với bearer access token, `BearerTokenAuthenticationEntryPoint` và OAuth2 Resource Server có các quy tắc token error riêng. Cần test đúng cơ chế thay vì giả định mọi lỗi login đều qua cùng handler.

## 12. Tổ chức audit log mà không lộ bí mật

Thông điệp công khai phải tối thiểu, nhưng hệ thống vận hành vẫn cần đủ dữ kiện để phát hiện tấn công và hỗ trợ người dùng:

- **Event type:** `authentication_failure`, `authentication_success`, `csrf_rejection`, `rate_limit_triggered`.
- **Timestamp, request ID, source metadata đã giới hạn:** giúp liên hệ các sự kiện, không cần log request body.
- **Ngữ cảnh nội bộ vừa đủ:** reason category có thể được phép trong audit log **được bảo vệ**; quản lý thời hạn lưu và phân quyền truy cập log.
- **Tín hiệu chống bot:** tỷ lệ thất bại, nhiều username trên cùng tín hiệu mạng, phân bố thiết bị, IP reputation khi hợp pháp và phù hợp chính sách riêng tư.

**Không log**: password, OTP, access/refresh token, session cookie, raw Authorization header, toàn bộ form body, recovery token hoặc stack trace chứa secrets. Không dùng hash không khóa của email làm “ẩn danh hoàn toàn”, vì không gian email/username dễ bị đoán và hash có thể bị đảo bằng từ điển; nếu cần liên kết sự kiện mà hạn chế PII, dùng cơ chế pseudonymization có quản lý khóa và retention rõ ràng.

Không nên đưa **audit failure reason** từ server xuống response header/client để “tiện debug”. Nhà vận hành có thể truy vấn theo request ID có phân quyền.

### Không phân biệt account bằng monitoring endpoint công khai

Một dashboard/API metrics chưa xác thực trả “failed_password_for_existing_users” hoặc kích thước queue reset-mail theo username có thể tái tạo enumeration, ngay cả khi form login an toàn. Bảo vệ metrics/tracing, giảm chi tiết trong response public và kiểm tra các ứng dụng hỗ trợ như helpdesk/chatbot.

## 13. Checklist kiểm thử phản hồi đăng nhập

Khi review hoặc pentest hợp pháp, xây dựng các nhóm request sau:

| Nhóm | Yêu cầu | Điều cần so |
| --- | --- | --- |
| A | User tồn tại, password sai | status, Location, body, headers, cookies, thời gian |
| B | User không tồn tại, password bất kỳ | so với A |
| C | User disabled/locked, password đúng hoặc sai | so với A/B theo chính sách disclosure |
| D | Missing CSRF token | phân loại 403; không gây attempt password |
| E | User/password đúng | success, session, fixation protection |
| F | Nhiều attempt, nhiều IP/device/usernames | rate limit/challenge không làm lộ existence |
| G | Forgot password/registration/activation | thông báo và side effects không lộ account |
| H | MFA/SSO/IdP error | không lộ trạng thái account khi caller chưa đủ trust |

**Hướng dẫn kiểm thử:**

1. Chỉ thử trên môi trường/các tài khoản được phép, tránh gây khóa tài khoản người dùng thật.
2. So sánh response ở **toàn bộ HTTP lifecycle**: POST và redirect GET; không chỉ DOM.
3. Kiểm tra response khi cookie có/không có, login từng bước, account disabled, role khác nhau, localization và error handler tùy biến.
4. Đo timing có phương pháp, đủ mẫu, cùng điều kiện nhưng không tạo lưu lượng gây hại; loại bỏ nhiễu network/cache hợp lý.
5. Kiểm tra reset/signup/MFA và sau rate limiting, vì các nhánh khác có thể khôi phục kênh enumeration.
6. Kiểm tra logging an toàn và sự hiện diện của các giới hạn chống đoán credentials ở gateway/backend.
7. Ghi nhận rõ *cái gì đã kiểm thử* và *cái gì chưa*: một unit test status/location không chứng minh toàn hệ thống không bị enumerate.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả “Tài khoản không tồn tại” | Lộ account existence | Thông báo chung |
| Trả “Mật khẩu sai” chỉ cho username thật | Dễ enumerate | Chuẩn hóa phản hồi |
| UI cùng thông báo nhưng status/Location khác | Có kênh khác để quan sát | So cả HTTP status/headers/redirect |
| Lấy `exception.getMessage()` đưa lên login page | Lộ nội bộ/account state | Dùng error flag chung, audit reason ở server |
| Tắt `hideUserNotFoundExceptions` rồi công khai exception | Phân biệt unknown user và bad password | Giữ hành vi không phân biệt; review provider |
| User không có thật trả về quá nhanh | Timing oracle | Cân bằng đường xác thực, kiểm thử timing, throttling |
| Chỉ tài khoản có thật mới nhận 429/lockout banner | Tạo enumeration mới | Thiết kế throttling/UX không lộ existence |
| Khóa cứng account ngay sau rất ít lần sai | Kẻ tấn công gây account-lockout DoS | Adaptive limits/challenge + recovery an toàn |
| Gộp 403 CSRF vào thống kê password sai | Sai nguyên nhân, tăng khóa nhầm | Tách CsrfFilter và auth failure |
| Gọi 403 thiếu quyền là login failure | Sai event/UX | Tách authorization với authentication |
| Tắt CSRF để curl POST login dễ hơn | Tăng rủi ro CSRF | Dùng formLogin() test helper/cookie+token |
| Không test account disabled/unknown | Bỏ sót branch lộ | Test ma trận failure cases |
| Log password/token/session | Rò bí mật qua monitoring | Redact, retention, least privilege |
| Trang reset trả “email đã đăng ký” | Lộ qua luồng khác | Phản hồi chung, gửi chi tiết qua kênh kiểm chứng |
| Thay form login redirect bằng JSON nhưng giữ tests cũ | Client/API contract sai | Tách policy, update tests theo mechanism |
| Nghĩ thông báo chung đã đủ chống enumeration | Bỏ qua timing/rate-limit/MFA/IdP | Kiểm thử toàn bộ observable behavior |

## 15. Câu hỏi tự kiểm tra

**1.** Vì sao “Email này không tồn tại” là một phản hồi nguy hiểm khi nhập sai đăng nhập?

**Trả lời:** vì người chưa xác thực có thể xác định email có trong hệ thống, hỗ trợ phishing, password spraying hoặc tấn công theo mục tiêu.

**2.** Spring Security form login mặc định thường làm gì khi credentials sai?

**Trả lời:** `AuthenticationFailureHandler` được gọi và thường redirect tới `/login?error`; trang login hiển thị một thông báo chung, không trả raw internal exception.

**3.** HTTP 302 ở `POST /login` có chứng minh xác thực thành công không?

**Trả lời:** không. Login thành công và thất bại đều có thể redirect; phải kiểm tra `Location` và security context.

**4.** Có nên trả 404 khi username không tồn tại, còn 401 khi password sai không?

**Trả lời:** không, nếu cùng là authentication attempt; status khác biệt tạo account enumeration dù body giống nhau.

**5.** Vì sao POST /login không CSRF token trả 403 không có nghĩa password sai?

**Trả lời:** `CsrfFilter` có thể chặn trước `UsernamePasswordAuthenticationFilter`, nên credentials chưa được thử.

**6.** `hideUserNotFoundExceptions` giải quyết toàn bộ account enumeration chưa?

**Trả lời:** chưa. Nó giảm khác biệt exception type, nhưng timing, body, recovery, lockout và MFA vẫn có thể lộ.

**7.** Nếu tài khoản có thật mới bị rate limit 429, điều gì có thể xảy ra?

**Trả lời:** status và ngưỡng rate limit có thể tiết lộ existence; thiết kế limit cần không tạo khác biệt public như vậy.

**8.** Vì sao khóa account vĩnh viễn sau vài lần sai có thể phản tác dụng?

**Trả lời:** attacker có thể cố ý làm user thật không đăng nhập được; cần chính sách chống đoán có cân nhắc denial-of-service.

**9.** Có cần che lỗi identity store đang down bằng “sai mật khẩu” không?

**Trả lời:** không. Nên fail closed và dùng lỗi dịch vụ chung; điều quan trọng là không lộ stack trace/secrets, cũng không quyết định status theo account existence.

**10.** Vì sao test cùng Location cho unknown username và wrong password không chứng minh chống timing enumeration?

**Trả lời:** nó chỉ kiểm tra một phần HTTP response. Hai nhánh có thể có độ trễ khác nhau, đặc biệt khi một nhánh chạy BCrypt còn nhánh kia không.

**11.** Browser login failure có luôn trả 401 không?

**Trả lời:** không. Form login có thể redirect 302 tới trang lỗi, còn API/HTTP Basic thường dùng 401. Cần xét cơ chế authentication cụ thể.

**12.** Đưa `SPRING_SECURITY_LAST_EXCEPTION.message` lên trang login custom có an toàn không?

**Trả lời:** không nên, vì exception có thể chứa account state hoặc thông tin nội bộ. Render generic message và giữ reason ở audit backend.

**13.** Nếu user quên mật khẩu, có nên thông báo “đã gửi thư” chỉ khi email tồn tại không?

**Trả lời:** với use case cần chống enumeration, không. Dùng thông điệp có điều kiện chung, kiểm tra email và cấp token ở server theo policy.

**14.** Sau khi user đăng nhập thành công nhưng vào endpoint không đủ role và nhận 403, có nên tăng bộ đếm sai password không?

**Trả lời:** không. Đây là authorization failure, không phải một lần nhập sai credentials.

## 16. Kết luận

- Phản hồi đăng nhập thất bại là một phần của **bảo mật danh tính**, không chỉ là UX.
- Giữ **một thông điệp công khai chung** cho unknown username, wrong password và các account state cần che, đồng thời không tiết lộ ở HTTP status, Location, body, headers hoặc cookie.
- Trong Spring Security Servlet, **`AuthenticationFailureHandler`** xử lý form authentication failure; mặc định thường **redirect `/login?error`**. `CsrfFilter` chặn request thiếu token trước giai đoạn kiểm tra mật khẩu.
- `AbstractUserDetailsAuthenticationProvider` thường **ẩn `UsernameNotFoundException`** đằng sau lỗi credentials chung, nhưng không giải quyết toàn bộ timing side channels.
- Kết hợp chống enumeration với **password hash an toàn, throttling có cân nhắc, recovery/MFA không lộ, audit log bảo mật và tests**.
- Đừng vô tình tạo lỗi mới qua **lockout, 429, reset password, account disabled, JWT/IdP** hoặc việc lộ exception message.
- Ví dụ Java/MockMvc chứng minh một phần contract của form login; muốn đánh giá production cần kiểm thử HTTPS, timing, bot controls và tất cả luồng identity liên quan.

### Tài liệu tham khảo

- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — FormLoginConfigurer và failureUrl/failureHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html
- Spring Security — AbstractUserDetailsAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — Testing Form-Based Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Security HTTP error handling: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- OWASP Authentication Cheat Sheet — Authentication Responses and Error Messages: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
