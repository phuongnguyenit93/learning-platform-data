# Recovery token purpose — Mục đích và quyền hạn của token khôi phục

**Recovery token** là một giá trị mà hệ thống cấp và kiểm tra để cho phép người yêu cầu thực hiện một bước xác định trong luồng khôi phục tài khoản. Bước đó có thể là chứng minh đã nhận được liên kết ở một kênh recovery, tiếp tục hồ sơ đã được kiểm tra, đặt mật khẩu mới hoặc đăng ký yếu tố xác thực thay thế.

Điều quan trọng không chỉ là token có hợp lệ hay không, mà là **hợp lệ để làm gì, cho tài khoản nào và trong hoàn cảnh nào**.

Ví dụ, một liên kết cho phép đặt mật khẩu mới không nên đồng thời cho phép tắt MFA, thay email và lấy access token đọc toàn bộ dữ liệu. Token có chữ ký đúng hoặc còn hạn chưa đủ để cấp những quyền ngoài mục đích đã được cho phép.

Trong bài này, các tên purpose, mô hình dữ liệu và API là thiết kế minh họa. Chúng giúp mô tả ranh giới quyền; không phải một giao thức recovery chuẩn dùng chung cho mọi dịch vụ.

## 1. Token chuyển một quyền cụ thể qua các bước của recovery

Một luồng recovery thường bắt đầu khi người dùng chưa thể xác thực theo cách thông thường. Dịch vụ cần chuyển một lượng quyền có giới hạn qua các bước mà không mở toàn bộ tài khoản.

Có thể hiểu token như một **capability có phạm vi**:

- Máy chủ xác định thao tác được phép.
- Token đại diện cho khả năng yêu cầu thao tác ấy trong các điều kiện đã định.
- Endpoint nhận token phải kiểm tra cả tính hợp lệ lẫn phạm vi.
- Quyền chấm dứt khi token bị dùng, hết hạn, thu hồi hoặc không còn phù hợp với trạng thái hồ sơ.

Đối với bearer token, ai có giá trị token có thể sử dụng quyền tương ứng nếu đáp ứng các điều kiện còn lại. Vì vậy, token phải được bảo vệ như một bí mật, dù giao diện chỉ hiển thị nó dưới dạng một đường dẫn.

### Token chứng minh điều gì?

Một token gửi qua email có thể cung cấp bằng chứng rằng người nộp có được bí mật đã gửi tới kênh đó. Nó không tự chứng minh danh tính ngoài đời hoặc đảm bảo email chưa bị người khác truy cập.

Một token được cấp sau khi hồ sơ recovery đã đáp ứng chính sách có thể đại diện cho quyền thực hiện bước tiếp theo. Độ tin cậy của quyết định vẫn phụ thuộc vào bằng chứng và chính sách trước lúc cấp.

Không nên có quy tắc chung “cứ có token hợp lệ là coi như đã xác thực đầy đủ”.

NIST mô tả recovery là quy trình lấy lại khả năng xác thực khi mất quyền kiểm soát các authenticator cần thiết; quy trình có thể sử dụng nhiều loại bằng chứng và dẫn tới ràng buộc authenticator mới. Vì vậy, token trong một bước không nên bị hiểu là toàn bộ quy trình. [NIST SP 800-63B-4, Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery)

## 2. Phân biệt các loại token thường gặp

Cùng là chuỗi ngẫu nhiên hoặc JWT, các token vẫn có mục đích khác nhau:

| Loại | Mục đích minh họa | Không mặc nhiên cho phép |
| --- | --- | --- |
| Access token | Truy cập tài nguyên theo quyền đã cấp | Khôi phục mọi yếu tố xác thực |
| Refresh token | Xin token mới theo quan hệ ủy quyền tương ứng | Thay thế recovery khi các điều kiện không còn đáp ứng |
| Token xác nhận địa chỉ mới | Chứng minh có thể nhận tại địa chỉ mới | Chứng minh quyền sở hữu tài khoản cần thay địa chỉ |
| Recovery challenge token | Cung cấp bằng chứng cho một challenge của hồ sơ | Hoàn tất mọi yêu cầu recovery |
| Password reset token | Cho đặt mật khẩu mới trong phạm vi cho phép | Tắt MFA, đổi contact hoặc đăng nhập đầy đủ |
| Token tiếp tục recovery | Cho đi tiếp trong hồ sơ và bước được cấp | Gọi API nghiệp vụ như một session thông thường |
| Token đăng ký yếu tố thay thế | Cho thực hiện một hành động ràng buộc authenticator đã được phê duyệt | Tự tái tạo private key bị mất hoặc thay mọi cấu hình bảo mật |

Định dạng không quyết định quyền. Hai giá trị cùng có cấu trúc JWT không được thay thế cho nhau chỉ vì cùng được một dịch vụ ký.

Cũng không nên gọi một mã cứu hộ đã cấp từ trước và một liên kết vừa gửi qua email là cùng một loại chỉ vì người dùng đều nhập hoặc bấm vào chúng. Thời điểm cấp, cách giữ bí mật, kênh phân phối và điều kiện sử dụng khác nhau có thể làm chúng đóng vai trò khác nhau trong policy.

## 3. Xác định purpose trước khi phát token

Một hợp đồng purpose cần trả lời được:

> Token này cho phép chủ thể nào yêu cầu hành động nào, trên đối tượng nào, ở bước nào và đến khi nào?

Ví dụ về các purpose do ứng dụng định nghĩa:

| Purpose | Quyền được cấp | Điều kiện còn phải kiểm |
| --- | --- | --- |
| `VERIFY_RECOVERY_CHALLENGE` | Nộp bí mật của một challenge | Đúng hồ sơ, kênh, thời hạn và trạng thái challenge |
| `SET_NEW_PASSWORD` | Đặt mật khẩu mới cho tài khoản đã ràng buộc | Hồ sơ và chính sách vẫn cho phép thay mật khẩu |
| `CONTINUE_RECOVERY` | Tiếp tục các bước được liệt kê của một hồ sơ | Bước tiếp theo và bằng chứng bắt buộc còn hợp lệ |
| `ENROLL_REPLACEMENT_AUTHENTICATOR` | Thực hiện quy trình đăng ký yếu tố thay thế | Đúng loại yếu tố, đúng hồ sơ và hoàn tất giao thức đăng ký |
| `CANCEL_RECOVERY_CASE` | Yêu cầu hủy đúng hồ sơ được cấp quyền | Đủ điều kiện hủy theo policy, không ảnh hưởng hồ sơ khác |

Các giá trị này là ví dụ nội bộ. Purpose cần có ngữ nghĩa rõ thay vì một nhãn rộng như `ACCOUNT_RECOVERY_ALL`.

### Ai được quyết định purpose?

Người dùng có thể chọn ý định “quên mật khẩu” hoặc “mất thiết bị MFA”. Tuy nhiên, máy chủ quyết định quy trình và quyền thực sự được cấp.

Không lấy `purpose` do client gửi rồi gắn trực tiếp vào một token có quyền tương ứng. Cũng không để endpoint hoàn tất đọc `expectedPurpose` từ body để tự khẳng định rằng token đáp ứng điều kiện.

Ví dụ:

```text
Sai:
    expectedPurpose = request.body.purpose
    accept token if token.purpose == expectedPurpose

Phù hợp hơn:
    expectedPurpose = SET_NEW_PASSWORD
    accept token only under the password-reset endpoint policy
```

Giá trị expected purpose đến từ endpoint hoặc chính sách máy chủ đã xác định. Request có thể cung cấp dữ liệu cho thao tác, nhưng không được tự định nghĩa thẩm quyền của thao tác đó.

## 4. Một token cần nhiều ràng buộc hơn trường purpose

Purpose trả lời “được làm gì”, nhưng chưa trả lời “làm cho ai” hay “được dùng ở đâu”.

| Ràng buộc | Câu hỏi | Ví dụ lỗi nếu thiếu |
| --- | --- | --- |
| Subject hoặc tài khoản đích | Token tác động đến tài khoản nào? | Token của A được dùng để đổi mật khẩu B |
| Tenant | Tài khoản thuộc không gian tổ chức nào? | Nhầm tài khoản có cùng định danh hiển thị ở hai tenant |
| Hồ sơ recovery | Token thuộc lượt khôi phục nào? | Dùng token từ hồ sơ cũ cho một yêu cầu mới |
| Purpose | Hành động nào được phép? | Token xác nhận email được dùng để reset MFA |
| Audience | Thành phần nhận nào được phép xử lý? | Một dịch vụ khác chấp nhận token ngoài ngữ cảnh |
| Bước và phạm vi hành động | Thao tác cụ thể nào đang được thực hiện? | Đổi ý định sau khi đã nhận chấp thuận |
| Thời hạn | Token còn được phép dùng không? | Liên kết cũ vẫn đổi được thông tin |
| Thế hệ hoặc phiên bản trạng thái | Hồ sơ, tài khoản đã thay đổi chưa? | Token còn hạn nhưng được phát trước khi recovery bị thu hồi |
| Trạng thái sử dụng | Quyền đã được tiêu thụ chưa? | Hai request cùng hoàn tất một quyền dùng một lần |

Không nhất thiết mọi ràng buộc đều phải xuất hiện trong chuỗi token. Với opaque token, chúng có thể nằm ở bản ghi máy chủ được tra cứu bằng giá trị kiểm tra bí mật. Với token tự chứa, một phần có thể nằm trong claims nhưng vẫn cần xem xét trạng thái có thể thay đổi.

Nếu một hành động đã có tham số đích được phê duyệt, chẳng hạn một địa chỉ contact cụ thể, quyền phải ràng buộc với tham số ấy hoặc một tham chiếu bất biến tương ứng. Không cho thay đích sau khi nhận token mà vẫn giữ cùng thẩm quyền.

Ngược lại, không cần đưa mật khẩu mới vào token trước khi người dùng chọn mật khẩu. Hợp đồng `SET_NEW_PASSWORD` cho phép nộp một mật khẩu mới đáp ứng policy cho đúng tài khoản; nó không yêu cầu lưu bí mật mới trong URL.

## 5. Ví dụ hợp đồng của một password reset token

Sau khi phát một opaque token, máy chủ có thể lưu metadata như sau:

```json
{
  "tokenRef": "rt_example_opaque",
  "subjectAccountRef": "acc_example_opaque",
  "tenantRef": "tenant_example",
  "recoveryCaseRef": "rc_example_opaque",
  "purpose": "SET_NEW_PASSWORD",
  "audience": "password-reset-service",
  "recoveryGeneration": 4,
  "state": "ISSUED",
  "issuedAt": "2026-11-23T10:00:00Z",
  "expiresAt": "2026-11-23T10:15:00Z"
}
```

Đây là metadata minh họa, không phải secret thật hoặc payload bắt buộc. Thời hạn 15 phút chỉ là một lựa chọn ví dụ, không phải giá trị chuẩn cho mọi kênh hoặc mọi loại recovery.

Giá trị token thực tế không cần chứa email, ngày sinh hoặc toàn bộ hồ sơ. Nếu token có đủ độ ngẫu nhiên, hệ thống có thể lưu giá trị kiểm tra một chiều thay vì lưu secret nguyên văn. Cách bảo vệ mã ngắn cần đánh giá riêng khả năng đoán trực tuyến và ngoại tuyến.

Một request hoàn tất có thể có dạng:

```http
POST /recovery/password/complete
Content-Type: application/json

{
  "token": "<password-reset-secret>",
  "newPassword": "<new-password>"
}
```

Trong phương án này, tài khoản đích được lấy từ bản ghi token đã kiểm tra. Không cần cho client chọn thêm một `accountId` khác trong cùng request.

Nếu hệ thống có nhiều tenant, tenant phải được xác định và đối chiếu từ ngữ cảnh tin cậy. Một header tùy ý do client khai không được dùng để thay thế tenant đã ràng buộc trong token.

## 6. Phát token và chấp nhận token là hai quyết định khác nhau

Một số token được phát trước khi hệ thống có bằng chứng rằng người yêu cầu kiểm soát kênh recovery. Liên kết được gửi tới địa chỉ đã đăng ký chính là challenge để thu bằng chứng đó.

Một số token khác chỉ được phát sau khi đã đánh giá đủ bằng chứng và cho phép một hành động tiếp theo.

| Giai đoạn | Quyết định máy chủ |
| --- | --- |
| Nhận yêu cầu recovery | Có cho mở hồ sơ và gửi challenge theo giới hạn không? |
| Phát challenge | Secret được gửi tới kênh nào đã được policy cho phép? |
| Người yêu cầu nộp secret | Secret có khớp, còn hiệu lực và thuộc đúng hồ sơ không? |
| Đánh giá bằng chứng | Bằng chứng hiện có đã đủ cho hành động cần thực hiện chưa? |
| Phát grant hành động | Quyền hẹp nào được cấp cho bước tiếp theo? |
| Dùng grant | Trạng thái hiện tại còn cho phép thực hiện đúng hành động ấy không? |

Không nên xem việc mở hồ sơ hoặc gửi được email là đã xác minh người yêu cầu. Cũng không nên phát token có quyền rộng chỉ vì hệ thống đã phát một challenge thành công.

Với tài khoản có MFA, một password reset token không nhất thiết đủ để thay thế yếu tố thứ hai. Policy cần xác định bằng chứng cho từng hành động; không kế thừa quyền ngoài phạm vi bằng cách dùng cùng từ “recovery”.

OWASP yêu cầu token reset phải được sinh an toàn, bảo vệ khi lưu, có hạn phù hợp và dùng một lần. Các đặc tính này bảo vệ secret, còn việc giới hạn đúng hành động vẫn là trách nhiệm của thiết kế quyền. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

## 7. Xác thực token đúng purpose ở phía máy chủ

Một quy trình kiểm tra tổng quát:

1. Kiểm tra định dạng và giới hạn đầu vào.
2. Tra cứu hoặc kiểm tra tính xác thực mật mã theo loại token mà endpoint chấp nhận.
3. Xác định tài khoản, tenant và hồ sơ từ nguồn đã được bảo vệ.
4. So khớp purpose và audience với hợp đồng của endpoint.
5. Kiểm tra thời hạn, trạng thái sử dụng và điều kiện thu hồi.
6. Kiểm tra trạng thái hiện tại của hồ sơ và thế hệ recovery.
7. Đánh giá điều kiện nghiệp vụ còn lại.
8. Thực hiện đúng hành động và tiêu thụ quyền theo cơ chế chống dùng lặp.

Pseudocode cho một mô hình opaque token:

```text
completePasswordReset(rawToken, newPassword):
    enforceInputLimits()
    enforceRecoveryAttemptBudget()

    tokenRef = deriveLookupReference(rawToken)
    candidate = findRecoveryToken(tokenRef)
    require candidate exists

    validateNewPasswordUnderCurrentPolicy(newPassword)
    preparedPasswordHash = preparePasswordHash(newPassword)

    begin transaction
        account = lockAccount(candidate.subjectAccountRef)
        case = lockRecoveryCase(candidate.recoveryCaseRef)
        token = lockRecoveryToken(candidate.id)

        require token secret matches rawToken
        require token.purpose == SET_NEW_PASSWORD
        require token.audience == PASSWORD_RESET_SERVICE
        require token.subjectAccountRef == account.id
        require token.tenantRef == account.tenantRef
        require token.recoveryCaseRef == case.id
        require case.accountRef == account.id
        require case.tenantRef == account.tenantRef
        require token.state == ISSUED
        require serverNow < token.expiresAt
        require case is eligible for password reset
        require token.recoveryGeneration == case.currentGeneration
        require current policy permits this password change

        set the new password hash for account
        mark token CONSUMED
        apply the configured invalidation for related reset artifacts
        record required session and notification actions
    commit
```

Pseudocode chỉ thể hiện ranh giới quyền và transaction; không phải mã triển khai hoàn chỉnh. Khi dùng thực tế, thao tác tra cứu và so khớp secret phải phù hợp với cách lưu token, không ghi secret vào log. Việc kiểm tra điều kiện quan trọng phải dựa trên các bản ghi hiện tại trong transaction, không chỉ dựa vào bản tra cứu ban đầu.

Đổi mật khẩu và tiêu thụ token cần có kết quả nhất quán: không được đổi thành công nhưng để token tiếp tục đổi lần nữa. Khi có nhiều request đồng thời, cơ chế khóa hoặc cập nhật có điều kiện phải bảo đảm chỉ quyền hợp lệ được thực thi theo chính sách dùng một lần.

Các tác vụ gửi thông báo có thể đi qua outbox để tránh phụ thuộc việc gửi email trong transaction. Nếu việc vô hiệu hóa session nằm ở thành phần khác, cần cơ chế đồng bộ và cưỡng chế phiên bản bảo mật phù hợp; không tuyên bố session đã bị chặn tức thì chỉ vì đã phát một sự kiện.

## 8. Hạn dùng, tiêu thụ và thu hồi phục vụ mục đích khác nhau

| Cơ chế | Điều được kiểm soát |
| --- | --- |
| Hết hạn | Quyền không tồn tại quá thời điểm đã xác định |
| Tiêu thụ | Một quyền dùng một lần không được thực hiện lại |
| Thu hồi | Chấm dứt quyền trước hạn khi bối cảnh thay đổi |
| Kiểm thế hệ hoặc phiên bản | Loại bỏ token được phát cho trạng thái cũ |
| Giới hạn mục đích | Ngăn token hợp lệ bị dùng cho hành động khác |

Một token còn hạn có thể đã được tiêu thụ. Một token chưa dùng có thể đã bị thu hồi. Token chưa hết hạn và chưa dùng vẫn phải bị từ chối nếu sai purpose.

Ví dụ về lý do thu hồi theo chính sách:

- Người dùng hủy hồ sơ recovery.
- Một hồ sơ mới thay thế hồ sơ trước.
- Có báo cáo đáng tin về kênh nhận bị chiếm.
- Tài khoản hoặc cấu hình recovery thay đổi làm token cũ không còn phù hợp.
- Hành động đã hoàn tất bằng phương thức khác.

Không cần vô hiệu hóa mọi token khi bất kỳ ai bấm “quên mật khẩu”. Người ngoài có thể lặp hành động đó để gây gián đoạn. Cần xác định rõ thời điểm và thẩm quyền làm thay đổi các thế hệ token.

### “Dùng một lần” phải xác định dùng tại bước nào

Có hai thiết kế minh họa:

**Thực hiện trực tiếp:** token được tiêu thụ cùng thao tác đặt mật khẩu mới.

**Đổi sang phiên hẹp:** token được tiêu thụ khi đổi lấy một recovery session hoặc grant ngắn hạn. Quyền đặt mật khẩu lúc này nằm ở session hoặc grant mới và vẫn cần giới hạn, thời hạn cùng cơ chế hoàn tất riêng.

Không giữ cả token gốc và quyền mới đều có thể thực hiện lại cùng hành động mà không có kiểm soát. Chuyển từ token sang cookie không tự làm giảm quyền nếu cookie được middleware coi như đăng nhập đầy đủ.

Không tiêu thụ quyền nhạy cảm chỉ vì một request GET tải trang. Trình xem trước liên kết hoặc bộ quét email có thể truy cập liên kết trước người dùng. Việc xem trang cần được tách khỏi thao tác xác nhận có chủ ý; các request thay đổi trạng thái còn cần cơ chế chống CSRF phù hợp với cách mang credential.

OWASP có mô tả phiên giới hạn chỉ cho reset mật khẩu. Ý nghĩa cần giữ là phiên đó chỉ có quyền cho thao tác recovery được cấp. [OWASP Forgot Password Cheat Sheet, PINs](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#pins)

## 9. Purpose không được chỉ tồn tại trên nhãn hoặc giao diện

Một email viết “liên kết đặt mật khẩu” không có tác dụng giới hạn nếu API phía sau chấp nhận token cho mọi hành động.

Một đường dẫn mang tên `/recovery/password` cũng chưa đủ nếu service dùng chung chỉ kiểm token có chữ ký hợp lệ rồi trả một principal có toàn quyền.

Cần giữ ranh giới ở các lớp:

| Lớp | Trách nhiệm |
| --- | --- |
| Phát token | Chọn purpose và đối tượng theo policy |
| Lưu hoặc ký | Bảo vệ metadata ràng buộc với secret |
| Validator của endpoint | Từ chối token ngoài loại và ngữ cảnh được chấp nhận |
| Service nghiệp vụ | Kiểm quyền cho đúng hành động và trạng thái hiện tại |
| Middleware | Không biến recovery principal thành session đăng nhập đầy đủ |
| API nghiệp vụ khác | Không chấp nhận credential recovery để đọc hoặc sửa dữ liệu ngoài phạm vi |

Trong một ứng dụng Java có tầng security chung, việc một đối tượng `Authentication` mang trạng thái đã xác thực chưa đủ để chứng minh nó có mọi quyền tài khoản. Có thể cần loại principal hoặc authority riêng cho recovery; API nghiệp vụ vẫn phải yêu cầu quyền phù hợp.

Ví dụ, một principal chỉ có quyền `RECOVERY_SET_PASSWORD` không được tự nhận `ACCOUNT_READ`, `MFA_DISABLE` hoặc `RECOVERY_CONTACTS_EDIT`.

Đây là ví dụ mô hình phân quyền, không phải cấu hình bắt buộc của một framework cụ thể.

## 10. Opaque token và JWT đều phải giữ ranh giới purpose

### Opaque token

Client giữ một giá trị không tự mô tả. Máy chủ tra cứu bản ghi để biết quyền.

Ưu điểm cho việc giới hạn purpose là metadata và trạng thái có thể được quản lý tập trung. Tuy nhiên, nếu cùng một hàm tra cứu trả “token đúng” mà bỏ qua purpose, opaque token vẫn bị dùng sai ngữ cảnh.

### JWT

JWT có thể mang subject, audience, thời hạn và các claim do ứng dụng định nghĩa. Nếu được ký, người nhận cần kiểm tra tính xác thực mật mã và các điều kiện của profile token mà endpoint chấp nhận.

Một claim như `purpose` là hợp đồng của ứng dụng trong ví dụ này, không phải sự bảo đảm có sẵn rằng mọi thư viện sẽ tự kiểm nó.

RFC 8725 khuyến nghị explicit typing và yêu cầu quy tắc xác thực phân biệt các loại JWT để chống dùng token của ngữ cảnh này vào ngữ cảnh khác. Chỉ kiểm chữ ký là chưa đủ. [RFC 8725, mục 3.11–3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.12)

Ví dụ về các biện pháp kết hợp:

- Loại token được nhận diện và thực sự được kiểm tra.
- Audience của recovery khác với audience của API nghiệp vụ.
- Bộ claim bắt buộc và purpose phải đúng profile.
- Issuer và khóa được chọn theo cấu hình tin cậy.
- Trạng thái thu hồi và dùng một lần được quản lý nếu hành động yêu cầu.

Một JWT tự chứa không tự cung cấp trạng thái “chưa từng dùng”. Với quyền dùng một lần hoặc cần thu hồi trước hạn, vẫn cần một cơ chế trạng thái hoặc giao thức tương đương đủ bảo đảm.

Thêm prefix như `reset_` có thể hỗ trợ phân loại nhưng không thay thế kiểm tra. Client có thể thay prefix; quyền phải dựa vào dữ liệu được bảo vệ, không chỉ dựa vào phần tên mà client gửi.

## 11. Giới hạn purpose giúp giảm hậu quả, không làm token bớt nhạy cảm

Nếu token bị lộ, giới hạn purpose có thể ngăn một số hành động ngoài phạm vi. Nhưng quyền đặt mật khẩu hoặc đăng ký authenticator vẫn rất nhạy cảm.

Thiết kế minh họa cần giảm các nơi secret có thể xuất hiện:

- Không ghi token nguyên văn vào application log, access log hoặc audit.
- Không đưa token vào công cụ analytics hoặc nội dung báo lỗi.
- Không tải tài nguyên bên thứ ba không cần thiết trên trang mang secret.
- Không cho redirect tùy ý chuyển secret sang một origin khác.
- Dùng kênh truyền được bảo vệ và cấu hình cache phù hợp với trang recovery.

Nếu token có trong URL, các lớp hạ tầng cần được cấu hình theo thực tế ghi log và chuyển hướng. Đổi token sang phiên hẹp có thể giảm thời gian secret tồn tại trong URL, nhưng phải giữ kiểm soát về quyền và vòng đời đã nêu.

Giao diện cũng nên nói rõ hành động: “Đặt mật khẩu mới” khác với “Lấy lại toàn bộ tài khoản”. Người dùng cần biết một mã đang phục vụ thao tác nào để tránh bị dụ nhập mã recovery vào một ngữ cảnh khác.

Phản hồi công khai cho token sai, hết hạn hoặc đã dùng nên tránh tiết lộ dữ liệu tài khoản không cần thiết. Log nội bộ có thể lưu mã lý do và tham chiếu token để vận hành, nhưng không lưu secret.

## 12. Ba tình huống để xác định đúng purpose

### 12.1. Quên mật khẩu, vẫn còn yếu tố MFA

Minh vẫn dùng được yếu tố MFA nhưng quên mật khẩu. Dịch vụ thực hiện luồng phù hợp để cho đặt mật khẩu mới.

Token có purpose `SET_NEW_PASSWORD` tác động tới đúng tài khoản. Sau khi đặt xong, nó không trở thành bằng chứng cho phép tắt MFA hoặc đổi recovery contact. Khi đăng nhập lại, các điều kiện xác thực của tài khoản tiếp tục được áp dụng.

### 12.2. Mất thiết bị chứa MFA

Minh nhớ mật khẩu nhưng mất điện thoại. Một token từ luồng quên mật khẩu không giải quyết việc chứng minh đủ điều kiện thay yếu tố MFA.

Dịch vụ phải đánh giá phương thức recovery phù hợp. Nếu đã đủ bằng chứng, có thể cấp quyền `ENROLL_REPLACEMENT_AUTHENTICATOR` cho quy trình đã xác định. Người yêu cầu vẫn phải hoàn tất đăng ký và chứng minh kiểm soát yếu tố mới theo cơ chế tương ứng.

### 12.3. Mất toàn bộ phương thức hoặc nghi bị chiếm quyền

Hồ sơ có thể cần nhiều bước xác minh, thời gian chờ hoặc hỗ trợ theo policy. Một token `CONTINUE_RECOVERY` chỉ đưa người yêu cầu đi tiếp ở những bước được cho phép.

Nó không tự chứng minh mọi bằng chứng đã đủ, không cho đọc toàn bộ dữ liệu và không tự vô hiệu hóa các session cũ. Khi quyết định recovery đã được phê duyệt, các quyền hành động cùng kế hoạch xử lý session mới được áp dụng đúng phạm vi.

Nếu private key của một passkey hoặc khóa giải mã thực sự đã mất, một token cấp quyền đăng ký mới không tái tạo khóa cũ. Khôi phục quyền xác thực và phục hồi vật liệu mật mã là hai vấn đề khác nhau.

## 13. Những lỗi thiết kế cần tránh

| Thiết kế | Hậu quả |
| --- | --- |
| Một token dùng chung cho xác nhận email, reset mật khẩu và reset MFA | Quyền của một luồng yếu hơn lan sang hành động nhạy cảm khác |
| Chỉ kiểm chữ ký và thời hạn | Bỏ qua purpose, audience và trạng thái hồ sơ |
| Lấy tài khoản đích từ request mà không đối chiếu token | Token của tài khoản này có thể tác động tài khoản khác |
| Cho client tự khai purpose được phép | Người yêu cầu tự chọn thẩm quyền |
| Đổi token recovery thành session thông thường | Quyền tạm thời biến thành quyền truy cập rộng |
| Coi `exp` là cơ chế dùng một lần | Token có thể dùng lặp trước khi hết hạn |
| Hoàn tất thay đổi rồi mới đánh dấu dùng ở tác vụ sau | Request đồng thời có thể dùng lại quyền |
| Chỉ hạn chế bằng tên URL hoặc nội dung email | Backend vẫn chấp nhận hành động ngoài mục đích |
| Cho sửa phạm vi sau khi cấp token | Quyền cũ bị áp dụng cho một ý định mới |
| Gọi mọi token là “đã xác minh tài khoản” | Các tầng sau hiểu sai mức bằng chứng |

Ranh giới quan trọng là: **token hợp lệ cho một mục đích chỉ có giá trị trong hợp đồng của mục đích đó**. Mỗi endpoint và bước recovery cần thực thi hợp đồng này bằng dữ liệu tin cậy, trạng thái hiện tại và quyền có phạm vi rõ ràng.