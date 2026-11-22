# Phương thức không có annotation và chính sách bao phủ mặc định

> **Module:** Spring Security - authorization  
> **Nhóm kiến thức:** Method security  
> **Mục tiêu:** Hiểu chính xác điều gì xảy ra với method không mang annotation bảo mật trong Spring Security; nhận biết khi nào method **đã được bảo vệ thông qua class/interface/pointcut** dù bản thân không có annotation; thiết kế chính sách bao phủ mặc định theo hướng deny-by-default mà không phá luồng gọi hợp lệ; và viết test chứng minh mọi đường thực thi quan trọng đều có authorization phù hợp.

## 1. Câu hỏi cần trả lời trước khi viết code

Một project đã thêm:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

Sau đó có service:

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public ReportView readReport(long reportId) {
        return repository.readReport(reportId);
    }

    public void deleteReport(long reportId) {
        repository.deleteById(reportId);
    }
}
```

Liệu Spring Security tự động chặn `deleteReport` vì method này **không có annotation**?

**Không.** `@EnableMethodSecurity` kích hoạt cơ chế bảo vệ method bằng các interceptor, nhưng các interceptor annotation mặc định chỉ áp dụng khi tìm thấy annotation bảo mật phù hợp trên method, class, interface hoặc meta-annotation. Nếu một lời gọi không có rule bảo mật hiệu lực và không bị một custom pointcut/advisor khác bao phủ, **không có quyết định DENY mặc định chỉ vì method thiếu annotation**.

Điều này không có nghĩa method được mọi người trên internet gọi trực tiếp; HTTP, controller, authentication, business policy, Java visibility và đường gọi thực tế có thể giới hạn nó. Nhưng cũng **không được suy ra rằng một method không được gọi qua HTTP thì an toàn**: nó có thể được một controller mới, GraphQL resolver, job, message listener hoặc Spring bean khác gọi.

Nguyên tắc của bài:

> **Sự vắng mặt của annotation trên dòng method không tương đương với sự hiện diện của một policy DENY. Muốn “mặc định từ chối”, hãy thiết kế và kiểm chứng một rule thực sự bao phủ các lời gọi cần bảo vệ.**

## 2. Bốn tình huống nhìn giống nhau nhưng kết quả khác nhau

| Trường hợp | Có annotation trực tiếp ở method? | Có rule method-security hiệu lực? | Nhận định |
| --- | --- | --- | --- |
| Method không annotation, class/interface cũng không, không custom advisor | Không | Thường không | Không được annotation-based method security chặn |
| Method không annotation, class có `@PreAuthorize("hasRole('USER')")` | Không | Có | Method **kế thừa rule ở class** |
| Method không annotation, interface cha có rule hợp lệ | Không | Có thể có | Cần xác minh annotation inheritance và proxy/interface resolution |
| Method không annotation, một custom `Advisor` có pointcut khớp | Không | Có | Được bảo vệ qua **pointcut**, không cần annotation trên method |
| Method có `@PreAuthorize("denyAll()")` | Có | Có | Bị từ chối khi interceptor thực sự chạy |
| Method có `@PreAuthorize("permitAll()")` | Có | Có | Có rule cho phép tại checkpoint này, nhưng các checkpoint khác vẫn có thể DENY |
| Method có `@Secured` nhưng `securedEnabled=false` | Có | Chưa chắc | Annotation tồn tại nhưng loại interceptor đó có thể chưa bật |
| Method mang annotation nhưng bị gọi trực tiếp bằng `this.method()` | Có | Có thể **không chạy advice** | Self-invocation qua proxy thông thường không được chặn |
| Method ở object tạo bằng `new` ngoài Spring | Có hoặc không | Không bảo đảm | Không có Spring proxy để áp method security |
| Method có annotation nhưng app chưa bật `@EnableMethodSecurity` | Có | Không chắc có interceptor | Không được xem là đã được bảo vệ chỉ vì annotation trong source |

**Bảo vệ hiệu lực phải được kiểm tra ở runtime**, không đơn giản đếm số annotation.

## 3. @EnableMethodSecurity thực sự kích hoạt điều gì?

Spring Security Servlet 6.5 dùng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

Điều này kích hoạt các phương thức bảo vệ bằng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` theo cấu hình mặc định. `Spring Boot Starter Security` **không tự bật method-level authorization**; hãy xác minh bean/config của chính dự án.

Dòng xử lý khi có `@PreAuthorize`:

```text
Spring bean qua proxy
       |
       v
Method invocation
       |
       v
Annotation-aware pointcut có thấy @PreAuthorize
trên method/class/interface/meta-annotation?
       | NO
       |   -> @PreAuthorize interceptor không có reason để chặn
       | YES
       v
AuthorizationManagerBeforeMethodInterceptor
       |
       v
PreAuthorizeAuthorizationManager
       |
       +--- DENY -> exception / denied handler
       |
       +--- ALLOW -> method body được chạy
```

Cần phân biệt:
- `@PreAuthorize` quyết định **trước** khi chạy method body.
- `@PostAuthorize` xét kết quả **sau** khi body đã thực thi.
- `@PreFilter`/`@PostFilter` lọc input/output phù hợp; không thay thế mọi chính sách cấp quyền command.
- `@Secured` và `@RolesAllowed` (JSR-250) yêu cầu bật tùy chọn tương ứng.

Không có một interceptor mặc định “vét tất cả method rồi DENY nếu không thấy annotation” sau khi bật `@EnableMethodSecurity`.

Nguồn: tài liệu chính thức Spring Security 6.5 nói rõ *unannotated methods are not secured* trong mô hình annotation-based; đồng thời khuyên có catch-all HTTP authorization rule để bảo vệ đường vào request.

## 4. “Không có annotation” cần xét toàn bộ hierarchy

Một method không thấy annotation bên trên nó vẫn có thể được bảo vệ bởi annotation ở class:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("hasAuthority('finance:read')")
public class FinanceService {

    public String summary() {
        return "financial summary";
    }

    public String details() {
        return "financial details";
    }
}
```

Trong cấu hình method security phù hợp, cả `summary` và `details` chịu rule `hasAuthority('finance:read')` từ class; chúng không phải “unsecured” chỉ vì thiếu annotation tại từng method.

Nếu class-level và method-level cùng có **loại annotation `@PreAuthorize`**, method-level **ghi đè/ưu tiên** class-level:

```java
@Service
@PreAuthorize("hasRole('USER')")
public class CatalogService {

    public String list() {
        return "normal catalog";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String deleteCatalog() {
        return "admin operation";
    }
}
```

Với `deleteCatalog`, rule `hasRole('ADMIN')` ở method thay rule class-level thuộc cùng loại annotation. Không diễn giải nó là “USER AND ADMIN” chỉ vì cả class và method cùng dùng `@PreAuthorize`.

Tuy nhiên **những loại annotation khác nhau có interceptor khác nhau**. Ví dụ `@PreAuthorize` kết hợp `@PostAuthorize` trên cùng invocation thường áp tuần tự, về hiệu quả phải vượt qua cả hai rule. Đừng nhầm sự ghi đè **cùng loại** với việc mọi annotation tại method thay thế tất cả chính sách khác.

### Interface và đa kế thừa

Spring Security hỗ trợ annotation ở interface. Một implementation không ghi annotation lên method cụ thể vẫn có thể chịu policy kế thừa từ interface. Nếu một class thực thi nhiều interface có các annotation mâu thuẫn và Spring không thể chọn rule rõ ràng, quá trình khởi tạo có thể báo lỗi; phải giải quyết bằng annotation tường minh trên method cụ thể.

Khi audit coverage, phải kiểm tra **method + class + interface + meta annotations + advisors**, không chỉ `method.isAnnotationPresent(PreAuthorize.class)`.

## 5. Một HTTP rule mặc định bảo vệ điều gì?

Ví dụ một `SecurityFilterChain` dùng fallback deny:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain app(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/healthz")
                .permitAll()
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .requestMatchers("/api/**")
                .authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Ở đây:
- `GET /healthz` public tại checkpoint HTTP.
- `/api/admin/**` yêu cầu role ADMIN trước rule API chung.
- Các request `/api/**` khác cần authentication.
- Các đường dẫn còn lại trong chain nhận `denyAll`.

Điều này giúp tránh lộ một HTTP endpoint mới bên ngoài `/api/**`, **nếu request thực sự thuộc SecurityFilterChain đó**. Nhưng `/api/**.authenticated()` vẫn chỉ kiểm tra người gọi đã đăng nhập; nếu một controller gọi method nguy hiểm không có method guard/domain policy, user đăng nhập thường có thể tới chức năng đáng ra dành cho ADMIN.

**Quan trọng hơn:** `anyRequest().denyAll()` chỉ là fallback **HTTP authorization**. Nó **không** tự chặn một `@Scheduled` job, message consumer hoặc bean gọi `deleteReport` từ nội bộ. Chính sách method/service là lớp riêng.

Nếu ứng dụng có nhiều `SecurityFilterChain` dùng `securityMatcher` hẹp, cần có fallback chain phù hợp để route không rơi khỏi filter chain. `anyRequest` trong một chain không bảo vệ URL ở ngoài chain.

## 6. Hai hướng “bao phủ mặc định” thường được dùng

### Hướng A — Đảm bảo tất cả HTTP entry point đã được phân quyền

Thích hợp khi chính sách request-level là lớp bao phủ chính:

- Liệt kê mọi route và HTTP method.
- Đặt rule hẹp trước matcher rộng.
- Có `anyRequest().denyAll()` hoặc fallback `authenticated()` được duyệt theo thiết kế.
- Test anonymous, user thường, role cao và resource khác tenant.
- Với nhiều chain, đảm bảo route được chọn bởi một chain thực tế.
- Tất cả service nhạy cảm còn có domain policy nếu có thể được gọi từ nơi khác.

Ưu điểm: giảm nguy cơ vô tình public route mới. Giới hạn: **không bao phủ lời gọi service không đi qua HTTP**.

### Hướng B — Bảo vệ cả service layer bằng chính sách mặc định

Thích hợp khi service có nhiều entry point hoặc tổ chức muốn một chính sách service-level rõ ràng:

- Đặt annotation ở **class/interface** để bao phủ các method thường.
- Hoặc đăng ký **custom pointcut + AuthorizationManagerBeforeMethodInterceptor** cho một nhóm service.
- Có phương thức cho phép cụ thể bằng annotation/policy có review.
- Chặn object-level action tại use case, không chỉ quyền role.
- Test gọi bean trực tiếp qua Spring proxy, kể cả method không có annotation tại dòng method.

Ưu điểm: một controller/job mới gọi service cũ vẫn đi qua guard trên service khi invocation đi qua proxy/pointcut. Giới hạn: **proxy boundaries, self-invocation, nơi tạo object và các thư viện gọi ngoài Spring** vẫn cần được quản lý.

Hai hướng **bổ sung** nhau chứ không loại trừ nhau.

## 7. Mẫu class-level default deny: @PreAuthorize("denyAll()")

Nếu một service muốn **không cho phép method mới bị mở ngoài ý định**, có thể khai báo class-level:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("denyAll()")
public class DocumentCommandService {

    @PreAuthorize("hasAuthority('document:read')")
    public String readDocument(long id) {
        return "document:" + id;
    }

    @PreAuthorize("hasAuthority('document:delete')")
    public void deleteDocument(long id) {
        // Load resource in allowed tenant,
        // check ownership/ACL/state, then delete.
    }

    public void exportAllDocuments() {
        // Không có @PreAuthorize ở method:
        // class-level denyAll vẫn có hiệu lực khi advice chạy.
    }

    @PreAuthorize("permitAll()")
    public String publicMetadata() {
        return "public metadata";
    }
}
```

**Ý tưởng:**
- `@PreAuthorize("denyAll()")` ở class là một chính sách method-level hiệu lực cho các method không khai báo override.
- `readDocument` và `deleteDocument` có `@PreAuthorize` riêng nên **override** rule class-level cùng loại.
- `exportAllDocuments` không có annotation trực tiếp nên bị deny bởi class-level rule.
- `publicMetadata` được override `permitAll()` tại chốt `@PreAuthorize`; hãy chỉ làm điều này nếu thực sự public, nhớ các filter hoặc domain rule khác vẫn có thể từ chối.

Đây là **ví dụ cấu trúc**, không phải một ứng dụng hoàn chỉnh: chưa có configuration `@EnableMethodSecurity`, authentication, DB/policy thực và exception handling. Giá trị trả về được dùng để minh họa, không cho rằng một method trả text thì tự an toàn.

**Đây mới thực sự là default-deny ở class đó** — khác hẳn việc class không có annotation nhưng mong framework từ chối tất cả các method mới.

### Lưu ý quan trọng khi dùng class-level denyAll

1. Cần `@EnableMethodSecurity` và caller qua Spring proxy/appropriate advice.
2. Method-level `@PreAuthorize` **ghi đè** class-level `@PreAuthorize`, vì vậy phải ghi đủ điều kiện trong override.
3. `@PreAuthorize("permitAll()")` là ngoại lệ phải được review kỹ; HTTP hoặc auth context khác vẫn có thể yêu cầu thêm.
4. Không đổi `@PreAuthorize` class-level thành `@PostAuthorize("denyAll()")` cho command: post-check xảy ra **sau** body, có thể quá muộn cho side effect.
5. Các internal calls `this.method()` không đi qua proxy thông thường; không được dùng class-level deny làm hàng rào duy nhất cho self-invocation nguy hiểm.
6. Đừng đặt policy này lên toàn bộ class tiện ích hoặc mọi repository mà không kiểm tra luồng sử dụng; có thể chặn nhầm method nội bộ và gây regression.
7. Nếu method được gọi ngoài bean/proxy, class-level annotation không tự tạo firewall.
8. Nếu method có thêm annotation bảo mật loại khác đang bật, phải xét cả interceptor của annotation ấy.
9. Với API vừa public vừa private, nhiều khi tách bean public/private rõ ràng dễ review hơn lạm dụng `permitAll()`.

## 8. Mẫu class-level baseline authenticated

Không phải service nào cũng cần default-deny tuyệt đối. Một số nhóm service có policy “mọi method chỉ dành cho actor đã xác thực”:

```java
@Service
@PreAuthorize("isAuthenticated()")
public class CustomerService {

    public CustomerView profile() {
        return service.currentCustomer();
    }

    @PreAuthorize("hasAuthority('customer:write')")
    public void updateCustomer(String id) {
        // ...
    }
}
```

`profile()` không có annotation riêng nhưng kế thừa `isAuthenticated()` từ class. `updateCustomer` có annotation cùng loại riêng nên **không nên tưởng rằng Spring luôn thực hiện hai biểu thức với AND**; method-level rule của cùng loại override class-level.

Nếu `hasAuthority('customer:write')` thỏa điều kiện trên Authentication tin cậy, nó có thể đủ; nhưng nếu policy yêu cầu thêm MFA, tenant, ownership hoặc session assurance, hãy ghi tường minh trong method rule hoặc domain policy.

**Chọn baseline theo rủi ro:**
- `denyAll()`: thích hợp với các service có lệnh nhạy cảm và yêu cầu mỗi method public phải được review/cho phép riêng.
- `isAuthenticated()`: phù hợp với nhóm method có cùng yêu cầu authentication chung và không có lệnh nguy hiểm dễ được gọi bởi user thường.
- `hasAuthority("...")`: phù hợp khi mọi method class thực sự cần cùng một permission.
- `permitAll()`: chỉ cho các method vô hại/public có hợp đồng rõ.

Không biến `isAuthenticated()` thành chính sách mặc định cho mọi command chỉ vì nó làm integration test dễ pass.

## 9. Chú ý @PermitAll, @Secured và @RolesAllowed

Trong `@EnableMethodSecurity` mặc định:
- `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` được bật.
- `@Secured` cần `securedEnabled = true`.
- Các annotation JSR-250 `@RolesAllowed`, `@PermitAll` và `@DenyAll` cần `jsr250Enabled = true`.

Ví dụ khi dùng cả hai nhóm:

```java
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
class MethodSecurityConfiguration {}
```

Không được suy ra rằng method mang `@Secured("ROLE_ADMIN")` được bảo vệ trong một app mới chỉ vì source có annotation, nếu interceptor `securedEnabled` chưa được kích hoạt.

### Khác loại annotation không phải cùng một hệ override

Nếu class khai báo `@PreAuthorize("denyAll()")` nhưng method lại ghi `@PermitAll`, **đừng mặc định** `@PermitAll` sẽ thay thế class-level `@PreAuthorize`. Chúng thuộc **hai loại annotation/advices khác nhau**, các kiểm tra có thể cùng áp dụng. Khi muốn override class-level `@PreAuthorize`, hãy dùng **method-level `@PreAuthorize`** cùng loại, rồi test.

Tương tự, `@PostAuthorize("permitAll()")` không làm mất `@PreAuthorize("denyAll()")` trước khi chạy body. Khi có nhiều loại annotation bảo mật trên cùng invocation, các decisions thường phải cùng thỏa.

## 10. Dùng pointcut để bảo vệ method không có annotation

Spring Security xây dựng method security trên Spring AOP, vì vậy có thể bảo vệ một nhóm method thông qua **pointcut**, kể cả chúng không mang annotation trực tiếp. Tài liệu chính thức cung cấp mẫu đăng ký `Advisor` với `AuthorizationManagerBeforeMethodInterceptor`.

Ví dụ yêu cầu mọi method của các class `*Service` trong package `com.example.service` phải có `ROLE_USER`:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Role;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class ServiceLayerPolicy {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor protectServiceMethods() {
        var pointcut = new AspectJExpressionPointcut();
        pointcut.setExpression(
            "execution(* com.example.service.*Service.*(..))"
        );

        return new AuthorizationManagerBeforeMethodInterceptor(
            pointcut,
            AuthorityAuthorizationManager.hasRole("USER")
        );
    }
}
```

**Đây là snippet Spring**, yêu cầu package/service names đúng và dependencies Spring AOP/AspectJ phù hợp. Nó không phải `javac` standalone. Trong ví dụ:
- `execution(* com.example.service.*Service.*(..))` chỉ nhắm tới class `*Service` trong package đã ghi; **không tự bao phủ mọi subpackage**.
- Interceptor tùy biến yêu cầu role USER đối với những lời gọi **thực sự đi qua proxy** và khớp pointcut.
- Method không có annotation vẫn chịu rule do pointcut.
- Nếu cùng invocation còn có `@PreAuthorize`, các interceptor có thể **cùng kiểm tra**; đừng kỳ vọng annotation tự động override pointcut advisor.

**Hạn chế lớn:** Một advisor mặc định `DENY ALL` dùng pointcut quá rộng sẽ chặn cả method có annotation ALLOW, trừ khi bạn thiết kế pointcut loại trừ chúng một cách chính xác. Với yêu cầu “method mới trong class phải deny, method được review mới mở”, **class-level `@PreAuthorize("denyAll()")` + method-level override** thường minh bạch hơn một advisor deny-all toàn package.

## 11. Pointcut là tập method: cần tính đủ phạm vi

Một biểu thức AOP dạng:

```text
execution(* com.example.service.*Service.*(..))
```

có thể bỏ sót:
- Class nằm ở `com.example.service.internal` thay vì package trực tiếp.
- Class đặt tên `DocumentManager` chứ không kết thúc `Service`.
- Method không thuộc bean Spring.
- Private/final methods và những lời gọi không qua proxy.
- Một service interface/implementation nằm ngoài quy tắc đặt tên.
- Job/GraphQL gọi object hoặc repository trực tiếp.

Một custom pointcut vì vậy **không tự động là “bảo vệ mọi method”**. Hãy đối chiếu với danh sách service beans và entry points thật. Nếu chọn pattern theo naming convention, CI cần test naming/bean discovery để các class mới không vô tình nằm ngoài scope.

### Tại sao không nên “chặn theo tên get*/delete*”?

Tên method không phải chính sách bảo mật đáng tin:
- `deletePreviewCache` và `deleteCustomer` có rủi ro khác nhau.
- Một service có thể gọi `execute`, `process`, `handle` mà vẫn xóa dữ liệu.
- Một getter có thể xuất dữ liệu nhạy cảm.
- Một handler có thể tạo side effect dù tên bắt đầu bằng `get`.

Phân quyền bằng operation/capability và boundary thật, không chỉ dựa trên prefix tên.

## 12. Điểm quan trọng: một annotation không bảo vệ lời gọi không qua proxy

Với Spring AOP proxy-based method security, đường gọi điển hình:

```text
Controller / another bean
     |
     v
Spring proxy
     |
     v
Method-security advisors
     |
     v
Target service method
```

Lỗi self-invocation:

```java
@Service
public class PaymentService {

    public void process(long paymentId) {
        this.approvePayment(paymentId);
    }

    @PreAuthorize("hasAuthority('payment:approve')")
    public void approvePayment(long paymentId) {
        // Side effect...
    }
}
```

Trong cấu hình proxy-based thông thường, `this.approvePayment(...)` là lời gọi nội bộ trên target, **không đi qua proxy**, nên advice của `@PreAuthorize` có thể không chạy. Thêm annotation ở class không chữa được một đường gọi bị bypass proxy.

Để giảm rủi ro:
1. Đặt command được bảo vệ ở **bean service boundary** mà caller dùng qua Spring container.
2. Tách những operation khác nhau thành bean rõ trách nhiệm nếu cần đi qua proxy.
3. Đặt **domain authorization bắt buộc** trong application use case trước side effect nếu business yêu cầu.
4. Test cả lời gọi trực tiếp vào bean từ bên ngoài và luồng gọi lồng nhau.
5. Xem xét `AdviceMode.ASPECTJ` chỉ khi hiểu weaving/bytecode, không coi đó là mẹo tự sửa mọi lỗi.
6. Không tạo service bằng `new` rồi nghĩ annotations sẽ chạy.
7. Lưu ý method/private/final và proxy type, Kotlin final classes, object visibility; xác minh hành vi trên framework/runtime thực tế.

**Kết luận:** coverage phải tính theo **đường thực thi thật**, không đơn thuần là “annotation xuất hiện đâu đó trong source”.

## 13. HTTP fallback và method fallback có khoảng phủ khác nhau

Hai ví dụ:

```text
Case A: GET /api/reports/42
   -> HttpSecurity requestMatchers
   -> Controller
   -> ReportService.readReport()
   -> Domain policy

Case B: @Scheduled job
   -> ReportService.readReport()
   -> Domain policy

Case C: Message listener
   -> ReportService.deleteReport()
   -> Domain policy
```

Ở A, HTTP security có thể chặn trước controller. Ở B/C, HTTP filter **không tham gia**. Nếu service method không có annotation/class/pointcut và domain policy cũng không tồn tại, business operation có thể chạy mà không có authorization.

Job hoặc service actor có thể được cấp quyền riêng, nhưng đó phải là **một quyết định chính sách được thiết kế**: không có HTTP user không đồng nghĩa “system được toàn quyền”. Background process có thể có tenant, task scope và principal/service identity; audit phải ghi actor thực và context tin cậy.

### Lớp nào có trách nhiệm gì?

| Lớp | Vai trò | Không nên kỳ vọng |
| --- | --- | --- |
| HTTP `SecurityFilterChain` | Chặn request chưa xác thực/sai quyền theo route | Bảo vệ job, queue, direct bean invocation |
| Method security | Chặn lời gọi bean đi qua interception theo annotation/pointcut | Tự bảo vệ mọi method không có rule hoặc self-invocation |
| Application service policy | Actor–action–object–context, tenant/owner/ACL | Tự biết Authentication nếu entry point không truyền identity rõ |
| DB/repository scope | Chặn đọc/ghi sai tenant, version và dữ liệu | Thay thế quyết định nghiệp vụ tổng thể |
| Audit/monitoring | Theo dõi hành vi và giải thích deny | Thay thế enforcement |

Hệ thống quan trọng nên thiết kế **defense in depth** nhưng không để một lớp thiếu hẳn policy do cho rằng lớp khác “chắc đã chặn”.

## 14. Khi nào method không annotation vẫn an toàn?

Một method không có annotation trực tiếp **không tự động là lỗ hổng**. Ví dụ:

- Method internal thuần tính toán không đọc/ghi resource nhạy cảm.
- Một helper nhận dữ liệu đã được validate, chỉ được gọi từ use case đã qua policy; nhưng vẫn cần đảm bảo không có entry point khác gọi bypass.
- Một getter cho constant công khai.
- Một method được class/interface annotation bảo vệ.
- Một method nằm trong pointcut advisor và được kiểm thử.
- Một repository được gọi chỉ từ một service bảo đảm tenant scope và domain policy; repository vẫn nên có contract/ngăn dùng sai.

Điểm quyết định là **đường gọi và chức năng được thực thi**, không phải có hay không có dòng `@PreAuthorize`. Mọi method thao tác dữ liệu nhạy cảm hoặc thực hiện side effect cần có một checkpoint bảo mật **không thể bị lách qua đường gọi hợp lệ trong kiến trúc**.

Một dự án có hàng nghìn helper không cần phủ annotation cho từng helper bằng mọi giá. Nhưng mọi **entry point vào use case nhạy cảm** phải được nhận diện, gán policy và kiểm thử.

## 15. @PostAuthorize không thay được default-deny trước method

Ví dụ:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView read(long id) {
    return repository.loadView(id);
}
```

`@PostAuthorize` có thể hữu ích khi owner nằm trong return object, nhưng body đã chạy để tạo kết quả. Với read, điều này có thể chấp nhận nếu query và logging không làm rò dữ liệu trước post-check; với write, không nên dùng như guard chính.

Một command nguy hiểm:

```java
@PostAuthorize("denyAll()")
public void transferMoney(long transferId) {
    paymentGateway.sendMoney(transferId);
}
```

Method có thể đã gọi external API trước khi hậu kiểm từ chối. Dù có `@Transactional`, database rollback không hoàn tác mọi external side effect. Với write, dùng `@PreAuthorize` hoặc guard trong service **trước** khi thay đổi dữ liệu, với transaction/locking phù hợp.

**Đừng nhầm** “method có annotation” với “annotation bảo vệ đúng thời điểm”.

## 16. Default-deny ở service không thay ownership/tenant authorization

Ví dụ:

```java
@Service
@PreAuthorize("denyAll()")
public class DocumentService {

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(long documentId) {
        return repository.findViewById(documentId);
    }
}
```

Bây giờ method `read` đã có rule tường minh; nhưng actor có `document:read` vẫn có thể lấy ID thuộc người khác nếu `findViewById` bỏ qua tenant/owner. **Default-deny cho method chưa được khai báo không phải giải pháp IDOR/BOLA.**

Policy đủ chặt:

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView read(long id) {
    Actor actor = actorResolver.requireAuthenticatedActor();
    Document doc = repository
        .findByIdAndTenantId(id, actor.activeTenantId())
        .orElseThrow(DocumentNotFoundException::new);

    if (!documentPolicy.canRead(actor, doc)) {
        throw new AccessDeniedException("Not accessible");
    }

    return mapper.toView(doc);
}
```

Đây là **snippet tích hợp**: Actor, repo, domain policy, mapper và exception do app định nghĩa. Nó minh họa ba điều kiện: có quyền chức năng, có tenant scope, có quyền trên resource cụ thể.

Một method có rule `@PreAuthorize("hasRole('ADMIN')")` cũng không mặc nhiên được bypass tenant/ACL. Nếu muốn admin đọc mọi document cùng tenant, cần capability `document:read:tenant` tường minh và policy giới hạn tenant.

## 17. Test cần xác minh cả method “bị quên annotation”

Nếu áp dụng class-level default deny, kiểm thử một method **không có annotation riêng**:

```java
// Trong Spring Boot test với @EnableMethodSecurity,
// inject DocumentCommandService do Spring quản lý.
@Test
@WithMockUser(authorities = {"document:read"})
void unreviewedExportRemainsDenied() {
    assertThatThrownBy(
        () -> documentCommandService.exportAllDocuments()
    ).isInstanceOf(AccessDeniedException.class);
}
```

Test phải gọi **bean qua Spring proxy**, không gọi `new DocumentCommandService(...)`. Nếu tự tạo object, bạn đang kiểm tra logic Java trực tiếp chứ không kiểm tra method security interception.

Để chứng minh override hoạt động:

```java
@Test
@WithMockUser(authorities = {"document:read"})
void reviewedReadIsAllowed() {
    assertThat(documentCommandService.readDocument(42L))
        .isNotNull();
}

@Test
@WithMockUser(authorities = {"document:read"})
void readOnlyUserCannotDelete() {
    assertThatThrownBy(
        () -> documentCommandService.deleteDocument(42L)
    ).isInstanceOf(AccessDeniedException.class);
}
```

Các snippet yêu cầu JUnit 5, AssertJ, `@WithMockUser`/`spring-security-test`, config method security, domain fixtures và exception mapping phù hợp. Ví dụ `readDocument` phải có handler/fixture thật trả data; nếu repository trả null hoặc policy từ chối thì test ALLOW vẫn fail ở chặng khác. Đừng coi một test 403 là bằng chứng đầy đủ khi nguyên nhân thực ra đến từ DB hoặc HTTP filter.

### Kiểm thử âm tính với no-annotation

Test giá trị nhất là:
- Tạo một method public không annotation trong class default-deny.
- Gọi qua bean proxy bằng user đủ login nhưng **không** có grant riêng.
- Xác minh **method body không chạy** và state không đổi.
- Xác minh một method khác được whitelist đúng vẫn chạy.
- Lặp lại bằng anonymous/role thấp/admin.
- Nếu một method được phép ở class thông qua baseline, xác minh method mới giữ baseline.

## 18. MockMvc test catch-all HTTP thật sự

Giả sử HTTP policies:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/info").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

Ma trận:

| Request | Actor | Kỳ vọng HTTP |
| --- | --- | --- |
| GET /api/public/info | Anonymous | ALLOW |
| POST /api/public/info | Anonymous | DENY nếu không có rule ghi công khai |
| GET /api/admin/users | ROLE_USER | DENY |
| GET /api/admin/users | ROLE_ADMIN | ALLOW HTTP |
| GET /api/documents/42 | Anonymous | DENY |
| GET /api/documents/42 | Authenticated | ALLOW tại rule HTTP, nhưng method/domain policy có thể DENY |
| GET /private-new-route | Authenticated | DENY do catch-all |
| POST /api/documents/42/delete | ROLE_USER | Có thể qua HTTP authenticated, phải bị method/domain policy từ chối nếu thiếu quyền |

Một test route mới:

```java
@Test
void unknownRouteIsNotPublic() throws Exception {
    mvc.perform(get("/private-new-route")
            .with(user("reader").roles("USER")))
        .andExpect(status().isForbidden());
}
```

Đây là snippet MockMvc, không phải `javac` standalone. Để phân biệt `denyAll` với 404 vì không có handler, tốt nhất có fixture route/controller thật và kiểm tra interceptor/handler không được gọi. Với POST/PATCH dùng session/CSRF, cung cấp CSRF token hợp lệ để test không pass 403 vì `CsrfFilter` trước khi đến authorization policy.

**HTTP test thôi chưa chứng minh** các method gọi từ event listener, job hoặc service bean đã được bảo vệ.

## 19. Java 17+ chạy độc lập: mô phỏng no-annotation, class-default và override

Chương trình Java thuần sau tự định nghĩa annotation `@Policy` và một bộ kiểm tra đơn giản để mô phỏng cách **method policy override class policy**. Nó **không phải implementation của Spring Security hoặc Spring AOP**, không chứng minh proxy của framework. Mục đích là quan sát ba trạng thái:
- Không có method/class policy → **NO_GUARD**.
- Class có DENY → method thiếu annotation riêng **bị chặn**.
- Method có policy riêng → override class default.

Lưu thành file `MethodDefaultPolicyDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Set;

public class MethodDefaultPolicyDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Policy {
        String value();
    }

    record Actor(boolean authenticated, Set<String> authorities) {}

    static class UnprotectedService {
        public String export() {
            return "exported";
        }
    }

    @Policy("DENY")
    static class ProtectedService {
        @Policy("USER")
        public String read() {
            return "document";
        }

        public String purge() {
            return "deleted";
        }

        @Policy("PUBLIC")
        public String health() {
            return "ok";
        }
    }

    static String call(Object target, String operation, Actor actor)
            throws ReflectiveOperationException {
        Method method = target.getClass().getDeclaredMethod(operation);
        Policy methodPolicy = method.getAnnotation(Policy.class);
        Policy classPolicy = target.getClass().getAnnotation(Policy.class);

        String rule = methodPolicy != null
            ? methodPolicy.value()
            : classPolicy != null ? classPolicy.value() : "NO_GUARD";

        boolean allowed = switch (rule) {
            case "DENY" -> false;
            case "PUBLIC", "NO_GUARD" -> true;
            case "USER" -> actor.authenticated()
                && actor.authorities().contains("ROLE_USER");
            default -> throw new IllegalStateException(rule);
        };

        if (!allowed) {
            return "DENY " + operation + " via " + rule;
        }
        return "ALLOW " + operation + " via " + rule
            + " -> " + method.invoke(target);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Actor guest = new Actor(false, Set.of());
        Actor user = new Actor(true, Set.of("ROLE_USER"));
        UnprotectedService unsafe = new UnprotectedService();
        ProtectedService safe = new ProtectedService();

        System.out.println("Unsafe guest: "
            + call(unsafe, "export", guest));
        System.out.println("Safe guest purge: "
            + call(safe, "purge", guest));
        System.out.println("Safe guest read: "
            + call(safe, "read", guest));
        System.out.println("Safe user read: "
            + call(safe, "read", user));
        System.out.println("Safe guest health: "
            + call(safe, "health", guest));
        System.out.println("Safe user purge: "
            + call(safe, "purge", user));
    }
}
```

Biên dịch và chạy JDK 17 trở lên:

```bash
javac MethodDefaultPolicyDemo.java
java MethodDefaultPolicyDemo
```

Stdout chính xác:

```text
Unsafe guest: ALLOW export via NO_GUARD -> exported
Safe guest purge: DENY purge via DENY
Safe guest read: DENY read via USER
Safe user read: ALLOW read via USER -> document
Safe guest health: ALLOW health via PUBLIC -> ok
Safe user purge: DENY purge via DENY
```

**Ý nghĩa:** `UnprotectedService.export` không có class/method policy nên bộ mô phỏng không chặn guest. `ProtectedService.purge` không có annotation riêng nhưng kế thừa policy DENY của class. `read` và `health` có annotation riêng nên override baseline. Khi user thiếu role, `read` bị từ chối.

**Giới hạn bắt buộc:** `@Policy` trong demo do bài này tự định nghĩa, không phải annotation của Spring. `MethodDefaultPolicyDemo.call` dùng reflection để mô phỏng rule resolution; Spring thật dùng AOP advisors, annotation discovery và Authentication. Đừng copy bộ mô phỏng này vào production.

## 20. Chính sách không có annotation theo loại method

Không phải tất cả method đều cần cùng một mức bảo vệ. Một phân loại thực tế:

| Loại method | Ví dụ | Cách bảo vệ gợi ý |
| --- | --- | --- |
| Public query không lộ dữ liệu riêng | `getPublicVersion()` | Explicit public policy ở HTTP/method phù hợp |
| Query của người đã đăng nhập | `getMyProfile()` | Authentication + ràng buộc actor ID server-side |
| Query document riêng tư | `readDocument(id)` | Authority read + tenant/owner/ACL |
| Command write | `renameDocument(id)` | Quyền chức năng + policy trong transaction trước side effect |
| Command đặc quyền | `approvePayment(id)` | Permission mạnh + SoD, state, hạn mức, MFA khi cần |
| Background task | `expireSessions()` | Service actor/job scope, log và policy rõ |
| Helper thuần | `normalizeTitle()` | Có thể không cần annotation nhưng không phải public use case |
| Internal event handler | `onPaymentEvent(evt)` | Xác minh event origin/identity và domain invariants |
| Repository gateway | `findAllByTenant(...)` | Query scoping và contract, tránh bypass service |

Khi thêm một public method mới vào service nhạy cảm, kiến trúc default-deny class-level khiến việc bỏ quên policy dễ bộc lộ hơn (method bị DENY). Nhưng nếu một developer thêm direct repository access ở controller, class-level policy của một service **không liên quan** sẽ không bảo vệ nó. Review kiến trúc vẫn bắt buộc.

## 21. Phương thức kế thừa từ class/interface và những rủi ro đặc biệt

Cần xem:
- Method được khai báo trong interface nhưng implement ở class khác.
- Annotation ở interface method/class.
- Annotation ở class cha, method override ở class con.
- Cùng method thừa hưởng annotation từ nhiều interface.
- Java bridge methods/generics và proxy type.
- Meta annotations được định nghĩa bởi ứng dụng.
- Cấu hình `@EnableMethodSecurity` bật những nhóm annotation nào.

Tài liệu Spring Security nói annotation có thể đặt ở method, class và interface; method-level có thể override class-level khi cùng loại. Với mâu thuẫn nhiều interface, framework có thể từ chối startup để tránh ambiguity.

Do đó, **không dùng một reflection scanner đơn giản chỉ đọc declared method annotations rồi khẳng định “mọi method được bảo vệ”**. Scanner là hỗ trợ review, nhưng runtime pointcut/advisor và integration tests mới là bằng chứng áp dụng policy.

Một mã như:

```java
method.isAnnotationPresent(PreAuthorize.class)
```

sẽ không phát hiện đầy đủ annotation tại class/interface/meta hoặc custom AOP rules. Có thể dùng ArchUnit hoặc custom static checks để phát hiện các service public methods không có **effective policy**, nhưng check phải phù hợp inheritance và exception list, không được báo “safe” chỉ vì thấy một annotation bất kỳ.

## 22. Runtime coverage inventory: từ entry point tới method use case

Tạo ma trận:

| Entry point | Service method | Effective method rule | HTTP rule | Resource policy | Negative test |
| --- | --- | --- | --- | --- | --- |
| GET /api/documents/{id} | `read(id)` | `document:read` | Authenticated | Tenant + owner/ACL | User khác owner DENY |
| POST /api/documents/{id}/delete | `delete(id)` | `document:delete` | Authenticated | Tenant + status | User chỉ READ DENY |
| GET /api/public/version | `getVersion()` | Explicit PUBLIC | Public GET | Không có data riêng | POST không tự public |
| @Scheduled cleanup | `cleanup()` | Service actor / explicit default | Không có HTTP | Scope dữ liệu + audit | Job context thiếu quyền DENY |
| Message listener | `process(event)` | Explicit command policy | Không có HTTP | Event origin, tenant, state | Forged event DENY |
| GraphQL mutation | `rename(id)` | `document:rename` | POST /graphql | Tenant + owner + status | Viewer DENY |
| New controller route | `exportAll()` | Class-level denyAll cho tới review | HTTP fallback | Export policy | Không có grant DENY |

Với mỗi use case, hãy hỏi:
1. Entry point này có thể được gọi bởi những ai?
2. Caller có đi qua HTTP filter hay không?
3. Lời gọi service có đi qua Spring proxy không?
4. Method có annotation class/interface/meta hay custom pointcut hiệu lực không?
5. Có policy theo object/tenant/capability không?
6. Có phương thức nội bộ hoặc đường vào khác bỏ qua guard không?
7. Negative test nào chứng minh không có bypass?

**Không đồng nhất coverage với số annotation**. Coverage phải đo bằng hành vi chính sách trên các đường gọi thật.

## 23. Khi method-security hoạt động nhưng vẫn sai quyền

Một service:

```java
@PreAuthorize("hasRole('USER')")
public DocumentView readDocument(long id) {
    return repository.findById(id);
}
```

Dù method được bảo vệ, mọi user có ROLE_USER có thể truy cập các ID khác nếu thiếu object authorization. Với default-deny ở class, việc khai báo `hasRole('USER')` làm method này vượt baseline, nhưng vẫn cần policy dữ liệu.

Ràng buộc:

```text
ALLOW readDocument
    = method policy hasAuthority("document:read")
      AND resource belongs to verified tenant
      AND (owner OR ACL READ OR explicit tenant-wide grant)
      AND state permits reading
```

Chọn cách implement:
- `@PreAuthorize` gọi bean `@documentPolicy.canRead(authentication, #id)` cho check trước method.
- Hoặc tải entity có scope và check policy trong service.
- Hoặc phối hợp cả hai; tránh duplicate DB reads và TOCTOU.
- `@PostAuthorize` có thể hữu ích trên read returnObject, nhưng không bảo vệ side effect trước body.

Không kết luận “method có annotation = đã an toàn” nếu data scope chưa được kiểm chứng.

## 24. Không có default-deny thì cần làm gì trong code review?

Nếu dự án chọn annotation-driven opt-in (không class-level deny), quy trình reviewer nên có:
- Danh sách service methods được coi là public entry points.
- Danh sách method nào được bảo vệ qua HTTP và đường gọi khác.
- Bằng chứng method annotations đã được enable.
- Test cho use case nhạy cảm và actor thiếu quyền.
- Policy riêng cho owner/tenant/ACL và state.
- Check service mới có thể được gọi từ batch/job/listener.
- Không có self-invocation bypass security.
- Mapping tương ứng giữa controllers/resolvers/listeners và application service.
- Test thay đổi khi thêm method/endpoint mới.

Với team lớn, có thể bổ sung lint/ArchUnit rule:
- Public methods thuộc package `application.command` phải có annotation hiệu lực hoặc policy wrapper.
- Exception cho pure helpers được ghi rõ.
- Controller không gọi repository nhạy cảm trực tiếp.
- Commands không thực hiện side effect trước authorizer.
- Method privileged phải có negative tests.

Một scanner tĩnh không hiểu proxy semantics và security configuration toàn bộ sẽ không bảo đảm coverage tuyệt đối. Dùng nó như *guardrail*, không phải proof.

## 25. 401, 403 và lỗi do cấu hình không rõ

Một method bị `@PreAuthorize` DENY thông thường ném `AccessDeniedException` hoặc subtype liên quan; nếu đi qua HTTP và `ExceptionTranslationFilter`/handlers phù hợp, đã xác thực nhưng thiếu quyền thường ra 403. Anonymous vào API yêu cầu login thường ra 401 (bearer) hoặc redirect (form login). Chỉ nhìn HTTP status chưa biết pointcut nào từ chối.

Những nguyên nhân test dễ nhầm:
- 403 vì CSRF token thiếu trên POST/PATCH, không phải default-deny.
- 404 vì không có controller, không chứng minh rule deny.
- 403 vì domain policy owner/tenant, không chứng minh `@PreAuthorize` chạy.
- 401 do bearer authentication trước method.
- Method không có proxy nhưng body tự ném `AccessDeniedException`; annotation có thể hoàn toàn không tham gia.
- Test dùng user có nhiều authority nên ALLOW dù rule quá rộng.

Hãy dùng mock/spies xác minh **method body không chạy** khi before-rule từ chối, và kiểm tra dữ liệu/side effects không đổi. Khi cần debug, xem log chain/advisor với không ghi credential hay thông tin private.

## 26. Không dùng @DenyAll “mọi nơi” rồi cho phép bằng annotation khác một cách mơ hồ

Một thiết kế dễ sai:

```java
@PreAuthorize("denyAll()")
public class SensitiveService {
    @PermitAll
    public String status() {
        return "OK";
    }
}
```

Nếu bật JSR-250, `@PermitAll` có interceptor riêng; nó không mặc định override `@PreAuthorize("denyAll()")` của class. Spring có thể xử lý cả hai quyết định theo semantics của từng advisor. Đây **không phải** một cách mở exception đáng tin.

Dùng cùng loại để override:

```java
@Service
@PreAuthorize("denyAll()")
public class SensitiveService {

    @PreAuthorize("permitAll()")
    public String status() {
        return "OK";
    }
}
```

Ngay cả khi override thành công, phương thức này có thể vẫn bị HTTP auth hoặc một custom pointcut advisor khác chặn. Test thật trên app version cụ thể.

Nếu không muốn security policy public và private cùng trong một bean, hãy tách bean để đơn giản hóa policy. Tránh dùng annotations trùng lặp hoặc mâu thuẫn chỉ để ép một test pass.

## 27. Chọn mô hình bao phủ nào cho từng hệ thống?

| Mô hình | Mức bảo đảm của mặc định | Rủi ro và yêu cầu |
| --- | --- | --- |
| Annotation opt-in từng method | Method chưa annotation thường không có guard method tương ứng | Phải kiểm kê entry points; có HTTP catch-all và domain policy |
| Class-level `@PreAuthorize("denyAll()")` | Method chưa override bị deny khi proxy advice áp dụng | Phải review override, test self-invocation, tách helper |
| Class-level `@PreAuthorize("isAuthenticated()")` | Method chưa override yêu cầu authenticated | Không đủ cho privileged commands, ghi rõ owner/ACL |
| Custom service pointcut advisor | Method khớp pointcut có check dù không annotation | Có thể miss package/bean, AND với annotations; version/proxy QA |
| HTTP default deny | Chặn route chưa khai báo trong chain | Không bảo vệ job/queue/service direct, chain fallback cần có |
| Domain service policy | Kiểm tra actor-resource-context ngay trước sử dụng | Phải được gọi từ mọi entry point, quản lý transaction/concurrency |

Không có một công tắc “mặc định deny mọi method Spring” vừa an toàn vừa tương thích với mọi bean. Chính sách tốt nhất được chọn theo **ranh giới use case**, với chứng cứ test đúng.

## 28. Checklist trước khi đánh dấu service được bảo vệ đầy đủ

1. `@EnableMethodSecurity` đã bật trong app context thật chưa?
2. Những annotation đang sử dụng có được enable đúng nhóm không (`@Secured`, JSR-250)?
3. Với mỗi method quan trọng, effective annotation/pointcut nằm ở method, class, interface hay custom advisor?
4. Method không có annotation riêng có class-level default thực sự không?
5. Method-level override cùng loại đã ghi đủ điều kiện quyền chưa?
6. `@PermitAll`/`@DenyAll` khác loại có tạo ngộ nhận override không?
7. Custom pointcut có khớp đúng class/package/method thực tế không?
8. Spring bean/proxy có được dùng ở mọi entry point không?
9. Có self-invocation, private/final method hay object tạo bằng `new` không?
10. HTTP `anyRequest`/fallback chain có chặn route chưa liệt kê không?
11. Có đường ngoài HTTP (job, queue, GraphQL, event) gọi operation không?
12. Chỉ role/authority hay còn cần owner/tenant/ACL/state?
13. Có side effect nào chạy trước authorization không?
14. Transaction, locking và policy update có tránh TOCTOU không?
15. Anonymous, user thấp quyền, đủ quyền, khác tenant đều đã test chưa?
16. Test người đúng role nhưng sai object có bị DENY không?
17. Test method mới không có annotation trong class default-deny có bị DENY không?
18. Test controller mới không có rule HTTP có bị chặn đúng không?
19. Error handling và audit có giữ bí mật dữ liệu khi DENY không?
20. Security config trong staging/prod có giống test (proxy/AOP/role mapping) không?

### Câu hỏi tự kiểm tra

**Câu 1.** Chỉ có `@EnableMethodSecurity`, một method public trong Spring service không có annotation bảo mật hiệu lực. Spring mặc định deny không?  
→ **Không.** Annotation-based interceptors chỉ bảo vệ điểm khớp rule/pointcut của chúng.

**Câu 2.** Class có `@PreAuthorize("denyAll()")`, method không khai báo annotation riêng. Khi gọi qua proxy, có thể chạy body không?  
→ **Không**, nếu interceptor `@PreAuthorize` được bật và thực thi đúng.

**Câu 3.** Class có `@PreAuthorize("denyAll()")`, method có `@PreAuthorize("hasRole('USER')")`. Hai điều kiện AND hay method override?  
→ Với **cùng loại** `@PreAuthorize`, method-level rule ưu tiên/override class-level.

**Câu 4.** Dùng `@PermitAll` để mở method trong class có `@PreAuthorize("denyAll()")` có luôn hiệu quả không?  
→ **Không thể giả định.** Hai loại interceptor khác nhau; muốn override rõ ràng dùng method-level `@PreAuthorize("permitAll()")` và test.

**Câu 5.** Có `anyRequest().denyAll()` tại HTTP. Một job gọi thẳng service method không annotation có được HTTP rule chặn không?  
→ **Không.** Job không đi qua HTTP filter chain.

**Câu 6.** Method có annotation nhưng được gọi qua `this.securedMethod()`. Có chắc method security chặn không?  
→ **Không** trong proxy-AOP thông dụng; self-invocation có thể bypass advice.

**Câu 7.** Một custom pointcut yêu cầu ROLE_USER trên `*Service`. Có bảo vệ mọi class dưới package con không?  
→ Không mặc định. Phải kiểm tra biểu thức pointcut và package thực.

**Câu 8.** `@PostAuthorize("denyAll()")` được đặt trên method chuyển tiền. Có bảo đảm không chuyển tiền khi DENY không?  
→ **Không.** Check sau body có thể quá muộn.

**Câu 9.** Method đã có `@PreAuthorize("hasAuthority('document:read')")`, vậy đọc được mọi document ID không?  
→ **Không.** Cần domain policy owner/tenant/ACL/status.

**Câu 10.** Test không annotation nhưng 403 từ controller là bằng chứng đủ cho method default-deny không?  
→ **Không.** 403 có thể đến từ HTTP/CSRF/domain; phải test service bean proxy và xác định điểm deny.

## Kết luận

Trong Spring Security, **phương thức không có annotation bảo mật hiệu lực không tự bị DENY vì thiếu annotation**. `@EnableMethodSecurity` kích hoạt interception cho những annotation/pointcut được đăng ký; annotation ở class/interface hoặc custom advisor có thể bảo vệ method dù dòng method trống annotation. Để không bỏ lọt operation, hãy kết hợp **HTTP catch-all**, **class-level default-deny hoặc service pointcuts có phạm vi rõ**, **domain policy actor–resource**, và **negative integration tests trên đường gọi thực tế**. Một chính sách chỉ đúng trên source code nhưng bị bypass qua proxy, job, controller mới hoặc tenant query vẫn chưa phải bảo vệ đầy đủ.

## Tài liệu tham khảo chính thức

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — xác nhận unannotated methods, inheritance, pointcuts và các interceptor.
2. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — `anyRequest` fallback và HTTP authorization.
3. [Spring Security 6.5 — Method Security Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html#method-security-architecture) — `AuthorizationManagerBeforeMethodInterceptor`.
4. [Spring Security 6.5 — Spring AOP / Pointcut Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html#using-custom-pointcuts) — custom `Advisor`.
5. [Spring Security 6.5 — Test Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` và security method tests.
6. [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html) — Spring Security filters và chain selection.
