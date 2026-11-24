# Segregation control evidence — Bằng chứng kiểm soát phân tách nhiệm vụ

Bài học thuộc chương **Compliance** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào việc thiết kế, thu thập và kiểm tra bằng chứng cho cơ chế phân tách nhiệm vụ trong các luồng tạo, phê duyệt và thực thi nghiệp vụ nhạy cảm.

Một bảng phân quyền ghi rằng có vai trò “người tạo” và “người duyệt” chưa chứng minh hệ thống đã ngăn tự phê duyệt. Một dòng log ghi `approved=true` cũng chưa cho biết ai duyệt, họ có quyền gì lúc đó, đã duyệt phiên bản dữ liệu nào và giao dịch thực tế có sử dụng đúng quyết định đó không.

**Segregation control evidence** là tập thông tin có thể truy vết để đánh giá quy tắc phân tách đã được định nghĩa, cưỡng chế và vận hành như thế nào trong một phạm vi, khoảng thời gian cụ thể.

Sau bài học, bạn cần có thể:

- Chuyển yêu cầu phân tách nhiệm vụ thành bất biến có thể kiểm thử.
- Phân biệt bằng chứng thiết kế, triển khai, kiểm thử và vận hành thực tế.
- Liên kết người tạo, người duyệt, danh tính đại diện và service thực thi.
- Gắn phê duyệt với đối tượng, tenant, dữ liệu trọng yếu và phiên bản policy.
- Giữ bằng chứng nhất quán với transaction và vòng đời idempotency.
- Phát hiện thiếu bằng chứng, đường bypass và ngoại lệ chưa được kiểm soát.
- Xuất một gói bằng chứng có nguồn gốc, phạm vi và giới hạn rõ ràng.

## 1. Phân tách nhiệm vụ cần chứng minh điều gì?

**Segregation of duties**, thường viết tắt là **SoD**, phân chia những trách nhiệm có xung đột để một chủ thể không tự thực hiện toàn bộ chuỗi nhạy cảm ngoài chính sách được chấp thuận.

Ví dụ trong hệ thống hoàn tiền:

~~~text
Maker tạo yêu cầu với số tiền và đối tượng nhận cụ thể.
Checker độc lập xem xét và phê duyệt yêu cầu đó.
Executor chỉ thực hiện dữ liệu đã được phê duyệt còn hợp lệ.
Người quản lý bằng chứng không có toàn quyền che dấu hành động của chính mình.
~~~

NIST SP 800-53 Rev. 5, AC-5 yêu cầu xác định, lập tài liệu các nhiệm vụ cần phân tách và định nghĩa quyền truy cập hỗ trợ sự phân tách đó. Bài học dùng AC-5 như một tham chiếu thiết kế; phạm vi kiểm soát thực tế phải được tổ chức xác định. [NIST SP 800-53 Rev. 5, AC-5](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-53r5.pdf#page=63).

Hai cách triển khai thường gặp:

| Dạng phân tách | Ví dụ quy tắc | Bằng chứng trọng tâm |
|---|---|---|
| Tĩnh | Một danh tính không được đồng thời giữ hai quyền xung đột trong scope | Lịch sử cấp quyền, nhóm quyền, phạm vi và rà soát xung đột |
| Động | Một người có thể có cả hai quyền nhưng không được duyệt yêu cầu do chính mình tạo | Quyết định trên từng đối tượng, người tạo/người duyệt và lịch sử giao dịch |

Hai dạng có thể cùng tồn tại. Nếu policy yêu cầu phân tách tĩnh, kiểm tra tự duyệt ở runtime không tự thay thế yêu cầu đó. Nếu policy yêu cầu phân tách động, ảnh chụp danh sách role không chứng minh từng giao dịch được xử lý đúng.

Phân tách làm giảm một số rủi ro lạm dụng; nó không tự chứng minh hai người không thông đồng hoặc một tài khoản không bị chiếm quyền. Kết luận bằng chứng cần giới hạn đúng điều đã kiểm tra.

## 2. Viết hợp đồng kiểm soát trước khi thu log

Một kiểm soát phải trả lời được:

~~~text
Hành động nào cần phân tách?
Những chủ thể hoặc trách nhiệm nào bị coi là xung đột?
Scope là tenant, phòng ban, đối tượng hay toàn hệ thống?
Phân tách theo account, con người hay đơn vị trách nhiệm?
Quyền và policy có hiệu lực tại điểm quyết định nào?
Dữ liệu trọng yếu nào làm phê duyệt cũ mất hiệu lực?
Ngoại lệ nào được phép, ai duyệt và được ghi nhận ra sao?
~~~

### 2.1. Ví dụ hợp đồng cho luồng hoàn tiền

Giả sử tổ chức định nghĩa kiểm soát nội bộ minh họa `SOD-REFUND-01`:

~~~text
1. Mọi yêu cầu hoàn tiền thuộc scope đã chọn phải qua một checker.
2. Maker và checker phải là hai con người khác nhau theo nguồn danh tính tin cậy.
3. Checker có quyền phê duyệt trên đúng tenant và đối tượng tại lúc quyết định.
4. Phê duyệt gắn với request ID, version và dữ liệu trọng yếu đã xem xét.
5. Executor chỉ dùng phê duyệt hợp lệ cho đúng nội dung thực thi.
6. Một thao tác hoàn tiền không được tạo tác động trùng do retry.
7. Quyết định và kết quả bền vững phải truy vết được tới bằng chứng.
~~~

Đây là hợp đồng bài học, không phải ngưỡng hoặc quy định bắt buộc cho mọi tổ chức. Nếu hệ thống thật có hạn mức, nhiều tầng duyệt hoặc phân tách theo đơn vị, cần đưa các điều kiện đó vào policy và bằng chứng tương ứng.

### 2.2. Biến hợp đồng thành bất biến

Với một approval đã commit:

~~~text
approval.tenant = request.tenant
approval.requestId = request.id
approval.reviewedVersion = phiên bản đã được trình duyệt
approval.makerPersonId != approval.checkerPersonId
checker có quyền theo đối tượng tại điểm phê duyệt
~~~

Tại lần thực thi mới, cần kiểm tra dữ liệu trọng yếu vẫn khớp approval, các điều kiện hiệu lực theo policy và trạng thái còn cho phép thực thi. Không chỉ kiểm tra cờ `approved` của request.

Quy tắc phê duyệt được kiểm tra tại thời điểm nào phải rõ. Ví dụ hệ thống có thể yêu cầu checker có quyền khi duyệt và approval chưa bị thu hồi khi thực thi. Không tự suy rằng checker phải tiếp tục giữ nguyên role mãi sau một giao dịch đã hoàn tất.

## 3. Bốn lớp bằng chứng cần nối với nhau

| Lớp | Ví dụ bằng chứng | Điều có thể đánh giá | Giới hạn |
|---|---|---|---|
| Thiết kế | Policy, ma trận nhiệm vụ xung đột, scope, chủ sở hữu | Kiểm soát dự kiến bảo vệ điều gì | Chưa chứng minh có cưỡng chế |
| Triển khai | Guard phía server, state machine, schema, cấu hình quyền, phiên bản deploy | Cơ chế tồn tại và được cấu hình như thế nào | Chưa chứng minh toàn kỳ vận hành đúng |
| Kiểm thử | Ca tự duyệt, sửa giá sau duyệt, replay, tranh chấp và đường bypass | Cơ chế phản ứng với fixture cụ thể | Chưa bao phủ mọi giao dịch production |
| Vận hành | Quyết định, approval, kết quả commit, lịch sử quyền, đối soát, ngoại lệ | Các hoạt động trong phạm vi được kiểm tra | Phụ thuộc độ đầy đủ và độ tin cậy nguồn |

Một gói tốt có thể nối:

~~~text
Control ID + policy version
  → implementation/deployment version
  → test case và kết quả
  → population giao dịch trong kỳ
  → quyết định và tác động từng giao dịch
  → review, phát hiện, ngoại lệ và xử lý
~~~

Không suy diễn “có log” thành “kiểm soát có hiệu lực”. Cũng không xem một ca test pass là chứng minh mọi giao dịch trong tháng đều tuân thủ. Cần nói rõ bằng chứng hỗ trợ kết luận về thiết kế hay về vận hành, với phạm vi nào.

## 4. Ma trận rủi ro, cơ chế và bằng chứng

| Rủi ro logic | Cơ chế cần xem xét | Bằng chứng cần nối |
|---|---|---|
| Maker tự duyệt | SoD gate dựa trên danh tính đáng tin | Maker, checker, kết quả và reason từ phía server |
| Một người dùng hai account | Liên kết account với person theo policy | Nguồn và phiên bản liên kết danh tính, lịch sử hiệu lực |
| Duyệt chéo tenant | Authorization theo đối tượng | Tenant đã giải quyết, resource, scope quyền và quyết định |
| Sửa số tiền hoặc người nhận sau duyệt | Gắn approval với version và dữ liệu trọng yếu | Bản đã duyệt, thay đổi, quyết định hủy hiệu lực hoặc duyệt lại |
| Bỏ qua bước duyệt | State machine và guard cuối | Chuỗi chuyển trạng thái, approval tham chiếu khi thực thi |
| Retry gây tác động trùng | Idempotency và ràng buộc nghiệp vụ | Command fingerprint, operation ID, kết quả và liên kết tác động |
| Đổi role trước/sau giao dịch để che xung đột | Lưu quyết định và lịch sử quyền theo thời gian | Policy, grant snapshot/reference, sự kiện cấp/thu quyền |
| Admin sửa trực tiếp dữ liệu | Hạn chế đường quản trị và đối soát độc lập | Lịch sử thay đổi đặc quyền, đường thực thi, phát hiện thiếu quyết định |
| Sửa hoặc xóa audit | Bảo vệ nơi lưu và phân tách quyền quản trị | Kiểm soát truy cập, integrity check, lịch sử xuất và review |
| Dùng ngoại lệ như bypass thường xuyên | Workflow ngoại lệ có scope và thời hạn | Ai cho phép, lý do, giao dịch liên quan và kết quả hậu kiểm |

Một dòng log phía browser không đủ chứng minh server đã chặn hành động. HTTP 200 cũng không tự chứng minh một approval đã commit hoặc provider đã thực hiện tác động.

## 5. Danh tính: hai username chưa chắc là hai người

### 5.1. Phân biệt các loại chủ thể

| Khái niệm | Ví dụ | Vai trò trong bằng chứng |
|---|---|---|
| Principal xác thực | Account đăng nhập hoặc service credential | Ai đã được hệ thống xác thực |
| Con người chịu trách nhiệm | Person ID nội bộ đã giải quyết | So sánh tính độc lập khi policy yêu cầu hai người |
| Chủ thể được đại diện | Người mà support/admin đang thao tác thay | Nhận diện delegation hoặc impersonation |
| Service thực thi | Worker gửi lệnh hoàn tiền | Ai thực hiện bước kỹ thuật và dựa trên approval nào |

Person ID trong bài là định danh nội bộ có quản lý, không cần là số giấy tờ cá nhân. Nguồn mapping phải có thẩm quyền, được kiểm soát và đủ lịch sử để giải thích một quyết định trong quá khứ.

Không nhận `checkerPersonId` từ payload rồi dùng nó làm bằng chứng độc lập. Việc client khai một tên khác không thay đổi danh tính đã xác thực.

### 5.2. Delegation và impersonation

Nếu nhân viên hỗ trợ thao tác thay người dùng, bằng chứng cần giữ cả principal thực hiện và chủ thể được đại diện cùng căn cứ ủy quyền. Chỉ ghi `effectiveUser=checker-B` có thể che việc maker-A đang điều khiển phiên impersonation.

Policy phải xác định xung đột dựa trên những chủ thể nào. Ví dụ có thể cấm maker tự duyệt qua bất kỳ phiên đại diện nào mà chính họ điều khiển. Không chỉ đổi trường hiển thị để vượt phép so sánh hai ID.

### 5.3. Service account không tự tạo một người duyệt thứ hai

Một worker tự động thực thi sau phê duyệt là executor kỹ thuật. Nó không trở thành checker độc lập chỉ vì có account riêng.

Nếu có phê duyệt tự động dựa trên quy tắc, cần một policy riêng xác định trường hợp được phép và bằng chứng của quyết định tự động. Không đưa account bot vào báo cáo như một con người thứ hai đã xem xét yêu cầu.

Định danh dùng chung hoặc mapping thiếu lịch sử phải được ghi là giới hạn hoặc gap bằng chứng. Không suy ra tính độc lập từ tên role, địa chỉ email hoặc hai IP khác nhau.

## 6. Approval phải gắn với đúng nội dung và state machine

Giả sử maker trình yêu cầu version 3 với số tiền 500000 VND và tài khoản nhận đã token hóa là `beneficiary-X`. Checker duyệt đúng nội dung đó.

~~~text
REQUESTED(v3)
  → REVIEW_PENDING(v3)
  → APPROVED(v3, approval-A)
  → EXECUTION_PENDING(v3, approval-A)
  → EXECUTED(v3, approval-A, operation-K)
~~~

Nếu maker đổi số tiền thành 5000000 VND hoặc đổi người nhận, approval-A không tự áp dụng cho dữ liệu mới. Hệ thống cần chuyển sang trạng thái yêu cầu duyệt lại hoặc từ chối thay đổi theo hợp đồng.

### 6.1. Version và digest có vai trò khác nhau

- Version giúp nhận diện một trạng thái dữ liệu và kiểm soát cập nhật cạnh tranh.
- Digest của dữ liệu trọng yếu có thể hỗ trợ kiểm tra nội dung đã được duyệt có khớp nội dung thực thi không.
- Một reference tới bản snapshot được bảo vệ giúp người kiểm tra đọc lại nội dung thực tế đã duyệt.

Digest cần có quy tắc canonicalization, schema và tập field rõ ràng. Hash của một JSON bất kỳ không đủ nếu thứ tự trường, định dạng số hoặc các field bị bỏ sót làm thay đổi ý nghĩa so sánh. Hash cũng không thay thế quyền truy cập, lưu bản gốc cần thiết hoặc xác minh nguồn dữ liệu.

OWASP Transaction Authorization khuyến nghị kiểm soát thứ tự workflow, bảo vệ dữ liệu giao dịch khỏi thay đổi sai và có kiểm tra trước thực thi. Việc gắn approval với nội dung trong ví dụ là cách thiết kế để hỗ trợ những mục tiêu đó. [OWASP: Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

### 6.2. Bằng chứng cần tồn tại ở mỗi ranh giới

~~~text
Lúc trình duyệt:
  maker, đối tượng, tenant, version và snapshot dữ liệu trọng yếu.

Lúc phê duyệt:
  checker, quyền tại thời điểm quyết định, policy, dữ liệu đã xem xét,
  kết quả kiểm tra SoD và approval đã commit.

Lúc thực thi:
  approval được dùng, dữ liệu thực thi, operation/idempotency,
  guard cuối, trạng thái commit và kết quả tác động.
~~~

Không đặt timestamp phê duyệt vào một đối tượng rồi xem đó là chứng minh thứ tự. Cần chuyển trạng thái hợp lệ, liên kết quyết định và cơ chế lưu nhất quán.

## 7. Thiết kế record bằng chứng có thể giải thích được

Một record cần đủ dữ liệu để người có quyền trả lời: ai, làm gì, trên đối tượng nào, với policy nào, kết quả gì và bằng chứng đó đến từ đâu.

NIST SP 800-53 Rev. 5 có AU-3 về nội dung audit record và AU-9 về bảo vệ thông tin audit khỏi truy cập, sửa đổi, xóa trái phép. Đây là hai điểm tham chiếu bổ sung cho thiết kế bằng chứng dưới đây. [NIST SP 800-53 Rev. 5, AU-3 và AU-9](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-53r5.pdf#page=94).

### 7.1. Các nhóm field

| Nhóm | Field minh họa | Mục đích |
|---|---|---|
| Định danh | `eventId`, `decisionId`, `operationId`, `attemptId` | Phân biệt sự kiện, quyết định, thao tác và lần thử |
| Đối tượng | `tenantId`, `resourceType`, `resourceId`, `reviewedVersion` | Ngăn nối nhầm đối tượng hoặc phiên bản |
| Danh tính | Principal, person reference, maker reference, delegation reference | Xác định trách nhiệm và xung đột |
| Căn cứ quyền | Policy version, grant/authorization reference, identity binding reference | Giải thích quyền có hiệu lực khi quyết định |
| Kết quả | Rule ID, allow/deny, reason code, commit outcome | Phân biệt đánh giá với thay đổi thực tế |
| Nội dung | Snapshot reference, digest, digest schema | Gắn approval với dữ liệu trọng yếu |
| Thời gian/thứ tự | Thời điểm quyết định, commit, thu thập, aggregate sequence | Dựng lại trình tự với giới hạn đã biết |
| Nguồn | Service, deployment version, nguồn xuất | Đánh giá nguồn gốc và độ bao phủ |
| Ngoại lệ | Exception ID, scope, người cho phép, thời hạn | Giải thích nhánh xử lý khác policy thông thường |

Không phải mọi sự kiện đều có mọi field. Một lần thử bị từ chối vì chưa xác thực không có person ID đã xác minh; cần biểu diễn “chưa xác định” thay vì lấy tên client gửi để điền cho đủ.

### 7.2. Ví dụ sự kiện phê duyệt đã commit

Các giá trị sau là fixture minh họa:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-approval-81",
  "eventType": "REFUND_APPROVAL_COMMITTED",
  "controlId": "SOD-REFUND-01",
  "policyVersion": "policy-7",
  "decisionId": "decision-81",
  "tenantId": "tenant-T",
  "requestId": "refund-R",
  "reviewedVersion": 3,
  "makerPersonRef": "person-M",
  "checkerPrincipalRef": "account-C",
  "checkerPersonRef": "person-C",
  "identityBindingRef": "identity-binding-26",
  "authorizationRef": "authorization-81",
  "reviewSnapshotRef": "snapshot-R-v3",
  "controlOutcome": "ALLOW",
  "commitOutcome": "COMMITTED",
  "approvalId": "approval-A",
  "aggregateSequence": 8,
  "sourceService": "refund-service",
  "deploymentRef": "deployment-example-12"
}
~~~

Reference chỉ có ích nếu dữ liệu được tham chiếu còn tồn tại, có quyền truy cập phù hợp và có thể giải thích. Một ID trỏ tới bản ghi đã bị ghi đè bằng giá trị hiện tại không giữ được căn cứ lịch sử.

Thời gian được bổ sung theo hợp đồng của hệ thống. Đừng dùng số thứ tự của một aggregate để kết luận thứ tự toàn cục giữa các aggregate khác nhau.

### 7.3. Phân biệt các loại outcome

~~~text
APPROVAL_ATTEMPTED: có một lần thử, chưa chứng minh được phép.
SOD_DECISION_DENIED: guard từ chối, cần reason và căn cứ có thể ghi được.
SOD_EVALUATED_ALLOW: đánh giá cho phép, transaction vẫn có thể thất bại.
REFUND_APPROVAL_COMMITTED: approval đã được lưu bền vững.
REFUND_EXECUTION_COMMITTED: quyết định thực thi nội bộ đã commit.
PROVIDER_REFUND_CONFIRMED: có bằng chứng kết quả bên ngoài đã được kiểm tra.
~~~

Không dùng chung một event `SUCCESS` cho tất cả các giai đoạn. Commit ý định gửi không tương đương provider đã hoàn tiền thành công.

## 8. Bằng chứng phải nhất quán với transaction

### 8.1. Lưu approval và bằng chứng quyết định cùng ranh giới

Một luồng phê duyệt có thể được mô tả:

~~~text
Giải quyết danh tính, tenant và quyền theo nguồn đáng tin.
Bắt đầu transaction phù hợp.
Đọc request và version cần phê duyệt theo cơ chế đồng thời đã chọn.
Kiểm tra trạng thái, quyền đối tượng, SoD và nội dung trọng yếu.

Nếu được phép:
    Tạo approval gắn với reviewedVersion/snapshot.
    Ghi quyết định và bằng chứng commit cần thiết.
    Ghi outbox event cho việc chuyển bằng chứng sang nơi lưu khác.
    Commit nhất quán.

Nếu không được phép:
    Không chuyển request sang APPROVED.
    Ghi nhận lần từ chối qua đường bền vững phù hợp.
~~~

Đây là mã giả trách nhiệm. Cần hiện thực isolation, kiểm soát version và ràng buộc duy nhất để hai checker cạnh tranh hoặc request bị sửa đồng thời không tạo approval sai.

Transactional outbox giúp lưu ý định phát bằng chứng cùng dữ liệu nghiệp vụ khi chúng nằm trong cùng transaction được thiết kế đúng. Nó không tự chứng minh nơi lưu audit ngoài đã nhận, không loại bỏ giao lặp và không bảo vệ khỏi mọi người có quyền sửa database nguồn.

### 8.2. Audit của lần từ chối không được mất theo rollback

Nếu chỉ chèn record từ chối vào transaction rồi throw exception làm rollback, bằng chứng chặn tự phê duyệt có thể mất hoàn toàn.

Cần một đường ghi nhận phù hợp, chẳng hạn transaction riêng sau khi quyết định từ chối đã xác định, hoặc cơ chế audit bền vững độc lập. Thiết kế phải tránh ghi nhầm “đã chặn thành công” khi trạng thái nghiệp vụ thực tế chưa được xác minh.

Nếu audit lần từ chối gặp lỗi, quyết định từ chối vẫn không được biến thành allow. Đồng thời phát tín hiệu thiếu bằng chứng và xử lý theo hợp đồng vận hành. Đối với thao tác cho phép, nếu policy yêu cầu không được commit thiếu bằng chứng, lỗi ghi bằng chứng trong ranh giới đó phải ngăn commit; không âm thầm bỏ audit để tiếp tục.

### 8.3. Retry và giao lặp event

Phân biệt:

- `operationId`: thao tác nghiệp vụ được nhận diện xuyên retry.
- `attemptId`: từng lần gọi hoặc lần xử lý lại.
- `decisionId`: một quyết định kiểm soát được tạo ở điểm xác định.
- `eventId`: sự kiện được phát và có thể được giao nhiều lần.

Consumer bằng chứng cần chống ghi lặp theo hợp đồng event. Nhiều lần giao cùng event không có nghĩa có nhiều approval. Ngược lại, gộp mọi lần thử vào một dòng có thể làm mất lịch sử bị chặn hoặc các lần dùng payload khác.

Không đưa idempotency key thô vào mọi nơi nếu nó chứa dữ liệu nhạy cảm; có thể dùng reference nội bộ phù hợp. Bằng chứng cần đủ liên kết mà vẫn giữ giới hạn truy cập.

## 9. Ví dụ Java: tách kết quả SoD khỏi việc commit

Ví dụ Java 17 chỉ mô hình hóa quy tắc “hai con người khác nhau và checker có quyền theo đối tượng”. Application service phải cung cấp facts đã được giải quyết từ nguồn tin cậy; đây không phải DTO nhận trực tiếp từ client.

~~~java
import java.util.Objects;

final class SegregationGate {
    enum Outcome {
        ALLOW,
        DENY,
        INDETERMINATE
    }

    record Facts(
            String makerPersonId,
            String checkerPersonId,
            boolean checkerAuthorizedForObject,
            boolean identityBindingVerified,
            String policyVersion) {
        Facts {
            Objects.requireNonNull(policyVersion);
            if (policyVersion.isBlank()) {
                throw new IllegalArgumentException("policyVersion is blank");
            }
        }
    }

    record Decision(
            Outcome outcome,
            String reasonCode,
            String policyVersion) {}

    Decision evaluate(Facts facts) {
        Objects.requireNonNull(facts);

        if (!facts.identityBindingVerified()
                || facts.makerPersonId() == null
                || facts.makerPersonId().isBlank()
                || facts.checkerPersonId() == null
                || facts.checkerPersonId().isBlank()) {
            return new Decision(
                    Outcome.INDETERMINATE,
                    "IDENTITY_EVIDENCE_INSUFFICIENT",
                    facts.policyVersion());
        }

        if (!facts.checkerAuthorizedForObject()) {
            return new Decision(
                    Outcome.DENY,
                    "CHECKER_NOT_AUTHORIZED",
                    facts.policyVersion());
        }

        if (facts.makerPersonId().equals(facts.checkerPersonId())) {
            return new Decision(
                    Outcome.DENY,
                    "MAKER_CHECKER_CONFLICT",
                    facts.policyVersion());
        }

        return new Decision(
                Outcome.ALLOW,
                "DISTINCT_AUTHORIZED_CHECKER",
                facts.policyVersion());
    }
}
~~~

`identityBindingVerified` là kết quả của adapter tin cậy trong ví dụ. Một boolean do client gửi hoặc một adapter luôn trả true không có giá trị chứng minh. Cần giữ reference tới nguồn binding và quyết định authorization tương ứng.

`INDETERMINATE` khác một vi phạm đã được xác nhận. Với hợp đồng bài học, trạng thái đó không được phép tạo approval mới và phải được ghi nhận như thiếu căn cứ. Không báo người dùng gian lận chỉ vì dịch vụ danh tính tạm thời không trả được dữ liệu.

`ALLOW` ở gate chưa phải approval đã commit. Service phải gắn kết quả với request/version, kiểm tra các guard còn lại và ghi bằng chứng trong transaction phù hợp. Ví dụ chưa kiểm tra delegation, nhiều tầng duyệt hoặc tính độc lập theo đơn vị; những quy tắc đó cần facts và policy riêng.

## 10. Truy vấn phát hiện thiếu liên kết bằng chứng

Một báo cáo hữu ích bắt đầu từ population nghiệp vụ cần kiểm tra, rồi tìm bằng chứng tương ứng. Nếu chỉ bắt đầu từ bảng audit, giao dịch bị thiếu audit có thể biến mất khỏi báo cáo.

Giả sử có ba bảng minh họa:

- `refund_execution`: từng lần thực thi đã commit, gồm tenant, request/version, digest dữ liệu thực thi, approval ID và thời điểm commit.
- `refund_approval`: approval với dữ liệu đã duyệt, maker/checker person ID và quyết định SoD tham chiếu.
- `control_decision`: quyết định kiểm soát gồm tenant, control ID, policy version và outcome.

Các định danh ghép phải bao gồm tenant hoặc có ràng buộc toàn cục tương đương. Named parameter trong SQL dưới đây cần được lớp truy cập dữ liệu bind; đây là truy vấn minh họa, không phải script chạy trực tiếp cho mọi hệ quản trị.

Trong ví dụ, `request_version` là phiên bản nội dung nghiệp vụ đã được duyệt và mang sang execution. Số thứ tự chuyển trạng thái workflow được quản lý riêng; không so hai loại version có ngữ nghĩa khác nhau chỉ vì cùng là số nguyên.

~~~sql
SELECT
    e.tenant_id,
    e.execution_id,
    e.request_id,
    e.approval_id,
    a.sod_decision_id
FROM refund_execution e
LEFT JOIN refund_approval a
    ON a.tenant_id = e.tenant_id
   AND a.approval_id = e.approval_id
LEFT JOIN control_decision d
    ON d.tenant_id = a.tenant_id
   AND d.decision_id = a.sod_decision_id
WHERE e.tenant_id = :tenantId
  AND e.committed_at >= :periodStart
  AND e.committed_at < :periodEnd
  AND (
      a.approval_id IS NULL
      OR a.request_id IS NULL
      OR a.request_id <> e.request_id
      OR a.reviewed_version IS NULL
      OR e.request_version IS NULL
      OR a.reviewed_version <> e.request_version
      OR a.reviewed_digest IS NULL
      OR e.execution_digest IS NULL
      OR a.reviewed_digest <> e.execution_digest
      OR a.maker_person_id IS NULL
      OR a.checker_person_id IS NULL
      OR a.maker_person_id = a.checker_person_id
      OR d.decision_id IS NULL
      OR d.control_id IS NULL
      OR d.control_id <> 'SOD-REFUND-01'
      OR d.policy_version IS NULL
      OR d.outcome IS NULL
      OR d.outcome <> 'ALLOW'
  );
~~~

Giả định schema bắt buộc `e.request_id` có giá trị và khóa liên kết không tạo nhiều bản ghi không kiểm soát. Nếu dữ liệu cũ không đáp ứng, cần kiểm tra chất lượng dữ liệu riêng. Chuỗi rỗng, snapshot không đọc được hoặc reference không xác minh được cũng cần kiểm tra bổ sung; `IS NOT NULL` không chứng minh dữ liệu hợp lệ.

Kết quả là **ứng viên cần điều tra**: có thể là vi phạm, gap dữ liệu, sai logic join hoặc pipeline bằng chứng chưa hoàn tất. Truy vấn không chứng minh quyền của checker lúc duyệt, tình trạng thu hồi approval, delegation, ngoại lệ hợp lệ hay tác động bên provider. Cần đối chiếu các căn cứ đó trước khi kết luận.

Không có dòng trả về chỉ cho thấy các điều kiện của truy vấn không tìm thấy vấn đề trên population đã chọn. Nó không tự chứng minh mọi đường thực thi và mọi quy tắc SoD đều được bao phủ.

## 11. Tính đầy đủ và khả năng dựng lại lịch sử

### 11.1. Xác định population độc lập với log cần đánh giá

Ghi rõ:

~~~text
Đối tượng: giao dịch thực thi thuộc control SOD-REFUND-01.
Scope: tenant, môi trường và đường xử lý đã liệt kê.
Kỳ: [periodStart, periodEnd) theo mốc commit đã định nghĩa.
Nguồn population: dữ liệu nghiệp vụ hoặc ledger/nguồn đối soát có thẩm quyền.
Nguồn evidence: quyết định, approval, outbox, kho audit và lịch sử quyền.
Điểm chốt dữ liệu: snapshot/watermark và xử lý event đến muộn.
~~~

Một nguồn cùng database vẫn có thể là điểm bắt đầu hữu ích, nhưng chưa độc lập với mọi cách sửa/xóa dữ liệu. Nếu threat model gồm admin nguồn, cần đối soát thêm nguồn có quyền quản trị hoặc nguồn gốc độc lập phù hợp.

### 11.2. Tách các nhóm kết quả báo cáo

| Nhóm | Ý nghĩa |
|---|---|
| Đủ căn cứ, chưa phát hiện vi phạm trong phép kiểm tra | Liên kết và các điều kiện đã xét phù hợp |
| Vi phạm đã xác nhận | Bằng chứng đủ để kết luận trái policy trong scope |
| Ngoại lệ được chấp thuận | Có căn cứ ngoại lệ đúng scope và hiệu lực |
| Thiếu hoặc không tin cậy bằng chứng | Chưa đủ cơ sở để kết luận |
| Ngoài phạm vi | Có lý do loại trừ rõ ràng và số lượng được ghi nhận |

Đừng chuyển “thiếu bằng chứng” thành pass để báo cáo đạt 100%. Các nhóm phải có định nghĩa và cách tránh đếm trùng; tổng population cần được đối chiếu với nguồn đã chọn.

### 11.3. Không dùng trạng thái hiện tại thay lịch sử

Nếu checker bị thu quyền sau giao dịch, truy vấn role hiện tại có thể báo sai một quyết định trước đó. Ngược lại, cấp role sau giao dịch không làm quyết định cũ hợp lệ trở lại.

Cần policy version, quyền/binding có hiệu lực khi quyết định và những thay đổi liên quan. Tương tự, request hiện tại version 8 không thay thế snapshot version 3 đã được duyệt.

Timestamp từ nhiều nguồn không tự tạo thứ tự tuyệt đối. Phân biệt thời gian sự kiện, commit và ingestion; kết hợp sequence theo đối tượng, causal reference và chất lượng nguồn thời gian. Không dùng thời gian browser như căn cứ duy nhất cho thời điểm phê duyệt.

## 12. Bảo vệ độ tin cậy của bằng chứng

Bằng chứng cần xét nguồn gốc, khả năng bị thay đổi, tính đầy đủ, quyền truy cập và khả năng đọc lại. Mỗi cơ chế chỉ bảo vệ một phần của vấn đề.

| Biện pháp | Hỗ trợ điều gì | Giới hạn cần công bố |
|---|---|---|
| Quyền append có kiểm soát | Hạn chế ứng dụng sửa/xóa record qua đường thông thường | Superuser hoặc đường quản trị khác có thể vẫn tác động |
| Kho audit với quyền quản trị tách biệt | Giảm khả năng một người vừa thao tác vừa che dấu | Cần kiểm tra quyền thực tế, credential và đường truy cập dự phòng |
| Lưu giữ không cho sửa/xóa trong phạm vi đã cấu hình | Bảo vệ bản ghi sau khi được nhận và lưu | Không chứng minh nguồn gửi đủ hoặc nội dung ban đầu đúng |
| Hash và manifest | Phát hiện byte thay đổi khi có digest tham chiếu đáng tin | Kẻ có quyền thay cả file và manifest có thể tính lại hash |
| Chữ ký số và quản lý khóa phù hợp | Hỗ trợ xác minh nguồn ký và tính toàn vẹn | Không chứng minh người ký đã cưỡng chế SoD đúng; khóa bị lộ làm giảm bảo đảm |
| Đối soát với nguồn khác | Phát hiện thiếu liên kết hoặc chênh lệch | Nguồn đối soát cũng có giới hạn và độ trễ |
| Sao lưu và kiểm tra đọc lại | Giảm rủi ro mất hoặc không đọc được dữ liệu | Bản sao cũng cần scope, bảo mật và chính sách vòng đời |

Không gọi một bảng là “immutable” chỉ vì ứng dụng không có nút sửa. Cần nêu ai còn có quyền sửa/xóa, những thao tác đó được kiểm soát ra sao và có bằng chứng độc lập nào để phát hiện.

### 12.1. Phân tách cả quyền quản lý audit

Nếu người có thể tự cấp quyền checker cũng có thể xóa log cấp quyền và viết lại lịch sử approval, bằng chứng về phân tách bị suy yếu.

Xét quyền trên toàn chuỗi:

~~~text
Quản lý account và binding danh tính.
Cấp/thu quyền nghiệp vụ.
Sửa policy hoặc deploy code cưỡng chế.
Thay dữ liệu nghiệp vụ bằng công cụ đặc quyền.
Cấu hình collection, retention, export và khóa ký.
Đọc, sửa, xóa hoặc phục hồi bằng chứng.
~~~

Việc phân chia trách nhiệm cụ thể phụ thuộc mô hình tổ chức. Cần ghi các quyền còn tập trung và biện pháp giám sát/đối soát liên quan, thay vì chỉ đặt tên hai nhóm khác nhau.

### 12.2. Log injection, dữ liệu nhạy cảm và mức truy cập

OWASP Logging Cheat Sheet khuyến nghị xác định nguồn dữ liệu, xử lý dữ liệu từ trust zone khác, bảo vệ log và kiểm thử hành vi khi logging gặp lỗi. Bằng chứng SoD cũng cần những kiểm tra đó để record không bị giả mạo qua input hoặc làm lộ dữ liệu ngoài mục đích. [OWASP: Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Sử dụng schema có kiểu, giới hạn độ dài và encoding phù hợp. Một trường `reason` do client gửi không được tạo thêm record giả bằng ký tự xuống dòng. Không ghi password, access token, OTP hoặc toàn bộ thông tin tài khoản nhận tiền vào event chỉ để thuận tiện kiểm tra.

Reviewer chỉ được xem evidence thuộc scope được giao. Các lần đọc, xuất hoặc thay đổi quyền trên kho evidence cũng cần được quản lý và truy vết. Bản CSV đã xuất ra máy cá nhân không tự kế thừa quyền và vòng đời của kho nguồn.

### 12.3. Retention và khả năng đọc lại

Thời gian lưu và cách xử lý yêu cầu bảo toàn phải theo chính sách, nghĩa vụ áp dụng và phạm vi được tổ chức xác định. Bài học không đặt một số năm lưu mặc định cho mọi hệ thống.

Giữ được file chưa chắc đọc lại được quyết định: schema cũ, policy cũ, mapping danh tính và reference phụ thuộc có thể đã mất. Kế hoạch lưu giữ cần xét cả tài liệu giải thích schema, định dạng export, lịch sử khóa xác minh và các snapshot cần thiết.

Không giữ dữ liệu nhận diện vô thời hạn chỉ vì gọi nó là audit. Giảm dữ liệu không cần thiết, dùng reference hoặc pseudonymous ID phù hợp và kiểm soát khả năng liên kết lại danh tính theo mục đích được cho phép.

## 13. Xuất gói bằng chứng có thể tái kiểm tra

Một gói evidence cần giúp người kiểm tra hiểu phạm vi, dựng lại phép đối soát và nhận diện phần còn thiếu. Không chỉ gom ảnh chụp màn hình vào một thư mục.

### 13.1. Nội dung của gói minh họa

| Thành phần | Nội dung cần có |
|---|---|
| Mô tả kiểm soát | Control ID, mục tiêu, rule, scope, owner và phiên bản policy |
| Mô tả triển khai | Điểm cưỡng chế, phiên bản triển khai, đường đặc quyền và giới hạn |
| Population | Nguồn, kỳ, bộ lọc, số lượng, quy tắc bao gồm/loại trừ |
| Quyết định và tác động | Approval, execution, evidence reference và liên kết đối soát |
| Căn cứ lịch sử | Quyền, binding danh tính, snapshot đã duyệt, policy hiệu lực |
| Kiểm thử | Fixture, expected/actual, phiên bản và lớp được kiểm tra |
| Ngoại lệ và gap | Phân loại, bằng chứng, người chịu trách nhiệm và trạng thái xử lý |
| Kết quả review | Ai kiểm tra, kiểm tra gì, phát hiện nào và cách theo dõi |
| Manifest xuất | Thời điểm chốt, nguồn xuất, phiên bản truy vấn, checksum và quyền truy cập |

Nếu dùng lấy mẫu, ghi population, phương pháp chọn mẫu, cỡ mẫu, lý do chọn và giới hạn của kết luận. Không biến kết quả trên một mẫu thành khẳng định mọi giao dịch đều phù hợp.

### 13.2. Quy trình xuất

1. Chốt scope, khoảng thời gian và mốc dữ liệu nhất quán.
2. Xác định nguồn population và đối chiếu số lượng.
3. Chạy truy vấn/logic đã có phiên bản với parameter được ghi lại.
4. Nối bằng chứng, phân loại thiếu dữ liệu và xử lý event đến muộn.
5. Áp quyền và che bớt dữ liệu không cần thiết cho người nhận.
6. Tạo manifest mô tả nguồn, số lượng, phiên bản và digest thực tế của các file xuất.
7. Xác minh gói đọc được, liên kết quan trọng truy cập được và số lượng khớp.
8. Ghi người xuất, nơi lưu, người nhận, mục đích và kết quả review theo quy trình.

Đây là quy trình kỹ thuật minh họa. Việc các bằng chứng đó đủ cho một kỳ đánh giá cụ thể còn phụ thuộc tiêu chí kiểm soát và phương pháp đánh giá đã thống nhất.

### 13.3. Snapshot và event đến muộn

Nếu population được chốt lúc 10:00 nhưng bảng audit được đọc lúc 10:05 trong khi ingestion vẫn đang chạy, số lượng có thể thay đổi giữa hai phép đọc. Gói xuất cần mô tả điểm chốt, độ trễ chấp nhận và cách xử lý dữ liệu đến sau.

Không sửa lặng lẽ gói đã review. Nếu cần bổ sung, tạo phiên bản gói hoặc phụ lục có liên kết tới bản trước và lý do thay đổi. Hash của gói xác nhận byte đã xuất, không chứng minh population đầy đủ hay nội dung nghiệp vụ ban đầu đúng.

## 14. Ngoại lệ và kiểm soát bù

Một tổ chức có thể gặp tình huống cần xử lý khẩn cấp khi không có checker thông thường. Cơ chế ngoại lệ phải được định nghĩa trước theo thẩm quyền phù hợp; worker hoặc admin không tự đánh dấu “ngoại lệ hợp lệ” để làm báo cáo đẹp hơn.

Bằng chứng ngoại lệ nên giải thích:

~~~text
Exception ID và policy cho phép ngoại lệ.
Lý do, scope đối tượng/hành động và giới hạn hiệu lực.
Người yêu cầu, người cho phép và căn cứ quyền của họ.
Rule thông thường bị thay thế hoặc được nới theo cách nào.
Giao dịch đã sử dụng ngoại lệ.
Kiểm soát bù, người hậu kiểm, kết quả và hành động khắc phục.
~~~

### 14.1. Hậu kiểm không biến thành phê duyệt trước

Nếu một người đã tự thực hiện rồi ngày hôm sau người khác review, đó là kiểm soát phát hiện/hậu kiểm. Nó không chứng minh đã có checker độc lập trước tác động.

Báo cáo cần giữ đúng loại kiểm soát và thời điểm. Nếu policy không cho phép nhánh đó, một chữ ký hậu kiểm không tự hợp thức hóa vi phạm trong quá khứ.

### 14.2. Theo dõi ngoại lệ lặp lại

Nhiều ngoại lệ cùng người, cùng tenant hoặc cùng lý do có thể cho thấy kiểm soát đang bị dùng sai hoặc quy trình thiếu khả năng vận hành. Cần review xu hướng, điều kiện đóng ngoại lệ và tác động tới đánh giá kiểm soát.

Không xóa record từ chối trước đó khi một ngoại lệ được chấp thuận sau này. Giữ liên kết để giải thích đầy đủ: lần đầu bị chặn theo policy thông thường, lần sau được xử lý theo ngoại lệ nào.

## 15. Kiểm thử chất lượng kiểm soát và bằng chứng

Mỗi ca cần kiểm tra cả kết quả nghiệp vụ lẫn record được lưu. Test chỉ assert HTTP status không đủ cho bài toán này.

| Kịch bản | Kết quả nghiệp vụ | Bằng chứng cần kiểm tra |
|---|---|---|
| Maker tự duyệt bằng cùng account | Bị chặn | Reason xung đột, đúng request và không có approval commit |
| Maker dùng account thứ hai cùng person | Bị chặn theo hợp đồng hai người | Binding đáng tin cho thấy cùng person |
| Checker khác person, có quyền đúng đối tượng | Có thể duyệt nếu mọi guard khác đúng | Approval, decision, policy và reviewed version khớp |
| Checker thuộc tenant khác | Bị chặn | Scope đã giải quyết và reason authorization |
| Không xác minh được binding | Không tạo approval mới | Kết quả thiếu căn cứ, không ghi sai thành allow |
| Maker điều khiển phiên impersonation của checker | Theo rule delegation, không tự thoát SoD | Principal thực, subject đại diện và căn cứ delegation |
| Sửa số tiền/người nhận sau duyệt | Không thực thi với approval cũ | Version/digest mismatch và workflow duyệt lại |
| Hai checker cạnh tranh với một lần sửa request | Không commit approval cho dữ liệu ngoài bản đã duyệt | Version thắng, rollback/conflict và liên kết record đúng |
| Transaction approval rollback | Không có approval thành công giả | Phân biệt evaluation allow với commit thất bại |
| Audit record chèn trong transaction từ chối bị rollback | Lần từ chối vẫn có đường ghi phù hợp | Không mất dấu do rollback toàn bộ |
| Kho audit ngoài ngừng nhận | Theo hợp đồng lưu bền vững đã chọn | Outbox, độ trễ, cảnh báo và khả năng phát lại |
| Consumer nhận lại cùng event | Không nhân bản approval hoặc tác động | Event ID và cơ chế chống ghi lặp |
| Retry execution cùng command | Không hoàn tiền thêm lần nữa | Operation ID, payload fingerprint và cùng kết quả |
| Thu quyền checker sau giao dịch | Không đánh giá lịch sử bằng role hiện tại | Căn cứ quyền tại điểm quyết định |
| Cấp quyền checker sau giao dịch sai | Không làm quyết định cũ hợp lệ | Lịch sử hiệu lực chỉ ra thứ tự và gap |
| Dữ liệu nghiệp vụ có execution nhưng thiếu decision | Bị phát hiện trong đối soát | Bắt đầu từ population để tìm audit bị thiếu |
| Người đặc quyền sửa/xóa một record | Ngăn hoặc phát hiện theo thiết kế | Tín hiệu integrity, lịch sử quản trị hoặc nguồn đối soát |
| Xuất sai tenant hoặc thiếu dữ liệu cuối kỳ | Bị phát hiện, không giao gói sai scope | Bộ lọc, số lượng, watermark và quyền export |

Các test về cơ chế ghi và đối soát cần chạy ở lớp phù hợp: gate thuần, service/repository, pipeline hoặc môi trường tích hợp. Một test double của audit sink không chứng minh cấu hình quyền của kho production đúng.

### 15.1. Test không có bằng chứng giả sau rollback

~~~text
Dựng maker M và checker C độc lập, đúng quyền.
Cho guard SoD trả ALLOW.
Gây lỗi trước commit approval.
Đọc lại dữ liệu nghiệp vụ và evidence.

Expected:
  Không có approval ở trạng thái committed.
  Không có event thành công được công bố như đã commit.
  Nếu lưu evaluation attempt, trạng thái của nó không gây hiểu nhầm.
~~~

### 15.2. Test khả năng phát hiện record bị thiếu

Trong fixture tích hợp được phép chỉnh dữ liệu, tạo một execution thiếu liên kết approval hoặc decision. Chạy đúng logic báo cáo dự kiến dùng khi vận hành và xác nhận nó được đưa vào nhóm cần điều tra.

Ca này kiểm tra khả năng phát hiện gap, không phải bằng chứng rằng hệ thống cho phép tạo gap qua API. Kiểm thử cưỡng chế và kiểm thử đối soát có mục đích khác nhau nhưng cần nối kết quả trong gói evidence.

## 16. Tình huống xuyên suốt: từ tự duyệt bị chặn tới thực thi

Giả sử person-M có hai account, cả hai cùng được nguồn danh tính liên kết với một con người. Person-C là checker có quyền trên tenant-T.

| Bước | Hoạt động | Bằng chứng mong đợi |
|---|---|---|
| 1 | M tạo refund-R version 3 | Maker binding, tenant, dữ liệu trọng yếu và trạng thái |
| 2 | M dùng account thứ hai để duyệt R | Decision deny vì cùng person; không có approval commit |
| 3 | C duyệt version 3 | Decision allow, quyền đúng scope, snapshot và approval-A commit |
| 4 | M sửa số tiền tạo version nội dung 4 | Approval-A không còn dùng được cho nội dung mới |
| 5 | Worker thử thực thi version 4 bằng A | Bị chặn vì nội dung/version không khớp |
| 6 | C xem xét lại version 4 theo workflow | Approval-B gắn với nội dung mới và căn cứ quyền tương ứng |
| 7 | Worker thực thi với B, operation-K | Quyết định cuối, idempotency và bằng chứng tác động |
| 8 | Message operation-K được giao lại | Không có tác động thứ hai; giữ được lịch sử retry |

Khi review, cần nối các bước theo ID và phiên bản, không chỉ tìm một dòng “C đã duyệt refund-R”. Dòng đó có thể thuộc approval-A trong khi tác động thực tế dùng version 4.

Nếu bước 6 thiếu căn cứ quyền hoặc bước 7 không có evidence đủ tin cậy, kết quả là một gap hoặc phát hiện cần xử lý. Không suy ra các bước đều hợp lệ chỉ vì tổng số tiền cuối cùng trông hợp lý.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng ảnh danh sách role làm toàn bộ evidence | Không chứng minh phân tách trên giao dịch | Nối policy, quyết định, danh tính và tác động |
| Hai username được coi là hai người | Bỏ sót account thứ hai hoặc impersonation | Dùng binding theo đơn vị độc lập mà policy yêu cầu |
| Tin các field actor do client gửi | Bằng chứng có thể bị giả mạo | Giải quyết danh tính phía server và giữ nguồn tham chiếu |
| Chỉ ghi `approved=true` | Không biết ai duyệt nội dung nào | Gắn approval với snapshot/version và decision |
| Ghi allow trước commit như thành công | Có bằng chứng thành công giả sau rollback | Tách evaluation, commit và kết quả provider |
| Log từ chối nằm trong transaction bị rollback | Mất dấu kiểm soát đã chặn | Đường audit bền vững phù hợp cho denial |
| Báo cáo bắt đầu từ bảng audit | Giao dịch thiếu audit bị bỏ qua | Đối soát từ population nghiệp vụ |
| Dùng role hiện tại để xét giao dịch cũ | Kết luận sai khi quyền thay đổi | Giữ căn cứ hiệu lực tại điểm quyết định |
| Hash file rồi gọi là bằng chứng không thể sửa | Có thể thay cả file và hash | Bảo vệ digest tham chiếu, nguồn và quyền quản trị |
| Xem hậu kiểm là phê duyệt trước | Che sai trình tự kiểm soát | Ghi đúng loại kiểm soát và căn cứ ngoại lệ |
| Gộp missing evidence vào pass | Tạo mức bao phủ ảo | Báo riêng gap và theo dõi xử lý |
| Chỉ lấy mẫu rồi kết luận toàn bộ | Vượt phạm vi bằng chứng | Công bố phương pháp và giới hạn kết luận |

## 18. Bài tập thực hành

### Bài tập 1: Hợp đồng phân tách

Chọn một luồng hoàn tiền, thay đổi giá hoặc cấp quyền đặc biệt. Viết nhiệm vụ xung đột, scope, đơn vị danh tính cần độc lập, điểm kiểm tra và trường hợp ngoại lệ được phép.

### Bài tập 2: Thiết kế chuỗi bằng chứng

Tạo mẫu record cho một lần tự duyệt bị chặn, một approval đã commit và một execution. Chỉ ra field do server giải quyết, field tham chiếu dữ liệu lịch sử và field cần bảo vệ khỏi lộ dữ liệu.

### Bài tập 3: Phân tích thiếu căn cứ

Có một execution hợp lệ về số tiền nhưng không đọc được snapshot quyền của checker tại thời điểm duyệt. Phân loại kết quả, nêu điều chưa thể kết luận và nguồn nào có thể bổ sung căn cứ.

### Bài tập 4: Sửa truy vấn đối soát

Mở rộng truy vấn minh họa để kiểm tra approval bị thu hồi theo policy và ngoại lệ được phép. Viết rõ điểm quyết định, cách xử lý NULL, event đến muộn và lý do một dòng bị đưa vào nhóm điều tra.

### Bài tập 5: Xuất gói evidence

Với một kỳ kiểm tra tự chọn, lập danh mục nguồn, population, bộ lọc, policy version, lịch sử danh tính, kết quả kiểm thử, ngoại lệ và manifest. Nêu cách người review dựng lại cùng phép kiểm tra mà không có quyền sửa dữ liệu nguồn.

## 19. Tự kiểm tra bài làm

- Control ID, rule, scope và owner được định nghĩa rõ.
- Phân biệt SoD tĩnh và động theo đúng policy đang áp dụng.
- Danh tính độc lập được giải quyết từ nguồn có thẩm quyền.
- Có bằng chứng cho delegation, quyền theo đối tượng và policy lịch sử.
- Approval gắn với dữ liệu trọng yếu, version và tenant đúng.
- Evaluation, commit và tác động ngoài được phân biệt.
- Transaction, outbox, retry và audit denial không tạo khoảng trống bị bỏ qua.
- Population được xác định từ nguồn phù hợp và đối soát số lượng.
- Vi phạm, ngoại lệ, gap và ngoài phạm vi có cách phân loại rõ.
- Quyền sửa/xóa/export evidence và các giới hạn integrity được mô tả.
- Gói xuất có nguồn gốc, điểm chốt, phiên bản logic và khả năng đọc lại.
- Kết luận không vượt quá điều bằng chứng thực sự hỗ trợ.

Bằng chứng phân tách nhiệm vụ có giá trị khi nối được một quy tắc rõ ràng với quyết định đã cưỡng chế trên đúng giao dịch và kết quả bền vững. Việc thu thập phải đủ để giải thích, đối soát và phát hiện khoảng trống, đồng thời giữ đúng giới hạn về quyền, dữ liệu và phạm vi kết luận.
