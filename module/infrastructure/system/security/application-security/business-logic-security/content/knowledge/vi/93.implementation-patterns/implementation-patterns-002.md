# Specification pattern — Đặc tả điều kiện để bảo vệ logic nghiệp vụ

Bài học thuộc chương **Implementation Patterns** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Chủ đề là cách biểu diễn điều kiện nghiệp vụ thành những đặc tả có tên, có thể kết hợp và kiểm thử, sau đó cưỡng chế chúng trên đúng dữ liệu và đúng đường cập nhật.

Một hệ thống có thể kiểm tra role tại API nhưng vẫn cho người dùng tự duyệt yêu cầu của mình, duyệt đối tượng ngoài tenant hoặc duyệt số tiền đã bị sửa. Khi các điều kiện nằm rải rác trong controller, batch và consumer, mỗi đường vào dễ thực hiện một phiên bản khác nhau của cùng quy tắc.

**Specification pattern** tách điều kiện "một đối tượng/ngữ cảnh có thỏa yêu cầu không" khỏi đối tượng được đánh giá và thao tác sử dụng kết quả đó. Tài liệu gốc của Eric Evans và Martin Fowler mô tả specification qua việc đánh giá candidate, với các cách hiện thực bằng mã, tham số và tổ hợp. [Evans & Fowler: Specifications](https://www.martinfowler.com/apsupp/spec.pdf).

Trong bài này, candidate là **ngữ cảnh một lần duyệt hoàn tiền**, gồm actor đã xác minh, request được tải phía server, thời điểm đánh giá và version người duyệt đã xem. Specification giúp diễn đạt quyết định; nó không tự cung cấp authentication, transaction, khóa dữ liệu hay idempotency.

Ví dụ Java dùng cú pháp Java 21. Phần liên hệ persistence tham chiếu Spring Data JPA 4.0 và PostgreSQL 18 như những mốc minh họa, không suy cấu hình hay phiên bản dự án từ tên module.

Sau bài học, bạn cần có thể:

- Chia một quy tắc duyệt thành các điều kiện có ý nghĩa trong miền nghiệp vụ.
- Ghép `AND`, `OR`, `NOT` mà vẫn giữ các ràng buộc bắt buộc như tenant và phân tách nhiệm vụ.
- Đánh giá trên facts có nguồn đáng tin, không dùng cờ quyền hoặc giá từ client làm kết luận.
- Đặt specification ở use case và bảo vệ tính nhất quán giữa kiểm tra với cập nhật.
- Phân biệt domain specification với query specification của Spring Data JPA.
- Thiết kế lý do từ chối, audit và kiểm thử các trường hợp lạm dụng logic.

## 1. Vì sao cần một specification có tên?

Giả sử một checker được phép duyệt request hoàn tiền khi đồng thời thỏa các điều kiện:

~~~text
Actor có membership đang hoạt động trong tenant của request.
Actor có quyền refund.approve đối với phạm vi đang xét.
Người duyệt khác người tạo theo person identity đáng tin.
Số tiền và tiền tệ nằm trong thẩm quyền của checker.
Request đang chờ duyệt và chưa hết hạn duyệt.
Row version và content version khớp dữ liệu người duyệt đã xem.
~~~

Nếu cùng điều kiện được viết lại ở ba controller, một job và một script quản trị, sửa chính sách ở một nơi có thể bỏ sót nơi khác. Đặt tên như `SameTenant`, `IndependentChecker` hoặc `WithinApprovalLimit` làm rõ điều kiện cần review và dữ liệu cần kiểm thử.

Một specification nên trả lời một câu hỏi. Ví dụ `WithinApprovalLimit` so sánh tiền của request với hạn mức được cấp; nó không đồng thời gửi email, cập nhật số dư hay đánh dấu request đã duyệt.

### 1.1. Tách các trách nhiệm liên quan

| Trách nhiệm | Câu hỏi | Ví dụ |
|---|---|---|
| Input validation | Command có đúng hình dạng không? | ID đúng kiểu, expected version không âm |
| Authentication | Caller là ai? | Token được xác minh, mapping thành danh tính nội bộ |
| Authorization policy | Actor được làm gì trên đối tượng này? | Đúng tenant, quyền duyệt, phạm vi và hạn mức |
| Transition precondition | Đối tượng có thể chuyển trạng thái lúc này không? | Đang chờ duyệt, còn hạn, đúng version |
| Invariant trong miền | Điều gì phải luôn được giữ khi thay đổi? | Approval gắn đúng revision, không tự duyệt, số tiền hợp lệ |
| Concurrency control | Quyết định còn đúng khi ghi dữ liệu không? | Khóa, conditional update, version hoặc cơ chế tuần tự hóa phù hợp |

Specification có thể biểu diễn một phần điều kiện trong authorization hoặc transition. Hệ thống vẫn cần nơi bắt buộc sử dụng kết quả trước mutation. Một class tên `CanApproveSpecification` không bảo vệ được endpoint gọi thẳng repository.

### 1.2. Khi nào một câu lệnh if đã đủ?

Một điều kiện cục bộ, ít thay đổi và chỉ dùng tại một nơi có thể được giữ bằng `if` hoặc method có tên rõ. Specification hữu ích khi điều kiện cần tái sử dụng, tổ hợp theo chính sách, đánh giá độc lập hoặc kiểm thử nhiều biến thể.

Không cần tạo hàng chục class chỉ để bọc từng phép so sánh. Điều quan trọng là hợp đồng của điều kiện và nơi cưỡng chế, không phải số lượng abstraction.

## 2. Phép ghép logic là một phần của chính sách bảo mật

| Phép ghép | Ý nghĩa trên dữ liệu đầy đủ | Ví dụ |
|---|---|---|
| `A AND B` | Cả hai điều kiện đều bắt buộc | Đúng tenant và có quyền duyệt |
| `A OR B` | Một trong hai nhánh đủ để đạt điều kiện chung | Thuộc nhóm xử lý A hoặc nhóm xử lý B trong cùng tenant |
| `NOT A` | Phủ định một mệnh đề có nghĩa xác định | Không phải cùng person identity với maker |

### 2.1. Một OR đặt sai có thể mở quyền xuyên tenant

Giả sử `T` là đúng tenant, `O` là được phân công đối tượng và `S` là supervisor. Nếu supervisor được xử lý mọi request **trong tenant của mình**, biểu thức đúng là:

~~~text
T AND (O OR S)
~~~

Biểu thức sau mở một đường supervisor không cần thỏa tenant:

~~~text
(T AND O) OR S
~~~

| T | O | S | `(T AND O) OR S` | `T AND (O OR S)` |
|---|---|---|---|---|
| false | false | true | true — vượt tenant | false |
| true | false | true | true | true |
| true | false | false | false | false |
| true | true | false | true | true |

Trong Java, chuỗi method `sameTenant.and(assigned).or(supervisor)` tạo biểu thức sai ở trên. Không có quy tắc ưu tiên toán tử nào tự chuyển chuỗi gọi đó thành biểu thức mong muốn.

Một cấu trúc dễ review hơn là:

~~~java
BusinessSpec<ApprovalContext> mandatoryScope = sameTenant.and(activeMember);
BusinessSpec<ApprovalContext> eligibleAssignee = assigned.or(supervisor);
BusinessSpec<ApprovalContext> allowed = mandatoryScope.and(eligibleAssignee);
~~~

Ngoại lệ về người được phân công không mặc nhiên miễn tenant, state, checker độc lập hoặc hạn mức. Mỗi ngoại lệ cần xác định nó thay thế điều kiện nào. Với quy trình khẩn cấp, nên có use case và bằng chứng riêng thay vì thêm `or(isAdmin)` vào toàn bộ policy.

### 2.2. Không biến "không biết" thành "được phép"

Một lời gọi tra cứu blacklist có thể thất bại. Khi đó hệ thống chưa biết caller có nằm trong blacklist không. Nếu bắt exception và trả `false` từ `isBlacklisted`, rồi gọi `isBlacklisted.not()`, kết quả sẽ trở thành `true`.

Với API boolean trong bài, dữ liệu bắt buộc phải đầy đủ và hợp lệ **trước khi** đánh giá. Lỗi tải facts hoặc lỗi đánh giá phải dừng use case trước mutation; không thay lỗi thành một kết quả có thể bị phủ định để cấp quyền. Có thể phân biệt lỗi hạ tầng với từ chối nghiệp vụ ở hợp đồng response và log, nhưng cả hai đều không cho phép tác động chưa được chấp thuận.

Nếu miền thật sự cần ba trạng thái `ALLOW`, `DENY`, `INDETERMINATE`, hãy định nghĩa bảng tổ hợp riêng và chỉ tạo tác động khi kết quả cuối là `ALLOW`. Không đem một hàm `not()` boolean áp lên trạng thái chưa xác định. Tránh phủ định một policy authorization tổng hợp để xây policy cho hành động khác; "không được duyệt" không đồng nghĩa "được hủy".

## 3. Hiện thực một domain specification tối thiểu trong Java

Interface sau là mã do ứng dụng định nghĩa. Nó không phụ thuộc Spring hoặc persistence:

~~~java
import java.util.Objects;

@FunctionalInterface
public interface BusinessSpec<T> {
    boolean isSatisfiedBy(T candidate);

    default BusinessSpec<T> and(BusinessSpec<? super T> other) {
        Objects.requireNonNull(other, "other");
        return candidate -> isSatisfiedBy(candidate)
                && other.isSatisfiedBy(candidate);
    }

    default BusinessSpec<T> or(BusinessSpec<? super T> other) {
        Objects.requireNonNull(other, "other");
        return candidate -> isSatisfiedBy(candidate)
                || other.isSatisfiedBy(candidate);
    }

    default BusinessSpec<T> not() {
        return candidate -> !isSatisfiedBy(candidate);
    }
}
~~~

Java đã có `Predicate<T>` với `test`, `and`, `or` và `negate`; có thể dùng nó nếu tên và hợp đồng phù hợp. Các phép `and`/`or` của `Predicate` có short-circuit và truyền exception về caller. [Java SE 21: Predicate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Predicate.html).

`BusinessSpec` dùng tên `isSatisfiedBy` để làm rõ ý nghĩa miền. Các phép ghép trong mẫu cũng có short-circuit: nhánh phải có thể không chạy. Vì vậy:

- Không đặt ghi audit bắt buộc, tăng bộ đếm hoặc gọi provider trong một leaf specification.
- Không dựa vào việc mọi leaf đều chạy để tải facts cần dùng ở leaf sau.
- Không đặt truy vấn database hoặc HTTP tùy ý trong từng predicate rồi kỳ vọng chi phí không đổi.
- Không bắt exception trong leaf để trả một boolean tùy tiện.

Mỗi lần đánh giá nên dùng cùng snapshot, cùng thời điểm và cùng bộ tham số policy. Nếu một leaf đọc `Instant.now()` riêng và leaf khác đọc entity vừa thay đổi, kết quả tổng không còn mô tả một ngữ cảnh nhất quán.

Một specification có thể là lambda, class hoặc record giữ tham số bất biến. Ví dụ `WithinApprovalLimit(limit, currency)` phù hợp khi cùng quy tắc dùng nhiều cấu hình. Không sửa tham số dùng chung trong singleton để phục vụ từng request; dữ liệu của caller phải thuộc context riêng của lần gọi.

## 4. Candidate là facts đã được giải quyết phía server

Context không nên chỉ là entity `RefundRequest`, vì quyền duyệt còn phụ thuộc actor, tenant, thẩm quyền và thời điểm. Cũng không nên chỉ là DTO client tự khai actor hoặc `canApprove = true`.

Các kiểu minh họa sau được đặt trong các tệp Java tương ứng khi triển khai. Các constructor chỉ kiểm tra tính đầy đủ/hình dạng cơ bản; việc xác minh nguồn dữ liệu thuộc adapter và application service.

~~~java
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public record ActorFacts(
        UUID personId,
        UUID tenantId,
        boolean membershipActive,
        Set<String> permissions,
        long approvalLimitMinor,
        String limitCurrency) {
    public ActorFacts {
        Objects.requireNonNull(personId, "personId");
        Objects.requireNonNull(tenantId, "tenantId");
        permissions = Set.copyOf(permissions);
        Objects.requireNonNull(limitCurrency, "limitCurrency");
        if (approvalLimitMinor < 0) {
            throw new IllegalArgumentException("Negative approval limit");
        }
    }
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record RefundFacts(
        UUID requestId,
        UUID tenantId,
        UUID makerPersonId,
        String state,
        long rowVersion,
        long contentVersion,
        long amountMinor,
        String currency,
        Instant approvalDeadline) {
    public RefundFacts {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(makerPersonId, "makerPersonId");
        Objects.requireNonNull(state, "state");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(approvalDeadline, "approvalDeadline");
        if (rowVersion < 0 || contentVersion < 0 || amountMinor <= 0) {
            throw new IllegalArgumentException("Invalid refund facts");
        }
    }
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;

public record ApprovalContext(
        ActorFacts actor,
        RefundFacts refund,
        long expectedRowVersion,
        long reviewedContentVersion,
        Instant evaluatedAt) {
    public ApprovalContext {
        Objects.requireNonNull(actor, "actor");
        Objects.requireNonNull(refund, "refund");
        Objects.requireNonNull(evaluatedAt, "evaluatedAt");
        if (expectedRowVersion < 0 || reviewedContentVersion < 0) {
            throw new IllegalArgumentException("Invalid reviewed version");
        }
    }
}
~~~

### 4.1. Nguồn của từng nhóm dữ liệu

| Facts | Nguồn cần có thẩm quyền | Điều cần tránh |
|---|---|---|
| Person identity, tenant membership | Principal đã xác minh kết hợp mapping/membership phía server | So sánh account ID do client gửi rồi coi đó là phân tách con người |
| Permission và hạn mức được cấp | Policy/grant store hoặc claim được chấp nhận theo hợp đồng và độ cũ cho phép | Nhận `approvalLimit` hay role từ body |
| Số tiền, tiền tệ, maker, trạng thái, version | Request được tải phía server trong scope đã xác minh | Kiểm tra giá từ request rồi cập nhật số tiền khác trong database |
| Expected row/content version | Command từ client, dùng để đối chiếu với dữ liệu server | Coi version đúng là bằng chứng có quyền |
| Thời điểm đánh giá | Clock phía server lấy một lần theo hợp đồng thời gian | Dùng ngày giờ client để kéo dài hạn duyệt |

`Set.copyOf` giúp snapshot không bị sửa qua collection permission ban đầu. Record không tự biến dữ liệu giả thành đáng tin: một caller trong code vẫn có thể dựng `ActorFacts` bất kỳ. Không bind trực tiếp request HTTP vào các kiểu facts này.

Mẫu biểu diễn tiền bằng số nguyên đơn vị nhỏ nhất theo hợp đồng tiền tệ của ứng dụng; chỉ so sánh khi tiền tệ khớp. Không mặc định mọi currency đều có hai chữ số thập phân. Nếu có quy đổi, nguồn tỷ giá, quy tắc làm tròn và version tỷ giá phải là phần rõ ràng của quyết định.

String `state` giúp ví dụ ngắn; state không được nhận diện sẽ không thỏa rule chờ duyệt. Khi triển khai mô hình miền có thể dùng enum/state type và chính sách migration tương ứng.

## 5. Ghép policy duyệt từ các đặc tả nhỏ

Các specification sau dùng ba record ở phần 4. Mẫu giả định grant `refund.approve` có hiệu lực trong toàn tenant đã được xác minh, kèm hạn mức của checker. Nếu hệ thống còn phân quyền theo chi nhánh, nhóm được phân công hoặc loại hoàn tiền, phải bổ sung facts và rule tương ứng; permission action tổng quát không tự mô tả các scope đó.

~~~java
public final class ApprovalSpecs {
    private ApprovalSpecs() {}

    private static final BusinessSpec<ApprovalContext> SAME_TENANT = c ->
            c.actor().tenantId().equals(c.refund().tenantId());

    private static final BusinessSpec<ApprovalContext> ACTIVE_MEMBER = c ->
            c.actor().membershipActive();

    private static final BusinessSpec<ApprovalContext> HAS_APPROVE_GRANT = c ->
            c.actor().permissions().contains("refund.approve");

    private static final BusinessSpec<ApprovalContext> INDEPENDENT_CHECKER = c ->
            !c.actor().personId().equals(c.refund().makerPersonId());

    private static final BusinessSpec<ApprovalContext> WITHIN_LIMIT = c ->
            c.actor().limitCurrency().equals(c.refund().currency())
            && c.refund().amountMinor() <= c.actor().approvalLimitMinor();

    private static final BusinessSpec<ApprovalContext> PENDING = c ->
            "PENDING_APPROVAL".equals(c.refund().state());

    private static final BusinessSpec<ApprovalContext> SAME_ROW_VERSION = c ->
            c.refund().rowVersion() == c.expectedRowVersion();

    private static final BusinessSpec<ApprovalContext> REVIEWED_CONTENT = c ->
            c.refund().contentVersion() == c.reviewedContentVersion();

    private static final BusinessSpec<ApprovalContext> BEFORE_DEADLINE = c ->
            c.evaluatedAt().isBefore(c.refund().approvalDeadline());

    public static BusinessSpec<ApprovalContext> actorMayApprove() {
        return SAME_TENANT
                .and(ACTIVE_MEMBER)
                .and(HAS_APPROVE_GRANT)
                .and(INDEPENDENT_CHECKER)
                .and(WITHIN_LIMIT);
    }

    public static BusinessSpec<ApprovalContext> transitionIsValid() {
        return PENDING
                .and(SAME_ROW_VERSION)
                .and(REVIEWED_CONTENT)
                .and(BEFORE_DEADLINE);
    }

    public static BusinessSpec<ApprovalContext> mayApprove() {
        return actorMayApprove().and(transitionIsValid());
    }
}
~~~

Tách `actorMayApprove` với `transitionIsValid` giúp application service phân biệt quyền của actor với trạng thái có thể thay đổi. Khi caller chưa có quyền biết request tồn tại, không trả chi tiết transition cho caller đó.

### 5.1. Một số hợp đồng quan trọng của mẫu

- `membershipActive` là kết quả giải quyết membership cho chính `actor.tenantId`, không phải một cờ active toàn hệ thống.
- `personId` biểu diễn con người theo mapping đáng tin; một người tạo hai account không trở thành hai người duyệt độc lập.
- `WITHIN_LIMIT` kiểm tra cùng currency trước khi so sánh. Mẫu không cấp quyền bằng cách đổi currency hoặc cho hạn mức âm.
- Deadline là biên loại trừ: tại đúng `approvalDeadline`, rule trả `false`. Cần công bố biên thời gian này trong nghiệp vụ.
- `reviewedContentVersion` do client gửi chỉ có nghĩa khi so với version server. Nó không chứng minh actor đã thực sự đọc mọi field trên giao diện.

Mọi thay đổi nội dung trọng yếu như số tiền, tiền tệ hoặc người nhận phải tăng content version theo hợp đồng server. Approval phải lưu revision/snapshot đã được duyệt. Nếu có đường sửa người nhận nhưng không tăng version, `REVIEWED_CONTENT` không thể phát hiện thay đổi đó.

`mayApprove` là câu trả lời tổng hợp cho facts hiện tại. Một kết quả `true` không nên được giữ vô thời hạn để dùng cho request khác, actor khác hoặc lần cập nhật khác.

## 6. Đặt đánh giá tại ranh giới use case và bảo vệ đến lúc ghi

### 6.1. Dòng thực thi mong muốn

~~~text
Command từ HTTP / batch / consumer
  → Xác thực caller và giải quyết tenant được phép
  → Bắt đầu transaction theo hợp đồng hạ tầng
  → Tải facts actor/policy và request đúng scope
  → Kiểm tra quyền theo đối tượng bằng specification
  → Kiểm tra state, version, nội dung và thời hạn
  → Aggregate thực hiện transition hợp lệ
  → Ghi request + approval + evidence nhất quán
  → Commit
~~~

Pseudocode Java dưới đây minh họa orchestration; `transactions`, resolver, repository, aggregate, receipt và exception là các port/kiểu do ứng dụng tự định nghĩa. `transactions.required` biểu diễn việc thân xử lý chạy trong transaction có rollback khi thất bại, không phải tên một API mặc định của Spring.

~~~java
public ApprovalReceipt approve(ApproveCommand command) {
    return transactions.required(() -> {
        ActorFacts actor = actorResolver.requireCurrentFacts();

        RefundRequest request = refunds
                .lockByTenantAndId(actor.tenantId(), command.requestId())
                .orElseThrow(RequestNotVisibleException::new);

        ApprovalContext context = new ApprovalContext(
                actor,
                request.toFacts(),
                command.expectedRowVersion(),
                command.reviewedContentVersion(),
                clock.instant());

        if (!ApprovalSpecs.actorMayApprove().isSatisfiedBy(context)) {
            throw new ForbiddenOperationException();
        }
        if (!ApprovalSpecs.transitionIsValid().isSatisfiedBy(context)) {
            throw new InvalidTransitionException();
        }

        ApprovalReceipt receipt = request.approve(
                actor.personId(),
                context.refund().contentVersion(),
                context.evaluatedAt());

        refunds.save(request);
        evidence.append(receipt, actor, "refund-approval-v1");
        return receipt;
    });
}
~~~

`ApproveCommand` chỉ cần request ID và các expected version cần thiết, không nhận actor, quyền hoặc số tiền làm nguồn sự thật. `request.toFacts()` phải phản ánh chính aggregate sẽ bị cập nhật. `approve` tạo approval gắn đúng request, tenant, revision, checker và thời điểm; không tự tạo tác động chuyển tiền.

Aggregate vẫn bảo vệ các bất biến và transition mà nó sở hữu, chẳng hạn chỉ duyệt từ trạng thái chờ và gắn approval vào đúng content version. Có thể tái sử dụng cùng đặc tả thuần khi phù hợp. Không cần làm aggregate truy cập SecurityContext để biết caller; application service truyền danh tính đã giải quyết và các dữ kiện cần cho hành vi miền.

Hợp đồng của mẫu là request, approval và evidence thành công được lưu trong cùng tài nguyên giao dịch. Nếu evidence hoặc sự kiện đi tới dịch vụ ngoài, cần thiết kế nhất quán riêng, chẳng hạn outbox. Không coi tên method `save` hoặc `lockByTenantAndId` là bằng chứng hạ tầng đã hiện thực đúng transaction/lock.

### 6.2. Bài toán kiểm tra rồi mới dùng dữ liệu đã thay đổi

~~~text
T1: đọc request số tiền 100, checker có hạn mức 200 → specification cho phép.
T2: sửa request thành 1.000 và commit.
T1: ghi approval cho request hiện tại mà không kiểm tra version → duyệt sai.
~~~

Specification của T1 có thể hoàn toàn đúng với snapshot cũ. Lỗi nằm ở việc dùng kết quả đó cho dữ liệu khác. Có hai hướng thường gặp:

| Hướng | Điều cần bảo đảm |
|---|---|
| Khóa request rồi đánh giá | Đọc đúng dữ liệu sau khi có lock; giữ lock đến hết transaction; mọi đường ghi phải tuân theo cơ chế cạnh tranh của database |
| Optimistic/conditional write | Write kiểm tra version/state đã đánh giá; nếu không còn khớp thì không commit approval và cần tải lại để quyết định mới |

Ví dụ PostgreSQL mô tả row lock `FOR UPDATE` chặn các cập nhật/khóa xung đột trên cùng hàng đến khi transaction kết thúc. Mức isolation và lỗi cạnh tranh vẫn cần xử lý theo cấu hình thật. [PostgreSQL 18: Row-Level Locks](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).

Một conditional update minh họa cho phần state/version:

~~~sql
UPDATE refund_request
SET state = 'APPROVED',
    approved_content_version = content_version,
    row_version = row_version + 1
WHERE tenant_id = :verified_tenant_id
  AND id = :request_id
  AND state = 'PENDING_APPROVAL'
  AND row_version = :evaluated_row_version
  AND content_version = :evaluated_content_version;
~~~

Phải kiểm tra số hàng được cập nhật bằng một. Nếu bằng không, không ghi nhận thành công; nếu approval đã được insert trước đó trong cùng transaction thì phải rollback transaction khi điều kiện này thất bại. Ví dụ SQL chỉ bảo vệ những điều kiện ghi rõ, chưa hiện thực toàn bộ policy, deadline, membership, hạn mức tổng hoặc bằng chứng duyệt.

Nếu dùng expected version từ context để conditional write, version đó phải đại diện mọi thay đổi request có liên quan. Các guard thời gian cũng cần thời điểm có hiệu lực đã chọn: mẫu xét tại quyết định, không tự hứa deadline vẫn còn tại commit hay lúc worker thực thi lâu sau đó.

### 6.3. Các bất biến vượt quá một request

Hai request riêng lẻ đều có thể thỏa `amount <= checkerLimit`, nhưng tổng hai request vượt ngân sách còn lại. Một specification kiểm tra tổng bằng snapshot đọc thông thường chưa ngăn hai transaction cùng tiêu cùng hạn mức.

Cần cơ chế cập nhật nhất quán trên tài nguyên hạn mức, reservation/conditional decrement, hoặc chiến lược isolation và retry phù hợp với bất biến. Khóa một request không tự khóa membership, bảng policy hay số dư tổng.

Việc thu hồi grant cũng cần hợp đồng hiệu lực rõ. Nếu quyền phải còn hiệu lực đến thời điểm cập nhật, phải phối hợp việc đọc/kiểm tra version của dữ liệu quyền với đường ghi và đường thu hồi. Ghi policy version vào audit chỉ giúp truy vết, không tự loại bỏ race.

## 7. Domain specification và Spring Data JPA Specification

Spring Data JPA có `Specification<T>` để tạo predicate Criteria API và `JpaSpecificationExecutor` để thực thi query. Đây là công cụ biểu diễn điều kiện ở tầng persistence; phần dưới tham chiếu API `Specification` trong nhánh tài liệu 4.0. [Spring Data JPA 4.0: Specifications](https://docs.spring.io/spring-data/jpa/reference/4.0/jpa/specifications.html).

| Khía cạnh | `BusinessSpec<ApprovalContext>` trong bài | `org.springframework.data.jpa.domain.Specification<RefundEntity>` |
|---|---|---|
| Dữ liệu đầu vào | Facts actor + request + thời điểm + version | Root/query/CriteriaBuilder để tạo query predicate |
| Kết quả trực tiếp | Boolean trên một context đã có | Predicate được provider dùng khi sinh query |
| Trách nhiệm chính | Diễn đạt điều kiện miền cần đánh giá | Lọc/chọn dữ liệu ở database |
| Đồng thời và commit | Không tự cung cấp | Không tự cung cấp chỉ vì được gọi là Specification |
| Phụ thuộc persistence | Không bắt buộc | Có |

Không import nhầm hai interface hoặc kéo JPA Criteria vào policy thuần chỉ để dùng chung một tên. Có thể đặt tên riêng như `RefundApprovalSpecs` và `RefundQuerySpecs`.

### 7.1. Query có tenant scope bắt buộc

Ví dụ sau giả định entity có thuộc tính `tenantId` kiểu UUID và `state` kiểu String. `RefundEntity` là entity ứng dụng cần tự định nghĩa.

~~~java
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.jpa.domain.Specification;

public final class RefundQuerySpecs {
    private RefundQuerySpecs() {}

    public static Specification<RefundEntity> inTenant(UUID verifiedTenant) {
        Objects.requireNonNull(verifiedTenant, "verifiedTenant");
        return (root, query, cb) ->
                cb.equal(root.get("tenantId"), verifiedTenant);
    }

    public static Specification<RefundEntity> pendingApproval() {
        return (root, query, cb) ->
                cb.equal(root.get("state"), "PENDING_APPROVAL");
    }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface RefundRepository
        extends JpaRepository<RefundEntity, UUID>,
                JpaSpecificationExecutor<RefundEntity> {
}
~~~

Với repository đó, query minh họa:

~~~java
var scoped = RefundQuerySpecs.inTenant(verifiedTenant)
        .and(RefundQuerySpecs.pendingApproval());
var page = repository.findAll(scoped, pageable);
~~~

Tenant truyền vào phải đã được xác minh với principal. Những filter do người dùng chọn chỉ được thu hẹp trong scope bắt buộc. Không ghép `.or(userFilter)` phía ngoài tenant condition, không bỏ tenant filter khi tenant vắng, và không dùng một kết quả null làm đại diện cho điều kiện tenant bắt buộc.

Query có scope giảm nguy cơ tải dữ liệu ngoài tenant, nhưng request "đang chờ duyệt trong tenant" vẫn có thể do chính checker tạo hoặc vượt thẩm quyền của họ. Nó chưa đủ để cho phép một command duyệt.

### 7.2. Không mặc định predicate trên Java và SQL tương đương

Domain model có thể bắt buộc non-null nhưng dữ liệu cũ trong database vẫn có null. SQL có logic ba giá trị: `NOT NULL` vẫn là unknown thay vì true. Thứ tự đánh giá các toán hạng SQL cũng không được bảo đảm như chuỗi short-circuit Java. [PostgreSQL 18: Logical Operators](https://www.postgresql.org/docs/18/functions-logical.html).

Khi chuyển một rule thành query, cần xác định null, join, timezone, currency, precision và collation tương ứng. Không đặt một hàm SQL có tác động phụ rồi trông đợi tenant predicate sẽ luôn chạy trước nó.

Nếu query chỉ dùng để gợi ý danh sách có thể duyệt, hãy coi kết quả là hint tại thời điểm đọc và kiểm tra lại trong command. Nếu query là ranh giới read authorization, phải bảo vệ cả projection, count, tổng hợp và phân trang theo cùng scope.

Khi hai cách hiện thực được tuyên bố tương đương, dùng cùng bộ trường hợp nghiệp vụ để đối chiếu kết quả. Không vì cùng có tên `Specification` mà suy rằng một lambda Java tự dịch được sang SQL hoặc luôn có cùng ngữ nghĩa.

## 8. Lý do từ chối và audit không nên làm thay đổi kết quả policy

Boolean đủ cho câu hỏi "có thỏa không", nhưng vận hành thường cần biết rule nào đã chặn. Có thể bổ sung kết quả quyết định gồm action, decision ID, rule code và policy version, hoặc dùng cây rule có tên thay vì lambda không có metadata.

| Rule code nội bộ | Ý nghĩa | Thông điệp public có thể dùng |
|---|---|---|
| `TENANT_SCOPE_MISMATCH` | Request không thuộc scope đã xác minh | Không tìm thấy hoặc không được phép theo hợp đồng |
| `APPROVE_GRANT_MISSING` | Không có quyền hành động | Không được phép thực hiện |
| `SAME_PERSON_AS_MAKER` | Không đạt checker độc lập | Không được phép duyệt yêu cầu này |
| `APPROVAL_LIMIT_EXCEEDED` | Vượt thẩm quyền theo giá trị/tiền tệ | Cần người có thẩm quyền phù hợp, nếu caller được biết dữ liệu |
| `CONTENT_VERSION_STALE` | Nội dung không khớp revision đã xem | Cần tải lại dữ liệu, sau khi quyền truy cập đã được xác nhận |
| `APPROVAL_WINDOW_CLOSED` | Hết cửa sổ duyệt | Không thể duyệt ở thời điểm này, nếu được phép tiết lộ |

Không trả toàn bộ điều kiện thất bại cho mọi caller. Danh sách đó có thể tiết lộ tenant, số tiền, maker hoặc trạng thái của một object mà caller không được biết.

### 8.1. Chú ý ngữ nghĩa khi thu thập lý do

Với `A AND B`, một điều kiện sai có thể đủ để từ chối. Với `A OR B`, nhánh A sai chưa phải lý do từ chối tổng nếu B đúng. Nếu triển khai kết quả có lý do, cần giữ cấu trúc cây và ngữ nghĩa kết hợp, không gom mọi leaf sai rồi kết luận deny.

Short-circuit có thể khiến một số rule không được đánh giá. Audit không nên ghi "tất cả rule đều đã chạy" khi thực tế chưa chạy. Nếu cần chẩn đoán sâu cho người vận hành có quyền, có thể đánh giá thêm các rule thuần trên cùng facts sau khi đã xác định quyền truy cập; cân nhắc chi phí và dữ liệu nhạy cảm.

Ghi sự kiện quyết định ở tầng điều phối sau khi có kết quả, không tạo side effect trong từng leaf. Evidence thành công lưu cùng transaction nghiệp vụ khi thiết kế cho phép. Sự kiện từ chối cần cơ chế giữ lại sau rollback nếu muốn truy vết lần tấn công; không trông chờ một bản ghi trong transaction bị rollback vẫn tồn tại.

Nhãn `refund-approval-v1` trong pseudocode là version minh họa của logic policy. Triển khai thật cần quản lý version theo thay đổi quy tắc và ghi thêm version/nguồn của grant hoặc cấu hình liên quan nếu cần tái dựng quyết định. Không ghi bearer token, secret hoặc toàn bộ dữ liệu tài chính vào log chỉ để giải thích một boolean.

## 9. Các giới hạn của pattern trong workflow thực tế

### 9.1. Idempotency là một giao thức cập nhật, không chỉ là predicate

Một rule `NotProcessedYet` đọc thấy command chưa xử lý có thể trả true cho hai request đồng thời. Specification không tự claim key hay bảo đảm một lệnh chỉ tạo một tác động.

Để hỗ trợ retry, ledger cần scope key phù hợp, ví dụ tenant + actor/delegation scope + action + idempotency key. Key phải gắn fingerprint của command và kết quả tối thiểu; claim key cùng mutation cần cơ chế nhất quán và ràng buộc duy nhất phù hợp. Cùng key nhưng đổi request ID hoặc nội dung command phải được xử lý như xung đột theo hợp đồng.

Nhánh trả kết quả đã lưu vẫn phải xác thực caller và kiểm tra quyền đọc receipt trong scope hiện tại. Không áp nguyên xi rule `PENDING_APPROVAL` cho một lần replay đã hoàn tất, vì lần đầu thành công đã đổi state. Tách quyền truy cập kết quả khỏi điều kiện tạo transition mới; cả hai đều có kiểm soát rõ.

Nếu phát lệnh tới provider, cần deduplicate và đối soát riêng khi delivery lặp hoặc timeout không rõ kết quả. `mayApprove == true` không có nghĩa provider chỉ nhận một lệnh, và transaction database không tự rollback được chuyển tiền bên ngoài.

### 9.2. Tái sử dụng có chủ đích giữa các hành động

`SameTenant` có thể dùng lại khi đọc, sửa, hủy hoặc duyệt. Policy tổng cho từng action vẫn khác nhau. Người được hủy một bản nháp không mặc nhiên được duyệt; người được duyệt không mặc nhiên được đổi giá hay người nhận.

Một state machine có thể khai báo các transition `DRAFT → PENDING_APPROVAL → APPROVED`. Mỗi transition xác định actor, input hợp lệ và guard riêng. Specification diễn đạt điều kiện của transition; nó không thay thế việc aggregate hạn chế các transition không tồn tại, như nhảy thẳng từ DRAFT sang APPROVED.

Mọi entry point như HTTP, batch và consumer phải đi qua use case hoặc cơ chế cưỡng chế tương đương. Consumer cần principal máy/ủy quyền được xác minh; không tự dựng actor đặc quyền từ JSON và không bỏ kiểm tra vì lệnh được gọi là "nội bộ".

### 9.3. Chính sách cấu hình động cần giữ ranh giới bắt buộc

Nếu rule được lắp từ JSON hoặc màn hình quản trị, hệ thống cần kiểm soát ai được thay rule, điều gì được thay, version, phê duyệt và cách rollback cấu hình. Cho phép sửa tham số hạn mức không đồng nghĩa cho phép xóa tenant guard.

Chỉ chấp nhận loại rule/toán tử/field đã định nghĩa; giới hạn độ sâu, số node và chi phí. Rule không nhận diện hoặc cấu hình thiếu không được âm thầm bỏ qua. Không thực thi chuỗi biểu thức tùy ý do client gửi như mã đặc quyền.

Có thể tách phần bắt buộc do hệ thống sở hữu khỏi phần cấu hình được phép thay đổi:

~~~text
policy = mandatoryTenantAndIdentityRules
         AND configuredEligibility
         AND mandatoryTransitionRules
~~~

Cấu hình eligibility cũng cần policy action rõ ràng. Một nhánh OR do người quản trị tenant chọn không được phủ lên toàn bộ root để vô hiệu hóa các phần bắt buộc.

### 9.4. Cache và hiệu năng phải giữ đúng facts

Cache một boolean theo `requestId` có thể tái sử dụng kết quả của checker khác hoặc revision khác. Nếu phải cache quyết định, khóa và thời hạn hiệu lực cần phản ánh actor/tenant, action, request/version, grant/policy version và thời điểm hết hạn liên quan; đồng thời có cơ chế vô hiệu hóa hoặc giới hạn độ cũ được chấp nhận.

Thường dễ kiểm soát hơn khi cache dữ liệu tham chiếu có version và vẫn đánh giá lại các guard nhạy cảm tại mutation. Với danh sách lớn, tải facts cần thiết theo lô thay vì để từng specification truy vấn database gây N+1. Lọc ở query có thể giảm dữ liệu, nhưng không thay việc đánh giá command trên dữ liệu có tính nhất quán phù hợp.

## 10. Kiểm thử từ quy tắc tới tác động bền vững

### 10.1. Ma trận tình huống cần bao phủ

| Tình huống | Kỳ vọng |
|---|---|
| Checker khác maker, đúng tenant, đủ quyền, đúng version, còn hạn | Đạt policy của mẫu |
| Có permission nhưng request tenant khác | Từ chối dù các điều kiện khác đúng |
| Cùng tenant nhưng membership đã bị thu hồi | Áp dụng đúng hợp đồng hiệu lực quyền, không dùng cờ client để bật lại |
| Maker dùng account thứ hai cùng person identity | Không đạt checker độc lập |
| Số tiền bằng hạn mức / lớn hơn hạn mức một đơn vị nhỏ nhất | Trường hợp đầu đạt, trường hợp sau bị chặn nếu các rule khác đúng |
| Số tiền có currency khác hạn mức | Không so sánh như cùng đơn vị và không cấp quyền theo mẫu |
| Client sửa `approvalLimit`, `makerId` hoặc giá trong body | Không làm thay đổi facts có thẩm quyền |
| Version nội dung đã cũ dù caller có permission | Không duyệt revision mới bằng quyết định cũ |
| Request không ở trạng thái chờ duyệt | Không tạo transition duyệt |
| Thời điểm trước deadline / đúng deadline / sau deadline | Chỉ trường hợp trước deadline có thể đạt rule thời gian của mẫu |
| Supervisor ngoài tenant trong policy có OR | Tenant bắt buộc vẫn từ chối |
| Lỗi tải membership/policy hoặc facts bắt buộc vắng | Không tạo approval và không biến lỗi thành allow qua NOT |
| Hai transaction kiểm tra cùng một version | Không commit hai transition trái bất biến |
| Hai request cùng tiêu phần hạn mức tổng cuối | Cơ chế đồng thời bảo vệ tổng, không chỉ từng request |
| Replay key từ actor khác hoặc fingerprint khác | Không đọc kết quả riêng tư và không tạo tác động mới trái hợp đồng |
| Gọi qua batch/consumer thay cho API | Không bỏ qua cùng policy và guard tương ứng |

### 10.2. Ví dụ unit test cho policy thuần

Các test sau dùng JUnit Jupiter và những kiểu ở phần 3–5. UUID cố định chỉ là dữ liệu fixture. Bộ test nhỏ này kiểm tra vài biên có ý nghĩa nghiệp vụ; không thay thế toàn bộ ma trận hoặc kiểm thử transaction.

~~~java
import java.time.Instant;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApprovalSpecsTest {
    private static final UUID TENANT_A = new UUID(0, 1);
    private static final UUID TENANT_B = new UUID(0, 2);
    private static final UUID MAKER = new UUID(0, 3);
    private static final UUID CHECKER = new UUID(0, 4);
    private static final UUID REQUEST = new UUID(0, 5);
    private static final Instant NOW = Instant.parse("2026-11-23T03:00:00Z");
    private static final Instant DEADLINE = NOW.plusSeconds(60);

    private ActorFacts actor(UUID tenant, UUID person, long limit) {
        return new ActorFacts(person, tenant, true,
                Set.of("refund.approve"), limit, "VND");
    }

    private RefundFacts refund(long amount) {
        return new RefundFacts(REQUEST, TENANT_A, MAKER,
                "PENDING_APPROVAL", 4, 7, amount, "VND", DEADLINE);
    }

    private boolean allowed(ActorFacts actor, RefundFacts refund,
            long expectedRow, long reviewedContent, Instant at) {
        return ApprovalSpecs.mayApprove().isSatisfiedBy(
                new ApprovalContext(actor, refund,
                        expectedRow, reviewedContent, at));
    }

    @Test
    void amountAtLimitIsAllowedButOneUnitOverIsDenied() {
        var checker = actor(TENANT_A, CHECKER, 5_000);
        assertTrue(allowed(checker, refund(5_000), 4, 7, NOW));
        assertFalse(allowed(checker, refund(5_001), 4, 7, NOW));
    }

    @Test
    void permissionDoesNotAllowCrossTenantApproval() {
        var foreignChecker = actor(TENANT_B, CHECKER, 5_000);
        assertFalse(allowed(foreignChecker, refund(5_000), 4, 7, NOW));
    }

    @Test
    void makerCannotApproveEvenWithGrantAndLimit() {
        var makerWithGrant = actor(TENANT_A, MAKER, 5_000);
        assertFalse(allowed(makerWithGrant, refund(5_000), 4, 7, NOW));
    }

    @Test
    void staleRowOrContentVersionIsDenied() {
        var checker = actor(TENANT_A, CHECKER, 5_000);
        assertFalse(allowed(checker, refund(5_000), 3, 7, NOW));
        assertFalse(allowed(checker, refund(5_000), 4, 6, NOW));
    }

    @Test
    void deadlineIsExclusive() {
        var checker = actor(TENANT_A, CHECKER, 5_000);
        assertTrue(allowed(checker, refund(5_000), 4, 7, NOW));
        assertFalse(allowed(checker, refund(5_000), 4, 7, DEADLINE));
        assertFalse(allowed(checker, refund(5_000), 4, 7,
                DEADLINE.plusSeconds(1)));
    }
}
~~~

Nếu policy có thêm nhánh supervisor/assignment, bổ sung tổ hợp đủ để chứng minh một nhánh ngoại lệ không vượt điều kiện tenant hoặc checker độc lập. Không chỉ thêm happy path cho role mới.

### 10.3. Kiểm thử ranh giới tích hợp

Unit test boolean không chứng minh application service đã dùng rule, repository có lock hay rollback có hiệu lực. Cần kiểm thử đường gọi thật với dữ liệu thật phù hợp môi trường test:

1. Gửi command không có quyền và xác minh state/version, approval, outbox và tác động ngoài không thay đổi trái hợp đồng.
2. Đổi dữ liệu giữa hai bước có điều phối để kiểm tra conditional write/lock; hai lần gọi tuần tự không đại diện cho một race.
3. Làm save hoặc evidence thất bại và đọc lại bằng transaction/connection mới để quan sát kết quả sau rollback.
4. Kiểm tra cả HTTP, batch và consumer để phát hiện đường bỏ qua policy.
5. Với read query có scope, kiểm tra cả item lẫn count/tổng hợp/phân trang, đặc biệt khi thêm join hoặc filter OR.

Một ca từ chối có thể tạo security event được thiết kế trước, nhưng không được tạo approval thành công hoặc lệnh chuyển tiền ngoài ý muốn. Chỉ kiểm tra status HTTP hay exception class chưa đủ để chứng minh điều đó.

Các đoạn mã là ví dụ phục vụ bài học; chúng chưa được biên dịch hoặc chạy trong một dự án ứng dụng cụ thể ở bước biên soạn này.

## 11. Bài thực hành: hoàn thiện policy duyệt theo chi nhánh

Mở rộng tình huống: checker chỉ được duyệt request trong chi nhánh được phân công; supervisor có thể duyệt mọi chi nhánh **trong tenant của mình**. Cả hai vẫn phải khác maker, nằm trong hạn mức và duyệt đúng revision đang chờ.

1. Xác định facts cần thêm, nguồn có thẩm quyền và cách ràng buộc branch assignment với tenant. Không lấy danh sách chi nhánh được phép trực tiếp từ body.
2. Viết biểu thức logic trên giấy. Tách rõ điều kiện bắt buộc và nhánh lựa chọn giữa checker được phân công với supervisor.
3. Đặt tên các leaf và tạo policy tổng. Giữ kiểm tra state/version, snapshot và thời gian cho mọi nhánh có thể cho phép.
4. Mô tả transaction/version/lock bảo vệ quyết định đến write; nêu riêng cách xử lý thu hồi phân công đồng thời.
5. Viết ca supervisor ngoài tenant, checker đúng tenant nhưng sai chi nhánh, maker có role supervisor, sửa người nhận sau khi mở màn hình và hai lần duyệt đồng thời.
6. Thiết kế kết quả từ chối public cùng bằng chứng nội bộ, đồng thời chỉ ra nhánh replay được kiểm tra quyền đọc receipt như thế nào.

Sản phẩm cần có là biểu thức chính sách, facts có nguồn rõ ràng, nơi cưỡng chế trong use case và các kiểm tra tác động có thể quan sát. Khi đánh giá một thiết kế Specification, hãy kiểm tra đủ ba điểm: **điều kiện đúng, dữ liệu đánh giá đúng, và kết quả được sử dụng đúng lúc trước tác động**.
