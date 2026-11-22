# Khả năng hỗ trợ @AuthorizeReturnObject, xử lý từ chối và annotation template

## 1. Ba khả năng cần phân biệt khi nâng cấp Spring Security

Khi chuyển phiên bản Spring Security, một đoạn mã có thể **biên dịch nhưng chưa bảo vệ đúng dữ liệu**, hoặc ngược lại không biên dịch vì tính năng chưa tồn tại trong dependency thực tế. Ba cơ chế trong chủ đề này giải quyết ba vấn đề khác nhau của *method authorization*:

1. **`@AuthorizeReturnObject`**: bao đối tượng được phương thức trả về bằng proxy có áp dụng lời khuyên (advice) của method security. Một getter/operation trên đối tượng trả về có `@PreAuthorize` hoặc `@PostAuthorize` được kiểm tra khi gọi qua proxy ấy.
2. **`@HandleAuthorizationDenied` + `MethodAuthorizationDeniedHandler`**: xác định cách xử lý khi method authorization **từ chối**. Có thể ném lỗi như mặc định hoặc trả giá trị an toàn, ví dụ `null`, một bản đã che dữ liệu hay đối tượng fallback, nếu hợp đồng API cho phép.
3. **Annotation template**: tạo meta-annotation như `@RequiresPermission("profile:read")` để tái sử dụng biểu thức `@PreAuthorize("hasAuthority('{value}')")`. Template cần cơ chế cấu hình tương ứng, không đơn thuần là Java annotation thông thường.

Cả ba hoạt động trong hệ thống có `@EnableMethodSecurity` và Spring AOP. Chúng bổ sung cho nhau nhưng không thay thế kiểm tra quyền **trên từng tài nguyên/tenant**, không thay HTTP filter chain, và không tự bảo đảm DTO/JSON hay đường truy cập dữ liệu khác an toàn.

Ví dụ xuyên suốt: người dùng `alice` có `profile:read`, được phép đọc hồ sơ số 1 của chính mình. Hồ sơ số 2 thuộc `bob`. Trường `email` trong hồ sơ 1 chỉ được đọc nếu Alice có thêm `profile:email`. Khi thiếu quyền này, một getter được bảo vệ sẽ trả `null` theo chính sách fallback minh họa; truy vấn hồ sơ 2 vẫn trả `null` trước khi có đối tượng nào được xuất ra.

Kết quả học tập cần đạt: xác định đúng **phiên bản hỗ trợ**, chọn vị trí kiểm tra trước/sau method, biết khi nào proxy trên return object hoạt động, không dùng fallback để che lỗi cấp quyền nghiêm trọng, và có bài kiểm thử chứng minh quyền thực sự được áp dụng sau nâng cấp.

## 2. Ma trận khả năng theo phiên bản: đừng suy từ Spring Boot

Các mốc sau dựa trên API documentation và hướng dẫn method security chính thức. Khi một phiên bản cụ thể được chọn, hãy đối chiếu tài liệu **đúng nhánh** và dependency đã resolve thay vì mặc định trang tài liệu “current” trùng với môi trường dự án.

| Khả năng | Spring Security 6.2 trở xuống | 6.3.x | 6.4+ / 6.5 và các nhánh mới có API tương ứng |
| --- | --- | --- | --- |
| `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` | Có trong thế hệ Spring Security 6, cần bật method security | Có | Có |
| `@AuthorizeReturnObject` | Chưa có API này | **Được giới thiệu từ 6.3** | Có |
| `@HandleAuthorizationDenied` | Chưa có API này | **Được giới thiệu từ 6.3** | Có |
| `MethodAuthorizationDeniedHandler` | Chưa có API này | **Được giới thiệu từ 6.3** | Có |
| `AnnotationTemplateExpressionDefaults` và placeholder `'{value}'` | Chưa có API này | Chưa có API này ở 6.3 | **Được giới thiệu từ 6.4**, dùng với bean cấu hình |
| Bảo vệ getter trả về bằng proxy | Cần chiến lược khác/manual authorization | Có nếu cấu hình và phiên bản đúng | Có; kiểm tra tương thích proxy và AOT khi cần |

**Lưu ý bảo mật bắt buộc khi chọn 6.3.x:** Spring công bố **CVE-2024-38810** liên quan việc thiếu một phần method security advice trên đối tượng được proxy bằng `@AuthorizeReturnObject`/`AuthorizationAdvisorProxyFactory` trong một cấu hình AOP + FactoryBean nhất định. Các bản **6.3.0 và 6.3.1** bị ảnh hưởng theo điều kiện advisory; **6.3.2** là bản sửa cho nhánh 6.3. Do đó, không chọn 6.3.0/6.3.1 cho tính năng này; dùng nhánh đang được hỗ trợ và bản vá phù hợp. Không suy rằng mọi ứng dụng có `@AuthorizeReturnObject` đều từng bị lỗi: advisory nêu điều kiện cụ thể.

Spring Boot quản lý các phiên bản Spring Security qua BOM/dependency management. **Phiên bản Boot không phải phiên bản Security.** Kiểm tra `spring-security-core`, `spring-security-config` và `spring-security-test` được resolve đồng bộ. Với Gradle có thể dùng lệnh tham khảo từ đúng module:

```bash
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
```

Trên Windows, dùng `gradlew.bat`. Trong multi-project Gradle, có thể cần ghi rõ task `:ten-module:dependencyInsight` và configuration đúng plugin. Các lệnh trên là hướng dẫn kiểm tra, **không phải kết quả đo dependency của module hiện tại**.

Khi tìm API trong JAR hoặc IDE, tên package cần nhớ:

- `org.springframework.security.authorization.method.AuthorizeReturnObject`
- `org.springframework.security.authorization.method.HandleAuthorizationDenied`
- `org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler`
- `org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults`

Lỗi “cannot find symbol” không nên chữa bằng cách tự tạo một annotation trùng tên hoặc sao chép code giữa các version. Hãy xác nhận phiên bản dependency, bản vá bảo mật và phạm vi hỗ trợ.

## 3. Cơ chế method security: trước, sau và trên object trả về

`@EnableMethodSecurity` đăng ký các interceptor được hỗ trợ cho lời gọi method qua Spring AOP. Một cách hình dung:

```text
Spring bean proxy
   │
   ├─ @PreAuthorize: đánh giá trước khi chạy method
   │      └─ DENY → mặc định ném lỗi; handler có thể thay kết quả
   │
   ├─ body của method (đọc dữ liệu, tính toán, tác dụng phụ...)
   │
   ├─ @PostAuthorize: đánh giá theo returnObject sau khi method chạy
   │      └─ DENY → mặc định ném lỗi; handler có thể xử lý kết quả
   │
   └─ @AuthorizeReturnObject: bao đối tượng trả về bằng proxy
          ├─ getDisplayName() → có thể không có ràng buộc riêng
          └─ getEmail()       → @PreAuthorize trên getter
                                 └─ DENY → @HandleAuthorizationDenied
```

Thứ tự chính xác của advisor có thể chịu ảnh hưởng cấu hình/custom interceptors; sơ đồ cho thấy ý nghĩa thực tế, **không đại diện mọi chuỗi advisor ở mọi ứng dụng**.

### @PreAuthorize và @PostAuthorize không tương đương

- `@PreAuthorize` từ chối **trước khi body chạy**, phù hợp hành động có side effect, như xóa, chuyển tiền, cấp quyền, ghi database. Biểu thức có thể dựa vào authority, tham số method hoặc bean policy.
- `@PostAuthorize` được đánh giá **sau khi body đã chạy** và có thể truy cập `returnObject`. Hữu ích cho read-only method khi quyết định dựa trên object trả về; nhưng nếu body đã ghi/đẩy event trước lúc deny, exception sau đó không tự hoàn tác side effect trong mọi môi trường.
- `@AuthorizeReturnObject` đặt lời khuyên bảo mật lên đối tượng sau khi trả về. Nó **không tự gán** quyền cho getter nào, cũng không tự chuyển mọi field thành `REDACTED`. Các getter/nested method cần annotation thích hợp hoặc policy service.
- `@HandleAuthorizationDenied` thay đổi hành vi khi deny, **không thay đổi điều kiện ALLOW/DENY**. Fallback có thể khiến caller không biết lần truy cập đã bị từ chối; phải chọn nó có chủ đích.

Một bài kiểm thử tốt cần phân biệt: phương thức chính bị chặn, đối tượng trả về có proxy thật hay không, getter nào bị từ chối, body đã chạy trước khi bị từ chối hay chưa, và giá trị cuối cùng có lọt dữ liệu nhạy cảm không.

## 4. @AuthorizeReturnObject: khi nào nên dùng?

Giả sử `ProfileView` có hai getter: `getDisplayName()` được phép với người đã truy cập hồ sơ, còn `getEmail()` chỉ dành cho người có `profile:email`. Sau khi service trả `ProfileView` qua method có `@AuthorizeReturnObject`, lời gọi `profile.getEmail()` trên **proxy được trả về** sẽ đi qua method security.

```java
// Minh họa vị trí annotation; ví dụ đầy đủ nằm ở phần 7.
@AuthorizeReturnObject
public ProfileView profileById(long id) {
    return repository.findVisible(id, currentUser());
}

public class ProfileView {
    @PreAuthorize("hasAuthority('profile:email')")
    public String getEmail() {
        return email;
    }
}
```

Quan sát những giới hạn quan trọng:

1. Trả object từ service mà **không** dùng `@AuthorizeReturnObject` thì object thông thường có thể được gọi trực tiếp mà không có interceptor cho getter.
2. Chỉ đánh dấu `@AuthorizeReturnObject` nhưng getter không có `@PreAuthorize`/`@PostAuthorize` hoặc policy tương ứng thì **không tạo được quy tắc bảo vệ field**.
3. Gọi getter **trong chính object gốc** qua `this.getEmail()` không đi qua proxy returned-object, nên không nên dựa vào nó như cách bảo vệ duy nhất bên trong domain logic.
4. Method ở Spring bean có thể không qua proxy nếu bị gọi bằng `this.otherMethod()` (*self-invocation*); cần thiết kế ranh giới bean/policy rõ.
5. Kiểu class/record/final method, interface/JDK proxy, dữ liệu trong collection/`Optional`, serialization và native image có ràng buộc proxy riêng; test trên kiểu trả về **thực tế**, không mặc định mọi Java object đều dễ proxy.
6. Không dùng `@AuthorizeReturnObject` thay cho truy vấn theo tenant/owner. Nếu service đã trả object ngoài quyền, dữ liệu có thể bị lộ qua getter khác, log, serializer, mapping hoặc đường không đi qua proxy.

### Phạm vi áp dụng class-level

Có thể đặt `@AuthorizeReturnObject` ở cấp type, tương đương áp dụng cho các method của type đó. Tuy nhiên Spring Security sẽ thử proxy nhiều kiểu trả về, kể cả `String`, `Integer` hoặc collection của value type. Hướng dẫn chính thức đề xuất một `TargetVisitor` để bỏ qua value types khi cấu trúc trả về như vậy:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.method
        .AuthorizationAdvisorProxyFactory.TargetVisitor;

@Bean
static TargetVisitor skipValueTypes() {
    return TargetVisitor.defaultsSkipValueTypes();
}
```

Đoạn này là **fragment đặt bên trong một class @Configuration** và cần cấu hình phiên bản hỗ trợ API ấy. Với ứng dụng chỉ có một vài method trả domain object, thường dễ kiểm soát hơn khi gắn annotation trực tiếp trên **method cụ thể**.

## 5. Xử lý từ chối bằng @HandleAuthorizationDenied

Hành vi mặc định của một method bị deny là phát sinh `AuthorizationDeniedException`/`AccessDeniedException` theo lớp security đang dùng. Ứng dụng web có thể ánh xạ exception thành HTTP 403 trong ngữ cảnh phù hợp; một lời gọi service từ job hoặc unit test có thể quan sát exception trực tiếp. Không có quy tắc rằng mọi denial đều tự động trả HTTP 403 nếu không có HTTP request.

Khi một field tùy chọn không được xem, đôi khi cần hợp đồng như `"email": null` hoặc `"email": "***"`. Spring Security cung cấp `@HandleAuthorizationDenied(handlerClass = ...)` để chỉ định một implementation `MethodAuthorizationDeniedHandler`.

Hai callback đáng phân biệt:

| Callback | Thời điểm có thể áp dụng | Có body result nguyên bản? | Hợp lý cho |
| --- | --- | --- | --- |
| `handleDeniedInvocation(MethodInvocation, AuthorizationResult)` | Từ chối trước khi method thực hiện; callback chung cho denied invocation | Không có giá trị trả về từ body bị chặn | Trả `null`, placeholder cố định hoặc ném lại |
| `handleDeniedInvocationResult(MethodInvocationResult, AuthorizationResult)` | Khi denial có thể xảy ra sau khi method tạo result | Có thể có result của method | Che một phần giá trị đã tạo theo policy rất cụ thể |

Mặc định `handleDeniedInvocationResult` có thể chuyển cho `handleDeniedInvocation`. Nếu handler **xem dữ liệu gốc** để masking sau `@PostAuthorize`, kết quả phải luôn an toàn, không để bản gốc lọt vào log/error/caching. Với thao tác ghi, **không dùng fallback để giả vờ thành công**. Thường nên deny tường minh trước side effect.

### Vì sao không nên trả null ở mọi nơi?

- Với field nullable và không thiết yếu, `null` có thể là hợp đồng hợp lý nếu client hiểu ý nghĩa.
- Với hàm trả primitive `int`/`boolean` hoặc một `@NonNull` contract, `null` có thể phá vỡ type contract hoặc gây lỗi runtime.
- Với endpoint xuất dữ liệu nhạy cảm, fallback thành danh sách rỗng có thể che việc người dùng thiếu quyền, tạo báo cáo sai hoặc gây sự cố logic.
- Với mutation, trả `"SUCCESS"` khi thật ra bị deny là hành vi gây hiểu lầm và có thể làm hỏng audit.
- Với API cần phân biệt “không tồn tại” và “không được phép”, phản hồi phải được thiết kế tránh enumeration leak và phù hợp chính sách bảo mật.

Cần có test của **cả allow và deny**, xác minh method body không thực hiện khi `@PreAuthorize` deny, response không chứa giá trị gốc, và kiểm tra toàn bộ response serializing chứ không chỉ assertion trực tiếp Java getter.

## 6. Annotation template: tái sử dụng policy bằng meta-annotation

Một meta-annotation cố định hoạt động như:

```java
@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('ADMIN')")
public @interface AdminOnly {}
```

Trong phiên bản hỗ trợ template (từ **6.4**), thay giá trị cố định bằng tham số của annotation:

```java
@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresPermission {
    String value();
}
```

`@RequiresPermission("profile:read")` được phân giải theo template thành một biểu thức tương ứng với `hasAuthority('profile:read')`. Giá trị trong `{value}` là thuộc tính annotation khai báo trong mã nguồn; **không phải** chuỗi lấy trực tiếp từ HTTP body để thực thi SpEL.

Phải có bean cấu hình:

```java
@Bean
static AnnotationTemplateExpressionDefaults templateDefaults() {
    return new AnnotationTemplateExpressionDefaults();
}
```

Dùng import `org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults` và đặt fragment trong class `@Configuration`. Đừng nhầm việc có Java meta-annotation với việc Spring Security **đã bật template expansion**: không có bean/không đúng version thì placeholder có thể không được giải đúng.

Một số quy tắc khi định nghĩa annotation template:

- Sử dụng đúng dấu nháy trong SpEL, ví dụ `hasAuthority('{value}')`. Hãy kiểm thử biểu thức đã được phân giải; template có chuỗi role/permission sai dẫn đến deny hàng loạt hoặc điều kiện khác ý muốn.
- Các giá trị annotation nên do developer kiểm soát, không dùng để nối user input vào SpEL. Nếu cần chính sách phụ thuộc ID/tenant từ request, gọi bean policy với tham số đã được kiểm tra, không tạo template động.
- `hasAuthority("profile:read")` so chuỗi authority trực tiếp; `hasRole("ADMIN")` thường dùng prefix `ROLE_`. Test phải dùng đúng quyền đã cấp trong `Authentication`.
- `@PreAuthorize` lặp hai lần trên cùng method **không được hỗ trợ**. Không xếp thêm một meta-annotation chứa `@PreAuthorize` và một `@PreAuthorize` khác trên method mà mong Spring tự gộp an toàn; hãy dùng một biểu thức kết hợp hoặc policy bean.
- Có thể dùng ở type/method đúng phạm vi `@Target`, nhưng phải rà soát annotation kế thừa từ class/interface và trường hợp xung đột. Không giả định kế thừa annotation từ nhiều interface mâu thuẫn có thứ tự ưu tiên tự nhiên.
- `AnnotationTemplateExpressionDefaults#setIgnoreUnknown(false)` có thể dùng để phát hiện placeholder không xác định ở cấu hình muốn kiểm soát chặt; mặc định của API là bỏ qua placeholder không nhận diện. Trước khi đổi hành vi này, test tất cả expression template hiện có.

Annotation template giúp bớt lặp và giảm lỗi gõ policy, nhưng **không tự sinh** kiểm soát object-level. Một method đọc ID vẫn cần ràng buộc actor/tenant vào truy vấn hoặc policy domain.

## 7. Ví dụ tích hợp Spring Security 6.4+ với ba tính năng

Ví dụ dưới đây đặt trong một ứng dụng Java 17+ có Spring Security 6.4 trở lên, Spring Framework/Spring Test phù hợp và `spring-security-test` khi test. Nó dùng repository trong bộ nhớ để tập trung vào method security; **không tự thay thế** kiểm tra database/tenant trong production. File trong cùng package `demo.security`.

### 7.1. Cấu hình: bật method security, template và denied handler

Tệp `MethodSecuritySetup.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecuritySetup {
    @Bean
    static AnnotationTemplateExpressionDefaults templateDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }

    @Bean
    NullDeniedHandler nullDeniedHandler() {
        return new NullDeniedHandler();
    }
}
```

Tệp `NullDeniedHandler.java`:

```java
package demo.security;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler;

public class NullDeniedHandler implements MethodAuthorizationDeniedHandler {
    @Override
    public Object handleDeniedInvocation(
            MethodInvocation invocation, AuthorizationResult result) {
        return null;
    }
}
```

Ở đây handler chỉ dành cho getter trả `String` nullable. Nếu dùng một handler chung cho API trả object hoặc primitive khác, phải xử lý type rõ ràng để không tạo lỗi hoặc che nhầm từ chối.

### 7.2. Meta-annotation có tham số

Tệp `RequiresPermission.java`:

```java
package demo.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.access.prepost.PreAuthorize;

@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresPermission {
    String value();
}
```

`@RequiresPermission("profile:read")` ở service bên dưới kiểm soát quyền chức năng. Khi test phát hiện method không bị chặn dù thiếu `profile:read`, hãy kiểm tra bean template, phiên bản dependency và proxy Spring AOP trước khi kết luận biểu thức đúng.

### 7.3. Domain object có getter nhạy cảm

Tệp `ProfileView.java`:

```java
package demo.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.method.HandleAuthorizationDenied;

public class ProfileView {
    private final long id;
    private final String owner;
    private final String displayName;
    private final String email;

    public ProfileView(
            long id, String owner, String displayName, String email) {
        this.id = id;
        this.owner = owner;
        this.displayName = displayName;
        this.email = email;
    }

    public long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean ownedBy(String actor) {
        return owner.equals(actor);
    }

    @PreAuthorize("hasAuthority('profile:email')")
    @HandleAuthorizationDenied(handlerClass = NullDeniedHandler.class)
    public String getEmail() {
        return email;
    }
}
```

`ProfileView` là class thông thường, không `final`, getter không `final` để có thể kiểm tra qua proxy kiểu class trong cấu hình minh họa. Việc thiếu `getOwner()` có chủ đích để không xuất owner trực tiếp qua serializer; production nên dùng projection/DTO chỉ chứa trường cần thiết.

### 7.4. Repository ràng buộc quyền trên từng đối tượng

Tệp `ProfileStore.java`:

```java
package demo.security;

import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class ProfileStore {
    private final Map<Long, ProfileView> values = Map.of(
            1L, new ProfileView(
                    1L, "alice", "Alice", "alice@example.test"),
            2L, new ProfileView(
                    2L, "bob", "Bob", "bob@example.test"));

    public ProfileView findVisible(long id, String actor) {
        ProfileView result = values.get(id);
        return result != null && result.ownedBy(actor)
                ? result : null;
    }
}
```

Điểm bảo mật ở đây là **chỉ trả đối tượng thuộc actor**. Trong database thật, ràng buộc đó phải được thể hiện trong query an toàn theo owner/tenant/ACL và được thực thi ở mọi đường truy cập. Không dựa vào mỗi `getEmail()` để bảo vệ object 2.

### 7.5. Service áp dụng annotation template và bảo vệ return object

Tệp `ProfileService.java`:

```java
package demo.security;

import org.springframework.security.authorization.method.AuthorizeReturnObject;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private final ProfileStore store;

    public ProfileService(ProfileStore store) {
        this.store = store;
    }

    @RequiresPermission("profile:read")
    @AuthorizeReturnObject
    public ProfileView getProfile(long id) {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return store.findVisible(id, auth.getName());
    }
}
```

Khi có `profile:read` và đúng chủ sở hữu, method trả một `ProfileView` đã được bọc để getter `getEmail()` có thể bị từ chối hoặc cho phép. Với actor không được phép đọc object, service trả `null`. Actor lấy từ context do Spring Security xác lập, không lấy chuỗi owner do client tự khai.

**Đây là ví dụ cho Spring Security 6.4+**, vì chỉ từ phiên bản này mới có `AnnotationTemplateExpressionDefaults`. Nếu chạy trên 6.3.2, có thể giữ `@AuthorizeReturnObject` và `@HandleAuthorizationDenied` nhưng phải thay `@RequiresPermission` bằng `@PreAuthorize("hasAuthority('profile:read')")` hoặc một meta-annotation **cố định** không dùng placeholder template.

## 8. Kiểm thử Spring method security: kiểm tra proxy thật và denial

Ví dụ JUnit 5 dùng Spring Test + Spring Security Test; bốn test độc lập trong cùng package `demo.security`.

Tệp `ProfileServiceSecurityTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = {
        MethodSecuritySetup.class,
        ProfileStore.class,
        ProfileService.class
})
class ProfileServiceSecurityTest {
    @Autowired ProfileService service;

    @Test
    @WithMockUser(username = "alice", authorities = "profile:read")
    void returnsPublicFieldsButMasksDeniedEmail() {
        ProfileView profile = service.getProfile(1L);

        assertNotNull(profile);
        assertEquals("Alice", profile.getDisplayName());
        assertNull(profile.getEmail());
    }

    @Test
    @WithMockUser(
            username = "alice",
            authorities = { "profile:read", "profile:email" }
    )
    void returnsEmailWhenFieldPermissionExists() {
        ProfileView profile = service.getProfile(1L);

        assertNotNull(profile);
        assertEquals("alice@example.test", profile.getEmail());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "other")
    void deniesServiceWithoutFunctionalPermission() {
        assertThrows(AccessDeniedException.class,
                () -> service.getProfile(1L));
    }

    @Test
    @WithMockUser(
            username = "alice",
            authorities = { "profile:read", "profile:email" }
    )
    void deniesForeignProfileBeforeReturningObject() {
        assertNull(service.getProfile(2L));
    }
}
```

Những assertion này kiểm tra ba tầng theo đúng thứ tự: meta-annotation áp dụng quyền ở service, `@AuthorizeReturnObject` khiến getter `getEmail()` bị kiểm tra, và `@HandleAuthorizationDenied` biến denied getter thành `null`. Nếu bỏ `@AuthorizeReturnObject` ở service mà test thứ nhất lại nhận email thô, ta phát hiện lỗ hổng do getter không được proxy. Nếu thiếu bean template khiến `@RequiresPermission` không phân giải đúng, test điều kiện allow/deny sẽ phát hiện vấn đề.

Các đoạn Java phía trên là **bộ mã tích hợp có dependencies Spring cần thiết**; không thể chạy bằng `javac` trần. Có thể chạy bằng build của dự án, ví dụ:

```bash
./gradlew test --tests demo.security.ProfileServiceSecurityTest
```

Trong multi-project, dùng task của đúng module và dependency `spring-security-test`. Test trực tiếp service không thay thế kiểm thử HTTP/Jackson, session hoặc các đường không qua proxy. Hãy bổ sung một integration test gọi endpoint/serialization thật nếu object được đưa ra JSON.

**Không dựa vào một kiểu exception cố định khi test hệ thống có exception translator tự viết.** `assertThrows(AccessDeniedException.class)` phù hợp với lời gọi service trong ví dụ. Ở HTTP, mapping có thể là 403 hoặc một định dạng lỗi tùy controller/advice.

## 9. Ví dụ Java 17 độc lập để kiểm tra logic ALLOW, DENY và fallback

Đoạn này không dùng Spring AOP: nó mô phỏng logic để thấy rõ quyền ở service, quyền đối tượng và quyền trường dữ liệu là ba điều kiện khác nhau. Chạy độc lập được với JDK 17, giúp đối chiếu kết quả dự kiến trước khi xây dựng integration tests.

Tệp `AuthorizationFeatureDemo.java`:

```java
import java.util.Set;

public class AuthorizationFeatureDemo {
    record Actor(String name, Set<String> authorities) {}
    record Profile(String owner, String label, String email) {}

    static Profile view(Actor actor, Profile profile) {
        if (!actor.authorities().contains("profile:read")) {
            throw new SecurityException("profile:read denied");
        }
        return actor.name().equals(profile.owner()) ? profile : null;
    }

    static String visibleEmail(Actor actor, Profile profile) {
        Profile allowed = view(actor, profile);
        return allowed != null
                && actor.authorities().contains("profile:email")
                ? allowed.email()
                : null;
    }

    public static void main(String[] args) {
        Profile own = new Profile(
                "alice", "Alice", "alice@example.test");
        Profile foreign = new Profile(
                "bob", "Bob", "bob@example.test");
        Actor basic = new Actor(
                "alice", Set.of("profile:read"));
        Actor elevated = new Actor(
                "alice", Set.of("profile:read", "profile:email"));

        System.out.println("ownReadable=" + (view(basic, own) != null));
        System.out.println("foreignReadable=" +
                (view(basic, foreign) != null));
        System.out.println("emailBasic=" + visibleEmail(basic, own));
        System.out.println("emailElevated=" +
                visibleEmail(elevated, own));
    }
}
```

Biên dịch và chạy:

```bash
javac AuthorizationFeatureDemo.java
java AuthorizationFeatureDemo
```

Stdout chính xác:

```text
ownReadable=true
foreignReadable=false
emailBasic=null
emailElevated=alice@example.test
```

Với Java thuần, `visibleEmail` trả `null` bằng biểu thức điều kiện. Trong Spring Security, `@HandleAuthorizationDenied` được gọi khi annotation deny trên **proxy**, không phải vì Java tự che dữ liệu. Hai mô hình cùng minh họa policy nhưng cơ chế thực thi khác nhau.

## 10. Xử lý sau khi có result: masking và nguy cơ side effect

`@PostAuthorize` có thể kiểm tra `returnObject` sau khi getter/service đã chạy. Khi kết quả bị deny, handler có thể nhận `MethodInvocationResult` và trả bản che dữ liệu. Thí dụ nguyên tắc (fragment cần đặt trong handler phù hợp):

```java
@Override
public Object handleDeniedInvocationResult(
        MethodInvocationResult invocationResult,
        AuthorizationResult decision) {
    // Với field không được phép, không trả raw value cho caller.
    return "[REDACTED]";
}
```

Cần import `MethodInvocationResult` từ `org.springframework.security.authorization.method`. Khi bổ sung callback này vào `MethodAuthorizationDeniedHandler`, vẫn phải triển khai `handleDeniedInvocation(...)` theo interface để xử lý denial trước body. Tránh dùng kiểu ép `(String) invocationResult.getResult()` nếu result có thể null hoặc đổi type mà không test.

Phân biệt hai phong cách:

```java
// Trước body: không đọc dữ liệu nhạy cảm khi thiếu quyền.
@PreAuthorize("hasAuthority('secret:read')")
@HandleAuthorizationDenied(handlerClass = NullDeniedHandler.class)
public String readSecret() {
    return secretStore.load();
}

// Sau body: có result mới kiểm tra, phù hợp chỉ khi chính sách
// cho phép load trước rồi che, và không có tác dụng phụ.
@PostAuthorize("hasAuthority('secret:read')")
@HandleAuthorizationDenied(handlerClass = RedactDeniedHandler.class)
public String readForDisplay() {
    return secretStore.load();
}
```

`RedactDeniedHandler` ở ví dụ sau là **tên minh họa** cho handler tương tự fragment ở trên; đoạn này không phải chương trình độc lập. Với dữ liệu có yêu cầu “không được truy xuất khỏi database khi thiếu quyền”, phải kiểm soát quyền **trước truy vấn** và giới hạn dữ liệu ở query, không chọn post-processing. Với ghi/sửa/xóa, kiểm tra trước body, thêm transaction và predicate DB; masking sau khi thực thi không đảo ngược việc ghi.

### Chính sách không làm lộ data qua side-channel

Một handler có thể trả `null` nhưng log lại `returnObject`, trả stack trace chứa email, hoặc phát sự kiện chứa dữ liệu trước lúc bị deny. Vì vậy review phải nhìn cả HTTP body, logs, cache, tracing, metrics và các tác dụng phụ. Không truyền raw result vào bản ghi audit của denied access nếu không có lý do và kiểm soát phù hợp.

## 11. Tương thích kiểu trả về, AOT và serializer

### 11.1. Optional, List, nested object

Tài liệu chính thức có ví dụ `Optional<User>` và `List<Account>` với `@AuthorizeReturnObject`. Khả năng proxy các phần tử phụ thuộc phiên bản và loại trả về; hãy kiểm thử **đúng shape trả về** trong ứng dụng: `ProfileView`, `Optional<ProfileView>`, `List<ProfileView>`, mảng, class kế thừa hoặc các object lồng nhau. Đừng suy từ một method trả class đơn lẻ sang mọi collection/custom wrapper.

Trên class được proxy, mỗi getter nhạy cảm phải có policy rõ, kể cả getter nằm trên object lồng nhau. Nếu `getProfile()` trả `ProfileView` nhưng `getAddress()` trả một `Address` có trường bí mật, cần quyết định liệu phải proxy tiếp `Address`, dùng DTO whitelist hoặc policy service riêng.

### 11.2. Class, final, record, primitive

Proxy của class có thể gặp hạn chế khi class hoặc method là `final`; JDK proxy qua interface lại có quy tắc kiểu gọi khác. Java `record` mặc định là `final`, nên không đánh đồng “là DTO record” với “có thể được class-proxy như bean thường”. Đối với value types và string, cân nhắc `TargetVisitor.defaultsSkipValueTypes()` nếu dùng class-level annotation.

Kiểm tra cấu hình Spring AOP (proxy target class hay interface) và nơi serializer truy cập getter. Một serialization framework truy cập trực tiếp field hoặc một mapper dùng object gốc có thể bỏ qua method security advice; nên **giới hạn dữ liệu được nạp và xuất ngay từ repository/projection** khi bảo mật quan trọng.

### 11.3. AOT/native image và generics

Khi biên dịch ahead-of-time, Spring Security cần biết kiểu có method được bảo vệ hoặc kiểu cần proxy. Tài liệu Spring Security có các registrar runtime hints cho return types, ví dụ `AuthorizeReturnObjectHintsRegistrar` và `PrePostAuthorizeExpressionBeanHintsRegistrar` trong các trường hợp generic type erasure khiến kiểu phần tử không thể suy từ chữ ký method.

Nếu ứng dụng dùng native image, hãy test loại thực tế của collection, proxy class, nested types, reflection và hint registration. Không chỉ dựa vào test JVM thành công rồi kết luận native image chắc chắn tương thích. Tên API registrar và cách đăng ký có thể đổi theo nhánh, nên tra tài liệu version tương ứng trước khi sao chép fragment cấu hình.

### 11.4. Chi phí thực thi

Việc thêm proxy và kiểm tra nhiều getter có thể tăng số lần quyết định quyền, đọc DB hoặc gọi policy service. Với response list lớn, tránh tạo hàng nghìn truy vấn quyền kiểu N+1; đưa object-level filter vào truy vấn, batch-check permission khi an toàn, cache theo actor/tenant/scope với invalidation và expiry đúng. Tối ưu sau khi đã chứng minh policy không rò rỉ.

## 12. Khác biệt giữa nâng cấp 6.2 → 6.3 → 6.4+ và cách di trú

### Bước 1 — Kiểm tra baseline và quyền đang có

Đọc `build.gradle`/BOM, kết quả resolved dependencies, cấu hình `@EnableMethodSecurity` hoặc `@EnableGlobalMethodSecurity`, các policy `@PreAuthorize`/`@PostAuthorize`, custom expression handler và kiểu trả về của service. Ghi hành vi baseline: ai đọc được gì, ai bị deny, HTTP/log side effects ra sao.

**Migration quan trọng khác:** `@EnableGlobalMethodSecurity(prePostEnabled = true)` là cấu hình đời trước. `@EnableMethodSecurity` bật pre/post theo mặc định, dùng API `AuthorizationManager`. Nếu trước đây chỉ bật `@Secured` và tắt pre/post, khi di trú cần xem lại `prePostEnabled = false` thay vì vô tình kích hoạt những annotation trước đó chưa được thực thi.

### Bước 2 — Chọn đúng phiên bản và bản vá

- **Ứng dụng 6.2 trở xuống:** chưa thể áp dụng nguyên mã `@AuthorizeReturnObject`/`@HandleAuthorizationDenied` như bản 6.3, và chưa có annotation template 6.4. Cân nhắc service-level explicit policy, projection/DTO và nâng cấp được kiểm soát.
- **Ứng dụng 6.3:** dùng return-object proxy và denied handler theo API 6.3; **tránh 6.3.0–6.3.1** do advisory đã nêu, tối thiểu kiểm tra 6.3.2 và dùng bản vá phù hợp. Template có tham số `{value}` cần 6.4+.
- **Ứng dụng 6.4+ hoặc nhánh mới hơn:** có thể bật template bean, giữ return-object/denied-handler với kiểm thử hồi quy. Kiểm tra chi tiết package, AOT/proxy và security behavior ở đúng branch.
- Không nâng riêng `spring-security-core` trong khi `spring-security-config` và test dependencies còn khác minor ngoài chiến lược dependency management được hỗ trợ. Hệ sinh thái Spring cần tương thích, tránh version skew.

### Bước 3 — Di trú tuần tự theo hành vi

1. Chốt test của quyền chức năng, quyền đối tượng và trường nhạy cảm trước khi đổi annotation.
2. Nâng dependency và áp dụng hướng dẫn migration chính thức; xác thực method security thực sự bật và proxy đang được tạo.
3. Dùng `@AuthorizeReturnObject` cho một domain/view có getter nhạy cảm đơn giản, test allow/deny, rồi mở rộng từng vùng.
4. Dùng `@HandleAuthorizationDenied` chỉ khi hợp đồng API muốn fallback; test `null`/masked/error khác biệt rõ. Không “đổi toàn bộ 403 thành null” một cách cơ học.
5. Với 6.4+, tạo meta-annotation template cùng bean cấu hình, test đúng authority, role prefix, tham số và việc từ chối khi không có quyền.
6. Với collection/nested/record/native image, viết test riêng cho shape thật trước khi thay đổi hàng loạt.
7. Quan sát log/audit và so sánh response sau triển khai: không lộ raw field, không đổi contract HTTP ngoài ý muốn, không tăng N+1 quá mức chấp nhận.
8. Đặt khả năng rollback deployment theo cách vận hành của dự án nếu phát hiện regression security; giữ chính sách deny làm chuẩn.

Tuyệt đối không dùng một test “mọi request đăng nhập đều trả 200” để kết luận migration hoàn tất. Test bắt buộc có trường hợp thiếu quyền và đối tượng không thuộc chủ sở hữu.

## 13. Ma trận kiểm thử hồi quy thực tế

| Tình huống | Hành động kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Chưa bật `@EnableMethodSecurity` | Gọi method có annotation | Test phải phát hiện guard không chạy; đây là cấu hình lỗi |
| Thiếu `profile:read` | `service.getProfile(1)` | Deny trước body, không trả object |
| Có `profile:read`, profile của mình | `service.getProfile(1)` | Có object proxy, getter thông thường dùng được |
| Có `profile:read` nhưng thiếu `profile:email` | Gọi `proxy.getEmail()` | `null` theo handler minh họa, không có raw email |
| Có cả hai authority | Gọi `proxy.getEmail()` | Trả đúng email của actor |
| Cố lấy profile người khác | `service.getProfile(2)` | `null`/deny theo domain, không xuất giá trị bí mật |
| Bỏ `@AuthorizeReturnObject` trong thử nghiệm âm | Gọi getter nhạy cảm | Test phát hiện chính sách getter không được áp dụng |
| Đặt `@AuthorizeReturnObject` lên class có value returns | Kiểm tra proxy/visitor | Không lỗi proxy String/final type ngoài dự định |
| Gắn template nhưng thiếu bean hoặc sai version | Dùng `@RequiresPermission` | Test phát hiện annotation không hoạt động đúng |
| Annotation trùng/xung đột | Khởi động context / gọi method | Startup/test phải phát hiện cấu hình mơ hồ |
| Denied với `@PostAuthorize` | Method read-only có return value | Handler che dữ liệu, không leak qua errors/log |
| Denied trước mutation | Method ghi dữ liệu | Không có DB update, event, audit thành công sai |
| `Optional/List/nested` | Truy cập từng phần tử/getter | Policy hoạt động trên mọi đường dữ liệu |
| HTTP serialization | Trả object ra JSON | Không xuất trường nhạy cảm qua field access |
| AOT/native image | Native integration test | Proxy, interceptor, hints và result đúng |
| Cấu hình AOP + FactoryBean | Kiểm tra nhánh có advisory | Dùng phiên bản đã fix; test method advice được áp dụng |

Test quan trọng nhất phải **thất bại nếu bỏ kiểm soát**. Với return-object proxy, so sánh trực tiếp object gốc và object proxy; với annotation template, gỡ bean template trong môi trường thử nghiệm cô lập để xác minh test thực sự nhận ra hành vi bị mất. Test bảo mật là bằng chứng thực thi, không chỉ kiểm tra annotation tồn tại bằng reflection.

## 14. Những hiểu lầm gây lỗi khi chuyển phiên bản

- **“Mọi bản 6.x đều có `@AuthorizeReturnObject`.”** API bắt đầu ở 6.3; 6.2 trở xuống không có.
- **“Có 6.3 là đã có template `{value}`.”** `AnnotationTemplateExpressionDefaults` bắt đầu ở 6.4.
- **“`@AuthorizeReturnObject` tự bảo vệ từng field.”** Getter/method vẫn cần rule; đường truy cập trước proxy cũng phải an toàn.
- **“Bảo vệ getter thì khỏi cần kiểm tra object/tenant.”** Object khác tenant có thể lộ qua các field khác hoặc serializer.
- **“`@HandleAuthorizationDenied` là annotation xác định ai được phép.”** Nó chỉ quyết định cách xử lý khi đã deny.
- **“Trả null luôn tốt hơn 403.”** Fallback có thể phá contract, che lỗi hoặc gây giả thành công.
- **“`@PostAuthorize` deny thì database tự rollback.”** Body đã chạy; side effect cần kiểm tra/transaction rõ.
- **“Proxy hoạt động mọi nơi.”** Self-invocation, final methods, object gốc ngoài proxy và serialization đặc biệt có thể bỏ qua interception.
- **“Đã có `@RequiresPermission` thì luôn phân giải placeholder.”** Cần bean template và đúng version.
- **“Trộn meta `@PreAuthorize` với annotation trực tiếp sẽ AND theo ý muốn.”** Repeated same annotation không được hỗ trợ; thiết kế một policy rõ.
- **“Spring Boot starter tự bật method security.”** Cần `@EnableMethodSecurity`.
- **“Đã vá app thì phiên bản Security chắc chắn an toàn.”** Kiểm tra resolved dependency và advisory cụ thể; 6.3.0/6.3.1 có trường hợp thiếu advice.
- **“Test service thành công là serialization đã an toàn.”** Test endpoint thật với format JSON/GraphQL và các serializer đang dùng.
- **“JVM pass thì native image pass.”** AOT generic/proxy runtime hints cần kiểm chứng riêng.
- **“Role ADMIN vượt toàn bộ object ACL.”** Nếu có ngoại lệ admin, phải mô tả bằng policy domain và audit; không tự động cho bypass từ annotation.

## 15. Bài tập và tiêu chí nghiệm thu

**Bài tập A — Xác định phiên bản hỗ trợ.** Cho ba ứng dụng dùng Spring Security 6.2, 6.3.2 và 6.4+. Hãy ghi annotation nào có thể dùng nguyên bản, annotation nào cần thay bằng chính sách service tường minh, và tại sao không nên dùng 6.3.0/6.3.1 cho tình huống bị advisory.

**Bài tập B — Bảo vệ field.** Thêm `phoneNumber` vào `ProfileView` và tạo authority `profile:phone`. Kiểm chứng actor có quyền đọc hồ sơ nhưng thiếu quyền field sẽ không nhận số điện thoại, kể cả khi JSON serializer được chạy. Cân nhắc trả null và trả masked string: khi nào contract cho phép mỗi cách?

**Bài tập C — Annotation template.** Tạo `@RequiresPermission("profile:edit")` cho method không có side effect trước authorization. Test có/không authority. Thử thiếu bean template trong test cách ly và đối chiếu kết quả; sửa cho cơ chế bảo vệ hoạt động. Không kết hợp hai `@PreAuthorize` trên cùng method.

**Bài tập D — Migration và proxy.** Chạy test với đối tượng trực tiếp, `Optional<ProfileView>`, `List<ProfileView>`. Xác nhận đúng phương thức nào thực sự được bao bởi proxy. Thử record/final type và ghi rõ hạn chế; không đẩy ra production nếu chưa có test đường serializer.

**Checklist kết thúc:** xác định dependency Spring Security đã resolve và bản vá; bật method security; policy service áp dụng đúng object/tenant; object trả về được proxy đúng đường; từng getter nhạy cảm có annotation/policy; deny handler trả kết quả an toàn theo return type; template bean được bật trong version phù hợp; test cả allow/deny và negative control; không có data leak hay side effect khi denial; những kiểu collection/AOT/serializer đang dùng đã được kiểm tra.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security, Return Objects, Denied Results, Meta-Annotation Templates: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security — `@AuthorizeReturnObject` Javadoc (Since 6.3): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/AuthorizeReturnObject.html
- Spring Security — `@HandleAuthorizationDenied` Javadoc (Since 6.3): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/HandleAuthorizationDenied.html
- Spring Security — `MethodAuthorizationDeniedHandler` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/MethodAuthorizationDeniedHandler.html
- Spring Security — `AnnotationTemplateExpressionDefaults` Javadoc (Since 6.4): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/annotation/AnnotationTemplateExpressionDefaults.html
- Spring Security Advisory — CVE-2024-38810 (6.3.0/6.3.1, fix 6.3.2): https://spring.io/security/cve-2024-38810/
