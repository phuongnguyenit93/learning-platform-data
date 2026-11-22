# DefaultMethodSecurityExpressionHandler và các điểm tùy biến trong Spring Security

## 1. Vì sao cần hiểu class này?

Khi một service dùng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` hoặc `@PostFilter`, Spring Security cần hiểu các biểu thức như:

```java
@PreAuthorize("hasRole('ADMIN') or @documentAccess.canRead(authentication, #p0)")
public Document findById(long id) { /* ... */ }
```

`DefaultMethodSecurityExpressionHandler` là **triển khai mặc định của `MethodSecurityExpressionHandler`** hỗ trợ phân tích cú pháp biểu thức Spring Expression Language (SpEL), tạo môi trường đánh giá cho **lời gọi phương thức**, cung cấp root chứa các phép kiểm tra bảo mật và hỗ trợ lọc đầu vào/kết quả.

Có thể xem nó là **bộ chuyển ngữ cảnh của lời gọi phương thức sang ngữ cảnh mà biểu thức phân quyền hiểu được**: ai gọi, gọi phương thức nào, tham số gì, kết quả gì, và có thể gọi bean nào để đưa ra quyết định. Nó **không tự xác thực mật khẩu**, không sở hữu dữ liệu permission của ứng dụng, không phải endpoint filter và không thay thế `AuthorizationManager` đưa ra quyết định chặn/cho qua ở interceptor.

Mục tiêu sau bài học:

1. Theo được đường đi từ method-security annotation đến `EvaluationContext` và kết quả phân quyền.
2. Nhận diện các biến và hàm root của biểu thức: `authentication`, `principal`, `hasRole`, `hasAuthority`, `hasPermission`, `#p0`, `returnObject`, `filterObject`.
3. Chọn đúng mức mở rộng: **bean được gọi bằng SpEL → `PermissionEvaluator`/`RoleHierarchy` → cấu hình handler → tùy biến `AuthorizationManager`**, thay vì lập tức subclass handler.
4. Tránh các sai lầm về proxy, bean khởi tạo quá muộn, biểu thức kiểm tra sai tham số, khác biệt phiên bản Spring Security 6 và 7.

Phạm vi bài này là **method authorization**, chủ yếu với ứng dụng Servlet/Spring Boot thông thường; cấu hình dành riêng cho HTTP request, WebSocket message hoặc reactive method security có điểm khác.

## 2. Vị trí trong kiến trúc thực thi

Ví dụ lời gọi của client đi vào bean `DocumentService` do Spring quản lý:

```text
Caller
  |
  v
Spring AOP proxy của DocumentService
  |
  v
AuthorizationManagerBeforeMethodInterceptor (@PreAuthorize)
  |
  v
PreAuthorizeAuthorizationManager
  |
  v
MethodSecurityExpressionHandler
  |-- SpEL ExpressionParser: phân tích "hasRole(...) and ..."
  |-- MethodInvocation: method, target, arguments
  |-- Supplier<Authentication>: lấy người dùng hiện tại khi cần
  |-- MethodSecurityEvaluationContext:
  |      root + tham số #p0/#p1/tên tham số + bean resolver
  v
Đánh giá biểu thức thành quyết định phân quyền
  |                     |
  | được phép           | bị từ chối
  v                     v
Thân phương thức        AccessDeniedException
```

Sau khi method trả về, advice của `@PostAuthorize` có thể đánh giá điều kiện phụ thuộc `returnObject`. Với `@PreFilter` và `@PostFilter`, handler hỗ trợ đánh giá biểu thức cho từng phần tử, qua `filterObject`. Các advice hoạt động ở thời điểm khác nhau; **không được coi lọc sau phương thức là một cơ chế hoàn tác thao tác ghi**.

Các loại và trách nhiệm:

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| `@EnableMethodSecurity` | Bật method-security infrastructure | Đặt trên `@Configuration` |
| `AuthorizationManagerBeforeMethodInterceptor` | Chặn lời gọi trước khi chạy | Advice ứng với `@PreAuthorize` |
| `PreAuthorizeAuthorizationManager` | Lấy và đánh giá chính sách trước lời gọi | Dùng handler để xử lý SpEL |
| `DefaultMethodSecurityExpressionHandler` | Tạo evaluation context và hỗ trợ đánh giá/lọc | Cài role hierarchy, permission evaluator |
| `MethodSecurityEvaluationContext` | Đặt root và tham số phương thức vào context | `#p0`, tên tham số |
| `MethodSecurityExpressionOperations` | Giao diện các phép/thuộc tính của root phương thức | `hasRole`, `authentication`, `filterObject` |
| `PermissionEvaluator` | Gắn luật quyền đối tượng vào `hasPermission(...)` | Can-read theo ID và tenant |
| `AuthorizationManager` tùy biến | Tự quyết định quyền bằng Java nếu SpEL không phù hợp | Luật nhiều điều kiện, kết quả có lý do |

`DefaultMethodSecurityExpressionHandler` nằm trong package:

```java
org.springframework.security.access.expression.method
    .DefaultMethodSecurityExpressionHandler
```

Handler này mở rộng `AbstractSecurityExpressionHandler<MethodInvocation>` và triển khai `MethodSecurityExpressionHandler`. Không nhầm với `DefaultWebSecurityExpressionHandler` cho mô hình web expression cũ hoặc `DefaultMessageSecurityExpressionHandler` cho messaging.

### Handler biết những gì khi đánh giá?

Ví dụ biểu thức:

```java
@PreAuthorize("hasAuthority('DOC_READ') and "
            + "@documentAccess.canRead(authentication, #p0)")
public Document read(long id) { /* ... */ }
```

Trong lời gọi `read(42L)`, expression context có:

- `authentication`: đối tượng `Authentication` liên quan đến invocation; `authentication.name` thường là tên principal.
- `principal`: phần principal bên trong `Authentication`; kiểu thực tế có thể là `UserDetails`, `Jwt`, chuỗi, hoặc kiểu riêng.
- `#p0`/`#a0`: tham số đầu tiên (ở đây `42L`); `#p1`/`#a1`: tham số thứ hai.
- `#id`: sử dụng được nếu tên tham số được Spring xác định, ví dụ nhờ `-parameters` hoặc annotation `@P("id")`. Không mặc định mọi ứng dụng đều biên dịch giữ tên tham số.
- `@documentAccess`: một bean có tên `documentAccess` trong Spring application context, được phép gọi từ biểu thức.
- Root security: các phép `hasAuthority`, `hasRole`, `isAuthenticated`, `permitAll`, `denyAll`, `hasPermission`...

Khuyến nghị giữ policy đủ rõ để đọc: `hasAuthority('DOC_READ') and @documentAccess.canRead(authentication, #p0)`. Khi nghiệp vụ phức tạp hơn, chuyển logic sang class Java thay vì nhồi hàng chục phép điều kiện trực tiếp trong chuỗi annotation.

## 3. Những điểm mặc định cần nắm vững

### 3.1. Role, authority và tiền tố

- `hasAuthority('DOC_READ')` yêu cầu một authority có tên tương ứng, không tự thêm `ROLE_`.
- `hasRole('ADMIN')` thông thường kiểm tra authority `ROLE_ADMIN` nhờ tiền tố mặc định `ROLE_`.
- `RoleHierarchy` có thể làm quyền cấp cao bao hàm quyền cấp thấp: ví dụ `ROLE_ADMIN > ROLE_READER`.
- Chỉ đổi biểu thức sang `hasRole('ADMIN')` không khiến Spring tự cấp `ROLE_ADMIN` cho ai; quyền thực tế vẫn phải có trong `Authentication` hoặc được suy ra bằng hierarchy có cấu hình.

### 3.2. Quyền đối tượng bằng `hasPermission`

Hai dạng phổ biến:

```java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document view(Document document) { /* ... */ }

@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document viewById(long id) { /* ... */ }
```

Dạng thứ nhất truyền một domain object cho `PermissionEvaluator.hasPermission(Authentication, Object, Object)`. Dạng thứ hai truyền ID, tên loại đối tượng và action cho overload `hasPermission(Authentication, Serializable, String, Object)`. Kiểu, thứ tự và ý nghĩa các tham số là **hợp đồng ứng dụng** của evaluator, không phải Spring tự biết ý nghĩa “Document/read”.

Nếu ứng dụng không cấp một evaluator phù hợp, `hasPermission` không tự kiểm tra database/ACL theo kỳ vọng. Đừng giả định chỉ khai báo annotation đã đủ triển khai phân quyền theo chủ sở hữu.

### 3.3. Biến sau lời gọi và biến phần tử

```java
@PostAuthorize("returnObject == null or returnObject.owner == authentication.name")
public Document fetch(long id) { /* ... */ }

@PostFilter("filterObject.publicVisible or filterObject.owner == authentication.name")
public List<Document> list() { /* ... */ }
```

- `returnObject` là giá trị trả về của method trong bối cảnh `@PostAuthorize`.
- `filterObject` là từng phần tử đang xét trong `@PreFilter`/`@PostFilter`.
- `@PostAuthorize` có thể từ chối sau khi thân phương thức đã chạy. Không dùng một phép kiểm tra sau lời gọi để bảo vệ thao tác ghi có side effect.
- Dùng `@PostFilter` cho tập dữ liệu rất lớn có thể làm nhiều việc ở bộ nhớ không cần thiết; cân nhắc lọc tại truy vấn database theo tenant/quyền.

### 3.4. `Supplier<Authentication>` và lazy lookup

Method security hiện đại dùng `Supplier<Authentication>` khi tạo context để có thể trì hoãn việc lấy thông tin xác thực. Một biểu thức như `permitAll` có thể không cần đọc `Authentication`. Việc tự viết handler mà lấy `authentication.get()` quá sớm có thể đánh mất lợi ích này hoặc thay đổi thời điểm kiểm tra.

Đây cũng là lý do một số cách subclass trước đây không còn hoạt động như mong đợi, sẽ được làm rõ ở mục 7.

## 4. Nên tùy biến ở mức nào?

| Nhu cầu | Điểm tùy biến phù hợp | Vì sao |
| --- | --- | --- |
| Kiểm tra chủ sở hữu, tenant, trạng thái tài nguyên, nghiệp vụ riêng | Bean `@policyName` trong SpEL | Dễ kiểm thử Java, không cần thay root |
| Dùng API `hasPermission` trên domain object/ID | Cài `PermissionEvaluator` vào handler | Tập trung ngữ nghĩa quyền đối tượng |
| Cho phép một role bao hàm role khác | `RoleHierarchy` qua handler/factory phù hợp phiên bản | Giữ biểu thức vai trò đơn giản |
| Đổi tiền tố của `hasRole` | `GrantedAuthorityDefaults` hoặc cấu hình factory tương ứng | Tránh viết nhầm `ROLE_` ở nhiều chỗ |
| Đổi cách phát hiện tên tham số | `setParameterNameDiscoverer(...)`, `@P` hoặc `#p0` | Ổn định truy cập tham số |
| Thay cách phân tích SpEL | `setExpressionParser(...)` (rất hiếm) | Ảnh hưởng mọi biểu thức dùng handler |
| Cần một hàm root SpEL mới không phù hợp với bean | Tùy biến evaluation context/root có kiểm thử | Can thiệp sâu, dễ phụ thuộc phiên bản |
| Policy phức tạp hoặc không muốn dựa vào SpEL | `AuthorizationManager` và advisor phù hợp | Quyết định bằng Java, kiểm thử độc lập |

**Thứ tự thực dụng:** thử bean policy được gọi bằng `@bean.method(...)` trước. Chỉ điều chỉnh handler khi cần sửa một khả năng dùng chung của chính expression engine. Một handler thường được chia sẻ bởi các advisor sử dụng expression; không tạo một handler mới cho mỗi service hoặc mỗi method.

## 5. Cách đơn giản nhất: dùng bean chính sách trong SpEL

Giả sử tài liệu có `tenantId` và `ownerId` nằm trong database; ứng dụng muốn chỉ cho người có quyền đọc và thuộc tenant phù hợp truy cập. Policy nên nằm trong bean Java, nhận danh tính và ID rồi tra dữ liệu phía server.

```java
@Component("documentAccess")
public class DocumentAccess {

    private final DocumentRepository repository;

    public DocumentAccess(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication auth, long documentId) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }

        return repository.findById(documentId)
                .filter(doc -> tenantMatches(auth, doc.tenantId()))
                .filter(doc -> ownerOrShared(auth, doc))
                .isPresent();
    }

    // tenantMatches, ownerOrShared là luật nghiệp vụ của dự án.
}
```

Đây là **đoạn tích hợp**, không phải file chạy độc lập: `DocumentRepository`, `tenantMatches` và `ownerOrShared` do ứng dụng triển khai, và cần xử lý authentication ẩn danh theo đúng chính sách. Tránh tin `tenantId` do client tự gửi mà không đối chiếu claim/identity tin cậy.

Dùng tại service:

```java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOC_READ') and "
                + "@documentAccess.canRead(authentication, #p0)")
    public Document read(long id) {
        // Chỉ chạy khi cả hai điều kiện đã cho phép.
        return loadDocument(id);
    }
}
```

`loadDocument` là phương thức của ứng dụng, được lược bỏ để tập trung vào policy. `@documentAccess` là cú pháp SpEL gọi bean do Spring quản lý; không cần subclass `DefaultMethodSecurityExpressionHandler` chỉ để tạo hàm `canRead`.

Nếu muốn tách hẳn biểu thức khỏi chi tiết người dùng, bean cũng có thể nhận `#root` (kiểu `MethodSecurityExpressionOperations`) và dùng `root.hasAuthority(...)`. Cách này phù hợp khi muốn gọi lại các phép kiểm tra chuẩn trong cùng chính sách.

**Lợi ích:** policy là mã Java có kiểu, dễ mock repository, test được các nhánh deny; annotation chỉ còn nêu chính sách ở ranh giới lời gọi. **Giới hạn:** query trong policy có thể tạo thêm round-trip và gặp race condition nếu quyền/trạng thái thay đổi trước bước ghi; với thao tác ghi nhạy cảm, kiểm tra nhất quán trong cùng transaction hoặc dùng locking/version thích hợp.

## 6. Cấu hình `DefaultMethodSecurityExpressionHandler` dùng chung

Khi phải thiết lập role hierarchy hoặc evaluator mặc định cho biểu thức, có thể khai báo một bean `MethodSecurityExpressionHandler`. Cần đảm bảo bean tồn tại **trước khi Spring dựng cấu hình method security**; tài liệu Spring Security minh họa `@Bean static` nhằm đáp ứng thứ tự khởi tạo đó.

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
                "ROLE_ADMIN > ROLE_READER");
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
```

Imports chính của đoạn tích hợp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Khi đó, trong cấu hình phù hợp, người có authority `ROLE_ADMIN` được xem là có vai trò `READER` khi đánh giá:

```java
@PreAuthorize("hasRole('READER')")
public String readReport(long id) {
    return "report-" + id;
}
```

**Lưu ý tương thích:** `setRoleHierarchy(...)` tồn tại và sử dụng rộng rãi trong Spring Security 6.x. Trong API Spring Security **7.0+**, setter này bị đánh dấu deprecated, với khuyến nghị sử dụng `setAuthorizationManagerFactory(AuthorizationManagerFactory)` hoặc cơ chế cấu hình factory tương ứng; không sao chép cấu hình 6.x mà bỏ qua cảnh báo khi nâng cấp. `setDefaultRolePrefix(...)` và `setTrustResolver(...)` cũng deprecated từ 7.0. Phần ví dụ thực hành tiếp theo cố định Spring Boot 3.5.15 (dòng Spring Security 6.x) để có hành vi và API nhất quán.

Để đổi tiền tố vai trò ở cấp ứng dụng, Spring Security còn cung cấp:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}
```

Với cấu hình ấy, `hasRole('READER')` thường hướng tới `APP_READER` thay vì `ROLE_READER` trong các thành phần hỗ trợ cấu hình này. Cần kiểm thử cả rules ở web, method, `@Secured`/JSR-250 và cấu hình hierarchy cụ thể; **không mặc định mỗi kiểu annotation đều dùng cùng expression handler**. Không tự thêm tiền tố thủ công hai lần.

## 7. Thêm `PermissionEvaluator`: điểm nối với domain permission

`PermissionEvaluator` có hai overload; triển khai đầy đủ **cả hai**, kể cả khi một overload không được hỗ trợ, và nên **deny by default** khi không nhận diện được loại đối tượng/hành động.

Minh họa tích hợp:

```java
import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.Authentication;

public final class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentAuthorizationRepository repository;

    public DocumentPermissionEvaluator(
            DocumentAuthorizationRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean hasPermission(Authentication auth,
                                 Object target,
                                 Object permission) {
        if (!(target instanceof Document document)) {
            return false;
        }
        return canRead(auth, document.id(), permission);
    }

    @Override
    public boolean hasPermission(Authentication auth,
                                 Serializable targetId,
                                 String targetType,
                                 Object permission) {
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }
        return canRead(auth, id, permission);
    }

    private boolean canRead(Authentication auth, long id, Object action) {
        return auth != null
                && "read".equals(action)
                && repository.isReader(auth.getName(), id);
    }
}
```

`Document` và `DocumentAuthorizationRepository` là kiểu do dự án cung cấp; đây là đoạn tích hợp, không phải chương trình độc lập. `isReader` phải kiểm tra quyền dựa trên dữ liệu server/tenant; ví dụ tập trung vào hai overload và chính sách deny mặc định.

Đăng ký evaluator và cấu hình **cùng một handler**:

```java
@Bean
static PermissionEvaluator documentPermissionEvaluator(
        DocumentAuthorizationRepository repository) {
    return new DocumentPermissionEvaluator(repository);
}

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy hierarchy, PermissionEvaluator evaluator) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(hierarchy);
    handler.setPermissionEvaluator(evaluator);
    return handler;
}
```

Đoạn trên **thay thế** bean `methodSecurityExpressionHandler` ở mục 6, không được thêm như một bean thứ hai. Dùng với:

```java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(long documentId) { /* ... */ }
```

Đánh đổi quan trọng:

- `hasPermission` đưa ra một ngôn ngữ chung cho nhiều domain object; bean `@documentAccess` thường dễ đọc hơn với chính sách nghiệp vụ đơn giản.
- Nếu evaluator dùng repository, chú ý số lần query: filter theo từng phần tử có thể sinh N+1 truy vấn; cân nhắc truy vấn batch hoặc filter tại DB.
- Đừng cache quyết định quyền vô hạn; tenant, chủ sở hữu và revocation có thể thay đổi.
- Không trả `true` cho overload chưa triển khai; không tin thuộc tính quyền hoặc tenant được truyền từ phía client.

## 8. Ví dụ Java 17 chạy được: thấy rõ vai trò của handler

Ví dụ nhỏ sau chạy trong **Spring Boot 3.5.15** với Java 17. Nó minh họa đồng thời:

1. Handler được khai báo bằng `@Bean static`.
2. `ROLE_ADMIN` suy ra `ROLE_READER` từ hierarchy.
3. Bean policy `@reportGate` kiểm tra điều kiện theo ID.
4. `@PreAuthorize` thực sự chặn lời gọi qua proxy; chương trình đổi `SecurityContext` để xem các kết quả.

Cấu trúc:

```text
method-security-demo/
  pom.xml
  src/main/java/demo/
    MethodSecurityDemo.java
    ReportGate.java
    ReportService.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.15</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>method-security-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
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

Tệp `src/main/java/demo/MethodSecurityDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(MethodSecurityDemo.class);
        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"
        ));
        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner đã chạy trước khi SpringApplication.run trả về.
        }
    }

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
                "ROLE_ADMIN > ROLE_READER");
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    @Bean
    CommandLineRunner demo(ReportService reportService) {
        return args -> {
            attempt(reportService, "alice", "ROLE_ADMIN", 42L);
            attempt(reportService, "alice", "ROLE_ADMIN", 7L);
            attempt(reportService, "bob", "ROLE_READER", 42L);
        };
    }

    private static void attempt(ReportService service, String username,
                                String role, long reportId) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        "ignored",
                        List.of(new SimpleGrantedAuthority(role))));
        SecurityContextHolder.setContext(context);

        try {
            String value = service.readReport(reportId);
            System.out.println(username + "/" + reportId + ": " + value);
        } catch (AccessDeniedException denied) {
            System.out.println(username + "/" + reportId + ": DENIED");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

Tệp `src/main/java/demo/ReportGate.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportGate")
public class ReportGate {

    public boolean canRead(Authentication authentication, long reportId) {
        // Dữ liệu giả lập cho bài học: chỉ alice được xem report 42.
        return authentication != null
                && "alice".equals(authentication.getName())
                && reportId == 42L;
    }
}
```

Tệp `src/main/java/demo/ReportService.java`:

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('READER') and "
                + "@reportGate.canRead(authentication, #p0)")
    public String readReport(long reportId) {
        return "report-" + reportId;
    }
}
```

Lệnh chạy tại thư mục có `pom.xml` (máy cần JDK 17+ và Maven):

```bash
mvn -q clean package
java -jar target/method-security-demo-1.0.0.jar
```

Ba dòng kết quả do ứng dụng in ra:

```text
alice/42: report-42
alice/7: DENIED
bob/42: DENIED
```

Giải thích từng trường hợp:

- `alice/42`: `alice` có `ROLE_ADMIN`; hierarchy khiến `hasRole('READER')` đạt; `reportGate.canRead` cũng đạt → service được gọi.
- `alice/7`: role đạt nhưng bean policy từ chối ID `7` → service không chạy.
- `bob/42`: `bob` có `ROLE_READER` nên điều kiện role đạt; policy chỉ cho `alice` nên vẫn từ chối.
- Vì `CommandLineRunner` gọi `ReportService` được lấy từ Spring container, method interceptor thực sự tham gia. Nếu tự `new ReportService()` và gọi trực tiếp thì annotation không tự hoạt động.

Đây là demo command-line chủ động đặt `Authentication` giả để dễ quan sát, **không phải cách đăng nhập người dùng cho production**. Hệ thống thực dùng security filter/authentication provider được cấu hình và policy quyền từ dữ liệu đáng tin cậy. `ReportGate` cố ý hardcode để bài minh họa có kết quả xác định.

### Đổi sang permission evaluator

Nếu muốn dùng `hasPermission`, thay biểu thức bằng:

```java
@PreAuthorize("hasPermission(#p0, 'Report', 'read')")
public String readReport(long reportId) { /* ... */ }
```

Sau đó đưa `PermissionEvaluator` phù hợp vào **chính bean handler hiện có** qua `setPermissionEvaluator(...)`. Không chỉ đổi annotation rồi bỏ qua bước đăng ký evaluator; kết quả sẽ khác kỳ vọng.

## 9. Khi nào cần subclass handler?

Một số hệ thống cũ kế thừa `DefaultMethodSecurityExpressionHandler` để thêm hàm kiểu `isTenantAdmin()` lên custom root. Cách này can thiệp sâu hơn bean SpEL vì phải đảm bảo root mới giữ được mọi phép kiểm tra/biến của `MethodSecurityExpressionOperations`.

**Bẫy nâng cấp quan trọng:** với `@EnableMethodSecurity` hiện đại, cơ chế evaluation dùng overload `createEvaluationContext(Supplier<Authentication>, MethodInvocation)`. Override **chỉ** `createSecurityExpressionRoot(Authentication, MethodInvocation)` có thể không được gọi như trước. Tài liệu Spring Security khuyên dùng bean policy nếu có thể.

Nếu thật sự phải tạo root riêng, ý tưởng chính là:

```text
createEvaluationContext(Supplier<Authentication>, MethodInvocation)
    -> gọi super.createEvaluationContext(...)
    -> lấy root hiện tại từ StandardEvaluationContext
    -> tạo custom root/decorator giữ MethodSecurityExpressionOperations
    -> setRootObject(customRoot)
    -> trả về context
```

Đây là **phác thảo**, không phải Java chạy độc lập. Chữ ký generic và nullability có khác biệt theo phiên bản Spring Security; kiểm tra JavaDoc đúng version trước khi viết `@Override`. Một custom root phải giữ toàn bộ hành vi tiêu chuẩn như `hasRole`, `hasPermission`, `authentication`, `returnObject` và `filterObject`; nếu bỏ một phần, những annotation đang đúng có thể sai khi thay handler. Không thay root chỉ để thêm một phép `canRead` có thể viết trong bean.

Mặt khác, khi cần chính sách hoàn toàn do Java tính toán, dùng `AuthorizationManager<MethodInvocation>` được gắn qua method advisor phù hợp sẽ tránh ép logic phức tạp vào SpEL. Handler không phải điểm mở rộng duy nhất của kiến trúc authorization.

## 10. Cách xác minh cấu hình và kiểm thử

Hãy kiểm thử qua **Spring bean proxy**, dùng `@SpringBootTest` và `spring-security-test`/`@WithMockUser` khi phù hợp. Với demo ở mục 8, mỗi trường hợp tương ứng một phép kiểm tra cụ thể:

| Tình huống | Kỳ vọng | Phát hiện lỗi gì? |
| --- | --- | --- |
| `alice` chỉ có `ROLE_ADMIN` gọi ID 42 | Cho phép | Handler/hierarchy đã được áp dụng |
| `alice` gọi ID 7 | Từ chối | Bean policy được gọi, không bỏ qua quyền theo tài nguyên |
| `bob` có `ROLE_READER` gọi ID 42 | Từ chối | Kiểm tra owner/tenant không bị thay bằng kiểm tra role |
| Không có authentication hợp lệ | Từ chối với rule yêu cầu quyền | Không vô tình cho anonymous quyền |
| `hasPermission` với object/ID không nhận diện | Từ chối | Evaluator có deny mặc định |
| Tham số tên `#id` không được xác định | Test nhận diện lỗi expression | Cần `-parameters`, `@P` hoặc `#p0` |
| Gọi qua proxy và tự gọi trong cùng bean | Khác biệt phải được hiểu rõ | Self-invocation có thể bỏ qua advice |
| Thêm bean handler cấu hình sớm | Cấu hình hiệu lực | Tránh bean có nhưng infrastructure không dùng |
| Nâng Spring Security 6 lên 7 | Kiểm tra deprecation và hành vi | Không phụ thuộc setter cũ vô thời hạn |

Ví dụ test kiểm tra từ chối nếu đã có `spring-security-test`:

```java
@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminCanReadAllowedReportThroughHierarchy() {
        assertEquals("report-42", reportService.readReport(42L));
    }

    @Test
    @WithMockUser(username = "bob", roles = "READER")
    void readerWithoutResourcePermissionIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> reportService.readReport(42L));
    }
}
```

Đoạn test là ví dụ **đưa vào dự án Spring Boot test** (cần các imports JUnit 5, `@SpringBootTest`, `@Autowired`, `@WithMockUser` và `AccessDeniedException` cùng các dependencies `spring-boot-starter-test`, `spring-security-test`); chưa phải một source độc lập chạy bằng `javac`. Vì có thể xuất hiện khác biệt thứ tự bean/advisor hoặc thiết lập context, test thực tế quan trọng hơn việc chỉ thấy handler được tạo.

## 11. Những lỗi thường gặp và cách xử lý

**1. Đã định nghĩa bean `MethodSecurityExpressionHandler` nhưng role hierarchy không có hiệu lực.** Kiểm tra `@EnableMethodSecurity`, bean có bị đăng ký quá muộn hay trùng, có dùng `@Bean static`, có gọi service qua proxy, có đang test `@Secured`/JSR-250 thay vì expression annotation, và version đang dùng. Không mặc định mọi authorization manager dùng chung một handler.

**2. Thêm `@Component("policy")` rồi muốn gọi `canRead(...)` mà subclass expression root.** Không cần. Dùng trực tiếp `@policy.canRead(authentication, #p0)`; policy nhận đủ tham số cần thiết và được unit-test bằng Java thuần.

**3. `hasRole('ADMIN')` không khớp authority.** Kiểm tra authority thực tế có tên `ROLE_ADMIN` hay tiền tố tùy biến; phân biệt `hasRole` và `hasAuthority`. Test có hierarchy để xác nhận vai trò được bao hàm như dự kiến.

**4. `#documentId` luôn null hoặc SpEL không tìm thấy biến.** Kiểm tra Java compiler giữ tên tham số, annotation `@P`, tên method thực tế trên interface/proxy và dùng `#p0` như một đường kiểm tra chắc chắn.

**5. Truyền `returnObject` vào `@PreAuthorize`.** Giá trị trả về chưa tồn tại tại thời điểm pre-authorization. Dùng `@PostAuthorize` cho kiểm tra sau method; với thao tác ghi cần kiểm tra quyền và tính nguyên tử trước khi gây side effect.

**6. Policy truy cập database một lần cho từng phần tử.** Với `@PostFilter` hoặc `@PreFilter`, evaluator/bean có thể chạy nhiều lần. Kiểm tra N+1 query, cache đúng phạm vi request/tenant hoặc chuyển lọc về database.

**7. Dùng `isAuthenticated()` đơn lẻ làm toàn bộ xác thực quyền.** Điều kiện “đã xác thực” không nói người dùng có quyền trên tài nguyên cụ thể. Với luồng yêu cầu authentication, phân biệt anonymous, remember-me và fully authenticated nếu chính sách yêu cầu; kiểm tra authority và quyền domain ở chỗ thích hợp.

**8. Viết biểu thức SpEL tùy ý từ input người dùng.** Annotation thường chứa biểu thức do code ứng dụng quản lý. Không biến dữ liệu client thành mã SpEL được parse/đánh giá, bởi SpEL có thể tham chiếu bean/phương thức trong context; giá trị client chỉ nên xuất hiện như **dữ liệu tham số** đã được validate.

**9. Override class root cũ rồi nâng lên `@EnableMethodSecurity` mới.** Kiểm tra overload dùng `Supplier<Authentication>` và giữ contract của `MethodSecurityExpressionOperations`. Với phần lớn nghiệp vụ, di chuyển logic vào bean SpEL.

**10. Ghi log mật khẩu, token hoặc toàn bộ principal khi debug.** Chỉ log tên policy, method, ID tài nguyên phù hợp và kết quả; tuân thủ quy định bảo mật dữ liệu và không ghi bí mật xác thực.

## 12. Checklist khi lựa chọn điểm mở rộng

- [ ] Ứng dụng đã bật `@EnableMethodSecurity` và test gọi method qua Spring bean proxy.
- [ ] Đã phân biệt rõ yêu cầu quyền theo HTTP route, method, role và đối tượng.
- [ ] Chính sách nghiệp vụ riêng ưu tiên bean Java có tên rõ ràng; biểu thức annotation ngắn và dễ hiểu.
- [ ] Nếu dùng `hasPermission`, cả overload của `PermissionEvaluator` đều có hành vi deny an toàn.
- [ ] Role hierarchy/prefix và nguồn authority trong `Authentication` nhất quán; có test cho quyền được phép và bị từ chối.
- [ ] Nếu định nghĩa handler, đăng ký sớm bằng bean phù hợp và tránh nhiều handler mâu thuẫn.
- [ ] Mọi tùy biến subclass đã kiểm tra chữ ký `createEvaluationContext(Supplier<Authentication>, MethodInvocation)` đúng version, không làm mất root chuẩn.
- [ ] Có test theo quyền từng đối tượng, tenant, trạng thái thay đổi, self-invocation và lỗi SpEL.
- [ ] Quyền dựa trên dữ liệu server, deny by default; giới hạn N+1 query và tránh rò dữ liệu nhạy cảm.
- [ ] Khi nâng Spring Security 7+, đã đối chiếu cảnh báo deprecated của `setRoleHierarchy`, `setDefaultRolePrefix`, `setTrustResolver` và cân nhắc `AuthorizationManagerFactory`.

**Ghi nhớ:** `DefaultMethodSecurityExpressionHandler` giải quyết **cách đánh giá biểu thức method security trong một context cụ thể**. Muốn thêm một luật nghiệp vụ, thường bắt đầu từ **bean policy**. Muốn đổi cơ chế expression dùng chung, mới cấu hình handler hoặc các thành phần mở rộng chuyên dụng. Muốn quyết định phân quyền hoàn toàn bằng Java, cân nhắc `AuthorizationManager`.

## Tài liệu chính thức

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — JavaDoc DefaultMethodSecurityExpressionHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html)
- [Spring Security — JavaDoc AbstractSecurityExpressionHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/AbstractSecurityExpressionHandler.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
