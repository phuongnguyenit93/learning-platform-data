# Separation of duties

## 1. Phân tách nhiệm vụ là gì?

**Separation of duties**, viết tắt là **SoD**, là nguyên tắc phân chia các nhiệm vụ hoặc quyền có thể tạo xung đột để một chủ thể không tự kiểm soát toàn bộ một quy trình nhạy cảm.

Trong IAM, vấn đề không chỉ là người dùng có quyền hay không. Một người có thể được cấp những quyền hợp lệ riêng lẻ, nhưng khi kết hợp chúng lại thì có khả năng tự tạo, phê duyệt, thực thi và che giấu một thay đổi đặc quyền.

Ví dụ, Lan tạo yêu cầu cấp quyền quản trị production cho một tài khoản. Nếu Lan đồng thời được tự phê duyệt yêu cầu, gọi API cấp quyền và xóa audit của thao tác, toàn bộ vòng kiểm soát đều nằm trong tay một người. Việc mỗi endpoint đều kiểm tra “có role admin” chưa giải quyết được xung đột đó.

SoD đặt ra những ràng buộc như người tạo yêu cầu không tự duyệt yêu cầu của mình, người sửa chính sách không tự phát hành thay đổi nhạy cảm hoặc người quản trị quyền không tùy ý sửa dấu vết kiểm toán của chính mình.

Kiểm soát AC-5 của NIST nhấn mạnh việc xác định các nhiệm vụ cần phân tách và thiết kế quyền truy cập để hỗ trợ sự phân tách đó. [NIST SP 800-53 — AC-5, Separation of Duties](https://csrc.nist.gov/CSRC/media/Projects/risk-management/800-53%20Downloads/800-53r5/SP_800-53_v5_1-derived-OSCAL.pdf).

Mục tiêu của SoD là giảm khả năng lạm dụng đặc quyền và tạo cơ hội phát hiện sai sót trước khi thay đổi có hiệu lực. Nó không bảo đảm ngăn được mọi thông đồng giữa nhiều người hoặc mọi trường hợp các tài khoản liên quan cùng bị chiếm quyền.

## 2. SoD khác least privilege, MFA và audit như thế nào?

| Kiểm soát | Câu hỏi chính | Ví dụ trong IAM |
|---|---|---|
| Least privilege | Chủ thể thực sự cần những quyền nào? | Người hỗ trợ chỉ được khởi tạo quy trình phục hồi, không được đọc mọi dữ liệu |
| Separation of duties | Những nhiệm vụ nào không nên nằm trong cùng một chủ thể hoặc cùng một quyết định? | Người lập yêu cầu đặc quyền không được phê duyệt chính yêu cầu đó |
| MFA | Có đủ bằng chứng xác thực chủ thể theo yêu cầu không? | Xác thực bổ sung trước khi duyệt quyền production |
| Audit | Có thể biết ai đã làm gì, khi nào và trên đối tượng nào không? | Ghi người lập, người duyệt và workload thực thi |
| Access review | Quyền hiện có còn phù hợp không? | Rà soát các tổ hợp quyền gây xung đột theo thời gian |

Các kiểm soát này bổ sung cho nhau. Lan hoàn tất MFA vẫn có thể là người không được phép duyệt yêu cầu do chính Lan tạo. Ghi audit sau một hành động cũng không thay thế một ràng buộc cần chặn hành động trước khi thực hiện.

Least privilege giới hạn quyền của từng chủ thể theo nhu cầu. SoD bổ sung giới hạn về **tổ hợp quyền**, **vai trò trong quy trình** và **lịch sử hành động**. Một tập quyền có thể cần thiết cho công việc nói chung nhưng vẫn không được dùng để hoàn thành cả hai bước xung đột của cùng một yêu cầu.

## 3. Ba phạm vi ràng buộc thường gặp

### 3.1. Static separation of duties: ràng buộc khi gán vai trò

Với SoD tĩnh, hệ thống không cho cùng một chủ thể nhận một tổ hợp vai trò xung đột trong phạm vi được xác định.

Ví dụ, chính sách của một tổ chức quy định trong môi trường production:

```text
policy_editor và policy_release_approver là hai vai trò xung đột.
Một người không được đồng thời giữ cả hai vai trò trong phạm vi đó.
```

Việc kiểm tra cần diễn ra khi cấp role, thay đổi group, thay đổi role kế thừa hoặc cập nhật một mapping có thể tạo ra quyền tương đương. Nếu chỉ kiểm tra hai role được gán trực tiếp mà bỏ qua role kế thừa, xung đột vẫn có thể hình thành.

Phạm vi rất quan trọng. Tổ chức có thể cho phép một người là editor ở môi trường thử nghiệm và approver ở production nếu policy của họ cho phép. Không nên tự biến một xung đột theo một tài nguyên thành lệnh cấm toàn nền tảng, hoặc ngược lại bỏ qua phạm vi cần bảo vệ.

### 3.2. Dynamic separation of duties trong phiên RBAC

Trong mô hình RBAC, SoD động có thể ràng buộc các vai trò được kích hoạt trong một phiên: một người được gán nhiều vai trò nhưng không được kích hoạt những vai trò xung đột cùng lúc trong phiên đó. SoD tĩnh xét quan hệ gán vai trò; SoD động xét các vai trò đang hoạt động trong phiên. [NIST — Role Based Access Control FAQs](https://csrc.nist.gov/projects/role-based-access-control/faqs).

Ví dụ, một người được phân công cả vai trò vận hành và kiểm tra trong các công việc khác nhau, nhưng phải chọn vai trò phù hợp cho phiên hiện tại. Hệ thống không cho kích hoạt đồng thời tập vai trò bị policy cấm.

Tuy nhiên, ràng buộc ở cấp phiên không tự động ngăn một người tạo yêu cầu trong phiên A rồi đăng nhập phiên B để duyệt chính yêu cầu đó. Nếu yêu cầu nghiệp vụ là hai người độc lập tham gia, cần kiểm tra thêm lịch sử và danh tính ở cấp quy trình.

### 3.3. Phân tách người thực hiện theo yêu cầu hoặc giao dịch

Ở cấp workflow, một ràng buộc thường gặp là:

```text
Người phê duyệt của yêu cầu X phải khác người tạo yêu cầu X.
```

Đối với một thay đổi đặc quyền cao, policy còn có thể cấm người hưởng quyền phê duyệt hoặc yêu cầu nhiều người phê duyệt độc lập. Điều kiện này dựa trên dữ liệu của yêu cầu và lịch sử tham gia, không chỉ dựa trên role của phiên hiện tại.

Một người đổi role, mở trình duyệt khác hoặc tạo phiên mới vẫn là cùng người đối với ràng buộc đó. Đổi vai trò hiện tại không xóa việc họ đã tạo yêu cầu trước đây.

Trong tài liệu triển khai, cần nói rõ đang áp dụng SoD theo phép gán role, theo phiên hay theo workflow. Gọi chung là “đã có SoD” dễ che giấu việc kiểm soát mới bao phủ một trong các phạm vi này.

## 4. Maker-checker và số người phê duyệt

**Maker-checker** là cách tổ chức trong đó một bên chuẩn bị thay đổi và một bên khác kiểm tra, phê duyệt theo thẩm quyền. Luồng IAM có thể thêm bước thực thi bằng một workload được kiểm soát.

```text
Người lập yêu cầu
        ↓
Người phê duyệt độc lập
        ↓
Workload thực thi thay đổi đã được chấp thuận
        ↓
Ghi nhận kết quả và audit
```

Phải định nghĩa rõ số người và vai trò của từng người. Những nhãn như “hai người kiểm soát” hoặc “nhiều bước phê duyệt” không đủ chính xác để triển khai.

| Chính sách minh họa | Người lập | Người phê duyệt bắt buộc | Số người tối thiểu trong hai nhóm này |
|---|---|---|---|
| Không tự duyệt, một approver độc lập | Một người | Một người khác | Hai |
| Không tự duyệt, hai approver độc lập | Một người | Hai người khác nhau và khác người lập | Ba |
| Hai nhóm chuyên môn cùng duyệt | Một người | Một người thuộc nhóm A và một người thuộc nhóm B, với yêu cầu độc lập được định nghĩa rõ | Phụ thuộc policy; nếu phải là hai approver khác nhau thì tối thiểu ba |

Trong chính sách yêu cầu hai approver khác nhau, một người đồng thời thuộc cả hai nhóm không được tính thành hai người. Hai lần bấm duyệt của cùng một người cũng không tạo ra hai phê duyệt độc lập.

Người hưởng quyền có thể khác người lập yêu cầu. Nếu mục tiêu là tránh tự cấp đặc quyền, chỉ kiểm tra `approver != requester` có thể vẫn chưa đủ: người hưởng quyền có thể nhờ người khác lập hộ rồi tự duyệt. Với thao tác nhạy cảm, cần xác định rõ người hưởng quyền có bị loại khỏi tập approver hay không.

## 5. Thiết kế một yêu cầu cấp quyền có thể kiểm soát

Giả sử hệ thống cho phép yêu cầu quyền quản trị tạm thời trong một tenant. Một yêu cầu cần thể hiện đủ đối tượng và phạm vi để người duyệt biết chính xác mình đang chấp thuận điều gì.

```yaml
accessRequest:
  id: request-204
  version: 3
  tenantId: tenant-an-phu
  environment: production
  requesterPersonId: person-lan
  beneficiarySubjectId: user-minh
  beneficiaryPersonId: person-minh
  roleId: production_operator
  roleDefinitionVersion: 12
  resourceScope: service-document
  requestedExpiresAt: "2026-06-01T12:00:00Z"
  reason: Xu ly su co theo pham vi duoc giao
  state: SUBMITTED
```

Đây là dữ liệu minh họa, không phải schema tiêu chuẩn. Mốc thời gian, role và phạm vi được đặt ra cho ví dụ.

Những thuộc tính như requester, beneficiary, tenant, role, phiên bản định nghĩa role, tài nguyên và thời hạn phải đến từ các nguồn được xác minh hoặc được kiểm tra đúng thẩm quyền. Không chấp nhận việc client tự khai `requesterPersonId` để tránh điều kiện không tự duyệt.

### Phê duyệt phải gắn với đúng nội dung

Nếu Huy duyệt quyền đọc trong một giờ, sau đó yêu cầu bị đổi thành quyền quản trị trong một ngày, phê duyệt cũ không được tiếp tục dùng cho nội dung mới.

Một cách thiết kế là gắn approval với phiên bản yêu cầu và nội dung có ý nghĩa bảo mật. Khi thay đổi tenant, người hưởng quyền, role, phạm vi, thời hạn hoặc thông số quan trọng, hệ thống tạo phiên bản mới và yêu cầu phê duyệt lại theo policy.

Cũng cần xem xét phiên bản của role. Nếu giữ nguyên `roleId` nhưng thêm nhiều permission vào định nghĩa role sau khi phê duyệt, quyền được cấp có thể khác với quyền đã được kiểm tra. Hệ thống cần ràng buộc phiên bản hoặc đánh giá lại thay đổi đó trước khi thực thi.

Có thể dùng dấu vân tay nội dung để hỗ trợ phát hiện sự khác biệt, nhưng một hash do bên gọi tùy ý cung cấp không chứng minh tính hợp lệ của yêu cầu. Dữ liệu gốc, approval và cách tính hoặc xác minh dấu vân tay vẫn cần được bảo vệ khỏi sửa trái phép.

### Trạng thái yêu cầu phải có thứ tự

```text
DRAFT → SUBMITTED → APPROVED → EXECUTING → APPLIED
             ├── REJECTED
             ├── CANCELLED
             └── EXPIRED
```

Đây là một mô hình trạng thái minh họa. Có thể cần thêm trạng thái lỗi hoặc đang xác minh kết quả khi tích hợp hệ thống ngoài. Điểm cốt lõi là không được cấp quyền từ một bản nháp, yêu cầu đã hết hạn hoặc phiên bản chưa được phê duyệt.

## 6. Kiểm tra ở phía máy chủ và ngay lúc thực thi

Ẩn nút “Approve” đối với người tạo yêu cầu chỉ cải thiện giao diện. Người dùng vẫn có thể gọi API trực tiếp, vì vậy các ràng buộc phải nằm tại điểm thực thi phía máy chủ.

Ví dụ mã giả cho một bước phê duyệt:

```text
function approveAccessRequest(requestId, submittedVersion, authenticatedActor):
    actor = resolveTrustedActorAndPerson(authenticatedActor)

    transaction:
        accessRequest = loadRequestForUpdate(requestId)
        require accessRequest.state == SUBMITTED
        require accessRequest.version == submittedVersion
        require accessRequest.isNotExpired(serverTime)

        require actor.isActive
        require actor.canApprove(accessRequest.tenantId,
                                 accessRequest.environment,
                                 accessRequest.resourceScope)
        require actor.personId != accessRequest.requesterPersonId
        require actor.personId != accessRequest.beneficiaryPersonId
        require meetsAuthenticationConditions(actor, accessRequest)

        require noApprovalFromSamePersonForThisVersion(actor, accessRequest)
        saveApprovalBoundToRequestVersion(actor, accessRequest)

        if enoughEligibleDistinctApprovers(accessRequest):
            setState(accessRequest, APPROVED)

        persistAuditEventOrDurableOutbox()
```

Mã giả áp dụng một policy minh họa có cấm cả người lập lẫn người hưởng quyền duyệt. Nó chưa phải triển khai hoàn chỉnh và không quyết định số approver cho mọi loại yêu cầu.

Khi thực thi, cần tiếp tục xác minh yêu cầu vẫn đúng phiên bản, chưa hết hạn, các approval đáp ứng policy hiệu lực và quyền dự kiến không vượt giới hạn được phép cấp. Trong ví dụ này, người phê duyệt phải vẫn còn đủ tư cách theo policy tại thời điểm thực thi; nếu tư cách đã bị thu hồi, hệ thống yêu cầu đánh giá hoặc phê duyệt lại.

Approval không tự tạo quyền vượt ranh giới. Hai người duyệt một yêu cầu cấp role nền tảng trong tenant vẫn không làm yêu cầu đó hợp lệ nếu tenant không có thẩm quyền với role ấy.

### Đồng thời, đếm trùng và thực thi lặp

Hai yêu cầu API có thể cùng tới để ghi một approval hoặc cùng thực thi yêu cầu đã được duyệt. Cần kết hợp khóa hoặc kiểm tra phiên bản với các ràng buộc dữ liệu phù hợp.

Ví dụ, quan hệ duy nhất trên `(requestId, requestVersion, approverPersonId)` có thể ngăn việc cùng một người được đếm hai lần cho cùng phiên bản. Số approval cần tính theo những người đủ điều kiện, không phải theo số hàng hoặc số lần nhấn nút.

Việc thực thi cũng cần định danh thao tác để retry không cấp quyền lần hai hoặc vô tình gia hạn quyền thêm. Một retry của cùng yêu cầu nên giữ nguyên thời hạn đã được chấp thuận, thay vì tính lại “thêm hai giờ kể từ bây giờ”.

Nếu quyền được ghi ở một directory hoặc hệ thống bên ngoài, giao dịch cơ sở dữ liệu local không tự động bao phủ thao tác bên ngoài. Có thể cần một bản ghi ý định thực thi bền vững, xử lý idempotent và đối chiếu kết quả. Không đánh dấu `APPLIED` chỉ vì đã đưa lệnh vào hàng đợi khi chưa xác nhận thay đổi đích.

## 7. Một người, nhiều tài khoản và các đường cấp quyền gián tiếp

### 7.1. Hai tài khoản chưa chắc là hai người độc lập

Một người có thể sở hữu tài khoản thông thường và tài khoản quản trị. Nếu policy yêu cầu người duyệt khác người tạo, so sánh hai username có thể không đủ.

Hệ thống cần một cách liên kết đáng tin cậy giữa tài khoản và chủ thể mà policy muốn phân tách, chẳng hạn một định danh nhân sự nội bộ được quản lý. Không suy ra sự độc lập chỉ từ việc hai email hoặc hai account ID khác nhau.

Nếu có chức năng impersonation hoặc thao tác thay người dùng, cần giữ cả người thực hiện thật lẫn người được đại diện. Một người không được đổi ngữ cảnh hiển thị sang tài khoản khác rồi trở thành approver “độc lập” của yêu cầu do chính mình lập.

Tài khoản dùng chung làm suy yếu khả năng xác định người thực hiện và trách nhiệm cá nhân. Việc có hai credential dùng chung không đáp ứng ý nghĩa hai người độc lập nếu cùng một người có thể sử dụng cả hai.

### 7.2. Role kế thừa, nhóm và permission trực tiếp

Kiểm tra SoD cần bao phủ quyền hiệu lực, không chỉ tên role nhìn thấy ở một màn hình. Xung đột có thể xuất hiện qua:

- Role được gán trực tiếp.
- Role kế thừa từ một role khác.
- Nhóm lồng nhau hoặc mapping từ IdP.
- Permission gán trực tiếp ngoài luồng role chính.
- Thuộc tính ABAC mà người dùng được phép tự sửa.
- Quyền tạm thời hoặc ủy quyền từ người khác.

Ví dụ, Lan không được gán `policy_release_approver` trực tiếp, nhưng được thêm vào nhóm có ánh xạ sang role đó. Nếu kiểm tra xung đột chỉ chạy ở API gán role, đường thay đổi nhóm có thể bỏ qua ràng buộc.

Khi sửa định nghĩa role hoặc mapping, cần xem tác động lên các chủ thể hiện có. Một thay đổi role có thể tạo xung đột hàng loạt mà không cần có thêm thao tác gán role cho từng người.

### 7.3. SoD có thể trải qua nhiều hệ thống

Một người có thể lập yêu cầu ở cổng IAM, tự sửa dữ liệu approval qua công cụ quản trị khác hoặc gọi API directory ngoài workflow. Vì vậy, phạm vi kiểm soát phải xem xét các đường thực thi liên quan, không chỉ một ứng dụng riêng lẻ.

Nếu người tạo yêu cầu đồng thời có quyền sửa mã hoặc policy của chính workflow mà không có kiểm soát độc lập, họ có thể vô hiệu hóa điều kiện không tự duyệt. Quyền quản trị cơ chế SoD cũng cần được phân tách và theo dõi phù hợp.

## 8. Workload thực thi không mặc nhiên là approver thứ hai

Một workflow thường dùng service account hoặc workload identity để áp dụng quyền sau phê duyệt. Tự động hóa bước thực thi có thể giảm việc con người giữ credential đặc quyền thường trực.

Tuy nhiên, nếu Lan lập yêu cầu rồi một bot do Lan kiểm soát tự duyệt mọi yêu cầu của Lan, hệ thống chưa có một bước phê duyệt độc lập chỉ vì bot dùng account ID khác.

Nếu policy yêu cầu người duyệt độc lập, bot chỉ được thực thi kết quả phê duyệt hợp lệ. Nếu tổ chức cho phép phê duyệt tự động cho một loại quyền ít rủi ro, đó là một policy tự động hóa khác cần được định nghĩa rõ, không nên báo cáo như đã có hai người tham gia.

Workload thực thi cần quyền đủ hẹp để chỉ áp dụng yêu cầu đã được chấp thuận, trong tenant, catalog role, phạm vi và thời hạn được phép. Không cho người gọi tùy ý gửi một payload cấp quyền khác sau khi chỉ trình một request ID đã được duyệt.

Credential của workload và quyền thay đổi cấu hình workload cũng cần được bảo vệ. Nếu bất kỳ requester nào đều lấy được credential thực thi để gọi directory trực tiếp, workflow phê duyệt chỉ còn là một đường tùy chọn.

## 9. Ngoại lệ khẩn cấp và khả năng truy trách nhiệm

SoD có thể làm một thao tác chậm lại khi người duyệt không có mặt. Với hoạt động khẩn cấp, tổ chức có thể thiết kế một quy trình riêng, nhưng cần xác định rõ đây là ngoại lệ nào và ai được phép dùng.

Một ngoại lệ có kiểm soát có thể bao gồm phạm vi quyền hẹp, thời hạn bắt buộc, lý do, cảnh báo cho bên giám sát, audit được bảo vệ và hậu kiểm bởi người độc lập. Điều kiện cụ thể phụ thuộc hệ thống; không nên dùng một nút “emergency” để mọi requester tự mở quyền vô hạn.

Việc hậu kiểm sau sự cố không biến một hành động tự thực hiện thành phê duyệt trước hành động. Báo cáo cần phân biệt truy cập thông thường đã qua kiểm soát với truy cập theo ngoại lệ.

Audit cho luồng SoD thường cần liên kết được:

- Request ID, phiên bản và nội dung có ý nghĩa bảo mật.
- Người lập, người hưởng quyền, người duyệt thật và người được đại diện nếu có.
- Căn cứ thẩm quyền, điều kiện và thời điểm phê duyệt.
- Workload hoặc người thực thi cùng kết quả ở hệ thống đích.
- Lý do từ chối, thay đổi, hủy, hết hạn hoặc sử dụng ngoại lệ.

Người có quyền cấp đặc quyền không nên tùy ý sửa hoặc xóa dấu vết của quy trình đó. Dữ liệu audit cần được bảo vệ bằng quyền riêng và cơ chế lưu trữ phù hợp. Không ghi mật khẩu, token đầy đủ hoặc credential thực thi vào sự kiện audit.

Đối với thay đổi nhạy cảm, thiết kế cần tránh trường hợp ghi quyền thành công nhưng mất toàn bộ bằng chứng approval hoặc audit. Cơ chế giao dịch, outbox và đối chiếu hệ thống ngoài cần được lựa chọn theo kiến trúc thực tế.

## 10. Tình huống xuyên suốt: cấp quyền production tạm thời

Lan lập yêu cầu cấp role vận hành production cho Minh trong tenant An Phú. Chính sách của ví dụ yêu cầu hai approver khác nhau, trong đó có đại diện an ninh và chủ sở hữu tài nguyên. Người lập và người hưởng quyền không được duyệt.

Huy thuộc nhóm an ninh, Mai là chủ sở hữu tài nguyên. Một luồng hợp lệ có thể là:

1. Lan gửi yêu cầu với đúng Minh, tenant An Phú, role, phạm vi tài nguyên và thời hạn.
2. Huy đọc nội dung phiên bản hiện tại và phê duyệt trong phạm vi thẩm quyền.
3. Mai phê duyệt cùng phiên bản; hệ thống kiểm tra Mai khác Huy, Lan và Minh.
4. Workload kiểm tra lại trạng thái yêu cầu, tư cách phê duyệt và giới hạn cấp quyền trước khi thực thi.
5. Hệ thống xác nhận thay đổi đích, ghi kết quả và thu hồi quyền khi hết hạn theo cơ chế đã thiết kế.

Những biến thể dưới đây phải được xử lý đúng:

| Biến thể | Kết quả mong đợi |
|---|---|
| Lan dùng tài khoản quản trị khác của chính Lan để duyệt | Không được tính là người độc lập |
| Minh có quyền approve nhưng là người hưởng quyền | Bị từ chối theo policy của ví dụ |
| Huy thuộc cả hai nhóm và bấm duyệt hai lần | Chỉ có một người; chưa đủ hai approver |
| Lan đổi thời hạn hoặc role sau khi Huy duyệt | Phê duyệt cũ không dùng cho nội dung mới |
| Role giữ nguyên tên nhưng permission nhạy cảm được thêm vào | Kiểm tra phiên bản hoặc yêu cầu đánh giá lại trước khi cấp |
| Huy bị thu hồi tư cách duyệt trước lúc thực thi | Không thực thi dựa trên approval không còn đáp ứng policy ví dụ |
| Hai worker cùng nhận cùng một yêu cầu | Không tạo hai lần cấp quyền hoặc gia hạn ngoài nội dung đã duyệt |
| Người gọi thay tenant thành Bình Minh | Không sử dụng approval của An Phú cho tenant khác |

Trong luồng này, “đủ hai approval” chỉ là một phần điều kiện. Hệ thống còn cần xác nhận đúng hai người, đúng thẩm quyền, đúng nội dung, đúng phạm vi và đúng thời điểm.

## 11. Kiểm tra hiệu lực SoD trong vận hành

Kiểm tra nên bao gồm cả các đường được phép và các đường bị cấm, thay vì chỉ xác nhận nút duyệt có xuất hiện cho approver hay không.

Những trường hợp quan trọng gồm xung đột role trực tiếp và qua nhóm, kích hoạt role xung đột trong phiên, tự duyệt bằng phiên khác, tự duyệt qua tài khoản liên kết, sửa request sau approval, approval hết hạn, quyền approver bị thu hồi và xử lý nhiều yêu cầu đồng thời.

Cần kiểm tra cả các đường ngoài giao diện chính như API, CLI quản trị, import role, đồng bộ nhóm và tác vụ nền. Một đường cấp quyền trực tiếp bỏ qua workflow có thể làm mọi kiểm tra ở giao diện trở nên không đủ.

Các tín hiệu vận hành hữu ích gồm số tổ hợp quyền gây xung đột chưa được giải quyết, số ngoại lệ còn hiệu lực, thời gian quyền tạm thời tồn tại sau khi hết hạn và số thay đổi đích chưa đối chiếu được với yêu cầu đã phê duyệt.

SoD cũng cần được rà soát khi role, nhóm, tổ chức hoặc hệ thống tích hợp thay đổi. Một cấu hình từng không có xung đột có thể trở nên xung đột sau khi một nhóm được ánh xạ thêm quyền hoặc một role được mở rộng permission.

## 12. Câu hỏi tự kiểm tra

1. Vì sao MFA thành công không cho phép một người tự phê duyệt yêu cầu mà policy cấm họ duyệt?
2. SoD tĩnh, SoD theo vai trò hoạt động trong phiên và ràng buộc theo workflow khác nhau ở đâu?
3. Khi nào `approverAccountId != requesterAccountId` vẫn chưa đáp ứng yêu cầu hai người độc lập?
4. Approval cần gắn với những thông tin nào để tránh việc nội dung được cấp khác nội dung đã duyệt?
5. Vì sao service account thực thi và quyền sửa workflow cũng cần nằm trong phạm vi kiểm soát SoD?

Separation of duties phân chia quyền và trách nhiệm để một chủ thể không tự hoàn thành toàn bộ chuỗi hành động nhạy cảm. Hiệu lực của nó phụ thuộc vào danh tính đáng tin cậy, ràng buộc đúng phạm vi, lịch sử quy trình được bảo vệ và việc thực thi nhất quán qua mọi đường cấp quyền liên quan.
