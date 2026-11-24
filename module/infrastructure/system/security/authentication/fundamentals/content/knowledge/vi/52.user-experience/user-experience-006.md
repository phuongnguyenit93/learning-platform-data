# Device enrollment experience

**Device enrollment experience** là trải nghiệm hướng dẫn người dùng đăng ký một thiết bị hoặc authenticator mới để thiết bị đó có thể tham gia vào các luồng xác thực của tài khoản. Tùy sản phẩm, người dùng có thể thêm passkey, security key, điện thoại nhận push, ứng dụng TOTP, thiết bị tin cậy hoặc một phương thức khôi phục. Enrollment thường tạo ra một liên kết bảo mật lâu dài giữa tài khoản, credential và thiết bị; vì vậy, thiết kế trải nghiệm cần giúp người dùng hiểu họ đang thêm gì, xác minh đúng người đang thực hiện thao tác và cho phép quản lý hoặc thu hồi liên kết đó về sau.

Một quy trình enrollment tốt phải đồng thời dễ hoàn tất và khó bị chiếm đoạt. Người dùng cần biết lý do hệ thống yêu cầu thêm thiết bị, dữ liệu nào được lưu, thiết bị có thể làm gì, cách dùng thiết bị khi đăng nhập và cách gỡ bỏ khi bị mất. Hệ thống cần xác minh phiên hiện tại, yêu cầu step-up phù hợp, chống CSRF và replay, kiểm tra challenge, ràng buộc đúng tài khoản và ghi audit event. Nếu một thiết bị bị mất hoặc người dùng đổi điện thoại, họ cần có con đường khôi phục an toàn mà không phải hạ thấp assurance cho toàn bộ tài khoản.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn. Trong chương **Trải nghiệm người dùng**, bài này tập trung vào trải nghiệm đăng ký thiết bị, authenticator và quản lý vòng đời của chúng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt device enrollment, authenticator enrollment, device recognition và device binding.
2. Thiết kế luồng thêm thiết bị có xác minh phiên, step-up authentication và transaction binding.
3. Giải thích các lựa chọn enrollment cho passkey, security key, TOTP, push và thiết bị quản lý.
4. Xây dựng UX giúp người dùng hiểu consent, phạm vi sử dụng, đồng bộ và quyền riêng tư.
5. Ngăn enrollment takeover bằng re-authentication, CSRF defense, challenge một lần và thông báo ngoài băng.
6. Quản lý thiết bị nhiều tài khoản, nhiều authenticator và nhiều nền tảng mà không trộn credential.
7. Thiết kế trạng thái pending, active, suspended, revoked và expired.
8. Xử lý đổi thiết bị, mất thiết bị, đồng bộ passkey và account recovery.
9. Đảm bảo accessibility, localization và hỗ trợ người dùng khi enrollment thất bại.
10. Xây dựng test plan đo cả completion rate, usability và các thuộc tính bảo mật của enrollment.

## 2. Phân biệt thiết bị, authenticator và device binding

Từ “thiết bị tin cậy” thường được dùng cho nhiều khái niệm khác nhau. Cần tách chúng để UX và policy không hứa quá mức.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Device enrollment | Ghi nhận một thiết bị hoặc installation trong tài khoản theo một quy trình xác minh | Người dùng thêm điện thoại mới vào danh sách thiết bị. |
| Authenticator enrollment | Đăng ký một phương tiện có thể tạo bằng chứng xác thực | Tạo passkey, thêm security key hoặc TOTP authenticator. |
| Device recognition | Nhận diện một thiết bị dựa trên tín hiệu hoặc cookie để điều chỉnh risk/UX | Hiển thị “thiết bị đã từng dùng” hoặc giảm bước kiểm tra phụ theo policy. |
| Device binding | Ràng buộc credential/token với khóa hoặc thiết bị theo một giao thức cụ thể | DPoP key hoặc khóa thiết bị dùng để chứng minh possession. |
| Managed device enrollment | Đăng ký thiết bị vào hệ thống quản lý của tổ chức | MDM/EMM áp policy cho thiết bị nhân viên. |
| Trusted session | Một phiên đã được xác thực và có thể được đánh giá theo policy | Session cookie còn hiệu lực sau login và MFA. |

Device recognition không tự chứng minh người đang cầm thiết bị là chủ tài khoản. IP, user-agent, cookie nhận diện hoặc fingerprint có thể bị thay đổi, sao chép, chia sẻ hoặc sai lệch. Chúng có thể là tín hiệu risk nhưng không thay thế password, passkey, MFA hoặc bằng chứng possession của private key.

Device binding mạnh hơn khi dựa trên khóa mật mã được tạo và giữ trong vùng bảo vệ của hệ điều hành/phần cứng, và server yêu cầu proof-of-possession theo giao thức. Tuy vậy, binding cũng không bảo đảm tuyệt đối thiết bị không bị compromise; malware có thể điều khiển app hoặc gọi thao tác ký nếu chiếm được runtime. UX phải mô tả chính xác mức bảo vệ đang có.

### 2.1. Enrollment không đồng nghĩa login

Login xác minh người dùng trong một transaction. Enrollment thay đổi các credential có thể dùng cho những lần login sau. Một attacker chiếm được session đang hoạt động có thể cố thêm passkey hoặc factor của họ để duy trì quyền truy cập sau khi session bị thu hồi. Vì vậy, enrollment là hành động nhạy cảm và thường cần re-authentication hoặc step-up.

### 2.2. Một thiết bị có thể có nhiều authenticator

Điện thoại có thể chứa passkey platform, TOTP app, push authenticator và khóa thiết bị dùng cho ứng dụng. Ngược lại, một passkey có thể được đồng bộ qua credential provider tới nhiều thiết bị. UI nên hiển thị đúng đối tượng đang quản lý: authenticator, thiết bị vật lý, installation, hoặc bản sao đồng bộ. Không hiển thị một passkey đồng bộ như thể chỉ tồn tại trên một chiếc điện thoại nếu thực tế nó có thể được dùng trên các thiết bị khác.

## 3. Nguyên tắc thiết kế trải nghiệm enrollment

Một trải nghiệm tốt cần làm rõ mục đích, giảm bất ngờ và giữ được kiểm soát bảo mật.

### 3.1. Nói rõ người dùng đang thêm gì

Dùng tên cụ thể như:
- Thêm passkey trên thiết bị này.
- Đăng ký security key.
- Thêm ứng dụng xác thực tạo mã.
- Cho phép điện thoại này nhận yêu cầu xác minh.
- Đăng ký thiết bị công ty được quản lý.

Tránh chỉ dùng nhãn chung chung như “Trust this device” nếu hành động thực tế là thêm một authenticator có thể đăng nhập tài khoản. Giải thích thiết bị hoặc credential có thể làm gì, chẳng hạn “Có thể dùng passkey này để đăng nhập mà không cần mật khẩu”.

### 3.2. Nói rõ lý do và thời điểm

Giải thích tại sao enrollment được yêu cầu:
- Người dùng chủ động thêm phương thức đăng nhập.
- Tổ chức yêu cầu MFA cho tài khoản có quyền cao.
- Người dùng vừa đăng nhập trên thiết bị mới.
- Risk policy yêu cầu thêm yếu tố trước khi thực hiện hành động nhạy cảm.
- Người dùng đang thay thế thiết bị sắp ngừng sử dụng.

Không tạo cảm giác khẩn cấp giả hoặc dùng thông điệp gây sợ hãi để ép người dùng enroll. Nếu enrollment là bắt buộc, nêu rõ thời hạn, chức năng bị giới hạn và kênh hỗ trợ.

### 3.3. Consent có ý nghĩa

Trước khi tạo credential, giải thích:
- Loại credential sẽ được tạo.
- Credential gắn với tài khoản nào và relying party/organization nào.
- Dữ liệu nào được lưu ở server và dữ liệu nào do OS/authenticator quản lý.
- Credential có đồng bộ giữa thiết bị hay không, nếu sản phẩm biết điều đó.
- Người dùng có thể đổi tên, xem lần sử dụng gần nhất hoặc thu hồi ra sao.
- Việc thu hồi có ảnh hưởng các thiết bị hoặc bản sao khác hay không.

Không tuyên bố ứng dụng đọc hoặc lưu biometric template nếu thao tác thực tế do hệ điều hành xử lý. Không hứa passkey “chỉ nằm trên điện thoại này” nếu credential provider có thể đồng bộ.

### 3.4. Bảo mật không được phụ thuộc vào lời nhắc khó hiểu

Nếu cần step-up, giải thích người dùng cần xác minh lại vì đang thêm phương thức có thể đăng nhập tài khoản. Không yêu cầu nhập lại password trong một form trông giống trang của bên thứ ba. Ưu tiên authentication flow đã đăng ký, passkey hoặc factor hiện có. Nếu phiên đã quá cũ, yêu cầu xác thực mới theo policy và gắn proof đó với đúng enrollment transaction.

## 4. Luồng enrollment tổng quát

Một flow có thể gồm các bước:

1. Người dùng mở phần Security hoặc Devices trong account settings.
2. Chọn loại thiết bị/authenticator muốn thêm.
3. Hệ thống kiểm tra session, account status, risk và policy.
4. Nếu cần, yêu cầu re-authentication hoặc step-up bằng factor hiện có.
5. Server tạo enrollment transaction và challenge ngẫu nhiên, có thời hạn.
6. Client gọi API/OS/browser authenticator để tạo hoặc xác minh credential.
7. Server xác minh challenge, origin, RP ID, signature, transaction và account binding.
8. Credential được lưu với trạng thái pending hoặc active theo protocol.
9. UI hiển thị xác nhận, cho phép đặt tên và giải thích cách dùng.
10. Hệ thống gửi thông báo bảo mật qua kênh đã xác minh.
11. Audit event ghi actor, subject, credential reference, outcome và thời điểm.
12. Người dùng có thể xem và thu hồi credential trong phần quản lý thiết bị.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant UI as Account Security UI
    participant AS as Authentication Service
    participant A as OS / Authenticator
    participant DB as Credential Store
    participant N as Notification Service
    U->>UI: Chọn thêm authenticator
    UI->>AS: Yêu cầu bắt đầu enrollment
    AS->>AS: Kiểm tra session, risk và policy
    AS-->>UI: Step-up hoặc enrollment challenge
    opt Cần step-up
        UI->>AS: Bằng chứng xác thực bổ sung
        AS-->>UI: Step-up được chấp nhận
    end
    UI->>A: Tạo credential / ký challenge
    A-->>UI: Credential response
    UI->>AS: Gửi response và transaction
    AS->>AS: Verify challenge, origin, account binding
    AS->>DB: Lưu credential
    AS->>N: Gửi thông báo bảo mật
    AS-->>UI: Enrollment thành công
    UI-->>U: Hiển thị thiết bị/authenticator mới
~~~

Thứ tự thực tế tùy protocol. Với WebAuthn, server tạo creation options/challenge, browser gọi authenticator và server xác minh attestation/credential response. Với TOTP, server tạo seed/provisioning URI, người dùng quét bằng authenticator app rồi nhập mã để xác minh khả năng tạo OTP. Không dùng một flow chung để bỏ qua semantics riêng của từng protocol.

## 5. Xác minh người yêu cầu enrollment

Enrollment có thể làm thay đổi các phương thức đăng nhập của tài khoản. Trước khi thêm credential, cần xác minh request đến từ một chủ thể đã được xác thực và có quyền thay đổi security settings.

### 5.1. Re-authentication và step-up

Có thể yêu cầu:
- Password hiện tại, nếu tài khoản dùng password và policy cho phép.
- Passkey hiện có với user verification.
- Security key đã đăng ký.
- TOTP hoặc factor mạnh hiện có.
- Step-up theo assurance policy của tổ chức.

Chọn factor dựa trên risk và khả năng chống phishing. Nếu attacker đã chiếm password nhưng chưa có MFA, việc yêu cầu lại chính password không đủ bảo vệ enrollment. Với hành động thêm passkey hoặc thay recovery factor, ưu tiên proof mạnh đã đăng ký và gần thời điểm hiện tại.

### 5.2. Transaction binding

Proof step-up phải gắn với hành động cụ thể:
- Account/subject đúng.
- Loại credential đang thêm.
- Enrollment transaction ID.
- Challenge và thời hạn.
- Client/origin hợp lệ.
- Nonce/state không thể tái sử dụng.
- Policy version và mức assurance đạt được.

Không cho phép một lần xác thực chung được tái sử dụng vô thời hạn để enroll nhiều thiết bị. Nếu người dùng mở nhiều tab, mỗi transaction phải có state riêng hoặc cơ chế đồng bộ được thiết kế rõ.

### 5.3. CSRF và session hijacking

Endpoint enrollment thay đổi trạng thái phải có CSRF defense phù hợp với session model. Kiểm tra origin/referer theo policy, anti-CSRF token hoặc cơ chế tương đương; cookie SameSite chỉ là một lớp bảo vệ. Không để GET request tạo credential hoặc kích hoạt thao tác bảo mật. Chống session fixation, rotate session khi cần và yêu cầu step-up nếu session có dấu hiệu rủi ro.

### 5.4. Thông báo ngoài băng

Sau enrollment, gửi thông báo tới kênh đã xác minh trước đó, chẳng hạn email hoặc push hiện có:
- Có thiết bị/authenticator mới được thêm.
- Thời điểm và loại phương thức.
- Cách xem danh sách và thu hồi nếu không phải người dùng thực hiện.
- Liên kết tới trang quản lý tài khoản trên origin chính thức.

Thông báo không được chứa secret, private key, TOTP seed hoặc token. Link quản lý phải chống phishing, dùng domain chính thức và yêu cầu xác thực khi thực hiện thao tác nhạy cảm. Không dựa vào email notification như bằng chứng enrollment hợp lệ; nó là kênh phát hiện và phản ứng.

## 6. Enrollment passkey và WebAuthn

Passkey enrollment cần giải thích rằng authenticator tạo một cặp khóa: private key được giữ bởi authenticator/credential provider, server lưu public key và metadata để xác minh assertion. Người dùng có thể dùng biometric hoặc PIN của thiết bị để mở khóa thao tác, nhưng ứng dụng không nhận biometric template.

### 6.1. Trải nghiệm đề xuất

1. Người dùng chọn “Tạo passkey”.
2. UI nêu passkey dùng để đăng nhập và có thể được quản lý bởi password/passkey provider của hệ điều hành.
3. Server tạo challenge, user/account binding và creation options.
4. Browser/OS hiển thị prompt authenticator.
5. Người dùng xác minh bằng biometric/PIN hoặc thao tác security key.
6. Client gửi credential response.
7. Server kiểm tra challenge, origin, RP ID, attestation policy nếu áp dụng và các thuộc tính bắt buộc.
8. Server lưu credential ID, public key, transports và metadata.
9. UI xác nhận passkey đã được thêm, cho phép đặt nhãn dễ nhận biết.
10. Người dùng nhận thông báo bảo mật và có thể kiểm tra trong danh sách passkey.

### 6.2. Không diễn giải sai về đồng bộ

Một passkey có thể:
- Chỉ tồn tại trên authenticator/thiết bị cụ thể.
- Được đồng bộ qua hệ sinh thái credential provider.
- Được dùng qua cross-device authentication bằng QR hoặc Bluetooth-assisted flow tùy nền tảng.
- Được lưu trên security key vật lý.

UI không phải lúc nào cũng biết chính xác mọi bản sao đồng bộ tồn tại ở đâu. Dùng mô tả có điều kiện, ví dụ “Passkey được lưu bởi nhà cung cấp credential trên thiết bị/tài khoản của bạn; khả năng đồng bộ phụ thuộc cài đặt của nhà cung cấp”. Tránh khẳng định thu hồi credential phía server sẽ xóa mọi bản sao passkey khỏi cloud provider; server-side revoke thường chỉ làm credential không còn được chấp nhận cho tài khoản tại dịch vụ.

### 6.3. Attestation và quyền riêng tư

Attestation có thể cung cấp thông tin về authenticator model hoặc nguồn gốc, nhưng có thể tạo fingerprint thiết bị. Chỉ yêu cầu attestation khi threat model, policy và ecosystem cần; chọn conveyance phù hợp và giảm thiểu dữ liệu. Không thu thập attestation chỉ vì có thể. Nêu rõ nếu tổ chức yêu cầu authenticator được quản lý hoặc chứng nhận.

### 6.4. Passkey enrollment thất bại

Xử lý rõ các trường hợp:
- Người dùng hủy prompt.
- Browser/OS không hỗ trợ.
- Không có authenticator phù hợp.
- Challenge hết hạn.
- Origin/RP ID không hợp lệ.
- Credential đã được đăng ký.
- Network timeout sau khi authenticator tạo credential.
- Server lưu thành công nhưng response tới UI bị mất.

Không hiển thị “thất bại” chung chung nếu trạng thái có thể đã commit. Cung cấp nút kiểm tra danh sách passkey hoặc làm mới trạng thái từ server. Nếu transaction không rõ kết quả, không tự lặp tạo credential mù quáng; kiểm tra transaction/status trước khi retry.

## 7. Enrollment TOTP và ứng dụng xác thực

TOTP enrollment thường cần trao đổi shared secret một lần, nên cần đặc biệt bảo vệ provisioning data.

### 7.1. Luồng

1. Người dùng chọn thêm ứng dụng xác thực.
2. Hệ thống yêu cầu step-up theo policy.
3. Server tạo TOTP seed bằng CSPRNG và enrollment transaction có expiry.
4. UI hiển thị QR/provisioning URI chỉ trong phiên enrollment.
5. Người dùng quét bằng authenticator app.
6. Người dùng nhập mã hiện tại.
7. Server xác minh mã trong time window và chống replay theo policy.
8. Server kích hoạt factor và mã hóa seed để lưu.
9. UI xác nhận, cung cấp recovery codes nếu policy yêu cầu.
10. Gửi thông báo enrollment.

Không ghi QR/provisioning URI, seed hoặc OTP vào log, analytics, screenshot, clipboard history hay support ticket. Khi người dùng đóng trang trước khi verify, seed pending phải hết hạn và được hủy theo policy.

### 7.2. UX cho nhập mã

- Chấp nhận paste toàn bộ mã nếu an toàn.
- Tự chuyển focus hợp lý nhưng không làm screen reader khó hiểu.
- Không chỉ dựa vào màu để báo lỗi.
- Hiển thị thời gian thử lại nếu mã hết hạn.
- Cho phép nhập lại trong giới hạn rate limit.
- Không tạo seed mới sau mỗi lần nhập sai.
- Giải thích cần đồng bộ thời gian trên authenticator nếu có clock skew.

### 7.3. Recovery codes

Nếu cung cấp recovery code:
- Nêu rõ mỗi mã chỉ dùng một lần.
- Hiển thị một lần và khuyến nghị lưu ở nơi an toàn.
- Không gửi lại mã qua email hoặc chat.
- Cho phép tạo bộ mới sau step-up và thu hồi bộ cũ.
- Thông báo khi một mã được dùng.
- Có cách kiểm tra số mã còn lại mà không hiển thị mã gốc.

## 8. Enrollment push authenticator và thiết bị nhận challenge

Một số sản phẩm cho phép điện thoại nhận push challenge để phê duyệt đăng nhập. Enrollment cần ràng buộc app installation/device key với tài khoản và chứng minh người dùng kiểm soát thiết bị.

Quy trình gợi ý:
1. Người dùng đã đăng nhập và vượt step-up.
2. App đăng ký device public key hoặc installation credential theo protocol.
3. Server tạo challenge enrollment.
4. App chứng minh possession của private key hoặc hoàn tất xác minh kênh theo thiết kế.
5. Server liên kết credential với account, device reference và app instance.
6. App bật notification permission với lời giải thích rõ; permission hệ điều hành không phải bằng chứng xác thực.
7. Gửi một challenge thử để người dùng xác nhận đúng thiết bị.
8. UI hiển thị tên thiết bị, trạng thái và cách thu hồi.

Push approval nên gắn với transaction, hiển thị context như dịch vụ, thời điểm hoặc số matching nếu có. Không chỉ hiển thị nút Approve/Reject chung chung cho mọi request. Chống notification fatigue bằng cooldown, rate limit, number matching và cảnh báo khi có nhiều challenge không mong muốn.

Nếu người dùng từ chối notification permission, không tự động bỏ MFA. Có thể cung cấp TOTP/security key đã enroll hoặc hướng dẫn bật notification nếu policy yêu cầu push.

## 9. Enrollment security key vật lý

Security key có thể là authenticator chống phishing mạnh, nhưng UX phụ thuộc cổng kết nối, NFC/Bluetooth, PIN và thao tác chạm.

Hướng dẫn nên:
- Cho biết thiết bị hỗ trợ USB/NFC/Bluetooth nào.
- Yêu cầu người dùng cắm/chạm key khi browser prompt xuất hiện.
- Không yêu cầu nhập PIN vào trang web nếu PIN phải nhập qua browser/OS authenticator UI.
- Giải thích touch/PIN có thể cần cho mỗi lần xác thực theo cấu hình.
- Hỗ trợ hủy và thử lại mà không tạo credential trùng.
- Cho phép đăng ký nhiều key dự phòng.
- Gợi ý đặt nhãn vật lý như “Key dự phòng” hoặc “Key mang theo”.

Không yêu cầu người dùng gửi security key cho support hoặc chụp ảnh mã định danh bí mật. Nếu cần inventory, chỉ lưu credential reference và metadata tối thiểu; không lưu private key.

## 10. Device naming và danh sách thiết bị

Sau enrollment, người dùng cần nhận biết credential nào đang hoạt động. Một danh sách tốt có:
- Tên do người dùng đặt hoặc nhãn mặc định có thể sửa.
- Loại authenticator/device.
- Ngày thêm.
- Lần sử dụng gần nhất nếu có dữ liệu đáng tin.
- Trạng thái active, pending, suspended hoặc revoked.
- Thông tin đồng bộ/managed nếu hệ thống biết.
- Hành động đổi tên, xem chi tiết hoặc thu hồi.

Tên thiết bị là nhãn do người dùng nhập, không phải bằng chứng danh tính. Sanitize nội dung, giới hạn độ dài, xử lý Unicode/control characters và không dùng tên làm authorization decision. Nếu dùng user-agent để gợi ý tên mặc định, phải coi là metadata không đáng tin và cho phép người dùng sửa.

### 10.1. Tránh gây nhầm lẫn

Không hiển thị nhiều record giống nhau mà không có cách phân biệt. Nếu một credential được đồng bộ, diễn đạt rằng nó có thể xuất hiện trên nhiều thiết bị theo nhà cung cấp. Nếu một installation có nhiều authenticator, tách chúng trong UI. Khi xóa một credential, nêu rõ thao tác ảnh hưởng credential đó trên dịch vụ và không nhất thiết xóa bản sao trong OS/cloud provider.

### 10.2. Thiết bị hiện tại và thiết bị khác

Phân biệt “phiên đang dùng” với “thiết bị có authenticator”. Một người có thể đăng nhập bằng passkey được đồng bộ từ thiết bị khác; browser hiện tại không nhất thiết là nơi lưu credential. UI nên tránh khẳng định “thiết bị này đã được đăng ký” chỉ vì session hiện tại thành công.

## 11. Vòng đời và state machine

Một credential/device enrollment nên có trạng thái rõ ràng để UI và backend không bất đồng.

~~~mermaid
stateDiagram-v2
    [*] --> NotEnrolled
    NotEnrolled --> Pending: Start enrollment
    Pending --> Active: Proof verified and persisted
    Pending --> Expired: Challenge expires
    Pending --> Cancelled: User cancels
    Active --> Suspended: Risk or admin hold
    Suspended --> Active: Revalidated
    Active --> Revoked: User/admin revokes
    Suspended --> Revoked: Confirmed compromise
    Revoked --> [*]
    Expired --> [*]
    Cancelled --> [*]
~~~

Ý nghĩa:
- **NotEnrolled:** chưa có credential được liên kết.
- **Pending:** transaction đã bắt đầu nhưng chưa hoàn tất proof.
- **Active:** credential được xác minh và có thể dùng theo policy.
- **Suspended:** tạm thời không được chấp nhận trong khi điều tra hoặc revalidation.
- **Revoked:** server không còn chấp nhận credential.
- **Expired:** enrollment challenge hoặc credential đã hết hạn.
- **Cancelled:** người dùng chủ động hủy transaction.

Chỉ chuyển sang Active sau khi server xác minh proof và lưu credential bền vững. Không dựa vào việc browser prompt đóng hoặc app báo thành công để kích hoạt. Nếu server commit nhưng client mất response, client cần truy vấn trạng thái transaction/credential thay vì tạo thêm credential vô tình.

### 11.1. Idempotency và nhiều tab

Enrollment request có thể bị gửi lại do double-click, refresh, network retry hoặc nhiều tab:
- Mỗi transaction có ID và challenge riêng.
- Dùng idempotency key cho thao tác tạo/commit nếu API hỗ trợ.
- Chỉ một commit được chấp nhận cho transaction.
- Challenge một lần và có expiry.
- Không để response đến muộn ghi đè trạng thái Revoked.
- Khi account đổi hoặc logout, transaction pending phải bị hủy hoặc không còn quyền commit.

## 12. Đổi thiết bị, mất thiết bị và account recovery

Enrollment UX không hoàn chỉnh nếu chỉ hỗ trợ thêm thiết bị. Người dùng thường đổi điện thoại, mất security key, xóa authenticator app hoặc không còn truy cập thiết bị cũ.

### 12.1. Người dùng còn thiết bị cũ

Nếu người dùng còn một authenticator hợp lệ:
1. Đăng nhập trên thiết bị mới.
2. Step-up bằng passkey/security key/factor hiện có.
3. Thêm authenticator mới.
4. Kiểm tra thiết bị mới hoạt động.
5. Chuyển dữ liệu hoặc đăng ký lại phương thức cần thiết.
6. Thu hồi thiết bị cũ khi người dùng xác nhận.
7. Thông báo thay đổi và cập nhật danh sách.

Không yêu cầu xóa thiết bị cũ trước khi thiết bị mới được xác minh, trừ khi threat model yêu cầu. Giữ ít nhất một phương thức dự phòng hợp lệ giúp tránh lockout.

### 12.2. Người dùng mất thiết bị cũ

Nếu không còn factor hiện có:
- Dùng account recovery đã thiết kế và xác minh độc lập.
- Có thể yêu cầu recovery code, passkey khác, security key dự phòng hoặc quy trình proofing phù hợp.
- Đánh giá risk và có cooling-off period cho thay đổi nhạy cảm nếu policy cần.
- Thông báo qua kênh liên hệ đã xác minh trước đó.
- Revoke session/device credential bị mất sau khi xác minh quyền sở hữu.
- Không cho support agent bỏ qua mọi kiểm tra chỉ dựa vào thông tin dễ biết như tên, ngày sinh hoặc email.

Recovery phải có mức assurance phù hợp với hậu quả của việc chiếm tài khoản. Nếu không thể xác minh đủ, cần từ chối hoặc chuyển sang quy trình hỗ trợ có kiểm soát.

### 12.3. Thiết bị bị mất nhưng vẫn còn session khác

Từ một session khác đã xác thực, người dùng có thể:
- Xem danh sách session/device/authenticator.
- Revoke session của thiết bị bị mất.
- Revoke credential hoặc device key tương ứng.
- Đổi password hoặc re-enroll MFA nếu có dấu hiệu compromise.
- Kiểm tra hoạt động gần đây.
- Nhận thông báo về các thay đổi.

Revoke session không nhất thiết revoke passkey đồng bộ trên mọi thiết bị. Cần giải thích khác biệt giữa session, credential và device key. Nếu tài khoản có nguy cơ bị takeover, có thể cần revoke nhiều session/token family và yêu cầu xác thực lại.

## 13. Quyền riêng tư và quản lý dữ liệu thiết bị

Device enrollment có thể thu thập metadata về phần cứng, OS, browser, vị trí hoặc network. Thu thập quá mức làm tăng rủi ro privacy mà không chắc cải thiện security.

Nguyên tắc:
- Thu thập tối thiểu để xác minh, hỗ trợ và quản lý credential.
- Dùng internal device/credential reference thay vì hardware identifier không cần thiết.
- Không dùng IMEI, advertising ID hoặc serial number làm secret hay yếu tố xác thực.
- Giải thích dữ liệu nào được tổ chức quản lý nếu thiết bị thuộc doanh nghiệp.
- Phân biệt device metadata và nội dung cá nhân trên thiết bị.
- Có retention và deletion policy.
- Cho người dùng xem, sửa nhãn và thu hồi thiết bị khi policy cho phép.
- Không tạo fingerprint dài hạn bí mật mà không có cơ sở và thông báo phù hợp.

Nếu doanh nghiệp yêu cầu MDM compliance, UI cần nói rõ điều kiện nào được kiểm tra, dữ liệu nào được gửi tới tổ chức và điều gì xảy ra nếu thiết bị không compliant. Không tuyên bố tổ chức chỉ nhìn thấy trạng thái compliance nếu MDM thực tế có quyền quản lý rộng hơn; mô tả đúng phạm vi theo cấu hình.

## 14. Multi-account, multi-device và household/shared device

Một thiết bị có thể được dùng cho nhiều tài khoản, đặc biệt là máy tính gia đình hoặc thiết bị dùng chung. Enrollment cần ràng buộc credential đúng subject và tenant:
- Mỗi enrollment transaction gắn account/tenant cụ thể.
- Không tái sử dụng challenge giữa hai tài khoản.
- UI hiển thị rõ tài khoản đang được thêm thiết bị.
- Logout hoặc account switch không để transaction cũ commit vào account mới.
- Device list không tiết lộ thông tin tài khoản khác cho người dùng không có quyền.
- Shared device cần cảnh báo về việc credential có thể được lưu trong profile/OS account hiện tại.
- Tổ chức có thể giới hạn enrollment theo device compliance hoặc managed profile.

Không suy ra người dùng sở hữu thiết bị chỉ vì họ có thể mở browser trên thiết bị đó. Với thiết bị dùng chung, cần khuyến nghị profile OS riêng, khóa màn hình và không lưu credential vào profile không kiểm soát.

## 15. Accessibility và hỗ trợ người dùng

Enrollment thường kết hợp browser prompt, OS dialog, camera/QR, keyboard, NFC hoặc biometric. Hướng dẫn phải hoạt động cho nhiều cách tương tác.

Kiểm tra:
- Label và hướng dẫn có accessible name/description.
- Keyboard navigation tới từng bước và focus được phục hồi sau OS dialog.
- Screen reader đọc được trạng thái pending/success/failure.
- Không dùng màu sắc hoặc icon đơn lẻ để biểu diễn trạng thái.
- Có phương án nhập setup key thay QR nếu người dùng không thể quét.
- Có hướng dẫn security key cho người không dùng touch/biometric.
- Text zoom và responsive layout không che mã hoặc nút.
- Localization không làm sai thứ tự ký tự/OTP hoặc hướng dẫn domain.
- Thông báo lỗi nêu bước tiếp theo, không chỉ “Something went wrong”.
- Có hỗ trợ khi OS prompt bị hủy hoặc browser không hỗ trợ.

Không tự động chuyển người dùng sang factor yếu hơn vì một thiết bị hỗ trợ accessibility không đáp ứng. Hãy cung cấp phương thức thay thế có assurance phù hợp và đã được enroll.

## 16. Error handling và UX khi enrollment thất bại

Thông báo lỗi nên phân biệt lỗi người dùng có thể sửa, lỗi tạm thời và lỗi policy/security.

| Tình huống | UX phù hợp | Xử lý backend |
| --- | --- | --- |
| User cancel authenticator prompt | Nêu enrollment chưa hoàn tất, cho phép thử lại | Hủy hoặc giữ transaction pending theo TTL. |
| Browser không hỗ trợ | Nêu capability cần thiết và phương thức thay thế đã enroll | Không tạo credential. |
| Challenge expired | Yêu cầu bắt đầu transaction mới | Vô hiệu challenge cũ. |
| Network timeout | Cho phép kiểm tra trạng thái trước khi retry | Tra cứu transaction/commit status, tránh duplicate. |
| Credential đã tồn tại | Nêu credential đã được thêm hoặc gợi ý quản lý danh sách | Idempotent response hoặc conflict có kiểm soát. |
| Step-up thất bại | Dừng enrollment và hướng dẫn dùng factor hiện có | Không tạo/commit credential. |
| Rate limit | Nêu thời gian có thể thử lại nếu phù hợp | Enforce server-side cooldown. |
| Device policy không compliant | Giải thích yêu cầu tổ chức và kênh hỗ trợ | Không bypass compliance policy. |
| Storage/provider error | Nêu trạng thái chưa xác định nếu commit có thể đã xảy ra | Reconcile transaction với store. |
| Enrollment bị risk engine chặn | Thông báo chung, hướng dẫn kênh hỗ trợ an toàn | Ghi reason code nội bộ, tránh lộ detection logic. |

Không hiển thị stack trace, token, seed hoặc chi tiết risk rule. Nếu backend đã lưu credential nhưng client không nhận response, UI nên hiển thị trạng thái đã kiểm tra từ server. Nếu chưa rõ, nói “Đang kiểm tra trạng thái” thay vì báo thất bại và khuyến khích thử lại liên tục.

## 17. Pseudocode enrollment coordinator

Pseudocode dưới đây mô tả nguyên tắc chung; triển khai thật cần dùng API và SDK chuẩn của authenticator/IdP.

~~~text
startEnrollment(account, authenticatorType, currentSession):
    requireAuthenticatedSession(currentSession)
    requireAccountMayManageCredentials(account)
    requireRecentStepUpIfPolicyNeedsIt()

    transaction = createEnrollmentTransaction(
        subject = account.id,
        type = authenticatorType,
        challenge = secureRandom(),
        expiresAt = now + shortEnrollmentTTL,
        sessionRef = currentSession.reference
    )

    emitAudit("credential.enrollment.started", transaction.reference)
    return transaction.publicOptions

completeEnrollment(transactionId, response):
    tx = loadPendingTransaction(transactionId)
    requireNotExpired(tx)
    requireSameSubjectAndSession(tx)
    requireChallengeUnused(tx)

    proof = verifyAuthenticatorResponse(
        type = tx.authenticatorType,
        response = response,
        challenge = tx.challenge,
        origin = configuredOrigin,
        relyingParty = configuredRelyingParty
    )

    requireProofValid(proof)
    credential = persistCredentialAtomically(
        subject = tx.subject,
        type = tx.authenticatorType,
        publicMaterial = proof.publicMaterial,
        metadata = minimalApprovedMetadata
    )

    markTransactionCompleted(tx.id)
    emitAudit("credential.enrollment.completed", credential.reference)
    notifyPreviouslyVerifiedChannel(tx.subject, credential.reference)
    return safeCredentialSummary(credential)

revokeCredential(subject, credentialRef, session):
    requireAuthenticatedSession(session)
    requireRecentStepUpIfPolicyNeedsIt()
    requireCredentialBelongsTo(subject, credentialRef)

    revokeCredentialAtomically(credentialRef)
    invalidateRelatedSessionsOrBindingsByPolicy(credentialRef)
    emitAudit("credential.revoked", credentialRef)
    notifyOtherVerifiedChannels(subject, credentialRef)
~~~

Các bất biến cần giữ:
- Challenge đủ ngẫu nhiên, gắn transaction và chỉ dùng một lần.
- Transaction không thể đổi subject hoặc authenticator type giữa chừng.
- Proof được xác minh server-side trước khi Active.
- Commit credential và transaction completion có semantics nguyên tử/idempotent.
- Response không chứa private key hoặc raw shared secret ngoài trường hợp provisioning cần hiển thị một lần.
- Audit event không chứa secret.
- Logout/revoke có ưu tiên cao hơn response enrollment đến muộn.

## 18. Bài thực hành: thiết kế Device enrollment experience cho StudyHub

**Bối cảnh:** StudyHub có web app và mobile app. Người dùng có thể đăng nhập bằng password, passkey hoặc TOTP. Giảng viên và quản trị viên phải có MFA. Người dùng có thể đăng nhập trên nhiều thiết bị; passkey có thể được đồng bộ qua hệ sinh thái của nhà cung cấp. Một số tổ chức dùng thiết bị được quản lý. Hỗ trợ khách hàng nhận yêu cầu khi người dùng mất điện thoại hoặc security key.

Hãy thiết kế trải nghiệm thêm và quản lý thiết bị đáp ứng:

1. Người dùng hiểu đang thêm device, passkey, TOTP hay push authenticator.
2. Enrollment yêu cầu session hợp lệ và step-up theo risk/policy.
3. Challenge được gắn với account, transaction và origin đúng.
4. Không thể enroll credential vào account khác khi đổi tab hoặc switch account.
5. UI giải thích dữ liệu nào được lưu và passkey có thể đồng bộ hay không.
6. TOTP seed/QR không bị log hoặc lưu ngoài flow enrollment.
7. Push enrollment xác minh device key/installation theo protocol và permission notification không bị coi là proof.
8. Người dùng có thể đặt tên, xem trạng thái và lần sử dụng gần nhất khi có dữ liệu.
9. Có thể đăng ký phương thức dự phòng để tránh lockout.
10. Logout/account switch hủy transaction pending theo policy.
11. Người dùng còn thiết bị cũ có thể thêm và xác minh thiết bị mới trước khi revoke cũ.
12. Người mất mọi thiết bị đi qua account recovery có assurance phù hợp.
13. Người dùng có thể revoke session/device credential theo phạm vi rõ.
14. Notification được gửi qua kênh đã xác minh và không chứa secret.
15. Accessibility, localization và browser/OS capability được hỗ trợ.
16. Backend chống replay, duplicate commit, timeout ambiguity và enrollment takeover.

### 18.1. Quyết định thiết kế cần ghi lại

- Các loại device/authenticator được hỗ trợ.
- Khác biệt giữa device recognition, device binding và authenticator enrollment.
- Step-up policy và freshness requirement.
- Challenge format, transaction ID, expiry và idempotency.
- WebAuthn RP ID/origin/attestation policy.
- TOTP provisioning, verification và seed encryption.
- Push device key, notification permission và number matching.
- Device metadata, privacy notice và retention.
- State machine, pending cleanup và revoke semantics.
- Multi-account/multi-device behavior.
- Recovery và lost-device runbook.
- Audit event, notification và support escalation.
- Accessibility và browser/OS compatibility.

### 18.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Session còn mới và step-up hợp lệ | Enrollment transaction được tạo cho đúng account. |
| Session quá cũ | Yêu cầu re-authentication/step-up theo policy. |
| CSRF token hoặc origin không hợp lệ | Enrollment request bị từ chối. |
| Challenge bị replay | Server từ chối và không tạo credential thứ hai. |
| Challenge hết hạn | Transaction bị đóng; cần bắt đầu mới. |
| User cancel OS prompt | Không có credential Active; UI cho phép thử lại. |
| Passkey origin/RP ID sai | Server từ chối response. |
| Passkey provider đồng bộ | UI không tuyên bố credential chỉ tồn tại trên một thiết bị. |
| TOTP seed/QR xuất hiện trong log | Security test thất bại. |
| TOTP mã sai hoặc hết hạn | Factor chưa được kích hoạt. |
| Push notification permission bị từ chối | Không tự động bỏ MFA; hiển thị phương thức thay thế hợp lệ. |
| Push approval từ transaction khác | Server từ chối. |
| Hai tab cùng commit một transaction | Chỉ một commit có hiệu lực. |
| Account switch giữa enrollment | Transaction cũ không thể commit vào account mới. |
| Network timeout sau khi server commit | UI kiểm tra trạng thái; không tạo credential trùng. |
| Server commit nhưng response bị mất | Credential được hiển thị qua readback trạng thái server. |
| Notification provider outage | Enrollment vẫn có audit; notification pending được retry theo policy. |
| Device bị đánh dấu non-compliant | Enrollment bị chặn hoặc yêu cầu remediation theo policy. |
| Device bị mất | Session/key/credential được revoke theo phạm vi đã chọn. |
| Revoke một device session | Các thiết bị khác không bị ảnh hưởng ngoài policy. |
| Revoke passkey server-side | Assertion tiếp theo từ credential đó bị từ chối tại dịch vụ. |
| Recovery không đủ proof | Không thêm credential mới hoặc thay recovery factor. |
| Recovery thành công | Event, notification và session review được thực hiện theo policy. |
| User không dùng được QR | Có phương án setup thủ công an toàn nếu được hỗ trợ. |
| Screen reader/keyboard | Có thể hoàn tất hoặc hủy flow và hiểu trạng thái. |
| Enrollment response đến sau logout | Response muộn không kích hoạt credential/session. |
| Audit event | Có actor, subject, credential reference, outcome; không có raw secret. |
| Device label chứa markup/control characters | Được sanitize và không ảnh hưởng authorization. |
| Một thiết bị dùng nhiều account | Credential và transaction tách biệt theo account/tenant. |

### 18.3. Câu hỏi tự đánh giá

1. Device enrollment khác authenticator enrollment và device recognition như thế nào?
2. Vì sao thêm passkey hoặc MFA factor là hành động nhạy cảm?
3. Khi nào cần re-authentication hoặc step-up trước enrollment?
4. Transaction binding ngăn việc tái sử dụng proof ra sao?
5. Vì sao device fingerprint không phải bằng chứng possession?
6. Passkey private key được giữ ở đâu và server lưu gì?
7. Vì sao UI cần nói rõ passkey có thể đồng bộ qua provider?
8. TOTP QR/provisioning URI cần được bảo vệ thế nào?
9. Notification permission có chứng minh người dùng kiểm soát authenticator không?
10. Xử lý thế nào khi server commit credential nhưng browser không nhận response?
11. Vì sao không nên xóa thiết bị cũ trước khi thiết bị mới được xác minh?
12. Khi mất mọi factor, recovery cần bảo đảm điều gì?
13. Revoke session khác revoke authenticator credential ra sao?
14. Làm thế nào để nhiều tab hoặc account switch không trộn enrollment transaction?

**Tiêu chí hoàn thành:** Người học có thể thiết kế luồng enrollment rõ ràng và dễ hiểu, xác minh đúng chủ tài khoản, ràng buộc challenge với transaction, bảo vệ credential, mô tả chính xác quyền riêng tư và đồng bộ, đồng thời xử lý multi-device, lost-device, recovery và revoke mà không tạo đường bypass authentication.

## 19. Các lỗi thiết kế phổ biến

- **Gọi device recognition là xác thực:** tín hiệu nhận diện không chứng minh possession hoặc danh tính.
- **Cho phép enroll chỉ vì session còn cookie:** attacker chiếm session có thể thêm factor của họ.
- **Không yêu cầu step-up cho hành động nhạy cảm:** enrollment takeover dễ duy trì quyền truy cập.
- **Challenge không gắn transaction/account:** proof có thể bị dùng nhầm hoặc replay.
- **Kích hoạt credential trước server verification:** UI có thể báo thành công trong khi proof chưa hợp lệ.
- **Không xử lý timeout ambiguity:** retry có thể tạo credential trùng hoặc commit sai trạng thái.
- **Mô tả sai về passkey sync:** người dùng hiểu nhầm credential chỉ ở một thiết bị.
- **Lưu TOTP seed/QR trong log:** lộ shared secret cho người có quyền đọc telemetry.
- **Coi notification permission là authenticator proof:** permission chỉ cho phép gửi thông báo.
- **Không cung cấp factor dự phòng:** người dùng dễ bị lockout khi mất thiết bị.
- **Xóa thiết bị cũ quá sớm:** người dùng mất đường đăng nhập trước khi thiết bị mới hoạt động.
- **Revoke session nhưng không revoke credential bị lộ:** attacker có thể tạo session mới.
- **Revoke credential nhưng không giải thích phạm vi:** người dùng tưởng mọi bản sao trên provider đã bị xóa.
- **Dùng device fingerprint làm secret:** tín hiệu có thể bị giả mạo và gây vấn đề privacy.
- **Tên thiết bị được dùng trong policy:** nhãn người dùng nhập không phải bằng chứng bảo mật.
- **Enrollment không hỗ trợ accessibility:** người dùng bị đẩy sang recovery yếu hơn.
- **Thông báo không qua kênh đã xác minh:** attacker có thể thay đổi contact trước khi nhận cảnh báo.
- **Không audit factor change:** không thể điều tra ai đã thêm hoặc gỡ authenticator.

## 20. Vận hành và cải tiến trải nghiệm

Đo lường enrollment cần cân bằng completion và security:
- Tỷ lệ bắt đầu và hoàn tất theo loại authenticator.
- Tỷ lệ hủy ở từng bước và reason code.
- Thời gian hoàn tất và số lần thử lại.
- Tỷ lệ challenge hết hạn hoặc response không hợp lệ.
- Tỷ lệ step-up failure và recovery escalation.
- Tỷ lệ enrollment bị risk policy chặn.
- Tỷ lệ credential được dùng lần đầu và lần gần nhất.
- Tỷ lệ người dùng có phương thức dự phòng.
- Số báo cáo enrollment không nhận ra hoặc account takeover.
- Tỷ lệ notification delivery và thời gian gửi.
- Tỷ lệ lỗi theo browser/OS/device class và accessibility mode.

Không tối ưu completion rate bằng cách bỏ step-up hoặc giảm yêu cầu proof. Một enrollment có tỷ lệ hoàn tất thấp có thể do UX khó hiểu, browser không hỗ trợ, authenticator prompt bị hủy hoặc policy đúng đang chặn hành vi rủi ro. Phân tích theo reason code và test usability trước khi thay đổi control.

Khi có báo cáo enrollment trái phép:
1. Xác định credential/device reference và transaction.
2. Thu hồi credential và session liên quan theo policy.
3. Kiểm tra authentication, recovery và admin event trước/sau enrollment.
4. Xác minh contact channel và session nào còn tin cậy.
5. Hỗ trợ người dùng khôi phục bằng quy trình đã xác minh.
6. Kiểm tra transaction binding, step-up freshness, CSRF và notification.
7. Giữ audit evidence, không ghi thêm secret trong ticket.
8. Theo dõi xem credential cũ còn được chấp nhận ở mọi region/cache hay không.

## 21. Tài liệu tham khảo và hướng đọc tiếp

- **W3C Web Authentication (WebAuthn):** credential creation, assertion, origin, RP ID và authenticator.
- **FIDO Alliance — Passkeys:** mô hình passkey, synced credential và user experience.
- **NIST SP 800-63B — Digital Identity Guidelines:** authenticator enrollment, binding, lifecycle và recovery.
- **OWASP Authentication Cheat Sheet:** re-authentication, MFA và account management.
- **OWASP Forgot Password Cheat Sheet:** recovery flow và xác minh chủ tài khoản.
- **OWASP Session Management Cheat Sheet:** session lifecycle, rotation và revocation.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với khóa.
- **Apple Platform Security / passkeys documentation:** Keychain, passkey và authenticator integration.
- **Android Credential Manager documentation:** passkey và credential selection trên Android.
- **WCAG 2.2:** accessibility cho form, focus, status message và authentication.
- **OWASP Application Security Verification Standard (ASVS):** kiểm soát authentication, session và access control.

Khi triển khai, cần đối chiếu phiên bản tiêu chuẩn và API nền tảng hiện hành. Passkey sync, attestation, device compliance và notification behavior phụ thuộc hệ sinh thái cụ thể. Chính sách enrollment cần được kiểm thử trên browser/OS thật, có threat model, privacy review và quy trình recovery được phê duyệt.

**Kết luận:** Device enrollment experience là một phần của vòng đời xác thực, không chỉ là màn hình thêm thiết bị. Trải nghiệm tốt giải thích rõ loại credential và quyền của nó, xác minh người dùng bằng step-up phù hợp, ràng buộc proof với đúng transaction/account, bảo vệ dữ liệu và thông báo thay đổi. Quản lý nhiều thiết bị cần hỗ trợ đặt tên, kiểm tra trạng thái, thu hồi và khôi phục khi mất thiết bị. Mọi đường đi phải giữ nguyên assurance và không biến sự tiện lợi thành bypass authentication.
