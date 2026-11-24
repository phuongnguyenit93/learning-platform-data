# Reauthentication failure — Xử lý thất bại khi xác thực lại

## 1. Mục tiêu và phạm vi

Trong chương **Reauthentication** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, xác thực lại được dùng để kiểm tra người đang tiếp tục một phiên hoặc muốn thực hiện hành động nhạy cảm có đáp ứng điều kiện xác thực hiện tại hay không.

Thất bại có thể xảy ra khi người dùng nhập sai mật khẩu, trình mã hết hiệu lực, hủy thao tác passkey, mất thiết bị MFA, gặp lỗi nhà cung cấp danh tính hoặc sử dụng một context đã bị thay đổi.

Cách xử lý cần đồng thời giữ hai yêu cầu:

- Hành động đang cần xác thực lại chỉ được tiếp tục sau khi server xác minh đủ điều kiện.
- Người dùng hợp lệ nhận được đường thử lại, khôi phục hoặc kết thúc phiên phù hợp với nguyên nhân và chính sách.

Bài học tập trung vào **reauthentication failure**: phân loại kết quả, bảo vệ hành động nhạy cảm, quyết định hiệu lực session, hạn chế lạm dụng và chuyển sang recovery khi cần.

Các trạng thái, endpoint và mã giả trong bài là thiết kế minh họa. Thời hạn, số lần thử và tổ hợp phương tiện cần được xác định theo sản phẩm. Không dùng các ví dụ này để tự khẳng định một mức AAL.

## 2. Thế nào là một lần xác thực lại chưa thành công?

### 2.1. Điều kiện thành công có nhiều thành phần

Một kết quả có thể chỉ được chấp nhận khi:

1. Bằng chứng được verifier phù hợp xác minh.
2. Bằng chứng thuộc đúng principal đang cần xác thực lại.
3. Challenge, request hoặc context còn hiệu lực.
4. Phương thức đáp ứng chính sách cho tình huống hiện tại.
5. Session, credential và trạng thái bảo mật vẫn được chấp nhận.
6. Kết quả được gắn với đúng mục đích hoặc phạm vi quyền cần cấp.

Một mật khẩu đúng chưa đủ nếu chính sách còn yêu cầu MFA. Một assertion có chữ ký đúng chưa đủ nếu credential đã bị thu hồi hoặc kết quả thuộc một operation khác.

OWASP khuyến nghị yêu cầu xác thực lại cho tính năng nhạy cảm và sau các sự kiện rủi ro như recovery hoặc thay đổi thông tin bảo mật. [OWASP, Re-authentication After Risk Events](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#reauthentication-after-risk-events)

### 2.2. Ba kết quả cần tách biệt

| Kết quả | Ý nghĩa | Hành vi cần có |
| --- | --- | --- |
| Đã xác minh bằng chứng | Verifier chấp nhận một thành phần hoặc toàn bộ bằng chứng | Tiếp tục kiểm tra context và chính sách |
| Đã đáp ứng yêu cầu reauthentication | Đủ điều kiện cho phạm vi được xác định | Có thể cấp kết quả hoặc grant giới hạn |
| Đã thực hiện hành động nghiệp vụ | Thay đổi nhạy cảm đã được commit | Trả trạng thái thực tế, hỗ trợ retry an toàn |

Một lần xác thực lại thành công không tự chứng minh hành động phía sau đã commit. Ngược lại, response bị mất sau commit không có nghĩa hành động chắc chắn chưa xảy ra.

Thiết kế cần lưu trạng thái đủ rõ để tránh người dùng hoặc client đoán kết quả từ việc popup đóng hay một request bị timeout.

### 2.3. Bất biến quan trọng

**Khi chưa có kết quả server chấp nhận cho yêu cầu hiện tại, hành động cần xác thực lại vẫn bị chặn.**

Không cho phép client bỏ qua bước đó bằng cách:

- Đóng hộp thoại.
- Chọn một URL tiếp tục.
- Gửi cờ `reauthenticated=true`.
- Trình access token vừa được refresh.
- Nhập sai đủ số lần để được chuyển tự động sang nhánh yếu hơn.

Các đường API phục vụ hành động phải cùng thực thi điều kiện này, kể cả khi request được gửi trực tiếp.

## 3. Phân loại thất bại trước khi quyết định phản ứng

### 3.1. Nhóm nguyên nhân và kết luận có thể đưa ra

| Nhóm | Ví dụ | Kết luận phù hợp |
| --- | --- | --- |
| Bằng chứng không được chấp nhận | Mật khẩu sai, chữ ký không hợp lệ, OTP không khớp | Chưa xác minh được bằng chứng đó |
| Bằng chứng dùng lại | OTP đã chấp nhận, challenge đã tiêu thụ | Không tạo một lần xác thực mới từ bằng chứng cũ |
| Context hết hạn | Challenge hoặc operation hết thời gian | Cần context mới nếu còn đủ điều kiện |
| Context thay đổi | Session bị thu hồi, target hoặc policy đổi | Kết quả cũ không còn đủ cho yêu cầu hiện tại |
| Người dùng không hoàn tất | Hủy thao tác hoặc không chọn được phương tiện | Chưa có bằng chứng thành công |
| Phương tiện không khả dụng | Thiết bị mất, khóa không kết nối, ứng dụng bị khóa | Có thể cần phương tiện khác hoặc recovery |
| Chính sách chưa đáp ứng | Có xác thực nhưng thiếu phương thức hoặc độ mới yêu cầu | Chưa cấp quyền nhạy cảm |
| Dịch vụ bắt buộc đang lỗi | Verifier, KMS hoặc IdP không khả dụng | Chưa xác định được kết quả cần thiết |
| Kết quả chưa rõ | Response mất sau khi dịch vụ xử lý | Cần tra trạng thái hoặc đối soát |
| Bị hạn chế thử | Vượt ngân sách thử hoặc hạn mức gửi | Chờ hoặc dùng nhánh hợp lệ theo chính sách |

Nhóm lỗi nội bộ có thể chi tiết hơn thông báo cho người dùng. Không phải mọi nguyên nhân đều có thể suy ra chắc chắn từ một mã lỗi phía client.

### 3.2. Một lỗi đơn lẻ chưa chứng minh bị chiếm quyền

Nhập sai mật khẩu có thể là lỗi gõ. Timeout có thể do kết nối. Hủy passkey có thể là người dùng chọn nhầm thao tác.

Hệ thống có thể kết hợp tín hiệu để đánh giá rủi ro, nhưng không nên tự diễn giải mọi thất bại thành kết luận credential đã bị đánh cắp.

Ngược lại, một lời khai “tôi bấm nhầm” cũng không thay đổi kết quả verifier. Quyền nhạy cảm chỉ được cấp khi có bằng chứng phù hợp.

### 3.3. Lỗi hạ tầng khác với bằng chứng sai

Nếu verifier không trả kết quả, hệ thống chưa biết người dùng nhập đúng hay sai. Không nên tăng bộ đếm “mật khẩu sai” chỉ vì một dịch vụ backend đang lỗi.

Vẫn cần hạn mức về tần suất request và chi phí xử lý để tránh lạm dụng. Bộ đếm chống đoán bí mật và bộ đếm chống làm quá tải có mục đích khác nhau.

Trong mọi trường hợp chưa xác minh được, hành động cần reauthentication vẫn chưa được cấp quyền.

## 4. Thất bại ảnh hưởng session như thế nào?

### 4.1. Chặn hành động và kết thúc session là hai quyết định

| Bối cảnh | Hành động nhạy cảm | Session hiện tại |
| --- | --- | --- |
| Session còn hợp lệ, sai một lần khi đổi email | Giữ trạng thái bị chặn | Có thể giữ quyền thông thường theo chính sách |
| Người dùng hủy thêm thiết bị tin cậy | Không thêm thiết bị | Không tự nâng quyền; xử lý session theo trạng thái vốn có |
| Session đã hết timeout bắt buộc | Không tiếp tục hành động | Kết thúc hoặc yêu cầu thiết lập lại session theo quy định |
| Có căn cứ session bị đánh cắp | Không chấp nhận reauthentication từ context không còn tin cậy | Thu hồi hoặc giới hạn theo quyết định sự cố |
| Verifier tạm lỗi khi xuất dữ liệu | Chờ hoặc báo lỗi | Chỉ giữ những quyền còn hợp lệ theo chính sách |
| Credential cần dùng đã bị thu hồi | Không dùng credential đó để cấp quyền | Xét phạm vi ảnh hưởng đến session, không tự phục hồi credential |

Giữ quyền thông thường chỉ áp dụng khi session vẫn còn được chấp nhận và quyền đó chưa bị chính sách khác hạn chế. Không dùng bảng này để kéo dài một phiên đã hết hiệu lực.

### 4.2. Không cập nhật độ mới từ lần thử thất bại

Các trường có thể cần phân biệt:

~~~text
last_activity_at
last_successful_auth_at
reauthentication_required_for_action
reauthentication_deadline
session_expires_at
~~~

Một request thử lại không được tự trở thành `last_successful_auth_at`. Việc cập nhật hoạt động theo quy tắc inactivity là một quyết định riêng, không thay thế bằng chứng xác thực mới.

NIST phân biệt inactivity timeout và overall timeout; khi timeout áp dụng đã hết, session phải được kết thúc. Xác thực lại thành công có tác động riêng lên các giới hạn đó. [NIST SP 800-63B-4, Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b/session/#reauthentication)

Vì vậy, liên tục gửi request sai hoặc refresh token không được làm overall deadline dịch chuyển như một lần xác thực thành công.

### 4.3. Đừng mặc định mọi reauthentication đều cùng yêu cầu

Một chính sách có thể yêu cầu MFA cho hành động đặc biệt, trong khi quy tắc reauthentication định kỳ có điều kiện khác.

Ví dụ, NIST SP 800-63B-4 có điều kiện riêng cho reauthentication tại AAL2 khi inactivity timeout đã xảy ra nhưng overall timeout chưa hết; yêu cầu tại AAL3 khác với trường hợp đó. [NIST SP 800-63B-4, Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b/aal/)

Triển khai cần đối chiếu đúng tình huống, không tự bỏ yếu tố vì tiện và cũng không tuyên bố một tổ hợp luôn đủ cho mọi hành động.

### 4.4. Quyền step-up cũ cần được đánh giá đúng phạm vi

Nếu một sự kiện rủi ro mới buộc xác thực lại cho operation hiện tại, một cờ MFA cũ trên session chưa chắc còn đáp ứng.

Cần xác định rõ grant nào đã bị thay thế hoặc không còn đủ độ mới. Không dùng một cờ `mfa_verified` toàn cục để bỏ qua yêu cầu mới.

Các quyền không liên quan không nhất thiết cùng bị thu hồi. Phạm vi phản ứng phải theo quyết định và trạng thái thực tế.

## 5. Mô hình operation, attempt và kết quả giới hạn

### 5.1. Tách operation khỏi mỗi lần thử

Một operation có thể yêu cầu người dùng xác thực lại trước khi đổi email. Trong operation đó có thể có nhiều attempt, mỗi attempt có request hoặc challenge riêng.

~~~text
ReauthenticationOperation
    operation_id
    account_id
    tenant_context
    session_reference
    session_security_version
    action
    target_reference
    target_revision
    policy_version
    generation
    state
    created_at
    expires_at

ReauthenticationAttempt
    attempt_id
    operation_id
    generation
    method
    challenge_or_request_reference
    state
    result_reference
    internal_reason_code
    submitted_at
~~~

Biết operation ID không tự tạo quyền thao tác. Server phải kiểm tra liên kết với account, session hoặc context đã được cấp quyền.

### 5.2. Vòng đời của operation minh họa

~~~mermaid
stateDiagram-v2
    [*] --> REQUIRED
    REQUIRED --> IN_PROGRESS
    IN_PROGRESS --> RETRY_ALLOWED: Lỗi có thể thử lại theo chính sách
    RETRY_ALLOWED --> IN_PROGRESS: Attempt mới còn được phép
    IN_PROGRESS --> WAITING_FOR_DEPENDENCY: Chưa có kết quả xác minh
    WAITING_FOR_DEPENDENCY --> IN_PROGRESS: Có thể đối soát hoặc thử lại hợp lệ
    IN_PROGRESS --> THROTTLED: Chạm hạn mức
    THROTTLED --> RETRY_ALLOWED: Đủ điều kiện thử tiếp
    IN_PROGRESS --> VERIFIED: Đủ bằng chứng và context
    IN_PROGRESS --> CANCELLED
    RETRY_ALLOWED --> EXPIRED
    WAITING_FOR_DEPENDENCY --> EXPIRED
    THROTTLED --> EXPIRED
    IN_PROGRESS --> INVALIDATED: Context không còn phù hợp
    VERIFIED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
    INVALIDATED --> [*]
~~~

Mọi trạng thái đang mở đều cần bị kiểm tra expiry khi sử dụng, kể cả khi sơ đồ không vẽ từng cạnh hết hạn. Trạng thái wait hoặc throttle không tự gia hạn lifetime của operation.

`VERIFIED` chỉ phản ánh operation reauthentication đã đáp ứng điều kiện. Hành động nghiệp vụ còn cần kiểm tra quyền và commit riêng.

### 5.3. Kết quả thành công cần có phạm vi

Một kết quả minh họa có thể gắn với:

~~~text
account A
session S
action CHANGE_RECOVERY_EMAIL
pending target E2
operation O1
generation 4
policy P
verified_at
expires_at
~~~

Một lần xác thực cho đổi email không mặc nhiên cho phép xóa MFA, xuất recovery code hoặc thay chủ sở hữu tổ chức.

Nếu target hoặc generation thay đổi, server cần đánh giá lại kết quả. Không chuyển proof từ một thao tác đã hủy sang thao tác mới chỉ vì người dùng vẫn ở cùng browser tab.

## 6. Luồng xử lý thất bại tổng quát

### 6.1. Giữ hành động ở phía sau cổng kiểm tra

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant A as Dịch vụ ứng dụng
    participant V as Verifier
    participant S as Kho trạng thái
    U->>C: Yêu cầu hành động nhạy cảm
    C->>A: Gửi yêu cầu
    A->>S: Kiểm tra quyền và yêu cầu xác thực lại
    A-->>C: Operation giới hạn
    U->>C: Trình bằng chứng
    C->>A: Gửi attempt
    A->>V: Xác minh theo phương thức
    V-->>A: Không đạt hoặc chưa có kết quả
    A->>S: Ghi trạng thái, reason và hạn mức phù hợp
    A-->>C: Thử lại, chờ, recovery hoặc kết thúc theo chính sách
    Note over A,S: Hành động nhạy cảm chưa được thực thi
~~~

Ứng dụng có thể lưu một yêu cầu pending, nhưng pending chưa được áp dụng như thay đổi chính thức. Ví dụ, email mới chưa được dùng làm kênh recovery chỉ vì người dùng đã nhập nó trước bước reauthentication.

### 6.2. Một thứ tự quyết định minh họa

~~~text
handleAttempt(context, operation, attempt):
    kiểm tra caller có quyền với operation
    kiểm tra operation còn hiệu lực và đúng generation
    kiểm tra session/account chưa bị thu hồi hoặc đổi ngoài phạm vi
    kiểm tra ngân sách request và ngân sách thử

    gọi verifier phù hợp bằng request có định danh

    nếu kết quả chưa rõ:
        lưu trạng thái cần đối soát
        không cấp quyền nhạy cảm

    nếu bằng chứng bị từ chối:
        ghi một kết quả cho attempt
        cập nhật bộ đếm tương ứng
        quyết định thử lại, throttle hoặc kết thúc

    nếu verifier chấp nhận:
        kiểm tra lại context, method, freshness và policy
        nếu context không còn phù hợp:
            không cấp grant
        nếu còn phù hợp:
            lưu kết quả verified trong phạm vi được phép
~~~

Mã giả nhấn mạnh thứ tự nghiệp vụ. Một triển khai hoàn chỉnh còn cần chống replay, tính nguyên tử, kiểm tra giao thức và xử lý cạnh tranh.

## 7. Xử lý lỗi theo phương tiện xác thực

### 7.1. Mật khẩu

Khi mật khẩu không được chấp nhận:

- Không thực hiện hành động đang chờ.
- Không đánh dấu một thành phần chưa đạt thành đã đạt.
- Áp dụng hạn mức chống đoán theo account và các chiều phù hợp.
- Cho người dùng thử lại hoặc đi vào đường đặt lại mật khẩu được hỗ trợ.

Không lưu mật khẩu vừa nhập vào operation, queue hoặc log để “tự thử lại sau”. Nếu verifier tạm lỗi, client cần một kết quả rõ về bước tiếp theo mà không giữ bí mật lâu hơn cần thiết.

Đặt lại mật khẩu là một luồng cấp quyền khác. Link quên mật khẩu không được tự biến thành quyền thực hiện hành động nhạy cảm ban đầu.

### 7.2. TOTP hoặc mã dùng một lần

Một mã không được chấp nhận có thể do sai tài khoản trong ứng dụng, sai bước thời gian, đã dùng hoặc không đúng factor.

Server cần kiểm tra theo cấu hình và cửa sổ được chọn. RFC 6238 yêu cầu không chấp nhận OTP lần thứ hai sau khi lần đầu đã được xác minh thành công và phân tích tác động của cửa sổ thời gian. [RFC 6238, Validation and Time-Step Size](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2)

Hướng dẫn thử lại có thể yêu cầu chọn đúng mục trong ứng dụng và dùng mã còn hiệu lực. Không mở cửa sổ thời gian vô hạn để vượt lỗi.

Nếu mã đã được chấp nhận nhưng response mất, request lặp cần được xử lý theo attempt/result đã lưu khi phù hợp. Không trình cùng mã như một lần xác thực độc lập mới.

Nhân viên hỗ trợ không cần nhận seed hoặc mã OTP thô trong ticket để chẩn đoán lỗi.

### 7.3. WebAuthn và passkey

`NotAllowedError` không phải bằng chứng chắc chắn rằng người dùng nhập sai PIN hay rằng một credential không tồn tại. Đặc tả có nhiều đường dẫn đến lỗi này; ứng dụng cần tránh suy luận vượt quá dữ kiện. [W3C WebAuthn, Web Authentication API](https://www.w3.org/TR/webauthn-3/)

Các bước xử lý có thể gồm:

- Giúp người dùng chọn đúng phương tiện đã thiết lập.
- Hướng dẫn kiểm tra kết nối hoặc client tương thích.
- Cho phép thử lại bằng ceremony mới khi còn đủ điều kiện.
- Cung cấp đường dùng authenticator khác đáp ứng chính sách.
- Chuyển sang recovery nếu phương tiện bắt buộc thực sự không còn.

Phía server vẫn cần verifier kiểm tra challenge, origin, RP ID, chữ ký, trạng thái credential và các yêu cầu xác thực tương ứng.

Không hạ yêu cầu user verification hoặc bỏ kiểm tra origin vì browser báo lỗi. Không yêu cầu người dùng nhập PIN authenticator vào form hỗ trợ của RP.

### 7.4. Push bị từ chối hoặc không phản hồi

Từ chối push nghĩa là chưa có kết quả được chấp nhận cho yêu cầu đó. Không phản hồi cũng không được diễn giải thành đồng ý.

Giao diện cần cho biết hành động nào đang được xác nhận, có thể hủy và có đường dùng phương tiện khác theo chính sách.

Hạn mức gửi và khoảng chờ giúp giảm việc phát push liên tục. Đừng dùng việc gửi nhiều thông báo để bù cho thiếu bằng chứng.

### 7.5. Thành công một phần

Giả sử mật khẩu đã đạt nhưng MFA chưa đạt. Server có thể lưu kết quả thành phần trong thời hạn ngắn nếu chính sách cho phép, gắn với đúng operation và generation.

Kết quả đó không phải reauthentication hoàn chỉnh. Không cập nhật `last_successful_auth_at` của toàn yêu cầu hoặc cấp quyền cuối cùng trước khi đủ tổ hợp.

Thời hạn của thành phần đã đạt không được kéo dài vô hạn bằng các lần thất bại ở thành phần sau.

## 8. Thất bại khi xác thực lại qua IdP hoặc SSO

### 8.1. Redirect thành công chưa chứng minh độ mới

RP và IdP có session riêng. Một lượt đi qua IdP có thể trả lại assertion từ phiên còn tồn tại mà người dùng chưa thực hiện lần xác thực mới theo yêu cầu của RP.

RP cần xác định dữ liệu nào chứng minh yêu cầu của mình đã được đáp ứng. Token được mint gần đây không tự đồng nghĩa con người vừa được xác thực.

OIDC định nghĩa `max_age` để yêu cầu độ mới và `auth_time` trong ID Token khi dùng tham số này. RP cần xác minh kết quả theo giao thức và chính sách. [OpenID Connect Core, Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest)

### 8.2. Lỗi cần tương tác khác với mật khẩu sai

Với yêu cầu không tương tác như `prompt=none`, IdP có thể trả `login_required` hoặc `interaction_required` khi cần người dùng tương tác. Các mã này không tự kết luận người dùng đã nhập sai một bí mật. [OpenID Connect Core, Authentication Error Response](https://openid.net/specs/openid-connect-core-1_0.html#AuthError)

Ứng dụng có thể chuyển sang luồng tương tác phù hợp khi chính sách và context cho phép. Không lặp redirect im lặng vô hạn và không chấp nhận token cũ để làm yêu cầu biến mất.

### 8.3. Principal trả về phải đúng principal đang thao tác

Người dùng có thể chọn một account khác tại IdP. Dù account mới xác thực thành công, kết quả đó chưa có quyền thay thông tin của account ban đầu.

RP cần kiểm tra issuer và subject đã được liên kết, cùng state, nonce và những điều kiện của flow tương ứng. Không đối chiếu chỉ bằng email hiển thị hoặc chấp nhận bất kỳ account nào ở cùng tổ chức.

Nếu principal thay đổi, cần hủy hoặc khởi tạo lại context đúng mục đích. Không tự chuyển operation nhạy cảm sang account vừa được chọn.

### 8.4. IdP không khả dụng

Nếu IdP bắt buộc đang lỗi, hành động cần reauthentication vẫn chưa đủ điều kiện. Các lựa chọn có thể là chờ, thử lại có kiểm soát hoặc dùng phương thức khác đã được sản phẩm hỗ trợ.

Không dùng outage làm điều kiện tự bật một đường bypass. Lỗi IdP cũng không tự chứng minh mọi session tại RP cần bị thu hồi; quyết định đó dựa trên timeout, rủi ro và phạm vi riêng.

## 9. Hạn mức thử và phản ứng với lạm dụng

### 9.1. Đếm theo đúng sự kiện

| Sự kiện | Bộ đếm có thể liên quan | Điều cần tránh |
| --- | --- | --- |
| Mật khẩu hoặc OTP bị verifier từ chối | Ngân sách đoán theo account/factor và nguồn | Chỉ giới hạn IP rồi bỏ lọt nhiều nguồn |
| Tạo challenge liên tục | Hạn mức tạo context và chi phí | Tạo context mới để reset mọi hạn mức |
| Client báo đã hủy passkey | Hạn mức request và telemetry phù hợp | Tự coi lời báo client là một lần sai PIN |
| Verifier timeout hoặc KMS lỗi | Hạn mức request, circuit breaker và chỉ số hạ tầng | Tăng bộ đếm sai bí mật như đã có kết luận |
| Retry cùng attempt đã xử lý | Idempotency và hạn mức request | Đếm thành nhiều lần đoán độc lập |
| Gửi push hoặc mã liên tục | Hạn mức gửi và chi phí theo đích | Dồn thông báo lên người dùng để ép chấp thuận |

OWASP lưu ý việc throttling cần xét account và nguy cơ cơ chế khóa bị lạm dụng để gây từ chối dịch vụ. [OWASP, Login Throttling và Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#login-throttling)

Các hạn mức có thể phối hợp theo account, factor, operation, session, nguồn và chi phí. Mỗi chiều giải quyết một phần vấn đề; không cần áp cùng một phản ứng cho mọi lỗi.

### 9.2. Khóa một hành động khác với khóa toàn account

Sau nhiều lần thất bại, sản phẩm có thể:

- Tạm ngừng thử cho operation hoặc phương thức.
- Yêu cầu chờ trước attempt mới.
- Yêu cầu một phương tiện khác đã được chấp nhận.
- Kết thúc context hoặc session có rủi ro.
- Chuyển hồ sơ đến nhánh recovery được hỗ trợ.

Khóa toàn account là tác động rộng hơn, cần chính sách và căn cứ phù hợp. Một người chỉ biết tên đăng nhập không nên dễ dàng làm mọi session của nạn nhân mất quyền.

Mặt khác, một session có dấu hiệu bị chiếm không được tiếp tục hoạt động chỉ để tránh gây gián đoạn. Chọn phản ứng cần dựa trên tín hiệu, mức độ tin cậy và tác động.

### 9.3. Hạn mức cần sống qua các lần tạo context

Nếu mỗi challenge mới có ba lượt thử nhưng người gọi tạo được vô hạn challenge, giới hạn ba lượt không bảo vệ được account.

Cần có ngân sách tổng hợp phù hợp và cập nhật nhất quán giữa các verifier. Các request cạnh tranh không được cùng đọc một bộ đếm cũ rồi vượt ngưỡng ngoài ý định.

Thời hạn operation cũng không tự được kéo dài khi người dùng chờ hết một khoảng throttle. Sau khi chờ, server vẫn kiểm tra operation còn sống và phương thức còn được phép.

### 9.4. Chuyển phương thức cần kiểm tra chính sách

Nút “dùng cách khác” nên chọn từ những phương thức đã được sản phẩm chấp nhận cho mục đích đó.

Nhập sai passkey hoặc TOTP nhiều lần không tạo quyền hạ yêu cầu xuống một email mới tự khai. CAPTCHA, câu hỏi thông tin công khai hay IP quen thuộc cũng không tự thay thế bằng chứng bắt buộc.

Nếu phương thức thay thế thực chất là recovery, giao diện và quyền server cần phản ánh đúng sự chuyển nhánh.

## 10. Retry, replay và kết quả chưa rõ

### 10.1. Attempt mới khác với gửi lại request cũ

Có hai tình huống:

~~~text
Attempt mới:
    người dùng chủ động trình bằng chứng cho lần thử tiếp theo
    có request/challenge mới khi phương thức cần

Retry:
    client gửi lại cùng request vì chưa biết kết quả
    cần tra hoặc trả lại kết quả của attempt cũ
~~~

Idempotency key cần gắn với account, operation, generation và nội dung liên quan. Cùng key với một proof khác không được âm thầm coi là cùng request thành công.

Mọi lần đọc kết quả vẫn cần xác minh quyền đối với operation. Không công khai trạng thái chỉ từ một attempt ID.

### 10.2. Timeout không phải bằng chứng chắc chắn bị từ chối

Ví dụ:

1. Verifier đã chấp nhận OTP.
2. Server lưu kết quả cho attempt A1.
3. Response về client bị mất.
4. Client hiển thị lỗi kết nối.

Nếu người dùng gửi lại OTP như một attempt mới, mã có thể đã bị tiêu thụ. Cách tốt hơn là tra kết quả A1 hoặc trả kết quả đã lưu khi retry đúng request.

Nếu một dịch vụ bên ngoài có thể đã xử lý nhưng trạng thái local chưa biết, operation cần ở trạng thái chờ đối soát. Chưa có kết quả được server chấp nhận thì chưa cấp quyền nhạy cảm.

Không gọi lại verifier vô hạn với cùng bí mật chỉ để “chắc chắn”. Việc đối soát nên dùng request reference và giao thức mà dịch vụ thực sự hỗ trợ.

### 10.3. Challenge đã đóng không được sống lại

Khi attempt đã terminal hoặc operation bị thay thế, challenge không được trở lại trạng thái chấp nhận chỉ vì một response đến muộn.

Một attempt mới cần dữ liệu mới phù hợp với phương thức. Server vẫn giữ các hạn mức tổng hợp và các điều kiện của operation.

Với TOTP, mã không tự chứa challenge của ứng dụng. Binding giữa kết quả TOTP và operation là trách nhiệm của verifier cùng trạng thái server; không được giả định mã số đã ký toàn bộ nội dung hành động.

Với WebAuthn, challenge mới và kiểm tra context giúp chống dùng lại phản hồi của ceremony khác. Nó không thay thế việc kiểm tra quyền tài khoản và trạng thái credential.

### 10.4. Kết quả đến muộn không nhất thiết còn dùng được

Giả sử người dùng hủy operation O1 rồi tạo O2. Một kết quả thành công của O1 xuất hiện sau đó.

Server có thể lưu kết quả lịch sử để giải thích điều đã xảy ra, nhưng không được tự gắn nó vào O2.

Tương tự, một proof từng hợp lệ có thể không còn đủ nếu session đã bị thu hồi hoặc policy yêu cầu nghiêm ngặt hơn. “Verifier từng trả thành công” khác với “hiện tại được phép thực hiện hành động”.

## 11. Bảo vệ điểm commit của hành động nhạy cảm

### 11.1. Cổng kiểm tra phải ở phía server

Một lỗi thiết kế:

~~~text
Frontend:
    nếu popup xác thực lại thành công thì hiện nút lưu

Backend:
    nhận request lưu từ session bất kỳ còn hợp lệ
~~~

Đối tượng có thể gọi endpoint lưu trực tiếp. Điều kiện reauthentication cần nằm ở backend cho mọi đường có thể tạo cùng tác động.

Nếu có nhiều API cho cùng một thay đổi, như giao diện web, ứng dụng di động và endpoint quản trị, mỗi đường phải thực thi điều kiện theo quyền của nó.

### 11.2. Kiểm tra lại sau khi verifier trả kết quả

Trong thời gian người dùng xác thực:

- Session có thể bị thu hồi.
- Credential có thể bị ngừng do sự cố.
- Target email hoặc thiết bị có thể bị thay đổi.
- Role hoặc membership có thể không còn.
- Policy có thể được cập nhật.
- Một operation cạnh tranh có thể đã hoàn tất.

Vì vậy, kết quả verifier cần được đánh giá lại với context có thẩm quyền trước khi cấp grant hoặc thực hiện hành động.

Không nên dùng mọi cập nhật hoạt động session làm security version; các version cần phản ánh thay đổi có ý nghĩa bảo mật để tránh tạo vòng lặp xác thực không cần thiết.

### 11.3. Mã giả tiêu thụ grant cùng thay đổi

~~~text
commitSensitiveAction(caller, operation, grant):
    BEGIN

    kiểm tra quyền caller với account và target
    kiểm tra operation chưa bị hủy, hết hạn hoặc thay thế
    kiểm tra grant đúng account, session/context, action và generation
    kiểm tra verified_at và expires_at theo policy hiện tại
    kiểm tra session security version và trạng thái credential liên quan
    kiểm tra target revision và những điều kiện nghiệp vụ bắt buộc
    kiểm tra grant chưa bị tiêu thụ

    nếu có điều kiện không đạt:
        không áp dụng thay đổi nhạy cảm
        trả trạng thái cần thử lại hoặc bắt đầu context mới

    áp dụng thay đổi
    tiêu thụ grant và lưu kết quả operation
    ghi audit/outbox

    COMMIT
~~~

Mã giả áp dụng cho các dữ liệu nằm trong cùng miền giao dịch. Nếu hành động đi qua dịch vụ ngoài, cần một operation bền vững và cơ chế nhất quán phù hợp; không giả định một transaction database có thể bao trùm mọi thành phần.

### 11.4. Thất bại ở bước nghiệp vụ không sửa lịch sử xác thực

Người dùng có thể đã reauthenticate đúng nhưng thay đổi thất bại vì xung đột revision hoặc tài nguyên không còn.

Hệ thống nên ghi riêng:

~~~text
authentication_result = ACCEPTED
action_result = NOT_APPLIED_DUE_TO_CONFLICT
~~~

Không ghi sự kiện này như mật khẩu sai. Nếu cho phép dùng lại grant cho một retry, phạm vi và trạng thái phải còn phù hợp; không tự mở rộng quyền sang target mới.

Nếu commit đã xảy ra nhưng response mất, cần trả kết quả nghiệp vụ đã lưu. Không thực hiện thay đổi lần nữa hoặc yêu cầu người dùng đoán rằng lần trước chưa thành công.

### 11.5. Gắn operation không tự thành ký giao dịch

Gắn grant với action và target giúp server ngăn dùng lại sai phạm vi. Điều đó không tự chứng minh người dùng đã nhìn thấy và chấp thuận mọi chi tiết trên một màn hình đáng tin.

Với giao dịch có yêu cầu xác nhận nội dung cao hơn, sản phẩm cần thiết kế transaction authorization và kênh hiển thị phù hợp. Một lỗi reauthentication không nên được “sửa” bằng cách bỏ bước xác nhận nội dung.

## 12. Chuyển sang account recovery khi không còn phương tiện

### 12.1. Phân biệt thử lại với recovery

| Điều còn khả dụng | Nhánh có thể dùng | Điều kiện phải giữ |
| --- | --- | --- |
| Nhập sai nhưng phương tiện vẫn còn | Thử lại trong hạn mức | Không kéo dài operation hoặc hạ yêu cầu tự động |
| Có authenticator khác đã đăng ký | Xác thực bằng phương thức đáp ứng chính sách | Không mặc định mọi phương thức tương đương |
| Mất MFA nhưng có bằng chứng recovery được hỗ trợ | Luồng recovery riêng | Quyền và bằng chứng gắn với hồ sơ, có phạm vi |
| Chỉ còn session đang hoạt động | Có thể tiếp tục bước được phép | Session không tự đủ quyền thay toàn bộ phương tiện |
| Chỉ có email hoặc số mới tự khai | Xác nhận kênh mới nếu cần | Chưa chứng minh quyền với account cũ |
| Không còn bằng chứng phù hợp | Chờ bổ sung hoặc kết thúc theo chính sách | Không hứa hỗ trợ luôn có thể cấp quyền |

Quy trình recovery cần được mô tả trước và bảo vệ khỏi lạm dụng. Số lần reauthentication thất bại không phải một loại bằng chứng sở hữu.

### 12.2. Recovery thành công có thể cấp quyền khác

Một hồ sơ recovery có thể được chấp nhận để đăng ký lại MFA. Kết quả đó có thể là:

~~~text
purpose = REENROLL_MFA
account = A
case = R1
allowed_target = phương tiện thuộc quyết định
expires_at = thời hạn
~~~

Đây chưa phải quyền đổi email recovery, xuất dữ liệu hay thực hiện giao dịch ban đầu.

Sau khi phương tiện mới active, sản phẩm có thể yêu cầu đăng nhập hoặc reauthentication theo chính sách của hành động. Không gắn nhãn mọi recovery result thành `reauthenticated=true` cho toàn ứng dụng.

### 12.3. Không phục hồi phương tiện cũ chỉ để vượt bước bị lỗi

Nếu credential bị thu hồi do mất hoặc lộ, thất bại khi thử bằng credential đó là hành vi đúng của hệ thống.

Nhân viên hỗ trợ không nên bật lại credential chỉ để người dùng đi qua màn hình xác thực lại. Cần dùng đường đã được cấp quyền để thiết lập phương tiện thay thế hoặc xử lý sự cố theo chính sách.

Nếu không còn bằng chứng được chấp nhận, có thể chưa khôi phục được. Áp lực hoàn tất một hành động không tự tạo thêm quyền cho người yêu cầu.

## 13. Giao diện lỗi và dữ liệu được giữ lại

### 13.1. Thông báo đủ để hành động tiếp

| Tình huống | Thông báo minh họa | Bước tiếp theo |
 --- | --- | --- |
| Chưa xác minh được bằng chứng | “Chưa xác thực được. Hãy kiểm tra và thử lại.” | Thử trong hạn mức hoặc chọn phương thức được hỗ trợ |
| Người dùng chưa hoàn tất ceremony | “Xác thực chưa hoàn tất. Bạn có thể thử lại.” | Ceremony mới khi còn đủ điều kiện |
| Operation hết hạn | “Yêu cầu xác thực đã hết hạn. Hãy bắt đầu lại.” | Tạo context mới |
| Hạn mức tạm thời | “Vui lòng chờ trước khi thử tiếp.” | Theo thời điểm server cho phép |
| Verifier đang lỗi | “Hiện chưa thể xác thực. Hãy thử lại sau.” | Chờ hoặc dùng nhánh khác được hỗ trợ |
| Session không còn hợp lệ | “Phiên này cần được thiết lập lại.” | Login hoặc recovery phù hợp |
| Không còn phương tiện xác thực | “Dùng phương thức dự phòng hoặc bắt đầu khôi phục tài khoản.” | Quy trình recovery có điều kiện |

Các thông báo là ví dụ về ý nghĩa, không phải danh sách bắt buộc. Client không cần thấy mọi reason code nội bộ.

### 13.2. Mức chi tiết phụ thuộc context được phép

Ở endpoint công khai, thông báo không nên làm lộ account có tồn tại, factor nào đã được đăng ký hoặc account có đang bị khóa.

Trong context đã được cấp quyền, có thể đưa hướng dẫn phù hợp hơn như chọn đúng mục TOTP, kiểm tra thời gian thiết bị hoặc dùng khóa đã thiết lập. Không cần biến mọi lỗi thành một câu mơ hồ khiến người dùng không biết bước tiếp theo.

OWASP lưu ý phản hồi và khác biệt hành vi của chức năng xác thực có thể làm lộ thông tin account. [OWASP, Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)

### 13.3. Giữ dữ liệu nháp với phạm vi rõ ràng

Một thao tác bị chặn có thể chứa dữ liệu người dùng đã nhập. Ứng dụng có thể giữ bản nháp nếu phù hợp với độ nhạy cảm và trạng thái session.

Cần xác định:

- Bản nháp giữ ở client hay server, và trong bao lâu.
- Ai còn được phép đọc sau khi session thay đổi.
- Dữ liệu nào phải xóa khi logout hoặc context bị thu hồi.
- Target có phải kiểm tra lại trước khi commit không.

Không giữ password, OTP, seed hoặc token reauthentication trong draft. Một email mới hoặc thiết bị mới ở trạng thái pending chưa được trở thành phương tiện recovery chính thức.

### 13.4. Tránh vòng lặp gây khó sử dụng

Nếu người dùng quay lại từ IdP nhưng vẫn thiếu điều kiện, client cần hiển thị một kết quả có thể xử lý, không redirect liên tục.

Nút hủy nên đưa về trạng thái an toàn với hành động chưa thực thi. Nút thử lại chỉ khởi tạo attempt mới khi server cho phép.

Nếu session đã kết thúc, giao diện cần ngừng gửi proof từ operation cũ. Không lưu một callback cũ rồi tự áp dụng nó sau khi người dùng đăng nhập account khác.

## 14. Logging, giám sát và hỗ trợ

### 14.1. Reason code nội bộ nên có ý nghĩa ổn định

Các sự kiện minh họa:

~~~text
REAUTH_REQUIRED
REAUTH_ATTEMPT_SUBMITTED
REAUTH_PROOF_REJECTED
REAUTH_NOT_COMPLETED
REAUTH_CONTEXT_EXPIRED
REAUTH_CONTEXT_INVALIDATED
REAUTH_THROTTLED
REAUTH_DEPENDENCY_UNAVAILABLE
REAUTH_RESULT_UNKNOWN
REAUTH_VERIFIED
REAUTH_GRANT_REJECTED_AT_COMMIT
REAUTH_RECOVERY_STARTED
~~~

Một báo cáo client rằng người dùng hủy chỉ là một nguồn dữ kiện. Log cần phân biệt tín hiệu client, kết luận verifier và quyết định chính sách.

Không đặt tên một sự kiện là “sai PIN” nếu RP chỉ nhận một lỗi WebAuthn không đủ cụ thể.

### 14.2. Ghi dữ liệu phục vụ điều tra, bảo vệ bí mật

Có thể ghi:

- Operation và attempt reference.
- Account hoặc tenant reference theo quyền truy cập.
- Loại phương thức và verifier.
- Policy version, generation và session security version.
- Reason code, thời điểm và thời gian phản hồi.
- Kết quả xác thực riêng với kết quả nghiệp vụ.

Không ghi password, OTP thô, seed, assertion nguyên vẹn không cần thiết, session cookie hay token recovery.

Mã hỗ trợ cho người dùng nên là reference tra cứu, không phải một capability cho phép bỏ qua bước xác minh.

### 14.3. Theo dõi cả tấn công lẫn lỗi sản phẩm

Các chỉ số hữu ích có thể gồm:

| Chỉ số | Câu hỏi có thể giải đáp |
| --- | --- |
| Tỷ lệ từ chối theo phương thức | Có tăng đột biến do đoán mã hoặc lỗi triển khai không |
| Tỷ lệ timeout theo verifier | Có outage bị ghi nhầm thành người dùng sai không |
| Tỷ lệ context hết hạn | Có vòng lặp hoặc thời gian xử lý vượt lifetime không |
| Số request cùng operation/generation | Có replay hoặc retry không được xử lý đúng không |
| Tỷ lệ chuyển recovery | Có nhóm người dùng thường xuyên mất phương tiện không |
| Grant bị từ chối tại commit | Có thay đổi context cạnh tranh hoặc ràng buộc chưa rõ không |

Một lỗi đơn lẻ không nhất thiết cần cảnh báo gửi đến người dùng. Cảnh báo nên dựa trên mẫu hành vi và tác động để tránh spam hoặc làm lộ thông tin.

### 14.4. Hỗ trợ không cần bí mật của người dùng

Nhân viên có thể dùng mã lỗi, thời điểm, phương thức và trạng thái operation để hướng dẫn.

Không yêu cầu gửi mật khẩu, PIN authenticator, QR seed hay ảnh chụp OTP vào ticket. Không có nút “đánh dấu reauthenticated” chỉ từ lời khai của người yêu cầu.

Nếu có một nhánh tác nghiệp thay thế, nhánh đó cần thẩm quyền, bằng chứng và audit riêng. Nó không được che giấu dưới việc sửa một lỗi frontend.

## 15. Ví dụ xuyên suốt

### 15.1. Nhập sai TOTP khi đổi email recovery

Minh có session còn hợp lệ và muốn đổi email recovery sang E2. Chính sách yêu cầu reauthentication với phương tiện đã thiết lập.

1. Server tạo operation O1 và lưu E2 ở trạng thái pending.
2. Minh nhập một mã không được chấp nhận.
3. Server ghi kết quả attempt, cập nhật hạn mức tương ứng.
4. E2 chưa trở thành email recovery.
5. Minh có thể thử lại hoặc hủy theo trạng thái O1.
6. Chỉ khi đủ bằng chứng và commit hợp lệ, E2 mới có hiệu lực.

Nếu Minh đổi E2 thành E3 trong lúc chờ, proof gắn với target cũ không được tự áp dụng cho target mới ngoài chính sách.

Session còn hợp lệ có thể tiếp tục các quyền thông thường. Điều đó không mở quyền đổi email khi bước xác thực lại vẫn chưa đạt.

### 15.2. Hủy passkey, rồi phát hiện mất khóa

Lan chọn reauthentication bằng passkey nhưng đóng hộp thoại. RP nhận một kết quả không hoàn tất.

Hệ thống không kết luận Lan nhập sai PIN hoặc lập tức thu hồi mọi session. Hành động nhạy cảm vẫn bị chặn và Lan có thể chọn phương thức phù hợp.

Sau đó Lan xác nhận khóa thực sự đã mất và không còn dùng được. Lan đi vào nhánh recovery được hỗ trợ thay vì cố tạo vô hạn ceremony mới.

Quyền recovery, nếu được cấp, chỉ cho các hành động thuộc hồ sơ. Lan cần đáp ứng điều kiện của hành động ban đầu trước khi tiếp tục.

### 15.3. IdP lỗi trong khi session gần hết hạn

Hà cần xác thực lại để xuất dữ liệu. IdP bắt buộc đang không khả dụng.

- Operation chưa đủ điều kiện, dữ liệu chưa được xuất.
- Lỗi không bị ghi như Hà nhập sai mật khẩu.
- Hệ thống cho chờ hoặc thử lại theo chính sách.
- Overall deadline của session không được gia hạn như đã reauthenticate thành công.
- Nếu session hết hiệu lực, các quyền của session đó kết thúc theo chính sách.

Khi IdP hoạt động lại, một callback từ context đã hết hạn không tự tiếp tục yêu cầu xuất. Hà cần context hiện hành và kết quả xác thực đáp ứng yêu cầu.

### 15.4. Verifier thành công nhưng action response bị mất

Phúc đã reauthenticate và yêu cầu thay số điện thoại trong operation O2. Server commit thay đổi rồi response bị mất.

Client tra trạng thái O2 hoặc retry đúng idempotency để lấy kết quả đã lưu. Nó không tự thực hiện thay đổi thêm lần nữa.

Nếu chỉ verifier thành công nhưng bước commit chưa xảy ra, trạng thái phải phân biệt được điều này. UI không dùng lỗi mạng chung để tuyên bố chắc chắn “mã sai” hoặc “thay đổi chưa được áp dụng”.

## 16. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Bằng chứng bị verifier từ chối | Hành động nhạy cảm chưa được thực thi |
| Client gửi cờ reauthenticated hoặc bỏ qua popup | Backend vẫn kiểm tra điều kiện |
| Password đạt nhưng MFA chưa đạt | Không cấp kết quả hoàn chỉnh |
| Mã TOTP đã được chấp nhận trong time step | Không chấp nhận lại như bằng chứng độc lập |
| Retry đúng attempt đã có kết quả | Trả kết quả cũ theo quyền và trạng thái hiện tại |
| Cùng idempotency key nhưng proof khác | Phát hiện xung đột |
| Tạo challenge mới sau nhiều lần sai | Hạn mức tổng hợp vẫn có hiệu lực |
| Client báo hủy passkey | Không tự ghi là sai PIN |
| WebAuthn response sai challenge, origin hoặc account | Bị từ chối theo giao thức và context |
| Thiếu user verification khi chính sách yêu cầu | Không hạ yêu cầu để chấp nhận |
| Verifier hoặc KMS timeout | Không coi là bằng chứng sai và không cấp quyền mặc định |
| Response mất sau khi OTP đã được chấp nhận | Có đường tra hoặc đối soát kết quả |
| Kết quả đến sau khi operation bị hủy | Không làm operation sống lại |
| Session bị thu hồi trong lúc verifier xử lý | Không cấp grant cho context cũ |
| Credential bị thu hồi trước commit | Kiểm tra lại điều kiện theo chính sách |
| Target thay đổi sau khi xác thực | Proof cũ không tự áp dụng ngoài scope |
| Thời hạn session bắt buộc đã hết | Không giữ quyền cũ nhờ việc thử lại |
| Refresh token thành công nhưng người dùng chưa xác thực mới | Không tự cập nhật độ mới của con người |
| OIDC prompt none trả login_required | Chuyển nhánh tương tác phù hợp, không coi ngay là sai mật khẩu |
| IdP trả account khác | Không dùng kết quả cho account gốc |
| Token mới nhưng auth_time không đáp ứng | Không coi reauthentication đã đạt |
| Một operation bị throttle | Không tự khóa toàn account ngoài chính sách |
| Người dùng mất phương tiện bắt buộc | Có nhánh recovery với bằng chứng và scope riêng |
| Recovery chỉ cho phép đăng ký lại MFA | Không dùng để đổi email hoặc xuất dữ liệu tùy ý |
| Action commit thành công nhưng response mất | Retry không tạo tác động lần hai |
| Reauthentication đạt nhưng action xung đột | Ghi riêng kết quả xác thực và kết quả nghiệp vụ |
| Đăng nhập account khác sau khi đóng popup cũ | Callback cũ không chuyển quyền sang account mới |
| Kiểm tra log, draft và ticket | Không có password, OTP, seed hoặc token thô |

## 17. Những điểm cần ghi nhớ

- Reauthentication chưa đạt thì hành động đang cần bằng chứng mới vẫn bị chặn ở server.
- Bằng chứng sai, không hoàn tất ceremony, context hết hạn, lỗi hạ tầng và kết quả chưa rõ cần được phân biệt.
- Một thất bại không tự kéo dài session, tạo độ mới hay biến thành quyền recovery.
- Việc kết thúc session phụ thuộc timeout, chính sách và bằng chứng rủi ro; nó là quyết định riêng với việc chặn hành động.
- Hạn mức phải sống qua nhiều attempt và không trở thành cách để người ngoài khóa nạn nhân tùy ý.
- Retry cần tra kết quả của cùng attempt; replay không được tạo một lần xác thực độc lập.
- Kết quả xác thực phải khớp principal, mục đích, context và trạng thái tại thời điểm cấp quyền hoặc commit.
- Khi phương tiện đã mất, dùng nhánh recovery được hỗ trợ với quyền giới hạn, thay vì hạ điều kiện để vượt lỗi.
