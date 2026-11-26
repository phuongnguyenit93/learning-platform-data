# RequestMatcher, context path và servlet path trong ca kiểm thử

## 1. Vì sao cùng một URL có thể khớp matcher khác nhau?

Một endpoint Spring MVC có thể chạy ở nhiều môi trường triển khai:

- Ứng dụng được deploy ở root context: `https://example.test/api/orders`.
- Ứng dụng được deploy dưới context path `/shop`: `https://example.test/shop/api/orders`.
- `DispatcherServlet` được ánh xạ vào `/mvc/*`: request tới `/shop/mvc/api/orders`.

Controller vẫn có thể khai báo cùng mapping `/api/orders`, nhưng cấu trúc request Servlet nhìn thấy có thể khác nhau. Nếu cấu hình Spring Security dùng sai phần đường dẫn hoặc test dựng request không phản ánh cách servlet được ánh xạ, matcher có thể không khớp, hoặc khớp nhầm endpoint.

Trong module **SPRING_SECURITY_TESTING**, người học dùng `spring-security-test` để kiểm chứng xác thực và phân quyền HTTP trên ứng dụng **Servlet** và **Reactive**. Bài này tập trung vào `RequestMatcher`, cấu trúc đường dẫn Servlet và cách dựng test đúng bằng `MockMvc`. Mục tiêu là xác nhận rằng test đang kiểm tra **đúng request mà ứng dụng thực tế nhận được**.

Sau bài học, bạn có thể:

- Phân biệt `requestURI`, `contextPath`, `servletPath`, `pathInfo` và query string.
- Hiểu context path thường không được đưa vào pattern phân quyền.
- Cấu hình matcher theo Spring MVC hoặc theo servlet path được ánh xạ.
- Phân biệt `securityMatcher` (chọn filter chain) với `requestMatchers` (chọn rule authorization).
- Dựng MockMvc request có context path/servlet path chính xác, đồng thời kiểm tra cả ca khớp và không khớp.
- Nhận biết lỗi do matcher, servlet mapping, filter chain, routing hoặc cấu hình test.

## 2. Cấu trúc đường dẫn trong HttpServletRequest

Một request Servlet có nhiều thành phần đường dẫn khác nhau. Xét URL:

```text
https://example.test/shop/mvc/api/orders/42?expand=items
```

Giả sử ứng dụng được deploy với context path `/shop` và `DispatcherServlet` được ánh xạ vào `/mvc/*`:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `requestURI` | `/shop/mvc/api/orders/42` | Đường dẫn request trong URI, không bao gồm query string |
| `contextPath` | `/shop` | Tiền tố xác định web application được deploy |
| `servletPath` | `/mvc` | Phần đường dẫn khớp servlet mapping |
| `pathInfo` | `/api/orders/42` | Phần còn lại sau servlet path với mapping dạng path |
| `queryString` | `expand=items` | Tham số query, không phải một phần của path matcher thông thường |

Với cấu hình phổ biến hơn, `DispatcherServlet` được ánh xạ vào `/`:

```text
https://example.test/shop/api/orders/42?expand=items

requestURI  = /shop/api/orders/42
contextPath = /shop
servletPath = /api/orders/42
pathInfo    = null
queryString = expand=items
```

Hai request có thể đi tới cùng controller mapping `/api/orders/{id}`, nhưng giá trị `servletPath` và `pathInfo` khác nhau. Vì vậy, không nên xem tất cả chuỗi đường dẫn là một khái niệm.

### Context path là tiền tố triển khai

`contextPath` xác định ứng dụng được triển khai ở đâu trong server. Nó có thể rỗng khi ứng dụng chạy ở root context, hoặc là `/shop`, `/portal` khi deploy dưới một tiền tố khác.

Thông thường, **không đưa context path vào pattern của Spring Security**. Với ứng dụng ở `/shop`, rule vẫn có thể là:

```java
.requestMatchers("/api/orders/**").authenticated()
```

Không viết `/shop/api/orders/**` chỉ vì môi trường hiện tại dùng context path `/shop`. Context path có thể thay đổi theo môi trường deploy; gắn nó vào matcher làm cấu hình dễ hỏng khi đổi môi trường.

### Servlet path là phần liên quan đến mapping của servlet

`servletPath` phụ thuộc cách servlet được ánh xạ:

- `DispatcherServlet` mapping `/`: phần path ứng dụng thường nằm trong `servletPath`.
- `DispatcherServlet` mapping `/mvc/*`: `servletPath` thường là `/mvc`, còn phần path sau đó nằm trong `pathInfo`.

Khi ứng dụng có servlet mapping khác mặc định, matcher cần được cấu hình để hiểu phần path mà Spring MVC xử lý. Nếu không, pattern có thể được so khớp trên sai phần đường dẫn.

## 3. Phân biệt filter-chain matcher và authorization matcher

Spring Security có hai cấp matcher:

| Cấp | API | Câu hỏi được trả lời |
| --- | --- | --- |
| Chọn filter chain | `HttpSecurity.securityMatcher(...)` | Request này đi qua `SecurityFilterChain` nào? |
| Chọn rule bên trong chain | `authorizeHttpRequests(...).requestMatchers(...)` | Trong chain đã chọn, request cần quyền gì? |

Ví dụ một ứng dụng tách API Bearer token và trang web session:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Trong ví dụ này, `securityMatcher("/api/**")` giới hạn chain đầu. `requestMatchers(HttpMethod.GET, "/api/orders/**")` chỉ là rule authorization khi request đã vào chain đó. Nếu API không khớp `securityMatcher`, request có thể rơi vào chain tiếp theo và nhận chính sách khác.

Với nhiều chain, cần kiểm thử cả hai việc: request chọn đúng chain, và matcher authorization bên trong chain khớp đúng method/path. Một test chỉ xác minh status cuối cùng đôi khi chưa đủ để xác định chain nào đã xử lý request.

## 4. RequestMatcher và cách chọn matcher

`RequestMatcher` là abstraction quyết định một `HttpServletRequest` có khớp điều kiện hay không. Điều kiện có thể dựa trên:

- HTTP method và path.
- Servlet path, path info hoặc pattern của Spring MVC.
- Header, dispatcher type hoặc điều kiện request khác.
- Tổ hợp nhiều điều kiện AND/OR/NOT.

Trong DSL:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Spring Security tạo matcher phù hợp theo phiên bản và môi trường ứng dụng. Với ứng dụng có Spring MVC, lựa chọn matcher có thể sử dụng semantics của MVC; khi không có MVC, cách diễn giải pattern có thể khác. Khi cần kiểm soát rõ servlet mapping hoặc muốn test matcher độc lập, có thể tạo matcher tường minh.

### Dùng matcher theo semantics Spring MVC

Trong các cấu hình dùng `MvcRequestMatcher`, tạo builder từ `HandlerMappingIntrospector`:

```java
@Configuration
class MvcOrderSecurityConfig {
    @Bean
    SecurityFilterChain mvcSecurity(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
            new MvcRequestMatcher.Builder(introspector);
        RequestMatcher orderRead = new AndRequestMatcher(
            mvc.pattern("/api/orders/**"),
            request -> HttpMethod.GET.matches(request.getMethod())
        );

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(orderRead)
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .build();
    }
}
```

`MvcRequestMatcher` sử dụng cách xử lý đường dẫn phù hợp với Spring MVC. Nếu `DispatcherServlet` được ánh xạ vào `/mvc/*`, cấu hình builder với servlet path:

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

RequestMatcher orderMatcher = mvc.pattern("/api/orders/**");
```

Pattern `/api/orders/**` là path của ứng dụng MVC sau servlet mapping; `/mvc` được cấu hình riêng qua builder. Không cộng thêm context path `/shop` vào pattern.

Lưu ý phiên bản: các API matcher và lựa chọn mặc định thay đổi theo các dòng Spring Security. Với phiên bản mới có `PathPatternRequestMatcher`, có thể dùng `basePath` để biểu diễn servlet mapping; dự án đang dùng `MvcRequestMatcher` có thể tiếp tục theo API tương thích của phiên bản đó. Hãy chọn API theo phiên bản thực tế và không trộn semantics của các matcher trong cùng một test mà không chủ ý.

### Dùng PathPatternRequestMatcher với base path

Ở các phiên bản cung cấp `PathPatternRequestMatcher`, có thể khai báo base path tương ứng servlet mapping:

```java
PathPatternRequestMatcher.Builder mvc =
    PathPatternRequestMatcher.withDefaults()
        .basePath("/mvc");

RequestMatcher orderMatcher =
    mvc.matcher("/api/orders/**");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(orderMatcher)
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll());
```

Ở đây `/mvc` là base path của servlet mapping; pattern truyền cho matcher là phần path của ứng dụng sau base path. Cách này hữu ích khi servlet được ánh xạ vào tiền tố riêng và dự án dùng PathPattern semantics. Nếu phiên bản Spring Security hiện tại chưa có API này, dùng matcher được hỗ trợ ở phiên bản đó, chẳng hạn `MvcRequestMatcher.Builder`.

## 5. Context path không phải một phần của pattern

Giả sử ứng dụng được deploy dưới `/shop`, controller có mapping `/api/orders/{id}`. Khi request thực tế là:

```text
GET /shop/api/orders/42
contextPath = /shop
servletPath = /api/orders/42
```

Pattern authorization thường vẫn là:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Nếu test viết:

```java
.requestMatchers("/shop/api/orders/**")
```

thì test có thể chạy được trong một môi trường đặc biệt nhưng không còn portable khi ứng dụng deploy ở root context hoặc context path khác. Tương tự, test không nên bỏ context path trong request URI rồi chỉ giả lập một URL khác với request production; cần dựng request theo đúng Servlet API.

### Ví dụ MockMvc với context path

Với `DispatcherServlet` mapping mặc định `/`, request MockMvc có thể mô phỏng deployment prefix:

```java
@Test
@WithMockUser(authorities = "SCOPE_orders.read")
void matcherIgnoresDeploymentContextPath() throws Exception {
    mvc.perform(get("/shop/api/orders/42")
            .contextPath("/shop"))
       .andExpect(status().isOk());
}
```

Mock request có `requestURI` là `/shop/api/orders/42`, `contextPath` là `/shop`; path mà ứng dụng xử lý vẫn là `/api/orders/42`. Matcher không nên yêu cầu tiền tố `/shop`.

Không tạo test authorization bằng cách cố tình ghép request URI thuộc context `/shop` với `contextPath` là `/portal`. Đây là mock request không nhất quán; cách xử lý có thể phụ thuộc MockMvc và phiên bản Spring Framework, nên không có một status cố định phù hợp để làm hợp đồng phân quyền. Trong test authorization, hãy dựng request hợp lệ rồi kiểm tra matcher có bỏ qua context prefix như mong muốn.

## 6. Servlet path khác context path: ứng dụng dùng /mvc/*

Giả sử servlet mapping là `/mvc/*`, context path `/shop`, controller mapping `/api/orders/{id}`. Request:

```text
GET /shop/mvc/api/orders/42

requestURI  = /shop/mvc/api/orders/42
contextPath = /shop
servletPath = /mvc
pathInfo    = /api/orders/42
```

Matcher phải hiểu `/mvc` là servlet path/base path và `/api/orders/42` là path MVC. Với `MvcRequestMatcher`:

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

RequestMatcher orderRead = mvc.pattern("/api/orders/**");
```

Với `PathPatternRequestMatcher` ở phiên bản hỗ trợ:

```java
PathPatternRequestMatcher.Builder mvc =
    PathPatternRequestMatcher.withDefaults()
        .basePath("/mvc");

RequestMatcher orderRead = mvc.matcher("/api/orders/**");
```

Trong cả hai cách, không thêm `/shop` vào pattern vì đó là context path. Cũng không thêm `/mvc` vào pattern khi builder đã cấu hình servlet/base path; nếu làm vậy, matcher có thể tìm `/mvc/mvc/api/orders` hoặc không khớp theo semantics của builder.

### Dựng MockHttpServletRequest với servlet mapping riêng

Khi cần kiểm tra chính xác thành phần request, có thể tạo mock request trực tiếp:

```java
MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/shop/mvc/api/orders/42");

request.setContextPath("/shop");
request.setServletPath("/mvc");
request.setPathInfo("/api/orders/42");

assertThat(request.getRequestURI())
    .isEqualTo("/shop/mvc/api/orders/42");
assertThat(request.getContextPath()).isEqualTo("/shop");
assertThat(request.getServletPath()).isEqualTo("/mvc");
assertThat(request.getPathInfo()).isEqualTo("/api/orders/42");
```

Đây là test cấu trúc request; để kiểm tra `MvcRequestMatcher` thực sự, cần khởi tạo matcher với `HandlerMappingIntrospector` và cấu hình servlet mapping phù hợp. Để kiểm tra toàn bộ chuỗi, dùng MockMvc được cấu hình theo mapping đó. Không dùng một mock request tự tạo rồi suy ra controller mapping đã hoạt động.

Với MockMvc request builder, có thể chỉ rõ các phần:

```java
mvc.perform(get("/shop/mvc/api/orders/42")
        .contextPath("/shop")
        .servletPath("/mvc")
        .pathInfo("/api/orders/42"))
   .andExpect(status().isOk());
```

Đoạn này chỉ hợp lệ nếu môi trường MockMvc/DispatcherServlet test được thiết lập để phản ánh servlet mapping `/mvc/*`. Mặc định `@WebMvcTest` thường dùng servlet mapping `/`; không đặt `servletPath("/mvc")` vào test mặc định rồi mong controller mapping hoạt động như ứng dụng đã triển khai dưới `/mvc/*`.

## 7. Cấu hình test cần phản ánh cách deploy

Một test authorization có thể chạy qua Spring Security filter chain nhưng vẫn dựng sai path. Khi đó kết quả không đại diện cho ứng dụng triển khai. Trước khi viết test, hãy ghi rõ:

| Câu hỏi | Ví dụ cấu hình |
| --- | --- |
| Context path là gì? | `""` ở root hoặc `"/shop"` |
| DispatcherServlet mapping? | `"/"` hay `"/mvc/*"` |
| Controller mapping? | `"/api/orders/{id}"` |
| Security matcher dùng API nào? | DSL matcher mặc định, `MvcRequestMatcher` hoặc `PathPatternRequestMatcher` |
| Có bao nhiêu filter chain? | API bearer chain và web session chain |
| Test dựng request ra sao? | URI + contextPath + servletPath/pathInfo tương ứng |

### Cấu hình servlet mapping mặc định

Với `DispatcherServlet` mapping `/`, security config đơn giản thường đủ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll());
```

MockMvc có thể dùng:

```java
mvc.perform(get("/shop/api/orders/42").contextPath("/shop"))
   .andExpect(status().isOk());
```

### Cấu hình servlet mapping có prefix

Với servlet mapping `/mvc/*`, cấu hình matcher tường minh:

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(
        HttpMethod.GET, "/api/orders/**"))
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll());
```

Khi dùng lambda `RequestMatcher`, hãy giữ điều kiện đơn giản, dễ kiểm tra và có test riêng. Nếu phiên bản đang dùng cung cấp matcher method-aware phù hợp, có thể dùng trực tiếp thay cho `AndRequestMatcher`.

## 8. Kiểm thử matcher độc lập trước khi kiểm thử toàn bộ HTTP

Nếu lỗi xuất phát từ cách diễn giải path, kiểm tra trực tiếp matcher giúp khoanh vùng trước khi đưa vào controller/service. Ví dụ với `PathPatternRequestMatcher`:

```java
class OrderRequestMatcherTest {
    private final RequestMatcher orderPath =
        PathPatternRequestMatcher.withDefaults()
            .matcher("/api/orders/**");

    @Test
    void matchesPathWithoutContextPrefix() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders/42");
        request.setServletPath("/api/orders/42");

        assertThat(orderPath.matches(request)).isTrue();
    }

    @Test
    void doesNotTreatContextPrefixAsApplicationPath() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/shop/api/orders/42");
        request.setContextPath("/shop");
        request.setServletPath("/api/orders/42");

        assertThat(orderPath.matches(request)).isTrue();
    }

    @Test
    void doesNotMatchAnotherResource() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/users/42");
        request.setServletPath("/api/users/42");

        assertThat(orderPath.matches(request)).isFalse();
    }
}
```

Ví dụ này giả định servlet mapping mặc định `/` và dùng `PathPatternRequestMatcher` ở phiên bản hỗ trợ. Khi dùng `MvcRequestMatcher`, cần cung cấp `HandlerMappingIntrospector` và servlet path tương ứng; không thể thay matcher này bằng matcher kia rồi mặc định kết quả luôn giống nhau.

Đối với matcher có điều kiện method:

```java
RequestMatcher getOrderPath = new AndRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher("/api/orders/**"),
    request -> HttpMethod.GET.matches(request.getMethod())
);
```

Test độc lập:

```java
MockHttpServletRequest getRequest =
    new MockHttpServletRequest("GET", "/api/orders/42");
getRequest.setServletPath("/api/orders/42");
assertThat(getOrderPath.matches(getRequest)).isTrue();

MockHttpServletRequest deleteRequest =
    new MockHttpServletRequest("DELETE", "/api/orders/42");
deleteRequest.setServletPath("/api/orders/42");
assertThat(getOrderPath.matches(deleteRequest)).isFalse();
```

Khi đã xác nhận matcher, hãy đưa chính matcher đó vào security config và kiểm tra request qua MockMvc. Test unit của matcher không thay thế integration test filter chain.

## 9. Kiểm thử MockMvc với context path

Ví dụ test slice cho servlet mapping mặc định:

```java
@WebMvcTest(OrderController.class)
@Import(MvcOrderSecurityConfig.class)
class OrderContextPathMvcTest {
    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void orderReadWorksUnderDeploymentContext() throws Exception {
        mvc.perform(get("/shop/api/orders/42")
                .contextPath("/shop"))
           .andExpect(status().isOk())
           .andExpect(content().string("order-42"));
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.write")
    void writeRuleStillUsesApplicationPath() throws Exception {
        mvc.perform(patch("/shop/api/orders/42")
                .contextPath("/shop"))
           .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void readScopeDoesNotAuthorizeDeleteUnderContextPath()
            throws Exception {
        mvc.perform(delete("/shop/api/orders/42")
                .contextPath("/shop"))
           .andExpect(status().isForbidden());
    }
}
```

Các test dùng `@WithMockUser` để kiểm tra authority sau xác thực; không kiểm tra JWT decoder. `@WebMvcTest`/`@AutoConfigureMockMvc` cần có security filters. Nếu tự tạo MockMvc qua `MockMvcBuilders`, tích hợp `springSecurity()` để request đi qua filter chain.

Trong test slice, cần đảm bảo URI, context path và mapping controller nhất quán. Nếu gặp lỗi do request URI/context path không hợp lệ, hãy kiểm tra mock request trước khi sửa matcher. Không nên thêm context path vào security pattern chỉ để làm một test fixture dựng sai trở nên xanh.

## 10. Các lưu ý về đường dẫn và matcher

### Trailing slash

Không mặc định `/api/orders` và `/api/orders/` luôn tương đương. Hành vi phụ thuộc Spring Framework, cấu hình path matching và matcher đang sử dụng. Hãy quyết định endpoint nào là canonical; nếu hỗ trợ cả hai, kiểm thử cả hai và tránh để một biến thể vô tình bỏ qua rule.

### Biến đường dẫn

Matcher `/api/orders/*` và `/api/orders/**` có phạm vi khác nhau theo semantics của matcher. Dấu `*` thường giới hạn một segment, còn `**` có thể bao gồm nhiều segment. Đừng dùng wildcard rộng hơn cần thiết. Với route lồng nhau như `/api/orders/42/attachments/7`, viết test để xác nhận pattern bao phủ đúng vùng dự kiến.

### URL encoding và dấu gạch chéo

Các path chứa encoded slash, dấu chấm, ký tự Unicode hoặc dấu gạch chéo lặp có thể được container, proxy và framework chuẩn hóa khác nhau. Không dựa vào một phép so khớp chuỗi tự viết mà bỏ qua cách request được giải mã/chuẩn hóa. Nếu ID có thể chứa ký tự đặc biệt, kiểm thử đường đi qua container hoặc integration test phù hợp.

### Query string

Thông thường `?expand=items` không phải một phần của path pattern. Nếu chính sách phụ thuộc query parameter, hãy kiểm tra bằng logic request rõ ràng và test cả trường hợp tham số thiếu, lặp hoặc không hợp lệ; không nhét query string vào pattern path.

### Dispatcher type

Request có thể đi qua nhiều dispatcher type như `REQUEST`, `ASYNC`, `ERROR` hoặc `FORWARD`. Một số ứng dụng cần chính sách riêng cho error dispatch hoặc forward. Đừng cho phép rộng mọi dispatcher type chỉ để tránh test lỗi; hãy xác định request nào cần được phép và kiểm thử luồng đó.

### WebFlux không có servletPath

Các khái niệm `HttpServletRequest.getServletPath()` và `getPathInfo()` chỉ thuộc Servlet API. Ứng dụng WebFlux không có `HttpServletRequest` hoặc `DispatcherServlet`; request path được biểu diễn bằng `RequestPath` trên `ServerHttpRequest`:

```java
RequestPath path = exchange.getRequest().getPath();

String contextPath = path.contextPath().value();
String pathWithinApplication = path.pathWithinApplication().value();
```

Với WebFlux, `pathMatchers("/api/**")` được viết theo path trong ứng dụng; không sao chép `servletPath("/mvc")` hoặc `pathInfo` từ cấu hình Servlet sang Reactive. Nếu ứng dụng Reactive được triển khai dưới context path, hãy kiểm thử cấu hình context path ở tầng WebFlux/server và xác nhận matcher vẫn nhắm vào `pathWithinApplication`. `WebTestClient` phải được gắn với application context và cấu hình test phản ánh context path thực tế; không dùng `MockMvc` hoặc `MvcRequestMatcher` cho WebFlux.

## 11. Chẩn đoán khi test không khớp

| Triệu chứng | Nguyên nhân thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| Matcher hoạt động ở root context nhưng lỗi khi deploy dưới `/shop` | Pattern bị thêm context path hoặc test không đặt contextPath | Xác minh requestURI/contextPath và giữ pattern độc lập context |
| Matcher không khớp khi servlet mapping là `/mvc/*` | Chưa cấu hình servletPath/basePath | Dùng builder phù hợp và pattern tương đối với servlet path |
| Rule đúng nhưng request vào chain khác | `securityMatcher` của chain không khớp như dự kiến | Kiểm tra thứ tự và phạm vi các SecurityFilterChain |
| Request đúng path nhưng sai method vẫn được phép | Matcher chỉ xét path hoặc rule rộng đứng trước | Kết hợp method và path, thêm ca âm |
| MockMvc test xanh nhưng ứng dụng thật sai | MockMvc dùng servlet mapping mặc định khác production | Cấu hình test phản ánh mapping thực tế hoặc bổ sung integration test |
| Matcher unit test đúng nhưng HTTP test sai | Request không qua đúng filter chain hoặc một filter khác từ chối | Kiểm tra MockMvc security integration, CSRF, authentication entry point |
| `MvcRequestMatcher` và matcher khác cho kết quả khác | Semantics MVC/path-pattern/Ant không giống nhau | Xác định loại matcher và phiên bản Spring Security |

### Quy trình debug có thứ tự

1. Ghi lại `requestURI`, `contextPath`, `servletPath`, `pathInfo` và HTTP method trong test.
2. Xác định servlet mapping thực tế, không chỉ controller mapping.
3. Xác định `SecurityFilterChain` được chọn bởi `securityMatcher`.
4. Xác định matcher authorization nào khớp đầu tiên.
5. Kiểm tra principal và authority, sau đó kiểm tra CSRF/CORS hoặc filter khác nếu request vẫn bị từ chối.
6. Xác minh controller mapping có tồn tại cho method đó; phân biệt lỗi security với `404`/`405` từ routing.

Nếu cần logging Spring Security để debug trong môi trường test, bật mức log phù hợp trong cấu hình test và không ghi token/credentials. Sau khi tìm được nguyên nhân, nên giữ test hồi quy mô tả request path/method và kết quả mong đợi.

## 12. Thực hành: cùng controller dưới nhiều servlet path

Một ứng dụng có controller `GET /api/reports/{id}` và `DELETE /api/reports/{id}`. Yêu cầu:

- `GET` yêu cầu `SCOPE_reports.read`.
- `DELETE` yêu cầu `ROLE_ADMIN`.
- Ứng dụng có thể deploy dưới context path `/reports-app`.
- Trong một cấu hình triển khai riêng, `DispatcherServlet` được ánh xạ vào `/mvc/*`.

Hãy thực hiện:

1. Viết hai bộ cấu hình matcher phù hợp với mapping mặc định `/` và mapping `/mvc/*`. Dùng API matcher tương thích với phiên bản Spring Security của dự án.
2. Không đưa `/reports-app` vào pattern security; mô phỏng nó qua `contextPath` của request test.
3. Với mapping `/mvc/*`, cấu hình servlet/base path và pattern tương đối với phần path sau servlet mapping.
4. Viết test matcher độc lập cho request đúng path, sai path, sai method và sai servlet path.
5. Viết MockMvc test cho `GET` được phép, `DELETE` bị từ chối với reader, `DELETE` được phép với admin, request anonymous và request dưới context path.
6. Nếu MockMvc mặc định không thể phản ánh servlet mapping tùy chỉnh, cấu hình môi trường test phù hợp hoặc bổ sung integration test chạy với mapping đó; không giả định chỉ thay `servletPath` trong builder là đã cấu hình DispatcherServlet.

**Tiêu chí hoàn thành:** test dựng đúng cấu trúc Servlet request; context path không bị nhúng nhầm vào security pattern; servlet path được cấu hình đúng với mapping; filter chain và authorization matcher được phân biệt; các ca dương/âm chứng minh đúng method, path và authority.
