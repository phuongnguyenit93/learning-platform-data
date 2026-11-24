# Application service enforcement — Thực thi bảo vệ nghiệp vụ tại application service

## 1. Mục tiêu và phạm vi

Trong chương **Spring Security Integration**, application service là nơi điều phối một ca sử dụng như duyệt yêu cầu mua hàng, xác nhận hoàn tiền hoặc đổi giá bán. **Enforcement** nghĩa là các điều kiện bảo vệ được thực sự kiểm tra trên đường thực thi trước khi hành động tạo ra tác dụng nghiệp vụ.

Một hệ thống có thể xác thực đúng người dùng và bảo vệ đúng URL nhưng vẫn cho phép bỏ qua phê duyệt, sửa số tiền hoặc thực hiện lệnh trùng. Nguyên nhân thường nằm ở chỗ quy tắc chỉ được đặt trong giao diện, controller hoặc một helper không phải mọi đường gọi đều đi qua.

Bài học giúp người học:

- Đặt một ranh giới thực thi cho các lệnh thay đổi nghiệp vụ.
- Kết hợp Spring method security với quyền trên đối tượng và bất biến của domain.
- Lấy actor từ nguồn xác thực tin cậy, không nhận người thực hiện từ DTO.
- Gắn kiểm tra trạng thái, revision và chống lặp với transaction phù hợp.
- Nhận diện đường bỏ qua proxy, tác vụ nền và lỗi kiểm tra sau khi đã ghi dữ liệu.
- Kiểm thử việc từ chối bằng trạng thái dữ liệu và tác dụng phụ thực tế.

Ví dụ dùng Java 17+, Spring MVC/Servlet, Spring Security với API tham chiếu nhánh 7.0 và transaction đồng bộ trên một database quan hệ. Đây là thiết kế minh họa, không phải project có thể chạy ngay: các port persistence, authentication, policy và fixture kiểm thử phải được triển khai theo hợp đồng được nêu trong bài. Với ứng dụng reactive, cần thiết kế context và transaction theo mô hình reactive tương ứng.

## 2. Lỗ hổng khi chỉ bảo vệ controller

Giả sử ứng dụng có quy tắc: người tạo yêu cầu mua hàng không được tự duyệt; người duyệt phải có quyền trong đúng tenant và đúng đơn vị; chỉ revision đang ở trạng thái `SUBMITTED` được duyệt.

Một cách tổ chức dễ sai:

```java
// Ví dụ không an toàn: chỉ controller này thực hiện kiểm tra.
@PostMapping("/purchase-requests/{id}/approve")
public void approve(@PathVariable UUID id) {
    controllerPermissionCheck.requireApprover(id);
    purchaseService.markApproved(id);
}
```

Nếu `markApproved` chỉ cập nhật trạng thái, một consumer hoặc endpoint quản trị khác có thể gọi nó mà không qua `controllerPermissionCheck`. Quyền trên URL ban đầu không bảo vệ lời gọi Java này.

| Đường gọi | Điều kiện dễ bị bỏ quên |
| --- | --- |
| REST controller thông thường | Kiểm tra quyền theo đối tượng, không chỉ quyền truy cập URL |
| Endpoint quản trị | Không tự miễn quy tắc không tự duyệt chỉ vì có role quản trị |
| Consumer hoặc batch | Service identity, tenant và điều kiện thực thi lệnh đã được chấp nhận |
| Import dữ liệu | Không cho trạng thái hoặc giá từ file đi thẳng vào entity |
| Một service khác trong JVM | Không gọi repository để thay thế ca sử dụng đã được bảo vệ |
| Retry hoặc replay | Không tạo quyết định và sự kiện nghiệp vụ thêm lần nữa |

Mục tiêu là mọi đường thay đổi cùng một hành vi nghiệp vụ đều đi qua ca sử dụng được bảo vệ, hoặc một ca sử dụng riêng có policy rõ ràng. Không tạo phương thức `approveWithoutValidation` để thuận tiện cho caller nội bộ.

## 3. Chia trách nhiệm giữa các lớp

```text
HTTP / message / scheduler adapter
    -> xác minh nguồn gọi, chuyển input thành command
    -> application service qua Spring bean được quản lý
        -> method security: điều kiện truy cập thao tác
        -> actor tin cậy + đối tượng trong tenant
        -> quyền hiện tại trên đối tượng
        -> idempotency + revision + quy tắc chuyển trạng thái
        -> ghi thay đổi, kết quả lệnh, audit và outbox
    -> commit
    -> trả kết quả / xử lý outbox theo hợp đồng
```

| Thành phần | Trách nhiệm chính | Không đủ để thay thế |
| --- | --- | --- |
| HTTP security/filter | Xác thực, bảo vệ đường request theo cấu hình | Quyền trên từng đối tượng và workflow |
| Controller/inbound adapter | Định dạng input, mapping DTO, response và lỗi | Điều kiện nghiệp vụ dùng chung cho mọi caller |
| Method security | Quyền truy cập thao tác tại bean/method | Nhất quán dữ liệu thay đổi đồng thời |
| Application service | Điều phối identity, policy, domain và transaction | Mọi bất biến cục bộ bên trong domain |
| Domain model | Chuyển trạng thái hợp lệ, không tự duyệt, ràng buộc nội dung | Xác minh credential hoặc quyết định tenant từ request |
| Persistence/database | Ghi có điều kiện, khóa, constraint và atomicity | Toàn bộ policy nghiệp vụ của actor |

Application service là ranh giới kiến trúc trong code tin cậy; nó không phải sandbox chống mọi code tùy ý chạy trong cùng JVM. Nếu một module vẫn có thể dùng repository để sửa thẳng cột trạng thái, cần xử lý cả dependency và quyền ghi dữ liệu của module đó.

## 4. Hợp đồng command và danh tính

### 4.1. Client gửi ý định, server xác định actor và dữ liệu có thẩm quyền

Request duyệt chỉ cần chỉ ra đối tượng, revision người dùng đã xem và key chống lặp:

```json
{
  "expectedRevisionId": "9b697edf-45b8-4e66-a968-60f215b60a86",
  "idempotencyKey": "approve-2026-001"
}
```

`requestId` có thể nằm trong đường dẫn. Không dùng `approverId`, `tenantId`, `approved=true`, role hoặc giá trong body làm nguồn có thẩm quyền để thực thi duyệt. Một API có thể từ chối hoặc bỏ qua field không biết; điều bắt buộc là chúng không thể thay actor, tenant được phép hoặc giá trị nghiệp vụ đã lưu.

Spring Security lưu `Authentication` trong `SecurityContext`; trong mô hình Servlet mặc định, context gắn với thread. Application adapter ánh xạ principal đã xác minh sang actor nội bộ theo hợp đồng authentication của ứng dụng. [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html).

Các kiểu public dưới đây được đặt trong những file Java riêng khi triển khai; bài không yêu cầu ghép tất cả vào một file:

```java
import java.util.Objects;
import java.util.UUID;

public record Actor(UUID accountId, UUID tenantId) {
    public Actor {
        Objects.requireNonNull(accountId);
        Objects.requireNonNull(tenantId);
    }
}
```

```java
public interface CurrentActor {
    Actor require();
}
```

`CurrentActor.require()` phải từ chối context thiếu, anonymous hoặc principal không hỗ trợ. Actor dùng ID nội bộ ổn định; tenant là phạm vi đã được lựa chọn và xác minh, không phải một header được tin trực tiếp. Việc account và membership còn hiệu lực được kiểm tra thêm trong policy của ca sử dụng.

### 4.2. Dữ liệu đầu vào và dữ liệu chống lặp

```java
import java.util.Objects;
import java.util.UUID;

public record ApprovePurchaseCommand(
        UUID requestId,
        UUID expectedRevisionId,
        String idempotencyKey) {

    public ApprovePurchaseCommand {
        Objects.requireNonNull(requestId);
        Objects.requireNonNull(expectedRevisionId);
        if (idempotencyKey == null
                || idempotencyKey.isBlank()
                || idempotencyKey.length() > 128) {
            throw new IllegalArgumentException("Invalid idempotency key");
        }
    }
}
```

Validation hình dạng không chứng minh quyền hoặc trạng thái. Chuỗi key trong ví dụ được so sánh chính xác theo hợp đồng lưu trữ; không tự đổi chữ hoa/thường hoặc trim ở một lớp nhưng giữ nguyên ở lớp khác.

Các record hỗ trợ có dạng:

```java
// Mỗi public record là một file riêng; imports được lược ở khối minh họa.
public record ApprovalIntent(UUID expectedRevisionId) {}

public record CommandScope(
        UUID tenantId,
        UUID actorId,
        String action,
        UUID objectId,
        String idempotencyKey) {}

public record ApprovalResult(
        UUID requestId,
        UUID revisionId,
        UUID approvedBy,
        Instant approvedAt) {}

public record StoredApproval(
        ApprovalIntent intent,
        ApprovalResult result) {}
```

Trong ví dụ, scope của key gồm tenant, actor, action và đối tượng. Hai đối tượng khác nhau được phép dùng cùng chuỗi key theo hợp đồng này. `ApprovalIntent` chứa toàn bộ dữ liệu đầu vào ảnh hưởng đến ý định duyệt ở API hiện tại; nếu bổ sung quyết định, lý do có tác dụng nghiệp vụ hoặc tham số khác, phải mở rộng dữ liệu so sánh chống lặp tương ứng.

## 5. Bật method security và transaction thực sự

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement
public class ApplicationEnforcementConfiguration {
}
```

`@EnableMethodSecurity` kích hoạt bảo vệ method như `@PreAuthorize` trên Spring-managed bean. Chỉ thêm Spring Boot Security Starter không tự bật method security. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html).

Transaction cần transaction manager phù hợp với persistence đang dùng. Cấu hình trên chưa tự tạo datasource hoặc transaction manager; với Spring Boot, cần kiểm tra cấu hình thực tế đã cung cấp chúng. [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

HTTP filter chain và cơ chế authentication vẫn phải được cấu hình theo kiểu session, bearer token hoặc cơ chế đã chọn. Method security không làm mất nhu cầu bảo vệ request, CSRF khi áp dụng, hay xác minh token.

## 6. Application service điều phối lệnh duyệt

### 6.1. Luồng thực thi

Ví dụ chọn khóa bi quan trên chính yêu cầu mua hàng để tuần tự hóa các lệnh thay đổi cùng đối tượng. Mọi đường chỉnh sửa, hủy hoặc duyệt đối tượng phải tuân theo cùng giao thức khóa, hoặc dùng cơ chế ghi có điều kiện tương đương.

```java
import java.time.Clock;
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseApprovalService {
    private final CurrentActor currentActor;
    private final PurchaseRequests requests;
    private final ApprovalAccess approvalAccess;
    private final ApprovalCommandLog commandLog;
    private final ApprovalAudit audit;
    private final ApprovalOutbox outbox;
    private final Clock clock;

    public PurchaseApprovalService(
            CurrentActor currentActor,
            PurchaseRequests requests,
            ApprovalAccess approvalAccess,
            ApprovalCommandLog commandLog,
            ApprovalAudit audit,
            ApprovalOutbox outbox,
            Clock clock) {
        this.currentActor = currentActor;
        this.requests = requests;
        this.approvalAccess = approvalAccess;
        this.commandLog = commandLog;
        this.audit = audit;
        this.outbox = outbox;
        this.clock = clock;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('PURCHASE_APPROVE')")
    @Transactional
    public ApprovalResult approve(ApprovePurchaseCommand command) {
        Actor actor = currentActor.require();

        PurchaseRequest request = requests
            .findForUpdate(actor.tenantId(), command.requestId())
            .orElseThrow(() -> new AccessDeniedException(
                "Purchase request is not accessible"
            ));

        approvalAccess.requireCurrentPermission(actor, request);

        CommandScope scope = new CommandScope(
            actor.tenantId(),
            actor.accountId(),
            "APPROVE_PURCHASE",
            request.id(),
            command.idempotencyKey()
        );
        ApprovalIntent intent =
            new ApprovalIntent(command.expectedRevisionId());

        StoredApproval completed = commandLog.findCompleted(scope)
            .orElse(null);
        if (completed != null) {
            if (!completed.intent().equals(intent)) {
                throw new IdempotencyConflict();
            }
            return completed.result();
        }

        request.approve(
            actor.accountId(),
            command.expectedRevisionId(),
            clock.instant()
        );
        requests.save(request);

        ApprovalResult result = new ApprovalResult(
            request.id(),
            request.revisionId(),
            request.approvedBy(),
            request.approvedAt()
        );

        commandLog.saveCompleted(scope, intent, result);
        audit.appendSuccess(actor, result);
        outbox.appendPurchaseApproved(
            UUID.randomUUID(), actor.tenantId(), result
        );
        return result;
    }
}
```

### 6.2. Hợp đồng bắt buộc của các port

| Port/kiểu | Hợp đồng trong ví dụ |
| --- | --- |
| `PurchaseRequests.findForUpdate(tenantId, id)` | Trả `Optional<PurchaseRequest>`; đọc đúng tenant và giữ khóa ghi đối tượng tới hết transaction |
| `PurchaseRequests.save(request)` | Lưu qua cùng transaction; không có commit riêng trước các bước còn lại |
| `ApprovalAccess.requireCurrentPermission(actor, request)` | Từ chối nếu account/membership không hoạt động hoặc không có quyền duyệt đối tượng, đơn vị và mức tiền tương ứng |
| `ApprovalCommandLog.findCompleted(scope)` | Trả `Optional<StoredApproval>` từ dữ liệu đã lưu nhất quán với transaction |
| `ApprovalCommandLog.saveCompleted(scope, intent, result)` | Ghi kết quả lệnh với unique constraint trên toàn bộ scope |
| `ApprovalAudit.appendSuccess(actor, result)` | Ghi audit thành công trong cùng database/transaction của ví dụ |
| `ApprovalOutbox.appendPurchaseApproved(eventId, tenantId, result)` | Chỉ ghi outbox bền vững trong transaction, chưa gọi dịch vụ ngoài |
| `IdempotencyConflict` | Exception nghiệp vụ kế thừa `RuntimeException`, biểu thị cùng key nhưng khác ý định |
| `Clock` | Bean thời gian do server quản lý, giúp kiểm thử thời điểm duyệt |

`ApprovalAccess` kiểm tra entitlement và quyền trên đối tượng, không yêu cầu đối tượng còn ở `SUBMITTED`. Trạng thái và revision được domain kiểm tra cho một lệnh mới. Việc tách này cho phép replay lệnh đã commit trả kết quả cũ sau khi kiểm tra quyền hiện tại, dù đối tượng đã là `APPROVED`.

Authority trong annotation là điều kiện truy cập thao tác ở lớp ngoài. Policy trong body vẫn kiểm tra quyền hiện tại từ dữ liệu có thẩm quyền; một authority có trong session/token cũ không thay thế được membership hoặc hạn mức đã thay đổi.

## 7. Domain giữ bất biến của quyết định phê duyệt

### 7.1. Không biến application service thành tập hợp các setter

Application service gọi một hành vi có ý nghĩa, thay vì gọi `setStatus(APPROVED)` và `setApprovedBy(...)` tùy ý. Domain có thể giữ phần quy tắc không phụ thuộc Spring:

```java
// Phương thức bên trong PurchaseRequest.
// id, tenantId, requesterId là dữ liệu đã lưu;
// state, revisionId, approvedBy, approvedAt là trạng thái của aggregate.
public void approve(
        UUID actorId,
        UUID expectedRevisionId,
        Instant now) {
    if (requesterId.equals(actorId)) {
        throw new ApprovalRuleViolation("SELF_APPROVAL_FORBIDDEN");
    }
    if (!revisionId.equals(expectedRevisionId)) {
        throw new ApprovalRuleViolation("STALE_REVISION");
    }
    if (state != PurchaseState.SUBMITTED) {
        throw new ApprovalRuleViolation("INVALID_APPROVAL_STATE");
    }

    state = PurchaseState.APPROVED;
    approvedBy = actorId;
    approvedAt = now;
}
```

`PurchaseState` là enum trạng thái của domain; `ApprovalRuleViolation` là exception nghiệp vụ kế thừa `RuntimeException`, mang reason code tương ứng. Các getter được service sử dụng trả dữ liệu của aggregate đã được nạp. Đoạn code trên minh họa hành vi duyệt, không phải toàn bộ entity hoặc mapping ORM.

Exception tối thiểu cho ví dụ và các assertion reason code ở phần kiểm thử:

```java
public final class ApprovalRuleViolation extends RuntimeException {
    public ApprovalRuleViolation(String reasonCode) {
        super(reasonCode);
    }
}
```

Mô hình này giả định một quyết định duyệt cho mỗi revision. Workflow nhiều cấp phải mô hình hóa từng bước, người được phép duyệt ở bước đó và điều kiện hoàn tất; không dùng một boolean `approved` để thay toàn bộ state machine.

### 7.2. Revision gắn quyết định với đúng nội dung

Revision nghiệp vụ phải đại diện cho nội dung cần duyệt: mặt hàng, giá, số lượng, tiền tệ, đơn vị hưởng lợi và các thuộc tính liên quan. Mọi chỉnh sửa làm thay đổi nội dung đó cần tạo revision mới và xử lý lại trạng thái/phê duyệt theo policy.

Ví dụ Carol đã xem yêu cầu 5 triệu đồng ở revision R1. Alice sửa thành 50 triệu đồng trước khi Carol bấm duyệt. Lệnh mang `expectedRevisionId=R1` phải thất bại nếu đối tượng hiện tại là R2; việc Carol có role duyệt không cho phép hệ thống tự hiểu Carol đã chấp thuận R2.

Không nhầm revision nghiệp vụ với cột version kỹ thuật của ORM. Một số thay đổi kỹ thuật có thể không làm đổi nội dung được duyệt; ngược lại, một lệnh sửa nội dung phải thực sự cập nhật revision theo hợp đồng, không chỉ dựa vào giao diện.

### 7.3. Giá và hạn mức lấy từ nguồn có thẩm quyền

`ApprovalAccess` đánh giá hạn mức dựa trên số tiền và tiền tệ đã lưu trong đối tượng đang được bảo vệ. Không kiểm tra `amount` thấp do client gửi rồi cập nhật một yêu cầu có tổng tiền cao hơn.

Nếu số tiền phụ thuộc giá sản phẩm hiện hành, cần xác định đang duyệt snapshot giá đã chốt hay một báo giá có phiên bản. Không vừa hiển thị giá A cho người duyệt vừa lấy giá B ở thời điểm ghi mà không thay revision hoặc yêu cầu xác nhận lại.

Các điều kiện này vẫn bắt buộc khi caller là admin, batch hoặc consumer. Quy trình override phải là hành vi riêng có quyền, lý do và audit, không phải nhánh `if admin then skipAllRules`.

## 8. Quyền trên đối tượng phải đi cùng tính nhất quán

### 8.1. Tenant và ID đối tượng không độc lập

Truy vấn `findForUpdate(actor.tenantId(), requestId)` buộc scope tenant tham gia việc lấy đối tượng. Quyền còn phải xem actor có được duyệt đơn vị, nhóm hoặc yêu cầu cụ thể đó hay không. Hai người cùng tenant không mặc nhiên có cùng quyền trên mọi đối tượng.

Không lấy đối tượng toàn cục theo ID, thay tenant trong entity bằng tenant của actor rồi lưu. Cách đó có thể biến việc giả ID thành chuyển dữ liệu giữa tenant.

Đối tượng ngoài quyền và đối tượng không tồn tại có thể được ánh xạ ra cùng response theo chính sách không tiết lộ. Trong ví dụ, ứng dụng từ chối trước khi đọc command log hoặc tạo tác dụng nghiệp vụ cho đối tượng đó.

### 8.2. Đọc lại quyền không tự loại bỏ race với thu hồi quyền

Một transaction có thể đọc membership còn hoạt động, trong khi transaction khác đang thu hồi membership đó. Chỉ thêm `@Transactional` không tự tạo một cam kết rằng mọi quyết định dựa trên membership sẽ được sắp thứ tự với thao tác thu hồi.

Cần định nghĩa điểm có hiệu lực của policy:

| Cam kết nghiệp vụ | Cách thiết kế cần xem xét |
| --- | --- |
| Chấp nhận snapshot quyền tại một điểm đã định nghĩa | Ghi rõ điểm đánh giá, thời hạn snapshot và hành vi sau thu hồi |
| Thu hồi và duyệt phải có thứ tự nhất quán | Các đường thực thi phối hợp bằng khóa, phiên bản policy hoặc cơ chế serial hóa phù hợp |
| Quyền nằm ở dịch vụ ngoài | Xác định độ mới của quyết định, token quyết định có scope hoặc giao thức phối hợp; transaction local không bao trùm dịch vụ đó |
| Hạn mức dùng chung giữa nhiều đối tượng | Bảo vệ cả tài nguyên hạn mức, không chỉ khóa từng yêu cầu riêng |

Ví dụ bài học giả định port policy được triển khai theo cam kết consistency đã chọn. Khóa trên yêu cầu chỉ giải quyết cạnh tranh trên chính yêu cầu; nó chưa chứng minh việc thu hồi quyền hoặc ngân sách dùng chung là nguyên tử với phê duyệt.

Nếu dùng nhiều khóa, mọi ca sử dụng cần cùng thứ tự lấy khóa và timeout hữu hạn. Thiết kế khóa riêng cho từng method mà không xét các method còn lại có thể tạo deadlock hoặc một đường cập nhật không được bảo vệ.

## 9. Transaction, concurrency và idempotency

### 9.1. Điều gì phải commit cùng nhau?

Trong ví dụ, một lần duyệt mới tạo bốn kết quả bền vững:

1. Đối tượng chuyển sang `APPROVED` với actor và thời điểm do server xác định.
2. Kết quả command được lưu để retry có thể nhận lại kết quả cũ.
3. Audit thành công được ghi.
4. Outbox có sự kiện phê duyệt để xử lý tiếp.

Các ghi này nằm trong cùng local transaction và cùng tài nguyên dữ liệu theo giả định của ví dụ. Nếu ghi command log hoặc outbox sang nơi lưu trữ khác, cần một thiết kế phối hợp riêng; annotation trên service không tự tạo atomicity qua mọi database hoặc broker.

Không trả thành công khi mới ghi status nhưng chưa bảo đảm những dữ liệu bắt buộc còn lại đã commit. Lỗi flush/constraint/commit cũng là lỗi thực thi lệnh, không được chuyển thành response thành công bằng một catch tổng quát.

### 9.2. Vì sao kiểm tra chống lặp nằm trước kiểm tra state của lệnh mới?

Sau lần duyệt đầu tiên, đối tượng đã là `APPROVED`. Nếu retry luôn gọi `request.approve(...)` trước khi tra kết quả cũ, retry hợp lệ sẽ bị coi là sai trạng thái.

Service vì vậy thực hiện theo thứ tự:

```text
actor tin cậy
-> khóa đúng đối tượng trong tenant
-> kiểm tra quyền hiện tại
-> tìm kết quả của scope/key
   -> có, cùng intent: trả kết quả đã lưu
   -> có, khác intent: từ chối xung đột
   -> chưa có: kiểm tra revision và workflow, thực thi một lần
```

Replay trả lại quyết định lịch sử của command, không áp dụng quyết định đó cho một revision mới và không phát sinh thêm audit thành công/outbox nghiệp vụ. Nếu hệ thống cần ghi nhật ký truy cập của lần replay, đó là một loại sự kiện quan sát riêng.

Actor khác không được dùng key cũ để nhận kết quả ngoài quyền: actor nằm trong scope và policy được kiểm tra trước khi trả kết quả. Nếu quyền đã bị thu hồi, endpoint trong ví dụ có thể từ chối replay; cần xác định hợp đồng này với client.

### 9.3. Chống hai request cùng đi qua bước “chưa có”

Thiết kế persistence cần unique constraint tương đương:

```sql
UNIQUE (tenant_id, actor_id, action, object_id, idempotency_key)
```

Các cột thuộc scope phải bắt buộc có giá trị và có quy tắc so sánh key phù hợp. Constraint là hàng rào dữ liệu, không thay cho kiểm tra quyền hoặc so sánh intent.

Trong thiết kế khóa của bài, các lệnh cho cùng đối tượng đợi cùng khóa rồi mới tra command log. Kết hợp với unique constraint và khả năng đọc kết quả đã commit phù hợp của database, retry có thể trả kết quả cũ. Chi tiết isolation và hành vi khi deadlock/serialization failure phải được kiểm thử trên database triển khai.

| Hai lệnh cạnh tranh | Kết quả cần đạt |
| --- | --- |
| Cùng actor, đối tượng, key và intent | Một lần chuyển trạng thái; lệnh còn lại trả kết quả cũ hoặc retry theo hợp đồng lỗi tạm thời |
| Cùng scope/key nhưng khác intent | Một intent được chấp nhận; intent khác bị từ chối |
| Khác key, cùng đối tượng/revision | Một quyết định mới được ghi; lệnh còn lại không được duyệt lần hai |
| Một lệnh sửa và một lệnh duyệt | Quyết định gắn với revision hợp lệ hoặc bị từ chối, không duyệt nhầm nội dung |
| Hai đối tượng dùng cùng ngân sách | Không vượt ngân sách; cần bảo vệ tài nguyên ngân sách chung |

Khóa đối tượng không tạo “exactly once” cho mọi hệ thống bên ngoài. Consumer của outbox vẫn phải chống nhận lặp hoặc dùng idempotency của dịch vụ đích theo hợp đồng.

### 9.4. Nếu chọn optimistic locking

Có thể thay khóa bi quan bằng ghi có điều kiện dựa trên version/state và kiểm tra số row được cập nhật, hoặc cơ chế optimistic locking phù hợp. Khi có xung đột, phải rollback toàn bộ command rồi đánh giá lại từ dữ liệu mới.

Không retry chỉ câu `save` trên entity cũ sau khi authorization và revision đã được kiểm tra với snapshot khác. Nếu retry toàn ca sử dụng, cần giới hạn số lần, bảo toàn command/intent và bảo đảm các lần thất bại chưa tạo tác dụng bên ngoài transaction.

## 10. Đóng các đường bỏ qua proxy và entry point

### 10.1. Annotation không tự bảo vệ mọi lời gọi Java

Spring AOP dùng proxy; self-invocation qua `this` bỏ qua advice. Với proxy dựa trên class, method `final` hoặc `private` không được advice như một public method có thể override. [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

```java
// Ví dụ cần tránh trong thiết kế proxy thông thường.
public void approveFromBatch(ApprovePurchaseCommand command) {
    this.approve(command);
}

@PreAuthorize("hasAuthority('PURCHASE_APPROVE')")
@Transactional
public ApprovalResult approve(ApprovePurchaseCommand command) {
    // Luồng duyệt thực tế.
    return executeApproval(command);
}
```

`approveFromBatch` có thể làm mất interceptor security và transaction đặt ở `approve`. Nếu method ngoài đã có transaction, vẫn không được suy ra interceptor phân quyền của method trong đã chạy.

Một cách tổ chức rõ là tách entry point được bảo vệ thành bean riêng và để các adapter gọi bean đó. Kiểm thử phải dùng bean được inject; `new PurchaseApprovalService(...)` chỉ kiểm tra code thường, không kiểm chứng annotation.

### 10.2. Không để một method khác làm cùng tác dụng với ít điều kiện hơn

Ví dụ các method `updateStatus`, `saveEntity`, `approveAsAdmin` hoặc `importApprovedRequest` có thể vô hiệu hóa ranh giới dù `approve` được bảo vệ tốt. Cần kiểm kê những đường ghi cùng trạng thái, số tiền và approval record.

Các lựa chọn kiến trúc gồm giới hạn dependency tới repository, không cung cấp setter trạng thái tùy ý, chia interface theo use case và kiểm tra dependency giữa module khi phù hợp. Đây là cách giữ các caller đi qua chính sách thực thi đã định nghĩa.

Đường override hoặc sửa dữ liệu vận hành phải có command riêng: ai được làm, với đối tượng nào, bất biến nào vẫn bắt buộc, lý do và bằng chứng nào phải ghi. Quyền “nội bộ” không phải một policy đủ cụ thể.

## 11. Kiểm tra trước tác dụng và hiểu rollback

### 11.1. Không dùng PostAuthorize làm hàng rào duy nhất cho lệnh ghi

`@PostAuthorize` đánh giá biểu thức sau khi method được gọi. [Spring Security — PostAuthorize API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/access/prepost/PostAuthorize.html).

Vì thế, với một lệnh ghi, việc cuối cùng trả lỗi không chứng minh hành động chưa xảy ra. Body có thể đã gửi email, gọi thanh toán hoặc ghi dữ liệu đã commit trước khi bị từ chối. Thiết kế thứ tự advisor và rollback có thể bảo vệ một số ghi local, nhưng không thu hồi được mọi tác dụng đã gửi ra ngoài.

Đặt kiểm tra cho phép hành động trước khi tạo tác dụng. Post-authorization có thể phục vụ bảo vệ kết quả đọc theo thiết kế phù hợp; nó không thay thế việc kiểm tra trước của ca sử dụng thay đổi nghiệp vụ.

### 11.2. Đừng suy ra transaction từ vị trí annotation

Thứ tự viết `@PreAuthorize` và `@Transactional` trong source không quy định thứ tự chạy interceptor. Cần xét advisor order khi phối hợp method security với transaction. [Spring Security — Coordinating with @Transactional](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html).

Một biểu thức security đọc database không mặc nhiên chạy trong cùng transaction/khóa với body. Ví dụ bài học dùng annotation cho điều kiện thao tác, rồi thực hiện kiểm tra quyền đối tượng và domain tại ranh giới dữ liệu trong body.

### 11.3. Không nuốt lỗi rồi commit dở dang

Với cấu hình rollback mặc định, Spring rollback khi exception không được xử lý thuộc `RuntimeException` hoặc `Error`; checked exception cần quy tắc rollback thích hợp. Cấu hình của ứng dụng có thể thay đổi mặc định. [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

Ví dụ trong bài dùng exception nghiệp vụ dạng runtime và để lỗi thoát ra khỏi service. Không catch lỗi policy rồi tiếp tục ghi, hoặc catch lỗi audit/outbox rồi coi duyệt đã thành công nếu hợp đồng đòi hỏi chúng phải tồn tại cùng quyết định.

Nếu lỗi persistence đã khiến transaction không còn khả năng commit, không bắt lỗi unique rồi tiếp tục truy vấn để trả kết quả như thể transaction vẫn bình thường. Có thể rollback và thực hiện một lần đọc/retry mới được bảo vệ, tùy chiến lược persistence.

## 12. Tái sử dụng ca sử dụng từ nhiều loại caller

### 12.1. Controller giữ vai trò chuyển đổi giao thức

Controller dựng `ApprovePurchaseCommand` từ path/body rồi gọi bean `PurchaseApprovalService`; nó không tự gán `approvedBy` hoặc lưu entity sau khi service trả về. Mapping response và lỗi nằm ở adapter.

Không deserialize trực tiếp JSON vào entity chứa trạng thái, giá, tenant và trường approval. Command chỉ mở những tham số mà ca sử dụng cho phép điều khiển.

### 12.2. Consumer và job cần mô hình identity riêng

Job bền vững không được lấy `requesterId` trong payload rồi coi đó là người đang đăng nhập. Cần xác định worker đang thực thi theo mô hình nào:

| Mô hình | Cơ sở cho phép thực thi |
| --- | --- |
| Thực hiện thay đổi do service tự chịu trách nhiệm | Service identity với quyền giới hạn, scope tenant và đối tượng |
| Tiếp tục một quyết định người dùng đã được chấp nhận | Command/approval bền vững, revision, điều kiện tiếp tục và policy đã định nghĩa |
| Hành động thay mặt người dùng | Bằng chứng ủy quyền có thời hạn, phạm vi và quy tắc thu hồi |
| Operator replay | Quyền replay riêng và kiểm tra command/workflow/idempotency |

Service minh họa dùng `CurrentActor` từ context phù hợp cho caller đã có authentication. Nếu worker dùng một đường identity khác, cần inbound adapter và application entry point được thiết kế tương ứng, tái sử dụng policy/domain cần thiết. Không xóa annotation hoặc thêm cờ `skipSecurity=true` để job chạy được.

Thiếu context phải bị từ chối theo hợp đồng, không fallback sang admin/system. Tác vụ trong tiến trình cần truyền/dọn context có kiểm soát; job qua queue cần xác thực producer/consumer và dữ liệu ủy quyền, không serialize nguyên credential hoặc `SecurityContext` để giữ quyền vô thời hạn.

## 13. Audit và outbox phản ánh quyết định đã commit

### 13.1. Actor do server xác định tại điểm hành động

Audit phê duyệt nên có đủ dữ liệu để trả lời ai làm gì với nội dung nào:

```text
tenantId, requestId, revisionId
actorAccountId, actorKind
action, decision, reasonCode
commandReference, policyVersion
recordedAt, correlationId
initiatedBy / executedBy / onBehalfOf khi có ủy quyền
```

Không ghi actor từ `approverId` trong DTO. Với worker, người khởi tạo và service thực thi có thể khác nhau; giữ hai vai trò thay vì ghi như người dùng vừa đăng nhập duyệt lại.

Không log nguyên bearer token, session hoặc credential. Idempotency key là khóa đối chiếu lệnh theo hợp đồng, không phải bằng chứng authentication hoặc một bí mật có thể thay quyền truy cập.

Trong ví dụ, audit thành công commit cùng quyết định. Nếu cần giữ bằng chứng một lần bị từ chối, không dựa duy nhất vào row audit trong chính transaction sẽ rollback. Cần đường telemetry/audit phù hợp cho lần từ chối, với dữ liệu tối thiểu và không phát sinh một approval thành công giả.

### 13.2. Outbox tránh gửi tác dụng trước khi biết kết quả ghi dữ liệu

`appendPurchaseApproved` chỉ ghi một sự kiện có ID bền vững. Sau commit, publisher đọc sự kiện đó để gọi hệ thống tiếp theo. Nếu transaction duyệt rollback, không được còn sự kiện outbox thành công của lần duyệt đó.

Publisher có thể gửi lại cùng event ID sau lỗi mạng hoặc restart; consumer phải nhận diện lần gửi lặp khi tác dụng đích cần chống lặp. Không tạo event ID mới cho mỗi lần retry gửi cùng sự kiện.

Gọi dịch vụ ngoài trực tiếp trong transaction không làm tác dụng đó rollback cùng database. Nếu đã trừ tiền rồi commit local thất bại, ứng dụng cần quy trình đối soát/bù trừ hoặc giao thức thích hợp; không thể giải quyết bằng cách đổi exception thành 500.

Hook sau commit có thể hữu ích cho thông báo theo mức bảo đảm đã chọn, nhưng không tự là hàng đợi bền vững. Với tác dụng bắt buộc không được mất khi process dừng, cần thiết kế lưu bền và retry tương ứng.

## 14. Hợp đồng từ chối và thao tác hàng loạt

### 14.1. Từ chối phải dừng ca sử dụng

| Tình huống | Hành vi cần bảo đảm |
| --- | --- |
| Thiếu identity hoặc anonymous | Không thực thi command; adapter yêu cầu authentication theo giao thức |
| Thiếu authority ở method security | Không chạy body của thao tác được bảo vệ |
| Account/membership/quyền đối tượng không còn hợp lệ | Không tạo approval hoặc phát dữ liệu ngoài quyền |
| Principal hoặc policy không xử lý được | Từ chối an toàn, quan sát lỗi tích hợp; không tự cho phép |
| Tự duyệt | Không chuyển trạng thái; reason code phục vụ kiểm thử/audit theo policy |
| Revision hoặc trạng thái không hợp lệ | Không thay nội dung được duyệt hoặc tự nhảy bước |
| Key cũ với intent khác | Từ chối xung đột, không thay kết quả command đã commit |
| Lỗi persistence/commit | Không báo thành công dở dang; retry theo phân loại lỗi |

Controller/error handler ánh xạ exception thành response API theo hợp đồng: lỗi authentication, không có quyền, không tìm thấy hoặc xung đột nghiệp vụ. Response không nên tiết lộ người sở hữu, số tiền hay trạng thái của một đối tượng ngoài quyền.

Không trả một kết quả “mặc định thành công” khi authorization thất bại. Tương tự, không bắt mọi exception trong application service rồi trả `approved=false` nếu caller có thể hiểu command đã được xử lý hợp lệ và dừng retry dù transaction chưa đạt trạng thái đã cam kết.

### 14.2. Bulk không được tạo lối đi tắt

API duyệt một danh sách phải kiểm tra quyền, tenant, revision và workflow cho từng đối tượng. Role cho phép gọi bulk endpoint không đồng nghĩa mọi ID trong danh sách đều được duyệt.

Cần chọn hợp đồng rõ:

- **Atomic toàn bộ:** chỉ commit khi tất cả đối tượng đạt điều kiện; thứ tự khóa nhất quán để hạn chế deadlock.
- **Kết quả từng phần:** mỗi item có ranh giới transaction, trạng thái kết quả và chống lặp rõ; dữ liệu lỗi vẫn tuân thủ chính sách không tiết lộ.

Không lọc âm thầm các item ngoài quyền rồi báo “duyệt thành công toàn bộ”. Nếu kết quả từng phần được cho phép, response phải phản ánh đúng những hành động đã commit và phạm vi thông tin caller được phép biết.

## 15. Kiểm thử enforcement ở đúng ranh giới

### 15.1. Phân biệt ba loại bằng chứng

| Lớp kiểm thử | Cần chứng minh |
| --- | --- |
| Unit test domain/policy | Quy tắc không tự duyệt, revision, state và quyền theo dữ liệu đầu vào đúng |
| Integration test gọi Spring bean | Method security/proxy, transaction và persistence thực sự có hiệu lực |
| HTTP/message integration test | Authentication, input mapping, context và đường thực thi tới ca sử dụng hoạt động đúng |

Một unit test gọi service được tạo bằng `new` không chứng minh annotation được kích hoạt. Ngược lại, một HTTP test nhận 403 do CSRF thiếu không chứng minh quy tắc không tự duyệt đã chạy.

### 15.2. Test thiếu quyền khi gọi trực tiếp bean

Đoạn sau là method trong một Spring integration test. Harness phải bật method security, có transaction manager phù hợp, inject `PurchaseApprovalService` thật qua proxy và dùng các port mock để quan sát lời gọi. `service` không phải mock; các biến port là những dependency đã đưa vào bean đó.

```java
@Test
@WithMockUser(authorities = "PURCHASE_READ")
void directServiceCallWithoutApproveAuthorityIsRejected() {
    var command = new ApprovePurchaseCommand(
        UUID.randomUUID(),
        UUID.randomUUID(),
        "deny-before-body"
    );

    assertThrows(
        AccessDeniedException.class,
        () -> service.approve(command)
    );

    verifyNoInteractions(
        currentActor,
        requests,
        approvalAccess,
        commandLog,
        audit,
        outbox
    );
}
```

`@WithMockUser` tạo authentication phục vụ test; principal mặc định là Spring Security `User`, không phải principal custom của ứng dụng. [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/test/method.html).

Test trên cố ý bị chặn trước khi gọi `CurrentActor`, nên không cần ánh xạ principal custom. Với test đi vào body, phải tạo principal đúng hợp đồng và actor có account/membership hợp lệ; nếu không, test có thể thất bại sớm ở identity mà không kiểm tra điều mong muốn.

### 15.3. Test không tự duyệt và kiểm tra dữ liệu sau rollback

Harness tiếp theo dùng database kiểm thử, bean thật và fixture đã commit. `securityFixtures.runAs` thiết lập authentication test có principal mà `CurrentActor` hỗ trợ, rồi dọn/khôi phục context trong `finally`. `inspect` đọc dữ liệu đã commit bằng transaction độc lập, không chỉ nhìn entity còn nằm trong persistence context của lần gọi trước.

```java
@Test
void requesterCannotApproveOwnRequestThroughApplicationService() {
    var f = fixtures.committedSubmittedRequestCreatedByAlice();
    var before = inspect.committedBusinessSnapshot(f.requestId());
    var command = new ApprovePurchaseCommand(
        f.requestId(),
        f.revisionId(),
        "alice-self-approval"
    );

    securityFixtures.runAs(
        f.alicePrincipal(),
        "PURCHASE_APPROVE",
        () -> {
            var failure = assertThrows(
                ApprovalRuleViolation.class,
                () -> service.approve(command)
            );
            assertEquals("SELF_APPROVAL_FORBIDDEN", failure.getMessage());
        }
    );

    assertEquals(before, inspect.committedBusinessSnapshot(f.requestId()));
    assertEquals(0, inspect.approvalSuccessAuditCount(f.requestId()));
    assertEquals(0, inspect.approvalOutboxCount(f.requestId()));
    assertEquals(0, inspect.completedApprovalCommandCount(f.requestId()));
}
```

Fixture phải cho Alice có authority và quyền đối tượng hợp lệ theo `ApprovalAccess`, để domain thực sự xét quy tắc không tự duyệt. Bản ghi audit từ chối, nếu có, không phải audit thành công được đếm ở đây.

Đây là mẫu test cần lắp vào harness của dự án; các factory fixture và inspector mô tả trách nhiệm rõ ràng, không phải API có sẵn của Spring. Không dùng transaction bao ngoài test để vô tình che lỗi một đoạn code đã commit riêng; cần quan sát commit/rollback của chính ca sử dụng và cả fake dịch vụ ngoài nếu có.

### 15.4. Ma trận tình huống lạm dụng

| Tình huống | Bằng chứng cần kiểm tra |
| --- | --- |
| Body/header giả `approverId` hoặc tenant | Actor và tenant vẫn từ nguồn server; không duyệt bằng danh tính giả |
| Có authority nhưng đối tượng ngoài tenant/đơn vị | Không đổi dữ liệu; không lộ kết quả command ngoài quyền |
| Account hoặc membership bị khóa | Policy từ chối dù token còn authority cũ |
| Người tạo tự duyệt | Reason code đúng; không có approval, command thành công hoặc outbox mới |
| Sửa giá sau khi người duyệt đã xem | Revision cũ bị từ chối, không duyệt nhầm nội dung mới |
| Đối tượng đã hủy hoặc chưa submit | Không chuyển thẳng sang `APPROVED` |
| Gửi lại cùng scope/key và intent | Kết quả cũ; một tác dụng nghiệp vụ, một sự kiện outbox |
| Cùng scope/key nhưng khác revision | Xung đột idempotency; không đổi kết quả đã lưu |
| Khác actor dùng cùng chuỗi key | Không nhận kết quả thay actor trước; kiểm tra quyền riêng |
| Hai key khác nhau duyệt cùng revision | Không có hai quyết định mới được commit |
| Outbox/audit bắt buộc ghi thất bại | Trạng thái và command thành công cùng rollback |
| Gọi từ controller, consumer, batch | Đi qua entry point có policy; không có method cập nhật tắt |
| Self-invocation hoặc tạo service bằng `new` | Kiến trúc/test phát hiện đường không qua interceptor cần thiết |
| Consumer nhận lại cùng event | Tác dụng đích tuân thủ hợp đồng chống lặp |

### 15.5. Kiểm thử cạnh tranh cần nhiều transaction thật

Với hai lệnh cùng key, fixture được commit trước; mỗi worker test có authentication riêng và gọi bean bằng transaction riêng. Dùng barrier trước khi gọi service để tạo cạnh tranh và timeout hữu hạn, không dùng một khoảng sleep rồi giả định đã xảy ra race.

Sau khi các transaction kết thúc và xử lý retry tạm thời theo hợp đồng, kiểm tra một kết quả duyệt bền vững, một command thành công cho scope, một audit thành công và một outbox nghiệp vụ. Với hai key khác nhau, vẫn chỉ có một lần chuyển trạng thái hợp lệ.

Không đặt barrier sau khi mỗi worker đã giữ cùng một khóa độc quyền: worker đầu có thể chờ worker thứ hai, trong khi worker thứ hai không thể lấy khóa. Cần thiết kế điểm đồng bộ test phù hợp với cơ chế concurrency đang kiểm tra.

Kiểm thử race thu hồi quyền hoặc dùng chung ngân sách phải có hai loại transaction tương ứng và kiểm tra đúng cam kết ở mục 8. Một test duyệt đồng thời trên cùng request không chứng minh được hai bất biến khác đó.

## 16. Bài tập áp dụng

Một hệ thống mua hàng có các đặc điểm sau:

- Controller kiểm tra role `APPROVER`, sau đó gọi `updateStatus(id, "APPROVED")`.
- Body nhận `approverId`, `tenantId` và `approvedAmount` từ client.
- Import CSV gọi thẳng repository để đánh dấu duyệt.
- Service dùng `@PostAuthorize` để kiểm tra người sở hữu sau khi cập nhật.
- Audit được gửi qua HTTP trước khi transaction local commit.
- Khi client retry, hệ thống tạo một command mới và phát sự kiện mới.

Hãy thực hiện lần lượt:

1. Xác định mọi entry point có thể thay đổi trạng thái duyệt và những field cần được bảo vệ.
2. Thiết kế command chỉ chứa ý định cần thiết; chọn nguồn actor, tenant, giá và revision có thẩm quyền.
3. Viết application service phân biệt điều kiện method security, quyền đối tượng và bất biến domain.
4. Chọn ranh giới transaction và chiến lược concurrency; chỉ ra dữ liệu nào chưa được bảo vệ nếu chỉ khóa một yêu cầu.
5. Định nghĩa scope key, intent, kết quả replay và chính sách khi quyền đã bị thu hồi.
6. Chuyển tác dụng ngoài sang thiết kế có bảo đảm giao nhận phù hợp; tách audit thành công và audit từ chối.
7. Xử lý đường import/batch bằng entry point có policy, thay vì thêm cờ bỏ qua kiểm tra.
8. Viết test gọi trực tiếp bean, giả actor, cross-tenant, revision cũ, request trùng và transaction thất bại.

Tiêu chí hoàn thành là mọi đường thực thi được phép tạo cùng tác dụng đều áp dụng policy đã định nghĩa, quyết định gắn với đúng actor và nội dung, và một lần bị từ chối không để lại tác dụng nghiệp vụ trái phép. Bằng chứng phải gồm dữ liệu đã commit và tác dụng ngoài, không chỉ status code hoặc sự hiện diện của annotation.
