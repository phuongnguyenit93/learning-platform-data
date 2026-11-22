# DelegatingSecurityContextRepository và lưu SecurityContext qua nhiều nơi

## 1. Vì sao một SecurityContext cần được lưu ở nhiều nơi?

Trong Spring Security Servlet, `SecurityContext` chứa `Authentication` đại diện cho danh tính và quyền hạn đang được dùng để xử lý request. `SecurityContextHolder` giúp mã đang chạy trong một thread truy cập ngữ cảnh này. Nhưng một `ThreadLocal` của request hiện tại **không phải** nơi lưu trữ bền vững cho request kế tiếp, và cũng không giải quyết mọi lần dispatch của Servlet container.

Để tách việc **sử dụng ngữ cảnh hiện tại** khỏi việc **đọc/ghi ngữ cảnh vào một nơi lưu trữ**, Spring Security có giao diện `SecurityContextRepository`. Cài đặt `DelegatingSecurityContextRepository` kết hợp nhiều repository theo thứ tự: khi đọc, tìm ngữ cảnh ở các delegate; khi lưu, chuyển yêu cầu lưu cho các delegate.

Hai delegate điển hình trong ứng dụng Servlet có session là:

- `RequestAttributeSecurityContextRepository`: lưu trong thuộc tính của **ServletRequest** để có thể đọc lại trong cùng request, bao gồm các tình huống dispatch phù hợp.
- `HttpSessionSecurityContextRepository`: lưu trong **HttpSession** để ngữ cảnh có thể được khôi phục ở các HTTP request tiếp theo thuộc cùng session, nếu chính sách ứng dụng cho phép.

Ý tưởng quan trọng: **mỗi nơi giải quyết một phạm vi tồn tại khác nhau**. “Lưu qua nhiều nơi” ở đây là phối hợp các kho ngữ cảnh trong chu trình Servlet, không phải sao chép toàn bộ dữ liệu người dùng vào nhiều cơ sở dữ liệu.

Mục tiêu sau bài học: phân biệt `SecurityContextHolder` với `SecurityContextRepository`; giải thích vì sao request attribute và session có thể được dùng đồng thời; đọc được thứ tự load/save; hiểu `SecurityContextHolderFilter` và explicit save; tự kiểm chứng ngữ cảnh qua các request và tránh các cấu hình gây mất phiên.

## 2. Bốn khái niệm không nên trộn lẫn

| Thành phần | Câu hỏi nó giải quyết | Phạm vi/đặc điểm |
| --- | --- | --- |
| `Authentication` | Ai đang được xác thực, có các authority nào? | Đối tượng danh tính/quyền; có thể được đặt trong `SecurityContext`. |
| `SecurityContext` | Ngữ cảnh bảo mật hiện tại chứa Authentication nào? | Có thể được tạo mới, gắn Authentication, hoặc khôi phục từ repository. |
| `SecurityContextHolder` | Code của luồng xử lý hiện tại lấy SecurityContext bằng cách nào? | Thường dùng `ThreadLocal`; cần clear đúng cách, không tự tạo tính bền vững qua request. |
| `SecurityContextRepository` | Tìm và lưu SecurityContext ở đâu? | Giao diện lưu/khôi phục; repository có thể dựa trên request, HTTP session hoặc cơ chế khác. |

Ví dụ, một filter xác thực thành công có thể tạo context rồi gọi:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Đây là **đoạn trích trong một filter/handler có đủ các biến `authentication`, `request`, `response` và `securityContextRepository`**, không phải lớp Java độc lập. Nó cho thấy hai hành động khác nhau:

1. `setContext(context)` giúp phần xử lý ở luồng hiện tại nhìn thấy Authentication.
2. `saveContext(...)` yêu cầu kho lưu ngữ cảnh, để các bước hoặc request sau có thể khôi phục theo cơ chế đã cấu hình.

Chỉ thực hiện bước 1 **không bảo đảm** bước 2 xảy ra tự động trong Spring Security 6.

## 3. SecurityContextRepository và hợp đồng load/save

Ở Spring Security 6, giao diện repository phục vụ các thao tác cốt lõi:

- `loadDeferredContext(HttpServletRequest request)`: cung cấp một `DeferredSecurityContext` để có thể trì hoãn việc truy xuất ngữ cảnh cho tới lúc cần. Đây là hướng tiếp cận của các filter hiện đại.
- `saveContext(SecurityContext context, HttpServletRequest request, HttpServletResponse response)`: ghi ngữ cảnh theo chính sách repository và trạng thái request/response.
- `containsContext(HttpServletRequest request)`: kiểm tra repository có ngữ cảnh đã được lưu cho request đó hay không, theo ý nghĩa của implementation.

Những API cũ như `loadContext(HttpRequestResponseHolder)` có thể xuất hiện trong mã lịch sử hoặc tài liệu phiên bản khác; không nên tự coi mọi phiên bản dùng cùng một đường đi.

`DelegatingSecurityContextRepository` có thể nhận nhiều `SecurityContextRepository` khi khởi tạo:

```java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
```

Đoạn trên cần các import từ `org.springframework.security.web.context` và được sử dụng trong môi trường Spring Security Servlet; nó minh họa việc ghép **hai nơi lưu**, không tự đăng ký vào filter chain.

### 3.1. Quy tắc đọc: tìm context theo thứ tự

Tư duy để đọc hành vi `DelegatingSecurityContextRepository`:

```text
Cần khôi phục SecurityContext
        |
        v
Delegate #1: RequestAttributeSecurityContextRepository
        |
        +-- có context? ---> dùng context này
        |
        +-- không -------> Delegate #2: HttpSessionSecurityContextRepository
                              |
                              +-- có context? ---> dùng context này
                              |
                              +-- không -------> context rỗng/mặc định
```

**Thứ tự delegate có ý nghĩa đối với việc đọc.** Context từ request attribute được ưu tiên khi sẵn có, ví dụ cần bảo toàn context cho một lần `ERROR` dispatch trong cùng request. Nếu request mới không có attribute, repository có thể lấy context từ session.

Đây là mô hình hành vi để học, không cam kết các implementation đều gọi trực tiếp `loadContext` từng lần: phiên bản hiện đại có `DeferredSecurityContext`, tối ưu truy xuất và có thể trì hoãn việc load.

### 3.2. Quy tắc ghi: chuyển tới tất cả delegate

Khi gọi `saveContext(context, request, response)` trên repository kết hợp, thao tác lưu được chuyển đến **mọi delegate** theo logic của chúng:

```text
saveContext(context, request, response)
        |
        +--> RequestAttributeSecurityContextRepository.saveContext(...)
        |
        +--> HttpSessionSecurityContextRepository.saveContext(...)
```

Đừng hiểu đây là giao dịch cơ sở dữ liệu có rollback đồng bộ: mỗi repository có quy tắc riêng, và việc truyền lời gọi `saveContext` tới delegate **không bảo đảm** mọi nơi đều ghi bền vững một bản sao. Ví dụ, `HttpSessionSecurityContextRepository` có thể không tạo session hoặc không lưu một ngữ cảnh anonymous/rỗng tùy chính sách và trạng thái hiện tại.

**Tóm gọn cơ chế:** load ưu tiên repository đầu tiên có context phù hợp; save phân phối yêu cầu tới các delegate. Vì vậy thứ tự danh sách không chỉ là vấn đề trình bày.

## 4. Hai delegate mặc định và bài toán thực tế của từng nơi

### 4.1. RequestAttributeSecurityContextRepository

Một Servlet request có thể trải qua nhiều giai đoạn dispatch như `REQUEST`, `FORWARD`, `ERROR` hoặc `ASYNC`, phụ thuộc ứng dụng và cấu hình container. Ở một số container, ngữ cảnh hiện tại được clear khỏi `SecurityContextHolder` giữa các giai đoạn. Tuy vậy, dữ liệu gắn vào `ServletRequest` vẫn có thể được dùng trong phạm vi request/dispatch có liên quan.

`RequestAttributeSecurityContextRepository` bảo toàn ngữ cảnh ở request attribute để lần dispatch phù hợp có thể khôi phục lại context.

Tình huống điển hình:

```text
REQUEST /orders/123
  |
  +--> authentication thành công, context được save
  |
  +--> controller/servlet ném lỗi
  |
  +--> SecurityContextHolder được clear ở ranh giới xử lý
  |
  +--> ERROR dispatch tới /error (nếu được ánh xạ)
          |
          +--> load từ request attribute
          |
          +--> thông tin Authentication có thể vẫn sẵn có
```

Sơ đồ diễn tả **mục đích của repository**. Việc filter có chạy trong `ERROR` dispatch hay không còn phụ thuộc dispatcher type, filter mapping và cấu hình Spring Security; không thể khẳng định mọi ứng dụng tự động thực hiện chính xác chuỗi trên.

Request attribute **không kéo dài qua một HTTP request mới**. Người dùng bấm F5 hoặc gửi GET tiếp theo không mặc nhiên có lại attribute của request trước.

### 4.2. HttpSessionSecurityContextRepository

`HttpSessionSecurityContextRepository` dùng `HttpSession` làm nơi lưu context, thường với key do Spring Security quản lý (chẳng hạn `SPRING_SECURITY_CONTEXT`). Nó giúp khôi phục Authentication cho các HTTP request tiếp theo thuộc cùng session.

```text
Request #1: POST /login thành công
    |
    +--> SecurityContext được lưu vào HttpSession
    |
Response mang session cookie phù hợp
    |
    v
Request #2: GET /account, gửi lại session cookie
    |
    +--> session được tìm thấy
    +--> khôi phục SecurityContext từ session
    +--> endpoint có thể nhận principal đã đăng nhập
```

Để bước khôi phục thành công cần **cùng session hợp lệ**, session chưa hết hạn/chưa bị vô hiệu hóa, cấu hình lưu tương ứng, và client gửi cookie hoặc cơ chế session identifier đang sử dụng. Repository **không tự xác thực lại password trong mỗi request** khi nạp từ session.

Lưu ý quan trọng:

- Repository không nhất thiết tạo session cho request anonymous hoặc context không thay đổi. Cách xử lý phụ thuộc chính sách tạo session và trạng thái Authentication.
- `SessionCreationPolicy.STATELESS` thể hiện yêu cầu không sử dụng HTTP session để giữ SecurityContext; nếu ứng dụng API stateless, không nên kỳ vọng context trong session sống qua request.
- Ứng dụng nhiều node cần có chiến lược chia sẻ/định tuyến session nếu muốn duy trì phiên đăng nhập khi request chuyển node; repository tự nó không làm mọi node có chung bộ nhớ.
- Logout, session expiration, session fixation protection và concurrency control ảnh hưởng đến vòng đời session; chỉ hiểu repository là chưa đủ để thiết kế đầy đủ quản trị phiên.

## 5. Vì sao cần dùng cả RequestAttribute lẫn HttpSession?

Giả sử ứng dụng có đăng nhập bằng form và đồng thời muốn xử lý trang lỗi có ngữ cảnh bảo mật phù hợp.

Nếu **chỉ dùng RequestAttributeSecurityContextRepository**, một dispatch thuộc cùng request có thể khôi phục context, nhưng HTTP request kế tiếp không thể dựa vào request attribute cũ. Người dùng có thể mất trạng thái đăng nhập sau redirect nếu không có cơ chế lưu khác.

Nếu **chỉ dùng HttpSessionSecurityContextRepository**, ngữ cảnh có thể sống qua request, nhưng một số luồng dispatch hoặc tình huống session chưa được tạo có thể cần ngữ cảnh gắn trực tiếp vào request để khôi phục nhất quán trong cùng vòng đời.

Kết hợp hai repository đáp ứng cả hai nhu cầu mà không bắt người viết filter tự đồng bộ ngữ cảnh giữa request attribute và session.

| Tình huống | Request attribute | HTTP session |
| --- | --- | --- |
| Đọc lại trong cùng request/dispatch được hỗ trợ | Có thể hữu ích | Có thể dùng nếu session/context hợp lệ |
| Request HTTP mới dùng cùng session | Không còn attribute cũ | Có thể nạp context đã lưu |
| Không có HTTP session | Có thể lưu trong request hiện tại | Không thể đọc context từ session chưa tồn tại |
| Session đã hết hạn hoặc logout | Attribute của request đang chạy có thể tồn tại tới hết request | Context cũ không còn sẵn cho request mới |
| API stateless, client gửi token mỗi request | Có thể giữ ngữ cảnh nội bộ của request | Thường không được dùng để nhớ đăng nhập |

Bảng diễn đạt phạm vi lưu trữ; có hay không `SecurityContext` trong từng thời điểm còn phụ thuộc filter đã save, dispatcher, chính sách session và cơ chế authentication.

## 6. Ai thực sự đọc và lưu: SecurityContextHolderFilter và SecurityContextPersistenceFilter

### 6.1. Cơ chế phổ biến của Spring Security 6

Với cấu hình hiện đại, `SecurityContextHolderFilter` dùng `SecurityContextRepository` để cung cấp context cho `SecurityContextHolder` trong quá trình xử lý request, và clear holder khi hoàn tất nhánh đồng bộ phù hợp.

```text
SecurityContextHolderFilter
  |
  +--> repository.loadDeferredContext(request)
  |
  +--> SecurityContextHolder có deferred context
  |
  +--> phần còn lại của security filters / endpoint
  |
  +--> clear SecurityContextHolder khi kết thúc
```

**Điểm quan trọng:** `SecurityContextHolderFilter` **không tự động gọi `saveContext` ở cuối request**. Spring Security 6 ưu tiên mô hình **explicit save**: thành phần thay đổi Authentication phải bảo đảm ngữ cảnh được lưu khi cần duy trì ở repository.

Trong cơ chế đăng nhập chuẩn như form login, filter xác thực của Spring Security thường thực hiện việc lưu context sau khi xác thực thành công. Vì vậy “cần explicit save” không có nghĩa mọi ứng dụng form login đều phải tự thêm câu lệnh `saveContext` trong controller.

### 6.2. Khác biệt với SecurityContextPersistenceFilter

Trong cấu hình cũ hoặc chế độ tương thích, `SecurityContextPersistenceFilter` nạp context trước request và có cơ chế tự lưu lại vào repository lúc request kết thúc. Ngay cả khi dùng mô hình này, thời điểm response commit và wrapper vẫn có ý nghĩa.

Không nên đưa cả hai filter vào chain chỉ để “chắc chắn lưu được”. Khi đọc mã hoặc log, cần xác nhận ứng dụng dùng `SecurityContextHolderFilter` hay `SecurityContextPersistenceFilter` và cơ chế `requireExplicitSave` được chọn.

### 6.3. Vì sao thời điểm lưu là quan trọng?

Giả sử filter tự xác thực thành công rồi gọi `response.sendRedirect("/profile")` **trước** khi lưu context. Response có thể bị commit, session mới hoặc session ID cần gửi bằng cookie có thể không được phản ánh đúng cho browser. Request tiếp theo sẽ thiếu ngữ cảnh dù đoạn xử lý trước đó đặt `SecurityContextHolder` thành công.

Vì thế, với cơ chế xác thực tùy biến, hãy tạo context, đặt Authentication, **gọi saveContext trước khi hoàn tất/commit response**, rồi mới redirect hoặc trả response thành công.

Một sơ đồ thứ tự hữu ích:

```text
Xác thực credentials/token
    |
    v
Tạo SecurityContext mới
    |
    v
context.setAuthentication(result)
    |
    v
SecurityContextHolder.setContext(context)
    |
    v
repository.saveContext(context, request, response)
    |
    v
Commit response / redirect
```

Tạo context mới bằng `SecurityContextHolder.createEmptyContext()` cũng giúp tránh việc sửa chung trực tiếp một đối tượng context có thể đang được chia sẻ qua session giữa những request đồng thời.

## 7. Cấu hình DelegatingSecurityContextRepository trong Spring Security Servlet

Nếu muốn **nêu tường minh** hai delegate thay vì phụ thuộc defaults của phiên bản, có thể khai báo repository riêng và gắn vào `HttpSecurity`.

Ví dụ sau dùng Spring Boot 3.3.x / Spring Security 6.x / Java 17. Lớp là **một phần của ứng dụng Spring**, không chạy độc lập bằng `java SecurityConfig`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
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

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository)
            throws Exception {

        http
            .securityContext(security -> security
                .securityContextRepository(securityContextRepository)
                .requireExplicitSave(true))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learning-only"))
                .roles("USER")
                .build()
        );
    }
}
```

Giải thích từng lựa chọn:

1. `securityContextRepository()` tạo một delegate cho request attribute và một delegate cho HTTP session **theo đúng thứ tự đọc mong muốn**.
2. `securityContext(security -> security.securityContextRepository(...))` gắn repository này với cơ chế quản lý security context của chain.
3. `requireExplicitSave(true)` làm rõ mô hình explicit save. Filter xử lý đăng nhập chuẩn chịu trách nhiệm lưu context sau khi xác thực; nếu bạn tự viết cơ chế đăng nhập, phải lưu đúng cách.
4. `formLogin` giúp ví dụ có một luồng đăng nhập sử dụng session và redirect. Form login mặc định đòi hỏi CSRF token hợp lệ khi POST `/login`.
5. `PasswordEncoder` và `InMemoryUserDetailsManager` dùng để tạo một tài khoản ví dụ. Mật khẩu này **chỉ dùng trong môi trường học tập**, không phải cách cấp tài khoản thật.

**Không cấu hình thêm `SessionCreationPolicy.STATELESS` cho cùng ví dụ nếu mục tiêu là chứng minh login được giữ qua HTTP session.** API dùng bearer token mỗi request có chính sách khác và không nên trộn lẫn mô hình.

## 8. Kiểm chứng với một ứng dụng Spring Boot và MockMvc

Phần này mở rộng lớp `SecurityConfig` ở trên thành ứng dụng tối giản có thể chạy/kiểm thử với Java 17 và Maven. Các đoạn `pom.xml`, application, controller, test dưới đây tạo thành một ví dụ thống nhất.

### 8.1. Cấu trúc

```text
context-repository-demo/
  pom.xml
  src/
    main/java/example/security/
      SecurityDemoApplication.java
      SecurityConfig.java
      DemoController.java
    test/java/example/security/
      SecurityContextRepositoryTest.java
```

### 8.2. Cấu hình Maven

Tạo `pom.xml`:

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
    <artifactId>context-repository-demo</artifactId>
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

### 8.3. Lớp khởi động

`src/main/java/example/security/SecurityDemoApplication.java`:

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

### 8.4. Endpoint công khai và yêu cầu đăng nhập

`src/main/java/example/security/DemoController.java`:

```java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

`/private` nhận Authentication do hạ tầng bảo mật cung cấp sau khi context được khôi phục. Nếu chưa xác thực, quy tắc `anyRequest().authenticated()` yêu cầu đăng nhập trước khi controller được gọi.

### 8.5. Test request đăng nhập và request mới cùng session

`src/test/java/example/security/SecurityContextRepositoryTest.java`:

```java
package example.security;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextRepositoryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginStoresContextForNextRequestUsingSameSession()
            throws Exception {
        var loginResult = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "learning-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession saved = loginResult.getRequest().getSession(false);
        assertNotNull(saved, "Successful login needs a session");

        MockHttpSession session = (MockHttpSession) saved;

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));
    }

    @Test
    void requestWithoutSessionIsNotAlreadyLoggedIn()
            throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicRequestDoesNotRequireLogin()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

Ở phép thử đăng nhập, POST dùng `csrf()` để cung cấp token hợp lệ theo cấu hình Spring Security Test. Sau khi đăng nhập thành công, test lấy `MockHttpSession` từ request đầu và truyền lại cho một request `GET /private` mới. Nếu phần lưu/khôi phục hoạt động, controller nhìn thấy principal `learner` và trả body `hello learner`.

**Giới hạn của phép thử:** test này kiểm tra kết quả tích hợp của repository được cấu hình và form login; nó không trực tiếp chứng minh từng delegate đã được gọi bao nhiêu lần. Để kiểm chứng từng lời gọi `saveContext`, có thể dùng mock/spy hoặc quan sát repository riêng. Nó cũng không kiểm tra hành vi `ERROR` dispatch của từng Servlet container.

Chạy trong thư mục có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Các thông điệp khởi động/build Maven chứa timestamp và thông tin máy nên không có stdout cố định. **Các kết quả xác định cần kiểm chứng là assertion:** ba test pass; GET `/public` trả 200/body `public`; GET `/private` trước khi có session được redirect; GET `/private` với session sau login trả 200/body `hello learner`.

## 9. Chạy Java 17 độc lập để quan sát thứ tự đọc/ghi của các delegate

Nếu chưa chạy Spring Boot, bạn vẫn có thể hiểu hành vi kết hợp bằng một mô hình thuần Java. **Đoạn code này cố ý dùng interface tự tạo `Store`, không phải implementation Spring Security**, và `Map` mô phỏng storage; nó chỉ chứng minh thứ tự tìm và phân phối thao tác lưu, không giả vờ mô phỏng toàn bộ Servlet/session policy.

Tạo file `DelegatingStorageDemo.java`:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class DelegatingStorageDemo {

    record Identity(String username) {}

    static class Request {
        final Map<String, Identity> attributes = new HashMap<>();
        final Map<String, Identity> session;

        Request(Map<String, Identity> session) {
            this.session = session;
        }
    }

    interface Store {
        Optional<Identity> load(Request request);
        void save(Request request, Identity identity);
    }

    static class RequestAttributeStore implements Store {
        public Optional<Identity> load(Request request) {
            return Optional.ofNullable(request.attributes.get("CONTEXT"));
        }

        public void save(Request request, Identity identity) {
            request.attributes.put("CONTEXT", identity);
        }
    }

    static class SessionStore implements Store {
        public Optional<Identity> load(Request request) {
            return Optional.ofNullable(request.session.get("CONTEXT"));
        }

        public void save(Request request, Identity identity) {
            request.session.put("CONTEXT", identity);
        }
    }

    static class DelegatingStore implements Store {
        private final List<Store> delegates;

        DelegatingStore(List<Store> delegates) {
            this.delegates = delegates;
        }

        public Optional<Identity> load(Request request) {
            for (Store delegate : delegates) {
                Optional<Identity> context = delegate.load(request);
                if (context.isPresent()) {
                    return context; // Ưu tiên delegate đầu tiên có dữ liệu.
                }
            }
            return Optional.empty();
        }

        public void save(Request request, Identity identity) {
            for (Store delegate : delegates) {
                delegate.save(request, identity); // Gửi cho mọi delegate.
            }
        }
    }

    public static void main(String[] args) {
        Map<String, Identity> sharedSession = new HashMap<>();

        Store repository = new DelegatingStore(List.of(
            new RequestAttributeStore(),
            new SessionStore()
        ));

        Request first = new Request(sharedSession);
        repository.save(first, new Identity("linh"));

        System.out.println("first request: "
            + repository.load(first).orElseThrow().username());
        System.out.println("session stored: "
            + sharedSession.containsKey("CONTEXT"));

        Request second = new Request(sharedSession);
        System.out.println("second request attribute: "
            + second.attributes.containsKey("CONTEXT"));
        System.out.println("second request loaded: "
            + repository.load(second).orElseThrow().username());

        second.attributes.put("CONTEXT", new Identity("local"));
        System.out.println("request first priority: "
            + repository.load(second).orElseThrow().username());
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac DelegatingStorageDemo.java
java DelegatingStorageDemo
```

Stdout **chính xác** với JDK 17+:

```text
first request: linh
session stored: true
second request attribute: false
second request loaded: linh
request first priority: local
```

Giải thích: `save` trên repository kết hợp ghi cả request attribute lẫn bản đồ session. Đến request thứ hai, attribute mới trống nên `load` tìm tiếp trong session. Khi cố ý thêm giá trị khác vào attribute, repository đọc delegate đầu tiên có dữ liệu, kết quả là `local`.

Mô hình đơn giản này **không có** chính sách anonymous/session creation, deferred context, thread-local, login filter hoặc cookie/session ID của Spring. Đó là lý do dùng nó để học thuật toán phối hợp, còn dùng MockMvc ở phần trên để kiểm chứng tích hợp thật.

## 10. Khác biệt với các repository khác

Một số lựa chọn thay thế hoặc bổ sung cần nhận diện:

**`NullSecurityContextRepository`:** không duy trì SecurityContext giữa các request bằng kho này. Hữu ích khi ứng dụng thực sự stateless và xác thực lại từ bearer token hoặc cơ chế tương ứng ở mỗi request. Không kết hợp một cách tùy tiện với yêu cầu đăng nhập bằng session.

**`HttpSessionSecurityContextRepository` dùng riêng:** phục vụ mô hình session, nhưng không có lợi ích bổ sung của request-attribute delegate trong các luồng dispatch cần đến nó.

**`RequestAttributeSecurityContextRepository` dùng riêng:** giữ ngữ cảnh theo phạm vi request, không đủ để “nhớ đăng nhập” qua các HTTP request chỉ nhờ request attribute.

**`DelegatingSecurityContextRepository` với repository tùy biến:** có thể ghép nhiều nơi khác nhau khi thực sự có yêu cầu đặc biệt. Khi đó cần làm rõ ưu tiên đọc, semantics lưu, lỗi từng delegate, điều kiện xóa, tính nhất quán và bảo vệ dữ liệu. Không tự giả định các nơi lưu đồng bộ giao dịch.

Thứ tự và loại repository cần phản ánh yêu cầu runtime. API stateless, ứng dụng session truyền thống và ứng dụng xử lý error dispatch có nhu cầu khác nhau.

## 11. Những lỗi dễ gặp và hướng sửa

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Sau khi custom authentication thành công, redirect tới trang mới lại mất login | Chỉ `SecurityContextHolder.setContext`, quên `saveContext` trong mô hình explicit save | Tạo context mới, đặt Authentication, lưu bằng repository đang được chain sử dụng **trước** khi response commit. |
| GET đầu thấy user, GET kế tiếp anonymous | Không có/còn HTTP session, cookie không được gửi, session expired, dùng stateless hoặc repository request-only | Kiểm tra session policy, session ID/cookie, repository trong đúng SecurityFilterChain. |
| Trong error page mất Authentication | Không lưu request attribute, context đã clear giữa dispatch, hoặc filter không chạy cho `ERROR` | Kiểm tra dispatcher mappings và RequestAttributeSecurityContextRepository; không mặc định tất cả ERROR dispatch được bảo vệ giống nhau. |
| Đã cấu hình bean Delegating repository nhưng behavior không đổi | Bean không được gắn vào SecurityFilterChain đang chọn, hoặc có nhiều chains | Kiểm tra `securityContext(...securityContextRepository(...))` của chain phù hợp. |
| Login có session nhưng context không được load | Dùng session khác, cookie không đúng path/domain, session bị invalidate, context không được lưu | Xác minh cùng session và thời điểm save/redirect. |
| Debug thấy context trong ThreadLocal nhưng repository trống | Holder là ngữ cảnh đang xử lý, không phải storage | Phân biệt set context với explicit save. |
| Cố dùng session để truyền context giữa worker threads | Repository quản lý request/session storage, không tự propagate ThreadLocal | Sử dụng cơ chế propagation được hỗ trợ khi cần; không copy thread-local tùy ý. |
| Thay Authentication trong context lấy từ session, request khác bị ảnh hưởng | SecurityContext là object có thể thay đổi, request đồng thời có thể chia sẻ tham chiếu | Tạo context mới, đặt Authentication, save theo chính sách thay vì mutate context chia sẻ. |
| Nhầm 401/403 với việc repository không tìm được context | Authentication filter, AuthorizationFilter và exception translation đều có thể ảnh hưởng response | Tìm đúng SecurityFilterChain/filter và sự kiện authentication trước khi đổ lỗi cho repository. |
| Xóa session nhưng cùng request vẫn có context | RequestAttribute delegate có phạm vi khác; holder có thể vẫn giữ ngữ cảnh trong request hiện tại | Logout cần dùng quy trình Spring Security chuẩn để dọn holder và xử lý lưu/xóa context, đồng thời invalidate session đúng cách. |

### Cần lưu ý khi đổi cấu hình lưu context

Nếu chuyển từ session-based sang stateless, hãy đánh giá đồng bộ authentication mechanism, CSRF/session policy, security context repository và logout/session handling. Thay một bean không đủ để bảo đảm ứng dụng thực sự stateless, cũng không đủ để chứng minh đã vô hiệu hóa mọi session.

## 12. Kiểm tra tải, race condition và an toàn

`SecurityContextHolder` mặc định sử dụng ngữ cảnh gắn với thread. Repository đọc/ghi khi được gọi, nhưng **không phải bộ quản lý khóa** cho mọi request đồng thời của cùng một session. Ví dụ hai tab browser có thể gửi request cùng lúc; nếu cùng tham chiếu đến một mutable SecurityContext trong session, cập nhật trực tiếp Authentication trên context đó có thể gây hành vi khó dự đoán.

Quy tắc an toàn:

1. Dùng `SecurityContextHolder.createEmptyContext()` khi cần thay Authentication, rồi `setContext` và `saveContext` thay vì sửa trực tiếp context hiện có mà không xét tính chia sẻ.
2. Đừng lưu credentials nhạy cảm hoặc object không phù hợp vào Authentication/session; phải cân nhắc serialization nếu session được phân tán.
3. Không tự quản lý session cookie bằng cách ghép string hoặc log session ID/token.
4. Tách request attribute, HTTP session và thread-local theo đúng phạm vi sống; các cơ chế này giải quyết các vấn đề khác nhau.
5. Nếu cần propagation sang tác vụ bất đồng bộ, xem cơ chế tích hợp được Spring Security hỗ trợ cho executor/async và đảm bảo clear context; repository không tự làm ngữ cảnh xuất hiện trên mọi thread.

## 13. Debug từng bước khi “mất SecurityContext”

Khi request sau đăng nhập không còn authenticated, hãy kiểm tra:

1. **Đúng chain chưa?** Request đăng nhập và request truy cập tài nguyên có thể đi qua các `SecurityFilterChain` khác nhau. Xem `securityMatcher`, thứ tự và repository gắn với từng chain.
2. **Ai xác thực?** Đảm bảo cơ chế authentication hoàn thành và tạo `Authentication` hợp lệ, không chỉ đặt biến tùy ý.
3. **Ai lưu?** Với `SecurityContextHolderFilter`, xác minh filter/handler đăng nhập có gọi `saveContext` trên repository đúng lúc trước response commit.
4. **Lưu vào đâu?** Kiểm tra có request attribute và/hoặc session theo chính sách. `HttpSessionSecurityContextRepository` không mặc nhiên tạo session cho mọi trường hợp.
5. **Request tiếp theo dùng session nào?** Cookie/ID có được truyền lại không, session còn tồn tại không, có session fixation rotation hoặc logout không?
6. **Ai nạp?** Repository của chain đang chạy có đọc được SecurityContext không; nó có bị ghi đè bởi context rỗng hoặc logic tùy biến không?
7. **Có dispatch khác không?** `ERROR`/`FORWARD`/`ASYNC` có được map filter không? Có clear holder ở ranh giới xử lý không?

Có thể bật log phục vụ phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

DEBUG giúp định vị chain/filter trong nhiều trường hợp, nhưng không bảo đảm ghi toàn bộ từng quyết định nội bộ; cần breakpoint vào repository/filter khi muốn biết chính xác thời điểm load/save. Khi có dữ liệu thật, tránh in cookie, session ID hoặc credentials vào log.

## 14. Câu hỏi tự kiểm tra

**1. Repository có lưu ở hai nơi, vậy mỗi request mới có cùng hai nơi chứa context không?**

Không. Request attribute gắn với request riêng. Request mới chỉ có thể khôi phục context từ nơi tồn tại xuyên request như session (nếu dùng session hợp lệ), sau đó có thể lưu vào request attribute của request mới khi có thao tác save tương ứng.

**2. Nếu RequestAttribute repository có context khác HttpSession repository, cái nào được đọc trước?**

Với thứ tự khai báo `RequestAttribute` rồi `HttpSession` như ví dụ, delegate đầu được ưu tiên nếu có context. Đây là lý do thứ tự constructor quan trọng.

**3. Nếu chỉ đặt Authentication vào SecurityContextHolder rồi kết thúc handler trong Spring Security 6, login đã được duy trì chưa?**

Chưa thể khẳng định. Với `SecurityContextHolderFilter` và explicit save, phải có một thành phần gọi `saveContext` đúng lúc. Form login chuẩn đã có logic lưu của framework; custom authentication phải bảo đảm việc này.

**4. Vì sao có thể có context trong ERROR dispatch dù SecurityContextHolder đã clear?**

Vì `RequestAttributeSecurityContextRepository` có thể lưu context trên ServletRequest, cho phép khôi phục trong dispatch thuộc cùng request khi filter mapping và cấu hình phù hợp.

**5. Vì sao `saveContext` đến mọi delegate không bảo đảm mọi delegate ghi bền vững?**

Vì mỗi delegate tự áp dụng chính sách. Session repository có thể không tạo session hoặc không lưu ngữ cảnh không phù hợp; request attribute không tồn tại qua request mới. Delegation không đồng nghĩa giao dịch đồng bộ.

**6. Nếu ứng dụng yêu cầu stateless, có nên dùng HttpSessionSecurityContextRepository để “cho chắc” không?**

Không nên. Phải thống nhất policy xác thực lại mỗi request, session management và context repository. Thêm lưu session có thể đi ngược mục tiêu stateless.

## 15. Tóm tắt kiến thức trọng tâm

- `SecurityContextHolder` là cách truy cập context trong luồng xử lý; `SecurityContextRepository` là nơi đọc và ghi context.
- `DelegatingSecurityContextRepository` **đọc theo thứ tự delegate** và **gửi lệnh lưu tới mọi delegate**, với chính sách riêng của từng nơi.
- `RequestAttributeSecurityContextRepository` hữu ích trong phạm vi cùng Servlet request/dispatch; `HttpSessionSecurityContextRepository` cho phép khôi phục qua request mới dùng cùng session.
- `SecurityContextHolderFilter` trong mô hình hiện đại dùng deferred loading và không tự save ở cuối request; thao tác thay đổi Authentication cần được lưu chủ động khi muốn duy trì.
- Khi tự xác thực, tạo context mới, set Authentication, set holder, `saveContext(context, request, response)` **trước response commit**; filter đăng nhập chuẩn của framework thường đã xử lý phần lưu.
- Muốn debug mất login, kiểm tra đúng chain, đúng repository, thời điểm save, session/cookie, nơi nạp lại và các dispatcher, thay vì chỉ nhìn trạng thái `SecurityContextHolder` ở một thời điểm.
