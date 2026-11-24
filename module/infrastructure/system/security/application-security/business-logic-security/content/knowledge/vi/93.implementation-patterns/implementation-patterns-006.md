# Authorization decision object — Mô hình hóa kết quả quyết định phân quyền

## 1. Mục tiêu trong bảo vệ logic nghiệp vụ

Trong chương **Implementation Patterns**, authorization decision object là mẫu thiết kế biểu diễn một kết quả phân quyền bằng dữ liệu có cấu trúc. Thay vì chỉ trả `true` hoặc `false`, policy trả một đối tượng thể hiện kết luận, lý do, phạm vi được đánh giá và các điều kiện thực thi liên quan.

Mẫu này hữu ích khi ứng dụng cần ngăn tự phê duyệt, thao tác sai tenant, duyệt vượt hạn mức hoặc dùng lại một kết quả kiểm tra đã cũ. Nó giúp application service biết vì sao một hành động được cho phép, quyết định đó áp dụng cho dữ liệu nào và còn phải thực hiện nghĩa vụ gì trước khi báo thành công.

Sau bài học, người học có thể:

- Thiết kế kết quả phân quyền bất biến, có trạng thái rõ ràng và mặc định từ chối.
- Gắn quyết định với actor, tenant, action, resource và snapshot dữ liệu.
- Phân biệt quyết định phân quyền với kết quả thực thi nghiệp vụ.
- Xử lý nghĩa vụ bắt buộc, lỗi policy, quyết định hết hạn và quyền bị thu hồi.
- Dùng decision object trong application service cùng transaction, workflow và idempotency.
- Kiểm thử trường hợp tái sử dụng quyết định sai đối tượng hoặc bỏ qua nghĩa vụ.

Ví dụ dùng Java 17+ và một ca sử dụng phê duyệt yêu cầu mua hàng. Các kiểu policy là thiết kế nội bộ của bài, không phải một bản triển khai đầy đủ XACML hoặc một thư viện phân quyền có sẵn. Đoạn service minh họa dùng transaction đồng bộ của Spring; authentication, persistence và port nghiệp vụ cần được triển khai theo hợp đồng được mô tả.

## 2. Từ boolean tới một quyết định có ngữ cảnh

### 2.1. Những thông tin bị mất khi chỉ trả boolean

```java
if (policy.canApprove(actor, request)) {
    request.approve();
}
```

Đoạn code không cho biết `false` là do không có quyền, không có policy phù hợp hay dịch vụ cung cấp membership bị lỗi. Nó cũng không cho biết `true` vừa được tính cho revision nào, có yêu cầu audit bắt buộc không, hoặc có được dùng lại sau khi đối tượng thay đổi không.

Boolean vẫn phù hợp với một điều kiện đơn giản, cục bộ và không cần thêm ngữ cảnh. Khi nhiều lớp cần giải thích, thực thi và theo dõi cùng một quyết định, một kiểu dữ liệu rõ ràng giúp tránh việc mỗi caller tự suy diễn các điều kiện còn thiếu.

### 2.2. Một quyết định mẫu

Một cách đọc kết quả nghiệp vụ:

```text
Kết luận: PERMIT
Lý do: POLICY_SATISFIED
Actor: Carol
Tenant: T1
Action: APPROVE_PURCHASE
Resource: yêu cầu P100
Cơ sở: revision R7, resourceVersion 12, authorizationVersion 31
Policy: purchase-approval/v1
Hiệu lực: trong khoảng thời gian đã định nghĩa
Nghĩa vụ: ghi audit thành công trong cùng transaction
```

Kết quả này chỉ nói policy chấp nhận hành động trong ngữ cảnh đã đánh giá. Service vẫn cần kiểm tra workflow, ghi dữ liệu nhất quán và hoàn thành nghĩa vụ. `PERMIT` không có nghĩa giao dịch đã commit, ngân sách đã được giữ chỗ hoặc một dịch vụ ngoài đã xử lý thành công.

## 3. Tách điểm quyết định và điểm thực thi

Trong thuật ngữ phân quyền, PDP đánh giá policy và PEP thực thi kết quả. Hai vai trò có thể cùng nằm trong một ứng dụng; việc tách vai trò không bắt buộc phải tạo thêm dịch vụ mạng. [OASIS — XACML 3.0, glossary](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html).

```text
Authentication tin cậy
    -> actor và tenant được xác minh
    -> nạp facts có thẩm quyền cho actor/resource
    -> policy evaluator tạo decision object
    -> application service kiểm tra phạm vi, cơ sở, hiệu lực, nghĩa vụ
    -> domain kiểm tra trạng thái và bất biến
    -> ghi thay đổi + audit/outbox theo transaction
    -> commit và trả kết quả nghiệp vụ
```

| Thành phần | Vai trò trong mẫu thiết kế |
| --- | --- |
| Authentication adapter | Xác định actor thực sự; không tin actor ID trong body |
| Fact loader | Nạp membership, quyền, hạn mức và dữ liệu đối tượng từ nguồn có thẩm quyền |
| Policy evaluator | Đánh giá facts, trả kết luận và metadata của quyết định |
| Decision guard | Kiểm tra quyết định dùng được cho lời gọi hiện tại |
| Application service | Gọi guard, thực hiện nghĩa vụ và điều phối domain/transaction |
| Domain model | Giữ bất biến như không duyệt revision cũ hoặc trạng thái đã hủy |

Một object do code bất kỳ trong JVM tự tạo không tự có độ tin cậy. Ranh giới tin cậy nằm ở đường tạo và sử dụng nó: nguồn facts, evaluator được phép và entry point thực thi. Việc đặt tên một record là `AuthorizationDecision` không biến dữ liệu từ client thành kết quả phân quyền hợp lệ.

## 4. Mô hình hóa kết luận và mặc định từ chối

### 4.1. Bốn kết luận trong hợp đồng của bài

| Kết luận | Ý nghĩa | Có được thực thi lệnh được bảo vệ? |
| --- | --- | --- |
| `PERMIT` | Policy đã xác định đủ điều kiện cho phạm vi đã đánh giá | Chỉ khi decision hợp lệ và nghĩa vụ được đáp ứng |
| `DENY` | Có căn cứ xác định hành động không được phép | Không |
| `NOT_APPLICABLE` | Evaluator này không có policy áp dụng cho hành động | Không tại ranh giới cuối của bài |
| `INDETERMINATE` | Không thể đưa ra quyết định đầy đủ, chẳng hạn thiếu facts bắt buộc | Không |

XACML cũng có các giá trị Permit, Deny, NotApplicable và Indeterminate. Bài dùng tên tương ứng để làm rõ trạng thái; quy tắc kết hợp và cách thực thi dưới đây là hợp đồng nội bộ, không tuyên bố tương đương mọi ngữ nghĩa của chuẩn. [OASIS — XACML 3.0, authorization decision](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html).

Tại ranh giới thực thi cuối cùng, chỉ `PERMIT` rõ ràng mới có thể mở đường cho hành động. Không dùng `outcome != DENY`, vì biểu thức đó vô tình chấp nhận cả thiếu policy và lỗi đánh giá. OWASP cũng nhấn mạnh nguyên tắc mặc định từ chối và kiểm tra quyền trên mọi request. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

### 4.2. Kết hợp nhiều policy phải có hợp đồng riêng

Nếu ứng dụng có nhiều evaluator, cần phân biệt kết quả cục bộ với quyết định cuối. `NOT_APPLICABLE` của policy A có thể được chuyển tới bộ kết hợp để xét policy B; nó không tự là quyền thực thi.

Với ca duyệt mua hàng, có thể chọn hợp đồng: mọi điều kiện bắt buộc về tenant, membership, quyền thao tác và phân tách nhiệm vụ phải đạt; một điều kiện bị từ chối thì kết quả cuối bị từ chối; điều kiện bắt buộc chưa xác định được thì không được cấp quyền.

Không dùng `anyMatch(PERMIT)` cho các điều kiện bắt buộc phải đồng thời đúng. Cần định nghĩa thứ tự ưu tiên lý do, cách xử lý lỗi và nghĩa vụ của kết quả cuối. Một policy cho phép theo role không được tự xóa điều kiện cấm tự duyệt.

## 5. Những trường cần có và giới hạn của chúng

| Trường | Mục đích | Giới hạn cần hiểu |
| --- | --- | --- |
| `decisionId` | Liên kết decision với audit và lần đánh giá | Không phải credential hay key chống lặp command |
| `outcome` | Kết luận có kiểu rõ ràng | Không chứng minh service đã thực thi đúng |
| `reason` | Mã lý do ổn định cho vận hành/kiểm thử | Không nên trả nguyên mọi lý do nội bộ cho client |
| `scope` | Actor, tenant, action, resource đã được đánh giá | Phải đối chiếu với lời gọi hiện tại |
| `basis` | Revision, phiên bản đối tượng/quyền/policy | Nhãn version chỉ hữu ích khi được cập nhật và kiểm tra đúng |
| `evaluatedAt`, `expiresAt` | Khoảng thời gian quyết định có thể được chấp nhận | Chưa hết hạn không bảo đảm quyền chưa bị thu hồi |
| `obligations` | Những việc bắt buộc gắn với kết quả cho phép | Caller phải có handler và thực sự thực hiện |

Trong bài, `scope` chứa bốn định danh ổn định. `basis` chứa revision nội dung, version kỹ thuật của resource, version dữ liệu quyền và version policy. Nếu action có tham số ảnh hưởng đến quyền như số tiền hoàn, người nhận hoặc tập field được sửa, phải gắn thêm chúng vào phạm vi/intent được kiểm chứng, hoặc gắn với một snapshot chứa đầy đủ các giá trị đó.

Ví dụ duyệt ở đây sử dụng giá và nội dung của revision đã lưu; body không được tự thay giá trị được duyệt. Không dùng một hash thiếu trường người nhận hoặc tiền tệ rồi cho rằng toàn bộ ý định giao dịch đã được ràng buộc.

## 6. Thiết kế kiểu Java bất biến

### 6.1. Enum và phạm vi

Các public type dưới đây nằm trong file Java riêng khi triển khai. Các khối nhiều type chỉ nhằm trình bày; imports thông dụng gồm `java.util.UUID`, `java.util.Objects`, `java.util.Set`, `java.util.Optional`, `java.time.Instant` và `java.math.BigDecimal`.

```java
public enum BusinessAction {
    APPROVE_PURCHASE,
    CANCEL_PURCHASE
}

public enum DecisionOutcome {
    PERMIT, DENY, NOT_APPLICABLE, INDETERMINATE
}

public enum DecisionReason {
    POLICY_SATISFIED,
    NO_POLICY_FOR_ACTION,
    REQUIRED_FACTS_UNAVAILABLE,
    ACCOUNT_DISABLED,
    MEMBERSHIP_INACTIVE,
    TENANT_MISMATCH,
    AUTHORITY_MISSING,
    SELF_APPROVAL_FORBIDDEN,
    CURRENCY_NOT_ALLOWED,
    APPROVAL_LIMIT_EXCEEDED
}

public enum DecisionObligation {
    SUCCESS_AUDIT_IN_TRANSACTION,
    REDACT_SENSITIVE_FIELDS
}
```

`REDACT_SENSITIVE_FIELDS` minh họa một nghĩa vụ có thể dùng cho đường đọc khác. Guard của lệnh duyệt trong bài chỉ hỗ trợ audit; nếu nhận thêm nghĩa vụ redaction, nó sẽ từ chối thay vì lờ đi.

```java
public record DecisionScope(
        UUID actorId,
        UUID tenantId,
        BusinessAction action,
        UUID resourceId) {

    public DecisionScope {
        Objects.requireNonNull(actorId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(action);
        Objects.requireNonNull(resourceId);
    }
}

public record DecisionBasis(
        long resourceVersion,
        UUID contentRevisionId,
        long authorizationVersion,
        String policyVersion) {

    public DecisionBasis {
        Objects.requireNonNull(contentRevisionId);
        if (resourceVersion < 0 || authorizationVersion < 0
                || policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException("Invalid decision basis");
        }
    }
}
```

`authorizationVersion` trong ví dụ đại diện snapshot quyền của actor trong tenant: membership, permission và hạn mức liên quan. Nếu hệ thống phân tách nhiều nguồn quyền, cần revision/epoch hoặc evidence tương ứng cho từng nguồn; một counter cập nhật không đầy đủ không tạo bảo đảm độ mới.

### 6.2. Record chứa quyết định và kiểm tra bất biến

```java
public record BusinessAuthorizationDecision(
        UUID decisionId,
        DecisionOutcome outcome,
        DecisionReason reason,
        DecisionScope scope,
        Optional<DecisionBasis> basis,
        Instant evaluatedAt,
        Instant expiresAt,
        Set<DecisionObligation> obligations) {

    public BusinessAuthorizationDecision {
        Objects.requireNonNull(decisionId);
        Objects.requireNonNull(outcome);
        Objects.requireNonNull(reason);
        Objects.requireNonNull(scope);
        Objects.requireNonNull(basis);
        Objects.requireNonNull(evaluatedAt);
        Objects.requireNonNull(expiresAt);
        obligations = Set.copyOf(obligations);

        if (!expiresAt.isAfter(evaluatedAt)) {
            throw new IllegalArgumentException("Invalid validity interval");
        }

        boolean compatibleReason = switch (outcome) {
            case PERMIT -> reason == DecisionReason.POLICY_SATISFIED;
            case NOT_APPLICABLE ->
                reason == DecisionReason.NO_POLICY_FOR_ACTION;
            case INDETERMINATE ->
                reason == DecisionReason.REQUIRED_FACTS_UNAVAILABLE;
            case DENY -> reason != DecisionReason.POLICY_SATISFIED
                && reason != DecisionReason.NO_POLICY_FOR_ACTION
                && reason != DecisionReason.REQUIRED_FACTS_UNAVAILABLE;
        };
        if (!compatibleReason) {
            throw new IllegalArgumentException("Incompatible decision reason");
        }
        if (outcome == DecisionOutcome.PERMIT && basis.isEmpty()) {
            throw new IllegalArgumentException("Permit requires a basis");
        }
        if (outcome != DecisionOutcome.PERMIT && !obligations.isEmpty()) {
            throw new IllegalArgumentException(
                "This model attaches obligations only to permit"
            );
        }
    }
}
```

`Set.copyOf` ngăn caller sửa collection nghĩa vụ sau khi decision được tạo. Các giá trị bên trong cũng cần bất biến; không đưa entity ORM hoặc map mutable đang được chia sẻ vào object rồi coi record đã là một snapshot an toàn.

`basis` là `Optional` để biểu diễn lỗi đánh giá chưa có đủ evidence. Một `PERMIT` không được thiếu basis. Đây là lựa chọn schema của ví dụ; mô hình này chỉ gắn nghĩa vụ với permit, còn audit từ chối do tầng thực thi quan sát theo chính sách riêng.

Constructor kiểm tra tính nhất quán dữ liệu, không xác minh nguồn tạo. Một client vẫn có thể gửi JSON chứa mọi trường trông hợp lệ. Không nhận record này từ body rồi dùng nó như quyết định đã được server đánh giá.

## 7. Policy evaluator trả dữ liệu, không tạo tác dụng nghiệp vụ

### 7.1. Facts phải đến từ nguồn có thẩm quyền

Một snapshot đầu vào cho policy duyệt có thể có dạng:

```java
public record ApprovalFacts(
        DecisionScope scope,
        UUID resourceTenantId,
        UUID requesterId,
        long resourceVersion,
        UUID contentRevisionId,
        long authorizationVersion,
        boolean accountActive,
        boolean membershipActive,
        Set<BusinessAction> permissions,
        BigDecimal amount,
        String currency,
        BigDecimal approvalLimit,
        String limitCurrency) {

    public ApprovalFacts {
        Objects.requireNonNull(scope);
        Objects.requireNonNull(resourceTenantId);
        Objects.requireNonNull(requesterId);
        Objects.requireNonNull(contentRevisionId);
        Objects.requireNonNull(amount);
        Objects.requireNonNull(approvalLimit);
        permissions = Set.copyOf(permissions);
        if (resourceVersion < 0 || authorizationVersion < 0
                || amount.signum() < 0 || approvalLimit.signum() < 0
                || currency == null || currency.isBlank()
                || limitCurrency == null || limitCurrency.isBlank()) {
            throw new IllegalArgumentException("Invalid approval facts");
        }
    }
}
```

Fact loader dựng scope từ actor đã xác thực và đối tượng được nạp, không từ `actorId` do client tự nhận. Nó nạp requester, số tiền, tiền tệ, membership và hạn mức từ nguồn có thẩm quyền. `accountActive=false` nghĩa là đã biết account không hoạt động; không dùng `false` làm giá trị mặc định để che việc truy vấn bị lỗi.

Snapshot trên là dữ liệu đã đủ để evaluator tính toán. Khi không lấy được facts bắt buộc, adapter phải biểu diễn lỗi rõ ràng hoặc tạo `INDETERMINATE`; không cấp hạn mức vô hạn, quyền admin hoặc version giả để tiếp tục.

### 7.2. Evaluator minh họa

```java
public final class PurchaseApprovalPolicy {
    private static final String VERSION = "purchase-approval/v1";

    public String version() {
        return VERSION;
    }

    public BusinessAuthorizationDecision decide(ApprovalFacts f, Instant now) {
        if (f.scope().action() != BusinessAction.APPROVE_PURCHASE) {
            return result(f, DecisionOutcome.NOT_APPLICABLE,
                DecisionReason.NO_POLICY_FOR_ACTION, now);
        }
        if (!f.accountActive()) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.ACCOUNT_DISABLED, now);
        }
        if (!f.scope().tenantId().equals(f.resourceTenantId())) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.TENANT_MISMATCH, now);
        }
        if (!f.membershipActive()) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.MEMBERSHIP_INACTIVE, now);
        }
        if (!f.permissions().contains(BusinessAction.APPROVE_PURCHASE)) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.AUTHORITY_MISSING, now);
        }
        if (f.requesterId().equals(f.scope().actorId())) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.SELF_APPROVAL_FORBIDDEN, now);
        }
        if (!f.currency().equals(f.limitCurrency())) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.CURRENCY_NOT_ALLOWED, now);
        }
        if (f.amount().compareTo(f.approvalLimit()) > 0) {
            return result(f, DecisionOutcome.DENY,
                DecisionReason.APPROVAL_LIMIT_EXCEEDED, now);
        }
        return result(f, DecisionOutcome.PERMIT,
            DecisionReason.POLICY_SATISFIED, now);
    }

    private BusinessAuthorizationDecision result(
            ApprovalFacts f,
            DecisionOutcome outcome,
            DecisionReason reason,
            Instant now) {
        DecisionBasis basis = new DecisionBasis(
            f.resourceVersion(),
            f.contentRevisionId(),
            f.authorizationVersion(),
            VERSION
        );
        Set<DecisionObligation> obligations =
            outcome == DecisionOutcome.PERMIT
                ? Set.of(DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION)
                : Set.of();

        return new BusinessAuthorizationDecision(
            UUID.randomUUID(), outcome, reason, f.scope(),
            Optional.of(basis), now, now.plusSeconds(10), obligations
        );
    }

    public BusinessAuthorizationDecision unavailable(
            DecisionScope scope, Instant now) {
        return new BusinessAuthorizationDecision(
            UUID.randomUUID(),
            DecisionOutcome.INDETERMINATE,
            DecisionReason.REQUIRED_FACTS_UNAVAILABLE,
            scope,
            Optional.empty(),
            now,
            now.plusSeconds(10),
            Set.of()
        );
    }
}
```

Khoảng 10 giây chỉ là giá trị minh họa để trình bày kiểm tra hiệu lực, không phải một ngưỡng an toàn chung. Thời hạn phải phù hợp với rủi ro, độ mới facts và cơ chế thu hồi quyền của ứng dụng.

Evaluator không cập nhật yêu cầu, trừ ngân sách hoặc gửi email. Với cùng facts và policy, outcome/reason/nghĩa vụ phải nhất quán; decision ID và thời điểm đánh giá có thể khác giữa các lần gọi.

Policy này chỉ hỗ trợ so hạn mức cùng tiền tệ theo mã đã được chuẩn hóa. Nó không tự đổi tiền bằng tỉ giá tùy ý. Nếu cần quy đổi, phải thêm snapshot tỉ giá và quy tắc làm tròn vào facts/basis phù hợp.

`unavailable` dành cho adapter xử lý lỗi lấy facts đã được phân loại, chẳng hạn dependency timeout. Lỗi lập trình bất ngờ cũng phải dừng hành động và được quan sát; không catch mọi exception rồi trả `PERMIT`. Có thể để exception thoát ra thay vì cố tạo decision cho mọi loại lỗi.

## 8. Guard kiểm tra decision trước khi dùng

### 8.1. Phân biệt lý do policy với lỗi sử dụng quyết định

`SELF_APPROVAL_FORBIDDEN` giải thích tại sao policy từ chối. `SCOPE_MISMATCH` lại có nghĩa caller đang sử dụng decision không khớp lời gọi hiện tại. Hai loại thông tin cần được phân biệt khi theo dõi lỗi tích hợp hoặc tấn công tái sử dụng.

```java
public enum EnforcementFailure {
    DECISION_MISSING,
    DECISION_UNAVAILABLE,
    NOT_PERMITTED,
    SCOPE_MISMATCH,
    BASIS_MISMATCH,
    OUTSIDE_VALIDITY,
    UNSUPPORTED_OBLIGATION,
    REQUIRED_OBLIGATION_MISSING
}

public final class DecisionEnforcementException extends RuntimeException {
    private final EnforcementFailure code;

    public DecisionEnforcementException(EnforcementFailure code) {
        super(Objects.requireNonNull(code).name());
        this.code = code;
    }

    public EnforcementFailure code() {
        return code;
    }
}
```

### 8.2. Chỉ hỗ trợ những nghĩa vụ thực sự có handler

```java
public final class ApprovalDecisionGuard {
    private static final Set<DecisionObligation> SUPPORTED = Set.of(
        DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION
    );

    public void requirePermit(
            BusinessAuthorizationDecision decision,
            DecisionScope expectedScope,
            DecisionBasis expectedBasis,
            Instant now) {
        Objects.requireNonNull(expectedScope);
        Objects.requireNonNull(expectedBasis);
        Objects.requireNonNull(now);

        if (decision == null) {
            reject(EnforcementFailure.DECISION_MISSING);
        }
        if (!decision.scope().equals(expectedScope)) {
            reject(EnforcementFailure.SCOPE_MISMATCH);
        }
        if (decision.outcome() == DecisionOutcome.INDETERMINATE) {
            reject(EnforcementFailure.DECISION_UNAVAILABLE);
        }
        if (decision.outcome() != DecisionOutcome.PERMIT) {
            reject(EnforcementFailure.NOT_PERMITTED);
        }
        if (decision.basis().isEmpty()
                || !decision.basis().get().equals(expectedBasis)) {
            reject(EnforcementFailure.BASIS_MISMATCH);
        }
        if (now.isBefore(decision.evaluatedAt())
                || !now.isBefore(decision.expiresAt())) {
            reject(EnforcementFailure.OUTSIDE_VALIDITY);
        }
        if (!SUPPORTED.containsAll(decision.obligations())) {
            reject(EnforcementFailure.UNSUPPORTED_OBLIGATION);
        }
        if (!decision.obligations().contains(
                DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION)) {
            reject(EnforcementFailure.REQUIRED_OBLIGATION_MISSING);
        }
    }

    private void reject(EnforcementFailure code) {
        throw new DecisionEnforcementException(code);
    }
}
```

Khoảng hiệu lực của guard là `[evaluatedAt, expiresAt)`: đúng thời điểm hết hạn cũng bị từ chối. Với decision đi qua mạng, cần thiết kế độ lệch đồng hồ và nguồn thời gian; không tự nới hiệu lực vô hạn khi kiểm tra thất bại.

`expectedScope` phải được dựng độc lập từ actor và đối tượng hiện tại. Nếu lấy chính `decision.scope()` làm giá trị kỳ vọng, phép so sánh không bảo vệ được trường hợp Carol dùng quyết định của Alice hoặc đổi action từ đọc sang duyệt.

Guard xác nhận handler có thể hỗ trợ các nghĩa vụ; nó chưa thực hiện chúng. Service phải hoàn thành phần việc bắt buộc. Danh sách `SUPPORTED` không được mở rộng chỉ để tránh lỗi tương thích khi chưa có code thực thi nghĩa vụ mới.

Guard chuyên biệt này còn yêu cầu audit là nghĩa vụ tối thiểu của mọi lần duyệt mới. Vì vậy, một permit bị thiếu nghĩa vụ audit cũng không được chấp nhận. Model decision tổng quát có thể cho phép tập nghĩa vụ rỗng cho hành động khác; điểm thực thi vẫn phải giữ các yêu cầu tối thiểu của ca sử dụng mà nó bảo vệ.

## 9. Dùng decision trong application service và transaction

### 9.1. Một đường thực thi cho lệnh duyệt mới

Đoạn dưới là method trong application service được Spring quản lý; các dependency được inject qua constructor. Transaction management, transaction manager và proxy phải được kích hoạt trong ứng dụng. Ví dụ tập trung vào quyết định phân quyền và audit; hợp đồng replay command được trình bày riêng ở mục 12.

```java
@Transactional
public ApprovalResult approve(ApprovePurchaseCommand command) {
    Actor actor = currentActor.require();
    PurchaseRequest request = requests
        .findForUpdate(actor.tenantId(), command.requestId())
        .orElseThrow(() -> new DecisionEnforcementException(
            EnforcementFailure.NOT_PERMITTED
        ));

    DecisionScope expectedScope = new DecisionScope(
        actor.accountId(),
        actor.tenantId(),
        BusinessAction.APPROVE_PURCHASE,
        request.id()
    );

    ApprovalFacts facts = factLoader.load(actor, request);
    DecisionBasis expectedBasis = new DecisionBasis(
        request.version(),
        request.contentRevisionId(),
        facts.authorizationVersion(),
        policy.version()
    );

    BusinessAuthorizationDecision decision =
        policy.decide(facts, clock.instant());
    guard.requirePermit(
        decision, expectedScope, expectedBasis, clock.instant()
    );

    ApprovalResult result = request.approve(
        actor.accountId(),
        command.expectedRevisionId(),
        clock.instant()
    );
    requests.save(request);

    if (decision.obligations().contains(
            DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION)) {
        audit.appendApproved(actor, result, decision);
    }

    return result;
}
```

Import transaction annotation trong ví dụ là `org.springframework.transaction.annotation.Transactional`. Các port/kiểu nghiệp vụ được giả định có hợp đồng sau:

| Dependency/kiểu | Hợp đồng |
| --- | --- |
| `CurrentActor` / `Actor` | Trả actor đã xác thực với `accountId`, `tenantId` nội bộ; từ chối anonymous/context không hợp lệ |
| `ApprovePurchaseCommand` | Chứa request ID và revision người duyệt đã xem; không cho client chọn actor hoặc tự gán số tiền đã lưu |
| `PurchaseRequests` | Truy vấn/khóa theo tenant và ID; lưu qua cùng transaction |
| `PurchaseRequest` | Có ID, version, revision; `approve` kiểm tra trạng thái, revision và bất biến rồi trả `ApprovalResult` |
| `ApprovalFactLoader` | Trả facts bất biến, đúng actor/resource, với quyền và hạn mức từ nguồn có thẩm quyền |
| `PurchaseApprovalPolicy` | Evaluator ở mục 7; không tạo tác dụng nghiệp vụ |
| `ApprovalDecisionGuard` | Guard ở mục 8, được gọi trước hành động |
| `ApprovalAudit` | Ghi audit thành công qua cùng database/transaction; lỗi bắt buộc làm ca sử dụng thất bại |
| `Clock` | Nguồn thời gian server có thể thay bằng clock cố định trong test |

`expectedBasis` lấy phiên bản resource từ đối tượng đang được bảo vệ và phiên bản quyền từ loader tin cậy. Đây không phải cơ chế tự xác thực mọi facts: loader vẫn phải bảo đảm số tiền, requester và membership thuộc đúng snapshot, không trả dữ liệu từ cache sai tenant hoặc từ input chưa xác minh.

### 9.2. Quyền hợp lệ chưa thay thế bất biến nghiệp vụ

Carol có thể được phân quyền duyệt P100 nhưng P100 vừa bị hủy, chưa submit hoặc đã có một quyết định cuối. Domain phải từ chối chuyển trạng thái không hợp lệ.

Tương tự, decision cho revision R7 không cho phép duyệt R8. `command.expectedRevisionId()` ràng buộc ý định người duyệt với nội dung đã xem; `basis.contentRevisionId()` mô tả snapshot policy đã đánh giá. Cần kiểm tra cả hai quan hệ, không cho client gửi một revision mới rồi tự coi đó là bằng chứng đã xem đúng nội dung.

Các ghi trạng thái và audit trong ví dụ phải commit/rollback cùng nhau. Nếu gọi thêm dịch vụ ngoài, cần outbox hoặc giao thức phối hợp phù hợp; gửi yêu cầu ra ngoài không tự rollback với database local.

Khi tham gia một transaction bên ngoài, giá trị method trả về chưa tự chứng minh outer transaction đã commit. Hợp đồng response cuối phải phản ánh ranh giới commit thực sự của ca sử dụng.

## 10. Hiệu lực, thu hồi quyền và TOCTOU

### 10.1. Version và thời hạn giải quyết những vấn đề khác nhau

Giả sử decision được tạo lúc 10:00:00, hết hạn lúc 10:00:10. Carol bị thu hồi quyền lúc 10:00:02. Việc còn trước 10:00:10 không chứng minh Carol vẫn được phép duyệt.

Nếu membership/hạn mức thay đổi mà `authorizationVersion` không đổi, so sánh version không phát hiện được sự thay đổi. Nếu resource thay giá nhưng không đổi revision/version tương ứng, quyết định cũ cũng có thể bị dùng sai.

| Cơ chế | Bảo vệ được | Chưa tự bảo đảm |
| --- | --- | --- |
| Scope đầy đủ | Không dùng nhầm actor/tenant/action/resource | Dữ liệu chưa thay đổi sau lúc đánh giá |
| Resource version/revision | Nhận diện snapshot đối tượng | Phiên bản được kiểm tra nguyên tử với ghi |
| Authorization version | Nhận diện snapshot quyền khi mọi cập nhật tuân thủ hợp đồng | Thu hồi quyền không xảy ra ngay sau bước đọc version |
| Policy version | Phân biệt bộ quy tắc được đánh giá | Facts đầu vào còn mới hoặc policy cũ còn được chấp nhận |
| Expiry | Giới hạn cửa sổ tái sử dụng | Thu hồi tức thì hoặc chống thực thi trùng |

### 10.2. So sánh đúng vẫn có thể bị thay đổi dữ liệu sau kiểm tra

Đây là vấn đề time-of-check to time-of-use: dữ liệu có thể thay đổi giữa bước kiểm tra và bước sử dụng. Chỉ đọc version hiện tại rồi so sánh với decision chưa tự đóng khoảng trống đó.

Với resource, có thể giữ khóa tới commit hoặc ghi có điều kiện dựa trên version/state và kiểm tra kết quả cập nhật. Mọi đường sửa cùng đối tượng phải tuân theo cơ chế đã chọn.

Với quyền, cần định nghĩa điểm có hiệu lực của thu hồi. Nếu yêu cầu duyệt và thu hồi phải có thứ tự nhất quán, các đường thực thi phải phối hợp bằng khóa, epoch, conditional write hoặc cơ chế serial hóa thích hợp. Nếu quyền ở dịch vụ khác, transaction local không tự bao trùm nguồn quyền đó.

Ví dụ service giữ khóa resource nhưng chưa tự chứng minh atomicity với việc thu hồi membership. Fact loader và luồng thu hồi phải được triển khai theo cam kết consistency đã định nghĩa. Khi xung đột, đánh giá lại toàn bộ điều kiện cần thiết; không chỉ retry một câu `save` với decision cũ.

Đối với job chạy chậm hoặc chờ hàng giờ, nên lưu command/approval và dữ liệu truy vết cần thiết, rồi thực thi theo policy/delegation đã chọn. Không giữ một object `PERMIT` trong queue để dùng như quyền vô thời hạn.

## 11. Nghĩa vụ bắt buộc cần được thực thi đầy đủ

### 11.1. Phân biệt nghĩa vụ với thông tin tham khảo

| Loại thông tin | Ví dụ | Có thể bỏ qua? |
| --- | --- | --- |
| Nghĩa vụ | Ghi audit cùng transaction, che field nhạy cảm trước khi trả kết quả | Không nếu muốn chấp nhận decision đó |
| Thông tin tham khảo | Nhãn giải thích dùng cho quan sát hoặc gợi ý giao diện | Có theo hợp đồng, không được ảnh hưởng điều kiện bắt buộc |
| Evidence đã được đánh giá | Phiên bản membership, mức assurance, revision nội dung | Không phải một công việc caller tự đánh dấu đã hoàn tất |

Một service trả dữ liệu chưa che field không thể chấp nhận permit yêu cầu redaction chỉ vì nó đã gọi policy. Handler phải có khả năng xử lý đúng kiểu kết quả và đúng field; một nhãn `redacted=true` trong log không chứng minh response đã được xử lý.

Trong ví dụ duyệt, audit là nghĩa vụ ghi local cùng transaction. Nếu audit thất bại, hành động duyệt phải thất bại theo hợp đồng. Guard kiểm tra khả năng hỗ trợ trước hành động; service thực hiện nghĩa vụ và để lỗi bắt buộc làm rollback.

### 11.2. Xác định nghĩa vụ chạy trước, cùng hoặc sau tác dụng

| Thời điểm | Ví dụ thiết kế | Điều phải bảo đảm |
| --- | --- | --- |
| Trước hành động | Xác nhận assurance hoặc bằng chứng giao dịch cần thiết | Chưa đạt thì chưa được tạo tác dụng nghiệp vụ |
| Cùng transaction | Ghi audit thành công, lưu command hoặc reservation bắt buộc | Ghi cùng ranh giới atomicity đã chọn |
| Trước khi trả dữ liệu | Redaction hoặc giới hạn field | Dữ liệu chưa xử lý không được gửi ra caller |
| Sau commit qua cơ chế bền vững | Thông báo hoặc đồng bộ sự kiện bắt buộc | Có bản ghi bền vững, retry và kiểm soát gửi lặp |

Không mô hình hóa một yêu cầu step-up chưa được đáp ứng thành permit mà caller có thể dùng ngay. Nếu cần người dùng xác thực thêm, có thể trả kết quả từ chối/challenge có kiểu riêng, ràng buộc với actor và giao dịch; chỉ đánh giá lại để cấp quyền sau khi bằng chứng phù hợp được xác minh.

Mô hình enum trong bài chưa có challenge hoặc tham số nghĩa vụ. Khi mở rộng, cần schema có kiểu cho từng nghĩa vụ: field được che, phạm vi hành động hoặc loại bằng chứng cần thiết. Không dùng map tùy ý chứa tên class, script hoặc URL để caller thực thi như một lệnh do policy gửi tới.

Nghĩa vụ không nhận diện được hoặc thiếu handler phải dừng đường thực thi tương ứng. Đổi schema cần kiểm thử tương thích cả producer quyết định lẫn consumer thực thi, không chỉ phía evaluator.

## 12. Decision ID, idempotency và quyết định đã được chấp thuận

### 12.1. Mỗi định danh giải quyết một vấn đề

| Định danh/dữ liệu | Câu hỏi được giải quyết |
| --- | --- |
| `decisionId` | Lần đánh giá policy nào được dùng? |
| Business command ID / idempotency key | Đây có phải cùng một ý định đã được thực thi trước đó? |
| Resource revision | Nội dung nào được xem xét/phê duyệt? |
| Approval record | Quyết định nghiệp vụ nào đã được chấp nhận và commit? |
| Event ID | Đây có phải cùng sự kiện đang được gửi lại? |

Hai lần đánh giá cho cùng command có thể có hai `decisionId` khác nhau. Ngược lại, một decision được phép sử dụng trong một phạm vi thời gian cũng không có nghĩa command chỉ chạy được một lần.

Không dùng `decisionId` làm cờ “đã thanh toán” hoặc thay unique constraint của command. Muốn chống tác dụng lặp, cần scope key, so sánh intent và ghi kết quả cùng ranh giới transaction phù hợp.

### 12.2. Retry không được dùng kết quả cũ để bỏ kiểm tra quyền

Một scope chống lặp có thể gồm tenant, actor, action, resource và key. Intent cần chứa toàn bộ tham số ảnh hưởng nghiệp vụ. Cùng scope/key nhưng khác intent phải bị từ chối; các ghi đồng thời cần constraint hoặc cơ chế điều phối tương ứng.

Khi trả kết quả command cũ, vẫn phải kiểm tra caller có quyền đọc kết quả đó tại thời điểm tra cứu theo policy đã chọn. Đừng cho Alice dùng key của Carol để nhận số tiền, người nhận hoặc trạng thái ngoài quyền.

Service ở mục 9 minh họa một lần thực thi mới, chưa cài đặt API trả kết quả command cũ. Domain của nó vẫn phải từ chối chuyển trạng thái lặp. Khi bổ sung replay thân thiện với client, cần xác định riêng luồng tra kết quả, quyết định phân quyền và nghĩa vụ của luồng đó.

Ví dụ có thể mở rộng action thành một thao tác đọc kết quả command với policy riêng. Audit của lần truy cập/replay được phân biệt với approval/audit nghiệp vụ của lần chuyển trạng thái ban đầu. Không phát sinh approval hoặc outbox nghiệp vụ mới chỉ vì client retry.

Nếu một nghĩa vụ bắt buộc gắn với quyết định đang dùng, caller không được bỏ qua nó rồi trả kết quả cũ. Hãy xác định đúng action và nghĩa vụ của replay thay vì coi sự tồn tại của command record là bằng chứng mọi nghĩa vụ hiện tại đã hoàn tất.

### 12.3. Decision object không thay một approval bền vững

Một workflow có thể cho Carol phê duyệt trước, rồi worker thực hiện sau. Khi đó cần approval record hoặc lệnh đã được tiếp nhận với revision, phạm vi, người phê duyệt và điều kiện tiếp tục rõ ràng.

Worker thực hiện theo service identity/delegation hoặc quyết định nghiệp vụ đã được chấp nhận theo hợp đồng. Nó không tự trở thành Carol bằng cách deserialize một decision object cũ. Cần giữ riêng `initiatedBy`, `approvedBy`, `executedBy` khi chúng là các chủ thể khác nhau.

## 13. Reason code, response công khai và audit

### 13.1. Một lý do nội bộ không nhất thiết là thông báo cho client

Các reason như `TENANT_MISMATCH`, `MEMBERSHIP_INACTIVE` hoặc `APPROVAL_LIMIT_EXCEEDED` hữu ích khi kiểm thử/vận hành. Nếu trả chi tiết trước khi xác định caller có quyền biết đối tượng, chúng có thể tiết lộ tenant, quan hệ hoặc hạn mức nhạy cảm.

Tách hai hợp đồng:

```text
Kết quả nội bộ:
    outcome + reason + scope + basis + nghĩa vụ + decisionId

Response công khai:
    mã lỗi an toàn + thông báo phù hợp + reference để hỗ trợ tra cứu
```

Adapter ánh xạ lỗi authentication, không có quyền, không tìm thấy hoặc dependency không sẵn sàng theo hợp đồng API. `INDETERMINATE` không phải một loại cấp quyền tạm thời; việc phân loại response khác `DENY` giúp vận hành và retry mà vẫn không thực thi hành động.

Đối với người đã có quyền xem đối tượng, ứng dụng có thể cung cấp chi tiết nghiệp vụ phù hợp như yêu cầu xác thực thêm hoặc revision đã cũ. Cần quyết định theo policy tiết lộ, không serialize nguyên decision object cho mọi caller.

### 13.2. Audit ghi cả quyết định và kết quả thực thi

Một bản ghi truy vết phù hợp có thể gồm:

```text
decisionId, correlationId, commandReference
actorId, tenantId, action, resourceId
outcome, reason, policyVersion
resourceVersion, contentRevisionId, authorizationVersion
evaluatedAt, expiresAt
enforcementResult, enforcementFailureCode
businessResult, committedAt nếu có
```

`outcome=PERMIT` và `businessResult=FAILED` không mâu thuẫn: actor có thể đủ quyền nhưng domain hoặc persistence từ chối. Không ghi “đã duyệt” chỉ vì policy trả permit.

Lần bị từ chối cần đường audit/telemetry phù hợp nếu chính transaction nghiệp vụ rollback. Audit thành công bắt buộc trong ví dụ phải phản ánh kết quả commit. Không log toàn bộ credential, token, entity hoặc facts nhạy cảm để giải thích policy.

Reason code nên ổn định và có tài liệu; thông báo hiển thị có thể thay đổi/ngôn ngữ hóa độc lập. Với nhiều điều kiện cùng sai, cần quy tắc chọn primary reason nhất quán; tránh trả toàn bộ danh sách facts chỉ để giải thích một lần từ chối.

## 14. Cache, ranh giới mạng và tích hợp framework

### 14.1. Cache quyết định không chỉ theo user và role

Cache key thiếu tenant, action, resource hoặc dữ liệu ý định có thể dùng permit của đối tượng này cho đối tượng khác. Cache theo các trường đầy đủ vẫn cần xử lý độ mới của quyền, resource và policy.

Khi thiết kế cache cần xác định:

- Những thuộc tính nào ảnh hưởng đến policy và được gắn vào key/basis.
- Cách phát hiện membership, hạn mức, quan hệ và revision thay đổi.
- Thời hạn hiệu lực, invalidation và hành vi khi không kiểm chứng được version.
- Có được dùng snapshot cũ trong cửa sổ nào và tại điểm nào phải đánh giá lại.
- Cách tránh làm quyền đã bị thu hồi tiếp tục hiệu lực chỉ vì cache còn permit.

Cache kết quả deny cũng có thể làm quyền mới chưa sử dụng được; đó là vấn đề availability/trải nghiệm cần hợp đồng rõ. Dù là permit hay deny, không biến lỗi đọc cache thành mặc định cho phép.

### 14.2. Decision đi qua mạng cần thêm hợp đồng tin cậy

Nếu PDP là dịch vụ riêng, cần xác thực bên trả lời, bảo vệ truyền tải và kiểm tra schema/outcome/nghĩa vụ. JSON parse được không chứng minh response đến từ evaluator được tin cậy hoặc dành cho đúng consumer.

Không dùng deserialization Java tùy ý để nạp object từ nguồn không tin cậy. Với wire schema, cần quy định version, kiểu trường, giá trị enum và hành vi khi thiếu field hoặc có nghĩa vụ chưa hỗ trợ. `Optional` trong model Java là cách biểu diễn nội bộ; format JSON cần mapping rõ, không phụ thuộc ngẫu nhiên vào thư viện serialize.

Nếu chủ động thiết kế một decision token có chữ ký, phải xác định issuer, audience, subject, action, resource/revision, ý định, hiệu lực và cách chống replay/thu hồi theo yêu cầu. Chữ ký bảo vệ nguồn và toàn vẹn theo cơ chế đã chọn; nó không tự làm dữ liệu mới, không tự giới hạn một lần sử dụng và không thực hiện nghĩa vụ thay service.

### 14.3. Không đánh đồng với một kiểu framework cùng tên

Spring Security có hợp đồng `AuthorizationResult` với `isGranted()`. Một business decision giàu metadata là mô hình ứng dụng; không tự được framework thực thi chỉ vì có cấu trúc hoặc tên tương tự. [Spring Security — AuthorizationResult API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationResult.html).

Adapter chuyển sang kiểu framework cần ánh xạ rõ: chỉ kết quả permit phù hợp mới trở thành granted; thiếu policy và indeterminate không được coi là granted. Application service vẫn phải giữ các metadata cần thiết và thực thi nghĩa vụ ở ranh giới dữ liệu.

Nếu adapter chỉ giữ boolean rồi làm mất scope, basis hoặc nghĩa vụ, những bảo đảm tương ứng cũng bị mất. Method security cho phép vào một method không thay việc kiểm tra quyết định trên đúng đối tượng trong transaction và domain guard của ca sử dụng.

## 15. Kiểm thử decision object và đường thực thi

### 15.1. Những bất biến của model và policy

| Nhóm | Ca kiểm thử cần có |
| --- | --- |
| Constructor | Permit thiếu basis, khoảng thời gian sai, reason không tương thích hoặc nghĩa vụ gắn sai outcome bị từ chối |
| Bất biến dữ liệu | Sửa set đầu vào không sửa được nghĩa vụ/permission đã lưu |
| Account/membership | Account bị khóa hoặc membership không hoạt động không được permit |
| Tenant/quyền | Role đúng nhưng tenant sai, thiếu permission hoặc vượt hạn mức vẫn bị từ chối |
| Phân tách nhiệm vụ | Requester không tự duyệt dù có quyền thao tác thô |
| Giá trị tiền | Tiền tệ khác hoặc số tiền vượt hạn mức được xử lý đúng policy |
| Thiếu facts | Không tạo permit với giá trị quyền/hạn mức giả |
| Kết hợp policy | Một permit theo role không xóa một deny bắt buộc về tự duyệt |

### 15.2. Test guard với phạm vi, thời hạn và nghĩa vụ

Ví dụ JUnit Jupiter dưới đây kiểm tra các lớp model/guard đã trình bày. Các model nằm trong cùng package của test hoặc được import từ package tương ứng của ứng dụng.

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ApprovalDecisionGuardTest {
    private final Instant at = Instant.parse("2026-11-23T03:00:00Z");
    private final DecisionScope scope = new DecisionScope(
        new UUID(0, 1), new UUID(0, 2),
        BusinessAction.APPROVE_PURCHASE, new UUID(0, 3)
    );
    private final DecisionBasis basis = new DecisionBasis(
        12, new UUID(0, 7), 31, "purchase-approval/v1"
    );
    private final ApprovalDecisionGuard guard = new ApprovalDecisionGuard();

    private BusinessAuthorizationDecision permit(
            Set<DecisionObligation> obligations) {
        return new BusinessAuthorizationDecision(
            new UUID(0, 100),
            DecisionOutcome.PERMIT,
            DecisionReason.POLICY_SATISFIED,
            scope,
            Optional.of(basis),
            at,
            at.plusSeconds(10),
            obligations
        );
    }

    @Test
    void cannotReusePermitForAnotherResource() {
        var decision = permit(Set.of(
            DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION
        ));
        var another = new DecisionScope(
            scope.actorId(), scope.tenantId(), scope.action(), new UUID(0, 4)
        );

        var failure = assertThrows(
            DecisionEnforcementException.class,
            () -> guard.requirePermit(decision, another, basis, at)
        );
        assertEquals(EnforcementFailure.SCOPE_MISMATCH, failure.code());
    }

    @Test
    void expiryIsAnExclusiveBoundary() {
        var decision = permit(Set.of(
            DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION
        ));
        assertDoesNotThrow(() -> guard.requirePermit(
            decision, scope, basis, at.plusSeconds(9)
        ));

        var failure = assertThrows(
            DecisionEnforcementException.class,
            () -> guard.requirePermit(
                decision, scope, basis, at.plusSeconds(10)
            )
        );
        assertEquals(EnforcementFailure.OUTSIDE_VALIDITY, failure.code());
    }

    @Test
    void unsupportedObligationCannotBeIgnored() {
        var decision = permit(Set.of(
            DecisionObligation.REDACT_SENSITIVE_FIELDS
        ));
        var failure = assertThrows(
            DecisionEnforcementException.class,
            () -> guard.requirePermit(decision, scope, basis, at)
        );
        assertEquals(
            EnforcementFailure.UNSUPPORTED_OBLIGATION, failure.code()
        );
    }

    @Test
    void requiredAuditCannotBeRemovedFromPermit() {
        var decision = permit(Set.of());
        var failure = assertThrows(
            DecisionEnforcementException.class,
            () -> guard.requirePermit(decision, scope, basis, at)
        );
        assertEquals(
            EnforcementFailure.REQUIRED_OBLIGATION_MISSING, failure.code()
        );
    }

    @Test
    void decisionOwnsAnImmutableCopyOfObligations() {
        var input = new HashSet<DecisionObligation>();
        input.add(DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION);
        var decision = permit(input);

        input.clear();

        assertEquals(
            Set.of(DecisionObligation.SUCCESS_AUDIT_IN_TRANSACTION),
            decision.obligations()
        );
        assertThrows(
            UnsupportedOperationException.class,
            () -> decision.obligations().clear()
        );
    }
}
```

Mở rộng test thay từng trường actor, tenant, action, resource version, revision, authorization version và policy version một cách độc lập. Khi test đổi nhiều trường cùng lúc, một guard chạy trước có thể che việc thiếu kiểm tra ở guard còn lại.

### 15.3. Test application service và concurrency

Unit test model/guard chưa chứng minh service có gọi guard hoặc thực hiện audit. Cần integration test gọi application service qua bean thật với transaction/persistence phù hợp và fixture đã commit.

| Tình huống | Bằng chứng sau lần gọi |
| --- | --- |
| Guard từ chối | Không gọi hành vi duyệt/không có thay đổi nghiệp vụ đã commit |
| Audit bắt buộc ghi lỗi | Trạng thái phê duyệt cùng rollback |
| Policy permit nhưng revision người dùng đã xem cũ | Domain từ chối, không duyệt nội dung mới |
| Resource bị sửa sau lúc đánh giá | Khóa/conditional write xử lý theo cam kết, không lưu dựa trên snapshot cũ |
| Quyền bị thu hồi cạnh tranh với duyệt | Kết quả đúng điểm hiệu lực thu hồi đã định nghĩa |
| Hai command hoặc retry cạnh tranh | Không có tác dụng nghiệp vụ lặp; decision ID không thay cơ chế chống lặp |
| Body giả decision hoặc actor | Đường inbound không dùng dữ liệu giả làm quyết định server |
| Replay kết quả cũ | Kiểm tra quyền hiện tại và nghĩa vụ riêng; không tạo approval mới |
| Caller ngoài HTTP | Đi qua entry point được bảo vệ hoặc mô hình service/delegation tương ứng |

Test rollback nên đọc trạng thái đã commit bằng transaction độc lập để tránh chỉ nhìn entity trong persistence context. Với tác dụng ngoài, quan sát fake service/outbox theo thiết kế. Một status code từ chối không đủ chứng minh không có thay đổi trái phép.

Test concurrency cần transaction độc lập, điểm đồng bộ hợp lý và timeout hữu hạn. Không đặt barrier yêu cầu cả hai worker cùng giữ một khóa độc quyền trên cùng row. Cũng không dùng vài lần gọi tuần tự rồi kết luận không có race.

## 16. Bài tập áp dụng

Một ứng dụng hoàn tiền trả kết quả policy như sau:

```json
{
  "allowed": true,
  "message": "manager",
  "userId": "carol"
}
```

Controller cho client gửi lại JSON này để xác nhận giao dịch. Service chỉ kiểm tra `allowed`; cache theo `userId`; lỗi kết nối policy được chuyển thành `allowed=true`. Sau khi gửi lệnh hoàn tiền, service mới cố ghi audit nhưng bỏ qua lỗi ghi.

Hãy thực hiện:

1. Xác định ranh giới tin cậy bị vi phạm và các tham số hoàn tiền phải được ràng buộc: đối tượng, số tiền, tiền tệ, người nhận, revision và actor.
2. Thiết kế outcome/reason có kiểu rõ ràng, đặc biệt cho thiếu policy và lỗi facts bắt buộc.
3. Thiết kế scope/basis và quy tắc immutable; chỉ ra những thay đổi nào phải tăng version hoặc tạo revision mới.
4. Viết guard kiểm tra phạm vi, thời hạn, phiên bản và nghĩa vụ trước tác dụng.
5. Phân biệt decision ID, command ID, approval record và event ID.
6. Chọn cơ chế nhất quán giữa hoàn tiền, hạn mức dùng chung và thu hồi quyền; nêu rõ giới hạn của transaction local.
7. Định nghĩa response công khai, audit nội bộ và hành vi khi nghĩa vụ bắt buộc không thực hiện được.
8. Viết test giả decision, đổi người nhận, cache khác tenant, decision cũ, policy timeout và yêu cầu trùng.

Bài làm đạt cần chứng minh một permit được dùng cho đúng chủ thể, hành động và snapshot, mọi điều kiện thực thi bắt buộc đều được đáp ứng, và các kết quả chưa xác định không mở đường cho tác dụng nghiệp vụ. Quyết định phân quyền, kết quả thực thi và bằng chứng commit phải được thể hiện riêng để có thể kiểm tra trách nhiệm và xử lý retry đúng.
