# Phân biệt context path, servlet path và phần đường dẫn bên trong ứng dụng — Spring Security Servlet

Khi cấu hình **request matching** trong Spring Security Servlet, một URL nhìn thấy trên trình duyệt không nhất thiết là chuỗi mà `RequestMatcher` đang kiểm tra. Có ba thành phần cần phân biệt: **context path** (đường dẫn ứng dụng được triển khai trong servlet container), **servlet path** (phần đường dẫn được container dùng để định tuyến tới servlet) và **path info** (phần còn lại sau một prefix servlet mapping, nếu có). Spring MVC còn có **đường dẫn tương đối với DispatcherServlet** để tìm `@GetMapping`, `@PostMapping`, v.v.

Nhầm các phần này dễ gây hai loại lỗi: cấu hình Spring Security chặn cả endpoint được phép, hoặc nguy hiểm hơn là viết một matcher không bao phủ endpoint nhạy cảm và tưởng rằng đã bảo vệ nó. Đặc biệt, **không nên bê nguyên `request.getRequestURI()` hoặc đường dẫn ngoài proxy vào một `requestMatchers("...")` mà không biết matcher đang so phần nào của request**.

Ví dụ chủ đạo:

~~~text
URL:  https://example.org/catalog/mvc/orders/42?view=full
      └─ host ─┘ └────────────────────────────┘ └─────┘
                            path                 query

Giả sử:
  context path             /catalog
  servlet mapping          /mvc/*
  servlet path             /mvc
  path info                /orders/42
  đường dẫn MVC trong servlet /orders/42
  request URI              /catalog/mvc/orders/42
  query string             view=full
~~~

**Không phải mọi cấu hình đều tách giống ví dụ.** Container quyết định `servletPath` và `pathInfo` dựa trên kiểu mapping. Nếu `DispatcherServlet` được map theo mặc định `/`, thông thường `servletPath` sẽ chứa toàn bộ đường dẫn còn lại trong ứng dụng (ví dụ `/orders/42`) và `pathInfo` là `null`. Bài này giải thích hai trường hợp cụ thể đó, rồi liên hệ đến `MvcRequestMatcher`, `AntPathRequestMatcher` và `SecurityFilterChain`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt giá trị của `getRequestURI()`, `getContextPath()`, `getServletPath()`, `getPathInfo()`, `getQueryString()` và `getRequestURL()`.
2. Dự đoán đúng ba thành phần path khi ứng dụng chạy ở root context, ở context `/catalog`, dưới servlet mapping `/mvc/*` và với extension mapping.
3. Giải thích tại sao Spring MVC `@GetMapping("/orders/{id}")` thường **không** chứa context path hoặc prefix mapping của DispatcherServlet.
4. Biết khi nào Spring Security matcher so **path tương đối servlet**, khi nào nó so **servletPath + pathInfo**, và vì sao phải xác định **loại RequestMatcher** trước khi viết mẫu URL.
5. Phân biệt `securityMatcher(...)` để chọn `SecurityFilterChain` với `requestMatchers(...)` để chọn quy tắc phân quyền trong chain.
6. Tạo ứng dụng Java 17+ / Spring Boot 3.3.5 minh họa context path thật và kiểm thử MockMvc theo đúng HTTP request metadata.
7. Nhận biết các rủi ro từ reverse proxy, servlet path prefix, nhiều servlets, encoded path, path normalization và test thiếu context/servlet information.

## 2. Bốn lớp của một URL nhìn thấy trong trình duyệt

Một request HTTP có nhiều cách biểu diễn:

~~~text
https://api.example.org/catalog/mvc/orders/42?sort=latest#details
└────── origin ──────┘└───── URI path ────────┘└─query─┘└fragment┘
                       /catalog/mvc/orders/42
                            |
               HTTP request trên server
                            |
                  +---------+-----------+
                  |                     |
              contextPath         path in context
               /catalog            /mvc/orders/42
                                       |
                            +----------+----------+
                            |                     |
                        servletPath             pathInfo
                           /mvc                 /orders/42
~~~

Một số điều phải nhớ:

- URL fragment `#details` chỉ là phần điều hướng trên client; browser không gửi fragment đó trong HTTP request target thông thường.
- Query string như `sort=latest` **không nằm trong `getRequestURI()`**. Nó được đọc riêng qua `getQueryString()` hoặc parameters.
- `getRequestURL()` có thể cho scheme/host/port/path nhưng **không bao gồm query string**; thông tin host/scheme sau reverse proxy có thể cần xử lý forwarding đúng.
- `getContextPath()` là prefix mà servlet container gắn cho web application. Với root deployment, nó thường là chuỗi rỗng `""`, không phải `"/"`.
- `getServletPath()` và `getPathInfo()` **không chỉ đơn giản là kết quả `String.split("/")`**. Servlet mapping do container chọn quyết định ranh giới giữa hai phần.
- Một số container/filter có thể cung cấp đường dẫn đã decode hoặc đã qua normalization theo hợp đồng API. **Không dùng các method này như một cơ chế canonicalization bảo mật tự viết**; matcher/framework cần áp dụng chính sách path parsing nhất quán.

### 2.1. context path: ứng dụng được mount ở đâu?

Giả sử server có ứng dụng tại `/catalog`. Những đường dẫn bên ngoài có thể là:

~~~text
GET /catalog/public/ping
GET /catalog/orders/42
GET /catalog/admin/report
~~~

Trong servlet request, `getContextPath()` thường trả `"/catalog"`, còn phần path bên trong ứng dụng không bao gồm `"/catalog"`. Khi deploy ứng dụng ở root context, `getContextPath()` là `""`.

Ví dụ cấu hình Spring Boot:

~~~properties
server.servlet.context-path=/catalog
~~~

Kết quả: browser vào `http://localhost:8080/catalog/public/ping` thay vì `http://localhost:8080/public/ping`. Nhưng controller vẫn có thể khai:

~~~java
@GetMapping("/public/ping")
public String ping() {
    return "pong";
}
~~~

**Không thêm `/catalog` vào `@GetMapping` chỉ vì server đã mount app tại `/catalog`.** Đây là prefix thuộc triển khai web application, không phải business route.

Khi dùng Spring Security string request matcher cho một MVC endpoint, quy tắc thông thường cũng **không ghi context path**. Tuy nhiên phần còn lại của pattern phụ thuộc matcher và servlet mapping. Đừng đánh đồng “bỏ context path” với “mọi matcher đều bỏ servlet path”.

### 2.2. servlet path: container đã chọn servlet nào?

Servlet container có thể map servlet theo nhiều cách:

- **Default mapping `/`:** request thuộc ứng dụng và không bị exact/prefix/extension mapping khác chiếm sẽ được servlet mặc định xử lý. Với DispatcherServlet map `/`, `servletPath` thường là đường dẫn trong context như `/orders/42`; `pathInfo` thường là `null`.
- **Prefix mapping `/mvc/*`:** request `/catalog/mvc/orders/42` có `servletPath="/mvc"` và `pathInfo="/orders/42"`.
- **Extension mapping `*.do`:** request `/catalog/reports.do` có thể có `servletPath="/reports.do"`, `pathInfo=null`.
- **Exact mapping `/health`:** request `/catalog/health` thường có `servletPath="/health"`, `pathInfo=null`.

Các trường hợp trên minh họa quy tắc servlet mapping; nếu có nhiều servlet/route mapping, hãy kiểm tra request thực thay vì suy đoán. Đặc biệt, một slash cuối, path parameters hoặc URL encoding có thể ảnh hưởng việc chọn mapping.

### 2.3. pathInfo: phần còn lại sau prefix mapping

Với servlet mapping `/mvc/*`:

~~~text
request URI:  /catalog/mvc/orders/42
contextPath:  /catalog
servletPath:  /mvc
pathInfo:     /orders/42
~~~

Với default DispatcherServlet mapping `/`:

~~~text
request URI:  /catalog/orders/42
contextPath:  /catalog
servletPath:  /orders/42
pathInfo:     null
~~~

Cả hai trường hợp đều có thể khiến controller tương ứng khai `@GetMapping("/orders/{id}")`, nhưng **giá trị `getServletPath()` và `getPathInfo()` không giống nhau**. Đó là lý do logging mỗi `request.getServletPath()` rồi gọi là “full request path” sẽ gây hiểu nhầm.

### 2.4. Bảng đối chiếu request thực tế

| Context | Servlet mapping | Request URI | getContextPath() | getServletPath() | getPathInfo() |
| --- | --- | --- | --- | --- | --- |
| Root | `/` | `/orders/42` | `""` | `/orders/42` | `null` |
| `/catalog` | `/` | `/catalog/orders/42` | `/catalog` | `/orders/42` | `null` |
| `/catalog` | `/mvc/*` | `/catalog/mvc/orders/42` | `/catalog` | `/mvc` | `/orders/42` |
| Root | `/mvc/*` | `/mvc/orders/42` | `""` | `/mvc` | `/orders/42` |
| `/catalog` | `*.do` | `/catalog/reports.do` | `/catalog` | `/reports.do` | `null` |
| `/catalog` | Exact `/health` | `/catalog/health` | `/catalog` | `/health` | `null` |

Đây là bảng **theo servlet mapping thông dụng**, không phải lời hứa rằng mọi proxy/framework sẽ expose cùng metadata sau khi URL đã bị rewrite. Query string không nằm trong các giá trị `requestURI` ở bảng.

## 3. Phần đường dẫn “bên trong ứng dụng” là khái niệm nào?

Một cách mô tả gần đúng thường dùng là:

~~~text
requestURI = contextPath + servletPath + (pathInfo hoặc "")
~~~

Với các ví dụ mapping đơn giản, phép ghép này tái tạo path trong request URI. **Đây là mô hình tư duy, không phải code parsing bảo mật nên tự cài đặt bằng substring**: encoding, normalization, proxy rewrite và các Servlet API contracts cần được framework xử lý nhất quán.

Có **hai phần đường dẫn** hay bị gọi chung là “application path”:

1. **Path sau context root:** `servletPath + pathInfo`, ví dụ `/mvc/orders/42`. Một số RequestMatcher của Spring Security xem đây là đường dẫn cần match.
2. **Path bên trong DispatcherServlet:** sau servlet mapping prefix, ví dụ `/orders/42`. Spring MVC handler mappings tìm route controller theo đường dẫn liên quan tới servlet này.

Nếu DispatcherServlet map mặc định `/` thì hai biểu diễn có thể giống nhau (ví dụ `/orders/42`). Chính sự giống nhau đó khiến lỗi chỉ xuất hiện khi sau này đổi sang mapping `/mvc/*`.

### 3.1. Đường dẫn của Spring MVC controller

Trong app có context `/catalog` và DispatcherServlet `/mvc/*`, controller:

~~~java
@RestController
class OrdersController {
    @GetMapping("/orders/{id}")
    String getOrder(@PathVariable String id) {
        return "order-" + id;
    }
}
~~~

có thể được truy cập qua URL bên ngoài `/catalog/mvc/orders/42` khi servlet mapping và MVC path matching được cấu hình tương thích. `@GetMapping` không cần khai `"/catalog/mvc/orders/{id}"`.

Tuy nhiên, **đừng coi việc tự ghép context + servlet prefix là một quy tắc tuyệt đối** nếu có gateway rewrite, `ForwardedHeaderFilter`, nhiều DispatcherServlet hoặc URL mapping tùy chỉnh. Hãy xem request metadata và mapping thực.

### 3.2. getRequestURI khác getQueryString

Với request:

~~~http
GET /catalog/mvc/orders/42?sort=price&page=3 HTTP/1.1
Host: example.org
~~~

các giá trị điển hình:

~~~text
request.getRequestURI()   = "/catalog/mvc/orders/42"
request.getContextPath()  = "/catalog"
request.getServletPath()  = "/mvc"
request.getPathInfo()     = "/orders/42"
request.getQueryString()  = "sort=price&page=3"
~~~

Spring Security path matchers thường không dùng query string để quyết định đường dẫn. **Không dùng query parameters để làm ranh giới phân quyền thay cho path/method/identity**; tham số như `tenantId`, `orderId` hoặc `ownerId` vẫn cần authorization logic kiểm tra ownership/tenant.

### 3.3. Servlet mapping là đầu vào của matching

Để hiểu tại sao `getServletPath()` là `/mvc` chứ không phải `/mvc/orders/42`, cần nhìn **mapping** chứ không nhìn `@Controller`. Container đã chọn servlet theo `/mvc/*`; phần `/orders/42` còn lại được cung cấp qua `getPathInfo()`.

Một middleware tự viết:

~~~java
String path = request.getServletPath();
if (path.startsWith("/orders/")) {
    // ...
}
~~~

có thể hoạt động khi DispatcherServlet map `/`, nhưng **không hoạt động** khi map `/mvc/*` vì `servletPath` lúc này chỉ bằng `/mvc`. Nếu đây là security check, bug có thể tạo lỗ hổng hoặc chặn sai đường dẫn. Dùng Spring Security RequestMatcher phù hợp thay vì tự chế so sánh chuỗi thủ công.

## 4. RequestMatcher của Spring Security so phần nào?

Không thể trả lời chính xác chỉ bằng từ “Spring Security” mà thiếu **loại matcher và phiên bản**. Các API khác nhau có cách hiểu pattern khác nhau.

### 4.1. MvcRequestMatcher (Spring Security 6.x + Spring MVC)

`MvcRequestMatcher` sử dụng `HandlerMappingIntrospector` để áp dụng semantics của Spring MVC. Với DispatcherServlet map dưới `/mvc/*`, bạn có thể cấu hình **servlet path cụ thể**:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

MvcRequestMatcher adminMatcher =
    mvc.pattern(HttpMethod.GET, "/admin/**");
~~~

Đây là **mảnh code minh họa**, cần Spring MVC, Spring Security, bean `HandlerMappingIntrospector` và imports. Pattern `"/admin/**"` được hiểu theo đường dẫn mà Spring MVC dùng để match handler; bạn khai `servletPath("/mvc")` riêng để phân biệt servlet.

Đừng viết `mvc.pattern("/catalog/mvc/admin/**")` vì `/catalog` là context path và `/mvc` đã được khai cho servlet mapping. Khi dùng MvcRequestMatcher với nhiều servlets, nêu rõ servlet path giúp tránh áp dụng nhầm rule sang servlet khác. **Nếu ứng dụng không dùng MVC hoặc có servlet mapping khác, không sử dụng MVC matcher theo thói quen.**

### 4.2. AntPathRequestMatcher và biểu diễn servletPath + pathInfo

Trong các phiên bản Spring Security 6 còn có `AntPathRequestMatcher`. Với matcher này, đường dẫn cần so thường được hình thành bằng:

~~~java
request.getServletPath() + (request.getPathInfo() == null
    ? ""
    : request.getPathInfo())
~~~

Ví dụ request có `contextPath="/catalog"`, `servletPath="/mvc"`, `pathInfo="/orders/42"`:

- `AntPathRequestMatcher("/mvc/orders/**")` → **match**.
- `AntPathRequestMatcher("/catalog/mvc/orders/**")` → **không match**, vì context path không thuộc phần match.
- `AntPathRequestMatcher("/orders/**")` → thường **không match** trong ví dụ prefix mapping vì còn `/mvc`.

Đây là khác biệt then chốt với pattern tương đối trong `MvcRequestMatcher`. **Không sao chép một pattern giữa hai matcher mà không kiểm tra semantics.**

Một số API cũ chuyển sang trạng thái deprecated ở các release mới; nếu ứng dụng đang nâng cấp, cần kiểm tra phiên bản Spring Security hiện dùng và ưu tiên API matching được khuyến nghị tại phiên bản đó. Đừng tự đoán rằng lớp matcher nào cũng tồn tại mãi hoặc có cùng semantics.

### 4.3. String requestMatchers trong DSL

Cấu hình quen thuộc:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
~~~

Trên các phiên bản Spring Security 6 với Spring MVC, DSL có thể chọn MVC-aware matcher cho các string patterns khi điều kiện tự động chọn matcher được đáp ứng. Nếu project có nhiều servlets hoặc cấu hình đặc biệt, có thể gặp ambiguity hoặc khác biệt giữa các matcher. Vì thế:

1. Biết framework version cụ thể.
2. Biết `DispatcherServlet` đang map tới `/` hay `/mvc/*`.
3. Biết DSL đã tạo `MvcRequestMatcher`, `AntPathRequestMatcher` hay một matcher khác.
4. Khi có nhiều servlets/prefix, **tạo matcher rõ ràng** thay vì dựa vào suy đoán từ một string path.

**Không lấy câu “requestMatchers luôn bỏ context path” rồi suy ra nó luôn bỏ cả servlet path.** Context path và servlet path là hai lớp khác nhau; việc servlet path có nằm trong pattern phụ thuộc matcher.

### 4.4. PathPatternRequestMatcher ở các phiên bản mới hơn

Một số Spring Security release mới hơn cung cấp `PathPatternRequestMatcher` với builder hỗ trợ `basePath(...)` cho prefix servlet mapping. Cách khai pattern có thể dựa trên path **tương đối context root** và cần định nghĩa prefix đúng khi servlet không ở root. Đây là API version-sensitive; **không copy đoạn code của phiên bản mới vào Boot 3.3.5 mà không kiểm tra dependency Spring Security đi kèm**.

Quy tắc an toàn là: **dùng matcher theo đúng version và xác minh bằng tests trực tiếp đối với request ở production mapping**. Đặc biệt trong giai đoạn migration Ant/MVC/PathPattern, một pattern “giống nhau” không có nghĩa same behavior.

## 5. securityMatcher và requestMatchers: hai cấp matching riêng

Trong Spring Security Servlet còn có thứ tự chọn chain.

~~~text
Request: GET /catalog/mvc/admin/report
                 |
                 v
          FilterChainProxy
                 |
       SecurityFilterChain #1
       securityMatcher match?
                 |
       yes -> chọn CHAIN #1
                 |
       authorizeHttpRequests
       requestMatchers:
         rule A match? -> permission check
         rule B match? -> ...
                 |
       Controller / error response
~~~

- `http.securityMatcher(...)` quyết định **SecurityFilterChain có bảo vệ request này hay không**. Nhiều chains được xét theo order và **chain đầu tiên match** được chọn.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...))` quyết định **quy tắc authorization** của request bên trong chain đã được chọn.
- `anyRequest().denyAll()` chỉ áp dụng **sau khi chain đã được chọn**, không tự bảo vệ URL bên ngoài `securityMatcher` của chain đó.

Nếu bạn viết `securityMatcher` theo sai path (ví dụ chứa context path mà matcher không dùng), một chain chuyên biệt có thể **không bao giờ được chọn**. Nếu chain chung/fallback tiếp tục permitAll hoặc authenticated quá rộng, endpoint admin có thể bị phân quyền yếu hơn ý định.

### 5.1. Ví dụ hai chains theo path

Mảnh cấu hình minh họa, không phải file Java độc lập:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Ví dụ này giả định string matchers ở đúng servlet mapping và matcher semantics; trong app nhiều servlet, nên dùng explicit RequestMatcher. Nếu vô tình đặt `securityMatcher("/catalog/admin/**")` trong app có context path `/catalog`, chain admin có thể không match. Trường hợp đó cần sửa **matcher**, không phải `@Order` hoặc `hasRole`.

### 5.2. Sai URL bên ngoài proxy còn nguy hiểm hơn

Ví dụ proxy ngoài đặt prefix `/edge` và forward đến app nội bộ ở `/catalog`:

~~~text
External client:  GET /edge/catalog/admin/report
Reverse proxy:   GET /catalog/admin/report
Servlet app:     contextPath=/catalog
Security matcher cần áp dụng cho request do servlet container nhìn thấy.
~~~

Không được copy `"/edge/catalog/admin/**"` vào Spring Security chỉ vì browser thấy URL đó. Nếu gateway **không rewrite** như ví dụ mà truyền tiếp prefix hoặc dùng forwarded headers, request metadata có thể khác. **Quan sát request thật và chỉ tin proxy headers từ hạ tầng trusted.**

## 6. Bài lab: một ứng dụng có context path khác root

Để ví dụ ổn định với Java 17+ và Spring Boot 3.3.5, project runnable sau dùng **Servlet Dispatcher mapping mặc định `/`** nhưng đặt **context path `/catalog`**. Điều này minh họa được việc context path là prefix deployment nhưng không được đưa vào `@GetMapping` hay matcher MVC.

Phần nâng cao về servlet prefix `/mvc/*` nằm ở mục 8 dưới dạng **ví dụ cấu hình độc lập**; đừng trộn hai cấu hình lại rồi cho rằng property đã tự sửa mọi matcher.

### 6.1. Cấu trúc dự án

~~~text
request-path-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/pathdemo/
    │   │   ├── PathDemoApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PathController.java
    │   └── resources/application.properties
    └── test/java/example/pathdemo/
        └── PathMatchingTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'request-path-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
server.servlet.context-path=/catalog
# Không khai spring.mvc.servlet.path: DispatcherServlet map mặc định /
server.port=8080
~~~

Sau khi chạy, các URL bên ngoài bắt đầu bằng `/catalog`. Controller vẫn không khai prefix đó.

### 6.2. Class khởi động

Tệp `src/main/java/example/pathdemo/PathDemoApplication.java`:

~~~java
package example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfiguration: matcher không chứa context path

Tệp `src/main/java/example/pathdemo/SecurityConfiguration.java`:

~~~java
package example.pathdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                // Không viết /catalog/public/ping ở đây.
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()

                // Chỉ admin được vào report.
                .requestMatchers(HttpMethod.GET, "/admin/report")
                    .hasRole("ADMIN")

                // User có scope đọc sản phẩm.
                .requestMatchers(HttpMethod.GET, "/products/{id}")
                    .hasAuthority("SCOPE_products.read")

                // Endpoint xem HTTP path metadata, không public.
                .requestMatchers(HttpMethod.GET, "/whoami")
                    .authenticated()

                // Bảo vệ các path mới chưa khai báo.
                .anyRequest().denyAll())

            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .authorities("ROLE_USER", "SCOPE_products.read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities("ROLE_ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

Tất cả patterns `"/public/ping"`, `"/admin/report"` và `"/products/{id}"` đều mô tả MVC paths **trong ứng dụng**, không chứa `/catalog`. Các endpoint không có matcher phù hợp bị `denyAll()`. `HttpMethod.GET` là phần của điều kiện: một POST cùng path không tự được phép.

### 6.4. PathController: quan sát Servlet request

Tệp `src/main/java/example/pathdemo/PathController.java`:

~~~java
package example.pathdemo;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PathController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }

    @GetMapping("/products/{id}")
    public String product(@PathVariable long id) {
        return "product-" + id;
    }

    @GetMapping("/whoami")
    public Map<String, Object> whoami(HttpServletRequest request) {
        Map<String, Object> path = new LinkedHashMap<>();
        path.put("requestURI", request.getRequestURI());
        path.put("contextPath", request.getContextPath());
        path.put("servletPath", request.getServletPath());
        path.put("pathInfo", request.getPathInfo());
        path.put("queryString", request.getQueryString());
        return path;
    }
}
~~~

**Bảo mật:** endpoint `/whoami` chỉ phục vụ học, không nên đưa thông tin nội bộ, headers nhạy cảm hoặc cookies vào response công khai của production. Nó cố ý không trả về session id, Authorization header hoặc CSRF token. Thông tin path này vẫn cần kiểm soát truy cập nếu chứa internal topology hoặc dữ liệu người dùng.

### 6.5. MockMvc tests: contextPath phải được mô phỏng chính xác

Tệp `src/test/java/example/pathdemo/PathMatchingTests.java`:

~~~java
package example.pathdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathMatchingTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicPathMatchesWithoutContextPrefixInSecurityRule()
            throws Exception {
        mockMvc.perform(get("/catalog/public/ping")
                .contextPath("/catalog")
                .servletPath("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void protectedProductNeedsAuthentication() throws Exception {
        mockMvc.perform(get("/catalog/products/42")
                .contextPath("/catalog")
                .servletPath("/products/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerWithAuthorityCanSeeProduct() throws Exception {
        mockMvc.perform(get("/catalog/products/42")
                .contextPath("/catalog")
                .servletPath("/products/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("product-42"));
    }

    @Test
    void readerCannotSeeAdminReport() throws Exception {
        mockMvc.perform(get("/catalog/admin/report")
                .contextPath("/catalog")
                .servletPath("/admin/report")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanSeeAdminReport() throws Exception {
        mockMvc.perform(get("/catalog/admin/report")
                .contextPath("/catalog")
                .servletPath("/admin/report")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }

    @Test
    void servletMetadataShowsActualDecomposition() throws Exception {
        mockMvc.perform(get("/catalog/whoami")
                .contextPath("/catalog")
                .servletPath("/whoami")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requestURI")
                .value("/catalog/whoami"))
            .andExpect(jsonPath("$.contextPath")
                .value("/catalog"))
            .andExpect(jsonPath("$.servletPath")
                .value("/whoami"));
    }

    @Test
    void antMatcherUsesServletPathPlusPathInfoNotContext()
            throws Exception {
        MockHttpServletRequest request =
            new MockHttpServletRequest(
                "GET", "/catalog/mvc/orders/42");

        request.setContextPath("/catalog");
        request.setServletPath("/mvc");
        request.setPathInfo("/orders/42");

        assertEquals("/catalog", request.getContextPath());
        assertEquals("/mvc", request.getServletPath());
        assertEquals("/orders/42", request.getPathInfo());

        assertTrue(new AntPathRequestMatcher(
            "/mvc/orders/**").matches(request));

        assertFalse(new AntPathRequestMatcher(
            "/catalog/mvc/orders/**").matches(request));

        assertFalse(new AntPathRequestMatcher(
            "/orders/**").matches(request));
    }

    @Test
    void defaultServletRequestHasNoPathInfo()
            throws Exception {
        MockHttpServletRequest request =
            new MockHttpServletRequest(
                "GET", "/catalog/products/42");

        request.setContextPath("/catalog");
        request.setServletPath("/products/42");

        assertEquals("/products/42", request.getServletPath());
        assertNull(request.getPathInfo());
    }

    @Test
    void unknownUrlIsDeniedToAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/catalog/not-configured")
                .contextPath("/catalog")
                .servletPath("/not-configured")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Trong phần kiểm thử thủ công với `MockHttpServletRequest`, chúng ta **tự đặt** contextPath/servletPath/pathInfo để mô phỏng servlet mapping. Unit test đó chứng minh semantics của `AntPathRequestMatcher` trên request fixture, nhưng **không chứng minh container production tự chọn đúng mapping**. Các HTTP integration tests còn lại dùng MockMvc đi qua Spring Security chain và Spring MVC controller.

Tùy version, một số matcher cũ có thể deprecated; ở demo Spring Security 6.3.x chúng giúp minh họa, nhưng khi nâng cấp phải kiểm tra API thay thế. **Không sử dụng AntPathRequestMatcher chỉ để né MVC path semantics nếu project có nhiều servlet và yêu cầu rõ ràng hơn**.

### 6.6. Chạy dự án

Có Java 17+ và Gradle tương thích:

~~~bash
gradle test
gradle bootRun
~~~

Với Gradle Wrapper, ưu tiên `./gradlew test` và `./gradlew bootRun`; Windows dùng `gradlew.bat test` và `gradlew.bat bootRun`. Dự án dùng Spring Boot dependencies nên chỉ chạy `javac` và `java` trần sẽ thiếu classpath.

Thử trên localhost:

~~~bash
curl -i http://localhost:8080/catalog/public/ping
curl -i http://localhost:8080/catalog/products/42
curl -i -u reader:reader-pass \
  http://localhost:8080/catalog/products/42
curl -i -u reader:reader-pass \
  http://localhost:8080/catalog/whoami
curl -i -u reader:reader-pass \
  http://localhost:8080/catalog/admin/report
curl -i -u admin:admin-pass \
  http://localhost:8080/catalog/admin/report
~~~

Response của `GET /catalog/whoami` trong cấu hình default servlet mapping về mặt cấu trúc:

~~~json
{
  "requestURI": "/catalog/whoami",
  "contextPath": "/catalog",
  "servletPath": "/whoami",
  "pathInfo": null,
  "queryString": null
}
~~~

Đây là output minh họa theo mapping đã cấu hình, không phải kết quả runtime đã được chạy trong bài viết. Curl có `-u` chỉ dùng cho username/password **demo**; không đưa credentials thật vào shell history, process list hoặc logs. Production dùng HTTPS và auth policies phù hợp.

## 7. Cách suy luận từng request trong bảng test

| Request bên ngoài | contextPath | servletPath trong demo | Authorization matcher | Kỳ vọng |
| --- | --- | --- | --- | --- |
| GET /catalog/public/ping | /catalog | /public/ping | GET /public/ping → permitAll | 200 |
| GET /catalog/products/42, anonymous | /catalog | /products/42 | GET /products/{id} → scope read | 401 |
| GET /catalog/products/42, reader | /catalog | /products/42 | GET /products/{id} → scope read | 200 |
| GET /catalog/admin/report, reader | /catalog | /admin/report | GET /admin/report → ROLE_ADMIN | 403 |
| GET /catalog/admin/report, admin | /catalog | /admin/report | GET /admin/report → ROLE_ADMIN | 200 |
| GET /catalog/whoami, reader | /catalog | /whoami | GET /whoami → authenticated | 200 |
| GET /catalog/not-configured, reader | /catalog | /not-configured | anyRequest → denyAll | 403 |

Khi nhận 403, không vội kết luận “sai path”: có thể matcher đúng nhưng role/authority không đủ; một POST còn có thể bị `CsrfFilter` chặn trước authorization. Phải phân biệt **matcher có khớp hay không**, **chain nào được chọn** và **authorization result**.

## 8. Nâng cao: DispatcherServlet được map dưới /mvc/*

Đây là **biến thể cấu hình độc lập**, không copy nguyên vào project chạy ở mục 6 mà bỏ qua những thay đổi khác.

Giả sử:

~~~properties
server.servlet.context-path=/catalog
spring.mvc.servlet.path=/mvc
~~~

Bề ngoài, một controller `@GetMapping("/orders/{id}")` có thể được gọi tại:

~~~text
/catalog/mvc/orders/42
~~~

Khi container sử dụng prefix mapping `/mvc/*`, giá trị dự kiến:

~~~text
getContextPath() = /catalog
getServletPath() = /mvc
getPathInfo()    = /orders/42
getRequestURI()  = /catalog/mvc/orders/42
~~~

**Lưu ý về Spring Boot 3.x:** khả năng phối hợp prefix `spring.mvc.servlet.path` với MVC path matching strategy phụ thuộc version/configuration. Một số bản Boot cần điều chỉnh `spring.mvc.pathmatch.matching-strategy=ant_path_matcher` khi dùng prefix; hãy kiểm tra tài liệu đúng bản và startup tests thay vì giả định property prefix luôn tương thích với default PathPatternParser. Vì vậy phần này trình bày **cách hiểu RequestMatcher và cấu hình cần xét**, không tuyên bố đã chạy integration test cho biến thể.

### 8.1. Cấu hình MVC-aware matcher có servletPath

Trong Spring Security 6, có thể tạo `MvcRequestMatcher.Builder` từ bean `HandlerMappingIntrospector`, rồi khai servletPath:

~~~java
@Bean
SecurityFilterChain mvcSecurity(
        HttpSecurity http,
        HandlerMappingIntrospector introspector)
        throws Exception {

    MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector)
            .servletPath("/mvc");

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(mvc.pattern(
                HttpMethod.GET, "/public/ping"))
                .permitAll()
            .requestMatchers(mvc.pattern(
                HttpMethod.GET, "/admin/**"))
                .hasRole("ADMIN")
            .requestMatchers(mvc.pattern(
                HttpMethod.GET, "/orders/{id}"))
                .authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **mảnh code**, cần imports của `Bean`, `HttpSecurity`, `HandlerMappingIntrospector`, `MvcRequestMatcher`, `HttpMethod`, `Customizer` và `SecurityFilterChain`. Chỉ dùng nếu MVC matcher phù hợp với servlet configuration hiện tại.

Chú ý hai lớp thông tin:

- `mvc.servletPath("/mvc")` nêu servlet mapping riêng.
- `mvc.pattern("/admin/**")` nêu đường dẫn MVC bên trong servlet; **không** ghi `/catalog/mvc/admin/**`.

Nếu có thêm `DispatcherServlet` khác map `/legacy/*` hoặc servlet không phải MVC, đừng mặc định một builder sẽ match mọi servlet. Phải phân biệt từng servlet path và chọn matcher tương ứng.

### 8.2. So sánh với AntPathRequestMatcher

Cùng request `/catalog/mvc/admin/report` trong mapping `/mvc/*`:

~~~text
requestURI     /catalog/mvc/admin/report
contextPath    /catalog
servletPath    /mvc
pathInfo       /admin/report

MvcRequestMatcher (đã set servletPath("/mvc")):
  pattern("/admin/**")        -> thường match theo MVC semantics

AntPathRequestMatcher:
  pattern("/mvc/admin/**")    -> match servletPath + pathInfo
  pattern("/admin/**")        -> không match ở ví dụ này
  pattern("/catalog/mvc/admin/**") -> không match
~~~

Đừng áp dụng máy móc `"/admin/**"` cho mọi matcher. Khi đổi loại matcher trong lúc upgrade Spring Security, cần test negative/positive cases vì pattern vocabulary và base path có thể thay đổi.

### 8.3. Nhiều Servlet và matcher ambiguity

Một web application có thể chạy:

- DispatcherServlet chính map `/mvc/*`.
- Servlet legacy map `/legacy/*`.
- Một servlet quản trị/internal map riêng.

Nếu dùng string matchers mà framework không biết servlet nào cần được match, cấu hình có thể ambiguous hoặc match khác ý muốn. Với nhiều servlets, giải quyết bằng **matcher tường minh** cho từng nhóm, kiểm tra `HttpServletMapping` và có tests xác minh servlet path/chain selection. Không tìm “mẹo thêm contextPath vào string” như giải pháp tổng quát.

### 8.4. Không tự tạo “full path” bằng substring trong filter security

Đoạn sau hấp dẫn nhưng dễ sai:

~~~java
String path = request.getRequestURI()
    .substring(request.getContextPath().length());

if (path.startsWith("/mvc/admin")) {
    // tự quyết định quyền...
}
~~~

Nó bỏ context path theo chuỗi nhưng còn nhiều rủi ro: encoding, path separators, path parameters, boundary prefix `/mvc/administer` cũng bắt đầu bằng `/mvc/admin`, dấu slash, case sensitivity và URL normalization. Đó là lý do Spring Security cung cấp `RequestMatcher` với semantics kiểm soát và có thể kiểm thử.

Nếu cần custom RequestMatcher, nên định nghĩa logic rõ ràng bằng Servlet API/matcher chuẩn và viết test với cả **positive** lẫn **negative boundary cases**.

## 9. Reverse proxy và external prefix: thêm một lớp đường dẫn nữa

Khi app nằm sau Nginx/Ingress/Gateway, URL public có thể khác URI mà servlet container nhận:

~~~text
Client:     https://example.org/gateway/catalog/orders/42
Proxy:      strip /gateway
Upstream:   http://app:8080/catalog/orders/42
Container:  contextPath=/catalog, servletPath=/orders/42
~~~

Trong ví dụ này, **/gateway không xuất hiện trong requestURI nội bộ**. Nếu proxy *không* strip prefix hoặc sử dụng Forwarded/X-Forwarded-Prefix, Servlet request metadata mà Spring nhìn thấy có thể khác.

### 9.1. Forwarded headers không được tin vô điều kiện

`Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix` và headers tương tự có thể tác động đến scheme/host/path khi framework xử lý chúng. Không bao giờ tin các giá trị do client internet trực tiếp tự ghi nếu gateway chưa strip/overwrite chúng.

Với một hạ tầng trusted, Spring Boot có các cách cấu hình forwarding strategy, ví dụ:

~~~properties
server.forward-headers-strategy=framework
~~~

Đây không phải “bật là đủ an toàn”: cần thiết lập proxy boundary, header sanitization, URL rewrite, TLS termination và tests đúng môi trường. Khi debug, ghi nhận cả URL public lẫn URI nội bộ (không log secrets) để tránh nhầm ranh giới.

### 9.2. Đừng nhầm context path với đường dẫn hiển thị bên ngoài

Các cách vận hành khác nhau:

- WAR deploy tại `/catalog` trong Tomcat: contextPath có thể là `/catalog`.
- Spring Boot embedded server có `server.servlet.context-path=/catalog`: contextPath tương ứng.
- Reverse proxy publish app ở `/gateway` nhưng upstream server ở root: contextPath phía container có thể vẫn là `""`.
- Proxy cấu hình forwarding: request wrappers/framework có thể expose đường dẫn khác theo strategy.

Chỉ nhìn browser address bar không đủ để xác định giá trị `request.getContextPath()`. Debug từ HTTP request đến container, rồi mới tới Spring Security matcher.

### 9.3. Sinh URL trong ứng dụng

Khi form hoặc redirect cần dẫn về một controller, đừng hardcode URL thiếu context path. Trong Spring MVC/Thymeleaf, các helper tạo URL theo context sẽ giảm lỗi deployment prefix. Nhưng cần test thêm proxy prefix nếu ingress rewrite. Một URL được render đúng cho người dùng **không** đồng nghĩa pattern `requestMatchers` nên dùng chính URL public đó.

## 10. Matching và bảo mật: những edge cases cần test

Một matcher nhìn đúng ở path bình thường vẫn có thể thất bại khi path được chuẩn hóa theo nhiều tầng.

### 10.1. Query, fragment và path variables

- `GET /catalog/orders/42?sort=asc`: query `sort=asc` không phải một segment URL path để `requestMatchers("/orders/**")` xử lý.
- `#section` trong URL không được browser gửi lên server trong HTTP request thông thường.
- `@GetMapping("/orders/{id}")` có path variable; matcher chọn URL phạm vi. **Sau khi xác thực**, nghiệp vụ vẫn phải kiểm tra user có quyền xem đúng `orderId`/tenant hay không.

### 10.2. Encoded slash, double slashes, semicolons

Cần xem môi trường xử lý những dạng như:

~~~text
/catalog/orders/%2F42
/catalog//orders/42
/catalog/orders/42;v=1
/catalog/orders/../admin/report
/catalog/ADMIN/report
~~~

Không chủ trương rằng tất cả đường dẫn trên đều được container nhận, decode hoặc route như nhau: servlet container, firewall, proxy, MVC matcher và Spring Security có thể reject hoặc normalize khác nhau. **Đặc biệt, đừng tự decode URL thêm lần nữa để tìm một path “đẹp hơn” rồi cấp quyền**. Double decoding/path traversal có thể dẫn đến bypass nếu proxy, firewall và backend không thống nhất.

Kiểm thử integration ở **proxy và servlet container thật** để xác định request bị reject hay match đúng; unit test với MockHttpServletRequest không thay thế hoàn toàn kiểm thử hệ thống.

### 10.3. Path-prefix boundary

Không dùng:

~~~java
path.startsWith("/admin")
~~~

như một security decision nếu mong chỉ match namespace `/admin/`. Nó cũng match `/administrator` hoặc `/administer`. Sử dụng RequestMatcher có phân tích segment/pattern đúng, và thêm negative tests cho boundary.

### 10.4. HTTP methods khác nhau

Một pattern `"/orders/**"` không nêu HTTP method có thể match nhiều methods. Nếu chỉ GET có quyền đọc, đừng để cùng quyền đó được dùng cho POST/DELETE tại controller khác. Ví dụ:

~~~java
.requestMatchers(HttpMethod.GET, "/orders/{id}")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/orders/{id}")
    .hasAuthority("SCOPE_orders.delete")
.anyRequest().denyAll()
~~~

Chọn method-aware matcher và test CSRF riêng nếu application dùng cookie-authenticated browser. CSRF có thể chặn POST/DELETE trước authorization; nó không thay thế rule quyền delete.

### 10.5. Dispatcher types

Trong Servlet, request còn có `DispatcherType.REQUEST`, `FORWARD`, `ERROR`, `ASYNC` và `INCLUDE`. Một forward/error dispatch có thể dùng đường dẫn khác request gốc. Security filter registrations và matcher policy có thể ảnh hưởng quyền vào error view hoặc MVC forward.

Chỉ đặt `dispatcherTypeMatchers(...)` theo yêu cầu thật và đánh giá impact. Đừng mở toàn bộ path bằng `permitAll()` chỉ vì error page bị 403; cần phân tích dispatcher types, chain và URL mục tiêu.

## 11. Quy trình debug lỗi matcher theo từng lớp

Khi một endpoint unexpectedly trả 401, 403 hoặc bị mở quyền, kiểm tra theo thứ tự:

1. **Request nào thực sự đến server?** Ghi HTTP method, raw requestURI (đã lọc secrets), contextPath, servletPath, pathInfo, queryString và dispatcher type ở môi trường học.
2. **Servlet mapping nào được chọn?** DispatcherServlet map `/`, `/mvc/*` hay servlet khác?
3. **Proxy có rewrite hoặc forwarded headers không?** URL bên ngoài và path nội bộ có thể khác.
4. **RequestMatcher class nào được dùng?** MVC-aware, Ant-style, PathPattern hoặc custom; đừng suy ra từ string.
5. **Chain nào match đầu tiên?** Kiểm tra `@Order` và `securityMatcher`, kể cả fallback.
6. **Rule authorization nào match đầu tiên?** Kiểm tra thứ tự `requestMatchers` trong chain.
7. **Kết quả role/authority/ownership là gì?** Matcher đúng vẫn có thể deny vì thiếu quyền.
8. **Có filter trước authorization chặn không?** CSRF, authentication, request firewall, HTTPS requirements có thể góp phần.
9. **Test mock đã đặt đúng contextPath/servletPath/pathInfo chưa?** Fixture không đúng dễ cho kết luận sai.
10. **Có encoded path/trailing slash/semicolon/forward không?** Lặp lại test trên container/proxy thật.
11. **Có request nào nằm ngoài tất cả filter chains không?** Bổ sung fallback chain hoặc default deny khi cần.
12. **Sửa matchers rồi thêm regression tests**, không chỉ thử một happy path.

### 11.1. Log DEBUG có kiểm soát

Trong môi trường học, có thể đặt:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Không dựa vào chính xác một câu log giữa các phiên bản. Không log nguyên `Authorization`, `Cookie`, session id, CSRF token, password hoặc nội dung token. Log path metadata cũng nên được redaction nếu nó chứa identifiers nhạy cảm, ví dụ token đặt nhầm trong URL.

### 11.2. Bảng chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Việc cần làm |
| --- | --- | --- |
| Đổi context root khiến endpoint public bị 401 | Matcher có thể đã hardcode context path | Xem request metadata, bỏ prefix triển khai khỏi MVC matcher |
| `/catalog/mvc/admin/report` bị 404 | MVC servlet mapping/controller không khớp | Kiểm tra mapping `/mvc/*` và `@GetMapping` |
| Admin chain không chạy | `securityMatcher` sai prefix hoặc thứ tự chain | Xác định class matcher/order và test |
| Matcher Ant không khớp `/orders/**` khi servletPath `/mvc` | Ant path gồm `/mvc` + pathInfo | Dùng đúng Ant pattern hoặc MVC matcher tường minh |
| Matcher MVC nhầm servlet | Builder không chỉ rõ servletPath khi có nhiều servlets | Dùng `MvcRequestMatcher.Builder.servletPath` thích hợp |
| GET chạy nhưng POST 403 | CSRF thiếu hoặc rule method không cho phép | Phân biệt filter CSRF với authorization |
| URL ngoài gateway khác app requestURI | Proxy rewrite/X-Forwarded-Prefix | Quan sát upstream request và trusted forwarding |
| MockMvc pass nhưng production fail | Test chưa mô phỏng context/servlet/proxy | Sửa fixture và thêm integration test |
| Dấu `/` cuối khiến rule lệch | Matcher/handler mapping semantics khác | Test trailing slash và pattern thực |
| `getServletPath()` không có phần after-prefix | Servlet mapping kiểu `/mvc/*` | Đọc `getPathInfo()` và dùng matcher phù hợp |
| Unmatched path được xử lý ngoài Spring Security | Không có fallback chain bảo vệ | Kiểm thử FilterChainProxy coverage |
| User đúng auth nhưng vẫn 403 | Authority/role/tenant hoặc CSRF | Đừng chỉ thay URL pattern |

## 12. Bài tập thực hành

1. Với URI `/catalog/mvc/orders/42`, context `/catalog` và mapping `/mvc/*`, viết chính xác `getContextPath()`, `getServletPath()` và `getPathInfo()`.
2. Với **cùng URI**, nếu DispatcherServlet được map theo `/` thay vì `/mvc/*`, phần nào của servletPath/pathInfo thay đổi?
3. Vì sao `getContextPath()` là `""` khi ứng dụng chạy ở root context mà không phải `"/"`?
4. Chứng minh `getRequestURI()` không chứa query string bằng một request có `?page=2`.
5. Vẽ quan hệ giữa URL public, reverse proxy, context path, servlet mapping và Spring MVC `@GetMapping`.
6. Trong app context `/catalog`, vì sao `@GetMapping("/products/{id}")` có thể phục vụ URL `/catalog/products/42` mà không ghi `/catalog` trong annotation?
7. Một `AntPathRequestMatcher("/orders/**")` có match request có `servletPath="/mvc"`, `pathInfo="/orders/42"` không? Tại sao?
8. Tạo `MvcRequestMatcher.Builder` với `servletPath("/mvc")` và `pattern("/orders/**")`. Giải thích thành phần nào được bao gồm và thành phần nào không.
9. Nêu sự khác nhau giữa `http.securityMatcher(...)` và `authorizeHttpRequests().requestMatchers(...)`.
10. Nếu một request không khớp chain nào, `anyRequest().denyAll()` trong một chain chỉ match `/mvc/**` có bảo vệ request đó không?
11. Một app thêm servlet legacy `/legacy/*` bên cạnh DispatcherServlet `/mvc/*`. Bạn sẽ kiểm chứng matcher và chain như thế nào để không cấp nhầm quyền?
12. MockMvc test cho `/catalog/products/42` cần khai requestURI, contextPath và servletPath thế nào?
13. Nếu test tự đặt `MockHttpServletRequest.setServletPath("/mvc")`, kết luận đó có chứng minh production container luôn trả `"/mvc"` không?
14. Một URL có fragment `#comments`; Servlet API có nhận phần fragment không?
15. Tại sao không viết access check bằng `requestURI.substring(contextPath.length()).startsWith("/admin")`?
16. Khi proxy ngoài dùng prefix `/gateway` và strip nó trước upstream, pattern nào trong Spring Security cần xét? Làm sao xác minh?
17. Một POST thiếu CSRF token trả 403 dù `@PostMapping` và path matcher đúng; thứ tự debug nào nên áp dụng?
18. Khi nâng cấp từ AntPathRequestMatcher sang matcher kiểu mới, các trường hợp URI/servlet prefix nào cần có regression tests?
19. Thiết kế test cho encoded slash, double slash, path segment traversal và semicolon để xác minh ứng dụng reject hoặc xử lý nhất quán.
20. Giải thích vì sao dù matcher đã xác định đúng endpoint `/orders/{id}`, server vẫn cần kiểm tra user có sở hữu order và thuộc đúng tenant hay không.

## 13. Checklist khi cấu hình RequestMatcher trong production

- [ ] Biết application có context root nào ở servlet container, không nhầm với external proxy prefix.
- [ ] Biết DispatcherServlet map `/`, `/mvc/*` hay có nhiều servlet mappings.
- [ ] Có bảng requestURI/contextPath/servletPath/pathInfo cho các endpoint đại diện.
- [ ] Biết chính xác `RequestMatcher` được dùng và semantics path của nó theo phiên bản Spring Security.
- [ ] MVC handler mappings và Spring Security matchers dùng cùng phạm vi servlet/pattern phù hợp.
- [ ] Không đưa context path của deployment vào MVC matcher theo thói quen.
- [ ] Không copy Ant matcher pattern sang MVC matcher mà không review servlet prefix.
- [ ] Nếu có nhiều servlets, chỉ rõ servlet path/matcher và chain boundaries.
- [ ] Có fallback `SecurityFilterChain` hoặc policy không để URL ngoài dự kiến vượt Spring Security.
- [ ] Quy tắc cụ thể đứng trước quy tắc rộng; test chain order và rule order.
- [ ] Matcher có điều kiện HTTP method nếu quyền khác nhau theo method.
- [ ] Có tests positive/negative cho role/scope, anonymous và multi-tenant/resource ownership.
- [ ] MockMvc fixtures mô phỏng đúng contextPath/servletPath/pathInfo; integration test qua proxy/container cho các case quan trọng.
- [ ] Đường dẫn encoded/traversal/semicolon/trailing slash được xử lý nhất quán giữa gateway/firewall/MVC.
- [ ] Không tự parse URL để kiểm tra quyền; tránh prefix boundary và double decode.
- [ ] Trusted forwarded headers từ gateway được kiểm soát; không tin header client tự khai.
- [ ] Log và debug metadata path có kiểm soát, không làm lộ tokens/passwords/cookies.
- [ ] Khi đổi context path, servlet mapping hoặc SecurityMatcher implementation, chạy lại toàn bộ authorization regression tests.

## 14. Kết luận

**Context path** xác định ứng dụng được gắn ở đâu; **servlet path** và **pathInfo** phản ánh cách container chọn servlet và phần đường dẫn còn lại; **đường dẫn Spring MVC** là ngữ cảnh mà DispatcherServlet dùng để khớp controller. Trong trường hợp đơn giản, các chuỗi có thể trông giống nhau, nhưng khi app có prefix servlet hoặc reverse proxy, khác biệt trở thành yếu tố bảo mật.

Để cấu hình Spring Security đúng, trước hết hãy **quan sát request metadata thật**, sau đó **xác định loại RequestMatcher**, rồi viết pattern theo semantics của matcher và kiểm chứng bằng các test method/path/context/servlet prefix. Cuối cùng, đảm bảo không có request lọt khỏi filter chain và authorization rules vẫn kiểm soát đúng role, scope, owner và tenant. Khi nắm vững các ranh giới này, bạn có thể deploy cùng một ứng dụng ở `/`, `/catalog` hoặc phía sau gateway mà không vô tình mở hoặc khóa nhầm endpoint.
