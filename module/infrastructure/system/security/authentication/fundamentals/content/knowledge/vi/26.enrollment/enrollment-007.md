# Enrollment notification — Thông báo khi ghi danh hoặc thay đổi phương thức xác thực

**Enrollment notification** là thông báo gửi tới người dùng khi một phương thức xác thực hoặc thông tin bảo mật được thêm, kích hoạt, thay thế, gỡ bỏ hay thay đổi trên tài khoản. Ví dụ: ghi danh passkey mới, thêm security key, bật ứng dụng TOTP, đăng ký số điện thoại nhận mã, thay đổi email khôi phục hoặc tắt MFA.

Thông báo này giúp chủ tài khoản nhận biết thay đổi có thể ảnh hưởng tới quyền truy cập. Nếu attacker đã chiếm một phiên đang hoạt động và thêm authenticator của họ, thông báo gửi tới kênh liên lạc đã xác minh trước đó có thể giúp người dùng phát hiện và phản ứng sớm. Tuy nhiên, **notification không phải là bằng chứng xác thực và không thay thế bước xác minh khi ghi danh**. Email hoặc SMS báo “đã thêm passkey” không chứng minh người nhận là chủ tài khoản; việc bấm vào một nút trong thông báo cũng không tự động chứng minh thay đổi là hợp lệ.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, enrollment là một phần của vòng đời credential: xác minh người dùng trước khi thêm phương thức, liên kết credential với đúng tài khoản, thông báo thay đổi, quản lý thu hồi và hỗ trợ recovery. Bài này tập trung vào thiết kế thông báo an toàn, đáng tin, dễ hiểu và có khả năng hỗ trợ phản ứng khi xuất hiện thay đổi trái phép.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mục đích của enrollment notification và phân biệt nó với OTP, verification challenge, approval prompt và transaction confirmation.
2. Xác định những sự kiện cần thông báo khi thêm, thay thế, xóa hoặc thay đổi authenticator và kênh recovery.
3. Chọn kênh thông báo dựa trên tính độc lập, độ tin cậy và trạng thái đã xác minh.
4. Thiết kế nội dung thông báo hữu ích mà không tiết lộ secret, token hoặc dữ liệu cá nhân không cần thiết.
5. Ràng buộc notification với đúng account, credential, enrollment transaction và thời điểm hoàn tất.
6. Xây dựng quy trình phản ứng khi người dùng không nhận ra thay đổi.
7. Chống notification bombing, phishing, spoofing, suppression, account enumeration và lạm dụng liên kết trong thông báo.
8. Thiết kế delivery, retry, idempotency, audit và giám sát nhà cung cấp email/SMS/push.
9. Viết bộ kiểm thử cho cả luồng thành công, thất bại, pending, duplicate event và báo cáo thay đổi trái phép.

## 2. Enrollment notification giải quyết vấn đề gì?

Khi một phương thức xác thực mới được ghi danh, phương thức đó có thể tiếp tục được sử dụng để đăng nhập hoặc phê duyệt hành động. Nếu người thực hiện không phải chủ tài khoản, attacker có thể tạo một đường truy cập bền vững ngay cả khi nạn nhân đổi mật khẩu sau đó.

Ví dụ:
1. Attacker lấy được một phiên đăng nhập đang hoạt động.
2. Attacker thêm passkey hoặc ứng dụng TOTP do họ kiểm soát.
3. Hệ thống lưu credential mới.
4. Attacker dùng credential đó trong những lần đăng nhập sau.
5. Chủ tài khoản không biết có phương thức mới nên không thu hồi kịp thời.

Thông báo gửi tới một kênh đã được xác minh trước đó có thể làm lộ thay đổi bất thường. Người dùng có thể nhận ra họ không khởi tạo sự kiện và báo cáo sự cố. Đây là một lớp phát hiện sau hành động; nó không thay thế reauthentication, step-up authentication, kiểm tra risk hoặc xác minh WebAuthn/TOTP trong chính enrollment flow.

### 2.1. Thông báo không phải là xác minh

Cần phân biệt bốn loại tương tác:

| Loại | Mục đích | Ví dụ | Có tự chứng minh danh tính không? |
| --- | --- | --- | --- |
| **Verification challenge** | Chứng minh người dùng kiểm soát kênh hoặc authenticator đang ghi danh | Nhập mã xác minh email/điện thoại; hoàn tất challenge passkey | Chỉ chứng minh điều kiện cụ thể của challenge, trong phạm vi và thời điểm của nó. |
| **Approval prompt** | Yêu cầu người dùng xác nhận một giao dịch hoặc yêu cầu đang chờ | Push prompt hiển thị “Bạn có đang thêm security key không?” | Chỉ có giá trị khi prompt được ràng buộc với transaction, xác thực đúng thiết bị và chống fatigue/phishing. |
| **Enrollment notification** | Thông báo một sự kiện đã bắt đầu hoặc hoàn tất | “Một passkey mới đã được thêm vào tài khoản” | Không. Đây là tín hiệu thông tin và phát hiện. |
| **Security incident alert** | Cảnh báo hoạt động có nguy cơ và hướng dẫn phản ứng | “Có yêu cầu thêm MFA mà bạn không nhận ra” | Không. Cảnh báo giúp khởi động quy trình xử lý sự cố. |

Không dùng email notification như một yếu tố MFA chỉ vì người dùng có thể bấm nút. Không coi việc người dùng không phản hồi thông báo là đồng ý. Im lặng có thể do email bị chậm, spam, mất mạng hoặc người dùng không còn truy cập kênh.

## 3. Những sự kiện nào cần thông báo?

Không phải mọi thay đổi cấu hình đều có mức rủi ro giống nhau. Hãy xác định sự kiện theo khả năng làm thay đổi đường đăng nhập, recovery hoặc quyền kiểm soát tài khoản.

| Sự kiện | Mức độ quan trọng thường gặp | Nội dung cần thông báo |
| --- | --- | --- |
| Thêm passkey | Cao | Passkey mới được thêm, thời điểm, tên thiết bị do người dùng đặt nếu có, cách báo cáo nếu không nhận ra. |
| Thêm security key | Cao | Khóa bảo mật mới được ghi danh; mô tả nhận biết phù hợp nhưng không tiết lộ secret. |
| Bật ứng dụng TOTP | Cao | Ứng dụng xác thực đã được kích hoạt; không gửi seed/QR hoặc mã dự phòng trong thông báo. |
| Bật SMS/email OTP | Trung bình đến cao tùy policy | Kênh mới đã được xác minh và dùng cho mục đích gì; che một phần địa chỉ/số điện thoại. |
| Thay đổi số điện thoại/email recovery | Cao | Kênh cũ và kênh mới nhận thông tin phù hợp; cảnh báo nếu người dùng không yêu cầu. |
| Xóa authenticator | Cao | Credential nào đã bị gỡ và các phương thức còn lại có thể bị ảnh hưởng thế nào. |
| Tắt MFA hoặc giảm yêu cầu xác thực | Rất cao | MFA đã bị tắt/giảm, thời điểm và hướng xử lý khẩn cấp nếu không phải người dùng. |
| Tạo/regenerate recovery code | Cao | Bộ mã mới đã được tạo; bộ cũ có thể đã mất hiệu lực. Không gửi mã thực tế. |
| Thực hiện account recovery | Cao | Recovery bắt đầu/hoàn tất, credential hoặc phiên nào bị thay đổi. |
| Thay đổi mật khẩu hoặc credential chính | Cao | Thay đổi đã hoàn tất và hướng xử lý nếu không nhận ra. |
| Hủy một enrollment đang chờ | Tùy rủi ro | Chỉ cần thông báo nếu có nguy cơ hoặc hành động quan trọng bị hủy. |
| Đổi tên thiết bị hiển thị | Thấp đến trung bình | Có thể hiển thị trong security activity; không nhất thiết gửi cảnh báo tức thời cho mọi thay đổi nhỏ. |

Chính sách cần xác định rõ sự kiện nào gửi email, SMS, push hoặc chỉ hiển thị trong security center. Tránh gửi quá nhiều thông báo ít giá trị vì người dùng sẽ quen bỏ qua cảnh báo quan trọng.

### 3.1. Thông báo khi bắt đầu và khi hoàn tất

Với thay đổi có rủi ro cao, có thể phát hai sự kiện:
- **Enrollment started:** một yêu cầu thêm hoặc thay đổi authenticator đang chờ. Thông báo này giúp phát hiện yêu cầu bất thường sớm, nhưng phải tránh làm lộ account enumeration hoặc tạo notification bombing.
- **Enrollment completed:** credential đã được xác minh, liên kết và lưu thành công. Đây là thời điểm thông báo xác nhận thay đổi thực sự có hiệu lực.

Không gửi thông báo “đã thêm passkey thành công” trước khi server xác minh registration response và commit credential. Nếu cần thông báo pending, nội dung phải nói rõ trạng thái đang chờ.

## 4. Chọn kênh thông báo đáng tin cậy

Kênh thông báo nên được chọn dựa trên mức độ độc lập với sự kiện vừa xảy ra. Nếu attacker đang thêm email của họ làm kênh recovery, gửi cảnh báo duy nhất tới email mới sẽ không giúp chủ tài khoản phát hiện.

Ưu tiên thông báo tới:
1. Kênh đã xác minh và tồn tại trước khi thay đổi bắt đầu.
2. Thiết bị/phiên đáng tin cậy đã đăng nhập từ trước, nếu có cơ chế notification an toàn.
3. Kênh bổ sung được người dùng thiết lập trước và có kiểm soát truy cập độc lập.
4. Security center hiển thị sự kiện sau khi người dùng đăng nhập lại an toàn.

Không dựa duy nhất vào kênh vừa được thêm hoặc vừa thay đổi để cảnh báo chính thay đổi đó.

### 4.1. So sánh các kênh

| Kênh | Ưu điểm | Rủi ro và giới hạn |
| --- | --- | --- |
| **Email đã xác minh trước** | Có thể chứa thông tin chi tiết, dễ lưu và tra cứu | Hộp thư có thể bị chiếm; link có thể bị phishing; email delivery có thể trễ. |
| **SMS** | Phổ biến, hữu ích khi người dùng không có app | SIM swap, chuyển tiếp SMS, số tái cấp và SS7/nhà mạng; không coi là kênh độc lập mạnh. |
| **Push tới thiết bị đã đăng ký** | Nhanh, có thể hiển thị thông tin ngắn và mở security center | Thiết bị có thể bị mất/chia sẻ; push fatigue; nội dung trên màn hình khóa có thể bị người khác nhìn thấy. |
| **In-app security center** | Có lịch sử sự kiện và trạng thái tập trung | Người dùng phải đăng nhập; attacker có phiên cũng có thể xem hoặc xóa nếu quyền kiểm soát yếu. |
| **Thông báo quản trị tổ chức** | Hữu ích với tài khoản doanh nghiệp/trường học | Quản trị viên có thể không phải chủ thể cá nhân; cần phân quyền và audit. |

Một kênh chỉ có giá trị nếu tài khoản/kênh đó đã được xác minh và bảo vệ phù hợp. Email hoặc số điện thoại được khai báo nhưng chưa xác minh không nên nhận thông báo nhạy cảm như thể đó là kênh đáng tin.

### 4.2. Thay đổi kênh liên lạc

Khi email hoặc số điện thoại thay đổi:
- Xác minh kênh mới trước khi dùng cho đăng nhập/recovery.
- Gửi thông báo tới kênh cũ đã xác minh.
- Có thể gửi thông báo xác nhận tới kênh mới, nhưng không coi kênh mới là kênh độc lập để xác nhận chính thay đổi đó.
- Với tài khoản rủi ro cao, áp dụng thời gian chờ, step-up hoặc phê duyệt bổ sung trước khi thay đổi có hiệu lực.
- Không cho phép một request thay đổi email vừa thay địa chỉ nhận cảnh báo, vừa xóa mọi kênh cũ trong cùng một thao tác không được bảo vệ.

Nếu người dùng đã mất quyền truy cập kênh cũ, cần đi qua recovery policy riêng. Không bỏ qua xác minh chỉ vì người dùng không thể nhận notification ở địa chỉ cũ.

## 5. Ràng buộc thông báo với enrollment transaction

Thông báo phải phản ánh một sự kiện có thật trên đúng tài khoản. Backend cần lưu transaction và sự kiện có định danh, không xây dựng nội dung chỉ từ dữ liệu client gửi lên.

Một enrollment transaction có thể lưu:

~~~text
EnrollmentTransaction:
  transaction_id
  account_id
  initiated_by_session_id
  credential_type
  credential_reference
  requested_action
  created_at
  expires_at
  verified_at
  completed_at
  status: pending | verified | completed | rejected | expired
  risk_context
~~~

Một notification event có thể lưu:

~~~text
EnrollmentNotificationEvent:
  event_id
  transaction_id
  account_id
  event_type
  event_version
  occurred_at
  delivery_targets
  delivery_status
  deduplication_key
~~~

Đây là mô hình logic, không phải schema bắt buộc. Các trường nhạy cảm cần được tối thiểu hóa, mã hóa và giới hạn truy cập.

### 5.1. Những ràng buộc cần kiểm tra

- Transaction thuộc đúng account ID lấy từ server-side session.
- Credential type và action nằm trong danh sách được phép.
- WebAuthn/TOTP/OTP verification đã đạt yêu cầu trước khi đánh dấu completed.
- Credential reference là record đã được lưu thành công và có trạng thái active.
- Transaction chưa hết hạn, chưa bị hủy và chưa được tiêu thụ.
- Notification event được tạo từ sự kiện commit, không từ một thông báo client tự gửi.
- Event ID và deduplication key ngăn gửi lặp khi worker retry.
- Delivery target được lấy từ danh sách kênh đã xác minh ở thời điểm thích hợp, không tin địa chỉ tự khai trong payload.

### 5.2. Thời điểm phát notification

Một thứ tự an toàn thường là:
1. Xác thực người dùng và áp step-up nếu policy yêu cầu.
2. Tạo enrollment transaction và challenge.
3. Người dùng hoàn tất ceremony của authenticator.
4. Server xác minh response, kiểm tra account binding và policy.
5. Commit credential mới cùng trạng thái enrollment.
6. Ghi notification event trong cùng transaction hoặc qua transactional outbox.
7. Worker gửi thông báo tới kênh đã xác minh.
8. Cập nhật delivery status và audit.

Transactional outbox giúp tránh trường hợp credential đã được thêm nhưng event notification bị mất do ứng dụng crash giữa hai thao tác. Worker có thể retry việc gửi, nhưng phải dùng idempotency/deduplication để tránh tạo nhiều cảnh báo giống nhau.

## 6. Nội dung thông báo cần có gì?

Một thông báo tốt giúp người dùng trả lời nhanh:
- Điều gì vừa xảy ra?
- Khi nào xảy ra?
- Tài khoản hoặc dịch vụ nào bị ảnh hưởng?
- Thiết bị/phương thức nào được thêm hoặc thay đổi?
- Người dùng nên làm gì nếu không nhận ra sự kiện?

Ví dụ nội dung:

~~~text
Tiêu đề: Một passkey mới đã được thêm vào tài khoản StudyHub

Một passkey vừa được thêm vào tài khoản của bạn.
Thời gian: 22/11/2026, 14:32 (múi giờ tài khoản)
Phương thức: Passkey
Tên thiết bị: Laptop cá nhân
Phiên/thiết bị: Thông tin nhận biết rút gọn nếu có

Nếu chính bạn thực hiện thao tác này, bạn không cần làm gì thêm.
Nếu bạn không nhận ra thay đổi:
- Mở StudyHub bằng ứng dụng hoặc địa chỉ đã lưu.
- Vào Security settings để xem và thu hồi credential lạ.
- Thu hồi phiên đáng ngờ và làm theo hướng dẫn bảo vệ tài khoản.

StudyHub sẽ không bao giờ yêu cầu bạn gửi mật khẩu, OTP, recovery code hoặc private key qua email.
~~~

Nội dung thực tế phải dùng thời gian và múi giờ rõ ràng, tên dịch vụ nhất quán và thông tin thiết bị đã được xác minh ở mức phù hợp. Không khẳng định vị trí địa lý chính xác nếu chỉ có IP hoặc dữ liệu không đáng tin.

### 6.1. Không đưa bí mật vào thông báo

Không gửi:
- OTP hoặc mã xác minh.
- TOTP seed, QR enrollment secret hoặc private key.
- Recovery code hoặc refresh/access token.
- Session ID, cookie hoặc authorization code.
- Toàn bộ số giấy tờ, ngày sinh hoặc dữ liệu cá nhân không cần thiết.
- Link chứa token dài hạn có thể đăng nhập trực tiếp mà không có kiểm soát bổ sung.

Có thể che một phần email/số điện thoại, ví dụ `m***@example.com` hoặc `••• ••• 4821`. Chỉ hiển thị tên thiết bị do người dùng đặt nếu đã lọc độ dài/ký tự và tránh phản chiếu nội dung không an toàn.

### 6.2. Nêu rõ trạng thái và hành động

Dùng từ ngữ phân biệt:
- “Yêu cầu đang chờ” khi chưa hoàn tất.
- “Đã thêm thành công” khi credential đã được xác minh và lưu.
- “Đã bị từ chối” khi server từ chối.
- “Đã thu hồi” khi trạng thái server đã thay đổi.

Không dùng thông báo mơ hồ như “Tài khoản của bạn có hoạt động mới” cho mọi loại sự kiện. Nhưng cũng không tiết lộ chi tiết kỹ thuật giúp attacker dò policy hoặc nhận diện credential bí mật.

## 7. Liên kết trong notification và chống phishing

Thông báo có thể chứa đường dẫn tới security center hoặc quy trình báo cáo. Link trong email/SMS là bề mặt phishing phổ biến; attacker có thể gửi thông báo giả giống hệt dịch vụ để lấy mật khẩu, OTP hoặc dụ người dùng cài phần mềm.

Nguyên tắc:
- Dùng domain cố định, dễ nhận diện và nhất quán với sản phẩm.
- Không tạo URL từ `Host`, `return_to`, `redirect` hoặc dữ liệu người dùng chưa được xác minh.
- Không dùng shortener hoặc domain bên thứ ba khó nhận biết cho link nhạy cảm.
- Không yêu cầu người dùng nhập mật khẩu/OTP trực tiếp vào trang mở từ một cảnh báo bất ngờ.
- Khuyến khích mở ứng dụng hoặc tự nhập địa chỉ đã biết để xem security center.
- Nếu link có token hành động, token phải ngẫu nhiên, mục đích hẹp, gắn account/event, hết hạn ngắn và chỉ dùng một lần.
- Không thực hiện thay đổi trạng thái chỉ bằng HTTP GET; thao tác xác nhận/báo cáo phải dùng request thay đổi trạng thái có CSRF protection và kiểm tra quyền.
- Không để link báo cáo chuyển hướng tới URL do client cung cấp.

### 7.1. Link “Không phải tôi” cần làm gì?

Nút “Không phải tôi” nên mở quy trình báo cáo sự cố được bảo vệ. Có thể yêu cầu người dùng:
1. Xác nhận họ không nhận ra sự kiện.
2. Xác thực lại qua phương thức còn tin cậy hoặc bắt đầu account recovery.
3. Xem credential/phiên đang hoạt động.
4. Thu hồi credential hoặc session đáng ngờ sau khi xác minh phù hợp.
5. Đổi credential chính và kiểm tra các thay đổi liên quan nếu có dấu hiệu takeover.

Không nên để một lần bấm link trong email lập tức xóa tất cả authenticator hoặc khóa tài khoản vĩnh viễn. Attacker có thể lợi dụng notification giả hoặc gửi hàng loạt yêu cầu để gây denial of service cho nạn nhân.

### 7.2. Không dùng notification làm approval ngầm

Nếu sản phẩm cần push approval, hãy thiết kế nó như một authentication/transaction approval flow riêng:
- Hiển thị rõ hành động, thiết bị và ngữ cảnh.
- Ràng buộc challenge với transaction.
- Chống push fatigue bằng rate limit và giới hạn số prompt.
- Không cho phép approve bằng một nút chung chung không có transaction binding.
- Với hành động nhạy cảm, yêu cầu xác minh cục bộ hoặc step-up theo policy.

Một email báo thay đổi không thể thay thế một approval prompt được thiết kế và xác minh đúng.

## 8. Quy trình phản ứng khi người dùng không nhận ra enrollment

Thông báo chỉ hữu ích nếu người dùng biết phải làm gì. Hãy cung cấp một đường phản ứng rõ, dễ tìm và không yêu cầu họ tiết lộ secret.

~~~mermaid
flowchart TD
    A["Người dùng nhận thông báo enrollment"] --> B{"Có nhận ra thay đổi?"}
    B -->|Có| C["Không cần hành động; xem security activity nếu muốn"]
    B -->|Không| D["Mở ứng dụng/địa chỉ đã biết"]
    D --> E["Xác thực lại qua phương thức còn tin cậy"]
    E --> F["Xem credential, session và thay đổi gần đây"]
    F --> G["Xác định credential/phiên đáng ngờ"]
    G --> H["Thu hồi credential và session theo policy"]
    H --> I["Đổi credential chính hoặc recovery nếu cần"]
    I --> J["Kiểm tra email/điện thoại, liên kết IdP và quyền"]
    J --> K["Ghi nhận incident và thông báo kết quả"]
~~~

Các hành động có thể gồm:
- Thu hồi passkey/security key/TOTP vừa được thêm nếu người dùng đã xác minh và credential được định danh đúng.
- Thu hồi refresh token family và phiên đăng nhập có dấu hiệu bị chiếm.
- Kiểm tra email, số điện thoại, recovery code và tài khoản IdP đã liên kết.
- Đổi mật khẩu hoặc thực hiện lại recovery nếu credential chính có thể đã lộ.
- Kiểm tra hành động nhạy cảm sau thời điểm enrollment.
- Chuyển support/security team nếu người dùng không còn phương thức tin cậy.

Không thu hồi mọi credential của tài khoản theo mặc định nếu chỉ một credential bị nghi ngờ và các phương thức còn lại vẫn an toàn. Nhưng với takeover nghiêm trọng, có thể cần revoke toàn bộ session/token và yêu cầu recovery tăng cường.

## 9. Thông báo cho từng loại enrollment

### 9.1. Passkey và security key

Thông báo nên nói credential mới đã được thêm, thời gian và tên thiết bị/nhãn do người dùng đặt nếu có. Không gửi public key, credential ID đầy đủ hoặc attestation data nếu người dùng không cần. Với passkey đồng bộ, không tuyên bố rằng một thiết bị cụ thể là nơi duy nhất giữ credential nếu thực tế credential có thể đồng bộ.

Nếu người dùng thêm passkey từ thiết bị mới, có thể hiển thị browser/platform ở mức nhận biết. Metadata thiết bị có thể không chính xác; hãy diễn đạt là “thiết bị được ghi nhận” thay vì khẳng định tuyệt đối.

### 9.2. TOTP authenticator

Khi ứng dụng TOTP được kích hoạt:
- Chỉ gửi thông báo sau khi người dùng chứng minh mã TOTP đầu tiên hợp lệ và server đã lưu secret an toàn.
- Không gửi QR code, seed hoặc mã TOTP trong email/push.
- Nêu cách thu hồi hoặc thêm thiết bị dự phòng.
- Nếu người dùng tạo lại seed, thông báo rằng cấu hình cũ có thể không còn hoạt động.

### 9.3. Email/SMS factor và recovery channel

Thông báo kênh mới đã được xác minh và che một phần địa chỉ/số. Nếu thay đổi kênh, cảnh báo tới kênh cũ trước đó và kênh đã đăng ký độc lập. Đừng gửi OTP hoặc link đăng nhập tự động trong thông báo xác nhận.

### 9.4. Xóa MFA hoặc credential

Đây là sự kiện có rủi ro cao vì có thể làm yếu khả năng bảo vệ tài khoản. Thông báo nên nêu rõ phương thức nào bị xóa/tắt, thời gian, trạng thái MFA còn lại và cách báo cáo. Nếu thao tác làm tài khoản không còn yếu tố dự phòng, có thể yêu cầu xác nhận hoặc enrollment phương thức thay thế trước khi cho phép xóa theo policy.

## 10. Chống lạm dụng notification

Notification có thể bị attacker sử dụng như một công cụ tấn công:
- Gửi hàng trăm cảnh báo để người dùng mệt mỏi và bỏ qua.
- Tạo enrollment giả hoặc transaction liên tục để gây hoang mang.
- Dùng email giả mạo thông báo thật để lấy credential.
- Chiếm email rồi xóa/đổi kênh notification để che hoạt động.
- Tạo nhiều yêu cầu “Không phải tôi” để khóa tài khoản nạn nhân.
- Khai thác khác biệt thông báo để dò account tồn tại.

Kiểm soát:
1. Rate limit theo account, transaction, IP/risk signal và loại sự kiện.
2. Gộp các event lặp trong cửa sổ hợp lý nhưng không che mất sự kiện bảo mật quan trọng.
3. Dùng event ID và idempotency để worker retry không gửi vô hạn.
4. Phản hồi công khai đồng nhất khi account không tồn tại/không đủ điều kiện để giảm enumeration.
5. Không cho request chưa xác minh tự tạo notification tới địa chỉ bất kỳ.
6. Giới hạn số lần gửi lại và cung cấp security center để xem lịch sử.
7. Giám sát burst, bounce, complaint, delivery failure và thay đổi đích nhận bất thường.
8. Bảo vệ endpoint unsubscribe/preferences; không cho attacker tắt cảnh báo trọng yếu chỉ bằng một link GET.
9. Duy trì kênh phản ứng độc lập khi email chính bị chiếm.
10. Có playbook cho notification provider outage và sự cố queue.

Không tắt tất cả thông báo bảo mật chỉ để giảm spam. Có thể cho người dùng chọn ngôn ngữ, kênh phụ hoặc thông báo ít quan trọng, nhưng các cảnh báo quan trọng cần policy riêng và không thể bị vô hiệu hóa tùy tiện nếu sản phẩm cần chúng để bảo vệ tài khoản.

## 11. Delivery architecture và độ tin cậy

Notification là một phần của hệ thống phân tán. Credential store, event queue, worker và nhà cung cấp email/SMS/push có thể lỗi độc lập.

Một kiến trúc khái niệm:

~~~mermaid
flowchart LR
    E["Enrollment service"] --> DB[("Credential + transaction DB")]
    E --> O["Transactional outbox"]
    O --> Q["Notification queue"]
    Q --> W["Delivery worker"]
    W --> P["Email / SMS / Push provider"]
    P --> U["Kênh người dùng"]
    W --> L[("Delivery status + audit")]
    U --> S["Security center"]
    S --> DB
~~~

### 11.1. Các nguyên tắc vận hành

- Tạo notification event sau khi trạng thái enrollment đã được commit.
- Dùng transactional outbox hoặc cơ chế bảo đảm event không bị mất giữa database và queue.
- Worker retry lỗi tạm thời với backoff/jitter và giới hạn số lần.
- Dùng event ID/deduplication key để tránh gửi trùng khi queue giao lại message.
- Lưu delivery status: queued, sent-to-provider, delivered (nếu provider xác nhận), bounced, failed hoặc unknown.
- Phân biệt “đã gửi tới provider” với “người dùng đã nhận/đọc”.
- Không chặn việc lưu credential chỉ vì provider email tạm lỗi, trừ khi policy explicitly yêu cầu notification delivery như một điều kiện. Nếu không, ghi nhận pending alert và retry/hiển thị security center.
- Nếu notification là một kiểm soát bắt buộc cho hành động rủi ro cao, thiết kế trạng thái pending/hold rõ ràng và có timeout; không giả vờ rằng email đã được nhận.
- Bảo vệ provider API key, webhook signing secret và queue payload.
- Hạn chế dữ liệu nhạy cảm trong queue; dùng reference ID thay vì ảnh giấy tờ, secret hoặc token.

### 11.2. Webhook và xác nhận delivery

Nếu provider gửi webhook trạng thái:
- Xác minh chữ ký webhook hoặc phương thức xác thực được provider hỗ trợ.
- Kiểm tra timestamp/nonce hoặc cơ chế chống replay nếu có.
- Ràng buộc event với message ID đã gửi.
- Chỉ cập nhật trạng thái delivery, không cho webhook thay đổi trạng thái credential.
- Chấp nhận webhook duplicate một cách idempotent.
- Không tin nội dung webhook chưa được xác thực.

Delivery receipt không chứng minh người dùng đã đọc hoặc hiểu thông báo. Read receipt cũng không phải bằng chứng rằng chủ tài khoản là người đọc.

## 12. Quyền riêng tư và nội dung tối thiểu

Notification thường đi qua nhà cung cấp bên ngoài và có thể xuất hiện trên màn hình khóa hoặc thiết bị dùng chung. Vì vậy nội dung nên tối thiểu nhưng vẫn đủ để người dùng nhận diện sự kiện.

Không nên đưa vào notification:
- Họ tên đầy đủ, số giấy tờ, ngày sinh hoặc địa chỉ nếu không cần.
- Credential secret, TOTP seed, recovery code hoặc token.
- Chi tiết IP đầy đủ, tọa độ chính xác hoặc dữ liệu thiết bị quá sâu.
- Dữ liệu sinh trắc, ảnh selfie hoặc ảnh giấy tờ.
- Tên thiết bị do người dùng đặt mà chưa được lọc; tên có thể chứa HTML, URL hoặc dữ liệu nhạy cảm.

Có thể hiển thị:
- Tên dịch vụ và loại sự kiện.
- Thời điểm theo múi giờ tài khoản hoặc ghi rõ UTC.
- Loại authenticator và nhãn thiết bị rút gọn.
- Kênh được che một phần.
- Hướng dẫn mở security center từ ứng dụng/địa chỉ đã biết.

Cần hỗ trợ ngôn ngữ, khả năng tiếp cận và thông báo rõ ràng cho người dùng có thiết bị hỗ trợ hạn chế. Không dùng màu sắc hoặc từ ngữ gây hoảng sợ quá mức; cảnh báo phải cụ thể, có hành động và không đổ lỗi người dùng.

## 13. Bài thực hành: thiết kế enrollment notification cho StudyHub

**Bối cảnh:** StudyHub hỗ trợ đăng nhập bằng mật khẩu, TOTP và passkey. Người dùng có thể thêm nhiều passkey, đổi email recovery và tạo recovery code. Tài khoản giảng viên có quyền sửa điểm; tài khoản quản trị có thể cấp role. Ứng dụng có email đã xác minh, push tới thiết bị tin cậy và security center.

### 13.1. Xây dựng ma trận sự kiện

Với mỗi sự kiện, hãy xác định:
- Khi nào event được tạo: started, verified, completed hay revoked.
- Kênh nào nhận notification và vì sao kênh đó độc lập.
- Trường dữ liệu nào được hiển thị và trường nào phải che.
- Người dùng làm gì nếu không nhận ra sự kiện.
- Có cần thời gian chờ, step-up hoặc phê duyệt hai người không.
- Retry, deduplication và audit được xử lý thế nào.

Ví dụ ma trận ban đầu:

| Sự kiện | Kênh chính | Nội dung | Phản ứng nếu không nhận ra |
| --- | --- | --- | --- |
| Thêm passkey | Email đã xác minh trước + security center | Thời gian, nhãn thiết bị, phương thức | Xem credential và thu hồi sau xác minh. |
| Bật TOTP | Email đã xác minh trước | TOTP đã kích hoạt; không chứa seed/QR | Thu hồi authenticator, kiểm tra session. |
| Đổi email recovery | Email cũ và thông báo tới email mới sau xác minh | Địa chỉ cũ/mới được che, thời gian có hiệu lực | Bắt đầu recovery/incident, giữ kênh cũ nếu policy yêu cầu. |
| Tắt MFA | Email + push thiết bị tin cậy nếu có | MFA đã tắt và mức bảo vệ còn lại | Step-up, revoke session đáng ngờ, liên hệ hỗ trợ. |
| Tạo recovery code mới | Email + security center | Bộ mã mới đã tạo; bộ cũ có thể bị vô hiệu | Kiểm tra tài khoản và tạo lại sau xác minh. |

### 13.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Passkey registration hợp lệ và được commit | Gửi notification completed tới kênh đã xác minh trước; không gửi private key/secret. |
| WebAuthn registration thất bại | Không gửi thông báo “đã thêm thành công”. |
| Enrollment đang pending | Nếu policy gửi alert, nội dung ghi rõ đang chờ; không mô tả như đã hoàn tất. |
| Credential bị thu hồi | Gửi thông báo thu hồi sau khi server commit trạng thái. |
| Kênh mới chưa xác minh | Không dùng nó làm kênh tin cậy duy nhất cho cảnh báo thay đổi kênh. |
| Email recovery thay đổi | Kênh cũ được thông báo theo policy; kênh mới chỉ được dùng sau xác minh. |
| Notification worker retry cùng event | Không tạo nhiều message trùng ngoài policy; event ID/deduplication hoạt động. |
| Provider timeout | Trạng thái delivery là pending/unknown; retry có giới hạn và không báo người dùng rằng đã nhận. |
| Provider webhook giả hoặc replay | Không cập nhật trạng thái credential; webhook bị từ chối hoặc xử lý idempotent sau xác minh. |
| Attacker tạo hàng loạt enrollment request | Rate limit/abuse controls giới hạn notification bombing và không làm lộ account existence. |
| Link trong email bị sửa domain/redirect | Người dùng không bị chuyển tới domain không được phép; endpoint không nhận redirect tùy ý. |
| Người dùng bấm “Không phải tôi” | Mở quy trình báo cáo có xác minh; không tự động xóa mọi credential bằng GET. |
| Attacker đã chiếm email chính | Hệ thống có kênh độc lập/security center và quy trình recovery phù hợp; không giả định email là an toàn. |
| Tên thiết bị chứa HTML hoặc URL | Nội dung được encode/normalize; không thực thi script hoặc tạo link tùy ý. |
| Notification gửi tới sai account/tenant | Test thất bại; account binding và delivery target được lấy server-side. |
| Người dùng tắt marketing notification | Cảnh báo bảo mật trọng yếu vẫn theo policy riêng. |
| Notification provider bị outage | Credential state vẫn nhất quán; event được lưu, retry và hiển thị trong security center. |
| Tài khoản admin thêm authenticator | Áp step-up/phê duyệt theo policy và audit actor/approver. |
| Người dùng không nhận ra thiết bị nhưng session vẫn active | Quy trình hỗ trợ thu hồi credential/session đáng ngờ và rà soát thay đổi liên quan. |

### 13.3. Câu hỏi tự đánh giá

1. Enrollment notification khác OTP và approval prompt ở mục đích nào?
2. Vì sao không nên gửi cảnh báo duy nhất tới email vừa được thêm?
3. Tại sao notification “đã thêm passkey” chỉ được gửi sau khi registration đã được xác minh và commit?
4. HttpOnly, passkey hoặc MFA có làm email notification trở thành bằng chứng xác thực không?
5. Vì sao link “Không phải tôi” không nên trực tiếp xóa mọi credential bằng GET?
6. Transaction ID, event ID và deduplication key giúp bảo vệ điều gì?
7. Làm sao xử lý notification khi provider timeout hoặc webhook bị replay?
8. Những trường dữ liệu nào không bao giờ được đưa vào email/push?
9. Làm sao giảm notification bombing mà không làm mất cảnh báo quan trọng?
10. Người dùng cần làm gì khi nhận thông báo enrollment mà họ không nhận ra?

**Tiêu chí hoàn thành:** Người học có thể thiết kế ma trận event/channel, giải thích vì sao notification không thay thế enrollment verification, ràng buộc event với trạng thái credential đã commit, xây dựng đường phản ứng an toàn và viết test cho duplicate delivery, phishing, channel takeover, notification bombing và provider outage.

## 14. Vận hành, chỉ số và cải tiến

Các chỉ số nên theo dõi:
- Số enrollment event theo loại authenticator và mức rủi ro.
- Tỷ lệ notification queued, sent, delivered, bounced, failed và unknown.
- Độ trễ từ lúc credential commit tới lúc event được tạo và gửi.
- Tỷ lệ event duplicate, retry và queue backlog.
- Số lần người dùng báo “không phải tôi” theo loại sự kiện.
- Tỷ lệ sự cố được xác nhận là enrollment trái phép.
- Tỷ lệ false alarm và thời gian xử lý support/security.
- Số request enrollment bị rate limit hoặc đánh dấu abuse.
- Tỷ lệ người dùng có kênh notification dự phòng đã xác minh.
- Tỷ lệ cảnh báo bị complaint/spam hoặc delivery provider từ chối.

Không dùng số lần bấm link làm chỉ số duy nhất cho mức độ an toàn. Người dùng có thể không mở email nhưng vẫn nhận ra sự kiện qua security center; hoặc attacker có thể bấm link từ hộp thư bị chiếm. Cần đánh giá outcome: sự cố được phát hiện, credential lạ bị thu hồi, session bị bảo vệ và thời gian phản ứng.

Mỗi notification event nên có correlation ID, account ID nội bộ, transaction ID, event type, timestamp, policy version và delivery result cần thiết. Không log secret, token, mã OTP, ảnh giấy tờ hoặc toàn bộ địa chỉ liên lạc nếu không cần. Giới hạn quyền xem log và đặt retention phù hợp.

Khi thay đổi nội dung, nhà cung cấp hoặc policy, cần kiểm tra lại domain link, template, encoding, localization, webhook signature, retry và kênh fallback. Với tài khoản có quyền cao, có thể yêu cầu phê duyệt bổ sung hoặc thông báo tới nhóm quản trị theo chính sách tổ chức.

## 15. Tài liệu nên đọc tiếp

- **NIST SP 800-63B — Authentication and Authenticator Management**: vòng đời authenticator, binding, notification và các yêu cầu liên quan; kiểm tra phiên bản hiện hành.
- **NIST SP 800-63A — Identity Proofing and Enrollment**: proofing/enrollment và liên kết bằng chứng với tài khoản.
- **W3C WebAuthn**: registration ceremony, credential và xác minh phản hồi ở RP.
- **FIDO Alliance — Passkeys**: mô hình passkey, đồng bộ, thiết bị và trải nghiệm enrollment.
- **OWASP Authentication Cheat Sheet**: xác thực, thay đổi credential, recovery và thông báo.
- **OWASP Forgot Password Cheat Sheet**: bảo vệ các luồng khôi phục và liên kết nhạy cảm.
- **OWASP Logging Cheat Sheet**: audit sự kiện mà không ghi secret hoặc dữ liệu nhạy cảm không cần thiết.
- **OWASP ASVS**: chuyển yêu cầu enrollment, session và notification thành tiêu chí kiểm thử.

Khi triển khai thật, hãy xác định loại tài khoản, mức rủi ro, kênh đã xác minh, khả năng provider, yêu cầu pháp lý và cách hỗ trợ người dùng. **Một enrollment notification có giá trị khi nó phản ánh đúng thay đổi đã được server xác nhận, tới được kênh phù hợp, không tiết lộ bí mật và giúp chủ tài khoản hành động an toàn nếu thay đổi không phải do họ thực hiện.**
