# Notification privacy — Bảo vệ quyền riêng tư trong thông báo xác thực

## 1. Notification privacy là gì?

**Notification privacy** là việc thiết kế, gửi, lưu trữ và hiển thị thông báo liên quan đến đăng nhập, MFA, thiết bị, credential, session và khôi phục tài khoản sao cho người nhận có đủ thông tin để nhận biết hoạt động quan trọng nhưng không làm lộ dữ liệu cá nhân hoặc bí mật xác thực. Thông báo có thể được gửi qua email, SMS, push notification, ứng dụng, trung tâm thông báo hoặc kênh hỗ trợ.

Ví dụ: người dùng nhận push “Có đăng nhập mới vào tài khoản của bạn”. Thông báo nên cho biết thời điểm, ứng dụng hoặc thiết bị ở mức vừa đủ và cách báo cáo nếu không phải họ thực hiện. Nó không nên chứa mật khẩu, OTP, recovery code, access token hay toàn bộ dữ liệu nhạy cảm của tài khoản. Nếu điện thoại đang khóa màn hình hoặc được chia sẻ, nội dung quá chi tiết có thể bị người khác nhìn thấy.

Trong chương **Error và privacy** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, notification privacy kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần mô hình hóa ranh giới tin cậy giữa hệ thống phát sự kiện, notification service, nhà cung cấp kênh, thiết bị và người nhận; giảm thiểu dữ liệu, chống phishing và tránh biến thông báo thành kênh rò rỉ danh tính hoặc bí mật.

**Thông báo bảo mật phải hữu ích nhưng không trở thành bằng chứng xác thực.** Việc nhận email hoặc push không tự chứng minh người nhận là chủ tài khoản; việc bấm một liên kết trong thông báo cũng không thay thế authentication và authorization. Thông báo chỉ là kênh truyền thông tin hoặc khởi tạo một quy trình có kiểm soát.

## 2. Vì sao thông báo xác thực có thể làm lộ dữ liệu?

Thông báo thường xuất hiện bên ngoài vùng giao diện đã xác thực. Chúng có thể hiển thị trên lock screen, màn hình xe, đồng hồ thông minh, màn hình máy tính dùng chung, hộp thư được forward hoặc thiết bị gia đình. Nội dung cũng có thể đi qua nhà cung cấp push, SMS gateway, email provider, hệ thống analytics và log vận hành.

Thông tin bị lộ có thể gồm:

- Tên thật, email, số điện thoại hoặc tên đăng nhập.
- Thời điểm, địa điểm gần đúng, IP hoặc thiết bị đăng nhập.
- Tên ứng dụng, tenant, tổ chức hoặc dịch vụ người dùng đang sử dụng.
- Việc một tài khoản tồn tại, đang hoạt động, bị khóa hoặc đã bật MFA.
- Một phần thông tin giao dịch, số dư, dữ liệu nhân sự hoặc tài nguyên được truy cập.
- Mã xác minh, recovery link, token hoặc thông tin có thể giúp attacker tiếp tục tấn công.

Ngay cả metadata tưởng như vô hại cũng có thể tiết lộ thói quen, lịch làm việc, quan hệ tổ chức hoặc thời điểm người dùng không có mặt. Cần đánh giá nội dung theo bối cảnh và người có thể nhìn thấy thông báo, không chỉ theo việc kênh có mã hóa hay không.

## 3. Các loại thông báo trong vòng đời xác thực

Thông báo nên được phân loại theo mục đích và mức nhạy cảm:

| Loại thông báo | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **Login alert** | Đăng nhập thành công từ thiết bị mới. | Giúp phát hiện truy cập không do chủ tài khoản thực hiện. |
| **Failed login alert** | Có nhiều lần đăng nhập thất bại đáng ngờ. | Cảnh báo hoạt động bất thường mà không tiết lộ trạng thái credential. |
| **MFA notification** | Có yêu cầu push approval hoặc thay đổi authenticator. | Giúp người dùng nhận biết và từ chối yêu cầu không khởi tạo. |
| **Credential change** | Mật khẩu, passkey, certificate hoặc API key được thêm/xóa. | Cảnh báo thay đổi có tác động lâu dài tới quyền truy cập. |
| **Device binding** | Thiết bị mới được liên kết hoặc bị thu hồi. | Giúp người dùng kiểm soát danh sách thiết bị. |
| **Password reset/recovery** | Có yêu cầu reset hoặc recovery đã hoàn tất. | Cảnh báo và hướng dẫn xử lý nếu yêu cầu không phải của người dùng. |
| **Session/token event** | Logout all sessions hoặc token bị thu hồi. | Giải thích thay đổi trạng thái truy cập. |
| **Federation/account linking** | Tài khoản liên kết với IdP hoặc ứng dụng mới. | Giúp phát hiện liên kết danh tính trái phép. |
| **Administrative event** | Tài khoản bị suspend hoặc thay đổi quyền. | Thông báo thay đổi do tổ chức thực hiện theo policy. |

Không phải mọi lần đăng nhập thất bại đều cần gửi một email riêng. Gửi quá nhiều thông báo có thể tạo notification fatigue, khiến người dùng bỏ qua cảnh báo quan trọng hoặc bị attacker lợi dụng để spam.

## 4. Ranh giới tin cậy của notification pipeline

Một pipeline điển hình có nguồn phát sự kiện, bộ dựng template, hàng đợi, nhà cung cấp và thiết bị người nhận:

~~~mermaid
flowchart LR
    AUTH["Auth / Credential service"]
    EVT["Security event"]
    POLICY["Notification policy<br/>minimize + classify"]
    Q[("Queue / outbox")]
    N["Notification service"]
    P["Email / SMS / Push provider"]
    U["Thiết bị / hộp thư người dùng"]
    AUD[("Audit / delivery metadata")]
    AUTH --> EVT
    EVT --> POLICY
    POLICY --> Q
    Q --> N
    N --> P
    P --> U
    POLICY --> AUD
    N --> AUD
~~~

Authentication service phát sự kiện có cấu trúc và mã lý do nội bộ. Notification policy quyết định có gửi hay không, qua kênh nào và nội dung nào được phép hiển thị. Notification service dựng nội dung từ template đã kiểm soát; provider vận chuyển thông điệp; thiết bị hoặc hộp thư hiển thị cho người nhận.

Mỗi ranh giới có rủi ro riêng:

- Event producer có thể gửi sai principal, tenant hoặc loại sự kiện.
- Queue có thể bị truy cập trái phép hoặc lưu payload quá chi tiết.
- Template engine có thể chèn dữ liệu chưa escape, gây HTML injection hoặc link giả.
- Provider có thể lưu metadata và nội dung theo chính sách riêng.
- Thiết bị có thể dùng chung, bị mất hoặc hiển thị nội dung trên lock screen.
- Delivery log có thể lưu email, số điện thoại, URL hoặc token không cần thiết.

Không đưa toàn bộ request authentication vào notification payload. Chỉ truyền event reference và các trường đã allowlist; notification service lấy dữ liệu tối thiểu từ nguồn tin cậy.

## 5. Nguyên tắc data minimization

Thông báo nên trả lời đúng các câu hỏi người dùng cần biết: điều gì vừa xảy ra, khoảng thời gian nào, có cần hành động không và báo cáo ở đâu nếu không phải họ. Mỗi trường bổ sung phải có lý do.

### Nên ưu tiên

- Loại sự kiện ở mức tổng quát.
- Tên dịch vụ/ứng dụng đã được xác minh.
- Thời gian theo múi giờ phù hợp.
- Thiết bị hoặc nền tảng ở mức khái quát nếu có ích.
- Vị trí gần đúng hoặc khu vực rộng, chỉ khi đáng tin và cần thiết.
- Hướng dẫn mở ứng dụng hoặc website chính thức để xem chi tiết.
- Kênh báo cáo hoạt động không nhận diện được.

### Nên tránh

- Mật khẩu, password hash, OTP, TOTP secret hoặc recovery code.
- Access token, refresh token, session cookie, authorization code.
- Private key, client secret, certificate private material.
- Recovery link chứa bearer token trong nội dung log/analytics hoặc bị forward không kiểm soát.
- Toàn bộ IP, tọa độ chính xác hoặc user agent dài nếu người dùng không cần.
- Email/số điện thoại đầy đủ trong lock-screen preview.
- Nội dung giao dịch hoặc dữ liệu cá nhân không liên quan tới cảnh báo.

Data minimization không có nghĩa bỏ mọi chi tiết cần thiết. Ví dụ, người dùng có thể cần phân biệt một thiết bị mới với thiết bị quen thuộc; khi đó tên thiết bị do người dùng đặt hoặc mô tả nền tảng ngắn có thể hữu ích. Hãy tránh thu thập thêm dữ liệu chỉ vì hệ thống có thể lấy được.

## 6. Nội dung trên lock screen và thiết bị dùng chung

Push notification và preview email có thể hiển thị khi điện thoại đang khóa. Người dùng cũng có thể bật đồng bộ thông báo sang đồng hồ, xe hơi, máy tính hoặc thiết bị gia đình.

Thiết kế an toàn:

- Mặc định dùng nội dung ngắn, không chứa dữ liệu cá nhân nhạy cảm.
- Cho phép người dùng chọn ẩn preview trên lock screen nếu nền tảng hỗ trợ.
- Không đưa OTP, recovery code hoặc nội dung xác nhận bí mật vào push preview.
- Với hành động nhạy cảm, yêu cầu mở ứng dụng chính thức và xác thực lại.
- Không tự động thực hiện thao tác chỉ vì notification được mở.
- Không giả định thiết bị đã đăng ký luôn chỉ do một người sử dụng.

Ví dụ, preview “Có yêu cầu thay đổi phương thức bảo mật. Mở ứng dụng để xem chi tiết” an toàn hơn thông báo nêu đầy đủ email, số điện thoại mới và tên authenticator. Người dùng đã mở ứng dụng và xác thực có thể xem thông tin cụ thể hơn.

## 7. Masking email, số điện thoại và định danh

Masking giúp giảm lộ thông tin nhưng không tự động biến dữ liệu thành vô danh:

| Dữ liệu | Cách hiển thị có thể phù hợp | Lưu ý |
| --- | --- | --- |
| Email | a***@example.com | Tên miền vẫn có thể tiết lộ tổ chức; không hiển thị đầy đủ trước khi xác minh. |
| Số điện thoại | ••• ••• 42 | Phần cuối có thể giúp người dùng nhận diện nhưng vẫn là dữ liệu cá nhân. |
| Username | Một phần đã che | Tránh xác nhận identifier tồn tại qua endpoint công khai. |
| Device name | Tên ngắn hoặc nhãn nền tảng | Tên do người dùng đặt có thể chứa dữ liệu nhạy cảm; cần giới hạn/escape. |
| IP/location | Khu vực rộng hoặc loại mạng | Địa lý IP không chính xác tuyệt đối và có thể gây hiểu nhầm. |

Không dùng masking để hợp thức hóa việc gửi dữ liệu tới sai người nhận. Trước khi gửi email/SMS, hệ thống phải lấy địa chỉ từ hồ sơ đã xác minh, không dùng địa chỉ tùy ý trong request client.

## 8. Thông báo đăng nhập mới và hoạt động bất thường

Login alert giúp người dùng nhận biết phiên mới, nhưng cần tránh làm lộ thông tin và tránh tạo cảnh báo sai:

- Gửi khi có sự kiện đáng kể theo policy, ví dụ thiết bị mới hoặc login rủi ro cao.
- Không nhất thiết gửi cho mọi request API hoặc refresh token.
- Dùng thời gian rõ ràng, có múi giờ hoặc nhãn “giờ địa phương”.
- Vị trí dựa trên IP nên được mô tả là ước lượng, không phải vị trí chính xác.
- Không hiển thị IP đầy đủ nếu người dùng không cần.
- Cung cấp hành động “Không phải tôi” dẫn tới quy trình chính thức, không yêu cầu gửi mật khẩu qua email.
- Khi có nhiều lần thất bại, có thể gộp theo khoảng thời gian để tránh spam.

Không tự động kết luận compromise chỉ từ một IP hoặc quốc gia mới. VPN, mạng di động, roaming và proxy doanh nghiệp có thể làm vị trí thay đổi. Cảnh báo cần diễn đạt trung tính: “Chúng tôi phát hiện hoạt động có thể bất thường” thay vì khẳng định chắc chắn tài khoản đã bị xâm nhập.

## 9. MFA push notification và notification fatigue

Push MFA có một rủi ro đặc biệt: attacker có thể gửi nhiều yêu cầu phê duyệt để người dùng mệt mỏi và vô tình bấm chấp thuận. Đây là **MFA fatigue** hoặc push bombing.

Biện pháp:

- Chỉ tạo push sau khi có login transaction hợp lệ và giới hạn số request.
- Có cooldown và rate limit theo account, device, source và toàn hệ thống.
- Dùng number matching hoặc hiển thị ngữ cảnh phù hợp khi phương thức hỗ trợ.
- Hiển thị dịch vụ và thao tác đang yêu cầu, tránh nội dung mơ hồ chỉ có nút Approve.
- Cho phép từ chối và báo cáo yêu cầu không do người dùng khởi tạo.
- Không gửi push liên tục khi người dùng đã từ chối hoặc challenge đã hết hạn.
- Theo dõi tỷ lệ deny, timeout và số push trên mỗi transaction.

Push notification không nên chứa OTP hoặc bí mật có thể sao chép. Nếu người dùng nhận push mà không đăng nhập, hướng dẫn họ từ chối và báo cáo qua ứng dụng chính thức.

## 10. Thông báo chứa OTP và recovery link

OTP qua SMS/email có thể là một phần của quy trình xác minh, nhưng cần hiểu rằng mã có thể bị đọc trên lock screen, forward, đồng bộ hoặc lừa người dùng cung cấp cho attacker.

### OTP

- Mã ngắn hạn, giới hạn số lần thử và gửi lại.
- Gắn với đúng account, transaction và purpose.
- Không ghi OTP vào log hoặc analytics.
- Không gửi cùng một mã qua nhiều kênh nếu policy không cần.
- Thông điệp nêu rõ “Không chia sẻ mã này với bất kỳ ai”, nhưng không coi cảnh báo đó là biện pháp bảo mật duy nhất.
- Không dùng OTP để thay thế passkey/phương thức chống phishing khi policy yêu cầu assurance cao.

### Recovery link

Recovery link có thể chứa bearer token. Nếu link bị forward, lộ trong browser history, Referer, proxy log hoặc hệ thống email, người khác có thể dùng nó.

- Token entropy cao, TTL ngắn, one-time use và purpose-bound.
- Không đưa token vào analytics, tracking pixel hoặc link shortener bên thứ ba.
- Dùng domain chính thức và HTTPS.
- GET chỉ hiển thị trang xác nhận; POST chủ động mới consume token và thay đổi trạng thái.
- Trang token hạn chế script bên thứ ba và đặt Referrer-Policy phù hợp.
- Không ghi URL đầy đủ chứa token vào access log.
- Sau khi hoàn tất, thông báo kết quả qua kênh đã xác minh trước đó.

Thông báo không được yêu cầu người dùng trả lời email bằng mật khẩu, OTP, recovery code hoặc private key. Nhân viên hỗ trợ cũng không được yêu cầu các bí mật đó.

## 11. Thông báo thay đổi credential và device binding

Thêm hoặc xóa credential có thể tạo đường truy cập lâu dài. Người dùng cần được thông báo khi:

- Mật khẩu được reset hoặc thay đổi.
- Passkey/security key mới được thêm hoặc thu hồi.
- TOTP/push authenticator được đăng ký, xóa hoặc thay thiết bị.
- Certificate hoặc API key được cấp, rotate hoặc revoke.
- Device binding mới được tạo hoặc bị hủy.
- Recovery method hoặc email/số điện thoại được thay đổi.

Thông báo nên nêu loại thay đổi, thời gian và cách xử lý nếu người dùng không thực hiện. Không hiển thị secret mới hoặc private key. Nếu thiết bị/kênh vừa được thêm chưa được tin cậy, gửi cảnh báo qua kênh đã xác minh trước đó; không chỉ gửi tới kênh mới.

Với thay đổi rủi ro cao, có thể áp dụng cooldown hoặc hạn chế thao tác nhạy cảm trong một khoảng thời gian theo policy. Thông báo phải giúp người dùng phản đối, nhưng không tự động rollback một thay đổi chỉ vì email được mở; cần quy trình xác minh và xử lý rõ ràng.

## 12. Thông báo account recovery

Recovery là thời điểm attacker có thể cố chiếm quyền kiểm soát tài khoản. Notification policy cần bảo vệ cả người yêu cầu lẫn chủ tài khoản:

- Khi có recovery request, gửi thông báo tới kênh đã xác minh trước đó nếu policy cho phép.
- Không tiết lộ trạng thái account trong response công khai.
- Khi recovery hoàn tất, thông báo các yếu tố được thay đổi/thu hồi ở mức metadata.
- Cho phép báo cáo nếu người dùng không khởi tạo recovery.
- Không gửi token, recovery code hoặc QR provisioning trong thông báo.
- Nếu email/số điện thoại vừa được thay đổi, cảnh báo qua kênh cũ hoặc kênh độc lập.
- Với helpdesk recovery, ghi actor/approver nhưng không tiết lộ dữ liệu nhân sự không cần thiết.

Thông báo recovery không được trở thành kênh bypass: bấm “Đây không phải tôi” có thể mở trang hỗ trợ hoặc quy trình hold, nhưng phải xác minh trước khi thay đổi credential hay cấp quyền.

## 13. Chống phishing và giả mạo thông báo

Attacker có thể giả mạo email hoặc SMS trông giống thông báo bảo mật để dẫn người dùng tới trang phishing:

- Dùng domain gửi chính thức và cấu hình SPF, DKIM, DMARC phù hợp.
- Tên hiển thị không phải bằng chứng nguồn gửi; người dùng cần có cách mở app/site chính thức độc lập.
- Không dùng URL rút gọn hoặc domain gần giống thương hiệu.
- Tránh yêu cầu đăng nhập từ link bất ngờ trong email; hướng dẫn mở ứng dụng hoặc gõ domain đã biết.
- Không yêu cầu cung cấp password, OTP, recovery code hoặc private key.
- Nội dung cần nhất quán, dễ nhận diện và không dùng ngôn ngữ gây hoảng sợ ép người dùng hành động ngay.
- Có kênh công khai để báo cáo email/SMS giả mạo.

SPF/DKIM/DMARC giảm một số dạng giả mạo domain nhưng không chứng minh nội dung thông báo là hợp lệ trong mọi trường hợp. Tài khoản gửi hợp pháp có thể bị chiếm; provider hoặc domain có thể cấu hình sai. Người dùng vẫn nên mở app chính thức để kiểm tra sự kiện nhạy cảm.

## 14. Account enumeration qua notification

Notification endpoint có thể vô tình xác nhận tài khoản tồn tại:

- Trang login trả thông báo chung, nhưng request “gửi cảnh báo đăng nhập” trả lỗi nếu email không tồn tại.
- Resend OTP chỉ phản hồi thành công khi account có thật.
- Người dùng có thể thử nhiều email và quan sát email nào nhận thông báo.
- SMS gateway timing hoặc response khác nhau theo số điện thoại.
- Push subscription endpoint tiết lộ account đã đăng ký thiết bị.

Biện pháp:

- Dùng response công khai đồng nhất khi phù hợp.
- Rate limit theo identifier, nguồn và toàn hệ thống.
- Không trả delivery receipt chi tiết cho client chưa xác thực.
- Chỉ gửi tới destination đã xác minh và lưu ở server.
- Không cung cấp API tra cứu notification history cho người chưa xác thực.
- Kiểm tra status code, body, timing và side channel ở login/recovery/resend endpoints.

Sau khi người dùng đã xác thực, có thể hiển thị lịch sử thông báo thuộc tài khoản của họ theo authorization policy.

## 15. Kênh gửi và rủi ro riêng

| Kênh | Ưu điểm | Rủi ro và biện pháp |
| --- | --- | --- |
| **Email** | Có thể lưu lịch sử và nội dung dài. | Hộp thư dùng chung/forward/takeover; không gửi secret, dùng domain chính thức và link an toàn. |
| **SMS** | Phổ biến, dễ tiếp cận. | SIM swap, preview, chuyển tiếp và phishing; không coi là chống phishing. |
| **Push** | Nhanh, có thể gắn với app đã đăng ký. | Lock-screen exposure, push fatigue và thiết bị dùng chung; giới hạn request, ẩn preview và number matching. |
| **In-app inbox** | Có thể hiển thị chi tiết sau authentication. | Cần kiểm soát session, authorization và retention; không để user khác truy cập. |
| **Voice call** | Hữu ích cho một số người dùng/trường hợp hỗ trợ. | Caller ID spoofing, nghe lén và social engineering; không đọc secret hoặc yêu cầu phê duyệt mơ hồ. |
| **Helpdesk** | Có thể xử lý tình huống phức tạp. | Insider abuse và giả danh; xác minh độc lập, dual control và audit. |

Không có kênh nào tự động an toàn chỉ vì nó phổ biến hoặc được mã hóa trên đường truyền. Cần đánh giá cả thiết bị đầu cuối, tài khoản nhà cung cấp và người có thể nhìn/nghe thông báo.

## 16. Nội dung template và chống injection

Thông báo thường được tạo từ template có dữ liệu người dùng, tên thiết bị hoặc tên tổ chức. Nếu không escape đúng ngữ cảnh, dữ liệu có thể gây HTML injection, link injection hoặc hiển thị nội dung giả:

- Escape HTML text và attribute theo đúng context.
- Không nối chuỗi trực tiếp để tạo URL hoặc HTML.
- Dùng allowlist cho scheme/domain của link.
- Không cho user-controlled device name chèn markup hoặc ký tự điều khiển.
- Không render remote image hoặc nội dung chủ động không cần thiết.
- Không đưa nội dung tùy ý từ log/error message vào email.
- Kiểm thử template trên email client, SMS và notification preview khác nhau.

Template cần có version, owner, review và quy trình rollback. Không cho phép event producer tự gửi HTML tùy ý hoặc override destination.

## 17. Privacy preference và thông báo bảo mật bắt buộc

Người dùng có thể muốn tắt email marketing hoặc giảm thông báo thông thường. Tuy nhiên, thông báo bảo mật quan trọng như reset password, thay đổi MFA hoặc đăng nhập rủi ro cao có thể cần được gửi theo policy và nghĩa vụ áp dụng.

Phân biệt:

- **Marketing/engagement:** thường có preference/consent riêng và cơ chế unsubscribe.
- **Product updates:** có thể tùy chọn theo cấu hình dịch vụ.
- **Security notifications:** phục vụ bảo vệ tài khoản; không nên bị tắt hoàn toàn nếu policy yêu cầu thông báo.
- **Operational messages:** thông báo sự cố hoặc thay đổi dịch vụ, theo policy và yêu cầu liên quan.

Cho người dùng chọn kênh, ngôn ngữ, mức preview hoặc tần suất gộp khi phù hợp. Không cho phép preference tắt cảnh báo critical theo cách làm người dùng mất khả năng phát hiện takeover. Nếu một kênh không còn khả dụng, cung cấp phương thức cập nhật contact đã xác minh.

## 18. Delivery status, retry và duplicate notification

Notification delivery không phải lúc nào cũng exactly-once. Queue có thể retry, provider có thể timeout sau khi đã nhận message, hoặc consumer xử lý lặp. Một sự kiện có thể tạo nhiều email/push nếu không có idempotency.

Thiết kế:

- Mỗi security event có event ID duy nhất.
- Notification record có idempotency key theo event, recipient, channel và template purpose.
- Consumer xử lý idempotent; retry không tạo spam.
- Phân biệt queued, accepted by provider, delivered, bounced, failed và unknown.
- Không ghi “đã gửi tới người dùng” chỉ dựa vào việc provider chấp nhận request.
- Retry có backoff, giới hạn và dead-letter handling.
- Với sự kiện critical, có thể fallback sang kênh khác theo policy nhưng không gửi secret qua kênh yếu hơn.

Provider delivery receipt chỉ cho biết một trạng thái vận chuyển, không chứng minh đúng chủ tài khoản đã đọc thông báo. Không dùng open pixel làm bằng chứng người dùng đã nhận biết hoặc phê duyệt.

## 19. Logging và retention cho notification

Log cần hỗ trợ điều tra nhưng không lưu nhiều dữ liệu hơn cần thiết:

### Có thể ghi

- Event ID/correlation ID.
- Loại thông báo và template version.
- Principal reference đã pseudonymize.
- Kênh và provider reference ở mức cần thiết.
- Thời điểm enqueue, provider accept, delivery/bounce/failure.
- Policy decision và reason code nội bộ.
- Actor/service tạo thông báo.

### Không nên ghi

- OTP, TOTP secret, recovery code.
- Password, password hash nếu không cần cho vận hành.
- Access token, refresh token, cookie hoặc authorization code.
- Private key, client secret hoặc certificate private material.
- Recovery URL đầy đủ chứa bearer token.
- Toàn bộ nội dung email/SMS nếu chỉ cần lưu template ID và metadata.
- Email/số điện thoại đầy đủ trong log rộng quyền nếu không cần.

Đặt retention theo mục đích, giới hạn quyền truy cập và bảo vệ integrity log. Nếu cần lưu nội dung để phục vụ điều tra, phải có lý do, thời hạn, phân quyền và cơ chế redaction.

## 20. Quyền riêng tư trong notification history

In-app notification center có thể lưu lịch sử sự kiện. Đây là dữ liệu nhạy cảm vì có thể cho biết người dùng đăng nhập ở đâu, thay đổi credential khi nào hoặc dùng dịch vụ nào.

- Chỉ principal được phép mới xem notification history của mình.
- Kiểm tra tenant và account ownership ở server cho mọi request.
- Không dùng ID tuần tự dễ đoán nếu API có thể truy cập chéo.
- Giới hạn retention và hỗ trợ xóa/ẩn theo policy.
- Không hiển thị secret hoặc token kể cả trong lịch sử.
- Phân biệt nội dung đã gửi với trạng thái hiện tại; một cảnh báo cũ không chứng minh credential còn active.
- Nếu admin được xem audit, áp dụng quyền tối thiểu và audit truy cập.

Notification history không phải audit log authoritative. Audit log cần integrity và access control riêng; notification có thể bị xóa hoặc ẩn theo preference nhưng sự kiện bảo mật quan trọng vẫn cần được lưu theo retention policy.

## 21. Mã giả: tạo notification an toàn

Mã giả dưới đây minh họa pipeline khái niệm, không thay thế hệ thống messaging hoặc privacy review:

~~~text
createSecurityNotification(event):
    require event.signatureOrTrustedProducer
    require event.type in allowlistedSecurityEvents

    policy = evaluateNotificationPolicy(
        eventType = event.type,
        risk = event.risk,
        principal = event.principalReference
    )

    if not policy.shouldNotify:
        recordMinimalDecision(event.id, "suppressed_by_policy")
        return suppressed

    recipient = loadPreviouslyVerifiedDestination(
        event.principalReference,
        policy.channel
    )
    require recipient.isVerified

    safeModel = minimizeAndAllowlistFields(event)
    safeModel = maskPersonalData(safeModel, policy.visibility)
    message = renderReviewedTemplate(policy.templateVersion, safeModel)
    require message.containsNoCredentialSecrets
    require linksUseApprovedDomains(message)

    idempotencyKey = hash(
        event.id + recipient.reference + policy.channel + policy.purpose
    )

    enqueueIdempotently(
        eventId = event.id,
        recipient = recipient,
        message = message,
        idempotencyKey = idempotencyKey
    )
    recordDeliveryMetadataOnly(event.id, recipient.reference)
    return queued
~~~

Trong triển khai thật:

- Event producer phải được xác thực; không nhận event giả từ client.
- Destination lấy từ hồ sơ đã xác minh, không từ request body tùy ý.
- Minimize fields trước khi đưa vào queue/template.
- Template phải escape theo context và chỉ dùng domain allowlist.
- Secret scanning cần bao gồm URL, query string, headers và metadata.
- Idempotency phải được lưu bền vững để retry không gửi lặp không kiểm soát.
- Log chỉ ghi delivery metadata tối thiểu và correlation ID.

## 22. Tình huống thực tế: thông báo đăng nhập mới trên điện thoại dùng chung

Một nhân viên dùng điện thoại cá nhân nhưng bật preview thông báo trên màn hình khóa. Điện thoại đôi khi được đặt ở quầy lễ tân. Hệ thống phát hiện đăng nhập mới từ một thiết bị khác và gửi push.

### Nội dung không an toàn

Thông báo hiển thị email đầy đủ, tên công ty, vị trí chính xác, IP, tên tài nguyên nội bộ và một liên kết “Khóa tài khoản ngay”. Người đứng gần có thể biết nhân viên thuộc tổ chức nào, truy cập hệ thống nào và thời điểm họ đăng nhập. Link cũng có thể bị giả mạo hoặc bị dùng để dẫn tới phishing.

### Nội dung an toàn hơn

> Có đăng nhập mới vào tài khoản của bạn. Mở ứng dụng chính thức để xem chi tiết. Nếu không phải bạn, hãy báo cáo hoạt động này trong mục Bảo mật.

Sau khi người dùng mở app và xác thực, trang bảo mật có thể hiển thị thời điểm, nền tảng, thiết bị và vị trí gần đúng ở mức cần thiết, cùng lựa chọn revoke session. Nếu người dùng báo cáo compromise, server xác minh yêu cầu, thu hồi session/token và hướng dẫn recovery.

### Các kiểm soát bổ sung

1. Không đưa OTP hoặc recovery token vào push.
2. Dùng template đã review và domain chính thức.
3. Không cho notification click trực tiếp thực hiện revoke/reset nếu chưa xác minh.
4. Có lựa chọn ẩn nội dung preview.
5. Gộp failed-login alert theo policy để tránh spam.
6. Audit event và delivery metadata, không lưu toàn bộ thông tin cá nhân không cần thiết.

## 23. Kiểm thử notification privacy

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Login alert trên lock screen | Không lộ email đầy đủ, token hoặc dữ liệu nhạy cảm. |
| Push MFA không do người dùng khởi tạo | Có ngữ cảnh đủ nhận biết, nút từ chối/báo cáo và cooldown. |
| OTP notification | Không ghi log; mã ngắn hạn, đúng purpose và giới hạn thử. |
| Recovery link | Domain chính thức, TTL ngắn, one-time; token không xuất hiện trong analytics/referrer/log. |
| Email/phone vừa thay đổi | Cảnh báo qua kênh đã xác minh trước đó theo policy. |
| Account không tồn tại | Endpoint không tiết lộ qua response/delivery behavior. |
| Device name chứa HTML/script | Template escape; không thực thi markup. |
| Link trong template | Chỉ domain/scheme được allowlist. |
| Event gửi lặp | Idempotency ngăn duplicate notification không mong muốn. |
| Provider timeout sau khi nhận message | Retry không tạo spam; trạng thái unknown được xử lý rõ. |
| Recipient chưa verified | Không gửi thông báo nhạy cảm tới destination đó. |
| User tắt marketing | Security notifications vẫn tuân theo policy riêng. |
| Notification history truy cập chéo account | Server từ chối do principal/tenant mismatch. |
| Delivery log | Không chứa OTP, recovery code, cookie, token hoặc URL bí mật. |
| Provider receipt | Không được diễn giải thành bằng chứng người dùng đã đọc/phê duyệt. |
| Shared device/watch preview | Nội dung mặc định tối thiểu và có privacy setting phù hợp. |
| Notification service unavailable | Event critical được giữ/retry theo policy; không giả vờ đã gửi. |
| Helpdesk notification | Không yêu cầu người dùng cung cấp bí mật xác thực. |

### Kiểm thử vận hành và quyền riêng tư

- Rà soát template trên email, SMS, push, wearable và lock screen.
- Kiểm tra data flow tới provider, analytics, APM, queue và log.
- Xác minh retention, access control và data residency của provider.
- Kiểm tra masking không làm lộ account existence qua API.
- Kiểm tra localization không làm thay đổi ý nghĩa cảnh báo hoặc domain.
- Đo duplicate rate, bounce rate, delivery latency và notification fatigue.
- Có quy trình báo cáo phishing và xử lý provider/account compromise.

## 24. Checklist thiết kế notification privacy

- [ ] Phân loại login, MFA, credential change, recovery, device binding, session và federation alerts.
- [ ] Xác định mục đích, người nhận, kênh và mức nhạy cảm cho từng event.
- [ ] Minimize dữ liệu; không gửi password, OTP, recovery code, token, cookie hoặc private key.
- [ ] Lock-screen preview mặc định không chứa dữ liệu nhạy cảm.
- [ ] Destination lấy từ kênh đã xác minh ở server.
- [ ] Mask email/phone/identifier khi phù hợp; không coi masking là anonymization.
- [ ] Login location/IP được mô tả đúng độ chính xác, không khẳng định quá mức.
- [ ] Push MFA có cooldown, rate limit, ngữ cảnh và cách từ chối/báo cáo.
- [ ] Recovery link purpose-bound, TTL ngắn, one-time và không rò rỉ qua log/referrer/analytics.
- [ ] GET không thực hiện thay đổi bảo mật; hành động nhạy cảm cần authentication/CSRF phù hợp.
- [ ] Chống phishing bằng domain chính thức, SPF/DKIM/DMARC và hướng dẫn mở app độc lập.
- [ ] Chống account enumeration ở login, resend, recovery và notification endpoints.
- [ ] Template escape theo context và link dùng allowlist.
- [ ] Event/queue/consumer idempotent; retry không tạo notification spam.
- [ ] Phân biệt provider accepted, delivered, bounced, failed và unknown.
- [ ] Privacy preference không âm thầm tắt cảnh báo bảo mật critical theo policy.
- [ ] Notification history được kiểm soát theo principal/tenant và retention.
- [ ] Log tối thiểu, không chứa secret hoặc URL chứa bearer token.
- [ ] Kiểm thử shared device, lock screen, wearable, provider failure và phishing.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao push notification không nên chứa OTP hoặc recovery code?

**Gợi ý:** Nội dung có thể xuất hiện trên lock screen, thiết bị dùng chung hoặc hệ thống đồng bộ; mã có thể bị người khác đọc và sử dụng.

**Câu 2.** Mask email có làm dữ liệu trở thành vô danh không?

**Gợi ý:** Không. Phần còn lại, domain hoặc ngữ cảnh vẫn có thể nhận diện cá nhân/tổ chức.

**Câu 3.** Vì sao nhận được email thông báo không chứng minh người nhận là chủ tài khoản?

**Gợi ý:** Hộp thư có thể được forward, dùng chung hoặc bị chiếm; notification channel không phải authentication proof.

**Câu 4.** Làm thế nào giảm MFA fatigue?

**Gợi ý:** Giới hạn push, cooldown, number matching, hiển thị ngữ cảnh và cho phép từ chối/báo cáo.

**Câu 5.** Vì sao recovery link cần tránh analytics và Referer?

**Gợi ý:** URL có thể chứa bearer token; hệ thống bên thứ ba hoặc log có thể lưu token và cho phép người khác dùng lại.

**Câu 6.** Provider báo delivered có nghĩa người dùng đã đọc thông báo không?

**Gợi ý:** Không. Delivery receipt chỉ phản ánh trạng thái vận chuyển theo semantics của provider, không chứng minh đúng người đã đọc hoặc phê duyệt.

**Câu 7.** Có nên cho người dùng tắt mọi thông báo bảo mật như marketing email không?

**Gợi ý:** Không mặc định. Cần phân biệt preference marketing với security notification quan trọng theo policy và nghĩa vụ áp dụng.

## 26. Ghi nhớ

**Notification privacy bảo đảm thông báo xác thực giúp người dùng nhận biết sự kiện quan trọng mà không tạo thêm kênh rò rỉ dữ liệu hoặc bí mật.** Hệ thống cần phân loại sự kiện, giảm thiểu nội dung, lấy destination từ kênh đã xác minh, bảo vệ lock-screen preview, chống MFA fatigue và phishing, đồng thời giữ recovery token/OTP/private key ngoài thông báo và log. Pipeline phải có ranh giới tin cậy rõ, template được escape, link dùng domain allowlist, retry idempotent và retention phù hợp. Delivery không chứng minh người dùng đã đọc; notification không phải authentication proof; các hành động như revoke, reset hoặc recovery vẫn cần xác minh và authorization ở server.
