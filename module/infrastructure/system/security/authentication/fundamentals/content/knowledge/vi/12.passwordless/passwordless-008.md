# Đánh giá passwordless

## 1. Passwordless là gì và cần đánh giá điều gì?

**Passwordless authentication** (xác thực không mật khẩu) là cách xác thực người dùng mà họ không phải nhập mật khẩu dùng chung với máy chủ trong mỗi lần đăng nhập. Thay vào đó, hệ thống có thể dựa vào khóa mật mã trong authenticator, xác nhận trên thiết bị, chứng chỉ, liên kết đăng nhập một lần hoặc một phương thức khác được liên kết với tài khoản.

Passwordless không phải một giao thức duy nhất và cũng không tự động đồng nghĩa với **phishing-resistant**, **MFA** hay mức đảm bảo cao. Một liên kết đăng nhập gửi qua email có thể không cần mật khẩu nhưng vẫn phụ thuộc vào bảo mật hộp thư; mã OTP qua SMS cũng là passwordless nhưng có thể bị phishing hoặc chuyển tiếp. Ngược lại, WebAuthn/passkey có ràng buộc với relying party và origin, nên có khả năng chống phishing mạnh khi verifier triển khai đúng.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, đánh giá passwordless phải đặt trong toàn bộ vòng đời danh tính: enrollment, credential, xác thực, session/token, liên kết IdP, thay thiết bị và recovery. Mục tiêu là chọn phương thức phù hợp với rủi ro, khả năng tiếp cận, trải nghiệm người dùng và năng lực vận hành; đồng thời phòng phishing, replay và lạm dụng đăng nhập.

Sau bài học, người học có thể:

- Phân biệt passwordless với MFA và phishing-resistant authentication.
- Đánh giá các phương thức như passkey, magic link, OTP, push và chứng chỉ.
- Xác định các ranh giới tin cậy trong đăng ký, đăng nhập, đồng bộ khóa và khôi phục.
- So sánh bảo mật, trải nghiệm, khả năng tương thích và chi phí vận hành.
- Lập kế hoạch chuyển đổi passwordless có fallback và recovery an toàn.
- Định nghĩa chỉ số để đo chất lượng triển khai thay vì chỉ đếm số người đã bật passkey.

## 2. Passwordless không phải một mức bảo đảm

Có ít nhất ba khái niệm cần tách biệt:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Passwordless** | Người dùng có phải nhập password để xác thực không? | Passkey, magic link, email OTP, client certificate |
| **MFA** | Flow đã xác minh các yếu tố độc lập theo policy chưa? | Khóa trên thiết bị + user verification bằng PIN/sinh trắc cục bộ, nếu đáp ứng yêu cầu |
| **Phishing-resistant** | Bằng chứng có được ràng buộc với đúng relying party/origin để khó bị chuyển tiếp sang trang giả không? | WebAuthn/FIDO2 được xác minh đúng origin và RP ID |

Một phương thức có thể passwordless nhưng không chống phishing. Một phương thức có thể chống phishing nhưng việc có đáp ứng MFA hay mức assurance nào còn phụ thuộc ceremony, loại authenticator, user verification, enrollment và tiêu chuẩn áp dụng.

Ví dụ:

- **Email magic link:** người dùng bấm link để đăng nhập, không nhập password. Kẻ tấn công kiểm soát hộp thư hoặc chuyển tiếp link có thể chiếm flow.
- **SMS OTP:** không cần password, nhưng mã có thể bị lừa nhập vào trang phishing, chuyển tiếp hoặc bị chiếm kênh qua SIM swap.
- **Passkey:** dùng khóa mật mã gắn với relying party. Nếu kiểm tra WebAuthn đúng, assertion được ràng buộc với challenge và origin; khả năng chống phishing tốt hơn OTP.
- **Client certificate:** có thể xác thực thiết bị hoặc workload bằng proof of possession khóa riêng; không mặc nhiên chứng minh danh tính con người hoặc quyền truy cập.

Vì vậy, câu hỏi đánh giá không phải chỉ là “có bỏ mật khẩu chưa?”, mà là **“bằng chứng nào được xác minh, ràng buộc với ai và bên nhận nào, ở mức tin cậy nào, và đường recovery có yếu hơn không?”**

## 3. Các phương thức passwordless thường gặp

| Phương thức | Bằng chứng được kiểm tra | Điểm mạnh | Rủi ro / giới hạn |
| --- | --- | --- | --- |
| **Passkey/WebAuthn** | Chữ ký trên challenge bằng khóa đã đăng ký; kiểm tra RP ID, origin và cờ authenticator | Chống phishing theo origin; không gửi shared secret tới server; hỗ trợ UX tốt | Cần hỗ trợ nền tảng, đồng bộ hoặc chuyển thiết bị; recovery và enrollment phải an toàn |
| **Security key FIDO2** | Chữ ký từ khóa bảo mật vật lý | Có thể dùng khóa chuyên dụng, thường phù hợp tài khoản rủi ro cao; chống phishing | Mất thiết bị, chi phí phân phối, dự phòng khóa và khả năng tương thích |
| **Email magic link** | Token/link ngẫu nhiên gửi tới mailbox | Dễ triển khai, ít thao tác, không cần password | Phụ thuộc email; link bị forward, lộ qua log/Referer, phishing mailbox, delay và deliverability |
| **Email OTP** | Mã ngắn gửi qua email | Dễ dùng trên thiết bị khác với email | Mã dễ bị phishing/relay; email account takeover trở thành đường đăng nhập |
| **SMS/voice OTP** | Mã gửi qua số điện thoại | Phổ biến, không cần app riêng | SIM swap, chuyển số, interception/relay, phụ thuộc nhà mạng và vùng phủ |
| **Push approval** | Người dùng phê duyệt trên thiết bị đã đăng ký | Trải nghiệm nhanh, có thể hiển thị ngữ cảnh | MFA fatigue, approve nhầm, push relay, thiết bị bị chiếm; không chống phishing mặc định |
| **Client certificate/mTLS** | Proof of possession private key gắn với certificate | Phù hợp service-to-service hoặc thiết bị được quản lý | PKI, provisioning, rotation, revocation; không nhất thiết xác thực người dùng cuối |
| **Device-bound key / platform authenticator** | Chữ ký từ khóa gắn với thiết bị hoặc vùng bảo mật | Có thể giảm khả năng sao chép khóa | Mất/hỏng thiết bị, phụ thuộc nền tảng, cần quy trình thay thế |

Bảng này so sánh đặc tính điển hình, không gán AAL tự động. Cấu hình, giao thức, verifier, chính sách và cách khôi phục có thể làm thay đổi mức bảo đảm thực tế.

## 4. Passkey và WebAuthn: tiêu chí đánh giá chính

Passkey là credential dựa trên cặp khóa công khai/riêng. Relying party lưu public key và thông tin credential; authenticator giữ private key. Khi đăng nhập, server phát challenge, authenticator ký dữ liệu liên quan, rồi server xác minh response.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / OS
    participant A as Authenticator
    participant S as Relying Party Server
    U->>S: Bắt đầu đăng nhập
    S-->>B: Challenge và thông tin RP
    B->>A: Yêu cầu xác thực
    A-->>U: User verification / consent nếu cần
    A-->>B: Assertion đã ký
    B->>S: Assertion
    S->>S: Kiểm tra challenge, origin, RP ID, chữ ký, UP/UV
    S-->>B: Kết quả và session nếu policy đạt
~~~

Các tiêu chí phải kiểm tra:

1. **Challenge:** do server tạo ngẫu nhiên, có thời hạn, gắn với flow và chỉ được chấp nhận theo quy tắc một lần.
2. **Origin:** server xác minh client data origin nằm trong danh sách được phép. Không chấp nhận origin do client tự khai trong trường khác.
3. **RP ID:** xác minh RP ID hash phù hợp relying party dự kiến.
4. **Chữ ký:** dùng public key đã đăng ký cho credential tương ứng; kiểm tra đúng thuật toán và dữ liệu ký.
5. **User Presence (UP):** bằng chứng người dùng hiện diện/tương tác, khi policy yêu cầu.
6. **User Verification (UV):** bằng chứng authenticator đã xác minh người dùng tại thiết bị theo cấu hình; không suy từ popup UI hoặc lời khai client.
7. **Credential binding:** credential được gắn với đúng principal qua enrollment flow đã xác thực.
8. **Trạng thái credential:** xử lý credential bị thu hồi, xóa, thay thế hoặc không còn thuộc quyền kiểm soát.
9. **Chính sách backup/sync:** hiểu khóa có thể được đồng bộ, sao lưu hoặc sử dụng trên nhiều thiết bị như thế nào.

**Không được chỉ decode response rồi tin.** Server phải xác minh toàn bộ dữ liệu WebAuthn cần thiết. Việc kiểm tra chữ ký mà bỏ qua challenge, origin hoặc RP ID làm mất các ràng buộc quan trọng của giao thức.

### 4.1. Passkey đồng bộ và passkey gắn thiết bị

Hai cách quản lý khóa có trade-off khác nhau:

| Thuộc tính | Passkey có thể đồng bộ | Credential gắn thiết bị |
| --- | --- | --- |
| Khả năng dùng nhiều thiết bị | Thuận tiện khi hệ sinh thái hỗ trợ đồng bộ | Thường cần đăng ký credential trên từng thiết bị |
| Khả năng phục hồi khi mất thiết bị | Có thể khôi phục qua tài khoản đồng bộ theo chính sách nhà cung cấp | Cần authenticator dự phòng hoặc recovery flow riêng |
| Ranh giới tin cậy | Bao gồm nhà cung cấp và tài khoản đồng bộ | Tập trung vào thiết bị/phần cứng giữ khóa |
| Khả năng kiểm soát khóa | Phụ thuộc cách đồng bộ, mã hóa và bảo vệ tài khoản đồng bộ | Có thể hạn chế xuất khóa nếu nền tảng hỗ trợ |
| Phù hợp | Người dùng phổ thông cần tiện lợi và nhiều thiết bị | Môi trường quản lý thiết bị hoặc yêu cầu khóa gắn phần cứng cụ thể |

Không nên mặc định “đồng bộ” là không an toàn hoặc “gắn thiết bị” là không thể bị xâm phạm. Cần đánh giá mô hình bảo vệ khóa, account recovery của nhà cung cấp, thiết bị đầu cuối và yêu cầu assurance. Nếu policy bắt buộc khóa không xuất khỏi phần cứng, phải kiểm tra đúng bằng chứng kỹ thuật và tiêu chuẩn thay vì chỉ dựa vào tên passkey.

### 4.2. Attestation và quyền riêng tư

WebAuthn có thể cung cấp attestation trong một số cấu hình để relying party đánh giá nguồn gốc hoặc loại authenticator. Attestation có thể hữu ích trong môi trường quản lý thiết bị, nhưng cũng có hệ quả quyền riêng tư và khả năng liên kết người dùng qua thiết bị. Chỉ yêu cầu và lưu attestation khi có nhu cầu rõ ràng; xác định loại attestation chấp nhận, chính sách trust anchor, cập nhật metadata và cách xử lý khi không có attestation.

## 5. Đánh giá magic link và OTP

Magic link và OTP là passwordless dễ triển khai, nhưng thường có bảo đảm thấp hơn passkey trước phishing.

### 5.1. Magic link

Một magic link nên chứa token ngẫu nhiên đủ mạnh, gắn với tài khoản, mục đích, flow và thời hạn. Server nên lưu verifier/hash của token thay vì giá trị dùng trực tiếp nếu thiết kế cho phép, tiêu thụ token một lần và thu hồi các link cũ khi cần.

Các rủi ro:

- Email bị chiếm quyền hoặc được mở trên thiết bị không đáng tin.
- Link bị chuyển tiếp cho người khác.
- Token xuất hiện trong log, browser history, analytics hoặc Referer.
- Scanner bảo mật của email tự động mở link, vô tình tiêu thụ token.
- Token được gửi tới sai redirect URI hoặc bị dùng trong flow khác.
- Người dùng mở link trên thiết bị khác, khiến binding phiên và trải nghiệm phức tạp.

Biện pháp giảm rủi ro gồm TTL ngắn phù hợp, token dùng một lần, ràng buộc flow, không chuyển tiếp token sang bên thứ ba, hạn chế tài nguyên ngoài ở trang callback, và thiết kế xử lý email scanner cẩn thận. Không nên để việc “mở GET link” tự động thực hiện hành động nhạy cảm mà không có xác nhận/kiểm soát bổ sung.

### 5.2. Email/SMS OTP

Mã OTP cần entropy đủ, TTL, giới hạn số lần thử, giới hạn gửi lại và chống replay. Server cần gắn mã với đúng principal, flow và mục đích. Mã ngắn có không gian đoán hữu hạn, do đó rate limiting là bắt buộc.

OTP qua email hoặc SMS **không chống phishing theo origin**. Người dùng có thể nhập mã vào trang giả; kẻ tấn công chuyển tiếp tới server thật trước khi mã hết hạn. SMS còn phụ thuộc an toàn số điện thoại và nhà mạng. Nếu dùng OTP như phương thức dự phòng, cần đánh giá rằng đường dự phòng có thể trở thành đường yếu nhất của tài khoản.

## 6. Push authentication và xác nhận trên thiết bị

Push approval cho phép server gửi yêu cầu tới ứng dụng đã đăng ký. Người dùng xác nhận hoặc từ chối. Thiết kế có thể thuận tiện, nhưng cần phân biệt “đã nhấn approve” với “đã chứng minh đúng giao dịch”.

Các câu hỏi đánh giá:

- Push được ràng buộc với flow đăng nhập và challenge nào?
- Người dùng thấy thông tin gì: vị trí gần đúng, thiết bị, ứng dụng, thời điểm hay hành động?
- Có number matching hoặc xác nhận một giá trị từ phiên đăng nhập không?
- Server giới hạn số push, chống spam và xử lý approve trùng lặp ra sao?
- Có thể bị relay qua thiết bị bị chiếm hoặc push fatigue không?
- Phản hồi approve có chữ ký hoặc ràng buộc với thiết bị/khóa đã đăng ký không?

Number matching giúp người dùng liên kết yêu cầu trên màn hình đăng nhập với thông báo trên thiết bị, giảm nguy cơ nhấn nhầm. Tuy nhiên, nó không tự tạo ra ràng buộc origin mạnh như WebAuthn và không nên được mô tả như bảo đảm chống phishing tuyệt đối.

## 7. Chứng chỉ và khóa thiết bị

Trong môi trường doanh nghiệp hoặc service-to-service, passwordless có thể dựa vào certificate và private key:

- **mTLS:** hai bên xác thực certificate trong TLS handshake; bên xác minh kiểm tra chain, thời hạn, mục đích sử dụng, subject/SAN và proof of possession.
- **Client certificate:** trình duyệt hoặc thiết bị sử dụng khóa riêng để xác thực với server.
- **Workload identity:** workload nhận credential ngắn hạn từ hệ thống cấp phát và dùng để xác thực với dịch vụ khác.

Ưu điểm là giảm việc nhập mật khẩu và có thể tự động hóa vòng đời credential. Đổi lại, tổ chức cần PKI hoặc hệ cấp phát danh tính workload, quản lý private key, rotation, thu hồi, trust anchor, inventory và phản ứng khi thiết bị bị mất.

Một certificate hợp lệ **không tự cấp quyền**. Server phải ánh xạ danh tính được xác minh sang principal và áp dụng authorization. Cũng cần phân biệt danh tính thiết bị/service với danh tính con người đang ngồi trước thiết bị.

## 8. Ma trận đánh giá passwordless

Không nên chọn phương thức chỉ vì demo nhanh hoặc giảm số lần nhập mật khẩu. Dùng ma trận để đánh giá theo yêu cầu sản phẩm:

| Tiêu chí | Câu hỏi đánh giá | Bằng chứng hoặc phép đo |
| --- | --- | --- |
| **Phishing resistance** | Bằng chứng có ràng buộc với đúng relying party/origin không? | Kiểm thử trang giả, relay OTP, sai origin/RP ID |
| **Replay resistance** | Token/challenge có dùng lại được không? | Thử gửi lại assertion, OTP, magic link đã tiêu thụ |
| **Authenticator binding** | Credential có gắn đúng principal không? | Kiểm tra enrollment, account linking, thay credential |
| **Key protection** | Private key được lưu, xuất hoặc đồng bộ ra sao? | Tài liệu nền tảng, policy, attestation khi phù hợp |
| **User verification** | Có xác minh người dùng tại authenticator theo policy không? | UP/UV flags và kết quả verifier |
| **Recovery** | Mất thiết bị thì khôi phục bằng cách nào? | Threat model và thử nghiệm takeover qua recovery |
| **Cross-device UX** | Đăng nhập từ thiết bị mới có rõ ràng và an toàn? | Tỷ lệ hoàn tất, lỗi, thời gian, hỗ trợ |
| **Compatibility** | Hỗ trợ browser, OS, thiết bị và môi trường doanh nghiệp nào? | Ma trận thiết bị thực tế, fallback |
| **Privacy** | Thu thập attestation, telemetry hay dữ liệu cá nhân nào? | Data inventory, retention, access control |
| **Operations** | Enrollment, revoke, rotation, support có vận hành được? | Quy trình, audit, SLA và chi phí hỗ trợ |
| **Accessibility** | Người dùng có thể dùng phương thức thay thế phù hợp? | Kiểm thử với công nghệ hỗ trợ và trường hợp thiết bị mất |
| **Assurance/compliance** | Phương thức và flow đáp ứng chuẩn/chính sách nào? | Mapping tới phiên bản tiêu chuẩn và bằng chứng kiểm toán |

Có thể chấm điểm nội bộ (ví dụ 1–5) để so sánh lựa chọn, nhưng phải định nghĩa rõ điểm số và trọng số. Không biến một điểm tổng hợp thành AAL/IAL chính thức; các mức assurance cần được xác định theo tiêu chuẩn tương ứng.

## 9. Threat model: passwordless vẫn có thể bị tấn công

| Mối đe dọa | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Phishing** | Trang giả lừa nhập OTP hoặc chuyển tiếp magic link | WebAuthn/passkey cho flow cần chống phishing; domain/origin validation |
| **Replay** | Dùng lại link, OTP hoặc challenge response | Token ngẫu nhiên, TTL, one-time use, challenge binding và verifier |
| **Mailbox takeover** | Kẻ tấn công kiểm soát email nhận magic link | Không coi email là yếu tố mạnh mặc định; bảo vệ recovery mailbox, step-up |
| **SIM swap** | Chiếm số điện thoại nhận OTP | Hạn chế SMS cho tác vụ rủi ro cao; phương thức thay thế mạnh hơn |
| **Push fatigue** | Spam yêu cầu approve để người dùng nhấn nhầm | Rate limit, number matching, ngữ cảnh, báo cáo và khóa flow |
| **Enrollment takeover** | Kẻ tấn công đã chiếm phiên thêm passkey của mình | Reauthentication, step-up, thông báo kênh cũ và audit |
| **Sync account takeover** | Tài khoản đồng bộ passkey bị chiếm | Đánh giá bảo vệ account sync, MFA và recovery của nền tảng |
| **Lost/stolen device** | Thiết bị giữ khóa bị mất | Revoke credential, đăng ký thiết bị mới an toàn, quản lý session |
| **Recovery bypass** | Reset email yếu thay thế passkey mạnh | Recovery assurance tương xứng, giới hạn thử, review và notification |
| **Session hijacking** | Cookie/token bị lấy sau passwordless login | Secure session, TTL, rotation, revoke và step-up |
| **Cross-account linking** | Ghép hai account chỉ vì email giống nhau | Liên kết theo issuer+subject và flow xác minh tài khoản hiện có |
| **Verifier implementation bug** | Bỏ qua origin/challenge hoặc kiểm tra sai chữ ký | Test giao thức, dùng thư viện chuẩn, kiểm toán verifier |

Passwordless loại bỏ một số rủi ro liên quan password reuse và password database, nhưng **không loại bỏ phishing, account takeover, session theft hoặc recovery abuse**. Threat model cần bao phủ từ lúc tạo credential đến lúc xóa hoặc khôi phục credential.

## 10. Thiết kế enrollment, recovery và vòng đời

Đây là phần thường quyết định mức an toàn thực tế của passwordless.

### 10.1. Enrollment

Khi thêm passkey hoặc authenticator mới:

1. Xác định principal từ session đã xác minh.
2. Yêu cầu reauthentication/step-up phù hợp trước thao tác nhạy cảm.
3. Tạo challenge đăng ký và ràng buộc với đúng flow.
4. Kiểm tra WebAuthn response theo RP ID, origin, challenge, attestation nếu policy yêu cầu.
5. Lưu public key/credential metadata an toàn; không lưu private key của authenticator.
6. Ghi audit, thông báo thay đổi và cho phép người dùng kiểm tra/revoke credential.
7. Ngăn session cũ hoặc recovery yếu tự thêm authenticator mà không qua policy.

### 10.2. Recovery và thiết bị dự phòng

Người dùng có thể mất điện thoại, khóa bảo mật hoặc quyền truy cập tài khoản đồng bộ. Cần quyết định trước:

- Có cho đăng ký nhiều passkey/khóa dự phòng không?
- Có recovery code không? Nếu có, mã có đủ entropy, lưu an toàn và dùng một lần không?
- Có quy trình xác minh danh tính hoặc hỗ trợ thủ công cho tài khoản rủi ro cao không?
- Có thông báo qua kênh đã đăng ký trước khi thay credential không?
- Khi recovery thành công, session/token/credential cũ nào phải thu hồi?
- Người dùng có thể khôi phục mà không phải hạ xuống một kênh yếu hơn đáng kể không?

Không nên để email magic link là cách duy nhất khôi phục tài khoản có passkey mạnh mà không đánh giá mức bảo vệ email. Nếu có fallback yếu hơn, cần giới hạn quyền, thời gian chờ, thông báo và bước xác minh bổ sung tương xứng.

### 10.3. Thu hồi và thay thế

Credential cần có vòng đời rõ: tạo, hoạt động, tạm khóa, thu hồi, xóa và thay thế. Người dùng cần xem được authenticator đã đăng ký ở mức phù hợp, thời điểm sử dụng gần nhất nếu có, và cách báo mất. Server cần khả năng thu hồi session/token liên quan khi phát hiện credential bị xâm phạm.

## 11. Chuyển đổi từ password sang passwordless

Không nên loại bỏ mật khẩu trên toàn bộ sản phẩm trong một lần mà chưa hiểu hành vi người dùng và các phụ thuộc hệ thống. Một lộ trình có thể gồm:

~~~mermaid
flowchart TD
    A[Đánh giá user, thiết bị và threat model] --> B[Chọn phương thức và policy]
    B --> C[Pilot: đăng ký tự nguyện passkey]
    C --> D[Đo enrollment, sign-in và recovery]
    D --> E{Kết quả đạt?}
    E -- Chưa --> F[Sửa UX, tương thích, support và policy]
    F --> C
    E -- Đạt --> G[Mở rộng theo nhóm người dùng]
    G --> H[Step-up hoặc password fallback có kiểm soát]
    H --> I[Giảm dần phụ thuộc password]
    I --> J[Đánh giá lại recovery, incident và vận hành]
~~~

### 11.1. Các giai đoạn thực tế

**Giai đoạn 1 — Baseline:** đo tỷ lệ login thất bại, reset password, credential stuffing, hỗ trợ và phân bố thiết bị. Xác định các tài khoản đặc quyền và thao tác rủi ro cao.

**Giai đoạn 2 — Pilot:** cho nhóm người dùng phù hợp đăng ký passkey; giữ phương thức hiện tại trong thời gian đánh giá. Kiểm thử browser/OS, đồng bộ, thiết bị mới, roaming authenticator và recovery.

**Giai đoạn 3 — Mở rộng:** tối ưu hướng dẫn enrollment, phát hiện credential đã có, hỗ trợ nhiều authenticator và thông báo an toàn. Phân nhóm theo nhu cầu, không giả định mọi người có cùng thiết bị.

**Giai đoạn 4 — Giảm phụ thuộc password:** khi coverage, support và recovery đủ tốt, có thể yêu cầu passwordless cho nhóm/tác vụ cụ thể, giảm password fallback hoặc tắt password ở những nơi policy cho phép.

**Giai đoạn 5 — Vận hành:** theo dõi takeover, mất thiết bị, credential revoke, sự cố sync/recovery và thay đổi nền tảng. Có quy trình rollback hoặc phương thức dự phòng có kiểm soát.

### 11.2. Fallback phải có cùng sự nghiêm ngặt về threat model

Một flow passkey có thể bị suy yếu nếu nút “Try another way” đưa người dùng tới SMS OTP hoặc email reset không được bảo vệ. Không phải fallback nào cũng phải có cùng UX hoặc cơ chế, nhưng quyền mà nó cấp phải tương xứng với bằng chứng và rủi ro.

Nếu phương thức thay thế có assurance thấp hơn, có thể giới hạn hành động, yêu cầu thêm kiểm tra, áp dụng thời gian chờ, thông báo kênh cũ hoặc review thủ công. Không âm thầm nâng trạng thái xác thực chỉ vì phương thức mạnh tạm thời không khả dụng.

## 12. Đánh giá trải nghiệm và khả năng tiếp cận

Passwordless có thể giảm ma sát, nhưng cũng có thể gây khó cho người dùng không có thiết bị tương thích, dùng máy tính chung, không có điện thoại cá nhân hoặc cần công nghệ hỗ trợ.

Cần kiểm tra:

- **Discoverability:** người dùng có tìm được passkey trên thiết bị hiện tại không?
- **Cross-device sign-in:** có flow QR/Bluetooth hoặc cơ chế chuyển thiết bị được nền tảng hỗ trợ không? Người dùng có hiểu họ đang xác thực cho đúng website không?
- **Roaming security key:** có hỗ trợ khóa vật lý cho môi trường đặc thù hoặc thiết bị chia sẻ không?
- **Shared devices:** không tự lưu credential cá nhân trên thiết bị công cộng; hướng dẫn logout và xóa credential đúng cách.
- **Accessibility:** thao tác sinh trắc, PIN, khóa vật lý và dialog có dùng được với công nghệ hỗ trợ không?
- **Account recovery:** người dùng mất thiết bị có phương thức thay thế dễ hiểu, an toàn và có thể tiếp cận không?
- **Localization:** thông báo lỗi, hướng dẫn enrollment và tên miền phải rõ ràng trong ngôn ngữ người dùng.
- **Support:** nhân viên hỗ trợ có quy trình xác minh phù hợp mà không yêu cầu người dùng đọc private key, OTP hoặc recovery secret cho họ không?

Không nên ép người dùng chia sẻ thiết bị hoặc sinh trắc. Cần có phương án thay thế bảo vệ tương xứng và không tạo đường bypass dễ bị lợi dụng.

## 13. Chỉ số đánh giá triển khai passwordless

Số lượng người “đã bật passkey” chưa cho biết triển khai thành công hay an toàn. Nên đo nhiều nhóm chỉ số:

| Nhóm | Chỉ số gợi ý | Câu hỏi trả lời |
| --- | --- | --- |
| **Adoption** | Tỷ lệ tài khoản có credential passwordless; số credential/user | Phương thức đã được đăng ký tới đâu? |
| **Usage** | Tỷ lệ sign-in dùng passkey; tỷ lệ fallback sang password/OTP | Người dùng thực sự sử dụng phương thức nào? |
| **Success** | Tỷ lệ hoàn tất đăng nhập, lỗi assertion, tỷ lệ challenge timeout | Flow có hoạt động ổn định không? |
| **Friction** | Thời gian đăng nhập, số bước, số lần thử, bỏ dở enrollment | UX có tốt hơn không? |
| **Recovery** | Tỷ lệ recovery, thời gian xử lý, trường hợp hỗ trợ thủ công | Mất thiết bị có dẫn tới khóa tài khoản hoặc bypass không? |
| **Security** | Phishing, credential stuffing, account takeover, replay và session theft | Rủi ro có giảm không? |
| **Operations** | Chi phí hỗ trợ, revoke, thay thiết bị, incident và SLA | Tổ chức có vận hành nổi không? |
| **Accessibility/coverage** | Tỷ lệ người dùng cần fallback, nhóm thiết bị không hỗ trợ | Có nhóm nào bị loại khỏi dịch vụ không? |

Phải định nghĩa mẫu số, phạm vi và cách ghi nhận cho từng metric. Ví dụ, tỷ lệ đăng nhập passkey thành công trên **những lần thử đã bắt đầu** khác với tỷ lệ tài khoản có passkey. Cũng cần phân biệt thất bại do người dùng hủy dialog với lỗi server hoặc credential không hợp lệ.

## 14. Khung ra quyết định chọn phương thức

Một cách lựa chọn thực tế:

| Bối cảnh | Hướng cân nhắc | Điều kiện quan trọng |
| --- | --- | --- |
| Ứng dụng người dùng phổ thông, nhiều thiết bị | Passkey đa nền tảng, có thể đồng bộ | Recovery tài khoản đồng bộ, thiết bị mới, fallback và hỗ trợ |
| Tài khoản đặc quyền/quản trị | Passkey hoặc security key với policy mạnh; có thể yêu cầu khóa dự phòng | Enrollment kiểm soát, step-up, revoke, audit và recovery nghiêm ngặt |
| Máy trạm doanh nghiệp được quản lý | Platform authenticator, security key hoặc certificate | Device management, PKI, rotation, offboarding |
| Service-to-service | Workload identity, mTLS hoặc token ngắn hạn | Private key bảo vệ, audience, TTL, rotation và trust anchor |
| Dịch vụ cần đăng nhập nhanh, rủi ro thấp | Magic link có giới hạn hoặc phương thức phù hợp | Bảo vệ mailbox, TTL, one-time use và không dùng cho thao tác nhạy cảm nếu chưa đủ |
| Người dùng không hỗ trợ passkey | Phương thức thay thế được policy chấp nhận | Không để fallback yếu trở thành đường bypass |
| Tác vụ tài chính/nhạy cảm | Phương thức chống phishing, freshness và xác nhận giao dịch phù hợp | Authorization, risk engine và kiểm soát giao dịch độc lập |

Không có một lựa chọn duy nhất phù hợp mọi sản phẩm. Hãy chọn theo **threat model, yêu cầu assurance, môi trường thiết bị, khả năng recovery, quyền riêng tư và chi phí hỗ trợ**.

## 15. Checklist review passwordless

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Phương thức có thực sự passwordless không? | Không yêu cầu password ở flow đó; mô tả rõ yếu tố và bằng chứng |
| Có chống phishing không? | Có ràng buộc relying party/origin và verifier kiểm tra đúng |
| Có chống replay không? | Challenge/token có entropy, TTL, binding và quy tắc tiêu thụ |
| Credential được gắn với đúng principal? | Enrollment yêu cầu session và xác minh phù hợp |
| Có phân biệt UP và UV? | Server kiểm tra cờ theo policy, không suy từ giao diện |
| Khóa có sync/export không? | Đặc tính khóa được hiểu và khớp yêu cầu assurance |
| Recovery có tạo đường vòng yếu? | Recovery threat model, giới hạn quyền, step-up và audit |
| Có nhiều authenticator hoặc thiết bị dự phòng? | Có quy trình thêm, revoke và thay thế |
| Session/token có được bảo vệ? | TTL, rotation, revoke, audience/scope và lưu trữ phù hợp |
| Có hỗ trợ nhiều thiết bị và trình duyệt? | Kiểm thử thực tế, có fallback có kiểm soát |
| Quyền riêng tư được bảo vệ? | Attestation và telemetry tối thiểu, retention và access policy |
| Có khả năng tiếp cận? | Có phương án thay thế an toàn và kiểm thử người dùng |
| Có chỉ số vận hành? | Đo adoption, success, fallback, recovery, takeover và support |
| Đã kiểm thử threat model? | Phishing, replay, sync takeover, enrollment, recovery và session theft |

### Tình huống tự kiểm tra

**Tình huống 1:** Một ứng dụng gửi magic link qua email, không còn form mật khẩu. Có thể gọi là passwordless không? Có. Có thể kết luận phishing-resistant không? Không. Quyền truy cập hộp thư và khả năng bảo vệ token link là một phần rủi ro chính.

**Tình huống 2:** Người dùng có passkey nhưng khi đăng nhập server không kiểm tra origin và challenge. Flow có còn bảo đảm WebAuthn như mong đợi không? Không. Verifier phải xác minh đầy đủ ràng buộc giao thức.

**Tình huống 3:** Người dùng mất thiết bị, chọn SMS recovery rồi hệ thống cấp phiên có quyền tương đương lần đăng nhập bằng security key. Đây có phải quyết định an toàn mặc định không? Không. Cần đánh giá assurance của recovery và giới hạn/step-up theo rủi ro.

**Tình huống 4:** Tổ chức yêu cầu passkey cho nhân viên nhưng chỉ đo tỷ lệ enrollment. Đã đủ đánh giá triển khai chưa? Chưa. Cần đo usage, sign-in success, fallback, recovery, takeover, hỗ trợ và khả năng tương thích.

**Tình huống 5:** Một certificate client hợp lệ được dùng trong mTLS. Có thể khẳng định người dùng cuối đã được xác thực bằng MFA không? Không. Certificate có thể xác thực workload hoặc thiết bị; cần xem danh tính được ràng buộc và ceremony của con người nếu có.

## 16. Ghi nhớ

**Passwordless là một hướng thiết kế đăng nhập, không phải một bảo đảm an toàn tự động.** Passkey/WebAuthn được xác minh đúng cung cấp khả năng chống phishing nhờ ràng buộc với relying party và challenge; magic link, email/SMS OTP và push có những rủi ro chuyển tiếp, chiếm kênh và lạm dụng riêng. Chứng chỉ phù hợp với thiết bị/workload khi PKI và vòng đời khóa được quản lý đúng.

Đánh giá đầy đủ phải bao gồm **enrollment → authentication → session/token → recovery → revoke**, cùng trải nghiệm, khả năng tiếp cận, quyền riêng tư và vận hành. Hãy đo hiệu quả bằng cả mức độ sử dụng, tỷ lệ thành công, fallback, recovery và sự cố bảo mật; không chỉ bằng số tài khoản đã bật passwordless.
