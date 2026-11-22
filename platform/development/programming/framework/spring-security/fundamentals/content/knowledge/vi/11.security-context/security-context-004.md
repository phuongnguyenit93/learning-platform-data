# SecurityContextRepository với việc tải và lưu ngữ cảnh Servlet

Hãy đặt tình huống: Mai đăng nhập thành công vào ứng dụng Spring MVC. Trong request đăng nhập, `SecurityContextHolder.getContext().getAuthentication()` cho biết người dùng hiện tại là Mai. Sau đó trình duyệt gửi `GET /me` và ứng dụng vẫn nhận diện được Mai **mà không yêu cầu nhập mật khẩu một lần nữa**.

Tại sao hai request HTTP khác nhau lại có thể chia sẻ danh tính đã được xác thực, trong khi `SecurityContextHolder` của ứng dụng Servlet mặc định sử dụng `ThreadLocal` và phải được dọn khi xử lý request kết thúc? Câu trả lời nằm ở một ranh giới có tên **`SecurityContextRepository`**.

Nó là chiến lược **tải** `SecurityContext` cho request hiện tại và **lưu** `SecurityContext` tại nơi thích hợp khi muốn sử dụng trong request tương lai hoặc trong các dispatch khác nhau của cùng một request. Một implementation có thể sử dụng `HttpSession`, một implementation khác dùng request attribute, và một implementation cố tình không lưu gì.

Bài tập trung vào **Spring Security Servlet stack** (Spring MVC/Tomcat và `jakarta.servlet`), không áp dụng nguyên xi cho WebFlux. Bạn sẽ học cơ chế `SecurityContextRepository` từ đầu đến cuối, hiểu rõ mặc định của Spring Security hiện đại, phân biệt `SecurityContextHolderFilter` với `SecurityContextPersistenceFilter`, dùng `saveContext` đúng thời điểm, và chạy ví dụ Spring Boot 4.1.2/Java 17 với form login + kiểm thử MockMvc.

## 1. Bốn thành phần phải phân biệt trước khi viết code

| Thành phần | Vai trò | Thời gian tồn tại và phạm vi |
| --- | --- | --- |
| `Authentication` | Danh tính, bằng chứng đã được xác minh và authorities của chủ thể | Một đối tượng có thể được giữ trong request, context hoặc session tùy cơ chế |
| `SecurityContext` | Container chứa `Authentication` của ngữ cảnh bảo mật | Có thể được tạo mới, nạp từ repository hoặc giữ trong session |
| `SecurityContextHolder` | Điểm truy cập `SecurityContext` của luồng xử lý hiện tại; mặc định là `ThreadLocal` trong Servlet | Thông thường chỉ gắn với luồng đang xử lý request; cần được dọn đúng lúc |
| `SecurityContextRepository` | Chiến lược **lưu trữ/tải** `SecurityContext` qua servlet request/response | Tùy implementation: request attribute, HTTP session hoặc không lưu |

Một đoạn code:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

**Không nói** Spring Security đã truy vấn cơ sở dữ liệu ở dòng này. Trong Servlet, context thường đã được filter tải/gắn vào `SecurityContextHolder` trước khi controller chạy; dòng code chỉ đọc context của thread hiện tại.

Một đoạn code khác:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticatedUser);
SecurityContextHolder.setContext(context);
~~~

Chỉ có tác dụng đặt `Authentication` vào context đang được gắn cho thread hiện tại. **Nó không tự cam kết** rằng request kế tiếp sẽ nhìn thấy `authenticatedUser`. Muốn duy trì qua request, cần cơ chế lưu tương ứng và/hoặc một authentication filter đã xử lý việc lưu.

### Trục thời gian để nhớ

~~~text
Request A: POST /login
    |
    +--> Xác thực thành công
    +--> SecurityContext(Authentication=Mai)
    +--> SecurityContextRepository.saveContext(...)
    +--> HTTP response + session cookie (nếu dùng session)

                (request A hoàn tất)
          SecurityContextHolder được dọn

Request B: GET /me, gửi lại session cookie
    |
    +--> Repository.loadDeferredContext(request B)
    +--> SecurityContextHolder có Authentication=Mai
    +--> Controller /me trả "mai"
    +--> SecurityContextHolder được dọn khi request B kết thúc
~~~

Việc **dọn `SecurityContextHolder`** và việc **lưu `SecurityContext` vào session** không mâu thuẫn. Thực ra chính nhờ tách hai trách nhiệm này mà một servlet thread tái sử dụng cho người dùng khác không vô tình giữ danh tính Mai.

## 2. Hợp đồng SecurityContextRepository

Interface nằm tại:

~~~java
org.springframework.security.web.context.SecurityContextRepository
~~~

Các phương thức quan trọng:

~~~java
// Trích yếu chữ ký API Spring Security; imports bỏ qua để tập trung cơ chế.
DeferredSecurityContext loadDeferredContext(HttpServletRequest request);

void saveContext(
    SecurityContext context,
    HttpServletRequest request,
    HttpServletResponse response
);

boolean containsContext(HttpServletRequest request);
~~~

Hiểu đúng từng phương thức:

1. **`loadDeferredContext(request)`** trả về một `DeferredSecurityContext`. Việc nạp có thể **trì hoãn** cho đến lúc cần `get()`, tránh đọc session không cần thiết trên những request không đòi hỏi danh tính.
2. **`saveContext(context, request, response)`** ghi context theo cơ chế của implementation. Với session repository, cần request/response phù hợp để tạo hoặc sử dụng HTTP session và gửi cookie khi cần.
3. **`containsContext(request)`** kiểm tra repository có context cho request hiện tại hay không. Nó **không** phải phép xác thực password hay kiểm tra role.
4. Phương thức cũ `loadContext(HttpRequestResponseHolder)` vẫn có thể gặp trong tài liệu/code cũ nhưng đã **deprecated**; ưu tiên `loadDeferredContext` trong thiết kế mới.

`DeferredSecurityContext` cung cấp `get()` và `isGenerated()` để truy cập context và biết khi nào context được tạo mới theo nghĩa API. Không nên dùng `isGenerated()` một mình làm quyết định người dùng đã đăng nhập hay có quyền; quyền cần được đánh giá dựa trên `Authentication` và policy đáng tin cậy.

### Ví dụ tư duy: load, set và save là ba hành động khác nhau

~~~text
load:
  repository -> context cho request

set:
  SecurityContextHolder <- context hiện tại của thread

save:
  context -> repository (nếu muốn lưu ở phạm vi repository hỗ trợ)
~~~

Nếu chỉ làm `set` thì trạng thái trong thread có thể hoạt động cho phần còn lại của request, nhưng không chắc tồn tại ở request sau. Nếu chỉ làm `save` mà không đặt context cho request hiện tại, những đoạn code gọi `SecurityContextHolder` **trong cùng request** có thể không nhận được kết quả bạn mong muốn. Thông thường custom login sẽ tạo context mới, `setContext`, rồi `saveContext`.

## 3. Những implementation chính

| Implementation | Nơi lưu dữ liệu | Có hỗ trợ request sau không? | Điểm cần nhớ |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | `HttpSession`, mặc định dưới key `SPRING_SECURITY_CONTEXT` | **Có**, nếu session còn hiệu lực và client gửi đúng session identifier | Phù hợp session-based login |
| `RequestAttributeSecurityContextRepository` | Attribute trên `ServletRequest` | **Không** qua HTTP request mới | Hữu ích giữa các dispatch trong cùng request, ví dụ error dispatch |
| `DelegatingSecurityContextRepository` | Nhiều repository con | Tùy delegates | Khi save, chuyển tới các delegates; khi load, lấy context phù hợp theo thứ tự |
| `NullSecurityContextRepository` | Không lưu | **Không** | Dùng khi không muốn persistence của context, tùy flow stateless |

Các implementation này thuộc package `org.springframework.security.web.context`.

Không nhầm `SecurityContextRepository` với `UserDetailsService`: thứ nhất lưu/nạp **kết quả định danh**; thứ hai nạp **dữ liệu user phục vụ authentication bằng username/password**. Repository context không nhất thiết kiểm tra mật khẩu mỗi request, còn `UserDetailsService` không phải nơi lưu session.

### 3.1. HttpSessionSecurityContextRepository

Implementation này dùng `HttpSession` để liên kết danh tính với **các request tiếp theo**. Sau khi login thành công, session chứa `SecurityContext`; client giữ session cookie (thường tên `JSESSIONID`, có thể là `SESSION` nếu Spring Session được dùng). Request mới kèm cookie hợp lệ sẽ dẫn tới session tương ứng.

~~~text
Browser                         Servlet app
  | POST /login                    |
  |------------------------------->|
  |                 Authenticate -> SecurityContext
  |                 saveContext -> HttpSession
  |<-------------------------------|
  |          Set-Cookie: JSESSIONID=...
  |
  | GET /me + Cookie: JSESSIONID=...
  |------------------------------->|
  |                  HttpSession -> SecurityContext
  |                  SecurityContextHolder -> Authentication
  |<-------------------------------|
  |                             "mai"
~~~

Mặc định key lưu trong session của lớp này là `SPRING_SECURITY_CONTEXT`. Đó là **tên thuộc tính nội bộ**, không phải một URL API hoặc tên cookie.

`HttpSessionSecurityContextRepository.saveContext` không có nghĩa cứ gọi là tạo session. Implementation có các điều kiện: trạng thái context có thay đổi hay không, có chứa anonymous authentication không, chính sách tạo session và những ràng buộc khác. Tài liệu nói nó có thể tạo session **khi cần**, với lựa chọn `allowSessionCreation` mặc định là `true`.

Một đoạn cấu hình:

~~~java
HttpSessionSecurityContextRepository repository =
    new HttpSessionSecurityContextRepository();

repository.setAllowSessionCreation(false);
~~~

Khi không cho tạo session, repository không thể tự tạo phiên mới chỉ vì bạn gọi `saveContext`. Nếu đã có session, hành vi lưu còn phụ thuộc những điều kiện khác. **Đừng coi `setAllowSessionCreation(false)` là cấu hình stateless toàn hệ thống**; session có thể vẫn được tạo ở component khác.

### 3.2. RequestAttributeSecurityContextRepository

Đối tượng này giữ context ở thuộc tính của **ServletRequest**, không tồn tại qua hai lần HTTP request độc lập.

Ví dụ hữu ích:

~~~text
REQUEST dispatch
   |
   +--> đã nhận diện user Mai
   +--> context được lưu vào request attribute
   +--> controller ném exception
   |
   v
ERROR dispatch (vẫn thuộc cùng servlet request)
   |
   +--> container có thể thay đổi/clear thread context
   +--> repository đọc request attribute
   +--> error view có thể biết danh tính Mai
~~~

Một số servlet container sử dụng dispatch khác nhau khi chuyển sang trang lỗi. `RequestAttributeSecurityContextRepository` được thiết kế để context vẫn có thể được truy cập trong các dispatch của **cùng request** dù `SecurityContextHolder` tạm bị dọn. Nó không phải database, không phát session cookie và không tạo xác thực lâu dài.

**Lưu ý:** việc error dispatch được chạy qua filter chain nào, policy gì, và có quyền truy cập thông tin hay không còn phụ thuộc dispatcher-type/security config. Không nên cho rằng “lưu request attribute” đồng nghĩa tự động hiển thị danh tính trên mọi trang lỗi.

### 3.3. DelegatingSecurityContextRepository

Từ Spring Security 6, cấu hình phổ biến dùng:

~~~java
new DelegatingSecurityContextRepository(
    new RequestAttributeSecurityContextRepository(),
    new HttpSessionSecurityContextRepository()
)
~~~

Khi `saveContext` được gọi, `DelegatingSecurityContextRepository` chuyển việc lưu tới các delegates. Khi load, nó có thể lấy một context phù hợp từ các delegates theo thứ tự. Cặp này mang lại **hai lợi ích bổ sung**: context có sẵn qua các dispatch của một request và có thể được lưu giữa các request bằng session.

**Không** có nghĩa Spring Security tạo hai session khác nhau. Request attribute và HTTP session là hai nơi lưu với **phạm vi khác nhau**.

Spring Security 7 tiếp tục hỗ trợ các implementation này. Mặc định thực tế của một ứng dụng có thể bị điều chỉnh bởi custom `SecurityFilterChain`, session policy, authentication mechanism hoặc Spring Boot auto-configuration; khi debug, hãy xem chain và repository **đang được cấu hình thật**, không chỉ tên class trong bài.

### 3.4. NullSecurityContextRepository

Đây là nơi “lưu nhưng không ghi, tải nhưng không khôi phục từ phiên trước”:

~~~java
SecurityContextRepository noPersistence =
    new NullSecurityContextRepository();
~~~

Phù hợp khi một request được xác thực lại từ bearer token hoặc cơ chế khác, **không muốn gắn Authentication với session phía server**.

Tuy nhiên `NullSecurityContextRepository` không tự validate JWT, không tạo `Authentication`, và **không tự xóa cookie** mà một phần ứng dụng khác có thể phát. Stateless authentication là một thiết kế tổng thể gồm chain, session policy, filter xác thực token, caching và cách quản lý credentials. Đừng chỉ đổi repository rồi tuyên bố mọi thành phần đã stateless.

## 4. Filter nào tải context: SecurityContextHolderFilter hay SecurityContextPersistenceFilter?

Đây là khác biệt giữa bài hướng dẫn Spring Security 5 và cấu hình Servlet hiện đại.

### 4.1. SecurityContextPersistenceFilter — kiểu cũ, tự lưu khi phù hợp

Luồng khái niệm:

~~~text
SecurityContextPersistenceFilter
      |
      +--> Repository LOAD vào SecurityContextHolder
      |
      +--> Các filter/controller xử lý request
      |
      +--> Khi context thay đổi, có thể SAVE tự động
      |    (bao gồm cơ chế wrapper trước khi response commit)
      |
      +--> CLEAR SecurityContextHolder
~~~

Khi filter này đảm nhận persistence, một số code cũ chỉ cần `SecurityContextHolder.setContext(context)`, sau đó cơ chế filter tự phát hiện và lưu. Nhưng cách theo dõi context thay đổi/saving ở cuối request khá phức tạp; còn có tình huống redirect gửi response trước khi code hậu xử lý chạy.

`SecurityContextPersistenceFilter` được giữ chủ yếu để hiểu/migrate hệ thống cũ, **không phải lựa chọn mặc định nên thêm thủ công** vào ứng dụng hiện đại.

### 4.2. SecurityContextHolderFilter — tải nhưng không tự lưu

Luồng:

~~~text
SecurityContextHolderFilter
      |
      +--> Repository.loadDeferredContext(request)
      |    thiết lập strategy để ứng dụng đọc SecurityContext
      |
      +--> Các filter/controller xử lý request
      |
      +--> Khi cần persistence:
      |        CODE XÁC THỰC PHẢI saveContext(...) RÕ RÀNG
      |
      +--> CLEAR SecurityContextHolder khi kết thúc
~~~

Sự khác nhau:

| Thuộc tính | `SecurityContextPersistenceFilter` | `SecurityContextHolderFilter` |
| --- | --- | --- |
| Tải context cho request | Có | Có |
| Tự phát hiện và lưu context khi thay đổi | Theo cơ chế cũ, có | **Không** |
| Yêu cầu explicit save cho code tự set context | Thường không trong cấu hình cũ | **Có**, nếu muốn tồn tại giữa request |
| Cần dọn context của thread | Có | Có |
| Hướng dùng khi viết Spring Security 6/7 | Chủ yếu cho migration/tương thích cũ | Mặc định hiện đại |

Trong một security filter chain, **không nên đồng thời thêm cả hai filter** vì đều tham gia quản lý `SecurityContextHolder`. Cấu hình mới nên dùng `SecurityContextHolderFilter` và explicit-save semantics phù hợp.

### 4.3. requireExplicitSave(true) nghĩa gì?

Trong `HttpSecurity` Servlet:

~~~java
http.securityContext(sc -> sc
    .requireExplicitSave(true)
);
~~~

Nó chọn semantics dùng `SecurityContextHolderFilter`: filter tải context nhưng **không tự lưu**. Đối với Spring Security 6/7, đây là hướng mặc định hiện đại; khai báo trực tiếp trong bài học để nhấn mạnh hợp đồng.

Cấu hình cũ có thể dùng `requireExplicitSave(false)` để chuyển sang behavior auto-save cho migration, nhưng **không nên coi đó là “cách sửa” khi custom login không lưu session**. Thay vào đó, xác định chỗ authentication thành công và gọi repository lưu context đúng.

Tài liệu của Spring Security nêu rõ trong hệ 6/7, code custom tự đặt `SecurityContextHolder` phải chủ động lưu nếu muốn persistence. <https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html>

## 5. Vì sao built-in form login thường lưu được session, nhưng custom login của bạn thì không?

Một nhầm lẫn thường gặp:

> “Spring Security 6 yêu cầu explicit save, vậy tại sao tôi dùng `formLogin()` không cần tự viết `saveContext` mà vẫn đăng nhập được?”

Bởi vì **filter xác thực do framework cung cấp** đã thực hiện trách nhiệm lưu context theo flow của nó. Với form login, `UsernamePasswordAuthenticationFilter` kế thừa cơ chế `AbstractAuthenticationProcessingFilter` và dùng `SecurityContextRepository` khi authentication thành công. Việc **filter quản lý context không tự lưu** không đồng nghĩa **toàn ứng dụng không component nào lưu**.

Phân biệt:

- **Form login mặc định:** framework đã thực hiện xác thực, session fixation protection, success/failure handling và lưu context theo cấu hình.
- **Code tự gọi `AuthenticationManager.authenticate` trong controller:** ứng dụng đang đứng ở chỗ framework thường làm; cần tự thiết kế cách `SecurityContext` được set/save, xử lý session strategy, CSRF, failure, logout, audit và tránh credentials leak.
- **HTTP Basic:** có thể xác thực bằng header ở mỗi request; không mặc định coi nó luôn tạo session login cho request sau không có header. Tùy filter/repository/session config, không suy đoán từ sự tồn tại của `SecurityContextHolder`.
- **Bearer/JWT:** request thường được xác thực dựa vào token hiện tại; không có nghĩa nó được chuyển thành session login phía server.

Nếu chỉ test `Authentication` trong request đang xử lý, bạn chưa chứng minh được session persistence. Test đúng phải gửi **request thứ hai** bằng cookie/session phù hợp.

## 6. Ví dụ đầy đủ Java 17+: lưu qua session và tải ở request tiếp theo

Chúng ta tạo một ứng dụng Spring Boot 4.1.2 dùng form login. Ví dụ được thiết kế để dễ quan sát repository: thay vì tự viết filter login có nguy cơ sai session fixation/CSRF, ta dùng form login chuẩn và cấu hình rõ ràng `DelegatingSecurityContextRepository`.

Các mục tiêu:

1. `GET /public` truy cập được khi chưa đăng nhập.
2. `GET /me` lúc chưa đăng nhập sẽ được chuyển về trang login.
3. Form login với user `mai` và mật khẩu demo tạo context đã xác thực, được lưu vào session.
4. Request thứ hai với session này gọi `GET /me` trả `mai`.
5. Unit-style test với mock servlet request chứng minh `saveContext` là thao tác cần thiết khi ứng dụng tự lưu.
6. Không tắt CSRF để làm test; dùng `spring-security-test` hỗ trợ form login hợp lệ.

### 6.1. Cấu trúc project

~~~text
security-context-repository-lab/
  pom.xml
  src/main/java/com/example/contextrepo/
    ContextRepositoryApplication.java
    SecurityConfiguration.java
  src/test/java/com/example/contextrepo/
    SecurityContextRepositoryTest.java
~~~

### 6.2. pom.xml

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-context-repository-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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
~~~

Boot 4 dùng starter `spring-boot-starter-webmvc` thay cho nhiều bài Boot 3 sử dụng `spring-boot-starter-web`. Test `@AutoConfigureMockMvc` thuộc package `org.springframework.boot.webmvc.test.autoconfigure` trong Boot 4. Các test starters chuyên biệt cung cấp hỗ trợ MockMvc và Spring Security Test. Boot BOM kiểm soát phiên bản Spring Security tương thích với Boot; không cần chỉ định version cho `spring-security-web` hay `spring-security-test`.

### 6.3. Application + controller

Tạo `src/main/java/com/example/contextrepo/ContextRepositoryApplication.java`:

~~~java
package com.example.contextrepo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ContextRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextRepositoryApplication.class, args);
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Controller chỉ đọc danh tính mà các filter đã nạp cho request. Nó không đọc password từ session, không lưu `SecurityContext` và không tự tạo authenticated token.

### 6.4. SecurityConfiguration

Tạo `src/main/java/com/example/contextrepo/SecurityConfiguration.java`:

~~~java
package com.example.contextrepo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        return http
            .securityContext(sc -> sc
                .securityContextRepository(repository)
                .requireExplicitSave(true)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .build();
    }
}
~~~

Phân tích:

1. Bean `SecurityContextRepository` là `DelegatingSecurityContextRepository` gồm **RequestAttribute** và **HttpSession**. Nó tương ứng với cặp mặc định thường được Spring Security dùng.
2. `HttpSecurity.securityContext(...).securityContextRepository(repository)` đảm bảo chain dùng chính object repository đã cấu hình. Khi đặt custom repository, cần chắc chắn các filter authentication liên quan dùng **cùng chiến lược**.
3. `.requireExplicitSave(true)` nhấn mạnh semantics hiện đại: `SecurityContextHolderFilter` không tự lưu.
4. `.formLogin(form -> form.permitAll())` bật login page/filter chuẩn, cho phép trang login và xử lý login theo flow Spring Security.
5. `InMemoryUserDetailsManager` cung cấp user demo; `PasswordEncoder` dùng BCrypt. Đây không phải cách quản lý user production.
6. Rule `/public` cho phép anonymous. `/me` yêu cầu authenticated.
7. **Không tắt CSRF**. POST form login phải gửi token CSRF hợp lệ; test dùng helper của Spring Security Test.

Khi ứng dụng khởi động, repository bean **chưa chứa danh tính Mai**. Chỉ khi có một yêu cầu authentication thành công và flow lưu context, session mới chứa kết quả phù hợp.

### 6.5. Kiểm thử MockMvc: hai request có chung session

Tạo `src/test/java/com/example/contextrepo/SecurityContextRepositoryTest.java`:

~~~java
package com.example.contextrepo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextRepositoryTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SecurityContextRepository repository;

    @Test
    void formLoginSavesContextForNextRequest() throws Exception {
        MvcResult login = mvc.perform(
                    formLogin().user("mai").password("demo-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        assertNotNull(session.getAttribute(
            HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY));

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));
    }

    @Test
    void explicitSaveMakesContextAvailableToLaterRequest() {
        MockHttpServletRequest first = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                    "mai", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
        );

        assertFalse(repository.containsContext(first));
        repository.saveContext(context, first, response);
        assertTrue(repository.containsContext(first));

        MockHttpSession session =
                (MockHttpSession) first.getSession(false);
        assertNotNull(session);

        MockHttpServletRequest next = new MockHttpServletRequest();
        next.setSession(session);
        SecurityContext loaded =
                repository.loadDeferredContext(next).get();

        assertEquals("mai", loaded.getAuthentication().getName());
    }

    @Test
    void anonymousMayReadPublicEndpoint() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
~~~

Các test trên minh họa **hai mức khác nhau**:

- `formLoginSavesContextForNextRequest` dùng thật filter chain + form login + session. Request thứ hai là `GET /me` không gửi lại password nhưng vẫn trả `mai`. Đây là bài test trực tiếp cho persistence giữa các request.
- `explicitSaveMakesContextAvailableToLaterRequest` tạo một `Authentication` giả **chỉ trong phạm vi unit-style test**, gọi repository trực tiếp rồi chuyển `MockHttpSession` sang request tiếp theo. Nó kiểm tra API `saveContext`/`loadDeferredContext`, **không phải** kiểm thử rằng việc tự tạo token authenticated từ input client là an toàn.
- `anonymousMayReadPublicEndpoint` xác nhận policy `permitAll`, không chứng minh context đã được lưu.

Không dùng `@WithMockUser` để chứng minh đăng nhập bằng password đã được lưu session; annotation đó chủ yếu thiết lập `SecurityContext` test, có thể bỏ qua flow xác thực và session lưu thật. Dùng `formLogin()` giúp test đi qua filter đăng nhập đúng cách, bao gồm token CSRF do helper cung cấp.

### 6.6. Chạy ứng dụng và kiểm tra

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Khi test thành công, Maven/Surefire hiển thị ba test đã pass (cùng các thông tin log phụ thuộc môi trường). **Không có stdout cố định cần assert** như chương trình Java standalone; giá trị quan trọng là các assertion pass và HTTP response `public`/`mai`.

Thử bằng trình duyệt:

1. Mở `http://localhost:8080/public`: body là `public`.
2. Mở `http://localhost:8080/me` khi chưa đăng nhập: được đưa đến trang login.
3. Đăng nhập với username `mai`, password `demo-password`.
4. Mở lại `http://localhost:8080/me`: body là `mai`.
5. Dùng một cửa sổ private/incognito khác chưa mang session cookie: truy cập `/me` lại cần đăng nhập.
6. Thực hiện logout qua flow được cấu hình nếu cần; với Spring Security có CSRF, thao tác logout POST cần token CSRF hợp lệ.

Những giá trị demo trên chỉ dành cho local. Với production, luôn dùng HTTPS, cookie `Secure`/HttpOnly/SameSite theo nhu cầu, session timeout và chính sách quản lý session thích hợp. **Không** đưa password thật vào script, log hay các lệnh terminal có thể lưu history.

### Vì sao không minh họa bằng curl -X POST /login không kèm CSRF?

Form login trên Servlet có CSRF protection theo mặc định. Một lệnh POST login chỉ gồm `username` và `password` nhưng **thiếu CSRF token** có thể bị từ chối 403, tạo cảm giác persistence bị lỗi dù thực ra đó là CSRF filter. Khi muốn automation, dùng browser test/MockMvc với token đúng hoặc tự thực hiện quy trình lấy/gửi token và cookie hợp lệ.

## 7. Custom login: setContext rồi saveContext rõ ràng

Một số ứng dụng tự viết `POST /api/login` trong controller. Nếu có code:

~~~java
Authentication authentication =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            username, password
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// THIẾU nếu muốn giữ login qua request sau:
return ResponseEntity.noContent().build();
~~~

Đây là **fragment minh họa lỗi**, không phải class độc lập. Request hiện tại đã có `Authentication`, nhưng `SecurityContextHolderFilter` không tự ghi context vào repository. Request tiếp theo có thể vẫn anonymous.

Bản sửa ở đúng vị trí sau khi đã xác thực thành công:

~~~java
// Fragment trong controller/filter CUSTOM, yêu cầu các dependency có sẵn.
// username/password đã được lấy và xác minh qua AuthenticationManager;
// request/response là jakarta.servlet.http.HttpServletRequest/Response.

Authentication authentication =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            username, password
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context, httpServletRequest, httpServletResponse
);

return ResponseEntity.noContent().build();
~~~

**Quan trọng:** đây là **fragment giải thích explicit save**, KHÔNG phải implementation login production có thể copy nguyên mà an toàn. Một endpoint login tự viết còn cần: CSRF theo loại client, session fixation protection (`SessionAuthenticationStrategy` khi phù hợp), quản lý username/password input và cleanup, auth failure handler, event/audit, session concurrency, rate limiting, cookie/HTTPS, logout và xử lý lỗi. Built-in form login đã giải quyết nhiều phần trong số đó, nên nên dùng khi phù hợp.

Điểm về thứ tự: gọi `saveContext` **trước khi response commit** để session/cookie có thể được tạo và gửi đúng. Không đặt lệnh save sau `sendRedirect`, sau khi `getWriter()` đã flush hoặc khi response đã commit. Nếu custom code yêu cầu chuyển hướng, hãy lưu context thành công rồi thực hiện redirect.

### Tại sao tạo SecurityContext mới thay vì sửa object có sẵn?

Trong nhiều ví dụ chính thức, Spring Security khuyên:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Thay vì:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Tạo context mới giúp tránh sửa nhầm một context đang được chia sẻ/khôi phục từ session, và làm rõ thời điểm thay đổi danh tính. Tùy cơ chế, mutate context hiện tại có thể gây tác dụng phụ tới những request khác cùng nhìn tham chiếu session. Không nhất thiết mọi trường hợp mutate đều sai, nhưng mẫu **createEmptyContext → setAuthentication → setContext → save** dễ suy luận và kiểm thử hơn.

### Không giữ password trong persisted Authentication

Sau khi login, context lưu vào session không nên giữ raw password, OTP hoặc bearer token không cần thiết. `ProviderManager` có cơ chế dọn credentials của result khi được bật, nhưng custom provider/principal có thể vẫn giữ secret bên trong. Xem `CredentialsContainer` và vòng đời session để tránh đưa bí mật vào storage lâu dài.

## 8. SecurityContextRepository và SessionCreationPolicy có quan hệ gì?

Hai cấu hình liên quan nhưng **không phải cùng một thứ**:

- `SecurityContextRepository` trả lời **context được lưu/nạp ở đâu và bằng cách nào**.
- `SessionCreationPolicy` trả lời **Spring Security sẽ tạo/sử dụng HttpSession như thế nào** theo chính sách.

Các giá trị phổ biến:

| Chính sách | Ý nghĩa khái quát | Điều cần phân biệt |
| --- | --- | --- |
| `ALWAYS` | Spring Security chủ động tạo session | Không phải mọi endpoint đều cần; cân nhắc tải |
| `IF_REQUIRED` | Tạo khi cơ chế cần | Phù hợp nhiều ứng dụng form login |
| `NEVER` | Spring Security không chủ động tạo session nhưng có thể sử dụng session đã tồn tại | **Không** đồng nghĩa hoàn toàn stateless |
| `STATELESS` | Spring Security không tạo và không dùng HttpSession để lấy SecurityContext | Các thành phần khác của ứng dụng có thể vẫn có session, cần xem toàn kiến trúc |

Với API bearer-token stateless, có thể cấu hình:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

Cần import `org.springframework.security.config.http.SessionCreationPolicy`. Đây là fragment trong cấu hình Servlet; muốn thực sự xác thực bearer token phải cấu hình resource server, decoder và policies. Không nên chỉ thêm `STATELESS` vào một ứng dụng form login dùng session rồi mong login bền vững hoạt động bình thường.

Một cấu hình minh họa không lưu `SecurityContext` qua session:

~~~java
http.securityContext(sc -> sc
    .securityContextRepository(new NullSecurityContextRepository())
);
~~~

Tuy nhiên đừng tùy tiện trộn các lựa chọn `STATELESS`, `NullSecurityContextRepository` và form login khi chưa hiểu cơ chế nào chịu trách nhiệm xác thực từng request. **Stateless không có nghĩa bỏ qua kiểm tra Authentication**; nó thường nghĩa mỗi request phải mang bằng chứng có thể xác minh riêng.

### Nếu dùng nhiều SecurityFilterChain

Có thể cấu hình `/api/**` stateless và phần web còn lại dùng form login stateful:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(sm -> sm
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

**Đây là fragment minh họa**, cần @Configuration/imports/dependency resource server/JWT decoder và cách xử lý login/CSRF thực tế. `@Order` quyết định chain nào được xét trước; chỉ chain khớp đầu tiên xử lý một request. `SecurityContextRepository` của từng chain có thể khác. Không dùng cookie của web chain để mặc định mở quyền cho API chain stateless trừ khi có quyết định thiết kế rõ ràng.

## 9. Khi nào saveContext không tạo session?

Nhiều người học nhầm `saveContext` nghĩa là “bắt buộc Set-Cookie”. Thực tế phụ thuộc implementation và nội dung context.

`HttpSessionSecurityContextRepository` có thể **không lưu context** trong những tình huống như:

- Context vẫn là empty/default và không mang Authentication được chấp nhận.
- Authentication là anonymous theo `AuthenticationTrustResolver`.
- Context không thay đổi theo quy tắc quyết định lưu.
- `allowSessionCreation=false` và không có session có thể sử dụng.
- Response đã commit trước khi một session/cookie mới cần được thiết lập, tùy cách gọi và container.

Vì vậy, trong test nên kiểm tra **sự tồn tại của authenticated context thực tế ở request tiếp theo** thay vì chỉ assert đã gọi `saveContext` hay chỉ dựa trên header `Set-Cookie`. `SecurityContextRepository.containsContext(request)` là một công cụ hữu ích ở cùng request, nhưng vẫn phải test hành vi cross-request khi yêu cầu chức năng là “người dùng vẫn đăng nhập”.

### Session key có cần sửa không?

Lớp `HttpSessionSecurityContextRepository` cung cấp `SPRING_SECURITY_CONTEXT_KEY` và `setSpringSecurityContextKey`. Trong ứng dụng thông thường, **không cần đổi key**; thay đổi không đồng bộ giữa bộ lọc và repository có thể làm context không được khôi phục.

Nếu sử dụng Spring Session Redis/JDBC để chia sẻ session giữa node, cần kiểm tra serialization, TTL, session migration, session fixation, cleanup và quyền truy cập kho session. Dùng `SecurityContextRepository` không tự mang lại phân phối session trên nhiều máy khi servlet container chỉ lưu session trong bộ nhớ của một node.

## 10. Error dispatch, async dispatch và request attributes

Servlet request có thể được dispatch nhiều lần trong cùng lifecycle:

~~~text
REQUEST /profile
    |
    +--> SecurityContextHolderFilter
    |       nạp context
    |
    +--> controller ném exception
    |
    +--> ERROR dispatch /error
            |
            +--> filter/security handling theo dispatcher type
            +--> request attribute giữ context trong cùng request
            +--> error handler xử lý theo policy
~~~

`RequestAttributeSecurityContextRepository` có ích vì `SecurityContextHolder` có thể đã được clear trong một giai đoạn chuyển dispatch. Tuy nhiên **không phải tất cả container/filters chạy cùng một cách**. Những việc cần kiểm tra thực tế:

- Error dispatch có đi qua Spring Security filter chain không?
- Những endpoint `/error` có policy phù hợp không?
- Request attribute có được mang sang dispatch trong cùng request không?
- Có vô tình chuyển 401/403 của Security thành 500 từ error handler khác không?
- Có lộ thông tin định danh, claim, stack trace hoặc token trong error response không?

Async processing còn phức tạp hơn: công việc trên thread khác không tự nhận được `SecurityContextHolder` từ thread ban đầu. Dùng cơ chế propagation phù hợp (`DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, MVC async integration...) nếu cần. **`SecurityContextRepository` không phải công cụ tự động truyền ThreadLocal qua mọi thread**. Lưu vào request/session và truyền context giữa các execution thread là hai bài toán liên quan nhưng khác nhau.

## 11. Logout: xóa context ở đâu, và cookie nào còn hiệu lực?

Khi người dùng logout, chỉ gọi:

~~~java
SecurityContextHolder.clearContext();
~~~

thường **không đủ** để tuyên bố phiên đã bị vô hiệu hóa ở server hoặc request tiếp theo sẽ không nhận lại context từ repository. Nếu session vẫn giữ `SPRING_SECURITY_CONTEXT`, request sau có cookie cũ có thể vẫn tải danh tính từ đó.

Luồng logout chuẩn của Spring Security có `LogoutFilter` và các `LogoutHandler` liên quan như dọn context, invalidating HTTP session và xử lý `SecurityContextRepository`, tùy cấu hình.

Một cấu hình Servlet phổ biến:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
);
~~~

Nó là fragment để hiểu chính sách; endpoint/method logout chịu ảnh hưởng CSRF và cấu hình URL. Trong một ứng dụng browser bật CSRF, logout thường cần POST với CSRF token. Cookie ở browser và session server có thể có vòng đời riêng; nếu dùng Spring Session hoặc SSO, yêu cầu thu hồi token/phiên các hệ khác cần tích hợp bổ sung.

**Không nhầm:** dọn context ThreadLocal, xóa thuộc tính session, invalidating session, xóa cookie trình duyệt và thu hồi JWT/refresh token là những hành động riêng. Một ứng dụng nhiều thiết bị có thể cần quản lý toàn bộ session của account hoặc một thiết bị cụ thể.

## 12. SecurityContextRepository không phải kho chứng thực gốc

Một `SecurityContext` được lưu trong session thường chứa `Authentication` đã được chấp nhận tại thời điểm login. Nó **không tự đảm bảo** rằng tài khoản hiện tại vẫn enabled hoặc authorities hiện tại chưa thay đổi.

Ví dụ:

~~~text
09:00 Mai đăng nhập:
  repo lưu Authentication(username=mai, authorities=[ROLE_ADMIN])

09:15 Admin thu hồi ROLE_ADMIN của Mai trong database:
  DB đã đổi, nhưng session trước đó vẫn chứa snapshot authorities.

09:20 Mai gửi GET /admin với session cookie:
  repo có thể tải lại Authentication cũ.
  Nếu không có revocation/re-evaluation, role cũ có thể vẫn hiệu lực.
~~~

Để bảo vệ hành động nhạy cảm, ứng dụng cần chính sách **làm mới hoặc thu hồi**:

- Invalidate session của user khi account bị khóa, xóa hoặc đổi quyền.
- Dùng security version/permission version trong session và kiểm tra bản mới.
- Kiểm tra membership/role/owner/tenant hiện hành tại service theo mức rủi ro.
- Giới hạn session lifetime, idle timeout và dùng reauthentication/step-up cho thao tác quan trọng.
- Đánh giá cache invalidation và consistency khi chạy nhiều node.

**Repository chỉ xử lý nơi giữ/tải context, không phải policy engine kiểm tra mọi thay đổi trong database.** Không được coi quyền trong session là bất biến mãi mãi.

## 13. Các lỗi thiết kế phổ biến

1. **“SecurityContextHolder giữ Authentication vĩnh viễn.”** Sai: mặc định gắn với thread, không phải kho lâu dài.
2. **“SecurityContextRepository chỉ là một lớp khác của UserDetailsService.”** Không: một bên lưu/nạp context, bên kia tải user phục vụ xác thực.
3. **“Set SecurityContextHolder là đủ cho request sau.”** Không với explicit-save flow; phải gọi repository lưu nếu muốn persistence.
4. **“SecurityContextHolderFilter tự lưu cuối request.”** Sai: nhiệm vụ của filter hiện đại là tải, không tự save.
5. **“Cả SecurityContextHolderFilter và SecurityContextPersistenceFilter nên được thêm cho chắc.”** Không; chúng quản lý cùng mục đích và không nên cùng tồn tại trong một chain.
6. **“Gọi saveContext luôn tạo HTTP session mới.”** Không: còn điều kiện nội dung context, session policy và implementation.
7. **“RequestAttributeSecurityContextRepository giúp login bền vững qua nhiều request.”** Không: nó dùng trong cùng servlet request.
8. **“NullSecurityContextRepository làm JWT tự được xác thực.”** Không: cần authentication filter/decoder thích hợp.
9. **“Một Spring Session store làm mọi user đều dùng chung SecurityContext.”** Không: context phải được tách theo session/identity; lỗi cấu hình có thể cực kỳ nguy hiểm.
10. **“SessionCreationPolicy.NEVER đồng nghĩa STATELESS.”** Không: NEVER vẫn có thể sử dụng session đã tồn tại.
11. **“Cấu hình formLogin vẫn không lưu vì SecurityContextHolderFilter không save.”** Built-in authentication filter có trách nhiệm save trong success flow.
12. **“Tôi thêm custom login controller và chỉ setContext, đã đủ.”** Không: nếu muốn request sau nhận diện người dùng, phải explicit save.
13. **“Controller @WithMockUser test 200 chứng minh context được lưu.”** Không: annotation có thể tạo sẵn Authentication chỉ cho test.
14. **“Lỗi login 403 chứng minh session không lưu.”** Có thể do thiếu CSRF token, không liên quan persistence.
15. **“HTTP Basic không cần header ở request sau vì request trước đã vào SecurityContextHolder.”** Không mặc định: Basic thường chứng thực từng request theo header, tùy cấu hình.
16. **“SecurityContextRepository tự truyền context sang mọi thread async.”** Không, cần strategy/wrapper phù hợp.
17. **“clearContext() tương đương logout tất cả thiết bị.”** Không, session/token lifecycle riêng.
18. **“Đã lưu ROLE_ADMIN trong session thì quyền không bao giờ đổi.”** Sai: có thể stale sau khi DB thay đổi.
19. **“Mọi saveContext nên gọi sau redirect.”** Sai: lúc đó response có thể commit và không thể tạo session/cookie.
20. **“Request attribute là browser cookie.”** Không: attribute chỉ nằm ở server-side servlet request.
21. **“Có SecurityContext nghĩa là người dùng luôn authenticated.”** Context có thể rỗng; phải xét `Authentication` và cơ chế anonymous.
22. **“Đổi key SPRING_SECURITY_CONTEXT thì mọi client tự chuyển theo.”** Không; đây là key server-side phải được đồng bộ.
23. **“Set requireExplicitSave(false) là giải pháp chuẩn để sửa mọi lỗi custom login.”** Không; ưu tiên thực hiện save đúng flow hiện đại.
24. **“Dùng HttpSession repository nghĩa tất cả session được bảo vệ an toàn mặc định.”** Còn phải bảo vệ cookie, TLS, session fixation, timeout, server store và revocation.

## 14. Ma trận kiểm thử cần có

| Trường hợp | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| GET công khai khi anonymous | `/public` | HTTP 200, body `public` |
| GET `/me` khi chưa đăng nhập | Trình duyệt hoặc MockMvc GET | Redirect tới login hoặc entry point tương ứng |
| Đăng nhập form hợp lệ | POST /login với CSRF/session phù hợp | Authentication thành công, context lưu vào session |
| Request sau dùng cùng session | GET /me không gửi lại password | HTTP 200, body `mai` |
| Request không có cookie | GET /me ở browser private | Không nhận diện được Mai, cần login lại |
| Chỉ set context trong custom code | Không gọi saveContext | Request sau **không được mặc định** khôi phục danh tính |
| Custom code gọi saveContext | Cùng repository và response chưa commit | Request sau khôi phục được nếu session còn hiệu lực |
| Session bị invalidate | Reuse cookie/session cũ | Không được tiếp tục xác thực |
| Tài khoản bị disable sau login | Request với session cũ | Hành vi thu hồi theo policy rõ; không tin snapshot vô hạn |
| Quyền bị thu hồi sau login | Request tới resource nhạy cảm | Kiểm tra session refresh/re-evaluation/revocation |
| ERROR dispatch | Request đã có context, sau đó ném exception | Không mất context ngoài ý muốn trong dispatch phù hợp |
| Stateless bearer API | Không có HTTP session persistence | Mỗi request cần token hợp lệ, không dựa vào cookie login web |
| Response commit sớm | Redirect/flush ngay sau custom login | Context được save **trước** commit |
| Thread async | Chuyển sang executor | Context được truyền/dọn đúng cách nếu nghiệp vụ yêu cầu |
| Test `@WithMockUser` | Mock user không đi qua login filter | Không xem đó là chứng cứ session persistence |
| Custom repository | Cấu hình riêng mỗi chain | Matching chain dùng đúng repo và filter |

Nên kiểm tra cả **cấu hình filter chain thực tế** bằng log debug trong môi trường dev:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Với trường hợp cần xác minh filter nào đang chạy, có thể dùng logging mức TRACE trong môi trường kiểm soát hoặc debugger. **Không ghi session cookie, Authorization header hoặc password** trong log production. Lỗi liên quan session thường cần nhìn cả cookie phía client, session store phía server và policy của chain.

## 15. Bài tập tự luyện

**Bài 1 — thay request attribute bằng session-only.** Trong dự án demo, thay `DelegatingSecurityContextRepository` thành `HttpSessionSecurityContextRepository` rồi chạy lại test. Những test persistence giữa HTTP request có thể vẫn pass. Nhưng so sánh khả năng giữ context khi chuyển ERROR dispatch để thấy vì sao RequestAttribute repository hữu ích.

**Bài 2 — bỏ lưu session trong flow custom.** Thử một custom authentication flow được cách ly trong bài test, gọi `SecurityContextHolder.setContext` mà không `saveContext`. Gửi request mới không có bearer credentials nhưng có cùng cookie/giả lập session. Quan sát rằng context không tự được ghi bởi `SecurityContextHolderFilter`.

**Bài 3 — dùng NullSecurityContextRepository.** Trong cấu hình thử nghiệm tách riêng, đặt Null repository; xác nhận request kế tiếp không khôi phục danh tính qua HTTP session. Không chỉ thêm một bean Null ở context rồi giả định mọi chain tự dùng nó.

**Bài 4 — session fixation.** Đăng nhập form qua browser, kiểm tra session ID được xử lý theo chính sách fixation protection của Spring Security. Đừng copy một custom login controller chỉ gồm `saveContext` rồi bỏ phần này.

**Bài 5 — thu hồi role.** Đăng nhập với `ROLE_ADMIN`, sau đó thu hồi quyền từ repository người dùng. Kiểm tra API `/admin` khi session cũ vẫn còn; bổ sung invalidation/version check hoặc authorization theo dữ liệu hiện hành.

**Bài 6 — multiple chains.** Có web session chain và API stateless chain, viết test phân biệt cookie của web với bearer token của API. Đảm bảo các request ngoài `securityMatcher` không rơi khỏi toàn bộ policy bảo mật.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vai trò chính của `SecurityContextRepository` trong Servlet là gì?

*Trả lời:* Là chiến lược tải/lưu `SecurityContext` qua các servlet request hoặc dispatch theo phạm vi implementation; không phải bộ kiểm tra password.

**Câu 2.** Vì sao `SecurityContextHolder` có thể được clear cuối request mà người dùng vẫn đăng nhập ở request sau?

*Trả lời:* Vì context đã được lưu vào một repository như HTTP session; request sau được tải lại context và gắn vào holder của thread hiện tại.

**Câu 3.** `RequestAttributeSecurityContextRepository` có làm người dùng đăng nhập mãi trên trình duyệt không?

*Trả lời:* Không; request attributes thuộc một ServletRequest, không persist qua hai HTTP request độc lập.

**Câu 4.** Phương thức API nào nên ưu tiên thay cho `loadContext(HttpRequestResponseHolder)` đã deprecated?

*Trả lời:* `loadDeferredContext(HttpServletRequest)`, rồi đọc `DeferredSecurityContext.get()` khi cần.

**Câu 5.** `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter` khác nhau ở bước lưu ra sao?

*Trả lời:* HolderFilter tải context nhưng không tự lưu; PersistenceFilter kiểu cũ có cơ chế auto-save khi context thay đổi.

**Câu 6.** Custom controller đã gọi `setContext(context)` sau khi xác thực; vì sao request sau vẫn anonymous?

*Trả lời:* Với explicit save, nó chưa gọi `SecurityContextRepository.saveContext(context,request,response)` vào repository phù hợp hoặc response/session không thể ghi.

**Câu 7.** Vì sao built-in form login vẫn giữ được session trong Spring Security hiện đại?

*Trả lời:* Authentication filter của framework xử lý success flow và lưu context theo cấu hình; việc HolderFilter không auto-save không ngăn thành phần authentication khác chủ động save.

**Câu 8.** `SessionCreationPolicy.NEVER` và `STATELESS` có tương đương không?

*Trả lời:* Không. NEVER không chủ động tạo session nhưng có thể dùng session đã có; STATELESS không dùng HTTP session để lấy SecurityContext.

**Câu 9.** Một `SecurityContext` tồn tại trong HTTP session có chứng minh role hiện tại ở DB vẫn đúng không?

*Trả lời:* Không; có thể là snapshot từ lúc login. Cần thiết kế làm mới/thu hồi hoặc kiểm tra quyền hiện hành.

**Câu 10.** `SecurityContextRepository.saveContext` có làm logout token JWT trên máy người dùng không?

*Trả lời:* Không; đây là API lưu context trên server. JWT có cơ chế validation/lifetime/revocation riêng.

**Câu 11.** Để test persistence giữa request, vì sao phải thực hiện hai request khác nhau?

*Trả lời:* Vì chỉ kiểm tra `SecurityContextHolder` trong một request chưa chứng minh context đã được lưu và tải lại từ repository.

**Câu 12.** Khi custom login cần tạo session cookie, phải gọi save trước hay sau `sendRedirect`?

*Trả lời:* Trước khi response commit/redirect để còn cơ hội lưu context và gửi session identifier hợp lệ.

## 17. Checklist trước khi đưa vào hệ thống thật

- [ ] Đúng stack Servlet và dùng `SecurityContextRepository` của `org.springframework.security.web.context`, không trộn `ServerSecurityContextRepository` của WebFlux.
- [ ] Biết rõ trong mỗi chain đang dùng `SecurityContextHolderFilter` (explicit save) hay cơ chế legacy; không thêm cả hai.
- [ ] Biết repository thực tế là HttpSession, RequestAttribute, Delegating hay Null và vì sao lựa chọn ấy phù hợp.
- [ ] Nếu custom login, có bước `createEmptyContext → setAuthentication → setContext → saveContext` sau khi xác thực đáng tin.
- [ ] Response chưa commit trước khi lưu context cần tạo session/cookie.
- [ ] Cơ chế session fixation, CSRF, failure/success handlers, concurrency, logout và timeout được thiết kế đầy đủ.
- [ ] Không đưa raw password, OTP, bearer token hoặc dữ liệu nhạy cảm dư thừa vào `Authentication`/session.
- [ ] Session cookie dùng TLS/`Secure`/`HttpOnly`/`SameSite` phù hợp với ứng dụng.
- [ ] Nếu dùng stateless API, request phải được xác thực từ bằng chứng riêng; không phụ thuộc cookie của web session ngoài ý muốn.
- [ ] Có test cross-request thực tế với cookie/session, không chỉ test `@WithMockUser`.
- [ ] Có test logout/invalid session và request sau khi user bị vô hiệu hoặc quyền bị thu hồi.
- [ ] Phân biệt REQUEST, ERROR và ASYNC dispatch; không log nhầm hoặc lộ SecurityContext trong trang lỗi.
- [ ] Có cơ chế context propagation khi xử lý async/thread pool, và dọn holder đúng lifecycle.
- [ ] Với nhiều node, session store/serialization/TTL/invalidations được thiết kế rõ; không ngầm dựa vào in-memory session trên một node.
- [ ] Không coi persisted authorities luôn mới; hành động nhạy cảm cần authorization theo nguồn hiện hành.
- [ ] Kiểm tra `securityMatcher`, `@Order`, session policy và repository của từng chain.
- [ ] Khi debug, xác minh cả context được **save** sau login lẫn context được **load** ở request sau.
- [ ] Có giám sát lỗi session/repository nhưng không để lộ cookie, bearer token hoặc password trong log.

### Tổng kết

**`SecurityContextHolder` giữ ngữ cảnh cho phần xử lý hiện tại; `SecurityContextRepository` quyết định ngữ cảnh ấy được nạp/lưu ở đâu.** Trong Servlet hiện đại, `SecurityContextHolderFilter` đảm nhận tải chứ không tự lưu. Form login do framework cung cấp thường đã có thành phần chủ động lưu; **custom authentication code** phải gọi `saveContext` đúng chỗ nếu muốn duy trì danh tính ở request tiếp theo.

Hãy luôn xác định **phạm vi** của repository: HTTP session phục vụ nhiều request, request attribute phục vụ một request qua nhiều dispatch, Null repository không lưu, và Delegating kết hợp các phạm vi khi phù hợp. Cuối cùng, lưu context không thay thế bảo vệ cookie/session, quản lý timeout, xử lý logout hay cập nhật quyền sau khi dữ liệu nghiệp vụ thay đổi.

### Tài liệu chính thức

- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security — SecurityContextHolderFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/SecurityContextHolderFilter.html)
- [Spring Security — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security — RequestAttributeSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html)
- [Spring Security — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html)
- [Spring Security — NullSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/NullSecurityContextRepository.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Boot 4 — Starters and Test Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
