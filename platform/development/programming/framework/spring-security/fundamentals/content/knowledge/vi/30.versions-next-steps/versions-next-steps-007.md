# Học sâu phân quyền, Servlet hoặc reactive theo kiến trúc ứng dụng

## 1. Mục tiêu của chặng học tiếp

Sau khi nắm nền tảng Spring Security (xác thực, phân quyền, `SecurityContext` và chuỗi bộ lọc), bước tiếp theo không phải học mọi API cùng lúc. Hãy trả lời hai câu hỏi độc lập:

1. **Ứng dụng cần kiểm soát quyền truy cập đến mức nào?** Quyền theo vai trò, quyền chi tiết, quyền trên từng bản ghi, tổ chức/người sở hữu, hay cả những điều kiện nghiệp vụ? Đây là nhánh **phân quyền (authorization)** mà mọi kiến trúc đều cần.
2. **Ứng dụng xử lý HTTP theo mô hình nào?** Spring MVC trên nền Servlet hay Spring WebFlux với luồng xử lý reactive? Câu trả lời quyết định bộ API cấu hình, nơi lưu ngữ cảnh bảo mật và công cụ kiểm thử.

Kết quả mong đợi: đọc được luồng bảo mật của dự án đang có; vẽ được ma trận quyền; chọn đúng cấu hình Servlet hoặc reactive; kiểm thử cả truy cập hợp lệ và truy cập bị từ chối; biết khi nào phải học sâu OAuth2 Resource Server, phương thức và quyền sở hữu tài nguyên.

## 2. Chọn hướng học theo kiến trúc thực tế

| Dấu hiệu trong dự án | Ưu tiên học | Công cụ Spring Security đặc trưng |
| --- | --- | --- |
| `spring-boot-starter-web`, Spring MVC, `DispatcherServlet`, controller trả về đối tượng/`ResponseEntity` | **Servlet** cùng phân quyền | `HttpSecurity`, `SecurityFilterChain`, `FilterChainProxy`, `SecurityContextHolder`, `MockMvc` |
| `spring-boot-starter-webflux`, handler trả `Mono`/`Flux`, chuỗi xử lý không chặn | **Reactive** cùng phân quyền | `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebFilterChainProxy`, `ReactiveSecurityContextHolder`, `WebTestClient` |
| Nhiều vai trò, nhiều tài nguyên, quy tắc theo người sở hữu/tenant | **Phân quyền sâu** trước, sau đó áp vào Servlet hoặc reactive đang dùng | `hasAuthority`, `hasRole`, `@PreAuthorize`, `AuthorizationManager`, kiểm thử quyền |
| Hệ thống có gateway WebFlux và các dịch vụ MVC | Học **cả hai**, mỗi ứng dụng theo đúng runtime của nó; thống nhất nguyên tắc quyền giữa các dịch vụ | Gateway: reactive; dịch vụ MVC: Servlet; cả hai tự xác thực/phân quyền theo phạm vi chịu trách nhiệm |
| API nhận JWT từ một nhà cung cấp danh tính | Học **OAuth2 Resource Server** sau khi hiểu quy tắc phân quyền | Bộ kiểm tra JWT, issuer/audience, ánh xạ scope/role, cấu hình Resource Server tương ứng runtime |

**Không dùng số lượng request lớn như lý do duy nhất để chuyển sang reactive.** WebFlux phù hợp nhất khi toàn bộ chuỗi I/O và thư viện liên quan có thể hoạt động không chặn; gọi JDBC hoặc HTTP blocking trực tiếp trên event loop có thể làm mất lợi thế và gây nghẽn. Dịch vụ MVC vẫn có thể phục vụ tải lớn với cấu hình phù hợp. Đổi runtime chỉ vì muốn dùng một bộ DSL bảo mật mới là quyết định sai trọng tâm.

**Kiểm tra classpath:** Khi thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` vào cùng ứng dụng, Spring Boot thường tự chọn Spring MVC; việc dùng `WebClient` không tự biến ứng dụng thành WebFlux. Kiểm tra loại ứng dụng thật trước khi chọn chain bảo mật. Hai cấu hình ví dụ ở dưới dành cho **hai ứng dụng riêng**, không ghép cả hai vào một ứng dụng.

## 3. Nền tảng phân quyền phải học ở cả hai nhánh

### 3.1. Xác thực khác phân quyền

- **Authentication**: ai đang gọi? Kết quả thường là một đối tượng `Authentication` trong ngữ cảnh bảo mật, chứa principal và các `GrantedAuthority`.
- **Authorization**: principal này có được thực hiện hành động trên tài nguyên cụ thể không? Quyết định phải xét hành động, tài nguyên và đôi khi cả ngữ cảnh như chủ sở hữu, tenant, trạng thái đơn hàng.
- **Role** là cách nhóm nhiều quyền; **authority** là một chuỗi quyền cụ thể. Theo mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; `hasAuthority("report:read")` kiểm tra đúng chuỗi `report:read`. Tránh tự thêm `ROLE_` vào đối số của `hasRole`.
- **Scope trong JWT** và **role nội bộ** không đồng nghĩa. Nếu JWT chứa scope `reports.read`, bộ ánh xạ thường tạo authority dạng `SCOPE_reports.read`; muốn dùng `report:read` hoặc `ROLE_ADMIN` cần thiết kế phép ánh xạ rõ ràng, có kiểm thử.

### 3.2. Hai lớp ra quyết định

1. **Ở HTTP:** chặn sớm những đường dẫn không công khai, giới hạn theo phương thức HTTP và loại người dùng. Servlet dùng `authorizeHttpRequests` + `requestMatchers`; reactive dùng `authorizeExchange` + `pathMatchers`.
2. **Ở nghiệp vụ:** kiểm tra quyền ngay tại phương thức dịch vụ và chính sách dữ liệu, đặc biệt khi dịch vụ có thể được gọi từ HTTP, tác vụ định kỳ, sự kiện, GraphQL hoặc nơi khác. Bật method security và dùng `@PreAuthorize` khi hợp lý.

Chỉ kiểm tra mẫu URL **không đủ** cho trường hợp “người dùng A được đọc báo cáo 42 nhưng không được đọc báo cáo 43 của người khác”. Quy tắc này cần so sánh principal với chủ sở hữu tài nguyên trong lớp nghiệp vụ hoặc truy vấn dữ liệu, và phải kiểm tra tenant để tránh truy cập chéo tổ chức.

### 3.3. Thiết kế một ma trận quyền trước khi viết cấu hình

Giả sử hệ thống có endpoint sau:

| Hành động | Khách chưa đăng nhập | Người có `report:read` | Người có `ROLE_ADMIN` |
| --- | --- | --- | --- |
| `GET /public` | Cho phép | Cho phép | Cho phép |
| `GET /reports/{id}` | Từ chối | Cho phép **nếu** chính sách dữ liệu cho phép | Tùy chính sách nghiệp vụ; ví dụ chỉ khi có `report:read` |
| `GET /admin/status` | Từ chối | Từ chối | Cho phép |
| Đường dẫn khác chưa được khai báo | Từ chối | Từ chối | Từ chối |

Với mỗi dòng, ghi rõ: nguồn danh tính, authority cần có, điều kiện chủ sở hữu/tenant, phản hồi dự kiến, vị trí thực thi chính sách và một bài kiểm thử âm tính. Dùng nguyên tắc **quyền tối thiểu**, **từ chối mặc định**, không lấy việc “đã đăng nhập” làm điều kiện đủ để đọc mọi dữ liệu.

## 4. Nhánh Servlet: Spring MVC / HTTP theo chuỗi Filter

### 4.1. Cơ chế cần hiểu

Một yêu cầu HTTP đi qua chuỗi `Filter` của Servlet container. Spring Security dùng `DelegatingFilterProxy` để kết nối vào `FilterChainProxy`; proxy này chọn `SecurityFilterChain` phù hợp và chạy các bộ lọc xác thực, bảo vệ ứng dụng, phân quyền theo thứ tự của framework. Sau đó, nếu được cho phép, yêu cầu mới đi tiếp đến `DispatcherServlet`/controller.

`SecurityContextHolder` trong ứng dụng Servlet truyền thống mặc định dựa vào `ThreadLocal`. Khi dùng xử lý bất đồng bộ, thread pool hoặc chuyển việc sang thread khác, đừng mặc nhiên cho rằng ngữ cảnh bảo mật tự theo sang mọi thread; dùng cơ chế truyền ngữ cảnh được Spring Security hỗ trợ và kiểm thử thực tế.

Nếu có nhiều `SecurityFilterChain`, `securityMatcher` xác định chain áp dụng cho **toàn bộ yêu cầu**; `requestMatchers` định nghĩa quyền **bên trong chain đã chọn**. Chain đầu tiên phù hợp được áp dụng. Cấu hình chain chỉ khớp `/api/**` mà bỏ quên đường dẫn khác có thể tạo vùng không được bao phủ nếu không có chain dự phòng.

### 4.2. Ví dụ cấu hình Servlet

Dự án ví dụ: Java 17+, Spring Boot với `spring-boot-starter-web`, `spring-boot-starter-security`. Tệp sau là cấu hình chạy được **trong ứng dụng Spring Boot có lớp main và controller tương ứng**; đây không phải một chương trình Java độc lập chạy bằng `javac`/`java`. Hai tài khoản trong bộ nhớ chỉ phục vụ thực hành.

~~~java
package demo.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ServletSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}demo")
                .authorities("report:read")
                .build(),
            User.withUsername("admin")
                .password("{noop}demo")
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Diễn giải:**

- `/public` được truy cập công khai; `GET /reports/**` yêu cầu đúng authority `report:read`; `/admin/**` yêu cầu `ROLE_ADMIN`; mọi request chưa có quy tắc bị từ chối.
- Các bộ quy tắc được xét theo thứ tự: khai báo đường dẫn cụ thể trước `anyRequest()`. `hasAuthority` chỉ kiểm tra quyền đường dẫn; phải bổ sung kiểm tra chủ sở hữu nếu dữ liệu của `/reports/{id}` có tính riêng tư.
- `httpBasic` là một cách xác thực dễ quan sát trong bài tập, **không có nghĩa kiến trúc sản xuất phải dùng HTTP Basic**. Có thể thay bằng session login hoặc OAuth2 Resource Server theo cách client xác thực thực tế.
- `{noop}demo` chỉ giúp người học thử nhanh; sản xuất phải dùng mật khẩu băm an toàn, kho danh tính thích hợp, HTTPS, quản lý bí mật và chính sách đăng nhập.
- Các cấu hình ở đây không tạo controller hay dữ liệu. Nếu chưa cài endpoint, yêu cầu được phép ở lớp bảo mật vẫn có thể trả `404`. Không khẳng định mọi request được phép đều trả `200`.

### 4.3. Những chủ đề Servlet nên học tiếp

1. Chọn đúng `SecurityFilterChain` khi có đường dẫn API và giao diện web; hiểu `@Order`, chain dự phòng và ý nghĩa `securityMatcher`.
2. Hiểu session, đăng nhập/đăng xuất, `SecurityContextRepository`, CSRF và đặc điểm của client trình duyệt.
3. Với API nhận bearer token, xác minh JWT qua issuer/audience/chữ ký, ánh xạ authority và xử lý `401/403`. Không tự viết bộ lọc JWT khi Spring Security Resource Server đáp ứng được nhu cầu.
4. Bảo vệ phương thức dịch vụ bằng `@EnableMethodSecurity`/`@PreAuthorize`; kiểm tra quyền trên dữ liệu thực và thử gọi service qua các entry point.
5. Dùng `MockMvc` + `spring-security-test` để kiểm tra anonymous, người có quyền, người thiếu quyền, các đường dẫn và các HTTP method nhạy cảm.

## 5. Nhánh reactive: WebFlux / luồng xử lý không chặn

### 5.1. Cơ chế cần hiểu

WebFlux xử lý request theo luồng reactive. Spring Security tích hợp bằng `WebFilterChainProxy` và một hoặc nhiều `SecurityWebFilterChain`, khai báo qua `ServerHttpSecurity`. Chính sách HTTP dựa trên `ServerWebExchange`; sự kiện xác thực và phân quyền được kết nối với publisher reactive.

Ngữ cảnh người dùng nằm trong **Reactor Context** và được truy cập qua `ReactiveSecurityContextHolder`, **không dựa vào việc đọc `ThreadLocal` ở thread bất kỳ**. Tránh gọi `block()`, truy vấn JDBC hoặc tác vụ I/O blocking ngay trong luồng xử lý event loop. Nếu thực sự phải dùng thư viện blocking, cần chuyển xử lý sang scheduler phù hợp và đánh giá lại kiến trúc.

### 5.2. Ví dụ cấu hình reactive

Dự án ví dụ khác: Java 17+, Spring Boot với `spring-boot-starter-webflux`, `spring-boot-starter-security`. Tệp cấu hình dưới đây dùng riêng trong ứng dụng WebFlux có lớp main và handler/controller, **không ghép với `ServletSecurityConfig`** ở nhánh Servlet.

~~~java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/reports/**")
                    .hasAuthority("report:read")
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("reader")
                .password("{noop}demo")
                .authorities("report:read")
                .build(),
            User.withUsername("admin")
                .password("{noop}demo")
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Đối chiếu với Servlet:** Cùng một ma trận quyền, nhưng `HttpSecurity / SecurityFilterChain / authorizeHttpRequests / requestMatchers / anyRequest` được thay bởi `ServerHttpSecurity / SecurityWebFilterChain / authorizeExchange / pathMatchers / anyExchange`. Phần mã bên trên vẫn dùng HTTP Basic và mật khẩu thử nghiệm để dễ so sánh; cơ chế xác thực sản xuất được chọn riêng.

### 5.3. Những chủ đề reactive nên học tiếp

1. Thứ tự lựa chọn `SecurityWebFilterChain`, `securityMatcher`, quy tắc `pathMatchers` và thứ tự khai báo chính sách.
2. `ReactiveSecurityContextHolder` và cách Reactor Context đi theo chuỗi `Mono`/`Flux`; sự khác nhau khi code đổi scheduler hoặc tự subscribe.
3. `@EnableReactiveMethodSecurity` với phương thức trả kiểu reactive như `Mono<T>`/`Flux<T>`; kiểm tra quyền không chặn; không gọi repository blocking từ biểu thức kiểm tra quyền.
4. OAuth2 Resource Server reactive, `ReactiveJwtDecoder` và ánh xạ claims thành authorities; phân biệt lỗi thiếu token, token không hợp lệ, token thiếu quyền.
5. `WebTestClient` + bộ công cụ `spring-security-test`, gồm `mockUser()`/`mockJwt()` khi thích hợp, để kiểm thử trên chính pipeline WebFlux.

## 6. Đưa phân quyền xuống lớp nghiệp vụ

Trong Servlet, khai báo `@EnableMethodSecurity`; trong WebFlux, dùng `@EnableReactiveMethodSecurity`. Đặt điều kiện quyền trên phương thức của Spring-managed bean, thường ở lớp service. Ví dụ hai phương thức sau thể hiện **hai biến thể riêng**, mỗi biến thể đặt trong module tương ứng; chúng chỉ minh họa cách dùng annotation, chưa bao gồm controller và kho dữ liệu:

~~~java
// Trong ứng dụng Servlet:
@PreAuthorize("hasAuthority('report:read')")
public String readReport(String id) {
    return "report:" + id;
}

// Trong ứng dụng reactive:
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> readReport(String id) {
    return Mono.just("report:" + id);
}
~~~

Cần import `org.springframework.security.access.prepost.PreAuthorize` và, ở nhánh reactive, `reactor.core.publisher.Mono`; các phương thức trên phải thuộc một Spring bean được quản lý với cơ chế method security đã bật. Lưu ý việc gọi nội bộ từ một phương thức khác của **cùng đối tượng** có thể không đi qua proxy bảo vệ; thiết kế điểm kiểm tra ở ranh giới dịch vụ thực và kiểm thử trường hợp này.

Để giải quyết quyền sở hữu, thay điều kiện chung bằng chính sách có dữ liệu, chẳng hạn `hasAuthority('report:read') and @reportPolicy.canRead(authentication, #id)`. `reportPolicy` phải là Spring bean có phương thức kiểm tra có thật; cần bảo đảm tên tham số `id` được Spring nhận diện (cấu hình biên dịch giữ tên tham số hoặc dùng cách khai báo tham số được hỗ trợ). Cách kiểm tra đúng còn phải xác minh tenant và chủ sở hữu từ nguồn tin cậy, không lấy `ownerId` do client gửi làm bằng chứng. Với reactive, lệnh truy vấn quyền nên ở dạng không chặn và tuân theo cơ chế method security/reactive authorization tương ứng.

Có hai điểm cần phân biệt: **quyền mức endpoint** trả lời “được gọi loại hành động này không?”, còn **quyền mức đối tượng** trả lời “được thao tác chính bản ghi này không?”. Cả hai thường cần thiết, nhất là API đa tenant. Quyền trong token chỉ là đầu vào của quyết định; trạng thái dữ liệu và quy tắc nghiệp vụ có thể thay đổi sau thời điểm phát token.

## 7. Xác thực, token, session và CSRF: chọn theo client

| Tình huống | Hướng phù hợp | Điều phải xác minh |
| --- | --- | --- |
| Giao diện trình duyệt dùng session/cookie | Đăng nhập qua session, bảo vệ CSRF | Cookie, thời gian sống session, CSRF token, logout, CORS/Origin |
| API cho ứng dụng di động hoặc máy chủ, dùng bearer JWT | OAuth2 Resource Server của Servlet hoặc reactive | Chữ ký, issuer, audience, hạn sử dụng, ánh xạ scope/role, lỗi `401/403` |
| Gateway kiểm tra JWT và chuyển tiếp tới dịch vụ | Bảo vệ gateway **và** điểm tin cậy của từng backend | Có thực sự xác thực lại token/xác minh nguồn tin cậy? Có kiểm tra quyền trên tài nguyên ở backend không? |
| Ứng dụng có cả browser lẫn API | Phân tách chain/chính sách và cơ chế xác thực theo đúng endpoint | Không tạo lỗ hổng do chain thiếu phạm vi, CSRF tắt quá rộng hoặc rule thứ tự sai |

**CSRF không phụ thuộc đơn giản vào việc có session phía máy chủ.** Trình duyệt tự gửi cookie và đôi khi cả thông tin xác thực Basic; ứng dụng “stateless” dùng cookie vẫn có thể chịu CSRF. Chỉ cân nhắc bỏ CSRF cho phần API đã chứng minh không dựa trên thông tin xác thực tự động được trình duyệt gửi, và giữ bảo vệ cho những phần khác. CORS giải quyết nguồn gọi qua trình duyệt, **không thay thế xác thực, phân quyền hay CSRF**.

## 8. Kiểm thử phân quyền theo hành vi, không chỉ kiểm tra cấu hình

Sau khi thêm controller/handler có thật cho `GET /public`, `GET /reports/42` và `GET /admin/status`, tạo các trường hợp sau. Trong ví dụ dùng HTTP Basic, một yêu cầu thiếu đăng nhập thường nhận `401`; người đã đăng nhập nhưng không có quyền nhận `403`. Khi dùng form login, yêu cầu chưa xác thực có thể bị chuyển hướng sang trang đăng nhập; cần kiểm tra theo cơ chế xác thực thực tế.

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Anonymous gọi `GET /public` | Qua lớp bảo mật |
| Anonymous gọi `GET /reports/42` | Bị chặn, thường `401` với Basic |
| `reader` gọi `GET /reports/42` | Qua kiểm tra authority `report:read`; kiểm tra tiếp quyền sở hữu |
| `reader` gọi `GET /admin/status` | `403` |
| `admin` gọi `GET /admin/status` | Qua lớp bảo mật |
| `admin` không có `report:read` gọi `GET /reports/42` | `403` theo chính sách đã định, không tự cấp quyền vì là admin |
| Gọi `POST /reports/42` khi chỉ cấp GET | Từ chối; phân biệt với lỗi CSRF nếu request dùng browser/cookie |
| User có quyền đọc báo cáo 42 gọi báo cáo 43 của người khác | `403` hoặc `404` theo hợp đồng che giấu dữ liệu, tuyệt đối không trả dữ liệu |
| User thuộc tenant A gọi dữ liệu tenant B | Từ chối ở chính sách dữ liệu |
| URL không có quy tắc riêng | Từ chối theo `denyAll` |

- **Servlet:** dùng `MockMvc` và `spring-security-test`; kiểm tra `@WithMockUser` hoặc `user()`, `httpBasic()`, `csrf()` theo kịch bản. Có thể dùng `@WithMockUser(authorities = "report:read")` để thử quyền mà không cần tạo tài khoản thật. Đảm bảo filter chain bảo mật được tích hợp vào `MockMvc`.
- **Reactive:** dùng `WebTestClient` đã áp dụng hỗ trợ Spring Security, kết hợp `mockUser()` hoặc `mockJwt()`. Viết ca có quyền, thiếu quyền và không xác thực bằng `exchange().expectStatus()`; riêng quyền dữ liệu cần fixture có nhiều chủ sở hữu/tenant.
- Kiểm tra cả khi route trả lỗi, khi chạy qua async/reactive boundary, và khi method service được gọi từ nơi khác ngoài HTTP. Chỉ nhìn HTTP `200` chưa đủ để kết luận chính sách đúng; cần xác minh tài nguyên trả về và không rò rỉ dữ liệu.

## 9. Lộ trình luyện tập theo dự án

**Bước 1 — Chụp kiến trúc hiện tại:** xác nhận starter web đang dùng, loại controller/handler, cách xác thực, luồng request, loại dữ liệu và hệ thống cấp token. Vẽ sơ đồ đơn giản từ client tới gateway, bộ lọc bảo mật, controller, service, repository.

**Bước 2 — Viết chính sách trước:** tạo ma trận hành động × tài nguyên × principal × tenant; viết ví dụ quyền thiếu và quyền sở hữu. Quyết định phân quyền cần nằm ở đâu để không bị bỏ qua khi có entry point mới.

**Bước 3 — Triển khai đúng runtime:** Servlet dùng `SecurityFilterChain` và nếu cần `@EnableMethodSecurity`; WebFlux dùng `SecurityWebFilterChain` và nếu cần `@EnableReactiveMethodSecurity`. Bắt đầu bằng `denyAll` cho đường dẫn chưa biết, mở đúng các trường hợp theo chính sách.

**Bước 4 — Đổi xác thực demo sang thực tế:** kết nối session hoặc OAuth2 Resource Server/JWT theo client; xác minh issuer/audience, mapping authorities, CSRF, CORS, cách xử lý `401/403` và log không lộ bí mật.

**Bước 5 — Kiểm thử và quan sát:** chạy ma trận tích cực/tiêu cực, thử cross-tenant và object ownership, xác nhận chain được áp dụng, thêm logging/metrics về lỗi xác thực hoặc từ chối quyền với mức thông tin phù hợp. Chỉ hoàn tất khi bài kiểm thử phủ được đường dẫn không định nghĩa và các trường hợp bị từ chối.

### Bài thực hành tổng hợp

Tạo hai ứng dụng nhỏ **độc lập** cùng chính sách `/public`, `GET /reports/{id}`, `/admin/**`: ứng dụng A dùng Spring MVC, ứng dụng B dùng WebFlux. Hai ứng dụng phải có controller/handler thật, ba người dùng thử (anonymous, reader, admin), ít nhất hai bản ghi thuộc hai chủ sở hữu. Áp dụng cùng ma trận quyền, thử bằng `MockMvc` và `WebTestClient`, sau đó mô tả sự khác biệt về cấu hình chain, lưu ngữ cảnh và kiểm thử. Không cần chuyển toàn bộ ứng dụng sản xuất sang reactive chỉ để làm bài tập này.

## 10. Lỗi thường gặp và cách tự kiểm tra

- **Nhầm authentication với authorization:** đã đăng nhập nhưng vẫn xem được tài nguyên người khác. Khắc phục bằng chính sách theo hành động và bản ghi.
- **Nhầm `hasRole` với `hasAuthority`:** `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`; role và JWT scope cần ánh xạ nhất quán.
- **Đặt `permitAll` hoặc matcher rộng trước matcher nhạy cảm:** rule phía sau không còn cơ hội quyết định. Kiểm tra thứ tự và ca thử từ chối.
- **Dùng `securityMatcher` như `requestMatchers`:** chain không áp dụng cho URL nằm ngoài phạm vi. Kiểm tra chain dự phòng và mọi entry point.
- **Tắt CSRF theo thói quen:** vô tình mở đường cho yêu cầu gây thay đổi trạng thái từ trình duyệt. Đánh giá cơ chế credentials trước khi thay đổi.
- **Mang code Servlet sang WebFlux:** sử dụng sai `HttpSecurity`/`SecurityContextHolder` cho luồng reactive. Đổi đúng loại chain và dùng Reactor Context.
- **Blocking trong WebFlux hoặc trong chính sách kiểm tra quyền:** làm nghẽn event loop. Dùng API không chặn hoặc đánh giá lại ranh giới kiến trúc.
- **Tin gateway là lớp bảo vệ duy nhất:** dịch vụ phía sau có thể bị gọi qua luồng khác hoặc lộ dữ liệu qua nghiệp vụ. Định nghĩa rõ ranh giới tin cậy và xác thực/phân quyền thích hợp ở backend.
- **Chỉ kiểm thử ca thành công:** bỏ qua `401`, `403`, quyền sai chủ sở hữu, sai tenant, method sai và URL chưa khai báo.

## 11. Tài liệu chính thức để học sâu

- [Spring Security: Kiến trúc Servlet](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security: Phân quyền yêu cầu HTTP Servlet](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security: Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security: Cấu hình WebFlux](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security: Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security: Kiểm thử Servlet với MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security: Kiểm thử reactive với WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Boot: Khi MVC và WebFlux cùng có trên classpath](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security: Cân nhắc CSRF](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)

Tất cả ví dụ dùng DSL hiện đại; khi áp dụng vào dự án thực tế, chọn trang tài liệu đúng dòng phiên bản Spring Security do Spring Boot BOM quản lý. Kiểm tra các API thay đổi khi nâng cấp, đặc biệt nếu dự án cũ còn dùng `WebSecurityConfigurerAdapter` hoặc `authorizeRequests`.

**Tiêu chí hoàn thành:** người học giải thích được vì sao chọn Servlet hay WebFlux, xác định đúng nơi quyết định quyền, viết và kiểm thử được cấu hình theo runtime đang dùng, đồng thời từ chối chính xác các truy cập ngoài phạm vi cho phép.
