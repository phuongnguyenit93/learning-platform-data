# SecurityContextPersistenceFilter, explicit save và thay đổi hành vi phiên

> **Phạm vi:** Nâng cấp ứng dụng **Spring Security Servlet** từ mô hình thường gặp ở **Spring Security 5.x** sang **Spring Security 6.x / Spring Boot 3.x (Java 17+, Jakarta Servlet)**. Chủ đề chính: `SecurityContextPersistenceFilter`, `SecurityContextHolderFilter`, `SecurityContextRepository`, `requireExplicitSave`, cách lưu `Authentication` vào đúng nơi và tại sao đăng nhập có vẻ thành công trong **request hiện tại** nhưng mất ở **request kế tiếp**. Bài phân biệt session persistence, session creation, session fixation, CSRF, logout, ứng dụng stateful và stateless. Những đoạn Java sử dụng Spring phải được đặt trong ứng dụng có dependencies tương ứng; không phải Java SE chạy đơn lẻ bằng `javac`.

## 1. Hiện tượng thường gặp khi nâng cấp

Một ứng dụng trước đây đăng nhập bằng một bộ lọc/custom controller:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Trên một số cấu hình Spring Security 5, request hiện tại truy cập được thông tin user, request sau cũng thấy user đã đăng nhập. Nhưng khi nâng cấp sang Spring Security 6, request đầu có thể vẫn thành công, trong khi request kế tiếp lại bị yêu cầu login hoặc trả 401/403.

Lý do quan trọng: **đặt `Authentication` vào `SecurityContextHolder` không đồng nghĩa với lưu `SecurityContext` để sử dụng ở request tiếp theo**.

Trước đây, nhiều ứng dụng dựa vào `SecurityContextPersistenceFilter` để tự lưu context thay đổi vào cuối request. Ở mô hình mặc định mới trong Spring Security 6, `SecurityContextHolderFilter` chủ yếu **đọc/nạp context** và **không tự lưu**; code nào chủ động thiết lập authentication phải gọi `SecurityContextRepository.saveContext(...)` khi cần persistence.

**Lưu ý rất quan trọng:** các filter đăng nhập có sẵn của Spring Security thường đã được cập nhật để lưu context đúng cách. Bài này **không** yêu cầu mọi controller sau login tự gọi `saveContext`. Vấn đề chủ yếu nằm ở luồng **custom authentication**, custom filter, các đoạn sửa context thủ công hoặc cấu hình repository/session đặc biệt.

### Ba câu hỏi phải tách riêng

1. **Request hiện tại có authentication chưa?** Kiểm tra `SecurityContextHolder.getContext().getAuthentication()` trong luồng xử lý hiện tại.
2. **Context có được lưu ở repository thích hợp chưa?** Kiểm tra nơi lưu, lệnh `saveContext(...)`, request/response và thời điểm gọi.
3. **Request tiếp theo có mang dữ liệu nhận diện phiên đúng không?** Kiểm tra session cookie, session store, cách filter load repository, network/cluster và `SessionCreationPolicy`.

Chỉ nhìn `authentication.isAuthenticated() == true` trong một request là chưa đủ để chứng minh user sẽ vẫn đăng nhập ở request sau.

## 2. SecurityContext, SecurityContextHolder và Authentication

Spring Security có ba khái niệm nền tảng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Authentication` | Thể hiện principal, authorities, credentials và trạng thái xác thực. |
| `SecurityContext` | Giữ `Authentication` đang gắn với ngữ cảnh thực thi. |
| `SecurityContextHolder` | Cung cấp cách truy cập `SecurityContext` cho code hiện tại (thường qua ThreadLocal trên Servlet request thread). |
| `SecurityContextRepository` | Nạp/lưu `SecurityContext` khi chuyển giữa các request/dispatch theo cấu hình. |

Ví dụ cách **đọc** context trong Java service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    System.out.println(authentication.getName());
}
~~~

Đây là **mảnh Java bên trong một method**, không phải file độc lập có `main()`. Giá trị in ra phụ thuộc request/principal hiện tại; không có một stdout cố định.

Bản thân `SecurityContextHolder` thường lưu context trong thread đang xử lý request. Khi request kết thúc, filter chain sẽ xóa/khôi phục trạng thái thích hợp để tránh rò principal sang request khác chạy trên cùng thread. Vì vậy nếu bạn chỉ làm:

~~~java
SecurityContextHolder.getContext().setAuthentication(authenticated);
~~~

thì bạn mới thay đổi trạng thái **trong ngữ cảnh request hiện tại**. Muốn request tiếp theo biết được người dùng là ai, còn phải có một repository phù hợp và thao tác lưu khi cơ chế persistence không tự làm việc đó.

**Đừng chia sẻ `SecurityContext` qua biến `static` hoặc singleton.** Làm vậy có nguy cơ user A nhìn thấy authentication của user B. Cũng không tự coi `SecurityContextHolder` là một cơ chế lưu đăng nhập liên request.

## 3. SecurityContextPersistenceFilter trước đây làm gì?

Ở mô hình Servlet cũ, `SecurityContextPersistenceFilter` có nhiệm vụ đại ý:

1. Đầu request: lấy `SecurityContext` từ `SecurityContextRepository` và đưa vào `SecurityContextHolder`.
2. Cho các filters/handler phía sau xử lý request.
3. Khi kết thúc, xử lý việc **lưu context thay đổi** theo cơ chế tự động, bao gồm các tình huống response sắp commit tùy wrapper/implementation.
4. Dọn `SecurityContextHolder` để request sau không tái sử dụng thông tin thread trước đó.

Sơ đồ khái niệm:

~~~text
Request N
  -> SecurityContextPersistenceFilter
     -> repository.loadContext(request)
     -> SecurityContextHolder = context đã load
     -> application/authentication filter thay Authentication
     -> repository.saveContext(...) theo cơ chế tự động
     -> clear holder
  -> response

Request N+1
  -> repository.loadContext(...)  # nếu đã lưu được và client mang session đúng
  -> application thấy Authentication trước đó
~~~

**Không phải mọi context đều được lưu vô điều kiện.** `SecurityContextRepository` có các điều kiện riêng về anonymous, session creation, thay đổi context, trạng thái response và cấu hình; đừng mặc định gọi `setAuthentication` sẽ luôn tạo một `HttpSession`. Tự động lưu chỉ hoạt động khi filter/repository/session policy tương thích.

### Vì sao cơ chế tự động khó dự đoán?

Các vấn đề thực tế gồm:

- Ứng dụng redirect/send response trước khi filter kịp lưu; framework phải xử lý cả thời điểm response commit.
- Repository có thể cần tạo session mới vào cuối request; việc thêm cookie khi response đã commit trở nên khó.
- Một request có nhiều dispatch/threads khiến thời điểm context thay đổi và việc lưu không hiển nhiên.
- Custom code có thể thay authentication trong ThreadLocal nhưng người viết không biết liệu nó được persist hay chưa.

Đó là lý do API mới hướng tới việc **code thực hiện authentication phải biết và chủ động lưu context vào repository** khi cần, thay vì dựa vào việc phát hiện thay đổi ở cuối request.

## 4. SecurityContextHolderFilter: thay đổi cốt lõi ở Spring Security 6

`SecurityContextHolderFilter` có vai trò chính là **đọc/chuẩn bị SecurityContext** cho chuỗi xử lý. Nó không mặc định nhận trách nhiệm “tự động lưu mọi thay đổi context vào cuối request” như cách một số luồng `SecurityContextPersistenceFilter` làm trước đây.

Sơ đồ khái niệm khi **require explicit save**:

~~~text
Request N
  -> SecurityContextHolderFilter
     -> repository.loadDeferredContext(request)
     -> SecurityContextHolder có context theo nhu cầu
     -> application/authentication code
          |
          +-- chỉ set SecurityContextHolder
          |      -> có thể dùng trong request N
          |      -> KHÔNG đảm bảo request N+1
          |
          +-- tạo SecurityContext mới
                 -> context.setAuthentication(verifiedAuthentication)
                 -> SecurityContextHolder.setContext(context)
                 -> repository.saveContext(context, request, response)
                        -> persisted theo repository/session policy
     -> clear holder

Request N+1
  -> SecurityContextHolderFilter
     -> repository.loadDeferredContext(request) nếu client có state hợp lệ
     -> Authentication đã lưu có thể được phục hồi
~~~

**“Explicit save” là hành vi cần làm của code thực hiện authentication**, không phải biến `SecurityContextHolder` thành một kho lưu trữ mới. Authentication trong holder và context trong repository là hai lớp trách nhiệm khác nhau.

### Bảng so sánh trước/sau

| Tiêu chí | Cơ chế phổ biến dựa trên `SecurityContextPersistenceFilter` | Cơ chế explicit save dùng `SecurityContextHolderFilter` |
| --- | --- | --- |
| Nạp context | Repository nạp và đưa vào holder đầu request. | Repository cung cấp deferred context, được nạp khi cần. |
| Lưu context thay đổi | Filter có cơ chế tự lưu tại các thời điểm kết thúc/commit phù hợp. | Filter không tự lưu mọi thay đổi; bên thiết lập auth cần lưu khi cần. |
| Custom code chỉ `setAuthentication` | Có thể được lưu tự động nếu filter/repository cho phép. | **Không đủ** để khẳng định request sau vẫn authenticated. |
| Built-in login filters | Framework xử lý authentication và persistence theo cấu hình. | Built-in login filters thường gọi lưu context như một phần thành công login. |
| Stateless API | Repository/session policy quyết định; không nhất thiết tạo session. | Vẫn do repository/session policy quyết định; explicit save không buộc phải là HttpSession. |
| Mục tiêu nâng cấp | Phát hiện code từng ngầm dựa vào auto-save. | Chuyển sang lưu tường minh tại nơi authentication được thiết lập. |

### requireExplicitSave

Trong Spring Security 6 Servlet, cấu hình liên quan là:

~~~java
http.securityContext(context -> context.requireExplicitSave(true));
~~~

Đây là **mảnh cấu hình** bên trong xây dựng `SecurityFilterChain`. Ý nghĩa là sử dụng cơ chế yêu cầu explicit save (thường với `SecurityContextHolderFilter`). Đây là hành vi mặc định trong các cấu hình Spring Security 6 thông dụng, nên không nhất thiết phải khai báo lại chỉ để lặp mặc định.

Trong một số phiên bản Spring Security 6, có thể cấu hình `requireExplicitSave(false)` để trở lại hành vi persistence cũ khi di trú tạm thời:

~~~java
// Phương án tương thích chuyển tiếp, không phải đích nâng cấp:
http.securityContext(context -> context.requireExplicitSave(false));
~~~

**Không dùng nó làm cách sửa vĩnh viễn khi custom authentication chưa đúng.** Kiểm tra chính xác version đang chạy, kiểm thử request lifecycle và chuyển sang code gọi `saveContext` đúng chỗ. Không tự đăng ký đồng thời cả `SecurityContextPersistenceFilter` và `SecurityContextHolderFilter` bằng tay chỉ để “có cả hai”.

## 5. SecurityContextRepository: lưu ở đâu mới quyết định hành vi phiên

Filter không thể tự tạo persistence phù hợp nếu repository đang dùng không cho phép. Các implementation quan trọng trên Servlet stack:

| Repository | Phạm vi/lifecycle | Ghi nhớ khi nâng cấp |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu context vào `HttpSession` khi cần và khi chính sách cho phép. | Dùng cho form login/session-based authentication, để request sau khôi phục từ session. |
| `RequestAttributeSecurityContextRepository` | Lưu vào **request attribute**, giúp thấy lại context trong những dispatch của **cùng request**. | Không thay thế session persistence giữa hai HTTP requests. |
| `DelegatingSecurityContextRepository` | Nạp/lưu qua nhiều repository theo cấu hình (thường request-attribute + session). | Spring Security 6 thường dùng cấu hình này làm mặc định, hỗ trợ cả error dispatch và session. |
| `NullSecurityContextRepository` | Không persist context qua repository. | Phù hợp thiết kế stateless hoặc một số flow xác thực lại mỗi request; save sẽ không tạo login session. |
| Custom repository | Cookie/token/store riêng do dự án triển khai. | Cần tự bảo đảm trust, serialization, rotation, replay và compatibility. |

### HttpSessionSecurityContextRepository

Đây là repository thường liên quan trực tiếp lỗi **“đăng nhập xong request sau mất user”**. Nó lưu context liên request qua `HttpSession`. Tuy nhiên:

- Có thể **không tạo session** nếu không cần hoặc chính sách `allowSessionCreation`/session management ngăn cản.
- Không nên persist một Authentication anonymous như một login hợp lệ.
- Session phải được client giữ bằng cookie đúng hoặc cơ chế session tracking được cấu hình. Không có cookie đúng → request sau không có cùng session → không load lại auth.
- Trong cluster, mọi node nhận cùng session cần có session store/sticky routing phù hợp.
- Không dùng nó để lưu toàn bộ đối tượng domain không Serializable hoặc các credential bí mật tùy tiện; giữ principal/session nhỏ, ổn định và tuân thủ policy.

### RequestAttributeSecurityContextRepository

Repository này giúp bối cảnh **ERROR/FORWARD dispatch** trong cùng một HTTP request vẫn truy cập được context trong tình huống servlet container dọn holder giữa dispatches. Nó **không** làm cho user đăng nhập ở request tiếp theo.

Ví dụ chuỗi:

~~~text
Một HTTP request /api/action
   -> authentication/authorization
   -> controller ném exception
   -> ERROR dispatch sang /error
   -> request attribute có thể giúp giữ SecurityContext trong cùng request

HTTP request mới /api/me
   -> không thể trông chờ request attribute của request trước
~~~

Nếu bạn chỉ dùng `RequestAttributeSecurityContextRepository` và kỳ vọng form login tồn tại qua nhiều requests, bạn đang chọn sai phạm vi lưu trữ.

### DelegatingSecurityContextRepository

Đây là lựa chọn thường thấy trong Spring Security 6 khi cần kết hợp:

~~~java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
~~~

Các imports:

~~~java
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
~~~

Đây là **mảnh Java**. `DelegatingSecurityContextRepository` lưu context thông qua các delegate theo implementation; nó **không tự biến stateless architecture thành stateful** nếu bạn đã cấu hình chính sách khác. Dùng đúng repository **đang được gắn vào SecurityFilterChain**; đừng tạo một instance khác trong controller rồi giả định filter sau đó sẽ đọc cùng nơi.

## 6. Mẫu cấu hình Spring Boot 3 / Spring Security 6 có session persistence

Phần này trình bày một ứng dụng Servlet mẫu có thể chạy trong **Spring Boot project**. Mục tiêu: login form chuẩn của Spring Security, lưu context đúng repository và xác minh bằng request kế tiếp. Các file đặt trong package `com.example.persistence`.

### 6.1 Maven dependencies

Trong `pom.xml` dùng Spring Boot parent/BOM, Java 17+, thêm:

~~~xml
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
~~~

Đây là **mảnh của POM**, không phải POM độc lập. Để Boot quản lý phiên bản tương thích; đừng trộn Spring Security 5 `javax.servlet` classes với Spring Boot 3/Spring Security 6 `jakarta.servlet` classes.

### 6.2 Điểm khởi động

File `src/main/java/com/example/persistence/PersistenceDemoApplication.java`:

~~~java
package com.example.persistence;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PersistenceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PersistenceDemoApplication.class, args);
    }
}
~~~

### 6.3 SecurityContextRepository và SecurityFilterChain dùng cùng bean

File `src/main/java/com/example/persistence/SecurityConfig.java`:

~~~java
package com.example.persistence;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(securityContextRepository))
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

**Tại sao khai báo repository thành một bean?**

1. Để filter chain và bất kỳ custom authentication integration nào cũng có thể **dùng đúng cùng cấu hình repository**, không tự tạo lệch nơi lưu.
2. `DelegatingSecurityContextRepository` lưu cả request attribute và session theo vai trò của các delegates, giúp dễ quan sát request/ERROR dispatch.
3. `requireExplicitSave(true)` nhấn mạnh hành vi Spring Security 6. Các built-in authentication filters sẽ quản lý việc lưu context cho login flow tương ứng; không cần controller `/login` tự gọi save nữa.
4. `/api/me` yêu cầu authenticated. Bất kỳ người chưa login mà gọi URL này đều phải được xử lý qua entry point (form login thường redirect tới `/login`).
5. `anyRequest().denyAll()` giới hạn những routes còn lại trong demo. Production cần thêm endpoints với policy cụ thể; không mở mọi URL chỉ để test qua.
6. **CSRF vẫn được bật.** POST login cần token hợp lệ. Nếu test POST login thiếu token và nhận 403, đó có thể là CSRF, chưa phải bằng chứng authentication manager từ chối password.

Cấu hình minh họa **không** ghi private credentials vào repository. Nó cũng không phải giải pháp cho một stateless JWT resource server vốn cần authentication lại theo Bearer token ở mỗi request.

### 6.4 Demo user

File `src/main/java/com/example/persistence/DemoUsersConfig.java`:

~~~java
package com.example.persistence;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("local-test-password"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Mật khẩu `local-test-password` chỉ dành cho môi trường demo/test, **không dùng production**. Trong ứng dụng thật cần user store/SSO, secret management, account status và login security theo yêu cầu hệ thống.

### 6.5 Controller trả danh tính của request hiện tại

File `src/main/java/com/example/persistence/MeController.java`:

~~~java
package com.example.persistence;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Controller này không tự xác thực người dùng và cũng không lưu session. Request `/api/me` được bảo vệ bởi filter chain; khi đã authenticated, nó đọc `Authentication` mà Spring Security cung cấp.

## 7. Built-in form login đã lưu context: đừng save trùng không cần thiết

Trong cấu hình `formLogin` chuẩn, các authentication components của Spring Security được thiết kế để xử lý authentication success và persistence theo cơ chế của phiên bản hiện tại. Tức là:

~~~text
POST /login (đúng username/password + CSRF)
  -> UsernamePasswordAuthenticationFilter
  -> AuthenticationManager / AuthenticationProvider
  -> SecurityContext được thiết lập
  -> SecurityContextRepository.saveContext(...) theo login integration
  -> response redirect

GET /api/me ở request mới, cùng session cookie
  -> SecurityContextHolderFilter
  -> SecurityContextRepository.loadDeferredContext(...)
  -> Authentication của alice
  -> controller trả "alice"
~~~

Đó là **luồng khái niệm**, không phải trace cố định của mọi ứng dụng. Các filters, entry points và session strategies có thể khác nếu dùng OAuth2 Login, SAML2, remember-me, custom login, multiple chains hoặc các customizations khác.

**Sai lầm phổ biến khi nâng cấp:** thấy `SecurityContextHolderFilter` không auto-save rồi thêm `saveContext` vào mọi controller sau authentication. Điều này vừa không cần thiết đối với built-in login, vừa dễ gây session semantics sai hoặc lưu một authentication không đáng tin. Hãy chỉ thêm explicit save tại **điểm thực sự do code của bạn chịu trách nhiệm thay đổi/persist SecurityContext**.

### Đăng nhập thành công không đồng nghĩa session cookie cũ giữ nguyên

Spring Security thường kích hoạt **session fixation protection** khi login thành công; session ID có thể thay đổi. Browser cần nhận và gửi **session cookie hiện tại** ở request sau. Thay đổi JSESSIONID trong quá trình login có thể là **hành vi bảo mật đúng**.

Một custom filter tự tạo session hoặc session cookie trong lúc redirect có thể gây lệch nếu không phối hợp với `SessionAuthenticationStrategy`. Đừng sửa lỗi mất login bằng cách tắt session fixation protection mà chưa hiểu nguyên nhân.

## 8. Explicit save: cách đúng cho custom authentication đã được xác thực

### 8.1 Anti-pattern chỉ set holder

Đoạn code sau **chưa đủ** dưới `requireExplicitSave(true)`:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(verifiedAuthentication);
~~~

Tên `verifiedAuthentication` trong snippet hàm ý authentication **đã được xác thực bằng một thành phần đáng tin**. Nếu code lấy username/role từ request body/header rồi tự gọi `UsernamePasswordAuthenticationToken.authenticated(...)`, đó là **giả mạo authentication**, không phải login an toàn.

Đoạn trên có thể giúp các components downstream trong **cùng request** thấy authentication. Nhưng request mới thường sẽ không thấy user đã đăng nhập, nếu không ai lưu context vào repository thích hợp.

### 8.2 Explicit save đúng thứ tự

Trong một custom authentication integration đáng tin (ví dụ sau khi `AuthenticationManager.authenticate(...)` đã thành công), cấu trúc nên là:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);

SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Các import cần có:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
~~~

Đây là **mảnh Java nằm trong một filter/handler/service có các biến đã được inject**, không phải chương trình chạy độc lập. Mấu chốt:

1. **Chỉ dùng** `verifiedAuthentication` do provider/trust boundary hợp lệ xác minh. Không đặt authority tùy ý từ client.
2. Tạo context mới với `SecurityContextHolder.createEmptyContext()` thay vì sửa một context object có thể được chia sẻ/tham chiếu ở nơi khác.
3. Gắn authentication vào context mới.
4. Đưa context vào holder để các components trong request hiện tại nhận ra user.
5. **Gọi `saveContext(context, request, response)`** trên repository được gắn vào đúng security chain.
6. Gọi lưu **trước khi response commit**, redirect hoặc hoàn tất xử lý nếu cần Set-Cookie/session tương ứng.

Cách này giúp tách rõ **“đặt context cho request”** và **“lưu context cho request tương lai”**.

### 8.3 Một class hỗ trợ lưu đã-verified Authentication

File `src/main/java/com/example/persistence/VerifiedAuthenticationPersistence.java`:

~~~java
package com.example.persistence;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.stereotype.Component;

@Component
public class VerifiedAuthenticationPersistence {

    private final SecurityContextRepository repository;

    public VerifiedAuthenticationPersistence(
            SecurityContextRepository repository) {
        this.repository = repository;
    }

    public void saveVerified(
            Authentication verifiedAuthentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (verifiedAuthentication == null ||
                !verifiedAuthentication.isAuthenticated()) {
            throw new IllegalArgumentException(
                    "Authentication must already be verified");
        }

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verifiedAuthentication);

        SecurityContextHolder.setContext(context);
        repository.saveContext(context, request, response);
    }
}
~~~

Class này **có thể biên dịch trong dự án Spring Boot đã khai báo bean repository ở phần 6**. Nó chỉ làm nhiệm vụ save context; **không phải một cơ chế login hoàn chỉnh**. `isAuthenticated()` là kiểm tra phòng vệ cơ bản, **không tự chứng minh nguồn authentication đáng tin** vì code bất kỳ cũng có thể tạo token ở trạng thái authenticated. Chỉ gọi method sau khi đi qua quá trình xác thực thật do application tin cậy. Không expose method này trực tiếp như HTTP endpoint cho user tự truyền principal/role.

### 8.4 Những trách nhiệm không có trong class hỗ trợ

Một custom login endpoint/filter production thường cần thêm:

- Xác minh password/credential/token qua `AuthenticationManager` hoặc provider/IdP hợp lệ, không tự tạo verified token.
- **SessionAuthenticationStrategy**: bảo vệ chống session fixation, giới hạn session đồng thời và các hành vi được cấu hình.
- **CSRF lifecycle**: trong ứng dụng dùng session/cookie, sau login/logout token cũ có thể bị xóa; frontend phải lấy token mới.
- Authentication success/failure handlers, redirect allowlist, error policy, audit và tránh credential logging.
- Đồng bộ với `SecurityContextRepository` thực sự gắn vào chain và session creation policy.
- Session logout/invalidation và principal revocation phù hợp.
- Test hai request và cookie từ cùng client.

Vì vậy **ưu tiên built-in authentication filters** (`formLogin`, `httpBasic`, OAuth2 Login, SAML2 Login, Resource Server tùy mô hình) khi đáp ứng yêu cầu. Chỉ viết custom login/filter khi có lý do cụ thể và hiểu đầy đủ các hooks bảo mật.

## 9. Explicit save có nhất thiết tạo HttpSession không?

**Không.** `SecurityContextRepository.saveContext(...)` là API lưu context theo implementation, không phải lệnh “tạo session chắc chắn”.

Một số trường hợp:

- `HttpSessionSecurityContextRepository` có thể tạo/lưu session nếu cần và được phép.
- `RequestAttributeSecurityContextRepository` chỉ giữ context trong request attribute; không tạo persistence qua HTTP requests mới.
- `NullSecurityContextRepository` không persist context, kể cả bạn gọi `saveContext`.
- Với `DelegatingSecurityContextRepository`, kết quả phụ thuộc delegates thực sự được cấu hình.
- `SessionCreationPolicy.STATELESS` thường được dùng để không tạo/dùng HTTP session làm nơi lưu authentication và bảo vệ resource server/token stateless.
- `SessionCreationPolicy.NEVER` tránh Spring Security tự tạo session nhưng có thể dùng session đã tồn tại trong những cơ chế phù hợp; đừng hiểu nó đồng nghĩa STATELESS.
- `SessionCreationPolicy.IF_REQUIRED` cho phép Spring Security tạo session khi cần, nhưng một request anonymous không bắt buộc sẽ tạo session trong mọi cấu hình.

### Bảng định hướng

| Mô hình ứng dụng | Persistence mong muốn | Hướng cấu hình |
| --- | --- | --- |
| Web MVC dùng form login và session cookie | Authentication qua nhiều request trong cùng session. | `HttpSessionSecurityContextRepository` hoặc `DelegatingSecurityContextRepository`, session policy phù hợp. |
| API Bearer JWT stateless | Mỗi request tự xác minh token; không lưu Authentication từ request trước. | Stateless session policy và repository phù hợp, thường `NullSecurityContextRepository`. |
| Error dispatch của cùng HTTP request | Giữ context cho dispatch liên quan. | `RequestAttributeSecurityContextRepository` làm một delegate. |
| Custom SSO login tạo session | Giữ Authentication đã verified ở request kế tiếp. | Explicit save vào repository chung, kèm đầy đủ session/auth strategies. |
| Machine-to-machine Basic auth mỗi request | Xác minh header mỗi request, không nhất thiết session. | Policy/repository tùy threat model; không tự biến thành session login. |

**Lưu ý:** nếu bạn muốn một API stateless, việc request kế tiếp không có Authentication khi thiếu Bearer token là **đúng thiết kế**, không phải bug explicit save. Đừng “sửa” bằng cách mở session cho mọi request bearer.

## 10. Session fixation, invalidation và thay đổi hành vi phiên khi nâng cấp

Nhiều sự cố có cùng biểu hiện “mất login sau request” nhưng nguyên nhân khác nhau.

### 10.1 Session fixation protection

Spring Security có thể đổi session ID sau authentication thành công để chống việc kẻ tấn công cố định một session ID trước login. Trên Servlet hiện đại, `changeSessionId()` thường là phương án có sẵn.

~~~text
Trước login: JSESSIONID = A
POST /login thành công
SessionAuthenticationStrategy / container bảo vệ session fixation
Sau login:  JSESSIONID = B (có thể là cùng logical session với ID đã đổi)
GET /api/me với cookie B -> vẫn authenticated nếu context đã save
GET /api/me với cookie A -> có thể không tìm được session hợp lệ
~~~

Đây là **timeline minh họa**, không phải giá trị cookie thật. Đừng kết luận rằng “Spring Security đổi session ID nên gây lỗi”; đổi ID là lớp bảo vệ đúng. Nếu custom client không tiếp nhận Set-Cookie mới hoặc proxy/Load Balancer làm sai cookie path/domain, request sau sẽ mất session dù repository đã lưu đúng.

**Không tắt session fixation protection chỉ để giữ nguyên JSESSIONID.** Hãy kiểm tra Set-Cookie, cookie jar, domain, path, Secure, SameSite và request tiếp theo.

### 10.2 CSRF token sau login/logout

CSRF và SecurityContext persistence là **hai cơ chế khác nhau**:

- `SecurityContextRepository` giữ Authentication/context theo phạm vi được chọn.
- `CsrfTokenRepository` giữ CSRF token theo repository của CSRF (thường HTTP session hoặc cookie).
- `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` có thể **xóa CSRF token cũ** khi authentication thay đổi/logout, tùy cấu hình thực tế.
- Sau login, một form/SPA giữ token trước login có thể bị 403 dù Authentication đã lưu đúng.

Vì vậy khi test migration phải phân biệt:
1. Request GET sau login bị redirect login → nghi về authentication/session persistence/cookie.
2. GET đã authenticated nhưng POST trả 403 → có thể do CSRF token stale/invalid, hoặc thiếu authority.
3. GET/POST đều đi vào đúng user nhưng hành động bị từ chối → xem authorization/owner/tenant.

Không dùng `csrf.disable()` để che giấu lỗi lưu context. Với session-based browser apps, CSRF protection thường là một lớp thiết yếu.

### 10.3 Concurrent sessions và logout

Các lý do khác khiến context “mất” hợp lệ:

- Session timeout.
- Logout invalidates session và dọn `SecurityContextHolder`.
- Chính sách maximum sessions / concurrent session control từ chối hoặc hết hạn session khác.
- SecurityContext/HTTP session bị hủy do password reset, explicit revocation hoặc session store eviction.
- User B login ở tab khác cùng browser làm principal/session thay đổi.

Không sửa mọi trường hợp bằng cách tạo session mới. Một session bị thu hồi có chủ đích **phải** mất quyền truy cập. Các client nhiều tab cần làm mới giao diện theo authentication hiện tại, không tự chạy thao tác của user A dưới session user B.

## 11. Khi nào save phải xảy ra trước response commit?

Một custom authentication flow có thể trả redirect hoặc response ngay sau khi đặt context:

~~~java
SecurityContextHolder.setContext(context);
response.sendRedirect("/dashboard");
// saveContext() ở đây có thể quá muộn nếu response đã commit.
~~~

Đoạn trên là **anti-pattern**. Nếu implementation cần tạo session hoặc gửi Set-Cookie, response đã commit có thể không còn chỗ cập nhật header.

Thứ tự đúng về mặt ý tưởng:

~~~java
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/dashboard");
~~~

**Chỉ làm khi context chứa Authentication đã verified và session strategies đã xử lý đúng.** Có thể cần kiểm tra response wrappers hoặc handler behavior ở framework version. Không dựa vào một call `saveContext` sau khi đã ghi body/flush buffer/sendError.

### Response commit có những biểu hiện nào?

- `sendRedirect(...)` hoặc `sendError(...)`.
- `flushBuffer()` hoặc flush output stream/writer.
- Body stream đã được đẩy qua network (trong một số server/container).
- Async handling hoặc một filter khác commit response trước khi custom authentication code tới đoạn save.

Nếu người dùng “login thành công” rồi redirect về lại login, hãy kiểm tra response login có lưu context trước commit và session cookie mới có được browser giữ không.

## 12. Multiple SecurityFilterChain: lưu một nơi, đọc một nơi?

Spring Security Servlet cho phép nhiều `SecurityFilterChain` với `securityMatcher` và `@Order`. Khi đó không chỉ cần auth được lưu, mà còn phải biết **filter chain nào đọc request tiếp theo**.

Ví dụ phân vùng:

~~~text
@Order(1): /api/**   -> stateless Bearer JWT (không đọc session context)
@Order(2): /**        -> stateful form login (đọc HttpSession context)
~~~

Nếu login tạo session trong chain web nhưng request tiếp theo vào `/api/**` dùng `NullSecurityContextRepository`, API có thể trả 401 nếu thiếu Bearer token. Đây có thể là thiết kế có chủ đích; `saveContext` ở web chain không tự áp dụng sang stateless chain.

Còn nguy hiểm hơn là **một custom handler ghi vào repository X nhưng chain nhận request tiếp theo lại đọc repository Y**. Lúc đó save thành công về mặt API nhưng user vẫn “mất phiên”.

### Hướng kiểm tra

1. Liệt kê các `SecurityFilterChain` được ứng dụng cấu hình và các URL/methods mà chúng match.
2. Xác định thứ tự `@Order`; filter chain đầu tiên match thường được chọn.
3. Kiểm tra repository nào được chain login và chain request sau dùng.
4. Kiểm tra `SessionCreationPolicy` của mỗi chain.
5. Gửi request thực tế tới cả đường login, dashboard/API và kiểm tra auth/cookie.
6. Không tạo một global repository bean rồi ngầm cho rằng **mọi chain** dùng bean đó; phải kiểm tra cách bean được gắn vào HttpSecurity của từng chain.

### Không dùng request matcher như bộ lưu session

`requestMatchers("/api/**").authenticated()` chỉ quyết định **authorization** trong chain; nó không làm user được lưu sang session. Và `requestMatchers("/login").permitAll()` không khiến custom login tự thực hiện session security strategies. Các phần phải được thiết kế độc lập.

## 13. MockMvc test: xác nhận login thực sự tồn tại qua nhiều request

Một phép thử quan trọng khi nâng cấp là **không dùng `@WithMockUser`** cho kịch bản đang muốn chứng minh authentication persistence. `@WithMockUser` chủ động đặt sẵn Authentication giả, nên có thể làm test xanh dù login filter/repository production không lưu gì.

### 13.1 Bộ test đăng nhập form thật trong Spring context

File `src/test/java/com/example/persistence/LoginPersistenceTest.java`:

~~~java
package com.example.persistence;

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

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistenceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void formLoginPersistsAuthenticationForSecondRequest()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-test-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession savedSession =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(savedSession);

        mvc.perform(get("/api/me").session(savedSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void anonymousSecondRequestCannotUsePrivateEndpoint()
            throws Exception {

        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void invalidPasswordDoesNotCreateAnAuthenticatedSession()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

**Vì sao test này có giá trị?**

- `POST /login` là request thực qua `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `UserDetailsService` và `PasswordEncoder` của demo (không phải `@WithMockUser`).
- `.with(csrf())` bảo đảm request login không bị CSRF chặn trước khi xác thực password.
- Sau login, lấy **session từ request kết thúc** (`getSession(false)`) để mô phỏng request mới cùng session. Điều này quan trọng vì session fixation protection có thể đổi session ID.
- Request thứ hai GET `/api/me` kiểm tra persistence liên request. Nếu chỉ assert redirect login thành công ở request đầu, bạn chưa chứng minh context đã được lưu.
- Test password sai và anonymous riêng giúp phát hiện trường hợp policy vô tình `permitAll` hoặc authentication bị giả lập.
- Nếu app dùng HTTPS/cookies phía proxy, MockMvc không kiểm tra được **browser có giữ Set-Cookie đúng không**. Cần integration test HTTP/browser khi triển khai thật.

**Kỳ vọng:** trong project demo cấu hình đúng, test đầu trả `alice` ở request thứ hai; hai test âm tính không vào `/api/me`. Không bịa stdout Maven cố định. Để chạy, dùng:

~~~bash
mvn test
~~~

Nếu test đầu fail, ghi lại status/headers, Session ID (được che khi log), repository và filter chain. Đừng đổi test thành `@WithMockUser` chỉ để nó pass.

### 13.2 Test đúng repository/bridge, không lẫn với kiểm thử login

Class `VerifiedAuthenticationPersistence` ở phần 8 có thể được unit-test riêng bằng Mockito để kiểm tra nó gọi `saveContext` đúng instance request/response, nhưng test đó **chưa chứng minh** repo thực sự persist qua requests.

Ví dụ test nhỏ **để kiểm tra giao tiếp với repository**, không kiểm tra login thật:

~~~java
@Test
void bridgeCallsRepositorySave() {
    SecurityContextRepository repository =
            Mockito.mock(SecurityContextRepository.class);
    VerifiedAuthenticationPersistence bridge =
            new VerifiedAuthenticationPersistence(repository);

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpServletResponse response = new MockHttpServletResponse();

    Authentication verified =
            UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));

    bridge.saveVerified(verified, request, response);

    Mockito.verify(repository).saveContext(
            Mockito.argThat(ctx ->
                    ctx.getAuthentication() == verified),
            Mockito.same(request), Mockito.same(response));

    SecurityContextHolder.clearContext();
}
~~~

Đây là **test-method snippet** có các imports JUnit, Mockito, Spring Mock Servlet và Spring Security liên quan. `UsernamePasswordAuthenticationToken.authenticated(...)` được dùng **chỉ để tạo test fixture**, không phải bằng chứng user đã xác thực thật. Không triển khai cách dựng auth giả này trong endpoint production.

Để chứng minh persistence đúng, cần thêm test **GET/POST request thứ hai** với repository thật như 13.1 hoặc custom flow integration test thích hợp.

## 14. Vì sao @WithMockUser che khuất lỗi explicit save?

Ví dụ một test:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void meReturnsAlice() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

Test này có thể pass mà **không có bất cứ context nào được lưu trong HttpSession**. `@WithMockUser` tạo Authentication test để request đang chạy thấy “alice”. Vì vậy đừng dùng nó làm bằng chứng cho câu hỏi: **“Sau khi user đăng nhập, GET request tiếp theo có thấy session không?”**

Nó vẫn rất hữu ích để kiểm tra:
- URL/method authorization.
- Quy tắc role/authority.
- Controller/service behavior khi đã có principal.
- CSRF ở request cụ thể khi kết hợp `.with(csrf())` phù hợp.

Nhưng riêng bài nâng cấp session persistence cần test đường **login thật → lưu context → request mới nạp lại**. Nếu dùng custom filter, thêm tests cho flow custom. Test giả principal và test authentication lifecycle phải được báo cáo như hai phạm vi khác nhau.

## 15. Chẩn đoán hành vi mất đăng nhập sau nâng cấp

### Dấu hiệu A: request login thành công nhưng request sau redirect lại /login

Kiểm tra theo thứ tự:

1. Login filter có phải **built-in** hay custom? Custom code có chỉ gọi `SecurityContextHolder.setContext` không?
2. Filter chain đang dùng `SecurityContextHolderFilter`/`requireExplicitSave(true)` không?
3. Repository nào thực sự được cấu hình? Có `HttpSessionSecurityContextRepository` delegate không, hay `NullSecurityContextRepository`?
4. Code custom đã gọi `saveContext(context, request, response)` **trước response commit** chưa?
5. Repository có được dùng lại để **load** request thứ hai không?
6. Response có Set-Cookie/JSESSIONID phù hợp, browser có gửi cookie hiện tại ở request kế không?
7. Session có bị invalidated ngay sau login vì logout/concurrency/security policy không?
8. Nếu qua load balancer, các node có cùng session store/sticky routing không?

### Dấu hiệu B: controller thấy Authentication nhưng session không có dữ liệu mong đợi

Có thể là:
- Authentication được đặt trong holder, nhưng chưa save.
- Repository chỉ lưu request attribute.
- Session policy không cho phép tạo session.
- Custom code lưu vào một repository khác với filter chain.
- Response đã commit trước khi có thể lưu cookie/session.
- Session attribute có thể đã được lưu nhưng bạn đang nhìn **khác session**, khác node hoặc khác namespace.

**Không nên kết luận** chỉ từ một giá trị trong session map nếu app dùng repository riêng. Điều cần test là **behavior thực tế ở request tiếp theo**, không chỉ tên attribute cụ thể.

### Dấu hiệu C: login xong GET được, POST nhận 403

Cần phân biệt:
- Authentication có thể đã persist đúng, nhưng **CSRF token cũ** không còn hợp lệ sau login/logout.
- User authenticated nhưng thiếu quyền cho POST.
- Cookie/session/authority bị thay giữa GET và POST.
- Nhiều filter chains áp dụng khác nhau theo URL/method.

Để kiểm tra quyền POST, phải gửi CSRF token hợp lệ nếu CSRF được bật. Đừng “sửa persistence” bằng cách tắt CsrfFilter.

### Dấu hiệu D: hành vi khác giữa server thật và MockMvc

MockMvc thường không khởi động TCP/TLS và không mô phỏng đầy đủ cookie browser/proxy, dù Spring Security filters vẫn chạy trong context. Các nguyên nhân ngoài MockMvc gồm:

- Cookie `Secure` chỉ gửi trên HTTPS.
- `SameSite` và cross-site redirect/post.
- Reverse proxy đổi scheme/host/context path.
- Session replication/sticky sessions giữa nhiều nodes.
- Timeout/eviction của session store.
- HTTP client giữ cookie cũ sau login/session ID rotation.

Cần browser/server integration test phù hợp, không tắt filters trong MockMvc để kết quả giống điều mong muốn.

## 16. Logging an toàn khi debug SecurityContext

Trong môi trường dev/test, có thể bật log để quan sát Spring Security filter chain:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.context=TRACE
~~~

TRACE chỉ dùng có kiểm soát; tuyệt đối không đưa raw session IDs, credentials, Authorization header, cookies, JWT/SAML assertion hoặc dữ liệu user nhạy cảm vào logs/ticket công khai. Có thể kiểm tra request ID, path, status, chain selected, authentication **loại nào** và có repository.saveContext call không mà không ghi secrets.

### Có thể quan sát từ đâu?

- `FilterChainProxy` và security filters trong context.
- Logger của `SecurityContextHolderFilter`/`SecurityContextPersistenceFilter` tùy cấu hình.
- Các phương thức `SecurityContextRepository.load...` và `saveContext` bằng mock/spy trong test, hoặc instrumentation được bảo vệ.
- Session creation và session ID rotation qua test (không công bố raw ID).
- Browser DevTools: cookie path/domain/Secure/SameSite và request headers (chỉ quan sát cục bộ, không gửi secrets lên ticket).
- Logs của Spring Session/session store nếu dùng Redis/JDBC, không dump toàn bộ session.

**Đừng dựa chỉ vào tên filter trong một log dòng đơn.** Hãy xem chain nào match request và repository nào được gọi. Một app có nhiều chains hoặc thay cấu hình test/prod có thể cho kết quả khác.

## 17. Bảng lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/khắc phục |
| --- | --- | --- |
| Login custom thành công trong request đầu, request sau 302 /login | Chỉ set holder, thiếu explicit save dưới `SecurityContextHolderFilter`. | Lưu context vào đúng repository trước response commit, test request thứ hai. |
| Login form mặc định mất phiên | Cookie/session store/repository/chain cấu hình sai; không tự giả định built-in filter thiếu save. | Kiểm tra Set-Cookie, session ID, repositories, chain matching và timeout. |
| SecurityContext chỉ tồn tại trong ERROR dispatch | Dùng request-attribute repository mà không có HttpSession persistence. | Chọn repository phù hợp với nhu cầu nhiều requests. |
| `saveContext` được gọi nhưng request sau vẫn 401 | `NullSecurityContextRepository`, stateless chain, session không tồn tại hoặc chain sau đọc repo khác. | Kiểm tra implementation, SessionCreationPolicy, request cookies, multiple chains. |
| Save sau redirect không tạo session cookie | Response đã commit nên không cập nhật được session/header như kỳ vọng. | Lưu context trước redirect/write response. |
| Sau login session ID đổi | Session fixation protection hoạt động; client không dùng cookie mới. | Giữ bảo vệ fixation, sửa cookie handling/proxy/client. |
| Đọc context bằng static biến thấy nhầm user | Lưu SecurityContext ngoài holder/repository theo kiểu shared mutable state. | Loại static/shared auth state, dùng security context và trusted repository đúng cách. |
| POST sau login 403 nhưng GET authenticated | CSRF token bị xóa/đổi, hoặc thiếu authority. | Chẩn đoán CSRF và authorization riêng, lấy token mới. |
| Session cứ được tạo dù “stateless” | Một thành phần khác tạo session (request cache, app code, container), hoặc policy chưa áp dụng đúng chain. | Kiểm tra các nguồn tạo session; không chỉ nhìn securityContext().requireExplicitSave(). |
| API JWT bị mất Authentication khi không có token mới | Resource server stateless hoạt động đúng theo thiết kế. | Gửi Bearer token mỗi request; không tự mở HttpSession để “giữ login”. |
| Test `@WithMockUser` pass, app thật mất login | Test gắn auth giả, bỏ qua login/persistence. | Test form/custom login thật và request sau cùng session. |
| Cùng session nhưng qua node khác mất auth | Session store không shared/sticky routing, serialization/replication lỗi. | Kiểm tra Spring Session/cluster topology và failover test. |
| Logout xong user vẫn authenticated trong test | Test tái dùng mock Authentication hoặc không đi qua logout filter. | Kiểm tra logout thực, session invalidation, test không dùng fake context khi cần chứng minh logout. |
| Sau nâng cấp gặp `javax.servlet` / `jakarta.servlet` mismatch | Boot 3/Security 6 chuyển sang Jakarta API. | Dùng imports `jakarta.servlet.*` và dependency versions tương thích. |

## 18. Chiến lược nâng cấp từng bước

### Bước 1 — Kiểm kê nơi ghi Authentication

Tìm **trong code của chính ứng dụng** các chỗ sử dụng:

~~~text
SecurityContextHolder.setContext(...)
SecurityContextHolder.getContext().setAuthentication(...)
new UsernamePasswordAuthenticationToken(...)
custom OncePerRequestFilter / authentication filter
custom login controller / trusted SSO bridge
SecurityContextRepository.saveContext(...)
securityContext().requireExplicitSave(...)
SessionCreationPolicy.STATELESS / NEVER / IF_REQUIRED
~~~

Không phải mọi kết quả đều là bug. Mục tiêu là phân biệt nơi **đặt Authentication cho request hiện tại** với nơi cần **persist cho request tiếp theo**.

### Bước 2 — Chốt trust và persistence model cho từng chain

Với mỗi loại request, ghi rõ:
- Ai xác thực user/token?
- Authentication cần tồn tại **trong một request** hay **qua nhiều requests**?
- Repository nào được load/save?
- Có session cookie không? Chính sách session creation thế nào?
- Filter chain nào áp dụng? Có Bearer stateless hoặc form-login stateful cùng app không?
- Session invalidation, timeout, logout, CSRF, fixation được xử lý ở đâu?

Chỉ sau khi có bảng này mới quyết định thêm explicit save hay thay repository.

### Bước 3 — Chuyển custom auth sang explicit save

Với code tự tạo verified Authentication:
1. Đảm bảo authentication do provider/trusted upstream tạo ra và đã được xác minh.
2. Tạo **SecurityContext mới**.
3. Đặt context vào `SecurityContextHolder`.
4. **Gọi `SecurityContextRepository.saveContext(context, request, response)`** đúng instance repository và trước response commit.
5. Xử lý session strategies, CSRF lifecycle và success/failure handlers theo mô hình authentication.
6. Không double-save theo thói quen nếu filter framework đã quản lý persistence.

### Bước 4 — Thêm test cho request thứ hai

Test **đúng**:
- Login thật/custom authentication thành công.
- Request tiếp theo với **cùng session/client** đã authenticated.
- Request khác session/không credential bị từ chối.
- Sai password hoặc authentication failure không tạo session authenticated.
- Logout/timeout làm access bị thu hồi theo policy.
- CSRF và quyền sau login không bị lẫn với lỗi persistence.

### Bước 5 — Test session lifecycle và triển khai thật

Kiểm tra:
- Set-Cookie sau login, changeSessionId behavior.
- Browser giữ cookie trên redirect/cross-site requests đúng.
- Session store/cluster/replication khi failover.
- Multiple filter chains và endpoint routes mới.
- Tests chạy trong profile/config giống production.
- SecurityContextRepository và các custom integrations dùng cùng hợp đồng load/save.

### Bước 6 — Chỉ dùng chế độ compatibility khi thật sự cần

Nếu phiên bản/framework cho phép `requireExplicitSave(false)`, có thể dùng **ngắn hạn** để khoanh vùng regression, không coi nó là giải pháp cuối. Kế hoạch nâng cấp phải xác nhận custom code đã explicit save và xóa phụ thuộc auto-save trước khi đổi hẳn.

## 19. Những anti-pattern phải tránh

- **Chỉ gọi `SecurityContextHolder.getContext().setAuthentication(...)`** trong custom login rồi tin rằng user đã được persist liên request.
- **Tự tạo authenticated token từ username/role do client gửi** và lưu vào session: đây là lỗi đặc quyền nghiêm trọng, không phải xử lý persistence.
- **Dùng `SecurityContextPersistenceFilter` và `SecurityContextHolderFilter` cùng lúc bằng cách register tay**, không hiểu FilterChainProxy và default config.
- **Gọi `saveContext` vào repository khác** với nơi next request load.
- **Dùng `RequestAttributeSecurityContextRepository` để mong user vẫn login ở HTTP request mới**.
- **Dùng `NullSecurityContextRepository` rồi kỳ vọng form-login stateful**.
- **Save sau sendRedirect/flush** rồi không kiểm tra response commit/cookie.
- **Tắt session fixation hoặc CSRF** chỉ để POST/redirect không còn lỗi.
- **Dùng `@WithMockUser` để chứng minh persistence**.
- **Dùng một user session global/static** khiến requests khác principal hoặc rò quyền chéo.
- **Cho mọi chain cùng một cơ chế session** dù API Bearer stateless cần tự xác thực mỗi request.
- **Đọc session ID hoặc raw SecurityContext vào logs** rồi lưu không kiểm soát.

## 20. Tự kiểm tra kiến thức

**Câu 1.** Với `SecurityContextHolderFilter` và `requireExplicitSave(true)`, gọi `SecurityContextHolder.setContext(ctx)` trong custom filter có đủ để request sau authenticated không?

**Trả lời:** **Không.** Khi muốn persistent login, custom code còn phải dùng `SecurityContextRepository.saveContext(ctx, request, response)` trên repository phù hợp, đúng lifecycle/session policy. Đặt holder chỉ ảnh hưởng request đang xử lý.

**Câu 2.** Vì sao `RequestAttributeSecurityContextRepository` không giải quyết được đăng nhập qua nhiều HTTP requests?

**Trả lời:** Vì request attributes chỉ có hiệu lực trong phạm vi request/dispatch liên quan; request HTTP mới không có cùng request object. Với form login stateful thường cần repository dựa trên HttpSession.

**Câu 3.** Một built-in form login của Spring Security 6 có cần controller gọi saveContext thủ công sau redirect không?

**Trả lời:** Thường **không**. Built-in authentication filters quản lý lưu context trong flow thành công theo cấu hình. Nếu mất login, trước hết kiểm tra session/cookies/repository/chain/customizations; không thêm double-save bừa.

**Câu 4.** Cùng một SecurityFilterChain, request login trả 302 nhưng GET protected tiếp theo cũng 302 về /login. Những nguyên nhân chính?

**Trả lời:** Context chưa save (đặc biệt custom auth), repository không lưu qua session, save quá muộn, client không mang session cookie mới, session bị invalidated, hoặc request tiếp theo vào chain/repo khác. Cần kiểm tra request thứ hai với cùng session.

**Câu 5.** Với `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository`, việc `saveContext` không giữ Authentication qua request có phải bug?

**Trả lời:** Không nhất thiết. Với stateless API, client gửi credential/token **mỗi request** và server xác minh lại. Không lưu session là đúng theo kiến trúc được chọn.

**Câu 6.** GET /api/me sau login thấy user alice, nhưng POST /api/save nhận 403. Có chắc persistence lỗi?

**Trả lời:** Không. Context đã có thể được phục hồi đúng; POST còn chịu CSRF và authorization. Hãy xác định `CsrfFilter` hoặc policy nào từ chối, cấp token CSRF mới sau login nếu cần và kiểm tra quyền tương ứng.

## 21. Tổng kết

Nâng cấp từ cách dùng `SecurityContextPersistenceFilter` sang mô hình `SecurityContextHolderFilter` / **explicit save** thay đổi trách nhiệm quan trọng: **code tự thiết lập Authentication và muốn duy trì nó qua requests phải lưu SecurityContext vào SecurityContextRepository phù hợp**. Nhưng **không phải mọi Authentication cần được lưu** — với API stateless, việc xác thực lại ở mỗi request là đúng thiết kế.

Trong hệ thống Servlet stateful, xem xét đồng thời **holder → repository → session → cookie → filter chain của request kế tiếp**. Built-in login filters thường đã xử lý lưu context; custom authentication cần được rà soát và test kỹ. Session fixation, CSRF, timeout, logout và multi-chain có thể tạo triệu chứng giống “mất login”, nhưng phải chẩn đoán theo đúng cơ chế.

**Quy tắc nhớ nhanh:** *`SecurityContextHolder` cho biết user của **request hiện tại**; `SecurityContextRepository.saveContext(...)` là bước cần thiết khi **custom authenticated context phải tồn tại qua request tiếp theo** dưới mô hình explicit save. Chỉ gọi save trên repository thực sự được dùng để load, trước response commit, và không bypass authentication/session safeguards.*

## Tài liệu tham khảo

- Spring Security Reference — Authentication Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security Reference — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security Reference — Migrating to Spring Security 6 (Servlet session management): https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security Reference — Servlet Architecture and FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Testing Spring MVC with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
