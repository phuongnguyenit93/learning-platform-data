# Password reset completion — Hoàn tất đặt lại mật khẩu an toàn

Trong chương **Password Reset** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bước hoàn tất là thời điểm hệ thống thay đổi bí mật xác thực đang có hiệu lực. Đây không chỉ là thao tác lưu một chuỗi băm mới: nó còn quyết định token nào hết giá trị, phiên nào phải bị thu hồi, bằng chứng nào vẫn cần cho lần đăng nhập tiếp theo và người dùng được thông báo ra sao.

Bài học tập trung vào đoạn từ khi người dùng gửi mật khẩu mới cùng quyền đặt lại hợp lệ cho đến khi giao dịch được ghi nhận bền vững. Mục tiêu là giảm nguy cơ chiếm đoạt tài khoản, kể cả khi có yêu cầu đồng thời, mất response hoặc dịch vụ phụ trợ gặp lỗi.

## 1. “Hoàn tất” nghĩa là gì?

Một lần đặt lại mật khẩu hoàn tất khi nguồn dữ liệu có thẩm quyền đã commit các thay đổi bắt buộc:

1. Mật khẩu mới được lưu bằng cơ chế băm mật khẩu phù hợp.
2. Token hoặc grant đã dùng được đánh dấu tiêu thụ.
3. Phiên bản mật khẩu và trạng thái vô hiệu hóa quyền cũ được cập nhật.
4. Chính sách session và các reset grant liên quan có hiệu lực.
5. Kết quả và sự kiện thông báo được ghi nhận bền vững.

Email thông báo có thể được gửi sau commit. Việc người dùng đã nhận email không phải điều kiện xác định mật khẩu có được đổi hay chưa.

Một HTTP response thành công cũng không tự chứng minh đúng nghiệp vụ nếu hệ thống đã ghi nhận sai tài khoản hoặc vẫn cho dùng lại token.

### 1.1. Phân biệt các luồng gần nhau

| Luồng | Bằng chứng đầu vào | Ý nghĩa |
|---|---|---|
| Đổi mật khẩu khi còn đăng nhập | Xác thực lại theo chính sách, có thể gồm mật khẩu hiện tại hoặc authenticator khác | Quản lý credential khi người dùng còn đủ khả năng xác thực |
| Đặt lại mật khẩu khi quên | Token hoặc reset grant được cấp sau bằng chứng khôi phục phù hợp | Thay mật khẩu mà không cần biết mật khẩu cũ |
| Khôi phục MFA, passkey hoặc thiết bị | Bằng chứng theo chính sách cho phương tiện bị mất | Xử lý authenticator khác; không tự nằm trong quyền đặt lại mật khẩu |
| Khôi phục tài khoản nghi bị chiếm đoạt | Bằng chứng độc lập và xử lý các thay đổi của kẻ tấn công | Phạm vi rộng hơn một lần đổi mật khẩu |

Không yêu cầu người quên mật khẩu phải nhập mật khẩu cũ để hoàn tất reset. Cũng không tự gỡ MFA, xóa passkey hoặc đổi email chỉ vì reset mật khẩu thành công.

## 2. Bất biến của bước hoàn tất

Các bất biến cần giữ dù dùng framework hoặc database nào:

- **Đúng tài khoản:** tài khoản đích được xác định từ reset grant đã xác minh, không từ `user_id` tùy ý trong request.
- **Đúng mục đích:** grant dành cho `PASSWORD_RESET` không cấp quyền thay yếu tố khác.
- **Đủ bằng chứng:** token hợp lệ chỉ đủ khi chính sách hiện hành cho phép tổ hợp bằng chứng đã hoàn thành.
- **Tối đa một lần hoàn tất trên một grant:** phát lại cùng token không đổi mật khẩu thêm lần nữa.
- **Nhất quán:** tiêu thụ grant và cập nhật mật khẩu cùng commit hoặc cùng rollback.
- **Không dùng quyền cũ:** token và session bị chính sách thu hồi không tiếp tục được sử dụng.
- **Không tự đăng nhập:** kết quả reset không được tự biến thành session đầy đủ.
- **Không lộ bí mật:** mật khẩu, token và verifier không đi vào log, email hoặc phản hồi lỗi.

Bất biến quan trọng có thể diễn đạt:

~~~text
Mỗi reset_grant_id:
  số completion đã commit <= 1

Mỗi completion đã commit:
  password update + grant consumption + version/epoch update
  thuộc cùng một quyết định có thẩm quyền.
~~~

OWASP khuyến nghị người dùng đăng nhập qua cơ chế thông thường sau reset, thay vì tự động đăng nhập, và yêu cầu thông báo việc đổi mật khẩu mà không gửi mật khẩu trong email. [OWASP Forgot Password, User Resets Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password).

## 3. Đầu vào và mô hình quyền

Một request hoàn tất có thể gồm:

~~~json
{
  "resetToken": "<token bí mật, chỉ là chỗ minh họa>",
  "newPassword": "<mật khẩu mới>",
  "confirmPassword": "<nhập lại mật khẩu mới>"
}
~~~

Các giá trị trong ví dụ không phải thông tin xác thực thật. Request phải đi qua HTTPS; các trường bí mật không được ghi vào access log, trace hoặc báo cáo lỗi.

Một thiết kế khác đổi token liên kết thành reset session giới hạn trước khi người dùng nhập mật khẩu. Khi đó request cuối gửi credential của reset session và bằng chứng chống CSRF phù hợp. Dù dùng dạng nào, quyền chỉ phục vụ reset và phải có vòng đời rõ.

### 3.1. Token và mật khẩu có cách lưu khác nhau

Giả sử reset token có 32 byte ngẫu nhiên mật mã, biểu diễn bằng Base64url. Có thể lưu digest mật mã của token để tra cứu; không lưu token rõ. Tính khó đoán đến từ entropy của token, không từ việc thêm email hay timestamp vào chuỗi.

Mật khẩu do con người chọn có phân bố khác. Nó cần hàm băm mật khẩu có salt và chi phí phù hợp; không sao chép cách băm nhanh của token sang mật khẩu.

Token phải được phân tích đúng định dạng đã cấp. Với Base64url, dấu gạch ngang có thể là một phần dữ liệu; không áp dụng quy tắc bỏ dấu gạch hoặc đổi hoa/thường của một loại mã khác.

### 3.2. Trạng thái phải kiểm tra lại

Trước khi quyết định đổi mật khẩu, kiểm tra:

- Grant tồn tại, đúng mục đích, chưa dùng, chưa thu hồi và chưa hết hạn.
- Grant thuộc đúng tài khoản và đúng phiên bản trạng thái bảo mật.
- Binding của reset context còn đúng nếu thiết kế dùng binding.
- Bằng chứng bổ sung đã hoàn thành và còn đủ mới.
- Tài khoản hiện được phép reset theo chính sách.
- Tài khoản được phép có mật khẩu cục bộ.

Không tự thêm mật khẩu cục bộ cho tài khoản chỉ dùng SSO hoặc passkey nếu chính sách không cho phép. Việc này có thể tạo ra đường đăng nhập mới ngoài kiểm soát của nhà cung cấp danh tính.

Trạng thái khóa cũng cần phân biệt: khóa tạm do thử đăng nhập sai khác với tài khoản bị đình chỉ hoặc có hạn chế bảo mật. Không áp dụng một cờ `locked` mơ hồ để vô tình bỏ qua lệnh đình chỉ hoặc khóa người dùng khỏi luồng recovery hợp lệ.

## 4. Kiểm tra mật khẩu mới trước khi tiêu thụ grant

Một mật khẩu chưa đạt chính sách không nên làm mất reset grant còn hợp lệ. Kiểm tra cú pháp, độ dài, xác nhận và các yêu cầu chính sách trước bước tiêu thụ cuối cùng.

### 4.1. Dùng chính sách thống nhất

Reset và đăng ký/đổi mật khẩu phải dùng chính sách backend thống nhất. Nếu giao diện chấp nhận mật khẩu nhưng backend đăng nhập xử lý khác, người dùng có thể đổi thành công rồi không đăng nhập được.

Khi áp dụng NIST SP 800-63B-4, lưu ý các yêu cầu về độ dài theo vai trò của mật khẩu, danh sách chặn, hỗ trợ mật khẩu dài và kiểm chứng toàn bộ mật khẩu. Không suy ra một quy tắc “8 ký tự cho mọi trường hợp” hoặc bắt buộc tổ hợp chữ hoa, chữ thường, số và ký hiệu theo thói quen. [NIST SP 800-63B-4, Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#password-verifiers).

Ví dụ, NIST yêu cầu tối thiểu 15 ký tự khi mật khẩu là cơ chế xác thực một yếu tố; có thể cho phép ngắn hơn khi mật khẩu chỉ dùng trong MFA, nhưng tối thiểu vẫn là 8 ký tự. Nếu sản phẩm chọn một ngưỡng chung cao hơn cho dễ áp dụng, cần thống nhất ở mọi nơi. [NIST SP 800-63B-4, mục 3.1.1.2](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#password-verifiers).

### 4.2. Unicode, độ dài và xác nhận

Nếu hỗ trợ Unicode, cần xác định cách chuẩn hóa và mã hóa trước khi băm. NIST khuyến nghị NFC; quy tắc được chọn phải nhất quán với bước đăng nhập. Không dùng bộ chuẩn hóa email hoặc backup code cho mật khẩu. [NIST SP 800-63B-4, Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#password-verifiers).

Trong Java, `String.length()` đếm đơn vị UTF-16, không luôn bằng số Unicode code point. Phép đếm và giới hạn đầu vào phải tương ứng với chính sách, đồng thời có giới hạn kích thước request để tránh tiêu tốn tài nguyên.

Không âm thầm cắt mật khẩu dài, chuyển tất cả sang chữ thường hoặc loại bỏ dấu cách. Nếu sản phẩm có quy tắc xử lý nào, phải được thiết kế và dùng nhất quán; người dùng cần biết đầu vào nào được chấp nhận.

Ô nhập lại mật khẩu giúp phát hiện gõ nhầm, nhưng không thay thế bất kỳ bằng chứng xác thực nào. Cho phép password manager, autofill và thao tác dán; tránh buộc người dùng gõ thủ công một bí mật khó nhớ.

### 4.3. Danh sách chặn và bí mật đã lộ

Kiểm tra mật khẩu mới theo chính sách danh sách chặn của hệ thống. Không gửi mật khẩu rõ tới một dịch vụ bên ngoài để hỏi nó có bị lộ không. Nếu dùng nhà cung cấp kiểm tra dữ liệu rò rỉ, phải đánh giá giao thức bảo vệ dữ liệu và hành vi khi dịch vụ không khả dụng.

Không gọi dịch vụ chậm trong khi giữ khóa tài khoản. Nếu chính sách kiểm tra thay đổi giữa bước chuẩn bị và commit, cần xác nhận lại phiên bản hoặc thực hiện lại kiểm tra thích hợp.

Không trả thông tin lịch sử mật khẩu nhạy cảm qua endpoint reset. Nếu tổ chức có quy tắc chống tái sử dụng, triển khai nó như một phần chính sách được kiểm soát; không lưu mật khẩu rõ để so sánh về sau.

## 5. Chuẩn bị password hash và giới hạn tài nguyên

Mật khẩu mới cần được băm bằng thư viện và thuật toán phù hợp, ví dụ Argon2id trong môi trường hỗ trợ, với salt riêng và tham số được chọn theo yêu cầu bảo mật, hiệu năng và môi trường triển khai. Nếu có yêu cầu dùng thuật toán được phê duyệt trong một môi trường cụ thể, lựa chọn cần tuân theo yêu cầu đó.

Không tự viết hàm băm mật khẩu bằng cách lặp SHA-256 hoặc mã hóa mật khẩu để có thể đọc lại. OWASP hướng dẫn dùng thuật toán băm mật khẩu thích nghi và giải thích vai trò của salt, pepper và work factor. [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

### 5.1. Băm ngoài giao dịch khóa ngắn

Băm mật khẩu có thể tốn CPU và bộ nhớ. Giữ khóa database trong suốt thời gian đó làm tăng thời gian chờ và có thể bị lạm dụng.

Một cách tổ chức:

~~~text
Kiểm tra đầu vào và giới hạn thử
  -> kiểm tra sơ bộ grant từ nguồn đáng tin cậy
  -> kiểm tra chính sách mật khẩu
  -> tính password hash
  -> mở transaction ngắn
  -> khóa tài khoản và kiểm tra lại toàn bộ điều kiện
  -> tiêu thụ grant, lưu hash, cập nhật trạng thái
  -> commit
~~~

Kiểm tra sơ bộ không quyết định thành công. Grant có thể bị tiêu thụ hoặc hết hạn trong khi đang băm; bước giao dịch phải bắt được thay đổi này. Hash đã tính nhưng không dùng được có thể bị bỏ đi.

Giới hạn số tác vụ băm đồng thời và kích thước hàng đợi. Không để mọi token ngẫu nhiên từ Internet kích hoạt băm đắt tiền không giới hạn. Rate limit và kiểm tra grant sơ bộ cần xảy ra trước công việc tốn tài nguyên.

### 5.2. Mã giả Java cho ranh giới xử lý

Các lớp trong ví dụ là mô hình minh họa, không phải API của một framework cụ thể:

~~~java
ResetResult complete(ResetCommand command) {
    requestLimits.check(command);
    resetLimiter.check(command.context());

    VerifiedGrantHint hint =
            grants.precheck(command.resetToken(), command.context());

    PasswordPolicySnapshot policy =
            passwordPolicies.currentFor(hint.accountId());

    PreparedPassword prepared =
            policy.validateAndPrepare(
                    command.newPassword(),
                    command.confirmPassword());

    EncodedPassword encoded =
            passwordHasher.encode(prepared);

    // Callback phải được commit thành công trước khi trả Completed.
    return transactions.execute(tx ->
            commitReset(tx, hint, command.context(), policy, encoded));
}
~~~

`commitReset` phải đọc lại grant và trạng thái tài khoản bằng transaction, không tin mù quáng `hint`. `hint.accountId` đến từ bản ghi grant đã xác minh phía máy chủ, không phải tài khoản do client chọn.

Không đánh dấu token đã dùng trong `precheck`, vì người dùng vẫn có thể gửi mật khẩu không hợp lệ hoặc tác vụ băm có thể thất bại. Dọn bí mật khỏi bộ nhớ trong khả năng thư viện cho phép và tránh sao chép sang đối tượng sống lâu; Java `String` không bảo đảm xóa sạch dữ liệu khỏi bộ nhớ.

## 6. Mô hình dữ liệu và phiên bản

Một thiết kế tối giản có các thực thể sau:

| Thực thể | Trường chính | Mục đích |
|---|---|---|
| `account_security` | `user_id`, `recovery_allowed`, `local_password_allowed`, `password_version`, `reset_epoch`, `session_epoch`, `recovery_policy_version` | Trạng thái có thẩm quyền và điểm phối hợp |
| `password_credential` | `user_id`, `password_hash`, `changed_at` | Verifier của mật khẩu hiện hành |
| `password_reset_grant` | `id`, `user_id`, `token_digest`, `purpose`, `issued_password_version`, `issued_reset_epoch`, `policy_version`, `expires_at`, `consumed_at`, `revoked_at` | Quyền đặt lại mật khẩu |
| `password_reset_completion` | `operation_id`, `grant_id`, `user_id`, `new_password_version`, `completed_at` | Kết quả bền vững để audit và đối chiếu retry |
| `security_outbox` | `event_id`, `event_type`, `user_id`, `payload`, `created_at` | Việc cần xử lý sau commit |

Nếu dùng reset session, grant còn cần binding và trạng thái bằng chứng tương ứng. Khóa chính, khóa ngoại và ràng buộc cùng tài khoản phải được thiết kế đầy đủ.

Các phiên bản có vai trò khác nhau:

- `password_version` tăng khi mật khẩu được thay đổi.
- `reset_epoch` làm mất hiệu lực cả nhóm quyền reset đã cấp trước một mốc.
- `session_epoch` phục vụ thu hồi session theo chính sách.
- `recovery_policy_version` nhận diện chính sách đã dùng khi cấp quyền.

Không gộp mọi thứ thành một biến nếu chưa xác định hậu quả. Ví dụ, đặt lại mật khẩu không tự có nghĩa phải xóa passkey; thu hồi session cũng không đồng nghĩa đổi verifier mật khẩu.

Các ràng buộc ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_reset_token_digest
    ON password_reset_grant (token_digest);

CREATE UNIQUE INDEX uq_completion_per_grant
    ON password_reset_completion (grant_id);
~~~

Mỗi grant có tối đa một completion. Quyền tra cứu không được thay thế kiểm tra mục đích, tài khoản, hạn dùng và trạng thái. Những đoạn SQL trong bài dùng PostgreSQL và không phải migration hoàn chỉnh.

## 7. Giao dịch hoàn tất

### 7.1. Thứ tự khóa và đường ghi

Ví dụ chọn thứ tự:

~~~text
account_security
  -> password_reset_grant
  -> password_credential
  -> completion và outbox
~~~

Mọi đường đổi mật khẩu, cấp grant mới, khóa recovery và thao tác liên quan cần phối hợp với cùng điểm khóa hoặc cơ chế so sánh phiên bản tương đương. Nếu chỉ endpoint reset khóa tài khoản còn endpoint đổi mật khẩu bỏ qua, vẫn có cuộc đua.

Việc cấp grant mới phải chụp `password_version` và `reset_epoch` nhất quán. Sau một lần reset, grant được tạo từ snapshot cũ không được trở thành quyền hợp lệ.

### 7.2. Khung giao dịch PostgreSQL

`ASSERT` trong chú thích là điều kiện ứng dụng **phải kiểm tra và rollback khi sai**, không phải lệnh SQL chạy trực tiếp. Các tham số `:locked_*` được lấy từ hàng đã khóa; `:server_*` được suy ra từ quyền đã xác minh.

~~~sql
BEGIN;

-- 1. Khóa trạng thái tài khoản theo user_id của grant.
SELECT user_id, recovery_allowed, local_password_allowed,
       password_version, reset_epoch, session_epoch,
       recovery_policy_version
FROM account_security
WHERE user_id = :server_user_id
FOR UPDATE;

-- ASSERT: tài khoản được phép reset mật khẩu cục bộ.

-- 2. Khóa và đọc lại grant.
SELECT id, user_id, purpose, issued_password_version,
       issued_reset_epoch, policy_version, expires_at,
       consumed_at, revoked_at
FROM password_reset_grant
WHERE id = :server_grant_id
  AND user_id = :server_user_id
  AND token_digest = :server_token_digest
FOR UPDATE;

-- ASSERT: đúng mục đích PASSWORD_RESET;
-- binding và bằng chứng bổ sung còn hợp lệ;
-- policy_version khớp chính sách hiện hành;
-- issued_password_version = phiên bản đã khóa;
-- issued_reset_epoch = reset_epoch đã khóa.
-- Xác nhận chính sách mật khẩu dùng để chuẩn bị hash còn hợp lệ.

-- 3. Tiêu thụ có điều kiện tại thời điểm quyết định.
UPDATE password_reset_grant
SET consumed_at = clock_timestamp()
WHERE id = :server_grant_id
  AND user_id = :server_user_id
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > clock_timestamp()
  AND issued_password_version = :locked_password_version
  AND issued_reset_epoch = :locked_reset_epoch
  AND policy_version = :locked_recovery_policy_version
RETURNING id;

-- ASSERT: đúng một dòng.

-- 4. Lưu hash đã chuẩn bị; không lưu mật khẩu rõ.
UPDATE password_credential
SET password_hash = :encoded_password,
    changed_at = clock_timestamp()
WHERE user_id = :server_user_id;

-- ASSERT: đúng một dòng trong mô hình tài khoản có mật khẩu.

-- 5. Tăng phiên bản và thu hồi theo chính sách ví dụ.
-- Ví dụ này tự động vô hiệu hóa các session cũ.
UPDATE account_security
SET password_version = password_version + 1,
    reset_epoch = reset_epoch + 1,
    session_epoch = session_epoch + 1
WHERE user_id = :server_user_id
RETURNING password_version, reset_epoch, session_epoch;

-- Lưu giá trị trả về làm các :new_* tương ứng.

-- 6. Thu hồi các grant reset khác.
UPDATE password_reset_grant
SET revoked_at = clock_timestamp()
WHERE user_id = :server_user_id
  AND id <> :server_grant_id
  AND consumed_at IS NULL
  AND revoked_at IS NULL;

-- 7. Ghi kết quả bền vững.
INSERT INTO password_reset_completion (
    operation_id, grant_id, user_id,
    new_password_version, completed_at
) VALUES (
    :operation_id, :server_grant_id, :server_user_id,
    :new_password_version, clock_timestamp()
);

-- 8. Ghi sự kiện; payload không chứa bí mật.
INSERT INTO security_outbox (
    event_id, event_type, user_id, payload, created_at
) VALUES (
    :event_id, 'PASSWORD_RESET_COMPLETED', :server_user_id,
    :metadata_without_secrets, clock_timestamp()
);

COMMIT;
~~~

Chỉ sau khi transaction đã commit thành công, API mới trả kết quả hoàn tất. Nếu lưu hash, completion hoặc outbox lỗi, toàn bộ thay đổi phải rollback, kể cả `consumed_at`.

Thời hạn grant được kiểm tra bằng thời gian database tại bước tiêu thụ, sau khi chờ khóa. Nếu chính sách yêu cầu một deadline khác, phải biểu diễn rõ; không dùng timestamp lấy từ đầu request để bỏ qua việc token đã hết hạn trong lúc chờ.

Nếu reset grant được đổi thành reset session trước đó, token gốc có thể đã được tiêu thụ ở bước đổi. Khi đó transaction cuối phải tiêu thụ **grant hoặc reset session còn có quyền thay mật khẩu**, không cố tiêu thụ lại token đã đóng và cũng không bỏ qua trạng thái dùng một lần của quyền mới.

### 7.3. Luồng thành công

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant A as Reset API
    participant H as Bộ băm mật khẩu
    participant D as Database có thẩm quyền
    participant W as Outbox worker
    U->>A: Gửi quyền reset và mật khẩu mới
    A->>A: Giới hạn thử, precheck và kiểm tra chính sách
    A->>H: Tính password hash
    H-->>A: Verifier đã mã hóa theo định dạng lưu trữ
    A->>D: BEGIN, khóa và kiểm tra lại
    A->>D: Tiêu thụ grant, lưu hash, tăng phiên bản
    A->>D: Thu hồi quyền cũ, ghi completion và outbox
    A->>D: COMMIT
    D-->>A: Commit thành công
    A-->>U: Hoàn tất; chuyển tới đăng nhập thông thường
    W->>D: Đọc sự kiện đã commit
    W-->>U: Thông báo bảo mật
~~~

Việc tăng epoch phải được nơi sử dụng token thực thi. Một hàng database thay đổi không tự làm vô hiệu hóa cookie hoặc JWT ở các dịch vụ chưa đối chiếu trạng thái đó.

## 8. Xử lý yêu cầu đồng thời và các cuộc đua

### 8.1. Hai request dùng cùng một grant

Nếu hai instance cùng precheck một token còn hiệu lực, cả hai có thể tính hash. Chỉ transaction quyết định request nào được ghi nhận.

| Thời điểm | Request A | Request B |
|---|---|---|
| 1 | Precheck hợp lệ, tính hash A | Precheck hợp lệ, tính hash B |
| 2 | Khóa tài khoản và grant | Chờ khóa |
| 3 | Tiêu thụ grant, đổi mật khẩu, commit | |
| 4 | | Đọc lại trạng thái sau khi lấy khóa |
| 5 | | Thấy grant đã dùng hoặc phiên bản đã đổi, từ chối |

Kết quả đúng là một completion và một lần tăng phiên bản. Không được để “request đến sau thắng” khi cùng một grant đã bị dùng.

Trong PostgreSQL `READ COMMITTED`, cập nhật cạnh tranh có thể chờ transaction trước và đánh giá lại điều kiện trên phiên bản hàng mới. Tuy nhiên, mức cô lập này không tự tạo nhất quán cho mọi điều kiện liên quan nhiều hàng; thiết kế còn cần khóa và quy ước đường ghi như ở mục 7. [PostgreSQL 18, Read Committed](https://www.postgresql.org/docs/18/transaction-iso.html#XACT-READ-COMMITTED).

### 8.2. Hai grant khác nhau của cùng tài khoản

Một người có thể xin liên kết nhiều lần. Nếu grant A và B cùng được cấp ở `password_version=7`, `reset_epoch=3`, completion từ A tăng thành phiên bản 8 và epoch 4. B không còn quyền ghi đè mật khẩu, dù thời hạn riêng của B chưa kết thúc.

Việc thu hồi bản ghi sibling grant giúp quản lý trạng thái; kiểm tra version/epoch là hàng rào bổ sung. Cả phát hành và sử dụng phải thực thi cùng mô hình, nếu không grant tạo từ snapshot cũ có thể lọt qua.

Không thu hồi session hoặc đổi mật khẩu chỉ vì nhận một yêu cầu gửi liên kết mới chưa xác minh. Người lạ biết email không được quyền gây mất truy cập của chủ tài khoản.

### 8.3. Reset cạnh tranh với đổi mật khẩu đang đăng nhập

Đường đổi mật khẩu có xác thực cũng cần làm mất hiệu lực các reset grant cũ theo chính sách. Nếu nó chỉ ghi hash mà không cập nhật version/epoch, một liên kết cũ có thể đổi lại mật khẩu sau đó.

Khóa và phiên bản giúp xác định thứ tự có thẩm quyền. Không dùng thời điểm người dùng mở trang làm thứ tự ưu tiên; trang đã mở không có quyền giữ nguyên trạng thái bảo mật mãi mãi.

### 8.4. Đăng nhập bằng mật khẩu cũ đang chạy đồng thời

Một cuộc đua ít rõ hơn:

~~~text
Login L đọc hash và password_version=7
  -> xác minh mật khẩu cũ, tác vụ băm còn đang chạy

Reset R commit:
  -> password_version=8, session_epoch tăng

Login L tiếp tục:
  -> nếu lấy epoch mới rồi cấp session mà không kiểm tra lại
     phiên bản mật khẩu đã xác minh, mật khẩu cũ có thể tạo session mới.
~~~

Đường đăng nhập phải ràng buộc kết quả xác minh với đúng phiên bản đã đọc. Trước khi cấp session, kiểm tra lại trạng thái có thẩm quyền hoặc dùng cơ chế so sánh phiên bản phù hợp. Nếu phiên bản đã đổi, xác minh cũ không được nâng thành session mang epoch mới.

Không chỉ xử lý cuộc đua ở endpoint reset. Đường refresh token, remember-me và tạo session cũng phải tuân theo phiên bản trạng thái hiện hành.

## 9. Thu hồi session và quyền khôi phục cũ

### 9.1. Xác định chính sách cụ thể

Ví dụ giao dịch trong bài chọn **tự động thu hồi session cũ** sau reset bằng cách tăng `session_epoch`. Đây là lựa chọn thiết kế cần được thực thi đầy đủ, không phải hành vi tự có của một framework.

Ở luồng quên mật khẩu thông thường, sản phẩm có thể có chính sách khác được đánh giá rõ. Nếu đang xử lý nghi ngờ chiếm đoạt tài khoản, không để một lựa chọn tiện lợi trên giao diện duy trì session của kẻ tấn công.

Các loại quyền cần được xét riêng:

| Loại quyền | Cách xử lý theo chính sách minh họa |
|---|---|
| Session trình duyệt | Kiểm tra epoch hoặc trạng thái thu hồi ở backend |
| Refresh token | Từ chối các token/family thuộc trạng thái cũ |
| Remember-me token | Vô hiệu hóa hoặc đưa vào cùng cơ chế phiên bản |
| Reset grant khác | Thu hồi và chặn bằng reset epoch/password version |
| Recovery grant khác có quyền thay credential | Đánh giá và thu hồi nếu có thể khôi phục quyền cũ |
| Access token tự chứa | Có cơ chế đối chiếu hoặc thu hồi tương ứng |
| API key, app password | Có chính sách riêng; không mặc định bị thu hồi do đổi mật khẩu |

Không xóa passkey hay seed TOTP như một tác dụng phụ không được định nghĩa. Nhưng nếu một authenticator đã bị xác định là bị chiếm quyền, phải xử lý nó trong luồng sự cố phù hợp.

### 9.2. Epoch không có tác dụng nếu không ai kiểm tra

JWT có chữ ký đúng và chưa hết hạn vẫn có thể được chấp nhận nếu resource server chỉ kiểm tra chữ ký và `exp`. Tăng một số trong database không tự thay đổi điều đó.

Để thu hồi có hiệu lực theo thời hạn cam kết, cần một phương án như đối chiếu trạng thái đáng tin cậy, introspection, denylist hoặc cơ chế quản lý phiên bản tương đương. Nếu dùng cache, xác định cửa sổ dữ liệu cũ và cách xử lý khi cache không được cập nhật.

TTL ngắn chỉ giới hạn thời gian tồn tại tối đa; nó không đồng nghĩa thu hồi tức thời. Khi chưa có cơ chế thu hồi toàn hệ thống, phải nói đúng giới hạn của thiết kế, không tuyên bố mọi phiên đã bị chặn ngay sau commit.

### 9.3. Cạnh tranh với refresh và các request đang chạy

Nếu refresh token được xác minh trước reset nhưng cấp token sau reset, kết quả vẫn phải bị ràng buộc với phiên bản đã kiểm tra. Không gắn epoch mới vào một proof cũ để làm nó sống lại.

Thu hồi cũng không tự đảo ngược một giao dịch nghiệp vụ đã được cấp phép trước thời điểm thu hồi. Hành động nhạy cảm có thể cần kiểm tra trạng thái sát thời điểm commit của chính hành động đó.

Đừng dùng outbox gửi email làm cơ chế thu hồi duy nhất nếu hệ thống cam kết thu hồi ngay. Outbox có thể hỗ trợ dọn kho session, nhưng điểm chấp nhận token phải có hàng rào trạng thái đáp ứng cam kết.

## 10. Retry, double submit và commit chưa rõ kết quả

### 10.1. Phân loại lỗi theo ranh giới commit

| Sự cố | Ý nghĩa | Hành vi |
|---|---|---|
| Mật khẩu không đạt chính sách | Chưa đến quyết định tiêu thụ cuối | Hiển thị lỗi phù hợp, không làm mất grant hợp lệ |
| Hash thất bại hoặc quá tải | Chưa commit thay đổi | Lỗi tạm thời; không đánh dấu hoàn tất |
| Ghi hash hoặc completion lỗi | Transaction rollback | Mật khẩu cũ và trạng thái grant giữ nhất quán |
| Commit thành công, mất HTTP response | Reset đã hoàn tất | Không dùng lại grant để đổi mật khẩu lần nữa |
| Kết nối đứt trong lúc commit | API chưa biết kết quả | Đối chiếu completion trên nguồn có thẩm quyền |
| Email hoặc dọn cache lỗi sau commit | Mật khẩu đã đổi | Retry việc phụ trợ, không mở lại grant |

Không báo “chưa đổi mật khẩu” chỉ vì request bị timeout. Timeout chỉ mô tả việc client không nhận được kết quả đúng hạn.

### 10.2. Đối chiếu bằng completion record

`password_reset_completion` cho biết operation nào đã commit, cho tài khoản/grant nào và ở phiên bản nào. Nó không chứa mật khẩu, token rõ hoặc hash mật khẩu.

Tra cứu kết quả cần ràng buộc với reset context hoặc một receipt có kiểm soát; không tạo endpoint công khai để người biết email dò thời điểm tài khoản đổi mật khẩu.

Một completion cũ chỉ chứng minh thao tác đó đã hoàn tất tại thời điểm ghi nhận. Nó không bảo đảm mật khẩu hiện tại vẫn là mật khẩu được đặt khi đó, vì người dùng có thể đã đổi thêm lần khác.

Không xác định commit thành công bằng cách thử đăng nhập với mật khẩu mới. Cách đó có thể tạo session, kích hoạt rate limit, phụ thuộc MFA và vẫn không giải thích đầy đủ trạng thái giao dịch.

### 10.3. Nếu bổ sung idempotency

Khóa idempotency có thể ràng buộc operation với cùng grant và context đã xác minh. Sau khi có completion, cùng operation chỉ trả receipt của kết quả đã có, không chạy lại cập nhật.

Phải xác định rõ hợp đồng khi request sau gửi mật khẩu khác. Không được trả lời theo nghĩa “mật khẩu mới trong request sau đã được chấp nhận” nếu server chỉ đang trả receipt của operation trước. Có thể yêu cầu client tra trạng thái qua một luồng riêng hoặc từ chối submission lại theo hợp đồng API.

Không lưu thêm SHA-256 của mật khẩu chỉ để nhận diện payload retry: nó tạo một verifier nhanh để đoán mật khẩu ngoại tuyến. Thiết kế idempotency nên tránh giữ bí mật hoặc dấu kiểm chứng mới không cần thiết.

Double submit do bấm nút hai lần phải bị backend xử lý an toàn ngay cả khi không có idempotency riêng. Khóa nút giao diện chỉ giúp trải nghiệm.

### 10.4. Không dùng giao dịch bù để hồi sinh quyền cũ

Sau commit, email không gửi được hoặc client báo lỗi không phải lý do khôi phục hash cũ hay đặt `consumed_at=NULL`. Việc bù như vậy có thể làm sống lại token đã bị đánh cắp.

Nếu cần một lần reset mới, cấp quyền mới sau bằng chứng phù hợp. Không tự gửi mật khẩu mới do server tạo vào email để “sửa lỗi” giao nhận.

## 11. Giao diện hoàn tất và đăng nhập lại

### 11.1. Mở liên kết không đồng nghĩa tiêu thụ quyền

Email scanner, trình xem trước liên kết và trình duyệt có thể tự gửi `GET`. Không đổi mật khẩu hoặc tiêu thụ quyền đổi mật khẩu chỉ vì liên kết được mở.

Nếu có bước đổi liên kết sang context giới hạn, thiết kế nó để hoạt động tự động của scanner không âm thầm tước khả năng reset của người dùng. Việc hoàn tất thay mật khẩu cần một request chủ đích với bằng chứng và dữ liệu cần thiết.

Trang reset nên giảm nguồn làm lộ token: không nạp công cụ phân tích không cần thiết, che thông tin nhạy cảm trong log và dùng chính sách referrer/cache phù hợp. Ví dụ:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Token trong URL liên kết ban đầu vẫn có thể đi vào log của hạ tầng nếu không che từ điểm tiếp nhận; header trên trang không xóa log đã có. Sau khi thiết lập context, có thể đưa người dùng tới URL không còn token theo thiết kế an toàn.

Khi sử dụng cookie reset context, áp dụng `Secure`, `HttpOnly`, `SameSite` phù hợp và cơ chế chống CSRF. Kiểm tra nguồn request và ràng buộc context theo kiến trúc; đừng cho rằng có một token trong bất kỳ trường nào thì mọi rủi ro CSRF đều tự biến mất.

### 11.2. Thông báo sau commit

Ví dụ nội dung:

> Mật khẩu của bạn đã được đặt lại. Hãy đăng nhập bằng mật khẩu mới. Nếu bạn không thực hiện thao tác này, hãy mở mục hỗ trợ bảo mật.

Chỉ hiển thị kết quả hoàn tất sau khi backend có kết quả có thẩm quyền. Không đưa token, email đầy đủ hoặc mật khẩu vào trang thành công, URL chuyển hướng hay thông báo toast.

Nếu dùng POST/Redirect/GET, chọn đích do máy chủ kiểm soát và bảo đảm redirect không mang dữ liệu bí mật. Tham số `returnUrl` không được tạo open redirect.

Không phản chiếu mật khẩu mới từ server để trình duyệt điền lại. Trường nhập lại phải được xử lý theo cùng quy tắc đã công bố; lỗi chính sách không được làm lộ token hoặc dữ liệu tài khoản.

### 11.3. Đăng nhập theo cơ chế thông thường

Sau reset, người dùng đăng nhập bằng luồng hiện hành. Nếu tài khoản có MFA, vẫn cần hoàn thành MFA. Nếu mất cả MFA, chuyển sang quy trình recovery riêng; không tự bỏ qua yếu tố vì người dùng vừa reset mật khẩu.

Khi tạo session mới sau đăng nhập, dùng session identifier mới theo framework, không nâng nguyên cookie của reset context thành phiên có mọi quyền. OWASP yêu cầu tái sinh session ID khi mức quyền thay đổi để giảm session fixation. [OWASP Session Management, Renew the Session ID](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#renew-the-session-id-after-any-privilege-level-change).

Nếu trình duyệt đang đăng nhập một tài khoản khác, tài khoản đích vẫn đến từ grant. Tránh thao tác reset làm đổi ngầm danh tính của session đang hoạt động. Giao diện nên giải thích bước đăng nhập tiếp theo bằng nội dung không lộ thông tin ngoài ngữ cảnh được phép.

## 12. Thông báo, audit và outbox sau commit

Một sự kiện có thể gồm các tham chiếu nội bộ và phiên bản; các giá trị dưới đây chỉ để minh họa:

~~~json
{
  "eventId": "evt-reset-example-01",
  "eventType": "PASSWORD_RESET_COMPLETED",
  "operationRef": "op-example-23",
  "accountRef": "account-internal-42",
  "grantRef": "grant-internal-17",
  "passwordVersion": 8,
  "sessionEpoch": 12,
  "outcome": "COMMITTED"
}
~~~

Ghi thời gian từ nguồn tin cậy, loại luồng và metadata rủi ro tối thiểu cần thiết. Không có mật khẩu, hash mật khẩu, token, token digest hoặc cookie trong payload.

Audit và outbox được ghi cùng transaction. Worker gửi thông báo qua kênh đã đăng ký và được chính sách đánh giá là an toàn. Nội dung không chứa mật khẩu mới hoặc liên kết có quyền đặt lại vô hạn.

Kênh “không phải tôi” cần một quy trình phản hồi sự cố có kiểm soát; không để một request dễ giả mạo tự đặt lại mật khẩu lần nữa hoặc khóa tài khoản vĩnh viễn.

Outbox thường cần retry và có thể phát sự kiện trùng. Consumer nên dùng `eventId` để khử trùng lặp khi có thể. Những sự kiện liên quan đến phiên bản cũng phải chịu được đảo thứ tự: không để sự kiện epoch 11 đến sau epoch 12 làm trạng thái quay về 11.

Một job dọn session phải thu hồi đúng phạm vi phiên cũ, không xóa nhầm session hợp lệ được tạo sau reset chỉ vì sự kiện đến muộn. Có thể dùng epoch hoặc mốc phiên bản gắn với sự kiện thay vì lệnh “xóa tất cả tại lúc worker chạy” không phân biệt nguồn gốc.

Các chỉ số hữu ích gồm completion đã commit, lỗi giao dịch, từ chối token đã dùng, thời gian chờ khóa, tải bộ băm, tuổi sự kiện outbox và độ trễ thu hồi session. Không dùng tài khoản hoặc token thô làm metric label.

## 13. Reset mật khẩu trong hệ thống nghi bị chiếm đoạt hoặc dùng IdP

### 13.1. Đổi mật khẩu chưa đủ để khôi phục toàn bộ quyền kiểm soát

Kẻ tấn công có thể còn session, refresh token, API key hoặc authenticator do họ thêm. Họ cũng có thể đã đổi thông tin liên hệ trước đó.

Quy trình sự cố cần rà soát các phương tiện và thay đổi trái phép, dùng bằng chứng đáng tin cậy theo chính sách. Không chỉ gửi thông báo hoặc mã mới tới địa chỉ vừa bị thay đổi rồi coi tài khoản đã an toàn. OWASP nhấn mạnh một lần reset mật khẩu đơn lẻ có thể chưa lấy lại quyền kiểm soát tài khoản bị chiếm đoạt. [OWASP Forgot Password, Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

Không tự khôi phục mọi địa chỉ hoặc số điện thoại cũ: chúng có thể đã bị thay vì mất quyền kiểm soát. Lịch sử giúp đánh giá bằng chứng, không phải lệnh tự động đảo ngược mọi thay đổi.

### 13.2. Khi mật khẩu nằm ở IdP hoặc dịch vụ khác

Transaction PostgreSQL trong bài chỉ bao phủ những thay đổi thuộc cùng nguồn dữ liệu có thẩm quyền. Nó không làm một lời gọi HTTP đổi mật khẩu ở IdP trở thành nguyên tử cùng database cục bộ.

Nếu IdP quản lý mật khẩu, cần dùng quy trình hoàn tất do IdP hỗ trợ và ghi nhận kết quả có thẩm quyền của họ. Không tạo một mật khẩu cục bộ dự phòng để né lỗi tích hợp.

Nếu phải điều phối nhiều hệ thống, cần trạng thái bền vững như:

~~~text
PENDING_EXTERNAL
  -> PROVIDER_CONFIRMED
  -> LOCALLY_FINALIZED
~~~

Đây là mô hình minh họa. Operation phải được ràng buộc, chống chạy lại và có cách đối chiếu khi timeout; dùng idempotency của nhà cung cấp nếu có. Không coi request timeout là bằng chứng IdP chưa đổi mật khẩu, và không cho một operation chưa rõ kết quả cấp thêm quyền tùy ý.

Thời điểm hiển thị thành công phải phản ánh phần nào đã được xác nhận. Nếu chính sách yêu cầu thu hồi ở IdP và RP, theo dõi cả hai thay vì chỉ đổi một cờ cục bộ.

## 14. Các lỗi thiết kế thường gặp

| Thiết kế | Hậu quả |
|---|---|
| Tiêu thụ token rồi commit riêng trước khi lưu hash | Người dùng mất quyền reset dù mật khẩu chưa đổi |
| Lưu hash trước, tiêu thụ token sau trong transaction khác | Token có thể đổi mật khẩu nhiều lần |
| Tin `user_id` trong body | Token một tài khoản có thể tác động tài khoản khác |
| Chỉ kiểm tra token ở lúc mở trang | Token đã hết hạn hoặc bị thu hồi vẫn hoàn tất |
| Tự đăng nhập và bỏ qua MFA | Reset mật khẩu trở thành đường vượt kiểm soát khác |
| Chỉ xóa cookie hiện tại | Session hoặc token ở thiết bị khác còn hoạt động |
| Gọi email trước commit | Thông báo thành công cho thay đổi đã rollback |
| Mở lại token khi gửi thông báo thất bại | Hồi sinh quyền có thể đã bị lộ |
| Tăng epoch nhưng dịch vụ không kiểm tra | Thu hồi chỉ tồn tại trên giấy |
| Xác minh mật khẩu cũ rồi cấp session mang phiên bản mới | Cuộc đua đăng nhập vượt lần reset vừa hoàn tất |
| Đưa mật khẩu vào fingerprint retry dạng băm nhanh | Tạo thêm khả năng đoán mật khẩu ngoại tuyến |
| Dùng fallback mật khẩu cho tài khoản SSO-only | Tạo đường truy cập ngoài chính sách |
| Thay đổi hash qua một công cụ hỗ trợ bỏ qua version/epoch | Liên kết và session cũ có thể sống lại |
| Restore snapshot trước reset | Mật khẩu và token cũ có thể xuất hiện lại |

Restore cần chính sách riêng: tái lập lịch sử thu hồi đáng tin cậy hoặc vô hiệu hóa những quyền bị ảnh hưởng trước khi phục vụ. Failover có khả năng mất transaction đã xác nhận cũng giới hạn mức bảo đảm dùng một lần; thuật toán ứng dụng không sửa được lịch sử đã bị mất.

## 15. Tình huống thực tế và các kiểm chứng cần có

### 15.1. Người dùng gửi hai lần, response đầu bị mất

Mai quên mật khẩu, vẫn còn phương tiện cần thiết theo chính sách và nhận một reset grant hợp lệ.

1. Mai nhập mật khẩu mới; request A qua kiểm tra, tính hash và vào transaction.
2. Do mạng chậm, trình duyệt gửi request B với cùng grant.
3. A tiêu thụ grant, lưu hash, tăng version/epoch, ghi completion và commit.
4. Response A bị mất trước khi đến trình duyệt.
5. B lấy khóa sau, thấy grant đã dùng hoặc epoch không còn khớp, nên không ghi hash lần nữa.
6. Luồng đối chiếu kết quả có kiểm soát xác định operation A đã hoàn tất, hoặc giao diện hướng dẫn đăng nhập theo hợp đồng sản phẩm.
7. Mai đăng nhập bằng mật khẩu đã đặt và vẫn hoàn thành MFA nếu được yêu cầu.
8. Email thông báo có thể đến sau; gửi chậm không làm operation A quay lại trạng thái chưa hoàn tất.

Nếu B mang mật khẩu khác, server không được đổi sang mật khẩu B rồi nói đó là retry. Grant chỉ cho một completion.

### 15.2. Các tình huống cần chứng minh

Bảng sau là yêu cầu kiểm chứng của thiết kế, không phải kết quả kiểm thử đã chạy trên ứng dụng.

| Tình huống | Kết quả cần có |
|---|---|
| Grant hợp lệ, mật khẩu đạt chính sách | Một completion, hash mới và phiên bản tăng đúng một lần |
| Mật khẩu yếu hoặc nhập lại không khớp | Không thay mật khẩu; không tiêu thụ grant hợp lệ |
| Grant sai mục đích hoặc khác tài khoản | Từ chối, không có thay đổi credential |
| Grant đã dùng, hết hạn hoặc thu hồi | Không tạo completion mới |
| Hai request cùng grant trên hai instance | Tối đa một lần cập nhật đã commit |
| Hai grant cùng snapshot của một tài khoản | Grant thua không ghi đè kết quả sau khi version/epoch đã đổi |
| Grant hết hạn trong lúc tính hash hoặc chờ khóa | Kiểm tra lại và từ chối theo deadline |
| Chính sách mật khẩu/recovery đổi trước commit | Không dùng snapshot cũ trái chính sách hiện hành |
| Ghi completion hoặc outbox lỗi | Rollback cả hash và trạng thái grant |
| Commit thành công nhưng mất response | Không reset lần hai; đối chiếu kết quả phù hợp |
| Login bằng mật khẩu cũ đang chạy đồng thời | Không tạo session mới từ proof thuộc phiên bản cũ |
| Refresh token cạnh tranh với reset | Không làm sống lại quyền bằng epoch mới |
| JWT cũ còn hạn | Hành vi đúng với cơ chế và cam kết thu hồi thực tế |
| Người dùng có MFA hoặc mất MFA | Không bỏ qua MFA do reset mật khẩu |
| Tài khoản SSO-only | Không tự thêm mật khẩu cục bộ |
| Email lỗi hoặc sự kiện đến trùng/đảo thứ tự | Không đổi lại mật khẩu, không giảm epoch |
| Scanner mở liên kết bằng GET | Không hoàn tất thay mật khẩu hoặc tước quyền đổi ngoài thiết kế |
| Session đang thuộc tài khoản khác | Tài khoản đích vẫn do grant quyết định |
| Body, URL, trace và error report | Không làm lộ mật khẩu hoặc token |
| Restore/failover về dữ liệu cũ | Có hàng rào xử lý quyền và trạng thái bị ảnh hưởng |

Kiểm tra cạnh tranh cần nhiều kết nối hoặc tiến trình độc lập và quan sát completion, phiên bản mật khẩu cùng session thực sự được chấp nhận. Chỉ đếm HTTP 200 hoặc nhìn hash cuối cùng không đủ để phát hiện mọi lần ghi sai.

## 16. Tài liệu đối chiếu và phạm vi ví dụ

- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): bước đặt mật khẩu mới, đăng nhập lại, token và xử lý sự cố.
- [NIST SP 800-63B-4 — Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#password-verifiers): chính sách và xử lý mật khẩu.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): băm mật khẩu, salt và work factor.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): vòng đời session và tái sinh session ID.
- [PostgreSQL 18 — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html): cập nhật cạnh tranh và giới hạn mức cô lập.

Mô hình version/epoch, tên bảng, Java, SQL và chính sách tự động thu hồi session trong bài là thiết kế minh họa. Chúng cần được tích hợp đầy đủ với nguồn quản lý credential, session, MFA và recovery của hệ thống; không phải mã triển khai hoàn chỉnh hoặc chứng nhận tuân thủ.
