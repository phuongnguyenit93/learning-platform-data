# Yêu cầu đặt lại mật khẩu mà không tiết lộ tài khoản tồn tại

Chức năng **Quên mật khẩu / Forgot Password** có biểu mẫu công khai để người dùng nhập email hoặc tên đăng nhập. Đây cũng là vị trí dễ phát sinh **account enumeration**: kẻ tấn công gửi nhiều địa chỉ rồi đoán tài khoản nào được đăng ký bằng mã HTTP, thông báo, thời gian phản hồi hoặc những dấu hiệu phụ.

Mục tiêu của bước **yêu cầu đặt lại mật khẩu**: **người chưa chứng minh quyền sở hữu tài khoản không thể biết một định danh hợp lệ có tồn tại, bị khóa, dùng SSO hay có quyền khôi phục bằng mật khẩu hay không chỉ qua endpoint công khai**. Hệ thống vẫn có thể gửi hướng dẫn tới kênh liên hệ đã xác minh của tài khoản đủ điều kiện, nhưng không phản ánh kết quả tra cứu hoặc gửi mail ra HTTP response.

Bài học phân biệt chống enumeration với toàn bộ vòng đời reset token, tập trung thiết kế phản hồi đồng nhất, tránh timing side-channel, xử lý nội bộ bất đồng bộ, rate limiting, Spring Security Servlet, mã Java 17+ minh họa và kiểm thử bảo mật.

## 1. Account enumeration xuất hiện như thế nào?

Giả sử client gửi:

~~~http
POST /auth/password-reset-requests HTTP/1.1
Content-Type: application/json

{"identifier":"lan@example.org"}
~~~

Một implementation không an toàn trả:

~~~text
lan@example.org       -> 200 "Đã gửi email đặt lại mật khẩu"
nobody@example.org    -> 404 "Không tìm thấy tài khoản"
locked@example.org    -> 403 "Tài khoản bị khóa"
sso-only@example.org  -> 409 "Tài khoản sử dụng SSO"
~~~

Những thông báo này giúp người lạ đoán được người dùng nào tham gia hệ thống. Kết hợp với danh sách email rò rỉ, attacker có thể nhắm tới phishing, credential stuffing, social engineering hoặc điều tra cấu trúc tổ chức.

Một phản hồi bảo mật hơn:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{"message":"Nếu có tài khoản phù hợp và đủ điều kiện, hướng dẫn sẽ được gửi qua phương thức liên hệ đã đăng ký."}
~~~

Cùng request format hợp lệ, **cùng mã trạng thái, body, schema, headers và redirect behavior**, dù tài khoản có hay không. `202 Accepted` có nghĩa đã **nhận yêu cầu xử lý**, không bảo đảm email được gửi. Dùng `200 OK` với response đồng nhất cũng là lựa chọn hợp lệ.

Thông điệp trung tính không được nói “email đã được gửi” như một thực tế chắc chắn cho mọi input, và không yêu cầu client tự báo một flag như `accountExists`.

## 2. Các kênh có thể làm lộ tài khoản

Không thể chống enumeration chỉ bằng đổi một câu thông báo. Cần xét đầy đủ các kênh quan sát:

| Kênh | Cách làm lộ | Bảo vệ |
| --- | --- | --- |
| HTTP status | Tồn tại trả 200, không tồn tại trả 404 | Cùng status với input hợp lệ |
| Body / JSON | `accountExists`, `mailSent`, nội dung khác nhau | Cùng schema/message, không có flag nội bộ |
| Redirect | User thật được chuyển sang trang khác | Cùng Location và quy tắc điều hướng |
| Header/cookie | Set-Cookie, Retry-After hoặc Cache-Control khác nhau | Đồng nhất envelope HTTP |
| Response length | Thêm masked email với tài khoản tồn tại | Không công bố dữ liệu contact |
| Độ trễ | Có user gửi email đồng bộ, không có user trả ngay | Tách lookup/send khỏi đường HTTP |
| Rate limiting | Chỉ user thật bị throttle theo account | Giới hạn cho cả identifier thật và lạ |
| CAPTCHA | Chỉ xuất hiện nếu email đã đăng ký | Kích hoạt theo mức độ abuse, không theo tồn tại |
| Trang resend/status | Trả biết thư đã gửi hay chưa | Không công khai trạng thái gửi |
| API login/registration | Lỗi khác nhau cho các trạng thái account | Dùng generic errors theo chính sách |
| Side effect | Reset request khóa tài khoản thật | Không đổi account trước khi xác minh token |

Ngay cả khi cả hai response có body giống nhau, nếu tài khoản thật tốn 400 ms để gửi SMTP còn tài khoản lạ trả trong 10 ms, attacker có thể lặp lại nhiều lần và dùng thống kê để phân loại.

**Mục tiêu không phải mọi HTTP request có thời gian bằng tuyệt đối tới từng microsecond.** Mục tiêu là không tồn tại sai khác đáng tin cậy có thể khai thác ở quy mô lớn; phải kiểm thử phân phối latency dưới tải thực.

## 3. Kiến trúc nên dùng: nhận request trước, tra user sau

Luồng dễ bảo vệ là **HTTP intake đồng nhất** rồi **worker nội bộ**:

~~~text
Client / Browser
     |
     | POST identifier
     v
Reset Request Controller
     | Kiểm cú pháp/kích thước
     | Throttle theo input/source, không lookup user
     | Enqueue một reset-intent cho mọi identifier hợp lệ
     v
  202 + generic response
     :
     : Queue xử lý tách biệt
     v
Reset Worker
     | Lookup account trong kho danh tính
     | Không có / không đủ điều kiện -> không gửi
     | Có account đủ điều kiện -> sinh token/TTL
     | Gửi tới recovery address đã được xác minh
     v
Internal audit / metric, không lộ ra public response
~~~

**Tất cả định danh hợp lệ về cú pháp phải đi qua cùng đường xử lý HTTP.** Controller không quyết định gửi email có thành công hay không rồi mới phản hồi. Worker có quyền xem account state nhưng kết quả chỉ phục vụ xử lý nội bộ.

Nếu queue hỏng, hệ thống có thể trả lỗi tạm thời chung như 503 cho mọi request bị ảnh hưởng, không giả vờ request đã được xếp hàng. Phân biệt **queue failure** với **account missing** trong telemetry nội bộ, không trong response.

### Phản ví dụ: cùng text nhưng timing khác

~~~java
// Cách làm sai: tra tài khoản và gửi mail đồng bộ.
var account = users.findByEmail(email);
if (account.isPresent()) {
    mailer.sendResetInstructions(account.get());
}
return "Nếu có tài khoản phù hợp, hướng dẫn sẽ được gửi.";
~~~

Body giống nhau, nhưng nhánh có tài khoản mất thêm thời gian gửi mail. Một cách làm tương tự nhưng gọi `future.join()` để chờ gửi email vẫn có nguy cơ. Giải pháp chính là **không tra cứu account và không chờ SMTP trong request path**.

Thêm một `Thread.sleep(500)` cố định không đủ: email provider đôi khi chậm hơn thời gian sleep, làm lộ khác biệt; sleep còn khiến server dễ bị cạn thread. Padding ngẫu nhiên nếu cần cũng chỉ là biện pháp bổ sung sau khi loại bỏ nhánh xử lý khác nhau.

## 4. Validation về cú pháp không được biến thành account lookup

Có thể từ chối payload không hợp lệ:

- JSON hỏng, thiếu field bắt buộc;
- Identifier trống, quá dài hoặc sai định dạng theo quy tắc được công bố;
- Request vượt payload size limit;
- Abuse được phát hiện theo IP, device/session hoặc tín hiệu khác.

Nhưng **định danh hợp lệ về cú pháp** phải nhận cùng generic response, bất kể nó nằm trong database hay không.

| Input | Đánh giá | HTTP behavior |
| --- | --- | --- |
| `lan@example.org` | Định dạng hợp lệ, account có thể có | Generic 202 |
| `unknown@example.org` | Định dạng hợp lệ, account có thể không có | Generic 202 |
| `disabled@example.org` | Account bị khóa | Generic 202 |
| `sso@example.org` | Account chỉ dùng SSO | Generic 202 |
| JSON thiếu dấu ngoặc | Payload sai cú pháp | Có thể 400 |
| Chuỗi dài hàng MB | Quá giới hạn chung | Có thể 413 hoặc 400 |

Không dùng `404 Not Found` để nói email chưa đăng ký. Không hiển thị một phần email khôi phục đã che (ví dụ `l***@example.org`) trước khi người dùng chứng minh quyền đối với tài khoản.

**Chuẩn hóa định danh** phải nhất quán với kho identity: xử lý Unicode, khoảng trắng và quy ước username/email theo hệ thống. Không tự áp dụng quy tắc Gmail bỏ dấu chấm/đuôi cộng cho mọi nhà cung cấp, vì có thể gộp hai địa chỉ khác nhau thành một tài khoản. Một quy tắc canonicalization sai còn gây lỗi rate limiting hoặc gửi hướng dẫn cho sai user.

## 5. Response HTTP thống nhất và không phản chiếu dữ liệu nhạy cảm

Một contract công khai:

~~~json
{
  "message": "Nếu có tài khoản phù hợp và đủ điều kiện, hướng dẫn sẽ được gửi qua phương thức liên hệ đã đăng ký."
}
~~~

Các trường không nên có trong response unauthenticated:

~~~json
{
  "accountExists": true,
  "accountType": "LOCAL_PASSWORD",
  "maskedEmail": "l***@example.org",
  "resetTokenGenerated": true,
  "mailDeliveryStatus": "QUEUED"
}
~~~

Không nên phản chiếu email nhập vào trong response nếu không cần, nhất là không encode/escape đúng cho HTML gây XSS. Các trường request ID/correlation ID nếu có phải độc lập với kết quả lookup và không mở ra API “kiểm tiến độ email” công khai.

Cần kiểm cả HTTP headers và routing:

- HTTP status giống nhau cho known/unknown/disabled khi cú pháp hợp lệ.
- Content-Type, Cache-Control, Location, Set-Cookie và body schema không khác vì account.
- Không trả endpoint hoặc đường dẫn riêng chỉ cho SSO-only user.
- Không tự động redirect theo domain email hoặc tenant đã được tìm trong database.
- Không cung cấp biến ẩn trong HTML/JavaScript có thông tin existence.
- Không ghi response debug exception stack trace chứa trạng thái account.

Nếu ứng dụng dùng SPA, thông báo hiển thị trên frontend cũng phải thống nhất, kể cả sau retry, navigation hoặc reload.

## 6. Rate limiting: chống cả enumeration lẫn email flooding

Endpoint trả cùng một câu nhưng không giới hạn tần suất vẫn có thể bị lạm dụng để thử hàng triệu email hoặc gửi spam reset tới một nạn nhân.

Có thể giới hạn kết hợp:

| Chiều | Mục đích |
| --- | --- |
| IP / dải mạng | Giảm tự động hóa theo nguồn |
| Normalized identifier | Chống bombardment một hộp thư |
| Session / browser flow | Chặn người dùng/bot submit liên tục |
| Tenant đáng tin cậy | Bảo vệ quota của tổ chức |
| Tổng lưu lượng toàn hệ thống | Không để queue, mail, database quá tải |
| Thư thực sự được gửi | Giới hạn chi phí và email bombing ở worker |

**Quota theo identifier phải áp dụng với cả email tồn tại và không tồn tại.** Nếu email đã đăng ký bị 429 sau vài lần còn email lạ luôn trả 202, chính rate limiter trở thành oracle.

Nếu lưu identifier làm Redis rate-limit key, nên dùng một dạng bảo vệ như **HMAC của identifier đã chuẩn hóa với key phía server**, tránh đưa email plaintext vào hệ thống logs và metrics. Cần thống nhất normalization cho lookup và throttling.

CAPTCHA hoặc progressive challenge có thể kích hoạt dựa trên dấu hiệu automation, không dựa vào account existence. Cũng không dùng request reset để khóa account login: attacker không được quyền làm gián đoạn việc đăng nhập của người khác chỉ bằng nhập email của họ.

**Bài toán availability:** một giới hạn quá chặt theo email có thể cho phép attacker ép nạn nhân không thể tự reset. Cần thiết kế cooldown, chống bot, phương thức hỗ trợ đáng tin cậy, quota và metric theo threat model, không áp dụng một ngưỡng cứng cho mọi dịch vụ.

## 7. Worker chỉ gửi đến địa chỉ recovery đã được xác minh

Trong worker, một luồng nội bộ có thể như sau:

~~~text
consume ResetIntent
  |
  +-- lookup normalized identifier
  |
  +-- account không tồn tại -> kết thúc nội bộ
  |
  +-- account không đủ điều kiện local reset -> kết thúc hoặc xử lý policy riêng
  |
  +-- lấy verifiedRecoveryContact của account
  |
  +-- tạo token ngẫu nhiên, gắn accountId + purpose + TTL
  |
  +-- lưu token verifier, single-use state
  |
  +-- gửi link tới verifiedRecoveryContact qua mail service
  |
  +-- audit nội bộ không lộ ra HTTP response
~~~

Không gửi link reset đến trường `destinationEmail` mà requester tự điền, trừ khi đó chính là địa chỉ đã được liên kết và xác minh với account theo chính sách. Người không được xác thực có thể tự đặt bất kỳ email nào; cho họ chọn địa chỉ nhận token là nguy cơ account takeover.

Các trường hợp đặc biệt:

| Account state | Hành vi worker |
| --- | --- |
| Local-password account + verified email | Có thể phát token và gửi tới verified email |
| Identifier không tồn tại | Không gửi, không công bố |
| Account disabled/locked | Không tự mở khóa; đi theo recovery policy |
| SSO/OIDC/SAML-only | Không tạo local password trái chính sách; có thể có hướng dẫn riêng gửi qua kênh xác minh |
| Không có verified recovery contact | Không gửi token cho contact chưa xác minh |
| Account mời chưa kích hoạt | Không tự kích hoạt account bằng request reset |
| Nhiều account cùng identifier | Không chọn ngẫu nhiên; cần chính sách identity ambiguity |

Dù worker xử lý khác nhau, phản hồi công khai **đã kết thúc** và không tiết lộ nhánh nào được chọn.

Queue là một vùng chứa PII: giới hạn quyền đọc, thời hạn lưu, encryption nếu cần, tránh log identifier/raw token, dùng dead-letter queue được bảo vệ và không để retry spam email vô hạn.

## 8. Java 17+: mô phỏng cùng response cho known/unknown

Chương trình sau mô phỏng HTTP intake và worker trong **một JVM**, dùng một queue nội bộ để chứng minh hai request cùng đường đi. **Không có HTTP server, gửi email hay token thật**; chỉ kiểm semantics “không lookup account trước khi trả generic response”.

Tạo file **ResetRequestDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Queue;
import java.util.Set;

public class ResetRequestDemo {
    private static final String GENERIC =
            "If an account is eligible, reset instructions will be sent.";

    record Intent(String identifier) {}

    private final Queue<Intent> pending = new ArrayDeque<>();
    private final Set<String> accounts =
            new HashSet<>(Set.of("lan@example.org"));

    String requestReset(String identifier) {
        if (identifier == null || identifier.isBlank()) {
            throw new IllegalArgumentException("Invalid input format");
        }
        pending.add(new Intent(identifier));
        return GENERIC;
    }

    void runWorker() {
        while (!pending.isEmpty()) {
            Intent intent = pending.remove();
            if (accounts.contains(intent.identifier())) {
                // Production worker would issue a one-time reset token
                // and send it to the account's verified recovery address.
            }
        }
    }

    int pendingCount() {
        return pending.size();
    }

    public static void main(String[] args) {
        ResetRequestDemo service = new ResetRequestDemo();

        String first = service.requestReset("lan@example.org");
        String second = service.requestReset("unknown@example.org");

        System.out.println("Response A = " + first);
        System.out.println("Response B = " + second);
        System.out.println("Responses equal = " + first.equals(second));
        System.out.println("Queued intents = " + service.pendingCount());

        service.runWorker();
        System.out.println("Queue empty = " + (service.pendingCount() == 0));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ResetRequestDemo.java
java ResetRequestDemo
~~~

Stdout chính xác:

~~~text
Response A = If an account is eligible, reset instructions will be sent.
Response B = If an account is eligible, reset instructions will be sent.
Responses equal = true
Queued intents = 2
Queue empty = true
~~~

Phân tích:

- Request intake không lookup account, chỉ enqueue hai định danh hợp lệ.
- Cùng message được trả cho cả hai.
- Worker tra tồn tại account sau đó; không có thông tin `mailSent` trả ra caller.
- `ArrayDeque` không thread-safe/distributed; **không dùng queue này trong production**.
- Chương trình không chứng minh HTTP latency đồng nhất, CAPTCHA/rate limit, email delivery, token cryptography hay security của Spring. Đây là lab minh họa ranh giới kiến trúc.

## 9. Áp dụng với Spring Security Servlet

Spring Security có filter chain, kiểm authorization, CSRF và `PasswordEncoder`, nhưng ứng dụng phải tự thiết kế forgot-password request, queue, worker, mail và reset token store.

Ví dụ controller Spring Boot Servlet Java 17+:

~~~java
package demo.security.reset;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/auth")
public class PasswordResetRequestController {
    private static final String GENERIC_MESSAGE =
            "Nếu có tài khoản phù hợp và đủ điều kiện, "
            + "hướng dẫn sẽ được gửi qua phương thức liên hệ đã đăng ký.";

    public interface ResetIntake {
        void enqueue(String identifier);
    }

    public record Request(String identifier) {}

    private final ResetIntake intake;

    public PasswordResetRequestController(ResetIntake intake) {
        this.intake = intake;
    }

    @PostMapping("/password-reset-requests")
    public ResponseEntity<Map<String, String>> requestReset(
            @RequestBody Request request) {

        if (request == null || request.identifier() == null
                || request.identifier().isBlank()
                || request.identifier().length() > 254) {
            return ResponseEntity.badRequest().body(
                    Map.of("message", "Dữ liệu yêu cầu không hợp lệ."));
        }

        // Intake chuẩn hóa, kiểm anti-abuse và enqueue theo một đường
        // độc lập với việc identifier có account hay không.
        intake.enqueue(request.identifier());

        return ResponseEntity.accepted().body(
                Map.of("message", GENERIC_MESSAGE));
    }
}
~~~

Đây là class Spring hợp lệ về cấu trúc nhưng **không phải ứng dụng độc lập chạy với javac**. Cần Spring Boot, Spring Web/Security và một bean triển khai `ResetIntake`. Implementation đó phải kiểm input/canonicalization, throttle độc lập existence, enqueue thật theo cùng đường và fail closed khi queue lỗi. Không triển khai `ResetIntake` bằng một lời gọi đồng bộ đến `findByEmail()` rồi gửi SMTP, vì điều đó quay lại timing oracle.

Đoạn cấu hình HTTP authorization:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                org.springframework.http.HttpMethod.POST,
                "/auth/password-reset-requests").permitAll()
        .anyRequest().authenticated());
~~~

Đây là **mảnh DSL bên trong SecurityFilterChain**. `permitAll()` chỉ có nghĩa không yêu cầu người gọi phải đăng nhập; nó **không tắt CSRF hoặc abuse protection**. Với form browser dùng session/cookie, hãy cung cấp CSRF token theo Spring Security. Nếu thiết kế reset API không dựa session, đánh giá CSRF/cross-origin và chống mail bombing theo threat model; không vô hiệu hóa CSRF toàn ứng dụng một cách tùy tiện.

**Lưu ý 400:** ví dụ trả 400 cho input trống/length >254, không phải vì account không tồn tại. Nếu login identifier có thể là username chứ không phải email, áp dụng giới hạn và validation phù hợp với policy thực tế.

## 10. Token reset là credential có mục đích hẹp

Một request response generic chưa đủ bảo mật nếu link reset có thể đoán hoặc dùng nhiều lần. Sau khi worker tìm được account đủ điều kiện, token phải:

1. Sinh từ CSPRNG (ví dụ 32 byte ngẫu nhiên).
2. Gắn với **userId**, mục đích `PASSWORD_RESET` và thời điểm hết hạn.
3. Lưu dạng verifier an toàn, ví dụ SHA-256 digest/HMAC của token entropy cao.
4. **Single-use**, được consume atomically để tránh race/replay.
5. Có TTL do server enforce (ví dụ 20 phút chỉ là chính sách minh họa).
6. Bị giới hạn brute force và có cơ chế thu hồi khi cần.
7. Không tự tạo login session hoặc thay password khi mới phát hành token.

Ví dụ bảng dữ liệu PostgreSQL minh họa:

~~~sql
CREATE TABLE password_reset_token (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    token_digest BYTEA NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
~~~

Khi người dùng nộp token để đặt mật khẩu mới, kiểm digest, expiry, chưa dùng, account policy và password policy; đánh dấu consumed và cập nhật password hash trong giao dịch nhất quán. Hai requests đồng thời không được cùng thành công với một token.

Generator Java (mảnh tiện ích, chưa có lưu trữ):

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class ResetTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String create() {
        byte[] raw = new byte[32];
        RANDOM.nextBytes(raw);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);
    }
}
~~~

Một token 32-byte ngẫu nhiên được base64url không padding có 43 ký tự. Không log raw token; không đưa vào monitoring hay exception.

**PasswordEncoder khác token hashing:** password do con người chọn thường có entropy thấp nên cần bộ hash chậm có salt/cost phù hợp (ví dụ thuật toán qua `DelegatingPasswordEncoder`). Token reset ngẫu nhiên 256-bit có thể lưu verifier bằng digest mật mã nhanh được kiểm soát. Không lưu password plaintext.

## 11. Link khôi phục: tránh Host Header Injection và rò token

Đừng tạo link bằng host do request công khai cung cấp:

~~~java
// Sai: attacker có thể thao túng header Host.
String link = "https://" + request.getHeader("Host")
        + "/reset-password?token=" + token;
~~~

Nếu attacker điều khiển Host header, email recovery của account thật có thể dẫn người dùng tới trang do attacker kiểm soát và làm lộ token. Thay vào đó dùng **public base URL cấu hình tin cậy**, chẳng hạn `https://accounts.example.org`, được phê duyệt cho môi trường triển khai.

Các biện pháp liên quan:

- Reset page chỉ qua HTTPS;
- Đặt `Referrer-Policy: no-referrer` cho trang chứa token;
- Không tải analytics/third-party scripts có thể đọc token;
- Cấu hình reverse proxy/access logs không ghi query token;
- Không cho requester cung cấp callback/redirect URL tùy ý;
- Chỉ gửi tới verified recovery contact của account;
- Có thể sau khi xác minh token chuyển sang một recovery session hạn chế để tránh giữ token trong URL.

**Không đổi password ở bước GET vào link**. GET nên hiển thị form hoặc mở flow xác minh; thay đổi password chỉ diễn ra sau hành động có kiểm tra token và password mới.

Sau khi đổi password thành công, theo policy có thể thu hồi session/refresh tokens cũ, gửi thông báo bảo mật, yêu cầu login lại. **Không tự động login chỉ vì token reset vừa được dùng**; token chỉ có mục đích cập nhật mật khẩu.

## 12. Trạng thái tài khoản đặc biệt

| Trạng thái | Worker cần làm | Public response |
| --- | --- | --- |
| Account local password và recovery contact verified | Có thể gửi link | Generic 202 |
| Không có account | Không gửi | Generic 202 |
| Account locked/disabled | Không tự mở khóa; áp dụng recovery policy | Generic 202 |
| SSO/OIDC/SAML-only | Không tự tạo mật khẩu local; hướng dẫn nội bộ nếu cần | Generic 202 |
| Recovery email chưa verified | Không gửi link tới email chưa xác minh | Generic 202 |
| Account chưa kích hoạt | Không tự kích hoạt chỉ vì request | Generic 202 |
| Username/email không duy nhất | Không tự chọn account bất kỳ | Generic 202 |

Không khóa tài khoản do một người không xác thực gửi request reset. Không dựa vào input để quyết định tài khoản nào nhận thư nếu có nhiều bản ghi trùng identifier.

Người sở hữu tài khoản có thể cần được thông báo về reset thành công hoặc hành động recovery theo chính sách, nhưng thông báo đó thuộc kênh riêng đã xác minh, không phải kết quả public của request.

## 13. Các điểm rò rỉ gián tiếp thường bị bỏ qua

Một hệ thống có endpoint forgot password trả generic vẫn có thể lộ qua:

- Trang đăng ký trả “email đã tồn tại”;
- Login trả “không tồn tại user” khác “sai mật khẩu”;
- Endpoint gửi lại email trả “không có reset đang chờ”;
- Trang “kiểm trạng thái đặt lại mật khẩu” công khai;
- CAPTCHA chỉ bật với tài khoản có thật;
- Rate limit per-account chỉ lưu cho user có thật;
- Header Retry-After, response size hoặc cookie khác nhau;
- Thư rác/bounce phản ánh vào HTTP response đồng bộ;
- Log/tracing/debug output lộ `foundUser=true`;
- Tên file hoặc URL redirect phân nhánh theo identity provider.

Cần audit **toàn bộ vòng đời xác thực/đăng ký/khôi phục**, không chỉ một route.

## 14. Kiểm thử: status, body, timing và side effects

| Test case | Kết quả mong đợi |
| --- | --- |
| Email thật hợp lệ | 202 generic |
| Email không tồn tại nhưng format đúng | Cùng status/body/headers |
| Account disabled/locked | Cùng response, không tự mở khóa |
| SSO-only account | Cùng response, không tự tạo local password |
| Email recovery chưa verified | Cùng response, không gửi link đến contact chưa xác minh |
| JSON không hợp lệ hoặc payload quá dài | Lỗi format chung, không phụ thuộc account |
| Rate-limit cùng identifier thật/lạ | Cùng quy tắc throttling |
| SMTP provider chậm | Không làm known-account response chậm riêng |
| Queue hỏng | Lỗi hạ tầng generic, không có account oracle |
| 100 requests cùng email | Không gửi 100 email vô hạn; có quota/dedup |
| Request reset | Không tự đổi password/session/account status |
| Token sai, hết hạn hoặc đã dùng | Không cho đổi password |
| Hai requests cùng dùng token | Một lần consume thành công |
| Host header độc hại | Link vẫn dùng trusted base URL |
| Token trong query/referrer/log | Được ngăn hoặc redacted |
| Resend/status API | Không tiết lộ account existence |
| Phân phối latency known/unknown | Không có oracle đáng tin cậy qua thống kê |

### MockMvc: so sánh hai trường hợp

Mảnh test Spring Boot Servlet có `MockMvc` và stub `ResetIntake`:

~~~java
var a = mockMvc.perform(post("/auth/password-reset-requests")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"identifier\":\"lan@example.org\"}")
        .with(csrf()))
        .andReturn().getResponse();

var b = mockMvc.perform(post("/auth/password-reset-requests")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"identifier\":\"unknown@example.org\"}")
        .with(csrf()))
        .andReturn().getResponse();

assertEquals(202, a.getStatus());
assertEquals(a.getStatus(), b.getStatus());
assertEquals(a.getContentAsString(), b.getContentAsString());
~~~

Đây là **mảnh test**, không tự chạy với javac; cần setup MockMvc và static imports JUnit/Spring Security test. Một test đầy đủ còn so sánh headers, xác minh worker queue đã nhận cả hai intents, và kiểm không có lookup account trong HTTP request thread.

Để đo timing, dùng nhiều requests xen kẽ known/unknown/disabled, warm-up JIT và cache, ghi latency histogram/median/p95 dưới nhiều mức tải, kể cả khi SMTP/queue chậm. Không suy luận chỉ từ một vài lần gửi request thủ công.

## 15. Checklist trước triển khai

1. Response của account tồn tại, không tồn tại, locked và SSO-only có **cùng status/body/headers/redirect** không?
2. HTTP intake có tránh lookup account và gửi SMTP đồng bộ không?
3. Mọi identifier hợp lệ có vào cùng queue/pipeline trước khi worker quyết định gửi mail?
4. Có throttling theo IP và normalized identifier cho **cả known và unknown** không?
5. Có tránh CAPTCHA, Retry-After hoặc error khác chỉ vì account tồn tại không?
6. Có bảo vệ queue/PII, worker retry, quota và lỗi hạ tầng không?
7. Chỉ gửi link tới contact đã được account xác minh, không theo destination do người lạ cung cấp?
8. Reset token có random entropy, TTL, single-use, account/purpose binding và rate limit?
9. Reset URL có trusted base host, HTTPS, no-referrer và redaction token?
10. Chỉ đổi password/session sau khi token và policy được xác minh?
11. Có dùng PasswordEncoder phù hợp và thông báo bảo mật sau completion?
12. Có test latency, response envelope, các endpoints liên quan và tình huống abuso/DoS?

**Kết luận:** “Không tiết lộ tài khoản tồn tại” phải là một tính chất của **toàn bộ luồng yêu cầu reset**, không chỉ câu thông báo. Phản hồi công khai phải trung tính; tra cứu user, phát token và gửi mail diễn ra ở worker nội bộ. Kết hợp đường xử lý đồng nhất, chống timing side-channel, rate limit và token an toàn mới hạn chế được việc attacker xác định tài khoản nào đang sử dụng dịch vụ.

### Tài liệu tham khảo

- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Spring Security — Password Storage / PasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — CSRF Protection (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- NIST SP 800-63B-4 — Account Recovery: https://pages.nist.gov/800-63-4/sp800-63b.html
