# Login usability — Thiết kế trải nghiệm đăng nhập an toàn, rõ ràng và dễ tiếp cận

> **Chương:** Trải nghiệm người dùng  
> **Chủ đề:** Login usability  
> **Phạm vi:** Security Authentication Fundamentals — thiết kế trải nghiệm đăng nhập cho web, mobile và ứng dụng doanh nghiệp; giảm nhầm lẫn và thao tác thừa, hỗ trợ password manager, passkey, MFA, bảo vệ quyền riêng tư và accessibility, đồng thời giữ nguyên yêu cầu xác thực của hệ thống.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt usability, accessibility và security trong luồng đăng nhập.
2. Mô hình hóa hành trình từ mở trang login tới khi người dùng vào đúng account và resource.
3. Thiết kế form, label, input type và autocomplete phù hợp với browser/password manager.
4. Giảm lỗi nhập password mà không làm yếu credential policy.
5. Thiết kế MFA, passkey và federation với hướng dẫn dễ hiểu, có thể khôi phục.
6. Viết thông báo lỗi hữu ích mà không tiết lộ account existence hoặc thông tin bảo mật.
7. Thiết kế session, remember-me và step-up authentication theo risk.
8. Đảm bảo keyboard navigation, screen reader, contrast, focus và responsive layout.
9. Đo lường tỷ lệ hoàn tất, lỗi, abandon, recovery và support contact mà vẫn bảo vệ privacy.
10. Kiểm thử login usability bằng task-based test, assistive technology và thiết bị thực tế.

## 1. Login usability là gì?

**Login usability** là mức độ người dùng có thể hoàn thành xác thực một cách dễ hiểu, hiệu quả, ít lỗi và phù hợp với nhu cầu của họ. Một luồng đăng nhập tốt giúp người dùng biết mình cần làm gì, hiểu kết quả của thao tác, xử lý lỗi và tiếp tục an toàn trên thiết bị hoặc phương thức xác thực phù hợp.

Đăng nhập là điểm tiếp xúc quan trọng giữa người dùng và ranh giới tin cậy của ứng dụng. Thiết kế quá khó có thể khiến người dùng chọn password yếu, chia sẻ OTP, bỏ qua cảnh báo hoặc tìm cách né quy trình. Thiết kế quá dễ dãi lại có thể tạo đường bypass MFA, recovery hoặc session policy.

### Bốn mục tiêu cần cân bằng

| Mục tiêu | Câu hỏi |
| --- | --- |
| Usability | Người dùng có hiểu và hoàn thành flow không? |
| Accessibility | Người dùng có thể sử dụng bằng bàn phím, screen reader, zoom hoặc công nghệ hỗ trợ không? |
| Security | Flow có xác minh đúng danh tính và chống lạm dụng không? |
| Privacy | UI có tiết lộ dữ liệu account hoặc thu thập dữ liệu không cần thiết không? |

Không nên xem số bước ít nhất là trải nghiệm tốt nhất. Một bước xác nhận thêm có thể cần thiết cho thao tác rủi ro cao; ngược lại, yêu cầu MFA lặp lại không có lý do có thể làm người dùng mệt mỏi và tăng nguy cơ approve nhầm.

## 2. Xác định người dùng và hành trình đăng nhập

Trước khi thiết kế màn hình, cần hiểu ai đang đăng nhập, từ đâu và để làm gì.

### Nhóm người dùng

- Người dùng cá nhân đăng nhập bằng email hoặc số điện thoại;
- Nhân viên dùng tài khoản doanh nghiệp và SSO;
- Quản trị viên có quyền cao;
- Khách hàng sử dụng mobile app;
- Người dùng chỉ có passkey hoặc passwordless;
- Người dùng cần hỗ trợ công nghệ tiếp cận;
- Người dùng đang ở thiết bị mới hoặc thiết bị dùng chung;
- Người dùng đang khôi phục account hoặc thay đổi factor.

Mỗi nhóm có kiến thức, thiết bị, ngôn ngữ và mức assurance khác nhau. Không mặc định mọi người đều có smartphone, có thể nhận SMS hoặc có quyền cài ứng dụng authenticator.

### Hành trình cơ bản

1. Người dùng mở ứng dụng hoặc theo một link hợp lệ;
2. Xác định đúng website/app và account context;
3. Chọn hoặc nhập identifier;
4. Chọn phương thức xác thực;
5. Hoàn tất password, passkey, MFA hoặc federation;
6. Xử lý challenge hoặc lỗi nếu có;
7. Nhận xác nhận đăng nhập thành công;
8. Được đưa tới đúng trang đích;
9. Duy trì session theo policy;
10. Có thể xem thiết bị/session và đăng xuất khi cần.

### Hành trình thay thế

Phải thiết kế cả các trường hợp:

- Quên password;
- Mất điện thoại hoặc authenticator;
- Không có mạng hoặc không nhận được OTP;
- Passkey không khả dụng trên thiết bị;
- Người dùng hủy challenge;
- IdP bên ngoài không phản hồi;
- Session hết hạn khi đang làm việc;
- Account đang bị khóa hoặc cần xác minh thêm;
- Người dùng đăng nhập nhầm tenant/account.

Một flow chỉ được xem là hoàn chỉnh khi cả đường thành công và các đường lỗi/khôi phục đều có hướng dẫn rõ ràng.

## 3. Nguyên tắc thiết kế màn hình đăng nhập

### Một màn hình, một mục tiêu chính

Mỗi bước nên có mục tiêu rõ:

- Nhập identifier;
- Chọn phương thức;
- Xác minh factor;
- Xác nhận recovery;
- Hoàn tất đăng nhập.

Tránh hiển thị cùng lúc quá nhiều lựa chọn, thông tin marketing, banner, form đăng ký, recovery và cảnh báo không liên quan. Nếu có nhiều phương thức, sắp xếp theo phương thức được hỗ trợ và phù hợp với user, nhưng luôn cung cấp đường thay thế đã được phê duyệt.

### Nội dung cần có

- Tên ứng dụng/tổ chức và ngữ cảnh domain;
- Tiêu đề mô tả hành động;
- Label rõ cho từng input;
- Nút hành động chính có tên cụ thể;
- Link trợ giúp hoặc recovery dễ tìm;
- Thông báo lỗi cạnh trường liên quan và summary khi cần;
- Chỉ dẫn về SSO/passkey/MFA khi flow yêu cầu.

### Không làm người dùng mất ngữ cảnh

Khi chuyển sang MFA hoặc external identity provider, cần cho người dùng biết:

- Họ đang xác minh cho ứng dụng nào;
- Vì sao cần thêm bước;
- Họ cần thao tác trên thiết bị nào;
- Có thể quay lại hoặc chọn cách khác ra sao;
- Điều gì xảy ra nếu hủy.

Không hiển thị chi tiết nội bộ như issuer URL, client secret, signing key hoặc policy rule.

## 4. Identifier và cách nhập liệu

Identifier có thể là email, username, số điện thoại hoặc enterprise identity. Label và validation cần phản ánh chính xác dữ liệu mà hệ thống chấp nhận.

### Label rõ ràng

Nên dùng label như:

- Email hoặc tên đăng nhập;
- Số điện thoại đã đăng ký;
- Tài khoản công ty;
- Mã nhân viên nếu đây thực sự là identifier được hỗ trợ.

Không dùng placeholder làm label duy nhất. Placeholder biến mất khi người dùng nhập và có thể không được screen reader nhận diện như label.

### Chuẩn hóa input

- Trim khoảng trắng ở đầu/cuối nếu semantics cho phép;
- Không tự ý đổi chữ hoa/thường của identifier nếu hệ thống phân biệt;
- Hỗ trợ paste;
- Không áp dụng mask gây cản trở password manager;
- Không từ chối ký tự hợp lệ chỉ vì regex quá hẹp;
- Không cắt chuỗi identifier một cách im lặng;
- Hiển thị định dạng ví dụ nếu có yêu cầu cụ thể.

### Validation

Client-side validation giúp người dùng sửa lỗi sớm, nhưng server vẫn là nguồn quyết định cuối cùng. Không dùng lỗi client để tiết lộ account có tồn tại hay không.

Ví dụ, lỗi định dạng email có thể hiển thị trước khi submit. Nhưng sau khi submit, thông báo account không tồn tại nên được thiết kế nhất quán với policy chống enumeration.

## 5. Password input và password manager

Password manager và autofill giúp người dùng dùng password dài, duy nhất. Form login cần hỗ trợ chúng thay vì cản trở.

### HTML input phù hợp

    <form method="post" action="/session">
      <label for="username">Email hoặc tên đăng nhập</label>
      <input id="username" name="username" type="text"
             autocomplete="username" required />
      <label for="password">Mật khẩu</label>
      <input id="password" name="password" type="password"
             autocomplete="current-password" required />
      <button type="submit">Đăng nhập</button>
    </form>

Ví dụ chỉ minh họa semantic form và autocomplete. Production cần HTTPS, CSRF protection phù hợp, server-side validation, secure session handling và rate limiting.

### Các thuộc tính quan trọng

- Username field dùng autocomplete=username;
- Password đăng nhập dùng autocomplete=current-password;
- Password tạo mới dùng autocomplete=new-password;
- OTP có thể dùng autocomplete=one-time-code khi phù hợp;
- Form có label liên kết với input;
- Không tắt paste hoặc autofill;
- Không chặn password manager bằng JavaScript tùy tiện.

### Show/hide password

Nút hiện/ẩn password có thể giúp người dùng phát hiện lỗi gõ, đặc biệt trên mobile. Nút phải có accessible name, trạng thái được thông báo cho assistive technology và không làm mất giá trị input.

Không tự động hiển thị password. Khi bật hiển thị, nên giữ trạng thái có thể kiểm soát và tránh làm password lộ khi màn hình đang được chia sẻ hoặc thiết bị dùng chung.

### Không áp đặt quy tắc nhập gây khó

- Không giới hạn password ở độ dài thấp;
- Không tự trim hoặc sửa password;
- Không yêu cầu người dùng tự nhớ nhiều quy tắc ký tự không cần thiết;
- Không bắt đổi password định kỳ nếu không có căn cứ rủi ro/chính sách;
- Không chặn password dài hoặc passphrase hợp lệ;
- Không buộc người dùng gõ lại password chỉ vì một lỗi mạng có thể retry an toàn.

### Copy và paste

Cho phép paste password và OTP khi phù hợp. Chặn paste thường làm password manager, assistive technology và người dùng khuyết tật khó sử dụng hơn, đồng thời không ngăn được attacker có credential.

## 6. Thông báo lỗi hữu ích và an toàn

Thông báo lỗi nên nói người dùng có thể làm gì tiếp theo, nhưng không tiết lộ account state, credential policy nội bộ hoặc tín hiệu giúp attacker dò account.

### Nguyên tắc

- Dùng ngôn ngữ dễ hiểu;
- Tránh mã lỗi kỹ thuật;
- Nêu bước tiếp theo;
- Giữ thông báo nhất quán khi cần chống enumeration;
- Không đổ lỗi hoặc làm người dùng xấu hổ;
- Không đưa dữ liệu nhạy cảm vào message;
- Đặt focus và thông báo lỗi cho screen reader.

### Ví dụ

| Tình huống | Thông báo gợi ý |
| --- | --- |
| Credential không hợp lệ | “Email hoặc mật khẩu chưa đúng. Hãy kiểm tra và thử lại.” |
| Rate limit | “Bạn đã thử quá nhiều lần. Vui lòng chờ một lúc rồi thử lại.” |
| MFA timeout | “Mã xác minh đã hết hạn. Hãy yêu cầu mã mới.” |
| Push challenge pending | “Hãy mở ứng dụng xác thực đã đăng ký và kiểm tra yêu cầu đăng nhập.” |
| Passkey unavailable | “Không tìm thấy passkey phù hợp trên thiết bị này. Bạn có thể thử cách xác minh khác.” |
| Service unavailable | “Hiện chưa thể đăng nhập. Thông tin của bạn chưa được xác minh; vui lòng thử lại sau.” |
| Recovery request | “Nếu thông tin phù hợp với một tài khoản, chúng tôi sẽ gửi hướng dẫn tới kênh đã đăng ký.” |

### Không nhầm lỗi hệ thống với credential sai

Nếu token endpoint, database hoặc MFA provider bị lỗi, không hiển thị “mật khẩu sai”. Thông báo sai khiến người dùng đổi password không cần thiết, làm tăng support load và che giấu outage.

### Error summary và inline error

Với form nhiều trường:

- Hiển thị summary ở đầu form khi submit thất bại;
- Liên kết từng lỗi với input tương ứng;
- Không chỉ dùng màu đỏ để truyền đạt lỗi;
- Giữ giá trị identifier nếu an toàn và hữu ích;
- Không giữ password sau lỗi theo policy;
- Đưa focus tới summary hoặc trường lỗi theo hành vi dễ hiểu.

## 7. MFA usability

MFA là một bước bổ sung có thể làm tăng assurance nhưng cũng tăng friction. Hướng dẫn cần đủ rõ để người dùng biết challenge thuộc login nào và thao tác đúng.

### Trước khi gửi challenge

- Nêu lý do yêu cầu MFA;
- Cho biết factor sẽ được dùng, ví dụ authenticator hoặc security key;
- Không tiết lộ toàn bộ số điện thoại/email recovery;
- Không gửi challenge lặp khi user chưa yêu cầu;
- Hiển thị trạng thái đang chờ và cách hủy.

### OTP

- Cho phép paste và autofill;
- Hỗ trợ nhập mã bằng một field khi phù hợp với password manager/OS;
- Không ép chia thành nhiều ô nếu gây khó cho screen reader hoặc paste;
- Nêu số chữ số và thời hạn khi cần;
- Không hiển thị OTP đã nhập sau submit;
- Có resend cooldown và thông báo rõ;
- Không cho phép resend vô hạn.

### Push notification

- Hiển thị tên dịch vụ và context đăng nhập;
- Dùng number matching hoặc transaction context khi có;
- Cho phép deny dễ dàng;
- Hướng dẫn người dùng từ chối nếu họ không tự khởi tạo;
- Không dùng wording gây áp lực như “Approve ngay để tránh khóa account”;
- Có cách báo cáo prompt không mong muốn.

### Factor fallback

Fallback phải được xác định theo assurance policy. Không tự động hạ xuống SMS/email chỉ vì factor mạnh đang lỗi. Nếu cần phương thức thay thế, giải thích lý do và áp dụng risk control phù hợp.

## 8. Passkey usability

Passkey có thể giảm thao tác nhập password và chống phishing nhờ credential gắn với relying party. Tuy vậy, trải nghiệm cần giải thích được hành động và hỗ trợ nhiều thiết bị.

### Đăng nhập

- Dùng nhãn quen thuộc như “Đăng nhập bằng passkey”;
- Cho biết người dùng có thể dùng thiết bị/security key đã đăng ký;
- Kích hoạt platform/browser UI đúng cách;
- Không bắt người dùng hiểu thuật ngữ WebAuthn, RP ID hoặc challenge;
- Có fallback an toàn nếu passkey không khả dụng;
- Không coi lỗi platform prompt là password sai.

### Đăng ký

- Giải thích lợi ích và thiết bị được dùng;
- Yêu cầu xác thực hiện tại đủ mạnh trước khi thêm credential;
- Xác nhận tên thiết bị thân thiện, không lộ metadata nhạy cảm;
- Cho phép quản lý và xóa passkey;
- Thông báo khi có credential mới được thêm;
- Cung cấp recovery path không làm yếu bảo mật.

### Nhiều thiết bị

Người dùng có thể có passkey đồng bộ hoặc passkey gắn thiết bị. UI nên tránh khẳng định “passkey chỉ nằm trên thiết bị này” nếu không biết chính xác loại credential. Cung cấp thông tin quản lý credential dựa trên metadata mà server thực sự có.

### Không ép dùng passkey trong mọi tình huống

Nếu người dùng đang ở thiết bị không hỗ trợ hoặc không có credential phù hợp, cung cấp đường thay thế đã được policy cho phép. Không tạo fallback yếu đến mức vô hiệu hóa lợi ích của passkey.

## 9. SSO và federation usability

Đăng nhập liên kết chuyển người dùng tới identity provider khác. UI phải giúp người dùng hiểu họ đang rời ứng dụng nào và đăng nhập ở đâu.

### Nội dung nút

Ưu tiên nhãn cụ thể:

- “Tiếp tục với tài khoản công ty”;
- “Đăng nhập qua Microsoft Entra ID” nếu đúng provider;
- “Đăng nhập bằng tài khoản tổ chức”.

Tránh nút chung chung như “Continue” khi có nhiều IdP.

### Chuyển hướng

- Nêu rõ người dùng sẽ được chuyển tới trang đăng nhập của tổ chức;
- Dùng domain/brand đã được xác minh;
- Không nhúng form password của IdP vào WebView không tin cậy;
- Giữ transaction context và quay lại đúng ứng dụng;
- Xử lý cancel, timeout và state mismatch rõ ràng;
- Không hiển thị raw protocol error hoặc issuer URL cho người dùng.

### Nhiều tổ chức/tenant

Nếu người dùng cần chọn organization, hiển thị tên dễ nhận biết và có thể xác minh. Không để query parameter tùy ý quyết định tenant mà không kiểm tra server-side.

## 10. Account recovery và quên mật khẩu

Recovery thường là lúc người dùng dễ căng thẳng và ít kiên nhẫn. Flow cần rõ ràng, nhất quán và không tạo lối bypass.

### Recovery UX

- Link “Quên mật khẩu?” dễ tìm;
- Hướng dẫn người dùng nhập identifier;
- Thông báo nhất quán để tránh account enumeration;
- Giải thích thời hạn link và cách yêu cầu link mới;
- Nêu kênh hỗ trợ chính thức;
- Cung cấp hướng dẫn khi mất MFA/passkey;
- Sau recovery, xác nhận thay đổi và hướng dẫn kiểm tra session.

### Recovery security

- Token entropy cao, purpose-bound, short-lived và single-use;
- GET không tự hoàn tất side effect nhạy cảm khi có nguy cơ email scanner/prefetch;
- Token không bị ghi vào log hoặc analytics;
- Thay đổi factor yêu cầu assurance phù hợp;
- Revoke session/token cũ theo policy;
- Gửi notification qua kênh tin cậy;
- Không dùng email/phone đang bị nghi compromise làm bằng chứng duy nhất.

### Hướng dẫn người dùng

Không yêu cầu người dùng gửi password, OTP hoặc recovery code cho support. Support không nên hỏi bí mật để xác minh account; dùng quy trình identity proofing và ticket có audit.

## 11. Session, remember me và thiết bị tin cậy

Người dùng muốn tránh đăng nhập lặp lại, nhưng session dài hạn làm tăng tác động nếu thiết bị hoặc cookie bị mất.

### Remember me

Nhãn “Giữ đăng nhập” cần giải thích ý nghĩa phù hợp:

- Có thể duy trì session trên thiết bị này;
- Không nên bật mặc định trên thiết bị dùng chung;
- Có thể đăng xuất từ danh sách thiết bị/session;
- Một số thao tác nhạy cảm vẫn yêu cầu xác minh lại.

Không dùng remember-me token không hết hạn hoặc cookie không có rotation/revocation policy.

### Session visibility

Cho phép người dùng xem:

- Thiết bị hoặc browser đã đăng nhập;
- Thời điểm hoạt động gần nhất;
- Session hiện tại;
- Hành động đăng xuất thiết bị khác;
- Thông tin bảo mật ở mức đủ hiểu, không hiển thị raw session ID.

### Reauthentication

Yêu cầu xác minh lại khi:

- Thay đổi password hoặc MFA;
- Thêm/xóa passkey;
- Thay email/phone recovery;
- Xem hoặc export dữ liệu nhạy cảm;
- Thực hiện giao dịch có rủi ro cao;
- Thay đổi quyền hoặc liên kết account.

Giải thích tại sao cần xác minh lại và factor nào được chấp nhận.

## 12. Risk-based login và step-up

Risk-based authentication có thể thay đổi mức xác minh dựa trên context, nhưng UI phải minh bạch và tránh tạo bất ngờ.

### Tín hiệu có thể dùng

- Thiết bị mới hoặc browser mới;
- Vị trí/network bất thường;
- Credential failure trước login;
- Thay đổi account gần đây;
- Hành động nhạy cảm;
- Session age và authentication age;
- Risk signal từ IdP hoặc device posture.

Tín hiệu không nên được xem như bằng chứng danh tính độc lập. IP/geolocation có thể sai do VPN, roaming hoặc shared network.

### Step-up UX

- Nêu hành động cần xác minh thêm;
- Không yêu cầu user đoán lý do;
- Hiển thị factor được hỗ trợ;
- Giữ nguyên công việc chưa submit nếu an toàn;
- Có timeout và cách tiếp tục;
- Không làm lộ rule risk hoặc thông tin phát hiện nội bộ.

### Tránh MFA fatigue

Không yêu cầu người dùng approve challenge không có transaction rõ ràng. Với push flow, cung cấp context và khả năng deny; không tự động gửi nhiều prompt do retry.

## 13. Accessibility cho login

Login là chức năng thiết yếu; người dùng phải có thể hoàn thành bằng nhiều cách tương tác.

### Keyboard

- Tất cả input, button và link có thể truy cập bằng Tab/Shift+Tab;
- Focus order theo thứ tự đọc và thao tác;
- Focus indicator rõ;
- Không tạo keyboard trap;
- Enter/Space hoạt động đúng theo loại control;
- Không tự chuyển focus bất ngờ khi user đang nhập.

### Screen reader

- Mỗi input có accessible name/label;
- Hint và error được liên kết với input;
- Trạng thái loading/challenge được thông báo;
- Error summary có thể được focus;
- Toggle show/hide password có tên và trạng thái;
- Không chỉ truyền đạt trạng thái bằng màu hoặc icon;
- OTP field không bị đọc thành nhiều phần khó hiểu.

### Visual accessibility

- Contrast văn bản và control đủ theo tiêu chuẩn áp dụng;
- Zoom/reflow không làm mất nút hoặc input;
- Không dùng màu làm tín hiệu duy nhất;
- Text không bị cắt khi tăng font;
- Focus không bị che bởi sticky footer/dialog;
- Error message có vị trí và wording rõ.

### Cognitive accessibility

- Hướng dẫn ngắn, trực tiếp;
- Tránh thuật ngữ nội bộ;
- Không yêu cầu ghi nhớ mã hoặc bước không cần thiết;
- Giữ tiến trình khi có thể;
- Cho phép xem lại identifier đã nhập;
- Dùng timeout có cảnh báo và cách gia hạn hợp lý nếu policy cho phép.

### Motion và timing

Không tự động chuyển màn hình quá nhanh. Người dùng cần thời gian đọc và thao tác. Nếu challenge hết hạn, thông báo trước khi hết hạn khi có thể và cho phép yêu cầu lại.

## 14. Responsive và mobile usability

Mobile login cần tính đến bàn phím ảo, màn hình nhỏ, autofill, camera/passkey prompt, app switching và mạng không ổn định.

### Form mobile

- Input đủ lớn để chạm;
- Label luôn nhìn thấy;
- Bàn phím phù hợp với loại input;
- Không che nút submit;
- Không yêu cầu nhập lại thông tin không cần;
- Cho phép paste và autofill;
- Hỗ trợ landscape/zoom;
- Tránh layout nhảy khi keyboard hoặc browser chrome xuất hiện.

### App switching

MFA hoặc federation có thể chuyển người dùng sang authenticator/browser khác. Khi quay lại:

- Khôi phục transaction state an toàn;
- Không mất identifier đã nhập nếu policy cho phép;
- Hiển thị trạng thái challenge;
- Xử lý callback đến trễ hoặc trùng;
- Không hoàn tất transaction hai lần;
- Cho phép user hủy hoặc thử lại.

### Mạng yếu

- Phân biệt timeout với credential failure;
- Hiển thị trạng thái đang gửi;
- Ngăn double-submit;
- Retry chỉ khi operation có semantics an toàn;
- Không gửi lại OTP hoặc password vô hạn;
- Giữ thông tin form không nhạy cảm nếu an toàn.

## 15. Localization và nội dung dễ hiểu

Authentication UX thường dùng từ ngữ có ý nghĩa bảo mật. Dịch máy móc có thể làm người dùng hiểu sai hành động.

### Nội dung cần bản địa hóa

- Label, button và helper text;
- Error, recovery và MFA instructions;
- Thời hạn và định dạng ngày giờ;
- Tên phương thức xác thực;
- Hướng dẫn thiết bị và accessibility;
- Notification đăng nhập/factor change;
- Support channel và policy.

### Nguyên tắc

- Dùng từ phổ biến, tránh thuật ngữ kỹ thuật;
- Không dịch khác nhau cùng một khái niệm ở các màn hình;
- Không ghép chuỗi theo ngữ pháp tiếng Anh;
- Hỗ trợ text expansion;
- Không giả định định dạng ngày, số điện thoại hoặc tên;
- Không dùng icon/flag để thay tên ngôn ngữ;
- Kiểm tra bản dịch với người dùng thực tế.

### Ví dụ wording

Thay vì “Invalid authentication factor”, dùng “Mã xác minh chưa đúng hoặc đã hết hạn. Hãy kiểm tra và thử lại.” Thay vì “OIDC provider unavailable”, dùng “Dịch vụ đăng nhập của tổ chức hiện chưa phản hồi. Bạn có thể thử lại sau.”

## 16. Privacy và trust signals

Người dùng cần nhận biết họ đang đăng nhập đúng ứng dụng và dữ liệu của họ được xử lý có trách nhiệm.

### Trust signals hữu ích

- Domain/app identity rõ ràng;
- Tên tổ chức/tenant đúng;
- HTTPS và browser security indicator do nền tảng hiển thị;
- Thông báo khi thêm factor hoặc đăng nhập từ thiết bị mới;
- Trang quản lý session và credential;
- Kênh support chính thức.

Không tự vẽ biểu tượng khóa hoặc tuyên bố “100% an toàn” để thay thế trust indicator của browser/OS.

### Privacy

- Không hiển thị email/phone đầy đủ khi không cần;
- Không tiết lộ account tồn tại trong recovery;
- Không gửi thông tin đăng nhập vào analytics;
- Không hiển thị sensitive claim trên notification lock screen;
- Không thu thập device fingerprint vượt mục đích;
- Nêu rõ khi chuyển sang external IdP;
- Cung cấp privacy notice ở nơi phù hợp, không làm rối màn hình login.

### Shared device

Trên thiết bị dùng chung, tránh tự động lưu identifier hoặc bật remember-me. Cung cấp tùy chọn đăng xuất rõ ràng và nhắc người dùng đóng session khi hoàn tất.

## 17. Performance và resilience

Login UX bị ảnh hưởng bởi latency, dependency outage và retry behavior.

### Trạng thái rõ ràng

- Idle;
- Submitting;
- Waiting for MFA/passkey;
- Redirecting to IdP;
- Success;
- Recoverable error;
- Service unavailable.

Button cần ngăn double-submit khi request đang chạy. Loading state không nên kéo dài vô hạn; có timeout và cách thử lại rõ ràng.

### Retry an toàn

- Không retry tự động password submit vô hạn;
- Không tạo nhiều MFA challenge khi user bấm nhiều lần;
- Không gửi lại authorization request khi transaction cũ còn pending;
- Với timeout không rõ server đã xử lý hay chưa, kiểm tra trạng thái transaction trước khi tạo transaction mới;
- Dùng backoff khi dependency tạm unavailable.

### Graceful degradation

Nếu passkey platform API lỗi, có thể hiển thị phương thức thay thế đã được policy cho phép. Nếu MFA provider outage, không tự động bỏ MFA cho action cần assurance cao. Nếu IdP unavailable, hiển thị trạng thái service issue thay vì yêu cầu người dùng đổi password.

## 18. Telemetry về usability và privacy

Đo lường giúp tìm friction, nhưng event cần được tối thiểu hóa và không chứa credential.

### Metric hữu ích

- Login completion rate;
- Time to complete;
- Abandonment theo bước;
- Error rate theo reason family;
- Password reset initiation/completion;
- MFA challenge success/timeout/deny;
- Passkey availability và completion;
- SSO redirect success/failure;
- Recovery support contact rate;
- Login failure do service dependency;
- Accessibility task completion.

### Event gợi ý

| Event | Dữ liệu tối thiểu |
| --- | --- |
| login.viewed | Flow ID, client, locale |
| login.method.selected | Method class, flow ID |
| login.submitted | Flow ID, method, outcome pending |
| login.completed | Flow ID, duration bucket, method |
| login.failed | Reason family, không có raw credential |
| mfa.started | Factor type, flow reference |
| mfa.completed | Outcome, duration bucket |
| passkey.started | Platform class, browser/app version |
| passkey.completed | Outcome, flow reference |
| recovery.completed | Purpose, outcome, duration bucket |

### Không thu thập

- Password, OTP, recovery code;
- Raw access/refresh/ID token;
- Session cookie;
- Full email/phone nếu không cần;
- Sensitive claim;
- Raw WebAuthn assertion;
- Nội dung người dùng nhập vào form.

Dùng pseudonymous flow reference và aggregate metric. Tránh label cardinality cao như user ID/session ID trong metric system.

## 19. Usability testing và nghiên cứu người dùng

Không thể kết luận login dễ dùng chỉ bằng review giao diện. Cần quan sát người dùng hoàn thành task.

### Task-based testing

Ví dụ task:

- Đăng nhập bằng password manager;
- Đăng nhập bằng passkey trên thiết bị có credential;
- Dùng security key hoặc authenticator;
- Hoàn tất SSO và quay lại app;
- Khôi phục password;
- Đổi hoặc xóa passkey;
- Đăng xuất khỏi thiết bị khác;
- Xử lý MFA prompt không do mình khởi tạo;
- Hoàn thành login bằng keyboard/screen reader.

### Quan sát

- Task completion rate;
- Thời gian hoàn tất;
- Số lần nhập sai;
- Số lần back/forward;
- Điểm người dùng bị mắc kẹt;
- Tỷ lệ cần trợ giúp;
- Mức độ hiểu thông báo lỗi;
- Khả năng nhận diện domain/tenant;
- Khả năng phân biệt MFA prompt thật và không mong muốn.

### Participant diversity

Bao gồm người dùng mới và quen thuộc, thiết bị cũ/mới, màn hình nhỏ, mạng yếu, người dùng keyboard-only và screen reader. Không chỉ test với nhân viên kỹ thuật đã quen hệ thống.

### Moderation

Yêu cầu người tham gia nói suy nghĩ khi thao tác, nhưng không yêu cầu họ dùng password thật. Dùng account test, dữ liệu giả và môi trường không có quyền truy cập production.

## 20. Common usability failures

| Lỗi thiết kế | Tác động | Cải thiện |
| --- | --- | --- |
| Placeholder là label duy nhất | Người dùng quên ý nghĩa field sau khi nhập | Label cố định và accessible name |
| Chặn paste | Password manager/assistive tech khó dùng | Cho phép paste và autofill |
| Tắt autocomplete | Người dùng phải nhớ password | Dùng autocomplete token đúng |
| Error “Something went wrong” | Không biết bước tiếp theo | Message theo reason family và action |
| Tiết lộ email tồn tại | Account enumeration | Response nhất quán |
| MFA prompt không context | User dễ approve nhầm | Nêu service/context và number matching |
| Nhiều ô OTP khó thao tác | Screen reader/paste gặp vấn đề | Một input semantic khi phù hợp |
| Không có fallback passkey | Người dùng bị khóa ngoài account | Fallback theo assurance policy |
| Recovery chỉ qua email yếu | Bypass MFA | Recovery proof độc lập và audit |
| Session hết hạn đột ngột | Mất công việc | Cảnh báo và xử lý session expiry rõ |
| Remember-me bật mặc định | Rủi ro thiết bị dùng chung | Tùy chọn rõ, không preselect |
| Chỉ báo lỗi bằng màu | Người dùng mù màu không nhận biết | Text/icon/ARIA |
| Focus bị mất sau lỗi | Keyboard user khó tiếp tục | Focus management có chủ đích |
| Redirect không giải thích | User tưởng bị phishing | Nêu IdP/organization rõ |
| Retry vô hạn | Tạo load và challenge trùng | Timeout, backoff, transaction state |

## 21. Ví dụ đặc tả login flow

Một ứng dụng doanh nghiệp hỗ trợ password, passkey và SSO.

### Entry screen

- Tiêu đề: “Đăng nhập vào tài khoản của bạn”;
- Identifier field: “Email hoặc tài khoản công ty”;
- Primary action: “Tiếp tục”;
- Alternative: “Đăng nhập bằng passkey”;
- Enterprise option: “Đăng nhập bằng tài khoản tổ chức”;
- Recovery link: “Không truy cập được tài khoản?”.

### Behavior

1. Người dùng nhập identifier và chọn Continue;
2. Server trả phương thức được phép cho account/tenant mà không tiết lộ account existence qua response công khai;
3. Nếu password flow, hiển thị password field với current-password autocomplete;
4. Nếu passkey flow, gọi platform/browser API và hiển thị prompt hệ thống;
5. Nếu SSO, chuyển qua external user-agent tới IdP đã cấu hình;
6. Nếu policy yêu cầu MFA/step-up, hiển thị context và factor;
7. Sau success, hiển thị trạng thái đăng nhập và route tới destination đã được allowlist;
8. Nếu lỗi, message đưa ra next step phù hợp;
9. Recovery và factor changes được xử lý bằng flow riêng có assurance tương ứng.

### Sơ đồ

    flowchart TD
        A["Open sign-in"] --> B["Enter identifier or choose passkey"]
        B --> C{"Available method"}
        C -->|Password| D["Password form"]
        C -->|Passkey| E["Platform passkey prompt"]
        C -->|SSO| F["External identity provider"]
        D --> G["Verify credential"]
        E --> H["Verify WebAuthn assertion"]
        F --> I["Validate federation response"]
        G --> J{"Step-up required?"}
        H --> J
        I --> J
        J -->|Yes| K["MFA / step-up"]
        J -->|No| L["Create application session"]
        K --> L
        L --> M["Show success and safe destination"]

### Error state

- Identifier format sai: chỉ dẫn sửa field;
- Credential không hợp lệ: thông báo chung, không tiết lộ account existence;
- Passkey không khả dụng: gợi ý phương thức thay thế;
- MFA timeout: cho phép yêu cầu challenge mới theo cooldown;
- IdP unavailable: thông báo service issue;
- Rate limited: nêu thời gian chờ nếu policy cho phép;
- Session expired: đưa tới login và giữ destination an toàn.

## 22. Bộ kiểm thử chấp nhận

| Trường hợp | Cách kiểm tra | Kết quả kỳ vọng |
| --- | --- | --- |
| Label semantics | Dùng screen reader đọc form | Mỗi input có label rõ |
| Placeholder | Xóa nội dung input | Label vẫn nhìn thấy |
| Keyboard order | Tab qua toàn form | Focus order hợp lý |
| Focus indicator | Điều hướng keyboard | Focus luôn nhìn thấy |
| Keyboard trap | Dùng Tab/Shift+Tab trong dialog | Có thể thoát và quay lại |
| Screen reader error | Submit form lỗi | Error được thông báo và liên kết field |
| Contrast | Kiểm tra text/control | Đạt tiêu chuẩn contrast áp dụng |
| Zoom/reflow | Phóng to 200%/400% | Không mất chức năng chính |
| Mobile keyboard | Mở identifier/password | Keyboard phù hợp, không che submit |
| Password manager | Autofill login | Username/password được nhận diện |
| Paste password | Paste password dài | Không bị chặn hoặc cắt |
| Current password autocomplete | Kiểm tra input | Dùng current-password |
| New password autocomplete | Kiểm tra reset form | Dùng new-password |
| OTP autofill | Nhận OTP trên thiết bị hỗ trợ | Có thể autofill/paste |
| Show password | Bật/tắt visibility | Accessible name/state đúng |
| Double submit | Bấm nút nhiều lần | Không tạo nhiều login transaction |
| Wrong credential | Submit password sai | Message hữu ích, không enumeration |
| Unknown account | Submit identifier không tồn tại | Response công khai nhất quán |
| Rate limit | Thử quá nhiều lần | Thông báo chờ và không lộ policy nội bộ |
| MFA context | Gửi push challenge | User biết dịch vụ và transaction |
| MFA deny | Từ chối prompt không yêu cầu | Có hướng dẫn và event phù hợp |
| MFA timeout | Để challenge hết hạn | Có thể yêu cầu lại theo cooldown |
| MFA outage | Provider không phản hồi | Không báo password sai hoặc bypass MFA |
| Passkey available | Login trên thiết bị có passkey | Flow hoàn tất rõ ràng |
| Passkey unavailable | Thiết bị không có credential | Fallback an toàn hiển thị |
| Passkey registration | Thêm credential mới | Reauthentication, confirm và audit |
| SSO redirect | Chọn tổ chức | Domain/provider rõ ràng |
| SSO cancel | Người dùng hủy tại IdP | Quay lại app với message hữu ích |
| SSO outage | IdP timeout | Service error, không lộ protocol detail |
| Recovery enumeration | Thử email tồn tại/không tồn tại | Response công khai nhất quán |
| Recovery scanner | Email scanner mở link | GET không consume action nhạy cảm |
| Recovery replay | Dùng link đã consume | Bị từ chối và hướng dẫn an toàn |
| Remember me | Đăng nhập trên thiết bị dùng chung | Không bật mặc định |
| Session visibility | Xem thiết bị/session | Không lộ raw session ID |
| Logout other sessions | Revoke session khác | Session bị thu hồi theo SLA |
| Step-up | Thực hiện action nhạy cảm | Yêu cầu factor phù hợp |
| Destination | Login với return path lạ | Redirect chỉ tới destination được phép |
| Localization | Chuyển locale | Wording và layout không lỗi |
| Privacy | Kiểm tra analytics/log | Không có password, OTP hoặc token |
| Network timeout | Ngắt mạng khi submit | Không retry vô hạn hoặc tạo challenge trùng |
| App switching | Chuyển sang authenticator rồi quay lại | Transaction được khôi phục an toàn |
| Shared device | Logout rồi mở lại app | Không còn thông tin account cũ |
| User research | Quan sát task với participant đa dạng | Task completion và friction được đo |

Kiểm thử cần có browser/OS thật, password manager phổ biến, screen reader, keyboard-only, mobile app và external IdP. Automated accessibility scan không thay thế usability test với người dùng.

## 23. Checklist thiết kế Login usability

- **User context:** Đã xác định user type, device, tenant, language và task?
- **Flow:** Có đường thành công, cancel, timeout, recovery và fallback?
- **Form:** Label, input type, autocomplete và validation đúng?
- **Password:** Password manager, paste, show/hide và password length được hỗ trợ?
- **Errors:** Thông báo hữu ích, không lộ account existence hoặc secret?
- **MFA:** Challenge có context, cooldown, deny và fallback theo policy?
- **Passkey:** Registration/login/management và recovery rõ ràng?
- **SSO:** Provider/domain, redirect, cancel và error được giải thích?
- **Recovery:** Có purpose-bound token, single-use, expiry và notification?
- **Session:** Remember-me, timeout, device visibility, logout và reauthentication?
- **Risk-based:** Step-up có lý do và không tạo MFA fatigue?
- **Accessibility:** Keyboard, focus, screen reader, contrast, zoom và timing?
- **Mobile:** Autofill, app switching, keyboard, network và deep link?
- **Localization:** Wording, date/time, layout và text expansion?
- **Privacy:** Không lộ identifier/claim/token; analytics tối thiểu?
- **Resilience:** Loading, retry, timeout và dependency outage được phân biệt?
- **Measurement:** Completion, abandon, duration, error và support contact được đo?
- **Testing:** Có usability test với người dùng đa dạng và thiết bị thực?

### Câu hỏi tự kiểm tra

1. Vì sao placeholder không thể thay thế label?
2. Password manager và paste hỗ trợ cả usability lẫn security như thế nào?
3. Vì sao login error cần cân bằng tính hữu ích với chống account enumeration?
4. MFA push cần context gì để giảm approve nhầm?
5. Passkey UX cần xử lý thế nào khi thiết bị không có credential?
6. Vì sao recovery cần được xem là một phần của login usability?
7. Khi nào cần step-up và cách giải thích với người dùng?
8. Những kiểm tra accessibility nào cần làm bằng keyboard và screen reader?
9. Vì sao không tự động bỏ MFA khi provider gặp outage?
10. Metric nào đo friction mà không thu thập password hoặc token?

## Kết luận

**Login usability tốt giúp người dùng hoàn thành xác thực đúng cách, hiểu điều đang xảy ra và xử lý được lỗi mà không phải hy sinh trust boundary.** Thiết kế cần hỗ trợ password manager, passkey, MFA, SSO và recovery; thông báo lỗi phải hữu ích nhưng không tiết lộ account state; session và step-up cần phản ánh risk. Accessibility, responsive behavior, localization và privacy phải được xem xét ngay từ đầu. Cuối cùng, cần đo task completion, abandonment, lỗi và support burden bằng telemetry tối thiểu, rồi kiểm thử với browser, thiết bị và người dùng đa dạng. Một luồng login chỉ thực sự usable khi người dùng hợp lệ có thể hoàn tất, người dùng gặp sự cố có đường hỗ trợ rõ, và attacker không có thêm con đường vượt xác thực.
