# Identity re-verification — Xác minh lại danh tính khi khôi phục tài khoản

> **Chương:** Account recovery  
> **Chủ đề:** Identity re-verification  
> **Phạm vi:** Security Authentication Fundamentals — xác minh lại người yêu cầu khôi phục quyền kiểm soát tài khoản, đánh giá bằng chứng và mức tin cậy, chống giả mạo/social engineering, khôi phục credential an toàn và bảo vệ vòng đời tài khoản sau recovery.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt identity re-verification với đăng nhập lại, xác thực đa yếu tố và identity proofing ban đầu.
2. Giải thích vì sao account recovery là một luồng bảo mật có thể trở thành đường vòng yếu nhất của hệ thống.
3. Chọn bằng chứng phù hợp với mức rủi ro và khả năng khôi phục của tài khoản.
4. Đánh giá giới hạn của recovery code, trusted device, email/phone, giấy tờ tùy thân, sinh trắc học và helpdesk.
5. Thiết kế recovery transaction có state, challenge, expiry, approval và audit.
6. Ngăn attacker dùng SIM swap, email compromise, deepfake, giấy tờ giả hoặc social engineering để chiếm tài khoản.
7. Thu hồi credential/session cũ, đăng ký credential mới và áp dụng giới hạn sau recovery.
8. Bảo vệ dữ liệu cá nhân trong quá trình thu thập và lưu bằng chứng xác minh.
9. Xây dựng bộ kiểm thử cho recovery hợp lệ, giả mạo, replay, race condition, hỗ trợ viên nội bộ và khôi phục tài khoản đặc quyền.

## 1. Identity re-verification là gì?

**Identity re-verification** là quá trình xác minh lại người đang yêu cầu khôi phục tài khoản có đủ bằng chứng để được công nhận là chủ thể hợp lệ của tài khoản đó. Quy trình được dùng khi người dùng mất quyền truy cập, mất authenticator, đổi thiết bị, không còn dùng được kênh recovery hoặc khi hệ thống nghi ngờ tài khoản bị chiếm quyền.

Ví dụ: Nhân viên mất điện thoại có passkey và ứng dụng MFA. Người đó yêu cầu đăng ký điện thoại mới. Hệ thống không nên chỉ gửi một liên kết tới địa chỉ email được khai trong yêu cầu rồi cho phép thay toàn bộ yếu tố xác thực. Nó cần xác minh yêu cầu dựa trên những bằng chứng đã được thiết lập trước đó hoặc quy trình recovery có assurance phù hợp, sau đó thu hồi credential cũ và cấp quyền đăng ký credential mới.

Identity re-verification là một phần của **account recovery**. Mục tiêu không chỉ là giúp người dùng vào lại hệ thống, mà là tránh cấp quyền kiểm soát tài khoản cho nhầm người.

### Những câu hỏi cần trả lời

- Người yêu cầu là chủ tài khoản hay người được ủy quyền hợp lệ?
- Bằng chứng đang có được gắn với tài khoản từ trước hay chỉ vừa được khai báo?
- Bằng chứng có thể bị attacker chiếm cùng lúc không?
- Mức tin cậy đạt được có đủ cho loại tài khoản và hành động cần khôi phục không?
- Ai phê duyệt recovery và quyết định được ghi lại như thế nào?
- Credential cũ nào cần thu hồi?
- Sau recovery, hệ thống có cần giới hạn hành động hoặc theo dõi tăng cường không?

## 2. Phân biệt identity re-verification với các khái niệm liên quan

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Authentication** | Chứng minh đang kiểm soát credential của một account | Đăng nhập bằng passkey |
| **Reauthentication** | Xác thực lại account đang có session | Dùng passkey trước thao tác nhạy cảm |
| **Identity proofing** | Thiết lập danh tính ban đầu theo một mức đảm bảo | Xác minh hồ sơ người mới mở tài khoản |
| **Identity re-verification** | Kiểm tra lại bằng chứng về chủ thể khi recovery hoặc rủi ro tăng | Khôi phục account sau khi mất mọi authenticator |
| **Credential recovery** | Khôi phục hoặc thay phương thức xác thực | Thu hồi passkey cũ và đăng ký passkey mới |
| **Account recovery** | Khôi phục quyền kiểm soát và trạng thái truy cập của account | Xác minh chủ tài khoản, thay credential, mở lại account |
| **Authorization** | Quyết định chủ thể được phép làm gì | Chỉ cấp quyền xem hồ sơ cho nhân viên |

Một lần đăng nhập thành công bằng mật khẩu cũ có thể là bằng chứng authentication, nhưng không nhất thiết đủ để xác minh lại danh tính khi attacker đã chiếm mật khẩu. Ngược lại, giấy tờ tùy thân được kiểm tra trong recovery không tự tạo ra session hoặc quyền truy cập; hệ thống vẫn cần hoàn tất quy trình credential và authorization.

## 3. Vì sao account recovery là ranh giới bảo mật quan trọng?

Hệ thống có thể bảo vệ đăng nhập bằng passkey chống phishing, MFA, rate limit và risk engine. Nhưng nếu attacker chỉ cần thuyết phục helpdesk đổi email recovery hoặc gửi mã tới SIM vừa chiếm, các kiểm soát đăng nhập mạnh có thể bị vô hiệu hóa.

Recovery thường có những đặc điểm làm tăng rủi ro:

- Người dùng đang ở trạng thái mất credential nên khó chứng minh quyền sở hữu;
- Họ có thể đang hoảng loạn hoặc chịu áp lực thời gian;
- Attacker có thể chủ động tạo tình huống “mất thiết bị” giả;
- Kênh recovery như email/phone có thể yếu hơn phương thức đăng nhập chính;
- Nhân viên hỗ trợ có quyền ghi đè hoặc reset credential;
- Recovery có thể thay đổi nhiều yếu tố cùng lúc và tạo persistence cho attacker.

**Mức bảo vệ của tài khoản bị giới hạn bởi con đường recovery yếu nhất có thể khai thác.** Vì vậy, recovery cần threat model, assurance, audit và kiểm soát thay đổi riêng.

## 4. Mô hình bằng chứng và mức tin cậy

Không có một loại bằng chứng duy nhất phù hợp cho mọi tình huống. Hệ thống nên đánh giá bằng chứng theo nguồn, thời điểm, tính độc lập, khả năng bị chiếm và mối liên hệ với tài khoản.

### Nhóm bằng chứng thường gặp

| Nhóm | Ví dụ | Giá trị và giới hạn |
| --- | --- | --- |
| **Credential đã đăng ký** | Passkey dự phòng, security key, smart card | Mạnh khi chứng minh được possession và credential đã gắn với account từ trước |
| **Recovery secret đã cấp trước** | Recovery code dùng một lần | Hữu ích khi được tạo/lưu an toàn; có thể bị đánh cắp hoặc lộ qua phishing |
| **Trusted device** | Thiết bị đã enrollment, device-bound key | Hữu ích nếu device proof còn hợp lệ; thiết bị có thể bị mất hoặc compromise |
| **Verified contact channel** | Email/phone đã xác minh trước | Hỗ trợ thông báo hoặc một phần quy trình; có thể bị chiếm, SIM swap hoặc chuyển tiếp |
| **Enterprise identity source** | IdP doanh nghiệp, HR directory, quản trị viên tenant | Có thể đáng tin nếu nguồn và quy trình phê duyệt được bảo vệ |
| **Identity document** | Hộ chiếu, giấy tờ do cơ quan có thẩm quyền cấp | Cần kiểm tra tính xác thực, chủ thể, hiệu lực và mức phù hợp; giấy tờ có thể bị giả hoặc đánh cắp |
| **Biometric/liveness** | So khớp khuôn mặt và kiểm tra hiện diện | Có thể hỗ trợ quy trình; có false match, false reject, deepfake và rủi ro dữ liệu sinh trắc |
| **Helpdesk/knowledge** | Nhân viên hỗ trợ, thông tin lịch sử | Dễ bị social engineering; không nên dựa vào dữ liệu công khai hoặc câu hỏi bí mật yếu |
| **Contextual signals** | Thiết bị quen, lịch sử đăng nhập, network | Chỉ là tín hiệu hỗ trợ; không tự chứng minh danh tính |

### Đánh giá bằng chứng theo nhiều chiều

Mỗi bằng chứng cần được xem xét:

- **Binding:** có được liên kết với account trước khi xảy ra recovery không?
- **Control:** người yêu cầu có chứng minh đang kiểm soát bằng chứng không?
- **Authenticity:** nguồn/bằng chứng có thể bị làm giả hoặc chỉnh sửa không?
- **Independence:** có độc lập với những kênh khác có thể cùng bị chiếm không?
- **Freshness:** bằng chứng có đủ mới cho quyết định hiện tại không?
- **Revocation:** có thể biết bằng chứng đã mất, bị thu hồi hoặc bị thay thế chưa?
- **Privacy:** việc thu thập có cần thiết và tương xứng không?

Hai bằng chứng cùng phụ thuộc một email đã bị chiếm không tạo thành hai yếu tố độc lập. Việc cộng số lượng bằng chứng mà không xét quan hệ phụ thuộc có thể tạo cảm giác assurance cao giả tạo.

## 5. Phân loại recovery theo mức rủi ro

Policy nên phân loại tài khoản và thao tác trước khi chọn quy trình xác minh.

| Tình huống | Rủi ro minh họa | Hướng xử lý |
| --- | --- | --- |
| Còn một passkey khác đã đăng ký | Thấp đến trung bình | Dùng credential còn hoạt động, xác minh rồi thêm credential mới |
| Mất một thiết bị nhưng còn trusted device khác | Trung bình | Device proof + reauthentication/step-up phù hợp |
| Mất MFA nhưng còn password và passkey | Trung bình | Xác thực bằng credential độc lập còn lại; xem xét risk và thông báo |
| Mất toàn bộ authenticator | Cao | Recovery ceremony với bằng chứng độc lập, có thể cần identity re-proofing |
| Email/phone recovery cũng bị mất | Cao | Không dựa vào kênh vừa khai báo; dùng bằng chứng dự phòng hoặc quy trình hỗ trợ có kiểm soát |
| Account đặc quyền/administrator | Rất cao | Phê duyệt độc lập, dual control, kiểm tra nguồn nhân sự/tổ chức |
| Tài khoản tài chính hoặc có dữ liệu nhạy cảm lớn | Cao/critical | Assurance cao, cooldown/notification và giới hạn sau recovery |
| Có dấu hiệu account takeover | Critical | Tạm khóa recovery tự phục vụ, điều tra và xử lý theo incident response |

Các mức trên chỉ là ví dụ. Hệ thống cần xác định risk dựa trên tài sản, hậu quả, quyền của account, bằng chứng còn lại và tín hiệu compromise.

## 6. Ưu tiên bằng chứng đã đăng ký trước

Khi có thể, recovery nên bắt đầu bằng bằng chứng đã gắn với account trước sự cố:

1. Passkey hoặc security key dự phòng;
2. Recovery code được cấp trước và còn hiệu lực;
3. Trusted device có device-bound credential;
4. IdP doanh nghiệp hoặc nguồn danh tính đã được tổ chức quản lý;
5. Kênh liên lạc đã xác minh trước, dùng như một tín hiệu hoặc kênh thông báo;
6. Identity proofing/helpdesk có assurance cao khi các lựa chọn trên không còn.

Bằng chứng mới được khai báo sau khi người dùng mất quyền truy cập cần được xem là chưa tin cậy cho tới khi được xác minh. Email mới vừa được nhập trong recovery request không thể tự chứng minh người nhập là chủ tài khoản.

### Recovery code

Recovery code thường là secret dùng một lần, được tạo và cấp cho người dùng từ trước.

Kiểm soát:

- Sinh bằng nguồn ngẫu nhiên mật mã;
- Hiển thị một lần khi tạo và hướng dẫn lưu ở nơi an toàn;
- Lưu verifier/hash phù hợp phía server, không lưu plaintext;
- Chỉ chấp nhận một lần và tiêu thụ atomically;
- Có rate limit và chống dò;
- Cho phép thu hồi/tạo bộ mới sau khi recovery;
- Thông báo khi code được dùng hoặc bộ code bị thay.

Recovery code bị chụp ảnh, lưu trong email hoặc đồng bộ vào nơi không an toàn có thể bị attacker lấy. Người dùng nên có nhiều phương thức dự phòng độc lập, nhưng không nên tạo quá nhiều bản sao không kiểm soát.

## 7. Email, phone và trusted contact

Email hoặc số điện thoại đã xác minh có thể hỗ trợ recovery nhưng thường không nên là bằng chứng duy nhất cho account có giá trị cao.

### Rủi ro của email

- Hộp thư có thể bị chiếm bằng password reuse hoặc recovery yếu;
- Email forwarding rule có thể âm thầm chuyển thư;
- Attacker có thể kiểm soát domain hoặc tài khoản quản trị email;
- Link recovery có thể bị chuyển tiếp, đánh cắp hoặc mở trên thiết bị khác.

### Rủi ro của phone/SMS

- SIM swap hoặc port-out;
- Social engineering với nhà mạng;
- SMS forwarding hoặc malware đọc tin nhắn;
- Mã OTP bị phishing/relay trong thời gian hiệu lực;
- Số điện thoại được tái cấp cho người khác.

### Trusted contact

Trusted contact có thể hỗ trợ xác nhận một số tình huống, nhưng quan hệ cá nhân không tự tạo bằng chứng mật mã. Cần xác minh người liên hệ, phạm vi họ được phép xác nhận, chống collusion và audit. Không để một trusted contact đơn phương đổi email, passkey hoặc quyền quản trị của chủ tài khoản.

### Cách dùng hợp lý

- Dùng kênh đã đăng ký trước để gửi cảnh báo và thông báo;
- Không gửi secret recovery dài hạn qua email/SMS;
- Link recovery phải có entropy cao, expiry ngắn và single-use;
- Gắn link với đúng account, transaction và purpose;
- Không cho link tự thay đổi mọi factor nếu chưa hoàn tất assurance cần thiết;
- Khi kênh liên lạc vừa bị đổi, không dùng ngay kênh mới làm bằng chứng xác minh chính.

## 8. Giấy tờ tùy thân và identity proofing từ xa

Khi người dùng mất mọi credential và hệ thống cần khôi phục account có giá trị cao, có thể cần identity proofing bổ sung. Quy trình có thể yêu cầu giấy tờ do nguồn có thẩm quyền cấp, đối chiếu thông tin hoặc kiểm tra trực tiếp.

### Những gì cần kiểm tra

- Loại giấy tờ có được chấp nhận cho mục đích và khu vực pháp lý này không;
- Giấy tờ còn hiệu lực và không có dấu hiệu chỉnh sửa;
- Ảnh/chip/dữ liệu xác thực có thể kiểm tra theo khả năng của hệ thống;
- Thông tin trên giấy tờ có khớp hồ sơ đã được xác minh trước đó không;
- Người xuất trình có phải chủ thể được ghi trên giấy tờ không;
- Có dấu hiệu ảnh chụp lại, deepfake, replay hoặc giả mạo phiên video không;
- Quy trình có reviewer/kiểm tra độc lập khi cần không.

### Giới hạn

Giấy tờ hợp lệ không tự chứng minh người đang gửi ảnh là chủ sở hữu. Ảnh giấy tờ có thể bị đánh cắp hoặc tái sử dụng. Một số dữ liệu trên giấy tờ có thể đã cũ, không cập nhật hoặc không phù hợp với account. Hệ thống không nên kết luận danh tính chỉ từ việc OCR đọc được tên và số giấy tờ.

### Data minimization

Chỉ thu thập trường dữ liệu cần thiết. Nếu chỉ cần xác nhận một thuộc tính, không nhất thiết giữ bản sao đầy đủ giấy tờ. Xác định mục đích, căn cứ thu thập, dữ liệu nào cần lưu, thời hạn lưu, ai được truy cập, mã hóa và cách xóa an toàn.

Không yêu cầu người dùng gửi giấy tờ qua kênh chat/email không bảo vệ. Dùng kênh upload được kiểm soát, giới hạn file và kiểm tra malware.

## 9. Sinh trắc học, liveness và deepfake

Sinh trắc học có thể hỗ trợ so khớp người đang thực hiện recovery với ảnh tham chiếu hoặc dữ liệu đã xác minh. Tuy nhiên, nó có giới hạn kỹ thuật và quyền riêng tư.

### Các khái niệm

- **Face matching:** so sánh khuôn mặt trong ảnh/video với ảnh tham chiếu;
- **Liveness/presentation attack detection:** đánh giá người đang tương tác có hiện diện thật hay là ảnh/video/mặt nạ;
- **Device biometric verification:** thiết bị xác nhận user verification cục bộ, ví dụ mở khóa authenticator;
- **Remote identity verification:** kết hợp giấy tờ, selfie/video, kiểm tra liveness và nguồn dữ liệu khác.

### Không nhầm device UV với identity proofing

WebAuthn user verification có thể cho biết authenticator đã thực hiện bước xác minh người dùng cục bộ theo cơ chế của nó. Nó không cung cấp cho RP dữ liệu sinh trắc học thô và không tự chứng minh danh tính pháp lý của người đó. Trong recovery, cần hiểu chính xác bằng chứng đang được xác minh là gì.

### Rủi ro và kiểm soát

- Ảnh/video deepfake hoặc replay;
- Presentation attack bằng ảnh in, màn hình hoặc mặt nạ;
- False acceptance/false rejection;
- Thiên lệch hiệu năng giữa nhóm người dùng;
- Dữ liệu sinh trắc bị lộ khó thay đổi như mật khẩu;
- Nhà cung cấp xử lý dữ liệu ngoài phạm vi mong muốn.

Dùng kiểm tra liveness và vendor có đánh giá phù hợp khi cần, nhưng kết hợp với nguồn bằng chứng khác, review cho trường hợp không chắc chắn và phương án thay thế tiếp cận được. Không coi một điểm similarity hoặc “liveness passed” là quyết định độc lập cho mọi account.

## 10. Helpdesk và xác minh thủ công

Helpdesk thường là mục tiêu của social engineering vì nhân viên có thể bị thúc ép bởi người tự nhận là lãnh đạo, khách hàng quan trọng hoặc người đang gặp sự cố khẩn cấp.

### Quy trình an toàn

1. Nhân viên tiếp nhận yêu cầu qua ticket/kênh đã xác thực.
2. Tra cứu account và trạng thái từ hệ thống có thẩm quyền.
3. Dùng checklist bằng chứng được policy phê duyệt; không ứng biến câu hỏi bí mật.
4. Với account nhạy cảm, yêu cầu reviewer thứ hai hoặc quản trị viên độc lập.
5. Không cho người yêu cầu tự cung cấp số điện thoại/email mới rồi dùng chính kênh đó để xác minh.
6. Tạo recovery transaction có thời hạn và scope rõ.
7. Ghi actor, reviewer, evidence reference, decision và reason code.
8. Gửi thông báo tới kênh đã có trước đó.
9. Nếu có dấu hiệu social engineering, dừng recovery và chuyển incident response.

### Những việc helpdesk không nên làm

- Yêu cầu người dùng đọc OTP, recovery code hoặc mật khẩu cho nhân viên;
- Gửi mã tạm qua kênh cá nhân của nhân viên;
- Tắt MFA chỉ dựa trên chức danh, áp lực hoặc lời xác nhận qua điện thoại;
- Ghi đè email/phone mà không xác minh độc lập;
- Bỏ qua dual control vì “trường hợp khẩn cấp”;
- Dùng thông tin công khai như ngày sinh, địa chỉ hoặc tên người thân làm bằng chứng mạnh;
- Xóa audit hoặc dùng tài khoản admin chung để reset credential.

### Khẩn cấp không phải ngoại lệ không kiểm soát

Nếu có quy trình emergency recovery, nó cần được định nghĩa trước: ai có quyền kích hoạt, loại account nào áp dụng, bằng chứng tối thiểu, thời hạn, người phê duyệt, phạm vi truy cập tạm và hậu kiểm bắt buộc. Mọi ngoại lệ đều cần audit và cảnh báo.

## 11. Thiết kế recovery transaction

Recovery nên là một transaction server-side có trạng thái, không phải chuỗi URL và cờ client tự điều khiển.

### Thành phần

- Recovery request ID;
- Account/subject reference được server xác định;
- Tenant và loại account;
- Reason code;
- Recovery purpose: thay MFA, mất passkey, mất mọi credential, mở khóa account;
- Evidence references và kết quả xác minh;
- Risk decision và policy version;
- Challenge/nonce, expiry và trạng thái consumed;
- Reviewer/approver nếu cần;
- Credential nào sẽ bị thu hồi hoặc thêm mới;
- Notification và cooldown policy;
- Audit/correlation ID.

### Ví dụ metadata

`````````yaml
recovery_transaction:
  recovery_id: rec-82d1
  subject_ref: usr-ref-7b2a
  tenant_ref: tenant-42
  purpose: lost_authenticator
  status: PENDING_VERIFICATION
  evidence:
    - type: previously_enrolled_passkey
      result: verified
    - type: trusted_device_proof
      result: verified
  risk_policy: account_recovery_high_v2
  created_at: "2026-11-22T06:30:00Z"
  expires_at: "2026-11-22T07:00:00Z"
  approval_required: false
`````````

Đây là ví dụ schema. Không lưu raw biometric, ảnh giấy tờ hoặc recovery secret trong metadata transaction nếu không cần. Chỉ lưu reference tới kho bằng chứng có kiểm soát và kết quả xác minh.

### State machine

`````````mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PENDING_VERIFICATION: Tạo transaction
    PENDING_VERIFICATION --> PENDING_REVIEW: Cần review thủ công
    PENDING_VERIFICATION --> VERIFIED: Đạt policy tự động
    PENDING_VERIFICATION --> REJECTED: Bằng chứng không đạt
    PENDING_REVIEW --> VERIFIED: Reviewer phê duyệt
    PENDING_REVIEW --> REJECTED: Reviewer từ chối
    PENDING_REVIEW --> EXPIRED: Hết hạn
    VERIFIED --> COOLDOWN: Áp dụng thời gian chờ
    VERIFIED --> CREDENTIAL_RESET: Không cần cooldown
    COOLDOWN --> CREDENTIAL_RESET: Hết thời gian chờ
    COOLDOWN --> CANCELLED: Phát hiện rủi ro
    CREDENTIAL_RESET --> NEW_FACTOR_ENROLLED: Đăng ký factor mới
    NEW_FACTOR_ENROLLED --> COMPLETED: Kiểm tra hậu recovery
    CREDENTIAL_RESET --> FAILED: Lỗi cấp credential
    REJECTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    COMPLETED --> [*]
`````````

Chỉ service có thẩm quyền được chuyển trạng thái. Client không thể gửi status=verified hoặc completed để tự bỏ qua bước xác minh.

## 12. Luồng recovery từ đầu đến cuối

Một quy trình điển hình có thể gồm:

1. **Request:** người dùng yêu cầu recovery và chọn lý do;
2. **Account lookup:** server xác định account/tenant và kiểm tra trạng thái;
3. **Risk assessment:** đánh giá account privilege, dấu hiệu compromise, thiết bị và kênh còn truy cập;
4. **Evidence selection:** chọn phương thức phù hợp theo policy, ưu tiên credential đã đăng ký trước;
5. **Verification:** xác minh proof, giấy tờ hoặc nguồn tổ chức theo profile;
6. **Review:** yêu cầu reviewer/dual control nếu risk cao hoặc có ngoại lệ;
7. **Notification/cooldown:** thông báo tới kênh cũ và áp dụng thời gian chờ khi cần;
8. **Credential reset:** thu hồi factor cũ theo phạm vi đã xác định;
9. **New enrollment:** cho phép đăng ký credential mới qua enrollment an toàn;
10. **Session handling:** thu hồi session/token có nguy cơ và tạo session mới theo policy;
11. **Post-recovery controls:** giới hạn hành động nhạy cảm hoặc tăng monitoring trong giai đoạn đầu;
12. **Completion:** thông báo, ghi audit và đóng transaction.

### Sơ đồ luồng

`````````mermaid
flowchart TD
    A["Người dùng yêu cầu recovery"] --> B["Xác định account và risk"]
    B --> C["Chọn bằng chứng theo policy"]
    C --> D["Xác minh proof/identity"]
    D --> E{"Đủ assurance?"}
    E -- "Không" --> F["Từ chối hoặc chuyển review"]
    F --> G{"Review được duyệt?"}
    G -- "Không" --> X["Đóng yêu cầu và cảnh báo phù hợp"]
    G -- "Có" --> H["Thông báo và cooldown nếu cần"]
    E -- "Có" --> H
    H --> I["Thu hồi credential cũ theo phạm vi"]
    I --> J["Đăng ký credential mới"]
    J --> K["Kiểm tra session, quyền và hậu recovery"]
    K --> L["Hoàn tất và audit"]
`````````

Nếu có dấu hiệu account takeover, quy trình có thể chuyển sang incident response thay vì tiếp tục self-service recovery.

## 13. Thu hồi credential và session cũ

Sau khi xác minh chủ thể, hệ thống cần quyết định credential nào phải thu hồi. Không phải mọi recovery đều cần xóa mọi factor; nhưng không được để credential bị mất tiếp tục có hiệu lực.

### Phạm vi thu hồi

- Passkey/security key đã mất hoặc nghi bị sao chép;
- TOTP seed và thiết bị MFA cũ;
- Recovery code đã dùng hoặc bộ code cũ;
- Device certificate và device-bound key;
- Refresh token và token grant có nguy cơ;
- Session hiện tại và session trên thiết bị không tin cậy;
- API key hoặc app password nếu sự cố có thể ảnh hưởng tới chúng;
- Recovery link/challenge còn pending.

### Revoke theo risk

- **Mất một authenticator:** thu hồi credential đó và các challenge liên quan; giữ factor khác nếu policy cho phép.
- **Mất thiết bị có session active:** revoke device credential và session/token trên thiết bị đó.
- **Nghi account takeover:** revoke toàn bộ session, refresh token và credential có khả năng bị compromise; xem xét khóa account.
- **Admin recovery:** kiểm tra quyền, delegated credential, privileged session và audit trail.

Thu hồi phải được truyền tới verifier, gateway, session store và resource server. Đo propagation latency và xác nhận credential cũ thực sự bị từ chối.

## 14. Đăng ký yếu tố mới và bảo vệ sau recovery

Recovery chưa kết thúc khi người dùng chỉ nhận được một mật khẩu tạm. Người dùng cần thiết lập credential mới theo enrollment policy.

### New factor enrollment

- Yêu cầu người dùng đăng ký passkey/security key hoặc phương thức phù hợp;
- Xác minh credential mới bằng challenge/attestation theo policy;
- Gắn credential với đúng subject/tenant;
- Hiển thị thông tin nhận diện và cho phép người dùng xác nhận;
- Lưu thời điểm, loại credential và reference;
- Thông báo tới kênh đã đăng ký trước đó;
- Tạo recovery code mới nếu hệ thống hỗ trợ;
- Thu hồi code/factor cũ đã bị thay thế.

### Post-recovery restrictions

Với account rủi ro cao, có thể áp dụng:

- Cooldown trước khi chuyển tiền hoặc thêm người thụ hưởng;
- Hạn chế thay đổi email/phone recovery lần tiếp theo;
- Yêu cầu step-up phishing-resistant cho high-value action;
- Tăng giám sát login từ thiết bị mới;
- Giới hạn export dữ liệu hoặc thay đổi quyền;
- Yêu cầu admin/manager xác nhận trong thời gian đầu.

Giới hạn phải có thời hạn, phạm vi và điều kiện kết thúc rõ. Không khóa người dùng hợp lệ vô thời hạn chỉ vì họ đã recovery.

## 15. Cooldown, notification và chống takeover sau recovery

Thời gian chờ có thể giúp chủ tài khoản thật phát hiện recovery trái phép trước khi attacker thay toàn bộ factor hoặc chuyển tài sản.

### Khi nào nên dùng cooldown?

- Thay toàn bộ MFA/passkey;
- Thay email hoặc số điện thoại recovery;
- Khôi phục account đặc quyền;
- Recovery qua helpdesk;
- Recovery khi có tín hiệu rủi ro cao;
- Thay đổi làm mất khả năng liên hệ với kênh cũ.

Cooldown cần tương xứng với rủi ro và hậu quả. Có thể không cần cho thao tác thay một factor khi người dùng vẫn xác thực bằng passkey dự phòng.

### Notification

Thông báo qua kênh đã có trước recovery, nếu còn khả dụng:

- Có yêu cầu recovery;
- Recovery được duyệt/từ chối;
- Credential mới được thêm;
- Credential cũ bị thu hồi;
- Account có giới hạn tạm thời;
- Cách báo cáo nếu người nhận không khởi tạo yêu cầu.

Không gửi thông báo chỉ tới địa chỉ vừa được thay đổi trong recovery. Nếu attacker kiểm soát địa chỉ mới, thông báo sẽ không cảnh báo được chủ tài khoản cũ.

### Cancel và dispute

Chủ tài khoản cần có cách báo recovery trái phép qua kênh độc lập. Khi nhận dispute đáng tin cậy, có thể tạm dừng transaction, revoke session mới và chuyển sang incident response. Không cho attacker dùng dispute flow để gây denial of service không giới hạn; cần xác minh và rate limit.

## 16. Enterprise account và recovery qua IdP

Trong tổ chức dùng federation, việc người dùng mất quyền truy cập ứng dụng có thể do:

- Mất credential tại IdP;
- Account bị disable trong directory/HR;
- SSO client hoặc federation connection lỗi;
- Session tại ứng dụng bị revoke;
- Provisioning/deprovisioning không đồng bộ.

RP không nên tự đặt lại credential của IdP nếu tổ chức không có thẩm quyền đó. Recovery cần được chuyển tới IdP hoặc đội IAM có thẩm quyền, sau khi xác minh quan hệ nhân viên/nhà thầu theo quy trình.

### Kiểm soát

- Xác minh nguồn nhân sự/tenant có thẩm quyền;
- Dùng quy trình recovery của IdP và kiểm tra kết quả;
- Không cho helpdesk ứng dụng tự ghi đè subject hoặc link account;
- Kiểm tra account còn active và không bị deprovision;
- Thu hồi local session khi IdP báo credential compromise hoặc account disable;
- Audit correlation giữa recovery tại IdP và session lifecycle tại RP.

Với administrator hoặc service account, cần quy trình đặc biệt, break-glass account được quản lý riêng, dual control và kiểm thử định kỳ.

## 17. Threat model: tấn công identity re-verification

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Email takeover** | Attacker chiếm mailbox rồi dùng link recovery | Không dùng email đơn lẻ; token ngắn hạn, single-use, bằng chứng độc lập |
| **SIM swap** | Attacker chiếm số điện thoại và nhận OTP | Không dựa SMS làm bằng chứng mạnh; notification và step-up khác |
| **Social engineering** | Attacker gây áp lực để helpdesk reset factor | Script chuẩn, dual control, ticket/audit, cấm ngoại lệ tùy tiện |
| **Recovery code theft** | Code bị lộ qua ảnh, email hoặc phishing | Lưu verifier, one-time use, rate limit, rotate sau recovery |
| **Document forgery** | Giấy tờ giả hoặc đánh cắp được dùng | Kiểm tra authenticity, đối chiếu nhiều nguồn và review |
| **Deepfake/liveness bypass** | Video giả vượt qua remote proofing | PAD, vendor assurance, reviewer, bằng chứng bổ sung |
| **KBA guessing** | Attacker biết dữ liệu cá nhân công khai | Không dùng câu hỏi bí mật yếu làm bằng chứng chính |
| **Trusted device compromise** | Device đã đăng ký bị attacker điều khiển | Proof freshness, device status, user verification và risk |
| **Recovery CSRF** | Browser bị dụ khởi tạo hoặc xác nhận recovery | CSRF, state, transaction binding và confirmation |
| **Token replay** | Recovery link/challenge bị dùng lại | Entropy, expiry, audience, atomic consume |
| **Account enumeration** | Phản hồi tiết lộ account có tồn tại | Thông báo công khai nhất quán, audit reason chi tiết nội bộ |
| **Factor replacement attack** | Attacker thêm factor mới rồi xóa factor cũ | Step-up, cooldown, notification và recovery state machine |
| **Insider abuse** | Nhân viên reset account trái phép | Least privilege, dual approval, immutable audit |
| **Tenant mix-up** | Recovery gắn nhầm account ở tenant khác | Tenant binding server-side và kiểm tra unique identity |
| **Weak emergency path** | Break-glass bypass mọi kiểm soát | Quy trình định trước, giới hạn thời gian, alert và hậu kiểm |
| **PII exposure** | Thu thập/lưu giấy tờ hoặc sinh trắc quá mức | Data minimization, encryption, access control, retention |

## 18. Tình huống thiết kế: nhân viên mất mọi authenticator

Nhân viên An sử dụng cổng tài chính nội bộ bằng passkey và security key. Điện thoại bị mất, security key thất lạc và An không còn truy cập được email công ty trên thiết bị khác. Tài khoản có quyền phê duyệt thanh toán.

### Thiết kế chưa an toàn

1. An gọi helpdesk và cung cấp tên, ngày sinh, mã nhân viên.
2. Nhân viên hỗ trợ gửi OTP tới số điện thoại mới do An đọc qua điện thoại.
3. OTP được dùng để tắt MFA và đổi email recovery.
4. Hệ thống giữ session cũ và không thu hồi passkey/security key đã mất.
5. An có thể phê duyệt thanh toán ngay sau recovery.

### Thiết kế lại

1. Helpdesk tạo recovery request, không đổi factor ngay trong cuộc gọi.
2. Hệ thống xác định account thuộc nhóm privileged và áp dụng recovery policy mức cao.
3. Đội IAM xác minh quan hệ nhân viên qua nguồn HR/directory có thẩm quyền.
4. Hai reviewer độc lập xác nhận hồ sơ/ticket và bằng chứng bổ sung theo quy trình đã phê duyệt.
5. Recovery transaction có ID, expiry, purpose và audit; mọi bằng chứng được tham chiếu từ kho bảo vệ.
6. Chủ tài khoản nhận thông báo qua kênh tổ chức đã đăng ký nếu còn khả dụng; nếu không, quy trình có kiểm soát thay thế.
7. Sau phê duyệt, thu hồi passkey/security key bị mất, session, refresh token và challenge cũ.
8. Cho An đăng ký passkey/security key mới qua enrollment có step-up.
9. Account được mở lại với hạn chế tạm thời đối với phê duyệt thanh toán; một checker độc lập xác nhận trước khi bỏ hạn chế.
10. Theo dõi login, credential change và high-value action sau recovery; gửi thông báo hoàn tất.

### Kết quả mong đợi

- Thông tin cá nhân công khai không đủ để recovery;
- Nhân viên helpdesk không thể đơn phương reset privileged account;
- Factor/session cũ bị thu hồi thực sự;
- Credential mới được enrollment theo policy;
- Recovery không tự động khôi phục mọi quyền nhạy cảm;
- Có audit để điều tra nếu yêu cầu không hợp lệ.

## 19. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Recovery bằng passkey dự phòng** | Dùng credential đã đăng ký và còn active | Xác minh thành công theo policy |
| **Recovery code hợp lệ** | Dùng code chưa tiêu thụ | Chấp nhận một lần và consume atomically |
| **Recovery code replay** | Gửi lại code đã dùng | Từ chối |
| **Email-only recovery** | Chỉ kiểm soát mailbox, không có bằng chứng khác cho account high-risk | Không đủ assurance |
| **Phone/SMS-only recovery** | Chỉ nhận được SMS tới số mới khai báo | Từ chối |
| **SIM swap signal** | Kênh phone vừa thay hoặc có risk signal | Tăng kiểm tra hoặc chuyển review |
| **Trusted device proof** | Dùng device credential hợp lệ | Tiếp tục đánh giá account/risk |
| **Device revoked** | Dùng proof từ thiết bị đã revoke | Từ chối |
| **Document expired** | Dùng giấy tờ hết hạn khi policy yêu cầu còn hiệu lực | Từ chối/chuyển review |
| **Document replay** | Dùng lại ảnh/tài liệu từ recovery transaction khác | Phát hiện hoặc chuyển review |
| **Liveness failure** | Không đạt kiểm tra theo profile | Không tự động approve |
| **Helpdesk single approval** | Một nhân viên reset privileged account | Từ chối nếu policy yêu cầu dual control |
| **Helpdesk social engineering** | Người yêu cầu tạo áp lực hoặc giả danh lãnh đạo | Nhân viên theo quy trình, không bypass |
| **Wrong tenant** | Sửa tenant/account reference trong request | Server dùng binding đã lưu và từ chối mismatch |
| **Recovery token replay** | Dùng lại link/challenge | Từ chối |
| **Recovery token expired** | Gửi sau expiry | Từ chối |
| **Concurrent recovery** | Hai transaction cùng reset factor | Chỉ transaction hợp lệ được commit |
| **Factor replacement** | Thêm factor mới rồi thử giữ factor đã báo mất | Factor cũ bị revoke theo policy |
| **Session revocation** | Dùng session cũ sau recovery | Bị từ chối theo SLA |
| **Refresh token replay** | Dùng refresh token cũ sau revoke | Từ chối |
| **Post-recovery high-value action** | Thực hiện thanh toán ngay sau recovery | Áp dụng cooldown/approval theo policy |
| **Notification** | Recovery hoàn tất | Gửi tới kênh đã đăng ký trước đó |
| **Account enumeration** | Thử recovery với account tồn tại/không tồn tại | Phản hồi công khai không tiết lộ trạng thái |
| **PII redaction** | Kiểm tra audit/log | Không có ảnh giấy tờ, biometric raw hoặc secret không cần thiết |
| **Audit integrity** | Thử sửa/xóa event bằng quyền vận hành thông thường | Bị ngăn hoặc tạo bằng chứng tamper |

Kiểm thử cần chạy trên recovery API, helpdesk workflow, identity provider, credential registry, session service và resource API. Một trang recovery báo “thành công” không chứng minh factor cũ đã bị thu hồi.

## 20. Audit, giám sát và chỉ số vận hành

Recovery cần audit chi tiết vì đây là quá trình thay đổi quyền kiểm soát tài khoản.

| Event | Trường gợi ý |
| --- | --- |
| account.recovery.started | Recovery ID, subject reference, tenant, purpose |
| account.recovery.evidence.submitted | Evidence type/reference, source, timestamp |
| account.recovery.verification.succeeded/failed | Method, policy version, reason code |
| account.recovery.review.requested | Reviewer group, reason, expiry |
| account.recovery.approved/rejected | Actor/reviewer reference, decision, reason |
| account.recovery.cooldown.started/ended | Start/end, policy, notification status |
| account.credential.revoked | Credential reference/type, reason, actor |
| account.credential.enrolled | New credential reference/type, enrollment transaction |
| account.session.revoked | Session reference, reason, propagation |
| account.recovery.completed/failed | Recovery ID, final state, affected credential refs |
| account.recovery.exception.used | Exception type, approver, expiry, post-review |

Không ghi recovery code, OTP, password, private key, raw token, biometric template hoặc ảnh giấy tờ vào event log. Dùng evidence reference và kết quả xác minh; dữ liệu gốc nếu phải giữ cần kho riêng, mã hóa và phân quyền chặt.

### Chỉ số nên theo dõi

- Recovery request rate theo tenant, account type và purpose;
- Tỷ lệ recovery thành công/thất bại theo evidence type;
- Manual review rate và thời gian xử lý;
- Recovery denial rate và reason code;
- Tỷ lệ recovery sau login bất thường;
- Tỷ lệ thay đổi factor/email/phone ngay sau recovery;
- Số high-value action trong cooldown window;
- Session/credential revocation propagation latency;
- Số recovery exception và tỷ lệ hậu kiểm;
- Account takeover được xác nhận sau recovery;
- False rejection và khiếu nại của người dùng hợp lệ;
- Thời gian lưu và truy cập dữ liệu proofing/PII.

Không tối ưu recovery success rate bằng cách hạ bằng chứng. Cần theo dõi cả takeover sau recovery và tỷ lệ từ chối nhầm để cân bằng bảo mật với khả năng tiếp cận.

## 21. Checklist triển khai Identity re-verification

- **Purpose:** Lý do recovery và loại account được xác định rõ?
- **Risk:** Có phân loại privilege, asset impact và dấu hiệu compromise?
- **Evidence:** Ưu tiên credential/kênh đã đăng ký trước; đánh giá nguồn, binding và independence?
- **Assurance:** Bằng chứng đạt mức phù hợp với account và action?
- **Contact channels:** Email/phone chỉ được dùng trong phạm vi phù hợp; kênh mới khai không tự xác minh chủ account?
- **Documents/biometrics:** Có authenticity/liveness review, phương án thay thế và data minimization?
- **Helpdesk:** Có quy trình, least privilege, dual control và chống social engineering?
- **Transaction:** Recovery ID, state, nonce, expiry, purpose và single-use được ràng buộc server-side?
- **Approval:** Privileged/high-risk recovery có reviewer độc lập?
- **Cooldown/notification:** Có thời gian chờ và thông báo tới kênh đã có trước đó khi cần?
- **Revocation:** Credential, recovery code, session, refresh token và challenge cũ được thu hồi đúng phạm vi?
- **New enrollment:** Credential mới được tạo và xác minh theo policy?
- **Post-recovery:** Có giới hạn hành động, monitoring và điều kiện kết thúc?
- **Federation:** Recovery tại IdP/RP có đúng thẩm quyền và đồng bộ trạng thái?
- **Privacy:** Dữ liệu giấy tờ/sinh trắc được giới hạn, mã hóa, phân quyền và xóa theo retention?
- **Audit:** Có event cho bằng chứng, quyết định, reviewer, revoke, enroll và exception?
- **Testing:** Đã thử email-only, SIM swap, replay, helpdesk abuse, race condition và session propagation?

### Câu hỏi tự kiểm tra

1. Identity re-verification khác reauthentication và identity proofing ban đầu thế nào?
2. Vì sao account recovery có thể trở thành đường vòng yếu nhất của authentication?
3. Tại sao bằng chứng đã đăng ký trước thường có giá trị hơn email hoặc số điện thoại vừa khai?
4. Recovery code cần những kiểm soát nào để chống dò và replay?
5. Giấy tờ tùy thân và liveness chứng minh được điều gì, và không chứng minh được điều gì?
6. Vì sao helpdesk cần dual control với account đặc quyền?
7. Recovery transaction cần ràng buộc những trường nào?
8. Sau recovery, credential và session cũ cần được xử lý thế nào?
9. Cooldown và notification giúp giảm rủi ro takeover ra sao?
10. Làm thế nào bảo vệ quyền riêng tư khi cần thu thập bằng chứng identity proofing?

## Kết luận

**Identity re-verification là bước xác minh lại chủ thể trước khi khôi phục quyền kiểm soát tài khoản, và phải có mức tin cậy tương xứng với giá trị của account.** Quy trình nên ưu tiên credential hoặc bằng chứng đã đăng ký trước, đánh giá nguồn, tính độc lập và freshness; dùng giấy tờ, sinh trắc học hoặc helpdesk như các thành phần có giới hạn và được kiểm soát. Recovery transaction cần gắn với đúng account, tenant, purpose, challenge và thời hạn; quyết định đặc quyền cần review độc lập. Sau khi xác minh, hệ thống phải thu hồi credential/session cũ, enrollment yếu tố mới, thông báo qua kênh đã có và áp dụng hạn chế sau recovery khi cần. Bảo vệ recovery đòi hỏi đồng thời chống social engineering, replay và insider abuse, duy trì audit có integrity và thu thập dữ liệu cá nhân ở mức tối thiểu.
