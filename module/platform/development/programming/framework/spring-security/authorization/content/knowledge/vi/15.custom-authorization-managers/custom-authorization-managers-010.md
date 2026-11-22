# AuthorizationManagerFactory và khả năng tùy biến ở dòng phiên bản hỗ trợ

## 1. Ý nghĩa và phạm vi phiên bản

Trong Spring Security, `AuthorizationManager<T>` là thành phần ra quyết định **GRANT/DENY** cho một hành động đang được bảo vệ, chẳng hạn HTTP request hoặc lời gọi phương thức Java. `AuthorizationManagerFactory<T>` là lớp trừu tượng **tạo các AuthorizationManager phổ biến** khi hệ thống xây dựng chính sách: `hasRole("ADMIN")`, `hasAuthority("document:read")`, `authenticated()`, `permitAll()` và những biến thể khác.

**Điều kiện phiên bản quan trọng:** API `org.springframework.security.authorization.AuthorizationManagerFactory` và implementation `DefaultAuthorizationManagerFactory` được giới thiệu từ **Spring Security 7.0** (Javadoc ghi `Since: 7.0`). Dự án Spring Security 6.x vẫn có `AuthorizationManager` và nhiều điểm mở rộng khác, nhưng không có sẵn factory này; không sao chép ví dụ 7.x vào nhánh 6.x rồi kỳ vọng biên dịch.

Nội dung hướng đến ứng dụng Spring Security 7.0+ dùng HTTP Servlet và method security, đồng thời nêu cách xử lý trên nhánh chưa hỗ trợ. Mục tiêu:

1. Phân biệt nhà máy **tạo manager** và manager **đánh giá quyền**.
2. Hiểu các phương thức factory, vai trò kiểu generic `T`.
3. Tùy chỉnh prefix role, role hierarchy, trust resolver và yêu cầu bổ sung.
4. Phân biệt factory dùng chung với factory áp dụng riêng cho web hoặc method security.
5. Nhận diện rủi ro thay đổi chính sách diện rộng và cách kiểm thử.
6. Biết khi nào dùng custom manager, `.access(...)` hoặc bean policy thay cho factory.

## 2. Factory tạo chính sách, manager thực hiện quyết định

Với Spring Security hiện đại, `AuthorizationManager<T>` có hợp đồng khái niệm:

```java
AuthorizationResult authorize(
    Supplier<? extends Authentication> authentication,
    T securedObject
);
```

Đây là chữ ký giản lược để giải thích. API thực có thể chứa các wildcard và nullability annotations khác theo bản patch. `authentication` giúp lấy người gọi khi cần; `securedObject` mô tả đối tượng đang được kiểm tra. Manager trả quyết định cho phép/từ chối, hoặc có thể abstain bằng `null` theo hợp đồng của API.

Ngược lại, factory có mục đích:

```java
AuthorizationManager<T> hasRole(String role);
AuthorizationManager<T> authenticated();
AuthorizationManager<T> permitAll();
```

Các phương thức trên là những ví dụ trong hợp đồng `AuthorizationManagerFactory<T>`: mỗi lời gọi **tạo một manager** có quy tắc tương ứng.

```text
Giai đoạn cấu hình:
  .requestMatchers("/reports/**").hasRole("READER")
                         |
                         v
         AuthorizationManagerFactory<T>
             .hasRole("READER")
                         |
                         v
            AuthorizationManager<T>

Khi request đến:
  Supplier<Authentication> + request context
                         |
                         v
         AuthorizationManager.authorize(...)
                         |
                         v
                    GRANT / DENY
```

Điều này phân biệt hai thời điểm. Factory không tự đăng nhập người dùng, không xác minh mật khẩu, không phải `AuthenticationManager` và không tự kiểm tra quyền sở hữu tài liệu. Quyền truy cập từng tài nguyên vẫn cần policy chuyên biệt và dữ liệu tin cậy.

## 3. Các phương thức phổ biến của AuthorizationManagerFactory

| Phương thức | Manager được tạo sẽ yêu cầu |
| --- | --- |
| `permitAll()` | Cho phép tất cả, không yêu cầu đọc Authentication |
| `denyAll()` | Từ chối tất cả |
| `anonymous()` | Chỉ cho anonymous |
| `authenticated()` | Người gọi đã xác thực theo trust resolver |
| `fullyAuthenticated()` | Xác thực đầy đủ, không chỉ remember-me |
| `rememberMe()` | Trạng thái remember-me |
| `hasRole("USER")` | Role USER, theo mặc định kiểm tra authority `ROLE_USER` |
| `hasAnyRole("USER", "ADMIN")` | Có ít nhất một role được nêu |
| `hasAllRoles("READER", "AUDITOR")` | Có đủ tất cả role được nêu |
| `hasAuthority("document:read")` | Authority chính xác `document:read` |
| `hasAnyAuthority("x", "y")` | Có ít nhất một authority |
| `hasAllAuthorities("x", "y")` | Có tất cả authority |

**Role và authority không đồng nghĩa.** `hasRole("ADMIN")` mặc định đòi `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` đòi chính xác chuỗi `ADMIN`. Thay `setRolePrefix("APP_")` sẽ ảnh hưởng quy tắc tạo từ `hasRole`, không biến `hasAuthority("document:read")` thành một role.

Từ 7.0, interface factory cung cấp **default implementations** cho các phương thức; factory tùy biến có thể override đúng một vài hành vi cần thiết. Tuy nhiên, khi override một phương thức, các phương thức khác **không tự nhiên nhận cùng chính sách mở rộng**: muốn quy tắc nhất quán phải chủ động cấu hình, dùng delegate hoặc role hierarchy rồi test.

## 4. Kiểu T xác định ngữ cảnh phân quyền

`AuthorizationManagerFactory<T>` là generic theo đối tượng cần kiểm tra:

- `AuthorizationManagerFactory<RequestAuthorizationContext>` dành cho các manager quyết định trên request của Servlet web authorization.
- `AuthorizationManagerFactory<MethodInvocation>` dành cho lời gọi Java method được Spring AOP intercept.
- Một bean factory khai báo generic `<T> AuthorizationManagerFactory<T>` có thể phục vụ các thành phần framework hỗ trợ dùng factory chung.

`RequestAuthorizationContext` cung cấp request, matcher variables; `MethodInvocation` cung cấp phương thức và đối số. Bản thân factory chưa kiểm tra chúng mà tạo `AuthorizationManager<T>` thích hợp.

```java
AuthorizationManager<RequestAuthorizationContext> webRule =
    webFactory.hasRole("ADMIN");

AuthorizationManager<MethodInvocation> methodRule =
    methodFactory.hasRole("ADMIN");
```

Đây là **hai đoạn minh họa trong ứng dụng** có biến `webFactory`/`methodFactory` đã được inject. Hai rule có cùng tên role nhưng có kiểu đầu vào khác nhau. Không ép một manager nhận `MethodInvocation` thành manager HTTP bằng cast; nếu cần cùng logic nghiệp vụ, chia sẻ một bean policy trả quyết định dựa trên `Authentication` và dữ liệu server.

## 5. DefaultAuthorizationManagerFactory và cấu hình dùng chung

Spring Security 7.x cung cấp `DefaultAuthorizationManagerFactory<T>`. Các điểm cấu hình chính:

- `setRolePrefix(String)` — chỉnh cách biến role thành authority.
- `setRoleHierarchy(RoleHierarchy)` — dùng quan hệ kế thừa role.
- `setTrustResolver(AuthenticationTrustResolver)` — điều chỉnh cách đánh giá anonymous, remember-me, fully authenticated.
- `setAdditionalAuthorization(AuthorizationManager<T>)` — thêm một điều kiện authorization vào một số loại rule do factory tạo.

Ví dụ tạo factory dùng chung với prefix khác mặc định:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;

@Configuration
public class AuthorizationFactoryConfiguration {

    @Bean
    public <T> AuthorizationManagerFactory<T> authorizationManagerFactory() {
        DefaultAuthorizationManagerFactory<T> factory =
            new DefaultAuthorizationManagerFactory<>();
        factory.setRolePrefix("APP_");
        return factory;
    }
}
```

Đây là **cấu hình trong Spring Security 7.x**, cần được đăng ký như Spring bean. Giả sử principal có authority `APP_ADMIN`, quy tắc `hasRole("ADMIN")` đi qua factory này có thể cho phép; principal chỉ có `ROLE_ADMIN` thì không đáp ứng prefix `APP_`.

**Không đổi prefix chỉ để chữa một HTTP 403.** Cần xem `GrantedAuthority` từ hệ thống authentication, cấu hình JWT converter/LDAP/database, role hierarchy, biểu thức Spring Security và những factory khác. Một ứng dụng có thể dùng `GrantedAuthorityDefaults` hoặc cơ chế role prefix khác; phải giữ cách map authority đồng bộ.

### Cấu hình RoleHierarchy

Nếu dự án đã công bố một `RoleHierarchy` bean, có thể truyền nó vào default factory:

```java
@Bean
public <T> AuthorizationManagerFactory<T> authorizationManagerFactory(
        RoleHierarchy hierarchy) {
    DefaultAuthorizationManagerFactory<T> factory =
        new DefaultAuthorizationManagerFactory<>();
    factory.setRoleHierarchy(hierarchy);
    return factory;
}
```

Đoạn này **thay thế** phương thức bean ví dụ trước, không khai báo đồng thời hai bean generic cùng tên. Import `RoleHierarchy` từ `org.springframework.security.access.hierarchicalroles.RoleHierarchy` và cung cấp bean hierarchy thực của dự án.

Ví dụ ý nghĩa một role hierarchy:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_READER
```

ADMIN có thể kế thừa quyền của READER theo hierarchy được cấu hình đúng. Thứ tự là ký pháp quan hệ kế thừa role, không phải thứ tự thực thi interceptor. Hãy kiểm tra cả đường kế thừa bắc cầu và quyền từng role; role hierarchy không tự chứng minh người dùng cùng tenant hoặc sở hữu tài nguyên.

## 6. Factory chuyên biệt cho HTTP request

Ví dụ một hệ thống muốn các endpoint dùng quy tắc `authenticated()` phải **vừa đăng nhập, vừa có role USER**. Factory chuyên biệt cho `RequestAuthorizationContext`:

```java
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class WebAuthorizationManagerFactory
        implements AuthorizationManagerFactory<RequestAuthorizationContext> {

    private final AuthorizationManagerFactory<RequestAuthorizationContext>
        delegate = new DefaultAuthorizationManagerFactory<>();

    @Override
    public AuthorizationManager<RequestAuthorizationContext> authenticated() {
        return AuthorizationManagers.allOf(
            this.delegate.authenticated(),
            this.delegate.hasRole("USER")
        );
    }
}
```

`AuthorizationManagers.allOf(...)` yêu cầu các thành phần đều cho phép. User chỉ có `ROLE_GUEST` nhưng đã authenticated sẽ bị từ chối bởi manager được tạo từ `authenticated()`. User có role USER nhưng chưa authenticated cũng không đáp ứng cả hai.

Cấu hình HTTP sử dụng những rule thông thường:

```java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/reports/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
```

Đoạn trên chỉ là **thành phần cấu hình**, cần import `HttpSecurity`, `SecurityFilterChain`, `Bean` và cấu hình xác thực phù hợp. Khi Spring Security 7.x dùng factory typed ở trên, `authenticated()` cho `/reports/**` có điều kiện USER bổ sung.

**Phạm vi override phải được đọc chính xác:**

- `permitAll()` không bị biến thành "phải có USER".
- `hasRole("ADMIN")` ở route khác không bị thay đổi bởi override `authenticated()`.
- `.access(customManager)` nhận một manager có sẵn, không nhất thiết được sinh qua factory.
- Nhiều `SecurityFilterChain` có quy tắc matching riêng; cần kiểm tra chain thực chạy.
- Một rule `hasAuthority("document:read")` không tự phải kèm USER nếu chỉ override `authenticated()`.

Nếu chỉ một URL cần cả ROLE_USER và xác thực, đưa điều kiện vào route đó có thể đơn giản và ít ảnh hưởng hơn việc thay đổi `authenticated()` ở mọi nơi.

## 7. Factory chuyên biệt cho method security

Khi dùng `@EnableMethodSecurity`, Spring Security 7.x có thể sử dụng factory typed `AuthorizationManagerFactory<MethodInvocation>` để tạo manager cho các biểu thức của method annotations.

Ví dụ muốn `ROLE_ADMIN` được **thay thế một role thông thường** khi method gọi `hasRole` hoặc `hasAnyRole`:

```java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;
import org.springframework.stereotype.Component;

@Component
public class MethodAuthorizationManagerFactory
        implements AuthorizationManagerFactory<MethodInvocation> {

    private final AuthorizationManagerFactory<MethodInvocation> delegate =
        new DefaultAuthorizationManagerFactory<>();

    @Override
    public AuthorizationManager<MethodInvocation> hasRole(String role) {
        return AuthorizationManagers.anyOf(
            this.delegate.hasRole(role),
            this.delegate.hasRole("ADMIN")
        );
    }

    @Override
    public AuthorizationManager<MethodInvocation>
            hasAnyRole(String... roles) {
        return AuthorizationManagers.anyOf(
            this.delegate.hasAnyRole(roles),
            this.delegate.hasRole("ADMIN")
        );
    }
}
```

`AuthorizationManagers.anyOf(...)` cho phép nếu **ít nhất một** nhánh cho phép. Với manager do factory này tạo từ `hasRole("READER")`, một principal có `ROLE_ADMIN` được cho phép ngay cả khi không có `ROLE_READER`.

Một service minh họa:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasRole('READER')")
    public String listReports() {
        return "reports";
    }
}
```

Bật method security tại cấu hình Spring:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Đây đều là **thành phần trong ứng dụng**. Việc gọi `listReports()` phải đi qua Spring proxy thì advice method security mới chạy theo chế độ proxy. Gọi `new ReportService()` trực tiếp trong unit test không kiểm tra tác động thực tế của factory.

**Giới hạn:** ví dụ override `hasRole` và `hasAnyRole`, không tự override `hasAllRoles`, `hasAuthority`, `hasAnyAuthority` hay rule khác. Nếu mục đích là kế thừa role cho ADMIN nhất quán, cân nhắc `RoleHierarchy`. Đừng suy luận rằng factory làm ADMIN vượt tất cả giới hạn owner, tenant hoặc ACL; quyền trên từng tài nguyên vẫn cần xác minh riêng.

## 8. Cấu hình generic và typed: chọn đường nào?

| Lựa chọn | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| `@Bean <T> AuthorizationManagerFactory<T>` | Công bố một factory chung cho các integration có hỗ trợ | Thay convention tổng quát, ví dụ prefix/hierarchy |
| `AuthorizationManagerFactory<RequestAuthorizationContext>` | Gắn với web Servlet request authorization | Override rule tạo từ `authorizeHttpRequests` |
| `AuthorizationManagerFactory<MethodInvocation>` | Gắn với method security | Override quy tắc tạo manager cho method annotation |
| `AuthorizationManager<RequestAuthorizationContext>` truyền vào `.access(...)` | Chọn một policy cụ thể tại một request matcher | Yêu cầu URL, HTTP method, path variable hoặc tài nguyên |
| `@PreAuthorize("@policy.canRead(authentication, #id)")` | Policy Java cho service method | Quyền theo user, tenant, tài liệu, ACL |
| `RoleHierarchy` | Mô hình kế thừa role | Thừa kế vai trò nhất quán hơn các nhánh OR rải rác |

Với bean typed và generic cùng tồn tại, phải kiểm tra Spring Security **thực sự sử dụng factory nào** ở từng điểm. Spring bean resolution có thể phụ thuộc cách khai báo generic, loại target và phiên bản; đừng chỉ dựa vào tên bean. Sự hiện diện của factory custom trong context không chứng minh mọi manager sử dụng nó.

Không dùng factory chỉ để đưa owner ID hoặc tenant từ request vào quyết định. HTTP path và method arguments là **dữ liệu có thể giả mạo**. Policy cần đọc owner/tenant/ACL từ nguồn server đã xác thực và ràng buộc truy vấn dữ liệu cho đúng.

## 9. setAdditionalAuthorization và yêu cầu xác thực bổ sung

Từ 7.x, `DefaultAuthorizationManagerFactory.setAdditionalAuthorization(AuthorizationManager<T>)` có thể thêm một yêu cầu authorization vào những manager được tạo từ:

- `hasRole`, `hasAnyRole`, `hasAllRoles`;
- `hasAuthority`, `hasAnyAuthority`, `hasAllAuthorities`;
- `authenticated`, `fullyAuthenticated`, `rememberMe`.

Điều kiện bổ sung được yêu cầu **cùng với** quy tắc gốc. Ví dụ, một manager từ `hasRole("READER")` còn có thể phải thỏa một kiểm tra MFA đáng tin cậy.

**Ngoại lệ API quan trọng:** theo Javadoc của default factory, `setAdditionalAuthorization` **không áp dụng** cho `anonymous()`, `permitAll()` hoặc `denyAll()`. Vì vậy không nói "bật additional authorization nghĩa là tất cả endpoint đều yêu cầu MFA". Phải xem các nhánh login, enrollment, recovery và những route mở cho anonymous.

Minh họa phần gắn manager có sẵn:

```java
DefaultAuthorizationManagerFactory<RequestAuthorizationContext> factory =
    new DefaultAuthorizationManagerFactory<>();

AuthorizationManager<RequestAuthorizationContext> mfaManager =
    /* policy MFA đã được hệ thống xác minh từ Authentication */;

factory.setAdditionalAuthorization(mfaManager);
```

Đoạn trên là **pseudocode Java về cách phối hợp**; phần `mfaManager` phải được ứng dụng cung cấp, không được copy nguyên dòng comment như biểu thức khởi tạo. Với Spring Security có tính năng MFA được hỗ trợ, đọc tài liệu `AuthorizationManagerFactories.multiFactor()` và `FactorGrantedAuthority` trước khi triển khai. Không chấp nhận một header "MFA complete" tự khai làm bằng chứng.

Khi cần **chỉ một endpoint** bắt MFA, có thể tạo manager riêng cho endpoint đó thay vì áp dụng additional manager lên cả factory dùng chung.

## 10. AuthenticationTrustResolver và các trạng thái xác thực

`setTrustResolver(...)` điều chỉnh cách các manager do factory tạo diễn giải anonymous, remember-me và full authentication. Các trạng thái này liên quan đến `authenticated()`, `fullyAuthenticated()`, `rememberMe()`, `anonymous()`.

Đừng dùng riêng `authentication.isAuthenticated()` để thay thế toàn bộ trust resolver. Một anonymous token trong Spring Security có thể báo `isAuthenticated() == true` ở API lõi, nhưng trust resolver nhận diện đó là anonymous, không phải người dùng đã đăng nhập đầy đủ.

Nếu thay trust resolver tùy chỉnh, phải kiểm thử:
 
- Anonymous request.
- Session login thường.
- Remember-me.
- JWT/OAuth2 đã xác thực, nếu ứng dụng sử dụng.
- Auth token đặc thù của hệ thống.

Nếu không có nhu cầu đặc thù, giữ trust resolver mặc định giúp giảm rủi ro thay đổi ngữ nghĩa của các rule quen thuộc.

## 11. Java 17 chạy độc lập: nhà máy tạo quy tắc

Chương trình sau là **mô hình Java thuần**, không cần Spring Security. Nó thể hiện một factory chuẩn tạo rule theo role và factory tùy biến thêm nhánh ADMIN.

Tạo file `AuthorizationManagerFactoryDemo.java`:

```java
import java.util.Set;

public class AuthorizationManagerFactoryDemo {
    record Actor(String username, Set<String> authorities) {}

    @FunctionalInterface
    interface Rule {
        boolean allows(Actor actor);
    }

    interface RuleFactory {
        Rule hasRole(String role);
    }

    static final class DefaultFactory implements RuleFactory {
        private final String prefix;

        DefaultFactory(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public Rule hasRole(String role) {
            String required = this.prefix + role;
            return actor -> actor != null
                && actor.authorities().contains(required);
        }
    }

    static final class AdminAwareFactory implements RuleFactory {
        private final RuleFactory delegate;

        AdminAwareFactory(RuleFactory delegate) {
            this.delegate = delegate;
        }

        @Override
        public Rule hasRole(String role) {
            Rule base = this.delegate.hasRole(role);
            Rule admin = this.delegate.hasRole("ADMIN");
            return actor -> base.allows(actor) || admin.allows(actor);
        }
    }

    public static void main(String[] args) {
        RuleFactory standard = new DefaultFactory("ROLE_");
        RuleFactory extended = new AdminAwareFactory(standard);

        Rule normalReader = standard.hasRole("READER");
        Rule readerOrAdmin = extended.hasRole("READER");

        Actor reader = new Actor("reader", Set.of("ROLE_READER"));
        Actor admin = new Actor("admin", Set.of("ROLE_ADMIN"));
        Actor guest = new Actor("guest", Set.of());

        System.out.println("Reader default: "
            + normalReader.allows(reader));
        System.out.println("Admin default: "
            + normalReader.allows(admin));
        System.out.println("Admin custom: "
            + readerOrAdmin.allows(admin));
        System.out.println("Guest custom: "
            + readerOrAdmin.allows(guest));
        System.out.println("No identity: "
            + readerOrAdmin.allows(null));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac AuthorizationManagerFactoryDemo.java
java AuthorizationManagerFactoryDemo
```

Stdout chính xác:

```text
Reader default: true
Admin default: false
Admin custom: true
Guest custom: false
No identity: false
```

Factory tạo `Rule` một lần, sau đó cùng rule đánh giá nhiều Actor. Với ADMIN, rule chuẩn READER trả false, còn rule tùy biến thêm nhánh ADMIN trả true. Ví dụ này chỉ mô phỏng **sự phân biệt tạo policy và đánh giá policy**; nó không chạy SpEL, Spring AOP, HTTP hay cơ chế anonymous thật của Spring Security.

## 12. Ranh giới phiên bản và đường tương thích

| Dòng Spring Security | Tình trạng `AuthorizationManagerFactory` | Cách phát triển |
| --- | --- | --- |
| 6.x | API này chưa được cung cấp (`Since: 7.0`) | Dùng `AuthorizationManager<T>`, `.access(...)`, `@PreAuthorize`, bean policy, role hierarchy và điểm mở rộng 6.x |
| 7.0 trở lên | Factory và default factory có sẵn | Có thể đăng ký generic hoặc typed factory; kiểm tra API theo patch |
| Các phiên bản 7.x mới | Có thể bổ sung helpers hoặc điều chỉnh integration | Đối chiếu Javadoc/changelog và integration test trước khi nâng cấp |

Hãy xác định **version thực được resolve**, không chỉ version Spring Security mà người viết đoán từ Spring Boot. Với Maven, dùng `mvn dependency:tree` và xem `spring-security-core`, `spring-security-config`; với Gradle, dùng `./gradlew dependencyInsight` hoặc `dependencies` đúng cấu hình runtime. Nếu dự án dùng Spring Boot BOM, đảm bảo các module Spring Security đồng bộ.

Khi code báo không tìm thấy `AuthorizationManagerFactory`:
 
1. Kiểm tra dependency thực là Spring Security 6.x hay 7.x.
2. Nếu 6.x, không tạo class giả trong package Spring để mô phỏng API mới.
3. Dùng custom `AuthorizationManager` ở các điểm hiện có hoặc lên kế hoạch nâng cấp đồng bộ theo migration guide.
4. Không trộn một artifact Security 7.x lẻ vào dependency graph 6.x.

### Thay thế trong 6.x: custom manager ở đúng điểm

Nếu chỉ cần kiểm tra quyền admin cho một nhóm URL, chính sách sẵn có thường đủ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Với logic phức tạp, dùng `.access(...)` nhận một `AuthorizationManager<RequestAuthorizationContext>` cụ thể hoặc `@PreAuthorize("@policy.canRead(authentication, #id)")` ở service. Cả hai hướng này vẫn hữu ích trong 7.x; không bắt buộc phải có factory tùy biến cho mọi trường hợp.

## 13. Kiểm thử ngữ nghĩa và phạm vi tác động

Một factory có thể biên dịch đúng nhưng **không được framework lựa chọn**, hoặc đổi nghĩa nhiều rule ngoài dự tính. Cần kiểm thử ở hai mức.

### Unit test factory

Với 7.x, gọi những phương thức factory rồi dùng manager trả về để kiểm tra các Authentication test tương ứng. Ít nhất:

1. `hasRole("READER")` với `ROLE_READER` → cho phép.
2. `hasRole("READER")` với `ROLE_ADMIN` → chỉ cho phép trong custom factory đã thêm nhánh ADMIN.
3. Không có cả READER/ADMIN → từ chối.
4. Anonymous hoặc thiếu Authentication → không được tự nâng quyền.
5. `hasAuthority("report:read")` không bị ảnh hưởng bởi override chỉ dành cho role.
6. `hasAllRoles(...)` có giữ nguyên ý nghĩa yêu cầu tất cả không?
7. Prefix `APP_` có khớp authority được cấp thực không?
8. `setAdditionalAuthorization` có áp dụng cho các phương thức được Javadoc liệt kê và **không** áp dụng cho `permitAll`/`denyAll`/`anonymous` không?

Khi test, sử dụng những Authentication/authority do Spring Security test hỗ trợ, không mô phỏng mọi trạng thái xác thực bằng một boolean đơn giản.

### HTTP integration test

Dùng `MockMvc` hoặc test servlet thực, xác minh route và chain khớp thật.

| Principal / URL | Rule | Kỳ vọng với web factory ví dụ |
| --- | --- | --- |
| Anonymous /public/info | `permitAll()` | Cho phép |
| Login có `ROLE_USER` /reports | `authenticated()` được bổ sung USER | Cho phép |
| Login chỉ có `ROLE_GUEST` /reports | `authenticated()` được bổ sung USER | Từ chối |
| Login chỉ có `ROLE_ADMIN` /reports | Chưa có USER; ví dụ không tự nới role | Từ chối |
| Bất kỳ /unknown | `denyAll()` | Từ chối |

HTTP 401 hay 403 tùy authentication entry point và exception handling của ứng dụng; kiểm tra cả trạng thái response lẫn việc business method trái quyền không được gọi.

### Method integration test

Bật `@EnableMethodSecurity`, đăng ký factory typed, lấy `ReportService` từ Spring context và gọi `listReports()`. Với `@WithMockUser(roles = "ADMIN")`, custom method factory ví dụ phải cho phép `@PreAuthorize("hasRole('READER')")`; với người không có cả hai role phải từ chối.

Test cần đi qua **Spring proxy**; gọi `this.listReports()` trong cùng bean có thể bypass interceptor ở cấu hình proxy. Nếu service có `@Transactional`, kiểm tra transaction và tác dụng phụ riêng; factory không tự giải quyết order của các advice.

Khi dùng cả factory generic và factory typed, test điểm web và điểm method độc lập. Quan sát bean configuration để xác nhận factory thực được framework sử dụng, không chỉ test direct invocation trên factory.

## 14. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Copy factory API 7.x vào ứng dụng 6.x | Class/method không tồn tại | Kiểm tra version và dùng API được hỗ trợ |
| Nhầm factory là manager chạy mỗi request | Logic runtime/DB đặt sai nơi | Factory tạo manager; manager làm authorization lúc request/method |
| Override `authenticated()` và tưởng tất cả rule đều thêm USER | Chỉ một nhóm rule thay đổi | Xác định chính xác method factory được override |
| Override `hasRole` nhưng bỏ `hasAnyRole`/`hasAllRoles` | Chính sách role thiếu nhất quán | Dùng RoleHierarchy hoặc sửa/test đúng các nhánh cần thiết |
| Đổi prefix role khác dữ liệu Authentication | Quyền bị từ chối bất ngờ | Đồng bộ mapping authority và viết negative tests |
| Coi ADMIN tự vượt điều kiện tenant/owner | Có thể đọc chéo dữ liệu | Giữ kiểm tra owner/tenant/ACL riêng, nguồn server đáng tin |
| Đặt factory cho web rồi suy ra method đã thay đổi | Nhầm ngữ cảnh generic | Đăng ký đúng typed factory và test từng integration |
| Giả định `setAdditionalAuthorization` tác động `permitAll` | Phân tích MFA sai, có thể mất bảo vệ | Đọc danh sách ngoại lệ API và test luồng authentication |
| Dùng `.access(customManager)` nhưng chờ factory tự thay manager đó | Rule đi ngoài factory | Tạo/combine manager trực tiếp ở điểm access |
| Dùng request parameter cho client chọn role cần kiểm tra | Lỗi logic phân quyền, dù không có SpEL injection | Cố định policy ở server, chỉ nhận dữ liệu tài nguyên |
| Chỉ unit test factory mà không test SecurityFilterChain/AOP | Bean không được dùng hoặc proxy bỏ qua | Integration test đường gọi thực |
| Đăng ký nhiều factory bean chồng lấn mà không kiểm tra | Không rõ factory được chọn | Giữ cấu hình có chủ đích, kiểm tra lựa chọn bean và kết quả cuối |

## 15. Checklist trước khi áp dụng

- **API version:** đã resolve Spring Security 7.0+ chưa, các dependency Security có đồng bộ không?
- **Mục đích:** cần convention tạo các rule thông dụng, hay chỉ cần custom manager cho một route/method?
- **Ngữ cảnh:** factory generic, `RequestAuthorizationContext` hay `MethodInvocation`?
- **Phạm vi override:** chính xác `authenticated`, `hasRole`, `hasAnyRole` hay phương thức nào?
- **Nguồn quyền:** role prefix và role hierarchy có nhất quán với Authentication không?
- **Ngoại lệ:** `permitAll`, `denyAll`, `anonymous` và `.access(...)` có được kiểm tra riêng không?
- **MFA:** additional authorization áp dụng ở đâu, có phá enrollment/recovery không?
- **Tài nguyên:** owner/tenant/ACL có được xác minh từ database/trusted services thay vì client không?
- **Tác dụng phụ:** có transaction, cache, async hoặc self-invocation nào ảnh hưởng đường kiểm tra không?
- **Bằng chứng:** đã có unit và integration test chứng minh factory được sử dụng và quyết định đúng ở cả GRANT lẫn DENY?

**Điểm cần nhớ:** `AuthorizationManagerFactory<T>` chỉ có từ Spring Security **7.0+** và cho phép thống nhất cách **tạo AuthorizationManager**; nó không tự thay thế một policy phân quyền nghiệp vụ. Tùy biến factory có thể thay đổi hành vi rất rộng. Hãy kiểm soát phạm vi, giữ dữ liệu phân quyền đáng tin cậy và kiểm thử các rule thật sau khi cấu hình.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): khái niệm factory và bean cấu hình dùng chung.
- [Javadoc — AuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagerFactory.html): hợp đồng và `Since: 7.0`.
- [Javadoc — DefaultAuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/DefaultAuthorizationManagerFactory.html): cấu hình role prefix/hierarchy/trust resolver/additional authorization.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): ví dụ custom factory cho request authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): ví dụ custom factory cho `MethodInvocation`.
- [Spring Security — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html): yếu tố xác thực bổ sung và factory MFA.
