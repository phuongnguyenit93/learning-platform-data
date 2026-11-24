# Khôi phục khi mất ứng dụng xác thực

Chủ đề **Authenticator application loss** thuộc chương **Authenticator Recovery**.

Người dùng có thể mất khả năng xác thực sau khi xóa ứng dụng, đặt lại điện thoại, đổi thiết bị hoặc mất máy chứa ứng dụng xác thực. Họ có thể vẫn nhớ mật khẩu nhưng không còn mã dùng cho bước MFA. Một quy trình khôi phục an toàn phải giúp người có quyền đăng ký lại phương tiện xác thực mà không biến câu “tôi mất ứng dụng” thành cách bỏ qua MFA.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, tình huống này kết nối đánh giá rủi ro, bằng chứng thay thế, token dùng một lần, chống lạm dụng và kiểm soát session. Mục tiêu là khôi phục quyền xác thực phù hợp, đồng thời xử lý yếu tố cũ có thể còn tồn tại trên thiết bị mất hoặc trong bản sao lưu.

## 1. Mất ứng dụng là mất điều gì?

Ứng dụng xác thực là phần mềm chứa hoặc sử dụng thông tin xác thực. Tùy cơ chế, dữ liệu quan trọng có thể là khóa bí mật dùng chung để tạo OTP, khóa riêng của đăng ký nhận thông báo xác nhận, hoặc thông tin xác thực theo giao thức khác.

| Tình huống | Điều cần làm rõ | Hướng xử lý ban đầu |
| --- | --- | --- |
| Xóa ứng dụng nhưng còn bản sao lưu được bảo vệ | Bản sao lưu có chứa đúng thông tin cần thiết và còn truy cập được không? | Khôi phục bằng chức năng chính thức nếu đáp ứng điều kiện |
| Đổi điện thoại và vẫn giữ máy cũ | Có thể xác thực và thực hiện chuyển đổi có kiểm soát không? | Dùng luồng quản lý yếu tố khi còn quyền xác thực |
| Đặt lại máy, không có bản sao lưu | Khóa hoặc đăng ký thiết bị đã mất khỏi máy | Dùng bằng chứng khôi phục đã chuẩn bị hoặc đường hỗ trợ phù hợp |
| Mất hoặc bị lấy cắp điện thoại | Người khác có thể truy cập yếu tố, session hoặc bản sao lưu không? | Đánh giá khả năng bị lộ và chuẩn bị thu hồi yếu tố liên quan |
| Ứng dụng còn nhưng OTP luôn sai | Có phải chọn nhầm tài khoản, lệch thời gian hoặc dùng bản sao cũ không? | Chẩn đoán lỗi sử dụng trước khi coi là mất yếu tố |
| Ứng dụng nhận thông báo xác nhận không còn hoạt động | Đăng ký thiết bị hoặc khóa riêng có còn hợp lệ không? | Xác định cơ chế đăng ký lại của loại yếu tố đó |

Cài lại một ứng dụng có cùng tên không đồng nghĩa khôi phục được khóa cũ. Một tài khoản đồng bộ của ứng dụng cũng không bảo đảm mọi mục xác thực đều đã được sao lưu. Không nên hướng dẫn người dùng xóa dữ liệu hoặc đặt lại thêm thiết bị khi chưa hiểu dữ liệu nào còn có thể khôi phục.

Một ứng dụng có thể chứa cả OTP, passkey hoặc chức năng xác nhận đẩy. Các loại này có mô hình khóa và chính sách khôi phục khác nhau. Bài này dùng **TOTP** làm ví dụ chính, đồng thời giữ nguyên tắc rằng việc thay yếu tố phải dựa trên quyền đã được chứng minh.

## 2. Hiểu khóa TOTP để tránh khôi phục sai

Với TOTP, ứng dụng và máy chủ cùng biết một khóa bí mật `K`. Ứng dụng kết hợp khóa với bộ đếm bước thời gian để tạo mã ngắn. Có thể biểu diễn ý tưởng như sau:

```text
counter = floor((currentTime - startTime) / timeStep)
otp = truncate(HMAC(K, counter)) mod 10^digits
```

Đây là mô tả khái niệm; triển khai thực tế cần sử dụng thành phần TOTP đã được kiểm chứng và bộ tham số phù hợp. Điểm cần nhớ là **mã ngắn không phải khóa bí mật**.

- Một mã đang hiển thị không đủ để khôi phục khóa TOTP theo quy trình sử dụng bình thường.
- Mã hết hiệu lực sau một khoảng ngắn không có nghĩa khóa `K` cũng hết hiệu lực.
- Nếu ai đó sao chép `K`, họ có thể tạo các mã tương lai cho đến khi thông tin xác thực đó bị thu hồi.
- Khôi phục bản sao lưu chứa cùng `K` tạo lại khả năng sinh mã cũ; nó không tự vô hiệu hóa bản sao trên thiết bị mất.

TOTP có thể được tạo khi điện thoại không có mạng nếu ứng dụng còn khóa và thời gian thích hợp. Lỗi mất mạng của ứng dụng không tự chứng minh rằng TOTP đã mất. Nếu thời gian tuyệt đối của thiết bị sai, mã có thể không khớp; đổi múi giờ hiển thị riêng lẻ thường không phải nguyên nhân nếu đồng hồ tuyệt đối vẫn đúng.

Không mở rộng tùy tiện cửa sổ chấp nhận thời gian để xử lý mọi trường hợp OTP sai. Chấp nhận nhiều bước thời gian làm tăng số mã có thể được chấp nhận tại một thời điểm và cần được xem xét cùng ngân sách thử.

Đối với TOTP, máy chủ cần có khả năng tính hoặc kiểm tra mã từ khóa, thông qua lưu trữ khóa được mã hóa hoặc dịch vụ bảo vệ khóa phù hợp. Không thể thay khóa đó bằng một hash một chiều rồi kiểm tra TOTP theo cách thông thường như kiểm tra mật khẩu. Quyền truy cập khóa phải được giới hạn; không cung cấp chức năng hiển thị lại khóa cũ như một lối khôi phục công khai.

## 3. Ba hoạt động cần phân biệt

### Khôi phục dữ liệu của ứng dụng

Người dùng phục hồi bản sao lưu hợp lệ và tiếp tục tạo mã cho đăng ký còn hoạt động. Phía dịch vụ có thể chưa thay đổi thông tin xác thực nào. Nếu thiết bị cũ bị mất và có nguy cơ còn truy cập được khóa, khả năng đăng nhập trở lại không giải quyết xong nguy cơ đó.

Chỉ sử dụng đường khôi phục chính thức, chú ý quyền truy cập tài khoản sao lưu và dữ liệu được bảo vệ. Không tải seed hoặc mã QR lên một công cụ “khôi phục authenticator” không rõ nguồn gốc.

### Thay phương tiện xác thực

Sau khi được cấp quyền thích hợp, người dùng đăng ký khóa mới, chứng minh ứng dụng mới tạo được mã và thu hồi thông tin xác thực cũ cần thay. Đây là thao tác quản lý an ninh của tài khoản, không đơn thuần là cài phần mềm.

### Khôi phục quyền truy cập tài khoản

Người dùng không còn đáp ứng cách xác thực bình thường nên cần chứng minh quyền bằng cơ chế khôi phục. Kết quả có thể là một quyền có phạm vi để thay yếu tố đã mất. Nó không nhất thiết phải tạo ngay một session đầy đủ.

Nếu vẫn còn máy cũ và xác thực được, nên dùng luồng chuyển hoặc đăng ký lại khi đang có quyền hợp lệ. Không đưa người dùng sang nhánh khôi phục yếu hơn chỉ vì nhánh đó ít thao tác hơn.

## 4. Bằng chứng nào có thể được dùng thay thế?

Máy chủ cần xác định những bằng chứng đã được đăng ký hoặc được chấp nhận theo chính sách trước khi cho thay yếu tố. Một lời khai về việc mất thiết bị là dữ liệu đánh giá rủi ro, không phải bằng chứng sở hữu tài khoản.

| Bằng chứng hoặc ngữ cảnh | Giá trị có thể có | Điều kiện và giới hạn |
| --- | --- | --- |
| Yếu tố độc lập đã đăng ký, như khóa bảo mật hoặc passkey còn dùng được | Chứng minh quyền bằng một phương tiện khác | Kiểm tra giao thức, đăng ký, mức bảo đảm và độ mới của lần xác thực |
| Mã khôi phục đã cấp trước | Chứng minh biết bí mật dự phòng | Dùng một lần, có đủ entropy, kiểm tra phạm vi và chống sử dụng đồng thời |
| Mật khẩu còn nhớ | Một phần bằng chứng trong tài khoản dùng mật khẩu | Không tự đủ để vô hiệu hóa MFA đã được đặt ra để bảo vệ mật khẩu |
| Session đang đăng nhập | Cung cấp ngữ cảnh và có thể chứa lịch sử xác thực phù hợp | Cookie có thể bị đánh cắp; cần xét thời gian, phương thức xác thực và quyền của session |
| Email hoặc số điện thoại đã xác minh | Bằng chứng tiếp cận một kênh | Mức tin cậy phụ thuộc kênh, thay đổi gần đây và rủi ro bị chiếm |
| Quy trình hỗ trợ xác minh danh tính | Có thể xử lý trường hợp mất mọi yếu tố trong phạm vi sản phẩm | Cần tiêu chí, phân quyền, lưu vết và biện pháp chống lừa nhân viên |

Một session cũ không nên tự có quyền thay yếu tố chỉ vì đã tồn tại nhiều ngày. Nếu dùng session làm một phần căn cứ, máy chủ phải lấy thông tin phương thức và thời điểm xác thực từ trạng thái đáng tin cậy; không nhận một trường do client tự khai rằng MFA đã hoàn tất.

Tính độc lập của bằng chứng rất quan trọng. Nếu bản sao lưu authenticator, email khôi phục và session đều phụ thuộc vào cùng một tài khoản đám mây đang bị chiếm, cộng số lượng tín hiệu không tạo ra mức bảo đảm tương đương nhiều yếu tố độc lập.

Với mã khôi phục có entropy cao, có thể lưu giá trị kiểm tra dạng hash phù hợp thay vì mã rõ. Đây là loại bí mật khác với OTP ngắn. Hệ thống cần bảo vệ danh sách mã và tiêu thụ mỗi mã theo cơ chế nguyên tử.

Khi một mã khôi phục được chấp nhận để cấp quyền cho một luồng, mã đó nên được đánh dấu đã dùng và ràng buộc với luồng theo thiết kế. Retry hợp lệ tiếp tục cùng luồng; không phục hồi mã về trạng thái chưa dùng chỉ vì người dùng tải lại trang hoặc gián đoạn mạng.

## 5. Đánh giá rủi ro của tình huống mất ứng dụng

Cần phân biệt việc mất dữ liệu với khả năng người khác đã có thông tin xác thực:

- Xóa ứng dụng trên thiết bị vẫn do người dùng kiểm soát có thể là vấn đề khả dụng.
- Điện thoại thất lạc, bị mở khóa hoặc bị phần mềm độc hại kiểm soát có thể liên quan tới lộ khóa, session và email.
- Mất quyền truy cập tài khoản sao lưu có thể ảnh hưởng nhiều mục xác thực cùng lúc.
- Yêu cầu từ thiết bị, vị trí hoặc ngữ cảnh bất thường cần được xem xét cùng lịch sử thay đổi an ninh của tài khoản.

Các quyết định có thể là cho tiếp tục, yêu cầu thêm bằng chứng, tạm giữ để xử lý hoặc từ chối nhánh khôi phục hiện tại. Không nên biến một điểm rủi ro thành kết luận danh tính tuyệt đối. Thời gian chờ cũng không tự chứng minh người yêu cầu là chủ tài khoản.

Việc đình chỉ yếu tố cũ ngay khi nhận một yêu cầu chưa xác minh có thể gây từ chối dịch vụ: người lạ chỉ cần khai “mất authenticator” để làm chủ tài khoản mất khả năng đăng nhập. Nếu có bằng chứng đáng tin về việc bị lộ và quyền thực hiện hành động bảo vệ đã được xác lập, hệ thống có thể đình chỉ hoặc thu hồi sớm theo chính sách. Hai trường hợp đó cần được tách rõ.

Không tạm tắt MFA và chỉ dựa vào mật khẩu trong lúc chờ người dùng đăng ký lại. Khoảng trống đó có thể chính là thời điểm kẻ tấn công sử dụng mật khẩu đã đánh cắp.

## 6. Luồng khôi phục có phạm vi và thời hạn

Một tiến trình thay TOTP đã mất có thể được mô tả như sau:

```text
STARTED
    -> EVIDENCE_PENDING
    -> AUTHORIZED_FOR_REPLACEMENT
    -> NEW_AUTHENTICATOR_PENDING
    -> COMPLETED

Tại các bước thích hợp có thể chuyển sang:
HELD, REJECTED, EXPIRED hoặc CANCELLED
```

Ý nghĩa từng giai đoạn:

1. **Bắt đầu:** tạo bản ghi luồng có thời hạn và ràng buộc với trình duyệt, tài khoản, mục đích và yếu tố cần thay.
2. **Thu thập bằng chứng:** kiểm tra mã dự phòng, yếu tố khác hoặc quy trình được phép; áp dụng giới hạn thử và chống dò tài khoản.
3. **Cấp quyền có phạm vi:** sau khi đủ điều kiện, tạo quyền chỉ cho phép thay authenticator đã định.
4. **Chuẩn bị yếu tố mới:** sinh khóa mới, hiển thị dữ liệu đăng ký qua kênh được bảo vệ, giữ ở trạng thái chờ xác nhận.
5. **Xác nhận và chuyển đổi:** kiểm tra mã từ ứng dụng mới, cập nhật trạng thái yếu tố và tiêu thụ quyền trong một thao tác nhất quán.
6. **Hoàn tất:** áp dụng chính sách session, thu hồi các quyền liên quan, thông báo và hướng dẫn kiểm tra lại phương án dự phòng.

Nếu quy trình cần thời gian chờ dài hoặc xử lý hỗ trợ, chỉ cấp quyền thao tác có thời hạn ngắn sau khi đạt điều kiện. Không phát một token ngắn hạn rồi âm thầm kéo dài nó nhiều lần trong suốt thời gian xử lý.

Một chính sách minh họa có thể đặt luồng thao tác tự phục vụ là 20 phút, quyền thay yếu tố là 10 phút và đăng ký chờ xác nhận là 5 phút. Mọi thời hạn con phải nằm trong điều kiện hiệu lực của quyền và luồng tương ứng. Các con số này phục vụ ví dụ; sản phẩm cần lựa chọn theo rủi ro và trải nghiệm thực tế.

## 7. Dữ liệu và ràng buộc cần lưu

Có thể dùng mô hình khái niệm sau:

```text
AuthenticatorCredential
  credentialId
  accountId
  type
  encryptedSecretRef
  status
  createdAt
  activatedAt
  revokedAt
  lastAcceptedTimeStep

AuthenticatorRecoveryFlow
  flowId
  accountId
  lostCredentialId
  purpose
  browserBindingRef
  evidenceDecisionRef
  accountAuthVersionAtAuthorization
  state
  expiresAt

RecoveryGrant
  grantId
  tokenDigest
  flowId
  allowedActions
  state
  expiresAt

PendingAuthenticator
  pendingId
  flowId
  encryptedSecretRef
  state
  attemptsUsed
  expiresAt
```

Quyền khôi phục cần khó đoán, được bảo vệ như một bí mật và được kiểm tra ở phía máy chủ. Nếu dùng token dạng opaque, có thể lưu digest của token đủ entropy để đối chiếu. Nếu dùng token có chữ ký, vẫn cần cơ chế tiêu thụ và thu hồi khi yêu cầu là dùng một lần; chữ ký hợp lệ không tự chống replay.

`allowedActions` có thể chỉ chứa thao tác thay một yếu tố cụ thể. Quyền đó không mặc nhiên cho thay email, số điện thoại, mật khẩu, mọi passkey hoặc thông tin thanh toán. Nếu cần khôi phục nhiều loại thông tin cùng lúc, chính sách phải cho phép rõ và yêu cầu bằng chứng phù hợp.

`accountAuthVersionAtAuthorization` giúp phát hiện tài khoản đã thay đổi thông tin an ninh sau khi cấp quyền. Ví dụ, một luồng khác vừa thay yếu tố thành công thì quyền cũ không nên tiếp tục áp dụng lên trạng thái đã thay đổi.

Ràng buộc luồng và trình duyệt không làm hệ thống tự chống được mọi hình thức lừa đảo. Nó có tác dụng giới hạn nơi và mục đích sử dụng quyền, trong khi việc xác minh bằng chứng và đánh giá rủi ro vẫn bắt buộc.

## 8. Đăng ký authenticator mới mà chưa kích hoạt vội

Máy chủ tạo khóa mới phù hợp cho TOTP bằng nguồn ngẫu nhiên dành cho mật mã và lưu ở trạng thái `PENDING`. Dữ liệu đăng ký, thường gồm mã QR hoặc chuỗi thiết lập, chứa bí mật cho phép tạo mã trong tương lai.

Cần bảo vệ dữ liệu này:

- Chỉ hiển thị khi quyền thay yếu tố còn hiệu lực và đúng ràng buộc.
- Sử dụng đường truyền được bảo vệ; tránh lưu cache nội dung nhạy cảm.
- Không đưa khóa hoặc mã QR vào log, URL truy cập trang, công cụ phân tích hay ảnh chụp gửi hỗ trợ.
- Không dùng dịch vụ tạo QR bên ngoài bằng cách truyền seed vào URL.
- Giới hạn thời gian tồn tại của đăng ký chờ và dọn dữ liệu khi bị hủy hoặc hết hạn.
- Lưu khóa phía máy chủ bằng cơ chế mã hóa và quản lý quyền phù hợp.

Người dùng quét dữ liệu vào ứng dụng mới và nhập một mã để chứng minh ứng dụng thực sự giữ khóa vừa cấp. **Mã từ ứng dụng mới không phải bằng chứng rằng người đó vốn là chủ tài khoản.** Kẻ tấn công được xem mã QR do chính họ yêu cầu cũng có thể sinh đúng mã. Quyền tạo và kích hoạt đăng ký phải được kiểm tra độc lập trước đó.

Không xóa yếu tố cũ ngay khi bắt đầu hiển thị QR nếu điều đó để lại tài khoản ở trạng thái không có MFA. Khi chuyển đổi bình thường, có thể giữ yếu tố cũ theo chính sách cho đến lúc yếu tố mới được xác nhận, rồi chuyển trạng thái nhất quán. Nếu yếu tố cũ đã bị đình chỉ có căn cứ vì nghi lộ, hệ thống vẫn phải giữ yêu cầu xác thực thích hợp thay vì tự hạ tài khoản xuống chỉ còn mật khẩu.

Nếu sinh lại QR với khóa mới, dữ liệu đăng ký chờ trước đó phải bị vô hiệu hóa. Không cho mỗi lần sinh lại một tập ngân sách thử mới không giới hạn.

## 9. Xác nhận và thay yếu tố theo cơ chế nguyên tử

Endpoint xác nhận phải kiểm tra cả quyền thay yếu tố lẫn OTP mới. Chỉ kiểm tra TOTP đúng là chưa đủ.

Mã giả dưới đây mô tả hợp đồng xử lý, không phải chương trình triển khai hoàn chỉnh:

```text
confirmReplacement(request):
    enforceIngressAbuseLimits()
    binding = resolveBoundRecoveryContext(request)

    atomicForAccount(binding.accountId):
        checkIdempotencyKeyAndBoundRequestFingerprint()
        loadAccountFlowGrantAndPendingAuthenticator()
        requireFlowAndGrantToBeValidForReplacement()
        requirePendingAuthenticatorToBelongToThisFlow()
        requireAllRelevantDeadlinesToBeValid()
        requireCurrentAuthVersionToMatchAuthorizedSnapshot()
        requireEvidenceDecisionToRemainAcceptable()

        reserveVerificationAttemptInAllRequiredBudgets()
        matchedStep = verifyNewTotpWithinAllowedWindow()

        if no step matched:
            persistFailureAndCommitConsumedAttempt()
            return rejectedResult()

        activateNewAuthenticatorWithReplayState(matchedStep)
        revokeExactlyTheOldCredentialAuthorizedForReplacement()
        consumeRecoveryGrant()
        markFlowCompleted()
        incrementAccountAuthVersion()
        invalidateConflictingRecoveryState()
        appendSecurityNotificationAndSessionActionsToOutbox()
        saveIdempotentCompletionResult()
        commit()

    return replacementCompletedReceipt()
```

Những thuộc tính cần được đảm bảo:

- Hai request đồng thời không cùng tiêu thụ một quyền khôi phục hoặc cùng kích hoạt hai đăng ký ngoài chính sách.
- Lượt xác minh sai vẫn được lưu; không dùng ngoại lệ làm transaction tự rollback bộ đếm.
- Nếu cập nhật thất bại, không trả thành công và không để xuất hiện kết quả nửa chừng như yếu tố cũ bị xóa nhưng yếu tố mới chưa hoạt động.
- Yếu tố bị thu hồi đúng là yếu tố được phép thay; không tùy tiện xóa các khóa bảo mật hoặc passkey còn khỏe mạnh khác.
- Request lặp cùng thao tác trả lại kết quả thích hợp, không tạo thêm yếu tố hay quyền mới. Cùng khóa idempotency nhưng thay nội dung phải bị từ chối.

Trạng thái chống dùng lại TOTP cần được xem xét ở phạm vi thông tin xác thực và các endpoint có liên quan. Nếu lưu bước thời gian đã chấp nhận, cập nhật đó phải nhất quán để một mã không được tái sử dụng trái chính sách ở request đồng thời hoặc endpoint khác. Không cho rằng mã tự đổi theo thời gian đã giải quyết toàn bộ replay trong bước thời gian hiện tại.

Đối với thông báo hoặc thu hồi session ở hệ thống bên ngoài, outbox hỗ trợ thực thi và đối soát sau transaction. Nó không biến mọi tác dụng bên ngoài thành một transaction cục bộ duy nhất. Khi kho trạng thái quyền hoặc ngân sách lỗi, không bỏ qua kiểm tra để “giúp người dùng vào trước”.

## 10. Thu hồi yếu tố cũ, session và phương án dự phòng

Khi thay khóa TOTP do nguy cơ lộ hoặc mất quyền kiểm soát thiết bị, cần vô hiệu hóa đăng ký dùng khóa cũ. Nếu sau này ứng dụng cũ được khôi phục từ bản sao lưu, mã của nó vẫn phải bị từ chối vì đăng ký đó đã bị thu hồi.

Với đăng ký nhận thông báo xác nhận, cần xử lý khóa hoặc đăng ký thiết bị tương ứng, không chỉ xóa tên hiển thị. Với một thiết bị chứa nhiều loại yếu tố, việc thu hồi TOTP không tự thu hồi passkey, session hoặc đăng ký khác trên cùng thiết bị; phải đánh giá từng loại theo bằng chứng và phạm vi hành động được phép.

Sau khôi phục, chính sách session có thể yêu cầu:

- Thu hồi session hoặc refresh token của thiết bị mất và các phiên nghi bị lộ.
- Yêu cầu xác thực lại bằng yếu tố mới trước hành động nhạy cảm.
- Vô hiệu hóa quyền khôi phục hoặc đăng ký chờ còn mâu thuẫn với trạng thái mới.
- Thay bộ mã dự phòng nếu bộ cũ có nguy cơ đã bị truy cập, hoặc theo chính sách cấp lại của sản phẩm.

Tăng `authVersion` chỉ hỗ trợ thu hồi nếu các nơi sử dụng session hoặc token thực sự kiểm tra phiên bản theo thiết kế. Một access token tự chứa được chấp nhận hoàn toàn ngoại tuyến không tự hết hiệu lực ngay vì một số trong cơ sở dữ liệu vừa tăng. Cần xác định rõ cơ chế kiểm tra, thời hạn token và khoảng trễ thực thi được chấp nhận.

Nếu cấp bộ mã dự phòng mới, phải làm rõ bộ cũ còn hiệu lực hay bị thay thế; trong thiết kế thay thế, chỉ duy trì một bộ có hiệu lực theo chính sách và cập nhật nhất quán. Không gửi toàn bộ seed TOTP hoặc mã dự phòng qua email như một bước hoàn tất mặc định.

Thông báo qua kênh đã đăng ký thích hợp giúp người dùng phát hiện việc thay đổi trái phép. Không chỉ gửi thông báo tới một kênh mới được thêm trong cùng tiến trình. Thông báo không chứa seed, OTP, mã dự phòng hoặc token khôi phục đầy đủ.

## 11. Chống lạm dụng mà không gây khóa tài khoản tùy ý

Một kẻ tấn công biết email có thể liên tục mở luồng, thử mã dự phòng, gửi yêu cầu hỗ trợ hoặc làm cạn hạn mức. Các kiểm soát cần bao phủ cả xác minh bằng chứng, cấp quyền và đăng ký yếu tố mới.

Các phạm vi thường cần quản lý gồm tài khoản, loại bằng chứng, luồng, nguồn yêu cầu và toàn dịch vụ. Ngân sách theo tài khoản phải tồn tại qua việc đổi trình duyệt, mở luồng mới hoặc chọn một nhánh khác có cùng mục tiêu chiếm tài khoản.

Có thể áp dụng một ngân sách minh họa là 5 phép kiểm tra OTP đăng ký trong một luồng, cùng các giới hạn cộng dồn theo tài khoản. Thời hạn và số lượt cần được chọn phù hợp; không áp dụng máy móc cùng một quy tắc cho OTP ngắn và mã khôi phục entropy cao.

Bắt đầu lại đăng ký chờ, đổi QR hoặc gửi lại request không được reset các giới hạn có phạm vi lớn hơn. Lưu trạng thái phía máy chủ; số đếm hoặc nút bị khóa ở frontend chỉ phục vụ trải nghiệm.

Phản hồi công khai cần hạn chế lộ tài khoản có tồn tại, có bật TOTP hay có bao nhiêu mã dự phòng. Sau khi có ngữ cảnh đủ tin cậy, giao diện có thể đưa hướng dẫn cụ thể hơn. Cũng cần xem xét thời gian xử lý, mã lỗi và hành vi gửi thông báo để tránh dò tài khoản chỉ qua những kênh khác.

Không thu hồi mọi session hoặc tắt yếu tố hợp lệ chỉ vì có một loạt yêu cầu thất bại chưa được xác minh. Phản ứng nên giới hạn đúng hoạt động bị lạm dụng và có đường xử lý cho người dùng có quyền.

## 12. Khi cần hỗ trợ và xác minh danh tính

Nếu không còn yếu tố khác, mã dự phòng hay kênh đáp ứng chính sách, người dùng có thể phải qua quy trình hỗ trợ được thiết kế cho sản phẩm. Nhân viên cần tiêu chí bằng chứng, phân quyền thao tác, lưu vết quyết định và cơ chế tăng mức xem xét cho tài khoản nhạy cảm.

Những dữ kiện dễ biết hoặc dễ lấy từ rò rỉ, như tên, ngày sinh hoặc vài hoạt động công khai, không nên tự đủ để bỏ MFA. Sự khẩn cấp, giọng nói thuyết phục hoặc ảnh chụp màn hình do bên yêu cầu cung cấp cũng không thay thế được bằng chứng phù hợp.

Nếu thu thập giấy tờ hoặc dữ liệu nhạy cảm, chỉ thu thập phần cần thiết theo chính sách của dịch vụ và bảo vệ quyền truy cập, lưu giữ, xử lý. Không mặc định mọi ứng dụng cần cùng một quy trình giấy tờ hoặc có khả năng xác minh danh tính pháp lý.

Một kết quả hợp lệ của quy trình có thể là chưa thể khôi phục do thiếu bằng chứng. Không nên sáng tạo một cửa sau để bảo đảm mọi người yêu cầu đều lấy lại được tài khoản. Người dùng cần được biết các phương án khả dụng và giới hạn của từng phương án.

## 13. Ví dụ xuyên suốt

Minh đặt lại điện thoại, mất dữ liệu ứng dụng TOTP và không có bản sao lưu dùng được. Minh vẫn nhớ mật khẩu và giữ một mã khôi phục đã cấp trước trong nơi lưu riêng. Giả sử chính sách sản phẩm cho phép kết hợp hai bằng chứng này để thay authenticator đã mất.

1. Minh mở trang chính thức, chọn mất authenticator và bắt đầu luồng `F1` có thời hạn.
2. Máy chủ xác minh mật khẩu, kiểm tra mã khôi phục còn hiệu lực và tiêu thụ mã theo cơ chế nguyên tử. Quyền tiếp tục được gắn với `F1`.
3. Sau đánh giá rủi ro, máy chủ cấp quyền chỉ cho thay TOTP cũ `A1`, ghi lại phiên bản an ninh hiện tại của tài khoản.
4. Máy chủ sinh khóa mới, tạo đăng ký chờ `P1` và hiển thị QR trong ngữ cảnh được bảo vệ. `P1` chưa được coi là yếu tố hoạt động.
5. Minh quét QR, nhập nhầm một mã rồi nhập đúng mã mới. Lượt sai vẫn được tính; mã đúng được kiểm tra cùng quyền và các thời hạn.
6. Trong lần cập nhật hoàn tất, hệ thống kích hoạt `A2`, thu hồi `A1`, tiêu thụ quyền và tăng phiên bản an ninh. MFA vẫn là yêu cầu của tài khoản.
7. Hệ thống thực thi chính sách session, thông báo thay đổi và hướng dẫn Minh chuẩn bị phương án dự phòng phù hợp.

Sau đó, nếu một bản sao lưu cũ được khôi phục và tiếp tục sinh mã từ khóa của `A1`, những mã đó không được dùng để đăng nhập. Nếu một luồng khác đã thay yếu tố trước bước 6, kiểm tra phiên bản phải ngăn quyền cũ tiếp tục áp dụng lên trạng thái mới.

So sánh với trường hợp kẻ tấn công chỉ biết mật khẩu: họ không được tự đăng ký một seed mới rồi dùng OTP từ seed của chính mình để chứng minh quyền sở hữu tài khoản. Việc quét QR và sinh đúng mã chỉ chứng minh họ giữ khóa vừa được cấp, nên việc cấp quyền thay yếu tố trước đó là ranh giới quyết định.

## 14. Những tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Người dùng chỉ cài lại ứng dụng, chưa khôi phục khóa | Không giả định TOTP cũ đã trở lại |
| OTP sai do thời gian hoặc chọn nhầm tài khoản | Có hướng dẫn chẩn đoán, không tự tắt MFA |
| Chỉ có mật khẩu nhưng thiếu bằng chứng cần thiết | Không cấp quyền thay authenticator |
| Hai request dùng cùng mã khôi phục | Chỉ một quyền tiêu thụ hợp lệ theo thiết kế |
| Request đăng ký mới không có quyền phù hợp | Không hiển thị seed hoặc kích hoạt yếu tố |
| Người yêu cầu tự tạo được OTP từ QR mới | Vẫn phải có quyền thay yếu tố đã được xác lập |
| Đăng ký chờ hết hạn hoặc bị sinh lại | Dữ liệu chờ cũ không còn được kích hoạt |
| Hai request xác nhận đồng thời | Không kích hoạt trùng hoặc dùng lại cùng quyền |
| Tài khoản thay đổi yếu tố sau khi cấp quyền | Quyền cũ bị chặn hoặc được đánh giá lại theo chính sách |
| Transaction thay yếu tố thất bại | Không trả thành công hoặc để tài khoản rơi vào khoảng trống MFA |
| Khôi phục bản sao lưu chứa seed cũ đã thu hồi | Mã từ seed cũ bị từ chối |
| Tăng phiên bản an ninh nhưng có access token tự chứa | Hành vi thu hồi đáp ứng cơ chế thực thi đã công bố |
| Yêu cầu mất ứng dụng từ người chưa xác minh | Không tự đình chỉ mọi yếu tố và session của nạn nhân |
| Hỗ trợ hoặc log thu nhận dữ liệu xác thực | Không để lộ seed, QR, mã dự phòng hoặc quyền khôi phục |

Khôi phục sau khi mất authenticator cần giải quyết cả quyền thay yếu tố lẫn vòng đời của khóa. Khi bằng chứng được kiểm tra trước, đăng ký mới được xác nhận đúng và yếu tố cũ được thu hồi nhất quán, người dùng có thể lấy lại khả năng xác thực mà hệ thống vẫn giữ được yêu cầu bảo vệ tài khoản.
