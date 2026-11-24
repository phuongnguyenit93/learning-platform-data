# Authentication assurance trong quản lý vòng đời danh tính IAM

**Authentication assurance** (mức bảo đảm xác thực) mô tả mức độ tin cậy có thể đặt vào kết quả một chủ thể đã chứng minh quyền kiểm soát phương tiện xác thực của mình trong một phiên hoặc một giao dịch cụ thể. Trong hệ thống doanh nghiệp, câu hỏi không chỉ là **đăng nhập thành công hay thất bại**, mà còn là **bằng cách nào, tại thời điểm nào, dưới chính sách nào và kết quả đó đủ an toàn cho hành động sắp thực hiện hay chưa**.

Bài thuộc chương **Authentication** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module nghiên cứu vòng đời danh tính **Joiner–Mover–Leaver (JML)**: xác minh danh tính, đăng ký tài khoản, cấp quyền, rà soát và thu hồi khi người dùng thay đổi vai trò hoặc rời tổ chức. Authentication assurance liên kết chặt chẽ với **IdP**, **SSO**, **MFA/passkey**, **SCIM**, phân quyền **RBAC/ABAC**, tài khoản dịch vụ, kiểm toán và việc ngăn **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Một nhân viên đã đăng nhập bằng mật khẩu để đọc lịch làm việc. Hệ thống không nhất thiết phải cho phép cùng phiên đó phê duyệt thanh toán giá trị lớn. Thao tác nhạy cảm có thể đòi hỏi xác thực mạnh hơn, mới hơn và chống phishing. Tuy nhiên, hoàn tất bước xác thực mạnh vẫn **không tự cấp quyền phê duyệt** nếu người dùng không có vai trò nghiệp vụ phù hợp.

## 1. Authentication assurance là gì?

Khi hệ thống xác thực người dùng, bộ xác minh (verifier) cần đánh giá nhiều yếu tố:

1. **Danh tính tài khoản được xác thực:** phiên này được gắn với tài khoản nào, định danh ổn định nào?
2. **Authenticator đã được đăng ký đáng tin:** password, TOTP, khóa bảo mật hoặc passkey có được liên kết đúng với tài khoản không?
3. **Cơ chế xác thực:** phương thức có chống replay, phishing hoặc trộm credential hay không?
4. **Bằng chứng trong phiên:** challenge, chữ ký, mã một lần hoặc bước user verification có được kiểm tra đúng?
5. **Độ mới của xác thực:** lần chứng minh quyền kiểm soát authenticator diễn ra khi nào?
6. **Phiên và ngữ cảnh sử dụng:** session/token có bị chiếm, hết hạn, bị thu hồi hoặc dùng ở sai ứng dụng không?
7. **Chính sách và mức rủi ro:** mức bảo đảm đạt được có đáp ứng hành động/tài nguyên yêu cầu không?

Các thành phần đó tạo ra một **kết luận có ngữ cảnh**, không phải nhãn vĩnh viễn của người dùng. Một nhân viên có khóa bảo mật mạnh nhưng phiên hiện tại chỉ đăng nhập bằng phương thức yếu **không tự động** được xem là vừa xác thực ở mức cao. Tương tự, một phiên đã đạt mức mạnh từ sáng có thể cần **xác thực lại** khi thực hiện giao dịch nhạy cảm vào cuối ngày.

### So sánh bốn khái niệm dễ nhầm

| Khái niệm | Câu hỏi chính | Ví dụ | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Identity proofing** | Người được khai báo có thực sự gắn với hồ sơ danh tính đó không? | Xác minh hồ sơ người được tuyển và nguồn HR. | Người đang truy cập vẫn giữ authenticator hợp lệ hôm nay. |
| **Authentication assurance** | Quá trình chứng minh quyền kiểm soát authenticator có đủ tin cậy cho phiên/hành động này không? | Đăng nhập bằng passkey với user verification. | Người đó có quyền xem mọi dữ liệu. |
| **Federation assurance** | Có thể tin cậy kết quả xác thực được truyền qua các bên đến mức nào? | Ứng dụng nhận assertion từ IdP qua OIDC/SAML. | Các quyền ở ứng dụng đích luôn cập nhật tức thì. |
| **Authorization** | Chủ thể được phép làm gì trên tài nguyên nào? | Role và ABAC chỉ cho duyệt giao dịch thuộc phòng ban. | Quá trình đăng nhập đang đạt mức bảo đảm cần thiết. |

**Nguyên tắc:** IAL, AAL, FAL và authorization liên quan nhưng là **những quyết định độc lập**. Một hệ thống cần đúng danh tính, xác thực đủ mạnh, tin cậy federation và kiểm tra quyền ứng dụng.

## 2. Authentication Assurance Level (AAL)

Trong các khung hướng dẫn bảo đảm danh tính như **NIST SP 800-63**, Authentication Assurance Level (**AAL**) được dùng để mô tả yêu cầu bảo đảm của cơ chế xác thực. Khi xây dựng hệ thống thực tế, cần chọn **phiên bản tiêu chuẩn** áp dụng và đối chiếu đầy đủ yêu cầu của phiên bản đó; mô tả dưới đây là **khái quát để học**, không thay thế việc đánh giá tuân thủ chuẩn.

| Mức | Ý nghĩa khái quát | Ví dụ tư duy | Điểm cần đặc biệt chú ý |
| --- | --- | --- | --- |
| **AAL1** | Mức bảo đảm cơ bản; có thể dựa trên một yếu tố được chấp nhận theo yêu cầu chuẩn. | Đăng nhập bằng authenticator đơn yếu tố được chấp nhận. | Chống đoán mật khẩu, bảo vệ kênh, hạn chế thử, quản lý phiên. |
| **AAL2** | Mức bảo đảm cao hơn với xác thực đa yếu tố hoặc tổ hợp cơ chế đáp ứng đầy đủ yêu cầu tương ứng. | Mật khẩu kết hợp authenticator thứ hai; hoặc một authenticator đa yếu tố phù hợp. | Hai yếu tố độc lập, chống replay, lifecycle authenticator và phương án chống phishing theo yêu cầu của chính sách/phiên bản chuẩn. |
| **AAL3** | Mức bảo đảm rất cao, có yêu cầu chặt chẽ hơn với cơ chế mật mã, phần cứng/bảo vệ khóa và chống giả mạo verifier theo chuẩn áp dụng. | Authenticator mật mã dựa trên phần cứng, sử dụng trong luồng đáp ứng đầy đủ các yêu cầu AAL3. | Không suy AAL3 chỉ vì có một khóa cứng; phải đánh giá toàn bộ authenticator, verifier, phiên và quy trình đăng ký/khôi phục. |

**Không định nghĩa AAL bằng công thức “AAL2 = luôn luôn SMS” hoặc “AAL3 = cứ mua khóa FIDO2”.** Một mức bảo đảm phụ thuộc **toàn bộ yêu cầu kỹ thuật và vận hành**: loại authenticator, proof of possession, bảo vệ secret/khóa, bảo mật giao thức, reauthentication, chống tấn công và vòng đời.

### Mức của người dùng và mức của phiên

Phân biệt:

- **Đủ điều kiện đăng ký:** tài khoản đã có authenticator được phép dùng cho mức AAL mục tiêu.
- **Mức đã đạt trong phiên:** phiên thực sự đã dùng phương thức và kiểm tra cần thiết theo policy.
- **Mức yêu cầu của hành động:** giao dịch cụ thể yêu cầu mức AAL, độ mới, khả năng chống phishing hoặc điều kiện khác.

Ví dụ Mai có cả mật khẩu, TOTP và khóa bảo mật. Khi Mai dùng mật khẩu + TOTP, phiên có thể đáp ứng chính sách MFA nhưng **không thể vì thế khẳng định phiên đã dùng khóa bảo mật**. Nếu ứng dụng yêu cầu xác thực chống phishing cho thay đổi quyền quản trị, IdP phải yêu cầu bước phù hợp, không chỉ kiểm tra rằng khóa bảo mật tồn tại trong hồ sơ.

## 3. Các yếu tố và đặc tính bảo mật của authenticator

Ba nhóm yếu tố quen thuộc:

- **Something you know:** mật khẩu hoặc PIN do chủ thể biết.
- **Something you have:** khóa bảo mật, thiết bị giữ khóa riêng hoặc authenticator có possession factor.
- **Something you are:** đặc điểm sinh trắc dùng trong cơ chế được thiết kế và bảo vệ phù hợp.

Hai mật khẩu khác nhau **không tạo MFA** vì thuộc cùng nhóm yếu tố. Một authenticator có thể kết hợp hai yếu tố, chẳng hạn khóa riêng được bảo vệ trên thiết bị và cần PIN/sinh trắc để sử dụng; kết quả bảo đảm phụ thuộc verifier và thiết kế cụ thể.

| Phương thức | Đặc tính tích cực | Rủi ro/giới hạn | Gợi ý sử dụng |
| --- | --- | --- | --- |
| **Password** | Phổ biến, dễ tích hợp. | Phishing, reuse, credential stuffing, đoán mật khẩu. | Bảo vệ bằng kiểm soát thử, kiểm tra mật khẩu yếu/lộ và MFA thích hợp. |
| **TOTP** | Mã một lần giới hạn thời gian, dùng rộng rãi. | Có thể bị phishing theo thời gian thực; seed cần bảo vệ. | Giải pháp MFA phổ thông khi chưa thể triển khai authenticator mạnh hơn. |
| **SMS/voice OTP** | Tiếp cận nhiều người dùng. | SIM swap, chuyển số, chặn tin, phishing; hạn chế về bảo đảm. | Chỉ dùng ở phạm vi chính sách chấp nhận và có phương án thay thế. |
| **Push approval** | Trải nghiệm thuận tiện. | MFA fatigue, người dùng chấp nhận nhầm, rủi ro thiết bị. | Number matching/binding, giới hạn yêu cầu và cảnh báo bất thường. |
| **WebAuthn/FIDO2 passkey** | Mật mã khóa công khai, ràng buộc với RP/origin, chống phishing khi triển khai đúng. | Phụ thuộc enrollment/recovery, cách bảo vệ khóa và user verification. | Ưu tiên cho tài khoản nhạy cảm và trải nghiệm chống phishing. |
| **Khóa bảo mật phần cứng** | Giảm nguy cơ sao chép khóa nếu phần cứng và cấu hình phù hợp. | Mất thiết bị, quản lý cấp phát, hỗ trợ thiết bị và recovery. | Phù hợp với nhiều yêu cầu bảo đảm cao, nhưng vẫn phải đánh giá cả phiên. |

### Replay resistance, phishing resistance và verifier impersonation resistance

Ba thuộc tính quan trọng nhưng không giống nhau:

1. **Replay resistance:** bằng chứng của lần xác thực trước không thể bị phát lại như một bằng chứng hợp lệ mới. Challenge ngẫu nhiên hoặc mã sử dụng một lần giúp giảm rủi ro này.
2. **Phishing resistance:** cơ chế khó bị trang giả hoặc bên trung gian giả mạo verifier lấy được bí mật/bằng chứng có thể chuyển sang site thật. OTP có thể bị chuyển tiếp, nên bản thân OTP không chống phishing.
3. **Verifier impersonation resistance:** giao thức có cơ chế chống việc kẻ khác giả làm bên xác minh để thu bằng chứng có thể dùng lại ở verifier thật.

WebAuthn/FIDO2 dùng cơ chế khóa công khai gắn với **Relying Party ID** và kiểm tra **origin/challenge** để chống phishing theo đặc tính giao thức. Điều này không làm biến mất rủi ro **đánh cắp session, chiếm quyền khôi phục tài khoản, tấn công thiết bị đầu cuối** hoặc lỗi authorization.

### Passkey và user verification

Với WebAuthn, **user presence (UP)** và **user verification (UV)** là những điều kiện khác nhau. Một thao tác chạm khóa có thể chứng minh sự hiện diện trong khi policy nhạy cảm yêu cầu bước xác minh người dùng cục bộ như PIN hoặc sinh trắc theo khả năng authenticator. Nếu cần UV, verifier **phải kiểm tra cờ/điều kiện UV đúng giao thức**, không suy ra từ tên phương thức.

Passkey đồng bộ và credential gắn thiết bị có đặc tính quản trị khác nhau. Với yêu cầu phần cứng hoặc mức bảo đảm rất cao, phải đánh giá **khả năng đồng bộ/xuất khóa, nguồn authenticator, attestation khi dùng được, recovery** và quy định của tiêu chuẩn áp dụng. Một passkey chỉ được gọi là “không thể sao chép” khi có căn cứ kỹ thuật thật sự cho kết luận đó.

## 4. Identity proofing và MFA enrollment là nền móng của assurance

**Cách một authenticator được đăng ký quyết định liệu chúng ta có tin nó thuộc đúng chủ thể hay không.** Nếu kẻ tấn công dùng tên người dùng và thông tin công khai để đăng ký khóa của chính mình, các lần đăng nhập sau có thể rất mạnh về mật mã nhưng gắn với sai người.

Luồng tin cậy thường có:

1. Nguồn nhân sự/đối tác có thẩm quyền xác nhận chủ thể đủ điều kiện.
2. Identity proofing thiết lập mối liên kết với hồ sơ danh tính ở mức cần thiết.
3. IAM tạo hoặc liên kết **subject ID ổn định** và account IdP.
4. Người dùng thực hiện **bootstrap** đủ tin cậy để đăng ký authenticator đầu tiên.
5. IdP xác minh **proof of possession** của phương thức mới: mã TOTP thử, WebAuthn registration response hoặc bằng chứng phù hợp.
6. Registry liên kết authenticator với đúng account, lưu thời điểm, loại, chính sách và metadata cần thiết.
7. Khi sử dụng, verifier xác thực và xác định mức bảo đảm **của lần xác thực/phiên thực tế**.

**Không được coi “đã lưu TOTP seed” là “đăng ký xong”** trước khi người dùng chứng minh đã cấu hình đúng phương thức theo policy. Tương tự, với WebAuthn, server phải kiểm tra challenge, RP ID hash, origin, dữ liệu đăng ký và cờ cần thiết trước khi lưu khóa công khai ở trạng thái active.

### Rủi ro từ recovery

Nếu helpdesk cho phép “mất MFA thì chỉ cần gọi điện và đọc mã nhân viên để đặt lại”, attacker có thể bypass toàn bộ cơ chế chống phishing. Vì vậy **khôi phục tài khoản là một phần của bảo đảm xác thực**, cần:

- Kênh yêu cầu được công bố và kiểm soát.
- Kiểm tra danh tính/phiên thay thế với mức tin cậy phù hợp.
- Phê duyệt độc lập cho tài khoản đặc quyền khi chính sách yêu cầu.
- Thu hồi authenticator mất/nghi lộ, session liên quan và đăng ký phương thức mới.
- Thông báo thay đổi bảo mật tới kênh liên hệ đáng tin và audit.

Không gửi OTP, private key, recovery code hay mật khẩu tới helpdesk qua chat/email để “xác nhận”. Recovery codes cần bảo vệ, giới hạn lần thử và dùng một lần; không nên trở thành cửa sau yếu cho tài khoản quản trị.

## 5. Quy trình xác thực và đánh giá assurance

~~~mermaid
sequenceDiagram
    participant User as Người dùng / Authenticator
    participant App as Ứng dụng
    participant IdP as IdP / Verifier
    participant Policy as Policy / Risk Engine
    User->>App: Yêu cầu đăng nhập
    App->>IdP: Redirect / yêu cầu xác thực
    IdP->>Policy: Lấy policy, rủi ro, trạng thái account
    Policy-->>IdP: Yêu cầu authenticator và mức assurance
    IdP->>User: Challenge / yêu cầu MFA
    User-->>IdP: Bằng chứng từ authenticator
    IdP->>IdP: Kiểm chứng, anti-replay, binding, trạng thái
    IdP-->>App: Kết quả SSO / assertion đã bảo vệ
    App->>App: Xác minh token/assertion và phiên
    App->>Policy: Kiểm tra assurance + quyền + tài nguyên
    Policy-->>App: Allow / deny / step-up
    App-->>User: Kết quả truy cập
~~~

Đối với một request nhạy cảm, có thể có **hai cổng kiểm soát**:

1. **Authentication assurance gate:** phiên hiện hành có mức xác thực, độ mới và các thuộc tính bắt buộc không?
2. **Authorization gate:** chủ thể có role, permission, tenant/resource scope và phê duyệt nghiệp vụ không?

Một người có thể PASS cổng assurance nhưng FAIL authorization hoặc ngược lại. Không dùng một câu lệnh “đã MFA nên cho phép” để bỏ qua kiểm tra quyền.

## 6. Ràng buộc phiên, token và độ mới của xác thực

Authentication assurance không chỉ nằm trong lần người dùng nhập yếu tố. Sau khi IdP xác thực, ứng dụng thường duy trì **session** hoặc nhận token. Nếu phiên bị đánh cắp, attacker có thể sử dụng phiên **mà không cần đi qua MFA lần nữa**.

Các kiểm soát cần cân nhắc:

| Kiểm soát | Vấn đề giải quyết | Điểm cần triển khai |
| --- | --- | --- |
| **Secure session cookies** | Giảm lộ cookie qua kênh không an toàn hoặc script. | HTTPS, Secure, HttpOnly, SameSite phù hợp, chống CSRF và XSS. |
| **Session rotation/binding** | Giảm session fixation và nhầm phiên sau đăng nhập/step-up. | Tạo lại session ID khi nâng trạng thái xác thực; kiểm tra binding. |
| **Idle timeout** | Giảm cửa sổ khi người dùng rời thiết bị. | Thời gian dựa trên mức assurance và policy thực tế. |
| **Absolute timeout** | Chặn sử dụng session dài hạn liên tục. | Buộc xác thực lại theo yêu cầu chuẩn và rủi ro. |
| **Recent authentication** | Yêu cầu thao tác nhạy cảm có xác thực mới. | Kiểm thời điểm xác thực, không chỉ thời điểm token được cấp. |
| **Revocation / logout** | Giảm phiên tồn dư sau Leaver, mất thiết bị hoặc nghi xâm nhập. | Chặn phiên/token tại nơi thực thi và xác minh hiệu lực. |
| **Access token validation** | Chặn token sai nguồn, sai đối tượng hoặc hết hạn. | Kiểm issuer, audience, chữ ký/introspection, expiry và policy. |

### Vì sao thời điểm phát hành token không phải lúc nào cũng là thời điểm MFA?

Một IdP có thể phát hành **access token mới** từ refresh token mà không yêu cầu người dùng nhập lại MFA. Khi đó thời điểm phát hành token mới **không chứng minh** có xác thực mạnh mới diễn ra. Để kiểm tra độ mới, phải dựa vào thông tin xác thực như **auth_time** hoặc dữ liệu phiên đáng tin được hợp đồng giao thức cung cấp, không dùng nhầm trường **iat** làm thời điểm người dùng vừa xác thực.

Khi một ứng dụng cần assurance mới hơn, nó có thể gửi yêu cầu **step-up/reauthentication** tới IdP theo khả năng giao thức và xác minh kết quả trả về, thay vì giả định phiên SSO cũ đã đáp ứng.

### Session hijacking không được giải quyết chỉ bằng MFA

MFA có thể ngăn attacker đăng nhập bằng mật khẩu đánh cắp, nhưng không tự ngăn attacker dùng cookie phiên đã chiếm được. Do đó cần bảo vệ endpoint, chống phishing trung gian, cấu hình cookie, giám sát rủi ro và cơ chế xác thực lại cho thao tác nhạy cảm.

## 7. Authentication assurance khi sử dụng SSO và federation

Trong mô hình SSO, IdP thực hiện xác thực, còn ứng dụng dựa vào kết quả đó. Ứng dụng không thể biết chính xác mức assurance chỉ từ câu “SSO login succeeded”; phải kiểm tra **assertion hoặc thông tin phiên có thể tin cậy**.

### Với OpenID Connect (OIDC)

Một **ID token** minh họa có thể chứa:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "person-4821",
  "aud": "finance-portal",
  "exp": 1795000000,
  "iat": 1794999700,
  "auth_time": 1794999600,
  "acr": "urn:example:assurance:phishing-resistant",
  "amr": ["hwk", "pin"]
}
~~~

Đây là **payload giả định**, không phải token có chữ ký hợp lệ; các giá trị **acr/amr** phụ thuộc IdP và **không có ánh xạ phổ quát** từ chuỗi tùy ý sang AAL. Một hệ thống phải:

- Xác minh chữ ký, issuer, audience, expiry, nonce và các yêu cầu liên quan của luồng OIDC.
- Kiểm tra **auth_time**, **acr**, **amr** hoặc thông tin assurance được thỏa thuận nếu có.
- Hiểu đúng **accreditation/contract** của IdP: một claim chỉ có giá trị khi bên phát hành có cơ chế bảo đảm và chính sách tương ứng.
- Không dùng ID token như access token để gọi API được bảo vệ.
- Không tự tin claim do frontend cung cấp hoặc một header chưa được xác thực.

**acr** thường biểu diễn ngữ cảnh/lớp xác thực theo quy ước của IdP; **amr** biểu diễn các phương thức đã được dùng. Chúng không nên được diễn giải theo tên trường một cách máy móc; ví dụ một array **amr** không tự chứng minh tất cả yêu cầu của AAL3 hoặc chính sách chống phishing đã được thỏa mãn.

### Với SAML

SAML có thể truyền thông tin **AuthnContext** và thời điểm xác thực. Ứng dụng cần xác minh chữ ký/assertion, issuer, audience, điều kiện hiệu lực và recipient theo đúng profile triển khai. **AuthnContextClassRef** có thể chỉ ra lớp xác thực nhưng ý nghĩa phụ thuộc trust agreement; không suy một giá trị tùy ý thành mức AAL mà không có ánh xạ được phê duyệt.

### Federation assurance khác authentication assurance

Ngay cả khi IdP xác thực người dùng tốt, ứng dụng có thể mắc lỗi **token confusion**, nhận assertion sai audience, bỏ qua chữ ký hoặc trust nhầm issuer. Vì vậy phải bảo vệ cả **bên phát hành, đường truyền kết quả, bên nhận và phiên sau khi nhận**. Khả năng tin cậy việc trao đổi assertion không tự thay thế khả năng tin cậy của authenticator ban đầu.

## 8. Step-up authentication cho hành động rủi ro cao

**Step-up authentication** là yêu cầu người dùng thực hiện thêm hoặc lặp lại bước xác thực để đạt assurance cần thiết trước một hành động nhạy cảm. Nó không nhất thiết là “bắt nhập OTP mọi lần”; phương thức nên phụ thuộc rủi ro và chính sách.

Ví dụ:

- Đọc cổng thông tin nhân viên: assurance mức cơ sở theo policy.
- Xuất hồ sơ khách hàng diện rộng: yêu cầu xác thực mạnh hơn và quyền xuất dữ liệu đã phê duyệt.
- Đổi số điện thoại khôi phục hoặc thêm authenticator MFA: yêu cầu **recent authentication** hoặc quy trình recovery tương xứng.
- Cấp quyền quản trị, thay policy hoặc chuyển tiền giá trị lớn: ưu tiên phương thức chống phishing, kiểm tra thời điểm xác thực và kiểm soát nghiệp vụ riêng.

~~~mermaid
flowchart TD
    R["Request tới tài nguyên"] --> A["Xác minh session / token"]
    A --> P["Đọc policy assurance của hành động"]
    P --> C{"Phiên đủ assurance và đủ mới?"}
    C -->|Không| S["Step-up qua IdP / reauthentication"]
    S --> V{"Step-up được xác minh?"}
    V -->|Không| D["Deny + audit"]
    V -->|Có| Z["Cập nhật trust context đáng tin"]
    C -->|Có| Z
    Z --> B["Kiểm RBAC/ABAC và tài nguyên"]
    B --> O{"Được phép?"}
    O -->|Có| Y["Allow"]
    O -->|Không| D
~~~

**Không được coi step-up hoàn tất ở client** chỉ vì giao diện hiện “Verified”. Backend cần kết quả có thể xác minh từ IdP/session service và ràng buộc với đúng user, phiên, hành động hoặc yêu cầu khi cần.

### Rủi ro của yêu cầu MFA liên tục

Thường xuyên ép xác thực lại bằng phương thức yếu có thể gây **MFA fatigue** và tăng khả năng người dùng phê duyệt nhầm. Chính sách tốt phân tầng theo rủi ro, yêu cầu phương thức chống phishing khi phù hợp và bảo vệ phiên để tránh hỏi lại vô ích.

## 9. Chính sách RBAC/ABAC kết hợp yêu cầu assurance

**RBAC** xác định quyền theo vai trò; **ABAC** quyết định dựa trên thuộc tính chủ thể, tài nguyên và ngữ cảnh. Authentication assurance có thể là **một thuộc tính đáng tin** được dùng trong chính sách, không phải quyền nghiệp vụ.

| Thuộc tính | Ví dụ | Nguồn đáng tin |
| --- | --- | --- |
| Danh tính | subject ID và trạng thái active | IdP, identity registry, HR/IGA |
| Role | FINANCE_PAYMENT_APPROVER | IAM/IGA hoặc nguồn role đã phê duyệt |
| Assurance phiên | Mức phương thức, khả năng chống phishing, auth_time | IdP/verifier hoặc session service đáng tin |
| Thiết bị | Managed/compliant, posture timestamp | MDM/UEM hoặc nguồn kiểm tra thiết bị đáng tin |
| Tài nguyên | tenant, classification, trạng thái giao dịch | Ứng dụng/hệ thống dữ liệu |
| Hành động | read, export, approve, change-password | Backend/router đáng tin |
| Rủi ro | device anomaly, sign-in risk, network context | Risk engine và nguồn tín hiệu được phép sử dụng |

Ví dụ cấu hình logic:

~~~yaml
policyId: payment-approval
subject:
  employmentStatus: ACTIVE
  role: FINANCE_PAYMENT_APPROVER
authentication:
  requiredProfile: PHISHING_RESISTANT
  recentAuthenticationRequired: true
  maxAuthenticationAgeMinutes: 10
resource:
  tenantMatchesSubject: true
  paymentStatus: PENDING_APPROVAL
action: APPROVE
separationOfDuties:
  requesterCannotApproveOwnPayment: true
fallback: DENY
~~~

Đây là **pseudoconfiguration minh họa**, không phải cấu hình thực thi của một IdP hay PDP cụ thể; ngưỡng 10 phút chỉ là ví dụ nghiệp vụ. Chỉ sử dụng profile assurance sau khi có ánh xạ đáng tin từ sự kiện xác thực thực sự. **Role FINANCE_PAYMENT_APPROVER** là điều kiện cần độc lập với việc đã dùng passkey.

## 10. Ví dụ kiểm tra assurance và quyền trong backend Java

~~~java
// Pseudocode: security context do backend xác minh từ IdP/session,
// không đọc AAL hay role từ header/body do client tự nhập.
ApprovalResult approvePayment(
        TrustedSecurityContext context,
        String paymentId) {

    UserIdentity user = userDirectory.requireActive(context.subjectId());
    Payment payment = paymentRepository.findById(paymentId)
        .orElseThrow(ResourceNotFoundException::new);

    if (!context.authentication().isValidNow()) {
        throw new UnauthenticatedException("session_not_valid");
    }

    if (!assurancePolicy.meetsRequiredProfile(
            context.authentication(), "PAYMENT_APPROVAL")) {
        throw new StepUpRequiredException();
    }

    if (!context.authentication().isRecentEnoughFor("PAYMENT_APPROVAL")) {
        throw new StepUpRequiredException();
    }

    // Kiểm tra quyền, tài nguyên, tenant và SoD RIÊNG với assurance.
    if (!accessPolicy.hasRole(user, "FINANCE_PAYMENT_APPROVER")
            || !accessPolicy.canAccessTenant(user, payment.tenantId())
            || !payment.isPendingApproval()
            || payment.requesterId().equals(user.id())) {
        throw new AccessDeniedException("not_authorized");
    }

    return paymentService.approveWithinTransaction(payment, user);
}
~~~

Đoạn code **minh họa cấu trúc điều kiện**. Trong hệ thống production còn cần kiểm soát concurrency, integrity của payment, replay giao dịch, CSRF và xác thực thời điểm quyết định; với giao dịch đặc biệt nhạy cảm có thể cần **transaction binding** giữa lần xác thực và nội dung phê duyệt theo chính sách.

**Không làm như sau:** frontend gửi JSON có trường **aal=3** rồi backend tin ngay. Nếu app cần biết assurance, nó phải sử dụng context từ token/assertion đã xác minh và hiểu cách IdP xác nhận phương thức.

## 11. Nguy cơ làm suy giảm authentication assurance

| Nguy cơ | Cơ chế | Biện pháp giảm rủi ro |
| --- | --- | --- |
| **Credential stuffing** | Dùng mật khẩu lộ từ hệ thống khác. | Chống reuse mật khẩu lộ, rate limit và MFA. |
| **Phishing / AiTM** | Dụ nhập OTP hoặc chiếm session qua proxy giả mạo. | Phương thức chống phishing, bảo vệ phiên và phát hiện bất thường. |
| **MFA fatigue** | Gửi push liên tục để người dùng nhấn chấp thuận. | Number matching, giới hạn yêu cầu, báo cáo yêu cầu lạ. |
| **SIM swap** | Chiếm số điện thoại để nhận SMS OTP. | Hạn chế SMS ở ngữ cảnh nhạy cảm, kiểm soát thay số. |
| **Enrollment hijack** | Tự đăng ký authenticator khi đã chiếm session/biết dữ liệu cá nhân. | Bootstrap mạnh, step-up, notification và binding. |
| **Recovery bypass** | Helpdesk reset MFA chỉ dựa thông tin dễ đoán. | Recovery phù hợp assurance mục tiêu, audit và phê duyệt độc lập. |
| **Session theft** | Trộm cookie hoặc token sau khi người dùng xác thực mạnh. | Session hardening, giới hạn lifetime, revoke, kiểm tra giao dịch nhạy cảm. |
| **Stale assurance** | Phiên mạnh từ nhiều giờ trước bị dùng cho thao tác cần xác thực mới. | auth_time và step-up dựa trên chính sách. |
| **Claim spoofing** | App tin claim do client tự gửi hoặc ID token sai audience. | Xác minh đầy đủ token/assertion và trust agreement. |
| **Overclaim AAL** | Gán nhãn AAL3 cho mọi passkey/khóa cứng mà không đánh giá. | Assurance mapping được phê duyệt, kiểm tra toàn bộ yêu cầu. |
| **Downgrade path** | Tài khoản admin dùng khóa mạnh nhưng recovery bằng SMS không kiểm soát. | Bảo vệ cả đăng nhập, enrollment, recovery và fallback. |
| **Residual access** | Nhân viên nghỉ nhưng phiên cũ/app token vẫn dùng được. | Deprovision có readback, revoke session/token và test. |

**Độ bảo đảm cao không đồng nghĩa không thể bị tấn công.** Nó giúp nâng độ tin cậy của bằng chứng xác thực; các lớp bảo vệ thiết bị, phiên, dữ liệu, phân quyền và vận hành vẫn cần thiết.

## 12. Authentication assurance trong Joiner–Mover–Leaver

### Joiner: thiết lập assurance từ đầu

Một nhân viên mới cần được **identity proofing** đúng theo chính sách, tạo tài khoản IdP, đăng ký MFA bằng quy trình bootstrap tin cậy và cấp quyền tối thiểu đúng ngày có hiệu lực. Nếu người dùng chưa có authenticator phù hợp với role nhạy cảm, hệ thống có thể chuẩn bị account nhưng **chưa kích hoạt quyền nhạy cảm**.

Quy trình gợi ý:

1. HRIS phát sự kiện Joiner hợp lệ có subject ID và ngày hiệu lực.
2. IAM/IGA xác minh điều kiện tạo account và phê duyệt quyền.
3. IdP cho phép đăng ký authenticator đầu tiên qua quy trình enrollment an toàn.
4. Hệ thống xác nhận phương thức đạt chính sách cho tài khoản/vai trò.
5. SCIM/connector cấp các account và entitlement được phép.
6. Ứng dụng xác minh session, assurance và quyền khi người dùng thực sự truy cập.

### Mover: yêu cầu assurance có thể thay đổi

Khi nhân viên chuyển từ vị trí đọc dữ liệu sang phê duyệt giao dịch hoặc quản trị hạ tầng, các role và điều kiện xác thực cần được **đánh giá lại**:

- Thu hồi quyền cũ không còn hợp lệ, tránh privilege creep.
- Cấp quyền mới sau phê duyệt và kiểm tra **Separation of Duties (SoD)**.
- Nếu role mới đòi hỏi phishing-resistant authenticator hoặc độ mới của phiên, chặn thao tác nhạy cảm cho tới khi đạt.
- Không tự suy rằng phương thức đã đăng ký hoặc phiên từ role cũ đáp ứng yêu cầu role mới.
- Rà soát quyền quản trị vault, service account, repository và CI/CD của nhóm cũ.

Ví dụ: Lan chuyển từ Sales sang Finance. Lan giữ account SSO và passkey hợp lệ, nhưng quyền Finance chỉ cấp khi có approval; quyền Sales cần được thu hồi ở IdP, ứng dụng CRM và các ACL liên quan. **Không cần đăng ký lại mọi authenticator** nếu phương thức hiện tại vẫn được tin cậy và đáp ứng chính sách mới.

### Leaver: assurance không thay thế deprovisioning

Người đã nghỉ việc có thể có phiên xác thực mạnh được tạo trước mốc nghỉ. Điều đó **không có nghĩa người đó được quyền tiếp tục truy cập**. Tổ chức cần:

- Disable account hoặc quyền đăng nhập theo thời điểm hiệu lực.
- Thu hồi session/refresh token và kiểm tra access token còn hạn theo thiết kế.
- Deprovision group/role, local account, SaaS session và quyền ở ứng dụng đích.
- Thu hồi quyền quản trị thiết bị, service account, vault hoặc credential cục bộ liên quan.
- Readback và kiểm tra effective access tại các hệ thống quan trọng; không chỉ dựa vào thông báo “IdP disabled”.

Kết quả **AAL cao trong phiên cũ** không thể bù cho **employment status=INACTIVE** hay role đã bị thu hồi. Ứng dụng phải có chính sách kiểm tra trạng thái và quyền hiện hành.

## 13. Service account và workload identity: không áp MFA người dùng máy móc

Service account, job CI/CD, microservice hoặc workload tự động thường **không có người để nhập OTP hoặc duyệt push** trong mỗi lần gọi API. Với các danh tính phi con người, bảo đảm xác thực được thiết kế bằng cơ chế phù hợp:

- Managed identity hoặc workload identity federation với token ngắn hạn.
- OAuth 2.0 client authentication (ví dụ private_key_jwt hoặc mTLS theo khả năng nền tảng).
- Chứng chỉ riêng của workload/thiết bị, khóa được bảo vệ và quản lý vòng đời certificate.
- Giới hạn issuer, audience, subject, namespace, repository, môi trường và trust policy.
- Luân chuyển/thu hồi credential, tránh dùng secret tĩnh chia sẻ rộng.

**Không gán nhãn AAL của xác thực người dùng** cho workload như thể một job đã nhập hai yếu tố. Các khung bảo đảm với authenticator của con người cần được diễn giải đúng phạm vi. MFA nên bảo vệ **con người có quyền quản trị** service identity, secret manager hoặc trust policy; còn workload tự động cần chứng minh danh tính máy/workload và chịu authorization riêng.

Khi owner của service account Mover/Leaver, dịch vụ có thể cần hoạt động tiếp nhưng **quyền quản lý của người cũ phải được gỡ**. Nếu người đó từng tiếp cận private key/client secret dài hạn, cần đánh giá rotation/revocation theo rủi ro.

## 14. Thiết kế chính sách assurance dựa trên rủi ro

Không nên bắt mọi người, mọi thao tác đều dùng cơ chế đắt đỏ nhất mà không xét tác động. Quản trị IAM có thể:

1. **Phân loại tài nguyên:** dữ liệu công khai/nội bộ/nhạy cảm; quyền xem, sửa, xuất, quản trị.
2. **Đánh giá tác hại khi chiếm phiên:** lộ dữ liệu, mất tiền, thay đổi cấu hình, phá hủy dịch vụ.
3. **Chọn profile xác thực:** yếu tố, chống phishing, độ mới, loại thiết bị hoặc mức AAL nếu chính sách áp chuẩn.
4. **Định nghĩa thời hạn phiên:** idle, absolute và reauthentication theo yêu cầu chuẩn/rủi ro.
5. **Thiết kế enrollment/recovery:** không tạo đường hạ cấp phá assurance mục tiêu.
6. **Xác định trust với IdP/SSO:** claim, assurance mapping, issuer, audience, cách refresh/step-up.
7. **Tách authorization:** role, SoD, tenant, resource và trạng thái nhân sự phải được kiểm tra riêng.
8. **Kiểm thử và rà soát:** mô phỏng rủi ro token cũ, mất MFA, Mover/Leaver và thay đổi chính sách.

### Ma trận yêu cầu minh họa

| Hành động | Assurance kỳ vọng | Kiểm soát bổ sung |
| --- | --- | --- |
| Xem lịch làm việc | Đáp ứng baseline theo policy. | Session hợp lệ, account active. |
| Xem báo cáo nội bộ | MFA theo mức rủi ro. | Role/tenant của báo cáo. |
| Xuất danh sách khách hàng | Xác thực mạnh hoặc step-up theo policy. | Quyền export, phạm vi dữ liệu, ghi audit. |
| Duyệt thanh toán lớn | Phương thức chống phishing và recent authentication. | Role approver, SoD, giới hạn số tiền. |
| Thay đổi authenticator MFA | Recent authentication hoặc recovery đủ bảo đảm. | Thông báo, audit, chống enrollment hijack. |
| Cấp global admin | Assurance cao phù hợp chính sách tổ chức. | Approval độc lập, PAM/PIM, thời hạn và giám sát. |

Đây là **ví dụ phân tầng yêu cầu**, không phải khẳng định chuẩn bắt buộc cho mọi ngành hoặc hệ thống.

## 15. Kiểm thử chất lượng authentication assurance

| Tình huống thử | Kết quả kỳ vọng |
| --- | --- |
| Người dùng chỉ đăng nhập bằng mật khẩu, thao tác yêu cầu MFA. | Yêu cầu bước xác thực bổ sung hoặc từ chối. |
| TOTP hợp lệ, thao tác yêu cầu phương thức chống phishing. | Không tự đánh dấu đạt yêu cầu phishing-resistant. |
| WebAuthn response có challenge/origin/RP ID không hợp lệ. | Từ chối, không nâng trạng thái xác thực. |
| WebAuthn không thỏa điều kiện UV nhưng policy bắt buộc UV. | Từ chối hoặc yêu cầu phương thức phù hợp. |
| Người dùng có khóa bảo mật đã đăng ký nhưng phiên không dùng khóa đó. | Không tự đánh giá phiên theo mức bảo đảm của khóa chưa dùng. |
| Access token mới phát hành bằng refresh token nhưng auth_time đã quá lâu. | Không coi iat là bằng chứng reauthentication mới; yêu cầu step-up. |
| Frontend gửi claim assurance giả hoặc header tự đặt. | Backend bỏ qua nếu không có xác nhận từ nguồn đáng tin. |
| ID token sai audience hoặc issuer, chữ ký không hợp lệ. | Ứng dụng từ chối assertion/token. |
| Session bị đánh cắp sau MFA. | Kiểm soát phiên và rủi ro giảm tác động; thao tác nhạy cảm yêu cầu lại assurance khi cần. |
| Reset MFA chỉ bằng thông tin công khai qua helpdesk. | Không cho phép; kích hoạt recovery được phê duyệt. |
| Role của nhân viên bị gỡ sau Mover nhưng token cũ còn claim quyền. | API kiểm quyền hiện hành hoặc áp cơ chế thu hồi theo SLA. |
| Leaver vẫn giữ cookie SaaS từ trước ngày nghỉ. | Phiên và API không được thực hiện hành động sau mốc thu hồi yêu cầu. |
| Người dùng có assurance cao nhưng không có role Finance. | Authorization từ chối hành động. |
| Job tự động không có người nhập MFA. | Dùng cơ chế workload authentication phù hợp; không tắt bảo mật hay dùng account cá nhân. |
| Hệ thống không truyền claim assurance qua federation. | Không phỏng đoán AAL; yêu cầu IdP/ứng dụng thiết lập trust contract hoặc phương án step-up khác. |

## 16. Audit và đo lường authentication assurance

Một quyết định assurance cần có **bằng chứng giải thích được** mà không tiết lộ bí mật:

| Loại sự kiện | Trường nên ghi (theo chính sách dữ liệu) | Câu hỏi kiểm toán |
| --- | --- | --- |
| Enrollment | Subject ID, authenticator reference, loại, phương pháp bootstrap, thời gian, kết quả. | Ai đăng ký authenticator, bằng kiểm tra nào? |
| Authentication | Subject, phương thức, assurance profile/claim đã kiểm, auth_time, IdP, kết quả. | Vì sao phiên đạt hoặc không đạt assurance? |
| Federation | Issuer, audience, protocol, token/assertion validation result, correlation ID. | Ứng dụng đã tin kết quả từ nguồn đúng chưa? |
| Step-up | Hành động yêu cầu, policy version, thời điểm yêu cầu/hoàn thành, kết quả. | Thao tác nhạy cảm có xác thực lại đủ mới không? |
| Recovery | Yêu cầu, nguồn xác minh, approval, authenticator bị thu hồi/thêm mới. | Có đường phục hồi yếu hơn policy không? |
| JML | Subject status, quyền trước/sau, account/session revoke, hệ thống đích. | Người chuyển vai trò/nghỉ việc còn đường truy cập không? |
| Policy exception | Người phê duyệt, lý do, phạm vi, hạn, kiểm soát bù trừ. | Ngoại lệ có bị kéo dài hoặc lạm dụng không? |

**Không ghi mật khẩu, OTP, TOTP seed, private key, recovery code, session cookie hay token thật vào log**. Nếu cần tương quan, dùng ID tham chiếu và metadata được phép, phân quyền log và retention phù hợp.

Các chỉ số hữu ích:

- **Phishing-resistant adoption:** tỷ lệ tài khoản thuộc phạm vi chính sách có authenticator chống phishing và sử dụng đúng cho giao dịch yêu cầu.
- **Assurance policy compliance:** tỷ lệ yêu cầu nhạy cảm được xử lý với assurance phù hợp.
- **Step-up success/failure:** phân tách lỗi người dùng, hỗ trợ thiết bị, policy và dấu hiệu tấn công.
- **Recovery bypass incidents:** trường hợp khôi phục/thay authenticator không theo policy.
- **Stale authentication attempts:** các yêu cầu có auth_time cũ phải step-up nhưng cố thực hiện.
- **Session/token residual exposure:** thời gian phiên cũ còn tác dụng sau Leaver, compromise hoặc revoke.
- **Federation claim coverage:** tỷ lệ ứng dụng có thể xác minh profile assurance cần thiết thay vì đoán.
- **Authenticator lifecycle drift:** phương thức cũ, mất, không owner hoặc không phù hợp vai trò mới.

Không chỉ đo tỷ lệ “MFA enabled”: tài khoản có OTP và recovery yếu có thể vẫn không đạt mục tiêu chống phishing; ngược lại, một phương thức mạnh nhưng chưa được sử dụng trong phiên hiện tại không chứng minh request đã đạt assurance.

## 17. Tình huống thực hành: nâng assurance khi Mover sang Finance

### Bối cảnh

Huy là nhân viên bán hàng thường đăng nhập SSO bằng mật khẩu và TOTP. Huy được chuyển sang Finance để phê duyệt thanh toán có giới hạn. Theo chính sách mới, nghiệp vụ này đòi hỏi **phương thức chống phishing, recent authentication** và role approver đã phê duyệt.

### Bước 1 – Đánh giá quyền và phương thức hiện có

IAM nhận sự kiện Mover từ HRIS. Tài khoản Huy đã hoàn thành identity proofing trước đây, nhưng các quyền Sales không còn phù hợp phải được gỡ. IdP ghi nhận Huy đã đăng ký TOTP, song chưa có authenticator đáp ứng profile chống phishing của nhóm Finance.

**Không mở quyền phê duyệt chỉ vì Huy đăng nhập bằng TOTP thành công**. Đồng thời, không cần xóa tài khoản IdP hoặc làm proofing lại từ đầu nếu không có lý do về danh tính.

### Bước 2 – Đăng ký và xác minh authenticator mới

Huy được yêu cầu đăng ký passkey/khóa bảo mật qua phiên enrollment đủ bảo đảm. IdP kiểm tra quá trình WebAuthn, RP ID, origin, challenge và user verification theo policy. Phương thức được liên kết với đúng subject ID và ghi audit. Nếu policy cao hơn yêu cầu bảo đảm phần cứng, tổ chức phải kiểm tra **loại authenticator và khả năng bảo vệ khóa**, không chỉ nhãn passkey.

### Bước 3 – Cấp quyền mới và thu hồi quyền cũ

IGA kiểm tra approval, SoD và gỡ các role/ACL Sales không còn hợp lệ. Nhóm Finance và role approver chỉ được cấp theo phạm vi cho phép. Ứng dụng Finance kiểm role trên **từng giao dịch**, không chỉ dựa vào việc Huy đăng nhập thành công.

### Bước 4 – Step-up cho giao dịch nhạy cảm

Khi Huy yêu cầu phê duyệt thanh toán, ứng dụng kiểm tra session context. Nếu phiên chỉ có TOTP hoặc auth_time đã quá giới hạn, ứng dụng yêu cầu step-up qua IdP. Sau khi IdP trả assurance context đã xác minh, backend vẫn kiểm số tiền, tenant, trạng thái và quy tắc không tự duyệt giao dịch của chính Huy.

### Bước 5 – Kiểm toán và Leaver về sau

Log cho biết phương thức đã dùng, auth_time, policy version, quyền và quyết định phê duyệt. Nếu Huy nghỉ việc, quyền Finance, session/refresh token và các app account phải bị thu hồi; **không để một phiên đã đạt assurance cao tiếp tục dùng được** sau thời điểm quyền bị chấm dứt.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Một tài khoản có passkey đã đăng ký nhưng phiên hiện tại đăng nhập bằng mật khẩu + TOTP. Có thể khẳng định phiên đã dùng phương thức chống phishing không?

**Trả lời:** Không. Mức assurance phải dựa trên phương thức thực sự được sử dụng và kiểm chứng trong phiên, không chỉ danh sách authenticator đã đăng ký.

**Câu 2.** MFA có đồng nghĩa AAL3 không?

**Trả lời:** Không. AAL3 có các yêu cầu chặt chẽ hơn theo tiêu chuẩn áp dụng; một tổ hợp MFA bất kỳ không tự đạt AAL3.

**Câu 3.** Vì sao một OTP đúng không nhất thiết chống phishing?

**Trả lời:** Kẻ tấn công có thể dụ người dùng nhập OTP vào trang giả và chuyển tiếp mã còn hạn tới verifier thật. WebAuthn có cơ chế ràng buộc với RP/origin để giảm kiểu tấn công đó.

**Câu 4.** Vì sao nên dùng auth_time thay vì iat khi kiểm độ mới của MFA?

**Trả lời:** Token có thể được phát hành lại mà không yêu cầu xác thực người dùng mới. auth_time, khi được IdP cung cấp và xác minh đúng, phản ánh thời điểm sự kiện xác thực; iat chỉ phản ánh lúc token được phát hành.

**Câu 5.** Nhân viên đã xác thực bằng khóa bảo mật có được phép xem dữ liệu Finance ngoài tenant của mình không?

**Trả lời:** Không. Assurance kiểm tra độ tin cậy xác thực, còn authorization phải kiểm role, action, tenant và resource theo chính sách.

**Câu 6.** Vì sao reset MFA qua helpdesk là một điểm cần bảo vệ đặc biệt?

**Trả lời:** Nếu kẻ mạo danh có thể đăng ký yếu tố mới chỉ bằng thông tin dễ đoán, họ có thể bỏ qua authenticator mạnh. Recovery cần bảo đảm, approval và audit phù hợp.

**Câu 7.** Khóa IdP khi Leaver có bảo đảm mọi ứng dụng mất quyền ngay lập tức không?

**Trả lời:** Không. Một số SaaS dùng session riêng, access token tự chứa hoặc quyền cục bộ. Cần xử lý và kiểm chứng deprovisioning tại từng điểm thực thi.

**Câu 8.** Tại sao không nên bắt một job tự động nhập OTP để gọi API?

**Trả lời:** Xác thực workload phi con người cần cơ chế máy đến máy như managed identity, federation hoặc mTLS. MFA người dùng nên bảo vệ người quản trị workload, không thay thế quản trị credential và quyền của job.

---

**Ghi nhớ:** Authentication assurance là **mức độ tin cậy của bằng chứng xác thực trong một phiên hoặc hành động**, không phải huy hiệu vĩnh viễn trên tài khoản. Hệ thống IAM cần kết hợp **đúng danh tính, authenticator đã đăng ký an toàn, cơ chế chống tấn công, phiên còn hiệu lực, reauthentication/step-up khi cần** và **authorization độc lập**. Trong vòng đời **Joiner–Mover–Leaver**, mức assurance phải được đánh giá lại khi quyền và rủi ro thay đổi, đồng thời không được trở thành lý do duy trì quyền truy cập sau khi danh tính đã bị thu hồi.
