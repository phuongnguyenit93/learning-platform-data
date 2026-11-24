# Recovery event taxonomy — Phân loại sự kiện khôi phục tài khoản

## 1. Vì sao recovery cần một hệ phân loại sự kiện riêng?

Một luồng khôi phục tài khoản có thể đi qua nhiều thành phần: nhận yêu cầu, đánh giá rủi ro, phát token dùng một lần, xác minh bằng chứng, thay mật khẩu hoặc yếu tố xác thực và xử lý các session đang tồn tại. Nếu tất cả chỉ được ghi bằng thông báo “recovery success” hoặc “recovery failed”, người vận hành không biết thành công ở bước nào, điều kiện nào đã được thỏa mãn và thay đổi nào thực sự được cam kết.

**Recovery event taxonomy** là bộ từ vựng và quy tắc dùng chung để phân loại các sự kiện đó. Nó xác định tên sự kiện, ý nghĩa, thời điểm phát, đối tượng liên quan, kết quả và những dữ liệu được phép kèm theo.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, taxonomy phải bao phủ việc mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Nó giúp trả lời các câu hỏi:

- Ai đã khởi tạo hoặc thực hiện hành động, và danh tính đó đã được xác thực đến mức nào?
- Hành động thuộc yêu cầu nào, mục đích nào và tài khoản nào nếu đã xác định được?
- Đó là yêu cầu thực hiện, quyết định của chính sách hay thay đổi đã hoàn tất?
- Token đã được chấp nhận, bị từ chối hay không kiểm tra được vì lỗi hệ thống?
- Credential đã thay đổi chưa? Session đã mất hiệu lực hay mới có yêu cầu thu hồi?
- Có dấu hiệu lạm dụng, can thiệp thủ công hoặc bỏ qua quy trình hay không?

OWASP khuyến nghị log ứng dụng thể hiện thời gian, nơi phát sinh, chủ thể và hành động; các thuộc tính phân loại cần được thống nhất. Bài này đề xuất một taxonomy cho recovery dựa trên nhu cầu nghiệp vụ đó. Các tên sự kiện và schema minh họa dưới đây là lựa chọn thiết kế, không phải bộ tên bắt buộc do OWASP quy định. [Nguồn: OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

## 2. Một sự kiện ghi nhận một sự thật có phạm vi rõ ràng

### Phân biệt sự kiện, trạng thái, log kỹ thuật và cảnh báo

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Sự kiện nghiệp vụ | recovery.token.consumed | Quyền của token đã được sử dụng theo giao dịch được xác định |
| Trạng thái hiện tại | Recovery record đang CONSUMED | Kết quả hiện thời; không mô tả đầy đủ lịch sử |
| Log kỹ thuật | Database connection timeout | Thông tin phục vụ chẩn đoán vận hành |
| Tín hiệu phát hiện | Nhiều token bị từ chối trong một cửa sổ thời gian | Kết luận từ một tập dữ kiện |
| Cảnh báo | Đội vận hành được báo về nghi vấn chiếm đoạt tài khoản | Một hành động thông báo theo quy tắc |

Có thể liên kết chúng bằng định danh, nhưng không coi chúng là cùng một loại bản ghi. Một lỗi timeout không chứng minh token sai. Một cảnh báo không chứng minh người dùng là kẻ tấn công. Một hàng trạng thái hiện tại cũng không cho biết ai đã thay đổi nó.

Audit event ghi nhận kết quả của thành phần có thẩm quyền tại thời điểm xảy ra. Nó hỗ trợ điều tra, nhưng không tự chứng minh mọi lời khai của người dùng là đúng hoặc mọi quyết định tự động là chính xác.

### Không suy diễn vượt quá điều đã quan sát

Những cặp sau cần được phân biệt:

| Điều đã biết | Điều chưa được phép kết luận |
| --- | --- |
| Yêu cầu HTTP đã được nhận | Tài khoản tồn tại hoặc người gửi là chủ tài khoản |
| Nhà cung cấp email nhận thông điệp | Người dùng đã nhận, đọc hoặc kiểm soát hộp thư |
| Token khớp và còn hạn | Mọi điều kiện thay MFA hoặc passkey đã được đáp ứng |
| Một bằng chứng được chấp nhận | Danh tính đã được xác minh đầy đủ theo toàn bộ chính sách |
| Credential mới được đăng ký | Credential cũ đã bị thu hồi |
| Lệnh thu hồi session được ghi bền vững | Mọi session ở dịch vụ bên ngoài đã mất hiệu lực |
| Recovery hoàn tất | Người dùng đã đăng nhập bằng cơ chế thông thường |
| Tín hiệu rủi ro cao | Có kết luận chắc chắn về chiếm đoạt tài khoản |

OWASP nhấn mạnh rằng luồng khôi phục MFA không được trở thành cách vượt MFA; phương pháp phù hợp phụ thuộc vào bối cảnh ứng dụng. Taxonomy vì vậy phải ghi rõ loại bằng chứng và quyết định chính sách, thay vì dùng một nhãn “verified” chung cho mọi tình huống. [Nguồn: OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa).

## 3. Thiết kế các chiều phân loại độc lập

Không nên nhét mọi thông tin vào tên sự kiện. Một mô hình minh họa dùng các chiều sau:

| Chiều | Câu hỏi | Ví dụ |
| --- | --- | --- |
| event_type | Điều gì đã xảy ra? | recovery.token.rejected |
| purpose | Mục tiêu của yêu cầu là gì? | PASSWORD_RESET, MFA_REPLACEMENT |
| outcome | Kết quả của thao tác được mô tả là gì? | SUCCEEDED, DENIED, FAILED, OBSERVED |
| reason_code | Vì sao có kết quả đó? | TOKEN_EXPIRED, POLICY_STEP_UP_REQUIRED |
| actor | Ai thực hiện hành động? | ANONYMOUS, RECOVERY_PRINCIPAL, OPERATOR, SERVICE |
| subject | Hành động tác động đến tài khoản nào? | Tham chiếu nội bộ đã giả danh hóa |
| resource | Đối tượng cụ thể nào liên quan? | Recovery request, challenge, token reference |
| decision | Quyết định chính sách là gì, nếu có? | ALLOW, STEP_UP, DENY, DEFER |
| severity | Sự kiện cần được chú ý ở mức nào? | INFO, WARN, ERROR |
| confidence | Độ tin cậy của một kết luận phát hiện | LOW, MEDIUM, HIGH |

Các chiều có ý nghĩa riêng:

- **DENIED** nghĩa là thao tác bị từ chối theo điều kiện hoặc chính sách.
- **FAILED** nghĩa là không thực hiện được thao tác vì lỗi xử lý hoặc phụ thuộc.
- **OBSERVED** ghi nhận đầu vào hoặc sự việc được quan sát, chưa mang ý nghĩa cấp quyền.
- **SUCCEEDED** chỉ khẳng định thao tác được nêu trong event_type đã thành công.

Ví dụ, recovery.policy.evaluated có outcome = SUCCEEDED và decision = DENY là hợp lý: bộ máy chính sách đã đánh giá thành công và đưa ra quyết định từ chối. Ngược lại, recovery.credential.changed với outcome = DENIED là tổ hợp sai nghĩa; khi bị từ chối, chưa có sự kiện “credential đã thay đổi”.

severity cũng không đồng nhất với outcome. Một token hết hạn bình thường có thể chỉ cần INFO; lỗi dịch vụ lưu trữ có thể là ERROR; hành vi dùng lại token trên một tài khoản nhạy cảm có thể tạo tín hiệu WARN hoặc cao hơn tùy chính sách.

purpose nên là enum có giới hạn, chẳng hạn:

~~~text
PASSWORD_RESET
MFA_REPLACEMENT
PASSKEY_REPLACEMENT
AUTHENTICATOR_DEVICE_REPLACEMENT
~~~

MFA_REPLACEMENT không tự bao gồm mọi loại passkey hoặc thiết bị. Hệ thống cần định nghĩa rõ các nhóm của mình và ghi thêm credential_kind nếu cần. Không suy loại recovery từ URL, tên màn hình hoặc loại thiết bị mà người dùng tự khai.

## 4. Danh mục sự kiện theo vòng đời

Quy tắc tên trong bài là **recovery.<đối tượng>.<sự việc>**, dùng chữ thường và dấu chấm. Tên không chứa email, ID tài khoản, ID tenant, mã lỗi nhà cung cấp hoặc biến thể tùy người dùng.

### Nhận yêu cầu và đánh giá chính sách

| event_type | Thời điểm phát | Dữ liệu phân biệt quan trọng |
| --- | --- | --- |
| recovery.request.received | Dịch vụ đã nhận một yêu cầu đầu vào thuộc phạm vi cần ghi nhận | attempt_id, purpose được yêu cầu, nguồn vào |
| recovery.request.opened | Một recovery workflow thực sự được tạo và lưu thành công | recovery_id, policy_version, subject nếu xác định được |
| recovery.request.rejected | Quyết định từ chối mở workflow đã được đưa ra | reason_code có giới hạn, policy_version |
| recovery.policy.evaluated | Một lần đánh giá chính sách kết thúc | decision, policy_version, risk_band, evidence_summary |
| recovery.abuse.blocked | Một biện pháp chống lạm dụng đã chặn hành động cụ thể | control_id, phạm vi kiểm soát, reason_code |

request.received dùng outcome = OBSERVED; request.opened dùng SUCCEEDED; request.rejected và abuse.blocked dùng DENIED. policy.evaluated dùng SUCCEEDED khi phép đánh giá đã hoàn tất, kể cả khi decision = DENY.

Một đầu vào bị chặn có thể chỉ có attempt_id mà chưa có recovery_id. Không tạo tài khoản giả hoặc workflow có thể sử dụng chỉ để điền đủ trường cho audit.

Nếu nhiều sự kiện phản ánh các giai đoạn khác nhau của cùng một đầu vào, chúng cùng dùng attempt_id. Khi tính số yêu cầu bị chặn, cần chọn một loại sự kiện chuẩn hoặc đếm attempt_id phân biệt; không cộng mọi event DENIED thành số lần tấn công.

### Challenge, token và kênh chuyển giao

| event_type | Thời điểm phát | Không được hiểu thành |
| --- | --- | --- |
| recovery.challenge.created | Challenge đã được lưu theo chính sách | Người dùng đã chứng minh quyền kiểm soát kênh |
| recovery.token.issued | Token mới và metadata cần thiết đã được cam kết | Token đã đến tay người dùng |
| recovery.delivery.requested | Yêu cầu chuyển giao đã được lưu bền vững | Nhà cung cấp đã nhận hoặc đã giao |
| recovery.delivery.accepted | Nhà cung cấp xác nhận tiếp nhận thông điệp | Người nhận đã đọc thông điệp |
| recovery.delivery.failed | Thành phần chịu trách nhiệm xác nhận một lỗi chuyển giao | Token không hợp lệ về mặt mật mã |
| recovery.challenge.verified | Một challenge cụ thể được kiểm tra và chấp nhận | Toàn bộ recovery đã được phê duyệt |
| recovery.challenge.rejected | Challenge bị từ chối theo điều kiện | Đã xác định chắc chắn danh tính người gửi |
| recovery.token.rejected | Token bị từ chối vì điều kiện xác định | Dịch vụ đã đổi credential |
| recovery.token.consumed | Việc dùng quyền token đã commit theo hợp đồng | Đã đăng nhập hoặc thu hồi mọi session |

token.issued cần token_ref không có khả năng sử dụng như bearer credential. Không ghi token vào audit. challenge_id, token_ref và recovery_id là các định danh khác nhau; một workflow có thể có nhiều challenge hoặc nhiều token phát lại.

Nếu chỉ có lỗi hạ tầng và chưa kết luận được token hợp lệ hay không, không phát token.rejected với reason TOKEN_INVALID. Có thể dùng recovery.operation.failed với operation = TOKEN_VALIDATION và outcome = FAILED.

Nếu nhà cung cấp có xác nhận giao tới đích đáng tin cậy, hệ thống có thể bổ sung delivery.confirmed với ngữ nghĩa riêng. Không nâng cấp delivery.accepted thành “người dùng sở hữu email”.

### Bằng chứng danh tính, phê duyệt và thời gian chờ

| event_type | Thời điểm phát | Thuộc tính cần giữ |
| --- | --- | --- |
| recovery.evidence.recorded | Một bằng chứng đã được tiếp nhận hoặc ghi nhận | evidence_ref, evidence_kind, nguồn bằng chứng |
| recovery.evidence.evaluated | Phép đánh giá bằng chứng hoàn tất | decision, evaluator_kind, rule_version |
| recovery.review.requested | Yêu cầu xét duyệt thủ công đã được lưu | case_ref, review_policy |
| recovery.review.decided | Người có thẩm quyền đã ra quyết định | operator_ref, decision, reason_code, approver_ref nếu cần |
| recovery.hold.started | Quy trình đi vào thời gian chờ bắt buộc | not_before, policy_version |
| recovery.hold.released | Điều kiện thoát thời gian chờ được xác nhận | release_basis, actor, thời điểm |

Bằng chứng được ghi nhận không đồng nghĩa bằng chứng là thật. Một nhân viên chấp thuận cũng không tự biến mức xác minh thành một mức bảo đảm cao hơn. Các khái niệm như assurance_level phải gắn với một mô hình đã định nghĩa, không tự gán theo tên sự kiện.

Nếu hỗ trợ quy trình ngoại lệ, có thể thêm recovery.exception.authorized. Sự kiện phải nêu mã chính sách ngoại lệ, phạm vi được phép và người phê duyệt; không dùng một trường free-text “admin override” để che đi việc bỏ qua kiểm soát.

### Thay đổi tài khoản, session và kết thúc workflow

| event_type | Thời điểm phát | Phạm vi khẳng định |
| --- | --- | --- |
| recovery.credential.changed | Thay đổi credential đã commit | Loại credential và loại thay đổi |
| recovery.authenticator.enrolled | Yếu tố mới đã được gắn thành công | Authenticator mới đã tồn tại theo hợp đồng |
| recovery.authenticator.revoked | Yếu tố cũ đã bị vô hiệu hóa thành công | Phạm vi yếu tố bị thu hồi |
| recovery.session_revocation.requested | Lệnh thu hồi được lưu bền vững | Công việc thu hồi đã được yêu cầu |
| recovery.session_revocation.completed | Thành phần có thẩm quyền xác nhận hoàn tất phạm vi thu hồi | Phạm vi, cơ chế và kết quả đã xác nhận |
| recovery.notification.requested | Thông báo bảo mật được đưa vào hàng đợi bền vững | Thông báo đã được yêu cầu |
| recovery.flow.completed | Workflow đạt định nghĩa hoàn tất theo chính sách | Các điều kiện bắt buộc đã đáp ứng |
| recovery.flow.closed | Workflow đóng vì hết hạn, thu hồi, hủy hoặc lý do khác | closure_reason; không mặc định thành công |
| recovery.operation.failed | Một thao tác cụ thể không thực hiện được | operation, dependency_kind, error_class |

credential.changed cần change_kind như PASSWORD_REPLACED, không chứa mật khẩu, hash mật khẩu hay mã khôi phục mới. Với passkey, có thể ghi credential_ref nội bộ và thao tác đã hoàn tất, không ghi dữ liệu xác thực dư thừa.

session_revocation.completed phải nêu scope và cơ chế. Ví dụ, tăng security_epoch làm session không còn được chấp nhận tại những điểm thực thi đã kiểm tra epoch là một cơ chế khác với việc xóa tất cả session vật lý. Chỉ ghi những gì hệ thống thực sự bảo đảm.

flow.completed không phải một tên thay thế cho “mật khẩu vừa đổi”. Nếu chính sách bắt buộc thêm bước thu hồi session hoặc hoàn tất gắn authenticator mới, cần giữ workflow chưa hoàn tất cho đến khi điều kiện đó được đáp ứng. Thông báo không bắt buộc có thể tiếp tục được xử lý sau, nhưng sự khác biệt này phải được ghi rõ trong định nghĩa workflow.

## 5. Envelope chung để liên kết các sự kiện

Mỗi loại sự kiện dùng một envelope ổn định. Các trường chi tiết chỉ được xuất hiện khi loại sự kiện cho phép.

| Trường minh họa | Vai trò và quy tắc |
| --- | --- |
| event_id | Định danh của sự thật được phát; giữ nguyên khi gửi lại cùng event |
| event_type | Tên có trong registry |
| schema_version | Phiên bản cấu trúc payload |
| taxonomy_version | Phiên bản hợp đồng ý nghĩa của các loại sự kiện |
| occurred_at | Thời điểm nguồn có thẩm quyền xác định sự kiện xảy ra |
| recorded_at | Thời điểm sự kiện được ghi bền vững tại nguồn |
| ingested_at | Thời điểm hệ thống thu thập tiếp nhận; do phía thu thập bổ sung |
| producer | Dịch vụ, phiên bản và môi trường phát |
| tenant_ref | Phạm vi tenant do máy chủ xác định, nếu áp dụng |
| attempt_id | Liên kết một lần tương tác hoặc thử thực hiện |
| recovery_id | Liên kết toàn workflow nếu đã có workflow |
| causation_id | Sự kiện hoặc thao tác gây ra sự kiện hiện tại nếu xác định được |
| actor | Loại chủ thể, tham chiếu và ngữ cảnh xác thực |
| subject_ref | Tài khoản chịu tác động đã được hệ thống xác định, có thể vắng |
| resource | Loại đối tượng cùng tham chiếu nội bộ |
| purpose | Mục tiêu recovery đã được ràng buộc hoặc giá trị yêu cầu chưa được xác nhận |
| outcome | Kết quả của chính thao tác được mô tả |
| reason_code | Lý do có trong danh mục được phép của event_type |
| policy_version | Chính sách được dùng cho quyết định liên quan |
| record_version | Phiên bản đối tượng khi sự kiện gắn với một thay đổi trạng thái |
| details | Các trường đã được cho phép riêng cho event_type |

Không bắt buộc mọi trường cho mọi event. Với request.received, purpose do người gọi yêu cầu cần được đặt dưới requested_purpose hoặc đánh dấu nguồn rõ ràng. Sau khi workflow được mở, purpose chuẩn lấy từ dữ liệu máy chủ; không ghi đè bằng giá trị mới trong request.

trace_id phục vụ theo dõi kỹ thuật có thể được bổ sung, nhưng không thay recovery_id hoặc event_id. Giá trị trace do bên ngoài gửi vào phải được kiểm tra; nó không chứng minh các hành động thuộc cùng một chủ thể tin cậy.

occurred_at và recorded_at có thể khác nhau. Đồng hồ giữa các dịch vụ cũng có thể lệch, nên không chỉ sắp theo timestamp để suy ra thứ tự nhân quả. record_version hỗ trợ liên kết thay đổi trên một đối tượng; nhiều sự kiện cùng transaction có thể dùng cùng version và vẫn có event_id riêng.

Nếu cần thứ tự tuyệt đối trong một workflow, phải định nghĩa sequence do một thành phần có thẩm quyền cấp hoặc một cơ chế tương đương. Không tự biến thứ tự nhận ở collector thành thứ tự nghiệp vụ.

### Actor và subject là hai khái niệm khác nhau

Một người chưa đăng nhập có thể yêu cầu recovery cho một định danh đã nhập. Actor lúc đó là ANONYMOUS; tài khoản được nhập chỉ là mục tiêu khai báo, không phải danh tính đã xác thực của actor.

Khi token hợp lệ cho phép thực hiện một hành động hẹp, có thể dùng RECOVERY_PRINCIPAL với authentication_context = RECOVERY_RESTRICTED. Điều đó không có nghĩa chủ thể đã có một session đăng nhập đầy đủ.

Trong luồng hỗ trợ thủ công, cần phân biệt người khởi tạo, người phê duyệt và dịch vụ thực thi nếu cả ba đều có vai trò. Không ghi tất cả thành actor = SYSTEM rồi mất dấu trách nhiệm của người vận hành.

## 6. Ví dụ một sự kiện từ chối token

Dữ liệu sau là minh họa. Các tham chiếu được tạo riêng để liên kết audit, không phải token, session cookie hoặc thông tin định danh thật.

~~~json
{
  "event_id": "evt-8b73",
  "event_type": "recovery.token.rejected",
  "schema_version": 1,
  "taxonomy_version": 1,
  "occurred_at": "2026-11-24T03:12:10.245Z",
  "recorded_at": "2026-11-24T03:12:10.251Z",
  "producer": {
    "service": "account-recovery",
    "version": "release-42",
    "environment": "production"
  },
  "tenant_ref": "tenant-ref-17",
  "attempt_id": "attempt-b93",
  "recovery_id": "recovery-6a2",
  "actor": {
    "kind": "ANONYMOUS",
    "authentication_context": "NONE"
  },
  "subject_ref": "acct-ref-a18",
  "resource": {
    "kind": "RECOVERY_TOKEN",
    "ref": "token-ref-c04"
  },
  "purpose": "PASSWORD_RESET",
  "outcome": "DENIED",
  "reason_code": "TOKEN_ALREADY_USED",
  "policy_version": "password-recovery-v5",
  "record_version": 12,
  "details": {
    "verification_method": "EMAIL_LINK"
  }
}
~~~

TOKEN_ALREADY_USED chỉ được ghi khi máy chủ thực sự xác định được token tương ứng đã dùng. Nếu đầu vào không ánh xạ được tới một tài nguyên đáng tin cậy, không bịa recovery_id, subject_ref hoặc token_ref.

Không dùng trực tiếp token chưa xác thực để trích một account ID rồi coi đó là tài khoản đã xác định. Trường nào do phía khách khai báo và cần được ghi lại phải có nhãn nguồn riêng, giới hạn độ dài và quyền truy cập phù hợp.

Một tập reason_code minh họa:

~~~text
TOKEN_INVALID
TOKEN_EXPIRED
TOKEN_ALREADY_USED
TOKEN_REVOKED
PURPOSE_MISMATCH
SECURITY_EPOCH_MISMATCH
ATTEMPT_LIMIT_REACHED
COOLDOWN_ACTIVE
POLICY_STEP_UP_REQUIRED
DEPENDENCY_UNAVAILABLE
~~~

Không phải mọi mã được phép trên mọi loại sự kiện. DEPENDENCY_UNAVAILABLE hợp với operation.failed; TOKEN_ALREADY_USED hợp với token.rejected. Registry phải ràng buộc tổ hợp thay vì chấp nhận một “túi enum” dùng chung không kiểm soát.

Lý do nội bộ có thể chi tiết hơn thông báo trả về người dùng. OWASP khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại khi yêu cầu đặt lại mật khẩu. Audit được giới hạn truy cập có thể phục vụ điều tra, nhưng API công khai, receipt hoặc dashboard của người yêu cầu không được làm lộ các khác biệt đó. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

## 7. Chuỗi sự kiện minh họa

### Đặt lại mật khẩu bằng liên kết dùng một lần

~~~text
attempt-1:
  recovery.request.received                 OBSERVED
  recovery.policy.evaluated                 SUCCEEDED / ALLOW
  recovery.request.opened                   SUCCEEDED
  recovery.challenge.created               SUCCEEDED
  recovery.token.issued                     SUCCEEDED
  recovery.delivery.requested               SUCCEEDED

delivery-job-1:
  recovery.delivery.accepted                SUCCEEDED

attempt-2, cùng recovery_id:
  recovery.challenge.verified               SUCCEEDED
  recovery.policy.evaluated                 SUCCEEDED / ALLOW

transaction thay đổi tài khoản:
  recovery.token.consumed                   SUCCEEDED
  recovery.credential.changed               SUCCEEDED
  recovery.session_revocation.requested     SUCCEEDED

session-worker:
  recovery.session_revocation.completed     SUCCEEDED

workflow:
  recovery.flow.completed                   SUCCEEDED
  recovery.notification.requested           SUCCEEDED
~~~

Đây là một thiết kế mà chính sách yêu cầu xác nhận kiểm soát session trước khi đóng workflow. Hệ thống khác có thể cam kết vô hiệu hóa bằng epoch ngay trong transaction thay credential và ghi nhận cơ chế đó trực tiếp.

token.consumed và credential.changed trong ví dụ phát sinh từ cùng giao dịch. Collector có thể nhận chúng không theo thứ tự hiển thị, nên không diễn giải chúng như hai transaction độc lập.

challenge.verified trước transaction không cấp phép bỏ qua việc kiểm tra lại quyền dùng một lần tại transaction hoàn tất. Nếu quyền bị thu hồi hoặc thay đổi epoch trong khoảng giữa, hành động thay credential phải bị từ chối và có sự kiện đúng với kết quả thực tế.

Một lần dùng lại token sau đó tạo token.rejected / TOKEN_ALREADY_USED. Nó không tạo thêm credential.changed hoặc flow.completed.

### Khôi phục MFA có xét duyệt thủ công

Một luồng khác có thể đi qua evidence.recorded, evidence.evaluated, review.requested, review.decided, hold.started và hold.released trước khi cho phép đăng ký yếu tố mới.

Việc nhân viên phê duyệt là một sự kiện riêng. Đăng ký authenticator mới và thu hồi authenticator cũ cũng là hai sự kiện riêng, chỉ được phát khi từng thao tác hoàn tất.

Nếu nhà cung cấp authenticator trả timeout và chưa biết việc đăng ký có thành công hay không, ghi operation.failed với kết quả chưa xác định của thao tác. Cần đối soát theo operation_ref trước khi thực hiện lại; không suy ra “chưa đăng ký” chỉ từ timeout và không phát enrolled theo dự đoán.

Với passkey, cũng cần phân biệt bắt đầu quy trình đăng ký, xác minh kết quả đăng ký và credential mới được lưu thành công. Taxonomy recovery không thay thế bộ xác minh giao thức passkey.

## 8. Khi nào được phát sự kiện thành công?

Tên sự kiện là một lời khẳng định. Điểm phát cần khớp với ranh giới commit hoặc xác nhận của thành phần có thẩm quyền.

Mã giả cho thao tác thay mật khẩu có thể là:

~~~text
begin transaction
    lock account and recovery grant
    validate purpose, proof, expiry, limits and current security epoch
    consume grant once
    replace password credential
    apply required local session invalidation policy
    append outbox events with stable event_id:
        recovery.token.consumed
        recovery.credential.changed
        appropriate session-control events
commit

relay committed outbox records to audit collection
~~~

Chỉ gọi logger trước commit có thể tạo sự kiện thành công cho một transaction cuối cùng bị rollback. Chỉ gửi event sau commit qua một lệnh mạng không bền vững có thể làm mất dấu vết nếu tiến trình chết ở giữa.

Outbox trong ví dụ giữ thay đổi nghiệp vụ và ý định phát event trong cùng transaction. Relay có thể giao nhiều lần, nên consumer cần loại trùng theo event_id. Gửi lại cùng event không được sinh event_id mới hoặc thay occurred_at.

Một lần thử nghiệp vụ mới là một sự kiện mới, có attempt_id và event_id phù hợp. Không loại bỏ nó chỉ vì recovery_id giống lần trước. Ngược lại, một HTTP retry trả lại kết quả của cùng thao tác idempotent không được bị đếm như một lần thay credential mới.

Audit event không tự trở thành nguồn cấp quyền. Handler phải quyết định từ trạng thái nghiệp vụ có thẩm quyền; không cho phép recovery chỉ vì đọc thấy một event challenge.verified trong kho log.

Nếu kho audit trung tâm tạm ngừng hoạt động, chính sách cần xác định cơ chế đệm bền vững và giới hạn tồn đọng. Với hành động nhạy cảm, có thể yêu cầu không commit nếu không ghi được audit outbox cục bộ; không cần gắn giao dịch nghiệp vụ trực tiếp với độ sẵn sàng của một collector từ xa. Không đổi FAILED thành SUCCEEDED để che lỗi audit.

## 9. Dữ liệu nào không được đưa vào taxonomy payload?

Một taxonomy tốt phải chỉ rõ dữ liệu được phép, thay vì chỉ cung cấp một trường details tùy ý.

Trong thiết kế của bài, payload audit thông thường loại các nhóm sau:

| Nhóm dữ liệu | Cách thay thế phục vụ liên kết |
| --- | --- |
| Raw recovery token, OTP, mã dự phòng | token_ref hoặc challenge_id độc lập |
| Reset URL có bearer token, request body chứa bí mật | Tên endpoint hoặc loại thao tác đã chuẩn hóa |
| Mật khẩu, hash mật khẩu, seed MFA, private key | credential_kind và change_kind |
| Session cookie, access token, refresh token | Tham chiếu audit riêng nếu cần |
| Toàn bộ hồ sơ định danh hoặc ảnh giấy tờ | evidence_ref trong kho riêng có kiểm soát |
| Email hoặc số điện thoại đầy đủ | channel_kind và tham chiếu tối thiểu cần thiết |
| Free-text từ người dùng hoặc nhà cung cấp | reason_code chuẩn hóa và error_ref tới kênh chẩn đoán được bảo vệ |

OWASP nêu các nhóm như token truy cập, mật khẩu, khóa và dữ liệu cá nhân nhạy cảm là thông tin thường cần loại bỏ hoặc xử lý trước khi ghi log. Những giới hạn cụ thể trong bảng là quy tắc đề xuất cho recovery audit của bài. [Nguồn: OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Không thay raw OTP bằng hash OTP để coi là hết nhạy cảm: không gian mã nhỏ có thể cho phép dò ngoại tuyến. Cũng không dùng digest đang phục vụ xác minh token làm định danh audit mặc định; token_ref riêng tránh chia sẻ thêm vật liệu liên quan tới verifier.

Nếu cần nối các yêu cầu cùng một định danh chưa có account, có thể dùng cơ chế giả danh hóa có khóa, ràng buộc theo tenant và phạm vi mục đích. Cần quản lý thời hạn liên kết và xoay khóa; đây không phải dữ liệu vô danh tuyệt đối. Hash không khóa của email dễ bị dò theo danh sách.

IP, thông tin thiết bị và tham chiếu tài khoản vẫn có thể là dữ liệu nhạy cảm hoặc có khả năng liên kết. Chỉ thu thập mức cần thiết cho mục đích điều tra đã xác định, giới hạn quyền đọc và thời hạn lưu.

Tất cả trường từ nguồn không tin cậy cần giới hạn độ dài, kiểm tra enum và mã hóa theo định dạng cấu trúc. Tránh nối chuỗi để tạo log khiến ký tự xuống dòng hoặc dấu phân cách biến đầu vào thành một bản ghi audit giả.

## 10. Registry là hợp đồng của từng loại sự kiện

Một registry minh họa có thể mô tả:

~~~yaml
eventType: recovery.token.rejected
taxonomyVersion: 1
description: Token bị từ chối sau khi kiểm tra điều kiện áp dụng.
allowedOutcomes:
  - DENIED
requiredFields:
  - event_id
  - occurred_at
  - recorded_at
  - producer
  - attempt_id
  - actor
  - outcome
  - reason_code
allowedReasonCodes:
  - TOKEN_INVALID
  - TOKEN_EXPIRED
  - TOKEN_ALREADY_USED
  - TOKEN_REVOKED
  - PURPOSE_MISMATCH
  - SECURITY_EPOCH_MISMATCH
  - ATTEMPT_LIMIT_REACHED
  - COOLDOWN_ACTIVE
optionalFields:
  - tenant_ref
  - recovery_id
  - subject_ref
  - resource
  - purpose
  - policy_version
  - record_version
allowedDetailFields:
  - verification_method
dataClassification: SECURITY_RESTRICTED
~~~

Trong registry đầy đủ, actor, producer và các object lồng nhau cũng có schema và quy tắc trường riêng. Không chỉ kiểm tra vài trường cấp cao rồi cho phép details chứa bất kỳ dữ liệu nào.

Mỗi loại event cần có chủ sở hữu về ngữ nghĩa và điểm phát. Credential service có thẩm quyền khẳng định credential đã thay đổi; dịch vụ gửi email không có thẩm quyền khẳng định identity proofing đã hoàn tất.

Nếu cùng một sự thật được cả API và worker quan sát, cần chọn nơi phát bản ghi chuẩn. Thành phần còn lại có thể phát một sự kiện khác với vai trò rõ ràng hoặc chỉ log kỹ thuật; không tạo hai bản ghi đều mang nghĩa “credential đã thay đổi một lần”.

Một đầu vào hoặc event không đúng schema cần được xử lý theo chính sách lỗi. Không chuyển cả payload nhạy cảm vào dead-letter log để tiện sửa lỗi. Có thể giữ metadata tối thiểu và error_ref trong kênh được kiểm soát.

## 11. Version và mở rộng taxonomy

Tên sự kiện cần giữ ý nghĩa ổn định theo thời gian.

Thêm một trường tùy chọn có thể tương thích với consumer cũ nếu hợp đồng cho phép bỏ qua trường chưa biết. Thay “delivery.accepted” từ nghĩa “provider nhận thông điệp” sang “người nhận đọc thông điệp” là thay đổi ngữ nghĩa và cần một loại event mới hoặc phiên bản hợp đồng mới được quản lý rõ ràng.

Consumer gặp event_type hoặc taxonomy_version chưa hỗ trợ không được tự ánh xạ sang một sự kiện thành công quen thuộc. Có thể giữ bản ghi chưa diễn giải và báo lỗi tương thích mà không làm lộ payload.

reason_code cũng cần được quản lý. Không dùng chuỗi exception message làm mã lý do vì nó không ổn định, dễ tăng số giá trị và có thể chứa dữ liệu nhạy cảm.

Việc thêm loại recovery mới thường mở rộng purpose và chi tiết được phép. Chỉ tạo event_type mới khi có một sự thật nghiệp vụ khác, chẳng hạn phê duyệt ngoại lệ hoặc xác nhận thu hồi một loại yếu tố có ngữ nghĩa riêng. Không tạo bốn bản sao của mọi event chỉ vì có bốn kênh vào.

## 12. Dùng taxonomy để điều tra và phát hiện lạm dụng

Một số truy vấn khái niệm:

| Mục tiêu | Dữ kiện cần nối | Điều cần tránh |
| --- | --- | --- |
| Phát hiện dùng lại quyền | token.rejected với TOKEN_ALREADY_USED theo token_ref | Đếm relay gửi trùng thành nhiều lần thử |
| Phát hiện dò token | Nhiều attempt_id bị token.rejected trong một cửa sổ | Gắn mọi lỗi hạ tầng thành token sai |
| Phát hiện lạm dụng help desk | review.decided hoặc exception.authorized theo operator_ref | Coi service executor là người phê duyệt |
| Tìm session còn hiệu lực sau recovery | credential.changed, yêu cầu thu hồi và xác nhận phạm vi | Coi requested là completed |
| Điều tra gián đoạn | operation.failed theo dependency_kind và phiên bản dịch vụ | Kết luận đó là chiếm đoạt tài khoản |
| Theo dõi workflow bỏ dở | request.opened nhưng thiếu sự kiện kết thúc sau thời hạn hợp lý | Coi thiếu log là bằng chứng chắc chắn chưa hoàn tất |

Tín hiệu phát hiện nên có rule_id, rule_version, khoảng thời gian, số lượng và confidence. Tên như “nghi vấn dùng lại token” phản ánh mức độ chắc chắn tốt hơn việc gán trực tiếp “account_takeover_confirmed” từ một lần từ chối.

Sự vắng mặt của event có thể do chậm thu thập, sai version hoặc mất dữ liệu. Điều tra cần đối chiếu trạng thái nghiệp vụ và tình trạng pipeline trước khi kết luận.

Không lấy mẫu tùy ý các sự kiện thay credential, tiêu thụ quyền, phê duyệt thủ công hoặc thu hồi quan trọng. Với đầu vào lạm dụng có khối lượng lớn, có thể thiết kế tổng hợp riêng để bảo vệ tài nguyên, nhưng phải ghi rõ cửa sổ, số lượng, phạm vi và việc chi tiết đã được lược bớt. Một bản tổng hợp không được giả dạng một lần thử đơn lẻ.

Taxonomy có ích khi tên sự kiện giúp người đọc biết **điều gì đã xảy ra**, envelope cho biết **ai và đối tượng nào liên quan**, còn outcome và reason_code giải thích **kết quả trong đúng phạm vi thao tác**. Những khẳng định về quyền khôi phục, trạng thái credential và session phải luôn bám vào dữ kiện đã được thành phần có thẩm quyền xác nhận.
