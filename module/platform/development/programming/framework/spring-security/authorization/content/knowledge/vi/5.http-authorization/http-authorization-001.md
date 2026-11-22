# Thiết lập SecurityFilterChain và authorizeHttpRequests trong Spring Security

**`SecurityFilterChain`** xác định chuỗi bộ lọc bảo mật được áp dụng cho một HTTP request trong ứng dụng Servlet. **`authorizeHttpRequests`** là DSL dùng để định nghĩa *request nào được phép truy cập, request nào cần xác thực, role hoặc authority nào*, dựa trên URL, HTTP method và những `RequestMatcher` phù hợp. Đây là lớp bảo vệ ở cửa vào ứng dụng; nếu endpoint xử lý dữ liệu của từng khách hàng, cửa hàng hay tenant, còn cần kiểm tra quyền trên **tài nguyên nghiệp vụ cụ thể** ở service.

Bài này hướng dẫn từ một cấu hình chạy được trong dự án **Spring Boot 3.x / Spring Security 6.x với Java 17+** đến thứ tự match, nhiều filter chain, xác thực, CSRF, CORS, kiểm thử và lỗi thường gặp. Ví dụ Spring là mã để đặt trong một dự án có dependency thích hợp; ví dụ Java độc lập ở cuối bài được chạy bằng JDK thuần.

## 1. Hiểu ba lớp: FilterChainProxy, SecurityFilterChain và authorizeHttpRequests

Một yêu cầu HTTP đi qua cơ chế Servlet filter. Spring Security đăng ký **`DelegatingFilterProxy`** nối đến bean **`springSecurityFilterChain`**, thường là **`FilterChainProxy`**. `FilterChainProxy` duyệt các `SecurityFilterChain` theo thứ tự và chọn **chain đầu tiên có matcher phù hợp request**. Chain được chọn chứa những security filter cho xác thực, CSRF, xử lý ngoại lệ, phân quyền và những khả năng khác đã cấu hình.

Trong chain đó, **`AuthorizationFilter`** thực thi yêu cầu phân quyền từ `authorizeHttpRequests` qua `AuthorizationManager`. Nó dựa trên `Authentication` hiện hành và request đang xử lý; quy tắc phù hợp đầu tiên trong DSL quyết định việc cho phép đi tiếp hoặc từ chối.

~~~text
Client gửi request
       |
       v
Servlet container -> DelegatingFilterProxy
       |
       v
FilterChainProxy
       |
       +-- chọn SecurityFilterChain đầu tiên match request
       |       (securityMatcher, @Order, hoặc match mọi request)
       v
Các security filter trong chain được chọn
       |
       +-- CORS / CSRF / authentication / security context ...
       |
       v
AuthorizationFilter
       |
       +-- authorizeHttpRequests: chọn rule đầu tiên match
       |       (requestMatchers + permitAll/hasRole/hasAuthority/...)
       +-- ALLOW: đi tiếp đến controller
       +-- DENY : ngoại lệ/entry point/handler -> 401, 403, redirect...
~~~

**Hai mức “match” khác nhau:**

| Thành phần | Nó chọn cái gì? | Phạm vi |
| --- | --- | --- |
| `http.securityMatcher(...)` | **SecurityFilterChain** có áp dụng cho request này không? | Ở mức toàn chain. |
| `authorizeHttpRequests(auth -> auth.requestMatchers(...))` | Trong chain đã chọn, **quy tắc phân quyền** nào áp dụng? | Ở mức rule. |
| `anyRequest()` | Tất cả request còn lại **trong chain hiện tại**. | Rule dự phòng của chain. |
| `@Order` trên bean `SecurityFilterChain` | Ưu tiên thử các chain khi có nhiều bean. | Thứ tự chọn chain. |

Nếu chỉ có một `SecurityFilterChain` không gọi `securityMatcher`, matcher mặc định của nó bảo vệ mọi request. **Nếu cấu hình nhiều chain nhưng không có chain nào match một đường dẫn, đường dẫn đó nằm ngoài các security filter của Spring Security.** Bởi vậy việc có fallback chain là một quyết định quan trọng.

## 2. Chuẩn bị dự án và vai trò của bean SecurityFilterChain

Với ứng dụng Spring MVC/Servlet, các dependency Gradle Groovy thông dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **trích đoạn `dependencies`**, không phải file Gradle đầy đủ. Dùng phiên bản do Spring Boot quản lý và dependency phù hợp hệ build của dự án; không gắn lẫn phiên bản Spring Security tùy ý.

Cách cấu hình khuyến nghị của Spring Security 6.x là xuất một bean **`SecurityFilterChain`** bằng `@Bean`, nhận `HttpSecurity`, gọi các DSL cần thiết, rồi **`return http.build()`**. `WebSecurityConfigurerAdapter` của thế hệ cũ đã bị loại bỏ trong Spring Security 6; không sử dụng `extends WebSecurityConfigurerAdapter` hoặc `authorizeRequests`/ `antMatchers` cũ làm nền tảng cho bài này.

Trong Spring Boot, khi người dùng tự định nghĩa bean `SecurityFilterChain`, cấu hình web security mặc định do Boot cung cấp sẽ **nhường cho chain tùy chỉnh**. Điều này không có nghĩa một bean chain tự tạo database người dùng, tự cấp authority hay tự bật JWT: **authentication provider, `UserDetailsService`, token decoder, user store** vẫn phải được cấu hình phù hợp. Đừng nhầm việc có filter chain với việc có tài khoản hợp lệ.

## 3. Cấu hình một SecurityFilterChain: ví dụ nền tảng

Chính sách minh họa của ứng dụng quản lý đơn hàng:

- `GET /api/catalog/**` là dữ liệu catalog công khai.
- `/api/admin/**` chỉ dành cho authority role `ROLE_ADMIN`.
- `GET /api/orders/**` cần quyền `ORDER_READ`.
- `POST /api/orders` cần quyền `ORDER_CREATE`.
- `/api/profile/**` chỉ yêu cầu đã xác thực.
- Những request khác **mặc định từ chối**.

Tạo file **`HttpAuthorizationConfig.java`** trong source set Java của ứng dụng Spring Boot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class HttpAuthorizationConfig {

    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("ORDER_CREATE")
                .requestMatchers("/api/profile/**")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **lớp cấu hình có thể biên dịch khi đặt trong một Spring Boot project với dependency đã nêu**, không phải chương trình Java thuần chạy riêng bằng `javac`; cũng chưa tự cung cấp tài khoản, dữ liệu hay controller. `@EnableWebSecurity` thể hiện rõ ngữ cảnh Servlet security; với ứng dụng Boot có security auto-configuration, annotation này thường không cần khai báo thủ công. `httpBasic(...)` bật cơ chế HTTP Basic để dễ minh họa kết quả unauthenticated; ứng dụng thực tế có thể chọn form login hoặc JWT tùy mô hình.

**Cần đọc kỹ từng dòng:**

1. `@Bean` đăng ký `SecurityFilterChain` với Spring; `HttpSecurity` là bộ dựng chain, còn `http.build()` là kết quả được đưa vào `FilterChainProxy`.
2. `authorizeHttpRequests` khai báo các cặp **matcher → yêu cầu phân quyền**. Match cụ thể đặt trước rule dự phòng.
3. `requestMatchers(HttpMethod.GET, "/api/catalog/**")` chỉ cho phép **GET** phù hợp; `POST` cùng đường dẫn không vì thế được công khai.
4. `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`. Với `hasAuthority("ORDER_READ")`, chuỗi được so **nguyên văn**, không thêm `ROLE_`.
5. `GET /api/orders/42` qua rule `ORDER_READ` chưa đồng nghĩa Alice được xem đơn số 42: service còn phải xét **owner, tenant, trạng thái** nếu nghiệp vụ yêu cầu.
6. `POST /api/orders` có rule riêng `ORDER_CREATE`; ví dụ **không vô tình cho phép** `POST /api/orders/42/cancel` vì chưa khai báo rule cho thao tác hủy.
7. `anyRequest().denyAll()` ngăn request chưa có chính sách rõ ràng được cho qua. Nếu endpoint mới cần quyền, người phát triển phải bổ sung rule đúng vị trí.

**CSRF vẫn được bật theo mặc định** trong chain này. Với HTTP Basic sử dụng từ trình duyệt, không nên vô hiệu hóa CSRF một cách máy móc: trình duyệt có thể tự gửi thông tin xác thực cho request gây thay đổi. Nếu gửi `POST /api/orders` thiếu CSRF token, request có thể trả **403 trước khi đến AuthorizationFilter**, dù user có `ORDER_CREATE`. Đây là **bảo vệ bổ sung**, không phải bug của `hasAuthority`.

Lưu ý rằng `permitAll` chỉ điều khiển **ủy quyền request**. Nó không tạo endpoint catalog và cũng không bắt mọi bộ lọc xác thực bỏ qua dữ liệu đăng nhập sai. Nếu controller chưa có mapping, request dù được phép vẫn có thể trả **404 Not Found**.

## 4. Quy tắc nào thắng? Thứ tự khai báo và HTTP method

Đối với `authorizeHttpRequests`, mỗi request đi theo **matcher phù hợp đầu tiên**. Các matcher **không cộng dồn điều kiện của mọi dòng khớp**. Vì vậy, thứ tự là thành phần **bảo mật** của cấu hình.

Ví dụ dễ sai:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Với `GET /api/admin/users`, dòng `/api/**` đã match trước. Dòng `hasRole("ADMIN")` **không bao giờ được áp dụng** cho đường dẫn đó; bất kỳ người dùng đã xác thực nào cũng vượt qua lớp kiểm tra HTTP này.

Cách chỉnh đúng theo yêu cầu quản trị:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Ở đây `/api/admin/**` được kiểm tra trước, sau đó các API khác mới dùng rule rộng. Trường hợp `/api/admin/**` có nhiều điều kiện (role **và** permission), phải diễn đạt rõ phép AND qua manager/policy phù hợp; hai `requestMatchers` trùng nhau **không tự hợp thành** hai điều kiện.

**HTTP method là một phần matcher**:

| Request | Rule trong cấu hình mục 3 | Hành vi mong đợi của lớp authorization |
| --- | --- | --- |
| `GET /api/catalog/products` | GET catalog → `permitAll` | Cho đi tiếp, kể cả anonymous. |
| `POST /api/catalog/products` | Không có rule công khai cho POST | `denyAll` (các filter khác cũng có thể chặn trước). |
| `GET /api/admin/users` | admin → `hasRole("ADMIN")` | Cần authority `ROLE_ADMIN`. |
| `GET /api/orders/42` | GET orders → `hasAuthority("ORDER_READ")` | Cần `ORDER_READ`; quyền trên Order 42 vẫn phải xét. |
| `POST /api/orders` | POST orders → `hasAuthority("ORDER_CREATE")` | Cần quyền tạo, đồng thời có thể cần CSRF token. |
| `DELETE /api/orders/42` | Không có rule DELETE orders | DENY mặc định; không được suy từ quyền đọc/tạo. |
| `GET /api/profile/me` | profile → `authenticated` | Chỉ yêu cầu đã xác thực. |
| `GET /api/unknown` | `anyRequest().denyAll()` | Từ chối. |

Một matcher như `requestMatchers("/api/orders/**")` **không giới hạn HTTP method** nếu không truyền `HttpMethod`; sử dụng matcher không phương thức khi nghiệp vụ thật sự muốn cùng chính sách cho tất cả phương thức. Tránh vô ý đặt `permitAll()` cho toàn bộ `/api/**` chỉ vì một GET phải công khai.

`anyRequest()` phải là rule cuối của danh sách; thêm rule phía sau nó không có nghĩa vì fallback đã bắt mọi request. Trong ứng dụng có nhiều servlet hoặc servlet path đặc biệt, cần chọn `RequestMatcher` phù hợp với đường dẫn thực tế và kiểm thử matcher thay vì đoán cách khớp URL.

## 5. `securityMatcher` khác `requestMatchers` như thế nào?

Dù tên gần giống nhau, chúng hoạt động ở **hai tầng khác nhau**. Giả sử:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

- `securityMatcher("/api/**")` giới hạn **toàn bộ chain** trong những request thuộc `/api/**`. Các filter của chain này (CSRF, authentication, authorization...) chỉ được sử dụng khi chain được chọn.
- `requestMatchers("/api/admin/**")` chỉ định **rule trong chain**. Request `/api/admin/users` cần role ADMIN.
- `anyRequest().authenticated()` chỉ áp dụng với những request **đã được lọc vào chain này**. Nó không tự bảo vệ `/health`, `/login` hay `/admin` bên ngoài `/api/**`.

Nếu **đây là chain duy nhất** của ứng dụng, các request ngoài `/api/**` có thể không khớp bất cứ `SecurityFilterChain` nào. Hậu quả là **Spring Security không bảo vệ chúng**; đây là lý do cần thiết kế rõ fallback chain khi chia theo vùng URL.

Hãy phân biệt:

~~~text
FilterChainProxy:
  first matching SecurityFilterChain   <-- securityMatcher + @Order
        |
        v
AuthorizationFilter của chain đó:
  first matching authorization rule    <-- requestMatchers + anyRequest
        |
        v
allow / deny
~~~

Một `requestMatchers(...).permitAll()` **không giống** việc bỏ đường dẫn khỏi security filter chain bằng `WebSecurityCustomizer.ignoring()`. `permitAll` vẫn cho request đi qua các filter bảo vệ liên quan như security headers; `ignoring` loại request khỏi hệ thống Spring Security. Đối với tài nguyên tĩnh, phần lớn ứng dụng nên ưu tiên `permitAll` trong chain phù hợp, trừ khi có lý do đo đạc/vận hành cụ thể để bỏ qua filter.

## 6. Nhiều SecurityFilterChain: API Bearer token và website sử dụng form login

Khi hai nhóm request có cách xác thực khác nhau, có thể định nghĩa **nhiều bean `SecurityFilterChain`**. Ví dụ sau là **một cấu hình lựa chọn thay cho cấu hình đơn ở mục 3**; không chép cả hai bộ bean vào cùng ứng dụng mà chưa thiết kế lại thứ tự.

Chính sách ví dụ:

- API `/api/**` dùng **Bearer JWT**, không dùng session để xác thực, có quyền theo scope/authority; cho phép catalog công khai.
- Website bên ngoài `/api/**` dùng **form login** và session.
- `@Order(1)` làm API chain được xét trước; fallback chain `@Order(2)` bao phủ các đường dẫn còn lại.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitHttpSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

**Điều kiện để ví dụ API hoạt động:** cần dependency OAuth2 Resource Server, JWT decoder có cấu hình hợp lệ (chẳng hạn issuer URI/JWK Set URI và cơ chế xác minh issuer, chữ ký, audience theo hệ thống). Authority `SCOPE_admin` là **quy ước mặc định** khi converter đọc scope phù hợp trong JWT, không phải role `ROLE_ADMIN`; nếu token có claim khác, cần converter/ánh xạ thích hợp. Đoạn cấu hình này **không tạo JWT issuer hoặc cấp token**.

Chính sách API trên yêu cầu đăng nhập với các API còn lại, **chưa phải bản phân quyền nghiệp vụ đầy đủ** cho mọi action. Trong thực tế hãy bổ sung các scope/permission riêng theo endpoint, method và tài nguyên, thay `authenticated()` bằng quyền cụ thể khi nghiệp vụ yêu cầu.

**Tại sao chỉ API chain tắt CSRF?** Đây là lựa chọn dành cho **API chỉ nhận Bearer token qua header do client chủ động gửi và không dựa vào credential mà trình duyệt tự gắn vào request**. Nếu API còn nhận cookie phiên, Basic authentication hoặc cơ chế browser tự gửi credential, `STATELESS` **không làm CSRF tự biến mất**; phải giữ hoặc cấu hình bảo vệ CSRF phù hợp. Web chain form login giữ CSRF mặc định cho các thao tác thay đổi trạng thái.

`@Order` chọn **chain**, không định thứ tự `requestMatchers` bên trong chain. Chỉ có **một chain đầu tiên match** được chọn cho request; các chain khác không cùng tham gia áp policy. Fallback chain không gọi `securityMatcher` nên mặc định nhận các request mà API chain không match; nhờ vậy `/web`, `/login`, `/assets/**` không bị bỏ ngoài Spring Security.

`formLogin(form -> form.permitAll())` bảo đảm endpoint đăng nhập do form login sử dụng được phép truy cập dù rule chung yêu cầu authentication. Cách xử lý người chưa đăng nhập ở web chain thường là redirect đến trang login, khác API Bearer thường dùng 401.

## 7. `authorizeHttpRequests` không tự tạo cơ chế authentication

Cấu hình authorization và authentication có nhiệm vụ liên quan nhưng khác nhau:

| Cơ chế | Tác dụng | Ví dụ |
| --- | --- | --- |
| `httpBasic(Customizer.withDefaults())` | Đọc HTTP Basic credentials để xác thực theo các provider hiện có. | Client gửi header `Authorization: Basic ...`. |
| `formLogin(form -> form.permitAll())` | Thiết lập đăng nhập biểu mẫu/phiên theo cấu hình. | Trình duyệt được redirect đến trang login. |
| `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` | Xác minh Bearer JWT, tạo Authentication/authorities từ JWT. | API nhận `Authorization: Bearer ...`. |
| `authorizeHttpRequests(...)` | Kiểm tra request dựa trên `Authentication` và matcher. | `hasRole("ADMIN")`, `authenticated()`. |

Với role, `hasRole("ADMIN")` thường yêu cầu `Authentication.getAuthorities()` chứa **`ROLE_ADMIN`**. Với `hasAuthority("ORDER_READ")`, phải có đúng **`ORDER_READ`**. Nếu người dùng đăng nhập được nhưng bị 403, hãy xem nguồn authority và rule thực tế; đừng vội đổi `denyAll` thành `permitAll`.

Trong ví dụ Basic ở mục 3, chưa có user store cụ thể; dự án cần `UserDetailsService`, `AuthenticationProvider` hoặc thành phần xác thực tương thích, kèm password encoding phù hợp. Không hard-code mật khẩu mẫu vào cấu hình production, không ghi token và password vào log.

Với JWT, claim `scope`/`scp` thường được converter mặc định ánh xạ sang authority `SCOPE_...`, còn một claim tùy biến tên `roles` không tự động trở thành `ROLE_...` trong mọi ứng dụng. Cần định nghĩa hợp đồng ánh xạ từ issuer đáng tin cậy.

`permitAll` không yêu cầu lấy `Authentication` để xét authorization, nhưng **không có nghĩa mọi request kèm credentials sai đều được bỏ qua bởi filter xác thực**. Một request “công khai” nhưng gửi token sai vẫn có thể bị filter xác thực từ chối, tùy chain.

## 8. CSRF, CORS, session và request dispatch vẫn ảnh hưởng kết quả

Một cấu hình HTTP authorization đúng tên quyền vẫn có thể trả 403 hoặc không xử lý được preflight vì các bảo vệ khác.

### CSRF đối với request thay đổi dữ liệu

Trong ứng dụng Servlet, Spring Security bật **CSRF protection theo mặc định** cho các request có khả năng thay đổi trạng thái (thường khác GET/HEAD/OPTIONS/TRACE). Với session cookie hoặc Basic được trình duyệt tự gửi, phải bảo vệ các thao tác thay đổi phù hợp. `POST /api/orders` có `ORDER_CREATE` vẫn có thể bị CSRF từ chối nếu thiếu token.

Khi unit/integration test request POST có principal hợp lệ, hãy phân biệt:

~~~java
// Có CSRF token hợp lệ trong MockMvc:
mvc.perform(post("/api/orders")
        .with(user("writer").authorities(
                new SimpleGrantedAuthority("ORDER_CREATE")))
        .with(csrf()));
~~~

Đây là **đoạn test illustration** cần `MockMvc`, `spring-security-test`, static imports và controller phù hợp; không phải lớp test độc lập. Khi test với CSRF enabled, một 403 từ request thiếu token **không chứng minh** rule `hasAuthority` từ chối đúng.

Chỉ tắt CSRF có mục đích, thường trong **một chain Bearer-only** không có browser auto-credentials. Nếu API hỗ trợ cookie auth hoặc Basic trong trình duyệt, việc tùy tiện tắt CSRF tạo rủi ro ngay cả khi session policy là STATELESS.

### CORS và OPTIONS preflight

Browser có thể gửi **OPTIONS preflight** trước request cross-origin. CORS là cơ chế khác với phân quyền user; preflight thường **không chứa session cookie**. Nếu bảo vệ CORS sai thứ tự, request có thể bị từ chối trước khi endpoint thực được gọi. Cấu hình Spring Security CORS qua `.cors(Customizer.withDefaults())` cùng nguồn `CorsConfigurationSource` hoặc MVC CORS thích hợp; chỉ cho phép origin, methods và headers được tin cậy.

Đừng giải quyết mọi lỗi CORS bằng cách `permitAll("/**")`. CORS không cấp quyền đọc/sửa dữ liệu; request thực vẫn phải đi qua authorization đúng.

### Dispatcher type và trang lỗi

`AuthorizationFilter` có thể đánh giá cả những dispatcher như `REQUEST`, `ERROR`, `FORWARD`. Một ứng dụng render view hoặc error page có thể bị từ chối tại dispatch thứ hai nếu `anyRequest().denyAll()` chặn đường dẫn lỗi. Khi nghiệp vụ cho phép, có thể khai báo rule dispatcher chuyên biệt **trước** các rule khác:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Chỉ thêm `permitAll` cho dispatcher nếu đã đánh giá đúng ứng dụng; đừng xem nó là bắt buộc với mọi dự án. Các quy tắc trong ví dụ mục 3 không được sửa bằng đoạn snippet này trừ khi bạn chủ động thay thế bộ matcher.

### Tài nguyên tĩnh

CSS, JS, hình ảnh và trang công khai cần được permit trong chain phù hợp, ví dụ `requestMatchers("/assets/**").permitAll()`. `permitAll` thường phù hợp hơn `web.ignoring` vì vẫn giữ cơ chế security headers và các filter liên quan. Tùy ứng dụng, phải cho phép cả favicon, error page, login page và static resources thực tế.

## 9. HTTP authorization có giới hạn: ID tài nguyên chưa phải quyền

Một request `GET /api/orders/42` có ba câu hỏi độc lập:

1. **Request có vào chain đã cấu hình không?** Trả lời bởi `securityMatcher` hoặc matcher mặc định của `SecurityFilterChain`.
2. **Người gọi có được sử dụng endpoint đọc đơn không?** Trả lời bởi `authorizeHttpRequests` qua `hasAuthority("ORDER_READ")`.
3. **Người gọi có được xem riêng Order 42 không?** Phụ thuộc vào bản ghi thật: owner, tenant, quan hệ chia sẻ và trạng thái, do service/domain policy kiểm tra.

Bước 2 ALLOW **không suy ra** bước 3 ALLOW. Bỏ bước 3 dễ dẫn đến **IDOR/BOLA**: đổi ID trong URL để xem dữ liệu người khác dù chỉ có quyền đọc chung. Với hệ thống đa tenant, cần lọc truy vấn theo tenant/ownership khi phù hợp và giữ kiểm soát ở các entry point khác ngoài HTTP.

Ví dụ mô hình service:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public OrderDto getOrder(long orderId) {
    Order order = repository.findById(orderId)
            .orElseThrow(NotFoundException::new);
    if (!policy.canRead(currentActor.get(), order)) {
        throw new AccessDeniedException("Access denied");
    }
    return mapper.toDto(order);
}
~~~

Đây là **pseudocode kiểu Java trong Spring-managed service**: `OrderDto`, `repository`, `NotFoundException`, `policy`, `currentActor` và `mapper` là thành phần ứng dụng cần triển khai; không tự biên dịch như chương trình độc lập. `@PreAuthorize` chỉ có tác dụng khi bật method security (`@EnableMethodSecurity`) và lời gọi đi qua interceptor/proxy phù hợp. Nếu không dùng annotation, service vẫn phải tự thực thi policy theo dữ liệu. Với tài nguyên khác tenant, có thể giới hạn truy vấn theo tenant ngay tại repository và dùng chiến lược 403/404 nhất quán để tránh lộ thông tin tồn tại bản ghi.

Trong ví dụ một chain, `AuthorizationFilter` có thể cho qua `GET /api/orders/42` khi có `ORDER_READ`; service sau đó vẫn có quyền từ chối do Alice không sở hữu Order 42.

## 10. Các kết quả HTTP nên mong đợi và cách chẩn đoán

Phản hồi còn phụ thuộc authentication entry point, access denied handler, filter khác và controller:

| Tình huống | Kết quả điển hình | Chú ý |
| --- | --- | --- |
| Anonymous gọi endpoint yêu cầu role/authority trong chain HTTP Basic | **401 Unauthorized** | Thường có header `WWW-Authenticate`. |
| Anonymous gọi endpoint yêu cầu xác thực qua form login | **302 Redirect** tới login | Cấu hình entry point khác có thể trả 401. |
| Người đã xác thực thiếu role/authority | **403 Forbidden** | Cần kiểm tra chuỗi `GrantedAuthority` hiện có. |
| Có role, đúng matcher nhưng POST thiếu CSRF token | **403 Forbidden** | Do CSRF filter, không nhất thiết do authorizeHttpRequests. |
| `permitAll`, nhưng không tồn tại controller/handler | **404 Not Found** | Cho qua security không đồng nghĩa endpoint tồn tại. |
| Không có `SecurityFilterChain` nào match request | **Ngoài phạm vi Spring Security** | Có nguy cơ endpoint không được filter bảo vệ. |
| Manager cho phép tầng HTTP nhưng service từ chối owner/tenant | Thường **403/404** | Tuân theo mapping ngoại lệ và tránh lộ dữ liệu. |

Khi điều tra một ca 403 hoặc 401, lần lượt kiểm tra: **chain nào match? matcher phân quyền nào thắng? authentication đã được tạo chưa? có authorities nào? filter CSRF/CORS có chặn không? service policy có từ chối không?** Nếu có nhiều chain, bước xác minh đầu tiên là **`securityMatcher` và `@Order`**, vì chain sai kéo theo mọi rule bên trong sai bối cảnh.

Có thể bật log DEBUG cho `org.springframework.security` trong môi trường thử nghiệm nhằm quan sát filter chain và quyết định; cần tránh đưa thông tin nhạy cảm lên hệ thống log, đặc biệt token và credentials. Không bật log mức cao của toàn bộ request bảo mật ở production chỉ để tìm một lỗi matcher.

## 11. Kiểm thử SecurityFilterChain bằng MockMvc

Khi dùng Spring Boot Test và `spring-security-test`, có thể test **các trường hợp DENY ngay tại HTTP filter** mà không phụ thuộc controller. Ví dụ các test sau giả định dự án Spring Boot có bean chain ở mục 3:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void orderReaderCannotOpenAdmin() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void orderReaderCannotDeleteOrder() throws Exception {
        mvc.perform(delete("/api/orders/42")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ORDER_READ")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }
}
~~~

Các test này **phụ thuộc dự án Spring Boot và dependencies test**, không biên dịch một mình bằng JDK. Trường hợp đầu giả định Basic entry point ở mục 3; với form login, mong đợi có thể là redirect thay vì 401. Test xóa **có CSRF token hợp lệ** để chứng minh `anyRequest().denyAll()` mới là lý do từ chối, tránh test vô tình pass vì thiếu CSRF.

Muốn chứng minh ca **ALLOW**, cần có controller test thực sự và assert cả HTTP status lẫn body phù hợp: bộ lọc cho qua rồi controller có thể trả 200, 404 hoặc lỗi nghiệp vụ. Cũng nên test request method không được khai báo, quyền đúng/sai, rule cụ thể so với rule rộng và quan hệ owner/tenant ở tầng service.

Nếu cần test API Bearer từ ví dụ nhiều chain, dùng `jwt()` trong Spring Security Test hoặc token hợp lệ trong integration test, kiểm tra `SCOPE_...` đúng converter đang cấu hình. Một `@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN`, khác `@WithMockUser(authorities = "ADMIN")` với chuỗi `ADMIN` nguyên văn.

## 12. Ví dụ Java 17+ độc lập: mô phỏng thứ tự rule

Ví dụ sau **không phải hiện thực của Spring Security**, mà là mô hình nhỏ minh họa **first matching rule** và cách `hasRole` khác `hasAuthority`. Điều kiện đường dẫn cố ý đơn giản bằng `startsWith`, vì vậy đừng dùng chúng thay cho `RequestMatcher` thật khi triển khai bảo mật. Để giống chương trình mục 3, mô hình lần lượt kiểm tra catalog, admin, GET orders, POST orders, rồi DENY mặc định.

Lưu đúng tệp **HttpRuleOrderDemo.java**:

~~~java
import java.util.Set;

public class HttpRuleOrderDemo {
    record Identity(boolean authenticated, Set<String> authorities) {}

    static boolean hasAuthority(Identity who, String authority) {
        return who != null && who.authenticated()
                && who.authorities().contains(authority);
    }

    static boolean hasRole(Identity who, String role) {
        return hasAuthority(who, "ROLE_" + role);
    }

    static boolean allowed(String method, String path, Identity who) {
        if (method.equals("GET") && path.startsWith("/api/catalog/")) {
            return true;
        }
        if (path.startsWith("/api/admin/")) {
            return hasRole(who, "ADMIN");
        }
        if (method.equals("GET") && path.startsWith("/api/orders/")) {
            return hasAuthority(who, "ORDER_READ");
        }
        if (method.equals("POST") && path.equals("/api/orders")) {
            return hasAuthority(who, "ORDER_CREATE");
        }
        return false;
    }

    public static void main(String[] args) {
        Identity guest = new Identity(false, Set.of());
        Identity reader = new Identity(true, Set.of("ORDER_READ"));
        Identity creator = new Identity(true, Set.of("ORDER_CREATE"));
        Identity admin = new Identity(true, Set.of("ROLE_ADMIN"));

        System.out.println("Public catalog: "
                + allowed("GET", "/api/catalog/item-1", guest));
        System.out.println("Anonymous order: "
                + allowed("GET", "/api/orders/42", guest));
        System.out.println("Reader can read: "
                + allowed("GET", "/api/orders/42", reader));
        System.out.println("Reader cannot admin: "
                + allowed("GET", "/api/admin/users", reader));
        System.out.println("Admin can admin: "
                + allowed("GET", "/api/admin/users", admin));
        System.out.println("Reader cannot create: "
                + allowed("POST", "/api/orders", reader));
        System.out.println("Creator can create: "
                + allowed("POST", "/api/orders", creator));
        System.out.println("Unknown path denied: "
                + allowed("GET", "/unlisted", admin));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac HttpRuleOrderDemo.java
java HttpRuleOrderDemo
~~~

Kết quả chuẩn:

~~~text
Public catalog: true
Anonymous order: false
Reader can read: true
Reader cannot admin: false
Admin can admin: true
Reader cannot create: false
Creator can create: true
Unknown path denied: false
~~~

Những kết quả quan trọng:

- Catalog công khai cho anonymous đi tiếp vì rule đầu tiên cho phép GET catalog.
- `reader` có `ORDER_READ` nhưng không có `ROLE_ADMIN`, vì vậy không vào `/api/admin/**`.
- `creator` có `ORDER_CREATE` nhưng không tự có `ORDER_READ`; hai thao tác phải được phân quyền riêng.
- Đường dẫn không có rule được **từ chối**, kể cả người có `ROLE_ADMIN`, vì fallback là DENY chứ không phải “ADMIN mặc nhiên truy cập mọi URL”.

Mô hình chỉ xét quyết định authorization, **không** mô phỏng CSRF, xác thực Basic/JWT, Servlet dispatch hoặc việc một người có quyền trên từng bản ghi cụ thể. Phân biệt điều này khi dùng stdout để hiểu ứng dụng Spring.

## 13. Lỗi cấu hình thường gặp và cách sửa

1. **Đặt `authenticated()` cho `/api/**` trước `hasRole()` của `/api/admin/**`.** Rule rộng nuốt rule hẹp. → Đưa rule cụ thể lên trước; test request admin với account bình thường.
2. **Chỉ tạo chain cho `/api/**`, không có fallback.** URL khác không được Spring Security bảo vệ. → Thêm chain cuối match mọi request theo chính sách rõ ràng.
3. **Nhầm `securityMatcher` và `requestMatchers`.** Một cái chọn toàn chain, một cái chọn rule trong chain. → Viết bảng URL → chain → rule để review.
4. **Dùng `hasAuthority("ADMIN")` khi thực tế cấp `ROLE_ADMIN`.** Mặc định `hasRole("ADMIN")` mới xét `ROLE_ADMIN`. → Kiểm tra `Authentication.getAuthorities()` và thống nhất mapper.
5. **Cho phép tất cả HTTP method của endpoint chỉ vì GET cần công khai.** → Dùng matcher có `HttpMethod` và chính sách riêng cho POST/PUT/DELETE.
6. **Quên `http.build()` hoặc không đăng ký bean `SecurityFilterChain`.** → Trả kết quả xây chain từ phương thức `@Bean`, đảm bảo Spring Boot tìm được configuration.
7. **Tưởng cấu hình authorization tự bật authentication mong muốn.** → Cấu hình `httpBasic`, `formLogin`, OAuth2/JWT và nguồn danh tính/authority tương ứng.
8. **Tắt CSRF cho mọi API vì thấy 403.** → Xác định request có dùng cookie/Basic hay browser auto-credentials không; chỉ điều chỉnh với mô hình cụ thể.
9. **Bỏ qua OPTIONS/CORS preflight.** → Cấu hình CORS đúng nguồn và thứ tự, không mở toàn bộ endpoints.
10. **Dùng `WebSecurityCustomizer.ignoring` cho dữ liệu cần policy.** Request bỏ qua filter security. → Dùng `permitAll` khi chỉ cần công khai nội dung mà vẫn giữ bảo vệ của chain.
11. **Chỉ kiểm tra URL, không kiểm tra bản ghi.** `ORDER_READ` chưa chứng minh sở hữu Order 42. → Thực thi policy tenant/owner ở service và query.
12. **Bỏ qua dispatcher ERROR/FORWARD và thứ tự nhiều chain.** → Test luồng dispatch và đường dẫn ngoài `securityMatcher`, có fallback thích hợp.
13. **Xem 403 là bằng chứng duy nhất cho authorization đúng.** → CSRF hoặc authentication mapping khác cũng có thể gây lỗi; test với security context và CSRF phù hợp.
14. **Dùng cấu hình API cũ của Spring Security 5** như `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`. → Với Spring Security 6, dùng bean `SecurityFilterChain` và `authorizeHttpRequests`; khi nâng lên dòng mới hơn, kiểm tra migration guide của phiên bản đang chạy.

## 14. Checklist khi đưa một endpoint mới vào cấu hình

Trước khi mở endpoint như `POST /api/orders/{id}/cancel`, hãy trả lời được:

1. **Chain nào bảo vệ đường dẫn đó?** Nếu có `securityMatcher`, có chắc URL và HTTP method thực tế match không? Có fallback khi không match?
2. **Rule nào thắng trong `authorizeHttpRequests`?** Rule cụ thể có đứng trước rule rộng? `anyRequest` có chặn phần còn lại?
3. **Cần xác thực kiểu gì?** Session, Basic, Bearer JWT hay một cơ chế khác? Principal và authorities đến từ nguồn tin cậy nào?
4. **Cần authority nào?** `ORDER_CANCEL`, `ROLE_ADMIN` hay tổ hợp có chủ đích? Tránh dùng quyền đọc để cho phép thay đổi dữ liệu.
5. **Cần điều kiện tài nguyên nào?** Chủ sở hữu, tenant, trạng thái đơn, hạn mức? Đã thực thi ở service/policy chưa?
6. **Cần CSRF và CORS như thế nào?** Có browser tự gửi cookie/Basic không? Preflight có được xử lý đúng không?
7. **Xảy ra gì khi từ chối?** API trả 401/403/404 theo thiết kế, frontend nhận redirect hay JSON? Có lộ sự tồn tại bản ghi tenant khác không?
8. **Test nào chứng minh an toàn?** Anonymous, role/permission sai, method sai, ID khác, tenant khác, CSRF thiếu, chain fallback và tình huống đổi thứ tự matcher.

**Điểm cốt lõi:** `SecurityFilterChain` xác định **những bộ lọc bảo mật nào chạy đối với request**; `authorizeHttpRequests` xác định **quy tắc phân quyền HTTP nào được áp dụng bên trong chain đó**. Thiết kế an toàn đòi hỏi **chain chọn đúng, rule cụ thể trước rule tổng quát, mặc định từ chối, cơ chế xác thực tương ứng và kiểm tra quyền trên bản ghi ở service khi cần**.

### Tài liệu tham khảo

- [Spring Security — Java Configuration và Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Architecture và Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
