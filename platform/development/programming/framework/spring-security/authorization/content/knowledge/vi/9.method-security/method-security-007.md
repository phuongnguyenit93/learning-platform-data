# Annotation ở lớp, phương thức, interface và quy tắc kế thừa

> **Module:** Spring Security – authorization  
> **Nhóm:** Method security  
> **Nội dung:** Cách Spring Security áp dụng `@PreAuthorize`, `@PostAuthorize` và các method-security annotations khi chúng nằm ở class, method, interface hoặc được khai báo trên các kiểu cha; ưu tiên và xung đột annotation; giới hạn Spring AOP proxy; ví dụ Java 17 và bộ kiểm thử chứng minh chính sách thực tế.

## 1. Bài toán: một method có thể “thấy” annotation từ đâu?

Một ứng dụng quản lý tài liệu có các lớp:

~~~java
@PreAuthorize("hasRole('USER')")
@Service
public class DocumentService {

    public String list() {
        return "Danh sách tài liệu";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(long id) {
        return "Đã xóa " + id;
    }
}
~~~

Câu hỏi quan trọng:

1. `list()` có cần `ROLE_USER` dù không tự ghi annotation?
2. `delete()` yêu cầu **chỉ** `ROLE_ADMIN`, hay cả `ROLE_ADMIN` **và** `ROLE_USER`?
3. Nếu `@PreAuthorize` được đặt ở một **interface**, implementation không ghi lại annotation thì còn được bảo vệ không?
4. Nếu một class implement **hai interface** với hai annotation `@PreAuthorize` khác nhau cho cùng một method, Spring chọn annotation nào?
5. Nếu method được annotate nhưng **tự gọi trong cùng bean** thì kiểm tra bảo mật có chạy không?
6. Cách kiểm thử nào đủ để kết luận annotation thực sự được áp dụng?

**Kết luận trước:** Với cơ chế method security theo proxy, một annotation `@PreAuthorize` trên class áp dụng mặc định cho các method được bảo vệ của class; `@PreAuthorize` trên method cụ thể **ghi đè annotation cùng loại trên class**. Interface có thể mang annotation được Spring Security tìm thấy qua hệ phân cấp, nhưng annotation xung đột được kế thừa từ nhiều interface phải được giải quyết tường minh; không có quy tắc “lấy interface khai báo trước là thắng”.

Cần phân biệt **ưu tiên của cùng một annotation type** với **nhiều annotation type khác nhau** được xử lý bởi các interceptor riêng. Chúng không cùng một thuật toán “override”.

## 2. Bật method security trước khi nói đến kế thừa

Trong Spring Boot 3.x / Spring Security 6.x, việc có dependency Spring Security hoặc rule HTTP **không tự bật** `@PreAuthorize`. Cần cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@EnableMethodSecurity` kích hoạt hạ tầng method authorization cho Spring-managed beans. Các `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` được hỗ trợ mặc định theo cấu hình thông dụng.

Các kiểu annotation khác cần bật tùy chọn:

~~~java
@EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
)
~~~

- `securedEnabled=true` hỗ trợ `@Secured`.
- `jsr250Enabled=true` hỗ trợ nhóm annotation Jakarta như `@RolesAllowed`, `@PermitAll` và `@DenyAll` theo cấu hình phù hợp.
- Với Spring Boot 3+, sử dụng namespace `jakarta.annotation.security` cho JSR-250; ví dụ trên blog cũ có `javax.annotation.security` có thể không tương thích.

**Quan trọng:** method security áp dụng khi **lời gọi đi qua Spring AOP advisor/proxy** hoặc cơ chế weaving được cấu hình. Đặt annotation lên một object do `new` tự tạo, method private hoặc một lời gọi nội bộ không đi qua proxy không đủ bảo đảm interceptor được thực thi.

HTTP authorization bằng `authorizeHttpRequests` và method authorization có thể cùng được áp dụng:

~~~text
HTTP request
   |
   v
Spring Security FilterChain
   +-- HTTP rule (path/method)
   |
   v
Controller
   |
   v
Spring-managed service proxy
   +-- method-security interceptor
   |
   v
Business method / repository
~~~

Một service cũng có thể được gọi từ scheduler, listener hoặc batch job không qua HTTP. Chính sách ở method có giá trị độc lập, nhưng caller ngoài HTTP phải xử lý `AccessDeniedException` phù hợp.

## 3. Cơ chế giải quyết annotation: tìm trên object hierarchy

Method security sử dụng Spring AOP pointcuts và cơ chế tìm metadata annotation trong **method và hệ phân cấp kiểu** của Spring-managed object. Với từng loại annotation được bật, Spring Security có interceptor/authorization manager riêng.

Hình dung một lời gọi `documentService.delete(42)`:

~~~text
Caller -> Spring proxy -> AOP advisor
                          |
                          v
              Tìm @PreAuthorize tương ứng
              - method cụ thể?
              - class chứa method?
              - declaration tương ứng ở parent/interface?
                          |
                          v
              PreAuthorizeAuthorizationManager
                          |
                   evaluate SpEL
                          |
                   allow / deny
                          |
                          v
                    method body
~~~

Phần tìm kiếm dựa vào **hạ tầng Spring Security**, không chỉ Java reflection thông thường. Một implementation method có thể không trực tiếp chứa annotation ở bytecode, trong khi Spring Security vẫn tìm và áp dụng annotation được khai báo trên method của interface.

### 3.1. Những phạm vi có thể khai báo

| Vị trí | Ví dụ | Tác động chính |
|---|---|---|
| Method implementation | `@PreAuthorize` ngay trên `delete()` | Policy riêng cho method đó |
| Class implementation | `@PreAuthorize` ngay trên `DocumentService` | Policy mặc định cho các method được interceptor bảo vệ trong class |
| Interface method | `@PreAuthorize` trên `DocumentApi.read()` | Contract bảo mật có thể được implementer kế thừa trong Spring method security |
| Interface type | `@PreAuthorize` trên `DocumentApi` | Chính sách mặc định ở interface cho các method được bảo vệ theo contract |
| Superclass method/type | Annotation ở declaration cha | Có thể được Spring method-security metadata resolver tìm qua hierarchy |
| Meta-annotation | `@CanReadDocument` được annotate bằng `@PreAuthorize` | Tên nghiệp vụ thay cho SpEL lặp lại |

**Không suy luận** rằng mọi vị trí trong bảng luôn hiệu quả trên mọi phương thức Java: còn phải xét loại proxy, khả năng override, visibility, cùng annotation type, xung đột interface và việc annotation có được bật hay không.

## 4. Annotation ở class: policy mặc định cho các method

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("hasRole('USER')")
public class CatalogService {

    public String list() {
        return "catalog";
    }

    public String detail(long id) {
        return "item-" + id;
    }
}
~~~

Một lời gọi **từ ngoài qua Spring proxy** tới `list()` hoặc `detail(...)` sẽ chịu kiểm tra `hasRole('USER')` nếu hệ thống đã bật method security và bean được proxy theo cách thích hợp.

Đây là cách có một baseline policy mà không cần viết lặp lại annotation ở từng method. Nó cũng có rủi ro: khi thêm method mới vào class, method đó có thể được bảo vệ theo baseline mà người viết không nhận ra; nếu baseline `permitAll` quá rộng, có thể vô tình làm lộ method mới.

### 4.1. Chính sách class-level không tự thêm annotation vào source/bytecode của từng method

Không nên viết test kiểu:

~~~java
boolean found = CatalogService.class
        .getMethod("list")
        .isAnnotationPresent(PreAuthorize.class);
~~~

rồi kết luận `false` nghĩa là method không được bảo vệ. `list()` không cần mang `@PreAuthorize` trực tiếp trong Java reflection khi class đã được annotate. Spring Security có resolver và advisor riêng.

Muốn chứng minh hiệu lực, phải gọi **bean Spring** qua proxy dưới các `Authentication` khác nhau và xác nhận allow/deny.

### 4.2. Có nên đặt annotation trên controller?

Spring Security cho phép method security ở controller hoặc service. Tuy nhiên với nghiệp vụ nhạy cảm, **service/use-case boundary** thường là nơi nên đặt quyền, bởi cùng service có thể được gọi qua REST, GraphQL, batch, message consumer hoặc code nội bộ.

~~~java
@Controller
@PreAuthorize("hasRole('USER')")
class MyController {
    // Có thể bảo vệ method được Spring AOP intercept.
}
~~~

Không được coi controller annotation là lý do bỏ object-level checks tại service/repository; quyền xem tài liệu của tenant khác vẫn phải kiểm tra.

## 5. Annotation ở method: ghi đè class-level cùng loại

Xét class:

~~~java
@Service
@PreAuthorize("hasRole('USER')")
public class CatalogService {

    public String list() {
        return "list";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(long id) {
        return "delete-" + id;
    }
}
~~~

Với `@PreAuthorize`:

- `list()` không có annotation cụ thể → dùng `hasRole('USER')` từ class.
- `delete(...)` có `@PreAuthorize` ngay trên method → **ghi đè điều kiện `@PreAuthorize` cấp class** thành `hasRole('ADMIN')`.
- Không mặc định hiểu `delete()` cần **cả** `ROLE_USER` **và** `ROLE_ADMIN`. Nếu muốn cả hai, hãy viết policy tường minh.

Ví dụ yêu cầu cả hai:

~~~java
@PreAuthorize("hasRole('USER') and hasRole('ADMIN')")
public String delete(long id) {
    return "delete-" + id;
}
~~~

Dù vậy, yêu cầu cả hai role không phải lúc nào cũng có ý nghĩa: nhiều hệ thống có role hierarchy trong đó ADMIN bao hàm USER, còn hệ thống khác lại có hai role độc lập. Chọn điều kiện theo nghiệp vụ thật.

### 5.1. Tránh hiểu “method-level càng cụ thể càng chặt” một cách máy móc

Một annotation method-level có thể **nới** chính sách class-level:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public class AdminService {

    @PreAuthorize("permitAll()")
    public String health() {
        return "ok";
    }
}
~~~

Ở ví dụ cùng `@PreAuthorize`, `health()` được thiết kế thành public ở tầng method authorization, dù baseline class đòi ADMIN. Nó vẫn có thể bị HTTP rule hoặc filter khác chặn.

Vì vậy, việc override không phải phép toán tự động chọn điều kiện nghiêm ngặt nhất. Khi review diff thêm annotation vào method, phải kiểm tra **policy mới có làm giảm yêu cầu cấp class không**.

### 5.2. Phương thức overload và tên method

Hai method tên giống nhau nhưng tham số khác:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String report(long id) { return "r-" + id; }

@PreAuthorize("hasAuthority('report:export')")
public byte[] report(long id, String format) {
    return new byte[0];
}
~~~

Đây là hai signature khác nhau và có thể có policy khác nhau. Test phải gọi **đúng overload**; không suy luận một annotation được “kế thừa theo tên method” từ overload này sang overload khác.

## 6. Annotation ở interface method: contract bảo mật

Một API dùng interface:

~~~java
public interface DocumentReader {

    @PreAuthorize("hasAuthority('document:read')")
    String read(long documentId);
}
~~~

Implementation:

~~~java
@Service
public class DefaultDocumentReader implements DocumentReader {

    @Override
    public String read(long documentId) {
        return "document-" + documentId;
    }
}
~~~

Trong cấu hình method security **proxy-based thông thường** của Spring Security, annotation ở interface method được framework nhận diện để áp dụng cho method implementation. Không cần copy `@PreAuthorize` sang implementation chỉ để Java compiler nhìn thấy nó.

Đây là lợi thế khi interface đại diện cho **security contract**: mọi implementation được Spring quản lý và truy cập qua cơ chế interceptor phù hợp đều có thể chia sẻ một policy.

**Tuy nhiên:** chỉ có contract ở interface không bảo vệ object tạo thủ công bằng `new DefaultDocumentReader()`; lời gọi không qua Spring proxy không được interceptor xử lý.

### 6.1. Annotation ở interface type

Có thể đặt policy mặc định cho cả interface:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public interface ReadOnlyDocumentApi {
    String list();
    String read(long id);
}
~~~

Các method được Spring method security áp dụng qua contract này có thể chịu policy ở interface type. Tuy vậy:

- Implementation có thể thêm method mới **không thuộc contract**; không nên dựa vào interface annotation để bảo vệ mọi method riêng thêm vào implementation.
- Nếu class implement nhiều interface, quy tắc ưu tiên/xung đột phải được test.
- Nếu muốn ràng buộc service đồng nhất, class-level annotation trên implementation có thể dễ audit hơn.
- Nếu interface được tái sử dụng ở module khác, một thay đổi annotation trên interface có thể tác động đến **nhiều bean**.

**Khuyến nghị:** khi đặt annotation trên interface, coi đó là một phần của API compatibility và security contract; review thay đổi như review thay đổi permission.

### 6.2. Java @Inherited không tương đương Spring method-security inheritance

Annotation Java có cơ chế `@Inherited`, nhưng đó không phải phép “copy annotation vào mọi method implement interface”. Theo cơ chế reflection chuẩn, `@Inherited` chỉ áp dụng nhất định cho **class annotations** trong chuỗi superclass, không làm interface annotation trở thành annotation trực tiếp của implementing class, và không tự làm method override kế thừa annotation.

Trong Spring Security, method-security resolver được thiết kế để tìm annotation trong hierarchy của bean. Do đó:

~~~text
Java reflection:
  ImplementationMethod.getDeclaredAnnotation(...)
    -> có thể null

Spring Security method interceptor:
  tìm trên method/type/interface hierarchy
    -> có thể tìm thấy rule interface
~~~

Đây là lý do **unit test dùng reflection thuần không thay thế được integration test Spring AOP**.

## 7. Quy tắc kế thừa giữa implementation và interface

Ở mức tư duy, một rule được khai báo trực tiếp trên **concrete method** có tính tường minh cao nhất. Policy lớp/interface có thể tạo mặc định cho method nếu không có rule cụ thể hơn của **cùng loại annotation**.

Ví dụ:

~~~java
public interface PaymentApi {
    @PreAuthorize("hasAuthority('payment:read')")
    String payment(long id);
}
~~~

Implementation muốn policy cụ thể hơn:

~~~java
@Service
public class PaymentService implements PaymentApi {

    @Override
    @PreAuthorize("hasAuthority('payment:read') and " +
                  "@paymentPolicy.canSee(authentication, #id)")
    public String payment(long id) {
        return "payment-" + id;
    }
}
~~~

Ở đây implementation method ghi policy mới, gồm **permission chung và kiểm tra tài nguyên** có chủ đích. Không nên annotate method chỉ bằng `hasAuthority('payment:special')` rồi giả định biểu thức interface `payment:read` vẫn được tự động AND vào, vì cùng loại `@PreAuthorize` có quy tắc override chứ không phải tích lũy vô điều kiện.

Snippet cần bean `paymentPolicy`, parameter name `#id` được discover đúng, `@EnableMethodSecurity` và Spring-managed invocation. Không phải Java độc lập.

### 7.1. Nếu muốn giữ cả baseline và restriction của method

Đọc rõ policy cũ trên class/interface, sau đó viết expression mới có **đủ những điều kiện cần giữ**:

~~~java
@PreAuthorize(
    "hasAuthority('payment:read') " +
    "and @paymentPolicy.canSee(authentication, #id)"
)
~~~

Hoặc chuyển policy chung vào một bean:

~~~java
@PreAuthorize("@paymentPolicy.canRead(authentication, #id)")
~~~

Bean `paymentPolicy` phải kiểm tra đầy đủ authentication, permission, tenant và resource. Tách ra bean có lợi khi policy phức tạp và cần unit test, nhưng cũng tạo phụ thuộc cần được kiểm soát trong Spring context.

### 7.2. Kế thừa từ superclass

Một subclass có thể được Spring Security bảo vệ theo annotation ở superclass/supermethod vì Spring method-security metadata resolver tìm trong hierarchy của object.

~~~java
@PreAuthorize("hasRole('USER')")
public abstract class BaseReportService {
    public String list() { return "reports"; }
}

@Service
public class MonthlyReportService extends BaseReportService {
    // Có thể sử dụng policy class/superclass khi qua Spring proxy.
}
~~~

Khi subclass override method, thêm annotation trên method mới hoặc thay đổi class hierarchy, **phải integration test**. Không nên giả định luật Java `@Inherited` giải thích đầy đủ kết quả của Spring AOP và các method-security pointcuts.

Đối với một method nhạy cảm, policy trực tiếp trên concrete service method có thể dễ hiểu hơn việc truy tìm nhiều tầng superclass/interface. Dùng inheritance để giảm lặp khi security contract thật sự đồng nhất.

## 8. Hai interface cùng khai báo annotation: xung đột và startup failure

Ví dụ:

~~~java
public interface SupportApi {
    @PreAuthorize("hasAuthority('support:manage')")
    void operate();
}

public interface AuditApi {
    @PreAuthorize("hasAuthority('audit:manage')")
    void operate();
}

@Service
public class OperationsService implements SupportApi, AuditApi {
    @Override
    public void operate() {
        // Logic nghiệp vụ
    }
}
~~~

Một concrete method `operate()` được kế thừa annotation `@PreAuthorize` từ **hai interface khác nhau**. Tài liệu Spring Security nêu rõ trường hợp này **không có cách chọn duy nhất** nên ứng dụng có thể **thất bại khi khởi động** lúc giải quyết cấu hình method security.

Không nên:

- Dựa vào thứ tự `implements SupportApi, AuditApi` để chọn.
- Dựa vào thứ tự reflection trả về interface.
- Mong framework tự ghép hai `@PreAuthorize` thành phép AND.
- Bắt một startup error rồi bỏ security annotation khỏi một interface một cách tùy tiện.

### 8.1. Giải quyết bằng annotation cụ thể trên method implementation

Nếu cả hai permission đều thực sự cần:

~~~java
@Service
public class OperationsService implements SupportApi, AuditApi {

    @Override
    @PreAuthorize(
        "hasAuthority('support:manage') " +
        "and hasAuthority('audit:manage')"
    )
    public void operate() {
        // Thực thi chỉ khi cả hai điều kiện đạt.
    }
}
~~~

Nếu chỉ một permission phù hợp với trách nhiệm của implementation thì concrete method phải chọn **policy phù hợp**, kèm giải thích. Việc thêm annotation trên concrete method giải quyết **ambiguity**; nó không tự bảo đảm rằng policy đã chọn là đủ chặt.

### 8.2. Chỉ một interface khai báo annotation

Khi một implementation có nhiều interface nhưng chỉ **một** interface mang `@PreAuthorize` cho method đó, có thể không có xung đột cùng loại. Dù vậy, luôn test method qua bean Spring vì các nguồn metadata khác như superclass hoặc meta-annotation có thể ảnh hưởng.

### 8.3. Nếu hai interface mang biểu thức giống nhau?

Đừng coi đó là một convention an toàn để trùng annotation. Tài liệu cảnh báo việc inherit annotation từ hai interface là mơ hồ; cấu hình cần được làm rõ trên concrete method, hoặc tái cấu trúc để chỉ có một contract security authoritative.

## 9. Nhiều annotation khác loại: xử lý theo chuỗi, thường kết hợp như AND

Xét:

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public Document readDocument(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Hai loại annotation trên cùng method không lặp cùng một interceptor:

1. `@PreAuthorize` được đánh giá **trước** method body, yêu cầu permission.
2. Nếu pass, method đọc dữ liệu.
3. `@PostAuthorize` được đánh giá **sau** method body, yêu cầu tài liệu trả về thuộc người gọi.
4. Request được nhận kết quả chỉ khi các kiểm tra cần thiết đều pass.

Theo tài liệu, nhiều method-security annotations khác nhau được xử lý **lần lượt** qua các interceptor và có thể xem là các yêu cầu cần đồng thời thỏa mãn. Tuy nhiên thời điểm chạy của chúng khác nhau; `@PostAuthorize` có thể từ chối **sau khi method đã chạy**, khác hẳn `@PreAuthorize`.

### 9.1. Không được lặp cùng loại `@PreAuthorize` trên một method

Không hợp lệ:

~~~java
// KHÔNG ĐƯỢC:
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("hasAuthority('document:delete')")
public void delete(long id) { }
~~~

Spring Security không hỗ trợ lặp cùng một annotation method security trên cùng method theo cách này. Hãy ghép điều kiện:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') and hasAuthority('document:delete')"
)
public void delete(long id) { }
~~~

Hoặc gọi một bean policy. Không tạo hai meta-annotations cùng ẩn `@PreAuthorize` và mong cơ chế tự ghép mà chưa xác nhận hỗ trợ; nên chuẩn hóa thành **một policy rõ ràng** để tránh xung đột.

### 9.2. Kế thừa cùng loại khác kết hợp khác loại

- `@PreAuthorize` ở method có thể ghi đè `@PreAuthorize` trên class.
- `@PreAuthorize` kết hợp với `@PostAuthorize` là **hai giai đoạn kiểm tra**.
- `@Secured`, `@RolesAllowed` và `@PreAuthorize` thuộc các hệ interceptor khác nhau khi được bật.
- Không nên dùng `@PermitAll` của JSR-250 để “vô hiệu hóa” một `@PreAuthorize` vẫn còn hiệu lực. Cần xác minh toàn bộ cấu hình; các annotation khác loại không tự mang nghĩa override nhau.
- Nếu nhiều loại annotation cùng tác động một lời gọi, test mọi trường hợp bất đồng ý định, ví dụ JSR-250 cho phép nhưng SpEL từ chối.

### 9.3. @PostAuthorize không thích hợp để bảo vệ thao tác ghi có side effect

Không nên dựa vào:

~~~java
@PostAuthorize("hasRole('ADMIN')")
public void transferMoney() {
    // Thay đổi database / gửi message ở đây.
}
~~~

để ngăn tiền đã được chuyển, vì method body có thể đã thực hiện side effect trước khi post-authorization kiểm tra. Với write operations, dùng `@PreAuthorize` và service policy kiểm tra **trước khi thay đổi trạng thái**. Nếu cần transaction rollback hoặc chính sách kiểm tra sau, phải thiết kế rõ transaction/advisor ordering, không giả định một exception ở cuối sẽ tự đảo tất cả side effects.

## 10. Meta-annotation: định nghĩa contract bảo mật theo ngôn ngữ nghiệp vụ

Khi nhiều method cần cùng một biểu thức, có thể dùng composed annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('document:read')")
public @interface CanReadDocument {
}
~~~

Dùng:

~~~java
@Service
public class DocumentSearchService {

    @CanReadDocument
    public String search(String term) {
        return term;
    }
}
~~~

Ưu điểm: ý nghĩa nghiệp vụ rõ ràng, ít copy-paste SpEL. Spring Security hỗ trợ tìm meta-annotations trong method-security pointcuts.

### 10.1. @Target và @Retention là hợp đồng

- `@Target(METHOD)` nếu chỉ được dùng ở method.
- `@Target(TYPE)` nếu cho phép đặt trên class/interface.
- Có thể chọn cả METHOD và TYPE để hỗ trợ cả hai.
- `@Retention(RUNTIME)` cần thiết để hạ tầng runtime tìm được annotation.
- Meta-annotation cần giá trị `@PreAuthorize` có tính xác thực/ủy quyền rõ; không mặc định tin input.
- Khi đổi expression của meta-annotation, **tất cả nơi sử dụng** có thể thay đổi quyền, cần chạy test regression.

### 10.2. Meta-annotation nhiều lớp vẫn cần xem xung đột

Giả sử class có:

~~~java
@CanReadDocument
public class DocumentService { }

~~~

và một method có `@PreAuthorize("hasRole('ADMIN')")`. Cùng loại underlying `@PreAuthorize`, hãy kiểm tra precedence và policy thật với integration test; không suy rằng annotation đặt trên type luôn bổ sung thành một yêu cầu nữa. Dùng một mô hình nhất quán: class-level baseline + explicit method exceptions, hoặc policy bean.

### 10.3. Meta-annotation có tham số

Spring Security cũng hỗ trợ cách biểu diễn parameter trong composed annotation theo phiên bản (ví dụ `@HasRole("ADMIN")`). Khi tạo annotation tham số, cần chú ý quotation trong SpEL, Java annotation value và khả năng injection/escaping. Nếu expression động phức tạp hoặc liên quan tài nguyên, dùng policy bean dễ test hơn.

## 11. Proxy, self-invocation và vì sao annotation “có nhưng không chạy”

Một ví dụ hay gây lỗ hổng:

~~~java
@Service
public class ExportService {

    public void exportFromController() {
        exportSensitiveData();
    }

    @PreAuthorize("hasAuthority('pii:export')")
    public void exportSensitiveData() {
        // Xuất dữ liệu nhạy cảm.
    }
}
~~~

Controller gọi `exportFromController()` qua Spring proxy. Nếu method này không có rule, nó được cho vào. Bên trong, `this.exportSensitiveData()` là **self-invocation** và thường không đi qua proxy, nên `@PreAuthorize` trên `exportSensitiveData()` có thể **không được thực thi**.

Đây không phải lỗi annotation inheritance mà là giới hạn cơ chế interception.

### 11.1. Cách sửa có chủ đích

Tách thao tác cần bảo vệ thành **một Spring-managed bean khác**:

~~~java
@Service
public class ProtectedExportService {

    @PreAuthorize("hasAuthority('pii:export')")
    public void exportSensitiveData() {
        // Thực hiện xuất PII.
    }
}

@Service
public class ExportOrchestrator {
    private final ProtectedExportService protectedService;

    public ExportOrchestrator(ProtectedExportService protectedService) {
        this.protectedService = protectedService;
    }

    public void export() {
        protectedService.exportSensitiveData();
    }
}
~~~

Caller đi qua proxy của `ProtectedExportService` nên interceptor có cơ hội chạy. Vẫn cần test thực tế để đảm bảo bean đúng, method interceptable và không có đường vòng gọi trực tiếp implementation.

### 11.2. Những bẫy proxy liên quan

| Tình huống | Điều cần nhớ |
|---|---|
| Caller dùng object được tạo bằng `new` | Không có Spring proxy; method security mặc định không tự chạy |
| `this.securedMethod()` | Bypass proxy trong mô hình AOP proxy thông thường |
| JDK dynamic proxy | Thường proxy interface methods; kiểm tra interface và injection type |
| Class-based/CGLIB proxy | Phụ thuộc method có thể được override; final/private methods không được proxy như public overridable methods |
| Method private | Không thể bảo vệ chỉ bằng proxy-based advice thông thường |
| Method final / class final | Có giới hạn với subclass-based proxy; kiểm tra proxy strategy |
| Kotlin class/method mặc định final | Cần cấu hình mở class/method hoặc strategy thích hợp |
| Interface default method | Không dựa vào giả định; test proxy mode/version và đường gọi |
| Overloaded / generic / bridge methods | Kiểm tra metadata resolution và signature thực |
| Interface annotation trong AspectJ mode | Có khác biệt với proxy mode, cần xem quy tắc kế thừa Java/AspectJ |

**Cảnh báo AspectJ:** tài liệu Spring Security nhấn mạnh rằng Java annotations trên interface **không được kế thừa theo quy tắc Java**, và AspectJ weaving tuân theo quy tắc đó. Nếu dùng `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)`, không suy ra interface annotation có tác dụng giống Spring proxy mode. Hãy đặt annotation phù hợp trên class/concrete method và test theo mô hình weaving thật.

### 11.3. AOP proxy không phải object-level authorization

Dù interceptor chạy và `hasAuthority('document:read')` pass, người gọi vẫn có thể yêu cầu tài liệu thuộc tenant khác. Dùng policy tài nguyên:

~~~java
@PreAuthorize(
    "hasAuthority('document:read') " +
    "and @documentPolicy.canRead(authentication, #documentId)"
)
public DocumentDto read(long documentId) {
    return repository.findVisible(documentId);
}
~~~

Đây là snippet phụ thuộc ứng dụng. `documentPolicy` phải kiểm tra quyền trên bản ghi tin cậy, không dựa vào ID hoặc tenantId do client tự khai.

## 12. Parameter names trong SpEL khi annotation nằm ở interface

Một interface có:

~~~java
public interface DocumentApi {
    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    DocumentDto read(long documentId);
}
~~~

`#documentId` chỉ hoạt động nếu hạ tầng expression có thể **khám phá đúng tên tham số**. Với interface, bytecode không chứa local-variable debug information giống concrete method theo cách Spring có thể luôn dựa vào.

Tài liệu Spring Security mô tả một số cơ chế:

1. `@P("documentId")` của Spring Security để khai báo tên theo annotation.
2. `@Param` trong một số trường hợp phù hợp.
3. Compile Java với `-parameters` để có metadata tên tham số.
4. Debug symbols của concrete classes (không đủ cho interface method trong trường hợp chỉ phụ thuộc debug metadata).

Ví dụ tường minh trên interface:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

public interface DocumentApi {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    DocumentDto read(@P("documentId") long documentId);
}
~~~

Snippet phụ thuộc bean `documentPolicy` và kiểu `DocumentDto` thực tế. Trong build Maven/Gradle, nên bật compiler parameter metadata khi dự án dùng SpEL theo tên. Test với **chính bean interface** và parameter data thật, đừng chỉ test một biểu thức không có tham số.

## 13. @Secured, @RolesAllowed, @PermitAll và @DenyAll có “kế thừa” tương tự không?

Khi được bật, Spring Security cũng cho phép `@Secured` và JSR-250 annotations ở class/interface/method. Nhưng mỗi nhóm có interceptor/semantics riêng:

~~~java
// Chỉ có tác dụng khi @EnableMethodSecurity(securedEnabled = true).
@Secured("ROLE_ADMIN")
public void manageUsers() { }
~~~

~~~java
// Chỉ có tác dụng khi @EnableMethodSecurity(jsr250Enabled = true).
@RolesAllowed("ADMIN")
public void manageUsers() { }
~~~

Ví dụ trên là hai **phương án khác nhau**, không phải hướng dẫn đặt cả hai lên cùng method. Với `@RolesAllowed`, cách diễn giải role prefix và hỗ trợ theo phiên bản/config cần được kiểm thử. `@PermitAll` và `@DenyAll` trong JSR-250 **không phải** `requestMatchers(...).permitAll()/denyAll()` của HTTP layer.

### 13.1. Không trộn annotation type để tạo “ngoại lệ” không rõ ràng

Ví dụ class có `@PreAuthorize("hasRole('ADMIN')")`, method đặt `@PermitAll`:

~~~java
@PreAuthorize("hasRole('ADMIN')")
class AdministrativeService {

    @PermitAll
    public String status() { return "ok"; }
}
~~~

Nếu các interceptor liên quan đều được bật, không được chắc chắn `@PermitAll` có thể hủy kiểm tra `@PreAuthorize`: đó là **hai annotation families khác nhau**, không có luật class-vs-method override cho cùng `@PreAuthorize`.

Nếu thực sự muốn ngoại lệ, nên dùng một `@PreAuthorize` rõ ràng trên method cùng loại với baseline:

~~~java
@PreAuthorize("permitAll()")
public String status() { return "ok"; }
~~~

và kiểm tra những policy khác vẫn chạy theo thiết kế. Tránh annotation conflict hoặc ý nghĩa quyền bị phân tán giữa ba cơ chế.

## 14. Test dựa trên hành vi: cách duy nhất xác minh kế thừa hiệu lực

Nếu code chỉ đọc Java reflection:

~~~java
assertNull(
    Implementation.class.getMethod("read")
        .getDeclaredAnnotation(PreAuthorize.class)
);
~~~

thì chưa biết Spring AOP có nhận annotation từ interface hay không. Ngược lại, kiểm tra rằng annotation tồn tại cũng chưa đủ vì bean có thể không được proxy.

Một bộ test đúng cần:

- Có `@EnableMethodSecurity` trong Spring context.
- Lấy bean qua `@Autowired`, không tự khởi tạo bằng `new`.
- Gọi method từ test qua bean/proxy.
- Đặt `SecurityContext` bằng `@WithMockUser` hoặc authentication strategy phù hợp.
- Test **được phép** và **bị từ chối**, đặc biệt role thường và role admin.
- Test behavior khi class-level bị method-level override.
- Test interface-level contract.
- Test xung đột hai interface bằng startup/context test.
- Test self-invocation được chặn bằng tái cấu trúc nếu có.
- Test object-level tenant/owner.

### 14.1. Mẫu JUnit 5 + Spring Security Test

Giả sử đã có bean `CatalogService`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CatalogMethodSecurityTest {

    @Autowired
    CatalogService catalogService;

    @Test
    @WithMockUser(roles = "USER")
    void userMayList() {
        assertEquals("list", catalogService.list());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userMayNotDelete() {
        assertThrows(AccessDeniedException.class,
                () -> catalogService.delete(7));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminMayDeleteUsingMethodRule() {
        assertEquals("delete-7", catalogService.delete(7));
    }
}
~~~

**Điều kiện để test thực sự hợp lệ:** `CatalogService` phải là bean Spring thực, với hai method trả về như ví dụ và `@EnableMethodSecurity` đã bật. `@WithMockUser` cần module `spring-security-test`. Trong cấu hình mặc định **không có role hierarchy** buộc ADMIN bao hàm USER, role ADMIN vẫn được phép xóa vì method-level `@PreAuthorize` ghi đè class-level, không cần giả định ADMIN cũng mang `ROLE_USER`.

Test này minh họa một **kết quả có thể phản trực giác**: thay đổi annotation trên method có thể làm mất baseline role USER ở class.

### 14.2. Test interface method

Với `DocumentReader` có `@PreAuthorize("hasAuthority('document:read')")` và Spring-managed `DefaultDocumentReader`:

~~~java
@SpringBootTest
class DocumentInterfaceSecurityTest {

    @Autowired
    DocumentReader reader;

    @Test
    @WithMockUser(authorities = "document:read")
    void readerMayRead() {
        assertEquals("document-9", reader.read(9));
    }

    @Test
    @WithMockUser(authorities = "document:write")
    void writerWithoutReadIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> reader.read(9));
    }
}
~~~

Snippet giả định các imports test giống ví dụ trước và bean implementation thực, không phải một file Java độc lập. **Không cấp sẵn authority `document:read` cho test deny**; test cần chứng minh annotation interface được Spring thực thi.

### 14.3. Test xung đột interface

Trường hợp `OperationsService implements SupportApi, AuditApi` nhưng không annotate concrete method cần được kiểm tra trong **Spring ApplicationContext test**. Theo tài liệu Spring Security, việc resolve kế thừa hai annotation cùng loại từ hai interfaces gây ambiguity và có thể làm startup fail. Một test context hợp lý sẽ assert startup failure liên quan method-security metadata. Sau khi thêm annotation cụ thể lên `OperationsService.operate()`, context phải khởi động được và test allow/deny theo policy mới.

Đừng đưa lớp **cố ý gây startup failure** vào main component scan của ứng dụng chỉ để minh họa: nó có thể khiến cả app không boot được. Tách test fixture/context riêng.

### 14.4. Test interface annotation dưới proxy mode thực tế

Nếu chuyển `proxyTargetClass`, đổi JDK proxy sang class proxy, dùng AspectJ weaving hoặc nâng Spring version, phải chạy lại test. Một test chạy qua implementation class được tạo bằng `new` không thể thay thế test trên Spring-managed proxy.

## 15. Java 17 độc lập: mô phỏng lookup, override và xung đột

Chương trình sau **không dùng Spring Security**. Nó mô phỏng quy tắc có ích cho học tập: method annotation ưu tiên class annotation, interface method annotation được tìm riêng, và hai interface cùng có annotation gây ambiguity. Java reflection ở đây cố ý cho thấy annotation trên interface **không tự xuất hiện như declared annotation của implementation method**.

**Cảnh báo:** Đây chỉ là một thuật toán demo đơn giản, không phải resolver/pointcut thật của Spring Security. Nó không mô phỏng superclass đa tầng, composed annotations, bridge methods, proxy, AspectJ hay authentication. Test Spring thật ở phần trên là bước cần thiết để xác nhận behavior.

Tạo file `MethodAnnotationDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

public class MethodAnnotationDemo {

    @Target({ElementType.TYPE, ElementType.METHOD})
    @Retention(RetentionPolicy.RUNTIME)
    @interface Gate { String value(); }

    @Gate("ROLE_USER")
    static class CatalogService {
        public String list() { return "list"; }
        @Gate("ROLE_ADMIN")
        public String delete() { return "delete"; }
    }

    interface ReaderApi {
        @Gate("document:read")
        String read();
    }

    static class ReaderService implements ReaderApi {
        public String read() { return "read"; }
    }

    interface SupportApi {
        @Gate("support:manage")
        String operate();
    }

    interface AuditApi {
        @Gate("audit:manage")
        String operate();
    }

    static class AmbiguousService implements SupportApi, AuditApi {
        public String operate() { return "operate"; }
    }

    static class ResolvedService implements SupportApi, AuditApi {
        @Gate("ops:approved")
        public String operate() { return "operate"; }
    }

    static String decide(Class<?> impl, String methodName) throws Exception {
        Method method = impl.getMethod(methodName);
        Gate methodRule = method.getDeclaredAnnotation(Gate.class);
        if (methodRule != null) return methodRule.value();

        Gate classRule = impl.getDeclaredAnnotation(Gate.class);
        if (classRule != null) return classRule.value();

        List<String> found = new ArrayList<>();
        for (Class<?> iface : impl.getInterfaces()) {
            try {
                Method interfaceMethod = iface.getMethod(methodName);
                Gate interfaceRule = interfaceMethod.getAnnotation(Gate.class);
                if (interfaceRule != null) found.add(interfaceRule.value());
                else {
                    Gate interfaceTypeRule = iface.getAnnotation(Gate.class);
                    if (interfaceTypeRule != null) found.add(interfaceTypeRule.value());
                }
            } catch (NoSuchMethodException ignored) {
                // This interface does not declare the requested method.
            }
        }
        if (found.size() > 1) {
            return "AMBIGUOUS(" + String.join(",", found) + ")";
        }
        return found.isEmpty() ? "NO_RULE" : found.get(0);
    }

    public static void main(String[] args) throws Exception {
        System.out.println("catalog list: " +
                decide(CatalogService.class, "list"));
        System.out.println("catalog delete: " +
                decide(CatalogService.class, "delete"));
        System.out.println("reader read: " +
                decide(ReaderService.class, "read"));
        System.out.println("ambiguous operate: " +
                decide(AmbiguousService.class, "operate"));
        System.out.println("resolved operate: " +
                decide(ResolvedService.class, "operate"));
        System.out.println("interface reflected on implementation: " +
                (ReaderService.class.getMethod("read")
                    .getDeclaredAnnotation(Gate.class) != null));
    }
}
~~~

Chạy bằng **Java 17 trở lên**:

~~~bash
javac --release 17 MethodAnnotationDemo.java
java MethodAnnotationDemo
~~~

Output chính xác:

~~~text
catalog list: ROLE_USER
catalog delete: ROLE_ADMIN
reader read: document:read
ambiguous operate: AMBIGUOUS(support:manage,audit:manage)
resolved operate: ops:approved
interface reflected on implementation: false
~~~

Phân tích từng dòng:

- `catalog list`: method không có `@Gate` nên demo tìm annotation ở class.
- `catalog delete`: method có `@Gate("ROLE_ADMIN")`, ghi đè giá trị class `ROLE_USER`.
- `reader read`: implementation method không annotate; demo tự dò interface declaration.
- `ambiguous operate`: hai interface cấp hai giá trị khác nhau; demo không tự chọn.
- `resolved operate`: concrete method annotate chính sách tường minh.
- `interface reflected on implementation: false`: Java reflection `getDeclaredAnnotation` trên implementation method không tự thấy annotation của interface.

**Không suy luận từ demo rằng Spring sẽ in cùng chuỗi “AMBIGUOUS”**: Spring Security có thể làm **ApplicationContext startup thất bại** khi phát hiện xung đột metadata. Demo chỉ trả nhãn để có thể chạy và học logic.

### 15.1. Bài tập mở rộng

1. Thêm method `@Gate("PUBLIC")` vào một class có annotation cấp class `ROLE_ADMIN`. Quan sát method “ghi đè” baseline.
2. Thêm interface thứ ba không có `@Gate` rồi kiểm tra demo vẫn chọn một interface được annotate.
3. Bổ sung hàm traverse superclass với danh sách `visited` để tránh duyệt lặp.
4. Thay giả định “method > class > interface” bằng một cấu hình kiểm thử Spring thật; so sánh những nơi tương đồng và khác biệt.
5. Đưa chính sách `@PreAuthorize("hasAuthority('document:read')")` lên interface trong một Spring Boot test, rồi gọi qua `@Autowired DocumentReader` với hai users.

## 16. Thứ tự advisor, transaction và cách áp dụng nhiều annotation

Method security dùng các AOP interceptors trước/sau method, không phải “quét annotation rồi chạy một lần ở startup”:

~~~text
proxy invocation
    |
    +--> @PreFilter (nếu có)
    +--> @PreAuthorize: yêu cầu trước khi gọi method
    +--> @Secured / JSR-250 (nếu đã bật và có)
    |
    v
    method body
    |
    +--> @PostAuthorize: yêu cầu sau khi method trả về
    +--> @PostFilter (nếu có)
    |
    v
result / AccessDeniedException
~~~

**Sơ đồ là đơn giản hóa logic**, không cam kết thứ tự chính xác cho mọi advisor. Các interceptor có order constants và có thể tương tác với transaction, caching, metrics và custom AOP advices. Spring Security cho phép cấu hình thứ tự qua `@EnableMethodSecurity` và các advisor registrations trong trường hợp phù hợp.

Điểm cốt lõi cho chủ đề này:

- Những annotation **khác loại** có interceptor riêng và được đánh giá theo giai đoạn.
- Những annotation **cùng loại ở nhiều cấp hierarchy** cần được resolve nhất quán, không phải tự động chạy tất cả.
- `@PostAuthorize` chạy sau method và không bảo đảm undo mọi side effects.
- Cơ chế interception có thể không chạy nếu caller bypass proxy, dù annotation ở method, class và interface đều có.
- Chuyển sang AspectJ mode làm thay đổi cách weaving và inheritance hoạt động; cần test.

## 17. Lỗi thường gặp và cách xử lý

| Lỗi | Rủi ro | Cách khắc phục |
|---|---|---|
| Quên `@EnableMethodSecurity` | Annotation không được dùng | Bật cấu hình, test denial |
| Class có `@PreAuthorize("hasRole('USER')")`, method ghi `@PreAuthorize("hasRole('ADMIN')")` rồi nghĩ cả hai được AND | Hiểu sai override | Ghi rõ điều kiện cần có trong method |
| Method cấp class vô tình được annotate `permitAll()` | Nới permission rộng ngoài dự kiến | Security review ở từng method exception |
| Annotation chỉ có trên interface nhưng gọi object bằng `new` | Không có AOP proxy | Lấy bean Spring qua DI |
| Hai interface cùng annotate method | Ambiguous metadata/startup failure | Đặt một annotation tường minh trên concrete method |
| Dựa vào thứ tự `implements` để chọn interface | Rule không xác định theo ý định | Resolve explicit, test |
| Dùng Java `@Inherited` để suy ra interface method authorization | Reflection không tương đương Spring resolver | Spring integration test |
| Tự gọi `this.securedMethod()` | Bypass proxy-based interception | Tách service hoặc thay architecture |
| Dùng final/private method với class-based proxy | Advice không intercept được | Public overridable method qua proxy, test |
| Chuyển sang AspectJ nhưng giữ interface-only annotation | Java/AspectJ inheritance khác | Annotation ở concrete method/class và test weaving |
| Lặp hai `@PreAuthorize` trên method | Không được hỗ trợ | Gộp SpEL bằng AND/OR |
| Kết hợp `@PermitAll` và `@PreAuthorize` để “override” | Các interceptor khác loại có thể xung đột | Dùng policy nhất quán và test |
| `@PostAuthorize` bảo vệ thao tác ghi | Side effect xảy ra trước kiểm tra | `@PreAuthorize` cho writes |
| Interface SpEL dùng `#id` nhưng thiếu parameter metadata | Sai hoặc không evaluate được expression | `@P` hoặc `-parameters`, test |
| Có meta-annotation nhưng `@Retention` không phù hợp | Hạ tầng runtime không thấy metadata | `RUNTIME` và `@Target` đúng |
| Chỉ kiểm tra `getDeclaredAnnotation` | Bỏ sót class/interface/meta annotation | Test qua Spring proxy |
| Chỉ kiểm tra HTTP authorization | Scheduler/other entrypoint bỏ lọt | Policy service + method security |
| Chỉ có role, không có quyền trên resource | IDOR/BOLA | Owner/tenant/object policy |
| Chỉ test admin thành công | Không phát hiện rule bị nới | Negative tests với user thường, anonymous |

## 18. Checklist khi thiết kế annotation ở nhiều cấp

- [ ] Method security đã được bật trong đúng Spring context?
- [ ] Chọn **một nơi authoritative** cho policy; class/interface mặc định hay concrete method?
- [ ] Annotation method-level cùng loại có làm giảm baseline cấp class/interface không?
- [ ] Đã đọc các contract interface mà service implement, kể cả những interface do thư viện cung cấp?
- [ ] Có hai interface cùng khai báo `@PreAuthorize` cho một signature? Đã resolve tường minh?
- [ ] Các composed annotations có `@Retention(RUNTIME)`, `@Target` đúng và không xung đột?
- [ ] Nhiều annotation khác loại có cần chạy đồng thời không? Đã test AND/denial semantics?
- [ ] Không lặp `@PreAuthorize` hai lần trên cùng method?
- [ ] Method được gọi qua bean proxy? Không bị self-invocation, new, private/final bypass?
- [ ] Proxy strategy (JDK/CGLIB/AspectJ) có khớp với vị trí annotation?
- [ ] Interface SpEL parameter names có sẵn qua `@P`/`-parameters`?
- [ ] Với `@PostAuthorize`, method có side effects trước khi được phép không?
- [ ] Có test allow + deny khi user có quyền trên class nhưng không có quyền method?
- [ ] Có test interface contract khi implementation không annotate lại?
- [ ] Có test startup failure khi nhiều interface conflict?
- [ ] Có test HTTP, scheduler hoặc các entrypoints khác cùng gọi use case quan trọng?
- [ ] Có policy owner/tenant/resource và audit, không chỉ role string?
- [ ] Có regression tests khi refactor interface, superclass, override hoặc đổi proxy mode?

**Quy tắc thực hành:** *Quy định rõ chính sách ở cấp nào, dùng concrete method để giải quyết ngoại lệ và mơ hồ, đồng thời chứng minh bằng lời gọi qua Spring proxy.*

## 19. Câu hỏi tự kiểm tra

**1. Class có `@PreAuthorize("hasRole('USER')")`, method có `@PreAuthorize("hasRole('ADMIN')")`. Method đòi cả hai role?**  
Không mặc định. Với annotation cùng loại, method-level override class-level; muốn cả hai phải viết expression kết hợp.

**2. Một implementation không annotate nhưng interface method có `@PreAuthorize`. Nó có thể được bảo vệ không?**  
Có trong Spring proxy-based method security phù hợp, vì resolver tìm annotation qua hierarchy. Phải bật method security, dùng bean/proxy và test.

**3. `@Inherited` của Java có tự copy annotation từ interface method sang implementation không?**  
Không. Java reflection inheritance và Spring method-security hierarchy resolution khác nhau.

**4. Hai interface đều annotate một method bằng `@PreAuthorize` khác nhau, Spring chọn interface khai báo trước?**  
Không. Đây là metadata mơ hồ có thể gây startup failure; annotate concrete method tường minh để giải quyết.

**5. `@PreAuthorize` và `@PostAuthorize` trên cùng một method có phải cùng loại lặp không?**  
Không, chúng là hai loại annotation với interceptor trước và sau khác nhau; cả hai điều kiện phải được xem xét.

**6. Có thể đặt hai `@PreAuthorize` trên một method và hy vọng AND không?**  
Không được hỗ trợ; hãy ghép điều kiện trong một annotation hoặc bean policy.

**7. Vì sao `@PostAuthorize` không phải lựa chọn mặc định để bảo vệ xóa/sửa dữ liệu?**  
Vì method body có thể đã gây side effect trước khi post-authorization kiểm tra.

**8. Vì sao method `@PreAuthorize` vẫn bị gọi trái phép khi được gọi bằng `this.method()`?**  
Trong proxy mode, self-invocation không đi qua proxy nên interceptor có thể bị bỏ qua.

**9. Interface annotation trong AspectJ mode có được kế thừa giống proxy mode không?**  
Không nên giả định; AspectJ tuân theo quy tắc Java về annotation trên interfaces. Cần đặt annotation thích hợp và test weaving.

**10. Reflection trên implementation method trả null có chứng minh Spring không bảo vệ method không?**  
Không. Annotation có thể được Spring tìm ở class/interface/superclass/meta annotation. Test qua Spring proxy.

**11. Nếu `@PreAuthorize` ở class và `@PermitAll` ở method, `@PermitAll` có tự hủy class-level check không?**  
Không được mặc định suy ra. Chúng thuộc hai annotation families/interceptors riêng, còn phải xét những loại được bật và policy hiện hành.

**12. Người có `document:read` có được đọc tất cả tài liệu của mọi tenant không?**  
Không. Annotation function-level phải kết hợp với object-level authorization trên tài nguyên thực tế.

## 20. Tài liệu chính thức

- Spring Security – **Method Security** (annotation ở class/interface; method-level override; multiple interface conflict; meta annotations; nhiều annotations và repeat): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Method Security** phiên bản 7.0 (kiểm tra khi nâng version): https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security – **Authorization Architecture** (AuthorizationManager và GrantedAuthority): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Framework – **Proxying Mechanisms** (self-invocation, JDK proxy và CGLIB): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security – **Testing Method Security**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Java SE 17 – **@Inherited JavaDoc**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html
