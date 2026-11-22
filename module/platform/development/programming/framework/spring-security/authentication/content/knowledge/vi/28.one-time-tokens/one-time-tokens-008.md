# Chống dò tài khoản, giới hạn yêu cầu gửi và bảo vệ token khỏi log, lịch sử trình duyệt

## 1. Phạm vi và lý do phải bảo vệ toàn bộ vòng đời của token dùng một lần

**Token dùng một lần** (*one-time token*) thường xuất hiện trong các chức năng: đặt lại mật khẩu, xác minh email, chấp nhận lời mời, xác nhận thao tác nhạy cảm hoặc đăng nhập qua đường dẫn (*magic link*). Một token hợp lệ có thể trao cho người sở hữu nó quyền thực hiện **một hành động có thời hạn** mà không cần biết mật khẩu cũ. Vì vậy, dù chỉ tồn tại vài phút, token vẫn là **bí mật có giá trị như một credential**.

Một luồng khôi phục tài khoản có thể bị tấn công **ngay cả khi token được tạo bằng thuật toán mật mã tốt**, vì ba nhóm lỗi khác nhau:

1. **Dò tài khoản (*account enumeration*):** endpoint “quên mật khẩu” trả lời khác nhau khi email tồn tại, hoặc có khác biệt đo được qua mã HTTP, kích thước, redirect, timing, rate-limit, thông báo lỗi. Kẻ tấn công xây được danh sách tài khoản thực.
2. **Lạm dụng yêu cầu gửi (*message flooding/abuse*):** attacker gửi hàng nghìn yêu cầu tới một email/số điện thoại, gây spam, tốn chi phí SMS, chiếm quota dịch vụ, làm gián đoạn trải nghiệm hoặc lợi dụng resend để vô hiệu hóa token hợp lệ của người dùng.
3. **Rò rỉ token qua đường vận hành và trình duyệt:** token đặt trong query string có thể được ghi trong reverse-proxy access log, APM, lỗi ứng dụng, analytics, lịch sử trình duyệt, Referer hoặc công cụ hỗ trợ. Một token còn hạn và chưa được sử dụng có thể bị chiếm đoạt.

Các biện pháp phải được thiết kế **xuyên suốt** từ lúc nhận yêu cầu đến lúc gửi, mở liên kết, hoàn tất hành động, thu hồi token và audit. Việc thêm một CAPTCHA hay đặt TTL 15 phút **không đủ** để thay thế các ranh giới bảo vệ còn lại.

### Mô hình tham chiếu

~~~text
[Anonymous client]
        |
        | POST /account/recovery/request { email }
        v
[Gateway / abuse control]
  - rate limit theo IP, identifier, tenant, global
  - chống request flood, không tin IP header giả
        |
        v
[Application request service]
  - chuẩn hóa identifier nhất quán
  - KHÔNG tiết lộ account có tồn tại
  - tìm user, kiểm tra policy
  - chỉ gửi nếu đủ điều kiện
  - trả phản hồi công khai đồng nhất
        |
        v
[Token issuer / DB / queue]
  - CSPRNG, secret đủ entropy
  - lưu hash/HMAC + purpose + userId + expiry
  - enqueue email/SMS có kiểm soát
        |
        v
[Recipient]
  - nhận link/code qua kênh phụ
  - mở trang sạch, không có third-party tracking
  - chỉ sử dụng token khi người dùng xác nhận qua POST
        |
        v
[Atomic token consume + business action]
  - kiểm tra purpose, expiry, used/revoked
  - đúng user và quyền của action
  - đánh dấu đã dùng trong transaction
  - hoàn tất thay đổi / tạo phiên giới hạn
  - chuyển hướng sang URL không chứa token
~~~

Ba câu hỏi bắt buộc: **Ai được phép yêu cầu gửi? Token có thể lộ ở đâu? Làm sao bảo đảm đúng một request thực sự sử dụng được token?**

## 2. Hiểu đúng account enumeration

Dò tài khoản là việc quan sát response/side effect để biết identifier do attacker thử có thuộc một tài khoản thật hay không. Kẻ tấn công thường không cần biết mật khẩu; danh sách email hợp lệ có thể hỗ trợ spear phishing, password spraying, credential stuffing hoặc thu thập thông tin khách hàng.

Ví dụ **không nên thiết kế**:

~~~http
POST /account/recovery/request
Content-Type: application/json

{"email":"lan@example.test"}
~~~

~~~json
{"exists": true, "message": "Đã gửi liên kết tới tài khoản này"}
~~~

Với email không tồn tại, server trả `404 {"exists":false}`. Bằng cách thử danh sách email, người ngoài xác định account chính xác. Cũng có thể dò khi **cả hai đều trả `200`** nhưng có khác biệt ở body, `Location`, header, thời gian xử lý hoặc trạng thái cooldown.

### Phản hồi công khai nên thế nào?

Với identifier có cú pháp hợp lệ, trả cùng một phản hồi **bất kể email tồn tại hay không**:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{"message":"Nếu thông tin khớp với tài khoản đủ điều kiện, chúng tôi sẽ gửi hướng dẫn."}
~~~

Thành phần quan trọng là **cùng mã HTTP, cùng cấu trúc và nội dung công khai, cùng chính sách redirect/cooldown** trong các trường hợp tài khoản tồn tại, không tồn tại, bị khóa hoặc chưa đủ điều kiện, trừ khi có lý do bảo mật cụ thể và threat model chấp nhận được. Không trả `accountExists`, `hasMfa`, `emailVerified`, `userStatus` hay `maskedEmail` chỉ ở nhánh account có thật.

**`202 Accepted` không có nghĩa email chắc chắn đã được gửi.** Nó phản ánh việc server đã nhận yêu cầu xử lý theo chính sách. Với account không tồn tại, hệ thống không tạo token hay gửi email nhưng vẫn đưa thông điệp công khai giống nhau.

Có thể báo lỗi cú pháp input (ví dụ email không có `@`) theo cùng quy tắc cho **mọi identifier có cùng lỗi cú pháp**; khác biệt này không phải tự thân là dò sự tồn tại. Nhưng sau khi input hợp lệ, không để kết quả lookup account lộ ra response.

### Các kênh rò rỉ ngoài JSON

| Kênh quan sát | Ví dụ lỗi | Hướng xử lý |
|---|---|---|
| HTTP status | `200` cho account thật, `404` cho account lạ. | Response công khai đồng nhất. |
| Body / thông báo UI | “Không tìm thấy email này”; hiện gợi ý tên account. | Câu chung, không gợi ý account có thật. |
| Redirect | `302 /sent` cho account thật, `200 /form` cho account lạ. | Điều hướng thống nhất cho cùng lớp request. |
| Kích thước response | Nhánh tồn tại trả metadata dài hơn. | Dùng chung template/schema. |
| Thời gian | Lookup trượt trả ngay, account thật gửi SMTP đồng bộ mất thêm 800 ms. | Tách công việc gửi sang queue và giảm chênh lệch nhánh. |
| Rate-limit | Identifier tồn tại có cooldown, không tồn tại thì không. | Áp dụng quota cho **mọi identifier hợp lệ**, cả chưa có account. |
| Email/SMS / thông báo | Một hộp thư do attacker sở hữu tự kiểm tra việc gửi. | Side channel gửi đến hộp thư là bản chất flow; không mở rộng thành endpoint tra tồn tại của người khác. |
| Endpoint kiểm tra token | Hiển thị “user X đang đặt lại password” trước khi xác minh token. | Chỉ trả trạng thái token tối thiểu, không lộ profile. |
| Telemetry công khai | `X-Account-Found: true`, error code khác biệt. | Không đưa trạng thái account vào header/analytics phía client. |

Mục tiêu không phải cam kết mọi mili-giây phản hồi **tuyệt đối bằng nhau** trên Internet; mục tiêu là loại bỏ khác biệt logic quan sát được, giảm tín hiệu timing có hệ thống và test bằng thống kê phù hợp.

## 3. Hạn chế timing side channel khi gửi email/SMS

Sai lầm thường gặp:

~~~java
// KHÔNG dùng mẫu này làm endpoint public:
if (repository.findByEmail(email).isEmpty()) {
    return ResponseEntity.notFound().build();
}
smtpClient.sendResetEmail(email); // request đợi SMTP
return ResponseEntity.ok().build();
~~~

Ngay cả khi sửa cả hai nhánh thành `200`, thời gian account thật còn phụ thuộc cuộc gọi SMTP, trong khi account lạ trả ngay. Một attacker có thể thu nhiều mẫu response để suy ra chênh lệch.

Thiết kế nên:

1. Tiếp nhận và kiểm tra cú pháp, hạn mức ở cùng đường xử lý.
2. Đưa công việc phù hợp vào **message queue/outbox** hoặc service xử lý bên trong có độ trễ không phụ thuộc mạnh vào sự tồn tại account.
3. Tách email delivery khỏi thời gian trả lời HTTP. Đảm bảo độ trễ tra account/kiểm tra policy không tạo ra nhánh khác biệt rõ rệt; có thể dùng cùng quy trình xử lý ban đầu và thực hiện công việc thực trong worker.
4. Để job gửi **chỉ gửi** khi account tồn tại, đủ điều kiện và quota cho phép. Không gửi email cho địa chỉ tùy ý chỉ để làm response đồng nhất.
5. Với throttling, áp dụng điều kiện từ các **khóa quota không phụ thuộc “có account”** và không trả response phân biệt cho known/unknown account.

**Không coi `Thread.sleep(1000)` là giải pháp chống enumeration.** Fixed sleep dễ bị DoS, timing thực vẫn biến động theo nhánh, và nếu attacker lấy nhiều mẫu, chênh lệch phân phối có thể còn hiện rõ. Một hàng đợi asynchronous giúp tách đường request khỏi SMTP nhưng vẫn cần kiểm tra xem lookup account/quota có tạo khác biệt hay không.

Thời gian biểu diễn để đo:

~~~text
Known account:    parse + quota + enqueue ack + HTTP 202
Unknown account:  parse + quota + enqueue ack + HTTP 202

Worker:
  -> lookup account
  -> (known + allowed): issue token + enqueue mail
  -> (unknown/blocked): no mail
  -> audit with protected metadata
~~~

Trong hệ thống thực tế, worker và request handler phải đồng nhất về cách normalize identifier và quota; không để một endpoint khác trả trạng thái job “mail sent/not sent” công khai.

## 4. Rate limit phải bảo vệ cả việc đoán tài khoản lẫn spam hộp thư

Token có entropy cao nên khó **đoán đúng token**, nhưng attacker có thể không cần đoán: chỉ việc yêu cầu gửi reset liên tục khiến nạn nhân bị flood, hoặc dùng SMS để gây chi phí. Vì vậy, quota yêu cầu gửi là phần thiết kế bảo mật bắt buộc.

**Không chỉ limit theo IP** vì attacker có thể dùng botnet hoặc nhiều IP; ngược lại, một IP NAT/VPN công ty có thể đại diện hàng nghìn user hợp lệ. Không chỉ limit theo email vì attacker có thể đổi email hoặc tận dụng lỗi normalize. Nên kết hợp nhiều chiều.

| Chiều giới hạn | Kiểm soát được | Lưu ý |
|---|---|---|
| **IP/client network** | Flood từ một nguồn mạng hoặc proxy. | NAT/shared IP: tránh khóa toàn bộ tổ chức quá gắt. |
| **Normalized account identifier** | Spam một mailbox/định danh dù nguồn IP thay đổi. | Áp dụng cả identifier **chưa có account**; cân nhắc HMAC identifier trong rate-limit store. |
| **Authenticated user / session** | Abuse sau login hoặc sau bước captcha. | Request recovery thường anonymous nên không thể phụ thuộc duy nhất vào session. |
| **Tenant / domain / organization** | Giữ quota hệ thống và từng khách hàng. | Không biến domain limit thành cơ chế một attacker dễ dùng để DoS tenant. |
| **Global endpoint / delivery provider** | Bảo vệ SMTP/SMS quota và chi phí. | Cần backpressure và worker retry hợp lý. |
| **Device / behavior signal** | Hỗ trợ phát hiện automation và risk scoring. | Cookie/device fingerprint có thể bị xóa/giả mạo; cân nhắc privacy. |

### Một chính sách mẫu (giá trị cần hiệu chỉnh)

~~~text
POST /account/recovery/request

- Per normalized identifier: tối đa 3 lần phát hành trong 60 phút.
- Cooldown gửi tiếp cho cùng identifier: 60 giây.
- Per IP: giới hạn ngắn hạn + burst allowance riêng.
- Per tenant / toàn hệ thống: giới hạn ngưỡng chi phí và kích thước queue.
- Nếu có tín hiệu abuse: thử thách CAPTCHA/Turnstile hoặc tăng rủi ro.
- Luôn trả thông điệp công khai thống nhất cho email có/không có account.
~~~

Các con số trên **chỉ là ví dụ**. Cần chọn theo lượng truy cập thật, tính năng hỗ trợ người khuyết tật, NAT, chi phí SMS, độ trễ email và threat model. Không để việc đối tượng xấu gửi yêu cầu reset liên tục khóa luôn tài khoản dùng đăng nhập bình thường. **Reset spam không được làm vô hiệu account trước khi có token hợp lệ**, trừ chính sách incident response riêng.

**Quan trọng:** nếu một người vừa nhấn “Gửi lại” nhiều lần, không nên đột ngột tiết lộ “Địa chỉ này đã có token active”. Frontend có thể hiển thị chung “Nếu đủ điều kiện, hướng dẫn sẽ được gửi” và dùng cooldown UI, nhưng quota thực phải được thực thi server-side.

### Quota phân tán và thông tin IP

Trong Spring Boot nhiều instance, `ConcurrentHashMap` ở một process **không phải rate limiter chung**. Cần store phân tán (như Redis) hoặc gateway limiter với thao tác atomic/TTL và cơ chế hạn chế race. Nếu backend đứng sau reverse proxy, chỉ lấy client IP từ header forwarded **khi proxy được tin cậy và đã chặn/ghi đè dữ liệu do client gửi**. Không tin một header `X-Forwarded-For` tùy ý từ Internet để bypass rate-limit.

Với identifier, có thể tính `HMAC(quotaPepper, normalizedIdentifier)` để làm key trong Redis nhằm không lưu email thô dài hạn; phải quản lý quotaPepper và phân biệt mục đích với pepper token. Dù đã HMAC, metadata vận hành vẫn cần chính sách retention và phân quyền truy cập.

## 5. Chống brute force token: khác với giới hạn số lần gửi

Có hai bề mặt độc lập:

- **Request endpoint:** attacker gửi nhiều email/SMS yêu cầu token mới (spam và enumeration).
- **Verify/consume endpoint:** attacker thử nhiều code hoặc chuỗi token để giành một phiên/đổi mật khẩu.

Với **token ngẫu nhiên 32 byte (256 bit)** do CSPRNG tạo, thử ngẫu nhiên để khớp là bất khả thi trong thực tế; nhưng vẫn phải chặn flood để bảo vệ CPU/DB và giám sát misuse. Với **mã số 6 chữ số**, chỉ có một triệu khả năng, nên phải có giới hạn số lần nhập sai theo identifier/challenge, TTL ngắn, cooldown, lockout cho *challenge* (không tự khóa toàn account) và giám sát.

| Loại | Độ mạnh / cách dùng | Kiểm soát bổ sung |
|---|---|---|
| URL token Base64url từ 32 byte CSPRNG | Entropy cao; dùng cho password reset/email verify. | TTL, single-use, purpose binding, không lộ URL, HTTPS, rate-limit request/consume. |
| Email/SMS PIN 6–8 chữ số | Dễ nhập tay nhưng không gian đoán thấp hơn rất nhiều. | Attempt counter atomic, per-challenge lockout, quota gửi, HMAC/pepper lưu trữ, chống mã sử dụng lại. |
| Magic link email | Quyền đăng nhập ngắn hạn dựa trên khả năng truy cập mailbox. | Same as URL token, thêm device/session binding theo threat model và cẩn trọng link scanners. |
| Email verification token | Chỉ chứng minh khả năng nhận thư trên địa chỉ đó trong flow. | Ràng buộc account + địa chỉ đang xác minh, không tự cấp role cao hoặc đổi ownership. |

Không đưa hành động của token từ một purpose sang purpose khác. Một token `VERIFY_EMAIL` không được dùng tại endpoint `RESET_PASSWORD`, và một token `ACCEPT_INVITATION` không được tự tạo phiên admin trừ khi flow được thiết kế, xác minh và phân quyền đúng.

## 6. Tạo và lưu one-time token để không phải giữ plaintext

Với đường dẫn khôi phục mật khẩu, server nên sinh một secret **không đoán được** bằng `SecureRandom`. Ví dụ 32 byte ngẫu nhiên mã hóa Base64url không padding thành 43 ký tự. Không sử dụng `Math.random()`, timestamp, incremental ID, email hoặc hash của email làm token.

~~~java
byte[] bytes = new byte[32];                       // 256 bit
new java.security.SecureRandom().nextBytes(bytes);
String token = java.util.Base64.getUrlEncoder()
        .withoutPadding().encodeToString(bytes); // 43 chars
~~~

Đoạn mã trên là **snippet Java 17**, chưa là chương trình độc lập.

Cách lưu:

~~~text
Client receives raw secret exactly once
             |
             v
Server computes:
  verifier = SHA-256("one-time-token:v1:" || rawSecret)
             |
             v
Database:
  token_id (optional selector / internal id)
  verifier (not rawSecret)
  subject_user_id
  purpose
  expires_at
  consumed_at
  revoked_at
  sent_to_address_version / desired email (if relevant)
  created_at, channel, issuer_context
~~~

Với 256 bit entropy, SHA-256 một chiều thường phù hợp cho token ngẫu nhiên đủ mạnh theo threat model; HMAC-SHA-256 bằng pepper ngoài DB có thể tăng cách ly nếu DB bị lộ. **Không dùng fast unsalted SHA-256 cho mã PIN ngắn như thể nó là secret 256 bit**: PIN cần chiến lược chống offline brute force thích hợp và giới hạn online.

**Không lưu token plaintext vào DB, queue payload, job log hoặc event stream lâu dài.** Để gửi email, worker đôi khi bắt buộc xử lý token plaintext trong thời gian ngắn; hạn chế quyền truy cập, retention, log và đường truyền từ queue đến mailer. Nếu email job phải lưu raw token trong queue một thời gian, điều đó vẫn là nơi lưu bí mật, nên cân nhắc giảm lifetime, mã hóa và hạn chế truy cập, hoặc thiết kế phát hành tại worker với transaction phù hợp.

Token là **credential**, khác với `token_id` công khai dùng tra cứu. Một ID công khai không được chứng minh user đã nhận được email. Liên kết token với **user ID, purpose, expiresAt và context** giúp ngăn dùng token vào hành động sai hoặc tài khoản sai.

## 7. Single-use: phải nguyên tử, không chỉ kiểm tra cờ `used` trước khi cập nhật

Một lỗi race condition quen thuộc:

~~~text
Request A: SELECT used_at == NULL  -> true
Request B: SELECT used_at == NULL  -> true
Request A: đổi mật khẩu, UPDATE used_at
Request B: đổi mật khẩu, UPDATE used_at
~~~

Cả hai request đều “thành công” vì check và update không nằm trong một ranh giới atomic. Hệ thống cần đảm bảo **chỉ đúng một thao tác consume hợp lệ** chiến thắng, kể cả khi nhiều application instance xử lý đồng thời.

Ví dụ SQL PostgreSQL dùng `UPDATE ... RETURNING` để claim token:

~~~sql
UPDATE one_time_tokens
   SET consumed_at = CURRENT_TIMESTAMP
 WHERE token_verifier = :computed_verifier
   AND purpose = 'PASSWORD_RESET'
   AND consumed_at IS NULL
   AND revoked_at IS NULL
   AND expires_at > CURRENT_TIMESTAMP
RETURNING subject_user_id;
~~~

Nếu không có dòng nào được trả về, token không còn hợp lệ cho thao tác này. **Điều kiện phải thuộc cùng một UPDATE nguyên tử**, có unique index/ràng buộc phù hợp cho verifier.

**Cần thêm một bước quan trọng:** nếu token dùng để đổi password, việc đánh dấu consumed và **cập nhật password hash** phải diễn ra trong **cùng một database transaction**, sau khi validate password policy. Nếu password update thất bại và transaction rollback, đánh dấu consume cũng rollback. Nếu mail/audit bên ngoài không tham gia cùng transaction, dùng outbox/event để đảm bảo không tạo trạng thái nửa vời. Với database và hệ thống phân tán, xét thêm idempotency, isolation, retry behavior.

Token đã được dùng phải không còn giá trị dù chưa đến `expires_at`. Token hết hạn nhưng còn trong DB không được pass; dọn dẹp định kỳ là công việc vận hành, không thay thế điều kiện kiểm tra expiry khi consume.

### Vòng đời khuyến nghị

~~~text
ISSUED  ── delivered ──►  PENDING
                             |
               +-------------+-------------+
               |             |             |
           valid POST      time limit     revoked
               |             |             |
               v             v             v
            CONSUMED       EXPIRED       REVOKED
               |
        cannot redeem again

GET link  -> show recovery page, NO state mutation
POST form -> check proof + business action atomically
~~~

Tùy nghiệp vụ, có thể giới hạn số token outstanding trên một tài khoản và chính sách resending: giữ token cũ đến khi hết hạn hay thu hồi khi cấp token mới. **Nếu mỗi request anonymous tự động thu hồi token trước đó, attacker có thể flood yêu cầu để vô hiệu hóa link mà người dùng vừa nhận.** Chọn chính sách có cooldown, rate-limit và UX rõ; không áp dụng “token mới luôn xóa mọi token cũ” mà thiếu đánh giá DoS.

## 8. Java 17 độc lập: cấp token, lưu hash và consume một lần

Ví dụ sau chạy trên **JDK 17 thuần**, không dùng Spring. Token thực sự ngẫu nhiên nên **không in ra màn hình**. Database được mô phỏng bằng `ConcurrentHashMap` trong một process; `computeIfPresent` bảo đảm thao tác consume một bản ghi là nguyên tử trong bản demo. Trong production phải dùng transaction/unique constraint tại DB (hoặc distributed atomic store) để đúng trên nhiều instance và để gắn việc consume với business action.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

public class OneTimeTokenSafetyDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final ConcurrentHashMap<String, Ticket> TOKENS =
            new ConcurrentHashMap<>();
    private static final Duration TTL = Duration.ofMinutes(15);

    record Ticket(String userId, String purpose, Instant expiresAt) {}

    static String verifier(String rawToken) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String input = "one-time-token:v1:" + rawToken;
            byte[] result = digest.digest(
                    input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(result);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 missing", e);
        }
    }

    static String issue(String userId, String purpose, Instant now) {
        while (true) {
            byte[] random = new byte[32];          // 256-bit secret
            RNG.nextBytes(random);
            String raw = Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(random);
            Ticket record = new Ticket(userId, purpose, now.plus(TTL));

            if (TOKENS.putIfAbsent(verifier(raw), record) == null) {
                return raw; // chỉ phát ra cho người nhận được phép, một lần
            }
        }
    }

    static Optional<String> consume(
            String raw, String expectedPurpose, Instant now) {
        if (raw == null || !raw.matches("[A-Za-z0-9_-]{43}")) {
            return Optional.empty();
        }

        AtomicReference<String> acceptedUser = new AtomicReference<>();
        TOKENS.computeIfPresent(verifier(raw), (digest, ticket) -> {
            if (!ticket.purpose().equals(expectedPurpose)) {
                return ticket;     // không tiêu token khác purpose
            }
            if (!now.isBefore(ticket.expiresAt())) {
                return null;       // expired: xóa bản ghi, không cấp quyền
            }
            acceptedUser.set(ticket.userId());
            return null;           // consumed: xóa nguyên tử
        });
        return Optional.ofNullable(acceptedUser.get());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String reset = issue("usr-1042", "PASSWORD_RESET", now);
        System.out.println("token length: " + reset.length());
        System.out.println("first use: " +
            consume(reset, "PASSWORD_RESET", now.plusSeconds(20))
                .orElse("DENIED"));
        System.out.println("replay: " +
            consume(reset, "PASSWORD_RESET", now.plusSeconds(21))
                .orElse("DENIED"));

        String expired = issue("usr-1042", "PASSWORD_RESET", now);
        System.out.println("expired: " +
            consume(expired, "PASSWORD_RESET", now.plus(TTL))
                .orElse("DENIED"));

        String email = issue("usr-1042", "VERIFY_EMAIL", now);
        System.out.println("wrong purpose: " +
            consume(email, "PASSWORD_RESET", now.plusSeconds(30))
                .orElse("DENIED"));
        System.out.println("correct purpose: " +
            consume(email, "VERIFY_EMAIL", now.plusSeconds(31))
                .orElse("DENIED"));
    }
}
~~~

Lưu thành `OneTimeTokenSafetyDemo.java` rồi chạy:

~~~bash
javac OneTimeTokenSafetyDemo.java
java OneTimeTokenSafetyDemo
~~~

Stdout chính xác:

~~~text
token length: 43
first use: usr-1042
replay: DENIED
expired: DENIED
wrong purpose: DENIED
correct purpose: usr-1042
~~~

Giải thích: token 32 byte -> 43 ký tự Base64url; hash chỉ dùng để tìm bản ghi; `computeIfPresent` chỉ cho một thread remove bản ghi hợp lệ trước khi thread thứ hai thấy nó. Khác purpose không consume; hết hạn đúng thời điểm biên bị chặn. `Instant` cố định giúp stdout ổn định, nhưng **token không phải giá trị cố định**.

**Hạn chế của demo:** `ConcurrentHashMap` chỉ tồn tại trên một JVM; không có database, rate-limit, password hashing, email, transaction với business action, bảo vệ request, CSRF hay điều phối nhiều replica. Hàm `consume` trả ID nội bộ để học cơ chế; production không được đưa ID đó vào response public khi token chưa được xác thực/ủy quyền theo flow phù hợp. Đừng dùng đoạn code này làm một hệ thống reset password hoàn chỉnh.

## 9. Token trong URL: vì sao dễ rơi vào log và lịch sử

Một email có thể chứa đường dẫn:

~~~text
https://accounts.example.test/recovery/open?token=<opaque-random-token>
~~~

Chuỗi `<opaque-random-token>` là chỗ minh họa, không phải credential thực. Khi người dùng mở liên kết, token có thể xuất hiện ở nhiều nơi:

- **Browser address bar và history:** người dùng có thể sao chép, chụp màn hình, đồng bộ lịch sử giữa thiết bị hoặc để extension quan sát URL.
- **HTTP request target:** reverse proxy, CDN, WAF, API gateway và server access log có thể ghi path + query, ngay **trước khi Spring Security xử lý**.
- **APM/tracing/error reporting:** span name, request URL, exception log, request dump và crash report có thể chứa nguyên query.
- **`Referer` header:** khi trang đang có URL nhạy cảm tải tài nguyên hoặc điều hướng, chính sách referrer không chặt có thể gửi URL đầy đủ (đặc biệt khi cùng origin). Mặc định của browser không phải cam kết không rò token cho mọi loại request.
- **Analytics, third-party scripts, pixels:** script chạy trong page có thể đọc `window.location.href` và gửi tới hệ thống bên ngoài. Một số email client/security scanner cũng có thể truy cập link trước người dùng.
- **Screenshots/helpdesk/recording:** người dùng vô tình gửi ảnh màn hình hoặc ticket kèm URL.
- **Link preview/antivirus bot:** hệ thống an toàn email có thể tự mở liên kết để kiểm tra; nếu GET làm tiêu token, user không sử dụng được, hoặc kẻ khác có điều kiện kích hoạt hành động.

**Đưa token từ query sang path không tự giải quyết vấn đề.** URL path vẫn có thể bị access log và browser history ghi. Tránh kết luận “HTTPS bảo vệ token khỏi log”: HTTPS chỉ bảo vệ đường truyền giữa endpoints, không bảo vệ hệ thống đầu cuối/observability đã thấy plaintext request.

### Những biện pháp trực tiếp

1. **Không log token** ở mọi hop: proxy/CDN, ingress, WAF, app, APM, analytics. Cấu hình access log chỉ ghi **route template/path không chứa secret** và bỏ/redact query string tại endpoint nhạy cảm; kiểm tra log retry/error.
2. Trên response chứa form hoặc recovery context dùng `Referrer-Policy: no-referrer`, `Cache-Control: no-store`; có thể thêm CSP chặt và `X-Robots-Tag: noindex, nofollow`. Đừng tải ảnh/script/tracker bên thứ ba trên trang chứa token.
3. **Không dùng GET để tiêu token**. GET chỉ hiển thị trang xác nhận hoặc đổi token sang một recovery session giới hạn được bảo vệ; hành động thực hiện bằng POST sau khi người dùng nhập/chấp thuận.
4. Khi đã có context an toàn, **chuyển hướng sang URL sạch** hoặc dùng `history.replaceState` sớm để loại token khỏi thanh địa chỉ/history entry hiện tại. Biện pháp này giảm nguy cơ lộ về sau, **không xóa được request/log/history sync đã xuất hiện trước đó**.
5. Tối thiểu hóa TTL, ràng buộc purpose, one-time consumption và chính sách invalidate/revoke để giảm thời gian khai thác nếu bị lộ.
6. Không dùng token trong `Referer`, route analytics, event name, error title, dashboard filter hay request ID.

### Header minh họa cho trang recovery

~~~http
HTTP/1.1 200 OK
Referrer-Policy: no-referrer
Cache-Control: no-store
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
X-Robots-Tag: noindex, nofollow
Content-Type: text/html; charset=UTF-8
~~~

Chọn CSP thực tế theo frontend; không bật inline script không kiểm soát chỉ để dùng `replaceState`. `Cache-Control: no-store` chủ yếu bảo vệ **response caching**, không tự xóa URL khỏi browser history hay log server. `Referrer-Policy` điều khiển `Referer` trên request phát sinh từ document, không xóa token khỏi **request ban đầu** đến server.

### Làm sạch URL bằng JavaScript (tùy kiến trúc)

~~~javascript
// Chỉ chạy trong first-party recovery page đáng tin.
// Raw token phải đã được lưu/đưa vào recovery flow an toàn trước khi xóa URL.
const url = new URL(window.location.href);
const token = url.searchParams.get("token");

if (token) {
    url.searchParams.delete("token");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    // Thực hiện thao tác người dùng ở bước riêng; không auto consume trên load.
}
~~~

Đây là **snippet phía browser**, không phải cấu hình bảo mật hoàn chỉnh: biến `token` vẫn tồn tại trong memory, trang có thể đã gửi initial URL đến server và các script chạy trước đoạn này có thể đã đọc token. Đừng để tracker/analytics chạy trước bước vệ sinh URL; tốt hơn là **không đưa token vào nơi chúng có thể chạy**.

Một biến thể đưa token vào **URL fragment** (`#token=...`) thường khiến fragment không nằm trong HTTP request target gửi tới server; frontend tin cậy phải đọc fragment và truyền token qua HTTPS POST. Cách này cũng có rủi ro trong address bar, history, extension và JavaScript; không phải phương pháp mặc định an toàn cho mọi ứng dụng và cần đánh giá link scanners/mobile deep links. Với flow đơn giản, server-side redirect sang URL sạch kết hợp header/log redaction thường dễ kiểm soát hơn.

## 10. Tránh tiêu token bằng GET: email scanners và link preview

Email security gateway và ứng dụng email có thể **truy cập URL tự động** để kiểm tra phishing hoặc tạo preview. Nếu server xử lý reset/verify/login ngay trên HTTP GET, bot có thể vô tình consume token trước khi người dùng nhìn thấy email.

Mẫu **không đúng**:

~~~http
GET /account/recovery/open?token=...   -> mark used = true; change password
~~~

Mẫu nên dùng:

~~~text
GET  /account/recovery/open?token=...
  -> trả trang first-party, không đổi mật khẩu/activate account
  -> không auto POST, không auto-login
  -> header no-referrer + no-store, no third-party content

User chủ động nhập mật khẩu mới / bấm xác nhận
  |
  v
POST /account/recovery/complete
  -> CSRF/origin policy phù hợp
  -> validate password + token purpose/TTL
  -> atomic consume + update password in transaction
  -> revoke old sessions/refresh tokens theo chính sách
  -> 303 redirect tới URL sạch
~~~

Với magic link login, có thể đổi token thành **phiên giới hạn để xác nhận** sau bước yêu cầu user tương tác; tránh tạo full authenticated session chỉ vì một robot truy cập GET. Bất cứ biến thể nào cũng phải xác định rõ **khi nào quyền được cấp** và xử lý link prefetch.

Nếu cần dùng **mã số nhập tay** thay URL token, người dùng có thể mở form ở URL không chứa bí mật rồi tự điền mã. Đổi lại, mã ngắn cần attempt limiting mạnh; không tự coi PIN 6 chữ số có độ an toàn như secret 256 bit.

## 11. Cách tạo URL khôi phục không bị Host header injection

Trong ứng dụng web, một lỗi ít được chú ý là xây email link từ input mạng:

~~~text
https://{request.getServerName()}/recovery/open?token=...
~~~

Khi proxy/header forwarding cấu hình sai, attacker có thể ảnh hưởng `Host` hoặc `X-Forwarded-Host`. Email chứa token thật nhưng trỏ tới domain do attacker kiểm soát: người dùng click link, token bị gửi tới attacker.

**Hãy dùng base URL được cấu hình và kiểm soát**, ví dụ `https://accounts.company.example`, hoặc allowlist strict theo tenant đã xác minh. Không ghép hostname do request anonymous tự cung cấp vào password-reset email. Kiểm tra HTTPS và exact redirect URL; không chấp nhận `returnTo` tùy ý biến endpoint thành open redirect.

~~~java
// Snippet minh họa (Spring app hoặc Java thuần):
String resetBaseUrl = "https://accounts.company.example";
String link = resetBaseUrl + "/recovery/open?token="
    + java.net.URLEncoder.encode(
        token, java.nio.charset.StandardCharsets.UTF_8);
~~~

Tùy chọn `URLEncoder` dùng biểu diễn form-style; token Base64url thuần thường đã là URL-safe. Chỉ sinh URL từ **origin được cấu hình tin cậy**, không phải header của request. Đoạn này bắt buộc có biến `token` do hệ thống phát hành, là **snippet tích hợp**, không chạy độc lập. Email phải được gửi qua hệ thống được kiểm soát, tránh chèn token vào template tracking URLs không cần thiết.

## 12. Spring Security: tổ chức request và consume endpoints

Trong Spring Boot 3.x/Spring Security 6.x (Servlet), hai lớp chính là:

- **Controller** nhận form/recovery request, trả response công khai nhất quán và ủy quyền cho service; không triển khai cryptography trong controller.
- **Application service** giữ normalization, quota, issue, message queue, validate token, update password, transactional consume và audit.
- **SecurityFilterChain** áp chính sách anonymous access cho form cần mở công khai, còn CSRF/cookie security, session handling và security headers vẫn phải được cấu hình phù hợp; **`permitAll()` không tự tắt CSRF**.

Ví dụ controller **mô tả integration**, không phải một chương trình `javac` độc lập; cần Spring MVC và interface `RecoveryUseCases` do hệ thống triển khai:

~~~java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/account/recovery")
public class RecoveryController {
    private final RecoveryUseCases recovery;

    public RecoveryController(RecoveryUseCases recovery) {
        this.recovery = recovery;
    }

    @PostMapping("/request")
    public ResponseEntity<Map<String, String>> request(
            @RequestParam("email") String email) {
        // Normalize + quota áp cho cả email tồn tại và không tồn tại.
        // Queue công việc, KHÔNG gửi mail đồng bộ.
        recovery.acceptRequestWithoutLeakingAccountStatus(email);
        return ResponseEntity.accepted().body(Map.of(
            "message",
            "Nếu thông tin khớp với tài khoản đủ điều kiện, "
              + "chúng tôi sẽ gửi hướng dẫn."));
    }

    @PostMapping("/complete")
    public ResponseEntity<Map<String, String>> complete(
            @RequestParam("token") String token,
            @RequestParam("newPassword") String newPassword) {
        // Service validate và commit consume + password update
        // trong cùng transaction.
        if (!recovery.consumeAndResetPassword(token, newPassword)) {
            return ResponseEntity.badRequest().body(Map.of(
                "message", "Liên kết không hợp lệ hoặc đã hết hạn."));
        }
        return ResponseEntity.ok(Map.of(
            "message", "Đã cập nhật mật khẩu."));
    }
}
~~~

~~~java
// Hợp đồng ứng dụng cần triển khai với DB, queue, rate limiter,
// password encoder và giao dịch; đây không phải app tự chạy.
public interface RecoveryUseCases {
    void acceptRequestWithoutLeakingAccountStatus(String email);
    boolean consumeAndResetPassword(String rawToken, String newPassword);
}
~~~

**Những điểm phải tự triển khai trước production:**

- `acceptRequestWithoutLeakingAccountStatus` kiểm tra đầu vào, normalize identifier **nhất quán với quy tắc đăng ký**, áp multi-dimensional quotas, lưu job an toàn hoặc outbox, không tạo mail khi account không tồn tại, không tiết lộ lookup result cho caller.
- `consumeAndResetPassword` kiểm tra token, purpose, expiry, used/revoked, password policy, xác định internal user, hash password bằng `PasswordEncoder` phù hợp (ví dụ Argon2id/bcrypt/scrypt theo cấu hình) rồi consume **nguyên tử cùng password update**. Không dùng SHA-256 đơn giản thay thế password hashing.
- Nếu dùng session/cookie, giữ **CSRF protection** cho POST form và sử dụng token CSRF/Origin controls phù hợp. Token recovery không tự thay thế mọi kiểm soát CSRF; không disable CSRF toàn ứng dụng để “cho form chạy”.
- Với session đang tồn tại sau password reset, quyết định hủy session cũ, refresh token và remember-me token. Cơ chế thu hồi phải được triển khai, không mặc định Spring Security tự thu hồi mọi phiên trên mọi thiết bị.
- Nếu có token trong request body, phải redact body/exception log. Nếu có token trong URL của GET, còn phải redact query ở gateway, proxy và app; **controller không kiểm soát được những log sinh trước nó**.
- Tầng API có thể dùng HTTP 400 cho token không hợp lệ/hết hạn nhưng phải tránh tiết lộ account, không phân biệt “token của user X” với “token của user Y” công khai.

### Một cấu hình SecurityFilterChain tối thiểu để hiểu scope

~~~java
// Spring Security 6.x, snippet integration:
// Các endpoint request/complete phải cho anonymous truy cập,
// nhưng CSRF mặc định của web form vẫn có hiệu lực.
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/account/recovery/**").permitAll()
        .anyRequest().authenticated());
    return http.build();
}
~~~

Ví dụ này **chưa đủ** để thành một ứng dụng hoàn chỉnh: cần cấu hình `@Bean`, CSRF token exposure cho form, URL GET, login cho các route khác, recovery service, response headers, password policy và persistent storage. Không nên copy nó để vô tình thay cấu hình chain hiện hành. Spring Security hỗ trợ CSP/Referrer-Policy/cache headers; vẫn cần cấu hình proxy/CDN/analytics riêng, không chỉ mỗi filter chain.

## 13. Có nên hiển thị thời gian hết hạn và trạng thái “đã gửi”?

Có thể công bố một câu chung kiểu “Nếu tài khoản đủ điều kiện, hãy kiểm tra email trong vài phút” và thời gian có thể dùng token (ví dụ 15 phút theo chính sách). Không nên:

- Hiển thị **địa chỉ khôi phục bị che một phần** chỉ khi account có thật, như `l***@company.example`, trước khi người dùng chứng minh quyền sở hữu account.
- Cho biết “email đang chờ gửi”, “đã gửi lúc 10:32”, “lần gửi thứ 3” hoặc “account chưa xác minh” ở endpoint public nếu khác biệt theo trạng thái account.
- Cho một endpoint `GET /request-status?email=...` công khai phân biệt job thành công/thất bại cho từng người dùng.
- Trả `Retry-After` khác nhau dựa trên việc account thật có quota còn account lạ không có; áp quota đồng nhất theo identifier bất kể lookup.
- Đưa vào response JSON mã nội bộ như `USER_NOT_FOUND` hoặc `LOCKED_ACCOUNT` rồi chỉ che message hiển thị bằng frontend.

Với user **đã đăng nhập** và đã qua xác thực mạnh, có thể hiển thị trạng thái quản lý email/2FA cụ thể theo policy. Bài toán account enumeration ở đây chủ yếu áp dụng với **anonymous recovery endpoint**, nơi caller chưa được xác thực quyền xem thông tin account.

### Resend và multiple outstanding tokens

Có hai chính sách thông dụng:

1. **Giữ một token active trong khoảng ngắn, bỏ qua resend liên tiếp:** giảm email flood nhưng không thể gửi lại raw token nếu server chỉ lưu hash. Không nên thử “lấy lại” secret. Có thể giữ job gửi sắp phát hành ở queue an toàn trong thời gian kiểm soát hoặc yêu cầu người dùng đợi, sau cooldown issue token mới.
2. **Cấp token mới và cho phép một số token cùng tồn tại:** thuận lợi cho thư đến chậm/out-of-order nhưng cần giới hạn số token active và expiry, revoke đúng khi action hoàn tất. Nếu cấp mới thu hồi cũ, attacker anonymous có thể gây DoS bằng cách reset spam.

Chính sách nào cũng cần rate-limit, cooldown và thông điệp chung. Sau khi đổi password thành công nên vô hiệu hóa các **password-reset token liên quan đến account** theo policy để những link cũ không hoạt động; nếu có race phải dùng transaction/locking phù hợp.

## 14. Xử lý email/SMS delivery mà không để lộ token

Token thường đi qua mailer/SMS provider, nhưng hệ thống vẫn có thể hạn chế độ phơi lộ:

- Chỉ gửi đến **địa chỉ đã liên kết và được xác minh theo chính sách**, không cho anonymous caller đổi `sendTo` để nhận token của user khác.
- Mẫu email có domain/origin chính xác, nhận diện thương hiệu và nhấn mạnh không chia sẻ link. Không chứa mật khẩu, thông tin tài khoản nhạy cảm không cần thiết.
- Nếu dùng dịch vụ theo dõi click/open của mail marketing, **tắt link rewriting/tracking redirect đối với reset link**. Một tracking domain trung gian có thể nhận full token.
- Cẩn trọng với email preview/security scanning: nếu bot mở link GET thì không tự thực hiện hành động.
- Hàng đợi cần mã hóa và ACL theo threat model, thời hạn lưu ngắn, không dump payload email ra debug log; các bản sao raw token trong retry queue/DLQ cũng là bí mật.
- Nếu email bị bounce, bị suppression hoặc SMS provider lỗi, không lộ lý do account tồn tại qua endpoint public; giám sát nội bộ theo chính sách.
- Kiểm tra lỗi gửi ở mức worker có backoff, giới hạn retry để không gửi spam; tránh gửi lại nhiều secret hoặc dùng lại một token hết hạn một cách mơ hồ.

**Email không bảo đảm luôn là yếu tố xác thực đủ mạnh** cho account admin/financial. Có thể cần MFA, thiết bị đáng tin, bước xác minh khác hoặc hỗ trợ thủ công có audit. Nếu reset mật khẩu đồng nghĩa xóa MFA, cần flow riêng có kiểm soát mức rủi ro cao hơn.

## 15. Phân biệt kiểm soát HTTP, browser và logs

Một thiết kế an toàn phải xét **đúng vị trí rò rỉ**, tránh đặt một header rồi cho rằng đã xong.

| Vị trí | Nguy cơ | Biện pháp tương ứng |
|---|---|---|
| Email/SMS | Người khác truy cập mailbox, mail forward, link tracking. | TTL ngắn, recipient policy, không tracking URL, MFA/risk policy. |
| Link khi nhập vào browser | History/address bar/clipboard/extension. | One-time TTL, chuyển URL sạch, có thể dùng fragment/POST flow phù hợp. |
| CDN/WAF/reverse proxy | Access log ghi full request URI/query. | Redact token/query theo route tại **mọi hop**, kiểm soát log ACL/retention. |
| Spring MVC/HTTP server | Request dump, debug, exception chứa token. | Structured logging whitelist field; không log body/header/query nhạy cảm. |
| Frontend SPA | Analytics, session replay, third-party script đọc URL. | First-party-only recovery page, CSP, analytics exclusion, early URL cleanup. |
| Browser Referer | Lộ đường dẫn/params khi fetch/navigate. | `Referrer-Policy: no-referrer`, không có third-party resources. |
| Browser/proxy cache | Lưu trang chứa dữ liệu nhạy cảm. | `Cache-Control: no-store` cho recovery form/response nhạy cảm. |
| DB, queue, backup | Token plaintext còn trong bản sao. | Lưu verifier một chiều; queue retention/ACL/encryption; scrub backups/logs theo policy. |
| Audit/support | Nhân viên vận hành nhìn thấy raw token trong ticket. | Ghi request ID/credential metadata, không raw secret. |

**Không thể “xóa mọi dấu vết” chỉ bằng `history.replaceState`.** Nó thay đổi history entry phía trình duyệt hiện tại; không thu hồi URL đã được gửi tới proxy, mail service, extension hoặc screenshot. Bảo vệ nhiều lớp và giới hạn thời gian hiệu lực là cần thiết.

### Log an toàn nên trông như thế nào?

Thay vì:

~~~text
GET /account/recovery/open?token=Vn...full-token... 200 145ms
~~~

Hãy ghi:

~~~json
{
  "event": "recovery_page_view",
  "route": "/account/recovery/open",
  "requestId": "req-b793",
  "result": "rendered",
  "durationMs": 145
}
~~~

Nếu cần correlate token để điều tra, có thể log **ID ngẫu nhiên riêng không cho phép xác thực** hoặc HMAC/truncated token fingerprint với khoá theo dõi tách biệt và chính sách retention, sau khi đánh giá privacy. **Không log raw token hay giá trị verifier đầy đủ**. Với email/username cũng nên dùng pseudonymization khi đủ cho mục đích vận hành.

Một log chỉ chứa mã HTTP không thể chứng minh token không lộ: phải kiểm tra log pipeline từ **ingress đến APM, frontend monitoring, backup và DLQ**. Security review nên có log redaction test tự động với một token canary giả lập, không dùng token người dùng thật.

## 16. Tình huống minh họa: doanh nghiệp gửi password reset link

Giả sử hệ thống nhân sự có account `lan@company.example`. Attacker muốn dò tài khoản và spam yêu cầu:

### Kịch bản A — Attacker thử một danh sách email

~~~text
POST /account/recovery/request email=lan@company.example
POST /account/recovery/request email=nobody@company.example
~~~

Hai request có cú pháp hợp lệ phải có response công khai tương đương. Quota theo identifier phải tính cho cả hai địa chỉ; worker chỉ gửi mail cho account thật đủ điều kiện. Không có URL `/recovery/status` để attacker biết mail job đã tạo.

### Kịch bản B — Attacker spam cùng một người qua hàng trăm IP

IP-only rate limit không hiệu quả. Hệ thống dùng limiter theo normalized identifier, IP/network, tenant và global queue. Vượt quota chỉ **ngừng/giảm phát hành token** hoặc yêu cầu challenge, không khóa account của Lan và không thay password. Monitoring ghi nhận spike nhưng không lưu email rõ ở nơi không cần thiết.

### Kịch bản C — Lan nhận email nhưng link bị email scanner mở trước

GET chỉ render/kiểm tra mức tối thiểu mà **không consume** token. Lan mở link, nhập mật khẩu mới và submit POST; transaction consume đúng một lần. Nếu scanner mở GET nhiều lần, token không vô hiệu chỉ vì click preview. Nếu hai POST cạnh tranh, chỉ một POST cập nhật thành công.

### Kịch bản D — Reverse proxy vô tình ghi token vào query log

Ngay cả khi DB chỉ có hash, proxy vẫn có thể ghi full URL chứa secret. Phải thay access-log template/redaction; rà soát retention/quyền truy cập các bản ghi đã lộ và **revoke các token có nguy cơ phơi lộ** theo incident response. `Cache-Control: no-store` không chữa được log ở proxy.

### Kịch bản E — User nhấn nút “Gửi lại” liên tục

Hệ thống có cooldown và message chung, không tự tạo vô hạn token mới. Nếu backend chọn chính sách cấp token mới, phải đảm bảo email cũ/ mới không bị đảo thứ tự làm user không thể hoàn tất; nếu chọn giữ một token active, không thể đọc lại raw token từ DB hash để gửi nó lần nữa. Thiết kế resend phải phản ánh thực tế đó.

### Kịch bản F — Password đã đổi thành công

Sau POST thành công, token consumed, các reset token cũ theo policy bị vô hiệu, session/refresh-token cũ bị xử lý theo policy, audit ghi sự kiện nhưng không ghi credential. Gửi một security notification đến kênh thông báo đã đăng ký (không kèm token), và chuyển browser đến URL sạch.

## 17. Bộ kiểm thử cho cả ba rủi ro

| Nhóm | Test case | Kỳ vọng |
|---|---|---|
| Enumeration | Email có account vs không có account. | Mã HTTP/body/redirect/header công khai nhất quán. |
| Enumeration | Account active vs disabled chưa được xác minh. | Không lộ trạng thái qua anonymous endpoint. |
| Enumeration | Kiểm tra timing qua nhiều mẫu. | Không có chênh lệch có hệ thống rõ do xử lý SMTP đồng bộ/nhánh lookup. |
| Enumeration | Rate limit với identifier không tồn tại. | Không bypass quota hoặc khác response công khai so với account thật. |
| Quota | Cùng identifier, nhiều IP. | Identifier limiter vẫn có hiệu lực. |
| Quota | Cùng IP NAT, nhiều user hợp lệ. | Chính sách không gây chặn quá mức, có fallback/monitoring. |
| Quota | Nhiều instance song song. | Đếm quota atomic ở store dùng chung. |
| Quota | Attacker nhấn resend nhiều lần. | Không flood mailbox, không tự khóa account, token policy nhất quán. |
| Token | Sinh secret bằng CSPRNG. | Đủ entropy và format; không dựa timestamp/email. |
| Token | Kiểm tra mục đích sai. | Token `VERIFY_EMAIL` không dùng được để reset password. |
| Token | Sau khi hết hạn. | Từ chối dù DB chưa dọn rác. |
| Token | Double-submit đồng thời. | Chỉ một transaction được consume và áp dụng business action. |
| Token | Reset password transaction lỗi. | Rollback token consumed, không nửa chừng. |
| Token | Đã dùng, gửi lại đúng chuỗi. | Bị từ chối (replay). |
| Token | Trình mã PIN sai nhiều lần. | Attempt limit chặn online guessing. |
| Browser | GET URL từ email scanner. | Không đổi password, không login hay consume trên GET. |
| Browser | Trang recovery tải tài nguyên third-party. | Không có tracking, CSP/referrer policy chặn rò URL. |
| Browser | Hoàn tất flow. | Redirect/replaceState sang URL sạch, không còn secret trên URL app. |
| Logs | Request URL chứa token canary. | Không thấy token ở proxy/CDN/APM/exception/server logs. |
| Cache | Recovery response. | Có `Cache-Control: no-store`, không vô tình cache nội dung nhạy cảm. |
| Phishing | Host hoặc forwarded host giả. | Reset link dùng allowed origin; không đưa token sang domain lạ. |
| Email | Link tracking rewrite. | Token không đi qua URL của bên thứ ba. |
| Privacy | Analytics và session replay. | Không ghi token, body mật khẩu, email không cần thiết. |
| Lifecycle | Account đã reset. | Invalidate sessions/tokens theo policy và gửi security notification. |
| Hạ tầng | SMTP/queue/store lỗi. | Fail closed, không phát token tràn lan hoặc tiết lộ account status. |

**Đừng chỉ test mã HTTP của endpoint.** Cần cả integration tests giữa limiter, DB transaction, mailer, Spring Security filter, gateway logging và browser/headless để tìm rò rỉ qua các lớp mà unit test Java không nhìn thấy. Test log leakage dùng token giả lập và môi trường kiểm soát, không phát email thật tới người ngoài.

## 18. Checklist triển khai trước khi phát hành

### Thiết kế request endpoint

- [ ] Anonymous request trả cùng một thông điệp, schema và trạng thái công khai cho identifier tồn tại/không tồn tại.
- [ ] Input normalization nhất quán với dữ liệu đăng ký; không suy đoán quy tắc email như bỏ dấu chấm/`+tag` cho mọi domain.
- [ ] Không gửi email/SMS đồng bộ trên đường trả lời công khai; tránh timing khác biệt dễ quan sát.
- [ ] Áp rate limit cho IP, normalized identifier kể cả account chưa tồn tại, tenant và global; dùng atomic store phân tán.
- [ ] Không khóa account chỉ vì nhận quá nhiều yêu cầu khôi phục; có monitoring/challenge khi abuse.
- [ ] Không cung cấp endpoint status/email existence công khai.

### Thiết kế token và consume

- [ ] CSPRNG đủ entropy, secret không đoán được; lưu hash/HMAC thay plaintext khi chỉ cần đối chiếu.
- [ ] Token gắn user, purpose, expiry, trạng thái, context; không tái sử dụng giữa reset/verify/invite.
- [ ] Kiểm tra expiry/revoked/consumed khi consume, không chỉ lúc render GET.
- [ ] Thay đổi nghiệp vụ và đánh dấu used trong cùng database transaction, an toàn khi request đồng thời.
- [ ] Chỉ POST (hoặc tương đương có chủ đích) tạo side effect; GET không tiêu token do link scanners.
- [ ] Sau thành công, revoke token/session theo policy, không giữ link cũ có thể dùng lại.

### Thiết kế HTTP, browser và vận hành

- [ ] HTTPS và origin reset URL cấu hình cố định/allowlist, không lấy từ Host header client.
- [ ] `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, CSP phù hợp trên trang recovery; không có third-party scripts/trackers.
- [ ] Log redaction tại CDN/WAF/reverse proxy/app/APM/queue, không chỉ trong controller.
- [ ] Cân nhắc URL sạch/redirect/`history.replaceState`, nhận thức giới hạn của chúng đối với log/history đã tồn tại.
- [ ] Form POST và session/cookie có CSRF/origin controls phù hợp; không tắt CSRF blanket cho cả site.
- [ ] Email không rewriting qua tracking domain, không xuất raw token trong analytics/hỗ trợ.
- [ ] Có test concurrency, replay, rate limit, false positive, timing và log canary.
- [ ] Có quy trình incident response: phát hiện token leak, revoke, cleanup, rotate và rà soát kênh rò rỉ.

## 19. Kết luận

Ba lớp bảo vệ của one-time token phải hoạt động **đồng thời**:

1. **Chống dò tài khoản:** endpoint yêu cầu không tiết lộ sự tồn tại/trạng thái account qua status, body, redirect, thời gian và quota.
2. **Chống lạm dụng gửi:** giới hạn theo nhiều chiều, phân biệt request quota và verify attempts, bảo vệ mailbox/SMS provider và không biến reset spam thành account lockout.
3. **Chống lộ token:** CSPRNG + TTL + one-time atomic consume, lưu verifier thay plaintext, không để token trong log/Referer/analytics/cache/history quá mức có thể kiểm soát, GET side-effect-free và URL sạch sau flow.

**Thông điệp quan trọng:** một token mạnh về mật mã không còn an toàn nếu được ghi vào log có người đọc, và một endpoint generic không còn chống enumeration nếu timing/quota cho biết account tồn tại. Thiết kế phải đo và kiểm thử **từ proxy đến database, từ mailer đến browser**, thay vì chỉ xem code controller.

## Tài liệu tham khảo

- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): generic responses, timing, account abuse, secure reset token, URL và Referrer-Policy.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account enumeration từ thông báo và timing.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing (khác với hash token ngẫu nhiên).
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): lifecycle và thu hồi session.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nhạy cảm không nên ghi log.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): điều khiển `Referer` gửi từ browser.
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): lưu cache và chỉ thị `no-store`.
- [MDN — History.replaceState](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState): thay URL của history entry hiện tại.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF trên các request đổi trạng thái.
- [Spring Security — HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): security headers và policy.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): tạo secret đủ entropy.
- [Java 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thao tác atomic theo key trong mô phỏng single JVM.
