# Phishing-resistant MFA — Xác thực đa yếu tố chống giả mạo verifier

## 1. Vì sao bật MFA chưa đủ để kết luận chống phishing?

MFA yêu cầu nhiều loại bằng chứng xác thực, chẳng hạn mật khẩu kết hợp mã từ ứng dụng authenticator. Điều này giảm khả năng chiếm tài khoản khi đối thủ chỉ có mật khẩu. Tuy nhiên, nếu người dùng có thể đưa cả mật khẩu và mã dùng một lần cho một trang giả, đối thủ vẫn có thể chuyển tiếp chúng đến hệ thống thật.

Phishing-resistant MFA bổ sung một yêu cầu quan trọng: giao thức xác thực phải khiến bằng chứng không thể được sử dụng hữu hiệu tại một verifier giả để đăng nhập thay người dùng vào verifier thật. Sự bảo vệ này đến từ cơ chế của giao thức, thay vì phụ thuộc hoàn toàn vào việc người dùng nhận ra tên miền giả.

NIST định nghĩa phishing resistance theo khả năng ngăn tiết lộ bí mật và đầu ra xác thực hợp lệ cho verifier giả mà không dựa vào sự cảnh giác của người dùng. Các phương thức nhập thủ công OTP không được xem là phishing-resistant vì đầu ra có thể được chuyển tiếp. [Nguồn: NIST SP 800-63B-4, Phishing Resistance](https://pages.nist.gov/800-63-4/sp800-63b.html#phishing).

Trong bài học này, mục tiêu là hiểu ràng buộc mật mã tạo ra đặc tính đó, lựa chọn luồng MFA thích hợp và giữ chính sách nhất quán từ đăng nhập đến recovery, phiên và quyền đặc quyền.

## 2. Một mã dùng một lần vẫn có thể bị chuyển tiếp

Xét một tình huống giả định: An cần đăng nhập cổng quản trị. Đối thủ gửi cho An một trang có giao diện giống cổng thật, rồi chuyển tiếp dữ liệu An nhập đến hệ thống thật.

```text
An nhập mật khẩu và OTP
          ↓
Trang giả do đối thủ kiểm soát
          ↓ chuyển tiếp khi mã còn hiệu lực
Endpoint xác thực thật
          ↓
Phiên được cấp trong luồng mà đối thủ kiểm soát
```

TOTP chỉ còn hiệu lực trong một khoảng thời gian và có thể được kiểm soát chống dùng lại. Nhưng lần sử dụng đầu tiên vẫn có thể là lần đối thủ chuyển tiếp mã. “Dùng một lần” và “chỉ dùng được cho verifier đúng” là hai thuộc tính khác nhau.

Tương tự, thao tác phê duyệt push có thể bị lừa hoặc bị khai thác bằng cách gửi nhiều yêu cầu khiến người dùng bấm chấp nhận. Number matching giúp người dùng đối chiếu ngữ cảnh và giảm một số kiểu phê duyệt nhầm; bản thân việc đối chiếu số không đủ để kết luận giao thức đã ràng buộc mật mã với verifier đúng.

HTTPS trên trang giả cũng không giải quyết tình huống này. Nó có thể bảo vệ kết nối của An với chính trang giả, trong khi trang đó vẫn do đối thủ kiểm soát. Biểu tượng kết nối được mã hóa không phải bằng chứng rằng người dùng đang tương tác với đúng dịch vụ mình định truy cập.

## 3. Ràng buộc mật mã với verifier

NIST nêu hai cách tạo phishing resistance: channel binding và verifier name binding. Cách thứ nhất gắn bằng chứng với kênh xác thực cụ thể; cách thứ hai gắn nó với định danh verifier đã được xác thực. WebAuthn là ví dụ của verifier name binding; TLS xác thực bằng chứng chỉ client là một ví dụ của channel binding. [Nguồn: NIST, Phishing Resistance](https://pages.nist.gov/800-63-4/sp800-63b.html#phishing).

Để hình dung khác biệt, so sánh hai câu sau:

```text
OTP được nhập lại:
“Đây là mã hiện tại mà tôi đang có.”

Bằng chứng gắn với verifier và challenge:
“Tôi kiểm soát khóa đã đăng ký cho dịch vụ này,
và đang trả lời yêu cầu xác thực cụ thể của dịch vụ đó.”
```

Đây là cách diễn giải để học, không phải định dạng dữ liệu thực của giao thức. Điểm cần giữ là một response hợp lệ không chỉ mang dấu hiệu “người dùng có một bí mật”, mà còn có ràng buộc mà verifier có thể kiểm tra.

Một challenge ngẫu nhiên giúp ngăn phát lại response cũ. Ràng buộc verifier giúp ngăn dùng response ở sai dịch vụ. Kiểm tra chủ sở hữu credential giúp ngăn dùng một credential hợp lệ để đăng nhập nhầm tài khoản. Các kiểm tra này giải quyết những vấn đề khác nhau và phải phối hợp với nhau.

## 4. So sánh các phương thức theo luồng thực tế

| Phương thức | Có thể tạo MFA trong cấu hình thích hợp? | Đặc tính cần lưu ý khi đánh giá phishing |
| --- | --- | --- |
| Mật khẩu và SMS OTP | Có | Mã nhập tay có thể bị chuyển tiếp; còn có rủi ro ở số điện thoại |
| Mật khẩu và TOTP | Có | Mã không tự ràng buộc với verifier mà người dùng đang nhìn thấy |
| Mật khẩu và push approval | Có | Phải xét giao thức và ngữ cảnh phê duyệt; nút chấp nhận đơn thuần chưa đủ |
| Mật khẩu và hardware OTP token | Có | Thiết bị vật lý vẫn có thể chỉ tạo mã nhập tay có thể bị phishing |
| Mật khẩu và khóa FIDO/WebAuthn phù hợp | Có | Có thể dùng ràng buộc verifier của giao thức; backend phải xác minh đúng |
| Passkey có user verification phù hợp | Có thể thay luồng mật khẩu cộng factor bổ sung | Cần đánh giá UV, khả năng authenticator và chính sách thực tế |
| Chứng chỉ client với cơ chế kích hoạt phù hợp | Có thể | Cần xét cả channel binding, bảo vệ khóa và yếu tố kích hoạt |

Đây là bảng phân tích kiến trúc, không phải danh sách chứng nhận sản phẩm. Hai thiết bị cùng có cổng USB có thể triển khai hai giao thức hoàn toàn khác nhau: một thiết bị xuất OTP để nhập lại, thiết bị kia tạo chữ ký gắn với dịch vụ. Hình dáng phần cứng không quyết định phishing resistance.

MFA bằng OTP vẫn có giá trị trong việc giảm rủi ro từ mật khẩu bị lộ. Khi yêu cầu là chống chuyển tiếp qua verifier giả, cần thêm cơ chế đáp ứng đúng yêu cầu đó, thay vì chỉ tăng số bước người dùng phải thực hiện.

## 5. WebAuthn tạo khác biệt như thế nào?

WebAuthn sử dụng credential khóa công khai có phạm vi Relying Party. Trong lần xác thực, authenticator tạo assertion; server kiểm tra bằng khóa công khai đã gắn với tài khoản. Dữ liệu được kiểm tra bao gồm challenge, origin, RP ID và chữ ký, cùng các điều kiện của ceremony. [Nguồn: W3C WebAuthn, Verifying an Authentication Assertion](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion).

Ví dụ cấu hình giả định của một dịch vụ:

```text
Origin hợp lệ: https://login.example.test
RP ID:         example.test
Trang giả:     https://login-example.test
```

Trình duyệt tuân thủ giao thức không cho trang giả tự sử dụng credential của RP hợp lệ chỉ bằng cách yêu cầu một RP ID không thuộc phạm vi được phép. Nếu đối thủ dùng credential của chính tên miền giả, assertion cũng không đáp ứng các kiểm tra kỳ vọng của RP thật.

Tại server, không được bỏ kiểm tra origin vì “trình duyệt đã xử lý rồi”. Không lấy origin được chấp nhận hoặc RP ID kỳ vọng trực tiếp từ request chưa tin cậy. Đó phải là cấu hình của dịch vụ và các trường hợp triển khai đã được cho phép rõ ràng.

RP ID và origin không đồng nghĩa. Một RP ID có thể bao phủ phạm vi tên miền phù hợp với nhiều origin được cho phép; vì vậy việc quản lý subdomain, origin và những ứng dụng được tin cậy trong cùng phạm vi là một phần của thiết kế.

Trong hệ thống giả định, nhóm phát triển chọn kiểm tra ở backend theo các nhóm sau:

| Nhóm kiểm tra | Sai sót mà nó cần ngăn |
| --- | --- |
| Giao dịch đang chờ và challenge | Response cũ, hết hạn hoặc thuộc yêu cầu khác |
| Loại ceremony và origin kỳ vọng | Dùng sai loại response hoặc response từ ngữ cảnh không được chấp nhận |
| RP ID và dữ liệu authenticator | Bằng chứng cho sai phạm vi dịch vụ |
| Credential và chủ sở hữu | Dùng credential của tài khoản hoặc tenant khác |
| Chữ ký và thuật toán | Bằng chứng không hợp lệ theo credential đã lưu |
| User verification và yêu cầu chính sách | Chấp nhận một lần xác thực chưa đáp ứng mức bảo vệ cần thiết |

Thư viện WebAuthn server cần thực thi đầy đủ đặc tả, gồm cả các trường hợp mở rộng, user handle và trạng thái credential tương ứng; bảng trên không thay thế thuật toán xác minh của chuẩn. Không tự viết một bộ kiểm tra chỉ gồm “chữ ký đúng” rồi coi đó là WebAuthn hoàn chỉnh.

## 6. User presence, user verification và số yếu tố

User presence thường thể hiện sự tham gia của người dùng vào thao tác, chẳng hạn chạm khóa bảo mật. User verification là kiểm tra người dùng cục bộ, có thể thông qua PIN hoặc sinh trắc theo khả năng authenticator. Hai thuộc tính này không thể thay thế cho nhau khi chính sách yêu cầu UV.

Một khóa chỉ yêu cầu chạm có thể được dùng cùng mật khẩu trong một luồng MFA. Một authenticator bảo vệ quyền sử dụng khóa bằng PIN hoặc sinh trắc có thể tham gia luồng passwordless nhiều yếu tố theo cấu hình và bằng chứng thích hợp. Không suy ra số factor chỉ từ số màn hình hoặc số lần bấm.

FIDO mô tả passkey có thể nằm trên thiết bị hoặc được đồng bộ giữa các thiết bị. Khi dùng sinh trắc để mở quyền sử dụng passkey, dữ liệu sinh trắc được xử lý tại thiết bị, không gửi mẫu sinh trắc cho website. [Nguồn: FIDO Alliance, Passkeys FAQ](https://fidoalliance.org/passkeys/).

Backend phải dựa vào kết quả giao thức đã xác minh và đặc tính được chấp nhận. Chuỗi `userVerified=true` do frontend tự gửi không tương đương với việc kiểm tra UV trong authenticator data hợp lệ.

Tên “Face login”, “khóa phần cứng” hoặc “đăng nhập bằng vân tay” trên giao diện cũng chưa đủ mô tả mức bảo vệ. Cần biết bằng chứng nào được tạo, nó có bị chuyển tiếp sang verifier khác không và nó đáp ứng chính sách MFA nào.

## 7. Passkey đồng bộ, khóa gắn thiết bị và mức assurance

Một passkey đồng bộ có thể giữ phishing resistance của giao thức khi sử dụng đúng. Khả năng đồng bộ không tự biến nó thành OTP có thể nhập vào một website bất kỳ. Tuy nhiên, việc quản lý và khôi phục tài khoản của nhà cung cấp passkey tạo thêm các phụ thuộc cần được đánh giá.

Với credential gắn thiết bị, tổ chức phải có cách xử lý mất hoặc hỏng thiết bị. Nếu quy trình khôi phục chỉ cần một cuộc gọi không được xác minh, lợi ích của khóa được bảo vệ tốt có thể bị đường vòng này làm suy yếu.

Không tự gán AAL3 cho mọi passkey hoặc mọi khóa USB. NIST yêu cầu tại AAL3 authenticator chống phishing và khóa riêng không xuất được; khóa của authenticator đồng bộ vốn có khả năng xuất ra ngoài ranh giới thiết bị. AAL3 còn có các yêu cầu khác ngoài hai điều kiện này. [Nguồn: NIST SP 800-63B-4, AAL3 và Non-Exportable Keys](https://pages.nist.gov/800-63-4/sp800-63b.html#aal3).

Đối với một hệ thống IAM cụ thể, nên ghi rõ các đặc tính chính sách cần biết: có yêu cầu UV hay không, có cho phép đồng bộ không, có yêu cầu bằng chứng về phần cứng không, xử lý credential mất như thế nào và ai có quyền thay đổi các yêu cầu đó.

Attestation có thể cung cấp thông tin phục vụ đánh giá authenticator, nhưng không nên suy ra model phần cứng từ tên hiển thị người dùng nhập. Tương tự, không có attestation đáng tin không có nghĩa là giao thức tự mất mọi đặc tính chống phishing; nó giới hạn những kết luận có thể đưa ra về nguồn gốc và thuộc tính thiết bị.

## 8. Chính sách phải dựa trên lần xác thực đã xảy ra

Một tài khoản có passkey đã đăng ký không có nghĩa là phiên hiện tại đã dùng passkey. Người dùng có thể vừa đăng nhập bằng TOTP hoặc vừa hoàn tất một luồng recovery hạn chế.

Ví dụ, cổng quản trị chọn quy tắc: thay đổi vai trò quản trị cần một lần xác thực chống phishing gần đây, đáp ứng MFA của chính sách và thuộc đúng người thực hiện. Backend cần một ngữ cảnh xác thực do server quản lý, chẳng hạn:

```text
subject_id
tenant_id
verified_authentication_method
mfa_policy_satisfied
phishing_resistance_verified
user_verification_result
authentication_time
credential_reference
authentication_policy_version
```

Đây là mô hình nội bộ minh họa, không phải schema chuẩn của WebAuthn hay OIDC. Các giá trị phải được dẫn xuất từ kết quả xác minh hoặc nguồn danh tính tin cậy, không lấy nguyên boolean do client khai báo.

Mã giả đánh giá thao tác có thể là:

```text
authorizeSensitiveAction(actor, action, authContext):
    requireAccountActive(actor)
    requirePermission(actor, action)
    requireSameSubjectAndTenant(actor, authContext)
    requireTrustedAndCurrentAuthContext(authContext)

    if not authContext.satisfiesMfaPolicy(action):
        requireStepUpAuthentication
    if not authContext.hasVerifiedPhishingResistance():
        requireStepUpAuthentication
    if not authContext.isFreshEnoughFor(action):
        requireStepUpAuthentication

    allowOnlyTheAuthorizedAction
```

`requireStepUpAuthentication` biểu thị dừng thao tác hiện tại và yêu cầu luồng xác thực bổ sung; không cho hành động tiếp tục rồi mới hiện cảnh báo. Sau step-up, vẫn phải kiểm tra lại quyền, tài khoản và ngữ cảnh hành động.

Xác thực chống phishing chứng minh một đặc tính của đăng nhập, không tự ký nội dung mọi giao dịch sau đó. Nếu thao tác yêu cầu phê duyệt chính xác số tiền, người nhận hoặc thay đổi quyền cụ thể, cần thêm thiết kế ràng buộc nội dung phê duyệt tương ứng.

## 9. SSO/OIDC phải chuyển được bằng chứng phù hợp

Trong mô hình SSO, IdP có thể trực tiếp thực hiện WebAuthn, còn ứng dụng chỉ nhận kết quả qua OIDC. Ứng dụng cần biết lần xác thực tại IdP đáp ứng yêu cầu gì trước khi cấp phiên hoặc quyền thao tác nhạy cảm.

OIDC định nghĩa `acr` cho authentication context, `amr` cho phương thức xác thực và `auth_time` cho thời điểm xác thực. Ý nghĩa mức bảo vệ phải được thống nhất với IdP; không có quy tắc chung rằng mọi chuỗi `mfa` đều có nghĩa là chống phishing. `acr_values` trong request thể hiện giá trị được yêu cầu ưu tiên và tự nó không chứng minh kết quả đã đáp ứng. [Nguồn: OpenID Connect Core 1.0, ID Token và Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#IDToken).

Trong thiết kế cổng quản trị, ứng dụng phải xác minh token theo luồng OIDC, bao gồm nguồn phát hành, đối tượng nhận và các ràng buộc giao dịch cần thiết, rồi kiểm tra authentication context thực nhận theo hợp đồng với IdP. Thiếu bằng chứng cần thiết thì yêu cầu xác thực phù hợp hoặc từ chối thao tác.

Không dựa vào một access token chỉ được decode mà chưa được xác minh để gán mức xác thực. Cũng không đánh đồng thời điểm phát hành token mới với thời điểm người dùng vừa xác thực lại: token có thể được cấp lại từ một phiên đã tồn tại.

Các đường đăng nhập cục bộ dự phòng, tài khoản hỗ trợ và tích hợp cũ phải được kiểm kê. Nếu chúng vẫn cấp cùng quyền quản trị sau một luồng yếu hơn, yêu cầu ở nút “đăng nhập SSO bằng passkey” chưa bao phủ toàn bộ đường truy cập.

## 10. Binding, fallback và recovery là một phần của phạm vi bảo vệ

Một đối thủ không nhất thiết phải phá WebAuthn. Họ có thể tìm cách gắn credential của mình vào tài khoản, dùng phương thức dự phòng yếu hơn hoặc thuyết phục hỗ trợ bỏ MFA.

Vì vậy, khi triển khai phishing-resistant MFA cần bảo vệ cả quyền đăng ký và thay credential. Một phiên có sẵn chưa chắc đủ để thêm khóa mới; cần xác thực lại phù hợp, kiểm tra rủi ro và thông báo thay đổi. OWASP xem thay factor là thao tác nhạy cảm cần bảo vệ riêng. [Nguồn: OWASP Multifactor Authentication Cheat Sheet, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

Đối với cổng quản trị giả định, một chính sách nhất quán có thể gồm:

- Luồng quản trị thông thường yêu cầu phương thức chống phishing đáp ứng chính sách MFA.
- Người dùng đăng ký phương tiện dự phòng phù hợp trước khi cần sử dụng recovery.
- Recovery không tự cấp ngay phiên quản trị đầy đủ nếu chưa có bằng chứng đáp ứng yêu cầu.
- Sau recovery, thay đổi credential và phiên được đánh giá theo phạm vi nghi bị xâm phạm.
- Ngoại lệ khẩn cấp có người chịu trách nhiệm, phạm vi, thời hạn và bằng chứng kiểm toán.

Không cần xóa mọi lựa chọn dự phòng một cách thiếu kế hoạch. Cần xác định mỗi lựa chọn được phép đưa người dùng đến trạng thái nào và quyền nào. Một luồng giúp khôi phục quyền thiết lập credential có thể hữu ích mà không được phép vượt thẳng vào chức năng quản trị.

Nếu sản phẩm cho phép “thử cách khác”, giao diện và backend phải áp dụng cùng chính sách. Không để frontend yêu cầu khóa bảo mật trong khi endpoint API vẫn cấp cùng phiên sau SMS OTP.

## 11. Những nguy cơ vẫn phải xử lý sau đăng nhập

Phishing-resistant MFA tập trung vào giao thức xác thực. Nó không tự bảo vệ mọi thành phần của một hệ thống IAM.

| Nguy cơ còn lại | Vì sao cần cơ chế bổ sung |
| --- | --- |
| Cookie hoặc bearer token bị lấy cắp sau đăng nhập | Đối thủ có thể dùng credential phiên mà không lặp lại lễ xác thực ban đầu |
| Mã độc trên endpoint hoặc trình duyệt bị kiểm soát | Môi trường tin cậy của người dùng có thể bị quan sát hoặc điều khiển |
| Lỗ hổng ứng dụng hoặc origin hợp lệ bị xâm phạm | Phương thức xác thực không sửa được logic ứng dụng bị chiếm |
| Cấp quyền RBAC/ABAC quá rộng | Đăng nhập đúng vẫn có thể được cấp quá nhiều quyền |
| Lừa người dùng ủy quyền ứng dụng không mong muốn | Đăng nhập hợp lệ không tự chứng minh quyết định cấp consent là đúng |
| Recovery hoặc hỗ trợ bị lợi dụng | Đối thủ có thể đổi đường kiểm soát tài khoản mà không phá giao thức đăng nhập |

Cần phối hợp bảo vệ phiên, quản lý endpoint, kiểm soát ứng dụng, ít quyền nhất và kiểm toán. Không nên mô tả sản phẩm là “không thể bị phishing” chỉ vì đã bổ sung một loại authenticator.

Một phiên được tạo sau WebAuthn cũng không tự trở thành token ràng buộc thiết bị. Nếu đó vẫn là bearer token, việc bảo vệ lưu trữ, truyền tải, thời hạn và thu hồi token vẫn cần được thiết kế riêng.

## 12. Triển khai theo mức độ rủi ro và khả năng vận hành

Nhóm IAM có thể bắt đầu bằng những đường có tác động lớn: quản trị danh tính, thay quyền, quản lý secret và truy cập hệ thống nhạy cảm. Trước khi bắt buộc sử dụng, cần bảo đảm người dùng có phương tiện phù hợp và một quy trình hỗ trợ hoạt động được.

Một kế hoạch cho cổng quản trị có thể đi theo các bước:

1. Kiểm kê mọi đường đăng nhập và cấp quyền tương đương, gồm cả cục bộ, SSO, API và dự phòng.
2. Chọn đặc tính authenticator được chấp nhận cho từng loại thao tác và xác định bằng chứng backend sẽ kiểm tra.
3. Thiết lập phương tiện chính, dự phòng và quy trình thu hồi; bảo vệ binding như một thay đổi credential.
4. Áp dụng yêu cầu ở backend và tại ranh giới federation, không chỉ ở giao diện.
5. Theo dõi thất bại, recovery, ngoại lệ và các lần dùng phương thức không đáp ứng yêu cầu.

Trong giai đoạn chuyển đổi, có thể hỗ trợ nhiều phương thức nhưng phải phân biệt quyền mà mỗi phiên được sử dụng. Không gán nhãn chống phishing cho toàn bộ tài khoản khi người dùng vẫn được vào cùng chức năng bằng phương thức cũ.

Audit nên ghi phương thức thực dùng, chính sách được áp dụng, kết quả kiểm tra và thời điểm cần thiết. Không ghi OTP, private key, token phiên hoặc payload credential nguyên vẹn để debug.

## 13. Tình huống kiểm chứng thiết kế

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Response cho challenge đã dùng được gửi lại | Bị từ chối cho lần xác thực mới |
| Assertion có chữ ký đúng nhưng origin không được chấp nhận | Bị từ chối |
| Credential hợp lệ thuộc tài khoản hoặc tenant khác | Không đăng nhập hoặc nâng quyền cho chủ thể hiện tại |
| Chính sách yêu cầu UV nhưng response không đáp ứng | Không cấp mức xác thực yêu cầu |
| Tài khoản có passkey nhưng phiên hiện tại chỉ dùng OTP | Không tự coi phiên là chống phishing |
| SSO trả context thấp hơn mức ứng dụng yêu cầu | Step-up hoặc từ chối theo chính sách |
| Người dùng chuyển sang SMS ở luồng dự phòng | Không nhận cùng quyền nếu SMS không đáp ứng yêu cầu của thao tác |
| Hoàn tất recovery nhưng chưa đáp ứng xác thực cho quản trị | Chỉ có quyền recovery hoặc thiết lập đã được cho phép |
| Token phiên bị thu hồi sau sự cố | Các thành phần truy cập thực sự áp dụng trạng thái thu hồi |
| Mất thiết bị xác thực chính | Có đường dự phòng được thiết kế trước và được kiểm toán |

Các thử nghiệm cần thực hiện trong môi trường được phép với tài khoản và tên miền thử nghiệm. Mục tiêu là kiểm tra chính sách và các ràng buộc giao thức, không chỉ xác nhận rằng nút đăng nhập bằng passkey hoạt động ở luồng thành công.

## 14. Bài tập vận dụng

Một doanh nghiệp đã bổ sung WebAuthn tại IdP, nhưng ứng dụng quản trị chỉ kiểm tra claim chung `mfa`. Người dùng có thể chuyển sang TOTP và vẫn nhận cùng quyền. Bộ phận hỗ trợ còn có thể bỏ MFA sau khi hỏi ngày sinh; cookie phiên quản trị tồn tại lâu và không được đánh giá lại khi credential thay đổi.

Hãy thiết kế lại chính sách và trả lời:

1. Ứng dụng cần bằng chứng nào để phân biệt một lần MFA có thể bị chuyển tiếp với lần xác thực chống phishing?
2. Phần nào thuộc kiểm tra WebAuthn tại IdP, phần nào thuộc hợp đồng OIDC và phân quyền tại ứng dụng?
3. Luồng dự phòng và recovery được phép cấp những quyền gì trước khi người dùng đáp ứng lại chính sách?
4. Vì sao việc bảo vệ cookie và thu hồi phiên vẫn cần thiết sau khi đã triển khai WebAuthn?
5. Cần kiểm chứng những đường truy cập nào trước khi công bố chức năng quản trị đã bắt buộc phishing-resistant MFA?

Phương án cần làm rõ giao thức, bằng chứng của lần xác thực và nơi thực thi yêu cầu. Số yếu tố, loại thiết bị và nhãn trên giao diện chỉ có ý nghĩa khi chúng phản ánh đúng những ràng buộc mà backend thực sự xác minh.
