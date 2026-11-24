# Recovery usability — Thiết kế trải nghiệm khôi phục tài khoản dễ dùng và an toàn
 
> **Chương:** Trải nghiệm người dùng  
> **Chủ đề:** Recovery usability

**Recovery usability** là khả năng giúp người dùng khôi phục quyền truy cập vào tài khoản một cách dễ hiểu, có thể hoàn tất, dễ tiếp cận và an toàn khi họ mất thiết bị, quên password, không còn dùng được authenticator hoặc không thể truy cập recovery channel. Một recovery flow tốt giúp người dùng hiểu mình cần làm gì, biết điều gì sẽ xảy ra tiếp theo và hoàn tất đúng quy trình mà không phải đoán, liên hệ hỗ trợ nhiều lần hoặc vô tình làm giảm bảo mật tài khoản.

Khôi phục tài khoản là một trong những trải nghiệm nhạy cảm nhất của sản phẩm. Người dùng thường thực hiện khi đang căng thẳng, mất thiết bị, đổi số điện thoại, chuyển công việc hoặc không còn truy cập email cũ. Nếu giao diện khó hiểu, họ có thể chọn sai account, gửi nhiều yêu cầu, chia sẻ recovery code với người giả danh support hoặc tạo một authenticator mới trên thiết bị của attacker. Nếu flow quá dễ dãi, recovery trở thành đường vòng yếu hơn login bình thường. Vì vậy, usability và security phải được thiết kế cùng nhau.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối credential, password, MFA, passkey, certificate, token, session, identity linking và account recovery. Người học sẽ thiết kế trải nghiệm recovery theo trạng thái và mức rủi ro, giải thích rõ các bước xác minh, hỗ trợ nhiều thiết bị và phương thức, bảo vệ người dùng khỏi phishing/social engineering, đáp ứng accessibility và đo lường cả tỷ lệ hoàn tất lẫn chất lượng bảo mật.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích recovery usability và phân biệt usability với việc giảm mức bảo đảm xác thực.
2. Mô hình hóa hành trình người dùng từ lúc mất quyền truy cập đến khi account được khôi phục.
3. Thiết kế nội dung, trạng thái, điều hướng và thông báo cho từng loại recovery.
4. Giúp người dùng chọn đúng account và phương thức đã đăng ký mà không tiết lộ thông tin nhạy cảm.
5. Thiết kế trải nghiệm cho password reset, MFA recovery, passkey replacement và certificate renewal.
6. Giải thích TTL, one-time code, cooldown, approval và session revocation bằng ngôn ngữ dễ hiểu.
7. Hỗ trợ người dùng đa thiết bị, đa tenant, người khuyết tật và người có kết nối mạng hạn chế.
8. Ngăn recovery flow bị lợi dụng qua enumeration, phishing, social engineering và helpdesk abuse.
9. Xây dựng thông báo, hướng dẫn self-service và escalation tới support an toàn.
10. Đo completion, abandonment, recovery time, false rejection, support contact và security outcome.

## 2. Recovery usability là gì?

Recovery usability là mức độ người dùng có thể hoàn thành quy trình khôi phục đúng mục đích với nỗ lực hợp lý, hiểu được yêu cầu và không mắc lỗi có thể tránh. Nó gồm nhiều yếu tố:

- **Discoverability:** người dùng tìm thấy đường khôi phục khi login thất bại;
- **Comprehension:** hiểu mình đang xác minh điều gì và vì sao;
- **Learnability:** có thể làm theo hướng dẫn mà không cần biết thuật ngữ bảo mật;
- **Efficiency:** không phải lặp lại bước hoặc nhập thông tin không cần thiết;
- **Accessibility:** dùng được với công nghệ hỗ trợ và nhiều khả năng khác nhau;
- **Error recovery:** hiểu cách xử lý khi mã sai, hết hạn hoặc thiết bị không có sẵn;
- **Trust:** nhận biết trang và thông báo là chính thức;
- **Security:** không bị dẫn vào đường tắt làm mất bảo vệ tài khoản.

### 2.1. Usability không có nghĩa là bỏ bước xác minh

Một flow có ít bước nhưng cho phép bất kỳ ai biết email cũng đổi password thì không phải trải nghiệm tốt. Nó chuyển rủi ro sang người dùng và tổ chức. Mục tiêu là làm các bước cần thiết rõ ràng, dễ thực hiện và tương xứng với rủi ro.

### 2.2. Recovery là một hành trình, không chỉ một form

Người dùng cần biết:
1. Bắt đầu recovery ở đâu;
2. Hệ thống cần xác minh điều gì;
3. Phương thức nào có thể sử dụng;
4. Nếu không còn phương thức đó thì làm gì;
5. Khi nào có kết quả;
6. Điều gì thay đổi sau khi khôi phục;
7. Cách báo cáo nếu họ không yêu cầu recovery.

## 3. Các tình huống người dùng cần recovery

Không nên giả định mọi người dùng đều gặp cùng một vấn đề.

| Tình huống | Nhu cầu người dùng | UX cần hỗ trợ |
| --- | --- | --- |
| Quên password | Đặt lại password | Hướng dẫn ngắn, xác minh an toàn |
| Mất điện thoại | Không dùng được TOTP/push/passkey trên thiết bị | Chọn authenticator dự phòng |
| Mất security key | Không còn thiết bị chính | Dùng key dự phòng hoặc quy trình recovery |
| Đổi số điện thoại | Không nhận được SMS | Xác minh bằng factor khác trước khi thay số |
| Mất email cũ | Không truy cập recovery inbox | Recovery có proofing và hỗ trợ |
| Thiết bị hỏng | Mất platform authenticator | Dùng thiết bị hoặc key khác |
| Passkey không đồng bộ | Không tìm thấy credential trên thiết bị mới | Giải thích lựa chọn passkey khác |
| Tài khoản bị khóa | Không thể login do policy | Giải thích bước xử lý và support path |
| Account bị nghi compromise | Người dùng cần lấy lại quyền kiểm soát | Recovery an toàn, revoke session/credential |
| Chuyển tổ chức/tenant | Không còn quyền ở tenant cũ | Phân biệt account identity và membership |
| Certificate hết hạn | Workload/device không xác thực được | Quy trình renewal/rotation |
| IdP/SSO outage | Không thể đăng nhập qua federation | Thông báo outage và phương án được phê duyệt |

### 3.1. Phân biệt vấn đề của người dùng và outage

Nếu identity provider đang ngừng hoạt động, không nên hướng người dùng đi qua password reset như thể họ quên password. Thông báo cần nói rõ hệ thống đang gặp gián đoạn, trạng thái account không bị thay đổi và khi nào nên thử lại nếu có thông tin đáng tin cậy.

### 3.2. Không buộc người dùng tự chẩn đoán

Tránh thông báo kiểu “authentication context invalid” hoặc “credential binding failure”. Hãy mô tả việc người dùng có thể làm tiếp theo: thử thiết bị đã đăng ký, dùng security key dự phòng hoặc liên hệ support chính thức.

## 4. Nguyên tắc thiết kế trải nghiệm recovery

### 4.1. Rõ ràng trước khi yêu cầu hành động

Nói ngắn gọn mục đích của bước xác minh, dữ liệu nào sẽ được dùng và điều gì sẽ xảy ra sau đó. Không yêu cầu người dùng nhập mã hoặc quét giấy tờ mà không giải thích lý do.

### 4.2. Một bước, một mục đích

Mỗi màn hình nên có một nhiệm vụ chính: xác định account, chọn phương thức, nhập code, xác minh identity, tạo credential mới hoặc hoàn tất. Tránh trộn nhiều quyết định nhạy cảm trên một màn hình.

### 4.3. Giữ ngữ cảnh

Cho biết người dùng đang khôi phục loại account nào ở mức an toàn, phương thức đã chọn và tiến trình hiện tại. Không hiển thị toàn bộ email, số điện thoại hoặc thông tin account trước khi được xác minh.

### 4.4. Có đường quay lại an toàn

Người dùng cần sửa lựa chọn sai hoặc chọn phương thức khác. Tuy nhiên, nút quay lại không được làm token cũ có thể dùng lại, bỏ qua cooldown hoặc thay đổi subject của transaction đang mở.

### 4.5. Tránh ép buộc và tạo áp lực

Không dùng countdown gây hoảng sợ hoặc ngôn ngữ đe dọa. Nếu có thời gian chờ vì lý do bảo mật, giải thích mục đích, thời gian dự kiến và cách nhận thông báo.

### 4.6. Không hứa điều hệ thống không đảm bảo

Không nói “tài khoản đã an toàn” chỉ vì password vừa được reset. Hãy mô tả chính xác: password đã đổi, session cũ đang được thu hồi hoặc một số thiết bị có thể cần đăng nhập lại.

## 5. Recovery journey và state model

Một recovery flow có thể dùng state machine để mọi trạng thái hiển thị tương ứng với trạng thái server.

~~~mermaid
stateDiagram-v2
    [*] --> Start
    Start --> IdentifierSubmitted
    IdentifierSubmitted --> MethodSelection
    MethodSelection --> ProofPending
    ProofPending --> ProofVerified
    ProofPending --> RetryOrHelp
    ProofVerified --> ApprovalOrCooldown
    ApprovalOrCooldown --> CredentialReplacement
    CredentialReplacement --> SessionReview
    SessionReview --> Completed
    RetryOrHelp --> ProofPending
    RetryOrHelp --> SupportReview
    SupportReview --> CredentialReplacement
    Completed --> [*]
~~~

Các trạng thái có thể gồm:
- Start;
- Identifier submitted;
- Request accepted;
- Method selected;
- Proof pending;
- Proof verified;
- Approval pending;
- Cooldown;
- Credential replacement;
- Session review;
- Completed;
- Expired/cancelled;
- Support review;
- Denied.

### 5.1. UI phải phản ánh state server

Không để frontend tự đánh dấu completed khi chỉ mới gửi request. Mỗi bước phải nhận kết quả từ server và xử lý retry/idempotency. Khi reload hoặc đổi thiết bị, người dùng cần khôi phục được tiến trình bằng transaction handle an toàn, không phải token bí mật trong URL dễ bị lộ.

### 5.2. Trạng thái không tiết lộ account existence

Public response của account tồn tại và không tồn tại có thể cần giống nhau. UI có thể nói: “Nếu thông tin này khớp với tài khoản, chúng tôi sẽ gửi hướng dẫn tới kênh đã đăng ký.” Trạng thái chi tiết chỉ được cung cấp sau khi xác minh đủ mức.

## 6. Bắt đầu recovery và chọn đúng account

### 6.1. Identifier input

Cho biết người dùng có thể nhập email, username hoặc mã tổ chức nào. Chuẩn hóa khoảng trắng và định dạng ở server. Hỗ trợ paste và password manager; không tự sửa dữ liệu theo cách thay đổi ý nghĩa.

### 6.2. Multi-account

Một người có thể có account cá nhân và account công việc, hoặc thuộc nhiều tenant. UX cần giúp họ chọn đúng ngữ cảnh bằng thông tin đã được phép hiển thị, ví dụ tên tổ chức công khai hoặc logo tenant, nhưng không tiết lộ membership riêng tư.

### 6.3. Masked destination

Sau khi xác minh phù hợp, có thể hiển thị gợi ý như email đã che một phần hoặc số điện thoại kết thúc bằng vài chữ số. Không hiển thị gợi ý quá chi tiết cho caller chưa xác thực vì nó tạo account enumeration.

### 6.4. Account không tìm thấy

Dùng nội dung trung lập và đưa ra hướng dẫn có ích:
- Kiểm tra lỗi chính tả;
- Thử identifier khác đã dùng để đăng ký;
- Kiểm tra domain tổ chức nếu dùng SSO;
- Liên hệ support qua website/app chính thức.

Không khẳng định account không tồn tại nếu privacy policy yêu cầu che trạng thái.

## 7. Lựa chọn phương thức recovery

Hiển thị các phương thức người dùng thực sự đã đăng ký và được policy cho phép. Không gợi ý một factor chưa được xác minh như thể nó thuộc account.

### 7.1. Thứ tự lựa chọn

Có thể ưu tiên:
1. Passkey/security key khác đã đăng ký;
2. Authenticator dự phòng độc lập;
3. Recovery code;
4. Factor khác phù hợp với assurance policy;
5. Identity proofing hoặc support có kiểm soát.

Thứ tự chính xác phụ thuộc risk và account class. Admin có thể chỉ được phép dùng phishing-resistant authenticator dự phòng hoặc quy trình break-glass đã phê duyệt.

### 7.2. Giải thích ưu/nhược điểm

Không yêu cầu người dùng hiểu thuật ngữ factor. Có thể nói:
- “Dùng khóa bảo mật dự phòng đã đăng ký”;
- “Dùng ứng dụng xác thực trên thiết bị khác”;
- “Nhập một mã khôi phục bạn đã lưu trước đây”.

Tránh mô tả SMS/email OTP là bảo vệ chống phishing. Không làm người dùng nghĩ mọi phương thức đều an toàn tương đương.

### 7.3. Không có phương thức khả dụng

Cung cấp next step rõ ràng: quy trình identity proofing, thời gian xử lý dự kiến, tài liệu cần chuẩn bị nếu có và kênh support chính thức. Không yêu cầu người dùng gửi password, OTP hoặc recovery code cho nhân viên.

## 8. Password reset usability

### 8.1. Form password mới

- Hiển thị rõ yêu cầu password trước khi nhập;
- Cho phép paste và password manager;
- Có nút show/hide password;
- Dùng autocomplete phù hợp;
- Báo lỗi cụ thể về yêu cầu chưa đạt, không tiết lộ chính sách bí mật;
- Không ép thay password nhiều lần vô ích;
- Không xóa nội dung đã nhập khi lỗi không liên quan;
- Không ghi password vào analytics hoặc telemetry.

### 8.2. Password policy dễ hiểu

Nếu hệ thống có yêu cầu độ dài tối thiểu, hiển thị trước khi submit. Tránh yêu cầu tổ hợp ký tự khó nhớ nếu policy không cần. Dùng breached-password screening và kiểm tra phía server; không dựa chỉ vào indicator “strength meter” phía client.

### 8.3. Sau khi reset

Thông báo rõ:
- Password đã được thay đổi;
- Có cần đăng nhập lại trên thiết bị khác không;
- Session cũ có thể bị kết thúc;
- MFA/passkey có còn được giữ hay cần kiểm tra;
- Cách báo cáo nếu người dùng không yêu cầu reset.

Không tự động đăng nhập người dùng vào session có assurance cao hơn proof vừa thực hiện.

## 9. Passkey và security key recovery usability

Passkey có thể được đồng bộ giữa thiết bị hoặc gắn với thiết bị/security key cụ thể. UX cần giúp người dùng hiểu sự khác biệt đủ để chọn đúng.

### 9.1. Mất một thiết bị

Nếu người dùng còn thiết bị khác có passkey, hướng dẫn thử thiết bị đó. Nếu dùng security key dự phòng, giải thích cách kết nối USB/NFC/Bluetooth tùy nền tảng mà không yêu cầu cài phần mềm không cần thiết.

### 9.2. Không tìm thấy passkey

Thông báo nên tránh khẳng định passkey đã bị xóa. Có thể credential đang nằm trong profile trình duyệt, tài khoản sync khác hoặc thiết bị khác. Đưa ra các bước kiểm tra:
- Đúng browser/profile;
- Đúng account đồng bộ;
- Thiết bị có hỗ trợ passkey;
- Bluetooth/nearby device nếu flow cross-device yêu cầu;
- Security key dự phòng.

### 9.3. Thêm passkey mới

Chỉ sau khi recovery proof đạt policy. Màn hình nên:
- Giải thích passkey sẽ được dùng để đăng nhập;
- Yêu cầu đặt tên thiết bị dễ nhận biết;
- Cho biết có thể quản lý/gỡ credential ở đâu;
- Thông báo khi enrollment hoàn tất;
- Hướng dẫn lưu phương thức dự phòng.

### 9.4. Thu hồi passkey đã mất

Giải thích rằng hệ thống có thể vô hiệu hóa credential phía server, nhưng không nhất thiết xóa private key khỏi thiết bị đã mất. Người dùng cần biết credential đó sẽ không còn được chấp nhận cho account và cần xem xét bảo mật account đồng bộ nếu passkey được sync.

## 10. MFA recovery usability

### 10.1. TOTP

Hướng dẫn kiểm tra đúng account trong authenticator app, đồng hồ thiết bị và mã hiện tại. Không yêu cầu người dùng gửi ảnh QR/secret cho support. Nếu mã hết hạn, cho biết cần dùng mã mới và tránh đếm sai nhiều lần do người dùng bấm submit liên tục.

### 10.2. Push MFA

Nói rõ challenge nào đang được yêu cầu và khuyến khích từ chối nếu người dùng không khởi tạo login. Nếu có number matching, trình bày mã trên màn hình login và yêu cầu chọn đúng số trên thiết bị. Không gửi prompt lặp không giới hạn.

### 10.3. Recovery code

- Giải thích đây là mã dùng một lần;
- Cho phép paste và nhập có/không có dấu phân cách theo format;
- Không tự lưu mã vào clipboard hoặc telemetry;
- Cảnh báo không chia sẻ với support;
- Cho biết code đã dùng không thể dùng lại;
- Sau recovery, hướng dẫn tạo bộ code mới nếu policy yêu cầu.

### 10.4. Thay factor

Trước khi gỡ factor cũ, người dùng cần hiểu factor mới đã được kiểm tra và account sẽ còn phương thức truy cập nào. Không cho xóa factor cuối cùng trước khi một phương thức thay thế hợp lệ được xác minh, trừ quy trình recovery được kiểm soát.

## 11. Recovery cho certificate và smart card

Certificate thường được quản lý bởi tổ chức hoặc PKI, vì vậy trải nghiệm có thể khác password reset.

Người dùng cần biết:
- Certificate nào hết hạn hoặc không còn được chấp nhận;
- Thiết bị/card nào cần thao tác;
- Có cần liên hệ IT/PKI administrator không;
- Có thể tiếp tục công việc nào trong lúc chờ;
- Certificate mới được cấp và cài đặt ở đâu;
- Certificate cũ bị revoke khi nào.

Không hướng người dùng bỏ qua certificate warning hoặc cài CA không rõ nguồn. Với smart card, hướng dẫn phải hỗ trợ người dùng kiểm tra reader, middleware và PIN lockout mà không tiết lộ PIN.

## 12. Recovery cho SSO và tài khoản liên kết

Người dùng SSO có thể không có password cục bộ trong ứng dụng. UX cần hướng họ tới IdP đúng và phân biệt lỗi ứng dụng với lỗi danh tính tổ chức.

### 12.1. SSO discovery

Nếu domain dùng SSO, nói rõ người dùng cần đăng nhập qua identity provider của tổ chức. Không hiển thị issuer hoặc tenant riêng tư cho người không được phép biết.

### 12.2. Account linking

Nếu external identity đã liên kết với account khác, không hướng dẫn người dùng tạo account mới rồi merge tự động. Cần xác minh quyền kiểm soát cả hai identity và chuyển sang support flow nếu mapping có xung đột.

### 12.3. Khi IdP outage

Thông báo trạng thái dịch vụ nếu đã được xác nhận. Tránh yêu cầu reset password cục bộ khi account được quản lý hoàn toàn bởi IdP. Cho biết dữ liệu và account không bị xóa chỉ vì IdP tạm thời không khả dụng.

## 13. Recovery cho nhiều tenant và nhiều vai trò

Một principal có thể là học viên ở tenant A và giảng viên ở tenant B. Recovery cần khôi phục danh tính gốc và giữ đúng membership/role.

### 13.1. Tách account identity và tenant membership

Không yêu cầu người dùng tạo account mới cho mỗi tenant nếu kiến trúc hỗ trợ một principal nhiều membership. Sau recovery, tenant membership vẫn phải được kiểm tra theo trạng thái hiện tại.

### 13.2. Hướng dẫn chọn tổ chức

Nếu người dùng chọn tenant, chỉ hiển thị lựa chọn mà policy cho phép. Không dùng tenant selector làm bằng chứng identity. Khi không tìm thấy tenant, hướng dẫn kiểm tra organization slug hoặc liên hệ admin chính thức.

### 13.3. Support có scope

Support tenant A không được xem recovery detail của tenant B nếu không có quyền. UI support cần hiển thị tenant context rõ ràng, purpose và approval state để tránh reset nhầm người.

## 14. Error handling và hướng dẫn tiếp tục

Một thông báo lỗi hữu ích trả lời ba câu hỏi: điều gì vừa xảy ra, người dùng có thể làm gì tiếp theo và có ảnh hưởng gì tới account không.

| Tình huống | Nội dung UX gợi ý |
| --- | --- |
| Mã sai | “Mã này chưa đúng. Kiểm tra và thử lại bằng mã mới nhất.” |
| Mã hết hạn | “Mã đã hết hạn. Yêu cầu mã mới để tiếp tục.” |
| Mã đã dùng | “Mã này đã được sử dụng. Nếu bạn không thực hiện thao tác đó, hãy liên hệ support chính thức.” |
| Gửi yêu cầu quá nhanh | “Bạn đã gửi nhiều yêu cầu. Chờ một lúc rồi thử lại.” |
| Provider outage | “Dịch vụ xác minh đang tạm thời gián đoạn. Thử lại sau hoặc xem trạng thái dịch vụ.” |
| Không có factor phù hợp | “Không dùng được các phương thức hiện có? Bắt đầu quy trình xác minh hỗ trợ.” |
| Recovery đang chờ | “Yêu cầu đang được xem xét. Chúng tôi sẽ thông báo khi có cập nhật.” |
| Account bị suspend | “Không thể hoàn tất yêu cầu tự phục vụ. Hãy liên hệ kênh hỗ trợ của tổ chức.” |

Các câu trên là ví dụ; response công khai cần tuân thủ account enumeration policy. Không tiết lộ account existence, recovery channel hoặc suspension reason cho caller chưa xác thực.

### 14.1. Preserve progress

Nếu mã hết hạn, không bắt người dùng nhập lại identifier và bắt đầu từ đầu nếu transaction vẫn còn hợp lệ. Nếu transaction hết hạn, giải thích rằng cần bắt đầu yêu cầu mới.

### 14.2. Không đổ lỗi cho người dùng

Tránh “Bạn đã làm sai”. Dùng câu mô tả trạng thái và next step. Hạn chế thuật ngữ nội bộ như nonce, RP ID, assertion, token audience trong giao diện thông thường.

## 15. Notification và xây dựng niềm tin

Recovery notification giúp người dùng nhận biết hành động hợp lệ và phát hiện yêu cầu trái phép.

### 15.1. Nội dung notification

Thông báo nên nêu:
- Loại thay đổi: password reset, passkey added, MFA removed;
- Thời điểm;
- Thiết bị hoặc vị trí gần đúng nếu policy cho phép;
- Hành động người dùng có thể làm nếu không yêu cầu;
- Link tới website/app chính thức được xác minh;
- Cảnh báo không chia sẻ OTP/recovery code.

### 15.2. Không gửi secret trong notification

Không gửi password, OTP hoặc recovery code trong email/chat support. Link recovery cần TTL, one-time use, purpose binding và tránh rò qua analytics/referrer.

### 15.3. Kênh notification

Nếu email chính là kênh bị mất hoặc nghi compromise, không gửi thông báo duy nhất tới đó. Dùng các kênh đã xác minh khác theo policy, chẳng hạn session đang hoạt động, authenticator đã đăng ký hoặc thông báo tới admin/owner.

### 15.4. Chống phishing trong notification

Dùng sender/domain nhất quán, không yêu cầu người dùng trả lời email bằng secret, không yêu cầu gọi số điện thoại không công bố. Link nên dẫn tới domain chính thức; hướng dẫn người dùng tự mở app/site nếu không chắc.

## 16. Helpdesk và assisted recovery usability

Self-service không phải lúc nào cũng đủ. Một số người mất mọi factor hoặc gặp vấn đề accessibility cần support. Assisted recovery phải dễ dùng cho người hợp lệ và khó bị social engineer.

### 16.1. Hướng dẫn support

- Cho biết kênh support chính thức;
- Nêu thông tin cần chuẩn bị nhưng không yêu cầu secret;
- Giải thích thời gian xử lý và trạng thái case;
- Cho phép theo dõi case bằng reference không tiết lộ dữ liệu;
- Hướng dẫn báo cáo nếu không phải người yêu cầu.

### 16.2. Những gì support không được yêu cầu

- Password hiện tại;
- OTP/TOTP;
- Recovery code;
- Private key;
- Toàn bộ session cookie hoặc token;
- Ảnh chụp QR enrollment chứa secret.

### 16.3. Quy trình support

Support cần thấy đúng principal, tenant, case và quyền được cấp. High-risk recovery có thể cần approval/dual control, cooldown và notification. UI phải phân biệt requester, verifier và approver; không cho agent vô tình tự phê duyệt yêu cầu của mình.

### 16.4. Không hứa bỏ qua kiểm soát

Nếu recovery cần review hoặc cooldown, giải thích lý do và thời gian dự kiến. Không hứa “support có thể mở ngay” khi policy không cho phép.

## 17. Accessibility và inclusive recovery

Recovery thường được thực hiện trong hoàn cảnh bất lợi: thiết bị mất, kết nối yếu, người dùng không thể nghe hoặc nhìn rõ, hoặc cần công nghệ hỗ trợ.

### 17.1. Keyboard và screen reader

- Tất cả control có label;
- Focus order hợp lý;
- Error được liên kết với field;
- Trạng thái async được thông báo cho assistive technology;
- Không chỉ dùng màu để biểu thị thành công/thất bại;
- Focus được chuyển tới lỗi đầu tiên phù hợp;
- Có thể hoàn thành bằng keyboard.

### 17.2. Captcha và challenge

Nếu dùng CAPTCHA, cung cấp phương án thay thế có thể tiếp cận. Không đặt CAPTCHA thành rào cản duy nhất cho người khuyết tật. Risk challenge phải có fallback hỗ trợ và không tạo oracle theo account existence.

### 17.3. Mã xác minh

- Hỗ trợ paste và autofill;
- Cho phép đọc mã bằng screen reader;
- Không bắt buộc nhập từng chữ số nếu điều đó làm giảm khả năng tiếp cận;
- Không dùng màu hoặc animation làm tín hiệu duy nhất;
- Cho biết thời gian còn lại bằng text;
- Cho phép yêu cầu mã mới theo rate limit.

### 17.4. Ngôn ngữ đơn giản

Dùng câu ngắn, tránh jargon và giải thích từ viết tắt khi cần. Bản dịch cần giữ nguyên ý nghĩa bảo mật, không dịch “recovery code” thành password hoặc “passkey” thành mã OTP.

## 18. Mobile, cross-device và offline considerations

### 18.1. Mobile

- Hỗ trợ deep link an toàn và app link đã xác minh;
- Không để token recovery lộ trong analytics hoặc crash report;
- Giữ trạng thái khi app chuyển background;
- Không yêu cầu người dùng copy secret giữa các app nếu có cách an toàn hơn;
- Xử lý app bị đóng hoặc network timeout bằng transaction state.

### 18.2. Cross-device passkey

Khi dùng điện thoại để xác thực cho laptop, giải thích rõ thiết bị nào đang yêu cầu và người dùng cần xác nhận đúng website. Không chỉ hiển thị QR mà không nói mục đích. Cross-device flow phải kiểm tra RP/origin và challenge phía server.

### 18.3. Offline

Một số recovery step cần kết nối server để tiêu thụ token hoặc revoke credential. Nếu offline, UI nên nói rõ thao tác chưa hoàn tất và không tuyên bố account đã được khôi phục. Không cache recovery token hoặc secret lâu dài để “hỗ trợ offline”.

### 18.4. Kết nối yếu

Cho biết request đang xử lý, tránh gửi lại nhiều lần và dùng idempotency ở server. Nếu timeout, hướng dẫn kiểm tra trạng thái trước khi tạo recovery request mới.

## 19. Thời gian chờ, cooldown và trạng thái pending

Một số recovery có cooldown nhằm giảm nguy cơ takeover. UX phải giải thích rõ để người dùng không nghĩ hệ thống bị treo.

### 19.1. Cách trình bày cooldown

- Lý do bảo mật ở mức phù hợp;
- Thời điểm có thể tiếp tục;
- Kênh nhận cập nhật;
- Điều gì người dùng nên và không nên làm;
- Cách báo cáo nếu yêu cầu không phải của họ.

Không hiển thị countdown có thể bị dùng để xác định trạng thái account cho caller chưa xác thực.

### 19.2. Không tạo cảm giác bị bỏ rơi

Nếu yêu cầu cần manual review, cung cấp case reference, trạng thái và SLA dự kiến. Nếu SLA thay đổi, gửi update. Tránh yêu cầu người dùng gửi lại giấy tờ hoặc tạo case mới liên tục.

### 19.3. Cancel recovery

Cho phép người dùng hủy yêu cầu chưa hoàn tất khi phù hợp. Hủy phải revoke transaction/token và ghi audit. Không để một link đã hủy vẫn dùng được.

## 20. Privacy và account enumeration trong UX

Một UX tốt không tiết lộ account existence cho người chưa xác minh.

### 20.1. Response chung

Ví dụ: “Nếu thông tin này khớp với tài khoản, chúng tôi sẽ gửi hướng dẫn tới kênh đã đăng ký.” Thông điệp nên nhất quán cho account tồn tại/không tồn tại nếu threat model yêu cầu.

### 20.2. Masking đúng thời điểm

Chỉ hiển thị masked email/phone sau khi user đạt bước xác minh phù hợp. Không hiển thị nhiều chữ số hoặc ký tự đủ để đoán danh tính.

### 20.3. Side channel

UX cần được kiểm tra cùng API: status code, timing, redirect, response shape, CAPTCHA, rate limit và notification side effect. Giao diện chung nhưng API trả field account_exists vẫn là enumeration.

### 20.4. Privacy by design

Không đưa identifier, recovery status, device details hoặc proofing artifact vào analytics event thô. Dùng event code và reference đã giảm thiểu; giới hạn retention và quyền truy cập.

## 21. Content design và microcopy

Microcopy là một phần của security control vì nó định hướng hành vi người dùng.

### 21.1. Cấu trúc thông báo

Một thông báo tốt thường gồm:
1. Trạng thái hiện tại;
2. Hành động tiếp theo;
3. Hệ quả hoặc thời gian cần biết;
4. Kênh trợ giúp chính thức.

Ví dụ:

**Trạng thái:** “Yêu cầu khôi phục đang được xem xét.”

**Tiếp theo:** “Bạn không cần gửi thêm yêu cầu. Chúng tôi sẽ cập nhật qua kênh liên hệ đã xác minh.”

**An toàn:** “Nếu bạn không khởi tạo yêu cầu này, hãy mở ứng dụng chính thức và báo cáo hoạt động đáng ngờ. Không chia sẻ mã xác minh với bất kỳ ai.”

### 21.2. Tránh ngôn ngữ gây hoang mang

Không dùng “Tài khoản của bạn đã bị hack” khi chưa xác nhận. Nói “Chúng tôi phát hiện hoạt động cần xác minh thêm” và cung cấp next step.

### 21.3. Consistency

Tên phương thức, trạng thái và nút hành động phải nhất quán giữa web, mobile, email và helpdesk. Nếu web gọi “security key” nhưng support gọi “USB token” mà không giải thích, người dùng có thể chọn sai.

## 22. Đo lường recovery usability

Không tối ưu một metric duy nhất như completion rate vì có thể làm flow yếu đi để tăng tỷ lệ hoàn tất.

| Metric | Ý nghĩa | Cần diễn giải cùng |
| --- | --- | --- |
| Recovery completion rate | Tỷ lệ flow hợp lệ hoàn tất | Assurance và abuse rate |
| Time to recover | Thời gian từ request tới quyền truy cập trở lại | Loại proof và cooldown |
| Abandonment rate | Tỷ lệ bỏ dở theo bước | Accessibility và lỗi UX |
| Retry rate | Số lần người dùng phải thử lại | Error clarity, provider health |
| Support contact rate | Tỷ lệ cần helpdesk | Self-service quality và risk |
| False rejection rate | Người hợp lệ bị từ chối | Abuse prevention và proofing |
| Recovery abuse rate | Request có dấu hiệu lạm dụng | False positive và population |
| Notification delivery | Tỷ lệ gửi/nhận được xác nhận | Provider reliability |
| Session revocation latency | Thời gian thu hồi session cũ | Security propagation |
| Accessibility task success | Tỷ lệ hoàn tất với assistive technology | Loại công nghệ và task |
| Comprehension score | Người dùng hiểu bước và hậu quả | Ngôn ngữ, nội dung |
| Repeat recovery | Người dùng phải recovery nhiều lần | Credential lifecycle và UX |

### 22.1. Funnel theo bước

Theo dõi:
- Bắt đầu recovery;
- Gửi identifier;
- Chọn phương thức;
- Bắt đầu proof;
- Proof thành công;
- Approval/cooldown;
- Credential replacement;
- Session review;
- Hoàn tất.

Funnel cần event tối thiểu hóa và pseudonymous; không ghi secret hoặc raw identifier vào analytics.

### 22.2. Phân đoạn có kiểm soát

Có thể phân tích theo platform, locale, accessibility mode, recovery method và tenant tier. Tránh phân đoạn nhạy cảm không cần thiết hoặc tạo nhóm nhỏ có thể nhận diện cá nhân.

### 22.3. Guardrail metrics

Theo dõi recovery takeover, account lockout, support override, session còn hiệu lực sau recovery và factor enrollment bất thường. Completion tăng nhưng takeover tăng là kết quả xấu.

## 23. User research và usability testing

### 23.1. Nhiệm vụ kiểm thử

Cho người tham gia thực hiện các nhiệm vụ giả lập:
- Quên password;
- Mất điện thoại có TOTP;
- Dùng security key dự phòng;
- Không nhận được email;
- Không tìm thấy passkey trên thiết bị mới;
- Hủy yêu cầu recovery;
- Nhận thông báo recovery không do mình yêu cầu;
- Liên hệ support qua kênh chính thức.

### 23.2. Quan sát

Ghi nhận:
- Người dùng có tìm được entry point không;
- Có hiểu sự khác nhau giữa password reset và account recovery không;
- Có chọn đúng account/tenant không;
- Có biết code hết hạn và dùng một lần không;
- Có nhận ra hành vi phishing không;
- Có hiểu session cũ sẽ bị xử lý thế nào không;
- Có thể hoàn tất bằng keyboard/screen reader không;
- Có gửi nhiều request do thiếu feedback không.

### 23.3. Không thu thập credential thật

Dùng account giả lập và code không có giá trị. Không yêu cầu người tham gia cung cấp password, OTP, recovery code hoặc giấy tờ thật. Có consent và quy trình xóa dữ liệu nghiên cứu.

### 23.4. Moderated và unmoderated

Moderated testing hữu ích cho flow có nhiều bước hoặc support. Unmoderated test có thể đo completion và comprehension ở quy mô lớn, nhưng không dùng kết quả đó thay security test hoặc accessibility audit.

## 24. Pseudocode chọn recovery journey theo policy

~~~text
start_recovery(identifier, requested_problem, context):
    public_response = generic_recovery_response()

    account = resolve_account_privately(identifier)
    if account is absent:
        record_minimized_nonmatch_event(identifier)
        return public_response

    if not recovery_is_allowed(account, requested_problem):
        record_policy_denial(account)
        return public_response

    policy = load_recovery_policy(
        account_class = account.class,
        action = requested_problem,
        tenant = verified_tenant_context(context)
    )

    methods = registered_methods(account)
    eligible = filter_by_assurance_and_status(methods, policy)

    transaction = create_recovery_transaction(
        subject = account.id,
        purpose = requested_problem,
        allowed_methods = eligible,
        ttl = policy.transaction_ttl
    )

    return render_safe_next_step(
        transaction_reference = transaction.public_reference,
        methods = safe_method_descriptions(eligible),
        help_path = policy.support_path
    )
~~~

Pseudocode minh họa tách response công khai khỏi account lookup nội bộ. Chỉ hiển thị method sau khi đạt mức xác minh mà policy cho phép. Không gửi account ID, raw recovery token hoặc secret trong UI state không an toàn.

## 25. Ví dụ thiết kế: người dùng mất điện thoại

Một học viên dùng passkey trên điện thoại và TOTP trong cùng ứng dụng authenticator. Điện thoại bị mất.

### 25.1. Trải nghiệm không tốt

- Màn hình chỉ hiện “Không thể xác thực”;
- Chỉ có lựa chọn gửi SMS tới số cũ;
- Người dùng không biết có security key dự phòng;
- Support yêu cầu gửi OTP qua chat;
- Sau reset, session trên điện thoại bị mất vẫn hoạt động.

### 25.2. Trải nghiệm tốt hơn

1. Ở login, chọn “Tôi không còn thiết bị này”.
2. Hệ thống hiển thị các phương thức dự phòng đã đăng ký, sau khi xác minh ở mức phù hợp.
3. Người dùng chọn security key dự phòng.
4. Hệ thống xác minh challenge, RP ID/origin và user verification.
5. Người dùng xem danh sách session/thiết bị ở mức thông tin được phép.
6. Người dùng thu hồi thiết bị đã mất và đăng ký passkey mới trên thiết bị hiện tại.
7. Hệ thống thông báo thay đổi qua kênh đã xác minh.
8. Người dùng được hướng dẫn tạo phương thức dự phòng độc lập.
9. Audit ghi credential references, actor, time và policy result; không lưu private key hoặc OTP.

### 25.3. Điều kiện an toàn

Nếu người dùng không có security key hoặc factor hợp lệ, chuyển sang recovery proofing. Không tự động cấp quyền tương đương passkey chỉ bằng email hoặc thông tin cá nhân công khai.

## 26. Những lỗi UX và security thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ có một đường recovery | Người dùng dễ bị lockout | Nhiều phương thức dự phòng độc lập |
| Không phân biệt reset và recovery | Người dùng chọn sai flow | Đặt tên và mô tả rõ |
| Hiển thị recovery channel quá sớm | Account enumeration | Mask sau proof phù hợp |
| OTP được mô tả là chống phishing | Người dùng đánh giá sai rủi ro | Nói rõ giới hạn phương thức |
| Hướng dẫn support gửi code | Social engineering | Cấm chia sẻ secret, xác minh qua portal |
| Mã hết hạn không có next step | Người dùng gửi request lặp | Hướng dẫn lấy mã mới và giữ progress |
| UI báo complete trước backend | Trạng thái sai | Chỉ báo theo server state |
| Không giải thích cooldown | Người dùng nghĩ hệ thống lỗi | Hiển thị thời gian/trạng thái và update |
| Factor cuối bị xóa trước khi thay | Account lockout | Xác minh factor mới trước removal |
| Recovery không revoke session | Attacker giữ quyền | Session/token review và revocation |
| Recovery link lộ qua analytics | Token theft | Redaction, no-referrer và TTL |
| Không hỗ trợ screen reader | Người dùng không thể hoàn tất | Accessible labels, focus và status |
| Không hỗ trợ paste/autofill | Nhập code khó, tăng lỗi | Cho phép paste/autofill an toàn |
| Retry tạo nhiều transaction | Spam và state conflict | Idempotency và rate limit |
| Tenant context không rõ | Recovery nhầm tổ chức | Hiển thị context đã xác minh |
| Thông báo quá kỹ | Lộ trạng thái account | Generic response và private notification |
| Copy gây hoảng sợ | Người dùng làm theo attacker | Ngôn ngữ trung lập, next step rõ |

## 27. Checklist production

1. **Entry point:** Người dùng tìm được recovery từ login và support chính thức?
2. **Journey:** Các state và next step được giải thích rõ?
3. **Account selection:** Hỗ trợ account/tenant khác nhau mà không lộ membership?
4. **Method choice:** Chỉ hiển thị factor đã đăng ký và được policy cho phép?
5. **Assurance:** Fallback/recovery không hạ assurance cho action nhạy cảm?
6. **Password reset:** Password manager, paste, show/hide và error handling hoạt động?
7. **Passkey:** Có hướng dẫn multi-device, synced/device-bound và security key?
8. **MFA:** TOTP, push, recovery code và factor replacement có UX riêng?
9. **Certificate/SSO:** Có hướng dẫn đúng owner/IdP/PKI và không bypass validation?
10. **Token:** TTL, purpose, one-time use và transaction state được phản ánh chính xác?
11. **Session:** Người dùng hiểu session cũ được revoke/đăng nhập lại?
12. **Notification:** Có thông báo thay đổi và đường báo cáo không phải mình?
13. **Support:** Kênh chính thức, case state, proofing và approval rõ?
14. **Accessibility:** Keyboard, screen reader, contrast, focus và CAPTCHA alternative?
15. **Mobile:** Deep link, background/resume, offline và network retry an toàn?
16. **Privacy:** Response chung, masked destination đúng thời điểm và analytics tối thiểu?
17. **Abuse:** Rate limit, replay, enumeration và helpdesk social engineering được kiểm soát?
18. **Comprehension:** Người dùng hiểu code dùng một lần, expiry và không chia sẻ secret?
19. **Metrics:** Completion, abandonment, false rejection, abuse và session revoke latency được đo?
20. **Research:** Có usability test với account giả lập và assistive technology?
21. **Recovery state:** UI không báo complete khi backend chưa commit?
22. **Governance:** Copy, support script và policy được review khi thay đổi?

## 28. Bài tập tình huống

Một nền tảng học tập yêu cầu passkey cho giảng viên. Khi giảng viên đổi điện thoại, login chỉ hiển thị lỗi “Credential not found”. Trang recovery cho phép gửi OTP tới email nhưng không nói đây là phương thức yếu hơn. Nếu OTP thành công, hệ thống lập tức thêm passkey mới và giữ tất cả session cũ. Helpdesk yêu cầu người dùng đọc OTP qua điện thoại để xác minh. Giao diện không hỗ trợ screen reader và không có trạng thái cho recovery đang chờ phê duyệt.

**Yêu cầu:**

1. Xác định ít nhất **tám vấn đề** về usability, accessibility và security.
2. Thiết kế lại recovery journey cho người đổi điện thoại nhưng còn security key dự phòng.
3. Thiết kế nhánh khi người dùng mất mọi authenticator và cần assisted recovery.
4. Viết microcopy cho mã sai, mã hết hạn, cooldown và yêu cầu không do người dùng khởi tạo.
5. Xác định lúc nào có thể hiển thị masked recovery destination.
6. Đề xuất cách xử lý session cũ và credential trên thiết bị bị mất.
7. Thiết kế test với keyboard, screen reader, mobile app và kết nối mạng yếu.
8. Chọn metric usability và security guardrail để đánh giá sau triển khai.

**Gợi ý đối chiếu:** Hiển thị next step rõ; ưu tiên security key đã đăng ký; email OTP không tương đương passkey; helpdesk không yêu cầu đọc code; proofing/approval cho recovery; revoke session/credential cũ; hỗ trợ accessibility; UI chỉ báo hoàn tất theo server state.

## 29. Ghi nhớ

- **Recovery usability** giúp người dùng khôi phục quyền truy cập dễ hiểu, dễ tiếp cận và an toàn.
- Recovery là hành trình nhiều trạng thái; UI phải phản ánh state server và không báo thành công sớm.
- Nhiều phương thức dự phòng độc lập giúp giảm lockout, nhưng chỉ được dùng khi đã đăng ký và đạt policy.
- Password reset, MFA recovery, passkey replacement, certificate renewal và SSO outage cần hướng dẫn riêng.
- Không biến email/SMS OTP hoặc helpdesk thành đường bypass yếu hơn cho account nhạy cảm.
- Giải thích TTL, one-time code, cooldown, approval và session revocation bằng ngôn ngữ rõ ràng.
- Không yêu cầu người dùng chia sẻ password, OTP, recovery code, private key hoặc session token với support.
- Account enumeration, notification phishing và recovery link leakage cần được kiểm soát ở cả UI lẫn API.
- Accessibility, mobile, cross-device, offline và network retry là một phần của recovery design.
- Đo completion cùng abandonment, false rejection, abuse, support contact và session revocation; không tối ưu usability bằng cách giảm assurance.

Recovery usability trưởng thành khi **người dùng luôn biết bước tiếp theo, hiểu vì sao cần xác minh và có thể hoàn tất bằng phương thức phù hợp, trong khi hệ thống vẫn giữ đúng danh tính, assurance, session state và khả năng thu hồi**.
