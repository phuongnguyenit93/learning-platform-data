# Knowledge proofing attempt limits — Giới hạn lượt thử câu hỏi kiến thức

## 1. Mục tiêu và giới hạn của biện pháp

Trong một luồng khôi phục tài khoản cũ, người dùng có thể được hỏi về thông tin cá nhân, lịch sử sử dụng hoặc câu trả lời đã đăng ký trước. Nếu hệ thống cho phép thử không giới hạn, kẻ tấn công có thể đoán, thay đổi câu trả lời và tích lũy thông tin từ phản hồi của dịch vụ.

**Knowledge proofing attempt limits** là các giới hạn đối với việc phát hành bộ câu hỏi và kiểm tra câu trả lời. Chúng kiểm soát ngân sách đoán mà hệ thống cho phép, kể cả khi người thử đổi phiên, đổi địa chỉ IP hoặc chuyển sang một kênh hỗ trợ khác.

Biện pháp này có giới hạn nền tảng: câu trả lời về đời tư có thể đã bị lộ, được công khai hoặc được người quen biết. NIST SP 800-63A-4 không cho phép dùng knowledge-based verification hoặc knowledge-based authentication để thực hiện identity verification theo hướng dẫn đó. Do vậy, việc đặt ngưỡng thử không biến câu hỏi kiến thức thành phương thức chứng minh danh tính phù hợp với yêu cầu này. [NIST SP 800-63A-4 — Identity Verification Methods](https://pages.nist.gov/800-63-4/sp800-63a/proofing/#identity-verification-methods)

Bài học tập trung vào cách kiểm soát rủi ro trong hệ thống còn tồn tại bước hỏi kiến thức, chẳng hạn trong giai đoạn chuyển đổi hoặc khi thu thập tín hiệu phụ trợ về gian lận. Thiết kế mới nên sử dụng phương thức khôi phục phù hợp với mức bảo đảm của tài khoản, thay vì lấy câu hỏi kiến thức làm đường cấp lại quyền truy cập.

Sau bài học, người học có thể:

- Định nghĩa chính xác một lượt thử và phân biệt nó với việc phát hành câu hỏi.
- Đặt giới hạn ở nhiều phạm vi mà không để việc tạo phiên mới làm mất lịch sử.
- Thiết kế cơ chế đếm chịu được gửi đồng thời, retry và lỗi nhà cung cấp.
- Ngăn việc lợi dụng giới hạn khôi phục để gây từ chối dịch vụ cho nạn nhân.
- Giữ kết quả câu hỏi tách biệt với quyền đặt lại mật khẩu, MFA hoặc passkey.

## 2. Vì sao cần giới hạn cả tốc độ lẫn tổng số lượt

Giới hạn tốc độ trả lời câu hỏi “trong một khoảng thời gian ngắn có bao nhiêu yêu cầu được xử lý?”. Giới hạn tổng số lượt trả lời câu hỏi “đối với mục tiêu này, bao nhiêu cơ hội đoán đã được cấp trong phạm vi chính sách?”. Hai cơ chế bổ sung cho nhau.

Ví dụ, cho phép một lượt mỗi phút nhưng không có giới hạn dài hơn vẫn tạo ra nhiều cơ hội đoán trong một ngày. Ngược lại, giới hạn ba lượt cho mỗi phiên không có tác dụng đáng kể nếu một người có thể tạo hàng nghìn phiên.

Một mô hình đơn giản giúp thấy tác động của số lượt. Giả sử bộ câu hỏi có ba câu, mỗi câu bốn phương án, yêu cầu đúng cả ba. Nếu các tổ hợp đáp án đều có khả năng như nhau và người tấn công không biết gì, có `4 × 4 × 4 = 64` tổ hợp. Thử ba tổ hợp khác nhau có xác suất thành công `3/64`, tức khoảng `4,69%`, thay vì `1/64` cho một lần đoán.

Đây chỉ là ví dụ toán học có giả định chặt chẽ. Câu trả lời thực tế không phân bố đều và có thể tương quan. Nếu kẻ tấn công biết sẵn toàn bộ đáp án, chỉ một lượt cũng đủ. Tăng số câu hoặc giảm số lượt không bù được việc câu trả lời đã bị lộ.

Phản hồi từng câu còn làm vấn đề nghiêm trọng hơn. Nếu dịch vụ xác nhận câu nào đúng, người thử có thể giữ đáp án đã biết và chỉ đổi phần còn lại, thay vì phải đoán một bộ hoàn chỉnh mà không có gợi ý.

## 3. Định nghĩa đơn vị được tính

### 3.1. Lượt phát hành và lượt kiểm tra là hai ngân sách khác nhau

| Sự kiện | Ngân sách phù hợp | Lý do cần theo dõi |
| --- | --- | --- |
| Yêu cầu tạo bộ câu hỏi | Phát hành challenge | Ngăn xin nhiều bộ để chọn câu dễ và hạn chế chi phí |
| Nộp một bộ câu trả lời mới, đủ điều kiện kiểm tra | Kiểm tra câu trả lời | Đây là một cơ hội đoán |
| Gửi lại cùng yêu cầu do mất kết nối | Cùng một lượt nếu idempotency hợp lệ | Tránh tính hai lần chỉ vì retry |
| Dùng cùng định danh retry nhưng đổi câu trả lời | Vi phạm ràng buộc của yêu cầu | Không được tạo phép kiểm tra miễn phí |
| Nộp dữ liệu sai cấu trúc trước khi so sánh đáp án | Giới hạn lưu lượng và dữ liệu đầu vào | Không nhất thiết là một phép đoán, nhưng vẫn có thể gây lạm dụng |
| Gọi lại sau khi hết ngân sách | Yêu cầu bị chặn trước khi kiểm đáp án | Không được tiếp tục chạy bộ so sánh ở phía sau |
| Chờ kết quả từ nhà cung cấp | Lượt đã được giữ chỗ | Chưa có kết quả không có nghĩa là chưa tiêu tốn cơ hội kiểm tra |

Một thiết kế dễ giải thích là tính **một lần nộp trọn bộ câu trả lời** thành một lượt. Máy chủ chấm bộ đó mà không trả kết quả từng câu cho client. Số câu trong bộ không được dùng làm số lượt còn lại.

Nếu giao diện nộp từng câu riêng, mỗi lần so sánh có thể cung cấp một cơ hội đoán riêng. Khi đó mô hình ngân sách phải phản ánh thực tế này; không thể gọi cả chuỗi phép so sánh là “một lượt” để che số cơ hội mà người thử có được.

### 3.2. Nên đếm trước khi biết đúng hay sai

Đối với ngân sách đoán, mọi lần kiểm tra được chấp nhận đều tiêu tốn một lượt, bao gồm lần cho kết quả khớp. Đếm chỉ những lần sai khiến việc kiểm soát phụ thuộc quá muộn vào kết quả và dễ tạo nhầm lẫn khi có nhiều yêu cầu đồng thời.

Hệ thống vẫn có thể giữ chỉ số số lần không khớp để phân tích rủi ro. Chỉ số này khác với bộ đếm lượt đã được cấp phép kiểm tra.

Một lượt cần được giữ chỗ trước khi thực hiện so sánh hoặc gửi câu trả lời cho nhà cung cấp. Nếu kiểm tra đáp án xong mới tăng bộ đếm, nhiều yêu cầu có thể đồng thời nhìn thấy cùng một lượt còn lại.

## 4. Các phạm vi giới hạn cần phối hợp

### 4.1. Theo challenge và yêu cầu khôi phục

Challenge cần có thời hạn, bộ câu hỏi cố định, số lượt tối đa và liên kết với yêu cầu khôi phục ở phía máy chủ. Không để client tự chọn tài khoản mục tiêu, phiên bản câu hỏi hoặc số lượt còn lại.

Giới hạn theo yêu cầu khôi phục ngăn việc xin bộ câu hỏi mới trong cùng hồ sơ để nhận lại toàn bộ ngân sách. Tuy nhiên, nó vẫn chưa đủ nếu người thử có thể mở hồ sơ khôi phục mới.

### 4.2. Theo tài khoản mục tiêu

Ngân sách gắn với tài khoản mục tiêu cần tồn tại độc lập với cookie hoặc phiên trình duyệt. Những yêu cầu nhắm vào cùng một tài khoản phải đi qua cùng phạm vi đếm, dù được gửi từ nhiều địa chỉ IP.

Máy chủ phải ánh xạ các bí danh của cùng tài khoản về một định danh nội bộ ổn định. Nếu email và tên đăng nhập có bộ đếm riêng, một người có thể tăng số cơ hội đoán chỉ bằng cách thay cách gọi cùng mục tiêu.

Khóa đếm cũng cần chứa ngữ cảnh tenant khi hệ thống có nhiều tenant. Không nên dùng một định danh do client tùy ý cung cấp làm nguồn chuẩn của bộ đếm.

OWASP khuyến nghị gắn bộ đếm thất bại đăng nhập với tài khoản thay vì chỉ địa chỉ IP. Khi vận dụng nguyên tắc này cho bước khôi phục cũ, cần giới hạn tuyến câu hỏi mà không biến yêu cầu khôi phục chưa được xác thực thành quyền khóa đăng nhập của nạn nhân. [OWASP — Authentication Cheat Sheet: Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#account-lockout)

### 4.3. Theo nguồn và toàn dịch vụ

Giới hạn theo IP, dải mạng hoặc tín hiệu thiết bị giúp giảm bot và bảo vệ tài nguyên. Chúng không thay thế giới hạn theo mục tiêu: một botnet có thể phân tán qua nhiều nguồn, còn nhiều người dùng hợp lệ có thể dùng chung một IP.

Giới hạn toàn dịch vụ hoặc theo nhà cung cấp bảo vệ năng lực xử lý và chi phí. Khi hết hạn mức hạ tầng, kết quả phải là tạm hoãn hoặc chuyển tuyến đã phê duyệt, không phải bỏ qua phép kiểm tra để cho khôi phục tiếp tục.

### 4.4. Theo các kênh cùng thực hiện câu hỏi kiến thức

Website, ứng dụng di động, tổng đài và quy trình hỗ trợ phải chia sẻ ngân sách mục tiêu nếu đều thực hiện cùng loại phép kiểm tra kiến thức. Nếu mỗi kênh cấp thêm năm lượt độc lập, tổng số cơ hội thực tế lớn hơn ngưỡng được công bố cho một tài khoản.

Tuyến thay thế dùng bằng chứng độc lập có thể có ngân sách riêng theo rủi ro của nó. Không cần vô hiệu hóa mọi phương thức khôi phục khi tuyến câu hỏi hết lượt. Điều cần tránh là một kênh khác tiếp tục hỏi cùng dữ kiện và âm thầm cấp ngân sách mới.

## 5. Thiết kế cửa sổ đếm và thời gian chờ

| Cơ chế | Tác dụng | Điểm cần chú ý |
| --- | --- | --- |
| Giới hạn suốt vòng đời challenge | Chặn đoán lặp trên cùng bộ câu hỏi | Tạo challenge mới không được xóa bộ đếm mục tiêu |
| Cửa sổ cố định | Dễ triển khai và giải thích | Có thể xuất hiện cụm yêu cầu ở hai phía ranh giới cửa sổ |
| Cửa sổ trượt | Đánh giá tổng số lượt trong khoảng thời gian gần nhất | Cần trạng thái hoặc thuật toán bảo đảm giới hạn đã chọn |
| Token bucket | Kiểm soát tốc độ trung bình và độ bùng phát | Token nạp lại vẫn cấp thêm lượt theo thời gian |
| Cooldown | Tạm ngừng tiếp nhận lượt mới | Không thay thế ngân sách dài hạn |
| Ngưỡng dài hơn để chuyển tuyến | Giảm đoán chậm kéo dài | Cần lối hỗ trợ không tiếp tục dựa trên cùng câu hỏi |

Nếu yêu cầu là “không quá năm lượt trong bất kỳ khoảng 24 giờ nào”, một bộ đếm đặt lại lúc 00:00 không đáp ứng đúng ý nghĩa đó. Năm lượt ngay trước và năm lượt ngay sau thời điểm đặt lại tạo thành mười lượt trong một khoảng rất ngắn.

Cooldown nên được kiểm tra bằng thời gian tin cậy ở máy chủ. Client có thể hiển thị thời gian chờ nhưng không được quyết định rằng thời gian chờ đã hết. Việc restart một tiến trình hoặc chuyển node cũng không được đặt lại lịch sử.

Những yêu cầu bị từ chối sau khi đã hết lượt không nên liên tục đẩy dài thời điểm mở lại tuyến cho nạn nhân. Nếu có cơ chế kéo dài thời gian chờ do lạm dụng, nó phải dựa trên chính sách riêng có đánh giá nguy cơ từ chối dịch vụ, không phải tác dụng phụ của mọi lần gọi endpoint.

### Ví dụ cấu hình để phân tích

Các con số dưới đây chỉ minh họa quan hệ giữa các giới hạn, không phải ngưỡng an toàn mặc định hoặc yêu cầu của NIST/OWASP:

```yaml
legacyKnowledgeStep:
  challengeLifetime: PT5M
  maxEvaluationsPerChallenge: 3
  maxEvaluationsPerTargetRolling24Hours: 5
  maxChallengesPerTargetRollingHour: 2
  cooldownAfterChallengeExhausted: PT15M
  onTargetBudgetExhausted: INDEPENDENT_RECOVERY_ROUTE
  answerMatchGrantsRecovery: false
```

Trong ví dụ này, challenge thứ hai không được cấp thêm ba lượt nếu tài khoản chỉ còn hai lượt trong cửa sổ 24 giờ. Hết 15 phút chờ của challenge trước cũng không khôi phục các lượt đã dùng trong cửa sổ dài hơn.

Các giá trị thực tế cần được quyết định theo thiệt hại tiềm tàng, mức dễ đoán của dữ kiện, chi phí xác minh và khả năng hỗ trợ người dùng. Một ngưỡng rất thấp vẫn không đủ nếu đáp án đã biết; một ngưỡng quá thấp mà thiếu tuyến thay thế có thể gây khó khăn cho người dùng hợp lệ.

## 6. Không để cấp lại challenge tạo ra lượt miễn phí

Ngân sách phát hành kiểm soát việc xem hoặc xin các bộ câu hỏi mới. Nó cần áp dụng trước khi hệ thống gọi nhà cung cấp hoặc cung cấp dữ liệu câu hỏi cho client.

Khi người dùng chọn “thử bộ câu hỏi khác”, hệ thống phải xác định đó là đổi challenge trong cùng yêu cầu, tạo challenge kế tiếp hay chuyển tuyến. Dù lựa chọn nào, bộ đếm theo tài khoản và lịch sử các lần kiểm tra vẫn được giữ.

Một số trường hợp không được tự động đặt lại ngân sách:

- Tải lại trang, xóa cookie hoặc mở cửa sổ riêng tư.
- Đổi IP, thiết bị hoặc ứng dụng.
- Dùng tên đăng nhập thay cho email của cùng tài khoản.
- Xin gửi lại liên kết khôi phục hoặc tạo hồ sơ khôi phục mới.
- Chuyển từ giao diện tự phục vụ sang nhân viên hỗ trợ để hỏi cùng dữ kiện.
- Cập nhật giao diện, triển khai phiên bản dịch vụ mới hoặc restart cache.

Challenge mới có thể có thời hạn mới, nhưng thời hạn mới không phải là lý do xóa lịch sử mục tiêu. Tương tự, đổi thứ tự các câu hỏi không tạo ra một bằng chứng độc lập.

## 7. Tính nguyên tử khi nhiều yêu cầu đến cùng lúc

### 7.1. Lỗi kiểm tra rồi mới tăng

Giả sử tài khoản còn một lượt, hai node cùng chạy logic sau:

```text
if remainingAttempts > 0:
    compareAnswers()
    remainingAttempts = remainingAttempts - 1
```

Cả hai có thể đọc thấy còn một lượt và đều thực hiện so sánh. Ngân sách thực tế đã bị vượt dù bộ đếm cuối cùng có thể trông vẫn hợp lệ. Dùng biến trong bộ nhớ của từng JVM không giải quyết được vấn đề trên một cụm nhiều node.

Thiết kế đúng cần thao tác nguyên tử để đồng thời kiểm tra trạng thái, giữ chỗ lượt và ghi định danh lần thử. Có thể dùng giao dịch cơ sở dữ liệu hoặc cơ chế lưu trữ khác có bảo đảm tương ứng. Khóa trong một tiến trình chỉ đủ khi toàn bộ phạm vi thực thi thật sự nằm trong tiến trình đó.

### 7.2. Giữ chỗ trước, kiểm tra sau

Một lần tiếp nhận câu trả lời nên tạo bản ghi attempt có định danh duy nhất và trạng thái ban đầu `RESERVED`. Việc giữ chỗ tiêu tốn ngân sách ngay cả khi kết quả chưa có.

Các điều kiện bắt buộc cần được xử lý như một thao tác chấp nhận thống nhất:

1. Challenge thuộc đúng yêu cầu và tài khoản đã được máy chủ xác định.
2. Challenge còn mở, còn thời hạn và phù hợp với phiên bản chính sách.
3. Không có yêu cầu retry đã được ghi nhận cho cùng định danh.
4. Mọi ngân sách bắt buộc còn đủ và thời gian chờ đã hết.
5. Một lượt được ghi nhận đồng thời vào các phạm vi cần thiết.

Nếu một phạm vi không đủ ngân sách, không được chạy phép kiểm tra đáp án. Cơ chế giữ chỗ nhiều phạm vi phải tránh việc một phần được chấp nhận rồi phần khác bỏ qua giới hạn. Nếu không có giao dịch xuyên tất cả kho, thiết kế phải nêu rõ cách giữ tính bảo thủ, xử lý giữ chỗ dở dang và tránh cấp phép vượt ngân sách.

Mã giả dưới đây giả định các bộ đếm cốt lõi theo challenge, yêu cầu và mục tiêu nằm trong cùng ranh giới giao dịch:

```text
submitAnswers(serverContext, challengeId, idempotencyKey, answers):
    validateSizeAndStructureBeforeAnswerComparison(answers)
    applyTrafficAbuseControls(serverContext)

    fingerprint = keyedFingerprintOfCanonicalRequest(answers)

    reservation = transaction:
        lockRelevantStateInStableOrder(serverContext, challengeId)

        prior = findAttempt(serverContext, challengeId, idempotencyKey)
        if prior exists:
            require prior.requestFingerprint == fingerprint
            return prior.withoutNewEvaluation()

        require challengeBelongsTo(serverContext)
        require challengeIsOpenAndNotExpired()
        require serverCooldownHasEnded()
        require everyMandatoryBudgetHasCapacity()

        chargeOneSlotToEveryMandatoryBudget()
        createUniqueAttempt(status=RESERVED, fingerprint=fingerprint)
        return reservationForNewAttempt()

    if reservation.isExistingAttempt:
        return authorizedViewOfExistingOutcomeOrPending()

    enqueueEvaluationExactlyForThisAttempt(reservation.attemptId)
    return PENDING
```

`serverContext` ở đây được máy chủ khôi phục từ phiên hạn chế hoặc hồ sơ hợp lệ. Client không được tự truyền một `targetId` khác để chọn bộ đếm có lợi hơn.

Tên hàm enqueue chỉ mô tả ý định gắn công việc với một attempt; nó không tự bảo đảm giao hàng đúng một lần qua mạng. Phần xử lý retry và nhà cung cấp vẫn cần được thiết kế rõ ràng.

### 7.3. Lượt cuối vẫn phải được kiểm tra

Khi còn đúng một lượt, hệ thống được phép giữ chỗ lượt đó rồi xử lý kết quả. Sau khi giữ chỗ, không nhận thêm lần nộp mới vì dung lượng còn lại đã bằng không.

Không được kiểm tra “còn lượt hay không” thêm lần nữa sau khi đã trừ lượt rồi từ chối chính lần thử cuối hợp lệ. Thay vào đó, quyền xử lý attempt dựa trên bản ghi giữ chỗ đã được cấp trước đó.

Nếu lần cuối không khớp, challenge chuyển sang hết lượt. Nếu khớp, kết quả chỉ hoàn tất bước kiến thức phụ trợ. Trong cả hai trường hợp, không xóa lịch sử ngân sách mục tiêu để mở lại cơ hội đoán.

## 8. Retry, timeout và kết quả chưa xác định

### 8.1. Idempotency phải gắn với cùng nội dung

Client mất phản hồi có thể gửi lại cùng yêu cầu. Khi định danh idempotency, challenge và nội dung đã chuẩn hóa trùng nhau, hệ thống trả trạng thái của attempt cũ thay vì chấm lại hoặc tính thêm lượt.

Nếu cùng idempotency key nhưng nội dung khác, phải từ chối xung đột. Không được lấy định danh cũ làm giấy phép kiểm tra vô hạn những bộ đáp án mới. Định danh cũng phải có phạm vi rõ ràng và bản ghi phải được giữ đủ lâu để retry không biến thành yêu cầu mới ngoài ý muốn.

Nếu cần fingerprint nội dung chứa câu trả lời ít entropy, không dùng mã băm thuần túy được lưu rộng rãi. Một MAC có khóa do máy chủ bảo vệ giúp tránh việc người có bản ghi fingerprint dễ thử từ điển offline. Fingerprint vẫn là dữ liệu nhạy cảm và chỉ nên giữ theo nhu cầu idempotency đã xác định.

### 8.2. Timeout không tạo ra lượt miễn phí

Một timeout có thể xảy ra sau khi nhà cung cấp đã kiểm tra đáp án nhưng trước khi hệ thống nhận kết quả. Do đó không thể mặc định hoàn lại lượt mỗi khi mạng lỗi.

Phương án bảo thủ là giữ lượt đã tính, đánh dấu kết quả `UNKNOWN` hoặc `PENDING_RECONCILIATION` và tra cứu lại cùng giao dịch. Không nộp lại câu trả lời như một giao dịch mới trong khi chưa biết giao dịch trước đã chạy hay chưa.

Chỉ điều chỉnh ngân sách theo quy tắc phục hồi đã xác định, chẳng hạn có chứng cứ đáng tin rằng công việc chưa bao giờ được thực hiện. Việc điều chỉnh phải có dấu vết và không trở thành cách người dùng kích hoạt lỗi để nhận thêm lượt.

### 8.3. Phân biệt ngân sách ứng dụng với tác dụng phụ tại nhà cung cấp

Một worker có thể nhận lại cùng công việc do hàng đợi giao lặp. Cần dùng attempt ID làm khóa chống lặp ở phía xử lý và dùng idempotency của nhà cung cấp nếu có.

Nếu nhà cung cấp không có idempotency và lần gọi trước có kết quả chưa xác định, không thể tuyên bố xử lý đúng một lần chỉ bằng một cờ trong cơ sở dữ liệu nội bộ. Cần đối soát hoặc dừng nhánh tự động đó, đồng thời không cấp thêm cơ hội đoán.

Kết quả đến muộn phải được đối chiếu với đúng giao dịch, attempt, challenge và yêu cầu còn hiệu lực. Một kết quả khớp đến sau khi yêu cầu đã hủy không được làm sống lại hồ sơ hoặc tạo quyền khôi phục mới.

### 8.4. Khi kho bộ đếm không khả dụng

Nếu không xác định chắc chắn ngân sách còn lại, hệ thống chưa có cơ sở để chấp nhận phép kiểm tra mới. Giữ tuyến đó ở trạng thái tạm hoãn hoặc chuyển sang phương thức độc lập đã phê duyệt.

Không fallback sang bộ đếm rỗng trên từng node. Không xem việc cache mất dữ liệu là tài khoản chưa từng thử. Nếu dùng TTL, thời gian giữ dữ liệu phải bao phủ cửa sổ đếm, cooldown, các yêu cầu đang xử lý và nhu cầu chống retry tương ứng.

## 9. Hết lượt không đồng nghĩa khóa tài khoản

Kẻ tấn công có thể biết email của nạn nhân và cố tình trả lời sai. Nếu mỗi lần thất bại khóa toàn bộ tài khoản, endpoint khôi phục trở thành công cụ gây từ chối dịch vụ.

OWASP khuyến nghị không khóa tài khoản chỉ vì một cuộc tấn công vào chức năng quên mật khẩu. Với bài toán này, tác động mặc định của việc hết lượt nên giới hạn vào nhánh câu hỏi đang bị lạm dụng, trong khi đăng nhập hợp lệ và các tuyến phục hồi độc lập được xử lý theo chính sách riêng. [OWASP — Forgot Password Cheat Sheet: Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-lockout)

Các biện pháp bổ sung có thể gồm tạm ngừng cấp challenge, giảm tốc theo nguồn, phát hiện hành vi phân tán và chuyển người dùng hợp lệ sang bằng chứng độc lập. Không yêu cầu người dùng chứng minh danh tính bằng chính các câu hỏi đã hết ngân sách.

Nhân viên hỗ trợ không nên chỉ nhấn “reset attempts” sau khi nghe người gọi cung cấp đúng vài dữ kiện cá nhân. Nếu được phép cấp ngoại lệ, cần kiểm tra bằng phương thức đủ mạnh và độc lập, phân quyền thao tác, ghi lý do cùng giới hạn của ngoại lệ. Việc biết câu trả lời không được tự cấp quyền xóa dấu vết những lần đoán trước đó.

Thành công ở bước kiến thức cũng không nên tự động đặt bộ đếm về không. Việc xóa lịch sử hoặc mở lại ngân sách chỉ được thực hiện theo chính sách có điều kiện rõ ràng, không theo một kết quả khớp có thể do kẻ tấn công tạo ra.

## 10. Phản hồi cho người dùng và chống rò rỉ thông tin

Trong giai đoạn chưa chứng minh quyền với tài khoản, các phản hồi cần tránh tiết lộ:

- Tài khoản mục tiêu có tồn tại hoặc đã đăng ký bộ câu hỏi hay không.
- Câu nào đã đúng, câu nào sai hoặc mức độ gần đúng của từng câu.
- Một dữ kiện cá nhân cụ thể có xuất hiện trong dữ liệu tham chiếu không.
- Chính xác bộ đếm và tín hiệu nào đã kích hoạt biện pháp chống lạm dụng.

Có thể thông báo rằng yêu cầu chưa hoàn tất và cung cấp hướng dẫn tiếp theo, nhưng phải kiểm soát cả nội dung, mã phản hồi và khác biệt thời gian có thể dùng để dò tài khoản. Không có một chuỗi thông báo giống nhau nào tự bảo đảm chống được mọi kênh suy luận.

Trong một phiên hạn chế đã được thiết lập bằng cơ sở đủ tin cậy, giao diện có thể hiển thị hướng dẫn về thời gian chờ hoặc số lần nộp còn lại nếu chính sách cho phép. Giá trị hiển thị chỉ có tính hướng dẫn; máy chủ vẫn kiểm tra lại khi nhận yêu cầu và có thể thấy ngân sách đã thay đổi do hoạt động đồng thời.

Một ví dụ thông báo cho phiên đang xử lý:

> Không thể hoàn tất bước này. Hãy làm theo hướng dẫn khôi phục thay thế hoặc thử lại khi dịch vụ cho phép.

Thông báo không nên chứa “bạn đã đúng hai trong ba câu”. Nó cũng không nên hứa rằng đổi trình duyệt sẽ tạo cơ hội mới.

## 11. Nhật ký và chỉ số phục vụ vận hành

Hệ thống cần giải thích được vì sao một lượt được chấp nhận, chặn hoặc giữ ở trạng thái chưa xác định. Bản ghi có thể gồm:

- Tham chiếu nội bộ của tài khoản, yêu cầu, challenge và attempt.
- Phiên bản chính sách, thời điểm giữ chỗ và trạng thái xử lý.
- Phạm vi ngân sách gây từ chối và thời điểm được xem xét lại ở phía máy chủ.
- Giao dịch nhà cung cấp cùng trạng thái đối soát khi có lỗi.
- Danh tính nhân viên, lý do và phạm vi ngoại lệ nếu có.

Không ghi câu trả lời, đáp án tham chiếu hoặc toàn bộ dữ kiện cá nhân vào log thông thường. Kết quả khớp/không khớp chi tiết cũng cần kiểm soát truy cập; nhật ký không được trở thành một kênh tra cứu đáp án.

Các chỉ số hữu ích gồm tỷ lệ hết lượt theo mục tiêu, mức phát hành challenge nhưng không nộp đáp án, lượng retry được gộp đúng, số giao dịch chưa đối soát và tần suất nhân viên đặt lại ngân sách. Việc nhiều IP cùng nhắm vào một tài khoản gợi ý đoán phân tán; một nguồn nhắm vào nhiều tài khoản có thể gợi ý thăm dò diện rộng.

Tỷ lệ hoàn tất cao không đủ để kết luận tuyến an toàn. Cần quan sát cả dấu hiệu chiếm đoạt tài khoản và tác động từ chối dịch vụ. Khi xác định dữ kiện đã bị lộ, giải pháp có thể là ngừng dùng dữ kiện hoặc loại bỏ bước câu hỏi, thay vì chỉ giảm ngưỡng thử.

## 12. Những tình huống cần giải thích được bằng thiết kế

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Hai node đồng thời nhận hai câu trả lời khi chỉ còn một lượt | Chỉ một attempt mới được giữ chỗ; attempt còn lại không chạy so sánh |
| Người dùng gửi lại cùng nội dung và idempotency key sau khi mất mạng | Trả trạng thái attempt cũ; không tạo lượt kiểm tra mới |
| Cùng idempotency key nhưng thay một đáp án | Từ chối xung đột; không kiểm tra nội dung mới miễn phí |
| Đổi IP và mở yêu cầu khôi phục mới | Ngân sách theo mục tiêu vẫn giữ nguyên |
| Nhà cung cấp đã nhận yêu cầu nhưng phản hồi timeout | Lượt vẫn được tính; tra cứu hoặc đối soát giao dịch cũ |
| Bộ đếm dùng chung tạm ngừng hoạt động | Tạm hoãn tuyến câu hỏi; không khởi tạo bộ đếm rỗng cục bộ |
| Hết lượt câu hỏi trên website rồi gọi tổng đài | Tổng đài không cấp thêm lượt cùng loại ngoài ngân sách |
| Một người lạ cố tình làm hết lượt của nạn nhân | Không tự động khóa toàn bộ đăng nhập hoặc hủy yếu tố xác thực |
| Lần thử cuối khớp với dữ liệu tham chiếu | Hoàn tất tín hiệu phụ trợ nếu còn hiệu lực; chưa tự cấp quyền khôi phục |
| Callback khớp đến sau khi hồ sơ đã hủy | Không khôi phục hồ sơ và không tạo token mới |

Các tình huống này giúp xác định ý nghĩa của chính sách trước khi lựa chọn công nghệ. Đặc tính cần đạt là số phép kiểm tra thực sự được cấp không vượt ngân sách mà hệ thống đã cam kết.

## 13. Liên hệ với quyền khôi phục tài khoản

Đối với tài khoản mất mật khẩu, MFA hoặc passkey, kết quả trả lời kiến thức chỉ có thể tham gia hồ sơ trong phạm vi đã xác định. Nó không tự cho phép thay email khôi phục, bỏ MFA, thêm passkey mới hoặc mở session đầy đủ.

Luồng quyết định cuối cùng cần dựa trên bằng chứng khôi phục đủ tin cậy và liên kết với đúng tài khoản. Nếu sau đó cấp quyền thay đổi, quyền đó phải có phạm vi hành động rõ ràng, thời hạn và kiểm soát sử dụng một lần. Quyết định xử lý session và yếu tố xác thực nghi bị mất hoặc xâm phạm thuộc bước hoàn tất khôi phục.

Giới hạn lượt thử tốt có ba đặc điểm: ngân sách tồn tại qua nhiều phiên và kênh; việc giữ chỗ diễn ra trước mọi phép kiểm tra; hết lượt dẫn tới xử lý an toàn mà không khóa oan toàn bộ tài khoản. Nó giảm cơ hội đoán trong một tuyến còn tồn tại, đồng thời giữ rõ nhu cầu chuyển sang phương thức khôi phục phù hợp hơn.
