# DelegatingSecurityContextRepository kết hợp các nơi lưu trữ

## Tổng quan

Trong Spring Security Servlet, `SecurityContext` giữ `Authentication` của request đang được xử lý. Vấn đề là ngữ cảnh này có thể cần được khôi phục tại **hai phạm vi thời gian khác nhau**:

1. **Trong cùng một servlet request:** container chuyển sang `FORWARD`, `ERROR` hoặc một dispatch khác; `SecurityContextHolder` của lần xử lý trước có thể đã bị dọn.
2. **Trong một HTTP request tiếp theo:** browser gửi session cookie sau lần đăng nhập trước; server cần tìm lại authentication từ `HttpSession`.

`DelegatingSecurityContextRepository` kết hợp nhiều implementation của interface `SecurityContextRepository` để phục vụ cả hai. Trong cấu hình Servlet mặc định của Spring Security 6, cặp delegate là:

~~~java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
~~~

`RequestAttributeSecurityContextRepository` giữ context bằng **request attribute** trong cùng servlet request; `HttpSessionSecurityContextRepository` giữ context bằng **HTTP session** qua các requests; `DelegatingSecurityContextRepository` **lưu tới các delegate** và **tải theo thứ tự** được cấu hình.

**Điểm cần nhớ:** *Request attribute giúp chuyển tiếp trong cùng request; HTTP session phục vụ request mới; Delegating ghép được cả hai mà không tạo một hệ thống xác thực riêng.*

Bài thuộc nhóm **Ngữ cảnh Servlet** của module *Spring Security - authentication*. Nội dung mô tả Spring Security 6.x và Spring Boot 3.x trên Java 17+. Không áp dụng nguyên các interface Servlet này cho WebFlux, nơi dùng `ServerSecurityContextRepository`.

Sau bài học, bạn có thể giải thích trách nhiệm của từng repository, thứ tự đọc/ghi, sự khác nhau giữa `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter`, cơ chế lưu tường minh và các tình huống session-based/stateless; đồng thời tự chạy ứng dụng và unit test để kiểm chứng.

## 1. Các khái niệm nền tảng

| Thành phần | Vai trò | Cần tránh nhầm với |
| --- | --- | --- |
| `Authentication` | Principal, authorities và thông tin xác thực | Không phải kho lưu session |
| `SecurityContext` | Chứa một `Authentication` cho ngữ cảnh bảo mật | Không tự động lưu qua các request |
| `SecurityContextHolder` | Cung cấp context cho execution hiện tại | Không phải persistence store |
| `SecurityContextHolderStrategy` | Cách holder gắn context với thread/execution | Không phải servlet request attribute |
| `SecurityContextRepository` | Hợp đồng đọc/ghi context từ nơi lưu | Không phải `AuthenticationManager` |
| `RequestAttributeSecurityContextRepository` | Lưu trên thuộc tính server-side của request | Không phải header/parameter client gửi |
| `HttpSessionSecurityContextRepository` | Lưu vào `HttpSession` | Không phải JWT/refresh token |
| `DelegatingSecurityContextRepository` | Điều phối nhiều repository | Không phải database replication |
| `SecurityContextHolderFilter` | Nạp context cho request qua repository | Không tự lưu context cuối request trong explicit-save mode |

Authentication và persistence là hai nhiệm vụ khác nhau. `AuthenticationManager` và provider mới kiểm tra username/password hoặc token, sau đó tạo authentication đã được tin cậy. Repository **chỉ ghi/tải kết quả**. Một user tồn tại trong DB hoặc có `SecurityContext` không chứng minh tất cả quyền truy cập; authorization còn kiểm tra authorities và account policy.

Ví dụ:

~~~text
HTTP login:
  client gửi credentials
       |
       v
  Authentication filter
       |
       v
  AuthenticationManager/Provider -> xác minh bằng chứng
       |
       v
  Authentication thành công
       |
       v
  SecurityContextHolder -> dùng trong request hiện tại
       |
       v
  SecurityContextRepository.saveContext(...)
       |
       v
  DelegatingSecurityContextRepository
       |                          |
       v                          v
  Request attribute          HTTP session
~~~

**Không bao giờ** tự tạo token authenticated từ username chưa kiểm chứng rồi đưa vào repository. Làm vậy bỏ qua authentication thực sự, dù code lưu/khôi phục context có vẻ hoạt động.

## 2. Hợp đồng SecurityContextRepository

Các method chính từ `org.springframework.security.web.context.SecurityContextRepository`:

~~~java
// Chữ ký API rút gọn để học; không phải file Java độc lập.
DeferredSecurityContext loadDeferredContext(
    HttpServletRequest request
);

void saveContext(
    SecurityContext context,
    HttpServletRequest request,
    HttpServletResponse response
);

boolean containsContext(HttpServletRequest request);

// API cũ đã deprecated:
SecurityContext loadContext(
    HttpRequestResponseHolder holder
);
~~~

### 2.1. loadDeferredContext: đọc khi cần

~~~java
// Fragment trong method có repository và request.
DeferredSecurityContext deferred =
    repository.loadDeferredContext(request);
SecurityContext current = deferred.get();
boolean generated = deferred.isGenerated();
~~~

`loadDeferredContext(...)` cho phép trì hoãn việc đọc thật sự từ repository. `get()` trả về context; `isGenerated()` cho biết context được sinh mới thay vì có sẵn trong kho. Không trả context `null`; nếu không tìm thấy danh tính lưu sẵn thì dùng context trống theo chiến lược phù hợp.

Với delegating repo, việc chọn một delegate diễn ra theo thứ tự cấu hình: kiểm tra nơi trước; nếu không có context hiện hữu, kiểm tra nơi tiếp. Nó không tìm “context mới nhất” bằng timestamp, không gộp authorities từ nhiều nguồn, không chọn principal có quyền cao nhất.

### 2.2. saveContext: gửi tới nhiều delegate

~~~java
repository.saveContext(context, request, response);
~~~

Nếu repository này là composite của request attribute và HTTP session, thao tác trên được chuyển cho cả hai delegate. Một cái lưu trong request object; cái còn lại lưu vào session **nếu context và chính sách phiên cho phép**. Không thể khẳng định save luôn tạo session mới, vì `HttpSessionSecurityContextRepository` tránh lưu session vô ích cho context rỗng/anonymous.

Không coi `saveContext` như transaction hai pha: nếu thêm Redis/DB backend tùy chỉnh, giao diện này không cung cấp rollback xuyên những kho dữ liệu độc lập.

### 2.3. containsContext: có dữ liệu, chưa phải có quyền

`repository.containsContext(request)` cho biết có context trong nguồn lưu phù hợp. Kết quả `true` **không đồng nghĩa** `Authentication.isAuthenticated()` hợp lệ, account không bị disabled hay user được vào `/admin`. Authorization phải dùng security rules được cấu hình, không dùng `containsContext` làm điều kiện cấp quyền.

## 3. Thứ tự ưu tiên: đọc khác với ghi

Giả sử:

~~~java
SecurityContextRepository repo =
    new DelegatingSecurityContextRepository(
        requestAttributeRepository,
        sessionRepository
    );
~~~

Khi **đọc**:

~~~text
repo.loadDeferredContext(request)
   |
   +--> RequestAttributeSecurityContextRepository
   |       có context hiện hữu -> chọn nó
   |       không có           -> tiếp tục
   |
   +--> HttpSessionSecurityContextRepository
   |       có context hiện hữu -> chọn nó
   |       không có           -> context mới/rỗng
   |
   v
SecurityContext cho SecurityContextHolder
~~~

Khi **ghi**:

~~~text
repo.saveContext(context, request, response)
   |
   +--> requestAttributeRepository.saveContext(...)
   |
   +--> sessionRepository.saveContext(...)
~~~

Đó là cơ chế **đọc chọn nguồn đầu tiên phù hợp, ghi tới các nguồn**. Vì vậy thứ tự của delegates là quyết định có ý nghĩa. Một custom delegate đặt trước session nhưng giữ context cũ có thể che context mới của session. Repository không sửa sự bất nhất này bằng cách so quyền/timestamp.

### 3.1. Ví dụ Bob ở request, Alice ở session

Trong unit test minh họa, session chứa Alice, nhưng request hiện tại có request attribute chứa Bob. Composite đặt request store trước session sẽ chọn Bob. Một HTTP request mới tạo request object mới không còn attribute của request trước, nên nếu dùng lại session thì có thể khôi phục Alice.

~~~text
Request R1:
  session = Alice
  attribute = Bob
  composite load -> Bob

Request R2, cùng session mới đi qua browser:
  session = Alice
  attribute của R1 không tồn tại
  composite load -> Alice
~~~

Đây là **mẫu test về thứ tự**, tuyệt đối không coi đó là cơ chế switch account hợp lệ. Trong production, nếu application chủ động đổi identity, phải có authentication/policy hợp lệ và lưu context nhất quán vào đúng repository; không chỉ sửa một attribute để “đăng nhập thành Bob”.

## 4. RequestAttributeSecurityContextRepository: cùng request, nhiều dispatch

Request attributes là dữ liệu server gắn với `ServletRequest`. Các dispatch như `DispatcherType.REQUEST`, `DispatcherType.FORWARD` và `DispatcherType.ERROR` có thể liên quan đến cùng request. Trong một số container, khi phát sinh lỗi, holder đã được clear trước khi error dispatch được xử lý.

~~~text
HTTP request #1
  REQUEST dispatch:
    đã xác thực Alice
    saveContext(...) -> request attribute của #1 có Alice
    controller xảy ra lỗi

  ERROR dispatch của request #1:
    holder cũ có thể đã bị dọn
    repository có thể khôi phục Alice từ attribute

HTTP request #2
  request attribute hoàn toàn mới
  không mang attribute của request #1
~~~

`RequestAttributeSecurityContextRepository` giúp một trang lỗi hoặc forward handler có khả năng nhìn thấy principal **trong cùng request**. Nhưng cần hiểu điều kiện: context phải được lưu, filter chain/dispatcher type phải có cơ hội load lại, container phải xử lý dispatch phù hợp. Nó **không đảm bảo** mọi error page luôn tự biết user.

### 4.1. Chỉ request attribute thì không giữ được login qua refresh

~~~java
// Fragment cấu hình trong SecurityFilterChain.
http.securityContext(sc -> sc
    .securityContextRepository(
        new RequestAttributeSecurityContextRepository()
    )
);
~~~

Một browser refresh hoặc click link gửi HTTP request mới; attribute server-side của request trước không được gửi theo. Nếu không có nơi lưu khác hoặc cơ chế xác thực lại mỗi request, user có thể thành anonymous. Đây là lý do không dùng riêng repository này thay cho session của form login nhiều request.

## 5. HttpSessionSecurityContextRepository: request kế tiếp

`HttpSessionSecurityContextRepository` lưu context trong `HttpSession`, mặc định theo key `SPRING_SECURITY_CONTEXT`. Servlet container quản lý session và cookie `JSESSIONID`, còn Spring Security quản lý nội dung `SecurityContext`.

~~~text
POST /login:
  filter/provider xác thực Alice
  session lưu SecurityContext Alice
  browser giữ session cookie

GET /me:
  browser gửi cookie cùng session ID
  server tìm session
  session repository trả SecurityContext Alice
  holder filter nạp context
  controller thấy Authentication Alice
~~~

Có `JSESSIONID` **không tự chứng minh** user đã đăng nhập: session còn có thể được tạo cho CSRF, request cache hoặc dữ liệu ứng dụng khác. Chỉ context authenticated hợp lệ cùng authorization phù hợp mới cho phép truy cập.

### 5.1. Không nhất thiết tạo session

`HttpSessionSecurityContextRepository` cố tránh tạo session không cần thiết. Theo API, việc load không tạo một session mới chỉ để đọc; khi save, nó tạo session nếu context khác empty/anonymous và policy cho phép. Method `setAllowSessionCreation(false)` có thể ngăn repository tạo session mới, nhưng không ngăn code khác tạo session.

Khi cần *kiểm tra* có session không, dùng:

~~~java
HttpSession existing = request.getSession(false);
~~~

Không dùng `request.getSession()` chỉ để kiểm tra, bởi nó có thể tạo session mới khiến việc debug bị nhầm.

### 5.2. Session fixation và nhiều node

Khi login thành công, Spring Security form login chuẩn tích hợp session fixation protection, thường đổi session ID trên servlet container hiện đại. Nếu tự viết login và chỉ save context thì chưa chắc bảo vệ đầy đủ.

Nếu ứng dụng chạy nhiều node mà session nằm trong bộ nhớ node A, một request đến node B có thể mất authentication. `DelegatingSecurityContextRepository` **không tự chia sẻ session giữa các node**. Cần sticky sessions hoặc backend/session storage được chia sẻ, ví dụ Spring Session nếu phù hợp.

Không cất raw password hoặc secrets trong principal/session. Một session store phân tán có thể yêu cầu serializable objects, vì vậy principal/context nên nhỏ, ổn định và phù hợp serialization policy.

## 6. Spring Security 6 và explicit save

Trong Spring Security 5, mô hình thường dùng `SecurityContextPersistenceFilter`, có cơ chế tự ghi context thay đổi lúc kết thúc request hoặc trước khi response commit. Spring Security 6 dùng `SecurityContextHolderFilter` mặc định; filter mới **nạp** context vào holder, **không tự save**.

| Filter | Load context | Save context |
| --- | --- | --- |
| `SecurityContextPersistenceFilter` | Có | Có thể tự lưu theo cơ chế cũ |
| `SecurityContextHolderFilter` | Có | **Không**; cần explicit save khi muốn persistence |

Đừng cấu hình đồng thời cả hai trên cùng chain.

### 6.1. requireExplicitSave là gì?

Spring Security 6 mặc định áp dụng mô hình tương ứng `requireExplicitSave(true)`. Có thể viết rõ:

~~~java
http.securityContext(sc -> sc
    .requireExplicitSave(true)
    .securityContextRepository(repository)
);
~~~

Đây là cấu hình minh họa khi đã có biến `HttpSecurity http` và `SecurityContextRepository repository`. Dòng này không có nghĩa **mỗi lần đọc** đều phải save lại. Chỉ khi code **tạo hoặc thay context và muốn lưu** qua requests/dispatch phù hợp, cần gọi `saveContext` đúng lúc.

### 6.2. Tại sao custom login thường mất session?

Đoạn sau chỉ đặt context vào holder:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
// Thiếu repo.saveContext(...); request kế tiếp có thể anonymous.
~~~

Với custom authentication đã được kiểm chứng, pattern đầy đủ hơn là:

~~~java
// Fragment: cần AuthenticationManager, SecurityContextRepository,
// HttpServletRequest/HttpServletResponse và credential inputs.
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context, request, response
);
~~~

Chỉ **AuthenticationManager/provider đã xác minh** mới được tạo authentication đáng tin. Đoạn này vẫn **chưa phải HTTP login production hoàn chỉnh**: còn session authentication strategy, session fixation, CSRF, rate limiting, success/failure handlers và audit. Nên dùng filter login chuẩn khi phù hợp.

Save cần xảy ra **trước khi HTTP response commit**, để session/cookie có thể được thiết lập đúng. Nếu bạn gắn một repository trong holder filter nhưng custom login save sang một instance khác, request sau có thể không thấy context.

### 6.3. Authentication filter stateless có thể có repository riêng

Cấu hình `http.securityContext(...securityContextRepository(repo))` tác động đến holder filter và các filter tham gia persistence như form login; một số authentication mechanisms stateless (ví dụ Basic/Bearer) có repository riêng. Không suy rằng chỉ khai báo bean `SecurityContextRepository` thì mọi filter đều lưu session. Phải kiểm tra filter chain theo URL và policy thực tế.

## 7. Chương trình Spring Boot Java 17+ chạy được

Ta viết một Spring Boot MVC app dùng form login **có sẵn** để quan sát session persistence qua nhiều requests. Cặp delegate được cấu hình tường minh dù nó cũng là mặc định trong Spring Security 6.

### 7.1. Tạo project

Trên Spring Initializr chọn Maven, Spring Boot 3.x, Java 17 (hoặc 21), package `com.example.demo` và dependencies **Spring Web**, **Spring Security**. Tương ứng có `spring-boot-starter-web` và `spring-boot-starter-security` trong `pom.xml`.

Tạo file **`src/main/java/com/example/demo/ContextRepositoryApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ContextRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextRepositoryApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain security(
        HttpSecurity http,
        SecurityContextRepository repository
    ) throws Exception {
        return http
            .securityContext(sc -> sc
                .requireExplicitSave(true)
                .securityContextRepository(repository)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "Hello " + authentication.getName();
        }
    }
}
~~~

Code minh họa đúng ranh giới:

- `UserDetailsService` cung cấp tài khoản; password được BCrypt hash lúc khởi tạo demo.
- `formLogin(withDefaults())` bật filter đăng nhập chuẩn; form có CSRF token thích hợp, authentication provider kiểm tra password.
- Composite repository chứa request attribute **trước** session và được gắn vào `HttpSecurity`.
- `SecurityContextHolderFilter` dùng repository để load; filter form login xử lý lưu khi thành công.
- Controller `/me` nhận `Authentication` do Spring Security tạo, không tự làm login.

Không dùng account demo hardcode/password `demo-pass` cho production. Không tắt CSRF chỉ để chạy ví dụ.

### 7.2. Chạy ứng dụng

Trong thư mục có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Thử trên browser, vì browser tự giữ session cookie và form login có CSRF:

1. Mở `http://localhost:8080/public`: nhận body `public`.
2. Mở `http://localhost:8080/me` khi anonymous: được redirect đến trang `/login`.
3. Nhập username **alice**, password **demo-pass**; submit.
4. Truy cập/refresh `/me`: body **`Hello alice`**. Đây là một HTTP request mới, chứng minh đã khôi phục context nhờ session.
5. Mở cửa sổ incognito không chia sẻ cookie: `/me` lại yêu cầu login.
6. Thực hiện logout qua giao diện mặc định, truy cập `/me` lại: không còn authenticated.

Không gửi POST login thiếu CSRF qua curl rồi cho rằng repository hỏng. Và refresh không chứng minh request attribute từ request cũ được gửi sang request mới — **nó không được gửi**.

### 7.3. Timeline minh họa

~~~text
R1 GET /me (anonymous)
  request attribute: không có
  session: chưa có authentication
  -> redirect login

R2 POST /login (form hợp lệ)
  provider xác minh alice
  form login tạo SecurityContext Alice
  saveContext vào request attribute R2 + session
  -> redirect thành công

R3 GET /me (browser có cookie)
  request attribute mới: trống
  session: Alice
  -> load context Alice, controller "Hello alice"

R4 GET /me (browser khác không có cookie phiên đó)
  request attribute: trống
  session authenticated tương ứng: không có
  -> redirect login
~~~

Session có thể đã được tạo phục vụ CSRF token hoặc request cache trước login; điều đó không đồng nghĩa đã xác thực.

## 8. Unit test về cả hai nơi lưu và thứ tự

Browser chứng minh session. Để thấy chính xác **ghi vào cả hai** và **ưu tiên request attribute**, có thể dùng Spring Test mocks, không cần servlet container thật.

Trong `pom.xml` bổ sung:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo file **`src/test/java/com/example/demo/DelegatingRepositoryTest.java`**:

~~~java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

import static org.junit.jupiter.api.Assertions.*;

class DelegatingRepositoryTest {

    private SecurityContext fixture(String username) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            )
        );
        return context;
    }

    @Test
    void saveToBothAndReadFromSessionOnNextRequest() {
        var requestRepo =
            new RequestAttributeSecurityContextRepository();
        var sessionRepo =
            new HttpSessionSecurityContextRepository();

        SecurityContextRepository repo =
            new DelegatingSecurityContextRepository(
                requestRepo, sessionRepo
            );

        var first = new MockHttpServletRequest();
        repo.saveContext(
            fixture("alice"), first,
            new MockHttpServletResponse()
        );

        assertTrue(requestRepo.containsContext(first));
        assertTrue(sessionRepo.containsContext(first));

        MockHttpSession session =
            (MockHttpSession) first.getSession(false);
        assertNotNull(session);

        var second = new MockHttpServletRequest();
        second.setSession(session);

        assertFalse(requestRepo.containsContext(second));
        assertTrue(sessionRepo.containsContext(second));
        assertEquals(
            "alice",
            repo.loadDeferredContext(second)
                .get().getAuthentication().getName()
        );
    }

    @Test
    void requestAttributeOverridesSessionOnlyInThatRequest() {
        var requestRepo =
            new RequestAttributeSecurityContextRepository();
        var sessionRepo =
            new HttpSessionSecurityContextRepository();
        SecurityContextRepository repo =
            new DelegatingSecurityContextRepository(
                requestRepo, sessionRepo
            );

        var first = new MockHttpServletRequest();
        repo.saveContext(
            fixture("alice"), first,
            new MockHttpServletResponse()
        );
        MockHttpSession session =
            (MockHttpSession) first.getSession(false);
        assertNotNull(session);

        var second = new MockHttpServletRequest();
        second.setSession(session);

        // Dữ liệu BOB chỉ được đặt ở request attribute để TEST,
        // KHÔNG phải cách đổi identity trong production.
        requestRepo.saveContext(
            fixture("bob"), second,
            new MockHttpServletResponse()
        );

        assertEquals(
            "bob",
            repo.loadDeferredContext(second)
                .get().getAuthentication().getName()
        );

        var third = new MockHttpServletRequest();
        third.setSession(session);

        assertEquals(
            "alice",
            repo.loadDeferredContext(third)
                .get().getAuthentication().getName()
        );
    }

    @Test
    void emptyContextDoesNotCreateNewHttpSession() {
        SecurityContextRepository repo =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );
        var request = new MockHttpServletRequest();

        repo.saveContext(
            SecurityContextHolder.createEmptyContext(),
            request,
            new MockHttpServletResponse()
        );

        assertNull(request.getSession(false));
    }
}
~~~

**Chú thích bảo mật:** method `fixture(username)` tự tạo authenticated token chỉ dành cho unit test repository. Trong ứng dụng thật, phải dùng authentication provider/manager kiểm tra bằng chứng trước, không tự tạo authenticated token từ input client.

Chạy:

~~~bash
./mvnw test
~~~

Windows: `.\mvnw.cmd test`. Kỳ vọng **ba test thành công**, có thể thấy tóm tắt Maven Surefire tương tự:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
~~~

Test chỉ kiểm tra contract repository: lưu vào cả hai; request mới nạp session; request attribute thắng trong request hiện tại; context rỗng không tạo session. Nó **không thay thế** integration test của `DispatcherType.ERROR` thực, session fixation, CSRF hay distributed session.

## 9. Chọn repository theo kiến trúc

| Thiết kế | Repository phù hợp | Cần kiểm tra |
| --- | --- | --- |
| Form login + session trong Servlet | Delegating(RequestAttribute, HttpSession) | Request mới, session cookie, error dispatch |
| Chỉ cần context trong cùng servlet request | RequestAttributeSecurityContextRepository | Không có persistence qua request mới |
| Chỉ cần session persistence với yêu cầu đặc thù | HttpSessionSecurityContextRepository | Error dispatch, session policy |
| JWT/Bearer stateless | NullSecurityContextRepository hoặc cơ chế stateless phù hợp | Token được xác minh mỗi request |
| Có store custom | Delegating(custom, RequestAttribute, Session) nếu thật sự cần | Thứ tự, stale data, lỗi từng backend, hiệu năng |

### 9.1. API stateless không nên tạo session tùy tiện

Một ứng dụng resource server có thể cấu hình:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(session ->
            session.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS
            )
        )
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

Đây là **fragment**, cần starter OAuth2 resource server, JWT decoder/issuer và imports. Không dán vào app form login phía trên rồi mong session vẫn hoạt động như cũ. Với `STATELESS`, Spring Security không sử dụng HTTP session để lấy context và thường dùng `NullSecurityContextRepository` trong cơ chế tương ứng.

`SessionCreationPolicy.NEVER` khác `STATELESS`: `NEVER` vẫn có thể sử dụng session đã tồn tại; những component khác có thể tạo session như request cache. Cần kiểm tra thực tế thay vì dựa vào tên enum.

### 9.2. Repository custom phải có chính sách xung đột

Nếu có repository từ database/Redis:

- Delegate ưu tiên nhưng stale có thể che dữ liệu mới từ session.
- Ghi vào nhiều backend không có đảm bảo atomic/rollback nếu một backend thất bại.
- Khi logout phải dọn/thu hồi chính xác những nơi đã lưu.
- Session/context có thể cần serialization an toàn.
- Truy cập remote backend trên request path tăng latency và lỗi hệ thống.
- Không lưu raw password, bearer token hoặc quá nhiều dữ liệu cá nhân trong serialized principal.

Không dùng `DelegatingSecurityContextRepository` như cache đồng bộ phân tán hay cơ chế hợp nhất quyền tự động.

## 10. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Login trả thành công nhưng refresh mất login | Chỉ set holder, thiếu save; chỉ dùng request attribute | Dùng composite và save đúng cơ chế |
| ERROR dispatch không thấy principal | Holder clear, không save request attr, thiếu filter mapping | Test RequestAttribute repo và dispatcher type |
| Request thấy Bob, refresh thành Alice | Chỉ thay request attribute, session vẫn Alice | Đảm bảo lưu đúng tất cả delegates |
| Có JSESSIONID nhưng vẫn anonymous | Session không có authenticated context hoặc đã hết hạn | Kiểm tra session content và filter |
| Không có session sau save | Context empty/anonymous, stateless, allowSessionCreation=false | Kiểm tra policy; không tạo session giả |
| Public page đã tạo session | CSRF, request cache hoặc code khác | Truy dấu component tạo session |
| Stateless API xuất hiện session | Trộn session policies/filter chain | Thiết lập và test STATELESS |
| `containsContext` được dùng để cho quyền | Hiểu nhầm API | Dùng authorization rules |
| Logout xong vẫn thấy user | Session/other delegate hoặc token chưa thu hồi | Dùng logout support và token policy |
| Multi-node mất login | Session không chia sẻ giữa node | Dùng backend session thích hợp |
| Async job không thấy principal | Thread khác không được truyền context | Dùng security context propagation |
| Một request có hai security context filters | Trộn HolderFilter với PersistenceFilter | Chỉ dùng một theo cấu hình |

### 10.1. Trình tự debug

1. Kiểm tra authentication có thành công từ manager/provider không.
2. Kiểm tra `SecurityFilterChain` thực sự xử lý URL.
3. Tìm nơi gọi `saveContext(...)` sau authentication và xác định repository instance.
4. Đọc riêng `requestAttributeRepo.containsContext(request)` và `sessionRepo.containsContext(request)` trong test.
5. Kiểm tra session cookie, expiry, session ID và backend/node.
6. Với trang lỗi, kiểm tra `DispatcherType.ERROR` và cấu hình filter registrations.
7. Nếu HTTP `403`, phân biệt thiếu authority với thiếu persistence.
8. Không log raw credentials, session ID nguyên văn hoặc dump `SecurityContext`.

## 11. Bảo mật và vòng đời

**Logout:** `SecurityContextHolder.clearContext()` chỉ xóa dữ liệu của execution hiện tại, **không tự** xóa session hoặc nơi lưu khác. Dùng Spring Security logout support và kiểm thử request mới không còn authentication; xử lý remember-me, refresh token hoặc JWT theo kiến trúc.

**CSRF/session fixation:** Form login dựa session phải bảo vệ request thay đổi trạng thái khỏi CSRF. Session fixation protection là nhiệm vụ session authentication strategy; chỉ lưu context vào HTTP session không thay nó. Với HTTPS, cấu hình cookie `HttpOnly`, `Secure` và `SameSite` phù hợp.

**Thay đổi account:** Một `SecurityContext` đã lưu trong session có thể giữ authorities cũ. Disable account hoặc thay quyền trong DB không mặc định thu hồi session/token. Nếu sản phẩm yêu cầu chặn tức thì, cần policy recheck/revocation riêng.

**Async và ThreadLocal:** Request attribute thuộc servlet request, còn holder thường dựa ThreadLocal. Chuyển thread không có nghĩa principal tự truyền theo. Dùng cơ chế hỗ trợ như `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` hoặc async integration phù hợp, không trông chờ repository request attribute giải quyết mọi thread boundary.

**Consistency:** Delegating gửi save tới các delegates, nhưng không có quorum/transaction phân tán. Nếu session store thất bại còn request attribute thành công, request hiện tại có thể thấy context trong dispatch sau, nhưng request kế tiếp có thể mất login. Phải có monitoring và failure policy rõ ràng.

## 12. Câu hỏi và đáp án

**Câu 1.** Vì sao có hai repository mặc định?

**Đáp án:** request attribute dùng trong cùng request qua các dispatch; session dùng giữa request kế tiếp với cùng phiên.

**Câu 2.** `SecurityContextHolder.setContext(ctx)` đã đủ để login được ghi nhớ qua requests chưa?

**Đáp án:** không với mô hình explicit save của `SecurityContextHolderFilter`. Phải lưu qua repository hoặc dùng authentication filter chuẩn đã xử lý.

**Câu 3.** Request attribute có Bob, session có Alice và thứ tự attr trước session. Load trả ai?

**Đáp án:** Bob trong request đó, nếu attribute có context hiện hữu. Không có phép merge hay so quyền.

**Câu 4.** Request tiếp theo có session Alice nhưng không attribute Bob cũ. Load trả ai?

**Đáp án:** Alice từ session, nếu session hợp lệ.

**Câu 5.** `containsContext(request) == true` có đủ cho `/admin` không?

**Đáp án:** không. Cần authentication và authorization thực sự.

**Câu 6.** Save context rỗng có chắc tạo session?

**Đáp án:** không; session repository chuẩn tránh tạo session vô ích cho empty/anonymous.

**Câu 7.** Tại sao trang lỗi có thể mất principal?

**Đáp án:** holder có thể bị clear trước ERROR dispatch; request attribute cho phép phục hồi nếu đã lưu và filter được áp dụng.

**Câu 8.** API stateless JWT có cần session repo?

**Đáp án:** không; bearer token có thể được xác minh mỗi request, dùng stateless policy.

**Câu 9.** Vì sao token authenticated tự tạo trong unit test không nên dùng để login production?

**Đáp án:** test chỉ tạo fixture. Trong production, tự tạo token này từ username chưa xác minh là bypass authentication.

**Câu 10.** Composite repo có đồng bộ session trên hai server?

**Đáp án:** không. Cần shared session backend hoặc routing/phương án phù hợp.

**Câu 11.** Sau logout chỉ clear holder nhưng session còn Alice, nguy cơ gì?

**Đáp án:** request mới có thể tải Alice lại từ session; phải dọn đúng các nơi lưu/token.

**Câu 12.** `requireExplicitSave(true)` có yêu cầu save sau mọi lần đọc không?

**Đáp án:** không. Cần save khi flow thay đổi context và muốn giữ nó; đọc không đổi thường không cần ghi.

## 13. Checklist triển khai

- [ ] Dùng đúng Servlet stack, phân biệt `SecurityContextRepository` với `SecurityContextHolder`.
- [ ] Hiểu thứ tự load và hành vi save-to-all của Delegating.
- [ ] Dùng request attribute và HTTP session khi cần cả error dispatch và session persistence.
- [ ] Với custom authentication, phải có kết quả đã được manager xác minh và gọi `saveContext` đúng lúc.
- [ ] Không tạo authenticated token từ username client chưa kiểm chứng.
- [ ] Không dùng `containsContext` như authorization check.
- [ ] Đã test request mới cùng session và request không cookie.
- [ ] Đã test error dispatch/filter mappings nếu trang lỗi cần principal.
- [ ] Không trộn `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter` trên cùng chain.
- [ ] Không dùng HTTP session cho API stateless ngoài policy; test `STATELESS` thực tế.
- [ ] Đã test logout, session expiration, session fixation và cookie flags.
- [ ] Với nhiều node hoặc custom store, có quy tắc consistency/failure/serialization rõ ràng.
- [ ] Không lưu raw password/token trong context hoặc log.
- [ ] Có test Spring Security 6 API và phiên bản dependency thật của dự án.

**Kết luận:** `DelegatingSecurityContextRepository` phối hợp các cách lưu `SecurityContext`. Trong Spring Security 6 Servlet, cặp `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository` giúp bảo toàn context qua dispatch của **cùng request** và qua các **request khác** trong một session. Delegating **đọc theo thứ tự**, **lưu qua các delegate**, nhưng không tự authenticate, không phân quyền và không đồng bộ session giữa máy chủ. Với explicit-save của `SecurityContextHolderFilter`, code tự xác thực phải lưu context tường minh nếu muốn duy trì đăng nhập.

## Tài liệu chính thức

- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Migration: Session Management](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security 6.5 — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html)
- [Spring Security 6.5 — RequestAttributeSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html)
- [Spring Security 6.5 — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
