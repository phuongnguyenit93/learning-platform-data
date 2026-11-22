# Nhiều SecurityFilterChain, @Order và rủi ro request không khớp chain nào

> **Module:** Spring Security – authorization  
> **Nhóm:** Phân quyền HTTP  
> **Trọng tâm:** `FilterChainProxy` lựa chọn **một** `SecurityFilterChain` theo `RequestMatcher` và thứ tự `@Order`; khác biệt giữa `securityMatcher` và `requestMatchers`; hậu quả khi request không khớp bất kỳ chain nào; cấu hình fallback và bộ kiểm thử chống lọt URL.

## 1. Vấn đề cần nhận ra ngay

Một ứng dụng Java có ba nhóm endpoint:

- `/api/**`: API của khách hàng, dùng HTTP Basic hoặc Bearer token.
- `/admin/**`: API quản trị, yêu cầu quyền `ROLE_ADMIN`.
- `/public/**`: nội dung công khai; ngoài ra có `/actuator/**`, `/error` và các URL ít được chú ý.

Nhóm phát triển cấu hình:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"));
    return http.build();
}
~~~

Nhìn qua tưởng đã có “phân quyền cho API” và “phân quyền cho admin”. Nhưng **request `GET /public/status` không khớp chain nào**. Nếu ứng dụng còn controller trả dữ liệu tại đường đó, nó có thể thực thi mà **không đi qua các filter bảo mật thuộc Spring Security `SecurityFilterChain`**.

Đây không phải hành vi `denyAll()` hay `authenticated()`. Nó là **lỗ hổng bao phủ filter chain**: quy tắc phân quyền HTTP không hề được đánh giá vì request không được giao cho một chain phù hợp.

Nguyên tắc chính của bài:

**Nhiều `SecurityFilterChain` không tự tạo thành một lưới bảo vệ toàn bộ URL. Phải chứng minh từng request quan trọng khớp đúng chain và có chain fallback bảo vệ các request còn lại.**

## 2. Ba tầng chọn lựa thường bị đánh đồng

Để hiểu và debug một yêu cầu, tách ba câu hỏi:

| Tầng | Ai quyết định? | Câu hỏi | Ví dụ |
|---|---|---|---|
| **Chọn chain** | `FilterChainProxy` dựa trên `SecurityFilterChain.matches(request)` | Request được xử lý bởi chain nào? | `/api/orders` thuộc API chain |
| **Chọn rule trong chain** | `AuthorizationManager` được cấu hình bởi `authorizeHttpRequests` | Trong chain đã chọn, rule URL/method đầu tiên nào khớp? | `GET /api/reports/**` cần `reports:read` |
| **Thực thi filter và nghiệp vụ** | Các filter trong chain + controller/service | Authentication, CSRF, authorization, method policy, owner/tenant được xử lý ra sao? | User thiếu quyền nhận từ chối |

Hình dung:

~~~text
HTTP request
     |
     v
DelegatingFilterProxy / springSecurityFilterChain
     |
     v
FilterChainProxy
     |
     +--> Chain @Order(1): securityMatcher("/api/**") ?
     |             |
     |          khớp --> CHỌN chain API; DỪNG chọn chain
     |
     +--> Chain @Order(2): securityMatcher("/admin/**") ?
     |             |
     |          khớp --> CHỌN chain ADMIN; DỪNG chọn chain
     |
     +--> Chain @Order(99): default matcher (mọi request)?
                   |
                khớp --> CHỌN chain FALLBACK; DỪNG chọn chain
                                 |
                                 v
                  Filters của chain được chọn
                                 |
                                 v
                  authorizeHttpRequests rule
                                 |
                                 v
                         Controller/service
~~~

Chỉ **chain đầu tiên khớp** được thực thi. Spring Security **không nối bộ lọc của chain A với chain B**, không lấy rule cuối chain A rồi tiếp tục rule của chain B, và không tự áp dụng cả hai security configurations lên cùng request.

Nếu không có fallback và cả A lẫn B không khớp, `FilterChainProxy` không có `SecurityFilterChain` tương ứng để áp dụng cho request đó. Các bộ lọc khác của ứng dụng, reverse proxy hoặc cơ chế bảo vệ khác vẫn có thể tồn tại, nhưng **không được coi là Spring Security authorization tự động**.

## 3. `SecurityFilterChain` là gì?

Mỗi `SecurityFilterChain` xác định hai thứ:

1. **Một `RequestMatcher` ở cấp chain**: request nào thuộc phạm vi chain?
2. **Danh sách security filters** cần chạy khi chain được chọn: ví dụ các filter liên quan security context, authentication, CSRF, exception translation, authorization; chi tiết phụ thuộc từng cấu hình.

Các chain có thể khác nhau về cơ chế đăng nhập, quản lý session, CSRF, CORS, authentication entry point, exception handling, chính sách URL và custom filters.

Ví dụ kiến trúc:

~~~text
Chain A: /api/**
    JWT authentication (nếu cấu hình)
    CSRF strategy dành cho API
    AuthorizationFilter: token scope / quyền API

Chain B: /admin/**
    HTTP Basic hoặc form login
    CSRF strategy dành cho admin
    AuthorizationFilter: ROLE_ADMIN

Chain C: mọi request còn lại
    Public endpoints được permitAll
    Những URL không nhận diện được: denyAll
~~~

**Không có bước “chain A cho qua thì chain B kiểm tra thêm”.** Chain được chọn là vùng bảo vệ của chính nó. Đây vừa là lợi ích (tách cơ chế xác thực theo khu vực), vừa là nguy cơ (cấu hình thiếu chain, thứ tự sai, hoặc một chain rộng che chain hẹp).

## 4. `securityMatcher` và `requestMatchers` khác nhau thế nào?

Đây là điểm quan trọng nhất khi review code:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

- `http.securityMatcher("/api/**")`: **cổng vào cấp chain**. Request bên ngoài `/api/**` không vào chain này; các rule phía trong **không có cơ hội chạy**.
- `authorizeHttpRequests(...).requestMatchers("/api/public/**")`: **rule bên trong chain**. Rule chỉ áp dụng nếu request đã khớp chain.
- `anyRequest().authenticated()`: bắt các request **còn lại bên trong chain đã chọn**, không tự bảo vệ toàn bộ ứng dụng.

So sánh:

| Cấu hình | Phạm vi | Mục đích |
|---|---|---|
| `http.securityMatcher("/api/**")` | Toàn bộ chain | Chọn bộ filter và chính sách dành cho `/api/**` |
| `http.authorizeHttpRequests(...requestMatchers("/api/admin/**"))` | Rule trong chain | Chọn điều kiện quyền cho request khớp URL/method |
| `anyRequest().denyAll()` trong API chain | Phần còn lại **của API chain** | Từ chối API không khớp rule cụ thể |
| Chain không khai báo `securityMatcher` | Mặc định khớp mọi request | Phù hợp làm fallback cuối |

**Bẫy thường gặp:** đặt `anyRequest().denyAll()` trong chain có `securityMatcher("/api/**")` rồi nghĩ mọi URL không thuộc API sẽ bị từ chối. Thực tế một request `/debug/config` không vào chain API; fallback nội bộ API không thể chặn nó.

### 4.1. Phạm vi chain và phạm vi rule phải nhất quán

Ví dụ sau chứa rule **không bao giờ được sử dụng**:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

Đường `/admin/**` ở ngoài `/api/**`, vì vậy rule role ADMIN không bảo vệ `/admin/**`. Nó không khiến phạm vi `securityMatcher` tự mở rộng.

Đặt rule admin trong chain có thể nhận request `/admin/**`; hoặc mở rộng matcher cấp chain một cách có chủ đích và kiểm tra lại thứ tự, chứ không chỉ thêm `requestMatchers` bên trong.

### 4.2. “Không gọi `securityMatcher`” là gì?

Mặc định `HttpSecurity` tạo chain với matcher bao phủ mọi request. Việc đặt `securityMatcher(...)` thay thế phạm vi mặc định đó bằng phạm vi do bạn chọn. Vì vậy một bean `SecurityFilterChain` **không gọi `securityMatcher`** là lựa chọn điển hình để làm catch-all. Không nên hiểu “không khai báo matcher = chain không khớp cái gì”.

## 5. `@Order` là thứ tự ưu tiên giữa các chain

Spring Security xem xét nhiều chain theo **thứ tự ưu tiên**; `@Order` trên các bean chain giúp chỉ định thứ tự đó. Số thứ tự thấp hơn có mức ưu tiên cao hơn:

~~~java
@Bean
@Order(1)
SecurityFilterChain highPriority(HttpSecurity http) throws Exception {
    // ...
}

@Bean
@Order(2)
SecurityFilterChain lowerPriority(HttpSecurity http) throws Exception {
    // ...
}
~~~

Nếu request khớp cả hai, chain `@Order(1)` được chọn; chain `@Order(2)` **không được gọi thêm**.

Ví dụ:

~~~text
@Order(1)  securityMatcher("/api/admin/**")
@Order(2)  securityMatcher("/api/**")
@Order(99) không đặt securityMatcher  (catch-all)

GET /api/admin/users --> chain 1
GET /api/orders      --> chain 2
GET /about           --> chain 99
~~~

### 5.1. Sai thứ tự tạo lỗ hổng chức năng

~~~java
// SAI khi /api/admin/** bắt buộc phải có role ADMIN.
@Bean
@Order(1)
SecurityFilterChain broadApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"));
    return http.build();
}
~~~

`GET /api/admin/users` khớp chain 1 trước → rule chỉ yêu cầu đăng nhập. **Chain 2 dù có `hasRole("ADMIN")` cũng không chạy.** Đây là một trường hợp lỗ hổng **vertical privilege escalation** do chain ưu tiên sai.

Sửa bằng cách đặt chain hẹp và nhạy cảm lên trước:

~~~text
@Order(1) /api/admin/**  --> hasRole("ADMIN")
@Order(2) /api/**        --> quy tắc API thông thường
@Order(99) mọi URL khác  --> public allowlist, còn lại denyAll
~~~

### 5.2. Catch-all đặt quá sớm cũng có thể che mọi chain

~~~java
// SAI: chain này khớp tất cả trước chain quản trị.
@Bean
@Order(1)
SecurityFilterChain earlyFallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().permitAll());
    return http.build();
}
~~~

Nếu có thêm chain admin `@Order(2)`, chain admin có thể không bao giờ được dùng, vì fallback chọn mọi request ở thứ tự 1.

**Kết luận:** “có fallback” chưa đủ; **fallback phải được xét sau** các chain chuyên biệt. Nếu fallback ở cuối dùng `denyAll`, nó là mạng an toàn cho URL không được khai báo; nếu fallback `permitAll` ở đầu, nó có thể vô hiệu hóa toàn bộ thiết kế.

### 5.3. Không dựa vào thứ tự tình cờ

Không dựa vào thứ tự định nghĩa method trong file hoặc thứ tự Spring quét class để suy ra ưu tiên. Với nhiều chain có matcher giao nhau, nên khai báo `@Order` rõ ràng, tránh trùng priority và có integration test chứng minh chain mong muốn được chọn.

Một chain không có `@Order` thường được xét sau các bean có priority được gán. Dù vậy, **đặt `@Order(99)` rõ ràng** cho fallback có thể làm thiết kế dễ review hơn nếu mọi chain ưu tiên trước được kiểm soát. Trường hợp nhiều cấu hình từ thư viện/starter cũng cần kiểm tra bean thực tế.

## 6. Rủi ro lớn nhất: request không khớp bất kỳ chain nào

Xét cấu hình:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain admin(HttpSecurity http) throws Exception {
    http.securityMatcher("/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"));
    return http.build();
}
~~~

Phân tích:

| Request | Chain khớp | Hệ quả |
|---|---|---|
| `GET /api/orders` | API | HTTP authorization yêu cầu đăng nhập |
| `GET /admin/users` | ADMIN | HTTP authorization yêu cầu `ROLE_ADMIN` |
| `GET /public/news` | **Không có** | Không được bảo vệ bởi một Spring Security `SecurityFilterChain` phù hợp |
| `GET /actuator/env` | **Không có** | Rất nguy hiểm nếu endpoint được công khai và thiếu lớp bảo vệ khác |
| `POST /internal/recalculate` | **Không có** | Có thể chạm controller dù security rule không hề chạy |
| `GET /error` | **Không có** | Behavior xử lý lỗi có thể khác dự định |

**Điểm quan trọng:** “không có chain” **không** nhất thiết trả 200; route có thể không tồn tại và trả 404, reverse proxy có thể chặn, hoặc custom servlet filter có thể bảo vệ. Nhưng nếu controller thực sự tồn tại và không có bảo vệ nào khác, endpoint có thể truy cập mà không cần quyền Spring Security.

Khi thiếu chain, các bảo vệ thuộc Spring Security filter chain như authentication, HTTP authorization, CSRF và việc thiết lập security headers bởi chain đó cũng không được áp dụng theo cách thông thường. Đây là **lỗ hổng diện bao phủ** và không thể khắc phục chỉ bằng cách thay `hasRole` trong các chain hiện hữu.

### 6.1. Vì sao `anyRequest().denyAll()` bên trong API chain không cứu được?

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().denyAll());
~~~

`GET /admin/users` chưa bao giờ khớp `/api/**`, nên không vào `AuthorizationFilter` của API chain. `anyRequest` chỉ có ý nghĩa **sau** khi chain đã được chọn.

Muốn bao phủ toàn bộ ứng dụng, cần có chain phù hợp với những URL còn lại, điển hình là **một fallback không có `securityMatcher`**.

### 6.2. Không nhầm với `web.ignoring()`

`web.ignoring()` là cấu hình chủ động bỏ qua security filtering cho matcher được chọn; `permitAll()` thì **giữ request đi qua security chain** nhưng không yêu cầu authority ở rule HTTP.

- **Không chain khớp**: có thể là lỗi cấu hình ngoài ý muốn.
- **`web.ignoring()`**: chủ động loại một URL khỏi Spring Security filters, cần đánh giá rủi ro.
- **`permitAll()`**: public ở cấp authorization rule, vẫn nằm trong chain.

Với phần lớn tài nguyên tĩnh/public, tài liệu Spring Security khuyến nghị ưu tiên `permitAll` thay vì loại khỏi security chain, để giữ các cơ chế như security headers và các filter thích hợp.

## 7. Mẫu cấu hình ba chain có fallback an toàn

Đây là **mẫu tích hợp Spring Boot 3.x / Spring Security 6.x ở Servlet stack**, không phải chương trình Java chạy độc lập với JDK. Cần có dependencies Spring Web và Spring Security, cấu hình user/authentication provider và controller thật.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class MultiChainSecurityConfig {

    // Chain 1: API thông thường.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Chain 2: khu vực quản trị.
    @Bean
    @Order(2)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Chain 3: không có securityMatcher => khớp mọi request
    // chưa được hai chain trước nhận.
    @Bean
    @Order(99)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**")
                    .permitAll()
                .anyRequest().denyAll()
        );

        return http.build();
    }
}
~~~

### Phân tích từng phần

- **API chain** chỉ nhận `/api/**`. Endpoint báo cáo GET cần authority chính xác `report:read`; API GET public không cần login ở rule HTTP; các API khác trong phạm vi `/api/**` cần xác thực. Để an toàn hơn, các API nhạy cảm khác nên có permission riêng chứ không chỉ `authenticated()`.
- **ADMIN chain** chỉ nhận `/admin/**`, yêu cầu `ROLE_ADMIN` theo quy ước `hasRole("ADMIN")` mặc định. Có role ADMIN không tự chứng minh quyền trên tài nguyên cụ thể.
- **FALLBACK chain** không khai báo `securityMatcher` nên mặc định nhận mọi URL còn lại; công khai GET `/public/**`, tất cả URL còn lại bị `denyAll()`.
- **Thứ tự** `@Order(1)`, `@Order(2)`, `@Order(99)` đảm bảo fallback không che API/admin.
- **Không có trống vùng bao phủ** tại cấp SecurityFilterChain khi cả ba bean được đăng ký đúng. Tuy nhiên phải kiểm thử thực tế: có thể có chain từ thư viện cấu hình khác, nhiều servlet context hoặc path rewriting.
- **Mỗi chain có bộ filter riêng**. Chúng không tự kế thừa cấu hình authentication của chain khác. Chain fallback chỉ chứa những cơ chế được cấu hình/mặc định tại chain đó; không mặc nhiên có HTTP Basic do hai chain trước khai báo.

**Quan trọng:** đây là ví dụ đặt quy tắc cho kiến trúc đã biết, không phải bộ cấu hình có thể dán vào mọi dự án. HTTP Basic phải dùng HTTPS, credential provider đáng tin và mật khẩu được mã hóa đúng. Ứng dụng dùng Bearer JWT cần thay/bổ sung `oauth2ResourceServer().jwt()` ở đúng chain, xác minh issuer/audience/scope và quản lý session/CSRF đúng loại client. Không nên tắt CSRF toàn cục để “giúp ví dụ chạy”.

### 7.1. `@Order(99)` không phải “độ ưu tiên tuyệt đối”

Nếu có bean chain khác `@Order(100)`, nó sẽ bị fallback bao phủ trước; vì vậy không nên cho bean mới đứng sau catch-all. Cách đặt thứ tự là một **contract của toàn bộ ứng dụng**, cần được kiểm soát khi thêm module.

Trong dự án nhỏ, một fallback **không có `@Order`** thường được Spring Security xét sau các chain có order cụ thể. Dù dùng cách nào, cần có test chống trường hợp một chain mới bị che.

## 8. Bảng định tuyến: từng URL được bảo vệ ở đâu?

Với cấu hình ba chain vừa nêu, giả định ứng dụng dùng các matcher path thông thường và method tương ứng:

| Request | Chain thắng | HTTP rule trong chain | Ghi chú |
|---|---|---|---|
| `GET /api/public/faq` | API | `permitAll` | Vẫn có filter của API chain |
| `GET /api/reports/2026` | API | `hasAuthority("report:read")` | Chưa thay thế kiểm tra dữ liệu báo cáo |
| `POST /api/reports` | API | `authenticated` | Không dùng GET-specific rule; cần xem có nên yêu cầu permission viết |
| `GET /admin/users` | ADMIN | `hasRole("ADMIN")` | Chain API không nhận |
| `GET /public/about` | FALLBACK | `permitAll` | Không cần login ở rule HTTP |
| `POST /public/about` | FALLBACK | `denyAll` | Vì chỉ GET được public |
| `GET /actuator/health` | FALLBACK | `denyAll` | Muốn mở health, thêm rule hẹp theo nhu cầu |
| `GET /error` | FALLBACK | `denyAll` | Cần đánh giá behavior `ERROR` dispatcher |
| `GET /unknown` | FALLBACK | `denyAll` | Đóng URL chưa khai báo |
| `GET /api` | **Cần kiểm thử** | Tùy semantics matcher cụ thể | `/api` và `/api/` có thể khác nhau theo cấu hình |

Bảng chỉ thể hiện **chain selection + rule authorization**. Nó không cam kết HTTP 200, 401, 403 hay 404. Kết quả cuối còn phụ thuộc controller, authentication entry point, CSRF, CORS và policy nghiệp vụ.

**Điểm cần tránh:** giả sử `/api/**` luôn khớp `/api`, `/api/`, trailing slash, URL encoded hoặc servlet context path theo cùng cách ở mọi phiên bản/cấu hình. Matcher implementation (MVC/Ant/PathPattern, servlet mapping, firewall) có thể khác. Hãy test các đường biên có thật trong hệ thống.

## 9. Một sai lầm khác: fallback có rule, nhưng nằm trong chain sai

Xét code:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll());
    return http.build();
}
~~~

Trông có `/public/**` và `denyAll`, nhưng:

- `/public/**` **không thuộc** `/api/**` nên rule `permitAll` không có tác dụng.
- Các URL `/admin/**`, `/internal/**` và `/public/**` đều có nguy cơ **không có chain** nếu đây là chain duy nhất.
- `anyRequest().denyAll()` chỉ chặn các request `/api/**` còn lại.

Muốn public route được xử lý với header/filter bảo mật phù hợp, hãy đặt rule vào **fallback không giới hạn chain** hoặc một public chain riêng được chọn bởi matcher thích hợp, đồng thời vẫn giữ fallback toàn cục.

## 10. Các endpoint do filter tự cung cấp: `/login` và `/logout`

Một chi tiết dễ bỏ qua khi thu hẹp chain:

~~~java
http.securityMatcher("/secured/**")
    .formLogin(Customizer.withDefaults());
~~~

`formLogin` mặc định có thể thiết lập các endpoint như `GET /login` và `POST /login`. Nhưng chain chỉ nhận `/secured/**`, nên những URL `/login` **không khớp chain này**. Trang login hoặc endpoint xử lý login do security filter cung cấp có thể **không tồn tại** trong phạm vi xử lý, dẫn tới 404 hoặc bị fallback từ chối.

Không thể chỉ đặt `permitAll()` cho `/login` bên trong chain `/secured/**` rồi mong nó hoạt động; request vẫn không vượt qua **chain matcher**.

Giải pháp trong ứng dụng form login: đảm bảo login/logout URLs nằm trong phạm vi chain có chứa các filter tương ứng, ví dụ:

~~~java
http.securityMatcher("/secured/**")
    .formLogin(form -> form
        .loginPage("/secured/login")
        .loginProcessingUrl("/secured/login")
        .permitAll()
    )
    .logout(logout -> logout
        .logoutUrl("/secured/logout")
        .logoutSuccessUrl("/secured/login?logout")
        .permitAll()
    );
~~~

Khi cấu hình `loginPage("/secured/login")`, ứng dụng cần **cung cấp trang GET login** phù hợp; filter Spring Security hỗ trợ xử lý POST login theo cấu hình. Đừng lẫn URL login do filter cung cấp với controller của application. Đường logout, CSRF, success/failure redirect, URL của form và `securityMatcher` đều cần thống nhất và được kiểm thử.

Một chain khác có thể được chọn cho `/login`, nhưng **nó không tự kích hoạt login filter của chain đã bị bỏ qua**.

## 11. Không suy ra các filter luôn được chia sẻ giữa các chain

Các cách cấu hình:

~~~text
/api/**:
  httpBasic hoặc bearer token
  stateless session policy (nếu thiết kế)
  AuthorizationFilter kiểm tra permission API

/admin/**:
  form login / session hoặc httpBasic
  CSRF, session management theo giao diện quản trị
  AuthorizationFilter kiểm tra ROLE_ADMIN

fallback:
  URL public cho phép theo allowlist
  URL không khai báo denyAll
~~~

Các cơ chế có thể khác nhau. Do đó:

- Nếu bật HTTP Basic **chỉ trong API chain**, request vào ADMIN chain không nhất thiết có HTTP Basic authentication filter đó.
- Nếu bật JWT Resource Server **chỉ trong API chain**, Bearer token gửi vào ADMIN chain không chắc được xác minh bởi chain ADMIN.
- Nếu chain ADMIN dùng session, đừng giả định có cùng stateless behavior của API.
- Nếu CSRF protection bị điều chỉnh ở một chain, đừng cho rằng điều chỉnh đó áp dụng toàn bộ các chain.
- Exception entry point và access-denied behavior có thể khác: cùng một thiếu quyền có thể dẫn đến 401/403/redirect tùy chain.
- Method security ở tầng service vẫn là lớp bảo vệ khác, nhưng **không nên coi nó là lý do chấp nhận URL không có chain**.

**Thiết kế:** phân chia chain khi thật sự cần khác nhau về authentication/filter/policy. Nếu chỉ cần các quyền URL khác nhau nhưng chung cơ chế bảo vệ, **một `SecurityFilterChain`** với nhiều `requestMatchers` có thể đơn giản và ít rủi ro hơn.

## 12. So sánh các cấu hình: an toàn, nguy hiểm, dễ hiểu nhầm

| Thiết kế | Kết quả | Đánh giá |
|---|---|---|
| Một chain mặc định + `requestMatchers` + `anyRequest().denyAll()` | Tất cả request khớp chain mặc định; rule quyết định | Đơn giản, dễ audit |
| API chain `/api/**` + ADMIN chain `/admin/**`, **không fallback** | URL khác có thể không qua Spring Security chain | Nguy hiểm nếu ngoài phạm vi còn endpoint |
| API chain + ADMIN chain + catch-all cuối `denyAll` | Bao phủ URL chưa khai báo | Phù hợp khi cần nhiều cơ chế bảo vệ |
| Catch-all `permitAll` `@Order(1)` trước ADMIN | Chain ADMIN có thể bị che hoàn toàn | Rất nguy hiểm |
| Broad API `/api/**` ưu tiên trước narrow `/api/admin/**` | Narrow chain không chạy cho admin API | Lỗi thứ tự |
| Dùng `web.ignoring` cho đường cần authentication | Bỏ security filtering tại đường đó | Sai mục tiêu |
| `anyRequest().denyAll()` trong chain chỉ khớp `/api/**` | Chặn API dư nhưng không bảo vệ URL ngoài API | Không phải fallback toàn hệ thống |
| Có fallback nhưng đặt sau một chain mặc định match-all | Fallback không bao giờ được chọn | Cần review matcher/priority |
| Chỉ dùng `authenticated` cho API nhạy cảm | Có login là đủ qua HTTP layer | Cần permission và object policy |

**Khuyến nghị về cấu trúc:** Càng nhiều chain, càng nhiều “giao điểm” giữa matcher, thứ tự, CSRF, login URL và exception handler. Không nên tạo nhiều chain chỉ để gom nhóm endpoint cho đẹp nếu một chain với rule rõ ràng đã đủ.

## 13. Làm sao kiểm tra “không có chain nào khớp” bằng test?

Đừng chỉ test rằng endpoint hợp lệ trả 200. Test phải bao phủ **các vùng nằm ngoài matcher** và chứng minh chúng bị bảo vệ đúng.

### 13.1. Ma trận coverage trước khi code

Lập một bảng “request → chain dự kiến → rule”:

| Nhóm | Request ví dụ | Chain dự kiến | Kết quả mong đợi |
|---|---|---|---|
| API public | `GET /api/public/faq` | API | Được qua HTTP rule dù anonymous |
| API nhạy cảm | `GET /api/reports/2026` | API | Thiếu `report:read` → từ chối |
| API khác | `POST /api/orders` | API | Yêu cầu authentication và kiểm tra CSRF theo policy |
| Admin | `GET /admin/users` | ADMIN | User thường → từ chối; admin → cho phép HTTP rule |
| Nội dung public | `GET /public/about` | FALLBACK | Được qua HTTP rule |
| Không khai báo | `GET /debug/threads` | FALLBACK | Từ chối |
| Sức khỏe hệ thống | `GET /actuator/health` | FALLBACK hoặc chain riêng | Theo chính sách vận hành |
| URL login/logout | `GET /login`, `POST /login` | Chain chứa login filter | Hoạt động đúng quy trình đăng nhập |
| URL error/forward | `/error`, dispatcher `ERROR`/`FORWARD` | Chain dự kiến | Xử lý lỗi hoạt động, không mở đường vòng |
| Path sát biên | `/api`, `/api/`, `/api//reports` | Chọn chain theo matcher thực tế | Không bị lọt bất ngờ |

Mỗi nhóm cần được test với anonymous, user thường và user có quyền phù hợp khi liên quan.

### 13.2. MockMvc: test quyền ở endpoint thật

Một mẫu test trong **dự án Spring Boot MVC có Spring Security Test**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChainCoverageTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unknownUrlMustBeRejectedByFallback() throws Exception {
        mvc.perform(get("/debug/threads"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotEnterAdmin() throws Exception {
        mvc.perform(get("/admin/users")
                    .with(user("lan").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReachExistingAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/users")
                    .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk());
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/about"))
                .andExpect(status().isOk());
    }
}
~~~

**Điều kiện:** các endpoint `/admin/users` và `/public/about` phải thực sự tồn tại và trả HTTP 200 khi được phép; cấu hình fallback và access-denied handler phải dẫn đến 403 cho request phù hợp. Mẫu test **không chạy độc lập**; cần Spring Boot Test + Spring Security Test, controller và security config đầy đủ.

**Quan trọng hơn status 403:** nếu `/debug/threads` không có controller, nó cũng có thể trả **404 khi không có security chain**. Test trạng thái trên một URL **không tồn tại** dễ cho cảm giác an toàn giả. Khi cần chứng minh coverage, hãy dùng một endpoint kiểm thử có handler thật hoặc kiểm tra chain matcher trực tiếp và bảo đảm requests bất hợp lệ không truy cập được dữ liệu.

### 13.3. Kiểm tra chain matcher trực tiếp

Có thể viết test integration để lấy danh sách `SecurityFilterChain` mà `FilterChainProxy` quản lý, tạo `MockHttpServletRequest` với các URL/method tiêu biểu, rồi đếm bao nhiêu chain có `matches(request) == true` và xác nhận **chain đầu tiên** đúng như mong đợi.

Mục tiêu:

~~~text
GET /api/orders      -> selected API
GET /admin/users     -> selected ADMIN
GET /public/about    -> selected FALLBACK
GET /debug/threads   -> selected FALLBACK, denyAll
POST /internal/ops   -> selected FALLBACK, denyAll
~~~

Việc nhiều chain đều `matches` một request không phải lỗi nếu các chain chuyên biệt đứng trước fallback; chỉ chain **đầu tiên** được sử dụng. Điều cần xác minh là **không có request quan trọng nào có số chain khớp bằng 0**, và không có chain quá rộng được xét trước chain cần quyền chặt hơn.

Để tin kết quả, test phải dựng `MockHttpServletRequest` đủ thông tin như contextPath, servletPath/pathInfo và dispatcher type phù hợp với matcher/servlet mapping của ứng dụng. Với matcher MVC hoặc PathPattern, nên ưu tiên MockMvc integration để tái hiện chính xác môi trường.

### 13.4. Các test âm tính đặc biệt có giá trị

1. **Narrow chain bị che**: User có `ROLE_USER` thử `/api/admin/users` và phải bị từ chối, dù API chain rộng có cho người đăng nhập qua.
2. **Gap ngoài mọi chain**: Tạo một endpoint kiểm thử nhạy cảm ngoài `/api/**`/`/admin/**`; kiểm tra fallback thật sự chặn anonymous.
3. **Thứ tự thay đổi**: Thêm một bean `@Order(0)` tạm trong test cấu hình để kiểm tra nguy cơ che chain, hoặc kiểm tra thứ tự bean trong test architecture.
4. **Method khác**: GET được phép nhưng POST/DELETE cùng path không được suy luận sẽ cùng quyền.
5. **Generated login/logout endpoints**: Nếu chain có form login, GET/POST login thật sự đi vào đúng chain.
6. **Exception path**: Trang xử lý lỗi có response phù hợp; không bị redirect loop hoặc bị mở rộng quyền.
7. **Actuator**: Mọi actuator endpoint được bật phải có chính sách rõ ràng; test môi trường deployment thực, không chỉ test config mặc định.
8. **Proxy rewrite/context path**: Đường mà Spring nhìn thấy có thể khác URL public; test qua gateway hoặc integration environment nếu routing có rewrite.

## 14. Test định tuyến khác test phân quyền dữ liệu

Một request có thể khớp đúng chain và vượt rule HTTP nhưng **vẫn không được thao tác tài nguyên**.

Ví dụ `GET /api/reports/2026`:

~~~text
1. Chain selected = API
2. HTTP rule = hasAuthority("report:read")
3. Principal có report:read => qua HTTP authorization
4. Service policy:
      đúng tenant?
      được cấp quyền trên báo cáo này?
      dữ liệu có thuộc phạm vi được phép?
5. Repository giới hạn tenant/owner
~~~

Do đó cần **hai lớp test độc lập**:

- **Chain coverage test**: chọn đúng chain và rule với URL/method/dispatcher.
- **Object authorization test**: hai người cùng role không được đọc tài nguyên của nhau, tenant A không được đọc tenant B.

Không vì đã có fallback mà bỏ service policy; cũng không vì service policy mà chấp nhận chain coverage gap.

## 15. Java 17 độc lập: mô phỏng chọn chain đầu tiên

Chương trình sau dùng **Java thuần** để mô phỏng ý tưởng `@Order` và “first matching chain wins”. Đây **không phải source Spring Security**, không thực thi filter, authentication, CSRF hay matcher thật. `startsWith` chỉ dùng để làm rõ phép chọn chain theo prefix.

Tạo file `ChainSelectionDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;

public class ChainSelectionDemo {
    record Chain(int order, String name, String prefix, String policy) {
        boolean matches(String path) {
            return "*".equals(prefix) || path.startsWith(prefix);
        }
    }

    static String select(String path, List<Chain> chains) {
        return chains.stream()
                .sorted(Comparator.comparingInt(Chain::order))
                .filter(chain -> chain.matches(path))
                .findFirst()
                .map(chain -> chain.name() + " [" + chain.policy() + "]")
                .orElse("NO_CHAIN");
    }

    static void show(String label, String path, List<Chain> chains) {
        System.out.println(label + ": " + select(path, chains));
    }

    public static void main(String[] args) {
        List<Chain> incomplete = List.of(
                new Chain(1, "API", "/api/", "AUTHENTICATED"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN")
        );

        show("gap /public", "/public/info", incomplete);
        show("api /api/orders", "/api/orders", incomplete);
        show("admin /admin/audit", "/admin/audit", incomplete);

        List<Chain> covered = List.of(
                new Chain(1, "API", "/api/", "AUTHENTICATED"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN"),
                new Chain(99, "FALLBACK", "*", "DENY_ALL")
        );
        show("safe /public", "/public/info", covered);

        List<Chain> wrongOrder = List.of(
                new Chain(1, "EARLY_CATCH_ALL", "*", "PERMIT_ALL"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN")
        );
        show("wrong /admin", "/admin/audit", wrongOrder);

        List<Chain> unsorted = List.of(
                new Chain(99, "FALLBACK", "*", "DENY_ALL"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN"),
                new Chain(1, "API", "/api/", "AUTHENTICATED")
        );
        show("unsorted input /admin", "/admin/audit", unsorted);
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ChainSelectionDemo.java
java ChainSelectionDemo
~~~

Output chính xác:

~~~text
gap /public: NO_CHAIN
api /api/orders: API [AUTHENTICATED]
admin /admin/audit: ADMIN [ROLE_ADMIN]
safe /public: FALLBACK [DENY_ALL]
wrong /admin: EARLY_CATCH_ALL [PERMIT_ALL]
unsorted input /admin: ADMIN [ROLE_ADMIN]
~~~

Diễn giải:

- **`NO_CHAIN`**: không có chain nào nhận `/public/info` trong danh sách chưa có fallback. Ở Spring Security thật, tình huống tương ứng **không có Spring Security chain bảo vệ request**; không thể suy ra HTTP status chỉ từ điều này.
- **`API`** và **`ADMIN`**: URL thuộc matcher chuyên biệt.
- **`FALLBACK [DENY_ALL]`**: URL không thuộc hai chain đầu vẫn có một chain để kiểm tra và từ chối. Output chỉ thể hiện **policy được cấu hình**, chưa thực thi authentication.
- **`EARLY_CATCH_ALL [PERMIT_ALL]`**: fallback mở đặt đầu che chain admin; đây là rủi ro rất rõ.
- **`unsorted input`**: không phụ thuộc thứ tự phần tử List, vì mô phỏng sắp xếp theo order trước khi chọn. Trong Spring Security thật, order được framework xử lý theo đăng ký và `@Order` trên bean.

Bài tập mở rộng: sửa danh sách `covered` để `/api/admin/**` có chain order 0 với `ROLE_ADMIN`. Test xem chain hẹp phải đứng trước API chain rộng để không bị che.

## 16. Gỡ lỗi khi URL không bị chặn như dự kiến

Đừng chỉ nhìn vào `hasRole`/`denyAll`. Hãy lần theo thứ tự:

1. **Request mà Spring thật sự nhận là gì?** Method, path, context path, servlet mapping, dispatcher type có khác URL ngoài proxy không?
2. **`FilterChainProxy` được đăng ký và có hiệu lực không?** Có cấu hình Spring Security cho servlet context này? Có đường nào bị `web.ignoring` không?
3. **Có bao nhiêu `SecurityFilterChain` bean?** Liệt kê bean/`@Order`/matcher; đừng chỉ xem một config class.
4. **Chain đầu tiên khớp là chain nào?** Matcher quá rộng/priority quá sớm có che chain đặc thù?
5. **Có chain fallback không?** Có thật sự không có `securityMatcher` hạn chế không? Nó được xét sau các chain chuyên biệt chứ?
6. **Rule bên trong chain là gì?** `requestMatchers`, `anyRequest`, method/dispatcher và thứ tự rule.
7. **Authentication filter của chain đó hoạt động không?** JWT, HTTP Basic, form login, session, custom provider và entry point có nằm trong đúng chain?
8. **Có lỗi CSRF/CORS hoặc method security không?** Một 403 không nhất thiết đến từ authorization rule; một 404 không chứng minh endpoint đã được bảo vệ.
9. **Có ràng buộc object-level không?** Đúng role nhưng sai owner/tenant vẫn phải từ chối ở policy nghiệp vụ.
10. **Kết quả test âm tính?** Anonymous, user thường, user khác tenant và URL ngoài mọi prefix đều được kiểm thử?

### Ghi log phục vụ điều tra

Có thể bật log Spring Security ở mức DEBUG/TRACE trong môi trường phát triển/test để thấy request được bảo vệ và filter chain nào có khả năng được chọn:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Log cụ thể phụ thuộc phiên bản và cấu hình. **Không bật log bảo mật chi tiết vô hạn trong production**, không log credentials/access token đầy đủ và không coi log là thay thế integration tests. Với môi trường gateway/proxy, hãy quan sát thêm request path tại tầng Servlet sau rewrite.

## 17. Các lỗi phổ biến và cách khắc phục

| Lỗi | Nguy cơ | Biện pháp |
|---|---|---|
| Khai báo hai chain hẹp rồi không có fallback | URL khác không qua Spring Security filter chain | Catch-all chain đứng cuối |
| Cho rằng `anyRequest().denyAll()` ở API chain bảo vệ toàn ứng dụng | URL ngoài `securityMatcher` vẫn lọt | Phân biệt chain matcher với rule matcher |
| Đặt chain `/api/**` trước `/api/admin/**` | Chain admin bị che | Chain chuyên biệt ưu tiên cao hơn |
| Catch-all `permitAll` đứng trước các chain khác | Mọi chain sau vô hiệu | Fallback đặt cuối, allowlist public hẹp |
| Đặt `/admin/**` rule trong chain chỉ khớp `/api/**` | Rule không bao giờ chạy | Đặt rule trong chain có matcher bao phủ |
| Tưởng chain B bổ sung filter cho chain A | CSRF/auth mechanism/authorization bị thiếu | Mỗi chain tự cấu hình đủ chính sách |
| Chỉ test endpoint tồn tại/200, không test URL ngoài phạm vi | Không phát hiện chain coverage gap | Test negative với handler thật và matcher |
| Dựa vào 404 để kết luận đã được chặn | 404 có thể do không có route | Phân biệt 404 vs security denial |
| Gắn `formLogin` vào chain `/secured/**` nhưng để `/login` mặc định | Login URL không thuộc chain, có thể 404 | Tùy chỉnh login/logout URL trong phạm vi chain |
| Để `/actuator/**` ngoài mọi chain | Lộ endpoint vận hành khi được bật | Policy actuator rõ ràng, môi trường deployment test |
| Không xét `ERROR`/`FORWARD` dispatch | Trang error có thể bị chặn hoặc policy sai | Test dispatcher và bảo vệ route nội bộ |
| Dùng `authenticated()` cho mọi API nhạy cảm | Người dùng thường có thể làm việc không được phép | Role/permission + object policy |
| Dựa vào cấu hình mặc định Boot mà không kiểm bean | Có thể không tồn tại fallback như tưởng tượng | Audit bean chain thực tế |
| Nhiều chain cùng order mà không kiểm thứ tự | Lựa chọn chain phụ thuộc trật tự không rõ ràng | Order tường minh và test |

## 18. Checklist thiết kế trước khi merge

Với mọi PR thêm hoặc đổi `SecurityFilterChain`:

- [ ] Liệt kê **tất cả** chain hiện hành, matcher cấp chain và giá trị `@Order`.
- [ ] Xác minh các chain nhạy cảm, hẹp hơn được ưu tiên trước chain rộng hơn.
- [ ] Có **một fallback catch-all** cuối cùng, không bị giới hạn bởi `securityMatcher`, nếu mục tiêu là bảo vệ toàn bộ Servlet app.
- [ ] Fallback mặc định `denyAll` hoặc quy tắc chặt tương đương; URL public là allowlist hẹp có lý do.
- [ ] Không để một chain matcher rộng với `permitAll`/`authenticated` che các chain nhạy cảm.
- [ ] Xác định rõ chain nào xử lý `/login`, `/logout`, `/error`, tài nguyên tĩnh, actuator, CORS preflight và API documentation.
- [ ] Đảm bảo authentication, CSRF, session, CORS và exception handling **đúng trong từng chain**.
- [ ] Test các đường biên `/api`, `/api/`, trailing slash, context path và proxy rewrite khi có liên quan.
- [ ] Test anonymous, authenticated user, user thiếu permission và user có role cao; không chỉ happy path.
- [ ] Test một endpoint nhạy cảm ngoài các prefix đã khai báo để chứng minh fallback chặn được.
- [ ] Không tin HTTP layer thay thế object-level policy trên tenant/owner.
- [ ] Có kiểm thử regression khi thêm chain mới hoặc thay `@Order`.

**Nguyên tắc review một dòng:** *Mỗi request phải vào đúng chain; mỗi chain phải áp dụng đúng quyền; các request chưa được khai báo phải bị chặn một cách có chủ đích.*

## 19. Câu hỏi tự kiểm tra

**1. Có hai chain `/api/**` và `/admin/**`, đều có `anyRequest().denyAll()`. Vậy `GET /debug` có bị Spring Security từ chối không?**  
Không thể kết luận có. Nếu không có chain fallback khác, request không khớp chain nào, nên hai rule `denyAll` không được đánh giá.

**2. `securityMatcher` và `requestMatchers` khác ở đâu?**  
`securityMatcher` quyết định **có dùng cả chain này cho request không**; `requestMatchers` quyết định **rule phân quyền nào áp dụng bên trong chain đã chọn**.

**3. Nếu `@Order(1)` có matcher `/api/**` và `@Order(2)` có matcher `/api/admin/**`, request admin khớp chain nào?**  
Chain `@Order(1)` trước. Chain `@Order(2)` không được gọi thêm, dù matcher của nó cũng đúng.

**4. Có thể chỉ thêm `anyRequest().denyAll()` vào API chain để lấp gap URL không?**  
Không. Cần một chain khác có matcher bao phủ URL còn lại, thường là catch-all cuối.

**5. Một catch-all `@Order(1)` với `permitAll` có an toàn không nếu chain admin `@Order(2)` có `hasRole("ADMIN")`?**  
Không. Catch-all che chain admin. Rule của admin không được đánh giá.

**6. Tại sao chain chỉ match `/secured/**` bật `formLogin` nhưng `GET /login` có thể 404?**  
Vì endpoint do filter cung cấp nằm ngoài matcher cấp chain. Cần tùy chỉnh login URL cho đúng phạm vi và cung cấp trang login nếu dùng custom login page.

**7. `GET /public/faq` trả 404 có chứng minh URL được chặn bởi Spring Security không?**  
Không. Có thể chỉ là route không tồn tại; phải xác minh chain và security decision thực.

**8. Có nên dùng nhiều chain chỉ để phân biệt `/api/admin/**` với `/api/users/**` nếu cùng authentication mechanism?**  
Không bắt buộc. Một chain dùng `requestMatchers` khác nhau thường đơn giản hơn; nhiều chain phù hợp khi cần các bộ filter/cơ chế xác thực riêng.

**9. Một request đã qua API chain với role đúng có chắc được đọc hóa đơn của user khác không?**  
Không. Cần policy theo owner/tenant/quyền trên tài nguyên cụ thể.

**10. Test quan trọng nhất cho bài này là gì?**  
Kiểm tra **request không thuộc matcher nào đã khai báo** vẫn được fallback bảo vệ; đồng thời kiểm tra **chain hẹp không bị chain rộng đứng trước che**.

## 20. Tài liệu tham khảo chính thức

- Spring Security – **Java Configuration / Multiple HttpSecurity Instances / Choosing securityMatcher or requestMatchers / SecurityFilterChain Endpoints**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security – **Servlet Architecture / Multiple SecurityFilterChain / FilterChainProxy**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – **Testing with MockMvc**: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security – **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
