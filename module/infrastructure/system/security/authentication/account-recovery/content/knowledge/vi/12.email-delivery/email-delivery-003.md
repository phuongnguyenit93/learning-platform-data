# Thời điểm gửi email khôi phục tài khoản

## 1. Recovery email delivery timing là gì?

Trong chương **Email Delivery**, thời điểm gửi email khôi phục không chỉ là lúc ứng dụng gọi hàm gửi thư. Một email có thể chờ trong hàng đợi nội bộ, được nhà cung cấp tiếp nhận, tiếp tục bị trì hoãn ở hệ thống email đích rồi mới xuất hiện với người dùng.

**Recovery email delivery timing** là việc thiết kế và kiểm soát những khoảng thời gian này để email còn hữu ích khi đến nơi, nhưng không kéo dài quyền khôi phục hoặc tạo thêm cơ hội chiếm đoạt tài khoản.

Bài học tập trung vào ba mối quan hệ:

- Độ trễ gửi thư và thời hạn cố định của token.
- Retry kỹ thuật và yêu cầu gửi lại do người dùng chủ động thực hiện.
- Trạng thái giao nhận email và trạng thái bảo mật của giao dịch khôi phục.

Một email được gửi nhanh không chứng minh người nhận sở hữu tài khoản. Một email bị chậm cũng không phải lý do để bỏ qua MFA, đổi kênh sang địa chỉ chưa xác minh hoặc tự gia hạn token.

Sau bài học, người học cần có khả năng xây dựng lịch gửi và retry có giới hạn, xử lý email đến muộn, thiết kế thông báo phù hợp và đo được các chặng trễ mà hệ thống thực sự quan sát.

## 2. Các mốc thời gian phải phân biệt

Một luồng minh họa có các mốc sau:

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant A as Dịch vụ khôi phục
    participant Q as Hàng đợi và bộ gửi
    participant P as Nhà cung cấp email
    participant M as Hệ thống email đích
    U->>A: Khởi tạo khôi phục
    A->>A: Lưu giao dịch và tác vụ gửi
    A-->>U: Phản hồi tiếp nhận chung
    A->>Q: Tác vụ sẵn sàng xử lý
    Q->>P: Gửi thông điệp còn đủ điều kiện
    P-->>Q: Tiếp nhận thông điệp
    P->>M: Chuyển email
    Note over M,U: Có thể còn trì hoãn, lọc thư hoặc đồng bộ hộp thư
    U->>A: Thực hiện bước khôi phục bằng token
    A->>A: Kiểm tra hạn dùng và tiêu thụ quyền phù hợp
~~~

Các tên dưới đây là quy ước minh họa để trao đổi thiết kế, không phải một chuẩn sự kiện của mọi nhà cung cấp.

| Mốc | Ý nghĩa | Giới hạn của thông tin |
|---|---|---|
| requested_at | Hệ thống nhận yêu cầu khởi tạo | Chưa chứng minh yêu cầu đủ điều kiện |
| committed_at | Giao dịch và ý định gửi đã được lưu bền vững | Chưa chứng minh email đã được gửi |
| token_issued_at | Token được phát hành và có hạn dùng cụ thể | Có thể xảy ra trước hoặc tại lần chuẩn bị gửi đầu tiên |
| dispatch_started_at | Bộ gửi bắt đầu một lần gọi nhà cung cấp | Lần gọi có thể timeout hoặc thất bại |
| provider_accepted_at | Nhà cung cấp xác nhận tiếp nhận thông điệp | Chưa bảo đảm thư có trong hộp thư đến |
| delivery_reported_at | Hệ thống nhận báo cáo giao thư theo nghĩa của nhà cung cấp | Có thể chỉ phản ánh máy chủ email đích đã nhận; không chứng minh người dùng thấy thư |
| redeemed_at | Máy chủ chấp nhận sử dụng bằng chứng theo giao dịch | Là sự kiện bảo mật, khác với mở email hoặc bấm xem trước |

Không mặc định rằng API gửi thành công có nghĩa “người dùng đã nhận thư”. Đồng thời, không coi việc không có webhook giao thư là bằng chứng chắc chắn rằng thư chưa đến.

Những mốc như opened_at thường không đủ tin cậy để điều khiển bảo mật: tính năng bảo vệ riêng tư, bộ quét và trình xem trước có thể tải tài nguyên mà không có hành động đọc thực sự của người dùng.

## 3. Vì sao email chậm là vấn đề bảo mật?

### 3.1. Thư đến sau khi token đã hết hạn

Hương yêu cầu đặt lại mật khẩu lúc 09:00. Hệ thống phát hành token ngay, nhưng hàng đợi bị dồn việc. Email tới muộn, khi người dùng chỉ còn vài chục giây để thực hiện.

Người dùng có thể yêu cầu gửi lại nhiều lần. Nếu mỗi lần đều tạo token mới hoặc vô hiệu hóa thư trước đó mà không có chính sách rõ, hộp thư sẽ chứa nhiều liên kết khó phân biệt. Một cơ chế xử lý độ trễ kém có thể biến thành thư rác hoặc gây từ chối dịch vụ đối với người đang cần khôi phục.

### 3.2. Thư tiếp tục được gửi sau khi trạng thái tài khoản thay đổi

Một tác vụ đang chờ có thể không còn phù hợp nếu:

- Giao dịch đã được hoàn tất hoặc bị hủy.
- Token đã bị thu hồi.
- Kênh email khôi phục đã thay đổi hoặc mất hiệu lực.
- Tài khoản bị áp dụng hạn chế bảo mật mới.
- Phiên bản chính sách hoặc yêu cầu xác minh đã thay đổi.

Không thể chỉ kiểm tra điều kiện lúc nhận yêu cầu rồi cho phép mọi tác vụ trong hàng đợi gửi về sau.

### 3.3. Retry vô tình kéo dài quyền khôi phục

Nếu mỗi lần thử gửi đều đặt lại hạn dùng thành “15 phút kể từ bây giờ”, một sự cố email có thể khiến token sống lâu hơn dự kiến. Người giữ được bản sao token sẽ có cửa sổ tấn công dài hơn.

**Retry là nỗ lực giao lại cùng thông điệp hợp lệ, không phải quyền tự gia hạn hoặc phát hành bằng chứng mới.**

## 4. Thiết kế thời hạn: không để việc giao thư quyết định hiệu lực token

### 4.1. Cố định mốc hết hạn khi phát hành

Một chính sách đơn giản là:

~~~text
expires_at = token_issued_at + token_ttl
~~~

Mốc hết hạn được máy chủ lưu hoặc ràng buộc vào bằng chứng theo thiết kế. Khi kiểm tra token, dùng thời gian đáng tin của hệ thống và trạng thái giao dịch.

Không tính lại hạn dùng từ:

- Thời điểm người dùng mở email.
- Thời điểm có sự kiện click hoặc tải ảnh.
- Ngày gửi hiển thị trong email.
- Một timestamp do trình duyệt gửi lên.
- Thời điểm retry gần nhất.
- Webhook giao thư đến muộn.

Thời hạn 15 phút trong các ví dụ của bài chỉ là giá trị minh họa. Hệ thống phải chọn thời hạn dựa trên mức rủi ro, độ trễ thực tế, thao tác cần làm và các biện pháp bảo vệ liên quan.

### 4.2. Thời gian người dùng còn lại

Ký hiệu:

- I: thời điểm phát hành token.
- E: thời điểm token hết hạn.
- R: thời điểm người dùng thực sự có thể bắt đầu sử dụng liên kết.

Thời gian hữu ích còn lại được mô tả bằng:

~~~text
U = max(0, E - R)
~~~

Ứng dụng thường không biết chính xác R. Sự kiện giao thư hoặc mở thư chỉ cung cấp một số tín hiệu, không phải phép đo chắc chắn rằng người dùng đã sẵn sàng.

Ví dụ, các mốc sau được trình bày cùng một múi giờ:

| Sự kiện | Thời điểm |
|---|---|
| Yêu cầu được nhận | 09:00:00 |
| Token được phát hành | 09:00:01 |
| Token hết hạn sau 15 phút | 09:15:01 |
| Bộ gửi xử lý tác vụ | 09:04:00 |
| Nhà cung cấp tiếp nhận | 09:04:03 |
| Có báo cáo giao thư | 09:07:00 |
| Người dùng bắt đầu sử dụng | 09:14:00 |

Trong ví dụ này, người dùng chỉ còn **1 phút 1 giây**. Việc nhà cung cấp tiếp nhận lúc 09:04:03 không cho phép hệ thống đổi hạn dùng thành 09:19:03.

### 4.3. Hai lựa chọn về thời điểm phát hành

| Phương án | Ưu điểm | Điều cần kiểm soát |
|---|---|---|
| Phát hành cùng lúc lưu giao dịch khôi phục | Hạn dùng gắn sớm với yêu cầu; quan hệ dữ liệu đơn giản | Thời gian chờ hàng đợi tiêu hao thời gian hữu ích |
| Phát hành ở lần chuẩn bị gửi đầu tiên được cho phép | Tránh tiêu hao toàn bộ TTL khi công việc còn chưa được xử lý | Phải có hạn tối đa của yêu cầu; không để một yêu cầu cũ phát hành token mới vô thời hạn |

Với phương án thứ hai, có thể ràng buộc:

~~~text
request_deadline = requested_at + max_request_age

token_expires_at = min(
    first_token_issued_at + token_ttl,
    request_deadline
)
~~~

Token chỉ được phát hành một lần cho tác vụ tương ứng theo chính sách. Retry không thay first_token_issued_at.

Nếu yêu cầu đã quá cũ hoặc chỉ còn khoảng thời gian không đủ theo chính sách, dừng tác vụ. Không phát hành một token mới chỉ để che đi việc hệ thống xử lý chậm.

### 4.4. Ngưỡng thời gian còn lại trước khi gửi

Có thể đặt một ngưỡng tối thiểu để quyết định có nên bắt đầu gửi hay không:

~~~text
được thử gửi =
    giao dịch còn đủ điều kiện
    AND token chưa hết hạn và chưa bị thu hồi
    AND expires_at - now >= min_remaining_to_submit
~~~

Ví dụ, hệ thống chọn ngưỡng 3 phút cho một luồng cụ thể. Một tác vụ chỉ còn 20 giây thì không nên được gửi như thể người dùng vẫn có đủ thời gian.

Ngưỡng này không bảo đảm thư sẽ tới trong 3 phút. Nó chỉ ngăn hệ thống chủ động bắt đầu gửi khi đã biết thời gian còn lại quá ngắn. Độ trễ sau khi nhà cung cấp tiếp nhận vẫn nằm ngoài khả năng kiểm soát hoàn toàn của ứng dụng.

## 5. Lưu tác vụ bền vững và kiểm tra trước khi gửi

### 5.1. Tách phản hồi API khỏi việc giao email

Endpoint khởi tạo không nên chờ toàn bộ quá trình giao email để trả lời. Một thiết kế thường dùng giao dịch dữ liệu cùng transactional outbox hoặc cơ chế tương đương để lưu ý định gửi.

Phản hồi công khai có thể là thông báo chung rằng hướng dẫn sẽ được gửi nếu yêu cầu đủ điều kiện. Không trả “email đã đến” chỉ vì một tác vụ đã được tạo.

Xử lý bất đồng bộ còn giúp giảm sự phụ thuộc của thời gian phản hồi vào việc tài khoản có tồn tại hay không. Tuy nhiên, vẫn phải kiểm tra các chênh lệch có thể quan sát qua status code, nội dung, header và phân bố thời gian; chỉ thêm hàng đợi không tự loại bỏ mọi kênh dò tài khoản.

### 5.2. Gắn tác vụ với đúng giao dịch

Một tác vụ có thể tham chiếu các dữ liệu sau:

~~~text
delivery_id
recovery_request_id
tenant_id
channel_reference
channel_version
created_at
next_attempt_at
attempt_count
request_deadline
token_expires_at
delivery_state
~~~

Dữ liệu nhận và liên kết phải được xác định từ giao dịch cùng hồ sơ máy chủ. Không đọc lại một địa chỉ tùy ý trong payload ban đầu để quyết định nơi gửi.

Nếu tác vụ chỉ lưu tham chiếu kênh, cần kiểm tra phiên bản của kênh trước khi dùng. Việc tự động lấy “email hiện tại” rồi chuyển một token cũ sang địa chỉ vừa thay đổi có thể phá vỡ quan hệ đã được đánh giá ban đầu.

### 5.3. Bí mật trong tác vụ có thời gian sống riêng

Nếu dịch vụ lưu token ở dạng verifier một chiều, bộ gửi không thể khôi phục token gốc từ verifier để gửi lại. Cần giải quyết rõ việc dựng thông điệp ở lần đầu và retry, chẳng hạn giữ nội dung bí mật đã được mã hóa trong outbox có quyền truy cập hạn chế.

Không vì cần retry mà lưu token thô vào log hoặc một hàng đợi ai cũng đọc được. Giới hạn thời gian lưu payload nhạy cảm; dọn theo kết quả gửi, hạn dùng và chính sách lưu giữ.

Khi thông điệp đã được tiếp nhận và không còn cần gửi lại ở lớp ứng dụng, không giữ bản sao bí mật vô thời hạn chỉ để hỗ trợ vận hành. Phần metadata cần cho điều tra có thể có chính sách lưu riêng với payload chứa token.

### 5.4. Kiểm tra lại gần thời điểm phát hành tác dụng phụ

Trước lần gọi nhà cung cấp, kiểm tra lại hạn dùng, trạng thái giao dịch, kênh nhận và các hạn chế bảo mật có liên quan.

Không thể có một giao dịch cơ sở dữ liệu thông thường bao phủ nguyên tử cả máy chủ của mình và một nhà cung cấp email bên ngoài. Một thay đổi có thể xảy ra ngay sau lần kiểm tra cuối hoặc thư đã được tiếp nhận từ trước.

Do đó, việc kiểm tra trước gửi là một lớp giảm rủi ro. Điểm sử dụng token vẫn phải kiểm tra hiệu lực hiện tại và từ chối token đã hết hạn, thu hồi hoặc không còn phù hợp, kể cả khi email vừa tới.

## 6. Retry có ngân sách và có hạn chót

### 6.1. Phân loại kết quả theo việc đã tiếp nhận hay chưa

| Tình huống | Cách xử lý ở lớp ứng dụng |
|---|---|
| Nhà cung cấp xác nhận tiếp nhận | Ghi nhận ACCEPTED; không gửi lại chỉ vì chưa có báo cáo giao thư |
| Từ chối tạm thời trước khi tiếp nhận, có thể retry theo hợp đồng | Lập lịch thử lại nếu còn ngân sách và thời gian |
| Lỗi vĩnh viễn được xác định theo hợp đồng | Dừng retry tự động cho tác vụ đó |
| Timeout hoặc mất kết nối, chưa biết đã tiếp nhận chưa | Ghi trạng thái chưa rõ; đối soát hoặc dùng idempotency nếu được hỗ trợ |
| Nhà cung cấp đã tiếp nhận nhưng báo trì hoãn chuyển thư | Theo dõi tiến trình của nhà cung cấp; không mặc định nộp một thông điệp mới |

Mã phản hồi và loại lỗi phải được diễn giải theo giao thức cùng hợp đồng của nhà cung cấp. Không gộp mọi lỗi thành “chưa gửi, thử lại ngay”.

Một lỗi vĩnh viễn về giao email không cho phép tự chuyển sang một email mới chưa xác minh. Nó cũng không phải lệnh tự xóa tài khoản hoặc bỏ xác thực.

### 6.2. Backoff, jitter và giới hạn số lần

Retry tức thì trên nhiều worker có thể tạo làn sóng gọi lại khi nhà cung cấp đang quá tải. Dùng backoff cùng jitter và giới hạn số lần hoặc tổng ngân sách thời gian.

Một công thức minh họa:

~~~text
base_delay = min(delay_cap, base * 2^retry_index)

candidate_delay = base_delay + random_jitter

next_attempt_at = now + max(
    candidate_delay,
    provider_requested_wait
)
~~~

retry_index bắt đầu từ 0 cho lần retry đầu. provider_requested_wait là khoảng chờ có thẩm quyền được diễn giải từ phản hồi nhà cung cấp nếu có. Không cố tình rút ngắn khoảng chờ được yêu cầu.

Sau khi tính lịch:

~~~text
nếu next_attempt_at + min_remaining_to_submit > expires_at:
    không lập lịch retry đó
~~~

Đồng thời kiểm tra request_deadline và ngân sách số lần gửi. Mọi giá trị như base, delay_cap, số lần thử và ngưỡng còn lại đều là quyết định chính sách; không có một bộ số dùng đúng cho mọi sản phẩm.

### 6.3. Timeout không đồng nghĩa chưa có email nào

Giả sử bộ gửi gọi nhà cung cấp, nhà cung cấp tiếp nhận nhưng phản hồi bị mất. Nếu ứng dụng tạo token mới rồi gửi lại ngay, người dùng có thể nhận hai email khác nhau dù chỉ yêu cầu một lần.

Một delivery_id ổn định có thể được dùng làm khóa idempotency khi nhà cung cấp hỗ trợ đúng phạm vi cần thiết. Mọi lần retry của cùng một lần gửi logic dùng cùng dữ liệu đã ràng buộc, không đổi token hoặc đích nhận để dùng lại cùng khóa.

Nếu nhà cung cấp không có khả năng loại trùng hoặc đối soát tương ứng, không tuyên bố có bảo đảm “gửi đúng một lần”. Thiết kế cần chấp nhận khả năng có thư trùng trong một số sự cố và bảo đảm thư trùng không tạo thêm quyền khôi phục độc lập.

### 6.4. Hàng đợi lỗi không phải kho để phát lại bí mật cũ

Một tác vụ vào dead-letter queue cần có hạn dùng và quy trình xử lý rõ. Khôi phục dịch vụ sau vài giờ không có nghĩa được replay toàn bộ thư khôi phục cũ.

Trước mọi lần phát lại, kiểm tra lại giao dịch, hạn dùng, trạng thái tài khoản và kênh. Payload hết hạn phải được loại bỏ hoặc xử lý theo chính sách bảo vệ dữ liệu; không cấp lại TTL bằng thao tác vận hành.

## 7. Mã giả điều phối lịch gửi

Mã giả sau dùng chính sách phát hành token một lần ở lần chuẩn bị gửi hợp lệ đầu tiên. Các hàm biểu thị trách nhiệm thiết kế, không phải mã triển khai đầy đủ.

~~~text
processDelivery(deliveryId):
    job = claimWithLease(deliveryId)

    if job is absent:
        return

    now = trustedClock.now()

    if now >= job.requestDeadline:
        stopDelivery(job, "REQUEST_TOO_OLD")
        return

    transaction:
        request = loadCurrentRecoveryRequest(job.requestId)
        channel = loadBoundChannel(job.channelReference)

        requireCurrentEligibility(request, channel, job.channelVersion)

        tokenEnvelope = issueOnceOrLoadExistingEnvelope(
            request,
            expiresAtUpperBound = job.requestDeadline
        )

        requireEnoughTimeBeforeSubmission(tokenEnvelope.expiresAt, now)
        reserveAttemptWithinBudgets(job)

    recheckBeforeProviderCall(job, tokenEnvelope)

    result = provider.submit(
        message = decryptForSendingOnly(tokenEnvelope),
        idempotencyKey = job.deliveryId
    )

    if result is confirmedAccepted:
        recordProviderAcceptance(job, result)
        return

    if result is uncertain:
        recordUnknownSubmission(job)
        reconcileWithoutIssuingNewToken(job)
        return

    if result is permanentFailure:
        stopDelivery(job, "PERMANENT_FAILURE")
        return

    retryAt = calculateBackoffAndProviderWait(job, result)

    if retryBudgetAllows(job)
       AND retryAt < job.requestDeadline
       AND retryAt + minimumRemaining <= tokenEnvelope.expiresAt:
        scheduleSameLogicalDelivery(job, retryAt)
    else:
        stopDelivery(job, "RETRY_WINDOW_CLOSED")
~~~

Hàm kiểm tra gần lần gọi phải lấy thời gian hiện tại, không dùng lại một giá trị now đã cũ sau một giao dịch kéo dài. Lease giúp điều phối worker nhưng không tự cung cấp bảo đảm gửi đúng một lần nếu worker chết sau khi nhà cung cấp đã tiếp nhận.

Một lần chuẩn bị gửi mới cũng không được bỏ qua thời gian tối thiểu còn lại của request_deadline. Nếu điều kiện không đạt, dừng thay vì phát hành token có tuổi thọ gần bằng không.

## 8. Gửi lại do người dùng khác với retry kỹ thuật

**Retry kỹ thuật** xử lý lỗi của một lần gửi logic. **Resend** là yêu cầu mới từ người dùng muốn có hướng dẫn khác hoặc nhận lại hướng dẫn. Hai hành vi cần chính sách riêng.

| Thuộc tính | Retry kỹ thuật | Người dùng yêu cầu gửi lại |
|---|---|---|
| Nguồn khởi tạo | Bộ gửi hoặc cơ chế đối soát | Endpoint và giao diện khôi phục |
| Mã gửi logic | Giữ delivery_id của lần gửi | Có thể có lần gửi logic mới theo chính sách |
| Token | Không tự tạo mới | Chỉ phát hành hoặc dùng lại theo chính sách được thiết kế |
| Hạn dùng | Không gia hạn | Không sửa âm thầm hạn token cũ |
| Kiểm soát lạm dụng | Ngân sách retry và tải nhà cung cấp | Cooldown, giới hạn nguồn, đích và tài khoản |
| Phản hồi công khai | Không nhất thiết có phản hồi trực tiếp | Không tiết lộ tài khoản tồn tại hoặc trạng thái nội bộ nhạy cảm |

### 8.1. Cooldown để giảm thư dồn dập

Có thể hiển thị thời gian chờ gửi lại, chẳng hạn 60 giây trong một thiết kế minh họa. Máy chủ phải thực thi giới hạn; chỉ vô hiệu hóa nút trên trình duyệt không ngăn được gọi API trực tiếp.

Nếu giao diện chưa xác minh người yêu cầu, thông tin cooldown không nên vô tình cho biết một tài khoản có thật đã nhận bao nhiêu thư. Phản hồi công khai và quy tắc hiển thị cần được thiết kế nhất quán, còn giới hạn nội bộ theo tài khoản có thể giữ kín.

Áp dụng thêm giới hạn theo nguồn gửi, kênh nhận, tenant và hệ thống. Không để nhiều lần gửi lại liên tục chiếm hết năng lực của hàng đợi.

### 8.2. Không để gửi lại trở thành cách vô hiệu hóa nạn nhân

Nếu bất kỳ yêu cầu ẩn danh nào cũng làm mất hiệu lực mọi liên kết đang chờ, kẻ tấn công có thể liên tục gửi yêu cầu để khiến thư của người dùng hợp lệ không dùng được.

Chính sách có thể giới hạn số giao dịch đang chờ, dùng cooldown hoặc chỉ thay thế giao dịch khi đạt điều kiện cụ thể. Cần cân bằng khả năng thu hồi token với việc tránh cho người chưa xác minh một công cụ gây gián đoạn.

Không tự khóa đăng nhập, thu hồi mọi session hoặc xóa MFA chỉ vì có nhiều yêu cầu gửi email. Những thay đổi bảo mật đó phải gắn với sự kiện và quyền phù hợp.

### 8.3. Thư đến không theo thứ tự

Thư thứ hai có thể đến trước thư thứ nhất. Nếu chính sách thay thế token, thư cũ cần dẫn tới hướng dẫn bắt đầu lại hoặc tiếp tục an toàn; không tự khôi phục hiệu lực vì người dùng vừa bấm vào nó.

Nội dung email nên cho biết thời điểm yêu cầu hoặc hạn dùng theo cách người dùng hiểu được, tránh lời hứa “liên kết còn hiệu lực 15 phút kể từ khi bạn đọc thư”. Không thể dùng thời điểm đọc làm mốc tin cậy.

## 9. Đồng hồ, sự kiện đến muộn và hai loại trạng thái

### 9.1. Dùng thời gian máy chủ có kiểm soát

Lưu các mốc bảo mật bằng biểu diễn thời gian thống nhất, thường là UTC. Đồng bộ đồng hồ giữa các thành phần và theo dõi độ lệch.

Đo khoảng thời gian xử lý trong một tiến trình có thể dùng đồng hồ monotonic phù hợp. Hạn dùng cần so sánh được giữa các máy nên phải có quy tắc thời gian nhất quán.

Nếu chính sách quy định token không hợp lệ khi now >= expires_at, áp dụng cùng ranh giới ở điểm gửi và điểm sử dụng theo vai trò của từng bước. Không lấy timezone hiển thị trên email để thực hiện phép so sánh bảo mật.

### 9.2. Sự kiện giao thư không thay đổi quyền khôi phục

Giữ riêng trạng thái giao nhận và trạng thái token:

~~~text
Giao nhận:
    PENDING, SENDING, SUBMISSION_UNKNOWN, ACCEPTED,
    RETRY_SCHEDULED, STOPPED

Token:
    NOT_ISSUED, ISSUED, USED, REVOKED, EXPIRED
~~~

Đây là tập trạng thái minh họa. Một hệ thống có thể lưu riêng các sự kiện giao thư như delivered, deferred hoặc bounced tùy hợp đồng nhà cung cấp.

Điều cốt lõi là email ACCEPTED không làm token thành USED; sự kiện delivered không làm token hết hạn trở lại ISSUED; bounce không chứng minh chủ tài khoản đã từ bỏ yêu cầu.

### 9.3. Webhook có thể trùng và sai thứ tự đến

Xác thực nguồn webhook theo cơ chế của nhà cung cấp, xử lý trùng theo định danh sự kiện và lưu thời điểm nhận cùng thời điểm sự kiện khai báo.

Không áp dụng mù quy tắc “webhook tới sau luôn là trạng thái mới nhất”. Thứ tự đến không nhất thiết là thứ tự xảy ra, và một số sự kiện phản ánh những giai đoạn hoặc phạm vi khác nhau.

Webhook hỗ trợ quan sát và điều phối giao nhận theo chính sách. Nó không được gia hạn token, đổi tài khoản đích hay khôi phục quyền đã bị thu hồi.

## 10. Quan sát độ trễ và kiểm soát tồn đọng

Một bộ chỉ số hữu ích cần tách những gì hệ thống đo trực tiếp và những gì chỉ được bên ngoài báo cáo.

| Chỉ số | Cách hiểu |
|---|---|
| Tuổi tác vụ lâu nhất còn đủ điều kiện gửi | Phát hiện tồn đọng có thể làm thư mất giá trị |
| Thời gian từ committed_at đến lần thử gửi đầu | Đo độ trễ hàng đợi và điều phối nội bộ |
| Thời gian đến provider_accepted_at | Đo khả năng nộp thư thành công tới nhà cung cấp |
| Tỷ lệ SUBMISSION_UNKNOWN | Phát hiện lỗi kết nối và nhu cầu đối soát |
| Tỷ lệ dừng do hết hạn hoặc không đủ thời gian | Đo ảnh hưởng của độ trễ tới khả năng sử dụng |
| Phân bố báo cáo giao thư | Tín hiệu về chặng sau khi nhà cung cấp tiếp nhận |
| Thời gian còn lại khi token được sử dụng | Quan sát mức thời gian người dùng thực tế còn có ở các lần sử dụng hợp lệ |
| Số lần gửi lại trên mỗi luồng được phép quan sát | Phát hiện trải nghiệm chậm hoặc lạm dụng |

Theo dõi p50, p95 và p99 giúp thấy phần đuôi của phân bố. Đo độ trễ toàn chuỗi riêng; cộng p95 của từng chặng không tự tạo ra p95 chính xác của cả chuỗi.

Một mục tiêu vận hành minh họa có thể là “99% tác vụ đủ điều kiện đã được lưu bền vững được nhà cung cấp tiếp nhận trong 30 giây”. Đây là mục tiêu nộp thư, không phải cam kết người dùng thấy email trong 30 giây.

Mẫu số và thời điểm bắt đầu phải được định nghĩa trước. Không loại các trường hợp timeout chưa đối soát hoặc lỗi gửi khỏi thống kê chỉ để tỷ lệ trông tốt hơn.

Khi hàng đợi tăng:

- Giới hạn lưu lượng khởi tạo và gửi lại trước khi hệ thống quá tải.
- Phân chia tài nguyên để một tenant hoặc nguồn gửi không chiếm mọi worker.
- Chỉ xử lý tác vụ còn giá trị; không ưu tiên gửi bí mật đã hết hạn.
- Kiểm soát tốc độ theo năng lực nhà cung cấp, kể cả khi thêm worker.
- Theo dõi nguyên nhân trì hoãn thay vì tăng TTL tự động cho mọi token.

Không đưa email, token, URL khôi phục hoàn chỉnh hoặc accountId vào nhãn metric. Dùng mã tương quan nội bộ cùng quyền truy cập và thời gian lưu phù hợp để điều tra.

## 11. Trải nghiệm khi thư chậm hoặc không đến

Giao diện có thể thông báo:

> Nếu yêu cầu đủ điều kiện, hướng dẫn sẽ được gửi qua phương thức đã đăng ký. Email có thể đến chậm. Bạn có thể kiểm tra thư rác và yêu cầu gửi lại sau khoảng chờ được hiển thị.

Không khẳng định thư đã đến hộp thư nếu hệ thống chỉ mới ghi outbox. Không hiển thị chi tiết bounce hoặc trạng thái tài khoản cho người chưa được phép biết.

Email nên diễn đạt hạn dùng rõ ràng, có thể kèm thời điểm hết hạn và múi giờ hiển thị. Nếu liên kết đã hết hạn khi người dùng mở, trang đích đưa ra lối bắt đầu yêu cầu mới và vẫn áp dụng giới hạn chống lạm dụng.

Nếu email không sử dụng được vì người dùng mất hộp thư, họ cần phương án khôi phục thay thế đã được thiết kế trước. Sự chậm trễ không cho phép bộ phận hỗ trợ bỏ bước xác minh, gửi token đến một địa chỉ bất kỳ hoặc yêu cầu người dùng chuyển tiếp bí mật qua kênh hỗ trợ.

Bộ quét email có thể mở liên kết trước người dùng. Trang đích không được tiêu thụ token hoặc hoàn tất thao tác chỉ bởi GET; đồng thời không dùng lần mở đó để quyết định rằng người dùng đã nhận thư đúng lúc.

## 12. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
|---|---|
| Hàng đợi chờ lâu hơn TTL token | Không gửi tác vụ đã hết hạn và không tự gia hạn |
| Chọn phát hành token tại lần gửi đầu nhưng yêu cầu đã quá cũ | Dừng theo request_deadline |
| Token chỉ còn ít hơn ngưỡng trước gửi | Không bắt đầu lần gửi đó |
| Nhà cung cấp đã tiếp nhận nhưng phản hồi timeout | Đối soát hoặc dùng idempotency; không tự tạo token mới |
| Nhà cung cấp tiếp nhận nhưng chưa có webhook delivered | Không tự nộp lại thư chỉ vì thiếu webhook |
| Hai worker cùng nhận một tác vụ | Có điều phối và chống trùng phù hợp; không hứa đúng một lần chỉ nhờ lease |
| Retry kế tiếp vượt cửa sổ thời gian | Dừng thay vì lập lịch vô ích |
| Email thay đổi trong lúc tác vụ chờ | Không âm thầm chuyển token cũ sang địa chỉ mới |
| Giao dịch hoàn tất trước khi worker gửi | Dừng tác vụ chưa gửi; token đã dùng vẫn bị từ chối nếu thư cũ tới |
| Email đã được nhà cung cấp nhận rồi token bị thu hồi | Không dựa vào khả năng thu hồi email; điểm sử dụng từ chối token |
| Người dùng bấm gửi lại liên tục | Giới hạn ở máy chủ, không gây thư dồn dập hoặc khóa đăng nhập của nạn nhân |
| Thư cũ đến sau thư mới | Xử lý theo chính sách hiệu lực, không theo thứ tự thư đến |
| Webhook đến trùng hoặc đảo thứ tự | Không cập nhật sai quyền hoặc gia hạn token |
| Bộ quét tải email và mở URL | Không coi là hành vi đọc đáng tin, không tiêu thụ token qua GET |
| Dịch vụ phục hồi sau sự cố kéo dài | Không replay toàn bộ payload khôi phục đã hết hạn |

## 13. Vận dụng vào trường hợp của Hương

Với yêu cầu của Hương, hệ thống lưu giao dịch cùng tác vụ gửi bền vững và phản hồi chung. Thời điểm phát hành cùng hạn dùng được xác định theo một chính sách rõ, có hạn tối đa cho yêu cầu.

Trước mỗi lần nộp thư, bộ gửi kiểm tra điều kiện hiện tại và thời gian còn lại. Lỗi tạm thời chỉ dẫn tới retry có ngân sách cho cùng lần gửi logic. Timeout được xử lý như trạng thái chưa rõ, còn thư đã được tiếp nhận thì không tự bị nộp lại chỉ vì chưa có báo cáo giao thư.

Nếu email đến quá muộn, trang đích từ chối token đã hết hạn và hỗ trợ bắt đầu lại an toàn. Quy trình vẫn giữ nguyên yêu cầu bằng chứng, ràng buộc mục đích và kiểm soát session của thao tác khôi phục; độ trễ giao thư không tạo ra quyền vượt qua các kiểm tra đó.
