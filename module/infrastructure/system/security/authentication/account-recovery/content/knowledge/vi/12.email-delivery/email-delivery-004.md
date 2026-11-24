# Recovery email retry policy — Chính sách thử gửi lại email khôi phục tài khoản

## 1. Retry email khôi phục là một quyết định bảo mật

Email khôi phục có thể không được gửi ngay vì mất kết nối, nhà cung cấp quá tải hoặc hệ thống tạm giới hạn lưu lượng. Thử lại giúp người dùng tiếp tục khôi phục khi họ mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Tuy nhiên, retry thiếu kiểm soát có thể tạo hàng loạt thư, gửi liên kết đã hết hạn hoặc làm lộ bí mật qua nhiều đường truyền.

**Recovery email retry policy** quy định khi nào hệ thống được thử gửi lại một thông điệp khôi phục, dùng lại thông điệp nào, chờ bao lâu, có bao nhiêu lần thử và dừng ở điều kiện nào. Chính sách phải bảo vệ cả khả năng giao thư lẫn hiệu lực của giao dịch khôi phục.

Một lỗi gửi email không làm giảm yêu cầu xác minh danh tính. Hệ thống không được tự bỏ MFA, chấp nhận một địa chỉ nhận mới hoặc cấp phiên đăng nhập chỉ vì người dùng chưa nhận được thư. Email giao thành công cũng chỉ là kết quả vận chuyển; quyền khôi phục vẫn cần token hợp lệ và các bước bằng chứng do chính sách yêu cầu.

Sau bài học, người học có thể thiết kế retry hữu hạn, xử lý kết quả gửi chưa rõ, phối hợp hàng đợi với nhà cung cấp và ngăn retry trở thành nguồn spam hoặc quyền khôi phục kéo dài vô hạn.

## 2. Phân biệt retry kỹ thuật, gửi lại và phát token mới

Ba hành động thường bị gộp dưới nhãn gửi lại nhưng có ý nghĩa khác nhau:

| Hành động | Ai kích hoạt? | Thông điệp và token | Chính sách cần áp dụng |
| --- | --- | --- | --- |
| Retry kỹ thuật | Bộ xử lý gửi sau một lỗi phù hợp | Cùng ý định giao thư và cùng token còn hiệu lực | Backoff, số lần thử, deadline và chống gửi trùng |
| Người dùng yêu cầu gửi lại | Người dùng thao tác qua giao diện | Có thể tái sử dụng ý định còn chờ hoặc tạo ý định mới theo thiết kế | Cooldown, quyền trên giao dịch, hạn mức theo tài khoản và nguồn |
| Phát hành token thay thế | Dịch vụ khôi phục quyết định | Token mới cùng quy tắc vô hiệu hóa token cũ | Quyền phát hành, vòng đời giao dịch và chống lạm dụng |

Retry kỹ thuật không nên tự sinh token mới mỗi lần gọi API email. Nếu làm vậy, một lỗi mạng có thể tạo nhiều quyền khôi phục, nhiều thời hạn khác nhau và nhiều email đến sai thứ tự. Token được phát hành bởi dịch vụ khôi phục; bộ gửi chỉ thực hiện đúng ý định giao thư đã được cấp.

Người dùng bấm gửi lại cũng không được đặt bộ đếm lỗi về không, kéo dài giao dịch vô hạn hoặc vượt hạn mức đã dùng. Nếu một ý định đang chờ retry hợp lệ, hệ thống có thể gộp yêu cầu thay vì xếp thêm hàng loạt công việc giống nhau.

Cần tách hai lớp retry trong vận chuyển:

- Ứng dụng thử chuyển thông điệp cho nhà cung cấp hoặc máy chủ thư.
- Nhà cung cấp đã nhận thông điệp tiếp tục thử giao tới máy chủ đích theo chính sách của họ.

Khi lớp sau đã nhận trách nhiệm giao thư, ứng dụng không nên cứ thiếu sự kiện delivered là gửi thêm một bản mới. Hai lớp cùng thử lại không phối hợp sẽ nhân lưu lượng và số bản sao.

## 3. Hiểu đúng mức độ chắc chắn của kết quả gửi

Một vòng gửi có thể đạt các mức quan sát khác nhau:

```text
Ý định giao thư được ghi nhận
    -> bộ gửi bắt đầu gọi nhà cung cấp
    -> nhà cung cấp xác nhận đã tiếp nhận
    -> có sự kiện giao hoặc lỗi giao ở bước sau
    -> người nhận có thể đọc thư
    -> người dùng thực hiện bằng chứng khôi phục hợp lệ
```

Không bước nào ở đầu chuỗi tự chứng minh bước cuối đã xảy ra. Một callback delivered thường mô tả mức giao nhận theo hợp đồng nhà cung cấp; nó không bảo đảm thư nằm trong hộp thư chính, đã được người dùng đọc hoặc chính chủ tài khoản đã bấm liên kết. Sự kiện mở thư hay nhấp liên kết có thể do phần mềm quét tạo ra, nên không dùng làm bằng chứng xác thực.

Một bảng phân loại lỗi minh họa:

| Kết quả quan sát | Ý nghĩa cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Xác nhận chưa tiếp nhận do lỗi tạm thời | Có thể thử lại cùng thông điệp | Retry hữu hạn với backoff và hạn mức |
| Timeout hoặc mất kết nối sau khi có thể đã gửi dữ liệu | Chưa biết nhà cung cấp đã nhận hay chưa | Đối soát hoặc gọi lại bằng cơ chế idempotency được hỗ trợ |
| Nhà cung cấp xác nhận đã tiếp nhận | Đã giao trách nhiệm tới lớp vận chuyển tiếp theo | Không tự gửi lại chỉ vì chưa thấy delivered |
| Lỗi người nhận hoặc chính sách được phân loại là vĩnh viễn | Retry cùng điều kiện không có triển vọng hợp lý | Dừng tự động, áp dụng suppression hoặc xử lý vận hành phù hợp |
| Sai thông tin xác thực API hoặc lỗi cấu hình người gửi | Vấn đề của tích hợp | Dừng vòng lặp gửi, cảnh báo và khắc phục cấu hình |
| Giao dịch đã hủy, hoàn tất hoặc token đã dùng | Thông điệp không còn được phép tiếp tục | Không retry, không phát quyền thay thế tự động |

Việc ánh xạ mã lỗi phải dựa trên hợp đồng của kênh gửi. Mã HTTP của một API, mã trả lời SMTP và sự kiện bounce là ba nguồn thông tin khác nhau; không đưa tất cả vào một quy tắc như mọi lỗi khác thành công đều thử lại. Ngay cả lỗi tạm thời cũng không có nghĩa được retry vô hạn.

Một phản hồi lỗi máy chủ hoặc timeout có thể đến sau khi hệ thống bên kia đã nhận thông điệp. Bộ phân loại cần lưu được kết quả **chưa rõ**, thay vì ép mọi tình huống thành đã gửi hoặc chắc chắn chưa gửi.

## 4. Một ý định giao thư ổn định cho nhiều lần thử

Một mô hình dữ liệu có thể gồm:

```text
recoveryDelivery:
    deliveryId
    recoveryRequestId
    principalId
    recipientChannelId
    recipientBindingVersion
    tokenReference
    tokenGeneration
    templateVersion
    createdAt
    submissionDeadline
    state
    attemptCount
    nextAttemptAt
    providerName
    providerMessageId
    idempotencyKey
    leaseVersion
```

`deliveryId` đại diện cho một ý định giao thư, không phải một lần gọi mạng. `attemptCount` đếm các lần đã bắt đầu thực hiện theo quy tắc rõ ràng, bao gồm lần có kết quả chưa rõ. Mỗi attempt có thể được ghi trong bản ghi con với thời điểm, loại lỗi và mã tương quan, không chứa token hoặc nội dung bí mật.

Người nhận phải lấy từ kênh đủ điều kiện đã gắn với giao dịch. Retry không được âm thầm tra lại email hiện tại rồi gửi cùng token sang địa chỉ khác. Nếu liên kết kênh thay đổi hoặc kênh bị thu hồi, bộ gửi dừng và để dịch vụ khôi phục đánh giá lại. Một địa chỉ mới cần quy trình cấp quyền riêng, không được chấp nhận chỉ vì địa chỉ cũ giao thư thất bại.

Payload cần ổn định giữa các lần thử cùng một ý định: người nhận, mục đích, liên kết, phiên bản mẫu và khóa idempotency phải tuân theo cùng hợp đồng. Thay nội dung nhưng giữ một khóa mà nhà cung cấp coi là cùng yêu cầu có thể gây lỗi hoặc kết quả không như dự kiến.

### Lưu token để gửi và lưu token để xác minh là hai nhu cầu khác nhau

Nếu dịch vụ xác minh chỉ lưu bản băm token, bộ gửi không thể tái tạo token gốc từ bản băm đó. Cần thiết kế trước cách cung cấp lại cùng thông điệp cho retry, chẳng hạn lưu payload được mã hóa trong kho ngắn hạn và chỉ cấp quyền giải mã cho bộ gửi cần thiết.

Nội dung email, payload trong outbox, hàng đợi, kho lỗi và dữ liệu ở nhà cung cấp đều có thể chứa token bearer. Chúng cần phân quyền, mã hóa phù hợp và thời hạn lưu theo mục đích. Không đưa payload đầy đủ vào log để tiện retry, và không tự phát token mới mỗi khi không còn truy cập được payload cũ.

### Ghi nhận ý định cùng giao dịch nghiệp vụ

Có thể ghi yêu cầu khôi phục, token và bản ghi outbox trong một giao dịch lưu trữ rồi mới để bộ gửi xử lý. Cách này tránh tình huống đã tạo token nhưng mất hoàn toàn công việc gửi, hoặc gửi email cho một yêu cầu chưa commit.

Outbox giúp chuyển giao công việc bền vững; nó không bảo đảm email chỉ được gửi đúng một lần. Nếu tiến trình chết sau khi nhà cung cấp đã nhận nhưng trước khi ghi lại kết quả, công việc vẫn có thể được xử lý lần nữa. Cần cơ chế idempotency và đối soát ở ranh giới hệ thống, không chỉ một cờ đã xử lý trong cơ sở dữ liệu nội bộ.

## 5. Backoff, jitter, hạn mức và deadline

Retry cần có cả giới hạn số lần lẫn giới hạn thời gian. Một chính sách minh họa có thể dùng:

```text
maxAttempts = 4                 # gồm cả lần gửi đầu tiên
baseDelay = 5 giây
maxDelay = 60 giây
minimumSpacing = 2 giây
maxSubmissionAge = 2 phút
minimumUsefulWindow = 2 phút
```

Các giá trị trên chỉ dùng để giải thích, không phải tiêu chuẩn bắt buộc cho mọi sản phẩm. Cần chọn theo thời hạn token, độ trễ kênh gửi, lưu lượng và mức rủi ro chấp nhận được.

Sau lần thất bại thứ n thuộc nhóm được phép retry:

```text
ceiling(n) = min(maxDelay, baseDelay * 2^(n - 1))
localDelay = max(minimumSpacing, random(0, ceiling(n)))

nextAttemptAt = max(
    now + localDelay,
    providerResumeAtIfSpecified,
    sharedRateLimitAvailableAt
)
```

Backoff tăng thời gian chờ khi lỗi kéo dài. Jitter phân tán các lần thử để nhiều công việc không cùng dồn trở lại sau sự cố. Thời gian nhà cung cấp yêu cầu chờ, nếu có ý nghĩa theo hợp đồng, là một ràng buộc cần tôn trọng; không thử sớm hơn chỉ vì backoff nội bộ ngắn hơn.

Chỉ xét lịch trên khi trạng thái vẫn cho retry và số lần thử còn ngân sách. Tính toán cần giới hạn số mũ và kiểm tra cấu hình để tránh tràn số hoặc khoảng chờ âm.

Một deadline gửi minh họa:

```text
submissionDeadline = min(
    delivery.createdAt + maxSubmissionAge,
    token.expiresAt - minimumUsefulWindow,
    recoveryRequest.expiresAt
)
```

Không lên lịch nếu thời điểm thử tiếp theo cùng ngân sách timeout của lần gọi đã vượt deadline. Khi công việc thực sự chạy, phải kiểm tra lại thời gian, trạng thái yêu cầu, token, phiên bản và ngân sách; công việc có thể đã nằm trong hàng đợi lâu hơn dự kiến.

Khoảng đệm trước khi token hết hạn chỉ tăng cơ hội người dùng kịp thao tác; nó không bảo đảm độ trễ giao thư ở bên ngoài. Nhà cung cấp có thể vẫn giao một email sau hạn. Endpoint khôi phục phải từ chối token hết hạn, đã dùng hoặc bị thu hồi; retry không được kéo dài thời hạn token để làm cho thư đến muộn trở nên hợp lệ.

## 6. Timeout chưa rõ kết quả và giới hạn của idempotency

Giả sử ứng dụng gửi email, nhà cung cấp đã tiếp nhận nhưng phản hồi bị mất. Nếu ứng dụng coi timeout là chắc chắn chưa gửi và tạo thông điệp mới, người dùng có thể nhận hai thư. Nếu lần thử thứ hai còn phát token mới, họ có thể nhận hai liên kết với hiệu lực khác nhau.

Khi nhà cung cấp hỗ trợ idempotency cho thao tác gửi, cần dùng một khóa ổn định cho cùng ý định giao thư, trong phạm vi tài khoản nhà cung cấp phù hợp. Retry cùng payload và cùng khóa trong thời gian bảo đảm có thể giúp nhà cung cấp nhận ra đây là yêu cầu lặp.

Cần kiểm tra rõ các điều kiện của khả năng này trong tích hợp:

- Khóa có được hỗ trợ cho đúng API gửi đang dùng hay không.
- Thời gian nhà cung cấp ghi nhớ khóa và giới hạn phạm vi của khóa.
- Cách xử lý hai yêu cầu đồng thời hoặc cùng khóa nhưng payload khác nhau.
- Khả năng truy vấn kết quả bằng khóa hoặc mã thông điệp nếu có.
- Những lớp thư viện, proxy hoặc cơ chế failover nào có thể tạo thêm lần gọi.

Một header do ứng dụng tự đặt không tạo tính idempotent nếu nhà cung cấp không xử lý nó. Tương tự, `Message-ID` của email có thể hỗ trợ tương quan nhưng không phải cam kết rằng hệ thống thư sẽ loại mọi bản sao.

Trạng thái chưa rõ có thể được xử lý theo thứ tự phù hợp với khả năng tích hợp:

```text
UNKNOWN_ACCEPTANCE
    -> đối soát bằng định danh tương quan, nếu có cơ chế tin cậy
    -> hoặc thử cùng ý định bằng idempotency còn được bảo đảm
    -> nếu vẫn không rõ: giữ trạng thái chưa xác định và dừng theo ngân sách
```

Không đổi khóa chỉ vì đã timeout. Khi cửa sổ bảo đảm idempotency kết thúc, một lần gửi mới có thể trở thành một bản sao; chính sách phải quyết định rõ có chấp nhận rủi ro đó hay cần xử lý vận hành. Không tuyên bố khả năng giao email đúng một lần trong mọi trường hợp khi ranh giới nhà cung cấp không có bảo đảm tương ứng.

Chuyển sang nhà cung cấp dự phòng cũng không tự giải quyết kết quả chưa rõ. Hai nhà cung cấp độc lập thường không chia sẻ kho chống trùng; cùng `deliveryId` ở hệ thống nội bộ không khiến họ biết lần gửi ở bên kia. Failover cần phân biệt trường hợp chắc chắn chưa được tiếp nhận với trường hợp có thể đã được tiếp nhận, đồng thời giữ ngân sách tổng và kiểm soát rủi ro gửi trùng.

## 7. Bộ xử lý hàng đợi và trạng thái giao thư

Có thể phân loại trạng thái nội bộ như sau:

| Trạng thái minh họa | Ý nghĩa |
| --- | --- |
| `PENDING` | Ý định đã ghi nhận, chưa bắt đầu gửi |
| `SENDING` | Một bộ xử lý đang thực hiện một lần gọi |
| `RETRY_WAIT` | Có lỗi được phép thử lại và đã có lịch tiếp theo |
| `UNKNOWN_ACCEPTANCE` | Chưa xác định nhà cung cấp đã tiếp nhận hay chưa |
| `ACCEPTED` | Có xác nhận tiếp nhận; theo dõi kết quả giao bằng dữ liệu riêng |
| `STOPPED` | Dừng vì hết ngân sách, deadline, thu hồi hoặc lỗi không thể retry |

Kết quả giao sau tiếp nhận như delivered, bounce hoặc complaint nên có thông tin riêng gắn với thông điệp và sự kiện tương ứng. Không coi mọi sự kiện đến sau là một bước tăng trạng thái đơn giản: bounce có thể đến sau accepted, còn sự kiện accepted bị giao trễ không được ghi đè kết quả giao đã biết.

Luồng xử lý minh họa:

```text
processDelivery(deliveryId):
    atomically claim a due delivery and reserve one attempt
    if claim failed:
        return

    load current recovery request, token and channel binding
    if no longer eligible or deadline cannot be met:
        record stop reason under current claim
        return

    submit the stable payload with bounded network timeout
    record the observed result for this attempt

    if acceptance is confirmed:
        mark accepted; do not schedule another application send
    else if acceptance is unknown:
        schedule bounded reconciliation or supported idempotent retry
    else if failure is retryable and budgets still permit:
        persist nextAttemptAt and RETRY_WAIT
    else:
        persist STOPPED with an internal reason
```

Việc giành công việc và giữ chỗ cho một lần thử cần nguyên tử để hai bộ xử lý không cùng vượt hạn mức. Cần kiểm tra quyền sở hữu hoặc phiên bản lease khi ghi kết quả, để một bộ xử lý cũ không ghi đè trạng thái mới. Không giữ một giao dịch cơ sở dữ liệu mở suốt lời gọi mạng dài chỉ để chờ email.

Lease có thể hết hạn khi lời gọi bên ngoài vẫn đang chạy. Phiên bản lease bảo vệ việc ghi nội bộ nhưng không tự ngăn bộ xử lý cũ tiếp tục gửi cho nhà cung cấp. Vì vậy, vẫn cần idempotency ở ranh giới gửi hoặc chính sách xử lý trùng phù hợp; không xem khóa hàng đợi là bảo đảm tuyệt đối về số thư được giao.

Cần chỉ định lớp nào sở hữu retry. Nếu thư viện HTTP tự thử ba lần, bộ xử lý hàng đợi thử bốn lần và một proxy cũng thử lại, lưu lượng thực có thể lớn hơn bộ đếm hiển thị. Tắt các retry không cần thiết hoặc tích hợp chúng vào cùng ngân sách, timeout và mã tương quan. Việc nhận lại cùng một job không được khởi tạo một ngân sách hoàn toàn mới.

Khi đã ghi nhận accepted, việc hàng đợi giao lại job phải trở thành thao tác không tạo thêm lần gửi. Khi đã stopped do token không còn hiệu lực, job cũ không được làm sống lại thông điệp chỉ vì một người vận hành khởi động lại bộ xử lý.

### Thay đổi bảo mật trong lúc đang gọi nhà cung cấp

Yêu cầu có thể bị hủy hoặc token bị dùng ngay sau lần kiểm tra cuối của bộ gửi. Không có một phép kiểm tra trước gửi nào tự thu hồi được email đã rời hệ thống. Cần dừng những công việc còn kiểm soát được, đồng thời bảo đảm endpoint khôi phục kiểm tra hiệu lực phía máy chủ ở thời điểm token được sử dụng.

Một thư đã gửi nhưng không còn cấp quyền là kết quả cần được xử lý rõ trong giao diện. Không được kéo dài token hoặc tạo quyền mới để làm cho mọi thư đã gửi đều sử dụng được.

## 8. Callback, suppression và hàng đợi lỗi

Sự kiện từ nhà cung cấp phải được xác thực theo cơ chế của tích hợp, đối chiếu đúng tài khoản gửi, thông điệp và người nhận nội bộ. Cần chống xử lý lặp bằng định danh sự kiện phù hợp và xử lý việc đến sai thứ tự. Không tin một trường `delivered = true` do nguồn tùy ý gửi vào endpoint công khai.

Callback không được tự đánh dấu giao dịch khôi phục là đã xác minh, đổi mật khẩu, tắt MFA hoặc thu hồi phiên. Nó cung cấp dữ liệu vận hành về giao thư; bằng chứng sử dụng token là một luồng riêng.

Đối với bounce hoặc complaint, hệ thống cần phân loại theo hợp đồng kênh gửi và chính sách suppression. Nếu địa chỉ đang bị chặn vì lý do phù hợp, retry liên tục hoặc đổi nhà cung cấp để né suppression sẽ làm vấn đề nặng hơn. Không tự xóa email khỏi tài khoản hoặc sửa đích nhận thư chỉ dựa vào một callback chưa được xác minh.

Lỗi cấu hình hoặc danh tính người gửi cần được xử lý như sự cố tích hợp. Tạm dừng gửi, sửa cấu hình và đánh giá lại các ý định còn đủ điều kiện sẽ phù hợp hơn việc để từng tài khoản tự thử vô hạn. Sau khi sửa, chỉ những công việc còn đúng trạng thái, thời hạn và ngân sách mới được xem xét tiếp.

Hàng đợi lỗi giúp điều tra những công việc đã dừng. Nó không phải nơi giữ các token còn hoạt động vô thời hạn hoặc nơi cho phép phát lại mọi email bằng một nút bấm. Khi xử lý lại cần:

1. Xác định nguyên nhân và kết quả các lần gửi trước, nhất là trường hợp chưa rõ đã được tiếp nhận.
2. Kiểm tra lại giao dịch, token, kênh, deadline, suppression và hạn mức.
3. Phân biệt tiếp tục cùng ý định còn hợp lệ với việc cần một yêu cầu khôi phục mới có cấp quyền riêng.
4. Ghi lịch sử thao tác; không đặt lại bộ đếm hoặc gia hạn token chỉ để công việc chuyển thành thành công.

Payload bí mật trong hàng đợi lỗi cần thời hạn lưu và bảo vệ tương tự hàng đợi chính. Sau khi không còn cần cho việc gửi, nên loại bỏ phần bí mật theo chính sách lưu giữ, giữ lại dữ liệu vận hành tối thiểu phục vụ đối soát.

## 9. Chống spam, chống dò tài khoản và phản hồi người dùng

Retry của một công việc riêng lẻ vẫn phải nằm trong hạn mức tổng. Cần phối hợp các chiều phù hợp như giao dịch, tài khoản sau khi tra cứu, kênh người nhận, nguồn truy cập, tenant và tài khoản nhà cung cấp. Một tài khoản có nhiều bí danh không được tự có nhiều ngân sách gửi chỉ vì đầu vào thay đổi.

Hạn mức nội bộ giúp gộp các lần thử về cùng chủ thể. Phản hồi công khai không nên để lộ rằng email tồn tại, đang bị suppression, vừa khôi phục thành công hoặc có một loại MFA cụ thể. Có thể phản hồi có điều kiện: “Nếu thông tin khớp với tài khoản đủ điều kiện, hướng dẫn sẽ được gửi qua kênh đã đăng ký.” Nội dung, mã phản hồi và thời gian xử lý cần được xem xét cùng nhau.

Ở ngữ cảnh người dùng đã có quyền quản lý đúng giao dịch, giao diện có thể biểu diễn đang xử lý và thời gian chờ hợp lý trước khi yêu cầu gửi lại. Nút gửi lại không nên tạo nhiều công việc khi người dùng bấm nhanh, tải lại trang hoặc thử lại sau mất mạng. Máy chủ phải thực thi cooldown và gộp yêu cầu, không chỉ vô hiệu hóa nút bằng JavaScript.

Không hứa đã giao thư cho người dùng khi mới ghi nhận outbox hoặc accepted. Cũng không coi chưa thấy delivered là lý do tự gửi thêm liên tục. Hướng dẫn nên giúp người dùng chờ trong khoảng phù hợp, kiểm tra hộp thư và dùng luồng hỗ trợ hoặc phương thức đã đăng ký khác nếu chính sách cho phép.

Không đề nghị chuyển token sang email mới chỉ vì thư chưa tới. Thay kênh khôi phục cần bằng chứng và quyền riêng; retry không được trở thành đường thay email của tài khoản.

## 10. Ví dụ: nhà cung cấp đã nhận nhưng phản hồi bị mất

Lan tạo yêu cầu `r-724` lúc 09:00. Token hết hạn lúc 09:10. Ý định giao thư `d-902` có tối đa bốn lần gọi, tuổi gửi tối đa hai phút và khoảng đệm sử dụng hai phút theo cấu hình minh họa ở trên. Deadline gửi được tính là 09:02, vì giới hạn tuổi gửi sớm hơn các mốc còn lại.

1. Bộ gửi dành một lần thử cho `d-902`, lấy payload ổn định và gọi nhà cung cấp với khóa idempotency `k-902`.
2. Nhà cung cấp tiếp nhận thư, nhưng kết nối bị mất trước khi ứng dụng nhận được phản hồi. Hệ thống ghi kết quả chưa rõ, không phát token khác và không kết luận chắc chắn chưa gửi.
3. Tích hợp hỗ trợ gọi lại bằng cùng khóa trong cửa sổ bảo đảm. Sau khoảng chờ phù hợp, bộ gửi dùng lại cùng payload và `k-902`, trong ngân sách đã quy định.
4. Nhà cung cấp trả lại kết quả của cùng thông điệp `m-381`. Ứng dụng ghi accepted và dừng các lần gửi ở lớp ứng dụng cho ý định này.
5. Callback delivered đến sau được xác thực và đối chiếu với `m-381`. Nó cập nhật dữ liệu vận chuyển, không tự xác minh tài khoản của Lan.
6. Lan dùng liên kết. Máy chủ kiểm tra token còn hạn, chưa dùng, đúng giao dịch và đáp ứng chính sách trước khi cấp quyền khôi phục được phép.

Nếu thay vào đó hệ thống chưa có xác nhận tiếp nhận và chỉ khôi phục kết nối được lúc 09:03, ý định đã vượt deadline gửi. Bộ gửi dừng, không gửi một thư cũ bằng cách gia hạn token. Nếu Lan cần một yêu cầu mới, luồng khởi tạo hoặc gửi lại có kiểm soát sẽ quyết định việc đó.

Nếu nhà cung cấp đã nhận từ trước nhưng giao email sau 09:10, token trong thư vẫn hết hạn. Không có chính sách retry nào bảo đảm tuyệt đối thời điểm thư tới; kiểm tra hiệu lực tại endpoint khôi phục là lớp bảo vệ cuối cùng.

## 11. Quan sát vận hành và các tình huống cần kiểm chứng

Các số liệu hữu ích gồm số ý định giao thư, số attempt trên mỗi ý định, tỷ lệ lỗi tạm thời, tỷ lệ kết quả chưa rõ, thời gian chờ hàng đợi, xác nhận accepted, sự kiện giao lỗi và số công việc dừng theo từng nguyên nhân. Cần phân biệt số lần ứng dụng gọi gửi với số thông điệp được nhà cung cấp tiếp nhận; hai số đó không phải lúc nào cũng bằng nhau.

Nhật ký nên có mã giao dịch, delivery, attempt, nhà cung cấp, mã tương quan và loại lỗi đã được lọc. Không ghi URL chứa token, nội dung thư đầy đủ hoặc thông tin xác minh nhạy cảm. Cảnh báo nên ưu tiên vấn đề có ý nghĩa như tăng timeout chưa rõ, backlog vượt deadline, lỗi xác thực nhà cung cấp hoặc tăng suppression, thay vì phát cảnh báo cho từng thư riêng lẻ.

| Tình huống cần kiểm chứng | Hành vi mong đợi |
| --- | --- |
| Lỗi tạm thời được xác nhận chưa tiếp nhận | Cùng ý định được thử lại với backoff, jitter và ngân sách còn hiệu lực |
| Timeout sau khi nhà cung cấp có thể đã nhận | Giữ trạng thái chưa rõ; đối soát hoặc dùng idempotency được bảo đảm |
| Đã accepted nhưng chưa có delivered | Không tự tạo thêm lần gửi ở lớp ứng dụng chỉ vì thiếu callback |
| Hai bộ xử lý cùng nhận một job | Giữ chỗ attempt nguyên tử; không vượt ngân sách do xử lý trùng |
| Bộ xử lý chết hoặc lease hết hạn sau lời gọi gửi | Kết quả được đối soát; không giả định rằng chưa gửi |
| Retry ngầm ở thư viện và hàng đợi | Số lần gọi thực được tính trong chính sách tổng |
| Job chạy sau deadline hoặc token đã hết hạn | Dừng; không gia hạn token hoặc phát token thay thế tự động |
| Yêu cầu bị hủy, hoàn tất hoặc kênh đã đổi | Không tiếp tục gửi quyền cũ sang trạng thái hoặc địa chỉ mới |
| Lỗi cấu hình hoặc suppression còn hiệu lực | Dừng đúng nguyên nhân; không đổi nhà cung cấp chỉ để né kiểm soát |
| Người dùng bấm gửi lại liên tục | Cooldown, gộp yêu cầu và hạn mức được thực thi phía máy chủ |
| Callback giả, lặp hoặc đến sai thứ tự | Không làm sai trạng thái hoặc cấp quyền khôi phục |
| Xử lý lại công việc từ hàng đợi lỗi | Kiểm tra lại quyền, thời hạn và kết quả gửi trước; không reset ngân sách tùy ý |
| Email đến sau khi token hết hạn hoặc bị dùng | Endpoint khôi phục từ chối token theo trạng thái hiện tại |
| Thiếu khả năng idempotency xuyên nhà cung cấp | Không tuyên bố giao đúng một lần; failover tuân theo chính sách rủi ro gửi trùng |

Một chính sách retry an toàn giúp thông điệp còn giá trị được gửi lại trong phạm vi kiểm soát. Nó giữ nguyên ràng buộc tài khoản, kênh, token và ngân sách, đồng thời phản ánh trung thực những trường hợp chưa xác định được kết quả ở hệ thống bên ngoài.
