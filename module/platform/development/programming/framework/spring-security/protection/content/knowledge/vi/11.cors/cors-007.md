# CorsConfigurationSource và UrlBasedCorsConfigurationSource

## 1. Bài toán: chọn đúng chính sách CORS cho từng URL

Một ứng dụng Spring Security phục vụ REST API ở `https://api.example.com`. Frontend chính thức ở `https://app.example.com` gọi `/api/orders`; giao diện quản trị ở `https://admin.example.com` gọi `/admin/reports`. Cả hai cần kết nối từ JavaScript trong trình duyệt, nhưng phạm vi tin cậy không giống nhau:

- API nghiệp vụ cho frontend có thể hỗ trợ `GET`, `POST` với một số request header.
- API quản trị chỉ nên cấp quyền CORS cho origin quản trị.
- Những đường dẫn ngoài API có thể không cần chính sách CORS nào.
- Preflight `OPTIONS` phải được xử lý đúng trước khi cơ chế xác thực chặn request vì không có cookie/token.

Spring Framework giải quyết bài toán **chọn cấu hình phù hợp cho từng request** bằng giao diện `CorsConfigurationSource`. Một triển khai thường dùng là `UrlBasedCorsConfigurationSource`, cho phép đăng ký `CorsConfiguration` theo mẫu đường dẫn như `/api/**`.

Trong mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, đây là lớp cấu hình quan trọng để phối hợp CORS với authentication, authorization, CSRF, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Người học cần hiểu việc tích hợp trong **Servlet/Spring MVC** và **Reactive/WebFlux**, đồng thời phân biệt cấu hình CORS với bảo mật thực tế của endpoint.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Nêu chính xác trách nhiệm của `CorsConfiguration`, `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource` và thành phần xử lý CORS.
2. Dựng một nguồn cấu hình CORS theo đường dẫn URL, bật nó qua `HttpSecurity` hoặc `ServerHttpSecurity`.
3. Giải thích luồng actual request và preflight `OPTIONS` đi qua chuỗi bảo mật.
4. Tránh nhầm lẫn giữa source Servlet và source Reactive có tên lớp giống nhau.
5. Xây ma trận kiểm thử theo origin, URL, method, header và credentials; chẩn đoán xung đột với gateway, Spring MVC và nhiều security chains.

Các hostname thuộc `example.com` và `example.org` ở đây là ví dụ minh họa, không phải API có thể truy cập thực tế.

## 2. Bốn thành phần có trách nhiệm khác nhau

| Thành phần | Thuộc lớp nào | Trả lời câu hỏi |
| --- | --- | --- |
| `CorsConfiguration` | **Dữ liệu chính sách** | Origin, method, request header, response header và credentials nào được cho phép? |
| `CorsConfigurationSource` | **Chọn chính sách** | Với request hiện tại, cần dùng `CorsConfiguration` nào? |
| `UrlBasedCorsConfigurationSource` | **Cách chọn chính sách theo URL** | Path của request khớp với cấu hình đăng ký nào? |
| `CorsFilter` / xử lý CORS của WebFlux và Spring Security | **Thực thi CORS** | Request/response có đạt kiểm tra CORS, có cần trả lời preflight và thêm header tương ứng không? |

Một điểm rất dễ nhầm: `UrlBasedCorsConfigurationSource` **không phải nơi xác thực user**, cũng không phải nơi browser thực thi Same-Origin Policy. Nó chủ yếu ánh xạ request path sang cấu hình CORS. Logic so khớp origin, method và headers được thực hiện bởi bộ xử lý CORS trên cấu hình đó.

Mối quan hệ khái niệm:

~~~mermaid
flowchart TD
    A["HTTP request tới Spring"] --> B["CORS filter / CORS integration"]
    B --> C["CorsConfigurationSource"]
    C --> D["UrlBasedCorsConfigurationSource: tìm policy theo path"]
    D --> E{"Có CorsConfiguration phù hợp?"}
    E -- "Có" --> F["CORS processor kiểm tra Origin, method, headers"]
    E -- "Không" --> G["Không có policy CORS cho path này"]
    F --> H{"Preflight hợp lệ?"}
    H -- "Có" --> I["Trả lời OPTIONS bằng CORS headers"]
    H -- "Không" --> J["Từ chối preflight"]
    F --> K["Actual request: xử lý CORS và chuyển tiếp khi phù hợp"]
    K --> L["Authentication / authorization / CSRF / endpoint"]
~~~

Đây là sơ đồ trách nhiệm logic; đường đi cụ thể phụ thuộc stack Servlet/Reactive và việc request là preflight hay actual request. Một request không mang `Origin` có thể là request HTTP thông thường và không cần xử lý như CORS request.

### 2.1. `CorsConfiguration` mô tả cái gì?

Ví dụ một chính sách:

~~~java
import java.util.List;
import org.springframework.web.cors.CorsConfiguration;

CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("https://app.example.com"));
config.setAllowedMethods(List.of("GET", "POST", "PUT"));
config.setAllowedHeaders(List.of(
    "Authorization", "Content-Type", "X-CSRF-TOKEN"
));
config.setExposedHeaders(List.of("X-Request-Id"));
config.setAllowCredentials(true);
config.setMaxAge(600L);
~~~

Ý nghĩa:

- `allowedOrigins` là **origin của frontend** được browser cho phép đọc phản hồi cross-origin. Giá trị cần có scheme và host, thêm port nếu không dùng port mặc định.
- `allowedMethods` liệt kê HTTP methods được phép qua kiểm tra preflight.
- `allowedHeaders` liệt kê request headers được phép nếu preflight yêu cầu.
- `exposedHeaders` cho phép JavaScript đọc thêm các **response headers** ngoài nhóm mặc định.
- `allowCredentials(true)` hỗ trợ browser chia sẻ response của request ở credentials mode `include`, khi các điều kiện CORS còn lại đạt.
- `maxAge` là số giây browser có thể cache kết quả preflight, chịu giới hạn của từng trình duyệt.

Các trường trên là quyền CORS, **không** tạo user, session, endpoint hay quyền truy cập database.

### 2.2. `CorsConfigurationSource` nhận request, trả chính sách

Ở Servlet, giao diện dùng phương thức dạng:

~~~java
CorsConfiguration getCorsConfiguration(
    jakarta.servlet.http.HttpServletRequest request
);
~~~

Nó trả một `CorsConfiguration` phù hợp hoặc `null` nếu không tìm thấy chính sách. `null` **không có nghĩa mọi origin được phép**. Khi một preflight đến đường dẫn không có cấu hình CORS, bộ xử lý CORS mặc định có thể từ chối nó; với actual request, kết quả phụ thuộc đường xử lý nhưng browser vẫn không được đọc response nếu thiếu CORS headers hợp lệ.

Ở Reactive, nguồn CORS dùng kiểu request khác:

~~~java
CorsConfiguration getCorsConfiguration(
    org.springframework.web.server.ServerWebExchange exchange
);
~~~

Hai API không thể tùy tiện hoán đổi dù có cùng tên `CorsConfigurationSource`. Các import chính xác sẽ được minh họa ở phần Servlet và Reactive.

## 3. `UrlBasedCorsConfigurationSource` ánh xạ chính sách theo path

Khi API có nhiều nhóm endpoint, bạn không cần tự viết `if/else` kiểm tra từng URL. Có thể đăng ký các mẫu đường dẫn:

~~~java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

UrlBasedCorsConfigurationSource source =
    new UrlBasedCorsConfigurationSource();

source.registerCorsConfiguration("/api/**", publicFrontendPolicy);
source.registerCorsConfiguration("/admin/**", adminFrontendPolicy);
~~~

Ở đây:

- Request `/api/orders` hoặc `/api/profile` nhận chính sách `publicFrontendPolicy`.
- Request `/admin/reports` nhận chính sách `adminFrontendPolicy`.
- Request `/assets/logo.svg` không nhận chính sách nào qua hai mục đăng ký trên.

Tên `publicFrontendPolicy` chỉ là biến Java minh họa; dù API gọi là public hay private, **bảo mật thực tế vẫn do authentication và authorization quyết định**.

**Phân biệt hai loại pattern:**

| Mục đích | Ví dụ | So khớp cái gì? |
| --- | --- | --- |
| Đăng ký URL trong `UrlBasedCorsConfigurationSource` | `"/api/**"` | **Path request tới API**, chẳng hạn `/api/orders` |
| `CorsConfiguration#setAllowedOrigins` | `"https://app.example.com"` | **Origin của trang gọi** |
| `CorsConfiguration#setAllowedOriginPatterns` | `"https://*.ui.example.com"` | **Origin của trang gọi** theo pattern được Spring hỗ trợ |

Đưa `https://app.example.com/dashboard` vào `registerCorsConfiguration` là nhầm: giá trị đăng ký ở đây là **đường dẫn của API**, không phải URL đầy đủ của frontend.

### 3.1. Đường dẫn phải thực sự khớp

Ví dụ một cấu hình chỉ đăng ký:

~~~java
source.registerCorsConfiguration("/api/**", config);
~~~

Preflight tới `/api/orders` có cơ hội tìm thấy chính sách đó. Preflight tới `/admin/reports` hoặc `/health` không được cấu hình này bao phủ.

Cần lưu ý khi hệ thống có servlet context path, reverse proxy rewrite, gateway prefix, router hoặc nhiều servlet mapping: đường dẫn mà nguồn CORS thực tế so khớp có thể khác URL mà frontend nhìn thấy. Hãy kiểm tra path được chuyển tới ứng dụng sau khi qua các lớp routing thay vì đoán theo địa chỉ bên ngoài.

### 3.2. Không dựa vào thứ tự hoặc cách gộp cấu hình chồng lấn

Giả sử đăng ký cả `"/**"` và `"/admin/**"`. Đừng mặc định hai cấu hình sẽ được cộng dồn hay luôn chọn chính sách chặt hơn theo trực giác. Cách xác định cấu hình áp dụng còn liên quan cơ chế matching và thiết lập nguồn CORS ở phiên bản framework.

Để dễ kiểm tra, ưu tiên **các tập path không chồng lấn**, chẳng hạn `/api/**` và `/admin/**`, hoặc xác minh bằng test rõ ràng khi buộc phải dùng các mẫu chồng lấn.

## 4. Cấu hình đầy đủ cho Servlet / Spring MVC

Dưới đây là cách thực tế để đưa chính sách CORS vào Spring Security Servlet. Ví dụ tạo nguồn cấu hình cho hai nhóm URL có quyền CORS khác nhau:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration api = new CorsConfiguration();
        api.setAllowedOrigins(List.of("https://app.example.com"));
        api.setAllowedMethods(List.of("GET", "POST", "PUT"));
        api.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        api.setExposedHeaders(List.of("X-Request-Id"));
        api.setAllowCredentials(true);
        api.setMaxAge(600L);

        CorsConfiguration admin = new CorsConfiguration();
        admin.setAllowedOrigins(List.of("https://admin.example.com"));
        admin.setAllowedMethods(List.of("GET", "POST"));
        admin.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        admin.setAllowCredentials(true);
        admin.setMaxAge(300L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", api);
        source.registerCorsConfiguration("/admin/**", admin);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        CorsConfigurationSource corsConfigurationSource
    ) throws Exception {
        return http
            .cors(cors -> cors.configurationSource(corsConfigurationSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**", "/admin/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Các quyết định cần chú ý:

1. `@Bean CorsConfigurationSource` tạo nguồn cấu hình để Spring Security sử dụng.
2. `registerCorsConfiguration("/api/**", api)` ràng buộc **chính sách API** với các endpoint tương ứng; `"/admin/**"` được một chính sách khác.
3. `http.cors(cors -> cors.configurationSource(...))` chỉ rõ nguồn CORS sử dụng trong **security filter chain**. Cách viết tường minh hữu ích nếu ứng dụng có nhiều nguồn cấu hình hoặc nhiều filter chains.
4. `authorizeHttpRequests` tiếp tục kiểm tra **quyền truy cập endpoint**. CORS thành công không làm mất hiệu lực `authenticated()` hay `denyAll()`.
5. Spring Security cần có cơ chế xác thực phù hợp với hệ thống thật (form login, session, OAuth2 resource server hoặc cách khác). Đoạn mã trên tập trung vào CORS nên **chưa triển khai toàn bộ cơ chế đăng nhập**.
6. CSRF protection của Spring Security cần được cấu hình phù hợp với mô hình ứng dụng. **Không tắt CSRF chỉ để tránh lỗi preflight** khi API xác thực bằng cookie phiên.

Nếu ứng dụng chỉ có một nguồn `CorsConfigurationSource` phù hợp, có thể dùng `http.cors(Customizer.withDefaults())`. Cách cấu hình tường minh giúp người đọc biết chính xác policy nào đang được áp dụng, nhất là dự án có nhiều bean hoặc cấu hình MVC khác nhau.

### 4.1. Không dùng wildcard origin cùng credentials

Với request `fetch(..., { credentials: "include" })`, response không được dùng `Access-Control-Allow-Origin: *` để cho JavaScript đọc dữ liệu.

Sai:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true);
~~~

Đây là kết hợp không hợp lệ; Spring có thể báo lỗi khi áp dụng chính sách. Trong ví dụ Servlet ở trên, `allowedOrigins` là danh sách các origin cụ thể. `allowedOriginPatterns` cũng có thể hoạt động với credentials vì Spring trả origin đã khớp, nhưng phải kiểm soát phạm vi hostname được tin cậy, đặc biệt khi có subdomain do người dùng tự quản lý.

### 4.2. `applyPermitDefaultValues()` có phù hợp không?

`CorsConfiguration` có phương thức `applyPermitDefaultValues()` để tạo bộ giá trị mặc định tiện dùng, trong đó có phạm vi origin/header rộng cho nhiều trường hợp. Nó không phải một **mẫu chính sách an toàn mặc định cho API chứa dữ liệu cá nhân**.

~~~java
CorsConfiguration config = new CorsConfiguration();
config.applyPermitDefaultValues();

// Thu hẹp lại theo hệ thống thật trước khi dùng cho dữ liệu nhạy cảm.
config.setAllowedOrigins(List.of("https://app.example.com"));
config.setAllowedMethods(List.of("GET", "POST"));
config.setAllowedHeaders(List.of("Content-Type", "Authorization"));
~~~

Cần hiểu chính xác những giá trị mà phương thức này đặt và kiểm tra lại policy sau khi ghi đè. Với API production, khai báo rõ từng quyền như ví dụ chính thường dễ kiểm soát hơn.

## 5. Request đi qua nguồn CORS như thế nào?

Xét frontend tại `https://app.example.com` gọi API để cập nhật hồ sơ:

~~~javascript
await fetch("https://api.example.com/api/profile", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "<csrf-token>"
  },
  body: JSON.stringify({ displayName: "Lan" })
});
~~~

Vì `PUT` và `Content-Type: application/json` không thuộc điều kiện CORS-safelisted tương ứng, browser cần preflight:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Luồng logic trong Spring Security Servlet:

1. Request `OPTIONS /api/profile` đến chuỗi filter có cấu hình CORS.
2. Bộ xử lý CORS hỏi `CorsConfigurationSource` lấy chính sách cho request.
3. `UrlBasedCorsConfigurationSource` thấy `/api/profile` khớp `/api/**` và trả về `api` `CorsConfiguration`.
4. Bộ xử lý CORS kiểm tra `Origin` có được phép, `PUT` có trong `allowedMethods`, các header được hỏi có trong `allowedHeaders` không.
5. Nếu hợp lệ, CORS trả lời preflight kèm các header được phép; browser có thể gửi actual `PUT`.
6. **Actual PUT** mới đi qua các lớp authentication, authorization và CSRF thích hợp của ứng dụng.

Ví dụ preflight response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Trên actual response, API phải tiếp tục cho phép browser đọc theo CORS:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Preflight thông thường **không mang credentials của actual request**. Nếu security filter đòi cookie hoặc bearer token ngay ở bước OPTIONS, browser có thể không bao giờ gửi được request chính. Đó là lý do cần xử lý CORS **trước** các bước bảo mật yêu cầu xác thực.

### 5.1. Source theo URL chỉ chọn policy; CORS processor quyết định chấp nhận

Nếu người dùng mở một trang tại `https://evil.example.org`, request có thể vẫn khớp **path** `/api/profile` và do đó source vẫn trả cùng cấu hình `api`. Nhưng `api.allowedOrigins` không có `https://evil.example.org`, nên bộ xử lý CORS từ chối preflight hoặc không cấp quyền đọc response.

Đây là sự khác biệt có chủ đích:

- **Path matching:** chọn tập quy tắc cần kiểm tra.
- **Origin/method/header matching:** quyết định request CORS có được phép trong tập quy tắc đó không.

### 5.2. Nếu URL không có cấu hình?

Giả sử chỉ đăng ký `/api/**` và `/admin/**`. Request tới `/internal/metrics` không nhận chính sách từ nguồn CORS đó.

Với preflight đến path không có CORS policy, xử lý mặc định có thể từ chối request. Với request thông thường, server có thể vẫn trả HTTP status/body tùy route và security chain, nhưng browser không chia sẻ cross-origin response nếu không có CORS header phù hợp.

**Không đánh đồng absence of CORS configuration với `permitAll()` hay `denyAll()` về authorization.** Đó là những quyết định bảo mật khác, cần cấu hình riêng.

## 6. Reactive / WebFlux: cùng ý tưởng, kiểu request khác

Trong Reactive stack, Spring dùng package:

- `org.springframework.web.cors.reactive.CorsConfigurationSource`
- `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`

Nguồn CORS ở đây làm việc với `ServerWebExchange`. Không nhập nhằng chúng với `org.springframework.web.cors.CorsConfigurationSource` và `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet.

Ví dụ cấu hình với `ServerHttpSecurity`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsSecurityConfiguration {

    @Bean
    CorsConfigurationSource reactiveCorsConfigurationSource() {
        CorsConfiguration api = new CorsConfiguration();
        api.setAllowedOrigins(List.of("https://app.example.com"));
        api.setAllowedMethods(List.of("GET", "POST", "PUT"));
        api.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        api.setExposedHeaders(List.of("X-Request-Id"));
        api.setAllowCredentials(true);
        api.setMaxAge(600L);

        CorsConfiguration admin = new CorsConfiguration();
        admin.setAllowedOrigins(List.of("https://admin.example.com"));
        admin.setAllowedMethods(List.of("GET", "POST"));
        admin.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        admin.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", api);
        source.registerCorsConfiguration("/admin/**", admin);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        CorsConfigurationSource reactiveCorsConfigurationSource
    ) {
        return http
            .cors(cors -> cors.configurationSource(reactiveCorsConfigurationSource))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/**", "/admin/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Luồng browser và ý nghĩa policy giống Servlet. Sự khác biệt quan trọng là cơ chế xử lý request trong WebFlux và các lớp nguồn CORS reactive.

Trong ứng dụng Reactive, một cách tổ chức khác là dùng `CorsWebFilter` với nguồn CORS reactive. Khi đó phải kiểm soát **thứ tự filter** so với Spring Security và tránh cùng lúc chèn các response headers CORS từ nhiều nơi. Một ví dụ sử dụng trực tiếp qua `ServerHttpSecurity.cors(...)` như trên giúp nhìn thấy mối liên hệ giữa security chain và policy source.

Session/CSRF trên Reactive cần được cấu hình theo các API bảo mật reactive tương ứng; không giả định cấu hình servlet session cookie sẽ tự áp dụng.

## 7. Một source hay nhiều source? Những lựa chọn triển khai

### 7.1. Dùng một source có nhiều đường dẫn

Khi các endpoint thuộc một ứng dụng và cấu hình CORS có thể phân chia theo path, một `UrlBasedCorsConfigurationSource` thường dễ quan sát:

~~~java
UrlBasedCorsConfigurationSource source =
    new UrlBasedCorsConfigurationSource();

source.registerCorsConfiguration("/api/**", apiCors);
source.registerCorsConfiguration("/admin/**", adminCors);
~~~

Mỗi cấu hình có thể chọn origin, method, headers và credentials khác nhau. Hãy giữ path patterns rõ ràng, test phản hồi tại **mỗi nhóm route** và xem chúng có cần được bảo vệ bởi các security chains khác nhau không.

### 7.2. Nếu có nhiều SecurityFilterChain

Một ứng dụng Servlet có thể có nhiều `SecurityFilterChain` với `securityMatcher(...)` khác nhau. Mỗi chain có thể có tập rule authorization và nguồn CORS riêng. Cần đảm bảo **chain thực sự khớp request** đã bật CORS hoặc có filter CORS phù hợp trong pipeline.

Ví dụ về ý tưởng cấu hình:

~~~java
// Minh họa ý tưởng: mỗi chain gắn với nguồn CORS đúng phạm vi.
http.securityMatcher("/api/**")
    .cors(cors -> cors.configurationSource(apiCorsSource));
~~~

Đoạn trên chỉ là một phần của cấu hình chain; một bean `SecurityFilterChain` hoàn chỉnh còn cần `build()` và các rule bảo mật liên quan. Đừng chỉ đăng ký `CorsConfigurationSource` bean rồi mặc định tất cả chains và gateway đều tự áp dụng giống nhau.

Nếu Spring context có **nhiều bean `CorsConfigurationSource`**, Spring Security không nhất thiết tự chọn đúng bean. Trong trường hợp đó, cấu hình tường minh `cors.configurationSource(...)` cho chain liên quan giúp tránh mơ hồ.

### 7.3. Nếu đã dùng `@CrossOrigin` hoặc `WebMvcConfigurer`

Spring MVC hỗ trợ khai báo CORS trong controller bằng `@CrossOrigin`, hoặc global MVC config qua `WebMvcConfigurer#addCorsMappings`:

~~~java
// Ví dụ ý tưởng MVC (Servlet):
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST");
}
~~~

Spring Security có thể tích hợp với cấu hình CORS của MVC trong trường hợp phù hợp (chẳng hạn khi MVC hiện diện và không có nguồn CORS riêng được cung cấp). Tuy nhiên khi hệ thống đã dùng `CorsConfigurationSource` riêng, cần xác định đâu là nguồn chính sách thực sự đang được Security sử dụng.

**Không mặc định cấu hình ở controller sẽ tự sửa mọi preflight bị filter xác thực chặn trước đó.** CORS phải được xử lý đủ sớm. Đồng thời tránh khai báo ở MVC, Spring Security, gateway và reverse proxy những allowlist khác nhau, dẫn đến response thiếu hoặc trùng `Access-Control-Allow-Origin`.

### 7.4. Khi cần chính sách động

Một ứng dụng đa tenant có thể cần allowlist origin phụ thuộc tenant đã được xác minh. Vì `CorsConfigurationSource` là giao diện, có thể xây dựng triển khai riêng theo route hoặc registry chính sách được quản trị.

Nguyên tắc:

- Chọn chính sách theo thông tin đáng tin cậy của ứng dụng và path/tenant được xác định.
- Đối chiếu origin của request với **allowlist đã được xác minh và có cơ chế thu hồi**.
- Không làm kiểu “đọc `Origin` nào thì lập tức tạo policy cho phép origin đó” khi API chứa dữ liệu nhạy cảm.
- Vẫn kiểm soát quyền truy cập dữ liệu tenant bằng authentication và authorization; chỉ allowlist CORS là chưa đủ.

Với nhiều tenant có hostname do họ tự vận hành, việc xác minh quyền sở hữu domain và phân quyền tenant quan trọng hơn việc viết một pattern mở toàn bộ `https://*`.

## 8. Sai khác giữa policy source và bảo mật endpoint

Một số tình huống phải hiểu rõ:

| Tình huống | Source / CORS xử lý | Bảo mật endpoint xử lý |
| --- | --- | --- |
| Frontend đúng origin gọi `GET /api/products` | Chọn policy `/api/**`, cấp quyền đọc khi hợp lệ | Có thể cho phép public hoặc bắt login theo rule |
| Frontend không tin cậy gọi `GET /api/me` | Không cấp quyền JavaScript đọc response | Vẫn phải xác thực và phân quyền request trên server |
| Browser hỏi `OPTIONS /api/orders` | Preflight xét origin/method/headers và trả lời khi hợp lệ | Không nên đòi cookie/token của actual request tại bước preflight |
| Người dùng thường thực hiện `PUT /admin/users` | Policy admin có thể cho origin quản trị qua CORS | Authorization vẫn từ chối nếu user không đủ quyền |
| Actual `POST` thiếu CSRF token | CORS có thể hợp lệ | CSRF protection có thể trả 403 |
| Request không có header `Origin` từ backend khác | Không phải trường hợp CORS browser thông thường | AuthN/AuthZ và kiểm soát API vẫn bắt buộc |

**CORS không phải firewall của server và không thay thế CSRF.** Một số request cross-site không cần preflight vẫn có thể tới backend; việc browser từ chối đọc body không ngăn hành vi thay đổi trạng thái nếu API thiếu bảo vệ CSRF thích hợp.

CSP `connect-src` là chính sách riêng do frontend nhận về, giới hạn nơi frontend có thể kết nối. HSTS và TLS giúp bảo vệ kết nối HTTPS; HTTP firewall xử lý những dạng request HTTP không hợp lệ/nguy hiểm; các cơ chế này bổ sung cho nhau chứ không được thay thế bằng `UrlBasedCorsConfigurationSource`.

## 9. Kiểm thử chọn đúng policy theo path và origin

### 9.1. Ma trận kiểm thử

Với cấu hình hai path trong mục Servlet:

| Request path | `Origin` | Method preflight | Kỳ vọng |
| --- | --- | --- | --- |
| `/api/profile` | `https://app.example.com` | `PUT` | Được phép nếu header được hỏi cũng hợp lệ |
| `/api/profile` | `https://admin.example.com` | `PUT` | Bị từ chối: policy `/api/**` không cho origin admin |
| `/admin/reports` | `https://admin.example.com` | `POST` | Được phép nếu header hợp lệ |
| `/admin/reports` | `https://app.example.com` | `POST` | Bị từ chối: policy `/admin/**` không cho origin app |
| `/admin/reports` | `https://admin.example.com` | `PUT` | Bị từ chối: admin policy không cho `PUT` |
| `/api/profile` | `https://evil.example.org` | `PUT` | Bị từ chối: origin ngoài allowlist |
| `/unknown/path` | `https://app.example.com` | `PUT` | Không tìm thấy CORS config trong nguồn minh họa |
| `/api/profile` | `https://app.example.com` | `PUT` + `x-admin-override` | Bị từ chối: header không được phép |

Bảng này mô tả kiểm tra **preflight**. Một actual request không cần preflight có thể được gửi đến server trước khi browser chặn quyền đọc, nên không thể diễn giải mọi dòng “bị từ chối” là server chắc chắn không nhận request.

### 9.2. Kiểm tra bằng curl

**Preflight hợp lệ với policy `/api/**`:**

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

**Cùng path nhưng origin không được phép:**

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://admin.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
~~~

**Đúng admin origin nhưng method không được phép:**

~~~bash
curl -i -X OPTIONS "https://api.example.com/admin/reports" \
  -H "Origin: https://admin.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Đối với preflight thành công, kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Allow-Credentials` nếu dùng credentials. Bộ xử lý mặc định có thể trả HTTP `200` hoặc một mã 2xx tương ứng; preflight lỗi trong Spring thường trả `403 Invalid CORS request`, nhưng proxy/filter tùy biến có thể gây trạng thái khác.

`curl` chỉ cho biết server trả HTTP header gì. Nó **không thực thi CORS của browser**, do đó cần thử thêm từ đúng origin frontend trong DevTools.

### 9.3. Ví dụ kiểm thử Servlet bằng MockMvc

Với ứng dụng Spring Boot, Spring Security và cấu hình mục 4, kiểm thử preflight theo path:

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
class UrlBasedCorsConfigurationSourceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void matchesApiPathAndAllowedOrigin() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void rejectsAdminOriginOnApiPolicy() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://admin.example.com")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsPutOnAdminPolicy() throws Exception {
        mvc.perform(options("/admin/reports")
                .header("Origin", "https://admin.example.com")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các assertion ví dụ giả định Spring Security đã nạp chính sách CORS như ở mục 4 và bộ xử lý mặc định trả status tương ứng. Đây là **mẫu kiểm thử chưa chạy trên dự án cụ thể**. Khi dùng filter/gateway khác, có thể cần chỉnh kỳ vọng HTTP status; luôn kiểm tra quyền CORS thực tế thay vì chỉ nhìn mã status.

Với Reactive, dùng `WebTestClient` gửi `OPTIONS` và cùng các request headers để xác minh `SecurityWebFilterChain` thực tế. Nên thêm bài test dương/âm cho `/api/**`, `/admin/**` và path không được đăng ký.

## 10. Những lỗi cấu hình phổ biến

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Frontend gửi OPTIONS nhận 401 | CORS chưa chạy trước authentication, hoặc chain khớp request thiếu CORS | Kiểm tra `http.cors` / `ServerHttpSecurity.cors` và filter chain thực tế |
| `OPTIONS /api/orders` 404/405 | Gateway/router chặn OPTIONS hoặc path rewrite sai | Xem path sau rewrite và lớp trả response |
| Chỉ `/api/**` hoạt động, `/admin/**` lỗi | Chưa đăng ký policy admin hoặc origin không thuộc admin policy | Đối chiếu path với `registerCorsConfiguration` |
| App hoạt động khi chạy thẳng, lỗi khi qua gateway | Header CORS bị xóa, chèn trùng hoặc gateway dùng policy khác | So response tại gateway và backend |
| `GET` qua được nhưng `POST application/json` lỗi | Preflight không cho method/header hoặc bị auth chặn | Xem `Access-Control-Request-*` và `Access-Control-Allow-*` |
| Cookie không được gửi dù CORS đúng | Fetch mặc định `credentials: "same-origin"` hoặc cookie `SameSite`/`Secure`/Domain/Path | Kiểm tra Network, tab Cookies và credentials mode |
| Request credentials báo wildcard error | `allowedOrigins("*")` hoặc proxy trả `Allow-Origin: *` | Chọn origin cụ thể với `Allow-Credentials: true` khi cần |
| Frontend thấy lỗi CORS nhưng API log 403 | Actual request bị authorization/CSRF chặn; error response thiếu header CORS | Kiểm tra error response và security chain |
| Cấu hình ở MVC khác cấu hình Security | Nhiều nguồn CORS hoặc tích hợp MVC không đúng | Xác định nguồn CORS đang thực thi |
| Nhiều `CorsConfigurationSource` beans | Cấu hình tự động không chọn được nguồn chính xác | Chỉ định `configurationSource(...)` cho từng chain |
| Frontend đổi port thì lỗi | Origin có port không khớp allowlist | Xem header `Origin` và danh sách origin |
| Lúc đúng lúc sai qua cache | Response thiếu `Vary: Origin` hoặc cache trộn dữ liệu theo user | Rà soát key cache, `Vary` và `Cache-Control` |

### Quy trình chẩn đoán trong DevTools

1. Tìm request API trong Network và xác định method, path, origin thực tế.
2. Nếu có preflight `OPTIONS`, đọc ba header `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. So sánh path với policy đăng ký trong `UrlBasedCorsConfigurationSource`; xác nhận security chain đang xử lý request đó.
4. Đối chiếu preflight response: `Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Allow-Credentials` khi cần.
5. Nếu preflight đạt, xem **actual request** có được gửi và response có header CORS tương ứng không, kể cả response 401/403/500.
6. Nếu lỗi liên quan cookie, kiểm tra riêng `credentials` của Fetch, `SameSite`, `Secure`, Domain/Path và chính sách browser.
7. Nếu chỉ lỗi sau proxy/CDN, kiểm tra path rewrite, biến thể cache và header CORS bị chèn trùng.

Không dùng `fetch(..., { mode: "no-cors" })` để né lỗi: response trở nên opaque và JavaScript không đọc JSON như mong muốn.

## 11. Những nguyên tắc thiết kế trong hệ thống nhiều lớp bảo vệ

Trước khi triển khai chính sách CORS, xác nhận:

- [ ] Mỗi nhóm endpoint có một nguồn policy rõ ràng, đường dẫn và origin được phép được tách bạch.
- [ ] Path pattern `/api/**`, `/admin/**` được kiểm tra với route thực tế sau proxy/rewrite.
- [ ] Source trả `CorsConfiguration` thích hợp cho request và không vô tình mở mọi origin.
- [ ] CORS được tích hợp vào đúng Servlet `SecurityFilterChain` hoặc Reactive `SecurityWebFilterChain` để preflight không bị xác thực chặn.
- [ ] Các origin cấp quyền đọc dữ liệu có credentials đều được quản lý và tin cậy; không phản chiếu mọi `Origin`.
- [ ] Với nhiều sources/chains, cấu hình tường minh và kiểm tra request đi qua chain nào.
- [ ] Không định nghĩa các header CORS mâu thuẫn tại MVC, Security và gateway.
- [ ] Đã có kiểm thử cả preflight hợp lệ, sai origin, sai method, sai header, sai path và actual response.
- [ ] CSRF, authentication, authorization, CSP, HSTS và bảo vệ session được đánh giá độc lập với CORS.

Một `CorsConfigurationSource` được cấu hình tốt giúp browser giao tiếp đúng với API; nó không thay thế bảo mật tài nguyên phía server.

## 12. Câu hỏi vận dụng

**Tình huống 1.** `UrlBasedCorsConfigurationSource` đăng ký `"/api/**"` với `allowedOrigins("https://app.example.com")`. Request `OPTIONS /api/orders` có `Origin: https://evil.example.org`. Source có trả policy không? Trình duyệt có được gửi actual request sau preflight không?

**Đáp án:** Source có thể trả policy do path khớp. Nhưng CORS processor từ chối origin không có trong policy, vì vậy preflight không thành công và browser không gửi actual request của luồng này.

**Tình huống 2.** Cấu hình `registerCorsConfiguration("/api/**", policy)` nhưng request được proxy chuyển vào backend tại `/service/api/orders`. Vì sao có thể lỗi CORS?

**Đáp án:** Policy theo path có thể không khớp đường dẫn mà backend CORS xử lý. Cần xác minh path sau rewrite, servlet context path và route thực tế, rồi điều chỉnh mapping một cách có chủ đích.

**Tình huống 3.** API có hai nhóm `/api/**` và `/admin/**` với allowlist khác nhau. Có nên dùng hai pattern path không chồng lấn trong cùng `UrlBasedCorsConfigurationSource`?

**Đáp án:** Đây là cách phù hợp để chọn cấu hình theo nhóm endpoint khi các rule có ranh giới rõ ràng. Cần test cả trường hợp origin frontend thường gọi nhầm đường dẫn admin và ngược lại.

**Tình huống 4.** Ứng dụng có nhiều `SecurityFilterChain` và một `CorsConfigurationSource` bean. Preflight chỉ lỗi ở một nhóm route. Cần xem gì?

**Đáp án:** Xác định chain nào khớp preflight ở route lỗi, chain đó đã tích hợp CORS đúng source chưa, và gateway có chặn OPTIONS không. Không mặc định một bean tự làm mọi chain hoạt động giống nhau.

**Tình huống 5.** `CorsConfiguration` bật `allowedMethods("DELETE")` và browser qua preflight. Có nghĩa người dùng được xóa tài khoản không?

**Đáp án:** Không. CORS chỉ cho phép browser gửi request theo điều kiện preflight. Authorization và quy tắc API vẫn phải xác định người dùng có được xóa hay không.

**Tình huống 6.** Backend có `CorsConfigurationSource` Servlet, nhưng ứng dụng thực tế chạy WebFlux. Có thể giữ nguyên loại source không?

**Đáp án:** Không. Reactive sử dụng nguồn CORS và `UrlBasedCorsConfigurationSource` thuộc package `org.springframework.web.cors.reactive`, làm việc với `ServerWebExchange`. Cần dùng API reactive tương ứng và tích hợp vào `ServerHttpSecurity`/pipeline WebFlux.

**Tình huống 7.** Một controller có `@CrossOrigin`, còn Spring Security dùng `CorsConfigurationSource` riêng. Response thỉnh thoảng có nhiều `Access-Control-Allow-Origin`. Nên xử lý thế nào?

**Đáp án:** Kiểm kê các tầng đang xử lý CORS, xác định một chính sách thống nhất và tránh thêm header trùng. Kiểm thử với cả preflight và actual response sau khi qua MVC, Security và gateway.

---

**Ghi nhớ:** `CorsConfiguration` định nghĩa **quyền CORS**; `CorsConfigurationSource` chọn policy cho **request**; `UrlBasedCorsConfigurationSource` là cách phổ biến để chọn policy theo **URL path**. Bộ xử lý CORS thực sự xét origin/method/header và tạo response tương ứng. Trong Spring Security cần gắn source vào đúng Servlet hoặc Reactive security chain, xử lý preflight trước authentication và tiếp tục bảo vệ actual request bằng authentication, authorization, CSRF cùng các lớp phòng vệ HTTP khác.
