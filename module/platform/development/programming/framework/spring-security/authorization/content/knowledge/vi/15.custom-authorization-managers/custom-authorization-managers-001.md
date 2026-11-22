# Chọn AuthorizationManager khi quy tắc dựng sẵn không đủ

## 1. Tình huống và câu hỏi thiết kế

Spring Security có sẵn các cách viết quy tắc phân quyền phổ biến:

- `permitAll()`, `denyAll()`, `authenticated()`: mở, chặn hoặc yêu cầu xác thực.
- `hasAuthority("DOC_READ")`, `hasRole("ADMIN")`: kiểm tra quyền nằm trong `Authentication`.
- `requestMatchers(...)`: gắn chính sách với nhóm HTTP request.
- `@PreAuthorize("...")`, `@PostAuthorize("...")`: kiểm tra ở ranh giới phương thức.
- `RoleHierarchy`, `PermissionEvaluator`, bean gọi qua SpEL: mở rộng những phép kiểm tra phổ biến.

Những lựa chọn ấy thường đã đủ. Nhưng một số câu hỏi thực tế là:

> Người dùng có quyền `DOC_READ`, đang thuộc tenant A, yêu cầu tài liệu 42. Tài liệu 42 có thuộc tenant A, chưa bị khóa, người dùng có quyền chia sẻ hoặc là chủ sở hữu, và chính sách hiện tại có cho phép hành động không?

Phép kiểm tra một authority không thể tự biết chủ sở hữu hay trạng thái tài liệu. Ghép quá nhiều biểu thức SpEL trực tiếp vào cấu hình cũng làm chính sách khó đọc và khó kiểm thử. Trong trường hợp này, ta có thể viết logic Java rồi đưa nó vào **`AuthorizationManager<T>`**. Đây là interface để Spring Security hỏi một component rằng một `Authentication` có được phép truy cập đối tượng `T` hay không.

**Bài học này tập trung vào quyết định chọn `AuthorizationManager` khi quy tắc dựng sẵn không đủ**, bao gồm lựa chọn thay thế, cách định nghĩa manager đúng loại đối tượng, ghép manager sẵn có với policy riêng, cách gắn vào HTTP/method security, fail-closed, kiểm thử và vận hành.

Kết luận cần hướng tới không phải “cứ có nghiệp vụ tùy biến thì tự viết manager”. Chỉ chọn manager tùy biến **khi lợi ích về mô hình chính sách, tái sử dụng và khả năng kiểm thử rõ ràng hơn các cơ chế đơn giản**.

## 2. `AuthorizationManager` nằm ở đâu?

Trong Spring Security hiện đại, `AuthorizationManager` là lớp trừu tượng cho một quyết định phân quyền. Với ứng dụng Servlet:

```text
HTTP request
  |
  v
SecurityFilterChain
  |
  v
Authentication filters -> SecurityContext / Authentication
  |
  v
AuthorizationFilter
  |
  v
RequestMatcher chọn rule tương ứng
  |
  v
AuthorizationManager<RequestAuthorizationContext>
  |
  +-- GRANT -> cho request đi tiếp
  |
  +-- DENY  -> AccessDeniedException -> phản hồi theo exception handling
```

Với method security:

```text
Caller -> Spring AOP proxy của service
            |
            v
 AuthorizationManagerBeforeMethodInterceptor
            |
            v
 AuthorizationManager<MethodInvocation>
            |
        GRANT / DENY
            |
            v
       Target method (nếu được phép)
```

Cả hai ngữ cảnh đều dùng mô hình `AuthorizationManager`, nhưng **kiểu đầu vào khác nhau**:

| Điểm thực thi | Kiểu manager | Dữ liệu được cung cấp |
| --- | --- | --- |
| HTTP Servlet `authorizeHttpRequests` | `AuthorizationManager<RequestAuthorizationContext>` | `HttpServletRequest`, biến đường dẫn được matcher trích xuất |
| Trước lời gọi service | `AuthorizationManager<MethodInvocation>` | Target, method, các tham số |
| Sau lời gọi service | `AuthorizationManager<MethodInvocationResult>` | Method invocation cùng kết quả trả về |
| Messaging hoặc Reactive | Các kiểu context khác tương ứng | Phụ thuộc integration và runtime |

**Không dùng nhầm** `AuthorizationManager<RequestAuthorizationContext>` với `AuthorizationManager<MethodInvocation>`. Cùng interface nhưng tham số `T` quyết định manager có thể đọc thông tin gì và được gắn ở đâu.

### Vai trò và ranh giới

`AuthorizationManager` quyết định **allow/deny**. Nó không tự đăng nhập người dùng, không tự chạy SQL trong transaction, không tự tạo AOP proxy, không thay thế quy tắc hợp lệ dữ liệu và không tự áp dụng mọi nơi chỉ vì có annotation `@Component`.

Ở web, `AuthorizationFilter` gọi manager qua rule `.access(...)`. Ở method, một interceptor/advisor thích hợp gọi manager khi lời gọi đi qua Spring proxy.

## 3. Khi nào các quy tắc dựng sẵn vẫn là đáp án tốt hơn?

Trước khi tự viết manager, đặt câu hỏi: “Quy tắc thực sự dựa vào dữ liệu gì?”

| Nhu cầu | Lựa chọn ưu tiên | Có cần custom manager? |
| --- | --- | --- |
| API công khai hoặc bị chặn hoàn toàn | `permitAll` / `denyAll` | Không |
| Đăng nhập mới được truy cập | `authenticated` | Không |
| Cần đúng authority `INVOICE_READ` | `hasAuthority` | Không |
| ADMIN được xem mọi endpoint trong nhóm | `hasRole` + matchers | Thường không |
| Role cấp trên bao hàm role cấp dưới | `RoleHierarchy` | Thường không |
| Cần cả hai quyền `APPROVE` và `FINANCE` | `AuthorizationManagers.allOf(...)` hoặc cấu hình dựng sẵn tương ứng | Thường không |
| Chỉ một trong hai nhóm được truy cập | `AuthorizationManagers.anyOf(...)` | Thường không |
| Method cần kiểm tra owner đơn giản | `@PreAuthorize("@policy.canRead(authentication,#p0)")` | Có thể không |
| Đã có domain permission theo `hasPermission` | `PermissionEvaluator` | Có thể không |
| Quy tắc phối hợp tenant, owner, trạng thái, ngoại lệ, nhiều nguồn dữ liệu | Java policy hoặc `AuthorizationManager` riêng | Có thể phù hợp |
| Phải dùng cùng engine phân quyền tùy chỉnh cho nhiều HTTP route | Custom `AuthorizationManager<RequestAuthorizationContext>` | Phù hợp |
| Cần chính sách Java cho service method với pointcut riêng | `AuthorizationManager<MethodInvocation>` và advisor | Phù hợp |
| Ủy quyền quyết định cho policy engine/PDP bên ngoài | Custom manager với timeout, audit, fail-closed | Phù hợp, cần thiết kế vận hành |
| Chỉ cần validate body, số tiền, định dạng email | Bean validation/business validation | Không nên biến lỗi đầu vào thành quyền |
| Cần phân biệt mã HTTP 400/409/422 | Validation/exception handling ở web/application | Không phải trách nhiệm duy nhất của manager |

**Thứ tự cân nhắc thực tế:**

1. Quy tắc dựng sẵn và các manager đã có.
2. Ghép manager bằng `allOf`/`anyOf` hoặc dùng hierarchy.
3. Chuyển nghiệp vụ vào bean policy Java và gọi từ `@PreAuthorize`, nếu chỉ có một vài điểm gắn.
4. Tạo custom `AuthorizationManager<T>` khi cần điểm nối chính thức, nhiều nơi dùng, policy phức tạp hoặc muốn tách hẳn expression.
5. Thay đổi framework advisor/`AuthorizationManagerFactory` khi cần **chính sách mang tính hạ tầng**, không chỉ một rule nghiệp vụ.

Không có tiêu chí “biểu thức dài trên 100 ký tự thì phải đổi sang manager”. Quyết định dựa vào phạm vi, dữ liệu đầu vào, khả năng kiểm thử và vòng đời thay đổi của chính sách.

## 4. Hợp đồng của `AuthorizationManager<T>`

Spring Security 6.5+ và 7.x cung cấp API trung tâm:

```java
AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        T object);
```

`Authentication` do `Supplier` cung cấp; `T` là đối tượng cần kiểm tra. `AuthorizationResult` cho biết quyết định thông qua `isGranted()`. Một cách trả kết quả phổ biến là `new AuthorizationDecision(true)` hoặc `new AuthorizationDecision(false)`.

Ví dụ **đoạn tích hợp** minh họa một manager chỉ kiểm tra authority, không cần đọc HTTP request:

```java
public final class DocumentReadManager<T>
        implements AuthorizationManager<T> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            T context) {
        Authentication auth = authentication.get();

        boolean allowed = auth != null
                && auth.isAuthenticated()
                && auth.getAuthorities().stream()
                    .anyMatch(a -> "DOC_READ".equals(a.getAuthority()));

        return new AuthorizationDecision(allowed);
    }
}
```

Để đoạn code biên dịch trong ứng dụng Spring Security tương ứng, cần imports:

```java
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
```

Đoạn này **cố ý đơn giản để chỉ rõ hợp đồng**; trong ứng dụng thật, bài toán chỉ kiểm tra `DOC_READ` nên dùng `AuthorityAuthorizationManager.hasAuthority("DOC_READ")`. Việc tự viết class ở đây là thừa.

### `authorize`, `check`, `verify` và kết quả không quyết định

- `authorize(...)` là API nên dùng trong mã mới. Spring Security 6.5 đánh dấu `check(...)` deprecated; tránh viết integration mới chỉ override `check`.
- `verify(...)` dùng quyết định của manager và báo lỗi khi từ chối, thường bằng `AccessDeniedException`.
- `AuthorizationResult.isGranted()` phân biệt cho phép với từ chối.
- Một số manager có thể trả về `null` để **abstain**, tức không đưa ra quyết định. Đây là hợp đồng có chủ đích, không phải lối mặc định phù hợp cho mọi rule.
- Khi policy đã xác định mình có trách nhiệm kiểm tra route/method đó, các lỗi parse ID, thiếu dữ liệu, tenant không khớp, PDP không sẵn sàng nên được **deny tường minh** hoặc chuyển thành lỗi vận hành đã quy định. Không trả `null` cho những trường hợp chỉ vì chưa viết đủ xử lý.

`AuthorizationManager` là functional interface nên có thể dùng lambda:

```java
AuthorizationManager<RequestAuthorizationContext> manager =
        (authentication, context) -> {
            boolean allowed = /* policy kiểm tra ở đây */;
            return new AuthorizationDecision(allowed);
        };
```

Đoạn trên chỉ minh họa chữ ký; dấu `/* policy kiểm tra ở đây */` không phải boolean expression chạy độc lập. Ở ví dụ hoàn chỉnh mục 8, chúng ta triển khai đầy đủ.

### Lợi ích của `Supplier<Authentication>`

Spring Security có thể trì hoãn việc lấy `Authentication`. Manager đơn giản như `permitAll` không nhất thiết gọi `authentication.get()`. Custom manager chỉ nên đọc authentication khi chính sách cần nó. Đừng giả định supplier lúc nào cũng trả principal dạng `UserDetails`: hệ thống JWT có thể có `JwtAuthenticationToken` hoặc kiểu xác thực khác; dựa vào contract ổn định như `Authentication#getName`, authorities và các claim được kiểm tra đúng cách.

## 5. Chọn ngữ cảnh phù hợp trước khi viết policy

### 5.1. Ở tầng HTTP

HTTP manager nhận `RequestAuthorizationContext`, có:

- `getRequest()`: `HttpServletRequest`.
- `getVariables()`: các biến path được request matcher trích xuất, ví dụ `id` từ mẫu `/documents/{id}` khi matcher hỗ trợ.

Nó phù hợp với chính sách cần method HTTP, path, IP, header, principal hoặc quyền route-level. Nhưng cần lưu ý: **header và query/body từ client không tự là dữ liệu đáng tin** để khẳng định người dùng sở hữu tài nguyên. Với owner/tenant, hãy đối chiếu repository hoặc policy service phía server.

Không nên parse JSON body từ `HttpServletRequest` trong authorization filter chỉ để ra quyết định, vì dễ gặp stream đã đọc, kích thước payload, encoding và duplicate reads. Nếu chính sách chủ yếu dựa trên DTO đã được validate hoặc domain object tải từ DB, method security/application service thường có ngữ cảnh tốt hơn.

### 5.2. Ở tầng method

Method manager nhận `MethodInvocation`: `getMethod()`, `getArguments()`, `getThis()`, v.v. Có thể xét tham số đã được Java bind/validate và quyết định ở ranh giới service. Để manager được chạy, cần **method interceptor/advisor hoặc cấu hình annotation tương ứng**, và lời gọi phải đi qua Spring AOP proxy.

Đối với chính sách phụ thuộc kết quả trả về, method-security sau lời gọi dùng `MethodInvocationResult`. Không bảo vệ thao tác ghi bằng cách duy nhất kiểm tra sau khi side effect đã xảy ra.

### 5.3. Chia sẻ một policy, nhiều adapter

Nếu cùng quy tắc “user X được xem tài liệu Y trong tenant Z” cần ở HTTP **và** service, hãy tách nghiệp vụ vào một Java service thuần:

```text
HTTP AuthorizationManager<RequestAuthorizationContext>
                |
                v
       DocumentAccessPolicy
                ^
                |
Method AuthorizationManager<MethodInvocation>
```

Hai manager chịu trách nhiệm **trích xuất thông tin từ context** và chuyển tới `DocumentAccessPolicy`. Policy dùng dữ liệu xác thực và repository đáng tin cậy. Không sao chép hai thuật toán quyền có thể bị lệch; cũng không ép mọi adapter dùng chung một `AuthorizationManager<Object>` rồi `instanceof` rất nhiều context.

## 6. Khi nào phải ghép các manager có sẵn?

Spring Security cung cấp bộ tổ hợp `AuthorizationManagers`, ví dụ:

```java
AuthorizationManagers.allOf(
    AuthorityAuthorizationManager.hasAuthority("DOC_READ"),
    documentOwnerAuthorizationManager
)
```

Ý nghĩa chính sách mong muốn: **có authority đọc VÀ thỏa điều kiện owner**. Với lựa chọn OR:

```java
AuthorizationManagers.anyOf(
    AuthorityAuthorizationManager.hasRole("SUPPORT"),
    documentOwnerAuthorizationManager
)
```

Nghĩa là nhóm SUPPORT được phép theo rule riêng, hoặc người dùng là owner. **Cảnh báo:** cho SUPPORT truy cập tài liệu của mọi tenant là một quyết định bảo mật nhạy cảm; phải có yêu cầu nghiệp vụ rõ ràng, audit, và test cho tenant khác.

Tổ hợp giúp tái sử dụng phần đơn giản thay vì tự viết lại chúng trong một custom manager. Khi manager có thể `abstain`, phải hiểu rõ cách bộ tổ hợp xử lý trường hợp không có quyết định và kiểm thử các tổ hợp allow/deny/abstain. **Đừng đặt rule cần thiết ở nhánh OR mà một nhánh khác có thể vô tình bỏ qua.**

### Rule ở matcher HTTP có thứ tự

`authorizeHttpRequests` duyệt các rule theo thứ tự khai báo; rule khớp trước có thể quyết định quyền cho request. Nếu đặt `anyRequest().permitAll()` quá sớm, rule chuyên biệt có thể không còn cơ hội được áp dụng.

Để hạn chế cấu hình lọt quyền, đặt rule cụ thể trước và một catch-all nghiêm ngặt:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Đây là **đoạn cấu hình tích hợp**, không phải file Java độc lập. `anyRequest().denyAll()` chỉ hợp lý nếu team đã liệt kê đầy đủ route cần truy cập; phải tính cả actuator, static resources, error/forward dispatches theo kiến trúc ứng dụng.

## 7. Mô hình hóa chính sách trước khi lập trình

Giả sử hệ thống tài liệu có các trường phía server: `documentId`, `tenantId`, `ownerId`, `status`; người dùng có `subjectId`, tenant được phép và authorities.

Yêu cầu nghiệp vụ:

> Cho phép đọc tài liệu khi caller đã xác thực, có `DOC_READ`, tài liệu tồn tại, cùng tenant, trạng thái cho phép đọc và caller là owner hoặc là người được chia sẻ; mọi trường hợp khác từ chối.

Tách các điều kiện:

```text
ALLOW =
    authenticated
    AND has(DOC_READ)
    AND document_exists
    AND tenant_matches
    AND readable_state
    AND (is_owner OR has_share_grant)
```

Cần quyết định thêm:

- Quyền ngoại lệ dành cho admin/support có áp dụng xuyên tenant không?
- Tài liệu đã xóa, khóa hoặc tạm dừng có phải deny?
- ID không tồn tại và ID có nhưng không có quyền có cần trả ra phản hồi giống nhau để tránh enumeration?
- Nếu repository lỗi/timeout, ta fail closed thế nào?
- Kết quả quyền có thể cache bao lâu; revocation có hiệu lực khi nào?
- Nếu vừa kiểm tra vừa ghi tài liệu, quyền và trạng thái có thể thay đổi giữa hai bước; dùng transaction/locking/version sao cho nhất quán?
- Audit log cần lưu điều gì để giải thích quyết định mà không lộ dữ liệu nhạy cảm?

Trả lời các câu hỏi ấy trước khi chọn implementation giúp tránh nhét policy không đầy đủ vào một lambda vài dòng.

## 8. Ví dụ Spring Boot 3.5.16, Java 17: HTTP AuthorizationManager tùy chỉnh

Ví dụ **có thể biên dịch và chạy trong một dự án Maven**. Để bài tập tự chạy mà không cần DB, “repository dữ liệu” được thay bằng `Map<Long, String>` bất biến đặt phía server: tài liệu `42` thuộc `alice`, tài liệu `7` thuộc `bob`.

Policy của demo: caller phải có authority `DOC_READ` **và** là owner của tài liệu được yêu cầu. Ta dùng manager sẵn có cho authority, manager riêng cho owner, rồi ghép bằng `allOf`.

**Lưu ý phiên bản:** Spring Boot `3.5.16` là phiên bản đã phát hành, sử dụng Spring Security 6.x, phù hợp để minh họa API. Dòng Boot 3.5 đã kết thúc hỗ trợ OSS; với dự án production cần chọn nhánh Spring Boot/Security còn được hỗ trợ và đối chiếu API trước khi triển khai. Ứng dụng ví dụ dùng HTTP Basic với mật khẩu `{noop}` **chỉ phục vụ bài học**, không dùng làm cơ chế bảo mật thực tế.

### 8.1. Cấu trúc

```text
custom-manager-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/
    │       └── CustomManagerApplication.java
    └── test/
        └── java/demo/
            └── DocumentAuthorizationTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>custom-manager-demo</artifactId>
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

### 8.3. `src/main/java/demo/CustomManagerApplication.java`

```java
package demo;

import java.util.Map;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CustomManagerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomManagerApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, DocumentOwnerAuthorizationManager owner)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/documents/{id}")
                .access(AuthorizationManagers.allOf(
                    AuthorityAuthorizationManager.hasAuthority("DOC_READ"),
                    owner))
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}demo")
                .authorities("DOC_READ")
                .build(),
            User.withUsername("bob")
                .password("{noop}demo")
                .authorities("DOC_READ")
                .build(),
            User.withUsername("charlie")
                .password("{noop}demo")
                .authorities("OTHER")
                .build()
        );
    }
}

@Component
final class DocumentOwnerAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    // Dữ liệu server mô phỏng; production dùng repository đáng tin cậy.
    private final Map<Long, String> owners =
            Map.of(42L, "alice", 7L, "bob");

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authenticationSupplier,
            RequestAuthorizationContext context) {

        String rawId = context.getVariables().get("id");
        if (rawId == null || !rawId.matches("[1-9][0-9]*")) {
            return new AuthorizationDecision(false);
        }

        final long documentId;
        try {
            documentId = Long.parseLong(rawId);
        } catch (NumberFormatException invalidOrOverflow) {
            return new AuthorizationDecision(false);
        }

        String owner = owners.get(documentId);
        if (owner == null) {
            return new AuthorizationDecision(false);
        }

        Authentication auth = authenticationSupplier.get();
        boolean granted = auth != null
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)
                && owner.equals(auth.getName());

        return new AuthorizationDecision(granted);
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    @GetMapping("/{id}")
    String read(@PathVariable long id) {
        return "document-" + id;
    }
}
```

**Phân tích mã:**

1. `SecurityFilterChain` áp dụng rule cho GET `/api/documents/{id}`. Rule này ghép `hasAuthority("DOC_READ")` và `DocumentOwnerAuthorizationManager`. Các HTTP request khác bị `denyAll` trong demo.
2. `RequestAuthorizationContext.getVariables().get("id")` nhận biến path do matcher hỗ trợ trích xuất. Nếu không có/không phải số nguyên dương/overflow, manager trả deny.
3. `owners` là dữ liệu phía server; caller không thể tự khai mình là owner bằng cách thêm header `X-Owner`.
4. Manager gọi `authenticationSupplier.get()` khi cần xác minh identity, kiểm tra anonymous và so sánh với chủ sở hữu.
5. `new AuthorizationDecision(false)` thể hiện fail-closed: không tồn tại ID hoặc thiếu quyền đều không được cấp phép.
6. Controller **không tự kiểm tra quyền** vì request phải qua filter chain. Trong production, tầng service vẫn nên có kiểm tra quyền domain khi nó có thể được gọi từ những entry point khác như batch jobs, events hoặc messaging.
7. `Map` và mật khẩu plaintext có `{noop}` cố ý dùng để demo dễ chạy. Production cần dữ liệu owner/tenant đáng tin cậy, password encoder phù hợp, HTTPS, audit và logic nghiệp vụ thực tế.

Cần lưu ý matcher có biến `{id}`; nếu đổi sang matcher không cung cấp path variables hoặc đổi tên `{id}` thành `{documentId}` mà không cập nhật manager, rule sẽ từ chối vì thiếu biến. Viết integration test cho cấu hình matcher thực tế.

### 8.4. Chạy ứng dụng

Máy có JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

```bash
mvn -q clean package
java -jar target/custom-manager-demo-1.0.0.jar
```

Trong terminal khác:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo \
  http://localhost:8080/api/documents/42

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo \
  http://localhost:8080/api/documents/7

curl -s -o /dev/null -w '%{http_code}\n' -u bob:demo \
  http://localhost:8080/api/documents/7

curl -s -o /dev/null -w '%{http_code}\n' -u charlie:demo \
  http://localhost:8080/api/documents/42
```

Kết quả HTTP status dự kiến cho bốn lệnh trên (mỗi lệnh in một dòng):

```text
200
403
200
403
```

GET được phép với `alice/42` trả body `document-42`, với `bob/7` trả `document-7`. `alice/7` bị deny vì không phải owner; `charlie/42` bị deny ngay ở phần kiểm tra authority `DOC_READ`.

Trường hợp không đăng nhập, mặc định HTTP Basic có thể trả `401 Unauthorized`. Với ứng dụng có session/login hoặc exception handler tùy chỉnh, mã HTTP cụ thể phụ thuộc cấu hình entry point và access-denied handling. Không dùng một bộ status code cứng duy nhất cho mọi hệ thống.

### 8.5. Kiểm thử tích hợp `MockMvc`

Tệp `src/test/java/demo/DocumentAuthorizationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerWithAuthorityCanRead() throws Exception {
        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("document-42"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readerCannotReadOtherOwnersDocument() throws Exception {
        mvc.perform(get("/api/documents/7"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "charlie", authorities = "OTHER")
    void ownerRuleCannotBypassAuthorityRule() throws Exception {
        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void secondOwnerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/7"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void unknownDocumentIsDenied() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
mvn -q test
```

Test dùng request thực tế qua `SecurityFilterChain`, kiểm tra cả authority lẫn owner, thay vì chỉ gọi trực tiếp `DocumentController.read(42)`. Gọi controller trực tiếp sẽ **bỏ qua request authorization filter**, vì manager gắn ở HTTP layer.

**Vì sao test “unknownDocument” trả 403?** Trong demo, policy trả deny khi ID không có trong `owners`. API production có thể muốn không tiết lộ tài nguyên tồn tại hay không, hoặc định nghĩa riêng chính sách trả `404`; điều này cần thống nhất giữa policy và exception handling, không tự đưa một ngoại lệ vào policy để lộ sự tồn tại.

## 9. Muốn gắn custom AuthorizationManager vào method security thì làm sao?

HTTP manager ở mục 8 chỉ bảo vệ HTTP request. Nếu cùng service có thể được gọi trực tiếp bởi job, listener hoặc service khác, cần boundary ở method.

Giả sử có:

```java
@Service
public class ApprovalService {
    public void approve(long documentId) {
        // Ghi trạng thái phê duyệt bằng repository của ứng dụng.
    }
}
```

Lựa chọn **ít phức tạp** nhất có thể vẫn là bean policy:

```java
@PreAuthorize("hasAuthority('DOC_APPROVE') and " +
              "@approvalPolicy.canApprove(authentication, #p0)")
public void approve(long documentId) {
    // ...
}
```

Đây là các **đoạn tích hợp**, không tự chạy vì `approvalPolicy` và repository thuộc ứng dụng. Chúng cho thấy khi chỉ một method có luật Java riêng, ta có thể tránh viết `AuthorizationManager<MethodInvocation>` mới.

Nếu cần **advisor Java áp dụng trên nhiều method** hoặc muốn thay thế cách tạo quyết định của annotation, có thể tạo manager kiểu `MethodInvocation`.

### 9.1. Custom method manager

```java
@Component
public final class ApprovalAuthorizationManager
        implements AuthorizationManager<MethodInvocation> {

    private final ApprovalPolicy policy;

    public ApprovalAuthorizationManager(ApprovalPolicy policy) {
        this.policy = policy;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            MethodInvocation invocation) {

        if (invocation.getArguments().length != 1
                || !(invocation.getArguments()[0] instanceof Long id)) {
            return new AuthorizationDecision(false);
        }

        Authentication auth = authentication.get();
        boolean granted = auth != null
                && auth.isAuthenticated()
                && policy.canApprove(auth, id);

        return new AuthorizationDecision(granted);
    }
}
```

Các kiểu cần import:

```java
import java.util.function.Supplier;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.stereotype.Component;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
```

`ApprovalPolicy` là một bean thuộc ứng dụng. Nó kiểm tra quyền từ dữ liệu phía server (tenant, owner, trạng thái, vai trò...) và trả boolean. Đoạn này là **mã minh họa tích hợp**, không tuyên bố chạy độc lập khi chưa triển khai `ApprovalPolicy`.

Điểm quan trọng: manager kiểm tra **tham số method** trong `MethodInvocation`, không parse lại HTTP request. Vì method tham số `long` nên reflection arguments sẽ boxing thành `Long`. Nếu chữ ký method hoặc thứ tự tham số thay đổi, cần cập nhật policy và test.

### 9.2. Gắn manager vào advisor có pointcut

```java
@Configuration
@EnableMethodSecurity
public class ApprovalMethodSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor approvalAdvisor(ApprovalAuthorizationManager manager) {
        AspectJExpressionPointcut pointcut =
                new AspectJExpressionPointcut();
        pointcut.setExpression(
                "execution(public * demo.ApprovalService.approve(..))");

        return new AuthorizationManagerBeforeMethodInterceptor(
                pointcut, manager);
    }
}
```

Imports chính:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Mã giả định package và class thật khớp `demo.ApprovalService`, được Spring quản lý, không `final` và gọi qua proxy. Method Security infrastructure phải được khởi tạo đúng; advisor này chỉ áp dụng cho pointcut đã chỉ ra.

**Chú ý khi ghép:** nếu cùng method có `@PreAuthorize` và advisor tùy chỉnh, có thể chạy **nhiều** kiểm tra. Đừng lặng lẽ thay “OR” thành “AND” hoặc ngược lại bằng thứ tự advisor. Xác định chính sách rõ ràng, test tất cả các nhánh. Nếu muốn **thay thế** các advisor `@PreAuthorize`/`@PostAuthorize` mặc định, Spring Security có cách dùng `@EnableMethodSecurity(prePostEnabled = false)` rồi đăng ký interceptors tương ứng, nhưng điều đó ảnh hưởng phạm vi method security của toàn ứng dụng; không dùng chỉ để sửa một method.

### 9.3. Vì sao không gắn HTTP manager trực tiếp vào method?

Vì `RequestAuthorizationContext` biết servlet request và biến path; `MethodInvocation` biết phương thức Java và tham số. Nếu cần dùng chung policy, trích ID/user từ mỗi loại context rồi gọi chung `ApprovalPolicy` hoặc `DocumentAccessPolicy`. Việc chia adapter là chủ ý để tránh coupling web/service và tránh bảo vệ được đường HTTP nhưng bỏ lọt scheduler.

## 10. Khi nào cần thay manager của framework ở mức hạ tầng?

Có sự khác biệt lớn giữa:

- **Policy nghiệp vụ:** “một tài liệu chỉ được người thuộc tenant và có quyền xem”.
- **Quy ước toàn hệ thống:** “mọi rule `hasRole` đều phải coi thêm role đặc biệt X là thỏa” hoặc “mọi pre-authorization phải đi qua một decision engine duy nhất”.

Với chính sách cấp phương thức chỉ ảnh hưởng một tập service, đặt custom advisor hoặc bean policy thường đủ. Với chính sách thay đổi cách framework tạo `AuthorizationManager` cho các expression/role, các phiên bản Spring Security mới cung cấp **`AuthorizationManagerFactory`** làm điểm tùy biến.

Trong Spring Security 7, tài liệu method security có ví dụ tạo `AuthorizationManagerFactory<MethodInvocation>` tùy chỉnh để điều chỉnh các manager mà `hasRole`/`hasAnyRole` tạo ra. Đó là đường đi phù hợp hơn việc sao chép toàn bộ framework interceptor để đổi một quy ước. Kiểm tra API và cách đăng ký theo **version đang dùng**, vì các factory và setter được khuyến nghị khác giữa Spring Security 6.x và 7.x.

Ví dụ mô tả mục tiêu (không phải Java chạy độc lập):

```text
Application policy convention
          |
          v
AuthorizationManagerFactory<MethodInvocation>
          |
          +-- hasRole("EDITOR") -> manager theo quy ước nội bộ
          +-- hasAnyRole(...)  -> manager theo quy ước nội bộ
          |
          v
Method security annotations / advisors
```

Không dùng `AuthorizationManagerFactory` chỉ để xử lý “owner của tài liệu 42” vì như vậy đẩy một rule nghiệp vụ vào hạ tầng toàn cục.

## 11. Chính sách bất biến và dữ liệu động: tránh lỗi TOCTOU

Custom manager thường truy vấn database: `policy.canRead(authentication, docId)`. Đó là một phép kiểm tra tại **một thời điểm**.

Với lệnh **đọc**, kiểm tra có thể được gắn ở HTTP hoặc service, nhưng cần tránh rò dữ liệu trước khi kiểm tra. Với lệnh **ghi**, nếu manager kiểm tra owner/state rồi transaction ghi chạy sau, tài nguyên có thể đổi owner hoặc state trong khoảng giữa (time-of-check/time-of-use).

Ví dụ:

```text
T1: AuthorizationManager đọc owner = alice -> GRANT
T2: Admin chuyển owner sang bob
T3: Service của alice ghi cập nhật -> có thể vượt quá quyền hiện hành
```

Cách xử lý phụ thuộc consistency contract:

- Kiểm tra quyền và trạng thái nhạy cảm bên trong transaction nghiệp vụ, với locking/optimistic version khi cần.
- Bảo đảm repository chỉ sửa bản ghi thuộc tenant/owner đúng điều kiện (conditional update) hoặc xác minh version.
- Không coi `@Transactional` tự động làm hai truy vấn trước/sau tuyệt đối không bị race; transaction isolation và locking phải được lựa chọn.
- Với hệ thống phân tán/PDP từ xa, định nghĩa độ tươi quyền, token lifetime, cache TTL, invalidation và cơ chế bù trừ khi không thể có transaction chung.

`AuthorizationManager` giúp đưa ra quyết định, còn **tính nguyên tử và nhất quán dữ liệu** vẫn thuộc application/transaction/storage design.

## 12. Khi nguồn quyết định ở dịch vụ ngoài

Một số hệ thống dùng policy engine độc lập (ví dụ OPA, dịch vụ RBAC/ABAC nội bộ). Custom manager đóng vai trò adapter:

```text
Spring Security interceptor
  -> Custom AuthorizationManager
      -> chuẩn hóa subject + resource + action + tenant
      -> gọi PDP/authorization service
      -> kiểm tra response/version/signature nếu contract yêu cầu
      -> trả GRANT hoặc DENY
```

Các nguyên tắc chính:

- Chỉ gửi identity/claims và thông tin tài nguyên cần thiết; tránh truyền token thô, dữ liệu cá nhân dư thừa.
- Deadline/timeout đủ chặt, giới hạn concurrency và connection pool để authorization không trở thành điểm nghẽn.
- Quyết định **fail-closed** nếu dịch vụ quyền không xác nhận được chính sách. Nếu ứng dụng chọn trả `503` thay vì `403` trong tình huống policy service hỏng, cần thiết kế exception handling để phân biệt lỗi hệ thống với deny; không tự cấp quyền khi timeout.
- Định nghĩa cache key bao gồm subject, tenant, resource, action, version policy và những thuộc tính ảnh hưởng quyết định. TTL phải phù hợp thời gian thu hồi quyền.
- Audit allow/deny, latency, nguyên nhân hệ thống, policy version bằng dữ liệu tối thiểu. Không log secret hoặc full JWT.
- Test circuit-breaker, retry có giới hạn, các trường hợp lỗi mạng, parse JSON sai, policy thay đổi và phản hồi chậm.

Một manager có thể gọi PDP ngoài; nó **không nên tự tạo tài nguyên, thay đổi ACL, cấp role hoặc sửa database** chỉ để ra quyết định. Logic quyết định nên tránh side effect và giữ tính lặp lại được với cùng đầu vào/trạng thái policy.

## 13. Những lỗi thường gặp khi tự viết AuthorizationManager

### Lỗi 1: dùng custom manager cho phép kiểm tra một authority

```java
boolean allow = auth.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("DOC_READ"));
```

Nếu chỉ có điều kiện này, dùng `AuthorityAuthorizationManager.hasAuthority("DOC_READ")`. Custom class chỉ tăng số dòng và nơi phải kiểm thử.

### Lỗi 2: không gắn manager ở đâu

```java
@Component
class CustomAuthz implements AuthorizationManager<RequestAuthorizationContext> {
    // ...
}
```

Đăng ký bean **không có nghĩa manager tự động bảo vệ tất cả request**. Phải chỉ rõ `.access(customAuthz)` ở rule phù hợp; tương tự method manager cần advisor/interceptor.

### Lỗi 3: cho phép khi dữ liệu không đủ

```java
if (document == null) {
    return new AuthorizationDecision(true); // Sai với chính sách cần tài liệu.
}
```

Khi owner, tenant hoặc policy chưa xác định, nên deny theo hợp đồng. Không coi lỗi parse ID, thiếu principal hoặc repository timeout như lý do cho qua.

### Lỗi 4: nhầm `abstain` với deny

`null` nghĩa là không ra quyết định, không đồng nghĩa deny. Với adapter đã gắn trực tiếp cho endpoint nhạy cảm, trả `AuthorizationDecision(false)` rõ ràng khi điều kiện không đạt. Nếu chủ đích dùng abstain trong tổ hợp, phải kiểm thử hành vi của manager bao ngoài và fallback.

### Lỗi 5: so sánh owner với header client

```java
String owner = request.getHeader("X-Owner"); // Client có thể tự đặt.
```

Một người dùng ác ý có thể gửi giá trị tùy ý. Chỉ dùng identity/tenant đã xác thực và owner lấy từ dữ liệu đáng tin cậy.

### Lỗi 6: bỏ qua tenant

Nếu `documentId` chỉ duy nhất trong một tenant, truy vấn `findById(id)` không kèm tenant có thể cấp quyền xuyên tenant, nhất là khi có ID trùng. Policy phải coi tenant là phần của resource identity hoặc scope truy vấn.

### Lỗi 7: tự đọc body request trong filter để kiểm tra field

Đọc stream body trong authorization manager có thể khiến controller không còn dữ liệu, gây lỗi deserialize, tốn RAM hoặc bị abuse bằng payload lớn. Với dữ liệu domain phức tạp, method security và validation tại application layer phù hợp hơn.

### Lỗi 8: dùng `Authentication.isAuthenticated()` duy nhất

Anonymous authentication token có thể có `isAuthenticated() == true`. Phải hiểu semantics authentication và không biến “có context” thành “có quyền”. Dùng authority/role và kiểm tra anonymous/fullyAuthenticated theo yêu cầu.

### Lỗi 9: quên proxy ở method security

Annotation hoặc custom advisor chỉ có hiệu lực khi lời gọi đi qua Spring proxy. `new Service()` hoặc `this.securedMethod()` có thể bypass security advice trong proxy mode. Giải pháp thường là inject bean và tách ranh giới service rõ ràng.

### Lỗi 10: dùng cùng manager cho mọi request mà không giới hạn matcher

`anyRequest().access(manager)` có thể bắt cả static assets, health checks, login callbacks, actuator và error dispatch. Nếu policy chỉ dành cho tài liệu, giới hạn `requestMatchers("/api/documents/**")` và xác định fallback. Test route coverage.

### Lỗi 11: test bằng cách gọi trực tiếp manager rồi cho rằng endpoint đã an toàn

Unit test manager chứng minh thuật toán. Integration test qua `MockMvc` hoặc method proxy mới chứng minh **config/pointcut/bean wiring** thực sự kích hoạt manager. Cần cả hai với policy nhạy cảm.

### Lỗi 12: trộn authorization với validation/business conflict

Nếu invoice đã thanh toán thì sửa nữa gây xung đột trạng thái, nhiều hệ thống chọn 409 thay vì 403. Phân biệt rõ “người này không có quyền” với “thao tác không hợp lệ theo trạng thái”. Có thể một số trạng thái thuộc chính sách phân quyền nhưng vẫn cần API contract về lỗi.

## 14. Kiểm thử theo ma trận quyết định

Custom manager phải được kiểm thử hai cấp.

**Cấp 1 — Unit test policy:** gọi manager trực tiếp với `Authentication`/`RequestAuthorizationContext` giả lập, dùng repository giả; thử allow, deny, null/anonymous, resource không tồn tại, tenant mismatch, ID sai, PDP timeout, trường hợp khó về dữ liệu.

**Cấp 2 — Integration test wiring:** dùng HTTP request thật qua Spring Security filter chain hoặc gọi Spring bean method qua AOP proxy; kiểm tra đúng route/pointcut, exception/HTTP status, các advisor ghép, thông tin principal/tenant.

Ma trận tối thiểu cho ví dụ tài liệu:

| Authentication | Authority | Resource | Điều kiện khác | Kết quả |
| --- | --- | --- | --- | --- |
| alice | DOC_READ | Doc 42, owner alice | hợp lệ | ALLOW |
| alice | DOC_READ | Doc 7, owner bob | hợp lệ | DENY |
| alice | OTHER | Doc 42, owner alice | hợp lệ | DENY |
| anonymous | Không có | Doc 42 | không xác thực | DENY |
| alice | DOC_READ | Doc 999 không tồn tại | không tìm được owner | DENY |
| alice | DOC_READ | ID không parse được | dữ liệu path lỗi | DENY |
| alice tenant A | DOC_READ | Doc tenant B | owner có thể khớp | DENY |
| alice | DOC_READ | Doc 42 | PDP/repository timeout | DENY hoặc lỗi hệ thống được quy định, tuyệt đối không ALLOW |
| admin | ADMIN | Doc tenant B | nhánh ngoại lệ | Chỉ ALLOW nếu chính sách cho phép rõ ràng |

Đặc biệt cần một test **negative-path**: xóa rule `.access(ownerManager)` trong môi trường kiểm thử và xem test owner mismatch có fail không. Ý tưởng này giúp chắc chắn test kiểm tra việc manager được kết nối, không chỉ kiểm tra endpoint luôn trả 200.

Cần test update/delete riêng vì quyền `DOC_READ` không được mặc nhiên cho phép `DOC_WRITE`. Với cùng path nhưng khác HTTP method, cần matcher riêng theo `HttpMethod`.

## 15. Hiệu năng, giám sát và bảo trì

Vì manager có thể được gọi cho **mỗi request hoặc mỗi method invocation**, hãy đo chi phí:

- Chỉ gọi `authentication.get()` và repository khi thực sự cần; tránh đọc DB cho public route.
- Không thực hiện N+1 query khi kiểm tra danh sách trong vòng lặp nếu có thể batch.
- Đặt thời gian timeout rõ khi gọi PDP; ghi nhận tỷ lệ deny, lỗi backend, latency p95/p99.
- Cân nhắc cache với dữ liệu tenant + resource + action + policy version, không chỉ username.
- Tránh cache allow quá lâu khiến quyền đã bị thu hồi còn hiệu lực.
- Log decision ID/method/resource ở mức phù hợp, không log password, access token hay toàn bộ body.
- Khi policy thay đổi, version hóa và kiểm tra regression test cho quyền trước và sau.
- Duy trì danh sách matcher/advisor ứng với từng policy; tránh nhiều rule ẩn chồng nhau gây khó giải thích.
- Hạn chế quyền admin đặc biệt, có audit riêng cho override và luôn kiểm tra tenant nếu tổ chức yêu cầu.
- Với nhiều instance, cache/policy backend phải nhất quán trong giới hạn đã cam kết.

Một `AuthorizationManager` viết tốt thường là **adapter mỏng**: lấy context, ủy quyền cho domain policy, biến kết quả thành `AuthorizationResult`. Logic hàng trăm nhánh nên nằm trong những class nghiệp vụ có trách nhiệm rõ và unit test riêng.

## 16. Vấn đề phiên bản và cơ chế cũ

Spring Security 6/7 dùng `AuthorizationManager` thay cho những điểm tùy biến cũ như `AccessDecisionManager` và `AccessDecisionVoter` trong các flow authorization hiện đại. Khi gặp tài liệu cũ đề xuất viết `AccessDecisionVoter` hoặc mở rộng `GlobalMethodSecurityConfiguration`, cần so lại API theo phiên bản đang chạy.

Các điểm cần lưu ý:

- Spring Security 6.5 có `authorize(...)` và `AuthorizationResult`; `check(...)` đã deprecated. Viết implementation mới dựa trên `authorize`.
- `authorizeHttpRequests` dùng `AuthorizationFilter` và `AuthorizationManager`; cấu hình `authorizeRequests` cũ dựa trên cơ chế khác.
- `@EnableMethodSecurity` bật method security mới, phù hợp với `AuthorizationManager`. Spring Boot Starter Security riêng nó **không** bật method-level authorization.
- HTTP `AuthorizationManager<RequestAuthorizationContext>` và method `AuthorizationManager<MethodInvocation>` là hai adapter khác nhau.
- Spring Security 7 mở rộng hướng `AuthorizationManagerFactory` để tùy chỉnh cách tạo manager của các quy tắc dựng sẵn; cần đọc tài liệu đúng version trước khi copy code.
- Với hệ thống reactive, không dùng nguyên xi Servlet `HttpSecurity` / `RequestAuthorizationContext`: dùng reactive security DSL và các kiểu authorization phù hợp.

Đừng nâng cấp framework bằng cách chỉ thay package/import. Hãy chạy lại test về allow/deny, các rule tổ hợp, anonymous, matcher, authentication, transaction và exception handling.

## 17. Câu hỏi ôn tập

**1. Nếu chỉ muốn kiểm tra `DOC_READ`, có cần custom manager không?** Không. Dùng `hasAuthority("DOC_READ")`. Manager riêng chỉ cần khi có một phần chính sách không thể biểu đạt rõ bằng rule có sẵn hoặc cần adapter chung.

**2. Khi nào `@PreAuthorize("@policy.check(authentication,#p0)")` đủ?** Khi chính sách gắn vào một vài service method, không cần custom advisor/pointcut, và có thể dễ dàng gọi bean policy. Logic Java trong bean vẫn unit-test được.

**3. Manager custom có tự được chạy vì là `@Component` không?** Không. Phải gắn `.access(manager)` trong HTTP security hoặc tạo method advisor/interceptor tương ứng.

**4. Tại sao không viết một manager chung cho HTTP và method?** Vì kiểu context chứa dữ liệu khác nhau và có lifecycle khác. Chia sẻ **domain policy** và viết adapter mỏng cho từng loại.

**5. Có nên trả `null` khi không tìm thấy tài liệu?** Nếu manager chịu trách nhiệm bảo vệ resource ấy, thường **DENY tường minh**. `null` là abstain, chỉ dùng khi framework phối hợp quyết định đã được thiết kế cho tình huống đó.

**6. Custom manager có thay transaction không?** Không. Với ghi dữ liệu, phải kiểm tra consistency, concurrent changes và transaction riêng. Allow tại thời điểm T1 không đảm bảo dữ liệu còn nguyên tại T2.

**7. Manager có được gọi API chính sách bên ngoài không?** Có, nhưng cần timeout, fail-closed, audit, cache hợp lý và xử lý sự cố; không cho phép khi PDP không trả kết quả đáng tin.

**8. Vì sao test manager trực tiếp chưa đủ?** Nó không chứng minh request matcher, SecurityFilterChain, proxy hay advisor được kết nối. Cần integration test qua entry point thực.

## 18. Checklist chọn và triển khai

- [ ] Đã mô tả policy bằng điều kiện rõ ràng và thống nhất hành vi missing/deny/abstain.
- [ ] Đã thử `hasAuthority`/`hasRole`, matcher, `RoleHierarchy`, `AuthorizationManagers.allOf/anyOf`.
- [ ] Với method security, đã xét bean Java gọi từ `@PreAuthorize` trước khi tự viết advisor.
- [ ] Đã chọn đúng `AuthorizationManager<T>` cho HTTP, method hoặc context khác.
- [ ] Đã gắn manager đúng matcher/advisor; không chỉ tạo bean.
- [ ] Policy kiểm tra identity, tenant, resource từ dữ liệu tin cậy phía server, deny by default.
- [ ] Phân biệt lỗi quyền và lỗi dữ liệu/kinh doanh; HTTP status được định nghĩa trong API contract.
- [ ] Chính sách độc lập không tạo side effect; external PDP có timeout, fail-closed và giám sát.
- [ ] Có unit test quyết định và integration test chứng minh route/pointcut thật sự được bảo vệ.
- [ ] Đã kiểm tra proxy/self-invocation khi áp dụng cho method, và transaction/TOCTOU cho lệnh ghi.
- [ ] Đã xem phiên bản Spring Security đang dùng và tránh API legacy/deprecated không cần thiết.
- [ ] Quy tắc admin override, tenant isolation, audit và thay đổi quyền được kiểm thử như những use case riêng.

**Nguyên tắc ghi nhớ:** Chọn custom `AuthorizationManager` khi cần một **đơn vị quyết định phân quyền rõ ràng, có kiểu context đúng, tái sử dụng được và kiểm thử riêng**. Tiếp tục dùng các manager dựng sẵn cho kiểm tra đơn giản; đưa logic nghiệp vụ vào policy Java; rồi gắn manager ở đúng điểm HTTP/method để Spring Security thực sự áp dụng quyết định đó.

## Tài liệu tham khảo

- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security và custom AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — JavaDoc AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7 — Method Security và AuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html)
- [Spring Boot 3.5.16 release notes](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now)
