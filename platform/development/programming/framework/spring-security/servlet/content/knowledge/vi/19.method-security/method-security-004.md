# @PostAuthorize và kiểm tra đối tượng sau khi phương thức trả về

> **Phạm vi:** Spring Security 6 trên Servlet stack, Java 17+ và Spring MVC. Chủ đề chính là `@PostAuthorize`: kiểm tra quyền **sau khi phương thức trả về** thông qua giá trị `returnObject` trong Spring Expression Language (SpEL). Bài phân biệt `@PreAuthorize`, `@PostAuthorize` và `@PostFilter`, trình bày cách kiểm tra chủ sở hữu tài liệu, các giới hạn của việc chặn sau khi method chạy, và ví dụ Spring Boot 3.3.5 có thể chạy với `MockMvc`.

## 1. Tại sao cần phân quyền sau khi tải đối tượng?

Giả sử hệ thống lưu tài liệu:

- Alice có quyền đọc tài liệu do **Alice sở hữu**.
- Bob có quyền đọc tài liệu do **Bob sở hữu**.
- Auditor có quyền kiểm toán nên được đọc cả tài liệu của Alice và Bob.
- Guest không có quyền đọc tài liệu.
- Một user đã đăng nhập nhưng không phải chủ sở hữu cần bị từ chối dù mật khẩu đúng.

Các bản ghi ví dụ:

| ID | ownerUsername | Title |
| --- | --- | --- |
| 42 | `alice` | Alice private report |
| 43 | `bob` | Bob private note |

Request `GET /documents/42` chỉ mang ID 42. Không thể biết quyền sở hữu chỉ từ URL; phải **tải document từ nguồn server tin cậy**, lấy thuộc tính owner thực tế, rồi so với identity của user. Nếu client tự khai `X-Owner: alice` và ứng dụng tin ngay, đó không phải cơ chế bảo mật.

Với `@PostAuthorize`, Spring Security có thể kiểm tra **object mà service vừa trả về** trước khi object đó được chuyển lại cho controller:

```text
GET /documents/42 + Basic credentials
        |
        v
Authentication filter kiểm chứng username/password
        |
        v
AuthorizationFilter kiểm tra HTTP policy
        |
        v
Controller gọi Spring-managed DocumentService bean
        |
        +--> @PreAuthorize: kiểm tra quyền loại thao tác
        |
        v
DocumentService.findDocument(42)
  - truy xuất document từ nguồn server
  - trả DocumentView(id=42, ownerUsername=alice, ...)
        |
        v
@PostAuthorize kiểm tra returnObject
        |
        +-- Owner alice hoặc có DOCUMENT_AUDIT -> GRANT
        |                                  |
        |                                  v
        |                             Controller nhận DTO -> HTTP 200
        |
        +-- Bob, không phải owner, không có audit -> DENY
                                           |
                                           v
                                       thường HTTP 403
```

**Thời điểm là điểm mấu chốt:** `@PostAuthorize` chạy **sau khi body của method đã thực thi**. Nó bảo vệ việc **trả kết quả cho caller**, không tự ngăn tác dụng phụ đã được tạo trong body method.

## 2. @PostAuthorize là gì?

`@PostAuthorize` là annotation của Spring Security method authorization. Nó dùng một biểu thức SpEL để quyết định một lời gọi method **có được phép trả kết quả vừa tạo ra** hay không.

Ví dụ tối giản:

```java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentView findDocument(long id) {
    return documentRepository.findById(id);
}
```

Đây là **fragment giải thích**; nó chưa phải một chương trình Java độc lập vì `DocumentView` và `documentRepository` còn phải được định nghĩa. Ví dụ chạy đầy đủ nằm ở mục 9.

Trong biểu thức trên:

- `returnObject` là giá trị return thực tế mà method vừa tạo.
- `returnObject.ownerUsername` là một property trên object, thường được SpEL đọc qua getter `getOwnerUsername()`.
- `authentication` là `Authentication` hiện tại từ Spring Security context.
- `authentication.name` thường là kết quả `Authentication.getName()`, tức định danh người dùng.
- `==` là phép so sánh trong SpEL, không phải cơ chế xác minh mật khẩu hay chữ ký token.

Nếu document thuộc user hiện tại, kết quả được phép đi tới caller. Nếu không, Spring Security phát sinh access-denied behavior. Với người dùng đã xác thực qua HTTP Basic, kết quả HTTP thường là **403 Forbidden**.

### API và các lớp liên quan

| Thành phần | Công việc |
| --- | --- |
| `@EnableMethodSecurity` | Kích hoạt infrastructure method-security trên Spring-managed beans |
| `@PostAuthorize` | Định nghĩa biểu thức phân quyền **sau** method |
| `@PreAuthorize` | Định nghĩa biểu thức phân quyền **trước** method |
| `AuthorizationManagerAfterMethodInterceptor` | Một thành phần method-security trong Spring Security 6 để đánh giá kiểm tra sau lời gọi |
| `PostAuthorizeAuthorizationManager` | Logic quản lý quyền tương ứng với biểu thức PostAuthorize |
| `SecurityContextHolder` | Giữ context và `Authentication` cho xử lý hiện tại |
| `AccessDeniedException` | Nhóm exception từ chối quyền được xử lý bởi security/exception handling |
| `ExceptionTranslationFilter` | Ở HTTP Servlet flow, chuyển lỗi access denied/chưa authenticated thành entry point hoặc access-denied response |
| `AuthorizationFilter` | Áp dụng policy HTTP path, **khác** với method-security interceptors |

`@PostAuthorize` **không phải một Servlet filter**. Nó áp dụng tại lời gọi method thông qua Spring AOP/advisor, có thể bảo vệ logic được tái sử dụng bởi các controller khác.

## 3. Khác biệt giữa @PreAuthorize, @PostAuthorize và @PostFilter

| Annotation | Thời điểm | Dữ liệu sẵn có | Ý nghĩa chính |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước khi body method chạy | Principal, authorities, method arguments | Có được **gọi** method không? |
| `@PostAuthorize` | Sau khi body method trả kết quả thành công | Các thông tin trên **và returnObject** | Có được **nhận kết quả** không? |
| `@PostFilter` | Sau khi method trả collection/kiểu hỗ trợ | `filterObject` từng phần tử | Giữ/bỏ các phần tử theo rule |
| `@PreFilter` | Trước method, với input collection phù hợp | `filterObject` từ đối số | Lọc input trước khi body chạy |

Ví dụ hai ràng buộc bổ sung:

```java
@PreAuthorize("hasAnyAuthority('DOCUMENT_READ','DOCUMENT_AUDIT')")
@PostAuthorize("hasAuthority('DOCUMENT_AUDIT') or " +
               "returnObject.ownerUsername == authentication.name")
public DocumentView findDocument(long id) {
    // Lấy document từ server-side store.
}
```

Ở đây **@PreAuthorize** chặn user không có permission đọc trước khi truy vấn. **@PostAuthorize** kiểm tra document cụ thể vừa được tải. Hai điều kiện này đều cần đạt; auditor có nhánh ngoại lệ được cấp có chủ đích.

Các bước cho Bob:

```text
Bob đã login, có DOCUMENT_READ
   -> HTTP authenticated(): grant
   -> PreAuthorize có DOCUMENT_READ: grant
   -> method tải document 42: ownerUsername=alice
   -> PostAuthorize: không có DOCUMENT_AUDIT và bob != alice
   -> deny, controller không nhận document, HTTP thường 403
```

Bob có mật khẩu đúng nên **không nhận 401** vì sai credentials; đây là **authorization failure**, không phải authentication failure.

### Đừng nhầm PostAuthorize với lọc danh sách

Một method trả `List<DocumentView>` không được `@PostAuthorize` tự động lọc theo owner từng item. Annotation này quyết định **toàn bộ return object**, còn `@PostFilter` có thể lọc các phần tử của kiểu collection được hỗ trợ:

```java
// Fragment minh họa: không phải thiết kế tối ưu khi dữ liệu nhiều.
@PostFilter("filterObject.ownerUsername == authentication.name")
public List<DocumentView> findAllDocuments() {
    return repository.findAll();
}
```

Nhược điểm: service **đã tải tất cả tài liệu** rồi mới lọc. Điều này có thể làm rò rỉ qua logs, tốn bộ nhớ, gây sai lệch pagination/total count, hoặc vượt ranh giới tenant trong các nhánh khác. Với ứng dụng thực tế, **ưu tiên truy vấn có điều kiện owner/tenant được kiểm chứng ngay tại database**, sau đó dùng method security như lớp bảo vệ bổ sung.

## 4. Cách viết biểu thức với returnObject

Ví dụ các biểu thức phụ thuộc return value:

| Biểu thức SpEL | Ý nghĩa |
| --- | --- |
| `returnObject.ownerUsername == authentication.name` | User hiện tại là chủ sở hữu của result |
| `hasAuthority('DOCUMENT_AUDIT') or returnObject.ownerUsername == authentication.name` | Auditor **hoặc** owner được nhận object |
| `returnObject.tenantId == principal.tenantId` | Result cùng tenant được gắn trên principal đáng tin |
| `returnObject != null and returnObject.ownerUsername == authentication.name` | Chỉ cho phép object khác null và thuộc user |
| `returnObject.isPublic() or hasRole('ADMIN')` | Public object hoặc user có role admin, nếu class/role mapping thực sự hỗ trợ |

Một số lưu ý:

1. **Tên property phải có thật.** Nếu DTO có `getOwnerUsername()`, dùng `ownerUsername`; không viết `returnObject.owner` khi class không có property owner.
2. **Không tin dữ liệu client** để xác định owner/tenant. Result cần đến từ server-side repository hoặc nguồn xác thực đáng tin.
3. **Tài khoản đa tenant:** so username đơn lẻ có thể không đủ nếu cùng username xuất hiện ở các tổ chức. Khi đó dùng stable user ID, tenant ID, membership và service policy đáng tin.
4. **Null:** nếu method trả null mà biểu thức dereference property, có thể phát sinh lỗi expression. Hãy xác định contract not-found rõ ràng.
5. **Optional:** nếu method trả `Optional<DocumentView>`, `returnObject` đại diện cho wrapper, không phải mặc định là `DocumentView`. Cần xử lý Optional trong biểu thức/bean policy hoặc đổi API trả DTO và ném 404.
6. **Collection:** PostAuthorize quyết định toàn bộ result; không ngầm lặp qua từng item.
7. **Getter side effects:** tránh getter tự gọi remote service hoặc thay đổi state; SpEL có thể truy cập getter khi đánh giá.

### DTO JavaBean rõ ràng

```java
public final class DocumentView {
    private final long id;
    private final String ownerUsername;

    public DocumentView(long id, String ownerUsername) {
        this.id = id;
        this.ownerUsername = ownerUsername;
    }

    public long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }
}
```

Đây là fragment một DTO độc lập về mặt cú pháp class, chưa cung cấp package/build. Các JavaBean getters làm cách đọc property trong SpEL và JSON serializer dễ hiểu. Project runnable bên dưới có class DTO với cả title.

### Nên xử lý tài liệu không tồn tại bằng lỗi riêng

```java
DocumentView result = repository.findById(id);
if (result == null) {
    throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found");
}
return result;
```

Fragment này cho thấy service **ném 404 trước khi trả null**. Khi method ném exception thay vì trả giá trị thành công, `@PostAuthorize` không có kết quả thành công để kiểm tra. Đây là cách tránh lỗi SpEL trên null và giữ hợp đồng API minh bạch, dù cách trả 403/404 còn cần đánh giá về việc tiết lộ existence của tài nguyên.

## 5. Luồng xử lý security: từ URL tới method

Với một Spring MVC request:

```text
HTTP GET /documents/42
         |
         v
Servlet FilterChainProxy -> SecurityFilterChain
         |
         v
BasicAuthenticationFilter
  - đọc header Basic
  - AuthenticationManager/Provider kiểm tra mật khẩu
  - đưa Authentication vào SecurityContext
         |
         v
AuthorizationFilter
  - /documents/{id} yêu cầu authenticated()
         |
         v
DispatcherServlet -> DocumentController
         |
         v
Proxy của DocumentService
         |
         +--> PreAuthorizeAuthorizationManager
         |      - Kiểm tra DOCUMENT_READ hoặc DOCUMENT_AUDIT
         |      - Deny => method không chạy
         |
         v
Target method findDocument(42)
  - đọc Map/DB
  - tạo DocumentView
  - trả object
         |
         +--> PostAuthorizeAuthorizationManager / after interceptor
         |      - returnObject.ownerUsername so với Authentication
         |      - Grant hoặc Deny
         |
         v
Caller nhận DTO hoặc exception
         |
         v
HTTP 200, 403 hoặc các lỗi riêng như 404
```

Nếu request thiếu Basic credentials, HTTP rule `authenticated()` có thể chặn sớm; Basic entry point thường trả **401 Unauthorized** cùng `WWW-Authenticate`. Nếu credentials hợp lệ nhưng policy method từ chối, HTTP thường trả **403 Forbidden**. Status cụ thể còn phụ thuộc authentication entry point, exception handler và cấu hình filter chain.

**SecurityContext của request hiện tại không đồng nghĩa session login lâu dài.** Trong demo, `SessionCreationPolicy.STATELESS` không lấy authentication từ HTTP session; nhưng method-security vẫn dùng được vì Basic filter xác thực **request hiện tại**.

## 6. Tại sao PostAuthorize không phải giải pháp an toàn cho thao tác ghi?

Đây là sai lầm quan trọng nhất cần tránh. Với `@PostAuthorize`, **method body đã thực thi** trước khi quyền được kiểm tra. Nếu body thay đổi database, gửi email, ghi Kafka event hoặc gọi hệ thống thanh toán, response 403 **không đảm bảo** các thay đổi đã được rollback.

### Phản ví dụ

```java
// PHẢN MẪU: không đưa vào production.
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentView deleteDocument(long id) {
    DocumentView result = repository.deleteAndReturn(id);
    emailService.sendDeletionNotice(result);
    return result;
}
```

Giả sử Bob gọi xóa document của Alice:

1. Method xóa tài liệu.
2. Method gửi email thông báo.
3. Method trả lại object đã xóa.
4. `@PostAuthorize` phát hiện owner không phải Bob và từ chối.
5. Response có thể là 403, **nhưng tài liệu/email đã bị tác động**.

Một số transaction có thể rollback trong cấu hình/order cụ thể, nhưng không thể dựa vào điều đó như cơ chế bảo mật mặc định: transaction advice có thứ tự, external side effects không tham gia rollback và các thay đổi đã commit không tự đảo ngược.

### Thiết kế đúng hơn

```text
POST/DELETE request
   |
   v
@PreAuthorize kiểm tra permission thao tác
   |
   v
Service + transaction:
   - Đọc resource thật với tenant/owner/scope từ server
   - Kiểm tra lại permission và domain state trước khi mutate
   - Dùng lock / optimistic locking / conditional update khi cần
   - Thực hiện thay đổi trong transaction
   - Audit/outbox event theo policy
   |
   v
Trả kết quả
```

Với các nghiệp vụ nhạy cảm như phê duyệt đơn, chuyển tiền hoặc xóa hồ sơ, **ưu tiên kiểm tra quyền trước hành động**, kết hợp domain-level checks trong transaction để tránh lỗi **TOCTOU (time of check/time of use)**. Không sử dụng PostAuthorize như hàng rào duy nhất.

## 7. @EnableMethodSecurity, proxy và self-invocation

Spring Security 6 thường bật method authorization qua:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // SecurityFilterChain, UserDetailsService, ...
}
```

Hoặc viết tường minh:

```java
@EnableMethodSecurity(prePostEnabled = true)
```

Các imports:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

`@EnableWebSecurity` và HTTP `SecurityFilterChain` không tự thay thế `@EnableMethodSecurity`. Nếu method security chưa được bật, annotation có thể nằm trong code nhưng không có interceptor thực thi.

### Gọi qua Spring-managed bean

Method security dựa vào Spring proxy/advice trong cấu hình phổ biến:

- Service cần là bean được Spring quản lý (ví dụ `@Service`).
- Controller nhận service qua constructor injection.
- Lời gọi phải đi qua bean/proxy do Spring cung cấp.
- Không tự `new DocumentService()` rồi mong annotation hoạt động.
- Cẩn trọng với private/final methods, proxy configuration và class/method không được intercept.
- Không mặc định gọi method từ cùng một class cũng qua proxy.

Phản mẫu self-invocation:

```java
@Service
public class DocumentService {
    public DocumentView outer(long id) {
        return this.findDocument(id);
    }

    @PostAuthorize("returnObject.ownerUsername == authentication.name")
    public DocumentView findDocument(long id) {
        return repository.load(id);
    }
}
```

Đây là **fragment phản mẫu**, cần repository/DTO để compile. Lời gọi `this.findDocument(id)` ở cùng object có thể bỏ qua AOP proxy trong mode proxy thông thường; `@PostAuthorize` không chạy. Nên để một Spring bean khác gọi injected DocumentService, hoặc thiết kế khác có kiểm tra bảo mật đáng tin.

**Kiểm thử thực tế rất quan trọng:** test “Alice được 200” không đủ, vì một service không có method security cũng cho Alice 200. Test “Bob bị 403 khi đọc tài liệu Alice” mới có khả năng bắt lỗi thiếu proxy/annotation.

## 8. Chính sách chủ sở hữu: role/permission và exception kiểm toán

Với document 42 của Alice và document 43 của Bob:

```text
User alice:
  authorities = [DOCUMENT_READ]

User bob:
  authorities = [DOCUMENT_READ]

User auditor:
  authorities = [DOCUMENT_AUDIT]

User guest:
  authorities = [ROLE_GUEST]
```

Chính sách:

```text
PRE:
    user has DOCUMENT_READ OR DOCUMENT_AUDIT

POST:
    user has DOCUMENT_AUDIT
    OR document.ownerUsername == authentication.name

FINAL:
    PRE AND POST
```

Kết quả dự kiến:

| Người gọi / document | Pre check | Post check | Outcome |
| --- | --- | --- | --- |
| Alice /42 | Grant: READ | Grant: owner Alice | 200 |
| Alice /43 | Grant: READ | Deny: owner Bob | 403 |
| Bob /42 | Grant: READ | Deny: owner Alice | 403 |
| Bob /43 | Grant: READ | Grant: owner Bob | 200 |
| Auditor /42 | Grant: AUDIT | Grant: AUDIT | 200 |
| Guest /42 | Deny: no permission | Method không chạy | 403 |
| Anonymous /42 | HTTP deny | Method không chạy | 401 với Basic |
| Alice /999 | Grant | Method ném 404 | 404 |

Điểm cần chú ý: role `ROLE_GUEST` không tự được mapping thành `DOCUMENT_READ`. Tương tự, một role `ROLE_ADMIN` không tự có wildcard permission nếu ứng dụng chưa định nghĩa/mapping quyền đó. Đừng dùng client-supplied roles hoặc header `X-Admin: true` để cấp quyền.

### Nếu ownerUsername không unique xuyên tenant

Trong hệ thống multi-tenant, hai người cùng username ở hai tenant khác nhau có thể tồn tại. So một chuỗi username **không đủ** để tách dữ liệu. Cần dùng user ID được kiểm chứng, tenant ID đáng tin, resource scope, membership và security policy trong service/DB. Rule kiểu `ownerUsername == authentication.name` chỉ thích hợp khi identity namespace và ownership model thực sự như vậy.

## 9. Project runnable: Spring Boot 3.3.5, Java 17 và MockMvc

Ví dụ dưới đây sử dụng Spring MVC Servlet, HTTP Basic, method security và một Map bất biến chứa hai document. Vì mục tiêu là phân quyền sau khi **đọc**, không có mutation hoặc side effects.

### 9.1. Cấu trúc thư mục

```text
post-authorize-demo/
├── pom.xml
├── src/main/java/example/postauthorize/
│   ├── PostAuthorizeApplication.java
│   ├── SecurityConfig.java
│   ├── DocumentService.java
│   └── DocumentController.java
└── src/test/java/example/postauthorize/
    └── DocumentAuthorizationTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>post-authorize-demo</artifactId>
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

### 9.3. PostAuthorizeApplication.java

```java
package example.postauthorize;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PostAuthorizeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.postauthorize;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo123");
        return new InMemoryUserDetailsManager(
            User.withUsername("alice").password(hash)
                .authorities("DOCUMENT_READ").build(),
            User.withUsername("bob").password(hash)
                .authorities("DOCUMENT_READ").build(),
            User.withUsername("auditor").password(hash)
                .authorities("DOCUMENT_AUDIT").build(),
            User.withUsername("guest").password(hash)
                .authorities("ROLE_GUEST").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/documents/{id}")
                    .authenticated()
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache ->
                cache.requestCache(new NullRequestCache()));

        // Chỉ dùng Basic; không redirect sang form login trong demo.
        http.formLogin(form -> form.disable());

        // Giữ CSRF mặc định: những endpoint demo chỉ dùng GET.
        return http.build();
    }
}
```

Các chú ý:

1. `@EnableMethodSecurity` kích hoạt @PreAuthorize và @PostAuthorize trên service Spring bean.
2. HTTP rule `authenticated()` chỉ chứng minh danh tính hợp lệ, **không tự quyết định owner**.
3. `httpBasic` cho phép test từng request với username/password. HTTP Basic **không an toàn qua mạng không mã hóa**; `localhost` ở đây chỉ là lab, production dùng HTTPS.
4. `STATELESS` không lấy `SecurityContext` từ HTTP session, nhưng authentication vẫn tồn tại trong request hiện tại và được method security sử dụng.
5. `NullRequestCache` tránh lưu URL cần login cho browser form-login flow; project này không có form login.
6. CSRF vẫn giữ mặc định, và demo chỉ có GET. Nếu thêm POST/DELETE, phải áp dụng CSRF phù hợp với cách client gửi credentials; không disable bừa bãi.
7. `UserDetailsService` in-memory/hash chung chỉ dùng để dạy; production cần nguồn tài khoản, quyền và password-hash bền vững và an toàn.

### 9.5. DocumentService.java

```java
package example.postauthorize;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final Map<Long, DocumentView> documents = Map.of(
            42L, new DocumentView(42L, "alice", "Alice private report"),
            43L, new DocumentView(43L, "bob", "Bob private note")
    );

    @PreAuthorize("hasAnyAuthority('DOCUMENT_READ', 'DOCUMENT_AUDIT')")
    @PostAuthorize("hasAuthority('DOCUMENT_AUDIT') or " +
                   "returnObject.ownerUsername == authentication.name")
    public DocumentView findDocument(long id) {
        DocumentView result = documents.get(id);
        if (result == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
        }
        return result;
    }

    // Immutable DTO với JavaBean getters để SpEL và Jackson đọc property.
    public static final class DocumentView {
        private final long id;
        private final String ownerUsername;
        private final String title;

        public DocumentView(long id, String ownerUsername, String title) {
            this.id = id;
            this.ownerUsername = ownerUsername;
            this.title = title;
        }

        public long getId() {
            return id;
        }

        public String getOwnerUsername() {
            return ownerUsername;
        }

        public String getTitle() {
            return title;
        }
    }
}
```

Đối với Alice gọi ID 42, cả pre/post đều grant. Đối với Bob gọi ID 42, pre grant nhưng post deny vì owner của object là Alice. Đối với guest, pre deny và method **không chạy**. Auditor được đọc nhờ `DOCUMENT_AUDIT` ở cả pre/post. Method với ID 999 ném 404 chứ không trả null.

**Chỉ có side effect đọc dữ liệu:** `Map.of` chứa bản ghi bất biến, giúp tập trung vào semantics của PostAuthorize. Trong production, `DocumentService` thường gọi database/repository có điều kiện tenant, owner và transaction/lazy-loading rõ ràng.

### 9.6. DocumentController.java

```java
package example.postauthorize;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/documents/{id}")
    public DocumentService.DocumentView getDocument(@PathVariable long id) {
        return documents.findDocument(id);
    }
}
```

Controller gọi service **qua dependency injection**. Khi Spring tạo method-security proxy cho service, `documents.findDocument(id)` sẽ đi qua interceptors. Nếu quyền bị từ chối, DTO **không đi tới bước Jackson serialize**. Không tự `new DocumentService()` trong controller.

### 9.7. DocumentAuthorizationTest.java

```java
package example.postauthorize;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public:ok"));
    }

    @Test
    void anonymousCannotReadDocument() throws Exception {
        mvc.perform(get("/documents/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerOwnDocument() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("alice"))
                .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void bobCannotReadAliceDocument() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadAcrossOwners() throws Exception {
        mvc.perform(get("/documents/43")
                .with(httpBasic("auditor", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("bob"));
    }

    @Test
    void guestIsDeniedByPreAuthorize() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("guest", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingIdReturnsNotFoundForReader() throws Exception {
        mvc.perform(get("/documents/999")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongPasswordGetsUnauthorized() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Vì `httpBasic(...)` gửi header Basic đến MockMvc, tests kiểm tra cả bước authentication và policy thực tế trong security chain/method proxy. Đây không phải benchmark hiệu năng. Đặc biệt **test Bob nhận 403** là regression test quan trọng: nếu `@EnableMethodSecurity` bị bỏ đi hoặc lời gọi bypass proxy, test này có khả năng phát hiện policy không được thực thi.

### 9.8. Chạy

Dùng JDK 17+, Maven trong thư mục có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` chạy JUnit/MockMvc; `mvn spring-boot:run` chạy ứng dụng. Với cấu hình mặc định, embedded Tomcat phục vụ tại `http://localhost:8080`. Chỉ dùng HTTP Basic qua HTTP thuần ở localhost cho bài học; triển khai thật phải dùng **HTTPS**.

## 10. Kiểm tra HTTP bằng curl

### 10.1. Public 200

```bash
curl -s http://localhost:8080/public
```

Body dự kiến:

```text
public:ok
```

### 10.2. Anonymous 401

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/documents/42
```

Output:

```text
401
```

Người dùng chưa gửi Basic credentials, nên tầng HTTP chặn **trước** khi gọi method.

### 10.3. Alice được đọc tài liệu 42: 200

```bash
curl -s -u alice:demo123 http://localhost:8080/documents/42
```

JSON dự kiến:

```json
{"id":42,"ownerUsername":"alice","title":"Alice private report"}
```

### 10.4. Bob không được đọc tài liệu 42: 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:demo123 http://localhost:8080/documents/42
```

Output:

```text
403
```

Bob có `DOCUMENT_READ`, nhưng không phải owner Alice; `@PostAuthorize` deny sau khi method tải result. **403 không có nghĩa Bob nhập sai mật khẩu**.

### 10.5. Auditor được đọc tài liệu 42: 200

```bash
curl -s -u auditor:demo123 http://localhost:8080/documents/42
```

JSON:

```json
{"id":42,"ownerUsername":"alice","title":"Alice private report"}
```

Auditor vượt qua nhánh `DOCUMENT_AUDIT` của cả @PreAuthorize và @PostAuthorize.

### 10.6. Guest bị chặn trước method: 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u guest:demo123 http://localhost:8080/documents/42
```

Output:

```text
403
```

Guest đã xác thực, nhưng thiếu cả DOCUMENT_READ lẫn DOCUMENT_AUDIT, nên `@PreAuthorize` deny.

### 10.7. ID không tồn tại: 404

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:demo123 http://localhost:8080/documents/999
```

Output:

```text
404
```

Đây là nhánh `ResponseStatusException(HttpStatus.NOT_FOUND)` từ service, không phải PostAuthorize trên một object null.

### 10.8. Sai mật khẩu: 401

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:incorrect http://localhost:8080/documents/42
```

Output:

```text
401
```

### Bảng kỳ vọng tổng hợp

| Request | HTTP authentication | @PreAuthorize | @PostAuthorize | Kết quả |
| --- | --- | --- | --- | --- |
| GET /public anonymous | Không cần | Không áp dụng | Không áp dụng | 200 |
| GET /documents/42 anonymous | Không có | Không chạy | Không chạy | 401 |
| GET /documents/42 alice | Hợp lệ | Grant | Owner grant | 200 |
| GET /documents/42 bob | Hợp lệ | Grant | Owner deny | 403 |
| GET /documents/42 auditor | Hợp lệ | Grant | Audit grant | 200 |
| GET /documents/42 guest | Hợp lệ | Deny | Không chạy | 403 |
| GET /documents/999 alice | Hợp lệ | Grant | Method ném 404 | 404 |
| GET /documents/42 alice sai password | Thất bại | Không chạy | Không chạy | 401 |

Những status và body này là **kỳ vọng của ứng dụng demo**, không phải cam kết rằng mọi cấu hình Spring Security đều có cùng entry point/exception handler. Với form login, thiếu authentication có thể thành **302 redirect** thay cho 401.

## 11. Tài liệu tồn tại nhưng không được phép: 403 hay 404?

Trong ví dụ, Bob đọc document 42 (có tồn tại) thì 403; truy cập ID 999 thì 404. Một attacker có thể dùng sự khác nhau để suy luận **ID nào tồn tại**. Đây là rủi ro thông tin existence trong một số hệ thống.

Các hướng thiết kế:

1. Giữ 403/404 theo hợp đồng API khi resource existence không nhạy cảm và có audit đầy đủ.
2. Với dữ liệu nhạy cảm, query trực tiếp theo scope user/tenant, nếu không thấy trong phạm vi hợp lệ thì trả not-found đồng nhất.
3. Thiết kế custom access-denied handling có kiểm soát nếu sản phẩm yêu cầu che giấu existence, nhưng tránh map mọi lỗi thành 404 thiếu phân tích.
4. Không trả DTO hoặc message chứa title/owner cho user không có quyền.
5. Test cả **non-owner** và **nonexistent ID** để kiểm tra response policy.

Pseudo-query có điều kiện:

```text
findByIdAndTenantIdAndOwnerId(
    documentId,
    trustedTenantIdFromPrincipal,
    trustedUserIdFromPrincipal)
```

Đây là mô tả ý tưởng, không phải method có sẵn tự động của mọi repository. Nếu auditor cần quyền xem tất cả, phải có truy vấn/policy riêng được cấp rõ ràng.

## 12. Multi-tenant, JPA lazy loading và hiệu năng

### Multi-tenant

So `ownerUsername == authentication.name` chỉ phù hợp khi tên này đủ duy nhất và là principal đáng tin trong nghiệp vụ. Đối với hệ thống nhiều tenant, ưu tiên kiểm tra:

```text
user has DOCUMENT_READ
AND document.tenantId == trustedPrincipal.tenantId
AND document.ownerId == trustedPrincipal.userId
```

Có thể dùng bean policy:

```java
// Fragment minh họa: cần bean documentPolicy thật.
@PostAuthorize("@documentPolicy.canRead(authentication, returnObject)")
public DocumentView findDocument(long id) {
    return repository.load(id);
}
```

Bean `documentPolicy` phải so owner/tenant theo dữ liệu server, không chỉ tin `X-Owner: true` hoặc `X-Tenant-Id` client tự gửi. Với user có nhiều tenant, membership/allowedTenants cần đến từ nguồn đã kiểm chứng.

### JPA lazy loading

Nếu `returnObject` là JPA entity và biểu thức đọc `returnObject.owner.username`, việc đánh giá có thể kích hoạt **lazy loading**. Nếu persistence context đã đóng, có thể có lỗi; nếu chưa đóng, có thể tạo thêm truy vấn khó dự đoán. Một DTO/projection chứa trường owner/tenant cần thiết thường dễ kiểm thử hơn. Khi cần logic phức tạp, policy bean có thể truy vấn repository với scope rõ ràng.

### Chi phí đọc trước khi được từ chối

Bob có permission DOCUMENT_READ vẫn làm method tải document 42 trước lúc PostAuthorize deny. Với tài liệu cực lớn hoặc database/remote API tốn kém, cân nhắc kiểm tra owner từ metadata ít tốn hơn trước khi tải payload, hoặc thực hiện query theo owner/tenant ngay từ đầu.

**PostAuthorize không phải chiến lược tối ưu hóa data access.** Nó là một lớp authorization dựa trên return object; hiệu năng và hạn chế lộ thông tin ở tầng data vẫn cần giải quyết.

## 13. Optional, collection, async và giá trị trả về khác

### Optional

Nếu method trả `Optional<DocumentView>`, `returnObject` là Optional wrapper. Biểu thức `returnObject.ownerUsername` không đọc trực tiếp owner của DocumentView. Nên dùng policy method hỗ trợ kiểu Optional hoặc đổi service contract thành DTO/ném 404. Không bỏ qua null/empty path.

### List / Page

Với `List<DocumentView>`, PostAuthorize cho phép hoặc từ chối cả collection. Nếu muốn lọc từng phần tử sau khi method trả về, `@PostFilter` có thể là lựa chọn cho các kiểu được hỗ trợ, nhưng không thay thế query có scope. Với phân trang, lọc sau tải có thể làm `totalElements`, offset/size và thứ tự không nhất quán.

### Async / reactive

Nếu method trả `CompletableFuture` hoặc publisher, thời điểm object được trả trong Java không nhất thiết là thời điểm dữ liệu bất đồng bộ hoàn tất. Reactive method security và Servlet synchronous method security có hỗ trợ/sự khác biệt riêng. Bài tập này chỉ áp dụng **method đồng bộ trong ứng dụng Spring MVC Servlet**. Không copy biểu thức và tự suy đoán nó kiểm tra value bên trong publisher trong mọi phiên bản.

### Method trả void

Một method `void` không có return data hữu ích để kiểm tra owner. Nếu thực hiện mutation, càng không nên trông chờ PostAuthorize. Dùng `@PreAuthorize` và domain validation trước side effects.

## 14. Testing trực tiếp method-security proxy

MockMvc kiểm tra toàn bộ request qua security chain. Nếu muốn tách việc kiểm tra method khỏi HTTP Basic, bạn có thể viết integration test inject service bean và đặt test authentication bằng `@WithMockUser`:

```java
// Fragment bổ sung trong @SpringBootTest có injected DocumentService documents.
@Test
@WithMockUser(username = "bob", authorities = "DOCUMENT_READ")
void bobCannotReadAliceDocumentViaServiceProxy() {
    assertThatThrownBy(() -> documents.findDocument(42L))
            .isInstanceOf(AccessDeniedException.class);
}
```

Đây là **fragment**, cần imports `@WithMockUser`, `@Test`, `AccessDeniedException` và AssertJ `assertThatThrownBy`, cùng bean `documents`. Nó kiểm tra trực tiếp proxy advice thay vì đi qua controller. `@WithMockUser` không xác minh password thật; nếu muốn kiểm thử cả provider, dùng `httpBasic(...)` như bộ test runnable mục 9.

**Điểm QA quan trọng:** chỉ kiểm tra case grant không phát hiện method security bị vô hiệu. Phải có ít nhất một case **deny** (Bob non-owner và guest no permission) và một case **allow** (Alice owner hoặc auditor).

## 15. Bảo mật tổng thể và cách debug

`@PostAuthorize` là một thành phần của kiến trúc nhiều lớp:

- Authentication filter kiểm chứng identity bằng credentials hợp lệ.
- HTTP authorization kiểm soát URL/method.
- `@PreAuthorize` chặn quyền thao tác tổng quát trước method.
- `@PostAuthorize` kiểm soát trả result dựa trên object đã tải.
- Database/service tiếp tục đảm bảo tenant, ownership và business invariants.
- Exception handling và logging bảo đảm không tiết lộ dữ liệu bị deny.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Bob đọc được tài liệu Alice | `@EnableMethodSecurity` thiếu, self-invocation, bean không proxied | Chạy negative test Bob 403, kiểm tra Spring DI |
| Có 403 nhưng DB đã bị xóa | PostAuthorize đặt trên mutation | Chuyển permission/owner checks trước mutation và transaction |
| Lỗi property ownerUsername | DTO thiếu getter, sai tên, result Optional/null | Xem kiểu return thực tế và getter |
| Alice đúng mật khẩu nhưng vẫn 403 | Pre permission thiếu, owner khác, tenant mismatch | Kiểm tra authorities và resource thuộc ai |
| Anonymous được 401 | HTTP Basic entry point chặn thiếu credentials | Hành vi bình thường |
| Guest 403 trước khi service chạy | PreAuthorize deny | Đúng theo policy |
| ID không tồn tại gây 500 | Return null rồi SpEL dereference | Ném 404 trước return hoặc xử lý null có chủ đích |
| Cross-tenant đọc nhầm tài liệu | Chỉ so username, không kiểm tra tenant | Dùng trusted principal ID và tenant ID |
| Lộ owner/title qua error body | Custom exception handler/log vô tình echo result | Kiểm tra response và logging |
| Lazy JPA property bị lỗi | PostAuthorize đọc quan hệ ngoài transaction | Sử dụng DTO/projection hoặc fetch thích hợp |
| List post-filter sai pagination | Tải tất cả rồi lọc phía Java | Scope query tại DB |
| Method security không chạy khi this.method() | Self-invocation bypass proxy | Tách bean, gọi qua injected proxy |
| Service method trả 403 sau email gửi | Side effect chạy trước post check | Thiết kế precheck/outbox hoặc transaction |
| Test 200 pass nhưng quyền không hoạt động | Chỉ có positive test | Bổ sung negative tests non-owner |

### Quy trình chẩn đoán

1. Xác nhận request vào đúng `SecurityFilterChain`, credentials được kiểm chứng và có `Authentication` hợp lệ.
2. Xác nhận `@EnableMethodSecurity` đã bật và lời gọi đi qua **Spring-managed proxy**.
3. Xác nhận `@PreAuthorize` có kiểm tra quyền sớm, không bị bỏ qua.
4. Xác nhận kiểu object trả về, property getter và expression `returnObject` có khớp.
5. So identity của principal với owner/tenant **server-side**, không dựa vào header từ client.
6. Tách lỗi 401 (chưa xác thực), 403 (thiếu quyền) và 404 (không có resource) theo contract.
7. Kiểm tra side effects, transaction boundaries, lazy JPA và lỗi self-invocation.
8. Chạy negative integration tests và xác minh response không chứa DTO bị chặn.

Development có thể bật log:

```properties
logging.level.org.springframework.security=DEBUG
```

Không log raw password, Authorization header, JWT, session cookies, hoặc toàn bộ DTO bị từ chối ở production.

## 16. Câu hỏi tự ôn

1. **PostAuthorize chạy trước hay sau method?** Sau khi method đã trả giá trị thành công.
2. **returnObject là gì?** Kết quả thực tế của method được đưa vào SpEL.
3. **@PreAuthorize có đọc returnObject hiện tại được không?** Không; method chưa chạy.
4. **Bob có DOCUMENT_READ mà vẫn 403 tại sao?** Có thể qua precheck nhưng bị postcheck vì không phải owner.
5. **Auditor được đọc tài liệu người khác nhờ gì?** Quyền DOCUMENT_AUDIT được khai báo rõ trong policy.
6. **Guest thiếu permission bị chặn lúc nào?** Ở PreAuthorize trước khi đọc object.
7. **Có nên chỉ dùng PostAuthorize cho delete/chuyển tiền không?** Không; mutation/side effects có thể xảy ra trước deny.
8. **PostAuthorize có rollback email đã gửi không?** Không bảo đảm.
9. **DTO có field ownerUsername nhưng không có getter thì sao?** SpEL property access có thể không đúng theo kiểu/visibility; getter rõ ràng an toàn hơn.
10. **Method trả Optional<DocumentView> có dùng returnObject.ownerUsername trực tiếp?** Không, returnObject là Optional.
11. **@PostAuthorize tự lọc List theo từng phần tử không?** Không; @PostFilter có semantics khác.
12. **Thiếu @EnableMethodSecurity nguy hiểm thế nào?** Method-security annotations có thể không được thực thi.
13. **Vì sao self-invocation có thể bypass?** Lời gọi this.method() không đi qua proxy Spring.
14. **Owner username có đủ cho multi-tenant không?** Thường không; cần trusted IDs/tenant.
15. **403 vs 404 có thể tiết lộ gì?** Có thể làm lộ resource ID tồn tại.
16. **Dùng MockMvc cần test những nhánh nào?** 200 owner, 403 non-owner, 200 auditor, 403 guest, 401 anonymous, 404 missing ID.
17. **Có thể vẫn dùng PostAuthorize khi API STATELESS?** Có, vì Authentication tồn tại trong request hiện tại.
18. **Method có ném 404 trước khi trả object thì PostAuthorize kiểm tra gì?** Không có return value thành công để đánh giá; exception xử lý theo flow riêng.

## 17. Checklist đưa vào dự án thật

- [ ] Bật `@EnableMethodSecurity` trong cấu hình Spring Security.
- [ ] Đặt `@PostAuthorize` trên **Spring-managed service method** được gọi qua proxy.
- [ ] Dùng `returnObject` với property/getter có thật và kiểu trả về rõ ràng.
- [ ] Không dùng client-supplied owner/tenant/role để quyết định quyền.
- [ ] Kết hợp `@PreAuthorize` để chặn user thiếu permission ngay trước method.
- [ ] Không chỉ dựa vào `@PostAuthorize` để bảo vệ mutation hoặc các side effects.
- [ ] Với thao tác ghi, kiểm tra permission + owner/tenant/domain state **trước** mutation và trong transaction khi phù hợp.
- [ ] Nếu ID không tồn tại, định nghĩa 404/null/Optional policy trước khi áp dụng SpEL.
- [ ] Với multi-tenant, dùng principal user ID và tenant scope đáng tin, không chỉ username.
- [ ] Với JPA, cân nhắc DTO/projection để tránh lazy-loading trong biểu thức.
- [ ] Với collection lớn, lọc dữ liệu trong query thay vì dựa vào @PostFilter sau tải.
- [ ] Không có logic đăng ký proxy tùy tiện hoặc self-invocation bỏ qua method advice.
- [ ] Kiểm soát HTTP 401/403/404, nguy cơ existence leak và error response.
- [ ] Test cả grant và deny; bảo đảm không lộ DTO qua logs/errors.
- [ ] Cấu hình HTTPS, token/session/CSRF phù hợp với HTTP client thực tế.
- [ ] Với async/reactive method, nghiên cứu interceptor/context propagation tương ứng trước khi áp dụng mẫu đồng bộ.

**Kết luận:** `@PostAuthorize` kiểm tra **kết quả mà service đã tạo ra** bằng biến SpEL `returnObject`. Nó đặc biệt hữu ích cho **method đọc** khi quyền phụ thuộc vào owner, tenant hoặc thuộc tính của resource đã được tải. Hãy ghép với `@PreAuthorize` cho permission kiểm tra trước; dùng Spring-managed proxy, dữ liệu server đáng tin và negative tests. Vì PostAuthorize chạy **sau method execution**, nó **không tự ngăn, không tự thu hồi hoặc đảo ngược side effects** của method.