# Giảm friction hợp lý — Thiết kế trải nghiệm xác thực thuận tiện mà vẫn an toàn

## 1. Friction trong xác thực là gì?

**Friction** là công sức, thời gian và sự gián đoạn mà người dùng phải chịu để hoàn tất một thao tác. Trong authentication, friction có thể là nhập mật khẩu, tìm điện thoại để lấy OTP, chờ push, xác minh email, xử lý CAPTCHA, đăng nhập lại hoặc khôi phục tài khoản. Một số bước là cần thiết để bảo vệ danh tính; một số bước xuất hiện do thiết kế kém, trạng thái không được giữ đúng hoặc kiểm soát được áp dụng không đúng thời điểm.

**Giảm friction hợp lý** là giảm thao tác không tạo thêm bảo đảm bảo mật đáng kể, đồng thời giữ hoặc tăng xác minh tại nơi rủi ro thực sự cao. Ví dụ, người dùng đã đăng nhập bằng passkey trên thiết bị quen thuộc có thể tiếp tục đọc nội dung ít nhạy cảm mà không phải nhập lại mật khẩu ở mỗi màn hình. Khi họ muốn thay recovery email hoặc chuyển tiền, hệ thống có thể yêu cầu xác minh lại bằng passkey với user verification.

Trong chương **Trải nghiệm người dùng** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này liên kết credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, account linking và recovery. Người học cần hiểu authentication xác minh danh tính, authorization quyết định quyền, còn UX quyết định người dùng có thể hoàn tất các bước đó dễ dàng và đúng ý định hay không. Trải nghiệm tốt phải hỗ trợ phòng chống phishing, replay và lạm dụng đăng nhập mà không tạo thêm đường tắt nguy hiểm.

**Ít bước hơn không tự động có nghĩa là an toàn hoặc dễ dùng hơn.** Một nút “Approve” mơ hồ có thể nhanh nhưng khiến người dùng chấp thuận push do attacker khởi tạo. Một CAPTCHA xuất hiện ở mọi lần đăng nhập có thể gây phiền mà không chặn được bot hiệu quả. Mục tiêu là đặt đúng bước, đúng lúc, với thông tin đủ rõ để người dùng đưa ra quyết định.

## 2. Phân biệt friction cần thiết và friction không cần thiết

| Loại friction | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Bảo vệ có giá trị** | Step-up trước khi thay MFA hoặc thực hiện giao dịch nhạy cảm. | Giữ lại, giải thích lý do và cung cấp phương thức phù hợp. |
| **Lặp lại không cần thiết** | Bắt nhập lại mật khẩu ở mỗi trang dù session còn hợp lệ. | Dùng session có thời hạn và policy rõ; chỉ xác minh lại khi cần. |
| **Do thiết kế yếu** | OTP hết hạn quá nhanh, lỗi không chỉ ra cách sửa. | Cải thiện timeout, resend và thông báo lỗi. |
| **Do thiếu khả năng tiếp cận** | MFA chỉ dùng thao tác kéo/thả hoặc chỉ hỗ trợ một giác quan. | Cung cấp phương thức thay thế tương đương về assurance. |
| **Do hệ thống không nhất quán** | Một node nhớ thiết bị, node khác liên tục yêu cầu MFA. | Sửa session/context consistency và đồng bộ policy. |
| **Friction bị attacker khai thác** | CAPTCHA hoặc lockout dễ bị dùng để khóa tài khoản nạn nhân. | Đánh giá abuse case, giới hạn theo nhiều tín hiệu và có recovery. |

Không loại bỏ friction chỉ vì nó làm giảm conversion. Trước khi bỏ một bước, cần xác định bước đó đang bảo vệ tài sản nào, ngăn threat nào và có thể thay bằng cơ chế ít gây cản trở hơn nhưng vẫn đạt assurance tương đương hay không.

## 3. Nguyên tắc thiết kế trải nghiệm xác thực

Một luồng tốt thường tuân theo các nguyên tắc:

1. **Ask only when needed:** không hỏi lại thông tin hoặc credential mà hệ thống đã có thể xác minh an toàn.
2. **Progressive assurance:** tăng mức xác minh khi rủi ro hoặc độ nhạy cảm của hành động tăng.
3. **Clear intent:** nói rõ người dùng đang đăng nhập, liên kết tài khoản, thêm credential hay phê duyệt hành động gì.
4. **Predictable behavior:** cùng một trạng thái và policy nên tạo trải nghiệm nhất quán giữa thiết bị và service.
5. **Accessible alternatives:** không phụ thuộc duy nhất vào một thiết bị, giác quan hoặc thao tác.
6. **Safe recovery:** khi mất phương thức chính, có đường khôi phục được kiểm soát và dễ hiểu.
7. **Privacy by design:** không yêu cầu dữ liệu cá nhân hoặc quyền thiết bị không cần thiết.
8. **Security feedback:** giải thích lỗi đủ để người dùng khắc phục nhưng không tiết lộ thông tin giúp attacker dò tài khoản.
9. **User control:** cho phép xem và quản lý session, thiết bị, credential và quyền đã cấp.
10. **Measure outcomes:** đo tỷ lệ hoàn tất, lỗi, support burden và security outcome, không chỉ số lần click.

## 4. Mô hình friction theo rủi ro

Không phải mọi request đều cần cùng mức xác minh. Có thể phân loại theo session assurance, credential, thiết bị, hành vi, tài nguyên và hậu quả của hành động:

| Mức rủi ro/hành động | Ví dụ | UX phù hợp |
| --- | --- | --- |
| Thấp | Đọc nội dung thông thường trong session hợp lệ. | Tiếp tục session; không yêu cầu xác thực lại vô ích. |
| Trung bình | Đổi một tùy chọn cá nhân ít nhạy cảm. | Có thể yêu cầu xác nhận rõ hoặc kiểm tra session freshness. |
| Cao | Thêm passkey, đổi email recovery, xem dữ liệu nhạy cảm. | Step-up bằng factor đủ mạnh và thông báo lý do. |
| Rất cao | Thay đổi quyền admin, chuyển tiền, thu hồi toàn bộ credential. | Reauthentication mạnh, xác nhận chi tiết giao dịch và có thể cần approval bổ sung. |
| Bất thường | Login từ ngữ cảnh rủi ro, token reuse hoặc MFA fatigue. | Tạm dừng, challenge phù hợp, từ chối hoặc chuyển recovery theo policy. |

Risk-based authentication cần thận trọng với tín hiệu như IP, vị trí, thiết bị hoặc thời gian. VPN, mạng di động, roaming và thiết bị dùng chung có thể khiến tín hiệu thay đổi. Không dùng một tín hiệu đơn lẻ để kết luận compromise hoặc chặn người dùng hợp lệ.

## 5. Progressive assurance và step-up authentication

**Progressive assurance** cho phép người dùng bắt đầu bằng luồng phù hợp với thao tác hiện tại, rồi yêu cầu xác minh mạnh hơn khi họ chuyển sang hành động nhạy cảm.

~~~mermaid
flowchart TD
    A["Người dùng mở ứng dụng"]
    B["Xác thực ban đầu"]
    C{"Hành động cần mức assurance nào?"}
    D["Tác vụ thông thường<br/>dùng session hiện tại"]
    E["Step-up authentication"]
    F{"Factor và context đạt policy?"}
    G["Cho phép hành động"]
    H["Từ chối / recovery an toàn"]
    A --> B --> C
    C -->|"Thấp"| D --> G
    C -->|"Cao"| E --> F
    F -->|"Có"| G
    F -->|"Không"| H
~~~

Ví dụ:

- Đọc dashboard: session hiện tại có thể đủ.
- Thêm phương thức MFA: yêu cầu reauthentication bằng factor hiện có.
- Thay email recovery: yêu cầu step-up và xác nhận qua kênh đã xác minh trước đó.
- Cấp quyền quản trị: xác minh phishing-resistant và approval theo policy.

Không nên dùng step-up như một popup chung chung. Giao diện cần nói hành động nào đang được bảo vệ, vì sao cần xác minh và factor nào được chấp nhận.

## 6. Passkey giúp giảm thao tác nhưng cần thiết kế đúng

Passkey có thể giảm friction vì người dùng không phải nhớ, gõ hoặc quản lý mật khẩu riêng cho từng dịch vụ. Với WebAuthn/FIDO, authenticator tạo chữ ký cho challenge gắn với RP ID/origin, giúp chống phishing tốt hơn so với OTP hoặc password có thể bị nhập vào trang giả.

Trải nghiệm tốt:

- Đặt passkey như lựa chọn dễ nhận biết khi thiết bị và trình duyệt hỗ trợ.
- Dùng lời giải thích ngắn: đăng nhập bằng khóa màn hình, sinh trắc học hoặc security key.
- Để người dùng hiểu họ đang tạo passkey cho tài khoản/dịch vụ nào.
- Xử lý hủy prompt hoặc không hỗ trợ một cách bình tĩnh; cung cấp lựa chọn khác theo policy.
- Cho phép đăng ký nhiều authenticator hoặc phương thức dự phòng.
- Hiển thị danh sách passkey/thiết bị đã đăng ký để người dùng quản lý.
- Thông báo khi thêm hoặc xóa credential.

Không khẳng định passkey luôn chỉ tồn tại trên một thiết bị. Passkey có thể device-bound hoặc syncable tùy nền tảng. Cần mô tả đúng mô hình và cung cấp cách xử lý khi người dùng mất thiết bị hoặc tài khoản đồng bộ.

### Tránh tạo friction khi passkey không khả dụng

Nếu browser không hỗ trợ hoặc authenticator không tìm thấy credential:

- Giải thích ngắn và đưa ra phương thức khác đã được đăng ký.
- Không buộc người dùng bắt đầu lại toàn bộ flow nếu transaction vẫn hợp lệ.
- Giữ state an toàn trong thời gian ngắn và chống replay.
- Không tự động hạ assurance sang kênh yếu hơn mà policy không cho phép.
- Cung cấp recovery rõ ràng nếu không còn authenticator nào.

## 7. Password manager, autofill và đăng nhập bằng mật khẩu

Password manager giảm gánh nặng ghi nhớ mật khẩu và giúp tạo mật khẩu duy nhất. Giao diện nên hỗ trợ:

- Autofill tiêu chuẩn và paste password.
- Không chặn paste hoặc password manager bằng JavaScript không cần thiết.
- Không áp đặt quy tắc composition tùy tiện như bắt buộc nhiều loại ký tự nếu không phù hợp hướng dẫn hiện hành.
- Cho phép mật khẩu dài và hỗ trợ ký tự Unicode theo policy.
- Hiển thị rõ khi Caps Lock bật hoặc có lỗi nhập liệu nếu phù hợp.
- Không tự động xóa trường password khi lỗi mạng không liên quan đến credential.
- Không yêu cầu người dùng đổi mật khẩu định kỳ nếu không có dấu hiệu compromise hoặc yêu cầu policy cụ thể.

Thông báo lỗi cần cân bằng UX và account enumeration. Ví dụ, trước khi xác minh identifier, dùng thông điệp chung như “Thông tin đăng nhập không hợp lệ”. Sau khi đã xác thực và biết account, có thể cung cấp hướng dẫn chi tiết hơn.

Không dùng CAPTCHA như bước mặc định cho mọi người. Chỉ thêm challenge khi có tín hiệu abuse và chọn phương thức có khả năng tiếp cận; CAPTCHA cũng có thể gây cản trở cho người khuyết tật và không thay thế rate limiting.

## 8. Thiết kế MFA dễ dùng và chống fatigue

MFA làm tăng assurance nhưng có thể gây gián đoạn nếu yêu cầu không đúng lúc hoặc không có lựa chọn:

- Ưu tiên factor chống phishing như passkey/security key khi phù hợp.
- Giữ TOTP hoặc phương thức khác làm lựa chọn dự phòng theo policy.
- Cho phép copy/paste OTP và hỗ trợ autofill hệ điều hành.
- Hiển thị thời gian còn lại và cách yêu cầu mã mới mà không gây nhầm lẫn.
- Không làm mã hết hạn quá nhanh so với thao tác thực tế.
- Với push, dùng number matching hoặc hiển thị transaction context nếu có.
- Có cooldown và rate limit để chống push bombing.
- Cho phép từ chối và báo cáo yêu cầu không do người dùng khởi tạo.
- Giải thích vì sao cần MFA và cách thiết lập phương thức dự phòng.

Không cho phép “Remember this device” vô thời hạn. Nếu có lựa chọn ghi nhớ, phải giải thích phạm vi, thời hạn, cách thu hồi và rủi ro trên thiết bị dùng chung. Ghi nhớ thiết bị không có nghĩa bỏ qua step-up cho mọi hành động nhạy cảm.

## 9. Session management giảm đăng nhập lặp lại

Session tốt giúp người dùng không phải xác thực lại ở mỗi request, nhưng vẫn giới hạn thời gian và quyền:

- Dùng cookie an toàn với Secure, HttpOnly và SameSite phù hợp cho browser session.
- Đặt idle timeout và absolute timeout theo rủi ro.
- Làm mới session ID sau login và thay đổi privilege.
- Hỗ trợ logout current session và logout all sessions.
- Hiển thị thiết bị/session đang hoạt động và cho phép thu hồi.
- Giữ session state nhất quán giữa các node/region.
- Không để refresh token rotation gây đăng xuất giả do race condition.
- Reauthenticate khi session quá cũ hoặc hành động cần assurance mới.

UX nên cho người dùng biết khi session sắp hết hạn và giữ lại công việc chưa gửi nếu có thể. Không tự động gia hạn session vô hạn chỉ để tránh người dùng đăng nhập lại.

### “Remember me” an toàn

Nếu hỗ trợ “Remember me”:

- Dùng token ngẫu nhiên, có thể revoke và rotation.
- Gắn với account/session và giới hạn thời gian.
- Không lưu password bản rõ.
- Không coi remembered browser là user verification cho hành động nhạy cảm.
- Cung cấp danh sách và thao tác thu hồi thiết bị/session.
- Cân nhắc thiết bị dùng chung và chính sách tổ chức.

## 10. Giảm friction khi đổi thiết bị và quản lý credential

Người dùng cần tự quản lý các phương thức đăng nhập mà không phải liên hệ support cho mọi thay đổi:

- Trang Security hiển thị passkey, security key, TOTP, thiết bị và session.
- Tên thiết bị dễ hiểu, có thể chỉnh sửa nhưng không dùng làm bằng chứng identity.
- Mỗi credential có trạng thái, ngày thêm và thao tác revoke.
- Thêm credential mới yêu cầu xác minh bằng phương thức hiện có hoặc recovery policy.
- Khi mất thiết bị, có thể thu hồi đúng binding mà không buộc logout tất cả nếu không cần.
- Khi thay máy, hướng dẫn đăng ký credential mới và kiểm tra phương thức dự phòng.
- Thông báo qua kênh cũ đã xác minh khi có thay đổi bảo mật quan trọng.

Không để người dùng xóa factor cuối cùng mà không có recovery path hoặc bước xác minh phù hợp. Giao diện nên cảnh báo rõ hậu quả và yêu cầu xác nhận có chủ đích.

## 11. Error message: rõ ràng nhưng không tiết lộ quá mức

Thông báo lỗi tốt giúp người dùng biết bước tiếp theo mà không cung cấp thông tin cho attacker:

| Tình huống | Thông báo phù hợp |
| --- | --- |
| Identifier/password sai trước khi xác minh account | “Thông tin đăng nhập không hợp lệ. Hãy kiểm tra và thử lại.” |
| MFA code sai | “Mã không hợp lệ hoặc đã hết hạn. Hãy kiểm tra thiết bị và thử mã mới.” |
| Push timeout | “Chưa nhận được xác nhận. Bạn có thể thử lại sau hoặc chọn phương thức khác đã đăng ký.” |
| Rate limit | “Bạn đã thử quá nhiều lần. Hãy đợi một lúc trước khi thử lại.” |
| Provider outage | “Dịch vụ xác minh đang tạm thời không khả dụng. Tài khoản của bạn chưa được đăng nhập.” |
| Passkey không khả dụng | “Không tìm thấy passkey cho tài khoản này trên thiết bị. Chọn phương thức khác đã đăng ký.” |
| Session hết hạn | “Phiên đã hết hạn. Đăng nhập lại để tiếp tục; nội dung chưa gửi sẽ được giữ nếu có thể.” |

Không hiển thị stack trace, database error, trạng thái account chi tiết hoặc tên provider nội bộ. Sau khi người dùng đã xác thực, có thể đưa hướng dẫn cụ thể hơn trong vùng được bảo vệ.

## 12. Accessibility và lựa chọn phương thức thay thế

Một luồng xác thực chỉ dễ dùng nếu nhiều nhóm người dùng có thể hoàn tất:

- Hỗ trợ screen reader và nhãn form rõ ràng.
- Không chỉ dùng màu sắc để biểu thị trạng thái.
- Có keyboard navigation và focus order hợp lý.
- Không đặt timeout quá ngắn mà không có cách gia hạn phù hợp.
- Không bắt buộc thao tác kéo/thả, nhận diện hình ảnh hoặc nghe âm thanh làm phương thức duy nhất.
- Cho phép paste và autofill.
- Cung cấp factor thay thế có assurance phù hợp khi người dùng không thể dùng sinh trắc học hoặc thiết bị cụ thể.
- Hướng dẫn lỗi bằng ngôn ngữ đơn giản, có thể dịch và không đổ lỗi cho người dùng.

Phương thức thay thế không nên là một đường vòng yếu mặc định. Cần đánh giá assurance, threat model và recovery evidence tương ứng; người dùng khuyết tật không nên bị buộc dùng một kênh dễ bị chiếm hơn chỉ vì giao diện thiếu hỗ trợ.

## 13. Account recovery dễ hiểu nhưng không dễ bị chiếm

Recovery là nơi UX và security thường xung đột. Một quy trình quá phức tạp khiến người dùng mất tài khoản; quá dễ lại tạo cơ hội social engineering.

Thiết kế:

- Hướng dẫn thiết lập nhiều phương thức dự phòng ngay sau khi đăng ký.
- Hiển thị trạng thái recovery readiness và nhắc bổ sung phương thức an toàn.
- Dùng recovery code one-time và hướng dẫn lưu offline/password manager.
- Cho phép bắt đầu recovery mà không tiết lộ account existence.
- Nêu các bước, thời gian chờ và thông tin cần chuẩn bị.
- Gửi cảnh báo qua kênh đã xác minh trước đó khi policy cho phép.
- Không yêu cầu support đọc hoặc gửi lại OTP/recovery code.
- Có trạng thái pending, review, completed, rejected và cách liên hệ hỗ trợ.
- Sau recovery, thu hồi credential/session cũ theo policy và thông báo kết quả.

Không hứa “khôi phục ngay” nếu quy trình cần kiểm tra thủ công hoặc cooldown. Nêu thời gian ước lượng trung thực và cách người dùng theo dõi yêu cầu.

## 14. Account linking và consent rõ ràng

Khi liên kết tài khoản với IdP, ứng dụng hoặc tenant khác, người dùng cần hiểu:

- Tài khoản nào đang được liên kết.
- Nhà cung cấp/issuer nào sẽ chia sẻ thông tin.
- Dữ liệu hoặc scope nào được cấp.
- Liên kết có thể dùng cho đăng nhập hay truy cập API.
- Cách thu hồi consent hoặc unlink.
- Hậu quả nếu tài khoản bên ngoài bị mất.

Không dùng nút “Continue” mơ hồ để xin scope rộng. Hiển thị tên ứng dụng đã xác minh, permission cụ thể và lý do. Nếu tài khoản đang đăng nhập không phải tài khoản người dùng muốn liên kết, cho phép quay lại mà không mất toàn bộ flow.

## 15. Transaction confirmation cho hành động nhạy cảm

Một bước xác nhận có giá trị khi người dùng nhìn thấy đúng nội dung họ sắp phê duyệt:

- Hiển thị beneficiary, số tiền, đơn vị tiền hoặc resource/action.
- Ràng buộc challenge/signature với dữ liệu giao dịch cần xác nhận.
- Không dùng nội dung chung như “Bạn có yêu cầu đăng nhập?” cho một hành động chuyển tiền.
- Cho phép hủy mà không gây hậu quả không rõ.
- Yêu cầu step-up theo policy và session freshness.
- Sau xác nhận, hiển thị kết quả thực tế và mã tham chiếu.

Nếu nội dung giao dịch thay đổi sau khi người dùng xác nhận, challenge cũ không được tái sử dụng. Giao diện và backend phải cùng ràng buộc vào cùng một transaction context để ngăn attacker thay đổi nội dung giữa lúc hiển thị và thực thi.

## 16. Phân biệt friction UX với kiểm soát chống abuse

Một số biện pháp như rate limit, risk challenge và throttling làm tăng thời gian nhưng có thể cần thiết:

- Rate limit nên giảm tốc độ abuse mà không khóa hàng loạt người dùng hợp lệ.
- CAPTCHA/challenge nên xuất hiện theo tín hiệu, có lựa chọn accessibility.
- Progressive delay không nên giữ worker hoặc tạo tài nguyên vô hạn.
- Account lockout cần tránh bị lợi dụng để khóa nạn nhân.
- Resend OTP có cooldown và quota rõ.
- Push MFA có giới hạn và number matching.
- Risk-based step-up cần giải thích đủ để người dùng nhận ra hoạt động lạ.

Không loại bỏ rate limit vì người dùng phàn nàn đăng nhập chậm. Thay vào đó, đo false positive, phân biệt nguồn lỗi, cải thiện adaptive policy và hỗ trợ phương thức xác thực chống phishing.

## 17. Privacy trong adaptive authentication

Adaptive authentication có thể sử dụng thiết bị, IP, vị trí gần đúng, hành vi và thời gian. Các tín hiệu này có thể nhạy cảm hoặc sai lệch:

- Thu thập tối thiểu và nêu mục đích phù hợp.
- Không dùng fingerprinting xâm lấn khi không cần.
- Không coi IP/geolocation là định danh chính xác.
- Giới hạn retention và quyền truy cập risk profile.
- Kiểm tra bias hoặc tác động không đồng đều lên nhóm người dùng.
- Có con đường hỗ trợ khi risk engine đánh giá sai.
- Không hiển thị thông tin nhạy cảm về risk model cho attacker.

UX không nên nói “Bạn bị chặn vì ở quốc gia X” nếu vị trí chỉ là suy đoán từ IP. Có thể dùng thông điệp “Cần xác minh thêm để bảo vệ tài khoản” và cung cấp factor an toàn.

## 18. Giảm friction trong ứng dụng mobile và browser

### Browser

- Dùng redirect flow chuẩn và giữ state/nonce an toàn.
- Hỗ trợ password manager, autofill và passkey API.
- Không tự tạo custom password field làm hỏng autofill.
- Giữ redirect sau login trong allowlist.
- Tránh bắt người dùng mở nhiều tab hoặc nhập lại identifier không cần thiết.
- Thông báo rõ khi session hết hạn hoặc cần step-up.

### Mobile

- Dùng system browser/authentication session theo hướng dẫn nền tảng cho OAuth/OIDC.
- Dùng secure storage cho token theo đúng threat model.
- Hỗ trợ deep link/Universal Link/App Link đã xác minh.
- Giữ login transaction qua app switch nhưng có expiry và chống replay.
- Hỗ trợ passkey/biometric prompt của hệ điều hành.
- Xử lý app background, network switching và process restart mà không tạo transaction mơ hồ.

Không nhúng client secret tĩnh vào mobile app. UX mượt không được đánh đổi PKCE, redirect validation, TLS hoặc token protection.

## 19. Ngôn ngữ, thông báo và microcopy

Ngôn ngữ ngắn gọn giúp người dùng biết điều gì đang xảy ra:

- Dùng động từ cụ thể: “Thêm passkey”, “Thu hồi thiết bị”, “Xác minh bằng security key”.
- Nói rõ hậu quả trước thao tác khó đảo ngược.
- Phân biệt “Đăng nhập thành công” với “Đã gửi yêu cầu xác minh”.
- Không dùng từ kỹ thuật như “nonce invalid” hoặc “claim mismatch” trong thông báo phổ thông.
- Cung cấp mã tham chiếu hỗ trợ không chứa secret.
- Hướng dẫn bước tiếp theo và phương thức thay thế.
- Tránh ngôn ngữ gây hoảng sợ hoặc đổ lỗi.

Ví dụ:

| Thay vì | Nên dùng |
| --- | --- |
| “Authentication failed: AADSTS/nonce error.” | “Không thể hoàn tất đăng nhập. Hãy thử lại hoặc chọn phương thức đã đăng ký khác.” |
| “Approve?” | “Bạn đang đăng nhập vào [tên dịch vụ] trên thiết bị mới. Nếu không phải bạn, hãy từ chối.” |
| “Invalid user.” | “Không thể xác minh thông tin này. Kiểm tra lại hoặc dùng phương thức khôi phục.” |
| “MFA required.” | “Để bảo vệ thay đổi bảo mật này, hãy xác minh lại bằng passkey hoặc phương thức đã đăng ký.” |

## 20. Đo lường friction và hiệu quả bảo mật

Không đánh giá UX chỉ qua số màn hình hoặc tỷ lệ click. Các chỉ số nên bao gồm:

| Metric | Ý nghĩa |
| --- | --- |
| Login completion rate | Tỷ lệ người dùng hợp lệ hoàn tất đăng nhập. |
| Time to authenticate | Thời gian hoàn tất xác thực, tách thời gian chờ người dùng và provider. |
| Challenge abandonment | Tỷ lệ bỏ dở MFA/step-up và nguyên nhân. |
| Retry rate | Số lần nhập lại hoặc yêu cầu gửi lại. |
| Recovery completion/time | Khả năng và thời gian khôi phục tài khoản. |
| False rejection | Người dùng hợp lệ bị chặn nhầm. |
| Support contact rate | Số yêu cầu hỗ trợ liên quan tới login/MFA/recovery. |
| Phishing-resistant adoption | Tỷ lệ người dùng đã thiết lập và sử dụng passkey/security key. |
| MFA fatigue signals | Push bị từ chối, timeout hoặc lặp bất thường. |
| Account takeover / abuse rate | Sự cố chiếm tài khoản hoặc lạm dụng sau xác thực. |
| Revocation effectiveness | Thời gian session/credential cũ bị từ chối sau revoke. |

Phân tích theo thiết bị, trình duyệt, accessibility needs, khu vực và nhóm người dùng chỉ khi có mục đích hợp lệ, dữ liệu đủ tin cậy và privacy controls phù hợp. Không tối ưu conversion bằng cách hạ MFA hoặc bỏ kiểm tra rủi ro mà không đánh giá tác động.

## 21. Thử nghiệm UX mà không làm yếu bảo mật

A/B testing có thể so sánh cách trình bày hoặc thứ tự lựa chọn, nhưng không được âm thầm thay đổi assurance:

- Thử copy, layout hoặc hướng dẫn passkey.
- So sánh vị trí hiển thị password manager/passkey option.
- Thử giải thích MFA và recovery setup.
- Đo thời gian hoàn tất và tỷ lệ lỗi theo cohort.
- Giữ nguyên policy, challenge validation và rate limit giữa các nhóm.
- Có guardrail về account takeover, false rejection và support burden.
- Dừng thử nghiệm nếu security metric xấu đi vượt ngưỡng.

Không đưa nhóm thử nghiệm vào chế độ “bỏ MFA” để tăng conversion nếu không có thiết kế nghiên cứu và phê duyệt bảo mật riêng. Không thử trên tài khoản thật theo cách có thể khóa người dùng hoặc làm lộ credential.

## 22. Mã giả: chọn mức xác minh phù hợp

Mã giả minh họa quyết định friction theo action và policy:

~~~text
authorizeUserJourney(session, action, context):
    require sessionIsValid(session)
    risk = evaluateTrustedRiskSignals(
        session = session,
        action = action,
        device = context.deviceSignals,
        network = context.networkSignals
    )

    requiredAssurance = policy.requiredAssurance(
        resource = action.resource,
        operation = action.operation,
        risk = risk
    )

    if session.assurance >= requiredAssurance
       and session.authenticationIsFresh(requiredAssurance.maxAge):
        return allowWithCurrentSession()

    options = availableAuthenticators(
        principal = session.principal,
        minimumAssurance = requiredAssurance,
        phishingResistance = requiredAssurance.phishingResistance
    )

    if options.isEmpty:
        return offerSecureRecoveryOrSupport()

    result = requestStepUp(
        purpose = action.operation,
        audience = action.resource,
        transaction = action.transactionReference,
        allowedAuthenticators = options
    )

    if verifyStepUpAndTransactionBinding(result):
        return allowAction()
    return denyWithClearNextStep()
~~~

Trong triển khai thật:

- Risk engine chỉ dùng tín hiệu đã được đánh giá và có giới hạn privacy.
- Policy không được hạ assurance chỉ vì provider lỗi hoặc người dùng bỏ challenge.
- Step-up proof phải gắn đúng purpose, audience và transaction.
- Session freshness phải dựa trên authentication time đáng tin cậy.
- Nếu không có factor phù hợp, dùng recovery có kiểm soát hoặc từ chối tạm thời.
- Mọi thay đổi credential/session cần audit và notification phù hợp.

## 23. Tình huống thực tế: giảm friction cho người dùng thường xuyên nhưng bảo vệ thay đổi nhạy cảm

Một dịch vụ quản lý hồ sơ cho phép nhân viên đăng nhập hằng ngày. Trước đây, ứng dụng yêu cầu password và OTP ở mỗi lần mở trang, kể cả khi người dùng vừa xác thực và chỉ xem nội dung thông thường. Nhiều người bỏ qua thông báo MFA, dùng lại mật khẩu hoặc liên hệ helpdesk vì mất thiết bị.

### Thiết kế mới

1. Hỗ trợ passkey làm phương thức đăng nhập ưu tiên trên thiết bị tương thích.
2. Hỗ trợ password manager/autofill và phương thức dự phòng theo policy.
3. Dùng session có idle/absolute timeout rõ ràng, Secure/HttpOnly/SameSite cookie phù hợp.
4. Không yêu cầu MFA lại cho mỗi trang trong session hợp lệ.
5. Yêu cầu step-up khi thêm passkey, đổi recovery email, export dữ liệu hoặc thay quyền.
6. Hiển thị rõ thiết bị/session và cho phép thu hồi.
7. Hướng dẫn thiết lập authenticator dự phòng và recovery code ngay sau onboarding.
8. Gửi thông báo bảo mật qua kênh đã xác minh khi credential hoặc recovery method thay đổi.

### Đo kết quả

- Login completion và time-to-authentication.
- Tỷ lệ passkey adoption và MFA challenge abandonment.
- Số ticket helpdesk về password/MFA.
- False rejection và số lần recovery thất bại.
- Account takeover, phishing report và credential stuffing rate.
- Revocation propagation khi người dùng báo mất thiết bị.

Nếu login nhanh hơn nhưng account takeover tăng hoặc người dùng không thể thu hồi thiết bị mất, thay đổi chưa thành công. Cần xem đồng thời usability và security outcome.

## 24. Kiểm thử giảm friction hợp lý

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người dùng có passkey hợp lệ | Hoàn tất đăng nhập với ít thao tác, xác minh RP ID/origin/challenge đúng. |
| Browser hỗ trợ password manager | Autofill/paste hoạt động; không bị chặn vô lý. |
| Passkey không khả dụng | Có lựa chọn dự phòng theo policy, không tự hạ assurance. |
| Người dùng hủy MFA | Session không được tạo nếu factor bắt buộc chưa hoàn tất. |
| Push MFA bị spam | Cooldown/rate limit và number matching giảm fatigue. |
| Session còn hợp lệ, action ít nhạy cảm | Không yêu cầu login lặp lại vô ích. |
| Session cũ, action nhạy cảm | Step-up được yêu cầu theo freshness policy. |
| Thêm passkey hoặc đổi recovery method | Có reauthentication, purpose binding và notification. |
| Thiết bị bị mất | Người dùng có thể revoke đúng binding/session và recovery an toàn. |
| Người dùng dùng screen reader | Form, focus, thông báo lỗi và lựa chọn factor có thể truy cập. |
| CAPTCHA/challenge không khả dụng | Có phương thức thay thế phù hợp; không khóa user vì accessibility. |
| Identifier không tồn tại | Error response không tiết lộ account enumeration. |
| Risk signal sai lệch | Có cách xác minh bổ sung/hỗ trợ, không chỉ dựa IP hoặc location. |
| OAuth consent scope rộng | Giao diện nêu rõ permission và cách revoke. |
| Transaction thay đổi sau xác nhận | Challenge cũ không được chấp nhận cho nội dung mới. |
| Recovery provider lỗi | Không bỏ qua identity proof; transaction pending hoặc hướng dẫn phương án an toàn. |
| A/B test UX | Assurance và security guardrail được giữ nguyên. |
| Logout/revoke | Session và token cũ bị từ chối; UX hiển thị trạng thái chính xác. |

## 25. Checklist thiết kế trải nghiệm xác thực

- [ ] Xác định friction nào bảo vệ threat cụ thể và friction nào chỉ do thiết kế kém.
- [ ] Dùng progressive assurance theo rủi ro và độ nhạy cảm của hành động.
- [ ] Ưu tiên passkey/phương thức chống phishing khi phù hợp.
- [ ] Hỗ trợ password manager, autofill và paste.
- [ ] Không dùng quy tắc mật khẩu hoặc CAPTCHA gây cản trở không cần thiết.
- [ ] MFA có lựa chọn dự phòng, cooldown và chống push fatigue.
- [ ] Session có timeout, refresh, logout và revoke nhất quán.
- [ ] Step-up giải thích rõ action, purpose và factor được chấp nhận.
- [ ] Recovery được hướng dẫn trước, có trạng thái và không hạ assurance.
- [ ] Credential/device inventory cho phép người dùng quản lý và thu hồi.
- [ ] Account linking/consent hiển thị rõ issuer, scope và cách unlink.
- [ ] Transaction confirmation ràng buộc với dữ liệu thực thi.
- [ ] Error message dễ hiểu nhưng chống account enumeration.
- [ ] Hỗ trợ screen reader, keyboard, timeout hợp lý và phương thức thay thế.
- [ ] Thu thập risk signal tối thiểu, đánh giá độ tin cậy và privacy impact.
- [ ] Đo completion, latency, abandonment, false rejection và abuse.
- [ ] A/B test không âm thầm hạ assurance hoặc bỏ security control.
- [ ] Kiểm thử thiết bị mất, provider outage, replay, session revoke và recovery.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Giảm friction có nghĩa là bỏ MFA không?

**Gợi ý:** Không. Có thể giảm MFA lặp lại trong session phù hợp nhưng vẫn yêu cầu step-up ở hành động nhạy cảm và giữ factor bắt buộc.

**Câu 2.** Vì sao passkey có thể vừa tăng bảo mật vừa giảm thao tác?

**Gợi ý:** Authenticator ký challenge gắn với RP ID/origin, giảm việc nhập mật khẩu/OTP có thể bị phishing và không cần người dùng ghi nhớ secret.

**Câu 3.** Vì sao không nên yêu cầu CAPTCHA ở mọi lần login?

**Gợi ý:** Tạo friction và vấn đề accessibility, trong khi không thay thế rate limit hoặc risk controls; chỉ dùng khi có tín hiệu phù hợp.

**Câu 4.** Khi nào cần step-up authentication?

**Gợi ý:** Khi action có impact cao, session authentication đã cũ, assurance hiện tại không đủ hoặc risk signal đáng tin yêu cầu xác minh thêm.

**Câu 5.** “Remember this device” có nghĩa là bỏ qua mọi xác minh sau này không?

**Gợi ý:** Không. Nó có phạm vi và thời hạn; hành động nhạy cảm vẫn có thể cần user verification hoặc step-up.

**Câu 6.** Làm thế nào giữ recovery dễ dùng mà không biến thành bypass?

**Gợi ý:** Thiết lập factor dự phòng trước, recovery code one-time, evidence độc lập, trạng thái rõ và không hạ assurance tùy tiện.

**Câu 7.** Vì sao phải đo cả UX và security outcome?

**Gợi ý:** Login nhanh hơn nhưng account takeover, false rejection hoặc recovery abuse tăng thì thiết kế chưa đạt mục tiêu.

## 27. Ghi nhớ

**Giảm friction hợp lý là đặt xác minh đúng lúc và đúng mức, không loại bỏ bảo vệ cần thiết.** Hãy giảm thao tác lặp lại bằng passkey, password manager, autofill và session có thời hạn; dùng progressive assurance và step-up cho thay đổi credential, recovery, dữ liệu hoặc giao dịch nhạy cảm; cung cấp MFA và recovery dễ hiểu, có lựa chọn tiếp cận; đồng thời bảo vệ chống phishing, push fatigue, enumeration, replay và session abuse. Đo tỷ lệ hoàn tất, thời gian xác thực, abandonment, false rejection, support burden và account takeover cùng nhau. Trải nghiệm chỉ thực sự tốt khi người dùng hoàn thành đúng ý định với ít trở ngại không cần thiết và hệ thống vẫn giữ nguyên các ranh giới tin cậy.
