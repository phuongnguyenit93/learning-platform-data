# Request matcher và thay đổi cách khớp đường dẫn giữa các dòng

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Cấu hình và kiểm chứng các lớp phòng vệ HTTP/trình duyệt của Spring Security qua **Servlet** và **Reactive**: phân quyền URL, CSRF, CORS, security headers/CSP/HSTS, HTTP firewall và session.  
> **Mốc tài liệu:** 26/11/2026. Các ví dụ chính sử dụng Lambda DSL theo Spring Security 7.x; ví dụ quá độ cho Spring Security 5.8/6.x được ghi rõ. Luôn kiểm tra phiên bản đã resolve và tài liệu đúng dòng khi áp dụng.

## 1. Tại sao request matcher có thể trở thành lỗ hổng bảo mật?

Giả sử ứng dụng có endpoint `GET /admin/reports` yêu cầu vai trò `ADMIN`. Sau khi nâng phiên bản Spring Security, một người dùng thường truy cập được URL `/admin/reports/` hoặc một dạng URL được proxy viết lại; đồng thời nhóm phát triển thấy cấu hình vẫn có `hasRole("ADMIN")`. Lý do có thể không nằm ở kiểm tra vai trò, mà nằm ở **quy tắc chọn URL**, **chọn filter chain** hoặc **cách các thành phần diễn giải đường dẫn**.

Trong một ứng dụng web, ít nhất bốn nơi có thể diễn giải đường dẫn request:

```text
Trình duyệt / HTTP client
          |
          v
Reverse proxy / ingress: có thể rewrite hoặc decode URI
          |
          v
Servlet container hoặc WebFlux HTTP server
          |
          v
Spring Security: chọn filter chain theo matcher
          |
          v
Spring Security: chọn authorization rule theo matcher
          |
          v
Spring MVC / WebFlux: chọn controller theo URL mapping
```

**Câu hỏi bảo mật cần trả lời:** với *mọi URL thực sự dẫn tới handler nhạy cảm*, Security có chọn đúng chain và đúng quy tắc phân quyền trước khi handler chạy hay không? Cấu hình URL rất dễ đọc nhưng hành vi thực tế còn phụ thuộc thư viện matcher, servlet path, context path, HTTP method, DispatcherType và firewall.

Mục tiêu sau bài:

1. Hiểu vai trò `RequestMatcher` và `ServerWebExchangeMatcher`.
2. Phân biệt `securityMatcher` với `requestMatchers`/`pathMatchers` và quy tắc *first match wins*.
3. Di chuyển cú pháp từ `antMatchers`/`mvcMatchers` sang cách khai báo phù hợp Spring Security 5.8/6.x/7.x.
4. Nắm thay đổi sang `PathPatternRequestMatcher` ở Spring Security 7 và những khác biệt quan trọng về cấu trúc pattern.
5. Xử lý context path, servlet path, trailing slash, URL encoding, HTTP method và nhiều filter chain.
6. Kiểm chứng security chain cho Servlet/Reactive bằng test, bảo toàn CSRF/CORS/headers/session/firewall khi nâng cấp.

## 2. Hai cấp khớp request trong Spring Security

### 2.1. Cấp 1 — Chọn security filter chain

Ở **Servlet**, Spring Security sử dụng `FilterChainProxy` chứa một hoặc nhiều `SecurityFilterChain`. Mỗi chain có một matcher xác định **toàn bộ chuỗi filter đó** có áp dụng cho request không.

Ở **Reactive**, cơ chế tương ứng dùng `WebFilterChainProxy`, `SecurityWebFilterChain` và `ServerWebExchangeMatcher`.

Một request được xử lý bởi **chain đầu tiên có matcher phù hợp** theo thứ tự được cấu hình. Nếu không có chain nào phù hợp thì các lớp phòng vệ của Spring Security **không được áp dụng** cho request đó. Đây là lý do cần fallback chain và kiểm thử URL nằm ngoài từng prefix.

### 2.2. Cấp 2 — Chọn quy tắc authorization *bên trong chain*

Trong một chain đã chọn, `authorizeHttpRequests` của Servlet hoặc `authorizeExchange` của Reactive tiếp tục chọn quy tắc phân quyền:

```text
GET /api/admin/report
   |
   v
Chain 1 có securityMatcher("/api/**") ? ---- không ---> Chain 2 / ...
   |
  có
   v
authorizeHttpRequests:
    /api/public/** -> permitAll
    /api/admin/**  -> hasRole("ADMIN")      <- trúng quy tắc này
    anyRequest()   -> authenticated
   |
   v
Kiểm tra quyền / 401 / 403 / cho phép
```

| Thành phần | Servlet | Reactive | Ý nghĩa |
| --- | --- | --- | --- |
| Chọn **chain** | `http.securityMatcher(...)` hoặc `http.securityMatchers(...)` | `http.securityMatcher(ServerWebExchangeMatcher)` | Request có đi qua chain này không? |
| Chọn **rule** | `authorizeHttpRequests(a -> a.requestMatchers(...))` | `authorizeExchange(a -> a.pathMatchers(...))` | Sau khi vào chain, người dùng được phép làm gì? |
| Phần còn lại | `anyRequest()` | `anyExchange()` | Mọi request **còn lại trong chain đó** |
| Sắp xếp các chain | `@Order`/`Ordered` | `@Order`/`Ordered` | Chain nào được xét trước? |
| Sắp xếp rule | Theo thứ tự khai báo | Theo thứ tự khai báo | Matcher đầu tiên phù hợp quyết định rule |

**Phân biệt quan trọng:** `anyRequest().authenticated()` **không** có nghĩa là toàn bộ ứng dụng được bảo vệ nếu chain chỉ match `/api/**`. Ngược lại, `permitAll()` chỉ bỏ qua **quyết định phân quyền** cho URL đó; request vẫn đi qua các filter khác trong chain, chẳng hạn xử lý CSRF và ghi security headers.

## 3. Ma trận thay đổi qua các dòng Spring Security

| Dòng Security | Cú pháp/matcher thường gặp ở Servlet | Cần lưu ý khi nâng cấp |
| --- | --- | --- |
| **5.7 trở về trước** | `authorizeRequests().antMatchers(...)`, `mvcMatchers(...)`, `regexMatchers(...)`; các API kế thừa như `WebSecurityConfigurerAdapter` | Các bài viết cũ có thể không còn biên dịch trong thế hệ mới; `antMatchers` không phải cùng ngữ nghĩa với MVC matcher |
| **5.8** | Thêm/khuyến nghị `requestMatchers(...)` cho authorization và `securityMatchers(...)` cho chọn chain; các method chuyên biệt cũ bị deprecated | Cách chọn matcher cho string thường ưu tiên `MvcRequestMatcher` khi có Spring MVC, nếu không dùng `AntPathRequestMatcher` |
| **6.0–6.4** | Bean `SecurityFilterChain`, `authorizeHttpRequests` và Lambda DSL; `requestMatchers(...)`/`securityMatcher(...)` | `antMatchers`/`mvcMatchers` cũ trên DSL đã bị loại bỏ; kiểm tra namespace Jakarta và cách mapping của Spring MVC |
| **6.5** | Duy trì nhánh 6.x, cho phép chuẩn bị với `PathPatternRequestMatcher`; có migration guide lên 7 | Có thể đăng ký `PathPatternRequestMatcherBuilderFactoryBean` để thử cách chọn matcher mới trước khi chuyển major |
| **7.x** | `PathPatternRequestMatcher` là cơ chế mặc định cho string URL trong Java DSL; Lambda DSL bắt buộc | `AntPathRequestMatcher` và `MvcRequestMatcher` không còn được hỗ trợ; pattern phải bắt đầu từ `/` và là đường dẫn tuyệt đối **trong ứng dụng**, bỏ context root |

Trong 5.8/6.x, nói “`requestMatchers("/api/**")` luôn dùng Ant” hoặc “luôn dùng MVC” là sai: cách chọn phụ thuộc cơ chế đăng ký matcher và Spring MVC trên classpath. Sang 7.x, Java DSL dựa trên `PathPatternRequestMatcher`. Để đối chiếu một project cụ thể, hãy kiểm tra **Spring Security dependency thực sự được resolve**, phiên bản MVC/WebFlux, servlet mapping và custom `RequestMatcher`.

Một ví dụ di chuyển từ Spring Security 5.x:

```java
// LEGACY ONLY: minh họa mã dùng trong Spring Security 5.x cũ.
http
    .authorizeRequests()
        .antMatchers("/public/**").permitAll()
        .antMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated();
```

Lambda DSL cho các dòng mới:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Hai đoạn có cùng **ý định phân quyền**, nhưng chưa đủ để khẳng định mọi URL biên được match y như nhau. Cần xem cách parser hiểu URL, các path liên quan servlet context và test cả trường hợp có dấu slash hoặc encoding bất thường.

## 4. Pattern có nghĩa gì? Ant, MVC và PathPattern không hoàn toàn tương đương

### 4.1. Ba cơ chế từng gặp trong Servlet

- **`AntPathRequestMatcher`:** dùng mô hình khớp đường dẫn dạng Ant, từng phổ biến trong tài liệu Security 5.x và trong một số ứng dụng Security 6.x.
- **`MvcRequestMatcher`:** tích hợp với Spring MVC để sử dụng logic mapping tương ứng với controller; cần `HandlerMappingIntrospector` và ngữ cảnh MVC phù hợp.
- **`PathPatternRequestMatcher`:** dùng mô hình `PathPattern` của Spring Framework, là hướng mặc định của Spring Security 7. Dữ liệu pattern được parse trước, xử lý URL theo cấu trúc segment và có cơ chế nhất quán hơn với Spring MVC hiện đại.

Spring Security còn hỗ trợ matcher theo điều kiện khác như `RegexRequestMatcher`, `DispatcherTypeRequestMatcher`, hoặc `RequestMatcher` do ứng dụng tự viết. Không phải matcher nào cũng là “khớp chuỗi path”.

### 4.2. Những pattern thông dụng khi dùng `PathPattern`

| Pattern | Ví dụ thường match | Ghi chú |
| --- | --- | --- |
| `/admin` | `/admin` | URL chính xác; không tự giả định khớp `/admin/` |
| `/admin/**` | `/admin`, `/admin/report`, `/admin/a/b` | Mở rộng tới nhiều segment con, gồm cả prefix |
| `/files/*` | `/files/a` | Một segment; không khớp `/files/a/b` |
| `/files/*.pdf` | `/files/report.pdf` | Glob bên trong một segment |
| `/orders/{id}` | `/orders/123` | Biến đường dẫn có thể được lấy từ match result |
| `/orders/{id:[0-9]+}` | `/orders/123` | Giới hạn pattern của một segment; không match `/orders/abc` |
| `/files/{*rest}` | `/files/a/b` | Bắt phần đường dẫn còn lại khi parser hỗ trợ mẫu này |
| `/a/**/b` | **Không hợp lệ** với `PathPattern` | `**` phải ở cuối pattern |

Một điểm dễ bị bỏ sót khi di chuyển Ant → PathPattern là pattern kiểu `/**/admin` hoặc `/api/**/status`. Ant trước đây có thể chấp nhận dạng này, nhưng `PathPatternParser` không cho phép `**` ở giữa đường dẫn. Phải sửa cấu trúc route/pattern có chủ đích; không thay thế bằng `/**` vì matcher quá rộng có thể cấp quyền nhầm.

Quy tắc khớp **case**, **trailing slash**, **encoding** và **URL path parameters** phải được thử trên đúng parser/container đang dùng. Không suy luận từ việc controller có `@RequestMapping` rồi cho rằng một `RequestMatcher` bất kỳ luôn chia sẻ cùng parser hoặc cùng normalization.

### 4.3. Không tự thêm context path vào matcher

Giả sử ứng dụng chạy tại:

```text
Public URL:      https://example.com/app/admin/report
Context path:    /app
Servlet path:    (mặc định, ánh xạ tại /)
Controller path: /admin/report
```

Trong Spring Security 7, pattern trên Servlet nên là `/admin/**`, **không** phải `/app/admin/**`. `PathPatternRequestMatcher` so sánh đường dẫn **đã bỏ context path**.

Nếu DispatcherServlet được map tại `/mvc/*` thì request public có thể là:

```text
Public URL:      /app/mvc/admin/report
Context path:    /app
Servlet path:    /mvc
Controller path: /admin/report
Matcher path:    /mvc/admin/**   (bỏ /app, gồm servlet path /mvc)
```

Với nhiều servlet hoặc một servlet mapping khác mặc định, có thể dùng `PathPatternRequestMatcher.Builder.basePath(...)` để không lặp lại servlet prefix. **Base path ở đây là servlet path/chung của các matcher, không phải context root.**

## 5. Servlet Spring Security 7: cấu hình filter chain và authorization rõ ràng

Ví dụ sau phù hợp với ứng dụng **Spring MVC/Servlet** thuộc thế hệ Security 7.x. API dùng HTTP Basic trên `/api/**`; website dùng form login trên các URL còn lại. Quy tắc GET public và admin được khai báo bằng matcher có kiểu tường minh:

```java
package com.example.protection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class ServletMatcherSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher(
                PathPatternRequestMatcher.pathPattern("/api/**")
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    PathPatternRequestMatcher.pathPattern(
                        HttpMethod.GET, "/api/public/**"
                    )
                ).permitAll()
                .requestMatchers(
                    PathPatternRequestMatcher.pathPattern("/api/admin/**")
                ).hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích kết quả:**

1. `@Order(1)` đảm bảo API chain được xét trước; `/api/admin/report` thuộc API chain nên yêu cầu ADMIN.
2. Rule GET public chỉ cho phép **GET** dưới `/api/public/**`. POST cùng URL không đi vào rule đó, tiếp tục đến `anyRequest().authenticated()` và vẫn chịu kiểm tra CSRF nếu CSRF áp dụng.
3. `/admin/report` **không** có prefix `/api/**`, do đó thuộc fallback web chain và cũng yêu cầu ADMIN.
4. Web chain không có `securityMatcher` nên mặc định xét mọi URL còn lại; giúp tránh khoảng trống ngoài `/api/**`.
5. `csrf(Customizer.withDefaults())` không phải là một quy tắc authorization. Với browser dùng session/cookie, POST/PUT/PATCH/DELETE cần token hợp lệ theo CSRF matcher.
6. Security headers mặc định của Spring Security tiếp tục được xử lý trên các request đi qua chain; nếu ứng dụng cần CSP/CORS/HSTS tùy chỉnh, bổ sung trong **chain liên quan**.

**Điều kiện chạy thực tế:** cần nguồn xác thực có user/roles, endpoint tương ứng, test dependency và cấu hình TLS/proxy phù hợp. HTTP Basic trong ví dụ chỉ để minh họa phân chain; nếu browser dùng credentials tự gửi, cần đánh giá CSRF và chính sách session theo threat model.

### 5.1. Trường hợp URL có servlet prefix: `Builder.basePath`

Spring Security 7 có builder cho servlet path:

```java
import static org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher.withDefaults;

PathPatternRequestMatcher.Builder mvc =
    withDefaults().basePath("/mvc");

http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(mvc.matcher("/public/**")).permitAll()
    .requestMatchers(mvc.matcher("/admin/**")).hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Đoạn trên minh họa phần **bên trong** phương thức tạo `SecurityFilterChain`; dòng import phải đặt ở đầu file Java. Giả sử ứng dụng có context path `/app`, DispatcherServlet ở `/mvc/*` và handler `/admin/report`, builder sẽ tạo matcher cho `/mvc/admin/**`. Không thêm `/app` vào `basePath`. Nếu có custom `PathPatternParser` hoặc nhiều DispatcherServlet, hãy dùng parser phù hợp với MVC và kiểm tra tất cả các servlet mapping.

### 5.2. Không nhất thiết phải chỉ dùng matcher tạo từ chuỗi

Với điều kiện đặc biệt, có thể truyền một `RequestMatcher` tự tạo vào `requestMatchers(RequestMatcher...)`:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher isReportExport = (HttpServletRequest request) ->
    "GET".equals(request.getMethod())
    && "/reports/export".equals(request.getServletPath());

http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(isReportExport).hasRole("EXPORTER")
    .anyRequest().authenticated()
);
```

Đây là ví dụ đơn giản cho Servlet mặc định; với context/servlet path đặc biệt, forward, pathInfo hoặc URL normalization, phải kiểm thử matcher trên **đường đi thực**. Không dùng `getRequestURI()` rồi so sánh với `/reports/export` mà quên context path. Nếu cần điều kiện query parameter, custom matcher phải xử lý tham số rõ ràng; path matcher thông thường không kiểm tra `?key=value`.

## 6. Chuẩn bị Spring Security 6.5 trước khi lên 7.x

Với dự án đang dùng Security **6.5**, migration guide cung cấp cách thử cơ chế tạo matcher mới trước khi nâng major. Đăng ký factory bean được tài liệu hướng dẫn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.PathPatternRequestMatcherBuilderFactoryBean;

@Configuration
class PrepareForSecurity7 {

    @Bean
    PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
        return new PathPatternRequestMatcherBuilderFactoryBean();
    }
}
```

Việc khai báo này hướng DSL sử dụng `PathPatternRequestMatcher` cho các matcher nó tự tạo. Khi đã bật:

1. Chạy lại toàn bộ test authorization và request URL thực tế.
2. Tìm các pattern Ant không hợp lệ theo `PathPattern`, ví dụ `/api/**/admin`.
3. Xác nhận mọi pattern dùng `/` ở đầu và bỏ context path.
4. Kiểm tra servlet path, nhiều DispatcherServlet, parser MVC tùy chỉnh và static resource URL.
5. Nếu bạn trực tiếp khởi tạo matcher/đưa matcher vào một setter, phải chủ động thay đối tượng đó; factory bean không thể biến mọi matcher tự tạo thành matcher mới.

Không tự áp dụng đoạn factory trên Security 5.x chưa hỗ trợ API hoặc một dự án chưa xác định phiên bản. Đây là **bước chuẩn bị có kiểm thử** khi còn ở dòng 6.5, không phải thay đổi chỉ để xóa cảnh báo IDE.

### 6.1. Chuyển code trực tiếp dùng Ant/MVC matcher

Trước đây có thể thấy:

```java
// LEGACY ONLY - không dùng khi build với Spring Security 7.
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

RequestMatcher oldMatcher =
    new AntPathRequestMatcher("/reports/**", "GET");
```

Trong Security 7, sử dụng `PathPatternRequestMatcher` khi phù hợp:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher reportReads =
    PathPatternRequestMatcher.pathPattern(HttpMethod.GET, "/reports/**");
```

Hãy rà soát **tất cả điểm dùng matcher**, không chỉ `authorizeHttpRequests`: còn có `securityMatcher`, CSRF ignoring matcher, custom filter `setRequestMatcher`, request cache, login/logout matcher, static resources và các thành phần HTTP security khác.

### 6.2. Đừng nhầm thay cú pháp với giữ nguyên ngữ nghĩa

Một đoạn `antMatchers("/admin/**")` không thể được coi là đã “migrate xong” chỉ vì đổi tên thành `requestMatchers("/admin/**")`. Kết quả phụ thuộc:

- Có Spring MVC trên classpath không?
- MVC đang dùng `PathPatternParser` hay một matcher tùy chỉnh?
- Có custom servlet path/context path không?
- Proxy/container có sửa URL trước khi request vào Security không?
- Pattern có dùng cú pháp Ant mà PathPattern không chấp nhận không?
- Rule xuất hiện trước hay sau `permitAll` quá rộng?

Tốt nhất giữ một tập request minh họa **các URL hợp lệ và các URL phải bị từ chối** để so sánh trước/sau khi nâng.

## 7. HTTP method, dispatcher type và thứ tự rule

### 7.1. Match theo HTTP method

Khi chính sách phân quyền phụ thuộc method, khai báo tường minh:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/orders/**").hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.POST, "/orders/**").hasAuthority("ORDER_WRITE")
    .requestMatchers(HttpMethod.DELETE, "/orders/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Kiểu trên là overload string matcher trong Lambda DSL (với import `org.springframework.http.HttpMethod`). Đối với Spring Security 7, string matcher mặc định dùng PathPattern; nếu muốn cố định kiểu matcher, truyền `PathPatternRequestMatcher.pathPattern(HttpMethod.POST, "/orders/**")` như ở mục 5.

**Tại sao `anyRequest().denyAll()` hữu ích?** Vì những method chưa được liệt kê sẽ bị từ chối ở bước authorization. Còn CSRF tiếp tục là lớp riêng kiểm soát request thay đổi trạng thái. Nếu ứng dụng trả 405 vì handler không hỗ trợ method, đó cũng không thay thế chính sách phân quyền với method không được phép.

### 7.2. Thứ tự có ý nghĩa

**Cấu hình sai:**

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Rule `/**` rộng xuất hiện trước sẽ khiến rule `/admin/**` không được áp dụng như dự định. Spring Security xử lý các rule authorization theo **thứ tự khai báo**; không tự sắp xếp để ưu tiên pattern cụ thể như khi framework chọn controller mapping.

**Cấu hình đúng hướng:**

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
```

Với nhiều `SecurityFilterChain`, `@Order` cũng rất quan trọng: một chain bắt `/**` ở thứ tự 1 sẽ làm chain `/api/**` ở thứ tự 2 không bao giờ được chọn.

### 7.3. Forward và error dispatch

Trên Servlet, `AuthorizationFilter` có thể xét cả các dispatcher type như `REQUEST`, `FORWARD`, `ERROR`. Ví dụ, controller trả về trang Thymeleaf qua forward, hoặc framework dispatch sang `/error`; một rule quá chặt có thể gây 403 khi render.

Chỉ khi nghiệp vụ cho phép, có thể dùng:

```java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(authorize -> authorize
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD, DispatcherType.ERROR
    ).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

**Không biến mọi dispatcher type thành `permitAll` theo quán tính.** Thử luồng forward/error có dữ liệu nhạy cảm và xác định controller, view, exception handler đang được gọi. Thêm rule `/error` phù hợp cũng có thể giải quyết một số trường hợp.

## 8. Reactive/WebFlux: `ServerWebExchangeMatcher` không phải Servlet `RequestMatcher`

WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchangeMatcher`. Cú pháp Lambda DSL tương tự Servlet nhưng API khác:

```java
package com.example.protection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
class ReactiveMatcherSecurity {

    @Bean
    @Order(1)
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .authorizeExchange(authorize -> authorize
                .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    SecurityWebFilterChain fallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Điểm cần nhớ:

- Reactive không dùng `org.springframework.security.web.util.matcher.RequestMatcher` Servlet.
- `ServerWebExchangeMatchers.pathMatchers(...)` tạo matcher cho Reactive; cần giới hạn method bằng overload phù hợp khi cần.
- `SecurityWebFilterChain` được chọn theo thứ tự; các rule `pathMatchers(...)` được xét bên trong chain.
- Mọi route không match chain API phải được fallback xử lý; nếu không, những request đó không được Spring Security bảo vệ.
- Dù có cùng tên “CSRF”, WebFlux dùng `CsrfWebFilter` và `WebSession`, không dùng `HttpSessionCsrfTokenRepository` của Servlet.

Khi nâng Spring Security 6.x → 7.x, sự thay đổi `AntPathRequestMatcher`/`MvcRequestMatcher` là **câu chuyện của Servlet**. Không suy ra rằng WebFlux cũng cần import `PathPatternRequestMatcher` để thay `pathMatchers`. Hãy đối chiếu [Reactive request authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) và API `ServerWebExchangeMatcher` của phiên bản đang dùng.

## 9. Servlet path, context path, proxy và URL normalization

### 9.1. Không nhầm ba loại path

| Khái niệm | Ví dụ | Được xử lý ở đâu? |
| --- | --- | --- |
| Context path | `/app` | Container/Boot quản lý phần gốc ứng dụng |
| Servlet path | `/mvc` | DispatcherServlet mapping, có thể khác mặc định |
| Controller path | `/admin/report` | `@RequestMapping`/`@GetMapping` |
| URL phía người dùng | `/app/mvc/admin/report` | Có thể đã qua proxy/rewrite |
| Security 7 PathPattern matcher | `/mvc/admin/report` | Thường **bỏ context path**, giữ servlet path |

Nếu proxy map public `/portal/api/orders` tới backend `/api/orders`, Spring Security thường nhìn thấy URL backend sau rewrite. Việc kiểm tra một URL trong MockMvc với path khác thực tế có thể bỏ sót sai lệch. Hãy ghi nhận **cả URL public lẫn URI backend** và gửi request qua đường production staging để xác nhận.

### 9.2. Một số URL “lạ” phải nằm trong test suite

- `/admin` và `/admin/`: trailing slash có thể thay đổi kết quả so với mapper cũ.
- `/Admin` và `/admin`: case sensitivity cần được xác minh.
- `/admin//report`: duplicate slash có thể bị proxy hoặc firewall từ chối/chuẩn hóa.
- `/admin;%20x/report` hoặc path parameters/matrix variables: xử lý tùy parser, firewall và servlet container.
- `/admin/%2e%2e/public`: encoded traversal phải bị từ chối hoặc xử lý chặt chẽ.
- `/files/a%2Fb`: encoded slash có thể bị firewall/container xử lý khác các đường dẫn thông thường.
- `/api/orders?debug=true`: query parameter **không phải một phần path pattern**.
- Các header `X-Forwarded-Prefix`, `Forwarded`, `X-Forwarded-Proto`: chỉ tin nguồn proxy đã xác thực và có kiểm soát.

Không kết luận “HTTP 404 chứng minh URL an toàn”. Nếu một request không vào controller do mapping khác, vẫn phải xác minh request đó đã qua security chain nào, đặc biệt khi có static handler, fallback controller, error handler và rewrite.

### 9.3. HTTP firewall bảo vệ ranh giới giữa matcher và handler

Trong Servlet, `StrictHttpFirewall` của Spring Security mặc định từ chối nhiều dạng URL bất thường: URL không normalized, dấu chấm phẩy, encoded slash, backslash, null bytes và một số HTTP method nguy hiểm. Khi request bị chặn trước authorization, có thể phát sinh `RequestRejectedException`; HTTP status cuối cùng phụ thuộc cách container/ứng dụng xử lý.

**Không sửa lỗi matcher bằng cách nới toàn bộ firewall**:

```java
// CẤU HÌNH CẦN ĐÁNH GIÁ RỦI RO; không dùng mặc định:
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true);
```

Ví dụ trên chỉ minh họa API có thể thấy trong hệ thống legacy cần matrix variables. Cho phép semicolon có thể làm đường dẫn được các thành phần hiểu khác nhau. Chỉ thực hiện sau khi phân tích rõ cách proxy, container, MVC và Security xử lý URL, kèm test chống authorization bypass.

**Dấu hiệu điều tra:** Nếu test request `/admin/a%2Fb` trả 400, đừng vội quy cho `hasRole`; có thể request bị firewall từ chối trước khi vào rule. Nếu request lại trả 200 qua proxy, cần xem proxy đã giải mã/normalize path trước Security hay chưa.

## 10. Request matcher ảnh hưởng trực tiếp đến CSRF, CORS, headers và session

### 10.1. Matcher phân quyền không tự tắt CSRF

Với một endpoint public cho anonymous:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/feedback").permitAll()
    .anyRequest().authenticated()
);
```

`POST /feedback` **vẫn có thể bị CSRF chặn** nếu ứng dụng dùng cấu hình mặc định và không cung cấp token. `permitAll` chỉ bỏ qua yêu cầu quyền; đây là hành vi có chủ đích cho những form công khai.

Nếu một webhook không dùng cookie và có cơ chế xác minh chữ ký độc lập, bạn có thể định nghĩa ngoại lệ CSRF **hẹp**, ví dụ Security 7 Servlet:

```java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers(
        PathPatternRequestMatcher.pathPattern(
            HttpMethod.POST, "/webhooks/vendor"
        )
    )
);
```

Đoạn trên chỉ thay cách CSRF chọn request; **không** cấp quyền webhook, không xác thực chữ ký, không chống replay và không bảo đảm request đã qua đúng security chain. Không tự động dùng `csrf(csrf -> csrf.disable())` cho mọi API chỉ vì nâng phiên bản làm test POST thất bại.

### 10.2. CORS preflight cũng có path và method

Preflight dùng `OPTIONS`, `Origin` và `Access-Control-Request-Method`, thường không mang session cookie. Spring Security cần được tích hợp với nguồn policy CORS và cho phép preflight được đánh giá trước authentication. Khi thay matcher hoặc chia nhiều chain, kiểm tra CORS policy ở **đúng chain** và đúng URL backend.

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Không dùng `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` như một cách thay thế hoàn toàn cho CORS policy. CORS cần allowlist origin, method, header và credentials; authorization vẫn có nhiệm vụ độc lập.

### 10.3. Header security chỉ được ghi ở request đi qua chain

`X-Content-Type-Options: nosniff`, frame options, cache control và HSTS trên HTTPS được quản lý bởi header writers của Spring Security theo cấu hình hiện hành. CSP cần được khai báo riêng.

Nếu request bị Servlet `web.ignoring()` hoặc không match chain nào, các header do Spring Security viết có thể biến mất. Vì vậy, khi chuyển static paths từ `antMatchers("/assets/**").permitAll()` sang API mới, hãy giữ `permitAll()` nếu muốn request đi qua security filters, tránh đổi thành `web.ignoring()` chỉ vì một hướng dẫn cũ.

Khi deploy sau reverse proxy có TLS termination, kiểm tra HSTS trên **HTTPS public response**, không chỉ trên HTTP backend. Nếu một chain chỉ match `/api/**`, cấu hình CSP/HSTS của nó sẽ không tự áp dụng cho `/admin/**` thuộc fallback chain.

### 10.4. Session và logout phụ thuộc chain được chọn

Form login thường sử dụng session để giữ `SecurityContext`. Nếu login URL ở `/login` nhưng chain chỉ match `/api/**`, endpoint login được Spring Security tạo cho chain đó **có thể không xuất hiện ở URL mong đợi**. Tương tự với logout, remember-me, request cache và session strategy.

Nếu một API chain được cấu hình `SessionCreationPolicy.STATELESS` (Servlet) thì không có nghĩa web chain dùng form login cũng stateless; đó là quyết định áp dụng theo chain/thiết kế. Đảm bảo login/logout endpoint và cookie session đi qua đúng chain, đồng thời kiểm tra CSRF cho các request thay đổi trạng thái.

## 11. Kiểm thử Servlet: chứng minh authorization trên các URL biên

Ví dụ sau giả định ứng dụng đã có controller cho `/api/public/ping`, `/api/admin/report`, `/admin/report` và những route này trả 200 khi truy cập hợp lệ. Filter chain sử dụng cấu hình ở mục 5. Dùng `spring-security-test` và `MockMvc`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletMatcherRegressionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void adminPathsCannotBeReadByOrdinaryUser() throws Exception {
        mvc.perform(get("/api/admin/report").with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/report").with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessBothAdminRoutes() throws Exception {
        mvc.perform(get("/api/admin/report").with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin/report").with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk());
    }

    @Test
    void publicApiIsReadableWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk());
    }
}
```

**Lưu ý phiên bản Spring Boot:** import `@AutoConfigureMockMvc` ở ví dụ dành cho **Boot 4** (`org.springframework.boot.webmvc.test.autoconfigure`), cần `spring-boot-starter-webmvc-test` và `spring-boot-starter-security-test`. Ở Boot 3, annotation ở package `org.springframework.boot.test.autoconfigure.web.servlet`; kiểm tra lại starter tương ứng. Mã test là khung minh họa, cần thêm dependency/handler như mô tả; không có controller sẽ trả 404 dù authorization cho phép.

Để tránh test “pass” giả:

- Xác nhận Spring Security filters đã gắn với `MockMvc`, đặc biệt khi tạo `MockMvc` thủ công (dùng `springSecurity()`).
- Thử **cả** user thiếu quyền và user đúng quyền, vì mọi request 403 cũng có thể do ứng dụng lỗi toàn cục.
- Với URL `/admin/report/`, đừng mặc định luôn được handler map; ghi nhận cả security decision và handler outcome.
- Thử request có query, encoded slash, semicolon, duplicate slash qua integration environment thực; mock container không tái hiện hết cách proxy/Servlet container xử lý.
- Với method POST, phải cấp CSRF token hợp lệ hoặc phân biệt lỗi CSRF với lỗi authorization; GET tests hữu ích để cô lập matcher logic.

### 11.1. Bộ test CSRF riêng cho route thay đổi trạng thái

Giả sử controller `POST /api/orders` chấp nhận người dùng đã xác thực:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// Trong một @Test có MockMvc mvc:
mvc.perform(post("/api/orders").with(user("alice")))
    .andExpect(status().isForbidden());

// Token hợp lệ giúp request qua CSRF, nhưng kết quả cuối phụ thuộc
// controller, authentication và authorization của ứng dụng.
mvc.perform(post("/api/orders").with(user("alice")).with(csrf()))
    .andExpect(status().isOk());
```

Đối với ví dụ nếu controller trả 201/204, cập nhật expectation. Nếu API dùng bearer token và có ngoại lệ CSRF được đánh giá riêng thì kỳ vọng sẽ khác; ghi rõ **threat model** trong test.

## 12. Kiểm thử Reactive: bảo đảm matcher và filter chain hoạt động

Với WebFlux, dùng `WebTestClient` được bind vào Spring `ApplicationContext` và áp dụng `springSecurity()`. Ví dụ test cho route `/api/admin/report`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void adminRouteRequiresAdminRole() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("admin").roles("ADMIN"))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk();
}
```

Một cách tạo client trong integration test:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

Test trên giả định handler và quyền đã được định nghĩa. Nếu dùng client gọi server từ xa qua TCP, `mockUser()` không tự đăng nhập trên server đó; cần credential thật hoặc test application context. Với POST, dùng `SecurityMockServerConfigurers.csrf()` để tạo token hợp lệ.

### 12.1. Ma trận request tối thiểu cho mỗi stack

| Đầu vào | Mục tiêu | Kỳ vọng cần xác minh |
| --- | --- | --- |
| `GET /api/public/ping` không auth | Public matcher | Được phép vào handler |
| `GET /api/admin/report` với USER | Admin rule | Từ chối (thường 403) |
| `GET /api/admin/report` với ADMIN | Admin rule | Qua authorization |
| `GET /admin/report` với USER | Fallback chain | Không bị bỏ qua Security |
| `GET /unknown` không auth | Catch-all | 401/redirect hoặc deny theo chính sách |
| `GET /admin/` | Trailing slash | Trùng đúng rule và handler theo ý định |
| `GET /ADMIN/report` | Case sensitivity | Không vô tình được handler nhạy cảm phục vụ |
| `GET /api/admin/report?debug=true` | Query | Rule path không bị biến đổi vì query |
| `POST /api/orders` thiếu/đúng CSRF token | CSRF | Phân biệt 403 và request hợp lệ |
| `OPTIONS /api/orders` có `Origin` | CORS | Allowlist đúng, không dùng auth cookie làm điều kiện preflight |
| Encoded slash, semicolon, duplicate slash | Firewall/normalization | Không bỏ qua rule do URL bị hiểu khác nhau |
| Login/logout qua URL đã cấu hình | Session | Vẫn đi qua chain đúng sau migration |

**Đừng chỉ kiểm tra status 200/403.** Nếu request 403 vì CSRF dù rule admin bị mở, test admin không chứng minh authorization đúng. Nếu request 404 vì controller không match dù chain không bảo vệ, test cũng có thể che lấp lỗ hổng. Cần kiểm tra logs, selected chain, response headers, hành vi với user khác quyền và server routing.

## 13. Chẩn đoán các lỗi thường gặp khi đổi matcher

### Lỗi A — Đã có `hasRole("ADMIN")` nhưng URL admin lọt

**Khả năng:** `securityMatcher` loại URL khỏi chain, một chain ưu tiên cao hơn áp rule rộng, hoặc `permitAll` xuất hiện trước rule admin. Kiểm tra danh sách `SecurityFilterChain`/`SecurityWebFilterChain`, `@Order` và matcher của mỗi chain. Thêm fallback bao phủ các route còn lại.

### Lỗi B — Mã `new AntPathRequestMatcher(...)` không biên dịch với Security 7

**Khả năng:** lớp/method matcher cũ bị loại bỏ ở thế hệ 7. Dùng `PathPatternRequestMatcher` cho Servlet khi phù hợp; sửa pattern không hợp lệ theo PathPattern. Đối với Reactive, dùng `ServerWebExchangeMatcher`, không dùng Servlet matcher.

### Lỗi C — Pattern `/api/**/admin` trước chạy, nay lỗi startup

**Khả năng:** `PathPatternParser` không cho phép `**` ở giữa pattern. Thiết kế lại route hoặc dùng matcher chuyên biệt nếu thật cần, rồi test ngăn bypass. Không thay bằng `/**` và `permitAll`.

### Lỗi D — `/app/admin/**` không match khi triển khai dưới context path `/app`

**Khả năng:** matcher Security 7 mong path đã bỏ context root. Sửa matcher thành `/admin/**` (nếu servlet ở root) hoặc gồm servlet prefix đúng (nếu servlet nằm dưới `/mvc`), rồi xác minh request public và backend.

### Lỗi E — `/admin` và `/admin/` có kết quả khác

**Khả năng:** trailing slash matching/handler mapping thay đổi hoặc parser khác giữa Security và MVC. Xác định URL canonical, redirect nếu cần và test cả hai URL. Không mặc nhiên nới rule trước khi hiểu handler có còn map hai URL không.

### Lỗi F — POST trả 403 ngay cả khi URL được `permitAll()`

**Khả năng:** CSRF vẫn bật cho unsafe method; hoặc CORS preflight không được xử lý đúng. Kiểm tra `CsrfFilter`/`CsrfWebFilter`, CSRF token repository, origin và matcher riêng của CSRF. `permitAll()` không phải vô hiệu hóa CSRF.

### Lỗi G — Static assets không có CSP/HSTS

**Khả năng:** `web.ignoring()`, URL không match chain hoặc assets được proxy/CDN phục vụ ngoài Spring. Nếu muốn giữ security headers do Spring Security ghi, dùng `permitAll` trong chain thích hợp và cấu hình CSP/HSTS phù hợp với HTTPS.

### Lỗi H — Cùng URL hoạt động khác giữa local và staging

**Khả năng:** context path/servlet mapping khác, proxy rewrite, encoded slash, header forward hoặc container normalization khác. Ghi log request path ở các tầng (không lộ credential), so sánh matchers và kiểm thử trên HTTPS public.

### Lỗi I — RequestRejectedException khi dùng matrix variables

**Khả năng:** `StrictHttpFirewall` từ chối dấu chấm phẩy hoặc URL không normalized. Kiểm tra xem ứng dụng có thực sự cần matrix variables và container/parser xử lý nhất quán không; chỉ nới firewall sau đánh giá rủi ro và test tấn công với URL biến thể.

## 14. Quy trình nâng cấp matcher an toàn

1. **Chốt baseline phiên bản:** đọc `spring-security-web`, `-config`, `spring-webmvc`/`spring-webflux` được resolve từ dependency graph. Chọn Boot/Security tương thích, tránh ghép nhiều major.
2. **Liệt kê matcher đang hoạt động:** `securityMatcher`, `requestMatchers`, legacy `antMatchers`/`mvcMatchers`, `WebSecurityCustomizer.ignoring()`, matcher CSRF, login/logout, custom filters và matchers tự viết.
3. **Vẽ sơ đồ chain:** thứ tự `@Order`, URL mà mỗi chain nhận và fallback chain. Đánh dấu tất cả URL nhạy cảm (admin, billing, settings, actuator, login/logout).
4. **Đối chiếu cách parser hiểu path:** context path, servlet path, MVC parser, trailing slash, wildcard, encoded segment, query string, proxy rewrite, dispatcher type.
5. **Nếu ở Security 6.5:** thử `PathPatternRequestMatcherBuilderFactoryBean` theo migration guide, sửa pattern legacy và test trước khi nâng lên 7.x.
6. **Chuyển sang Lambda DSL và matcher mới:** dùng `PathPatternRequestMatcher` trong Servlet Security 7 khi cần tường minh; WebFlux giữ `ServerWebExchangeMatcher` tương ứng.
7. **Giữ các phòng vệ đi kèm:** CSRF cho request browser dùng cookie, CORS policy cho preflight, CSP/headers/HSTS đúng từng chain, HTTP firewall và session/logout.
8. **Chạy kiểm thử hai chiều:** URL hợp lệ được phép theo đúng quyền **và** URL nhạy cảm bị chặn; thêm URL biên/encoding, method/dispatcher, request qua proxy.
9. **Kiểm tra production response:** security headers và request path thực tế đi qua CDN/proxy; không dựa duy nhất vào MockMvc/WebTestClient.
10. **Gỡ bỏ API đã obsolete:** sau khi kiểm chứng hành vi, xóa legacy matcher/config để tránh dự án lẫn nhiều cơ chế khó dự đoán.

### Mẫu ghi nhận quyết định matcher cho một endpoint

| Trường | Ví dụ |
| --- | --- |
| Endpoint nhạy cảm | `GET /admin/report` |
| URL public | `https://example.com/app/mvc/admin/report` |
| Context/servlet path | `/app` / `/mvc` |
| Chain matcher | `/mvc/**` |
| Authorization matcher | `/mvc/admin/**` |
| Quyền | `ROLE_ADMIN` |
| Nguyên nhân cho phép/từ chối | Authorization, CSRF, firewall, routing hay proxy |
| Test bắt buộc | USER → 403; ADMIN → handler; trailing slash/encoded URL không bypass |

## 15. Bài tập thực hành

**Bài 1 — Tìm lỗ hổng do thiếu fallback.** Một ứng dụng chỉ khai báo:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated());
    return http.build();
}
```

Ứng dụng còn có endpoint `/admin/reports`. Giải thích vì sao `anyRequest().authenticated()` không bảo vệ endpoint đó. Thêm fallback chain yêu cầu ADMIN cho `/admin/**` và authentication cho các URL còn lại; viết một test xác nhận user thường bị 403.

**Bài 2 — Di chuyển wildcard.** Một ứng dụng Security 5.x dùng `antMatchers("/documents/**/download")` và `antMatchers("/admin/**")`. Hãy xác định pattern nào không hợp lệ với `PathPattern`, đề xuất route/matcher thay thế và viết test ít nhất ba URL hợp lệ cùng ba URL cố tình gây nhầm.

**Bài 3 — Context path/servlet path.** Ứng dụng chạy tại `/app`, DispatcherServlet ở `/mvc/*`, endpoint là `/admin/list`. Tạo matcher `PathPatternRequestMatcher.withDefaults().basePath("/mvc").matcher("/admin/**")`; giải thích vì sao không thêm `/app` vào pattern và kiểm thử bằng request public qua proxy.

**Bài 4 — CSRF và CORS sau migration.** API có `POST /api/orders` được bảo vệ bằng cookie session. Nhóm chuyển matcher authorization sang `permitAll` và mong POST không cần CSRF nữa. Giải thích sai lầm, thiết lập bài test POST thiếu/đúng token và OPTIONS preflight cho origin hợp lệ/không hợp lệ.

**Bài 5 — Servlet và Reactive.** Viết hai ứng dụng độc lập với chính sách `/api/public/**` truy cập công khai, `/api/admin/**` cần ADMIN và còn lại cần xác thực. Dùng `PathPatternRequestMatcher`/`SecurityFilterChain` cho Servlet, `ServerWebExchangeMatchers.pathMatchers`/`SecurityWebFilterChain` cho Reactive. Kiểm thử bằng MockMvc/WebTestClient và liệt kê những lớp HTTP protection còn cần thiết.

## 16. Checklist trước khi merge

- [ ] Xác định được phiên bản thực sự của Spring Security, Framework, Boot và web stack.
- [ ] Biết DSL/RequestMatcher thực tế thuộc 5.x, 6.x hay 7.x; không dùng `AntPathRequestMatcher`/`MvcRequestMatcher` trên Security 7.
- [ ] Không còn pattern `**` giữa đường dẫn nếu chuyển sang `PathPattern`.
- [ ] Mọi pattern Servlet Security 7 bắt đầu từ `/` và bỏ context root; servlet path được tính đúng.
- [ ] Mọi chain có phạm vi rõ ràng, `@Order` đúng, fallback bảo vệ URL còn lại.
- [ ] Các rule authorization theo đúng thứ tự từ cụ thể đến tổng quát; không có `permitAll` quá rộng che rule nhạy cảm.
- [ ] Đã thử trailing slash, case, query string, encoded path, double slash, servlet mapping và proxy rewrite.
- [ ] Đã kiểm tra dispatcher type, HTTP method và URL của login/logout.
- [ ] CSRF/CORS/headers/CSP/HSTS/firewall/session giữ nguyên hiệu lực theo đúng chain.
- [ ] MockMvc/WebTestClient test cả người có quyền, thiếu quyền và request không xác thực.
- [ ] Đã kiểm chứng response/path thực tế qua proxy/container thay vì dựa vào kết quả mock duy nhất.

## Nguồn tham khảo chính thức

1. [Spring Security 6.5: Preparing for Spring Security 7 — Web Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html) — chuyển sang `PathPatternRequestMatcher`, dùng factory bean và quy tắc URI tuyệt đối bỏ context root.
2. [Spring Security 6.5: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — `securityMatcher`/`requestMatchers` và lựa chọn `MvcRequestMatcher`/`AntPathRequestMatcher` trong thế hệ 6.
3. [Spring Security 7.2: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/7.2/servlet/authorization/authorize-http-requests.html) — `PathPatternRequestMatcher`, regex, dispatcher type, custom matchers và authorization.
4. [Spring Security 7.2: Java Configuration](https://docs.spring.io/spring-security/reference/7.2/servlet/configuration/java.html) — nhiều `SecurityFilterChain`, `@Order` và phạm vi chain.
5. [PathPatternRequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html) và [PathPatternRequestMatcher.Builder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html) — path, context root, `basePath` và HTTP method.
6. [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — `PathPattern`, wildcard, URI variables và khác biệt với `AntPathMatcher`.
7. [Spring Security: HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html) — normalized paths, StrictHttpFirewall và vấn đề URL encoding/matrix variables.
8. [Spring Security: Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — `ServerWebExchangeMatcher` và `pathMatchers`.
9. [Spring Security: Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html), [Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) — tác động của matcher đến các lớp phòng vệ HTTP.

**Câu hỏi tự đánh giá:** Vì sao `securityMatcher("/api/**")` không bảo vệ `/admin/**` dù bên trong có `anyRequest().authenticated()`? Vì sao `/api/**/download` có thể cần viết lại khi lên Security 7? Context path `/app` có thuộc `PathPatternRequestMatcher` không? CORS preflight và CSRF có bị bỏ qua chỉ vì một URL dùng `permitAll()` không?
