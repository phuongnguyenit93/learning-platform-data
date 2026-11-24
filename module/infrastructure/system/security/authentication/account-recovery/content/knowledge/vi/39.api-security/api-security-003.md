# Recovery API authorization

## 1. Khôi phục tài khoản vẫn cần phân quyền

Người dùng tìm đến recovery thường không còn đăng nhập được bằng cách thông thường. Vì vậy, một số API phải nhận request từ người chưa có phiên đăng nhập đầy đủ. Điều này không có nghĩa toàn bộ API recovery được phép bỏ kiểm tra quyền.

Cần phân biệt hai câu hỏi:

- **Authentication:** request đang chứng minh điều gì, bằng credential nào?
- **Authorization:** với bằng chứng đó, request được làm thao tác nào trên tài khoản nào, ở bước nào?

Biết email của một tài khoản chỉ đủ để yêu cầu bắt đầu luồng trong một thiết kế phù hợp. Sở hữu token đặt lại mật khẩu có thể cho phép một thao tác hẹp sau khi hệ thống kiểm tra hợp lệ. Nó không mặc nhiên cấp quyền xóa MFA, đăng ký passkey mới, thay email hoặc gọi API quản trị.

**Recovery API authorization** là việc ràng buộc quyền tiếp tục với đúng tài khoản, tenant, mục đích, bằng chứng và trạng thái hiện hành của lần khôi phục.

Các endpoint và giá trị trong bài là mô hình minh họa; tên route không phải một tiêu chuẩn bắt buộc.

## 2. Mô hình quyền theo từng giai đoạn

Thiết kế nên dùng các ngữ cảnh có quyền khác nhau thay vì một cờ chung như `isRecovery=true`.

| Ngữ cảnh request | Có thể được phép | Không tự có quyền |
| --- | --- | --- |
| Chưa có bằng chứng recovery | Gửi yêu cầu bắt đầu theo chính sách công khai | Đọc thông tin tài khoản, đổi credential |
| Ngữ cảnh challenge giới hạn | Nộp bằng chứng cho đúng challenge, yêu cầu gửi lại theo giới hạn | Tự đánh dấu đã xác minh, đổi đích nhận mã |
| Quyền recovery đã đạt yêu cầu | Thực hiện đúng hành động được cấp | Gọi mọi API tài khoản |
| Quyền đã dùng, hết hạn hoặc bị thu hồi | Nhận kết quả không còn tiếp tục được | Phát sinh thay đổi mới |
| Phiên đăng nhập thông thường | Các hành động được chính sách phiên cho phép | Tự vượt yêu cầu xác minh cho thao tác nhạy cảm |
| Nhân sự hỗ trợ đã được cấp quyền | Các hành động hỗ trợ được phân công rõ | Tùy ý bỏ qua bước xác minh hoặc thao tác ngoài tenant |

Ngữ cảnh challenge trước xác minh chưa chứng minh danh tính chủ tài khoản. Nó chỉ có thể cấp những thao tác cần thiết để hoàn thành challenge. Nếu có credential bí mật để bảo vệ ngữ cảnh này, credential đó phải được xử lý như bí mật; không đánh đồng với một ID dùng để tra cứu.

Nguyên tắc chung là quyền tối thiểu, từ chối mặc định và kiểm tra quyền trên từng request, như [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) mô tả. Giao diện ẩn nút hoặc buộc người dùng đi qua một màn hình không thay thế kiểm tra tại API.

## 3. API bắt đầu công khai không cấp quyền thay đổi tài khoản

Một request khởi tạo có thể trông như sau:

```http
POST /api/recovery/requests HTTP/1.1
Host: accounts.example
Content-Type: application/json

{
  "identifier": "learner@example.test",
  "purpose": "password_reset"
}
```

Response có thể dùng thông điệp trung tính:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Neu thong tin phu hop, huong dan khoi phuc se duoc gui."
}
```

Trong mô hình này, việc nhận `202` không chứng minh tài khoản tồn tại, challenge đã được giải hay người gửi có quyền đổi mật khẩu. Server quyết định những mục đích nào được hỗ trợ và điều kiện nào áp dụng cho tài khoản thực tế.

Không trả token có khả năng đổi credential trực tiếp cho request công khai chỉ vì request đã cung cấp đúng email. Bằng chứng cần được gửi hoặc xác minh qua kênh đã được chính sách chấp nhận.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) hướng dẫn tránh khác biệt phản hồi làm lộ tài khoản và dùng token có thời hạn, dùng một lần. Các biện pháp này hỗ trợ luồng recovery; việc được phép thực hiện hành động cuối cùng vẫn cần được xác định riêng.

Kênh nhận mã phải lấy từ trạng thái tin cậy của tài khoản hoặc quy trình xác minh được phê duyệt. Tham số `sendTo` do client gửi không được tự thay kênh recovery đã đăng ký.

## 4. Quyết định quyền cần đủ các ràng buộc

Có thể diễn đạt quyết định cho một thao tác thay đổi credential như sau:

```text
ALLOW only if:
    credential is valid for the recovery service
    credential maps to this recovery attempt
    attempt belongs to the target account and tenant
    requested action matches the granted purpose
    required evidence is satisfied and still fresh
    workflow state permits this transition
    grant is not expired, consumed, cancelled or revoked
    current account policy still permits the operation
```

Một bản ghi quyền phía server có thể mang các thuộc tính:

```text
RecoveryGrant
  grantId
  attemptId
  accountId
  tenantId
  purpose
  allowedAction
  evidenceReferences
  verifiedAt
  expiresAt
  state
  policyVersion
```

Đây là mô hình dữ liệu minh họa, không phải danh sách claim chuẩn cho mọi hệ thống. Ý nghĩa quan trọng là server phải có nguồn tin cậy cho từng điều kiện.

`accountId` trong request không được ghi đè tài khoản gắn với grant. `tenantId` cũng không trở thành đáng tin chỉ vì client đặt nó trong header. Có thể dùng thông tin từ client để chọn một phạm vi tra cứu ban đầu, nhưng kết quả cuối phải được đối chiếu với ngữ cảnh và bản ghi đã được xác thực.

Một grant đúng tài khoản nhưng sai mục đích vẫn phải bị từ chối. Một grant đúng mục đích nhưng đã bị hủy cũng không còn quyền, dù thời hạn ban đầu chưa kết thúc.

## 5. Ba lớp phân quyền dễ bị bỏ sót

### 5.1. Quyền trên đối tượng

Ví dụ một API nhận `attemptId`:

```text
POST /api/recovery/attempts/{attemptId}/complete
```

Nếu request có credential của lần khôi phục A nhưng thay đường dẫn sang lần B, backend phải từ chối. Việc `attemptId` là UUID khó đoán không thay thế kiểm tra ràng buộc.

[OWASP API1: Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) mô tả rủi ro truy cập đối tượng ngoài quyền thông qua ID do client điều khiển. Trong recovery, đối tượng cần bảo vệ gồm account, attempt, challenge, thiết bị và phương thức xác thực.

Truy vấn và kiểm tra quyền phải thống nhất phạm vi tenant. Tránh tìm một attempt theo ID toàn cục rồi vô tình dùng account hoặc policy của tenant do request chọn.

### 5.2. Quyền gọi chức năng

Credential chỉ cho phép `password_reset` không được gọi `mfa_reset`. Thêm đường dẫn `/admin/`, đổi HTTP method hoặc gọi phiên bản API cũ cũng không được mở rộng quyền.

Đây là dạng vấn đề liên quan đến [OWASP API5: Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/). Quyền phải gắn với hành động nghiệp vụ; tên endpoint hoặc việc endpoint không được giao diện sử dụng không tạo ra ranh giới an toàn.

API hỗ trợ nội bộ cần quyền riêng, phạm vi tenant và điều kiện phê duyệt tương ứng. Không mở một endpoint “force complete recovery” chỉ dựa vào việc request đến từ mạng nội bộ.

### 5.3. Quyền trên thuộc tính đọc và ghi

Không bind toàn bộ JSON của client vào entity tài khoản hoặc bản ghi recovery.

Ví dụ payload cần bị từ chối theo contract chặt của endpoint đổi mật khẩu:

```json
{
  "newPassword": "DEMO_NOT_FOR_USE",
  "accountId": "another-account",
  "mfaEnabled": false,
  "role": "ADMIN",
  "verified": true
}
```

Client không được tự quyết định các thuộc tính `verified`, `role` hoặc trạng thái MFA thông qua một thao tác chỉ cho đổi mật khẩu. Dùng request DTO chỉ chứa trường được phép; trong thiết kế này, trường ngoài schema bị từ chối.

Response cũng cần chọn trường được phép đọc. Một API xem tiến độ recovery không nên serialize nguyên entity chứa hash token, dữ liệu xác minh, ghi chú hỗ trợ hoặc danh sách yếu tố xác thực.

Phân biệt quyền đọc và quyền sửa từng thuộc tính phù hợp với [OWASP API3: Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

## 6. Quyền phụ thuộc trạng thái và độ mới của bằng chứng

Một luồng minh họa:

```mermaid
stateDiagram-v2
    [*] --> CHALLENGE_PENDING
    CHALLENGE_PENDING --> EVIDENCE_ACCEPTED: Bằng chứng đạt yêu cầu
    EVIDENCE_ACCEPTED --> ACTION_AUTHORIZED: Chính sách hiện tại cho phép
    ACTION_AUTHORIZED --> COMPLETED: Thực hiện và tiêu thụ quyền
    CHALLENGE_PENDING --> CLOSED: Hết hạn hoặc hủy
    EVIDENCE_ACCEPTED --> CLOSED: Hết hạn hoặc thu hồi
    ACTION_AUTHORIZED --> CLOSED: Hết hạn hoặc thu hồi
    COMPLETED --> [*]
    CLOSED --> [*]
```

API hoàn tất không được chấp nhận chỉ vì client gửi `step=complete` hoặc vì trước đó đã có một request xác minh thành công. Server cần đọc trạng thái hiện hành của đúng attempt và bằng chứng gắn với nó.

Bằng chứng cũng có phạm vi. Xác minh thành công một challenge email của attempt A không cho phép xác minh attempt B. Một phê duyệt cũ có thể không đủ nếu tài khoản vừa bị đánh dấu có sự cố hoặc policy cần mức đảm bảo cao hơn.

Đối với MFA và passkey, quyền mở một bước recovery phải tách khỏi quyền thay phương thức xác thực. [OWASP về khôi phục MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) nhấn mạnh recovery không được tạo đường vòng chiếm đoạt tài khoản và lựa chọn phương pháp phụ thuộc bối cảnh.

Vì vậy, không dùng một quy tắc toàn cục “xác minh email xong thì được xóa mọi yếu tố”. Chính sách phải nêu bằng chứng nào đủ cho từng hành động. Nếu người dùng mất phương thức hiện tại, hệ thống áp dụng đường recovery thay thế đã thiết kế; không âm thầm bỏ yêu cầu bảo đảm.

## 7. Credential recovery phải có phạm vi riêng

Có thể dùng token opaque hoặc token được bảo vệ toàn vẹn như JWT. Cách đóng gói không tự tạo ra mô hình phân quyền đúng.

Với opaque token, backend tra cứu bản ghi quyền tương ứng và kiểm tra trạng thái. Với JWT, ngoài xác minh chữ ký theo cấu hình tin cậy, cần kiểm tra issuer, audience, thời hạn và profile áp dụng. Xem [OWASP REST Security về JWT](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#jwt).

Các ràng buộc riêng của hệ thống như purpose, tenant và attempt vẫn phải được thực thi. Chữ ký hợp lệ không có nghĩa token dùng được cho mọi endpoint.

Một số nguyên tắc trong thiết kế này:

- Credential recovery có audience và quyền được phân biệt với phiên truy cập ứng dụng.
- Token đăng nhập không được tự chuyển thành grant recovery chỉ vì cùng mô tả một tài khoản.
- Token của môi trường hoặc dịch vụ khác không được chấp nhận nhờ dùng chung bộ xác minh quá rộng.
- Việc hết hạn, tiêu thụ hoặc thu hồi được kiểm tra từ nguồn trạng thái phù hợp.
- Sau khi hoàn tất, không tiếp tục dùng credential recovery để truy cập hồ sơ.

Đặc biệt, JWT còn hạn không tự phản ánh rằng grant đã bị thu hồi hoặc đã dùng. Nếu hành động phải dùng một lần, hệ thống vẫn cần cơ chế theo dõi và tiêu thụ quyền tương ứng.

Một request thực hiện thao tác hẹp có thể là:

```http
POST /api/recovery/password-reset HTTP/1.1
Host: accounts.example
Authorization: Bearer DEMO_RECOVERY_GRANT_NOT_VALID
Content-Type: application/json

{
  "newPassword": "DEMO_NOT_FOR_USE"
}
```

Backend lấy tài khoản đích từ grant đã được xác thực. Payload không cần mang `accountId` để chọn tài khoản tùy ý.

## 8. Kiểm tra quyền và thay đổi phải tránh race condition

Mẫu xử lý sau có khoảng trống nguy hiểm:

```text
read grant as unused
authorize request
update account
mark grant consumed
```

Nếu hai request cùng đọc `unused`, cả hai có thể đi tiếp trước khi quyền bị tiêu thụ. Kiểm tra quyền một lần ở middleware chưa đủ để giải quyết cạnh tranh tại thời điểm ghi.

Pseudocode cho trường hợp dữ liệu nằm trong cùng ranh giới transaction:

```text
validate request schema and credential format
validate candidate password against password policy
prepare password hash without logging raw password

begin transaction
    lock recovery attempt and grant in a consistent order
    load target account in the same tenant scope

    authorize PASSWORD_RESET against current state and current time
    require grant is active and not consumed
    require evidence and account policy still permit this action

    update password hash
    mark grant consumed
    mark attempt completed
    record audit event and required follow-up work
commit transaction

return a minimal completion response
```

Các kiểm tra có thể làm trước transaction để từ chối sớm, nhưng điều kiện quyết định quyền một lần cần được xác nhận lại tại điểm ghi. Có thể dùng khóa hoặc cập nhật có điều kiện với phiên bản; yêu cầu là không có hai lần thực thi thành công ngoài ý định.

Nếu thay đổi trải trên nhiều dịch vụ, không giả định một transaction cơ sở dữ liệu cục bộ bao phủ mọi hệ thống. Cần thiết kế trạng thái, sự kiện và xử lý lặp sao cho lệnh bị gửi lại không tạo thêm quyền hoặc hoàn tất nhiều lần.

`Idempotency-Key` chỉ hỗ trợ xử lý request lặp theo contract được thiết kế. Nó không phải credential. Đọc lại kết quả cũ cũng phải có quyền phù hợp và không làm hành động đã tiêu thụ được thực thi lần hai.

## 9. Thực thi ở backend, kể cả khi có gateway

Một cấu trúc trách nhiệm có thể là:

| Thành phần | Trách nhiệm |
| --- | --- |
| Gateway hoặc lớp tiếp nhận | TLS, giới hạn request, loại header giả mạo, xác thực credential theo kiến trúc |
| Lớp API | Contract request, loại credential và hành động mà endpoint chấp nhận |
| Lớp nghiệp vụ recovery | Ràng buộc account/tenant/attempt/purpose, bằng chứng và chuyển trạng thái |
| Lớp dữ liệu | Truy vấn đúng phạm vi, bảo đảm cạnh tranh và tiêu thụ quyền |
| Audit và điều phối sau thao tác | Ghi quyết định, thông báo và xử lý phiên theo policy |

Nếu hệ thống truyền ngữ cảnh qua header nội bộ, phải có ranh giới tin cậy rõ ràng. Header `X-Recovery-Verified: true` từ Internet không được dùng làm bằng chứng. Gateway cần loại bỏ giá trị do client tự đặt, và backend chỉ chấp nhận ngữ cảnh từ đường truyền hoặc cơ chế đã xác thực.

Không chỉ bảo vệ controller web rồi để mobile API, GraphQL mutation, endpoint cũ hoặc background job gọi cùng nghiệp vụ mà thiếu kiểm tra. Hành động nhạy cảm phải đi qua cùng chính sách nghiệp vụ phù hợp.

Rate limit, CAPTCHA, CORS và CSRF giải quyết các vấn đề khác nhau. Chúng không thay ràng buộc quyền trên tài khoản và mục đích. Với phiên recovery dùng cookie tự gửi, cần phòng vệ CSRF phù hợp; với bearer token do client gắn, vẫn cần bảo vệ token và áp dụng đầy đủ authorization.

## 10. Trả kết quả và ghi dấu vết có kiểm soát

Ở bước công khai, hạn chế khác biệt làm lộ sự tồn tại của tài khoản. Sau khi đã có quyền xem một attempt, API chỉ nên trả dữ liệu cần thiết cho bước hiện tại.

Không dùng response để cung cấp cho người chưa có quyền một danh sách chi tiết về email, số điện thoại, passkey hoặc lý do tài khoản bị đánh dấu rủi ro. Các mã lỗi nội bộ phục vụ vận hành không nhất thiết được trả nguyên văn cho client.

Đồng thời, hệ thống cần hiểu vì sao một quyết định bị từ chối. Audit có thể ghi:

```json
{
  "event": "recovery_authorization_decision",
  "requestId": "demo-request-38",
  "attemptId": "demo-attempt-72",
  "action": "PASSWORD_RESET",
  "decision": "DENY",
  "reasonCode": "PURPOSE_MISMATCH"
}
```

Ví dụ trên không chứa credential có giá trị. Trong triển khai thật, định danh và dữ liệu audit cũng phải được giới hạn truy cập, giữ đúng phạm vi tenant và theo chính sách lưu trữ.

Không ghi mật khẩu mới, OTP, token hoặc cookie recovery vào log. Việc có audit đầy đủ không cho phép thu thập toàn bộ request body nhạy cảm.

Khi recovery hoàn tất, đóng quyền recovery và thực hiện chính sách phiên đăng nhập, thông báo, hoặc xác minh tiếp theo tương ứng. Không tự nâng một grant hẹp thành phiên đăng nhập đầy đủ chỉ để tiện điều hướng.

## 11. Các nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| API recovery nhận người chưa đăng nhập nên mọi endpoint đều công khai | Chỉ một số thao tác được công khai có chủ đích; thay đổi credential cần quyền tương ứng |
| UUID khó đoán là đủ bảo vệ attempt | Vẫn cần kiểm tra quan hệ với credential, tài khoản và tenant |
| Token có chữ ký hợp lệ thì được làm mọi bước | Phải đúng audience, purpose, trạng thái và hành động |
| Giao diện đã xác minh nên API hoàn tất không cần đọc lại trạng thái | Client có thể gọi trực tiếp, bỏ bước hoặc gửi lại request |
| Có quyền đổi mật khẩu thì có quyền gỡ MFA | Mỗi hành động có yêu cầu và grant riêng |
| Header nội bộ trông đáng tin là đủ | Nguồn của ngữ cảnh phải được xác thực và chống giả mạo |
| Một lần authorize ở đầu request giải quyết dùng token một lần | Cần bảo đảm nguyên tử tại thời điểm thay đổi và tiêu thụ quyền |

Một quyết định authorization tốt có thể giải thích được: credential nào cho phép hành động gì, trên tài khoản và tenant nào, bằng chứng nào hỗ trợ, trạng thái nào cho phép tiếp tục và quyền đó kết thúc khi nào. API recovery cần thực thi những ràng buộc này ở server trong suốt luồng khôi phục.
