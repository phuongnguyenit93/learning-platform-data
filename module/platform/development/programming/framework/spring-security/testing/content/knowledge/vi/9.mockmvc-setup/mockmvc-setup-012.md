# Xác minh một request thực sự đi qua chuỗi bảo mật mong đợi

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **Spring MVC với MockMvc**: xác minh một request được `FilterChainProxy` chuyển vào đúng `SecurityFilterChain` mà ứng dụng dự kiến.

Sau bài học, bạn có thể:

1. Giải thích `FilterChainProxy` chọn chuỗi bảo mật đầu tiên khớp request.
2. Phân biệt `securityMatcher(...)` với `authorizeHttpRequests().requestMatchers(...)`.
3. Thiết kế test có nhiều `SecurityFilterChain` với các policy khác nhau để phát hiện chọn nhầm chuỗi.
4. Xác minh cả request được phép, bị từ chối và request không khớp chuỗi nào.
5. Dùng response marker hoặc log `FilterChainProxy` để chẩn đoán chain được chọn.
6. Tránh kết luận sai chỉ dựa trên việc bean `SecurityFilterChain` tồn tại hoặc một request trả 200.

## 1. Một request chỉ đi qua chuỗi đầu tiên khớp

Ứng dụng Servlet có thể khai báo nhiều bean `SecurityFilterChain`, ví dụ một chuỗi cho API quản trị, một chuỗi cho API thông thường và một chuỗi fallback. `FilterChainProxy` nhận request rồi kiểm tra từng chuỗi theo thứ tự ưu tiên. Nó chọn **chuỗi đầu tiên có matcher khớp** và thực thi các filter trong chuỗi đó.

~~~mermaid
flowchart TD
    A["MockMvc request"] --> B["FilterChainProxy"]
    B --> C{"adminChain khớp?"}
    C -->|Có| D["Chạy adminChain"]
    C -->|Không| E{"apiChain khớp?"}
    E -->|Có| F["Chạy apiChain"]
    E -->|Không| G{"fallbackChain khớp?"}
    G -->|Có| H["Chạy fallbackChain"]
    G -->|Không| I["Không có SecurityFilterChain<br/>được áp dụng"]
    D --> J["Authentication / Authorization / CSRF"]
    F --> J
    H --> J
~~~

Hai khái niệm matcher cần phân biệt:

| API | Phạm vi | Câu hỏi được trả lời |
| --- | --- | --- |
| `http.securityMatcher(...)` | Chọn toàn bộ `SecurityFilterChain` | Request có thuộc chuỗi này không? |
| `authorizeHttpRequests(...).requestMatchers(...)` | Chọn luật authorization bên trong chuỗi đã chọn | Request này được phép cho ai? |

Ví dụ:

~~~java
http
    .securityMatcher("/api/admin/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().hasRole("ADMIN")
    );
~~~

Chuỗi này chỉ áp dụng cho đường dẫn `/api/admin/**`. Trong phạm vi đó, mọi request phải có role `ADMIN`. Một request `/api/public` không được xét bởi chuỗi này; `FilterChainProxy` tiếp tục kiểm tra chuỗi tiếp theo.

Nếu không có chuỗi nào khớp, request có thể đi tiếp mà không qua các security filters trong một `SecurityFilterChain`. Vì vậy, ứng dụng thường cần một **fallback chain** để xác định chính sách cho những URL còn lại.

## 2. Ví dụ ứng dụng có ba SecurityFilterChain

Ta chia request thành ba vùng:

- `/api/admin/**`: chỉ role `ADMIN`.
- `/api/**`: endpoint public được phép ẩn danh; các endpoint khác cần đăng nhập.
- Các URL còn lại: từ chối mặc định.

### 2.1. Security configuration

Tệp `src/main/java/example/SecurityConfiguration.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Các chuỗi được kiểm tra theo `@Order`. `adminChain` phải đứng trước `apiChain` vì đường dẫn admin cũng nằm trong `/api/**`. Nếu đảo thứ tự, request quản trị có thể khớp `apiChain` trước, và `adminChain` không bao giờ được chọn cho request đó.

`fallbackChain` không khai báo `securityMatcher` nên là chuỗi bắt mọi request còn lại. Quy tắc `denyAll()` khiến các URL ngoài hai vùng API không vô tình được phép truy cập. Trong ví dụ, `httpBasic` giúp minh họa phản hồi khi có/không có authentication; fallback vẫn từ chối cả người dùng đã xác thực.

### 2.2. Controller mẫu

Tệp `src/main/java/example/ApiController.java`:

~~~java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/api/admin/reports")
    String adminReports() {
        return "admin reports";
    }

    @GetMapping("/ops/health")
    String health() {
        return "health";
    }
}
~~~

Controller không tự kiểm tra role. Những luật URL được đặt ở security chain để test có thể quan sát rõ sự khác biệt giữa các chuỗi.

## 3. Dùng hành vi khác nhau để phát hiện chọn nhầm chain

Các chain ở ví dụ trên có policy đủ khác biệt để phân biệt:

| Request | Chain mong đợi | Danh tính | Kết quả |
| --- | --- | --- | --- |
| `GET /api/public` | `apiChain` | Anonymous | 200 |
| `GET /api/profile` | `apiChain` | Anonymous | 401 |
| `GET /api/profile` | `apiChain` | USER | 200 |
| `GET /api/admin/reports` | `adminChain` | Anonymous | 401 |
| `GET /api/admin/reports` | `adminChain` | VIEWER | 403 |
| `GET /api/admin/reports` | `adminChain` | ADMIN | 200 |
| `GET /ops/health` | `fallbackChain` | USER | 403 |

Điểm phân biệt quan trọng là request `/api/admin/reports` với `VIEWER`:

- Nếu `adminChain` được chọn, người dùng VIEWER bị 403 vì thiếu `ROLE_ADMIN`.
- Nếu `apiChain` được chọn, VIEWER đã xác thực sẽ được phép qua luật `anyRequest().authenticated()` và có thể nhận 200.

Vì vậy, ca VIEWER giúp phát hiện việc `apiChain` đứng trước `adminChain`. Chỉ kiểm tra ADMIN nhận 200 sẽ không phát hiện lỗi thứ tự, vì cả hai chain đều có thể cho ADMIN đi qua.

## 4. Bộ kiểm thử MockMvc cho các chuỗi

Tệp `src/test/java/example/SecurityChainSelectionTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class SecurityChainSelectionTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointUsesApiPolicyAndAllowsAnonymous() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void profileEndpointRejectsAnonymous() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void authenticatedUserCanReadProfile() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isOk());
    }

    @Test
    void adminEndpointRejectsAnonymous() throws Exception {
        mockMvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerIsForbiddenByAdminChain() throws Exception {
        mockMvc.perform(get("/api/admin/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadReports() throws Exception {
        mockMvc.perform(get("/api/admin/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin reports"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void fallbackChainDeniesUnmatchedApplicationPath() throws Exception {
        mockMvc.perform(get("/ops/health"))
            .andExpect(status().isForbidden());
    }
}
~~~

`@AutoConfigureMockMvc` giữ filters được đăng ký trong context theo mặc định. `@WithMockUser` tạo authentication giả lập cho các test authorization; nó không kiểm tra mật khẩu hoặc quy trình đăng nhập.

Các status 401/403 trong bảng dựa trên HTTP Basic và anonymous authentication mặc định. Nếu ứng dụng dùng form login hoặc entry point tùy chỉnh, anonymous có thể nhận 302 hoặc status khác. Hãy giữ nguyên contract thực tế của ứng dụng khi viết assertion.

## 5. Vì sao chỉ nhìn status đôi khi chưa đủ?

Một test status có thể chứng minh policy khác biệt đã được áp dụng, nhưng không phải lúc nào cũng xác định chính xác tên chain:

- Hai chain có thể tình cờ khai báo cùng policy, khiến cùng request trả cùng status.
- Một endpoint có thể bị chặn bởi method security hoặc logic trong controller/service trước khi kết quả phản ánh URL policy bạn định kiểm tra.
- Request có thể đi qua `FilterChainProxy` nhưng không có `SecurityFilterChain` nào khớp.
- Một custom filter có thể từ chối request trước khi tới `AuthorizationFilter`.

Khi cần bằng chứng rõ hơn, có thể kết hợp ba cách:

1. Thiết kế policy của từng chain đủ khác nhau để test một role phân biệt được chain.
2. Bật log `FilterChainProxy` để quan sát matcher và chain được chọn.
3. Trong môi trường test, thêm một response marker riêng cho từng chain để assertion trực tiếp chain đã được chọn.

### 5.1. Dùng log FilterChainProxy

Trong cấu hình test:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Log giúp quan sát `FilterChainProxy` nhận request, các `SecurityFilterChain` được xét và những filter tham gia xử lý. Nội dung log có thể thay đổi theo phiên bản Spring Security; hãy dùng nó để chẩn đoán, không nên assert nguyên văn log trong test.

Nếu không thấy `FilterChainProxy` nhận request, hãy kiểm tra cách dựng MockMvc và đăng ký filter. Nếu proxy có nhận request nhưng không chọn chain nào, kiểm tra `securityMatcher` và fallback. Nếu chain đúng được chọn nhưng status sai, kiểm tra rule authorization, authentication và CSRF.

### 5.2. Thêm response marker cho từng chain trong môi trường test

Khi cần xác nhận trực tiếp chain đã chạy, có thể thêm một filter chẩn đoán vào từng chain trong cấu hình **test profile**. Filter đặt response header trước khi các filter sau xử lý:

~~~java
package example;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

class ChainMarkerFilter extends OncePerRequestFilter {
    private final String chainName;

    ChainMarkerFilter(String chainName) {
        this.chainName = chainName;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        response.setHeader("X-Test-Security-Chain", chainName);
        filterChain.doFilter(request, response);
    }
}
~~~

Gắn marker vào từng chain, trước `SecurityContextHolderFilter`:

Đoạn cấu hình cần import `org.springframework.security.web.context.SecurityContextHolderFilter`.

~~~java
return http
    .securityMatcher("/api/admin/**")
    .addFilterBefore(
        new ChainMarkerFilter("admin"),
        SecurityContextHolderFilter.class
    )
    .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("ADMIN"))
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

Tương tự, `apiChain` dùng marker `"api"` và `fallbackChain` dùng marker `"fallback"`. Giữ nguyên các `securityMatcher` và authorization rules cần kiểm tra. Chỉ bật marker trong test profile hoặc cấu hình chẩn đoán; không để header nội bộ này lộ ra ngoài production nếu không có lý do.

Sau đó test có thể xác nhận cả chain và kết quả:

~~~java
mockMvc.perform(get("/api/admin/reports"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string("X-Test-Security-Chain", "admin"));

mockMvc.perform(get("/api/profile"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string("X-Test-Security-Chain", "api"));

mockMvc.perform(get("/ops/health")
        .with(user("operator").roles("USER")))
    .andExpect(status().isForbidden())
    .andExpect(header().string("X-Test-Security-Chain", "fallback"));
~~~

Ví dụ này cần static imports `get`, `status`, `header` và request post-processor `user`. Marker được đặt trước security context filter nên header được ghi trước khi authorization có thể từ chối request; nó giúp nhận biết chuỗi đã được vào, kể cả khi response cuối là 401/403.

Đây là instrumentation cho test, không phải thành phần bảo mật. Nếu tạo một test-only copy của security configuration, hãy nhớ rằng test đó chứng minh matcher/rule của bản copy. Để kiểm tra đúng cấu hình ứng dụng, hãy tích hợp marker qua test profile vào chính các chain đang được ứng dụng sử dụng, hoặc dựa trên log và policy-discriminating tests.

## 6. Kiểm tra matcher và thứ tự khi có nhiều chain

Một lỗi thường gặp là khai báo chuỗi tổng quát trước chuỗi chuyên biệt:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Với thứ tự này, `/api/admin/reports` khớp `apiChain` trước; `adminChain` không được xét nữa. Người dùng VIEWER đã xác thực có thể được phép bởi `anyRequest().authenticated()`, mặc dù ý định là chỉ ADMIN được vào.

Sửa bằng cách đặt `@Order(1)` trên method `@Bean adminChain(...)` và `@Order(2)` trên method `@Bean apiChain(...)`. Đặt annotation trên đúng method của từng chain, không đặt hai annotation trên cùng một method.

### Checklist cho mỗi request

1. URL và HTTP method của request là gì?
2. Những `SecurityFilterChain` nào có `securityMatcher` phù hợp?
3. Chain nào có `@Order` cao nhất (số nhỏ hơn) trong các chain khớp?
4. Có fallback chain cho URL ngoài vùng matcher không?
5. Rule `requestMatchers` bên trong chain được chọn cho phép role/authority nào?
6. Test đã có cả một danh tính thiếu quyền và một danh tính đủ quyền chưa?
7. Nếu status không phân biệt được chain, log hoặc marker nào xác nhận chain thực tế?

## 7. Request không khớp chuỗi nào

`FilterChainProxy` có thể được gọi nhưng không có `SecurityFilterChain` nào khớp request. Khi đó, proxy không thực thi filter list của một chuỗi bảo mật cho request đó. Đây là lý do fallback chain quan trọng.

Ví dụ:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Nếu chỉ có chain này, `GET /ops/health` không thuộc `/api/**`. Đừng giả định `anyRequest().authenticated()` trong chain đó bảo vệ toàn bộ ứng dụng; nó chỉ áp dụng cho request đã khớp `securityMatcher` của chain.

Thêm fallback:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Fallback giúp chính sách ngoài API trở nên rõ ràng. Nếu ứng dụng có trang web riêng, health endpoint hoặc static resources cần chính sách khác, hãy định nghĩa chain/rule tương ứng thay vì để chúng rơi vào một vùng không được bảo vệ ngoài ý muốn.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| VIEWER truy cập admin thành công | Chain tổng quát khớp trước chain admin | Sắp xếp `@Order` để chain chuyên biệt đứng trước |
| Admin nhận 401 dù có `@WithMockUser` | MockMvc chưa tích hợp Spring Security hoặc test dùng sai instance | Dùng Boot auto-config có filters hoặc `.apply(springSecurity())` |
| Request ngoài `/api/**` không bị chặn | Không có fallback chain | Thêm chain fallback hoặc policy rõ ràng cho vùng đó |
| Hai chain cùng trả 200 cho test ADMIN | Policy không đủ khác biệt để nhận diện chain | Thêm test VIEWER hoặc marker/log |
| Proxy có chạy nhưng không thấy security filter | Không có chain nào khớp request | Kiểm tra `securityMatcher` |
| Chain đúng nhưng 403 | Role/authority sai, CSRF hoặc rule bên trong chain từ chối | Kiểm tra authority, method và CSRF |
| Test marker header không xuất hiện khi 401 | Marker được đặt sau filter đã từ chối request, hoặc request không vào chain đó | Đặt marker sớm hơn trong chain và xem TRACE log |
| Test profile cho kết quả khác production | Test-only chain không giống cấu hình thật | Dùng cùng chain/configuration và chỉ bổ sung instrumentation |

## 9. Bài tập thực hành

**Bài 1 — Phát hiện thứ tự sai.** Đưa `apiChain` lên trước `adminChain`. Chạy test với VIEWER cho `GET /api/admin/reports` và quan sát vì sao request có thể nhận 200. Đổi lại thứ tự rồi xác nhận 403.

**Bài 2 — Kiểm tra fallback.** Bỏ `fallbackChain` và gửi request tới `/ops/health`. Sau đó thêm fallback `denyAll()` và viết test xác nhận request bị từ chối.

**Bài 3 — Phân biệt matcher.** Thay `securityMatcher("/api/**")` bằng matcher hẹp hơn. Xác định request nào không còn thuộc chain và vì sao `requestMatchers(...)` bên trong không bảo vệ URL ngoài phạm vi.

**Bài 4 — Xác nhận chain bằng marker.** Thêm `ChainMarkerFilter` trong test profile vào admin, api và fallback chain. Assert header cho request 401, 403 và 200.

**Bài 5 — Kiểm thử policy đầy đủ.** Viết bộ test anonymous, VIEWER, USER và ADMIN trên từng vùng URL. Đối chiếu status với TRACE log để xác nhận chuỗi được chọn.

## 10. Ghi nhớ

`FilterChainProxy` chọn **chuỗi đầu tiên khớp request**. `securityMatcher(...)` quyết định request thuộc chuỗi nào; `requestMatchers(...)` bên trong chuỗi đã chọn quyết định quyền truy cập. Một chuỗi tổng quát đặt trước chuỗi chuyên biệt có thể che khuất chính sách mong muốn, và một request không khớp chuỗi nào có thể không được bảo vệ bởi các filter của Spring Security.

Để xác minh request đi qua đúng chuỗi, hãy sắp xếp matcher rõ ràng, có fallback, thiết kế test role đủ phân biệt và kiểm tra cả request được phép lẫn bị từ chối. Khi status chưa đủ chứng minh, dùng TRACE log hoặc response marker chỉ dành cho test. Đừng kết luận từ một bean tồn tại hay một response 200 rằng đúng security chain đã chạy.
