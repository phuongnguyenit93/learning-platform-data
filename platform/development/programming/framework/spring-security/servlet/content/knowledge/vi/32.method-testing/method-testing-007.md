# Kiểm thử @PreAuthorize, @PostAuthorize và quyền theo tham số

> **Bối cảnh:** Spring Security trên **Servlet stack**, Spring Boot 3.x, Spring Security 6.x, Java 17+ và JUnit 5. Mục tiêu là kiểm thử **method-level authorization**, đặc biệt `@PreAuthorize` (kiểm tra trước), `@PostAuthorize` (kiểm tra sau) và những biểu thức sử dụng **tham số method** hay **quyền sở hữu tài nguyên**. Không nhầm chúng với việc chỉ kiểm thử đường dẫn URL trong `SecurityFilterChain`.

## 1. Vì sao cần bảo vệ và kiểm thử ngay tại method?

Một ứng dụng Spring MVC thường có ba nơi mà request có thể bị kiểm tra quyền:

1. **HTTP filter chain:** `authorizeHttpRequests(...)` kiểm tra URL/method HTTP và trạng thái authentication trước khi request tới controller.
2. **Method security:** `@PreAuthorize`, `@PostAuthorize` và các interceptor liên quan kiểm tra lời gọi method trên bean được Spring quản lý.
3. **Business authorization:** chính sách theo tài nguyên, chủ sở hữu, tenant, trạng thái đối tượng, quyền chia sẻ hoặc workflow được gọi từ method security/service.

Chỉ dùng `requestMatchers("/admin/**").hasRole("ADMIN")` chưa chắc bảo vệ được service nếu nó còn được gọi từ batch job, message listener, controller khác hoặc luồng nội bộ. Method security bổ sung một lớp thực thi chính sách tại nơi thực hiện nghiệp vụ.

Ví dụ cần kiểm thử:

- Người dùng `alice` được đọc trang cá nhân của `alice`, nhưng không được dùng đường dẫn `/owners/bob` để đọc dữ liệu của `bob`.
- Quản trị viên có `ROLE_ADMIN` được đọc trang của nhiều người nếu policy cho phép.
- Khi đọc tài liệu, ứng dụng chỉ biết **chủ sở hữu thật** sau khi lấy object từ repository; `@PostAuthorize` có thể kiểm tra `returnObject.owner()` trước khi trả kết quả cho caller.
- Người dùng chưa đăng nhập không được vượt qua biểu thức so sánh parameter bằng cách chọn username giống tên anonymous.
- Kiểm thử phải chứng minh **method thực sự bị chặn** trước/sau lời gọi, không chỉ HTTP endpoint trả 403 do một filter khác.

## 2. Phân biệt @PreAuthorize và @PostAuthorize

### 2.1. @PreAuthorize: quyết định trước khi method body chạy

`@PreAuthorize` sử dụng biểu thức Spring Security để quyết định có cho phép invocation **trước khi thực thi body** của method không:

```java
@PreAuthorize("hasRole('ADMIN')")
public Report exportReport() {
    return reportRepository.loadReport();
}
```

Nếu principal không có `ROLE_ADMIN`, method body không chạy. Đây là lựa chọn phù hợp với những quy tắc đã biết trước invocation: role, authority, owner parameter, tenant được xác minh, hoặc kết quả của một authorization service.

Một biểu thức theo tham số:

```java
@PreAuthorize("hasRole('ADMIN') or (isAuthenticated() and #owner == authentication.name)")
public String readProfile(@P("owner") String owner) {
    return "profile:" + owner;
}
```

Quy tắc: admin được đọc; user đã authenticated chỉ được đọc hồ sơ ứng với tên chính họ. `@P("owner")` khai báo tên tham số cho security expression; tránh phụ thuộc hoàn toàn vào metadata tên tham số nếu build thiếu `-parameters`.

**Tại sao có `isAuthenticated()`?** `authentication.name` có thể chứa tên đại diện anonymous trong cấu hình mặc định. Chỉ kiểm tra `#owner == authentication.name` có nguy cơ cho phép một anonymous principal giả định trùng string. `isAuthenticated()` trong Spring Security expression semantics loại trừ anonymous theo `AuthenticationTrustResolver`; đừng tự suy luận từ `Authentication#isAuthenticated()`, vì anonymous token có thể trả true cho phương thức này.

### 2.2. @PostAuthorize: quyết định sau khi method body đã chạy

`@PostAuthorize` kiểm tra biểu thức khi method đã **trả về kết quả thành công**, với biến `returnObject` trỏ đến giá trị trả về:

```java
@PostAuthorize("hasRole('ADMIN') or (isAuthenticated() and returnObject.owner() == authentication.name)")
public DocumentView readDocument(String id) {
    return documentRepository.load(id);
}
```

Khi tài liệu thuộc về `alice`, user `bob` có thể khiến repository load tài liệu, nhưng lời gọi qua security proxy vẫn ném `AccessDeniedException` **trước khi trả object cho caller** nếu policy không cho đọc. `returnObject.owner()` ở đây là lời gọi method của Java record dùng làm giá trị trả về; với POJO getter truyền thống, có thể dùng property access phù hợp.

**Giới hạn cực kỳ quan trọng:** `@PostAuthorize` **không ngăn method body chạy**. Nếu method thực hiện chuyển tiền, xóa hồ sơ, gọi external API, gửi email hay ghi database, tác dụng phụ có thể xảy ra **trước khi** người gọi bị từ chối. Không dùng post-authorization làm hàng rào duy nhất cho operation có side effects. Với thao tác ghi/sửa/xóa, thường cần `@PreAuthorize` hoặc kiểm tra policy trước khi thực hiện bất kỳ hành động không thể hoàn tác.

### 2.3. Bảng so sánh

| Tiêu chí | @PreAuthorize | @PostAuthorize |
| --- | --- | --- |
| Thời điểm kiểm tra | Trước method body | Sau khi method trả về thành công |
| Dữ liệu có thể dùng | Authentication, role, authority, method parameters, các security beans/policies | Tất cả yếu tố phù hợp ở trước, cộng `returnObject` |
| Có chạy method khi thiếu quyền? | Không | Có thể đã chạy, sau đó result bị chặn |
| Phù hợp nhất | Chặn truy cập trước khi thao tác; quyền dựa vào parameter/đối tượng được kiểm tra trước | Đọc dữ liệu khi chủ sở hữu/chính sách chỉ biết từ result |
| Có dùng cho command ghi DB không? | Thường phù hợp | Không nên dùng như chốt bảo vệ duy nhất |
| Lỗi thiếu quyền điển hình | `AccessDeniedException`, body chưa chạy | `AccessDeniedException` sau khi body chạy |
| Test cần xác minh | Không gọi repository/không có side effect nếu bị chặn | Không trả result cho caller; hiểu rõ phần xử lý đã chạy |
| Dễ nhầm | “Bảo vệ method nghĩa là mọi caller đều đi qua proxy.” | “Method bị từ chối tức là method chưa chạy.” |

Nếu method ném exception trước khi có return value, biểu thức `@PostAuthorize` có thể **không được thực thi** cho kết quả đó. Vì vậy cần test cả đường trả kết quả và đường ném exception. Khi method trả `null`, một biểu thức trực tiếp gọi `returnObject.owner()` cần xử lý null hoặc có contract bảo đảm non-null.

## 3. Bật method security đúng cách

Trong Spring Security 6, dùng `@EnableMethodSecurity` trên một class cấu hình Spring:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // ...
}
```

`@EnableMethodSecurity` kích hoạt hạ tầng method-security interceptor (đối với cấu hình thông thường, pre/post annotations được hỗ trợ). Không phụ thuộc một mình vào `@EnableWebSecurity` hoặc `http.authorizeHttpRequests(...)` để bật method annotations.

**Kiểm tra runtime:** Nếu quên `@EnableMethodSecurity`, annotation có thể xuất hiện trên source nhưng method body vẫn chạy như không có kiểm tra. Một unit test gọi trực tiếp `new DocumentService()` cũng không tự động có Spring AOP proxy, nên có thể “test pass” logic service mà hoàn toàn không kiểm tra method security.

Điều kiện thường gặp:

- Dùng bean được Spring quản lý, ví dụ `@Service` và lấy qua `@Autowired`/constructor injection.
- Method mà cần intercept thường nên là **public**, được caller gọi **từ bên ngoài proxy**. Đừng dựa vào annotation ở private method hay self-invocation nội bộ để bảo vệ.
- Hạ tầng proxy có thể dùng JDK hoặc CGLIB tùy class/interface/config; method final và những thiết kế không thể proxy cần được đánh giá.
- Với dự án nâng cấp từ phiên bản cũ, `@EnableGlobalMethodSecurity` đã được thay bằng `@EnableMethodSecurity` trong cấu hình Spring Security 6 hiện đại.
- Đối với reactive stack, có hạ tầng khác (`@EnableReactiveMethodSecurity`). Bài này chỉ áp dụng **Servlet**.

### 3.1. Security expression đọc dữ liệu gì?

Các tên phổ biến trong biểu thức:

- `authentication`: Spring `Authentication` hiện tại.
- `principal`: principal trong authentication.
- `hasRole('ADMIN')`: thường tìm authority `ROLE_ADMIN`.
- `hasAuthority('SCOPE_reports.read')`: so khớp authority cụ thể, không tự thêm prefix role.
- `isAuthenticated()`: theo semantics của Spring Security, thường không chấp nhận anonymous.
- `#owner` hoặc `#id`: tham số được Spring expression parameter name discoverer ánh xạ.
- `returnObject`: chỉ hữu ích sau lời gọi cho `@PostAuthorize`.
- `@policyBean.canRead(authentication, #id)`: gọi một bean policy được quản lý, giúp tách biểu thức phức tạp khỏi annotation.

**Không dùng input từ frontend làm nguồn sự thật cho quyền:** `#owner` chỉ là tham số request, có thể do attacker thay đổi. Biểu thức phải so sánh với danh tính đã xác thực hoặc policy tra cứu server-side. Một `documentId` mà user gửi **không chứng minh** user là owner của document đó.

### 3.2. Parameter name discovery và @P

Một expression như `#owner == authentication.name` cần mapping từ biến `owner` tới đúng argument:

```java
@PreAuthorize("#owner == authentication.name")
public String read(String owner) { ... }
```

Mã có thể hoạt động nếu build giữ metadata tên tham số `-parameters`, nhưng có thể lỗi hoặc trả false khi metadata thiếu. Với Spring Security, một cách tường minh là `@P`:

```java
import org.springframework.security.core.parameters.P;

@PreAuthorize("isAuthenticated() and #owner == authentication.name")
public String read(@P("owner") String name) {
    return "profile:" + name;
}
```

Ở đây tên biến trong Java method là `name` nhưng Spring method-security expression biết nó là `owner` nhờ `@P("owner")`. Khi có nhiều đối số, đặt tên rõ và viết test gọi đúng parameter. Bật `-parameters` cũng hữu ích để framework suy ra tên tham số:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Tuy nhiên, nếu bạn chủ động dùng `@P`, quy tắc đã rõ ngay trong source; không cần dựa độc quyền vào compiler flag.

## 4. Ví dụ xuyên suốt: owner parameter và quyền theo giá trị trả về

Chúng ta tạo ứng dụng Spring Boot 3.4.x + Java 17, có ba user test:

- `alice`: `ROLE_USER`.
- `bob`: `ROLE_USER`.
- `admin`: `ROLE_ADMIN`.

Service cung cấp hai method:

1. `readOwnerPage(owner)` được bảo vệ bằng `@PreAuthorize`. Admin được đọc mọi owner; user thường chỉ được đọc tên mình.
2. `readDocument(id)` được bảo vệ bằng `@PostAuthorize`. Service load document, sau đó kiểm tra field `owner` trong result.

Một API Spring MVC có thể gọi service, nhưng test method-level phải gọi **bean service qua proxy**, không chỉ kiểm tra rằng filter URL chặn request.

### 4.1. Cấu trúc dự án

```text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/methodsecurity/
    │   ├── MethodSecurityDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentView.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/com/example/methodsecurity/
        ├── DocumentServiceSecurityTest.java
        └── DocumentControllerSecurityTest.java
```

### 4.2. Gradle dependencies

`settings.gradle`:

```groovy
rootProject.name = 'method-security-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

`spring-security-test` cung cấp các annotation như `@WithMockUser` và `@WithAnonymousUser` và `SecurityMockMvcRequestPostProcessors`. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Spring test/MockMvc. Spring Boot quản lý phiên bản dependency tương thích.

### 4.3. Spring Boot application

`src/main/java/com/example/methodsecurity/MethodSecurityDemoApplication.java`:

```java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityDemoApplication.class, args);
    }
}
```

### 4.4. SecurityConfig

`src/main/java/com/example/methodsecurity/SecurityConfig.java`:

```java
package com.example.methodsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}
```

**Vì sao URL chỉ cần `authenticated()`?** Chúng ta muốn test phương thức thật sự từ chối `bob` đọc tài liệu `alice`, thay vì một rule URL đã chặn trước. `/owners/{owner}` và `/documents/{id}` đều hợp lệ về mặt HTTP và cần login; **service** mới quyết định quyền theo owner/result. Trong production, có thể đồng thời áp dụng rule URL và method security nhưng test phải làm rõ lớp nào chịu trách nhiệm.

Password test dùng `DelegatingPasswordEncoder`, không lưu password production. Demo HTTP Basic cần HTTPS nếu dùng ngoài localhost. Các đường dẫn đều GET nên không làm mất CSRF protection mặc định.

### 4.5. Record trả về

`src/main/java/com/example/methodsecurity/DocumentView.java`:

```java
package com.example.methodsecurity;

public record DocumentView(String id, String owner, String title) {
}
```

Java record có accessor `owner()`. Đây chính là giá trị `returnObject` được dùng trong `@PostAuthorize` ở ví dụ.

### 4.6. Service được Spring quản lý và method được intercept

`src/main/java/com/example/methodsecurity/DocumentService.java`:

```java
package com.example.methodsecurity;

import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final Map<String, DocumentView> documents = Map.of(
            "d-alice", new DocumentView("d-alice", "alice",
                    "Notes for Alice"),
            "d-bob", new DocumentView("d-bob", "bob",
                    "Notes for Bob")
    );

    @PreAuthorize("""
            hasRole('ADMIN') or
            (isAuthenticated() and #owner == authentication.name)
            """)
    public String readOwnerPage(@P("owner") String owner) {
        return "profile:" + owner;
    }

    @PostAuthorize("""
            hasRole('ADMIN') or
            (isAuthenticated() and returnObject.owner() == authentication.name)
            """)
    public DocumentView readDocument(@P("id") String id) {
        DocumentView document = documents.get(id);
        if (document == null) {
            throw new NoSuchElementException("Document not found");
        }
        return document;
    }
}
```

**Từng điểm quan trọng:**

- `@Service` khiến class là Spring-managed bean; interceptor method security được áp dụng khi caller sử dụng bean proxy.
- `@PreAuthorize` kiểm tra **trước** body; user `alice` không thể gọi `readOwnerPage("bob")` nếu không có `ROLE_ADMIN`.
- `@P("owner")` cho biểu thức biết tham số nào là `#owner`; username thật ở phía `authentication.name`.
- `@PostAuthorize` kiểm tra **sau** khi `readDocument` lấy object. Với `readDocument("d-alice")`, `bob` bị từ chối sau khi object đã được load, và controller không nhận được object.
- Method `readDocument` là **read-only** và không ghi DB/gửi thông điệp; đây là một case phù hợp để minh họa post-authorization. Không copy nguyên annotation này lên method thực hiện side effects.
- Khi document không tồn tại, body ném `NoSuchElementException` trước khi có kết quả để dùng ở `@PostAuthorize`. Controller phía dưới chuyển ngoại lệ này thành HTTP 404; đây là **lỗi không tìm thấy**, không phải một chứng minh về quyền.
- Đoạn demo có in-memory `Map` để kết quả ổn định khi chạy test, không phụ thuộc DB hoặc external service.

Vì Java text block ở trên tạo ra chuỗi SpEL với newline/indentation, syntax vẫn hợp lệ với parser của Spring Security. Nếu muốn tối giản hoặc dự án dùng cấu hình không hỗ trợ text blocks, có thể viết thành một string duy nhất:

```java
@PreAuthorize("hasRole('ADMIN') or (isAuthenticated() and #owner == authentication.name)")
```

### 4.7. Controller Spring MVC

`src/main/java/com/example/methodsecurity/DocumentController.java`:

```java
package com.example.methodsecurity;

import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("result", "public");
    }

    @GetMapping("/owners/{owner}")
    public Map<String, String> ownerPage(@PathVariable String owner) {
        return Map.of("result", service.readOwnerPage(owner));
    }

    @GetMapping("/documents/{id}")
    public DocumentView document(@PathVariable String id) {
        return service.readDocument(id);
    }

    @ExceptionHandler(NoSuchElementException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Map<String, String> notFound() {
        return Map.of("error", "not_found");
    }
}
```

Controller không tự viết `if ("alice".equals(...))`. Nó chuyển request vào bean service đã được method security bảo vệ, và chỉ xử lý `NoSuchElementException` thành 404. Khi thiếu quyền, `AccessDeniedException` được Spring Security xử lý qua cơ chế exception translation thông thường và kết quả HTTP phù hợp (thường 403 với user đã authenticated).

**Cần phân biệt:** trong ứng dụng thật, mã 403 và 404 khác nhau có thể vô tình tiết lộ tài liệu tồn tại hay không. Bài demo ưu tiên minh họa interceptor, còn production có thể cần chính sách chống enumeration, kiểm tra quyền theo ID **trước khi load** hoặc trả lỗi nhất quán theo mô hình dữ liệu.

## 5. Viết kiểm thử method-level với Spring Security Test

Những test dưới đây lấy `DocumentService` từ **Spring ApplicationContext**, do đó gọi qua method-security proxy. Chúng không gọi HTTP, nên có thể xác định chính xác annotation `@PreAuthorize` hoặc `@PostAuthorize` đã hoạt động hay chưa.

### 5.1. @WithMockUser làm gì?

`@WithMockUser` từ `spring-security-test` đặt một authentication giả lập vào test security context, ví dụ:

```java
@WithMockUser(username = "alice", roles = "USER")
```

Nó đặt user `alice` với authority `ROLE_USER`. Nó **không** nhập password qua login form/LDAP/HTTP Basic và không tự kiểm tra password encoder. Mục đích là kiểm thử method-security expressions với security context đã xác lập.

Một số tình huống cần nhớ:

- `@WithMockUser(username = "admin", roles = "ADMIN")` tạo `ROLE_ADMIN`.
- `@WithMockUser(username = "alice", authorities = "SCOPE_read")` tạo authority chính xác `SCOPE_read`, **không** tự thêm `ROLE_`.
- `@WithMockUser` mặc định username `user` và role `USER` nếu bạn không chỉ định; viết tường minh để tránh test dùng nhầm identity.
- `@WithAnonymousUser` mô phỏng ngữ cảnh anonymous, giúp kiểm tra `isAuthenticated()` và role check đúng.
- Nếu cần principal thật từ `UserDetailsService`, có thể dùng `@WithUserDetails`, nhưng điều đó cũng không tự biến thành kiểm thử password authentication thực tế.

### 5.2. Test đầy đủ cho @PreAuthorize và @PostAuthorize

`src/test/java/com/example/methodsecurity/DocumentServiceSecurityTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService service;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadOwnPage() {
        assertThat(service.readOwnerPage("alice"))
                .isEqualTo("profile:alice");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCannotReadOthersPage() {
        assertThatThrownBy(() -> service.readOwnerPage("bob"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadAnyOwnerPage() {
        assertThat(service.readOwnerPage("bob"))
                .isEqualTo("profile:bob");
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadOwnerPage() {
        assertThatThrownBy(() -> service.readOwnerPage("alice"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadOwnDocument() {
        DocumentView result = service.readDocument("d-alice");
        assertThat(result.owner()).isEqualTo("alice");
        assertThat(result.title()).isEqualTo("Notes for Alice");
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void userCannotReadOthersDocument() {
        assertThatThrownBy(() -> service.readDocument("d-alice"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadOthersDocument() {
        DocumentView result = service.readDocument("d-alice");
        assertThat(result.owner()).isEqualTo("alice");
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadDocument() {
        assertThatThrownBy(() -> service.readDocument("d-alice"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Vì sao đây thực sự là test method security?** `DocumentService` được autowire từ Spring; cả hai annotation được intercept. URL filter không tham gia. Nếu `@EnableMethodSecurity` bị bỏ, các negative tests có thể thất bại vì service vẫn trả dữ liệu thay vì ném `AccessDeniedException` — một tín hiệu test có giá trị.

Các test định nghĩa rõ cả **được phép** lẫn **bị từ chối**; không chỉ test happy path. Nhóm này cũng kiểm tra `@P("owner")` hoạt động. Với một service chủ sở hữu, test tham số không thuộc user giúp phát hiện lỗi IDOR khi lỡ bỏ so sánh owner.

### 5.3. Ma trận kết quả mong đợi

| Test principal | Method/call | Ý nghĩa kiểm tra | Kỳ vọng |
| --- | --- | --- | --- |
| alice / USER | `readOwnerPage("alice")` | Owner param khớp | Cho phép |
| alice / USER | `readOwnerPage("bob")` | Owner param sai | `AccessDeniedException` trước body |
| admin / ADMIN | `readOwnerPage("bob")` | Rule admin override | Cho phép |
| anonymous | `readOwnerPage("alice")` | Không có danh tính hợp lệ | `AccessDeniedException` |
| alice / USER | `readDocument("d-alice")` | Owner từ result khớp | Cho phép |
| bob / USER | `readDocument("d-alice")` | Owner từ result khác | `AccessDeniedException` sau body |
| admin / ADMIN | `readDocument("d-alice")` | Rule admin | Cho phép |
| anonymous | `readDocument("d-alice")` | Chưa xác thực | `AccessDeniedException` |

Những test tương tự có thể dùng cho tenant, department, project membership, organization, approval state hoặc permission on resource, nhưng **biểu thức phải phản ánh quyền đã xác minh phía server**, không đơn giản dựa vào tham số do client tự khai.

## 6. Kiểm thử qua HTTP bằng MockMvc: URL filter và method security cùng hoạt động

Để biết HTTP response có đúng không, cần test tích hợp Servlet web layer. Spring Boot có `@SpringBootTest` + `@AutoConfigureMockMvc`; `spring-security-test` hỗ trợ `httpBasic(...)`. Khác `@WithMockUser` direct service tests, HTTP Basic ở đây kiểm tra thêm đường đi qua authentication mechanism.

### 6.1. Test class

`src/test/java/com/example/methodsecurity/DocumentControllerSecurityTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentControllerSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("public"));
    }

    @Test
    void unauthenticatedOwnerRouteGets401() throws Exception {
        mvc.perform(get("/owners/alice"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanAccessOwnOwnerPage() throws Exception {
        mvc.perform(get("/owners/alice")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result")
                        .value("profile:alice"));
    }

    @Test
    void aliceCannotAccessBobOwnerPage() throws Exception {
        mvc.perform(get("/owners/bob")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCannotReadAliceDocument() throws Exception {
        mvc.perform(get("/documents/d-alice")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAliceDocument() throws Exception {
        mvc.perform(get("/documents/d-alice")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void missingDocumentGets404() throws Exception {
        mvc.perform(get("/documents/not-found")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isNotFound());
    }
}
```

**Cách giải thích HTTP status ở cấu hình này:**

- `401 Unauthorized`: request chưa có credential hợp lệ; `HTTP Basic` entry point yêu cầu xác thực **trước khi gọi service**.
- `403 Forbidden`: user đã xác thực nhưng service method-security rule từ chối.
- `404 Not Found`: controller map `NoSuchElementException` khi document không tồn tại. Đây là chính sách demo, không phải kết quả chung của mọi service.
- `200 OK`: cả HTTP authentication và policy method-level đều cho phép.

Trong ứng dụng dùng `formLogin()`, chưa đăng nhập có thể nhận `302` tới trang login thay vì 401. Do đó **không dán nguyên status assertion** của HTTP Basic vào một ứng dụng form-login khác mà không chỉnh theo entry point.

### 6.2. Chạy test

Nếu dự án được tạo với Gradle Wrapper:

```bash
# Linux/macOS
./gradlew test

# Windows PowerShell
.\gradlew.bat test
```

Khi ứng dụng, JDK, dependency và Gradle Wrapper đúng như ví dụ, 8 test service và 7 test HTTP phải pass. Đây là **kỳ vọng của mẫu**, không tuyên bố đã chạy lệnh trong môi trường của bạn. Không có stdout JSON cố định từ Gradle vì log và thời gian chạy thay đổi theo máy/phiên bản.

### 6.3. Vì sao không chỉ dùng standaloneSetup?

Một controller test chỉ tạo:

```java
MockMvcBuilders.standaloneSetup(new DocumentController(service)).build();
```

không mặc nhiên có Spring Security filter chain, context, authentication manager và method-security proxy như production. Nếu `service` cũng là `new DocumentService()`, test **bỏ qua interceptor** hoàn toàn. Test như vậy phù hợp kiểm thử MVC binding hoặc JSON đơn giản, nhưng không đủ để kết luận `@PreAuthorize` hay `@PostAuthorize` đã thực thi.

Để test method security, dùng Spring context có `@EnableMethodSecurity` và bean proxy; để test HTTP security, dùng `MockMvc` đã tích hợp `springSecurity()`/filter chain (trong ví dụ Boot `@AutoConfigureMockMvc` đảm nhận config phù hợp).

## 7. Kiểm chứng rằng @PreAuthorize chặn body, còn @PostAuthorize chạy sau body

Trong test không nên chỉ hỏi “có exception không” khi thứ tự thực thi là yêu cầu bảo mật.

### 7.1. Với @PreAuthorize

Một service có thể gọi repository:

```java
@PreAuthorize("hasRole('ADMIN')")
public void deleteDocument(String id) {
    documentRepository.deleteById(id);
}
```

Nếu user không có role, body không được thực thi. Trong Spring-integrated test, có thể dùng mock/spy repository rồi xác minh **không có `deleteById`** khi gọi method qua proxy. Điều này quan trọng hơn việc chỉ thấy 403 tại controller: 403 có thể đến từ filter khác, hoặc body có thể đã chạy nếu annotation bị bypass.

Pseudocode assertion cho một test có `@MockitoBean`/Mockito repository đã được quản lý:

```java
assertThatThrownBy(() -> service.deleteDocument("d1"))
        .isInstanceOf(AccessDeniedException.class);

verify(documentRepository, never()).deleteById(anyString());
```

Đây là **snippet kiểm thử có điều kiện**, không thuộc dự án mẫu bên trên (vì không có repository xóa hoặc bean mock). Khi dùng mock repository trong Spring Boot 3.4+, cần làm đúng cách inject mock vào bean đích, không tự new service bỏ qua proxy.

### 7.2. Với @PostAuthorize

Một method được `@PostAuthorize` kiểm tra **sau** khi trả về giá trị. Nếu method đã thực hiện external call, metric, query hoặc side effect, việc kết quả cuối cùng bị chặn **không có nghĩa những bước đã được hoàn tác**.

Có thể dùng spy/metric để test rằng repository `findById` được gọi dù result bị chặn, nhưng **không nên biến thiết kế có side effects thành “an toàn” chỉ vì test pass**. Với mutation, kiểm tra quyền **trước khi** ghi hoặc bảo đảm business authorization trong service trước mutation. Transaction rollback không thể đảo ngược một email đã gửi hoặc một external API call.

**Trường hợp null/exception:** nếu method trả `null`, biểu thức `returnObject.owner()` có thể gây evaluation error; khi method ném `NoSuchElementException`, post-authorization không có result để kiểm tra. Test các nhánh này theo contract của service, không chỉ happy path.

## 8. Kiểm thử quyền theo tham số: các mẫu phổ biến

### 8.1. So sánh tham số với tên user

```java
@PreAuthorize("isAuthenticated() and #owner == authentication.name")
public ProfileView profile(@P("owner") String owner) { ... }
```

Ưu điểm: gọn khi owner string có cùng format và độ tin cậy với `authentication.name`. Nhược điểm: user name có thể đổi; không thích hợp khi account ID/subject/tenant khác username. Với OIDC, nên dùng subject ổn định đã được xác minh và map đúng, không lấy email như khóa quyền mặc định.

Test tối thiểu: owner đúng, owner khác, anonymous, admin rule nếu có, null/empty input và case khác chữ hoa/chữ thường nếu policy cần.

### 8.2. Phân quyền theo ID tài nguyên

Ví dụ caller truyền `documentId`, nhưng owner nằm trong DB. Không thể tự cho phép chỉ vì tài liệu ID do client truyền. Một policy bean có thể quyết định:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(@P("documentId") String id) {
    return repository.findRequired(id);
}
```

Đây là **snippet kiến trúc**; để chạy cần bean có tên `documentPolicy`, method `canRead(Authentication, String)` và repository phù hợp. Nó kiểm tra quyền **trước method body** và tránh phải load/tiết lộ object đầy đủ rồi mới `@PostAuthorize`. Tuy nhiên nếu policy lookup và body lookup ở hai thời điểm khác nhau, phải xem xét **TOCTOU** (time-of-check/time-of-use) khi owner/ACL có thể thay đổi đồng thời; trong thao tác ghi, cân nhắc transaction/locking/conditional update.

Ví dụ signature của policy:

```java
@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication auth, String documentId) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        // Tiếp tục kiểm tra anonymous trust, account, tenant, ACL
        // và quyền sở hữu bằng dữ liệu server-side.
        return repository.mayRead(auth.getName(), documentId);
    }
}
```

Đây là **mẫu ý tưởng**, không phải file runnable trong demo, vì `DocumentRepository` là hợp đồng nghiệp vụ chưa được định nghĩa ở đây. Đặc biệt, điều kiện `auth.isAuthenticated()` **chưa đủ** để loại anonymous: policy production cần `AuthenticationTrustResolver` hoặc kiểm tra principal được công nhận phù hợp. Đừng copy nguyên snippet rồi tin rằng nó đã là ACL hoàn chỉnh.

### 8.3. Quyền theo tenant

```java
@PreAuthorize("""
        isAuthenticated() and
        @tenantPolicy.canAccess(authentication, #tenantId)
        """)
public InvoiceView invoice(
        @P("tenantId") String tenantId,
        @P("invoiceId") String invoiceId) { ... }
```

Rule không chỉ phải xác nhận user thuộc tenant mà còn phải bảo đảm `invoiceId` **thật sự thuộc tenant đó**. Nếu không, có thể xảy ra kiểu bypass: user có quyền vào tenant A nhưng gửi `invoiceId` thuộc tenant B. Test phải cố tình dùng **tenantId hợp lệ + invoiceId của tenant khác**.

### 8.4. Role và authority

- `hasRole('ADMIN')` thường so sánh với `ROLE_ADMIN`.
- `hasAuthority('DOC_READ')` so sánh authority chính xác `DOC_READ`.
- `hasAnyAuthority('DOC_READ', 'DOC_AUDIT')` kiểm tra một trong các authority chỉ định.
- `hasPermission(...)` chỉ hoạt động đúng khi có `PermissionEvaluator`/expression handler được cấu hình theo kiến trúc ứng dụng; không mặc định biết ACL DB của bạn.

Khi dùng `@WithMockUser(roles = "ADMIN")` để test `hasAuthority('ADMIN')`, test **có thể fail** vì actual authority là `ROLE_ADMIN`. Dùng `authorities = "ADMIN"` nếu policy yêu cầu authority chính xác `ADMIN`, hoặc sửa policy theo ngữ nghĩa role. Đừng cấp thêm quyền production chỉ để test pass.

### 8.5. Test matrix theo parameter và trạng thái

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Owner đúng | alice gọi `readOwnerPage("alice")` | Cho phép |
| Owner sai | alice gọi `readOwnerPage("bob")` | Từ chối |
| Role admin | admin gọi `readOwnerPage("bob")` | Cho phép nếu policy admin |
| Anonymous | anonymous gọi `readOwnerPage("alice")` | Từ chối |
| Null/empty owner | Tham số không hợp lệ | Validation/authorization theo contract; không cấp quyền ngầm |
| Case mismatch | `Alice` và `alice` | Chỉ chấp nhận khi chính sách định danh định nghĩa rõ |
| Tenant đúng, object khác tenant | User của tenant A gửi ID thuộc B | Từ chối |
| Object bị chuyển chủ | Quyền thay đổi giữa check và use | Chính sách bảo vệ concurrency/transaction |
| Principal đổi sau refresh | Session/token chứa account/role cũ | Kiểm chứng nguồn authority và policy khi quyền bị thu hồi |
| Endpoint public nhưng gọi service bảo vệ | Caller chưa authenticated | Method security vẫn chặn |

## 9. Quyền theo tham số và các lỗ hổng IDOR/BOLA

**IDOR** (Insecure Direct Object Reference) hay **BOLA** (Broken Object Level Authorization) xảy ra khi endpoint nhận ID của đối tượng nhưng không xác minh client có quyền với **đối tượng đó**.

Sai:

```java
@GetMapping("/documents/{id}")
public DocumentView get(@PathVariable String id) {
    return repository.findRequired(id);
}
```

Endpoint có thể yêu cầu login nhưng vẫn cho user đọc bất kỳ tài liệu nào khi biết ID. **Đăng nhập không đồng nghĩa quyền sở hữu mọi object**.

An toàn hơn:

- Dùng `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")` nếu có policy/check phù hợp trước query.
- Hoặc `@PostAuthorize` kiểm tra `returnObject.owner()` cho **read-only** method, hiểu rõ body đã chạy.
- Với command ghi, kiểm tra actor, tenant, owner/ACL trước mutation; cân nhắc atomic conditional update.
- Bảo vệ việc nhận dạng object không tồn tại với policy 403/404 thống nhất theo mô hình threat, không rò danh sách object thông qua chênh lệch response/time.
- Test cả cùng tenant khác owner, khác tenant cùng username, ID bị đoán, role thấp và account đã bị khóa.

**Không coi việc đoán ID khó** (UUID ngẫu nhiên) là authorization. ID chỉ là tham chiếu; quyền là quyết định riêng.

## 10. Các lỗi khiến test báo xanh nhưng production không được bảo vệ

### 10.1. Self-invocation bỏ qua proxy

Một bean có method được bảo vệ:

```java
@Service
public class ReportService {
    public String publicEntry() {
        return secretReport(); // lời gọi nội bộ qua this
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String secretReport() {
        return "sensitive";
    }
}
```

Trong mô hình proxy-based AOP mặc định, lời gọi `this.secretReport()` có thể **không đi qua proxy**; annotation không được thực thi cho lời gọi nội bộ đó. Nếu test chỉ gọi `reportService.secretReport()` qua bean proxy thì test pass, nhưng đường `publicEntry()` có thể bypass protection.

Giải pháp là thiết kế public entry point bảo vệ rõ ràng, tách secured method sang bean khác nếu phù hợp, và test **đường gọi thực tế**. Không chỉ dựa vào sự tồn tại của annotation trong source.

### 10.2. Unit test dùng new hoặc @InjectMocks

```java
DocumentService service = new DocumentService();
service.readOwnerPage("bob");
```

Đoạn này gọi Java object trực tiếp, **không có method-security interceptor**. Tương tự, một Mockito `@InjectMocks` service không tự được Spring method-security proxy bao. Unit test thuần rất có ích để kiểm tra business logic; nhưng **không phải test annotation authorization**. Khi cần xác minh proxy interceptor, dùng Spring context với `@EnableMethodSecurity` và lấy bean được quản lý.

### 10.3. Cấu hình test không bật method security

Nếu test slice chỉ load controller/repository mà không import config bật method security, negative case có thể không chạy đúng annotation. `@SpringBootTest` trong demo giúp có full context. Với test slice như `@WebMvcTest` hoặc context tối thiểu, cần import đúng configuration, bean và Spring Security test integration. Không suy diễn một test slice đã bao mọi tầng của production.

### 10.4. Sử dụng @WithMockUser nhưng cho rằng đã kiểm tra password

`@WithMockUser` bỏ qua login flow thật, không kiểm tra BCrypt, HTTP Basic, session cookie, OIDC token validation hoặc LDAP. Test method policy nên dùng nó để nhanh và rõ; test authentication phải có integration tests khác. **Đừng đánh đồng** “user mock có ROLE_ADMIN” với “provider production chắc chắn map role đúng”.

### 10.5. Chỉ test success, không test failure

Nếu tất cả test chạy với admin, bạn chưa kiểm tra ranh giới ownership. Dùng ma trận user cùng role nhưng owner khác; anonymous; user bị disable; object không tồn tại; tenant không khớp; authority thiếu. Với permission theo parameter, negative tests là phần quan trọng nhất.

### 10.6. @PostAuthorize để bảo vệ method ghi dữ liệu

Ví dụ nguy hiểm:

```java
@PostAuthorize("hasRole('ADMIN')")
public void sendTransfer() {
    transferClient.transferFunds();
}
```

Lời gọi chuyển tiền có thể đã xảy ra trước khi check; method `void` cũng không có return value hữu ích. Không dùng pattern này. Kiểm tra quyền **trước khi** thực thi side effect và ở tầng business/transaction phù hợp. Test phải chứng minh side effect không xảy ra khi user thiếu quyền.

## 11. Xử lý exception và HTTP status

Khi một method bị từ chối qua Spring Security method interceptor, thường phát sinh `AccessDeniedException` hoặc subtype tương thích. Direct service test có thể assert exception chính xác. Qua Servlet HTTP filter chain, `ExceptionTranslationFilter` có thể chuyển kết quả thành response, tùy authentication và entry point:

| Hoàn cảnh | Direct method invocation | HTTP qua cấu hình Basic của demo |
| --- | --- | --- |
| User authenticated, thiếu quyền method | `AccessDeniedException` | Thường 403 |
| User anonymous, route HTTP đã yêu cầu auth | Service có thể không được gọi | Thường 401 do Basic authentication entry point |
| User có quyền, method thực thi bình thường | Trả result | 200 nếu controller thành công |
| Document không tồn tại | `NoSuchElementException` của demo | 404 nhờ controller handler |
| Method business ném exception khác | Ngoại lệ theo method | Status tùy controller/error mapping |

**Trạng thái 403 từ MockMvc chưa tự chứng minh `@PreAuthorize` đã chạy**: request có thể bị chặn bởi URL rule, CSRF hoặc filter khác. Vì vậy nên có **direct service tests** bổ sung để chứng minh method interceptor hoạt động.

Các exception 403/401 cũng không tự bảo đảm response JSON đúng format của API; nếu yêu cầu thống nhất error body, cần cấu hình `AccessDeniedHandler`, `AuthenticationEntryPoint` và xử lý lỗi nghiệp vụ nhất quán, không leak thông tin nhạy cảm.

## 12. Mock user, UserDetails và test principal tùy chỉnh

Với hệ thống thật, principal có thể là custom `UserDetails`, `JwtAuthenticationToken`, `OidcUser` hoặc chứa tenant ID/permissions khác username. Một expression `principal.tenantId == #tenantId` sẽ cần dữ liệu principal phù hợp trong test.

Các hướng chính:

1. **`@WithMockUser`:** đủ cho rule về username, role, authority đơn giản.
2. **`@WithUserDetails`:** lấy principal qua `UserDetailsService` trong test context; hữu ích khi rule dùng fields trong `UserDetails` và cần phù hợp kiểu principal.
3. **`@WithSecurityContext` custom annotation:** xây dựng `Authentication`/principal đúng kiểu để test expression dùng domain claims; tránh tự giả dữ liệu trên request không được xác minh.
4. **HTTP MockMvc với `httpBasic(...)` hoặc security test request post-processors phù hợp:** kiểm thử integration layer.
5. **Test với token thật ở provider/decoder mock đáng tin hoặc test IdP:** khi cần xác minh cả mapping issuer, subject, scope và method security, không chỉ mock user.

Không đưa secrets, raw JWTs, refresh tokens hoặc thông tin thật vào test fixtures công khai. Sử dụng dữ liệu giả và kiểm tra phân quyền rỗng/khác role một cách tường minh.

## 13. Checklist hoàn chỉnh cho bài kiểm thử method security

- [ ] Ứng dụng bật `@EnableMethodSecurity` trong Spring context dùng khi test.
- [ ] Service là Spring-managed bean; method được gọi **qua proxy**, không phải `new`/self-invocation.
- [ ] Có ít nhất một positive và một negative test cho mỗi biểu thức `@PreAuthorize`/`@PostAuthorize`.
- [ ] Test `@PreAuthorize` xác minh method body hoặc side effect **không chạy** khi bị từ chối.
- [ ] Test `@PostAuthorize` hiểu rằng method đã chạy; dùng nó cho read-only result, không làm hàng rào duy nhất cho mutation.
- [ ] Test user có role tương tự nhưng **khác owner**, không chỉ so admin và anonymous.
- [ ] Test `@P`/parameter name discovery và compiler `-parameters` nếu phụ thuộc reflection.
- [ ] Test có/không có `ROLE_` prefix và `hasAuthority` theo đúng policy.
- [ ] Không cho anonymous bypass chỉ vì `authentication.name` khớp chuỗi tham số.
- [ ] Test tenant/object relationship, tránh BOLA khi client tự gửi ID.
- [ ] Test resource missing/null, error mapping, không tiết lộ thông tin object nhạy cảm.
- [ ] Test role/authority của principal custom hoặc OIDC/JWT theo trust boundary.
- [ ] Test trực tiếp service và HTTP layer riêng để phân biệt interceptor với URL filter.
- [ ] Test đường gọi nội bộ/self-invocation và các entry points có thể bỏ qua proxy.
- [ ] Giữ mock data ổn định, không dùng user thật/secrets trong test source.
- [ ] Với hành vi ghi DB, dùng transaction và xác minh không có side effect nếu bị từ chối.

## 14. Tự kiểm tra

**1.** `@PreAuthorize` và `@PostAuthorize` khác nhau ở đâu?  
**Đáp án:** pre kiểm tra trước body; post kiểm tra sau khi body trả result và có thể dùng `returnObject`. Post không thể bảo đảm side effects chưa diễn ra.

**2.** Tại sao `@WithMockUser(username="alice")` đọc `/owners/bob` phải fail?  
**Đáp án:** method rule so sánh owner argument từ request với `authentication.name`; alice và bob khác nhau, và user không phải admin.

**3.** Có `ROLE_ADMIN` nhưng viết `hasAuthority('ADMIN')` thì có chắc pass?  
**Không.** `hasAuthority` so khớp chính xác; `hasRole('ADMIN')` thường thêm prefix `ROLE_`.

**4.** Dùng `new DocumentService()` để test `@PreAuthorize` được không?  
**Không đủ.** Lời gọi trực tiếp không có Spring interceptor; cần test qua Spring-managed proxy.

**5.** Vì sao một câu lệnh DELETE không nên chỉ có `@PostAuthorize`?  
**Đáp án:** DELETE có thể đã xảy ra trước khi post check. Kiểm tra quyền trước mutation và test không có side effect.

**6.** Dùng `@WithMockUser` có chứng minh user đăng nhập HTTP Basic thật được không?  
**Không.** Đây là mocked security context, không xác thực password. Cần HTTP authentication integration test riêng.

**7.** Nếu service chỉ được gọi qua `this.securedMethod()` thì điều gì có thể xảy ra?  
**Đáp án:** self-invocation thường không đi qua Spring proxy, có thể bỏ qua method-security interceptor. Test đường thực tế.

**8.** Kiểm thử method ownership cần quan tâm điều gì ngoài username?  
**Đáp án:** owner object và tenant thực tế, account state, null/missing object, policy thay đổi, thời điểm kiểm tra và IDOR/BOLA.

## Kết luận

`@PreAuthorize` bảo vệ **trước khi** method chạy và phù hợp với kiểm tra role, authority, tham số hoặc policy bean. `@PostAuthorize` kiểm tra **kết quả sau khi** method chạy, thích hợp cho một số phép đọc khi quyền phụ thuộc `returnObject`, nhưng không bảo vệ khỏi side effect đã xảy ra.

Một bộ kiểm thử đáng tin phải gọi **Spring-managed proxy** với `@EnableMethodSecurity`, có cả positive/negative test cho owner, admin, anonymous và tham số, dùng `@WithMockUser` cho method expressions, bổ sung MockMvc cho HTTP behavior, và kiểm tra self-invocation, parameter discovery, role prefix và object-level authorization. Quan trọng nhất: **HTTP 403 là một kết quả quan sát được, còn bằng chứng method security đúng cần test chính interceptor và các tác động trước/sau lời gọi.**
