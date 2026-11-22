# Vì sao `@ControllerAdvice` không tự xử lý mọi lỗi phát sinh trong `Filter`

## 1. Câu trả lời cốt lõi

Trong ứng dụng **Spring MVC chạy trên Servlet**, `@ControllerAdvice` (hoặc `@RestControllerAdvice`) tham gia cơ chế xử lý ngoại lệ của **Spring MVC**, chủ yếu thông qua các `HandlerExceptionResolver` do `DispatcherServlet` gọi khi xử lý request. Trong khi đó, một Servlet `Filter` nằm **bên ngoài luồng gọi của `DispatcherServlet`**. Nếu filter ném exception trước khi chuyển request vào MVC, không có bước nào tự động đưa exception ấy vào `@ExceptionHandler` của advice.

Điều này không có nghĩa `@ControllerAdvice` chỉ bắt exception được ném trực tiếp trong method của controller: MVC còn có thể chuyển cho các resolver exception từ một số giai đoạn khác của quá trình xử lý MVC. Giới hạn quan trọng là **exception phải đi qua cơ chế resolver của MVC**. Tên “global exception handler” thường dùng cho `@ControllerAdvice` chỉ có nghĩa phạm vi nhiều controller trong MVC, không phải một trình bắt lỗi toàn cục cho cả Servlet container và mọi filter.

`@RestControllerAdvice` tương đương `@ControllerAdvice` kết hợp hành vi `@ResponseBody`; nó tiện cho API trả JSON, nhưng **không mở rộng ranh giới bắt exception**.

## 2. Request đi qua những lớp nào?

Một luồng request Servlet điển hình:

```text
Client
  |
  v
Servlet container (Tomcat/Jetty/...)
  |
  +--> Servlet Filter A (có thể do ứng dụng tự đăng ký)
  |
  +--> DelegatingFilterProxy("springSecurityFilterChain")
  |      |
  |      +--> FilterChainProxy: các filter của Spring Security
  |             ... -> ExceptionTranslationFilter -> AuthorizationFilter -> ...
  |
  +--> Servlet Filter B (nếu được đăng ký ở vị trí này)
  |
  v
DispatcherServlet (Spring MVC)
  |
  +--> HandlerMapping / HandlerAdapter
  |
  +--> Controller và các MVC interceptor
  |
  +--> Khi MVC cần xử lý exception:
         HandlerExceptionResolverComposite
           -> ExceptionHandlerExceptionResolver
                -> @ExceptionHandler tại controller / @ControllerAdvice
           -> các resolver khác tùy cấu hình
```

Sơ đồ biểu diễn **ranh giới trách nhiệm**, không cam kết rằng mọi ứng dụng có đúng thứ tự Filter A/B như trên. Thứ tự thực tế phụ thuộc cấu hình `FilterRegistrationBean`, container, `SecurityFilterChain` và cách đăng ký filter. `DelegatingFilterProxy` là một Servlet filter làm cầu nối đến chuỗi filter bảo mật; nó không biến mọi Servlet filter thành một phần của MVC.

### Hai luồng lỗi khác nhau

1. **Controller ném exception:** request đã vào `DispatcherServlet`; nếu MVC tìm được resolver phù hợp, method `@ExceptionHandler` có thể tạo response. Exception đã được giải quyết thường không tiếp tục nổi ra ngoài filter chain.
2. **Filter ném exception trước `chain.doFilter(...)`:** request còn chưa đến `DispatcherServlet`. Exception thoát qua các filter phía ngoài hoặc về container; Spring MVC không có cơ hội tự động gọi advice.
3. **Filter ném exception sau `chain.doFilter(...)`:** MVC có thể đã hoàn thành response. Exception phát sinh sau đó vẫn nằm ngoài phạm vi bắt lỗi tự động của advice; nếu response đã *committed*, việc đổi status/header/body còn bị hạn chế.

Chiều gọi rất quan trọng: filter gọi `chain.doFilter(...)` để đi xuống tầng tiếp theo, rồi stack quay ngược trở lại. Một `try/catch` ở filter phía ngoài có thể bắt exception nổi lên từ phía trong; `@ControllerAdvice` nằm trong MVC không thể tự bắt exception phát sinh ở tầng gọi phía ngoài.

## 3. Các trường hợp dễ nhầm

| Vị trí phát sinh / cách xử lý | `@ControllerAdvice` có tự xử lý? | Nơi xử lý phù hợp |
| --- | --- | --- |
| Controller ném `IllegalArgumentException` và MVC có `@ExceptionHandler` phù hợp | **Có thể có** | MVC `@ExceptionHandler` / `HandlerExceptionResolver` |
| MVC phát sinh lỗi mapping, binding, validation trong giai đoạn resolver hỗ trợ | **Tùy loại lỗi và resolver** | Cấu hình xử lý lỗi MVC |
| Servlet filter tự ném `RuntimeException` trước `chain.doFilter` | **Không** | Chính filter, filter bao ngoài hoặc container/error dispatch |
| Servlet filter tự ném exception sau khi `chain.doFilter` trả về | **Không** | Filter/container; kiểm tra `response.isCommitted()` |
| Lỗi authentication trong Spring Security | **Không mặc định qua advice** | Authentication filter/failure handler hoặc `AuthenticationEntryPoint` |
| `AccessDeniedException` trong phần chuỗi được `ExceptionTranslationFilter` bao quanh | **Không cần advice** | `AccessDeniedHandler` hoặc `AuthenticationEntryPoint`, tùy trạng thái xác thực |
| Filter gọi `response.sendError(...)` mà không ném exception | **Không** | Servlet container có thể thực hiện `ERROR` dispatch, ví dụ sang `/error` |
| Filter **chủ động gọi** `HandlerExceptionResolver.resolveException(...)` | **Có thể**, nếu resolver phù hợp | Cơ chế cầu nối được lập trình tường minh, không phải mặc định |

Đặc biệt, HTTP `401` và `403` thường do tầng bảo mật tạo ra; không nên suy luận rằng thiếu một method `@ExceptionHandler` là nguyên nhân của mọi phản hồi lỗi bảo mật.

## 4. Ví dụ Spring Boot 3.3.x + Java 17+: cùng exception, kết quả khác nhau

Ví dụ sau là một ứng dụng Spring Boot độc lập trong một file Java. Mục tiêu là so sánh `IllegalStateException` phát sinh trong controller với cùng loại exception phát sinh ở Servlet filter. Cần dự án Spring Boot với Gradle wrapper và hai dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Tạo `src/main/java/demo/FilterAdviceApplication.java`:

```java
package demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class FilterAdviceApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterAdviceApplication.class, args);
    }

    // Cho phép mọi GET trong ví dụ để quan sát riêng ranh giới MVC/Filter.
    @Bean
    SecurityFilterChain securityChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                   .build();
    }

    @Bean
    FilterRegistrationBean<OncePerRequestFilter> demoFilter() {
        var registration = new FilterRegistrationBean<OncePerRequestFilter>();
        registration.setFilter(new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain) throws ServletException, IOException {
                if ("/demo/filter".equals(request.getRequestURI())) {
                    throw new IllegalStateException("from filter");
                }
                chain.doFilter(request, response);
            }
        });
        registration.addUrlPatterns("/demo/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @RestController
    public static class DemoController {
        @GetMapping("/demo/controller")
        public String controllerFailure() {
            throw new IllegalStateException("from controller");
        }

        @GetMapping("/demo/filter")
        public String filterFailure() {
            return "This method is never reached.";
        }

        @GetMapping("/demo/ok")
        public String ok() {
            return "ok";
        }
    }

    @RestControllerAdvice
    public static class ApiAdvice {
        @ExceptionHandler(IllegalStateException.class)
        public ResponseEntity<ApiError> onIllegalState(
                IllegalStateException exception) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new ApiError("advice", exception.getMessage()));
        }
    }

    public record ApiError(String source, String message) {}
}
```

Chạy bằng `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`), sau đó gọi:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/demo/ok
curl -i -H "Accept: application/json" http://localhost:8080/demo/controller
curl -i -H "Accept: application/json" http://localhost:8080/demo/filter
```

Kết quả cần quan sát:

- `/demo/ok` trả HTTP `200`, body `ok`: filter gọi tiếp chain và controller chạy bình thường.
- `/demo/controller` trả HTTP `500`, body JSON từ advice, tương đương `{"source":"advice","message":"from controller"}` (thứ tự thuộc tính JSON không quan trọng).
- `/demo/filter` phát sinh lỗi trước MVC, thường được container/Spring Boot chuyển thành HTTP `500` qua luồng lỗi mặc định. **Body không phải đối tượng `ApiError` do `ApiAdvice` tạo**. Hình dạng response lỗi mặc định tùy Spring Boot, content negotiation và cấu hình `/error`, nên không giả định chính xác body của endpoint này.

Trong ví dụ, `registration.setOrder(Ordered.HIGHEST_PRECEDENCE)` đặt filter demo rất sớm. Mục đích là chủ động ném exception ngoài MVC. Nó không phải khuyến nghị dùng thứ tự này cho filter bảo mật trong ứng dụng thật.

### Kiểm chứng qua HTTP integration test

Với dependency `spring-boot-starter-test` ở trên, tạo `src/test/java/demo/FilterAdviceApplicationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterAdviceApplicationTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void mvcAdviceDoesNotAutomaticallyHandleFilterExceptions() {
        ResponseEntity<String> mvc =
                http.getForEntity("/demo/controller", String.class);
        assertThat(mvc.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(mvc.getBody()).contains("\"source\":\"advice\"");
        assertThat(mvc.getBody()).contains("from controller");

        ResponseEntity<String> filter =
                http.getForEntity("/demo/filter", String.class);
        assertThat(filter.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(String.valueOf(filter.getBody()))
                .doesNotContain("\"source\":\"advice\"");
    }
}
```

Chạy `./gradlew test` (hoặc `.\gradlew.bat test` trên Windows). Kiểm thử qua HTTP server thực giúp quan sát Servlet container và error dispatch. Khi chỉ dùng `MockMvc` không có container thật, exception từ filter có thể nổi thẳng ra phép gọi test thay vì tự biến thành JSON `/error`; vì vậy không nên lấy hành vi của một mock filter chain làm cam kết về response HTTP thực tế.

## 5. Spring Security xử lý những lỗi nào?

Trong Spring Security Servlet, cơ chế đáng nhớ là **`ExceptionTranslationFilter`**, chuyên chuyển một số **security exception** thành hành động HTTP:

- `AuthenticationException`: thường khởi động `AuthenticationEntryPoint` để yêu cầu người dùng xác thực. Với API, điều này thường có thể dẫn đến HTTP `401`; với form login có thể là redirect.
- `AccessDeniedException` khi user **đã được xác thực** nhưng thiếu quyền: chuyển cho `AccessDeniedHandler`, thường là HTTP `403`.
- `AccessDeniedException` khi request **chưa được xác thực đầy đủ**, ví dụ principal anonymous: `ExceptionTranslationFilter` có thể khởi động `AuthenticationEntryPoint` thay vì mặc định trả `403`.

Nhưng `ExceptionTranslationFilter` **không phải trình bắt mọi exception**. Nó xử lý các loại exception được thiết kế cho authentication/authorization và chỉ quan sát được exception đi qua đoạn `chain.doFilter(...)` mà nó bao quanh. Ví dụ, một custom JWT filter nằm **trước** nó và tự ném `AuthenticationException` sẽ không mặc nhiên được filter phía sau bắt. Một `NullPointerException` hoặc lỗi database cũng không tự biến thành `401`/`403` chỉ vì request đi qua Spring Security.

Một số authentication filter tự xử lý kết quả thất bại qua `AuthenticationFailureHandler` hoặc `AuthenticationEntryPoint`; không phải mọi thất bại authentication đều đi qua đúng cùng một nhánh `ExceptionTranslationFilter`.

### Cấu hình API thống nhất 401/403

Sau đây là một **cấu hình thay thế** bean `securityChain` có `permitAll()` của ví dụ, không phải bean thứ hai thêm song song vào ví dụ đó. Cơ chế xác thực thực tế (JWT, session, HTTP Basic, OAuth2 Resource Server...) phải được cấu hình riêng phù hợp với ứng dụng.

```java
package demo;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain securityChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, error) ->
                                writeError(response, 401, "AUTH_REQUIRED"))
                        .accessDeniedHandler((request, response, error) ->
                                writeError(response, 403, "ACCESS_DENIED")))
                .build();
    }

    private static void writeError(
            HttpServletResponse response, int status, String code)
            throws IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":\"" + code + "\"}");
    }
}
```

Đây là cấu hình minh họa với hai mã lỗi cố định, không ghép dữ liệu người dùng vào JSON. Trong hệ thống thật, sử dụng JSON serializer hoặc writer dùng chung và tránh ghi khi response đã committed. Với HTTP Basic/Bearer, cần bảo toàn header xác thực như `WWW-Authenticate` theo chuẩn/protocol; entry point tương ứng do framework cung cấp thường là lựa chọn đúng hơn khi cần chuẩn đó. Không được xem cấu hình `exceptionHandling(...)` là giải pháp tự bắt mọi exception của mọi custom filter.

## 6. Nếu lỗi phát sinh ngay trong filter của mình thì làm gì?

**Phân loại lỗi trước khi chọn cơ chế:**

1. **Lỗi nghiệp vụ từ controller/service:** để Spring MVC xử lý bằng `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseEntity` hoặc `ProblemDetail` như thiết kế API.
2. **Lỗi authentication/authorization:** tích hợp vào Spring Security qua cơ chế thích hợp như `AuthenticationEntryPoint`, `AccessDeniedHandler`, `AuthenticationFailureHandler` và đúng vị trí trong security filter chain. Nếu custom filter ở phía trước `ExceptionTranslationFilter`, nó phải tự xử lý hoặc chuyển giao lỗi theo contract rõ ràng.
3. **Lỗi kiểm tra request của Servlet filter:** filter có thể xử lý ngoại lệ dự kiến ngay tại chỗ và ghi response, hoặc gọi một thành phần chung chịu trách nhiệm tạo body JSON. Tránh biến lỗi nội bộ không mong muốn thành 4xx.
4. **Lỗi hệ thống không dự kiến:** cho phép cơ chế ghi log/giám sát và xử lý 5xx của container/app hoạt động; không lặng lẽ nuốt exception hay tiết lộ stack trace ra client.

Ví dụ một filter kiểm tra header và chủ động kết thúc request trước MVC (đây là **class minh họa**, cần đăng ký filter vào ứng dụng nếu sử dụng):

```java
package demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ClientHeaderFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        if (request.getHeader("X-Client") == null) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"code\":\"MISSING_X_CLIENT\"}");
            return; // Không gọi tiếp chain; request không đến controller.
        }
        chain.doFilter(request, response);
    }
}
```

Tùy yêu cầu, giới hạn filter bằng URL pattern hoặc `shouldNotFilter(...)`; ví dụ tối giản trên sẽ từ chối mọi request không có header khi nó được đăng ký cho mọi URL. Nếu filter đặt ngoài Spring Security, response `400` được tạo trước khi authorization diễn ra; cần cân nhắc thiết kế bảo mật và thứ tự thực tế.

### Có thể chuyển exception từ filter vào `HandlerExceptionResolver` không?

**Có, nhưng phải gọi tường minh** và hiểu giới hạn của nó. Ví dụ tại nhánh `catch` trong filter, khi response chưa committed:

```java
// resolver được inject với @Qualifier("handlerExceptionResolver")
ModelAndView handled =
        resolver.resolveException(request, response, null, exception);
if (handled == null) {
    throw exception; // Resolver không nhận xử lý: không được nuốt lỗi.
}
```

Đây là **đoạn minh họa đặt trong filter có sẵn**, không phải chương trình Java độc lập. `resolver` là `org.springframework.web.servlet.HandlerExceptionResolver`, `ModelAndView` thuộc `org.springframework.web.servlet.ModelAndView`; `exception` trong ví dụ là một `RuntimeException`. Truyền `handler = null` vì filter có thể chưa chọn được MVC handler. Một advice dùng selector theo controller/package/annotation có thể không áp dụng khi chưa có handler; resolver cũng có thể trả `null`. Nếu response đã ghi/committed hoặc resolver không hỗ trợ loại lỗi này, cơ chế cầu nối không giải quyết được vấn đề. Đừng gọi `DispatcherServlet` hoặc tạo vòng dispatch chỉ để hy vọng advice chạy.

Cách đơn giản và dễ kiểm soát hơn thường là để **filter/security handler** và **MVC advice** cùng sử dụng một mô hình lỗi (ví dụ `code`, `message`, `traceId`) và một dịch vụ serialize/log chung, còn mỗi tầng tự quyết định lúc nào gửi response.

## 7. `sendError`, `/error` và response đã committed

Có ba thao tác khác nhau:

- `throw exception`: chuyển quyền xử lý cho stack bên ngoài và có thể đến container nếu không ai bắt.
- `response.setStatus(400)` rồi viết JSON: filter trực tiếp tạo response; `@ControllerAdvice` không được gọi.
- `response.sendError(400)`: thông báo lỗi cho Servlet container; tùy container và ứng dụng, có thể kích hoạt dispatch loại `ERROR` đến trang lỗi hoặc `/error` của Spring Boot.

Một request `ERROR` dispatch có thể đi qua những filter/security rule được đăng ký cho dispatcher type đó. Đây là **một lần dispatch khác**, không có nghĩa exception ban đầu đã được advice bắt. Cần phân biệt request ban đầu, error dispatch và response kết quả trong log.

Khi `response.isCommitted()` là `true`, status và header đã được gửi hoặc cố định; cố ghi thêm body/đổi mã lỗi có thể thất bại hoặc tạo response hỏng. Vì vậy filter ghi lỗi phải kiểm tra thời điểm gửi response, tránh xử lý lặp và tránh vừa viết JSON vừa tiếp tục gọi `chain.doFilter(...)`.

## 8. Cách chẩn đoán một lỗi thực tế

Theo thứ tự sau:

1. **Xác định nơi ném exception:** stack trace chỉ đến `Filter#doFilter`, `OncePerRequestFilter#doFilterInternal`, `AuthenticationFilter`/`AuthorizationFilter`, interceptor hay controller/service? Đừng chỉ nhìn HTTP status.
2. **Xem loại exception gốc:** `AuthenticationException`, `AccessDeniedException`, exception binding/validation của MVC, hay `RuntimeException` khác? `401`, `403`, `400`, `500` có cơ chế và ý nghĩa khác nhau.
3. **Kiểm tra thứ tự filter thật:** filter do container đăng ký hay nằm trong `SecurityFilterChain` qua `http.addFilterBefore/After(...)`? Nó ở trước hay sau `ExceptionTranslationFilter`? Có bị đăng ký hai lần (vừa `@Component` như Servlet filter, vừa chèn vào security chain) không?
4. **Xem log của cả request gốc lẫn error dispatch:** có chuyển sang `/error` không? Có security rule nào chặn `DispatcherType.ERROR` khiến status cuối khác lỗi gốc không?
5. **Kiểm tra response:** đã committed chưa, filter có gọi `sendError` hay đã viết JSON chưa, còn gọi tiếp `chain.doFilter` sau khi ghi lỗi không?
6. **Thử ở đúng tầng:** test MVC advice bằng controller endpoint; test security exception handler bằng request authenticated/anonymous đúng kịch bản; test filter và error dispatch bằng HTTP integration test nếu cần hành vi container thật.

Một lỗi phổ biến là thêm `@ExceptionHandler(Exception.class)` rồi kỳ vọng mọi exception từ JWT filter đều trở thành JSON giống controller. Handler đó có thể xử lý nhiều exception MVC, nhưng không thay đổi đường đi của một exception ném trước `DispatcherServlet`. Lỗi phổ biến khác là dồn mọi thất bại authorization vào `401`, làm mất ý nghĩa `403`, hoặc tự trả JSON mà đánh mất `WWW-Authenticate` của Bearer/Basic.

## 9. Ghi nhớ

**`@ControllerAdvice` thuộc ranh giới Spring MVC. Servlet `Filter` và Spring Security có luồng bắt lỗi riêng.** Muốn response thống nhất, hãy xử lý lỗi tại đúng tầng (`@ExceptionHandler`, security handler, filter, container/error controller) và dùng chung chuẩn body khi cần. Chỉ khi filter **chủ động** chuyển exception qua `HandlerExceptionResolver` thì resolver MVC mới có cơ hội xử lý; không có cơ chế tự động áp dụng advice cho mọi filter.