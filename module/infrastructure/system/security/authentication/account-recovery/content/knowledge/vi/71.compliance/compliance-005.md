# Audit readiness — Sẵn sàng kiểm toán luồng khôi phục tài khoản

## 1. Mục tiêu: trả lời câu hỏi kiểm toán bằng bằng chứng có thể kiểm tra

Một hệ thống gửi được email đặt lại mật khẩu chưa đủ chứng minh rằng luồng khôi phục tài khoản được kiểm soát. Khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, hệ thống có thể cấp lại một đường truy cập rất mạnh. Người đánh giá cần biết quyền đó được cấp cho ai, dựa trên bằng chứng nào, trong phạm vi nào và với những kiểm soát nào.

Audit readiness là trạng thái tổ chức có thể cung cấp bằng chứng phù hợp để người đánh giá kiểm tra các tuyên bố về thiết kế và hoạt động của kiểm soát trong một phạm vi, một khoảng thời gian xác định.

Trong module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, trọng tâm là chứng minh được chuỗi:

~~~text
Yêu cầu được xác định là áp dụng
    → Chính sách có hiệu lực
    → Kiểm soát được triển khai
    → Quyết định cho một giao dịch recovery
    → Thay đổi thực tế tại hệ thống có thẩm quyền
    → Kết quả và bằng chứng có thể đối chiếu
~~~

Một mắt xích thiếu làm giới hạn kết luận. Ví dụ, có policy yêu cầu thu hồi session không chứng minh API tài nguyên đã từ chối session cũ. Có log “recovery approved” không chứng minh người phê duyệt có quyền tại thời điểm phê duyệt.

Sau bài học, người học có thể:

- Xác định ranh giới kiểm toán cho từng đường khôi phục tài khoản.
- Xây ma trận nối yêu cầu, kiểm soát, owner và bằng chứng.
- Thiết kế bằng chứng nghiệp vụ mà không đưa bí mật xác thực vào log.
- Phân biệt bằng chứng thiết kế với bằng chứng hoạt động trong kỳ.
- Kiểm tra độ đầy đủ, tính toàn vẹn và nguồn gốc của bằng chứng.
- Chuẩn bị tập giao dịch, mẫu kiểm tra và hồ sơ ngoại lệ có thể tái lập.
- Trả lời trung thực những câu hỏi còn thiếu bằng chứng.

Các control ID, schema, số liệu, trạng thái đánh giá và tình huống trong bài là thiết kế minh họa cho một sản phẩm giả định. Chúng không phải biểu mẫu bắt buộc của một cơ quan kiểm toán.

## 2. Xác định đúng điều cần chứng minh

### 2.1. Thiết kế, triển khai và hoạt động là ba lớp khác nhau

| Lớp đánh giá | Câu hỏi | Bằng chứng phù hợp | Giới hạn |
|---|---|---|---|
| Thiết kế | Kiểm soát được đề xuất có xử lý rủi ro không? | Policy, threat model, thiết kế và phân tích đường đi vòng | Chưa chứng minh đã triển khai |
| Triển khai | Cơ chế đó có tồn tại ở hệ thống trong phạm vi không? | Cấu hình thực tế, phiên bản, kiểm tra tích hợp và triển khai | Một thời điểm chưa đại diện cho cả kỳ |
| Hoạt động | Kiểm soát có vận hành theo yêu cầu trong khoảng được xét không? | Tập giao dịch trong kỳ, mẫu đối chiếu, kết quả giám sát và xử lý ngoại lệ | Kết luận phụ thuộc phạm vi và phương pháp kiểm tra |

Một unit test cho token dùng một lần là bằng chứng hữu ích về một phần cơ chế. Nó không tự trả lời token trên production có bị tiêu thụ nguyên tử, mọi endpoint có dùng cùng kiểm tra hay cấu hình có bị đổi giữa kỳ hay không.

Ngược lại, một giao dịch production thành công cũng không tự chứng minh thiết kế chống replay đúng. Cần bằng chứng cho cả hành vi hợp lệ lẫn hành vi phải bị từ chối.

### 2.2. Chốt cơ sở áp dụng trước khi lập checklist

Một hồ sơ yêu cầu nên ghi nguồn, phiên bản, điều khoản liên quan, phạm vi áp dụng, cách diễn giải và người có trách nhiệm xác nhận. Nguồn có thể là hợp đồng, chính sách nội bộ, tiêu chuẩn được tổ chức lựa chọn hoặc nghĩa vụ được xác định bởi bộ phận có thẩm quyền.

[NIST SP 800-53A Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/a/r5/final) cung cấp phương pháp và thủ tục đánh giá kiểm soát bảo mật, quyền riêng tư, đồng thời cho phép điều chỉnh theo bối cảnh quản lý rủi ro. Bài học dùng tư duy lập kế hoạch và đối chiếu bằng chứng đó, không tuyên bố rằng hoàn thành một bảng là đạt chứng nhận.

Đối với một hệ thống lựa chọn áp dụng hướng dẫn định danh số của NIST, cần đối chiếu đúng mức bảo đảm và phương thức recovery. [NIST SP 800-63B-4, phần Account Recovery và Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/) phân biệt các phương thức recovery và yêu cầu thông báo liên quan. Vì vậy, tuyên bố “có gửi OTP là đáp ứng recovery theo NIST” cần được kiểm tra lại theo điều khoản thực sự áp dụng.

Bài học không ấn định một thời hạn lưu bằng chứng, thời hạn thông báo hay mức bảo đảm xác thực cho mọi sản phẩm. Những giá trị đó phải được xác định trong cơ sở áp dụng của hệ thống cụ thể.

### 2.3. Viết tuyên bố đủ cụ thể để bị bác bỏ

Tuyên bố “recovery của chúng tôi an toàn” khó kiểm tra. Một tuyên bố tốt chỉ rõ hành động, phạm vi, điều kiện và tiêu chí.

~~~text
Trong kỳ được xét, mọi thao tác thay MFA qua nhánh hỗ trợ
phải có một phê duyệt còn hiệu lực, gắn với đúng tenant,
account, loại thao tác và phiên bản bằng chứng.

Thao tác commit phải kiểm tra các ràng buộc đó tại server.
Các trường hợp ngoại lệ phải được nhận diện riêng.
~~~

Người đánh giá có thể tìm một mutation thiếu phê duyệt, một phê duyệt của tenant khác hoặc một đường ghi bỏ qua kiểm tra để bác bỏ tuyên bố. Khả năng kiểm tra này làm tuyên bố có giá trị hơn một khẩu hiệu.

## 3. Ranh giới kiểm toán của account recovery

### 3.1. Kiểm kê theo đường nghiệp vụ và nơi thực thi quyền

Tối thiểu cần xác định những đường tồn tại trong sản phẩm:

| Đường nghiệp vụ | Câu hỏi về ranh giới |
|---|---|
| Quên mật khẩu | Ai phát hành và xác minh quyền đặt lại mật khẩu? |
| Mất MFA | Ai được cho phép loại bỏ hoặc thay factor? |
| Mất passkey hoặc thiết bị | Làm thế nào ràng buộc authenticator mới sau khi xác minh? |
| Recovery code | Mã được phát hành, thay thế và tiêu thụ ở đâu? |
| Hỗ trợ thủ công | Công cụ nào có thể phê duyệt hoặc trực tiếp đổi credential? |
| Quản trị tenant | Quyền quản trị có giới hạn đúng tenant và account không? |
| Luồng cũ hoặc batch | Có đường thay credential không đi qua API chính không? |
| Thu hồi quyền sau recovery | Session, refresh token và resource nào thực thi quyết định? |
| Gửi thông báo | Ai chọn địa chỉ, gửi, retry và xác nhận trạng thái? |

Trong trường hợp mất passkey, bằng chứng thường cần giải thích quyền đăng ký credential mới và việc xử lý credential cũ theo chính sách. Không mô tả recovery như một cơ chế lấy lại private key mà dịch vụ vốn không nắm giữ.

Chỉ bao quát những đường thực sự tồn tại. Nếu một đường không tồn tại, ghi căn cứ thay vì để người đọc tự đoán.

### 3.2. Phân biệt bên sở hữu, bên vận hành và bên cung cấp bằng chứng

Một dịch vụ email có thể chứng minh đã nhận yêu cầu gửi. Nó không chứng minh ứng dụng đã chọn đúng địa chỉ thông báo theo policy.

Một nhà cung cấp xác minh danh tính có thể trả kết quả. Ứng dụng vẫn cần chứng minh đã kiểm tra chữ ký hoặc nguồn kết quả, gắn đúng giao dịch và áp dụng đúng điều kiện trước khi cấp quyền.

Với từng dependency, nên ghi:

- Bên nào quyết định cho phép recovery.
- Bên nào thực hiện thay đổi credential.
- Bên nào lưu dữ liệu và bản ghi có thẩm quyền.
- Bên nào có quyền sửa cấu hình hoặc bỏ qua cơ chế bình thường.
- Bằng chứng nào có thể lấy và bằng chứng nào nằm ngoài khả năng quan sát.

Một báo cáo đánh giá của provider chỉ hỗ trợ kết luận trong dịch vụ, thời kỳ và phạm vi mà báo cáo đó bao phủ. Không dùng tên chứng nhận của provider để thay cho bằng chứng tích hợp của ứng dụng.

### 3.3. Thời gian và phiên bản thuộc phạm vi

Hồ sơ phạm vi cần nêu thời gian bắt đầu, kết thúc, múi giờ, môi trường, nhóm account hoặc tenant, các phiên bản có hiệu lực và các loại giao dịch được xét.

Nếu policy thay đổi giữa kỳ, chia phần đánh giá theo phiên bản và thời điểm hiệu lực. Không dùng cấu hình hiện tại làm bằng chứng rằng toàn bộ kỳ trước cũng sử dụng cấu hình đó.

## 4. Xây ma trận kiểm soát và bằng chứng

Ma trận nên bắt đầu từ rủi ro và tuyên bố cần kiểm tra, thay vì bắt đầu từ những ảnh chụp màn hình đang có sẵn.

| ID minh họa | Tuyên bố cần kiểm tra | Bằng chứng thiết kế | Bằng chứng hoạt động | Owner |
|---|---|---|---|---|
| REC-01 | Bằng chứng xác minh đáp ứng policy của nhánh recovery | Quy tắc chấp nhận, ràng buộc mức rủi ro | Quyết định gắn policy và reference tới kết quả xác minh | Identity |
| REC-02 | Quyền recovery chỉ có scope cho hành động được phép | Mô hình grant và kiểm tra authorization | Đối chiếu tenant, account, action ở grant và mutation | Recovery |
| REC-03 | Quyền một lần không tạo thêm mutation ngoài hợp đồng | Ranh giới nguyên tử và quy tắc retry | Kết quả test cạnh tranh, đối chiếu mutation theo grant | Credential |
| REC-04 | Thao tác hỗ trợ có actor và quyền hợp lệ | Ma trận quyền và quy trình phê duyệt | Lịch sử cấp quyền, phê duyệt, action và ngoại lệ | Support |
| REC-05 | Quyền cũ bị xử lý theo policy sau recovery | Thiết kế revocation và inventory resource | Mốc yêu cầu, mốc hiệu lực và kiểm tra ở resource liên quan | Session |
| REC-06 | Thông báo được phát sinh đúng sự kiện và địa chỉ | Quy tắc thông báo, retry, xử lý lỗi | Event, reference địa chỉ theo phiên bản, trạng thái provider | Messaging |
| REC-07 | Bằng chứng được bảo vệ và truy xuất đúng quyền | Thiết kế quyền đọc/ghi và lưu giữ | Kiểm tra quyền, truy cập kho, xuất dữ liệu và phục hồi | Platform |
| REC-08 | Thay đổi policy và ngoại lệ được kiểm soát | Quy trình thay đổi và phạm vi override | Approval, diff, deployment, thời hạn ngoại lệ và review | Security |

Mỗi hàng cần có tiêu chí chấp nhận đủ rõ. Với REC-03, “có cột usedAt” không phải tiêu chí chứng minh chống sử dụng lại. Một tiêu chí có thể yêu cầu hai yêu cầu cạnh tranh không tạo hai business mutation độc lập từ cùng một quyền chỉ cho phép một mutation.

Không phải mọi kiểm soát cần cùng loại bằng chứng hoặc cùng phương pháp lấy mẫu. Chính sách phân quyền có thể cần kiểm tra cả quyền được cấp lẫn quyền đã bị từ chối; kiểm soát hoạt động liên tục có thể cần dữ liệu xuyên suốt kỳ thay vì một ảnh chụp tại thời điểm cuối.

## 5. Thiết kế chuỗi bằng chứng cho một giao dịch

### 5.1. Tách quyết định, mutation và hiệu lực

Một chuỗi sự kiện minh họa:

~~~text
recovery.request.received
    → recovery.evidence.evaluated
    → recovery.authorization.decided
    → recovery.grant.issued
    → credential.change.committed
    → recovery.grant.consumed
    → session.revocation.requested
    → session.revocation.enforced
    → recovery.notification.dispatched
~~~

Chuỗi thực tế có thể khác; không phải giao dịch nào cũng có tất cả sự kiện. Điểm cần giữ là mỗi tên sự kiện có ý nghĩa rõ và được phát sinh ở nơi đủ thẩm quyền xác nhận.

Một log tại controller nói “password changed” trước khi database commit không phải bằng chứng mutation đã thành công. Một event từ session service nói “revocation requested” không đồng nghĩa mọi resource đã từ chối access token.

Thứ tự hiển thị tại collector cũng không tự chứng minh thứ tự commit. Cần giữ thời gian tại nguồn, thời gian nhận, version hoặc sequence khi cơ chế cung cấp được, và giới hạn về đồng bộ thời gian.

### 5.2. Những định danh cần nối được với nhau

Nên có một recovery transaction reference ổn định, một mutation reference từ authority và những liên kết đủ để tìm lại quyết định cấp quyền.

Các định danh dùng để audit phải là reference không có khả năng tự cấp quyền. Không dùng recovery token, session cookie hay bearer grant làm correlation ID.

Trong hệ thống đa tenant, tenant là một phần của khóa đối chiếu. Account ID hoặc mutation ID chỉ duy nhất trong một tenant không được đem join như thể duy nhất toàn hệ thống.

Một request từ người chưa xác thực có thể chưa liên kết được với account có thật. Bản ghi cần phản ánh mức biết thực tế, giữ response bên ngoài phù hợp với thiết kế chống dò account và hạn chế quyền đọc dữ liệu nội bộ có thể tiết lộ sự tồn tại của account.

### 5.3. Ví dụ event tối thiểu có ý nghĩa nghiệp vụ

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-example-204",
  "eventType": "credential.change.committed",
  "occurredAt": "2026-09-18T08:20:31Z",
  "ingestedAt": "2026-09-18T08:20:33Z",
  "producer": {
    "service": "credential-authority",
    "deploymentRef": "release-example-17"
  },
  "scope": {
    "tenantRef": "tenant-example-a",
    "accountRef": "account-example-91"
  },
  "actor": {
    "type": "service",
    "principalRef": "recovery-completion-service"
  },
  "recovery": {
    "transactionRef": "recovery-example-52",
    "grantAuditRef": "grant-reference-77",
    "authorizationDecisionRef": "decision-example-18",
    "initiatingActorRef": "support-agent-example-8"
  },
  "policyRef": "recovery-policy-example-v7",
  "mutation": {
    "ref": "mutation-example-106",
    "type": "mfa-factor-replaced",
    "authorityVersion": 45
  },
  "evidenceRef": "verification-record-example-12",
  "outcome": "COMMITTED"
}
~~~

Đây là dữ liệu tổng hợp. Schema không chứa mã recovery, seed TOTP, private key, password, access token hoặc bản chụp giấy tờ.

Principal thực hiện mutation và người khởi xướng có thể khác nhau. Nếu chỉ ghi principal dịch vụ, người đánh giá có thể không xác định được nhân viên nào đã phê duyệt. Tuy nhiên, các reference này chỉ có giá trị khi được gắn từ ngữ cảnh tin cậy và có bản ghi nguồn để đối chiếu; không tin actor ID do client tự gửi.

Ghi policyRef cũng chưa đủ nếu policy có thể bị sửa tại chỗ mà không giữ lịch sử. Reference phải trỏ tới nội dung có thể xác định lại trong kỳ được xét.

### 5.4. Chọn dữ liệu theo mục đích

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) đề xuất ghi rõ thời điểm, nguồn, chủ thể, hành động và kết quả; đồng thời chỉ dẫn loại trừ bí mật xác thực và bảo vệ dữ liệu log.

Áp dụng vào recovery, ưu tiên loại bằng chứng, kết quả kiểm tra, policy áp dụng và reference có kiểm soát. Người được cấp quyền có thể truy cập hồ sơ xác minh chi tiết khi cần; một dashboard rộng không cần chứa toàn bộ hồ sơ đó.

Dùng định danh giả làm giảm lộ dữ liệu trực tiếp nhưng không tự làm dữ liệu thành vô danh. Nếu có thể nối reference về một người, vẫn cần quản lý quyền và vòng đời dữ liệu phù hợp.

## 6. Làm cho bằng chứng phản ánh commit thực tế

### 6.1. Khoảng trống khi ghi nghiệp vụ và ghi audit tách rời

Hai lỗi phổ biến:

~~~text
Ghi audit trước:
  audit ghi thành công
  → transaction nghiệp vụ rollback
  → audit mô tả một mutation chưa từng tồn tại

Ghi audit sau:
  transaction nghiệp vụ commit
  → tiến trình dừng trước khi gửi audit
  → mutation tồn tại nhưng luồng audit không có bản ghi tương ứng
~~~

Không khắc phục bằng cách đổi tên mọi event thành “success”. Cần mô tả ý nghĩa tại thời điểm phát sinh và chọn cơ chế bảo đảm phù hợp.

### 6.2. Transactional outbox trong trường hợp cùng database

Với kiến trúc mà credential mutation và outbox nằm trong cùng database transaction, có thể ghi cả hai nguyên tử:

~~~text
BEGIN TRANSACTION
  kiểm tra quyền recovery, scope, thời hạn và trạng thái tại authority
  kiểm tra điều kiện consume grant theo cơ chế cạnh tranh được chọn
  thực hiện mutation credential được phép
  ghi trạng thái consume grant
  ghi outbox event mô tả mutation đã thực hiện
COMMIT

dispatcher:
  lấy outbox record đã commit
  gửi tới audit sink có xác thực nguồn
  retry với cùng eventId khi cần
~~~

Ví dụ này giả định các thao tác cần nguyên tử nằm trong cùng ranh giới transaction. Nếu credential authority ở dịch vụ khác, không thể chỉ thêm một outbox local rồi tuyên bố toàn bộ chuỗi phân tán đã nguyên tử.

Dispatcher có thể gửi trùng khi không biết lần gửi trước đã được nhận hay chưa. Audit sink cần xử lý trùng theo định danh ổn định; không đếm mỗi lần nhận là một mutation mới.

Outbox hỗ trợ việc giao event phản ánh commit, nhưng vẫn cần giám sát backlog, retry, dead letter, quyền sửa dữ liệu và tính đúng của nội dung event. Nó không chứng minh mọi đường mutation đều đã được instrument.

### 6.3. Sự kiện không có mutation cũng cần bằng chứng riêng

Đối chiếu với mutation authority chỉ bao phủ những thay đổi đã commit. Nó không cho biết đã bỏ sót bao nhiêu lần từ chối, bao nhiêu lần dò mã hoặc bao nhiêu quyết định bị hủy.

Đối với các sự kiện đó, cần nguồn kiểm kê phù hợp như transaction registry, authorization decision store hoặc bộ đếm có ranh giới rõ. Không dùng số mutation thành công làm mẫu số cho tỷ lệ ghi nhận toàn bộ lần thử recovery.

Chính sách khi audit pipeline gián đoạn cũng cần rõ. Có thể tiếp tục một số bước ít rủi ro, giữ bền dữ liệu chờ gửi hoặc tạm hạn chế nhánh nhạy cảm theo thiết kế. Không tùy tiện khóa mọi người dùng vì collector lỗi, cũng không cho phép một đường đặc quyền hoạt động vô hạn mà mất dấu vết.

## 7. Kiểm tra độ đầy đủ của tập bằng chứng

### 7.1. Xác định population trước khi chọn mẫu

Population là tập các phần tử đủ điều kiện trong phạm vi kiểm tra. Phải ghi đơn vị: request, recovery transaction, grant, mutation, account, phê duyệt hay quyết định.

Một account có thể có nhiều request và nhiều transaction. Một transaction có thể phát sinh nhiều lần giao lại cùng event. Nếu không phân biệt đơn vị, số liệu sẽ bị phóng đại hoặc đánh giá thiếu.

Khi kiểm tra “mọi mutation nhạy cảm có audit”, nguồn population nên xuất phát từ nơi biết mutation thực sự đã commit, kết hợp kiểm kê những đường ghi có thể bỏ qua nguồn đó. Nếu chỉ lấy event từ audit sink rồi hỏi event nào có audit, phép kiểm tra trở thành vòng tròn.

### 7.2. Ví dụ đối chiếu bằng SQL

Giả sử hệ thống có hai tập dữ liệu được xuất với quyền chỉ đọc:

- credential_mutation: bản ghi mutation đã commit từ authority.
- audit_event_export: event đã thu thập, có thông tin nguồn và định danh mutation.

Ví dụ PostgreSQL dưới đây tìm mutation thiếu event tương ứng. Các tên bảng, trường và biến đầu vào là minh họa; truy vấn không được thực thi trong bài học.

~~~sql
SELECT
    m.tenant_id,
    m.account_id,
    m.mutation_id,
    m.mutation_type,
    m.committed_at
FROM credential_mutation AS m
WHERE m.committed_at >= :period_start
  AND m.committed_at <  :period_end
  AND m.mutation_type IN (
      'password-replaced',
      'mfa-factor-replaced',
      'passkey-bound-via-recovery'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM audit_event_export AS a
      WHERE a.event_type = 'credential.change.committed'
        AND a.outcome = 'COMMITTED'
        AND a.tenant_id = m.tenant_id
        AND a.account_id = m.account_id
        AND a.mutation_id = m.mutation_id
        AND a.mutation_type = m.mutation_type
  );
~~~

Điều kiện NOT EXISTS tránh việc giao event trùng làm nhân số dòng của phép đối chiếu này. Nó không kiểm tra được mọi lỗi nội dung như policyRef sai hay actorRef bị giả; những thuộc tính đó cần tiêu chí khác.

Nếu mutation ID chỉ duy nhất theo authority, phải bổ sung authority ID vào khóa. Khóa đối chiếu phải theo schema thật, không được bỏ bớt thành phần chỉ vì truy vấn mẫu ngắn hơn.

### 7.3. Giữ rõ snapshot và event đến muộn

Cần ghi thời điểm export, khoảng commit được xét, nguồn dữ liệu, phiên bản truy vấn, điều kiện lọc và giới hạn phân trang.

Ví dụ, mutation commit cuối kỳ có thể chưa tới collector khi export được tạo. Không lọc audit_event_export bằng một cửa sổ ingestion hẹp rồi kết luận event cuối kỳ bị mất. Cần có cutoff và cơ chế xác nhận dữ liệu đã tới mức đủ xét, hoặc ghi những phần chưa hoàn tất.

“Chờ thêm một khoảng” không tự chứng minh pipeline đã đầy đủ. Có thể cần đối chiếu outbox, watermark của từng partition và các record thất bại. Cách chọn phụ thuộc kiến trúc; sự thiếu chắc chắn phải xuất hiện trong kết quả.

### 7.4. Không giải thích mọi chênh lệch bằng retry

Một chênh lệch có thể đến từ event đến muộn, schema không tương thích, lọc sai tenant, phân trang thiếu, pipeline mất dữ liệu hoặc một đường mutation chưa được ghi nhận.

Mỗi nguyên nhân cần bằng chứng. Bản ghi được backfill phải giữ nguồn thực sự, thời điểm tạo lại và liên kết tới finding. Không giả thời gian ghi như thể event đã được thu thập đầy đủ ngay khi mutation xảy ra.

Đối chiếu không có chênh lệch cũng chỉ có giá trị trong các nguồn và đường ghi đã bao phủ. Nó chưa loại trừ việc có người sửa trực tiếp credential ở một nơi nằm ngoài inventory.

## 8. Bảo vệ, lưu giữ và xuất bằng chứng

### 8.1. Tính toàn vẹn đi cùng nguồn gốc và quyền quản trị

Một manifest có SHA-256 giúp người nhận kiểm tra nội dung file có thay đổi kể từ lúc tạo manifest hay không. Nếu người sửa được cả file lẫn manifest, checksum đơn lẻ không cung cấp sự bảo vệ mong muốn.

Cần kết hợp nguồn đã xác thực, kiểm soát người có quyền ghi, lịch sử xuất, phân tách quyền phù hợp và cơ chế phát hiện thay đổi. Chữ ký hoặc kho lưu trữ hạn chế sửa có thể hỗ trợ tùy kiến trúc.

Ngay cả khi một file được ký đúng, chữ ký không chứng minh nguồn đã ghi đủ mọi sự kiện hoặc từng trường trong file phản ánh sự thật. Bằng chứng vẫn cần đối chiếu với authority và hiểu ranh giới tin cậy.

### 8.2. Kiểm soát quyền đọc và quyền xuất

Nhân viên hỗ trợ cần xử lý recovery không nhất thiết được tải toàn bộ lịch sử xác minh của mọi tenant. Người đánh giá cũng chỉ cần phần dữ liệu tương ứng với phạm vi.

Nên quản lý riêng quyền truy vấn, xem chi tiết nhạy cảm, xuất hàng loạt, thay cấu hình lưu giữ và xóa dữ liệu. Giữ record về hành động xuất để có thể biết ai đã lấy dữ liệu gì, vào lúc nào và phục vụ mục đích nào.

Nếu dùng bản đã che dữ liệu cho review, giữ phương thức nối có kiểm soát tới bản nguồn. Việc che dữ liệu cần thực hiện trước khi chia sẻ, không chỉ dựa vào lời nhắc người nhận đừng nhìn vào một cột.

### 8.3. Lưu giữ theo lớp dữ liệu và mục đích

Hồ sơ quyết định, event kỹ thuật và ảnh giấy tờ xác minh có thể có nhu cầu lưu giữ khác nhau. Không suy rằng phải giữ toàn bộ dữ liệu thô trong suốt thời gian giữ bản tóm tắt kiểm toán.

Một chính sách lưu giữ cần làm rõ chủ dữ liệu, mục đích, thời gian áp dụng, quyền thay đổi, cách truy xuất từ archive và cách xử lý khi có yêu cầu bảo toàn bằng chứng hợp lệ.

Cơ chế bảo toàn phục vụ điều tra cần có phạm vi và người chịu trách nhiệm; không mặc định giữ mọi dữ liệu vô thời hạn. Những quyết định liên quan nghĩa vụ pháp lý phải dựa trên yêu cầu thực sự áp dụng.

Cũng cần chứng minh dữ liệu còn đọc được. Một object vẫn tồn tại nhưng mất khóa giải mã, không còn schema decoder hoặc bị phân quyền sai có thể không đáp ứng nhu cầu cung cấp bằng chứng.

### 8.4. Không thu thập thêm bí mật để làm hồ sơ đẹp hơn

Không lưu recovery token plaintext chỉ để người đánh giá “thử lại”. Không yêu cầu cung cấp seed TOTP hoặc private key của passkey. Không gửi session cookie thật trong một file mẫu.

Khi kiểm tra cơ chế, dùng dữ liệu tổng hợp hoặc tài khoản thử nghiệm được cho phép. Khi kiểm tra vận hành, dùng bản ghi quyết định, reference và kết quả có thể đối chiếu. Hai nhu cầu đó không đòi hỏi sao chép bí mật đang còn hiệu lực.

## 9. Lấy mẫu phản ánh rủi ro và biến thể của luồng

### 9.1. Chọn mẫu có thể giải thích và tái lập

Một kế hoạch nên ghi population, tiêu chí đủ điều kiện, cách chọn mẫu, khoảng thời gian, người thực hiện và mục tiêu của từng nhóm kiểm tra.

Có thể kết hợp mẫu chọn theo phương pháp đã thống nhất với các trường hợp rủi ro cao, nhưng phải ghi rõ cách chọn từng phần. Không gộp các trường hợp chọn có chủ đích rồi diễn giải thành tỷ lệ đại diện thống kê cho toàn bộ hệ thống.

Không có một cỡ mẫu duy nhất phù hợp mọi cuộc đánh giá. Cỡ mẫu và mức bảo đảm cần được thống nhất theo phương pháp đánh giá, rủi ro, tần suất kiểm soát và phạm vi.

### 9.2. Các nhóm dễ bị bỏ sót

| Nhóm giao dịch | Lý do cần chú ý |
|---|---|
| Recovery thành công | Kiểm tra quyền cấp ra và hậu điều kiện |
| Bị từ chối hoặc hết hạn | Kiểm tra hành vi chặn và lý do |
| Replay, retry, yêu cầu đồng thời | Kiểm tra tính một lần và nhất quán |
| Nhánh hỗ trợ hoặc override | Quyền mạnh, có yếu tố con người |
| Tenant hoặc vùng triển khai khác | Cấu hình và ranh giới quyền có thể khác |
| Thời điểm chuyển policy hoặc release | Có thể có hai phiên bản cùng phục vụ |
| Provider lỗi hoặc gián đoạn | Dễ phát sinh fallback và mất bằng chứng |
| Transaction bị hủy giữa chừng | Kiểm tra quyền đã cấp còn hoạt động hay không |
| Account có MFA hoặc passkey | Cần chứng minh quyền đăng ký hay thay factor phù hợp |

Nếu một nhánh không có giao dịch thực tế trong kỳ, ghi population bằng không với căn cứ. Có thể kiểm tra thiết kế và diễn tập bằng dữ liệu tổng hợp, nhưng không gọi đó là bằng chứng rằng nhánh đã vận hành thường xuyên trong production.

### 9.3. Tránh chỉ chọn những hồ sơ dễ giải thích

Một tập mẫu toàn các giao dịch cuối kỳ, cùng tenant, cùng release và không có lỗi sẽ che mất biến thể quan trọng.

Giữ danh sách mẫu ban đầu, lý do thay mẫu nếu có và các hồ sơ không thể lấy được. Không loại một hồ sơ thiếu bằng chứng rồi thay bằng hồ sơ đẹp hơn mà không ghi nhận.

## 10. Chuẩn bị evidence package có thể tái lập

### 10.1. Tổ chức theo câu hỏi và control

Một gói bằng chứng nên giúp người nhận đi từ tuyên bố tới dữ liệu nguồn mà không phải hỏi một kỹ sư riêng cho từng dòng.

Các thành phần thường hữu ích:

1. Phạm vi, kỳ kiểm tra và những phần bị loại.
2. Danh mục yêu cầu áp dụng cùng phiên bản.
3. Ma trận kiểm soát, owner và tiêu chí.
4. Policy, cấu hình và lịch sử thay đổi liên quan.
5. Population, quy tắc chọn mẫu và danh sách mẫu.
6. Truy vấn hoặc phương pháp tạo từng tập dữ liệu.
7. Bằng chứng theo giao dịch và bảng đối chiếu.
8. Danh mục chênh lệch, ngoại lệ và việc khắc phục.
9. Manifest về nguồn gốc, tính toàn vẹn và quyền truy cập.

Đây là cấu trúc tài liệu đề xuất, không phải yêu cầu tạo thêm file cho module học tập.

### 10.2. Ví dụ manifest trong hồ sơ đánh giá

~~~yaml
evidencePackage:
  packageRef: recovery-audit-example-q3
  environment: production
  scope:
    service: account-recovery
    tenantSetRef: approved-scope-example
    periodStart: "2026-07-01T00:00:00Z"
    periodEndExclusive: "2026-10-01T00:00:00Z"
  artifacts:
    - ref: mutation-population-example
      source: credential-authority
      snapshotRef: read-only-export-example-24
      extractionMethodRef: query-example-v3
      generatedAt: "2026-10-03T09:00:00Z"
      integrityManifestRef: protected-manifest-example
    - ref: audit-reconciliation-example
      source: audit-platform
      populationRef: mutation-population-example
      completenessAssessmentRef: pipeline-check-example-11
  limitations:
    - legacy-resource-verification-is-tracked-separately
  access:
    classification: restricted
    ownerRole: recovery-control-owner
~~~

Các reference trong ví dụ không trỏ tới tài nguyên thật. Một manifest thực tế cần có giá trị đủ để người có quyền kiểm tra lại; không để placeholder trông như đã có bằng chứng.

Không ghi “complete” chỉ vì đã nén đủ danh sách file dự kiến. Cần xem từng file có đúng phạm vi, có truy xuất được và có hỗ trợ kết luận liên quan không.

### 10.3. Bằng chứng nhạy cảm nên được dẫn chiếu có kiểm soát

Với một giao dịch bị nghi gian lận, bản tổng hợp có thể nêu kết quả xác minh, loại bằng chứng và reference. Người đánh giá được cấp quyền mới truy cập hồ sơ chi tiết nếu mục tiêu kiểm tra đòi hỏi.

Nếu dữ liệu đã bị xóa theo chính sách trước kỳ yêu cầu cung cấp, ghi rõ điều gì vẫn còn, điều gì không thể chứng minh và căn cứ của quyết định lưu giữ. Không dựng lại một tài liệu giả như thể đó là bản được lưu từ đầu.

## 11. Diễn tập trả lời một yêu cầu kiểm toán

Giả sử người đánh giá chọn transaction tổng hợp recovery-example-52 và hỏi: “Vì sao thao tác thay MFA này được cho phép, và sau đó quyền cũ đã bị xử lý thế nào?”

### 11.1. Đi theo một đường kiểm tra có thể đối chiếu

| Bước | Cần cung cấp | Kiểm tra chéo |
|---|---|---|
| Xác định giao dịch | Tenant, account reference, loại recovery và thời điểm | Có thuộc population và kỳ xét không? |
| Xác định quy tắc | Policy version có hiệu lực | Có khác phiên bản hiện tại không? |
| Xác minh chủ thể | Kết quả và reference bằng chứng được chấp nhận | Có độc lập đủ với đường đang bị nghi chiếm không? |
| Quyền phê duyệt | Actor, quyền tại thời điểm quyết định và scope | Có tự phê duyệt trái policy hoặc sai tenant không? |
| Cấp quyền giới hạn | Grant audit reference, action, thời hạn | Có bị đổi scope hay tái sử dụng không? |
| Xác nhận mutation | Bản ghi đã commit từ authority | Có cùng account, action và decision không? |
| Hậu điều kiện | Trạng thái factor cũ, session và refresh theo policy | Có bằng chứng hiệu lực ở nơi cần thực thi không? |
| Thông báo | Quy tắc địa chỉ, event gửi và trạng thái có thể quan sát | Có nhầm địa chỉ mới chưa được tin cậy không? |

Không nhất thiết đưa toàn bộ chuỗi lên một ảnh chụp. Một bảng có reference tới nguồn, kèm cách truy xuất và quyền truy cập rõ, thường kiểm tra được tốt hơn.

### 11.2. Một khoảng trống không được biến thành PASS

Giả sử có bằng chứng thay MFA hợp lệ, có lệnh revoke session và resource API chính đã từ chối session cũ. Tuy nhiên, refresh path của client cũ chưa được kiểm tra.

Kết luận nên phân tách:

~~~text
Đã có bằng chứng:
  Thao tác thay MFA đáp ứng điều kiện đã xét.
  Resource API chính từ chối session trong phạm vi verification.

Chưa đủ bằng chứng:
  Refresh path của client cũ đã thực thi đầy đủ quyết định thu hồi.

Việc cần xử lý:
  Xác định inventory client và resource liên quan.
  Thực hiện verification được phép.
  Ghi kết quả, owner và biện pháp bù đắp nếu cần.
~~~

Không kết luận toàn bộ session đã mất quyền chỉ vì một bảng session có trạng thái revoked.

### 11.3. Không kéo suy luận về thông báo đi quá xa

Trạng thái provider “accepted” cho thấy provider đã nhận yêu cầu theo giao thức liên quan. Trạng thái “delivered”, nếu provider cung cấp, vẫn có ý nghĩa riêng theo kênh và cơ chế của provider; nó không chứng minh đúng chủ tài khoản đã đọc.

Bằng chứng cần tương ứng với tuyên bố đang đánh giá. Nếu tuyên bố là phát sinh và gửi thông báo theo policy, không tự đổi thành “chủ tài khoản đã biết”. Nếu quy trình đòi hỏi xác nhận độc lập của người dùng, cần một cơ chế và bằng chứng riêng.

## 12. Quản lý finding, ngoại lệ và việc khắc phục

### 12.1. Phân biệt kiểm soát thất bại với thiếu bằng chứng

Có thể dùng những kết quả đánh giá nội bộ sau:

| Kết quả minh họa | Ý nghĩa |
|---|---|
| SUPPORTED | Bằng chứng hỗ trợ tiêu chí trong phạm vi đã kiểm tra |
| CONTROL_FAILURE | Có bằng chứng hành vi không đáp ứng tiêu chí |
| INSUFFICIENT_EVIDENCE | Chưa đủ bằng chứng để kết luận |
| NOT_APPLICABLE | Không áp dụng, có lý do và căn cứ |

Các tên này chỉ dùng trong ví dụ hồ sơ đánh giá. Chúng không thay cho status kỹ thuật của bài học.

Một mutation không có event trong export chưa đủ xác định ngay cơ chế recovery đã cho phép chiếm account. Nhưng nó là một chênh lệch bằng chứng cần điều tra. Nếu phát hiện grant của tenant A thay được factor của tenant B, đó là hành vi vi phạm kiểm soát đã quan sát được.

### 12.2. Một finding cần mô tả hệ quả và phạm vi

~~~text
Finding:
  Nhánh hỗ trợ cũ chưa lưu policy version trong quyết định phê duyệt.

Ảnh hưởng tới đánh giá:
  Không thể tái lập trực tiếp quy tắc áp dụng cho các mẫu thuộc nhánh đó.

Phạm vi đã biết:
  Các transaction đi qua endpoint cũ trong cửa sổ phiên bản xác định.

Điều chưa biết:
  Các nguồn cấu hình triển khai có đủ để tái dựng toàn bộ kỳ hay không.

Kế hoạch:
  Bổ sung liên kết policy bất biến cho quyết định mới.
  Đánh giá khả năng đối chiếu dữ liệu lịch sử từ nguồn độc lập.
  Ghi rõ phần lịch sử vẫn không đủ bằng chứng.

Owner và nghiệm thu:
  Có người chịu trách nhiệm, thời hạn và evidenceRef khi hoàn tất.
~~~

Không tự bịa policyRef cho dữ liệu lịch sử rồi xem như đã lưu đúng ngay từ đầu. Nếu tái dựng được, phải chỉ rõ phương pháp, nguồn và mức chắc chắn.

### 12.3. Ngoại lệ cần ranh giới và thời hạn

Một ngoại lệ hợp lệ trong quy trình của tổ chức cần người có thẩm quyền, lý do, phạm vi, thời điểm có hiệu lực, thời điểm kết thúc hoặc review và biện pháp bù đắp nếu có.

Ngoại lệ không biến kiểm soát chưa đạt thành kiểm soát đã đạt. Người đánh giá vẫn cần biết điều gì bị bỏ qua và vì sao rủi ro được chấp nhận trong phạm vi đó.

Quyền override đặc biệt cần được ghi nhận riêng. Một tài khoản quản trị chung không đủ thông tin để quy hành động cho từng người nếu không có cơ chế nhận diện cá nhân phù hợp.

### 12.4. Nghiệm thu dựa trên bằng chứng mới

“Đã sửa code” chưa đủ đóng finding về hoạt động. Tùy vấn đề, cần xác nhận bản sửa đã được triển khai tới đúng đường gọi, cấu hình đã có hiệu lực, dữ liệu mới có đủ trường và phép đối chiếu đã cho kết quả mong muốn.

Đồng thời giữ giới hạn về lịch sử. Một sửa đổi từ hôm nay không làm bằng chứng của tháng trước tự trở nên đầy đủ.

## 13. Đưa readiness vào vận hành thường xuyên

### 13.1. Mỗi thay đổi nhạy cảm phải giữ khả năng giải thích

Khi bổ sung recovery channel, provider xác minh, phương thức passkey hoặc nhánh hỗ trợ mới, cần cập nhật inventory và ma trận tương ứng.

Một thay đổi schema event cũng có thể làm mất khả năng đối chiếu dù API recovery vẫn chạy. Owner của bằng chứng cần biết consumer nào sử dụng trường bị đổi, cách đọc dữ liệu cũ và cách phát hiện trường thiếu.

Không cần lưu mọi byte của hệ thống. Cần giữ những dữ kiện đủ để giải thích quyết định và kiểm tra tuyên bố trong thời gian được yêu cầu.

### 13.2. Chỉ số đo khả năng chứng minh

| Chỉ số | Cần ghi kèm để diễn giải đúng |
|---|---|
| Mutation có event tương ứng | Nguồn population, khóa đối chiếu, cutoff và độ bao phủ đường ghi |
| Transaction có policy version truy xuất được | Các loại transaction áp dụng và phiên bản schema |
| Ngoại lệ đang hiệu lực | Phạm vi, owner, thời hạn và biện pháp bù đắp |
| Bằng chứng không thể truy xuất | Nguyên nhân, tuổi dữ liệu và tác động tới kỳ đánh giá |
| Thời gian chuẩn bị một mẫu | Loại mẫu và những bước cần làm thủ công |
| Finding quá hạn | Mức rủi ro và điều kiện nghiệm thu |
| Khoảng thời gian pipeline chưa được đối chiếu | Nguồn, partition và dữ liệu có thể đến muộn |

Ví dụ giả định: authority ghi nhận 120 mutation trong population, audit export có event khớp cho 118 mutation. Hai mutation còn thiếu phải được điều tra; 118/120 chỉ mô tả kết quả đối chiếu của tập này tại cutoff đã ghi.

Không gọi tỷ lệ đó là “độ tuân thủ toàn hệ thống”. Nó không đo các lần từ chối, quyền phê duyệt, chất lượng xác minh hay những đường mutation ngoài population.

### 13.3. Giữ trách nhiệm rõ ràng

Owner kiểm soát chịu trách nhiệm giải thích thiết kế và hoạt động. Owner dữ liệu chịu trách nhiệm chất lượng nguồn và quyền truy xuất. Người đánh giá xác định bằng chứng có đủ cho mục tiêu đánh giá hay không theo phương pháp áp dụng.

Một nhóm nhỏ có thể kiêm nhiều vai, nhưng không để một nhiệm vụ quan trọng bị hiểu rằng “đội khác chắc đã làm”. Đặc biệt cần thống nhất ai điều tra chênh lệch giữa credential authority, recovery service và audit platform.

## 14. Bài tập vận dụng

### Bài tập 1: Ảnh chụp cấu hình cuối kỳ

Nhóm chỉ cung cấp ảnh cấu hình ngày cuối kỳ để chứng minh toàn bộ kỳ đã giới hạn thời gian sống của grant.

Hãy chỉ ra kết luận nào được hỗ trợ và bằng chứng nào còn cần.

Gợi ý: ảnh có thể hỗ trợ trạng thái tại thời điểm chụp nếu nguồn đáng tin. Cần lịch sử cấu hình, rollout và thời điểm hiệu lực để đánh giá cả kỳ; phải xem có tenant, instance hoặc nhánh cũ dùng quy tắc khác không.

### Bài tập 2: Tập mẫu toàn giao dịch thành công

Một báo cáo kết luận kiểm soát chống replay hiệu quả vì 30 người dùng khôi phục thành công.

Hãy thiết kế cách kiểm tra bổ sung.

Gợi ý: giao dịch hợp lệ chứng minh khả năng hoàn tất, không kiểm tra đầy đủ replay. Cần xem cơ chế dùng một lần, kiểm tra cạnh tranh tại tầng phù hợp và dữ liệu vi phạm bất biến nếu có. Bằng chứng thử nghiệm và bằng chứng vận hành phải được ghi đúng loại.

### Bài tập 3: Có checksum là đủ?

Kỹ sư đặt file export và file chứa checksum trong cùng folder mà mọi quản trị viên ứng dụng đều có thể sửa.

Hãy phân tích giới hạn.

Gợi ý: người sửa được cả hai có thể tạo lại checksum. Cần xem nguồn dữ liệu, quyền sửa, lịch sử xuất và cơ chế bảo vệ manifest; checksum cũng không chứng minh export đã lấy đủ population.

### Bài tập 4: Hai tenant dùng cùng mutation ID

Audit sink được join với authority chỉ bằng mutation_id. Mỗi tenant có sequence riêng.

Hãy mô tả lỗi kết luận có thể xảy ra.

Gợi ý: event của tenant A có thể che một mutation thiếu event ở tenant B. Khóa phải bao gồm thành phần xác định duy nhất theo schema thật, như authority, tenant, account và mutation khi cần.

### Bài tập 5: Provider đã nhận thông báo

Nhóm nói “chủ tài khoản đã được xác nhận an toàn” vì provider trả accepted cho email thông báo.

Hãy sửa tuyên bố.

Gợi ý: chỉ khẳng định sự kiện mà response thực sự hỗ trợ. Cần đối chiếu địa chỉ được chọn, policy, kết quả gửi và các kiểm soát phục hồi quyền; accepted không chứng minh người nhận đã đọc hoặc actor không còn quyền.

### Bài tập 6: Điền bù dữ liệu lịch sử

Sau khi phát hiện event cũ thiếu policy version, nhóm muốn điền toàn bộ bằng phiên bản policy hiện tại.

Hãy đề xuất hướng xử lý có thể kiểm tra.

Gợi ý: tái dựng từ lịch sử triển khai và cấu hình nếu có nguồn đủ tin cậy, ghi phương pháp cùng mức chắc chắn. Không suy phiên bản hiện tại áp dụng ngược cho lịch sử; những record không thể xác định cần được giữ là khoảng trống bằng chứng.

## 15. Kết quả cần đạt

Một luồng recovery sẵn sàng cho kiểm toán cho phép người có quyền lần theo một quyết định tới policy, bằng chứng xác minh, quyền được cấp, mutation thực tế và những hậu điều kiện cần thiết.

Hồ sơ đáng tin cũng chỉ rõ phần chưa được chứng minh. Khi điều kiện đó được duy trì trong vận hành, audit readiness trở thành khả năng giải thích và kiểm tra việc cấp lại quyền truy cập, thay vì một đợt gom tài liệu trước ngày đánh giá.

## Tài liệu tham khảo

- [NIST SP 800-53A Rev. 5 — Assessing Security and Privacy Controls in Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/a/r5/final): phương pháp và thủ tục đánh giá kiểm soát.
- [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/): tham chiếu về account recovery và thông báo, cần đối chiếu theo phạm vi áp dụng.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thiết kế log ứng dụng, dữ liệu cần loại trừ và bảo vệ log.
