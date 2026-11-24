# Ngân sách số lần thử OTP trong khôi phục tài khoản

Chủ đề **One time password attempt budget** thuộc chương **OTP Recovery**.

Khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, mã OTP có thể là một bước trong quá trình khôi phục tài khoản. Vì mã thường ngắn, tính an toàn phụ thuộc vào cả cách sinh mã, thời hạn hiệu lực và số cơ hội mà máy chủ cho phép thử. Một OTP chỉ được dùng một lần vẫn có thể bị đoán nhiều lần trước khi lần sử dụng thành công diễn ra.

Trong phạm vi thiết kế khôi phục tài khoản của `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **attempt budget** là ngân sách số lần máy chủ được phép kiểm tra mã do bên yêu cầu cung cấp, gắn với một phạm vi và khoảng thời gian cụ thể. Ngân sách này phải tồn tại ở phía máy chủ và không được tăng tùy ý khi đổi trình duyệt, gửi lại mã hoặc tạo yêu cầu khôi phục mới.

## 1. Mục tiêu và giới hạn của ngân sách thử

Sau bài này, người học có thể:

- Phân biệt thời hạn OTP, giới hạn tốc độ, ngân sách thử và giới hạn gửi mã.
- Ước lượng rủi ro đoán mã từ độ dài OTP và tổng số phép thử được chấp nhận.
- Thiết kế bộ đếm nhiều lớp, có khả năng chống vượt giới hạn qua yêu cầu đồng thời.
- Xác định việc gửi lại OTP, hết hạn hoặc chuyển kênh xác minh ảnh hưởng thế nào tới các bộ đếm.
- Kết nối kết quả xác minh OTP với quyền khôi phục có giới hạn và chính sách xử lý phiên.

Ngân sách thử chủ yếu chống **đoán mã trực tuyến**. Nó không ngăn được kẻ tấn công đã đọc được mã qua hộp thư bị chiếm, lừa đảo thời gian thực hoặc thiết bị bị kiểm soát. OTP gửi qua SMS hay email cũng không tự động cung cấp mức bảo đảm tương đương một passkey hoặc thiết bị MFA đã mất. Quyết định cho phép khôi phục vẫn cần dựa trên rủi ro và bằng chứng phù hợp với tài khoản.

## 2. Bốn khái niệm dễ bị nhầm

| Cơ chế | Câu hỏi được trả lời | Ví dụ minh họa | Hạn chế nếu dùng riêng |
| --- | --- | --- | --- |
| Thời hạn hiệu lực, hay TTL | Mã còn được chấp nhận đến khi nào? | OTP hết hạn sau 5 phút | Vẫn có thể có nhiều phép đoán trong 5 phút |
| Giới hạn tốc độ xác minh | Có thể gửi bao nhiêu yêu cầu trong một khoảng ngắn? | Giới hạn lưu lượng tại API gateway | Nhiều IP hoặc thời gian chờ dài có thể làm tổng số phép đoán tiếp tục tăng |
| Ngân sách thử | Có tối đa bao nhiêu lần được kiểm tra mã trong phạm vi đã định? | 5 phép kiểm tra cho một challenge | Có thể bị vượt nếu mỗi mã mới lại được cấp ngân sách mới |
| Giới hạn phát/gửi lại mã | Được phát hoặc gửi mã bao nhiêu lần? | Tối đa 3 lần gửi trong 15 phút | Không trực tiếp giới hạn số lần kiểm tra mỗi mã |

**Challenge** là bản ghi phía máy chủ đại diện cho một yêu cầu chứng minh quyền kiểm soát kênh xác minh. **Luồng khôi phục** là tiến trình lớn hơn, có thể bao gồm challenge OTP và các bước đánh giá rủi ro hoặc bằng chứng khác.

Trong bài này, một lượt thử được tính khi máy chủ chấp nhận một mã có hình dạng hợp lệ để so sánh với bí mật OTP đang hoạt động. Cả mã đúng và mã sai đều cần chiếm một lượt trước phép so sánh. Nhờ vậy, mỗi lượt tương ứng với tối đa một cơ hội đoán mã.

Đầu vào sai định dạng, challenge không tồn tại, phiên bản mã đã cũ hoặc yêu cầu đến sau khi hết hạn bị từ chối trước phép so sánh. Chúng vẫn chịu giới hạn lưu lượng và được theo dõi chống lạm dụng. Không cần trừ ngân sách bí mật nếu hệ thống thực sự không kiểm tra mã; cũng không được tạo đường xác minh thay thế để các yêu cầu đó vẫn thử được bí mật.

## 3. Ước lượng xác suất đoán trúng

Giả sử OTP có `d` chữ số thập phân, được sinh đều bằng bộ sinh số ngẫu nhiên phù hợp cho mật mã. Không gian mã có kích thước:

```text
N = 10^d
```

Với một mã cố định, một giá trị được chấp nhận và `g` phỏng đoán khác nhau, xác suất thành công là:

```text
P(thành công) = min(g, N) / N
```

Với OTP 6 chữ số, có một triệu giá trị, bao gồm các mã bắt đầu bằng số 0. Nếu chỉ cho phép 5 phỏng đoán khác nhau:

```text
P = 5 / 1.000.000
  = 0,000005
  = 0,0005%
```

Đây là xác suất cho giả định nêu trên, không phải cam kết an toàn của toàn bộ luồng khôi phục. Nếu 100.000 tài khoản đều bị thử 5 lần trong những điều kiện tương tự, số tài khoản bị đoán trúng kỳ vọng là khoảng `0,5`. Con số kỳ vọng không có nghĩa mỗi đợt tấn công sẽ thành công đúng nửa tài khoản.

Nếu mỗi lần thử nhắm tới một mã mới độc lập, công thức phù hợp cho `g` phép đoán là:

```text
P(thành công) = 1 - (1 - 1/N)^g
```

Khi `g` nhỏ so với `N`, giá trị này gần `g/N`. Vì thế, liên tục phát mã mới nhưng giữ nguyên tổng số phép thử vẫn có rủi ro tích lũy; phát mã mới không xóa lịch sử tấn công.

Nếu một lần kiểm tra chấp nhận tối đa `w` giá trị mã khác nhau, chẳng hạn do cùng chấp nhận nhiều thế hệ mã hoặc nhiều bước thời gian, một cận trên đơn giản là:

```text
P(thành công) <= min(1, g * w / N)
```

Đây là cận trên theo số giá trị có thể được chấp nhận, không phải công thức chính xác cho mọi cách triển khai. Cửa sổ chấp nhận rộng hơn làm tăng số mục tiêu mà một phỏng đoán có thể trúng. Với OTP gửi qua email hoặc SMS trong thiết kế minh họa của bài, chỉ một thế hệ mã hiện hành được chấp nhận.

Để đặt ngân sách ban đầu theo một mức rủi ro mục tiêu `p`, có thể dùng điều kiện bảo thủ:

```text
g * w / N <= p
```

Sau đó phải xét thêm quy mô tài khoản, số cửa sổ trong thời gian dài, mức bảo đảm cần thiết và tác động tới người dùng. Tăng số chữ số hoặc rút ngắn TTL không thay thế được việc kiểm soát tổng số lượt thử.

## 4. Thiết kế ngân sách theo nhiều phạm vi

Một bộ đếm theo challenge chưa đủ: kẻ tấn công có thể tạo challenge mới. Một bộ đếm theo IP cũng chưa đủ: địa chỉ nguồn có thể thay đổi, trong khi nhiều người dùng hợp lệ có thể dùng chung một IP.

| Phạm vi | Mục tiêu | Khóa logic nên dựa trên |
| --- | --- | --- |
| Challenge | Giới hạn phép đoán đối với yêu cầu OTP hiện hành | ID challenge do máy chủ tạo |
| Luồng khôi phục | Ngăn nhận thêm lượt bằng cách đổi challenge trong cùng tiến trình | ID luồng và mục đích khôi phục |
| Tài khoản | Cộng dồn các luồng, kênh và thiết bị cùng nhắm một tài khoản | Định danh tài khoản nội bộ và phạm vi chính sách |
| Nguồn yêu cầu | Hạn chế lưu lượng, bot và phân tán tài nguyên | IP, mạng, tín hiệu thiết bị hoặc phiên rủi ro |
| Toàn dịch vụ | Bảo vệ hệ thống xác minh và hạ tầng gửi mã | Ngân sách tài nguyên và tín hiệu tấn công tổng hợp |

Việc đổi email viết hoa thành viết thường hoặc dùng một bí danh đăng nhập khác không được tạo ra tài khoản đếm lượt mới. Hệ thống cần ánh xạ về cùng định danh tài khoản nội bộ sau khi xử lý định danh theo quy tắc của sản phẩm. Trong hệ thống nhiều tenant, khóa phải chứa ngữ cảnh tenant để tránh va chạm hoặc ảnh hưởng chéo.

Kẻ tấn công cũng không được đổi trường `purpose` từ phía client để tạo thêm ngân sách. Máy chủ xác định mục đích và nhóm ngân sách. Những đường khôi phục có cùng khả năng chiếm tài khoản cần được cộng dồn theo chính sách chung, kể cả khi một đường dùng email và đường khác dùng SMS.

### Một chính sách minh họa

Các con số dưới đây phục vụ việc phân tích, không phải cấu hình mặc định cho mọi sản phẩm:

| Thành phần | Chính sách ví dụ |
| --- | --- |
| OTP | 6 chữ số, sinh ngẫu nhiên đều, giữ được số 0 ở đầu |
| Thời hạn mã | 5 phút, nhưng không được vượt thời hạn còn lại của luồng |
| Thời hạn luồng | 15 phút, gửi lại mã không kéo dài luồng |
| Ngân sách challenge | Tối đa 5 phép kiểm tra mã |
| Ngân sách luồng | Tối đa 5 phép kiểm tra, cộng dồn mọi challenge trong luồng |
| Ngân sách tài khoản | Tối đa 20 phép kiểm tra khôi phục trong cửa sổ trượt 24 giờ |
| Phát/gửi mã | Tối đa 3 lần trong cửa sổ 15 phút theo tài khoản; hai lần cách nhau ít nhất 60 giây |
| Challenge hoạt động | Tối đa một challenge OTP cho cùng tài khoản và mục đích theo chính sách ví dụ |

Giới hạn challenge và luồng cùng bằng 5 là có chủ ý: nếu cách triển khai sau này thay ID challenge, luồng vẫn không có thêm lượt. Giới hạn theo tài khoản tiếp tục có hiệu lực khi một luồng mới được phép bắt đầu.

Với tối đa 20 phép đoán một mã 6 chữ số trong một cửa sổ 24 giờ và chỉ một giá trị được chấp nhận tại mỗi phép thử, cận trên do đoán mã là `20 / 1.000.000 = 0,002%` cho tài khoản trong cửa sổ đó. Nếu mức này vượt ngân sách rủi ro của sản phẩm, phải giảm số phép thử, tăng không gian mã hoặc yêu cầu bằng chứng bổ sung. Rủi ro tiếp tục tích lũy qua nhiều cửa sổ; giới hạn theo ngày không phải giới hạn suốt đời.

## 5. Các bất biến cần giữ

Một triển khai đúng cần giữ được các điều kiện sau ở phía máy chủ:

1. Mỗi phép so sánh OTP với một ứng viên mới phải tiêu thụ ngân sách ở mọi phạm vi bắt buộc.
2. Không phạm vi nào được vượt trần, kể cả khi nhiều máy chủ xử lý đồng thời.
3. Gửi lại hoặc thay mã không khôi phục số lượt của luồng và tài khoản.
4. Một challenge đã xác minh, hết lượt, hết hạn hoặc bị hủy không thể tiếp tục kiểm tra mã.
5. Xác minh thành công chỉ diễn ra một lần; gửi lại cùng yêu cầu không tạo quyền khôi phục mới.
6. Mọi thay đổi nhạy cảm sau OTP vẫn phải kiểm tra quyền khôi phục, mục đích, thời hạn và điều kiện rủi ro.

Trạng thái challenge có thể được mô tả như sau:

```text
ACTIVE --mã đúng, còn ngân sách--> VERIFIED
ACTIVE --mã sai ở lượt cuối-----> EXHAUSTED
ACTIVE --đến hạn----------------> EXPIRED
ACTIVE --luồng bị hủy-----------> CANCELLED
```

Chỉ `ACTIVE` được phép đi tới phép so sánh OTP. Nếu lượt thứ năm là mã đúng thì vẫn chấp nhận, vì hệ thống kiểm tra ngân sách trước khi dành lượt đó. Nếu lượt thứ năm sai, challenge chuyển sang `EXHAUSTED`; một mã đúng gửi ở lượt thứ sáu cũng không được kiểm tra.

Việc thay thế mã trong một challenge vẫn `ACTIVE` tạo thế hệ mã mới nhưng giữ nguyên số lượt đã dùng. Nó không đưa `EXHAUSTED` trở lại `ACTIVE`.

## 6. Dữ liệu cần lưu

Một mô hình tối thiểu có thể gồm:

```text
RecoveryFlow
  flowId
  accountRef
  purpose
  browserBindingRef
  state
  expiresAt
  attemptsUsed

OtpChallenge
  challengeId
  flowId
  generation
  verifier
  verifierKeyId
  state
  expiresAt
  attemptsUsed

AccountRecoveryBudget
  accountRef
  budgetScope
  các sự kiện hoặc bucket dùng để tính cửa sổ ngân sách

VerificationRequest
  flowId
  requestId
  requestFingerprint
  kết quả xử lý đã ràng buộc với luồng
  expiresAt
```

`generation` là số phiên bản của mã được phát. Khi gửi lại mã mới, máy chủ tăng phiên bản và thay verifier trong một thao tác nhất quán. Yêu cầu xác minh cần được ràng buộc với phiên bản thích hợp; yêu cầu thuộc phiên bản cũ bị từ chối mà không so sánh với mã hiện hành.

Không lưu OTP dạng rõ. Với mã ngắn, chỉ băm không có bí mật phía máy chủ không đủ bảo vệ khi cơ sở dữ liệu bị lộ: không gian một triệu giá trị có thể bị vét cạn ngoại tuyến. Có thể lưu verifier bằng HMAC với khóa bí mật được quản lý tách khỏi cơ sở dữ liệu OTP:

```text
verifier = HMAC(
  serverKey,
  encode(accountRef, purpose, flowId, challengeId, generation, otp)
)
```

`encode` phải tạo biểu diễn không mơ hồ, chẳng hạn mã hóa có độ dài từng trường; không nối chuỗi tùy tiện. So sánh verifier bằng primitive phù hợp để tránh rò rỉ qua phép so sánh. Khóa HMAC cần có định danh phiên bản và cơ chế quản lý, luân chuyển phù hợp. Nếu cả khóa lẫn cơ sở dữ liệu đều bị lộ, bảo vệ này không còn ngăn được việc thử mã ngoại tuyến.

Định danh challenge ngẫu nhiên khó đoán hỗ trợ chống dò bản ghi nhưng không thay thế ngân sách theo tài khoản. Client không được tự khai báo `attemptsUsed`, tài khoản thực, thời hạn hoặc mức giới hạn.

Đối với cửa sổ 24 giờ, cần định nghĩa chính xác cách tính: cửa sổ trượt, bucket xấp xỉ hay cửa sổ cố định. Cửa sổ cố định có thể cho phép hai đợt lớn sát ranh giới. Nếu yêu cầu là tối đa 20 lượt trong bất kỳ 24 giờ liên tiếp, phải dùng cách đếm đáp ứng yêu cầu đó; không gắn nhãn cửa sổ trượt cho một bộ đếm reset lúc nửa đêm.

## 7. Xác minh và trừ lượt trong một thao tác nguyên tử

Mẫu đọc bộ đếm, kiểm tra rồi tăng bằng các thao tác độc lập có lỗi cạnh tranh:

```text
Bộ đếm ban đầu: 4/5

Yêu cầu A đọc 4 và thấy còn một lượt.
Yêu cầu B đọc 4 và thấy còn một lượt.
A kiểm tra mã.
B kiểm tra mã.

Kết quả: hai phép đoán được thực hiện khi chỉ còn một lượt.
```

Khóa trong bộ nhớ của một tiến trình không giải quyết được trường hợp có nhiều instance. Cần transaction hoặc cơ chế điều phối nguyên tử trên kho trạng thái dùng chung, đủ mạnh để thực thi toàn bộ các ràng buộc liên quan.

Mã giả dưới đây mô tả hợp đồng xử lý, không phải chương trình chạy độc lập:

```text
verifyOtp(request):
    enforceIngressRateLimit(request.source)
    validateRequestShape(request)
    binding = resolveAndCheckRecoveryBinding(request)

    return atomicForAccount(binding.accountRef):
        now = authoritativeStoreTime()
        flow, challenge = loadAndCheckBoundRecords(binding)
        fingerprint = keyedFingerprintOfRequest(request, binding)

        previous = findRequestResult(flow.id, request.requestId)
        if previous exists:
            if previous.fingerprint != fingerprint:
                return genericRejectedResult()
            return previous.resultBoundToSameFlow()

        if flow is not active or flow.expiresAt <= now:
            return genericRejectedResult()
        if challenge is not ACTIVE or challenge.expiresAt <= now:
            return genericRejectedResult()
        if request.generation != challenge.generation:
            return genericRejectedResult()

        if anyRequiredBudgetIsExhausted(flow, challenge, account, now):
            return genericRejectedResult()

        consumeOneAttemptInAllRequiredBudgets()

        if constantTimeVerifierMatches(request.otp, challenge):
            challenge.state = VERIFIED
            flow.state = OTP_VERIFIED
            result = createOneBoundVerificationReceipt(flow)
        else:
            if challenge.attemptsUsed == challenge.maxAttempts:
                challenge.state = EXHAUSTED
            result = genericRejectedResult()

        saveRequestResult(request.requestId, fingerprint, result)
        commitAllChangesTogether()
        return result
```

Các điểm quyết định nằm ở hợp đồng của `atomicForAccount`:

- Việc kiểm tra và tiêu thụ tất cả ngân sách phải được phối hợp để không có phép so sánh nào vượt trần tài khoản hoặc luồng.
- Trạng thái challenge, số lượt và kết quả chống xử lý lặp phải được commit nhất quán. Mã sai vẫn phải commit lượt đã dùng; không ném ngoại lệ khiến transaction tự động rollback bộ đếm.
- Mọi nơi thay mã, hủy luồng hoặc xác minh cùng tài khoản phải tuân thủ cùng cơ chế đồng bộ.
- Quyền khôi phục thực sự chỉ được phát sau khi bước đánh giá rủi ro và các bằng chứng bắt buộc đã hoàn tất. Biên nhận xác minh OTP trong mã giả chưa phải quyền đăng nhập đầy đủ.

Nếu ngân sách tài khoản ở một kho, challenge ở kho khác và không có cách phối hợp đủ mạnh, không được coi hai lần cập nhật riêng biệt là một giao dịch nguyên tử. Có thể dùng một kho làm nguồn quyết định hoặc cơ chế giữ chỗ lượt có bảo đảm rõ ràng. Việc chọn cơ sở dữ liệu, khóa hay script nguyên tử là chi tiết triển khai; bất biến về tổng phép thử vẫn phải giữ nguyên.

Khi kho ngân sách không khả dụng, trả kết quả tạm thời chưa thể xác minh. Không âm thầm bỏ qua bộ đếm hoặc chuyển sang đếm riêng trong từng instance, vì điều đó tạo thêm lượt ngay lúc hệ thống gặp sự cố.

## 8. Gửi lại HTTP và tính idempotent

Một lần người dùng bấm xác minh có thể tạo ra hai request do mạng chập chờn, trình duyệt gửi lại hoặc proxy retry. Tính idempotent cho phép nhận biết cùng một thao tác để không trừ hai lượt và không phát hai kết quả khôi phục độc lập.

Một thiết kế phù hợp cần:

- `requestId` ngẫu nhiên, được ràng buộc với luồng và trình duyệt đang khôi phục.
- Fingerprint có khóa của toàn bộ nội dung quan trọng: challenge, phiên bản mã, ứng viên OTP và ngữ cảnh ràng buộc.
- Cùng `requestId` và cùng fingerprint trả lại kết quả đã lưu, không so sánh OTP lần nữa.
- Cùng `requestId` nhưng OTP hoặc nội dung khác phải bị từ chối, không được dùng để thử mã mới miễn phí.
- Sau thành công, retry chỉ nhận lại biên nhận phù hợp với cùng luồng; không sinh một quyền khôi phục mới hoặc thực hiện lại thay đổi thông tin xác thực.

Bản ghi idempotency phải được bảo vệ và có thời hạn đủ cho khoảng retry được hỗ trợ. Không ghi OTP hoặc fingerprint có thể dùng để dò OTP vào log thông thường. Nếu cần lưu lại dữ liệu nhạy cảm của kết quả để gửi lại cho đúng trình duyệt, phải bảo vệ dữ liệu đó như một bí mật có thời hạn.

Giới hạn lưu lượng ở đầu vào vẫn áp dụng với request lặp. Nếu chỉ miễn mọi giới hạn vì có `requestId`, kẻ tấn công có thể dùng tính năng retry để gây quá tải.

Nếu không biết một lượt đã được tiêu thụ hay chưa do timeout, không tự động hoàn lượt. Cần đọc lại trạng thái có thẩm quyền hoặc tra kết quả idempotency. Chính sách hoàn lượt tùy tiện có thể biến việc cố ý làm đứt kết nối thành cách lấy thêm phép đoán.

## 9. Gửi lại mã, hết hạn và bắt đầu lại

| Hành động | Cách xử lý trong chính sách minh họa |
| --- | --- |
| Tải lại trang hoặc đổi tab | Dùng trạng thái máy chủ; không reset bộ đếm |
| Gửi lại mã khi challenge còn hoạt động | Thay mã, tăng `generation`, giữ số lượt; kiểm tra hạn mức gửi |
| Thay mã gần cuối luồng | TTL mã mới không vượt `flow.expiresAt` |
| Mã hết hạn | Ngừng kiểm tra mã; lịch sử ngân sách luồng và tài khoản vẫn còn theo thời hạn của chúng |
| Challenge hết lượt | Không cho nút gửi lại mã làm challenge hoạt động trở lại |
| Tạo luồng mới | Phải qua điều kiện phát luồng; ngân sách tài khoản và hạn mức gửi vẫn được cộng dồn |
| Chuyển từ SMS sang email | Kiểm tra điều kiện kênh; không cấp một ngân sách tài khoản độc lập để đoán tiếp |
| Đổi IP hoặc thiết bị | Đánh giá lại rủi ro; giữ ngân sách của tài khoản |
| Xóa bản ghi challenge cũ | Không được kéo theo việc xóa lịch sử ngân sách tài khoản còn hiệu lực |

Chính sách một challenge hoạt động cũng tạo ra một vấn đề cần cân nhắc: người lạ liên tục yêu cầu mã mới có thể làm mã người dùng đang cầm bị thay thế. Việc phát, thay thế và hủy challenge cần được ràng buộc với luồng, có giới hạn và chống spam. Một yêu cầu chưa được tin cậy không nên tùy ý chiếm quyền điều khiển luồng của người dùng khác.

Hết ngân sách không nên tự động khóa vĩnh viễn tài khoản hoặc chấm dứt mọi phiên đăng nhập hiện có. Kẻ tấn công chỉ cần biết định danh tài khoản là có thể gây từ chối dịch vụ nếu các hành động đó được kích hoạt chỉ bằng nhập sai OTP. Phản ứng có thể là tạm dừng đường khôi phục, chờ cửa sổ thích hợp hoặc chuyển sang bằng chứng mạnh hơn theo chính sách.

Một bước chống bot có thể giúp giảm tự động hóa nhưng không tự biến thành bằng chứng sở hữu tài khoản và không nên mặc nhiên xóa ngân sách đã dùng.

## 10. Từ OTP đúng đến quyền khôi phục và phiên

Xác minh OTP thành công chỉ chứng minh rằng bên yêu cầu cung cấp được mã đang hợp lệ trong ngữ cảnh đã ràng buộc. Máy chủ cần kiểm tra các điều kiện còn lại trước khi cho đổi mật khẩu, thay MFA hoặc đăng ký passkey mới.

Khi đủ điều kiện, quyền khôi phục cần có phạm vi rõ ràng:

- Gắn với đúng tài khoản, luồng và hành động được phép.
- Có thời hạn ngắn và được kiểm tra ở phía máy chủ.
- Chỉ được tiêu thụ một lần khi thực hiện hành động nhạy cảm.
- Không được dùng như session đăng nhập có toàn bộ quyền chỉ vì OTP đã đúng.

Việc kiểm tra quyền, tiêu thụ quyền và áp dụng thay đổi thông tin xác thực cần được phối hợp để tránh thực hiện hai lần hoặc sử dụng lại quyền sau thay đổi. Với việc thu hồi phiên ở dịch vụ khác, cần cơ chế thực thi và đối soát đáng tin cậy thay vì giả định một transaction cục bộ có thể tự bao phủ mọi hệ thống.

Sau khi thực sự khôi phục thành công, áp dụng chính sách session phù hợp với mức rủi ro: chẳng hạn thu hồi phiên hoặc refresh token cũ, vô hiệu hóa các quyền khôi phục khác còn tồn tại và thông báo qua các kênh đã đăng ký. Không thực hiện các thay đổi này chỉ vì một request OTP thất bại.

Nếu người dùng mất thiết bị MFA hoặc passkey, cần đặc biệt xem xét liệu kênh OTP hiện tại có đủ bằng chứng để thay yếu tố mạnh hơn hay không. Ngân sách thử nhỏ không bù được một quy trình xác minh danh tính yếu.

## 11. Phản hồi và quan sát vận hành

Phản hồi công khai không nên tiết lộ tài khoản có tồn tại hay không, kênh bí mật đang dùng hoặc lý do nội bộ chi tiết như đã hết ngân sách tài khoản. Có thể dùng thông báo chung phù hợp ngữ cảnh: “Chưa thể xác minh mã. Vui lòng kiểm tra lại hoặc thử theo hướng dẫn khôi phục.”

Đối với trình duyệt đã được ràng buộc đúng luồng, giao diện có thể cung cấp hướng dẫn cần thiết như thời điểm có thể yêu cầu gửi lại. Máy chủ vẫn là nơi quyết định; bộ đếm hiển thị hoặc nút bị vô hiệu hóa ở frontend không phải kiểm soát an ninh.

Không thể khắc phục dò tài khoản chỉ bằng cách dùng cùng một chuỗi thông báo. Cũng cần xem xét khác biệt thời gian xử lý, mã lỗi, cấu trúc phản hồi và hành vi giới hạn. Đầu vào nhắm tài khoản không tồn tại cần có xử lý chống lạm dụng nhưng không được tạo vô hạn trạng thái giả làm cạn tài nguyên.

Các tín hiệu vận hành hữu ích gồm:

- Số phép kiểm tra và số lần bị từ chối theo nguyên nhân nội bộ: sai mã, hết hạn, hết lượt, sai ràng buộc, phiên bản cũ.
- Số yêu cầu phát/gửi lại mã bị chặn và tình trạng hạ tầng gửi mã.
- Số tài khoản bị nhắm từ nhiều nguồn và số nguồn nhắm nhiều tài khoản.
- Tỷ lệ người dùng hợp lệ bỏ dở sau khi hết lượt hoặc gặp sự cố gửi mã.
- Lỗi kho ngân sách, xung đột cập nhật và retry sau timeout.

Dùng nhãn metric có số lượng giá trị hữu hạn; không đặt email, số điện thoại hoặc ID tài khoản vào nhãn metric. Khi cần điều tra theo tài khoản, dùng sự kiện được phân quyền với định danh phù hợp và chính sách lưu giữ. Không ghi OTP, quyền khôi phục hoặc bí mật phiên vào log.

## 12. Ví dụ xuyên suốt

Lan mất thiết bị có passkey và bắt đầu khôi phục qua một kênh email đã đăng ký. Giả sử chính sách rủi ro của sản phẩm cho phép dùng kênh này như một bước trong luồng, với các hạn mức minh họa ở trên.

1. Máy chủ tạo luồng `F1` và challenge `C1`, phiên bản mã `1`. Bộ đếm challenge, luồng và tài khoản đều đang bằng `0`.
2. Có ba request khác nhau cung cấp mã sai đúng định dạng. Mỗi request được xử lý nguyên tử; cả ba phạm vi đều đã dùng `3` lượt.
3. Lan yêu cầu gửi lại mã khi còn đủ điều kiện gửi. Máy chủ thay mã của `C1`, tăng phiên bản lên `2`, giữ các bộ đếm bằng `3`.
4. Một request cũ thuộc phiên bản `1` tới muộn. Máy chủ từ chối trước phép so sánh; request vẫn chịu kiểm soát lưu lượng.
5. Hai ứng viên sai mới thuộc phiên bản `2` được kiểm tra. Bộ đếm lên `5`; challenge chuyển thành `EXHAUSTED`, luồng cũng không còn ngân sách kiểm tra.
6. Một request tiếp theo cung cấp mã đúng bị từ chối vì không còn lượt. Hệ thống không so sánh trước rồi mới quyết định có áp dụng giới hạn hay không.
7. Nếu chính sách cho phép mở luồng khác sau các điều kiện chờ và chống lạm dụng, luồng mới vẫn nhìn thấy tài khoản đã dùng `5` lượt trong cửa sổ 24 giờ. Việc mở luồng không đưa bộ đếm tài khoản về `0`.

Nếu thay bước 5 bằng một request đúng ở lượt thứ năm, máy chủ có thể xác minh OTP, đóng khả năng thử lại challenge và trả biên nhận ràng buộc với `F1`. Luồng chỉ cấp quyền thay thông tin xác thực sau khi đủ mọi điều kiện còn lại.

## 13. Những tình huống cần kiểm chứng khi triển khai

Các tình huống sau là tiêu chí thiết kế và nghiệm thu cho hệ thống thực tế:

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Còn một lượt, hai request khác nhau tới đồng thời | Tối đa một request được so sánh OTP |
| Mã đúng ở lượt cuối cùng còn được phép | Thành công đúng một lần |
| Mã đúng sau khi hết lượt | Không được so sánh hoặc xác minh thành công |
| Retry cùng `requestId` và cùng nội dung | Cùng kết quả, không thêm phép thử hoặc quyền mới |
| Cùng `requestId` nhưng thay OTP | Bị từ chối; không có phép đoán miễn phí |
| Gửi lại mã khi đã dùng ba lượt | Mã thay đổi, ba lượt đã dùng vẫn giữ nguyên |
| Yêu cầu phiên bản cũ tới sau khi thay mã | Không được thử bí mật của phiên bản mới |
| Nhiều luồng hoặc nhiều kênh nhắm cùng tài khoản | Cộng dồn đúng ngân sách tài khoản |
| Khởi động lại instance hoặc chuyển máy chủ | Giữ được trạng thái và tổng ngân sách |
| Kho trạng thái lỗi hoặc timeout | Không bỏ qua giới hạn, không hoàn lượt tùy tiện |
| Nhập sai OTP nhiều lần | Không tự thu hồi phiên đăng nhập của nạn nhân |
| Luồng đã hết hạn nhưng vừa yêu cầu gửi mã | Không kéo dài luồng ngoài chính sách |

Một ngân sách thử có ý nghĩa khi nó giới hạn được **tổng số cơ hội đoán mã mà hệ thống thực sự thực hiện**. Vì vậy, thiết kế cần nối liền bộ đếm, vòng đời challenge, trạng thái luồng và quyền khôi phục; chỉ đặt một số đếm cạnh ô nhập OTP chưa đủ.
