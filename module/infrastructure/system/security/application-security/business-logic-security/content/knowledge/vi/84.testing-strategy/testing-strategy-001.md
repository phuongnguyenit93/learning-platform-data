# Business rule unit tests

## 1. Unit test bảo vệ quy tắc nghiệp vụ nào?

Unit test cho quy tắc nghiệp vụ kiểm tra rằng một quyết định hoặc một chuyển trạng thái chỉ xảy ra khi các điều kiện của nghiệp vụ được đáp ứng. Trong bảo mật logic nghiệp vụ, những điều kiện này thường liên quan đến quyền trên đối tượng, số tiền, thứ tự xử lý, thẩm quyền phê duyệt và danh tính của một lệnh có thể được gửi lại.

Ví dụ, hàm hoàn tiền trả về một đối tượng `Refund` chưa đủ để kết luận rằng hành vi đúng. Cần kiểm tra người gọi có quyền với payment đó, yêu cầu đã được duyệt cho đúng revision, số tiền còn được phép hoàn và hành động không tái sử dụng một lệnh đã kết thúc.

Bài học thuộc chương **Testing Strategy** của module **Bảo mật logic nghiệp vụ** (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Trọng tâm là thiết kế unit test để phát hiện hành vi bỏ qua phê duyệt, sửa giá hoặc số tiền, thao tác sai quyền và xử lý lệnh trùng. Các ví dụ kết nối business invariants, state machine, quyền theo đối tượng, transaction và idempotency, đồng thời phân biệt điều gì có thể chứng minh ở cấp unit với điều gì phải kiểm tra ở cấp tích hợp.

Sau bài học, người đọc có thể:

- Chuyển mô tả nghiệp vụ thành tiền điều kiện, hành động và kết quả có thể kiểm tra.
- Chọn ca hợp lệ, ca bị từ chối, biên và tổ hợp có khả năng bị lạm dụng.
- Viết unit test Java có đầu vào xác định và kết quả độc lập với cách triển khai.
- Dùng test double đúng chỗ, tránh mock chính quy tắc cần bảo vệ.
- Nhận ra giới hạn của unit test với dữ liệu cũ, transaction, cạnh tranh và tác dụng phụ bên ngoài.

## 2. Xác định đơn vị kiểm thử và ranh giới bằng chứng

Một unit không bắt buộc là một phương thức hoặc một lớp. Nó có thể là một policy, một domain aggregate hoặc một nhóm đối tượng nhỏ cùng thực hiện một hành vi nghiệp vụ. Điều quan trọng là có thể kiểm tra hành vi đó độc lập với cơ sở dữ liệu, mạng, đồng hồ thực và các dịch vụ bên ngoài.

### 2.1. Ba loại hành vi thường cần kiểm tra

| Loại hành vi | Ví dụ | Unit test nên quan sát |
| --- | --- | --- |
| Quyết định thuần | Có cho phép thực thi refund với các facts hiện tại không? | Quyết định, mã lý do và không thay đổi đầu vào. |
| Chuyển trạng thái miền | Yêu cầu từ `APPROVED` chuyển sang chờ thực thi. | Trạng thái mới, revision, dữ kiện và domain event được tạo. |
| Điều phối ứng dụng | Lấy dữ liệu, đánh giá policy, lưu lệnh hoặc trả kết quả cũ. | Kết quả trả về và các tương tác có ý nghĩa nghiệp vụ với collaborator. |

Một policy thuần nhận dữ liệu đầu vào và trả quyết định là điểm bắt đầu tốt. Không cần mock Spring, HTTP hoặc database để kiểm tra phép so sánh hạn mức. Tuy nhiên, policy thuần chỉ quyết định trên một snapshot. Nó không chứng minh rằng snapshot còn đúng tại lúc transaction commit.

### 2.2. Điều unit test không tự chứng minh

| Câu hỏi | Unit test có thể kiểm tra | Bằng chứng bổ sung cần có |
| --- | --- | --- |
| Số tiền yêu cầu có vượt phần còn lại không? | Công thức và các nhánh so sánh trên dữ liệu cho trước. | Kiểm thử cạnh tranh để bảo vệ tổng tiền khi nhiều lệnh cùng chạy. |
| Chỉ cho thực thi sau phê duyệt? | Policy và state machine từ chối trạng thái sai. | Kiểm thử tích hợp các endpoint, job và đường ghi dữ liệu có dùng cơ chế đó. |
| Cùng lệnh không xử lý hai lần? | Quyết định với bản ghi idempotency đã tồn tại. | Unique constraint, nhận quyền xử lý nguyên tử, retry và phục hồi sau crash. |
| Bị từ chối có gọi đối tác không? | Service không gọi port gửi lệnh trong nhánh bị từ chối. | Kiểm thử tích hợp để kiểm tra wiring và hiệu ứng thật. |
| Transaction rollback có trả lại phần giữ không? | Service xử lý tín hiệu lỗi theo hợp đồng. | Kiểm thử với cơ sở dữ liệu thực và ranh giới transaction thực. |

Hai lời gọi chạy tuần tự trong một unit test không phải bằng chứng chống race condition. Một repository giả lưu dữ liệu trong `Map` cũng không thay thế được hành vi khóa, isolation hoặc constraint của database.

## 3. Chuyển quy tắc thành hợp đồng kiểm thử

### 3.1. Viết rõ điều phải giữ

Ví dụ với luồng hoàn tiền:

```text
R1 — Quyền thực thi:
  Người gọi có quyền thực thi trên yêu cầu thuộc tenant của mình.
  Yêu cầu phải liên kết với đúng payment trong cùng tenant.

R2 — Phê duyệt:
  Yêu cầu ở trạng thái APPROVED.
  Quyết định duyệt thuộc đúng yêu cầu và đúng revision.
  Người duyệt khác người tạo; quyết định còn hiệu lực.
  Số tiền không vượt mức được quyết định duyệt cho phép.

R3 — Giới hạn hoàn tiền:
  amount > 0; currency khớp payment.
  captured >= 0; refunded >= 0; reserved >= 0.
  refunded + reserved <= captured.
  amount <= captured - refunded - reserved.

R4 — Lệnh trùng:
  Một danh tính lệnh nghiệp vụ không tạo thêm hiệu ứng trái phép khi retry.
  Cùng khóa idempotency nhưng payload khác phải được xử lý như xung đột.
```

`captured` là tiền đã thu thành công, `refunded` là tiền đã hoàn thành công, còn `reserved` là tiền đang giữ cho các refund chưa kết thúc. Khi một refund thành công, số tiền tương ứng chuyển từ phần giữ sang phần đã hoàn; không được cộng vào cả hai phần sau khi chuyển đổi hoàn tất.

Các quy tắc này là hợp đồng của ví dụ. Nếu nghiệp vụ thực tế cho phép người tạo tự duyệt trong một phạm vi nhỏ hoặc có cách tính phí riêng, cần mô tả ngoại lệ và kiểm thử nó một cách tường minh. Unit test không nên tự phát minh một chính sách mà chủ nghiệp vụ chưa xác nhận.

### 3.2. Lập bảng quyết định trước khi viết assertion

| Mã | Thay đổi so với bộ dữ liệu hợp lệ | Kết quả mong đợi |
| --- | --- | --- |
| `UT-01` | Không thay đổi gì, số tiền đúng bằng phần còn lại. | Cho phép đánh giá thực thi. |
| `UT-02` | Người gọi thuộc tenant khác. | Từ chối quyền. |
| `UT-03` | Request trỏ tới payment khác. | Từ chối quan hệ đối tượng không hợp lệ. |
| `UT-04` | Request còn `DRAFT` hoặc `SUBMITTED`. | Từ chối do trạng thái. |
| `UT-05` | Không có quyết định duyệt. | Từ chối thiếu phê duyệt. |
| `UT-06` | Số tiền đã sửa, revision mới khác revision được duyệt. | Từ chối phê duyệt cũ. |
| `UT-07` | Người duyệt chính là người tạo. | Từ chối tự duyệt theo quy tắc ví dụ. |
| `UT-08` | Thời điểm hiện tại đúng bằng thời điểm hết hạn. | Từ chối theo khoảng hiệu lực đã định. |
| `UT-09` | Số tiền bằng 0 hoặc âm. | Từ chối số tiền không hợp lệ. |
| `UT-10` | Số tiền vượt phần còn lại một đơn vị nhỏ nhất. | Từ chối vượt hạn mức. |
| `UT-11` | Currency không khớp. | Không thực hiện phép so sánh như cùng một loại tiền. |
| `UT-12` | Dữ liệu số dư đã mâu thuẫn. | Không tiếp tục cho phép chuyển dịch giá trị. |
| `UT-13` | Số tiền vượt giới hạn của quyết định duyệt. | Từ chối dù payment vẫn còn đủ tiền. |

Đa số test nên bắt đầu từ một bộ dữ liệu hợp lệ rồi thay đúng một yếu tố. Cách này làm rõ lý do bị từ chối. Sau đó bổ sung một số tổ hợp có ý nghĩa, như phê duyệt cũ kèm số tiền tăng, hoặc quyền bị thu hồi trước lần retry.

Nếu mọi ca đều có cả tenant sai lẫn trạng thái sai, bộ test có thể vẫn xanh khi xóa hoàn toàn kiểm tra trạng thái: kiểm tra tenant đã chặn tất cả trước đó.

## 4. Tách policy khỏi hạ tầng để dễ kiểm thử

Ví dụ dưới đây dùng cú pháp Java 17 và JUnit Jupiter ở phần test, không phụ thuộc vào Spring. Policy trả một quyết định trên các facts do máy chủ cung cấp. Các đoạn mã minh họa không bao gồm cấu hình dependency hoặc toàn bộ luồng thực thi hoàn tiền.

Giả định của mô hình:

- ID và currency không null, đã được chuẩn hóa khi tạo facts. Bản đầy đủ cần kiểm tra các tiền điều kiện đó tại ranh giới phù hợp.
- `Approval` đến từ kho quyết định duyệt đáng tin cậy, không phải trường do client tự gửi. Thẩm quyền của người duyệt được kiểm tra khi quyết định được tạo và theo chính sách hiệu lực mà hệ thống lựa chọn.
- `mayExecuteRefund` là kết quả quyền thô; policy còn kiểm tra tenant và liên kết đối tượng. Hệ thống thực tế có thể cần thêm quyền theo đơn vị, nhóm hoặc từng payment.
- Tiền dùng số nguyên theo đơn vị nhỏ nhất đã quy định cho currency. Trong fixture VND, một đơn vị biểu diễn một đồng.
- Quyết định có hiệu lực trong khoảng trước `expiresAt`; tại đúng `expiresAt` thì hết hạn.

```java
import java.time.Instant;
import java.util.Objects;

public final class RefundPolicy {
    public enum State {
        DRAFT, SUBMITTED, APPROVED, EXECUTION_PENDING, SUCCEEDED, FAILED
    }

    public enum Decision {
        ALLOW,
        FORBIDDEN,
        INVALID_RELATION,
        INVALID_STATE,
        APPROVAL_REQUIRED,
        APPROVAL_STALE,
        SELF_APPROVAL,
        APPROVAL_EXPIRED,
        APPROVAL_LIMIT_EXCEEDED,
        INVALID_AMOUNT,
        CURRENCY_MISMATCH,
        INVALID_BALANCE,
        INSUFFICIENT_REMAINING
    }

    public record Actor(
            String userId, String tenantId, boolean mayExecuteRefund) {}

    public record Request(
            String id, String paymentId, String tenantId, String createdBy,
            long revision, State state, String currency, long amountMinor) {}

    public record Approval(
            String requestId, long approvedRevision, String approvedBy,
            long maxAmountMinor, Instant expiresAt) {}

    public record Balance(
            String paymentId, String tenantId, String currency,
            long capturedMinor, long refundedMinor, long reservedMinor) {}

    public Decision evaluate(
            Actor actor, Request request, Balance balance,
            Approval approval, Instant now) {
        Objects.requireNonNull(actor);
        Objects.requireNonNull(request);
        Objects.requireNonNull(balance);
        Objects.requireNonNull(now);

        if (!actor.mayExecuteRefund()
                || !actor.tenantId().equals(request.tenantId())) {
            return Decision.FORBIDDEN;
        }
        if (!request.paymentId().equals(balance.paymentId())
                || !request.tenantId().equals(balance.tenantId())) {
            return Decision.INVALID_RELATION;
        }
        if (request.state() != State.APPROVED) {
            return Decision.INVALID_STATE;
        }
        if (approval == null || !request.id().equals(approval.requestId())) {
            return Decision.APPROVAL_REQUIRED;
        }
        if (request.revision() != approval.approvedRevision()) {
            return Decision.APPROVAL_STALE;
        }
        if (request.createdBy().equals(approval.approvedBy())) {
            return Decision.SELF_APPROVAL;
        }
        if (!now.isBefore(approval.expiresAt())) {
            return Decision.APPROVAL_EXPIRED;
        }
        if (request.amountMinor() <= 0) {
            return Decision.INVALID_AMOUNT;
        }
        if (!request.currency().equals(balance.currency())) {
            return Decision.CURRENCY_MISMATCH;
        }
        if (request.amountMinor() > approval.maxAmountMinor()) {
            return Decision.APPROVAL_LIMIT_EXCEEDED;
        }

        long captured = balance.capturedMinor();
        long refunded = balance.refundedMinor();
        long reserved = balance.reservedMinor();
        if (captured < 0 || refunded < 0 || reserved < 0
                || refunded > captured || reserved > captured - refunded) {
            return Decision.INVALID_BALANCE;
        }
        long remaining = captured - refunded - reserved;
        return request.amountMinor() <= remaining
                ? Decision.ALLOW
                : Decision.INSUFFICIENT_REMAINING;
    }
}
```

Việc kiểm tra `reserved > captured - refunded` được thực hiện sau khi biết các số không âm và `refunded <= captured`. Nhờ đó, phép trừ dùng để tính phần còn lại không cần cộng hai số lớn có thể làm tràn `long`. Thứ tự toán hạng với `||` trong Java cũng giúp không tính các biểu thức phía sau khi một điều kiện trước đã đúng.

`ALLOW` chỉ có nghĩa các facts được truyền vào thỏa policy. Nó không phải một giấy phép có thể tái sử dụng vô thời hạn. Lớp thực thi vẫn phải giữ invariant khi cập nhật dữ liệu bằng transaction, khóa, cập nhật có điều kiện hoặc cơ chế đồng thời tương đương.

Các mã lý do ở đây là hợp đồng nội bộ phục vụ domain và test. Lớp API có thể cần ánh xạ chúng thành lỗi tổng quát hơn để tránh tiết lộ dữ liệu ngoài quyền truy cập. Một unit test của policy không mặc nhiên quy định mã HTTP.

## 5. Viết unit test có đầu vào xác định

### 5.1. Fixture hợp lệ và thời gian cố định

Fixture là tập dữ liệu chuẩn bị cho test. Nên dùng một fixture nhỏ, dễ đọc, thỏa mọi tiền điều kiện, sau đó thay yếu tố cần kiểm tra. Không nên có hàng chục giá trị mặc định bị giấu trong một builder khiến người đọc không biết vì sao test được phép thực hiện.

Ví dụ dưới đây đặt `RefundPolicy` và test trong cùng package. Các phương thức `request` và `approval` tạo facts, không gọi lại policy để suy ra expected result.

```java
import java.time.Instant;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RefundPolicyTest {
    private static final Instant NOW =
            Instant.parse("2030-01-01T00:00:00Z");

    private final RefundPolicy policy = new RefundPolicy();

    private static RefundPolicy.Actor actor() {
        return new RefundPolicy.Actor("operator-1", "tenant-a", true);
    }

    private static RefundPolicy.Request request(long amount, long revision) {
        return new RefundPolicy.Request(
                "refund-request-1", "payment-1", "tenant-a", "maker-1",
                revision, RefundPolicy.State.APPROVED, "VND", amount);
    }

    private static RefundPolicy.Approval approval(
            long revision, String approver, Instant expiresAt) {
        return new RefundPolicy.Approval(
                "refund-request-1", revision, approver, 100_000L, expiresAt);
    }

    private static RefundPolicy.Approval validApproval() {
        return approval(3L, "manager-1", NOW.plusSeconds(60));
    }

    private static RefundPolicy.Balance balance() {
        return new RefundPolicy.Balance(
                "payment-1", "tenant-a", "VND",
                100_000L, 20_000L, 30_000L);
    }

    static Stream<Arguments> amountCases() {
        return Stream.of(
                Arguments.of(-1L, RefundPolicy.Decision.INVALID_AMOUNT),
                Arguments.of(0L, RefundPolicy.Decision.INVALID_AMOUNT),
                Arguments.of(1L, RefundPolicy.Decision.ALLOW),
                Arguments.of(49_999L, RefundPolicy.Decision.ALLOW),
                Arguments.of(50_000L, RefundPolicy.Decision.ALLOW),
                Arguments.of(50_001L,
                        RefundPolicy.Decision.INSUFFICIENT_REMAINING));
    }

    @ParameterizedTest(name = "amount={0}, expected={1}")
    @MethodSource("amountCases")
    void evaluatesAmountAgainstRemaining(
            long amount, RefundPolicy.Decision expected) {
        var actual = policy.evaluate(
                actor(), request(amount, 3L), balance(), validApproval(), NOW);

        assertEquals(expected, actual);
    }

    @Test
    void rejectsExecutionByActorFromAnotherTenant() {
        var outsider = new RefundPolicy.Actor("operator-2", "tenant-b", true);

        var actual = policy.evaluate(
                outsider, request(10_000L, 3L), balance(), validApproval(), NOW);

        assertEquals(RefundPolicy.Decision.FORBIDDEN, actual);
    }

    @Test
    void rejectsChangedRevisionAfterApproval() {
        var changedRequest = request(10_000L, 4L);

        var actual = policy.evaluate(
                actor(), changedRequest, balance(), validApproval(), NOW);

        assertEquals(RefundPolicy.Decision.APPROVAL_STALE, actual);
    }

    @Test
    void rejectsApprovalByRequestCreator() {
        var selfApproval = approval(3L, "maker-1", NOW.plusSeconds(60));

        var actual = policy.evaluate(
                actor(), request(10_000L, 3L), balance(), selfApproval, NOW);

        assertEquals(RefundPolicy.Decision.SELF_APPROVAL, actual);
    }

    @Test
    void rejectsMissingApproval() {
        var actual = policy.evaluate(
                actor(), request(10_000L, 3L), balance(), null, NOW);

        assertEquals(RefundPolicy.Decision.APPROVAL_REQUIRED, actual);
    }

    @Test
    void approvalExpiresAtTheExactDeadline() {
        var expiresNow = approval(3L, "manager-1", NOW);

        var actual = policy.evaluate(
                actor(), request(10_000L, 3L), balance(), expiresNow, NOW);

        assertEquals(RefundPolicy.Decision.APPROVAL_EXPIRED, actual);
    }

    @Test
    void rejectsNonApprovedStateEvenWithAnApprovalRecord() {
        var draft = new RefundPolicy.Request(
                "refund-request-1", "payment-1", "tenant-a", "maker-1",
                3L, RefundPolicy.State.DRAFT, "VND", 10_000L);

        var actual = policy.evaluate(
                actor(), draft, balance(), validApproval(), NOW);

        assertEquals(RefundPolicy.Decision.INVALID_STATE, actual);
    }

    @Test
    void doesNotCreateRemainingValueNearLongLimit() {
        var fullyAllocated = new RefundPolicy.Balance(
                "payment-1", "tenant-a", "VND",
                Long.MAX_VALUE, Long.MAX_VALUE - 10L, 10L);

        var actual = policy.evaluate(
                actor(), request(1L, 3L), fullyAllocated, validApproval(), NOW);

        assertEquals(RefundPolicy.Decision.INSUFFICIENT_REMAINING, actual);
    }

    @Test
    void inconsistentBalanceNeverProducesAllow() {
        var inconsistent = new RefundPolicy.Balance(
                "payment-1", "tenant-a", "VND", 100L, 80L, 30L);

        var actual = policy.evaluate(
                actor(), request(1L, 3L), inconsistent, validApproval(), NOW);

        assertEquals(RefundPolicy.Decision.INVALID_BALANCE, actual);
    }
}
```

Ở test về revision, số tiền được giữ nguyên 10.000 VND và chỉ revision thay đổi. Nhờ đó, test không bị một kiểm tra số tiền khác chặn trước và che mất lỗi. Có thể bổ sung ca tấn công thực tế tăng số tiền sau duyệt, nhưng không dùng duy nhất ca có nhiều điều kiện sai để đại diện cho toàn bộ một quy tắc.

Ví dụ chưa liệt kê mọi ca trong bảng quyết định. Cần bổ sung các nhánh còn thiếu khi áp dụng, như payment sai quan hệ, quyền thực thi bị tắt, currency khác và giới hạn của người duyệt. Việc tách bảng quy tắc khỏi ví dụ giúp nhận diện phần chưa được kiểm thử thay vì xem một đoạn mã mẫu là bộ test đầy đủ.

### 5.2. Không dùng thời gian thực trong assertion

Không kiểm tra hạn duyệt bằng cách gọi `Instant.now()` nhiều lần rồi dùng `sleep` để chờ hết hạn. Test đó chậm, phụ thuộc lịch chạy và dễ không ổn định. Policy trên nhận `Instant now`, vì vậy có thể kiểm tra ba điểm: ngay trước hạn, đúng hạn và ngay sau hạn.

Nếu service tự lấy giờ, có thể tiêm `Clock` và dùng `Clock.fixed(...)` trong unit test. Múi giờ, ngày nghiệp vụ và thời điểm hết hạn vẫn phải có hợp đồng rõ ràng. Việc dùng UTC không tự quyết định một hạn mức “mỗi ngày” được tính theo ngày của tenant nào.

## 6. Chọn ca biên có khả năng bắt lỗi bảo mật

Biên là nơi các phép so sánh sai thường làm thay đổi quyền hoặc giá trị. Không chỉ thử một số tiền nhỏ hợp lệ và một số tiền rất lớn bị từ chối.

### 6.1. Số tiền, giá và currency

| Nhóm dữ liệu | Ca nên có | Lỗi có thể phát hiện |
| --- | --- | --- |
| Số tiền yêu cầu | Âm, 0, 1, đúng hạn mức, vượt một đơn vị. | Sai dấu, sai `<` với `<=`, bỏ kiểm tra số dương. |
| Phần đã sử dụng | Không dùng, dùng hết, giữ hết, dữ liệu tổng vượt giá trị đã thu. | Bỏ quên phần giữ hoặc chấp nhận số dư mâu thuẫn. |
| Số lớn | Gần giới hạn biểu diễn, kết hợp các số lớn vẫn hợp lệ. | Tràn số khi cộng, nhân hoặc đổi đơn vị. |
| Currency | Cùng currency, khác currency, currency không được hỗ trợ tại ranh giới nhập. | So sánh hoặc chuyển dịch hai loại tiền như cùng đơn vị. |
| Số thập phân | Scale hợp lệ, quá nhiều chữ số lẻ, làm tròn theo quy tắc. | Giá trị bị làm tròn xuống ngoài ý muốn hoặc chuyển đổi mất chính xác. |
| Dữ liệu tính giá | Giá máy chủ và giá client khác nhau; coupon hết hạn hoặc không đủ điều kiện. | Tin giá do client gửi, áp dụng ưu đãi sai phạm vi. |

Nếu miền dùng `BigDecimal`, tránh tạo tiền bằng `new BigDecimal(0.1)` từ số thực nhị phân. Test cần thể hiện cách tạo số thập phân chính xác và cách so sánh nghiệp vụ. `BigDecimal.equals` xét cả scale, còn `compareTo` so sánh giá trị số; lựa chọn assertion phải phù hợp hợp đồng về scale thay vì sửa test cho qua.

Không đặt expected result bằng cách gọi lại đúng hàm tính tiền mà mã đang kiểm thử sử dụng. Nếu cả hai dùng cùng công thức sai, test có thể xanh. Với ca ví dụ, tính expected thủ công từ đặc tả hoặc sử dụng một mô hình tham chiếu độc lập, nhỏ và dễ kiểm tra.

### 6.2. Quyền theo đối tượng

Quyền không chỉ là một boolean role. Nên kiểm tra các trục độc lập:

- Người đúng tenant nhưng không có quyền hành động.
- Người có quyền hành động nhưng khác tenant.
- Người có quyền trong tenant nhưng không được xử lý đối tượng cụ thể.
- Đối tượng con không thuộc đối tượng cha trong request.
- Tài khoản dịch vụ được phép làm một loại lệnh nhưng không được tự tạo quyết định duyệt.
- Người gọi có quyền đọc đối tượng nhưng không được sửa trường giá trị hoặc người nhận.

Mô hình `RefundPolicy` tối giản mới có một phần các trục này. Khi chính sách có quan hệ chủ sở hữu hoặc phạm vi đơn vị, hãy mở rộng facts và test tương ứng. Không lấy test `tenant-a` khác `tenant-b` để kết luận đã kiểm tra quyền theo đối tượng trong cùng tenant.

### 6.3. Phê duyệt và revision

Nên có ca ngay dưới, đúng bằng và vượt ngưỡng thẩm quyền; quyết định cho request khác; revision cũ; quyết định hết hạn; người tạo tự duyệt và quyết định không tồn tại. Nếu sửa người nhận hoặc giá cũng làm mất hiệu lực duyệt, test phải thể hiện rằng các thay đổi đó tăng revision hoặc thay fingerprint theo hợp đồng.

Quy tắc so sánh revision trong policy không chứng minh mọi đường sửa dữ liệu đều tăng revision. Điều đó cần unit test ở hành vi sửa aggregate và kiểm thử tích hợp các đường ghi dữ liệu. Ví dụ: `changeAmount` hoặc từ chối thay đổi sau duyệt, hoặc chuyển về trạng thái cần duyệt lại; không để dữ liệu đã thay đổi mà revision cũ vẫn còn hiệu lực.

## 7. Unit test cho state machine và invariant của aggregate

Policy trả quyết định và aggregate thay đổi trạng thái là hai hành vi có liên quan nhưng khác nhau. Một thiết kế có thể gộp chúng, hoặc aggregate gọi policy trước khi chuyển trạng thái. Dù tổ chức theo cách nào, bộ test phải kiểm tra được cả điều kiện chuyển và trạng thái sau chuyển.

### 7.1. Kiểm tra chuyển hợp lệ và chuyển bị cấm

| Trạng thái ban đầu | Hành động | Điều cần assert |
| --- | --- | --- |
| `DRAFT` | Gửi yêu cầu | Trạng thái thành `SUBMITTED`; giữ đúng dữ liệu đã gửi. |
| `DRAFT` | Thực thi | Bị từ chối; không có event thực thi hay dữ liệu mới. |
| `SUBMITTED` | Duyệt bởi người đủ quyền | Lưu quyết định cho đúng revision và sang `APPROVED`. |
| `APPROVED` | Sửa trường làm thay đổi giá trị | Bị cấm hoặc làm mất hiệu lực duyệt theo hợp đồng. |
| `APPROVED` | Thực thi hợp lệ | Sang `EXECUTION_PENDING`, tạo một ý định xử lý có danh tính. |
| `EXECUTION_PENDING` | Thực thi lại cùng lệnh | Không tạo thêm ý định tương đương ngoài hợp đồng. |
| `SUCCEEDED` | Đánh dấu thành công lần nữa | Không cộng tiền hoặc phát event hoàn tất lần hai. |
| `SUCCEEDED` | Nhận trạng thái chờ cũ | Không làm lùi trạng thái kết thúc. |

Không nhất thiết có đủ các trạng thái này trong mọi hệ thống. Bảng test phải được sinh từ state machine của sản phẩm, bao gồm cả những chuyển trạng thái bị cấm. Nếu chỉ kiểm tra đường `DRAFT → SUBMITTED → APPROVED → EXECUTION_PENDING`, thao tác gọi thẳng từ `DRAFT` sang thực thi có thể vẫn lọt qua.

### 7.2. Kết quả bị từ chối phải giữ nguyên trạng thái

Một assertion về exception chưa đủ nếu phương thức đã sửa dữ liệu trước khi ném lỗi. Với aggregate có thể thay đổi, cần chụp snapshot bất biến trước hành động và so sánh sau hành động, hoặc assert rõ các trường và event có ý nghĩa.

```text
Given:
  Request ở SUBMITTED, revision 3, chưa có quyết định duyệt.
  Chụp snapshot gồm state, amount, revision, approval và pending events.

When:
  Gọi hành vi execute trên aggregate bằng người có quyền thực thi.

Then:
  Hành vi bị từ chối vì chưa được duyệt.
  State vẫn là SUBMITTED; amount và revision không đổi.
  Không thêm event hoặc command yêu cầu gửi tiền.
```

Nếu `before` và `after` cùng trỏ tới một đối tượng mutable, phép so sánh có thể không phát hiện thay đổi. Snapshot cần là bản sao giá trị hoặc một cấu trúc bất biến. Ngoài ra, phân biệt event đã có từ hành động trước với event mới tạo; kiểm tra số lượng tăng thêm hoặc danh tính event thay vì chỉ nhìn tổng danh sách.

### 7.3. Kiểm tra chuỗi hành động

Một số lỗi xuất hiện qua chuỗi thao tác hợp lệ riêng lẻ. Ví dụ: tạo yêu cầu, gửi, duyệt, sửa người nhận rồi thực thi. Unit test có thể chạy cả chuỗi trên aggregate và kiểm tra tại từng bước. Đây vẫn là unit test nếu mọi hành vi nằm trong đơn vị miền và không cần hạ tầng bên ngoài.

Không dùng thao tác sửa trực tiếp trường private để tạo chuỗi rồi cho rằng đã kiểm tra API miền. Khi mục tiêu là quy tắc “sửa số tiền làm mất hiệu lực duyệt”, hãy gọi chính hành vi sửa số tiền. Có thể dùng factory chuyên dụng để tạo trạng thái đầu cho test một quy tắc khác, nhưng fixture phải nhất quán và không che những tiền điều kiện đang cần kiểm tra.

## 8. Unit test điều phối: từ chối phải ngăn tác dụng phụ

Một service có thể gọi policy đúng nhưng bỏ qua kết quả, hoặc gửi lệnh ra ngoài trước khi kiểm tra quyền. Vì vậy, bên cạnh test policy, cần một số test điều phối có mục đích rõ ràng.

### 8.1. Giữ quy tắc thật, thay hạ tầng bằng test double

- Dùng policy thật khi muốn chứng minh service tôn trọng quyết định nghiệp vụ trên dữ liệu cụ thể.
- Stub nguồn đọc dữ liệu, danh tính và đồng hồ để tạo tình huống cần kiểm tra.
- Dùng fake hoặc mock cho port ghi lệnh, lưu thay đổi và gửi tác vụ, nhằm quan sát hiệu ứng có ý nghĩa.
- Chỉ stub policy khi chủ đích là kiểm tra service xử lý các loại quyết định, và đã có test riêng cho policy thật.

Phân biệt các test double giúp tránh nhầm bằng chứng:

| Loại | Công dụng | Không nên suy ra |
| --- | --- | --- |
| Stub | Cung cấp dữ liệu đầu vào xác định, như số dư hoặc quyết định đã lưu. | Dữ liệu đó sẽ luôn mới trong môi trường thật. |
| Fake | Mô phỏng hành vi đơn giản, như kho lệnh in-memory có thể tra cứu. | Fake có cùng semantics transaction và cạnh tranh với database. |
| Mock hoặc spy | Quan sát tương tác, như không phát lệnh khi bị từ chối. | Một lời gọi vào port đồng nghĩa giao dịch bên ngoài đã xảy ra đúng một lần. |

Ví dụ kế hoạch unit test điều phối:

```text
Tên: reject_stale_approval_without_creating_refund_command

Arrange:
  Repository stub trả request revision 4 và approval cho revision 3.
  Actor hợp lệ, amount và balance đều hợp lệ.
  Dùng RefundPolicy thật.
  Command store là test double ghi nhận các lần ghi.

Act:
  Gọi service.executeRefund(...).

Assert:
  Nhận kết quả bị từ chối vì approval stale theo hợp đồng service.
  Không có refund command mới, không có outbox event yêu cầu thực thi.
  Không gọi port chuyển tiền nếu service có port đó.
  Không thay đổi dữ liệu nghiệp vụ; audit về lần thử bị từ chối vẫn được phép.
```

Đây là giả mã mô tả test; tên repository và port phụ thuộc kiến trúc cụ thể. Nếu thiết kế chỉ cho worker gửi tiền, service tiếp nhận lệnh cần được kiểm tra rằng không tạo outbox command trong nhánh bị từ chối. Kiểm tra một `paymentGateway` mà service vốn không sử dụng sẽ không phát hiện được lỗi ở đường ghi lệnh thực tế.

### 8.2. Assert hành vi quan trọng, tránh khóa chặt chi tiết nội bộ

Những assertion có giá trị thường là: không tạo lệnh khi không có quyền, giữ đúng số tiền đã được duyệt, liên kết đúng payment, trả lại command cũ khi retry và không tạo event lần hai.

Những assertion dễ gây giòn thường là: repository đọc đúng hai lần, getter được gọi theo thứ tự cụ thể hoặc mọi method helper đều phải được mock. Thay đổi cách tổ chức mã có thể làm các test đó hỏng dù hợp đồng nghiệp vụ vẫn đúng.

Không mặc định dùng “không có bất kỳ tương tác nào” cho toàn service khi bị từ chối. Service có thể phải đọc quyền, đọc request và ghi audit. Hãy tập trung vào việc không có tương tác tạo chuyển dịch giá trị hoặc thay đổi bị cấm. Khi thứ tự có ý nghĩa bảo mật, như kiểm tra quyền trước khi tiết lộ kết quả cache, có thể kiểm tra thứ tự ở ranh giới đó bằng một test có mục đích cụ thể.

## 9. Unit test cho quyết định idempotency và yêu cầu trùng

Idempotency có hai phần cần phân biệt: quyết định làm gì khi gặp một danh tính lệnh đã biết và cơ chế nhiều tiến trình tranh quyền thực thi danh tính đó. Unit test phù hợp với phần quyết định; phần tranh quyền cần kiểm thử tích hợp và đồng thời.

### 9.1. Xây bảng quyết định theo trạng thái đã lưu

| Dữ kiện | Kết quả theo hợp đồng mẫu |
| --- | --- |
| Chưa có khóa trong đúng scope | Đề nghị nhận quyền xử lý; chưa suy ra đã nhận quyền thành công. |
| Cùng khóa, cùng fingerprint, đang xử lý | Trả trạng thái đang xử lý hoặc tín hiệu retry theo hợp đồng. |
| Cùng khóa, cùng fingerprint, đã tiếp nhận lệnh | Trả danh tính và trạng thái của command cũ. |
| Cùng khóa, cùng fingerprint, đã có kết quả cuối | Trả kết quả cũ sau khi kiểm tra quyền truy cập. |
| Cùng khóa nhưng fingerprint khác | Từ chối xung đột, không biến thành lệnh mới. |
| Khác khóa nhưng cùng danh tính lệnh nghiệp vụ | Liên kết về command cũ hoặc từ chối theo quy tắc chống trùng nghiệp vụ. |
| Khóa thuộc scope tenant hoặc chủ thể khác | Không sử dụng kết quả đó để trả dữ liệu trái quyền. |
| Lệnh trước timeout, kết quả đối tác chưa rõ | Tra cứu hoặc đối soát theo thiết kế; không mặc định thực thi một giao dịch mới. |

Test cần kiểm tra scope của khóa và fingerprint. Thay từng trường có ý nghĩa như số tiền, currency, payment, người nhận hoặc revision rồi giữ nguyên khóa để kiểm tra xung đột. Ngược lại, thay thứ tự trường JSON nhưng giữ nguyên ý nghĩa phải cho fingerprint ổn định nếu hợp đồng coi hai payload là tương đương.

Không chỉ mock `fingerprintOf(payload)` luôn trả cùng một chuỗi trong toàn bộ bộ test. Khi đó, lỗi bỏ sót trường người nhận có thể không bị phát hiện. Hàm tạo fingerprint nên có test riêng với biểu diễn chuẩn hóa và dữ liệu phân biệt được các ý nghĩa nghiệp vụ.

### 9.2. Quyền truy cập vẫn áp dụng khi replay

Lần xử lý đầu có thể hợp lệ nhưng lần đọc lại kết quả diễn ra sau khi người dùng mất quyền. Cần xác định hợp đồng: ai được xem kết quả cũ, quyền nào cần kiểm tra lại và dữ liệu nào được phép trả về. Unit test có thể dùng cùng khóa nhưng actor hoặc phạm vi quyền mới để kiểm tra chính sách này.

Đừng dùng một cache idempotency toàn cục theo chuỗi khóa rồi trả phản hồi đã lưu trước khi xác thực người gọi. Ngoài lỗi logic lệnh trùng, cách đó có thể làm lộ dữ liệu của người khác. Test nên kiểm tra trực tiếp hành vi không tiết lộ kết quả ngoài scope, thay vì chỉ kiểm tra không phát sinh lần thu tiền mới.

### 9.3. Phân biệt khóa thử lại và danh tính nghiệp vụ

Một client có thể đổi `Idempotency-Key` cho cùng `refund_request_id`. Nếu mỗi khóa mới tạo một refund, hệ thống vẫn bị hoàn trùng. Unit test điều phối nên kiểm tra rằng service nhận ra command nghiệp vụ đã có và không tạo lệnh thứ hai.

Ngược lại, cùng một payment có thể có nhiều yêu cầu hoàn hợp lệ trong giới hạn. Không đặt quy tắc “mỗi payment chỉ có một refund” nếu đó không phải hợp đồng sản phẩm. Fixture nên có cả hai tình huống: retry cùng một yêu cầu và hai yêu cầu khác nhau trên cùng payment.

Test tuần tự với fake repository có thể kiểm tra các quyết định trên. Nó không chứng minh thao tác “tìm rồi tạo” là nguyên tử. Hai instance có thể đồng thời không thấy dữ liệu rồi cùng insert; việc đó cần constraint và xử lý xung đột thực tế.

## 10. Kiểm tra thuộc tính và quan hệ giữa các lần đánh giá

Test theo ví dụ cụ thể dễ đọc và phù hợp với ca tấn công đã biết. Với không gian đầu vào lớn, có thể bổ sung kiểm tra thuộc tính hoặc quan hệ giữa nhiều đầu vào để phát hiện vùng còn thiếu.

### 10.1. Các thuộc tính có ý nghĩa nghiệp vụ

- Khi mọi điều kiện khác giữ nguyên, tăng phần tiền đã giữ không thể biến một quyết định thiếu tiền thành cho phép.
- Khi mọi điều kiện khác giữ nguyên, giảm hạn mức của quyết định duyệt không thể cấp thêm quyền thực thi.
- Khi request không thay đổi, đưa thời gian từ trước sang sau hạn không thể làm quyết định đã hết hạn có hiệu lực trở lại.
- Với các facts giống nhau và thời gian giống nhau, policy thuần cho kết quả giống nhau.
- Với một hành động bị từ chối, aggregate không phát sinh thay đổi nghiệp vụ hoặc ý định chuyển dịch giá trị mới.
- Một sự kiện hoàn tất được xử lý lặp không làm tổng đã hoàn tăng thêm sau lần đầu theo hợp đồng của aggregate.

Những thuộc tính này cần tiền điều kiện chính xác. Ví dụ, kiểm tra đơn điệu về tiền phải giữ nguyên actor, currency, trạng thái và hiệu lực phê duyệt. Nếu mỗi lần sinh dữ liệu đều thay cả quyền lẫn hạn mức, kết quả không còn diễn giải được.

### 10.2. Ví dụ kiểm tra đơn điệu bằng dữ liệu hữu hạn

Phương thức dưới đây có thể đặt thêm trong lớp `RefundPolicyTest` ở trên. Nó dùng một tập đầu vào xác định, không cần thư viện sinh dữ liệu:

```java
@Test
void increasingReservationCannotRestorePermissionAfterInsufficientFunds() {
    assertEquals(
            RefundPolicy.Decision.ALLOW,
            policy.evaluate(
                    actor(), request(10_000L, 3L), balance(), validApproval(), NOW));

    boolean alreadyInsufficient = false;
    for (long reserved = 0L; reserved <= 80_000L; reserved += 1_000L) {
        var current = new RefundPolicy.Balance(
                "payment-1", "tenant-a", "VND",
                100_000L, 20_000L, reserved);
        var decision = policy.evaluate(
                actor(), request(10_000L, 3L), current, validApproval(), NOW);

        if (alreadyInsufficient) {
            assertEquals(
                    RefundPolicy.Decision.INSUFFICIENT_REMAINING,
                    decision,
                    "reservation=" + reserved);
        }
        if (decision == RefundPolicy.Decision.INSUFFICIENT_REMAINING) {
            alreadyInsufficient = true;
        }
    }
    assertEquals(true, alreadyInsufficient);
}
```

Ca hợp lệ ban đầu và việc phải quan sát được trạng thái thiếu tiền giúp tránh một phép kiểm tra đơn điệu đúng một cách rỗng. Tuy vậy, thuộc tính đơn điệu vẫn không thay thế các ca đúng biên và ca có số tiền kỳ vọng cụ thể. Một hàm luôn cho phép hoặc luôn từ chối có thể qua một số thuộc tính yếu nếu thiếu các ca neo hợp lệ và không hợp lệ.

Nếu dùng sinh dữ liệu ngẫu nhiên, cần lưu seed hoặc đầu vào tối thiểu gây lỗi để tái hiện. Cần có generator tạo trạng thái hợp lệ trước, rồi biến đổi theo mục tiêu; không để phần lớn mẫu chỉ bị chặn bởi cùng một lỗi cấu trúc đầu vào. Thu nhỏ dữ liệu thất bại giúp chuyển một lỗi khó đọc thành regression test cụ thể.

## 11. Tránh các bộ test xanh nhưng không bảo vệ quy tắc

### 11.1. Mock chính điều cần kiểm tra

```text
Stub policy.evaluate(...) luôn trả ALLOW.
Gọi service.
Assert service trả success.
```

Test này có thể hữu ích cho một nhánh điều phối rất hẹp, nhưng không kiểm tra được quy tắc quyền, số tiền hoặc phê duyệt. Không gắn nó với kết luận “đã kiểm thử hoàn tiền an toàn”. Cần dùng policy thật hoặc có bộ unit test riêng cho policy được stub.

### 11.2. Chỉ assert không ném exception

Một hàm có thể không ném exception nhưng cập nhật sai payment, làm tròn sai số tiền hoặc tạo hai event. Hãy assert các kết quả có ý nghĩa: danh tính đối tượng, số tiền, currency, state, revision, command và những hiệu ứng phải vắng mặt.

Tương tự, `assertThrows` cần chỉ rõ lỗi mong đợi khi lỗi là hợp đồng ổn định, đồng thời kiểm tra dữ liệu không bị thay đổi trái phép. Một `NullPointerException` vô tình không nên được xem là đã kiểm tra hành vi “thiếu phê duyệt thì bị từ chối”.

### 11.3. Chỉ có happy path hoặc chỉ có từ chối

Happy path không phát hiện được bỏ kiểm tra quyền. Nhưng một bộ toàn ca từ chối cũng có thể xanh với triển khai luôn từ chối. Mỗi nhóm quy tắc cần ca hợp lệ cho thấy hệ thống vẫn cho phép đúng hành vi, cùng ca không hợp lệ phân biệt điều kiện cần bảo vệ.

### 11.4. Expected result sao chép thuật toán

Nếu test tính expected bằng cùng công thức và cùng cách làm tròn như code sản phẩm, lỗi có thể xuất hiện ở cả hai nơi. Ưu tiên bảng ví dụ có kết quả đã tính độc lập, thuộc tính từ đặc tả và một mô hình tham chiếu đơn giản khi cần.

### 11.5. Dữ liệu dùng chung khiến test phụ thuộc thứ tự

Không dùng một aggregate mutable, danh sách event hoặc fake store tĩnh được chia sẻ mà không reset. Test trước có thể tạo quyết định duyệt hoặc sử dụng hạn mức khiến test sau phụ thuộc lịch chạy. Mỗi test nên tự tạo dữ liệu và có thể chạy riêng với cùng kết quả.

### 11.6. Coverage bị hiểu như bảo đảm bảo mật

Line coverage cao cho biết dòng mã đã được chạy, không chứng minh các invariant đã được kiểm tra. Một phép so sánh sai ở biên có thể vẫn được chạy trong mọi test. Branch coverage giúp thấy nhánh chưa đi qua, nhưng cũng cần assertion phân biệt đúng và sai.

Có thể đánh giá sức phân biệt của test bằng các thay đổi giả định: bỏ kiểm tra tenant, bỏ kiểm tra revision, thay `<=` thành `<`, không trừ phần giữ hoặc trả `ALLOW` ở nhánh sai. Nếu các test liên quan không thất bại, cần xem lại dữ liệu và assertion. Đây là cách suy nghĩ về chất lượng bộ test, không phải lý do tự ý thay đổi code sản phẩm trong quá trình chạy thông thường.

## 12. Tổ chức bộ test theo rủi ro và khả năng truy vết

### 12.1. Đặt tên theo hành vi

Tên như `testExecute1` không cho biết quy tắc bị hỏng khi test thất bại. Nên dùng tên thể hiện hành vi và điều kiện, chẳng hạn:

```text
rejectsExecutionWhenApprovalRevisionIsStale
rejectsActorFromAnotherTenant
allowsAmountExactlyEqualToRemaining
doesNotCreateNewCommandForRepeatedBusinessRequest
keepsAggregateUnchangedWhenExecutionIsRejected
```

Có thể đặt mã quy tắc trong chú thích hoặc tên nhóm test để liên kết với đặc tả. Không nhất thiết nhồi mọi chi tiết vào tên; phần arrange và assertion phải đủ rõ để người sửa lỗi hiểu hợp đồng.

### 12.2. Ghi rõ bằng chứng còn thiếu ở cấp khác

| Quy tắc | Unit test trọng tâm | Kiểm tra tiếp ở cấp phù hợp |
| --- | --- | --- |
| Không hoàn vượt giá trị đã thu | Biên số tiền, phần giữ, dữ liệu mâu thuẫn. | Hai lệnh cạnh tranh, cập nhật có điều kiện và tính tổng cuối. |
| Không bỏ qua phê duyệt | Trạng thái, revision, người duyệt và hạn hiệu lực. | Endpoint, batch, job và công cụ vận hành đi qua kiểm soát. |
| Không thao tác chéo đối tượng | Ma trận actor–action–resource–tenant. | Repository lọc đúng đối tượng, API không tin ID và tenant từ client. |
| Không thực thi trùng | Bảng quyết định replay, fingerprint và command cũ. | Constraint, tranh quyền cùng khóa, timeout và phục hồi sau crash. |
| Không mất ý định gửi | Service tạo dữ liệu lệnh đúng hợp đồng. | Commit cùng outbox, worker giao lại và dedup phía nhận. |

Một annotation transaction không tạo bằng chứng trong unit test chạy trực tiếp bằng `new Service(...)`. Nếu transaction được framework áp dụng qua proxy, cần kiểm tra ở môi trường tích hợp có cấu hình phù hợp. Tương tự, fake repository không chứng minh unique constraint tồn tại trong schema triển khai.

### 12.3. Dùng regression test khi sửa lỗi logic

Khi có lỗi bỏ qua bước duyệt, hãy mô tả tình huống tối thiểu ở cấp unit: actor hợp lệ, request chưa được duyệt, gọi hành vi thực thi và quan sát không có lệnh mới. Khi sửa lỗi cạnh tranh, vẫn cần unit test cho công thức hoặc quyết định nếu chúng thay đổi, nhưng test tái hiện đồng thời mới là bằng chứng trọng tâm cho cơ chế chống race.

Không nhân đôi cùng một assertion ở mọi tầng chỉ để tăng số lượng test. Chọn tầng thấp nhất có thể kiểm tra đáng tin cậy một quy tắc, rồi dùng số lượng phù hợp các test tích hợp hoặc xuyên luồng để kiểm tra cách những quy tắc đó được nối vào hệ thống.

## 13. Quy trình thiết kế một nhóm unit test thực tế

Giả sử cần bổ sung chức năng hoàn tiền có phê duyệt. Có thể thực hiện theo trình tự sau:

1. **Chốt hợp đồng:** tiền đã thu được định nghĩa thế nào, ai được tạo và duyệt, quyết định gắn với revision nào, giới hạn nào là cứng.
2. **Chọn hành vi nhỏ:** bắt đầu với policy quyết định hoặc hành vi chuyển trạng thái, chưa cần HTTP và database.
3. **Tạo fixture hợp lệ:** actor, request, payment, approval và thời gian cùng nhất quán.
4. **Viết ca được phép:** số tiền nhỏ hợp lệ và số tiền đúng bằng giới hạn.
5. **Thay từng điều kiện:** quyền, tenant, payment, state, approval, revision, hạn, currency, số tiền và số dư.
6. **Thêm chuỗi lạm dụng:** duyệt rồi sửa dữ liệu; gọi thực thi lặp; nhận lại sự kiện kết thúc; retry bằng khóa khác cho cùng lệnh.
7. **Kiểm tra điều phối cần thiết:** nhánh bị từ chối không tạo command hoặc outbox; nhánh replay trả về lệnh cũ trong đúng phạm vi quyền.
8. **Bổ sung thuộc tính có ích:** đơn điệu của hạn mức hoặc của phần giữ với tiền điều kiện rõ ràng.
9. **Ghi phần cần kiểm tra ngoài unit:** transaction, constraint, cạnh tranh, tích hợp đối tác và phục hồi sau crash.

Mục đích là tạo một bộ bằng chứng dễ giải thích: mỗi nhóm test trả lời một câu hỏi nghiệp vụ. Không cần dựng toàn bộ ứng dụng chỉ để kiểm tra một phép so sánh, nhưng cũng không dùng phép so sánh đã qua test để tuyên bố toàn bộ luồng tiền an toàn.

## 14. Checklist hoàn thiện unit test cho business rule

- [ ] Quy tắc có phát biểu rõ về chủ thể, đối tượng, trạng thái, số tiền, đơn vị và thời điểm.
- [ ] Có fixture hợp lệ và ít nhất một ca được phép cho mỗi hành vi cần hỗ trợ.
- [ ] Có ca từ chối theo từng điều kiện độc lập; tránh để một lỗi khác che nhánh đang kiểm tra.
- [ ] Có biên đúng bằng giới hạn, vượt một đơn vị, số không, số âm và số lớn phù hợp kiểu dữ liệu.
- [ ] Quyền được kiểm tra trên đối tượng và tenant cần thiết, không chỉ tên role.
- [ ] State machine có test chuyển bị cấm, sửa sau duyệt và hành động lặp.
- [ ] Quyết định duyệt gắn đúng request, revision, người duyệt, hạn mức và thời hạn theo hợp đồng.
- [ ] Nhánh bị từ chối không thay đổi aggregate hoặc tạo ý định chuyển dịch giá trị trái phép.
- [ ] Test idempotency phân biệt cùng khóa, khác payload, khác scope và cùng lệnh nghiệp vụ với khóa khác.
- [ ] Đồng hồ và dữ liệu ngẫu nhiên có thể kiểm soát; test không phụ thuộc thứ tự chạy.
- [ ] Quy tắc thật được kiểm tra; expected result không chỉ sao chép cách tính của implementation.
- [ ] Những điều cần transaction thật, cạnh tranh hoặc hệ thống bên ngoài được ghi nhận để kiểm thử ở cấp phù hợp.

Một unit test tốt làm cho quy tắc có thể bị phá vỡ trong mã nhưng khó bị phá vỡ mà không bị phát hiện. Giá trị của nó nằm ở việc chỉ ra chính xác điều kiện nào đã thay đổi và hành vi nghiệp vụ nào không còn được bảo vệ.
