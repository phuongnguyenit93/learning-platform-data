# Context path, servlet path, base path và địa chỉ thực được so khớp

Một tình huống phổ biến trong Spring Security: trình duyệt truy cập `https://example.com/shop/orders/42`, controller `@GetMapping("/orders/{id}")` vẫn chạy đúng, nhưng `requestMatchers("/shop/orders/**")` không khớp như dự tính. Hoặc ứng dụng được đặt sau reverse proxy tại `/edge/shop`, trong khi SecurityFilterChain kiểm tra `/api/**`. Nguyên nhân thường không nằm ở role/authority mà ở việc **đang so khớp nhầm lớp đường dẫn**.

Bài này giải thích bốn khái niệm dễ bị dùng lẫn: **context path**, **servlet path**, **base path** và **địa chỉ thực của request**. Trọng tâm là `RequestMatcher` ở **Spring Security Servlet**, đặc biệt `PathPatternRequestMatcher` từ Spring Security 6.5, các matcher MVC cũ, `securityMatcher`, `authorizeHttpRequests` và reverse proxy. Mục tiêu là xác định chính xác request được ứng dụng nhìn thấy và viết chính sách cho đúng đường dẫn, không dùng phép so khớp chuỗi tùy tiện gây lỗ hổng.

## 1. Có nhiều “đường dẫn” cho một HTTP request

Giả sử trình duyệt gọi:

~~~text
GET https://example.test/shop/orders/42?view=summary
~~~

Giả sử app Servlet được deploy với **context path `/shop`** và dùng `DispatcherServlet` ở mapping mặc định `/`. Trong một cách ánh xạ Servlet thông thường, các giá trị quan sát được là:

| Nguồn | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| URL ngoài trình duyệt | `https://example.test/shop/orders/42?view=summary` | Có scheme, host, path và query string. |
| `request.getRequestURI()` | `/shop/orders/42` | URI path mà Servlet container nhìn thấy, **gồm context path**, **không gồm query string**. |
| `request.getContextPath()` | `/shop` | Prefix dùng để định vị ứng dụng web trong container. |
| `request.getServletPath()` | `/orders/42` | Phần Servlet API xác định theo servlet mapping; với default mapping `/`, thường là phần path trong ứng dụng. |
| `request.getPathInfo()` | `null` | Phần dư ngoài servlet mapping, nếu loại mapping đó có phần dư. |
| `request.getQueryString()` | `view=summary` | Query riêng, **không phải** thành phần mặc định của matcher đường dẫn. |
| Đường dẫn tương đối context | `/orders/42` | Đây là dạng path mà `PathPatternRequestMatcher` sử dụng để so khớp. |
| Controller mapping | `/orders/{id}` | Khai báo tương đối với phạm vi mapping của `DispatcherServlet`. |

Với `PathPatternRequestMatcher`, matcher `/orders/**` có thể khớp URL trên **vì context `/shop` được bỏ khỏi path dùng để match**. Ngược lại, nếu viết `/shop/orders/**`, bạn đã đưa context path vào pattern và dễ khiến rule không match.

Một sơ đồ ngắn:

~~~text
Browser URL: https://example.test/shop/orders/42?view=summary
                 |             |      |          |
                 |             |      |          +-- query: view=summary
                 |             |      +-- route: /orders/42
                 |             +-- context path: /shop
                 +-- scheme/host, KHÔNG thuộc path matcher thông thường

getRequestURI()       = /shop/orders/42
getContextPath()      = /shop
PathPatternRequestMatcher sees path relative to context = /orders/42
Matcher hợp lý        = /orders/**
Matcher dễ sai         = /shop/orders/**
~~~

Các giá trị `servletPath` và `pathInfo` **phụ thuộc kiểu servlet mapping** (`/`, `/mvc/*`, mapping chính xác, extension mapping, v.v.). Không luôn giả định `getServletPath()` là URL đầy đủ trừ context path, cũng không luôn giả định `getPathInfo()` khác `null`.

## 2. Context path là gì? Nó không phải prefix tùy ý trong requestMatchers

**Context path** là đường dẫn gắn với *toàn ứng dụng web* ở Servlet container. Với Spring Boot trên Servlet stack, thuộc tính thông dụng là:

~~~yaml
server:
  servlet:
    context-path: /shop
~~~

Nếu endpoint trong app được định nghĩa là `GET /orders/42`, client trực tiếp truy cập server bằng `GET /shop/orders/42`. Trong Servlet API, `getContextPath()` thường trả `/shop`. Nếu deploy tại root context, kết quả thường là **chuỗi rỗng `""`**, không phải dấu gạch chéo `/`.

`PathPatternRequestMatcher` yêu cầu pattern **tương đối context path**. Ví dụ trong project Spring Boot 3 với phiên bản Spring Security **6.5+** có `PathPatternRequestMatcher`, đây là cấu hình hợp lệ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class ContextPathSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        PathPatternRequestMatcher.Builder paths =
                PathPatternRequestMatcher.withDefaults();

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(paths.matcher(HttpMethod.GET, "/orders/**"))
                .hasAuthority("ORDER_READ")
            .requestMatchers(paths.matcher(HttpMethod.GET, "/public/**"))
                .permitAll()
            .anyRequest()
                .denyAll()
        );

        return http.build();
    }
}
~~~

Đoạn này là **cấu hình Spring**, cần dependencies Spring Boot/Spring Security tương ứng và authentication provider được thiết kế riêng; không biên dịch độc lập bằng `javac` khi thiếu Spring libraries. Nó giả định `DispatcherServlet` ở mapping mặc định `/`, không có servlet prefix đặc biệt và không có gateway rewrite làm thay đổi đường đi của request.

Với `server.servlet.context-path=/shop`, request `GET /shop/orders/42` thuộc rule `/orders/**`, nếu đã qua các filter khác và `Authentication` có `ORDER_READ`. `GET /shop/public/info` thuộc rule public. Cần phân biệt **match URL** với **được phép thao tác trên Order 42**: rule chỉ yêu cầu quyền đọc chung; service vẫn phải kiểm tra owner/tenant của bản ghi thật.

**Không chuyển cách viết sang `/shop/orders/**` chỉ vì Chrome hiển thị `/shop`.** Context path do deployment quyết định; matcher nói trên chủ động bỏ nó. Có thể deploy cùng artifact dưới `/staging` thay vì `/shop` mà vẫn giữ pattern `/orders/**`.

### Khi nào getRequestURI() và đường match khác nhau?

`getRequestURI()` theo Servlet API chứa context path. Nếu tự viết:

~~~java
// KHÔNG làm thế này cho Spring Security authorization:
boolean allowed = request.getRequestURI().startsWith("/orders/");
~~~

thì URL `/shop/orders/42` không khớp, dù path thực trong ứng dụng đúng là `/orders/42`. Một “sửa chữa” bằng `contains("/orders/")` còn tệ hơn: nó có thể cho phép những path không mong muốn. Hãy dùng `RequestMatcher` có ngữ nghĩa đã kiểm chứng, không tự so chuỗi `requestURI` như một chính sách an toàn.

## 3. Servlet path là gì? Khác context path ở chỗ nào?

**Servlet path** mô tả phần liên quan đến mapping của một `HttpServlet`, đặc biệt `DispatcherServlet` trong ứng dụng Spring MVC. Có hai trường hợp minh họa:

### Trường hợp A — DispatcherServlet dùng mapping mặc định `/`

~~~text
Browser:       /shop/orders/42
contextPath:   /shop
servletPath:   /orders/42
pathInfo:      null
app path:      /orders/42
MVC mapping:   /orders/{id}
~~~

Lúc này `PathPatternRequestMatcher.withDefaults().matcher("/orders/**")` hoạt động đúng cho path tương đối context. Không cần `basePath` riêng.

### Trường hợp B — DispatcherServlet được map bằng prefix `/mvc/*`

Giả sử một Servlet được đăng ký ở `/mvc/*` để phục vụ Spring MVC, còn ứng dụng deploy tại context `/shop`:

~~~text
Browser:       /shop/mvc/orders/42
contextPath:   /shop
servletPath:   /mvc
pathInfo:      /orders/42
app path:      /mvc/orders/42
MVC mapping:   /orders/{id}  (bên trong DispatcherServlet)
~~~

Khi viết `PathPatternRequestMatcher`, **context `/shop` bị bỏ**, nhưng **prefix servlet `/mvc` vẫn nằm trong path cần match**. Hai cách tương đương trong ví dụ:

~~~java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

// Dùng Spring Security 6.5+ với parser/matcher phù hợp MVC:
PathPatternRequestMatcher.Builder builder =
        PathPatternRequestMatcher.withDefaults();

// Cách 1: viết toàn bộ path tương đối context
var fullPattern = builder.matcher("/mvc/orders/**");

// Cách 2: cấu hình prefix chung của một servlet
var servletPaths = builder.basePath("/mvc");
var relativePattern = servletPaths.matcher("/orders/**");
~~~

Đây là **đoạn xây matcher cho application có servlet prefix**, không phải class Java độc lập và cũng không tự đăng ký Servlet. Với `basePath("/mvc")`, `matcher("/orders/**")` được hiểu tương ứng path `/mvc/orders/**`. `basePath` là **cơ chế trong matcher builder để tái sử dụng prefix**, không phải thuộc tính thay đổi nơi ứng dụng được deploy.

Không được nhầm:

- `/shop` = **context path**, bỏ ra khỏi `PathPatternRequestMatcher`.
- `/mvc` = **servlet mapping prefix**, cần thể hiện trong path mà `PathPatternRequestMatcher` kiểm tra, trực tiếp hoặc qua `basePath`.
- `/orders/{id}` = **route trong Spring MVC**, thường khai báo tương đối với `DispatcherServlet`.

**Ràng buộc phiên bản/compatibility:** Trong Spring Boot 3.5, thuộc tính `spring.mvc.servlet.path` để đổi đường dẫn DispatcherServlet được tài liệu ứng dụng ghi chú **không tương thích với chiến lược mặc định `PathPatternParser`**. Vì vậy, ví dụ prefix `/mvc/*` ở đây mô tả **Servlet mapping đã được cấu hình tương thích**; không nên cứ đặt `spring.mvc.servlet.path=/mvc` vào dự án Boot 3.5 mặc định rồi kết luận rằng Spring MVC và Security sẽ cùng hoạt động. Nếu cần servlet prefix không mặc định, hãy kiểm tra chiến lược route/matcher, cách đăng ký Servlet và phiên bản thực tế bằng integration test.

## 4. Base path: ít nhất ba nghĩa hoàn toàn khác nhau

Từ “base path” thường bị dùng cho những thứ không cùng lớp. Hãy luôn nói rõ đang đề cập loại nào.

| Cách gọi base path | Ví dụ | Thuộc về | Ảnh hưởng đến matcher |
| --- | --- | --- | --- |
| Servlet **context path** | `server.servlet.context-path=/shop` | Địa chỉ deploy ứng dụng trong Servlet container. | `PathPatternRequestMatcher` so khớp **không bao gồm** nó. |
| Servlet mapping path/prefix | `/mvc/*` | Đăng ký `DispatcherServlet`. | Prefix `/mvc` **được tính** trong path match của `PathPatternRequestMatcher`. |
| `PathPatternRequestMatcher.Builder.basePath` | `.basePath("/mvc")` | Chỉ là cấu hình của **matcher builder**. | Tạo matcher có prefix chung; không thay URL của application. |
| Prefix cấp API trong controller | `@RequestMapping("/api/v1")` | Cách Spring MVC định tuyến endpoint. | Là thành phần route **trong ứng dụng**; thường phải có trong pattern. |
| Reverse proxy/gateway external prefix | `/edge` | Lớp định tuyến ở phía trước Java app. | Chỉ ảnh hưởng request bên trong app **nếu proxy chuyển prefix vào app hoặc forwarded-header processing làm thay đổi request wrapper**. |
| WebFlux base path | `spring.webflux.base-path` | Spring WebFlux/reactive stack. | Không phải context/servlet path của Spring MVC Servlet; không áp dụng trực tiếp cho `HttpServletRequest`. |

Ví dụ, với context path `/shop`, default servlet, controller route `/api/v1/orders`:

~~~text
External direct URL     /shop/api/v1/orders
Context path            /shop
App path                /api/v1/orders
Controller route        /api/v1/orders
PathPattern matcher     /api/v1/orders
~~~

Nếu chuyển controller route từ `/api/v1` sang `/api/v2`, bạn đang đổi một **prefix của endpoint**, không phải context path. Security policy dùng `/api/v1/**` cần được xem lại, khác với việc đổi context deploy từ `/shop` sang `/portal`.

**Quy tắc đặt tên trong tài liệu/team:** dùng các nhãn chính xác như “context path của Servlet”, “servlet mapping prefix”, “API route prefix”, “proxy external prefix” và “matcher builder basePath” thay vì chỉ nói “base path”. Điều này giảm đáng kể lỗi khi chuyển từ môi trường local sang staging/production.

## 5. URL ngoài trình duyệt chưa chắc là URI backend nhìn thấy

Khi request đi qua reverse proxy, ingress hoặc API gateway, **URL bên ngoài không nhất thiết là `getRequestURI()` trong Spring Boot**. Ví dụ:

~~~text
Browser:
  GET https://public.example/edge/shop/api/orders/42

Gateway:
  route /edge/... -> backend
  strip prefix /edge

Backend Servlet app:
  contextPath=/shop
  requestURI=/shop/api/orders/42
  request path relative to context=/api/orders/42

Spring Security PathPatternRequestMatcher:
  matcher("/api/orders/**")
~~~

Trong tình huống giả định này, matcher `/edge/shop/api/orders/**` là **sai** ở backend: nó chứa cả prefix bên ngoài đã bị proxy loại và context path. Việc cần so khớp là **địa chỉ đã đến Servlet container**, sau những biến đổi đã được cấu hình và tin cậy.

Một kiến trúc khác có thể **không strip prefix**, hoặc đổi upstream thành `/api/orders/42` với context root `""`, hoặc chèn prefix qua forwarded headers. Khi đó bảng path sẽ khác: **không có một công thức duy nhất từ URL trình duyệt đến matcher** nếu chưa biết proxy thực sự forward như thế nào.

### Forwarded headers làm bức tranh phức tạp hơn

Nhiều reverse proxy gửi `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix` hoặc các thông tin tương tự. Spring Boot có thuộc tính:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Cấu hình này cho phép framework xử lý thông tin forward trong những môi trường phù hợp; cách wrapper sửa `scheme`, `host`, `contextPath` hoặc URL cần được xác minh theo setup và phiên bản. **Không được coi header do bất cứ client Internet nào gửi là nguồn sự thật về nơi request đến.** Chỉ chấp nhận forwarded headers đã được gateway/proxy tin cậy thiết lập và xóa/ghi đè các giá trị không tin cậy ở ranh giới mạng.

Khi có `ForwardedHeaderFilter` hoặc xử lý tương đương, request object được các lớp trong app nhìn thấy có thể phản ánh thông tin forwarded đã được áp dụng. Vì vậy, khi debug, nên ghi **các trường của request tại vị trí có liên quan** và kiểm tra cấu hình reverse proxy cùng ingress, thay vì suy từ URL người dùng chụp màn hình.

Không sửa lỗi 403 ở production bằng `permitAll("/**")` hoặc thêm `/**` vào security matcher cho “đủ mọi prefix”. Cách này có thể vô tình mở endpoint quản trị mà lỗi ban đầu chỉ là sai đường dẫn.

## 6. RequestMatcher thực sự nhận và so khớp những gì?

Ở mức giao diện, `RequestMatcher` nhận một `HttpServletRequest`. Nhưng **matcher cụ thể** quyết định phần request nào được sử dụng và cách parse pattern. Ví dụ:

| Matcher / cơ chế | Cần lưu ý |
| --- | --- |
| `PathPatternRequestMatcher` (Spring Security 6.5+, dùng mặc định ở 7.x) | Path pattern **tương đối context path**; có thể cấu hình `basePath` để kèm servlet prefix. Phối hợp với Spring MVC `PathPatternParser` tương thích. |
| `MvcRequestMatcher` (legacy, deprecated trong 6.5) | Dựa trên Spring MVC `HandlerMappingIntrospector`; pattern tương đối **servlet path** trong ngữ cảnh MVC, có thể cần `setServletPath` khi có nhiều servlet hoặc mapping prefix. |
| `AntPathRequestMatcher` (legacy, deprecated hướng tới 7.x) | Dùng cơ chế Ant và semantics riêng liên quan `servletPath + pathInfo`; không mặc định là cùng semantics của PathPattern matcher. |
| `RegexRequestMatcher` | Cần kiểm tra chính xác chuỗi đầu vào, flags và biểu thức regex; cẩn thận anchor và encoded path. |
| Custom `RequestMatcher` | Có thể kiểm tra host, method, header, query... nhưng phải viết an toàn và có test cho các trường hợp biên. |

**Đặc biệt về phiên bản:** Ở Spring Security **6.x**, `.requestMatchers(String...)` có thể dựa trên matcher được framework chọn theo classpath/MVC setup hoặc cấu hình. Sang **Spring Security 7.x**, tài liệu migration giải thích Java DSL chuyển về `PathPatternRequestMatcher` và yêu cầu path tương đối context (có servlet prefix khi cần). Vì vậy, khi một pattern cũ bỗng “không match” sau nâng cấp, **đừng chỉ copy cùng chuỗi pattern**; hãy xác minh matcher thực tế, chính sách servlet prefix và thử request với URI thật.

Để minh bạch ở Spring Security 6.5+, có thể truyền một `RequestMatcher` cụ thể thay vì dựa vào cơ chế tự chọn của overload `String`:

~~~java
PathPatternRequestMatcher.Builder matcher =
        PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(matcher.matcher("/api/orders/**"))
        .hasAuthority("ORDER_READ")
    .anyRequest().denyAll()
);
~~~

Cần có các import/config Spring tương ứng; đây là **trích đoạn gắn vào HttpSecurity**, không phải file độc lập. Nếu MVC sử dụng parser tùy chỉnh, phải bảo đảm PathPattern matcher tương thích với quy tắc parse mà handler mapping đang dùng; không trộn parser khác nhau để chứng minh hai lớp route có cùng semantics.

### Tại sao không dùng phép so chuỗi tự viết?

Một chính sách như:

~~~java
// KHÔNG dùng để bảo vệ endpoint:
boolean isAdmin = request.getRequestURI().startsWith("/admin");
~~~

không chỉ nhầm context path mà còn có thể nhận nhầm `/administrator` hoặc `/admin-other` nếu không kiểm tra ranh giới segment. Các trường hợp `%2F`, `%2e`, đường dẫn lặp `//`, `;` (matrix/path parameters), URL encoded Unicode hoặc việc Servlet container normalize path có thể gây thêm sự khác biệt giữa tầng nhận request, MVC routing và security matcher.

**Khuyến nghị:** dùng `PathPatternRequestMatcher` hoặc matcher tương thích đúng framework; giữ `StrictHttpFirewall`/firewall Spring Security phù hợp, không mở rộng chấp nhận encoded slash/semicolon chỉ để làm một URL hoạt động; kiểm thử đường dẫn bất thường qua toàn bộ filter/handler chain. Nếu chuẩn hóa ở proxy, cần kiểm tra sự thống nhất giữa proxy và app để tránh một đường dẫn được gateway xem là public nhưng backend xem là private.

## 7. `securityMatcher` và `requestMatchers` phải dùng cùng bức tranh path

Spring Security có hai cấp matching:

1. **`http.securityMatcher(...)`** xác định **SecurityFilterChain** nào có trách nhiệm với request. `FilterChainProxy` chọn chain khớp đầu tiên theo thứ tự.
2. **`authorizeHttpRequests(...requestMatchers(...))`** xác định **authorization rule** nào áp dụng trong chain đã được chọn, cũng theo rule khớp đầu tiên.

Điều này quan trọng hơn một lỗi 403: **nếu không SecurityFilterChain nào match path thực tế, request có thể hoàn toàn không đi qua security filters của Spring Security**. `anyRequest().denyAll()` chỉ chặn những request **đã được chain đó bao phủ**.

Ví dụ ứng dụng ở context `/shop` và default servlet:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    PathPatternRequestMatcher.Builder paths =
            PathPatternRequestMatcher.withDefaults();
    http.securityMatcher(paths.matcher("/api/**"))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(paths.matcher("/api/public/**")).permitAll()
            .requestMatchers(paths.matcher("/api/orders/**"))
                .hasAuthority("ORDER_READ")
            .anyRequest().denyAll());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
    return http.build();
}
~~~

Đây là **mảnh code đặt trong lớp Spring `@Configuration`** (cần import `@Bean`, `@Order`, `PathPatternRequestMatcher`, `SecurityFilterChain`, `HttpSecurity`), chưa bao gồm cấu hình đăng nhập/token hoặc controller. Hai bean là một **phương án kiến trúc thay thế** cho config đơn chain ở trên, không phải tự động ghép vào cùng cấu hình nếu chưa kiểm soát matcher và `@Order`.

- `GET /shop/api/orders/42` → app path `/api/orders/42` → API chain rồi đến rule `ORDER_READ`.
- `GET /shop/api/public/version` → API chain → public rule → allow tại lớp HTTP.
- `GET /shop/web/home` → không vào API chain, đi fallback chain → DENY.

Nếu **thêm `/shop` vào `securityMatcher("/shop/api/**")`** khi `/shop` chỉ là context path, API chain có thể không bao giờ được chọn cho request mong muốn. Fallback chain giúp **từ chối an toàn** thay vì để request thoát toàn bộ Spring Security, nhưng người dùng vẫn thấy 403/401 và cần sửa chính sách matcher.

Khi app có servlet prefix `/mvc`, hãy cập nhật cả **chain matcher** lẫn **authorization rule matcher** để chúng cùng hiểu path `/mvc/... ` theo `PathPatternRequestMatcher`. Không chỉ sửa một bên. Nếu bạn dùng `MvcRequestMatcher` legacy ở một bên còn `PathPatternRequestMatcher` ở bên kia, khả năng lệch semantics càng cao, nhất là khi nâng cấp.

## 8. Ví dụ đặc biệt: controller path, context path và servlet prefix phối hợp

Giả sử:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    String get(@PathVariable String id) {
        return "order " + id;
    }
}
~~~

Đây là **trích đoạn Spring MVC**, cần các import Spring Web và controller thật. `@RequestMapping("/orders")` không tự quyết định một URL tuyệt đối trong browser; kết quả còn phụ thuộc deployment.

| Deployment | Browser URL path | App path tương đối context | Matcher PathPattern hợp lý |
| --- | --- | --- | --- |
| Context root, default servlet | `/orders/42` | `/orders/42` | `/orders/**` |
| Context `/shop`, default servlet | `/shop/orders/42` | `/orders/42` | `/orders/**` |
| Context `/shop`, servlet prefix `/mvc/*` | `/shop/mvc/orders/42` | `/mvc/orders/42` | `/mvc/orders/**` hoặc `basePath("/mvc")` + `/orders/**` |
| External prefix `/edge` bị proxy strip, context `/shop` | `/edge/shop/orders/42` | Backend nhận `/shop/orders/42` → app path `/orders/42` | `/orders/**` |
| Controller dùng `@RequestMapping("/api/v1/orders")`, context `/shop` | `/shop/api/v1/orders/42` | `/api/v1/orders/42` | `/api/v1/orders/**` |

Mỗi dòng giả định cấu hình Servlet/gateway tương thích. Chỉ cần proxy giữ prefix thay vì strip, hoặc áp dụng `ForwardedHeaderFilter` với thông tin prefix, các giá trị quan sát được có thể thay đổi. **Bảng mang tính mô hình**, không thay thế việc kiểm tra request thực tế trong môi trường đang chạy.

### Debug thực tế: in đúng 4 trường, không suy luận

Trong môi trường phát triển có thể đặt log tạm tại một Servlet `Filter` hoặc controller để xem:

~~~java
// Đoạn chèn vào code Servlet/Spring MVC có HttpServletRequest request:
System.out.println("requestURI = " + request.getRequestURI());
System.out.println("contextPath = " + request.getContextPath());
System.out.println("servletPath = " + request.getServletPath());
System.out.println("pathInfo = " + request.getPathInfo());
~~~

Không log token, cookie, thông tin nhạy cảm hoặc toàn bộ query string một cách tùy tiện. Log trong controller **chỉ nhìn thấy request đã qua được security filters**, nên nếu yêu cầu bị chặn trước controller thì cần quan sát tại filter/trace được bố trí đúng chỗ hoặc dùng Spring Security DEBUG trong môi trường an toàn. Trong các hệ thống có proxy/forwarded filters, hãy ghi rõ log ở **vị trí nào trong filter chain** để hiểu path đang là raw container path hay giá trị đã được wrapper cập nhật.

Khi cần xác minh cấu hình, nên ghi cả URL external do proxy nhận (tại gateway) và path upstream mà proxy đã forward. Chỉ nhìn một trong hai chưa đủ.

## 9. Ví dụ Java 17+ chạy độc lập: nhìn thấy các phần path

Đoạn chương trình sau **không sử dụng Spring và không triển khai `RequestMatcher` thật**. Nó mô phỏng ba request với dữ liệu Servlet API đã biết trong ví dụ, tách context path và kiểm tra một tiền tố `/**` **chỉ cho các sample path bình thường đã chuẩn hóa**. Nó không decode/normalize URL, không xử lý nhiều kiểu mapping, firewall hoặc encoded slash. **Không sao chép hàm demo này để thay cho Spring Security matcher trong production.**

Lưu chính xác thành tệp **`RequestPathComponentsDemo.java`**:

~~~java
public class RequestPathComponentsDemo {
    record Example(String requestUri, String contextPath,
                   String servletPath, String pathInfo) {
        String insideApplication() {
            if (!contextPath.isEmpty() && !requestUri.equals(contextPath)
                    && !requestUri.startsWith(contextPath + "/")) {
                throw new IllegalArgumentException("Invalid sample context");
            }
            return requestUri.substring(contextPath.length());
        }
    }

    static boolean matchesTrailingWildcard(String actual, String pattern) {
        if (!pattern.endsWith("/**")) {
            throw new IllegalArgumentException("Demo supports /** only");
        }
        String prefix = pattern.substring(0, pattern.length() - 3);
        return actual.equals(prefix) || actual.startsWith(prefix + "/");
    }

    public static void main(String[] args) {
        Example normal = new Example(
                "/shop/orders/42", "/shop", "/orders/42", null);
        Example prefixed = new Example(
                "/shop/mvc/orders/42", "/shop", "/mvc", "/orders/42");
        Example behindProxy = new Example(
                "/shop/api/orders/42", "/shop", "/api/orders/42", null);

        System.out.println("Default requestURI: " + normal.requestUri());
        System.out.println("Default contextPath: " + normal.contextPath());
        System.out.println("Default servletPath: " + normal.servletPath());
        System.out.println("Default pathInfo: " + normal.pathInfo());
        System.out.println("Default app path: " + normal.insideApplication());
        System.out.println("Default /orders/**: "
                + matchesTrailingWildcard(normal.insideApplication(), "/orders/**"));
        System.out.println("Incorrect /shop/orders/**: "
                + matchesTrailingWildcard(normal.insideApplication(), "/shop/orders/**"));
        System.out.println("Prefixed servletPath: " + prefixed.servletPath());
        System.out.println("Prefixed pathInfo: " + prefixed.pathInfo());
        System.out.println("Prefixed app path: " + prefixed.insideApplication());
        System.out.println("Prefixed /mvc/orders/**: "
                + matchesTrailingWildcard(prefixed.insideApplication(), "/mvc/orders/**"));
        System.out.println("Incorrect prefixed /orders/**: "
                + matchesTrailingWildcard(prefixed.insideApplication(), "/orders/**"));
        System.out.println("Proxy external path: /edge/shop/api/orders/42");
        System.out.println("Proxy backend requestURI: " + behindProxy.requestUri());
        System.out.println("Proxy backend app path: " + behindProxy.insideApplication());
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 RequestPathComponentsDemo.java
java RequestPathComponentsDemo
~~~

Kết quả chuẩn:

~~~text
Default requestURI: /shop/orders/42
Default contextPath: /shop
Default servletPath: /orders/42
Default pathInfo: null
Default app path: /orders/42
Default /orders/**: true
Incorrect /shop/orders/**: false
Prefixed servletPath: /mvc
Prefixed pathInfo: /orders/42
Prefixed app path: /mvc/orders/42
Prefixed /mvc/orders/**: true
Incorrect prefixed /orders/**: false
Proxy external path: /edge/shop/api/orders/42
Proxy backend requestURI: /shop/api/orders/42
Proxy backend app path: /api/orders/42
~~~

**Điều học được:** cùng một route nghiệp vụ `/orders/42` có thể có `requestURI` khác nhau do context/servlet mapping. Với context `/shop`, pattern tương đối context là `/orders/**`. Khi servlet prefix `/mvc` xuất hiện, path để `PathPatternRequestMatcher` xét là `/mvc/orders/42`. Với proxy đã strip `/edge`, backend không nhìn thấy prefix `/edge` trong requestURI minh họa.

Phép kiểm tra `matchesTrailingWildcard` của demo **chỉ minh họa tiền tố trên các chuỗi đã chuẩn hóa**, không thay thế `PathPatternParser`, `HttpFirewall` hoặc `RequestMatcher` của Spring Security. Các đoạn `javac`/`java` phía trên chạy độc lập với JDK; các ví dụ `HttpSecurity` trước đó cần project Spring và dependency.

## 10. Kiểm thử RequestMatcher đúng đường dẫn, không chỉ đúng response

Một bài test `get("/orders/42")` trong môi trường local mặc định **không chứng minh** hệ thống vẫn phân quyền đúng khi deploy dưới `/shop` hoặc có `/mvc`. Với `spring-security-test`, MockMvc có thể mô phỏng `contextPath`:

~~~java
// Trích đoạn trong Spring Boot + MockMvc integration test,
// giả định controller GET /orders/{id} tồn tại và security chain hoạt động.
mvc.perform(get("/shop/orders/42")
        .contextPath("/shop")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("ORDER_READ"))));
// Nếu controller/data hợp lệ, request vượt qua kiểm tra HTTP;
// vẫn cần assert status/body/authorization nghiệp vụ thích hợp.
~~~

Đoạn test cần Spring Security Test, MockMvc, static imports và ứng dụng cấu hình tương ứng; không phải chương trình độc lập. Thay vì chỉ assert HTTP 200, cần thiết kế **test các trường hợp DENY** ở filter/service, và test header/route theo đúng request fields.

Ma trận kiểm thử tối thiểu:

| Tình huống | Đường nhìn ở browser / app | Kỳ vọng |
| --- | --- | --- |
| Root context, default servlet | `/orders/42` / `/orders/42` | Rule `/orders/**` match. |
| Context `/shop` | `/shop/orders/42` / `/orders/42` | Rule `/orders/**` match; `/shop/orders/**` thường không. |
| Context `/shop`, servlet `/mvc/*` | `/shop/mvc/orders/42` / `/mvc/orders/42` | Matcher PathPattern có prefix `/mvc` match. |
| Sai servlet prefix | App path `/mvc/orders/42`, rule `/orders/**` | Không match theo PathPattern; cần rule đúng và fallback DENY. |
| Gateway strip `/edge` | External `/edge/shop/api/orders/42`, backend `/shop/api/orders/42` | Rule backend `/api/orders/**` match. |
| Request có query | `/shop/orders/42?view=summary` | Rule path không vì query mà đổi. |
| HTTP method khác | `POST /shop/orders/42` | Rule `GET` không tự cấp quyền cho POST. |
| Prefix giả tương tự | `/shop/orders-admin/42` | Rule `/orders/**` không được match `/orders-admin/**`. |
| Encoded path, double slash, semicolon | Các variant được gateway/container chấp nhận hoặc từ chối | Phải bảo đảm matcher và MVC xử lý nhất quán; kiểm thử firewall/proxy. |
| Không chain nào match | Request không vào một security chain | **Rủi ro bypass Spring Security**; cần fallback chain thích hợp. |
| Đúng path nhưng không có `ORDER_READ` | `/shop/orders/42` | DENY ở authorization. |
| Có `ORDER_READ` nhưng khác tenant | Cùng URL path hợp lệ | DENY ở tầng resource/service. |

Một test cho **chain selection** cũng rất cần thiết khi triển khai nhiều `SecurityFilterChain`: có `anyRequest().denyAll()` trong fallback giúp request lạc route bị từ chối thay vì nằm ngoài Spring Security. Nếu URL không có controller, 404 không chứng minh rule đúng/sai; muốn phân biệt hãy thêm controller fixture hoặc gọi trực tiếp matcher với `MockHttpServletRequest` được xây đúng `contextPath`, `servletPath`, `pathInfo`.

### Mẹo test độc lập matcher với MockHttpServletRequest

Trong unit test sử dụng `spring-test` và `spring-security-web` 6.5+, có thể tạo request giả và gọi trực tiếp:

~~~java
MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/shop/orders/42");
request.setContextPath("/shop");
request.setServletPath("/orders/42");

RequestMatcher matcher =
        PathPatternRequestMatcher.withDefaults()
                .matcher(HttpMethod.GET, "/orders/**");

boolean matched = matcher.matches(request);
// mong đợi true với dữ liệu request và matcher minh họa
~~~

Đây là **đoạn test có dependency Spring** và cần import `MockHttpServletRequest` (`org.springframework.mock.web`), `RequestMatcher`, `PathPatternRequestMatcher` và `HttpMethod`; không chạy với JDK thuần. Để test servlet prefix, đặt URI `/shop/mvc/orders/42`, `setContextPath("/shop")`, `setServletPath("/mvc")`, `setPathInfo("/orders/42")`, rồi dùng `basePath("/mvc").matcher("/orders/**")`.

Test matcher trực tiếp rất hữu ích để loại trừ lỗi path, nhưng **chưa đủ cho toàn bộ ứng dụng**: phải có integration test filter chain, MVC route, authentication, proxy rewrite và dữ liệu nghiệp vụ nếu cần.

## 11. Những lỗi thường gặp khi deploy khác môi trường

1. **Ghi context path hai lần:** `server.servlet.context-path=/shop` rồi dùng `PathPatternRequestMatcher("/shop/orders/**")`. → Trong trường hợp PathPattern, viết `/orders/**`.
2. **Quên servlet mapping prefix:** MVC thực ở `/mvc/*`, nhưng matcher PathPattern chỉ `/orders/**`. → Dùng `basePath("/mvc")` hoặc path đầy đủ tương đối context `/mvc/orders/**`.
3. **Lấy URL browser làm `getRequestURI()` của backend:** proxy strip/thêm prefix. → So request path ở gateway và backend, kiểm tra forward headers.
4. **Nhầm `basePath` của matcher với `server.servlet.context-path`:** đổi basePath không thay đổi URL app và không tự tạo context path.
5. **Tưởng `requestMatchers("/api/**")` là cấu hình chọn toàn chain:** thực ra `securityMatcher` mới giới hạn chain; rule matcher chỉ nằm bên trong.
6. **Không có fallback SecurityFilterChain:** path không match chain có thể bỏ qua Spring Security. → Bố trí chain cuối bao phủ mọi request với mặc định an toàn.
7. **Dùng `getRequestURI().startsWith(...)` làm logic security:** không loại context, dễ nhận nhầm segment và chịu rủi ro encoded path. → Dùng matcher đã kiểm chứng và firewall phù hợp.
8. **Dựa vào `MvcRequestMatcher` cũ nhưng nâng lên Spring Security 7 không kiểm thử:** semantics về servlet prefix đã thay đổi rõ ràng. → Chuyển PathPattern matcher và xác định prefix có chủ đích.
9. **Thiết lập `spring.mvc.servlet.path` trong Boot 3.5 cùng default PathPatternParser một cách vô thức:** có vấn đề compatibility. → Xem tài liệu phiên bản, chọn chiến lược routing tương thích và test full stack.
10. **Tin `X-Forwarded-Prefix` do client gửi trực tiếp:** có thể làm ứng dụng hiểu sai scheme/host/path. → Chỉ tin forwarded headers của proxy có kiểm soát, strip untrusted headers.
11. **Sửa 403 bằng `permitAll("/**")`:** bỏ lớp authorization thay vì xử lý đúng prefix/matcher. → Chẩn đoán chain, request fields và authorities.
12. **Chỉ test status của controller trong root context:** thiếu bài test deployment có context/servlet prefix, proxy, encoded path, query, HTTP method.
13. **Đồng nhất host/query với path matcher:** matcher URL pattern thông thường không tự kiểm tra hostname, port, query; nếu cần policy theo các dữ liệu đó, phải dùng matcher/logic phù hợp.
14. **Quên điều kiện tài nguyên:** `ORDER_READ` chỉ cho phép loại hành động, chưa xác minh Order 42 thuộc tenant nào.

## 12. Checklist thiết kế policy cho một ứng dụng có prefix

Trước khi merge cấu hình Spring Security dùng URL matcher, hãy trả lời có bằng chứng:

1. **Client gọi URL nào?** Ghi scheme, host, path, query ở điểm vào công khai; không dùng query như path.
2. **Gateway chuyển request ra sao?** Strip/thêm prefix, rewrite, servlet context của backend và forwarded headers có đáng tin không?
3. **`getRequestURI`, `getContextPath`, `getServletPath`, `getPathInfo` thực tế là gì?** Ghi log tạm ở vị trí phù hợp, không suy đoán.
4. **Matcher implementation nào đang được dùng?** `PathPatternRequestMatcher`, `MvcRequestMatcher`, Ant, Regex hay custom; Spring Security version nào?
5. **Pattern được viết tương đối lớp nào?** Với PathPattern thì bỏ context path; đưa servlet prefix vào path hoặc `basePath` nếu cần.
6. **Có nhiều SecurityFilterChain không?** `securityMatcher` nào thắng, `@Order` thế nào, fallback có bao phủ request không?
7. **Trong chain đã chọn, rule nào thắng?** `requestMatchers` cụ thể trước, method có được kiểm soát, `anyRequest` đúng chính sách?
8. **Nếu URL được phép, người gọi có được phép thao tác trên bản ghi không?** Policy owner/tenant/state ở service phải độc lập với matching path.
9. **Đã test deployment context/servlet/proxy thực tế chưa?** Ít nhất một ca ALLOW, một ca DENY, một ca prefix sai và một ca fallback.
10. **Các đường dẫn bất thường được xử lý nhất quán không?** Encoded slash, dấu chấm, double slash, semicolon, proxy normalization và HttpFirewall.

**Điểm nhớ cốt lõi:** *Context path* định vị ứng dụng trong Servlet container; *servlet path* phản ánh cách request đến Servlet; *basePath* của `PathPatternRequestMatcher.Builder` chỉ là cách định nghĩa prefix matcher; *địa chỉ thực được so khớp* là path mà request matcher cụ thể nhìn thấy **sau biến đổi phù hợp trong runtime**, không nhất thiết giống URL browser. Với `PathPatternRequestMatcher`, **bỏ context path, tính đến servlet prefix nếu có và xác minh quy tắc trên request thật**. Đúng path matcher mới bảo đảm rule được áp dụng; đúng quyền trên tài nguyên vẫn là trách nhiệm bổ sung của service.

### Tài liệu chính thức

- [Spring Security 6.5 — Migration: servlet path prefix và PathPatternRequestMatcher](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html)
- [Spring Security — Authorize HttpServletRequests và RequestMatcher](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — PathPatternRequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html)
- [Spring Framework — MVC Path Matching và Servlet API](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html)
- [Spring Boot 3.5 — Common Application Properties: servlet context/servlet path/forward headers](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
