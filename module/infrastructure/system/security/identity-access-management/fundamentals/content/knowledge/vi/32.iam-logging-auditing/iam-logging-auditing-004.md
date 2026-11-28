# Password change

## 1. Vì sao thay đổi mật khẩu cần một sự kiện audit riêng?

Thay đổi mật khẩu làm thay đổi một bằng chứng dùng để kiểm soát tài khoản. Sự kiện này có thể là hoạt động tự phục vụ bình thường, thao tác hỗ trợ đã được phê duyệt hoặc một bước trong quá trình chiếm tài khoản.

Trong logging và audit IAM, mục tiêu không phải ghi lại mật khẩu đã đổi thành gì. Mục tiêu là trả lời được:

- Ai yêu cầu và ai thực hiện thay đổi?
- Tài khoản nào bị tác động, thuộc nguồn danh tính và phạm vi nào?
- Thay đổi diễn ra qua luồng tự phục vụ, khôi phục hay quản trị?
- Những điều kiện xác thực và phân quyền nào đã được kiểm tra?
- Yêu cầu bị từ chối, gặp lỗi hay đã được ghi thành công?
- Những phiên, token hoặc công việc tiếp nối liên quan đã được xử lý đến đâu?

Một dòng “password changed” thiếu chủ thể, tài khoản đích và kết quả giao dịch thường không đủ để điều tra. Ngược lại, ghi toàn bộ request để có thêm chi tiết có thể làm lộ chính bí mật mà hệ thống đang bảo vệ.

## 2. Phân biệt các loại thay đổi

Không nên coi mọi thao tác liên quan đến mật khẩu là cùng một hành vi.

| Luồng | Người hoặc hệ thống thực hiện | Ý nghĩa cần thể hiện trong audit |
| --- | --- | --- |
| Tự đổi mật khẩu | Người dùng đã xác thực, đổi mật khẩu của mình | Actor và target tương ứng cùng chủ thể; điều kiện xác thực lại được ghi nhận theo thực tế |
| Đặt lại qua khôi phục | Người hoàn tất bằng chứng khôi phục hợp lệ | Thay đổi dựa trên quyền hạn của luồng khôi phục, không mặc định là phiên đăng nhập đầy đủ |
| Đặt lại bởi quản trị viên | Quản trị viên có quyền với tài khoản đích | Actor khác target; cần phạm vi quyền và tham chiếu yêu cầu hỗ trợ nếu có |
| Xoay vòng tài khoản kỹ thuật | Workload hoặc công cụ quản lý thông tin xác thực | Danh tính máy thực hiện, tài khoản được xoay vòng và trạng thái cập nhật hệ thống đích |
| Thiết lập mật khẩu lần đầu | Luồng cấp phát hoặc kích hoạt đã được cho phép | Không phải thay một mật khẩu cũ; có thể làm xuất hiện một khả năng đăng nhập mới |

Đặc biệt, đặt một mật khẩu cục bộ cho tài khoản vốn chỉ dùng SSO có thể làm thay đổi mô hình đăng nhập. Nếu hệ thống hỗ trợ thao tác này, audit phải phản ánh đúng việc thiết lập hoặc bật phương thức, thay vì che khuất nó dưới nhãn thay mật khẩu thông thường.

Tên sự kiện trong bài là ví dụ schema nội bộ. Tổ chức có thể dùng tên khác, nhưng ý nghĩa giữa các luồng và kết quả cần nhất quán.

## 3. Actor, target và service thực thi

### 3.1. Actor là chủ thể nào được xác minh?

Actor là chủ thể mà hệ thống có căn cứ gắn với thao tác. Nó có thể là người dùng, quản trị viên hoặc workload.

Không lấy tên người thực hiện từ trường `changedBy` do client tự gửi rồi xem đó là bằng chứng. Actor phải được xác lập từ ngữ cảnh xác thực hoặc cơ chế ủy quyền đã được kiểm tra.

Với request chưa xác thực, một tên tài khoản được nhập chỉ là thông tin người gọi khai báo. Nếu ghi lại theo chính sách, cần phân biệt rõ thông tin đó với một danh tính đã xác minh; không tạo bản ghi khẳng định nạn nhân là người thực hiện chỉ vì tên của họ xuất hiện trong yêu cầu.

### 3.2. Target là tài khoản bị thay đổi

Target cần có định danh ổn định trong nguồn danh tính và phạm vi của nó. Chỉ dùng tên hiển thị hoặc email có thể gây nhầm khi thông tin thay đổi hoặc khi nhiều tenant có tài khoản cùng tên.

Ví dụ:

```text
actor: admin-1042, nguồn corporate-identity
target: account-2050, tenant alpha, nguồn application-directory
operation: administrative-password-reset
```

Việc actor và target khác nhau là thông tin có giá trị điều tra, không phải mặc định là bất thường. Cần xét vai trò, phạm vi quyền và yêu cầu công việc tương ứng.

### 3.3. Service thực thi có thể là một chủ thể khác

Một cổng hỗ trợ có thể nhận yêu cầu của quản trị viên rồi gọi service danh tính để thực hiện thay đổi. Khi đó cần giữ được cả người khởi tạo và workload thực thi, nếu mô hình cho phép xác lập mối liên kết đáng tin cậy này.

Không nên chỉ ghi tài khoản kỹ thuật của service ở mọi sự kiện rồi mất dấu người khởi tạo. Cũng không nên tin một header “người yêu cầu” nếu đường chuyển tiếp không được kiểm soát.

## 4. Ghi đúng giai đoạn và kết quả

Một thao tác có thể đi qua nhiều trạng thái:

```text
Nhận yêu cầu
     |
     v
Kiểm tra xác thực lại, quyền và điều kiện
     |
     +---- Không đạt ------> Từ chối
     |
     v
Kiểm tra mật khẩu mới và chuẩn bị ghi
     |
     +---- Lỗi ------------> Thất bại hoặc chưa xác định kết quả
     |
     v
Ghi thay đổi tại kho thông tin xác thực
     |
     v
Xác nhận thay đổi đã commit
     |
     v
Thực hiện các công việc tiếp nối và theo dõi kết quả
```

Các kết quả cần phân biệt:

- **Requested/accepted:** hệ thống đã nhận hoặc tiếp nhận xử lý, chưa chứng minh mật khẩu đã thay đổi.
- **Denied:** không đủ điều kiện xác thực, quyền, phạm vi hoặc quy tắc bảo mật.
- **Rejected:** dữ liệu hoặc mật khẩu mới không đáp ứng chính sách đã định nghĩa, nếu schema tách loại này.
- **Failed:** xử lý gặp lỗi và có căn cứ xác định chưa hoàn tất theo nghĩa của thao tác.
- **Succeeded:** thay đổi đã được nguồn thực thi xác nhận thành công trong phạm vi được ghi.
- **Pending/unknown:** chưa có đủ bằng chứng kết luận, ví dụ mất phản hồi từ hệ thống đích sau khi gửi lệnh.

Không dùng HTTP trả về “đã tiếp nhận” làm bằng chứng rằng mật khẩu đã được đổi. Với thao tác gọi hệ thống khác, timeout cũng không luôn chứng minh thay đổi chưa xảy ra. Cần đối soát hoặc nhận kết quả theo định danh thao tác trước khi kết luận.

Một lần thay đổi thành công tại kho nguồn không đồng nghĩa đã đồng bộ đến mọi hệ thống hoặc đã thu hồi mọi phiên. Các kết quả này cần được mô tả và theo dõi riêng.

## 5. Những trường dữ liệu thường hữu ích

| Nhóm trường | Ví dụ nội dung | Mục đích |
| --- | --- | --- |
| Định danh sự kiện | `eventId`, `schemaVersion`, `eventType` | Phân biệt sự kiện, diễn giải schema và xử lý trùng |
| Thời gian | Thời điểm xảy ra, ghi nhận và nhận vào kho log | Dựng diễn biến, đánh giá độ trễ |
| Nguồn | Service, môi trường, nguồn danh tính | Biết thành phần nào xác nhận điều gì |
| Actor | ID ổn định, loại chủ thể, nguồn xác thực | Truy vết người hoặc workload thực hiện |
| Target | Account ID, tenant/phạm vi, nguồn quản lý tài khoản | Xác định đúng đối tượng bị thay đổi |
| Loại thao tác | Self-service, recovery, admin reset, rotation | Hiểu điều kiện và luồng áp dụng |
| Kết quả | Trạng thái, mã lý do có kiểm soát | Phân biệt từ chối, lỗi và thành công |
| Tham chiếu | Operation ID, correlation ID, yêu cầu hỗ trợ | Ghép các giai đoạn của cùng một thao tác |
| Bằng chứng chính sách | Policy ID/phiên bản, trạng thái xác thực lại đã kiểm tra | Giải thích căn cứ quyết định |
| Tác động tiếp nối | Tham chiếu tác vụ thu hồi phiên hoặc đồng bộ | Không nhầm thay mật khẩu với hoàn tất mọi xử lý |

Thời gian xảy ra và thời gian được thu thập có thể khác nhau. Nên dùng cách biểu diễn nhất quán, thể hiện múi giờ rõ ràng và quản lý đồng hồ của các thành phần. Khi có sai lệch đồng hồ hoặc sự kiện đến muộn, không kết luận thứ tự nhân quả chỉ từ timestamp.

Nếu cần liên kết với phiên, sử dụng tham chiếu audit phù hợp. Không ghi session cookie hoặc giá trị bearer token để làm khóa tương quan. Một định danh phục vụ truy vết không nên có khả năng trực tiếp cấp quyền truy cập.

Ngữ cảnh mạng, thiết bị hoặc mức xác thực chỉ nên được ghi theo nguồn đã xác minh và nhu cầu điều tra. IP hoặc user-agent không tự chứng minh ai là con người thực hiện; dữ liệu client tự khai báo cần được diễn giải với giới hạn tương ứng.

## 6. Ví dụ một sự kiện thay đổi thành công

```json
{
  "schemaVersion": 1,
  "eventId": "audit-event-5001",
  "eventType": "credential.password.changed",
  "occurredAt": "2030-01-01T09:00:00Z",
  "source": {
    "service": "identity-service",
    "environment": "production",
    "identityStore": "application-directory"
  },
  "actor": {
    "type": "user",
    "principalId": "principal-1042",
    "identitySource": "corporate-identity"
  },
  "target": {
    "accountId": "account-2050",
    "tenantId": "alpha"
  },
  "operation": {
    "id": "operation-7001",
    "mode": "SELF_SERVICE_CHANGE"
  },
  "authentication": {
    "reauthenticationVerified": true,
    "auditSessionRef": "audit-session-3001"
  },
  "decision": {
    "policyId": "self-service-password-change",
    "policyVersion": 6,
    "outcome": "SUCCEEDED",
    "reasonCode": "CREDENTIAL_UPDATE_COMMITTED"
  },
  "followUp": {
    "sessionHandlingOperationId": "session-operation-8001",
    "status": "PENDING"
  },
  "correlationId": "request-9001"
}
```

Các tên, ID và thời điểm trên chỉ minh họa. Trong ví dụ, `principal-1042` được hệ thống liên kết hợp lệ với `account-2050`; hai chuỗi ID không cần giống nhau nhưng phải có căn cứ xác định cùng chủ thể cho luồng tự phục vụ.

Sự kiện nói rõ mật khẩu đã được ghi tại kho nguồn. `followUp.status=PENDING` cho biết công việc xử lý phiên chưa được xác nhận hoàn tất. Không được diễn giải sự kiện này thành “mọi phiên cũ đã bị vô hiệu hóa”.

Nếu thao tác do quản trị viên thực hiện cho người khác, cần đổi đúng `mode`, giữ actor quản trị viên và target tài khoản đích, đồng thời ghi căn cứ quyền hoặc tham chiếu quy trình phù hợp. Không sửa actor thành chủ tài khoản để làm mọi bản ghi trông giống tự phục vụ.

Với yêu cầu bị từ chối, dùng loại sự kiện hoặc kết quả thể hiện thất bại đúng schema, chẳng hạn `credential.password.change.denied` cùng mã lý do như `REAUTHENTICATION_REQUIRED` hoặc `TARGET_OUTSIDE_ADMIN_SCOPE`. Không dùng sự kiện có nghĩa “đã thay đổi” để ghi cả các lần chưa thay đổi.

## 7. Tuyệt đối không biến audit thành kho bí mật

Không ghi những dữ liệu sau vào sự kiện audit thông thường:

- Mật khẩu cũ, mật khẩu mới hoặc mật khẩu tạm thời.
- Hash mật khẩu hay bản sao trường lưu thông tin xác thực trong cơ sở dữ liệu.
- Token đặt lại mật khẩu, OTP, mã khôi phục hoặc bí mật sinh mã.
- Authorization header, session cookie hoặc refresh token.
- Toàn bộ request/response có thể chứa các giá trị trên.

Hash mật khẩu cũng là dữ liệu nhạy cảm. Việc ghi nó vào trường `before`/`after` không cần thiết để chứng minh đã có thay đổi và làm tăng nơi phải bảo vệ. Thay vào đó, có thể ghi loại thông tin xác thực, định danh thao tác và phiên bản trạng thái không bí mật nếu thiết kế sử dụng.

Thông báo lỗi cũng cần dùng mã lý do được kiểm soát, không chèn nội dung mật khẩu hoặc token vào chuỗi lỗi. Tránh ghi nguyên đối tượng exception nếu thư viện hoặc lớp gọi có thể đưa request nhạy cảm vào thông điệp.

Các lớp ghi log tự động phải được xem xét cùng nhau: ứng dụng, proxy, công cụ theo dõi request, tracing và chức năng gỡ lỗi. Việc một sự kiện audit đã được lọc không đủ nếu một lớp khác vẫn ghi toàn bộ body.

Dữ liệu không tin cậy như user-agent hoặc chuỗi người dùng nhập cần được giới hạn, mã hóa đúng định dạng và xử lý an toàn để không tạo bản ghi giả qua ký tự điều khiển hoặc làm hỏng cấu trúc log.

## 8. Bảo đảm sự kiện khớp với giao dịch thật

Nếu ghi log “thành công” trước khi cập nhật mật khẩu, giao dịch rollback có thể để lại bằng chứng sai. Nếu cập nhật trước rồi ghi log bằng một lệnh độc lập, tiến trình chết giữa hai bước có thể làm mất sự kiện thành công.

Một cách thiết kế là ghi sự kiện audit hoặc bản ghi outbox bền vững trong cùng giao dịch với thay đổi tại kho cục bộ:

```text
changePassword(command, trustedContext):
    actor = trustedContext.requireVerifiedActor()
    target = accounts.resolveWithinAllowedScope(command.target)
    decision = policy.evaluatePasswordChange(actor, target, command.mode)

    if decision != ALLOW:
        audit.recordDeniedAttempt(
            safeMetadata(actor, target, decision)
        )
        return DENIED

    validatePasswordAccordingToPolicy(command.newPassword)
    newHash = passwordHasher.hash(command.newPassword)

    transaction:
        accounts.replaceCredentialWithRequiredConcurrencyChecks(
            target.id,
            newHash
        )
        auditOutbox.append(
            committedChangeMetadata(actor, target, command.mode)
        )

    return CHANGE_COMMITTED
```

Mã giả chỉ minh họa mối liên kết giữa thay đổi và bằng chứng audit. Nó không mô tả đầy đủ xác thực lại, kiểm tra mật khẩu hiện tại, xử lý quyền thay đổi đồng thời hoặc các biến thể khôi phục.

Khi outbox được phát đến kho log, sự kiện có thể được gửi lại. Giữ định danh sự kiện ổn định và xử lý trùng để một thay đổi không bị đếm thành nhiều lần chỉ vì retry.

Outbox đã ghi không đồng nghĩa kho log trung tâm đã nhận. Cần quan sát tồn đọng, lỗi phát và độ trễ thu thập. Với hệ thống đích bên ngoài, còn phải tách việc đã gửi lệnh và việc đích xác nhận thay đổi; không giả định một giao dịch cục bộ có thể bao phủ cả hai hệ thống.

Hành vi khi không ghi được bằng chứng bắt buộc cần được thiết kế theo độ nhạy và yêu cầu vận hành. Không tự bỏ audit mà vẫn báo mọi thứ hoàn tất; cũng không để một lỗi có thể bị kích hoạt dễ dàng trở thành đường gây gián đoạn ngoài dự kiến. Cần có cơ chế bền vững, khả năng quan sát và quy tắc xử lý rõ.

## 9. Liên kết với phiên, khôi phục và quyền truy cập

Một chuỗi điều tra có thể gồm:

```text
Sự kiện đăng nhập hoặc xác thực lại
                 |
                 v
Yêu cầu thay đổi mật khẩu
                 |
                 v
Quyết định phân quyền
                 |
                 v
Thay đổi thông tin xác thực được commit
                 |
                 v
Yêu cầu xử lý phiên / token / thông báo
                 |
                 v
Kết quả thực thi ở từng thành phần
```

Dùng operation ID và các tham chiếu liên quan để nối chuỗi, thay vì chỉ ghép theo cùng email và thời gian gần nhau. Một request có thể tạo nhiều sự kiện; một sự kiện gửi lại vẫn phải được nhận diện là cùng sự kiện đó.

Nếu thay đổi mật khẩu là một bước trong quy trình khôi phục, cần tham chiếu yêu cầu khôi phục đã được xác minh, nhưng không ghi token khôi phục. Nếu đó là xử lý tài khoản bị chiếm, có thể liên kết với mã sự cố và các tác vụ thu hồi tương ứng.

Không suy rằng đăng nhập bằng mật khẩu mới đồng nghĩa mọi token cũ đã bị thu hồi. Việc chặn ở resource server cần có bằng chứng hoặc phép kiểm chứng riêng theo cơ chế của hệ thống.

Đối với SSO, thay đổi mật khẩu tại một nguồn danh tính có thể không tác động giống nhau đến phiên SSO, phiên cục bộ của ứng dụng và token đã cấp. Audit nên mô tả đúng phạm vi đã thực hiện, để người điều tra không kết luận quá mức từ một sự kiện.

## 10. Phát hiện hành vi cần xem xét

Không phải mọi lần thay đổi mật khẩu đều là sự cố. Các dấu hiệu nên được xét cùng vai trò, lịch công việc và những sự kiện liên quan.

Ví dụ các mẫu có thể cần rà soát:

- Một actor quản trị đặt lại mật khẩu cho nhiều tài khoản trong thời gian ngắn ngoài tác vụ đã biết.
- Đặt lại mật khẩu cho tài khoản đặc quyền, rồi thêm phương thức MFA hoặc đổi kênh khôi phục.
- Nhiều lần từ chối do thiếu xác thực lại, sau đó xuất hiện thay đổi qua một đường khác.
- Đổi mật khẩu sau một phiên có dấu hiệu bị chiếm, nhưng các phiên cũ vẫn hoạt động ngoài thời gian xử lý đã thiết kế.
- Một workload xoay vòng thông tin xác thực cho tài khoản ngoài phạm vi được giao.
- Kho log không còn nhận sự kiện từ nguồn vẫn đang có hoạt động thay đổi mật khẩu.

Ngưỡng và hành động phản ứng cần phù hợp với môi trường. Một chiến dịch xoay vòng hợp lệ có thể tạo nhiều sự kiện; cùng số lượng đó trên tài khoản admin cá nhân có ý nghĩa khác. Cần tránh biến một mẫu thống kê thành kết luận chắc chắn về người thực hiện mà chưa có bằng chứng bổ sung.

## 11. Bảo vệ kho audit và kiểm chứng chất lượng

Nhật ký thay đổi mật khẩu có thể tiết lộ cấu trúc danh tính, tài khoản đặc quyền và hoạt động hỗ trợ. Quyền ghi, đọc, xuất và xóa log cần được giới hạn theo vai trò và phạm vi tenant.

Nên tách quyền thực hiện thay đổi mật khẩu khỏi khả năng tùy ý sửa hoặc xóa dấu vết liên quan. Tùy yêu cầu, có thể dùng lưu trữ chỉ bổ sung, cơ chế phát hiện sửa đổi và bản sao được quản lý độc lập. Không coi chỉ một trường checksum nằm cùng bản ghi và cùng quyền quản trị là bằng chứng đầy đủ chống mọi sửa đổi.

Thời hạn lưu giữ và dữ liệu được phép thu thập cần được xác định theo mục đích điều tra, quản trị và yêu cầu áp dụng cho hệ thống. Không cần lưu bí mật hoặc dữ liệu cá nhân không liên quan chỉ để tăng lượng log.

Các tình huống kiểm chứng quan trọng:

| Tình huống | Bằng chứng mong đợi |
| --- | --- |
| Người dùng tự đổi mật khẩu thành công | Actor, target, mode và kết quả commit đúng |
| Quản trị viên reset cho người khác | Giữ đúng người thực hiện và tài khoản bị tác động |
| Thiếu quyền hoặc thiếu xác thực lại | Có sự kiện từ chối, không có thành công giả |
| Giao dịch rollback | Không ghi nhận thay đổi đã commit |
| Timeout từ kho danh tính bên ngoài | Không kết luận chắc chắn thành công hoặc chưa thay đổi khi chưa có bằng chứng |
| Retry phát cùng sự kiện | Không đếm thành nhiều lần thay mật khẩu |
| Kho log trung tâm gián đoạn | Có cơ chế bền vững, quan sát tồn đọng và phục hồi |
| Request chứa mật khẩu hoặc token | Không xuất hiện bí mật trong audit, tracing hay log tự động liên quan |
| Actor và target cùng tên ở hai tenant | Truy vết đúng nguồn danh tính và phạm vi |
| Thay đổi mật khẩu đã xong, xử lý phiên chưa xong | Thể hiện riêng hai trạng thái, không báo thu hồi hoàn tất sai |

Một sự kiện Password change hữu ích phải chứng minh đúng điều đã xảy ra mà không tiết lộ bí mật: đúng chủ thể, đúng tài khoản, đúng luồng, đúng giai đoạn và đúng phạm vi kết quả. Chất lượng đó làm cho audit có thể hỗ trợ điều tra và kiểm chứng kiểm soát IAM, thay vì chỉ xác nhận rằng ứng dụng đã ghi thêm một dòng log.
