# AbstractHttpConfigurer và đóng gói cấu hình bảo mật dùng lại

> **Ngữ cảnh:** Spring Security trên Servlet stack, Java 17+, Spring Boot 3 và Spring Security 6.2+ cho ví dụ dùng API `HttpSecurity.with(...)`. Chủ đề là cách tạo **một DSL/configurer cho `HttpSecurity`** để tái sử dụng quy tắc lắp ráp bộ lọc và các thành phần bảo mật trong nhiều `SecurityFilterChain`. Nội dung này không áp dụng trực tiếp cho WebFlux; bên reactive dùng `ServerHttpSecurity` và kiểu cấu hình khác.

## 1. Vì sao cần một `AbstractHttpConfigurer`?

Trong ứng dụng nhỏ, có thể cấu hình trực tiếp qua `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain chain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là **mảnh mã bên trong một lớp `@Configuration`**; cần import Spring Security tương ứng. Khi ứng dụng lớn có nhiều chain, module hoặc dịch vụ, các đoạn lắp ráp giống nhau thường xuất hiện ở nhiều nơi: thêm một filter nội bộ, thiết lập đối tượng dùng chung, quy định vị trí filter, hoặc đóng gói tập cấu hình theo một chính sách.

`AbstractHttpConfigurer` là lớp nền để tạo **cấu hình mở rộng cho `HttpSecurity`**. Nó đưa logic đó vào một thành phần có:

- **Tham số cấu hình rõ ràng:** người dùng DSL có thể gọi các setter kiểu fluent trước khi xây chain.
- **Hai pha vòng đời:** `init(...)` để chuẩn bị và `configure(...)` để lắp ráp vào builder.
- **Khả năng dùng lại theo từng builder/chain:** một loại configurer có thể được khởi tạo riêng cho các chain khác nhau.
- **Khả năng bật/tắt hoặc tích hợp theo cách chuẩn của Spring Security:** phù hợp với pipeline `http.build()`.

Nó **không tự thay thế** `SecurityFilterChain`, `AuthenticationManager` hoặc `SecurityContextRepository`. Cũng không phải một servlet filter: **configurer chạy khi dựng cấu hình**, còn servlet filter được nó đăng ký sẽ chạy **trên từng HTTP request phù hợp**.

### Nhìn từ tầng kiến trúc

~~~text
Khởi tạo ứng dụng
  -> @Bean SecurityFilterChain(HttpSecurity http)
  -> http.with(new MyConfigurer(), customizer)
  -> http.build()
       -> init() của các SecurityConfigurer
       -> configure() của các SecurityConfigurer
       -> xây DefaultSecurityFilterChain

Khi HTTP request đến
  -> FilterChainProxy chọn SecurityFilterChain theo request matcher
  -> servlet Filter đã được lắp trong chain xử lý request
  -> controller/response
~~~

Vì vậy, nếu cấu hình bị sai thứ tự, đăng ký trùng filter hoặc bỏ lỡ một chain, lỗi bắt nguồn từ **cách build chain**. Nếu filter gặp lỗi khi xử lý request, hãy xem cả vị trí chạy và logic runtime của filter; hai vấn đề này cần phân biệt.

## 2. Chữ ký generic và các phương thức quan trọng

Với `HttpSecurity`, lớp mở rộng thường có dạng:

~~~java
public final class MyConfigurer
        extends AbstractHttpConfigurer<MyConfigurer, HttpSecurity> {
    // Các lựa chọn và các hook vòng đời sẽ nằm ở đây.
}
~~~

Các generic mang ý nghĩa:

| Thành phần | Mục đích |
| --- | --- |
| `MyConfigurer` | Kiểu configurer cụ thể để các phương thức fluent có thể trả về chính kiểu đó. |
| `HttpSecurity` | Kiểu builder cần mở rộng trên Servlet stack. |
| `init(HttpSecurity http)` | Pha khởi tạo: kiểm tra cấu hình, tạo và công bố shared object, áp dụng cấu hình phụ thuộc nếu cần. |
| `configure(HttpSecurity http)` | Pha cấu hình: lắp ráp filter hoặc sử dụng các shared object đã được chuẩn bị. |
| `disable()` | API kế thừa có thể yêu cầu loại configurer khỏi builder **trước khi build**. |
| `http.with(configurer, customizer)` | Đăng ký configurer và thiết lập lựa chọn của nó (API được cung cấp trong các phiên bản Spring Security 6.2+). |
| `http.build()` | Thực thi vòng đời builder và tạo một `SecurityFilterChain`. |

`init` và `configure` đều là hook; có thể chỉ override hook thực sự cần. Không phải mọi configurer đều cần tạo shared object hoặc thêm filter. Các API mức thấp bên trong builder thay đổi theo phiên bản; tránh dựa vào chi tiết nội bộ thay cho hợp đồng API công khai.

### Thứ tự hai pha

Trong quá trình `http.build()`, Spring Security khởi tạo các configurer rồi mới cấu hình chúng. Có thể hình dung:

~~~text
Customizer của từng configurer (khi gọi http.with(...))
            |
            v
init(A) -> init(B) -> init(C)
            |
            v
configure(A) -> configure(B) -> configure(C)
            |
            v
SecurityFilterChain đã build
~~~

Sơ đồ này thể hiện **ranh giới pha**, không bảo đảm tất cả configurer được chạy theo một thứ tự cụ thể bất kể phụ thuộc. Không được giả định `configure(A)` đã chạy khi `init(B)` đang chạy. Hãy sử dụng shared object / API được thiết kế cho builder thay vì tự đoán thời điểm các filter đã tồn tại. Khi cần thứ tự **filter lúc xử lý HTTP**, dùng các API sắp thứ tự filter phù hợp; thứ tự phương thức cấu hình không phải thước đo duy nhất.

## 3. Ví dụ thực tế: đóng gói một filter gắn request trace ID

Bài toán: nhiều servlet security chain muốn trả một header `X-Request-Trace` do server phát sinh để dễ đối chiếu log với yêu cầu HTTP. Header này **chỉ phục vụ quan sát**, không phải token xác thực hoặc quyền truy cập.

Chúng ta tạo:

1. `TraceHeaderConfigurer`: giữ tùy chọn tên header; ở `init` tạo shared object bất biến; ở `configure` đăng ký filter.
2. `TraceHeaderFilter`: tạo UUID cho request và thêm vào response; đây mới là mã chạy theo HTTP request.
3. `SecurityConfig`: áp dụng DSL vào `HttpSecurity` bằng `with(...)`.

Ví dụ dùng Spring Boot 3 / Spring Security 6.2+ và Jakarta Servlet API. Các class có package `com.example.demo`, nằm trong dự án có `spring-boot-starter-web` và `spring-boot-starter-security`. Không thể dùng `javac` không có classpath Spring để biên dịch các ví dụ tích hợp này.

### 3.1. Tạo `TraceHeaderConfigurer.java`

~~~java
package com.example.demo;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

public final class TraceHeaderConfigurer
        extends AbstractHttpConfigurer<TraceHeaderConfigurer, HttpSecurity> {

    private String headerName = "X-Request-Trace";

    // Fluent option: được gọi trước http.build().
    public TraceHeaderConfigurer headerName(String value) {
        if (value == null || !value.matches("[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException("Invalid trace header name");
        }
        this.headerName = value;
        return this;
    }

    @Override
    public void init(HttpSecurity http) {
        // Shared object thuộc một HttpSecurity builder, không phải biến toàn JVM.
        http.setSharedObject(
                TraceHeaderSettings.class,
                new TraceHeaderSettings(headerName)
        );
    }

    @Override
    public void configure(HttpSecurity http) {
        TraceHeaderSettings settings =
                http.getSharedObject(TraceHeaderSettings.class);
        if (settings == null) {
            throw new IllegalStateException("Trace settings were not initialized");
        }

        http.addFilterBefore(
                new TraceHeaderFilter(settings.headerName()),
                UsernamePasswordAuthenticationFilter.class
        );
    }

    public record TraceHeaderSettings(String headerName) {}
}
~~~

**Điểm cần hiểu:**

- `headerName(...)` chạy **khi cấu hình chain**, trước `http.build()`. Nó không được gọi trên từng request.
- `TraceHeaderSettings` là record Java 17 bất biến; `setSharedObject` lưu theo **builder hiện tại** để configurer khác (nếu được thiết kế tương thích) có thể truy cập. Với bài toán chỉ một filter, cũng có thể dùng trực tiếp trường `headerName` trong `configure` và bỏ shared object; ví dụ dùng shared object để thể hiện ý nghĩa của pha `init`.
- `configure` thêm filter vào vị trí đã biết trong Spring Security chain, trước loại `UsernamePasswordAuthenticationFilter`. API sắp thứ tự theo class tham chiếu; không cần tự tạo một instance `UsernamePasswordAuthenticationFilter`.
- Với lựa chọn hiện tại, trace filter **chạy trước bước xác thực form-login**; vì thế không nên đọc authenticated principal ở đó rồi cho rằng nó đã được thiết lập. Muốn xử lý hậu xác thực, hãy chọn anchor/thiết kế phù hợp và kiểm tra filter chain thực tế.
- `TraceHeaderSettings` là loại shared object riêng cho minh họa. Nếu nhiều configurer cùng ghi object có cùng `Class` trên một builder, chúng có thể ghi đè nhau; hãy đặt tên/ownership rõ ràng.

### 3.2. Tạo `TraceHeaderFilter.java`

~~~java
package com.example.demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.springframework.web.filter.OncePerRequestFilter;

public final class TraceHeaderFilter extends OncePerRequestFilter {
    private final String responseHeaderName;

    public TraceHeaderFilter(String responseHeaderName) {
        this.responseHeaderName = responseHeaderName;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Luôn tạo ID ở phía server; không tin giá trị header do client gửi.
        response.setHeader(responseHeaderName, UUID.randomUUID().toString());
        chain.doFilter(request, response);
    }
}
~~~

Đây là filter tối giản: không đọc/ghi `SecurityContext`, không tạo session, không cấp quyền. `OncePerRequestFilter` có ngữ nghĩa “once” theo chính sách dispatch của filter, không phải bảo đảm một HTTP request bất đồng bộ chỉ đi qua mã này một lần trong mọi tình huống. Hành vi trên `ASYNC`/`ERROR` dispatch tùy cấu hình/override thích hợp.

Không đăng ký class này thêm lần nữa bằng `@Component` hoặc `FilterRegistrationBean` khi đã đặt nó vào Spring Security chain; nếu Spring Boot tự đăng ký một `Filter` như servlet filter độc lập, nó có thể chạy ngoài chain bảo mật và gây xử lý kép hoặc sai thứ tự.

### 3.3. Tạo `SecurityConfig.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .with(new TraceHeaderConfigurer(), trace ->
                trace.headerName("X-Request-Trace"));

        return http.build();
    }
}
~~~

`with(new TraceHeaderConfigurer(), trace -> trace.headerName(...))` gồm hai bước: đăng ký configurer vào builder và tùy chỉnh đối tượng đó **trước khi build**. Khi gọi `http.build()`, Spring Security mới chạy các hook lifecycle. Kết quả là `SecurityFilterChain` đã chứa filter `TraceHeaderFilter` và những filter do cấu hình authentication/authorization cung cấp.

Ví dụ dùng HTTP Basic cho endpoint bảo vệ để thấy rõ filter chain. `.requestMatchers("/public").permitAll()` chỉ cho phép endpoint công khai đi qua **bước authorization**; nó **không bỏ qua toàn bộ Spring Security filters**. Vì vậy request `/public` vẫn nhận trace header.

### 3.4. Endpoint mẫu `PublicController.java`

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {
    @GetMapping("/public")
    public String publicPage() {
        return "ok";
    }
}
~~~

Đặt các class trên trong package được Spring Boot scan (ví dụ bên dưới package chứa `@SpringBootApplication`). Một ứng dụng Boot bình thường đã có main class và build file; các tệp trên là phần **bổ sung vào dự án**, không phải toàn bộ dự án Maven/Gradle độc lập.

Sau khi chạy ứng dụng với cấu hình phù hợp, thử:

~~~bash
curl -i http://localhost:8080/public
~~~

Kỳ vọng nhận HTTP `200`, body `ok` và **một header** `X-Request-Trace` chứa UUID do server phát sinh. Giá trị UUID thay đổi theo lần gọi, và các header khác phụ thuộc container; không nên ghi một output cố định không đúng thực tế. `GET` đến một path yêu cầu xác thực mà không gửi credentials sẽ bị authorization/authentication xử lý theo cấu hình HTTP Basic; đây là kết quả của chain, không phải của trace filter.

## 4. Một configurer có thể chia sẻ cho nhiều SecurityFilterChain như thế nào?

Trong một ứng dụng có cả `/api/**` lẫn phần web, ta có thể dùng **cùng một loại class configurer** nhưng **mỗi chain tạo instance mới** và cấu hình tùy chọn độc lập:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .with(new TraceHeaderConfigurer(), t ->
                t.headerName("X-Api-Trace"));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .with(new TraceHeaderConfigurer(), t ->
                t.headerName("X-Web-Trace"));

        return http.build();
    }
}
~~~

**Đây là cấu hình thay thế cho `SecurityConfig` ở mục 3, không bật cả hai cùng lúc.** Nếu bật cùng lúc, các catch-all chains và thứ tự matcher có thể khiến request vào chain ngoài dự kiến.

Tại thời điểm request:

| Request | Chain được chọn trong ví dụ thay thế | Header được tạo |
| --- | --- | --- |
| `GET /api/orders` | `api`, vì `/api/**` match và `@Order(1)` | `X-Api-Trace` |
| `GET /public` | `web`, vì không match chain API | `X-Web-Trace` |
| `GET /other` | `web`, vì chain web không khai báo `securityMatcher` riêng | `X-Web-Trace` |

Các endpoint minh họa `/api/orders` và `/other` có thể chưa được implement; security filter vẫn có thể xử lý request trước khi Spring MVC tìm handler. Đừng nhầm HTTP `404` (không có controller) với việc security chain không chạy.

**Khác biệt then chốt giữa hai matcher:**

- `securityMatcher(...)` quyết định **chain này có được `FilterChainProxy` chọn hay không**.
- `requestMatchers(...)` trong `authorizeHttpRequests(...)` quyết định **quy tắc authorization bên trong chain đã được chọn**.

Cấu hình `permitAll` không bảo đảm mọi filter tùy chỉnh bị bỏ qua. Nếu filter chỉ nên chạy cho một phần URL, hãy thiết kế matcher ở đúng cấp (chain hoặc trong filter), kiểm thử cả đường dẫn được cho phép và đường dẫn cần xác thực.

## 5. Dùng lại mã mà vẫn giữ đúng trách nhiệm

`AbstractHttpConfigurer` phù hợp khi bạn muốn đóng gói **cách xây security chain**, không phải khi chỉ cần một hàm Java chung. So sánh:

| Mục tiêu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Gắn một bộ filter và shared objects có hook `init/configure` | `AbstractHttpConfigurer` | Tham gia đúng lifecycle của `HttpSecurity`. |
| Dùng lại vài rule `authorizeHttpRequests` đơn giản | Phương thức cấu hình/helper hoặc một bean cung cấp customizer có kiểm soát | Ít trạng thái, có thể không cần DSL mới. |
| Chia sẻ logic kiểm tra quyền nghiệp vụ | `AuthorizationManager`, method security, policy service | Trách nhiệm authorization tách khỏi chuyện lắp filter. |
| Tái sử dụng cách xác thực credential | `AuthenticationProvider`/authentication manager và thành phần auth tương ứng | Tách việc xác thực khỏi configurer. |
| Thêm một servlet filter chung ngoài Spring Security | Đăng ký servlet filter có chủ đích | Không lẫn vòng đời filter của container với `SecurityFilterChain`. |
| Áp dụng chính sách qua nhiều ứng dụng | Thư viện/starter cung cấp configurer, beans và tài liệu opt-in | Mỗi ứng dụng vẫn kiểm soát chain/matcher/tuỳ chọn. |

Một configurer tốt thường có API ngắn, rõ tên và an toàn mặc định. Ví dụ `TraceHeaderConfigurer.headerName(...)` biểu diễn một tùy chọn cụ thể; tránh method tên mơ hồ kiểu `enabled(boolean)` nếu thực tế filter vẫn được tạo trong một số nhánh, hoặc method tự động tắt CSRF/session ngoài yêu cầu.

### Các quy tắc thiết kế một DSL dùng lại được

1. **Chọn đúng phạm vi:** cung cấp configurer cho `HttpSecurity` cụ thể; không sử dụng `static` mutable field để chứa tên header, principal hay trạng thái từng chain/request.
2. **Tùy chọn được chốt trước `build()`:** mọi setter nên phục vụ giai đoạn cấu hình. Không sửa configurer sau khi chain đã build rồi kỳ vọng filter đang chạy đổi hành vi.
3. **Giữ option bất biến lúc đăng ký filter:** filter nên nhận giá trị qua constructor, tránh đọc một mutable configurer ở thời điểm request.
4. **Xác định quyền sở hữu shared object:** loại object và thời điểm tạo/sử dụng phải rõ. Đừng ghi đè một `AuthenticationManager`/`SecurityContextRepository` hoặc shared object sẵn có chỉ để “tiện”.
5. **Không lén thay đổi chính sách:** thêm filter tracing không được vô hiệu `csrf()`, `authorizeHttpRequests()`, `sessionManagement()` hay thiết lập logout.
6. **Làm rõ thứ tự chạy filter:** vị trí trước/sau authentication, authorization và exception translation ảnh hưởng trực tiếp đến dữ liệu/exception nào thấy được.
7. **Không đăng ký filter hai lần:** tách cấu hình Servlet container và cấu hình Spring Security.
8. **Bảo đảm test riêng cho từng security chain:** nhiều chain tạo nhiều cấu hình và nhiều tập hợp filter khác nhau.

## 6. Vị trí filter và mối quan hệ với các thành phần bảo mật khác

Các API như:

~~~java
http.addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAfter(myFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAt(myFilter, UsernamePasswordAuthenticationFilter.class);
~~~

là **các mảnh mã minh họa**, cần có `myFilter` kiểu servlet filter và đặt trong nơi đang cấu hình `HttpSecurity`. Chúng biểu thị ý định gắn vị trí tương đối so với filter class có thứ tự được Spring Security biết tới.

- `addFilterBefore`: phù hợp khi filter cần chuẩn bị metadata, correlation ID hoặc dữ liệu mà authentication logic sử dụng.
- `addFilterAfter`: phù hợp khi cần hành vi sau **vị trí** của một filter tham chiếu, nhưng điều đó **không tự bảo đảm** principal đã xác thực hoặc response chưa commit.
- `addFilterAt`: thêm vào **cùng vị trí thứ tự**; không nên mặc định là “thay thế” filter gốc. Nếu hai filter có cùng order, thứ tự giữa chúng không phải cơ sở ổn định để thiết kế cơ chế bảo mật.

`HttpSecurity` biết thứ tự của nhiều loại filter chuẩn kể cả khi một loại cụ thể chưa được thêm vào chain. Tuy nhiên, sự tồn tại thực tế của filter và thứ tự cuối cùng phải được kiểm tra bằng security chain đang chạy.

Một filter tracing đặt trước `UsernamePasswordAuthenticationFilter` **không nên** dựa vào `SecurityContextHolder.getContext().getAuthentication()` là người dùng đã đăng nhập: authentication filter có thể chưa chạy, request có thể anonymous hoặc sử dụng một cơ chế token khác. Nếu thực sự cần đánh giá quyền, hãy dùng `AuthorizationManager`/method security và kiểm thử tại đúng điểm trong chuỗi.

## 7. `init()`, `configure()` và shared objects: dùng khi nào?

Một cách phân chia trách nhiệm hữu ích:

**Trong `init(...)`:**
- Xác minh các tùy chọn cần thiết đã được cung cấp hoặc dùng giá trị mặc định hợp lệ.
- Tạo/công bố một object dùng chung cho quá trình xây chain bằng `http.setSharedObject(Type.class, value)` khi **có nhu cầu thật**.
- Thiết lập phụ thuộc cấu hình ở cấp builder nếu API công khai cho phép.
- Tránh giả định tất cả các filter đã được tạo, hoặc truy cập runtime request/session.

**Trong `configure(...)`:**
- Đọc shared object đã được chuẩn bị qua `getSharedObject(...)`, nếu cần.
- Khởi tạo và gắn filter cuối cùng theo thứ tự phù hợp.
- Hoàn thiện cấu hình phụ thuộc các thành phần do builder cung cấp ở pha này.
- Tránh thực thi nghiệp vụ cho một HTTP request: chưa có request thực ở giai đoạn này.

Ở ví dụ trên, `TraceHeaderSettings` được tạo bằng `record` bất biến ở `init`, sau đó `configure` dùng để tạo `TraceHeaderFilter`. Khi không có thành phần khác dùng shared object, có thể viết configurer đơn giản hơn:

~~~java
@Override
public void configure(HttpSecurity http) {
    http.addFilterBefore(
        new TraceHeaderFilter(headerName),
        UsernamePasswordAuthenticationFilter.class
    );
}
~~~

Đoạn trên là **phương án thay thế cho `configure(...)` trong `TraceHeaderConfigurer`**, không phải code thêm vào bên cạnh nó. Khi dùng phương án này, có thể bỏ `init(...)` và `TraceHeaderSettings`. Đừng thêm shared object chỉ để làm cho DSL trông phức tạp.

### Cẩn thận với thay đổi builder từ nhiều configurer

Các configurer khác có thể cùng tương tác với shared objects và filter collection. Nếu configurer A phụ thuộc đối tượng từ B, hãy thiết kế hợp đồng dependency rõ ràng, kiểm tra thứ tự build và lỗi thiếu dependency. Không tự giả định “vì `with(A)` nằm trước `with(B)` nên filter A luôn chạy trước B” hoặc “`configure(A)` xong rồi mới `init(B)`”. Hai pha và thứ tự filter là hai trục riêng.

## 8. Đăng ký, tái áp dụng và tắt configurer

Một lần áp dụng điển hình:

~~~java
http.with(new TraceHeaderConfigurer(),
        trace -> trace.headerName("X-Request-Trace"));
~~~

Trong Spring Security 6.2+, API `with(configurer, customizer)` diễn đạt ý định rõ hơn cách gọi `apply(...)` cũ; `apply(...)` đã bị deprecate trong các phiên bản 6.x mới, nên các codebase nâng cấp nên đối chiếu migration guide đúng phiên bản của mình.

Đừng gọi `with(new TraceHeaderConfigurer(), ...)` nhiều lần trên **cùng một `HttpSecurity`** như thể hai filter độc lập chắc chắn được thêm vào: configurer có thể được quản lý theo class, lần đăng ký sau làm thay đổi/kết thúc khả năng của lần trước, tùy builder và phiên bản. Hãy tạo một configurer có khả năng nhận nhiều option, hoặc hai class configurer khác biệt nếu thật sự cần hai trách nhiệm.

Một configurer kế thừa phương thức `disable()` để loại chính nó khỏi builder trước lúc build. Cần phân biệt:

- **Không đăng ký configurer:** không có hành vi từ configurer đó.
- **Đăng ký rồi disable trước `build()`:** dự kiến không chạy hook thêm filter của configurer đã bị loại; kiểm tra lại với version thực tế.
- **Gỡ configurer sau `build()`:** không phải cơ chế thay đổi một `SecurityFilterChain` đã build.
- **`http.csrf(AbstractHttpConfigurer::disable)`:** là thao tác tắt **CSRF configurer**, không có nghĩa tắt DSL tracing. Không sao chép từ tutorial API vào ứng dụng web dùng cookie/session mà không hiểu CSRF.

Khi thư viện có nhiều cơ chế opt-in, ưu tiên một public API đơn giản và tài liệu nêu chain nào được áp dụng. Nếu configurer có trạng thái tùy chỉnh, tạo instance mới cho từng builder; không giữ một instance mutable làm singleton tái dùng cho mọi chain.

## 9. Kiểm thử chức năng và ranh giới bảo mật

Ở ví dụ có `SecurityConfig` và `PublicController` (mục 3) trong một ứng dụng Boot chuẩn, có thể viết kiểm thử Spring MVC dùng `MockMvc` và `spring-security-test`. Tệp `SecurityConfigTest.java`:

~~~java
package com.example.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointGoesThroughConfiguredFilter() throws Exception {
        mvc.perform(get("/public"))
           .andExpect(status().isOk())
           .andExpect(content().string("ok"))
           .andExpect(header().exists("X-Request-Trace"));
    }

    @Test
    void otherEndpointStillRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
           .andExpect(status().isUnauthorized())
           .andExpect(header().exists("X-Request-Trace"));
    }
}
~~~

Trong ví dụ, `/private` không có controller vẫn có thể nhận `401` do security xử lý trước bước định tuyến MVC. Test không chứng minh mọi chính sách bảo mật của ứng dụng; nó kiểm chứng **filter đã nằm trong chain** và **authorization vẫn hoạt động**. Một số ứng dụng tùy biến `AuthenticationEntryPoint` có thể trả status khác; kết quả trên dựa vào cấu hình `httpBasic(Customizer.withDefaults())` của mục 3.

Nếu dự án có Maven Wrapper và những dependency đã nêu, chạy:

~~~bash
./mvnw test
~~~

Tùy hệ điều hành, Windows dùng `mvnw.cmd test`. Nếu không dùng wrapper, chạy công cụ build tương ứng của dự án. Đây là kiểm thử **tích hợp Spring Boot**; không phải chương trình Java SE có stdout cố định.

### Những bài test bổ sung nên có

| Tình huống | Điều cần xác minh |
| --- | --- |
| Một chain, request `/public` | Filter vẫn chạy dù rule authorization là `permitAll`. |
| Path bị chặn | Trace header không vô tình cấp quyền; security vẫn trả `401/403` theo chính sách. |
| Hai chain `/api/**` và web | Mỗi chain chọn đúng matcher, header cấu hình tương ứng, không bị chồng chain. |
| Cấu hình trùng filter | Mỗi request được xử lý đúng số lần mong đợi; filter không bị servlet container đăng ký ngoài chain. |
| Header name không hợp lệ | DSL từ chối input sai trước build; filter không tạo header có tên lỗi. |
| Một request khác hoặc nhiều request đồng thời | Không dùng mutable state tĩnh để chia sẻ request ID; mỗi request có giá trị độc lập. |
| ERROR/ASYNC dispatch khi ứng dụng hỗ trợ | Nắm rõ dispatcher types, có thể lọc lại hoặc bỏ qua theo cấu hình; không giả định “once per HTTP request” tuyệt đối. |
| Thêm filter phải chạy sau authentication | Test vị trí thực sự và principal ở điểm dùng, không chỉ kiểm tra response status. |

Khi cần xem thứ tự filter, hãy bật logging phù hợp cho `org.springframework.security.web.FilterChainProxy` trong môi trường phát triển hoặc quan sát chain do Spring Security tạo. Tránh log credentials, cookie session, access token hoặc toàn bộ `SecurityContext`.

## 10. Lỗi thường gặp khi đóng gói DSL

### Lỗi 1: Tưởng `AbstractHttpConfigurer` xử lý request

Không đúng: `init` và `configure` chạy lúc **xây cấu hình**. Servlet filter do configurer thêm mới chạy với từng request. Nếu cần logic theo request, đặt nó trong `Filter`, `AuthorizationManager` hoặc thành phần runtime thích hợp.

### Lỗi 2: Cùng một instance mutable dùng cho nhiều chain

Ví dụ giữ `TraceHeaderConfigurer` là static singleton rồi gọi `headerName(...)` khác nhau có thể làm cấu hình và lifecycle khó dự đoán. Với mỗi `HttpSecurity`, tạo `new TraceHeaderConfigurer()` và truyền option riêng. Tương tự, filter tự chia sẻ mutable request state giữa các request có thể gây race condition.

### Lỗi 3: Đăng ký filter qua hai tầng

Một filter vừa là `@Component` được container đăng ký, vừa được `http.addFilterBefore(...)` có thể chạy hai lần hoặc ở vị trí không tương ứng với chain. Đăng ký tại một tầng có chủ đích; nếu bắt buộc dùng bean filter trong security chain, kiểm soát auto-registration của Boot bằng một `FilterRegistrationBean` tắt đăng ký bên ngoài theo thiết kế ứng dụng.

### Lỗi 4: Nhầm matcher của chain với rule authorization

`securityMatcher("/api/**")` giới hạn **chọn chain**. `requestMatchers("/api/**").authenticated()` chỉ đặt rule **bên trong chain đã được chọn**. Nếu cấu hình catch-all có `@Order` ưu tiên cao, chain API có thể không bao giờ được chọn. Kiểm thử matcher là phần thiết yếu của khả năng tái sử dụng.

### Lỗi 5: Không kiểm tra filter order thực tế

Chỉ vì code `with(...)` đứng sau `httpBasic(...)` không có nghĩa filter runtime đứng sau BasicAuthenticationFilter. Phải định vị bằng `addFilterBefore/After/At` với anchor thích hợp và kiểm chứng bằng chain. Nếu xác thực được thực hiện bởi nhiều cơ chế, không có một filter “đăng nhập xong” duy nhất cho mọi đường đi.

### Lỗi 6: Dùng configurer để vô hiệu hóa bảo vệ chung

Một DSL chỉ thêm trace header không nên đổi `csrf`, `cors`, `headers`, session policy hay logout. Các thay đổi security-sensitive phải được chỉ định rõ và kiểm thử rủi ro ở chain tương ứng. Đóng gói lại code không tự làm chính sách bảo mật tốt hơn.

### Lỗi 7: Đọc shared object trước khi nó sẵn sàng

`init(...)` và `configure(...)` khác pha. `getSharedObject(...)` có thể trả `null` nếu loại object chưa được tạo hoặc bị configurer khác thay thế. Nên kiểm tra điều kiện cần, tạo shared object ở đúng pha hoặc dùng API công khai phù hợp; đừng gọi trực tiếp `configure(...)` của configurer khác.

### Lỗi 8: Tin rằng `permitAll` vô hiệu filter tùy chỉnh

`permitAll` vẫn đi qua chain. Điều này hữu ích cho logging/trace nhưng có thể gây vấn đề nếu filter tự buộc credential với mọi request. Nếu cần một số route không đi qua filter, điều chỉnh matcher hoặc `shouldNotFilter(...)` thay vì mặc định route công khai sẽ được bỏ qua.

### Lỗi 9: Bỏ qua khả năng nâng cấp phiên bản

API `with(...)` xuất hiện từ Spring Security 6.2; dự án Spring Security 6.0/6.1 có thể dùng API khác. Khi nâng cấp sang phiên bản mới, đối chiếu release notes và compiler warnings. Không dùng tutorial từ một major khác để suy ra chính xác constructor, hook hoặc rule authorization của ứng dụng hiện tại.

## 11. Checklist khi đưa configurer vào thư viện chung

- Xác định rõ **module/chain nào** cần configurer và URL nào match các chain đó.
- Thiết kế DSL nhỏ, typed, có validation; mặc định an toàn.
- Giữ request-specific state ở filter/task, không lưu vào field chung của configurer.
- Chọn `init` cho việc chuẩn bị/shared object, `configure` cho lắp ráp filter; chỉ override khi cần.
- Không tạo hoặc thay `SecurityContext`/authentication/session nếu tính năng không liên quan.
- Dùng `http.with(new CustomConfigurer(), customizer)` trong phiên bản hỗ trợ, xây mỗi chain đúng một lần.
- Xác minh filter order, tránh auto-register filter ở container bên ngoài chain.
- Kiểm thử positive/negative path, nhiều chain, async/error nếu có.
- Tài liệu hóa các dependency Spring Boot/Spring Security, yêu cầu Java và những mặc định thay đổi.

## 12. Câu hỏi ôn tập

**Q1. `AbstractHttpConfigurer` khác một `Filter` ở điểm nào?** Configurer mở rộng **giai đoạn build `HttpSecurity`**; Filter xử lý **HTTP request runtime** sau khi được lắp vào chain.

**Q2. Tại sao gọi `init` và `configure` trong hai pha?** Các configurer có cơ hội chuẩn bị/công bố shared objects trước khi cấu hình filter cuối cùng; nhờ đó việc phụ thuộc giữa các thành phần dễ kiểm soát hơn.

**Q3. Làm sao một configurer có thể tái sử dụng giữa nhiều chain nhưng có option khác nhau?** Tạo một instance mới cho mỗi `HttpSecurity` rồi truyền `Customizer` thích hợp trong `with(...)`. Mỗi builder sinh một chain độc lập.

**Q4. `requestMatchers("/public").permitAll()` có khiến custom filter ngừng chạy không?** Không. Route vẫn thuộc security chain đã match; `permitAll` chỉ quyết định authorization.

**Q5. `addFilterAt(myFilter, SomeFilter.class)` có tự thay filter gốc không?** Không có bảo đảm như vậy; nó chỉ gắn cùng vị trí thứ tự. Kiểm tra chain để tránh hai filter cùng order và phụ thuộc thứ tự không xác định.

**Q6. Lúc nào nên dùng một helper thay vì tạo configurer?** Khi chỉ chia sẻ vài dòng cấu hình đơn giản, không cần tham gia pha `init/configure`, shared objects hay đóng gói lifecycle. Tránh thêm lớp DSL không mang lại giá trị.

**Ghi nhớ:** `AbstractHttpConfigurer` đóng gói **cách lắp ráp cấu hình bảo mật** vào một `HttpSecurity`. Thiết kế tốt làm rõ option, lifecycle, vị trí filter và phạm vi chain; các quyết định xác thực/ủy quyền vẫn phải dùng thành phần bảo mật đúng trách nhiệm.
