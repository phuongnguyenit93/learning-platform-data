# Authenticator binding

## 1. Authenticator binding là gì?

Authenticator binding là việc thiết lập mối liên hệ giữa một authenticator cụ thể và một tài khoản, để authenticator đó có thể được dùng xác thực cho tài khoản ấy. Tạo khóa, cài ứng dụng OTP hoặc cắm một security key vào máy chưa tự tạo ra mối liên hệ này ở dịch vụ.

NIST phân biệt authenticator do nhà cung cấp cấp phát và authenticator do người dùng mang tới; cả hai đều cần được gắn với tài khoản qua quy trình phù hợp. [NIST SP 800-63B-4 — Authenticator Binding](https://pages.nist.gov/800-63-4/sp800-63b/events/#binding)

Ví dụ, An đã đăng nhập vào ứng dụng công việc và muốn thêm security key. Máy chủ phải xác định tài khoản của An, cho phép thao tác thêm, xử lý đăng ký credential và lưu quan hệ với đúng tài khoản. Nếu máy chủ gắn nhầm public key của người khác, những lần xác thực sau có thể đúng về mật mã nhưng sai về chủ tài khoản.

Bài học tập trung vào ba câu hỏi:

- Ai có quyền tạo quan hệ binding này?
- Bằng chứng đăng ký có hợp lệ và thuộc đúng giao dịch không?
- Quan hệ đã tạo sẽ được quản lý, thay thế và thu hồi như thế nào?

Đó là phần nối giữa quản lý danh tính và khả năng sử dụng authenticator trong thực tế.

## 2. Phân biệt binding với các khái niệm gần nhau

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Identity proofing | Danh tính được đăng ký đã được xác minh theo mức nào? | Kiểm tra bằng chứng danh tính trong enrollment |
| Authenticator binding | Authenticator nào được chấp nhận cho tài khoản nào? | Lưu credential của security key dưới account nội bộ |
| Authentication | Lần này người gọi có đưa ra bằng chứng hợp lệ không? | Xác minh chữ ký với credential đã được gắn |
| Authorization | Người đã xác thực được làm gì? | Có được duyệt chứng từ thuộc tenant này không? |
| Device enrollment | Thiết bị đã tham gia hệ thống quản lý nào? | Đưa máy tính vào quản lý thiết bị của tổ chức |
| Token/key binding | Token được ràng buộc với khóa hoặc bên sử dụng nào? | Yêu cầu chứng minh kiểm soát khóa khi sử dụng token |

Các quan hệ này có thể phối hợp nhưng không thay thế nhau. Một laptop đã được quản lý không tự cho phép mọi credential trên máy trở thành authenticator của người dùng. Một credential được gắn thành công cũng không tự cấp role quản trị hoặc tenant membership.

Trong hệ thống nhiều tenant, cần xác định binding thuộc tài khoản toàn cục hay danh tính riêng của một miền. Nếu cùng một tài khoản đăng nhập nhiều tenant, thêm credential cho tài khoản đó có thể ảnh hưởng mọi tenant sử dụng nó. Không đặt mặc định rằng credential chỉ có hiệu lực trong tenant đang hiển thị ở giao diện.

## 3. Hai phần bằng chứng phải tách riêng

### 3.1. Thẩm quyền đối với tài khoản hiện có

Dịch vụ cần biết người đang thao tác có quyền thêm authenticator cho tài khoản đích. Với người dùng đã có authenticator, đây thường là một lần xác thực lại hoặc step-up được thiết kế cho hành động nhạy cảm.

Một cookie phiên còn hạn chưa đủ để kết luận việc thêm credential mới là an toàn. Kẻ đã lấy được phiên có thể dùng trang cài đặt bảo mật để gắn authenticator của chính chúng, biến quyền truy cập tạm thời thành khả năng đăng nhập lâu dài.

NIST quy định mức xác thực khi thêm authenticator dựa trên mức cao nhất tài khoản hiện có và mức cao nhất authenticator mới sẽ được dùng, lấy mức thấp hơn trong hai mức đó. Đây là quy tắc theo AAL, không phải phép đếm số màn hình đăng nhập. [NIST — Post-Enrollment Binding](https://pages.nist.gov/800-63-4/sp800-63b/events/#post-enroll)

Ứng dụng cần ánh xạ yêu cầu của mình sang bằng chứng cụ thể: phương thức đã dùng, thời điểm xác thực, tài khoản, phiên và hành động đang được phê duyệt. Một access token vừa được refresh không tự chứng minh người dùng vừa hoàn tất xác thực tăng cường.

### 3.2. Tính hợp lệ của đăng ký authenticator mới

Dịch vụ cũng cần kiểm tra dữ liệu đăng ký theo đúng loại authenticator. Người dùng được phép thêm authenticator không có nghĩa máy chủ có thể chấp nhận một public key hoặc một số điện thoại bất kỳ trong request body.

Ví dụ:

| Loại | Dữ liệu/liên hệ cần thiết lập | Bằng chứng hoặc kiểm tra liên quan |
|---|---|---|
| TOTP | Secret chung và tham số cho một đăng ký | Xác minh mã từ đăng ký đang chờ, giới hạn thử sai |
| WebAuthn | Credential ID, public key và tài khoản RP | Xác minh registration ceremony và chính sách RP |
| Out-of-band | Đầu cuối/kênh đã được xác nhận | Kiểm tra khả năng kiểm soát kênh theo cơ chế chấp nhận |
| Chứng thư/khóa | Khóa được chấp nhận cho tài khoản | Kiểm tra khóa, chứng thư và bằng chứng theo giao thức |

Quét được QR hoặc trả về một mã hợp lệ chỉ trả lời một phần câu hỏi. Người có secret TOTP của một giao dịch có thể tạo mã, nhưng điều đó không chứng minh họ là chủ tài khoản đang bị gắn nhầm.

## 4. Binding lúc enrollment và binding về sau

### 4.1. Authenticator đầu tiên

Khi tài khoản chưa có authenticator, không thể yêu cầu xác thực bằng một yếu tố chưa tồn tại. Binding đầu tiên phải gắn với một quy trình enrollment có thẩm quyền: tạo tài khoản, xác minh các bằng chứng cần thiết và chuyển quyền kiểm soát ban đầu.

Một lời mời có thể khởi tạo quy trình, nhưng cần xác định ai được phát hành, đối tượng nhận, phạm vi, thời hạn và cách tiêu thụ. Không thiết kế một endpoint công khai chỉ nhận `email + publicKey` rồi gắn khóa cho bất kỳ tài khoản nào tìm thấy qua email.

Đối với nhân viên, quy trình có thể dựa trên hồ sơ được bộ phận có thẩm quyền phê duyệt. Đối với sản phẩm tự đăng ký, quy trình có thể khác. Không suy luận mức identity proofing cao chỉ vì người dùng đã xác nhận một email.

### 4.2. Thêm authenticator dự phòng

Người dùng đã xác thực có thể thêm phương thức khác để giảm phụ thuộc vào một thiết bị duy nhất. Tuy nhiên, hai nhãn trong giao diện chưa chắc là hai phương tiện độc lập.

Hai ứng dụng TOTP dùng chung một seed tạo ra cùng loại bằng chứng từ cùng bí mật. Một passkey được đồng bộ trên nhiều thiết bị cũng cần được hiểu theo mô hình credential và nền tảng đồng bộ của nó. Không đếm số điện thoại hoặc số thiết bị hiển thị để tự kết luận khả năng phục hồi độc lập.

### 4.3. Thay thế sau mất thiết bị

Nếu vẫn còn phương thức hợp lệ, người dùng có thể xác thực theo chính sách rồi thêm authenticator mới. Nếu không còn đủ phương thức, họ cần đi qua account recovery được phê duyệt.

Recovery không được rút gọn thành “biết username và nói rằng đã mất điện thoại”. Quy trình hỗ trợ thủ công cũng cần ràng buộc người xử lý, bằng chứng, phê duyệt và audit. Quyền quản trị hệ thống không mặc nhiên cho phép gắn khóa tùy ý vào mọi tài khoản mà không có hồ sơ tương ứng.

## 5. Thiết kế một giao dịch binding

### 5.1. Khởi tạo bằng ngữ cảnh máy chủ đã xác minh

Với luồng tự phục vụ, tài khoản đích phải lấy từ ngữ cảnh xác thực đã được máy chủ kiểm chứng. Nếu client gửi `accountId`, máy chủ vẫn phải đối chiếu; không dùng nó làm nguồn thẩm quyền.

Một request bắt đầu có thể chỉ nêu loại authenticator và tên gợi nhớ:

```http
POST /security/authenticator-bindings HTTP/1.1
Content-Type: application/json

{
  "type": "WEBAUTHN",
  "displayName": "Security key dự phòng"
}
```

Endpoint và payload là thiết kế minh họa. Request còn phải đáp ứng cơ chế bảo vệ phiên, chống giả mạo request và yêu cầu xác thực lại của ứng dụng. Tên gợi nhớ do client cung cấp là nhãn người dùng, không phải chứng cứ về model phần cứng hoặc owner.

Đối với luồng quản trị hỗ trợ, phải có action và quyền riêng, lý do, tài khoản đích được định vị chính xác và quy trình phê duyệt phù hợp. Không tái sử dụng endpoint tự phục vụ với một cờ `admin=true` do client gửi.

### 5.2. Tạo ngữ cảnh chờ có thời hạn

Máy chủ lưu một đối tượng giao dịch, chẳng hạn:

```yaml
bindingId: bind-9b17
identityRealm: workforce-example
accountId: account-0042
authenticatorType: WEBAUTHN
purpose: ADD_AUTHENTICATOR
status: PENDING
initiatingSessionRef: session-ref-31
authorizationEvidenceRef: stepup-ref-88
accountSecurityVersion: 12
challengeRef: protected-challenge-ref
createdAt: '2026-12-01T09:00:00+07:00'
expiresAt: '2026-12-01T09:05:00+07:00'
```

Đây là schema nội bộ mẫu. Thời hạn 5 phút là lựa chọn của ví dụ, không phải yêu cầu chung của mọi giao thức. `authorizationEvidenceRef` tham chiếu kết quả đã xác minh, không phải nội dung token do client tự khai.

Challenge hoặc mã binding cần được sinh phù hợp, gắn với tài khoản, mục đích và giao dịch. ID khó đoán hỗ trợ chống đoán, nhưng không thay thế kiểm tra quyền. Nếu người dùng đăng xuất rồi đăng nhập tài khoản khác, giao dịch cũ không được chuyển theo người dùng mới.

Trạng thái máy chủ có thể có các nhánh:

```text
PENDING -> COMMITTED
        -> EXPIRED
        -> CANCELLED
        -> REJECTED
```

`COMMITTED` chỉ xuất hiện sau kiểm chứng và ghi nhận quan hệ thành công. Dữ liệu candidate đang chờ không được dùng để đăng nhập như một authenticator `ACTIVE`.

### 5.3. Xác minh và commit

Khi nhận phản hồi, máy chủ cần kiểm tra lại ngữ cảnh chứ không chỉ kiểm tra mật mã:

```text
- Đúng bindingId và đúng mục đích.
- Giao dịch đang chờ, chưa hết hạn và chưa bị tiêu thụ.
- Người thực hiện còn có thẩm quyền với đúng tài khoản.
- Bằng chứng xác thực lại vẫn đáp ứng yêu cầu.
- Tài khoản chưa bị khóa hoặc thay đổi trạng thái bảo mật liên quan.
- Dữ liệu đăng ký hợp lệ theo loại authenticator và chính sách.
- Không có xung đột credential hoặc quan hệ tài khoản.
```

Việc tiêu thụ giao dịch và kích hoạt credential phải chống race condition. Hai request hoàn tất đồng thời không được tạo hai binding khác nhau hoặc khiến một giao dịch được dùng lại.

Nếu có yêu cầu idempotent, request lặp sau một commit có thể nhận lại kết quả đã ghi khi toàn bộ ngữ cảnh khớp; nó không được thực thi lại quá trình gắn một credential khác.

## 6. Ví dụ với TOTP

TOTP dựa trên secret dùng chung và tham số thời gian thống nhất giữa bên tạo mã và verifier. RFC 6238 yêu cầu secret riêng cho từng prover và bảo vệ khóa khỏi truy cập, sử dụng trái phép. [RFC 6238 — Algorithm Requirements](https://www.rfc-editor.org/rfc/rfc6238.html#section-3)

Một luồng thiết lập mẫu:

1. Người dùng hoàn tất yêu cầu xác thực lại để thêm TOTP.
2. Máy chủ tạo một đăng ký đang chờ với seed riêng và thời hạn.
3. Máy chủ hiển thị dữ liệu provisioning cho đúng giao dịch qua kênh được bảo vệ.
4. Người dùng thêm secret vào ứng dụng authenticator và nhập một mã được tạo ra.
5. Máy chủ xác minh mã với seed của đúng đăng ký đang chờ và giới hạn số lần thử.
6. Chỉ khi đạt yêu cầu mới commit binding và cho phép sử dụng trong đăng nhập.

Chỉ tải trang hoặc nhìn thấy QR không đủ để đánh dấu `mfaEnabled=true`. Người dùng có thể chưa cấu hình ứng dụng, quét nhầm QR hoặc bỏ dở quy trình.

QR chứa dữ liệu seed phải được xem là bí mật. Không đưa nó vào analytics, log, ảnh chụp hỗ trợ hoặc cache công khai. Khi giao dịch hết hạn/hủy, xử lý dữ liệu pending theo chính sách để nó không trở thành credential còn dùng được ngoài ý muốn.

Verifier TOTP cần seed hoặc khả năng tính toán tương đương để kiểm tra mã. Vì vậy, không áp dụng nguyên mô hình lưu password hash cho seed rồi mong vẫn xác minh TOTP như cũ. Cần bảo vệ secret bằng cơ chế mã hóa/quản lý khóa và phân quyền phù hợp với kiến trúc.

Một mã TOTP hợp lệ cho pending registration chỉ chứng minh người gửi có khả năng tạo mã với secret tương ứng trong điều kiện kiểm tra đó. Nếu một phiên bị chiếm đã khởi tạo đăng ký cho tài khoản nạn nhân, bước nhập mã mới không tự sửa được việc thiếu thẩm quyền ban đầu.

Sau khi kích hoạt, việc chặn tái sử dụng mã và kiểm soát cửa sổ thời gian thuộc luồng xác thực TOTP. Không để một cơ chế kiểm tra lỏng ở bước binding trở thành cách thử mã không giới hạn hoặc bỏ qua trạng thái credential về sau.

## 7. Ví dụ với WebAuthn

### 7.1. Gắn credential của RP với account nội bộ

Trong đăng ký WebAuthn, RP cung cấp challenge và thông tin tài khoản; client và authenticator thực hiện ceremony, rồi máy chủ kiểm chứng phản hồi trước khi lưu credential.

Các kiểm tra quan trọng gồm loại ceremony, challenge, origin, RP ID hash, yêu cầu user verification, thuật toán và attestation theo chính sách. Danh sách này là điểm định hướng, không thay thế toàn bộ thuật toán xác minh chuẩn hoặc thư viện đã triển khai nó. [W3C WebAuthn — Registering a New Credential](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential)

Máy chủ cần giữ tài khoản đích trong ngữ cảnh đã khởi tạo. Không chọn account chỉ dựa trên tên hoặc email mà client gửi ở bước hoàn tất. User handle do RP quản lý phải có quan hệ ổn định với account; nhãn hiển thị không phải khóa định danh đáng tin cậy.

Sau khi thành công, bản ghi có thể chứa:

```text
authenticatorRecordId
identityRealm + accountId
RP ID + credential ID
credential public key
trạng thái ACTIVE
các thuộc tính đã xác minh cần cho policy và authentication
createdAt + bindingEventRef
nhãn người dùng và metadata vận hành phù hợp
```

Không lưu private key của authenticator tại RP. Cũng không cần gửi mẫu vân tay hoặc khuôn mặt lên RP chỉ vì authenticator dùng sinh trắc học để mở khóa cục bộ.

### 7.2. User presence, user verification và attestation

User presence và user verification có ý nghĩa khác nhau; một lần chạm không tự chứng minh danh tính thật của người chạm. Attestation hỗ trợ đánh giá đặc tính authenticator theo chính sách, không thay thế thẩm quyền gắn vào tài khoản. Không phải mọi đăng ký đều cung cấp cùng mức attestation. [W3C WebAuthn — Registration Verification](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential)

Do đó, đừng lấy kết quả “registration hợp lệ” để tự gán một AAL cao hoặc role đặc biệt. Ứng dụng phải đánh giá những thuộc tính thực sự được xác minh và toàn bộ luồng liên quan.

Với tài khoản giá trị cao, sản phẩm có thể chọn thêm một lần xác thực bằng credential mới để xác nhận khả năng sử dụng sau đăng ký. Đây là một bước bổ sung của thiết kế sản phẩm; không mô tả nó như một yêu cầu giống nhau cho mọi WebAuthn deployment.

### 7.3. Một thiết bị không đồng nghĩa một credential

Một authenticator có thể phục vụ nhiều tài khoản hoặc nhiều RP; một tài khoản cũng có thể có nhiều credential. Credential được đồng bộ có thể xuất hiện qua nhiều thiết bị. Vì vậy, không dùng serial thiết bị, tên laptop hoặc số thiết bị hiển thị làm khóa duy nhất để quản lý binding.

Khi xóa một credential record ở RP, phải chặn credential đó theo trạng thái dịch vụ. Chỉ xóa passkey trên một thiết bị không chứng minh bản ghi RP và các bản sao liên quan đã bị vô hiệu hóa.

## 8. Các tình huống tấn công vào binding

### 8.1. Gắn authenticator của kẻ chiếm phiên

Kẻ tấn công lấy cookie của Bình, mở cài đặt bảo mật và thêm khóa của chúng. Những lần đăng nhập sau có thể không cần cookie bị lấy trước đó nữa.

Cần xác thực lại bằng phương thức hiện có phù hợp, đánh giá rủi ro và thông báo thay đổi qua kênh độc lập. OWASP nhấn mạnh rằng thay yếu tố MFA là hành động rủi ro cao và không nên chỉ dựa vào phiên đang mở. [OWASP Multifactor Authentication — Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

Thông báo giúp phát hiện sự cố, nhưng không thay thế kiểm soát trước commit. Một email đến sau khi kẻ tấn công đã gắn khóa vẫn cần cơ chế xử lý nhanh để chủ tài khoản phản đối sự kiện.

### 8.2. Trộn giao dịch giữa hai tài khoản

Người dùng mở binding của tài khoản A, chuyển tab sang tài khoản B rồi gửi phản hồi cũ. Hoặc một request bị sửa `accountId` để đưa dữ liệu đăng ký sang người khác.

Máy chủ phải đối chiếu giao dịch với account và phiên/ngữ cảnh đã được phê duyệt. Không lấy account hiện đang hiển thị trên frontend làm bằng chứng rằng phản hồi thuộc account đó.

Trong nhiều miền danh tính, cùng một chuỗi email ở hai realm không có nghĩa cùng tài khoản. Cần định vị bằng ID nội bộ và miền đã xác minh.

### 8.3. Replay, CSRF và mã binding qua thiết bị khác

Challenge hay mã đã dùng không được tạo binding mới. Cần thời hạn, mục đích và việc tiêu thụ được kiểm soát ở phía máy chủ, cùng bảo vệ chống request giả mạo theo mô hình ứng dụng.

Một mã QR dùng nối thiết bị có thể bị tráo để người dùng chấp thuận giao dịch của người khác. Giao diện nên hiển thị rõ tài khoản, mục đích, thiết bị/đầu cuối liên quan và hướng dẫn hủy khi có nghi ngờ. Không dùng chung một loại mã mơ hồ cho login, thêm authenticator và recovery.

Người biết mã binding không vì thế có quyền chọn lại account đích hoặc loại thao tác. Mã cần trỏ tới ngữ cảnh mà máy chủ đã cố định, thay vì mang ý nghĩa “ai gửi mã trước thì được gắn vào account tùy chọn”.

### 8.4. Thay đồng thời authenticator và kênh thông báo

Nếu kẻ chiếm phiên có thể đổi email khôi phục rồi gắn khóa, mọi cảnh báo có thể chỉ đến địa chỉ mới của chúng. Thay notification/recovery address cũng cần bảo vệ riêng và đánh giá ảnh hưởng tới luồng binding.

Một thiết kế mẫu gửi thông báo sự kiện tới kênh đã được xác nhận trước thay đổi và hướng dẫn cách phản đối. Không coi một địa chỉ vừa được client nhập là kênh độc lập đã đáng tin cậy.

## 9. Commit, lưu vết và thông báo

Mô hình dữ liệu cần tách ít nhất ba đối tượng:

| Đối tượng | Mục đích | Trạng thái tiêu biểu |
|---|---|---|
| Binding request | Theo dõi giao dịch thêm/thay thế | Pending, committed, expired, cancelled |
| Authenticator record | Theo dõi quan hệ được dùng xác thực | Active, suspended, revoked |
| Security event | Lưu dấu vết và công việc thông báo | Đã ghi, chờ gửi, đã gửi, cần retry |

Pseudocode cho phần commit:

```java
BindingResult completeBinding(Context context, BindingId id, Proof proof) {
    PendingBinding pending = loadPendingBinding(id);
    requireAuthorizedContext(context, pending);

    VerifiedCandidate candidate = verifierFor(pending.type())
        .verifyRegistration(pending, proof);

    return transaction(() -> {
        PendingBinding current = lockAndReload(id);
        requireStillPendingAndNotExpired(current);
        requireSameContextAndCandidate(current, pending, candidate);
        requireAccountStillEligibleAndVersionMatches(current);
        requireAuthorizationEvidenceStillValid(context, current);
        requireNoCredentialOwnershipConflict(current, candidate);

        AuthenticatorRecord record = insertActiveRecord(current, candidate);
        markBindingCommitted(current, record.id());
        appendSecurityEventAndNotificationOutbox(current, record);
        return BindingResult.completed(record.id());
    });
}
```

Các kiểu và hàm là ký hiệu thiết kế, không phải một thư viện Java hoàn chỉnh. Adapter xác minh phải thực hiện đúng quy trình cho từng loại; `Proof` không có nghĩa mọi loại authenticator đều có cùng định dạng hoặc cùng bằng chứng mật mã.

Việc kiểm tra trạng thái và phiên bản tài khoản tại commit ngăn tình huống tài khoản bị offboard trong lúc người dùng đang thao tác với authenticator. Sau commit, luồng authentication vẫn phải kiểm tra trạng thái tài khoản và credential; không chỉ dựa vào sự tồn tại của public key hay seed.

Thông báo độc lập khi thêm authenticator là một phần quản lý sự kiện binding theo NIST. [NIST SP 800-63B-4 — Post-Enrollment Binding](https://pages.nist.gov/800-63-4/sp800-63b/events/#post-enroll)

Nếu dịch vụ gửi thông báo tạm lỗi, không lặp lại việc tạo credential chỉ để gửi lại email. Lưu công việc thông báo bền vững, retry và đưa vào xử lý vận hành nếu không hoàn tất. Chính sách phải quy định rõ trạng thái nào được xem là hoàn tất toàn bộ workflow và cách xử lý việc không thông báo được.

Audit event có thể lưu actor, account, loại authenticator, binding ID, thời điểm, nguồn phù hợp, bằng chứng xác thực tham chiếu và kết quả. Không ghi seed TOTP, QR provisioning, private key, OTP nguyên văn hoặc token phiên vào log.

## 10. Thay thế, thu hồi và recovery

Với thay thế theo kế hoạch, giữ authenticator cũ hoạt động trong thời gian thiết lập phương thức mới theo chính sách. Xác nhận phương thức mới dùng được rồi thu hồi phương thức cũ. Không xóa phương thức cuối cùng trước khi người dùng hoàn tất một đường truy cập thay thế hợp lệ.

Nếu authenticator cũ bị mất hoặc nghi bị chiếm, ưu tiên vô hiệu hóa nó qua luồng được phê duyệt; không giữ nó hoạt động chỉ để làm quy trình thay thế thuận tiện. Khi thiếu phương thức xác thực còn lại, chuyển sang recovery với thẩm quyền và bằng chứng riêng.

Thu hồi cần tác động tới khả năng dùng credential ở verifier. Xóa một tên thiết bị trên giao diện mà backend vẫn chấp nhận credential ID cũ không đạt mục tiêu. Tương tự, thu hồi một authenticator không tự chứng minh mọi phiên đã được tạo bởi nó đều kết thúc; cần chính sách phiên riêng.

Với TOTP bị lộ seed, đổi nhãn hoặc cài lại ứng dụng mà giữ cùng seed không tạo ra bí mật mới. Với passkey, phân biệt việc xóa ở RP, xóa khỏi thiết bị và xử lý nền tảng đồng bộ. Quy trình phải phản ánh những đối tượng mà từng thao tác thực sự kiểm soát.

Recovery cũng là cơ hội hình thành binding mới, nên phải tránh đường vòng hạ thấp toàn bộ bảo vệ. Sau khi phục hồi cần đánh giá authenticator cũ, credential dự phòng, phiên đang có và các thay đổi recovery liên quan.

## 11. Các phép kiểm tra cần thiết khi triển khai

| Tình huống | Kết quả mong đợi |
|---|---|
| Có phiên nhưng không đáp ứng yêu cầu xác thực lại | Không tạo binding active |
| Bắt đầu với account A, hoàn tất khi ngữ cảnh là account B | Bị từ chối; không gắn nhầm tài khoản |
| Client sửa account hoặc realm trong request | Không vượt được đối tượng đã cố định ở máy chủ |
| Giao dịch hết hạn hoặc bị hủy | Không kích hoạt candidate |
| Gửi hai phản hồi hoàn tất đồng thời | Một kết quả nhất quán, không tạo hai credential ngoài ý muốn |
| Tái gửi challenge hoặc proof đã tiêu thụ | Không tạo binding mới |
| TOTP hiển thị QR nhưng chưa có xác minh mã | Chưa cho sử dụng như yếu tố đã đăng ký |
| TOTP nhập sai liên tiếp | Có giới hạn thử; không trở thành endpoint đoán không hạn chế |
| WebAuthn sai challenge, origin hoặc RP ID | Registration bị từ chối |
| WebAuthn không đáp ứng policy user verification/thuộc tính | Không gán khả năng đảm bảo không được chứng minh |
| Credential xung đột với quan hệ tài khoản hiện có | Không chuyển owner âm thầm |
| Tài khoản bị vô hiệu hóa trong lúc binding đang chờ | Commit không tạo khả năng đăng nhập hoạt động |
| Gửi thông báo lỗi tạm thời | Có retry thông báo; không lặp tạo credential |
| Thu hồi credential rồi thử đăng nhập bằng nó | Verifier từ chối theo chính sách |
| Kiểm tra log, tracing và dữ liệu hỗ trợ | Không lộ secret provisioning hoặc token |

Các phép kiểm tra trên là yêu cầu thiết kế kiểm thử cho hệ thống sẽ triển khai. Chúng giúp đánh giá cả quan hệ account, quản lý trạng thái và kiểm chứng giao thức; không chỉ việc trình duyệt đã hiện hộp thoại thành công.

## 12. Bài tập vận dụng

Hãy thiết kế luồng thêm authenticator dự phòng cho một ứng dụng công việc. Người dùng hiện có password và TOTP, muốn thêm security key. Xác định bằng chứng cần có trước khi bắt đầu, account/realm đích, trạng thái pending, điều kiện commit và kênh thông báo.

Sau đó bổ sung hai biến thể: tài khoản bị offboard khi đăng ký chưa hoàn tất; người dùng mất điện thoại và chỉ còn một phiên trình duyệt cũ. Giải thích trường hợp nào có thể tiếp tục binding tự phục vụ và trường hợp nào cần recovery, cùng cách tránh biến phiên bị lấy cắp thành quyền sở hữu credential mới.

Sản phẩm cần có sơ đồ giao dịch, cấu trúc bản ghi, một ca thành công và các ca từ chối cho nhầm tài khoản, replay, hết hạn, thiếu thẩm quyền và xung đột trạng thái. Thiết kế phải cho thấy cả việc đăng ký hợp lệ lẫn lý do credential đó được phép đại diện cho đúng tài khoản.
