# Nhiều nguồn cấu hình CORS và cấu hình theo security chain

## 1. Bài toán: một ứng dụng, nhiều chính sách CORS

Giả sử hệ thống tại `https://api.example.com` phục vụ hai ứng dụng giao diện:

- `https://app.example.com` quản lý đơn hàng qua các endpoint `/api/**`.
- `https://admin.example.com` quản trị người dùng qua các endpoint `/admin/**`.

Hai frontend có mức độ tin cậy và nhu cầu HTTP khác nhau. Ứng dụng thường cần `GET`, `POST`, `PUT` và header `X-CSRF-TOKEN`; giao diện quản trị chỉ cần `GET`, `POST`. Không nên cấp cho frontend ứng dụng thông thường quyền CORS đọc phản hồi của khu vực quản trị.

Ở Spring Security, có hai cơ chế cần kết hợp:

1. **`CorsConfigurationSource`:** tìm ra `CorsConfiguration` áp dụng cho một request.
2. **Security chain:** quyết định tập filter bảo mật nào được thực thi đối với request, trong đó có thể tích hợp CORS thông qua `HttpSecurity.cors(...)` hoặc `ServerHttpSecurity.cors(...)`.

Đặc biệt, khi ứng dụng có **nhiều bean `CorsConfigurationSource`**, Spring Security không thể mặc nhiên biết phải chọn nguồn nào để cấu hình CORS tự động. Cách giải quyết rõ ràng là **chỉ định nguồn CORS cho từng security chain**.

Bài này thuộc mô-đun `SPRING_SECURITY_HTTP_PROTECTION`: ngoài CORS, ứng dụng vẫn cần xác thực, phân quyền, CSRF, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Chúng là những lớp phòng vệ bổ sung, không thể thay thế nhau.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `CorsConfiguration`, `CorsConfigurationSource` và `SecurityFilterChain` / `SecurityWebFilterChain`.
2. Hiểu vì sao nhiều source cùng tồn tại gây mơ hồ cho quá trình cấu hình CORS tự động.
3. Gắn một source tường minh cho mỗi chain trên Servlet và Reactive.
4. Thiết kế matcher sao cho preflight `OPTIONS` và actual request liên quan được xử lý CORS đúng.
5. Kiểm tra khả năng rò rỉ quyền CORS giữa `/api/**` và `/admin/**`, nhất là khi dùng credentials.
6. Chẩn đoán xung đột với Spring MVC/WebFlux, nhiều filter, gateway, security chain dự phòng và cache.
7. Viết kiểm thử tích hợp cho cả origin được phép lẫn origin bị từ chối, và xác nhận actual request vẫn phải qua bảo mật server.

Các hostname `example.com` và `example.org` chỉ là ví dụ minh họa.

## 2. Hai trục cấu hình: đường dẫn và quyền cross-origin

Hãy phân biệt hai câu hỏi:

**Câu hỏi A — request rơi vào security chain nào?**

Một `SecurityFilterChain` có thể chỉ xử lý `/api/**`, chain khác xử lý `/admin/**`. Trong Spring Security Servlet, `FilterChainProxy` chọn **chain đầu tiên khớp request** dựa trên các matcher và thứ tự. Trong WebFlux, việc lựa chọn chain cũng dựa vào matcher và thứ tự của các `SecurityWebFilterChain`.

**Câu hỏi B — chain đó cho origin nào qua CORS?**

`CorsConfigurationSource` trả chính sách CORS cho request theo path hoặc logic tùy biến. Sau đó CORS processor kiểm tra origin, method và request headers.

| Thành phần | So khớp với gì? | Ví dụ | Vai trò |
| --- | --- | --- | --- |
| `securityMatcher(...)` trên Servlet | Request đi vào chain | `"/api/**"` | Chọn bộ lọc bảo mật |
| `securityMatcher(...)` trên WebFlux | `ServerWebExchange` đi vào chain | Matcher `"/admin/**"` | Chọn reactive security chain |
| `UrlBasedCorsConfigurationSource` | Path áp dụng chính sách | `"/api/**"` | Chọn `CorsConfiguration` |
| `allowedOrigins` | Origin của trang đang gọi | `"https://app.example.com"` | Cấp quyền CORS cho frontend cụ thể |
| `allowedMethods` | Method được hỏi qua preflight | `"POST", "PUT"` | Cho phép method CORS |
| `allowedHeaders` | Tên request headers được hỏi | `"Authorization", "Content-Type"` | Cho phép request headers CORS |

**Không nhầm lẫn:** `securityMatcher("/api/**")` và `registerCorsConfiguration("/api/**", policy)` cùng chứa một path pattern, nhưng có hai trách nhiệm riêng. Matcher chọn chain; source chọn chính sách CORS. Chúng cần phối hợp nhất quán.

### 2.1. Một nguồn không làm thay đổi quyền endpoint

Ví dụ `/admin/users` có CORS policy cho `https://admin.example.com`. Điều này **không cho mọi user ở frontend admin quyền xóa user**. Server vẫn phải thực hiện authentication, authorization và CSRF. Ngược lại, một HTTP client ngoài browser vẫn có thể gửi request dù origin của nó không được CORS cấp quyền đọc response cho JavaScript.

### 2.2. Mối quan hệ tổng thể

~~~mermaid
flowchart TD
    A["Request tới /api/** hoặc /admin/**"] --> B["Chọn security chain đầu tiên phù hợp"]
    B --> C{"Chain nào?"}
    C -- "/api/**" --> D["API chain: CORS source API"]
    C -- "/admin/**" --> E["Admin chain: CORS source Admin"]
    C -- "Không khớp" --> F["Fallback chain"]
    D --> G["CORS processor kiểm tra Origin/Method/Headers"]
    E --> G
    G --> H{"Là preflight hợp lệ?"}
    H -- "Có" --> I["Trả lời OPTIONS, không cần xác thực phiên"]
    H -- "Không hoặc actual request" --> J["Tiếp tục/xử lý theo loại request"]
    J --> K["Authentication + authorization + CSRF khi áp dụng"]
    F --> L["Chính sách bảo vệ fallback"]
~~~

Trong thực tế, preflight không hợp lệ bị từ chối chứ không tự đi qua authentication để được chấp nhận; sơ đồ chỉ khái quát các nhánh chính. Với actual request khác origin, CORS headers cần hiện diện trên response nếu browser được phép đọc, kể cả status lỗi 401/403.

## 3. Khi nào một CorsConfigurationSource là đủ?

Nếu ứng dụng chỉ có một security chain hoặc muốn một nguồn quản lý nhiều nhóm path, một `UrlBasedCorsConfigurationSource` duy nhất đã có thể đáp ứng:

~~~java
CorsConfiguration api = new CorsConfiguration();
api.setAllowedOrigins(List.of("https://app.example.com"));
api.setAllowedMethods(List.of("GET", "POST", "PUT"));

CorsConfiguration admin = new CorsConfiguration();
admin.setAllowedOrigins(List.of("https://admin.example.com"));
admin.setAllowedMethods(List.of("GET", "POST"));

UrlBasedCorsConfigurationSource source =
    new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/**", api);
source.registerCorsConfiguration("/admin/**", admin);
~~~

Nó chọn policy theo path. Với security chain có CORS được bật, logic chọn policy có thể hoạt động mà không cần tách thành hai bean.

**Vậy khi nào cần nhiều source?**

- API và admin có **security chains khác nhau**, mỗi nhóm chịu trách nhiệm cấu hình bảo mật riêng.
- Một nguồn CORS cần phụ thuộc vào registry/tenant, trong khi nguồn khác là cấu hình tĩnh cho admin.
- Có các module triển khai độc lập cùng đưa `CorsConfigurationSource` bean vào Spring context.
- Muốn tách rõ quyền sở hữu và kiểm thử nguồn cấu hình của từng chain.

Không nhất thiết thêm nhiều source để “bảo mật hơn”. Việc tách nguồn chỉ có lợi khi **cách chọn và phạm vi áp dụng được kiểm soát rõ**.

## 4. Nhiều CorsConfigurationSource beans và mơ hồ cấu hình tự động

Spring Security có thể tự tích hợp CORS trong một số cấu hình khi nhận diện được nguồn cấu hình phù hợp. Tuy nhiên, khi có **nhiều bean `CorsConfigurationSource`**, việc tự chọn một source không còn rõ ràng; Spring Security không tự quyết định đúng chính sách cho tất cả chains.

Ví dụ:

~~~java
@Bean("apiCorsSource")
CorsConfigurationSource apiCorsSource() {
    // ...
}

@Bean("adminCorsSource")
CorsConfigurationSource adminCorsSource() {
    // ...
}
~~~

Nếu các chain chỉ cấu hình:

~~~java
http.cors(Customizer.withDefaults());
~~~

thì không nên giả định Spring Security sẽ tự chọn `apiCorsSource` cho API và `adminCorsSource` cho admin. Phải **gắn nguồn tường minh**:

~~~java
http.cors(cors -> cors.configurationSource(apiCorsSource));
~~~

và tại chain khác:

~~~java
http.cors(cors -> cors.configurationSource(adminCorsSource));
~~~

Tương tự đối với Reactive:

~~~java
http.cors(cors -> cors.configurationSource(apiReactiveCorsSource));
~~~

Việc chỉ đặt tên bean phù hợp không thay thế chỉ định source. Trong ví dụ Spring Boot, nếu một phương thức khai báo bean cần nhận source theo kiểu interface và có **hai bean cùng kiểu**, dùng `@Qualifier` để tránh tiêm dependency mơ hồ.

### 4.1. Không xem @Primary là lời giải cho mọi chain

`@Primary` có thể giải quyết mơ hồ của dependency injection tại một số điểm, nhưng **không diễn đạt chính sách “chain API dùng source API, chain admin dùng source admin”**. Nếu mọi chain vô tình lấy cùng một source mặc định, origin hoặc path của nhóm này có thể bị xử lý sai ở nhóm khác.

Với nhiều chain, cấu hình tường minh trên từng chain vừa dễ đọc, vừa dễ kiểm thử hơn việc dựa vào ưu tiên bean.

### 4.2. Các nguồn CORS khác bean

CORS còn có thể được khai báo tại:

- Spring MVC: `WebMvcConfigurer#addCorsMappings`, `@CrossOrigin`.
- Spring WebFlux: `WebFluxConfigurer#addCorsMappings`, `@CrossOrigin`.
- Servlet `CorsFilter` hoặc Reactive `CorsWebFilter` độc lập.
- Reverse proxy, CDN hoặc API gateway.

Những thành phần này có thể tạo thêm lớp xử lý CORS. Khi đã lựa chọn **nguồn CORS tường minh cho từng security chain**, cần biết policy nào đang thực thi tại từng tầng để tránh chồng chéo.

## 5. Cấu hình hoàn chỉnh trên Servlet: hai nguồn, hai SecurityFilterChain

Ví dụ dưới đây sử dụng Spring Security theo kiểu cấu hình `SecurityFilterChain`, phân tách rõ API và admin.

Chính sách dự kiến:

| Nhóm URL | Origin frontend được phép | Methods CORS | Credentials |
| --- | --- | --- | --- |
| `/api/**` | `https://app.example.com` | `GET`, `POST`, `PUT` | Có |
| `/admin/**` | `https://admin.example.com` | `GET`, `POST` | Có |
| Các URL còn lại | Không có CORS policy từ hai nguồn này | Không cấp quyền riêng | Không suy ra quyền truy cập |

~~~java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class MultiChainServletCorsConfiguration {

    @Bean("apiCorsSource")
    CorsConfigurationSource apiCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean("adminCorsSource")
    CorsConfigurationSource adminCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://admin.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(300L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/admin/**", cors);
        return source;
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
        HttpSecurity http,
        @Qualifier("apiCorsSource") CorsConfigurationSource apiCors
    ) throws Exception {
        return http
            .securityMatcher("/api/**")
            .cors(cors -> cors.configurationSource(apiCors))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain adminChain(
        HttpSecurity http,
        @Qualifier("adminCorsSource") CorsConfigurationSource adminCors
    ) throws Exception {
        return http
            .securityMatcher("/admin/**")
            .cors(cors -> cors.configurationSource(adminCors))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Chú giải:**

1. Hai bean `CorsConfigurationSource` khác nhau được đặt tên rõ ràng.
2. `@Qualifier` bảo đảm mỗi chain được tiêm **đúng bean**.
3. `@Order(1)` và `@Order(2)` xác định thứ tự ưu tiên xét chain. Những matcher `/api/**` và `/admin/**` không chồng lấn, nên kết quả dễ dự đoán.
4. `securityMatcher(...)` chọn phạm vi **request nhận chain**. `registerCorsConfiguration(...)` chọn **policy theo path** bên trong source tương ứng.
5. `cors(cors -> cors.configurationSource(...))` là nơi gắn nguồn CORS vào chain, không dựa vào auto-selection giữa hai bean.
6. `fallbackChain` từ chối các URL còn lại theo authorization mặc định của ví dụ, thay vì vô tình để lại vùng không có chain. Nếu ứng dụng có login page, assets hay health endpoint cần truy cập, phải thiết kế rule riêng phù hợp.
7. `authenticated()` chưa mô tả cơ chế đăng nhập cụ thể. Cấu hình production cần thêm authentication, authorization chi tiết, CSRF và session security theo mô hình thực tế.

**Không tắt CSRF chỉ vì muốn xử lý OPTIONS.** Spring Security CORS integration cần xử lý preflight trước các bộ lọc xác thực, nhưng actual `POST`/`PUT` dùng cookie phiên vẫn phải đáp ứng CSRF protection theo thiết kế.

### 5.1. Vì sao không chỉ viết hai @Bean rồi dùng withDefaults?

Hai bean cùng kiểu không cho biết chain nào nên lấy bean nào. Cấu hình tường minh `configurationSource(...)` trong cả hai chain loại bỏ sự mơ hồ đó. Khi đọc code, người vận hành có thể truy từ chain qua source tới danh sách origin/headers được phép.

### 5.2. Có cần cấu hình CORS trong fallback chain?

Điều đó tùy phạm vi API. Trong ví dụ, fallback chain không cấp một CORS policy mới; request cross-origin tới path ngoài phạm vi API/admin không được ứng dụng chủ động mở quyền đọc qua các nguồn này.

Nếu có các endpoint khác cần dùng từ frontend, hãy khai báo chính sách và chain có chủ đích. Đừng bật một wildcard origin rộng trên fallback chỉ để “bắt tất cả preflight”.

### 5.3. Khi dùng nhiều chain với cùng một source

Nếu cả hai chain cùng muốn dùng một nguồn đã đăng ký `/api/**` và `/admin/**`, có thể truyền cùng source cho cả hai. Điều quan trọng là **chain nhận OPTIONS phải được bật CORS**, không phải số lượng bean. Tuy nhiên hai source riêng có thể làm ranh giới quyền sở hữu và kiểm thử rõ ràng hơn khi API/admin do các nhóm khác nhau quản lý.

## 6. Chọn chain: thứ tự, matcher và request OPTIONS thực tế

Đây là bẫy thường gặp nhất khi chia security chains.

Browser muốn gọi:

~~~http
PUT /api/profile HTTP/1.1
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token>
~~~

Nó có thể hỏi trước bằng:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

**Security chain được chọn bằng method HTTP thực của request đang đến — tức OPTIONS**, không phải vì header `Access-Control-Request-Method` ghi PUT.

Ví dụ matcher sai cho luồng preflight:

~~~java
// Chỉ khớp PUT, sẽ không tự nhận OPTIONS preflight hỏi quyền PUT.
http.securityMatcher(request ->
    "PUT".equals(request.getMethod())
        && request.getServletPath().startsWith("/api/")
);
~~~

Nếu chỉ chain này có `cors(...)`, preflight `OPTIONS /api/profile` sẽ rơi vào chain khác hoặc fallback. Browser có thể nhận 401/403 thay vì CORS response hợp lệ.

**Thiết kế tốt hơn:** matcher theo đường dẫn `/api/**` đủ để cả preflight OPTIONS và actual PUT vào chain API, sau đó dùng `authorizeHttpRequests` để kiểm tra quyền theo method/route khi cần.

### 6.1. Order quyết định khi matcher chồng lấn

Giả sử:

- Chain A: `securityMatcher("/**")`, `@Order(1)`.
- Chain B: `securityMatcher("/admin/**")`, `@Order(2)`.

Chain A sẽ khớp trước chain B với hầu hết request, khiến chính sách admin có thể **không bao giờ được sử dụng**.

Không nên suy luận rằng Spring Security tự chọn matcher “cụ thể hơn”. Với nhiều chains, ưu tiên và matcher quyết định kết quả. Cách an toàn là để các chain chuyên biệt đứng trước và đặt fallback ở sau:

~~~text
@Order(1): /api/**
@Order(2): /admin/**
@Order(3): fallback (mọi request còn lại)
~~~

Nếu cần một chain quản trị ưu tiên cao hơn API vì pattern giao nhau, phải phân tích và kiểm thử quy tắc ưu tiên cho từng path thật.

### 6.2. CORS source phải nhận đúng path sau gateway rewrite

Frontend có thể gọi `https://api.example.com/service/api/profile` nhưng gateway chuyển vào Spring thành `/api/profile`. Nếu `securityMatcher` và `UrlBasedCorsConfigurationSource` đang dùng những path khác nhau so với request mà ứng dụng nhận, source có thể trả `null` hoặc chain không khớp.

Chẩn đoán cần bắt đầu từ đường dẫn **thực tế ở Spring sau khi proxy/gateway rewrite**, không đoán theo URL công khai.

### 6.3. Tránh giả định rằng 403 luôn do authorization

CORS processor có thể từ chối preflight bằng `403 Invalid CORS request` nếu origin, method, headers hoặc URL policy không đạt. Ngược lại, actual request có thể trả 403 do CSRF hoặc thiếu quyền. Phân biệt bằng method và các request/response headers, không chỉ bằng status code.

## 7. Luồng preflight và actual request qua hai chains

### 7.1. Frontend ứng dụng gọi API của mình

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Chain API được chọn theo `/api/**`. Source API cho `https://app.example.com` sử dụng `POST` và hai header này. Response có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Browser sau đó có thể gửi actual POST. Server vẫn cần xác thực session/token và kiểm tra CSRF.

### 7.2. Frontend ứng dụng cố đọc API admin

~~~http
OPTIONS /admin/users HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Request này vào **admin chain** do path `/admin/users`, dù origin là frontend ứng dụng. Source admin chỉ cho `https://admin.example.com`, nên preflight bị từ chối. Browser không gửi actual POST của luồng này.

**Nhưng đây không phải authorization:** `curl` hay HTTP client ngoài browser vẫn có thể gọi `/admin/users`, và server phải kiểm tra quyền quản trị trên request thật. CORS chỉ hạn chế JavaScript đọc response khác origin và một số actual request sau preflight.

### 7.3. Frontend admin gọi đúng API của mình

~~~http
OPTIONS /admin/users HTTP/1.1
Origin: https://admin.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Source admin cho phép origin và method này. Preflight có thể thành công, nhưng actual `POST /admin/users` vẫn phải xác thực và phân quyền hành động tạo user.

### 7.4. Frontend admin gọi nhầm API thường

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://admin.example.com
Access-Control-Request-Method: PUT
~~~

Request vào chain API; source API không cho `https://admin.example.com`. Vì vậy nó bị từ chối bởi **chính sách API**, dù trang admin là một origin được phép ở chính sách admin.

Không nên coi một origin được phép ở một chain là “được phép trong toàn bộ ứng dụng”.

## 8. Credentials và ranh giới tin cậy giữa các chains

Khi một API dùng cookie/session và frontend gọi:

~~~javascript
fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Browser yêu cầu actual response CORS sử dụng origin **cụ thể**, phù hợp với request, và `Access-Control-Allow-Credentials: true`. Không dùng:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

để cố cấp quyền trong credentials mode `include`.

Ở cấu hình nhiều source, cần tự hỏi:

- Source API có vô tình cho phép origin admin hoặc preview không?
- Source admin có vô tình cho phép origin của frontend người dùng thông thường không?
- Có pattern `https://*.example.com` bao gồm các subdomain do người dùng/đối tác kiểm soát?
- Có gateway hoặc một filter độc lập phản chiếu mọi `Origin` khiến allowlist theo chain mất tác dụng?
- Response 401/403/500 của từng chain có mang CORS headers nhất quán nếu frontend cần đọc status không?

Cookie được gửi theo Fetch credentials mode và luật cookie (`SameSite`, `Secure`, Domain/Path, chính sách browser), không phải do CORS source tự gắn cookie. Hai frontend khác origin có thể vẫn **same-site**; một subdomain nguy hiểm có thể nhận cookie trong request cùng site nếu được phép bởi browser. Do vậy không mở wildcard origin patterns bừa bãi với `allowCredentials(true)`.

### 8.1. Không nhầm source theo chain với kiểm soát truy cập tenant

Nếu `/api/tenants/{id}/orders` dùng chung một chain và một origin, CORS không kiểm tra user có quyền với tenant id đó hay không. Đó vẫn là trách nhiệm authentication/authorization của server. Không dùng Origin như bằng chứng tenant hoặc user đã được xác minh.

## 9. Cấu hình hoàn chỉnh trên Reactive / Spring WebFlux

WebFlux sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và nguồn CORS thuộc package `org.springframework.web.cors.reactive`. Không được nhập nhầm `CorsConfigurationSource` Servlet.

Ví dụ hai nguồn/chain Reactive với cùng ranh giới `/api/**` và `/admin/**`:

~~~java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class MultiChainReactiveCorsConfiguration {

    @Bean("apiReactiveCorsSource")
    CorsConfigurationSource apiReactiveCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean("adminReactiveCorsSource")
    CorsConfigurationSource adminReactiveCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://admin.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(300L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/admin/**", cors);
        return source;
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiWebChain(
        ServerHttpSecurity http,
        @Qualifier("apiReactiveCorsSource") CorsConfigurationSource source
    ) {
        return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .cors(cors -> cors.configurationSource(source))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public/**").permitAll()
                .anyExchange().authenticated())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain adminWebChain(
        ServerHttpSecurity http,
        @Qualifier("adminReactiveCorsSource") CorsConfigurationSource source
    ) {
        return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/admin/**"))
            .cors(cors -> cors.configurationSource(source))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallbackWebChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Điểm giống Servlet:

- Từng chain **tường minh** gắn đúng `CorsConfigurationSource` bằng `configurationSource(...)`.
- Matchers dựa trên path giúp preflight OPTIONS và actual request cùng thuộc phạm vi chain tương ứng.
- `@Order` ưu tiên chain cụ thể trước fallback.
- `allowCredentials(true)` chỉ áp dụng cùng origin cụ thể được tin cậy.
- CORS không thay thế kiểm tra user hoặc CSRF trên actual request.

Điểm khác:

- WebFlux sử dụng `ServerWebExchange`, `SecurityWebFilterChain` và `ServerWebExchangeMatchers`.
- Nguồn CORS là `org.springframework.web.cors.reactive.CorsConfigurationSource`.
- Nếu dùng một `CorsWebFilter` độc lập ngoài security chain, cần kiểm soát thứ tự WebFilter và tránh cùng xử lý CORS ở nhiều nơi.

**Lưu ý thực hành:** các đoạn cấu hình là ví dụ đầy đủ về cách **gắn CORS source theo chain**, không phải cấu hình login/session/token hoàn chỉnh. Cần bổ sung cơ chế authentication, session cookie và CSRF phù hợp với dự án, rồi kiểm thử end-to-end.

## 10. Tích hợp với Spring MVC, WebFlux handler và các tầng CORS khác

Một ứng dụng có thể đã khai báo CORS ở controller:

~~~java
@CrossOrigin(origins = "https://app.example.com")
@GetMapping("/api/products")
public List<Product> products() {
    // ...
}
~~~

hoặc global ở MVC:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com");
}
~~~

Spring Security có thể tích hợp CORS với MVC khi cấu hình phù hợp, đặc biệt trong trường hợp không có nguồn `CorsConfigurationSource` riêng. Tuy nhiên, nếu Security chains đã gắn các sources tường minh, đừng giả định annotations/global MVC sẽ trở thành chính sách duy nhất cho request.

Ở WebFlux có cơ chế tương tự qua `WebFluxConfigurer` và `@CrossOrigin`; khi sử dụng các nguồn CORS Reactive tường minh trên chains, cần quản lý sự phối hợp.

### 10.1. Chồng chéo không làm CORS “chặt hơn”

Giả sử security chain admin chỉ cho `https://admin.example.com` nhưng gateway tự phản chiếu mọi Origin hoặc một `CorsFilter` chung dùng wildcard. Tùy thứ tự, response có thể mang header trùng, header không đúng policy hoặc làm người vận hành hiểu sai phạm vi tin cậy.

Vì thế cần xác định:

1. Tầng nào là **nguồn chính sách CORS** cho từng nhóm URL?
2. Gateway có xử lý preflight riêng hay chuyển tiếp cho Spring?
3. Filter/handler nào thêm response headers?
4. Những chính sách này có cùng một allowlist và cách xử lý credentials không?
5. Khi request đi vào chain khác dự kiến, response cuối ở browser là gì?

Không phải mọi triển khai có hai bộ xử lý đều **luôn** tạo trùng header — một bộ xử lý có thể bỏ qua nếu response đã có header — nhưng thiết kế chồng chéo làm thứ tự và quyền CORS khó kiểm chứng. Tốt hơn là một luồng rõ ràng, có kiểm thử.

### 10.2. Nhiều sources có thể dùng trong một chain không?

Một chain thường được cấu hình một nguồn CORS được truyền vào DSL. Nếu cần nhiều policy theo URL, nguồn đó có thể là `UrlBasedCorsConfigurationSource` chứa nhiều path registrations, hoặc một `CorsConfigurationSource` tùy biến có logic lựa chọn rõ ràng.

**Không** nên tưởng rằng khai báo nhiều bean sẽ khiến CORS tự gộp các nguồn thành danh sách. Nếu cần logic phối hợp, phải thiết kế tường minh, kiểm soát thứ tự ưu tiên và test khi các path/policy chồng lấn.

## 11. Kiểm thử Servlet: chain nào thật sự xử lý preflight?

Một chính sách tốt phải chứng minh ít nhất bốn điều:

- Origin app được phép gọi `/api/**`.
- Origin admin được phép gọi `/admin/**`.
- Origin app **không** được cấp quyền CORS cho `/admin/**`.
- Origin admin **không** được cấp quyền CORS cho `/api/**`.

### 11.1. Ma trận kiểm thử

Với cấu hình Servlet mục 5:

| Path | Origin | Actual method được hỏi | Kỳ vọng |
| --- | --- | --- | --- |
| `/api/orders` | `https://app.example.com` | `POST` | Preflight hợp lệ nếu headers phù hợp |
| `/api/profile` | `https://app.example.com` | `PUT` | Preflight hợp lệ nếu headers phù hợp |
| `/api/orders` | `https://admin.example.com` | `POST` | Từ chối origin ở source API |
| `/admin/users` | `https://admin.example.com` | `POST` | Preflight hợp lệ nếu headers phù hợp |
| `/admin/users` | `https://app.example.com` | `POST` | Từ chối origin ở source Admin |
| `/admin/users` | `https://admin.example.com` | `PUT` | Từ chối method, Admin không cho PUT |
| `/api/orders` | `https://app.example.com` | `DELETE` | Từ chối method, API không cho DELETE |
| `/api/orders` | `https://app.example.com` | `POST` và `x-admin-override` | Từ chối header không trong allowlist |
| `/other/path` | `https://app.example.com` | `POST` | Không thuộc nguồn CORS được khai báo |

Các dòng “từ chối” mô tả **preflight**. Với request không cần preflight, browser có thể đã gửi actual request trước khi quyết định không cho JavaScript đọc response; CORS không phải biện pháp từ chối mọi kết nối tới server.

### 11.2. Test MockMvc

Với Spring Boot, Spring Security và hai sources/chains ở mục 5, một bộ kiểm thử tích hợp minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MultiChainServletCorsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiChainAllowsAppOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void adminChainAllowsAdminOrigin() throws Exception {
        mvc.perform(options("/admin/users")
                .header("Origin", "https://admin.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://admin.example.com"));
    }

    @Test
    void apiChainRejectsAdminOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://admin.example.com")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminChainRejectsAppOrigin() throws Exception {
        mvc.perform(options("/admin/users")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminChainRejectsPutMethod() throws Exception {
        mvc.perform(options("/admin/users")
                .header("Origin", "https://admin.example.com")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các bài test trên giả định CORS processor mặc định của Spring đang xử lý preflight (thành công trả 200, trường hợp không hợp lệ thường trả 403). Đó là **ví dụ chưa chạy trên dự án cụ thể**; nếu gateway/custom filters đổi trạng thái, cần cập nhật kỳ vọng nhưng vẫn phải kiểm tra browser không được cấp quyền CORS cho trường hợp bị từ chối.

**Bổ sung test actual request:** sau preflight thành công, một actual `POST /admin/users` không có quyền admin vẫn phải bị từ chối theo authentication/authorization. Chỉ kiểm tra preflight thành công **không chứng minh endpoint đã được bảo vệ**.

### 11.3. Kiểm tra một chain matcher chỉ nhận POST

Một test regression quan trọng khi trước đây security matcher dùng method:

~~~java
@Test
void preflightForPostStillEntersApiCorsChain() throws Exception {
    mvc.perform(options("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Access-Control-Allow-Origin", "https://app.example.com"));
}
~~~

Nếu matcher chỉ khớp method POST, test này có thể phát hiện OPTIONS đã vào sai chain. Khi dùng `securityMatcher("/api/**")`, preflight có thể được xử lý trong đúng chain mà không cần thêm authentication exemption tùy tiện.

## 12. Kiểm thử Reactive bằng WebTestClient

Với cấu hình WebFlux mục 9, cách kiểm thử tương ứng là `WebTestClient`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.HttpHeaders.*;

@SpringBootTest
@AutoConfigureWebTestClient
class MultiChainReactiveCorsTest {

    @Autowired
    WebTestClient client;

    @Test
    void appOriginPassesApiPreflight() {
        client.options()
            .uri("/api/orders")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com");
    }

    @Test
    void adminOriginPassesAdminPreflight() {
        client.options()
            .uri("/admin/users")
            .header(ORIGIN, "https://admin.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://admin.example.com");
    }

    @Test
    void appOriginCannotReadAdminPreflight() {
        client.options()
            .uri("/admin/users")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminOriginCannotReadApiPreflight() {
        client.options()
            .uri("/api/orders")
            .header(ORIGIN, "https://admin.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đây cũng là bộ test minh họa **chưa chạy**. `WebTestClient` kiểm tra response HTTP trong ứng dụng Reactive nhưng không tự thực thi toàn bộ SOP/CORS, giới hạn cookie bên thứ ba hoặc preflight cache của browser. Kiểm thử end-to-end cần thêm browser tại đúng origin và đường đi gateway thực tế.

## 13. Debug bằng curl và DevTools

### 13.1. Kiểm tra API preflight

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Kỳ vọng source API cấp origin `https://app.example.com` và hỗ trợ headers/method tương ứng.

### 13.2. Thử origin của chain khác

~~~bash
curl -i -X OPTIONS "https://api.example.com/admin/users" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST"
~~~

Request vào **admin chain** theo path, nhưng origin app không thuộc source Admin. Cần bảo đảm response không cấp quyền CORS cho app.

### 13.3. Thử origin đúng với admin

~~~bash
curl -i -X OPTIONS "https://api.example.com/admin/users" \
  -H "Origin: https://admin.example.com" \
  -H "Access-Control-Request-Method: POST"
~~~

Nếu thành công, đối chiếu `Access-Control-Allow-Origin` và `Access-Control-Allow-Methods` thực tế.

`curl` chỉ mô phỏng HTTP; nó không có browser SOP/CORS và có thể tự đặt `Origin`. Vì vậy curl thấy response không có nghĩa JavaScript của một origin bất kỳ đọc được body.

### 13.4. Quy trình DevTools

1. Mở Network ở frontend thật; tìm preflight OPTIONS và actual request tương ứng.
2. Xác định URL path, `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. Đối chiếu **chain được chọn**: matcher và `@Order` áp dụng cho request OPTIONS thực tế.
4. Xem source mà chain dùng qua `cors.configurationSource(...)`; kiểm tra path registrations và allowlist.
5. Xem preflight response. HTTP 200 **không đủ** nếu thiếu header CORS phù hợp.
6. Nếu preflight đạt, kiểm tra actual request và response 401/403/500; bảo đảm còn authentication, authorization và CSRF.
7. Nếu cookie thiếu, điều tra Fetch `credentials` cùng `SameSite`, `Secure`, Domain/Path và chính sách trình duyệt.
8. Nếu lỗi chỉ xuất hiện qua gateway/CDN, so sánh phản hồi trước và sau proxy, đặc biệt route OPTIONS và header trùng.

## 14. Lỗi điển hình khi có nhiều sources và chains

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| Thêm bean CORS thứ hai thì preflight lỗi | Spring Security không tự chọn một `CorsConfigurationSource` giữa nhiều bean | Chỉ định `configurationSource(...)` cho từng chain |
| Chỉ API chạy, admin OPTIONS trả 401 | Admin chain chưa bật CORS hoặc bị filter khác chặn | Kiểm tra chain matcher và CORS DSL của admin |
| Admin request nhận policy API | `@Order`/matcher chồng lấn; fallback đứng trước; gắn sai source | Test chain selection và `@Qualifier` |
| OPTIONS hỏi PUT nhưng vào fallback | Matcher của chain API chỉ khớp HTTP PUT | Match chain theo path để nhận cả OPTIONS |
| OPTIONS 200 nhưng browser báo lỗi | Thiếu `Access-Control-Allow-Origin`/Methods/Headers hoặc credentials | So response preflight với request |
| Preflight 403 `Invalid CORS request` | Origin/method/header/path không phù hợp | Kiểm tra `CorsConfiguration` của chain thực sự |
| Preflight thành công, actual PUT 403 | CSRF hoặc phân quyền trên actual request | Kiểm tra session/token, CSRF, quyền endpoint |
| Response có nhiều `Access-Control-Allow-Origin` | Gateway/filter/MVC/Security cùng xử lý | Thống nhất nguồn CORS cho response cuối |
| App origin đọc được dữ liệu admin trong browser | Source Admin quá rộng hoặc gateway phản chiếu Origin | Siết allowlist, kiểm tra credentials và dữ liệu trả về |
| Request ngoài `/api/**`/`/admin/**` được trả CORS bất ngờ | Có global MVC/WebFlux policy hoặc wildcard fallback filter | Kiểm kê mọi nơi phát CORS headers |
| Local dev đổi port đột nhiên lỗi | Port thuộc origin, không nằm trong allowlist | Khai báo đúng origin dev, không mở wildcard production |
| Request tới backend khác URL public | Gateway path rewrite làm matcher/source không khớp | Kiểm tra URL nội bộ nhận được và route mapping |
| Lúc đúng lúc sai qua cache | `Vary: Origin` thiếu, cache trộn origin/user, nhiều instance khác cấu hình | Kiểm tra cache key, response header và triển khai |
| Cookie không được gửi dù CORS đúng | Fetch mặc định `same-origin` hoặc cookie policy | Kiểm tra browser Cookies và credentials mode |

### 14.1. Một nguyên tắc khi đọc lỗi

**Phân tách hai thất bại:**

- **CORS/preflight thất bại:** browser không gửi actual request sau preflight bị chặn; kiểm tra policy/chain/filter/gateway.
- **Actual request bị Security từ chối:** browser đã gửi actual request, nhưng thiếu authentication/authorization/CSRF. Nếu CORS headers của actual response hợp lệ, JavaScript có thể đọc HTTP 401/403.

CORS source và security chain cần phối hợp, nhưng không nên dùng CORS để “chữa” một lỗi phân quyền thực tế.

## 15. Checklist triển khai nhiều nguồn cấu hình

- [ ] Có lý do rõ ràng để dùng nhiều `CorsConfigurationSource`; nếu một source theo URL là đủ, không tách cho phức tạp.
- [ ] Mỗi source có tên và phạm vi path/origin/method/header cụ thể.
- [ ] Mỗi chain liên quan gắn nguồn bằng `cors(cors -> cors.configurationSource(...))` thay vì dựa vào auto-selection khi có nhiều bean.
- [ ] Nếu tiêm dependency theo interface, đã dùng `@Qualifier` đúng bean để tránh nhầm source.
- [ ] Thứ tự `@Order` được kiểm tra; matcher cụ thể trước fallback.
- [ ] Preflight `OPTIONS` được chọn vào chain có CORS xử lý đủ sớm, không bị method-only matcher bỏ sót.
- [ ] Origin app không được cấp quyền CORS ở admin, và ngược lại, trừ khi chính sách có chủ đích khác.
- [ ] Request ngoài phạm vi API không vô tình nhận một wildcard global CORS policy.
- [ ] Dữ liệu cá nhân và session cookie không được cấp quyền CORS rộng bằng `allowedOriginPatterns("*")`.
- [ ] CORS của MVC/WebFlux handler, filter độc lập và gateway không xung đột với nguồn trên chain.
- [ ] Actual request vẫn có authentication, authorization, CSRF và bảo vệ session.
- [ ] Có test preflight dương/âm và actual response, bao gồm 401/403, cookie và DevTools.
- [ ] Proxy path rewrite, cache `Vary: Origin` và các instance production được kiểm tra.

## 16. Câu hỏi vận dụng có lời giải

**Tình huống A.** Ứng dụng có `apiCorsSource` và `adminCorsSource` cùng là bean `CorsConfigurationSource`. Cả hai `SecurityFilterChain` chỉ gọi `http.cors(Customizer.withDefaults())`. Điều gì có thể xảy ra?

**Trả lời:** Spring Security không có căn cứ tự động rõ ràng để chọn nguồn đúng cho từng chain. Cần gắn `configurationSource(apiCors)` và `configurationSource(adminCors)` tường minh, rồi kiểm thử.

**Tình huống B.** Chain fallback `securityMatcher("/**")` có `@Order(1)`; chain admin có `@Order(2)`. Vì sao admin source không có hiệu lực?

**Trả lời:** Fallback khớp request trước, khiến chain admin không được chọn. Đặt chain cụ thể ưu tiên cao hơn và fallback sau.

**Tình huống C.** Một chain chỉ khớp HTTP POST, nhưng frontend gửi POST JSON cần preflight. Preflight rơi vào đâu?

**Trả lời:** Preflight là HTTP OPTIONS, nên không khớp matcher chỉ chấp nhận POST. Cần bảo đảm OPTIONS và actual request cùng được CORS xử lý trong phạm vi thích hợp, thường bằng matcher theo path.

**Tình huống D.** Frontend `https://admin.example.com` gọi `/api/orders`. Vì được phép ở source admin, liệu được cấp CORS tại path API không?

**Trả lời:** Không. `/api/orders` đi vào chain và source API; phải khớp chính sách của API. Quyền CORS của admin path không được kế thừa.

**Tình huống E.** Source API cho phép `POST`, nhưng actual POST không có CSRF token và bị 403. Có nên thêm POST vào `allowedMethods` lần nữa?

**Trả lời:** Không. CORS đã cho phép preflight; thất bại nằm ở CSRF hoặc phân quyền của actual request.

**Tình huống F.** Spring Security chain admin từ chối origin app, nhưng gateway trả `Access-Control-Allow-Origin` bằng mọi `Origin` nhận được. Có an toàn không?

**Trả lời:** Không. Chính sách CORS bị chồng chéo và có thể làm thay đổi quyền đọc response ngoài ý muốn; cần xác định một chính sách cuối nhất quán và không phản chiếu origin tùy ý, nhất là với credentials.

**Tình huống G.** Với WebFlux, có thể dùng `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet cho `ServerHttpSecurity.cors(...)` không?

**Trả lời:** Không. WebFlux dùng nguồn CORS thuộc `org.springframework.web.cors.reactive` và làm việc với `ServerWebExchange`.

**Tình huống H.** Hai chains có cấu hình CORS riêng hoạt động trong MockMvc, nhưng qua CDN một số response trả header khác nhau. Nên bắt đầu điều tra ở đâu?

**Trả lời:** So request/response HTTP ở backend trực tiếp và qua CDN, đặc biệt OPTIONS, path rewrite, cache key, `Vary: Origin` và các CORS headers do gateway chèn. Unit/integration test trong ứng dụng không mô phỏng hết tầng ngoài.

---

**Ghi nhớ:** **Security chain chọn bộ lọc nào xử lý request; `CorsConfigurationSource` chọn chính sách CORS nào cho request đó.** Khi có nhiều nguồn, hãy chỉ định source **tường minh cho từng Servlet `SecurityFilterChain` hoặc Reactive `SecurityWebFilterChain`**, kiểm soát `@Order`, matcher và request preflight OPTIONS. Kiểm thử không chỉ frontend được phép mà cả đường truy cập chéo giữa các nhóm API. CORS cho browser đọc response; authentication, authorization, CSRF và bảo vệ session vẫn là trách nhiệm bảo mật độc lập của server.
