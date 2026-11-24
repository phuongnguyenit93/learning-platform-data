# Mailbox compromise signal: dấu hiệu hộp thư bị xâm nhập trong khôi phục tài khoản

## 1. Vì sao hộp thư là một điểm tin cậy nhạy cảm?

Nhiều hệ thống dùng email để gửi liên kết đặt lại mật khẩu, mã xác minh, thông báo đổi MFA và cảnh báo đăng nhập. Khi hộp thư bị xâm nhập, kẻ tấn công có thể tiếp cận các thông điệp này và lợi dụng chính luồng khôi phục để giành quyền truy cập dịch vụ khác.

**Mailbox compromise signal** là tín hiệu cho biết hộp thư gắn với tài khoản có thể đang bị một bên không được phép đọc, sử dụng hoặc điều khiển. Tín hiệu này thay đổi mức tin cậy của kênh email trong quyết định khôi phục.

Ví dụ, Mai vẫn đăng nhập được vào email, nhưng một ứng dụng không được phép có quyền đọc thư. Kẻ tấn công có thể đọc liên kết khôi phục tài khoản học tập mà Mai không biết. Việc Mai tiếp tục sử dụng hộp thư bình thường không loại trừ khả năng có người khác cùng truy cập.

Cần tách ba kết luận:

- **Hộp thư đang có dấu hiệu bất thường:** cần đánh giá thêm trước khi tin vào kênh email.
- **Có bằng chứng hộp thư bị xâm nhập:** cần ngừng dùng riêng kênh đó để phê duyệt các thay đổi nhạy cảm.
- **Tài khoản tại dịch vụ đang bị chiếm quyền:** là kết luận khác, cần bằng chứng về chính dịch vụ đó.

Một hộp thư bị xâm nhập có thể dẫn đến chiếm đoạt tài khoản, nhưng không nên gộp mọi trạng thái thành một cờ “người dùng gian lận”.

## 2. Điều gì có thể bị mất khi email không còn đáng tin?

Kẻ tấn công không nhất thiết phải đổi mật khẩu hộp thư. Một phiên đăng nhập bị đánh cắp, quyền đọc thư của ứng dụng, quyền ủy quyền hoặc quy tắc chuyển tiếp cũng có thể làm lộ thông điệp khôi phục.

Trong luồng đặt lại mật khẩu, có thể xảy ra chuỗi sự kiện sau:

1. Kẻ tấn công tiếp cận thư mới của nạn nhân.
2. Kẻ tấn công yêu cầu dịch vụ gửi liên kết khôi phục.
3. Liên kết được đọc từ hộp thư hoặc bản sao chuyển tiếp.
4. Kẻ tấn công sử dụng liên kết trước chủ tài khoản.
5. Kẻ tấn công thay mật khẩu, rồi tìm cách thay MFA hoặc địa chỉ khôi phục.
6. Thông báo bảo mật bị đọc, di chuyển hoặc xóa để giảm khả năng chủ tài khoản phát hiện.

Token ngẫu nhiên, thời hạn ngắn và tính dùng một lần vẫn cần thiết, nhưng các thuộc tính đó không chứng minh người nhận token là chủ tài khoản khi kênh nhận đã bị xâm nhập. Token dùng một lần có thể bị người không được phép sử dụng lần đầu tiên.

Theo OWASP, khi nghi ngờ chiếm quyền, việc khôi phục cần xem xét bằng chứng độc lập đã được thiết lập trước đó và không chỉ dựa vào thông tin khôi phục vừa thay đổi. Điều này hỗ trợ nguyên tắc không dùng một kênh đang bị nghi ngờ để tự xác nhận rằng kênh ấy an toàn. [OWASP, Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise)

## 3. Các nhóm dấu hiệu và giới hạn của từng nhóm

### 3.1. Thay đổi trong hộp thư

Microsoft liệt kê quy tắc hộp thư đáng ngờ, thư bị mất hoặc xóa, thông điệp lạ trong thư đã gửi và chuyển tiếp ra bên ngoài mới được thêm là những triệu chứng có thể liên quan đến hộp thư bị xâm nhập. Đây là dấu hiệu cần điều tra, không phải mọi quy tắc chuyển tiếp đều độc hại. [Microsoft Learn, Common symptoms of a compromised email account](https://learn.microsoft.com/en-us/defender-office-365/responding-to-a-compromised-email-account#common-symptoms-of-a-compromised-microsoft-365-email-account)

Các quan sát này đặc biệt có ý nghĩa khi có nguồn dữ liệu quản trị đáng tin, biết ai thực hiện thay đổi và có thể so sánh với mục đích sử dụng hợp lệ.

Ví dụ, quy tắc chuyển thư từ địa chỉ bảo mật của dịch vụ sang thư mục ít được chú ý có thể làm giảm khả năng phát hiện khôi phục trái phép. Tuy nhiên, người dùng cũng có thể chủ động sắp xếp thư theo cùng cách. Hệ thống cần ngữ cảnh và bằng chứng bổ sung.

### 3.2. Thay đổi quyền truy cập hoặc bảo mật

Một cảnh báo có thể liên quan đến:

- Phương thức xác thực mới mà chủ tài khoản không nhận ra.
- Thay đổi thông tin khôi phục của chính tài khoản email.
- Ứng dụng hoặc người được ủy quyền có quyền truy cập hộp thư ngoài dự kiến.
- Hoạt động truy cập do nhà cung cấp email xác định là đáng ngờ.
- Báo cáo từ đội an ninh rằng một danh tính doanh nghiệp đang trong quá trình xử lý xâm nhập.

Mỗi loại dữ liệu có độ bao phủ khác nhau. Một danh sách đăng nhập không bất thường chưa loại trừ việc thư bị đọc qua ứng dụng đã được cấp quyền từ trước.

### 3.3. Dấu hiệu quan sát tại dịch vụ cần khôi phục

Dịch vụ bên ngoài thường chỉ thấy yêu cầu gửi email, việc xuất trình token và các thay đổi trên tài khoản của mình. Nó có thể nhận ra một mẫu bất thường như đặt lại mật khẩu rồi yêu cầu gỡ MFA từ môi trường mới.

Những quan sát này gợi ý rủi ro đối với giao dịch khôi phục; chúng chưa đủ để kết luận hộp thư đã bị xâm nhập. Tên tín hiệu nội bộ cần phản ánh đúng mức suy luận, chẳng hạn RECOVERY_PATTERN_ANOMALY thay vì CONFIRMED_MAILBOX_COMPROMISE.

| Quan sát | Có thể gợi ý điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Quy tắc chuyển tiếp mới chưa giải thích được | Thư có thể được chuyển sang bên khác | Người tạo quy tắc chắc chắn là kẻ tấn công |
| Chủ tài khoản báo không gửi một email | Có thể có truy cập trái phép hoặc giả mạo | Hộp thư đã bị truy cập nếu chưa phân biệt được giả mạo người gửi |
| Token được dùng rất nhanh | Có thể có tự động hóa hoặc người theo dõi hộp thư | Chắc chắn có xâm nhập; bộ quét liên kết cũng có thể truy cập URL |
| Không nhận được thư cảnh báo | Có thể có lọc thư, lỗi chuyển phát hoặc hành vi che giấu | Thư chắc chắn đã bị kẻ tấn công xóa |
| Đổi mật khẩu rồi yêu cầu thay MFA | Có thể là chuỗi chiếm quyền hoặc người dùng mất thiết bị | Hộp thư là điểm xâm nhập ban đầu |
| Nhà cung cấp xác nhận sự cố đúng hộp thư | Có bằng chứng mạnh về kênh bị ảnh hưởng | Mọi tài khoản dùng địa chỉ đó đều đã bị chiếm quyền |

## 4. Dịch vụ thực sự nhìn thấy được những gì?

Khả năng quan sát là ràng buộc quan trọng khi thiết kế tín hiệu.

### 4.1. Hộp thư thuộc môi trường doanh nghiệp có tích hợp

Một tổ chức có thể có dữ liệu từ nhà cung cấp danh tính, nền tảng email hoặc đội ứng cứu. Việc tích hợp cần quyền phù hợp, ràng buộc tenant và ánh xạ danh tính rõ ràng.

Không nên giả định một sự kiện cho người dùng trong tenant A có thể áp dụng cho cùng chuỗi email ở tenant B. Nếu địa chỉ email được đổi tên hoặc tái cấp cho người khác, hệ thống cần quan tâm danh tính nhà cung cấp và lịch sử ràng buộc, không chỉ so sánh chuỗi địa chỉ.

### 4.2. Hộp thư cá nhân bên ngoài

Một website thông thường không tự biết quy tắc chuyển tiếp, danh sách phiên hoặc ứng dụng có quyền đọc Gmail của người dùng. Nếu không có tích hợp được cho phép, trạng thái đó là **không quan sát được**, không phải “đã kiểm tra và an toàn”.

Không yêu cầu người dùng đưa mật khẩu hộp thư hoặc gửi mã đăng nhập email cho nhân viên hỗ trợ để kiểm tra. Không thu thập toàn bộ nội dung thư chỉ để xây dựng một tín hiệu rủi ro khi không có nhu cầu và quyền truy cập tương ứng.

Trong nhiều trường hợp, lựa chọn thực tế là tiếp nhận báo cáo, hướng dẫn người dùng xử lý email với nhà cung cấp và yêu cầu bằng chứng khôi phục độc lập cho tài khoản của dịch vụ.

### 4.3. Email được xác minh từ trước

Trạng thái email_verified=true ghi nhận một điều kiện đã được xác minh theo cơ chế của hệ thống tại một thời điểm. Nó không chứng minh hộp thư chưa từng bị xâm nhập hoặc hiện chỉ có chủ tài khoản truy cập.

Tương tự:

- SMTP chấp nhận thư không chứng minh người nhận hợp lệ đã đọc thư.
- Sự kiện mở email không phải bằng chứng xác thực danh tính.
- SPF, DKIM và DMARC không xác nhận hộp thư người nhận an toàn.
- Hai địa chỉ email cùng chuyển về một hộp thư không phải hai kênh độc lập.
- Thay địa chỉ sang một hộp thư vừa được khai báo không tự giải quyết vấn đề chứng minh quyền sở hữu tài khoản.

## 5. Biểu diễn tín hiệu có nguồn gốc và thời gian

Một cờ mailboxCompromised=true thiếu dữ liệu để giải thích, sửa sai và xử lý sự kiện đến muộn. Có thể thiết kế bản ghi tín hiệu như sau:

~~~text
MailboxRiskSignal
  signalId
  issuer
  tenantId
  providerSubjectId
  accountId
  recoveryChannelId
  recoveryChannelVersion
  kind
  confidence
  sourceEventId
  eventTime
  receivedTime
  validUntil
  evidenceReference
  status
~~~

Các trường trong ví dụ có mục đích khác nhau:

- **eventTime:** thời điểm sự kiện xảy ra theo nguồn cung cấp.
- **receivedTime:** thời điểm hệ thống nhận được sự kiện.
- **validUntil:** giới hạn độ mới của thông tin dùng trong một quyết định.
- **recoveryChannelVersion:** phiên bản ràng buộc kênh, giúp tránh áp dụng sự kiện cho sai địa chỉ sau khi đổi kênh.
- **evidenceReference:** tham chiếu tới bằng chứng được bảo vệ, không nhúng token hay nội dung thư vào log vận hành.
- **confidence:** mức độ tin cậy của kết luận dựa trên nguồn và quá trình xác minh.

Độ nghiêm trọng và độ tin cậy là hai chiều khác nhau. Một lời khai “email bị chiếm quyền” mô tả hậu quả nghiêm trọng, nhưng lời khai chưa xác thực có độ tin cậy khác với sự kiện đã được nhà cung cấp và đội xử lý sự cố xác nhận.

Bản ghi cũng cần cho biết dữ liệu có sẵn hay không. Có thể tách trạng thái quan sát thành AVAILABLE, UNAVAILABLE và NOT_INTEGRATED. Không gán UNAVAILABLE thành “không có rủi ro”.

## 6. Xác thực sự kiện trước khi tác động tài khoản

Nguồn tín hiệu có thể trở thành một đường tấn công nếu bất kỳ ai cũng gửi được cảnh báo giả để khóa tài khoản người khác.

Với tích hợp sự kiện, các bước kiểm soát có thể gồm:

1. Xác minh bên phát hành theo giao thức tích hợp, bao gồm chữ ký, xác thực kết nối hoặc cơ chế tương ứng.
2. Kiểm tra đúng đối tượng nhận, tenant và phạm vi quyền của nguồn.
3. Ánh xạ sự kiện tới danh tính và kênh khôi phục đúng phiên bản.
4. Chống xử lý lặp bằng định danh sự kiện của nguồn.
5. Đánh giá thời gian, độ trễ và thứ tự sự kiện trước khi cập nhật trạng thái.
6. Ghi lại quyết định xử lý để có thể truy vết mà không làm lộ bí mật.

Không phải mọi nguồn đều có chữ ký sự kiện giống nhau. Cơ chế phải dựa trên hợp đồng của tích hợp thực tế; một trường issuer trong JSON do bên gửi tự khai không thay thế việc xác thực nguồn.

Ví dụ, nếu cảnh báo xâm nhập xảy ra lúc 09:00 nhưng đến 09:10 mới được nhận, hệ thống cần xem lại các grant phát hành trong khoảng đó. Nếu sự kiện khắc phục xảy ra lúc 09:30 đã được xử lý, một cảnh báo cũ đến lúc 09:40 không được mù quáng ghi đè toàn bộ lịch sử mà bỏ qua thứ tự sự cố.

Ngược lại, sự kiện khắc phục cũ không được xóa một cảnh báo xâm nhập mới hơn. Có thể quản lý theo incidentId, phiên bản hoặc cơ chế đối chiếu thứ tự riêng của nguồn.

## 7. Chuyển tín hiệu thành chính sách khôi phục

Một chính sách minh họa có thể phân biệt các tình huống sau:

| Trạng thái của kênh email | Quyết định đối với khôi phục chỉ dựa vào email | Đường xử lý tiếp theo |
| --- | --- | --- |
| Chưa tích hợp dữ liệu nhà cung cấp | Áp dụng chính sách nền, không tự cộng tín nhiệm vì thiếu cảnh báo | Đánh giá bằng chứng và rủi ro của hành động |
| Báo cáo chưa xác thực | Ghi nhận và hạn chế nguy cơ lạm dụng báo cáo | Đề nghị bằng chứng bổ sung phù hợp |
| Có dấu hiệu đáng ngờ đã được đối chiếu | Tạm ngừng nhánh nhanh cho hành động nhạy cảm | Xác minh qua phương thức độc lập |
| Xác nhận hộp thư bị xâm nhập | Không phê duyệt chỉ bằng token gửi vào hộp thư đó | Xử lý sự cố và dùng quy trình phục hồi khác |
| Có bằng chứng khắc phục phù hợp | Đánh giá lại điều kiện sử dụng kênh | Không tự phục hồi token cũ đã bị thu hồi |

Bảng này là ví dụ thiết kế, không phải một tiêu chuẩn ngưỡng áp dụng cho mọi sản phẩm.

Một tín hiệu mạnh về kênh bị xâm nhập nên là điều kiện chặn việc dùng riêng kênh ấy cho hành động nhạy cảm. Không nên để nhiều tín hiệu yếu như IP quen, giờ sử dụng quen hoặc cookie cũ cộng điểm rồi vô hiệu hóa điều kiện chặn đó.

Đối với báo cáo chưa xác thực, cần tránh biến endpoint “báo email bị hack” thành công cụ khóa tài khoản tùy ý. Có thể yêu cầu thêm xác minh hoặc ngừng một giao dịch rủi ro cụ thể thay vì vô hiệu hóa toàn bộ quyền đăng nhập hợp lệ.

Quyết định cần gắn với hành động. Dừng việc gỡ MFA qua email không đồng nghĩa phải từ chối mọi truy cập bằng khóa bảo mật còn hợp lệ.

## 8. Bằng chứng thay thế phải độc lập

Khi email đáng ngờ, hệ thống có thể xem xét phương thức đã thiết lập từ trước, phù hợp với mức bảo đảm của tài khoản và hành động:

- Khóa bảo mật hoặc passkey khác còn kiểm soát được.
- Mã khôi phục đã cấp trước sự cố, chưa sử dụng.
- Quy trình quản trị hoặc hỗ trợ có xác minh danh tính theo chính sách.
- Kênh khôi phục khác đã được ràng buộc an toàn và không cùng phụ thuộc vào hộp thư bị ảnh hưởng.

Không xem hai mã cùng gửi vào một hộp thư là hai bằng chứng độc lập. Đọc email rồi nhập OTP trong email vẫn dựa trên cùng một khả năng truy cập thư.

Cần xem cả phụ thuộc gián tiếp. Một địa chỉ dự phòng tự chuyển tiếp về hộp thư bị xâm nhập có thể không độc lập. Một phương thức được đăng ký sau khi kẻ tấn công đã có quyền kiểm soát cũng không nên tự động được coi là bằng chứng lịch sử của chủ tài khoản.

Nếu chọn passkey làm bằng chứng thay thế, cần đánh giá mô hình lưu trữ, đồng bộ và ràng buộc thực tế. Không chỉ dựa vào tên loại phương thức để khẳng định nó nằm ngoài cùng phạm vi xâm nhập.

## 9. Xử lý grant đang chờ và cuộc đua với sự kiện mới

Tín hiệu có thể xuất hiện sau khi email đặt lại đã được gửi. Khi đó, chỉ chặn việc phát hành token mới là chưa đủ.

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant R as Dịch vụ khôi phục
    participant S as Trạng thái bảo mật
    participant E as Nguồn tín hiệu email
    U->>R: Bắt đầu đặt lại mật khẩu
    R->>S: Đọc phiên bản và chính sách kênh
    R-->>U: Phát hành grant có giới hạn
    E->>S: Sự kiện xâm nhập được xác thực
    S->>S: Cập nhật trạng thái và phiên bản
    U->>R: Xuất trình token để hoàn tất
    R->>S: Kiểm tra lại grant và trạng thái hiện tại
    S-->>R: Kênh không còn đủ tin cậy
    R-->>U: Yêu cầu phương thức xác minh khác
~~~

Một cách thiết kế là gắn grant với phiên bản trạng thái bảo mật của tài khoản và kênh. Khi nhận sự kiện đủ mức tác động, hệ thống cập nhật phiên bản hoặc thu hồi các grant liên quan.

Mã giả cho bước hoàn tất:

~~~text
completeRecovery(rawToken, requestedAction):
    grant = lookupGrantByDigest(rawToken)
    require grant is issued, unexpired and not consumed
    require grant.action == requestedAction

    begin transaction
        lock grant and account security state
        recheck grant state and expiry
        require grant.securityVersion == currentSecurityVersion

        channel = loadCurrentRecoveryChannel(grant.channelId)
        require channel.version == grant.channelVersion

        decision = evaluateCurrentPolicy(
            action = requestedAction,
            verifiedEvidence = grant.evidence,
            channelState = channel.securityState
        )
        require decision permits this exact action

        apply authorized change
        consume grant
        record durable audit event
    commit transaction
~~~

Việc đọc ban đầu có thể hỗ trợ tra cứu, nhưng các điều kiện quyết định cần được kiểm tra lại trong cơ chế đồng bộ bảo vệ thay đổi. Kiểm tra một lần rồi dùng kết quả đó mãi sẽ tạo khoảng trống giữa đánh giá và thực thi.

Trong kiến trúc phân tán, nguồn tín hiệu, cơ sở dữ liệu khôi phục và session có thể không cập nhật cùng lúc. Cần xác định cửa sổ trễ, cách đánh dấu dữ liệu cũ và cơ chế kiểm tra phiên bản hoặc thu hồi phù hợp. Sơ đồ không tự bảo đảm mọi sự kiện bên ngoài đã được biết ngay lập tức.

## 10. Khắc phục hộp thư và khôi phục tài khoản là hai phạm vi

Chủ tài khoản cần xử lý hộp thư với nhà cung cấp hoặc đội quản trị email có thẩm quyền. Google hướng dẫn xem lại sự kiện bảo mật, thiết bị và các thiết lập Gmail như bộ lọc hoặc quy tắc chuyển tiếp không do người dùng tạo. [Google Account Help, Secure a hacked or compromised Google Account](https://support.google.com/accounts/answer/6294825)

Dịch vụ cần khôi phục không nên tự tuyên bố hộp thư an toàn chỉ vì người dùng nhấn “Tôi đã đổi mật khẩu email”. Tuyên bố đó là một đầu vào cần đánh giá; điều kiện tái tin cậy phải phù hợp với mức bảo đảm và khả năng quan sát thực tế.

Microsoft đưa việc thu hồi truy cập, xem lại phương thức MFA và ứng dụng được cấp quyền vào quy trình ứng phó tài khoản email bị xâm nhập. Điều này cho thấy đổi mật khẩu chỉ là một phần của quá trình khắc phục. [Microsoft Learn, Secure and restore email functionality](https://learn.microsoft.com/en-us/defender-office-365/responding-to-a-compromised-email-account#secure-and-restore-email-functionality-for-a-compromised-microsoft-365-mail-enabled-account)

Tại chính dịch vụ của mình, sau khi xác minh chủ tài khoản bằng quy trình phù hợp, có thể cần:

- Thu hồi session và refresh token trong phạm vi sự cố.
- Vô hiệu hóa các liên kết hoặc grant khôi phục còn tồn đọng.
- Xem lại phương thức xác thực và kênh khôi phục bị thay đổi trái phép.
- Đăng ký lại kênh theo quy trình có tái xác thực và thông báo thích hợp.
- Ghi nhận lý do cho phép sử dụng lại kênh và phạm vi quyết định.

Không khôi phục tự động một địa chỉ cũ chỉ vì nó từng tồn tại. Địa chỉ đó có thể đã bị bỏ, tái cấp hoặc thay đổi vì sự cố trước đây. Không gửi bí mật khôi phục mới vào kênh đang bị nghi ngờ để làm bước xác minh duy nhất.

Khoảng chờ có thể hỗ trợ vận hành, nhưng thời gian tự trôi qua không chứng minh xâm nhập đã chấm dứt.

## 11. Thông báo, quyền riêng tư và vận hành

Thông báo gửi tới hộp thư đáng ngờ có thể vẫn hữu ích theo chính sách, nhưng không được coi việc không phản hồi là đồng ý. Kẻ tấn công có thể đọc hoặc che giấu thông báo.

Nếu có kênh thông báo khác đã đăng ký và còn phù hợp, hệ thống có thể dùng để hướng dẫn chủ tài khoản xử lý. Nội dung thông báo cần tránh lộ token, địa chỉ đầy đủ của các kênh khác hoặc các chi tiết giúp người không được phép mở rộng truy cập.

Giao diện công khai nên diễn đạt kết quả theo phạm vi:

> Yêu cầu này cần thêm một phương thức xác minh đã đăng ký. Hãy tiếp tục bằng lựa chọn bảo mật khả dụng hoặc quy trình hỗ trợ.

Không cần trả cho người chưa xác thực thông tin chi tiết rằng nhà cung cấp đã phát hiện ứng dụng đọc thư nào, hộp thư thuộc tenant nào hoặc tài khoản có tồn tại hay không.

Dữ liệu vận hành nên tập trung vào mã sự kiện, nguồn, thời gian, phạm vi kênh và lý do quyết định. Chỉ lưu nội dung thư hoặc dữ liệu nhạy cảm khi có mục đích rõ ràng, quyền truy cập phù hợp và chính sách lưu giữ.

Các chỉ số có ích gồm:

- Độ trễ từ lúc nhận tín hiệu đến lúc ngừng chấp nhận grant liên quan.
- Số lần hoàn tất bị chặn vì trạng thái kênh thay đổi.
- Tỷ lệ báo cáo được xác minh và tỷ lệ chuyển nhánh nhầm.
- Số tài khoản bị ảnh hưởng bởi sự kiện không ánh xạ được đúng danh tính.
- Thời gian người dùng hợp lệ hoàn tất qua phương thức thay thế.

Một hệ thống chặn nhiều yêu cầu chưa chắc đã phát hiện tốt. Cần xem cả khả năng người dùng hợp lệ tiếp tục khôi phục và khả năng kẻ tấn công dùng cảnh báo giả để gây gián đoạn.

## 12. Tình huống thực hành

Tài khoản của An dùng một địa chỉ email đã xác minh. Lúc 08:00, dịch vụ phát hành liên kết đặt lại mật khẩu. Lúc 08:03, hệ thống quản trị nhận sự kiện đã được đối chiếu cho thấy hộp thư có quyền truy cập trái phép; sự kiện được dịch vụ khôi phục tiếp nhận lúc 08:05. Lúc 08:06, một bên xuất trình token đặt lại hợp lệ và yêu cầu gỡ MFA.

Hãy phân tích:

1. Token hợp lệ chứng minh điều gì trong tình huống này?
2. Quyền đặt lại mật khẩu có cho phép gỡ MFA không?
3. Grant phát hành lúc 08:00 cần được xử lý thế nào khi nhận sự kiện lúc 08:05?
4. Nếu An vẫn có khóa bảo mật đăng ký từ trước, cần điều kiện gì để dùng phương thức đó?
5. Một email dự phòng tự chuyển tiếp về hộp thư bị ảnh hưởng có độc lập không?
6. Nếu An báo đã đổi mật khẩu email, hệ thống còn cần quyết định gì trước khi tái sử dụng kênh?
7. Nếu cảnh báo đến muộn sau khi tài khoản đã thay đổi, cần xem lại các session và thay đổi nào?

Thiết kế cần nêu rõ nguồn tín hiệu, mức tin cậy, hành động bị hạn chế, bằng chứng thay thế và cách xử lý giao dịch đang chờ. Việc ghi thêm một cờ cảnh báo mà không thay đổi quyết định cấp quyền chưa ngăn được chiếm đoạt tài khoản qua hộp thư.
