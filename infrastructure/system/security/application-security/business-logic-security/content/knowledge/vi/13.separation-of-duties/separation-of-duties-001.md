# Duty separation principle: nguyên tắc phân tách nhiệm vụ

## 1. Mục tiêu bài học

Trong chương **Separation of Duties** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **phân tách nhiệm vụ** — Separation of Duties, viết tắt là **SoD** — là nguyên tắc không để một chủ thể tự kiểm soát toàn bộ các công đoạn xung đột của một nghiệp vụ nhạy cảm.

Ví dụ, người lập yêu cầu chi không được tự duyệt chính yêu cầu đó. Nếu nghiệp vụ yêu cầu một lớp kiểm soát tiếp theo, người phát lệnh chi có thể còn phải độc lập với cả người lập lẫn người duyệt.

Mục đích là tạo điểm kiểm tra có thẩm quyền và độc lập trước khi tiền, quyền truy cập, dữ liệu hoặc tài sản bị thay đổi. Việc đặt hai tên role hoặc hai nút bấm chưa đủ để tạo sự độc lập này.

Sau bài học, bạn có thể:

- Phân biệt SoD với quyền tối thiểu, nhiều bước xử lý và xác thực tăng cường.
- Chọn phạm vi phân tách phù hợp: khi cấp quyền, trong phiên làm việc hoặc theo lịch sử của một nghiệp vụ.
- Viết bất biến về người lập, người sửa, người duyệt và người thực thi.
- Bảo vệ quy tắc khỏi tài khoản phụ, ủy quyền, impersonation và các đường API khác nhau.
- Thực thi kiểm tra trong transaction, gắn quyết định với đúng revision và kiểm thử các cuộc đua liên quan.

## 2. Vì sao một người làm được mọi bước là rủi ro?

Xét quy trình:

~~~text
Tạo yêu cầu chi
    → xác minh nội dung
    → phê duyệt
    → phát lệnh thanh toán
~~~

Nếu cùng một người có thể tạo nội dung, xác nhận nội dung đó hợp lệ rồi phát lệnh chi, một sai sót hoặc tài khoản bị chiếm có thể tác động xuyên suốt quy trình mà không gặp kiểm tra độc lập.

Một số ví dụ:

| Nghiệp vụ | Nhiệm vụ có thể xung đột |
|---|---|
| Chi trả | Lập khoản chi và duyệt khoản chi đó |
| Quản lý nhà cung cấp | Đổi tài khoản nhận tiền và duyệt khoản trả sử dụng tài khoản vừa đổi |
| Cấp quyền | Xin quyền và tự phê duyệt cấp quyền |
| Hoàn tiền | Đề xuất hoàn tiền và duyệt hoàn cho giao dịch liên quan |
| Điều chỉnh tồn kho | Ghi giảm tồn và xác nhận điều chỉnh đó hợp lệ |
| Quản lý kiểm soát | Tự sửa chính sách duyệt rồi sử dụng phiên bản dễ hơn cho yêu cầu của mình |

Phân tách không bảo đảm người duyệt sẽ luôn phát hiện mọi vấn đề hoặc hai người không thông đồng. Nó giảm khả năng một chủ thể đơn lẻ tự hoàn tất chuỗi hành vi bị kiểm soát, đồng thời làm rõ trách nhiệm và bằng chứng.

Muốn người duyệt thực hiện kiểm tra có ý nghĩa, hệ thống còn phải cho họ thấy đúng nội dung, đúng thay đổi và đúng phạm vi mà họ đang chấp thuận.

## 3. Phân biệt SoD với các kiểm soát liên quan

| Kiểm soát | Câu hỏi chính | Vì sao chưa thay thế được SoD |
|---|---|---|
| Least privilege — quyền tối thiểu | Chủ thể cần những quyền nào để làm việc? | Một tập quyền nhỏ vẫn có thể chứa cả tạo và duyệt cùng đối tượng |
| Xác thực nhiều yếu tố | Người đăng nhập có chứng minh được danh tính không? | Cùng một người xác thực hai lần vẫn là một người |
| Workflow nhiều bước | Nghiệp vụ đi qua những trạng thái nào? | Cùng một chủ thể có thể đi hết mọi trạng thái |
| RBAC | Role nào được gọi hành động nào? | Một người có thể có nhiều role hoặc dùng nhiều tài khoản |
| Quyền theo đối tượng | Chủ thể có được tác động tới đối tượng này không? | Vẫn cần xét họ đã tham gia bước xung đột nào trên đối tượng |
| Dual control/four-eyes | Hành động có cần sự tham gia của hai người không? | Phải xác định hai người nào, làm nhiệm vụ gì và độc lập theo tiêu chí nào |
| SoD | Những nhiệm vụ nào không được cùng một chủ thể kiểm soát trong phạm vi đã chọn? | Cần kết hợp các kiểm soát trên để thực thi |

Dual control thường là một cách hiện thực hóa yêu cầu SoD, nhưng không phải mọi chính sách SoD đều có cùng cấu trúc “hai phiếu approve”.

Ví dụ, một người lập và một người duyệt độc lập đã tạo hai vai trò kiểm soát. Nếu chính sách yêu cầu thêm hai reviewer độc lập, tổng số người và điều kiện đếm phải được quy định riêng.

## 4. Xác định chủ thể độc lập

### 4.1. Hai userId chưa chắc là hai người

Giả sử Lan có:

~~~text
lan.employee → person-17
lan.finance  → person-17
~~~

Lan dùng tài khoản thứ nhất tạo yêu cầu, tài khoản thứ hai duyệt. Kiểm tra sau sẽ cho qua:

~~~java
if (!request.createdByUserId().equals(actor.userId())) {
    approve();
}
~~~

Nhưng nếu quy tắc là hai **người** khác nhau, cả hai tài khoản vẫn thuộc person-17.

Cần xác định đơn vị danh tính phù hợp với chính sách: thường là personId chuẩn được quản lý bởi nguồn danh tính có thẩm quyền. Không tự suy luận hai người khác nhau từ tên hiển thị, email hoặc việc họ đăng nhập trên hai thiết bị.

Quan hệ giữa account và person phải được lưu và quản lý đủ bền vững để còn giải thích được lịch sử khi tài khoản đổi tên, bị khóa hoặc nhân sự rời tổ chức.

### 4.2. Người đứng tên và người thực sự khởi tạo

Một API có thể được gọi bởi service account nhưng hành động được một nhân viên yêu cầu. Nếu chỉ ghi service-user vào createdBy, hệ thống có thể mất dấu người lập thực tế.

Cần phân biệt khi nghiệp vụ có các lớp này:

- Tài khoản đã xác thực.
- Người thực sự điều khiển thao tác.
- Danh tính có hiệu lực khi thao tác thay mặt.
- Nguồn thẩm quyền ủy quyền hoặc impersonation.
- Danh tính kỹ thuật của dịch vụ ghi dữ liệu.

Các trường này phải đến từ ngữ cảnh tin cậy và giao thức nội bộ được xác minh, không phải từ một header hoặc trường JSON do client tự khai.

Một tài khoản dịch vụ tự động ghi nhận yêu cầu không được mặc định coi là một người độc lập để đủ số lượng kiểm soát. Nếu có bước kiểm soát tự động được chính sách công nhận, phải mô hình hóa rõ ý nghĩa của bước đó.

### 4.3. Độc lập có thể mạnh hơn “khác người”

Tùy nghiệp vụ, hai người còn có thể phải:

- Khác bộ phận.
- Không nằm trong cùng quan hệ phê duyệt trực tiếp bị cấm.
- Không là người thụ hưởng hoặc có lợi ích liên quan.
- Đại diện cho hai nguồn thẩm quyền khác nhau.
- Không cùng tham gia tạo nội dung cần kiểm tra.

Không áp dụng mọi điều kiện này cho mọi hệ thống. Hãy chọn và ghi rõ tiêu chí độc lập mà nghiệp vụ thực sự yêu cầu.

## 5. Các phạm vi phân tách

### 5.1. Phân tách khi cấp quyền

**Static Separation of Duties** đặt ràng buộc ở bước phân quyền. Ví dụ:

~~~text
Một person không được đồng thời có role
PAYMENT_REQUESTER và PAYMENT_APPROVER
trong cùng phạm vi tổ chức bị kiểm soát.
~~~

Ưu điểm là hạn chế từ sớm việc tích lũy quyền xung đột. Hạn chế là có thể quá cứng nếu cùng một nhân viên cần lập yêu cầu của mình nhưng được duyệt yêu cầu của người khác.

Muốn thực thi đúng, cần xét các đường nhận quyền như role trực tiếp, role qua nhóm, role kế thừa và delegation. Chỉ chặn việc tick hai checkbox trực tiếp không bao phủ các đường còn lại.

### 5.2. Phân tách khi kích hoạt role trong phiên

Trong mô hình RBAC, **Dynamic Separation of Duties** có thể giới hạn những role được kích hoạt đồng thời trong một session, dù tài khoản có thể được gán nhiều role.

Ví dụ, một phiên không được đồng thời kích hoạt hai role xung đột.

Ràng buộc theo phiên không đủ để bảo vệ quy tắc “không tự duyệt yêu cầu đã lập”. Người dùng có thể tạo ở phiên trước, đăng xuất rồi duyệt ở phiên sau nếu hệ thống không kiểm tra lịch sử nghiệp vụ.

### 5.3. Phân tách theo đối tượng và lịch sử thao tác

Với logic nghiệp vụ, thường cần một ràng buộc như:

~~~text
Một person có thể lập yêu cầu A và duyệt yêu cầu B,
nhưng không được duyệt A nếu đã thực hiện nhiệm vụ
xung đột trên A hoặc ngữ cảnh nghiệp vụ được bảo vệ.
~~~

Đây là kiểm soát theo đối tượng/giao dịch và lịch sử tham gia. Nó có thể kết hợp với ràng buộc cấp quyền hoặc theo phiên, nhưng cần dữ liệu lịch sử riêng để thực thi.

Hãy mô tả phạm vi thay vì chỉ ghi “áp dụng dynamic SoD”. Phạm vi có thể là:

- Một request.
- Một revision hoặc một dòng nội dung cụ thể.
- Một hồ sơ nghiệp vụ chứa nhiều request.
- Một thay đổi thông tin nhà cung cấp và các khoản trả liên quan.
- Một kỳ đối soát hoặc một tài nguyên dùng chung.

Nếu chỉ kiểm tra requestId trong khi nhiệm vụ xung đột trải trên nhiều đối tượng liên quan, người dùng có thể tạo đối tượng mới để né kiểm soát.

### 5.4. Kết hợp có chọn lọc

Ví dụ một chính sách có thể:

- Cấm người quản trị quyền tự phê chuẩn việc cấp quyền cho mình.
- Cho phép nhân viên có cả quyền lập và quyền duyệt trong phạm vi được giao.
- Chặn duyệt nếu người đó là người lập hoặc người sửa nội dung trọng yếu của chính hồ sơ.
- Yêu cầu hai bộ phận độc lập cho khoản chi vượt một ngưỡng.

Sự kết hợp phải có chủ đích. Một rule cấp role không tự bao phủ lịch sử thao tác, và một rule trên request không tự ngăn việc quản trị viên tự nâng quyền.

## 6. Viết chính sách thành bất biến nghiệp vụ

Ví dụ sau dùng một hồ sơ chi trả với chính sách minh họa:

- Một người có thể được cấp cả quyền lập và quyền duyệt.
- Trong cùng hồ sơ nghiệp vụ, người tạo và mọi người sửa nội dung trọng yếu không được duyệt.
- Người thụ hưởng bị cấm duyệt khoản chi cho mình.
- Một người duyệt độc lập, đúng phạm vi và đủ hạn mức là đủ cho ví dụ cơ bản.
- Quyết định gắn với một revision; nội dung đã duyệt không được sửa trực tiếp.
- Thanh toán tự động sau phê duyệt không được tính là thêm một người kiểm soát độc lập.

Gọi:

~~~text
b       = ngữ cảnh hồ sơ nghiệp vụ được bảo vệ
r       = revision đang được xem xét
M(b)    = tập person đã tạo hoặc sửa nội dung trọng yếu của hồ sơ
A(b, r) = tập person có quyết định approve hợp lệ cho revision r
B(b, r) = tập person thụ hưởng bị cấm duyệt theo chính sách
~~~

Bất biến cốt lõi:

~~~text
M(b) ∩ A(b, r) = ∅
B(b, r) ∩ A(b, r) = ∅
~~~

Điều kiện thực thi còn cần:

~~~text
có đủ quyết định hợp lệ cho revision r
∧ revision được thực thi đúng là r
∧ request chưa bị hủy hoặc vô hiệu hóa
∧ các điều kiện nghiệp vụ khác vẫn được đáp ứng
~~~

SoD là một phần của hợp đồng, không thay thế kiểm tra số tiền, quyền theo đối tượng, trạng thái, hạn mức hoặc chống thực thi trùng.

### 6.1. Ai được tính vào tập người lập?

Chỉ so với createdBy có thể bỏ sót người sửa tài khoản nhận tiền, tăng số tiền hoặc thay đơn vị chịu chi.

Trong ví dụ, M(b) chứa:

- Người khởi tạo thực tế.
- Người thay đổi số tiền hoặc currency.
- Người thay người thụ hưởng hoặc thông tin nhận tiền.
- Người sửa dữ liệu trọng yếu khác được chính sách liệt kê.

Không nhất thiết mọi người thêm ghi chú hoặc sửa lỗi chính tả đều trở thành người lập. Cần xác định loại thay đổi nào tạo xung đột nhiệm vụ.

Chính sách ví dụ giữ lịch sử tham gia trọng yếu xuyên suốt các revision trong cùng hồ sơ. Tạo revision mới không xóa người đã tham gia. Nghiệp vụ khác có thể chọn phạm vi khác, nhưng phải chứng minh rằng cách reset phạm vi đó không tạo đường tự duyệt.

### 6.2. Dữ liệu tham gia phải do server ghi

Không nhận danh sách makers từ client để quyết định SoD. Một request có thể bỏ tên người tạo hoặc gửi personId giả.

Mỗi thao tác tạo/sửa trọng yếu cần ghi dấu tham gia cùng transaction với thay đổi nội dung. Có thể lưu:

~~~text
businessContextId
requestId, revision
personId, authenticatedAccountId
participationType
changedFieldCategory
occurredAt
delegationOrImpersonationContext
~~~

Dữ liệu này phải được bảo vệ khỏi các endpoint chỉnh sửa thông thường. Việc thay owner, chuyển người xử lý hoặc đổi createdBy hiển thị không được làm mất nguồn gốc thực tế.

Nếu cần sửa một sai sót về định danh, sử dụng quy trình hiệu chỉnh có thẩm quyền và dấu vết; không cho phép người dùng tự xóa bản ghi tham gia để trở thành reviewer.

### 6.3. Phạm vi phải ổn định qua các đường thao tác

Nếu các revision, bản sao hoặc request con thực chất thuộc cùng hồ sơ kiểm soát, cần liên kết với ngữ cảnh nghiệp vụ bền vững do server xác định.

Nếu người dùng chỉ cần clone request để có requestId mới và xóa lịch sử người lập, quy tắc theo requestId đã chọn sai phạm vi.

Không phải mọi giao dịch tương tự đều phải bị gộp. Việc xác định cùng hồ sơ cần dựa trên quan hệ nghiệp vụ rõ ràng, tránh vừa bỏ sót đường né tránh vừa chặn những giao dịch độc lập hợp lệ.

### 6.4. Hai người hay ba người là quyết định chính sách

Trong mô hình hai người:

~~~text
Maker M ──lập──> Hồ sơ
Checker A ──duyệt──> Hồ sơ
Worker ──thực thi quyết định đã duyệt──> Thanh toán
~~~

Worker tự động là cơ chế thực thi, không phải một người thứ ba.

Nếu cần thêm người phát lệnh độc lập, gọi tập người phát lệnh là E(b, r), có thể bổ sung:

~~~text
E(b, r) ∩ M(b) = ∅
E(b, r) ∩ A(b, r) = ∅
~~~

Khi đó phải có bước quyết định của một người phát lệnh đủ thẩm quyền. Thêm một service account khác để gửi API không đáp ứng yêu cầu ba người độc lập.

## 7. Ma trận quyền chỉ là lớp nền

Một ma trận đơn giản:

| Hành động | Người lập | Người duyệt | Người phát lệnh, nếu có | Worker |
|---|---|---|---|---|
| Tạo nội dung | Có quyền nền | Theo phân quyền | Theo phân quyền | Chỉ qua luồng được phép |
| Sửa nội dung trọng yếu | Có quyền nền, đúng trạng thái | Nếu sửa thì trở thành người tham gia xung đột | Tương tự nếu chính sách quy định | Ghi đúng nguồn khởi tạo |
| Duyệt | Không với hồ sơ mình tham gia | Có nếu độc lập và đủ thẩm quyền | Theo chính sách | Không giả lập quyết định con người |
| Phát lệnh thủ công | Theo chính sách | Theo chính sách | Có nếu đáp ứng SoD | Không áp dụng như người |
| Gửi thanh toán đã được cho phép | Không tự bỏ qua kiểm soát | Không tự bỏ qua kiểm soát | Không tự bỏ qua kiểm soát | Có theo trạng thái và bằng chứng |

Ma trận cho biết quyền nền. Quyền thực tế cần kết hợp:

~~~text
canApprove =
    basePermission
    ∧ objectScopeAllowed
    ∧ correctStateAndRevision
    ∧ authorityLimitAllowed
    ∧ notMaker
    ∧ notForbiddenBeneficiary
    ∧ remainingPolicyConditions
~~~

Không viết theo kiểu:

~~~text
có role APPROVER hoặc có role ADMIN thì luôn được duyệt
~~~

Một nhánh allow quá rộng có thể vô hiệu hóa toàn bộ điều kiện SoD. Trong chính sách thông thường của ví dụ, role quản trị không bỏ qua ràng buộc độc lập.

## 8. Thực thi nguyên tắc trong transaction

### 8.1. Các bước phải nhìn cùng một phiên bản nghiệp vụ

Luồng approve cần:

1. Xác thực actor và xác định danh tính chuẩn.
2. Đọc đúng tenant, đúng hồ sơ.
3. Bảo vệ revision, trạng thái và lịch sử tham gia khỏi thay đổi cạnh tranh.
4. Kiểm tra quyền nền, object scope và hạn mức.
5. Kiểm tra xung đột nhiệm vụ và người thụ hưởng.
6. Ghi quyết định gắn với nội dung đã xem.
7. Cập nhật trạng thái, audit và ý định bước tiếp theo trong cùng transaction.

Nếu đọc lịch sử tham gia rồi để một transaction khác sửa nội dung trước lúc commit approve, quyết định có thể được áp dụng cho dữ liệu mà người duyệt chưa được phép duyệt.

### 8.2. Java minh họa

Mã sau là phác thảo tầng ứng dụng với repository giả định. Nó minh họa một checker trực tiếp, chưa có bước người phát lệnh riêng.

Các giả định:

- Actor là người duyệt trực tiếp; luồng mẫu không chấp nhận service account hoặc impersonation để tạo quyết định con người.
- Mọi thao tác sửa nội dung và ghi participation dùng cùng giao thức khóa gốc hồ sơ.
- Các repository dùng cùng transaction; exception bắt buộc làm rollback.
- Không có lời gọi thanh toán bên ngoài trong transaction này.

~~~java
ApprovalResult approve(AuthenticatedActor actor, ApproveCommand cmd) {
    return transactions.required(() -> {
        access.requireDirectHumanApprovalSession(actor);
        var personId = identities.requireCanonicalPerson(actor);

        var request = requests.lockBusinessContextAndRequest(
                actor.tenantId(), cmd.requestId());

        access.requireCanApprove(actor, request);
        requireVersion(request, cmd.expectedVersion());
        requireRevision(request, cmd.expectedRevision());
        requireState(request, SUBMITTED);

        var policy = policies.requireApplicablePolicy(request);
        authority.requireApprovalLimit(personId, request, policy);

        var makers = participations.findMaterialContributors(
                request.businessContextId());
        duties.requireNotIn(personId, makers);
        duties.requireNotForbiddenBeneficiary(
                personId, request.approvalSnapshot(), policy);

        var decision = ApprovalDecision.approved(
                decisionIds.next(),
                request.id(),
                request.revision(),
                request.approvalSnapshotHash(),
                personId,
                policy.version(),
                clock.instant());

        decisions.insert(decision);
        request.markApproved(decision.id());
        requests.save(request);
        audit.insertApproval(actor, request, decision);
        outbox.insertApprovalGranted(request, decision);

        return ApprovalResult.from(request, decision);
    });
}
~~~

Các kiểm tra duties phải là validation bắt buộc, không dùng Java assert vì assertion có thể không được bật khi chạy.

Hash ràng buộc quyết định với snapshot; dữ liệu được hash phải có biểu diễn chuẩn và bao gồm các trường trọng yếu. Bản thân hash không thay cho việc đọc đúng revision hoặc kiểm tra thẩm quyền.

Unique constraint, state/version và quy tắc transaction cần ngăn tạo thêm quyết định cho cùng vị trí duyệt khi chính sách chỉ cho phép một. Nếu có nhiều slot, constraint phải phản ánh đúng mô hình đó thay vì cấm mọi quyết định thứ hai.

Ví dụ chưa trình bày receipt của idempotency. Khi API hỗ trợ gửi lại, cùng khóa và cùng nội dung phải trả kết quả đã lưu mà không ghi thêm quyết định; cùng khóa nhưng nội dung khác phải bị phát hiện. State check vẫn cần để hai khóa khác nhau không biến thành hai lần thực thi hợp lệ.

### 8.3. Luồng sửa phải tham gia cùng cơ chế bảo vệ

Chỉ khóa ở approve chưa đủ. Luồng sửa trọng yếu cũng phải:

~~~text
Khóa cùng gốc hồ sơ/request
    → kiểm tra version và trạng thái cho phép sửa
    → tạo revision mới nếu cần
    → ghi danh tính người sửa vào participation
    → cập nhật hiệu lực vòng duyệt theo chính sách
    → commit cùng thay đổi nội dung
~~~

Trong ví dụ, nội dung APPROVED không được sửa trực tiếp. Muốn thay đổi phải đi qua command mở lại/sửa đổi được kiểm soát trước khi bước thực thi khiến thay đổi không còn an toàn.

Không mở lại một khoản đã gửi thanh toán bằng cách đơn giản đổi trạng thái về DRAFT. Lúc đó cần xử lý cả hiệu ứng đã phát sinh.

### 8.4. Cuộc đua giữa sửa và duyệt

Giả sử Bình là reviewer, đồng thời cố sửa số tiền rồi approve bằng request khác.

Nếu sửa thắng:

~~~text
revision tăng
Bình được ghi vào tập người sửa trọng yếu
approve theo revision cũ bị từ chối
approve revision mới cũng bị từ chối theo SoD
~~~

Nếu approve thắng:

~~~text
quyết định gắn với revision đã duyệt
lệnh sửa thông thường không được ghi đè revision APPROVED
~~~

Hai command phải được tuần tự hóa hoặc một bên bị phát hiện xung đột. Việc cả hai cùng đọc trạng thái SUBMITTED rồi cùng ghi thành công trên dữ liệu cũ là dấu hiệu giao thức bảo vệ chưa đầy đủ.

## 9. Bảo vệ nguyên tắc trên mọi đường thực thi

### 9.1. Ẩn nút trên giao diện chưa đủ

Người dùng có thể gửi HTTP request trực tiếp, dùng client cũ hoặc gọi endpoint batch/import. Kiểm tra SoD phải nằm trong lớp xử lý nghiệp vụ mà các đường thực thi đều sử dụng.

Những nơi cần rà soát gồm:

- Endpoint tạo, sửa, submit, approve và execute.
- API hàng loạt hoặc import dữ liệu.
- Worker và scheduled job.
- Công cụ hỗ trợ khách hàng và trang quản trị.
- Luồng migration hoặc thao tác vận hành có quyền ghi.
- Tích hợp nội bộ gọi thay người dùng.

Không cần lặp lại cùng một đoạn kiểm tra ở mọi controller nếu đã có một command handler chung được bảo vệ đúng. Nhưng phải chứng minh không có đường ghi khác bỏ qua handler đó.

### 9.2. Ủy quyền không xóa xung đột

Giả sử Mai tạo yêu cầu. Reviewer Hùng ủy quyền cho Mai duyệt:

~~~text
Mai là maker.
Mai có delegation để thực hiện nhiệm vụ checker.
~~~

Nếu chính sách cấm maker duyệt, delegation không được biến Mai thành checker độc lập. Quyền được ủy quyền và điều kiện SoD phải cùng được đáp ứng.

Hai reviewer ủy quyền cho cùng một người cũng không mặc định tạo thành hai người kiểm soát. Nếu chính sách đòi hỏi nhiều nguồn thẩm quyền độc lập, phải xét thêm quan hệ nguồn ủy quyền, không chỉ người bấm nút.

Lưu người thực hiện thực tế, nguồn thẩm quyền và đối tượng được duyệt để quyết định có thể được đánh giá đúng.

### 9.3. Impersonation cần giữ dấu người điều khiển

Nhân viên hỗ trợ có thể đăng nhập thay người dùng theo một tính năng có kiểm soát. Nếu họ lập yêu cầu qua tài khoản A rồi duyệt bằng tài khoản riêng, hệ thống chỉ nhìn “effective user” có thể bỏ sót cùng một người điều khiển.

Có hai cách thiết kế theo chính sách:

- Không cho phép tạo quyết định phê duyệt trong phiên impersonation.
- Hỗ trợ nghiệp vụ thay mặt nhưng lưu đầy đủ danh tính thực tế và danh tính có hiệu lực, áp dụng kiểm tra xung đột lên các chủ thể liên quan.

Không cho client tự khai danh tính thực tế để né kiểm tra. Dữ liệu này phải được xác minh tại ranh giới xác thực và được truyền qua các dịch vụ bằng cơ chế tin cậy.

### 9.4. Không làm mất nguồn gốc qua service account

Một dịch vụ có thể xử lý lệnh do An khởi tạo:

~~~text
An → API → worker-service → bản ghi yêu cầu
~~~

Nếu business policy coi An là maker, bản ghi participation phải giữ được quan hệ đó. Chỉ lưu worker-service rồi cho An approve sẽ làm sai chính sách.

Với yêu cầu thực sự được tạo tự động, chẳng hạn theo lịch, cần định nghĩa:

- Thẩm quyền nào cho phép tạo yêu cầu.
- Ai được sửa cấu hình sinh yêu cầu.
- Những người nào bị cấm duyệt các yêu cầu liên quan.
- Có cần kiểm soát độc lập đối với thay đổi cấu hình hay không.

Không gán một người giả làm maker chỉ để đủ cấu trúc bảng; cũng không mặc định “do hệ thống tạo” là không có xung đột cần xem xét.

### 9.5. Thay người xử lý không thay lịch sử

Các thao tác sau không được tự xóa M(b):

~~~text
đổi owner
chuyển phòng ban xử lý
thay người được giao duyệt
hủy rồi mở lại round
tạo revision mới trong cùng hồ sơ
~~~

Nếu có chính sách thay đổi phạm vi xung đột, nó phải là một quyết định được quản lý và audit, không phải tác dụng phụ của việc cập nhật một trường hiển thị.

### 9.6. Phân tách có thể trải qua nhiều đối tượng

Ví dụ một người sửa bank account của nhà cung cấp rồi duyệt khoản trả. Request chi trả có thể do người khác tạo, nên kiểm tra createdBy của request vẫn cho qua.

Nếu chính sách coi hai nhiệm vụ đó xung đột, cần liên kết:

~~~text
payment request
    → beneficiary profile version
    → sự kiện thay đổi thông tin nhận tiền
    → người thực hiện thay đổi
~~~

Khi approve, kiểm tra lịch sử liên quan theo đúng phạm vi chính sách. Khi execute, sử dụng đúng snapshot/version thông tin nhận tiền được chấp thuận, không tự đọc “giá trị mới nhất” rồi chuyển tiền tới một tài khoản khác.

Hash hoặc snapshot bảo vệ nội dung được duyệt; điều kiện về người thay đổi thông tin mới bảo vệ phân tách nhiệm vụ. Hai lớp giải quyết hai câu hỏi khác nhau.

## 10. Thiếu người, ngoại lệ và quyền vận hành

### 10.1. Thiếu người độc lập không có nghĩa là được bỏ qua

Nếu không tìm được checker đủ điều kiện:

- Giữ yêu cầu ở trạng thái chờ hoặc cần hỗ trợ.
- Tìm người thay thế theo tuyến đã được chính sách cho phép.
- Kiểm tra lại phạm vi, hạn mức và sự độc lập của người thay.
- Không tự duyệt khi hết thời gian chờ.
- Không giảm số người chỉ vì một người có nhiều role.

Một chức danh cao hơn hoặc role ADMIN không tự giải quyết xung đột nhiệm vụ. Người đó vẫn có thể là maker hoặc người thụ hưởng.

### 10.2. Ngoại lệ phải được mô hình hóa rõ

Một số nghiệp vụ có thể cần cơ chế khẩn cấp. Nếu sản phẩm cho phép, cần định nghĩa riêng:

~~~text
Tình huống được dùng:
Ai được kích hoạt:
Phạm vi đối tượng và hạn mức:
Thời hạn:
Kiểm soát độc lập nào vẫn bắt buộc:
Bằng chứng và lý do:
Thông báo và rà soát sau sử dụng:
Cách thu hồi hiệu lực:
~~~

Nếu ngoại lệ thực sự cho phép một người làm các nhiệm vụ vốn xung đột, phải ghi nhận rằng mức kiểm soát đã được nới theo chính sách ngoại lệ. Audit sau đó không biến sự kiện thành một lần ngăn ngừa độc lập đã xảy ra trước khi thực thi.

Tránh một biến bỏ qua kiểm tra do client điều khiển hoặc một tài khoản đặc biệt có thể bỏ qua mọi rule mà không để lại bằng chứng.

### 10.3. Bảo vệ chính cơ chế kiểm soát

SoD ở ứng dụng không tự bảo vệ được trước chủ thể có toàn quyền sửa cả dữ liệu nghiệp vụ, chính sách và audit.

Tùy mô hình vận hành, cần giới hạn quyền ghi trực tiếp, quản lý việc sửa chính sách và bảo vệ log/audit khỏi người có thể tác động đến nghiệp vụ. Ví dụ người soạn chính sách không được tự phê chuẩn và áp dụng thay đổi làm giảm kiểm soát cho hồ sơ của mình.

Các thao tác vận hành hợp lệ cũng cần ghi rõ ai làm, lý do, đối tượng và phiên bản trước/sau. Một script “sửa nhanh” đặt APPROVED không được trở thành đường phê duyệt ngoài quy trình.

## 11. Kiểm thử các bất biến phân tách nhiệm vụ

Các ví dụ dưới đây là hướng dẫn xây dựng kiểm thử khi triển khai. Bài học không yêu cầu chạy một hệ thống hoàn chỉnh để hiểu nguyên tắc.

### 11.1. Ma trận tình huống

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Người có cả role maker và checker duyệt hồ sơ mình tạo | Bị từ chối theo SoD |
| Người đó duyệt hồ sơ độc lập của người khác | Có thể được chấp nhận nếu mọi quyền và điều kiện khác đều đúng |
| Maker đăng xuất rồi đăng nhập phiên mới để duyệt | Vẫn bị từ chối theo lịch sử nghiệp vụ |
| Maker dùng tài khoản thứ hai cùng personId | Không được coi là người độc lập |
| Người không tạo nhưng đã sửa số tiền hoặc tài khoản nhận | Bị từ chối nếu thuộc tập người sửa trọng yếu của chính sách |
| Chỉ thêm ghi chú không trọng yếu | Xử lý đúng phân loại thay đổi, không tự biến thành maker nếu chính sách không yêu cầu |
| Đổi owner hoặc createdBy hiển thị rồi approve | Không xóa được nguồn gốc xung đột |
| Tạo revision/clone trong cùng hồ sơ | Không tự mất lịch sử tham gia liên quan |
| Reviewer được ủy quyền chính là maker | Không có quyết định hợp lệ |
| Tạo qua worker rồi người khởi tạo approve | Kiểm tra đúng danh tính nguồn, không chỉ tài khoản dịch vụ |
| Approve qua phiên impersonation | Bị chặn hoặc kiểm tra đầy đủ theo chính sách đã chọn |
| Admin là maker và gọi endpoint approve | Không được bỏ qua SoD trong luồng thông thường |
| Gọi API thực thi trước khi đủ quyết định | Không tạo hiệu ứng nghiệp vụ |
| Sửa nội dung và approve đồng thời | Chỉ có thứ tự hợp lệ hoặc xung đột; không duyệt nhầm revision |
| Ghi quyết định thành công nhưng audit bắt buộc lỗi | Rollback cả quyết định và trạng thái |
| Retry sau mất response | Không tạo thêm quyết định hoặc lệnh chi trả |
| Thiếu checker độc lập | Chờ tuyến hợp lệ, không tự động thông qua |
| Người sửa bank profile duyệt khoản trả dùng version đó | Bị chặn nếu chính sách xác định đây là xung đột |

### 11.2. Một kiểm thử danh tính có sức phân biệt

Chuẩn bị:

~~~text
account-maker   → person-A
account-checker → person-A
independent-B   → person-B
~~~

Thực hiện:

1. Tạo hồ sơ bằng account-maker.
2. Đăng nhập bằng account-checker và gọi approve trực tiếp.
3. Kiểm tra bị từ chối, không có quyết định mới, trạng thái không đổi.
4. Đăng nhập bằng independent-B với quyền/phạm vi/hạn mức hợp lệ.
5. Approve cùng revision.
6. Đọc lại bằng transaction mới và kiểm tra quyết định thuộc person-B.

Kiểm thử này phát hiện lỗi so sánh userId trong khi đơn vị độc lập thực sự là personId.

Không chỉ kiểm tra HTTP status. Cần xác nhận cơ sở dữ liệu không có decision, outbox hoặc hiệu ứng nghiệp vụ của lần bị từ chối.

### 11.3. Kiểm thử người sửa trở thành checker

Chuẩn bị A tạo hồ sơ, B có quyền sửa và quyền duyệt, C là checker độc lập.

~~~text
A tạo revision 1.
B thay số tiền và tạo revision 2.
B cố duyệt revision 1.
B cố duyệt revision 2.
C duyệt revision 2.
~~~

Kết quả mong đợi:

- Duyệt revision 1 bị từ chối do dữ liệu cũ.
- B duyệt revision 2 bị từ chối do đã tham gia sửa trọng yếu.
- C có thể duyệt revision 2 nếu đủ mọi điều kiện.
- Quyết định cuối cùng gắn đúng số tiền và thông tin nhận tiền của revision 2.

### 11.4. Kiểm thử cạnh tranh

Dùng hai transaction/kết nối độc lập và điều phối để edit với approve cùng tranh chấp dữ liệu đang được bảo vệ.

Sau khi cả hai kết thúc, đọc lại:

~~~text
revision hiện tại
trạng thái hồ sơ
participation của người sửa
decision và snapshot được duyệt
outbox cho bước tiếp theo
~~~

Không được có trạng thái mà số tiền đã thay đổi nhưng quyết định vẫn được tính cho dữ liệu cũ, hoặc người sửa đã góp nội dung nhưng vẫn được tính là checker độc lập.

Kiểm thử transaction cần chạy trên cơ chế lưu trữ thực phù hợp. Chỉ mock repository rồi xác nhận hàm requireNotIn được gọi không chứng minh cuộc đua đã được chặn.

### 11.5. Kiểm thử chuỗi hành vi

Ngoài từng endpoint, thử các chuỗi:

~~~text
tạo → đổi owner → tự duyệt
tạo → chuyển role → tự duyệt
tạo → đăng xuất → tài khoản phụ → duyệt
tạo → hủy → mở lại cùng hồ sơ → tự duyệt
tạo → service cập nhật thay mặt → người khởi tạo duyệt
sửa bank profile → duyệt khoản trả liên quan
~~~

Sau mỗi hành động được chấp nhận, bất biến SoD phải vẫn đúng. Các bước đổi role, session hoặc owner có thể hợp lệ riêng lẻ nhưng không được làm mất lịch sử dùng để kiểm tra bước tiếp theo.

## 12. Audit để giải thích trách nhiệm và phát hiện đường né tránh

Audit nên giúp trả lời:

- Ai thực sự lập hoặc sửa nội dung trọng yếu?
- Danh tính tài khoản liên hệ với person nào tại thời điểm đó?
- Ai duyệt, qua nguồn quyền trực tiếp hay ủy quyền?
- Quyết định dựa trên revision, snapshot và policy version nào?
- Khi từ chối vì xung đột nhiệm vụ, điều kiện nào đã bị vi phạm?
- Có mở lại, thay người hoặc dùng ngoại lệ không?

Không ghi thông tin xác thực hoặc bí mật thanh toán chỉ để thuận tiện truy vết. Dấu vết cần đủ để chứng minh quyết định và được bảo vệ theo quyền truy cập phù hợp.

Có thể theo dõi những mẫu như liên tục tự duyệt bằng tài khoản khác, đổi owner trước approve, tập trung delegation về maker hoặc nhiều thao tác vận hành đặt trạng thái trực tiếp. Các dấu hiệu này cần được điều tra trong ngữ cảnh, không tự động chứng minh một người có ý đồ xấu.

## 13. Những câu hỏi cần chốt khi thiết kế

1. Những nhiệm vụ cụ thể nào xung đột?
2. Đơn vị độc lập là account, person, bộ phận hay nguồn thẩm quyền?
3. Phạm vi kiểm tra là session, request, revision hay một hồ sơ gồm nhiều đối tượng?
4. Ai được tính là người tham gia nội dung trọng yếu?
5. Lịch sử đó được ghi và bảo vệ cùng dữ liệu bằng cách nào?
6. Các luồng ủy quyền, impersonation, service account và vận hành giữ danh tính thực tế ra sao?
7. Quyết định được ràng buộc với nội dung nào và điều gì xảy ra khi nội dung đổi?
8. Làm sao edit, approve và execute không vượt qua nhau khi chạy đồng thời?
9. Thiếu người hoặc cần ngoại lệ thì trạng thái và mức kiểm soát được biểu diễn thế nào?
10. Những kiểm thử nào chứng minh quy tắc vẫn đúng khi đổi phiên, đổi tài khoản và đi qua endpoint khác?

Một chính sách phân tách nhiệm vụ có thể thực thi phải nêu rõ **ai không được kết hợp những nhiệm vụ nào, trên phạm vi nào và dựa trên lịch sử nào**. Sau đó, mọi đường thay đổi dữ liệu và thực thi nghiệp vụ phải giữ đúng ràng buộc ấy.
