# Servlet container, Filter chain và điểm vào DispatcherServlet trong Spring Web MVC

## 1. Mục tiêu và phạm vi

Khi trình duyệt gọi `GET /api/hello?name=Lan`, phương thức `@GetMapping` không phải thành phần đầu tiên nhận request. Trong ứng dụng Spring Web MVC chạy trên Servlet stack, **Servlet container** tiếp nhận request; những **Servlet Filter** được đăng ký phù hợp có cơ hội xử lý; request sau đó mới đến **`DispatcherServlet`** để Spring MVC tìm controller và tạo response.

Sau bài này, bạn có thể:
- Mô tả đúng ranh giới giữa HTTP server/Servlet container, Filter chain và Spring MVC.
- Đọc được luồng `client → container → filters → DispatcherServlet → handler → response`, cả nhánh bị chặn và nhánh lỗi.
- Phân biệt Servlet `Filter` với Spring MVC `HandlerInterceptor` và Spring Security filter chain.
- Tự đăng ký filter bằng `FilterRegistrationBean` trong Spring Boot, kiểm soát URL pattern, thứ tự, dispatcher type.
- Hiểu tại sao `OncePerRequestFilter` không có nghĩa đơn giản là chạy đúng một lần trong *mọi* lần dispatch của cả request.
- Kiểm tra luồng bằng ứng dụng Java 17 + Spring MVC thực thi được và test MockMvc.

Bài tập trung vào **Spring Web MVC dựa trên Jakarta Servlet** (Spring Framework 6.x / Spring Boot 3.x), không mô tả WebFlux reactive pipeline. Các ví dụ chạy dùng Spring Boot để khởi động embedded Tomcat; nguyên tắc Servlet/Filter/DispatcherServlet vẫn áp dụng nếu deploy Spring MVC dưới dạng WAR vào container độc lập.

## 2. Ai sở hữu phần nào của request?

```text
             +------------------- HTTP client --------------------+
             | GET /api/hello?name=Lan                          |
             +----------------------------+----------------------+
                                          |
                               (reverse proxy nếu có)
                                          |
                                          v
           +------------ Servlet container (Tomcat) ------------+
           |  Kết nối HTTP, parse request, chọn Servlet mapping |
           |                                                     |
           |  Servlet Filter chain cho dispatch hiện tại         |
           |    Filter A: trước chain.doFilter(...)              |
           |      Filter B: trước chain.doFilter(...)            |
           |        +-------------------------------------+      |
           |        | DispatcherServlet                  |      |
           |        |  HandlerMapping tìm route          |      |
           |        |  HandlerInterceptor.preHandle      |      |
           |        |  HandlerAdapter gọi controller     |      |
           |        |  Chuyển giá trị trả về thành body  |      |
           |        |  (hoặc ViewResolver render view)   |      |
           |        +-------------------------------------+      |
           |      Filter B: sau chain.doFilter(...)              |
           |    Filter A: sau chain.doFilter(...)                |
           +----------------------------+------------------------+
                                        |
                                        v
                                 HTTP response
```

Sơ đồ biểu diễn đường đi **thành công, đồng bộ** của một request được các filter cho đi tiếp. Nó không phải thứ tự cố định cho mọi cấu hình: filter có thể trả response sớm, servlet có thể khác `DispatcherServlet`, exception có thể tạo error dispatch, còn async có thể bổ sung dispatch về sau.

| Tầng | Đơn vị quản lý | Vai trò | Được biết trước thông tin gì? |
|---|---|---|---|
| Servlet container | Tomcat, Jetty, một container Jakarta Servlet tương thích | Nhận HTTP, quản lý Servlet/Filter, mapping, dispatch, request/response object, thread hoặc async lifecycle. | URI, method, headers, mapping và cấu hình container. |
| Servlet `Filter` | Servlet container | Bọc request/response, áp dụng chính sách chung, cho qua bằng `chain.doFilter` hoặc kết thúc sớm. | `HttpServletRequest` và `HttpServletResponse`; chưa cần biết handler Spring MVC. |
| `DispatcherServlet` | Spring MVC; được đăng ký như Servlet với container | Điểm vào tập trung (front controller) của Spring MVC; điều phối tới các thành phần Spring. | Spring `WebApplicationContext`, mappings và cấu hình MVC. |
| `HandlerMapping` | Spring MVC | Tìm handler khớp request; có thể trả kèm interceptor chain. | Những mapping đã đăng ký; method/path/headers/params theo điều kiện mapping. |
| `HandlerAdapter` | Spring MVC | Gọi handler được chọn, resolve arguments và xử lý return value. | Chữ ký phương thức/controller cùng các adapter, resolver, converter. |
| `HandlerInterceptor` | Spring MVC | Hook quanh xử lý handler đã được Spring MVC map, ví dụ `preHandle`, `postHandle`, `afterCompletion`. | Handler được chọn; không thay thế bộ lọc của Servlet container. |

**Không đồng nhất Servlet Filter với Spring MVC interceptor.** Filter chạy ở tầng container, có thể áp dụng cho request không vào controller. Interceptor thuộc Spring MVC, gắn vào chuỗi xử lý handler sau bước tìm mapping; phạm vi callback và exception/async cũng khác.

## 3. Servlet container thực hiện những bước nào?

Đối với HTTP request vào ứng dụng Servlet:

1. Container nhận kết nối/request, parse HTTP, quản lý lifecycle của các object `HttpServletRequest`/`HttpServletResponse`, xác định context path và Servlet mapping.
2. Từ URL pattern, Servlet name, thứ tự filter và **dispatcher type** hiện tại, container chọn những Filter registration phù hợp.
3. Container tạo `FilterChain` và gọi `doFilter(request,response,chain)` của filter đầu tiên. Mỗi filter có quyền gọi `chain.doFilter(...)` để chuyển quyền xử lý cho phần tử tiếp theo.
4. Sau filter cuối, container gọi Servlet được map. Với Spring MVC, thường là `DispatcherServlet.service(...)` và các xử lý framework liên quan.
5. Khi Servlet kết thúc xử lý đồng bộ, lời gọi `chain.doFilter(...)` trả về theo ngăn xếp; mã sau nó trong từng filter được chạy từ trong ra ngoài. Container hoàn tất response; response có thể đã commit trước đó.

**Quan trọng:** "đi vào Servlet" là quá trình container thực hiện Servlet mapping, khác với "chọn controller" do `HandlerMapping` bên trong Spring MVC thực hiện. Một filter có thể chạy trước cả khi Spring xác định có controller nào khớp request hay không. Nếu không có MVC route phù hợp, Spring MVC có thể trả 404; các filter đã được gọi vẫn có thể chạy nhánh `finally` của chúng.

### Mapping của Servlet và mapping của filter

- Servlet mapping `/` thường cho `DispatcherServlet` xử lý route ứng dụng, nhưng cấu hình có thể dùng một prefix khác, ví dụ `/mvc/*`.
- Filter mapping `/*` thường bao phủ các request trong web application. Có thể giới hạn bằng `/api/*` hoặc ánh xạ theo servlet name.
- Filter mapping là cấu hình của **container**, độc lập với `@GetMapping` hay `@RequestMapping`.
- URL có context path, servlet path và path info khác nhau. Đừng nhầm `request.getRequestURI()` (thường chứa context path, không chứa query) với path template Spring MVC hay `getQueryString()`.
- Reverse proxy, load balancer và container có thể xử lý request target hoặc forwarded headers trước khi request đến Spring. Không lấy nguyên header do client tự gửi làm bằng chứng đáng tin về origin/protocol nếu hệ thống proxy chưa cấu hình trust đúng.

### Filter chain là ngăn xếp gọi nhau

Với hai filter A rồi B:

```text
A: before
  B: before
    DispatcherServlet -> Controller -> Response
  B: after
A: after
```

Pseudo-code:

```java
// Đây là pseudo-code về flow, không phải file Java chạy độc lập.
void doFilter(Request request, Response response, FilterChain chain) {
    before(request);
    try {
        chain.doFilter(request, response);
    } finally {
        after(response);
    }
}
```

Nếu B **không gọi** `chain.doFilter`, C hoặc `DispatcherServlet` không được gọi trên nhánh đó; container có thể trả response do B tự tạo. Điều này hợp lệ khi B thực hiện từ chối truy cập, chặn rate limit hay trả CORS preflight response theo chính sách đã thiết kế. Bắt buộc phải xác định status và response cần trả, không đơn giản bỏ qua chain rồi để client nhận kết quả khó hiểu.

### Hủy request, exception và response commit

- `chain.doFilter` có thể ném `ServletException` hoặc `IOException`. `finally` vẫn chạy, nhưng không có nghĩa request đã xử lý thành công.
- Nếu response đã được commit (headers/body đã gửi), filter không thể tùy ý thay status/header hay viết lại body.
- Một filter có thể bọc request/response bằng wrapper để điều chỉnh hành vi, nhưng cần tuân thủ contract Servlet, xử lý stream cẩn thận và tránh đọc cạn request body trước controller.
- Khối `finally` thường phù hợp để giải phóng context/ThreadLocal, đo thời gian và hoàn thành instrumentation; cần tránh log dữ liệu nhạy cảm.

## 4. `DispatcherServlet` — front controller của Spring MVC

`DispatcherServlet` là một Servlet thật, được container gọi **sau các filter đã cho phép request đi tiếp**. Nó không tự tiếp nhận TCP socket, không quyết định thứ tự Servlet filters và không thay container quản lý Servlet lifecycle.

Bên trong Spring MVC, đường xử lý điển hình của request đồng bộ là:

```text
DispatcherServlet
    |
    +--> tìm HandlerExecutionChain bằng HandlerMapping
    |      |-- handler (thường là HandlerMethod)
    |      +-- interceptor(s)
    |
    +--> HandlerInterceptor.preHandle(...)
    |      |-- false: dừng trước khi gọi handler
    |      +-- true: tiếp tục
    |
    +--> HandlerAdapter.handle(...)
    |      +-- resolve @PathVariable / @RequestParam / @RequestBody ...
    |      +-- convert/bind/validate dữ liệu khi cấu hình phù hợp
    |      +-- gọi controller
    |      +-- xử lý return value
    |
    +--> Response path
    |      |-- @ResponseBody/@RestController:
    |      |      HttpMessageConverter ghi JSON/text/...
    |      +-- MVC view:
    |             ModelAndView -> ViewResolver -> render
    |
    +--> postHandle/afterCompletion tương ứng với lifecycle
           hoặc HandlerExceptionResolver khi có exception
```

Các thành phần thường gặp:

| Thành phần MVC | Công dụng |
|---|---|
| `RequestMappingHandlerMapping` | Đọc các mapping kiểu `@GetMapping`, `@PostMapping`, `@RequestMapping` và tìm handler. |
| `RequestMappingHandlerAdapter` | Gọi annotated controller method và dùng argument/return-value resolvers. |
| `HandlerMethodArgumentResolver` | Cấp tham số controller như `@RequestParam`, `@PathVariable`, `@RequestBody`. |
| `HttpMessageConverter` | Chuyển request body thành object hoặc object trả về thành body HTTP, ví dụ JSON. |
| `ViewResolver` | Chọn view để render trong MVC trả trang; API trả JSON thường không cần resolve view. |
| `HandlerExceptionResolver` | Thử giải quyết exception ở tầng MVC; ví dụ `@ExceptionHandler` hoặc `@ControllerAdvice`. |
| `HandlerInterceptor` | Hook quanh handler MVC; chỉ hoạt động trong luồng handling của MVC đã cấu hình. |

Đường xử lý thực tế có thêm nhiều bước, ví dụ multipart, locale, conditional request, async handling, và trường hợp không tìm thấy handler. **Không mặc định** mỗi request đều đi qua toàn bộ callback hoặc đều dùng `ViewResolver`. Với `@RestController` trả `Map`, response body thường được tạo ngay bởi `HttpMessageConverter` khi adapter xử lý return value; `postHandle` không phải điểm tốt để sửa JSON body đã được serialize.

### Nếu không có handler?

Spring MVC có thể trả 404 hoặc ném exception tùy cấu hình và loại route. Tuy nhiên filter đã khớp và gọi `chain.doFilter` vẫn bao quanh request; Spring Security filter hoặc custom filter ở container có thể từ chối trước khi MVC kịp chọn handler. Vì vậy khi gỡ lỗi 401/403, không nên vội kết luận `@GetMapping` sai.

## 5. Ví dụ chạy được: tự quan sát filter trước và sau controller

Ví dụ dùng **Java 17**, Spring Boot **3.5.16**, Spring MVC và Gradle. Spring Boot được dùng để cấu hình embedded Tomcat và đăng ký `DispatcherServlet` tự động. Trong một project dùng Spring Framework MVC thuần, bạn phải tự đăng ký Servlet vào container (bằng `web.xml`, `WebApplicationInitializer` hoặc Servlet initializer tương ứng).

### 5.1. Cấu trúc project

```text
servlet-pipeline-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/pipeline/
    │   │   ├── PipelineApplication.java
    │   │   └── web/
    │   │       ├── HelloController.java
    │   │       ├── TraceFilter.java
    │   │       └── TraceFilterConfig.java
    │   └── resources/application.properties
    └── test/java/com/example/pipeline/
        └── HelloControllerTest.java
```

Nếu tạo project từ https://start.spring.io/, chọn Gradle/Groovy, Java 17, Spring Boot 3.5.x và dependency **Spring Web**; Gradle Wrapper được Initializr tạo sẵn. Các đoạn sau là nội dung hoàn chỉnh cho những file chính; package phải trùng với đường dẫn dưới `src/main/java` hoặc `src/test/java`.

`settings.gradle`:

```groovy
rootProject.name = 'servlet-pipeline-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` trong Spring Boot 3.5.x kéo vào Spring MVC, Jackson cho JSON và embedded Tomcat. Spring Boot quản lý phiên bản framework/transitive dependencies. Nếu ứng dụng đã dùng một BOM/platform riêng, cần tuân thủ mô hình dependency management của project thay vì copy nguyên cấu hình ví dụ.

`src/main/resources/application.properties`:

```properties
spring.application.name=servlet-pipeline-demo
server.port=8080
```

### 5.2. Lớp khởi động

`src/main/java/com/example/pipeline/PipelineApplication.java`:

```java
package com.example.pipeline;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PipelineApplication {

    public static void main(String[] args) {
        SpringApplication.run(PipelineApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt auto-configuration và component scan từ package `com.example.pipeline` xuống các subpackage. Spring Boot tạo/đăng ký `DispatcherServlet` cùng embedded server khi phát hiện Servlet web stack phù hợp; đây là lý do chúng ta không phải viết `web.xml` trong ví dụ này.

### 5.3. Controller được `DispatcherServlet` tìm thấy

`src/main/java/com/example/pipeline/web/HelloController.java`:

```java
package com.example.pipeline.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(name = "name", defaultValue = "bạn") String name) {

        System.out.println("controller: handle name=" + name);
        return Map.of("message", "Xin chào, " + name + "!");
    }
}
```

Với `GET /api/hello?name=Lan`, annotated handler này được `RequestMappingHandlerMapping` lựa chọn và `RequestMappingHandlerAdapter` gọi. Return value `Map` được Jackson-based message converter serialize thành JSON. Không cần `ViewResolver` cho endpoint này.

### 5.4. Viết một Servlet Filter quan sát pipeline

`src/main/java/com/example/pipeline/web/TraceFilter.java`:

```java
package com.example.pipeline.web;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String path = request.getRequestURI();
        System.out.println("filter: before " + request.getMethod()
                + " " + path + " dispatch=" + request.getDispatcherType());

        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("filter: after status=" + response.getStatus());
        }
    }
}
```

Đây là lớp Java đầy đủ, dùng package `jakarta.servlet.*` tương thích Spring Framework 6.x. `OncePerRequestFilter` cung cấp một triển khai `Filter.doFilter` để xử lý marker đã lọc và quyết định có bỏ qua async/error dispatch theo contract. Với các điều kiện bình thường, code custom chỉ cần override `doFilterInternal`.

Vì sao cần `try/finally`? Nếu controller hoặc filter sau đó ném exception, nhánh cleanup vẫn có cơ hội chạy. Tuy nhiên status nhìn thấy trong `finally` có thể chưa phải status cuối cùng được container ghi sau khi xử lý exception/error dispatch. Không được suy đoán rằng log `status=200` sau một exception chắc chắn chứng minh client nhận HTTP 200.

### 5.5. Đăng ký filter qua `FilterRegistrationBean`

`src/main/java/com/example/pipeline/web/TraceFilterConfig.java`:

```java
package com.example.pipeline.web;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class TraceFilterConfig {

    @Bean
    FilterRegistrationBean<TraceFilter> traceFilterRegistration() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new TraceFilter());
        registration.setName("traceFilter");
        registration.addUrlPatterns("/api/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(Ordered.LOWEST_PRECEDENCE - 10);
        return registration;
    }
}
```

Ý nghĩa từng lựa chọn:

- `setFilter(new TraceFilter())` tạo filter instance để Servlet container đăng ký.
- `addUrlPatterns("/api/*")` giới hạn URL pattern thay vì chạy với toàn bộ request. Pattern này là quy tắc Servlet URL matching, không phải Spring MVC `PathPattern`.
- `setDispatcherTypes(DispatcherType.REQUEST)` cho filter quan sát **initial request dispatch** trong ví dụ; không tự chạy ở `ASYNC`, `ERROR` hoặc `FORWARD`.
- `setOrder(Ordered.LOWEST_PRECEDENCE - 10)` đặt độ ưu tiên tương đối của filter registration trong nhóm do Boot quản lý. Giá trị số thấp hơn thường được xếp trước; tuyệt đối không giả định thứ tự với mọi filter của container, security hoặc thư viện mà chưa kiểm tra cấu hình.
- `setName(...)` cho registration tên rõ ràng, thuận tiện khi kiểm tra log/registration.
- `@Bean` đăng ký chính **`FilterRegistrationBean`**. `TraceFilter` được tạo tại đây và **không đánh dấu `@Component`**, tránh nguy cơ đăng ký cùng filter thêm lần nữa qua cơ chế auto-registration của filter bean.

Spring Boot có cơ chế tự đăng ký Servlet `Filter` bean, nhưng khi cần kiểm soát order, dispatcher types và URL patterns thì `FilterRegistrationBean` minh bạch hơn. Đừng dùng cả `@WebFilter`, `@Component` và `FilterRegistrationBean` cho cùng một filter nếu chưa hiểu rõ cách container xử lý các registration chồng nhau.

### 5.6. Chạy thử và quan sát

Nếu project có Gradle Wrapper, ở root project:

```bash
# Linux/macOS
./gradlew test
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Ở terminal khác:

```bash
curl -i "http://localhost:8080/api/hello?name=Lan"
```

Trên Windows PowerShell có thể dùng `curl.exe -i "http://localhost:8080/api/hello?name=Lan"` để chắc chắn gọi bản executable curl.

Response body mong đợi:

```json
{"message":"Xin chào, Lan!"}
```

Một chuỗi log ứng dụng có ý nghĩa trong **request GET thành công, đồng bộ** là:

```text
filter: before GET /api/hello dispatch=REQUEST
controller: handle name=Lan
filter: after status=200
```

Các log khác của Spring Boot và container có thể xen giữa; đây là **ba dòng do code ví dụ in ra theo quan hệ thứ tự**, không phải toàn bộ stdout của chương trình. Không kết luận chỉ từ log rằng filter A luôn chạy trước filter B khi có thêm dependency khác hoặc thay đổi registration order.

Gọi endpoint khác không bắt đầu bằng `/api/`, ví dụ `GET /not-found`, sẽ không kích hoạt `TraceFilter` vì pattern ở ví dụ giới hạn `/api/*`. Nếu gọi `GET /api/missing`, filter vẫn có thể in `before` và `after` dù không có controller khớp; Spring MVC xử lý 404 sau khi request đi qua filter.

## 6. Kiểm thử bằng MockMvc

`src/test/java/com/example/pipeline/HelloControllerTest.java`:

```java
package com.example.pipeline;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestPassesThroughMvcAndReturnsJson() throws Exception {
        mvc.perform(get("/api/hello").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, Lan!"));
    }

    @Test
    void queryParameterDefaultsWhenMissing() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, bạn!"));
    }
}
```

`@SpringBootTest` tải Spring context; `@AutoConfigureMockMvc` cấu hình MockMvc. Mặc định, auto-configured MockMvc cũng đăng ký filter beans trong ngữ cảnh thích hợp để kiểm tra request qua lớp web. Đây là test **trong môi trường mock servlet request**, không dùng HTTP socket hay Tomcat thực tế. Test trên không trực tiếp assert dòng log hay container dispatcher mapping, vì vậy nó chủ yếu chứng minh controller mapping + response.

Nếu mục tiêu test chính xác Servlet filter registration, thứ tự, `DispatcherType.ERROR` hoặc async dispatch qua container thực, bổ sung integration test chạy server ngẫu nhiên bằng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` và HTTP client phù hợp. Hành vi của proxy, Tomcat, filter registrations và servlet dispatcher types chỉ được kiểm chứng đầy đủ trên đường request/container thực.

## 7. Phân biệt Servlet Filter, MVC Interceptor và Spring Security

| Khía cạnh | Servlet Filter | Spring MVC HandlerInterceptor | Spring Security filter chain |
|---|---|---|---|
| Thuộc tầng | Servlet container | Nội bộ Spring MVC | Bên trong một Servlet Filter proxy/chain |
| Điểm chạy | Trước Servlet được gọi, với các dispatcher types được map | Sau khi MVC tìm được handler và trước/sau khi handler xử lý theo callback | Trong Servlet filter chain, thường trước MVC controller |
| Có thể chặn request? | Có, không gọi `chain.doFilter` | Có, trả `false` từ `preHandle` | Có, kiểm tra authentication/authorization và quyết định tiếp tục/trả lỗi |
| Thấy handler method? | Không mặc định | `preHandle(..., Object handler)` có handler được chọn | Không mặc định phụ thuộc mapping MVC, dù có thể tích hợp thêm |
| Ứng dụng điển hình | Logging, correlation ID, wrapping request, encoding, CORS handling | Logic gắn với handler, đo thời gian MVC, bổ sung model/locale | Xác thực, phân quyền, CSRF và security context |

Với Spring Security, `DelegatingFilterProxy` của Servlet có thể chuyển lời gọi sang bean Spring tên `springSecurityFilterChain` (thường là `FilterChainProxy`). Bên trong đó, Spring Security chọn một `SecurityFilterChain` phù hợp với request. Như vậy có **hai khái niệm “chain”**:

```text
Container FilterChain
    |
    +-- filter thông thường
    +-- DelegatingFilterProxy
    |     |
    |     +-- Spring Security FilterChainProxy
    |            +-- SecurityFilterChain chọn theo request
    |                  +-- security filters...
    |
    +-- DispatcherServlet
          +-- Spring MVC HandlerExecutionChain
                +-- MVC interceptors
                +-- controller
```

Spring Security không tự động có mặt trong demo chỉ vì dùng `spring-boot-starter-web`; muốn tích hợp nó, project cần dependency và cấu hình bảo mật tương ứng.

**Không nên** thực hiện security dựa độc nhất vào `HandlerInterceptor`: có request không đến handler MVC, và các quy tắc authentication/authorization thường cần chạy trước lựa chọn handler hoặc trên toàn bộ surface phù hợp. Spring Security cung cấp mô hình filter chain và các extension point chuyên biệt hơn.

### Callback interceptor không trùng callback filter

Một `HandlerInterceptor` có:
- `preHandle(request,response,handler)`: chạy trước handler, có thể trả `false` để dừng xử lý.
- `postHandle(request,response,handler,modelAndView)`: theo sau handler khi luồng phù hợp; với `@ResponseBody`, body có thể đã được converter ghi nên không phải hook sửa body tùy ý.
- `afterCompletion(request,response,handler,exception)`: chạy sau khi kết thúc xử lý MVC trong các điều kiện callback của interceptor, thường dùng cleanup; không cam kết mọi nhánh, ví dụ interceptor trả `false` trước khi được chấp nhận vào execution chain.

Interceptor không thay thế vòng `try/finally` của filter, và filter không thay thế MVC argument/return-value processing.

## 8. Dispatcher types: vì sao cùng request có thể đi qua filter nhiều lần?

`jakarta.servlet.DispatcherType` phân loại cách một Servlet dispatch được gọi. Các giá trị chính:

| Loại | Khi thường xuất hiện |
|---|---|
| `REQUEST` | Client gửi request bình thường đến container. |
| `FORWARD` | Server thực hiện `RequestDispatcher.forward(...)` sang resource/Servlet khác. |
| `INCLUDE` | Server thực hiện `RequestDispatcher.include(...)` để nhúng output của resource khác. |
| `ASYNC` | Servlet async processing dispatch request ở một giai đoạn về sau. |
| `ERROR` | Container thực hiện error dispatch đến error page/Servlet mapping sau một số lỗi hoặc `sendError`. |

**Filter registration** phải bao gồm dispatcher type thích hợp thì container mới gọi filter trên loại dispatch đó. Nếu không chỉ định type, theo Servlet spec hành vi mặc định thường là `REQUEST`; cấu hình của Boot và từng registration có thể bổ sung type. Ví dụ `TraceFilter` chủ động đặt chỉ `REQUEST` để log minh bạch.

`OncePerRequestFilter` cung cấp thêm một lớp kiểm soát chạy một lần theo request dispatch và luồng thực thi. Nó **không tự mở rộng filter registration** để nhận async/error dispatch. Mặc định:
- `shouldNotFilterAsyncDispatch()` trả `true`: bỏ qua các subsequent async dispatch.
- `shouldNotFilterErrorDispatch()` trả `true`: bỏ qua error dispatch tương ứng.
- Nếu muốn xử lý async/error, phải xem **cả hai điều kiện**: registration ở container có map type đó không, và `OncePerRequestFilter` có cho phép chạy nội bộ không.
- Không thể lấy tên lớp "OncePerRequestFilter" để kết luận chính xác *một lần cho toàn bộ HTTP request* khi có multiple dispatch hoặc thread khác nhau; contract thực tế là once per dispatch phù hợp các điều kiện.

Ví dụ cấu hình thêm type vào một filter khác (mang tính mô tả):

```java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
```

Nếu lớp vẫn kế thừa `OncePerRequestFilter` và không override các phương thức `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch`, việc thêm dispatcher types **chưa đủ** khiến code `doFilterInternal` chạy cho các dispatch sau. Với bất kỳ filter async nào, còn phải kiểm tra hỗ trợ async của filter/Servlet registration và lifecycle tài nguyên.

### Error dispatch khác MVC exception handling

Có hai tình huống:

1. Handler ném exception, `HandlerExceptionResolver` của Spring MVC xử lý được (ví dụ `@ExceptionHandler` trả `ResponseEntity`). Response có thể được viết ngay trong lần dispatch MVC hiện tại; container không nhất thiết tạo `ERROR` dispatch.
2. Exception không được xử lý tại MVC, hoặc container nhận yêu cầu xử lý lỗi (ví dụ `sendError`). Container có thể thực hiện `ERROR` dispatch sang error mapping, như `/error` của Spring Boot. Đây có thể là một lượt dispatch mới, có mapping filter khác.

Không suy ra rằng mỗi HTTP 4xx/5xx đều đi qua `DispatcherType.ERROR`. Bên cạnh đó, cách container xử lý nested error dispatch có thể khác nhau; hãy kiểm tra thực tế khi xây filter logging/security.

### Async request

Controller MVC có thể trả `Callable<T>`, `DeferredResult<T>` hoặc dùng cơ chế async tương ứng. Initial thread có thể thoát khỏi filter chain trong lúc response **chưa hoàn thành**. Một async dispatch khác có thể diễn ra trên thread khác và tái vào container/DispatcherServlet.

Hệ quả:
- `finally` của initial filter invocation không luôn đánh dấu "response đã gửi xong" trong trường hợp async.
- Giá trị trong `ThreadLocal` không tự truyền sang thread khác; phải quản lý propagation/cleanup theo contract tương ứng.
- Log "trước/sau filter" có thể phản ánh một dispatch thay vì toàn bộ thời gian end-to-end của request.
- Nếu cần đo completion thực của async request, dùng async lifecycle listener hoặc cơ chế quan sát tương thích, thay vì chỉ lấy thời gian giữa hai dòng log của filter đầu tiên.

## 9. Cấu hình thứ tự và thời điểm filter chạy

Khi có nhiều filter, thứ tự là một phần hành vi: encoding, request wrapping, security, caching, metrics hoặc logging có thể cần chạy trước/sau những filter khác. Trong Spring Boot, có thể đặt thứ tự thông qua `FilterRegistrationBean.setOrder(...)` hoặc cơ chế order được hỗ trợ cho filter bean; việc ưu tiên nào phù hợp tùy chức năng.

Mẫu:

```java
registration.addUrlPatterns("/api/*");
registration.setDispatcherTypes(DispatcherType.REQUEST);
registration.setOrder(100);
```

Đây là cấu hình **một** registration cụ thể. Không có đảm bảo rằng filter của bạn là filter đầu tiên trong toàn bộ container chỉ nhờ số `100`; bộ lọc framework và container có thể có registration khác. Để xem filter registrations của Spring Boot, bật logging liên quan web khi cần kiểm tra môi trường:

```properties
logging.level.web=debug
```

Sau khi chẩn đoán, có thể tắt debug để giảm log. Giải thích log dựa trên cấu hình đang chạy và URL pattern, không suy luận rằng số `@Order` trên phương thức `@Bean` sẽ luôn quyết định thứ tự filter; với Spring Boot, khi cần điều khiển order rõ ràng của filter nên đặt qua `FilterRegistrationBean`.

### Đăng ký bằng Servlet API thuần

Không dùng Spring Boot, container có thể đăng ký filter trong `web.xml` hoặc qua Servlet API:

```java
// Mảnh code minh họa ở ServletContext startup, không phải chương trình độc lập.
FilterRegistration.Dynamic registration =
        servletContext.addFilter("traceFilter", new TraceFilter());

registration.addMappingForUrlPatterns(
        java.util.EnumSet.of(DispatcherType.REQUEST),
        false,
        "/api/*");
```

Ở đây `servletContext` có sẵn trong Servlet initialization callback; mã này **không** nằm trong controller và không tự chạy khi paste vào một class tùy ý. Trong Spring Boot embedded container, cơ chế `ServletContextInitializer`/registration bean là điểm tích hợp phù hợp; không giả định Boot sẽ tự chạy mọi `WebApplicationInitializer` của Servlet container như khi deploy một WAR thuần.

## 10. Các nhánh luồng xử lý quan trọng

### A. Request đi tiếp thành công

```text
REQUEST → Filter.doFilter
        → chain.doFilter
        → DispatcherServlet
        → HandlerMapping / HandlerAdapter
        → Controller
        → Converter / View
        → quay ra Filter.finally
        → response
```

Filter nhìn thấy status sau downstream processing nhưng có thể không phải trạng thái kết thúc nếu async/error dispatch diễn ra sau đó.

### B. Filter chủ động từ chối

```text
REQUEST → Authentication/RateLimit Filter
        → kiểm tra thất bại
        → response.setStatus(401/429)
        → ghi response hợp lệ
        → không gọi chain.doFilter
        → kết thúc dispatch
```

Không có điều gì bắt buộc Spring MVC controller phải được gọi trong nhánh này. Đừng đặt logic cleanup chỉ trong controller nếu tài nguyên được cấp ở filter.

### C. Không tìm thấy MVC handler

```text
REQUEST → Filter(s) → DispatcherServlet
                     → HandlerMapping: không tìm thấy
                     → HTTP 404 hoặc nhánh exception tùy cấu hình
        ← Filter(s) unwind
```

Filter vẫn có thể ghi log dù controller không tồn tại. Nếu filter được map riêng `/api/*`, 404 ở `/outside` có thể hoàn toàn không chạy filter đó.

### D. Exception hoặc lỗi HTTP

```text
REQUEST → Filter(s) → DispatcherServlet
                      → Controller throws
                      → HandlerExceptionResolver?
                           |-- handled: response được tạo trong MVC
                           +-- unresolved / sendError:
                                    container có thể ERROR dispatch
```

Filter ở initial request không đương nhiên nhận callback cho error dispatch; có thể cần một filter registration map `ERROR` riêng với logic thích hợp.

### E. Servlet async

```text
REQUEST dispatch → filter → Servlet/Controller bắt đầu async
                  → initial call stack trả về
...
ASYNC dispatch   → một filter chain phù hợp dispatcher types
                  → DispatcherServlet tiếp tục kết quả
                  → hoàn thành response
```

Hình vẽ nhằm giải thích rằng một logical request có thể bao gồm nhiều dispatch; ứng dụng cần test đúng kiểu request, container và filter mapping.

## 11. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Kiểm tra / cách sửa |
|---|---|---|
| Không thấy log của `TraceFilter` với `/api/hello` | Filter chưa đăng ký, bean configuration ngoài component scan, URL pattern không khớp, request không vào ứng dụng đang chạy. | Kiểm tra package của `@Configuration`, log registration, cổng/context path và dispatcher type. |
| Log filter nhưng không có log controller | Filter phía trước chặn; Spring Security trả 401/403; handler mapping không tìm thấy; interceptor dừng trước handler. | Kiểm tra HTTP status, order, matcher, logs, path và security config. |
| Một request có nhiều log filter | Filter đăng ký trùng, nhiều dispatch, Servlet forward/error/async, logging từ nhiều filter. | Tìm tất cả registrations, dispatcher types và class/name; kiểm tra logic `OncePerRequestFilter`. |
| `@Order` trên phương thức `@Bean` không đổi order mong đợi | Thứ tự registration của filter cần cấu hình cụ thể; order trên bean method không bảo đảm như dự định. | Dùng `FilterRegistrationBean.setOrder(...)` và kiểm tra registration thực tế. |
| Body tới controller rỗng sau filter | Filter đã đọc input stream trước handler mà không có cơ chế buffering/wrapper đúng. | Tránh consume request body tùy tiện; dùng wrapper và lifecycle phù hợp khi thật sự cần. |
| `after` in ra status 200 dù request cuối trả 500 | Exception/async/error dispatch có thể tạo status cuối sau khi filter hiện tại thoát. | Phân biệt status quan sát tại thời điểm log với response kết thúc. |
| Filter không chạy trong async/error | Registration không map dispatcher type hoặc `OncePerRequestFilter` mặc định bỏ qua. | Kiểm tra cả `setDispatcherTypes` lẫn `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch`. |
| `ClassNotFoundException: javax.servlet...` | Dùng API Servlet cũ `javax.servlet` với Spring Framework 6.x yêu cầu `jakarta.servlet`. | Đồng bộ framework/container và imports Jakarta. |
| Có controller nhưng HTTP 404 | Sai Servlet mapping/context path, sai controller route, package scan, application chưa chạy. | Kiểm tra `DispatcherServlet` registration và Spring mapping của handler. |
| Spring Security authentication không chạy với một path | Filter/security matcher hoặc dispatcher types không bao phủ path mong muốn. | Rà soát `SecurityFilterChain` matcher, filter registration và loại dispatch; test đường HTTP thật. |

### Cảnh báo khi triển khai filter dùng cho security và audit

- **Không** log nguyên Authorization/Cookie, password, token, dữ liệu cá nhân hoặc body nhạy cảm.
- **Không** tin thông số `X-Forwarded-*` từ client trực tiếp nếu reverse proxy chưa thiết lập chính sách trust.
- **Không** tự decode URI/path nhiều lần trong filter để quyết định quyền truy cập; proxy, container và MVC có thể giải thích khác nhau.
- **Không** giả định quy tắc bảo mật controller sẽ chạy nếu filter trả response trước.
- Khi dùng `ThreadLocal`/MDC, đặt và xóa theo lifecycle/dispatch phù hợp trong `try/finally`; chú ý thread khác khi async.
- Để kiểm tra authentication/authorization, thường nên dùng extension points của Spring Security thay vì viết filter kiểm tra header thủ công cho production.

## 12. Bài thực hành

1. Chạy ứng dụng `servlet-pipeline-demo`. Gửi `GET /api/hello?name=Lan` rồi đối chiếu ba dòng log filter/controller/filter và body JSON.
2. Thử `GET /api/missing`, giải thích vì sao filter có thể chạy nhưng controller không chạy.
3. Thay `registration.addUrlPatterns("/api/*")` thành `"/debug/*"`, chạy lại và giải thích vì sao log không xuất hiện với `/api/hello` dù controller vẫn trả JSON.
4. Thêm một filter thứ hai trả HTTP `403` với một đường dẫn do bạn chỉ định, bảo đảm không gọi `chain.doFilter` trong nhánh chặn. Quan sát controller không được gọi và giải thích luồng unwind.
5. Tạo controller trả `Callable<String>` hoặc `DeferredResult<String>` để khảo sát async. So sánh lần `REQUEST` với `ASYNC` trên container thật trước/sau khi bạn thay đổi dispatcher mapping, và tránh kết luận dựa trên số lần callback trong MockMvc.

### Câu hỏi tự kiểm tra

**Câu 1. `DispatcherServlet` thuộc container hay Spring MVC?**  
Nó là Servlet **do Spring MVC cung cấp**, nhưng phải được **đăng ký với Servlet container**. Container gọi phương thức Servlet, còn DispatcherServlet điều phối tiếp các handler Spring MVC.

**Câu 2. Vì sao filter có thể chạy với endpoint trả 404?**  
Filter được container chọn theo URL pattern/dispatcher type trước khi DispatcherServlet tìm handler. Filter không cần biết route Spring có tồn tại.

**Câu 3. Sau `chain.doFilter`, status 200 có chắc HTTP client nhận 200 không?**  
Không luôn chắc. Có thể có error dispatch, exception chưa xử lý hoặc async lifecycle tiếp theo. Phải kiểm tra status cuối ở đúng điểm quan sát.

**Câu 4. `OncePerRequestFilter` có ngăn mọi trường hợp chạy lại?**  
Không. Nó quản lý thực thi theo request dispatch/thread và logic tránh gọi trùng; async/error dispatch cùng registration quyết định khi nào code nội bộ được gọi.

**Câu 5. Spring Security filters có phải MVC interceptors không?**  
Không. `FilterChainProxy` của Spring Security làm việc qua Servlet Filter và nằm trước phần xử lý controller MVC thông thường.

## Tài liệu tham khảo chính thức

- Spring Framework — `DispatcherServlet`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — Processing sequence: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/sequence.html
- Spring Framework — Special bean types (`HandlerMapping`, `HandlerAdapter`, …): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html
- Spring Framework — Exception handling: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — `OncePerRequestFilter` API: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Boot — Servlet web applications, registration of filters: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — `FilterRegistrationBean` API (3.5): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
- Jakarta Servlet — Filter and DispatcherType contracts: https://jakarta.ee/specifications/servlet/
