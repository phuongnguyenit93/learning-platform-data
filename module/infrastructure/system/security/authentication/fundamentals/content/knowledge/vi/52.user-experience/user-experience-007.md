# Progressive security

**Progressive security** là cách thiết kế bảo mật theo mức độ rủi ro và độ nhạy của hành động. Hệ thống cho phép người dùng hoàn thành tác vụ thông thường bằng phiên và phương thức xác thực hiện có; khi bối cảnh thay đổi hoặc hành động có hậu quả lớn hơn, hệ thống yêu cầu thêm bằng chứng phù hợp như passkey, MFA chống phishing, xác minh lại gần đây hoặc approval độc lập. Mức bảo vệ tăng theo nhu cầu thực tế thay vì buộc mọi người thực hiện cùng một chuỗi xác minh nặng cho mọi thao tác.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. Progressive security kết nối các thành phần này thành trải nghiệm nhất quán: hệ thống biết bằng chứng nào đã có, bằng chứng đó còn mới và đủ mạnh không, hành động sắp thực hiện có rủi ro gì, và khi nào cần step-up hoặc từ chối.

Điểm cốt lõi: **tăng mức xác minh phải dựa trên policy rõ ràng, tín hiệu có giới hạn và giải thích được cho người dùng**. Risk score không phải bằng chứng danh tính; một thiết bị quen thuộc không làm token sai chữ ký trở nên hợp lệ; và step-up thành công không tự cấp quyền vượt quá authorization policy. Progressive security chỉ điều chỉnh cách thu thập bằng chứng và mức assurance cần thiết cho hành động.

## 1. Progressive security là gì?

Progressive security là mô hình áp dụng các lớp kiểm soát tăng dần theo ngữ cảnh. Người dùng bắt đầu với một mức xác thực cơ bản phù hợp với account và tác vụ. Nếu hệ thống phát hiện điều kiện cần bảo vệ cao hơn, nó có thể yêu cầu xác minh lại, thêm factor, dùng authenticator mạnh hơn, chờ approval hoặc từ chối hành động.

Ví dụ:
- Xem nội dung thông thường bằng session đang hoạt động.
- Khi thay đổi email hoặc số điện thoại, yêu cầu re-authentication gần đây.
- Khi thêm passkey mới, yêu cầu một authenticator hiện có hoặc recovery proofing.
- Khi xuất dữ liệu nhạy cảm, yêu cầu passkey hoặc MFA phishing-resistant.
- Khi cấp role quản trị, yêu cầu step-up và approval độc lập.
- Khi phát hiện token/session bất thường, yêu cầu xác minh lại hoặc revoke theo policy.

Progressive security không chỉ là “thêm MFA khi thấy lạ”. Nó bao gồm phân loại hành động, đánh giá assurance/freshness, quản lý session, kiểm soát recovery, thông báo minh bạch và xử lý trường hợp người dùng không thể hoàn tất step-up.

### 1.1. Phân biệt progressive security với các khái niệm gần

| Khái niệm | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Progressive security** | Tăng kiểm soát theo risk và action sensitivity. | Yêu cầu passkey khi thay đổi recovery method. |
| **Step-up authentication** | Yêu cầu bằng chứng xác thực bổ sung hoặc mạnh hơn. | Dùng security key trước khi cấp quyền admin. |
| **Risk-based authentication** | Dùng tín hiệu để ước lượng rủi ro và chọn policy. | Phát hiện refresh token reuse hoặc thiết bị mới. |
| **Continuous authentication** | Đánh giá lại trust trong suốt session hoặc khi có event. | Revoke session khi credential bị báo lộ. |
| **Progressive profiling** | Thu thập thêm thông tin hồ sơ theo nhu cầu. | Yêu cầu thông tin thanh toán khi user mua hàng. |

Progressive profiling không đồng nghĩa progressive security. Thu thập thêm profile data không tự tăng assurance và có thể làm tăng rủi ro privacy nếu không có mục đích rõ.

### 1.2. Vì sao cần progressive security?

Nếu mọi thao tác đều yêu cầu xác minh mạnh nhất, trải nghiệm trở nên chậm và người dùng có thể tìm cách né tránh hoặc chấp nhận prompt một cách máy móc. Nếu chỉ dùng một mức xác thực cho mọi tác vụ, account đã đăng nhập có thể thực hiện hành động nhạy cảm mà không có bằng chứng mới.

Progressive security giúp:
- Giảm friction ở tác vụ ít rủi ro.
- Tăng assurance ở thời điểm có hậu quả lớn.
- Giảm cơ hội attacker tận dụng session đã bị chiếm.
- Hạn chế prompt MFA không cần thiết.
- Tạo policy dễ giải thích và kiểm toán.
- Giữ đường recovery an toàn khi authenticator bị mất.

## 2. Các thành phần của quyết định progressive security

Một quyết định tốt kết hợp ít nhất bốn thành phần: principal/session context, action sensitivity, risk signals và assurance requirement.

### 2.1. Principal và session context

Context có thể gồm:
- Principal đã được xác minh theo issuer và subject.
- Authentication method đã dùng.
- Thời điểm authentication gần nhất.
- Assurance class hoặc authentication context.
- Session age, idle age và absolute expiry.
- Session/device binding nếu hệ thống hỗ trợ.
- Token issuer, audience, scope và trạng thái.
- Các sự kiện gần đây như recovery, password reset hoặc authenticator change.

Chỉ dùng context được xác minh từ nguồn tin cậy. Không lấy role hoặc identity từ header do client tự khai.

### 2.2. Action sensitivity

Phân loại action theo tác động nếu bị thực hiện trái phép:
- Public/read-only.
- Thay đổi preference ít nhạy cảm.
- Truy cập dữ liệu cá nhân.
- Thay đổi login identifier hoặc recovery channel.
- Thêm/xóa authenticator.
- Tạo API key hoặc OAuth grant.
- Chuyển tiền, ký duyệt hoặc export dữ liệu lớn.
- Cấp quyền, thay policy hoặc quản trị tenant.

Không phải mọi endpoint cùng một mức rủi ro. Một action đọc hồ sơ có thể ít nhạy cảm hơn action đổi email dùng để reset password.

### 2.3. Risk signals

Tín hiệu có thể gồm:
- Login failure hoặc credential stuffing pattern.
- Token refresh reuse hoặc session anomaly.
- Thiết bị mới hoặc device posture thay đổi.
- IP/ASN/region thay đổi ở mức khái quát.
- Session age hoặc authentication freshness.
- Account recovery vừa diễn ra.
- Password, passkey hoặc MFA factor vừa thay đổi.
- Request rate và hành vi transaction bất thường.
- Known compromised credential hoặc threat intelligence đã xác minh.

Tín hiệu phải được đánh giá theo chất lượng và nguồn. Một IP mới có thể là VPN hoặc mạng di động; một user agent mới có thể do cập nhật trình duyệt. Không coi một tín hiệu yếu là bằng chứng compromise.

### 2.4. Assurance requirement

Policy xác định loại bằng chứng cần thiết:
- Session hiện tại còn hợp lệ.
- Re-authentication bằng credential đã đăng ký.
- MFA bổ sung.
- Phishing-resistant authenticator như passkey/WebAuthn hoặc security key.
- Certificate/workload identity với proof phù hợp.
- Approval từ người có thẩm quyền khác.
- Identity proofing hoặc recovery flow.
- Từ chối nếu không thể đạt assurance cần thiết.

Yêu cầu phải gắn với action và threat model. Không dùng nhãn “MFA passed” chung chung nếu một factor có thể bị phishing hoặc không đáp ứng mức assurance mong muốn.

## 3. Phân loại mức bảo vệ theo hành động

Một ma trận action-to-assurance giúp team sản phẩm, security và UX thống nhất khi nào cần step-up.

| Mức hành động | Ví dụ | Kiểm soát tham khảo |
| --- | --- | --- |
| **Mức 0 — Public** | Đọc trang công khai. | Không yêu cầu authentication nếu không có dữ liệu riêng. |
| **Mức 1 — Routine** | Xem dashboard cá nhân, preference. | Session hợp lệ và authorization thông thường. |
| **Mức 2 — Sensitive** | Xem dữ liệu riêng tư, tải báo cáo cá nhân. | Session còn mới; step-up khi risk tăng hoặc policy yêu cầu. |
| **Mức 3 — Security change** | Đổi email, đổi password, thêm passkey, đổi recovery method. | Re-authentication bằng authenticator hiện có; thông báo kênh đã xác minh. |
| **Mức 4 — High impact** | Export dữ liệu lớn, phê duyệt giao dịch, cấp API credential. | Phishing-resistant step-up, transaction binding và xác nhận rõ. |
| **Mức 5 — Privileged** | Cấp admin role, thay trust policy, quản trị identity provider. | Authenticator mạnh, freshness ngắn, dual control/approval và audit. |

Các mức trên là ví dụ để thiết kế policy, không phải chuẩn assurance chính thức. Tổ chức cần ánh xạ chúng tới risk appetite, yêu cầu pháp lý, assurance framework và khả năng của authenticator.

### 3.1. Không dùng một factor cho mọi cấp

Password có thể đủ cho một số luồng thông thường nếu policy cho phép, nhưng không chống phishing. SMS OTP có thể hữu ích như fallback trong một số bối cảnh, nhưng không tương đương passkey hoặc security key chống phishing. Chọn factor theo threat model, không theo sự tiện lợi của API.

### 3.2. Tách xác thực khỏi authorization

Step-up chứng minh user đã cung cấp bằng chứng mạnh hơn hoặc mới hơn. Nó không tự cấp role hoặc scope mới. Sau step-up, backend vẫn phải kiểm tra:
- Principal có quyền trên resource không?
- Action có nằm trong scope/role hiện tại không?
- Tenant/resource mapping có đúng không?
- Có approval hoặc segregation-of-duties requirement không?
- Resource có bị khóa hoặc policy deny không?

## 4. Authentication freshness và session context

Freshness là mức độ gần đây của lần xác thực hoặc step-up. Một session có thể vẫn active nhưng authentication đã quá cũ đối với hành động nhạy cảm.

### 4.1. Session age không đồng nghĩa authentication freshness

Session được tạo lúc 09:00 và có thể tiếp tục tới cuối ngày. Nếu user re-authenticate lúc 14:00, freshness cho thao tác sau 14:00 khác với thời điểm tạo session ban đầu. Hệ thống cần lưu thời điểm xác thực thực tế và context của lần xác minh gần nhất.

Phân biệt:
- **Session creation time:** lúc session được tạo.
- **Authentication time:** lúc principal được xác minh.
- **Step-up time:** lúc yêu cầu assurance bổ sung được hoàn tất.
- **Last activity:** lúc session được sử dụng.
- **Token issue time:** lúc token được phát hành.
- **Token expiry:** thời điểm token không còn hợp lệ.

Không dùng last activity để giả định authentication vừa diễn ra.

### 4.2. Freshness policy

Ví dụ minh họa:
- Tác vụ routine có thể dùng session trong giới hạn idle/absolute timeout.
- Đổi recovery email yêu cầu authentication trong vài phút gần nhất.
- Thay đổi authenticator yêu cầu re-authentication bằng factor hiện có.
- Cấp admin role yêu cầu phishing-resistant step-up và approval mới.
- Giao dịch giá trị cao yêu cầu xác nhận gắn với chính transaction.

Thời hạn thực tế cần dựa trên rủi ro và khả năng sử dụng. Không chọn con số chỉ vì dễ cấu hình.

### 4.3. Dùng authentication context

Với OIDC, application có thể sử dụng các claim/context như auth_time, acr và amr theo profile và mapping đã xác minh. Với protocol khác, dùng field tương ứng. Không suy ra mức assurance chỉ từ chuỗi tên method nếu issuer không có contract rõ.

Nếu context không đủ hoặc không đáng tin, yêu cầu step-up hoặc từ chối action theo policy.

## 5. Risk engine và policy decision

Risk engine thu thập tín hiệu và đưa ra risk assessment; policy engine quyết định hành động. Tách hai phần giúp tránh việc một điểm số không giải thích được trực tiếp cấp quyền.

### 5.1. Risk assessment

Một mô hình đơn giản có thể phân loại:
- Low: không thấy tín hiệu bất thường đáng kể.
- Medium: có một hoặc nhiều tín hiệu cần xác minh thêm.
- High: có dấu hiệu compromise hoặc hành động có hậu quả lớn.
- Critical: có bằng chứng rõ về credential/session compromise hoặc policy violation.

Các mức phải có định nghĩa, nguồn tín hiệu và cách xử lý. Không giả định risk score có ý nghĩa giống nhau giữa các hệ thống.

### 5.2. Policy decision

Decision có thể là:
- Allow với session hiện tại.
- Allow nhưng giới hạn action.
- Require re-authentication.
- Require step-up factor cụ thể.
- Require approval độc lập.
- Delay/pending để user xác nhận qua kênh tin cậy.
- Deny và revoke session/credential.
- Escalate tới review/helpdesk.

Risk engine không nên trả về “allow” trực tiếp mà bỏ qua authorization và validation bắt buộc.

### 5.3. Policy có thể giải thích

Mỗi decision nên có:
- Action/resource.
- Risk category và signal family.
- Assurance requirement.
- Decision và reason code.
- Policy version.
- Thời điểm và TTL của challenge.
- Hướng xử lý nếu user không hoàn tất.
- Audit reference.

Không cần hiển thị chi tiết detector hoặc threshold cho end user nếu điều đó giúp attacker né kiểm soát. Nhưng UX nên giải thích lý do ở mức hữu ích, ví dụ “Bạn cần xác minh lại trước khi thay đổi phương thức khôi phục”.

## 6. Step-up authentication trong trải nghiệm người dùng

Step-up là điểm tương tác nhạy cảm. Một prompt không rõ ràng có thể khiến người dùng chấp nhận request phishing hoặc nhầm lẫn giữa thao tác của mình và của attacker.

### 6.1. Thời điểm yêu cầu step-up

Yêu cầu step-up ngay trước action cần bảo vệ, hoặc trước khi hoàn tất một transaction có thể bị thay đổi. Tránh hỏi quá sớm rồi dùng kết quả cho một hành động khác sau thời gian dài.

Step-up nên được gắn với:
- Account/principal.
- Session.
- Action và resource.
- Transaction payload hoặc transaction reference.
- Challenge nonce.
- TTL.
- Required assurance.
- Policy version.

Nếu user thay đổi người nhận, số tiền, recovery email hoặc target role sau khi xác minh, challenge cũ không được tự động áp dụng cho payload mới.

### 6.2. Chọn factor phù hợp

- Passkey/WebAuthn có thể cung cấp xác minh gắn với RP ID và chống phishing tốt.
- Security key có thể phù hợp cho account đặc quyền.
- TOTP có thể tăng lớp bảo vệ nhưng mã có thể bị phishing hoặc relay.
- Push approval cần hiển thị transaction context và chống push fatigue.
- Certificate/mTLS phù hợp cho workload/service identity.
- Recovery proofing cần quy trình riêng khi factor chính bị mất.

Không yêu cầu thêm factor yếu hơn chỉ để hoàn tất luồng nếu policy yêu cầu phishing-resistant assurance.

### 6.3. Transaction confirmation

Với hành động có hậu quả lớn, chỉ xác minh “đúng người” có thể chưa đủ. User cần xác nhận chính xác hành động:
- Ai là người nhận?
- Số tiền hoặc dữ liệu nào sẽ được chuyển/xuất?
- Quyền nào sẽ được cấp?
- Email hoặc phone nào sẽ được thay đổi?
- Thiết bị nào sẽ được đăng ký?

Challenge phải ràng buộc với payload. Nếu payload đổi, cần tạo transaction/challenge mới.

### 6.4. Chống prompt fatigue

- Không gửi nhiều push challenge song song.
- Không lặp prompt không giải thích.
- Có nút từ chối hoặc báo cáo request không do user khởi tạo.
- Rate limit challenge và approval.
- Hiển thị context đủ để nhận ra request lạ.
- Sau nhiều lần từ chối, đánh giá session/credential theo policy.

Không dùng “Approve” một chạm thiếu context cho thao tác nhạy cảm.

## 7. Trải nghiệm khi risk tăng

Một hệ thống tốt giải thích điều gì đang xảy ra mà không làm lộ tín hiệu phát hiện quá chi tiết.

### 7.1. Thông điệp cho người dùng

Thông điệp nên:
- Nêu hành động cần xác minh.
- Nói vì sao cần thêm bước ở mức tổng quát.
- Hướng dẫn factor được chấp nhận.
- Cho biết challenge hết hạn khi nào.
- Có cách hủy hoặc báo cáo.
- Không tiết lộ token, rule ID, threshold hoặc dữ liệu của người dùng khác.

Ví dụ: “Để bảo vệ tài khoản, hãy xác minh bằng passkey trước khi thêm phương thức đăng nhập mới.”

### 7.2. Không dùng thông điệp gây hoảng sợ

Nếu chỉ là thiết bị mới hoặc session cũ, không nên khẳng định “tài khoản đã bị tấn công”. Nói rõ hệ thống cần xác minh thêm. Nếu có bằng chứng compromise, cung cấp hướng dẫn containment cụ thể và kênh hỗ trợ chính thức.

### 7.3. Hỗ trợ người dùng không có factor

Nếu user mất điện thoại hoặc security key:
- Cung cấp recovery path đã được phê duyệt.
- Không tự hạ assurance mà không có proofing.
- Giải thích thời gian chờ hoặc approval nếu có.
- Cho phép hủy request.
- Thông báo qua kênh đã xác minh trước đó.
- Không yêu cầu user gửi OTP, password hoặc recovery code cho support.

Recovery là một luồng có risk riêng; attacker có thể cố tình kích hoạt step-up để ép user chuyển sang fallback yếu.

## 8. Progressive security theo vòng đời account

Progressive controls không chỉ xảy ra trong login. Chúng áp dụng xuyên suốt vòng đời credential, session và quyền.

### 8.1. Enrollment

Khi tạo account hoặc đăng ký credential:
- Xác minh identity theo mức phù hợp.
- Xác nhận email/phone qua flow an toàn nếu dùng làm identifier/recovery.
- Khuyến khích đăng ký phương thức dự phòng.
- Yêu cầu re-authentication trước khi thêm factor vào account đang hoạt động.
- Thông báo khi authenticator mới được thêm.
- Không coi thiết bị vừa cài app là trusted chỉ vì có device ID.

### 8.2. Login

- Dùng authentication method theo account policy.
- Đánh giá risk context.
- Step-up khi có tín hiệu hoặc action cần assurance cao.
- Giới hạn attempts và chống credential stuffing.
- Tạo session với timeout và binding phù hợp.
- Ghi audit event và metric an toàn.

### 8.3. Trong session

- Enforce idle/absolute timeout.
- Đánh giá lại khi credential, account hoặc device state thay đổi.
- Yêu cầu step-up cho action nhạy cảm.
- Revoke khi phát hiện compromise.
- Không kéo dài session chỉ vì user đang hoạt động nếu absolute timeout đã đạt.
- Không để background polling giả lập user activity nếu policy không cho phép.

### 8.4. Credential và account changes

Các thao tác như đổi password, thay email, thêm passkey, xóa MFA, tạo API key hoặc link IdP cần policy riêng. Một session bình thường không mặc nhiên đủ cho mọi thay đổi.

### 8.5. Logout và recovery

Logout phải revoke server-side theo kiến trúc và giải thích phạm vi local/global. Recovery phải xác minh bằng chứng độc lập, revoke credential cũ bị ảnh hưởng và yêu cầu enrollment lại theo policy.

## 9. Progressive security và chống phishing

Progressive security cần tránh tạo prompt mà attacker có thể relay hoặc social-engineer.

### 9.1. Ưu tiên phishing-resistant authentication

Passkey/WebAuthn và security key gắn với RP ID/origin giúp chống phishing tốt hơn password/TOTP. Với thao tác đặc quyền, có thể yêu cầu authenticator phishing-resistant thay vì chỉ thêm một OTP.

### 9.2. Hiển thị đúng origin và hành động

- Không yêu cầu user nhập OTP vào trang do support gửi.
- Không yêu cầu đọc recovery code qua điện thoại.
- Push prompt phải hiển thị account, action và transaction context.
- Passkey prompt phải xuất hiện trong đúng app/site origin.
- Thông báo bảo mật phải dùng domain/app chính thức.
- Cung cấp cách từ chối và báo cáo prompt lạ.

### 9.3. Step-up không phải bằng chứng chống phishing tuyệt đối

MFA có thể bị relay, push fatigue hoặc social engineering. Risk engine có thể hỗ trợ phát hiện nhưng không thay thế protocol chống phishing, origin binding, transaction binding và user education.

## 10. Privacy và công bằng trong risk-based UX

Risk signals có thể liên quan đến vị trí, thiết bị, mạng, hành vi và thói quen. Thu thập quá mức có thể gây xâm phạm riêng tư hoặc làm sai quyết định.

### 10.1. Data minimization

- Chỉ dùng tín hiệu cần cho mục đích xác thực.
- Ưu tiên region/ASN class thay vì lưu vị trí chính xác nếu không cần.
- Không lưu device fingerprint rộng nếu không có cơ sở và policy.
- Giới hạn retention của risk feature.
- Tách dữ liệu risk khỏi nội dung business.
- Không đưa user ID/IP/token thô vào metric label.
- Document nguồn, purpose, owner và access control.

### 10.2. False positive và false negative

False positive có thể khóa người dùng hợp lệ, đặc biệt khi:
- User đổi điện thoại hoặc đi du lịch.
- VPN hoặc mạng di động làm IP thay đổi.
- Trình duyệt cập nhật.
- Người dùng có khuyết tật hoặc dùng assistive technology.
- Đồng hồ thiết bị lệch.
- Nhiều người dùng chung thiết bị hợp lệ.

False negative có thể để attacker dùng session hoặc credential bị chiếm. Cần theo dõi cả hai loại lỗi và có con đường hỗ trợ an toàn.

### 10.3. Không dùng thuộc tính nhạy cảm làm proxy tùy tiện

Không suy ra risk từ chủng tộc, tôn giáo, sức khỏe, giới tính hoặc thuộc tính nhạy cảm khác. Không dùng vùng địa lý hoặc thiết bị như một proxy thiếu kiểm chứng cho đặc điểm cá nhân. Review feature, bias và impact trước khi triển khai.

### 10.4. Giải thích và khiếu nại

Người dùng cần biết:
- Vì sao một hành động bị yêu cầu xác minh thêm.
- Có thể hoàn tất bằng cách nào.
- Làm gì nếu không có factor.
- Làm sao báo cáo yêu cầu không phải của mình.
- Cách yêu cầu review nếu bị chặn nhầm.

## 11. Accessibility và inclusive authentication

Một policy bảo mật không nên mặc định mọi người đều có cùng thiết bị, khả năng vận động, thị giác, thính giác hoặc kết nối mạng.

Cần xem xét:
- Passkey có thể dùng trên nhiều platform và thiết bị hỗ trợ.
- Có phương thức dự phòng an toàn khi user không thể dùng biometric hoặc security key.
- Không yêu cầu thao tác drag/drop hoặc nhận diện hình ảnh nếu có lựa chọn accessible.
- Hỗ trợ screen reader và keyboard navigation.
- Không dùng timeout quá ngắn cho người cần thêm thời gian.
- Không yêu cầu nghe mã qua điện thoại làm lựa chọn duy nhất.
- Có flow phục hồi khi thiết bị hỏng hoặc mất.
- Thông báo lỗi nêu cách khắc phục thay vì chỉ hiện mã kỹ thuật.

Accessibility không có nghĩa bỏ xác minh. Nó yêu cầu nhiều con đường xác minh có assurance tương đương phù hợp với policy.

## 12. Policy state machine cho progressive security

Một state machine giúp client và server xử lý step-up nhất quán.

| Trạng thái | Ý nghĩa | Chuyển tiếp |
| --- | --- | --- |
| **normal** | Session đáp ứng yêu cầu hiện tại. | step_up_required, restricted hoặc revoked. |
| **step_up_required** | Action cần assurance/freshness cao hơn. | challenge_pending hoặc denied. |
| **challenge_pending** | Challenge đã được tạo và đang chờ user. | verified, failed, expired hoặc cancelled. |
| **verified** | Bằng chứng step-up hợp lệ cho transaction cụ thể. | action_authorized hoặc restricted. |
| **action_authorized** | Authorization riêng cho action đã kiểm tra. | completed hoặc failed. |
| **restricted** | Session chỉ được phép thực hiện một tập action giới hạn. | normal sau re-auth, revoked hoặc expired. |
| **denied** | Policy từ chối action. | normal nếu không ảnh hưởng session; review nếu cần. |
| **revoked** | Session hoặc credential không còn được tin cậy. | Recovery/re-enrollment theo flow riêng. |
| **expired** | Session/challenge hết thời hạn. | Authentication/recovery mới. |

### 12.1. Transaction binding

Challenge cần ràng buộc:
- Principal và session.
- Action/resource.
- Transaction ID và payload hash/reference.
- Nonce/challenge ID.
- Required authenticator/assurance.
- Issued-at và expiry.
- Policy version.
- One-time consumption state.

Không cho phép dùng một challenge xác minh “thêm passkey” để phê duyệt “đổi email” hoặc một transaction có payload khác.

### 12.2. Idempotency và race

Nhiều request có thể gửi cùng challenge do retry hoặc nhiều tab. Server cần:
- Consume challenge atomically.
- Kiểm tra trạng thái và version.
- Dùng idempotency key cho action có side effect.
- Chặn replay và double submit.
- Không cho response cũ ghi đè session state mới.
- Hủy challenge khi account/session bị revoke.

## 13. Progressive security trong các tình huống thực tế

### 13.1. Đăng nhập từ thiết bị mới

- Xác minh credential theo policy.
- Đánh giá risk signals có độ tin cậy phù hợp.
- Nếu cần, yêu cầu passkey hoặc MFA bổ sung.
- Không tự động link identity theo email.
- Thông báo đăng nhập mới qua kênh đã xác minh.
- Tạo session với scope/timeout phù hợp.

### 13.2. Thay đổi recovery email

- Kiểm tra session và authentication freshness.
- Re-authenticate bằng factor đã đăng ký trước.
- Xác minh email mới bằng transaction riêng.
- Thông báo tới email cũ hoặc kênh tin cậy đã đăng ký.
- Có delay/review nếu risk cao.
- Không cho email mới tự xác minh quyền sở hữu account hiện tại.

### 13.3. Thêm passkey

- Yêu cầu re-authentication hoặc step-up.
- Ràng buộc WebAuthn challenge với RP ID/origin và account.
- Hiển thị thiết bị/credential enrollment context.
- Xác nhận enrollment hoàn tất trước khi active.
- Thông báo và cho phép revoke credential lạ.
- Không xóa authenticator cuối cùng trước khi có recovery path.

### 13.4. Tạo API key hoặc client credential

- Chỉ role có quyền mới được tạo.
- Yêu cầu phishing-resistant step-up nếu key có quyền cao.
- Hiển thị scope, expiry và owner.
- Chỉ hiển thị secret một lần theo thiết kế.
- Ghi audit reference, không ghi secret.
- Có revoke/rotate và inventory.

### 13.5. Giao dịch giá trị cao

- Kiểm tra token/session, freshness và authorization.
- Yêu cầu step-up phù hợp.
- Hiển thị recipient/amount hoặc payload thực tế.
- Bind approval với transaction.
- Chặn sửa payload sau khi xác nhận.
- Ghi evidence về method, outcome và transaction reference.

### 13.6. Quản trị đặc quyền

- Phishing-resistant authenticator.
- Freshness ngắn.
- Dual control khi cấp quyền hoặc thay trust configuration.
- Tách requester và approver.
- Session đặc quyền có lifetime ngắn hơn.
- Audit đầy đủ và review định kỳ.
- Break-glass có scope/time limit riêng.

## 14. Khi step-up thất bại hoặc không thể thực hiện

Không phải mọi challenge đều hoàn tất. Hệ thống cần quyết định rõ cách xử lý mà không làm người dùng mắc kẹt hoặc tạo bypass.

### 14.1. Phân biệt các kết quả

- User từ chối challenge.
- User không phản hồi và challenge timeout.
- Authenticator không khả dụng.
- Proof sai hoặc replay.
- Provider outage.
- Network timeout.
- Policy deny do risk cao.
- Account/session đã bị revoke.
- Challenge bị hủy vì transaction thay đổi.

Mỗi reason có hành vi khác nhau. Network outage không phải user failure; proof sai không nên được retry vô hạn; account revoked cần recovery hoặc support theo policy.

### 14.2. Fallback

Fallback chỉ được dùng nếu:
- Được policy cho phép trước.
- Có assurance phù hợp với action.
- Không phụ thuộc cùng một nguồn đã bị compromise.
- Có rate limit và audit.
- Không tạo downgrade âm thầm.

Ví dụ có thể dùng security key dự phòng thay passkey trên thiết bị bị hỏng. Không tự chuyển từ phishing-resistant requirement sang SMS OTP nếu policy không cho phép.

### 14.3. Hủy an toàn

Nếu user không thể hoàn tất:
- Không thực hiện action đang chờ.
- Giữ dữ liệu form ở trạng thái an toàn nếu phù hợp.
- Hủy challenge khi hết TTL.
- Không tạo side effect một phần.
- Cho biết cách thử lại hoặc dùng recovery path.
- Ghi outcome và reason code không chứa secret.

## 15. Metrics và audit cho progressive security

Theo dõi hiệu quả policy mà không biến telemetry thành kho định danh.

### 15.1. Metric vận hành

Có thể đo:
- Step-up challenge issued.
- Step-up success/failure/timeout.
- Challenge latency.
- Tỷ lệ abandon.
- Tỷ lệ fallback theo method class.
- Action bị deny do freshness/assurance.
- Session revoke do risk decision.
- False-positive review rate.
- Provider error và challenge delivery failure.
- Transaction completion sau step-up.

Label nên là enum hữu hạn như action class, auth method class, result, reason và environment. Không dùng user ID, email, session ID, token hoặc raw IP làm label.

### 15.2. Audit evidence

Ghi:
- Actor/principal reference.
- Action/resource và transaction reference.
- Risk category hoặc signal family đã phê duyệt.
- Assurance requirement và authentication context.
- Challenge issued/completed/denied.
- Policy version và reason code.
- Approval/recovery reference nếu có.
- Outcome và timestamp.

Không ghi risk feature thô hoặc token/OTP vào audit nếu không có nhu cầu đã được phê duyệt.

### 15.3. Đánh giá hiệu quả

Review:
- Tỷ lệ step-up theo action class.
- Tỷ lệ hoàn tất và abandon.
- False positive và support ticket.
- Incident/ATO rate liên quan.
- Thời gian hoàn tất tác vụ.
- Tỷ lệ fallback yếu.
- Chênh lệch tác động giữa nhóm người dùng.
- Số prompt lặp lại hoặc push fatigue.
- Tác động tới accessibility.

Mục tiêu không phải tối đa hóa số lần step-up. Mục tiêu là đạt assurance cần thiết với friction, privacy và false-positive ở mức chấp nhận được.

## 16. Threat model cho progressive security

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Step-up phishing** | Attacker giả trang prompt để lấy OTP hoặc approval. | Credential bị relay hoặc user approve nhầm. | Passkey/security key, origin binding, transaction context và anti-phishing UX. |
| **Push fatigue** | Gửi nhiều approval prompt tới user. | User chấp nhận để dừng làm phiền. | Rate limit, number matching/context, deny/report và alert. |
| **Risk signal spoofing** | Client tự khai device/location/risk context. | Policy decision sai. | Tín hiệu server-verified, source trust và bounded feature. |
| **Risk score over-trust** | Một điểm số tự động cấp quyền. | Bypass authentication/authorization. | Tách risk assessment, assurance và authorization. |
| **Fallback downgrade** | Step-up thất bại rồi chuyển sang factor yếu. | Giảm assurance của action nhạy cảm. | Minimum assurance và fallback policy rõ. |
| **Challenge replay** | Dùng lại challenge đã xác minh. | Thực hiện action ngoài transaction. | Nonce, TTL, one-time consume và transaction binding. |
| **Payload substitution** | Đổi recipient/amount/role sau approval. | User xác nhận một action nhưng action khác được thực hiện. | Payload hash/reference binding và re-approval khi thay đổi. |
| **Session fixation/theft** | Attacker dùng session đã chiếm để gọi action. | Vượt login step nhưng vẫn thao tác được. | Session rotation, binding, revoke và step-up theo action. |
| **False positive lockout** | Risk engine đánh giá nhầm user hợp lệ. | Mất quyền truy cập, support burden. | Review, recovery path và theo dõi fairness. |
| **Privacy over-collection** | Thu thập fingerprint/location quá mức. | Lộ dữ liệu và tracking. | Data minimization, purpose limitation và retention. |
| **Accessibility exclusion** | Chỉ hỗ trợ một factor hoặc thao tác. | Người dùng không thể hoàn tất authentication. | Alternative factor có assurance tương đương và accessible flow. |
| **Stale assurance** | Dùng kết quả step-up cũ cho action mới. | Action nhạy cảm được phép bằng bằng chứng đã cũ. | Freshness TTL, action binding và policy version. |
| **Concurrent challenge race** | Hai tab/request consume cùng challenge. | Duplicate action hoặc state inconsistency. | Atomic consume, idempotency và state machine. |

## 17. Tình huống thực hành: thêm passkey sau khi đăng nhập từ thiết bị mới

**Bối cảnh:** Linh đăng nhập vào cổng nhân sự từ laptop mới bằng password và TOTP. Session được tạo thành công. Linh muốn thêm passkey để lần sau đăng nhập nhanh hơn. Hệ thống thấy thiết bị mới, session chưa lâu nhưng account vừa thực hiện password reset trong ngày.

**Phân tích:**

1. Login thành công không chứng minh request thêm authenticator mới là an toàn.
2. Password reset gần đây là tín hiệu cần đánh giá; nó có thể hợp lệ nhưng cũng có thể là một phần của account takeover.
3. Thiết bị mới làm tăng uncertainty nhưng không tự chứng minh compromise.
4. Thêm passkey là thay đổi credential có thể tạo đường truy cập bền vững.
5. Recovery method hiện tại cần được kiểm tra trước khi cho phép thêm credential.

**Luồng progressive security:**

- Policy đánh giá action class là security change và yêu cầu assurance cao hơn session thường.
- Hệ thống yêu cầu re-authentication bằng authenticator đã đăng ký trước, theo policy có thể là passkey/security key hiện có hoặc proofing đủ mạnh.
- Challenge được bind với account, RP ID/origin, transaction và credential enrollment.
- UI giải thích rằng cần xác minh trước khi thêm phương thức đăng nhập.
- Nếu Linh không còn authenticator cũ, chuyển sang recovery workflow đã được phê duyệt; không tự hạ xuống email mới hoặc SMS mới.
- Sau khi enrollment hoàn tất, hệ thống gửi notification tới channel đã xác minh.
- Audit event ghi actor, factor class, policy version, target credential reference và outcome; không ghi private key hoặc assertion thô.
- Linh có thể xem và revoke credential mới nếu không nhận ra.

**Câu hỏi:** Vì Linh vừa vượt qua password và TOTP, có thể bỏ step-up cho thao tác thêm passkey không? Không mặc nhiên. Policy cần xét freshness, risk signals, action sensitivity và assurance requirement. Hai yếu tố đã dùng cho login có thể đáp ứng nếu policy quy định rõ; nếu không, cần thêm bằng chứng hoặc recovery proofing thích hợp.

## 18. Checklist thiết kế progressive security

- [ ] Phân loại action theo tác động và dữ liệu được truy cập.
- [ ] Định nghĩa assurance/freshness requirement cho từng action class.
- [ ] Phân biệt session age, authentication time, step-up time và last activity.
- [ ] Xác định risk signals, nguồn, độ tin cậy, owner và retention.
- [ ] Không dùng risk score thay signature, issuer, audience hoặc authorization validation.
- [ ] Tách risk assessment khỏi policy decision và authorization.
- [ ] Ưu tiên phishing-resistant authenticator cho action nhạy cảm/đặc quyền.
- [ ] Bind challenge với principal, session, action, resource và transaction payload.
- [ ] Dùng nonce, TTL, one-time consume và idempotency để chống replay/race.
- [ ] Không dùng một challenge cho action hoặc payload khác.
- [ ] Hiển thị rõ lý do tổng quát, action và factor cần dùng.
- [ ] Chống push fatigue bằng rate limit, context và deny/report.
- [ ] Có fallback được phê duyệt với assurance tối thiểu.
- [ ] Có recovery path an toàn khi mất authenticator.
- [ ] Không tự động link identity theo email hoặc device ID.
- [ ] Duy trì idle/absolute timeout, revoke và session rotation.
- [ ] Bảo vệ privacy bằng data minimization và bounded metric labels.
- [ ] Review false positive/negative, bias và tác động tới accessibility.
- [ ] Hỗ trợ screen reader, keyboard, timeout hợp lý và nhiều factor.
- [ ] Ghi audit policy version, reason, actor, target, challenge và outcome.
- [ ] Đo step-up completion, abandon, latency, fallback và support burden.
- [ ] Kiểm thử phishing, replay, payload substitution, stale assurance và concurrency.
- [ ] Diễn tập provider outage, recovery, account compromise và break-glass.
- [ ] Review policy định kỳ khi threat, product action hoặc authenticator thay đổi.

## 19. Câu hỏi tự kiểm tra

**1. Progressive security là gì?**  
Là cách tăng mức xác minh theo rủi ro và độ nhạy của hành động, dựa trên policy và bằng chứng xác thực.

**2. Progressive security khác step-up authentication thế nào?**  
Progressive security là chiến lược tổng thể; step-up là một kỹ thuật yêu cầu bằng chứng bổ sung trong chiến lược đó.

**3. Vì sao session active chưa chắc đủ cho action nhạy cảm?**  
Session có thể còn hạn nhưng authentication đã cũ, assurance chưa đủ hoặc risk context đã thay đổi.

**4. Risk score có thể tự cấp quyền không?**  
Không. Nó chỉ hỗ trợ đánh giá; validator và authorization policy vẫn phải thực thi độc lập.

**5. Khi nào cần transaction binding?**  
Khi step-up phê duyệt hành động có payload như chuyển tiền, đổi email, thêm passkey hoặc cấp role; thay payload phải tạo challenge mới.

**6. Có nên chuyển sang SMS OTP nếu passkey step-up thất bại?**  
Chỉ khi policy đã cho phép và assurance phù hợp. Không được downgrade âm thầm cho action nhạy cảm.

**7. Làm sao giảm push fatigue?**  
Giới hạn challenge, hiển thị context/number matching, cho phép deny/report và theo dõi prompt bất thường.

**8. Vì sao cần đo false positive?**  
Vì policy quá nhạy có thể khóa người dùng hợp lệ, làm tăng support burden và loại trừ nhóm dùng thiết bị hoặc công nghệ hỗ trợ khác nhau.

**9. Progressive security có thay thế authorization không?**  
Không. Step-up chứng minh assurance; authorization vẫn quyết định principal có quyền thực hiện action trên resource hay không.

**10. Sau khi thêm authenticator mới cần làm gì?**  
Ghi audit event, thông báo qua kênh đã xác minh, cho phép review/revoke, kiểm tra recovery path và xử lý session/credential cũ theo policy.

**Ghi nhớ:** Progressive security cân bằng assurance và trải nghiệm bằng cách tăng xác minh đúng lúc, đúng action và đúng mức rủi ro. Hãy phân loại hành động, đánh giá tín hiệu có nguồn tin cậy, yêu cầu freshness/assurance rõ ràng, ưu tiên chống phishing, bind challenge với transaction, bảo vệ privacy và cung cấp recovery/accessibility path. Risk score không phải danh tính, step-up không phải authorization và mọi fallback phải giữ mức bảo vệ tối thiểu đã được policy phê duyệt.
