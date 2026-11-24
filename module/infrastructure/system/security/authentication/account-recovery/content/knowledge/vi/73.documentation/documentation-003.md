# Recovery API documentation

## 1. Tài liệu API phải mô tả quyền, không chỉ request và response

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, API khôi phục có thể thay mật khẩu, hỗ trợ thay MFA, đăng ký lại passkey hoặc xử lý việc mất thiết bị xác thực. Một tài liệu chỉ ghi URL, JSON mẫu và HTTP 200 chưa đủ để client sử dụng những quyền đó đúng cách.

Client cần biết caller đang ở trạng thái nào, bằng chứng nào được chấp nhận, request có tác động gì, khi nào quyền bị tiêu thụ và phải làm gì khi response bị mất. Nhân viên hỗ trợ cần biết phần nào được công khai, phần nào là thông tin vận hành nội bộ và thao tác nào cần thẩm quyền riêng.

Một lỗi tài liệu có thể trở thành lỗi bảo mật. Ví dụ mô tả recovery grant như access token bình thường có thể khiến client dùng nó để gọi API nhạy cảm; hướng dẫn retry mọi POST có thể làm gửi nhiều SMS hoặc tạo nhiều operation đổi factor.

Bài học xây dựng cách viết và kiểm chứng hợp đồng API recovery. Mọi endpoint, schema, class và policy trong ví dụ đều giả định phục vụ học tập, không khẳng định dự án đã triển khai chúng.

### 1.1. Ba lớp tài liệu cần liên kết

| Lớp | Mục đích | Nội dung chính |
| --- | --- | --- |
| API reference | Cho máy và developer tích hợp | Method, path, schema, security, status và header |
| Workflow guide | Giải thích thứ tự và quyền | State, proof, grant, retry, hết hạn và tác động session |
| Operations guide | Hỗ trợ vận hành và ứng phó | Dependency failure, reconcile, escalation và giới hạn thẩm quyền |

Một OpenAPI hợp lệ có thể vẫn thiếu workflow an toàn. Một runbook tốt cũng không thay thế schema mà SDK cần để tạo đúng request.

## 2. Xác định đối tượng đọc và phạm vi công khai

Một hệ thống có thể có API khởi tạo public, API dùng proof hoặc recovery grant, API quản lý factor trong session bình thường và API support/admin. Những mặt này không có cùng mô hình quyền.

| Caller | Điều có thể đang sở hữu | Điều cần tài liệu nói rõ |
| --- | --- | --- |
| Người chưa đăng nhập | Định danh do họ nhập | Khởi tạo không xác nhận account tồn tại và chưa cấp quyền đổi credential |
| Người có proof recovery | Token hoặc bằng chứng đúng loại | Binding, expiry, số lần dùng và phạm vi có thể đổi |
| Người có recovery grant | Quyền hạn chế sau xác minh | Purpose, subject, tenant, operation được phép |
| Người có session đăng nhập | Session đang hoạt động | Có cần step-up và factor còn đáng tin không |
| Support operator | Role/scoped permission | Không suy từ quyền xem ticket thành quyền reset factor |
| Provider webhook | Chữ ký/transport identity tương ứng | Callback không tự chứng minh caller là chủ account |

Một tài liệu nội bộ có thể mô tả quyết định rủi ro hoặc nguyên nhân chi tiết. Những thông tin đó không được tự xuất hiện trong response public vì chúng có trong API reference nội bộ.

### 2.1. Public không đồng nghĩa không có kiểm soát

Endpoint khởi tạo có thể không yêu cầu Authorization header, nhưng vẫn cần validation, chống lạm dụng, giới hạn dữ liệu và quy tắc tenant.

Endpoint trao đổi proof có thể public ở lớp HTTP authentication nhưng chỉ thực hiện khi proof hợp lệ. Tài liệu phải mô tả điều kiện này, không ghi một câu “no authentication required” rồi để người đọc hiểu không cần bằng chứng.

Tenant cần đến từ ngữ cảnh định tuyến hoặc xác thực đáng tin đã định nghĩa. Nếu có field tenant trong request, tài liệu phải giải thích cách server kiểm tra nó, không cho client tùy chọn tenant để vượt scope.

## 3. Viết workflow và state trước khi viết từng operation

Một workflow mất mật khẩu minh họa:

```text
Khởi tạo yêu cầu
  -> Nếu điều kiện nội bộ phù hợp, tạo và chuyển proof qua kênh đã đăng ký
  -> Caller trình proof
  -> Server xác minh và cấp grant hạn chế theo policy
  -> Caller thực hiện operation đúng purpose
  -> Server commit thay đổi và xử lý quyền/session theo contract
  -> Grant/proof bị tiêu thụ hoặc vô hiệu hóa tương ứng
```

Đối với mất MFA/passkey, bước proof và operation cuối có thể khác. Đừng lấy password reset làm mẫu rồi chỉ đổi tên field `newPassword` thành `newFactor` cho mọi cơ chế.

### 3.1. Phân biệt resource và capability

| Đối tượng | Vai trò | Có mặc định cấp quyền không? |
| --- | --- | --- |
| Recovery request reference | Định danh một resource hoặc hồ sơ | Không; cần kiểm tra quyền khi đọc/sửa |
| Correlation reference | Giúp tra cứu trong vận hành | Không; không được trở thành link xem dữ liệu bí mật |
| Proof token/code | Bằng chứng theo contract cụ thể | Có thể là dữ liệu nhạy cảm cấp quyền trong đúng phạm vi |
| Recovery grant | Authorization hạn chế sau xác minh | Chỉ những action, subject và purpose đã ràng buộc |
| Enrollment ticket | Quyền bắt đầu/hoàn tất đăng ký factor | Không mặc định là session đầy đủ |
| Operation receipt | Theo dõi outcome của một operation | Quyền đọc receipt phải được định nghĩa riêng |
| Session/access token | Quyền truy cập theo hệ thống xác thực | Không đồng nghĩa được bỏ qua step-up cho mọi thay đổi |

Một ID ngẫu nhiên khó đoán không tự thay thế authorization. Nếu một receipt cũng mang quyền đọc trạng thái, phải mô tả nó như capability và bảo vệ tương ứng, không gọi nó là correlation ID vô hại.

### 3.2. Trạng thái quan sát được phải có giới hạn

Không công khai một status endpoint nhận email rồi trả “account tồn tại, đang chờ MFA” cho caller chưa được phép. Một response khởi tạo chung sẽ mất tác dụng chống enumeration nếu polling tiết lộ ngay thông tin thật.

Nếu cần polling, tài liệu phải nêu quyền đọc, phạm vi dữ liệu, cách bind receipt và hành vi quan sát cho các trường hợp public cần bảo vệ. Không tự thêm endpoint poll chỉ để hoàn thiện sơ đồ bất đồng bộ.

## 4. Mẫu contract cho một operation

Mỗi operation nên có tối thiểu các phần dưới đây.

| Phần | Câu hỏi cần trả lời |
| --- | --- |
| Intent | Caller muốn làm gì, không phải chỉ tên method |
| Preconditions | Resource, proof, grant và policy nào phải hợp lệ |
| Caller identity | Anonymous, bearer grant, cookie session hay service identity |
| Authorization | Scope/purpose, tenant, subject, generation và action |
| Input | Kiểu, giới hạn, trường bắt buộc, dữ liệu nhạy cảm |
| State transition | Trạng thái trước/sau và những trạng thái bị từ chối |
| Side effects | Credential, session, outbox, audit và thông báo |
| Success | Milestone nào đã thực sự hoàn thành |
| Failure | Error contract và thông tin caller được biết |
| Retry | Có an toàn không, dùng identity nào, khi nào phải reconcile |
| Concurrency | Nhiều request, resend, cancel hoặc recovery song song |
| Data handling | Cache, log, retention và redaction cần thiết |
| Examples | Dữ liệu giả, đúng schema và đúng mức quyền |
| Evidence | Test hoặc nguồn thực thi dùng để đối chiếu |

Không cần lặp toàn bộ văn bản ở mọi operation. Có thể dẫn tới contract chung, nhưng các ngoại lệ và điều kiện đặc thù cần nằm gần chỗ developer sẽ đọc.

### 4.1. Mẫu prose cho operation hoàn tất

```text
Intent:
  Thay mật khẩu bằng một recovery grant có purpose password_reset.

Preconditions:
  Grant hợp lệ, đúng tenant/subject, chưa mất quyền thực thi;
  recovery và policy cho phép finalization tại điểm commit.

Success:
  Thay đổi đã commit và các điều kiện bắt buộc của completion đã đạt.
  Response không cấp session đăng nhập đầy đủ trong contract này.

Side effects:
  Tiêu thụ quyền theo policy, xử lý session trong scope,
  ghi audit và tạo ý định thông báo theo thiết kế.

Ambiguous response:
  Không tự đổi operation identity rồi thực hiện lại.
  Dùng quy trình idempotency/reconcile được mô tả cho operation.
```

Đoạn trên là ví dụ hợp đồng, không phải bằng chứng server thật đã có các kiểm soát đó.

## 5. Khởi tạo public và chống enumeration

Một request minh họa:

```http
POST /v1/account-recovery/requests HTTP/1.1
Host: recovery.example.invalid
Content-Type: application/json
Accept: application/json

{
  "identifier": "learner@example.invalid",
  "purpose": "password_reset"
}
```

Một response chung có thể là:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Nếu thông tin phù hợp, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký."
}
```

OWASP khuyến nghị giữ thông điệp quên mật khẩu nhất quán giữa account tồn tại và không tồn tại, đồng thời áp dụng bảo vệ trước yêu cầu tự động quá mức. Tài liệu API cần mô tả mục tiêu quan sát này, không chỉ ví dụ cho account thật. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

### 5.1. Accepted không phải delivered hoặc recovered

HTTP 202 thể hiện request được chấp nhận để xử lý, chưa khẳng định xử lý đã hoàn tất. Không diễn giải response trên thành “SMS đã đến” hoặc “tài khoản đã được xác minh”. [RFC 9110 §15.3.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3).

Trong contract ví dụ, endpoint không trả account ID, số factor hay recipient đầy đủ. Nó cũng không cung cấp một status handle public có thể dùng để khám phá trạng thái thật của account.

Phải nói rõ 202 chung không bảo đảm một account tồn tại hoặc có một thông báo được gửi. Tuy vậy, nếu hệ thống hoàn toàn không thể tiếp nhận công việc, lỗi hệ thống cần có hợp đồng riêng; không dùng response chung để che mọi outage khỏi vận hành.

### 5.2. Rate limit public và giới hạn subject

Nếu public API trả 429 theo nguồn, tài liệu cần nêu ý nghĩa mà caller có thể hiểu mà không tiết lộ lịch sử riêng của subject. Giới hạn subject nội bộ có thể cần được che trong response chung theo policy.

RFC 6585 định nghĩa 429 cho quá nhiều request và cho phép header Retry-After. Việc đếm theo account, IP hay scope khác là phần contract của hệ thống. [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Không công bố mọi ngưỡng anti-abuse nhạy cảm vào một error detail nếu policy không cho phép. Nhưng client vẫn cần biết có nên chờ, dừng tự động retry hay cung cấp phương án tiếp theo.

## 6. Proof, grant và tác động lên session

Tài liệu trao đổi proof cần trả lời token được lấy từ đâu, purpose nào, cách gửi, khi nào hết hạn và khi nào bị tiêu thụ. Không yêu cầu đưa proof vào URL API nếu có thể gửi theo kênh request phù hợp và tránh lộ vào log.

Trong mô hình bearer minh họa, proof được gửi trong body tới operation riêng, sau đó server có thể cấp một recovery grant opaque với action hạn chế. Grant đó chưa là access token cho toàn hệ thống.

### 6.1. Hợp đồng expiry và một lần sử dụng

Ghi rõ điểm server đánh giá thời gian: khi nhận request, khi bắt đầu xử lý hay tại điểm quyết định cấp quyền theo thiết kế. Dùng thời gian server, không cho client tùy chọn `now` để kéo dài proof.

Nếu một proof được đổi thành grant một lần, việc retry trao đổi sau khi mất response không được mặc định cấp grant mới. Tài liệu cần một quy trình cụ thể: idempotency/reconcile có kiểm soát hoặc khởi động lại đường proof phù hợp theo policy.

Một ví dụ cho TTL phải được đánh dấu là giá trị minh họa nếu không phản ánh policy thật. Không tự chọn một con số rồi để nó trở thành cam kết của SDK.

### 6.2. Purpose và generation

Token password reset không được tài liệu mô tả như quyền reset MFA hoặc thêm passkey. Mọi operation nhận grant cần kiểm tra action/purpose cùng tenant/subject và trạng thái hiện hành thích hợp.

Khi resend thay generation, cancel hoặc forced factor reset vô hiệu hóa quyền cũ, tài liệu phải nêu tác động tới proof/grant đang giữ. Chỉ ghi “token có hạn” không mô tả đủ vòng đời.

### 6.3. Session sau recovery

Nêu rõ API có tự đăng nhập hay không, session/refresh token nào bị thu hồi, khi nào quyền mới được cấp và trạng thái pending nếu tác động ngoài hệ thống chưa hoàn tất.

Trong contract minh họa của bài, operation password reset không trả session đăng nhập đầy đủ. Client phải đi qua bước authentication được hệ thống yêu cầu.

Nếu một triển khai khác có auto-login, tài liệu cần mô tả mức quyền và bảo đảm thực tế; không sao chép hợp đồng minh họa này rồi để hành vi khác đi mà không kiểm tra.

## 7. Status code, problem details và dữ liệu được phép lộ

Một bảng policy minh họa, không phải bảng ánh xạ bắt buộc cho mọi recovery API:

| Tình huống | Response có thể chọn trong contract ví dụ | Điều client cần biết |
| --- | --- | --- |
| Khởi tạo hợp lệ về schema | 202 với thông điệp chung | Chưa xác nhận account/delivery/completion |
| Body không hợp lệ | 400 với validation được phép lộ | Sửa kiểu/field, không retry nguyên xi |
| Proof không hợp lệ để trao đổi | 400 với code proof chung | Không suy ra trạng thái riêng của account |
| Thiếu hoặc sai bearer grant | 401 ở operation yêu cầu HTTP auth | Không có authorization hợp lệ cho operation |
| Grant hợp lệ nhưng sai action | 403 theo contract | Không đổi mục đích hoặc thử API khác để lách |
| Scope/payload của operation lặp bị xung đột | 409 | Không đổi key mù để tiếp tục |
| Giới hạn public có thể công khai | 429 | Chờ theo contract, không retry dồn dập |
| Dependency không thể quyết định | 503 hoặc error contract tương ứng | Kết quả có thể cần reconcile, không mặc định rollback |
| Password reset đã hoàn tất theo contract | 204 | Không có body và không tự có session đầy đủ |

Nếu dùng 401, response phải có challenge WWW-Authenticate thích hợp theo HTTP. Đừng mô tả một JSON error thay cho header bắt buộc đó. HTTP 204 không mang response content. [RFC 9110 §15.5.2 và §15.3.5](https://www.rfc-editor.org/rfc/rfc9110.html).

### 7.1. Một problem response minh họa

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://docs.example.invalid/problems/recovery-proof-invalid",
  "title": "Không thể sử dụng bằng chứng khôi phục",
  "status": 400,
  "code": "RECOVERY_PROOF_INVALID",
  "detail": "Hãy thực hiện lại hướng dẫn khôi phục phù hợp."
}
```

RFC 9457 cung cấp mô hình problem details cho lỗi HTTP và lưu ý tránh lộ thông tin có thể gây rủi ro. `code` ở ví dụ là extension do API định nghĩa, không phải field bắt buộc chung của RFC. [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html).

Trong contract riêng, có thể yêu cầu một số field để SDK ổn định. Phân biệt điều đó với yêu cầu của chuẩn chung. Message có thể được dịch, còn machine code cần có quy tắc tương thích.

Không đưa stack trace, raw token, OTP, account existence, số điện thoại đầy đủ hoặc chi tiết policy nội bộ vào `detail`. Correlation reference nếu có cũng không nên là URL công khai xem toàn bộ case.

### 7.2. Lỗi validation có thể cũng tiết lộ thông tin

Thông báo “email có đúng định dạng không” khác với “email chưa đăng ký”. Chỉ trường hợp thứ nhất thường là kiểm tra schema; trường hợp thứ hai chạm tới dữ liệu account.

Các trường như `proofExpired`, `mfaEnabled` hoặc `remainingAttempts` có thể tạo một oracle. Việc công khai cần được xét theo caller và capability đã được xác minh, không tự thêm vì frontend muốn hiển thị chi tiết.

## 8. Timeout, retry và idempotency phải được viết theo operation

HTTP method không tự quyết định một request có an toàn để retry trong nghiệp vụ recovery hay không. Một POST có thể đã commit dù client không nhận response.

Tài liệu cần phân biệt:

| Operation | Khi response bị mất | Điều không được tự suy ra |
| --- | --- | --- |
| Khởi tạo/gửi lại | Có thể đã tạo ý định gửi hoặc đã gọi provider | Timeout không đồng nghĩa chưa gửi |
| Trao đổi proof một lần | Proof có thể đã bị tiêu thụ và grant đã được tạo | Không mặc định đổi lại proof để lấy grant mới |
| Đổi mật khẩu/factor | Thay đổi có thể đã commit | Không đổi operation key rồi chạy lại vô điều kiện |
| Hủy request | Hủy có thể đã có hiệu lực trong lúc client chờ | Không hồi sinh request bằng retry khởi tạo cũ |
| Đăng ký factor | Credential có thể đang pending hoặc đã active | Không đánh đồng bắt đầu enrollment với hoàn tất |

### 8.1. Hợp đồng idempotency tối thiểu

Nếu API hỗ trợ Idempotency-Key, cần nêu:

- Operation nào yêu cầu hoặc cho phép key.
- Namespace gắn với tenant, subject/grant và loại tác động nào.
- Cùng key cùng payload được xử lý thế nào.
- Cùng key nhưng payload có ý nghĩa khác trả outcome gì.
- Hai request đồng thời đang xử lý có hành vi gì.
- Key/outcome được giữ bao lâu theo policy và sau thời hạn còn bảo đảm gì.
- Caller phải được xác thực thế nào để xem lại outcome.
- Việc key hoặc grant hết hiệu lực có ý nghĩa gì với kết quả operation cũ.

Key không phải authorization. Một caller biết key không được xem hoặc thực hiện operation của subject khác.

Nếu grant đã được tiêu thụ, việc trả lại receipt/outcome cũ cần một quy tắc xác minh gắn đúng operation và caller; không biến grant đã dùng thành quyền thực hiện thao tác mới. Nếu không còn đủ điều kiện đọc lại outcome, lỗi xác thực không chứng minh operation trước đã rollback.

### 8.2. Retry không được tạo thêm bí mật hoặc quyền

Đối chiếu payload cần bảo vệ dữ liệu như password mới, không dump payload vào ledger để dễ so sánh. Mô tả cơ chế fingerprint/binding và scope ở mức người tích hợp cần biết, giữ chi tiết bí mật trong thiết kế nội bộ.

Một lần replay outcome thành công có thể chỉ trả lại trạng thái hoàn tất. Không phát thêm session, refresh token, recovery code hoặc grant chỉ vì client gửi lại một operation đã xong.

Nếu implementation không có idempotency cho một operation, tài liệu nên nói rõ và chỉ ra đường reconcile hoặc bắt đầu lại được phép. Một lời khuyên “retry tối đa ba lần” không giải quyết được side effect chưa rõ.

### 8.3. Concurrency và những hành vi client cần dự kiến

Mô tả trường hợp cùng token bị dùng hai lần, resend làm generation cũ mất hiệu lực, cancel cạnh tranh với finalize và hai recovery cùng account.

Không hứa một request tới trước theo đồng hồ client sẽ thắng. Nêu điều kiện commit và kết quả có thể quan sát theo contract server.

Nếu có asynchronous operation, receipt/polling cần authorization và trạng thái rõ. Trong ví dụ OpenAPI dưới đây, password reset trả 204 chỉ khi completion theo contract đã đạt; một triển khai trả 202 chờ xử lý cần một contract khác cho trạng thái chờ, không được chỉ đổi status trong tài liệu.

## 9. OpenAPI minh họa cho luồng mất mật khẩu

Đoạn sau chọn OpenAPI 3.1.1 làm phiên bản minh họa cố định; nó không khẳng định đây là bản mới nhất hoặc mọi tool đều hỗ trợ như nhau.

Có ba operation: khởi tạo public, trao đổi proof và đổi mật khẩu bằng grant hạn chế. Các luồng MFA, passkey, support và callback chưa nằm trong tài liệu nhỏ này.

```yaml
openapi: 3.1.1
info:
  title: Account Recovery API - Educational Example
  version: 1.0.0-example
  description: >
    Vi du hoc tap cho password recovery.
    Khong phai API da duoc trien khai cua du an.
servers:
  - url: https://recovery.example.invalid
security:
  - RecoveryGrant: []
paths:
  /v1/account-recovery/requests:
    post:
      operationId: startPasswordRecovery
      summary: Khoi tao recovery voi phan hoi chung
      security: []
      description: >
        Khong xac nhan account ton tai, delivery thanh cong hay proof hop le.
        Tenant duoc xac dinh theo trusted routing context.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/StartRecoveryInput'
      responses:
        '202':
          description: Da tiep nhan theo contract khoi tao public
          headers:
            Cache-Control:
              schema: { type: string, const: no-store }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GenericAccepted'
        '400':
          $ref: '#/components/responses/ProblemResponse'
        '429':
          $ref: '#/components/responses/Throttled'
        '503':
          $ref: '#/components/responses/ProblemResponse'
  /v1/account-recovery/token-exchanges:
    post:
      operationId: exchangeRecoveryProof
      summary: Doi proof hop le lay grant han che
      security: []
      description: >
        Yeu cau proof trong body du khong dung HTTP Authorization.
        Proof va grant rang buoc dung purpose, subject va tenant.
        Khong auto retry sau timeout; proof co the da bi tieu thu.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ExchangeProofInput'
      responses:
        '200':
          description: Da cap grant chi cho password reset theo policy
          headers:
            Cache-Control:
              schema: { type: string, const: no-store }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RecoveryGrantOutput'
        '400':
          $ref: '#/components/responses/ProblemResponse'
        '429':
          $ref: '#/components/responses/Throttled'
        '503':
          $ref: '#/components/responses/ProblemResponse'
  /v1/account-recovery/password-resets:
    post:
      operationId: completePasswordReset
      summary: Doi mat khau bang recovery grant dung purpose
      description: >
        Yeu cau bearer recovery grant va Idempotency-Key.
        Chi tra 204 khi cac dieu kien completion da dat.
        Khong cap session dang nhap day du.
        Retry va doc outcome phai tuan binding cua operation.
      parameters:
        - $ref: '#/components/parameters/OperationKey'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PasswordResetInput'
      responses:
        '204':
          description: Operation da hoan tat, khong co response body
          headers:
            Cache-Control:
              schema: { type: string, const: no-store }
        '400':
          $ref: '#/components/responses/ProblemResponse'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/ProblemResponse'
        '409':
          $ref: '#/components/responses/ProblemResponse'
        '429':
          $ref: '#/components/responses/Throttled'
        '503':
          $ref: '#/components/responses/ProblemResponse'
components:
  securitySchemes:
    RecoveryGrant:
      type: http
      scheme: bearer
      bearerFormat: OpaqueRecoveryGrant
      description: >
        Quyen han che cho operation password_reset.
        Khong phai access token thong thuong.
  parameters:
    OperationKey:
      name: Idempotency-Key
      in: header
      required: true
      description: >
        Key cho cung mot operation va payload.
        Khong thay the authorization; khong doi key mu khi timeout.
      schema:
        type: string
        minLength: 16
        maxLength: 128
  responses:
    ProblemResponse:
      description: >
        Loi theo contract cua operation; code va detail duoc loc theo caller.
      headers:
        Cache-Control:
          schema: { type: string, const: no-store }
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    Throttled:
      description: Gioi han co the cong khai theo policy
      headers:
        Cache-Control:
          schema: { type: string, const: no-store }
        Retry-After:
          description: Gia tri neu duoc cung cap theo contract HTTP
          schema: { type: string }
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    Unauthorized:
      description: Khong co HTTP authorization hop le
      headers:
        Cache-Control:
          schema: { type: string, const: no-store }
        WWW-Authenticate:
          required: true
          schema: { type: string }
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
  schemas:
    StartRecoveryInput:
      type: object
      additionalProperties: false
      required: [identifier, purpose]
      properties:
        identifier:
          type: string
          minLength: 1
          maxLength: 254
        purpose:
          type: string
          const: password_reset
    GenericAccepted:
      type: object
      additionalProperties: false
      required: [message]
      properties:
        message:
          type: string
    ExchangeProofInput:
      type: object
      additionalProperties: false
      required: [recoveryToken]
      properties:
        recoveryToken:
          type: string
          minLength: 1
          writeOnly: true
    RecoveryGrantOutput:
      type: object
      additionalProperties: false
      required: [recoveryGrant, expiresAt, allowedAction]
      properties:
        recoveryGrant:
          type: string
          minLength: 1
          description: Secret chi duoc dung trong pham vi grant
        expiresAt:
          type: string
          format: date-time
        allowedAction:
          type: string
          const: password_reset
    PasswordResetInput:
      type: object
      additionalProperties: false
      required: [newPassword]
      properties:
        newPassword:
          type: string
          minLength: 1
          writeOnly: true
          description: Phai dat password policy do server thuc thi
    Problem:
      type: object
      required: [type, title, status, code]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
          minimum: 400
          maximum: 599
        code:
          type: string
        detail:
          type: string
```

### 9.1. Ý nghĩa của security trong ví dụ

Security ở mức root áp dụng mặc định cho operation đổi mật khẩu. Hai operation public dùng `security: []` để gỡ yêu cầu đó.

OpenAPI cho phép operation ghi đè security root. Các Security Requirement Object khác nhau trong mảng là các lựa chọn thay thế; không được vô tình thêm một lựa chọn rỗng nếu không muốn làm security tùy chọn. [OpenAPI 3.1.1 — Operation Object và Security Requirement Object](https://spec.openapis.org/oas/v3.1.1.html).

Việc bỏ HTTP bearer requirement cho exchange không bỏ điều kiện proof trong body. Schema cũng không tự thực thi purpose, tenant hoặc single-use; đó là các kiểm soát server cần được tài liệu prose và test đối chiếu.

`bearerFormat` mô tả định dạng để người đọc/tool hiểu; nó không biến một token bất kỳ thành grant đúng quyền. `writeOnly` cũng không tự cấu hình redaction trong log hay ngăn một proxy thu thập body.

### 9.2. Những giới hạn có chủ đích của ví dụ

Schema không mô tả đầy đủ mọi password rule, giá trị TTL, ngưỡng rate limit hay storage của idempotency. Chúng cần được đưa vào contract thật với nguồn policy rõ, không suy từ `minLength: 1` rằng password một ký tự được hệ thống thật chấp nhận.

Một OpenAPI nhỏ không đủ để người tích hợp tự suy ra quy trình reconcile, hỗ trợ hoặc security assurance. Cần liên kết tới các phần đó và xác định phần chưa được hỗ trợ.

Không đổi `security: []` ở operation đổi mật khẩu chỉ để Swagger UI gọi thử dễ hơn. Môi trường thử phải có cách cấp dữ liệu/grant tổng hợp đúng quyền.

## 10. Viết ví dụ tích hợp và sandbox an toàn

Ví dụ nên dùng địa chỉ, token và account tổng hợp. Đừng chụp traffic thật rồi thay mỗi email trong khi Authorization header, cookie, token URL hoặc ảnh proof vẫn còn.

Một happy path minh họa có thể được trình bày bằng các bước:

1. Gửi khởi tạo, nhận thông điệp chung.
2. Trong sandbox được kiểm soát, nhận proof qua test sink tương ứng.
3. Trao đổi proof theo đúng purpose, nhận grant hạn chế.
4. Gửi password reset với grant và operation key.
5. Xác nhận response hoàn tất theo contract, không giả định có session đầy đủ.
6. Thực hiện authentication tiếp theo nếu sản phẩm yêu cầu.

Test sink không được trở thành endpoint public đọc OTP của mọi account. Tài liệu sandbox cần nêu scope dữ liệu và khác biệt so với production.

### 10.1. Try it out và auto-generated clients

Một portal tài liệu có thể lưu Authorization, request history hoặc dữ liệu đã nhập. Cần đánh giá nơi lưu, scope người dùng và cách tránh dùng secret thật vào môi trường không thích hợp.

Không mặc định generated SDK hiểu đúng recovery grant vì nó có cùng hình thức bearer với access token. Đặt tên credential và method rõ để giảm nhầm lẫn, đồng thời server vẫn phải kiểm tra quyền.

Nếu generator tự retry POST hoặc log body trong chế độ debug, hướng dẫn cần cho biết cấu hình tương ứng với từng operation. Không đưa một cấu hình retry toàn client rồi xem nó an toàn cho mọi bước recovery.

### 10.2. Browser và cookie-based variant

Ví dụ dùng bearer grant để mô tả một kiểu contract. Một triển khai dùng cookie cần tài liệu riêng về cookie attributes, CSRF, origin/CORS và cách kết thúc phiên recovery.

Bearer không tự làm browser integration an toàn; vẫn cần bảo vệ trước XSS, tránh lưu secret ở nơi không phù hợp và ngăn rò rỉ qua analytics.

CORS không phải authorization. Việc browser không cho một origin đọc response không ngăn mọi client khác gửi request, và không thay thế kiểm tra subject/tenant/purpose.

## 11. Mở rộng tài liệu cho MFA, passkey và hỗ trợ

### 11.1. MFA recovery

Mô tả rõ người dùng còn factor độc lập nào, proof thay thế nào được chấp nhận và quyền nào được cấp sau proof. Không viết “nếu mất MFA thì bỏ qua MFA” như một điều kiện API.

Nếu cấp enrollment grant, nêu action hạn chế, expiry, một lần dùng và điều kiện factor mới chuyển từ pending sang active. Không để developer hiểu rằng begin enrollment đã hoàn tất recovery.

Tài liệu cần nêu session cũ, recovery codes và remembered devices bị tác động ra sao theo policy. Một reset binding không tự là revoke mọi quyền đã cấp trước đó.

### 11.2. Passkey recovery

WebAuthn registration có những bước và dữ liệu riêng; không mô tả một passkey mới như chuỗi password thay thế. Hướng dẫn cần liên kết tới contract registration/verification phù hợp của hệ thống.

Nêu sự khác nhau giữa thu hồi credential binding ở relying party và xóa private key/bản sao khỏi thiết bị. API không nên hứa remote wipe nếu chỉ cập nhật record server.

Không để proof cho việc lấy lại account tự cấp quyền thêm một authenticator bất kỳ ở mọi tenant. Enrollment cần đúng account, RP context và policy.

### 11.3. Support/admin và callback

API support cần principal, scope, approval và audit riêng. Đừng public hóa nó bằng cùng security scheme hạn chế dành cho user recovery.

Webhook cần mô tả cơ chế xác thực nguồn, binding event, duplicate, thứ tự và khả năng replay theo hợp đồng provider. Một callback báo delivered không được tài liệu hóa như proof đã xác minh.

Thông tin response nội bộ cho operator có thể chi tiết hơn public API, nhưng vẫn cần giới hạn quyền và redaction. Không chia sẻ một schema nội bộ chứa secret sang portal public chỉ vì code dùng chung DTO.

## 12. Phiên bản và thay đổi có ảnh hưởng bảo mật

Những thay đổi sau có thể ảnh hưởng client hoặc quyền dù path không đổi:

| Thay đổi | Tác động cần xem xét |
| --- | --- |
| Chuyển anonymous sang yêu cầu grant | Client và workflow xác minh thay đổi |
| Đổi purpose/action grant | Quyền đã cấp và API có thể dùng khác đi |
| Đổi thời hạn hoặc điểm expiry | Client retry/handoff có thể không còn đúng |
| Đổi rule resend/generation | Proof cũ có thể mất hiệu lực theo cách mới |
| Đổi synchronous thành asynchronous | Client cần receipt, polling và outcome pending |
| Thêm field bắt buộc hoặc đóng schema | Request cũ có thể bị từ chối |
| Đổi error code hoặc chi tiết công khai | SDK và thông tin bị lộ thay đổi |
| Đổi idempotency scope/retention | Retry có thể tạo tác động khác |
| Thay session policy | Người dùng có thể còn hoặc mất quyền khác trước |

Không gọi mọi thay đổi description là “chỉ tài liệu”. Có thể description cũ đang là thứ duy nhất hướng dẫn client về việc dùng grant đúng scope.

### 12.1. Đồng bộ policy, code và tài liệu

Lưu version, owner, trạng thái và môi trường mà contract áp dụng. Nếu policy phụ thuộc tenant hoặc loại account, ghi cách client biết phần được công bố, không hardcode một ví dụ thành cam kết cho mọi tenant.

Thay đổi khẩn cấp trong sự cố cần được phản ánh vào contract và changelog theo quy trình. Một endpoint đã bị chặn ngoài gateway nhưng tài liệu vẫn hướng dẫn gọi liên tục sẽ làm tăng lỗi và tải hỗ trợ.

Deprecation cần nói rõ phần nào ngừng được hỗ trợ và cách chuyển an toàn. Không để endpoint cũ tiếp tục cấp quyền yếu hơn chỉ vì client legacy chưa nâng cấp.

## 13. Kiểm chứng tài liệu bằng hành vi có thể quan sát

Có ít nhất ba lớp cần phân biệt:

| Lớp kiểm tra | Chứng minh được | Chưa tự chứng minh được |
| --- | --- | --- |
| Parse/lint OpenAPI | Cấu trúc, reference, một số quy tắc schema | Server thực thi quyền và policy |
| Contract test | Request/response khớp các ca đã kiểm tra | Toàn bộ race, abuse và state transition |
| Security/workflow test | Các bất biến được chọn trong luồng thực | Mọi cấu hình, tenant và dependency đều an toàn |

Không đánh dấu API “đã được bảo mật” chỉ vì OpenAPI render được và happy path gọi thành công.

### 13.1. Các oracle cần đọc

Đối chiếu response với state đã commit, proof/grant bị tiêu thụ, outbox notification, credential version và quyền session.

Một endpoint có thể trả 403 nhưng đã thay factor trước khi phát hiện sai purpose. Chỉ so status sẽ bỏ sót lỗi đó.

Test chống enumeration cần xét body, header và hành vi quan sát phù hợp; đo thời gian cần môi trường và phương pháp kiểm soát. Một cặp request có latency gần nhau chưa chứng minh đã loại mọi kênh rò rỉ.

### 13.2. Test negative và ambiguous outcomes

Chuẩn bị proof sai purpose, sai tenant, hết hạn, đã dùng, generation cũ và grant chỉ dùng enrollment gọi API nhạy cảm.

Tạo request đồng thời và lỗi sau commit trước response. Kiểm tra tài liệu retry/idempotency có phản ánh đúng outcome và trạng thái thực.

Một ca test gọi bằng proof vốn sai mật mã không chứng minh binding tenant được thực thi. Dữ liệu cần hợp lệ ở các điều kiện còn lại để xác định cơ chế đang được đánh giá.

## 14. Ma trận nghiệm thu recovery API documentation

| ID | Nội dung cần đối chiếu | Kết quả mong đợi |
| --- | --- | --- |
| DOC-01 | Root/operation security | Public và protected operations khai báo đúng |
| DOC-02 | Scheme recovery grant | Không bị hiểu là session/access token đầy đủ |
| DOC-03 | Start public | Không tiết lộ account/delivery ngoài contract |
| DOC-04 | Proof exchange | Purpose, binding, expiry và một lần dùng rõ |
| DOC-05 | Grant authorization | Đúng tenant, subject, action và generation |
| DOC-06 | Password/factor completion | Milestone và tác động session được nêu đúng |
| DOC-07 | 202 và 204 | Không nhầm accepted với completed, không body ở 204 |
| DOC-08 | 401 | Có WWW-Authenticate thích hợp |
| DOC-09 | Problem details | Schema/code ổn định, detail được lọc theo caller |
| DOC-10 | Rate limit | Retry và thông tin công khai không tạo oracle ngoài policy |
| DOC-11 | Timeout sau commit | Không hướng dẫn thực hiện lại mù |
| DOC-12 | Idempotency conflict | Cùng key/payload khác và concurrency có contract |
| DOC-13 | Consumed/expired grant | Không mở lại quyền, không suy lỗi auth thành rollback |
| DOC-14 | Resend/cancel/race | Proof cũ và trạng thái cạnh tranh được mô tả |
| DOC-15 | Async receipt nếu có | Quyền đọc và trạng thái pending/unknown rõ |
| DOC-16 | Browser/cookie variant | CSRF, CORS và secret handling được xét đúng |
| DOC-17 | Examples/sandbox | Dữ liệu giả, không lộ secret thật, không endpoint đọc OTP public |
| DOC-18 | Support/webhook | Thẩm quyền riêng và callback không cấp proof trái thiết kế |
| DOC-19 | Version/change policy | Thay đổi bảo mật và tương thích được theo dõi |
| DOC-20 | Evidence | Tài liệu được đối chiếu với code, config và các test trong scope |

Ma trận là công cụ đánh giá, không phải một chứng nhận. Ghi rõ mục nào đã kiểm tra, mục nào pending và những cấu hình nào chưa có bằng chứng.

## 15. Hồ sơ bàn giao và bảo trì

Một bộ bàn giao có thể gồm OpenAPI theo version, workflow guide, error catalogue, retry/idempotency contract, sandbox guide và evidence của các ca kiểm tra.

```text
CONTRACT_ID: recovery-api-example-v1
SCOPE: operations, environments and caller types
OWNER: implementation and documentation owners
SECURITY_MODEL: proof, grant, session and operator boundaries
STATE_AND_EFFECTS: transitions and completion conditions
ERRORS_AND_RETRY: codes, ambiguity, idempotency and reconcile
DATA_HANDLING: cache, logs, examples and sandbox
VERIFICATION: actual checks and known gaps
CHANGE_HISTORY: versions and security-relevant changes
```

Không ghi mọi mục PASS khi mới viết tài liệu. Code mẫu trong bài chưa là bằng chứng implementation thật đã được kiểm thử.

Khi phát hiện drift, xác định code sai, tài liệu sai hay policy chưa được quyết định. Không tự sửa description để hợp thức hóa một đường cấp quyền yếu hơn mà không đánh giá hành vi.

Một issue có ích nêu operation, caller, trạng thái đầu, request, outcome thật và phần contract bị lệch. Báo cáo nên dùng reference an toàn, không dán Authorization header hoặc proof còn hiệu lực.

## 16. Bài tập thiết kế

**Bài tập A — 202 bị hiểu thành đã gửi.** Client hiển thị “SMS đã đến” sau response khởi tạo chung. Viết lại contract và hướng dẫn UI để giữ đúng nghĩa accepted mà không tiết lộ account tồn tại.

**Bài tập B — Grant bị nhầm access token.** Một SDK dùng recovery grant cho API quản lý dữ liệu nhạy cảm. Xác định thay đổi naming, security scheme, tài liệu scope và test server cần có để chặn nhầm lẫn.

**Bài tập C — Timeout sau đổi mật khẩu.** Server đã commit nhưng response bị mất. Mô tả operation identity, điều kiện đọc outcome và hành vi khi grant hết hiệu lực; giải thích vì sao không đổi key rồi thử lại mù.

**Bài tập D — Status endpoint phá anti-enumeration.** Endpoint start trả chung nhưng endpoint poll theo email trả trạng thái thật. Thiết kế lại quyền đọc/payload hoặc bỏ polling public khỏi contract chưa đủ an toàn.

**Bài tập E — OpenAPI làm security tùy chọn.** Root yêu cầu bearer nhưng một operation thêm một lựa chọn security rỗng. Phân tích ý nghĩa theo OAS và đề xuất ca kiểm tra để phát hiện protected operation bị công bố sai.

**Bài tập F — Tài liệu đúng schema nhưng sai workflow.** OpenAPI render được, nhưng mô tả cho phép retry proof exchange một lần sau mọi timeout. Nêu dữ liệu và fault injection cần có để chứng minh token có thể đã bị tiêu thụ, rồi viết hướng dẫn client phản ánh đúng contract.

Một recovery API documentation tốt giúp người tích hợp biết họ đang có quyền gì, operation đã đạt mốc nào và cần hành động thế nào khi thất bại hoặc chưa rõ kết quả. Những điều đó phải được liên kết với policy và hành vi server có thể kiểm chứng.
