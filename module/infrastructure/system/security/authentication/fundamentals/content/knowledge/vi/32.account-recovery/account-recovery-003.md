# Recovery code

## 1. Recovery code là gì?

**Recovery code (mã khôi phục)** là một bí mật dự phòng được tạo trước và cấp cho người dùng để họ có thể khôi phục quyền truy cập khi mất hoặc không sử dụng được phương thức xác thực chính. Mã thường được tạo trong lúc người dùng đăng ký MFA, passkey hoặc một phương thức xác thực quan trọng khác.

Ví dụ: người dùng bật xác thực đa yếu tố bằng ứng dụng TOTP và được cấp một tập gồm nhiều recovery code. Khi điện thoại bị mất, họ có thể dùng một mã chưa từng sử dụng để chứng minh quyền truy cập theo quy trình recovery đã thiết kế. Sau khi mã được chấp nhận, mã đó phải bị tiêu thụ và không được dùng lại.

Recovery code thường là **bí mật bearer dùng một lần**: ai có mã hợp lệ và vượt qua các kiểm tra còn lại của quy trình có thể sử dụng mã đó. Vì vậy, mã cần được tạo ngẫu nhiên với entropy đủ lớn, chỉ hiển thị an toàn khi phát hành, lưu verifier thay vì plaintext và được thu hồi ngay sau khi dùng.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, recovery code là một phần của vòng đời credential và account recovery. Nó giúp người dùng không bị khóa tài khoản khi mất authenticator, nhưng cũng tạo một con đường thay thế mà attacker có thể nhắm tới. Hệ thống cần bảo vệ cả việc cấp, lưu, sử dụng, thu hồi và thay mới mã.

## 2. Recovery code giải quyết vấn đề nào?

Một tài khoản có thể dùng passkey, security key, TOTP hoặc push approval. Nếu tất cả phương thức đều nằm trên một thiết bị và thiết bị đó bị mất, người dùng có thể không còn cách đăng nhập.

Recovery code cung cấp một phương thức dự phòng độc lập với authenticator chính:

- Người dùng có thể lưu mã ở một nơi an toàn khác với điện thoại hoặc security key.
- Mỗi mã có thể dùng một lần, nên việc sử dụng không tạo ra một bí mật dùng lặp vô thời hạn.
- Mã được tạo trước sự cố, giúp tránh phải hạ thấp kiểm tra danh tính khi người dùng đang mất quyền truy cập.
- Một tập nhiều mã cho phép khôi phục trong nhiều tình huống cho tới khi người dùng tạo bộ mã mới.

Recovery code không tự giải quyết mọi vấn đề recovery. Nếu người dùng mất cả thiết bị lẫn mã dự phòng, họ vẫn cần một quy trình proofing hoặc hỗ trợ có bảo đảm phù hợp. Mã cũng không chứng minh danh tính dân sự; nó chỉ chứng minh người yêu cầu đang kiểm soát một bí mật đã được cấp cho tài khoản.

## 3. Phân biệt recovery code với các loại mã khác

Tên gọi “code” xuất hiện trong nhiều quy trình nhưng mục đích và vòng đời khác nhau:

| Loại mã | Mục đích | Vòng đời điển hình |
| --- | --- | --- |
| **Recovery code** | Khôi phục quyền truy cập khi mất phương thức xác thực chính. | Tạo trước, thường dùng một lần, có thể tồn tại tới khi dùng hoặc bị thu hồi. |
| **TOTP** | Xác thực bằng mã thay đổi theo thời gian từ secret đã đăng ký. | Mã ngắn hạn, thường đổi theo chu kỳ. |
| **Email/SMS verification code** | Xác minh quyền kiểm soát một kênh liên hệ hoặc một bước cụ thể. | Ngắn hạn, gắn với một challenge. |
| **Password reset token** | Cho phép đặt lại mật khẩu sau khi vượt qua quy trình recovery. | Ngắn hạn, dùng một lần, gắn với yêu cầu reset. |
| **Enrollment challenge** | Hoàn tất đăng ký authenticator mới. | Gắn với một flow đăng ký, hết hạn và dùng một lần. |
| **Transaction approval code** | Xác nhận một thao tác hoặc giao dịch cụ thể. | Gắn với nội dung giao dịch và một lần thực hiện. |

Không dùng recovery code như một OTP có thời hạn nếu hệ thống không thiết kế như vậy. Không dùng mã recovery để xác nhận giao dịch hoặc để chứng minh người dùng đã nhìn thấy nội dung giao dịch. Nó chỉ là một bằng chứng dự phòng trong luồng khôi phục tài khoản.

## 4. Recovery code không phải yếu tố chống phishing

Recovery code là bí mật có thể bị sao chép và nhập lại. Nó không tự ràng buộc với origin, RP ID, thiết bị hoặc nội dung request như WebAuthn/passkey. Nếu người dùng nhập mã vào trang giả, attacker có thể lấy mã và sử dụng trước chủ tài khoản.

Một mã đã được tiêu thụ không được chấp nhận lần thứ hai, nên one-time use giúp giảm replay sau lần dùng đầu. Tuy nhiên, attacker có thể đánh cắp và sử dụng mã trước nạn nhân. Vì thế:

- Không quảng bá recovery code là phương thức phishing-resistant.
- Chỉ nhập mã trên website/app chính thức, trong flow recovery do người dùng chủ động bắt đầu.
- Không gửi mã qua email, chat, cuộc gọi hoặc cho nhân viên hỗ trợ.
- Không yêu cầu người dùng đọc mã cho người khác để “xác minh tài khoản”.
- Bảo vệ trang recovery khỏi phishing, open redirect, CSRF và session substitution.
- Khi mã được sử dụng, thông báo cho người dùng qua kênh liên hệ đã xác minh.

Nếu tổ chức cần phương thức dự phòng chống phishing, nên cân nhắc security key/passkey thứ hai hoặc một phương thức có mức bảo đảm tương đương. Recovery code vẫn có thể là lựa chọn cuối cùng với policy chặt chẽ.

## 5. Tạo recovery code an toàn

Recovery code phải được sinh bằng **cryptographically secure pseudorandom number generator (CSPRNG)**. Không dùng thời gian, user ID, số thứ tự, email, mã ngẫu nhiên yếu hoặc giá trị do client tự chọn.

Một thiết kế tham khảo:

- Mỗi code chứa ít nhất 128 bit entropy ngẫu nhiên.
- Mỗi code trong cùng một bộ là độc lập và không trùng nhau.
- Mã được biểu diễn ở dạng dễ nhập, ví dụ Base64URL hoặc Base32 theo quy ước của hệ thống.
- Có thể chia mã thành nhóm ký tự để dễ đọc; dấu phân cách không tham gia vào bí mật sau bước chuẩn hóa.
- Mỗi mã có một định danh riêng để quản lý trạng thái đã dùng hoặc bị thu hồi.

Ví dụ Node.js tạo mã 128 bit:

~~~ts
import { randomBytes } from "node:crypto";

function generateRecoveryCode(): string {
  return randomBytes(16).toString("base64url");
}

const recoveryCodes = Array.from({ length: 10 }, generateRecoveryCode);
~~~

16 byte ngẫu nhiên tương đương 128 bit entropy trước khi mã hóa. Ví dụ này minh họa cách sinh; hệ thống thực tế cần quy định format, chuẩn hóa, số lượng code, kiểm tra uniqueness và xử lý lưu trữ an toàn.

Không dùng `Math.random()`, UUID dạng không có entropy phù hợp, timestamp hoặc mã tuần tự. Nếu dùng mã ngắn hơn để dễ nhập, phải tính entropy thực tế, giới hạn thử nghiêm ngặt và đánh giá nguy cơ đoán trực tuyến. Không được hy sinh độ khó đoán mà không có kiểm soát bù đắp.

### 5.1. Số lượng mã và entropy

Một tập gồm nhiều mã giúp người dùng có phương án dự phòng trong nhiều lần mất thiết bị. Mỗi mã phải có entropy độc lập; không sinh mã sau bằng cách tăng số từ mã trước.

Số lượng mã cần cân bằng giữa khả năng recovery và bề mặt tấn công. Càng nhiều mã còn hiệu lực thì càng có nhiều bí mật có thể bị đánh cắp. Hệ thống có thể phát hành một số lượng vừa đủ, cho phép tạo bộ mới sau khi người dùng xác thực thành công và thu hồi bộ cũ theo policy.

### 5.2. Chuẩn hóa định dạng

Nếu cho phép người dùng nhập mã có dấu gạch nối hoặc chữ thường, server cần chuẩn hóa theo quy tắc cố định:

1. Loại bỏ đúng các dấu phân cách đã quy định.
2. Chuẩn hóa chữ hoa/thường nếu format không phân biệt hoa thường.
3. Từ chối ký tự ngoài bảng ký tự hợp lệ.
4. Kiểm tra độ dài trước khi truy vấn verifier.
5. Không tự động sửa ký tự mơ hồ theo nhiều cách có thể tạo ra cùng một mã.

Chuẩn hóa không được làm giảm entropy hoặc khiến hai mã khác nhau trở thành cùng một giá trị.

## 6. Hiển thị và bàn giao mã cho người dùng

Recovery code thường chỉ nên hiển thị một lần ngay sau khi tạo. Người dùng cần được hướng dẫn lưu chúng ở nơi có thể truy cập khi mất thiết bị chính nhưng vẫn được bảo vệ khỏi người khác.

Các lựa chọn lưu trữ phù hợp có thể gồm:

- Password manager có bảo vệ mạnh và đồng bộ an toàn.
- Bản in cất ở nơi khóa được, tách khỏi thiết bị xác thực chính.
- Kho lưu trữ mã hóa do tổ chức quản lý, nếu có chính sách và phân quyền phù hợp.
- Một phương tiện backup vật lý được bảo vệ khỏi truy cập trái phép.

Không nên:

- Gửi recovery code qua email hoặc SMS như một bản sao tiện lợi.
- Lưu ảnh chụp màn hình trong thư viện ảnh đồng bộ không kiểm soát.
- Đưa mã vào ghi chú plaintext, ticket hỗ trợ, chat hoặc tài liệu chia sẻ.
- Lưu mã trên cùng thiết bị duy nhất có authenticator chính mà không có lớp bảo vệ khác.
- Chụp ảnh hoặc ghi màn hình mã trong lúc hiển thị.

Giao diện nên nói rõ đây là bí mật dùng một lần, không chia sẻ với bất kỳ ai và không thể xem lại sau khi đóng. Nếu người dùng chưa lưu mã, có thể cho phép tạo lại một bộ mới sau khi xác thực lại và thu hồi bộ cũ theo policy.

### 6.1. Không gửi lại mã cũ

Vì server không nên lưu plaintext recovery code, hệ thống không thể gửi lại mã cũ khi người dùng quên nơi lưu. Nếu người dùng còn đăng nhập bằng phương thức mạnh khác, họ có thể xác thực lại và tạo bộ mới. Nếu không, cần đi qua recovery proofing hoặc hỗ trợ đã được phê duyệt.

Không tạo tính năng “hiển thị lại recovery code” bằng cách lưu plaintext hoặc mã hóa có thể giải ngược chỉ để tiện hỗ trợ. Điều đó biến kho recovery thành mục tiêu có giá trị cao.

## 7. Lưu verifier thay vì plaintext

Server cần xác minh mã được nhập mà không giữ bản rõ trong database. Có thể lưu một verifier được tính từ code, gắn với tài khoản và bộ mã.

Vì recovery code được tạo ngẫu nhiên với entropy cao, một hàm băm mật mã hoặc HMAC có khóa phía server có thể phù hợp. HMAC với pepper/key được giữ trong KMS hoặc secret manager giúp giảm nguy cơ database dump có thể dùng trực tiếp để kiểm tra code offline nếu khóa không bị lộ cùng database.

Một bản ghi khái niệm:

| Trường | Ý nghĩa |
| --- | --- |
| `codeId` | Định danh bản ghi của một recovery code. |
| `principalId` / `tenantId` | Chủ tài khoản và tổ chức. |
| `setId` | Bộ recovery code được phát hành cùng nhau. |
| `verifier` | HMAC/hash của code đã chuẩn hóa, không phải plaintext. |
| `keyVersion` | Phiên bản pepper/KMS key dùng để tạo verifier. |
| `createdAt` | Thời điểm phát hành. |
| `usedAt` | Thời điểm code được tiêu thụ nếu đã dùng. |
| `revokedAt` | Thời điểm code hoặc bộ mã bị thu hồi. |

Nếu dùng HMAC, key phải được quản lý riêng khỏi database, có quy trình rotation và key version. Nếu dùng hash không khóa, cần đảm bảo code có entropy cao và không dùng mã ngắn dễ brute force offline. Với mã do con người tự chọn hoặc có entropy thấp, cần thiết kế verifier phù hợp hơn và đánh giá kỹ nguy cơ offline guessing.

Không ghi plaintext recovery code vào database, cache, analytics, application log, audit log hoặc telemetry. Tránh đưa mã vào exception message và tracing span.

## 8. Xác minh và tiêu thụ recovery code

Một luồng recovery an toàn có thể gồm:

1. Người dùng chủ động mở trang recovery chính thức.
2. Server tạo recovery transaction có thời hạn ngắn, gắn với principal/account hint, tenant, browser session và mục đích.
3. Người dùng nhập một recovery code.
4. Server chuẩn hóa định dạng, kiểm tra rate limit và tìm verifier thuộc đúng tài khoản.
5. Server xác minh code bằng verifier đã lưu.
6. Server **tiêu thụ code một cách nguyên tử**: chỉ một request được chuyển code từ chưa dùng sang đã dùng.
7. Server áp dụng policy recovery: xác minh rủi ro, thu hồi session/token nếu cần và yêu cầu thiết lập lại phương thức xác thực.
8. Server thông báo cho người dùng và ghi audit event không chứa code.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant R as Recovery service
    participant D as Credential database
    participant P as Policy / risk engine
    U->>B: Mở recovery flow chính thức
    B->>R: Bắt đầu recovery transaction
    R-->>B: Challenge ngắn hạn
    U->>B: Nhập recovery code
    B->>R: Code + transaction ID
    R->>R: Chuẩn hóa, rate limit và xác minh verifier
    R->>D: Consume code nếu chưa dùng (atomic)
    D-->>R: Thành công hoặc đã dùng
    R->>P: Đánh giá recovery và hành động tiếp theo
    P-->>R: Cho phép theo policy hoặc chuyển review
    R-->>B: Kết quả và hướng dẫn an toàn
~~~

Code đúng là bằng chứng để tiếp tục quy trình recovery, không nhất thiết là điều kiện đủ để mở toàn bộ tài khoản. Ví dụ, tài khoản đặc quyền hoặc có dấu hiệu bị chiếm có thể cần thêm xác minh, thời gian chờ, phê duyệt hoặc thông báo bảo mật.

## 9. One-time use và tính nguyên tử

Recovery code phải được tiêu thụ một lần. Một lỗi phổ biến là kiểm tra code chưa dùng rồi cập nhật sau bằng hai thao tác riêng:

~~~text
if code.used_at is null:
    verify(code)
    update code.used_at
    accept()
~~~

Hai request đồng thời có thể cùng đọc `used_at = null` và cùng được chấp nhận. Điều này phá vỡ one-time use.

Thay vào đó, server phải dùng transaction, row lock, compare-and-swap hoặc câu lệnh cập nhật có điều kiện để chỉ một request thành công:

~~~sql
UPDATE recovery_codes
SET used_at = CURRENT_TIMESTAMP
WHERE code_id = :code_id
  AND principal_id = :principal_id
  AND used_at IS NULL
  AND revoked_at IS NULL;
~~~

Chỉ chấp nhận nếu đúng một bản ghi được cập nhật và verifier đã được xác minh. Trong hệ thống nhiều node, thao tác này phải dựa trên kho trạng thái có tính nhất quán phù hợp; cache cục bộ không đủ để bảo đảm one-time use toàn hệ thống.

Nếu bước consume thành công nhưng bước tạo recovery session bị lỗi, không nên làm sống lại code đã dùng. Có thể lưu trạng thái recovery transaction và cho phép tiếp tục hoàn tất một cách idempotent sau khi retry, hoặc chuyển sang hỗ trợ có kiểm soát.

## 10. Rate limit và chống đoán mã

Recovery endpoint là mục tiêu có giá trị vì nó có thể giúp attacker vượt qua MFA. Cần áp dụng giới hạn theo nhiều chiều:

- Theo principal/account, kể cả khi account hint chưa được xác minh.
- Theo IP/network và thiết bị ở mức tín hiệu rủi ro.
- Theo recovery transaction và khoảng thời gian.
- Theo tenant hoặc client nếu endpoint được dùng chung.
- Theo số lần phát hành lại hoặc yêu cầu tạo bộ mã mới.

Không nên chỉ rate limit theo IP vì attacker có thể phân tán request. Cũng không nên khóa vĩnh viễn tài khoản chỉ sau vài lần nhập sai, vì attacker có thể cố tình gây denial of service cho nạn nhân. Có thể dùng cooldown tăng dần, challenge bổ sung, risk review và thông báo phù hợp.

Phản hồi lỗi nên chung chung, ví dụ “Không thể xác minh mã này hoặc mã không còn khả dụng”. Không tiết lộ số mã còn lại, mã có tồn tại hay không, hoặc account hint có khớp không trước khi người dùng được xác minh ở mức phù hợp.

## 11. Thu hồi và xoay bộ recovery code

Một bộ mã có thể gồm nhiều code độc lập. Khi một code được sử dụng, tối thiểu phải đánh dấu code đó đã dùng. Policy có thể giữ các code chưa dùng để hỗ trợ lần recovery tiếp theo, nhưng cần đánh giá nguy cơ bộ mã đã bị sao chép.

Các tình huống nên thu hồi toàn bộ bộ mã còn lại và phát hành bộ mới sau khi xác minh:

- Người dùng nghi ngờ bản in hoặc password manager đã bị lộ.
- Thiết bị hoặc tài khoản lưu trữ mã bị xâm nhập.
- Một recovery code được sử dụng trong sự kiện bất thường.
- Người dùng vừa hoàn tất account recovery sau khi mất thiết bị.
- Quản trị viên/security team yêu cầu rotate theo incident policy.

Khi phát hành bộ mới:

1. Xác minh người dùng bằng phương thức đang tin cậy hoặc recovery flow đã được phê duyệt.
2. Tạo `setId` mới và các code ngẫu nhiên mới.
3. Lưu verifier mới, không lưu plaintext.
4. Thu hồi toàn bộ code còn hiệu lực thuộc bộ cũ trong cùng giao dịch hoặc quy trình nhất quán.
5. Hiển thị bộ mới một lần và yêu cầu người dùng lưu an toàn.
6. Gửi thông báo về việc bộ mã đã được thay mới.

Không phát hành thêm bộ mới mà vẫn để nhiều bộ cũ cùng hoạt động vô thời hạn, trừ khi policy có lý do rõ ràng và quản lý được tổng số mã còn hiệu lực.

## 12. Recovery code và các bước sau khi khôi phục tài khoản

Sử dụng recovery code không nên kết thúc quy trình ngay tại thời điểm xác minh mã. Hệ thống cần quyết định trạng thái tài khoản và phương thức xác thực sau recovery.

Một quy trình thường gồm:

1. Tiêu thụ recovery code.
2. Kiểm tra account status, risk signals và sự kiện bảo mật gần đây.
3. Thu hồi session đáng ngờ hoặc mọi session nếu có khả năng chiếm tài khoản.
4. Thu hồi refresh token/grant liên quan khi cần; xem xét access token còn hiệu lực.
5. Yêu cầu đăng ký passkey/security key hoặc authenticator mới.
6. Kiểm tra và thay recovery code còn lại nếu bộ mã có thể bị lộ.
7. Kiểm tra email/số điện thoại recovery và các enrollment vừa được thêm.
8. Thông báo qua kênh liên hệ đã xác minh.
9. Ghi audit event và có thể áp dụng thời gian chờ trước một số thay đổi nhạy cảm.

Recovery code không được dùng để bỏ qua trạng thái tài khoản bị khóa do gian lận, lệnh quản trị hoặc điều tra bảo mật. Nếu tài khoản bị suspended, policy đó vẫn phải được thực thi.

## 13. Quyền riêng tư và audit

Audit event nên ghi nhận:

- Principal/tenant và recovery transaction ID.
- Code ID hoặc set ID dạng định danh nội bộ, không ghi code plaintext.
- Thời điểm thử, kết quả và trạng thái tiêu thụ.
- Tác nhân hoặc kênh yêu cầu.
- Policy decision và hành động downstream như revoke session hoặc enroll factor mới.
- Request/correlation ID để điều tra.

Không ghi recovery code vào log, URL, query string, analytics, crash report, support ticket hoặc email. Không lưu ảnh chụp mã trong hồ sơ người dùng.

Thông báo sau khi dùng mã cần cho biết recovery đã được bắt đầu hoặc hoàn tất, và hướng dẫn liên hệ nếu người dùng không thực hiện. Tránh tiết lộ thông tin về số lượng code còn lại hoặc các factor khác chưa được xác minh.

## 14. Ví dụ thiết kế: người dùng mất điện thoại

Một người dùng đã bật passkey và TOTP trên điện thoại. Khi thiết lập MFA, họ đã tải một tập recovery code và lưu trong password manager. Sau đó điện thoại bị mất.

**Luồng khôi phục:**

1. Người dùng mở website chính thức và chọn “Không còn truy cập authenticator”.
2. Server tạo recovery transaction ngắn hạn và ràng buộc với browser session.
3. Người dùng lấy một mã từ password manager và nhập vào form.
4. Server kiểm tra verifier, trạng thái chưa dùng, rate limit và account policy.
5. Server consume code nguyên tử.
6. Risk engine đánh giá sự kiện mất thiết bị. Theo policy, hệ thống thu hồi passkey/TOTP trên điện thoại và session/token liên quan.
7. Người dùng hoàn tất xác minh bổ sung nếu policy yêu cầu, rồi đăng ký passkey trên thiết bị mới.
8. Hệ thống phát hành bộ recovery code mới, thu hồi các code còn lại của bộ cũ và hiển thị bộ mới một lần.
9. Hệ thống gửi thông báo bảo mật tới kênh đã xác minh và ghi audit event không chứa mã.

**Nếu mã không còn:** hệ thống chuyển người dùng sang quy trình identity proofing hoặc hỗ trợ đã được phê duyệt. Không cho nhân viên hỗ trợ bỏ qua bước xác minh chỉ vì người gọi biết email, ngày sinh hoặc thông tin công khai.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Sinh mã bằng random yếu hoặc giá trị đoán được | Attacker có thể đoán recovery code. | Dùng CSPRNG và entropy đủ lớn. |
| Lưu plaintext recovery code | Database/log bị lộ làm lộ đường recovery. | Lưu verifier; bảo vệ pepper/key riêng nếu dùng HMAC. |
| Cho dùng mã nhiều lần | Một mã bị đánh cắp vẫn có thể được replay. | Tiêu thụ one-time một cách nguyên tử. |
| Chỉ kiểm tra rồi cập nhật trạng thái riêng rẽ | Hai request đồng thời có thể cùng thành công. | Transaction, row lock hoặc conditional update. |
| Gửi mã qua email/SMS/chat | Tạo thêm bản sao dễ bị chiếm đoạt. | Hiển thị một lần qua kênh chính thức; hướng dẫn lưu an toàn. |
| Cho xem lại mã cũ | Cần lưu plaintext hoặc dữ liệu có thể giải ngược. | Tạo bộ mới sau xác thực và thu hồi bộ cũ. |
| Coi recovery code là phishing-resistant | Attacker có thể lấy mã qua trang giả. | Cảnh báo rõ, bảo vệ recovery UI và ưu tiên factor dự phòng chống phishing. |
| Không giới hạn lần thử | Brute force và enumeration. | Rate limit nhiều chiều, cooldown và phản hồi chung. |
| Khóa tài khoản vĩnh viễn sau vài lần sai | Attacker có thể gây denial of service. | Dùng throttling/risk review có kiểm soát. |
| Phát hành nhiều bộ nhưng không thu hồi bộ cũ | Tăng số bí mật còn hiệu lực và bề mặt tấn công. | Quản lý set ID và rotate có chủ đích. |
| Dùng code đúng để bỏ qua mọi policy | Tài khoản bị khóa hoặc có dấu hiệu chiếm vẫn được mở. | Tiếp tục account status, risk và approval checks. |
| Recovery xong nhưng giữ session bị chiếm | Attacker vẫn dùng phiên cũ. | Đánh giá và thu hồi session/token liên quan. |
| Ghi mã vào audit hoặc support ticket | Tạo đường lộ bí mật mới. | Chỉ ghi code ID, trạng thái và correlation metadata. |

## 16. Checklist triển khai recovery code

Trước khi đưa recovery code vào production, hãy kiểm tra:

1. Recovery code có được tạo bằng CSPRNG với entropy đủ lớn và độc lập cho từng mã không?
2. Format có dễ nhập nhưng không làm giảm đáng kể độ khó đoán không?
3. Code có được hiển thị một lần và người dùng được hướng dẫn lưu trong nơi an toàn không?
4. Server có lưu verifier thay vì plaintext, và pepper/key có được quản lý tách biệt không?
5. Chuẩn hóa code có cố định, giới hạn độ dài và từ chối ký tự ngoài format không?
6. Recovery transaction có ngắn hạn, gắn với đúng principal/tenant/session và mục đích không?
7. Code có được xác minh và tiêu thụ one-time một cách nguyên tử trên mọi node không?
8. Có rate limit theo account, IP/network, device, transaction và tenant không?
9. Phản hồi lỗi có tránh tiết lộ mã tồn tại, số mã còn lại hoặc dữ liệu tài khoản không?
10. Recovery code có được xem là bí mật bearer dễ bị phishing, không phải yếu tố chống phishing không?
11. Sau recovery có đánh giá session/token, credential bị mất, recovery method và account status không?
12. Có chính sách rotate/thu hồi toàn bộ bộ mã khi nghi lộ hoặc sau sự cố không?
13. Có phương thức proofing/hỗ trợ thay thế khi người dùng mất cả authenticator lẫn recovery code không?
14. Audit/log/analytics có tránh lưu code plaintext và dữ liệu nhạy cảm không?
15. Có kiểm thử code trùng, code đã dùng, code revoked, brute force, race condition, replay, cache stale và recovery từ thiết bị mới không?

**Kết luận:** Recovery code là bí mật dự phòng dùng để khôi phục quyền truy cập khi người dùng mất authenticator. Mã phải được tạo ngẫu nhiên với entropy đủ lớn, hiển thị một lần, lưu verifier thay vì plaintext, giới hạn thử và tiêu thụ nguyên tử. Vì recovery code có thể bị phishing hoặc đánh cắp trước khi sử dụng, nó không thay thế passkey/security key chống phishing. Sau khi dùng mã, hệ thống cần đánh giá rủi ro, thu hồi session/token liên quan, thiết lập lại phương thức xác thực và quản lý bộ mã còn lại theo chính sách rõ ràng.
