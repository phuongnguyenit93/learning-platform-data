# Annotation tổng hợp để tái sử dụng chính sách phân quyền trong Spring Security Servlet

## 1. Vì sao cần annotation tổng hợp?

Một ứng dụng Spring Security Servlet có nhiều service xử lý các tài nguyên khác nhau. Chẳng hạn:

- Chỉ `ROLE_ADMIN` được xem các báo cáo quản trị.
- Người dùng chỉ được đọc báo cáo thuộc sở hữu của mình; quản trị viên được đọc thêm theo chính sách của hệ thống.
- Một endpoint kiểm toán yêu cầu **đồng thời** role admin và xác thực đầy đủ, không chỉ remember-me.
- Cùng chính sách đọc báo cáo được áp dụng cho phương thức ở `ReportService` và `ArchiveService`.
- Những quy tắc này phải được thực thi dù service được gọi từ controller, một service khác hoặc một tác vụ có cơ chế xác thực phù hợp.

Cách trực tiếp là lặp annotation trên từng method:

```java
@PreAuthorize("hasRole('ADMIN')")
public String adminSummary() {
    return "admin:summary";
}
```

Khi có nhiều method, lặp biểu thức SpEL dài dễ gây **policy drift**: một nơi dùng `hasRole('ADMIN')`, nơi khác chỉ kiểm tra `authenticated()` hoặc gõ sai tên bean. Spring Security hỗ trợ **meta-annotation** (annotation tổng hợp): ta tự tạo một annotation Java và đặt `@PreAuthorize` lên chính định nghĩa annotation đó.

Ví dụ:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

Khi một method được gắn `@RequiresAdmin`, Spring Security method security có thể tìm `@PreAuthorize` ở annotation tổng hợp và áp dụng chính sách tương ứng. Như vậy tên annotation phản ánh ý định nghiệp vụ, còn nội dung rule có một nguồn định nghĩa để bảo trì.

**Mục tiêu học tập:**

1. Phân biệt annotation tổng hợp, annotation lặp lại và biểu thức SpEL trong method security.
2. Tự tạo `@RequiresAdmin`, `@CanReadReport`, `@RequiresAdminFull` với `@Target`, `@Retention` và `@Documented` đúng.
3. Bật `@EnableMethodSecurity` và đặt annotation tại các **public methods của Spring-managed beans**.
4. Hiểu method arguments trong SpEL, `@P("reportId")` và lời gọi bean `@reportPermission`.
5. Biết giới hạn proxy/self-invocation, thứ tự HTTP authorization và method authorization, cũng như cách viết kiểm thử.
6. Tránh nhầm annotation tái sử dụng với cơ chế tự tạo quyền mới hoặc bypass authentication.

Ví dụ chính sử dụng **Java 17, Spring Boot 3.3.5, Spring Security 6.3.x (Servlet/MVC)**. Các tính năng annotation templating hoặc API mới ở version khác cần được xem lại theo tài liệu phiên bản đang dùng; bài không giả định mọi version đều có cú pháp giống nhau.

## 2. Method security và HTTP security là hai lớp khác nhau

Với HTTP authorization, cấu hình `authorizeHttpRequests` áp dụng rule theo đường dẫn request. Với **method security**, Spring Security áp dụng rule khi gọi **một phương thức Java** có annotation tương ứng thông qua cơ chế interception/proxy phù hợp.

```text
HTTP request GET /reports/r101
       |
       v
Servlet SecurityFilterChain
       |
       +-- Authentication (Basic/session/bearer/form)
       +-- authorizeHttpRequests(...) cho request đi tiếp
       |
       v
ReportController
       |
       v
Spring bean proxy của ReportService
       |
       +-- Before-method authorization interceptor
       |        đọc @CanReadReport
       |        tìm meta-annotation @PreAuthorize
       |        đánh giá SpEL với Authentication + method args
       |
       +-- GRANT: gọi target service method
       |
       +-- DENY: ném AccessDeniedException
       |
       v
Service result -> Controller response
```

Hai lớp bảo vệ giải quyết các câu hỏi khác nhau:

| Lớp | Đối tượng xét | Ví dụ |
| --- | --- | --- |
| HTTP filter security | URL, method, request và authentication | `GET /reports/**` phải có login |
| Method security | Lời gọi phương thức Java và đối số | User chỉ được xem report ID họ sở hữu |
| Domain/data policy | Resource thực, tenant, trạng thái và quyền sở hữu | Report `r101` thuộc user `lan` |
| Business transaction | Kiểm tra khi thực thi ghi dữ liệu | Không thay owner sau khi authorization nếu không có policy phù hợp |

HTTP security không luôn bảo vệ các lời gọi service từ message listener, scheduler hoặc tests; method security có thể áp dụng khi lời gọi **đi qua proxy đúng cách** và có security context phù hợp. Nhưng method security cũng không tự thay thế việc phân tích toàn bộ HTTP entry point và CSRF.

### 2.1. Bật method security

Trong ứng dụng Spring Security 6 Servlet, khai báo:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // Các bean và SecurityFilterChain...
}
```

`@EnableMethodSecurity` bật hạ tầng cho method security, trong đó hỗ trợ `@PreAuthorize` và `@PostAuthorize` theo cấu hình mặc định. Nếu chỉ có `@PreAuthorize` mà không bật cơ chế interception phù hợp, annotation có thể không được thực thi như mong đợi.

Trong ứng dụng cũ có thể thấy `@EnableGlobalMethodSecurity`; với Spring Security 6, ưu tiên `@EnableMethodSecurity`. Nếu muốn dùng `@Secured` hoặc `@RolesAllowed`, cần xem các flag như `securedEnabled` và `jsr250Enabled`; không suy ra chúng đều được bật theo mặc định.

### 2.2. Annotation tổng hợp không phải một bộ lọc HTTP

`@RequiresAdmin` không tự thêm filter và cũng không xác minh mật khẩu. Nó giúp method security tìm lại một biểu thức phân quyền đã khai báo ở `@PreAuthorize`. Authentication thường đến từ request đã qua security filter chain, hoặc từ security context được thiết lập tin cậy trong một loại tác vụ khác.

## 3. Meta-annotation trong Java: cú pháp và cơ chế phát hiện

Trong Java, annotation có thể được đặt trên **định nghĩa annotation khác**. Đối với custom authorization annotation, thông thường cần:

- `@Target`: chọn vị trí dùng annotation; ở ví dụ là `ElementType.METHOD`. Có thể cho phép cả `TYPE` khi chính sách thực sự áp dụng được cho mọi method của một class.
- `@Retention(RetentionPolicy.RUNTIME)`: metadata tồn tại lúc chạy để framework có thể inspect.
- `@Documented`: công cụ Javadoc có thể hiện annotation trong tài liệu API.
- `@PreAuthorize("...")`: điều kiện bảo mật được Spring Security tìm và thực thi khi method security được bật.

Ví dụ đầy đủ của một annotation không nhận tham số:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

Sau đó dùng:

```java
@RequiresAdmin
public String adminSummary() {
    return "admin:summary";
}
```

**Ý nghĩa:** annotation đặt tên cho một policy cố định để nhiều method cùng dùng, giảm khả năng sao chép sai SpEL. Nó không tạo ra một role mới, không cấp quyền cho caller và không tự thêm Authentication vào SecurityContext.

### 3.1. Tại sao RetentionPolicy.RUNTIME cần thiết?

Method security phân tích annotation qua thông tin runtime. Nếu chỉ để `SOURCE` hoặc `CLASS` mà không duy trì metadata runtime theo nhu cầu framework, custom meta-annotation có thể không được phát hiện đúng lúc cần ra quyết định.

`@Documented` chỉ phục vụ tài liệu; nó **không** tự bật phân quyền. `@Inherited` cũng không phải lời giải chung cho method-level inheritance vì quy tắc thừa kế annotation của Java và tìm kiếm annotation hợp nhất của Spring khác nhau; cần test thực tế trên interface, override và proxy.

### 3.2. METHOD hay TYPE?

Một annotation chỉ có `@Target(ElementType.METHOD)` có thể được dùng trên method, không gắn lên class. Nếu chính sách giống nhau cho mọi method trong một service, có thể cân nhắc:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface AdminOnly {
}
```

Tuy nhiên, class-level policy là quyết định có phạm vi rộng: một method `public` mới thêm vào sau này cũng có thể nhận chính sách đó tùy quy tắc kế thừa/override. Nếu annotation dùng biến như `#reportId` thì gắn trên class chỉ an toàn khi tất cả method cần bảo vệ thật sự có argument tương ứng. Ví dụ runnable chọn **METHOD-only** để giữ hợp đồng rõ ràng.

### 3.3. Không nhầm annotation ghép với annotation lặp

Một meta-annotation như `@RequiresAdmin` giúp **định nghĩa một rule đặt tên**. Nó khác với việc xếp chồng nhiều `@PreAuthorize` cùng method rồi hy vọng chúng tự động được kết hợp.

Spring Security **không hỗ trợ lặp tùy tiện một loại `@PreAuthorize`** trên cùng method như một danh sách điều kiện. Muốn AND role và full trust, viết **một biểu thức** `hasRole('ADMIN') and isFullyAuthenticated()`, hoặc dùng authorization manager/policy kết hợp rõ ràng.

## 4. Annotation tổng hợp với biểu thức SpEL tái sử dụng

Đối với rule cố định, SpEL đơn giản là đủ:

```java
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

Đối với tài nguyên theo đối số method, ta có thể tham chiếu parameter:

```java
@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")
public @interface CanReadReport {
}
```

Trong biểu thức này:

- `@reportPermission` là bean Spring có tên `reportPermission`, không phải một annotation Java.
- `canRead(...)` là method public trên bean đó để trả boolean phân quyền.
- `authentication` là đối tượng Authentication trong evaluation context.
- `#reportId` là đối số của method được bảo vệ.
- Biểu thức trả `true` khi cho phép, `false` khi từ chối.

Đây là một **mảnh meta-annotation minh họa**; file hoàn chỉnh được cung cấp trong dự án mẫu ở phần 9.

### 4.1. Đảm bảo tên argument trong SpEL

Các biểu thức `#reportId` phụ thuộc việc Spring Security tìm được tên parameter. Điều này có thể đến từ metadata compiler như `-parameters` hoặc annotation chuyên dụng.

Trong code runnable, dùng:

```java
@CanReadReport
public String read(@P("reportId") String reportId) {
    return "report:" + reportId;
}
```

`@P` thuộc package `org.springframework.security.core.parameters.P`. Dùng `@P("reportId")` làm hợp đồng rõ ràng, hữu ích khi method được biên dịch không giữ parameter names hoặc khi code được gọi qua một số kiểu proxy/interface.

Đừng sao chép SpEL `#id` từ một method khác nếu argument được export tên `reportId`. Nếu tên không được giải, expression có thể nhận null hoặc lỗi evaluation; policy nên từ chối rõ, không fail-open.

### 4.2. Bean permission phải được quản lý bởi Spring

Nếu biểu thức viết `@reportPermission.canRead(...)`, cần có bean:

```java
@Component("reportPermission")
public class ReportPermission {
    public boolean canRead(Authentication authentication, String reportId) {
        // Quy tắc phân quyền có nguồn dữ liệu server đáng tin.
        return false; // Chỉ là mảnh placeholder minh họa cú pháp.
    }
}
```

Đoạn **này chỉ để minh họa cấu trúc**; implementation đầy đủ ở phần 9. Khi thực thi, code phải dùng dữ liệu server như owner/tenant, chứ không tin query `?owner=lan` do browser tự khai.

### 4.3. Vì sao không đưa luôn query DB dài vào SpEL?

Một biểu thức như `@reportPermission.canRead(authentication, #reportId)` đóng vai trò *delegation*. Nó giữ annotation ngắn và gom logic ownership/tenant vào một bean có thể unit-test.

Nếu viết cả chính sách nhiều bảng DB, time window, trạng thái tài khoản và exception handling bằng SpEL, code khó review, khó bảo trì và dễ có ngữ nghĩa null sai. Hãy giữ annotation ở mức biểu đạt “đang yêu cầu quyền nào”, còn business policy trong lớp Java có trách nhiệm rõ.

## 5. Annotation tổng hợp và nguyên tắc duy trì chính sách

### 5.1. Một policy, nhiều nơi sử dụng

`@CanReadReport` có thể đặt trên:

```java
@CanReadReport
public String read(@P("reportId") String reportId) {
    return "report:" + reportId;
}
```

và:

```java
@CanReadReport
public String archived(@P("reportId") String reportId) {
    return "archive:" + reportId;
}
```

Nếu hai service thực sự dùng cùng policy về quyền sở hữu report, sửa biểu thức ở **định nghĩa annotation** hoặc sửa bean permission giúp đồng bộ tất cả callers. Nếu archive có quy tắc quyền riêng, đừng ép chúng dùng cùng annotation chỉ vì tên cả hai đều chứa “report”.

### 5.2. Đặt tên theo ý định nghiệp vụ

Nên cân nhắc tên:

- `@RequiresAdmin`: dùng khi yêu cầu role.
- `@CanReadReport`: dùng khi quyền tùy thuộc reportId.
- `@RequiresAdminFull`: dùng khi admin và full authentication là hai điều kiện đồng thời.

Tên như `@SecuredThing` hoặc `@AllowEverythingExceptGuests` khó đưa ra hợp đồng rõ ràng; khi policy thay đổi dễ tạo hiểu nhầm. Một annotation được dùng rộng nên có Javadoc mô tả dữ liệu/đối số yêu cầu và mức bảo vệ.

### 5.3. Tránh policy drift khi thêm endpoint

Cùng một URL có thể đi vào nhiều phương thức service. Phương thức mới nếu quên annotation có thể được gọi mà không qua method security check tương ứng; HTTP authorization có thể hoặc không bảo vệ đường gọi đó.

Cần có checklist code review và integration tests cho service entry points mới. Không xem meta-annotation là bảo chứng rằng mọi method trong package tự động được bảo vệ.

## 6. Kết hợp nhiều điều kiện trong một annotation

Một chính sách yêu cầu **role admin AND full authentication** có thể viết:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public @interface RequiresAdminFull {
}
```

Điều này khác:

```java
// Không dựa vào cách này để tự AND hai điều kiện:
@RequiresAdmin
@PreAuthorize("isFullyAuthenticated()")
public String auditSummary() {
    return "audit:summary";
}
```

Cách thứ hai tạo nhiều nguồn rule `@PreAuthorize` chồng chéo và có thể gây lỗi ambiguity/configuration. **Định nghĩa một meta-annotation chuyên biệt** với biểu thức AND rõ ràng, hoặc dùng policy manager nếu điều kiện phức tạp.

### 6.1. hasRole không thay thế isFullyAuthenticated

Một remember-me authenticated user có thể vẫn mang `ROLE_ADMIN`. Nếu method chỉ `hasRole('ADMIN')`, điều đó tự thân không yêu cầu full authentication. Ngược lại, `isFullyAuthenticated()` không chứng minh có `ROLE_ADMIN`. Chúng là hai trục khác nhau.

**Lưu ý an ninh:** “fully authenticated” theo Spring Security chủ yếu phân biệt với anonymous và remember-me; nó **không tự chứng minh MFA gần đây**. Các nghiệp vụ thực sự nhạy cảm có thể cần recent reauthentication, thiết bị tin cậy hoặc MFA riêng.

### 6.2. Một annotation nhiều attributes có tự biến thành expression không?

Không nên kỳ vọng cú pháp giả định này tự hoạt động trong Spring Security 6.3.x:

```java
// KHÔNG PHẢI implementation tự động tương thích mọi version:
@PreAuthorize("hasRole('{role}')")
public @interface RequiresRole {
    String role();
}
```

Chỉ khai báo `String role()` không bảo đảm Spring Security thay `{role}` bằng giá trị attribute. Một số phiên bản Spring Security mới hơn có cơ chế **annotation expression templates**, với bean/config phù hợp. Nếu dự án cần annotation parameterized, phải dựa vào tài liệu đúng version và có integration test; đừng diễn giải literal `{role}` là biến tự động.

Trong ví dụ runnable dùng **annotation cố định** để bảo đảm rõ nghĩa và phù hợp các version được pin.

## 7. @PreAuthorize, @PostAuthorize và các loại annotation khác

### 7.1. @PreAuthorize: kiểm tra trước khi gọi method

`@PreAuthorize` thực hiện policy trước body method (khi interception đúng). Nếu bị từ chối, target method **không được chạy** qua lời gọi đó. Phù hợp cho hành động có tác dụng phụ vì chặn sớm trước mutation.

Ví dụ `@CanReadReport` sẽ kiểm tra owner/role trước khi `ReportService.read` trả dữ liệu.

### 7.2. @PostAuthorize: kiểm tra kết quả trả về

`@PostAuthorize` có thể đánh giá SpEL **sau** khi method đã chạy, ví dụ tham chiếu `returnObject`:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PostAuthorize(
    "returnObject != null and " +
    "(returnObject.owner() == authentication.name or hasRole('ADMIN'))"
)
public @interface CanSeeReturnedReport {
}
```

Đây là ví dụ **minh họa**; import `org.springframework.security.access.prepost.PostAuthorize`. Đối tượng trả về cần có method như `owner()`, ví dụ Java record `record Report(String id, String owner) {}`. Khi role/trust/return object không hợp lệ, interceptor có thể chặn việc trả kết quả cho caller.

**Cảnh báo:** method đã thực thi trước khi kiểm tra `@PostAuthorize`. Không dùng nó làm lớp bảo vệ duy nhất cho thao tác đã ghi DB, gửi tiền hoặc gửi email; hiệu ứng phụ có thể xảy ra trước khi deny. Với mutation, `@PreAuthorize` và kiểm tra ở transaction/domain layer thường phù hợp hơn.

### 7.3. @PreFilter, @PostFilter

Spring Security cũng có `@PreFilter`/`@PostFilter` để lọc collection/array hoặc một số cấu trúc được hỗ trợ theo ngữ nghĩa của version. Chúng có thể được dùng trong annotation tổng hợp khi phù hợp.

Cần kiểm thử kiểu collection, cách xử lý null, hiệu năng và semantics khi dataset lớn. Đừng tải tất cả báo cáo từ DB rồi lọc bằng `@PostFilter` và nghĩ đã có authorization hiệu quả ở tầng truy vấn: việc truy xuất dữ liệu nhạy cảm đã xảy ra trước khi lọc và có thể tiêu tốn tài nguyên lớn.

### 7.4. @Secured và @RolesAllowed

`@Secured` chủ yếu dựa trên roles/authorities, `@RolesAllowed` thuộc JSR-250/Jakarta trong môi trường tương thích. Tùy version và flags của `@EnableMethodSecurity`, chúng có thể cần bật riêng.

Bài dùng `@PreAuthorize` vì có thể biểu diễn vừa role, vừa business policy từ bean và method arguments. Không trộn nhiều hệ annotation lên cùng method khi chưa hiểu rule precedence/ambiguity.

## 8. Giới hạn của proxy: khi annotation có thể không chạy

### 8.1. Spring-managed bean và lời gọi qua proxy

Method security trong cấu hình phổ biến hoạt động qua Spring AOP proxies. Một lời gọi **từ bean khác qua proxy** tới public method có annotation được intercept. Ngược lại, tự tạo đối tượng bằng `new ReportService()` sẽ không tự được Spring method-security proxy bọc.

Vì thế ví dụ runnable đưa service vào container bằng `@Service`, inject vào controller, rồi gọi method từ controller. Tests còn gọi bean service được inject trực tiếp để xác nhận interceptor thực sự hoạt động.

### 8.2. Self-invocation

Xem ví dụ:

```java
@Service
public class ExampleService {
    public String facade(String id) {
        return this.protectedOperation(id);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String protectedOperation(String id) {
        return "protected:" + id;
    }
}
```

Đây là **đoạn minh họa**, không phải một file thuộc dự án runnable bên dưới. Trong proxy-based AOP, lời gọi `this.protectedOperation(...)` từ cùng object có thể **bypass method-security proxy**, nên annotation không được enforce ở lời gọi nội bộ đó.

Cách giải quyết thường rõ ràng hơn là tách protected method sang bean khác và gọi qua proxy; hoặc cấu trúc policy ở service boundary khác phù hợp. Không chữa bằng cách đặt annotation vào private method rồi hy vọng proxy intercept.

### 8.3. Private/final methods và kiểu proxy

Phần lớn proxy-based method interception không bảo vệ private method, và một số kiểu proxy có hạn chế với final class/final method. Khi dùng interface proxy, method có thuộc interface hay không cũng có thể ảnh hưởng lựa chọn proxy và annotation lookup.

Cần test trên bean trong môi trường chạy thật, đặc biệt với Kotlin (final mặc định), Java records/final classes, package-private methods và kiến trúc Spring AOT. Nếu dùng AspectJ weaving thay proxy, mô hình interception có thể khác; không suy rộng lỗi self-invocation giống hệt cho mọi chế độ weaving.

### 8.4. Một method được gọi ngoài HTTP

Nếu scheduled job hoặc message listener gọi Spring bean có method security, nhưng không có `Authentication` phù hợp trong `SecurityContextHolder`, policy có thể từ chối dù không có HTTP request. Đó có thể là điều đúng theo thiết kế.

Không “sửa” bằng cách dựng Authentication giả có ROLE_ADMIN từ dữ liệu chưa xác minh. Tác vụ hệ thống cần một trust model, service identity và policy riêng khi thật sự được ủy quyền.

## 9. Dự án Spring Boot 3.3.5 + Java 17 hoàn chỉnh

Đây là ứng dụng Servlet/MVC tự chứa, có **ba annotation tổng hợp**:

| Annotation | Meta-annotation | Điều kiện |
| --- | --- | --- |
| `@RequiresAdmin` | `@PreAuthorize("hasRole('ADMIN')")` | Có role admin |
| `@CanReadReport` | `@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")` | Report tồn tại và user là owner hoặc admin |
| `@RequiresAdminFull` | `@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")` | Admin và full authentication |

Hai service `ReportService` và `ArchiveService` cùng dùng `@CanReadReport`. HTTP layer chỉ yêu cầu authentication cho các route riêng tư, **các chính sách chi tiết được thực thi ở service methods**.

### 9.1. Cấu trúc thư mục

```text
method-meta-authorization/
  pom.xml
  src/
    main/
      java/example/meta/
        MetaAuthorizationApplication.java
        SecurityConfig.java
        ReportPermission.java
        ReportService.java
        ArchiveService.java
        DemoController.java
        policy/
          RequiresAdmin.java
          RequiresAdminFull.java
          CanReadReport.java
    test/
      java/example/meta/
        MetaAuthorizationTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>method-meta-authorization</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven `spring-boot-starter-security` kéo method-security/Spring AOP dependencies phù hợp cho Spring Boot 3.3.x. `spring-security-test` giúp kiểm thử SecurityContext và form/Basic mechanisms ở tầng test.

### 9.3. MetaAuthorizationApplication.java

```java
package example.meta;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetaAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetaAuthorizationApplication.class, args);
    }
}
```

### 9.4. Annotation @RequiresAdmin

File `src/main/java/example/meta/policy/RequiresAdmin.java`:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN')")
public @interface RequiresAdmin {
}
```

Mặc định `hasRole('ADMIN')` kiểm tra authority `ROLE_ADMIN` theo quy ước. Trong ví dụ `roles("ADMIN")` của Spring Security sẽ tạo authority này.

### 9.5. Annotation @RequiresAdminFull

File `src/main/java/example/meta/policy/RequiresAdminFull.java`:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public @interface RequiresAdminFull {
}
```

Annotation này gói hai điều kiện trong **một** biểu thức rõ ràng. Với HTTP Basic authentication hợp lệ ở sample, user admin có thể được nhận diện là full theo trust resolver thông thường; không nhầm với remember-me token.

### 9.6. Annotation @CanReadReport

File `src/main/java/example/meta/policy/CanReadReport.java`:

```java
package example.meta.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")
public @interface CanReadReport {
}
```

Đây là điểm chính của bài: method gắn `@CanReadReport` phải có đối số được export tên `reportId` trong SpEL context. Các service bên dưới dùng `@P("reportId")`.

### 9.7. ReportPermission: quyền sở hữu lấy từ server

File `src/main/java/example/meta/ReportPermission.java`:

```java
package example.meta;

import java.util.Map;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPermission")
public class ReportPermission {

    private final Map<String, String> owners = Map.of(
        "r101", "lan",
        "r202", "minh"
    );

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public boolean canRead(Authentication current, String reportId) {
        if (reportId == null) {
            return false;
        }

        String owner = owners.get(reportId);
        if (owner == null) {
            return false;
        }

        if (current == null || !trust.isAuthenticated(current)) {
            return false;
        }

        boolean isOwner = owner.equals(current.getName());
        boolean isAdmin = current.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_ADMIN".equals(authority.getAuthority()));

        return isOwner || isAdmin;
    }
}
```

Điểm cần nhớ:

- Người đọc `lan` được xem `r101` nhưng không xem `r202` của `minh`.
- Admin được xem report đã tồn tại theo chính sách demo. Trong sản phẩm đa tenant, admin có thể vẫn bị giới hạn trong tenant.
- Report ID không tồn tại → deny; không `return true` hoặc “abstain” rồi để tầng khác grant.
- Ownership lấy từ một map **phía server**, không từ query `?owner=lan` do client tự gắn.
- `AuthenticationTrustResolver` loại anonymous ngay cả khi `AnonymousAuthenticationToken.isAuthenticated()` có thể true.
- Map chỉ phục vụ demo; trong sản phẩm dùng repository/authorization domain service và cân nhắc quyền ngay khi load/commit dữ liệu.

### 9.8. ReportService.java

```java
package example.meta;

import example.meta.policy.CanReadReport;
import example.meta.policy.RequiresAdmin;
import example.meta.policy.RequiresAdminFull;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @CanReadReport
    public String read(@P("reportId") String reportId) {
        return "report:" + reportId;
    }

    @RequiresAdmin
    public String adminSummary() {
        return "admin:summary";
    }

    @RequiresAdminFull
    public String auditSummary() {
        return "audit:summary";
    }
}
```

Đây là Spring-managed bean; lời gọi từ controller qua injected `ReportService` sẽ đi qua method-security proxy phù hợp. Không đặt việc xác thực mật khẩu trong body service method.

### 9.9. ArchiveService.java: tái sử dụng cùng annotation

```java
package example.meta;

import example.meta.policy.CanReadReport;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class ArchiveService {

    @CanReadReport
    public String archived(@P("reportId") String reportId) {
        return "archive:" + reportId;
    }
}
```

`ReportService.read` và `ArchiveService.archived` khác nhau về kết quả nhưng **cùng contract phân quyền**. Nếu policy archive khác chính sách báo cáo thông thường, cần một annotation riêng; việc tái sử dụng chỉ đúng khi nghiệp vụ thật sự thống nhất.

### 9.10. SecurityConfig.java: bật method security và HTTP Basic

```java
package example.meta;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("lan-demo"))
            .roles("USER")
            .build();

        UserDetails minh = User.withUsername("minh")
            .password(encoder.encode("minh-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(lan, minh, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Demo chỉ có GET endpoints; giữ nguyên CSRF protection mặc định.
        return http.build();
    }
}
```

**Vì sao HTTP layer chỉ dùng authenticated?** Ví dụ cố ý đặt policy owner/admin **ở method** để nhìn thấy method-security hoạt động. Đây không phải lời khuyên dùng `anyRequest().authenticated()` cho mọi sản phẩm: route mới quên method annotation có thể bị mở cho mọi authenticated user. Production cần review route coverage, nguyên tắc least privilege và có thể dùng HTTP policy chi tiết, `denyAll` fallback và domain/service checks phù hợp.

**HTTP Basic** chỉ để test phân quyền mà không cần form HTML. Base64 không phải encryption; production cần HTTPS và secret storage đúng. `STATELESS` không tự miễn trừ đánh giá CSRF cho API có thao tác ghi; ví dụ GET chỉ đọc, nên không tắt CSRF.

### 9.11. DemoController.java

```java
package example.meta;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ReportService reports;
    private final ArchiveService archive;

    public DemoController(ReportService reports, ArchiveService archive) {
        this.reports = reports;
        this.archive = archive;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/reports/{reportId}")
    public String report(@PathVariable("reportId") String reportId) {
        return reports.read(reportId);
    }

    @GetMapping("/archive/{reportId}")
    public String archived(@PathVariable("reportId") String reportId) {
        return archive.archived(reportId);
    }

    @GetMapping("/admin/summary")
    public String adminSummary() {
        return reports.adminSummary();
    }

    @GetMapping("/audit/summary")
    public String auditSummary() {
        return reports.auditSummary();
    }
}
```

Controller không viết lại SpEL hoặc owner check. Mỗi lời gọi đến method service bảo vệ đi **qua proxy**, nên annotation tổng hợp được áp dụng.

## 10. Kiểm thử JUnit 5 và MockMvc

File `src/test/java/example/meta/MetaAuthorizationTest.java`:

```java
package example.meta;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MetaAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService reports;

    @Autowired
    ArchiveService archive;

    @Test
    void publicRouteIsAvailableWithoutAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousPrivateRouteGetsBasicChallenge() throws Exception {
        MvcResult response = mvc.perform(get("/reports/r101"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge =
            response.getResponse().getHeader("WWW-Authenticate");
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void lanCanReadOwnReport() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r101"));
    }

    @Test
    void lanCannotReadMinhReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void minhCanReadHisReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("minh", "minh-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r202"));
    }

    @Test
    void adminCanReadBothReports() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk());
        mvc.perform(get("/reports/r202")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk());
    }

    @Test
    void missingReportIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/reports/missing")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void samePolicyWorksOnArchiveService() throws Exception {
        mvc.perform(get("/archive/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("archive:r101"));
        mvc.perform(get("/archive/r202")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void normalUserCannotAccessAdminSummary() throws Exception {
        mvc.perform(get("/admin/summary")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminSummary() throws Exception {
        mvc.perform(get("/admin/summary")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:summary"));
    }

    @Test
    void normalUserCannotAccessAdminFullAudit() throws Exception {
        mvc.perform(get("/audit/summary")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminFullAudit() throws Exception {
        mvc.perform(get("/audit/summary")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit:summary"));
    }

    @Test
    void wrongPasswordGetsUnauthorized() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void directSpringBeanCallIsProtectedByMethodProxy() {
        // Không có HTTP: gọi Spring bean được inject qua method proxy.
        assertThrows(AccessDeniedException.class,
            () -> reports.read("r202"));

        assertThrows(AccessDeniedException.class,
            () -> archive.archived("r202"));
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void directSpringBeanCallAllowsOwnedReport() {
        // Kiểm tra cả phía được cấp quyền, không chỉ denial.
        String output = reports.read("r101");
        org.junit.jupiter.api.Assertions.assertEquals(
            "report:r101", output
        );
    }
}
```

**Mười lăm bài kiểm thử** kiểm tra cả HTTP integration và lời gọi trực tiếp vào Spring bean:

- Anonymous → HTTP 401 + Basic challenge đối với route cần xác thực.
- `lan` → đọc `r101` nhưng không đọc `r202` của `minh`.
- `minh` → đọc `r202`.
- Admin → đọc cả report hợp lệ; ID không tồn tại vẫn bị deny.
- `ArchiveService` dùng lại `@CanReadReport` đúng như `ReportService`.
- `@RequiresAdmin` bảo vệ trang quản trị; `@RequiresAdminFull` bảo vệ audit.
- Password Basic sai → HTTP 401.
- `@WithMockUser` chỉ dùng cho **direct service call tests** để tạo SecurityContext thử nghiệm; **không** dùng để khẳng định đã test password thật. Test HTTP dùng `httpBasic(...)`.

### 10.1. Tại sao test lời gọi trực tiếp có giá trị?

`directSpringBeanCallIsProtectedByMethodProxy` không gọi controller. Nó inject bean `ReportService` và gọi method qua proxy; nếu `@EnableMethodSecurity` bị bỏ hoặc meta-annotation không được phát hiện, cuộc gọi `reports.read("r202")` có thể trả dữ liệu thay vì ném `AccessDeniedException` và test sẽ thất bại.

Kết hợp test HTTP và test service giúp phân biệt: HTTP layer có thể ngăn anonymous, còn method security mới kiểm soát owner và admin đúng chi tiết.

### 10.2. Tại sao test đúng một user là chưa đủ?

Nếu chỉ test admin đọc report thì chưa chứng minh chính sách chống BOLA/IDOR. Một user đã xác thực hợp lệ như `lan` cần có test **đọc tài nguyên của người khác** bị deny. Tương tự, nếu chỉ test denial mà không test owner allowed, biểu thức SpEL sai có thể vô tình từ chối tất cả.

### 10.3. Điều gì xảy ra khi bean permission trả false?

`@PreAuthorize` được đánh giá trước body service. Khi false, Spring Security method interceptor từ chối và có thể ném `AccessDeniedException`. Tại HTTP request, `ExceptionTranslationFilter` chuyển exception phù hợp thành status theo entry point/handler. Với HTTP Basic đã xác thực nhưng thiếu quyền, response thường là **403 Forbidden** trong sample.

Không tự diễn giải rằng mọi false luôn là 403: anonymous thường bị Basic challenge 401, form login có thể redirect 302, và custom handlers có thể quyết định response khác.

### 10.4. Kiểm tra CSRF độc lập

Demo chỉ có GET endpoints. Nếu thêm `POST /reports/{id}/approve`, phải phân tích CSRF tùy cơ chế credentials và client, kiểm tra role/owner/action và transaction. Không đơn giản thêm `.csrf(csrf -> csrf.disable())` toàn cục chỉ để test dễ chạy.

## 11. Chạy chương trình và dự kiến kết quả

Tại thư mục `method-meta-authorization`, cần JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Nếu dependency và môi trường phù hợp, **15 bài kiểm thử dự kiến pass**. Đây là đánh giá tĩnh của source, không phải báo cáo kết quả Maven đã thực thi.

Thử HTTP Basic **chỉ với tài khoản demo trên localhost**:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r202
curl -i -u minh:minh-demo http://localhost:8080/reports/r202
curl -i -u admin:admin-demo http://localhost:8080/admin/summary
curl -i -u lan:lan-demo http://localhost:8080/audit/summary
curl -i -u admin:admin-demo http://localhost:8080/audit/summary
```

**Không** dùng HTTP không mã hóa cho credentials thật. `curl -u` có thể đưa mật khẩu vào command history hoặc process listing. Dùng HTTPS, secret management và client auth phù hợp trong production.

| Tình huống | Kết quả dự kiến | Vì sao |
| --- | --- | --- |
| Anonymous `GET /public` | 200 `public` | HTTP permitAll |
| Anonymous `GET /reports/r101` | 401 + Basic challenge | Chưa xác thực ở HTTP layer |
| Lan đọc `r101` | 200 `report:r101` | Owner thật theo server store |
| Lan đọc `r202` | 403 | Không phải owner và không có ROLE_ADMIN |
| Minh đọc `r202` | 200 `report:r202` | Owner |
| Admin đọc report có tồn tại | 200 | Admin được grant theo policy demo |
| Admin đọc report thiếu trong store | 403 | Deny rõ ràng, không cho qua missing |
| Lan vào `/admin/summary` | 403 | Không có ROLE_ADMIN |
| Admin vào `/admin/summary` | 200 `admin:summary` | @RequiresAdmin |
| Lan vào `/audit/summary` | 403 | Không đủ role/full |
| Admin vào `/audit/summary` | 200 `audit:summary` | @RequiresAdminFull |
| Basic sai password | 401 | Authentication thất bại trước khi policy service chạy |

Trong ứng dụng dùng form login thay vì Basic, anonymous access có thể redirect `/login` thay vì HTTP 401. Điều này không làm thay đổi nghĩa của meta-annotation trên service.

## 12. Java 17 độc lập: quan sát annotation tổng hợp bằng reflection

Spring Security có cơ chế phát hiện meta-annotation riêng, nhưng trước tiên có thể dùng Java Reflection để hiểu **annotation được gắn trên annotation khác**. Chương trình này **không** chạy Spring, không có authentication và không thực thi SpEL. Nó chỉ đọc metadata runtime.

Tạo `MetaAnnotationReflectionDemo.java`:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class MetaAnnotationReflectionDemo {

    @Target(ElementType.ANNOTATION_TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Rule {
        String value();
    }

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Rule("ADMIN")
    @interface RequiresAdmin {
    }

    static class Service {

        @RequiresAdmin
        public String adminSummary() {
            return "admin:summary";
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = Service.class.getMethod("adminSummary");

        RequiresAdmin composed = method.getAnnotation(
            RequiresAdmin.class
        );
        System.out.println("method has RequiresAdmin: " +
            (composed != null));

        Rule meta = RequiresAdmin.class.getAnnotation(Rule.class);
        System.out.println("meta rule: " + meta.value());

        // Đây là đọc metadata, chưa phải một quyết định phân quyền.
        System.out.println("result: " +
            new Service().adminSummary());
    }
}
```

Biên dịch và chạy với Java 17:

```bash
javac MetaAnnotationReflectionDemo.java
java MetaAnnotationReflectionDemo
```

Stdout **chính xác**:

```text
method has RequiresAdmin: true
meta rule: ADMIN
result: admin:summary
```

**Bài học:** reflection đọc ra annotation tổng hợp và meta-annotation `@Rule("ADMIN")`, nhưng `new Service().adminSummary()` vẫn chạy không cần login vì chương trình không có Spring method-security interception. Trong ứng dụng Spring Security, `@EnableMethodSecurity` và lời gọi qua Spring proxy phù hợp mới là cơ chế thực thi `@PreAuthorize`.

## 13. Annotation tái sử dụng không tự giải quyết mọi quyền

Một điểm quan trọng trong kiến trúc: **tái sử dụng cú pháp policy** không có nghĩa mọi tài nguyên có cùng policy.

Ví dụ:

- `@CanReadReport` kiểm tra quyền report theo owner hoặc admin.
- `@CanReadAuditLog` có thể cần role auditor, mục đích truy cập và retention policy.
- `@CanExportReport` có thể đòi full authentication, quota, giấy phép hoặc consent.
- `@CanDeleteReport` có thể cần approver và kiểm tra trạng thái report chưa locked.

Dùng một annotation chung vì cả bốn liên quan report có thể làm quyền quá rộng hoặc quá hẹp. Nên xác định **mỗi annotation có hợp đồng nhất quán theo nghiệp vụ** và version/kiểm thử khi thay đổi.

### 13.1. Chính sách thay đổi tác động nhiều nơi

Nếu thay `@CanReadReport` từ owner-only sang owner OR admin, mọi service method dùng annotation sẽ thay hành vi. Điều này là ưu điểm **và** rủi ro của tái sử dụng: một thay đổi nhỏ có thể mở quyền trên nhiều endpoint.

Code review cần biết usages của annotation, đánh giá threat model và chạy integration/regression tests tương ứng. Không cho rằng “chỉ sửa một file” đồng nghĩa phạm vi ảnh hưởng nhỏ.

### 13.2. Chính sách ở HTTP và service có thể cộng dồn

Giả sử HTTP rule yêu cầu `ROLE_READER` cho `GET /reports/**` nhưng method `@CanReadReport` cho owner OR admin. Nếu admin không có `ROLE_READER`, họ bị chặn ở HTTP layer trước khi method được gọi. Đây có thể là policy đúng hoặc một lỗi không chủ ý.

Vì các lớp kiểm tra có thể **cộng dồn**, nên cần test kết quả tổng thể. Không suy ra manager/annotation “không hoạt động” chỉ vì request chưa vượt qua HTTP authorization trước đó.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Quên `@EnableMethodSecurity` | Meta-annotation có thể không được thực thi | Bật method security và test direct bean call |
| Chỉ có `@Retention(SOURCE)` | Framework không có metadata runtime phù hợp | Dùng `RetentionPolicy.RUNTIME` |
| Dùng `@Target(TYPE)` khi annotation chỉ nên áp cho một method | Phạm vi bảo vệ không khớp hợp đồng | Dùng METHOD-only hoặc thiết kế class-level rõ |
| Annotation tổng hợp không có `@PreAuthorize`/meta policy | Chỉ là metadata trang trí | Khai báo meta-annotation đúng |
| Định nghĩa `@RequiresRole(role="ADMIN")` rồi kỳ vọng `{role}` tự thay | Literal/template có thể không được xử lý | Dùng fixed rule hoặc bật template theo version có test |
| Dùng hai `@PreAuthorize`/meta rules cùng method và mong tự AND | Có thể ambiguous hoặc behavior không như ý | Một expression AND/policy manager |
| Gắn annotation lên private/final method, không test proxy | Interception có thể không xảy ra | Public/proxy-compatible service boundary |
| Lời gọi `this.securedMethod()` trong cùng bean | Bypass proxy trong chế độ phổ biến | Tách bean hoặc thiết kế interception phù hợp |
| Tạo service bằng `new` bên ngoài Spring | Không có method security proxy | Inject Spring bean |
| Sai tên biến `#reportId` | Expression không tìm được argument | `@P("reportId")` hoặc build metadata đúng |
| Gọi bean `@reportPermission` chưa đăng ký | Evaluation không chạy như dự kiến | Định nghĩa bean và test SpEL |
| Bean permission trả true nếu ID null/missing | Mở quyền sai, BOLA | Fail closed, kiểm thử missing ID |
| Lấy owner từ request query do client tự gửi | Client giả mạo owner | Đối chiếu server-side resource store |
| Chỉ dùng hasRole cho tất cả report | User có role đọc report của người khác | Kết hợp owner/tenant |
| Dùng `fullyAuthenticated` rồi cho rằng đã MFA | Không có chứng cứ MFA mới | Thêm recent auth/MFA policy |
| Dùng `@PostAuthorize` cho method đã ghi DB | Deny đến sau side effects | Dùng pre-check và domain transaction checks |
| Quên bảo vệ scheduled/background caller | Không có HTTP security context | Thiết kế service identity & policy phù hợp |
| Không có test non-owner | Không phát hiện IDOR/BOLA | Test owner, non-owner, admin, unknown |
| Coi 403 luôn do SpEL | CSRF/HTTP rule cũng có thể chặn | Kiểm tra filter chain/exception |
| Test bằng `@WithMockUser` rồi tuyên bố Basic password hoạt động | Không kiểm tra Basic authentication | HTTP tests phải gửi header Basic |
| Đặt `anyRequest().authenticated()` và quên annotation mới | Endpoint mới có thể quá rộng | Audit coverage, deny fallback ở nơi phù hợp |
| Đặt annotation chứa dữ liệu tenant nhạy cảm vào logs | Lộ dữ liệu vận hành | Log quyết định tối thiểu, không lộ secrets |
| Lặp biểu thức SpEL ở hàng chục service | Policy drift | Meta-annotation có tên và tests |
| Chuyển cấu hình từ 6.3 sang version khác không test | Templating/API behavior đổi | Xem tài liệu version, integration tests |

## 15. Gỡ lỗi khi annotation tổng hợp không chặn request

Nếu user không có quyền vẫn gọi được service method:

1. **Bean có được Spring quản lý?** Có `@Service`, `@Component` hoặc bean phù hợp không?
2. **`@EnableMethodSecurity` đã thực sự được quét?** Xác nhận configuration có hiệu lực.
3. **Lời gọi có đi qua proxy?** Controller inject service hay code tạo bằng `new`? Có self-invocation `this.method()`?
4. **Method có intercept được không?** Kiểm tra visibility, final, proxy type, interface.
5. **Annotation có Runtime retention?** `@Retention(RUNTIME)` và `@Target(METHOD)` đúng?
6. **Meta-annotation có `@PreAuthorize` hợp lệ?** Không gắn nhầm annotation ở nơi khác?
7. **Có annotation trùng loại hoặc conflict?** Method, class, interface có rule trái nhau?
8. **SpEL có tìm được bean?** Tên `@reportPermission`, method `canRead` và return type đúng?
9. **`#reportId` có giá trị?** Test `@P("reportId")` và compile metadata.
10. **Principal/authority trong SecurityContext?** Có anonymous/remember-me không? Role prefix đúng?
11. **Request có qua HTTP layer?** Nếu bị chặn ở filter, service chưa chạy; 401/403 có thể đến từ nơi khác.
12. **Service có được gọi trực tiếp từ một background job?** SecurityContext đó có đáng tin không?
13. **Policy lấy owner từ server store?** Không dùng query để quyết định owner.
14. **Version Spring Security?** Kiểm tra hỗ trợ composed annotations và expression templating tương ứng.
15. **Có tác dụng phụ trước check?** `@PostAuthorize` hoặc self-invocation có thể không bảo vệ đúng lúc.

Dùng logging ở môi trường phát triển khi cần:

```properties
logging.level.org.springframework.security=DEBUG
```

Không log mật khẩu, cookie, session ID, bearer token hoặc dữ liệu riêng tư của report. Dùng unit test cho bean permission và integration tests trên Spring proxy/MockMvc để biết denial đến từ đâu.

## 16. Bảo mật, hiệu năng và multi-tenant

### 16.1. Tránh tăng quyền khi thay annotation

Một tên như `@CanReadReport` có thể được dùng rộng trong nhiều module. Nếu policy thay từ owner-only sang owner OR admin, có thể vô tình cho admin toàn hệ thống xem tài nguyên của tenant khác. Cần thêm tenant boundary rõ, ví dụ owner cùng tenant hoặc admin được giới hạn tenant, và kiểm thử cross-tenant.

### 16.2. Hạn chế truy vấn policy tốn kém

Một `@PreAuthorize` gọi bean permission có thể thực hiện DB lookup trên mỗi service call. Cần đo chi phí, tránh N+1, cache đúng key (principal/tenant/action/resource) và đồng bộ khi revoke. Đừng cache theo report ID đơn thuần rồi tái sử dụng kết quả true cho user khác.

### 16.3. TOCTOU và transaction

Policy trước method có thể kiểm tra owner lúc T1 nhưng báo cáo đổi owner trước khi DB update ở T2. Khi thao tác nhạy cảm, service cần xác minh quyền gần lúc sử dụng dữ liệu, dùng query ràng buộc owner/tenant, transaction/version hoặc database row-level controls phù hợp.

Một meta-annotation `@PreAuthorize` không đảm bảo tính nhất quán transaction cho mọi bước nghiệp vụ.

### 16.4. Không dùng annotation làm bằng chứng audit duy nhất

Việc method có `@RequiresAdmin` không chứng minh mọi call đều được intercept, nhất là khi có self-invocation hoặc code không đi qua Spring proxy. Audit nên quan sát runtime decisions và entry points, có test cover đường gọi quan trọng.

### 16.5. Defense in depth

- HTTP layer chặn request không cần thiết.
- Method security bảo vệ service boundary.
- Domain service kiểm tra owner, tenant, action.
- DB queries/transactions giữ kiểm soát ở thời điểm thao tác.
- CSRF, TLS, logging an toàn và secret management bảo vệ các lớp khác.

Các lớp nên **bổ sung** nhau chứ không mâu thuẫn hoặc tạo tình trạng mọi user có `ROLE_USER` được truy cập các tài nguyên của nhau.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** Vì sao nên tạo `@RequiresAdmin` thay vì lặp `@PreAuthorize("hasRole('ADMIN')")` ở nhiều method?

**Đáp án:** Tái sử dụng một policy có tên, giảm policy drift và tập trung việc chỉnh sửa/review; vẫn cần test các nơi sử dụng vì thay đổi ảnh hưởng nhiều method.

**Câu 2.** Annotation tổng hợp có cần `RetentionPolicy.RUNTIME` không?

**Đáp án:** Có với cơ chế runtime annotation inspection trong ví dụ; metadata phải có khi Spring Security cần đánh giá.

**Câu 3.** Chỉ định nghĩa `@RequiresAdmin` nhưng quên `@EnableMethodSecurity` thì sao?

**Đáp án:** Có nguy cơ không có method-security interceptor thực thi `@PreAuthorize`. Test direct injected service bean sẽ phát hiện.

**Câu 4.** `ReportService` tự gọi `this.read("r202")` trong một method khác cùng bean, annotation `@CanReadReport` có chắc hoạt động không?

**Đáp án:** Không với proxy-based interception thông dụng; self-invocation có thể bypass proxy. Tách protected method sang bean khác hoặc đổi thiết kế.

**Câu 5.** Vì sao đặt `@P("reportId")` cho method argument?

**Đáp án:** Để SpEL expression `#reportId` có tên parameter rõ, không phải phụ thuộc hoàn toàn compiler metadata.

**Câu 6.** Một request `GET /reports/r202` được lan gọi với Basic credential đúng. Vì sao có thể nhận 403?

**Đáp án:** HTTP layer xác thực thành công, nhưng method policy `@CanReadReport` đối chiếu owner và thấy report `r202` thuộc Minh, lan không có ROLE_ADMIN nên deny.

**Câu 7.** User có ROLE_ADMIN và remember-me Authentication, method `@RequiresAdminFull` có thỏa không?

**Đáp án:** Không theo logic `hasRole('ADMIN') and isFullyAuthenticated()` vì remember-me không phải fully authenticated. Với app HTTP Basic mẫu không bật remember-me nên cần test loại token riêng nếu triển khai tính năng đó.

**Câu 8.** Có thể viết `@RequiresRole(role="MANAGER")` và `@PreAuthorize("hasRole('{role}')")`, mong tự thay placeholder trong mọi version?

**Đáp án:** Không. Annotation attribute templates phụ thuộc hỗ trợ/config của version. Mẫu 6.3.x dùng fixed rule hoặc custom policy thay vì giả định interpolation.

**Câu 9.** Hai `@PreAuthorize` hoặc hai annotation tổng hợp đều chứa `@PreAuthorize` trên cùng method có tự AND không?

**Đáp án:** Không nên giả định; có thể ambiguity. Muốn AND, dùng một expression hoặc policy manager tổng hợp rõ ràng.

**Câu 10.** `@PostAuthorize` có phù hợp làm bảo vệ duy nhất cho method `transferMoney` không?

**Đáp án:** Không. Post-check có thể chạy **sau** khi tiền đã chuyển; dùng pre-check và transaction/domain authorization phù hợp.

**Câu 11.** Tại sao test lan đọc `r101` được phép và `r202` bị từ chối cùng quan trọng?

**Đáp án:** Ca được phép chứng minh rule không chặn tất cả; ca user đã authenticated nhưng không phải owner giúp phát hiện lỗi IDOR/BOLA.

**Câu 12.** Trong test dùng `@WithMockUser` gọi trực tiếp bean, có thể khẳng định HTTP Basic password được xác minh không?

**Đáp án:** Không. `@WithMockUser` dựng SecurityContext thử nghiệm. Test Basic phải gửi header thật qua MockMvc hoặc HTTP client.

**Câu 13.** Có `@CanReadReport` trên service, vậy các message consumers gọi bằng đối tượng `new ReportService()` có được bảo vệ không?

**Đáp án:** Không tự động. Object không do Spring tạo/proxy không đi qua method security. Thiết kế entry points và dependency injection đúng.

**Câu 14.** Admin của tenant A nên mặc nhiên đọc tất cả report tenant B khi dùng `@CanReadReport` không?

**Đáp án:** Không nếu policy không cho cross-tenant. Cần source dữ liệu owner/tenant và rule rõ ràng, không dùng role global một cách vô điều kiện.

## 18. Checklist áp dụng trước khi triển khai

**Thiết kế annotation:**

- Tên annotation có mô tả rõ action và resource không?
- Chính sách là cố định hay cần tham số method?
- Có `@Target` và `@Retention(RUNTIME)` đúng?
- Mỗi annotation có một rule `@PreAuthorize` hoặc cơ chế security rõ ràng?
- Có tránh multiple conflicting `@PreAuthorize` trên một method không?
- Có Javadoc về hợp đồng argument `#reportId`, role/tenant và kết quả denial không?

**Thiết lập framework:**

- `@EnableMethodSecurity` đã được bật đúng Spring context?
- Service method public, non-final và được gọi qua Spring proxy?
- Không có self-invocation bypass ở đường gọi nhạy cảm?
- SpEL bean `@reportPermission` có tồn tại?
- Argument được export đúng bằng `@P` hoặc compiler metadata?
- HTTP filter policy không vô tình mở route chưa có method annotation?

**Kiểm thử:**

- Có test owner và non-owner đã xác thực, admin, report không tồn tại?
- Cùng annotation có chạy ở các bean khác nhau?
- Có test service bean trực tiếp ngoài HTTP?
- Có test 200/401/403 đúng entry point?
- Có test Basic/authentication riêng, không suy từ `@WithMockUser`?
- Có test policy thay đổi không ảnh hưởng route ngoài phạm vi?
- Có kiểm tra CSRF và method HTTP khi thêm mutation?

**Production:**

- Dữ liệu owner/tenant lấy từ nguồn đáng tin.
- Không hardcode password, signing key hoặc token.
- DB/cache authorization có giới hạn hiệu năng và revoke.
- Có controls về step-up/MFA cho tác vụ nhạy cảm nếu cần.
- Có logging/audit an toàn, không ghi secrets.
- Review tất cả usages trước khi thay nội dung annotation.

## 19. Ghi nhớ trọng tâm

- **Annotation tổng hợp** là một Java annotation có meta-annotation như `@PreAuthorize` để **tái sử dụng một chính sách phân quyền có tên**.
- Bật **`@EnableMethodSecurity`**, đặt annotation ở **Spring-managed public service methods** và bảo đảm lời gọi đi **qua proxy**.
- `@Target(METHOD)`, `@Retention(RUNTIME)`, `@Documented` giúp định nghĩa và phát hiện annotation nhất quán.
- Với biểu thức cần method argument, dùng `@P("reportId")` hoặc metadata parameter names phù hợp để `#reportId` được resolve chính xác.
- `@PreAuthorize("@reportPermission.canRead(authentication, #reportId)")` ủy quyền quyết định ownership cho bean Java, **không** tự tin dữ liệu do client khai.
- Muốn role **AND** full authentication, viết **một** policy, ví dụ `hasRole('ADMIN') and isFullyAuthenticated()`; không chồng nhiều `@PreAuthorize` rồi mong framework tự tổng hợp.
- **Self-invocation**, private/final methods, bean tạo bằng `new` và custom proxies là các ranh giới quan trọng có thể khiến annotation không được thực thi.
- Test cả **request HTTP** (MockMvc/Basic) lẫn **direct Spring bean calls** (@WithMockUser) và các trường hợp non-owner để chống lỗi BOLA/IDOR.
- Tái sử dụng policy giúp giảm lặp, nhưng mọi thay đổi tại annotation chung có thể tác động nhiều methods; cần ownership/tenant checks, regression tests và defense in depth.
