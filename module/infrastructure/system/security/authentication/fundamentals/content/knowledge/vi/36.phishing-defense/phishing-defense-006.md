# User awareness

> **Chương:** Chống phishing  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Giúp người dùng nhận biết, kiểm tra và báo cáo các nỗ lực lừa lấy credential hoặc chiếm phiên; hình thành thói quen xác minh yêu cầu nhạy cảm qua kênh tin cậy và phối hợp với kiểm soát kỹ thuật của tổ chức.

## 1. User awareness là gì?

**User awareness (nhận thức của người dùng)** là khả năng nhận ra tình huống có thể là phishing hoặc social engineering, biết cách kiểm tra trước khi hành động và báo cáo kịp thời khi có dấu hiệu đáng ngờ. Trong bảo mật xác thực, mục tiêu là giúp người dùng bảo vệ mật khẩu, passkey, mã MFA, recovery code, session và quyền truy cập của họ.

Phishing là hành vi giả mạo một người, tổ chức hoặc dịch vụ đáng tin để khiến nạn nhân tiết lộ thông tin, phê duyệt một yêu cầu hoặc thực hiện hành động có lợi cho attacker. Nó có thể xuất hiện qua email, SMS, cuộc gọi, mạng xã hội, mã QR, trang web giả, ứng dụng OAuth độc hại hoặc lời nhờ từ một đồng nghiệp bị mạo danh.

Ví dụ, một nhân viên nhận email trông giống thông báo từ bộ phận IT, yêu cầu đăng nhập lại để tránh bị khóa tài khoản. Link trong email dẫn tới một trang có logo và giao diện giống cổng công ty. Người dùng nhập mật khẩu và mã MFA, attacker dùng thông tin đó để đăng nhập vào hệ thống thật. Nếu người dùng biết tự mở cổng công ty qua bookmark hoặc địa chỉ đã lưu, thay vì theo link bất ngờ, nguy cơ này giảm đáng kể.

Nhận thức của người dùng là một lớp phòng vệ trong hệ thống. Nó không thể thay thế passkey chống phishing, MFA, kiểm tra domain/origin, bảo vệ session, lọc email, xác minh giao dịch và quy trình phản ứng sự cố. Một người cẩn thận vẫn có thể bị đánh lừa bởi nội dung tinh vi hoặc áp lực thời gian; tổ chức phải thiết kế hệ thống để sai sót không lập tức dẫn đến chiếm tài khoản.

### Kết quả học tập

Sau bài này, người học có thể:

- Nhận diện các dấu hiệu thường gặp của phishing và social engineering hiện đại.
- Kiểm tra yêu cầu đăng nhập, thay đổi credential, MFA và thanh toán qua kênh độc lập.
- Hiểu vì sao không chia sẻ OTP, recovery code hoặc chấp thuận MFA không do mình khởi tạo.
- Sử dụng password manager và passkey đúng cách để giảm nguy cơ phishing.
- Báo cáo email, SMS, cuộc gọi, QR code và OAuth consent đáng ngờ.
- Thực hiện các bước đầu tiên nếu đã nhấp link, nhập credential hoặc phê duyệt nhầm.
- Xây dựng chương trình awareness có thực hành, đo lường và hỗ trợ người dùng.

## 2. Phishing nhắm vào điều gì?

Attacker thường muốn một trong các kết quả sau:

- **Credential theft:** lấy mật khẩu, OTP, recovery code hoặc private key.
- **Session theft:** đánh cắp cookie hoặc token để sử dụng phiên đã đăng nhập.
- **MFA abuse:** lừa người dùng phê duyệt push, nhập mã hoặc đăng ký yếu tố mới.
- **Account recovery abuse:** chiếm email/điện thoại khôi phục hoặc lừa nhân viên hỗ trợ đặt lại credential.
- **OAuth consent abuse:** khiến người dùng cấp quyền cho ứng dụng độc hại.
- **Payment or data fraud:** lừa chuyển tiền, thay thông tin nhận thanh toán hoặc tải dữ liệu.
- **Malware delivery:** dụ mở tệp, cài ứng dụng hoặc chạy mã độc.

Không phải mọi phishing đều yêu cầu người dùng nhập mật khẩu. Một cuộc gọi có thể yêu cầu cài phần mềm hỗ trợ từ xa; một QR code có thể dẫn tới trang đăng nhập giả; một lời mời OAuth có thể yêu cầu quyền đọc thư hoặc truy cập tệp. Vì vậy, nhận thức cần bao phủ cả hành động và quyền được cấp, không chỉ nội dung email.

## 3. Các hình thức phishing thường gặp

| Hình thức | Cách tiếp cận | Dấu hiệu cần kiểm tra |
|---|---|---|
| **Email phishing** | Giả mạo IT, ngân hàng, dịch vụ giao hàng hoặc đồng nghiệp | Domain người gửi, link, tệp đính kèm, yêu cầu bất thường |
| **Spear phishing** | Cá nhân hóa theo vai trò, dự án hoặc quan hệ của nạn nhân | Chi tiết có vẻ chính xác nhưng yêu cầu vượt quy trình |
| **Business email compromise (BEC)** | Mạo danh lãnh đạo/đối tác để yêu cầu chuyển tiền hoặc dữ liệu | Thay tài khoản nhận tiền, yêu cầu giữ bí mật, bỏ qua phê duyệt |
| **Smishing** | Lừa qua SMS hoặc ứng dụng nhắn tin | Link rút gọn, cảnh báo giao hàng/tài khoản giả, yêu cầu mã |
| **Vishing** | Gọi điện giả danh IT, ngân hàng, cơ quan chức năng | Gây áp lực, yêu cầu đọc OTP, cài công cụ hoặc chia sẻ màn hình |
| **QR phishing (quishing)** | Dùng QR trên email, poster, hóa đơn hoặc tài liệu | Không thấy trước domain đích, trang đăng nhập bất ngờ |
| **OAuth consent phishing** | Dụ người dùng cấp quyền cho ứng dụng | Tên publisher, domain, permissions và mục đích không phù hợp |
| **MFA fatigue** | Gửi liên tục push request để người dùng bấm Approve | Prompt không do mình khởi tạo hoặc xuất hiện lặp |
| **Clone phishing** | Sao chép một thông điệp thật rồi thay link/tệp | Nội dung quen thuộc nhưng đích hoặc tệp đã thay |
| **Fake support** | Giả nhân viên hỗ trợ qua chat/call/pop-up | Yêu cầu remote access, mật khẩu, mã hoặc recovery code |

### Phishing có thể dùng thông tin thật

Attacker có thể biết tên quản lý, tên dự án, nhà cung cấp hoặc một phần lịch làm việc từ mạng xã hội, website công ty hay dữ liệu bị rò rỉ. Một email nhắc đúng cuộc họp không tự chứng minh người gửi là đồng nghiệp. Hãy xác minh yêu cầu nhạy cảm bằng một kênh đã biết độc lập với thông điệp đang nhận.

## 4. Nhận diện dấu hiệu đáng ngờ

Không có một dấu hiệu đơn lẻ nào xác định chắc chắn phishing. Hãy kết hợp ngữ cảnh, người gửi, nội dung, đích đến và hành động được yêu cầu.

### Dấu hiệu về người gửi và kênh

- Domain gần giống domain thật nhưng có ký tự thừa, thiếu hoặc thay thế.
- Tên hiển thị giống đồng nghiệp nhưng địa chỉ gửi không phù hợp.
- Địa chỉ reply-to khác người gửi mà không có lý do rõ.
- Tin nhắn bất ngờ từ số điện thoại hoặc tài khoản mạng xã hội mới.
- Cuộc gọi yêu cầu xác minh danh tính bằng cách đọc mã dùng một lần.
- Một người quen đột nhiên yêu cầu chuyển tiền hoặc gửi dữ liệu nhạy cảm.

### Dấu hiệu về nội dung và áp lực

- Đe dọa khóa tài khoản, phạt tiền hoặc mất quyền truy cập nếu không hành động ngay.
- Yêu cầu giữ bí mật, không gọi lại quản lý hoặc bỏ qua quy trình.
- Hứa thưởng, hoàn tiền hoặc quyền lợi bất ngờ.
- Lý do chung chung nhưng đòi mật khẩu, OTP hoặc recovery code.
- Ngôn ngữ khác thường, chữ ký không đúng hoặc thông tin không khớp.
- Yêu cầu thực hiện ngoài giờ hoặc trong tình huống gấp không có xác nhận.

Lỗi chính tả có thể là dấu hiệu, nhưng email được viết hoàn hảo vẫn có thể là phishing. Nội dung tạo bằng AI có thể đúng ngữ pháp, dùng giọng điệu của đồng nghiệp và cá nhân hóa rất tốt. Không dựa vào chất lượng câu chữ để quyết định độ tin cậy.

### Dấu hiệu về link và trang đăng nhập

- Domain không đúng domain chính thức.
- Link rút gọn hoặc redirect qua nhiều website không rõ mục đích.
- Trang yêu cầu đăng nhập lại dù người dùng không chủ động mở luồng đăng nhập.
- Trang yêu cầu cả mật khẩu, OTP và recovery code trong một biểu mẫu bất thường.
- Trình duyệt hiển thị cảnh báo chứng chỉ hoặc kết nối không an toàn.
- URL có ký tự tương tự, subdomain gây nhầm lẫn hoặc tên miền quốc tế hóa khó phân biệt.

Biểu tượng ổ khóa/HTTPS chỉ cho biết kết nối được mã hóa tới domain đang mở; nó không chứng minh domain đó thuộc tổ chức thật. Một trang phishing cũng có thể dùng HTTPS hợp lệ.

## 5. Kiểm tra yêu cầu đăng nhập và URL

Khi nhận thông báo yêu cầu đăng nhập, hãy tự bắt đầu luồng từ ứng dụng hoặc địa chỉ chính thức mà tổ chức đã công bố.

### Thói quen kiểm tra

1. Không mở link đăng nhập từ thông điệp bất ngờ nếu không cần thiết.
2. Tự mở bookmark, ứng dụng đã cài hoặc gõ địa chỉ chính thức đã biết.
3. Kiểm tra hostname chính xác trước khi nhập credential.
4. Chú ý domain thực sự ở phần cuối của hostname; tên thương hiệu nằm trong subdomain không làm domain đó trở thành website chính thức.
5. Nếu có nghi ngờ, hỏi bộ phận IT/security qua danh bạ hoặc kênh nội bộ đã lưu trước đó.
6. Không tiếp tục nếu browser cảnh báo chứng chỉ hoặc có redirect không mong đợi.

Ví dụ, nếu domain chính thức là login.example.com, thì login.example.com.attacker.test thuộc domain attacker.test, không phải example.com. Tương tự, example-login.test không phải domain chính thức chỉ vì có chữ example.

### Trên điện thoại

Màn hình nhỏ có thể làm hostname bị rút gọn và khó kiểm tra. Không dựa vào logo, màu sắc hoặc tên ứng dụng hiển thị. Mở ứng dụng đã cài từ nguồn chính thức hoặc tự truy cập website qua bookmark đáng tin.

### Không dùng link tìm được từ quảng cáo hoặc kết quả tìm kiếm làm nguồn xác minh duy nhất

Kết quả tìm kiếm, quảng cáo, bài đăng và mã QR có thể dẫn đến website giả. Với thao tác nhạy cảm, dùng địa chỉ do tổ chức cung cấp qua kênh đã xác minh trước đó.

## 6. Bảo vệ mật khẩu bằng password manager

Password manager giúp tạo và lưu mật khẩu dài, duy nhất cho từng dịch vụ. Nó cũng có thể hỗ trợ nhận diện domain: nhiều trình quản lý mật khẩu chỉ tự điền khi domain phù hợp với thông tin đã lưu.

### Thói quen nên áp dụng

- Dùng mật khẩu riêng cho từng dịch vụ.
- Tạo mật khẩu ngẫu nhiên, dài bằng password manager.
- Bảo vệ password manager bằng mật khẩu chính mạnh và MFA/passkey nếu được hỗ trợ.
- Chỉ cài extension/app từ nguồn chính thức.
- Kiểm tra domain khi password manager không tự điền.
- Không copy mật khẩu vào chat, email, ticket hoặc tài liệu chia sẻ.
- Không dùng chung vault hoặc chia sẻ master password.
- Có phương án khôi phục password manager được bảo vệ.

### Tự điền là một tín hiệu, không phải phán quyết

Nếu password manager không tự điền, có thể domain không khớp, trang đăng nhập mới hoặc ứng dụng dùng trường nhập khác. Không nên cố dán mật khẩu vào trang đáng ngờ chỉ để hoàn tất thao tác. Hãy kiểm tra domain và mở dịch vụ từ bookmark chính thức.

Password manager không bảo vệ khỏi mọi hình thức lừa đảo. Attacker có thể lừa người dùng tạo một mục lưu mới, cài extension độc hại hoặc đánh cắp phiên sau khi đăng nhập. Cần bảo vệ cả thiết bị, browser và session.

## 7. Passkey và xác thực chống phishing

Passkey dựa trên public-key cryptography và WebAuthn/FIDO. Trong luồng web, authenticator tạo chữ ký gắn với challenge và ngữ cảnh RP ID/origin. Một website giả ở domain khác không thể đơn giản dùng passkey đã đăng ký cho domain thật như cách nó có thể thu thập mật khẩu nhập tay.

### Người dùng cần nhớ

- Ưu tiên passkey hoặc security key cho tài khoản hỗ trợ.
- Chỉ tạo passkey khi đang ở website/app chính thức.
- Kiểm tra tên dịch vụ và ngữ cảnh trước khi xác nhận trên authenticator.
- Không phê duyệt đăng ký passkey hoặc security key mà mình không khởi tạo.
- Giữ phương thức dự phòng và recovery code theo hướng dẫn an toàn.
- Báo cáo ngay khi nhận thông báo credential mới mà mình không đăng ký.

### Passkey giảm rủi ro nào?

Passkey giúp chống việc nhập mật khẩu vào website giả vì xác thực gắn với RP ID/origin. Nó cũng giảm nguy cơ credential stuffing do không dùng chung một mật khẩu giữa nhiều dịch vụ.

Passkey không ngăn mọi cuộc tấn công. Attacker vẫn có thể lừa người dùng cấp quyền OAuth, chiếm thiết bị, chiếm session sau khi đăng nhập, lừa quy trình recovery hoặc dụ người dùng xác nhận một thao tác khác. Awareness vẫn cần bao phủ quyền, phiên và hành động nhạy cảm.

## 8. MFA fatigue và yêu cầu phê duyệt bất ngờ

Trong MFA fatigue, attacker đã biết mật khẩu hoặc có cách kích hoạt đăng nhập rồi gửi liên tục push request. Người dùng có thể bấm Approve chỉ để thông báo biến mất.

### Khi nhận push không do mình khởi tạo

1. Chọn Deny/Reject.
2. Không chấp nhận chỉ vì prompt lặp lại hoặc có người gọi yêu cầu.
3. Báo cáo cho IT/security qua kênh chính thức.
4. Nếu có thể, đổi mật khẩu từ thiết bị sạch và thu hồi session theo hướng dẫn.
5. Kiểm tra phương thức MFA/passkey mới được thêm.

Không bao giờ đọc OTP hoặc recovery code cho người gọi tự xưng là IT, ngân hàng hay bộ phận bảo mật. Nhân viên hỗ trợ hợp lệ không cần người dùng gửi mã bí mật để chứng minh danh tính.

### Number matching và context

Một số hệ thống MFA hiển thị số cần nhập hoặc thông tin vị trí/ứng dụng để người dùng đối chiếu. Hãy kiểm tra yêu cầu có khớp hành động mình vừa khởi tạo không. Number matching làm giảm việc bấm nhầm, nhưng vẫn không nên chấp thuận nếu bản thân không bắt đầu đăng nhập.

## 9. Phishing qua OAuth consent

OAuth consent phishing lừa người dùng cấp quyền cho ứng dụng bên thứ ba. Ứng dụng có thể xin đọc email, xem tệp, truy cập lịch hoặc duy trì quyền truy cập lâu dài.

Trước khi chọn Accept/Allow:

- Kiểm tra tên ứng dụng và publisher.
- Kiểm tra domain của trang consent.
- Đọc danh sách permissions/scopes.
- Hỏi vì sao ứng dụng cần từng quyền.
- Không cấp quyền rộng chỉ để xem một tài liệu hoặc tham gia một cuộc họp.
- Nếu không nhận ra ứng dụng hoặc publisher, hủy và hỏi IT/security.

### Nếu đã cấp quyền nhầm

Không chỉ đổi mật khẩu rồi cho rằng mọi quyền đã mất. Hãy báo cáo, yêu cầu tổ chức kiểm tra consent/grant, thu hồi quyền ứng dụng đáng ngờ, kiểm tra activity log và thu hồi session/token liên quan theo khả năng của nền tảng.

## 10. QR phishing, tệp đính kèm và mã độc

### QR code

QR code che giấu địa chỉ đích cho đến khi camera hoặc ứng dụng giải mã. Không quét QR bất ngờ trên email, hóa đơn, poster hoặc tài liệu không rõ nguồn. Nếu đã quét:

- Xem hostname trước khi mở.
- Không nhập credential nếu domain chưa được xác minh.
- Không cài profile, ứng dụng hoặc chứng chỉ chỉ vì trang yêu cầu.
- Không cấp quyền camera, accessibility hoặc quản lý thiết bị nếu không có lý do rõ.

### Tệp và tài liệu

- Không bật macro hoặc nội dung chủ động chỉ vì tài liệu yêu cầu.
- Không chạy script/lệnh được gửi qua email hoặc chat.
- Không cài phần mềm hỗ trợ từ xa theo hướng dẫn của người gọi chưa xác minh.
- Báo cáo tệp đáng ngờ bằng chức năng của tổ chức; không chuyển tiếp rộng cho đồng nghiệp.

Nếu tổ chức cung cấp sandbox hoặc nút báo cáo phishing, dùng đúng quy trình đó. Người dùng không cần tự mở tệp để kiểm tra xem có độc hại không.

## 11. Deepfake và mạo danh bằng AI

Attacker có thể dùng giọng nói tổng hợp, video giả, ảnh đại diện và dữ liệu công khai để mạo danh lãnh đạo, nhân viên IT, nhà cung cấp hoặc người thân. Một cuộc gọi có hình ảnh/giọng nói giống người quen không phải bằng chứng đủ để phê duyệt giao dịch hoặc thay đổi credential.

### Xác minh yêu cầu nhạy cảm qua kênh độc lập

- Gọi lại số đã lưu trong danh bạ nội bộ, không dùng số người gọi vừa cung cấp.
- Dùng quy trình phê duyệt hai người cho chuyển tiền hoặc thay đổi thông tin nhận tiền.
- Xác nhận thay đổi tài khoản ngân hàng với nhà cung cấp qua kênh đã biết.
- Yêu cầu ticket hoặc phê duyệt trong hệ thống chính thức.
- Dùng từ khóa/phrase xác minh nội bộ nếu tổ chức đã thiết lập và quản lý an toàn.

Không dựa vào bí mật cá nhân dễ tìm trên mạng như ngày sinh, tên thú cưng hoặc trường học để xác minh người gọi.

## 12. Quy tắc vàng khi nhận yêu cầu nhạy cảm

Trước khi nhập credential, phê duyệt MFA, cấp quyền hoặc chuyển tiền, hãy tự hỏi:

1. **Tôi có khởi tạo hành động này không?** Nếu không, dừng và từ chối prompt.
2. **Tôi có biết chắc kênh này là chính thức không?** Nếu không, tự mở kênh đã lưu.
3. **Yêu cầu có đúng mục đích và phạm vi không?** Một tài liệu không cần quyền đọc toàn bộ mailbox.
4. **Có bị thúc ép hoặc yêu cầu giữ bí mật không?** Áp lực là lý do để xác minh thêm.
5. **Có thay đổi nào không thể đảo ngược không?** Chuyển tiền, cấp quyền admin, đổi recovery method cần kiểm tra độc lập.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đăng nhập / cấp quyền / chuyển tiền"] --> B{"Tôi có khởi tạo không?"}
    B -->|"Không"| C["Từ chối / dừng thao tác"]
    C --> D["Báo cáo qua kênh chính thức"]
    B -->|"Có"| E{"Kênh và domain đã xác minh?"}
    E -->|"Không"| F["Tự mở ứng dụng hoặc gọi số đã lưu"]
    F --> G{"Xác minh độc lập thành công?"}
    E -->|"Có"| H["Kiểm tra phạm vi và hành động"]
    G -->|"Không"| D
    G -->|"Có"| H
    H --> I{"Quyền/hành động đúng mục đích?"}
    I -->|"Không"| D
    I -->|"Có"| J["Tiếp tục theo quy trình chuẩn"]
~~~

## 13. Nếu đã nhấp link hoặc nhập thông tin

Không trì hoãn báo cáo vì lo bị trách phạt. Phản ứng nhanh thường giúp tổ chức thu hồi phiên và hạn chế thiệt hại.

### Chỉ nhấp link, chưa nhập dữ liệu

- Đóng trang nếu thấy bất thường.
- Không tải hoặc chạy nội dung từ trang.
- Báo cáo thông điệp và URL theo quy trình.
- Nếu đã tải tệp hoặc cài ứng dụng, nói rõ điều đó với IT/security.

### Đã nhập mật khẩu

- Báo cáo ngay qua kênh IT/security chính thức.
- Từ thiết bị sạch và website chính thức, đổi mật khẩu bị ảnh hưởng; không dùng lại mật khẩu đó ở dịch vụ khác.
- Yêu cầu thu hồi session, refresh token và các phiên đáng ngờ.
- Kiểm tra MFA/passkey/recovery method mới được thêm.
- Nếu dùng cùng mật khẩu ở nơi khác, thay đổi các mật khẩu đó.

### Đã nhập OTP hoặc phê duyệt MFA

- Báo cáo ngay và nói rõ mã đã nhập hay push đã được chấp thuận.
- Yêu cầu đội bảo mật kiểm tra đăng nhập, session và thay đổi credential.
- Thu hồi phiên/token đáng ngờ và reset yếu tố xác thực nếu quy trình yêu cầu.
- Không chờ đến khi thấy giao dịch lạ mới báo cáo.

### Đã cấp quyền OAuth

- Báo cáo ứng dụng và các permission đã cấp.
- Yêu cầu quản trị viên kiểm tra và thu hồi consent/grant đáng ngờ.
- Kiểm tra activity log, mailbox rules, forwarding và ứng dụng đã kết nối nếu phù hợp.
- Đổi mật khẩu không tự động thu hồi mọi OAuth grant.

### Đã chuyển tiền hoặc gửi dữ liệu

- Liên hệ ngay bộ phận tài chính/ngân hàng qua số chính thức đã lưu để yêu cầu chặn hoặc thu hồi giao dịch nếu còn khả năng.
- Báo cáo security/legal/privacy theo quy trình tổ chức.
- Ghi lại thời điểm, người nhận, kênh và nội dung đã gửi; không xóa bằng chứng.

### Thiết bị có thể đã bị cài mã độc

Ngừng sử dụng thiết bị đó cho đăng nhập nhạy cảm và liên hệ IT/security để được hướng dẫn cô lập/kiểm tra. Không tự cài công cụ dọn dẹp từ link do người lạ cung cấp. Dùng thiết bị khác đã được tin cậy cho thao tác đổi credential theo hướng dẫn của tổ chức.

## 14. Báo cáo phishing đúng cách

Một báo cáo hữu ích giúp đội bảo mật chặn domain, sender, attachment hoặc chiến dịch trước khi nhiều người bị ảnh hưởng.

Nên cung cấp:

- Thông điệp gốc qua nút Report Phishing hoặc quy trình được chỉ định.
- Thời điểm nhận và kênh nhận.
- Link hoặc domain hiển thị nếu có thể sao chép an toàn.
- Tệp đính kèm có được mở/tải hay không.
- Người dùng đã nhập mật khẩu, OTP, recovery code hoặc cấp quyền chưa.
- Có phê duyệt MFA, cài ứng dụng hay chuyển tiền không.
- Thiết bị và tài khoản liên quan ở mức cần thiết.

Không chuyển tiếp email phishing như một email thông thường nếu việc đó làm mất header hoặc kích hoạt link/tệp. Dùng công cụ báo cáo chính thức để giữ nguyên bằng chứng. Không đăng công khai ảnh chụp có chứa email, số điện thoại, token hoặc dữ liệu cá nhân.

### Báo cáo sớm, không sợ bị phạt

Tổ chức nên khuyến khích báo cáo thiện chí, kể cả khi người dùng đã nhấp link hoặc nhập credential. Nếu người dùng sợ bị trách phạt, họ có thể che giấu sự cố và làm chậm containment. Văn hóa báo cáo sớm là một kiểm soát bảo mật thực tế.

## 15. Xây dựng chương trình user awareness

Một khóa học một lần hoặc email nhắc nhở hằng năm không đủ để duy trì thói quen. Chương trình nên kết hợp nội dung ngắn, thực hành, thông báo theo sự kiện và hỗ trợ dễ tiếp cận.

### Thành phần chương trình

- **Onboarding:** hướng dẫn domain chính thức, MFA, passkey, password manager và kênh báo cáo.
- **Microlearning:** bài ngắn về một tình huống cụ thể như QR phishing hoặc MFA fatigue.
- **Scenario practice:** mô phỏng email, cuộc gọi, OAuth consent và yêu cầu chuyển tiền.
- **Just-in-time guidance:** nhắc nhở ngay tại luồng nhạy cảm như thêm recovery method hoặc cấp quyền ứng dụng.
- **Reporting practice:** cho người dùng thực hành nút báo cáo và biết phản hồi sau báo cáo.
- **Role-based training:** nội dung riêng cho finance, HR, IT/helpdesk, executives và administrators.
- **Incident feedback:** chia sẻ bài học sau sự cố mà không làm lộ thông tin nạn nhân.

### Mô phỏng phishing có trách nhiệm

Mô phỏng giúp đánh giá khả năng nhận biết, nhưng không nên dùng để bêu tên hoặc trừng phạt người mắc bẫy. Cần:

- Được tổ chức phê duyệt và thông báo phù hợp.
- Không thu thập mật khẩu thật hoặc OTP thật.
- Không làm giả tình huống gây hoảng loạn hoặc ảnh hưởng công việc quan trọng.
- Cung cấp giải thích ngay sau mô phỏng.
- Cho phép người dùng đặt câu hỏi và nhận hỗ trợ.
- Dùng kết quả tổng hợp để cải thiện kiểm soát và đào tạo.

### Thiết kế theo vai trò

| Nhóm | Tình huống cần luyện tập |
|---|---|
| Nhân viên nói chung | Link đăng nhập giả, QR, MFA push bất ngờ |
| Finance/procurement | Thay tài khoản ngân hàng, hóa đơn giả, yêu cầu chuyển tiền gấp |
| HR | Hồ sơ ứng viên, bảng lương, dữ liệu nhân viên và giả mạo quản lý |
| IT/helpdesk | Reset MFA, thêm passkey, remote support và xác minh người gọi |
| Administrators | OAuth consent, quyền admin, session/token theft và recovery abuse |
| Executives | BEC, deepfake voice/video, yêu cầu bí mật hoặc vượt phê duyệt |

## 16. Đo lường hiệu quả

Không đánh giá awareness chỉ bằng tỷ lệ người bấm vào email mô phỏng. Một chương trình tốt cần đo cả khả năng báo cáo, thời gian phản ứng và tác động đến sự cố.

| Chỉ số | Điều cần hiểu |
|---|---|
| Report rate | Tỷ lệ người dùng báo cáo thông điệp mô phỏng/thực tế |
| Click rate | Tỷ lệ mở link; chỉ là một tín hiệu, không phản ánh toàn bộ nhận thức |
| Credential submission rate | Tỷ lệ nhập dữ liệu vào trang mô phỏng; tuyệt đối không thu mật khẩu thật |
| Time to report | Thời gian từ lúc nhận đến lúc báo cáo |
| Repeat behavior | Xu hướng theo thời gian sau đào tạo và hỗ trợ |
| MFA prompt rejection/reporting | Người dùng có từ chối và báo cáo prompt không khởi tạo không |
| OAuth consent review | Người dùng có kiểm tra publisher/permissions không |
| Incident containment time | Thời gian từ báo cáo đến thu hồi session/credential |
| Near-miss reporting | Số sự kiện đáng ngờ được báo cáo trước khi gây thiệt hại |

### Diễn giải cẩn thận

- Click rate giảm không đồng nghĩa tổ chức an toàn nếu attacker chuyển sang vishing hoặc OAuth consent.
- Report rate tăng có thể là dấu hiệu nhận thức và niềm tin báo cáo tốt hơn, không phải nhiều người dùng bất cẩn hơn.
- So sánh giữa nhóm cần tính đến loại công việc, mức tiếp xúc và cách triển khai mô phỏng.
- Không xếp hạng công khai cá nhân hoặc dùng một lần bấm nhầm để kết luận năng lực.
- Kết hợp metric awareness với dữ liệu kỹ thuật như domain bị chặn, MFA abuse, session theft và thời gian revoke.

## 17. Trách nhiệm của tổ chức

Không thể giao toàn bộ trách nhiệm chống phishing cho người dùng. Tổ chức cần giảm cơ hội thành công của attacker:

- Ưu tiên passkey/WebAuthn hoặc phương thức chống phishing cho tài khoản quan trọng.
- Bảo vệ domain, email authentication và hệ thống gửi thông báo.
- Lọc URL/tệp, sandbox và chặn domain độc hại.
- Dùng conditional access, rate limit, risk-based authentication và session protection.
- Hạn chế quyền OAuth và yêu cầu admin consent cho ứng dụng rủi ro.
- Có quy trình xác minh độc lập cho thanh toán và thay đổi thông tin nhận tiền.
- Bảo vệ helpdesk khỏi social engineering bằng quy trình reset MFA/recovery.
- Cung cấp nút báo cáo rõ ràng, dễ dùng và đội phản ứng có trách nhiệm.
- Thu hồi session/token/credential nhanh khi phát hiện compromise.
- Tạo môi trường không đổ lỗi để người dùng báo cáo sớm.

### Thiết kế hệ thống để giảm hậu quả sai sót

Ngay cả khi người dùng nhập mật khẩu vào trang giả, passkey chống phishing, MFA chống phishing, giới hạn đăng nhập, phát hiện bất thường và session binding có thể giảm khả năng attacker chiếm quyền. Với giao dịch, phê duyệt hai người và xác minh qua kênh độc lập giúp giảm thiệt hại nếu một tài khoản bị chiếm.

Awareness phát huy hiệu quả nhất khi quy trình và công nghệ hỗ trợ hành vi an toàn, không tạo áp lực khiến người dùng phải bỏ qua kiểm tra.

## 18. Tình huống thực hành: yêu cầu khẩn cấp từ “giám đốc”

**Bối cảnh:** Nhân viên tài chính nhận cuộc gọi video từ người có hình ảnh và giọng nói giống giám đốc. Người này yêu cầu chuyển khoản lớn trong 20 phút, nói rằng giao dịch bí mật và không cần quy trình phê duyệt thông thường. Sau cuộc gọi, một email có thông tin tài khoản nhận tiền được gửi tới.

### Cách xử lý

1. Không chuyển tiền chỉ dựa trên cuộc gọi hoặc email.
2. Dùng số điện thoại đã lưu trong danh bạ công ty hoặc kênh nội bộ để xác minh độc lập.
3. Thực hiện quy trình phê duyệt hai người và kiểm tra thay đổi tài khoản nhận tiền.
4. Báo cáo cuộc gọi/email cho security và finance theo kênh chính thức.
5. Giữ lại email, thời điểm cuộc gọi và thông tin giao dịch để điều tra.

### Vì sao?

Giọng nói/video có thể bị giả mạo. Áp lực thời gian, yêu cầu giữ bí mật và bỏ qua phê duyệt là dấu hiệu social engineering. Một kênh xác minh độc lập khiến attacker khó kiểm soát đồng thời cả hai luồng.

## 19. Kiểm thử và bài tập thực hành

| Tình huống | Hành động đúng mong đợi |
|---|---|
| Email yêu cầu đăng nhập ngay để tránh khóa tài khoản | Tự mở cổng chính thức; không dùng link bất ngờ |
| URL có thương hiệu trong subdomain của domain lạ | Kiểm tra hostname thực; không nhập credential |
| Trang HTTPS có logo giống công ty | Không coi HTTPS/logo là bằng chứng domain thật |
| SMS giao hàng yêu cầu phí nhỏ qua link | Kiểm tra qua ứng dụng/website hãng vận chuyển chính thức |
| Cuộc gọi IT yêu cầu đọc OTP | Từ chối; liên hệ IT qua danh bạ đã biết |
| MFA push xuất hiện khi không đăng nhập | Deny và báo cáo |
| QR code trên poster dẫn đến đăng nhập | Kiểm tra domain trước; tự mở dịch vụ chính thức |
| OAuth app yêu cầu đọc toàn bộ mailbox | Hủy nếu không cần; hỏi IT/security |
| Người quản lý yêu cầu chuyển tiền bí mật | Xác minh độc lập và tuân thủ phê duyệt |
| Password manager không tự điền | Dừng và kiểm tra domain |
| Đã nhập mật khẩu vào trang giả | Báo cáo, đổi từ thiết bị sạch và yêu cầu revoke session |
| Đã cấp quyền OAuth nhầm | Báo cáo và yêu cầu kiểm tra/thu hồi grant |
| Đã gửi recovery code cho người gọi | Báo cáo ngay, thu hồi/reissue recovery material và session liên quan |
| Tệp đính kèm yêu cầu bật macro | Không bật; báo cáo theo quy trình |
| Người dùng sợ bị phạt vì bấm link | Khuyến khích báo cáo ngay, hỗ trợ containment |

### Bài tập nhóm

1. Nhận một thông điệp giả lập và xác định các dấu hiệu cần kiểm tra.
2. Tìm domain thực của link mà không mở trang hoặc nhập dữ liệu.
3. Chọn một kênh độc lập để xác minh yêu cầu.
4. Soạn báo cáo phishing có đủ thời điểm, kênh và hành động đã thực hiện.
5. Đề xuất bước containment nếu credential hoặc session đã bị lộ.

## 20. Checklist user awareness

- [ ] Người dùng biết domain và ứng dụng chính thức của tổ chức.
- [ ] Người dùng tự mở dịch vụ qua bookmark/app thay vì tin link bất ngờ.
- [ ] Người dùng hiểu HTTPS không chứng minh website là thật.
- [ ] Mật khẩu riêng biệt được tạo/lưu bằng password manager.
- [ ] Passkey/security key được ưu tiên cho tài khoản hỗ trợ.
- [ ] Người dùng không chia sẻ OTP, recovery code hoặc mật khẩu với bất kỳ người gọi nào.
- [ ] MFA push không do mình khởi tạo luôn bị từ chối và báo cáo.
- [ ] Người dùng kiểm tra publisher và permissions trước OAuth consent.
- [ ] QR code, tệp đính kèm và yêu cầu cài ứng dụng được kiểm tra nguồn.
- [ ] Yêu cầu chuyển tiền/thay đổi thông tin nhận tiền được xác minh độc lập.
- [ ] Có kênh báo cáo phishing dễ tìm và phản hồi rõ ràng.
- [ ] Người dùng biết phải làm gì nếu đã nhấp link, nhập credential hoặc cấp quyền.
- [ ] Chương trình awareness có tình huống thực hành và nội dung theo vai trò.
- [ ] Mô phỏng phishing không thu secret thật và không bêu tên người dùng.
- [ ] Đo report rate, time to report, containment và xu hướng theo thời gian.
- [ ] Tổ chức có kiểm soát kỹ thuật, helpdesk và quy trình ứng phó hỗ trợ người dùng.

## Ghi nhớ

Phishing khai thác sự tin tưởng, áp lực và thói quen để lấy credential, chiếm session, lạm dụng MFA hoặc khiến người dùng cấp quyền. Hãy tự khởi tạo đăng nhập từ kênh chính thức, kiểm tra domain và permissions, không chia sẻ OTP/recovery code, từ chối MFA prompt bất ngờ và xác minh yêu cầu nhạy cảm qua kênh độc lập.

Nếu đã mắc bẫy, báo cáo ngay và nói rõ dữ liệu hoặc thao tác nào đã xảy ra để tổ chức thu hồi session, credential và quyền liên quan. User awareness cần đi cùng passkey chống phishing, bảo vệ session, quy trình phê duyệt và văn hóa không đổ lỗi; mục tiêu là giảm cơ hội thành công của attacker và giảm thiệt hại khi có sai sót.
