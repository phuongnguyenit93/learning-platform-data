# Approval decision recording — Ghi nhận quyết định phê duyệt

## 1. Ghi một quyết định khác với đặt trạng thái “đã duyệt”

**Approval decision recording** là việc lưu bền vững một quyết định nghiệp vụ của người hoặc chủ thể có thẩm quyền, gắn với đúng đối tượng, nội dung được xem xét, vòng phê duyệt và chính sách áp dụng.

Một trường `approved = true` không trả lời được những câu hỏi quan trọng: ai đã duyệt, đã duyệt phiên bản nào, người đó có quyền tại thời điểm quyết định không, cần bao nhiêu người độc lập và một request gửi lại có bị tính thêm phiếu hay không.

Trong chương **Approval Workflows** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, ghi nhận quyết định là một phần của bảo vệ quy tắc nghiệp vụ trước việc bỏ qua phê duyệt, sửa giá sau khi được duyệt, thao tác sai quyền và gửi yêu cầu trùng. Bản ghi chỉ đáng tin khi đi cùng kiểm tra quyền trên đối tượng, state machine, transaction và idempotency.

Ví dụ xuyên suốt:

- Một đề nghị mua hàng có nội dung phiên bản 14, tổng tiền do server xác định là 250.000.000 VND.
- Một vòng phê duyệt được mở cho đúng phiên bản đó, với snapshot và policy version được chốt tại server.
- Policy ví dụ chỉ định đúng hai người duyệt độc lập; cả hai phải chọn `APPROVE` thì vòng mới hoàn tất thành công.
- Người tạo đề nghị không được là người duyệt. Trong mô hình chính của bài, chưa cho phép ủy quyền quyết định.
- Một `REJECT` hợp lệ được nhận khi vòng còn `PENDING` sẽ đóng vòng thành `REJECTED`.
- Mỗi người chỉ có một quyết định trong một vòng. Retry không tạo thêm quyết định.
- Nội dung quan trọng thay đổi thì vòng cũ không còn dùng để phê duyệt nội dung mới.

Sau quyết định đầu tiên, hệ thống có thể đã lưu thành công một phiếu `APPROVE` nhưng đề nghị vẫn chưa được duyệt. Phải phân biệt **quyết định cá nhân đã được ghi nhận** với **điều kiện hoàn tất vòng đã đạt**.

## 2. Phân biệt các loại sự kiện và kết quả

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Yêu cầu quyết định | Client gửi `choice = APPROVE` | Ý định chưa được server chấp nhận |
| Quyết định được chấp nhận | Một reviewer hợp lệ chọn `REJECT` | Một sự thật nghiệp vụ cần được lưu |
| Request bị từ chối | Người ngoài nhóm duyệt gọi API | Không phải một phiếu `REJECT` của vòng |
| Kết quả vòng phê duyệt | Hai reviewer đã `APPROVE` | Policy tổng hợp quyết định thành `APPROVED` |
| Cho phép thực thi bước tiếp theo | Đề nghị đủ điều kiện chuyển sang đặt hàng | Còn phải gắn với đúng dữ liệu và kiểm tra ở đường thực thi |
| Audit/technical log | API bị gọi sai quyền, lỗi database | Dấu vết hỗ trợ; không thay thế dữ liệu quyết định chuẩn |

Một lỗi thiết kế nguy hiểm là đưa cả request không có quyền vào bảng quyết định dưới dạng `REJECT`. Kẻ không được phép phê duyệt khi đó có thể làm vòng bị từ chối bằng cách gọi API.

Ngược lại, reviewer hợp lệ chọn `REJECT` là một quyết định nghiệp vụ đã được ghi thành công. Nó không phải lỗi xác thực hoặc lỗi hệ thống chỉ vì kết quả của đề nghị không như người tạo mong muốn.

Ví dụ chuỗi diễn biến đúng:

```mermaid
sequenceDiagram
    participant A as Reviewer A
    participant S as Approval service
    participant D as Database
    participant B as Reviewer B
    A->>S: APPROVE snapshot v14, key K1
    S->>D: Lưu quyết định D1, vòng vẫn PENDING
    S-->>A: D1 đã được ghi, vòng chưa hoàn tất
    B->>S: APPROVE cùng snapshot, key K2
    S->>D: Lưu D2, đủ điều kiện, vòng APPROVED
    S-->>B: D2 đã được ghi, vòng đã hoàn tất
    A->>S: Retry K1
    S-->>A: Trả receipt D1; không tạo quyết định D3
```

Receipt của D1 có thể mô tả trạng thái vòng **ngay sau D1** là `PENDING`, dù hiện tại vòng đã `APPROVED`. Đặt tên trường rõ như `round_state_after_decision`, không gọi đó là trạng thái hiện tại. Muốn biết trạng thái mới nhất, truy vấn tài nguyên vòng theo quyền truy cập hiện tại.

## 3. Quyết định phải gắn với đúng nội dung được duyệt

### 3.1. Chỉ có document ID là chưa đủ

Nếu chỉ lưu `document_id`, một người có thể duyệt tổng tiền 250 triệu, sau đó giá hoặc người nhận được sửa trước lúc thực thi. Hệ thống vẫn thấy “đơn đã duyệt” nhưng nội dung thực thi không còn là nội dung đã được xem xét.

Mỗi vòng cần chốt các liên kết:

```text
tenant + document_id + document_content_version
    + snapshot_id/hash + policy_version + round_id
```

- `tenant` xác định phạm vi tổ chức sở hữu dữ liệu.
- `document_content_version` thay đổi khi nội dung có ý nghĩa phê duyệt thay đổi.
- Snapshot lưu những dữ kiện cần để hiểu quyết định trong tương lai.
- `policy_version` xác định quy tắc đã dùng để mở và xử lý vòng.
- `round_id` phân biệt các lần gửi duyệt của cùng tài liệu.

Các giá trị này đến từ server. Client có thể gửi version/hash mà giao diện đã hiển thị để server phát hiện bản xem đã cũ; client không có quyền tự định nghĩa nội dung hoặc chính sách có thẩm quyền.

### 3.2. Snapshot cần đủ nội dung và có định dạng xác định

Với đề nghị mua hàng, snapshot có thể gồm danh sách mặt hàng, số lượng, đơn giá, thuế/phí, tiền tệ, tổng tiền, nhà cung cấp và các điều kiện quan trọng khác. Chọn trường theo invariant của nghiệp vụ, không chỉ theo những trường đang hiện trên một màn hình.

Nếu dùng hash, server cần quy định rõ byte dữ liệu được băm:

1. Có version của schema snapshot.
2. Quy định tên trường, thứ tự hoặc phương thức serialize chuẩn.
3. Thống nhất biểu diễn tiền, số thập phân, timestamp và giá trị rỗng.
4. Lưu snapshot thực tế hoặc tham chiếu bất biến có thể truy xuất; chỉ giữ hash sẽ không giúp đọc lại nội dung khi bản gốc đã mất.
5. Băm dữ liệu do server tạo, không lưu hash do client gửi như bằng chứng duy nhất.

Hash hỗ trợ kiểm tra tính khớp của nội dung. Nó không tự chứng minh người dùng đã đọc mọi dòng, cũng không thay thế phân quyền hoặc kiểm soát chống sửa dữ liệu tại nơi lưu.

### 3.3. Tách version nội dung và version kỹ thuật khi cần

Ví dụ sử dụng hai ý nghĩa riêng:

- `content_version` của tài liệu tăng khi giá hoặc dữ liệu ảnh hưởng quyết định thay đổi.
- `version` của vòng tăng khi vòng nhận quyết định hoặc đổi trạng thái.

Một phiếu mới làm version vòng tăng nhưng không biến nội dung v14 thành v15. Việc cập nhật trạng thái kỹ thuật của tài liệu cũng có thể có `row_version` riêng. Phải định nghĩa rõ để không vô tình làm mọi quyết định vừa lưu trở thành lỗi thời vì chính thao tác ghi trạng thái phê duyệt.

Nếu tài liệu bị sửa nội dung trong lúc đang duyệt, đường chỉnh sửa phải khóa/kiểm tra dữ liệu liên quan và đánh dấu vòng cũ `SUPERSEDED` hoặc vô hiệu hóa nó theo policy. Không đổi snapshot của vòng đang tồn tại rồi giữ nguyên các phiếu cũ.

Nguyên tắc gắn ủy quyền với dữ liệu và kiểm tra tại bước thực thi giúp chống tình huống dữ liệu bị thay giữa lúc xem xét và sử dụng. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

## 4. Danh tính và quy tắc tính phiếu

### 4.1. Ai thực hiện và ai được tính là reviewer?

Ít nhất cần phân biệt:

| Thông tin | Nguồn có thẩm quyền |
| --- | --- |
| Tài khoản đang thực hiện | Ngữ cảnh xác thực đã kiểm chứng |
| Danh tính reviewer chuẩn hóa | Directory hoặc cơ chế ánh xạ danh tính do hệ thống kiểm soát |
| Phân công trong vòng | Assignment do server tạo theo policy |
| Quyền hiện tại trên đối tượng | Kiểm tra tenant, vai trò, quan hệ đối tượng và điều kiện liên quan |
| Dữ liệu đã được xem xét | Snapshot/version đã chốt tại server |

`actor_account_id` và `reviewer_principal_id` không nhất thiết giống nhau. Một người có thể có nhiều tài khoản; dùng số tài khoản khác nhau làm số người độc lập có thể phá quy tắc hai người duyệt.

Trong mô hình ví dụ, hệ thống có cơ chế nhận diện reviewer chuẩn hóa đáng tin cậy. Nếu không có cơ chế đó, unique constraint theo một UUID tài khoản chỉ chứng minh tài khoản khác nhau, không chứng minh hai con người độc lập.

### 4.2. Các invariant cần thực thi

```text
Một quyết định được commit
    => vòng đang nhận quyết định
    AND reviewer được phân công và còn đủ quyền
    AND reviewer không phải người tạo
    AND nội dung/version khớp vòng
    AND thời điểm quyết định còn hợp lệ theo policy.

Trong một vòng của mô hình này:
    mỗi reviewer chuẩn hóa có tối đa một quyết định.

Vòng APPROVED
    => cả hai reviewer đã có APPROVE hợp lệ
    AND không có REJECT đã được chấp nhận.
```

Hai vai trò trên cùng một người không tạo thành hai phiếu. `COUNT(*)` chỉ có ý nghĩa sau khi dữ liệu đầu vào đã được bảo vệ bằng assignment, uniqueness và kiểm tra điều kiện.

Trong policy ví dụ có đúng hai reviewer được chỉ định. Vòng đóng ngay khi đủ cả hai phiếu thuận hoặc có một phiếu từ chối. Quyết định gửi tới sau khi vòng đã đóng không được thêm vào vòng như một phiếu mới.

### 4.3. Nếu mở rộng sang ủy quyền

Mô hình chính chưa cho phép delegate. Khi bổ sung, không chỉ thay actor hiển thị bằng tên người được đại diện. Cần lưu người thực hiện thật, người/chỗ phê duyệt được đại diện, grant ủy quyền, phạm vi, thời hạn và căn cứ kiểm tra.

Thường phải bảo vệ cả hai điều kiện khác nhau:

- Một vị trí phê duyệt không được người gốc và delegate cùng sử dụng thành hai phiếu.
- Một người thực hiện thật không được chiếm nhiều vị trí rồi tự tạo đủ số người độc lập.

Có thể cần uniqueness theo cả `approval_slot_id` và reviewer thực hiện chuẩn hóa, kèm policy xử lý đại diện. Schema đơn giản ở phần sau không tự đáp ứng toàn bộ bài toán ủy quyền này.

## 5. Hợp đồng API và bản ghi quyết định

### 5.1. Request chỉ thể hiện ý định

Ví dụ API:

```http
POST /purchase-requests/{documentId}/approval-rounds/{roundId}/decisions
Idempotency-Key: review-a-20261122-01
Content-Type: application/json

{
  "choice": "APPROVE",
  "expected_content_version": 14,
  "reviewed_snapshot_hash": "6f8c4d2a9b0e7315c6d4a8205f7b91e3a2c8d6407e1f5b93c0a6d28419e7f035",
  "reason_code": "REQUIREMENTS_SATISFIED",
  "comment": "Đã đối chiếu nội dung đề nghị."
}
```

Hash trên là giá trị minh họa. Server phải tính và đối chiếu với snapshot đã lưu của đúng vòng.

Request không được cấp quyền bằng những trường như `actor_id`, `is_admin`, `required_approvals`, `approved_count`, `round_state` hoặc `policy_version` do client tự gửi. Dùng DTO với tập trường cho phép; không bind trực tiếp request vào entity quyết định/vòng.

`reason_code` là mã nghiệp vụ có kiểm tra. Với `REJECT`, policy có thể bắt buộc lý do phù hợp. Comment tự do là dữ liệu bổ sung được giới hạn độ dài, không thay thế mã quyết định hoặc kết quả kiểm tra quyền.

### 5.2. Nội dung một receipt có cấu trúc

```json
{
  "decision_id": "b2bdfcd0-d855-4bd7-90c6-7914ff63d8a7",
  "round_id": "256b8cee-1445-436a-b404-0fbebd9028e5",
  "document_id": "ff9e22f7-6a4d-4bc8-b8d0-5bb1250860a9",
  "document_content_version": 14,
  "snapshot_hash": "6f8c4d2a9b0e7315c6d4a8205f7b91e3a2c8d6407e1f5b93c0a6d28419e7f035",
  "reviewer_principal_id": "dc2c825b-405e-4dc9-b10d-611ca3baedfe",
  "choice": "APPROVE",
  "reason_code": "REQUIREMENTS_SATISFIED",
  "policy_version": "purchase-approval-v4",
  "decision_at": "2026-11-22T04:12:05.250Z",
  "round_state_after_decision": "PENDING",
  "round_version_after_decision": 1
}
```

Đây là receipt của quyết định đầu tiên, không phải thông báo toàn bộ đề nghị đã được duyệt. Payload trả ra ngoài có thể giảm các trường danh tính tùy quyền đọc; bản ghi chuẩn phía server vẫn cần đủ liên kết để điều tra.

Thông tin xác thực bổ sung, nếu policy yêu cầu, nên được lưu dưới dạng tham chiếu bằng chứng và metadata đã xác minh, ví dụ phương thức xác nhận, thời điểm và challenge ID nội bộ. Không lưu OTP, mật khẩu, bearer token hoặc toàn bộ header xác thực.

## 6. Schema quan hệ minh họa

Schema PostgreSQL dưới đây tập trung vào vòng, phân công và quyết định. Bảng tài liệu và kho snapshot là thành phần nghiệp vụ riêng; backend phải kiểm tra liên kết và version với các thành phần đó khi mở vòng, ghi quyết định và thực thi.

```sql
CREATE TABLE approval_round (
    tenant_id                 uuid NOT NULL,
    id                        uuid NOT NULL,
    document_id               uuid NOT NULL,
    document_content_version  bigint NOT NULL,
    snapshot_hash             varchar(64) NOT NULL,
    policy_version            varchar(128) NOT NULL,
    required_approvals        integer NOT NULL,
    state                     varchar(32) NOT NULL,
    version                   bigint NOT NULL DEFAULT 0,
    opened_at                 timestamptz NOT NULL,
    expires_at                timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, id),
    CHECK (document_content_version >= 0 AND version >= 0),
    CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    CHECK (required_approvals > 0),
    CHECK (expires_at > opened_at),
    CHECK (state IN (
        'PENDING', 'APPROVED', 'REJECTED',
        'SUPERSEDED', 'EXPIRED', 'CANCELLED'
    ))
);

CREATE TABLE approval_assignment (
    tenant_id              uuid NOT NULL,
    round_id               uuid NOT NULL,
    reviewer_principal_id  uuid NOT NULL,
    PRIMARY KEY (tenant_id, round_id, reviewer_principal_id),
    FOREIGN KEY (tenant_id, round_id)
        REFERENCES approval_round (tenant_id, id)
);

CREATE TABLE approval_decision (
    tenant_id              uuid NOT NULL,
    id                     uuid NOT NULL,
    round_id               uuid NOT NULL,
    reviewer_principal_id  uuid NOT NULL,
    actor_account_id       uuid NOT NULL,
    choice                 varchar(16) NOT NULL,
    reason_code            varchar(64) NOT NULL,
    comment                text,
    decision_at            timestamptz NOT NULL,
    command_id             uuid NOT NULL,
    authorization_context  jsonb NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, round_id, reviewer_principal_id),
    UNIQUE (tenant_id, command_id),
    CHECK (choice IN ('APPROVE', 'REJECT')),
    CHECK (comment IS NULL OR char_length(comment) <= 2000),
    FOREIGN KEY (tenant_id, round_id, reviewer_principal_id)
        REFERENCES approval_assignment (
            tenant_id, round_id, reviewer_principal_id
        )
);
```

Các ràng buộc phục vụ những việc khác nhau:

- Composite foreign key có tenant ngăn decision tham chiếu assignment thuộc tenant khác qua một ID rời rạc.
- Unique theo vòng và reviewer chặn tính hai phiếu cho cùng danh tính chuẩn hóa, kể cả client đổi idempotency key.
- Unique theo command ID hỗ trợ nhận diện một thao tác logic, nhưng không thay thế kho idempotency chứa fingerprint và kết quả.
- `CHECK` giới hạn tập lựa chọn và hình dạng dữ liệu; nó không kiểm tra đủ tất cả quy tắc liên hàng như số reviewer phù hợp hoặc người tạo không nằm trong danh sách.

PostgreSQL hỗ trợ unique constraint trên nhiều cột và foreign key tham chiếu nhóm cột có ràng buộc khóa phù hợp. Dùng các constraint này để cơ sở dữ liệu cùng bảo vệ invariant thay vì chỉ dựa vào kiểm tra trước khi insert. [Tài liệu PostgreSQL về constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).

Đường mở vòng trong ví dụ phải tạo đúng hai assignment khác người tạo, đặt `required_approvals = 2` và bảo vệ các binding nội dung/policy khỏi sửa tùy ý. Assignment của vòng đã mở không được âm thầm thay đổi; nếu cần phân công lại, phải có policy và dấu vết riêng hoặc tạo vòng mới.

Snapshot, version nội dung và policy nằm ở vòng nên decision không cần sao chép chúng vào nhiều cột có thể lệch nhau. Điều này chỉ an toàn khi các binding đó bất biến sau khi mở vòng. Khi phát hành receipt hoặc event, lấy thông tin từ decision và đúng vòng gắn với nó.

## 7. Ghi quyết định và tổng hợp kết quả trong transaction

### 7.1. Vì sao không chỉ insert rồi tăng counter?

Đoạn logic sau thiếu nhiều điều kiện:

```java
decisionRepository.insert(request);
roundRepository.incrementApprovedCount(request.roundId());
```

Client có thể giả reviewer, request bị retry có thể tăng thêm phiếu, hai transaction có thể tổng hợp trên dữ liệu khác nhau, hoặc quyết định đã lưu nhưng cập nhật vòng thất bại. Nếu counter tách rời dữ liệu quyết định, việc đối soát cũng khó xác định nguồn nào đúng.

Với vòng nhỏ gồm hai reviewer, có thể dùng quyết định chuẩn làm nguồn sự thật và tổng hợp lại trong transaction giữ khóa vòng. Nếu cần counter để tối ưu, vẫn phải cập nhật nó nguyên tử, chỉ tăng cho insert mới hợp lệ và có cơ chế đối soát với nguồn chuẩn.

### 7.2. Một thứ tự xử lý dễ kiểm chứng

1. Khóa tài liệu theo tenant và ID, sau đó khóa đúng vòng thuộc tài liệu đó.
2. Kiểm tra quyền hiện tại trên đối tượng trước khi trả kết quả nhạy cảm.
3. Nhận/tra claim idempotency và xác minh fingerprint.
4. Nếu thao tác đã hoàn tất, trả receipt đã lưu; không insert hay tổng hợp lại.
5. Với thao tác mới, kiểm tra vòng còn `PENDING`, nội dung/hash khớp, reviewer được phân công, đủ quyền và không tự duyệt.
6. Kiểm tra điều kiện thời gian và bằng chứng xác nhận mà policy yêu cầu.
7. Insert decision bất biến, rồi tổng hợp các decision đã được chấp nhận của vòng.
8. Cập nhật version/trạng thái vòng, trạng thái phê duyệt của tài liệu nếu vòng kết thúc, audit/outbox và kết quả idempotency.
9. Commit rồi mới trả thông báo ghi nhận thành công.

Đường chỉnh sửa tài liệu, hủy vòng và ghi quyết định phải dùng giao thức khóa tương thích. Trong ví dụ, cùng tuân thứ tự **tài liệu → vòng** để tránh một bên khóa vòng rồi chờ tài liệu trong khi bên kia giữ tài liệu và chờ vòng.

`SELECT ... FOR UPDATE` ngăn transaction khác sửa hoặc lấy khóa xung đột trên cùng hàng cho đến khi transaction kết thúc. Nó không tự khóa mọi bảng dữ liệu quyền hoặc danh tính liên quan. [Tài liệu PostgreSQL về row-level locking](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

### 7.3. Khung application service Java

Đoạn sau dùng `TransactionTemplate` của Spring. Các repository và policy là hợp đồng minh họa, không phải chương trình hoàn chỉnh có thể chép chạy ngay.

```java
public DecisionReceipt recordDecision(
        RecordDecisionCommand cmd, TrustedActor actor) {

    return transactions.execute(tx -> {
        PurchaseRequest document = documents.lockByTenant(
            actor.tenantId(), cmd.documentId());

        ApprovalRound round = rounds.lockByTenantAndDocument(
            actor.tenantId(), cmd.roundId(), document.id());

        // Quyền đọc/thao tác trên đối tượng, chưa yêu cầu state PENDING.
        access.requireDecisionScope(actor, document, round);

        IdempotencyClaim claim = idempotency.claim(
            actor.tenantId(), actor.accountId(), "RECORD_APPROVAL_DECISION",
            cmd.idempotencyKey(), fingerprints.decision(cmd));

        if (claim.isCompleted()) {
            return claim.originalReceipt();
        }

        round.requirePending();
        round.requireReviewedContent(
            cmd.expectedContentVersion(), cmd.reviewedSnapshotHash());
        round.requireMatchesCurrentContent(document);

        // Xác minh principal từ nguồn tin cậy, assignment, quyền và maker-checker.
        ReviewerAuthorization grant = reviewerPolicy.requireAllowed(
            actor, document, round, cmd.choice(), cmd.reasonCode());

        // Lấy sau các bước có thể chờ khóa theo giao thức đã chọn.
        Instant decisionAt = databaseClock.currentInstant();
        round.requireBeforeDeadline(decisionAt);

        ApprovalDecision decision = ApprovalDecision.accepted(
            UUID.randomUUID(), actor.tenantId(), round.id(),
            grant.reviewerPrincipalId(), actor.accountId(),
            cmd.choice(), cmd.reasonCode(), cmd.comment(),
            decisionAt, claim.commandId(), grant.safeEvidence());

        decisions.insert(decision);

        DecisionTally tally = decisions.tally(
            actor.tenantId(), round.id());

        RoundState nextState;
        if (tally.rejects() > 0) {
            nextState = RoundState.REJECTED;
        } else if (tally.approvals() >= round.requiredApprovals()) {
            nextState = RoundState.APPROVED;
        } else {
            nextState = RoundState.PENDING;
        }

        long nextVersion = Math.addExact(round.version(), 1);
        rounds.applyOutcomeOrThrow(round, nextState, nextVersion);

        if (nextState != RoundState.PENDING) {
            documents.recordApprovalOutcomeOrThrow(
                document, round, nextState);
        }

        outbox.appendDecisionRecorded(decision, round, nextState, nextVersion);
        if (nextState != RoundState.PENDING) {
            outbox.appendRoundCompleted(round, nextState, nextVersion);
        }

        DecisionReceipt receipt = DecisionReceipt.from(
            decision, round, nextState, nextVersion);
        idempotency.complete(claim, receipt);
        return receipt;
    });
}
```

Những giả định bắt buộc của khung trên:

- Tất cả thao tác lưu nằm trong cùng database và transaction manager; lỗi ghi decision, vòng, tài liệu, outbox hoặc idempotency phải rollback toàn bộ.
- `fingerprints.decision` bao gồm document/round ID, lựa chọn, version/hash đã xem và các trường lý do/comment được coi là nội dung của thao tác. Nó không đưa request ID thay đổi theo mỗi retry vào fingerprint.
- `reviewerPolicy` không nhận reviewer ID tự khai làm nguồn sự thật. Nó xác minh reviewer chuẩn hóa, assignment, người tạo, policy áp dụng và bằng chứng xác nhận cần thiết.
- `applyOutcomeOrThrow` kiểm tra tenant, ID, state và version hiện tại khi cập nhật, đồng thời yêu cầu số hàng bị cập nhật bằng một. `recordApprovalOutcomeOrThrow` gắn kết quả với đúng vòng và content version đang khóa.
- Ghi kết quả phê duyệt vào tài liệu chỉ thay đổi trạng thái/row version phù hợp; không âm thầm sửa nội dung hoặc tăng content version như thể giá đã thay đổi.
- `safeEvidence` chỉ chứa metadata được phép lưu, không có bí mật xác thực. Outbox có event ID ổn định cho mỗi event đã lưu để relay retry không tạo danh tính sự kiện mới.
- Exception làm transaction thất bại không bị nuốt. Chỉ trả receipt ra ngoài sau khi `execute` hoàn tất transaction thành công.

Nếu nguồn quyền nằm ở dịch vụ khác, cần xác định rõ policy về độ mới của bằng chứng quyền và việc thu hồi quyền. Khóa vòng không tự biến lời gọi phân quyền từ xa thành một phần nguyên tử của database transaction.

### 7.4. Tổng hợp chỉ trên nguồn đã được bảo vệ

Truy vấn tally đơn giản cho policy ví dụ:

```sql
SELECT
    count(*) FILTER (WHERE choice = 'APPROVE') AS approvals,
    count(*) FILTER (WHERE choice = 'REJECT') AS rejects
FROM approval_decision
WHERE tenant_id = :tenant_id
  AND round_id = :round_id;
```

Nó đúng trong phạm vi mô hình đã chọn vì assignment và uniqueness ngăn phiếu ngoài danh sách hoặc phiếu lặp, binding vòng không đổi, và mọi writer tuân thủ giao thức khóa vòng.

Nếu policy yêu cầu một phiếu tài chính và một phiếu nghiệp vụ, phiếu có trọng số, quyết định bị rút hoặc quyền cũ bị vô hiệu, không được giữ nguyên phép đếm này rồi chỉ thay ngưỡng. Khi đó phải mô hình hóa điều kiện tính phiếu và tổng hợp theo policy tương ứng.

## 8. Retry và xử lý đồng thời

### 8.1. Cùng key, cùng nội dung

Reviewer A gửi `APPROVE`, server commit D1 nhưng response bị mất. Retry cùng key và cùng nội dung phải trả receipt D1. Không insert D2, không tăng version vòng và không phát thêm sự kiện hoàn tất.

Quyền truy cập hiện tại vẫn cần được kiểm tra trước khi trả receipt. Nhánh replay không được yêu cầu vòng còn `PENDING`, vì vòng có thể đã hoàn tất hợp lệ sau quyết định cũ.

### 8.2. Cùng key, đổi nội dung

Nếu cùng key được gửi lại với `REJECT` hoặc round/hash khác, server từ chối xung đột. Không được dùng `ON CONFLICT DO UPDATE` để đổi phiếu cũ thành phiếu mới rồi coi là retry.

### 8.3. Đổi key để bỏ qua idempotency

Reviewer gửi cùng quyết định bằng key khác vẫn không có quyền tạo phiếu thứ hai. Unique theo `(tenant, round, reviewer_principal)` là lớp bảo vệ độc lập với idempotency key.

Policy API có thể trả thông tin rằng reviewer đã có quyết định hoặc lỗi xung đột phù hợp. Nó không được âm thầm ghi đè quyết định trước đó.

### 8.4. Hai reviewer quyết định đồng thời

A và B cùng xem snapshot v14 rồi gửi quyết định. Khóa vòng tuần tự hóa việc insert và tổng hợp:

1. A ghi D1, tally có một phiếu thuận, vòng vẫn `PENDING`, version vòng thành 1.
2. B lấy khóa sau đó, vẫn thấy cùng content version/hash và vòng còn mở.
3. B ghi D2, tally có hai phiếu thuận, vòng chuyển `APPROVED`, version thành 2.

Không nhất thiết bắt B gửi lại chỉ vì version kỹ thuật của vòng đã tăng sau phiếu A. Điều phải khớp để thể hiện nội dung được xem xét là binding nội dung và vòng. Code dùng version vòng đang khóa cho cập nhật có điều kiện, không lấy số đếm do client cung cấp.

Nếu B chọn `REJECT`, vòng kết thúc `REJECTED`. Nếu vòng đã kết thúc do quyết định hợp lệ khác, request mới phải bị từ chối; muốn khiếu nại hoặc xem xét lại cần workflow riêng theo policy.

### 8.5. Quyết định cuối cùng và chỉnh sửa nội dung

Đường sửa giá và đường ghi quyết định cùng tranh chấp khóa tài liệu rồi vòng:

- Nếu sửa nội dung được chấp nhận trước, content version đổi và vòng cũ bị vô hiệu; quyết định trên snapshot cũ không được nhận.
- Nếu phê duyệt hoàn tất trước, đường sửa phải tuân policy sau phê duyệt, chẳng hạn tạo bản sửa cần duyệt lại. Không giữ trạng thái được duyệt cho nội dung mới.

Đây là điều kiện chống sửa giá sau duyệt. Việc lưu thêm một hash trong log nhưng không kiểm tra nó ở đường ghi/thực thi không bảo vệ được invariant này.

## 9. Sửa sai, rút quyết định và thay đổi quyền

### 9.1. Không âm thầm sửa lịch sử

Quyết định đã được chấp nhận là bản ghi bất biến trong mô hình này. Một endpoint cập nhật comment/lựa chọn trực tiếp có thể làm mất bằng chứng về điều từng được dùng để hoàn tất vòng.

Nếu cần sửa thông tin hoặc rút quyết định, định nghĩa action mới có quyền riêng, lý do và liên kết với decision cũ. Phải chỉ rõ:

- Có được rút khi vòng còn mở không?
- Rút có làm vòng mất điều kiện hoàn tất hay phải tạo vòng mới?
- Sau khi tác dụng tiếp theo đã xảy ra thì cần bù trừ hoặc xử lý ngoại lệ nào?
- Quyết định nào còn hiệu lực để tính kết quả tại từng thời điểm?

Schema và phép đếm ở ví dụ không hỗ trợ retraction. Không thêm một bảng “rút phiếu” rồi vẫn dùng `COUNT(*)` trên toàn bộ quyết định như trước. Có thể giữ lịch sử append-only và xây projection quyết định hiệu lực theo quy tắc mới.

### 9.2. Vai trò bị thu hồi sau khi quyết định

Cần chọn rõ policy: đánh giá quyền tại thời điểm ghi quyết định, hay còn yêu cầu kiểm tra lại tại lúc hoàn tất/thực thi. Quyết định từng hợp lệ không được tự động viết lại thành “chưa từng xảy ra” chỉ vì reviewer chuyển vị trí công việc.

Nếu chính sách yêu cầu vô hiệu các phê duyệt đang chờ khi một quyền bị thu hồi, ghi nhận việc vô hiệu và tính lại kết quả theo quy trình được kiểm soát. Không dùng role hiện tại để diễn giải lại lịch sử mà không có dấu vết thay đổi.

### 9.3. Policy thay đổi giữa vòng

Lưu policy version cùng vòng và xác định rõ có tiếp tục policy đã chốt hay chuyển vòng sang trạng thái cần xét lại. Không áp dụng ngầm threshold mới lên một số phiếu cũ rồi giữ cách giải thích policy cũ trong receipt.

Với thay đổi chính sách khẩn cấp, có thể dừng hoặc thay thế các vòng chưa thực thi. Cần lưu lý do, phạm vi và liên kết vòng mới để giải thích vì sao những phiếu đã ghi không còn đủ điều kiện sử dụng.

## 10. Độ bền, sự kiện và bước thực thi tiếp theo

### 10.1. Nguồn sự thật phải nằm bền vững

Bản ghi quyết định, kết quả vòng, trạng thái phê duyệt tài liệu và kết quả idempotency phải nhất quán. Không báo “đã ghi nhận” chỉ vì message vừa được đưa vào một hàng đợi trong bộ nhớ hoặc một logger đã được gọi.

Nếu cần gửi email, cập nhật search hoặc thông báo cho service khác, lưu ý định gửi trong outbox cùng transaction. Relay gửi sau commit và có thể giao lại. Consumer phải khử trùng theo event ID; request idempotency và message deduplication giải quyết hai lớp khác nhau.

Các sự kiện cũng cần phân biệt:

- `ApprovalDecisionRecorded`: có một quyết định mới hợp lệ.
- `ApprovalRoundCompleted`: vòng vừa kết thúc với kết quả cụ thể.
- Sự kiện thực thi nghiệp vụ tiếp theo: chỉ phát khi hành động đó thực sự được chấp nhận/hoàn tất theo mô hình của nó.

Không coi một event về phiếu đầu tiên là lệnh được phép thực thi cả đề nghị.

### 10.2. Kiểm tra ở đường sử dụng kết quả

Service đặt hàng hoặc tạo tác dụng tiếp theo không được chỉ kiểm tra “có ít nhất một decision APPROVE”. Nó phải xác minh vòng kết thúc hợp lệ, đúng tenant/tài liệu, đúng content version/hash và chưa bị vô hiệu theo policy thực thi.

Với bước thực thi trong cùng database, dùng transaction và điều kiện cập nhật để gắn việc sử dụng phê duyệt với đúng nội dung. Với nhiều service, cần hợp đồng sự kiện/bằng chứng ủy quyền rõ ràng, kiểm tra tính toàn vẹn và cơ chế xử lý thay đổi/vô hiệu phù hợp; transaction cục bộ không tự bao trùm mọi dịch vụ.

Nếu một kết quả phê duyệt chỉ được dùng một lần cho một action, chính việc “tiêu thụ” kết quả đó cũng cần idempotency và trạng thái có điều kiện. Giữ decision ID làm tham chiếu không tự ngăn được gọi lặp API thực thi.

### 10.3. Mất kết nối ở thời điểm commit

Nếu ứng dụng không biết transaction đã commit hay chưa, không tạo quyết định mới với key mới để thử lại. Tra hoặc retry cùng key để nhận kết quả đã lưu. Một HTTP timeout không chứng minh database đã rollback.

## 11. Bảo vệ bằng chứng và truy vấn lịch sử

Tài khoản chạy nghiệp vụ không nên có quyền tùy ý sửa/xóa quyết định đã ghi. Binding snapshot/policy và assignment cũng cần được bảo vệ theo tính bất biến đã định nghĩa. Tài khoản quản trị, tác vụ migration và đường sửa dữ liệu vận hành không được trở thành lối tắt không có dấu vết.

Append-only đối với tài khoản ứng dụng không đồng nghĩa chống được mọi người có đặc quyền database. Nếu mô hình đe dọa yêu cầu bằng chứng độc lập, cần bản sao hoặc cơ chế kiểm chứng nằm ngoài cùng miền quản trị. Hash/chữ ký hỗ trợ kiểm tra theo mô hình khóa và nơi lưu, không tự chứng minh rằng không có quyết định nào bị bỏ sót từ đầu.

Comment có thể chứa dữ liệu nhạy cảm, ký tự xuống dòng hoặc markup. Dùng giới hạn kích thước, serialization/encoding đúng định dạng và kiểm soát quyền khi hiển thị/xuất dữ liệu. Không nối comment thành chuỗi SQL hoặc HTML thực thi.

Truy vấn lịch sử của một vòng có thể lấy decision cùng binding bất biến:

```sql
SELECT d.id AS decision_id,
       d.reviewer_principal_id,
       d.actor_account_id,
       d.choice, d.reason_code, d.decision_at,
       r.document_id, r.document_content_version,
       r.snapshot_hash, r.policy_version
FROM approval_decision d
JOIN approval_round r
  ON r.tenant_id = d.tenant_id
 AND r.id = d.round_id
WHERE d.tenant_id = :tenant_id
  AND d.round_id = :round_id
ORDER BY d.decision_at, d.id;
```

API gọi truy vấn vẫn phải kiểm tra quyền đọc đúng đối tượng. Có cột tenant không tự tạo cách ly dữ liệu nếu truy vấn hoặc endpoint bỏ qua nó.

Thứ tự timestamp hỗ trợ trình bày, không mặc nhiên là bằng chứng thứ tự toàn cục hoặc thời điểm commit. Nếu cần thứ tự quyết định chính xác trong vòng, lưu thêm sequence/version sau quyết định được cấp dưới khóa vòng. Không suy ra số phiếu hoặc hiệu lực chỉ từ dòng log xuất hiện trước trên dashboard.

Đối soát định kỳ nên tìm vòng `APPROVED` thiếu tập quyết định cần thiết, quyết định không khớp phân công, tài liệu đổi nội dung mà vẫn giữ kết quả cũ và outbox chưa giao. Dùng snapshot đọc nhất quán hoặc checkpoint để tránh báo sai vì đọc các bảng ở những thời điểm khác nhau.

## 12. Những tình huống kiểm thử quan trọng

Kiểm thử phải quan sát dữ liệu đã commit và điều kiện nghiệp vụ, không chỉ xác nhận hàm ghi log được gọi.

| Tình huống | Kết quả cần bảo đảm |
| --- | --- |
| Reviewer đầu tiên chọn `APPROVE` hợp lệ | Có một decision; vòng vẫn `PENDING` |
| Reviewer thứ hai độc lập chọn `APPROVE` | Có hai decision; vòng và tài liệu cập nhật kết quả nguyên tử |
| Reviewer hợp lệ chọn `REJECT` khi vòng mở | Lưu quyết định từ chối; vòng `REJECTED` |
| Người không được phân công gửi `REJECT` | Không có decision hợp lệ làm ảnh hưởng vòng |
| Người tạo tự duyệt | Bị từ chối dù có role chung hoặc gọi endpoint trực tiếp |
| Giả reviewer ID hoặc policy trong request | Server không dùng dữ liệu tự khai làm căn cứ quyền |
| Dùng document/round ID thuộc tenant khác | Không ghi quyết định hoặc làm lộ receipt/snapshot |
| Sửa giá sau khi mở vòng rồi duyệt snapshot cũ | Không chấp nhận quyết định cho nội dung mới bằng vòng cũ |
| Cùng key và nội dung sau khi mất response | Trả cùng decision ID, không tăng số phiếu |
| Cùng key nhưng đổi lựa chọn hoặc snapshot | Từ chối xung đột; không ghi đè decision |
| Cùng reviewer dùng key mới | Không có phiếu thứ hai trong cùng vòng |
| Một người dùng hai tài khoản được ánh xạ cùng principal | Không được tính thành hai người duyệt độc lập |
| Hai reviewer quyết định đồng thời | Không mất phiếu, tính sai ngưỡng hoặc hoàn tất nhiều lần |
| Decision cuối cùng tranh chấp với sửa tài liệu | Chỉ kết quả hợp lệ với binding được commit |
| Hủy/hết hạn tranh chấp với quyết định mới | Không nhận quyết định mới sau khi vòng đã đóng theo policy |
| Lỗi ghi vòng, tài liệu, outbox hoặc idempotency | Decision và các thay đổi liên quan rollback cùng nhau |
| Event được giao lại | Consumer không tạo thêm tác dụng hoặc thông báo nghiệp vụ trùng ngoài policy |
| Thu hồi quyền trước retry receipt | Áp dụng quyền đọc hiện tại mà không tạo lại quyết định |
| Thử sửa/xóa decision bằng tài khoản ứng dụng | Bị cơ chế quyền/bất biến ngăn chặn |
| Comment có markup, xuống dòng hoặc dữ liệu quá lớn | Không phá log, truy vấn hoặc giao diện xem lịch sử |

Với concurrency, dùng hai kết nối/transaction thật có cùng điểm tranh chấp. Với atomicity, chèn lỗi sau insert decision và trước các lần cập nhật tiếp theo, rồi đọc bằng kết nối khác để xác nhận không có trạng thái commit dở dang.

Nếu triển khai delegation, retraction hoặc policy nhiều nhóm, bổ sung kiểm thử cho các invariant mới. Bộ constraint và phép tally đơn giản của bài không phải lời khẳng định rằng các biến thể đó đã được hỗ trợ.

Khung mã và các tình huống trong bài mang tính thiết kế; chúng chưa được chạy như một ứng dụng hoàn chỉnh.

## 13. Bài tập áp dụng

Mở rộng ví dụ để cần một phiếu từ bộ phận tài chính và một phiếu từ chủ ngân sách. Một người có thể đồng thời có hai role, và có trường hợp ủy quyền tạm thời.

Hãy thiết kế:

1. Assignment/slot nào được tạo khi mở vòng, và điều kiện nào bảo đảm hai người độc lập?
2. Các trường nào phân biệt tài khoản thực hiện, reviewer thật và người/chỗ được đại diện?
3. Những unique constraint nào ngăn người gốc và delegate cùng dùng một slot, đồng thời ngăn một người dùng nhiều slot để tự đủ điều kiện?
4. Tally phải thay đổi thế nào để hai phiếu cùng nhóm không bị hiểu là đủ điều kiện?
5. Sửa tổng tiền hoặc thu hồi grant ủy quyền giữa vòng làm các quyết định đã ghi còn hiệu lực ra sao?
6. Receipt khi retry sau khi vòng đã hoàn tất phải trả dữ kiện lịch sử và trạng thái hiện tại như thế nào để không gây nhầm?
7. Bước tạo tác dụng nghiệp vụ kiểm tra và tiêu thụ kết quả phê duyệt ra sao để không thực hiện lặp?

Một bản ghi quyết định tốt phải giúp trả lời ai đã quyết định điều gì, cho nội dung nào, trong vòng nào và theo căn cứ nào. Một thiết kế an toàn còn phải bảo đảm chỉ quyết định hợp lệ mới được lưu, không bị tính trùng, và không bị sử dụng cho nội dung khác sau khi vòng phê duyệt hoàn tất.
