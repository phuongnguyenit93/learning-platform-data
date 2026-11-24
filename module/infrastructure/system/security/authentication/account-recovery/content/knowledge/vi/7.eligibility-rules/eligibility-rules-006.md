# Giới hạn khôi phục khi có thay đổi đang chờ xử lý

Trong chương **Eligibility Rules** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **pending change restrictions** là các quy tắc quyết định một yêu cầu khôi phục được phép làm gì khi tài khoản đang có thay đổi nhạy cảm chưa hoàn tất.

Thay đổi đó có thể là đổi email khôi phục, thay số điện thoại, thêm passkey, gỡ MFA hoặc một yêu cầu khôi phục khác đang chờ xem xét. Người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực vẫn có thể cần trợ giúp trong thời gian này. Tuy nhiên, đường khôi phục không được tự bỏ qua điều kiện của thay đổi đang chờ.

Vấn đề cốt lõi là phân biệt **đã yêu cầu thay đổi**, **đã xác minh một phần** và **đã có hiệu lực**. Một email mới nhận được mã xác minh chưa mặc nhiên có quyền đặt lại tài khoản. Một passkey mới chứng minh được khả năng ký chưa mặc nhiên được phép phê duyệt việc đăng ký chính nó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt dữ liệu có hiệu lực với dữ liệu ứng viên trong thay đổi đang chờ.
- Xác định thay đổi nào xung đột với một yêu cầu khôi phục.
- Giải thích vì sao bằng chứng kiểm soát email, số điện thoại hoặc authenticator mới chưa đủ để cấp toàn bộ quyền.
- Thiết kế giới hạn có phạm vi thay vì khóa mọi hoạt động khi có bất kỳ yêu cầu nào.
- Xử lý thời gian chờ, phê duyệt, hủy, hết hạn và thay đổi đồng thời.
- Ngăn việc sử dụng khôi phục để né điều kiện hoặc tự phê duyệt thay đổi nhạy cảm.

## 2. Thế nào là một thay đổi đang chờ?

Một thay đổi đang chờ là một giao dịch đã được hệ thống ghi nhận nhưng chưa đạt đủ điều kiện để áp dụng tác động cuối cùng. “Đang chờ” cần có ý nghĩa cụ thể, không chỉ là một cờ chung trên tài khoản.

| Trạng thái minh họa | Ý nghĩa | Điều chưa được suy ra |
| --- | --- | --- |
| Đã tạo yêu cầu | Có một đề xuất thay đổi | Người yêu cầu đã được xác minh |
| Chờ xác minh | Đang chờ bằng chứng hoặc hoàn thành kiểm tra | Giá trị mới được dùng cho khôi phục |
| Chờ thời điểm cho phép | Đã đạt một số điều kiện nhưng chưa tới thời điểm được thực hiện | Hết giờ sẽ tự thay đổi dù thiếu điều kiện khác |
| Chờ phê duyệt | Cần quyết định theo quy trình được hỗ trợ | Nhân viên bất kỳ được quyền bỏ qua kiểm tra |
| Đủ điều kiện thực hiện | Các điều kiện cấp quyền đã đạt trong phạm vi và thời hạn xác định | Mọi hành động khác trên tài khoản đều được cho phép |
| Đã áp dụng | Thay đổi đã được ghi nhận có hiệu lực | Những phiên, cache hoặc tác vụ liên quan đã được xử lý nếu hệ thống chưa bảo đảm điều đó |
| Đã hủy, hết hạn hoặc bị từ chối | Giao dịch không còn được dùng để thực hiện thay đổi | Có thể tiếp tục bằng một token cũ chỉ vì chữ ký còn đúng |

Các tên này là mô hình minh họa cho ứng dụng. Hệ thống thực tế cần định nghĩa điều kiện chuyển trạng thái, người hoặc thành phần được quyền chuyển và tác động đi kèm.

### Một yêu cầu gửi mã không đồng nghĩa có một thay đổi đã được phê duyệt

Bất kỳ ai biết email có thể thử bắt đầu đặt lại mật khẩu. Chỉ việc gửi mã không nên tự thay mật khẩu, gỡ MFA, đổi email hay đăng xuất mọi phiên.

Nếu mỗi yêu cầu công khai đều tạo một hạn chế rộng và kéo dài, đối thủ có thể liên tục gửi yêu cầu để ngăn chủ tài khoản sử dụng dịch vụ. Mức hạn chế cần phụ thuộc vào mức xác minh, độ tin cậy của sự kiện và loại tác động.

## 3. Dữ liệu có hiệu lực và dữ liệu ứng viên

Giả sử tài khoản đang dùng email khôi phục A và có yêu cầu chuyển sang B.

Một mô hình rõ ràng giữ riêng:

- **Giá trị có hiệu lực:** email A, cùng trạng thái và phạm vi tin cậy hiện tại.
- **Giá trị ứng viên:** email B được đề xuất trong một giao dịch cụ thể.
- **Bằng chứng:** những kiểm tra đã hoàn thành cho giao dịch đó.
- **Điều kiện còn thiếu:** phê duyệt, thời gian chờ hoặc xác minh bổ sung.
- **Kết quả cuối cùng:** giao dịch được áp dụng, bị hủy, hết hạn hoặc bị từ chối.

Không nên ghi đè email A bằng B ngay rồi chỉ đặt một cờ “chưa xác minh”. Một thành phần khác có thể chỉ đọc trường email và vô tình gửi liên kết khôi phục đến B.

Ngay cả khi cơ sở dữ liệu tách đúng, giao diện, API, hệ thống gửi thông báo và cache cũng phải đọc đúng nguồn dữ liệu. Việc một dịch vụ dùng giá trị ứng viên như giá trị có hiệu lực có thể phá toàn bộ điều kiện chờ.

### Chứng minh quyền kiểm soát giá trị mới có phạm vi hạn chế

Nhận được mã ở B giúp xác minh khả năng nhận thông tin tại B trong giao dịch tương ứng. Nó không tự chứng minh rằng người kiểm soát B có quyền thay tài khoản đang dùng A.

Tương tự, xác minh một passkey ứng viên có thể chứng minh quyền sử dụng credential đó. Quyền gắn credential vào tài khoản vẫn phải đến từ một quyết định hợp lệ khác theo chính sách.

Nguyên tắc là:

> Giá trị đang được đề xuất thay đổi không được tự trở thành căn cứ duy nhất để phê duyệt chính thay đổi hoặc một đường khôi phục phụ thuộc vào thay đổi đó.

Nếu sản phẩm có một quy trình khác chấp nhận người yêu cầu qua bằng chứng độc lập, quy trình đó có thể cấp quyền cho thay đổi. Căn cứ phải được ghi nhận rõ; không thể chỉ đổi tên bước xác minh email mới thành “xác minh chủ tài khoản”.

## 4. Những thay đổi thường ảnh hưởng đến khôi phục

| Thay đổi đang chờ | Rủi ro với yêu cầu khôi phục | Giới hạn minh họa |
| --- | --- | --- |
| Đổi email khôi phục | Đối thủ có thể muốn nhận liên kết đặt lại ở email ứng viên | Không dùng email ứng viên như kênh khôi phục có hiệu lực trước khi đạt điều kiện |
| Đổi số điện thoại | Số mới có thể bị dùng để gỡ MFA hoặc nhận mã khôi phục | Không mặc định số đã nhận mã là đủ quyền thay cấu hình bảo mật |
| Thêm passkey hoặc authenticator | Credential ứng viên có thể được dùng để phê duyệt việc đăng ký chính nó | Chưa cho credential đó quyền xác thực đầy đủ trước khi đăng ký được cấp quyền và áp dụng |
| Gỡ MFA | Một yêu cầu khác có thể cố đăng nhập như thể MFA đã bị gỡ | Giữ yêu cầu hiện hành cho tới khi thay đổi có hiệu lực, trừ hành động xử lý sự cố riêng được cho phép |
| Đặt lại mật khẩu | Nhiều token hoặc nhiều giao dịch có thể cạnh tranh thay cùng credential | Ràng buộc quyền với giao dịch, kiểm soát xung đột và tiêu thụ quyền một lần |
| Khôi phục qua xem xét | Người yêu cầu có thể thử đường tự phục vụ để né kết quả đang chờ | Áp dụng chính sách chung cho cùng phạm vi, không cho đổi đường để bỏ điều kiện |
| Thay kênh sau nghi bị chiếm | Kênh cũ và kênh mới đều có thể chưa đủ tin cậy | Chọn căn cứ theo quy trình xử lý sự cố; không mặc định một bên an toàn chỉ vì cũ hoặc mới |

Các giới hạn này là ví dụ thiết kế. Sản phẩm phải quyết định cụ thể đường nào được phép tiếp tục và đường nào cần thêm bằng chứng.

### Không giữ phương thức bị chiếm chỉ vì phương thức thay thế chưa hoạt động

Thông thường, yêu cầu thay đổi đang chờ chưa làm phương thức hiện hành tự mất hiệu lực. Nhưng nếu đã có căn cứ và quyền phù hợp để thu hồi một credential bị chiếm, việc thu hồi có thể cần thực hiện qua một hành động xử lý sự cố riêng.

Cần tách hai quyết định:

1. Có được vô hiệu hóa phương thức bị nghi hoặc đã xác định bị chiếm không?
2. Có được kích hoạt phương thức thay thế và cấp quyền truy cập mới không?

Quyền thực hiện quyết định thứ nhất không tự cấp quyết định thứ hai. Ngược lại, không nên tiếp tục dùng một kênh không còn đáng tin chỉ vì giao dịch thay kênh đang chờ.

## 5. Xác định xung đột theo tác động và quan hệ phụ thuộc

Không phải mọi thay đổi đang chờ đều phải chặn mọi yêu cầu khôi phục. Cần xác định chúng có cùng thay đổi một tài sản bảo mật hoặc phụ thuộc vào kết quả của nhau không.

Ví dụ:

- Hai giao dịch cùng thay email khôi phục xung đột trực tiếp.
- Một giao dịch thêm passkey và một giao dịch gỡ MFA có thể cùng làm thay đổi tập phương thức đăng nhập, nên cần đánh giá quan hệ giữa chúng.
- Đặt lại mật khẩu qua email B phụ thuộc vào giao dịch chuyển email sang B.
- Một sửa đổi tên hiển thị thông thường có thể không ảnh hưởng đến điều kiện khôi phục.

Có thể mô tả xung đột bằng ba câu hỏi:

1. Hai giao dịch có cùng thay một credential, kênh hoặc điều kiện truy cập không?
2. Giao dịch này có sử dụng kết quả chưa có hiệu lực của giao dịch kia làm bằng chứng không?
3. Áp dụng hai giao dịch theo thứ tự khác nhau có làm thay đổi quyền cuối cùng hoặc bỏ qua kiểm tra không?

Nếu câu trả lời là có, hệ thống cần một quy tắc xử lý rõ: tuần tự hóa, giữ lại để đánh giá, hủy một giao dịch theo quyền hoặc tạo một quy trình kết hợp được thiết kế trước.

### Không chỉ kiểm tra một cờ ở giao diện

Ẩn nút “đổi email” khi đang chờ không đủ nếu API khác vẫn cho thực hiện. Kiểm tra xung đột phải có ở phía máy chủ, tại nơi cấp quyền và nơi ghi thay đổi.

Một cờ “hasPendingChange” cũng quá thô nếu không cho biết thay đổi gì, ai tạo, đã xác minh đến đâu và còn hiệu lực đến khi nào. Cờ đó có thể vừa chặn nhầm việc hợp lệ, vừa bỏ sót xung đột quan trọng.

## 6. Giới hạn quyền trong thời gian chờ

Một thiết kế có thể cho tiếp tục một số thao tác và giữ lại những thao tác khác. Phạm vi này phụ thuộc chính sách của tài khoản và bối cảnh sự cố.

| Hoạt động | Cách đánh giá minh họa |
| --- | --- |
| Xem trạng thái giao dịch của mình | Có thể cho phép qua cơ chế truy cập có phạm vi phù hợp |
| Bổ sung bằng chứng cho đúng giao dịch | Có thể cho phép nếu đường đó được hỗ trợ và không làm thay đổi mục tiêu âm thầm |
| Gửi lại mã | Theo giới hạn, thời hạn và quy tắc hiệu lực của mã |
| Hủy giao dịch | Cần quyền hủy phù hợp; không chỉ dựa vào việc biết định danh tài khoản |
| Dùng email ứng viên để đặt lại tài khoản | Chưa cho phép chỉ vì email đã nhận mã xác minh ứng viên |
| Thêm một phương thức để phê duyệt giao dịch đang chờ | Không cho tự nâng quyền qua chính phương thức chưa được chấp nhận |
| Dùng một đường khác có bằng chứng độc lập | Đánh giá theo cùng chính sách xung đột, không tự coi là được phép hoặc bị cấm |
| Sử dụng phiên đã có | Xác định theo mức tin cậy và quyền của phiên; không mặc định mọi phiên đều bị khóa hoặc đều còn an toàn |
| Thay đổi nhạy cảm ngoài phạm vi | Cần quyền riêng và kiểm tra tác động đến giao dịch đang chờ |

Một phiên dùng để theo dõi khôi phục không nên mặc nhiên có quyền sử dụng toàn bộ tài khoản. Nếu hệ thống cấp một quyền giới hạn, quyền đó cần gắn với tài khoản, giao dịch, hành động và thời hạn cụ thể.

Đối với phiên đang tồn tại trước sự cố, cần đánh giá riêng. Việc có phiên không tự chứng minh người dùng muốn thay email, và việc có yêu cầu đang chờ cũng không tự đủ để người ngoài thu hồi mọi phiên của chủ tài khoản.

## 7. Thời gian chờ không thay thế bằng chứng

Một số chính sách dùng thời gian chờ để tạo cơ hội phát hiện hoặc phản ứng trước thay đổi nhạy cảm. Đây là một điều kiện bổ sung, không phải phép xác minh danh tính.

Cần định nghĩa ít nhất:

- Sự kiện nào bắt đầu thời gian chờ.
- Khi nào có thể thực hiện thay đổi.
- Giao dịch hết hạn lúc nào.
- Điều kiện nào phải còn đúng lúc thực hiện.
- Khi nào cần xác minh lại vì bằng chứng đã cũ hoặc bối cảnh đã thay đổi.
- Yêu cầu gửi lại, sửa mục tiêu hoặc tạo giao dịch khác ảnh hưởng thời gian ra sao.

Một biểu thức minh họa là:

~~~text
có_thể_thực_hiện =
    giao_dịch_đang_hoạt_động
    và now >= thời_điểm_cho_phép
    và now < thời_điểm_hết_hạn
    và bằng_chứng_đáp_ứng_chính_sách
    và phê_duyệt_bắt_buộc_đã_đạt
    và không_có_xung_đột_chưa_giải_quyết
    và tài_khoản_vẫn_đủ_điều_kiện
~~~

Thời điểm được tính từ nguồn thời gian phía máy chủ. Đồng hồ đếm ngược trên trình duyệt chỉ giúp người dùng theo dõi, không phải căn cứ cho API cấp quyền.

Không có một khoảng chờ chung phù hợp mọi dịch vụ. Cần lựa chọn theo loại thay đổi, giá trị tài khoản, khả năng phát hiện và tác động đến người dùng.

### Phân biệt hạn của bằng chứng với hạn của giao dịch

Một mã xác minh có thể hết hạn trước thời điểm kết thúc chờ. Sản phẩm cần định nghĩa bước xác minh đó tạo ra kết quả có hiệu lực trong bao lâu và có cần kiểm tra lại khi áp dụng không.

Không nên kéo dài hiệu lực mọi token chỉ để chúng sống qua khoảng chờ. Có thể ghi nhận kết quả xác minh theo phạm vi được phép, rồi yêu cầu bằng chứng mới khi chính sách cần. Việc này phải được thiết kế rõ, không suy luận tự động từ trạng thái “đã xác minh”.

### Tránh dùng thời gian chờ để gây mắc kẹt

Nếu một yêu cầu công khai mới luôn khởi động lại thời gian chờ của yêu cầu hợp lệ, đối thủ có thể trì hoãn khôi phục vô thời hạn. Nếu gửi lại mã tự rút ngắn thời gian chờ, đối thủ lại có thể vượt điều kiện.

Quy tắc cần gắn với giao dịch và mức quyền của người tạo sự kiện. Việc tạo yêu cầu chưa được xác minh không nên tự có quyền thay thế hoặc kéo dài mọi giao dịch đang được xử lý.

## 8. Hủy, hết hạn và thay đổi mục tiêu

### 8.1. Hủy giao dịch

Quyền hủy cần có phạm vi và điều kiện rõ. Biết email hoặc mã hồ sơ dễ đoán không nên đủ để hủy mọi yêu cầu của tài khoản khác.

Nếu sử dụng thông báo có khả năng phản đối hoặc hủy, cần xác định kênh nhận có còn đáng tin không và quyền đó được phép tác động tới đâu. Nó không được tự trở thành quyền thay credential hoặc đăng nhập.

Một phản đối từ kênh bị nghi chiếm có thể cần xem xét theo chính sách, thay vì tự quyết định toàn bộ quyền sở hữu tài khoản.

### 8.2. Hết hạn

Khi giao dịch hết hạn, những quyền thuộc giao dịch đó không còn được dùng để áp dụng thay đổi. Token có chữ ký đúng nhưng gắn với giao dịch đã hết hạn hoặc đã hủy vẫn phải bị từ chối.

Nếu cho bắt đầu lại, cần nói rõ bước nào phải thực hiện lại. Không tự mang toàn bộ kết quả cũ sang yêu cầu mới mà không có quy tắc về thời hạn, phạm vi và bối cảnh.

### 8.3. Sửa giá trị ứng viên

Đổi email ứng viên từ B sang C là thay đổi nội dung được phê duyệt. Bằng chứng xác minh B không tự đủ để kích hoạt C.

Giao dịch nên ràng buộc quyết định với nội dung thay đổi cụ thể và phiên bản tương ứng. Sửa mục tiêu phải làm các bằng chứng hoặc phê duyệt liên quan được đánh giá lại theo chính sách.

Cũng cần xử lý token cũ: nó không được áp dụng cho mục tiêu mới chỉ vì cùng mã giao dịch.

### 8.4. Đã áp dụng thì không còn là hủy yêu cầu

Khi thay đổi đã có hiệu lực, một thao tác “hủy” không tự đảo ngược toàn bộ tác động. Có thể cần một giao dịch mới hoặc quy trình xử lý sự cố.

Nếu yêu cầu hủy và yêu cầu áp dụng đến gần đồng thời, hệ thống phải có một kết quả cuối cùng nhất quán. Không được vừa báo hủy thành công vừa kích hoạt phương thức mới mà không kiểm soát.

## 9. Mô hình dữ liệu và kiểm tra phía máy chủ

Một giao dịch thay đổi nhạy cảm có thể cần các thuộc tính sau:

| Thuộc tính | Mục đích |
| --- | --- |
| Định danh tài khoản và phạm vi tổ chức | Không để quyền áp dụng sang tài khoản hoặc tổ chức khác |
| Loại hành động | Phân biệt thay email, gỡ MFA, thêm passkey hoặc đặt lại mật khẩu |
| Tham chiếu giá trị có hiệu lực | Xác định bối cảnh và phát hiện thay đổi bảo mật liên quan |
| Giá trị ứng viên hoặc tham chiếu được bảo vệ | Cố định nội dung thay đổi; chỉ lưu dữ liệu cần thiết |
| Trạng thái và phiên bản giao dịch | Kiểm soát chuyển trạng thái và yêu cầu đồng thời |
| Bằng chứng, nguồn phê duyệt và phạm vi | Biết điều kiện nào đã được đáp ứng cho thay đổi nào |
| Thời điểm cho phép và hết hạn | Kiểm tra điều kiện thời gian phía máy chủ |
| Phiên bản chính sách hoặc trạng thái bảo mật liên quan | Hỗ trợ đánh giá lại khi điều kiện thay đổi |
| Lý do hủy, từ chối hoặc áp dụng | Kiểm toán mà không ghi bí mật |

Đây là mô hình khái niệm, không phải yêu cầu phải lưu toàn bộ dữ liệu dưới một bảng duy nhất. Token, mã, khóa riêng hoặc bí mật xác thực không được ghi vào log chỉ để tiện theo dõi.

### Mã giả áp dụng thay đổi

~~~text
applyPendingChange(transactionId, presentedAuthorization, now):
    begin consistent update

    change = loadAndProtectChange(transactionId)
    account = loadAndProtectRelevantAccountState(change.accountId)

    require change.state allows execution
    require now >= change.availableAt
    require now < change.expiresAt

    require presentedAuthorization:
        is bound to change.id
        is bound to account.id and account.tenantId
        is bound to change.action and change.payloadVersion
        is still valid and not consumed

    require account is currently eligible for change.action
    require current policy accepts the evidence and approvals
    require no unresolved conflicting change
    require no required restriction has been bypassed

    consume execution authorization once
    apply the exact approved change
    mark change as applied
    record required follow-up work consistently

    commit consistent update
~~~

Mã giả mô tả yêu cầu về tính nhất quán, không chỉ định một cơ chế lưu trữ cụ thể. Triển khai thực tế có thể dùng khóa, phiên bản hoặc cơ chế tương ứng để ngăn các yêu cầu đồng thời vượt điều kiện.

Đối với thao tác đã hoàn tất, một lần gửi lại có thể trả kết quả hiện có nếu thiết kế cho phép, nhưng không được thực hiện lại tác động bằng quyền một lần đã dùng.

Kiểm tra trước ở giao diện hoặc ở đầu hành trình không đủ. Những điều kiện ảnh hưởng đến quyền phải được kiểm tra ở thời điểm thực hiện thay đổi.

## 10. Dòng trạng thái minh họa

~~~mermaid
flowchart TD
    A[Yêu cầu thay đổi] --> B[Chờ xác minh trong phạm vi]
    B --> C{Đủ bằng chứng ban đầu?}
    C -- Chưa --> B
    C -- Có --> D[Chờ thời điểm hoặc phê duyệt nếu chính sách yêu cầu]
    D --> E{Mọi điều kiện hiện tại đều đạt?}
    E -- Chưa và còn được tiếp tục --> D
    E -- Có --> F[Đủ điều kiện thực hiện]
    F --> G[Kiểm tra lại và cập nhật nhất quán]
    G --> H[Đã áp dụng]
    B --> I[Đã hủy hoặc hết hạn]
    D --> I
    F --> I
    D --> J[Bị từ chối hoặc chuyển xử lý sự cố]
~~~

Một nút “đủ điều kiện thực hiện” có thể chỉ tồn tại trong thời gian ngắn hoặc được biểu diễn bằng quyền có hạn. Nó không phải trạng thái bỏ qua các thay đổi mới của tài khoản.

Những chuyển trạng thái như hủy, hết hạn và áp dụng phải được giải quyết bằng dữ liệu có thẩm quyền phía máy chủ. Trình duyệt mở tab cũ không được quyết định giao dịch vẫn đang chờ hay đã hoàn tất.

## 11. Khôi phục khi có thay đổi đang chờ: ba tình huống

### Tình huống A: Email mới được xác minh nhưng chưa có hiệu lực

An yêu cầu đổi email từ A sang B. An đã xác minh nhận mã ở B, nhưng giao dịch vẫn chờ điều kiện phê duyệt theo chính sách minh họa của dịch vụ.

Một yêu cầu đặt lại mật khẩu xuất hiện và muốn nhận liên kết ở B.

Hệ thống không được coi B là kênh khôi phục có hiệu lực chỉ vì B đã nhận mã. Nó đánh giá đường khôi phục dựa trên trạng thái hiện tại và những kênh được phép.

Nếu A bị báo không còn an toàn, không nhất thiết quay về A như một căn cứ duy nhất. Cần chọn đường xử lý sự cố có bằng chứng phù hợp. Kết quả không được là tự kích hoạt B để “giải quyết nhanh”.

### Tình huống B: Gỡ MFA đang chờ, người dùng thử đường khác

Bình báo mất điện thoại và có giao dịch gỡ TOTP đang chờ xem xét. Sau đó Bình bắt đầu đặt lại mật khẩu qua email.

Theo chính sách minh họa, đặt lại mật khẩu có thể được phép mà vẫn giữ yêu cầu MFA hiện hành. Đường mới không được tự hoàn tất việc gỡ TOTP hoặc cấp một phiên toàn quyền chỉ vì mật khẩu đã thay.

Nếu Bình còn một authenticator độc lập được chấp nhận, hệ thống có thể đánh giá đường đó theo chính sách. Việc chuyển đường không tự là gian lận, nhưng cũng không được dùng để bỏ qua xung đột hoặc điều kiện của thay đổi đang chờ.

### Tình huống C: Thay đổi và hủy đến đồng thời

Chi có giao dịch thêm passkey đã đạt điều kiện. Một yêu cầu áp dụng và một yêu cầu hủy có quyền phù hợp đến gần cùng lúc.

Máy chủ phải quyết định nhất quán theo trạng thái và quy tắc cập nhật. Nếu hủy đã có hiệu lực trước khi áp dụng được chấp nhận, quyền không còn được dùng. Nếu thay đổi đã áp dụng, giao diện phải phản ánh kết quả đó và hướng tới đường xử lý tiếp theo.

Không được để một dịch vụ báo “đã hủy” trong khi dịch vụ khác vẫn kích hoạt credential ứng viên từ dữ liệu cũ.

## 12. Ngoại lệ và xử lý sự cố

Có thể có tình huống người dùng cần khôi phục khẩn cấp trong khi giao dịch đang chờ. Nếu sản phẩm hỗ trợ ngoại lệ, ngoại lệ phải là một đường có điều kiện và thẩm quyền cụ thể.

Một ngoại lệ cần xác định:

- Ai hoặc thành phần nào được quyết định.
- Bằng chứng nào cho phép thay đổi cách xử lý.
- Điều kiện nào vẫn bắt buộc.
- Giao dịch cũ được giữ, hủy hay thay thế bằng cách nào.
- Quyền nào được cấp và những hạn chế nào tiếp tục tồn tại.
- Cách ghi nhận quyết định và thông báo phù hợp.

Nhân viên hỗ trợ không nên tự sửa trực tiếp dữ liệu có hiệu lực để né trạng thái chờ. Nếu được phép xử lý, hành động đó phải đi qua cơ chế thực thi và ghi nhận tương ứng.

Chờ đủ lâu, có câu chuyện thuyết phục hoặc không ai phản đối không tự chứng minh quyền sở hữu. Một email mới có thể nhận thông tin liên lạc của hồ sơ, nhưng không vì thế tự trở thành kênh khôi phục đáng tin của tài khoản.

Nếu thành phần đánh giá chính sách hoặc trạng thái giao dịch đang lỗi, hệ thống nên giữ lại việc cấp quyền nhạy cảm và xử lý như tình trạng chưa đánh giá được. Không tự coi thiếu dữ liệu là không có thay đổi đang chờ.

## 13. Giao diện, thông báo và quan sát vận hành

Người dùng cần biết họ đang chờ điều gì, có thể làm gì và kết quả nào chưa xảy ra. Nội dung hiển thị nên mô tả tác động thực tế.

| Tránh diễn đạt | Diễn đạt chính xác hơn theo trạng thái |
| --- | --- |
| “Email đã đổi” khi chỉ mới xác minh email ứng viên | “Email mới đã được xác minh; yêu cầu đổi email vẫn đang chờ hoàn tất.” |
| “MFA đã tắt” khi đang chờ duyệt | “Yêu cầu thay đổi MFA đang được xử lý; các yêu cầu đăng nhập hiện tại vẫn áp dụng theo chính sách.” |
| “Hết giờ là tự vào được” khi còn thiếu bằng chứng | “Sau thời điểm này, bạn có thể tiếp tục nếu các điều kiện còn lại được đáp ứng.” |
| “Mọi thiết bị đã đăng xuất” khi tác vụ thu hồi chưa hoàn tất | Chỉ thông báo phạm vi đã thực thi; hiển thị trạng thái còn lại nếu cần |
| “Hủy thành công” khi thay đổi đã áp dụng trước đó | Nêu trạng thái thực tế và hướng dẫn cách xử lý tiếp |

Điểm công khai không nên tiết lộ tài khoản có tồn tại, đang chờ đổi email sang đâu hoặc có những authenticator nào. Việc xem trạng thái chi tiết cần cơ chế truy cập có phạm vi phù hợp.

Thông báo có thể giúp phát hiện thay đổi trái phép. Nhưng không nên nhúng bí mật, token xác thực rộng hoặc thông tin nhạy cảm không cần thiết vào nội dung thông báo.

Theo dõi vận hành có thể ghi nhận:

- Thời gian chờ theo từng loại giao dịch.
- Số yêu cầu bị giữ vì xung đột.
- Số lần dùng token của giao dịch đã hủy hoặc đã hoàn tất.
- Trường hợp quyền được cấp nhưng điều kiện tài khoản thay đổi trước khi áp dụng.
- Độ trễ của tác vụ thu hồi phiên và cập nhật những thành phần liên quan.
- Dấu hiệu một nguồn liên tục tạo yêu cầu để kéo dài hoặc làm gián đoạn khôi phục.

Không ghi OTP, mã dự phòng, cookie hoặc token dùng được vào log. Thông tin kiểm toán cần đủ giải thích quyết định, với quyền truy cập và thời hạn lưu phù hợp.

## 14. Các lỗi cần tránh

| Lỗi | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Ghi đè kênh hiện hành bằng kênh ứng viên quá sớm | Thành phần khác có thể dùng kênh chưa được cấp quyền | Tách dữ liệu có hiệu lực khỏi dữ liệu đang đề xuất |
| Cho email ứng viên tự phê duyệt thay email | Người yêu cầu tự tạo nguồn bằng chứng để chiếm quyền | Dùng căn cứ sở hữu được chính sách chấp nhận ngoài việc nhận mã ở kênh mới |
| Chỉ kiểm tra thời gian chờ | Có thể bỏ qua phê duyệt, bằng chứng hoặc trạng thái đã thay đổi | Kiểm tra đồng thời toàn bộ điều kiện |
| Mọi yêu cầu công khai đều khóa rộng tài khoản | Đối thủ có thể gây từ chối dịch vụ | Áp dụng giới hạn theo mức xác minh và phạm vi rủi ro |
| Đường đặt lại mật khẩu tự gỡ MFA đang chờ | Một nhánh yếu hơn làm mất tác dụng kiểm soát | Giữ quyền đặt lại mật khẩu và quyền thay MFA riêng |
| Chỉ chặn ở giao diện | API khác hoặc tab cũ vẫn có thể thực hiện | Thực thi điều kiện tại máy chủ |
| Sửa mục tiêu nhưng giữ nguyên bằng chứng và token | Quyền phê duyệt B có thể bị dùng để kích hoạt C | Ràng buộc với nội dung và phiên bản thay đổi |
| Tin token còn chữ ký đúng sau khi hủy | Quyền đã thu hồi vẫn bị sử dụng | Kiểm tra trạng thái có thẩm quyền và tiêu thụ quyền một lần |
| Hủy và áp dụng không nhất quán | Trạng thái thông báo khác trạng thái credential | Bảo vệ cập nhật đồng thời và phản ánh đúng kết quả |
| Hỗ trợ bỏ điều kiện bằng sửa dữ liệu trực tiếp | Tạo đường vượt chính sách không kiểm soát | Thiết kế ngoại lệ có phạm vi, thẩm quyền và kiểm toán |

## 15. Danh sách kiểm tra khi thiết kế giới hạn

Một đặc tả rõ ràng cần trả lời được:

- Những loại thay đổi nào được coi là nhạy cảm và có trạng thái chờ?
- Giá trị ứng viên được tách khỏi giá trị có hiệu lực ở mọi thành phần liên quan chưa?
- Bằng chứng nào chứng minh quyền kiểm soát giá trị mới, và bằng chứng nào cấp quyền thay tài khoản?
- Một yêu cầu khôi phục xung đột với giao dịch đang chờ theo tiêu chí nào?
- Trong lúc chờ, hoạt động nào được phép và hoạt động nào cần giữ lại?
- Thời gian chờ bắt đầu từ sự kiện nào, khi nào hết hạn và khi nào phải xác minh lại?
- Tạo yêu cầu mới hoặc gửi lại mã có thể gây kéo dài, rút ngắn hoặc thay thế giao dịch không?
- Hủy, áp dụng, hết hạn và sửa mục tiêu được xử lý nhất quán ra sao?
- Nếu nghi phương thức hiện hành bị chiếm, việc thu hồi và việc cấp phương thức mới có được quyết định riêng không?
- Giao diện và thông báo có mô tả đúng phần đã xảy ra và phần còn chờ không?

Giới hạn đối với thay đổi đang chờ bảo vệ khoảng thời gian mà cấu hình bảo mật chưa ổn định. Mục tiêu là cho người dùng tiếp tục theo một đường có căn cứ, giữ đúng phạm vi quyền và chỉ áp dụng thay đổi khi toàn bộ điều kiện hiện tại đã được đáp ứng.