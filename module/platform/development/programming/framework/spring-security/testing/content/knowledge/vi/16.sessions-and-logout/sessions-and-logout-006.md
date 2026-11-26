# Chính sách tạo phiên trong ứng dụng stateful hoặc stateless

## 1. Vì sao phải chọn chính sách tạo phiên?

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, một quyết định quan trọng khi cấu hình Spring Security là ứng dụng có cần duy trì trạng thái đăng nhập qua nhiều request hay không. Ứng dụng web truyền thống thường dùng HTTP session để giữ trạng thái đăng nhập. Ngược lại, API stateless thường xác thực độc lập từng request bằng bearer token hoặc credentials gửi kèm.

**SessionCreationPolicy** quy định Spring Security có tạo HTTP session và có sử dụng session để lấy SecurityContext hay không. Lựa chọn sai có thể làm ứng dụng tạo session ngoài ý muốn, không tiếp nối được đăng nhập, hoặc khiến API phụ thuộc trạng thái phiên trong khi kiến trúc yêu cầu stateless.

Sau bài này, bạn có thể:

- Phân biệt bốn chính sách **ALWAYS**, **IF_REQUIRED**, **NEVER** và **STATELESS**.
- Giải thích sự khác nhau giữa **NEVER** và **STATELESS**.
- Cấu hình stateful form login và stateless resource server.
- Kiểm chứng việc tạo và tái sử dụng session bằng **MockMvc**.
- Dùng **spring-security-test** để kiểm thử endpoint stateless với JWT giả lập.
- Tổ chức ứng dụng có cả web stateful và API stateless bằng nhiều SecurityFilterChain.
- Nhận biết cách tiếp cận tương ứng của ứng dụng Reactive với WebSession và SecurityContextRepository.

## 2. Stateful và stateless là hai cách duy trì trạng thái xác thực

### Stateful: server giữ trạng thái đăng nhập

Trong mô hình stateful, server lưu thông tin xác thực sau khi người dùng đăng nhập. Với ứng dụng Servlet, thông tin đó thường nằm trong **SecurityContext** được lưu vào **HttpSession** thông qua **SecurityContextRepository**.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    participant H as HttpSession
    B->>S: POST /login + credentials
    S->>S: Xác thực người dùng
    S->>H: Lưu SecurityContext
    S-->>B: Redirect + session cookie
    B->>S: GET /profile + cookie
    S->>H: Nạp SecurityContext
    H-->>S: Authentication
    S-->>B: 200 OK
~~~

Trình duyệt gửi cookie session ở request sau. Server tra cứu session, nạp Authentication và áp dụng quy tắc phân quyền. Người dùng không phải gửi lại mật khẩu trong mỗi request.

Mô hình này thường phù hợp với ứng dụng web có form login, trang cá nhân, giỏ hàng và các thao tác tương tác dựa trên session.

### Stateless: mỗi request tự mang thông tin xác thực

Trong mô hình stateless, server không dựa vào HTTP session để khôi phục Authentication cho request tiếp theo. Client gửi bearer token, JWT hoặc credentials theo cơ chế được cấu hình ở từng request.

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant S as Spring Security
    participant R as Resource Server
    C->>S: GET /api/orders + Bearer token
    S->>S: Xác minh token và tạo Authentication
    S->>R: Chuyển request đã xác thực
    R-->>C: 200 OK
    C->>S: GET /api/orders + Bearer token
    S->>S: Xác minh token cho request mới
    S->>R: Chuyển request đã xác thực
    R-->>C: 200 OK
~~~

Mỗi request được xác thực độc lập. Việc request trước đã thành công không khiến request sau tự động được xác thực nếu request sau thiếu token.

**Stateless không có nghĩa ứng dụng không được phép dùng session cho bất kỳ mục đích nào.** Chính sách STATELESS nói về cách Spring Security quản lý SecurityContext: không tạo session để lưu ngữ cảnh và không dùng session để lấy ngữ cảnh xác thực. Code ứng dụng, thư viện khác hoặc servlet container vẫn có thể tạo session nếu chúng được lập trình để làm vậy. Nếu yêu cầu là API tuyệt đối không phát sinh session, cần kiểm thử cả hành vi của ứng dụng và hạ tầng liên quan.

## 3. Bốn giá trị SessionCreationPolicy

Spring Security cung cấp enum **SessionCreationPolicy** với bốn chính sách thường dùng:

| Chính sách | Spring Security tạo session? | Có dùng session sẵn có để lấy SecurityContext? | Tình huống thường gặp |
| --- | --- | --- | --- |
| **ALWAYS** | Có, luôn tạo | Có | Ứng dụng chủ động yêu cầu mọi request có session |
| **IF_REQUIRED** | Chỉ khi cần | Có | Web app stateful, lựa chọn phổ biến |
| **NEVER** | Không tự tạo | Có | Không muốn Security tự tạo session nhưng vẫn chấp nhận session do thành phần khác tạo |
| **STATELESS** | Không tạo để lưu SecurityContext | Không | API xác thực độc lập bằng token |

Trong cấu hình Servlet, chọn một giá trị tại `sessionCreationPolicy(...)`:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.ALWAYS)
)

// Các lựa chọn thay thế:
// SessionCreationPolicy.IF_REQUIRED
// SessionCreationPolicy.NEVER
// SessionCreationPolicy.STATELESS
~~~

### 3.1. ALWAYS

Spring Security luôn tạo HTTP session, kể cả khi request hiện tại chưa cần lưu SecurityContext. Điều này có thể hữu ích với ứng dụng được thiết kế xoay quanh session, nhưng cũng làm tăng số session phía server và tài nguyên quản lý.

Nếu phần lớn request chỉ đọc dữ liệu công khai, ALWAYS có thể tạo nhiều session không cần thiết. Hãy xác nhận ứng dụng thực sự cần hành vi đó trước khi chọn.

### 3.2. IF_REQUIRED

Spring Security chỉ tạo session khi một thành phần cần lưu dữ liệu vào đó. Đây là lựa chọn phù hợp với nhiều ứng dụng web stateful: trang công khai có thể không cần session, còn form login hoặc request cache có thể cần session.

Không nên hiểu IF_REQUIRED là “chỉ tạo session sau đăng nhập”. CSRF token, request cache, ứng dụng hoặc thư viện khác cũng có thể là lý do tạo session, tùy cấu hình.

### 3.3. NEVER

Spring Security không tự tạo session, nhưng **vẫn sử dụng session đã tồn tại** để đọc hoặc lưu SecurityContext khi cần. Vì thế, nếu một thành phần khác đã tạo session và lưu dữ liệu xác thực ở đó, Spring Security vẫn có thể sử dụng session ấy.

NEVER phù hợp khi ứng dụng muốn hạn chế việc Spring Security tạo session nhưng vẫn phải tương thích với session do tầng ứng dụng tạo. Nó không tương đương STATELESS.

### 3.4. STATELESS

Spring Security không tạo session để lưu SecurityContext và không đọc SecurityContext từ session có sẵn. Đây là lựa chọn cho API stateless, chẳng hạn resource server nhận bearer token.

Trong cấu hình stateless, request cache mặc định cũng được xử lý theo hướng không dùng HTTP session. Tuy vậy, nếu ứng dụng tự tạo session ở controller hoặc filter khác, chính sách này không tự ngăn code ứng dụng làm điều đó.

### Phân biệt NEVER và STATELESS

Đây là điểm thường gây nhầm:

- **NEVER:** Spring Security không tạo session mới, nhưng nếu request có session thì vẫn có thể đọc SecurityContext từ session.
- **STATELESS:** Spring Security không dùng session để lưu hoặc nạp SecurityContext, kể cả khi request mang một session có sẵn.

Nếu hệ thống yêu cầu mỗi request phải xác thực độc lập bằng token, hãy dùng STATELESS. Nếu chỉ muốn Spring Security không chủ động tạo session nhưng vẫn chấp nhận trạng thái phiên đã được tạo bởi thành phần khác, hãy xem xét NEVER.

## 4. Cấu hình stateful cho ứng dụng web

Ví dụ sử dụng Spring Boot 3.x, Spring Security 6.x, Spring MVC và form login. Ứng dụng có người dùng alice và endpoint profile cần xác thực.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/profile").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Controller mẫu:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class WebController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Trong cấu hình này, **IF_REQUIRED** cho phép ứng dụng duy trì đăng nhập qua session. Form login mặc định xử lý POST /login và lưu SecurityContext theo repository được cấu hình. Request sau có cùng session có thể truy cập /profile.

Nếu chuyển sang **ALWAYS**, chỉ cần thay giá trị policy. Với **NEVER**, Spring Security không chủ động tạo session; tuy nhiên session có sẵn vẫn có thể được dùng. Với **STATELESS**, cần cân nhắc cả cơ chế xác thực: form login dựa trên session thường không còn là lựa chọn phù hợp cho hành trình đăng nhập nhiều request.

## 5. Kiểm thử stateful bằng MockMvc

Mục tiêu là xác minh request công khai không nhất thiết tạo session, nhưng sau khi đăng nhập thành công, session chứa SecurityContext và có thể được dùng để gọi request tiếp theo.

Ví dụ test dưới đây chạy với cấu hình IF_REQUIRED ở mục 4:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class StatefulSessionPolicyTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicRequestDoesNotNeedSession() throws Exception {
        MvcResult result = mockMvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"))
                .andReturn();

        assertThat(result.getRequest().getSession(false)).isNull();
    }

    @Test
    void loginCreatesContextThatCanBeUsedOnNextRequest()
            throws Exception {
        MvcResult login = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(saved).isInstanceOf(SecurityContext.class);
        assertThat(((SecurityContext) saved).getAuthentication().getName())
                .isEqualTo("alice");

        mockMvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

Hai test này minh họa hành vi của cấu hình mẫu. Test đầu giả định endpoint /public và các thành phần liên quan không tự tạo session. Test thứ hai chứng minh form login đã lưu SecurityContext và request sau sử dụng đúng session.

**MockMvc không tự giữ cookie giữa các lần perform.** Vì vậy phải lấy MockHttpSession từ request login rồi truyền bằng .session(session). Nếu không truyền session, request mới là một request độc lập và thường không nhận được danh tính đã đăng nhập.

### Kiểm tra ALWAYS

Với policy ALWAYS, có thể kiểm tra một request công khai đã tạo session:

~~~java
MvcResult result = mockMvc.perform(get("/public"))
        .andExpect(status().isOk())
        .andReturn();

assertThat(result.getRequest().getSession(false)).isNotNull();
~~~

Assertion này chỉ phù hợp khi endpoint không bị chặn trước filter chain và không có cấu hình khác thay đổi cách quản lý session. Nó giúp nhận diện việc Spring Security chủ động tạo session ngay cả khi endpoint không yêu cầu Authentication.

### Kiểm tra NEVER

Với NEVER, request công khai không có session đầu vào không nên khiến Spring Security tự tạo session nếu không có thành phần nào khác cần session:

~~~java
MvcResult result = mockMvc.perform(get("/public"))
        .andExpect(status().isOk())
        .andReturn();

assertThat(result.getRequest().getSession(false)).isNull();
~~~

Để kiểm tra vế “vẫn dùng session có sẵn”, có thể chuẩn bị một session chứa SecurityContext hợp lệ rồi gửi nó vào request. Ví dụ:

~~~java
import java.util.List;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

MockHttpSession existing = new MockHttpSession();

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
    UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "N/A",
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    )
);

existing.setAttribute(
    HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
    context
);

mockMvc.perform(get("/profile").session(existing))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
~~~

Đây là cách kiểm tra khả năng đọc session sẵn có, không phải kiểm thử quy trình đăng nhập. Authentication được chuẩn bị trực tiếp trong test nên không xác minh mật khẩu hay filter xử lý form login.

## 6. Cấu hình stateless cho REST API

Với API sử dụng JWT bearer token, mỗi request phải mang token. Ví dụ sau cấu hình một resource server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Resource server cần cấu hình nguồn xác minh JWT, chẳng hạn issuer URI hoặc JWK Set URI, trong cấu hình ứng dụng. Ví dụ trên tập trung vào chính sách session; nó không tự cung cấp khóa ký hoặc cấu hình decoder.

Endpoint API:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    String orders(Authentication authentication) {
        return "orders for " + authentication.getName();
    }
}
~~~

Trong cấu hình này:

- **STATELESS** chỉ rõ Spring Security không duy trì SecurityContext qua HttpSession.
- **NullSecurityContextRepository** không lưu hoặc tải SecurityContext từ session.
- **NullRequestCache** tránh lưu request cần xác thực vào HTTP session để chuyển hướng sau đăng nhập.
- **oauth2ResourceServer().jwt()** xác thực bearer JWT trên từng request.

Với bearer token trong Authorization header, việc client gửi token ở từng request là trách nhiệm của client. Nếu request thiếu token hoặc token không hợp lệ, API phải từ chối theo entry point và access denied handler đã cấu hình.

### 6.1. Kiểm thử API stateless bằng MockMvc và jwt()

Spring Security Test cung cấp request post-processor **jwt()** để gắn một JwtAuthenticationToken giả lập vào request. Cần dependency **spring-security-test** và các phụ thuộc resource server phù hợp.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class StatelessApiSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void jwtRequestIsAuthenticatedWithoutCreatingHttpSession()
            throws Exception {
        MvcResult result = mockMvc.perform(get("/api/orders")
                    .with(jwt().jwt(token -> token.subject("alice"))))
                .andExpect(status().isOk())
                .andExpect(content().string("orders for alice"))
                .andReturn();

        assertThat(result.getRequest().getSession(false)).isNull();
    }

    @Test
    void requestWithoutJwtIsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**jwt() tạo Authentication giả lập cho test**, giúp kiểm tra quy tắc authorization và luồng xử lý của ứng dụng sau khi có principal. Nó không kiểm tra chữ ký JWT thật, thời hạn token, issuer, audience hay kết nối JWK. Muốn kiểm chứng decoder và việc xác minh token, cần thêm test với token thực phù hợp hoặc test tích hợp resource server.

Assertion không có session trong test giả định endpoint và các filter liên quan không tự gọi getSession() để tạo session. Nếu code ứng dụng tạo session độc lập, test sẽ phát hiện điều đó; cần xác định thành phần nào tạo session thay vì cho rằng STATELESS cấm mọi code tạo session.

## 7. Ứng dụng kết hợp web stateful và API stateless

Nhiều sản phẩm có cả trang web dùng form login và API cho mobile hoặc service-to-service. Không nhất thiết ép toàn bộ ứng dụng theo một chính sách. Có thể định tuyến request đến các SecurityFilterChain riêng bằng **securityMatcher** và thứ tự **@Order**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );

        return http.build();
    }
}
~~~

**Thứ tự chain rất quan trọng.** Chain API được xét trước và chỉ khớp /api/**. Các request còn lại đi vào chain web. Nếu không có chain phù hợp hoặc matcher được khai báo sai, request có thể nhận cấu hình bảo mật ngoài dự kiến. Hãy kiểm thử riêng endpoint trong từng vùng.

Một bộ test cho ứng dụng hỗn hợp nên xác minh:

- Trang web có thể đăng nhập bằng form và tiếp tục truy cập với cùng session.
- API chấp nhận JWT hợp lệ ở từng request.
- API không nhận Authentication chỉ vì client có session cookie của trang web.
- Request không có credentials bị từ chối ở cả hai vùng theo entry point tương ứng.
- CSRF và cookie được cấu hình theo cách xác thực thực tế của từng vùng.

### Lưu ý về CSRF

Không nên tắt CSRF chỉ vì đã đặt STATELESS. Rủi ro CSRF phụ thuộc cách client gửi credentials. Bearer token được JavaScript chủ động đặt trong Authorization header có đặc tính khác với cookie tự động được trình duyệt gửi. Nếu API dùng cookie để mang thông tin xác thực, CSRF vẫn có thể là mối quan tâm. Chỉ vô hiệu hóa CSRF khi kiến trúc xác thực và cách trình duyệt gửi credentials đã được đánh giá phù hợp.

## 8. Reactive: WebSession và SecurityContextRepository

Ứng dụng WebFlux không dùng HttpSession/MockHttpSession của Servlet. Khái niệm tương ứng là **WebSession** và **ServerSecurityContextRepository**.

- **WebSessionServerSecurityContextRepository** lưu SecurityContext vào WebSession để duy trì đăng nhập qua các request Reactive.
- **NoOpServerSecurityContextRepository** không lưu SecurityContext để dùng lại giữa các request.
- **WebTestClient** cùng **spring-security-test** cung cấp tiện ích mock JWT và mock user cho kiểm thử Reactive.

Ví dụ API Reactive stateless:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain reactiveApiChain(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .authorizeExchange(exchange -> exchange
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Với ứng dụng Reactive stateful, có thể cấu hình repository dựa trên WebSession:

~~~java
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

http.securityContextRepository(
        new WebSessionServerSecurityContextRepository()
);
~~~

Đoạn cấu hình thứ hai đặt trong quá trình xây dựng **SecurityWebFilterChain** của WebFlux. Không có enum SessionCreationPolicy tương đương được dùng theo cách Servlet ở đây; chính repository xác định SecurityContext được lưu vào WebSession hay không.

Ví dụ kiểm thử Reactive API bằng WebTestClient:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveStatelessSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void requestWithMockJwtCanAccessApi() {
        webTestClient.mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
            .get()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void aSeparateRequestWithoutJwtIsRejected() {
        webTestClient.get()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Hai request trên được thực hiện riêng biệt. Request đầu có JWT giả lập trong phạm vi test; request sau dùng WebTestClient gốc, không mang mock JWT. Test chứng minh một request không kế thừa Authentication của request trước qua SecurityContext đã lưu. Cũng như MockMvc, **mockJwt() không kiểm tra chữ ký token thật**.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Request web sau login không nhận người dùng | Đang dùng STATELESS, không truyền cùng session hoặc repository không lưu context | Kiểm tra policy, session và SecurityContextRepository |
| API tạo session dù đã đặt STATELESS | Controller/filter/thư viện khác gọi tạo session | Kiểm tra request.getSession(), request cache và các thành phần ứng dụng |
| NEVER bị hiểu nhầm là stateless | NEVER vẫn có thể dùng session có sẵn | Gửi request với session chứa SecurityContext để kiểm chứng |
| IF_REQUIRED vẫn tạo session trên request công khai | CSRF, request cache hoặc code ứng dụng cần session | Xác định thành phần tạo session |
| jwt() test pass nhưng token thật bị từ chối | Mock JWT bỏ qua decoder và xác minh chữ ký | Viết test tích hợp cho JwtDecoder và cấu hình issuer/JWK |
| API và web nhận cùng cấu hình | securityMatcher hoặc @Order sai | Kiểm tra chain nào xử lý từng URL |
| Reactive test dùng MockHttpSession | Nhầm stack Servlet với WebFlux | Dùng WebSession, WebTestClient và repository Reactive |
| POST API trả 403 | CSRF đang bật và request thiếu token | Xác minh cơ chế credentials; gửi CSRF token nếu endpoint cần |

## 10. Bài tập thực hành

1. Chạy hai test stateful ở mục 5. Xác minh endpoint công khai không cần session và login tạo SecurityContext trong session.
2. Đổi policy thành ALWAYS, gọi /public và kiểm tra session được tạo dù endpoint không cần Authentication.
3. Đổi sang NEVER. Gọi endpoint công khai không có session, sau đó chuẩn bị một session chứa SecurityContext và kiểm tra request sử dụng được session có sẵn.
4. Đổi sang STATELESS và cấu hình resource server JWT. Gửi request với jwt() rồi kiểm tra session không được tạo; bỏ jwt() và xác minh request bị từ chối.
5. Tạo hai SecurityFilterChain cho /api/** và phần web còn lại. Kiểm tra API không kế thừa đăng nhập bằng session của trình duyệt.
6. Với WebFlux, thử thay NoOpServerSecurityContextRepository bằng WebSessionServerSecurityContextRepository và quan sát khác biệt giữa request có và không có WebSession.
7. Nếu hệ thống dùng cookie để xác thực, đánh giá CSRF trước khi thay đổi cấu hình bảo vệ.

Khi chọn SessionCreationPolicy, hãy bắt đầu từ cách ứng dụng xác thực và duy trì danh tính. Web app cần tiếp nối đăng nhập thường dùng IF_REQUIRED; API bearer token thường dùng STATELESS; ALWAYS và NEVER dành cho những nhu cầu cụ thể cần được kiểm thử rõ ràng. Bằng chứng quan trọng là hành vi thực tế của request: session có được tạo khi cần, được dùng đúng nơi, và không vô tình trở thành nguồn xác thực cho một API được thiết kế stateless.
