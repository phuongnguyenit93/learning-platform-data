# Context path, servlet path và đường dẫn dùng khi khớp yêu cầu

Trong ứng dụng **Spring Security chạy trên Servlet**, một URL có thể chứa nhiều phần đường dẫn. Nhầm lẫn giữa đường dẫn ở phía trình duyệt, đường dẫn bên trong ứng dụng, đường dẫn ánh xạ servlet và mẫu dùng bởi Spring Security có thể làm quy tắc phân quyền không khớp như dự kiến. Mục tiêu của bài là đọc đúng các thành phần đó và chọn `RequestMatcher` phù hợp.

## 1. Phân tách một yêu cầu HTTP

Xét một ứng dụng triển khai dưới context path `/app`, với `DispatcherServlet` được ánh xạ theo tiền tố `/mvc/*`. Trình duyệt gửi:

~~~http
GET /app/mvc/admin/reports?page=2 HTTP/1.1
Host: example.test
~~~

Giả sử servlet container sử dụng ánh xạ tiền tố trên, `HttpServletRequest` cung cấp:

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `getContextPath()` | `/app` | Đường dẫn gốc của web application trong servlet container. |
| `getServletPath()` | `/mvc` | Phần đường dẫn khớp ánh xạ servlet `/mvc/*`. |
| `getPathInfo()` | `/admin/reports` | Phần còn lại sau servlet path đối với ánh xạ tiền tố. |
| `getRequestURI()` | `/app/mvc/admin/reports` | URI của yêu cầu, gồm context path và phần đường dẫn, không chứa query string. |
| `getQueryString()` | `page=2` | Dữ liệu sau dấu `?`, không phải thành phần path để so khớp trong các matcher đường dẫn thông dụng. |

Cách hình dung hữu ích cho **trường hợp ánh xạ tiền tố** là:

~~~text
URL:           https://example.test/app/mvc/admin/reports?page=2
                              └─┬┘└┬┘└──────┬─────┘
                         context  servlet   pathInfo
                         /app     /mvc      /admin/reports

requestURI                = /app/mvc/admin/reports
servletPath + pathInfo    = /mvc/admin/reports
đường dẫn trong servlet   = /admin/reports
queryString               = page=2
~~~

Đây là sơ đồ của **một kiểu servlet mapping**, không phải phép cộng chuỗi áp dụng vô điều kiện cho mọi request. Servlet specification cho phép ánh xạ chính xác, ánh xạ tiền tố, ánh xạ phần mở rộng và servlet mặc định; cách container trả về `servletPath` và `pathInfo` phụ thuộc mapping thực tế. `getPathInfo()` thường là `null` với ánh xạ mặc định `/` hoặc ánh xạ chính xác. Không nên viết code bảo mật dựa trên giả thiết rằng `pathInfo` luôn khác `null`.

**Context path không đồng nghĩa servlet path.** `server.servlet.context-path=/app` (trong Spring Boot) đặt tiền tố cho toàn web application. `spring.mvc.servlet.path=/mvc` là tùy chọn ánh xạ riêng cho Spring MVC `DispatcherServlet`. Chúng giải quyết hai tầng khác nhau; cần kiểm tra thêm tương thích của servlet mapping và chiến lược path matching ở phiên bản Spring Boot/Spring MVC đang chạy.

Ví dụ cấu hình thường gặp:

~~~properties
server.servlet.context-path=/app
spring.mvc.servlet.path=/mvc
~~~

Với `DispatcherServlet` mặc định được ánh xạ `/` thay vì `/mvc/*`, cùng một endpoint ứng dụng `/admin/reports` dưới context `/app` sẽ có URL `/app/admin/reports`. Trường hợp phổ biến này thường trả về `servletPath=/admin/reports` và `pathInfo=null`. Vì vậy, chỉ nhìn URL hoặc tên controller chưa đủ để suy ra tất cả thuộc tính của `HttpServletRequest`.

## 2. Java nhìn thấy gì và vì sao không tự cắt URL?

Minh họa Java 17 độc lập sau đây ghép **các giá trị giả định** từ ví dụ ánh xạ tiền tố; nó không thay thế việc đọc `HttpServletRequest` thực tế:

~~~java
public class PathPartsDemo {
    public static void main(String[] args) {
        String contextPath = "/app";
        String servletPath = "/mvc";
        String pathInfo = "/admin/reports";

        String requestUri = contextPath + servletPath + pathInfo;

        System.out.println("requestURI = " + requestUri);
        System.out.println("appPath = " + servletPath + pathInfo);
        System.out.println("pathInfo = " + pathInfo);
    }
}
~~~

Lưu tên tệp là `PathPartsDemo.java`, rồi chạy:

~~~bash
javac PathPartsDemo.java
java PathPartsDemo
~~~

Kết quả stdout chính xác:

~~~text
requestURI = /app/mvc/admin/reports
appPath = /mvc/admin/reports
pathInfo = /admin/reports
~~~

Trong ứng dụng thật, đọc các thành phần từ request để biết servlet container đã diễn giải chúng thế nào. Không tự dùng `substring` hoặc `startsWith` trên URI thô để xây dựng kiểm tra quyền truy cập: còn có URL encoding, đường dẫn chuẩn hóa, dấu `;`, nhiều servlet mapping và cấu hình proxy.

Ví dụ một filter chẩn đoán (đoạn mã thuộc **ứng dụng Spring Boot/Spring MVC có dependency Jakarta Servlet**, không phải chương trình Java chạy độc lập):

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class PathDiagnosticsFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(PathDiagnosticsFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        log.debug("contextPath={}, servletPath={}, pathInfo={}, requestURI={}",
                request.getContextPath(),
                request.getServletPath(),
                request.getPathInfo(),
                request.getRequestURI());

        chain.doFilter(request, response);
    }
}
~~~

Chỉ bật log chẩn đoán tại môi trường phù hợp, không ghi token, cookie hoặc thông tin nhạy cảm vào log. Với request qua proxy, đối chiếu log ở ứng dụng và đường dẫn thật do proxy chuyển tiếp.

## 3. Spring Security khớp đường dẫn ở đâu?

Có ba quyết định khác nhau trong luồng xử lý:

1. **Servlet container** nhận request và quyết định ứng dụng/servlet nào xử lý nó; context path và servlet mapping tham gia ở đây.
2. **`FilterChainProxy` của Spring Security** duyệt danh sách `SecurityFilterChain` theo thứ tự và chọn **chain đầu tiên** có `RequestMatcher` khớp. Trong cấu hình `HttpSecurity`, `securityMatcher(...)` giới hạn phạm vi của một chain.
3. **Quy tắc authorization trong chain đã chọn** đánh giá các `requestMatchers(...)` theo thứ tự khai báo và dùng quy tắc đầu tiên phù hợp, ví dụ `permitAll()`, `hasRole("ADMIN")` hoặc `authenticated()`.

Hai API có tên gần giống nhau nhưng **khác cấp độ quyết định**:

| API | Câu hỏi trả lời | Hậu quả khi không khớp |
| --- | --- | --- |
| `http.securityMatcher(...)` | Request có đi vào **SecurityFilterChain này** không? | Thử chain kế tiếp; nếu không chain nào khớp thì request không được bảo vệ bởi các filter của những chain ấy. |
| `authorizeHttpRequests(...requestMatchers(...))` | Trong chain đã chọn, **quy tắc quyền nào** áp dụng? | Xét quy tắc sau, thường đến `anyRequest()`. |

Ví dụ với `DispatcherServlet` mặc định ánh xạ `/` và một ứng dụng được triển khai ở `/app`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đoạn trên là cấu hình cho dự án Spring Security; nó cần ứng dụng Spring Boot và các dependency tương ứng. Về mặt đường dẫn, một request đến `/app/api/admin/users` nằm trong context `/app` nhưng matcher cấu hình vẫn dùng mẫu `/api/**` và `/api/admin/**` trong trường hợp này. **Không tự thêm `/app` vào mẫu chỉ vì URL công khai có context path đó.** Đối với các matcher đường dẫn chuẩn của Spring Security, context path thường được loại khỏi phạm vi so khớp; chi tiết còn tùy loại `RequestMatcher`.

**Điểm cần chú ý:** Cấu hình trên chỉ định nghĩa chain cho `/api/**`. Nếu dự án cần bảo vệ cả `/login`, `/actuator` hoặc các endpoint khác, phải có chain/chiến lược phù hợp cho chúng. Một chain duy nhất với `securityMatcher("/api/**")` không tự động bảo vệ mọi URL ngoài `/api/**`. Và `permitAll()` vẫn để request đi qua các filter của chain; nó khác việc bỏ qua Spring Security filter hoàn toàn.

## 4. Tại sao servlet path làm matcher dễ nhầm?

Giả sử ứng dụng ánh xạ `DispatcherServlet` tới `/mvc/*`, còn controller có endpoint `@GetMapping("/admin/reports")`. Người dùng truy cập `/app/mvc/admin/reports`. Có ít nhất ba chuỗi hợp lệ nhưng có nghĩa khác nhau:

- URI đầy đủ trong servlet request: `/app/mvc/admin/reports`.
- Phần path trong ứng dụng không gồm context path: `/mvc/admin/reports`.
- Đường dẫn tương đối trong servlet ánh xạ tiền tố: `/admin/reports`.

**Các `RequestMatcher` không nhất thiết cùng diễn giải chuỗi pattern.** Không có quy tắc rằng mọi cách gọi `requestMatchers("/admin/**")` đều so sánh với một chuỗi duy nhất do chính ứng dụng tự cắt ra.

Trong nhiều cấu hình **Spring Security 6.x + Spring MVC**, `MvcRequestMatcher` dùng `HandlerMappingIntrospector` để theo semantics matching của Spring MVC. Khi `DispatcherServlet` có servlet path riêng, nên đặt servlet path tường minh cho matcher MVC:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class MvcSecurityConfig {
    @Bean
    SecurityFilterChain mvcChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector)
                        .servletPath("/mvc");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(mvc.pattern("/public/**")).permitAll()
                .requestMatchers(mvc.pattern("/admin/**")).hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Trong ví dụ này, `/mvc` định danh servlet path, còn `/admin/**` là pattern theo đường dẫn MVC bên trong servlet. Đó là một cách tường minh để tránh nhầm `/mvc/admin/**` với `/admin/**`. Lớp `MvcRequestMatcher` là API theo thế hệ Spring Security 6.x; nếu dùng Spring Security mới hơn, cần kiểm tra matcher được phiên bản đó hỗ trợ và mặc định sử dụng.

Với các cấu hình dùng `PathPatternRequestMatcher` (được giới thiệu ở các phiên bản Spring Security mới hơn), tư duy tương ứng là xác định base path của servlet rồi khớp phần còn lại, ví dụ qua builder `PathPatternRequestMatcher.withDefaults().basePath("/mvc")`, với điều kiện chiến lược path matching tương thích. Ngược lại, `AntPathRequestMatcher` trong cấu hình cũ so khớp trên `servletPath + pathInfo` (bỏ query string), nên mẫu tương ứng có thể cần `/mvc/admin/**`. Không sao chép nguyên pattern từ loại matcher này sang loại khác mà chưa kiểm thử.

Bảng sau tóm tắt **các ví dụ giả định** khi context path là `/app` và servlet prefix là `/mvc/*`:

| URL nhận được | `servletPath` | `pathInfo` | Matcher MVC có `servletPath("/mvc")` + `pattern("/admin/**")` |
| --- | --- | --- | --- |
| `/app/mvc/admin/reports` | `/mvc` | `/admin/reports` | Khớp. |
| `/app/mvc/public/help` | `/mvc` | `/public/help` | Không khớp với rule admin. |
| `/app/mvc/administrator` | `/mvc` | `/administrator` | Không khớp với segment `/admin/**`. |
| `/app/mvc/admin/reports?page=2` | `/mvc` | `/admin/reports` | Vẫn khớp: query không làm thay đổi path. |

Giá trị trong bảng được suy ra từ ánh xạ prefix cụ thể và pattern cụ thể; khi dùng servlet mặc định, controller servlet khác hoặc RequestMatcher khác, phải xác nhận lại các trường request thực tế.

## 5. Thứ tự rule, HTTP method và nhiều filter chain

Trong một chain, đặt rule cụ thể trước rule rộng. Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll());
~~~

Đoạn này cần `import org.springframework.http.HttpMethod;` và nằm trong cấu hình `HttpSecurity` của ứng dụng. Nó minh họa rằng `GET /api/public/news` có thể được phép, còn `POST /api/public/news` không khớp rule GET và sẽ rơi vào yêu cầu đăng nhập của `/api/**`. Một `anyRequest().permitAll()` đặt quá rộng hoặc một rule `/api/**` đặt trước `/api/admin/**` có thể làm rule đặc thù không còn được xét tới.

Khi có nhiều `SecurityFilterChain`, thứ tự chain quyết định chain đầu tiên khớp. Ví dụ thiết kế: chain `@Order(1)` chỉ áp dụng `/api/**`; chain `@Order(2)` là fallback cho phần còn lại. Hãy kiểm tra cả matcher chọn chain lẫn matcher phân quyền trong chain. Nếu đặt `securityMatcher("/api/**")` mà sau đó khai báo `requestMatchers("/admin/**")`, rule `/admin/**` không thể giúp bảo vệ endpoint nằm hoàn toàn ngoài phạm vi chain ấy.

Phân biệt ba trường hợp dễ bị lẫn: **không chọn được security chain**, **đã chọn chain nhưng không khớp rule đặc thù**, và **khớp rule nhưng bị từ chối vì chưa xác thực/thiếu quyền**. Các trường hợp này dẫn tới cách sửa khác nhau.

## 6. Kiểm tra matcher bằng request thực, log và test

Khi một endpoint được cho là "public" nhưng trả `401/403`, hoặc endpoint tưởng cần quyền lại đi qua, quy trình chẩn đoán hữu ích là:

1. Ghi lại **method**, URL/path mà client gửi, path mà reverse proxy thực sự forward, servlet mapping và các giá trị `getContextPath()`, `getServletPath()`, `getPathInfo()`, `getRequestURI()`.
2. Xác định đang dùng `MvcRequestMatcher`, `PathPatternRequestMatcher`, matcher kiểu Ant hay matcher tùy biến; đừng chỉ nhìn chuỗi pattern.
3. Xem thứ tự `SecurityFilterChain`, đặc biệt phạm vi `securityMatcher`; sau đó mới xem thứ tự các `requestMatchers` trong `authorizeHttpRequests`.
4. Kiểm tra HTTP method, query string, URL encoding và dấu gạch chéo cuối path. Quy tắc có thể khác nhau theo version và matching strategy.
5. Tạo request thử cho ít nhất một path **phải khớp**, một path **không được khớp** và một path **giống tên nhưng khác segment** như `/admin/reports` và `/administrator`. Test bằng người dùng chưa đăng nhập và người dùng có/không có role.

Có thể bật log ở môi trường kiểm thử:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.intercept=TRACE
~~~

Log giúp thấy filter chain được chọn và nhiều quyết định truy cập, nhưng không thay thế assertion kiểm thử; thông điệp log thay đổi theo phiên bản. Nên tắt hoặc giảm mức log sau khi tìm ra lỗi.

Ví dụ kiểm thử `MockMvc` trong dự án có Spring Security filter được tích hợp. Khi mô phỏng context path và servlet prefix, phải thiết lập request nhất quán với mapping thực tế:

~~~java
mockMvc.perform(get("/app/mvc/admin/reports")
        .contextPath("/app")
        .servletPath("/mvc")
        .pathInfo("/admin/reports"))
    .andExpect(status().isUnauthorized());
~~~

Đây là **đoạn trong lớp test Spring Boot** (cần `MockMvc`, static imports của `get`/`status`, endpoint tồn tại và HTTP Basic hoặc entry point trả `401`). Kết quả `401` chỉ đúng dưới các tiền đề đó, với request chưa xác thực; ứng dụng dùng form login có thể redirect `302`. Test tiếp với principal có role `ADMIN` và role khác để xác nhận rule, thay vì suy luận an toàn từ một status đơn lẻ. Nếu có nhiều servlet/filter chain, cần xác nhận request giả lập được ánh xạ như request thật của container.

### Khi ứng dụng chạy sau reverse proxy

Giả sử client gọi `https://host.example/gateway/app/mvc/admin/reports` nhưng proxy loại bỏ `/gateway` trước khi chuyển vào ứng dụng. Khi đó ứng dụng có thể chỉ nhận `/app/mvc/admin/reports`. Pattern Security cần được thiết kế theo thông tin request mà ứng dụng thực sự nhìn thấy, không mặc nhiên theo URL bên ngoài. Việc xử lý `Forwarded`, `X-Forwarded-*` hoặc `ForwardedHeaderFilter` còn có thể ảnh hưởng các thuộc tính đường dẫn; ghi nhận cấu hình thực tế trước khi chỉnh matcher.

Tương tự, không dùng `startsWith("/admin")` để thay cho matcher đã chuẩn hóa: cách kiểm tra ấy có thể nhận nhầm `/administrator`, và tự xử lý decode `%2F` hoặc dấu `;` có thể tạo khác biệt giữa security layer và MVC routing. Cần dùng cùng chiến lược path matching với framework, cấu hình xử lý URL bất thường nhất quán và kiểm thử các trường hợp biên.

## 7. Bài tập tự kiểm tra

**Tình huống A.** Web application có context `/portal`, servlet mapping `/ui/*`. Yêu cầu `GET /portal/ui/admin/dashboard?tab=stats` đi vào servlet này. Hãy xác định các phần path.

**Đáp án:** `contextPath=/portal`; `servletPath=/ui`; `pathInfo=/admin/dashboard`; `requestURI=/portal/ui/admin/dashboard`; `queryString=tab=stats`. Nếu dùng matcher MVC có `servletPath("/ui")` và `pattern("/admin/**")`, URL này khớp rule admin.

**Tình huống B.** Một chain có `securityMatcher("/api/**")`, trong đó khai báo `requestMatchers("/admin/**").hasRole("ADMIN")`. Endpoint `/admin/metrics` nằm ngoài `/api/**`. Rule admin này có bảo vệ endpoint không?

**Đáp án:** Không. Chain không được chọn cho endpoint đó. Cần thiết kế phạm vi chain hoặc fallback chain đúng thay vì chỉ thêm authorization rule trong chain không áp dụng.

**Tình huống C.** Ở servlet mặc định `/`, ứng dụng có context `/shop`. URL công khai là `/shop/api/orders/7` nhưng rule Security dùng `/shop/api/**`. Tại sao rule có thể không khớp?

**Đáp án:** Vì context path `/shop` thường nằm ngoài đường dẫn dùng để so khớp ở các matcher chuẩn. Pattern ứng viên đúng theo path trong ứng dụng là `/api/**`. Phải xác nhận loại matcher và servlet mapping trước khi sửa cấu hình.

## 8. Checklist khi xây dựng quy tắc đường dẫn

- Xác nhận **context path**, **servlet mapping**, **servletPath/pathInfo thực tế** và URL sau proxy.
- Xác nhận **loại `RequestMatcher`**, version Spring Security và cách engine xử lý servlet prefix.
- Phân biệt **chọn chain** bằng `securityMatcher` với **phân quyền** bằng `requestMatchers`.
- Đặt rule cụ thể trước rule bao quát, có fallback rõ ràng và kiểm thử cả các endpoint ngoài phạm vi chain.
- Không ghép context path vào pattern một cách máy móc; không cắt chuỗi URL thô để quyết định quyền.
- Viết test cho method, prefix, route gần giống nhau, người dùng chưa xác thực, người dùng thiếu role và trường hợp proxy nếu có.

**Ghi nhớ:** Đường dẫn mà client nhìn thấy, đường dẫn servlet container phân tách và đường dẫn mà từng `RequestMatcher` sử dụng là các khái niệm liên quan nhưng không đồng nhất. Hiểu rõ lớp nào đang khớp cái gì sẽ giúp viết rule Spring Security chính xác và dễ kiểm chứng.