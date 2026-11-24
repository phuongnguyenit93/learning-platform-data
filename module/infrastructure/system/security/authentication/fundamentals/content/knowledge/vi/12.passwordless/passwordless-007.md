# Fallback về mật khẩu

> **Chương:** Passwordless  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Thiết kế đường đăng nhập dự phòng bằng mật khẩu trong một hệ thống passwordless sao cho người dùng có thể khôi phục khả năng truy cập, trong khi đường dự phòng không trở thành lối tắt dễ bị phishing, credential stuffing hoặc lạm dụng để chiếm tài khoản.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao một hệ thống passwordless đôi khi vẫn cung cấp **fallback về mật khẩu** và vì sao đường fallback có thể làm giảm mức bảo đảm tổng thể.
2. Phân biệt **fallback đăng nhập**, **khôi phục tài khoản**, **thay thế authenticator** và **step-up authentication**.
3. Nhận diện các rủi ro khi fallback: phishing, credential stuffing, password spraying, dò tài khoản, downgrade, lạm dụng reset và chiếm phiên.
4. Thiết kế chính sách khi passkey không khả dụng, thiết bị bị mất, authenticator hỏng hoặc người dùng không thể hoàn thành xác minh.
5. Bảo vệ mật khẩu dự phòng, mã khôi phục, kênh email/SMS và quy trình hỗ trợ theo vòng đời credential.
6. Đặt điều kiện xác thực lại và step-up cho thao tác nhạy cảm, đồng thời không tin trạng thái do client tự khai.
7. Chuyển chính sách fallback thành yêu cầu kiểm thử, tín hiệu giám sát và quy trình ứng phó.

## 1. Vì sao hệ thống passwordless lại có fallback về mật khẩu?

**Passwordless authentication** là cách xác thực mà người dùng không cần nhập mật khẩu dùng chung với dịch vụ trong luồng đăng nhập chính. Một ví dụ phổ biến là **passkey**: thiết bị/authenticator giữ khóa riêng, máy chủ lưu khóa công khai và kiểm tra phản hồi mật mã cho thử thách mới.

Tuy nhiên, người dùng có thể không sử dụng được passkey tại một thời điểm:

- Điện thoại hoặc máy tính đang giữ passkey bị mất, hỏng hoặc hết pin.
- Người dùng đổi thiết bị nhưng chưa đồng bộ hoặc chưa đăng ký passkey mới.
- Thiết bị hiện tại, trình duyệt hoặc môi trường đăng nhập không hỗ trợ phương thức mong muốn.
- Khóa bảo mật vật lý không có sẵn.
- Người dùng không thể hoàn thành thao tác xác minh cục bộ do vấn đề trợ năng hoặc thiết bị.
- Tài khoản nền tảng dùng để đồng bộ passkey đang gặp sự cố hoặc cần khôi phục.
- Người dùng đang ở môi trường tạm thời, không thể truy cập authenticator thường dùng.

Nếu hệ thống không có đường thay thế, người dùng hợp lệ có thể bị khóa khỏi tài khoản. Một sản phẩm vì vậy có thể giữ lại mật khẩu, mã khôi phục, authenticator dự phòng hoặc quy trình hỗ trợ.

Nhưng khi thêm **fallback về mật khẩu**, hệ thống lại tạo một đường mà kẻ tấn công có thể nhắm vào bằng cách thu thập bí mật qua trang giả, thử mật khẩu bị lộ hoặc đoán mật khẩu. Kẻ tấn công thường chọn **đường dễ khai thác nhất** trong tất cả các đường đăng nhập và khôi phục được cung cấp.

**Nguyên tắc trung tâm:** passwordless chỉ có ý nghĩa bảo mật khi toàn bộ đường truy cập — đăng nhập chính, fallback, enrollment, reset và recovery — được thiết kế nhất quán. Một passkey chống phishing không thể bù cho một đường mật khẩu hoặc khôi phục quá yếu.

## 2. Phân biệt bốn khái niệm dễ nhầm lẫn

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Fallback đăng nhập** | Người dùng có phương thức thay thế nào để hoàn tất lần đăng nhập hiện tại? | Dùng mật khẩu khi passkey không dùng được. |
| **Khôi phục tài khoản (account recovery)** | Người dùng lấy lại quyền kiểm soát tài khoản khi mất hoặc không còn credential nào? | Dùng mã khôi phục, authenticator dự phòng hoặc quy trình hỗ trợ được kiểm chứng. |
| **Thay thế authenticator (authenticator replacement)** | Làm sao gỡ credential cũ và gắn credential mới một cách an toàn? | Thu hồi passkey trên thiết bị bị mất và đăng ký passkey mới. |
| **Step-up / reauthentication** | Có cần chứng minh lại hoặc tăng mức bảo đảm trước thao tác nhạy cảm không? | Yêu cầu passkey hoặc phương thức mạnh hơn trước khi đổi email khôi phục. |

Các luồng này liên quan nhưng không giống nhau. Ví dụ:

- Người dùng vẫn có mật khẩu đã đăng ký và chỉ tạm thời không dùng được passkey: đây có thể là **fallback đăng nhập**.
- Người dùng mất toàn bộ thiết bị và credential: cần **khôi phục tài khoản**.
- Sau khi khôi phục, người dùng muốn thêm passkey mới và thu hồi khóa cũ: đó là **thay thế authenticator**.
- Người dùng vừa đăng nhập bằng mật khẩu fallback nhưng muốn thay phương thức MFA: hệ thống có thể yêu cầu **step-up** bằng bằng chứng mạnh hơn.

Không nên dùng một đường “quên mật khẩu” chung để giải quyết mọi trường hợp. Mỗi thao tác có mục tiêu, bằng chứng và hậu quả bảo mật khác nhau.

## 3. Fallback về mật khẩu thay đổi mô hình tin cậy thế nào?

Trong luồng passwordless chính, passkey/WebAuthn có thể ràng buộc phản hồi với origin và RP ID của dịch vụ. Người dùng không phải gửi một bí mật dùng chung có thể nhập lại trên website giả.

Khi cho phép mật khẩu fallback, hệ thống bổ sung một đường mà kẻ tấn công có thể nhắm vào bằng:

- Phishing để thu thập mật khẩu.
- Credential stuffing từ mật khẩu bị lộ ở dịch vụ khác.
- Password spraying hoặc đoán mật khẩu phổ biến.
- Malware/keylogger lấy mật khẩu.
- Lạm dụng reset password hoặc email khôi phục.
- Dò tài khoản qua response, thời gian hoặc hành vi của endpoint.
- Lạm dụng mật khẩu fallback để thêm authenticator do attacker kiểm soát.

~~~mermaid
flowchart TD
    U["Người dùng mở đăng nhập"] --> C{"Chọn phương thức"}
    C -->|"Passkey"| P["WebAuthn challenge"]
    P --> PV{"Assertion hợp lệ?"}
    PV -->|"Có"| S["Thiết lập phiên theo chính sách"]
    PV -->|"Không / không khả dụng"| F["Luồng fallback được kiểm soát"]
    C -->|"Mật khẩu fallback"| F
    F --> PW["Kiểm tra mật khẩu và chính sách"]
    PW --> M{"Có yêu cầu MFA bổ sung?"}
    M -->|"Có"| MF["Xác minh yếu tố bổ sung"]
    MF --> OK{"Đạt chính sách?"}
    M -->|"Không"| OK
    OK -->|"Có"| S
    OK -->|"Không"| X["Từ chối / khôi phục / thử lại có giới hạn"]
    S --> A["API kiểm tra phiên và quyền"]
~~~

Sơ đồ cho thấy cả passkey và password fallback có thể dẫn đến phiên, nhưng **ngữ cảnh xác thực của chúng có thể khác nhau**. Ứng dụng không được gán cùng một mức bảo đảm cho hai đường chỉ vì cả hai đều hiển thị “Đăng nhập thành công”.

### Fallback trở thành điểm yếu nhất khi nào?

- Passkey được yêu cầu cho đăng nhập chính nhưng mật khẩu đơn lẻ vẫn mở toàn bộ tài khoản.
- Mật khẩu fallback không có giới hạn thử hoặc kiểm tra rủi ro.
- Reset password chỉ cần truy cập email dễ bị chiếm.
- Đăng nhập bằng mật khẩu có thể thêm passkey mới mà không xác thực lại đủ mạnh.
- Hệ thống không phân biệt phiên được tạo bằng passkey và phiên được tạo bằng mật khẩu.
- Các thao tác nhạy cảm không yêu cầu xác thực lại, dù phiên được tạo qua fallback.
- Sau khi đổi mật khẩu, session/token cũ và authenticator đáng ngờ vẫn hoạt động.

Nếu đường fallback có bảo đảm thấp hơn, hệ thống cần **ghi nhận và áp chính sách tương ứng**. Ví dụ, người dùng có thể được xem nội dung thông thường nhưng cần passkey hoặc step-up phù hợp trước khi thay đổi thông tin khôi phục, thêm credential, xuất dữ liệu nhạy cảm hoặc phê duyệt giao dịch.

## 4. Các lựa chọn thay thế trước khi dùng mật khẩu

Fallback không nhất thiết phải là mật khẩu. Trước khi bật đường password, hãy xem xét các phương thức thay thế sau:

| Phương thức | Khi hữu ích | Rủi ro/điều cần quản lý |
| --- | --- | --- |
| **Passkey thứ hai** | Người dùng có thêm thiết bị đã đăng ký hoặc passkey đồng bộ trong hệ sinh thái phù hợp. | Tài khoản nền tảng đồng bộ passkey và thiết bị của người dùng cũng cần được bảo vệ. |
| **Khóa bảo mật dự phòng** | Tài khoản quan trọng, người dùng có thể giữ một khóa ở nơi an toàn. | Mất cả khóa chính và dự phòng; cần quy trình thu hồi và thay thế. |
| **Passkey đồng bộ** | Người dùng chuyển thiết bị trong hệ sinh thái có hỗ trợ đồng bộ. | Độ tin cậy phụ thuộc vào bảo vệ tài khoản đồng bộ, khôi phục và chính sách nhà cung cấp. |
| **Authenticator dự phòng** | TOTP hoặc phương thức khác đã đăng ký trước để dự phòng. | Mã TOTP vẫn có thể bị phishing; cần bảo vệ bí mật và thiết bị dự phòng. |
| **Mã khôi phục dùng một lần** | Người dùng lưu trước mã dự phòng khi còn kiểm soát tài khoản. | Mã là bearer secret; cần entropy cao, lưu an toàn, dùng một lần và thu hồi sau sử dụng. |
| **Thiết bị tin cậy / phiên hiện có** | Người dùng còn một thiết bị hoặc phiên đã xác thực đáng tin cậy. | Phiên có thể bị chiếm hoặc đã quá cũ; cần kiểm tra trạng thái và độ mới. |
| **Hỗ trợ khôi phục có kiểm chứng** | Người dùng mất toàn bộ authenticator. | Social engineering, sai sót của nhân viên, chi phí vận hành và quyền riêng tư. |
| **Mật khẩu + yếu tố bổ sung** | Sản phẩm vẫn phải hỗ trợ một số môi trường hoặc người dùng không thể dùng passkey. | Mật khẩu vẫn phishable; MFA cần độc lập và có chính sách rõ ràng. |

Không có lựa chọn nào miễn phí rủi ro. Ví dụ, passkey đồng bộ giúp người dùng đổi thiết bị thuận tiện nhưng cần đánh giá cách tài khoản đồng bộ được khôi phục. Một khóa bảo mật dự phòng độc lập có thể hữu ích nhưng nếu người dùng để cả hai khóa cùng một nơi thì mất một sự cố có thể làm mất cả hai.

**Khả năng dự phòng nên được thiết lập khi người dùng còn quyền kiểm soát tài khoản**, thay vì đợi đến lúc mất thiết bị rồi mới tạo một đường thay thế vội vàng.

## 5. Chính sách khi passkey không khả dụng

Không phải mọi lỗi WebAuthn đều có nghĩa người dùng mất passkey. Có thể do người dùng hủy hộp thoại, thiết bị không có credential phù hợp, trình duyệt không hỗ trợ, khóa bị thu hồi hoặc challenge hết hạn.

Hệ thống cần phân loại kết quả ở mức đủ để đưa ra trải nghiệm phù hợp, nhưng tránh tiết lộ thông tin tài khoản cho người chưa xác thực.

| Tình huống | Cách xử lý phù hợp |
| --- | --- |
| Người dùng chủ động hủy hộp thoại passkey | Cho phép thử lại hoặc chọn phương thức khác theo chính sách. Không đánh dấu tài khoản bị xâm nhập chỉ vì người dùng hủy. |
| Thiết bị hiện tại không có passkey phù hợp | Hiển thị lựa chọn thiết bị/credential khác hoặc phương thức dự phòng đã được phép. |
| Challenge hết hạn | Bắt đầu transaction mới và phát challenge mới; không dùng lại challenge cũ. |
| Assertion sai chữ ký hoặc origin/RP ID không hợp lệ | Từ chối, ghi sự kiện phù hợp và áp kiểm soát lạm dụng; không tự hạ cấp sang mật khẩu mà không có chủ đích. |
| Credential bị thu hồi hoặc tài khoản bị khóa | Không tiếp tục dùng credential đó; chuyển sang quy trình khôi phục/kiểm tra trạng thái. |
| Người dùng mất toàn bộ thiết bị | Chuyển sang account recovery với mức kiểm chứng phù hợp. |
| Người dùng không thể sử dụng sinh trắc học | Cho phép phương thức user verification thay thế được authenticator hỗ trợ, chẳng hạn PIN cục bộ, nếu chính sách cho phép. |

### Không tự động downgrade sau lỗi passkey

Một thiết kế nguy hiểm là: bất cứ khi nào WebAuthn trả lỗi, ứng dụng lập tức hiện form mật khẩu hoặc tự chuyển sang password fallback. Điều này có thể:

- Biến lỗi tạm thời hoặc bị attacker kích hoạt thành đường hạ cấp.
- Làm người dùng quen với việc nhập mật khẩu sau một hộp thoại passkey thất bại.
- Tạo giao diện thuận lợi cho phishing và dò tài khoản.
- Che khuất khác biệt giữa người dùng hủy, thiết bị không hỗ trợ và assertion không hợp lệ.

Tốt hơn là phân biệt trạng thái đủ tin cậy để hỗ trợ UX, yêu cầu người dùng chủ động chọn phương thức thay thế và để server kiểm tra chính sách fallback. Không tiết lộ chi tiết nhạy cảm như tài khoản có tồn tại hoặc loại credential cụ thể nếu người gửi chưa được xác thực.

## 6. Khi nào nên giữ mật khẩu fallback?

Quyết định này phụ thuộc đối tượng người dùng, mức rủi ro, yêu cầu trợ năng, thiết bị hỗ trợ và năng lực vận hành recovery.

### Có thể cân nhắc giữ fallback khi:

- Sản phẩm cần hỗ trợ người dùng có thiết bị cũ hoặc môi trường chưa hỗ trợ passkey.
- Người dùng có tình huống hợp lệ thường xuyên mất quyền truy cập thiết bị chính.
- Hệ thống có thể áp kiểm soát mật khẩu, MFA, giới hạn thử và giám sát phù hợp.
- Có chính sách rõ về thao tác nào được phép sau đăng nhập fallback và thao tác nào cần step-up.
- Tổ chức có khả năng hỗ trợ người dùng và ứng phó khi fallback bị lạm dụng.

### Nên tránh hoặc giới hạn mạnh khi:

- Tài khoản có quyền quản trị, tài sản tài chính hoặc dữ liệu có hậu quả cao.
- Mục tiêu sản phẩm yêu cầu xác thực chống phishing và password fallback phá vỡ yêu cầu đó.
- Mật khẩu fallback chỉ được bảo vệ bằng email hoặc kênh dễ bị chiếm.
- Không thể phân biệt ngữ cảnh passkey và password trong phiên.
- Hệ thống không thể thu hồi phiên/token hoặc xử lý credential bị lộ.
- Fallback cho phép thay email, gỡ MFA hoặc thêm authenticator mà không có xác minh bổ sung.

Không nên giữ mật khẩu chỉ vì “có thể một ngày người dùng cần”. Cần có lý do sản phẩm và mô hình đe dọa cụ thể; nếu giữ, phải xem fallback là một **phương thức xác thực thực sự** cần quản lý vòng đời, chứ không phải nút phụ không cần bảo vệ.

## 7. Nếu giữ mật khẩu: bảo vệ credential và lần đăng nhập

### 7.1 Lưu trữ và kiểm tra mật khẩu

- Truyền mật khẩu qua HTTPS/TLS.
- Lưu bằng thuật toán băm mật khẩu chuyên dụng, có salt riêng, chẳng hạn Argon2id với tham số phù hợp môi trường.
- Không lưu mật khẩu rõ, không log mật khẩu và không gửi lại mật khẩu qua email.
- Kiểm tra mật khẩu mới so với danh sách phổ biến/bị lộ khi chính sách và nguồn dữ liệu cho phép.
- Khuyến khích password manager và mật khẩu duy nhất cho dịch vụ.
- Kiểm soát thử sai theo tài khoản, nguồn, thiết bị, thời gian và dấu hiệu hành vi; tránh khóa cứng dễ bị dùng để DoS người dùng.
- Không tiết lộ quá nhiều qua thông báo lỗi, thời gian phản hồi hoặc API dò tài khoản.

Không dùng hàm băm nhanh thông thường như SHA-256 đơn lẻ để lưu mật khẩu. Việc bảo vệ bản băm cần được thiết kế cùng quản lý secret, backup, quyền truy cập kho credential và kế hoạch nâng cấp tham số.

### 7.2 Có cần MFA sau mật khẩu fallback không?

Nếu chính sách yêu cầu MFA, mật khẩu đúng chỉ hoàn tất **yếu tố thứ nhất**. Hệ thống không được cấp full session trước khi yếu tố bổ sung hợp lệ.

Tuy nhiên, MFA bằng TOTP/SMS không tự chống phishing thời gian thực. Nếu mục tiêu của passwordless là giảm nguy cơ phishing, mật khẩu + OTP có thể không tương đương passkey. Với thao tác nhạy cảm, nên yêu cầu phương thức chống phishing hoặc quy trình step-up đáp ứng mức bảo đảm đã chọn.

### 7.3 Ghi ngữ cảnh xác thực

Khi tạo phiên, server có thể lưu ngữ cảnh tin cậy như:

- Chủ thể/tài khoản nội bộ.
- Phương thức đã dùng: password, passkey, recovery code hoặc IdP.
- Thời điểm xác thực thực sự hoàn tất.
- Có MFA hay không và các điều kiện chính sách đã đạt.
- Transaction, nguồn phát hành và các giới hạn phiên cần thiết.
- Trạng thái cần step-up trước thao tác nhạy cảm.

Đây phải là dữ liệu do server/IdP tin cậy ghi nhận, không phải cờ passwordless=true, mfaPassed=true do client tự gửi.

## 8. Mật khẩu fallback không nên tự nâng quyền sau đăng nhập

Một nguyên tắc hữu ích là **phân biệt trạng thái phiên theo cách xác thực đã hoàn thành**. Ví dụ, phiên tạo bằng passkey có thể đáp ứng chính sách chống phishing cho một số hành động; phiên tạo bằng mật khẩu fallback có thể chỉ cho phép tác vụ thông thường.

| Hành động | Phiên passkey đáp ứng chính sách | Phiên mật khẩu fallback |
| --- | --- | --- |
| Xem nội dung không nhạy cảm | Có thể cho phép nếu phiên và quyền hợp lệ. | Có thể cho phép nếu chính sách sản phẩm cho phép. |
| Xem hồ sơ cá nhân | Kiểm tra phiên, quyền và độ mới. | Kiểm tra phiên, quyền; có thể yêu cầu thêm yếu tố theo rủi ro. |
| Đổi mật khẩu hoặc email khôi phục | Có thể vẫn yêu cầu xác thực lại/step-up. | Không nên dựa vào chính phiên fallback cũ; yêu cầu xác thực tăng cường phù hợp. |
| Thêm passkey mới hoặc gỡ passkey cũ | Xác minh lại đủ mạnh, ràng buộc thao tác và thông báo. | Cần step-up theo chính sách; nếu không đủ thì chuyển recovery được kiểm chứng. |
| Xuất dữ liệu nhạy cảm hoặc giao dịch rủi ro cao | Xét độ mới, quyền và xác nhận nghiệp vụ. | Không mặc nhiên cho phép; yêu cầu phương thức đủ bảo đảm. |
| Quản trị tài khoản hoặc cấp quyền | Kiểm tra quyền riêng và xác thực mạnh theo chính sách. | Có thể bị từ chối hoặc bắt buộc step-up bằng phương thức chống phishing. |

Bảng chỉ là ví dụ chính sách; mỗi sản phẩm phải xác định yêu cầu theo tài sản và hậu quả. Không nên mặc định rằng passkey luôn đủ cho mọi thao tác, cũng không nên mặc định rằng mật khẩu fallback luôn chỉ được phép đọc. Điều cần có là **chính sách server-side rõ ràng**.

### Ví dụ về ngữ cảnh phiên

~~~text
AuthenticationContext
  subjectId: "account-42"
  method: "password"
  mfaSatisfied: true
  phishingResistant: false
  authenticatedAt: 2026-11-22T08:30:00Z
  recoveryUsed: false
  sessionId: <opaque server-side reference>
~~~

Đây là cấu trúc minh họa, không phải schema chuẩn. Trường phishingResistant chỉ nên được đặt dựa trên kết quả thực thi và profile đã được định nghĩa; không suy ra chỉ từ tên phương thức. Tương tự, mfaSatisfied không đủ nếu ứng dụng không biết nguồn và ngữ nghĩa của kết quả.

## 9. Khôi phục tài khoản khi người dùng mất passkey

Nếu người dùng mất thiết bị chứa passkey, việc khôi phục cần xác định họ còn kiểm soát yếu tố nào. Không phải mọi trường hợp đều cần quy trình thủ công; nếu người dùng có passkey đồng bộ hoặc khóa dự phòng, họ có thể tiếp tục đăng nhập qua phương thức đó.

### 9.1 Thứ tự lựa chọn dự phòng

Một chính sách có thể ưu tiên theo hướng:

1. Dùng passkey khác hoặc khóa bảo mật dự phòng đã đăng ký.
2. Dùng passkey đồng bộ qua tài khoản nền tảng đã được bảo vệ, nếu chính sách chấp nhận mức tin cậy đó.
3. Dùng authenticator dự phòng hoặc mã khôi phục được cấp trước.
4. Dùng phương thức fallback đã đăng ký (ví dụ mật khẩu + MFA) nếu tài khoản và rủi ro cho phép.
5. Chuyển sang quy trình recovery có kiểm chứng/hỗ trợ khi mất mọi phương thức.

Thứ tự không phải quy tắc bắt buộc cho mọi sản phẩm. Cần xét mức rủi ro, thiết bị, người dùng và khả năng xác minh; không được coi email hoặc số điện thoại đơn lẻ là bằng chứng mạnh cho mọi tài khoản.

### 9.2 Mã khôi phục

Mã khôi phục (recovery code) thường là bí mật có entropy cao, dùng một lần hoặc theo bộ mã được quản lý. Vì ai nắm mã có thể khôi phục quyền truy cập, cần:

- Sinh ngẫu nhiên bằng nguồn an toàn, đủ độ dài/entropy.
- Hiển thị cho người dùng tại thời điểm đăng ký khi họ còn kiểm soát tài khoản.
- Yêu cầu lưu ở nơi an toàn; không gửi mã rõ qua email hoặc log.
- Lưu phía server dưới dạng hash hoặc dạng bảo vệ phù hợp; không lưu bản rõ nếu không cần.
- Đánh dấu đã dùng ngay khi chấp nhận và từ chối phát lại.
- Cho phép tạo bộ mã mới qua quy trình đủ tin cậy; vô hiệu hóa bộ cũ.
- Thông báo sau khi mã được sử dụng và cân nhắc step-up trước thao tác nhạy cảm.

Recovery code là **credential khôi phục**, không phải mật khẩu dùng chung vô thời hạn. Không nên dùng cùng một mã nhiều lần hoặc cho phép mã khôi phục tự động gỡ mọi biện pháp bảo vệ mà không có giới hạn.

### 9.3 Khôi phục thủ công qua hỗ trợ

Nếu người dùng mất mọi authenticator, hỗ trợ thủ công có thể cần thiết. Quy trình nên:

1. Tiếp nhận yêu cầu qua kênh hỗ trợ chính thức.
2. Xác minh bằng nhiều bằng chứng phù hợp với mức rủi ro, không chỉ thông tin dễ tìm thấy trên mạng.
3. Tách người xác minh, người phê duyệt và người thực hiện nếu thao tác có hậu quả cao.
4. Có thời gian chờ hoặc kiểm tra bổ sung trong tình huống rủi ro cao, nếu phù hợp.
5. Ghi audit ai yêu cầu, ai kiểm tra, ai phê duyệt, ai thay credential và khi nào.
6. Thông báo cho các kênh liên hệ đã đăng ký trước nếu còn đáng tin cậy.
7. Sau khôi phục, yêu cầu đăng ký authenticator mới và xem xét thu hồi phiên/credential cũ.

Nhân viên hỗ trợ không được yêu cầu người dùng đọc mật khẩu, OTP hoặc private key. Câu hỏi bảo mật có câu trả lời dễ tìm hoặc đoán không nên là bằng chứng chính cho tài khoản quan trọng.

## 10. Thiết kế luồng fallback an toàn

Một luồng fallback có thể được thiết kế thành các bước sau:

1. **Người dùng chọn phương thức thay thế:** giao diện giải thích họ đang dùng password fallback và những hành động nào có thể yêu cầu xác thực mạnh hơn.
2. **Server tạo transaction mới:** ràng buộc với tài khoản/luồng, có thời hạn và chống lặp.
3. **Kiểm tra trạng thái tài khoản:** tài khoản có hoạt động, có cho phép fallback và có bị khóa/chặn do sự cố không?
4. **Xác minh mật khẩu:** kiểm tra bản băm, rate limit và tín hiệu rủi ro; không lộ tài khoản qua response.
5. **Hoàn tất yếu tố bổ sung nếu chính sách yêu cầu:** yếu tố phải gắn đúng tài khoản và transaction.
6. **Ghi ngữ cảnh xác thực:** method, thời điểm, MFA, mức bảo đảm theo policy và trạng thái recovery.
7. **Tạo phiên mới có giới hạn:** xoay session ID, thời hạn và scope phù hợp; không cấp quyền vượt chính sách.
8. **Thông báo sự kiện cần thiết:** đặc biệt nếu fallback bất thường hoặc theo sau là thay đổi bảo mật.
9. **Kiểm tra quyền ở API:** xác minh phiên và quyền trên từng tài nguyên; yêu cầu step-up nếu hành động nhạy cảm.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Browser / App
    participant A as Authentication service
    participant D as Account / Credential store
    participant S as Session service
    participant API as Resource API
    U->>C: Chọn "Dùng phương thức khác"
    C->>A: Bắt đầu password fallback
    A->>D: Kiểm tra trạng thái tài khoản và policy
    D-->>A: Tài khoản và credential hợp lệ
    A-->>C: Form / transaction có thời hạn
    U->>C: Nhập mật khẩu và yếu tố cần thiết
    C->>A: Trình bằng chứng
    A->>A: Verify password, MFA, rate/risk policy
    A->>D: Ghi nhận ngữ cảnh xác thực
    A->>S: Tạo phiên mới với policy phù hợp
    S-->>A: Session reference
    A-->>C: Kết quả và cookie bảo vệ
    C->>API: Request với phiên
    API->>S: Xác minh phiên và ngữ cảnh
    S-->>API: Subject và policy context
    API->>API: Kiểm tra quyền và step-up nếu cần
    API-->>C: Trả dữ liệu được phép
~~~

Không phải tất cả ứng dụng đều cần session service riêng; sơ đồ thể hiện trách nhiệm logic. **Client không được quyết định** phiên fallback có quyền gì. Server phải lưu và kiểm tra ngữ cảnh đã xác minh.

## 11. Quản lý thay đổi credential sau fallback

Một trong những tình huống rủi ro cao nhất là người dùng đăng nhập bằng password fallback rồi thay đổi yếu tố passwordless.

Ví dụ: kẻ tấn công có password và đã qua MFA yếu, sau đó thêm passkey của mình. Nếu server cho phép enrollment chỉ dựa vào phiên vừa tạo mà không xác thực lại, attacker có thể duy trì quyền ngay cả khi chủ tài khoản đổi mật khẩu.

### Yêu cầu bảo vệ thao tác

- Thêm passkey, gỡ passkey, đổi mật khẩu, thay email/số khôi phục và tắt MFA đều là thao tác nhạy cảm.
- Yêu cầu xác thực lại/step-up dựa trên chính sách, độ mới và phương thức trước đó.
- Không cho phép một phiên pending MFA hoặc phiên bị giới hạn tự thay đổi authenticator.
- Thông báo qua kênh cũ hoặc kênh độc lập đã đăng ký khi có thể.
- Có khả năng thu hồi credential/phiên bị nghi lộ.
- Ghi audit và xử lý xung đột nếu credential đang gắn với tài khoản khác.
- Cân nhắc thời gian chờ hoặc phê duyệt cho thao tác rủi ro rất cao.

### Thứ tự sự kiện mẫu

~~~text
1. User authenticates using password fallback.
2. Server creates a session with fallback authentication context.
3. User requests to add a new passkey.
4. Server checks whether this session and its authentication age
   meet the enrollment policy.
5. If not, server requires step-up using an accepted authenticator
   or starts account recovery.
6. User completes WebAuthn registration.
7. Server validates challenge, origin, RP ID and registration data.
8. Server binds the new public key to the correct account.
9. Server notifies the account owner and records the change.
10. Server evaluates old sessions and authenticators under policy.
~~~

Đây là trình tự khái niệm. Đăng ký WebAuthn thực tế cần kiểm tra toàn bộ dữ liệu registration theo giao thức và cấu hình RP; không chỉ lưu khóa công khai nhận từ client.

## 12. Phát hiện và giám sát việc lạm dụng fallback

Fallback có thể trở thành mục tiêu tấn công riêng. Hệ thống nên quan sát cả **số lần sử dụng** lẫn **chuỗi sự kiện trước/sau**.

| Tín hiệu | Có thể chỉ ra | Hành động đánh giá |
| --- | --- | --- |
| Tỷ lệ password fallback tăng đột ngột | Passkey/IdP gặp sự cố hoặc có chiến dịch tấn công. | So sánh theo phiên bản app, thiết bị, vùng và thời gian; xác minh nguyên nhân. |
| Một nguồn thử mật khẩu trên nhiều tài khoản | Credential stuffing/password spraying. | Rate limit, phân tích cụm và kiểm soát lạm dụng. |
| Đăng nhập fallback sau nhiều lần WebAuthn thất bại | Người dùng gặp sự cố hoặc attacker đang ép downgrade. | Xem loại lỗi, ngữ cảnh thiết bị, hành động tiếp theo và rủi ro. |
| Fallback rồi đổi email khôi phục ngay | Có thể là attacker đang củng cố quyền. | Step-up, thông báo, trì hoãn hoặc kiểm tra bổ sung theo chính sách. |
| Fallback rồi thêm passkey mới | Có thể là thay thế hợp lệ hoặc enrollment trái phép. | Xác minh lại, kiểm tra độ mới, thông báo và audit. |
| Nhiều reset hoặc recovery code được dùng | Lạm dụng recovery hoặc người dùng mất thiết bị. | Giới hạn, phát hiện chuỗi và hỗ trợ an toàn. |
| Cùng phiên xuất hiện dấu hiệu bất thường | Cookie/token có thể bị chia sẻ hoặc đánh cắp. | Thu hồi/step-up tùy bằng chứng và tác động. |

Không nên kết luận ATO chỉ vì một người dùng chọn fallback. Người dùng hợp lệ có thể thường xuyên đổi thiết bị hoặc không sử dụng được passkey. Cần kết hợp tín hiệu, bối cảnh và hành động tiếp theo để giảm false positive.

### Log nên có và log cần tránh

Nên ghi sự kiện có cấu trúc:

- Tài khoản nội bộ hoặc định danh đã bảo vệ.
- Phương thức đăng nhập đã dùng và lý do fallback ở mức phân loại.
- Transaction ID, thời gian, kết quả, mã lý do và trạng thái MFA.
- Sự kiện thêm/gỡ authenticator, reset, dùng recovery code, thu hồi phiên.
- Actor và người phê duyệt đối với thao tác hỗ trợ.
- Kết quả kiểm tra quyền với thao tác nhạy cảm.

Không ghi mật khẩu, OTP, secret TOTP, recovery code rõ, private key, raw cookie/session ID hoặc access/refresh token. Dùng ID audit riêng để liên kết sự kiện.

## 13. Ứng phó khi fallback bị lạm dụng

Khi nghi ngờ mật khẩu fallback bị chiếm, chỉ đổi mật khẩu có thể không đủ. Attacker có thể đã tạo phiên, thêm authenticator, lấy refresh token hoặc đổi kênh khôi phục.

Một quy trình ứng phó nên:

1. **Đánh giá tín hiệu:** xác định lần fallback, transaction, tài khoản, thiết bị, IP/tín hiệu rủi ro và các hành động tiếp theo.
2. **Hạn chế hành động nhạy cảm:** nếu cần, tạm chặn đổi credential, thanh toán, export hoặc quản trị cho tới khi xác minh.
3. **Thu hồi phiên/token:** chấm dứt session và refresh token theo cơ chế của hệ thống; xem giới hạn với token tự chứa còn hiệu lực.
4. **Rà soát authenticator:** kiểm tra passkey, TOTP, khóa bảo mật và phương thức khôi phục vừa thêm/thay đổi.
5. **Xác minh chủ tài khoản:** dùng quy trình recovery an toàn, không yêu cầu mật khẩu hoặc OTP.
6. **Khôi phục:** đặt credential mới, gỡ authenticator trái phép, thiết lập passkey/khóa dự phòng và thông báo.
7. **Kiểm tra tác động:** xem dữ liệu đã đọc/xuất, thay đổi hồ sơ, giao dịch và ứng dụng liên kết.
8. **Cải thiện:** xác định vì sao fallback được sử dụng, có lỗ hổng policy/rate limit/recovery hay không và cập nhật test.

Nếu một phiên được cấp bằng password fallback không đáp ứng chính sách của thao tác, server nên yêu cầu step-up hoặc từ chối hành động đó. Không nâng mức assurance chỉ vì người dùng đã sử dụng phiên lâu hoặc vừa refresh token.

## 14. Ví dụ thiết kế cho nền tảng học tập

Giả sử nền tảng học tập hỗ trợ passkey là phương thức chính. Một số học viên không có thiết bị tương thích, nên sản phẩm vẫn cho phép mật khẩu fallback kèm TOTP.

### 14.1 Chính sách mẫu

| Hành động | Phương thức được chấp nhận trong ví dụ | Ghi chú |
| --- | --- | --- |
| Đăng nhập thông thường | Passkey; hoặc password + TOTP theo policy | Hai đường có ngữ cảnh xác thực khác nhau. |
| Xem khóa học đã ghi danh | Phiên hợp lệ và quyền ghi danh | Không dựa vào userId từ URL để quyết định chủ thể. |
| Thay email khôi phục | Xác thực lại đủ mạnh theo policy | Không chấp nhận chỉ vì phiên fallback còn hạn. |
| Thêm/gỡ passkey | Step-up và kiểm tra quyền quản lý tài khoản | Ghi audit và thông báo thay đổi. |
| Xem/xuất dữ liệu học tập nhạy cảm | Kiểm tra phiên, quyền, độ mới và rủi ro | Có thể yêu cầu xác thực tăng cường. |
| Khôi phục khi mất mọi thiết bị | Recovery code hoặc quy trình hỗ trợ có kiểm chứng | Không mặc định email là bằng chứng đủ mạnh. |

### 14.2 Luồng cụ thể

1. Học viên mở trang đăng nhập và chọn passkey.
2. Passkey không khả dụng trên thiết bị hiện tại; người dùng chủ động chọn **“Dùng phương thức khác”**.
3. Server kiểm tra tài khoản và policy cho biết tài khoản có được dùng password fallback không.
4. Người dùng nhập mật khẩu và hoàn tất TOTP đã đăng ký.
5. Server ghi nhận phiên được tạo bằng password + TOTP, có thời điểm và trạng thái chính sách phù hợp.
6. Học viên xem tiến độ khóa học; API kiểm tra phiên và quyền trên khóa học.
7. Học viên yêu cầu đổi email khôi phục; API nhận thấy hành động cần step-up mạnh hơn hoặc độ mới phù hợp.
8. Hệ thống yêu cầu passkey đã đăng ký khác, khóa bảo mật dự phòng hoặc quy trình recovery được chấp nhận. Nếu không có, thao tác được chuyển sang khôi phục thay vì tự động cho phép bằng email.
9. Sau khi xác minh đủ, hệ thống thực hiện thay đổi, thông báo và ghi audit.

Ví dụ cho thấy fallback có thể giữ khả năng truy cập cơ bản mà vẫn giới hạn thao tác có khả năng chuyển quyền kiểm soát tài khoản.

## 15. Yêu cầu bảo mật có thể kiểm thử

| ID | Yêu cầu | Bằng chứng kiểm thử |
| --- | --- | --- |
| PF-01 | Fallback phải được cấu hình theo policy của tài khoản và trạng thái hệ thống. | Tài khoản không được phép fallback bị từ chối kể cả khi client tự mở form. |
| PF-02 | Lỗi/hủy WebAuthn không tự động cấp phiên bằng mật khẩu. | Test hủy, timeout, sai assertion; không có full session nếu chưa qua phương thức khác. |
| PF-03 | Mật khẩu fallback phải có rate limit và kiểm tra credential an toàn. | Test thử sai, credential stuffing giả lập, response không tiết lộ tài khoản. |
| PF-04 | MFA bắt buộc phải hoàn tất trước khi cấp full session. | Dừng sau password; API dữ liệu riêng tư từ chối pending state. |
| PF-05 | Server ghi nhận đúng phương thức và thời điểm xác thực. | So sánh ngữ cảnh phiên sau passkey và password fallback; client không sửa được. |
| PF-06 | Thao tác nhạy cảm yêu cầu step-up theo policy. | Phiên fallback không đủ điều kiện không thể đổi email/thêm authenticator. |
| PF-07 | Recovery code dùng một lần và không lưu bản rõ. | Test dùng lại mã, hết hạn, tạo bộ mới và kiểm tra log/storage. |
| PF-08 | Reset/recovery không tự động để lại phiên hoặc credential trái phép. | Test thu hồi session/refresh token và rà soát authenticator sau recovery. |
| PF-09 | Thay đổi email, password hoặc authenticator tạo sự kiện audit và thông báo phù hợp. | Kiểm tra sự kiện, actor, thời gian và không lộ secret. |
| PF-10 | API không tin cờ fallback/MFA/role do client tự gửi. | Sửa payload; server vẫn lấy ngữ cảnh từ phiên và policy tin cậy. |
| PF-11 | Liên kết IdP không dựa duy nhất vào email. | Hai issuer/subject khác nhau cùng email không tự động gộp. |
| PF-12 | Có thể hạn chế hoặc thu hồi phiên khi nghi ngờ ATO. | Test incident/revoke; request tiếp theo bị từ chối theo SLA/policy. |

## 16. Checklist thiết kế fallback

- [ ] Đã nêu lý do sản phẩm cần mật khẩu fallback.
- [ ] Đã phân biệt fallback đăng nhập với khôi phục tài khoản và thay authenticator.
- [ ] Đã đánh giá passkey dự phòng, khóa bảo mật, mã khôi phục và các lựa chọn không dùng mật khẩu.
- [ ] Đã xác định tài khoản/nhóm người dùng được phép dùng fallback.
- [ ] Đã xác định hành động nào bị giới hạn khi phiên được tạo qua fallback.
- [ ] Đã bảo vệ mật khẩu bằng hash chuyên dụng, salt, rate limit và kiểm soát lạm dụng.
- [ ] Đã kiểm tra MFA và không cấp full session trước khi hoàn tất.
- [ ] Đã lưu ngữ cảnh xác thực đáng tin cậy ở server.
- [ ] Đã bảo vệ thao tác thêm/gỡ authenticator, đổi email và reset.
- [ ] Đã thiết kế recovery code và hỗ trợ thủ công an toàn.
- [ ] Đã có thông báo, audit, phát hiện bất thường và thu hồi phiên/token.
- [ ] Đã kiểm thử downgrade, replay, session fixation, account enumeration và recovery abuse.
- [ ] Đã xem xét trợ năng, false positive, quyền riêng tư và khả năng người dùng lấy lại quyền truy cập.

## 17. Tự kiểm tra

**Câu 1.** Một ứng dụng quảng bá đăng nhập bằng passkey nhưng vẫn cho phép bất kỳ ai nhập mật khẩu đơn lẻ để vào cùng tài khoản. Rủi ro chính là gì?

**Đáp án:** Password fallback có thể trở thành đường yếu nhất và làm giảm lợi ích chống phishing của passkey. Attacker có thể nhắm vào mật khẩu qua phishing, credential stuffing hoặc reset yếu.

**Câu 2.** Người dùng hủy hộp thoại WebAuthn. Có nên tự động chuyển sang mật khẩu không?

**Đáp án:** Không nên tự động downgrade. Hủy có thể là lựa chọn chủ động hoặc tình huống tạm thời. Hãy cho phép người dùng chọn phương thức khác theo policy và server phải kiểm tra fallback độc lập.

**Câu 3.** Fallback đăng nhập khác account recovery thế nào?

**Đáp án:** Fallback dùng một phương thức thay thế đã đăng ký để hoàn tất lần đăng nhập. Recovery dùng khi người dùng mất hoặc không còn phương thức hợp lệ và cần chứng minh lại quyền kiểm soát tài khoản.

**Câu 4.** Vì sao password + TOTP vẫn không tương đương passkey về chống phishing?

**Đáp án:** Người dùng có thể nhập cả password và mã TOTP vào website giả; attacker chuyển tiếp ngay khi mã còn hiệu lực. WebAuthn ràng buộc assertion với RP ID/origin nên website khác không thể lấy assertion dùng cho RP thật theo cách tương tự.

**Câu 5.** Một phiên password fallback còn hạn có thể tự thêm passkey mới không?

**Đáp án:** Không mặc nhiên. Thêm authenticator là thao tác nhạy cảm; server phải kiểm tra quyền, độ mới và mức bảo đảm, yêu cầu step-up hoặc recovery nếu policy chưa đạt.

**Câu 6.** Vì sao email khôi phục không nên tự động là bằng chứng đủ cho tài khoản đặc quyền?

**Đáp án:** Hộp thư có thể bị chiếm, tái cấp hoặc bảo vệ bằng cùng mật khẩu yếu. Nếu chỉ cần email để thay mọi credential, attacker có thể bỏ qua passkey/MFA.

**Câu 7.** Recovery code cần có thuộc tính nào để giảm lạm dụng?

**Đáp án:** Được sinh ngẫu nhiên đủ entropy, dùng một lần, có thể hết hạn hoặc bị thu hồi, lưu dưới dạng hash/bảo vệ phù hợp, không ghi log và có thông báo sau khi sử dụng.

**Câu 8.** Nếu người dùng đăng nhập bằng mật khẩu fallback rồi đổi email khôi phục, hệ thống nên làm gì?

**Đáp án:** Đánh giá thao tác nhạy cảm, yêu cầu xác thực lại/step-up phù hợp, thông báo qua kênh đáng tin cậy trước đó khi có thể, ghi audit và xem xét phiên/token cũ.

**Câu 9.** Vì sao cần phân biệt phiên passkey và phiên password fallback?

**Đáp án:** Hai phương thức có đặc tính bảo mật và khả năng chống phishing khác nhau. Server cần ngữ cảnh xác thực để áp quyền, độ mới và step-up đúng chính sách thay vì coi mọi phiên như nhau.

**Câu 10.** Khi nghi ngờ fallback bị lạm dụng, chỉ đổi mật khẩu có đủ không?

**Đáp án:** Không. Cần rà soát và thu hồi phiên/token, refresh token, authenticator được thêm, email/số khôi phục, ứng dụng liên kết và các quyền bị thay đổi; đồng thời xác minh chủ tài khoản và kiểm tra tác động.

## Ghi nhớ

**Fallback về mật khẩu** giúp người dùng không bị khóa khỏi tài khoản khi passkey không khả dụng, nhưng đồng thời tạo một đường xác thực có thể bị phishing, đoán hoặc tái sử dụng. Nếu giữ fallback, phải xem nó như một phương thức đăng nhập thực sự: có policy, rate limit, MFA phù hợp, ngữ cảnh phiên, giám sát và khả năng thu hồi.

Thiết kế tốt cần ưu tiên authenticator dự phòng và recovery được thiết lập trước, phân biệt fallback với khôi phục, bảo vệ thay đổi credential, giới hạn hành động theo mức bảo đảm của phiên và yêu cầu step-up khi cần. **Không để một đường mật khẩu hoặc reset yếu vô hiệu hóa mục tiêu chống phishing của passwordless.**
