# One-time password

**One-time password (OTP)** là mã xác thực được thiết kế để chỉ được chấp nhận một lần trong phạm vi sử dụng đã quy định. Khác với mật khẩu dài hạn mà người dùng thường ghi nhớ, OTP có giá trị ngắn hạn hoặc gắn với một trạng thái thay đổi, chẳng hạn bộ đếm.

Một mã gồm sáu chữ số chưa tự trở thành OTP an toàn. Hệ thống còn phải kiểm tra mã cho đúng chủ thể, đúng lần xác thực, đúng điều kiện hiệu lực và bảo đảm một lần sử dụng thành công không thể được phát lại.

Trong IAM, OTP thường xuất hiện ở bước xác thực bổ sung, xác nhận thay đổi nhạy cảm hoặc phục hồi tài khoản. Bài này tập trung vào cách OTP hoạt động và những điều kiện cần để ứng dụng thực sự thực thi ý nghĩa “một lần”.

## 1. Phân biệt mã OTP với bí mật tạo mã

Một hệ thống OTP thường có ít nhất ba loại dữ liệu khác nhau:

| Thành phần | Ý nghĩa | Hệ quả nếu bị lộ |
| --- | --- | --- |
| Bí mật dài hạn, thường gọi là seed hoặc khóa K | Dữ liệu dùng để sinh và kiểm tra một chuỗi OTP | Có thể cho phép tạo nhiều mã về sau |
| Mã OTP đang hiển thị | Đầu ra ngắn hạn mà người dùng nhập | Có thể bị sử dụng trong thời gian hoặc trạng thái còn hợp lệ |
| Bản ghi liên kết | Cho biết authenticator gắn với tài khoản nào và đang ở trạng thái nào | Sửa sai liên kết có thể làm mã của kẻ tấn công được chấp nhận cho tài khoản khác |

Ví dụ, ứng dụng tạo mã trên điện thoại của Linh giữ một seed được đăng ký với tài khoản của Linh. Số đang hiển thị trên màn hình chỉ là một đầu ra của seed đó.

Mã hết hạn không có nghĩa seed hết giá trị. Nếu ảnh QR đăng ký hoặc bản sao seed bị đánh cắp, kẻ tấn công có thể tiếp tục tạo mã mới. Thay đổi mã theo thời gian không chữa được việc bí mật gốc đã bị lộ.

Cũng cần phân biệt **authenticator** với **authenticator output**. Ứng dụng hoặc thiết bị cùng bí mật mà nó kiểm soát tham gia vào cơ chế xác thực; OTP người dùng nhìn thấy là đầu ra được cung cấp trong lần xác thực.

## 2. HOTP: thay đổi theo bộ đếm

HOTP là cơ chế OTP dựa trên HMAC và một bộ đếm. Hai phía cùng biết khóa bí mật K và có trạng thái bộ đếm tương thích.

Biểu diễn khái niệm:

```text
K = khóa bí mật dùng chung
C = bộ đếm
d = số chữ số của mã

hmacValue = HMAC-SHA-1(K, encodeCounter(C))
binaryValue = dynamicTruncate(hmacValue)
otp = decimal(binaryValue mod 10^d), đệm số 0 bên trái đủ d chữ số
```

Cách mã hóa bộ đếm, dynamic truncation và các yêu cầu đồng bộ được mô tả trong [RFC 4226](https://www.rfc-editor.org/rfc/rfc4226.html). Không thay các bước đó bằng việc nối chuỗi seed với counter rồi hash tùy ý.

Ở phía thiết bị, một sự kiện tạo mã làm tiến bộ đếm. Máy chủ chấp nhận mã ở trạng thái phù hợp rồi tiến trạng thái của mình. Nếu người dùng bấm tạo mã nhiều lần mà chưa đăng nhập, hai phía có thể bị lệch.

Ví dụ do bài học xây dựng:

```text
Máy chủ đang chờ counter 120.
Người dùng đã tạo mã ở counter 120 và 121 nhưng không gửi.
Mã được nhập thuộc counter 122.

Nếu chính sách cho phép tìm trong các counter phù hợp:
    máy chủ tìm thấy counter 122;
    sau khi chấp nhận, counter kế tiếp là 123.
```

Cửa sổ tìm kiếm hỗ trợ khả năng sử dụng, nhưng càng nhiều counter được thử thì càng có nhiều mã ứng viên được chấp nhận. Cần giới hạn cửa sổ, số lần thử và quy trình đồng bộ lại.

Một điểm khác với TOTP: HOTP không tự hết giá trị chỉ vì đã qua 30 giây. Hiệu lực phụ thuộc trạng thái counter và các giới hạn bổ sung của ứng dụng. Không áp dụng suy luận về thời gian của TOTP cho mọi HOTP.

## 3. TOTP: thay bộ đếm bằng bước thời gian

TOTP sử dụng giá trị thay đổi được tính từ thời gian:

```text
T = floor((unixTime - T0) / X)
TOTP(K, unixTime) = HOTP(K, T)
```

Trong đó, X là độ dài bước thời gian và T0 là mốc bắt đầu. Hai phía phải thống nhất khóa, thuật toán, số chữ số và tham số thời gian. [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238.html) mô tả cơ chế này, với bước mặc định 30 giây và khả năng sử dụng các biến thể HMAC được quy định.

Ví dụ số học, chưa phải kết quả sinh mã:

```text
T0 = 0
X = 30 giây

unixTime = 1710 → T = 57
unixTime = 1739 → T = 57
unixTime = 1740 → T = 58
```

Với cùng khóa và cấu hình, hai thời điểm nằm trong cùng bước tạo cùng một OTP. Vì vậy, bấm nút nhiều lần trong cùng bước không tạo các bằng chứng độc lập.

Máy chủ dùng thời gian của mình để xác minh. Không cho client tự gửi thời gian rồi dùng giá trị ấy làm nguồn quyết định, vì client có thể lựa chọn thời điểm có lợi cho việc dùng lại mã.

TOTP không phụ thuộc múi giờ hiển thị của điện thoại như một lịch địa phương. Nó dựa trên thời gian Unix và các tham số chung. Tuy nhiên, đồng hồ hệ thống sai vẫn có thể làm hai phía tính bước khác nhau.

## 4. So sánh các cơ chế thường được gọi chung là OTP

| Cơ chế | Giá trị thay đổi dựa trên | Máy chủ cần quản lý | Điểm cần chú ý |
| --- | --- | --- | --- |
| HOTP | Counter | Khóa, counter và trạng thái đồng bộ | Tiến counter nguyên tử sau khi chấp nhận |
| TOTP | Bước thời gian | Khóa, cấu hình và trạng thái chống phát lại | Cửa sổ thời gian và mã đã dùng |
| Mã ngẫu nhiên gửi qua kênh khác | Một challenge do máy chủ tạo | Challenge, verifier của mã, hạn dùng, số lần thử | Kênh nhận mã và liên kết với lần xác thực |
| Mã phục hồi dùng một lần | Một phần tử trong tập mã đã cấp | Trạng thái mã còn dùng được | Tiêu thụ nguyên tử và bảo vệ quá trình cấp lại |

Một mã sáu chữ số gửi bằng SMS không mặc nhiên là TOTP. Máy chủ có thể tạo mã ngẫu nhiên rồi gửi cho người dùng, thay vì hai phía cùng tính mã từ seed.

Tương tự, mã gửi qua email có thể phục vụ xác nhận địa chỉ hoặc phục hồi, nhưng tính chất của nó còn phụ thuộc quyền kiểm soát email và luồng sử dụng. Không đánh đồng việc nhận được mã với mọi mức bảo đảm của một authenticator OTP.

Trong cách phân loại của NIST, OTP authenticator và xác thực qua kênh ngoài là các cơ chế khác nhau. Khi đánh giá yêu cầu bảo đảm, cần đối chiếu đúng cơ chế thay vì chỉ nhìn hình thức mã số trên màn hình.

## 5. Cửa sổ chấp nhận và đồng hồ lệch

Điện thoại và máy chủ có thể không đổi bước đúng cùng lúc. Để tránh người dùng vừa nhập xong mã thì bị từ chối vì chuyển bước, ứng dụng có thể chấp nhận một số bước lân cận.

Ví dụ cấu hình riêng của bài học:

```text
step máy chủ = 57
window = 1

Các step được xét:
    56, 57, 58
```

Điều này không phải yêu cầu bắt buộc phải chấp nhận cả quá khứ lẫn tương lai. Hệ thống cần chọn cửa sổ phù hợp với yêu cầu và khả năng vận hành của mình.

Có ba hệ quả cần hiểu:

- Mã hiển thị trong 30 giây có thể được máy chủ chấp nhận trong khoảng rộng hơn do cửa sổ.
- Cửa sổ càng rộng thì càng có nhiều mã ứng viên cho một lần đoán.
- Một mã đã được sử dụng thành công không được chấp nhận lại chỉ vì vẫn nằm trong cửa sổ.

Không xử lý sự cố lệch đồng hồ bằng cách mở rộng cửa sổ không giới hạn. Cần kiểm tra đồng bộ thời gian, tham số đăng ký, độ dài mã và thuật toán. Việc máy chủ trong một cụm lệch giờ khác nhau cũng có thể tạo hành vi khó dự đoán.

Nếu cho phép ghi nhận độ lệch theo credential, dữ liệu này phải có giới hạn và được cập nhật qua quá trình xác minh đáng tin. Không để một request chưa xác thực tự thay độ lệch của tài khoản.

## 6. “Hết hạn” và “đã dùng” là hai điều kiện khác nhau

Giả sử mã `004219` đang có hiệu lực và được Linh sử dụng thành công lúc 10:00:05. Mã vẫn còn nằm trong bước thời gian ở 10:00:10.

Nếu máy chủ chỉ tính TOTP hiện tại và so sánh, nó có thể chấp nhận lại cùng mã. Đó là lỗi chống phát lại. [RFC 6238, mục 5.2](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2) yêu cầu không chấp nhận lần sử dụng tiếp theo của OTP sau lần xác minh thành công đầu tiên.

Một thiết kế có thể ghi lại bước đã được chấp nhận của từng credential. Ví dụ:

```text
credentialId = cred-totp-demo-7
acceptedStep = 57
```

Nếu dùng `lastAcceptedStep`, máy chủ chỉ chấp nhận bước lớn hơn giá trị đã ghi. Thiết kế này đơn giản nhưng cũng từ chối một bước cũ hơn chưa từng dùng nếu bước mới hơn đã được chấp nhận trước; cần hiểu rõ hệ quả đó khi cho phép cửa sổ.

Một thiết kế khác có thể theo dõi tập các bước đã dùng còn liên quan trong cửa sổ và bảo đảm duy nhất theo `credentialId + step`. Trạng thái này cần được giữ đủ lâu để một bước đã tiêu thụ không trở thành hợp lệ trở lại.

Đừng lưu vĩnh viễn mỗi chuỗi sáu chữ số như một giá trị cấm dùng trên toàn hệ thống. Những chuỗi số có thể lặp lại ở thời điểm khác hoặc ở credential khác. Trạng thái chống phát lại phải phản ánh cơ chế và phạm vi của credential.

### Hai request đồng thời

Hai request có thể cùng đọc “step 57 chưa dùng”, cùng kiểm tra đúng mã và cùng được chấp nhận. Cách xử lý “đọc rồi ghi” thông thường không bảo đảm tính một lần.

Việc kiểm tra trạng thái và ghi nhận tiêu thụ cần có tính nguyên tử, chẳng hạn:

- Giao dịch có khóa bản ghi phù hợp.
- Cập nhật có điều kiện theo phiên bản hoặc step trước đó.
- Ràng buộc duy nhất cho lần tiêu thụ tại một kho dùng chung.

Trong hệ thống nhiều instance, lưu trạng thái này trong bộ nhớ riêng của từng instance sẽ không tạo được tính duy nhất toàn cụm.

## 7. Gắn OTP với đúng lần xác thực

OTP không được biến thành một API “nhập user ID và mã là nâng quyền cho bất kỳ phiên nào”. Ứng dụng cần quản lý một lần xác thực hoặc challenge có ngữ cảnh rõ ràng.

Ví dụ metadata do bài học định nghĩa:

```json
{
  "authenticationAttemptId": "attempt-demo-901",
  "subjectId": "user-demo-42",
  "credentialId": "cred-totp-demo-7",
  "purpose": "LOGIN_SECOND_FACTOR",
  "state": "PENDING",
  "primaryAuthenticationSatisfied": true,
  "expiresAt": "2026-01-15T09:05:00Z"
}
```

Không có seed hay mã OTP trong metadata minh họa này. `PrimaryAuthenticationSatisfied` là trạng thái máy chủ quản lý, không phải cờ do client tự khai.

Khi nhận mã, máy chủ xác minh rằng attempt:

1. Thuộc đúng luồng và chủ thể đã được xác định.
2. Được ràng buộc với client hoặc phiên tạm theo thiết kế.
3. Chưa hết hạn và chưa hoàn tất.
4. Đang yêu cầu đúng mục đích và credential.
5. Còn ngân sách thử theo chính sách.

TOTP thông thường không ký trực tiếp nội dung giao dịch. Dù máy chủ gắn một attempt với “duyệt hóa đơn”, mã TOTP bản thân nó không chứng minh người dùng đã nhìn thấy đúng số tiền và người nhận. Yêu cầu xác nhận giao dịch cụ thể cần cơ chế ràng buộc nội dung phù hợp.

### Mã giả xác minh

Đây là mã giả về điều phối trạng thái; phần OTP phải sử dụng triển khai thuật toán phù hợp:

```text
verifyTotp(attemptId, submittedCode, temporaryClientContext):

    if not fullMatchConfiguredAsciiDigits(submittedCode):
        reject()

    atomicallyConsumeAttemptBudgetForSubjectAndCredential()
    if overLimit:
        reject()

    begin transaction:

        attempt = loadAndLockAttempt(attemptId)
        credential = loadAndLockCredential(attempt.credentialId)

        verifyAttemptBinding(attempt, temporaryClientContext)
        require attempt.state == PENDING
        require attempt.expiresAt > trustedServerNow()
        require attempt.primaryAuthenticationSatisfied
        require credential.subjectId == attempt.subjectId
        require credential.state == ACTIVE
        require accountIsActive(attempt.subjectId)

        matchedStep = verifyWithinConfiguredWindow(
            credential,
            submittedCode,
            trustedServerNow()
        )

        require matchedStep exists
        require matchedStep > credential.lastAcceptedStep

        credential.lastAcceptedStep = matchedStep
        attempt.state = COMPLETED
        createAuthenticationResultForThisAttempt()

    commit

    return authenticationResult
```

Đoạn này chọn phương án `lastAcceptedStep`. `LastAcceptedStep` có giá trị ban đầu được định nghĩa rõ khi đăng ký; không lấy từ request.

Ngân sách thử được ghi trước phần giao dịch quyết định kết quả để các lần kiểm tra thất bại vẫn bị tính. Nếu triển khai bằng giao dịch khác, việc rollback khi mã sai không được vô tình khôi phục số lần thử.

Phần tạo kết quả và đánh dấu hoàn tất cũng cần được điều phối nhất quán. Nếu một request gửi lại do mất phản hồi mạng, có thể xử lý tính lặp của cùng attempt theo contract riêng; không giải quyết bằng cách chấp nhận mã lần nữa để tạo một phiên mới.

## 8. Mã ngắn cần giới hạn số lần thử

Sáu chữ số tạo khoảng một triệu khả năng, không phải không gian đủ lớn để bỏ qua chống đoán trực tuyến.

Minh họa toán học đơn giản, coi các mã phân bố gần đều:

```text
d = 6 chữ số
n = số mã ứng viên có thể được chấp nhận trong một lần thử

Xác suất đoán đúng một lần xấp xỉ:
    n / 10^d

Với cửa sổ có 3 step ứng viên:
    xấp xỉ 3 / 1.000.000
```

Đây là mô hình gần đúng để hiểu tác động của độ dài và cửa sổ, không phải bảo đảm an toàn của một triển khai. Số lần thử, nhiều tài khoản, cửa sổ thay đổi và các luồng phụ đều ảnh hưởng kết quả.

Giới hạn cần xét tài khoản, credential, attempt và các nguồn tấn công liên quan. Chỉ giới hạn theo IP dễ bị vượt qua bởi nhiều nguồn. Chỉ giới hạn theo attempt dễ bị vượt qua nếu kẻ tấn công tạo attempt mới không hạn chế.

Các giá trị như “tối đa 5 lần thử” trong một thiết kế là tham số chính sách cần được chọn và kiểm chứng, không phải quy tắc chung của mọi hệ thống.

Cần cân bằng với nguy cơ gây từ chối dịch vụ: khóa vĩnh viễn một tài khoản chỉ bằng cách gửi nhiều mã sai có thể cho phép người ngoài làm người dùng hợp lệ mất quyền truy cập. Có thể kết hợp khoảng chờ, hạn mức nhiều tầng và bước xác minh phục hồi phù hợp.

Với mã do máy chủ gửi qua kênh ngoài, việc bấm “gửi lại” cũng cần giới hạn. Thiết kế phải quy định mã cũ có bị vô hiệu hóa hay không và không tự làm mới toàn bộ ngân sách tấn công sau mỗi lần gửi.

## 9. Đăng ký, lưu trữ và thay thế seed

### 9.1. Đăng ký đúng tài khoản

Seed phải được tạo bằng nguồn ngẫu nhiên mật mã phù hợp, không suy ra từ email, số điện thoại, user ID hoặc thời gian tạo tài khoản.

Một quy trình đăng ký minh họa:

1. Xác minh quyền thêm authenticator cho tài khoản hiện tại.
2. Tạo seed riêng và bản ghi ở trạng thái chờ.
3. Truyền thông tin đăng ký qua kênh được bảo vệ.
4. Yêu cầu chứng minh đã thiết lập được bộ tạo mã.
5. Kích hoạt credential sau khi kiểm tra thành công.
6. Ghi sự kiện và thông báo theo chính sách.

Không đánh dấu “MFA đã bật” ngay khi hiển thị QR. Người dùng có thể chưa quét được, quét nhầm ứng dụng hoặc bỏ dở quy trình.

Nếu mã xác nhận đăng ký đã được dùng để hoàn tất một quyết định xác thực, trạng thái chống dùng lại cần được thiết kế nhất quán; không vô tình chấp nhận lại mã đó ở một luồng khác có cùng phạm vi.

### 9.2. Bảo vệ seed khác với bảo vệ mật khẩu

Máy chủ HOTP/TOTP dùng chung bí mật cần sử dụng khóa để tính giá trị kiểm tra. Chỉ lưu hash một chiều của seed rồi bỏ seed sẽ không đáp ứng cách xác minh đó.

Seed thường cần được mã hóa hoặc quản lý bằng hệ thống bảo vệ bí mật, với quyền giải mã hay sử dụng giới hạn. Khóa bảo vệ seed phải được quản lý riêng.

Ngược lại, với mã ngẫu nhiên ngắn hạn do máy chủ phát hành, có thể lưu dữ liệu xác minh thay cho mã gốc. Nhưng hash thông thường của sáu chữ số vẫn có không gian đoán nhỏ nếu dữ liệu bị lộ; cần lựa chọn cơ chế bảo vệ phù hợp, kể cả khóa bảo vệ riêng khi thiết kế sử dụng nó.

Phân biệt seed và mã ngắn hạn, cùng yêu cầu hạn dùng, giới hạn thử và không ghi mã vào log, được thảo luận trong [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html).

### 9.3. Mất thiết bị và phục hồi

Đổi hoặc xóa seed không giống đổi số đang hiển thị. Nếu seed bị lộ, cần thu hồi credential cũ và đăng ký seed mới qua một quy trình được phép.

Không cho người gọi bỏ MFA chỉ vì khai “đã mất điện thoại”. Mã phục hồi, authenticator dự phòng hoặc quy trình hỗ trợ đều phải có cơ chế xác minh và kiểm toán riêng.

Một mã phục hồi dùng một lần cần được tiêu thụ nguyên tử giống nguyên tắc đối với OTP. Nó có thể có thiết kế và độ dài khác mã sáu chữ số hiển thị trên ứng dụng.

Khi thu hồi OTP authenticator, cần xem xét các phiên hoặc token đã được cấp trước đó. Thu hồi seed không tự làm mọi phiên đang tồn tại biến mất.

## 10. OTP, MFA và khả năng chống phishing

Một ứng dụng tạo TOTP thông thường thể hiện quyền kiểm soát bí mật trên thiết bị hoặc môi trường lưu trữ. Khi kết hợp đúng với mật khẩu, hệ thống có thể sử dụng hai loại yếu tố.

Tuy nhiên, hai mã OTP liên tiếp từ cùng một seed không tạo thành MFA. Hai bản sao ứng dụng chứa cùng seed cũng không tự là hai yếu tố độc lập.

OTP nhập thủ công có thể bị chuyển tiếp theo thời gian thực. Một trang giả yêu cầu Linh nhập mật khẩu và OTP, sau đó chuyển ngay các dữ liệu đó sang dịch vụ thật trước khi mã bị dùng hoặc hết hạn.

```text
Linh → trang giả: mật khẩu + OTP hiện tại
Trang giả → dịch vụ thật: dữ liệu vừa thu được
Dịch vụ thật → kẻ tấn công: kết quả đăng nhập nếu kiểm tra thành công
```

Chống phát lại ngăn mã đã tiêu thụ được dùng lần nữa, nhưng không bảo đảm người sử dụng đầu tiên là bên hợp lệ. Kẻ tấn công có thể sử dụng mã trước người dùng.

[NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) xác định xác thực OTP không có tính chống phishing. Với yêu cầu chống phishing, cần lựa chọn phương thức có cơ chế ràng buộc phù hợp với bên xác minh, chẳng hạn triển khai xác thực khóa công khai đáp ứng các điều kiện liên quan.

TOTP offline cũng không đồng nghĩa mọi bản sao seed đều nằm trong một thiết bị duy nhất. Khả năng sao lưu, xuất hoặc đồng bộ phụ thuộc ứng dụng. Cần đưa điều đó vào đánh giá rủi ro, thay vì mặc định “có điện thoại” luôn chứng minh một yếu tố không thể sao chép.

## 11. Những chi tiết triển khai dễ bị bỏ sót

### Giữ số 0 ở đầu

Mã `004219` là chuỗi sáu chữ số. Chuyển thành số nguyên `4219` rồi so sánh tùy ý có thể tạo khác biệt giữa các tầng xử lý.

Nên kiểm tra đúng định dạng cấu hình và giữ mã dưới dạng chuỗi phù hợp. Nếu giao diện cho phép khoảng trắng để dễ đọc, quy tắc chuẩn hóa phải được định nghĩa rõ trước khi gửi hoặc xác minh.

### Không tự bịa thuật toán OTP

Dùng `hash(userId + currentMinute)`, lấy sáu ký tự cuối hoặc dùng bộ sinh ngẫu nhiên không phù hợp sẽ không tạo ra HOTP/TOTP đúng. Thư viện còn phải xử lý đúng cấu hình, độ dài, biểu diễn counter và trường hợp biên.

### Không tin cờ MFA do client gửi

`mfaVerified=true`, `mfaAt` hoặc `credentialId` trong request body không phải bằng chứng đã xác thực. Kết quả MFA phải do máy chủ thiết lập và ràng buộc với đúng ngữ cảnh.

### Không ghi seed và mã vào log

Cần kiểm tra cả request logging, trace, công cụ phân tích lỗi, analytics và ảnh chụp màn hình hỗ trợ. Log một mã còn hiệu lực có thể làm lộ dữ liệu đủ cho tấn công tức thời; log seed tạo rủi ro dài hạn.

Audit có thể ghi credential ID, attempt ID, thời điểm, kết quả và loại lỗi nội bộ phù hợp. Không cần ghi giá trị mã để đếm lỗi xác thực.

### Không nhầm TTL của kho dữ liệu với kiểm tra hiệu lực

Một challenge có thể vẫn tồn tại trong kho dù đã qua thời điểm hết hạn vì cơ chế dọn dữ liệu chưa chạy. Verifier cần kiểm tra `expiresAt` và trạng thái, không chỉ kiểm tra bản ghi còn tồn tại.

### Không mở rộng quyền quá mức sau OTP

Sau khi hoàn tất OTP cho một lần đăng nhập hoặc một thao tác nhạy cảm, ứng dụng phải ghi nhận đúng mục đích và độ mới của xác thực. Không biến kết quả ấy thành quyền quản trị toàn hệ thống hay quyền truy cập mọi tenant.

## 12. Ví dụ vận hành và các tình huống cần chứng minh

Giả sử ứng dụng dùng mật khẩu và TOTP để đăng nhập. Cấu hình minh họa là mã sáu chữ số, bước 30 giây và cửa sổ chấp nhận có giới hạn. Các mã xuất hiện dưới đây chỉ là ví dụ, không được sinh từ một seed thực tế trong bài.

| Tình huống | Hành vi cần có |
| --- | --- |
| Mã đúng, đúng tài khoản, attempt còn hiệu lực | Hoàn tất đúng attempt và tiêu thụ step |
| Mã đúng nhưng tài khoản đã bị khóa | Từ chối |
| Mã đúng của credential khác | Không được dùng cho tài khoản hoặc credential đang yêu cầu |
| Mã đã dùng nhưng vẫn còn trong cửa sổ | Từ chối phát lại |
| Hai request dùng cùng mã đồng thời | Tối đa một lần hoàn tất xác thực mới |
| Mã ở bước ngoài cửa sổ | Từ chối, không tự tăng cửa sổ |
| Mã có số 0 đầu | Được xử lý đúng nếu còn lại đều hợp lệ |
| Mã thiếu chữ số hoặc có ký tự không được chấp nhận | Từ chối theo contract định dạng |
| Tạo nhiều attempt mới để đoán mã | Vẫn chịu ngân sách thử ở cấp chủ thể hoặc credential |
| Seed ở trạng thái chờ hoặc đã thu hồi | Không được dùng như credential đang hoạt động |
| Kho seed hoặc trạng thái chống phát lại không truy cập được | Không mặc định cho qua MFA |
| Phản hồi thành công bị mất trên mạng | Xử lý gửi lại theo trạng thái attempt, không chấp nhận OTP lần hai để tạo thêm kết quả |
| Đồng hồ một instance lệch lớn | Phát hiện và xử lý vận hành, không chấp nhận tùy ý |
| Người dùng khai mất điện thoại | Đi qua quy trình phục hồi, không bỏ MFA trực tiếp |
| OTP được hoàn tất cho tenant Alpha | Không tự cấp quyền quản trị tại tenant Beta |

Kiểm thử thuật toán bằng các test vector chính thức là một phần của việc xác nhận thư viện và cấu hình. Kiểm thử ứng dụng còn cần các ca về trạng thái, request đồng thời, giới hạn thử, liên kết attempt và phục hồi.

OTP có thể giảm rủi ro chỉ dựa vào mật khẩu, nhưng hiệu quả phụ thuộc cả vòng đời seed, tính một lần tại verifier và đường xử lý sau xác thực. Khi thiết kế IAM, cần xem OTP như một cơ chế có trạng thái và ngữ cảnh, không chỉ là phép so sánh hai chuỗi số.
