# Delegated object access — Ủy quyền truy cập đối tượng an toàn

## 1. Cho người khác truy cập không đồng nghĩa trao quyền sở hữu

Giả sử nhân viên A sở hữu một hồ sơ chi phí và muốn nhờ B xem, bổ sung nhận xét trong hai ngày. B cần truy cập đúng hồ sơ đó, nhưng không vì thế được xem mọi hồ sơ của A, đổi người nhận tiền, duyệt chi hoặc chia sẻ tiếp cho người khác.

**Delegated object access** là cơ chế cho một chủ thể thực hiện một tập hành động có giới hạn trên một đối tượng mà họ không sở hữu, dựa trên sự ủy quyền được hệ thống công nhận.

Một thiết kế an toàn phải giữ được hai điều:

- Quyền sở hữu và trách nhiệm của đối tượng không bị thay đổi ngầm.
- Người nhận chỉ có đúng quyền, trên đúng đối tượng, trong đúng điều kiện được cấp.

Nếu chỉ truyền `ownerId` của A xuống backend hoặc cho B thao tác dưới danh tính A, hệ thống dễ mất dấu người thực sự làm việc và mở ra các đường vượt quyền nghiệp vụ.

Bài học sử dụng hồ sơ chi phí làm ví dụ, tập trung vào quyền theo đối tượng, nguồn ủy quyền, thời hạn, thu hồi, transaction, idempotency và kiểm thử các cách lạm dụng quyền được giao.

## 2. Phân biệt ủy quyền với các cơ chế gần giống

| Cơ chế | Ý nghĩa | Điều không tự có |
| --- | --- | --- |
| Quyền sở hữu | Quan hệ sở hữu hoặc quản lý đối tượng theo mô hình nghiệp vụ | Không mặc nhiên bỏ qua mọi điều kiện trạng thái và phân tách nhiệm vụ |
| Role trong một phạm vi | Năng lực theo nhiệm vụ, tenant hoặc đơn vị | Không tự là quyền trên mọi đối tượng có cùng loại |
| Chia sẻ hoặc ủy quyền đối tượng | Quyền hẹp trên đối tượng được nêu rõ | Không tự đổi chủ sở hữu hoặc cho chia sẻ tiếp |
| Thao tác thay danh tính | Một chủ thể làm việc trong ngữ cảnh danh tính khác theo cơ chế đặc biệt | Không được làm mất actor gốc hoặc giả thành người độc lập |
| Dịch vụ gọi thay người dùng | Service thực hiện một bước thay cho chủ thể được xác định | Quyền kỹ thuật của service không thay thế phạm vi người dùng |
| Link truy cập dạng bearer | Người giữ bí mật trong link có thể dùng quyền theo hợp đồng của link | Không chứng minh người dùng là người nhận cụ thể nếu link không ràng buộc danh tính |

Ví dụ trong bài dùng grant gắn với danh tính người nhận đã xác thực. Một grant ID bị đoán được hoặc bị lộ không đủ để người thứ ba truy cập.

Link chia sẻ ẩn danh là một mô hình khác, có giới hạn quy trách nhiệm và thu hồi riêng. Không áp dụng ngầm mô hình bearer cho một chức năng mà sản phẩm mô tả là chỉ chia sẻ với đồng nghiệp được chỉ định.

## 3. Mô hình nghiệp vụ xuyên suốt

Xét hồ sơ chi phí có:

```text
ExpenseReport = {
    tenant_id,
    report_id,
    owner_subject_id,
    owner_epoch,
    state,
    version
}
```

Hành động có thể gồm:

| Action | Ý nghĩa |
| --- | --- |
| `REPORT_READ` | Đọc những trường của hồ sơ được policy cho phép |
| `REPORT_COMMENT_ADD` | Thêm nhận xét khi trạng thái cho phép |
| `REPORT_ATTACHMENT_DOWNLOAD` | Tải chứng từ thuộc hồ sơ theo điều kiện riêng |
| `REPORT_EDIT_FINANCIAL_DATA` | Sửa dữ liệu tài chính |
| `REPORT_SUBMIT` | Gửi hồ sơ vào quy trình duyệt |
| `REPORT_APPROVE` | Ra quyết định phê duyệt |
| `REPORT_DELEGATE_ACCESS` | Tạo quyền truy cập đối tượng cho người khác |
| `REPORT_TRANSFER_OWNERSHIP` | Thay quan hệ sở hữu qua quy trình riêng |

Chính sách ủy quyền minh họa chỉ cho chia sẻ đọc và thêm nhận xét. Quyền tải chứng từ là lựa chọn riêng nếu được phép. Các hành động sửa dữ liệu tài chính, gửi duyệt, phê duyệt, chuyển chủ sở hữu và cấp lại quyền không tự đi kèm.

Ngay cả khi A là chủ sở hữu, A không được tự trao cho B một action mà chức năng chia sẻ không cho phép ủy quyền. Đọc được đối tượng cũng không đồng nghĩa được cấp quyền đọc đó cho người khác.

## 4. Một grant ủy quyền cần biểu diễn điều gì?

```text
ObjectDelegationGrant = {
    grant_id,
    tenant_id,
    resource_type,
    resource_id,
    owner_epoch,
    grantor_subject_id,
    grantee_subject_id,
    allowed_actions,
    not_before,
    not_after,
    lifecycle_state,
    version,
    parent_grant_id_if_supported,
    policy_revision
}
```

| Thành phần | Mục đích bảo vệ |
| --- | --- |
| Tenant và đối tượng có kiểu rõ ràng | Không dùng grant của nơi khác hoặc loại tài nguyên khác |
| Người cấp | Truy nguyên nguồn thẩm quyền và kiểm tra khả năng tiếp tục cấp quyền |
| Người nhận | Chặn người thứ ba dùng grant ID như mật khẩu |
| Tập action | Không biến quyền xem thành quyền sửa, duyệt hoặc chia sẻ |
| Khoảng thời gian | Giới hạn khi nào grant được dùng |
| Trạng thái và version | Hỗ trợ thu hồi và thay đổi có kiểm soát |
| `owner_epoch` | Làm mất hiệu lực quyền cũ khi quan hệ sở hữu thay đổi theo chính sách |
| Policy revision | Giải thích quy tắc đã áp dụng |

Thông tin người cấp phải lấy từ danh tính tin cậy và policy, không lấy nguyên `grantorId` trong request. Người nhận được server giải quyết thành một chủ thể hoặc membership có thẩm quyền, không chỉ là một chuỗi email chưa được xác minh.

### 4.1. Phạm vi một đối tượng phải giữ nguyên

Grant trên report R1 không tự áp dụng cho:

- Report R2 của cùng chủ sở hữu.
- Mọi report trong cùng dự án.
- Tài khoản của chủ sở hữu.
- Những dữ liệu liên quan nhưng có chính sách truy cập riêng.

Nếu cần chia sẻ một tập đối tượng hoặc cả dự án, hãy định nghĩa một loại scope riêng và quy tắc truyền quyền rõ ràng. Không tự mở rộng từ một report sang mọi đối tượng có cùng `owner_id`.

## 5. Điều kiện sử dụng grant phải được kiểm tra đầy đủ

Trong bài, chọn chính sách nguồn quyền còn sống: người cấp phải còn đủ thẩm quyền đối với action được ủy quyền ở thời điểm người nhận sử dụng.

Một điều kiện tổng quát:

```text
usable(grant, actor, report, action, t) =
    actor đã được xác thực
    AND actor là đúng grantee đã ràng buộc
    AND actor còn là chủ thể được phép hoạt động trong tenant
    AND grant.tenant_id == report.tenant_id == active_tenant
    AND grant.resource_type == EXPENSE_REPORT
    AND grant.resource_id == report.id
    AND grant.lifecycle_state == ACTIVE
    AND grant.not_before <= t < grant.not_after
    AND grant.owner_epoch == report.owner_epoch
    AND action thuộc grant.allowed_actions
    AND action vẫn thuộc tập được phép ủy quyền theo policy
    AND grantor còn đủ thẩm quyền cấp action đó trên report
    AND không có điều kiện cấm hoặc xung đột bắt buộc
```

Ngoài điều kiện về nguồn quyền, action còn phải hợp lệ với trạng thái và dữ liệu hiện tại. Một grant thêm nhận xét còn hạn không cho phép thêm nhận xét sau khi hồ sơ đã khóa bình luận.

### 5.1. Chọn rõ chính sách sống hay snapshot

Không phải mọi hệ thống đều dùng cùng chính sách cho người cấp:

| Chính sách | Ý nghĩa | Điều phải thiết kế thêm |
| --- | --- | --- |
| Nguồn quyền còn sống | Grant phụ thuộc quyền hiện tại của người cấp | Kiểm tra, độ mới dữ liệu và cách thu hồi khi nguồn thay đổi |
| Ủy quyền độc lập sau khi cấp | Grant có thẩm quyền riêng đến khi hết hạn hoặc bị thu hồi theo hợp đồng | Điều kiện ai được cấp loại quyền này, phạm vi, audit và cơ chế thu hồi riêng |

Không được kiểm tra quyền người cấp lúc tạo grant rồi tuyên bố tự động thu hồi theo người cấp nếu đường sử dụng không có cơ chế thực thi điều đó.

Ví dụ của bài dùng chính sách thứ nhất. Những giới hạn nhất quán với nguồn IAM bên ngoài phải được nêu đúng; một annotation transaction không làm dữ liệu quyền ở hai hệ thống tự đồng bộ tức thời.

## 6. Tạo ủy quyền: chủ sở hữu cũng có giới hạn

Quá trình tạo grant cần kiểm tra:

1. Người gọi được phép cấp truy cập trên đúng report.
2. Người nhận thuộc loại chủ thể và tenant mà chính sách cho phép.
3. Mọi action yêu cầu đều nằm trong tập được phép ủy quyền.
4. Người cấp có nguồn quyền cần thiết theo chính sách, không chỉ quyền xem.
5. Khoảng thời gian hợp lệ và không vượt giới hạn được phép.
6. Các giới hạn trường dữ liệu, chứng từ hoặc điều kiện bổ sung được xác định rõ.
7. Không có rule cấm chia sẻ hoặc yêu cầu phê duyệt chưa được đáp ứng.
8. Grant, audit và outbox bắt buộc được ghi cùng transaction cục bộ.

Một yêu cầu minh họa:

```http
POST /expense-reports/report-123/access-delegations
Authorization: Bearer <access-token>
Idempotency-Key: 5c54910c-4d67-44be-b984-d2a973e37afe
Content-Type: application/json

{
  "granteeMembershipId": "member-456",
  "actions": ["REPORT_READ", "REPORT_COMMENT_ADD"],
  "notAfter": "2026-12-03T09:00:00Z",
  "expectedReportVersion": 18,
  "reason": "Nhờ rà soát chứng từ trước khi gửi duyệt"
}
```

Server tự quyết định tenant, người cấp, thời điểm ghi nhận, `owner_epoch` và trạng thái ban đầu. Deadline do client đề nghị phải được kiểm tra theo policy; nó không tự có thẩm quyền.

Nếu request đòi thêm `REPORT_APPROVE` hoặc `canRedelegate=true` mà hợp đồng không hỗ trợ, không được âm thầm mở quyền. Có thể từ chối yêu cầu vượt phạm vi để người gọi biết chính xác điều gì chưa được cấp.

### 6.1. Không dùng mass assignment cho grant

Không map trực tiếp JSON vào entity có các trường như trạng thái thu hồi, người cấp, tenant, parent grant hoặc owner epoch. DTO tạo grant chỉ chứa những trường người dùng được đề nghị; server tính các trường bảo mật từ nguồn có thẩm quyền.

## 7. Ủy quyền tiếp không được mặc định tồn tại

Trong phiên bản đơn giản của ví dụ, người nhận không được chia sẻ tiếp chỉ nhờ grant đã nhận. B có quyền đọc report của A không có nghĩa B có quyền tạo grant cho C.

Nếu B có một nguồn thẩm quyền chia sẻ độc lập được policy công nhận, nguồn đó phải được đánh giá riêng. Không dùng quyền đọc được ủy quyền làm bằng chứng cho quyền cấp lại.

### 7.1. Nếu hỗ trợ chuỗi ủy quyền

Một thiết kế chuỗi cần ít nhất các điều kiện:

```text
action_con là tập con của action_cha
scope_con không rộng hơn scope_cha
khoảng_hiệu_lực_con nằm trong khoảng được cha cho phép
cha cho phép ủy quyền tiếp
mọi grant tổ tiên bắt buộc vẫn hợp lệ theo hợp đồng
chuỗi không có chu trình và không vượt độ sâu được hỗ trợ
```

Thu hồi cha phải có cách làm quyền con mất khả năng sử dụng theo chính sách đã chọn. Không chỉ đánh dấu cha mà để đường kiểm tra quyền con bỏ qua tổ tiên.

Không cho client tự trỏ `parentGrantId` vào một grant không thuộc quyền của họ hoặc đổi cha sau khi tạo để làm như có nguồn hợp lệ.

Chuỗi phải giữ actor thực sự, người khởi tạo và nguồn thẩm quyền cần thiết. Đi qua nhiều người hoặc nhiều service không làm một giao dịch trở thành có hai người độc lập nếu chính sách vẫn coi cùng chủ thể chịu trách nhiệm.

## 8. Danh tính thật phải được giữ khi người nhận thao tác

Nếu B thêm nhận xét dựa trên grant của A, bản ghi phải thể hiện B là người viết. Không gán `created_by=A` chỉ vì A là chủ sở hữu hoặc người cấp.

Một sự kiện có thể giữ:

```text
actor_subject = B
grantor_subject = A
access_source = DELEGATION
grant_id = G
report_id = R
tenant_id = T
```

Với service gọi thay, có thể cần thêm service principal và chủ thể khởi tạo. Không dùng một tài khoản `system` chung làm mất toàn bộ chuỗi quy trách nhiệm.

### 8.1. Bảo vệ phân tách nhiệm vụ

Nếu một phiên bản sản phẩm cho phép người nhận sửa dữ liệu tài chính, lịch sử cần ghi chủ thể thực sự sửa và những trách nhiệm liên quan theo policy. Không giả thành chủ sở hữu để né rule maker-checker hoặc để đổ trách nhiệm sang người cấp.

Ngược lại, việc A cấp quyền không mặc nhiên có nghĩa mọi hành động sau đó của B đều được coi là A thực hiện. Chính sách phải xác định rõ ai là chủ thể xung đột cho từng nghiệp vụ, không suy luận tùy ý chỉ từ một trường tên người sở hữu.

Hai tài khoản của cùng một người cũng không tự tạo hai chủ thể độc lập. Việc đối chiếu cần dựa trên danh tính chuẩn hóa hoặc quan hệ danh tính được hệ thống tin cậy.

## 9. Kiểm tra đối tượng con, trường dữ liệu và đường truy cập phụ

### 9.1. Chứng từ phải thực sự thuộc report được chia sẻ

Ví dụ endpoint:

```text
GET /expense-reports/R1/attachments/A1
```

Không đủ để kiểm tra người dùng được đọc R1 rồi tải A1 bằng ID toàn cục. Phải kiểm tra A1 thuộc R1, cùng tenant và action tải chứng từ được phép theo policy.

Thay A1 bằng chứng từ của R2 không được biến quyền R1 thành quyền R2.

### 9.2. Quyền đọc hồ sơ không tự mở mọi trường liên quan

Một report có thể tham chiếu tài khoản nhận tiền, thông tin nhân sự hoặc dữ liệu nhà cung cấp. Quyền đọc report chỉ cho phép biểu diễn dữ liệu mà hợp đồng chia sẻ cho phép.

Không trả toàn bộ entity và các quan hệ lồng nhau rồi chỉ ẩn trường trên giao diện. Bộ lọc trường và kiểm tra dữ liệu liên quan phải ở server.

### 9.3. Search, export và link tải cũng cần kiểm tra

Quyền đọc qua API chính không đủ nếu endpoint tìm kiếm, export hoặc dịch vụ ký URL tải dùng một mô hình yếu hơn.

Một URL tải có thời hạn có thể cho tiếp tục truy cập đến khi hết hạn theo hợp đồng của cơ chế đó. Nếu yêu cầu thu hồi ngay, cần khả năng kiểm soát tương ứng ở đường tải; không hứa thu hồi sớm chỉ bằng việc sửa grant trong cơ sở dữ liệu nếu URL đã phát hành vẫn hoạt động độc lập.

## 10. Ví dụ Java: dùng grant để thêm nhận xét

### 10.1. Giả định và thứ tự đồng bộ

Ví dụ dùng Spring transaction và dữ liệu cục bộ cho report, grant, membership, quyền cần thiết, audit và outbox.

Để diễn đạt chính sách nguồn quyền còn sống:

- Đường sử dụng lấy một guard quyết định quyền của tenant trước khi đọc snapshot quyền cục bộ.
- Thay đổi membership hoặc quyền nguồn có giao thức khóa tương thích để không đổi dữ liệu đã được bảo vệ giữa lúc kiểm tra và commit.
- Sau guard quyền, thao tác khóa report rồi grant theo thứ tự cố định.
- Tạo, thu hồi grant, đổi chủ sở hữu và thay trạng thái liên quan tuân theo giao thức tương ứng.
- Không gọi IAM hoặc dịch vụ ngoài trong khi giữ transaction này.

Guard có thể được thiết kế bằng khóa đọc và ghi hoặc cơ chế phiên bản phù hợp. Ví dụ không yêu cầu mọi lần đọc dữ liệu đều phải dùng cùng một kiểu khóa, nhưng một cơ chế khác phải xác định rõ điểm cấp quyền và bảo đảm nhất quán của nó.

### 10.2. Service minh họa

Các repository, policy và kiểu dữ liệu cần được triển khai. Constructor injection được lược bỏ; đây không phải ứng dụng hoàn chỉnh có thể chạy độc lập.

```java
@Service
public class DelegatedReportCommentService {
    private final AuthorizationDecisionGuard authorizationGuard;
    private final AuthorizationSnapshotRepository authorizationSnapshots;
    private final ExpenseReportRepository reports;
    private final ObjectDelegationRepository delegations;
    private final ReportCommentRepository comments;
    private final DelegatedAccessPolicy policy;
    private final DatabaseTimeSource databaseTime;
    private final IdempotencyRepository idempotency;
    private final WorkflowAuditRepository audits;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprints;

    @Transactional(rollbackFor = Exception.class)
    public CommentReceipt addComment(
            VerifiedActor actor,
            AddDelegatedReportCommentCommand command) {

        actor.requireAuthenticated();
        command.validateSyntaxAndLimits();

        authorizationGuard.lockForDecision(actor.tenantId());

        ExpenseReport report = reports.lockForUpdate(
                actor.tenantId(), command.reportId())
            .orElseThrow(ReportNotFoundException::new);

        ObjectDelegationGrant grant = delegations.lockForUse(
                actor.tenantId(), command.grantId(),
                ResourceType.EXPENSE_REPORT, report.id())
            .orElseThrow(DelegationNotFoundException::new);

        AuthorizationSnapshot authorization =
                authorizationSnapshots.loadUnderDecisionGuard(
                        actor.tenantId());
        authorization.requireValidAndComplete();

        Instant checkedAt = databaseTime.currentInstant();

        // Bao gồm đúng người nhận, tenant, đối tượng, action,
        // thời hạn, owner epoch và quyền nguồn hiện tại của người cấp.
        DelegationDecision decision = policy.requireDelegatedAuthority(
                actor, report, grant,
                BusinessAction.REPORT_COMMENT_ADD,
                authorization, checkedAt);

        CommandScope keyScope = new CommandScope(
                actor.tenantId(), report.id(),
                actor.canonicalSubjectId(),
                "ADD_REPORT_COMMENT", command.idempotencyKey());
        String fingerprint = fingerprints.forDelegatedComment(command);

        var previous = idempotency.find(keyScope);
        if (previous.isPresent()) {
            if (!previous.get().fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }
            return previous.get().receipt();
        }

        // Guard trạng thái áp dụng cho lần thêm nhận xét mới.
        report.requireCommentsOpen(command.expectedReportVersion());

        UUID commentId = UUID.randomUUID();
        comments.insert(
                commentId, actor.tenantId(), report.id(),
                actor.canonicalSubjectId(), command.commentText(),
                grant.id(), checkedAt);

        int changed = reports.noteCommentAdded(
                actor.tenantId(), report.id(), report.version(),
                report.ownerEpoch(), checkedAt);
        if (changed != 1) {
            throw new ConcurrentReportChangeException();
        }

        audits.appendDelegatedCommentAdded(
                actor, report, grant, decision, commentId);
        outbox.appendReportCommentAdded(
                UUID.randomUUID(), actor.tenantId(),
                report.id(), commentId);

        CommentReceipt receipt = new CommentReceipt(
                commentId, report.id(), report.version() + 1);
        idempotency.insert(keyScope, fingerprint, receipt);
        return receipt;
    }
}
```

Các dependency `final` phải được khởi tạo bằng constructor. Với Spring transaction qua proxy thông thường, lời gọi phải đi qua bean được quản lý và các repository phải tham gia đúng transaction manager của ví dụ.

`lockForUse()` phải thật sự ràng buộc tenant, grant ID, loại đối tượng và report ID, không chỉ có tên method như vậy. Policy kiểm tra người nhận từ danh tính đã xác thực; grant ID không thay cho xác thực.

`noteCommentAdded()` cần cập nhật có điều kiện theo version, owner epoch và trạng thái cho phép, đồng thời tăng version. Nếu ghi audit hoặc outbox bắt buộc thất bại, transaction phải rollback cả comment và cập nhật report.

### 10.3. Hợp đồng retry của ví dụ

Ví dụ kiểm tra grant hiện tại trước khi trả receipt cũ. Nếu grant đã bị thu hồi hoặc hết hạn và không có quyền đọc receipt theo cơ chế khác, retry bị từ chối; một comment đã commit trước đó vẫn tồn tại, không bị thực hiện lại.

Đây là lựa chọn hợp đồng có chủ ý. Một hệ thống có thể cung cấp endpoint đọc trạng thái command với quyền riêng, nhưng không dùng idempotency key làm quyền truy cập độc lập.

Trong khi grant còn dùng được, cùng key và cùng nội dung trả lại receipt cũ trước guard version của lần ghi mới. Fingerprint phải ràng buộc report, grant được dùng, nội dung nhận xét và các trường quyết định ý định theo hợp đồng API.

Đổi key có thể tạo một nhận xét mới hợp lệ. Nếu nghiệp vụ cần chống trùng theo một intent riêng, phải có ràng buộc cho intent đó; idempotency không tự nhận diện mọi nội dung giống nhau là cùng một ý định.

## 11. Thu hồi grant và cuộc đua với hành động đang thực hiện

### 11.1. Ai được thu hồi?

Có thể cho người cấp hiện còn đủ thẩm quyền, chủ sở hữu hoặc một vai trò quản trị truy cập được phép thu hồi. Quyền thu hồi cần kiểm tra trên đúng đối tượng và tenant.

Người nhận có thể được phép từ chối hoặc ngừng dùng grant của mình qua một action riêng. Điều đó không tạo quyền thu hồi grant của người khác.

Một cập nhật minh họa:

```sql
UPDATE report_delegation
SET lifecycle_state = 'REVOKED',
    revoked_by_subject_id = :actorSubjectId,
    revoked_at = :checkedAt,
    version = version + 1
WHERE tenant_id = :tenantId
  AND report_id = :reportId
  AND id = :grantId
  AND lifecycle_state = 'ACTIVE';
```

Đoạn SQL chỉ minh họa thay đổi vòng đời. Kiểm tra quyền, thứ tự khóa, audit và outbox bắt buộc vẫn phải có trong transaction phù hợp. Tham số phải được bind qua lớp truy cập dữ liệu.

### 11.2. Chọn một điểm phân định rõ ràng

Nếu đường thêm comment và thu hồi cùng khóa report rồi grant:

| Thứ tự hợp lệ | Kết quả |
| --- | --- |
| Comment được nhận và commit trước | Comment tồn tại với bằng chứng grant hợp lệ tại gate; thu hồi chặn lần dùng mới |
| Thu hồi commit trước | Lần thêm comment sau không được dùng grant đã thu hồi |

Không yêu cầu thu hồi xóa ngược những hành động đã hợp lệ, trừ khi có nghiệp vụ khác được thiết kế để xử lý chúng.

Với response đọc dữ liệu đã được chấp nhận trước thu hồi, dữ liệu có thể đang trên đường truyền. Thu hồi quyền không làm người nhận quên dữ liệu đã xem hoặc tự lấy lại file đã tải.

### 11.3. Không nhầm trạng thái worker với kết quả nghiệp vụ

Nếu một action được ủy quyền tạo tác động bên ngoài, hủy task hoặc mất lease không chứng minh hiệu ứng đã dừng. Cần command bền vững, định danh hiệu ứng, idempotency và đối soát phù hợp.

Một grant hết hạn sau khi command đã được nhận có thể hoặc không ảnh hưởng command theo hợp đồng đã chọn. Phải tách quyền nhận hành động mới khỏi quy trình xử lý công việc đã nhận, tránh tạo hiệu ứng lặp khi mở lại đường thực thi.

## 12. Hết hạn, quyền nguồn thay đổi và chuyển chủ sở hữu

### 12.1. Hết hạn không phụ thuộc scheduler

Đường sử dụng grant phải tự kiểm tra khoảng `[not_before, not_after)`. Một job nền chưa ghi nhãn `EXPIRED` không giữ quyền sống sau deadline.

Tại đúng `not_after`, grant hết hiệu lực theo quy ước nửa mở. Thời điểm gate cần lấy từ nguồn server phù hợp sau các thời gian chờ khóa cần thiết, không dùng mốc do client gửi.

### 12.2. Quyền nguồn bị thu hồi

Theo chính sách nguồn quyền còn sống của bài, người cấp mất thẩm quyền cần thiết thì grant không còn đủ điều kiện dùng. Có thể ghi nhận trạng thái tổng hợp sau đó, nhưng hàng rào nằm ở kiểm tra nguồn tại gate và cơ chế nhất quán đã công bố.

Nếu nguồn quyền ở một IAM ngoài và chỉ đồng bộ định kỳ, độ trễ đó cần được nêu đúng. Cache hoặc token cũ không tự hỗ trợ thu hồi tức thời.

### 12.3. Chuyển chủ sở hữu

Ví dụ:

```text
Trước chuyển: owner=A, owner_epoch=7.
Sau chuyển:   owner=C, owner_epoch=8.
Grant cũ G:   owner_epoch=7.
```

Grant G không tự có hiệu lực dưới chủ sở hữu C. Nếu C muốn tiếp tục chia sẻ, tạo quyết định mới theo policy thay vì làm sống lại quyền cũ.

Epoch tăng đơn điệu. Không đặt lại epoch khi hồ sơ quay về một chủ sở hữu cũ, vì request hoặc token cũ có thể khớp trở lại.

Chuyển sở hữu trong tenant khác với chuyển tenant. Không dùng chức năng chia sẻ để âm thầm thay `tenant_id` hoặc đưa đối tượng sang một miền quản trị khác.

### 12.4. Sao chép đối tượng

Bản sao có định danh và quan hệ sở hữu riêng. Không mặc định sao chép toàn bộ grant của bản gốc. Nếu sản phẩm muốn giữ một phần quyền, phải định nghĩa và kiểm tra đó như một hành động cấp quyền mới phù hợp với đối tượng đích.

## 13. Token tự chứa, grant lưu server và cache

### 13.1. Grant lưu ở server

Đường thực thi có thể tra grant hiện tại theo ID rồi kiểm tra actor, đối tượng, thời gian và nguồn quyền. Cách này hỗ trợ quyết định theo trạng thái hiện tại, nhưng vẫn cần giữ nhất quán với cache và các thay đổi đồng thời.

### 13.2. Token hoặc capability tự chứa

Nếu token có chữ ký chứa quyền truy cập, cần bảo vệ ít nhất các thành phần có ý nghĩa: tenant, đối tượng, action, người nhận nếu ràng buộc danh tính, thời hạn, owner epoch và tham chiếu grant hoặc nguồn quyền theo thiết kế.

Chữ ký hợp lệ không chứng minh grant chưa bị thu hồi. Nếu không kiểm tra trạng thái hoặc cơ chế thu hồi tương ứng, token có thể tiếp tục dùng đến hết hạn theo hợp đồng của nó.

Không dùng một bearer token rồi mô tả nó như quyền chỉ dành cho một người đã xác thực nếu server không thực sự đối chiếu người nhận.

### 13.3. Cache phải giữ đúng phạm vi

Cache quyết định chỉ theo `reportId` có thể làm quyền của B bị dùng cho C. Cache theo người và report nhưng bỏ action có thể biến quyền đọc thành quyền thêm hoặc tải dữ liệu.

Các phụ thuộc còn gồm grant version, owner epoch, quyền nguồn, membership, policy revision và giới hạn thời gian. Chỉ giảm TTL không bảo đảm thu hồi tức thời hoặc xử lý đúng chuyển chủ sở hữu.

Nếu cache dùng cho đường nhạy cảm, cần chứng minh hợp đồng invalidation hoặc kiểm tra version. Nhãn chia sẻ trên giao diện không phải bằng chứng cuối để server thực hiện action.

## 14. Tích hợp service và tác vụ bất đồng bộ

Một service có quyền kỹ thuật đọc dữ liệu không được trở thành trung gian lấy mọi đối tượng theo ID mà người dùng gửi.

Ví dụ, job export được tạo từ grant phải giữ tham chiếu command, tenant, report, action, người khởi tạo và bằng chứng đã được nhận. Payload không được tự thay sang report khác mà vẫn dùng quyền rộng của worker.

Cần định nghĩa riêng:

- Grant phải hợp lệ khi nhận job hay cả khi worker bắt đầu đọc dữ liệu?
- Nếu grant hết hạn trong lúc tạo file, job tiếp tục, dừng hay chuyển trạng thái nào?
- Khi tải file kết quả, người dùng có phải còn quyền trên report không?
- File đã tạo được lưu và hết hạn theo cơ chế nào?

Một câu “grant đã hợp lệ lúc bấm export” không tự trả lời các câu hỏi trên. Nếu yêu cầu đọc lại quyền lúc tải, đường tải phải thực sự kiểm tra; một URL độc lập còn hạn có thể không đáp ứng yêu cầu đó.

Với batch, từng report và action phải nằm trong nguồn quyền hợp lệ. Không kiểm tra grant cho phần tử đầu rồi áp dụng cho toàn bộ danh sách.

## 15. Audit và giải thích quyết định

Audit cần liên kết được:

- Người cấp, người nhận và actor thực tế của từng hành động.
- Tenant, loại đối tượng, object ID và owner epoch.
- Grant ID, version, tập action và khoảng hiệu lực.
- Nguồn thẩm quyền của người cấp đã dùng theo chính sách.
- Thời điểm gate, policy revision và command ID.
- Thay đổi trạng thái, thu hồi, hết hạn hoặc chuyển chủ sở hữu có liên quan.

Không chỉ ghi “owner truy cập thành công” nếu người thực sự làm việc là delegate. Cũng không ghi token chia sẻ, access token hoặc URL chứa bí mật nguyên văn vào log.

Nhận xét, tên người nhận và lý do chia sẻ là dữ liệu không đáng tin. Cần giới hạn đầu vào và hiển thị bằng cơ chế escaping phù hợp; quyền thêm comment không bao gồm quyền chèn nội dung thực thi trong công cụ của người duyệt.

| Tín hiệu | Điều cần kiểm tra |
| --- | --- |
| Dùng grant với nhiều actor không khớp | Grant ID có thể bị coi như bearer ngoài ý muốn hoặc có dò quyền |
| Nhiều request đổi report ID nhưng giữ grant | Có thể đang thử truy cập đối tượng ngang cấp |
| Grant cũ xuất hiện sau chuyển chủ sở hữu | Có replay hoặc đường kiểm tra bỏ owner epoch |
| Người nhận thử cấp tiếp hoặc thêm action nhạy cảm | Có thể đang mở rộng quyền vượt hợp đồng |
| Quyền vẫn được dùng lâu sau thu hồi | Cache, token hoặc worker có thể không tuân thủ hợp đồng thu hồi |
| Service thực hiện trên đối tượng khác command gốc | Có thể có lỗi trung gian dùng quyền rộng |
| Lịch sử ghi chủ sở hữu thay cho actor | Mất quy trách nhiệm và có nguy cơ vượt SoD |

Audit thành công bắt buộc cần commit cùng hiệu ứng cục bộ tương ứng. Các lần thử bị từ chối có thể cần đường ghi riêng vì transaction rollback không giữ lại bản ghi cùng transaction đó.

## 16. Kiểm thử tình huống tấn công logic

### 16.1. Người nhận, đối tượng và action

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| B được chia sẻ R1 và truy cập R1 đúng action | Được phép khi thỏa các điều kiện còn lại |
| C dùng grant ID của B | Bị từ chối dù grant có tồn tại và còn hạn |
| B đổi R1 thành R2 cùng chủ sở hữu | Không mở rộng theo owner ID |
| Grant tenant A dùng cho đối tượng tenant B | Không truy cập hoặc tiết lộ ngoài phạm vi |
| Grant đọc được dùng để thêm comment hoặc duyệt | Không suy ra action chưa được cấp |
| B tự thêm `canRedelegate` hoặc action vào body | Không thay quyền server đã quyết định |
| B chia sẻ tiếp chỉ dựa vào grant đọc | Bị từ chối trong mô hình không cho cấp tiếp |
| Grant trên report được dùng tải chứng từ của report khác | Bị chặn bởi quan hệ đối tượng con |
| Report trả quan hệ lồng nhau nhạy cảm | Chỉ dữ liệu được policy cho phép được xuất ra |

### 16.2. Thời gian, thu hồi và quyền nguồn

Kiểm tra trước, đúng và sau `not_before`, `not_after` theo độ chính xác thực tế. Dùng abstraction thời gian điều khiển được cho logic thuần, không phụ thuộc `sleep` để chờ hết hạn.

Các trường hợp cần có:

1. Scheduler hết hạn bị dừng nhưng grant đã qua deadline.
2. Người cấp mất quyền nguồn theo chính sách còn sống.
3. Người nhận bị vô hiệu membership.
4. Grant bị thu hồi nhưng token hoặc cache cũ vẫn còn.
5. Chủ sở hữu thay đổi rồi đổi lại, owner epoch vẫn khác grant cũ.
6. Request bắt đầu trước hạn nhưng chờ khóa đến sau hạn.
7. Client đổi đồng hồ hoặc gửi timestamp cũ để xin quyền.
8. Grant được gia hạn hoặc tạo lại phải có quyết định và bằng chứng phù hợp, không tự gia hạn khi đọc.

Với PostgreSQL, nếu gate yêu cầu thời gian mới sau chờ khóa, cần hiểu rằng `now()` và `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu transaction. Chọn nguồn thời gian phù hợp, chẳng hạn lấy mốc mới từ `clock_timestamp()` sau các điểm chờ cần thiết, và kiểm tra đúng ngữ nghĩa đó bằng test tích hợp.

### 16.3. Concurrency và idempotency

Dùng hai transaction độc lập cùng barrier hoặc latch để tạo lịch có chủ đích:

```text
A. Thu hồi commit trước lần thêm comment.
   Kết quả: comment không được nhận bằng grant đã thu hồi.

B. Comment nhận và commit trước thu hồi.
   Kết quả: comment giữ actor và bằng chứng nguồn đúng;
   thu hồi chặn lần dùng mới, không tạo lại hoặc xóa ngầm comment cũ.

C. Chuyển chủ sở hữu cạnh tranh với sử dụng grant cũ.
   Kết quả: gate và owner epoch tuân theo thứ tự được bảo vệ,
   không dùng quyền của chủ cũ trên trạng thái chủ mới trái policy.
```

Gửi hai request cùng key và cùng nội dung khi grant còn hợp lệ để chứng minh chỉ có một comment. Cùng key nhưng đổi grant hoặc nội dung phải xung đột theo fingerprint. Sau khi hết quyền, retry phải tuân theo chính sách đọc receipt hiện tại, không biến key thành một quyền truy cập mới.

### 16.4. Lỗi transaction và đường phụ

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Audit hoặc outbox bắt buộc lỗi | Comment, version và receipt không commit nửa vời |
| Mất response sau commit | Không tạo thêm comment khi retry cùng ý định được nhận diện |
| Queue message đổi report hoặc tenant | Worker không dùng quyền kỹ thuật để thực hiện trên đối tượng khác |
| Batch trộn nhiều report | Mọi phần tử được kiểm tra bằng nguồn quyền phù hợp |
| URL tải đã phát hành trước thu hồi | Hành vi đúng giới hạn mà cơ chế tải thực sự hỗ trợ |
| Search hoặc export đi đường khác API đọc chính | Không mở rộng quyền ngoài grant |
| Actor qua service bị ghi thành owner | Test audit phát hiện mất quy trách nhiệm |
| Chuỗi ủy quyền lỗi hoặc quá sâu nếu có hỗ trợ | Không cấp quyền từ kết quả phân giải một phần |

Không chỉ kiểm tra HTTP status. Cần kiểm tra dữ liệu report, comment, grant, audit, outbox, job và quyền tải kết quả. Mock repository không chứng minh được hành vi khóa, commit hoặc khả năng thu hồi của nơi lưu file.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao tạo lỗ hổng logic | Hướng thay thế |
| --- | --- | --- |
| Dùng grant ID như đủ quyền | Người thứ ba có thể dùng lại | Ràng buộc danh tính và kiểm tra nguồn quyền |
| Chia sẻ một đối tượng nhưng query theo owner | Mở quyền sang mọi đối tượng của chủ sở hữu | Ràng buộc tenant, loại và ID đối tượng |
| Có read thì tự có edit, approve hoặc delegate | Mở action ngoài quyết định | Tập action rõ ràng và policy giới hạn |
| Ghi actor thành người cấp | Mất trách nhiệm thực tế và có thể vượt SoD | Giữ actor thật cùng nguồn ủy quyền |
| Chỉ kiểm tra người cấp lúc tạo nhưng hứa thu hồi sống | Hợp đồng không được thực thi khi sử dụng | Kiểm tra nguồn hoặc chọn mô hình ủy quyền độc lập rõ ràng |
| Chỉ dựa vào scheduler hết hạn | Job chậm giữ quyền quá hạn | Kiểm tra thời gian trực tiếp tại gate |
| Đổi owner nhưng giữ grant cũ | Chủ mới kế thừa chia sẻ ngoài ý muốn | Owner epoch hoặc cơ chế vô hiệu hóa tương đương |
| Cache theo object ID | Quyền một người hoặc một action bị dùng cho người khác | Khóa và version đủ phạm vi |
| Thu hồi DB rồi hứa lấy lại mọi file | Dữ liệu đã tải hoặc URL độc lập có giới hạn khác | Công bố và thực thi đúng hợp đồng tải |
| Khóa grant nhưng bỏ quyền nguồn thay đổi | Quyết định dùng dữ liệu không còn đúng theo policy sống | Giao thức nhất quán cho các phụ thuộc cần thiết |
| Worker tin payload và có quyền rộng | Service bị dùng làm trung gian vượt quyền | Command bền vững, đối tượng ràng buộc và xác thực nguồn |
| Chia sẻ làm đổi tenant hoặc chủ sở hữu | Trộn cấp truy cập với chuyển giao dữ liệu | Workflow riêng cho thay đổi quan hệ sở hữu |

## 18. Bài tập thiết kế

Thiết kế chức năng cho chủ hồ sơ chi phí chia sẻ quyền đọc và nhận xét với đồng nghiệp trong cùng tenant. Chứng từ có thể chứa dữ liệu cần bảo vệ riêng. Quyền phải hết hạn, có thể thu hồi và không tự tiếp tục sau khi hồ sơ đổi chủ sở hữu.

Hãy mô tả:

1. Grant ràng buộc người cấp, người nhận, đối tượng và action như thế nào?
2. Người cấp phải có quyền gì ngoài khả năng đọc, và nguồn quyền có phải còn sống khi sử dụng không?
3. Cơ chế nào ngăn chia sẻ tiếp hoặc dùng grant R1 cho R2?
4. Owner epoch, thời gian và trạng thái report được kiểm tra tại gate nào?
5. Lần thêm comment và thu hồi grant cạnh tranh sẽ có những kết quả hợp lệ nào?
6. Actor thật, người cấp và service làm thay được lưu ra sao để không vượt phân tách nhiệm vụ?
7. Đường tải chứng từ và export có hợp đồng thu hồi gì, gồm giới hạn nào của URL đã phát hành?
8. Những test nào chứng minh API chính, queue, batch và cache đều giữ đúng phạm vi ủy quyền?

Một thiết kế đạt yêu cầu phải giải thích được ai đang làm việc, quyền đến từ đâu, được dùng trên đối tượng nào và điều gì làm quyền đó mất hiệu lực, trong khi quan hệ sở hữu và các bất biến nghiệp vụ vẫn được giữ đúng.
