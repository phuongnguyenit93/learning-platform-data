# Per account rate limit — Giới hạn tần suất theo tài khoản

## 1. Vì sao cần giới hạn theo tài khoản?

Trong luồng khôi phục, giới hạn theo IP giúp kiểm soát nguồn gửi nhưng không đủ bảo vệ một tài khoản cụ thể. Kẻ tấn công có thể dùng nhiều nguồn mạng để cùng yêu cầu gửi mã hoặc thử đoán mã của một nạn nhân.

**Per account rate limit** là cơ chế áp dụng ngân sách hoặc hạn mức dựa trên tài khoản đích, bất kể yêu cầu đi qua IP, trình duyệt hoặc node xử lý nào.

Ví dụ:

```text
Nguồn A -> tài khoản U -> thử mã
Nguồn B -> tài khoản U -> thử mã
Nguồn C -> tài khoản U -> thử mã

Ngân sách tài khoản U phải nhìn thấy cả ba lần thử.
```

Đối với khôi phục tài khoản khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, cơ chế này phục vụ những mục tiêu khác nhau:

- Giảm khả năng đoán bằng chứng có không gian giá trị nhỏ, như OTP.
- Giảm gửi email, SMS hoặc push dồn dập tới cùng một người.
- Hạn chế tạo quá nhiều hồ sơ recovery cho cùng tài khoản.
- Giảm tác động của việc đổi IP, mở phiên mới hoặc chuyển kênh để né hạn mức.

Giới hạn theo tài khoản là một lớp kiểm soát. Dịch vụ vẫn cần giới hạn theo nguồn gửi, endpoint, năng lực hạ tầng và mức rủi ro.

OWASP đề cập rate limiting theo tài khoản như một biện pháp chống gửi yêu cầu khôi phục tự động quá mức. [OWASP, Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request)

## 2. Phải xác định đang đếm hành động nào

Một bộ đếm duy nhất có tên `recoveryCount` thường không đủ rõ để thiết kế chính sách. Một request khởi tạo không giống một lần gửi SMS, và một lần gửi SMS không giống một lần so sánh OTP.

| Loại ngân sách | Đơn vị được đếm | Mục đích |
| --- | --- | --- |
| Khởi tạo recovery | Yêu cầu hoặc hồ sơ mới được tiếp nhận theo chính sách | Giảm tạo hồ sơ dồn dập |
| Gửi hướng dẫn | Một lần tạo lệnh gửi hợp lệ | Giảm làm phiền và chi phí |
| Thử bằng chứng | Một ứng viên được phép đưa vào kiểm tra | Giới hạn khả năng đoán |
| Thử sai liên tiếp | Lần xác minh thất bại trong phạm vi credential hoặc chính sách tương ứng | Thực thi giới hạn retry |
| Thao tác nhạy cảm | Số lần được phép thực hiện thay đổi đã ủy quyền | Kiểm soát lạm dụng nghiệp vụ |

Các ngân sách có thể phối hợp nhưng không nên bị xóa hoặc tăng cùng nhau chỉ vì có chung từ “recovery”.

Ví dụ, việc gửi thành công một email không phải xác thực thành công. Nó không được tự xóa số lần thử sai của người đang cố đoán mã.

### Một bảng chính sách minh họa

Các con số dưới đây chỉ để giải thích cách chia phạm vi, không phải khuyến nghị áp dụng mặc định:

| Hành động | Phạm vi | Chính sách minh họa |
| --- | --- | --- |
| Gửi hướng dẫn | Tài khoản, tổng các kênh được hỗ trợ | Tối đa 3 lệnh gửi trong 15 phút |
| Gửi lại quá gần lần trước | Tài khoản | Gộp hoặc trì hoãn trong khoảng chờ tối thiểu |
| So sánh mã | Một challenge | Tối đa 5 ứng viên trong toàn bộ vòng đời challenge |
| So sánh mã | Tài khoản, nhóm bằng chứng mã ngắn | Tối đa 12 ứng viên trong cửa sổ trượt 30 phút |
| Retry của authenticator | Theo loại authenticator và yêu cầu bảo đảm | Hạn mức liên tiếp riêng, nếu được yêu cầu |

Hạn mức trong cửa sổ thời gian không tự thay thế yêu cầu về số lần thất bại liên tiếp. Khi áp dụng một chuẩn bảo đảm cụ thể, phải đáp ứng đồng thời các điều kiện liên quan.

## 3. Xác định đúng khóa tài khoản

### 3.1. Đếm theo danh tính nội bộ ổn định

Khi đã xác định được tài khoản trong ngữ cảnh phù hợp, nên dùng ID nội bộ cùng phạm vi dịch vụ hoặc tenant để đặt khóa ngân sách.

```text
account-budget:
    realm_id
    internal_account_id
    action_group
```

Không chỉ dùng chuỗi email mà người gọi nhập nếu cùng một tài khoản có nhiều định danh được dịch vụ công nhận. Nếu mỗi alias có một hạn mức độc lập, người gửi có thể luân phiên alias để tăng tổng số lần thử trên cùng tài khoản.

Cũng không nên dùng riêng:

- IP: nhiều IP vẫn có thể cùng nhắm một tài khoản.
- Cookie hoặc device ID: người gửi có thể mở phiên mới hoặc sao chép giá trị.
- Request ID: tạo request mới có thể tạo ngân sách mới.
- Tên endpoint: chuyển endpoint có thể né một chính sách vốn phải dùng chung.

### 3.2. Phân biệt đếm theo đầu vào và đếm theo tài khoản đã xác định

Endpoint công khai thường nhận một định danh trước khi người gọi chứng minh quyền kiểm soát tài khoản. Lúc này cần tránh để chính việc đặt hạn mức tiết lộ tài khoản tồn tại.

Có thể chia hai lớp:

1. **Lớp theo định danh đầu vào:** chuẩn hóa theo quy tắc của dịch vụ và tính ngân sách cho cả định danh tồn tại lẫn không tồn tại.
2. **Lớp theo tài khoản nội bộ:** sau khi xử lý nội bộ xác định tài khoản, áp dụng ngân sách chung cho mọi alias và kênh tương ứng.

Lớp thứ nhất không thay thế lớp thứ hai. Lớp thứ hai cũng không được tạo thông báo công khai chỉ xuất hiện với tài khoản có thật.

Nếu cần giảm lộ định danh trong tên khóa, có thể sử dụng HMAC với khóa bí mật phía máy chủ và dữ liệu được mã hóa cấu trúc rõ ràng. Đây là biện pháp giảm lộ dữ liệu, không phải cơ chế xác thực người gửi hoặc bảo đảm dữ liệu hoàn toàn vô danh.

Không tự áp dụng quy tắc xóa dấu chấm hoặc phần sau dấu cộng cho mọi email. Quy tắc định danh phải nhất quán với hệ thống tài khoản.

## 4. Giới hạn đoán mã cần nhìn vào tổng ngân sách

### 4.1. Độ dài mã và số lần thử liên quan trực tiếp

Giả sử có một mã ngẫu nhiên đều gồm 6 chữ số, với một giá trị hợp lệ trong tập một triệu giá trị. Nếu được thử 5 giá trị khác nhau cho cùng mã, xác suất đoán trúng là:

```text
5 / 1.000.000 = 0,000005 = 0,0005%
```

Ví dụ này chỉ xét đoán trực tuyến đối với một mã được sinh đều. Nó không tính việc đánh cắp mã, phishing, lỗi sinh ngẫu nhiên hoặc các bằng chứng khác được chấp nhận đồng thời.

Nếu hệ thống tạo nhiều challenge độc lập, mỗi challenge lại cho 5 lần thử mà không có ngân sách chung, tổng cơ hội sẽ tăng. Một giới hạn nhỏ trên từng request không bảo đảm giới hạn nhỏ trên tài khoản.

### 4.2. Gửi mã mới không được cấp lại vô hạn lượt đoán

Một đường né hạn mức:

```text
Thử sai gần hết lượt
    -> yêu cầu gửi mã mới
    -> bộ đếm về 0
    -> tiếp tục thử
```

NIST quy định giới hạn thử trực tuyến cho các loại authenticator liên quan; với bí mật xác thực ngoài băng được đề cập trong tài liệu, việc sinh bí mật mới không được đặt lại số lần thất bại. [NIST SP 800-63B-4, Authenticators](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/)

Áp dụng vào mô hình của bài:

- Challenge mới có trạng thái và hạn dùng riêng.
- Ngân sách thử theo tài khoản tiếp tục phản ánh các lần thử đã được phép.
- Bộ đếm thất bại liên tiếp được giữ theo chính sách của authenticator.
- Chuyển SMS sang email không tự cấp lại một ngân sách mã ngắn hoàn toàn độc lập nếu chính sách yêu cầu ngân sách chung.

Nếu một tiêu chuẩn đưa ra ngưỡng tối đa cho authenticator, không nên hiểu ngưỡng đó thành số lượt mặc định phải cấp cho mọi OTP. Dịch vụ cần lựa chọn mức phù hợp với rủi ro và đáp ứng các yêu cầu áp dụng.

## 5. Chọn mô hình thời gian phù hợp

### 5.1. Fixed window

Một cửa sổ cố định đơn giản có thể đếm số lượt trong từng khoảng thời gian, chẳng hạn các khoảng 15 phút theo mốc đồng hồ.

Điểm cần chú ý là ranh giới: nếu cho 3 lượt mỗi cửa sổ, người gửi có thể sử dụng 3 lượt ngay trước khi hết cửa sổ và 3 lượt ngay sau khi sang cửa sổ mới.

Đây không nhất thiết là lỗi triển khai. Nó là hành vi của thuật toán và phải phù hợp với điều mà chính sách hứa bảo vệ.

### 5.2. Sliding window

Cửa sổ trượt xem xét hoạt động trong khoảng gần nhất, chẳng hạn 30 phút tính từ thời điểm quyết định.

Cách lưu toàn bộ thời điểm cho kết quả khác với cách xấp xỉ bằng các bucket. Cần biết mức sai số của triển khai trước khi dùng cho giới hạn có yêu cầu nghiêm ngặt.

### 5.3. Token bucket

Token bucket cho phép một lượng burst có kiểm soát rồi bổ sung ngân sách theo tốc độ quy định. Nó phù hợp khi cần mô tả rõ khả năng tiếp nhận ngắn hạn và tốc độ dài hạn.

Đối với đoán OTP, chỉ một token bucket bổ sung đều chưa chắc đáp ứng được giới hạn retry liên tiếp hoặc giới hạn trong vòng đời challenge. Những điều kiện này cần được kiểm tra riêng.

### 5.4. TTL không phải chính sách reset cho mọi loại bộ đếm

Bộ đếm của một cửa sổ thời gian có thể hết hạn theo cửa sổ đó. Bộ đếm thử sai liên tiếp không nên bị xóa chỉ vì developer tái sử dụng cùng một TTL cache.

Tương tự, không vô tình kéo dài thời gian chờ mãi mãi mỗi khi có thêm request bị từ chối, trừ khi đó là chính sách có chủ đích và đã cân nhắc tác động với nạn nhân.

Một thiết kế cần mô tả được:

- Khi nào ngân sách được bổ sung hoặc cửa sổ hết hiệu lực.
- Request bị từ chối có làm thay đổi thời gian mở lại hay không.
- Điều kiện nào cho phép reset bộ đếm liên tiếp.
- Trạng thái nào cần được giữ lâu hơn vòng đời của một challenge.

## 6. Quyết định hạn mức phải nguyên tử trên mọi node

### 6.1. Đọc rồi tăng có thể cấp vượt lượt

Ví dụ, tài khoản còn đúng một lượt:

```text
Node A đọc remaining = 1
Node B đọc remaining = 1

A cho phép kiểm tra mã
B cũng cho phép kiểm tra mã
```

Hai node đã cấp hai lượt trong khi ngân sách chỉ còn một.

Quy trình “kiểm tra còn ngân sách rồi mới tăng sau” cần có ranh giới nguyên tử. Chỉ dùng một kho dữ liệu chung nhưng tách các thao tác không có bảo vệ vẫn có thể xảy ra cuộc đua.

Tài liệu Redis mô tả Lua script như một cách thực hiện chu trình đọc, quyết định và cập nhật nguyên tử tại nơi xử lý. Điều này cần được xem xét cùng phạm vi khóa và kiến trúc triển khai. [Redis, Rate Limiter](https://redis.io/docs/latest/develop/use-cases/rate-limiter/)

### 6.2. Không đợi xác minh thất bại rồi mới quyết định có được thử

Nếu chỉ tăng số lần sai sau khi so sánh, nhiều request song song có thể cùng được kiểm tra trước khi bộ đếm đạt ngưỡng.

Một thiết kế đơn giản hơn để giải thích là **giữ chỗ một lượt trước khi so sánh bằng chứng**. Mỗi ứng viên được phép so sánh đã chiếm ngân sách tài khoản và challenge.

Sau đó có thể cập nhật thêm số lần thất bại liên tiếp nếu kết quả sai. Đây là hai đại lượng khác nhau:

- Số ứng viên đã được phép kiểm tra.
- Số lần xác minh thất bại liên tiếp theo chính sách.

Không nên cho rằng vì ứng viên đúng thì mọi ngân sách gửi và tiếp nhận cũng cần được hoàn lại.

### 6.3. Nếu dùng nhiều vùng

Cần xác định nơi nào có thẩm quyền cấp lượt cho một tài khoản. Nếu mỗi vùng tự cấp đầy đủ hạn mức, tổng hạn mức thực tế có thể bị nhân theo số vùng.

Một lựa chọn là định tuyến quyết định của cùng tài khoản về cùng chủ sở hữu trạng thái. Lựa chọn khác là cơ chế ngân sách phân bổ có giới hạn rõ ràng.

Chỉ đồng bộ cuối cùng các bộ đếm không tự bảo đảm một ngưỡng toàn cục nghiêm ngặt.

## 7. Giả mã cho kiểm tra OTP theo tài khoản

Ví dụ sau dùng giao dịch cơ sở dữ liệu và ngân sách cửa sổ trượt. Nó minh họa ranh giới trạng thái, không phải mã sản phẩm hoàn chỉnh.

```text
verifyRecoveryCode(requestRef, candidateCode, recoveryContext):
    require boundedInputAndValidCodeSyntax(candidateCode)
    require sourceAdmissionAllowsRequest(recoveryContext)

    result = transaction:
        requestSnapshot = resolveRecoveryReference(requestRef)

        account = lockAccount(requestSnapshot.accountId)
        request = lockRecoveryRequest(requestSnapshot.requestId)
        challenge = lockChallenge(request.challengeId)
        budget = lockAccountVerificationBudget(account.id, SHORT_CODE)

        require recoveryContext.isValidFor(account, request)
        require request.isAllowedToVerifyCode()
        require challenge.belongsTo(account, request)

        now = trustedServerTime()

        if challenge.isExpiredOrTerminal(now):
            return INVALID_OR_EXPIRED

        budget.discardWindowEntriesOlderThan(now - policy.window)

        if budget.attemptsInWindow >= policy.accountAttemptLimit:
            return TEMPORARILY_LIMITED

        if challenge.admittedAttempts >= policy.challengeLifetimeLimit:
            challenge.markExhausted()
            return INVALID_OR_EXPIRED

        if retryPolicy.isSuspendedFor(account, challenge):
            return RECOVERY_METHOD_UNAVAILABLE

        budget.reserveAttempt(now)
        challenge.admittedAttempts += 1

        if not codeVerifier.matchesStoredSecret(candidateCode, challenge):
            retryPolicy.recordFailure(account, challenge)

            if challenge.admittedAttempts >= policy.challengeLifetimeLimit:
                challenge.markExhausted()

            return INVALID_CODE

        challenge.consumeOnce(now)
        recordVerifiedRecoveryEvidence(
            account = account,
            request = request,
            purpose = challenge.purpose
        )

        retryPolicy.recordSuccessfulVerificationForRelevantScope(
            account,
            challenge
        )

        return VERIFIED_FOR_NEXT_STEP

    return mapResultToAuthorizedResponse(result, recoveryContext)
```

### Những điều kiện ngầm phải được triển khai đúng

**Trả kết quả sai vẫn phải commit bộ đếm.** Nếu dùng exception khiến giao dịch rollback mỗi lần mã sai, số lượt đã dùng và số lần thất bại có thể biến mất. Phản hồi xác minh thất bại là kết quả nghiệp vụ, không mặc nhiên là lỗi hạ tầng cần hoàn tác.

**Ngữ cảnh phải được kiểm tra ở backend.** Client không được tự gửi một `accountId` khác để chọn bộ đếm rẻ hơn hoặc một cờ “đã xác minh” để bỏ qua kiểm soát.

**Cơ chế khóa cần nhất quán.** Tất cả luồng có thể thay trạng thái liên quan phải tuân theo cùng ranh giới đồng bộ; việc ghi thêm dòng ngân sách từ một endpoint khác không được bỏ qua khóa tài khoản.

**Kết quả đúng chỉ cho phép bước tiếp theo đã định nghĩa.** Một OTP đúng không tự trở thành quyền tắt toàn bộ MFA, đổi mọi địa chỉ recovery hoặc cấp session đặc quyền.

**Không gọi nhà cung cấp email hoặc SMS trong giao dịch giữ khóa.** Tác động bên ngoài cần cơ chế xử lý riêng, với khả năng tránh gửi lặp và trạng thái phù hợp.

## 8. Giới hạn theo tài khoản không được làm lộ sự tồn tại tài khoản

### 8.1. Một lỗi phản hồi thường gặp

```text
Định danh có tài khoản:
    sau vài request -> "Tài khoản đã hết lượt recovery."

Định danh không có tài khoản:
    luôn -> "Nếu phù hợp, hướng dẫn sẽ được gửi."
```

Người gọi có thể dùng khác biệt đó để xác nhận tài khoản.

Đối với bước khởi tạo công khai, thiết kế của bài áp dụng thông báo chung cho việc gửi hướng dẫn. Hạn mức nội bộ có thể khiến dịch vụ không gửi thêm, nhưng không trả chi tiết ngân sách tài khoản cho người chưa có quyền.

Các trường như `remainingAttempts`, `accountLocked`, `nextAccountResetAt` và header tương ứng đều có thể tiết lộ thông tin. Không chỉ body mới cần được xem xét.

### 8.2. 429 và thông báo chờ

HTTP 429 biểu thị người gọi gửi quá nhiều yêu cầu và có thể kèm `Retry-After`; chuẩn không áp đặt một cách duy nhất để xác định phạm vi đếm. [RFC 6585, 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)

Trong mô hình này:

- Giới hạn nguồn gửi công khai có thể trả phản hồi yêu cầu chờ theo hợp đồng chung.
- Quyết định không gửi thêm thông báo theo tài khoản được thực thi nội bộ.
- Ở bước có ngữ cảnh recovery phù hợp, dịch vụ có thể cung cấp hướng dẫn chờ cần thiết nhưng không mở quyền xem toàn bộ trạng thái bảo mật của tài khoản.

Không coi việc có một request ID là đủ để tiết lộ mọi hạn mức hoặc xác nhận một tài khoản có thật.

## 9. Tránh biến hạn mức thành công cụ gây gián đoạn

### 9.1. Giới hạn một hành động khác với khóa toàn tài khoản

Một người chưa xác thực có thể cố tình tiêu thụ ngân sách của nạn nhân. Vì vậy, việc đạt hạn mức gửi email không nên tự khóa đăng nhập bằng passkey đang hoạt động hoặc tự thu hồi mọi session hợp lệ.

Cần tách:

- Tạm không gửi thêm hướng dẫn.
- Tạm không cho thử thêm mã ở nhánh recovery cụ thể.
- Đình chỉ một authenticator theo yêu cầu retry và chính sách bảo đảm.
- Khóa hoặc hạn chế toàn tài khoản do một quyết định xử lý sự cố riêng.

Đây là các hành động có phạm vi và hậu quả khác nhau.

### 9.2. Thừa nhận giới hạn về tính sẵn sàng

Một giới hạn nghiêm ngặt theo tài khoản có thể bị người ngoài làm cạn. Không có lựa chọn vừa cho mọi lần thử vô hạn vừa bảo đảm ngân sách đoán hữu hạn.

Để giảm tác động, dịch vụ có thể phối hợp giới hạn nguồn, thử thách chống tự động hóa, thời gian chờ có giới hạn và phương thức xác thực mạnh còn hoạt động.

Một credential dự phòng đã đăng ký có thể dẫn tới một nhánh được ủy quyền khác, với chính sách riêng phù hợp. Đây không phải nút “bỏ qua hạn mức” chỉ cần người dùng tự nhận mình là chủ tài khoản.

Hỗ trợ viên cũng không được xóa bộ đếm hoặc cấp lại quyền chỉ vì người gọi yêu cầu. Việc reset cần có điều kiện, phạm vi và dấu vết nội bộ.

## 10. Khi nào được reset và phải giữ lại điều gì?

Một chính sách reset cần trả lời chính xác loại trạng thái được thay đổi.

| Sự kiện | Điều cần cân nhắc |
| --- | --- |
| Người dùng bấm gửi lại | Không cấp lại vô hạn ngân sách thử theo tài khoản |
| Challenge hết hạn | Kết thúc challenge; không mặc nhiên xóa lịch sử retry liên quan |
| Đổi IP hoặc mở trình duyệt mới | Không reset ngân sách tài khoản |
| Mã được xác minh thành công | Chỉ điều chỉnh retry ở phạm vi được chính sách cho phép |
| Recovery hoàn tất có ủy quyền | Vô hiệu hóa bằng chứng đã dùng và ghi lại chuyển trạng thái |
| Đổi cấu hình hoặc triển khai phiên bản mới | Không vô tình tạo ngân sách mới bằng cách đổi tên key |

Với bộ đếm cửa sổ, dữ liệu cũ có thể được dọn khi không còn ảnh hưởng quyết định. Với trạng thái đình chỉ hoặc retry liên tiếp, thời gian giữ phải theo quy tắc của chính sách tương ứng.

Nếu thay thuật toán hoặc đổi schema key, cần xác định cách chuyển tiếp ngân sách đang có. Việc deploy không phải lý do để mọi tài khoản tự được cấp lại toàn bộ lượt thử.

## 11. Xử lý lỗi kho hạn mức

Nếu kho trạng thái không truy cập được, ứng dụng không nên tự coi ngân sách của mọi tài khoản là chưa dùng.

Đối với kiểm tra OTP có rủi ro cao, một chính sách an toàn là tạm dừng bước xác minh khi không thể xác định còn lượt hay không. Với gửi thông báo, có thể tạm dừng hoặc trì hoãn để bảo vệ người nhận và chi phí.

Không tự chuyển sang một bộ đếm bộ nhớ riêng trên mỗi node rồi vẫn tuyên bố giữ nguyên hạn mức toàn hệ thống.

Một chế độ suy giảm, nếu được thiết kế, phải có phạm vi và ngân sách rõ ràng. Nó không được âm thầm biến lỗi phụ thuộc thành quyền thử mã không giới hạn.

Cần phân biệt nội bộ:

- Hết ngân sách.
- Bằng chứng sai.
- Challenge đã hết hạn hoặc dùng rồi.
- Credential bị đình chỉ.
- Không kiểm tra được trạng thái do lỗi hạ tầng.

Lỗi kho dữ liệu không phải bằng chứng người dùng đang tấn công. Phản hồi và thông báo cần phản ánh đúng khả năng tiếp tục của hệ thống.

## 12. Quan sát vận hành và tình huống vận dụng

Có thể theo dõi số lượt được cấp, số lượt bị giới hạn, số thông báo thực gửi, số request bị gộp và lỗi phụ thuộc. Hạn chế đưa account ID làm nhãn metric công khai hoặc có số lượng giá trị không kiểm soát.

Log không nên chứa OTP, token recovery, cookie hoặc địa chỉ liên hệ đầy đủ nếu không cần thiết. Tham chiếu giả danh hóa vẫn cần được quản lý như dữ liệu có khả năng liên kết.

Các tình huống cần giải thích được:

**Nhiều IP cùng nhắm một tài khoản:** các nguồn có ngân sách riêng nhưng chia sẻ ngân sách tài khoản; thay IP không cấp lại lượt.

**Tạo challenge mới sau khi thử sai:** challenge mới không xóa ngân sách cửa sổ hoặc retry liên tiếp của phạm vi cần bảo vệ.

**Hai request tranh lượt cuối:** quyết định cấp lượt phải nguyên tử; chỉ một request được phép kiểm tra nếu chỉ còn một lượt.

**Mã sai làm giao dịch rollback:** cần sửa ranh giới xử lý để trạng thái hạn mức đã sử dụng vẫn được lưu như kết quả nghiệp vụ.

**Gửi quá nhiều hướng dẫn:** dịch vụ hạn chế gửi, không tự biến yêu cầu chưa xác minh thành việc khóa toàn bộ tài khoản.

**Kho hạn mức bị lỗi:** bước nhạy cảm dừng hoặc suy giảm theo chính sách đã định; không mặc định mở hoàn toàn.

## 13. Câu hỏi tự kiểm tra

1. Hạn mức theo IP khác hạn mức theo tài khoản ở điểm nào?
2. Vì sao nên tách ngân sách gửi mã và ngân sách thử mã?
3. Một tài khoản có nhiều alias có thể né hạn mức ra sao nếu khóa được thiết kế sai?
4. Vì sao tạo challenge mới không được cấp lại vô hạn lượt đoán?
5. Điều gì xảy ra khi nhiều request cùng kiểm tra trước rồi mới tăng bộ đếm?
6. Vì sao một kết quả mã sai vẫn cần commit trạng thái hạn mức?
7. Khi nào phản hồi hết lượt có thể trở thành công cụ dò tài khoản?
8. Làm thế nào giữ một nhánh xác thực mạnh còn hợp lệ mà không cho người ngoài bỏ qua hạn mức?

Điểm cốt lõi là xác định đúng phạm vi tài khoản, đúng loại hành động và đúng điều kiện reset. Một hạn mức chỉ bảo vệ được recovery khi các node cùng thực thi quyết định nhất quán, việc đổi request không cấp lại ngân sách và người chưa xác minh không thể dùng cơ chế đó để tiết lộ hoặc khóa tùy ý tài khoản của người khác.
