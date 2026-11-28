# MFA factor binding — Gắn phương tiện xác thực vào đúng tài khoản

## 1. Binding là một thao tác thay đổi quyền kiểm soát danh tính

MFA factor binding là quá trình thiết lập liên kết giữa một tài khoản và một phương tiện xác thực được phép tham gia xác thực cho tài khoản đó. Trong giao diện sản phẩm, quá trình này thường mang tên “thêm ứng dụng xác thực”, “đăng ký khóa bảo mật” hoặc “thêm passkey”.

NIST dùng thuật ngữ authenticator binding để chỉ liên kết một authenticator cụ thể với tài khoản người dùng. Hệ thống cần giữ bản ghi liên kết và các đặc tính cần thiết để đánh giá khả năng xác thực của authenticator. [Nguồn: NIST SP 800-63B-4, Authenticator Binding](https://pages.nist.gov/800-63-4/sp800-63b.html#bind).

Trong bài học, “factor” được dùng theo cách gọi phổ biến trên giao diện, nhưng cần phân biệt hai khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Authentication factor | Loại bằng chứng được sử dụng | Điều người dùng biết, sở hữu hoặc đặc điểm sinh trắc |
| Authenticator | Phương tiện cụ thể tạo hoặc kiểm tra bằng chứng | Ứng dụng giữ seed TOTP, khóa bảo mật, credential WebAuthn |
| Binding | Liên kết cho phép một authenticator xác thực cho một tài khoản | Credential `cred-A` thuộc tài khoản `u-104` trong tenant `t-7` |

Hai mật khẩu không tự tạo thành hai loại factor. Hai ứng dụng cùng giữ một seed TOTP cũng không trở thành hai bí mật độc lập chỉ vì có hai biểu tượng trên điện thoại. Khi thiết kế IAM, cần xét cơ chế và khả năng thực tế, thay vì đếm số dòng trong màn hình “phương thức đăng nhập”.

Binding quan trọng vì nó thay đổi những phương tiện có thể được dùng để kiểm soát tài khoản. Bảo vệ bước đăng nhập bằng MFA sẽ mất ý nghĩa nếu kẻ tấn công có thể dễ dàng thêm authenticator của mình qua một endpoint quản lý yếu hơn.

## 2. Hai câu hỏi độc lập phải được trả lời

Một lần binding thành công phải giải quyết cả hai câu hỏi sau:

1. **Ai được phép thay đổi phương tiện xác thực của tài khoản này?** Đây là quyết định về chủ thể, quyền thực hiện, độ mới của xác thực và chính sách rủi ro.
2. **Phương tiện mới có được thiết lập và xác minh đúng không?** Đây là kiểm tra giao thức, dữ liệu credential, bằng chứng cần thiết và trạng thái đăng ký.

Giả sử đối thủ lấy được cookie phiên của người dùng An. Họ mở trang thêm ứng dụng TOTP, nhận seed mới, quét vào điện thoại của mình và nhập đúng mã do seed đó sinh ra.

Mã TOTP đúng chứng minh người đang thao tác có thể tạo mã từ seed mới. Nó không chứng minh đó là An, vì đối thủ chính là người vừa nhận seed. Nếu server coi “có phiên đăng nhập và nhập đúng mã mới” là đủ trong mọi trường hợp, đối thủ có thể thiết lập một đường truy cập lâu dài.

Theo OWASP, thay đổi factor cần được bảo vệ bằng xác thực lại với factor đã đăng ký phù hợp, không chỉ dựa vào phiên đang hoạt động; kiểm tra rủi ro và thông báo độc lập cũng giúp phát hiện thay đổi trái phép. [Nguồn: OWASP Multifactor Authentication Cheat Sheet, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

## 3. Phân biệt thiết lập ban đầu, thêm mới và recovery

Không thể yêu cầu mọi người xác thực bằng một factor cũ khi họ chưa có factor nào. Thay vào đó, hệ thống phải xác định hoàn cảnh và bằng chứng cho từng luồng.

| Hoàn cảnh | Vấn đề phải giải quyết | Hướng thiết kế |
| --- | --- | --- |
| Thiết lập authenticator đầu tiên | Chưa có factor bổ sung để xác thực lại | Dựa vào quy trình cấp tài khoản và mức xác thực hiện có, hạn chế quyền trước khi hoàn tất nếu chính sách yêu cầu |
| Thêm authenticator khi tài khoản đã có MFA | Ngăn phiên bị chiếm tự thêm thiết bị | Yêu cầu xác thực lại phù hợp bằng phương tiện hiện có và kiểm tra rủi ro |
| Thay thiết bị nhưng còn một phương thức hợp lệ | Giữ liên tục quyền truy cập và loại thiết bị cũ | Xác thực lại, binding thiết bị mới, rồi thu hồi thiết bị cũ theo một kế hoạch rõ ràng |
| Mất toàn bộ phương thức sử dụng được | Không thể đi theo đường quản lý thông thường | Dùng recovery được thiết kế riêng trước khi cấp quyền binding |
| Quản trị viên hỗ trợ người dùng | Người thao tác không phải chủ tài khoản | Dùng quyền và quy trình hỗ trợ riêng, có kiểm toán và giới hạn hành động |

Đối với việc thêm authenticator sau enrollment, NIST yêu cầu mức xác thực dựa trên mức AAL cao nhất tài khoản hiện có và mức AAL cao nhất authenticator mới sẽ được dùng, lấy mức thấp hơn trong hai mức đó. Không diễn giải quy tắc này thành “luôn phải có MFA trước khi được thiết lập MFA lần đầu”. [Nguồn: NIST, Binding an Additional Authenticator](https://pages.nist.gov/800-63-4/sp800-63b.html#post-enroll-bind).

Một phiên chỉ được cấp quyền thiết lập ban đầu không nên mặc nhiên được sử dụng để truy cập mọi dữ liệu nhạy cảm. Tương tự, quyền binding sau recovery cần xuất phát từ kết quả recovery đã được xác minh, không xuất phát từ một cờ `recovery=true` do client gửi lên.

## 4. Thiết kế trạng thái: đang đăng ký chưa phải đã kích hoạt

Một lỗi phổ biến là bật `mfaEnabled=true` ngay khi server tạo QR code. Ở thời điểm đó, người dùng có thể chưa quét QR, quét nhầm tài khoản hoặc đã đóng trình duyệt.

Có thể tách hai loại bản ghi:

```text
Enrollment transaction:
PENDING ── xác minh và commit thành công ──> CONFIRMED
   ├── hết hạn ──> EXPIRED
   ├── người dùng hủy ──> CANCELLED
   └── vượt ngân sách thử ──> FAILED

Authenticator binding:
ACTIVE ── thu hồi ──> REVOKED
```

Các tên trạng thái trên là mô hình minh họa cho bài học. Điều quan trọng là các quy tắc bất biến:

- Chỉ binding `ACTIVE` được xét cho các lần xác thực tiếp theo.
- Giao dịch enrollment chưa hoàn tất không làm tăng số factor sử dụng được.
- Giao dịch đã hết hạn hoặc bị hủy không được kích hoạt bằng một response đến muộn.
- Thu hồi một authenticator không được tự động khôi phục chỉ vì client gửi lại thông tin cũ.
- Trạng thái “tài khoản đáp ứng MFA” phải được đánh giá theo chính sách và các phương thức thực sự hợp lệ.

Với luồng WebAuthn, server chỉ tạo binding hợp lệ sau khi xử lý thành công registration ceremony. Với luồng TOTP trong ví dụ, server chỉ kích hoạt sau khi xác nhận mã từ seed mới. Không dùng cùng một kiểm tra “client đã bấm xong” cho hai loại giao thức khác nhau.

## 5. Ràng buộc một giao dịch vào đúng ngữ cảnh

Một enrollment ID ngẫu nhiên giúp hạn chế việc đoán định danh, nhưng định danh khó đoán không thay thế kiểm tra quyền sở hữu.

Ví dụ bản ghi giao dịch phía server:

```text
enrollment_id
tenant_id
account_id
factor_type
purpose = ENROLL_AUTHENTICATOR
session_binding
reauth_event_id
auth_methods_version
created_at
expires_at
state
attempt_count
challenge_or_setup_material_reference
```

`tenant_id` và `account_id` phải đến từ ngữ cảnh đã được server xác minh. Nếu URL hoặc request body chứa các giá trị này, server vẫn phải kiểm tra chúng với chủ thể thực hiện; không cho client chọn tự do tài khoản đích.

`reauth_event_id` tham chiếu bằng chứng xác thực lại đã xảy ra, bao gồm thời điểm và phương thức phù hợp. Giá trị này không phải một chuỗi mà client có thể tự khai để vượt qua kiểm tra. `auth_methods_version` giúp phát hiện danh sách authenticator đã thay đổi giữa lúc bắt đầu và xác nhận.

Trong ví dụ của bài, enrollment được hoàn tất trong cùng ngữ cảnh phiên đã bắt đầu nó. Nếu sản phẩm hỗ trợ binding qua hai thiết bị hoặc hai endpoint, cần thiết kế một giao thức phê duyệt riêng có ràng buộc tài khoản, mục đích, thời hạn và tính dùng một lần; không đơn giản bỏ kiểm tra phiên để luồng đó “chạy được”.

Challenge cũng cần phân biệt mục đích. Response của một yêu cầu đăng nhập không được mặc nhiên dùng để phê duyệt thêm factor, và response thêm factor không được tự chuyển thành bằng chứng cho một giao dịch quản trị khác.

## 6. Binding ứng dụng TOTP

TOTP sử dụng bí mật dùng chung giữa authenticator và verifier. RFC 6238 yêu cầu bí mật riêng cho mỗi prover, thiết lập tham số phù hợp và bảo vệ khóa khỏi truy cập trái phép. RFC mô tả thuật toán; nó không tự cung cấp toàn bộ quy trình cấp phát ứng dụng. [Nguồn: RFC 6238, Algorithm Requirements](https://www.rfc-editor.org/rfc/rfc6238.html#section-3).

Một luồng binding TOTP có thể diễn ra như sau:

1. Server xác minh quyền thiết lập hoặc thay đổi authenticator.
2. Server tạo seed mới bằng nguồn ngẫu nhiên mật mã và một giao dịch `PENDING`.
3. Người dùng nhận QR hoặc dữ liệu cấu hình qua kênh thiết lập được bảo vệ.
4. Ứng dụng authenticator nhập seed và bắt đầu tạo mã.
5. Người dùng nhập một mã để xác nhận cấu hình mới.
6. Server kiểm tra mã, ngữ cảnh giao dịch, thời hạn và ngân sách thử, rồi kích hoạt binding bằng cập nhật có kiểm soát.

QR chứa seed hoặc dữ liệu đủ để nhập seed phải được coi là bí mật. Không gửi nội dung QR đến một dịch vụ tạo ảnh bên thứ ba; không ghi provisioning URI vào log, trace, email hỗ trợ hoặc analytics. Sau khi binding đã kích hoạt, màn hình quản lý chỉ cần hiển thị metadata phù hợp, không cần cung cấp lại seed cho bất kỳ ai có phiên.

Seed TOTP khác mật khẩu người dùng về yêu cầu sử dụng: verifier thường cần truy xuất seed để tính mã kiểm tra. Vì vậy, không thể chỉ thay seed bằng hash một chiều rồi tiếp tục xác minh như cũ. Cần bảo vệ seed bằng cơ chế lưu bí mật thích hợp, quyền truy cập hạn chế và quản lý khóa. [Nguồn: RFC 6238, Security Considerations](https://www.rfc-editor.org/rfc/rfc6238.html#section-5).

Thời hạn của giao dịch thiết lập và bước thời gian của mã TOTP là hai khái niệm khác nhau. Một giao dịch chưa hết hạn không làm mọi mã cũ đều hợp lệ. Ngân sách thử cũng phải được quản lý ở server, kể cả khi có nhiều request song song.

Khi chấp nhận mã, hệ thống phải kiểm soát việc dùng lại trong cửa sổ còn hiệu lực. RFC 6238 yêu cầu không chấp nhận lần thứ hai của một OTP đã xác minh thành công. Trong thiết kế này, thông tin chống phát lại cần được giữ khi chuyển từ seed đang thiết lập sang factor đang hoạt động. [Nguồn: RFC 6238, Validation and Time-Step Size](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2).

Hai điện thoại cùng quét một QR có thể cùng tạo mã từ một seed. Hệ thống không được suy ra rằng đó là hai authenticator độc lập có thể thu hồi riêng chỉ từ việc giao diện liệt kê hai tên thiết bị. Nếu cần quản lý độc lập, cần các binding và bí mật phù hợp cho từng phương tiện.

## 7. Binding WebAuthn và passkey

Với WebAuthn, server đăng ký credential gồm định danh và khóa công khai; khóa riêng do authenticator quản lý. Registration phải được kiểm tra theo ceremony, gồm challenge, origin, RP ID, thuật toán và yêu cầu user presence hoặc user verification tương ứng. Không chỉ nhận một public key rồi gắn vào account ID do client gửi. [Nguồn: W3C WebAuthn, Registering a New Credential](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential).

Ứng dụng nên dùng thư viện server đã triển khai đầy đủ giao thức và cấu hình đúng kỳ vọng của Relying Party. Việc trình duyệt gọi thành công `navigator.credentials.create()` mới chỉ là một phần của luồng; server còn phải xác minh response và quyết định chấp nhận credential.

Attestation và user verification cũng có ý nghĩa khác nhau. Không có attestation đáng tin thì không được kết luận credential thuộc một mẫu phần cứng cụ thể. User presence không tự tương đương user verification; nếu chính sách yêu cầu UV, backend phải kiểm tra điều đó. Đồng thời không chuyển một credential ID đã thuộc tài khoản khác sang tài khoản mới. [Nguồn: W3C WebAuthn, Registration](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential).

Đối với chính sách sản phẩm, không mặc định mọi passkey đều là khóa gắn với một thiết bị duy nhất. Nếu yêu cầu credential không đồng bộ hoặc yêu cầu phần cứng cụ thể, phải xác định bằng chứng và khả năng xác minh được chấp nhận, thay vì dựa vào tên người dùng đặt như “khóa USB công ty”.

Thêm một passkey cũng không tự chứng minh một phiên đã đạt mức xác thực mà mọi thao tác đặc quyền yêu cầu. Hệ thống phải đánh giá bằng chứng thực sự đã thu thập và chính sách của thao tác đó.

## 8. Hợp đồng API và quyền thao tác

Ví dụ API cho tài khoản hiện tại:

```text
POST   /me/mfa/enrollments
POST   /me/mfa/enrollments/{enrollmentId}/confirm
DELETE /me/mfa/enrollments/{enrollmentId}
DELETE /me/mfa/factors/{factorId}
```

Đây là cách đặt endpoint minh họa, không phải giao thức bắt buộc. Hủy enrollment và thu hồi factor là hai thao tác khác nhau, nên cần phân biệt rõ trong nghiệp vụ.

| Thành phần | Quy tắc tại backend |
| --- | --- |
| Bắt đầu enrollment | Xác minh chủ thể, trạng thái tài khoản, loại authenticator được phép và điều kiện xác thực lại |
| Đọc dữ liệu thiết lập | Chỉ cho ngữ cảnh được phép của giao dịch còn hiệu lực |
| Xác nhận | Kiểm tra ownership, purpose, challenge hoặc seed, thời hạn, ngân sách thử và trạng thái hiện tại |
| Hủy | Chỉ hủy đúng giao dịch thuộc tài khoản được phép |
| Thu hồi | Kiểm tra quyền thay đổi credential và ảnh hưởng đến khả năng đăng nhập còn lại |

Nếu dùng cookie để xác thực, endpoint thay đổi trạng thái cần biện pháp chống CSRF phù hợp. Với mọi kiểu phiên, vẫn phải kiểm tra quyền ở backend; nút bị ẩn trên giao diện không ngăn request trực tiếp.

Response chỉ chứa dữ liệu cần thiết cho bước hiện tại. Không trả seed của factor đã kích hoạt trong API danh sách factor. Không nhận `verified=true`, `mfaEnabled=true` hoặc loại thiết bị tự khai như bằng chứng hoàn tất giao thức.

Rate limit cần bao phủ tạo giao dịch và thử xác nhận. Chỉ giới hạn theo một địa chỉ IP có thể không đủ cho tấn công phân tán; chỉ giới hạn theo một enrollment ID lại có thể bị né bằng cách tạo liên tục các giao dịch mới.

## 9. Hoàn tất một lần, kể cả khi request chạy song song

Giả sử người dùng bấm xác nhận hai lần, hoặc client tự retry sau timeout. Hai request có thể cùng nhìn thấy trạng thái `PENDING` trước khi một request kịp ghi kết quả.

Một quy trình minh họa có thể tổ chức như sau:

```text
confirmEnrollment(actorContext, enrollmentId, proofPayload):
    snapshot = loadEnrollmentForActor(actorContext, enrollmentId)
    checkOwnershipPurposeExpiryAndAttemptBudget(snapshot)
    checkFreshAuthorizationForBinding(actorContext, snapshot)

    proofResult = verifyUsingProtocolLibrary(snapshot, proofPayload)
    if proofResult is invalid:
        persistFailureAndEnforceBudget(snapshot)
        reject

    begin transaction:
        current = lockAndReloadEnrollment(enrollmentId)
        checkCurrentActorAccountAndSession(actorContext, current)
        checkStillPendingUnexpiredAndWithinBudget(current)
        checkAccountAndAuthorizationVersionsUnchanged(current)
        checkProofMatchesExactSetupVersion(proofResult, current)
        checkProofStillAcceptableAtCommit(proofResult)
        consumeChallengeOrAcceptedOtpAtomically(current, proofResult)
        createActiveBindingWithUniquenessChecks(current, proofResult)
        markEnrollmentConfirmed(current)
        incrementAuthMethodsVersion(current.accountId)
        appendAuditAndNotificationOutboxWithoutSecrets(current)
    commit

    return confirmationMetadata
```

Đây là mã giả về điều phối và giao dịch, không phải một triển khai giao thức mật mã. Nếu việc kiểm tra proof diễn ra trước transaction, kết quả phải gắn với đúng dữ liệu thiết lập và phiên bản đã kiểm tra. Không dùng một boolean `proofValid` không còn biết nó thuộc seed, challenge hoặc giao dịch nào.

Bộ đếm thất bại cần được lưu bền vững, cập nhật an toàn khi có cạnh tranh. Ném exception làm rollback cả lần tăng bộ đếm sẽ cho phép đối thủ thử vô hạn trong khi giao diện vẫn báo đã giới hạn.

Ràng buộc duy nhất và cập nhật có điều kiện phải ngăn tạo nhiều binding cho cùng một lần xác nhận. Sau retry, server có thể trả lại metadata kết quả đã hoàn tất nếu chính sách cho phép và chủ thể vẫn có quyền xem; điều đó không có nghĩa là chấp nhận lại proof để thực hiện một hành động mới.

Outbox giúp lưu yêu cầu thông báo cùng transaction rồi chuyển phát với retry. Nếu kênh thông báo tạm lỗi, hệ thống phải theo dõi và xử lý việc giao thông báo, thay vì bỏ mất sự kiện hoặc giả vờ thông báo đã tới người dùng.

## 10. Thay factor và recovery không được tạo đường vòng yếu hơn

Khi còn authenticator sử dụng được, luồng thay thiết bị nên xác thực lại bằng phương thức phù hợp, binding phương tiện mới và xử lý phương tiện cũ theo chính sách. Không thu hồi factor cũ ngay khi mới hiển thị QR của factor thay thế.

Nếu thiết bị cũ nghi bị đánh cắp, yêu cầu ngăn tiếp tục sử dụng có thể buộc phải thu hồi sớm. Khi đó cần phối hợp đường recovery và các phương thức còn lại; không giữ thiết bị bị xâm phạm hoạt động chỉ để luồng thay thế được thuận tiện.

Trước khi xóa phương thức cuối cùng đáp ứng chính sách của tài khoản, backend phải có quyết định rõ: từ chối thao tác, yêu cầu thiết lập phương thức khác hoặc chuyển sang một quy trình quản trị được cho phép. Phương thức đang `PENDING` không được tính là phương án thay thế đã dùng được.

Khi người dùng mất mọi phương thức, recovery phải xác minh bằng chứng theo thiết kế của dịch vụ. Không cho phép tự gắn factor mới chỉ vì người gửi biết email, ngày sinh hoặc thông tin công khai của tài khoản. Quyền hỗ trợ của nhân viên cũng không được đồng nghĩa với quyền tùy ý bỏ MFA.

Thông báo thay đổi cần gửi đến kênh đã được xác lập phù hợp, không chỉ đến địa chỉ hoặc số điện thoại vừa được thêm trong cùng thao tác. Thông báo nên cho người dùng biết thay đổi nào xảy ra và cách báo cáo nếu họ không thực hiện; không chứa seed, OTP hoặc token phê duyệt có thể dùng lại.

## 11. Phiên đăng nhập, phân quyền và SSO sau binding

Sự kiện thêm factor và sự kiện hoàn thành một lần xác thực MFA cần được phân biệt trong dữ liệu phiên. Không tự nâng mọi phiên cũ thành “đã MFA” chỉ vì tài khoản vừa có thêm một binding `ACTIVE`.

Sau thay đổi, hệ thống cần đánh giá phiên hoặc refresh token có phải thu hồi, yêu cầu xác thực lại hoặc cập nhật trạng thái hay không. Việc tăng `auth_methods_version` chỉ giúp nếu các thành phần sử dụng phiên thực sự kiểm tra và áp dụng phiên bản đó. Ghi một số vào database mà không có nơi thực thi không làm token cũ mất hiệu lực.

Trong hệ thống RBAC hoặc ABAC, quyền thêm factor cho chính mình khác quyền quản lý factor của người khác. Thao tác hỗ trợ cần kiểm tra tenant và tài khoản đích, ghi nhận người thực hiện và giới hạn tác động. Binding thành công cũng không tự cấp vai trò quản trị.

Đối với SSO/OIDC, cần xác định nơi sở hữu authenticator. Nếu IdP thực hiện MFA, ứng dụng không nên suy ra cấu hình binding tại IdP từ một checkbox cục bộ. Ứng dụng cần áp dụng hợp đồng tin cậy với IdP và kiểm tra bằng chứng xác thực phù hợp khi yêu cầu truy cập nhạy cảm.

Danh tính workload có cách cấp phát và liên kết credential riêng; quy trình nhập OTP bằng người dùng không thể được áp dụng nguyên xi cho workload. Phạm vi của bài là phương tiện xác thực của tài khoản con người trong hệ thống IAM.

## 12. Dữ liệu vận hành và bằng chứng kiểm toán

Bản ghi binding cần đủ để hỗ trợ quản lý vòng đời: chủ sở hữu, loại, trạng thái, thời điểm tạo hoặc thu hồi và đặc tính mà chính sách cần sử dụng. Tên hiển thị giúp người dùng nhận diện thiết bị nhưng không phải bằng chứng về khả năng bảo vệ khóa.

Audit event có thể chứa mã tài khoản, mã binding nội bộ, loại thao tác, kết quả, chủ thể thực hiện và mã tương quan. Không ghi seed, provisioning URI, QR, OTP, recovery code hoặc request body nguyên vẹn. Metadata thiết bị và mạng cũng cần được thu thập theo mục đích và quyền truy cập phù hợp.

Giao dịch `PENDING` hết hạn cần có cơ chế dọn dữ liệu thiết lập. Chỉ xóa liên kết ở giao diện trong khi seed vẫn nằm vô thời hạn ở cache, object storage hoặc telemetry là chưa hoàn tất vòng đời dữ liệu.

Các chỉ số vận hành có ích gồm tỷ lệ bắt đầu nhưng không hoàn tất, số lần xác nhận thất bại, số enrollment tạo liên tục, độ trễ thông báo và sự kiện thay factor ở tài khoản đặc quyền. Cần phân biệt lỗi người dùng, lỗi giao thức và hành vi lạm dụng mà không ghi lại bí mật để debug.

## 13. Tình huống kiểm chứng thiết kế

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tạo QR rồi đóng trang | Không có factor mới được dùng để đăng nhập |
| Tài khoản B xác nhận enrollment của A | Bị từ chối dù biết enrollment ID |
| Account ID giống nhau ở hai tenant | Không thể dùng dữ liệu của tenant này cho tenant kia |
| Response đúng giao thức nhưng sai challenge hoặc mục đích | Không kích hoạt binding |
| Phiên có cookie nhưng thiếu xác thực lại theo chính sách | Không được phép thêm factor |
| Hai request xác nhận hợp lệ đến đồng thời | Chỉ một lần chuyển trạng thái và một binding tương ứng |
| Mã TOTP đã chấp nhận được gửi lại | Không được dùng cho một lần chấp nhận mới |
| Tài khoản bị vô hiệu hóa trước lúc commit | Không kích hoạt dựa trên snapshot cũ |
| Danh sách factor đã thay đổi sau khi bắt đầu | Phát hiện thay đổi phiên bản và đánh giá lại |
| Chỉ còn một factor hợp lệ, factor thay thế chưa hoàn tất | Không coi factor đang chờ là phương án truy cập đã sẵn sàng |
| WebAuthn response thiếu UV khi chính sách yêu cầu UV | Bị từ chối |
| Notification service tạm lỗi | Yêu cầu thông báo vẫn được theo dõi để giao lại |

Các tình huống trên cần được đánh giá ở backend, kể cả khi giao diện đã hạn chế thao tác. Kiểm tra luồng đúng chỉ chứng minh một enrollment có thể hoàn tất; các trường hợp sai ngữ cảnh mới cho thấy binding có thực sự thuộc đúng tài khoản và mục đích hay không.

## 14. Bài tập vận dụng

Một cổng quản trị cho phép thêm ứng dụng TOTP khi có cookie phiên. Server bật `mfaEnabled=true` ngay sau khi tạo QR; API xác nhận nhận `accountId` trong body và không kiểm tra chủ sở hữu enrollment. Email thông báo được gửi đến địa chỉ vừa cập nhật trong cùng phiên.

Hãy đề xuất thiết kế thay thế và giải thích:

1. Bằng chứng nào cho phép bắt đầu binding, và bằng chứng nào xác nhận phương tiện mới?
2. Những trường nào phải được ràng buộc ở server để ngăn đổi tài khoản, tenant hoặc mục đích?
3. Khi hai request xác nhận cạnh tranh, cập nhật nào bảo đảm chỉ có một kết quả hợp lệ?
4. Người mất thiết bị và người còn factor cũ phải đi qua hai luồng khác nhau như thế nào?
5. Sau thay đổi, phiên cũ, quyền quản trị và kênh thông báo cần được xử lý ra sao?

Một phương án tốt phải chỉ rõ ai được phép tạo liên kết, server kiểm tra giao thức nào và thời điểm authenticator bắt đầu được sử dụng. Ba quyết định đó tạo nền tảng để quản lý MFA xuyên suốt cấp phát tài khoản, thay thiết bị, recovery và thu hồi quyền truy cập.
