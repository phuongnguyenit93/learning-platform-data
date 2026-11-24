# Phishing report handling — Xử lý báo cáo lừa đảo trong khôi phục tài khoản

## 1. Vì sao báo cáo phishing là một phần của thiết kế khôi phục tài khoản?

Một người dùng nhận được thư “Passkey của bạn đã bị vô hiệu hóa, hãy khôi phục ngay”. Họ báo cáo thư đó cho bộ phận hỗ trợ. Nếu nhân viên lập tức đổi email khôi phục sang địa chỉ người báo cáo cung cấp, chính quy trình xử lý báo cáo đã trở thành đường chiếm đoạt tài khoản.

**Phishing report handling** là quy trình tiếp nhận, phân tích, ứng phó và phản hồi khi có dấu hiệu giả mạo nhằm đánh cắp thông tin hoặc điều khiển hành động của người dùng. Trong khôi phục tài khoản, đối tượng bị nhắm tới có thể là mật khẩu, mã MFA, recovery code, liên kết đặt lại mật khẩu, phiên đăng nhập hoặc quyết định của nhân viên hỗ trợ.

Quy trình cần đồng thời đạt ba mục tiêu:

- Giúp người dùng báo cáo sớm, kể cả khi họ đã mất quyền đăng nhập.
- Ngăn thiệt hại tiếp diễn dựa trên bằng chứng và thẩm quyền phù hợp.
- Giữ nguyên yêu cầu xác minh danh tính trước khi khôi phục hoặc gắn phương thức xác thực mới.

Một báo cáo là **tín hiệu sự cố**, không phải bằng chứng rằng người gửi sở hữu tài khoản được nhắc đến. Mã tiếp nhận báo cáo cũng không phải recovery token.

Bài học này tập trung vào vòng đời báo cáo và mối liên hệ với luồng khôi phục; các trạng thái, thời hạn và dữ liệu mẫu bên dưới là phương án thiết kế minh họa.

## 2. Thiết kế kênh tiếp nhận mà người dùng có thể tìm thấy an toàn

### 2.1. Có đường báo cáo khi không đăng nhập được

Cung cấp mục báo cáo trên website hoặc ứng dụng chính thức, đồng thời có hướng dẫn tìm lại kênh này từ trang trợ giúp. Người bị mất thiết bị MFA hoặc bị kẻ tấn công đăng xuất vẫn phải gửi được cảnh báo.

Tách hai khả năng:

| Khả năng | Có thể cho phép khi chưa đăng nhập? | Giới hạn |
| --- | --- | --- |
| Gửi mẫu thư, mô tả sự việc | Có | Không trả thông tin riêng của tài khoản |
| Nhận xác nhận đã tiếp nhận | Có | Chỉ xác nhận đã nhận báo cáo |
| Xem bằng chứng, thiết bị hoặc lịch sử tài khoản | Không mặc định | Cần kiểm tra quyền truy cập |
| Thu hồi toàn bộ phiên hoặc thay MFA theo yêu cầu cá nhân | Không chỉ dựa vào biểu mẫu | Cần xác minh hoặc quyết định ứng phó được cấp quyền |
| Gắn passkey, đổi địa chỉ khôi phục | Không | Phải qua chính sách xác minh riêng |

Không bắt người dùng mở liên kết trong chính thư đáng ngờ để đến trang báo cáo. Nếu hỗ trợ qua điện thoại, hướng dẫn họ lấy số liên hệ từ ứng dụng hoặc website đã biết; không dùng số ghi trong thư làm căn cứ tin cậy.

### 2.2. Hỏi về hành động đã xảy ra

Biểu mẫu nên hỏi bằng ngôn ngữ dễ hiểu:

1. Bạn chỉ nhận thư/tin nhắn hay đã mở liên kết?
2. Bạn có nhập mật khẩu, mã MFA hoặc recovery code không?
3. Bạn có chấp thuận thông báo đăng nhập, quét QR hoặc cấp quyền cho ứng dụng không?
4. Bạn có tải, mở tệp hoặc cài phần mềm không?
5. Bạn còn truy cập được tài khoản và phương thức xác thực nào?
6. Sự việc diễn ra lúc nào, theo múi giờ nào?

Cho phép lựa chọn “Không rõ”. Không ép người dùng đoán rằng mình đã bị chiếm tài khoản hay chưa.

Có thể hiển thị ngay thông điệp:

> Đã nhận báo cáo. Hãy ngừng tương tác với nội dung đáng ngờ và tự mở ứng dụng hoặc website chính thức để kiểm tra. Không gửi mật khẩu, OTP, recovery code hay liên kết khôi phục còn hiệu lực vào phần mô tả. Nếu đã nhập thông tin hoặc chấp thuận đăng nhập, hãy chọn đúng hành động để đội hỗ trợ ưu tiên xử lý.

Không yêu cầu người dùng làm lại thao tác nguy hiểm để quay video hoặc chứng minh sự cố.

### 2.3. Chống lạm dụng kênh báo cáo

Giới hạn tốc độ, kích thước tệp, số lần gửi lại và chi phí xử lý theo nguồn gửi. Khi có chiến dịch lớn, gộp các mẫu giống nhau để giảm tải nhưng giữ riêng thông tin về từng người đã tương tác.

Phản hồi công khai cần có nội dung và hành vi đủ nhất quán để không tiết lộ email có tài khoản hay không. Nếu có trang theo dõi, dùng quyền truy cập riêng; mã hồ sơ không tự cấp quyền đọc nội dung nhạy cảm. Báo cáo trùng có thể được ghi nhận là bằng chứng bổ sung, không nhất thiết tạo một sự cố mới.

## 3. Thu thập bằng chứng tối thiểu nhưng có ích

Mục tiêu là tái dựng được điều đã xảy ra mà không tạo thêm kho chứa bí mật xác thực.

| Nhóm dữ liệu | Ví dụ hữu ích | Điều cần tránh |
| --- | --- | --- |
| Thời gian | Thời điểm nhận thư, tương tác, phát hiện; múi giờ | Chỉ ghi “hôm qua” |
| Kênh tấn công | Email, SMS, cuộc gọi, QR, trang giả mạo | Mặc định mọi báo cáo đều là email |
| Mẫu gốc | Thư gốc với header khi có thể thu thập an toàn | Chỉ giữ ảnh chụp đã mất thông tin định tuyến |
| Hành động của người dùng | Đã nhập mật khẩu, mã dùng một lần, cấp quyền | Yêu cầu nhập lại chính bí mật đã lộ |
| Dữ liệu liên kết nội bộ | ID yêu cầu khôi phục, sự kiện đăng nhập, phiên | Sao chép cookie hoặc token vào ticket |
| Thay đổi sau sự việc | MFA mới, email khôi phục mới, phiên lạ | Coi mọi thay đổi mới đều do chủ tài khoản thực hiện |

Địa chỉ From, Reply-To và tên hiển thị có thể khác nhau; lưu đúng từng trường nếu có. Kết quả SPF, DKIM hoặc DMARC là một phần của phân tích nguồn thư, không đủ để kết luận nội dung an toàn. Thư phát ra từ hộp thư thật đã bị chiếm vẫn có thể vượt qua kiểm tra xác thực miền.

Phân biệt hai lớp lưu trữ:

- **Kho bằng chứng hạn chế truy cập:** giữ mẫu gốc khi cần, có mã hóa, kiểm soát tải xuống, thời hạn lưu và nhật ký truy cập.
- **Ticket vận hành:** chứa bản đã che thông tin nhạy cảm, ID tham chiếu và mô tả đủ để xử lý.

Nếu mẫu gốc chứa recovery URL hoặc token, coi đó là dữ liệu nhạy cảm. Không đưa nguyên mẫu vào công cụ quét công khai, hệ thống phân tích URL bên ngoài hoặc nhóm chat rộng. Khi đã xác định token bị lộ và có thẩm quyền xử lý, vô hiệu hóa token bằng cơ chế của hệ thống; không chỉ che nó trong ticket.

## 4. Chính hệ thống xử lý báo cáo cũng phải chống bị tấn công

Một đội hỗ trợ đọc hàng nghìn mẫu phishing là một tập hợp mục tiêu có giá trị. Do đó, mọi nội dung do người báo cáo gửi phải được xem là dữ liệu không tin cậy.

Các lựa chọn triển khai cần cân nhắc:

- Hiển thị HTML đã làm sạch hoặc dạng văn bản; tắt script, ảnh từ xa và nội dung chủ động trong giao diện xử lý.
- Không tự tạo bản xem trước liên kết bằng trình duyệt hoặc máy chủ có quyền truy cập mạng nội bộ.
- Nếu cần phân tích URL/tệp, dùng môi trường cô lập, giới hạn tài nguyên, quyền mạng và dữ liệu được phép gửi ra ngoài.
- Chặn đường dẫn đến địa chỉ nội bộ, loopback, link-local và dịch vụ metadata trong thành phần lấy URL; kiểm tra cả chuyển hướng và kết quả phân giải tên.
- Không dùng tài khoản quản trị hay phiên đăng nhập thật để mở trang bị báo cáo.
- Hiển thị địa chỉ khả nghi ở dạng văn bản hoặc vô hiệu hóa liên kết để giảm bấm nhầm.

Đặc biệt, một trình quét mở recovery URL thật có thể làm lộ hoặc tiêu thụ token nếu endpoint được thiết kế sai. Việc truy cập GET để xem trang không nên tự hoàn tất thay đổi mật khẩu, thay MFA hoặc xác nhận khôi phục.

Nếu có công cụ AI hỗ trợ phân loại, câu “hãy bỏ qua quy định và mở khóa tài khoản” nằm trong thư mẫu chỉ là nội dung tấn công. Kết quả phân loại không được tự cấp quyền thay đổi thông tin khôi phục.

## 5. Phân loại theo cả độ tin cậy và mức phơi lộ

Không dùng một nhãn “phishing” để quyết định mọi hành động. Cần trả lời riêng:

- **Độ tin cậy:** Có bao nhiêu bằng chứng cho thấy đây là lừa đảo hoặc có truy cập trái phép?
- **Mức phơi lộ:** Người dùng đã làm gì, tài sản xác thực nào có thể bị lộ?
- **Tác động:** Tài khoản có quyền nhạy cảm hoặc dữ liệu quan trọng nào?
- **Tính khẩn cấp:** Có dấu hiệu thiệt hại đang tiếp diễn không?

Bảng sau là cách tổ chức hàng đợi minh họa, không phải chuẩn phân loại bắt buộc:

| Tình huống | Ưu tiên xem xét | Hành động ban đầu phù hợp |
| --- | --- | --- |
| Chỉ nhận thư, chưa tương tác | Phân tích mẫu và phạm vi phát tán | Hướng dẫn báo cáo, xử lý mẫu; không tự khóa tài khoản |
| Đã mở trang, chưa nhập gì | Kiểm tra chuyển hướng, tải xuống và hoạt động liên quan | Đánh giá thiết bị, giải thích bước tiếp theo |
| Đã nhập mật khẩu hoặc mã xác thực | Khả năng lộ thông tin hoặc có phiên trái phép | Chuyển nhanh sang điều tra tài khoản và biện pháp ứng phó được phép |
| Đã cấp quyền cho ứng dụng | Khả năng có quyền truy cập kéo dài | Kiểm tra grant, phạm vi quyền và hoạt động của ứng dụng |
| Có phiên lạ, thay MFA hoặc đổi email khôi phục trái phép | Sự cố tài khoản có khả năng đang diễn ra | Ưu tiên cô lập, điều tra và mở hồ sơ khôi phục độc lập |
| Đã cài phần mềm đáng ngờ | Có thể liên quan cả thiết bị và danh tính | Phối hợp đội thiết bị, dùng môi trường sạch cho khôi phục |

“Mở liên kết” chưa đủ chứng minh tài khoản bị chiếm. Ngược lại, “không nhập mật khẩu” chưa đủ loại trừ rủi ro: người dùng có thể đã cấp quyền cho ứng dụng hoặc phê duyệt một yêu cầu đăng nhập.

Không đợi phân tích xong toàn bộ chiến dịch mới bảo vệ tài khoản đang có bằng chứng truy cập trái phép. Nhưng cũng không dùng một báo cáo chưa xác minh để khóa tài khoản của người khác.

## 6. Tách trạng thái báo cáo, sự cố và khôi phục

Ba đối tượng có vòng đời khác nhau:

| Đối tượng | Câu hỏi nó trả lời | Trạng thái minh họa |
| --- | --- | --- |
| Báo cáo | Đã tiếp nhận và phân loại mẫu chưa? | RECEIVED, TRIAGED, DUPLICATE, CLOSED |
| Sự cố | Thiệt hại đã được ngăn và xử lý chưa? | INVESTIGATING, CONTAINMENT_PENDING, CONTAINED, REMEDIATED |
| Yêu cầu khôi phục | Người yêu cầu đã chứng minh quyền kiểm soát chưa? | EVIDENCE_PENDING, VERIFIED, REBIND_PENDING, COMPLETED |

~~~mermaid
flowchart TD
    A[Báo cáo được tiếp nhận] --> B[Phân loại mẫu và mức phơi lộ]
    B --> C{Có bằng chứng cần bảo vệ tài khoản?}
    C -->|Chưa đủ| D[Thu thập thêm và hướng dẫn an toàn]
    C -->|Có| E[Ứng phó theo thẩm quyền]
    E --> F[Theo dõi kết quả từng hành động]
    F --> G{Người dùng cần khôi phục?}
    G -->|Có| H[Xác minh độc lập theo chính sách]
    H --> I[Khôi phục và kiểm tra quyền truy cập]
    G -->|Không| J[Theo dõi và phản hồi]
    I --> J
    D --> J
~~~

Báo cáo có thể được đóng vì đã gộp vào một sự cố khác trong khi sự cố vẫn đang điều tra. Tài khoản cũng có thể đã được cô lập nhưng chưa xác minh được người yêu cầu khôi phục.

Không viết logic “ticket CLOSED thì mở khóa tài khoản”. Đóng ticket là quyết định quản lý công việc; khôi phục quyền truy cập là quyết định bảo mật có điều kiện riêng.

Mỗi trạng thái cần có người hoặc dịch vụ chịu trách nhiệm, lý do chuyển trạng thái, thời điểm và bằng chứng tham chiếu. Các mốc tiếp nhận, ra quyết định, thực thi và xác nhận hiệu lực phải được ghi riêng.

## 7. Bảo vệ tài khoản theo loại tài sản bị ảnh hưởng

### 7.1. Phân biệt ngăn truy cập và trả lại quyền kiểm soát

Khi có căn cứ và thẩm quyền ứng phó, đội bảo mật có thể cần ngăn phiên đáng ngờ tiếp tục hoạt động trước khi hoàn thành xác minh chủ tài khoản. Quyền này thuộc quy trình ứng phó, không đến từ việc người gửi báo cáo nói “đây là tài khoản của tôi”.

Đặt lại mật khẩu đơn lẻ có thể chưa loại bỏ quyền truy cập của kẻ tấn công. OWASP khuyến nghị xem xét cả phiên hiện có, phương thức xác thực, thông tin khôi phục và các liên kết hoặc mã khôi phục còn tồn tại khi xử lý tài khoản nghi bị chiếm. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

### 7.2. Liệt kê phạm vi thực thi thay vì chỉ ghi “đã revoke”

Một kế hoạch ứng phó có thể phải xem xét:

| Tài sản | Câu hỏi cần trả lời |
| --- | --- |
| Phiên web/mobile | Phiên nào bị thu hồi? Có cần chấm dứt toàn bộ phiên không? |
| Refresh token | Token còn đổi được access token mới không? |
| Access token | Resource server đã từ chối token cũ hay token vẫn sống tới khi hết hạn? |
| Luồng khôi phục đang mở | Token cũ hoặc phiên hạn chế có tiếp tục đổi thông tin không? |
| Authenticator | MFA, passkey hoặc recovery code nào bị lộ hay được thêm trái phép? |
| Liên kết ứng dụng | Có grant hoặc credential nào cho phép truy cập độc lập với mật khẩu không? |
| Kênh khôi phục | Email, số điện thoại, recovery contact có bị thay đổi trái phép không? |

Không phải mọi hệ thống có cùng khả năng thu hồi. Với JWT tự chứa, việc xóa cookie hoặc thu hồi refresh token không tự khiến mọi resource server từ chối access token đã phát hành. Cần nêu rõ cơ chế như kiểm tra phiên bản phiên, danh sách thu hồi, kiểm tra trực tuyến hoặc khoảng hiệu lực còn lại; đánh giá độ trễ truyền thay đổi giữa các dịch vụ.

Thu hồi phiên cần có tác động phía máy chủ phù hợp; xóa dữ liệu trên trình duyệt của nạn nhân không làm mất bản token kẻ tấn công đã lấy được. [Nguồn: OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Trong sự cố hộp thư, còn phải điều tra MFA lạ, ứng dụng được cấp quyền, vai trò và quy tắc chuyển tiếp thư. Đây là những ví dụ Microsoft đưa vào quy trình xử lý tài khoản email bị chiếm; khi áp dụng cho hệ thống khác phải đối chiếu các cơ chế tương đương. [Nguồn: Microsoft Learn](https://learn.microsoft.com/en-us/defender-office-365/responding-to-a-compromised-email-account).

### 7.3. Xác nhận hiệu lực

“Đã gửi yêu cầu thu hồi” khác “đã thu hồi thành công”. Nếu dịch vụ quản lý phiên lỗi hoặc một vùng triển khai chưa nhận thay đổi, trạng thái phải phản ánh công việc đang chờ.

Ghi nhận phạm vi đã bảo vệ, phần chưa hoàn tất, lần thử lại và người tiếp quản. Biện pháp tạm thời như chặn hành động nhạy cảm phải có điều kiện kích hoạt, thẩm quyền và điều kiện gỡ bỏ rõ ràng.

## 8. Xử lý hai trường hợp dễ nhầm lẫn

### 8.1. Thư khôi phục thật nhưng người dùng không yêu cầu

Thư được phát ra từ hệ thống thật có thể là kết quả của một người khác nhập email vào biểu mẫu quên mật khẩu. Điều đó chưa chứng minh mật khẩu, hộp thư hay tài khoản đã bị chiếm.

Đối chiếu với nhật ký phát thông báo và yêu cầu khôi phục nội bộ. Xem xét tần suất, nguồn, thời điểm và hành động tiếp theo. Phản hồi qua kênh an toàn rằng người dùng không cần làm theo yêu cầu không do mình khởi tạo; không biến số lượng yêu cầu khôi phục thành lý do tự động đổi mật khẩu hoặc khóa tài khoản.

Nếu mẫu đã làm lộ token thật, đội có thẩm quyền có thể hủy đúng token hoặc yêu cầu liên quan. Không cần mở chính liên kết đó để kiểm tra nó còn dùng được hay không.

### 8.2. Thư giả và người dùng đã làm theo

Tập trung vào hành động thực tế. Nếu người dùng đưa OTP cho trang giả và xuất hiện phiên mới, việc OTP đã hết hạn không loại bỏ phiên đã được tạo.

Nếu người dùng bị lừa mở trang cấp quyền thật cho một ứng dụng độc hại, chỉ chặn tên miền giả hoặc đổi mật khẩu có thể bỏ sót grant đã được cấp. Điều tra quyền truy cập thực tế tương ứng với hành động, thay vì chỉ phân tích hình thức của thư.

Không trả lời “an toàn” chỉ vì tên miền trang đăng nhập là thật, hoặc vì người dùng đang sử dụng passkey. Luồng hỗ trợ, quyền ứng dụng, thiết bị và phiên vẫn cần được đánh giá.

## 9. Chuyển sang khôi phục mà không tạo đường vòng qua xác thực

### 9.1. Bằng chứng báo cáo không thay thế bằng chứng sở hữu

Ảnh chụp thư, tên tài khoản, ID ticket, thông tin công khai và số điện thoại người gọi cung cấp đều có thể do kẻ tấn công biết hoặc tạo ra.

Khi cần cấp lại quyền truy cập:

- Dùng phương thức khôi phục đã được thiết lập và được chính sách chấp nhận.
- Không chỉ dựa vào email hoặc số điện thoại vừa được thêm trong giai đoạn nghi có xâm nhập.
- Không tự khôi phục mọi địa chỉ cũ; địa chỉ đó có thể đã bị thay vì bị mất hoặc bị chiếm.
- Không gửi liên kết khôi phục sang địa chỉ mới chỉ vì người gọi nói hộp thư cũ không dùng được.
- Nếu nghi thiết bị hiện tại bị xâm nhập, hướng dẫn thực hiện bước nhạy cảm trên thiết bị hoặc môi trường đáng tin cậy.

NIST SP 800-63B-4 phân biệt khôi phục tài khoản với thay authenticator khi người dùng vẫn xác thực được bằng phương thức khác. Tài liệu cũng mô tả các nhóm phương thức khôi phục và yêu cầu thông báo khi khôi phục xảy ra. Việc lựa chọn tổ hợp bằng chứng phải phù hợp chính sách bảo đảm của tài khoản. [Nguồn: NIST SP 800-63B-4, Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery).

Không tự đặt yêu cầu “gửi giấy tờ tùy thân là đủ” cho tài khoản trước đây chưa gắn với danh tính được xác minh. Một danh tính thật chưa chắc liên kết với tài khoản đang tranh chấp.

### 9.2. Giữ đúng ý nghĩa của phishing resistance

OTP, recovery code hoặc email link vẫn có thể bị người dùng đưa cho trang giả. Dùng chúng trong một quy trình được kiểm soát không biến bản thân phương thức đó thành xác thực chống phishing.

NIST mô tả khả năng chống phishing dựa trên ràng buộc mật mã với kênh hoặc tên bên xác minh; việc nhập tay đầu ra xác thực không cung cấp ràng buộc này. [Nguồn: NIST SP 800-63B-4, Phishing Resistance](https://pages.nist.gov/800-63-4/sp800-63b.html#phishing-resistance).

Sau khi khôi phục thành công, việc gắn lại MFA hoặc passkey phải đi qua luồng được cấp quyền, đồng thời xử lý phương thức trái phép và tạo thông báo phù hợp. Không tự đăng ký passkey từ thiết bị của nhân viên hỗ trợ. Nếu có phiên khôi phục hạn chế, phiên đó chỉ nên làm được những hành động cần thiết cho quá trình đã được phê duyệt.

### 9.3. Phản hồi mà không tạo thêm mồi phishing

Thông báo trạng thái nên giải thích điều đã làm, điều còn chờ và cách tự mở kênh chính thức để tiếp tục. Không đặt nội dung gây hoảng loạn hoặc yêu cầu gửi bí mật vào email.

Không coi địa chỉ nhận phản hồi do người báo cáo cung cấp là địa chỉ thông báo đã được xác minh của tài khoản. Với hộp thư nghi bị chiếm, đánh giá lại độ an toàn của kênh trước khi đưa thông tin nhạy cảm vào đó.

## 10. Mô hình dữ liệu và xử lý backend minh họa

### 10.1. Dữ liệu báo cáo không chứa quyền khôi phục

~~~json
{
  "reportId": "pr_example_1042",
  "incidentId": "inc_example_77",
  "sourceChannel": "PUBLIC_REPORT_FORM",
  "receivedAt": "2026-11-23T08:15:00Z",
  "reporterAssurance": "UNVERIFIED",
  "exposure": ["PASSWORD_ENTERED", "MFA_APPROVED"],
  "evidenceRef": "restricted-evidence/example-1042",
  "triageStatus": "TRIAGED",
  "accountBindingStatus": "INTERNAL_CORRELATION_REQUIRED"
}
~~~

Đây là dữ liệu nội bộ đã tối giản. Không đưa mật khẩu, recovery code, cookie, URL chứa token hoặc nội dung giấy tờ vào sự kiện dùng chung. ID bằng chứng không phải URL tải xuống công khai.

Nếu cho phép người gửi nhập email liên quan, lưu đó là **thông tin được khai báo**, không phải liên kết sở hữu đã xác nhận. Việc gắn báo cáo vào tài khoản nội bộ cần có lý do và kiểm tra quyền; không tiết lộ kết quả đối chiếu qua API công khai.

### 10.2. Tiếp nhận và ứng phó là hai thao tác riêng

~~~text
receiveReport(input):
    validateSizeAndShape(input)
    applySubmissionAbuseControls(input.source)
    evidenceRef = evidenceStore.acceptRestricted(input.sample)

    transaction:
        report = reports.create(
            reporterAssurance = UNVERIFIED,
            claimedAccount = input.claimedAccount,
            evidenceRef = evidenceRef
        )
        outbox.append(ReportReceived(report.id))

    return genericReceipt(report.receiptId)
~~~

Thao tác này không đổi mật khẩu, email khôi phục hay MFA; không khóa tài khoản chỉ theo trường email đầu vào.

Một quyết định ứng phó cần thêm bước được cấp quyền:

~~~text
authorizeContainment(incidentId, assessment, actor):
    requireIncidentResponsePermission(actor)
    requireSupportedAccountCorrelation(assessment)
    requireEvidenceAndReason(assessment)

    transaction:
        incident = incidents.lock(incidentId)
        decision = decisions.createOnce(
            incident,
            assessment.evidenceRefs,
            assessment.actions,
            actor
        )
        outbox.appendOnce(ContainmentRequested(decision.id))
        incident.moveTo(CONTAINMENT_PENDING)

applyContainment(decisionId):
    decision = decisions.loadAuthorized(decisionId)

    for action in decision.actions:
        executeWithStableIdempotencyKey(decision.id, action.id)
        recordActionResult(action)

    if allRequiredActionsHaveConfirmedEffect(decision):
        markIncidentContained(decision.incidentId)
    else:
        keepPendingAndEscalateUnresolvedActions(decision)
~~~

Đây là mã giả mô tả ranh giới trách nhiệm, không phải triển khai hoàn chỉnh. Mẫu outbox giúp ghi quyết định và việc cần phát trong cùng giao dịch cơ sở dữ liệu; không làm các dịch vụ bên ngoài trở thành một giao dịch nguyên tử.

Cần khóa hoặc kiểm soát phiên bản khi quyết định cạnh tranh; ràng buộc duy nhất cho khóa chống lặp; cơ chế retry và tiếp quản khi lỗi. Worker nhận sự kiện phải dùng quyết định đã được phê duyệt, không lấy danh sách hành động tùy ý từ báo cáo công khai.

Tác vụ hủy token và hoàn tất khôi phục cũng có thể chạy đồng thời. Chúng cần cùng kiểm tra trạng thái, phiên bản hoặc dấu mốc vô hiệu hóa tại điểm commit; việc đánh dấu “đã hủy” ở một bản sao đọc chậm không đủ để chặn luồng còn lại.

## 11. Ví dụ xuyên suốt: người dùng mất quyền truy cập sau thư giả

Linh nhận thư giả “Thiết bị MFA hết hạn”, nhập mật khẩu và chấp thuận một yêu cầu đăng nhập. Sau đó, một phương thức MFA lạ được thêm vào tài khoản.

| Thời điểm minh họa | Sự kiện | Quyết định xử lý |
| --- | --- | --- |
| 09:00 | Linh nhận và làm theo thư | Chưa có báo cáo; cần giữ được nhật ký liên quan |
| 09:05 | Linh gửi báo cáo từ trang chính thức | Cấp mã tiếp nhận, ghi nhận hành động; không gửi recovery link đến email mới trong biểu mẫu |
| 09:08 | Điều tra phát hiện phiên và MFA lạ trùng khoảng sự việc | Đội có quyền ứng phó phê duyệt biện pháp bảo vệ |
| 09:10 | Một dịch vụ thu hồi phiên chưa trả thành công | Giữ trạng thái đang chờ, tiếp quản lỗi; không thông báo đã chặn xong |
| 09:20 | Linh hoàn thành phương thức xác minh độc lập được chấp nhận | Tiến hành khôi phục và gắn lại phương thức trong luồng chính thức |
| Sau đó | Các biện pháp bắt buộc đã có kết quả, quyền truy cập được xác nhận | Phản hồi, theo dõi tái xâm nhập và đánh giá điều kiện đóng sự cố |

Trong lúc xử lý, một người khác gọi đến, nêu đúng mã ticket và yêu cầu gửi recovery code qua số điện thoại mới. Nhân viên ghi thêm thông tin nhưng không thay đổi kênh khôi phục. Biết mã ticket không nâng mức xác minh của người gọi.

Sau khi Linh lấy lại tài khoản, đội xử lý vẫn cần xem các thay đổi trái phép và công việc chưa hoàn tất. Việc Linh đăng nhập thành công không tự chứng minh mọi quyền truy cập của kẻ tấn công đã bị loại bỏ.

## 12. Trách nhiệm, tiêu chí đóng và chỉ số vận hành

### 12.1. Có người chịu trách nhiệm cho từng quyết định

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Bộ phận tiếp nhận | Hướng dẫn an toàn, ghi nhận đủ dữ liệu, chuyển đúng hàng đợi |
| Đội điều tra/ứng phó | Đánh giá bằng chứng, phạm vi ảnh hưởng, phê duyệt và theo dõi biện pháp |
| Đội danh tính/khôi phục | Thực hiện chính sách xác minh và gắn lại phương thức xác thực |
| Đội vận hành dịch vụ | Xác nhận biện pháp có hiệu lực, xử lý lỗi và độ trễ giữa các hệ thống |
| Người phụ trách hồ sơ | Theo dõi các việc còn mở, phản hồi và điều kiện đóng |

Tài khoản đặc quyền hoặc trường hợp tranh chấp có thể cần kiểm soát nhiều người theo chính sách tổ chức. Không mặc định mọi nhân viên đọc được ticket đều có quyền thay MFA.

### 12.2. Điều kiện đóng theo kết quả

Một báo cáo không có dấu hiệu người dùng tương tác có thể được xử lý xong sau khi phân loại, gộp mẫu và phản hồi. Với sự cố tài khoản, cân nhắc tối thiểu:

- Đã ghi nhận kết luận, độ chắc chắn và phạm vi ảnh hưởng.
- Các biện pháp bắt buộc đã thực thi, có bằng chứng hiệu lực hoặc phần còn lại được bàn giao rõ.
- Thay đổi trái phép và quyền truy cập kéo dài đã được xem xét.
- Nếu có khôi phục, quyết định xác minh và kết quả đã được ghi riêng.
- Người dùng nhận hướng dẫn qua kênh phù hợp.
- Có kế hoạch theo dõi, lưu bằng chứng và xử lý việc tồn đọng.

Không xóa mẫu gốc chỉ vì ticket được đóng; áp dụng chính sách lưu trữ đã xác định và giới hạn người được xem.

### 12.3. Đo thời gian và chất lượng xử lý

Theo dõi các khoảng thời gian riêng: từ tiếp nhận đến phân loại; từ phát hiện phơi lộ đến quyết định; từ quyết định đến biện pháp có hiệu lực; từ yêu cầu khôi phục đến xác minh hoàn tất.

Các chỉ số chất lượng có thể gồm tỷ lệ hồ sơ thiếu người phụ trách, hành động thu hồi còn lỗi, sự cố mở lại, tài khoản bị khóa nhầm và trường hợp khôi phục trái phép. Không chỉ đo số ticket đã đóng hoặc thời gian phản hồi tự động.

Thời hạn ưu tiên phải do tổ chức đặt theo rủi ro và khả năng trực vận hành. Một cam kết trả lời nhanh không đồng nghĩa đã khôi phục an toàn.

## 13. Những sai lầm cần nhận ra

| Sai lầm | Hệ quả | Cách thiết kế phù hợp |
| --- | --- | --- |
| Cứ có báo cáo là khóa tài khoản được nêu | Kẻ xấu dùng báo cáo gây từ chối dịch vụ | Tách tiếp nhận khỏi quyết định ứng phó |
| Đổi email vì người gọi biết mã ticket | Ticket trở thành đường vòng qua xác minh | Giữ mức xác minh riêng với quyền truy cập hồ sơ |
| Chỉ đặt lại mật khẩu | Bỏ sót phiên, grant hoặc authenticator trái phép | Lập kế hoạch theo từng loại tài sản |
| Tự mở mọi URL gửi kèm | Lộ token, tiêu thụ liên kết thật hoặc gây SSRF | Phân tích có kiểm soát trong môi trường cô lập |
| Coi thư hợp lệ về miền là nội dung an toàn | Bỏ sót hộp thư thật bị chiếm | Đối chiếu nội dung và sự kiện tài khoản |
| Dùng địa chỉ khôi phục vừa thêm làm bằng chứng duy nhất | Tin vào dữ liệu do kẻ tấn công cài vào | Đánh giá lịch sử và bằng chứng độc lập |
| Báo “đã chặn” ngay khi enqueue tác vụ | Người dùng tin vào biện pháp chưa có hiệu lực | Theo dõi và xác nhận kết quả thực thi |
| Đóng sự cố ngay khi người dùng đăng nhập lại | Bỏ sót quyền truy cập còn tồn tại | Tách tiêu chí khôi phục và xử lý sự cố |

## 14. Tình huống tự suy luận

**Tình huống:** Một người chưa đăng nhập gửi ảnh thư reset password thật, khai rằng tài khoản đã bị chiếm và yêu cầu gửi liên kết mới sang email khác. Không có nhật ký đăng nhập bất thường, nhưng có nhiều yêu cầu đặt lại mật khẩu trong vài phút.

**Hướng xử lý:** Tiếp nhận báo cáo và đối chiếu sự kiện phát thư; điều tra việc lạm dụng biểu mẫu khôi phục. Không kết luận đã có chiếm đoạt chỉ từ số yêu cầu và không đổi kênh nhận liên kết theo lời khai. Nếu mẫu chứa token thật bị lộ, xử lý đúng token theo thẩm quyền. Khi người đó cần khôi phục, chuyển sang luồng xác minh độc lập.

**Biến thể:** Sau đó xuất hiện phiên lạ và một passkey mới mà chủ tài khoản đã được xác minh không nhận ra.

**Hướng xử lý:** Nâng mức ưu tiên theo bằng chứng mới, xem xét biện pháp bảo vệ tài khoản và điều tra thay đổi authenticator. Việc cô lập khẩn cấp và việc cấp lại quyền truy cập có thể diễn ra ở hai nhánh khác nhau; nhánh khôi phục vẫn cần đủ điều kiện xác minh.

Nguyên tắc xuyên suốt: xử lý báo cáo phải giúp phát hiện và ngăn phishing, đồng thời bảo vệ chính quy trình khôi phục khỏi việc bị lợi dụng.

## Tài liệu tham khảo

- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): khôi phục sau nghi ngờ xâm nhập, token và thông tin khôi phục.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): vòng đời phiên và vô hiệu hóa phía máy chủ.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): khôi phục tài khoản, quản lý authenticator và khả năng chống phishing.
- [Microsoft Learn — Respond to a compromised email account](https://learn.microsoft.com/en-us/defender-office-365/responding-to-a-compromised-email-account): ví dụ vận hành về phiên, MFA, ứng dụng được cấp quyền và chuyển tiếp thư.
