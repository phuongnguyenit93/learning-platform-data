# Kênh khôi phục tài khoản qua cuộc gọi thoại

Chủ đề **Voice call recovery channel** thuộc chương **SMS Voice Recovery**.

Kênh khôi phục qua cuộc gọi thoại sử dụng một cuộc gọi tới số điện thoại đã đăng ký để chuyển một mã hoặc thực hiện một bước xác nhận trong luồng khôi phục. Nó có thể hữu ích khi người dùng không nhận được SMS nhưng vẫn có thể nhận cuộc gọi. Khả năng nghe máy chỉ là bằng chứng về quyền tiếp cận đường nhận cuộc gọi tại thời điểm đó; nó không tự chứng minh danh tính pháp lý hay quyền sở hữu đầy đủ đối với tài khoản.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, việc dùng cuộc gọi phải được đặt trong mục tiêu khôi phục an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Một thiết kế đầy đủ cần kết hợp đánh giá rủi ro, mã dùng một lần, kiểm soát lạm dụng, bằng chứng danh tính thích hợp và xử lý session sau khôi phục.

## 1. Cuộc gọi đóng vai trò gì trong khôi phục?

Một mô hình thường gặp là máy chủ phát cuộc gọi tự động, đọc OTP và yêu cầu người dùng nhập mã trên trang khôi phục đang mở. Một mô hình khác dùng tổng đài tương tác, hay IVR, để thu nhận thao tác bấm phím. Cả hai đều cần được ràng buộc với một luồng do máy chủ quản lý.

| Tín hiệu nhận được | Có thể suy ra | Không thể tự suy ra |
| --- | --- | --- |
| Nhà cung cấp nhận yêu cầu gọi | Hạ tầng đã tiếp nhận công việc | Người dùng đã nghe máy |
| Cuộc gọi có trạng thái đã trả lời | Một đầu cuối hoặc hệ thống đã trả lời | Đúng chủ tài khoản đang nghe |
| Người nghe bấm một phím | Có thao tác tương tác trên đường gọi | Người nghe có quyền thay MFA hoặc passkey |
| OTP đúng được nhập trong luồng phù hợp | Bên yêu cầu biết mã còn hiệu lực của challenge đó | Kênh không bị chuyển tiếp hoặc mã không bị lừa lấy |
| Giọng nói nghe quen thuộc | Có một tín hiệu cảm nhận hoặc sinh trắc học tùy hệ thống | Danh tính đã được xác minh chắc chắn |

Bài này tập trung vào **cuộc gọi tự động chuyển OTP rồi xác minh trên ứng dụng**. Nếu dùng IVR để nhận mã hoặc xác nhận hành động, cần bổ sung ràng buộc giữa phiên gọi, luồng và hành động; không được chỉ đánh dấu thành công vì có sự kiện bấm phím.

Cuộc gọi thoại cũng không phải cơ chế nhận diện người gọi bằng giọng nói. Giọng nói có thể được ghi lại, phát lại hoặc tổng hợp. Một nhân viên hỗ trợ nghe thấy giọng giống người dùng không nên coi đó là bằng chứng đủ để bỏ qua quy trình khôi phục.

## 2. Vì sao gọi thoại không mặc nhiên mạnh hơn SMS?

SMS và cuộc gọi tới cùng một số thường phụ thuộc vào cùng quan hệ thuê bao hoặc cùng cấu hình định tuyến điện thoại. Nếu số đã bị chiếm quyền hoặc được chuyển tiếp, việc đổi từ SMS sang thoại có thể vẫn đưa bí mật đến cùng kẻ tấn công.

| Rủi ro | Ảnh hưởng tới khôi phục qua thoại | Hướng kiểm soát |
| --- | --- | --- |
| Chiếm quyền SIM hoặc chuyển mạng giữ số trái phép | Cuộc gọi có thể tới người kiểm soát thuê bao mới | Đánh giá tín hiệu thay đổi thuê bao nếu có; yêu cầu bằng chứng độc lập khi rủi ro cao |
| Chuyển tiếp cuộc gọi | Số đã đăng ký vẫn tồn tại nhưng cuộc gọi tới đầu cuối khác | Không coi nhận cuộc gọi là bằng chứng về thiết bị vật lý ban đầu |
| Hộp thư thoại | OTP có thể nằm trong bản ghi hoặc bản chép lời | Hạn chế để lại bí mật; không coi phát hiện người thật là bảo đảm tuyệt đối |
| Số dùng chung hoặc tổng đài doanh nghiệp | Nhiều người có thể nghe hoặc truy cập bản ghi | Đánh giá tính phù hợp của số và quyền truy cập thực tế |
| Số bị thu hồi rồi cấp lại | Chủ thuê bao mới nhận được cuộc gọi cho tài khoản cũ | Quản lý vòng đời số, xác minh lại theo rủi ro và có cách khôi phục khác |
| Tài khoản điện thoại qua Internet bị chiếm | Cuộc gọi có thể được nhận trên nhiều thiết bị | Xem xét cách kiểm soát số, không chỉ loại số |
| Lừa đảo thời gian thực | Người dùng bị dụ đọc hoặc nhập mã vào luồng của kẻ tấn công | Gắn mã với mục đích, hướng dẫn rõ ràng và đánh giá rủi ro luồng |
| Gọi hàng loạt hoặc gọi tới đích đắt tiền | Gây quấy rối, tiêu hao chi phí, ảnh hưởng dịch vụ | Giới hạn phát cuộc gọi, kiểm soát đích và ngân sách nhà cung cấp |

Nhận được cả SMS và cuộc gọi trên cùng một số không tạo ra hai bằng chứng độc lập. Số điện thoại mới thêm vào trong chính quá trình khôi phục cũng không tự trở thành kênh đáng tin chỉ vì người yêu cầu nhận được cuộc gọi tại số đó.

## 3. Điều kiện để một số điện thoại đủ tư cách nhận cuộc gọi

Trước khi tạo cuộc gọi, máy chủ cần xác định số đích từ dữ liệu đã lưu của tài khoản, không lấy trực tiếp một số tùy ý từ request khôi phục.

Một bản ghi kênh có thể chứa:

```text
RecoveryPhone
  channelId
  accountId
  normalizedNumber
  verifiedAt
  changedAt
  version
  status
  recoveryEligible
```

`verifiedAt` thể hiện lần xác minh quyền tiếp cận số trước đây. Nó không bảo đảm số vẫn thuộc cùng một người ở hiện tại. `recoveryEligible` là quyết định chính sách; không nên chỉ là kết quả của việc chuỗi số đúng định dạng.

Các điều kiện thường cần xem xét gồm:

- Kênh đã được xác minh bằng quy trình thích hợp và đang hoạt động.
- Số không đang chờ xác minh, chờ thay đổi hoặc bị đánh dấu không còn tin cậy.
- Việc thay số gần đây không được dùng ngay để bỏ qua bằng chứng đã mất, nếu chính sách yêu cầu thời gian chờ hoặc bằng chứng bổ sung.
- Loại đích và khu vực được hỗ trợ cho sản phẩm; không cho chuyển tới số đặc biệt hoặc đích không được phép.
- Các tín hiệu rủi ro đang có không buộc luồng phải chuyển sang phương án khác.

Chuẩn hóa số về biểu diễn nhất quán giúp tránh đếm ngân sách riêng cho các cách viết khác nhau. Việc phân tích số cần dựa trên ngữ cảnh quốc gia phù hợp và thành phần xử lý số điện thoại đáng tin cậy; chỉ xóa dấu cách hoặc ghép mã quốc gia bằng chuỗi không đủ. Biểu diễn theo E.164 là một dạng chuẩn hóa thường dùng, nhưng số có dạng hợp lệ vẫn có thể không được cấp phát, không thuộc người dùng hoặc không nhận được cuộc gọi.

Nếu sản phẩm hỗ trợ số nhánh hoặc tổng đài, phải có mô hình dữ liệu và đánh giá riêng. Không nối phần mở rộng tùy ý vào số đích và gửi thẳng tới nhà cung cấp.

Trường hợp người dùng đã mất cả số điện thoại cần một đường khôi phục khác: mã dự phòng, yếu tố đã đăng ký độc lập hoặc quy trình hỗ trợ có kiểm soát. Việc yêu cầu họ nhập một số mới rồi gọi tới đó chỉ chứng minh họ tiếp cận được số mới.

## 4. Luồng tương tác được ràng buộc rõ ràng

Một luồng minh họa có thể đi qua các bước sau:

```text
Người dùng mở trang khôi phục
    -> Máy chủ tạo luồng có thời hạn
    -> Đánh giá điều kiện kênh và rủi ro
    -> Người dùng chủ động chọn nhận cuộc gọi
    -> Giữ chỗ ngân sách và tạo challenge
    -> Gửi công việc gọi qua hạ tầng tin cậy
    -> Người nghe nhận OTP
    -> Nhập OTP trên đúng trang khôi phục
    -> Xác minh mã và các điều kiện còn lại
    -> Cấp quyền thực hiện hành động khôi phục cụ thể
```

Luồng cần gắn với tài khoản, mục đích và trình duyệt khởi tạo. Một ID luồng khó đoán hỗ trợ bảo vệ bản ghi, nhưng không thay thế toàn bộ ràng buộc trình duyệt, kiểm soát request và xác minh quyền ở phía máy chủ. Nếu dùng cookie cho trạng thái nhạy cảm, cần bảo vệ cookie và chống giả mạo request phù hợp với thiết kế ứng dụng.

Giao diện có thể hiển thị đích đã che, chẳng hạn “Gọi tới số kết thúc bằng 42”, khi ngữ cảnh đã đủ điều kiện tiết lộ. Không trả toàn bộ số cho bất kỳ ai chỉ cần nhập email của tài khoản. Phản hồi ban đầu cũng không nên làm lộ tài khoản có tồn tại hay có đăng ký kênh thoại hay không.

Nút nhận cuộc gọi cần thể hiện một hành động chủ động. Không tự động thực hiện nhiều cuộc gọi chỉ vì người dùng mở trang, tải lại trang hoặc vì một callback báo thất bại. Khi người dùng nói họ không yêu cầu cuộc gọi hoặc chọn hủy, hệ thống cần dừng phần công việc còn có thể dừng và không phát thêm cuộc gọi ngoài chính sách.

### Nội dung lời thoại

Một lời thoại minh họa:

> Đây là mã khôi phục cho yêu cầu bạn vừa tạo tại ứng dụng An Tâm. Mã gồm sáu chữ số: không, bốn, hai, bảy, một, chín. Chỉ nhập mã tại trang khôi phục chính thức bạn đã mở. Nhân viên hỗ trợ không yêu cầu bạn đọc mã này. Nếu bạn không yêu cầu, hãy bỏ qua cuộc gọi.

Lời thoại cần đọc đủ chữ số, giữ số 0 ở đầu, có nhịp rõ ràng và hỗ trợ ngôn ngữ phù hợp. Việc nghe lại mã trong cùng cuộc gọi có thể được cho phép có giới hạn; nó không cấp lại TTL hoặc ngân sách xác minh.

Không đọc mật khẩu, liên kết mang quyền truy cập, thông tin tài khoản đầy đủ hoặc dữ liệu cá nhân không cần thiết. Không chèn nội dung tự do do người yêu cầu cung cấp vào lời thoại. Điều này giảm nguy cơ biến dịch vụ thành công cụ gọi quấy rối hoặc phát thông điệp giả mạo.

Hướng dẫn chống lừa đảo giúp người dùng nhưng không làm OTP qua thoại trở thành cơ chế chống phishing. Kẻ tấn công vẫn có thể tạo luồng hợp lệ của chính họ rồi dụ nạn nhân chuyển mã theo thời gian thực.

## 5. Hộp thư thoại, chuyển tiếp và thao tác bấm phím

Một cuộc gọi được trả lời có thể đi tới người thật, hộp thư thoại, trợ lý giọng nói, hệ thống tổng đài hoặc thiết bị đang ghi âm. Không nên giả định API trạng thái đã phân biệt chính xác tất cả các trường hợp này.

Có thể yêu cầu người nghe bấm một phím trước khi đọc OTP để giảm việc phát mã ngay vào một số hộp thư thoại. Tuy nhiên:

- Phát hiện máy trả lời có thể sai.
- Tổng đài hoặc hệ thống tự động vẫn có thể tương tác bằng phím.
- Người kiểm soát số sau khi chuyển tiếp hoặc chiếm thuê bao vẫn có thể bấm phím.
- Hệ thống có bản ghi hoặc chép lời vẫn có thể lưu OTP sau bước tương tác.

Vì vậy, thao tác bấm phím là một phần của giao diện hoặc biện pháp giảm lộ thụ động, không phải bằng chứng danh tính độc lập. Với hành động có yêu cầu bảo đảm cao, nếu sản phẩm không chấp nhận được rủi ro kênh thoại thì cần yêu cầu phương án khác thay vì dựa vào một phím xác nhận.

Chính sách về ghi âm và lưu giữ phải tính đến OTP là bí mật có thời hạn. Tránh bật ghi âm cho nội dung xác minh nếu không cần thiết; kiểm soát cả log, bản chép lời, công cụ hỗ trợ và quyền truy cập tại nhà cung cấp. Hết hạn OTP làm giảm giá trị sử dụng lại nhưng không xóa yêu cầu bảo vệ dữ liệu đã lưu.

## 6. Tách trạng thái chuyển cuộc gọi khỏi trạng thái xác minh

Một lỗi nghiêm trọng là gán `accountRecovered = true` khi nhà cung cấp báo cuộc gọi đã hoàn tất. Hoàn tất chuyển nội dung không đồng nghĩa người có quyền đã chứng minh được tài khoản.

Có thể tách dữ liệu thành hai nhóm:

```text
VoiceDeliveryAttempt
  attemptId
  challengeId
  challengeGeneration
  providerAccountRef
  providerCallId
  providerRequestKey
  destinationChannelId
  destinationVersion
  deliveryStatus
  requestedAt
  lastEventAt

RecoveryChallenge
  challengeId
  flowId
  accountId
  purpose
  otpVerifier
  verifierKeyId
  generation
  challengeStatus
  attemptsUsed
  expiresAt
```

Trạng thái chuyển cuộc gọi có thể là `QUEUED`, `REQUESTED`, `RINGING`, `ANSWERED`, `COMPLETED`, `BUSY`, `NO_ANSWER`, `FAILED` hoặc `UNKNOWN`, tùy mô hình nhà cung cấp. Trạng thái challenge có thể là `ACTIVE`, `VERIFIED`, `EXHAUSTED`, `EXPIRED` hoặc `CANCELLED`.

Không có quy tắc tự động `ANSWERED -> VERIFIED` hoặc `COMPLETED -> VERIFIED`. Challenge chỉ được xác minh qua endpoint xác minh có đủ ràng buộc và ngân sách.

Snapshot phiên bản số đích giúp phát hiện số điện thoại bị thay đổi giữa lúc tạo công việc và lúc gọi. Nếu kênh đã đổi hoặc bị thu hồi tư cách khôi phục, công việc cũ cần được hủy theo chính sách. Không tự sửa công việc cũ để gọi sang số mới.

## 7. Tạo công việc gọi và xử lý retry

Gọi tới nhà cung cấp là tác dụng bên ngoài transaction cơ sở dữ liệu. Nếu ghi challenge thành công nhưng tiến trình chết trước khi gọi, công việc có thể bị mất. Nếu gọi xong nhưng mất phản hồi, thử lại thiếu kiểm soát có thể tạo thêm cuộc gọi.

Một cách tổ chức là ghi challenge cùng một công việc trong outbox, sau đó bộ xử lý gửi cuộc gọi. Outbox giúp công việc có thể được thực hiện lại; nó không tự bảo đảm cuộc gọi bên ngoài chỉ diễn ra đúng một lần.

Mã giả sau diễn tả hợp đồng kiến trúc:

```text
requestVoiceRecovery(flowBinding, requestId):
    enforceIngressAbuseLimits()
    flow = resolveBoundFlow(flowBinding)
    phone = loadEligibleRegisteredPhone(flow.accountId)
    decision = evaluateRecoveryRisk(flow, phone)

    if decision does not allow voice:
        return policyAppropriateResponse()

    atomicForAccountAndDestination:
        recheckFlowPhoneVersionAndDecisionValidity()
        if sameRequestAlreadyProcessed(flow.id, requestId):
            return previousBoundReceipt()

        checkFlowAndDestinationCallBudgets()
        checkSharedRecoveryAttemptBudget()
        reserveOneCallIntent()
        createOrReplaceOtpGenerationWithoutResettingAttempts()
        saveEncryptedShortLivedDeliveryMaterial()
        appendVoiceOutboxJobWithStableProviderRequestKey()
        saveBoundRequestReceipt()
        commit()

    return callRequestAcceptedReceipt()
```

OTP cần được sinh bằng nguồn ngẫu nhiên phù hợp cho mật mã. Có thể lưu verifier bằng HMAC với khóa được bảo vệ tách khỏi dữ liệu OTP; mã ngắn không nên chỉ được băm rồi coi là đã chống vét cạn ngoại tuyến khi cơ sở dữ liệu bị lộ.

Để đọc OTP, một thành phần gửi tin cậy vẫn phải tiếp cận được mã trong thời gian cần thiết. Có thể lưu tạm dữ liệu chuyển phát đã mã hóa với thời hạn ngắn, phân quyền giải mã và xóa sau khi không còn cần dùng. Không lưu mã rõ vào outbox, log, URL callback hay thông báo lỗi. Nếu dùng cơ chế sinh mã của nhà cung cấp, phải xác định rõ ai có thẩm quyền xác minh và các giới hạn được thực thi ở đâu.

Trước khi gửi, bộ xử lý cần kiểm tra lại luồng còn hiệu lực, phiên bản challenge còn hiện hành, số đích còn đúng phiên bản và công việc chưa bị hủy. Một cuộc gọi tới quá muộn không được kéo dài hiệu lực của mã hoặc khôi phục một challenge đã kết thúc.

### Khóa idempotency ở hai ranh giới

1. **Ứng dụng tới máy chủ:** cùng `requestId` và cùng nội dung của một thao tác nhận cuộc gọi trả cùng biên nhận, không tạo thêm công việc. Cùng khóa nhưng nội dung khác phải bị từ chối.
2. **Bộ gửi tới nhà cung cấp:** dùng khóa ổn định cho cùng ý định gọi nếu API hỗ trợ, với phạm vi và thời hạn theo hợp đồng của nhà cung cấp.

Khi timeout, không lập tức đổi khóa rồi gọi tiếp. Cần tra cứu hoặc đối soát trạng thái nếu có thể; trong thời gian chưa rõ, giữ trạng thái `UNKNOWN` và ngăn việc tự động tạo chuỗi cuộc gọi mới. Nếu phải phát một cuộc gọi thực sự mới, thao tác đó cần được tính vào hạn mức tương ứng.

Không thể giả định mọi nhà cung cấp có cơ chế idempotency giống nhau. Nếu có khả năng gửi lặp, thiết kế phải chấp nhận và giới hạn tác động của cuộc gọi trùng, đồng thời vẫn giữ OTP dùng một lần và ngân sách xác minh chung.

## 8. Callback là dữ liệu từ một ranh giới tin cậy khác

Callback báo trạng thái cuộc gọi đi vào từ bên ngoài. Dùng HTTPS là cần thiết cho đường truyền nhưng không tự chứng minh request đến từ nhà cung cấp được phép.

Việc xử lý cần dựa trên cơ chế xác thực callback của nhà cung cấp, chẳng hạn kiểm tra chữ ký theo đúng dữ liệu và quy tắc chuẩn hóa mà API yêu cầu. Nếu chữ ký phụ thuộc vào raw body hoặc URL, cần giữ đúng dữ liệu gốc và cấu hình proxy, tên miền tin cậy; không xây URL kiểm tra chữ ký từ header tùy ý của người gửi.

Sau bước xác thực, máy chủ vẫn cần:

- Đối chiếu tài khoản nhà cung cấp, `providerCallId` và công việc gọi đã biết.
- Ràng buộc với đúng tenant, challenge và phiên bản được lưu ở máy chủ.
- Chống sự kiện trùng, replay và dữ liệu sai định dạng theo khả năng giao thức.
- Xử lý callback tới muộn hoặc không đúng thứ tự mà không làm trạng thái bị lùi sai.
- Giới hạn quyền của callback vào việc cập nhật chuyển phát và đối soát.

Ví dụ, callback `RINGING` đến sau `COMPLETED` không nên làm giao diện quay lại trạng thái đang đổ chuông. Cách hợp nhất sự kiện phải theo ngữ nghĩa và định danh sự kiện của nhà cung cấp; khi mâu thuẫn có thể cần truy vấn trạng thái có thẩm quyền. Không áp dụng tùy tiện một thứ tự tuyến tính cho tất cả trạng thái của mọi API.

Endpoint cung cấp nội dung đọc mã hoặc nhận phím từ IVR cũng cần được bảo vệ. Không chỉ bảo vệ callback trạng thái trong khi để nội dung OTP có thể được tải từ một URL công khai chứa mã trên query string.

Dù callback có chữ ký hợp lệ, nó vẫn không được quyền tự đổi mật khẩu, thay MFA hay tạo session đăng nhập. Một sự kiện chuyển phát được xác thực chỉ cho biết nguồn sự kiện là đáng tin trong phạm vi đó.

## 9. Hiệu lực OTP và ngân sách xác minh dùng chung

Một chính sách minh họa cho cuộc gọi có thể gồm:

| Thành phần | Giá trị ví dụ |
| --- | --- |
| OTP | 6 chữ số ngẫu nhiên, giữ được chữ số 0 ở đầu |
| Hiệu lực mã | 3 phút từ lúc phát, không vượt hạn cuối của luồng |
| Hiệu lực luồng | 15 phút, không được kéo dài do cuộc gọi chậm |
| Ngân sách xác minh | 5 phép kiểm tra trong luồng, cộng dồn qua các thế hệ mã |
| Hạn mức khởi tạo cuộc gọi | Tối đa 2 ý định gọi trong 15 phút theo tài khoản và đích |
| Khoảng chờ gọi lại | Ít nhất 90 giây, đồng thời phải còn các hạn mức khác |

Đây là ví dụ để học thiết kế, không phải cấu hình áp dụng cho mọi sản phẩm. Cần chọn giá trị theo rủi ro, trải nghiệm, khả năng hạ tầng và chi phí.

Khi người dùng chủ động yêu cầu cấp lại mã, có thể tạo thế hệ OTP mới và vô hiệu hóa thế hệ cũ trong một cập nhật nhất quán. Việc gửi lại ở tầng hạ tầng cho cùng công việc không nhất thiết là cấp mã mới: nếu dùng lại mã, nó vẫn giữ nguyên TTL và giới hạn cũ. Hai khái niệm cần được tách rõ trong dữ liệu và giao diện.

Mã được kiểm tra phải gắn với đúng tài khoản, luồng, mục đích và thế hệ. Mọi phép so sánh phải tiêu thụ ngân sách phía máy chủ theo cơ chế nguyên tử. Với một mã 6 chữ số phân bố đều, một giá trị được chấp nhận và 5 phỏng đoán khác nhau, xác suất đoán trúng là `5 / 1.000.000 = 0,0005%`. Rủi ro tăng khi tổng số phép thử hoặc số giá trị đồng thời được chấp nhận tăng.

Giới hạn chỉ theo luồng chưa đủ: cần ngân sách cộng dồn theo tài khoản và các phạm vi chống lạm dụng khác. Chuyển từ SMS sang thoại không được mặc nhiên cấp một tập lượt mới để đoán cùng mục tiêu khôi phục.

Yêu cầu đúng mã ở lượt cuối còn được phép có thể thành công. Sau khi hết lượt hoặc hết hạn, không được so sánh trước rồi chấp nhận vì mã tình cờ đúng. Việc xác minh thành công, đổi trạng thái challenge và tạo kết quả ràng buộc phải được phối hợp để hai request đồng thời không tạo hai quyền khôi phục.

## 10. Chống quấy rối và tiêu hao chi phí

Endpoint nhận cuộc gọi có thể bị lạm dụng ngay cả khi kẻ tấn công không bao giờ đoán OTP. Vì thế, ngân sách cuộc gọi và ngân sách kiểm tra mã là hai lớp độc lập.

Các phạm vi cần xem xét gồm tài khoản, số đích đã chuẩn hóa, luồng, nguồn yêu cầu, tenant, khu vực định tuyến và tổng dịch vụ. Một số đích được dùng cho nhiều tài khoản vẫn cần giới hạn tổng hợp phù hợp. Ngược lại, việc chặn cứng theo một IP dùng chung có thể ảnh hưởng nhiều người hợp lệ.

Cơ chế kiểm soát có thể gồm:

- Chỉ gọi tới kênh đã đăng ký đủ điều kiện, không nhận số đích hoặc URL điều khiển cuộc gọi tùy ý.
- Giới hạn tần suất, số cuộc gọi đồng thời và số lần gọi lại.
- Cho phép các tuyến và loại đích phù hợp; tránh khả năng gọi tới đích đặc biệt hoặc có chi phí bất thường ngoài chính sách.
- Đặt ngân sách chi phí, cảnh báo và khả năng tạm dừng phát cuộc gọi khi có bất thường.
- Giới hạn thử lại, kể cả khi tự chuyển nhà cung cấp hoặc đổi tuyến.
- Theo dõi tỷ lệ không trả lời, thời lượng bất thường và nhiều tài khoản cùng nhắm một đích.

Không tự hoàn hạn mức chỉ vì người nghe không bắt máy: cuộc gọi vẫn có thể gây quấy rối hoặc phát sinh tài nguyên. Với lỗi xảy ra chắc chắn trước khi có tác dụng bên ngoài, có thể điều chỉnh giữ chỗ theo chính sách đã định; không hoàn khi trạng thái gọi còn chưa rõ.

Không khóa vĩnh viễn tài khoản hoặc thu hồi session chỉ vì ai đó đã yêu cầu quá nhiều cuộc gọi. Những hành động đó có thể biến một API khôi phục thành công cụ từ chối dịch vụ nhắm vào nạn nhân. Phản ứng cần giới hạn đúng hoạt động đang bị lạm dụng và cung cấp đường xử lý phù hợp cho người dùng hợp lệ.

## 11. Sau khi xác minh mã

OTP đúng chỉ hoàn tất một bằng chứng trong luồng. Tùy hành động và mức rủi ro, máy chủ còn có thể yêu cầu bằng chứng độc lập, thời gian chờ hoặc quy trình hỗ trợ có kiểm soát trước khi cho thay thông tin xác thực.

Quyền khôi phục được cấp sau khi đủ điều kiện cần:

- Gắn với đúng tài khoản và hành động, chẳng hạn đặt lại mật khẩu hoặc thay một yếu tố đã mất.
- Có thời hạn ngắn, được kiểm tra ở phía máy chủ.
- Được tiêu thụ một lần khi thực hiện hành động nhạy cảm.
- Được bảo vệ khỏi log, liên kết bị rò rỉ và sử dụng lại ở luồng khác.

Không biến OTP qua thoại thành session có toàn bộ quyền rồi mới giới hạn ở giao diện. Việc kiểm tra quyền và áp dụng thay đổi phải diễn ra tại endpoint thực hiện hành động.

Sau khi khôi phục thực sự hoàn tất, áp dụng chính sách xử lý session phù hợp: có thể thu hồi phiên hoặc refresh token cũ, vô hiệu hóa challenge và quyền khôi phục còn lại, rồi yêu cầu xác thực lại bằng thông tin mới. Nếu việc thu hồi nằm ở hệ thống khác, cần cơ chế thực thi và đối soát đáng tin cậy.

Thông báo qua các kênh đã đăng ký khác giúp phát hiện thay đổi trái phép. Không chỉ gửi thông báo tới số mới vừa được thêm. Nội dung thông báo cần có hướng dẫn xử lý khi người dùng không thực hiện hành động, đồng thời tránh tạo một liên kết hủy thay đổi thiếu bảo vệ mà bất kỳ ai cũng có thể kích hoạt.

## 12. Khả năng tiếp cận và phương án thay thế

Cuộc gọi có thể giúp người dùng không nhận được SMS hoặc sử dụng thiết bị chỉ nhận thoại. Tuy nhiên, nó có thể không phù hợp với người khiếm thính, người đang ở nơi không thể nghe điện thoại hoặc người không còn tiếp cận được số.

Thiết kế trải nghiệm nên cho biết cuộc gọi đang được yêu cầu, khoảng chờ hợp lý và cách dùng phương án khác. Không khẳng định đã gửi thành công chỉ vì công việc vừa được đưa vào hàng đợi. Khi mã đã hết hạn trước khi người dùng nghe xong, hướng dẫn bắt đầu lại theo hạn mức còn lại thay vì kéo dài mã cũ.

Các phương án khác có thể là yếu tố đã đăng ký độc lập, mã dự phòng hoặc hỗ trợ theo quy trình. Không giải quyết vấn đề khả năng tiếp cận bằng cách vô hiệu hóa toàn bộ kiểm soát danh tính cho một nhóm người dùng. Cần cung cấp một cách chứng minh phù hợp với cùng mục tiêu bảo đảm.

## 13. Ví dụ thiết kế xuyên suốt

Linh mất thiết bị chứa ứng dụng xác thực nhưng vẫn nhận cuộc gọi ở số đã đăng ký từ trước trên một điện thoại khác. Giả sử chính sách của sản phẩm cho phép dùng thoại như một bằng chứng trong khôi phục và các tín hiệu hiện có không yêu cầu chặn kênh.

1. Linh mở trang chính thức, bắt đầu luồng `F1` và chọn nhận cuộc gọi tới số đã che. Máy chủ lấy số đích từ hồ sơ kênh, không từ một trường số mới do client gửi.
2. Máy chủ kiểm tra rủi ro, giữ chỗ hạn mức và tạo challenge `C1`, phiên bản `1`. Challenge và công việc gọi được lưu nhất quán.
3. Bộ gửi kiểm tra lại thời hạn và phiên bản kênh, rồi yêu cầu nhà cung cấp gọi bằng một khóa ổn định. Phản hồi API bị timeout nên công việc được đánh dấu chưa rõ, không lập tức phát thêm cuộc gọi bằng khóa mới.
4. Callback hợp lệ báo `ANSWERED`. Máy chủ cập nhật trạng thái chuyển phát; challenge vẫn `ACTIVE`.
5. Linh nghe mã và nhập vào trình duyệt đã ràng buộc với `F1`. Endpoint xác minh kiểm tra TTL, phiên bản, mục đích và các ngân sách trước khi so sánh.
6. OTP đúng làm challenge thành `VERIFIED`. Luồng tiếp tục kiểm tra các điều kiện bắt buộc cho việc thay MFA, rồi mới cấp quyền có phạm vi và dùng một lần.
7. Sau khi thay yếu tố thành công, hệ thống xử lý session theo chính sách và gửi thông báo tới kênh thích hợp đã đăng ký.

Nếu ở bước 1 số điện thoại vừa thay đổi trong điều kiện đáng ngờ, quyết định có thể là tạm giữ hoặc chuyển sang bằng chứng khác. Nếu Linh cũng mất quyền tiếp cận thuê bao, yêu cầu gọi lại không giải quyết được vấn đề. Nếu hộp thư thoại trả lời ở bước 4, trạng thái `ANSWERED` vẫn không tạo ra quyền khôi phục.

## 14. Những tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Client gửi số đích mới không thuộc kênh đủ điều kiện | Không phát cuộc gọi tới số tùy ý |
| Kênh điện thoại đổi sau khi tạo công việc | Công việc cũ không tự chuyển sang số mới |
| Hai request cùng một thao tác nhận cuộc gọi | Không tạo thêm công việc do xử lý lặp |
| Nhà cung cấp timeout sau khi có thể đã nhận yêu cầu | Không tạo chuỗi gọi lại thiếu giới hạn |
| Callback giả mạo hoặc sai tài khoản nhà cung cấp | Không cập nhật bản ghi cuộc gọi |
| Callback trùng hoặc đến không đúng thứ tự | Không phát sinh tác dụng lặp hoặc trạng thái lùi sai |
| Cuộc gọi đã trả lời, chưa có OTP đúng | Challenge chưa được xác minh |
| Cuộc gọi đến sau khi luồng hết hạn | Không kéo dài luồng hoặc khôi phục mã cũ |
| Gọi lại hoặc chuyển từ SMS sang thoại | Giữ ngân sách xác minh cộng dồn |
| Hết hạn mức phát cuộc gọi | Không vượt giới hạn qua đổi nhà cung cấp |
| Hai request đúng mã cùng lúc | Chỉ có một kết quả xác minh có hiệu lực theo thiết kế |
| Cuộc gọi gây quấy rối tài khoản nạn nhân | Hạn chế kênh gọi mà không tự thu hồi phiên của nạn nhân |
| Nhà cung cấp bật ghi âm hoặc chép lời | Bí mật và quyền truy cập được kiểm soát theo chính sách |
| Người dùng không thể nghe điện thoại | Có đường khôi phục khác đáp ứng yêu cầu bảo đảm |

Kênh thoại cần được đánh giá trên toàn bộ đường đi từ số đã đăng ký, quyết định phát cuộc gọi, hạ tầng chuyển phát và xác minh OTP đến quyền thay thông tin xác thực. Trạng thái cuộc gọi chỉ là một phần của đường đi đó; quyền khôi phục phải xuất phát từ bằng chứng và chính sách được thực thi ở phía máy chủ.
