# Compromise notification — Thông báo khi tài khoản có dấu hiệu bị chiếm đoạt

## 1. Vai trò trong luồng khôi phục tài khoản

Compromise notification là thông báo giúp chủ tài khoản nhận biết một sự kiện có thể liên quan đến truy cập trái phép và biết cách phản hồi an toàn. Trong khôi phục tài khoản, sự kiện đó có thể là yêu cầu thay MFA không quen thuộc, thêm passkey sau recovery, đổi địa chỉ khôi phục hoặc xác nhận một phiên truy cập do kẻ tấn công kiểm soát.

Một thông báo hữu ích phải trả lời được bốn câu hỏi:

1. Điều gì đã xảy ra, vào thời điểm nào?
2. Hệ thống biết chắc điều gì và còn nghi ngờ điều gì?
3. Biện pháp bảo vệ nào đã có hiệu lực?
4. Người nhận nên làm gì nếu họ không thực hiện thao tác?

Thông báo là một lớp phát hiện và phối hợp ứng phó. Nó không tự chứng minh người đọc là chủ tài khoản, không thay thế xác minh danh tính và không tự thu hồi session hay phương thức xác thực.

**Ví dụ:** Một người mất điện thoại yêu cầu khôi phục MFA. Nếu một passkey mới được thêm sau khi recovery hoàn tất, chủ tài khoản cần có cơ hội phát hiện việc thêm đó qua kênh thông báo phù hợp. Chỉ hiển thị “khôi phục thành công” trong trình duyệt đang thực hiện recovery sẽ bỏ sót chủ tài khoản khi chính trình duyệt ấy do kẻ tấn công điều khiển.

NIST SP 800-63B-4 mô tả thông báo độc lập cho các sự kiện như gắn phương thức xác thực và khôi phục tài khoản; thông báo cần có hướng dẫn cùng thông tin liên hệ để người nhận phản đối sự kiện. Khi áp dụng chuẩn này, cần đọc đầy đủ yêu cầu về địa chỉ và phương thức gửi trong [Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-notifications).

Các mô hình sự kiện, mẫu câu và cách tổ chức hàng đợi dưới đây là phương án thiết kế minh họa cho dịch vụ khôi phục tài khoản, không phải schema bắt buộc của chuẩn.

## 2. Phân biệt sự kiện với kết luận chiếm đoạt

Cùng một thao tác có thể xuất hiện trong recovery hợp lệ hoặc trong tấn công. Thông báo nên tách **sự kiện quan sát được**, **đánh giá rủi ro** và **kết quả xử lý**.

| Tình huống | Điều đã biết | Cách diễn đạt phù hợp |
| --- | --- | --- |
| Có yêu cầu khôi phục mật khẩu | Có người gửi yêu cầu; chưa xác định người gửi | “Đã có yêu cầu khôi phục mật khẩu.” |
| Recovery xuất hiện tín hiệu bất thường | Hệ thống phát hiện dấu hiệu cần kiểm tra | “Chúng tôi phát hiện hoạt động khôi phục cần bạn kiểm tra.” |
| Phương thức MFA được thay thế | Thay đổi đã được ghi nhận thành công | “Phương thức xác thực hai bước đã được thay đổi.” |
| Chủ tài khoản báo không thực hiện thao tác | Có phản hồi phủ nhận; cần xử lý theo độ tin cậy của phản hồi | “Chúng tôi đã tiếp nhận báo cáo hoạt động không được bạn cho phép.” |
| Có bằng chứng xác định truy cập trái phép | Sự kiện đã được xác nhận trong phạm vi bằng chứng | “Chúng tôi xác nhận đã có truy cập không được phép vào tài khoản.” |

Không suy từ một địa chỉ IP lạ, trình duyệt mới hoặc vị trí khác thường thành kết luận chắc chắn “tài khoản đã bị hack”. VPN, mạng di động và thiết bị mới có thể tạo ra tín hiệu tương tự.

Ngược lại, nếu đã xác nhận có truy cập trái phép, câu “có một hoạt động nhỏ” làm giảm mức độ nghiêm trọng và khiến người dùng không hiểu vì sao cần hành động.

Mỗi thông báo nên bám vào một sự kiện chính. Nếu có nhiều bước liên quan, trình bày dòng thời gian trong trung tâm bảo mật, thay vì ghép chúng thành một câu mơ hồ như “tài khoản có thay đổi”.

## 3. Tách thông báo công khai khỏi cảnh báo gửi chủ tài khoản

Màn hình nhập email khôi phục thường chưa xác thực người dùng. Phản hồi ở đây không được trở thành công cụ kiểm tra một email có tài khoản hay không.

Ví dụ phản hồi công khai:

> Nếu thông tin bạn nhập phù hợp với tài khoản có thể khôi phục, chúng tôi sẽ gửi hướng dẫn qua kênh đã đăng ký.

Nội dung cảnh báo chi tiết chỉ đi qua kênh thông báo đã được lựa chọn hoặc giao diện có quyền truy cập phù hợp. Không hiển thị trên màn hình công khai rằng “tài khoản này đang bị điều tra”, “người dùng có ba passkey” hoặc “email dự phòng là…”.

OWASP khuyến nghị phản hồi nhất quán cho yêu cầu quên mật khẩu và kiểm soát việc gửi hàng loạt để tránh dò tài khoản, gây ngập hộp thư. Xem [Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Việc gửi một cảnh báo cũng không đồng nghĩa hệ thống đã chấp nhận yêu cầu recovery. Trong nội dung cần phân biệt rõ:

- **Đã nhận yêu cầu:** chưa thay mật khẩu hoặc phương thức xác thực.
- **Đang chờ xử lý:** còn bước xác minh hoặc khoảng chờ theo chính sách.
- **Đã hoàn tất thay đổi:** trạng thái mới đã có hiệu lực.
- **Đã áp dụng bảo vệ:** chỉ mô tả những hành động hệ thống thực sự hoàn tất.

## 4. Chọn kênh khi thông tin liên hệ cũng có thể bị chiếm đoạt

Một kẻ tấn công có thể đổi email hoặc số điện thoại trước khi thực hiện recovery. Nếu cảnh báo chỉ gửi tới địa chỉ vừa được thay, chính người cần được bảo vệ sẽ không nhận được nó.

Khi thiết kế lựa chọn kênh, cần lưu được nguồn gốc và lịch sử thay đổi địa chỉ thông báo: địa chỉ được xác minh khi nào, thay bằng giao dịch nào, đã bị người dùng báo mất quyền kiểm soát hay chưa. Việc “đang nằm trong hồ sơ” không tự chứng minh kênh đó còn an toàn.

| Kênh | Giá trị sử dụng | Giới hạn cần tính đến |
| --- | --- | --- |
| Email thông báo đã đăng ký | Tiếp cận người dùng ngoài phiên đang recovery | Hộp thư có thể bị chiếm quyền hoặc có quy tắc chuyển tiếp |
| Push tới thiết bị đã đăng ký | Có thể tiếp cận thiết bị khác với thiết bị đang recovery | Thiết bị có thể bị mất; nội dung có thể hiện trên màn hình khóa |
| SMS tới số đã đăng ký | Hữu ích khi người dùng không có phiên ứng dụng | Có thể bị SIM swap, chuyển tiếp hoặc tái cấp số |
| Trung tâm bảo mật trong ứng dụng | Hiển thị lịch sử và trạng thái mới nhất | Người dùng đã mất toàn bộ quyền truy cập có thể không mở được |

Nhiều kênh chỉ đem lại lợi ích độc lập nếu chúng không cùng phụ thuộc vào một điểm đã mất kiểm soát. Email và ứng dụng email trên cùng điện thoại bị đánh cắp không mặc nhiên tạo thành hai đường liên lạc độc lập.

Trong ví dụ triển khai, hệ thống chụp danh sách kênh thông báo phù hợp trước một thay đổi nhạy cảm, đồng thời áp dụng chính sách hiện hành về địa chỉ nhận. Cần kiểm tra lại các dấu hiệu kênh không an toàn trước mỗi lần gửi lại. Snapshot giúp giữ bằng chứng về lựa chọn ban đầu, nhưng không cho phép bỏ qua thông tin mới.

Không gửi tùy tiện đến mọi địa chỉ lịch sử: một email cũ có thể đã bị thu hồi hoặc thuộc người khác. Việc giữ địa chỉ cũ để cảnh báo một thay đổi và việc khôi phục địa chỉ đó thành phương thức recovery là hai quyết định có rủi ro khác nhau.

Nếu không còn kênh có thể dùng an toàn, ghi nhận tình trạng này và chuyển sang luồng hỗ trợ phù hợp. Không tự hạ mức xác minh chỉ vì cảnh báo không gửi được.

## 5. Nội dung tối thiểu và mức tiết lộ

Một cấu trúc thông báo thực dụng gồm năm phần:

1. **Tiêu đề mô tả sự kiện:** đủ rõ để nhận biết, tránh gây hoảng loạn.
2. **Sự kiện và thời gian:** thao tác nào, đã xảy ra hay còn chờ, kèm múi giờ.
3. **Ngữ cảnh nhận diện vừa đủ:** loại thiết bị, trình duyệt hoặc khu vực gần đúng nếu có ích.
4. **Trạng thái bảo vệ:** việc đã xong, việc đang chờ và giới hạn còn lại.
5. **Hướng dẫn phản hồi:** đường vào ứng dụng chính thức và cách báo không nhận ra hoạt động.

Thời gian nên phản ánh lúc sự kiện xảy ra, không thay bằng thời gian thư được gửi. Một thư bị chậm cần cho phép người nhận phân biệt hai thời điểm.

Thông tin thiết bị và địa điểm chỉ hỗ trợ nhận diện. Tên thiết bị do người dùng đặt có thể không đáng tin; dữ liệu vị trí từ IP có thể sai. Cần chuẩn hóa, giới hạn độ dài và escape nội dung đưa vào HTML để dữ liệu đầu vào không biến thành nội dung giả trong thông báo.

Không đưa mật khẩu, OTP, mã recovery, bí mật TOTP, token session, tài liệu định danh hoặc liên kết cấp quyền khôi phục vào cảnh báo sự cố. Nếu quy trình có thư cấp mã recovery riêng, phân biệt rõ mục đích của thư đó với cảnh báo.

Mức chi tiết có thể thay đổi theo bề mặt:

| Bề mặt hiển thị | Nội dung minh họa |
| --- | --- |
| Màn hình khóa | “Có hoạt động bảo mật cần kiểm tra. Mở ứng dụng để xem.” |
| Email cảnh báo | Loại thay đổi, thời điểm, trạng thái bảo vệ và hướng dẫn vào trung tâm bảo mật |
| Trung tâm bảo mật có kiểm soát truy cập | Dòng thời gian, phương thức bị ảnh hưởng, các lựa chọn xử lý được cấp phép |

Che một phần email giúp giảm tiết lộ nhưng không bảo đảm ẩn danh. Mã sự kiện cũng chỉ nên là mã tra cứu không mang quyền, không phải ID tuần tự có thể dùng để xem hồ sơ của người khác.

## 6. Hai nhánh hướng dẫn cho người nhận

### Khi người nhận đã thực hiện thao tác

Hướng dẫn nên ngắn và nêu điều kiện cụ thể:

> Nếu bạn đã thay phương thức xác thực vào thời điểm trên, hãy mở ứng dụng để kiểm tra phương thức mới. Bạn không cần trả lời thư này.

Nếu còn bước bắt buộc, cần nói rõ. Ví dụ, không thể ghi “không cần làm gì” khi người dùng vẫn phải thiết lập lại MFA hoặc hoàn tất xác minh.

### Khi người nhận không thực hiện hoặc không chắc chắn

Đưa ra một hành động chính, dễ tìm:

> Hãy mở ứng dụng từ biểu tượng quen thuộc, vào Bảo mật → Hoạt động gần đây và chọn “Tôi không thực hiện thao tác này”.

Nếu người dùng không đăng nhập được, phải có đường hỗ trợ từ trang chính thức. Không buộc họ dùng đúng phương thức MFA vừa bị mất để báo rằng tài khoản có thể đang bị chiếm đoạt.

Tiếp nhận báo cáo và cấp quyền thay đổi tài khoản có thể có mức xác minh khác nhau. Có thể nhận thông tin nghi vấn trước, nhưng việc đổi email, gỡ phương thức xác thực hoặc chuyển quyền tài khoản cần đáp ứng chính sách tương ứng. Người có một bản sao email cảnh báo không mặc nhiên được làm các việc đó.

Tránh lời đe dọa như “bấm ngay trong 30 giây nếu không tài khoản sẽ bị xóa”. Nếu tồn tại thời hạn thật, trình bày thời hạn tuyệt đối, múi giờ và hậu quả đúng với trạng thái hệ thống.

## 7. Nút “Tôi không thực hiện” không được trở thành lỗ hổng mới

Liên kết trong thư có thể bị hệ thống quét thư, trình xem trước hoặc trình duyệt truy cập tự động. Vì vậy, một yêu cầu GET mở trang cảnh báo không nên tự đổi trạng thái tài khoản.

Một luồng minh họa:

~~~mermaid
flowchart TD
    A[Người nhận mở cảnh báo] --> B[Trang thông tin trên tên miền chính thức]
    B --> C[Chọn báo không nhận ra hoạt động]
    C --> D[Tiếp nhận báo cáo và đánh giá độ tin cậy]
    D --> E{Loại hành động}
    E --> F[Biện pháp bảo vệ giới hạn theo rủi ro]
    E --> G[Xác minh bổ sung cho thay đổi nhạy cảm]
    F --> H[Ghi sự kiện và phản hồi trạng thái]
    G --> H
~~~

Nếu sản phẩm có token riêng cho việc báo sự cố, token đó cần tách khỏi token recovery, giới hạn mục đích, thời hạn và số lần sử dụng. Mở trang không tiêu thụ token hay thực hiện thay đổi; hành động xác nhận diễn ra qua yêu cầu riêng, được bảo vệ phù hợp với cách xác thực của endpoint.

Token báo sự cố có thể cho phép gửi một tín hiệu hoặc yêu cầu bảo vệ giới hạn. Nó không nên cho phép chọn mật khẩu mới, thêm passkey hay thay địa chỉ nhận mã. Cũng không được đổi token đó thành session đăng nhập đầy đủ.

Một biện pháp tạm ngưng ít tác động vẫn cần đánh giá nguy cơ bị lạm dụng gây từ chối dịch vụ. Một người ngoài gửi báo cáo không được tùy ý khóa vĩnh viễn tài khoản của người khác. Mức bảo vệ tự động phải dựa trên bằng chứng, tác động và khả năng phục hồi.

Sau khi tiếp nhận, giao diện cần phân biệt “đã nhận báo cáo” với “đã thu hồi quyền truy cập”. Không hiển thị kết quả thứ hai khi mới tạo một công việc trong hàng đợi.

## 8. Mẫu thông báo theo trạng thái

Các tên sản phẩm, thời điểm và mã sự kiện dưới đây chỉ để minh họa. Trạng thái bảo vệ trong mẫu chỉ được sử dụng khi đúng với kết quả thực tế.

### Mẫu A — Thay đổi MFA đã hoàn tất, chưa có kết luận chiếm đoạt

~~~text
Tiêu đề: Phương thức xác thực hai bước đã được thay đổi

Vào 14:10 ngày 23/11/2026 (UTC+07:00), phương thức xác thực
hai bước của tài khoản p***@example.com đã được thay đổi.

Nếu bạn đã thực hiện thao tác, hãy mở ứng dụng để kiểm tra
phương thức mới.

Nếu bạn không thực hiện hoặc không chắc chắn, hãy mở ứng dụng
từ biểu tượng quen thuộc, vào Bảo mật → Hoạt động gần đây
và chọn “Tôi không thực hiện thao tác này”.

Nếu không đăng nhập được, hãy vào mục Trợ giúp trên trang chính
thức của dịch vụ để báo sự cố. Đội hỗ trợ không yêu cầu bạn đọc
OTP, mật khẩu hay mã recovery qua thư hoặc điện thoại.

Mã sự kiện: SEC-R8M4
Mã này chỉ dùng để tra cứu khi liên hệ hỗ trợ.
~~~

OWASP xem việc thay MFA là thao tác rủi ro cao, khuyến nghị xác thực lại và gửi thông báo qua kênh ngoài giao dịch. Cảnh báo trong mẫu không thay thế các kiểm soát đó. Xem [Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

### Mẫu B — Đã xác nhận sự cố, một phần xử lý còn đang chạy

~~~text
Tiêu đề: Cần kiểm tra bảo mật sau truy cập không được phép

Chúng tôi xác nhận có truy cập không được phép vào tài khoản
của bạn vào 14:18 ngày 23/11/2026 (UTC+07:00).

Passkey được thêm trong sự kiện này đã bị vô hiệu hóa.
Việc kết thúc các phiên truy cập cũ đang được xử lý.
Bạn có thể xem trạng thái mới nhất trong Trung tâm bảo mật.

Hãy mở ứng dụng chính thức và làm theo hướng dẫn khôi phục
tài khoản. Nếu bạn không truy cập được, sử dụng mục Trợ giúp
trên trang chính thức và cung cấp mã sự kiện SEC-K2V7.

Không gửi mật khẩu, OTP hoặc mã recovery cho người liên hệ
tự nhận là nhân viên hỗ trợ.
~~~

Mẫu B không hứa “tài khoản đã hoàn toàn an toàn”. Vô hiệu hóa một passkey không tự chứng minh rằng các session, refresh token, phương thức recovery và quyền truy cập khác đều đã được xử lý.

Mỗi dịch vụ có phạm vi session và token khác nhau. Thông báo chỉ được nói “đã kết thúc tất cả phiên” khi cơ chế thu hồi thực tế đáp ứng lời khẳng định đó, kể cả các giới hạn phân tán hoặc token còn hiệu lực.

## 9. Ghép trạng thái bảo vệ với việc gửi thông báo

Trong một thiết kế hướng sự kiện, dữ liệu tối thiểu có thể được chia thành ba lớp:

| Lớp | Ví dụ dữ liệu | Mục đích |
| --- | --- | --- |
| Sự kiện bảo mật | eventId, accountId nội bộ, occurredAt, loại sự kiện, mức xác nhận | Ghi lại điều đã xảy ra |
| Hành động bảo vệ | loại hành động, trạng thái, completedAt, phạm vi | Xác định điều được phép khẳng định |
| Lần gửi thông báo | kênh, người nhận nội bộ, templateVersion, attempt, providerStatus | Theo dõi việc truyền tải |

Một sự kiện có thể có nhiều hành động bảo vệ và nhiều lần gửi. Không dùng một biến “success” chung cho cả thay đổi tài khoản, thu hồi session và gửi email.

Ví dụ giả mã dưới đây minh họa transactional outbox khi thay đổi trạng thái và bản ghi outbox cùng nằm trong một cơ sở dữ liệu:

~~~text
transaction:
    event = recordSecurityEvent(observedFacts)

    completedAction = applyLocalProtection()
    protectionState = persistProtectionResult(completedAction)

    recipients = selectRecipientsUsingNotificationPolicy(event)
    insertOutbox(event.id, recipients, protectionState.version)
commit

dispatcher:
    claimPendingOutboxItem()
    loadCurrentEventAndProtectionState()
    recheckRecipientSafetyAndAuthorization()
    renderApprovedTemplate()
    sendNotification()
    recordProviderOutcome()
~~~

Outbox giúp tránh trường hợp thay đổi đã commit nhưng tiến trình chết trước khi ghi việc cần gửi. Nó không bảo đảm thư chỉ xuất hiện đúng một lần và không đưa thao tác của dịch vụ bên ngoài vào cùng giao dịch cơ sở dữ liệu.

Nếu thu hồi session ở một dịch vụ khác, kết quả ban đầu có thể là “đang xử lý”. Chỉ sau khi có bằng chứng hoàn tất mới tạo cập nhật trạng thái tương ứng. Không trì hoãn cảnh báo quan trọng chỉ để chờ mọi biện pháp kết thúc; có thể thông báo ngay kết quả hiện có rồi cập nhật sau.

Một khóa chống trùng minh họa là:

~~~text
(eventId, recipientInternalId, channel, notificationPurpose, protectionVersion)
~~~

Khóa này giúp phân biệt gửi lại cùng thông báo với cập nhật có ý nghĩa. Nó không nên dùng địa chỉ liên hệ thô làm dữ liệu quan sát công khai. Nếu nhà cung cấp không hỗ trợ chống trùng và xảy ra timeout sau khi nhận thư, vẫn có thể xuất hiện bản gửi trùng; cần thiết kế nội dung để trường hợp đó không gây hiểu nhầm thành một sự cố mới.

Thông báo đến trễ nên hiển thị thời điểm sự kiện và chỉ dẫn xem trạng thái mới nhất. Không gửi lại mẫu “đang xử lý” như thể đó là trạng thái hiện tại khi hệ thống đã có kết quả mới.

## 10. Gửi thất bại, chống ngập và quan sát vận hành

Không đồng nhất các trạng thái truyền tải:

- **Đã xếp hàng:** có công việc cần gửi.
- **Nhà cung cấp đã chấp nhận:** nhà cung cấp nhận yêu cầu.
- **Có tín hiệu chuyển phát:** nhận callback hoặc kết quả tương ứng.
- **Người dùng phản hồi:** có hành động được ghi nhận qua luồng sản phẩm.

Ngay cả tín hiệu chuyển phát cũng không chứng minh chủ tài khoản đã đọc. Việc tải ảnh theo dõi hoặc nhấp liên kết có thể do proxy và bộ quét tự động thực hiện; không dùng chúng làm bằng chứng xác minh danh tính.

Với lỗi tạm thời, có thể retry với backoff, jitter và giới hạn. Với địa chỉ không hợp lệ hoặc kênh đã bị báo mất quyền kiểm soát, cần chuyển sang trạng thái xử lý phù hợp thay vì lặp vô hạn. Callback của nhà cung cấp phải được xác thực; dữ liệu callback không có quyền sửa trạng thái bảo vệ tài khoản.

Chống ngập cần tách hai nhóm:

| Nhóm | Cách kiểm soát minh họa |
| --- | --- |
| Yêu cầu recovery chưa xác thực, lặp lại | Hạn chế theo tài khoản, nguồn và mẫu hành vi; gộp thông báo phù hợp |
| Sự kiện đã xác nhận hoặc thay đổi nhạy cảm mới | Ưu tiên riêng; tránh bị hạn mức của nhóm yêu cầu lặp che khuất |

Kẻ tấn công có thể gửi hàng loạt yêu cầu nhẹ để làm người dùng bỏ qua cảnh báo thật. Vì vậy, một hạn mức chung kiểu “mỗi tài khoản chỉ nhận một thư mỗi ngày” có thể khiến sự kiện quan trọng không được thông báo.

Các chỉ số vận hành hữu ích gồm độ trễ từ sự kiện đến lúc xếp hàng, độ trễ gửi, tỷ lệ lỗi theo kênh, số công việc gửi quá hạn và số báo cáo phủ nhận chưa được xử lý. Mục tiêu thời gian cần được định nghĩa theo mức rủi ro của dịch vụ; không coi một mốc minh họa là yêu cầu chung cho mọi sản phẩm.

Log nên ghi mã sự kiện, phiên bản mẫu và trạng thái xử lý. Hạn chế ghi nguyên nội dung thư, địa chỉ đầy đủ hoặc chi tiết điều tra; không ghi bí mật xác thực. Quyền xem log và thời gian lưu cần phù hợp với dữ liệu được thu thập.

## 11. Ví dụ xuyên suốt: recovery bị lợi dụng để thêm passkey

Giả sử Mai mất điện thoại. Trong lúc Mai tìm cách khôi phục tài khoản, một người khác giành quyền vào hộp thư của cô và thực hiện recovery để thêm passkey mới.

**Bước 1 — Nhận yêu cầu:** Màn hình công khai trả phản hồi thống nhất. Nội bộ ghi nhận yêu cầu và tín hiệu rủi ro, chưa khẳng định có chiếm đoạt và chưa coi yêu cầu đó là lý do đủ để đổi MFA.

**Bước 2 — Có thay đổi nhạy cảm:** Sau khi quy trình cho phép thêm passkey, hệ thống tạo sự kiện gắn phương thức xác thực. Việc cảnh báo được xử lý riêng với giao dịch thêm passkey; chỉ thông báo trong chính phiên đó sẽ không giúp Mai phát hiện.

**Bước 3 — Liên hệ qua kênh phù hợp:** Nếu một thiết bị khác vẫn có kênh push an toàn, Mai có thể nhận cảnh báo ở đó. Email đang bị kiểm soát không được coi là bằng chứng độc lập chỉ vì thư đã được chuyển phát thành công.

**Bước 4 — Mai báo không thực hiện:** Báo cáo được tiếp nhận với mã sự kiện. Hệ thống đánh giá bằng chứng để áp dụng biện pháp bảo vệ; việc trả quyền sở hữu và thay lại phương thức recovery vẫn đi qua quy trình xác minh phù hợp.

**Bước 5 — Thông báo tiến trình:** Nếu passkey đã vô hiệu hóa nhưng session cũ chưa được thu hồi xong, nội dung phải phản ánh hai trạng thái khác nhau. Khi hoàn tất, trung tâm bảo mật cập nhật kết quả và hướng dẫn kiểm tra những thay đổi liên quan.

Ví dụ này cho thấy một thông báo rõ ràng chỉ phát huy tác dụng khi có đường phản hồi sử dụng được và trạng thái phía máy chủ đáng tin. Chủ tài khoản đã mất quyền đăng nhập vẫn cần một cách báo sự cố; người đang giữ session cũng không tự được coi là chủ tài khoản hợp lệ.

## 12. Những quyết định cần ghi rõ trong thiết kế

Để người viết nội dung và người triển khai hiểu cùng một hợp đồng, tài liệu thiết kế nên xác định:

- Sự kiện nào kích hoạt cảnh báo, mức xác nhận nào được phép dùng từng cách diễn đạt.
- Chính sách chọn người nhận và xử lý địa chỉ vừa thay đổi, địa chỉ cũ, kênh bị nghi xâm phạm.
- Những trạng thái bảo vệ nào được phép khẳng định là hoàn tất.
- Đường báo không nhận ra hoạt động cho người còn đăng nhập và người đã mất quyền truy cập.
- Quyền cụ thể của liên kết báo sự cố, cùng cách ngăn hành động ngoài ý muốn do bộ quét thư.
- Cách xử lý gửi chậm, gửi trùng, gửi thất bại và cập nhật trạng thái sau cảnh báo đầu tiên.
- Mức dữ liệu được phép xuất hiện trên từng kênh và trong log vận hành.

Các quyết định này nối nội dung thông báo với hành vi thật của dịch vụ khôi phục. Người dùng cần biết điều đã xảy ra, điều đã được bảo vệ và bước tiếp theo họ có thể thực hiện một cách an toàn.
