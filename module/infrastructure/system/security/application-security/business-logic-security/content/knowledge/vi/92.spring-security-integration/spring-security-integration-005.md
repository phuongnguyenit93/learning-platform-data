# Kiểm tra quyền khi thực hiện giao dịch trong Spring Security (Transaction authorization checks)

Một người có authority `order:confirm` chưa chắc được xác nhận mọi đơn hàng. Đơn có thể thuộc tenant khác, chưa được duyệt, đã bị sửa giá sau khi duyệt hoặc đang có một operation thanh toán. Nếu chỉ kiểm tra role ở controller rồi ghi dữ liệu trong một transaction khác, hệ thống vẫn có thể thực hiện thao tác sai quyền hoặc sai quy tắc nghiệp vụ.

Trong chương **Spring Security Integration** của module Business Logic Security, transaction authorization checks là các kiểm tra cho phép một **ý định nghiệp vụ cụ thể** được chấp nhận thực thi, dựa trên actor, đối tượng, phiên bản dữ liệu, approval, trạng thái và nghĩa vụ đã tồn tại. Spring Security cung cấp authentication và các điểm kiểm soát lời gọi; ứng dụng phải gắn chúng với ranh giới dữ liệu nhất quán và business invariants.

Ví dụ trong bài dùng **Servlet stack, Spring AOP ở proxy mode và Jakarta Persistence/JPA**. Các đoạn Java là mã khung minh họa cách tổ chức; constructor, entity mapping, repository phụ, exception mapping và các helper nghiệp vụ được lược bỏ hoặc mô tả bằng hợp đồng. Chúng chưa phải ứng dụng có thể copy rồi chạy độc lập, và không mô tả transaction reactive của WebFlux.

## 1. Phân biệt quyền chức năng và quyền thực hiện ý định

### 1.1. Ba lớp kiểm tra có nhiệm vụ khác nhau

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Request/endpoint authorization | Caller có được gọi loại chức năng này không? | API xác nhận đơn yêu cầu authentication phù hợp |
| Method authorization | Lời gọi service có đáp ứng điều kiện quyền được công bố không? | `@PreAuthorize("hasAuthority('order:confirm')")` |
| Kiểm tra trong transaction nghiệp vụ | Với dữ liệu authoritative hiện tại, ý định này có được thực hiện không? | Đúng owner/tenant, approval đúng revision, order còn APPROVED, chưa có operation cạnh tranh |

Không lớp nào tự thay cho toàn bộ các lớp còn lại. Kiểm tra trong filter không bao phủ mọi lời gọi từ job hoặc service khác; kiểm tra authority không tự biết giá đã được duyệt hay reservation đang tồn tại.

### 1.2. “Transaction” có hai nghĩa cần tách

- **Business transaction:** xác nhận đơn, hoàn tiền hoặc giải ngân; có thể gồm nhiều bước và hệ thống.
- **Database transaction:** đơn vị commit/rollback của những thay đổi dữ liệu thực sự tham gia transaction đó.

`@Transactional` quản lý ranh giới transaction theo hạ tầng Spring đã cấu hình. Nó không tự xác định ai có quyền, không tự biến cuộc gọi thanh toán thành thay đổi rollback được và không tự bảo đảm invariant khi nhiều request chạy song song.

### 1.3. Quyết định phải gắn với dữ liệu sẽ được ghi

```text
Không đủ:
    đọc order -> kiểm tra owner/approval -> dữ liệu thay đổi -> ghi theo snapshot cũ

Cần chứng minh:
    đọc dữ liệu authoritative theo cơ chế nhất quán
    kiểm tra quyền + approval + state + nghĩa vụ đã có
    chấp nhận đúng chuyển trạng thái/ý định với cơ chế concurrency phù hợp
    commit các thay đổi cục bộ cần đi cùng nhau
```

Đặt code trong transaction mới giải quyết một phần. Isolation, khóa, conditional update và cách các luồng khác cập nhật dữ liệu quyết định kiểm tra có còn đúng tại ranh giới chấp nhận hay không.

## 2. Mô hình xuyên suốt: xác nhận đơn đã được duyệt

Fixture dùng các định danh chuỗi như ORD-A và T1:

- Đơn ORD-A thuộc tenant T1, owner là A.
- A có authority `order:confirm` trong authentication được hệ thống tin cậy thiết lập.
- Order có `contentRevision=7`, trạng thái APPROVED và approval hợp lệ cho revision 7.
- Approver khác maker/owner theo policy của fixture; approval có thời hạn được server kiểm tra.
- Tổng tiền authoritative đã được chấp nhận là 195.000 VND; client không được truyền giá để ghi đè.
- Mỗi order trong luồng mẫu chỉ có một operation xác nhận; thanh toán và retry gắn với operation đó.
- Hệ thống giữ kho và phát PaymentRequested qua outbox sau khi chấp nhận ý định.

Các invariant chính:

```text
TA-01: Chỉ actor có quyền chức năng và quyền trên đúng order/tenant được chấp nhận.
TA-02: Ý định mới phải dùng nội dung đã được duyệt, đúng revision và còn hiệu lực.
TA-03: Không bỏ qua state machine bằng sửa request hoặc dùng đường gọi khác.
TA-04: Operation, reservation, trạng thái order, idempotency và outbox nhất quán cục bộ.
TA-05: Replay không tạo operation hoặc hiệu lực thanh toán thứ hai.
TA-06: Timeout không được diễn giải thành chắc chắn không có hiệu lực ngoài.
```

Nếu hệ thống cho phép nhiều lần xác nhận sau các vòng hủy/tạo lại, cần định nghĩa thêm business cycle/obligation ID và ràng buộc tương ứng. Không dùng uniqueness của fixture để áp vào nghiệp vụ có vòng đời khác.

## 3. Bật method security và giữ nguồn actor đáng tin cậy

### 3.1. Cấu hình tối thiểu của ví dụ

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement
class ApplicationMethodConfiguration {
}
```

Ứng dụng còn cần cấu hình authentication/request security, JPA/DataSource và transaction manager phù hợp. Trong ứng dụng Spring Boot, một phần hạ tầng transaction có thể đã được auto-configuration cung cấp; cần xác minh cấu hình thực tế thay vì tạo nhiều transaction manager không rõ bean nào được dùng.

[Spring Security Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) mô tả việc bật `@EnableMethodSecurity` và lưu ý starter security của Spring Boot không tự bật method authorization. Annotation có trong source không chứng minh advice đã chạy.

### 3.2. Actor lấy từ authentication, không từ request body

```java
record AppPrincipal(String subjectId, String activeTenantId) {}
record Actor(String subjectId, String tenantId) {}

@Component
class ActorResolver {
    Actor requireCurrentActor() {
        var authentication = SecurityContextHolder.getContext()
            .getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof AppPrincipal p)) {
            throw new AccessDeniedException("Unsupported authentication");
        }

        return new Actor(p.subjectId(), p.activeTenantId());
    }
}
```

Các kiểu `Component`, `SecurityContextHolder` và `AccessDeniedException` là API Spring tương ứng; import của các ví dụ sau được lược bỏ khi rõ ngữ cảnh. `AppPrincipal` là principal riêng của ứng dụng, do authentication flow đã xác minh danh tính và tenant context tạo ra; constructor record không tự thực hiện việc xác minh đó.

Không đọc `actorId`, `role=ADMIN` hoặc `tenantId` từ JSON rồi coi chúng là quyền của caller. Header chọn tenant cũng phải được kiểm chứng membership/scope trước khi trở thành active tenant đáng tin cậy.

Authority trong JWT/session có thể là snapshot tại thời điểm cấp. Nếu nghiệp vụ yêu cầu quyền còn hiệu lực ngay tại execution gate, cần nguồn quyền/version hoặc giao thức thu hồi đáp ứng yêu cầu ấy; kiểm tra token còn hạn không tự chứng minh role chưa bị thu hồi.

## 4. Đọc đúng đối tượng trong transaction và kiểm soát concurrency

### 4.1. Repository giới hạn tenant và khóa bản ghi

Ví dụ repository dùng khóa bi quan cho order:

```java
interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, String> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select o from PurchaseOrder o
        where o.tenantId = :tenantId and o.id = :orderId
        """)
    Optional<PurchaseOrder> lockByTenantAndId(
        @Param("tenantId") String tenantId,
        @Param("orderId") String orderId
    );
}
```

`LockModeType` thuộc `jakarta.persistence`; `@Lock`, `@Query`, `@Param` và `JpaRepository` thuộc các package Spring Data thích hợp. `PurchaseOrder` ở đây là tên JPA entity của ví dụ. [Spring Data JPA Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html) mô tả việc gắn lock mode vào query method bằng `@Lock`.

Method này phải được gọi trong transaction phù hợp. Việc khóa và timeout thực tế còn phụ thuộc provider/database. Không nhận entity do controller deserialize rồi dùng luôn để quyết định owner, tenant hoặc approval.

Tenant filter giúp tránh đọc nhầm tenant; owner/object authorization vẫn phải kiểm tra sau khi đọc. Đối tượng không tồn tại hoặc ngoài scope có thể được ánh xạ thành phản hồi không tiết lộ sự tồn tại theo chính sách API.

### 4.2. Khóa order có phạm vi giới hạn

Nếu mọi đường sửa owner/content/state của order cùng tuân thủ giao thức khóa này, request đồng thời không thể thay những trường đó tùy tiện trong khi transaction đang quyết định. Một đường bulk update hoặc script không tuân thủ vẫn có thể phá giả định.

Khóa order không tự khóa các hàng approval/ACL độc lập hoặc tồn kho của SKU dùng chung. Cần các hàng cùng tham gia giao thức, policy revision hoặc cơ chế tương đương. Giữ kho phải có bảo vệ riêng để hai order khác nhau không cùng lấy đơn vị hàng cuối.

### 4.3. Có thể dùng optimistic concurrency, nhưng phải kiểm tra đủ

Một lựa chọn khác là `@Version` hoặc conditional update với điều kiện tenant, state và revision; phải xác minh số hàng cập nhật và xử lý conflict. Chỉ thêm `@Version` không tự bảo vệ tổng nhiều hàng, ACL bên ngoài hoặc invariant không ghi lên hàng được kiểm soát version.

Nếu transaction bị hủy do conflict/deadlock đã xác định, retry phải đọc lại dữ liệu và đánh giá quyền/invariant lại. Nếu kết quả commit chưa rõ, xử lý bằng định danh operation/idempotency, không tự khởi tạo một ý định mới.

## 5. Ví dụ service: guard trong transaction, replay trước kiểm tra trạng thái mới

### 5.1. Command chỉ biểu diễn ý định client được phép gửi

```java
record ConfirmOrderCommand(
    long expectedContentRevision,
    String idempotencyKey
) {}

record ConfirmOrderResult(UUID operationId, String status) {}
```

API kiểm tra định dạng, giới hạn độ dài key và revision theo hợp đồng. Amount, currency, owner, approval status và role không lấy từ command. Các giá trị đó được đọc từ nguồn authoritative đã được ràng buộc với nội dung duyệt.

### 5.2. Service đi qua Spring proxy

```java
@Service
public class OrderConfirmationService {
    // Constructor injection được lược bỏ.
    // Các dependency/helper domain được định nghĩa bằng hợp đồng ở mục 5.3.

    @PreAuthorize("hasAuthority('order:confirm')")
    @Transactional
    public ConfirmOrderResult confirm(
            String orderId, ConfirmOrderCommand command) {

        var actor = actors.requireCurrentActor();
        var order = orders.lockByTenantAndId(actor.tenantId(), orderId)
            .orElseThrow(OrderNotVisibleException::new);

        policy.assertMayAccessConfirmation(actor, order);

        var scope = IdempotencyScope.of(
            actor.tenantId(), actor.subjectId(),
            "ORDER_CONFIRM", command.idempotencyKey()
        );
        var intent = ConfirmIntent.from(orderId, command);
        var previous = idempotency.find(scope);

        if (previous.isPresent()) {
            previous.get().assertSameIntent(intent);
            return results.forExistingOperation(previous.get().operationId());
        }

        policy.assertMayStartConfirmation(
            actor, order, command.expectedContentRevision(), clock.instant()
        );

        var operation = operations.createPendingPayment(order, actor, intent);
        reservations.reserveFromServerOrder(order, operation.id());
        order.markPaymentPending(operation.id());
        idempotency.bind(scope, intent.fingerprint(), operation.id());
        outbox.appendPaymentRequested(operation);
        audit.recordConfirmationAccepted(actor, order, operation);

        return new ConfirmOrderResult(operation.id(), "PENDING_PAYMENT");
    }
}
```

Đây là mã khung: các field dependency được cung cấp qua constructor trong triển khai thực; không có gọi provider trong method. Method cần được gọi qua bean Spring được inject, với transaction manager/JPA context đúng cho các repository dùng chung.

`@PreAuthorize` chặn quyền chức năng trước lời gọi. Các guard theo object và invariant chạy trong thân method khi transaction advice đã mở/join transaction. Thiết kế không dựa vào việc expression bên trong `@PreAuthorize` tự nằm trong cùng database transaction.

### 5.3. Hợp đồng của các helper không được để mơ hồ

| Helper | Hợp đồng bắt buộc trong fixture |
|---|---|
| `assertMayAccessConfirmation` | Kiểm tra tenant/owner và quyền xem/thao tác liên quan trước khi trả bất kỳ replay result nào; không bắt buộc state APPROVED |
| `ConfirmIntent.from` | Chuẩn hóa action, order ID, expected content revision; fingerprint ổn định, không chứa key như một phần của nội dung ý định |
| `assertSameIntent` | Khác fingerprint thì ném conflict, không sửa operation hoặc dùng dữ liệu retry ghi đè |
| `assertMayStartConfirmation` | Kiểm tra state APPROVED, revision mong đợi, approval còn hiệu lực cho nội dung đó, người duyệt hợp lệ và các guard nghiệp vụ khác |
| `createPendingPayment` | Lưu một operation với amount/currency/snapshot server; có ràng buộc tránh operation cạnh tranh cho cùng nghĩa vụ |
| `reserveFromServerOrder` | Giữ số lượng từ order authoritative trong cùng transaction, bảo vệ invariant tồn kho ở đúng các hàng dùng chung |
| `bind` | Lưu ánh xạ scope/key/fingerprint → operation, có uniqueness ở database và cùng transaction với operation |
| `appendPaymentRequested` | Lưu outbox theo operation và snapshot trong transaction hiện tại; chỉ relay dữ liệu đã commit |
| `recordConfirmationAccepted` | Ghi audit chấp nhận trong cùng ranh giới dữ liệu; không công bố thành công của transaction chưa commit |
| `forExistingOperation` | Chỉ trả kết quả thuộc operation đã được ràng buộc đúng ý định/scope, không gọi thanh toán mới |

Nếu approval nằm ở bảng riêng, guard phải đọc/kiểm chứng nó dưới cơ chế concurrency phù hợp. Một helper mở transaction `REQUIRES_NEW` để commit operation rồi quay về transaction ngoài sẽ làm thay đổi bảo đảm nguyên tử của ví dụ.

### 5.4. Vì sao replay được xét trước guard cho ý định mới?

Sau lần xác nhận đã commit, order thường ở PAYMENT_PENDING hoặc PAID. Nếu mọi retry đều bị kiểm tra “phải APPROVED” trước khi tìm operation cũ, cùng key hợp lệ có thể bị từ chối dù lần đầu đã thành công.

Thứ tự trong ví dụ là:

```text
authentication/quyền chức năng
    -> tenant/object access hiện tại
    -> lookup và kiểm tra replay cùng ý định
    -> guard state/approval cho ý định mới
    -> ghi nguyên tử
```

Replay không bỏ qua quyền đọc kết quả. Với key khác, request đi qua guard ý định mới và bị state machine/ràng buộc nghĩa vụ chặn nếu order đã có confirmation; key mới không tạo quyền thu lại.

## 6. Thứ tự AOP và các cách tích hợp dễ gây hiểu nhầm

### 6.1. Không suy thứ tự chạy từ thứ tự annotation trong source

Đặt `@Transactional` ở dòng trên `@PreAuthorize` không tự làm transaction chạy ngoài security advice. Advisor order mới quyết định cách advice lồng nhau. Với cấu hình mặc định thông dụng của proxy mode, pre-authorization có thể chạy trước khi transaction method được mở; sau khi method trả, transaction có thể commit trước một bước post-authorization bên ngoài.

[Spring Framework Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) mô tả cấu hình transaction advice và order. Nếu tùy chỉnh advisor order, phải kiểm tra chuỗi advice thật và rollback behavior; đổi order không tự tạo khóa hoặc sửa TOCTOU.

### 6.2. Expression đọc object có thể vẫn bị TOCTOU

```java
@PreAuthorize("@orderAccess.canConfirm(authentication, #orderId)")
@Transactional
public void confirm(String orderId) {
    // Nếu chỉ tin snapshot mà expression đã đọc, dữ liệu có thể đã đổi.
}
```

`orderAccess` là bean minh họa, không phải API tích hợp sẵn. Nếu dùng tên tham số `#orderId`, phải bảo đảm Spring khám phá đúng parameter name theo cấu hình build/annotation của phiên bản sử dụng. Test phải chứng minh expression nhận đúng giá trị.

Object check ở annotation có thể hữu ích để từ chối sớm, nhưng nếu nó đọc trước transaction ghi hoặc không giữ được ràng buộc cần thiết, service vẫn phải tái kiểm tra theo dữ liệu nhất quán. Không để `PermissionEvaluator` hoặc custom authorization bean âm thầm tạo tác dụng phụ trong bước đánh giá quyền.

### 6.3. Không dùng post-authorization làm rào chắn chính cho thao tác ghi

Một method đã ghi database/gọi provider rồi mới bị `@PostAuthorize` từ chối có thể đã tạo hiệu lực. Khả năng rollback cục bộ còn phụ thuộc transaction có bao bước từ chối đó hay đã commit trước; hiệu lực ngoài database lại là vấn đề riêng.

Vì vậy các guard cho thao tác ghi phải được đánh giá trước khi chấp nhận thay đổi/hiệu lực. `@PostAuthorize` có thể phục vụ kiểm tra dữ liệu trả về trong thiết kế phù hợp, nhưng phản hồi bị chặn không tự chứng minh toàn bộ công việc trước đó chưa xảy ra.

## 7. Ranh giới transaction phải tồn tại trên đường gọi thực tế

### 7.1. Self-invocation có thể bỏ qua advice

Trong proxy mode, lời gọi nội bộ `this.confirm(...)` không đi qua proxy của method đó. Annotation trên method được gọi vì thế không tự tạo thêm kiểm tra quyền hoặc ranh giới transaction. Nếu method ngoài đã có transaction, code bên trong có thể vẫn chạy trong transaction ấy, nhưng điều đó không chứng minh security advice của `confirm` đã chạy. Giới hạn về transaction được mô tả trong [Spring Framework: Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

```java
@Service
class OrderBatchService {
    private final OrderConfirmationService confirmations;

    OrderBatchService(OrderConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    public ConfirmOrderResult confirmOne(
            String orderId, ConfirmOrderCommand command) {
        return confirmations.confirm(orderId, command);
    }
}
```

Ví dụ tách bean giúp lời gọi đi qua service được inject. Authentication thích hợp vẫn phải được thiết lập; tách bean không cấp quyền cho batch job. Không tạo service bằng `new OrderConfirmationService(...)` trong code ứng dụng rồi trông chờ annotation tự có hiệu lực.

Một entry point mới như API quản trị, consumer hoặc tác vụ định kỳ phải được xem là một đường gọi cần thiết kế quyền. Tránh đường tắt gọi thẳng repository để đưa order sang PAYMENT_PENDING mà không qua các guard tương đương.

### 7.2. Từ chối phải làm transaction thất bại đúng cách

Theo cấu hình mặc định thông thường, exception kiểu `RuntimeException` và `Error` làm rollback; checked exception cần quy tắc phù hợp. `AccessDeniedException` là unchecked exception. Nếu nó phát sinh trong ranh giới transaction và được truyền ra ngoài, quy tắc rollback mặc định áp dụng; nếu pre-authorization từ chối trước khi transaction mở thì chưa có transaction của lời gọi đó để rollback. Xem [Spring Framework: Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

Đây là mẫu dễ tạo lỗi nghiệp vụ:

```java
@Transactional
public ConfirmOrderResult unsafeConfirm(...) {
    order.markPaymentPending(operationId);
    try {
        policy.assertMayStartConfirmation(...);
    } catch (AccessDeniedException denied) {
        return new ConfirmOrderResult(operationId, "DENIED");
    }
    // ...
}
```

Đoạn trên chỉ minh họa anti-pattern, không phải Java hoàn chỉnh. Entity đã bị sửa trước guard; việc nuốt exception rồi trả kết quả bình thường có thể cho phép commit thay đổi đó. Dirty checking của JPA khiến việc không gọi `save()` không phải bằng chứng rằng chưa ghi dữ liệu.

Thiết kế của mục 5 đặt guard trước mutation, truyền lỗi ra ngoài transaction và ánh xạ lỗi thành phản hồi ở lớp ngoài. Nếu domain dùng checked exception cho lỗi bắt buộc hủy giao dịch, cấu hình rõ, chẳng hạn `@Transactional(rollbackFor = ApprovalInvalidException.class)`, rồi kiểm tra cấu hình rollback thực tế của ứng dụng. Không để `noRollbackFor` hoặc cơ chế xử lý lỗi chung vô tình cho phép commit một ý định bị từ chối.

### 7.3. Service trả kết quả chưa luôn là transaction cuối cùng đã commit

Khi service tham gia transaction do caller mở, kết quả từ `confirm` có thể được trả về cho caller trong lúc transaction ngoài vẫn chưa kết thúc. Caller có thể tiếp tục gặp lỗi và rollback toàn bộ. Vì vậy không phát thông báo chắc chắn đã chấp nhận, hoặc gọi provider, chỉ vì một method nội bộ đã trả `PENDING_PAYMENT`.

Trong fixture, trạng thái operation và outbox chỉ có giá trị sau khi transaction chứa chúng commit thành công. Một lỗi khi flush/commit cũng phải được xử lý như lỗi chấp nhận giao dịch, kể cả khi thân method không ném lỗi. Mọi repository lưu order, operation, reservation, idempotency và outbox phải thật sự tham gia cùng ranh giới dữ liệu; dùng nhiều DataSource độc lập không tự có bảo đảm này.

## 8. Kết hợp guard với ràng buộc database và thời điểm quyết định

### 8.1. Ràng buộc bảo vệ nghĩa vụ, không chỉ bảo vệ request key

Trong fixture một lần xác nhận cho mỗi order, có thể biểu diễn các ràng buộc ở mức thiết kế như sau:

| Dữ liệu | Ràng buộc cần thiết | Lạm dụng bị chặn |
|---|---|---|
| Confirmation operation | Unique `(tenant_id, order_id)` | Đổi key để tạo operation xác nhận thứ hai |
| Idempotency binding | Unique `(tenant_id, subject_id, action, key)` | Hai request cùng scope/key cùng được bind |
| Reservation của operation | Một reservation logic cho mỗi operation và dòng hàng | Retry giữ kho lặp |
| PaymentRequested của fixture | Unique `(operation_id, event_type)` | Tạo hai sự kiện yêu cầu thanh toán logic cho một operation |
| Provider payment reference | Liên kết duy nhất theo phạm vi provider/account và operation | Gắn cùng hiệu lực thanh toán vào nhiều nghĩa vụ |

Đây là hợp đồng schema, chưa phải DDL dùng chung cho mọi database. Các thành phần của unique key cần có chính sách `NOT NULL`, chuẩn hóa và so sánh rõ ràng. Ví dụ không được để một giá trị key được coi là hai giá trị ở application nhưng lại bằng nhau dưới collation của database, hoặc ngược lại. Unique outbox ở đây không ngăn relay gửi lại cùng một event nhiều lần.

Trạng thái chỉ bảo vệ được invariant khi mọi đường ghi đều tôn trọng nó. Database constraint là lớp bảo vệ cuối cho một số điều kiện có thể biểu diễn bằng schema; nó không tự xác minh actor hay approval.

### 8.2. Cùng key nhưng khác order vẫn có thể đua nhau

Khóa ORD-A không tuần tự hóa request đang khóa ORD-B. Hai request của A dùng cùng scope/key nhưng trỏ vào hai order khác nhau có thể đều không tìm thấy binding lúc đầu. Unique constraint trên binding phải khiến tối đa một transaction commit được việc bind key đó; transaction thua phải rollback cả operation, reservation và outbox của mình.

Không bắt lỗi uniqueness trong transaction đã hỏng rồi tiếp tục ghi hoặc trả một kết quả giả định. Lớp ngoài transaction có thể phân loại lỗi, sau đó đọc binding đã commit trong transaction mới, kiểm tra lại quyền trên đối tượng và so fingerprint:

- Cùng ý định và còn quyền đọc kết quả: trả operation đã tồn tại.
- Khác ý định: trả conflict theo hợp đồng API, không trả nội dung order của request thắng.
- Binding chưa đọc được hoặc trạng thái commit chưa rõ: xử lý theo giao thức retry có giới hạn, không suy đoán đã có operation mới hợp lệ.

Các bước đọc lại này vẫn phải dùng service/repository có scope phù hợp. Không biến nhánh xử lý lỗi constraint thành API tra cứu kết quả của actor hoặc tenant khác.

### 8.3. Approval hết hạn hoặc bị thu hồi được xét ở thời điểm nào?

Phải định nghĩa thời điểm policy có hiệu lực. Trong fixture, server đánh giá approval tại execution gate sau khi lấy được dữ liệu/khóa cần thiết, trước khi chấp nhận operation. `clock.instant()` là thời gian server tại bước kiểm tra, không phải thời gian client gửi request hay thời gian request vào hàng đợi.

Nếu request đợi khóa lâu đến lúc approval hết hạn thì phải đánh giá bằng thời điểm mới sau khi đợi. Không tái sử dụng một kết quả `approvalValid=true` đọc từ trước transaction. Approval cần ràng buộc vào nội dung thực sự được thực hiện: order, revision và các giá trị nhạy cảm được revision bao phủ như tổng tiền, currency, người nhận hoặc phạm vi hạn mức.

Nếu transaction thu hồi approval chạy đồng thời, giao thức phải xác định bên nào được chấp nhận trước bằng khóa/version hoặc cơ chế tương đương. Chỉ đọc cột `revoked=false` dưới isolation mặc định không đủ chứng minh invariant khi hàng approval có thể thay đổi độc lập.

Một policy yêu cầu approval còn hiệu lực tại lúc provider thực sự thu tiền chặt hơn policy tại lúc chấp nhận order. Khi đó phải có gate riêng ở worker hoặc một quyền thực thi đã được ràng buộc rõ vào operation, thời hạn và điều kiện hủy. Kiểm tra lại một lần ở service không bảo đảm thời gian và quyền ở một hệ thống khác trong tương lai.

## 9. Transaction cục bộ và hiệu lực thanh toán ngoài hệ thống

### 9.1. Outbox lưu ý định đã được chấp nhận

Luồng của fixture là:

```text
Request của A
  -> service: kiểm tra quyền và dữ liệu nhất quán
  -> một transaction database:
       operation + reservation + PAYMENT_PENDING
       + idempotency binding + outbox + audit chấp nhận
  -> COMMIT
  -> relay/worker đọc PaymentRequested đã commit
  -> gọi provider bằng định danh ổn định của operation
  -> ghi nhận kết quả qua chuyển trạng thái có kiểm soát
```

Thông điệp outbox dùng snapshot server của operation. Không đọc lại giá từ payload client khi relay chạy; cũng không tự thay giá thanh toán theo giá sản phẩm mới nhất nếu operation đã được duyệt cho một nội dung khác.

Relay có thể gặp crash sau khi provider xử lý nhưng trước khi đánh dấu event đã gửi. Do đó cần thiết kế cho việc gửi lại. Nếu provider có hỗ trợ idempotency, dùng key ổn định từ operation theo phạm vi và thời hạn provider cam kết. Khả năng chống trùng ngoài hệ thống phụ thuộc hợp đồng provider; outbox tự nó không cung cấp “exactly once” cho hiệu lực thu tiền.

### 9.2. Không coi timeout là thanh toán thất bại chắc chắn

| Quan sát | Kết luận được phép | Cách xử lý |
|---|---|---|
| Transaction cục bộ rollback chắc chắn trước khi nhận operation | Chưa chấp nhận ý định trong database này | Retry phải đi lại guard và protocol idempotency |
| Transaction commit nhưng response tới client bị mất | Operation có thể đã được chấp nhận | Client retry cùng key, tra operation cũ |
| Provider timeout sau khi gửi request | Chưa biết provider đã thu tiền hay chưa | Đối soát theo operation/provider reference; retry có kiểm soát cùng định danh |
| Callback báo thành công cho operation đã biết | Có bằng chứng cần kiểm chứng từ provider | Xác thực nguồn, đối chiếu nội dung và chuyển trạng thái idempotent |
| Callback lặp hoặc tới sai thứ tự | Không phải một nghĩa vụ thanh toán mới | Dedupe và kiểm tra state machine trước khi ghi |

Không tạo operation mới hoặc giải phóng kho một cách chắc chắn chỉ vì request thanh toán bị timeout. Nếu đã giải phóng kho nhưng provider sau đó báo thu tiền thành công, hệ thống có thể vừa bán quá số lượng vừa nợ hoàn tiền. Thiết kế cần trạng thái chưa xác định, tiến trình đối soát và chính sách bù trừ phù hợp.

### 9.3. Callback và worker có policy riêng

Callback không mang identity người dùng A theo cách request ban đầu mang. Entry point này cần xác thực provider/service identity và đối chiếu operation, merchant/account, amount, currency và trạng thái trước khi ghi PAID. Một callback có chữ ký hợp lệ nhưng amount hoặc account không khớp vẫn không chứng minh nghĩa vụ của order đã được thanh toán đúng.

Worker được cấp quyền xử lý operation đã được chấp nhận; quyền kỹ thuật ấy không có nghĩa được tạo order mới, đổi người nhận hoặc bỏ qua approval. Nếu hệ thống yêu cầu thu hồi quyền của A ngăn cả các operation đang chờ thực thi, phải có policy hủy/tái kiểm tra được đồng bộ với việc worker nhận thực thi. Nếu policy cho phép hoàn thành nghĩa vụ đã chấp nhận, cần ghi rõ quyết định đó và lưu bằng chứng đủ để đối soát.

Không chuyển toàn bộ `SecurityContext` của request thành thông điệp rồi mặc nhiên dùng lại mãi. Lưu actor ban đầu để truy vết và giới hạn quyền worker vào action/operation cần xử lý. Một retry kỹ thuật của worker không phải lần phê duyệt nghiệp vụ mới.

## 10. Lỗi, audit và quyền quản trị phải giữ đúng ý nghĩa nghiệp vụ

### 10.1. Phản hồi không thay thế bằng chứng dữ liệu

Ứng dụng có thể ánh xạ lỗi theo hợp đồng API, chẳng hạn 403 khi từ chối quyền, 404 khi không muốn tiết lộ đối tượng ngoài scope, 409 khi revision/state/intent xung đột. Đây là lựa chọn thiết kế; không phải mọi exception tự động có đúng mã HTTP này.

Không trả stack trace, owner thật, tenant khác hoặc fingerprint nội bộ cho caller không có quyền. Replay cũng chỉ trả dữ liệu tối thiểu mà actor hiện tại được xem. Giới hạn độ dài key, scope dữ liệu và tốc độ request giúp tránh biến cơ chế idempotency thành nơi lưu dữ liệu vô hạn do client điều khiển.

Điều cần chứng minh sau lỗi là không có thay đổi bị cấm đã commit. Một response 403 đi kèm operation mới hoặc kho bị trừ vẫn là vi phạm TA-01/TA-04.

### 10.2. Tách audit chấp nhận khỏi audit từ chối

Audit chấp nhận nên gắn `actor`, tenant, action, order ID, operation ID, content revision, approval reference/version, policy version và correlation ID. Lưu các bằng chứng cần thiết dưới chính sách dữ liệu phù hợp; không ghi token, credentials hoặc dữ liệu nhạy cảm không cần thiết. Khi ghi audit chấp nhận trong cùng transaction, rollback sẽ không để lại bản ghi khẳng định chấp nhận thành công.

Audit từ chối có mục đích khác. Nếu cần giữ lại sau rollback, dùng đường ghi/sink đã được thiết kế cho sự kiện từ chối và không phụ thuộc vào transaction nghiệp vụ bị hủy. Bản ghi này không được cập nhật order, tạo operation hoặc vô tình commit một phần công việc. Nó phải phân biệt “đã từ chối”, “đã chấp nhận” và “kết quả provider chưa rõ”.

Đừng coi log ghi trước commit là sổ cái operation. Ngay cả dòng log “confirmation accepted” cũng có thể xuất hiện trước một lỗi commit; nên ghi rõ giai đoạn hoặc đối chiếu với bản ghi authoritative.

### 10.3. ADMIN không mặc nhiên được phá invariant

Nếu có chức năng quản trị xác nhận thay người dùng, thiết kế một action riêng với phạm vi đối tượng và lý do được ghi nhận. Quyền hỗ trợ có thể cho phép truy cập một order nhưng không mặc nhiên cho phép dùng approval đã hết hạn, thay amount hoặc tự duyệt giao dịch mình tạo.

Một cơ chế khẩn cấp được nghiệp vụ cho phép cần policy và audit riêng. Tránh nhánh `if (isAdmin) return true` dùng chung cho cả object access, separation of duties, state transition và bảo vệ chống thu tiền trùng.

## 11. Kiểm thử transaction authorization theo hiệu lực quan sát được

### 11.1. Chọn đúng lớp kiểm thử

Unit test policy giúp kiểm tra bảng quyết định actor/order/approval, nhưng không chứng minh AOP đã chạy hoặc transaction thật đã rollback. Integration test cần gọi bean Spring được inject và dùng database có semantics gần môi trường triển khai để kiểm tra khóa, constraint và commit.

Với `ActorResolver` của bài, principal phải là `AppPrincipal`. `@WithMockUser` mặc định tạo principal kiểu `User` của Spring Security nên không mô phỏng được actor hợp lệ của fixture; chỉ thêm `authorities = "order:confirm"` vẫn chưa đủ. Có thể tạo annotation với `@WithSecurityContext` hoặc thiết lập context riêng trong test. Xem [Spring Security: Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html).

Khi kiểm thử HTTP tới server chạy thật, authentication cần đi cùng request thật; context đặt ở test thread không tự truyền sang server thread. Test trực tiếp service và test qua HTTP trả lời hai câu hỏi khác nhau.

### 11.2. Ví dụ test object authorization không nhầm với thiếu authority

Đây là trích đoạn integration test với JUnit 5 và AssertJ. `service` là bean Spring được inject; `fixtures` và `probe` là helper domain do test suite cung cấp, không phải API Spring. Fixture tạo dữ liệu đã commit; `probe.businessSnapshot` đọc ở transaction mới và lấy trạng thái order, operation, reservation, idempotency và outbox liên quan, không lấy thời gian/log từ chối.

```java
@Test
void sameAuthorityDoesNotPermitAnotherOwnerOrder() {
    fixtures.approvedOrder("ORD-A", "T1", "A", 7L);
    var before = probe.businessSnapshot("T1", "ORD-A");

    var context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(
        new UsernamePasswordAuthenticationToken(
            new AppPrincipal("B", "T1"),
            null,
            List.of(new SimpleGrantedAuthority("order:confirm"))
        )
    );
    SecurityContextHolder.setContext(context);

    try {
        assertThatThrownBy(() -> service.confirm(
            "ORD-A", new ConfirmOrderCommand(7L, "attempt-by-B")
        )).isInstanceOf(AccessDeniedException.class);
    } finally {
        SecurityContextHolder.clearContext();
    }

    assertThat(probe.businessSnapshot("T1", "ORD-A"))
        .isEqualTo(before);
}
```

Test này giả định guard owner ném `AccessDeniedException`; nếu ứng dụng che sự tồn tại bằng exception khác, assertion phải theo hợp đồng thật. Chủ đích là B có quyền chức năng đúng nhưng vẫn không có quyền trên ORD-A. Đặt authentication giả lập chỉ là cách dựng fixture trong test, không phải cách xác thực request sản phẩm.

Không bao bọc toàn bộ test commit/rollback trong một transaction test mà service vô tình join vào rồi chỉ rollback ở cuối test. Hãy để ranh giới transaction của service được thực thi và đọc dữ liệu đã commit từ ranh giới độc lập; nếu chủ động dùng transaction test, phải kết thúc nó đúng lúc để quan sát được điều cần chứng minh.

### 11.3. Ma trận tình huống tối thiểu cho fixture

| Tình huống | Kết quả cần quan sát |
|---|---|
| A đúng tenant/owner, đủ authority, approval revision 7 hợp lệ | Một operation, một reservation logic, order PAYMENT_PENDING và một PaymentRequested cùng commit |
| A thiếu `order:confirm` | Bị từ chối qua method security; không có thay đổi nghiệp vụ |
| B có cùng authority, cùng tenant nhưng khác owner | Bị từ chối bởi object policy; snapshot nghiệp vụ giữ nguyên |
| Actor thuộc T2 gọi ORD-A của T1 | Không đọc/ghi hoặc tiết lộ dữ liệu ngoài tenant |
| Client gửi actor/tenant/amount giả qua HTTP | Không thay nguồn actor hoặc amount authoritative; có thể bị reject ở validation theo hợp đồng |
| Order chưa APPROVED, approval hết hạn hoặc revision không khớp | Không tạo operation, reservation hoặc outbox |
| Nội dung được đổi sau khi approval cấp | Không thực hiện nội dung mới dưới approval cũ |
| Approver vi phạm separation of duties | Guard từ chối ý định mới |
| Retry cùng key và cùng intent sau commit | Cùng operation ID dù state đã chuyển PAYMENT_PENDING/PAID; không thêm reservation hoặc thu tiền mới |
| Cùng key nhưng đổi order/revision trong intent | Conflict; không tiết lộ kết quả của intent khác và không tạo hiệu lực mới |
| Hai key khác nhau cùng xác nhận một order | Tối đa một operation theo invariant của fixture |
| Replay sau khi actor mất quyền trên order | Không được dùng replay để đọc kết quả ngoài quyền hiện tại |
| Lỗi sau reservation nhưng trước khi lưu outbox | Toàn bộ thay đổi transaction rollback |
| Relay nhận event lặp, provider timeout, callback lặp | Bám cùng operation; không suy ra nghĩa vụ thanh toán mới |
| Batch/job hoặc API quản trị gọi cùng chức năng | Có identity/policy thích hợp và vẫn giữ invariant, không đi tắt qua repository |

Đối với happy path, kiểm tra amount/currency và revision trong operation/outbox khớp nguồn server, không chỉ kiểm tra operation tồn tại. Đối với lỗi, kiểm tra các hàng liên quan ở trạng thái đã commit; không chỉ assert exception hoặc mã HTTP.

### 11.4. Kiểm thử race có lịch chạy kiểm soát được

Một kiểm thử concurrency cần hai connection/transaction độc lập, mỗi worker có authentication/context riêng. Dùng latch/barrier tại điểm hợp lý để điều khiển lịch chạy; không dựa vào `sleep` và không đặt barrier buộc hai request phải cùng giữ một khóa độc quyền không thể giữ đồng thời.

Có thể dựng ba lịch tấn công sau:

1. **Hai xác nhận trên cùng order:** request thứ nhất giữ khóa order; request thứ hai chờ. Sau khi request thứ nhất commit, request thứ hai phải đọc lại state mới. Cùng key trả operation cũ; key khác không được tạo operation thứ hai.
2. **Sửa nội dung hoặc thu hồi approval đồng thời:** đường sửa/thu hồi và đường confirm dùng giao thức khóa/version đã chọn. Kiểm tra operation được chấp nhận theo đúng thứ tự policy đã định nghĩa, không dùng approval cũ cho nội dung mới.
3. **Hai order cùng tranh đơn vị kho cuối:** mỗi request giữ một khóa order riêng nên khóa order không giải quyết tranh chấp kho. Chứng minh nhiều nhất một reservation thành công và stock không âm.

Bổ sung race cùng scope/key trên hai order để kiểm tra unique binding và rollback của transaction thua. Khi kết thúc, đọc dữ liệu từ transaction mới, đối chiếu số operation, nghĩa vụ, reservation, binding và outbox. Nếu test chỉ mock `lockByTenantAndId`, nó chưa kiểm chứng được hành vi lock hoặc isolation của database.

## 12. Bài tập áp dụng và các câu hỏi thiết kế cần trả lời

### 12.1. Bài tập: approval hết hạn trong lúc đợi khóa

Giả sử approval của ORD-A hết hạn lúc 10:00:05 theo clock server. Request vào hệ thống lúc 10:00:04 nhưng đợi khóa đến 10:00:07. Một triển khai đọc approval từ cache trước khi đợi, rồi sau khi lấy khóa dùng kết quả `valid=true` để chuyển sang PAYMENT_PENDING.

Hãy chỉ ra ranh giới quyết định sai, sửa thứ tự đọc/kiểm tra và mô tả test có clock điều khiển được. Với policy của fixture, request này không được tạo operation mới vì approval đã hết hạn khi gate thực thi đánh giá. Nếu đó là retry của operation đã được chấp nhận trước đó, cần phân biệt nhánh replay với nhánh tạo ý định mới theo mục 5.4.

### 12.2. Bài tập: thấy 403 nhưng vẫn bị giữ kho

Một service gọi `reserveFromServerOrder`, sau đó mới kiểm tra owner; exception bị lớp xử lý chung trong service bắt và đổi thành kết quả DENIED. Client nhận response từ chối, nhưng reservation vẫn xuất hiện sau commit.

Hãy sửa thứ tự guard/mutation, ranh giới truyền exception và cách quan sát rollback. Test đạt yêu cầu phải chứng minh B có authority hợp lệ, không sở hữu order và không làm thay đổi reservation, operation, order, binding hoặc outbox đã commit. Một assertion chỉ kiểm tra 403 không phát hiện đủ lỗi này.

### 12.3. Checklist trước khi áp dụng vào một luồng nghiệp vụ khác

- Ai là actor, tenant context được xác minh ở đâu, quyền có thể bị thu hồi theo semantics nào?
- Ý định gồm những dữ liệu nhạy cảm nào, dữ liệu nào do server quyết định, approval ràng buộc vào revision nào?
- Chuyển trạng thái hợp lệ là gì, và các entry point khác có dùng cùng invariant không?
- Quyền/object/state được đọc trong transaction nào, khóa/version bảo vệ những hàng nào, còn hàng dùng chung nào chưa được bảo vệ?
- Một nghĩa vụ được định danh thế nào; scope/key, fingerprint và database constraint chống trùng ra sao?
- Mọi lỗi bắt buộc hủy giao dịch có thật sự rollback; caller có thể mở transaction ngoài hay nuốt exception không?
- Hiệu lực nào nằm ngoài database; timeout, redelivery và callback được đối soát theo operation nào?
- Test có chứng minh đúng actor, proxy, transaction thật và dữ liệu đã commit, kể cả khi bị từ chối hoặc chạy song song không?

Mục tiêu của transaction authorization checks là để một ý định chỉ được chấp nhận khi actor, dữ liệu và trạng thái cùng thỏa policy tại ranh giới đã xác định. Trong Spring Security, annotation kiểm soát lời gọi là một phần của thiết kế; tính đúng của giao dịch còn phụ thuộc guard trong transaction, concurrency, state machine, ràng buộc nghĩa vụ và cách xử lý hiệu lực ngoài hệ thống.
