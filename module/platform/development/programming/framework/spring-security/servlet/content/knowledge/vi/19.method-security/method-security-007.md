# SpEL: authentication, principal, tham số phương thức và bean chính sách trong Spring Security Servlet

## 1. Mục tiêu bài học

Spring Security có thể chặn một HTTP request trước controller, nhưng một người dùng được phép gọi endpoint không có nghĩa họ được đọc **mọi tài liệu**, chỉnh sửa **mọi đơn hàng** hoặc truy cập **dữ liệu của mọi tenant**. Để kiểm tra quyền ngay tại nghiệp vụ, Spring Security hỗ trợ **method security**: đặt biểu thức SpEL (Spring Expression Language) trên method của Spring bean bằng `@PreAuthorize`, `@PostAuthorize` và các cơ chế liên quan.

Bốn thành phần cần nắm chắc:

1. **`authentication`:** đối tượng `Authentication` hiện hành, chứa danh tính, authorities và trạng thái xác thực.
2. **`principal`:** đối tượng đại diện user nằm trong `authentication.getPrincipal()`; kiểu thực tế phụ thuộc cơ chế đăng nhập.
3. **Tham số phương thức:** `#documentId`, `#username` hoặc `#p0` từ những argument được truyền vào method.
4. **Bean chính sách:** `@documentPolicy.canRead(authentication, #documentId)` gọi một Spring bean để thực thi chính sách quyền phức tạp hơn một phép so role.

Bài này áp dụng cho **Spring Security Servlet / Spring MVC**, Spring Security 6.x, Java 17+. Ví dụ chạy trên Spring Boot 3.3.5 như một mốc thống nhất API để học; **không mặc định phiên bản đó là mới nhất hay còn trong vòng hỗ trợ**. Với sản phẩm thực, chọn release còn được hỗ trợ và kiểm tra API phù hợp.

**Kết quả mong muốn:** biết viết biểu thức đúng, hiểu ai cung cấp dữ liệu cho SpEL, không nhầm identity với input do client gửi, đặt policy đúng tầng, tránh tự gọi method làm vượt qua proxy, và chứng minh bằng test rằng người dùng không thể truy cập bản ghi của người khác chỉ bằng cách đoán ID.

## 2. Method security bổ sung cho HTTP authorization

Một request thường đi qua:

```text
GET /docs/10
    |
Servlet FilterChain -> Spring Security
    |
SecurityContextHolder chứa Authentication của request
    |
AuthorizationFilter / authorizeHttpRequests
    |
DispatcherServlet -> DocumentController
    |
DocumentService bean (được Spring tạo proxy)
    |
@PreAuthorize expression
    |
ALLOW -> thực thi DocumentService.read(10)
DENY  -> AccessDeniedException -> xử lý theo security chain
```

`authorizeHttpRequests` trả lời “đường dẫn/method này cần đăng nhập hay role nào?”. Method security trả lời câu hỏi sâu hơn: **“user đang xác thực có được gọi thao tác này với các argument cụ thể không?”**

Ví dụ:

```java
@PreAuthorize("hasRole('ADMIN')")
public void deleteAnyDocument(long documentId) { ... }

@PreAuthorize("authentication.name == #username")
public String readOwnProfile(String username) { ... }

@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document read(long documentId) { ... }
```

Đây là **những mảnh annotation/method**, chưa phải chương trình độc lập. Trong bài thực tế, cần `@EnableMethodSecurity`, bean được Spring quản lý, security context phù hợp và class Java có import đầy đủ.

**Một HTTP role check không thay thế object-level authorization.** Nếu `GET /docs/{id}` chỉ cần `authenticated()`, user Bob có thể đoán `id=10` của Alice. Nếu service có policy kiểm tra owner, request dù qua HTTP authorization vẫn bị từ chối ở ranh giới nghiệp vụ.

Với tác vụ chạy từ scheduled job, listener hoặc lời gọi service ngoài web, method security có thể bảo vệ cùng một service khi có authentication context phù hợp. Ngược lại, HTTP matcher không chạy trên những entry point không phải HTTP. Cần thiết kế caller identity/authorization của các tác vụ đó rõ ràng.

## 3. Bật @EnableMethodSecurity đúng chỗ

Ở Spring Security 6, cách cấu hình điển hình là:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // SecurityFilterChain, UserDetailsService, PasswordEncoder...
}
```

`@EnableMethodSecurity` bật các interceptor cần thiết để áp dụng biểu thức trên method; nó thường bật `@PreAuthorize` và `@PostAuthorize` theo cấu hình mặc định. Ở code cũ có thể gặp `@EnableGlobalMethodSecurity(prePostEnabled = true)`; khi migration sang Security 6 nên sử dụng API hiện hành và kiểm tra sự khác biệt phiên bản.

**Nếu thiếu `@EnableMethodSecurity`, annotation trên service có thể không được thực thi.** Một controller vẫn yêu cầu `authenticated()` khiến người học lầm tưởng policy theo owner đã hoạt động dù thực tế chỉ có HTTP rule.

Method security hoạt động chủ yếu thông qua **Spring AOP proxies/interceptors**. Những nguyên tắc quan trọng:

- Annotation nên được đặt trên public method của Spring-managed service bean.
- Caller phải gọi **qua bean/proxy** được inject, không dùng `new DocumentService(...)` rồi kỳ vọng Spring intercept.
- Gọi `this.read(...)` hoặc một method `@PreAuthorize` khác **trong cùng instance** có thể là *self-invocation*, không đi qua proxy theo cơ chế proxy phổ biến.
- Private, final method, class final, giao diện và class-based proxy có các ràng buộc khác nhau; không tự dựa vào method security cho một code path chưa kiểm thử.
- Quyết định policy nên đặt ở **entry method thực sự được external caller gọi**. Nếu nghiệp vụ có nhiều đường vào (HTTP, job, message), kiểm soát tại service/resource boundary thay vì chỉ ở controller.
- Không cấu hình `@PreAuthorize` trên một method nhưng lại gọi trực tiếp vào repository từ controller và bỏ qua service được bảo vệ.

Spring Security có thể xử lý cả HTTP và method-level denial. Với HTTP Basic như project ví dụ, client chưa xác thực thường nhận **401**; client đã xác thực nhưng method expression trả false thường nhận **403**. Với form login, request chưa đăng nhập có thể được redirect thay vì trả 401.

## 4. SpEL expression context của method security

Một biểu thức `@PreAuthorize` không phải code Java thông thường. Đây là **SpEL** được Spring Security đánh giá với root object và variables do method security cung cấp.

| Biểu thức | Nghĩa thông dụng | Lưu ý |
|---|---|---|
| `authentication` | `Authentication` từ SecurityContext | Là property của root expression; thường không cần dấu `#` |
| `authentication.name` | Danh tính theo `Authentication.getName()` | Thường dễ dùng hơn ép kiểu principal |
| `authentication.authorities` | Authorities hiện hành | Không đồng nghĩa quyền trên từng resource |
| `principal` | `authentication.principal` | Kiểu thay đổi theo Basic/form/JWT/OIDC/custom |
| `principal.username` | Username nếu principal có property này, như UserDetails | Có thể lỗi với principal là String hoặc object khác |
| `isAuthenticated()` | Người gọi có authentication không phải anonymous theo semantics của Spring Security | Không bảo đảm MFA hoặc account state mới nhất |
| `hasRole('ADMIN')` | Có role ADMIN theo prefix role mặc định | Thường ánh xạ `ROLE_ADMIN` |
| `hasAuthority('document:read')` | Có đúng authority string đã nêu | Không tự thêm prefix |
| `#documentId` | Argument tên documentId ở method được intercept | Cần parameter-name discovery đáng tin |
| `#p0` hoặc `#a0` | Argument vị trí 0 | Ít biểu đạt hơn tên và dễ sai khi đổi thứ tự |
| `@documentPolicy` | Spring bean tên documentPolicy | Bean name phải tồn tại, method có thể gọi được |
| `returnObject` | Giá trị method trả về trong `@PostAuthorize` | Không dùng làm return value của `@PreAuthorize` |

**Hai dấu khác nhau:**

- `#parameterName`: tham chiếu biến argument trong evaluation context.
- `@beanName`: tham chiếu bean từ Spring ApplicationContext.

Không viết `#documentPolicy.canRead(...)` nếu mục tiêu là lấy Spring bean, và không viết `@documentId` nếu mục tiêu là tham số method. Biểu thức ví dụ `"@documentPolicy.canRead(authentication, #documentId)"` có cả hai đúng chỗ.

### Authentication: đã xác thực ai?

`Authentication` thường có các thuộc tính:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
Collection<? extends GrantedAuthority> roles =
    authentication.getAuthorities();
Object principal = authentication.getPrincipal();
```

Đây là mảnh code minh họa ngoài annotation; trong Spring Security, `authentication` được đưa vào expression context khi đánh giá method authorization. `getName()` có thể trả username hoặc một identifier khác tùy token.

**Không tự mặc định `authentication.isAuthenticated() == true` nghĩa là user thực.** Một số anonymous Authentication có thể biểu diễn trạng thái authenticated về kỹ thuật; dùng `isAuthenticated()` của method-security expression root để áp đúng semantics phân biệt anonymous theo framework. Với bảo mật thực tế, còn phải kiểm tra cấp bảo đảm xác thực, account disabled/locked hoặc session revocation nếu hệ thống yêu cầu.

Ví dụ:

```java
@PreAuthorize("isAuthenticated() and authentication.name == #username")
public String profile(String username) {
    return "PROFILE:" + username;
}
```

Nếu request đã xác thực dưới tài khoản `alice`, người dùng không thể đổi đường dẫn thành `/profiles/bob` chỉ để lấy dữ liệu của Bob; `authentication.name` đến từ SecurityContext đã được xác thực, còn `#username` đến từ argument.

### Principal: đối tượng hiện tại là gì?

`principal` chính là đối tượng được lưu trong Authentication, nhưng **không có một Java class cố định cho mọi login method**:

- Form login/DAO provider hay HTTP Basic với `UserDetailsService` thường dùng một đối tượng `UserDetails` có `getUsername()`.
- Một custom AuthenticationProvider có thể dùng domain user object hoặc principal tối giản.
- Authentication cho JWT/OIDC thường chứa principal/token object khác với `UserDetails`.
- Anonymous principal có thể là một chuỗi như `anonymousUser`.

Ví dụ khi hệ thống chắc chắn principal là UserDetails:

```java
@PreAuthorize("principal.username == #username or hasRole('ADMIN')")
public String viewProfile(String username) {
    return "PROFILE:" + username;
}
```

Nếu refactor sang JWT và `principal.username` không còn là property tương ứng, expression có thể không hoạt động như dự kiến. **Lựa chọn bền vững hơn cho user ID hiện hành là một principal chuẩn hóa hoặc `authentication.name` với hợp đồng định danh rõ**. Trong hệ thống multi-tenant, chỉ username thường chưa đủ định danh; nên dùng immutable user ID và tenant ID từ nguồn xác thực tin cậy.

Không truy cập `principal.password` để đưa vào SpEL hay trả về response. Không đưa secrets, raw token hoặc PII không cần thiết vào exception/log khi policy bị từ chối.

## 5. Method arguments: #documentId, #username, #p0 và tên tham số

Giả sử có:

```java
@PreAuthorize("authentication.name == #ownerName")
public void updateDocument(long documentId, String ownerName, String text) {
    // Business operation.
}
```

`#ownerName` là **argument của method**. Nó có thể bắt nguồn từ URL, query, request body hoặc code gọi nội bộ — **không phải dữ liệu đáng tin chỉ vì nó được truyền vào Java method**.

Ví dụ sai:

```java
// Không đủ bảo mật nếu ownerName do client tự khai.
@PreAuthorize("authentication.name == #ownerName")
public void updateAnyDocument(long documentId, String ownerName) {
    repository.update(documentId);
}
```

Attacker Alice chỉ cần truyền `ownerName=alice` trong khi `documentId` là tài liệu của Bob; expression vẫn true. **Một phép so Authentication với argument không chứng minh argument phản ánh owner thật trong database.** Đó là nguyên nhân phổ biến của lỗi BOLA/IDOR.

Đúng hơn:

```java
@PreAuthorize("@documentPolicy.canEdit(authentication, #documentId)")
public void updateDocument(long documentId, String text) {
    // Policy tra owner của documentId trong nguồn dữ liệu tin cậy.
}
```

Bean policy kiểm tra dữ liệu hiện hành thay vì tin `ownerName` do client gửi.

### Khả năng khám phá tên tham số

Để `#documentId` được giải quyết chính xác, Spring Security phải biết tên tham số Java. Với Java compilation, nên bật `-parameters` trong Maven compiler:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Trong nhiều project Boot parent đã có cấu hình hỗ trợ, nhưng khai báo tường minh giúp mục đích rõ và tránh phụ thuộc vào môi trường. Các lựa chọn khác có thể gồm annotation đặt tên tham số `@P` theo API được phiên bản Spring Security hỗ trợ. Nếu không có tên, `#p0`/`#a0` có thể dùng argument đầu tiên, nhưng dễ vỡ khi thứ tự tham số thay đổi.

**Nên chọn named parameters để code review thấy đúng nghiệp vụ**, và thêm integration test khiến test fail nếu expression không nhận được ID. Không xem lỗi evaluation/SpEL parse là “tự động deny an toàn” trong mọi cấu hình; lỗi có thể tạo exception server và cần chẩn đoán rõ.

### Tránh null và nhầm kiểu

Nếu `#documentId` là nullable `Long`, policy cần xử lý null. Với bản ghi không tồn tại hoặc ID không hợp lệ, **trả false** khi kiểm tra quyền thường an toàn hơn để exception NPE/SpEL đi sâu xuống service. Nếu policy gọi repository lỗi, không che mọi exception thành “không có quyền”; phân biệt outage với user không đủ quyền ở monitoring.

Một expression quá phức tạp với nhiều phép truy cập nested property dễ phát sinh NPE và khó kiểm thử. Khi phải đọc DB, giải quyết tenant/ownership, document state, ACL hoặc tính giờ, chuyển logic vào **bean chính sách** thay vì nhồi tất cả vào string annotation.

## 6. Bean chính sách: tổ chức authorization theo domain

Một bean như `@documentPolicy` nên:

1. Nhận **Authentication đáng tin từ security context**.
2. Nhận **resource ID** từ method argument.
3. Lấy **trạng thái tài nguyên hiện hành** từ repository/database.
4. Kiểm tra account/tenant/role/owner/permission theo chính sách nghiệp vụ.
5. Trả **boolean** cho quyết định authorize, không thực hiện thao tác thay đổi dữ liệu trước khi quyết định.
6. Được test riêng cho missing resource, user không có quyền, tenant mismatch và các authority không mong muốn.

Cú pháp:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document read(long documentId) { ... }

@PreAuthorize("hasAnyRole('EDITOR', 'ADMIN') and "
        + "@documentPolicy.canEdit(authentication, #documentId)")
public Document update(long documentId, String body) { ... }
```

Hai method trên là **mảnh ví dụ**. Trong Java annotation, nối string literals bằng dấu `+` như trên là một compile-time constant, nên hợp lệ; trong project runnable dưới đây dùng một string literal đơn để giảm bất tiện.

Lợi ích của policy bean so với expression dài:

- Có thể debug và unit-test như Java code bình thường.
- Đọc repository theo ID bất biến và tenant scope, không phụ thuộc dữ liệu giả do client truyền.
- Dùng lại tại nhiều service methods có cùng policy.
- Tránh lặp lại biểu thức `hasRole`/`principal`/owner check không nhất quán.
- Dễ thêm cache, metrics và kiểm soát transaction khi có yêu cầu.

**Cảnh báo thời điểm kiểm tra:** `@PreAuthorize` chạy trước method; nếu policy đọc owner/quyền rồi dữ liệu thay đổi trước khi mutation thực hiện, có thể có TOCTOU (time of check/time of use). Với thao tác tài chính/khóa dữ liệu nhạy cảm, kiểm tra permission **bên trong transaction hoặc tại điểm cập nhật có điều kiện**, không coi một annotation trước service là transaction isolation hoàn chỉnh.

## 7. @PreAuthorize so với @PostAuthorize, @PreFilter, @PostFilter

| Cơ chế | Thời điểm | Ứng dụng phù hợp | Giới hạn |
|---|---|---|---|
| `@PreAuthorize` | Trước khi chạy method | Chặn request khi caller không đủ role/quyền trên ID | Policy có thể không có returnObject hoặc cần DB lookup |
| `@PostAuthorize` | Sau khi method trả kết quả | Kiểm tra owner của object đã load, trước khi trả về caller | Method đã chạy; **không dùng để bảo vệ side effects** |
| `@PreFilter` | Trước method, lọc tập arguments phù hợp | Lọc một collection đầu vào được hỗ trợ | Có thể làm thay đổi semantics của batch operation |
| `@PostFilter` | Sau method, lọc kết quả collection phù hợp | Demo lọc kết quả nhỏ | Tốn chi phí load dữ liệu không được phép; không thay tenant filter ở DB |

Ví dụ đọc dữ liệu:

```java
@PostAuthorize("returnObject != null and "
    + "(returnObject.owner() == authentication.name or hasRole('ADMIN'))")
public Document loadDocument(long id) {
    return repository.findById(id).orElse(null);
}
```

Đây là mảnh code minh họa dùng record có method `owner()`. Nó chỉ hợp lý cho read có chủ đích và đã kiểm soát nguy cơ tải dữ liệu nhạy cảm; **không đặt @PostAuthorize lên method chuyển tiền/cấp quyền/xóa** rồi kỳ vọng nó ngăn thao tác vì business code đã chạy xong trước khi expression được kiểm tra.

Với danh sách lớn hoặc multi-tenant query, ưu tiên **WHERE tenant_id = ... AND allowed...** trong truy vấn hoặc policy truy cập dữ liệu ngay trong service thay vì trả mọi record rồi `@PostFilter`. Lọc dữ liệu sau khi đọc có thể gây memory/time/side-channel và pagination sai.

Spring Security có những biểu thức như `hasPermission(...)` khi được nối với `PermissionEvaluator` phù hợp, nhưng **không mặc định đã có evaluator domain**. Policy bean là giải pháp minh bạch cho nhiều ứng dụng khi chưa có ACL infrastructure.

## 8. Ví dụ đầy đủ Spring Boot 3.3.5 / Java 17 / Maven

Ứng dụng minh họa có các endpoint:

| Endpoint | Ai có quyền | Policy |
|---|---|---|
| `GET /public` | Bất kỳ ai | HTTP `permitAll` |
| `GET /docs/{documentId}` | Owner của document hoặc ADMIN | `@documentPolicy.canRead(authentication, #documentId)` |
| `PUT /docs/{documentId}` | Owner có ROLE_EDITOR hoặc ADMIN | `hasAnyRole` kết hợp `@documentPolicy.canEdit` |
| `GET /profiles/{username}` | User cùng username hoặc ADMIN | `principal.username == #username or hasRole('ADMIN')` |

Dữ liệu học tập:

```text
Document 10: owner alice, body "alice-note"
Document 11: owner bob,   body "bob-note"

User alice: ROLE_READER, ROLE_EDITOR
User bob:   ROLE_READER
User admin: ROLE_ADMIN
```

Một user có thể vượt qua HTTP rule `authenticated()` nhưng vẫn bị `@PreAuthorize` chặn khi ID không thuộc quyền mình. Admin được xem/sửa tất cả trong **policy demo**, nhưng production multi-tenant không được mặc định superuser tự xem mọi tenant.

Project dùng repository in-memory để dễ tái tạo; **không dùng làm thiết kế storage/transaction production**. Các mật khẩu trong source là dữ liệu giả, không sử dụng thực tế.

### 8.1. Cấu trúc thư mục

```text
method-spel-demo/
├── pom.xml
└── src/
    ├── main/java/example/methodspel/
    │   ├── MethodSpelApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentRepository.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   ├── ProfileService.java
    │   └── ApiController.java
    └── test/java/example/methodspel/
        └── MethodSpelTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>method-spel-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`<parameters>true</parameters>` giúp SpEL tìm đúng `#documentId`/`#username` từ method declarations. Spring Boot parent quản lý version của security dependencies; không tự thêm version lệch cho `spring-security-core`.

### 8.3. Main class

File `src/main/java/example/methodspel/MethodSpelApplication.java`:

```java
package example.methodspel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSpelApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSpelApplication.class, args);
    }
}
```

### 8.4. SecurityConfig: bắt buộc @EnableMethodSecurity

File `src/main/java/example/methodspel/SecurityConfig.java`:

```java
package example.methodspel;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("READER", "EDITOR")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("READER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

HTTP security ở đây chỉ quyết định public và authenticated. **Nó không cho phép Bob tự xem mọi docs:** DocumentService policy mới quyết định owner/role. HTTP Basic được dùng để nhìn thấy 401/403 rõ trong MockMvc, không phải khuyến nghị truyền password qua HTTP không mã hóa. Spring Boot có thể tạo hoặc sử dụng HttpSession tùy security context/session policy; ví dụ không cần khẳng định stateless.

CSRF **không bị tắt**. Test PUT cần `with(csrf())` để phân biệt lỗi CSRF với quyền method.

### 8.5. DocumentRepository và record dữ liệu

File `src/main/java/example/methodspel/DocumentRepository.java`:

```java
package example.methodspel;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentRepository {
    private final Map<Long, Document> documents =
        new ConcurrentHashMap<>();

    public DocumentRepository() {
        reset();
    }

    public void reset() {
        documents.clear();
        documents.put(10L, new Document(10L, "alice", "alice-note"));
        documents.put(11L, new Document(11L, "bob", "bob-note"));
    }

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document replaceBody(long id, String newBody) {
        return documents.computeIfPresent(id,
            (key, old) -> new Document(old.id(), old.owner(), newBody));
    }
}

// Java 17 record, chỉ dùng trong package example.methodspel.
record Document(long id, String owner, String body) {}
```

Đây là fixture dữ liệu để test. Record `Document` cố tình không phải `public`; controller/service/policy nằm trong **cùng package**, nên Java code có thể sử dụng nó. Test gọi `reset()` trước mỗi test để trạng thái đổi body không làm lệch test khác. Không có transaction, tenant ID, persistence hoặc audit trong repository demo.

### 8.6. DocumentPolicy: lấy owner từ repository, không từ client

File `src/main/java/example/methodspel/DocumentPolicy.java`:

```java
package example.methodspel;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository documents;

    public DocumentPolicy(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (!isRealUser(authentication)) {
            return false;
        }

        return documents.findById(documentId)
            .map(document -> isAdmin(authentication)
                || document.owner().equals(authentication.getName()))
            .orElse(false);
    }

    public boolean canEdit(Authentication authentication, long documentId) {
        // Role gate nằm ở @PreAuthorize trên service.
        // Policy này chỉ xác minh resource ownership/admin.
        return canRead(authentication, documentId);
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean isAdmin(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    }
}
```

Điểm quan trọng:

- Bean name `documentPolicy` được khai báo rõ bằng `@Component("documentPolicy")`, nên SpEL tham chiếu `@documentPolicy`.
- Bean nhận `Authentication` từ method expression, không lấy username do client truyền để coi là người gọi.
- Owner của document được lấy **từ repository**. Alice không thể gửi `documentId=11` rồi khai `owner=alice` để vượt qua.
- Document không tồn tại → `Optional.empty()` → policy trả false; đây là **deny-by-default**. App có thể chọn trả 404 thay vì 403 theo chính sách chống rò thông tin tồn tại, nhưng cần thiết kế nhất quán, không suy rằng 403 là dấu hiệu document chắc chắn tồn tại.
- `isAuthenticated()` của token kỹ thuật không đủ khi có anonymous token; policy có guard cho `AnonymousAuthenticationToken`. HTTP/method expression còn có các phép kiểm tra riêng.
- `canEdit` không tự kiểm tra role EDITOR; yêu cầu role được thể hiện ở method service. Vì vậy **nếu sau này service khác gọi canEdit mà thiếu role gate, policy sẽ không tự chặn user chỉ có READER**. Production có thể đóng gói đầy đủ role + ownership + tenant trong một method policy để tránh quên; ví dụ tách ra nhằm thấy sự kết hợp SpEL.

Trong nghiệp vụ thật, policy cần xử lý immutable user ID, tenant ID, account status, role cập nhật, ownership, ACL, document visibility và transaction. Không biến một Java boolean trả true thành bảo đảm chống race/concurrent update nếu dữ liệu có thể thay đổi trong lúc method thực thi.

### 8.7. DocumentService: method authorization trên Spring-managed service

File `src/main/java/example/methodspel/DocumentService.java`:

```java
package example.methodspel;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("isAuthenticated() and @documentPolicy.canRead(authentication, #documentId)")
    public Document read(long documentId) {
        return documents.findById(documentId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("hasAnyRole('EDITOR', 'ADMIN') and @documentPolicy.canEdit(authentication, #documentId)")
    public Document update(long documentId, String body) {
        Document updated = documents.replaceBody(documentId, body);
        if (updated == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return updated;
    }
}
```

Lưu ý cả **expression** và **method arguments**:

- `#documentId` phải được discover đúng nhờ `-parameters`. Tham số đầu `documentId` không phải principal; nó chỉ là resource ID.
- `authentication` đến từ security context. Policy tra owner trong repository, không từ body.
- `isAuthenticated() and ...` dùng short-circuit, tránh gọi policy cho anonymous qua biểu thức read.
- `hasAnyRole('EDITOR','ADMIN') and ...` chặn Bob (chỉ READER) trước khi tới policy edit. Alice có EDITOR nhưng vẫn không sửa document 11 của Bob. Admin được bypass owner **chỉ theo policy demo**.
- Policy chạy trước method. Nếu không được phép, `documents.replaceBody` **không chạy**, nên không có side effect từ business method.
- Một lỗi bất ngờ từ repository trong policy có thể gây exception khác với AccessDenied; không nên che timeout DB thành “sai mật khẩu” hoặc “không có quyền” một cách mù quáng.

Trong production, nếu update phải an toàn trước thay đổi đồng thời, cần transaction và kiểm tra điều kiện owner/tenant ở câu lệnh update hoặc khóa dữ liệu phù hợp; test demo không thay thế các bảo đảm đó.

### 8.8. ProfileService: dùng principal trực tiếp

File `src/main/java/example/methodspel/ProfileService.java`:

```java
package example.methodspel;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    @PreAuthorize("principal.username == #username or hasRole('ADMIN')")
    public String viewProfile(String username) {
        return "PROFILE:" + username;
    }
}
```

Trong demo, Basic authentication dùng `InMemoryUserDetailsManager` và principal là `UserDetails` có `getUsername()`. User Bob không xem được `/profiles/alice`; Admin được phép xem. Nếu ứng dụng đổi sang principal loại khác, cần sửa biểu thức hoặc chuẩn hóa principal, không mặc nhiên tin `principal.username` tồn tại.

Một biểu thức ít phụ thuộc principal class hơn là `authentication.name == #username`, với điều kiện hợp đồng `getName()` thực sự là username tương ứng. Với multi-tenant hoặc tài khoản có rename, ưu tiên immutable ID.

### 8.9. ApiController: chỉ gọi service bean được inject

File `src/main/java/example/methodspel/ApiController.java`:

```java
package example.methodspel;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    private final DocumentService documents;
    private final ProfileService profiles;

    public ApiController(DocumentService documents,
                         ProfileService profiles) {
        this.documents = documents;
        this.profiles = profiles;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/docs/{documentId}")
    public String read(@PathVariable long documentId) {
        Document d = documents.read(documentId);
        return "DOC:" + d.id() + ":" + d.body();
    }

    @PutMapping("/docs/{documentId}")
    public String update(@PathVariable long documentId,
                         @RequestBody String body) {
        Document d = documents.update(documentId, body);
        return "UPDATED:" + d.id() + ":" + d.body();
    }

    @GetMapping("/profiles/{username}")
    public String viewProfile(@PathVariable String username) {
        return profiles.viewProfile(username);
    }
}
```

Controller không tự kiểm tra owner bằng query parameter và không tự đánh dấu Authentication hợp lệ. **Service bean do Spring inject** là ranh giới để Spring AOP áp `@PreAuthorize`. Nếu controller gọi thẳng repository, chính sách sẽ bị bypass — vì vậy cần test đường gọi thực tế.

### 8.10. MockMvc + method-security integration tests

File `src/test/java/example/methodspel/MethodSpelTest.java`:

```java
package example.methodspel;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSpelTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentRepository repository;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        repository.reset();
    }

    @Test
    void publicEndpointDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousCannotReadProtectedDocument() throws Exception {
        mvc.perform(get("/docs/10"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/docs/10")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOwnDocumentButNotBobsDocument() throws Exception {
        mvc.perform(get("/docs/10")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("DOC:10:alice-note"));

        mvc.perform(get("/docs/11")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnDocumentButNotAlicesDocument() throws Exception {
        mvc.perform(get("/docs/11")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("DOC:11:bob-note"));

        mvc.perform(get("/docs/10")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadBothDocuments() throws Exception {
        mvc.perform(get("/docs/10")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/docs/11")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void aliceEditorCanUpdateOwnDocumentWithCsrf() throws Exception {
        mvc.perform(put("/docs/10")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("revised"))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:10:revised"));
    }

    @Test
    void aliceEditorCannotUpdateSomeoneElsesDocument() throws Exception {
        mvc.perform(put("/docs/11")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("stolen"))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobReaderCannotUpdateEvenHisOwnDocument() throws Exception {
        mvc.perform(put("/docs/11")
                .with(httpBasic("bob", "bob-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("new"))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminMayUpdateDocumentsUnderDemoPolicy() throws Exception {
        mvc.perform(put("/docs/11")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("approved"))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:11:approved"));
    }

    @Test
    void validUserWithoutCsrfCannotPut() throws Exception {
        mvc.perform(put("/docs/10")
                .with(httpBasic("alice", "alice-pass"))
                .contentType(MediaType.TEXT_PLAIN)
                .content("changed"))
            .andExpect(status().isForbidden());
    }

    @Test
    void profileExpressionUsesPrincipalAndArgument() throws Exception {
        mvc.perform(get("/profiles/alice")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("PROFILE:alice"));

        mvc.perform(get("/profiles/alice")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/profiles/alice")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void missingDocumentFailsClosedInPolicy() throws Exception {
        mvc.perform(get("/docs/999")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER"})
    void directBeanCallIsProtectedWithoutMvc() {
        assertThatThrownBy(() -> service.read(10L))
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

**14 test cases** chứng minh:

- HTTP Basic thiếu/sai credential → 401.
- Alice/Bob đọc đúng doc của mình nhưng bị 403 khi đổi ID sang doc của người khác.
- Admin được xem cả hai trong chính sách demo.
- Update cần **cả** role EDITOR/ADMIN, ownership policy, **và CSRF**: Alice sửa doc mình được, không sửa doc Bob; Bob thiếu EDITOR nên không sửa cả doc mình; Admin sửa theo policy demo.
- PUT của Alice thiếu CSRF trả 403 từ CSRF filter, **không** dùng case này làm bằng chứng method policy từ chối.
- `principal.username == #username` cho Alice và Admin qua, Bob bị chặn.
- Doc không tồn tại được policy từ chối trước khi method truy cập repository; demo trả 403, không tự kết luận rằng ID tồn tại.
- Gọi trực tiếp **Spring-injected** service với `@WithMockUser` vẫn chịu interceptor. Đây là test khác với HTTP authorization, giúp phát hiện nếu method security không được bật.

Các test được thiết kế để chạy dưới Spring Boot 3.3.5 và Java 17. **Bài viết không khẳng định đã chạy chúng trong môi trường thực tế.** Vì repository in-memory được reset ở `@BeforeEach`, mặc định các JUnit tests không chạy song song; nếu dự án bật parallel tests hoặc có traffic ngoài, reset global shared state sẽ cần cách cô lập khác.

### 8.11. Lệnh chạy và kết quả quan sát

Trong thư mục `method-spel-demo`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Dự kiến Maven test reports ghi nhận **14 tests**, không có failures/errors khi dependencies resolve và code đúng như cấu trúc trên. Đây là mục tiêu kiểm thử, không phải stdout đã quan sát.

Nếu app phát triển chạy trên localhost:8080:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/docs/10
curl -i -u alice:alice-pass http://localhost:8080/docs/10
curl -i -u bob:bob-pass http://localhost:8080/docs/10
curl -i -u admin:admin-pass http://localhost:8080/docs/11
```

Status/body dự kiến:

```text
/public (anonymous)           -> 200 PUBLIC_OK
/docs/10 (anonymous)          -> 401
/docs/10 (alice)              -> 200 DOC:10:alice-note
/docs/10 (bob)                -> 403
/docs/11 (admin)              -> 200 DOC:11:bob-note
```

Không lấy phản hồi 403 của curl PUT thiếu CSRF để kết luận user thiếu role. Để test cập nhật, dùng MockMvc `with(csrf())` đã cấu hình, hoặc xây client nhận/gửi CSRF token theo ứng dụng thực. Không đưa tài khoản/mật khẩu fixture lên production và không dùng credential thật trong command line hoặc logs.

## 9. Phân biệt authentication, principal và method arguments bằng ví dụ lỗi

### 9.1. Nhầm principal với tham số userId

Sai:

```java
@PreAuthorize("#userId != null")
public Secret getSecret(String userId) { ... }
```

Client luôn có thể gửi một ID khác null. Không có identity/ownership check nào được thực hiện. Hãy lấy principal/user ID từ Authentication và kiểm tra resource owner từ nguồn tin cậy.

### 9.2. Tin username do request body tự khai

Sai:

```java
@PreAuthorize("authentication.name == #claimedOwner")
public void delete(long documentId, String claimedOwner) { ... }
```

Attacker có thể chọn `claimedOwner` bằng tên của mình dù documentId thuộc người khác. Cần `@policy.canDelete(authentication, #documentId)` và policy tra bản ghi thật.

### 9.3. Gọi method được annotate trong cùng class

Sai trong kiến trúc proxy thông thường:

```java
@Service
class DocumentFacade {
    public void flow(long id) {
        this.deleteProtected(id); // self-invocation có thể bỏ qua proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void deleteProtected(long id) {
        // Business mutation.
    }
}
```

Có thể sửa bằng cách đặt protected method trong một Spring bean khác được inject, hoặc tổ chức policy trực tiếp tại entry method; không chỉ dùng mẹo `self-injection` nếu không hiểu lifecycle, vòng phụ thuộc và test. AOP/proxy behavior phải được xác minh ở version cấu hình.

### 9.4. @PostAuthorize bảo vệ thao tác đã xảy ra

Sai:

```java
@PostAuthorize("hasRole('ADMIN')")
public void transferMoney() {
    bank.transfer(...); // đã chạy trước khi post-authorization kiểm tra
}
```

Post-authorization là **sau method**, nên không chặn được side effect trước đó. Dùng `@PreAuthorize` và authorization trong transaction/business layer cho hành động nhạy cảm.

### 9.5. Principal class thay đổi sau migration

Expression `principal.username` có thể đúng cho `UserDetails` nhưng sai cho JWT principal, custom `String` principal hoặc một adapter khác. Việc SpEL không tìm được property có thể ném exception evaluation, không nhất thiết chỉ trả false. Chuẩn hóa principal hoặc dùng `authentication.name` với ý nghĩa định danh đã thống nhất và test với cơ chế login thật.

### 9.6. Lẫn role/authority prefix

`hasRole('ADMIN')` mặc định kiểm tra authority `ROLE_ADMIN`, còn `hasAuthority('ADMIN')` kiểm tra chuỗi `ADMIN`. Nếu JWT authority mapping là `SCOPE_documents.read` thì phải dùng đúng authority hoặc converter phù hợp; không đổi `hasRole` ngẫu nhiên vì thấy 403.

### 9.7. Chỉ bảo vệ controller, service còn đường gọi khác

Nếu annotation chỉ ở controller nhưng service được gọi từ message listener, batch job hoặc endpoint khác, đường vào mới có thể không đi qua controller. Đặt bảo vệ tại service/resource boundary và chỉ cung cấp quyền đặc biệt cho caller nội bộ theo thiết kế có audit.

### 9.8. Cache policy sai làm dùng quyền lỗi thời

Vai trò/quyền hoặc ownership trong DB có thể đổi sau khi user đăng nhập; `authentication.authorities` trong SecurityContext session có thể còn là snapshot cũ. Nếu policy cần quyền tức thời, phải có session revocation/revalidation, security version hoặc lookup hiện hành. Cache kết quả canRead theo documentId mà **không gắn user/tenant/permissions version** có thể cấp quyền của user khác.

## 10. Thiết kế policy cho tenant và quyền theo bản ghi

Trong ứng dụng nhiều tổ chức, một rule như:

```java
@PreAuthorize("hasAuthority('document:read')")
public Document read(long documentId) { ... }
```

chỉ chứng minh caller có quyền **loại thao tác**, chưa chứng minh document thuộc đúng **tenant**. Policy nên kiểm tra:

1. Authentication phản ánh user ID hiện hành đã được xác minh.
2. Tenant ID không được tin chỉ vì nó nằm trong request path/body; phải kiểm tra user thuộc tenant từ nguồn đáng tin.
3. Document ID tồn tại và document thuộc tenant phù hợp.
4. Role/permission cho hành động và các điều kiện trạng thái document (đã khóa, đang xử lý, owner).
5. Nếu action thay đổi dữ liệu, điều kiện còn đúng tại thời điểm update/transaction.
6. Mọi kết quả từ chối được audit phù hợp, không tiết lộ document của tenant khác.

Ví dụ logic định hướng, **không phải mã nguyên file**:

```java
public boolean canEdit(Authentication auth, long documentId) {
    // 1. Xác minh auth và userId từ principal đáng tin.
    // 2. Lấy document cùng tenant scope từ repository.
    // 3. Kiểm tra role, owner, trạng thái nghiệp vụ.
    // 4. Trả false khi user không được phép hoặc resource không phù hợp.
    return permissionService.isAllowed(auth, documentId, "EDIT");
}
```

Ở mức thực thi, `permissionService` là dependency phải được inject, không phải biến có sẵn. Nếu policy này truy vấn DB nhiều lần, dùng query/index/transaction và cache có key đúng; **đừng** chọn “load toàn bộ documents rồi PostFilter” cho dữ liệu lớn.

## 11. Kiểm thử và quan sát method security trong production

Bộ test nên bao gồm:

- **Authentication boundary:** request không login, credential sai, anonymous/remember-me, session expired.
- **Argument binding:** `#documentId` có giá trị thật; đổi thứ tự hoặc đổi tên method arguments phải làm tests phát hiện lỗi.
- **Object ownership:** Alice không đọc/sửa doc của Bob dù Alice có role EDITOR.
- **Role + policy:** có role nhưng sai owner bị deny; đúng owner nhưng thiếu role cũng bị deny.
- **Bean resolution:** `@documentPolicy` được Spring quản lý và trả false khi resource missing.
- **Proxy boundary:** gọi trực tiếp bean đã inject vẫn bị deny nếu thiếu quyền; thử cả đường vào không phải controller.
- **Return value policy:** nếu dùng `@PostAuthorize`, đảm bảo method read không có side effects bị thực thi trước khi từ chối.
- **Concurrency:** quyền/owner/tenant thay đổi trong lúc business update, kiểm tra transaction policy.
- **Async:** `SecurityContextHolder` thường gắn với thread; thực thi async cần propagation rõ và không mặc định context truyền sang worker thread.
- **Observability:** log request ID, principal identifier đủ dùng, resource ID đã hạn chế, policy name, outcome; không log raw password, JWT, cookie hay các thuộc tính nhạy cảm.

**Để debug một request trả 403**, trước tiên phân biệt nó do HTTP AuthorizationFilter, CSRF, hay method security. Ở môi trường phát triển có thể bật log Spring Security phù hợp và test method bằng bean injection. Không sửa bừa `permitAll` hoặc vô hiệu CSRF để che lỗi.

## 12. Checklist tổng kết

- [ ] Đã bật `@EnableMethodSecurity` và kiểm tra annotation thực sự được intercept.
- [ ] Biết `authentication` là Authentication, `principal` là object bên trong token, `#argument` là tham số method, `@bean` là Spring bean.
- [ ] Không mặc định mọi principal có `username`; có hợp đồng kiểu principal phù hợp.
- [ ] Bật `-parameters` hoặc đặt tên tham số rõ ràng; test SpEL arguments.
- [ ] Rule chỉ so user với input do client cung cấp **không thay thế** kiểm tra owner từ repository.
- [ ] Dùng `@PreAuthorize` trước method có side effects; không dựa vào `@PostAuthorize` cho mutation.
- [ ] Policy bean xử lý null, resource missing, role, tenant và nguồn dữ liệu tin cậy.
- [ ] Có transaction/revalidation ở điểm action nhạy cảm để giảm TOCTOU.
- [ ] Không gọi protected method qua `this.method()` nếu phụ thuộc proxy-based interception.
- [ ] HTTP authorization, CSRF, method security và object-level authorization được test phân biệt.
- [ ] Có test trực tiếp trên bean injected, test username/owner bị giả mạo, và test role thiếu dù owner đúng.
- [ ] Không cache permission mà thiếu user/tenant/version trong key; không log raw credentials.

### Câu hỏi tự kiểm tra

**1.** Trong `@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")`, dấu `@` và `#` khác nhau ra sao?  
**Đáp án:** `@documentPolicy` truy cập Spring bean; `#documentId` truy cập argument của method. `authentication` là property có sẵn của method security expression context.

**2.** `principal.username` luôn hoạt động với JWT/OIDC không?  
**Đáp án:** Không. Principal class phụ thuộc cơ chế xác thực. Cần chuẩn hóa principal hoặc dùng API của Authentication với hợp đồng nhận diện đã thống nhất.

**3.** Vì sao `authentication.name == #ownerName` có thể không đủ chặn đọc trộm tài liệu?  
**Đáp án:** `#ownerName` có thể do attacker truyền; phải kiểm tra owner thật trong DB dựa trên documentId.

**4.** User có `ROLE_EDITOR` nhưng không phải owner, với biểu thức kết hợp role và `@policy.canEdit`, request nên thế nào?  
**Đáp án:** Bị từ chối; cả điều kiện role lẫn quyền trên resource đều cần thỏa.

**5.** Nếu bỏ `@EnableMethodSecurity` nhưng vẫn có `anyRequest().authenticated()`, nguy cơ gì?  
**Đáp án:** Endpoint vẫn cần đăng nhập nhưng không còn kiểm tra owner ở method, dẫn đến IDOR/BOLA.

**6.** Vì sao `@PostAuthorize` không đủ bảo vệ transfer money?  
**Đáp án:** Nó chạy sau khi method thực thi; side effect đã xảy ra.

**7.** Vì sao gọi `this.read(10)` trong cùng service có thể không kiểm tra annotation?  
**Đáp án:** Lời gọi nội bộ có thể không đi qua Spring AOP proxy. Cần tổ chức lại boundary hoặc áp policy ở điểm vào thực sự.

**8.** Vì sao một test `403` cho PUT thiếu CSRF chưa chứng minh method policy đúng?  
**Đáp án:** `CsrfFilter` có thể chặn trước controller/service. Test quyền method cần CSRF hợp lệ và credential/role đúng.

**Kết luận:** SpEL trong Spring Security method security nối **danh tính từ `authentication/principal`**, **argument của method** và **bean chính sách truy vấn dữ liệu tin cậy**. Sự kết hợp này giúp kiểm soát quyền theo từng resource, nhưng chỉ an toàn khi bật method interceptors, giải quyết đúng parameter names, không tin client-supplied owner và kiểm tra chính sách tại service/transaction boundary.