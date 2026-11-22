# Lỗi phát sinh trong bộ lọc không tự đi qua @ControllerAdvice

> **Phạm vi:** ứng dụng **Spring MVC trên Servlet stack**, Spring Boot 3.x / Spring Security 6.x và Java 17+. Chủ đề cha: **Lỗi bảo mật**. Trọng tâm là vì sao exception phát sinh trong `Filter` hoặc `OncePerRequestFilter` không tự được `@ControllerAdvice` bắt, cách chọn cơ chế xử lý phù hợp, và sự khác nhau với lỗi xác thực/phân quyền của Spring Security.

## 1. Vấn đề thường gặp

Bạn có một `@RestControllerAdvice` với `@ExceptionHandler` để chuẩn hóa JSON lỗi. Khi controller ném `IllegalArgumentException` hoặc exception nghiệp vụ, API trả đúng cấu trúc mong muốn. Nhưng khi một **Servlet Filter** ném cùng exception, lời gọi vào `@ExceptionHandler` không xảy ra; ứng dụng có thể trả trang/JSON `/error` của Spring Boot, HTTP 500 hoặc một kết quả khác do container/gateway xử lý.

Điều này không có nghĩa `@ControllerAdvice` “không global”. Từ “global” ở đây áp dụng cho **cơ chế xử lý exception của Spring MVC**, chứ không tạo một `try/catch` ôm toàn bộ Servlet Filter Chain.

Ba câu hỏi cần xác định mỗi khi thấy lỗi:

1. **Lỗi phát sinh ở đâu?** Container, servlet filter, security filter, handler/controller hay tác vụ bất đồng bộ?
2. **Bộ xử lý nào bao quanh điểm phát sinh đó?** `HandlerExceptionResolver` của MVC, `ExceptionTranslationFilter` của Security, authentication failure handler, request-rejection handler, hay error page của container?
3. **Response đã được ghi/commit chưa?** Nếu đã commit header/body thì không thể tùy ý đổi mã HTTP hay ghi thêm body lỗi mới.

### Mục tiêu sau bài

- Đọc được luồng `FilterChain.doFilter(...)` và ranh giới `DispatcherServlet`.
- Giải thích vì sao `@ExceptionHandler` không tự bắt exception được ném **trước** lúc MVC bắt đầu xử lý.
- Phân biệt lỗi ứng dụng trong filter với `AuthenticationException`, `AccessDeniedException` và `RequestRejectedException`.
- Chọn một trong ba cách xử lý hợp lý: **phản hồi ngay trong filter**, **chuyển một lỗi ứng dụng được kiểm soát cho `HandlerExceptionResolver`**, hoặc **dùng handler chuyên trách của Spring Security**.
- Viết test chứng minh request có/không qua advice, đồng thời tránh làm lộ thông tin nhạy cảm.

## 2. Ranh giới thực thi: Filter chạy trước MVC

Một luồng điển hình của **Servlet application**:

```text
HTTP client
   |
   v
Servlet container (parse request)
   |
   +--> Servlet Filter A
   |      |
   |      +--> DelegatingFilterProxy
   |               |
   |               +--> Spring Security FilterChainProxy
   |                         |
   |                         +--> authentication/CSRF/authorization filters
   |                         +--> ExceptionTranslationFilter (chỉ một số lỗi Security)
   |               |
   +--> Servlet Filter B (nếu có, theo thứ tự đăng ký)
   |      |
   |      +--> DispatcherServlet
   |               |
   |               +--> HandlerMapping / HandlerAdapter
   |               +--> Controller / Service
   |               |
   |               +--> HandlerExceptionResolver
   |                         |
   |                         +--> @ExceptionHandler trong controller
   |                         +--> @ControllerAdvice / @RestControllerAdvice
   |
   +--> Servlet container error processing / /error (khi còn lỗi chưa xử lý)
```

*Hình là sơ đồ ý tưởng*: vị trí Filter A/B và các security filter thực tế phụ thuộc cấu hình; thứ tự `ExceptionTranslationFilter` với những filter khác cũng quan trọng. `HandlerExceptionResolver` không phải filter ở ngoài cùng; nó được `DispatcherServlet` gọi trong quy trình xử lý của MVC khi có exception thuộc trách nhiệm của servlet này.

### Tại sao `@ControllerAdvice` không tự nhận lỗi?

- `@ControllerAdvice` chứa các phương thức `@ExceptionHandler` được `ExceptionHandlerExceptionResolver` tìm và gọi như một phần của hệ thống `HandlerExceptionResolver`.
- `DispatcherServlet` gọi các resolver này đối với exception xảy ra trong quá trình nó ánh xạ, gọi hoặc xử lý một handler.
- Một custom filter có thể ném exception **trước khi gọi** `chain.doFilter(...)`. Khi đó request chưa đi vào `DispatcherServlet`, nên MVC không có cơ hội tự gọi resolver.
- Kể cả một filter ném exception **sau khi** `chain.doFilter(...)` trả về, thời điểm đó cũng đã ở ngoài phạm vi xử lý exception nội bộ của `DispatcherServlet`.
- Nếu filter tự gọi `HandlerExceptionResolver`, đó là **chuyển tiếp chủ động do lập trình viên viết**, không phải hành vi mặc định của annotation.

So sánh một đoạn mã minh họa:

```java
@Override
protected void doFilterInternal(HttpServletRequest request,
                                HttpServletResponse response,
                                FilterChain chain)
        throws ServletException, IOException {

    if (isInvalid(request)) {
        throw new InvalidRequestException("Invalid request"); // Phát sinh trong Filter
    }

    chain.doFilter(request, response); // MVC chỉ được gọi nếu request đi tới servlet
}
```

Hàm `isInvalid` và exception trên chỉ là *pseudocode minh họa*, chưa phải chương trình độc lập. Đặt `@ExceptionHandler(InvalidRequestException.class)` trong advice không khiến exception đầu tiên tự động đi qua MVC.

### Phân biệt với interceptor của MVC

Một `HandlerInterceptor` được `DispatcherServlet` gọi trong chuỗi xử lý handler. Vì vậy exception từ `preHandle`/handler thường có cơ hội đi qua `HandlerExceptionResolver` của MVC, tùy thời điểm và trạng thái response. **Servlet Filter** hoạt động ở tầng ngoài `DispatcherServlet`, khác về phạm vi xử lý lỗi.

## 3. Ma trận: loại exception nào được xử lý ở đâu?

| Nguồn lỗi | Bộ xử lý phù hợp | Có tự đi qua `@ControllerAdvice`? |
| --- | --- | --- |
| Controller hoặc service được controller gọi ném exception trong request MVC | `HandlerExceptionResolver`, `@ExceptionHandler` | **Thường có**, khi advice áp dụng và resolver xử lý được. |
| Validation của `@RequestBody` trong MVC | MVC exception resolver / `ResponseEntityExceptionHandler` | Có thể, nếu handler được cấu hình tương ứng. |
| Servlet `Filter`/`OncePerRequestFilter` tự ném runtime exception | Local handler trong filter, hoặc chủ động gọi MVC resolver; nếu bỏ ngỏ thì container/error processing | **Không tự động.** |
| `AuthenticationException` từ nhánh Security phù hợp | `AuthenticationEntryPoint` hoặc cơ chế authentication failure handler | **Không cần đi qua advice.** |
| `AccessDeniedException` phát sinh *sau* `ExceptionTranslationFilter` trong phần chain nó bao quanh | `AccessDeniedHandler` hoặc `AuthenticationEntryPoint` tùy trạng thái xác thực | **Không mặc định.** |
| `RequestRejectedException` do `HttpFirewall` từ chối request | `RequestRejectedHandler` / `FilterChainProxy` | **Không tự động.** |
| Request bị Tomcat/proxy từ chối trước ứng dụng | Container / reverse proxy | Không. |
| Exception còn lại được container dispatch đến `/error` | Error handling của container/Spring Boot (thường `BasicErrorController`) | Không có bảo đảm advice của endpoint gốc được gọi. |
| Exception từ `@Async`, thread nền, job độc lập | Handler cho async/job, logger, result/future | Không; không còn là xử lý đồng bộ của request MVC. |

**Điểm tinh tế:** `ExceptionTranslationFilter` không “bắt mọi lỗi Security”. Nó chủ yếu chuyển `AuthenticationException` và `AccessDeniedException` ném từ **đoạn chain phía sau** mà nó bao quanh thành phản hồi HTTP. Custom filter ném lỗi **trước** khi đến `ExceptionTranslationFilter` có thể nằm ngoài phạm vi `try/catch` của nó. Lỗi kiểu `IllegalArgumentException` hay `NullPointerException` cũng không trở thành lỗi 401/403 chỉ vì xảy ra trong security chain.

Một `AccessDeniedException` ném sâu từ method security trong đường gọi controller có thể được MVC resolver xử lý **trước**, nếu advice bắt loại lỗi đó; chỉ khi lỗi lan ra đến `ExceptionTranslationFilter` thì filter này mới có cơ hội xử lý. Do đó nên tránh handler tổng quát vô tình biến lỗi quyền truy cập thành HTTP 500 hoặc 200.

## 4. Demo tái hiện khác biệt: controller 400, filter không vào advice

Ví dụ dùng **một ứng dụng Spring Boot MVC**, có các dependency `spring-boot-starter-web`, `spring-boot-starter-security`; kiểm thử dùng thêm `spring-boot-starter-test`. Các class dưới đây đặt trong package `com.example.filtererrors`, mỗi code block là **một tệp Java riêng**. Chương trình chạy trong ứng dụng Spring Boot với Java 17+, không phải từng class chạy độc lập bằng `java`.

### 4.1. Lớp khởi động — `FilterErrorDemoApplication.java`

```java
package com.example.filtererrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterErrorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterErrorDemoApplication.class, args);
    }
}
```

### 4.2. Exception dùng chung — `DemoInputException.java`

```java
package com.example.filtererrors;

public final class DemoInputException extends RuntimeException {
    public DemoInputException(String message) {
        super(message);
    }
}
```

### 4.3. Controller — `DemoController.java`

```java
package com.example.filtererrors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    @GetMapping("/ok")
    public String ok() {
        return "ok";
    }

    @GetMapping("/controller-failure")
    public String controllerFailure() {
        throw new DemoInputException("Invalid controller input");
    }
}
```

### 4.4. Global advice — `ApiAdvice.java`

```java
package com.example.filtererrors;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiAdvice {

    @ExceptionHandler(DemoInputException.class)
    public ResponseEntity<Map<String, String>> handleDemoInput(DemoInputException ex) {
        return ResponseEntity.badRequest().body(Map.of(
            "code", "INVALID_INPUT",
            "message", ex.getMessage()
        ));
    }
}
```

`@RestControllerAdvice` kết hợp `@ControllerAdvice` với `@ResponseBody` để ghi kết quả vào HTTP response. Vì lỗi từ controller được chuyển cho MVC resolver, handler này sẽ trả **400 Bad Request** với body JSON. Cấu trúc và thứ tự key JSON có thể khác nhau; hai field `code` và `message` mới là hợp đồng cần kiểm tra.

### 4.5. Filter gây lỗi — `DemoFailureFilter.java`

```java
package com.example.filtererrors;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class DemoFailureFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        if ("true".equalsIgnoreCase(request.getHeader("X-Demo-Filter-Failure"))) {
            throw new DemoInputException("Invalid filter input");
        }

        chain.doFilter(request, response);
    }
}
```

Filter này cố tình ném **cùng loại exception** với controller khi client gửi header `X-Demo-Filter-Failure: true`.

### 4.6. Đăng ký filter và security — `WebConfig.java`

```java
package com.example.filtererrors;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/api/demo/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    FilterRegistrationBean<DemoFailureFilter> demoFailureFilter() {
        FilterRegistrationBean<DemoFailureFilter> registration =
            new FilterRegistrationBean<>(new DemoFailureFilter());

        registration.addUrlPatterns("/api/demo/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
        return registration;
    }
}
```

Đây là cấu hình **demo**: đường dẫn `/api/demo/**` được `permitAll` để khảo sát lỗi mà không bị màn hình đăng nhập cản trở; các request khác vẫn yêu cầu xác thực. `ERROR` dispatch được phép để error view/controller của Boot có cơ hội render kết quả. Trong ứng dụng thật, cần thiết kế quyền cho các dispatch theo kiến trúc cụ thể, không chỉ sao chép rule minh họa.

**Tránh đăng ký filter hai lần:** `DemoFailureFilter` không gắn `@Component` hay một `@Bean` riêng. `FilterRegistrationBean` ở trên là đường đăng ký servlet filter duy nhất. Nếu đồng thời tạo một Filter bean tự đăng ký và thêm nó vào `http.addFilterBefore(...)`, filter có thể chạy ở cả Servlet chain và Security chain, làm dấu vết lỗi khó hiểu.

### 4.7. Thử bằng curl

Chạy từ project Spring Boot đã có Gradle wrapper:

```bash
./gradlew bootRun

# Route bình thường
curl -i http://localhost:8080/api/demo/ok

# Exception từ controller: advice bắt được
curl -i http://localhost:8080/api/demo/controller-failure

# Exception từ filter: advice không tự bắt được
curl -i -H 'X-Demo-Filter-Failure: true' \
  http://localhost:8080/api/demo/ok
```

Kết quả mong đợi **theo luồng xử lý**:

| Request | Kết quả |
| --- | --- |
| `GET /api/demo/ok` | 200, body `ok`. |
| `GET /api/demo/controller-failure` | 400, JSON chứa `"code":"INVALID_INPUT"` từ `ApiAdvice`. |
| `GET /api/demo/ok` kèm header cố ý gây lỗi filter | **Không chạy `ApiAdvice`**; nếu không có handler khác, thường là 500 do container/`/error`. Body và mã cụ thể phụ thuộc cấu hình error dispatch. |

Lỗi filter minh họa là **lỗi do ứng dụng cố tình ném**, không phải lỗi xác thực. Nếu bản ghi lại cho thấy cả hai request trả cùng một JSON, cần kiểm tra xem có một handler ngoài MVC nào đã được cấu hình hay không; đừng kết luận `@ControllerAdvice` tự bao phủ tất cả filter.

## 5. Cách xử lý A — filter tự trả lỗi (thường đơn giản nhất)

Nếu filter có trách nhiệm kiểm tra một điều kiện rõ ràng, ví dụ header bắt buộc, và có thể quyết định response ngay, hãy **viết status + body một lần, rồi `return`**, không ném exception để hy vọng MVC bắt.

Đây là **phiên bản thay thế** của `DemoFailureFilter.java` trong demo, dùng Jackson `ObjectMapper` do Spring Boot cấu hình sẵn:

```java
package com.example.filtererrors;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

public final class DemoFailureFilter extends OncePerRequestFilter {

    private final ObjectMapper objectMapper;

    public DemoFailureFilter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        if ("true".equalsIgnoreCase(request.getHeader("X-Demo-Filter-Failure"))) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());

            objectMapper.writeValue(response.getOutputStream(), Map.of(
                "code", "INVALID_INPUT",
                "message", "Invalid filter input"
            ));
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Đồng thời **thay thế duy nhất bean đăng ký filter** trong `WebConfig` bằng phương thức sau, còn bean `SecurityFilterChain` giữ nguyên:

```java
@Bean
FilterRegistrationBean<DemoFailureFilter> demoFailureFilter(ObjectMapper objectMapper) {
    FilterRegistrationBean<DemoFailureFilter> registration =
        new FilterRegistrationBean<>(new DemoFailureFilter(objectMapper));
    registration.addUrlPatterns("/api/demo/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
    return registration;
}
```

Đoạn method thứ hai đặt trong `WebConfig`, cần import `com.fasterxml.jackson.databind.ObjectMapper`. Đây là **mẫu thay thế**, không khai báo song song hai bean cùng tên.

Sau khi sửa, request gây lỗi filter sẽ trả **400** với hai field JSON thống nhất về mặt hợp đồng. Lúc này `ApiAdvice` **vẫn không được gọi**: filter tự xử lý ngay tại nguồn.

**Lưu ý quan trọng:**

- `response.setStatus(...)` khác `response.sendError(...)`: `sendError` có thể kích hoạt cơ chế error page/`ERROR` dispatch của container; đó không phải lời gọi trực tiếp vào advice. Chọn cách dựa trên mong muốn response.
- Chỉ ghi body nếu chưa commit response; không cố ghi tiếp sau khi output stream đã bị đóng hoặc đã trả dữ liệu cho client.
- Sau khi đã xử lý lỗi, phải `return`; gọi tiếp `chain.doFilter(...)` có thể làm controller viết lần thứ hai.
- Tránh dựng chuỗi JSON bằng cách nối dữ liệu chưa escape; dùng serializer. Không trả nguyên `ex.getMessage()` cho client nếu chuỗi đó có thể chứa thông tin nội bộ.
- Không tự biến mọi exception ngoài dự kiến thành 400; lỗi lập trình, kết nối DB hay I/O thường không phải “bad request”.

## 6. Cách xử lý B — chủ động ủy quyền cho HandlerExceptionResolver

Khi cần **tái sử dụng đúng một định dạng lỗi MVC** cho một exception *ứng dụng* phát sinh trong filter, có thể gọi `HandlerExceptionResolver` một cách tường minh. Cách này hữu ích khi đã có `@RestControllerAdvice` tương ứng, nhưng cần hiểu giới hạn của resolver.

Thay **`DemoFailureFilter.java`** bằng phiên bản dưới đây (không áp dụng đồng thời với cách A):

```java
package com.example.filtererrors;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerExceptionResolver;
import org.springframework.web.servlet.ModelAndView;

public final class DemoFailureFilter extends OncePerRequestFilter {

    private final HandlerExceptionResolver resolver;

    public DemoFailureFilter(HandlerExceptionResolver resolver) {
        this.resolver = resolver;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        if ("true".equalsIgnoreCase(request.getHeader("X-Demo-Filter-Failure"))) {
            DemoInputException exception =
                new DemoInputException("Invalid filter input");

            ModelAndView handled =
                resolver.resolveException(request, response, null, exception);

            if (handled == null) {
                throw exception; // Resolver không xử lý được: để lỗi lan ra ngoài
            }
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Và thay bean đăng ký trong `WebConfig`:

```java
@Bean
FilterRegistrationBean<DemoFailureFilter> demoFailureFilter(
        @Qualifier("handlerExceptionResolver") HandlerExceptionResolver resolver) {

    FilterRegistrationBean<DemoFailureFilter> registration =
        new FilterRegistrationBean<>(new DemoFailureFilter(resolver));
    registration.addUrlPatterns("/api/demo/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
    return registration;
}
```

Trong `WebConfig` thêm import `org.springframework.beans.factory.annotation.Qualifier` và `org.springframework.web.servlet.HandlerExceptionResolver`.

**Cơ chế:**

1. Filter thấy điều kiện lỗi do chính nó phát hiện.
2. Filter tạo `DemoInputException`.
3. Lời gọi `resolver.resolveException(request, response, null, exception)` **chủ động** kích hoạt cơ chế resolver.
4. Nếu `@RestControllerAdvice` có global `@ExceptionHandler(DemoInputException.class)` phù hợp, resolver có thể ghi response JSON 400, trả một `ModelAndView` biểu thị đã xử lý, và filter dừng.
5. Nếu resolver trả `null`, nghĩa là **chưa xử lý**, nên ví dụ ném lại exception để không âm thầm làm request thất bại với 200.

### Giới hạn của cách B

- Đối số `handler = null` vì filter chưa có `HandlerMethod` do MVC chọn. Handler `@ExceptionHandler` ở controller cụ thể không có đủ ngữ cảnh để hoạt động; các `@ControllerAdvice` giới hạn theo package, annotation hoặc class cũng có thể không áp dụng khi không xác định controller.
- Resolver có thể trả về một `ModelAndView` cần **render view**; gọi trực tiếp từ filter không bảo đảm toàn bộ quá trình render HTML được thực hiện như trong `DispatcherServlet`. Mẫu ở trên phù hợp hơn với `@RestControllerAdvice` trả `ResponseEntity`/JSON.
- Handler có thể phụ thuộc request attributes vốn chỉ được khởi tạo trong MVC; cần kiểm thử thực tế. Không suy rằng mọi handler MVC sẽ hoạt động tương tự khi gọi trước MVC.
- Không nên bọc toàn bộ `chain.doFilter(...)` trong `catch (Exception ex) { resolver.resolveException(...) }`: như vậy bạn có thể chặn nhầm lỗi xác thực, lỗi phân quyền, lỗi IO hoặc lỗi lập trình từ các tầng phía sau.
- Đừng chuyển `AccessDeniedException`, `AuthenticationException` hay mọi loại runtime exception sang resolver chỉ để có JSON đồng nhất. Hành vi 401/403, challenge header và cơ chế bảo mật có thể bị phá vỡ.

## 7. Cách xử lý C — dùng cơ chế lỗi của Spring Security

`@ControllerAdvice` không phải nơi chính để chuẩn hóa lỗi **xác thực và phân quyền** nảy sinh trong Spring Security filter chain. Mỗi loại lỗi có cơ chế riêng:

### 7.1. AuthenticationEntryPoint: chưa xác thực hoặc xác thực không hợp lệ

`AuthenticationEntryPoint` được dùng khi hệ thống cần bắt đầu luồng xác thực. Tùy ứng dụng, phản hồi có thể là:

- **401 Unauthorized** với `WWW-Authenticate` phù hợp, ví dụ HTTP Basic hoặc Bearer token.
- **302 Redirect** tới trang đăng nhập cho web app dùng form login.
- Cơ chế khác nếu đã cấu hình scheme đặc thù.

Một số authentication filter, ví dụ form login filter, có **`AuthenticationFailureHandler`** riêng để xử lý lỗi xác thực tại filter đó. Không giả định mọi `AuthenticationException` đều luôn đi qua `ExceptionTranslationFilter`.

### 7.2. AccessDeniedHandler: đã xác thực nhưng thiếu quyền

`AccessDeniedHandler` xử lý `AccessDeniedException` khi `ExceptionTranslationFilter` quyết định request thuộc trường hợp bị từ chối quyền, thường là **403 Forbidden**. Với principal ẩn danh/chưa xác thực, filter có thể dùng `AuthenticationEntryPoint` thay vì `AccessDeniedHandler`.

Khi tùy chỉnh `http.exceptionHandling(...)`, kiểm tra hợp đồng của từng cơ chế đăng nhập: HTTP Basic/Bearer thường cần header challenge chính xác; việc thay entry point bằng đoạn `response.setStatus(401)` trống có thể khiến client không biết cách xác thực.

### 7.3. HttpFirewall và RequestRejectedHandler

Lỗi bị từ chối vì URI/method/header bất thường có thể phát sinh ngay tại `StrictHttpFirewall` dưới dạng `RequestRejectedException`. `FilterChainProxy` có cơ chế `RequestRejectedHandler` để xử lý. Nó **khác** `AccessDeniedException` (đã tới kiểm tra quyền) và thường xảy ra trước việc chọn, chạy bộ lọc MVC/controller. Đừng gán mọi lỗi request rejection cho advice.

### 7.4. Ví dụ cấu hình phù hợp

Với Basic Authentication, giữ entry point mặc định của `httpBasic(...)` (để giữ challenge header), rồi chỉ tùy chỉnh phản hồi thiếu quyền khi ứng dụng thật sự cần:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .exceptionHandling(ex -> ex
            .accessDeniedHandler((request, response, denied) -> {
                response.sendError(HttpServletResponse.SC_FORBIDDEN);
            })
        );

    return http.build();
}
```

Đoạn code trên là **một lựa chọn thay thế cho bean `SecurityFilterChain`** của demo, không đăng ký thêm một chain trùng tất cả request. Cần import `jakarta.servlet.http.HttpServletResponse` nếu sử dụng. `sendError(403)` có thể dẫn tới `/error`; đây chỉ là ví dụ status, không chủ đích tạo JSON chuẩn hóa. Với API JWT/OAuth2 Resource Server, hãy giữ hoặc tùy chỉnh entry point và denied handler của resource server để phản hồi chuẩn Bearer, thay vì sao chép thiết lập Basic của ví dụ.

**Vấn đề thứ tự:** `ExceptionTranslationFilter` chỉ xử lý exception từ phần chain mà lời gọi `chain.doFilter` của nó bao quanh. Đưa custom filter ra trước nó (hoặc đăng ký ở Servlet container bên ngoài security chain) rồi ném `AccessDeniedException` **không bảo đảm** filter dịch lỗi này. Không đổi thứ tự security filter tùy tiện chỉ để “giải quyết lỗi 500”; xác định đúng trách nhiệm và vị trí trước.

## 8. Spring Boot /error không đồng nghĩa với @ControllerAdvice

Trong ứng dụng Servlet, Spring Boot thường cấu hình đường dẫn `/error`, dùng `BasicErrorController` và error attributes để tạo phản hồi cho những lỗi không được xử lý ở nơi phát sinh. Đó là *cơ chế dự phòng* được container kích hoạt khi request kết thúc với lỗi hoặc `sendError`, khác với `ExceptionHandlerExceptionResolver` trực tiếp xử lý exception của controller gốc.

Một số điểm dễ nhầm:

- Khi exception đi ra ngoài filter mà chưa được xử lý, **container** có thể gửi một `ERROR` dispatch đến `/error`. Lúc đó client nhận JSON/HTML lỗi của Boot, mặc dù `@ExceptionHandler` cho exception nguồn chưa từng chạy.
- `@ResponseStatus` hoặc `ResponseStatusException` được dùng trong MVC không bảo đảm khi ném từ mọi Servlet Filter sẽ được MVC resolver tự diễn giải.
- `OncePerRequestFilter` có quy tắc riêng cho dispatcher type. Mặc định `shouldNotFilterErrorDispatch()` trả `true`, nhưng việc filter có tham gia `ERROR` dispatch còn phụ thuộc kiểu đăng ký và servlet container. Không khẳng định rằng mọi filter đều được gọi lại đúng một lần cho toàn bộ các dispatch.
- Nếu security chặn `ERROR` dispatch hoặc chính đường `/error`, lỗi ban đầu có thể bị che bởi 401/403 mới. Trong Spring Security có `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` khi chính sách cho phép hiển thị error page; cần đặt rule trước `anyRequest()`.
- Nếu response đã commit, cơ chế error dispatch không thể viết lại header/body một cách an toàn.

**Chẩn đoán đúng:** nếu `@ExceptionHandler` không log gì, nhưng `/error` trả JSON, trước hết xác định lỗi đã xảy ra ở filter/container nào và có đi qua `DispatcherServlet` ở request ban đầu không. Đừng tạo một `@ExceptionHandler(Exception.class)` cực rộng để “chữa” mọi 500; nó không mở rộng phạm vi ra ngoài MVC.

## 9. Checklist xử lý lỗi chuẩn, nhất quán và an toàn

### 9.1. Khi thiết kế

| Trường hợp | Hướng ưu tiên | Lưu ý |
| --- | --- | --- |
| Controller/service ném exception nghiệp vụ | `@RestControllerAdvice` + `@ExceptionHandler` cụ thể | Giữ status đúng và không lộ chi tiết nội bộ. |
| Filter tự kiểm tra header/metadata/request và biết rõ lỗi | Trả status/body trực tiếp, `return` | Có thể dùng helper serializer dùng chung. |
| Filter có exception ứng dụng cần tái dùng policy JSON từ MVC | Ủy quyền `HandlerExceptionResolver` cho loại exception đã định nghĩa | Test trường hợp `handler=null` và resolver không xử lý. |
| HTTP authentication/authorization | `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, `AccessDeniedHandler` | Tôn trọng scheme, headers và trạng thái xác thực. |
| HttpFirewall từ chối request | `RequestRejectedHandler` | Không biến request bất thường thành “permission denied”. |
| Lỗi nền, lỗi không thuộc request | Exception handler của task/executor/job | Tách khỏi Servlet request lifecycle. |
| Lỗi không được xử lý | `/error`, error attributes / log / giám sát | Không dựa vào đây cho mọi hợp đồng API nghiệp vụ. |

Nếu nhiều tầng phải trả cùng cấu trúc JSON, tạo **một model lỗi và một utility viết response** có thể được cả advice, entry point và filter handler sử dụng. Tránh “dồn” mọi error vào advice bằng cách thay đổi luồng Security thiếu kiểm soát.

### 9.2. Khi xử lý ngay trong filter

1. Chỉ bắt và xử lý lỗi mà filter **sở hữu**. Giữ logic fail-fast dễ đoán.
2. Kiểm tra `response.isCommitted()` nếu đường xử lý có khả năng đã ghi dữ liệu; không cố đổi status/body sau khi commit.
3. Chọn status có nghĩa: 400 cho request sai cú pháp/đầu vào, 401 cho thiếu xác thực phù hợp scheme, 403 cho thiếu quyền; 500 cho lỗi ngoài dự kiến. Đây là **định hướng**, thực tế còn phụ thuộc chính sách HTTP của API.
4. Trả nội dung có cấu trúc ổn định; không trả stack trace, token, cookie, SQL error hoặc thông tin hệ thống.
5. Ngừng filter chain sau khi ghi lỗi. Nếu không xử lý được exception, đừng nuốt lỗi rồi để request trả 200 giả.
6. Không bắt toàn bộ `RuntimeException` từ `chain.doFilter(...)` chỉ để trả một loại JSON; như vậy dễ che các lỗi bảo mật phía sau.
7. Xem xét `REQUEST`, `ASYNC` và `ERROR` dispatcher types khi đăng ký filter; tránh filter chạy lặp ngoài dự kiến.
8. Kiểm tra cả phía trước filter và phía sau: proxy/container có thể trả lỗi trước khi Spring Boot kịp xử lý.

### 9.3. Khi phát hiện lỗi 401/403/500 khó hiểu

- Bật log có chọn lọc cho `org.springframework.security` và filter của bạn ở môi trường kiểm thử, kiểm tra exception class, stack trace và lớp đầu tiên ném lỗi.
- Xác định filter thuộc **Servlet filter chain** hay **Spring Security FilterChainProxy**, được đăng ký/ordered như thế nào và có bị đăng ký hai lần không.
- Kiểm tra advice nào có `@ExceptionHandler` phù hợp; xem nó có bị giới hạn bởi `basePackages`, `annotations` hoặc `assignableTypes` không.
- Phân biệt lỗi security được trả bởi entry point, denied handler, authentication failure handler, request rejection handler với lỗi được container/`/error` render.
- Kiểm tra các dispatch tiếp theo, response commit và việc có filter/log ghi body hai lần.
- Ghi correlation ID và loại lỗi theo mức phù hợp; loại bỏ dữ liệu nhạy cảm khỏi log.

## 10. Kiểm thử: dùng cả MVC test và HTTP thật

**Lưu ý về test:** `MockMvc` giúp kiểm tra controller, advice và nhiều filter đã đăng ký, nhưng không thay thế hoàn toàn servlet container. Nếu filter ném exception không xử lý, `MockMvc` có thể **ném exception lên test** thay vì mô phỏng chính xác trang `/error` hoặc status 500 mà Tomcat thật trả. Vì vậy test cần tách ba mức:

1. **MVC layer:** gọi endpoint controller và assert `400` + body từ `ApiAdvice`.
2. **Filter layer:** tạo request vào filter và assert nó trả lỗi/ủy quyền resolver đúng, hoặc exception lan ra khi chưa xử lý.
3. **Live HTTP integration:** chạy Spring Boot với embedded server, gọi `curl` hoặc một HTTP client thực tế để quan sát error dispatch, security headers, status và content type.

Ví dụ test sau chỉ áp dụng **sau khi triển khai cách A hoặc B**, lúc lỗi trong filter đã có handler trả HTTP 400:

```java
package com.example.filtererrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterErrorIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerExceptionIsResolvedByAdvice() throws Exception {
        mvc.perform(get("/api/demo/controller-failure"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void filterExceptionReturnsConfiguredJson() throws Exception {
        mvc.perform(get("/api/demo/ok")
                .header("X-Demo-Filter-Failure", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
```

Điều kiện: dự án có `spring-boot-starter-test` và ứng dụng demo nằm cùng package hoặc package cha của test. Test thứ hai **không nên chạy như kỳ vọng 400 trên phiên bản ban đầu**, bởi filter ban đầu cố ý ném lỗi chưa xử lý. Với cách A, test chứng minh filter tự trả JSON; với cách B, nó chứng minh resolver được gọi chủ động. Test này **không chứng minh `ApiAdvice` được gọi ở cách A** — muốn kiểm tra nơi xử lý, dùng instrumentation/spy hoặc log có chủ đích.

### Ma trận tình huống cần xác minh

| Tình huống | Điều cần xác minh |
| --- | --- |
| Request hợp lệ, filter tiếp tục chain | Endpoint bình thường chạy; không có double invocation. |
| Request bị filter từ chối | Đúng status/body; controller không chạy; sau khi ghi lỗi không gọi tiếp chain. |
| Exception từ controller | Resolver/advice xử lý đúng; không bị filter “nuốt”. |
| Thiếu xác thực | Đúng entry point, challenge header/redirect phù hợp. |
| Đã xác thực nhưng thiếu quyền | Đúng denied handler; không trả 200 hoặc làm lộ resource. |
| Malformed URL bị firewall từ chối | Không vào controller; có handler và log phù hợp; trạng thái phụ thuộc stack. |
| Lỗi không dự kiến trong filter | Không giả thành lỗi input; có log, giám sát và phản hồi 5xx phù hợp. |
| Lỗi trong `ERROR` dispatch / response đã commit | Không lặp vô hạn, không ghi response hai lần. |

## 11. Các hiểu lầm phổ biến

**“Thêm `@ExceptionHandler(Exception.class)` là bắt được mọi lỗi.”** Sai. Handler này vẫn thuộc MVC. Ngoài ra nó có thể bắt nhầm security exception đi qua MVC, làm sai status và che lỗi.

**“Filter ném `ResponseStatusException(HttpStatus.BAD_REQUEST)` là chắc chắn trả 400.”** Không có bảo đảm như vậy nếu exception không vào `ResponseStatusExceptionResolver`. Đường xử lý phụ thuộc bộ lọc, container và error page.

**“Dùng `@Component` cho filter là đủ để Spring MVC quản lý lỗi của filter.”** Sai. `@Component` chỉ tham gia tạo/đăng ký bean; nó không mở rộng phạm vi `DispatcherServlet`. Với Spring Boot, `Filter` bean còn có thể được tự đăng ký ở servlet container.

**“`ExceptionTranslationFilter` xử lý mọi `RuntimeException` trong Security.”** Sai. Nó xử lý các loại lỗi xác thực và thiếu quyền thích hợp từ đoạn chain được bao quanh; lỗi ứng dụng bất kỳ cần handler của chính nó.

**“Sau khi `response.sendError(...)` thì `@ControllerAdvice` sẽ chạy.”** Không. `sendError` thường yêu cầu error handling của servlet container, có thể dẫn tới `/error`; đó là một dispatch khác.

**“Cứ bắt mọi lỗi trong filter rồi gọi `resolver.resolveException`.”** Nguy hiểm: sẽ can thiệp lỗi chưa xác thực, thiếu quyền, IO và lỗi ứng dụng phía sau, nhất là khi response đã commit. Chỉ ủy quyền những lỗi đã xác định rõ và kiểm thử kết quả.

**“Nếu controller advice không chạy thì Spring Boot không xử lý lỗi.”** Không đúng. Container và `/error` có thể tạo response dự phòng, nhưng không nên nhầm với hợp đồng lỗi nghiệp vụ của MVC.

## 12. Câu hỏi tự kiểm tra

1. Exception được ném **trước** `chain.doFilter` trong Servlet Filter. Tại sao `@ControllerAdvice` không tự nhận?
2. Điều gì xảy ra nếu `HandlerExceptionResolver.resolveException(...)` trả `null`?
3. Khi ứng dụng dùng HTTP Basic, vì sao không nên tùy ý thay `AuthenticationEntryPoint` bằng đoạn mã chỉ trả status 401?
4. Vì sao một `AccessDeniedException` ném trong custom filter có thể không được `ExceptionTranslationFilter` bắt?
5. Sự khác nhau giữa response lỗi do `ApiAdvice` tạo và response từ Spring Boot `/error` là gì?
6. Làm sao chứng minh một test `MockMvc` chưa phản ánh hoàn toàn behavior trên embedded Tomcat?
7. Tại sao không nên bắt `Exception` bao quanh toàn bộ `chain.doFilter(...)` rồi luôn trả 400?

**Gợi ý:** (1) chưa vào vùng xử lý của MVC; (2) lỗi chưa được giải quyết, phải có đường fallback/throw; (3) có thể đánh mất `WWW-Authenticate`; (4) vị trí filter và phạm vi `chain.doFilter` của `ExceptionTranslationFilter`; (5) resolver xử lý exception nguồn so với error dispatch dự phòng; (6) so sánh live HTTP trên container thật; (7) che lỗi Security và lỗi server, dẫn đến status sai hoặc response bị ghi hai lần.

## Tài liệu chính thức

- Spring Framework — xử lý exception bằng `HandlerExceptionResolver`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — `@ControllerAdvice` / `@RestControllerAdvice`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework — Servlet request processing: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/sequence.html
- Spring Framework — `OncePerRequestFilter` API: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security — Servlet architecture and exception translation: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — RequestRejectedHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/RequestRejectedHandler.html
- Spring Security — HTTP authorization and ERROR dispatcher: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot 3.3 — Servlet web error handling: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
