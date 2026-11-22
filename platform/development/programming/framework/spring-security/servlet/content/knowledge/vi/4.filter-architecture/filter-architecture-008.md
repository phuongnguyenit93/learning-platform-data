# ExceptionTranslationFilter và giới hạn những ngoại lệ được chuyển đổi

Trong **Spring Security dành cho Servlet**, `ExceptionTranslationFilter` là cầu nối giữa những lỗi liên quan **xác thực/phân quyền** và cách ứng dụng trả lời HTTP khi lỗi xảy ra. Nó không xác thực người dùng, không tự quyết định quyền truy cập và cũng không phải bộ xử lý mọi ngoại lệ của ứng dụng. Nhiệm vụ chính của nó là quan sát ngoại lệ phát sinh **ở những thành phần nằm sau nó trong filter chain**, sau đó:

- Với `AuthenticationException`: khởi động quy trình xác thực thông qua `AuthenticationEntryPoint`.
- Với `AccessDeniedException`: xét trạng thái xác thực của người gọi để **bắt đầu xác thực** hoặc **từ chối truy cập** qua `AccessDeniedHandler`.
- Với ngoại lệ không thuộc hai họ trên: để lỗi tiếp tục lan truyền đến cơ chế xử lý phù hợp khác.

Bài học tập trung vào giới hạn được chuyển đổi: **loại ngoại lệ, vị trí phát sinh, cách ngoại lệ lan truyền, trạng thái response và cấu hình security chain**. Phân biệt đúng những giới hạn này giúp chẩn đoán chính xác lỗi `401`, `403`, redirect đến trang đăng nhập và lỗi ứng dụng `500`.

## 1. Vị trí của ExceptionTranslationFilter trong kiến trúc Servlet

Một request HTTP thông thường đi qua Servlet container, `DelegatingFilterProxy`, `FilterChainProxy` và **một** `SecurityFilterChain` được chọn. Trong chuỗi ấy, `ExceptionTranslationFilter` được đặt sao cho nó có thể bao quanh các bước phân quyền phía sau, thường bao gồm `AuthorizationFilter`.

~~~text
Servlet container
  |
  v
DelegatingFilterProxy ("springSecurityFilterChain")
  |
  v
FilterChainProxy
  |-- chọn SecurityFilterChain đầu tiên khớp request
  |
  v
Các filter đứng TRƯỚC ExceptionTranslationFilter
  |    (ví dụ: một số filter xác thực và CSRF)
  v
ExceptionTranslationFilter
  |    try {
  |        chain.doFilter(request, response)
  |    } catch (ngoại lệ hỗ trợ) {
  |        chuyển thành authentication/denial response
  |    }
  v
Các filter phía SAU, đặc biệt AuthorizationFilter
  |
  v
DispatcherServlet -> Controller -> Service
~~~

Trong sơ đồ này, thao tác `chain.doFilter(...)` của `ExceptionTranslationFilter` gọi phần tiếp theo của chuỗi; do đó filter **chỉ bắt được những ngoại lệ thực sự lan ngược qua lệnh gọi ấy**. Không thể kết luận rằng mọi `AuthenticationException` hoặc `AccessDeniedException` xuất hiện ở bất kỳ vị trí nào của request đều được filter này xử lý.

Ví dụ, nếu một filter xác thực nằm **trước** `ExceptionTranslationFilter` tự ném ngoại lệ hoặc xử lý lỗi bằng failure handler riêng, ngoại lệ đó có thể không bao giờ đi qua `ExceptionTranslationFilter`. Nếu `DispatcherServlet` đã xử lý ngoại lệ bằng `@ExceptionHandler` hay `HandlerExceptionResolver` và tạo response, ngoại lệ cũng có thể không lan ngược đến filter.

**Hai lớp quyết định khác nhau:** `FilterChainProxy` quyết định **SecurityFilterChain nào chạy**; `ExceptionTranslationFilter` quyết định **xử lý một ngoại lệ security đi qua nó như thế nào**. Nếu request không được chọn vào một chain có filter này, nó không có cơ hội xử lý ngoại lệ của request đó.

## 2. Hai họ ngoại lệ được nhận diện

### 2.1. AuthenticationException: cần bắt đầu quy trình xác thực

`org.springframework.security.core.AuthenticationException` là lớp cha của các lỗi xác thực trong Spring Security, chẳng hạn `BadCredentialsException`, `InsufficientAuthenticationException` hoặc `AuthenticationCredentialsNotFoundException`. Khi một ngoại lệ loại này lan từ phần chuỗi phía sau vào `ExceptionTranslationFilter`, filter gọi nhánh **start authentication**.

Điều quan trọng: `ExceptionTranslationFilter` **không kiểm tra username/password để giải quyết lỗi**. Nó bàn giao cho một `AuthenticationEntryPoint`, chẳng hạn:

- HTTP Basic: trả yêu cầu xác thực, thường là HTTP `401` kèm `WWW-Authenticate`.
- Bearer token / OAuth2 Resource Server: có thể trả `401` cùng Bearer challenge phù hợp.
- Form login: thường chuyển hướng HTTP `302` đến trang đăng nhập.
- Entry point tùy biến: có thể trả JSON/status theo hợp đồng API của ứng dụng.

Response cuối cùng phụ thuộc cấu hình, không phải quy tắc cứng “AuthenticationException luôn bằng 401”.

### 2.2. AccessDeniedException: chưa đủ quyền, nhưng phải xét loại Authentication

`org.springframework.security.access.AccessDeniedException` biểu thị thao tác bị từ chối bởi cơ chế phân quyền. Ví dụ: một người dùng đăng nhập không có role `ADMIN` truy cập endpoint yêu cầu role đó.

Khi bắt được `AccessDeniedException`, `ExceptionTranslationFilter` dùng `AuthenticationTrustResolver` và `SecurityContextHolder` để kiểm tra trạng thái authentication:

1. Nếu người gọi được xem là **anonymous** hoặc ở mức **remember-me** chưa đủ bảo đảm, filter có thể khởi động quy trình xác thực lại, thường thông qua `AuthenticationEntryPoint`. Nó tạo một `InsufficientAuthenticationException` làm lý do khởi động xác thực trong nhánh này.
2. Nếu người gọi đã được xác thực đầy đủ nhưng không có quyền cần thiết, filter gọi `AccessDeniedHandler`, thường trả `403 Forbidden`.

Một `AccessDeniedException` không tự động đồng nghĩa `403`; điều kiện anonymous/remember-me làm nhánh xử lý thay đổi. Ngược lại, thông tin xác thực đã hợp lệ không có nghĩa người dùng có đủ authority, nên `403` là hành vi bình thường cho nhiều trường hợp.

### 2.3. Bảng quyết định thực hành

| Ngoại lệ đi đến ExceptionTranslationFilter | Trạng thái người gọi | Nhánh xử lý | Response thường gặp |
| --- | --- | --- | --- |
| `AuthenticationException` | Bất kỳ | `AuthenticationEntryPoint` | 401 hoặc 302, tùy phương thức login |
| `AccessDeniedException` | Anonymous | Bắt đầu xác thực qua entry point | 401 hoặc 302 |
| `AccessDeniedException` | Remember-me theo trust resolver | Bắt đầu xác thực lại | 401 hoặc 302, tùy cấu hình |
| `AccessDeniedException` | Đã xác thực đầy đủ, thiếu quyền | `AccessDeniedHandler` | 403 |
| `IllegalArgumentException`, `NullPointerException`, lỗi nghiệp vụ không thuộc hai họ trên | Bất kỳ | Không được chuyển đổi bởi filter này | Đi tiếp đến cơ chế xử lý lỗi khác; có thể là 500 |
| Bất kỳ lỗi security nào được xử lý hoàn toàn trước khi tới filter | Bất kỳ | Không có nhánh xử lý tại filter | Phụ thuộc thành phần xử lý trước |

“Thường gặp” ở cột cuối có nghĩa **không phải bảo đảm cho mọi ứng dụng**. Status, header, body, redirect, session hay trang lỗi được quyết định bởi entry point/handler và những filter/framework khác.

## 3. Cơ chế bắt ngoại lệ: không chỉ nhìn exception ngoài cùng

Ngoại lệ security có thể bị bọc trong các ngoại lệ Servlet hoặc exception khác khi lan qua nhiều tầng. `ExceptionTranslationFilter` sử dụng `ThrowableAnalyzer` để tìm lỗi security phù hợp trong chuỗi nguyên nhân, thay vì chỉ kiểm tra một lớp ngoài cùng theo cách đơn giản.

Có thể hình dung:

~~~text
ServletException
  └── caused by AuthenticationException
          -> ExceptionTranslationFilter nhận ra lỗi xác thực
          -> khởi động AuthenticationEntryPoint

ServletException
  └── caused by AccessDeniedException
          -> xử lý theo trạng thái authentication

ServletException
  └── caused by SQLException / IllegalStateException
          -> không có ngoại lệ security phù hợp
          -> ngoại lệ tiếp tục lan truyền
~~~

Đây là mô hình minh họa. Khi một chuỗi nguyên nhân có nhiều ngoại lệ hoặc tùy biến `ThrowableAnalyzer`, cách tìm lỗi thuộc implementation/version đang sử dụng. Điểm cần hiểu là Spring Security chỉ nhận diện **những họ ngoại lệ security được hỗ trợ**, không biến tùy ý mọi `RuntimeException` thành response xác thực.

Trong đường xử lý của bản Spring Security 6.x thông dụng, filter bắt lỗi phát sinh từ việc gọi downstream filter chain, phân tích nguyên nhân, chọn `AuthenticationException` hoặc `AccessDeniedException` khi có thể, rồi xử lý. Nếu không tìm thấy loại phù hợp, lỗi được ném tiếp. Một số loại lỗi nghiêm trọng, trường hợp async dispatch, hoặc response đã được ghi xong có thể nằm ngoài khả năng xử lý bằng cách tạo response mới.

## 4. Nhánh AuthenticationEntryPoint làm gì?

Khi phải bắt đầu xác thực, `ExceptionTranslationFilter` thực hiện quy trình logic sau:

1. Xóa/ngắt security context hiện tại khỏi xử lý yêu cầu để không dùng nhầm authentication cũ khi bắt đầu xác thực.
2. Yêu cầu `RequestCache` lưu request gốc nếu cơ chế lưu request được cấu hình (trường hợp thường thấy là form login muốn quay lại URL ban đầu).
3. Gọi `AuthenticationEntryPoint.commence(request, response, authenticationException)`.
4. Entry point quyết định response: redirect, status code, challenge header hoặc nội dung trả về.

Sơ đồ:

~~~text
AuthenticationException
        |
        v
ExceptionTranslationFilter
        |
        +--> reset SecurityContext cho quá trình bắt đầu login
        |
        +--> RequestCache.saveRequest(...) (theo cấu hình)
        |
        +--> AuthenticationEntryPoint.commence(...)
                      |
                      +--> HTTP Basic: challenge / 401
                      +--> Form login: 302 /login
                      +--> REST entry point tùy biến: JSON 401
~~~

**RequestCache không đồng nghĩa luôn ghi session.** Với form login, `HttpSessionRequestCache` thường phù hợp để nhớ URL và trở lại sau khi login. Với REST API stateless, ứng dụng thường dùng `NullRequestCache` hoặc chính sách không tạo session để tránh vô tình lưu request. Việc chọn request cache và session policy phải nhất quán với thiết kế API.

Không nên cố tự gọi `AuthenticationEntryPoint` từ controller cho mọi lỗi nghiệp vụ. Bộ phận này có mục đích cụ thể: mở đầu/chuyển người dùng sang quy trình xác thực.

## 5. Nhánh AccessDeniedHandler làm gì?

Nếu người gọi **được xác thực đầy đủ** và `AccessDeniedException` đi qua `ExceptionTranslationFilter`, filter chuyển trách nhiệm sang `AccessDeniedHandler`.

`AccessDeniedHandlerImpl` thường gửi HTTP `403`; nó cũng hỗ trợ chuyển tiếp đến trang lỗi cấu hình qua `errorPage`. Một `AccessDeniedHandler` tùy biến có thể ghi JSON hoặc bổ sung thông tin lỗi được phép tiết lộ, miễn là không làm lộ chi tiết phân quyền/định danh nhạy cảm.

Ví dụ ứng dụng:

- Người dùng `alice` đã login và có `ROLE_USER`.
- Endpoint `GET /admin/reports` yêu cầu `ROLE_ADMIN`.
- `AuthorizationFilter` ném `AccessDeniedException`.
- Ngoại lệ lan ngược qua `ExceptionTranslationFilter`.
- Vì `alice` không phải anonymous/remember-me theo `AuthenticationTrustResolver`, `AccessDeniedHandler` xử lý; mặc định thường là `403`.

**Đừng nhầm quyền với xác thực:** “Đã đăng nhập” trả lời câu hỏi người dùng là ai; “được phép truy cập” trả lời câu hỏi người dùng ấy có đủ quyền cho tài nguyên cụ thể hay không.

## 6. Những ngoại lệ ExceptionTranslationFilter KHÔNG giải quyết

Giới hạn là phần cốt lõi của cơ chế:

### 6.1. Không chuyển mọi exception Java thành 401/403

Những lỗi `NullPointerException`, `IllegalStateException`, truy vấn database hỏng, timeout của dịch vụ, lỗi lập trình hoặc `ResponseStatusException` thông thường không trở thành security exception chỉ vì request đi qua Spring Security. Chúng thuộc cơ chế xử lý lỗi ứng dụng như `@ControllerAdvice`, `HandlerExceptionResolver`, `BasicErrorController` hoặc servlet container.

Một lỗi bất thường có thể cuối cùng dẫn đến `500 Internal Server Error`, nhưng status thật còn tùy exception resolver và xử lý lỗi của ứng dụng.

### 6.2. Không bắt lỗi sinh ra ở filter đứng trước nó

Hãy nhớ cấu trúc gọi hàm:

~~~java
// Mô hình ý tưởng của filter A đứng trước ExceptionTranslationFilter:
filterA.doFilter(request, response, chain);  // có thể ném exception
// ExceptionTranslationFilter chỉ chạy khi request tới nó.

// Mô hình ý tưởng bên trong ExceptionTranslationFilter:
try {
    chain.doFilter(request, response); // các filter phía SAU
} catch (Exception exception) {
    // Chỉ xem xét những lỗi lan ngược qua điểm này.
}
~~~

Đây là **đoạn giả mã**, không phải code copy vào chương trình thực; các kiểu/nhánh catch thật của Spring Security phức tạp hơn. Nếu `BasicAuthenticationFilter` hoặc một authentication filter khác ở trước xử lý `AuthenticationException` bằng failure handler của chính nó, `ExceptionTranslationFilter` không xử lý lại lỗi ấy.

Do đó, khi xác thực sai mật khẩu trả `401`, không nên khẳng định `ExceptionTranslationFilter` đã tạo `401`. Một authentication filter/entry point khác có thể đã thực hiện điều đó trước.

### 6.3. Không thay thế exception handling của Spring MVC

Các exception từ controller/service có thể bị xử lý bởi:

- `@ExceptionHandler` trong controller.
- `@ControllerAdvice` dùng chung cho MVC.
- `HandlerExceptionResolver`, trình xử lý status hoặc response của framework.
- Các thành phần xử lý lỗi sau khi Servlet dispatch.

Nếu MVC đã tiêu thụ exception và trả response, filter phía ngoài không còn thấy exception để chuyển đổi. Nếu một `AccessDeniedException` thực sự lan qua downstream chain mà không bị xử lý, filter **có thể** bắt nó. Vì vậy cũng không chính xác khi nói rằng `ExceptionTranslationFilter` “chỉ xử lý lỗi từ AuthorizationFilter”; nguồn lỗi có thể là bất kỳ thành phần downstream phù hợp nào, miễn là exception còn lan qua nó.

Một `@ControllerAdvice` bắt `Exception.class` quá rộng có thể vô tình bắt ngoại lệ security và trả JSON `500`/`200` trước khi `ExceptionTranslationFilter` thấy nó. Cần cân nhắc thứ tự exception resolver và chính sách bảo mật khi bắt ngoại lệ tổng quát.

### 6.4. Không tự động xử lý mọi lỗi CSRF

`CsrfFilter` thường chạy **trước** `ExceptionTranslationFilter`. Khi thiếu hoặc sai CSRF token, CSRF filter có thể dùng `AccessDeniedHandler` của nó để trả `403` mà ngoại lệ không đi qua `ExceptionTranslationFilter`. `MissingCsrfTokenException` và `InvalidCsrfTokenException` thuộc nhóm lỗi denied access, nhưng vị trí phát sinh và cách `CsrfFilter` xử lý mới quyết định filter nào gửi response.

Vì vậy, thấy `403` không đủ để xác định là thiếu role. Với HTTP `POST`/`PUT`/`DELETE`, kiểm tra CSRF trước khi kết luận authorization rule sai.

### 6.5. Không thể viết lại response đã committed

Sau khi status/header/body đã được gửi đến client (`response.isCommitted()`), không còn bảo đảm có thể chuyển tiếp sang login, gửi challenge, đổi status hoặc ghi JSON lỗi khác. `ExceptionTranslationFilter` có logic nhận biết trường hợp response đã committed và có thể ném lỗi xử lý tiếp theo thay vì cố ghi response không hợp lệ.

Tình huống thường gặp: một filter hoặc controller đã ghi một phần response rồi mới ném `AccessDeniedException`. Cách sửa là kiểm tra quyền trước khi bắt đầu stream dữ liệu khi có thể, tránh tạo response partial rồi mới xử lý security exception.

### 6.6. Không áp dụng nếu không có security chain phù hợp

`FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp request**. Nếu mọi chain đều bị giới hạn bởi `securityMatcher("/api/**")` và URL `/reports` không khớp, `ExceptionTranslationFilter` của API chain không chạy cho `/reports`. Quy tắc `anyRequest().authenticated()` bên trong API chain cũng không thể bảo vệ URL ấy.

Ngoài ra, `web.ignoring()` loại request khỏi security filtering có thể khiến `ExceptionTranslationFilter` không tham gia. Khác với `permitAll()`: cho phép trong rule authorization vẫn có thể giữ request đi qua các security filter.

### 6.7. Async/error dispatch có vòng đời riêng

Servlet `ASYNC` hoặc `ERROR` dispatch có thể đi qua tập filter khác nhau, hoặc xảy ra sau khi luồng ban đầu đã kết thúc. Phạm vi filter registration, dispatcher type, cách Spring Security áp dụng bảo mật với async và tình trạng committed của response ảnh hưởng việc exception có đi qua `ExceptionTranslationFilter` hay không. Cần test thực tế; không mặc định một exception ném trong tác vụ async muộn luôn được filter bao ngoài request gốc xử lý.

## 7. Mô phỏng quyết định bằng Java 17 độc lập

Đoạn mã dưới đây **mô phỏng chính sách phân nhánh** để học, không triển khai các lớp Spring Security thật. Nó chỉ phân loại ba nhóm exception và ba loại trạng thái authentication; networking, request cache và Servlet filter chain đã được lược bỏ. Mã chạy với Java 17+ và giúp kiểm tra ngay các nhánh.

~~~java
public class ExceptionTranslationDecisionDemo {
    enum Caller { ANONYMOUS, REMEMBER_ME, FULLY_AUTHENTICATED }

    static class AuthFailure extends RuntimeException {}
    static class Denied extends RuntimeException {}

    static String decide(Caller caller, RuntimeException error) {
        if (error instanceof AuthFailure) {
            return "START_AUTH";
        }
        if (error instanceof Denied) {
            if (caller == Caller.ANONYMOUS || caller == Caller.REMEMBER_ME) {
                return "START_AUTH";
            }
            return "ACCESS_DENIED";
        }
        return "PROPAGATE";
    }

    static void show(Caller caller, RuntimeException error) {
        System.out.println(caller + " + " + error.getClass().getSimpleName()
                + " -> " + decide(caller, error));
    }

    public static void main(String[] args) {
        show(Caller.ANONYMOUS, new AuthFailure());
        show(Caller.ANONYMOUS, new Denied());
        show(Caller.REMEMBER_ME, new Denied());
        show(Caller.FULLY_AUTHENTICATED, new Denied());
        show(Caller.FULLY_AUTHENTICATED, new IllegalStateException());
    }
}
~~~

Lưu tệp đúng tên `ExceptionTranslationDecisionDemo.java`, sau đó chạy:

~~~bash
javac ExceptionTranslationDecisionDemo.java
java ExceptionTranslationDecisionDemo
~~~

Stdout chính xác:

~~~text
ANONYMOUS + AuthFailure -> START_AUTH
ANONYMOUS + Denied -> START_AUTH
REMEMBER_ME + Denied -> START_AUTH
FULLY_AUTHENTICATED + Denied -> ACCESS_DENIED
FULLY_AUTHENTICATED + IllegalStateException -> PROPAGATE
~~~

Ý nghĩa:

- `START_AUTH` tương ứng gọi entry point, **không đồng nghĩa chắc chắn HTTP 401**.
- `ACCESS_DENIED` tương ứng gọi access denied handler, **thường** trả 403.
- `PROPAGATE` nghĩa filter không chuyển ngoại lệ đó thành luồng xác thực/phân quyền.
- Mô hình đã giả định exception thật sự đi đến filter và response chưa committed. Chương trình không mô phỏng xử lý nguyên nhân lồng nhau, context, request cache hoặc ordering.

## 8. Cấu hình thực tế với Spring Security 6.x Servlet

Một cấu hình tối thiểu cho ứng dụng Spring Boot 3.x, Java 17+, Spring Security 6.x và `spring-boot-starter-web` + `spring-boot-starter-security` có thể là:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AccessRulesConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là cấu hình một chain bao phủ mọi request và dùng HTTP Basic. Khi người dùng chưa xác thực truy cập `/admin/report`, quá trình phân quyền có thể ném `AccessDeniedException`; `ExceptionTranslationFilter` phát hiện người dùng anonymous và khởi động `BasicAuthenticationEntryPoint`, thường trả `401` với challenge. Khi một người dùng đã được xác thực nhưng thiếu `ROLE_ADMIN` truy cập endpoint ấy, nhánh denied access thường trả `403`.

Cần phân biệt hai đường đi đến cùng status 401:

1. **Không có hoặc thiếu authentication khi phân quyền**: downstream `AuthorizationFilter` ném lỗi, `ExceptionTranslationFilter` có thể gọi entry point.
2. **Gửi credentials HTTP Basic sai**: `BasicAuthenticationFilter` có cơ chế xử lý lỗi xác thực riêng và có thể gọi entry point mà không đi qua `ExceptionTranslationFilter`.

Chỉ nhìn HTTP 401 không phân biệt được hai cơ chế này. Để phân tích, hãy kiểm tra filter nào thực sự phát hiện lỗi.

Một controller minh họa, cùng dự án:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SampleController {
    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "report";
    }
}
~~~

Role `ADMIN` được Spring Security hiểu theo authority mặc định `ROLE_ADMIN` khi dùng `hasRole("ADMIN")`. Nếu hệ thống lưu authorities khác quy tắc tiền tố ấy, phải thống nhất cấu hình authority và rule.

### Tùy biến AuthenticationEntryPoint và AccessDeniedHandler

Trong các ứng dụng API sử dụng JSON, có thể tùy biến cách trả lỗi bằng DSL `exceptionHandling`:

~~~java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint((request, response, exception) -> {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"authentication_required\"}");
    })
    .accessDeniedHandler((request, response, exception) -> {
        response.setStatus(403);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"access_denied\"}");
    })
);
~~~

Đây là **đoạn bổ sung bên trong phương thức đang cấu hình `HttpSecurity`**, đặt trước `http.build()`, không phải một class Java độc lập. Lớp xử lý lỗi chỉ điều khiển **cách phản hồi**, không thay thế `AuthenticationProvider`, `AuthorizationManager` hoặc chính sách matcher.

**Cẩn thận với HTTP Basic và Bearer:** Nếu ghi đè entry point bằng cách chỉ trả JSON 401 như trên, response có thể mất `WWW-Authenticate` mà client cần để biết cơ chế xác thực. Với API tuân theo HTTP Basic hoặc OAuth2 Bearer, giữ challenge header phù hợp hoặc sử dụng entry point dành cho giao thức ấy thay vì sao chép máy móc đoạn JSON.

Với API stateless, có thể xem xét thêm cấu hình request cache và session:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.savedrequest.NullRequestCache;

// Trong phần cấu hình HttpSecurity, trước khi build:
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .requestCache(cache -> cache.requestCache(new NullRequestCache()));
~~~

Đoạn trên chỉ minh họa lựa chọn không lưu request cho API; khi ứng dụng cần form login, session hoặc “quay về trang trước”, dùng cấu hình phù hợp thay vì tắt request cache toàn hệ thống.

## 9. Kiểm thử nhánh 401 và 403 bằng MockMvc

Với cấu hình và controller ở mục 8, test tích hợp Spring Boot có thể kiểm tra nhánh anonymous, thiếu quyền và đủ quyền. Bổ sung dependency `spring-security-test` bên cạnh `spring-boot-starter-test` và bật Spring Security filter trong MockMvc.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityExceptionFlowTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousIsAskedToAuthenticate() throws Exception {
        mockMvc.perform(get("/admin/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutRoleIsForbidden() throws Exception {
        mockMvc.perform(get("/admin/report")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedWithRoleIsAllowed() throws Exception {
        mockMvc.perform(get("/admin/report")
                        .with(user("manager").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

Các assertion được kỳ vọng đúng khi sử dụng **đúng cấu hình HTTP Basic ở mục 8**, không có custom entry point/handler thay đổi status, request là GET, controller tồn tại và Spring Security filter hoạt động trong MockMvc. Mock user do `spring-security-test` cung cấp để kiểm tra authorization mà không cần mật khẩu thật.

Để phân biệt lỗi filter trước/sau, bổ sung test riêng cho xác thực sai credentials và cho endpoint bị `CsrfFilter` chặn. Không viết test kiểu “mọi AccessDeniedException từ mọi tầng luôn trả 403”; điều đó bỏ qua vị trí phát sinh, xử lý MVC, anonymous authentication và response committed.

### Cách lần dấu trong log

Ở môi trường phát triển hoặc test, có thể tạm bật:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=TRACE
logging.level.org.springframework.security.web.access.intercept=TRACE
~~~

Log giúp tìm chain đã chọn và đường đi qua các filter. Câu chữ và mức log có thể khác nhau theo phiên bản, vì vậy **dùng assertion HTTP và cấu hình thực tế làm bằng chứng chính**, không kiểm thử dựa vào thông báo log. Tránh ghi credentials, token hoặc session cookie.

Khi gặp kết quả bất ngờ, kiểm tra lần lượt:

1. Request có đi vào đúng `SecurityFilterChain` không? Có `securityMatcher` loại request khỏi chain không?
2. Ngoại lệ gốc là `AuthenticationException`, `AccessDeniedException` hay loại khác?
3. Ngoại lệ được ném ở filter **trước hay sau** `ExceptionTranslationFilter`? Có component nào đã xử lý trước không?
4. Authentication là anonymous, remember-me hay fully authenticated? Authority hiện tại là gì?
5. `AuthenticationEntryPoint` / `AccessDeniedHandler` đang được áp dụng có đúng đối tượng request không?
6. Response đã committed chưa, và request có đang ở async/error dispatch không?
7. Có `CsrfFilter`, exception resolver của MVC hoặc custom filter chủ động ghi response trước không?

## 10. Các tình huống dễ nhầm và hướng xử lý

| Hiện tượng | Giải thích cần kiểm chứng | Hướng kiểm tra |
| --- | --- | --- |
| Anonymous gọi endpoint bảo vệ và thấy 302 thay vì 401 | Form login entry point có thể redirect | Kiểm tra `formLogin()`, entry point và response `Location` |
| Người dùng có login nhận 403 | Đã xác thực nhưng thiếu role/authority, hoặc bị CSRF | Xem `AccessDeniedException`, security context, CSRF và handler |
| Nhập password sai nhận 401, không thấy ETF log | Authentication filter trước ETF có thể tự xử lý | Kiểm tra `BasicAuthenticationFilter`/failure handler |
| Controller ném IllegalStateException rồi trả 500 | Không thuộc hai loại security exception | Kiểm tra stack trace, MVC exception resolver và error handling |
| Controller ném AccessDeniedException nhưng @ControllerAdvice trả JSON riêng | MVC có thể đã bắt ngoại lệ trước khi nó lan ra filter | Kiểm tra `@ExceptionHandler` và `HandlerExceptionResolver` |
| POST endpoint permitAll vẫn 403 | CSRF còn bật, và CsrfFilter có thể xử lý riêng | Kiểm tra token, `CsrfFilter` và luật áp dụng CSRF |
| API stateless tạo session sau challenge | Request cache hoặc thành phần khác có thể lưu request | Kiểm tra `RequestCache`, session policy và cookies |
| Filter không nhận được lỗi từ route nhất định | Request có thể vào chain khác hoặc không vào security chain | Kiểm tra thứ tự chain và matcher |
| Đã bắt AccessDeniedException nhưng response không thể đổi thành 403 | Response đã committed | Kiểm tra streaming, thứ tự ghi response và log lỗi |
| 403 được trả nhưng không phải do AccessDeniedHandler của ETF | Một filter khác có thể tự trả 403 | Bật trace và xác định thành phần phát response |

Đặc biệt, **401 khác 403 về ý nghĩa giao thức**: 401 yêu cầu quá trình xác thực (thường có challenge tương ứng); 403 biểu thị yêu cầu bị từ chối. Dù hai status hay gặp trong nhánh của ETF, chúng không phải phép ánh xạ một-một từ class exception sang mã HTTP.

## 11. Bài tập tự kiểm tra

**Tình huống A.** Một khách chưa đăng nhập gọi `GET /admin/report`. `AuthorizationFilter` ném `AccessDeniedException`, request đi qua `ExceptionTranslationFilter` và ứng dụng dùng form login. Dự kiến nhánh nào?

**Đáp án:** Filter coi anonymous access denied là trường hợp cần xác thực, nên gọi `AuthenticationEntryPoint`. Với form login, kết quả thông thường là chuyển hướng đến trang đăng nhập (302), không bắt buộc 403.

**Tình huống B.** Người dùng đã xác thực bằng HTTP Basic, có `ROLE_USER` nhưng endpoint yêu cầu `ROLE_ADMIN`. Ngoại lệ từ authorization lan tới filter. Kết quả thường là gì?

**Đáp án:** `AccessDeniedHandler` xử lý vì người dùng fully authenticated nhưng thiếu quyền. Với handler mặc định, status thường là 403. Đây không phải tín hiệu yêu cầu nhập password lại trong cấu hình thông thường.

**Tình huống C.** Một `BasicAuthenticationFilter` từ chối password sai, trả 401 thông qua entry point riêng. Có bắt buộc phải có `ExceptionTranslationFilter` xử lý mới trả được 401 không?

**Đáp án:** Không. Authentication filter có thể tự xử lý lỗi khi ở trước ETF. Trạng thái 401 không chứng minh ETF đã bắt exception.

**Tình huống D.** Controller ném `NullPointerException` và không có security exception trong cause chain. ETF có đổi nó thành `AccessDeniedException` hay 403 không?

**Đáp án:** Không. Đó là lỗi không thuộc phạm vi chuyển đổi của ETF. Nó tiếp tục tới cơ chế xử lý lỗi ứng dụng/servlet tương ứng.

**Tình huống E.** Controller ném `AccessDeniedException`, nhưng một `@ControllerAdvice` đã bắt và trả HTTP 400. ETF có ghi đè thành 403 không?

**Đáp án:** Không nếu exception đã được MVC xử lý hoàn toàn và không lan ra filter. Nếu muốn security xử lý nhất quán, cần thiết kế exception resolver tránh nuốt sai security exception.

**Tình huống F.** `ExceptionTranslationFilter` bắt một ngoại lệ security nhưng controller đã stream nhiều dữ liệu ra mạng. Có bảo đảm chuyển thành 401/403 được không?

**Đáp án:** Không. Nếu response đã committed, đổi status/headers có thể bất khả thi; cần thiết kế phân quyền trước khi gửi dữ liệu và xử lý lỗi trong luồng phù hợp.

## 12. Checklist thiết kế và chẩn đoán

- Xác định **chain được chọn** và vị trí `ExceptionTranslationFilter` trong chain đó.
- Phân biệt rõ **`AuthenticationException`**, **`AccessDeniedException`** và ngoại lệ ứng dụng thông thường.
- Với `AccessDeniedException`, xét **anonymous / remember-me / fully authenticated** trước khi suy luận 401 hoặc 403.
- Phân biệt **`AuthenticationEntryPoint`** với **`AccessDeniedHandler`**, và xem cấu hình response thực tế.
- Xem xét `RequestCache`, session và security context khi sử dụng redirect login hoặc API stateless.
- Xác định exception xuất phát **trước hay sau filter**, có bị MVC/CSRF/authentication filter xử lý riêng không.
- Kiểm tra response committed, async/error dispatch và custom exception resolver nếu thông báo lỗi bất thường.
- Viết kiểm thử cho anonymous, đã xác thực thiếu quyền, đã xác thực đủ quyền, lỗi xác thực và lỗi nghiệp vụ độc lập.

**Kết luận:** `ExceptionTranslationFilter` chuyển một tập ngoại lệ security **được lan truyền tới nó** thành luồng bắt đầu xác thực hoặc từ chối truy cập. Giới hạn xử lý được quyết định đồng thời bởi **kiểu exception, vị trí trong filter chain, trạng thái authentication và trạng thái response**. Hiểu bốn yếu tố ấy giúp tránh nhầm 401/403/302 với lỗi ứng dụng, và xây dựng luồng bảo mật Servlet dễ kiểm chứng.