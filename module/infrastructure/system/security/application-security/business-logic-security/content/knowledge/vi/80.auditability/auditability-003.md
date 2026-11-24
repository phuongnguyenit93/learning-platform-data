# Actor context recording — Ghi nhận ngữ cảnh tác nhân

## 1. Vì sao một mã người dùng chưa đủ?

Trong bảo mật logic nghiệp vụ, một bản ghi như “người dùng u-17 đã phê duyệt hoàn tiền R-420” có thể bỏ sót điều quan trọng nhất: u-17 đăng nhập trực tiếp, đang đại diện cho người khác, hay chỉ là danh tính được một dịch vụ phía trước truyền đến? Quyền nào đã được kiểm tra? Hoàn tiền thuộc tenant nào? Quyết định được đưa ra trước hay sau khi quyền bị thu hồi?

**Actor context recording** là việc ghi lại ngữ cảnh tác nhân gắn với một hành động và quyết định nghiệp vụ cụ thể. Ngữ cảnh này phải đến từ các nguồn tin cậy đã được kiểm chứng ở phía máy chủ, đủ để giải thích vì sao hành động được cho phép hoặc bị từ chối tại thời điểm đó.

Trong chương Auditability của module bảo mật logic nghiệp vụ, mục tiêu không chỉ là biết “ai gọi API”. Cần nối được danh tính với quyền theo đối tượng, quy tắc nghiệp vụ, trạng thái tài nguyên và kết quả thực tế. Ví dụ:

- Ai yêu cầu hoàn tiền và ai phê duyệt?
- Nhân viên hỗ trợ đang thao tác bằng quyền của mình hay đại diện cho khách hàng?
- Một worker thanh toán thực thi yêu cầu do ai khởi tạo?
- Yêu cầu lặp lại có tạo thêm một lần chuyển tiền hay chỉ nhận lại kết quả cũ?
- Việc sửa giá được phép bởi chính sách nào, trên phiên bản đơn hàng nào?

Một bản ghi audit có danh tính không thay thế việc kiểm tra quyền. Nó cũng không tự chứng minh người thật nào đang ngồi trước thiết bị, hay chứng minh sự đồng ý của người đó. Giá trị của nó nằm ở khả năng giải thích quyết định của hệ thống dựa trên bằng chứng và mức tin cậy thực tế.

Sau bài này, người học cần có khả năng thiết kế ngữ cảnh tác nhân, chọn nguồn dữ liệu đúng, giữ mạch truy vết qua dịch vụ và hàng đợi, đồng thời tránh việc ghi sai người hoặc làm lộ thông tin xác thực.

## 2. Tình huống xuyên suốt: phê duyệt hoàn tiền

Giả sử hệ thống quản lý hoàn tiền có các quy tắc:

1. Hoàn tiền chỉ được phê duyệt khi đang ở trạng thái **PENDING_APPROVAL**.
2. Người phê duyệt phải có quyền **refund.approve** trong phạm vi tenant và đối tượng tương ứng.
3. Người yêu cầu không được tự phê duyệt yêu cầu của mình.
4. Cơ chế đại diện không được dùng để biến cùng một người thành hai người phê duyệt độc lập.
5. Một yêu cầu nghiệp vụ chỉ tạo một kết quả phê duyệt có hiệu lực; các lần thử lại phải được xử lý phù hợp.

Người dùng u-17 tạo hoàn tiền R-420 trong tenant t-a, rồi gửi:

~~~http
POST /refunds/R-420/approve
Content-Type: application/json

{
  "actorId": "u-manager-42",
  "tenantId": "t-a",
  "expectedVersion": 8,
  "reason": "Approve refund"
}
~~~

Nếu ứng dụng lấy **actorId** trong body để kiểm tra “người phê duyệt khác người yêu cầu”, kẻ tấn công có thể vượt qua quy tắc. Nếu phần kiểm tra quyền dùng danh tính từ phiên đăng nhập nhưng phần audit lại dùng **actorId** trong body, hành động có thể bị chặn đúng nhưng bằng chứng lại ghi sai người.

Cách xử lý cần thống nhất:

- Danh tính tác nhân lấy từ ngữ cảnh xác thực đã kiểm chứng.
- Tenant trong URL, header hoặc body chỉ là lựa chọn được yêu cầu; máy chủ phải xác minh quyền trong tenant đó.
- Người yêu cầu, trạng thái, số tiền và phiên bản hoàn tiền lấy từ dữ liệu có thẩm quyền.
- Quyết định và bản ghi audit dùng cùng một ảnh chụp ngữ cảnh đã được dùng để đánh giá chính sách.

Trong thiết kế API mới, lệnh phê duyệt thường không cần trường **actorId** do client cung cấp. Nếu API cần **requestedApproverId** để chỉ định người sẽ nhận việc trong tương lai, đó là đối tượng của thao tác phân công, không phải danh tính người đang thực hiện thao tác.

## 3. Phân biệt các danh tính trong một hành động

Không nên gom mọi khái niệm vào một trường **userId**.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Authenticated principal | Chủ thể nào đã được xác thực tại ranh giới đang xét? | Người dùng u-17 ở API công khai; dịch vụ refund-api ở API nội bộ |
| Initiating actor | Chủ thể nào khởi tạo chuỗi công việc nghiệp vụ? | u-17 gửi yêu cầu ban đầu |
| Effective subject | Hệ thống đang thực hiện hành động trong phạm vi quyền hoặc tư cách của ai? | Khách hàng được đại diện; u-17 khi thao tác trực tiếp |
| Executing service | Thành phần phần mềm nào thực thi bước hiện tại? | refund-api hoặc refund-worker |
| Delegating actor | Ai cấp quyền đại diện, nếu mô hình nghiệp vụ có cơ chế này? | Chủ tài khoản cấp ủy quyền có phạm vi |
| Target subject | Ai hoặc tài khoản nào chịu tác động bởi thao tác? | Khách hàng nhận tiền hoàn |
| Resource owner | Ai sở hữu hoặc quản lý đối tượng nghiệp vụ? | Tenant t-a sở hữu hoàn tiền R-420 |

Các khái niệm này phụ thuộc vào mô hình của hệ thống, vì vậy cần định nghĩa ý nghĩa và quy tắc điền từng trường trong schema audit.

### 3.1. Thao tác trực tiếp

Ở API công khai, u-17 xác thực và thao tác cho chính mình:

~~~text
authenticated principal = u-17
initiating actor         = u-17
effective subject        = u-17
executing service        = refund-api
delegation               = không có
~~~

Không cần tạo một quan hệ đại diện giả khi các danh tính trùng nhau.

### 3.2. Nhân viên hỗ trợ đại diện khách hàng

Nhân viên support-9 mở phiên hỗ trợ để xem đơn hàng của customer-42:

~~~text
authenticated principal = support-9
initiating actor         = support-9
effective subject        = customer-42
executing service        = support-api
delegation/session ref   = support-session-78
~~~

Nếu audit chỉ ghi customer-42, lịch sử có thể khiến người điều tra tưởng khách hàng tự thực hiện thao tác. Bản ghi cần giữ cả nhân viên thao tác và khách hàng được đại diện.

Việc một phiên hỗ trợ được phép xem đơn hàng không đồng nghĩa phiên đó được phê duyệt hoàn tiền. Quyền đại diện cần có phạm vi hành động, đối tượng, thời hạn và các hạn chế nghiệp vụ riêng.

### 3.3. Tác vụ tự động

Một lịch chạy tự động phát hiện hoàn tiền quá hạn:

~~~text
authenticated principal = workload-refund-scheduler
initiating actor         = workload-refund-scheduler
effective subject        = service identity theo mô hình quyền
executing service        = refund-scheduler
human initiator          = không có
~~~

Không gán tác vụ cho một tài khoản “admin” mặc định để điền cho đủ trường. Nếu không có người khởi tạo trực tiếp, schema phải biểu đạt được điều đó. Người từng cấu hình lịch chạy có thể là một liên kết audit riêng; họ không mặc nhiên là tác nhân của mọi lần thực thi sau này.

## 4. Nội dung cần ghi và nguồn đáng tin cậy

Một ngữ cảnh tác nhân hữu ích thường gồm các nhóm thông tin dưới đây. Không phải mọi sự kiện đều cần toàn bộ trường; lựa chọn dựa trên khả năng giải thích quyết định và giới hạn thu thập dữ liệu.

| Nhóm | Trường gợi ý | Nguồn và lưu ý |
|---|---|---|
| Định danh chủ thể | principalId, principalType, identityIssuer | Kết quả xác thực đã kiểm chứng; dùng cặp issuer và subject nếu subject không duy nhất toàn hệ thống |
| Nguồn khởi tạo | initiatingActorId, initiatingActorType | Từ yêu cầu trực tiếp hoặc chuỗi chuyển tiếp được kiểm chứng |
| Chủ thể hiệu lực | effectiveSubjectId | Từ mô hình quyền và quan hệ đại diện đã xác minh |
| Thực thi | serviceId, workloadId | Danh tính triển khai hoặc workload đáng tin cậy |
| Tenant | selectedTenantId, resourceTenantId | Tenant đã xác minh quyền truy cập và tenant thực tế của đối tượng |
| Đại diện | delegationId, supportSessionId, scope, expiresAt | Tham chiếu và ảnh chụp các thuộc tính cần thiết của grant đã kiểm chứng |
| Xác thực bổ sung | authenticationMethod, stepUpVerifiedAt | Từ thành phần xác thực có thẩm quyền, không từ cờ do client tự khai |
| Quyền tại quyết định | evaluatedRoles, evaluatedPermissions, scope | Các quyền và phạm vi thực sự tham gia đánh giá |
| Chính sách | policyVersion, decision, reasonCode | Kết quả của bộ kiểm tra quyền và quy tắc nghiệp vụ |
| Hành động và đối tượng | action, resourceType, resourceId | Tên hành động chuẩn hóa và định danh đối tượng phù hợp |
| Liên kết yêu cầu | requestId, commandId, traceId, causationId | Mã do hệ thống sinh hoặc giá trị chuyển tiếp được kiểm soát |
| Thời gian | occurredAt, decisionAt, recordedAt | Đồng hồ máy chủ; phân biệt thời điểm quyết định với thời điểm ghi nhận |
| Nguồn kết nối | sourceAddress, trustedClientId | Chỉ ghi khi cần; xác định nguồn qua cấu hình proxy đáng tin cậy |
| Kết quả nghiệp vụ | outcome, resourceVersionBefore, resourceVersionAfter | Kết quả thực tế của giao dịch hoặc kết quả từ chối |

### 4.1. Snapshot quyền khác với danh sách quyền hiện tại

Sau ba tháng, u-17 có thể đã chuyển phòng ban hoặc bị khóa tài khoản. Nếu lúc điều tra mới truy vấn vai trò hiện tại rồi suy ra quyền ở quá khứ, kết luận có thể sai.

Cần lưu những thông tin đã tham gia quyết định tại thời điểm hành động:

- Danh tính và phạm vi tenant đã được xác minh.
- Vai trò hoặc permission liên quan, cùng phạm vi áp dụng.
- Phiên bản chính sách và mã lý do.
- Tham chiếu hoặc snapshot cần thiết của grant đại diện.
- Bằng chứng đã xác minh về xác thực bổ sung nếu quy tắc yêu cầu.

Không nhất thiết sao chép toàn bộ hồ sơ người dùng hoặc mọi quyền của họ. Một bộ policy có phiên bản nhưng phụ thuộc vào cấu hình động như hạn mức phê duyệt vẫn cần ghi hạn mức đã dùng, hoặc tham chiếu tới một phiên bản cấu hình được giữ lại và bảo vệ. Chỉ có **policyVersion** chưa chắc đủ để tái dựng quyết định.

### 4.2. IP và User-Agent không phải danh tính

Địa chỉ IP có thể thuộc NAT hoặc proxy; User-Agent có thể bị giả. Các trường này hỗ trợ điều tra nguồn truy cập nhưng không được thay cho định danh đã xác thực.

Tương tự, không lấy phần tử đầu tiên của **X-Forwarded-For** làm bằng chứng nguồn truy cập nếu chưa xác định và cấu hình chuỗi proxy đáng tin cậy. Chỉ nhận thông tin chuyển tiếp theo chính sách của hạ tầng; phân loại độ tin cậy rõ ràng.

### 4.3. Giá trị chưa xác minh phải được phân loại riêng

Yêu cầu chưa xác thực không có authenticated actor hợp lệ. Nếu cần ghi tên đăng nhập mà client thử sử dụng, có thể lưu một trường riêng như **claimedLogin**, có giới hạn độ dài và quyền truy cập phù hợp.

Không ghi giá trị đó vào **authenticatedPrincipalId**. Dấu hiệu “client tự khai” và “hệ thống đã xác minh” phải khác nhau trong schema, không chỉ khác nhau trong chú thích dành cho người đọc.

## 5. Ranh giới tin cậy và thời điểm chụp ngữ cảnh

Ngữ cảnh tác nhân được xây dựng ở phía máy chủ sau khi xác thực và được bổ sung khi có đủ dữ liệu để kiểm tra quyền trên đối tượng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant P as Policy
    participant D as Database
    participant J as Audit
    C->>A: Lệnh phê duyệt và thông tin xác thực
    A->>A: Xác thực, xác minh tenant và đại diện
    A->>D: Đọc đối tượng với cơ chế kiểm soát cạnh tranh
    A->>P: Chủ thể đã xác minh, đối tượng, hành động
    P-->>A: Quyết định, lý do, phiên bản chính sách
    A->>A: Tạo snapshot actor context cho quyết định này
    alt Được phép và cập nhật thành công
        A->>D: Cập nhật nghiệp vụ + audit outbox cùng giao dịch
        D-->>A: Commit
        A-->>C: Thành công
        D-->>J: Chuyển sự kiện đã commit qua publisher
    else Bị từ chối
        A->>J: Ghi sự kiện từ chối theo đường ghi độc lập
        A-->>C: Trả kết quả từ chối
    end
~~~

Sơ đồ mô tả luồng logic; một tiến trình publisher thực hiện việc đọc outbox và chuyển sự kiện. Cơ sở dữ liệu không tự gửi sự kiện nếu chưa có cơ chế tương ứng.

### 5.1. Đừng tin header chỉ vì nó có tên nội bộ

Các trường **X-User-Id**, **X-Tenant-Id**, **X-Role** không đáng tin nếu client có thể tự gửi chúng.

Nếu gateway truyền ngữ cảnh danh tính xuống backend, cần có ranh giới rõ ràng:

- Gateway xác thực chủ thể và loại bỏ hoặc ghi đè các header danh tính do client gửi.
- Backend chỉ nhận thông tin danh tính theo cơ chế đã thiết kế từ gateway hoặc workload đáng tin cậy.
- Đường truy cập thẳng tới backend cũng phải được kiểm soát; chỉ “có gateway phía trước” chưa đủ.
- Backend vẫn kiểm tra quyền và quy tắc nghiệp vụ phù hợp với đối tượng.
- Nguồn gốc và ý nghĩa của các trường chuyển tiếp phải được thống nhất.

Một token có chữ ký hợp lệ vẫn phải được kiểm tra issuer, audience, thời hạn và các điều kiện sử dụng liên quan. Chữ ký không biến mọi claim thành quyền phê duyệt mọi đối tượng.

### 5.2. Cùng một snapshot cho kiểm tra quyền và ghi audit

Giả sử ứng dụng kiểm tra quyền bằng tenant t-a nhưng sau đó logger lấy tenant t-b từ một context dùng chung đã bị thay đổi. Audit sẽ gắn sai phạm vi dù phép kiểm tra ban đầu đúng.

Ngữ cảnh nên là dữ liệu bất biến, gắn với yêu cầu hoặc lệnh cụ thể. Snapshot audit phải phản ánh dữ liệu đã được policy sử dụng, không dựng lại bằng cách đọc vai trò, tenant hoặc phiên đại diện một lần nữa sau khi quyết định đã xong.

Các quy tắc liên quan đến trạng thái, phiên bản hoặc người tạo đối tượng cần được đánh giá trên dữ liệu đủ nhất quán với thao tác cập nhật. Nếu có cập nhật đồng thời, dùng cơ chế transaction, khóa hoặc kiểm tra phiên bản phù hợp. Audit ghi đúng người nhưng ghi một quyết định dựa trên trạng thái lỗi thời vẫn chưa đáp ứng mục tiêu bảo vệ nghiệp vụ.

## 6. Ví dụ bản ghi từ chối tự phê duyệt

Dưới đây là một schema minh họa do ứng dụng tự định nghĩa, không phải một chuẩn bắt buộc. Principal được xác thực ở ranh giới API công khai là u-17; refund-api là dịch vụ đang thực thi.

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-8f31",
  "eventType": "REFUND_APPROVAL_DENIED",
  "occurredAt": "2026-11-22T08:15:30.120Z",
  "recordedAt": "2026-11-22T08:15:30.124Z",
  "requestId": "req-731",
  "commandId": "cmd-882",
  "actor": {
    "authenticatedPrincipal": {
      "id": "u-17",
      "type": "HUMAN",
      "issuer": "identity-main"
    },
    "initiatingActorId": "u-17",
    "effectiveSubjectId": "u-17",
    "executingServiceId": "refund-api",
    "delegation": null
  },
  "tenant": {
    "selectedTenantId": "t-a",
    "resourceTenantId": "t-a"
  },
  "action": "refund.approve",
  "resource": {
    "type": "REFUND",
    "id": "R-420",
    "versionObserved": 8
  },
  "authorization": {
    "evaluatedRoles": ["REFUND_APPROVER"],
    "evaluatedPermissions": ["refund.approve"],
    "scope": {
      "tenantId": "t-a"
    },
    "policyVersion": "refund-approval-v7",
    "decision": "DENY",
    "reasonCode": "APPROVER_IS_REQUESTER"
  },
  "businessFacts": {
    "stateObserved": "PENDING_APPROVAL",
    "requestedBy": "u-17",
    "amountMinor": 750000,
    "currency": "VND"
  },
  "outcome": "DENIED"
}
~~~

Ở ví dụ này, số tiền được biểu diễn bằng đơn vị tiền tệ nhỏ nhất theo quy ước của ứng dụng; với VND trong ví dụ, một đơn vị là một đồng. Quy ước phải rõ để tránh diễn giải sai dữ liệu.

Bản ghi giải thích được rằng u-17 có permission liên quan nhưng vẫn bị từ chối do quy tắc tách biệt người yêu cầu và người phê duyệt. **Có quyền chức năng** và **được phép thực hiện một chuyển trạng thái cụ thể** là hai điều kiện khác nhau.

Các trường **businessFacts** chỉ chứa dữ liệu cần để giải thích quyết định. Trong tình huống truy cập trái tenant hoặc đối tượng không tồn tại, không tự đọc thêm dữ liệu ngoài phạm vi cho phép chỉ để điền đủ schema. Dùng định danh đối tượng được yêu cầu đã kiểm soát định dạng, mã lý do phù hợp và mức chi tiết mà hệ thống thực sự có quyền biết.

Bản ghi audit nội bộ có thể chi tiết hơn phản hồi cho client. Không trả nguyên bản ghi này ra API nếu nó làm lộ sự tồn tại của tài nguyên, quyền nội bộ hoặc dữ liệu của người khác.

## 7. Tổ chức mã Java để không ghi nhầm tác nhân

Ví dụ dưới đây là mã giả theo phong cách Java. Các lớp repository, policy, transaction và journal là hợp đồng minh họa, không phải API thư viện có sẵn.

Một command từ client chỉ mô tả thao tác được yêu cầu:

~~~java
record ApproveRefundCommand(
    String refundId,
    long expectedVersion,
    String reason
) {}
~~~

Danh tính được truyền riêng từ thành phần xác thực và giải quyết đại diện có thẩm quyền:

~~~java
record VerifiedActor(
    String authenticatedPrincipalId,
    String initiatingActorId,
    String effectiveSubjectId,
    String executingServiceId,
    String tenantId,
    String verifiedDelegationId
) {}
~~~

Tên **VerifiedActor** không tự tạo ra tính an toàn. Chỉ thành phần đã xác thực và kiểm chứng quan hệ đại diện mới được tạo đối tượng này trong luồng xử lý; không deserialize nó trực tiếp từ body của client.

Một luồng xử lý có thể được tổ chức như sau:

~~~java
ApprovalResult approve(
        ApproveRefundCommand command,
        VerifiedActor actor) {

    ApprovalAttempt attempt = transactions.required(() -> {
        Refund refund = refunds.findForUpdate(
            command.refundId(), actor.tenantId());

        // Policy bao gồm quyền, tenant, đại diện, trạng thái,
        // người yêu cầu và phiên bản mong đợi.
        Decision decision = policy.evaluateApproval(
            actor, refund, command.expectedVersion());

        // Snapshot giữ đúng các dữ liệu đã dùng trong decision.
        ActorAuditContext context =
            auditContext.snapshot(actor, decision);

        if (!decision.allowed()) {
            return ApprovalAttempt.denied(
                events.denied(command, context, decision));
        }

        long versionBefore = refund.version();

        refund.approveBy(actor.effectiveSubjectId());
        refunds.save(refund);

        AuditEvent event = events.approved(
            command, context, decision,
            versionBefore, refund.version());

        // Cùng transaction với cập nhật hoàn tiền.
        auditOutbox.append(event);

        return ApprovalAttempt.approved(refund.id());
    });

    if (attempt.denied()) {
        // Đường ghi bền vững riêng, sau khi transaction trên kết thúc.
        denialJournal.record(attempt.denialEvent());
        throw new ApprovalDeniedException();
    }

    return ApprovalResult.approved(attempt.refundId());
}
~~~

Các điều kiện của ví dụ:

- **findForUpdate** phải dùng cách đọc và kiểm soát cạnh tranh phù hợp. Khi không tìm thấy đối tượng trong phạm vi tenant, policy tạo quyết định từ chối mà không giả định đối tượng tồn tại.
- **policy.evaluateApproval** không chỉ kiểm tra role. Nó áp dụng business invariants và các điều kiện trên tài nguyên thực tế.
- Các nhánh trong transaction trước khi cho phép không tạo thay đổi nghiệp vụ. Nhánh từ chối trả kết quả ra ngoài rồi mới phát sinh lỗi cho client.
- **refund.approveBy** chỉ lưu chủ thể hiệu lực theo mô hình miền. Audit vẫn giữ người thực hiện thật; nếu bảng nghiệp vụ cần truy vấn cả hai thì lưu hai trường có nghĩa rõ ràng.
- **auditOutbox.append** và **refunds.save** phải tham gia cùng transaction. Thành công của hàm chỉ được trả sau khi transaction commit thành công.
- **denialJournal.record** có đường lưu bền vững độc lập với transaction nghiệp vụ đã kết thúc. Không giả định một lệnh gọi logger thông thường bảo đảm điều này.
- Mã chưa triển khai idempotency, chuyển tiếp liên dịch vụ hoặc toàn bộ nhánh lỗi; các phần đó cần hợp đồng riêng như các mục sau.

Lỗi hay gặp là ghi audit vào cùng transaction rồi ném exception để rollback toàn bộ. Kết quả là bản ghi từ chối cũng mất theo. Một lỗi khác là ghi “APPROVED” trước commit: nếu transaction thất bại, audit lại tuyên bố một thay đổi chưa từng có hiệu lực.

Đối với sự kiện thành công cần tính nhất quán chặt với dữ liệu nghiệp vụ, outbox có thể giữ bản ghi cùng commit rồi chuyển tiếp sau. Đối với sự kiện từ chối hoặc lỗi, cần đường ghi riêng và quy tắc xử lý lỗi rõ ràng. Nếu journal bị lỗi, hệ thống không được báo rằng đã ghi thành công; lựa chọn từ chối thao tác, đưa vào bộ đệm bền vững hay phát cảnh báo phụ thuộc vào yêu cầu của loại hành động.

## 8. Đại diện và impersonation: giữ được người thao tác thật

Cơ chế “đăng nhập như khách hàng” thường làm mất dấu tác nhân nếu ứng dụng thay toàn bộ danh tính hiện tại bằng khách hàng. Khi đó:

- Log chỉ ghi khách hàng dù nhân viên hỗ trợ là người thực hiện.
- Quy tắc không tự phê duyệt có thể chỉ so sánh chủ thể hiệu lực.
- Phiên hỗ trợ hết hạn nhưng công việc nền vẫn dùng dữ liệu đại diện cũ.
- Một chuỗi chuyển tiếp làm mất grant hoặc mở rộng quyền ngoài phạm vi ban đầu.

Ngữ cảnh đại diện nên ghi tham chiếu grant hoặc phiên hỗ trợ, chủ thể khởi tạo, chủ thể được đại diện, phạm vi đã xác minh và thông tin cần thiết về thời hạn. Nếu có nhiều bước ủy quyền, cần giữ chuỗi có giới hạn và kiểm chứng từng quan hệ; không chấp nhận một danh sách actor do client tùy ý gửi.

Chẳng hạn, u-17 là người tạo hoàn tiền. Nếu u-17 có thể đại diện cho manager-42, việc chỉ kiểm tra **effectiveSubjectId != requestedBy** sẽ cho kết quả sai về tính độc lập. Chính sách phê duyệt cần xét người thao tác thật và chuỗi đại diện theo mô hình tách biệt nhiệm vụ.

Một lựa chọn nghiệp vụ là cấm phê duyệt hoàn tiền trong phiên impersonation. Nếu tổ chức cho phép một số hình thức ủy quyền phê duyệt, phải mô hình hóa rõ ai được đại diện, phạm vi nào và điều kiện độc lập nào còn phải được thỏa mãn. Audit phải ghi đúng chế độ đó; không dùng việc có audit để thay thế điều kiện cho phép.

Trường **reason** do nhân viên nhập có thể cung cấp ngữ cảnh điều tra, nhưng không phải bằng chứng rằng họ có quyền. Mã ticket hỗ trợ cũng cần được kiểm chứng nếu nó là điều kiện của chính sách.

## 9. Qua nhiều dịch vụ và tác vụ bất đồng bộ

Xét chuỗi:

~~~text
u-17 -> refund-api -> hàng đợi -> refund-worker -> payment-service
~~~

Tại refund-api, principal trực tiếp có thể là u-17. Tại payment-service, principal trực tiếp thường là workload của refund-worker. Nếu chỉ giữ principal hiện tại, người điều tra không biết ai đã khởi tạo nghiệp vụ; nếu chỉ giữ u-17, họ không biết workload nào đã thực thi bước thanh toán.

Mỗi bước cần giữ mạch liên kết và bổ sung thông tin của ranh giới hiện tại:

- Danh tính workload gửi hoặc thực thi bước này.
- Tác nhân khởi tạo và chủ thể hiệu lực có nguồn gốc đã kiểm chứng.
- Tham chiếu đại diện còn có ý nghĩa với bước này.
- Command ID, message ID, causation ID và tham chiếu sự kiện trước.
- Thời điểm chấp nhận yêu cầu, thời điểm xử lý, số lần thử và quyết định ở bước hiện tại.

Không tin một trường **initiatingActorId** trong message chỉ vì message nằm trong hàng đợi. Cần kiểm soát producer, xác thực nguồn và bảo vệ tính toàn vẹn của envelope theo kiến trúc. Dịch vụ nhận vẫn kiểm tra quyền gọi của workload và điều kiện nghiệp vụ của bước mình chịu trách nhiệm.

### 9.1. Quyền được đánh giá lúc nào?

Cần xác định rõ một công việc dùng thẩm quyền đã được chấp nhận ở thời điểm enqueue, hay phải kiểm tra lại khi thực thi:

- **Chấp nhận quyền tại thời điểm nhận lệnh:** lưu quyết định hoặc bản ủy quyền có phạm vi và thời hạn phù hợp. Worker kiểm tra lệnh còn hợp lệ và chưa bị hủy theo chính sách.
- **Kiểm tra lại tại thời điểm thực thi:** worker đánh giá quyền hiện tại trước khi tạo tác động. Audit ghi cả nguồn khởi tạo ban đầu và quyết định mới.

Đây là lựa chọn nghiệp vụ. Không tự suy ra rằng một token còn hạn hoặc một message cũ luôn cho phép thanh toán. Cũng không nên lưu access token hay refresh token vào audit để “dùng lại sau”.

Nếu tác vụ bị từ chối do quyền đã bị thu hồi, sự kiện phải thể hiện người khởi tạo ban đầu, workload thực thi và lý do từ chối tại thời điểm chạy.

### 9.2. Không dùng thread-local như nguồn sự thật duy nhất

Trong ứng dụng Java dùng thread pool, callback hoặc luồng phản ứng, công việc sau có thể chạy trên thread khác, hoặc thread cũ được tái sử dụng cho người dùng khác.

MDC có thể giúp thêm trường vào application log, nhưng không nên là nguồn duy nhất để quyết định ai có quyền hoặc ai là actor của audit. Nên truyền ngữ cảnh bất biến một cách tường minh hoặc dùng cơ chế propagation có hợp đồng rõ ràng. Context gắn với thread cần được dọn trong **finally** và được kiểm tra qua các đường bất đồng bộ.

Một bản ghi của tenant t-b mang **actorId** từ yêu cầu trước của tenant t-a là lỗi audit nghiêm trọng, dù chỉ xuất hiện trong một số lần xử lý đồng thời.

## 10. Yêu cầu trùng, retry và idempotency

Cần phân biệt **lần thử thực hiện** với **tác động nghiệp vụ đã commit**.

Giả sử client gọi phê duyệt ba lần vì timeout:

- Có thể có ba sự kiện ghi nhận các lần thử hoặc quyết định tương ứng.
- Chỉ được có số lần chuyển trạng thái có hiệu lực theo hợp đồng idempotency, thường là một cho cùng lệnh.
- Các sự kiện phải liên kết được với command và kết quả ban đầu.
- Lần trả lại kết quả đã có không được ghi như một lần phê duyệt mới.

Idempotency key không phải bằng chứng về danh tính hoặc quyền. Trước khi trả kết quả đã lưu, vẫn phải kiểm tra người gọi có quyền nhận kết quả trong phạm vi tương ứng.

Phạm vi chống trùng có thể bao gồm tenant, loại hành động, chủ thể phù hợp và khóa. Khi hành động phụ thuộc vào danh tính người khởi tạo hoặc quan hệ đại diện, hợp đồng cần xử lý cả các khác biệt đó. Không có một tổ hợp khóa phù hợp cho mọi hệ thống.

Ví dụ, u-18 dùng lại key của u-17 không được nhận kết quả nhạy cảm của u-17 chỉ vì chuỗi key trùng nhau. Việc cùng người gọi dùng một key với payload hoặc ngữ cảnh đại diện khác cũng phải được xử lý theo quy tắc xung đột đã định nghĩa.

Trong audit có thể ghi:

~~~text
attemptId           = attempt-3
commandId           = cmd-882
outcome             = REPLAYED_RESULT
originalEventId     = evt-approved-91
currentCaller       = danh tính đã xác minh của lần gọi này
originalActor       = lấy từ bản ghi gốc được bảo vệ, nếu cần giải thích
businessEffectCount = không tăng do lần replay
~~~

Đây là cách minh họa ý nghĩa, không phải yêu cầu phải có trường đếm trong schema. Bản ghi gốc giữ nguyên actor ban đầu; lần gọi lại có actor context riêng. Không sửa actor của sự kiện cũ thành người gọi lần gần nhất.

Publisher outbox và consumer cũng có thể giao nhận lặp. Dùng định danh sự kiện ổn định cùng cơ chế chống trùng phù hợp để không biến một sự kiện đã commit thành nhiều tác động hoặc nhiều bản ghi biểu thị những lần phê duyệt khác nhau.

## 11. Dữ liệu nhạy cảm, tính toàn vẹn và giới hạn của bằng chứng

### 11.1. Thu thập vừa đủ

Không ghi access token, refresh token, cookie phiên, mật khẩu, OTP, khóa API hoặc toàn bộ header xác thực. Không lưu nguyên credential đại diện vào audit.

Ưu tiên ID ổn định và tham chiếu được kiểm soát thay vì sao chép email, số điện thoại, địa chỉ hoặc hồ sơ đầy đủ. Ngay cả định danh nội bộ và IP cũng có thể là dữ liệu nhạy cảm; quyền đọc, thời gian lưu và mục đích sử dụng phải được xác định.

Không nhúng toàn bộ request body nếu chỉ cần biết ai sửa giá, sửa đối tượng nào, từ giá nào sang giá nào và theo quyền nào. Với ghi chú tự do, giới hạn độ dài, dùng dữ liệu có cấu trúc và xử lý ký tự điều khiển để tránh log injection. Giao diện xem audit phải escape nội dung khi hiển thị.

### 11.2. Bảo vệ đường ghi và đường đọc

Một schema tốt không giúp nhiều nếu client được gửi sự kiện “đã phê duyệt” trực tiếp vào cùng kho audit mà không kiểm soát nguồn.

Cần giới hạn thành phần được phát sự kiện, ghi nhận nguồn phát và bảo vệ tính toàn vẹn khi chuyển tiếp. Quyền đọc lịch sử audit cũng phải có phạm vi; người có quyền xem một hoàn tiền chưa chắc được xem toàn bộ thông tin nhân viên hỗ trợ hoặc hoạt động liên tenant.

Cơ chế lưu chỉ thêm, phân quyền tách biệt hoặc xác thực tính toàn vẹn có thể hỗ trợ phát hiện sửa đổi. Nếu dùng hash chain hay chữ ký, phải quản lý khóa và điểm kiểm chứng phù hợp. Một chuỗi hash mà kẻ tấn công có thể sửa toàn bộ rồi tính lại không tự tạo bằng chứng chống sửa đổi.

### 11.3. Thời gian và thứ tự cần được giải thích

Ghi thời gian theo một quy ước thống nhất, chẳng hạn UTC, và phân biệt:

- Thời điểm sự kiện hoặc quyết định xảy ra.
- Thời điểm kho audit nhận bản ghi.
- Thời điểm message được xử lý nếu có trì hoãn.

Timestamp ở các dịch vụ có thể lệch hoặc đến không đúng thứ tự. Dùng thêm phiên bản tài nguyên, command ID và liên kết nhân quả để dựng chuỗi thao tác. Một trace ID dùng chung giúp liên kết, nhưng không chứng minh hai sự kiện có cùng quyền hoặc cùng tác nhân đã xác minh.

### 11.4. Ghi nhận không đồng nghĩa quan sát được mọi thao tác

Nếu người có quyền truy cập cơ sở dữ liệu sửa giá trực tiếp, bản ghi actor ở tầng API không tự xuất hiện. Cần nhận diện đường tác động ngoài ứng dụng và bổ sung nguồn audit tương ứng theo phạm vi hệ thống.

Nếu một tài khoản bị chiếm đoạt, audit có thể chứng minh hệ thống đã xử lý hành động dưới danh tính đó và phương thức xác thực nào đã được dùng. Nó không tự chứng minh chủ tài khoản thực sự chủ động thực hiện hành động. Kết luận điều tra cần tôn trọng giới hạn này.

## 12. Tình huống kiểm thử khi triển khai

Các tình huống dưới đây dùng để thiết kế kiểm thử cho một triển khai thực tế. Chúng không hàm ý mã giả trong bài đã được chạy.

| Tình huống | Hành vi nghiệp vụ cần xác minh | Bằng chứng actor context cần có |
|---|---|---|
| Client gửi actorId của quản lý | Không dùng trường tự khai để nâng quyền hoặc vượt quy tắc | Principal và người khởi tạo vẫn là người đã xác thực |
| Người tạo tự phê duyệt | Bị chặn dù có permission phê duyệt | Quy tắc bị vi phạm, người yêu cầu và actor đã xác minh |
| Thay tenant hoặc ID đối tượng | Không thao tác hoặc lấy kết quả ngoài phạm vi | Tenant đã xác minh, định danh được yêu cầu và mã lý do phù hợp |
| Nhân viên đại diện khách hàng | Chỉ cho phép trong phạm vi grant hoặc phiên hỗ trợ | Cả nhân viên, chủ thể hiệu lực và tham chiếu đại diện |
| Dùng đại diện để tự phê duyệt | Không tạo ra tính độc lập giả | Người thao tác thật và quan hệ đại diện đã tham gia quyết định |
| Quyền đổi sau khi enqueue | Hành vi đúng mô hình đánh giá quyền đã chọn | Quyết định lúc nhận lệnh và lúc thực thi khi có yêu cầu |
| Hai yêu cầu đồng thời | Không tạo chuyển trạng thái trái invariant | Actor từng lần thử, phiên bản quan sát và kết quả commit |
| Retry cùng lệnh | Không tạo thêm tác động nghiệp vụ | Lần replay liên kết kết quả gốc, actor gốc không bị sửa |
| Người khác dùng cùng key | Không lộ kết quả hoặc nhận nhầm quyền | Actor hiện tại, phạm vi kiểm tra và kết quả từ chối hoặc xung đột |
| Transaction rollback | Không xuất hiện sự kiện khẳng định thành công đã commit | Sự kiện từ chối hoặc lỗi có ngữ nghĩa riêng khi cần |
| Worker nhận lại message | Không tạo lại tác động đã hoàn tất | Message hoặc event ID ổn định, workload và mạch khởi tạo |
| Thread pool dùng lại thread | Không trộn người dùng hoặc tenant | Actor context của từng yêu cầu được cô lập |
| Yêu cầu chưa xác thực | Không gán tên tự khai thành actor đã xác thực | Actor chưa xác định; dữ liệu tự khai ở trường riêng nếu cần |
| Ghi chú chứa xuống dòng hoặc HTML | Không tạo dòng log giả hay mã hiển thị có hại | Nội dung được giới hạn, ghi có cấu trúc và hiển thị an toàn |
| Journal hoặc publisher gặp lỗi | Không báo sai mức bảo đảm audit | Outbox còn dữ liệu để chuyển tiếp hoặc có tín hiệu lỗi phù hợp |

Khi kiểm thử, cần đối chiếu hành vi nghiệp vụ với nội dung audit. Chỉ kiểm tra “có một dòng log” không phát hiện được các lỗi như đúng quyền nhưng sai actor, đúng actor nhưng sai tenant, hoặc ghi thành công trước khi transaction rollback.

## 13. Checklist thiết kế cho một hành động nhạy cảm

Trước khi áp dụng vào hành động sửa giá, chuyển tiền, phê duyệt hoặc thay đổi quyền, hãy trả lời:

1. Danh tính nào được xác thực tại từng ranh giới, và nguồn nào có thẩm quyền xác nhận?
2. Người khởi tạo, chủ thể hiệu lực và dịch vụ thực thi có được phân biệt không?
3. Tenant và quyền theo đối tượng có được xác minh bằng dữ liệu có thẩm quyền không?
4. Ngữ cảnh đại diện có giữ được người thao tác thật, phạm vi và điều kiện tách biệt nhiệm vụ không?
5. Bản ghi có dùng đúng snapshot đã tham gia quyết định, gồm phiên bản chính sách và các dữ kiện cần thiết không?
6. Sự kiện thành công có nhất quán với commit; sự kiện từ chối có sống được qua rollback không?
7. Qua hàng đợi, có bảo toàn nguồn khởi tạo, nguồn thực thi và quy tắc đánh giá quyền theo thời điểm không?
8. Retry có liên kết kết quả gốc mà không sửa actor cũ hoặc lộ dữ liệu cho người khác không?
9. Dữ liệu đã đủ để điều tra mà không chứa credential, payload dư thừa hoặc thông tin vượt phạm vi không?
10. Người đọc audit có hiểu được mức tin cậy, giới hạn bằng chứng và các đường tác động ngoài ứng dụng không?

Một ngữ cảnh tác nhân có giá trị khi nó giải thích được ai đã được hệ thống xác minh, ai thực sự khởi tạo hoặc đại diện, trong phạm vi nào, theo quyết định nào và tạo ra kết quả gì. Thiết kế đó phải đi cùng việc thực thi invariants; việc lưu lịch sử không thể bù cho một quy tắc nghiệp vụ bị bỏ qua.
