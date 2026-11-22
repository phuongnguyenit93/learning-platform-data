# Đọc danh sách bộ lọc và xác định SecurityFilterChain đã được chọn trong Spring Security Servlet

> **Phạm vi:** Java 17+, Spring Boot 3 và Spring Security 6 trên **Servlet stack**. Bài này tập trung vào **chẩn đoán đường đi của một HTTP request**: filter nào tham gia, vì sao một `SecurityFilterChain` được chọn, cách đọc logs và danh sách filters, cách xác minh bằng test, và cách phân biệt lỗi chọn chain với lỗi xác thực/phân quyền. Đây không phải bài về WebFlux (`SecurityWebFilterChain`).
>
> **Nguyên tắc cốt lõi:** `FilterChainProxy` duyệt các `SecurityFilterChain` **theo thứ tự**, chọn **chain đầu tiên có `RequestMatcher` khớp request** và chạy những filters của chain đó. Nó không gộp filters của tất cả các chain cùng khớp. Vì vậy cần biết **matcher của từng chain**, **thứ tự chain** và **danh sách filters trong chain được chọn** trước khi kết luận một request có được Spring Security bảo vệ đúng hay không.

## 1. Tại sao đọc danh sách filter lại quan trọng?

Một ứng dụng có thể cùng phục vụ:

- `/api/**`: endpoint REST nhận HTTP Basic hoặc Bearer token, thường trả `401` khi chưa xác thực.
- `/admin/**`: endpoint quản trị yêu cầu role hoặc scope riêng.
- `/login` và trang web truyền thống: form login, `HttpSession` và CSRF.
- `/public/**`: người dùng chưa đăng nhập vẫn được đọc, nhưng vẫn cần security headers.
- `/actuator/**` hoặc servlet riêng: một số endpoint nằm trong servlet context/filter chain khác.

Các câu hỏi chẩn đoán thường gặp:

1. Vì sao `GET /api/orders` chưa đăng nhập lại **redirect 302 về `/login`** thay vì trả 401?
2. Vì sao cấu hình `oauth2ResourceServer(...)` không xử lý Bearer token ở một URL cụ thể?
3. Vì sao một endpoint bị **403** dù người dùng có Authentication hợp lệ?
4. Vì sao static resource không nhận CSP/HSTS/security headers?
5. Vì sao một filter custom chạy hai lần, chạy sai thứ tự hoặc không chạy?
6. Vì sao `requestMatchers("/api/**").permitAll()` không đồng nghĩa mọi request `/api/**` sẽ vào “API chain”?
7. Vì sao một URL chưa được chain nào bao phủ dù trong ứng dụng có `anyRequest().authenticated()`?

Để trả lời, không nên chỉ nhìn controller, exception handler hoặc một dòng `authorizeHttpRequests`. Phải lần theo **container filter → FilterChainProxy → selected SecurityFilterChain → ordered security filters → authorization → MVC**.

## 2. Kiến trúc: DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain

Mô hình phổ biến của Spring Security Servlet:

```text
Client
  |
  v
Servlet container's FilterChain
  |
  +-- Some application/container filters (the order varies)
  |
  +-- DelegatingFilterProxy
  |      bean name: springSecurityFilterChain
  |               |
  |               v
  |         FilterChainProxy
  |            |
  |            +-- SecurityFilterChain #1
  |            |     RequestMatcher: /api/**
  |            |     Filters: [SecurityContextHolderFilter,
  |            |               HeaderWriterFilter, ...,
  |            |               BasicAuthenticationFilter,
  |            |               ExceptionTranslationFilter,
  |            |               AuthorizationFilter]
  |            |
  |            +-- SecurityFilterChain #2
  |            |     RequestMatcher: /admin/**
  |            |     Filters: [context, headers, form login, ...]
  |            |
  |            +-- SecurityFilterChain #3
  |                  RequestMatcher: any request
  |                  Filters: [context, headers, form login, ...]
  |            |
  |            +--> FIRST MATCHING CHAIN ONLY
  |
  +-- Remaining servlet filters
  |
  v
DispatcherServlet -> HandlerMapping -> Controller
```

**`DelegatingFilterProxy`** là cầu nối giữa Servlet filter lifecycle và Spring ApplicationContext: nó tìm bean đã được Spring quản lý, thường tên `springSecurityFilterChain`.

**`FilterChainProxy`** là filter đại diện cho Spring Security. Nó sở hữu danh sách các `SecurityFilterChain` và xác định chain nào sẽ xử lý request. Các security filters trong chain thường không đăng ký trực tiếp thành servlet filters riêng lẻ.

**`SecurityFilterChain`** biểu diễn hai thông tin:
- Điều kiện chọn chain: `matches(HttpServletRequest)`.
- Danh sách filters có thứ tự: `getFilters()`.

Một số filters thường gặp (chỉ là ví dụ, không cam kết áp dụng cho mọi cấu hình):
- `DisableEncodeUrlFilter`;
- `WebAsyncManagerIntegrationFilter`;
- `SecurityContextHolderFilter`;
- `HeaderWriterFilter`;
- `CsrfFilter`;
- `LogoutFilter`;
- `UsernamePasswordAuthenticationFilter` khi dùng form login;
- `BasicAuthenticationFilter` khi bật HTTP Basic;
- `BearerTokenAuthenticationFilter` khi bật OAuth2 Resource Server;
- `AnonymousAuthenticationFilter`;
- `ExceptionTranslationFilter`;
- `AuthorizationFilter`.

**Sự hiện diện và thứ tự thực tế** phụ thuộc phiên bản Spring Security, DSL, login mechanism, session policy và các filters custom. Không nên ghi nhớ một danh sách “chuẩn” rồi giả định luôn đúng.

### 2.1. Một request chỉ chọn một security chain

Ví dụ có ba chain theo thứ tự:

| Thứ tự xét | Matcher của SecurityFilterChain | Request khớp |
| --- | --- | --- |
| 1 | `/api/**` | `/api/orders`, `/api/users` |
| 2 | `/admin/**` | `/admin/users` |
| 3 | `anyRequest` | Các request khác như `/login`, `/dashboard` |

Với `GET /api/orders`, chain #1 khớp nên được chọn. Spring Security **không tiếp tục** chạy chain #2 hoặc #3 dù một matcher ở chain sau cũng có thể khớp.

Nếu đưa matcher `anyRequest` lên đầu, nó sẽ khớp gần như mọi request phù hợp servlet chain và có thể “nuốt” các chain đặc biệt ở phía sau. Việc app vẫn khởi động không bảo đảm các routes được bảo vệ theo ý muốn.

**Hệ quả quan trọng:** Nếu một filter trong chain #1 quyết định cho đi tiếp hoặc trả lỗi, Spring Security **không** “thử chain #2” sau đó. Chain được chọn không phải bộ cơ chế authentication fallback tự động.

### 2.2. Nếu không chain nào khớp

Nếu `FilterChainProxy` không tìm thấy `SecurityFilterChain` khớp request, các filters thuộc Spring Security không được áp lên request đó và request có thể tiếp tục xuống Servlet application. Điều này có thể khiến endpoint **không được Spring Security bảo vệ** nếu không có biện pháp khác.

Đừng nhầm trường hợp này với một chain có matcher khớp nhưng cấu hình `permitAll()`. Trong trường hợp `permitAll`, chain vẫn chạy: các filters bảo mật liên quan, headers, context và một số cơ chế khác vẫn có thể tham gia.

Với ứng dụng nhiều chain, thường nên có **fallback chain có matcher bao phủ** ở cuối và kiểm thử tất cả URL quan trọng. Nếu chủ động để một URL không qua Spring Security, phải có lý do và threat model rõ ràng.

## 3. Hai nhóm matcher dễ nhầm: securityMatcher và requestMatchers

### 3.1. securityMatcher chọn **chain**

`http.securityMatcher("/api/**")` xác định **những request nào có thể vào SecurityFilterChain** được xây từ `HttpSecurity` đó.

Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

Mọi request khớp `/api/**` sẽ vào chain này nếu chưa bị chain có thứ tự trước đó chọn. Bên trong nó, `anyRequest().authenticated()` áp dụng **chỉ cho request đã được chain này chọn**, không phải mọi URL của ứng dụng.

### 3.2. requestMatchers bên trong authorizeHttpRequests đặt **quy tắc phân quyền**

`http.authorizeHttpRequests(auth -> auth.requestMatchers(...).permitAll())` không phải cú pháp thay thế cho `http.securityMatcher(...)`. Nó định nghĩa **authorization rules sau khi một security chain đã được chọn**.

Ví dụ:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Ở đây:
- `securityMatcher("/api/**")` chọn chain.
- Các `requestMatchers` trong `authorizeHttpRequests` kiểm tra quyền cho **các đường dẫn nằm trong chain đó**.
- Nếu request là `/dashboard`, các authorization rules ở trên **không có cơ hội chạy**.
- Nếu request là `/api/admin/42`, chain API được chọn rồi authorization rule quản trị được áp dụng.

**Không dùng `requestMatchers("/api/**").authenticated()` trong một catch-all chain để suy ra Spring Security sẽ tự chuyển sang một API chain khác.** Chain selection xảy ra **trước** bước authorization bên trong chain đã chọn.

### 3.3. @Order và thứ tự khai báo

Khi có nhiều bean `SecurityFilterChain`, dùng `@Order` hoặc cơ chế ordering được hỗ trợ để quy định thứ tự xét:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception { ... }

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception { ... }
```

**Chain đặc biệt đặt trước, chain bao phủ rộng đặt sau.** Không dựa vào thứ tự source file, tên bean, alphabetical order hoặc hành vi ngẫu nhiên khi nhiều beans có cùng priority. Việc **thứ tự filters bên trong một chain** lại do Spring Security quản lý theo quy tắc filter ordering riêng; đừng nhầm với `@Order` của các `SecurityFilterChain` beans.

## 4. Ví dụ Spring Security Servlet: API và web dùng hai chain

Ví dụ này có thể dùng trong một project Spring Boot 3, Spring Security 6 với Java 17+, khi có các starters `spring-boot-starter-web` và `spring-boot-starter-security`. Mỗi file ở đúng package được `@SpringBootApplication` scan; không phải Java độc lập chạy bằng `javac` nếu thiếu Spring libraries.

### 4.1. SecurityConfig.java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-test-only"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Ở đây:
- **Chain 1** chỉ nhận URL `/api/**`; chưa xác thực thường nhận HTTP `401` theo HTTP Basic authentication entry point.
- **Chain 2** không đặt `securityMatcher` riêng, nên có matcher bao phủ các requests còn lại. Request chưa xác thực ở web thường redirect `302` đến trang login.
- Endpoint `/api/admin/**` yêu cầu role `ADMIN`; user `alice` chỉ có role `USER`, nên request Basic hợp lệ vẫn bị từ chối **403**.
- `/api/public/**` dùng `permitAll` **trong API chain**, không có nghĩa bypass tất cả security filters.
- Cấu hình không cố tắt CSRF toàn cục. Các bài thử bên dưới dùng GET; với POST/PUT/DELETE cần xử lý CSRF tùy cơ chế credential. Nếu chain API dùng HTTP Basic và browser có thể tự gửi Basic credentials, phải **đánh giá CSRF**, không tự disable chỉ vì có tiền tố `/api`.
- `httpBasic` và `formLogin` là hai cơ chế authentication được gắn vào **hai chain khác nhau**, chứ không tạo một danh sách fallback tự động trên cùng request.

**Lưu ý thực tế:** `/login` có thể được Spring Security tạo trang đăng nhập mặc định; nếu tự xây trang, controller/static resources phải có quy tắc phù hợp. Tùy application context, có thêm filters khác do Spring Boot hoặc thư viện tạo, nhưng chỉ những filters có trong chain được chọn của Spring Security mới tham gia theo cơ chế này.

### 4.2. DemoController.java

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public String publicPing() {
        return "pong";
    }

    @GetMapping("/api/orders")
    public String orders() {
        return "orders";
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "admin-report";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }
}
```

Các response chỉ phục vụ test chain selection và authorization; không chứa dữ liệu thật. `/api/orders` không định nghĩa business permissions ngoài authenticated; dự án thật cần scope/ownership theo endpoint.

### 4.3. Kỳ vọng theo từng URL

| Request | Chain được chọn | Filter authentication chính | Kết quả thường gặp |
| --- | --- | --- | --- |
| `GET /api/public/ping` không auth | API | `BasicAuthenticationFilter` có mặt nhưng không có header | `200 pong` vì `permitAll` |
| `GET /api/orders` không auth | API | HTTP Basic | `401`, thường `WWW-Authenticate: Basic` |
| `GET /api/orders` có Basic đúng | API | HTTP Basic | `200 orders` |
| `GET /api/admin/report` với Alice/USER | API | HTTP Basic | `403` vì thiếu ADMIN |
| `GET /dashboard` không auth | Web fallback | Form login | `302` redirect tới `/login` |
| `GET /dashboard` sau form login hợp lệ | Web fallback | Session/authentication trong web chain | `200 dashboard` |
| `GET /apiary` không auth | Web fallback | Form login | Thường redirect `/login`; **không** phải API chain |
| `GET /login` | Web fallback | Login page filters | Trang login theo cấu hình/version |
| `GET /not-found` đã xác thực | Web fallback | Web auth | Spring MVC có thể trả 404; đó không có nghĩa chain không khớp |

Hãy phân biệt **vị trí lỗi**: `401`, `403` hoặc `302` có thể do authentication entry point/authorization; `404` là route/controller không tồn tại sau khi filter chain cho đi tiếp. Nhìn status một mình không chứng minh chain nào được chọn — cần phối hợp với logs, filter inventory và các tests tương ứng.

## 5. Java 17 độc lập: mô phỏng quy tắc first-match

Chương trình thuần JDK này minh họa **thuật toán chọn phần tử đầu tiên khớp**. Nó **không phải implementation của Spring Security RequestMatcher**: không xét servlet context, URL decoding, path normalization hoặc HTTP firewall. Dùng để hiểu nguyên tắc thứ tự, không dùng làm logic bảo mật thực tế.

File `FirstMatchingChainDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public final class FirstMatchingChainDemo {
    record Rule(String name, Predicate<String> matches) {}

    static String selected(List<Rule> chains, String path) {
        for (Rule chain : chains) {
            if (chain.matches().test(path)) {
                return chain.name();
            }
        }
        return "<none>";
    }

    public static void main(String[] args) {
        List<Rule> ordered = List.of(
            new Rule("API", p -> p.startsWith("/api/")),
            new Rule("ADMIN", p -> p.startsWith("/admin/")),
            new Rule("WEB", p -> true)
        );

        for (String path : List.of(
                "/api/orders", "/admin/users", "/dashboard", "/apiary")) {
            System.out.println(path + " -> " + selected(ordered, path));
        }

        List<Rule> wrongOrder = List.of(
            new Rule("WEB", p -> true),
            new Rule("API", p -> p.startsWith("/api/"))
        );
        System.out.println("wrong-order: /api/orders -> " +
            selected(wrongOrder, "/api/orders"));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac FirstMatchingChainDemo.java
java FirstMatchingChainDemo
```

Stdout chính xác:

```text
/api/orders -> API
/admin/users -> ADMIN
/dashboard -> WEB
/apiary -> WEB
wrong-order: /api/orders -> WEB
```

Giải thích: `/apiary` **không** bắt đầu bằng `/api/` trong mô hình đơn giản, nên rơi vào WEB. Khi WEB matcher `p -> true` đứng đầu, mọi path đều bị “nuốt” trước khi API matcher có cơ hội chạy. Trong Spring Security, matcher path thực tế phức tạp hơn và phải dựa vào framework thay vì dùng `startsWith` để quyết định bảo vệ endpoint.

## 6. Đọc danh sách SecurityFilterChain khi ứng dụng khởi động

Không cần đợi một request lỗi mới kiểm tra chain. Spring Security tạo các `SecurityFilterChain` từ DSL, thường ghi log khi xây chain và liệt kê matcher cùng các filter classes. Nội dung log chính xác phụ thuộc phiên bản.

Có hai cách bổ sung nhau:
1. **Bật log phù hợp ở môi trường test/dev** để thấy cấu hình chain và quá trình match request.
2. **Truy cập có kiểm soát danh sách `FilterChainProxy.getFilterChains()`** để in tên matcher và filters mà app thực sự khởi tạo.

### 6.1. Bật logging

Trong môi trường development/staging kiểm soát, cấu hình:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
```

`TRACE` có thể giúp quan sát quá trình Spring Security thử các chains, chọn chain nào và các security filters được chạy. Tên thông điệp, format, số filters và thứ tự chi tiết **không ổn định giữa các phiên bản**; hãy kiểm tra log thực thay vì tìm một literal string duy nhất.

Những dạng thông điệp thường có thể gặp (chỉ **minh họa**, không phải output bắt buộc):

```text
Will secure ... with [ ... filter names ... ]
Trying to match request against ... 
Securing GET /api/orders
Invoking ... filter ...
```

Hãy quan sát:
- Matcher của từng chain và thứ tự được thử.
- Chain nào khớp **đầu tiên**.
- Filter authentication phù hợp đã có mặt chưa (`BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, `BearerTokenAuthenticationFilter` ...).
- `AuthorizationFilter` có chạy ở cuối luồng bảo vệ dự kiến không.
- Request có bị HTTP firewall từ chối trước khi đến phần application routing không.

**Không bật TRACE/DEBUG rộng trên production chỉ để xem username.** Logs có thể chứa URL/query, danh tính, thông tin security và đôi khi dữ liệu nhạy cảm do custom filters ghi. Khi debug, hãy dùng môi trường an toàn, request dữ liệu giả, hạn chế retention và **redact Authorization, Cookie, Set-Cookie, session IDs và tokens**.

### 6.2. Debug mode của Spring Security

Một cấu hình hỗ trợ chẩn đoán trong development là:

```java
// Chỉ dùng trong local/test và chỉ khi cần debug:
@EnableWebSecurity(debug = true)
```

Đây là **annotation minh họa**, không phải class độc lập. Debug mode có thể cung cấp thông tin request/chain hữu ích nhưng **không dành cho production**; output có thể chứa dữ liệu request đáng chú ý và gây overhead. Khi đã chẩn đoán xong phải tắt.

Ưu tiên logger `FilterChainProxy` có phạm vi phù hợp nếu chỉ cần biết chain nào khớp, rồi mở rộng logger khi cần. Đừng đánh đồng log của servlet container filter với log của FilterChainProxy.

### 6.3. Liệt kê chain bằng mã Java trong môi trường nội bộ

Một `CommandLineRunner` chỉ bật cho profile dev có thể in inventory lúc startup. File `SecurityChainInventory.java` (mã **trong ứng dụng Spring Boot**, không chạy độc lập):

```java
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.DefaultSecurityFilterChain;

@Configuration
@Profile("dev")
public class SecurityChainInventory {
    private static final Logger log =
        LoggerFactory.getLogger(SecurityChainInventory.class);

    @Bean
    CommandLineRunner reportSecurityChains(
            @Qualifier("springSecurityFilterChain")
            FilterChainProxy proxy) {

        return args -> {
            int index = 0;
            for (SecurityFilterChain chain : proxy.getFilterChains()) {
                index++;

                String matcherDescription =
                    chain instanceof DefaultSecurityFilterChain known
                        ? known.getRequestMatcher().toString()
                        : chain.getClass().getName();

                String filterNames = chain.getFilters().stream()
                    .map(filter -> filter.getClass().getSimpleName())
                    .collect(Collectors.joining(" -> "));

                log.info("SECURITY CHAIN #{} matcher={}",
                    index, matcherDescription);
                log.info("SECURITY CHAIN #{} filters={}",
                    index, filterNames);
            }
        };
    }
}
```

**Ý nghĩa:**
- `getFilterChains()` trả danh sách SecurityFilterChain mà `FilterChainProxy` giữ, theo thứ tự đang được sử dụng.
- `SecurityFilterChain.getFilters()` cung cấp danh sách filters cho chain, thường theo đúng thứ tự chạy trong chain.
- Với `DefaultSecurityFilterChain`, `getRequestMatcher()` cho thông tin matcher. `toString()` của matcher là **dữ liệu chẩn đoán**, không phải định dạng hợp đồng ổn định để parser tự động.
- Chỉ dùng `@Profile("dev")` và **không expose inventory qua endpoint public**. Tên filters/matchers cho biết cấu trúc bảo vệ bên trong của ứng dụng.
- Không ghi Authentication, secrets hoặc raw HTTP header vào inventory.

Danh sách này trả lời **“ứng dụng đã xây những chains nào?”**, nhưng để biết **“một request cụ thể khớp chain nào?”**, vẫn cần logging theo request hoặc dùng `matches(request)` trên request đúng bối cảnh.

### 6.4. Tự kiểm tra chain khớp trong test nội bộ

Một phương pháp chẩn đoán ở môi trường thử nghiệm là duyệt chính danh sách chains:

```java
// Snippet bên trong một test/helper đã có FilterChainProxy proxy
// và HttpServletRequest request do Servlet test/container cung cấp.
int index = 0;
SecurityFilterChain chosen = null;

for (SecurityFilterChain chain : proxy.getFilterChains()) {
    index++;
    if (chain.matches(request)) {
        chosen = chain;
        System.out.println("first match #" + index);
        break;
    }
}

if (chosen != null) {
    for (jakarta.servlet.Filter filter : chosen.getFilters()) {
        System.out.println(filter.getClass().getSimpleName());
    }
} else {
    System.out.println("NO_SECURITY_CHAIN_MATCH");
}
```

Đây là **snippet**, không phải file Java độc lập; imports/biến `proxy`, `request` và `SecurityFilterChain` phải có trong test/helper. **Không** tạo một `MockHttpServletRequest` sai servletPath/contextPath rồi tưởng nó khớp y hệt request thực.

Một khác biệt quan trọng: `FilterChainProxy` có thể áp dụng `HttpFirewall` và thực hiện matching trên **request đã được firewall wrap/normalize theo quy tắc của framework**. Tự gọi `matches(rawRequest)` trên request dựng sai sẽ không tuyệt đối tương đương luồng HTTP thật. Khi cần kết luận cuối cùng, hãy kiểm chứng bằng **request thực qua filter chain** và bật TRACE để thấy lựa chọn tại runtime.

## 7. Các filter authentication xuất hiện theo cấu hình nào?

Một số dấu hiệu thông dụng:

| Filter | Thường đi cùng | Ý nghĩa khi chẩn đoán |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` | Form login | Xử lý submit username/password theo login processing URL |
| `BasicAuthenticationFilter` | `httpBasic` | Xử lý `Authorization: Basic ...` |
| `BearerTokenAuthenticationFilter` | `oauth2ResourceServer` | Trích Bearer token và gọi authentication pipeline |
| `OAuth2AuthorizationRequestRedirectFilter` | OAuth2 Login | Khởi tạo redirect tới OAuth2 provider |
| `OAuth2LoginAuthenticationFilter` | OAuth2 Login | Xử lý callback/login authentication |
| `SecurityContextHolderFilter` | Security context lifecycle | Cung cấp context trong request, phối hợp với repository |
| `CsrfFilter` | CSRF enabled | Kiểm soát CSRF trên request cần bảo vệ |
| `LogoutFilter` | Logout configuration | Kiểm tra request logout và gọi logout handlers |
| `AnonymousAuthenticationFilter` | Anonymous authentication enabled | Đại diện anonymous khi chưa có Authentication |
| `ExceptionTranslationFilter` | Exception handling của bảo mật web | Chuyển một số exception thành authentication entry point/access denied response |
| `AuthorizationFilter` | `authorizeHttpRequests` | Áp dụng quyết định phân quyền của chain |

**Không đọc tên filter một cách máy móc:** ví dụ `BearerTokenAuthenticationFilter` có mặt không đồng nghĩa mọi request đều có bearer token; `CsrfFilter` có mặt không đồng nghĩa GET bị chặn; `AuthorizationFilter` có mặt không đồng nghĩa cấu hình có rule chặt trên mọi endpoint.

Điều cần xác minh là **filter có trong selected chain không**, **request có đi qua filter không**, và **bước tương ứng có thật sự áp dụng cho HTTP method/URL đó không**.

### 7.1. Thứ tự filters bên trong chain

Spring Security có thứ tự filter được thiết kế sẵn. Một vài quan hệ thường quan trọng:
- Security context phải được chuẩn bị trước khi authorization dùng Authentication.
- Authentication filters xử lý credentials trước khi authorization cuối cùng ra quyết định.
- `ExceptionTranslationFilter` phối hợp chuyển authentication/authorization exceptions thành response HTTP phù hợp.
- `AuthorizationFilter` thường là bước authorization cuối trong nhiều cấu hình `authorizeHttpRequests`.

Khi thêm custom filter, sử dụng API `addFilterBefore`, `addFilterAfter` hoặc `addFilterAt` với filter type phù hợp và hiểu vị trí thật trong chain:

```java
// Snippet minh họa: loại filter và vị trí phải được đánh giá.
// http.addFilterBefore(customFilter, AuthorizationFilter.class);
```

**Không** tự đặt `@Order` lên một `@Component Filter` rồi nghĩ nó sẽ được đưa vào `FilterChainProxy` ở vị trí mong muốn. `@Order` của container filters và security filter ordering là hai lớp khác nhau.

### 7.2. Cảnh giác filter bị đăng ký hai lần

Khi một custom `Filter` là bean Servlet được Spring Boot tự đăng ký vào **container chain**, và cũng được thêm bằng `http.addFilterBefore(...)` vào **Spring Security chain**, cùng logic có thể chạy hai lần hoặc chạy trong hai vòng đời khác nhau.

Cách tiếp cận:
1. Xác định filter đang được quản lý bởi container hay là security filter.
2. Nếu muốn filter chỉ nằm trong Spring Security chain, tránh tự đăng ký nó thành servlet filter ngoài chain (ví dụ vô hiệu hóa servlet registration của bean bằng `FilterRegistrationBean#setEnabled(false)` khi phù hợp).
3. Kiểm tra tên filter trong security inventory và servlet filter registrations riêng.
4. Test request thực và đếm số lần filter thực thi, không chỉ dựa vào danh sách filters đã khởi tạo.

Một `OncePerRequestFilter` giúp tránh nhiều lần trong một số dispatch/lifecycle nhất định, nhưng không phải lời giải thay thế cho **đăng ký đúng vị trí** hoặc cách xử lý ASYNC/ERROR dispatch.

## 8. Cách đọc triệu chứng HTTP để khoanh vùng chain

### Trường hợp A: API trả 302 thay vì 401

**Kỳ vọng:** `GET /api/orders` chưa authenticated trả HTTP 401 từ API chain. **Thực tế:** 302 sang `/login`.

Kiểm tra theo thứ tự:
1. `/api/orders` có thật sự khớp `securityMatcher("/api/**")` của chain API không?
2. Có catch-all chain đứng trước API chain không?
3. API chain có `httpBasic` hoặc `oauth2ResourceServer` đúng loại request không?
4. Có custom `AuthenticationEntryPoint` redirect sang login không?
5. Request thực có contextPath/servletPath/proxy rewrite khác path nghĩ ban đầu không?

Nếu catch-all formLogin chain được chọn trước, API rules ở chain sau **không bao giờ chạy**. Khắc phục bằng thứ tự chain chính xác và test cả request anonymous/authenticated.

### Trường hợp B: API Bearer token “không được xử lý”

Có thể:
- Request khớp một chain không cấu hình `oauth2ResourceServer(...)`, nên không có `BearerTokenAuthenticationFilter` ở chain đó.
- Token được gửi sai nguồn (query/cookie/header tùy cấu hình resolver).
- Resolver tìm được token nhưng JWT decoder/introspection từ chối token (issuer, signature, expiry, audience).
- Authorization từ chối do thiếu scope/authority dù token hợp lệ.

**Chẩn đoán theo tầng:** chain selected → filter present → token extraction → authentication → authorization. Không sửa bằng cách bật mọi nguồn token hoặc nới `permitAll`.

### Trường hợp C: 403 dù đã xác thực

Có ít nhất hai nhóm nguyên nhân khác nhau:
- `CsrfFilter` từ chối unsafe request thiếu hoặc sai CSRF token.
- `AuthorizationFilter` hoặc method security từ chối vì thiếu role/scope/quyền đối với tài nguyên.

Một response 403 **không đủ** để xác định nhóm. Xem HTTP method, matcher, filter chain, logger, authentication state và test case. Nếu chỉ POST lỗi trong web session app, kiểm tra CSRF trước. Nếu GET `/api/admin/report` với user USER lỗi 403, kiểm tra rule `hasRole("ADMIN")`.

### Trường hợp D: filter custom không chạy

Có thể matcher chain không khớp; custom filter chỉ được thêm ở chain khác; request bị filter trước đó short-circuit; hoặc custom filter đăng ký vào container chain ở thứ tự không như dự tính. Đọc inventory theo chain và TRACE request, tránh thêm cùng filter vào mọi chain một cách mù quáng.

### Trường hợp E: không thấy security headers

Kiểm tra:
- Request có đi qua `FilterChainProxy` không?
- Có chain matching hay bị `web.ignoring()`/container rule bypass?
- `HeaderWriterFilter` có tồn tại và được thực thi trên response?
- Filter có ghi header trên loại response và HTTP scheme tương ứng không (ví dụ HSTS chỉ trên HTTPS)?
- CDN/reverse proxy có thay header hoặc trả response trước khi đến backend?

**`permitAll` không có nghĩa bỏ qua headers.** Nếu muốn static resource vẫn có CSP/nosniff (theo policy), cần bảo đảm request đi qua chain phù hợp.

### Trường hợp F: Spring MVC trả 404 nhưng tưởng không có chain

Nếu anonymous request tới `/unknown` được web chain redirect `/login`, chain **đã** xử lý request trước MVC. Khi đã authenticated, cùng `/unknown` có thể trả 404 do không tìm được handler. Đây không phải lỗi chain matching.

### Trường hợp G: request bị từ chối trước khi match

`HttpFirewall` của Spring Security có thể từ chối một số request có URL bất thường (encoded slash, semicolon hoặc ký tự/path không hợp lệ tùy firewall/config) bằng `RequestRejectedException`. Không “chữa” mọi lỗi này bằng nới firewall để matcher bắt đầu khớp; đánh giá URL và threat model, test normalization qua proxy/container. Nếu firewall từ chối, đừng giả định `AuthorizationFilter` đã chạy.

## 9. Kịch bản kiểm thử qua MockMvc

Đây là một bộ test thực tế trong Spring Boot project có `spring-boot-starter-test`, `spring-security-test` và các class `SecurityConfig`/`DemoController` ở mục 4. Test HTTP Basic **đi qua filter thật** với header được tạo từ credentials test; không dùng `@WithMockUser` để chứng minh Basic filter đã kiểm mật khẩu.

File `SecurityChainSelectionTests.java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainSelectionTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiUsesApiChainAndIsAccessible() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousApiGetsHttpBasicChallenge() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Basic")));
    }

    @Test
    void apiBasicCredentialsAuthenticate() throws Exception {
        mvc.perform(get("/api/orders")
                .with(httpBasic("alice", "demo-test-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("orders"));
    }

    @Test
    void apiRoleRuleDeniesOrdinaryUser() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("alice", "demo-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWebGetsLoginRedirect() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void similarPrefixDoesNotUseApiChain() throws Exception {
        mvc.perform(get("/apiary"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Chạy với Maven:

```bash
mvn -Dtest=SecurityChainSelectionTests test
```

Hoặc với Gradle:

```bash
./gradlew test --tests SecurityChainSelectionTests
```

Kỳ vọng sáu test PASS với setup ở mục 4. **Không giả định JUnit in stdout ứng dụng theo một mẫu cố định**: framework test báo kết quả tùy runner. Các tests xác minh hành vi HTTP đặc trưng của chain đã chọn và authentication/authorization, nhưng nếu hai chains tình cờ cho response giống nhau, **status riêng lẻ không đủ chứng minh identity của chain**. Bổ sung TRACE logs hoặc kiểm tra `getFilterChains()` để chứng minh filter inventory trong trường hợp cần mức bằng chứng cao hơn.

### 9.1. Vì sao test HTTP Basic không nên chỉ dùng @WithMockUser?

`@WithMockUser` / `with(user("alice"))` tạo Authentication giả lập cho test, có thể bỏ qua quá trình kiểm username/password của `BasicAuthenticationFilter`. Nó hữu ích khi test authorization nhưng **không chứng minh filter Basic thật có mặt hoặc hoạt động**. Với Resource Server, `with(jwt())` cũng giả lập JWT authentication, **không kiểm tra JWT decoder chữ ký thật**.

Khi chẩn đoán một filter authentication cụ thể, hãy test cả:
- Request **không có credential**.
- Request **có header/credential thực theo giao thức**.
- Credential không hợp lệ.
- Credential hợp lệ nhưng thiếu authority.
- Route khác matcher của chain để chứng minh chain boundary.

### 9.2. Test chain inventory và thứ tự

Có thể tạo unit/integration test truy cập bean `FilterChainProxy` và duyệt `getFilterChains()`:
- Số chains trong context đúng với cấu hình dự kiến; lưu ý thư viện hoặc test profile có thể tạo thêm chain.
- Matcher của chain API đứng **trước** catch-all web chain.
- Filter list API có `BasicAuthenticationFilter`, web có `UsernamePasswordAuthenticationFilter`.
- Nếu app dùng Bearer, chain cần thiết có `BearerTokenAuthenticationFilter`.
- Không đặt filter authentication sai bên trong chain vốn không chấp nhận credential đó.

Tránh hardcode một danh sách **toàn bộ** filter class names và thứ tự từ một phiên bản làm golden snapshot tuyệt đối. Chỉ assert những bất biến quan trọng; Spring Security version nâng cấp có thể thêm hoặc đổi filter hợp lệ.

### 9.3. Test explicit negative cho request không có chain

Nếu bạn cố tình xây những chain phạm vi hẹp **không có fallback**, tạo một endpoint test và gọi qua full MockMvc filter chain để kiểm tra nó có bị bảo vệ hay không. **Không** để endpoint nhạy cảm ngoài chain. Một test cố tình gửi anonymous tới protected URL và nhận 200 là tín hiệu cần điều tra, nhưng nếu controller tự `permitAll` hoặc không có security requirement, không đủ để kết luận chỉ từ 200.

Khi triển khai production, hãy quyết định **mọi request quan trọng phải được chain nào bảo vệ**, rồi test theo ma trận URL × method × user role.

## 10. Lộ trình chẩn đoán khi có nhiều SecurityFilterChain

Một quy trình tiết kiệm thời gian:

1. **Xác định HTTP request thực:** method, đường dẫn, servlet context, dispatcher type, scheme, proxy rewrite. Không log raw Authorization/Cookie.
2. **Liệt kê security chains:** gọi `FilterChainProxy.getFilterChains()` hoặc đọc log build chains; ghi matcher và thứ tự.
3. **Tìm first matching chain:** xem TRACE logs của request; chú ý firewall và các quy tắc match path.
4. **Đọc filter inventory của selected chain:** filter cần thiết có ở đó không? Có custom filter? Thứ tự có hợp lý?
5. **Phân biệt authentication và authorization:** token/credentials có được đọc/xác minh không? Sau đó có đủ role/scope không?
6. **Kiểm tra entry point / access denied:** 401, 302, 403 có đúng theo API/web chain không?
7. **Kiểm tra HTTP method/CSRF:** GET thành công nhưng POST 403 có thể do CSRF, không phải chain sai.
8. **Kiểm tra MVC routing:** được qua security nhưng 404/405 là tầng handler/method, không đồng nghĩa không có filters.
9. **Kiểm tra servlet filter registrations ngoài Spring Security:** duplicate filters, order, proxy headers, error dispatch.
10. **Chạy regression tests:** mỗi matcher boundary phải có ít nhất một request khớp và một request không khớp; test anonymous và authenticated.

Mục tiêu là tạo bằng chứng **“request X chọn chain #n, gồm filters F1..Fk, filter G đã xác thực/từ chối vì lý do Y, authorization trả kết quả Z”**, thay vì “Spring Security không chạy”.

## 11. Path matching và HTTP firewall: các góc dễ gây sai kết luận

### 11.1. URL chứa query parameter

`securityMatcher("/api/**")` so đường dẫn HTTP theo semantics của matcher, không phải tìm raw string trong toàn URL. Query như `?next=/api/admin` **không tự biến** `/dashboard` thành route API. Đồng thời proxy/container có thể normalize URL trước khi Spring Security nhìn thấy request.

Nếu viết custom `RequestMatcher`, không dùng trực tiếp `request.getRequestURI().contains("/api")` làm logic bảo mật; phải cân nhắc context path, servlet path, pathInfo, URL decoding và HTTP firewall. Chọn matcher có sẵn của Spring Security/MVC khi phù hợp.

### 11.2. /api/** và /apiary

`/api/**` biểu diễn một cấu trúc path, không phải so tiền tố chuỗi `"/api"` vô điều kiện. `/apiary` là đường dẫn khác. Khi gặp route lạ, thêm test negative như `/apiary` để đảm bảo matcher không quá rộng.

### 11.3. Forward, error và async dispatch

Servlet container có nhiều dispatcher types: `REQUEST`, `FORWARD`, `ERROR` và `ASYNC`. Tùy cấu hình đăng ký filters và behavior của từng filter, một request có thể đi qua các dispatch khác nhau. Đừng suy từ log một lần rằng filter “không chạy” trong mọi giai đoạn. Xác minh dispatcher type, lifecycle `OncePerRequestFilter` và bảo mật của error routes/async callbacks.

### 11.4. Context path và servlet path

Nếu ứng dụng chạy dưới context path `/app`, URL bên ngoài `/app/api/orders` có thể tương ứng với path security match `/api/orders` tùy matcher/Servlet mapping. Không tự viết `securityMatcher("/app/api/**")` chỉ bằng cách copy nguyên URL từ browser; hãy kiểm tra matcher đang đọc servlet path/path within application nào.

### 11.5. Khi sử dụng PathPattern hoặc MVC matchers

Spring Security 6 có nhiều cơ chế chọn `RequestMatcher` dựa trên môi trường MVC/Servlet và các API matcher được cấu hình. Không so sánh một matcher tự viết bằng `startsWith` với MVC matcher rồi kết luận chắc chắn chúng hành xử giống nhau. Với nhiều servlets hoặc mapping tùy biến, có thể cần cấu hình explicit matcher loại phù hợp và test Servlet path riêng.

**Chẩn đoán bảo mật không nên nới matcher/firewall chỉ để đạt status mong muốn.** Điều đúng là định nghĩa rõ phạm vi URL, kiểm thử path variants và giữ một fallback chain phù hợp.

## 12. Anti-patterns và cách sửa

### Anti-pattern A: catch-all trước chain chuyên biệt

```java
// PHẢN VÍ DỤ:
@Bean
@Order(1)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

Với cấu hình này, web chain catch-all đứng đầu. API chain sau có thể **không bao giờ được chọn**. Cách sửa: đặt chain API với matcher hẹp trước, catch-all web sau. Nếu định dùng OAuth2 Resource Server, còn cần `JwtDecoder`/issuer config phù hợp và kiểm thử JWT thật; snippet chỉ minh họa **lỗi thứ tự chain**, không phải cấu hình chạy độc lập.

### Anti-pattern B: nhầm securityMatcher và authorization requestMatchers

```java
// Sai ý định nếu muốn một API chain độc lập:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().permitAll());
```

Code này **không tạo security chain riêng cho /api**. Nó chỉ tạo các rules cho chain hiện tại. Nếu application cũng có API chain bean riêng, phải kiểm tra matcher và order của từng bean. Sửa ở **phân chia chain**, không chỉ sửa rule.

### Anti-pattern C: chẩn đoán bằng cách tắt security

Để “kiểm tra cho dễ”, developer dùng `web.ignoring()` hoặc loại bỏ filters cho request, sau đó thấy endpoint 200 và kết luận controller đúng. Điều này **không chứng minh security config đúng** và có thể bỏ CSP/HSTS/CSRF. Dùng test user/token, debug/TRACE trong test environment và tách rõ bypass có chủ đích.

### Anti-pattern D: filter custom vừa là servlet filter vừa là security filter

Một `@Component` filter có thể được Spring Boot tự đăng ký ở container, sau đó được thêm thủ công vào security chain. Test đếm số lần thực thi và kiểm tra đăng ký; không giải quyết chỉ bằng việc sửa `@Order` của bean.

### Anti-pattern E: log toàn bộ token để đo filter

Việc in `Authorization: Bearer`, `Cookie: JSESSIONID` hoặc raw JWT để “xem filter đã thấy gì” tạo nguồn rò rỉ. Hãy log **tên filter, route đã che dữ liệu nhạy cảm, ID request an toàn, loại auth và kết quả**, không log credential.

### Anti-pattern F: chỉ nhìn HTTP status

Cùng 403 có thể do CSRF hoặc authorization. Cùng 302 có thể do form login hoặc custom redirect. Cùng 404 có thể xảy ra sau khi security filters chạy đúng. Kết luận phải dựa trên **chain selection + filter inventory + runtime trace + test**.

## 13. Checklist điều tra và nghiệm thu

- [ ] Xác nhận bean `springSecurityFilterChain` đang được Servlet container đăng ký qua `DelegatingFilterProxy`; biết nơi cấu hình/đăng ký.
- [ ] Liệt kê đủ các `SecurityFilterChain` với matcher và thứ tự, không đoán từ tên bean hoặc thứ tự code.
- [ ] Đặt chain matcher hẹp trước catch-all, có test để phát hiện catch-all nuốt API.
- [ ] Phân biệt `securityMatcher` chọn chain và `requestMatchers` trong `authorizeHttpRequests` đặt authorization rule.
- [ ] Với request cụ thể, xác định chain **khớp đầu tiên**; không cộng dồn filters từ các chains khác.
- [ ] Đọc `getFilters()` của selected chain; xác nhận filter Basic, Bearer, Form, CSRF hoặc custom có mặt theo đúng contract.
- [ ] Dùng logging `FilterChainProxy` có kiểm soát ở dev/test, không bật verbose logs chứa credentials trên production.
- [ ] Test ít nhất một positive và một negative URL cho từng matcher, bao gồm đường dẫn gần giống như `/apiary`.
- [ ] Test riêng anonymous, credential hợp lệ, credential sai và thiếu role/scope; phân biệt 401, 302, 403.
- [ ] Test GET và unsafe methods; không suy 403 do authorization khi có thể là CSRF.
- [ ] Kiểm tra servlet context/path, proxy rewrites, dispatcher types và firewall nếu request không match như dự kiến.
- [ ] Kiểm tra duplicate custom filter ở container registration và security chain.
- [ ] Static/public resources đi qua chain phù hợp nếu cần headers; không bỏ Spring Security filters ngoài ý muốn.
- [ ] Với Resource Server, không dùng `with(jwt())` để chứng minh decoder đã xác thực JWT ký thật.
- [ ] Đánh giá filter order theo cơ chế Spring Security, không chỉ `@Order` của servlet filter bean.
- [ ] Không cung cấp filter inventory/trace dưới public endpoint, không ghi raw token, Cookie hay session ID vào log.
- [ ] Nếu một route không được chain nào match, xác định đó là quyết định chủ động hay lỗ hổng bảo vệ.

**Kết luận:** Khi chẩn đoán Spring Security Servlet, hãy bắt đầu từ **`FilterChainProxy`**, liệt kê **`SecurityFilterChain` theo thứ tự**, tìm **matcher đầu tiên khớp request**, rồi xem **danh sách filters và hành vi runtime** của chính chain đó. `securityMatcher` quyết định request vào chain nào; `authorizeHttpRequests().requestMatchers(...)` chỉ định quyền **bên trong chain**. Kết hợp inventory, TRACE logs, MockMvc và HTTP thực để phân biệt chain sai, filter thiếu, authentication thất bại, CSRF, authorization 403 và MVC 404 một cách có bằng chứng.
