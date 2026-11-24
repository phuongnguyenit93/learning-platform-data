# Error timing

## 1. Error timing là gì?

**Error timing (thời gian phản hồi của nhánh lỗi)** là khoảng thời gian hệ thống cần để xử lý một request dẫn tới lỗi hoặc bị từ chối. Trong authentication, thời gian này có thể tiết lộ thông tin mà response body không nói ra: tài khoản có tồn tại không, password có đúng không, user có bật MFA không, recovery code có hợp lệ không hoặc token có qua được một bước xác minh nào đó không.

Ví dụ: một endpoint đăng nhập trả cùng thông báo “Thông tin đăng nhập không hợp lệ” cho cả email không tồn tại và password sai. Tuy nhiên, với email không tồn tại, server trả lời sau 15 ms vì không tìm thấy bản ghi; với email tồn tại, server mất 250 ms để kiểm tra password hash rồi mới từ chối. Attacker đo nhiều lần có thể phân biệt hai trường hợp qua thời gian phản hồi và xây dựng danh sách tài khoản hợp lệ.

Đây là một dạng **timing side-channel**: dữ liệu bí mật không được trả trực tiếp, nhưng tác động của nó lên thời gian thực thi có thể quan sát từ bên ngoài. Side-channel có thể tồn tại ở network latency, CPU, cache, database lookup, cryptographic operation hoặc thứ tự gọi dependency.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, Error timing nằm ở giao điểm của authentication, privacy và abuse prevention. Hệ thống cần tránh để thời gian phản hồi trở thành oracle giúp attacker suy ra trạng thái tài khoản hoặc bí mật xác thực, đồng thời giữ latency hợp lý cho người dùng hợp lệ.

## 2. Timing side-channel trong authentication

Một endpoint có thể trả cùng status code và message nhưng vẫn có thời gian xử lý khác nhau:

| Nhánh xử lý | Công việc có thể xảy ra | Thông tin có thể bị suy ra |
| --- | --- | --- |
| Username không tồn tại | Lookup nhanh rồi trả lỗi. | Tài khoản không tồn tại. |
| Username tồn tại, password sai | Đọc password verifier và chạy password hash verification. | Tài khoản có tồn tại. |
| Password đúng, MFA chưa hoàn tất | Kiểm tra factor hoặc tạo challenge. | Tài khoản có MFA hoặc factor cụ thể. |
| Recovery code không tìm thấy | Lookup một tập verifier rồi trả lỗi. | Bộ mã hoặc account có thể không tồn tại. |
| Recovery code tìm thấy nhưng đã dùng | Đọc trạng thái rồi từ chối. | Mã đã từng hợp lệ hoặc đã bị tiêu thụ. |
| Token sai issuer/audience | Dừng ở bước kiểm tra claim. | Loại token hoặc cấu hình issuer/resource. |
| Token đúng chữ ký nhưng hết hạn | Hoàn tất verify rồi kiểm tra thời gian. | Token đã được ký hợp lệ nhưng không còn hiệu lực. |
| User bị khóa | Kiểm tra account state rồi từ chối. | Trạng thái khóa hoặc risk flag. |

Attacker không cần biết chính xác một request mất bao nhiêu mili giây. Họ có thể gửi nhiều request, lấy trung vị hoặc phân phối độ trễ, so sánh giữa các nhóm và loại bớt nhiễu do mạng.

### 2.1. Error message giống nhau chưa đủ

Generic error message là một kiểm soát cần thiết để hạn chế account enumeration qua nội dung response. Nhưng nếu nhánh xử lý khác nhau đáng kể về thời gian, status, kích thước response, header hoặc số lần redirect, attacker vẫn có thể phân loại kết quả.

Ví dụ:

- Email không tồn tại trả HTTP 401 ngay.
- Email tồn tại nhưng password sai trả HTTP 401 sau khi verify Argon2id.
- Tài khoản bị khóa trả HTTP 423 ngay.

Ba phản hồi có thể làm lộ ba trạng thái khác nhau dù body đều ghi “Đăng nhập không thành công”. Cần xem toàn bộ observable response, không chỉ câu thông báo.

## 3. Những dữ liệu nhạy cảm có thể bị lộ qua timing

Timing side-channel có thể tiết lộ:

- Tài khoản hoặc email có tồn tại.
- Tài khoản đang active, disabled, locked hoặc pending enrollment.
- Người dùng có đăng ký MFA, passkey, recovery channel hay không.
- Password có đúng một phần hoặc đã qua một bước xác minh hay không.
- Recovery code có thuộc một bộ mã hợp lệ, đã dùng hay đã thu hồi.
- Token có chữ ký hợp lệ, key ID tồn tại hoặc issuer được tin cậy không.
- Một API key hoặc client credential có tồn tại trong kho bí mật.
- Một tài nguyên có tồn tại trong tenant hoặc có quyền truy cập không.
- Một email hoặc số điện thoại có được đăng ký trong hệ thống không.

Không phải mọi khác biệt timing đều là lỗ hổng có thể khai thác. Cần đánh giá mức độ nhạy cảm, khả năng lặp lại, độ nhiễu mạng, giới hạn request và việc thông tin đó có thể hỗ trợ tấn công tiếp theo hay không.

## 4. Threat model và điều kiện khai thác

Attacker thường cần:

1. Một endpoint có thể gọi từ xa, ví dụ login, password reset, MFA hoặc recovery.
2. Khả năng gửi nhiều request với input được kiểm soát.
3. Khả năng đo thời gian gửi request và nhận response đủ ổn định.
4. Một biến bí mật làm thay đổi đường xử lý, chẳng hạn account tồn tại hay không.
5. Đủ số mẫu để phân biệt tín hiệu với network noise.

Các yếu tố làm tấn công dễ hơn:

- Endpoint công khai, không có rate limit.
- Một nhánh xử lý nhanh hơn nhánh còn lại hàng trăm mili giây.
- Password hashing chỉ chạy khi username tồn tại.
- Database/cache có hit/miss ổn định theo trạng thái tài khoản.
- Response status hoặc kích thước khác nhau giữa các nhánh.
- Gửi email/SMS hoặc gọi dependency đồng bộ chỉ xảy ra với account tồn tại.

Các yếu tố làm tấn công khó hơn:

- Các nhánh nhạy cảm thực hiện công việc tương đương.
- Rate limit theo account hint, source và tenant.
- Response body/status không tiết lộ trạng thái.
- Timing variance không có tương quan ổn định với bí mật.
- MFA/passkey và kiểm soát abuse hạn chế giá trị của một lần đoán.

Không dựa vào network noise như biện pháp bảo mật. Mạng có thể ổn định, attacker có thể ở gần server hoặc thu thập đủ nhiều mẫu để trung bình hóa nhiễu.

## 5. Làm cân bằng nhánh đăng nhập

Một cách phòng thủ phổ biến là thực hiện công việc có chi phí tương đương cho username không tồn tại và username tồn tại nhưng password sai.

Ví dụ, khi không tìm thấy account, server vẫn thực hiện password hash verification bằng một dummy verifier có cùng thuật toán và cấu hình cost với verifier thật. Kết quả dummy luôn bị từ chối.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A["Nhận username và password"] --> B["Chuẩn hóa định danh"]
    B --> C["Tìm account"]
    C --> D{"Có account?"}
    D -->|Có| E["Lấy password verifier thật"]
    D -->|Không| F["Dùng dummy verifier"]
    E --> G["Chạy password verification"]
    F --> G
    G --> H{"Account tồn tại và password đúng?"}
    H -->|Không| I["Generic authentication failure"]
    H -->|Có| J["Kiểm tra account state và MFA policy"]
~~~

Dummy verifier phải được tạo trước bằng cùng password hashing scheme và cost parameters. Không tạo dummy hash mới bằng thao tác ngẫu nhiên tốn thời gian ngay trong mỗi request nếu điều đó làm latency biến động hoặc tạo thêm tải.

### 5.1. Ví dụ pseudocode password verification

~~~ts
async function authenticate(accountName, suppliedPassword) {
  const normalized = normalizeAccountName(accountName);
  const account = await accounts.findByNormalizedName(normalized);

  const verifier = account?.passwordVerifier ?? DUMMY_PASSWORD_VERIFIER;
  const passwordMatches = await passwordHasher.verify(
    verifier,
    suppliedPassword
  );

  if (!account || !passwordMatches || account.status !== "active") {
    return genericLoginFailure();
  }

  return continueWithMfaOrSession(account);
}
~~~

Đây là pseudocode. DUMMY_PASSWORD_VERIFIER phải là verifier hợp lệ được tạo sẵn với thuật toán và cost tương đương verifier thật. Hàm verify phải xử lý format verifier an toàn. Không dùng một hash nhanh hoặc một chuỗi giả khiến nhánh account không tồn tại lại chạy nhanh hơn.

Việc cân bằng này không làm mọi request có thời gian giống hệt nhau. Database cache, account state, MFA và network vẫn tạo khác biệt. Mục tiêu là loại bỏ tín hiệu rõ ràng nhất gắn trực tiếp với việc account có tồn tại.

### 5.2. Kiểm tra account state sau password verification

Nếu account disabled hoặc locked, không nên trả lỗi sớm trước password verification nếu điều đó làm lộ trạng thái. Một số hệ thống có thể thực hiện verifier work tương đương trước khi trả generic failure.

Tuy nhiên, không nên cho phép account bị khóa thực hiện mọi side effect như account active. Việc chạy dummy/equivalent verification chỉ nhằm cân bằng observable work; policy vẫn phải từ chối session và không phát token.

## 6. Constant-time comparison

Khi so sánh các giá trị bí mật có độ dài cố định, thuật toán thông thường có thể dừng ngay tại byte đầu tiên khác nhau. Thời gian thực thi khi đó có thể phụ thuộc số byte khớp.

**Constant-time comparison** được thiết kế để thời gian so sánh không phụ thuộc vị trí khác biệt của dữ liệu bí mật trong giới hạn triển khai. Nó hữu ích cho:

- HMAC tag.
- MAC hoặc authenticator response đã được chuẩn hóa.
- Secret verifier có độ dài cố định.
- Một số phép so sánh cryptographic proof.

Ví dụ Node.js:

~~~ts
import { timingSafeEqual } from "node:crypto";

function equalMac(expected: Buffer, supplied: Buffer): boolean {
  if (expected.length !== supplied.length) {
    return false;
  }
  return timingSafeEqual(expected, supplied);
}
~~~

Hàm timingSafeEqual yêu cầu hai buffer có cùng độ dài. Cần kiểm tra định dạng và độ dài trước khi gọi; không tự viết vòng lặp so sánh secret trong ứng dụng nếu thư viện mật mã đáng tin đã cung cấp primitive phù hợp.

Constant-time comparison chỉ bảo vệ phép so sánh đó. Nó không làm toàn bộ endpoint constant-time, không che giấu database lookup, parsing, cache behavior, network latency hoặc các nhánh logic trước/sau phép so sánh.

### 6.1. Không dùng constant-time cho mọi dữ liệu

Không cần ép mọi phép so sánh trong hệ thống thành constant-time. Nên tập trung vào nơi thời gian có thể phụ thuộc dữ liệu bí mật và attacker có thể đo được. Việc sử dụng primitive đúng mục tiêu giúp giảm độ phức tạp và tránh tạo ra một tuyên bố bảo mật sai.

## 7. Timing trong MFA và OTP

OTP thường có không gian giá trị nhỏ. Nếu hệ thống trả kết quả hoặc thời gian khác nhau cho:

- Challenge không tồn tại.
- Challenge đã hết hạn.
- OTP sai.
- OTP đúng nhưng đã dùng.
- OTP đúng và đang chờ bước tiếp theo.

attacker có thể suy ra trạng thái challenge hoặc factor.

Biện pháp:

1. Dùng response chung cho các trường hợp không xác minh được trước khi người dùng được xác thực.
2. Gắn OTP với challenge, purpose, principal và thời hạn.
3. Giới hạn số lần thử theo challenge và account.
4. Tiêu thụ OTP thành công bằng thao tác nguyên tử.
5. Tránh trả khác biệt rõ ràng giữa challenge không tồn tại và challenge có nhưng OTP sai.
6. Không tạo challenge vô hạn để attacker có thêm lượt đoán.
7. Không log OTP hoặc secret TOTP.

Với TOTP, phép kiểm tra mã có thể thử một số time step cho phép. Cần tránh trả response khác nhau cho mã khớp ở time step trước, hiện tại hoặc kế tiếp nếu điều đó tiết lộ thông tin thời gian hoặc trạng thái. Cửa sổ cho phép phải nhỏ và replay phải bị chặn.

## 8. Timing trong password reset và account recovery

Các endpoint reset/recovery thường có thể bị dùng để dò email, số điện thoại hoặc trạng thái tài khoản.

Ví dụ: request reset cho email không tồn tại trả ngay; request cho email tồn tại tạo token, ghi database và gửi email nên mất lâu hơn. Attacker có thể phân biệt người dùng có tài khoản.

Kiểm soát:

- Dùng thông báo chung như “Nếu địa chỉ này phù hợp với tài khoản, chúng tôi sẽ gửi hướng dẫn qua kênh đã đăng ký”.
- Thực hiện công việc nền qua queue sau khi ghi nhận request hợp lệ, để response không phụ thuộc hoàn toàn vào việc gửi email.
- Cân bằng các thao tác lookup và validation quan trọng giữa nhánh có/không có account.
- Rate limit cả account hint không tồn tại.
- Không tiết lộ số factor, số recovery code còn lại hoặc trạng thái tài khoản.
- Không tạo reset token hoặc side effect cho account không tồn tại.
- Dùng token ngẫu nhiên, ngắn hạn, purpose-bound và one-time.

Đưa email delivery sang queue có thể giảm khác biệt timing của HTTP response, nhưng không tự bảo đảm an toàn. Queue enqueue, database lookup và response size vẫn có thể tạo side-channel; cần đánh giá cả đường xử lý.

## 9. Timing trong federation và OAuth/OIDC

Federation có thể làm lộ thông tin qua redirect, lỗi callback hoặc token endpoint:

- Unknown user có thể bị từ chối nhanh hơn user hợp lệ cần thực hiện MFA.
- Client ID không tồn tại có thể trả lỗi khác client bị disable.
- Authorization code sai có thể dừng trước khi kiểm tra code hợp lệ.
- Refresh token bị revoke có thể tạo nhánh khác với token hết hạn.
- User consent hoặc account linking có thể làm thay đổi thời gian và response.

Các biện pháp:

- Dùng lỗi giao thức chung khi thông tin không được phép tiết lộ cho caller.
- Không hiển thị chi tiết về account, issuer hoặc factor trong URL/error page công khai.
- Không để redirect URI hoặc callback response trở thành oracle cho trạng thái tài khoản.
- Rate limit các endpoint authorization, token, device code và recovery.
- Bảo vệ state, nonce, PKCE và correlation để callback không thể bị tráo.
- Ghi lý do chi tiết trong audit nội bộ, không trả toàn bộ lý do cho browser.

Không thay đổi tùy tiện response theo chuẩn OAuth/OIDC chỉ để làm timing giống nhau. Cần giữ đúng semantics của protocol, đồng thời giảm thông tin nhạy cảm và bảo vệ endpoint khỏi enumeration.

## 10. Timing trong API key, HMAC và token validation

Với API key hoặc HMAC authentication, phép so sánh secret cần dùng constant-time primitive phù hợp. Trước đó, server vẫn có thể bị lộ timing qua lookup key ID hoặc trạng thái key.

Ví dụ, key ID không tồn tại trả lỗi ngay trong khi key ID tồn tại nhưng secret sai phải tính HMAC. Attacker có thể dò key ID hợp lệ. Nếu key ID không được xem là bí mật thì việc lộ nó có thể chấp nhận được; nếu key ID hoặc trạng thái client nhạy cảm, cần cân bằng nhánh và rate limit.

Với token validation:

- Chỉ chấp nhận thuật toán trong allowlist.
- Xác minh chữ ký trước khi tin claim.
- Dùng key/issuer từ cấu hình tin cậy, không fetch URL tùy ý từ token.
- Trả lỗi chung cho caller khi token không hợp lệ.
- Không để thời gian xác minh tiết lộ key nội bộ hoặc trạng thái user vượt quá nhu cầu vận hành.
- Không bỏ qua kiểm tra chữ ký để làm response nhanh hơn.

Không nên thêm delay lớn cho mọi token lỗi. Hãy dùng verifier đúng chuẩn, cache key an toàn và rate limit để kiểm soát tải.

## 11. Response shaping: body, status, header và redirect

Đánh giá timing cần đi cùng các thuộc tính response khác:

| Thuộc tính | Câu hỏi cần kiểm tra |
| --- | --- |
| HTTP status | Tài khoản tồn tại và không tồn tại có status khác nhau không? |
| Response body | Message, error code hoặc JSON field có tiết lộ trạng thái không? |
| Content length | Một nhánh có thêm field hoặc dữ liệu khác biệt không? |
| Headers | Có header như Retry-After, challenge hoặc redirect khác nhau không? |
| Redirect | Location có chỉ ra account state, issuer hoặc factor không? |
| Cookies | Nhánh lỗi có vô tình đặt session/pre-auth cookie khác nhau không? |
| Timing | Phân phối latency có phân biệt được theo trạng thái bí mật không? |

Không nhất thiết mọi response phải giống từng byte. Một số khác biệt là cần thiết cho protocol hoặc trải nghiệm. Cần xác định dữ liệu nào được phép công khai, dữ liệu nào chỉ được trả sau authentication, và liệu khác biệt có tạo oracle hữu ích cho attacker không.

## 12. Timing equalization và random delay

Một số hệ thống thêm delay hoặc dùng response time bucket để giảm khác biệt dễ quan sát. Cần thận trọng:

- **Equalized work:** làm cho nhánh nhạy cảm thực hiện chi phí tính toán tương đương. Đây thường là biện pháp trực tiếp hơn.
- **Minimum response time:** đảm bảo response không trả trước một mốc tối thiểu. Có thể che chênh lệch nhỏ nhưng tăng latency và có thể bị trung bình hóa.
- **Random jitter:** thêm biến thiên ngẫu nhiên để làm nhiễu phép đo. Attacker có thể gửi nhiều mẫu để giảm ảnh hưởng của nhiễu.
- **Asynchronous processing:** tách side effect như gửi email khỏi response request. Cần bảo vệ queue và các bước lookup trước enqueue.

Không dựa vào random delay như kiểm soát chính. Nếu nhánh A luôn mất 20 ms và nhánh B luôn mất 300 ms, thêm jitter 0–30 ms không che được chênh lệch. Nếu thêm delay cố định lớn cho mọi request, hệ thống có thể bị lợi dụng để giữ connection và gây denial of service.

Ưu tiên loại bỏ khác biệt công việc gắn trực tiếp với bí mật, sau đó đo lại response distribution. Chỉ dùng delay/bucketing khi có threat model, latency budget và đánh giá tác động.

## 13. Database, cache và các nguồn timing khác

Ngay cả khi password verification được cân bằng, database và cache có thể tạo khác biệt:

- Account tồn tại có record nóng trong cache; account không tồn tại gây database miss.
- Một nhánh truy vấn nhiều bảng hoặc join hơn.
- Cache hit và cache miss có latency khác nhau.
- Lock contention xảy ra khi cập nhật failed-login counter.
- Gửi email/SMS đồng bộ chỉ xảy ra với account tồn tại.
- Một nhánh gọi risk engine hoặc MFA provider, nhánh khác không gọi.

Biện pháp:

- Tránh thực hiện side effect đồng bộ không cần thiết trong đường trả response.
- Cân nhắc query shape tương đương cho lookup nhạy cảm.
- Giới hạn thông tin có thể quan sát từ cache key và response.
- Dùng queue/outbox cho tác vụ nền có side effect.
- Đo latency theo từng stage để tìm nguồn chênh lệch.
- Không cache dữ liệu nhạy cảm lâu chỉ để làm timing giống nhau.

Không thể và không cần loại bỏ mọi khác biệt hiệu năng. Mục tiêu là giảm những khác biệt có tương quan rõ với trạng thái bí mật và có thể bị khai thác từ xa.

## 14. Đo lường và kiểm thử timing side-channel

Một lần đo không đủ để kết luận. Cần thu thập nhiều mẫu trong điều kiện tương đương:

1. Tạo tập input đại diện cho account tồn tại/không tồn tại, password sai, account disabled và factor khác nhau.
2. Gửi request từ cùng vị trí mạng và cùng cấu hình client.
3. Xen kẽ các nhóm input để giảm ảnh hưởng tải hệ thống thay đổi theo thời gian.
4. Thu thập latency end-to-end và nếu có thể, latency theo stage ở môi trường test.
5. So sánh median, percentile, variance và phân phối thay vì chỉ so sánh trung bình.
6. Kiểm tra response status, body size, headers và redirect cùng với timing.
7. Lặp lại ở tải bình thường và tải gần giới hạn.
8. Xác định khác biệt có ổn định, có ý nghĩa và có thể phân loại trạng thái bí mật hay không.

Các kỹ thuật thống kê như Mann–Whitney U hoặc kiểm định phân phối có thể giúp phát hiện khác biệt giữa hai nhóm. Tuy nhiên, ý nghĩa thống kê không tự động chứng minh khai thác thực tế; cần xem số mẫu attacker có thể lấy, rate limit, latency noise và mức nhạy cảm của thông tin lộ.

Không chạy thử nghiệm tải hoặc enumeration trên tài khoản thật khi chưa có phê duyệt. Dùng dữ liệu synthetic và môi trường staging để đo chính xác.

### 14.1. Test matrix mẫu

| Nhóm | Input | Kỳ vọng |
| --- | --- | --- |
| A | Username không tồn tại | Generic failure; work tương đương nhánh password sai. |
| B | Username tồn tại, password sai | Generic failure; không có timing gap lớn, ổn định. |
| C | Account disabled, password sai | Không tiết lộ trạng thái disabled trước xác thực. |
| D | Account active, password đúng, MFA required | Chuyển sang MFA theo policy, không phát session hoàn chỉnh trước khi factor xong. |
| E | Recovery account không tồn tại | Response không làm lộ account enumeration. |
| F | Recovery account tồn tại | Message/status tương đương; email được xử lý qua queue. |
| G | API key ID không tồn tại | Không tạo oracle nhạy cảm; quota áp dụng. |
| H | API key ID tồn tại, secret sai | Constant-time secret compare; response chung. |

## 15. Logging, privacy và audit

Log hỗ trợ điều tra nhưng có thể tạo thêm rò rỉ:

- Không log password, OTP, recovery code, API key, bearer token, authorization code hoặc session cookie.
- Không log hash password hoặc verifier có thể bị dùng để kiểm tra password offline.
- Tránh ghi email/username đầy đủ trong telemetry nếu HMAC/pseudonymous identifier đáp ứng mục đích.
- Không đưa chi tiết như “user tồn tại nhưng bị khóa” vào log mà người dùng hoặc client không có quyền đọc.
- Ghi error category nội bộ, request ID, tenant và timestamp theo quyền truy cập phù hợp.
- Hạn chế quyền truy cập log và đặt retention theo mục đích.

Audit nội bộ có thể ghi lý do chính xác để hỗ trợ security operations. Response công khai nên chỉ chứa thông tin cần thiết cho người dùng. Phải giữ ranh giới rõ giữa log nội bộ và thông báo client.

## 16. Ví dụ: password reset không tiết lộ email đã đăng ký

Một trang quên mật khẩu nhận email và luôn hiển thị:

“Nếu địa chỉ này phù hợp với một tài khoản, chúng tôi sẽ gửi hướng dẫn qua kênh đã đăng ký.”

Để giảm timing side-channel:

1. Chuẩn hóa email theo quy tắc đăng nhập.
2. Thực hiện lookup có kiểm soát và áp dụng quota kể cả khi không tìm thấy account.
3. Nếu account tồn tại và đủ điều kiện, tạo reset request/token ngẫu nhiên, lưu verifier và ghi event vào outbox.
4. Worker gửi email bất đồng bộ qua kênh đã đăng ký.
5. Request HTTP trả cùng status/body và không chờ email provider.
6. Nếu account không tồn tại, không tạo reset token; ghi metric không chứa email thô.
7. Đo lại latency giữa hai nhóm để xác định lookup/outbox còn tạo chênh lệch có thể khai thác hay không.

Tách email delivery khỏi response giảm chênh lệch lớn do provider, nhưng vẫn phải kiểm tra database, queue và cache timing. Generic message không thay thế rate limiting và abuse monitoring.

## 17. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cùng message nhưng nhánh account miss trả nhanh hơn nhiều | Attacker enumerate account bằng timing. | Dùng dummy password verifier và cân bằng công việc nhạy cảm. |
| Password hash chỉ chạy khi account tồn tại | Timing trực tiếp tiết lộ username hợp lệ. | Chạy verifier dummy với cùng scheme/cost. |
| So sánh HMAC bằng phép so sánh dừng ở byte khác đầu tiên | Timing có thể tiết lộ prefix khớp. | Dùng constant-time primitive cho giá trị cùng độ dài. |
| Thêm random delay và coi như đã an toàn | Attacker lấy nhiều mẫu để trung bình hóa nhiễu. | Loại bỏ chênh lệch work; jitter chỉ là lớp phụ. |
| Gửi email reset đồng bộ | Latency tiết lộ account tồn tại và phụ thuộc mail provider. | Dùng outbox/queue và response chung. |
| Trả lỗi riêng cho account locked/disabled | Lộ trạng thái tài khoản. | Generic response trước authentication; audit chi tiết nội bộ. |
| Bỏ qua status/header/content length | Enumeration vẫn qua response metadata. | Kiểm tra toàn bộ observable response. |
| Constant-time comparison cho toàn bộ endpoint bị hiểu sai | Tạo cảm giác an toàn giả; các nhánh khác vẫn khác thời gian. | Áp dụng primitive đúng chỗ và đo toàn flow. |
| Thêm delay cố định quá lớn | Tăng latency và dễ bị khai thác DoS. | Dùng equalized work và latency budget. |
| Không rate limit endpoint enumeration | Attacker thu thập đủ mẫu để phân loại. | Quota theo principal hint, source, tenant và global. |
| Không đo lại sau thay đổi | Side-channel khác vẫn tồn tại qua cache/DB/dependency. | Test matrix và phân tích phân phối định kỳ. |
| Log secret hoặc verifier trong lúc debug | Tạo rò rỉ credential mới. | Redaction, pseudonymous identifiers và log access control. |

## 18. Checklist giảm rò rỉ qua error timing

Trước khi đưa authentication endpoint vào production, hãy kiểm tra:

1. Username không tồn tại và password sai có response công khai tương đương không?
2. Nhánh account không tồn tại có chạy dummy password verification với cùng thuật toán/cost không?
3. Account locked/disabled có bị tiết lộ trước khi xác minh danh tính không?
4. So sánh MAC/HMAC/secret có dùng constant-time primitive phù hợp không?
5. Có kiểm tra độ dài và định dạng trước constant-time comparison không?
6. MFA, OTP, password reset và recovery có tránh timing oracle về challenge/account state không?
7. OAuth/federation callback có tránh lộ trạng thái user, factor và token qua timing/redirect không?
8. Response status, body, content length, header, cookie và redirect có được kiểm tra không?
9. Email/SMS và side effect chậm có được tách khỏi request path khi phù hợp không?
10. Có rate limit và abuse monitoring để giới hạn số mẫu attacker thu thập không?
11. Có đo phân phối latency theo nhóm input bằng dữ liệu synthetic và môi trường được phép không?
12. Có xem xét cache hit/miss, database lookup, lock contention và dependency latency không?
13. Random jitter hoặc minimum delay có được coi là lớp phụ, không phải biện pháp duy nhất không?
14. Log có tránh password, OTP, recovery code, token, cookie và verifier không?
15. Có kiểm thử lại sau thay đổi password hashing cost, cache, database, MFA hoặc provider không?

**Kết luận:** Error timing có thể trở thành timing side-channel làm lộ sự tồn tại tài khoản, trạng thái credential hoặc tiến trình xác minh dù response message giống nhau. Cần cân bằng công việc ở các nhánh nhạy cảm, dùng dummy password verifier, constant-time comparison cho secret phù hợp, response shaping, rate limiting và kiểm thử phân phối latency. Random delay đơn lẻ không đủ vì attacker có thể lấy nhiều mẫu; cũng không nên thêm độ trễ lớn gây ảnh hưởng availability. Hãy đo toàn bộ flow và chỉ giữ những khác biệt timing cần thiết, không tiết lộ thông tin riêng tư.
