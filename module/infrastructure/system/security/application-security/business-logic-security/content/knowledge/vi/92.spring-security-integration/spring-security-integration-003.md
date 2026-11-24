# SecurityContext actor identity — Xác định chủ thể thực hiện hành động nghiệp vụ

## 1. Mục tiêu và tình huống cần bảo vệ

Trong chương **Spring Security Integration**, việc lấy đúng danh tính actor là nền tảng để kiểm tra quyền theo đối tượng, chống tự phê duyệt, ghi audit và xử lý lệnh lặp. Nếu ứng dụng lấy người thực hiện từ request body hoặc một header không được xác thực, các kiểm tra nghiệp vụ có thể đúng về hình thức nhưng được áp dụng cho sai người.

Ví dụ, Alice tạo yêu cầu mua hàng và chỉ Carol được quyền duyệt yêu cầu đó. Alice gửi thêm `approverId=Carol` hoặc header `X-Actor-Id` để ứng dụng ghi nhận Carol là người duyệt. Nếu server tin dữ liệu này, quy tắc không tự duyệt có thể bị vượt qua mà không cần chiếm phiên của Carol.

Bài học tập trung vào cách:

- Đọc danh tính đã được thiết lập trong `SecurityContext`.
- Phân biệt authenticated principal, actor nghiệp vụ, tenant và quyền trên đối tượng.
- Xây adapter chuyển principal sang actor có định danh ổn định.
- Từ chối anonymous, principal không đúng hợp đồng và trường hợp thiếu context.
- Đưa actor vào quyết định phê duyệt cùng ranh giới transaction.
- Xử lý chuyển thread, tác vụ nền, audit và kiểm thử giả mạo danh tính.

Các ví dụ dùng Java 17+ với mô hình Servlet/Spring MVC và API được đối chiếu theo tài liệu Spring Security 7.0. Đây là các thành phần minh họa, không phải một project hoàn chỉnh hoặc hướng dẫn thay dependency của ứng dụng hiện có. Ứng dụng cần dùng bộ phiên bản tương thích và cấu hình authentication phù hợp với project của mình.

## 2. Những khái niệm cần tách rõ

### 2.1. Từ context tới quyết định nghiệp vụ

```text
Credential/session/token được xác minh
-> Authentication trong SecurityContext
-> Principal theo hợp đồng của cơ chế authentication
-> Ánh xạ sang account/actor nội bộ
-> Xác định tenant và quyền hiện tại
-> Kiểm tra đối tượng, revision, workflow và bất biến
-> Thực hiện lệnh trong ranh giới nhất quán
```

`SecurityContextHolder` cung cấp context chứa `Authentication`. Với cấu hình Servlet mặc định, thông tin này gắn với thread xử lý. `Authentication` có principal và authorities; kiểu principal phụ thuộc cơ chế xác thực. [Spring Security 7.0 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html).

Danh tính trả lời “ai đang hành động”. Authorization trả lời “chủ thể này được làm gì với đối tượng nào”. State machine và các bất biến còn quyết định “hành động có hợp lệ ở trạng thái và dữ liệu hiện tại không”.

### 2.2. Actor không đồng nghĩa mọi ID liên quan trong request

| Giá trị | Ý nghĩa | Nguồn phù hợp |
| --- | --- | --- |
| Actor/account ID | Chủ thể thực hiện hành động | Authentication đã xác minh và ánh xạ nội bộ |
| Requester ID | Người tạo yêu cầu | Dữ liệu đối tượng đã lưu |
| Target user ID | Đối tượng người dùng bị thao tác | Input cần kiểm tra quyền, không phải actor |
| Approver ID | Người thực sự ra quyết định duyệt | Actor tại lúc duyệt, không lấy tùy ý từ body |
| Tenant ID | Phạm vi dữ liệu được lựa chọn và cho phép | Ngữ cảnh tenant đã xác minh, membership và đối tượng |
| Correlation ID | Liên kết quan sát các bước xử lý | Cơ chế tracing đã kiểm soát, không phải bằng chứng danh tính |

Endpoint “quản lý tài khoản của Bob” vẫn có actor là người đang quản lý, không tự biến thành Bob. Việc thao tác thay mặt người khác cần một mô hình ủy quyền rõ, không thay actor ID rồi xóa dấu vết người thực sự khởi tạo.

## 3. SecurityContext là nguồn danh tính trong một ranh giới tin cậy

### 3.1. Đọc context không thay cho xác thực

Trong luồng Servlet được cấu hình đúng, authentication filter/provider xác minh credential hoặc token trước khi đưa kết quả vào context. Application service đọc kết quả đó; nó không cần tự giải mã một header actor để quyết định ai đang gọi.

Tuy nhiên, context không phải một chứng thư bất khả giả mạo đối với code chạy trong cùng JVM. Một custom filter hoặc đoạn code có quyền gọi `setContext` có thể gán authentication sai. Vì vậy, cần kiểm soát những thành phần được phép thiết lập danh tính và không xây filter tin trực tiếp actor ID từ input.

Các header danh tính do reverse proxy/gateway cung cấp chỉ có ý nghĩa khi có thiết kế pre-authentication đầy đủ: ranh giới mạng, xác thực bên gửi, loại bỏ header giả từ client và quy tắc ánh xạ. Tên header nghe “internal” không tạo ra bảo đảm đó.

### 3.2. Không fallback sang system actor

Khi context thiếu hoặc principal không hỗ trợ, hành động nghiệp vụ cần được bảo vệ phải từ chối theo hợp đồng. Những cách fallback nguy hiểm gồm:

- Không có user thì dùng tài khoản admin/system.
- Principal sai kiểu thì parse `getName()` như account ID bất kỳ.
- Worker không có context thì lấy requester ID trong payload và coi đó là người đã được xác thực.
- Không tìm thấy membership thì tin tenant trong request để tiếp tục.

Một system actor hợp lệ phải được thiết kế và xác thực theo đường riêng với quyền giới hạn. Nó không phải phương án dự phòng cho lỗi lấy danh tính.

### 3.3. Danh tính ổn định hơn tên hiển thị

Không dùng email, display name hoặc username có thể thay đổi làm khóa duy nhất cho quyết định tài chính, tự duyệt hoặc audit lâu dài nếu hệ thống không bảo đảm tính ổn định tương ứng.

Actor nên dùng account ID nội bộ bất biến theo hợp đồng. Với danh tính liên kết, cần lưu nguồn định danh và quan hệ ánh xạ; cùng chuỗi tên ở hai nguồn khác nhau không tự là cùng một người.

## 4. Anonymous và mức xác thực

### 4.1. Có Authentication không có nghĩa đã đăng nhập

Spring Security có thể đặt `AnonymousAuthenticationToken` vào context cho một request chưa đăng nhập. Việc context có authentication vì thế không đủ để kết luận có actor đã xác thực. [Spring Security 7.0 — Anonymous Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/anonymous.html).

Không dùng riêng:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    // Chưa đủ để kết luận có người dùng đã đăng nhập.
}
```

Anonymous token có thể mang cờ authenticated trong mô hình của nó. Cần phân biệt loại/trust của authentication, không so principal với một chuỗi như `"anonymousUser"` rồi coi mọi trường hợp còn lại là an toàn.

### 4.2. AuthenticationTrustResolver

`AuthenticationTrustResolver` cung cấp cách phân biệt anonymous và remember-me. Trong API 7.0, `isAuthenticated(authentication)` kiểm tra authentication không null, có trạng thái authenticated và không phải anonymous; `isFullyAuthenticated` còn loại remember-me. [Spring Security 7.0 — AuthenticationTrustResolver](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html).

“Fully authenticated” theo cách phân loại này không tự chứng minh MFA, xác thực gần đây hoặc đã ký đúng nội dung giao dịch. Nếu hành động cần step-up, ứng dụng phải kiểm tra thêm bằng chứng và thời hạn theo policy.

Trong ví dụ, adapter cho biết có actor đăng nhập; service phê duyệt yêu cầu thêm authentication không thuộc remember-me. Hai điều kiện được đặt rõ, không gộp identity với mọi yêu cầu assurance.

## 5. Thiết kế principal và actor nội bộ

### 5.1. Hợp đồng principal của ví dụ

Ví dụ chọn `AppPrincipal` là principal do tầng authentication tin cậy tạo. Nó chứa account ID nội bộ và tenant đang được chọn qua một quy trình hợp lệ.

Các kiểu sau nằm trong các file Java riêng theo quy tắc public type của Java:

```java
import java.security.Principal;
import java.util.Objects;
import java.util.UUID;

public record AppPrincipal(
        UUID accountId,
        UUID activeTenantId) implements Principal {

    public AppPrincipal {
        Objects.requireNonNull(accountId);
        Objects.requireNonNull(activeTenantId);
    }

    @Override
    public String getName() {
        return accountId.toString();
    }
}
```

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

`AppPrincipal` không tự được tạo ra chỉ vì ứng dụng dùng form login. Với cơ chế mặc định, principal có thể là `UserDetails`; JWT resource server có thể dùng principal khác. Cần adapter/provider/converter đã được kiểm chứng để tạo đúng hợp đồng, hoặc viết resolver tương ứng với kiểu principal thực tế.

Không tạo một authenticated token từ DTO chứa `accountId`, tenant và role do client gửi. Record có dữ liệu hợp lệ về kiểu vẫn không chứng minh nguồn danh tính đáng tin.

### 5.2. Tenant trong principal là lựa chọn đã kiểm soát, chưa phải quyền vĩnh viễn

Tenant selection có thể bắt đầu từ input, nhưng server cần xác minh actor được phép hoạt động trong tenant đó. Khi membership bị thu hồi, một principal cũ không được tự giữ quyền mãi.

Trong mô hình bài học, mỗi lệnh nhạy cảm kiểm tra lại account còn hoạt động và membership hiện tại. Nếu policy cần hiệu lực thu hồi nguyên tử với giao dịch, cơ chế dữ liệu/điều phối phải hỗ trợ cam kết đó; đọc lại một row mà không điều phối chưa tự chống được race.

Không sửa principal hoặc context dùng chung để đổi tenant giữa chừng cho một lệnh đã bắt đầu. Lệnh cần một snapshot actor/tenant nhất quán, còn quyết định quyền vẫn được kiểm tra theo policy.

### 5.3. Actor record không phải capability tự cấp

Domain có thể nhận `Actor` qua tham số để dễ kiểm thử và giảm phụ thuộc Spring. Nhưng inbound application adapter phải là nơi lấy nó từ nguồn tin cậy.

Không cho client gọi một endpoint nhận nguyên actor record rồi chuyển vào domain như đã xác minh. Tên kiểu `Actor` không biến một input thành bằng chứng authentication.

## 6. Xây CurrentActor adapter có hành vi từ chối rõ

### 6.1. Port cho application service

```java
public interface CurrentActor {
    Actor require();
}
```

Một directory minh họa:

```java
import java.util.UUID;

public interface ActorDirectory {
    Actor requireActiveMembership(UUID accountId, UUID tenantId);
}
```

Hợp đồng của `requireActiveMembership`: xác định account/tenant từ dữ liệu có thẩm quyền, từ chối account không hoạt động hoặc membership không hợp lệ, và trả đúng cặp ID đã yêu cầu khi đạt điều kiện. Nó không tự cấp mọi quyền trên các đối tượng trong tenant.

### 6.2. Adapter đọc SecurityContext

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class SecurityContextCurrentActor implements CurrentActor {
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    private final ActorDirectory actorDirectory;

    public SecurityContextCurrentActor(ActorDirectory actorDirectory) {
        this.actorDirectory = actorDirectory;
    }

    @Override
    public Actor require() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (!trustResolver.isAuthenticated(authentication)) {
            throw new AuthenticationCredentialsNotFoundException(
                "An authenticated actor is required"
            );
        }

        if (!(authentication.getPrincipal() instanceof AppPrincipal principal)) {
            throw new AuthenticationServiceException(
                "Unsupported principal contract"
            );
        }

        return actorDirectory.requireActiveMembership(
            principal.accountId(),
            principal.activeTenantId()
        );
    }
}
```

Adapter không đọc body, query hoặc `X-Actor-Id`. Nó không fallback khi principal sai kiểu. Việc sai hợp đồng principal cần được quan sát như lỗi cấu hình/tích hợp và từ chối an toàn, không công khai chi tiết nội bộ cho client.

Loại exception và cách ánh xạ response phải được kiểm chứng trong filter chain/error handling của ứng dụng. API có thể dùng entry point/handler trả 401 hoặc 403 theo tình huống; web form có thể chuyển hướng đăng nhập. Không suy ra response cuối chỉ từ một exception trong unit test.

Adapter này chỉ hỗ trợ hợp đồng `AppPrincipal`. Nếu ứng dụng dùng nhiều cơ chế authentication, cần resolver tường minh cho từng cơ chế và quy tắc chọn có kiểm soát; không thử cast thất bại rồi tin `getName()` như phương án chung.

## 7. Dùng actor tại application service và transaction

### 7.1. Endpoint không nhận người duyệt tùy ý

Một request duyệt có thể gồm:

```json
{
  "expectedRevisionId": "85d3db65-13b8-47ba-848c-7d93dd7ecb70",
  "idempotencyKey": "approve-request-example-001"
}
```

Không cần `approverId` để xác định người đang duyệt. Actor được service lấy từ `CurrentActor`; requester và dữ liệu được duyệt lấy từ đối tượng đã lưu.

Trường không biết trong JSON có thể bị từ chối hoặc bỏ qua theo cấu hình API. Điều bắt buộc là chúng không thay đổi actor thực tế hoặc các dữ liệu nghiệp vụ không được phép sửa.

### 7.2. Service minh họa

Các dependency dưới đây là port nghiệp vụ giả định, cần triển khai trong dự án:

```java
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseApprovalApplicationService {
    private final CurrentActor currentActor;
    private final PurchaseRequestRepository requests;
    private final PurchaseApprovalPermissions permissions;
    private final ApprovalCommands approvalCommands;

    public PurchaseApprovalApplicationService(
            CurrentActor currentActor,
            PurchaseRequestRepository requests,
            PurchaseApprovalPermissions permissions,
            ApprovalCommands approvalCommands) {
        this.currentActor = currentActor;
        this.requests = requests;
        this.permissions = permissions;
        this.approvalCommands = approvalCommands;
    }

    @Transactional
    @PreAuthorize(
        "isFullyAuthenticated() and hasAuthority('PURCHASE_APPROVE')"
    )
    public void approve(
            UUID requestId,
            UUID expectedRevisionId,
            String idempotencyKey) {
        Actor actor = currentActor.require();

        PurchaseRequest request = requests
            .findForUpdate(actor.tenantId(), requestId)
            .orElseThrow(() -> new AccessDeniedException(
                "Request is not accessible"
            ));

        permissions.requireCanApprove(actor, request);

        if (request.requesterId().equals(actor.accountId())) {
            throw new AccessDeniedException("Self approval is forbidden");
        }

        approvalCommands.approveOnce(
            actor,
            request,
            expectedRevisionId,
            idempotencyKey
        );
    }
}
```

Hợp đồng các port:

| Thành phần | Trách nhiệm |
| --- | --- |
| `findForUpdate(tenantId, requestId)` | Đọc/khóa đúng đối tượng trong tenant, không tải ngoài tenant rồi quên kiểm tra |
| `requireCanApprove(actor, request)` | Kiểm tra quyền hiện tại trên đối tượng và quan hệ được duyệt |
| `approveOnce(...)` | Kiểm tra revision, state, idempotency; ghi approval và chuyển trạng thái nhất quán |
| Transaction local | Bao phủ các thay đổi bắt buộc và audit/outbox theo thiết kế |

Authority trong authentication là điều kiện thô. `requireCanApprove` vẫn cần bảo vệ membership, phạm vi và quyền hiện tại theo policy; authority đã được cấp từ lâu có thể không phản ánh mọi thay đổi dữ liệu.

### 7.3. Danh tính đúng vẫn cần bất biến đúng

Carol là actor đúng chưa đủ để duyệt một yêu cầu đã bị hủy hoặc một revision khác với nội dung Carol xem. `expectedRevisionId` giúp gắn ý định duyệt với nội dung cụ thể; service cần từ chối nếu không khớp.

Cùng lệnh được gửi lại không được tạo approval thứ hai hoặc làm tăng version nghiệp vụ ngoài hợp đồng. Idempotency phải có scope phù hợp và kiểm tra nội dung; nó không cho phép Alice dùng key của Carol để lấy dữ liệu hoặc ra quyết định thay Carol.

Actor và tenant cần được ghi cùng approval thực sự đã commit. Không ghi Carol vào audit chỉ vì body nói Carol là approver hoặc vì request đang thao tác trên đối tượng của Carol.

## 8. Bật method security và hiểu giới hạn proxy

### 8.1. Annotation cần được kích hoạt

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Spring Security hỗ trợ `@PreAuthorize` tại service khi bật method security; chỉ thêm starter không tự làm mọi annotation method-level có hiệu lực. [Spring Security 7.0 — Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html).

Cấu hình HTTP authentication/authorization vẫn cần tồn tại và được kiểm thử. Bài không đưa một `SecurityFilterChain` chung vì form/session, bearer token và pre-authentication có hợp đồng khác nhau.

### 8.2. Đừng để test bỏ qua đường thực thi thật

Với cách dùng proxy AOP thông thường, gọi qua Spring-managed bean là điều kiện cần cho interceptor tương ứng. Một lời gọi nội bộ trực tiếp trong cùng instance có thể bỏ qua proxy; tạo service bằng `new` trong test cũng không chứng minh `@PreAuthorize` đã chạy.

Domain guard trong service là hàng rào cần thiết, nhưng không phải lý do bỏ kiểm thử proxy. Test tích hợp phải gọi bean thật qua đường mà ứng dụng sử dụng.

Không mặc định biểu thức authorization đọc database sẽ chạy trong đúng transaction/khóa của body chỉ vì method có thêm `@Transactional`. Thứ tự advisor và thiết kế consistency cần được hiểu; các điều kiện nghiệp vụ thay đổi được vẫn cần kiểm tra ở ranh giới phù hợp.

## 9. @AuthenticationPrincipal và cơ chế JWT

### 9.1. Lấy principal tại controller khi cần

Spring MVC có `@AuthenticationPrincipal` để resolve `Authentication.getPrincipal()` vào tham số controller. Annotation này lấy principal theo cơ chế authentication hiện có, không tự chuyển nó thành actor nghiệp vụ. [Spring Security 7.0 — Spring MVC Integration](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/mvc.html).

Ví dụ một endpoint chỉ phục vụ thông tin profile có thể dùng:

```java
@GetMapping("/me")
public ProfileView me(
        @AuthenticationPrincipal AppPrincipal principal) {
    return profiles.loadForAuthenticatedPrincipal(principal);
}
```

Ví dụ giả định endpoint được bảo vệ và hợp đồng principal đã cấu hình đúng. Cần xử lý trường hợp null/sai kiểu theo policy; không fallback sang một profile mặc định có quyền cao.

Với lệnh nhạy cảm, application service trong bài tự gọi `CurrentActor`, để controller, job adapter hoặc caller khác không thể truyền một actor tùy ý rồi được coi là đã xác minh.

### 9.2. JWT không mặc định có principal AppPrincipal

Trong cấu hình JWT resource server thông thường, principal là `Jwt`, còn authentication có thể là `JwtAuthenticationToken`. Ứng dụng cần ánh xạ theo cấu hình thực tế, không dùng cùng cast như với principal custom.

Tài liệu Spring mô tả việc resource server xác minh JWT và ánh xạ principal/authorities. Những kiểm tra bổ sung như audience cần cấu hình theo hợp đồng API; không coi việc đọc được claims là xác minh token. [Spring Security 7.0 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/resource-server/jwt.html).

Một luồng ánh xạ nghiệp vụ có thể là:

```text
JWT đã qua decoder/validators đúng cấu hình
-> issuer được tin cậy + subject theo hợp đồng định danh
-> account nội bộ trong namespace của issuer
-> tenant selection đã được phép
-> membership/account hiện tại
-> Actor dùng cho quyết định nghiệp vụ
```

Không lấy JWT thô từ body rồi base64-decode để tạo actor. Không dùng một `sub` thiếu namespace nguồn nếu hệ thống có nhiều issuer; cũng không tự thay identity bằng email hoặc `getName()` mà không kiểm tra converter đang định nghĩa chúng thế nào.

Claim tenant đã có chữ ký vẫn cần phù hợp với trust contract của issuer và quyền trong ứng dụng. Nó không tự cho phép truy cập mọi đối tượng có cùng tenant ID, và membership có thể thay đổi trong thời gian token còn hạn.

## 10. ThreadLocal, tác vụ bất đồng bộ và nguy cơ lẫn actor

### 10.1. Chuyển thread cần cơ chế rõ

Không mặc định một executor tùy ý hoặc `CompletableFuture` có cùng context với request hiện tại. Thiếu context có thể làm job thất bại; rò context có thể làm job chạy dưới danh tính request trước.

Spring cung cấp các wrapper như `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextExecutor` để thiết lập context khi task chạy và dọn context sau đó. [Spring Security 7.0 — Concurrency Support](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/concurrency.html).

Ví dụ với executor đã được quản lý vòng đời:

```java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

public final class RequestTaskDispatcher {
    private final Executor securedExecutor;

    public RequestTaskDispatcher(Executor managedDelegate) {
        this.securedExecutor =
            new DelegatingSecurityContextExecutor(managedDelegate);
    }

    public void dispatch(Runnable task) {
        securedExecutor.execute(task);
    }
}
```

Constructor một tham số của wrapper lấy context theo lần submit. Nó khác cách truyền một context cố định vào wrapper rồi dùng cùng danh tính đó cho mọi task.

Ví dụ chỉ minh họa truyền context trong một tiến trình. Cần tích hợp đúng executor mà ứng dụng thực sự dùng, bao gồm đường `@Async` nếu có; thêm một bean không được sử dụng không thay đổi hành vi task.

### 10.2. Context được truyền không phải deep copy hoặc giấy phép vĩnh viễn

Không sửa `Authentication`, principal mutable hoặc context đang được chia sẻ để đổi user/tenant cho một task khác. Truyền context không bảo đảm dữ liệu quyền còn mới, cũng không chụp một snapshot đầy đủ của transaction nghiệp vụ.

Task chậm vẫn cần kiểm tra lại điều kiện cần còn hiệu lực lúc thực thi. Authentication được phân loại full không chứng minh token/session hoặc approval của một giao dịch còn hợp lệ sau thời gian chờ dài.

Không dùng `MODE_GLOBAL` trong ứng dụng web nhiều người dùng để “giải quyết mất context”. Không coi `MODE_INHERITABLETHREADLOCAL` là giải pháp chung cho thread pool: việc kế thừa khi tạo thread không tương đương truyền đúng actor theo từng task submit.

### 10.3. Dọn context là điều kiện chống rò danh tính

Trong luồng web được Spring Security quản lý, framework có cơ chế cleanup context. Với thread/task custom hoặc code test tự gán context, cần bảo đảm cleanup trên cả đường exception.

Không sửa một static field để lưu “current user”, cũng không cache actor của request đầu tiên trong singleton service. Singleton có thể giữ adapter lấy actor theo lần gọi; nó không được giữ actor mutable dùng chung cho mọi request.

Bài chỉ dùng mô hình Servlet. Ứng dụng reactive cần cơ chế context tương ứng; không bê nguyên giả định ThreadLocal sang một luồng xử lý khác mô hình.

## 11. Job bền vững, service actor và ủy quyền

### 11.1. Không serialize SecurityContext vào queue

Job có thể chạy sau khi request kết thúc, sau restart hoặc dưới một service khác. Không lưu nguyên Authentication, credential hay bearer token để giữ quyền người dùng vô thời hạn.

Có thể lưu dữ liệu truy vết:

```text
businessCommandId, tenantId, objectId, objectRevision
initiatedByAccountId, acceptedAt, policyVersion
authorizationReference nếu có
jobId, correlationId
```

Các field này mô tả lệnh đã được tiếp nhận và nguồn khởi tạo. Chúng không tự là bằng chứng người gửi queue có quyền tạo lệnh; queue producer và consumer cần được xác thực, phân quyền và kiểm tra dữ liệu theo hợp đồng.

### 11.2. Chọn mô hình thực thi rõ

| Mô hình | Điều cần kiểm tra |
| --- | --- |
| Worker thực hiện quyết định đã được chấp thuận | Có lệnh/approval bền vững, scope và điều kiện tiếp tục hợp lệ |
| Worker thực hiện thay người dùng | Quyền ủy quyền, thời hạn, phạm vi và quyền hiện tại theo policy |
| Service thực hiện nhiệm vụ của chính nó | Service identity có quyền giới hạn trên đối tượng/hành động |
| Operator replay | Operator có quyền replay, lệnh còn hợp lệ và không tạo tác dụng lặp |

Không gán requester vào context rồi coi worker là requester đã đăng nhập. Nếu worker cần gọi một service dùng method security, phải có inbound adapter/service identity được thiết kế phù hợp; không tạo một admin authentication tổng quát chỉ để annotation cho qua.

### 11.3. Tách người khởi tạo và người thực thi

Audit có thể cần `initiatedBy`, `executedBy` và `onBehalfOf` riêng. Worker thực hiện dưới service account không được ghi như Carol vừa đăng nhập duyệt lại.

Ủy quyền không làm mất actor thực sự. Cần giữ chuỗi người/service, phạm vi được ủy quyền, đối tượng và bằng chứng để kiểm tra trách nhiệm khi có sự cố.

## 12. Audit và kết quả lỗi

### 12.1. Ghi actor từ nguồn server tại điểm hành động

Một approval/audit có thể chứa:

```text
actorAccountId, actorKind, tenantId
targetObjectId, objectRevisionId
action, decision, reasonCode
policyVersion, businessCommandId
initiatedBy/executedBy nếu có
correlationId, recordedAt
```

Không lấy actor cho audit từ trường cùng tên trong DTO. Không log toàn bộ principal, session hoặc token để “chứng minh ai gọi”; dùng định danh và tham chiếu đủ cho mục đích điều tra.

Với hành động thành công, audit nghiệp vụ phải phản ánh kết quả đã commit theo thiết kế. Với lần từ chối, giữ bằng chứng phù hợp nhưng tránh lộ sự tồn tại hoặc nội dung của đối tượng ngoài quyền.

### 12.2. Phân biệt thiếu identity, thiếu quyền và vi phạm workflow

| Tình huống | Cách xử lý cần định nghĩa |
| --- | --- |
| Không có authentication hoặc anonymous | Yêu cầu authentication theo cơ chế API/web |
| Principal sai hợp đồng | Từ chối, quan sát lỗi tích hợp, không fallback |
| Account/membership không hợp lệ | Từ chối theo policy, không tin claim cũ thay thế |
| Actor đúng nhưng không có quyền đối tượng | Không tạo tác dụng; response không lộ dữ liệu ngoài quyền |
| Actor được phép nhưng request/revision không hợp lệ | Từ chối chuyển trạng thái theo hợp đồng nghiệp vụ |
| Cùng command đã hoàn tất | Trả/tra cứu kết quả cũ sau kiểm tra quyền, không thực thi lại |

401, 403, 404 hoặc mã lỗi nghiệp vụ phải phù hợp với giao thức và chính sách không tiết lộ của ứng dụng. Bằng chứng cuối cùng cần có là không xuất hiện approval, ledger hoặc tác dụng ngoài ý muốn, không chỉ một status code.

## 13. Kiểm thử danh tính và các đường lạm dụng

### 13.1. Test adapter từ chối anonymous

Ví dụ unit test dùng adapter thật và một directory giả lập. Context chỉ được gán để tạo fixture của test, không phải cách authentication production:

```java
@Test
void anonymousTokenDoesNotBecomeABusinessActor() {
    var context = SecurityContextHolder.createEmptyContext();
    var anonymous = new AnonymousAuthenticationToken(
        "test-key",
        "anonymousUser",
        AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS")
    );
    context.setAuthentication(anonymous);
    SecurityContextHolder.setContext(context);

    try {
        assertTrue(anonymous.isAuthenticated());

        assertThrows(
            AuthenticationCredentialsNotFoundException.class,
            currentActor::require
        );

        verifyNoInteractions(actorDirectory);
    } finally {
        SecurityContextHolder.clearContext();
    }
}
```

Test chứng minh một trường hợp dễ bị bỏ sót khi chỉ dùng `isAuthenticated()`. Thêm ca không có authentication, token chưa authenticated, principal sai kiểu và membership bị thu hồi.

### 13.2. Test principal hợp lệ được ánh xạ đúng account và tenant

Ca thành công cần chứng minh adapter dùng chính account/tenant của principal đã được thiết lập trong context để hỏi directory. Test dưới đây dùng JUnit Jupiter và Mockito, cùng các kiểu `AppPrincipal`, `Actor`, `ActorDirectory`, `CurrentActor` và `SecurityContextCurrentActor` đã định nghĩa ở trên:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

class SecurityContextCurrentActorTest {
    @Test
    void resolvesInternalActorFromPrincipalAndActiveMembership() {
        UUID accountId = UUID.randomUUID();
        UUID tenantId = UUID.randomUUID();
        Actor expected = new Actor(accountId, tenantId);

        ActorDirectory directory = mock(ActorDirectory.class);
        when(directory.requireActiveMembership(accountId, tenantId))
            .thenReturn(expected);

        CurrentActor currentActor = new SecurityContextCurrentActor(directory);
        var authentication = UsernamePasswordAuthenticationToken.authenticated(
            new AppPrincipal(accountId, tenantId),
            null,
            List.of(new SimpleGrantedAuthority("PURCHASE_APPROVE"))
        );

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        try {
            assertEquals(expected, currentActor.require());
            verify(directory).requireActiveMembership(accountId, tenantId);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

Đây là fixture unit test tự quản lý context trên thread test, không dùng cơ chế tự khôi phục context của một test harness khác. Tạo context mới rồi dọn trong `finally` giúp fixture không sửa context đang được chia sẻ hoặc để lại actor cho test tiếp theo. Spring cũng hướng dẫn tạo một `SecurityContext` mới thay vì sửa trực tiếp context hiện tại khi thiết lập authentication bằng code. [Spring Security 7.0 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html).

Test này chỉ kiểm tra hợp đồng lấy danh tính và gọi directory với đúng ID; directory là mock nên chưa chứng minh membership thật được kiểm tra trong database. Nó cũng chưa kiểm tra credential, quyền phê duyệt, workflow hoặc transaction. Những điều kiện đó thuộc các test tương ứng của authentication, directory và application service.

### 13.3. Test HTTP không tin header actor giả

Harness dưới đây giả định MockMvc có Spring Security filter chain, method security và service thật; fixture đã commit, API duyệt ánh xạ `AccessDeniedException` thành 403, và có CSRF token hợp lệ để đi tới kiểm tra nghiệp vụ.

```java
@Test
void actorHeaderCannotTurnSelfApprovalIntoCarolApproval() throws Exception {
    var f = fixtures.committedRequestCreatedByAlice();
    var before = inspect.businessSnapshot(f.requestId());

    var principal = new AppPrincipal(f.aliceId(), f.tenantId());
    var authentication = UsernamePasswordAuthenticationToken.authenticated(
        principal,
        null,
        List.of(new SimpleGrantedAuthority("PURCHASE_APPROVE"))
    );

    var body = Map.of(
        "expectedRevisionId", f.revisionId().toString(),
        "idempotencyKey", "approve-command-1"
    );

    mvc.perform(post("/purchase-requests/{id}/approve", f.requestId())
            .with(authentication(authentication))
            .with(csrf())
            .header("X-Actor-Id", f.carolId().toString())
            .contentType(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(body)))
        .andExpect(status().isForbidden());

    assertEquals(before, inspect.businessSnapshot(f.requestId()));
    assertEquals(0, inspect.approvalCount(f.requestId()));
}
```

Alice trong fixture có authority thô và membership hợp lệ để test thực sự đi tới quy tắc không tự duyệt. Nếu CSRF, authentication hoặc một fixture thiếu quyền chặn trước, test 403 có thể đạt nhưng không chứng minh điều đang muốn kiểm tra.

Spring Security Test hỗ trợ request postprocessor cho custom authentication. Cần gắn đúng Spring Security vào MockMvc; một standalone controller test không tự có đầy đủ filter/context integration. [Spring Security 7.0 — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/7.0/servlet/test/mockmvc/authentication.html).

Postprocessor đưa authentication vào test, vì vậy không chứng minh credential/JWT thật được xác minh đúng. Với JWT cần các test decoder/validator hoặc luồng HTTP dùng token phù hợp để kiểm tra chữ ký, issuer, audience và thời hạn theo cấu hình.

### 13.4. Ma trận kiểm thử cần thiết

| Nhóm | Ca cần kiểm chứng |
| --- | --- |
| Nguồn danh tính | Body/header/query không thay actor đã xác thực |
| Anonymous | Context có anonymous token vẫn không cấp actor nghiệp vụ |
| Principal | Sai kiểu hoặc thiếu mapping bị từ chối, không parse tên để fallback |
| Tenant | Principal T1 không duyệt đối tượng T2; tenant input không mở rộng membership |
| Quyền | Authority thô có nhưng quyền đối tượng không có; quyền bị thu hồi |
| Approval | Tự duyệt, revision thay đổi, yêu cầu đã hủy hoặc đã có quyết định |
| Idempotency | Cùng lệnh không tạo approval mới; actor khác không dùng key để lấy dữ liệu ngoài quyền |
| Proxy | Gọi Spring bean thật áp dụng method security; đường self-invocation được kiểm soát |
| Async | Hai task khác actor chạy trên cùng pool không lẫn identity |
| Cleanup | Exception trong task không để context sang task kế tiếp |
| JWT | Token hợp lệ nhưng account/membership không hợp lệ bị chặn |
| Worker | Thiếu context không fallback system; initiatedBy và executedBy được tách |
| Audit | Actor từ server, đúng tenant/revision; không ghi token/credential |
| Assurance | Remember-me hoặc thiếu step-up không đạt policy của hành động nhạy cảm |

Với kiểm thử thread pool, dùng pool nhỏ có thể tái sử dụng cùng thread, barrier/timeout hữu hạn và kiểm tra cả task có context lẫn task không được phép kế thừa. Không chỉ kiểm tra một task của một user rồi kết luận không có rò danh tính.

## 14. Bài tập áp dụng

Một ứng dụng Spring MVC cho phép phê duyệt mua hàng. Controller hiện nhận `approverId` trong body. Service kiểm tra role APPROVER nhưng không kiểm tra tenant của đối tượng. Một task dùng `CompletableFuture` đọc context để ghi audit; khi không tìm thấy actor, code chuyển sang tài khoản system.

Hãy thực hiện:

1. Vẽ luồng danh tính từ authentication tới quyết định phê duyệt và chỉ ra dữ liệu nào không được tin từ client.
2. Thiết kế principal/actor mapping với account ID ổn định, tenant và kiểm tra membership.
3. Sửa inbound contract để không nhận người duyệt như nguồn actor.
4. Đặt kiểm tra quyền đối tượng, không tự duyệt, revision và idempotency tại ranh giới phù hợp.
5. Xác định hành vi khi anonymous, principal sai kiểu, context thiếu hoặc quyền bị thu hồi.
6. Chọn cơ chế async cho task ngắn và mô hình service/delegation cho job bền vững.
7. Viết test giả header/body actor, cross-tenant, anonymous và context cleanup trên thread pool.
8. Xác định actor, initiatedBy, executedBy và revision cần lưu trong audit.

Bài làm đạt phải chứng minh danh tính được lấy từ ranh giới authentication tin cậy, được ánh xạ đúng vào nghiệp vụ và không bị input hoặc thread reuse thay thế. Danh tính đúng sau đó phải đi cùng quyền, trạng thái, revision và chống lặp để bảo vệ hành động thực tế.
