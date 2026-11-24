# Transaction auditability

## 1. Khả năng kiểm toán của transaction là gì?

Transaction auditability là khả năng tái dựng và kiểm chứng một thay đổi nghiệp vụ: ai khởi tạo, ai thực thi, tác động lên đối tượng nào, dựa trên quyền và phê duyệt nào, thay đổi gì, và có bằng chứng nào cho thấy kết quả đã được ghi nhận bền vững.

Trong một hệ thống hoàn tiền, câu hỏi không chỉ là “có dòng log hoàn tiền không?”. Cần xác định:

- Yêu cầu đến từ tenant và chủ thể nào?
- Ý định hoàn tiền đã được phê duyệt đúng số tiền và đúng phiên bản chưa?
- Transaction đã chuyển trạng thái nào sang trạng thái nào?
- Đó là tiếp nhận yêu cầu thực thi hay nhà cung cấp đã hoàn tiền thật sự?
- Các lần retry có tạo thêm tác dụng hay chỉ trả lại kết quả cũ?
- Nếu có sự cố, dữ liệu nghiệp vụ, audit và hệ thống bên ngoài có khớp nhau không?

Khả năng kiểm toán hỗ trợ phát hiện bỏ qua phê duyệt, chỉnh giá trái phép, thao tác sai quyền và yêu cầu trùng. Tuy nhiên, audit không thay thế cơ chế ngăn chặn: một lịch sử đầy đủ về hai lần hoàn tiền sai vẫn là một vi phạm nghiệp vụ.

## 2. Phân biệt log vận hành, audit và bằng chứng commit

| Loại dữ liệu | Mục đích chính | Giới hạn |
|---|---|---|
| Log vận hành | Chẩn đoán exception, độ trễ, kết nối và lỗi triển khai | Có thể bị sampling, mất hoặc ghi trước khi transaction hoàn tất |
| Trace | Liên kết các bước xử lý trong một luồng phân tán | Không tự chứng minh nghiệp vụ đã commit hoặc dữ liệu không bị sửa |
| Audit nghiệp vụ | Ghi lại hành động, quyết định và thay đổi có ý nghĩa | Cần được gắn đúng với dữ liệu thật, có kiểm soát truy cập và vòng đời |
| Dữ liệu nghiệp vụ/sổ giao dịch | Nguồn sự thật về trạng thái và tác dụng theo thiết kế | Không nhất thiết chứa đủ bối cảnh ai, tại sao và dựa trên bằng chứng nào |
| Thông tin transaction của database | Hỗ trợ phân tích commit, rollback hoặc luồng thay đổi | Phụ thuộc sản phẩm; không thay thế ngữ cảnh quyền và ý định nghiệp vụ |

Ví dụ:

```text
10:00:01 application: refund succeeded
10:00:02 database: transaction bị hủy vì lỗi ràng buộc
```

Nếu dòng log được ghi trước commit, thông điệp đó không chứng minh hoàn tiền nội bộ đã thành công. Ngược lại, transaction có thể đã commit nhưng log sau commit bị mất vì process chết.

Thiết kế cần chỉ rõ bằng chứng nào chứng minh một thay đổi đã commit, bằng chứng nào chỉ ghi nhận một lần thử và trường hợp nào vẫn chưa xác định được kết quả.

## 3. Xác định các câu hỏi kiểm toán từ bất biến nghiệp vụ

Nên bắt đầu bằng quy tắc cần bảo vệ rồi xác định dữ liệu kiểm chứng, thay vì thu thập toàn bộ request theo thói quen.

| Bất biến | Bằng chứng cần liên kết |
|---|---|
| Không vượt số tiền được phép hoàn | Ý định, số tiền, loại tiền, giới hạn áp dụng và giao dịch đã ghi nhận |
| Không bỏ qua phê duyệt | Định danh phê duyệt, phiên bản ý định được duyệt, người duyệt và điều kiện còn hiệu lực |
| Không thao tác chéo tenant hoặc trái quyền | Tenant, chủ thể hiệu lực, đối tượng đích và quyết định quyền |
| Không chuyển trạng thái sai thứ tự | Trạng thái trước/sau, phiên bản đối tượng và tên hành động |
| Không tạo tác dụng lặp | Operation ổn định, ý định nghiệp vụ, các lần thử và kết quả tương ứng |
| Không báo thành công giả | Audit được commit cùng dữ liệu hoặc có bằng chứng kết quả bên ngoài rõ ràng |

Không phải mọi bằng chứng đều phải sao chép đầy đủ vào một hàng audit. Có thể lưu tham chiếu đến bản ghi phê duyệt hoặc chính sách được giữ phiên bản, nếu các tham chiếu đó vẫn truy cập và kiểm chứng được trong thời hạn cần thiết.

Một mã phê duyệt trỏ tới bản ghi có thể bị sửa mà không có lịch sử không đủ để chứng minh trước đây đã phê duyệt nội dung gì. Cần lưu phiên bản hoặc ảnh chụp tối thiểu của thông tin có ý nghĩa.

## 4. Mô hình định danh để nối các mảnh bằng chứng

### 4.1. Không dùng một ID cho mọi khái niệm

| Định danh | Phạm vi và ý nghĩa |
|---|---|
| `request_id` hoặc `attempt_id` | Một lần nhận hoặc thử xử lý request |
| `operation_id` | Một ý định thực thi ổn định xuyên các lần retry của cùng nghiệp vụ |
| `event_id` | Một sự kiện audit hoặc sự kiện nghiệp vụ cụ thể |
| `transaction_group_id` | Nhóm thay đổi mà ứng dụng dự kiến commit trong cùng transaction |
| `aggregate_id`, `aggregate_version` | Đối tượng nghiệp vụ và phiên bản gắn với chuyển trạng thái |
| `causation_id` | Sự kiện hoặc lệnh trực tiếp gây ra sự kiện hiện tại |
| `correlation_id` | Liên kết rộng hơn, ví dụ nhiều operation của một luồng đơn hàng |
| `provider_reference` | Định danh tra cứu kết quả tại hệ thống bên ngoài |

Một operation có thể có nhiều attempt và nhiều sự kiện. Vì thế không đặt unique trên `operation_id` trong bảng audit nếu nghiệp vụ cần ghi cả tiếp nhận, thực thi và xác nhận kết quả cho cùng operation.

ID transaction nội bộ của database có thể hữu ích khi điều tra, nhưng không nên mặc định nó là định danh nghiệp vụ toàn cục, tồn tại vĩnh viễn hoặc duy nhất xuyên mọi lần khôi phục. Đặc tính của nó phụ thuộc database và cách vận hành.

`transaction_group_id` do ứng dụng cấp cũng chỉ thể hiện nhóm mà ứng dụng liên kết. Bản thân nó không chứng minh các câu lệnh thật sự dùng chung connection hoặc cùng commit; bằng chứng nằm ở ranh giới transaction thực tế.

### 4.2. Giữ danh tính chủ thể đáng tin cậy

Audit cần phân biệt người khởi tạo và tác nhân thực thi. Một nhân viên tạo lệnh nhưng worker thực thi sau đó không nên bị ghi đơn giản là “worker đã quyết định hoàn tiền”.

Có thể cần ghi:

```text
tenant_id
initiated_by_actor_id
effective_actor_type / effective_actor_id
service_identity
delegation hoặc impersonation reference nếu có
authorization_decision_id
policy_version
approval_reference và approval_version
```

Các giá trị này phải đến từ ngữ cảnh xác thực, ủy quyền và dữ liệu server đáng tin cậy. Không lấy `actor_id` hoặc `approved_by` trong request client làm bằng chứng người thực hiện hoặc người phê duyệt.

IP và User-Agent có thể hỗ trợ điều tra nhưng không phải danh tính chắc chắn. Khi có reverse proxy, chỉ tin header chuyển tiếp theo cấu hình nguồn proxy đáng tin cậy.

## 5. Audit thay đổi đã áp dụng phải gắn với transaction

Khi thay đổi nghiệp vụ và audit nằm trong cùng database, một thiết kế trực tiếp là ghi cả hai trong cùng transaction:

```text
BEGIN
  nhận quyền cho operation
  khóa/kiểm tra đối tượng, quyền và phê duyệt
  thực hiện chuyển trạng thái có điều kiện
  INSERT audit mô tả đúng chuyển trạng thái đó
  ghi kết quả idempotency hoặc liên kết operation
COMMIT
```

Nếu insert audit bắt buộc thất bại, transaction phải bị hủy theo chính sách của hành động đó. Nếu thay đổi nghiệp vụ rollback, sự kiện mô tả thay đổi đã áp dụng cũng rollback.

Bản ghi được insert trước lệnh `COMMIT`, nhưng chỉ trở thành bằng chứng bền vững của thay đổi khi transaction chung commit. Vì thế không cần ghi “commit đã xảy ra lúc này” vào một timestamp lấy trước commit.

Các điều kiện của bảo đảm này cần được xác minh:

- Cả audit và dữ liệu nghiệp vụ sử dụng cùng transaction thực tế.
- Không có connection autocommit hoặc transaction độc lập ngoài dự kiến.
- Exception khi ghi audit không bị nuốt rồi cho phép commit thiếu audit.
- Audit mô tả kết quả từ thay đổi thực tế, không chỉ lặp lại yêu cầu client.

### 5.1. Vì sao không ghi audit thành công bằng transaction độc lập?

```text
Transaction A: sửa nghiệp vụ, chưa commit
Transaction B: ghi "đã thành công" rồi commit độc lập
Transaction A: gặp lỗi rồi rollback
```

Audit còn tồn tại nhưng trạng thái mà nó tuyên bố không tồn tại. Ở chiều ngược lại, commit nghiệp vụ rồi mới mở transaction ghi audit tạo khoảng trống nếu process chết giữa hai bước.

Đối với hành động quan trọng, cần audit nguyên tử hoặc một cơ chế thu nhận thay đổi có bảo đảm và quy trình đối soát phù hợp. Log sau commit đơn thuần không đóng được khoảng trống này.

## 6. Lần thử bị từ chối và transaction rollback cần kênh bằng chứng riêng

Nếu audit được ghi trong cùng transaction, rollback cũng hủy audit đó. Đây là hành vi đúng với sự kiện “thay đổi đã áp dụng”, nhưng không đủ để lưu mọi lần cố gắng thao tác trái quyền.

Nên phân biệt các loại bằng chứng:

| Sự kiện | Điều nó khẳng định |
|---|---|
| `REQUEST_RECEIVED` | Hệ thống đã quan sát một lần gửi yêu cầu |
| `AUTHORIZATION_DENIED` | Quyết định quyền từ chối theo ngữ cảnh đã ghi nhận |
| `TRANSACTION_ABORT_OBSERVED` | Có bằng chứng transaction bị hủy, với phạm vi được xác định |
| `TRANSACTION_OUTCOME_UNCERTAIN` | Chưa biết chắc transaction gốc đã commit hay chưa |
| Sự kiện chuyển trạng thái, ví dụ `REFUND_EXECUTION_REQUESTED` | Thay đổi tương ứng đã được áp dụng bền vững khi lưu cùng transaction |
| `PROVIDER_RESULT_CONFIRMED` | Có bằng chứng kết quả từ phía nhận, với định danh liên kết |

Lần thử bị từ chối có thể được ghi qua kênh bảo mật hoặc transaction riêng vì không có thay đổi nghiệp vụ cần commit chung. Nội dung phải phản ánh đúng việc bị từ chối hoặc được quan sát, không tuyên bố một thay đổi nghiệp vụ đã thành công.

Nếu một request vừa sửa dữ liệu rồi phát hiện thiếu quyền, việc ghi audit từ chối không thay thế yêu cầu rollback các thay đổi đó. Cần thiết kế kiểm tra quyền và ranh giới transaction đúng ngay từ đầu.

Với sự cố tiến trình hoặc mạng, không phải lúc nào ứng dụng cũng quan sát được mọi kết quả cuối. Có thể cần dữ liệu database, operation và quy trình đối soát để bổ sung bằng chứng. Không quảng bá rằng một dòng log tự nó chứng minh mọi transaction đều đã được bao phủ.

## 7. Schema audit tối thiểu cho chuyển trạng thái

Ví dụ PostgreSQL sau minh họa bảng audit cho thay đổi nghiệp vụ đã được áp dụng trong transaction chung:

```sql
CREATE TABLE business_audit_events (
    event_id                UUID         PRIMARY KEY,
    tenant_id               UUID         NOT NULL,
    operation_id            UUID         NOT NULL,
    attempt_id              UUID         NOT NULL,
    transaction_group_id    UUID         NOT NULL,
    event_type              VARCHAR(100) NOT NULL,
    schema_version          SMALLINT     NOT NULL,
    aggregate_type          VARCHAR(64)  NOT NULL,
    aggregate_id            UUID         NOT NULL,
    aggregate_version       BIGINT       NOT NULL,
    effective_actor_type    VARCHAR(20)  NOT NULL,
    effective_actor_id      UUID         NOT NULL,
    initiated_by_actor_id   UUID,
    authorization_context   JSONB        NOT NULL,
    reason_code             VARCHAR(100),
    before_snapshot         JSONB,
    after_snapshot          JSONB        NOT NULL,
    recorded_at             TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),

    CHECK (schema_version > 0),
    CHECK (aggregate_version >= 0),
    CHECK (effective_actor_type IN ('USER', 'SERVICE')),
    CHECK (jsonb_typeof(authorization_context) = 'object'),
    CHECK (
        before_snapshot IS NULL
        OR jsonb_typeof(before_snapshot) = 'object'
    ),
    CHECK (jsonb_typeof(after_snapshot) = 'object'),

    UNIQUE (
        tenant_id,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_type
    )
);

CREATE INDEX business_audit_operation_idx
    ON business_audit_events (tenant_id, operation_id);

CREATE INDEX business_audit_aggregate_idx
    ON business_audit_events (
        tenant_id, aggregate_type, aggregate_id, aggregate_version
    );
```

Ràng buộc unique trong ví dụ thể hiện chính sách “một sự kiện cùng loại cho một phiên bản đối tượng”. Nếu một phiên bản cần nhiều sự kiện cùng loại, phải đổi định danh và ràng buộc theo mô hình thật; không áp đặt ví dụ này vào mọi nghiệp vụ.

`recorded_at` là thời điểm câu lệnh ghi audit đánh giá đồng hồ database, không phải thời điểm commit được xác nhận. Không dùng nó để chứng minh thứ tự commit tuyệt đối giữa transaction đồng thời.

`before_snapshot` và `after_snapshot` là các trường được chọn có chủ đích, không phải toàn bộ entity. Không đưa mật khẩu, token, bí mật thanh toán hoặc dữ liệu cá nhân không cần thiết vào JSON.

Ví dụ không dùng khóa ngoại có xóa dây chuyền từ đối tượng nghiệp vụ sang audit. Nếu xóa một đơn hàng làm mất toàn bộ bằng chứng liên quan, thời hạn giữ audit có thể bị phá. Cần thiết kế tham chiếu và chính sách xóa rõ ràng thay vì dựa vào mặc định ORM.

Schema chưa tự bảo đảm dữ liệu là bất biến, chính xác hoặc đã được phân quyền tốt. Các bảo đảm đó cần cơ chế ghi, quyền database và vận hành tương ứng.

## 8. Ghi trước/sau từ dữ liệu thật, không từ suy đoán

Một sự kiện chỉ ghi “đã sửa đơn hàng” thường không đủ kiểm toán. Ngược lại, ghi toàn bộ object có thể lộ dữ liệu và tạo phụ thuộc khó quản lý.

Nên chọn những thay đổi liên quan đến bất biến, chẳng hạn:

```json
{
  "event_type": "REFUND_EXECUTION_REQUESTED",
  "aggregate_version": 8,
  "before": {
    "state": "APPROVED",
    "intent_version": 7
  },
  "after": {
    "state": "EXECUTION_PENDING",
    "intent_version": 8,
    "amount_minor": 150000,
    "currency": "VND"
  },
  "authorization": {
    "decision_reference": "decision-52",
    "approval_reference": "approval-18",
    "approved_intent_version": 7
  }
}
```

Đây là biểu diễn rút gọn nội dung sự kiện, không phải đầy đủ mọi cột của schema. Nó mô tả việc tiếp nhận ý định thực thi hoàn tiền, chưa tuyên bố nhà cung cấp đã hoàn tiền.

Giá trị trước phải đến từ phiên bản dữ liệu được khóa hoặc kiểm soát đồng thời phù hợp. Giá trị sau phải tương ứng với kết quả cập nhật thật, ví dụ từ `UPDATE ... RETURNING` hoặc dữ liệu được xác nhận trong cùng transaction.

Không đọc trạng thái trước từ cache rồi cập nhật một phiên bản database khác mà vẫn ghi hai giá trị như một cặp trước/sau chắc chắn. Nếu optimistic locking báo không cập nhật được dòng nào, không ghi audit như thể chuyển trạng thái đã xảy ra.

Với sự kiện tạo mới, ảnh trước có thể không có. Với dữ liệu lớn, có thể lưu một tập thay đổi hoặc tham chiếu phiên bản bất biến, miễn là người kiểm toán vẫn hiểu được điều gì đã thay đổi và có thể truy xuất bằng chứng cần thiết.

## 9. Mã giả Java: audit và outbox trong cùng transaction

```java
AcceptedOperation requestRefundExecution(Command command, AuthContext auth) {
    return transactions.runAndCommit(() -> {
        TrustedScope scope = scopes.fromAuthenticatedContext(auth);
        Claim claim = idempotency.claimOrFind(scope, command);

        if (claim.hasCompletedResult()) {
            authorization.requireCanReadOperation(auth, claim.operationId());
            return claim.acceptedOperation();
        }

        RefundIntent before = intents.findForUpdate(
            scope.tenantId(), command.intentId()
        );
        authorization.requireCanExecute(auth, before);
        ApprovalEvidence approval = approvals.requireMatching(before);
        refunds.requireBusinessInvariants(before);

        OperationId operationId = claim.operationId();
        RefundIntent after = intents.moveToExecutionPending(
            before, operationId
        );

        AuditEvent event = auditFactory.refundExecutionRequested(
            operationId, claim.attemptId(), auth, approval, before, after
        );
        audit.insertInSameTransaction(event);
        outbox.insertInSameTransaction(event.toExecutionMessage());

        AcceptedOperation accepted = AcceptedOperation.of(operationId);
        idempotency.completeAcceptance(claim, accepted);
        return accepted;
    });
}
```

Đây là mã giả để thể hiện ranh giới. `claimOrFind` phải kiểm tra scope, fingerprint, quyền nhận xử lý và trạng thái đang chạy theo hợp đồng; không phải cứ tìm thấy key là trả kết quả. Các thao tác ghi phải cùng tham gia một transaction thực tế.

`runAndCommit` chỉ trả kết quả cho tầng HTTP sau commit thành công. Nếu không biết commit đã xảy ra chưa, cần tra cứu operation thay vì tạo ý định thực thi mới.

Audit ở đây chứng minh việc chuyển sang `EXECUTION_PENDING` khi transaction commit. Worker thực thi và xác nhận kết quả bên ngoài sẽ tạo những sự kiện riêng, ví dụ chuyển sang `SUCCEEDED` với `provider_reference` đã đối soát.

Không bắt lỗi insert audit rồi tiếp tục commit một thay đổi bắt buộc phải có audit. Cũng không dùng `ON CONFLICT DO NOTHING` một cách máy móc để che mọi lỗi trùng sự kiện: nếu trùng do sai danh tính hoặc sai phiên bản, đó có thể là lỗi cần làm hủy transaction và điều tra.

## 10. Retry, phát lại và sự kiện trùng

### 10.1. Một nghiệp vụ, nhiều lần thử

Giả sử operation đã commit nhưng client không nhận response:

```text
attempt-1 → operation-42 → commit chuyển trạng thái + audit event-81
attempt-2 → operation-42 → đọc kết quả cũ, không chuyển trạng thái mới
```

Lần retry có thể cần một dấu vết quan sát như “đã phát lại kết quả”, nhưng không tạo thêm sự kiện mô tả cùng một thay đổi nghiệp vụ đã xảy ra lần nữa.

Nếu mọi retry đều sinh một `REFUND_EXECUTION_REQUESTED` mới mà không phân biệt phát lại, người kiểm toán có thể hiểu nhầm số lần thực thi. Ngược lại, nếu chỉ đếm số request rồi suy ra số giao dịch, kết luận cũng không đúng.

Khi transaction thật sự rollback trước commit, event tạo trong transaction đó không tồn tại bền vững. Lần thực thi sau có thể tạo event mới; điều cần giữ là danh tính operation và ý nghĩa chuyển trạng thái đã commit, không phải giữ một ID của sự kiện chưa từng commit bằng mọi giá.

### 10.2. Vận chuyển sự kiện thường có thể lặp

Worker outbox có thể gửi event rồi chết trước khi đánh dấu đã gửi. Lần sau gửi lại là hành vi phục hồi dự kiến, không nhất thiết là hai lần nghiệp vụ xảy ra.

Khi xuất sang kho tìm kiếm hoặc hệ thống audit tập trung:

- Giữ `event_id` của sự kiện nguồn qua các lần gửi lại.
- Consumer nhận diện trùng bằng danh tính sự kiện và nguồn phù hợp.
- Nếu consumer cập nhật projection trong database riêng, gắn dấu vết đã nhận với cập nhật đó trong cùng transaction khi có thể.
- Lưu được nguồn và phiên bản schema để không giải thích lại payload cũ bằng cấu trúc mới một cách sai lệch.

“Nhận được hai bản sao event” khác với “có hai giao dịch hoàn tiền”. Tương tự, consumer chỉ giữ một bản sao không chứng minh producer chưa tạo tác dụng ngoài hệ thống hai lần. Cần đối chiếu cả dữ liệu nghiệp vụ và định danh phía nhận.

### 10.3. Thứ tự không thể suy ra chỉ từ timestamp

Event đến trễ, đồng hồ giữa dịch vụ khác nhau hoặc transaction giữ khóa lâu có thể làm thứ tự timestamp khác thứ tự nhận hoặc commit.

Dùng `aggregate_version` để hiểu chuỗi chuyển trạng thái của cùng đối tượng khi mô hình đảm bảo phiên bản tăng nhất quán. Dùng quan hệ nhân quả và định danh thông điệp để nối các bước liên dịch vụ. Không tự áp đặt một thứ tự tuyệt đối toàn hệ thống chỉ từ thời gian ứng dụng.

Nếu dùng dữ liệu commit hoặc change-data-capture của database để bổ sung thứ tự, phải hiểu phạm vi và ngữ nghĩa của dữ liệu đó. Nó không tự cung cấp lý do phê duyệt hoặc danh tính nghiệp vụ đã thiếu ở nguồn.

## 11. Bảo vệ audit khỏi sửa đổi và giả mạo

### 11.1. Append-only là chính sách cần được thực thi

Một bảng đặt tên `audit_events` vẫn có thể bị sửa hoặc xóa nếu tài khoản ứng dụng có quyền tương ứng. Các lớp bảo vệ có thể gồm:

- Tách quyền insert với quyền đọc và quản trị.
- Hạn chế update/delete đối với vai trò ghi audit thường ngày.
- Kiểm soát riêng các công việc retention và migration.
- Lưu bản sao hoặc checkpoint ở miền quyền khác khi yêu cầu chống sửa đòi hỏi.
- Ghi dấu vết thay đổi cấu hình, quyền database và thao tác quản trị liên quan.

Quyền append-only của ứng dụng không ngăn quản trị viên có toàn quyền database chỉnh sửa dữ liệu. Cần nói rõ đối tượng nào được tin cậy và loại sửa đổi nào thiết kế có thể phát hiện.

Trigger audit trong database có thể bao phủ các đường cập nhật mà ứng dụng bỏ sót, nhưng thường không tự biết đầy đủ chủ thể cuối, phê duyệt hoặc lý do nghiệp vụ. Ngữ cảnh truyền vào database phải được thiết lập và làm sạch đúng, đặc biệt khi dùng connection pool.

Không mặc định trigger hoặc ORM listener tự có toàn bộ ý nghĩa nghiệp vụ. Một lần flush có thể sinh nhiều câu SQL cho một hành động, trong khi một hành động cũng có thể cập nhật nhiều đối tượng; cần thiết kế mức sự kiện phù hợp.

### 11.2. Hash chain và chữ ký có giới hạn bảo đảm

Một chuỗi hash có thể liên kết các sự kiện:

```text
hash_n = H(hash_(n-1) || canonical(event_n))
```

Thiết kế phải quy định serialization chuẩn, phiên bản thuật toán, phạm vi chuỗi và cách đồng bộ khi nhiều writer cùng ghi. Những trường định danh, tenant, nội dung thay đổi và ngữ cảnh quan trọng phải được bao phủ đúng, không chỉ hash một message dễ thay thế.

Nếu kẻ tấn công sửa được toàn bộ chuỗi và tính lại mọi hash, một chuỗi nằm hoàn toàn trong cùng miền quyền không đủ phát hiện. Xóa phần đuôi chuỗi cũng có thể không bị phát hiện nếu không có mốc kiểm chứng số lượng hoặc checkpoint ở nơi khác.

Chữ ký hoặc checkpoint được lưu độc lập có thể tăng khả năng phát hiện sửa đổi, nhưng cần bảo vệ khóa, quản lý phiên bản khóa và lưu bằng chứng đủ lâu. Chúng không chứng minh dữ liệu đầu vào ban đầu là đúng nếu bên ghi được phép ký một sự kiện sai.

Hash và chữ ký bảo vệ tính toàn vẹn theo mô hình tin cậy; chúng không mã hóa dữ liệu nhạy cảm và không thay thế kiểm tra quyền thực thi nghiệp vụ.

## 12. Dữ liệu nhạy cảm và quyền đọc audit

Audit có thể chứa lịch sử tài chính, danh tính nhân viên, đối tượng khách hàng và bối cảnh bảo mật. Quyền đọc audit cần được bảo vệ như một chức năng nhạy cảm, không phải một endpoint hỗ trợ ai đăng nhập cũng được xem.

Các yêu cầu thường gặp:

- Cô lập tenant trên mọi truy vấn và đường export.
- Kiểm tra quyền theo vai trò và theo đối tượng/phạm vi dữ liệu.
- Giới hạn trường được trả về theo mục đích sử dụng.
- Dùng truy vấn tham số hóa, phân trang và giới hạn khối lượng.
- Ghi nhận truy cập hoặc xuất dữ liệu nhạy cảm theo chính sách.
- Kiểm soát thời hạn giữ và người được thực hiện xóa theo quy trình.

Không lưu nguyên `Authorization`, cookie, mật khẩu, khóa API, nonce thô hoặc dữ liệu thanh toán bí mật vào audit. Nếu cần liên kết request, dùng định danh nội bộ hoặc dẫn xuất phù hợp thay vì giữ toàn bộ bí mật truyền tải.

Trường lý do hoặc ghi chú do người dùng nhập phải được coi là dữ liệu không tin cậy. Giới hạn độ dài, ghi theo cấu trúc và hiển thị an toàn để tránh làm sai cấu trúc log hoặc chèn nội dung nguy hiểm vào giao diện xem audit.

Việc che dữ liệu ở màn hình không xóa dữ liệu thô đã lưu. Cần giảm thiểu ngay tại nguồn và đánh giá cả bản sao tìm kiếm, export, backup và hệ thống quan sát.

## 13. Đối soát audit với dữ liệu nghiệp vụ

### 13.1. Tìm thay đổi quan trọng thiếu audit

Ví dụ hệ thống có bảng `refund_operations` với trạng thái tiếp nhận bền vững, có thể kiểm tra thiếu sự kiện tiếp nhận:

```sql
SELECT operation.tenant_id,
       operation.operation_id
FROM refund_operations AS operation
WHERE operation.acceptance_state = 'ACCEPTED'
  AND NOT EXISTS (
      SELECT 1
      FROM business_audit_events AS audit
      WHERE audit.tenant_id = operation.tenant_id
        AND audit.operation_id = operation.operation_id
        AND audit.event_type = 'REFUND_EXECUTION_REQUESTED'
  );
```

Bảng operation trong ví dụ là mô hình minh họa, không được định nghĩa đầy đủ bởi schema audit phía trên. Truy vấn chỉ tìm thiếu một loại bằng chứng, chưa xác minh nội dung, quyền, phiên bản hoặc tác dụng bên ngoài là đúng.

Điều kiện đối soát phải xét thời hạn retention, dữ liệu được lưu trữ lạnh và quy tắc xóa. Không báo một audit đã được chuyển sang kho lưu trữ hợp lệ là “mất dữ liệu” chỉ vì tìm trong bảng đang hoạt động không thấy.

### 13.2. Tìm audit không khớp dữ liệu thật

Cần kiểm tra thêm những trường hợp:

- Audit tuyên bố chuyển trạng thái nhưng không có operation hoặc lịch sử nghiệp vụ tương ứng.
- Amount/currency trong audit khác dữ liệu giao dịch gắn với cùng ý định.
- Phiên bản ý định được phê duyệt không khớp phiên bản đã áp dụng.
- Một operation có nhiều kết quả cuối mâu thuẫn.
- Provider reference trỏ tới kết quả có số tiền hoặc người nhận khác.
- Chuỗi phiên bản của đối tượng thiếu bước hoặc có bước không hợp lệ theo state machine.

Không dùng trạng thái hiện tại để kết luận mọi trạng thái trước đây trong audit phải giống nó. Một ý định từng `EXECUTION_PENDING` rồi chuyển sang `SUCCEEDED` là bình thường. Cần đối chiếu theo lịch sử, phiên bản và quan hệ nhân quả.

Audit cũng không nên tự được coi là sổ tài chính chỉ vì có trường số tiền. Tổng tiền thực tế cần đối chiếu với nguồn giao dịch được thiết kế làm nguồn thẩm quyền; projection audit có thể trễ hoặc cần rebuild.

### 13.3. Không tự sửa sai lệch bằng cách xóa bằng chứng

Khi phát hiện mâu thuẫn, giữ lại sự kiện gốc và bổ sung sự kiện điều chỉnh/đối soát có lý do và tham chiếu phù hợp. Nếu cần sửa dữ liệu nghiệp vụ, áp dụng quyền, phê duyệt và lệnh bù theo quy tắc.

Không xóa một event chỉ để báo cáo hết chênh lệch. Thay đổi quản trị phải có dấu vết về người thực hiện, bằng chứng và kết luận; không giả vờ transaction gốc đã diễn ra khác đi.

## 14. Commit chưa rõ, rollback và khôi phục sự cố

### 14.1. Mất xác nhận commit

Nếu ứng dụng mất kết nối lúc commit, một dòng log lỗi không đủ để khẳng định rollback. Tra cứu operation, dữ liệu nghiệp vụ và audit đã commit trên nguồn có thẩm quyền.

Nếu audit và nghiệp vụ được ghi đúng cùng transaction, sự hiện diện của chúng trong trạng thái đã commit là bằng chứng cho phần thay đổi nội bộ tương ứng. Nhưng không được từ một audit “đã tiếp nhận” suy ra nhà cung cấp đã hoàn tiền.

Không đọc replica có độ trễ rồi kết luận cả nghiệp vụ và audit đều không tồn tại. Khi chưa biết kết quả, giữ operation ở quy trình xác định trạng thái; không cấp quyền thực thi mới chỉ vì log thiếu.

### 14.2. Audit sink tạm ngừng

Nếu bảng audit nội bộ đã commit cùng nghiệp vụ và outbox còn giữ sự kiện, hệ thống có thể chuyển tiếp lại khi kho tập trung phục hồi, theo giới hạn dung lượng và chính sách vận hành.

Nếu audit bắt buộc chưa ghi được ở ranh giới cần nguyên tử, hành động đó phải bị hủy hoặc trì hoãn theo chính sách. Không áp dụng một quy tắc chung “mọi lỗi log đều bỏ qua” cho bằng chứng nghiệp vụ bắt buộc.

Ngược lại, một lỗi telemetry không thiết yếu không tự động chứng minh transaction phải rollback. Cần xác định rõ dữ liệu nào là bằng chứng bắt buộc và dữ liệu nào chỉ phục vụ quan sát, tránh quyết định tùy hứng trong catch block.

### 14.3. Backup và phục hồi nhiều kho

Khôi phục database về một mốc cũ có thể làm mất audit và operation mới hơn, trong khi kho audit xuất ra ngoài hoặc nhà cung cấp vẫn còn sự kiện/kết quả sau mốc đó.

Cần đối soát theo định danh ổn định và mốc phục hồi. Không coi một event ở kho ngoài là giả chỉ vì database vừa khôi phục không còn dữ liệu tương ứng; cũng không replay mọi event ngoài thành tác dụng mới một cách mù quáng.

Quy trình phục hồi phải xác định nguồn nào đang có độ mới và thẩm quyền phù hợp cho từng loại bằng chứng. Giữ được schema, phiên bản chính sách, khóa kiểm chứng và tham chiếu cần thiết để đọc lịch sử sau khôi phục.

## 15. Bao phủ mọi đường thay đổi nghiệp vụ

Một endpoint có audit đầy đủ chưa bảo đảm toàn hệ thống có khả năng kiểm toán. Cùng dữ liệu có thể bị đổi bởi:

- API người dùng và API quản trị.
- Worker, tác vụ định kỳ và consumer thông điệp.
- Công cụ hỗ trợ khách hàng.
- Import dữ liệu và sửa dữ liệu hàng loạt.
- Script migration hoặc câu SQL vận hành.

Cần xác định đường nào được phép thay đổi đối tượng nhạy cảm và cách ghi nhận chủ thể, lý do, phiên bản cùng kết quả trên mỗi đường. Không cho chức năng hỗ trợ vượt yêu cầu phê duyệt chỉ vì nó không đi qua API công khai.

Với thay đổi hàng loạt, một sự kiện “đã sửa 10.000 bản ghi” có thể không đủ để tìm ảnh hưởng trên một đối tượng cụ thể. Có thể dùng bản ghi batch cùng danh sách hoặc sự kiện chi tiết liên kết, tùy quy mô và yêu cầu kiểm chứng.

Audit của script vận hành cần danh tính thực thi và tham chiếu thay đổi đáng tin cậy. Một `reason` tùy ý như “fix data” không đủ giải thích tại sao thao tác được phép và đã sửa điều gì.

## 16. Kiểm thử tính nguyên tử và độ trung thực

### 16.1. Kiểm thử lỗi tại ranh giới transaction

| Điểm chèn lỗi | Kết quả cần xác nhận |
|---|---|
| Sau sửa nghiệp vụ, trước insert audit | Nếu hủy transaction, không có thay đổi nghiệp vụ bền vững một phần |
| Insert audit thất bại | Hành động bắt buộc có audit không được commit thiếu bằng chứng |
| Sau insert audit, trước commit | Khi rollback, sự kiện thay đổi đã áp dụng cũng không tồn tại bền vững |
| Sau commit, trước response | Retry không tạo thêm chuyển trạng thái hoặc sự kiện nghiệp vụ giả |
| Sau commit, trước gửi outbox | Có thể chuyển tiếp lại từ outbox khi process phục hồi |
| Sau gửi event, trước đánh dấu đã gửi | Consumer xử lý được bản sao mà không nhân đôi ý nghĩa nghiệp vụ |

Đọc kết quả bằng connection hoặc ngữ cảnh độc lập sau khi transaction kết thúc. Một entity còn trong bộ nhớ không chứng minh dữ liệu đã commit hoặc rollback.

### 16.2. Kiểm thử nội dung và ngữ cảnh

Thử request thay `tenant_id`, `actor_id`, người duyệt, amount và currency trong các trường client có thể gửi. Audit phải phản ánh danh tính được xác thực, quyết định server và thay đổi thật; không chép nguyên các giá trị giả vào vị trí bằng chứng đáng tin cậy.

Thử optimistic locking thất bại, dữ liệu cache cũ và thay đổi quyền/phê duyệt đồng thời. Không được sinh audit thành công cho một chuyển trạng thái không cập nhật được dòng nào hoặc dựa trên ý định khác phiên bản đã duyệt.

### 16.3. Kiểm thử song song và retry

Gửi cùng request qua nhiều connection với một idempotency key, rồi gửi key khác cho cùng ý định nghiệp vụ. Kiểm tra số tác dụng thật, sự kiện chuyển trạng thái, các attempt và liên kết operation.

Kỳ vọng không chỉ là “không trùng event ID”. Hệ thống có thể sinh hai event ID khác nhau cho hai tác dụng không hợp lệ; kiểm thử phải phát hiện bằng bất biến nghiệp vụ.

### 16.4. Kiểm thử bảo vệ bằng chứng

Thử update/delete audit bằng tài khoản ứng dụng, đọc/export chéo tenant, nhập ghi chú chứa ký tự đặc biệt và dùng tài khoản không đủ quyền xem trường nhạy cảm.

Nếu có hash chain hoặc chữ ký, thử sửa nội dung, đổi thứ tự, xóa ở giữa và xóa phần đuôi. Kiểm tra khả năng phát hiện theo checkpoint thật sự đã triển khai, không chỉ xác nhận hàm hash tạo ra một giá trị.

Đồng thời thử retention, chuyển dữ liệu sang kho lạnh, khôi phục backup và đọc event có schema cũ. Bằng chứng cần sử dụng được trong toàn bộ vòng đời, không chỉ ngay sau lúc tạo.

## 17. Chỉ số và quy trình điều tra

Những tín hiệu có ích gồm lỗi ghi audit bắt buộc, độ trễ xuất outbox, số event trùng ở consumer, sai lệch đối soát và khoảng thời gian operation chưa xác định kết quả. Có thể theo dõi độ bao phủ audit cho các chuyển trạng thái quan trọng thay vì chỉ đếm tổng số log.

Không dùng event ID, operation ID hoặc user ID làm nhãn metric có số lượng giá trị không giới hạn. Giữ các định danh chi tiết trong kênh tìm kiếm được phân quyền phù hợp.

Khi điều tra một giao dịch:

1. Xác định tenant, ý định nghiệp vụ và operation từ nguồn đáng tin cậy.
2. Tập hợp các attempt và phân biệt thực thi mới với phát lại kết quả.
3. Tái dựng chuỗi trạng thái theo phiên bản và quan hệ nhân quả.
4. Kiểm tra chủ thể hiệu lực, ủy quyền, chính sách và phê duyệt áp dụng.
5. Đối chiếu audit với dữ liệu nghiệp vụ, outbox/inbox và kết quả phía nhận.
6. Phân loại điều đã được chứng minh, điều mâu thuẫn và điều còn chưa rõ.
7. Nếu cần điều chỉnh, ghi nhận quyết định và thực hiện nghiệp vụ sửa/bù đúng quyền.

Không kết luận “không có hành vi” chỉ từ một tìm kiếm log không thấy kết quả. Có thể log bị sampling, event đang chờ chuyển tiếp, dữ liệu đã sang kho lưu trữ hoặc truy vấn thiếu phạm vi.

## 18. Câu hỏi tự kiểm tra

1. Sự kiện nào chứng minh thay đổi đã commit, sự kiện nào chỉ ghi nhận một lần thử?
2. Audit và dữ liệu nghiệp vụ có thật sự cùng transaction hay chỉ được gọi trong cùng method?
3. Khi audit bắt buộc không ghi được, hành động nghiệp vụ có còn commit không?
4. Một operation có nhiều attempt và nhiều sự kiện được liên kết thế nào?
5. Audit có phân biệt tiếp nhận hoàn tiền với hoàn tiền đã được nhà cung cấp xác nhận không?
6. Chủ thể, phê duyệt, phiên bản và dữ liệu trước/sau đến từ nguồn nào?
7. Ai có thể đọc, sửa, xóa hoặc xuất bằng chứng, và thiết kế phát hiện được loại sửa đổi nào?
8. Sau retry, xuất sự kiện lặp, retention hoặc khôi phục backup, có còn kiểm chứng được bất biến nghiệp vụ không?

Transaction auditability cần bằng chứng đúng ý nghĩa, đúng danh tính và gắn với ranh giới commit thật. Khi audit được ghi nguyên tử, liên kết được các bước xử lý và bảo vệ trong toàn bộ vòng đời, hệ thống có thể kiểm chứng quyền, phê duyệt, trạng thái và tác dụng nghiệp vụ thay vì chỉ dựa vào những thông điệp log rời rạc.
