# DispatcherServlet và vị trí của Servlet Filter trước HandlerInterceptor

> **Phạm vi:** Spring MVC chạy trên Servlet stack (Spring Boot 3.x, Spring Security 6.x), thuộc chủ đề **Nền tảng Servlet**. Bài này giải thích thứ tự thực thi trên cùng một HTTP request, đặc biệt là lý do lớp bảo mật Spring Security có thể xử lý hoặc từ chối request trước khi MVC chọn controller. Spring WebFlux dùng WebFilter/WebFilterChain và cơ chế dispatch khác.

## 1. Ba thành phần ở ba vị trí khác nhau

Khi nhận một HTTP request, **Servlet container** (ví dụ Tomcat) vận hành chuỗi `jakarta.servlet.Filter`. Nếu request đi tiếp đến servlet MVC, **`DispatcherServlet`** đóng vai trò front controller: tìm handler, chọn adapter thực thi và phối hợp xử lý kết quả. **`HandlerInterceptor`** thuộc riêng Spring MVC, được gắn vào `HandlerExecutionChain` sau khi MVC xác định handler phù hợp.

| Thành phần | Ai gọi? | Điểm chạy | Nhiệm vụ phù hợp |
| --- | --- | --- | --- |
| `Filter` (`jakarta.servlet.Filter`) | Servlet container và `FilterChain` | **Bên ngoài, trước khi vào `DispatcherServlet`**; thường có đoạn xử lý khi response quay ra | CORS, chuẩn hóa request/response, correlation ID, logging, bảo mật ở ranh giới web |
| `DispatcherServlet` | Servlet container gọi như một `HttpServlet` | Sau các filter đã gọi `chain.doFilter` thành công để chuyển tiếp | `HandlerMapping`, `HandlerAdapter`, xử lý ngoại lệ MVC, render/ghi response |
| `HandlerInterceptor` | Spring MVC thông qua `HandlerExecutionChain` | **Bên trong quá trình dispatch của MVC**, sau bước chọn handler và trước khi controller chạy | Gắn dữ liệu theo handler, đo thời gian MVC, kiểm tra điều kiện giao diện/định tuyến không mang tính bảo mật cốt lõi |

**Quy tắc nhận diện:** Filter có thể chặn request *trước khi MVC biết controller nào sẽ xử lý*. Interceptor MVC chỉ được gọi khi request đã đi vào `DispatcherServlet` và được ánh xạ tới một handler kèm interceptor đó.

## 2. Luồng request thông thường và đường quay về

```text
HTTP client
  |
  v
Servlet container
  |
  v
Filter A.doFilter(...)      <-- chạy phần "before"
  |
  +-- Filter B.doFilter(...) <-- có thể là DelegatingFilterProxy của Spring Security
  |     |
  |     +-- ... các security filter ... --> có thể trả 401/403 tại đây
  |     |
  |     +-- chain.doFilter(...) nếu được đi tiếp
  |              |
  |              v
  |        DispatcherServlet
  |              |
  |        HandlerMapping -> handler + các HandlerInterceptor
  |              |
  |        interceptor.preHandle()       (theo thứ tự đăng ký)
  |              |
  |        HandlerAdapter -> Controller
  |              |
  |        interceptor.postHandle()      (theo thứ tự ngược)
  |              |
  |        xử lý kết quả / render khi cần
  |              |
  |        interceptor.afterCompletion() (theo thứ tự ngược)
  |              |
  |              v
  |          trở về filter B
  |
  v
trở về filter A             <-- chạy phần "after" / finally
  |
  v
HTTP response
```

Sơ đồ thể hiện một request đồng bộ, hoàn tất bình thường. Tên và thứ tự **các filter thực tế** phụ thuộc vào cấu hình đăng ký và thứ tự của container. `DelegatingFilterProxy` cũng là một servlet filter; các security filter do nó gọi nằm *bên trong* chuỗi bảo mật, không phải các `HandlerInterceptor`.

Ví dụ với hai filter lồng nhau, đoạn mã sau mô tả mô hình “vào theo thứ tự, ra theo thứ tự ngược”:

```java
public void doFilter(ServletRequest request, ServletResponse response,
                     FilterChain chain) throws IOException, ServletException {
    System.out.println("A: before");
    try {
        chain.doFilter(request, response);
    } finally {
        System.out.println("A: after");
    }
}
```

Đây là **phần thân minh họa** của một filter, không phải một lớp Java độc lập. `chain.doFilter` gọi filter kế tiếp hoặc servlet đích. Nếu downstream chạy thành công, `finally` thực thi trên đường quay ra; nếu downstream ném ngoại lệ, `finally` vẫn chạy. Nếu filter **không gọi** `chain.doFilter`, `DispatcherServlet` và interceptor sẽ không nhận request đó trên nhánh thực thi ấy.

## 3. DispatcherServlet làm gì khi request đi qua filter?

Trong luồng MVC thường gặp:

1. Container chọn servlet theo URL mapping và thực thi các servlet filter phù hợp; mỗi filter quyết định gọi tiếp hay kết thúc request.
2. `DispatcherServlet` tiếp nhận request. `HandlerMapping` xác định handler và tạo `HandlerExecutionChain` chứa các interceptor áp dụng cho handler/path đó.
3. MVC gọi từng `preHandle(request, response, handler)`. Nếu tất cả trả `true`, `HandlerAdapter` gọi handler (ví dụ phương thức controller).
4. Với xử lý đồng bộ thành công, MVC gọi `postHandle` theo thứ tự ngược, sau đó xử lý kết quả/render nếu cần.
5. MVC gọi `afterCompletion` theo thứ tự ngược cho những interceptor đã hoàn tất `preHandle` với kết quả `true`, rồi kết thúc dispatch; các filter bao ngoài mới hoàn tất đoạn mã sau `chain.doFilter`.

Điểm cần phân biệt: `DispatcherServlet` **không** quản lý thứ tự của servlet filter; `WebMvcConfigurer.addInterceptors` **không** đưa interceptor lên trước filter. Một interceptor không thể bảo đảm bắt tất cả request của container (ví dụ request bị từ chối sớm trong security chain hoặc không được định tuyến vào MVC).

Các hook có điều kiện quan trọng:

- `preHandle` trả `false`: MVC dừng gọi handler; interceptor đang trả `false` **không** nhận `postHandle`/`afterCompletion` tương ứng; những interceptor đứng trước đã trả `true` có thể được gọi `afterCompletion` để dọn dẹp.
- Controller/handler phát sinh lỗi: `postHandle` có thể không chạy. `afterCompletion` thường vẫn được gọi cho interceptor có `preHandle=true` sau khi MVC xử lý dispatch/exception; đừng đặt cleanup chỉ trong `postHandle`.
- `@RestController` có thể ghi response body ngay trong giai đoạn xử lý handler; `postHandle` không phải vị trí chắc chắn để sửa response body sau đó.
- Với MVC bất đồng bộ (`Callable`, `DeferredResult`), vòng dispatch ban đầu có thể kết thúc mà chưa gọi `postHandle`/`afterCompletion`; `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` và lần dispatch tiếp theo cần được tính đến.

## 4. Spring Security nằm ở đâu?

Trên Servlet stack, Spring Security thường được tích hợp bằng servlet filter tên **`springSecurityFilterChain`**: container gọi `DelegatingFilterProxy`, proxy chuyển việc xử lý cho bean `FilterChainProxy`. `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên phù hợp** với request, sau đó thực thi các security filter theo thứ tự nội bộ của Spring Security.

```text
Container FilterChain
    -> [Filter của ứng dụng, tùy order]
    -> DelegatingFilterProxy("springSecurityFilterChain")
         -> FilterChainProxy
              -> SecurityFilterChain khớp request
                   -> SecurityContext / xác thực / CSRF / authorization / ...
    -> [các container filter khác, tùy order]
    -> DispatcherServlet
         -> HandlerInterceptor
         -> Controller
```

Đây là sơ đồ cấu trúc, **không ấn định** mọi filter của ứng dụng đều đứng trước hay sau security proxy. Thứ tự cụ thể cần kiểm tra ở cấu hình thực tế.

Hệ quả thực dụng:

- Nếu `AuthorizationFilter` hoặc thành phần xác thực/CSRF của Spring Security từ chối request **trước khi gọi chuỗi tiếp theo**, controller và `HandlerInterceptor` MVC sẽ không chạy cho request đó.
- `permitAll()` cho phép truy cập theo luật authorization, nhưng request **vẫn đi qua** security filter chain phù hợp. Nó khác với việc loại request khỏi security chain bằng `web.ignoring()`.
- Dữ liệu `SecurityContextHolder` không nhất thiết sẵn sàng trong *một container filter chạy trước security chain*. Một custom filter cần thông tin người dùng phải được đặt đúng giai đoạn của security chain và đúng sau cơ chế xác thực liên quan.
- Authorization cho endpoint nên được cấu hình bằng `authorizeHttpRequests` và, khi phù hợp, method security. `HandlerInterceptor` không phải cơ chế bảo vệ endpoint thay thế Spring Security: nó có thể bị bỏ qua khi request không đi vào MVC hoặc bị xử lý bởi servlet khác.

**Hai loại thứ tự cần cấu hình ở đúng nơi:**

| Muốn sắp thứ tự | Cơ chế |
| --- | --- |
| Servlet filter do container quản lý | `FilterRegistrationBean#setOrder` hoặc `@Order` trên filter được Boot đăng ký |
| Filter **bên trong** Spring Security | `HttpSecurity.addFilterBefore/addFilterAfter/addFilterAt` với filter mốc phù hợp |
| MVC interceptor | `InterceptorRegistry#order` hoặc thứ tự thêm qua `WebMvcConfigurer` |

Đừng suy ra rằng `@Order` trên một servlet filter sẽ thay đổi vị trí của nó *bên trong* `SecurityFilterChain`. Tương tự, đăng ký cùng một custom filter vừa dưới dạng container filter (ví dụ bean `@Component` được Boot auto-register), vừa qua `http.addFilterBefore(...)` có thể tạo hai đường thực thi không mong muốn. Khi muốn nó chỉ thuộc security chain, cần vô hiệu hóa đăng ký servlet container cho bean filter đó (ví dụ qua `FilterRegistrationBean#setEnabled(false)`) rồi thêm filter ở đúng chỗ trong `HttpSecurity`.

## 5. Ví dụ chạy được: Filter → Security → Interceptor → Controller

Ví dụ Java 17+, Spring Boot 3.3.x, Spring MVC và Spring Security 6.x. Mục tiêu là **quan sát đúng ranh giới**: `/hello` được phép vào controller; `/private` bị chặn bởi security trước interceptor. Cấu trúc tệp:

```text
servlet-chain-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    TraceFilter.java
    TraceInterceptor.java
    WebConfig.java
    SecurityConfig.java
    DemoController.java
```

`settings.gradle`:

```groovy
rootProject.name = 'servlet-chain-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}
```

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/demo/TraceFilter.java` — servlet filter được Boot đăng ký với container; `HIGHEST_PRECEDENCE` giúp log trước security proxy trong ví dụ này:

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {
        System.out.println("1 FILTER before " + request.getRequestURI());
        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("6 FILTER after status=" + response.getStatus());
        }
    }
}
```

`src/main/java/demo/TraceInterceptor.java` — đây là thành phần MVC, **không phải** filter của container:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

@Component
public class TraceInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) {
        System.out.println("2 INTERCEPTOR preHandle");
        return true;
    }

    @Override
    public void postHandle(HttpServletRequest request,
                           HttpServletResponse response,
                           Object handler,
                           ModelAndView modelAndView) {
        System.out.println("4 INTERCEPTOR postHandle");
    }

    @Override
    public void afterCompletion(HttpServletRequest request,
                                HttpServletResponse response,
                                Object handler,
                                Exception ex) {
        System.out.println("5 INTERCEPTOR afterCompletion");
    }
}
```

`src/main/java/demo/WebConfig.java` — chỉ gắn interceptor cho hai endpoint dùng trong bài:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final TraceInterceptor traceInterceptor;

    public WebConfig(TraceInterceptor traceInterceptor) {
        this.traceInterceptor = traceInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(traceInterceptor)
                .addPathPatterns("/hello", "/private");
    }
}
```

`src/main/java/demo/SecurityConfig.java` — chỉ `/hello` là public; endpoint còn lại yêu cầu authentication:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/hello").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/hello")
    public String hello() {
        System.out.println("3 CONTROLLER hello");
        return "Hello";
    }

    @GetMapping("/private")
    public String privateArea() {
        System.out.println("3 CONTROLLER private");
        return "Private";
    }
}
```

Từ thư mục dự án, chạy bằng Gradle đã cài sẵn hoặc Gradle wrapper nếu dự án có wrapper:

```bash
gradle bootRun
# hoặc ./gradlew bootRun (macOS/Linux)
# hoặc .\gradlew.bat bootRun (Windows PowerShell)
```

Ở terminal khác:

```bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/private
```

**Kết quả cần quan sát với `GET /hello`:** HTTP 200, body `Hello`. Các dòng `System.out.println` do mã ví dụ tạo ra theo thứ tự:

```text
1 FILTER before /hello
2 INTERCEPTOR preHandle
3 CONTROLLER hello
4 INTERCEPTOR postHandle
5 INTERCEPTOR afterCompletion
6 FILTER after status=200
```

**Kết quả cần quan sát với `GET /private` khi không gửi thông tin đăng nhập:** thông thường HTTP 401 (cấu hình `httpBasic`). Vì Spring Security chặn trước MVC, các dòng tương ứng của request này chỉ gồm:

```text
1 FILTER before /private
6 FILTER after status=401
```

Không có `INTERCEPTOR preHandle` hoặc `CONTROLLER private` của request bị từ chối. Các log riêng của Spring Boot/Spring Security có thể xen kẽ; dispatcher `ERROR` hay môi trường cấu hình khác có thể tạo lượt xử lý bổ sung, nhưng không thay đổi nguyên tắc ranh giới. Để thử đường được phép sau xác thực, cần cung cấp credentials hợp lệ theo cấu hình authentication của ứng dụng (Spring Boot có thể tạo tài khoản phát triển mặc định khi chưa định nghĩa user).

**Ý nghĩa của thí nghiệm:** Filter đặt ở container thấy được cả hai request; MVC interceptor chỉ thấy request đã đi vào chu trình xử lý MVC. Trong ví dụ, `TraceFilter` là servlet filter độc lập; nếu đưa một filter vào chính `SecurityFilterChain`, thứ tự và điều kiện chạy của nó phải được cấu hình ở `HttpSecurity`.

## 6. Các trường hợp dễ hiểu sai

### 6.1. “Filter nào cũng chạy trước mọi interceptor?”

Với **một lần dispatch đồng bộ**, các servlet filter áp dụng cho request nằm ngoài việc gọi `DispatcherServlet`; mã trước `chain.doFilter` chạy trước các hook MVC, và mã sau `chain.doFilter` thường chạy sau khi MVC kết thúc. Tuy nhiên, có nhiều filter với thứ tự khác nhau; filter có thể không áp dụng vì URL pattern/dispatcher type, có thể dừng chain, hoặc request có thể đi tới servlet khác. Không suy ra filter **nào** đứng trước security proxy chỉ từ khái niệm “Filter”.

### 6.2. “Interceptor bảo vệ API là đủ?”

Không. `HandlerInterceptor` chỉ gắn vào handler MVC được định tuyến phù hợp. Request bị từ chối ở filter, hoặc đi tới servlet không qua Spring MVC, sẽ không qua interceptor. Kiểm soát xác thực, authorization, CSRF, session và các chính sách HTTP security nên đặt ở Spring Security. Interceptor thích hợp hơn cho logic *gắn với handler MVC*, như bổ sung thông tin theo route hoặc đo thời gian xử lý MVC.

### 6.3. “`preHandle=false` hay security trả 401 thì Filter.after có chạy?”

Thông thường **có**, nếu filter dùng `try/finally` quanh `chain.doFilter` như ví dụ. `preHandle=false` dừng handler MVC; security trả 401 có thể dừng trước khi tới MVC. Cả hai vẫn có thể trả quyền điều khiển về filter bao ngoài, khiến `finally` thực thi. Ngoại lệ như tiến trình bị dừng đột ngột không thuộc luồng Java thông thường.

### 6.4. “`OncePerRequestFilter` bảo đảm một lần trong mọi trường hợp?”

Không nên hiểu tuyệt đối. Nó cung cấp cơ chế đánh dấu để tránh xử lý lặp trong phạm vi dispatch được hỗ trợ; request bất đồng bộ và dispatch lỗi `ERROR` có quy tắc riêng, chịu ảnh hưởng bởi `shouldNotFilterAsyncDispatch`, `shouldNotFilterErrorDispatch` và đăng ký dispatcher types. Đừng dùng giả định “luôn đúng một lần trong suốt toàn bộ HTTP transaction” khi xử lý async/error hoặc khi filter có nhiều cách đăng ký.

### 6.5. “Đọc body, bắt lỗi và sửa response đặt ở đâu?”

- Filter thích hợp để bọc `HttpServletRequest`/`HttpServletResponse`, nhưng đọc body trực tiếp có thể làm controller mất stream; nếu cần đọc nhiều lần, dùng wrapper/caching đúng cách.
- Ngoại lệ phát sinh **trước** `DispatcherServlet` thường không được xử lý tự động bằng `@ControllerAdvice`/`HandlerExceptionResolver` như ngoại lệ từ controller. Với lỗi authentication/authorization, dùng cơ chế của Spring Security như `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`.
- Interceptor `postHandle` không phải giải pháp chung để thay body JSON đã được `@ResponseBody` ghi; response customization cần chọn đúng tầng (message converter, `ResponseBodyAdvice`, filter/wrapper, tùy mục tiêu).
- CORS preflight phải được xử lý đúng tương quan với Spring Security; đừng chờ một MVC interceptor mới quyết định cho `OPTIONS` bị security từ chối.

### 6.6. “Tại sao cùng URL lại thấy log lặp?”

Kiểm tra `DispatcherType.REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, cấu hình dispatcher types của filter, async MVC và lần chuyển tới `/error`. Cũng kiểm tra custom filter có được auto-register ở servlet container *đồng thời* được thêm vào Spring Security chain hay không. Đừng kết luận toàn bộ log lặp là controller chạy hai lần.

## 7. Cách kiểm tra một request thực tế

Khi thứ tự trong một ứng dụng không khớp kỳ vọng, hãy xác định: (1) URL và dispatcher type; (2) container filter registrations và order; (3) proxy `springSecurityFilterChain`, danh sách/matcher của `SecurityFilterChain`; (4) filter nội bộ có dừng `chain.doFilter` hay trả lỗi; (5) request có thực sự tới `DispatcherServlet`, handler nào được `HandlerMapping` chọn; (6) interceptor có match path/handler và `preHandle` có trả `true` hay không. Log request ID xuyên qua các tầng giúp đọc đúng luồng khi có xử lý đồng thời.

Có thể dùng các điểm đặt log sau để phân biệt:

| Dấu hiệu | Suy luận trước tiên |
| --- | --- |
| Có `Filter.before` và `Filter.after`, không có `Interceptor.preHandle` | Bị chặn sớm ở filter/security, không vào MVC, hoặc interceptor không match |
| Có `Interceptor.preHandle`, không có controller | `preHandle=false`, exception trước handler, hoặc lời gọi handler không hoàn tất bình thường |
| Có controller và `afterCompletion`, không thấy `postHandle` | Có thể đường lỗi hoặc xử lý bất đồng bộ; xem exception/dispatch |
| Có `Filter.before` lặp | Có thể nhiều dispatch types hoặc đăng ký filter ở nhiều nơi; xác minh bằng request ID và `DispatcherType` |

## 8. Tự kiểm tra

1. Nếu security trả 401 trước `DispatcherServlet`, `HandlerInterceptor.preHandle` có chạy không? **Không, với request bị chặn trên nhánh đó.**
2. `@Order` của một container filter có sắp thứ tự các filter *bên trong* Spring Security không? **Không; dùng API `HttpSecurity` cho thứ tự nội bộ security chain.**
3. Vì sao `afterCompletion` phù hợp để dọn tài nguyên hơn `postHandle`? **Vì `postHandle` có thể bị bỏ qua ở đường exception; `afterCompletion` được gọi cho interceptor có `preHandle=true` sau khi MVC hoàn tất xử lý đồng bộ.**
4. Muốn bắt buộc xác thực với `/private` thì dùng interceptor hay `SecurityFilterChain`? **Dùng Spring Security; interceptor chỉ bổ trợ khi cần logic liên quan MVC.**
5. Vì sao `Filter.after` xuất hiện sau `Interceptor.afterCompletion`? **Servlet filter bao quanh lời gọi downstream bằng `chain.doFilter`; MVC hoàn tất dispatch rồi mới trả về caller trong filter.**

**Ghi nhớ:** `Filter` là ranh giới của Servlet container; `DispatcherServlet` là front controller của Spring MVC; `HandlerInterceptor` nằm bên trong MVC sau khi chọn handler. Spring Security Servlet vận hành chủ yếu qua các filter, vì vậy có thể kiểm soát request trước khi controller và MVC interceptor được gọi.
