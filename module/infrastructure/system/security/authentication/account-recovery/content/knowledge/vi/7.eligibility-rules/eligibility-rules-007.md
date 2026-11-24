# Recovery cooldown eligibility: điều kiện khôi phục khi có thời gian chờ

Một người nhập đúng mã recovery nhưng hệ thống vẫn chưa cho phép thay MFA vì kênh liên hệ vừa được đổi. Một người khác đã chờ đủ thời gian nhưng mã xác minh lại hết hạn. Hai trường hợp này cho thấy **đủ thời gian chờ** và **đủ quyền khôi phục** là hai điều kiện khác nhau.

**Recovery cooldown eligibility** là việc xác định một thao tác khôi phục đã đáp ứng các điều kiện về thời gian chờ áp dụng cho nó hay chưa. Kết quả phải được đánh giá cùng bằng chứng xác minh, trạng thái tài khoản, mức rủi ro và phạm vi quyền được cấp.

Bài học thuộc chủ đề **Eligibility Rules**, trong phạm vi khôi phục an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là thiết kế cooldown có tác dụng giảm rủi ro mà không biến việc đợi đủ thời gian thành bằng chứng sở hữu tài khoản.

## 1. Cooldown giải quyết vấn đề gì?

Trong luồng recovery, cooldown là một khoảng thời gian mà một thao tác cụ thể chưa được thực hiện, dù một số bước khác có thể đã hoàn tất.

Ví dụ, sản phẩm có thể yêu cầu:

- Kênh recovery mới gắn chưa được dùng ngay để thay toàn bộ phương tiện xác thực.
- Một thay đổi nhạy cảm phải chờ sau khi yêu cầu đã đạt các điều kiện xác minh ban đầu.
- Một tài khoản vừa hoàn tất recovery chưa được thực hiện một số thao tác có tác động lớn.
- Một đường khôi phục không được sử dụng lại ngay sau một lần thay đổi hợp lệ trước đó.

Khoảng chờ có thể tạo cơ hội phát hiện thay đổi trái phép, nhận cảnh báo hoặc giảm khả năng thực hiện một chuỗi chiếm đoạt liên tiếp. Nhưng nó không tự xác định người yêu cầu là ai.

### 1.1. Hết thời gian chờ không nâng chất lượng bằng chứng

Nếu đối thủ kiểm soát email của nạn nhân, chờ thêm một khoảng thời gian không làm email đó trở lại đáng tin. Nếu người dùng không có căn cứ đủ để thay MFA, đồng hồ về không cũng không tự tạo ra căn cứ đó.

Cần giữ nguyên tắc:

> Cooldown là điều kiện bổ sung cho quyết định cấp quyền hoặc thực hiện thao tác, không phải phương án thay thế bằng chứng.

Không nhận được phản đối trong thời gian chờ cũng không có nghĩa chủ tài khoản đồng ý. Người dùng có thể chưa đọc cảnh báo, mất thiết bị hoặc không còn truy cập kênh nhận thông báo.

## 2. Phân biệt các cơ chế có yếu tố thời gian

Những cơ chế dưới đây có thể cùng tồn tại nhưng không nên dùng chung một field mơ hồ như `lockedUntil`.

| Cơ chế | Câu hỏi nó trả lời | Khi hết thời gian |
| --- | --- | --- |
| Recovery cooldown | Thao tác này đã được phép xét tiếp về mặt thời gian chưa? | Đánh giá lại các điều kiện còn lại |
| Rate limit hoặc backoff | Có được gửi hoặc thử thêm trong cửa sổ này không? | Có thể thử theo ngân sách còn lại; chưa có quyền recovery |
| Hạn token hoặc OTP | Bí mật này còn được chấp nhận không? | Không tiếp tục dùng bí mật đã hết hạn |
| Hạn giao dịch | Giao dịch còn được tiếp tục không? | Kết thúc hoặc bắt đầu lại theo chính sách |
| Độ mới bằng chứng | Lần kiểm tra trước còn đủ mới cho thao tác này không? | Có thể phải xác minh lại |
| Hạn chế sau recovery | Quyền nào còn bị giữ lại sau khi đã khôi phục phương tiện? | Chỉ gỡ hạn chế theo các điều kiện đã thiết kế |
| Giữ xử lý sự cố | Có quyết định bảo vệ đặc biệt đang có hiệu lực không? | Không nhất thiết tự gỡ chỉ vì một cooldown khác đã hết |

Chẳng hạn, giới hạn “gửi lại mã sau một phút” chủ yếu điều khiển tần suất gửi. Nó không có cùng ý nghĩa với việc “kênh mới chưa được dùng cho thay MFA”.

Một thông điệp “hãy thử lại sau” cần tương ứng đúng cơ chế đang chặn. Nếu thực chất thiếu bằng chứng, chỉ yêu cầu người dùng chờ sẽ tạo kỳ vọng sai.

## 3. Chỉ rõ thao tác và thời điểm áp dụng điều kiện chờ

Cooldown cần được gắn với một quyết định cụ thể. Không nên đặt một hạn chung khiến mọi chức năng của tài khoản đều bị chặn.

| Vị trí kiểm tra | Ví dụ mục tiêu | Những gì vẫn cần xác định |
| --- | --- | --- |
| Trước khi chọn một phương án recovery | Kênh mới chưa đủ điều kiện làm căn cứ cho một thao tác | Có phương án độc lập khác được phép không? |
| Trước khi cấp quyền recovery | Chưa phát hành quyền thay phương tiện trong khoảng chờ | Bằng chứng có cần kiểm tra lại khi hết chờ không? |
| Trước khi áp dụng thay đổi | Chỉ cho thực hiện thay đổi sau mốc đã định | Quyền và trạng thái tài khoản có còn hợp lệ không? |
| Sau khi thay phương tiện | Chặn một số hành động có tác động lớn | Hạn chế có phạm vi gì và điều kiện gỡ là gì? |

Cùng một tài khoản có thể được phép đặt mật khẩu mới nhưng chưa được đổi kênh recovery. Nó cũng có thể được đăng nhập với phạm vi hạn chế nhưng chưa được tạo API token có quyền cao.

### 3.1. Eligibility về thời gian không phải authorization

Có thể biểu diễn quyết định cuối như sau:

```text
ĐƯỢC THỰC HIỆN =
    giao_dịch_còn_hiệu_lực
    VÀ bằng_chứng_đạt_chính_sách
    VÀ các_điều_kiện_cooldown_đã_đáp_ứng
    VÀ quyền_bao_phủ_đúng_thao_tác
    VÀ trạng_thái_bảo_mật_hiện_tại_cho_phép
    VÀ các_điều_kiện_rủi_ro_khác_được_chấp_nhận
```

Một API nội bộ trả về `cooldownSatisfied = true` chỉ xác nhận phần thời gian. Không được dùng kết quả đó như `recoveryAuthorized = true`.

### 3.2. Phạm vi phải bao phủ đường đi gián tiếp

Nếu chặn thay MFA bằng kênh mới nhưng vẫn cho kênh đó đặt mật khẩu để đăng nhập và gỡ MFA ngay sau đó, điều kiện chờ có thể bị vòng qua.

Cần xét các thao tác kết hợp:

- Đặt mật khẩu rồi đăng nhập qua đường ít yếu tố hơn.
- Đổi email trước, sau đó khôi phục bằng email vừa đổi.
- Đăng ký phương tiện mới rồi dùng nó để gỡ mọi hạn chế.
- Nhờ hỗ trợ thực hiện cùng thay đổi thay cho API bị chặn.
- Dùng một session hoặc token cũ để gọi endpoint khác.

Chính sách cần bao phủ kết quả bảo mật thực tế, không chỉ nút hoặc tên luồng.

## 4. Chọn sự kiện bắt đầu cooldown

Một cooldown có thể chỉ đáng tin khi sự kiện làm mốc cũng đáng tin. Nếu lấy thời điểm client gửi lên hoặc thời điểm một người ngoài bắt đầu yêu cầu làm mốc cho mọi hạn chế, hệ thống dễ bị thao túng.

| Sự kiện | Có thể dùng làm mốc theo chính sách? | Lưu ý |
| --- | --- | --- |
| Hoàn tất việc gắn kênh recovery có quyền | Có thể dùng cho điều kiện kênh mới | Phải phân biệt với việc mới nhập địa chỉ hoặc yêu cầu gửi mã |
| Hoàn tất thay mật khẩu, MFA hoặc passkey hợp lệ | Có thể dùng cho hạn chế sau thay đổi | Gắn với thay đổi đã thực sự được ghi nhận |
| Yêu cầu đã đạt điều kiện để bắt đầu khoảng chờ | Có thể dùng cho trì hoãn thao tác nhạy cảm | Định nghĩa rõ điều kiện này là gì |
| Một người ngoài gửi yêu cầu recovery | Không tự đủ để đặt hạn chế mạnh lên cả tài khoản | Tránh biến endpoint công khai thành công cụ gây gián đoạn |
| Nhập sai mã hoặc gửi lại mã | Thường thuộc kiểm soát lạm dụng | Không tự khởi động lại mọi cooldown recovery |
| Tín hiệu thay SIM hoặc kênh có rủi ro từ bên ngoài | Có thể là đầu vào đánh giá | Cần xét nguồn, thời điểm, độ tin cậy và cách chính sách diễn giải |
| Thời điểm do trình duyệt tự khai | Không phải mốc có thẩm quyền | Client có thể sửa giá trị |

Một sự kiện “kênh mới đã nhận mã” chưa tự chứng minh việc gắn kênh đó vào tài khoản đã được cho phép. Mốc cho cooldown kênh mới nên phản ánh bước liên kết hợp lệ được chính sách chọn, không chỉ một thông điệp đã gửi.

### 4.1. Lưu căn cứ, không chỉ lưu mốc kết thúc

Một bản ghi minh họa:

```text
cooldown_record:
  id
  account_id
  tenant_id_if_applicable
  operation_scope
  recovery_route_if_applicable
  channel_reference_if_applicable
  reason
  trigger_event_id
  trigger_effective_at
  not_before
  policy_version
  status
  cleared_by_decision_if_applicable
```

Bản ghi cần giúp giải thích tại sao phải chờ, phạm vi nào bị ảnh hưởng và thay đổi nào có quyền sửa kết quả.

Không cần lưu số điện thoại nguyên vẹn hoặc token recovery vào bản ghi cooldown nếu một tham chiếu nội bộ đã đủ.

### 4.2. Không khởi động lại đồng hồ chỉ vì có truy vấn

Việc đọc eligibility, tải lại trang hoặc retry một yêu cầu giống nhau không nên tạo sự kiện bắt đầu cooldown mới.

Một thay đổi bảo mật hợp lệ khác có thể tạo khoảng chờ mới theo chính sách. Nhưng cần ghi nhận đây là sự kiện mới, không âm thầm sửa thời điểm cũ khiến không ai biết vì sao thời gian tiếp tục tăng.

Nếu cùng một sự kiện được gửi lại do retry, cơ chế xử lý phải nhận ra định danh sự kiện và không cộng thêm thời gian nhiều lần.

## 5. Tính mốc đủ điều kiện một cách xác định

Với một quy tắc đơn giản:

```text
not_before = trigger_effective_at + cooldown_duration
đạt_điều_kiện_thời_gian = now >= not_before
```

Cần quy định rõ các đại lượng:

- `trigger_effective_at` đến từ sự kiện có thẩm quyền.
- `cooldown_duration` đến từ phiên bản chính sách áp dụng.
- `now` do máy chủ lấy từ nguồn thời gian được chọn cho quyết định.
- So sánh phải thống nhất ở các điểm cấp quyền và áp dụng thay đổi.

Đồng hồ đếm ngược trên trình duyệt chỉ hỗ trợ hiển thị. Nó không tạo quyền khi chạy về không.

### 5.1. Nhiều điều kiện đồng thời

Nếu cùng một thao tác bắt buộc đáp ứng nhiều khoảng chờ, mốc sớm nhất về mặt thời gian là mốc muộn nhất trong các ràng buộc đó:

```text
earliest_time_for_this_operation =
    max(not_before_1, not_before_2, ..., not_before_n)
```

Ví dụ, thay MFA có thể cùng chịu điều kiện kênh mới và một khoảng chờ của yêu cầu đã xác minh.

Công thức này chỉ đúng với những ràng buộc **đồng thời bắt buộc cho đúng thao tác và phương án đang xét**. Không lấy toàn bộ cooldown của tài khoản rồi áp dụng cho mọi phương án.

Nếu chính sách cho phép dùng một passkey còn an toàn thay vì kênh mới, đường đó cần được đánh giá riêng. Nó không tự bỏ qua một hạn chế toàn tài khoản đang có hiệu lực.

Cũng không cộng thời lượng tùy ý. Hai quy tắc bắt đầu từ hai sự kiện khác nhau cần được tính bằng các mốc cụ thể, trừ khi chính sách thật sự định nghĩa chúng nối tiếp nhau.

### 5.2. Chờ đủ nhưng quyền hoặc bằng chứng hết hạn

Điều kiện sử dụng một quyền có thể yêu cầu:

```text
now >= not_before
VÀ now < grant_expires_at
VÀ now < transaction_expires_at
VÀ bằng_chứng_còn_đủ_mới
```

Nếu quyền hết hạn trước hoặc đúng mốc `not_before`, nó không có cửa sổ sử dụng hợp lệ theo các quy tắc trên.

Không sửa bằng cách kéo dài OTP, giữ bằng chứng cũ vô hạn hoặc bỏ kiểm tra hạn. Một thiết kế phù hợp hơn có thể là chỉ cấp quyền ngắn hạn gần lúc được thực hiện, sau khi đánh giá lại các điều kiện cần thiết.

Chính sách có thể cho phép một phần chuẩn bị diễn ra trong thời gian chờ. Nhưng lúc thực hiện vẫn phải kiểm tra lại bằng chứng nào cần còn mới và trạng thái nào chưa được thay đổi.

### 5.3. Thời gian tuyệt đối và cách hiển thị

Có thể lưu các mốc tuyệt đối theo UTC và hiển thị theo múi giờ của người dùng. Tránh tính đủ điều kiện bằng chuỗi ngày giờ cục bộ do trình duyệt gửi lên.

Nếu chính sách nói “một khoảng thời lượng”, cần định nghĩa đó là thời lượng trôi qua. Nếu nói “sau một ngày làm việc” hoặc “sau thời điểm vận hành”, cần quy tắc lịch riêng. Không giả định mọi cách diễn đạt đều đồng nghĩa cùng số giờ.

Sai lệch đồng hồ giữa dịch vụ cũng cần được xử lý trong kiến trúc. Quyết định nhạy cảm nên dùng nguồn thời gian và điểm kiểm tra nhất quán, thay vì tin bộ đếm ở một máy khác.

### 5.4. Không đủ dữ liệu không có nghĩa là đã chờ xong

Nếu một điều kiện bắt buộc không đọc được mốc sự kiện, hệ thống không nên thay bằng thời điểm bằng không rồi kết luận đã đủ điều kiện.

Cần phân biệt:

- Không có cooldown nào áp dụng theo chính sách.
- Có cooldown áp dụng và đã hết thời gian.
- Có cooldown áp dụng nhưng còn phải chờ.
- Chưa thể đánh giá vì dữ liệu hoặc dịch vụ phụ thuộc không có sẵn.

Với thao tác nhạy cảm, trường hợp chưa thể đánh giá cần có kết quả chờ xử lý, retry hoặc thẩm định phù hợp. Nó không được trở thành đường bỏ qua điều kiện.

## 6. Thiết kế kết quả eligibility

Một kết quả chỉ có `true` hoặc `false` thường không đủ cho vận hành. Backend cần phân biệt nguyên nhân và bước được phép tiếp theo.

| Kết quả nội bộ | Ý nghĩa | Hành động có thể thực hiện |
| --- | --- | --- |
| TIME_ELIGIBLE | Đã đáp ứng những điều kiện cooldown đang xét | Tiếp tục kiểm tra bằng chứng, quyền và các điều kiện khác |
| WAIT_UNTIL | Có mốc thời gian xác định còn ở tương lai | Chờ đến mốc dự kiến rồi đánh giá lại |
| NEED_FRESH_EVIDENCE | Bằng chứng cần kiểm tra lại | Thực hiện phương án xác minh được phép |
| REVIEW_REQUIRED | Có điều kiện phải qua thẩm định theo chính sách | Chuyển đúng quy trình và thẩm quyền |
| NOT_PERMITTED | Phương án hoặc thao tác không được chấp nhận | Hướng đến lựa chọn hợp lệ nếu có |
| TEMPORARILY_UNDETERMINED | Chưa có dữ liệu đủ tin cậy để quyết định | Retry hoặc xử lý theo quy trình phụ thuộc |

Các kết quả trên có thể phản ánh nhiều lớp quyết định. Một yêu cầu vừa có cooldown chưa hết vừa có bằng chứng đã cũ. Nội bộ cần giữ các điều kiện liên quan; giao diện có thể chọn trình bày bước tiếp theo phù hợp mà không tiết lộ dữ liệu nhạy cảm.

### 6.1. Mốc dự kiến không phải lời hứa cấp quyền

`next_eligible_at` là mốc dự kiến sớm nhất theo các ràng buộc đã biết cho một thao tác. Nó không bảo đảm yêu cầu chắc chắn được chấp nhận ở thời điểm đó.

Từ lúc trả kết quả đến lúc người dùng thử lại, có thể xảy ra:

- Kênh hoặc phương tiện bị thu hồi.
- Một thay đổi bảo mật hợp lệ mới tạo điều kiện chờ khác.
- Giao dịch hoặc quyền hết hạn.
- Chính sách áp dụng thay đổi.
- Tài khoản chịu một hạn chế độc lập.
- Thẩm quyền phê duyệt không còn hợp lệ.

Vì vậy, kết quả eligibility cần được ràng buộc với ngữ cảnh và được đánh giá lại tại nơi thực hiện thao tác.

### 6.2. Không biến API eligibility thành công cụ dò tài khoản

Một endpoint công khai trả “tài khoản này còn chờ 37 giờ vì vừa đổi số” có thể làm lộ tài khoản tồn tại và lịch sử bảo mật.

Với người ngoài chưa được xác minh, phản hồi cần hạn chế tiết lộ thông tin riêng. Với ngữ cảnh hợp lệ, hệ thống có thể hiển thị mốc dự kiến và bước tiếp theo theo quyền của người đó.

Ngay cả định danh giao dịch khó đoán cũng không nên mặc định đủ để xem mọi lý do bảo mật của tài khoản.

## 7. Thực thi điều kiện ở backend

Một cách tách trách nhiệm là có bộ đánh giá thời gian, sau đó quyết định cấp quyền hoặc áp dụng thay đổi kiểm tra thêm các điều kiện khác.

### 7.1. Mã giả đánh giá cooldown

```text
evaluateCooldown(accountId, tenantId, operation, route, now):
    policy = resolveApplicablePolicy(accountId, tenantId, operation, route)
    constraints = loadRelevantCooldownConstraints(policy)

    if any required constraint cannot be evaluated reliably:
        return TEMPORARILY_UNDETERMINED

    applicable = selectConstraintsForThisOperationAndRoute(constraints)

    if applicable is empty:
        return TIME_ELIGIBLE

    notBefore = maximumNotBefore(applicable)

    if now < notBefore:
        return WAIT_UNTIL(
            notBefore = notBefore,
            policyVersion = policy.version,
            constraintReferences = applicable.references
        )

    return TIME_ELIGIBLE
```

Đây là mã giả cho lớp thời gian. Nó không kiểm tra toàn bộ danh tính, bằng chứng hay quyền thay thông tin xác thực.

Các định danh tài khoản và phương án cần đến từ ngữ cảnh được kiểm soát. Client không được tùy ý đổi `route` hoặc `operation` để loại bỏ ràng buộc mà vẫn thực hiện thao tác cũ.

### 7.2. Kiểm tra lại tại điểm áp dụng thay đổi

```text
applyRecoveryChange(context, transactionId, grantId, requestedChange):
    require context may continue this transaction

    begin transaction or equivalent concurrency control:
        tx = lockRecoveryTransaction(transactionId)
        grant = lockRecoveryGrant(grantId)
        account = lockCurrentAccountSecurityState(tx.accountId)

        require tx and grant are active and not expired
        require grant belongs to tx and account
        require grant permits requestedChange
        require evidence remains acceptable for this change
        require security state and policy still permit the decision

        now = authoritativeCurrentTime()
        require evaluateCooldown(
            account.id, tx.tenantId, requestedChange.operation, tx.route, now
        ) == TIME_ELIGIBLE

        apply requestedChange
        consume grant
        record new security state
        record new cooldowns triggered by this legitimate change, if required
        record durable work for required notifications and session effects

    commit
```

Cơ chế thực tế có thể khác, nhưng cần giữ được tính nhất quán giữa việc kiểm tra cooldown và thay đổi bảo mật. Nếu dữ liệu nằm ở nhiều dịch vụ, phải có cách phát hiện quyết định đã cũ hoặc điều kiện mới phát sinh; không chỉ đọc một cache rồi tin mãi.

### 7.3. Xử lý đồng thời và retry

Hai yêu cầu có thể cùng đọc rằng cooldown đã hết nhưng vẫn đang dùng cùng một quyền recovery. Điều kiện thời gian không thay thế kiểm soát dùng một lần.

Backend cần ngăn cả hai cùng áp dụng thay đổi độc lập bằng khóa, phiên bản hoặc cơ chế giao dịch phù hợp.

Nếu phản hồi bị mất sau khi thay đổi đã hoàn tất, retry của cùng thao tác cần nhận kết quả nhất quán. Không tạo một lần khôi phục mới hoặc khởi động lại cooldown chỉ vì client gửi lại yêu cầu đã thành công.

Một công việc nền gửi thông báo trễ cũng không được đặt lại `trigger_effective_at` của thay đổi. Mốc đó phải phản ánh sự kiện có hiệu lực đã được chọn, không phải lần xử lý lại gần nhất.

## 8. Trải nghiệm người dùng trong thời gian chờ

Một cooldown an toàn cần cho người dùng biết bước tiếp theo thực tế, thay vì chỉ hiển thị một đồng hồ không có ngữ cảnh.

Trong ngữ cảnh được phép, giao diện có thể giải thích:

- Thao tác nào đang phải chờ.
- Mốc dự kiến để thử tiếp.
- Những chức năng hoặc phương án khác còn được phép.
- Việc có thể phải xác minh lại khi tiếp tục.
- Cách báo cáo thay đổi không do mình thực hiện.
- Cách liên hệ hỗ trợ theo đường đã quy định.

Không nên tiết lộ chi tiết phát hiện gian lận, thông tin của kênh khác hoặc dữ liệu tài khoản cho người chưa có quyền xem.

### 8.1. Mẫu thông điệp có phạm vi rõ

| Tình huống | Cách diễn đạt minh họa |
| --- | --- |
| Kênh mới chưa được dùng cho thay MFA | “Phương án này chưa thể dùng để thay MFA. Bạn có thể thử lại từ mốc được hiển thị hoặc dùng phương án khác nếu có.” |
| Hết cooldown nhưng bằng chứng cũ không còn đủ mới | “Bạn có thể tiếp tục bước xác minh. Cần kiểm tra lại trước khi thực hiện thay đổi.” |
| Đăng nhập được nhưng còn hạn chế một thao tác | “Bạn đã lấy lại khả năng đăng nhập. Chức năng này hiện vẫn bị hạn chế theo điều kiện bảo mật.” |
| Không đọc được dữ liệu để quyết định | “Chưa thể kiểm tra điều kiện lúc này. Hãy thử lại theo hướng dẫn.” |
| Thao tác đã hoàn tất và đang xử lý tác động liên quan | “Thay đổi đã được ghi nhận. Một số bước bảo mật còn đang hoàn tất.” |

Thông điệp không nên hứa “hết thời gian là chắc chắn khôi phục thành công”.

### 8.2. Nhắc tiếp tục không đồng nghĩa tự thực hiện

Một công việc theo lịch có thể nhắc người dùng khi đến mốc dự kiến. Nó không tự có quyền đổi mật khẩu, gỡ MFA hoặc thêm passkey.

Nếu sản phẩm thiết kế một thay đổi được lên lịch từ trước, cần có căn cứ ủy quyền rõ ràng cho chính thay đổi đó và kiểm tra lại các điều kiện tại thời điểm thực hiện. Không lấy một sự kiện đồng hồ làm thay thế cho giao dịch có quyền.

Tương tự, tự gửi một mã mới khi đến hạn phải đi qua chính sách gửi và kiểm soát lạm dụng. Không để công việc chạy lại tạo một loạt thông điệp hoặc kéo dài thời hạn bí mật ngoài dự kiến.

### 8.3. Thông báo cần tới kênh phù hợp

Khoảng chờ thường hữu ích hơn khi có thông báo qua kênh còn đáng tin đã đăng ký trước, hoặc một ngữ cảnh ứng dụng phù hợp.

Nhưng cần xét:

- Cảnh báo gửi đến chính kênh bị chiếm có thể không tới người dùng thật.
- Kênh cũ có thể không còn an toàn hoặc không còn thuộc người dùng.
- Không nhận được phản hồi không phải bằng chứng đồng ý.
- Nút báo cáo hoặc hủy cũng cần quyền và phạm vi phù hợp.

Một báo cáo có thể dẫn đến quy trình kiểm tra sự cố. Không nên cho bất kỳ người ngoài nào nhập email rồi hủy mọi phương tiện hoặc khóa toàn bộ tài khoản.

## 9. Tránh cooldown trở thành công cụ gây gián đoạn

Đối thủ có thể không cần chiếm tài khoản nếu họ làm người dùng hợp pháp không bao giờ đến được mốc đủ điều kiện.

Một thiết kế dễ bị lạm dụng:

```text
mỗi lần nhận yêu cầu recovery:
    account.notBefore = now + duration
```

Nếu endpoint công khai, đối thủ có thể gửi yêu cầu đều đặn để kéo dài hạn vô hạn.

Thiết kế tốt hơn cần phân biệt sự kiện:

- **Yêu cầu chưa xác minh:** áp dụng giới hạn lưu lượng và thông điệp thích hợp; chưa tự đặt hạn chế mạnh lên tài khoản.
- **Thay đổi bảo mật hợp lệ:** có thể tạo cooldown theo phạm vi và mốc được định nghĩa.
- **Tín hiệu rủi ro cần xử lý:** đi qua chính sách phản ứng riêng với nguồn, căn cứ và thẩm quyền rõ ràng.
- **Retry của cùng sự kiện:** không tạo thêm một khoảng chờ mới.

### 9.1. Không để người dùng tự làm yếu điều kiện

Ngoài việc kéo dài để gây gián đoạn, đối thủ còn có thể cố rút ngắn cooldown bằng cách:

- Gửi timestamp cũ từ client.
- Chọn một tên phương án không có ràng buộc nhưng gọi API thay đổi khác.
- Đổi thiết bị để mất bản ghi cooldown chỉ lưu trong trình duyệt.
- Tạo giao dịch mới để tránh ràng buộc đang áp dụng ở cấp tài khoản.
- Chuyển tenant hoặc dùng endpoint hỗ trợ để thực hiện cùng kết quả.
- Dùng một token được cấp trước khi cooldown mới có hiệu lực.

Các điều kiện phải được lưu và thực thi tại phạm vi phù hợp. Nếu điều kiện thuộc tài khoản hoặc kênh, tạo giao dịch mới không tự xóa nó.

### 9.2. Lựa chọn phương án khác cần giữ các hạn chế chung

Một passkey còn hợp lệ có thể cho phép đi theo đường không phụ thuộc kênh recovery mới, nếu chính sách đã cho phép. Đây là đánh giá một phương án khác, không phải xóa toàn bộ cooldown.

Những hạn chế toàn tài khoản hoặc theo thao tác vẫn phải được kiểm tra. Không cho người dùng chọn một đường khác để bỏ qua quyết định xử lý sự cố độc lập.

## 10. Ngoại lệ và thay đổi chính sách

Có thể có tình huống cần xem xét ngoại lệ, đặc biệt với tài khoản tổ chức hoặc yêu cầu khẩn cấp. Ngoại lệ cần là một quyết định có phạm vi, không phải sửa trực tiếp timestamp để tránh bị phát hiện.

Một bản ghi ngoại lệ có thể cần:

- Tài khoản, tenant, thao tác và giao dịch được áp dụng.
- Quy tắc thời gian nào được điều chỉnh.
- Bằng chứng và lý do chấp nhận rủi ro.
- Người có thẩm quyền phê duyệt.
- Thời hạn và số lần sử dụng.
- Điều kiện thu hồi.
- Các hạn chế khác vẫn còn hiệu lực.
- Dấu vết thay đổi và thông báo tương ứng.

Ngoại lệ về thời gian không mặc định miễn bằng chứng xác minh. Nó cũng không tự bỏ hạn chế đặc quyền, giữ xử lý sự cố hoặc yêu cầu phê duyệt độc lập khác.

Không lấy sự khẩn cấp của người gọi làm bằng chứng sở hữu tài khoản.

### 10.1. Chính sách mới tác động đến yêu cầu đang chờ thế nào?

Khi thời lượng hoặc phạm vi cooldown thay đổi, cần quyết định:

- Yêu cầu đang mở tiếp tục theo phiên bản nào?
- Quy tắc mới có áp dụng ngay cho thao tác nhạy cảm chưa thực hiện không?
- Trường hợp nào cần tính lại mốc?
- Mốc đã hiển thị cho người dùng có cần cập nhật không?
- Việc rút ngắn có đủ thẩm quyền và đánh giá rủi ro không?

Không lặng lẽ tính lại mọi mốc bằng thời điểm hiện tại, khiến người dùng phải chờ lại từ đầu dù sự kiện gốc không thay đổi.

Cũng không giữ một quyền cũ hoạt động nếu chính sách mới đã xác định quyết định đó không còn được chấp nhận. Cần quy tắc chuyển tiếp rõ ràng và kiểm tra tại nơi áp dụng thay đổi.

## 11. Ví dụ: kênh mới, thời gian chờ và bằng chứng đã cũ

Giả sử một dịch vụ có các quy tắc minh họa sau:

- Kênh recovery mới chỉ được dùng cho đường thay MFA đang xét sau 48 giờ từ lúc việc gắn kênh hợp lệ hoàn tất.
- Đường đó còn yêu cầu chờ 30 phút sau một mốc xác minh ban đầu đã được quy định.
- Bằng chứng cần còn đủ mới khi cấp quyền và áp dụng thay đổi.
- Quyền thay MFA có thời hạn ngắn, không dùng thay cho phiên đầy đủ.

**Các con số chỉ phục vụ ví dụ**, không phải khuyến nghị dùng chung. Kênh mới đủ tuổi vẫn chỉ là một thành phần của bộ bằng chứng được chính sách chấp nhận.

### 11.1. Tính thời điểm sớm nhất

Tất cả mốc dưới đây dùng UTC để dễ đối chiếu:

| Sự kiện | Thời điểm | Hệ quả |
| --- | --- | --- |
| Hoàn tất gắn kênh hợp lệ | Thứ Hai, 09:00 | Điều kiện 48 giờ kết thúc vào Thứ Tư, 09:00 |
| Yêu cầu đạt mốc xác minh ban đầu | Thứ Ba, 10:00 | Điều kiện 30 phút kết thúc vào Thứ Ba, 10:30 |
| Đánh giá cùng đường thay MFA | Thứ Ba, 10:30 | Vẫn phải chờ điều kiện kênh mới |
| Mốc sớm nhất của hai điều kiện | Thứ Tư, 09:00 | Đủ phần thời gian nếu không có ràng buộc mới |

Không cộng thành 48 giờ 30 phút kể từ một mốc tùy ý. Hai điều kiện có sự kiện bắt đầu khác nhau.

### 11.2. Không giữ mã cũ sống đến hết hai ngày

Nếu mã hoặc quyền được cấp từ Thứ Ba đã hết hạn trước Thứ Tư, hệ thống không được chấp nhận chúng chỉ vì cooldown đã kết thúc.

Đến Thứ Tư, người dùng cần hoàn tất những bước xác minh còn bắt buộc theo chính sách. Sau đó backend mới cấp hoặc sử dụng quyền có hiệu lực cho thao tác.

Thiết kế luồng nên tránh bắt người dùng nhận một token không bao giờ có cửa sổ sử dụng hợp lệ. Có thể trì hoãn việc cấp quyền ngắn hạn đến gần lúc được thực hiện, trong khi vẫn bảo toàn bằng chứng nào cần kiểm tra lại.

### 11.3. Thay đổi mới trong lúc chờ

Nếu kênh được thay hợp lệ bằng một kênh khác vào Thứ Ba, quy tắc cho kênh mới phải dùng đúng sự kiện của kênh đang được xét.

Nếu chỉ có một lần tải lại trang hoặc yêu cầu gửi mã chưa tạo thay đổi bảo mật hợp lệ, không tự tính lại 48 giờ cho toàn tài khoản.

Nếu một hạn chế độc lập phát sinh trước Thứ Tư, mốc dự kiến cũ không đủ để áp dụng thay đổi. Backend cần đánh giá lại các ràng buộc hiện tại.

### 11.4. Khôi phục xong nhưng một số hành động vẫn phải chờ

Giả sử dịch vụ còn có hạn chế riêng cho một thao tác nhạy cảm sau recovery. Hạn chế này bắt đầu từ sự kiện hoàn tất thay đổi được quy định, không phải từ ngày kênh liên hệ được gắn.

Người dùng có thể đã lấy lại phương tiện đăng nhập nhưng chưa được thực hiện thao tác đó. Giao diện và API phải cùng thể hiện phạm vi này, thay vì coi “recovery thành công” là mở mọi quyền.

## 12. Nhật ký và các tình huống cần đặc tả

Nhật ký nên giúp giải thích quyết định eligibility mà không ghi bí mật:

- Thao tác và phương án được đánh giá.
- Tham chiếu sự kiện bắt đầu và các cooldown áp dụng.
- Mốc `not_before`, nguồn thời gian quyết định và phiên bản chính sách.
- Phiên bản trạng thái bảo mật liên quan.
- Kết quả chờ, được xét tiếp, cần xác minh mới hoặc chưa thể quyết định.
- Ngoại lệ, người phê duyệt và phạm vi được miễn.
- Thời điểm thực tế áp dụng thay đổi và các tác động sau đó.

Dữ liệu hiển thị công khai cần ít hơn nhật ký nội bộ. Không ghi OTP, token recovery nguyên vẹn, mật khẩu hoặc bí mật mã dự phòng.

| Tình huống | Hành vi cần được xác định |
| --- | --- |
| Đúng trước mốc một khoảng rất nhỏ | Chưa cho qua điều kiện thời gian |
| Đúng tại mốc theo quy tắc so sánh đã chọn | Cho qua phần thời gian; vẫn kiểm tra điều kiện khác |
| Đồng hồ client được chỉnh sớm | Không làm thay đổi quyết định máy chủ |
| Không đọc được dữ liệu cooldown bắt buộc | Không mặc định đã hết thời gian |
| Token hết hạn trước mốc chờ | Không kéo dài hoặc dùng lại token cũ |
| Thời gian đã đủ nhưng bằng chứng không còn mới | Yêu cầu xác minh theo chính sách |
| Nhiều cooldown cùng áp dụng cho một thao tác | Dùng đúng tổ hợp ràng buộc, không cộng hoặc bỏ qua tùy ý |
| Có phương án độc lập khác | Đánh giá riêng nhưng vẫn giữ các hạn chế chung |
| Yêu cầu công khai được gửi lặp | Không tự kéo dài hạn mạnh trên toàn tài khoản |
| Cùng sự kiện được xử lý nhiều lần | Không tạo thêm khoảng chờ do retry |
| Tạo giao dịch mới hoặc đổi thiết bị | Không bỏ điều kiện ở phạm vi tài khoản hoặc kênh |
| Một thay đổi bảo mật hợp lệ phát sinh khi đang chờ | Đánh giá lại dựa trên đúng sự kiện và chính sách |
| Hai yêu cầu cùng áp dụng khi đã hết chờ | Vẫn kiểm soát dùng quyền một lần và tính nhất quán |
| Ngoại lệ được phê duyệt cho một thao tác | Không tự miễn mọi cooldown hoặc mọi bằng chứng |
| Đếm ngược kết thúc trên giao diện | Chỉ cho gửi yêu cầu đánh giá lại, không tự cấp quyền |
| Recovery đã hoàn tất nhưng còn hạn chế sau khôi phục | Không cho đường API khác mở quyền ngoài phạm vi |

Các tình huống này là đầu vào cho đặc tả và kiểm thử triển khai, không thay thế việc thiết kế đồng bộ và phân quyền của hệ thống thực tế.

Một quy tắc cooldown có thể thực thi phải trả lời được: **chờ cho thao tác nào, bắt đầu từ sự kiện nào, khi nào đủ điều kiện về thời gian và còn cần kiểm tra gì khi tiếp tục**. Khi các câu trả lời này rõ ràng, khoảng chờ mới hỗ trợ giảm nguy cơ chiếm đoạt tài khoản mà không trở thành bằng chứng giả hoặc công cụ khóa người dùng hợp pháp.
