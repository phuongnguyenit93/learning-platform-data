# Recovery API authentication: Xác thực cho API khôi phục tài khoản

API khôi phục tài khoản phải phục vụ người dùng không còn sử dụng được một phần hoặc toàn bộ phương thức đăng nhập thông thường. Nếu mọi endpoint đều yêu cầu đăng nhập trước, người dùng có thể không còn đường khôi phục. Nếu mọi endpoint đều được xem là công khai, kẻ tấn công có thể lợi dụng chúng để đổi mật khẩu hoặc thay yếu tố xác thực.

Cách giải quyết là chia hành trình thành các mức tin cậy rõ ràng. Một yêu cầu bắt đầu khôi phục chưa chứng minh quyền sở hữu tài khoản. Bằng chứng khôi phục hợp lệ có thể tạo ra quyền giới hạn cho một giao dịch; quyền đó cũng chưa đồng nghĩa với một phiên đăng nhập toàn quyền.

Bài học này trình bày cách xác thực và cấp quyền cho API khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực, với trọng tâm là không để quyền vượt quá bằng chứng đã kiểm tra.

## 1. Phân biệt định danh, xác thực và cấp quyền

Ba khái niệm cần được tách rõ trong mã máy chủ:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Định danh tài khoản | Yêu cầu đang nhắc tới tài khoản nào? | Người gọi nhập địa chỉ email |
| Xác minh bằng chứng khôi phục | Người gọi đã trình bày bằng chứng hợp lệ nào? | Token dùng một lần, mã dự phòng, yếu tố còn sử dụng được |
| Cấp quyền cho thao tác | Bằng chứng đó cho phép làm việc gì trong giao dịch này? | Đặt mật khẩu mới, nhưng chưa được xóa MFA |

Địa chỉ email, tên người dùng và ID tài khoản là dữ liệu định danh; chỉ biết chúng không chứng minh quyền khôi phục. Tương tự, một requestId khó đoán có thể giúp định vị giao dịch mà không nên được mặc nhiên xem là bằng chứng đủ để đổi yếu tố xác thực.

Trong một số thiết kế, mã giao dịch đồng thời là một capability bí mật. Khi chọn cách đó, phải công khai trong thiết kế rằng nó là thông tin xác thực và bảo vệ tương ứng. Không vừa gọi một giá trị là “chỉ để tra cứu”, vừa cho phép người giữ nó thực hiện thao tác nhạy cảm.

Khôi phục cũng cần được phân biệt với việc thay một yếu tố khi người dùng vẫn xác thực được bằng phương thức khác. NIST mô tả các phương thức và yêu cầu khôi phục theo bối cảnh bảo đảm danh tính, không coi mọi tình huống mất yếu tố là một quy trình giống nhau. Xem [NIST SP 800-63B: Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html).

## 2. Chia API theo mức tin cậy

Bảng dưới là một hợp đồng API minh họa. Tên đường dẫn và phạm vi quyền là lựa chọn thiết kế của bài học, không phải tên endpoint bắt buộc của một tiêu chuẩn.

| Endpoint minh họa | Thông tin người gọi cần có | Quyền được thực hiện |
| --- | --- | --- |
| POST /recovery/requests | Có thể chưa đăng nhập; cung cấp định danh và mục đích được hỗ trợ | Đề nghị bắt đầu khôi phục |
| POST /recovery/proofs | Mã giao dịch cùng bằng chứng mà máy chủ yêu cầu | Trình bày bằng chứng để máy chủ kiểm tra |
| GET /recovery/session | Credential khôi phục hợp lệ | Đọc trạng thái tối thiểu của chính phiên khôi phục |
| POST /recovery/password | Credential có quyền đặt mật khẩu của đúng giao dịch | Đặt mật khẩu mới |
| POST /recovery/authenticators/options | Credential có quyền đăng ký lại yếu tố tương ứng | Nhận challenge hoặc dữ liệu bắt đầu đăng ký |
| POST /recovery/authenticators/finish | Credential, kết quả đăng ký và điều kiện bổ sung | Hoàn tất việc gắn yếu tố đã được cấp quyền |
| POST /recovery/cancel | Quyền hủy giao dịch tương ứng | Chấm dứt phiên hoặc giao dịch khôi phục |

Endpoint trình bày bằng chứng có thể chưa có credential khôi phục vì đó là nơi credential được hình thành. Tuy nhiên, máy chủ vẫn phải kiểm tra bằng chứng, trạng thái, số lần thử và các điều kiện liên quan trước khi cấp quyền.

Ngược lại, endpoint thay đổi tài khoản không được chỉ dựa vào việc người gọi biết email hoặc requestId. Mỗi yêu cầu không công khai phải có kiểm soát truy cập tại endpoint; gateway không thay thế toàn bộ quyết định này. Đây cũng là nguyên tắc được nêu trong [OWASP: REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#access-control).

“Không yêu cầu đăng nhập thông thường” và “không cần bằng chứng” là hai trạng thái khác nhau. Một controller có thể được cấu hình cho phép người chưa đăng nhập đi vào để trình bày token, nhưng tầng xử lý vẫn phải xác thực token trước khi làm bất cứ việc nhạy cảm nào.

## 3. Không cấp quyền ngay khi khởi tạo yêu cầu

Ví dụ người dùng bắt đầu luồng đặt lại mật khẩu:

~~~http
POST /recovery/requests HTTP/1.1
Host: accounts.example.com
Content-Type: application/json

{
  "identifier": "nguoidung@example.com",
  "purpose": "PASSWORD_RESET"
}
~~~

Phản hồi bên ngoài có thể là:

~~~http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Type: application/json

{
  "message": "Nếu yêu cầu phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký."
}
~~~

Mã 202 trong ví dụ chỉ thể hiện yêu cầu đã được tiếp nhận theo hợp đồng công khai. Nó không xác nhận tài khoản tồn tại, không xác nhận email thuộc người gọi và không có nghĩa tài khoản đã bị thay đổi.

Cần nhất quán cả nội dung, hình dạng phản hồi và cách xử lý thời gian để giảm khả năng dò tài khoản. Không trả thêm “đã bật MFA”, địa chỉ khôi phục đầy đủ hoặc trạng thái đặc biệt chỉ khi tài khoản tồn tại. Nếu thiết kế trả một mã theo dõi cho client, cũng phải xem xét hành vi đó ở cả trường hợp tài khoản có và không có.

OWASP khuyến nghị phản hồi nhất quán và token khôi phục được sinh an toàn, đủ khó đoán, có thời hạn và chỉ dùng một lần. Xem [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Tại thời điểm này, máy chủ chưa nên:

- Tạo một phiên đăng nhập đầy đủ cho người gọi.
- Cấp credential cho phép đổi mật khẩu chỉ vì email đúng định dạng.
- Xóa MFA hoặc thay địa chỉ khôi phục.
- Khóa tài khoản chỉ vì nhận một yêu cầu khôi phục.
- Gửi bằng chứng đến một địa chỉ mới do người gọi tùy ý nhập mà chưa có cơ sở xác minh.

Rate limit, CAPTCHA và đánh giá rủi ro có thể hạn chế lạm dụng bước khởi tạo. Chúng không xác thực quyền sở hữu tài khoản.

## 4. Trao đổi bằng chứng lấy quyền khôi phục giới hạn

Một mô hình dễ kiểm soát là dùng bằng chứng ban đầu để tạo một phiên khôi phục riêng.

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Tiếp nhận yêu cầu
    Requested --> ProofPending: Chuẩn bị phương thức xác minh
    ProofPending --> Authorized: Đủ bằng chứng theo chính sách
    ProofPending --> Denied: Hết hạn hoặc vượt điều kiện
    Authorized --> Completed: Thao tác đúng quyền thành công
    Authorized --> Cancelled: Hủy hoặc thu hồi
    Authorized --> Expired: Hết thời hạn
    Completed --> [*]
    Cancelled --> [*]
    Expired --> [*]
    Denied --> [*]
~~~

Đây là mô hình trạng thái minh họa. Một hệ thống có thể cần nhiều bước xác minh hoặc thời gian chờ; không được chuyển sang Authorized chỉ vì giao diện đã hiển thị thành công.

Ví dụ trình bày bằng chứng:

~~~http
POST /recovery/proofs HTTP/1.1
Host: accounts.example.com
Content-Type: application/json

{
  "requestId": "REQUEST_ID_MINH_HOA",
  "proofType": "ISSUED_RECOVERY_TOKEN",
  "proof": "RECOVERY_TOKEN_MINH_HOA"
}
~~~

Các chuỗi trên chỉ là ký hiệu minh họa. Máy chủ phải tìm giao dịch, kiểm tra phương thức đang được phép và xác minh bằng chứng gắn với giao dịch đó.

Nếu bằng chứng đủ cho mục đích được yêu cầu, máy chủ tạo một credential mới. Credential khôi phục này nên được gắn với:

~~~yaml
credentialType: RECOVERY_SESSION
accountId: server-resolved-account
transactionId: server-resolved-transaction
purpose: PASSWORD_RESET
permissions:
  - recovery:password:commit
expiresAt: server-defined-deadline
proofContext: server-verified-evidence
state: ACTIVE
~~~

Đây là mô hình dữ liệu bên trong máy chủ, không phải nội dung client được quyền tự khai báo để được tin cậy.

### Những ràng buộc quan trọng

AccountId phải lấy từ bản ghi giao dịch hoặc nguồn đã xác minh. Permission và purpose phải do chính sách máy chủ quyết định. Client không được biến một quyền đặt mật khẩu thành quyền xóa MFA bằng cách đổi một field JSON.

Bằng chứng ban đầu và credential của phiên là hai bí mật có vòng đời riêng. Khi trao đổi một token dùng một lần, việc đánh dấu đã dùng và tạo phiên phải được kiểm soát đồng thời để hai người giữ cùng token không tạo ra hai phiên độc lập.

Sau khi tạo phiên thành công, không tiếp tục chấp nhận token cũ như một phương án xác thực thay thế cho mọi endpoint.

## 5. Chọn cơ chế mang credential

### Cookie cho ứng dụng trình duyệt

Một ứng dụng web có thể dùng cookie phiên khôi phục riêng, do máy chủ phát hành, với Secure, HttpOnly và SameSite phù hợp. Không tái sử dụng cookie đó như cookie đăng nhập toàn quyền.

Khi trình duyệt tự gửi cookie, endpoint thay đổi trạng thái cần cơ chế chống CSRF phù hợp. SameSite là một lớp hỗ trợ; không nên xem nó là toàn bộ thiết kế chống CSRF. Hướng dẫn của [OWASP: CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) trình bày các cơ chế như token chống CSRF và kiểm tra nguồn yêu cầu.

Phiên khôi phục mới cần có giá trị do máy chủ sinh, tránh dùng lại một session ID do client chọn. Nếu người dùng đồng thời đang đăng nhập tài khoản A nhưng khôi phục tài khoản B, máy chủ phải áp dụng ràng buộc giao dịch rõ ràng hoặc yêu cầu tách hành trình; không âm thầm lấy tài khoản của cookie đăng nhập làm đích khôi phục.

### Bearer token trong Authorization

API dành cho một client chủ động quản lý credential có thể chọn gửi token theo dạng:

~~~http
POST /recovery/password HTTP/1.1
Host: accounts.example.com
Authorization: Bearer RECOVERY_SESSION_MINH_HOA
Content-Type: application/json

{
  "newPassword": "MAT_KHAU_MOI_MINH_HOA"
}
~~~

Body không cần một accountId để quyết định tài khoản được đổi mật khẩu. Máy chủ lấy đích thao tác từ credential đã được xác thực và giao dịch gắn với nó.

Bearer có đặc điểm là người giữ token có thể sử dụng quyền liên quan, nên token phải được bảo vệ khi truyền và lưu. RFC 6750 mô tả cơ chế này và cách dùng Authorization header trong bối cảnh OAuth. Ví dụ ở đây minh họa cách mang credential, không khẳng định toàn bộ luồng khôi phục là một giao thức OAuth. Xem [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html).

Không đưa credential của phiên vào query để tiện gọi API. Không ghi Authorization vào access log hoặc công cụ theo dõi lỗi. HTTPS phải được dùng xuyên suốt các điểm xử lý credential hợp lệ.

### Không nhận credential mơ hồ

Với mỗi endpoint, xác định chính xác loại credential được chấp nhận. Nếu dùng nhiều cơ chế cho các client khác nhau, cần quy tắc giải quyết rõ khi một yêu cầu mang cả cookie và Authorization; có thể từ chối tổ hợp không được hỗ trợ.

Không thử lần lượt “token khôi phục không hợp lệ thì dùng cookie đăng nhập”, hoặc ngược lại, nếu điều đó làm người gọi được chuyển sang quyền khác ngoài hợp đồng của endpoint.

CORS không chứng minh danh tính người gọi. API key nhúng trong ứng dụng web hoặc mobile cũng không chứng minh người sử dụng là chủ tài khoản đang khôi phục.

## 6. Xác thực credential rồi mới cấp quyền cho hành động

Một trình xử lý endpoint có thể được mô tả bằng mã giả:

~~~text
handlePasswordReset(request):
    credential = extractOnlySupportedRecoveryCredential(request)
    principal = recoveryAuthenticator.authenticate(credential)

    require principal.type == RECOVERY_SESSION
    require principal.permission includes recovery:password:commit

    transaction = loadTransaction(principal.transactionId)

    require transaction.accountId == principal.accountId
    require transaction.purpose == PASSWORD_RESET
    require transaction.state == AUTHORIZED
    require principal and transaction are not expired or revoked
    require current recovery policy still permits the operation

    validateNewPassword(request.body.newPassword)

    commitAtomically:
        require transaction and credential are still usable
        updatePassword(transaction.accountId)
        consumeRecoveryCredential()
        completeTransaction()
        applyRequiredSessionRevocation()
        recordNotificationOutboxEvent()

    dispatchRecordedNotificationAsynchronously()
    return minimalSuccessResponse()
~~~

Đây là mã giả về thứ tự kiểm soát, không phải một implementation hoàn chỉnh.

Một bước kiểm tra ở đầu request có thể bị lỗi thời trước khi ghi dữ liệu. Vì vậy, khi hoàn tất phải kiểm tra lại điều kiện dùng một lần trong cùng cơ chế giao dịch hoặc điều phối nguyên tử phù hợp.

### Không tin các cờ xác minh do client gửi

Các field sau không tạo ra quyền, ngay cả khi client gửi đúng kiểu:

~~~json
{
  "verified": true,
  "mfaPassed": true,
  "accountId": "TAI_KHOAN_DICH",
  "allowedAction": "REMOVE_ALL_AUTHENTICATORS"
}
~~~

Máy chủ có thể từ chối các field ngoài hợp đồng. Nó không được lấy chúng làm nguồn chuẩn cho trạng thái xác minh, tài khoản đích hoặc quyền được cấp.

### Không suy rộng bằng chứng sang thao tác khác

Một token đã đủ để đặt mật khẩu mới chưa chắc đủ để:

- Xóa yếu tố MFA đang tồn tại.
- Đăng ký một passkey thay thế.
- Đổi email hoặc số điện thoại khôi phục.
- Tắt cảnh báo bảo mật.
- Cấp phiên đăng nhập có quyền thực hiện mọi hành động.

Nếu muốn cho phép những thao tác này, chính sách phải xác định thêm bằng chứng và điều kiện cần thiết. “Đã qua API khôi phục” không phải một mức bảo đảm đủ rõ để làm căn cứ phân quyền.

## 7. Token opaque và JWT cần những kiểm soát khác nhau

### Credential opaque

Một token opaque là chuỗi ngẫu nhiên không mang ý nghĩa nghiệp vụ mà client cần giải mã. Máy chủ tra cứu bản ghi để lấy tài khoản, giao dịch, quyền và trạng thái.

Cách này hỗ trợ thu hồi và dùng một lần tương đối trực tiếp, nhưng cần kho trạng thái khả dụng và cơ chế xử lý đồng thời đúng. Với token ngẫu nhiên có entropy cao, có thể lưu giá trị băm phù hợp để hạn chế lộ token gốc từ cơ sở dữ liệu. Mã OTP ngắn có đặc tính đoán khác; không được suy ra rằng băm là đủ thay cho giới hạn số lần thử.

Kho trạng thái không khả dụng thì endpoint nhạy cảm không được tự chuyển sang chấp nhận token mà chưa kiểm tra. Hệ thống cần trả lỗi có kiểm soát và giữ nguyên tài khoản.

### Credential JWT

Nếu chọn JWT, chữ ký đúng chỉ chứng minh token phù hợp với quy tắc mật mã đã kiểm tra. Máy chủ còn phải áp dụng đúng thuật toán cho phép, issuer, audience, thời hạn, loại token và các ràng buộc giao dịch liên quan.

Cần có quy tắc xác thực tách biệt giữa token đăng nhập và token khôi phục để tránh dùng một loại token ở nơi nhận loại khác. RFC 8725 bàn về audience, explicit typing và các quy tắc xác thực loại trừ nhau cho những loại JWT khác nhau. Xem [RFC 8725: JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.12).

Exp còn hạn không có nghĩa token chưa được dùng. Jti không tự tạo cơ chế chống phát lại nếu máy chủ không theo dõi việc tiêu thụ hoặc không có một cơ chế trạng thái tương đương.

Không dùng trường claim do client tự gửi trong body để ghi đè claim đã xác thực, và không chọn khóa hay thuật toán chỉ theo dữ liệu không tin cậy trong token.

## 8. Phản hồi lỗi và khả năng gọi lại

API cần cung cấp đủ thông tin để client xử lý, đồng thời tránh trở thành kênh dò tài khoản hoặc bằng chứng.

| Tình huống | Hành vi phản hồi minh họa |
| --- | --- |
| Khởi tạo yêu cầu với định danh có hoặc không có tài khoản | Phản hồi công khai nhất quán |
| Thiếu hoặc credential khôi phục không hợp lệ | Lỗi xác thực chung, không trả token hay chi tiết nội bộ |
| Credential hợp lệ nhưng thiếu quyền cho thao tác | Từ chối cấp quyền; không tự nâng scope |
| Mật khẩu mới không đáp ứng chính sách | Thông báo phù hợp sau khi người gọi đã qua kiểm soát cần thiết |
| Vượt giới hạn thử bằng chứng | Dừng thử tiếp theo chính sách và trả phản hồi hạn chế lạm dụng |
| Giao dịch đã hoàn tất hoặc bị thu hồi | Không cho thực hiện thay đổi lần hai |
| Dịch vụ kiểm tra trạng thái lỗi | Không thay đổi tài khoản; trả lỗi tạm thời có kiểm soát |

Với endpoint bảo vệ bằng HTTP authentication, các mã như 401 cho credential thiếu hoặc không hợp lệ và 403 cho trường hợp không được cấp quyền cần được dùng nhất quán theo hợp đồng. Đừng áp dụng máy móc một mã lỗi vào mọi bước của hành trình, nhất là endpoint công khai cần chống dò tài khoản.

Không đưa lý do chi tiết như “tài khoản tồn tại nhưng chưa bật MFA” vào phản hồi cho người chưa có quyền biết trạng thái đó. Bản ghi vận hành nội bộ có thể chứa phân loại lỗi và ID tương quan không phải bí mật; không cần chứa token, mật khẩu hoặc mã dự phòng.

### Mất phản hồi sau khi thay đổi thành công

Client có thể gửi yêu cầu đổi mật khẩu, máy chủ đã hoàn tất nhưng kết nối bị ngắt trước khi nhận phản hồi. Nếu client gửi lại cùng credential, cơ chế dùng một lần phải tiếp tục có hiệu lực.

Có thể thiết kế cơ chế idempotency hoặc một quyền đọc kết quả tối thiểu riêng. Các cơ chế này vẫn phải ràng buộc với giao dịch và không cho thực hiện thay đổi lần hai. Không kích hoạt lại credential đã tiêu thụ để làm cho thao tác gọi lại “dễ thành công”.

Nếu không có kênh xác nhận an toàn, giao diện có thể hướng dẫn người dùng thử đăng nhập thông thường hoặc bắt đầu lại theo luồng được cho phép.

## 9. Xác thực dịch vụ không thay thế bằng chứng người dùng

Trong kiến trúc nhiều dịch vụ, gateway hoặc backend ứng dụng có thể gọi dịch vụ khôi phục bằng mTLS hay credential của workload. Điều đó trả lời câu hỏi dịch vụ nào đang gọi, không tự trả lời người dùng nào đã chứng minh quyền khôi phục.

Dịch vụ thực hiện thay đổi cần nhận được ngữ cảnh giao dịch đã được bảo vệ tính toàn vẹn và có thể kiểm chứng nguồn. Không tin một header như X-Account-Id hoặc X-Recovery-Verified nếu bất kỳ client bên ngoài nào cũng có thể gửi nó đến đường vào.

Credential workload nên có phạm vi chức năng phù hợp. Tránh thiết kế một API key mà chỉ cần biết nó và accountId là có thể đổi mật khẩu cho mọi tài khoản, rồi dựa hoàn toàn vào giao diện để giữ an toàn.

Nếu có nhân viên hỗ trợ tham gia, danh tính nhân viên, quyền thực hiện nghiệp vụ và bằng chứng của người yêu cầu vẫn là các yếu tố riêng. Một nhân viên đã đăng nhập không làm mọi yêu cầu khôi phục mà họ nhận được trở thành hợp lệ.

Sau khi khôi phục thành công, hệ thống cần chấm dứt quyền khôi phục đã dùng, áp dụng chính sách đối với các phiên hoặc yếu tố có nguy cơ và thông báo qua kênh phù hợp. Không tự cấp một phiên đăng nhập đầy đủ chỉ để rút ngắn trải nghiệm.

Thiết kế đúng cho API khôi phục cho phép người dùng bắt đầu khi chưa đăng nhập, nhưng chỉ cho phép thay đổi tài khoản sau khi máy chủ đã xác minh đủ bằng chứng và cấp đúng quyền cho đúng giao dịch.

