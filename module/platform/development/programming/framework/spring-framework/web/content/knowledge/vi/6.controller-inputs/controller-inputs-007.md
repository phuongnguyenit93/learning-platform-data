# @RequestAttribute, @SessionAttribute và dữ liệu có sẵn trong ngữ cảnh Spring MVC

## 1. Tại sao controller có thể nhận dữ liệu dù client không truyền trực tiếp?

Một HTTP request đi qua nhiều thành phần trước khi chạy vào phương thức controller: web server/Servlet container, Servlet Filter, `DispatcherServlet`, `HandlerInterceptor`, rồi đến quá trình Spring MVC chọn và gọi handler. Ở các bước trước controller, ứng dụng có thể đã tạo thông tin nội bộ như mã theo dõi, tenant đã xác định, metadata của request hoặc đối tượng được tải từ session.

Hai annotation trong **Spring MVC (Servlet stack)** giúp controller nhận lại các giá trị **đã tồn tại** ở đúng phạm vi:

- `@RequestAttribute`: đọc một thuộc tính từ **Servlet request hiện tại**; thường được đặt trước đó qua `HttpServletRequest#setAttribute` bởi filter, interceptor hoặc thành phần khác.
- `@SessionAttribute`: đọc một thuộc tính từ **HTTP session liên quan đến client**, thường được đặt qua `HttpSession#setAttribute` ở một request trước hoặc bởi logic quản lý session.

Cả hai là annotation trên **tham số phương thức controller**, không tự động tạo ra giá trị, không đọc query parameter và không tự đọc JSON body. Nếu thuộc tính chưa có, phải xử lý tình huống thiếu theo `required`.

Ví dụ:

```text
Client
  GET /api/context/request
       |
       v
Servlet Filter                request.setAttribute("traceId", "demo-42")
       |
       v
DispatcherServlet
       |
       v
HandlerInterceptor (nếu có)  có thể đặt thêm request attribute
       |
       v
@RequestAttribute("traceId") String traceId
       |
       v
Controller: "traceId=demo-42"
```

Trong luồng khác, session có thể lưu một lựa chọn `language=vi` từ request trước. Request mới gửi cookie xác định session, server tìm lại thuộc tính và `@SessionAttribute("language")` đọc giá trị đó. Request attribute và session attribute độc lập: **cùng một tên key** không có nghĩa là cùng một giá trị.

## 2. Phân biệt các nguồn dữ liệu đầu vào

| Nguồn | Controller lấy bằng | Giá trị đến từ đâu? | Vòng đời điển hình |
| --- | --- | --- | --- |
| Query/form parameter | `@RequestParam("q")` | URL `?q=java` hoặc form body phù hợp | Theo request |
| Path variable | `@PathVariable("id")` | Segment do URL mapping bắt được, ví dụ `/users/7` | Theo request |
| Header | `@RequestHeader("X-Trace-Id")` | HTTP header client/proxy gửi | Theo request |
| Cookie | `@CookieValue("theme")` | Cookie trong request | Theo request/client |
| Body JSON | `@RequestBody Dto` | Payload được `HttpMessageConverter` đọc | Theo request |
| Request attribute | `@RequestAttribute("traceId")` | Object ở `ServletRequest#setAttribute`, thường do thành phần phía server đặt | Theo request |
| Session attribute | `@SessionAttribute("language")` | Object ở `HttpSession#setAttribute` | Qua nhiều request của cùng session |
| Model attribute | `@ModelAttribute`, `Model` | Model của Spring MVC; có thể khởi tạo/bind từ request | Theo luồng MVC, tùy cơ chế model/session |
| Servlet context attribute | `ServletContext#getAttribute` | Trạng thái cấp ứng dụng web do server code đặt | Chia sẻ ở cấp ServletContext |
| Security principal | `Principal`, `Authentication` hoặc `@AuthenticationPrincipal` khi dùng Spring Security | Danh tính đã được xác thực theo cơ chế bảo mật | Theo security context đã thiết lập |

**Điểm dễ nhầm:** `request.getParameter("traceId")` và `request.getAttribute("traceId")` tra **hai kho dữ liệu khác nhau**. Gửi `?traceId=evil` không tự tạo `request` attribute tên `traceId`, và một JSON field `{"language":"vi"}` cũng không tự biến thành `session` attribute.

## 3. `@RequestAttribute`: đọc thuộc tính thuộc request hiện tại

Cú pháp:

```java
@GetMapping("/example")
public String handle(
        @RequestAttribute("traceId") String traceId,
        @RequestAttribute(name = "tenant", required = false) String tenant) {
    return traceId + ":" + (tenant == null ? "unknown" : tenant);
}
```

Các thành phần quan trọng:

- `value` và `name` là alias. Nên **ghi rõ tên** để tránh phụ thuộc cấu hình compiler giữ tên tham số (ví dụ `-parameters`).
- `required` mặc định là `true`. Nếu không có attribute tương ứng, Spring ném ngoại lệ khi resolve tham số, phương thức controller không được gọi. Mã HTTP cuối cùng chịu ảnh hưởng của bộ xử lý ngoại lệ (thông thường lỗi binding sẽ trở thành 400).
- `required = false` cho phép giá trị vắng mặt, thường được truyền là `null` cho reference type; cũng có thể dùng `Optional<T>`.
- Annotation **không có `defaultValue`** như `@RequestParam`. Nếu cần fallback, tự tính trong controller hoặc thành phần cung cấp.
- Tên attribute so khớp tên đã đặt vào request; `@RequestAttribute("tenant")` không đọc `tenantId` chỉ vì kiểu dữ liệu tương ứng.
- Object lấy ra phải phù hợp với kiểu tham số hoặc có cơ chế chuyển kiểu thích hợp. Annotation không biến JSON hay Map thành một đối tượng domain tùy ý.

Nguồn đặt attribute phổ biến:

```java
// Servlet Filter:
request.setAttribute("traceId", traceId);

// HandlerInterceptor#preHandle:
request.setAttribute("tenant", resolvedTenant);

// Bất cứ thành phần phía server có cùng ServletRequest:
String traceId = (String) request.getAttribute("traceId");
request.removeAttribute("traceId");
```

Một attribute có thể được sửa/loại bỏ trong quá trình xử lý request. Nó **không tự tồn tại** ở request HTTP tiếp theo. Forward trong Servlet container có thể cùng dùng một request; redirect là request mới nên request attribute cũ không đi theo.

**Không nhầm request attribute với Spring `@RequestScope`:** cả hai liên quan request scope, nhưng `@RequestScope` quản lý vòng đời bean Spring, trong khi `@RequestAttribute` đọc thuộc tính do Servlet API lưu dưới một key. Spring không tự lấy mọi bean request-scoped làm request attribute cùng tên.

## 4. `@SessionAttribute`: đọc dữ liệu đã lưu qua các request

Cú pháp:

```java
@GetMapping("/preferences")
public String preferences(
        @SessionAttribute(name = "language", required = false) String language) {
    return "language=" + (language == null ? "none" : language);
}
```

- `@SessionAttribute("language")` tìm attribute trong **HTTP session**. Nó không đọc một cookie `language` trực tiếp; thông thường cookie `JSESSIONID` hoặc cơ chế session id khác giúp server xác định session.
- `required` mặc định là `true`: thiếu session hoặc thiếu key sẽ gây lỗi resolve tham số. Dùng `required=false` khi giá trị có thể chưa được thiết lập.
- `value` và `name` là alias; nên khai báo tên tường minh. Không có `defaultValue` trong annotation này.
- `@SessionAttribute` phù hợp khi **đọc** trạng thái session do các thành phần khác quản lý. Để **ghi/xóa**, dùng `HttpSession`, `WebRequest` hoặc dịch vụ quản lý session phù hợp.
- Thời hạn tồn tại phụ thuộc timeout, invalidate, cookie/session id và backend session. Không phải dữ liệu bền vững hay luôn còn sau khi server restart.
- Nếu hai request đồng thời sửa chung một object trong session, có thể phát sinh race condition; session không mặc nhiên đảm bảo thread-safety cho những object mutable.

Ví dụ quản lý trực tiếp:

```java
@PostMapping("/set-language")
public String setLanguage(@RequestParam("language") String language,
                          HttpSession session) {
    session.setAttribute("language", language);
    return "saved";
}

@PostMapping("/clear-language")
public String clearLanguage(HttpSession session) {
    session.removeAttribute("language");
    return "removed";
}
```

Đây là các **method minh họa** đặt trong `@RestController` có cấu hình Spring MVC; không phải chương trình Java chạy độc lập. Khi một method yêu cầu đối số `HttpSession`, servlet có thể tạo session nếu chưa có. Nếu cần chỉ kiểm tra session đã tồn tại mà không tạo mới:

```java
HttpSession existing = request.getSession(false);
if (existing != null) {
    existing.removeAttribute("language");
}
```

Đoạn trên giả sử đang có biến `HttpServletRequest request`. `getSession(false)` trả `null` nếu request chưa có session.

## 5. Ví dụ ứng dụng Spring Boot 3.x + Java 17 trở lên

Ví dụ dưới đây minh họa đồng thời **request attribute do Filter cung cấp** và **session attribute do controller ghi/đọc**. Dùng một dự án Spring Boot Servlet/MVC có dependency `spring-boot-starter-web`. Với phần test ở sau, thêm `spring-boot-starter-test`.

Ở Spring Boot 3.x dùng namespace `jakarta.servlet.*`; nếu bạn đang ở Boot 2.x sẽ gặp `javax.servlet.*` và cần điều chỉnh imports theo phiên bản.

Tạo **`src/main/java/demo/web/ContextAttributesApplication.java`**:

```java
package demo.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.SessionAttribute;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class ContextAttributesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextAttributesApplication.class, args);
    }

    @Bean
    OncePerRequestFilter traceAttributeFilter() {
        return new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain)
                    throws ServletException, IOException {

                String traceId = request.getHeader("X-Trace-Id");
                if (traceId == null || traceId.isBlank()) {
                    traceId = "generated-demo";
                }

                request.setAttribute("traceId", traceId);
                try {
                    chain.doFilter(request, response);
                } finally {
                    request.removeAttribute("traceId");
                }
            }
        };
    }
}

@RestController
class ContextController {

    @GetMapping("/api/context/request")
    String requestContext(@RequestAttribute("traceId") String traceId) {
        return "traceId=" + traceId;
    }

    @GetMapping("/api/context/optional")
    String optionalRequestContext(
            @RequestAttribute(name = "feature", required = false) String feature) {
        return "feature=" + (feature == null ? "none" : feature);
    }

    @PostMapping("/api/context/session")
    String rememberLanguage(@RequestParam("language") String language,
                            HttpSession session) {
        session.setAttribute("language", language);
        return "stored=" + language;
    }

    @GetMapping("/api/context/session")
    String readLanguage(
            @SessionAttribute(name = "language", required = false)
            String language) {
        return "language=" + (language == null ? "none" : language);
    }

    @GetMapping("/api/context/session-required")
    String readRequiredLanguage(@SessionAttribute("language") String language) {
        return "language=" + language;
    }

    @PostMapping("/api/context/session/remove")
    String removeLanguage(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute("language");
        }
        return "removed";
    }
}
```

**Giải thích hoạt động:**

1. Spring Boot đăng ký bean `OncePerRequestFilter` vào Servlet filter chain theo cơ chế autoconfiguration; mỗi request dispatch được xử lý phù hợp với semantics của filter.
2. Filter lấy header `X-Trace-Id` hoặc dùng giá trị mẫu `generated-demo`, rồi đặt `request.setAttribute("traceId", ...)`. Nó gọi `chain.doFilter` để tiếp tục tới Spring MVC.
3. Khi MVC gặp `@RequestAttribute("traceId")`, Spring lấy attribute mà filter vừa đặt. Controller không cần tự đọc Servlet API.
4. Block `finally` dọn attribute sau khi downstream kết thúc. Việc dọn này **không ảnh hưởng** giá trị mà controller đã nhận khi chạy trước đó.
5. POST session lưu `language`; một GET khác chỉ đọc lại khi client gửi đúng session id. GET dùng `required=false` trả `none` khi chưa có lựa chọn.
6. `/api/context/session-required` khác endpoint optional: nếu thiếu attribute, argument resolution thất bại trước khi method body chạy.

Filter trên dùng header do client cung cấp **chỉ để trình diễn dữ liệu trace**. Không được coi header tự khai là bằng chứng tenant, user id hoặc quyền truy cập. Ở hệ thống thật, ID do hạ tầng tin cậy cấp cần cơ chế kiểm soát nguồn và logging rõ ràng.

Trong dự án Spring Boot 3.x dùng Gradle/Groovy, dependency tối thiểu liên quan bài (khi project đã có Boot plugin, dependency management và repository):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khởi chạy project qua `./gradlew bootRun` (hoặc `./mvnw spring-boot:run` khi dự án dùng Maven). Đoạn dependency này là **mảnh cấu hình build**, không phải toàn bộ file `build.gradle` độc lập.

### Quan sát bằng HTTP client

Sau khi chạy ứng dụng trên `localhost:8080`, thực hiện trong shell Bash (các lệnh `curl` chuẩn):

```bash
curl -sS -H 'X-Trace-Id: demo-42' http://localhost:8080/api/context/request
curl -sS http://localhost:8080/api/context/request
curl -sS http://localhost:8080/api/context/optional
curl -sS http://localhost:8080/api/context/session
curl -sS -c cookies.txt -X POST -d 'language=vi' http://localhost:8080/api/context/session
curl -sS -b cookies.txt http://localhost:8080/api/context/session
curl -sS -b cookies.txt -X POST http://localhost:8080/api/context/session/remove
curl -sS -b cookies.txt http://localhost:8080/api/context/session
```

Body trả về tương ứng, **nếu các endpoint không bị filter/security khác can thiệp**:

```text
traceId=demo-42
traceId=generated-demo
feature=none
language=none
stored=vi
language=vi
removed
language=none
```

`-c cookies.txt` ghi cookie từ phản hồi POST, và `-b cookies.txt` gửi lại cookie ấy để server xác định cùng session. Nếu gọi GET mới **không gửi cookie session**, không có bảo đảm lấy lại `language=vi`. Đây là kết quả body minh họa, không phải stdout của lệnh `javac`. Không commit file `cookies.txt` vào repository.

Trong những client tự theo redirect hoặc ứng dụng có middleware kiểm tra authentication, cần dùng `curl -i` để quan sát HTTP status, header `Set-Cookie` và cookie gửi lại.

## 6. Đặt request attribute bằng `HandlerInterceptor`

Khi cần thêm dữ liệu **sau khi Spring MVC đã chọn handler** nhưng trước khi method chạy, `HandlerInterceptor#preHandle` là một điểm mở rộng phù hợp. Ví dụ rút gọn:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

class TenantInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        String resolvedTenant = "tenant-demo"; // Thay bằng bộ phân giải đáng tin cậy.
        request.setAttribute("tenant", resolvedTenant);
        return true;
    }
}
```

Đăng ký interceptor trong cấu hình MVC (đoạn dưới là **mảnh class configuration**):

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcInterceptors implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TenantInterceptor())
                .addPathPatterns("/api/tenant/**");
    }
}
```

Controller được interceptor hỗ trợ có thể khai báo:

```java
@GetMapping("/api/tenant/info")
public String tenantInfo(@RequestAttribute("tenant") String tenant) {
    return "tenant=" + tenant;
}
```

Nếu ghép đúng ba fragment trên vào một dự án, `GET /api/tenant/info` sẽ nhận `tenant-demo`. Trong ứng dụng thật, giá trị tenant phải được xác định từ nguồn đáng tin (ví dụ principal đã xác thực hoặc context đã xác thực); đoạn này chỉ mô phỏng nơi đặt attribute.

Khác biệt quan trọng:

- **Filter** tham gia Servlet chain, có thể chạy trước khi Spring MVC chọn handler; có thể áp dụng cả request chưa match controller, static content và một số dispatch type tùy cấu hình.
- **Interceptor** là thành phần của Spring MVC, chạy quanh handler đã được chọn; không tương đương lớp bảo vệ ở Servlet chain.
- **MethodArgumentResolver** là cơ chế Spring dùng để đưa giá trị vào tham số controller, trong đó hai annotation ở bài này có resolver tương ứng. Nếu chỉ cần truyền giá trị đã lưu ở request/session, thường **không cần** viết custom resolver.

Đừng đặt logic bảo mật bắt buộc chỉ trong một interceptor rồi cho rằng nó bảo vệ toàn bộ URL. Những request không đi qua handler MVC dự kiến có thể không đi qua interceptor đó.

## 7. `@SessionAttribute` khác `@SessionAttributes` (có “s”)

Hai annotation tên gần giống nhưng có vai trò rất khác:

| `@SessionAttribute` | `@SessionAttributes` |
| --- | --- |
| Đặt ở **tham số method** | Đặt trên **class controller** |
| **Đọc** một HTTP session attribute đã có | Quản lý **model attributes** của quy trình controller và lưu chúng tạm trong session |
| Không tự tạo/cập nhật attribute | Có thể “promote” model attribute tương ứng vào session |
| `required = true/false` | Cấu hình theo `names`/`types`, không có `required` tương tự |
| Thích hợp đọc lựa chọn người dùng, context lâu hơn một request | Thích hợp nhiều bước của một form/workflow |
| Xóa thủ công bằng `HttpSession#removeAttribute` hoặc API quản lý | Kết thúc hội thoại model/session bằng `SessionStatus#setComplete()` |

Ví dụ minh họa workflow model/session (các đoạn nằm trong cùng controller):

```java
@Controller
@SessionAttributes("draft")
class DraftController {

    @ModelAttribute("draft")
    public Draft draft() {
        return new Draft();
    }

    @PostMapping("/draft/finish")
    public String finish(@ModelAttribute("draft") Draft draft,
                         SessionStatus status) {
        // Xử lý draft hợp lệ rồi hoàn thành workflow.
        status.setComplete();
        return "redirect:/done";
    }
}
```

`Draft` ở đây là kiểu domain do ứng dụng tự định nghĩa; ví dụ chỉ minh họa luồng MVC, **không phải source file biên dịch độc lập**. Với `@SessionAttributes`, tên lưu trữ session thực tế có thể được framework quản lý theo cơ chế model của controller, nên code khác không nên phụ thuộc vào tên key nội bộ đó. `SessionStatus#setComplete()` **không đồng nghĩa invalidate toàn bộ HTTP session** và không xóa mọi thuộc tính khác của người dùng.

Nếu yêu cầu đơn giản là đọc key do filter hoặc controller đặt vào session, chọn `@SessionAttribute`. Nếu mục tiêu là đưa model qua nhiều bước form với lifecycle rõ, `@SessionAttributes` và `SessionStatus` phù hợp hơn.

## 8. `required`, `Optional`, thiếu attribute và lỗi thường gặp

Ví dụ các khai báo:

```java
// Bắt buộc: không có attribute -> exception khi resolve tham số.
@RequestAttribute("correlationId") String id

// Tùy chọn: không có -> null.
@RequestAttribute(name = "correlationId", required = false) String id

// Tùy chọn ở dạng đối tượng:
@RequestAttribute("correlationId") Optional<String> id

// Không có HTTP session hoặc không có key -> cho phép null:
@SessionAttribute(name = "language", required = false) String language
```

Các dòng trên là **chữ ký tham số** để so sánh, không phải một method Java hợp lệ khi đứng riêng. Với `Optional<String>` hãy import `java.util.Optional`.

Các vấn đề thường phát sinh:

1. **Key không khớp**: filter đặt `request.setAttribute("traceId", ...)` nhưng controller yêu cầu `@RequestAttribute("requestId")`.
2. **Đặt quá muộn**: thuộc tính được thêm sau khi controller đã được gọi hoặc chỉ trong một nhánh interceptor.
3. **Không cùng scope**: lưu `request` nhưng đọc `session`, hoặc lưu session trên request A rồi request B không mang session id.
4. **Sai kiểu dữ liệu**: đặt một object domain hoặc `Integer` nhưng tham số khai báo kiểu không phù hợp; không mặc định diễn giải JSON thành object.
5. **Thiếu dữ liệu nhưng vẫn dùng kiểu primitive**: hãy dùng reference type hoặc `Optional<T>` cho trường hợp nullable.
6. **Giả định status code cứng**: thông thường lỗi thuộc tính bắt buộc thiếu được Spring MVC xử lý như lỗi binding với phản hồi 400, nhưng `@ControllerAdvice`, exception resolver và bộ lọc bảo mật có thể thay đổi kết quả HTTP. Xác minh trong test của ứng dụng.
7. **Rò rỉ dữ liệu giữa người dùng**: đặt context theo user trong singleton field hoặc static variable rồi nhầm là request-scoped. Controller mặc định thường là singleton; dữ liệu request phải nằm ở method arguments/request scope, session và tài nguyên chia sẻ phải được bảo vệ khỏi tranh chấp.
8. **Giả định `@RequestAttribute` là dữ liệu client gửi**: HTTP header/parameter không được Spring tự chuyển thành request attribute tương ứng.

## 9. Ngữ cảnh sẵn có: lấy khi nào và dùng cách nào?

Spring MVC hỗ trợ inject trực tiếp các kiểu Servlet/Spring quen thuộc vào method, ví dụ:

```java
@GetMapping("/context/details")
public String details(HttpServletRequest request, HttpSession session) {
    Object currentTrace = request.getAttribute("traceId");
    Object language = session.getAttribute("language");
    return String.valueOf(currentTrace) + "/" + String.valueOf(language);
}
```

Đây là **một method minh họa** trong controller. Lưu ý tham số `HttpSession session` có thể tạo session dù mục tiêu ban đầu chỉ đọc; nếu không muốn tạo, thay bằng `HttpServletRequest request` rồi gọi `request.getSession(false)`.

Dùng kiểu tham số rõ (`@RequestAttribute`, `@SessionAttribute`) khi chỉ cần một hoặc hai giá trị, vì method signature biểu lộ phụ thuộc và dễ test. Dùng `HttpServletRequest`, `HttpSession` hoặc `WebRequest` khi cần đọc/ghi nhiều thuộc tính, kiểm tra sự tồn tại, xóa hoặc xử lý lifecycle.

Một số cơ chế liên quan cần phân biệt:

- `RequestContextHolder` giữ `RequestAttributes` gắn với thread thực thi request theo cơ chế Spring. Đây là tiện ích cho code nằm sâu trong luồng web nhưng làm tăng phụ thuộc ngầm; tránh dựa vào nó trong service nếu có thể truyền giá trị tường minh.
- Sau khi chuyển việc sang thread khác (ví dụ `@Async`, `CompletableFuture` hoặc executor), context gắn với thread **không mặc nhiên được truyền đi**; tránh lấy request/session tùy tiện từ worker thread, cần thiết kế context propagation phù hợp và chỉ truyền dữ liệu cần thiết.
- `@RequestScope` và `@SessionScope` quản lý **Spring bean theo scope**, khác với map thuộc tính Servlet trực tiếp dù có cùng khái niệm vòng đời.
- `ServletContext#getAttribute` là dữ liệu chia sẻ ở cấp ứng dụng, không phải request riêng hay user session; cần cân nhắc concurrency và lifecycle khi cập nhật.
- `SecurityContextHolder` và `@AuthenticationPrincipal` thuộc cơ chế của Spring Security khi được cấu hình; không tự khẳng định rằng một attribute từ request/session đã được xác thực.

Bảng vòng đời dễ nhớ:

```text
Request A ----------------------------------X       (request attribute hết scope)
     Session S ===================================X  (tồn tại đến timeout/invalidate)
Request B -----------X                           |
Request C -----------------X                     |
ServletContext ====================================== (cấp ứng dụng)
```

Các hình dạng thời gian trên chỉ diễn đạt **quan hệ vòng đời**, không đại diện timeout cụ thể. Một session có thể hết hạn giữa hai request; khi triển khai nhiều node, nơi lưu session phải nhất quán hoặc dùng cơ chế phù hợp (sticky session, store chung, Spring Session khi cần).

## 10. Bảo mật và tính đúng đắn trong ứng dụng thật

Request/session attributes giúp truyền context thuận tiện nhưng **không tự động là nguồn tin cậy**:

- Giá trị lấy trực tiếp từ `X-User-Id`, `X-Tenant` hoặc query parameter mà chưa kiểm tra có thể bị giả mạo. Nếu attribute quyết định phân quyền, trước hết phải xác thực nguồn và ràng buộc với principal đã được Spring Security xác nhận.
- Không lưu mật khẩu, token thô, PII không cần thiết hoặc object lớn vào session; cân nhắc thời gian sống, serialization và chính sách bảo mật. Session ID phải được bảo vệ; thực tế cần HTTPS, cookie `HttpOnly`/`Secure`/`SameSite` phù hợp và chống session fixation.
- Không dùng một Java mutable map/object trong session rồi mặc định rằng nhiều request đồng thời có thể sửa an toàn. Thiết kế bất biến, đồng bộ hóa thích hợp hoặc cập nhật qua lớp lưu trữ có tính nhất quán.
- Sau logout hoặc revoke cần xóa trạng thái liên quan; session invalidation hoặc hệ thống authentication/session management phải chịu trách nhiệm. Xóa `@SessionAttributes` của một workflow không đồng nghĩa đăng xuất.
- Không dùng request attribute làm kho lưu dữ liệu bền vững hoặc qua HTTP redirect; dùng URL/flash attribute/session hoặc store chuyên dụng theo đúng mục tiêu.
- Không đưa stack trace hoặc tên nội bộ attribute ra API response trong production; xử lý lỗi theo hợp đồng HTTP/API rõ ràng.

## 11. Kiểm thử với `MockMvc`

Trong một dự án đã có Spring Boot test, tạo **`src/test/java/demo/web/ContextAttributesApplicationTests.java`**:

```java
package demo.web;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextAttributesApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void filterProvidesRequestAttribute() throws Exception {
        mvc.perform(get("/api/context/request")
                        .header("X-Trace-Id", "abc-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("traceId=abc-123"));

        mvc.perform(get("/api/context/request")
                        .param("traceId", "value-from-query"))
                .andExpect(status().isOk())
                .andExpect(content().string("traceId=generated-demo"));
    }

    @Test
    void sessionAttributeNeedsTheSameSession() throws Exception {
        MvcResult saved = mvc.perform(post("/api/context/session")
                        .param("language", "vi"))
                .andExpect(status().isOk())
                .andExpect(content().string("stored=vi"))
                .andReturn();

        HttpSession servletSession = saved.getRequest().getSession(false);
        assertNotNull(servletSession);
        MockHttpSession session = (MockHttpSession) servletSession;

        mvc.perform(get("/api/context/session").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("language=vi"));

        mvc.perform(get("/api/context/session"))
                .andExpect(status().isOk())
                .andExpect(content().string("language=none"));

        mvc.perform(post("/api/context/session/remove").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("removed"));

        mvc.perform(get("/api/context/session").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("language=none"));
    }
}
```

Chạy `./gradlew test` hoặc `./mvnw test`. Khi ứng dụng ví dụ chỉ có Spring MVC và các starter như đã nêu, kỳ vọng **hai bài test pass**. Test đầu chứng minh query parameter `traceId` không ghi đè request attribute do filter đặt. Test thứ hai chứng minh session tồn tại qua nhiều request **khi tái sử dụng cùng `MockHttpSession`**, và trạng thái bị xóa khi gọi endpoint remove.

**Giới hạn:** test tích hợp `MockMvc` sử dụng môi trường Spring test, không mô phỏng hoàn toàn proxy, network, cookie policy của browser hay cluster nhiều node. Nếu dự án bổ sung Spring Security, CSRF, filter custom hoặc cấu hình lỗi riêng, test cần setup authentication, CSRF và filter chain theo hệ thống thực tế.

Có thể test thiếu request attribute một cách độc lập bằng `MockMvcBuilders.standaloneSetup(new ContextController())` **không đăng ký filter** và gọi `GET /api/context/request`; nếu `required=true`, controller không được chạy. Khi kiểm thử session bắt buộc, gọi `/api/context/session-required` với session mới hoặc không có session và xác minh HTTP status/error contract của ứng dụng.

## 12. Quy trình chọn annotation trong dự án

1. **Nguồn dữ liệu client gửi?** Sử dụng `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@CookieValue`, `@RequestBody` theo định dạng, không dùng `@RequestAttribute` để mong Spring tự đọc HTTP input.
2. **Đã có object do filter/interceptor tạo trong cùng request?** Đặt bằng `request.setAttribute` trước controller rồi đọc `@RequestAttribute`; quyết định rõ attribute bắt buộc hay tùy chọn.
3. **Cần lựa chọn/trạng thái qua nhiều request của cùng phiên HTTP?** Ghi/xóa bằng `HttpSession` hoặc cơ chế session đã chọn, đọc bằng `@SessionAttribute`.
4. **Đang làm form nhiều bước với Spring MVC model?** Cân nhắc `@SessionAttributes` trên controller và `SessionStatus#setComplete()`.
5. **Cần user đã xác thực hoặc quyền truy cập?** Dùng Spring Security và principal đã được kiểm tra; attribute tùy ý không đủ để quyết định quyền.
6. **Cần làm việc bất đồng bộ hoặc liên dịch vụ?** Đóng gói context cần thiết thành dữ liệu truyền tường minh hoặc cơ chế propagation phù hợp, không giả định request-bound ThreadLocal hoặc HTTP session tự đi qua thread/process.

## 13. Bài tập tự kiểm tra

- **Tình huống 1:** Filter đặt `request.setAttribute("region", "apac")`. Controller khai báo `@RequestParam("region")`; request không có query parameter. Điều gì xảy ra? Hãy sửa controller bằng annotation đúng và kiểm thử.
- **Tình huống 2:** Client POST chọn `language=en`, GET tiếp theo không có cookie session. Vì sao `@SessionAttribute(name="language", required=false)` có thể trả `null`?
- **Tình huống 3:** Controller khai báo `@RequestAttribute("tenant")` bắt buộc, nhưng interceptor chỉ đặt attribute cho `/api/admin/**`. Request vào endpoint không thuộc pattern sẽ có hành vi gì? Thiết kế test và thống nhất pattern.
- **Tình huống 4:** Form tạo draft nhiều bước dùng `@SessionAttributes("draft")`. Sau khi hoàn tất, gọi `status.setComplete()` có xóa luôn thuộc tính `language` đang có ở session không? Giải thích.
- **Tình huống 5:** Một `@Async` service cần trace id. Hãy so sánh việc truyền `String traceId` như tham số với đọc `RequestContextHolder` từ worker thread. Chỉ ra trường hợp dữ liệu có thể không tồn tại.

## Tài liệu tham khảo chính thức

- [Spring MVC — `@RequestAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestattrib.html)
- [Spring MVC — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html)
- [Spring MVC — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html)
- [Spring MVC — Handler Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring MVC — Interception](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html)
- [Spring Framework Javadoc — `@RequestAttribute`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/RequestAttribute.html)
- [Spring Framework Javadoc — `@SessionAttribute`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/SessionAttribute.html)
