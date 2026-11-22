# Risk signal, challenge và step-up

API có thể bị lạm dụng ngay cả khi request có cú pháp hợp lệ và người gọi đã đăng nhập. Một tài khoản bị chiếm đoạt có thể thực hiện hàng loạt thao tác; một client tích hợp có thể đột ngột thay đổi hành vi; hoặc một người dùng hợp lệ có thể gửi request nhạy cảm từ thiết bị mới, sau nhiều lần thử sai hoặc trong một chuỗi thao tác bất thường.

Risk signal, challenge và step-up là các lớp kiểm soát giúp hệ thống phản ứng theo ngữ cảnh. Risk signal cung cấp bằng chứng về mức độ bất thường; challenge yêu cầu thêm một bước xác minh hoặc chứng minh client đang tương tác theo cách phù hợp; step-up yêu cầu mức xác thực mạnh hơn trước khi cho phép một hành động có rủi ro cao.

Các cơ chế này bổ sung cho xác thực, phân quyền, quota, rate limit và kiểm tra nghiệp vụ. Chúng không thay thế việc xác minh danh tính, quyền trên object hoặc trạng thái của workflow. Một request có điểm rủi ro thấp vẫn phải bị từ chối nếu principal không có quyền; một request có điểm rủi ro cao có thể cần challenge hoặc step-up dù credential ban đầu hợp lệ.

## 1. Phân biệt risk signal, challenge và step-up

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Risk signal | Dấu hiệu đầu vào để đánh giá hành vi hoặc request có bất thường không | Nhiều lần đăng nhập thất bại, thiết bị mới, tốc độ gọi API tăng đột ngột |
| Risk decision | Chính sách kết hợp tín hiệu, ngữ cảnh và mức tác động để chọn hành động | Cho phép, theo dõi, challenge, step-up, giới hạn hoặc từ chối |
| Challenge | Yêu cầu thêm bằng chứng hoặc một thao tác xác minh phù hợp | CAPTCHA, xác nhận qua kênh đã đăng ký, proof-of-possession hoặc xác nhận thao tác |
| Step-up authentication | Nâng mức xác thực của principal trước khi cho phép thao tác nhạy cảm | Yêu cầu passkey/WebAuthn hoặc MFA mạnh hơn phiên hiện tại |

Ví dụ, một user đăng nhập bằng session hợp lệ nhưng đột nhiên yêu cầu đổi tài khoản ngân hàng nhận settlement. Hệ thống có thể nhận thấy thiết bị mới và hành vi khác thường, yêu cầu xác thực lại bằng yếu tố mạnh, rồi yêu cầu phê duyệt độc lập theo workflow. Việc vượt qua challenge không tự động cấp quyền đổi tài khoản; server vẫn phải kiểm tra permission, tenant, object và quy tắc phê duyệt.

## 2. Xác định khi nào cần đánh giá rủi ro

Không nhất thiết mọi request đều cần chạy một mô hình risk phức tạp. Hãy xác định các điểm có khả năng bị lạm dụng và mức hậu quả nếu hành động xảy ra.

Các điểm thường cần đánh giá:

- Đăng nhập, đăng ký, xác minh email/số điện thoại và khôi phục tài khoản.
- Tạo hoặc thay đổi API key, credential, MFA, thiết bị tin cậy và thông tin khôi phục.
- Đọc dữ liệu nhạy cảm, export, download hoặc chia sẻ tài liệu.
- Thanh toán, refund, chuyển tiền, thay đổi giá hoặc tài khoản nhận tiền.
- Thay đổi role, permission, tenant membership hoặc quyền sở hữu.
- Gửi thông báo hàng loạt, publish nội dung hoặc thao tác moderation.
- Batch operation, import, export và endpoint có chi phí xử lý cao.
- Các endpoint có dấu hiệu bị dò object, credential stuffing hoặc automation.

Risk evaluation có thể diễn ra ở gateway, authentication service hoặc domain service tùy loại tín hiệu. Những tín hiệu liên quan đến hành vi nghiệp vụ chỉ có thể được đánh giá đầy đủ ở nơi hiểu object và workflow. Ví dụ risk của một lệnh refund phụ thuộc amount, payment history, trạng thái và tenant; gateway chỉ nhìn URL có thể không có đủ dữ liệu.

### 2.1. Gắn mức rủi ro với tác động

Đánh giá rủi ro nên xem cả khả năng bị lạm dụng và hậu quả:

| Hành động | Tác động nếu bị lạm dụng | Kiểm soát có thể cân nhắc |
|---|---|---|
| Đọc dữ liệu công khai | Thấp nếu không có dữ liệu riêng tư | Rate limit và phát hiện scraping |
| Đọc hồ sơ nhạy cảm | Rò rỉ dữ liệu và ảnh hưởng riêng tư | Object authorization, risk signal, audit và step-up theo policy |
| Đổi email hoặc reset MFA | Có thể dẫn đến chiếm đoạt tài khoản | Xác minh mạnh, thông báo kênh độc lập và kiểm tra session |
| Tạo API key hoặc cấp quyền | Mở rộng quyền truy cập | Step-up, xác nhận mục đích, audit và giới hạn scope |
| Refund hoặc chuyển tiền | Tổn thất tài chính trực tiếp | Step-up, transaction confirmation, idempotency, hạn mức và dual control |
| Publish hoặc gửi thông báo diện rộng | Tác động danh tiếng và quyền lợi | Challenge/approval, preview, audience check và khả năng dừng |

Một thao tác ít rủi ro trong điều kiện bình thường có thể trở thành rủi ro cao khi được thực hiện hàng trăm lần, trên nhiều object hoặc từ một session có dấu hiệu bị chiếm đoạt.

## 3. Thu thập và đánh giá risk signal

Risk signal là dữ liệu đầu vào cho quyết định. Mỗi tín hiệu nên có nguồn, thời điểm, độ tin cậy, phạm vi và thời hạn sử dụng rõ ràng. Không nên coi một tín hiệu riêng lẻ là bằng chứng chắc chắn về gian lận.

### 3.1. Nhóm tín hiệu theo request và tốc độ

- Số request trong các cửa sổ thời gian khác nhau.
- Tốc độ thử đăng nhập, reset mật khẩu, gửi OTP hoặc kiểm tra mã xác minh.
- Số object ID khác nhau được truy cập trong thời gian ngắn.
- Tỷ lệ lỗi 401, 403, 404, 409 hoặc 429 tăng bất thường.
- Số lần thử coupon, thanh toán, refund hoặc action nhạy cảm.
- Số request có payload lớn, query phức tạp hoặc pattern lặp lại.

Những tín hiệu này giúp phát hiện enumeration, credential stuffing, brute force, scraping và automation. Cần phân biệt request bị từ chối với thao tác nghiệp vụ thành công để không đánh giá sai mức tiêu thụ.

### 3.2. Nhóm tín hiệu về session và thiết bị

- Session mới hoặc thiết bị chưa từng được dùng trong bối cảnh tài khoản.
- Thay đổi đột ngột về user agent hoặc đặc điểm client.
- Nhiều tài khoản được sử dụng từ cùng một thiết bị hoặc môi trường tự động.
- Token được sử dụng đồng thời ở các ngữ cảnh khó giải thích.
- Refresh token hoặc session có dấu hiệu bị replay.
- Thay đổi thông tin xác thực ngay trước một action nhạy cảm.

Device fingerprinting có thể hỗ trợ nhận diện thay đổi, nhưng thường không ổn định và có hệ quả riêng tư. Thiết bị có thể dùng chung, reset hoặc thay đổi đặc điểm sau cập nhật. Không nên dùng fingerprint như một danh tính chắc chắn hoặc làm căn cứ duy nhất để từ chối người dùng.

### 3.3. Nhóm tín hiệu mạng và vị trí

- IP hoặc ASN có reputation xấu theo nguồn dữ liệu được quản lý.
- Tốc độ và số lượng request từ một nguồn mạng.
- Địa lý hoặc vùng mạng thay đổi bất thường so với lịch sử.
- Proxy, hosting provider hoặc hạ tầng tự động có đặc điểm khác với hành vi thông thường.
- Request đến từ vùng mạng không phù hợp với chính sách dịch vụ.

Địa chỉ IP có thể thay đổi do VPN, mạng di động, NAT, proxy doanh nghiệp hoặc đi công tác. Địa lý IP chỉ là ước lượng và không chứng minh vị trí thật. Tránh dùng một lần đăng nhập từ quốc gia khác làm lý do duy nhất để khóa tài khoản.

### 3.4. Nhóm tín hiệu hành vi và nghiệp vụ

- Thay đổi thông tin nhận tiền ngay trước ngày settlement.
- Refund nhiều giao dịch hoặc nhiều lần thử refund trong thời gian ngắn.
- Thay đổi role, owner hoặc tenant membership bất thường.
- Truy cập tuần tự nhiều object không có quan hệ nghiệp vụ.
- Tạo lượng lớn API key, user, coupon hoặc job.
- Hành vi khác biệt rõ so với lịch sử của user, tenant hoặc client.
- Một thao tác được thực hiện sau chuỗi hành động có rủi ro cao, ví dụ reset mật khẩu rồi export dữ liệu.

Các tín hiệu nghiệp vụ thường có giá trị hơn việc chỉ nhìn IP hoặc user agent, nhưng phải được giới hạn theo tenant và quyền truy cập. Risk service chỉ nên nhận dữ liệu tối thiểu cần thiết để đưa ra quyết định.

### 3.5. Đánh giá chất lượng tín hiệu

Với mỗi signal, cần ghi nhận:

- **Source:** nguồn tạo tín hiệu, ví dụ gateway, identity provider, fraud service hoặc domain event.
- **Freshness:** thời điểm tín hiệu được tạo và thời hạn còn hữu ích.
- **Confidence:** độ tin cậy của nguồn và cách đo.
- **Scope:** áp dụng cho request, session, user, API client hay tenant.
- **Reason code:** mã lý do có thể dùng trong policy và audit.
- **Data handling:** thời hạn lưu, mục đích và quyền truy cập.

Một tín hiệu cũ không nên tiếp tục làm tăng risk vô thời hạn. Một cảnh báo trên thiết bị dùng chung cũng không nên tự động gắn cho mọi user của tenant.

## 4. Kết hợp tín hiệu thành quyết định rủi ro

Risk engine có thể dùng rule, điểm số, mô hình thống kê hoặc kết hợp. Mục tiêu là tạo quyết định có thể giải thích và vận hành được, không phải tạo một con số bí ẩn mà không ai biết vì sao request bị challenge.

### 4.1. Rule-based decision

Rule phù hợp khi điều kiện rõ và hậu quả cần kiểm soát trực tiếp:

- Quá số lần gửi OTP trong cửa sổ: tạm dừng gửi và yêu cầu chờ.
- API key bị thu hồi: từ chối request.
- Token không hợp lệ hoặc hết hạn: yêu cầu xác thực lại.
- Request vượt quota: trả 429 theo contract.
- Action tài chính vượt hạn mức của người duyệt: chuyển cấp phê duyệt hoặc từ chối.
- Nhiều lần thử sai trên tài khoản: áp dụng throttling và kiểm soát bổ sung.

Rule cứng cần tránh tạo khóa tài khoản kéo dài chỉ vì một nguồn tín hiệu dễ bị giả mạo. Ví dụ, không nên để một IP có thể khiến tài khoản của nạn nhân bị khóa vô thời hạn bằng cách liên tục gửi mật khẩu sai.

### 4.2. Risk score

Một mô hình đơn giản có thể cộng trọng số cho các tín hiệu:

| Signal | Trọng số minh họa |
|---|---:|
| Thiết bị mới | +15 |
| Nhiều lần xác minh thất bại | +25 |
| Tốc độ request bất thường | +20 |
| Thay đổi thông tin khôi phục gần đây | +25 |
| Dấu hiệu token replay đáng tin cậy | +40 |

Các con số chỉ minh họa cách suy nghĩ, không phải ngưỡng triển khai. Trong thực tế, trọng số và ngưỡng cần được hiệu chỉnh bằng dữ liệu có kiểm soát, đánh giá false positive/false negative và theo dõi thay đổi hành vi.

Không nên cộng điểm một cách máy móc nếu các tín hiệu tương quan mạnh. Ví dụ IP reputation xấu, ASN hosting và proxy có thể phản ánh cùng một nguyên nhân. Mô hình cần tránh tính trùng bằng chứng và phải có cơ chế giải thích reason code.

### 4.3. Các mức quyết định

Một policy có thể dùng các mức:

| Quyết định | Hành vi |
|---|---|
| Allow | Cho phép tiếp tục sau khi các kiểm tra xác thực, authorization và nghiệp vụ đều pass |
| Monitor | Cho phép nhưng tăng mức audit hoặc theo dõi |
| Challenge | Yêu cầu một bước xác minh bổ sung có thời hạn |
| Step-up | Yêu cầu xác thực mạnh hơn hoặc xác thực lại |
| Restrict | Giảm tốc độ, giới hạn tính năng hoặc chuyển thao tác sang review |
| Deny | Từ chối khi có bằng chứng mạnh, vi phạm policy hoặc điều kiện cứng không đạt |

Risk score chỉ hỗ trợ chọn hành động. Nó không được tự động biến thành permission. Ví dụ điểm thấp không thể cho phép user đọc object của tenant khác; điểm cao cũng không nên làm lộ cho client những rule chống gian lận nội bộ.

### 4.4. Kết hợp risk theo từng hành động

Một user có thể có risk thấp khi đọc dữ liệu thông thường nhưng risk cao khi đổi email, thêm API key hoặc refund. Vì vậy, quyết định nên phụ thuộc cả action và mức tác động, không chỉ gắn một nhãn risk cố định cho toàn bộ tài khoản.

Ví dụ:

- Đọc profile: allow nếu authentication và object authorization pass.
- Export hồ sơ nhạy cảm: yêu cầu step-up nếu session cũ hoặc thiết bị mới.
- Đổi tài khoản nhận tiền: step-up và dual control dù risk score thấp.
- Refund bất thường: yêu cầu review hoặc từ chối theo hạn mức và policy.

Các điều kiện bắt buộc của nghiệp vụ như hạn mức, approval hoặc trạng thái không được bỏ qua chỉ vì risk engine đánh giá request an toàn.

## 5. Challenge phù hợp với từng tình huống

Challenge là một bước xác minh bổ sung. Chọn loại challenge theo rủi ro, loại client và mức bảo đảm cần đạt. Không phải challenge nào cũng xác minh danh tính.

| Loại challenge | Mục đích | Giới hạn |
|---|---|---|
| CAPTCHA hoặc bot challenge | Tăng chi phí automation hoặc phát hiện tương tác tự động | Không chứng minh người giải có quyền sở hữu tài khoản |
| OTP qua kênh đã đăng ký | Xác minh khả năng truy cập kênh liên lạc | Có thể bị phishing, SIM swap hoặc chuyển tiếp |
| Push approval | Yêu cầu xác nhận trên thiết bị đã đăng ký | Cần chống MFA fatigue và hiển thị rõ nội dung |
| Passkey/WebAuthn | Xác thực bằng public-key credential gắn với origin/RP | Cần quy trình đăng ký, recovery và kiểm tra user verification phù hợp |
| Proof-of-possession | Chứng minh client nắm giữ khóa gắn với credential | Phù hợp với client/API credential; không tự chứng minh người dùng được quyền |
| Human review | Chuyển trường hợp bất thường cho người có thẩm quyền | Chậm hơn, cần audit và quy trình nhất quán |

### 5.1. CAPTCHA và bot challenge

CAPTCHA có thể tăng chi phí automation trên endpoint đăng ký, gửi OTP hoặc tìm kiếm công khai. Tuy nhiên:

- CAPTCHA có thể bị giải bởi dịch vụ bên ngoài hoặc bị vượt qua bằng kỹ thuật tự động khác.
- CAPTCHA không thay thế rate limit, authorization hoặc xác minh tài khoản.
- Cần có lựa chọn tiếp cận được cho người dùng gặp khó khăn với challenge hình ảnh/âm thanh.
- Không nên yêu cầu CAPTCHA lặp lại ở mọi request của client API hợp lệ.
- Server phải xác minh token challenge với nhà cung cấp hoặc verifier tin cậy; không tin kết quả do browser tự gửi.

### 5.2. OTP và xác nhận qua kênh độc lập

OTP có thể phù hợp để xác minh quyền truy cập một kênh đã đăng ký, nhưng cần giới hạn số lần gửi và thử, thời hạn ngắn, chống replay và gắn với đúng mục đích. Không ghi OTP vào log và không trả thông tin cho phép dò xem số điện thoại/email có tồn tại hay không.

Với thao tác tài chính hoặc thay đổi credential, OTP SMS/email có thể không đủ mạnh. Cân nhắc passkey, security key hoặc cơ chế MFA chống phishing phù hợp với mức bảo đảm cần thiết.

### 5.3. Challenge phải gắn với mục đích

Một challenge được tạo để xác minh đổi email không được dùng lại để refund hoặc tạo API key. Challenge nên ràng buộc với:

- Principal và session hoặc client identity.
- Tenant và loại action.
- Object hoặc operation ID khi phù hợp.
- Nội dung giao dịch hoặc hash của các trường quan trọng.
- Thời hạn hết hiệu lực.
- Nonce hoặc mã dùng một lần.
- Trạng thái đã sử dụng/chưa sử dụng.

Nếu payload thay đổi sau khi challenge được hoàn tất, server phải yêu cầu xác minh lại hoặc kiểm tra lại theo policy. Không chấp nhận một cờ verified=true do client gửi.

## 6. Step-up authentication

Step-up authentication yêu cầu principal chứng minh mức xác thực cao hơn mức hiện tại trước khi thực hiện hành động nhạy cảm. Đây có thể là xác thực lại, MFA bổ sung hoặc phương thức chống phishing mạnh hơn.

Các trường hợp thường cân nhắc:

- Thay đổi email, số điện thoại, mật khẩu, MFA hoặc thiết bị tin cậy.
- Tạo, xoay vòng hoặc cấp quyền API key.
- Thêm người dùng quản trị hoặc thay đổi role.
- Export dữ liệu nhạy cảm hoặc cấp quyền chia sẻ.
- Thay đổi tài khoản nhận tiền, chuyển tiền hoặc refund.
- Phê duyệt giao dịch hoặc publish thông tin quan trọng.

### 6.1. Chọn yếu tố xác thực theo mức bảo đảm

Không phải mọi MFA đều có cùng khả năng chống phishing. SMS OTP, email OTP, TOTP, push approval và passkey/security key có đặc tính khác nhau. Với thao tác có tác động lớn, nên ưu tiên phương thức chống phishing như WebAuthn/passkey hoặc security key khi khả thi, đồng thời có recovery flow đủ an toàn.

Step-up cần xem xét:

- Mức xác thực hiện tại và thời điểm xác thực gần nhất.
- Phương thức MFA đã được đăng ký và độ tin cậy của nó.
- Session có dấu hiệu bị chia sẻ hoặc replay không.
- Action có yêu cầu xác minh lại ngay trước khi thực hiện không.
- Người dùng có thể hoàn tất challenge an toàn trên thiết bị hiện tại không.

### 6.2. Fresh authentication và thời hạn

Một session được xác thực mạnh từ nhiều giờ trước không nhất thiết đủ cho một action có tác động tài chính. Policy có thể yêu cầu authentication freshness, ví dụ xác thực lại trong một khoảng thời gian nhất định hoặc yêu cầu MFA mới.

Nếu dùng OAuth/OIDC, resource server và authorization server cần phối hợp để yêu cầu mức xác thực phù hợp, kiểm tra các claim như acr, amr hoặc auth_time theo profile được triển khai. Không chỉ tin một claim do client tự gửi; token phải được xác minh và policy cần hiểu ý nghĩa thực tế của assurance level.

Với hệ thống hỗ trợ giao thức step-up chuẩn, hãy dùng challenge và error semantics đúng theo chuẩn đã chọn. Nếu API dùng contract riêng, cần mô tả rõ cách client bắt đầu xác thực lại, hoàn tất challenge và gửi lại thao tác.

### 6.3. Transaction confirmation

Với chuyển tiền hoặc thay đổi tài khoản nhận settlement, xác thực lại chung chung có thể chưa đủ. Người dùng cần xác nhận chính giao dịch cụ thể: số tiền, đơn vị tiền, tài khoản nguồn/đích hoặc thông tin thay đổi quan trọng.

Transaction confirmation nên ràng buộc approval với một bản biểu diễn ổn định của giao dịch. Nếu amount, beneficiary hoặc các trường quan trọng thay đổi, approval cũ không còn hợp lệ. Với phương thức hỗ trợ cryptographic transaction signing, dữ liệu hiển thị và dữ liệu được ký cần nhất quán để tránh thay thế nội dung sau khi người dùng xác nhận.

### 6.4. Step-up không thay thế authorization

Một user xác thực bằng passkey không tự động được phép gọi endpoint quản trị. Step-up chỉ chứng minh mức xác thực hoặc sự hiện diện của credential; server vẫn cần kiểm tra:

- Function permission.
- Object và tenant scope.
- Field được phép thay đổi.
- Trạng thái workflow và hạn mức.
- Approval hoặc separation of duties nếu cần.

## 7. Luồng challenge và step-up cho API

API cần định nghĩa một giao thức rõ ràng để client biết request đang chờ challenge, cách hoàn tất và khi nào có thể thử lại.

Một luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant R as Risk service
    participant I as Identity provider
    C->>A: Request sensitive action
    A->>A: Authenticate and authorize baseline
    A->>R: Evaluate request context
    R-->>A: Step-up required
    A-->>C: Challenge required with short-lived reference
    C->>I: Complete MFA or passkey
    I-->>C: New authenticated result
    C->>A: Retry action with step-up proof
    A->>A: Verify proof, binding, freshness and one-time use
    A->>A: Recheck permission, object and workflow state
    A-->>C: Execute or reject action
~~~

Các bước quan trọng:

1. Xác thực credential ban đầu.
2. Kiểm tra permission và object scope cơ bản.
3. Đánh giá risk theo action, principal, object và context.
4. Nếu cần, tạo challenge ngắn hạn và gắn với operation.
5. Client hoàn tất challenge qua identity provider hoặc verifier tin cậy.
6. Server xác minh kết quả, assurance level, freshness, audience, purpose và trạng thái dùng một lần.
7. Server đánh giá lại quyền, object, trạng thái và dữ liệu trước khi thực hiện side effect.
8. Ghi audit event và kết quả risk decision.

Không giữ một request đang mở vô thời hạn để chờ người dùng nhập OTP. Tạo challenge có thời hạn, cho client tiếp tục qua một request mới và bảo đảm operation không bị thực hiện hai lần.

### 7.1. Thiết kế response challenge

Response cần cho client biết bước tiếp theo nhưng không tiết lộ risk rule nội bộ. Ví dụ một contract riêng có thể trả:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/step-up-required",
  "title": "Additional authentication required",
  "status": 403,
  "challenge_id": "ch_opaque_short_lived",
  "action": "complete_step_up",
  "expires_in": 180
}
~~~

Đây chỉ là ví dụ response tùy biến. Status code và schema phải nhất quán với API contract và cơ chế OAuth/OIDC đang dùng. Không đưa điểm risk, rule bị kích hoạt, IP reputation hoặc tín hiệu phát hiện gian lận vào response công khai.

### 7.2. Bảo vệ challenge token

Challenge ID hoặc proof cần:

- Khó đoán và có entropy đủ cao.
- Hết hạn nhanh.
- Dùng một lần và được đánh dấu tiêu thụ nguyên tử.
- Gắn với principal, tenant, session, action và operation.
- Không được dùng ở endpoint hoặc audience khác.
- Không xuất hiện trong URL/log/referrer nếu có thể tránh.
- Được truyền qua kênh bảo mật và không lưu vào cache công khai.

Nếu hai request đồng thời sử dụng cùng proof, chỉ một request được phép tiêu thụ thành công. Việc kiểm tra và đánh dấu dùng một lần cần có tính nguyên tử để chống replay.

### 7.3. Hành vi client khi challenge

Client cần:

- Hiển thị lý do ở mức thân thiện và hướng dẫn bước tiếp theo.
- Không tự retry vô hạn khi nhận challenge.
- Không gửi lại payload nhạy cảm vào log hoặc telemetry phía client.
- Giữ nguyên operation ID/idempotency key khi tiếp tục cùng một thao tác.
- Bắt đầu operation mới nếu payload đã thay đổi.
- Xử lý challenge hết hạn hoặc bị thu hồi bằng cách bắt đầu lại luồng.

Với mobile/web app, cần tránh deep link hoặc redirect không được xác minh có thể chuyển challenge proof sang origin khác.

## 8. Phân biệt người dùng tương tác và machine-to-machine client

CAPTCHA, OTP nhập tay hoặc passkey tương tác phù hợp với một số luồng có người dùng hiện diện. Không nên áp dụng máy móc cho API-to-API hoặc service account.

Với machine client, các kiểm soát tương ứng có thể gồm:

- Workload identity hoặc OAuth client credentials với scope tối thiểu.
- mTLS hoặc cơ chế proof-of-possession khi phù hợp.
- Credential rotation và thu hồi nhanh.
- Giới hạn theo client, tenant, endpoint và cost.
- Phát hiện thay đổi bất thường về volume, endpoint hoặc thời gian gọi.
- Approval ngoài băng cho thay đổi scope hoặc thao tác có tác động cao.
- Tách service identity theo nhiệm vụ thay vì dùng một credential quản trị chung.

Nếu machine client thực hiện action thay mặt người dùng, cần có delegation context được xác minh và policy xác định rõ quyền nào được ủy quyền. Không để một service account dùng quyền của user chỉ vì request chứa userId.

## 9. Giảm false positive và bảo vệ quyền riêng tư

Risk-based control có thể làm gián đoạn người dùng hợp lệ. IP thay đổi, thiết bị mới, đi công tác, mạng công ty hoặc hành vi tăng đột biến vào mùa cao điểm không nhất thiết là tấn công.

Để giảm false positive:

- Kết hợp nhiều tín hiệu độc lập thay vì chặn theo một dấu hiệu yếu.
- Đặt ngưỡng khác nhau theo action và mức tác động.
- Dùng challenge tăng dần trước khi khóa hoặc từ chối dài hạn khi phù hợp.
- Cho phép recovery hoặc review an toàn.
- Theo dõi tỷ lệ challenge thành công, abandonment và khiếu nại.
- Kiểm tra tác động lên người dùng có công nghệ hỗ trợ hoặc thiết bị dùng chung.
- Có cơ chế cập nhật rule khi phát hiện một nhóm người dùng hợp lệ bị ảnh hưởng.

### 9.1. Data minimization

Không thu thập mọi tín hiệu có thể lấy được chỉ vì chúng có thể hữu ích. Với mỗi dữ liệu như IP, user agent, device signal, vị trí ước lượng hoặc hành vi, cần xác định:

- Mục đích bảo mật cụ thể.
- Cơ sở và phạm vi sử dụng phù hợp.
- Thời hạn lưu và cách xóa.
- Ai có quyền truy cập.
- Có thể dùng dữ liệu tổng hợp hoặc giả danh hóa thay thế không.
- Có được dùng cho mục đích khác ngoài mục đích đã thông báo không.

Không ghi OTP, access token, cookie, secret hoặc dữ liệu sinh trắc học thô vào risk log. Device fingerprint và vị trí cần được xử lý theo chính sách riêng tư và quy định áp dụng.

### 9.2. Không tiết lộ rule nội bộ

Client cần biết cần làm gì tiếp theo, nhưng không cần biết chính xác điểm số hoặc rule chống abuse. Nếu response nói rõ IP của bạn có reputation xấu hoặc bạn bị đánh dấu do thử 7 lần, attacker có thể điều chỉnh hành vi để né phát hiện.

Hãy trả reason code ở mức công khai đủ dùng như additional_verification_required hoặc temporarily_limited; giữ reason chi tiết trong audit log nội bộ với quyền truy cập được kiểm soát.

## 10. Xử lý khi risk service hoặc challenge provider lỗi

Risk engine và challenge provider cũng có thể gặp timeout, lỗi mạng hoặc dữ liệu không nhất quán. Cần định nghĩa hành vi theo mức tác động:

- Với action tài chính, thay đổi credential hoặc cấp quyền nhạy cảm, có thể fail closed hoặc chuyển sang manual review khi không đánh giá được risk.
- Với thao tác đọc ít rủi ro, có thể dùng policy fallback có giới hạn và tăng giám sát.
- Không được mặc định cho phép mọi action khi risk service không khả dụng.
- Không giữ request hoặc worker vô thời hạn để chờ provider.
- Challenge provider timeout không được coi là challenge thành công.
- Ghi metric, alert và reason code khi fallback được sử dụng.

Fallback phải được thiết kế trước và kiểm thử. Một cơ chế fail-open cho endpoint đọc không nên vô tình áp dụng cho refund hoặc thay đổi API key.

## 11. Kiểm thử risk signal, challenge và step-up

Test cần xác minh cả quyết định lẫn việc thực thi. Một response challenge đúng không có ý nghĩa nếu server vẫn thực hiện side effect trước khi challenge hoàn tất.

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Signal freshness | Dùng signal cũ hoặc hết hạn | Không áp dụng như tín hiệu hiện tại |
| Signal scope | Risk của user A không ảnh hưởng nhầm user B | Phạm vi đúng user/session/tenant |
| Threshold | Gửi request ngay dưới, tại và trên ngưỡng | Quyết định theo policy đã định |
| False positive | Thiết bị mới hoặc IP thay đổi đơn lẻ | Không tự động khóa tài khoản nếu chưa đủ căn cứ |
| Challenge validity | Challenge hết hạn, sai action hoặc sai tenant | Từ chối |
| Replay | Dùng lại challenge đã tiêu thụ hoặc gửi đồng thời | Chỉ một lần sử dụng thành công |
| Binding | Sửa amount/beneficiary sau khi challenge | Yêu cầu xác minh lại hoặc từ chối |
| Step-up assurance | Token không đủ acr/amr hoặc xác thực quá cũ | Không cho thực hiện action cần assurance cao |
| Authorization | Step-up thành công nhưng thiếu function/object permission | Vẫn từ chối |
| Client type | CAPTCHA được yêu cầu cho service account | Policy chọn cơ chế machine phù hợp |
| Provider failure | Risk/challenge provider timeout | Áp dụng fallback theo action, không coi là pass |
| Privacy | Kiểm tra log và response | Không có OTP, token, secret hoặc risk rule nhạy cảm |

### 11.1. Kiểm thử luồng hoàn chỉnh

Với một action nhạy cảm như đổi tài khoản nhận tiền, test nên xác minh:

1. Session hợp lệ nhưng chưa step-up: request bị challenge và không thay đổi dữ liệu.
2. Challenge hoàn tất bằng phương thức đủ mạnh: server xác minh proof và freshness.
3. Payload không thay đổi: action tiếp tục nếu permission, object và workflow state đều hợp lệ.
4. Payload bị sửa sau challenge: proof cũ không được chấp nhận cho giao dịch mới.
5. Challenge bị replay hoặc dùng ở tenant khác: từ chối.
6. Risk service lỗi: hành vi theo fail policy đã định.
7. Mọi kết quả được ghi audit mà không lộ credential.

Nên chạy integration test qua authentication provider và API security filter thực tế. Mock một boolean stepUpPassed=true trong unit test không chứng minh token hoặc challenge được xác minh đúng.

## 12. Giám sát hiệu quả của risk control

Các metric hữu ích:

- Số request được allow, monitor, challenge, step-up, restrict và deny.
- Tỷ lệ challenge được hoàn tất, thất bại, hết hạn hoặc bị bỏ dở.
- Tỷ lệ step-up thành công theo action và phương thức xác thực.
- Số challenge bị replay hoặc gửi sai purpose.
- Tỷ lệ false positive qua khiếu nại hoặc review.
- Latency và lỗi của risk service/challenge provider.
- Tỷ lệ gian lận hoặc sự cố sau khi đã challenge.
- Số lần dùng fallback do dependency không khả dụng.

Metric nên được phân nhóm theo endpoint template, action, loại client và mức rủi ro; tránh label có cardinality cao hoặc dữ liệu nhận diện cá nhân. Audit log cần ghi decision ID, reason code nội bộ, policy version, actor, tenant, action, kết quả và correlation ID.

Đánh giá hiệu quả không chỉ bằng số challenge được tạo. Nếu challenge tăng mạnh nhưng tỷ lệ gian lận không giảm hoặc người dùng hợp lệ bỏ cuộc nhiều hơn, policy cần được điều chỉnh. Cần xem xét cả chi phí vận hành, độ trễ và khả năng tiếp cận.

## 13. Những sai lầm thường gặp

- **Coi risk score là quyền:** điểm thấp không thay thế authorization và object scope.
- **Dựa vào một signal yếu:** IP hoặc thiết bị mới có thể gây false positive.
- **Dùng CAPTCHA như xác thực danh tính:** giải CAPTCHA không chứng minh quyền sở hữu tài khoản.
- **Dùng OTP cho mọi mức rủi ro:** OTP có thể bị phishing hoặc chiếm đoạt kênh nhận.
- **Step-up nhưng không ràng buộc action:** proof của một thao tác bị dùng lại cho thao tác khác.
- **Không kiểm tra freshness:** MFA từ lâu vẫn được coi là đủ cho action nhạy cảm.
- **Không bind transaction:** người dùng xác nhận một amount nhưng server thực hiện amount khác.
- **Challenge hoàn tất là tự động cho phép:** bỏ qua function, object, tenant và state authorization.
- **Challenge không có expiry hoặc one-time use:** tạo cơ hội replay.
- **Đưa risk rule vào response:** giúp attacker học cách né phát hiện.
- **Áp CAPTCHA cho machine client:** làm hỏng tích hợp mà không tăng bảo đảm phù hợp.
- **Fail-open không phân biệt action:** risk service lỗi khiến mọi thao tác được phép.
- **Thu thập tín hiệu quá mức:** tăng rủi ro riêng tư và chi phí mà không chứng minh được lợi ích.
- **Không đo false positive:** policy gây phiền cho người dùng hợp lệ và làm giảm tỷ lệ hoàn tất.

## 14. Checklist trước khi phát hành

- [ ] Xác định endpoint/action cần risk evaluation dựa trên tác động và khả năng lạm dụng.
- [ ] Mỗi risk signal có source, freshness, confidence, scope và retention.
- [ ] Tenant, user, session và client được phân biệt rõ trong risk context.
- [ ] Risk decision kết hợp nhiều tín hiệu và có reason code giải thích được.
- [ ] Có các hành động allow, monitor, challenge, step-up, restrict và deny phù hợp.
- [ ] CAPTCHA chỉ dùng để tăng chi phí automation, không thay thế xác thực.
- [ ] OTP/challenge có rate limit, expiry, purpose binding và chống replay.
- [ ] Step-up yêu cầu assurance/freshness phù hợp với action.
- [ ] Giao dịch nhạy cảm được bind với amount, beneficiary hoặc payload đã xác nhận.
- [ ] Challenge proof gắn với principal, tenant, session, action và operation.
- [ ] Step-up thành công vẫn phải qua function, object, tenant và workflow authorization.
- [ ] Machine client dùng workload identity, scope tối thiểu và proof phù hợp.
- [ ] Có fallback rõ ràng khi risk service hoặc challenge provider lỗi.
- [ ] Response không tiết lộ điểm số hoặc rule chống abuse nội bộ.
- [ ] Log không chứa OTP, token, secret hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Có test expiry, replay, payload tampering, concurrency, false positive và provider failure.
- [ ] Có metric cho challenge completion, false positive, latency và hiệu quả phát hiện.

Risk signal, challenge và step-up giúp API điều chỉnh mức xác minh theo hành vi và tác động của từng action. Khi tín hiệu được đánh giá đúng phạm vi, challenge được ràng buộc với mục đích và step-up không bỏ qua authorization nghiệp vụ, hệ thống có thể tăng sức chống lạm dụng mà vẫn giữ trải nghiệm hợp lý cho người dùng và client hợp lệ.
