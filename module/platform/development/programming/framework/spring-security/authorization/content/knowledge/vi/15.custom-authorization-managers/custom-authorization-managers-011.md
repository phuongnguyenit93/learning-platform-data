# Quản lý exception, dữ liệu thiếu và quyết định mặc định an toàn

## 1. Mục tiêu

Một `AuthorizationManager<T>` tùy chỉnh của Spring Security không chỉ quyết định người dùng có authority nào. Nó còn phải trả lời khi dữ liệu để kiểm tra quyền bị thiếu, khi principal chưa xác thực, khi ACL service trả `null`, khi truy vấn lỗi hoặc khi nhiều manager cùng tham gia một quyết định.

**Nguyên tắc cốt lõi:** chỉ cho phép thực hiện thao tác nhạy cảm khi có **quyết định ALLOW rõ ràng, dựa trên dữ liệu và danh tính đáng tin**. Thiếu bằng chứng hoặc lỗi đánh giá không được mặc định thành cho phép.

Nhưng “fail closed” không có nghĩa cứ bắt mọi exception rồi trả HTTP 403. Một tài khoản **bị từ chối đúng policy** và một hệ thống phân quyền **không khả dụng** đều không được thực hiện hành động, song cần phân biệt về thông báo lỗi, logging, retry, audit và vận hành.

Bài học này tập trung vào cách thiết kế hợp đồng của custom `AuthorizationManager`: kết quả ALLOW/DENY/ABSTAIN, exception, dữ liệu thiếu, default khi phối hợp manager, ví dụ Spring Security theo phiên bản và kiểm thử để chứng minh không có nhánh fail-open.

## 2. Phân biệt ALLOW, DENY, ABSTAIN và ERROR

| Trạng thái | Ý nghĩa | Biểu diễn trong Spring Security | Thực hiện thao tác nhạy cảm? |
|---|---|---|---|
| **ALLOW** | Chính sách có đủ dữ liệu, cho phép | `new AuthorizationDecision(true)` | Có, nếu các điều kiện bắt buộc khác cũng đạt |
| **DENY** | Chính sách có đủ căn cứ để từ chối hoặc thiếu điều kiện bắt buộc | `new AuthorizationDecision(false)` | Không |
| **ABSTAIN** | Manager **không ra quyết định**, có thể ủy quyền cho thành phần khác | `null` | Không được tự suy ra ALLOW hoặc DENY; xem caller/composition |
| **ERROR** | Kiểm tra không hoàn tất vì lỗi hạ tầng hoặc lập trình | Exception được phân loại | Không; xử lý lỗi có kiểm soát |

Ở một `AuthorizationManager`, `null` **không đồng nghĩa** với `AuthorizationDecision(false)`. Nó có ý nghĩa “abstain”. Nếu manager là lớp bảo vệ duy nhất của một use case bắt buộc được bảo vệ, trả null khi thiếu tenant, sai owner hoặc backend timeout thường là lựa chọn nguy hiểm.

Ví dụ về ba kết quả thay thế:

~~~java
return new AuthorizationDecision(true);   // ALLOW
return new AuthorizationDecision(false);  // DENY
return null;                              // ABSTAIN, chỉ dùng có chủ đích
~~~

Ba dòng trên minh họa ba nhánh khác nhau, **không** phải một method Java được viết liên tiếp như vậy.

**Lỗi hạ tầng không phải abstain theo nghĩa nghiệp vụ.** Một policy engine timeout không có nghĩa manager “không quan tâm” đến tài nguyên này. Thao tác phải dừng; hệ thống có thể ném exception để báo lỗi hoặc chuyển sang quyết định từ chối theo chính sách dự phòng đã được thống nhất.

## 3. Hợp đồng phiên bản trước khi viết code

Chữ ký Java của `AuthorizationManager<T>` thay đổi theo Spring Security. Phải kiểm tra version của `spring-security-core` **trên compile classpath và runtime classpath của module thực tế**, không đoán theo tên Spring Boot starter.

| Phiên bản | Phương thức abstract cần hiện thực | Phương thức bổ sung | Kết quả |
|---|---|---|---|
| Spring Security 6.3 | `check(Supplier<Authentication>, T)` | `verify(...)` default | `AuthorizationDecision` hoặc `null` |
| Spring Security 6.4–6.5 | `check(Supplier<Authentication>, T)` **vẫn abstract dù deprecated** | `authorize(...)` default, `verify(...)` default | `authorize` dùng `AuthorizationResult` |
| Spring Security 7.x | `authorize(Supplier<? extends Authentication>, T)` abstract | `verify(...)` default; `check` đã bị loại khỏi interface | `AuthorizationResult` hoặc `null` |

Javadoc 7.x có thể ghi `Supplier<? extends @Nullable Authentication>` vì annotation nullability. Khi hiện thực bằng Java, wildcard `? extends` cần khớp API; trong 6.5 chữ ký `Supplier<Authentication>` khác. `AuthorizationDecision` implements `AuthorizationResult` nên có thể trả `new AuthorizationDecision(granted)` từ method 7.x.

**Không xóa `@Override` để che lỗi version.** Nếu compiler báo “does not override”, cần đọc đúng Javadoc của phiên bản được build. Một method Java không được Spring interceptor gọi có thể khiến bảo vệ thực tế không đúng mong đợi.

Xem Javadoc chính thức:
- [AuthorizationManager 6.3](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 7.x](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html).

## 4. Ma trận dữ liệu thiếu và quyết định an toàn

| Trường hợp | Nguyên nhân | Hành vi phù hợp khi quyền bắt buộc |
|---|---|---|
| `Authentication` null | Chưa có danh tính hoặc đường gọi không truyền context | Không cấp; cần xác thực hoặc báo lỗi luồng gọi |
| `AnonymousAuthenticationToken` | Có object authentication nhưng là anonymous | Không cấp quyền tài nguyên riêng |
| Thiếu authority | Actor đã xác thực không có quyền thao tác | DENY |
| Tenant claim null/absent/rỗng | Token không có scope bắt buộc | DENY, không lấy tenant từ query parameter để thay thế |
| Resource ID null, âm, bằng 0 nếu ID cần dương | Request không hợp lệ | DENY hoặc input error trước khi đọc |
| Resource không nằm trong tenant của actor | Phạm vi dữ liệu không khớp | DENY hoặc NOT_FOUND theo policy chống lộ tồn tại |
| Owner/ACL trên bản ghi null | Thiếu bằng chứng object-level permission | Không cấp; phân biệt dữ liệu lỗi với tài nguyên public thật |
| Permission service trả false | Chính sách từ chối hợp lệ | DENY |
| Permission service trả null | Không có quyết định có nghĩa | Không cấp; DENY hoặc lỗi hạ tầng tùy contract |
| Permission service timeout/503 | Sự cố dependency | Không cấp; báo lỗi có kiểm soát/ghi metric |
| Dữ liệu kết quả từ backend bị hỏng schema | Không thể tin quyết định | Không cấp; báo lỗi |
| Lỗi `ClassCastException`, `NullPointerException` trong policy | Bug hoặc mismatch kiểu | Không cấp; phải sửa bug, không swallow rồi allow |
| Không có rule phù hợp với đối tượng | Policy thiếu cấu hình | Default an toàn là DENY |
| Manager được thiết kế chỉ xử lý một nhóm object, không phải nhóm hiện tại | Chủ đích không tham gia quyết định | Có thể ABSTAIN nếu composition được bảo vệ và đã test |

**Không suy diễn “public” khi owner/tenant/ACL là null.** Tài nguyên public cần một thuộc tính và chính sách public tường minh được quản trị hợp lệ.

**Không coi `authentication != null` hoặc `isAuthenticated()` đơn lẻ luôn xác nhận user thật.** Một số anonymous token có thể có trạng thái authenticated. Với quyền riêng tư phải phân biệt anonymous bằng cơ chế tin cậy phù hợp; có thể dùng `AuthenticatedAuthorizationManager` hoặc `AuthenticationTrustResolver` nếu bài toán đòi hỏi.

## 5. Ranh giới dữ liệu tin cậy

Các dữ liệu khác nhau có mức độ tin cậy khác nhau:

~~~text
HTTP/JWT/message metadata do client khai
        |
        v
Xác thực nguồn: chữ ký, issuer, audience, session, workload identity
        |
        v
Trusted actor + verified tenant + authority
        |
        v
Resource trong dữ liệu: query theo tenant + ID, kiểm tra owner/ACL
        |
        v
AuthorizationManager --> ALLOW / DENY / lỗi kiểm tra
~~~

Khi một token không có tenant, tuyệt đối không lấy `request.getParameter("tenant")` để làm tenant đã xác thực. Trong các hệ đa tenant, truy cập theo ID phải kết hợp scope tenant ở repository hoặc policy có khả năng bảo vệ tương đương.

Phân biệt hai câu hỏi:
1. Actor có quyền thao tác như `document:read` hay không?
2. Actor có quyền xem **document cụ thể trong tenant đang xét** hay không?

Một role hoặc authority chung không tự trả lời câu thứ hai. Nếu kiểm tra ACL từ service ngoài, result phải gắn với đúng actor, tenant, resource, operation và version chính sách.

Các giá trị sentinel như `"public"`, `"default"`, `"guest"` không được tự động gán khi một claim bắt buộc bị thiếu. Đó có thể là giá trị hợp lệ của nghiệp vụ khác, nhưng không phải phép thay thế cho bằng chứng quyền.

## 6. Boolean.TRUE.equals: hữu ích nhưng không che mất outage

Giả sử một permission gateway trả `Boolean`:

~~~java
Boolean granted = permissionGateway.canRead(actorId, documentId);
return new AuthorizationDecision(Boolean.TRUE.equals(granted));
~~~

Ưu điểm: `Boolean.TRUE.equals(granted)` chỉ trả true khi backend thật sự trả `Boolean.TRUE`, còn false hoặc null đều không grant. Nó tránh `NullPointerException` do unboxing. Phù hợp nếu contract của gateway định nghĩa null là **không được cấp quyền**.

Nếu gateway dùng null để biểu thị **không thể quyết định**, giữ ý nghĩa này:

~~~java
Boolean granted = permissionGateway.canRead(actorId, documentId);
if (granted == null) {
    throw new PermissionLookupUnavailableException(
            "Permission backend returned no decision");
}
return new AuthorizationDecision(granted);
~~~

Đây là đoạn **tích hợp ứng dụng**: `permissionGateway` và exception được ứng dụng định nghĩa. Điều quan trọng là tầng phía trên không xử lý exception bằng cách cho thao tác chạy.

Nguy hiểm:

~~~java
Boolean granted = permissionGateway.canRead(actorId, documentId);
return new AuthorizationDecision(
        granted == null || granted.booleanValue());
~~~

Khi backend trả null, biểu thức trên cấp quyền. Tương tự, `catch (Exception ex) { return new AuthorizationDecision(true); }` là **fail-open**, dù được viết với lý do “tăng availability”.

Không có lựa chọn dự phòng nào có thể tự tạo bằng chứng quyền nếu backend không thể cung cấp kết quả. Nếu thực sự có cache quyền phục vụ khi backend mất kết nối, cache phải được thiết kế riêng về tính hợp lệ, actor, tenant, resource, expiry/revocation và rủi ro sử dụng quyết định cũ; không tự “cache ALLOW mãi mãi”.

## 7. Ví dụ Spring Security 7.x: manager từ chối an toàn

Ví dụ sau dùng `AuthorizationManager<DocumentReadManager.Access>` và hợp đồng rõ về dữ liệu thiếu. Nó dành cho **dự án đã có Spring Security 7.x** và có thể biên dịch sau khi khai báo dependencies thích hợp. Một file `DocumentReadManager.java`:

~~~java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class DocumentReadManager
        implements AuthorizationManager<DocumentReadManager.Access> {

    public record Access(long documentId, String requestedTenant) { }

    public interface TenantResolver {
        String verifiedTenant(Authentication authentication);
    }

    public interface PermissionGateway {
        Boolean canRead(String tenant, String actorName, long documentId);
    }

    public static final class PermissionUnavailableException
            extends RuntimeException {
        public PermissionUnavailableException(String message) {
            super(message);
        }
    }

    private final TenantResolver tenantResolver;
    private final PermissionGateway gateway;

    public DocumentReadManager(TenantResolver tenantResolver,
                               PermissionGateway gateway) {
        this.tenantResolver = tenantResolver;
        this.gateway = gateway;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> supplier, Access access) {

        if (access == null || access.documentId() <= 0
                || access.requestedTenant() == null
                || access.requestedTenant().isBlank()) {
            return new AuthorizationDecision(false);
        }

        Authentication actor = supplier.get();
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        boolean authorizedForAction = actor.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));
        if (!authorizedForAction) {
            return new AuthorizationDecision(false);
        }

        String trustedTenant = tenantResolver.verifiedTenant(actor);
        if (trustedTenant == null
                || !trustedTenant.equals(access.requestedTenant())) {
            return new AuthorizationDecision(false);
        }

        Boolean result = gateway.canRead(
                trustedTenant, actor.getName(), access.documentId());

        if (result == null) {
            throw new PermissionUnavailableException(
                    "Authorization backend did not provide a decision");
        }
        return new AuthorizationDecision(result);
    }
}
~~~

**Các điều kiện để dùng đúng:**

- `TenantResolver` phải lấy tenant từ identity đã xác thực, không coi chuỗi `requestedTenant` là nguồn tin cậy. `Access` chỉ là ngữ cảnh cần so sánh; nếu yêu cầu API có tenant khác, bị từ chối.
- `PermissionGateway.canRead` phải kiểm tra đúng document, tenant, owner/ACL và trạng thái. Trả false khi có quyết định từ chối, null nếu contract báo không thể quyết định.
- Gateway có thể ném timeout exception cụ thể. Không bắt và biến thành ALLOW. Khi không có kết quả hợp lệ, thao tác không được tiếp tục.
- `Authentication.getAuthorities()` và `actor.getName()` phải phù hợp với authentication mechanism đang dùng.
- Đây là **manager cho kiểu context `Access`**, không phải manager HTTP `RequestAuthorizationContext`. Nó chỉ chạy nếu code thực sự gắn vào ranh giới tương ứng hoặc gọi với cơ chế enforcement đúng. Tạo bean mà không đăng ký interceptor **không tự bảo vệ API**.
- Việc return DENY đối với trường ID/scope thiếu khác với xử lý permission backend outage. Một bên là policy/validation, bên kia là lỗi vận hành cần được giám sát.

Với Spring Security **6.3 hoặc 6.4–6.5**, không copy nguyên chữ ký 7.x. Nếu trực tiếp implements `AuthorizationManager<T>` ở 6.x, phương thức bắt buộc là:

~~~java
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        Access access) {
    return evaluateWithSharedPolicy(authentication.get(), access);
}
~~~

Đây là **mảnh ghép chữ ký**, không phải một class độc lập: helper `evaluateWithSharedPolicy` có contract trả `AuthorizationDecision`. Ở 6.4–6.5, `authorize(...)` là default nhưng `check(...)` vẫn abstract dù deprecated. Ở 7.x, `check` đã bị loại khỏi interface, còn `authorize` là abstract. Không để adapter 6.x và 7.x có chính sách quyết định khác nhau.

## 8. Exception nào là DENY, exception nào là lỗi hạ tầng?

Một custom manager có thể làm việc với authentication, repository, service ACL hoặc OPA. Phân loại:

**Từ chối theo chính sách**: actor không có authority, sai tenant, thiếu ID, ACL trả false, trạng thái tài nguyên không cho đọc. Trả negative decision. Khi chạy qua framework, interceptor có thể tạo `AccessDeniedException` hoặc subtype tương ứng của phiên bản.

**Lỗi xác thực**: token không hợp lệ, thiếu credential hoặc session không đúng. Đây là vấn đề của authentication pipeline; thường cần challenge/login qua `AuthenticationEntryPoint`, không phải custom manager tự gán role hay tenant.

**Lỗi dependency**: database/service quyền timeout, trả response malformed, policy server unavailable. Không cấp; tùy contract có thể ném exception hạ tầng có kiểu rõ hoặc map sang DENY kèm metric. Tránh bắt rồi bỏ qua.

**Lỗi code/config**: `ClassCastException`, thiếu bean, sai generic context, `NullPointerException` vì dereference, method security không bật. Phải coi là lỗi cần sửa, không biến thành quyết định ALLOW.

### Hai cách fail-closed có đánh đổi

| Chiến lược | Điều khách hàng thấy | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Trả `AuthorizationDecision(false)` khi backend lỗi | Thường là denied/403 sau HTTP mapping | Không thực hiện thao tác, đơn giản cho enforcement | Che khuất outage nếu thiếu metric; user hiểu nhầm lỗi là thiếu quyền |
| Ném exception hạ tầng có kiểm soát | 5xx/503 khi adapter ánh xạ đúng | Phân biệt sự cố vận hành với quyền bị từ chối | Cần exception mapping, monitoring và bảo đảm không làm side effect |

Không có lựa chọn duy nhất cho mọi hệ thống. Nhưng **cả hai phải chặn side effect**, không được fallback sang permit. Chọn trước trong thiết kế, thay vì để một lập trình viên bất kỳ catch rồi quyết định.

Ví dụ anti-pattern:

~~~java
try {
    return new AuthorizationDecision(remotePolicy.canWrite(actor, object));
} catch (Exception exception) {
    return new AuthorizationDecision(true);
}
~~~

Ngược lại, một mẫu truyền lỗi (snippet tích hợp):

~~~java
try {
    Boolean grant = remotePolicy.canWrite(actor, object);
    if (grant == null) {
        throw new PermissionUnavailableException("Missing decision");
    }
    return new AuthorizationDecision(grant);
} catch (PermissionBackendTimeoutException exception) {
    throw new PermissionUnavailableException("Backend unavailable");
}
~~~

Trong ứng dụng thật, exception custom có constructor nhận `cause` để bảo toàn nguyên nhân; không in token/ACL ra client hoặc log. Không bắt rộng `RuntimeException` rồi nuốt lỗi lập trình một cách tùy tiện.

## 9. verify không phải chính sách "null = deny"

Mặc định, `AuthorizationManager.verify(...)` gọi manager và ném `AccessDeniedException` khi gặp **negative decision**. Với kết quả `null` từ manager, framework xem là **abstain**, không nhất thiết ném lỗi giống DENY.

Mẫu dễ nhầm:

~~~java
AuthorizationManager<Object> abstain = (auth, object) -> null;
abstain.verify(() -> authenticatedUser, new Object());
~~~

Đây là snippet tích hợp Spring Security 7.x, với `authenticatedUser` là fixture có sẵn. Nó cho thấy không nên dùng `verify` như một phép ép “null → 403” cho use case bắt buộc.

Nếu tự gọi manager và cần quyết định dương tính rõ ràng:

~~~java
AuthorizationResult result =
        manager.authorize(() -> authenticatedUser, access);
if (result == null || !result.isGranted()) {
    throw new AccessDeniedException("Authorization required");
}
// Chỉ sau đây mới thực hiện hành động nhạy cảm.
~~~

Mã trên là mảnh ghép 7.x, phụ thuộc biến và import phù hợp. Tuy nhiên, trong ứng dụng Spring thường nên cấu hình **interceptor/HTTP DSL** cho framework thực thi rule, thay vì rải các lời gọi manager thủ công khắp nghiệp vụ.

**Không bắt `AccessDeniedException` rồi tiếp tục mutate**. Exception là tín hiệu dừng; nếu bắt để log, phải dừng/rethrow hoặc ánh xạ thành lỗi khác mà không đi tiếp.

## 10. Composition: allOf và anyOf có thể gây bất ngờ

Spring Security có `AuthorizationManagers.allOf(...)` và `anyOf(...)` để kết hợp các manager. Nếu policy con trả `null`, manager kết hợp có thể cho qua thay vì coi null như DENY. Đặc biệt, Javadoc mô tả `allOf(managers...)` cho phép khi mọi manager cho phép **hoặc abstain**, và trường hợp không có manager cũng được coi như granted.

Do đó nếu tenant manager, owner manager và authority manager đều trả null khi thiếu dữ liệu, một cấu hình không có all-abstain default an toàn có thể làm mất hiệu lực bảo vệ.

Có overload định nghĩa rõ default khi mọi delegate abstain:

~~~java
AuthorizationManager<RequestAuthorizationContext> combined =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false),
                tenantManager,
                authorityManager,
                resourceManager);
~~~

Đây là snippet tích hợp, các manager phải cùng generic context và đã được khởi tạo. Nó không biến policy yếu thành mạnh: một manager bắt buộc vẫn nên trả **DENY** khi điều kiện của nó không thỏa. Overload có `AuthorizationDecision(false)` chỉ định trường hợp **all-abstain** là DENY, nhưng phải test cả hỗn hợp grant/deny/abstain. Xem đúng version trước khi áp dụng API.

Với `anyOf`, một grant từ nhánh khác có thể đủ để mở quyền ngay cả khi rule tenant không thỏa, tùy semantics cấu hình. Đừng cấu hình “tenant OR authority” khi ý định thật là “tenant AND (owner OR shared) AND authority”.

**Quy tắc cho policy bắt buộc:** thiếu tenant → DENY; thiếu quyền object → DENY; backend không có kết quả → ERROR hoặc DENY có chủ đích; ABSTAIN chỉ dùng khi có phân công trách nhiệm rõ ràng giữa các manager.

## 11. ExceptionTranslationFilter và mã HTTP

`AuthorizationManager` quyết định quyền, không trực tiếp quyết định mã HTTP. Trong Spring Security Servlet, `ExceptionTranslationFilter` chuyển một số exception bảo mật trong filter chain thành phản hồi thông qua `AuthenticationEntryPoint` và `AccessDeniedHandler`.

| Tình huống | Mã/luồng thường gặp | Điều phải chú ý |
|---|---|---|
| Chưa xác thực, cần credentials | 401/challenge hoặc redirect login | Phụ thuộc cơ chế xác thực của ứng dụng |
| Đã xác thực nhưng không đủ quyền | 403 | HTTP adapter xác định cách trả body |
| Không tìm thấy tài nguyên hoặc giấu sự tồn tại | 404 theo policy API | Không tiết lộ ID tồn tại ở tenant khác |
| Authorization backend lỗi | 5xx/503 thích hợp khi propagate exception hạ tầng | Không cho phép thao tác, ghi metric |
| Request thiếu field bắt buộc | 400/422 tùy API | Validation không thay cho authorization |

`ExceptionTranslationFilter` không tự chuyển **mọi** runtime exception thành 403; nó chủ yếu xử lý `AuthenticationException` và `AccessDeniedException` trong phạm vi filter chain bắt được. Với MVC exception handler, servlet error dispatch, asynchronous task hoặc message consumer, cần kiểm chứng tuyến exception thực tế của stack đang chạy.

Với lỗi backend permission, tránh tự ném `AuthenticationException` như thể user nhập sai mật khẩu. Trường hợp đó cần thông tin vận hành về dependency unavailable; phải dừng action nhưng không đánh đồng với authentication failure.

Nếu dùng `@ControllerAdvice` để trả JSON, đừng viết handler tổng quát bắt `Exception` rồi trả `200 OK` với body “warning” khi tác vụ ghi đã bị từ chối. Hãy bảo toàn status, transaction và audit, đồng thời không đưa JWT, ACL, response nội bộ hoặc stack trace ra ngoài.

## 12. Exception và transaction: chặn trước side effect

Đối với thao tác ghi, đặt authorization **trước** mutation. Không dựa duy nhất vào `@PostAuthorize` để phát hiện sai quyền sau khi method đã có side effect.

Luồng lý tưởng:

~~~text
Actor/scope đã xác thực
  -> manager kiểm tra authority
  -> đọc resource theo tenant tin cậy
  -> object-level policy / ACL
  -> chỉ khi ALLOW: mutate / persist / publish event
  -> commit đúng transaction
~~~

Khi permission backend lỗi, cần dừng trước khi ghi. Nếu exception xảy ra giữa transaction, quy tắc rollback phụ thuộc exception type, advice order và transaction configuration; trong Spring, runtime exception thoát ra ngoài transaction interceptor thường kích hoạt rollback theo mặc định. Nếu code **bắt rồi nuốt** exception, transaction ngoài có thể vẫn commit thay đổi trước đó.

Đối với message consumer/batch, phân biệt all-or-nothing và partial success; từng item cần được kiểm tra rõ và retry không được tạo đường bypass. Ngoài ra cần idempotency và quyền được kiểm tra tại **thời điểm thực thi**, không chỉ khi message được phát.

## 13. Java 17 độc lập: chỉ ALLOW mới được thực thi

Ví dụ chạy được bằng JDK 17+, không cần Spring. Mục tiêu là biểu diễn **DENY khi thiếu dữ liệu** và **UNAVAILABLE khi backend chưa ra quyết định**, đồng thời chỉ cho phép action khi có ALLOW.

Tạo tệp `SafeDecisionDemo.java`:

~~~java
public class SafeDecisionDemo {
    enum Decision { ALLOW, DENY, UNAVAILABLE }

    record Access(String actor, String verifiedTenant,
                  String resourceTenant, long documentId) { }

    interface PermissionLookup {
        Boolean canRead(Access access);
    }

    static final class BackendUnavailable extends RuntimeException { }

    static Decision evaluate(Access access, PermissionLookup lookup) {
        if (access == null
                || access.actor() == null || access.actor().isBlank()
                || access.verifiedTenant() == null
                || access.verifiedTenant().isBlank()
                || access.resourceTenant() == null
                || access.resourceTenant().isBlank()
                || access.documentId() <= 0
                || !access.verifiedTenant().equals(access.resourceTenant())) {
            return Decision.DENY;
        }

        try {
            Boolean permission = lookup.canRead(access);
            if (permission == null) {
                return Decision.UNAVAILABLE;
            }
            return permission ? Decision.ALLOW : Decision.DENY;
        } catch (BackendUnavailable exception) {
            return Decision.UNAVAILABLE;
        }
    }

    static void show(String label, Access access, PermissionLookup lookup) {
        Decision result = evaluate(access, lookup);
        System.out.println(label + ": " + result
                + ", execute=" + (result == Decision.ALLOW));
    }

    public static void main(String[] args) {
        Access ok = new Access("an", "north", "north", 7L);
        Access otherTenant = new Access("an", "north", "south", 7L);

        show("allowed", ok, a -> true);
        show("denied", ok, a -> false);
        show("missing-tenant",
                new Access("an", null, "north", 7L), a -> true);
        show("wrong-tenant", otherTenant, a -> true);
        show("no-decision", ok, a -> null);
        show("outage", ok, a -> { throw new BackendUnavailable(); });
    }
}
~~~

Chạy:

~~~bash
javac SafeDecisionDemo.java
java SafeDecisionDemo
~~~

Stdout chính xác:

~~~text
allowed: ALLOW, execute=true
denied: DENY, execute=false
missing-tenant: DENY, execute=false
wrong-tenant: DENY, execute=false
no-decision: UNAVAILABLE, execute=false
outage: UNAVAILABLE, execute=false
~~~

Phân tích: thiếu tenant hoặc tenant lệch bị chặn trước khi gọi backend. Backend trả null hoặc ném exception nhận diện không làm action được phép. Chỉ `ALLOW` mới tạo `execute=true`. Demo giả định `verifiedTenant` đến từ nguồn tin cậy; mã Java thuần không tự chứng minh danh tính. Trong ứng dụng thật, không tự bắt mọi `RuntimeException` rồi coi đó là một kết quả nghiệp vụ thông thường; chỉ bắt exception dependency có contract rõ hoặc cho lỗi lan lên tầng xử lý.

## 14. Kiểm thử để chứng minh fail closed

Bảng test tối thiểu:

| Đầu vào / tình trạng | Kỳ vọng |
|---|---|
| Principal thật, authority đủ, tenant đúng, ACL true | ALLOW |
| Thiếu authority | DENY |
| Principal anonymous nhưng khác null | Không cấp |
| Supplier trả null | Không cấp |
| Tenant claim thiếu, null hoặc rỗng | Không cấp |
| Resource ID sai/không tồn tại theo scope | Không cấp |
| Tenant actor A, resource thuộc B | DENY ngay cả khi backend mock trả true |
| ACL false | DENY |
| ACL null | Không cấp; xử lý theo contract lỗi hoặc từ chối |
| ACL timeout/5xx | Không cấp, có tín hiệu vận hành |
| Manager trả null | ABSTAIN, **không** giả định verify sẽ deny |
| Tất cả delegate abstain | Default DENY nếu tài nguyên bắt buộc bảo vệ |
| Một delegate DENY, delegate khác ALLOW | Theo phép AND/OR chủ đích; test chống grant ngoài ý muốn |
| Exception bị catch ở service | Không có mutation hoặc commit ngoài contract |
| Spring Security version thay đổi | Signature và interceptor được gọi đúng |

Một đoạn unit test tích hợp 7.x (fixture và AssertJ do project cung cấp):

~~~java
AuthorizationResult result =
        manager.authorize(() -> authenticatedUser, accessContext);

assertThat(result).isNotNull();
assertThat(result.isGranted()).isFalse();
~~~

Đối với 6.3/6.5 sử dụng `check(...)` theo hợp đồng. Không chỉ unit test manager trực tiếp: nếu chưa gắn nó vào HTTP DSL hoặc interceptor thì policy có thể hoàn toàn không chạy.

### Test end-to-end bắt buộc

1. Gửi HTTP request qua đúng SecurityFilterChain; test cả route không match và fallback `denyAll()`.
2. Gọi method Spring qua bean proxy thật; không phụ thuộc annotation trên private method hoặc self-invocation.
3. Với request unauthenticated, xác nhận challenge/401 hoặc behavior login tương ứng.
4. Với authenticated nhưng thiếu quyền, xác nhận denied và không có thay đổi database.
5. Giả lập permission backend timeout; xác nhận không update/publish side effect dù exception được HTTP mapping thành 503.
6. Test cùng user trên tenant khác, owner khác, record đã bị thu hồi ACL.
7. Test `verify` với negative và null; test `AuthorizationManagers.allOf/anyOf` với grant/deny/abstain.
8. Test cả message consumer/scheduled job nếu cùng use case được gọi từ ngoài HTTP.
9. Sau khi nâng Spring Security major, rebuild extension class, chạy integration test để phát hiện `NoSuchMethodError`/`AbstractMethodError`.

## 15. Logging, metrics và audit: đủ để vận hành nhưng không rò rỉ

Mỗi quyết định quan trọng nên có thông tin truy dấu:

- Operation (ví dụ `document:read`), loại tài nguyên, ID theo chính sách log an toàn.
- Actor và tenant **đã xác minh**, không ghi raw JWT hoặc credential.
- Kết quả ALLOW/DENY/ABSTAIN/ERROR, phiên bản policy và correlation ID.
- Với lỗi backend: loại lỗi (timeout, unavailable, invalid response), thời gian, số lần retry có giới hạn.
- Với deny: ghi lý do tổng quát an toàn, không đưa ACL chi tiết hoặc thông tin về resource của tenant khác ra response.

Không log toàn bộ principal object, Authorization header, nội dung token, database secret, stack trace nhạy cảm vào API body. Có thể tăng metric lỗi backend và alert để tránh việc một outage bị che giấu dưới một loạt 403.

**Cache authorization** (nếu có) phải key theo actor, tenant, resource, action và chính sách hiệu lực. Cache ALLOW sai scope hoặc quá lâu sau khi thu hồi permission tạo lỗi vượt quyền; không bao giờ dùng một cache key chỉ có resource ID trong môi trường multi-tenant.

## 16. Những anti-pattern cần loại bỏ

**1. Thiếu dữ liệu thì trả null.** Null là ABSTAIN, không phải DENY; composition có thể grant. **Sửa:** với policy bắt buộc, trả negative decision hoặc exception được xử lý có chủ đích.

**2. Gặp timeout thì permitAll.** Fail-open. **Sửa:** không cấp, giữ tín hiệu backend unavailable.

**3. Permission `Boolean null` được diễn giải là true.** Hỏng logic ba trạng thái. **Sửa:** `Boolean.TRUE.equals(permission)` nếu null nghĩa là không cấp, hoặc ném lỗi nếu null nghĩa là backend không xác định.

**4. Kiểm tra chỉ `authentication != null`.** Anonymous có thể khác null. **Sửa:** kiểm tra trust/authority thực.

**5. Tenant bị thiếu thì lấy từ request parameter.** Tin dữ liệu do client khai. **Sửa:** chỉ dùng tenant đã được xác minh.

**6. Bắt `AccessDeniedException` để log rồi cho method cập nhật chạy tiếp.** Vô hiệu hóa bảo vệ. **Sửa:** dừng và rethrow/handle an toàn.

**7. Tưởng `verify(null)` luôn ném lỗi.** Không đúng semantics abstain. **Sửa:** explicit DENY hoặc fail-closed caller.

**8. Tất cả manager abstain nhưng composition cho phép.** Lỗi default. **Sửa:** dùng default deny khi cần và test.

**9. Manager tồn tại trong context nhưng không được gắn vào matcher/interceptor.** Không bảo vệ hành động. **Sửa:** test integration điểm vào thật.

**10. Trộn API 6.x và 7.x.** Sai chữ ký, compile hoặc linkage exception. **Sửa:** kiểm tra phiên bản và `@Override` chuẩn.

**11. Lỗi backend được biến thành 403 mà không có metric.** Không fail-open nhưng che lỗi vận hành. **Sửa:** phân biệt DENY với ERROR, có alert/correlation.

**12. Dùng `@PostAuthorize` trên lệnh ghi để cứu lỗi phân quyền.** Quyền kiểm tra sau side effect có thể quá muộn. **Sửa:** bảo vệ trước mutation và transaction phù hợp.

## 17. Checklist thiết kế trước khi merge

- [ ] Hợp đồng `AuthorizationManager<T>` đúng version 6.x hay 7.x.
- [ ] ALLOW, DENY, ABSTAIN và lỗi hạ tầng được phân biệt rõ.
- [ ] Thiếu authentication/authority/tenant/resource ID dẫn tới không cấp quyền.
- [ ] Dữ liệu identity và tenant đến từ nguồn đã xác minh.
- [ ] ACL/owner/resource scope được kiểm tra theo đúng tài nguyên.
- [ ] Backend trả null/timeout không trở thành ALLOW.
- [ ] Việc dùng `verify` không dựa vào giả định null = deny.
- [ ] Default của `AuthorizationManagers.allOf/anyOf` đã được kiểm thử.
- [ ] Không nuốt `AccessDeniedException` rồi thực hiện side effect.
- [ ] Mã HTTP phản ánh được khác biệt unauthorized/forbidden/unavailable theo hợp đồng.
- [ ] Transaction, retry, cache, audit và logging không tạo đường bypass.
- [ ] Manager thực sự được gọi bởi HTTP/method/message interceptor.
- [ ] Test bao gồm anonymous, null, missing, wrong tenant, backend outage và no side effect.
- [ ] Không log token, credential, ACL hoặc thông tin nhạy cảm ngoài quyền.

**Kết luận:** Một `AuthorizationManager` tùy chỉnh an toàn không đoán quyền khi dữ liệu thiếu và không mở quyền khi gặp exception. Nó trả **DENY rõ ràng** khi điều kiện chính sách không được đáp ứng, giữ **ERROR rõ ràng** khi không thể kiểm tra, chỉ dùng **ABSTAIN** khi có chính sách composition được kiểm chứng, và không cho side effect chạy khi chưa có bằng chứng ALLOW.

## Tài liệu tham khảo

- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, quyết định positive/negative/null và `verify`.
- [Spring Security 6.5 API – AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check` và `authorize` ở 6.x.
- [Spring Security 7.x API – AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): chữ ký `authorize` và `verify`.
- [Spring Security API – AuthorizationManagers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, mặc định abstain.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): đăng ký và thực thi method authorization.
