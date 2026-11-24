# Policy object pattern: đóng gói quyết định bảo vệ quy tắc nghiệp vụ

Một API hoàn tiền có thể kiểm tra role ở controller, kiểm tra owner ở service và kiểm tra số tiền ở một helper khác. Khi thêm API quản trị hoặc consumer bất đồng bộ, một đường gọi dễ bỏ sót điều kiện. Mỗi đoạn `if` đều có vẻ hợp lý, nhưng không có một nơi thể hiện đầy đủ điều kiện để chấp nhận hành động.

**Policy object pattern** đưa quyết định cho một hành động cụ thể vào một đối tượng có hợp đồng rõ ràng: nhận actor, đối tượng nghiệp vụ, ý định và các dữ kiện cần thiết; trả kết quả cho phép hoặc từ chối cùng lý do. Pattern giúp đọc, tái sử dụng và kiểm thử quy tắc bảo vệ nghiệp vụ. Ứng dụng vẫn cần điểm cưỡng chế, dữ liệu đáng tin cậy, transaction và bảo vệ concurrency để biến quyết định thành một thay đổi an toàn.

Trong chương **Implementation Patterns** của module **Business Logic Security**, bài dùng luồng khách hàng tạo yêu cầu hoàn tiền để minh họa chống thao tác sai quyền, sửa số tiền, bỏ qua duyệt và gửi yêu cầu trùng. Ví dụ Java dùng cú pháp Java 17 và độc lập với framework. Phần điều phối transaction được ghi rõ là mã giả; đây chưa phải ứng dụng persistence hoàn chỉnh.

## 1. Đặt tên rõ cho quyết định cần bảo vệ

### 1.1. Vấn đề của những điều kiện rải rác

```text
Controller A: có quyền refund thì gọi service
Controller B: là ADMIN thì gọi repository
Service:     chưa quá số tiền thì tạo refund
Consumer:    message chứa approved=true thì thực thi
```

Thiết kế này chưa phân biệt quyền tạo yêu cầu, quyền duyệt và quyền chuyển tiền. Không rõ ADMIN được tạo thay khách hay được bỏ qua mọi invariant; message có thể xuất phát từ dữ liệu cũ hoặc đường gọi thiếu kiểm tra.

Các policy nên được đặt tên theo hành động:

```text
RequestRefundPolicy          -> được tạo yêu cầu chờ duyệt không?
ApproveRefundPolicy          -> được duyệt yêu cầu cụ thể này không?
ExecuteApprovedRefundPolicy  -> được thực thi yêu cầu đã duyệt không?
```

Ba policy có actor, dữ kiện và hậu quả khác nhau. Cho phép tạo yêu cầu không cấp quyền duyệt hoặc chuyển tiền.

### 1.2. Hợp đồng khái quát

```text
Decision = Policy.evaluate(Actor, ResourceFacts, Intent, EnvironmentFacts)
```

- **Actor:** danh tính, tenant và quyền do hệ thống đã xác minh.
- **ResourceFacts:** dữ liệu authoritative của đối tượng và các quan hệ liên quan.
- **Intent:** hành động và tham số mà caller đề nghị.
- **EnvironmentFacts:** thời điểm server, cấu hình policy hoặc dữ kiện rủi ro cần thiết.
- **Decision:** kết quả cho đúng hành động được đánh giá.

Trong bài, policy là một phép tính thuần: cùng đầu vào hợp lệ và cùng phiên bản policy cho cùng kết quả; không ghi database, gọi provider hoặc đọc ngầm request hiện tại. Đây là lựa chọn thiết kế để làm rõ phụ thuộc, không phải yêu cầu mọi hệ thống authorization phải dùng cùng một implementation.

Policy object hữu ích khi có nhiều điều kiện actor/object/state, nhiều entry point hoặc cần kiểm thử bảng quyết định độc lập. Nếu một điều kiện nhỏ chỉ dùng trong một aggregate, một method domain có tên rõ ràng có thể đủ. Không cần interface và registry chỉ để thay một phép so sánh đơn giản.

## 2. Policy và những thành phần xung quanh

| Thành phần | Trách nhiệm | Điều không tự bảo đảm |
|---|---|---|
| Authentication adapter | Xác minh caller, tạo actor context | Caller được thao tác mọi đối tượng |
| Input validation | Kiểm tra định dạng và kích thước request | Amount đúng định dạng được phép hoàn |
| Fact loader/repository | Đọc dữ liệu trong scope và cơ chế nhất quán | Đối tượng đọc được đã được authorization |
| Policy object | Đánh giá một hành động trên facts đầu vào | Kết quả còn đúng sau mọi thay đổi đồng thời |
| Application service/handler | Tải facts, cưỡng chế quyết định, điều phối ghi | Không còn đường gọi khác đi tắt |
| Aggregate/state machine | Bảo vệ chuyển trạng thái và invariant | Mọi actor gọi chuyển trạng thái đều có quyền |
| Database constraint/concurrency | Bảo vệ điều kiện tại ranh giới ghi | Database biết toàn bộ policy của actor |

Policy có thể được tổ chức theo tinh thần Strategy: thay cách quyết định bằng implementation khác nhau. Specification thường biểu diễn điều kiện có thể kiểm tra/kết hợp; policy của bài còn mang ngữ nghĩa action, mã lý do và phiên bản. Đổi tên một `Predicate` thành `Policy` chưa đủ tạo một thiết kế authorization đầy đủ.

Rule engine hoặc dịch vụ policy bên ngoài cũng có thể đánh giá quyết định; chúng vẫn cần facts đáng tin cậy và điểm cưỡng chế tại nơi phát sinh hiệu lực.

[OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) khuyến nghị deny by default và kiểm tra quyền trên mọi request. Với thiết kế bài này, policy biểu diễn quyết định; các đường tạo thay đổi phải cưỡng chế quyết định tương ứng.

## 3. Fixture: khách hàng đề nghị hoàn tiền

### 3.1. Phạm vi hành động và số tiền

- Khách hàng C-7 thuộc TENANT-A, có authority `refund:request`.
- Payment PAY-42 thuộc TENANT-A, customer C-7, đang CAPTURED và có version 12.
- Đã thu 1.000.000 VND, đã hoàn thành công 200.000 VND, đang giữ chỗ cho yêu cầu khác 100.000 VND.
- Phần còn có thể giữ chỗ là 700.000 VND; khách đề nghị thêm 400.000 VND trước deadline.
- Tạo yêu cầu hợp lệ dẫn đến PENDING_APPROVAL và giữ chỗ amount tương ứng; chưa gọi provider hoặc chuyển tiền.

Tiền trong mã dùng `long` theo đơn vị nhỏ nhất của currency đã xác định. Với fixture VND này, các số là số đồng. Không giả định mọi currency có hai chữ số thập phân; chuyển đổi từ dữ liệu nhập phải theo metadata currency và hợp đồng API.

### 3.2. Các invariant

| Mã | Quy tắc |
|---|---|
| PO-01 | Đúng authority, customer và tenant của payment |
| PO-02 | State và thời hạn cho phép tạo yêu cầu mới |
| PO-03 | Amount dương, không vượt captured trừ cả refunded và reserved |
| PO-04 | Facts đã kiểm tra phải phù hợp với dữ liệu transaction sẽ cập nhật |
| PO-05 | Yêu cầu mới luôn PENDING_APPROVAL, không bỏ qua duyệt |
| PO-06 | Retry cùng ý định không tạo request hoặc giữ chỗ lần nữa |

Invariant tổng tiền chưa chứng minh khách có căn cứ hoàn đúng mặt hàng/claim. Sản phẩm thực tế có thể cần return/claim ID, số lượng được hoàn và uniqueness theo nghĩa vụ. Hai key khác nhau cho cùng claim có thể là lạm dụng dù tổng tiền chưa vượt payment.

Fixture không có nhánh ADMIN bỏ qua invariant. Nhân viên tạo thay khách cần action/policy riêng, không giả mạo actor thành customer.

## 4. Hợp đồng dữ kiện và kết quả

| Dữ kiện | Nguồn hợp lệ của fixture |
|---|---|
| Subject, tenant, authorities | Authentication/authorization context đã xác minh |
| Customer, state, version, captured/refunded/reserved, currency | Repository authoritative |
| Deadline | Policy/facts server |
| Amount đề nghị | Command client, cần đánh giá |
| Expected version | Command client, so với version server |
| Thời điểm đánh giá | Clock server tại execution gate |

Không nhận `isOwner`, `remainingAmount`, `approved` từ client rồi coi là facts đã xác minh. Expected version cũng chỉ là yêu cầu concurrency của caller; gửi đúng version không tự có quyền.

Policy nhận snapshot chứa các facts cần thiết, thay vì entity lazy-loading hoặc repository. Snapshot bất biến giữ nguyên dữ liệu trong bộ nhớ, không khóa database và không khiến dữ liệu cũ trở nên mới.

Java record có component field `final`, nhưng một component tham chiếu collection mutable vẫn cần được bảo vệ. Ví dụ dùng `Set.copyOf` cho authorities. Tham khảo cấu trúc record tại [Oracle Java 17: Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html).

Kết quả có mã lý do giúp phân biệt thiếu quyền, sai version và quá hạn mức. `Decision` không phải approval hoặc capability để dùng mãi ở request khác: nó không chứng minh facts hiện tại còn đúng hoặc transaction đã commit.

## 5. Ví dụ Java: policy thuần cho hành động tạo yêu cầu

Các kiểu dưới đây có thể đặt cùng package và sử dụng cùng nhau với Java 17. Chúng thể hiện phần đánh giá của fixture; chưa có authentication adapter, repository hoặc transaction. Khởi tạo `Actor` không xác minh danh tính: ứng dụng chỉ được dựng actor từ nguồn đã xác minh.

### 5.1. Actor, facts và command

```java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

record Actor(
        String subjectId,
        String tenantId,
        Set<String> authorities) {
    Actor {
        Objects.requireNonNull(subjectId);
        Objects.requireNonNull(tenantId);
        authorities = Set.copyOf(authorities);
    }
}

enum PaymentState {
    CAPTURED,
    VOIDED
}

record PaymentSnapshot(
        String id,
        String tenantId,
        String customerId,
        PaymentState state,
        long version,
        long capturedMinor,
        long refundedMinor,
        long reservedMinor,
        String currency,
        Instant refundDeadline) {
    PaymentSnapshot {
        Objects.requireNonNull(id);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(state);
        Objects.requireNonNull(currency);
        Objects.requireNonNull(refundDeadline);

        if (version < 0
                || capturedMinor < 0
                || refundedMinor < 0
                || reservedMinor < 0
                || refundedMinor > capturedMinor
                || reservedMinor > capturedMinor - refundedMinor) {
            throw new IllegalArgumentException("Inconsistent payment facts");
        }
    }

    long availableMinor() {
        return capturedMinor - refundedMinor - reservedMinor;
    }
}

record RequestRefundCommand(
        long amountMinor,
        long expectedPaymentVersion) {
}

record RefundContext(
        Actor actor,
        PaymentSnapshot payment,
        RequestRefundCommand command,
        Instant evaluatedAt) {
    RefundContext {
        Objects.requireNonNull(actor);
        Objects.requireNonNull(payment);
        Objects.requireNonNull(command);
        Objects.requireNonNull(evaluatedAt);
    }
}
```

Định danh cần được kiểm tra định dạng ở boundary phù hợp; constructor ở đây thể hiện ràng buộc null và tính nhất quán của số tiền. Không deserialize raw JSON thành `PaymentSnapshot` rồi coi đó là dữ liệu server.

Phép kiểm tra `reservedMinor > capturedMinor - refundedMinor` tránh cộng hai giá trị lớn trước khi kiểm tra giới hạn. Với facts hợp lệ, phép trừ tính phần còn lại không âm và không vượt phạm vi `long`. Mọi luồng cập nhật tiền vẫn phải giữ cùng invariant; constructor không sửa được database đã sai.

### 5.2. Quyết định và implementation

```java
enum Reason {
    PERMITTED,
    TENANT_MISMATCH,
    NOT_OWNER,
    MISSING_PERMISSION,
    VERSION_CONFLICT,
    INVALID_STATE,
    WINDOW_CLOSED,
    INVALID_AMOUNT,
    ABOVE_AVAILABLE
}

record Decision(Reason reason, String policyVersion) {
    Decision {
        Objects.requireNonNull(reason);
        Objects.requireNonNull(policyVersion);
    }

    boolean allowed() {
        return reason == Reason.PERMITTED;
    }
}

interface Policy<C> {
    Decision evaluate(C context);
}

final class RequestRefundPolicy implements Policy<RefundContext> {
    static final String VERSION = "refund-request/v1";

    @Override
    public Decision evaluate(RefundContext context) {
        Objects.requireNonNull(context);
        var actor = context.actor();
        var payment = context.payment();
        var command = context.command();

        if (!actor.tenantId().equals(payment.tenantId())) {
            return deny(Reason.TENANT_MISMATCH);
        }
        if (!actor.subjectId().equals(payment.customerId())) {
            return deny(Reason.NOT_OWNER);
        }
        if (!actor.authorities().contains("refund:request")) {
            return deny(Reason.MISSING_PERMISSION);
        }
        if (command.expectedPaymentVersion() != payment.version()) {
            return deny(Reason.VERSION_CONFLICT);
        }
        if (payment.state() != PaymentState.CAPTURED) {
            return deny(Reason.INVALID_STATE);
        }
        if (!context.evaluatedAt().isBefore(payment.refundDeadline())) {
            return deny(Reason.WINDOW_CLOSED);
        }
        if (command.amountMinor() <= 0) {
            return deny(Reason.INVALID_AMOUNT);
        }
        if (command.amountMinor() > payment.availableMinor()) {
            return deny(Reason.ABOVE_AVAILABLE);
        }
        return new Decision(Reason.PERMITTED, VERSION);
    }

    private Decision deny(Reason reason) {
        return new Decision(reason, VERSION);
    }
}
```

`PERMITTED` chỉ có nghĩa “đủ điều kiện tạo yêu cầu mới”, không có nghĩa “đã được phê duyệt”. Policy không thay state, tăng reservation, tạo refund hoặc gọi provider.

Tenant và owner được kiểm tra trước thông tin về trạng thái, version và amount. API không nên dùng mã lý do nội bộ để tiết lộ chi tiết payment cho actor ngoài scope. Chỉ công bố `VERSION_CONFLICT` hoặc `ABOVE_AVAILABLE` ở mức phù hợp với quyền xem dữ liệu của caller.

Nếu không dựng được context/facts hợp lệ, ví dụ này ném lỗi. Lớp điều phối phải dừng hiệu lực và ánh xạ lỗi kỹ thuật theo hợp đồng; không bắt mọi lỗi rồi mặc định cho phép. Hệ thống lớn hơn có thể có kết quả INDETERMINATE, nhưng kết quả đó không được cưỡng chế như PERMIT.

### 5.3. Một lần đánh giá cụ thể

```java
class RefundPolicyDemo {
    public static void main(String[] args) {
        var actor = new Actor(
            "C-7", "TENANT-A", Set.of("refund:request")
        );
        var payment = new PaymentSnapshot(
            "PAY-42", "TENANT-A", "C-7",
            PaymentState.CAPTURED, 12L,
            1_000_000L, 200_000L, 100_000L,
            "VND", Instant.parse("2026-12-01T00:00:00Z")
        );
        var command = new RequestRefundCommand(400_000L, 12L);
        var context = new RefundContext(
            actor, payment, command,
            Instant.parse("2026-11-23T03:00:00Z")
        );

        var decision = new RequestRefundPolicy().evaluate(context);
        System.out.println(decision.allowed());
        System.out.println(decision.reason());
        System.out.println(payment.availableMinor());
    }
}
```

Kết quả suy ra từ fixture là `true`, `PERMITTED` và `700000`. Phần còn lại vẫn là 700.000 vì policy chưa giữ chỗ 400.000. Chỉ sau khi service cưỡng chế quyết định và transaction ghi thành công thì phần còn lại authoritative mới giảm xuống 300.000.

Thời gian trong ví dụ là fixture cố định. Ở sản phẩm, `evaluatedAt` lấy từ clock server tại execution gate, không từ field client chọn. Các đoạn Java minh họa logic đánh giá; chưa mô tả cách xác thực hoặc ghi một refund thật.

## 6. Tích hợp vào application service mà không mất invariant

### 6.1. Đánh giá và cưỡng chế là hai bước khác nhau

```text
decision = policy.evaluate(context)
log(decision)
repository.createRefund(command)  // lỗi: tiếp tục cả khi bị từ chối
```

Policy đúng vẫn vô dụng nếu caller bỏ qua kết quả. Service phải biến quyết định không cho phép thành đường dừng trước mutation. Không để repository tạo hiệu lực được nhiều caller sử dụng với một bước kiểm tra tùy chọn.

```text
HTTP / job / consumer
         |
         v
Application service
    xác định actor đáng tin cậy
    đọc facts nhất quán trong đúng scope
    kiểm tra access và replay
    evaluate policy cho ý định mới
    enforce decision
    ghi các thay đổi cục bộ cần đi cùng nhau
         |
         v
Transaction commit
```

UI có thể kiểm tra để bật/tắt nút, nhưng service vẫn phải đánh giá lại trước khi chấp nhận thay đổi. Quyết định hiển thị ở màn hình không phải giấy phép thực thi sau này.

### 6.2. Mã giả cho tạo yêu cầu và retry

```text
requestRefund(paymentId, command, idempotencyKey):
    actor = trustedIdentity.currentActor()

    in database transaction:
        payment = loadAndLockPayment(actor.tenantId, paymentId)
        accessPolicy.requireMayAccessRefunds(actor, payment)

        scope = (actor.tenantId, actor.subjectId, "REFUND_REQUEST", idempotencyKey)
        intent = normalize(paymentId, command.amountMinor,
                           command.expectedPaymentVersion)
        previous = idempotency.find(scope)

        if previous exists:
            require previous.intent == intent
            return authorizedResult(previous.refundRequestId)

        facts = snapshotFromAuthoritativePayment(payment)
        context = (actor, facts, command, serverClock.now())
        decision = requestRefundPolicy.evaluate(context)
        require decision.allowed

        request = createRefundRequest(
            paymentId = payment.id,
            amount = command.amountMinor,
            currency = payment.currency,
            status = PENDING_APPROVAL,
            requestedBy = actor.subjectId
        )
        reserveRefundAmount(payment, request)
        idempotency.bindUnique(scope, intent, request.id)
        outbox.appendRefundReviewRequested(request)
        audit.appendAccepted(actor, request, decision.policyVersion)

    return committed request result
```

Đây là mã giả; các helper không phải API thư viện. `require decision.allowed` phải làm đường ghi thất bại và rollback đúng cách. Request, reservation, binding, outbox và audit chấp nhận phải thực sự tham gia cùng ranh giới transaction để có bảo đảm nguyên tử như thiết kế.

`accessPolicy` trước replay kiểm tra quyền truy cập hiện tại, gồm quyền chức năng phù hợp, mà không bắt state/version/capacity thỏa điều kiện tạo yêu cầu mới. Sau lần đầu, version và phần tiền khả dụng có thể đổi. Replay đúng key/intent cần trả request cũ thay vì giữ chỗ lần nữa; vẫn không được đọc kết quả ngoài quyền.

Scope/key phải có uniqueness ở database. Cùng key nhưng khác payment hoặc amount phải bị conflict, không dùng dữ liệu mới ghi đè ý định đã chấp nhận. Khi triển khai, cần giới hạn độ dài key, chuẩn hóa dữ liệu ý định và kiểm tra fingerprint theo hợp đồng ổn định.

### 6.3. Policy thuần không tự giải quyết TOCTOU

Phần còn lại là 700.000; hai request cùng đọc snapshot đó và đều đề nghị 500.000. Policy trả PERMITTED cho cả hai theo đầu vào nó được cung cấp. Nếu mỗi request giữ chỗ riêng mà không kiểm soát concurrency, tổng reservation có thể vượt phần được phép hoàn.

Có thể dùng khóa hàng payment giữ đến commit, optimistic version hoặc conditional update kiểm tra đủ tiền tại bước ghi. Với version/conditional update, phải xác minh kết quả cập nhật và rollback toàn bộ transaction khi conflict. Chỉ so expected version với snapshot trong Java chưa tạo bảo vệ concurrency ở database.

Nếu phần tiền là tổng nhiều hàng, khóa/version một hàng chỉ có tác dụng khi mọi đường thay tổng cùng bảo vệ qua hàng hoặc giao thức đó. Một bulk update hay callback không tuân thủ có thể làm hỏng giả định của policy.

Sau conflict, đọc lại facts và đánh giá lại ý định mới. Không tái sử dụng kết quả PERMITTED cũ khi retry transaction. Trường hợp không rõ commit đã thành công hay chưa cần tra operation/request theo idempotency; không tự tạo ý định khác key.

### 6.4. Không dùng quyền tạo yêu cầu để bỏ qua duyệt

Request mới luôn PENDING_APPROVAL, kể cả client gửi thêm `approved=true` hoặc `status=APPROVED`. API chỉ ánh xạ field được phép vào command; state được server quyết định.

Luồng duyệt có policy riêng về actor, tenant/object scope, trạng thái, hạn mức và separation of duties. Luồng thực thi kiểm tra approval hợp lệ cho đúng request/revision, amount, currency và đích hoàn tiền, đồng thời ngăn thực thi trùng. Đổi nội dung nhạy cảm sau duyệt cần hủy approval cũ hoặc mở vòng duyệt mới theo policy.

[OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html) nhấn mạnh kiểm soát thứ tự bước, bảo vệ dữ liệu giao dịch và có gate trước thực thi. Trong fixture, `RequestRefundPolicy` chỉ là gate của bước tạo yêu cầu, không thay gate duyệt hoặc chuyển tiền.

Transaction database không rollback được một khoản tiền đã chuyển ở provider. Khi đến bước thực thi, cần operation ID ổn định, giao thức idempotency/đối soát và state machine cho kết quả chưa rõ. Không nhét lời gọi provider vào `evaluate`.

## 7. Kết hợp policy con mà không tạo đường bỏ qua

### 7.1. Phải nhìn thấy toán tử và phạm vi điều kiện

Nếu mọi điều kiện là bắt buộc, phép kết hợp là ALL:

```text
sameTenant
AND ownsPayment
AND hasRequestPermission
AND paymentAllowsNewRequest
AND amountWithinAvailable
```

Sai lầm nguy hiểm là đổi thành ANY vì muốn “linh hoạt”:

```text
ownsPayment OR hasRequestPermission OR amountWithinAvailable
```

Một amount nhỏ hợp lệ có thể làm biểu thức sau cho phép dù payment thuộc người khác.

Khi mở rộng căn cứ quyền trên đối tượng, có thể có OR trong một phần của công thức nhưng vẫn giữ invariant khác:

```text
sameTenant
AND (ownsPayment OR hasExplicitDelegationForThisPayment)
AND hasRequestPermission
AND paymentAllowsNewRequest
AND amountWithinAvailable
```

Đây là ví dụ mở rộng, không phải implementation của fixture. Delegation phải được server xác minh theo resource, action và thời hạn; không phải cờ client tự gửi. Một role STAFF không tự tương đương với được ủy quyền trên mọi payment.

### 7.2. Tập rule rỗng và policy không áp dụng

Bộ ghép tổng quát phải định nghĩa kết quả khi không có rule, không có policy phù hợp hoặc không đủ dữ kiện. Với hành động được bảo vệ, không có căn cứ cho phép thì không tạo hiệu lực.

Không để `allMatch` trên danh sách rỗng vô tình thành mặc định cho phép, hoặc coi NOT_APPLICABLE là PERMIT. Action mới chưa đăng ký policy phải bị từ chối hoặc dừng có kiểm soát, thay vì rơi vào policy mặc định dễ cho phép.

Nếu engine dùng PERMIT, DENY, NOT_APPLICABLE và INDETERMINATE, phải xác định đúng thuật toán combining của engine; không giả định nó là phép `&&` trên boolean.

### 7.3. Fail-fast và bảo vệ thông tin lý do

Ví dụ Java dừng ở lý do đầu tiên. Thứ tự rule là một phần hành vi cần kiểm thử; từ chối ở tenant/owner không được làm lộ hạn mức hoặc trạng thái đối tượng.

Màn hình nội bộ có thể cần nhiều lý do để xử lý, nhưng phải kiểm tra quyền xem trước. Không trả một danh sách như “tenant khác, owner C-7, còn 700.000” cho người không có quyền nhìn payment. Tách mã audit nội bộ khỏi thông tin an toàn để công bố qua API.

## 8. Vòng đời, cache và phiên bản policy

### 8.1. Giữ policy stateless

Policy của ví dụ không lưu `currentActor`, payment hoặc kết quả gần nhất vào field. Instance có thể được dùng lại mà không mang dữ liệu request trước sang request sau. Context thuộc từng lần đánh giá; dependency cấu hình nếu có cần bất biến hoặc dùng cơ chế nhất quán rõ ràng.

Singleton policy có field `actor` được gán trước mỗi lần gọi là một thiết kế nguy hiểm: hai thread có thể làm lẫn actor/facts. Truyền context theo tham số giúp thấy ownership của dữ liệu.

Thời gian nên là một fact hoặc được cung cấp bằng `Clock` có thể kiểm soát. Tránh gọi giờ hệ thống rải rác trong từng rule khiến một lần đánh giá dùng nhiều mốc thời gian khác nhau. Trong fixture, server lấy mốc sau khi đã đọc/khóa facts cần thiết; request vào hàng đợi trước deadline không chứng minh lúc thực thi còn trong hạn.

### 8.2. Cache có thể giữ lại quyền đã hết hiệu lực

Cache quyết định theo `(actorId, paymentId)` bỏ sót tenant, action, amount, resource version, quyền bị thu hồi và thời hạn. TTL ngắn vẫn có thể cho phép dùng kết quả cũ trong khoảng TTL.

Với thao tác ghi nhạy cảm, cách dễ chứng minh nhất là đánh giá lại trên facts hợp lệ tại execution gate. Nếu phải cache vì chi phí, cần xác định dependency, version, invalidation và mức stale mà nghiệp vụ chấp nhận; không coi đây chỉ là tối ưu kỹ thuật.

Cache cấu hình policy bất biến khác với cache PERMITTED cho một actor/object. Policy version không đổi nhưng owner, authorities và phần tiền còn lại vẫn có thể đổi. Authority trong token/session cũng có thể là snapshot; yêu cầu thu hồi quyền tức thời cần nguồn quyền/giao thức phù hợp, không chỉ kiểm tra token còn hạn.

### 8.3. Version phục vụ truy vết

`refund-request/v1` giúp audit và test nhận biết logic đã dùng. Nó không chứng minh quyết định đã commit và không khiến facts cũ còn hiệu lực.

Với cấu hình động, một lần đánh giá nên dùng snapshot cấu hình/version nhất quán. Tránh đọc hạn mức version mới nhưng ghi audit version cũ. Khi rollout policy mới, cần định nghĩa nó áp dụng ra sao với ý định mới, request chờ duyệt và operation đã được chấp nhận.

Nếu một request cần nhiều subpolicy, audit phải đủ nhận biết tổ hợp logic thực sự được dùng, thay vì chỉ lưu nhãn không liên quan đến cấu hình đã đánh giá.

## 9. Anti-pattern cần nhận diện khi review

| Anti-pattern | Vì sao dễ bị lạm dụng | Cách tổ chức phù hợp hơn |
|---|---|---|
| `canDoAnything(user, object)` | Quyền bước này bị dùng cho bước khác | Tên policy theo action cụ thể |
| Facts như `isOwner`, `approved`, `remainingAmount` từ JSON | Caller tự chọn đầu vào để qua kiểm tra | Nạp facts authoritative; command chỉ chứa ý định được phép |
| `if (ADMIN) return permit` | Bỏ qua tenant, state, tiền và approval | Action quản trị có căn cứ quyền riêng |
| Policy tự query nhiều lần không rõ transaction | Dữ kiện khó kiểm soát thời điểm | Fact loader/context có hợp đồng nhất quán |
| `evaluate` giữ chỗ hoặc gọi provider | Gọi để xem quyền hoặc retry gây hiệu lực lặp | Policy thuần, handler ghi sau điểm cưỡng chế |
| Bắt mọi exception rồi PERMIT | Lỗi hoặc thiếu facts trở thành bỏ qua quyền | Dừng hiệu lực và báo lỗi có kiểm soát |
| Chỉ ẩn nút UI | Caller gọi thẳng endpoint vẫn tạo hiệu lực | Cưỡng chế tại service thực thi |
| Lưu quyết định trên session dùng lại | Quyền hoặc trạng thái đã đổi | Đánh giá lại ở gate phù hợp |
| Copy rule sang admin API và consumer | Các bản dễ thay đổi lệch nhau | Hợp đồng dùng chung hoặc policy action riêng rõ ràng |
| Log quyết định rồi bỏ qua `allowed()` | Không có enforcement thực sự | Đường deny dừng trước mutation và được test |

Không phải mọi I/O trong authorization đều sai; dịch vụ bên ngoài có thể là nguồn quyền authoritative. Điều cần tránh trong thiết kế thuần của bài là I/O và side effect bị giấu trong `evaluate` mà caller tưởng chỉ đang tính một kết quả cục bộ.

Tương tự, một aggregate vẫn nên bảo vệ invariant riêng của nó. Không xóa mọi guard domain sau khi có policy rồi để bất kỳ caller nào gọi chuyển trạng thái không hợp lệ.

## 10. Kiểm thử theo quyết định và hiệu lực nghiệp vụ

### 10.1. Ma trận unit test

Lấy fixture ở mục 5.3 làm baseline. Mỗi hàng chỉ thay dữ kiện được nêu, trừ trường hợp cố ý kết hợp nhiều lỗi:

| Thay đổi | Kết quả mong đợi |
|---|---|
| Không đổi, amount 400.000 | PERMITTED |
| Actor thuộc tenant khác | TENANT_MISMATCH |
| Actor khác customer, vẫn đủ authority | NOT_OWNER |
| Actor đúng customer nhưng thiếu authority | MISSING_PERMISSION |
| Command version 11, payment version 12 | VERSION_CONFLICT |
| Payment VOIDED | INVALID_STATE |
| Thời điểm đúng bằng deadline | WINDOW_CLOSED |
| Thời điểm sau deadline | WINDOW_CLOSED |
| Amount 0 hoặc âm | INVALID_AMOUNT |
| Amount đúng 700.000 | PERMITTED |
| Amount 700.001 | ABOVE_AVAILABLE |
| Reserved tăng lên 400.000, amount vẫn 400.000 | PERMITTED vì còn đúng 400.000 |
| Reserved tăng lên 500.000, amount vẫn 400.000 | ABOVE_AVAILABLE vì chỉ còn 300.000 |
| Captured/refunded/reserved mâu thuẫn | Không dựng được snapshot hợp lệ; không có hiệu lực |
| Thiếu context bắt buộc | Lỗi kỹ thuật; không tự chuyển thành PERMITTED |

Thử thêm trường hợp sai tenant đồng thời vượt amount. Với thứ tự rule hiện tại, kết quả là TENANT_MISMATCH; API không được làm lộ hạn mức của payment ngoài scope.

Unit test nên cung cấp thời gian cố định. Không dùng ngày hiện tại khiến test deadline tự đổi kết quả sau một thời gian chạy.

### 10.2. Thuộc tính có ích ngoài test theo ví dụ

- Cùng context và policy version cho cùng kết quả, không thay đổi facts.
- Với fixture chỉ cho owner tự tạo yêu cầu, khác tenant hoặc customer luôn không được phép bất kể amount.
- Giữ các facts khác hợp lệ, giảm phần tiền khả dụng không thể làm một amount đã vượt hạn mức trở nên hợp lệ.
- Giữ facts khác không đổi, bỏ authority bắt buộc không thể biến từ chối thành cho phép.
- Với policy deadline hiện tại, yêu cầu tại hoặc sau deadline không được phép; kiểm tra biên theo độ chính xác thời gian hệ thống dùng.

Thuộc tính phải theo policy cụ thể. Hệ thống có delegation cần thuộc tính tương ứng; không copy máy móc “khác owner luôn deny” của fixture này sang luồng nhân viên được ủy quyền.

### 10.3. Integration test cho phần policy không tự bảo đảm

Unit test không chứng minh handler đã gọi policy, transaction rollback đúng hoặc constraint thật hoạt động. Integration test cần quan sát dữ liệu sau commit/rollback:

1. Sai quyền không tạo request, không tăng reservation và không sinh outbox chấp nhận.
2. Happy path tạo đúng một request PENDING_APPROVAL, currency từ payment server và reservation đúng amount.
3. Lỗi sau reserve nhưng trước binding làm rollback toàn bộ thay đổi cục bộ liên quan.
4. Retry cùng scope/key/intent trả request cũ, không thêm reservation/event logic.
5. Cùng key nhưng khác amount/payment bị conflict; không dùng replay để truy cập đối tượng khác.
6. Hai transaction độc lập tranh phần tiền còn lại không làm refunded cộng reserved vượt captured.
7. API quản trị, job và consumer không đi tắt thiếu gate thích hợp.
8. Client gửi thêm `approved=true`, currency khác hoặc đích hoàn tiền mới không sửa dữ liệu server không cho phép.

Khóa từng payment không ngăn race cùng scope/key trên hai payment khác nhau. Cần uniqueness của binding và rollback transaction thua. Chống hai key khác nhau cho cùng nghĩa vụ hoàn tiền cần claim/return ID và ràng buộc nghiệp vụ riêng.

Concurrency test cần hai connection/transaction độc lập và lịch chạy điều khiển được bằng latch/barrier tại vị trí phù hợp. Mock snapshot chỉ kiểm tra phép tính của policy, không chứng minh database giữ đúng invariant.

Không coi response 403 là đủ bằng chứng. Nếu reservation vẫn commit hoặc outbox chấp nhận vẫn được relay, luồng đã vi phạm invariant. Đọc dữ liệu từ ranh giới độc lập sau khi transaction thực thi kết thúc để tránh nhầm dữ liệu trong bộ nhớ với dữ liệu đã commit.

## 11. Đưa pattern vào codebase đang có

### 11.1. Di chuyển theo một hành động cụ thể

Liệt kê các đường tạo cùng hiệu lực: API khách hàng, API hỗ trợ, job và consumer. Ghi rõ actor và nguồn dữ kiện của từng đường. Sau đó chọn một hành động có tên cụ thể thay vì gom cả vòng đời refund vào một class.

Viết bảng quyết định hiện tại và tình huống lạm dụng đã biết. Tách việc tải facts khỏi phần quyết định; chuyển điều kiện vào policy với đầu vào rõ ràng. Handler tiếp tục giữ transaction và điểm cưỡng chế trước mutation.

Đưa entry point liên quan qua đường thực thi được kiểm soát. Chỉ bỏ guard cũ sau khi hành vi thay thế được kiểm chứng; phải tìm được các caller vẫn ghi hiệu lực tương đương mà thiếu policy hoặc invariant phù hợp. Mục tiêu là thống nhất quy tắc, không chỉ chuyển các dòng `if` sang một file khác.

### 11.2. Theo dõi khác biệt và audit

Có thể tính policy mới ở chế độ quan sát để so với quyết định đang được cưỡng chế, nhưng policy quan sát phải không có side effect. Khi có khác biệt, điều tra actor, action, facts/version và reason; không tự chọn kết quả dễ cho phép hơn.

Audit nên liên kết actor, tenant, resource, action, intent/request ID, resource version, policy version và outcome. Mã nội bộ hỗ trợ chẩn đoán; response client vẫn tuân theo chính sách tiết lộ dữ liệu. Không log credentials, token hoặc toàn bộ dữ liệu thanh toán để tiện debug.

Quyết định PERMITTED được tính trước commit khác với một request đã commit. Audit chấp nhận lưu cùng transaction không tồn tại nếu transaction rollback; log trước commit cần ghi rõ giai đoạn. Nếu cần giữ audit từ chối sau rollback, dùng cơ chế riêng được thiết kế cho việc đó và không tạo hiệu lực nghiệp vụ.

### 11.3. Tránh policy biết quá nhiều

Nếu `BusinessPolicy` biết mọi entity, repository, transaction manager và provider, sự tập trung đã trở thành ghép chặt. Tách theo action/domain, chia sẻ rule có ý nghĩa thật sự và giữ context đủ nhỏ để thấy các dependency.

Không cần một class cho từng biểu thức một dòng nếu chúng không có vòng đời độc lập. Một policy có vài guard rõ ràng thường dễ kiểm chứng hơn chuỗi combinator không nhìn thấy toán tử, thứ tự và semantics khi thiếu dữ kiện.

## 12. Bài tập áp dụng và tiêu chí tự kiểm tra

### 12.1. Thêm nhân viên được ủy quyền mà không mở toàn tenant

Thiết kế policy cho nhân viên tạo yêu cầu thay khách. Facts có assignment/delegation được server xác minh theo payment/case, action và thời hạn.

Mục tiêu là cho phép đúng quan hệ được ủy quyền nhưng vẫn bắt buộc tenant, authority, state, thời hạn và phần tiền còn lại. Thêm test nhân viên có cùng role nhưng không được giao case, delegation hết hạn và amount vượt phần tiền khả dụng. Không thay policy khách hàng bằng `owner OR staff` nếu STAFF chỉ là role rộng.

### 12.2. Tìm lỗi trong policy có side effect

```text
canRequestRefund(context):
    if amount <= payment.available:
        payment.reserve(amount)
        return true
    return false
```

Phân tích hậu quả khi UI gọi để hiển thị, service gọi lại để thực thi hoặc request được retry. Tách quyết định khỏi reserve; đặt reserve sau điểm cưỡng chế trong transaction, kèm concurrency và idempotency.

Sau đó bổ sung policy vòng đời reservation: yêu cầu bị từ chối/hủy cần giải phóng giữ chỗ đúng một lần. Đối với thanh toán ngoài hệ thống có kết quả chưa rõ, không giải phóng chỉ vì timeout mà chưa đối soát. Đây là các quy tắc riêng của bước xử lý sau, không phải side effect được giấu vào policy xem quyền.

### 12.3. Xác định ranh giới của PERMITTED

Với mỗi policy mới, trả lời rõ:

- Nó cho phép action nào, và action nào vẫn cần gate khác?
- Actor, quan hệ đối tượng, tiền, trạng thái và thời gian lấy từ đâu?
- Kết quả chỉ đúng cho snapshot nào; race được xử lý ở đâu?
- Caller nào cưỡng chế, và còn đường ghi nào bỏ qua caller đó không?
- Thiếu dữ kiện hoặc không có policy phù hợp dẫn đến hành vi gì?
- Replay khác tạo ý định mới ở bước nào?
- Reason nào được công bố cho client, dữ kiện nào chỉ lưu nội bộ?
- Test nào chứng minh từ chối không để lại thay đổi nghiệp vụ đã commit?

Một policy object tốt khiến quyết định cho một hành động có thể đọc, giải thích và kiểm thử độc lập. An toàn của toàn luồng đến từ đúng facts, điểm cưỡng chế tại nơi thực thi, state machine, transaction, concurrency và định danh nghĩa vụ chống trùng.
