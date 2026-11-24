# Binding token to account

## 1. Ràng buộc token với tài khoản là gì?

Trong khôi phục tài khoản, **binding token to account** là việc máy chủ gắn một token với đúng tài khoản mà token được phép tác động, đồng thời kiểm tra ràng buộc đó khi sử dụng token.

Ví dụ, một token được phát hành để đặt lại mật khẩu của tài khoản A. Người giữ token không được đổi đối tượng sang tài khoản B bằng cách sửa email, user ID, đường dẫn API hoặc trạng thái đăng nhập trên trình duyệt.

Bất biến cốt lõi là:

```text
tài khoản được thay đổi
    = tài khoản mà máy chủ đã ràng buộc với token hợp lệ
```

Một chuỗi token khó đoán chỉ giải quyết khả năng đoán bí mật. Nếu endpoint xác minh token rồi chọn tài khoản cần sửa từ một tham số khác do client gửi, hệ thống vẫn có thể cho phép chiếm đoạt tài khoản.

OWASP yêu cầu các token khôi phục được liên kết với từng người dùng trong database, được sinh bằng nguồn ngẫu nhiên mật mã, có độ dài phù hợp, được lưu an toàn và bị vô hiệu hóa sau khi sử dụng. Xem [OWASP Forgot Password Cheat Sheet — General Security Practices](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Trong bài này, ràng buộc tài khoản được xem là một hợp đồng cấp quyền của dịch vụ khôi phục. Các tên trường, trạng thái và mã giả bên dưới là mô hình minh họa để áp dụng hợp đồng đó.

## 2. Lỗi nguy hiểm: token hợp lệ nhưng thay đổi nhầm tài khoản

Xét một API nhận:

```json
{
  "email": "victim@example.invalid",
  "token": "TOKEN_CUA_TAI_KHOAN_KHAC",
  "newPassword": "DU_LIEU_MAT_KHAU_MOI"
}
```

Một cách xử lý sai:

```text
if existsValidRecoveryToken(request.token):
    account = findAccountByEmail(request.email)
    updatePassword(account, request.newPassword)
```

Hàm kiểm tra đầu tiên chỉ trả lời rằng token có tồn tại và còn hợp lệ ở đâu đó. Nó không chứng minh token cấp quyền đối với tài khoản được chọn ở bước sau.

Kẻ tấn công có thể:

1. Yêu cầu token khôi phục cho tài khoản do mình kiểm soát.
2. Nhận token hợp lệ qua kênh liên hệ của chính mình.
3. Gửi token đó cùng email hoặc ID của nạn nhân.
4. Lợi dụng endpoint để thay đổi thông tin xác thực của nạn nhân.

Token vẫn có thể ngẫu nhiên tốt, chưa hết hạn và chưa dùng lần nào. Lỗ hổng nằm ở việc **tách xác minh token khỏi đối tượng được cấp quyền**.

Cách thiết kế tốt hơn là trả về một ngữ cảnh đã xác minh:

```text
verifiedGrant = verifyRecoveryToken(request.token)

updatePassword(
    tenantId = verifiedGrant.tenantId,
    accountId = verifiedGrant.accountId,
    newPassword = request.newPassword
)
```

Nếu API vẫn có trường tài khoản trong đường dẫn hoặc body, trường đó chỉ được dùng sau khi đối chiếu chính xác với ngữ cảnh của token. Nó không được ghi đè đối tượng đã ràng buộc.

## 3. Chọn định danh tài khoản ổn định

Token nên gắn với định danh nội bộ ổn định của tài khoản, chẳng hạn `account_id`, thay vì phụ thuộc hoàn toàn vào một giá trị có thể thay đổi.

| Giá trị | Vấn đề khi dùng làm căn cứ duy nhất |
| --- | --- |
| Email | Có thể đổi, có alias, có thể được cấp lại hoặc xuất hiện ở nhiều tenant |
| Số điện thoại | Có thể đổi chủ hoặc được tái cấp |
| Username | Có thể đổi hoặc được tái sử dụng tùy sản phẩm |
| Tên hiển thị | Không duy nhất và thường do người dùng tự sửa |
| ID tài khoản trong body | Do client chọn, cần đối chiếu với quyền đã xác minh |
| Tài khoản đang đăng nhập | Có thể khác tài khoản sở hữu liên kết khôi phục |

Email hoặc số điện thoại vẫn có vai trò trong việc tìm tài khoản lúc bắt đầu yêu cầu và chuyển thông điệp khôi phục. Sau khi máy chủ đã xác định đối tượng hợp lệ, bản ghi token cần giữ tham chiếu ổn định đến đối tượng đó.

### Ví dụ email thay đổi

```text
T1: account_id = A, email = old@example.invalid
T2: token được phát hành cho account_id A
T3: A đổi email
T4: old@example.invalid được một tài khoản khác sử dụng
```

Nếu tại T4 hệ thống lấy email trong yêu cầu cũ để tìm lại tài khoản, token có thể bị chuyển nhầm đối tượng. Với `account_id` ổn định, token vẫn tham chiếu A; việc còn cho phép token đó hoạt động hay phải thu hồi là một quyết định chính sách riêng.

Không tái sử dụng ID tài khoản đã xóa cho một tài khoản mới. Token của một tài khoản đã bị xóa phải bị từ chối, thay vì được áp dụng cho đối tượng mới tình cờ mang cùng ID.

## 4. Ràng buộc nhiều chiều: tài khoản, tenant, yêu cầu và mục đích

Chỉ biết tài khoản chưa đủ để xác định toàn bộ quyền khôi phục. Một bản ghi token có thể cần các thuộc tính sau:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `tenant_id` | Không gian tổ chức hoặc khách hàng mà quyền có hiệu lực |
| `account_id` | Tài khoản đích ổn định |
| `recovery_request_id` | Quy trình khôi phục đã phát hành token |
| `purpose` | Thao tác cụ thể được phép thực hiện |
| `recovery_epoch` | Phiên bản quyền khôi phục của tài khoản khi phát hành |
| `expires_at` | Hạn cuối sử dụng |
| `state` | Quyền còn hoạt động, đã dùng hay đã bị thu hồi |
| Tham chiếu đối tượng phụ | Yếu tố xác thực hoặc bước đăng ký cụ thể, nếu nghiệp vụ cần |

Ví dụ:

```text
tenant = organization-1
account = account-A
request = request-18
purpose = RESET_PASSWORD
```

Quyền này không tự cho phép:

- Đặt lại mật khẩu của account-A ở một tenant khác.
- Xóa MFA của account-A.
- Thêm passkey cho account-B.
- Dùng lại token trong một quy trình khôi phục đã bị hủy hoặc thay thế.

Các giá trị trong URL, header hoặc body là đầu vào cần kiểm tra. Tenant đích phải được xác định theo cơ chế tin cậy của ứng dụng và đối chiếu với tenant của token. Một header do trình duyệt tự chọn không đủ để tạo quyền truy cập tenant.

Nếu kiến trúc dùng một danh tính toàn cục và nhiều membership theo tenant, cần nêu rõ thao tác đang thay đổi credential toàn cục hay một thiết lập riêng của tenant. Không phát hành một quyền có phạm vi tenant rồi để nó âm thầm thay đổi credential dùng chung cho toàn hệ thống.

### Mục đích cần hẹp theo loại khôi phục

```text
RESET_PASSWORD
REPLACE_MFA_FACTOR
ENROLL_REPLACEMENT_PASSKEY
REGISTER_REPLACEMENT_DEVICE
```

Đây là các tên minh họa, không phải danh sách bắt buộc. Điểm quan trọng là endpoint kiểm tra đúng quyền mà nó yêu cầu. Token đặt lại mật khẩu không được mặc nhiên coi là quyền thay thế mọi yếu tố xác thực.

## 5. Mô hình token opaque và bản ghi phía máy chủ

Một cách triển khai là phát hành token opaque: phía client giữ một chuỗi ngẫu nhiên, còn ý nghĩa và phạm vi quyền nằm trong dữ liệu được máy chủ quản lý.

Có thể chia token thành:

```text
token = selector.secret
```

Trong đó:

- `selector` giúp tìm bản ghi token; bản thân nó không cấp quyền.
- `secret` là bí mật đủ entropy, được sinh bằng nguồn ngẫu nhiên mật mã.
- Database giữ bộ kiểm chứng bí mật thay vì raw token.

Ví dụ lựa chọn thiết kế: dùng 32 byte ngẫu nhiên cho phần secret, sau đó mã hóa bằng Base64url. Con số này là một cấu hình minh họa; vẫn cần kiểm tra cách sinh, truyền, lưu và giới hạn lạm dụng.

Một bản ghi khái niệm:

```json
{
  "tokenRecordId": "rt_demo_42",
  "selector": "sel_demo_42",
  "secretVerifier": "BO_KIEM_CHUNG_KHONG_PHAI_RAW_TOKEN",
  "verifierKeyId": "recovery-key-3",
  "tenantId": "tenant_demo_1",
  "accountId": "account_demo_A",
  "recoveryRequestId": "request_demo_18",
  "purpose": "RESET_PASSWORD",
  "recoveryEpoch": 7,
  "state": "ACTIVE",
  "expiresAt": "2026-01-01T03:10:00Z"
}
```

Các giá trị trên là dữ liệu giả.

Một lựa chọn để xây dựng bộ kiểm chứng:

```text
secretVerifier = HMAC(
    server_key,
    canonicalEncode("recovery-token:v1", selector, secret)
)
```

`canonicalEncode` biểu thị cách mã hóa các trường có ranh giới rõ ràng; không nối các chuỗi có độ dài tùy ý theo cách gây nhập nhằng. Khóa HMAC cần được quản lý tách biệt khỏi dữ liệu token, với quy tắc chọn khóa và luân chuyển rõ ràng.

HMAC trong ví dụ bảo vệ việc kiểm chứng secret. **Ràng buộc tài khoản vẫn được thực thi bằng bản ghi có thẩm quyền và logic cấp quyền của máy chủ.** Công thức trên không tự bảo vệ mọi cột trong database trước một kẻ có quyền sửa dữ liệu. Kho token và các quan hệ tài khoản phải được kiểm soát truy cập và bảo vệ tính toàn vẹn.

Với token ngẫu nhiên entropy cao, một thiết kế dùng hàm băm mật mã để lưu bộ kiểm chứng cũng có thể phù hợp. Mã số ngắn có không gian đoán nhỏ cần phân tích khác: giới hạn số lần thử, giới hạn tần suất và ràng buộc đúng yêu cầu là thiết yếu. Không lấy thiết kế cho token ngẫu nhiên dài rồi áp dụng nguyên xi cho OTP ngắn.

## 6. Xác minh token phải tạo ra ngữ cảnh có thẩm quyền

Kết quả xác minh không nên chỉ là `true` hoặc `false`. Lớp nghiệp vụ cần biết chính xác quyền nào đã được xác minh.

Một mô hình kết quả:

```text
VerifiedRecoveryGrant {
    tokenRecordId
    tenantId
    accountId
    recoveryRequestId
    purpose
    recoveryEpoch
    expiresAt
}
```

Chỉ thành phần xác minh phía máy chủ được tạo ngữ cảnh này sau khi kiểm tra đầy đủ. Không bind trực tiếp JSON do client gửi vào kiểu `VerifiedRecoveryGrant`, vì tên kiểu không biến dữ liệu đầu vào thành bằng chứng.

Luồng xác minh cần:

1. Giới hạn kích thước và kiểm tra định dạng token trước khi xử lý sâu.
2. Tìm bản ghi bằng selector, không coi việc tìm thấy bản ghi là đã xác thực.
3. Tính lại và so sánh bộ kiểm chứng bằng cơ chế phù hợp để hạn chế rò rỉ qua phép so sánh secret.
4. Kiểm tra token còn hoạt động và còn hạn theo thời gian có thẩm quyền.
5. Kiểm tra tài khoản, tenant và yêu cầu khôi phục còn hợp lệ.
6. Kiểm tra mục đích đúng với thao tác được gọi.
7. Kiểm tra phiên bản khôi phục và các điều kiện chính sách còn hiệu lực.
8. Tạo ngữ cảnh từ dữ liệu đã xác minh, không từ email hoặc ID thay thế của client.

Việc xác minh trước khi hiển thị form có ích cho trải nghiệm, nhưng không thay thế xác minh lúc ghi thay đổi cuối cùng. Trong khoảng thời gian người dùng nhập mật khẩu, token có thể đã hết hạn, bị dùng hoặc bị thu hồi.

### ID trong request được xử lý thế nào?

Nếu đường dẫn là:

```text
POST /accounts/{accountId}/password-recovery/complete
```

thì `accountId` phải khớp với tài khoản trong quyền đã xác minh. Một lựa chọn khác là dùng endpoint không nhận tài khoản đích:

```text
POST /password-recovery/complete
```

Máy chủ lấy tài khoản từ token. Cả hai cách đều cần kiểm tra đầy đủ; endpoint ngắn hơn chỉ giúp giảm một nguồn nhầm lẫn.

## 7. Thực hiện thay đổi và tiêu thụ token trong cùng ranh giới nhất quán

Ràng buộc đúng tài khoản phải được giữ đến lúc cập nhật dữ liệu, kể cả khi có nhiều request chạy đồng thời.

Mã giả sau giả định tài khoản, token và yêu cầu khôi phục cùng nằm trong một database hỗ trợ giao dịch:

```text
completePasswordRecovery(rawToken, trustedTenantContext, newPassword):
    parse và giới hạn kích thước rawToken
    chuẩn bị passwordHash theo chính sách mật khẩu của hệ thống

    BEGIN TRANSACTION

    đọc và khóa token, account, recovery_request
        theo thứ tự khóa thống nhất của ứng dụng

    xác minh secret của token
    xác minh token ACTIVE và chưa hết hạn
    xác minh tenant của token khớp trustedTenantContext
    xác minh token.purpose == RESET_PASSWORD
    xác minh request thuộc cùng tenant và account với token
    xác minh request còn cho phép hoàn tất
    xác minh account còn hợp lệ
    xác minh token.recovery_epoch == account.recovery_epoch

    targetTenant = token.tenant_id
    targetAccount = token.account_id

    cập nhật password_hash của đúng targetTenant + targetAccount
    chuyển token sang CONSUMED
    xử lý các quyền khôi phục liên quan theo chính sách
    ghi ý định thông báo và xử lý session cần thiết

    COMMIT
```

Mật khẩu mới được băm bằng cơ chế lưu mật khẩu của ứng dụng; không dùng bộ kiểm chứng token để lưu mật khẩu. Việc chuẩn bị hash ngoài giao dịch có thể giảm thời gian giữ khóa, còn điều kiện cấp quyền phải được kiểm tra lại trong ranh giới nhất quán trước lúc cập nhật.

Một thao tác SQL có điều kiện cần sử dụng định danh từ ngữ cảnh máy chủ:

```sql
UPDATE account
SET password_hash = :prepared_password_hash
WHERE tenant_id = :verified_tenant_id
  AND account_id = :verified_account_id
  AND recovery_epoch = :verified_recovery_epoch;
```

Đây là phần minh họa của giao dịch, không phải toàn bộ endpoint. Ứng dụng phải kiểm tra đúng một tài khoản được cập nhật. Nếu điều kiện thất bại, rollback thay vì vẫn đánh dấu token đã dùng.

Khi hai request cùng sử dụng một token, khóa hoặc cập nhật có điều kiện phải bảo đảm chỉ một lần hoàn tất thành công. Khi một request thu hồi token chạy đồng thời, quyết định phải dựa trên trạng thái được tuần tự hóa, thay vì một bản sao cache cũ.

Nếu credential và token nằm ở hai dịch vụ khác nhau, cần thiết kế cơ chế phối hợp, idempotency và khôi phục lỗi riêng. Một giao dịch ở kho token không tự làm cho cập nhật credential ở dịch vụ khác trở nên nguyên tử.

## 8. Giữ ràng buộc qua các bước trung gian

Luồng khôi phục thường gồm nhiều bước: xác minh liên kết, hiển thị form, yêu cầu bằng chứng bổ sung rồi cập nhật thông tin xác thực.

### Tránh mất tài khoản đích giữa các bước

Một lỗi phổ biến:

```text
Bước 1: xác minh token của A
Bước 2: lưu session.recoveryAllowed = true
Bước 3: nhận accountId từ form và thực hiện thay đổi
```

Cờ boolean đã làm mất tài khoản và mục đích đã xác minh. Bước 3 có thể bị chuyển sang B.

Nếu chuyển token sang phiên khôi phục giới hạn, phiên phải giữ tham chiếu có thẩm quyền đến:

```text
tenant + account + request + purpose + expiry + trạng thái quyền
```

Client có thể giữ một cookie opaque để tham chiếu phiên. Các thuộc tính cấp quyền phải được bảo vệ phía máy chủ hoặc bằng cơ chế toàn vẹn phù hợp. Cần định nghĩa rõ lúc trao đổi có tiêu thụ token gốc hay không và cách vô hiệu hóa phiên thay thế sau khi hoàn tất.

### Nhiều tab và nhiều tài khoản

Người dùng có thể mở liên kết của A ở tab thứ nhất rồi liên kết của B ở tab thứ hai. Một biến session toàn cục như `currentRecoveryAccount` có thể bị tab sau ghi đè.

Mỗi quy trình cần định danh riêng. Form hoàn tất phải tham chiếu đúng quy trình đã được xác minh; máy chủ kiểm tra nó cùng ngữ cảnh phiên và quyền hiện hành.

Nếu trình duyệt đang đăng nhập B nhưng mở token của A, hệ thống cần chính sách xử lý xung đột rõ ràng, chẳng hạn yêu cầu chuyển luồng hoặc kết thúc phiên hiện tại trước khi tiếp tục. Không lấy tài khoản đang đăng nhập làm đích cập nhật và không tự cấp phiên đầy đủ cho A chỉ vì mở liên kết.

Một request GET hiển thị trang cũng không nên tự hoàn tất thay đổi credential. Các thao tác ghi cần thể hiện ý định phù hợp và có biện pháp bảo vệ request tương ứng với cơ chế cookie, phiên và giao diện đang dùng.

## 9. Thay đổi tài khoản, thu hồi và giới hạn của binding

### Khi dữ liệu nhận dạng thay đổi

Khi email hoặc số điện thoại thay đổi, máy chủ cần phân biệt:

- Tham chiếu tài khoản: vẫn là ID nội bộ đã ràng buộc.
- Kênh chuyển token: là kênh đã được chọn theo chính sách ở thời điểm phát hành.
- Hiệu lực token cũ: được quyết định bởi chính sách thu hồi.

Không tự chuyển một token đang tồn tại sang địa chỉ mới do một request hoàn tất khôi phục cung cấp. Nếu cần thay đổi kênh khôi phục, phải có quy trình và bằng chứng tương ứng.

### Phiên bản khôi phục của tài khoản

Một cơ chế có thể dùng là lưu `recovery_epoch` trên tài khoản và chụp giá trị này vào token khi phát hành. Khi một sự kiện bảo mật phù hợp xảy ra, hệ thống tăng epoch; token mang phiên bản cũ bị từ chối khi sử dụng.

Ví dụ:

```text
account.recovery_epoch = 7
token.recovery_epoch = 7
=> khớp phiên bản

sau một lần khôi phục đã được xác minh:
account.recovery_epoch = 8

token cũ vẫn mang 7
=> từ chối
```

Đây là một lựa chọn thu hồi theo nhóm, cần áp dụng nhất quán ở các đường sử dụng token. Không tăng phiên bản chỉ vì bất kỳ ai gửi yêu cầu quên mật khẩu công khai, nếu điều đó cho phép kẻ tấn công liên tục phá quy trình hợp lệ của chủ tài khoản.

### Binding không ngăn mọi hành vi chiếm đoạt

Nếu kẻ tấn công đánh cắp token của A, ràng buộc tài khoản khiến token tiếp tục chỉ tác động A. Nó không chứng minh người đang giữ token là chủ tài khoản.

Vì vậy, vẫn cần bảo vệ kênh gửi, ngăn lộ bí mật qua log và URL, kiểm soát thời hạn, chống đoán, thu hồi và bổ sung bằng chứng khi mức rủi ro yêu cầu.

IP, User-Agent hoặc tên thiết bị có thể là tín hiệu đánh giá rủi ro, nhưng không nên được coi là danh tính tài khoản. Người dùng hợp lệ có thể đổi mạng hoặc dùng thiết bị mới trong chính quá trình khôi phục.

### Nếu dùng token tự chứa

Với một token có chữ ký chứa các claim như `sub`, tenant, mục đích và thời hạn, máy chủ phải xác minh tính toàn vẹn và toàn bộ điều kiện chấp nhận trước khi sử dụng claim. Không lấy `sub` từ một payload chỉ mới được decode.

Chữ ký cũng không tự bảo đảm dùng một lần hoặc thu hồi ngay. Nếu quyền khôi phục yêu cầu các thuộc tính đó, cần trạng thái hoặc cơ chế kiểm soát tương ứng. Mọi bước trung gian vẫn phải giữ nguyên tài khoản và phạm vi đã xác minh.

## 10. Các tình huống minh họa hợp đồng cấp quyền

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Token của A, body yêu cầu thay mật khẩu B | Từ chối sai đối tượng; không sửa A hoặc B ngoài thao tác được cấp |
| Token của A, email A đã đổi | Xác định A bằng ID ổn định, rồi xét hiệu lực theo chính sách thu hồi |
| Cùng email xuất hiện ở hai tenant | Chỉ chấp nhận đúng tenant và đối tượng của token |
| Token đặt lại mật khẩu được gửi đến API thay MFA | Từ chối sai mục đích |
| Token của tài khoản đã xóa | Từ chối; không ánh xạ sang tài khoản mới |
| Token còn hạn nhưng đã dùng | Từ chối lần sử dụng tiếp theo |
| Token cũ sau khi epoch đã tăng | Từ chối do quyền khôi phục đã lỗi thời |
| Đăng nhập B rồi mở liên kết của A | Xử lý xung đột theo chính sách; không cập nhật B |
| Hai tab mở hai quy trình khác nhau | Mỗi form hoàn tất vẫn trỏ đúng quy trình và tài khoản |
| Thay selector nhưng giữ nguyên secret | Không vượt qua kiểm chứng của bản ghi đích |
| Sửa account ID trong ngữ cảnh do client gửi | Không tạo được ngữ cảnh máy chủ đã xác minh |
| Hai request hoàn tất đồng thời | Chỉ một lần sử dụng quyền một lần được thành công |

Phản hồi ra ngoài nên tránh tiết lộ tài khoản nào tồn tại hoặc token thực sự thuộc tài khoản nào. Audit nội bộ có thể lưu định danh bản ghi token, tenant, account, request, mục đích và lý do từ chối theo quyền truy cập phù hợp. Không ghi raw token, mật khẩu mới hoặc cookie khôi phục.

Ràng buộc tài khoản được duy trì xuyên suốt khi cùng một đối tượng đã xác minh được dùng để chọn yêu cầu, kiểm tra quyền, tạo phiên khôi phục và ghi thay đổi cuối cùng. Mỗi lần một bước lấy lại tài khoản từ dữ liệu client, hệ thống có nguy cơ làm mất ràng buộc đó.
