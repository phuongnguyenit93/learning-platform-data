# Filter, interceptor, argument resolver và cấu hình MVC tùy chỉnh trong Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm:** Spring MVC  
> **Mục tiêu:** Hiểu điểm vào, thứ tự xử lý và trách nhiệm của Servlet Filter, Spring MVC HandlerInterceptor, HandlerMethodArgumentResolver và WebMvcConfigurer; đăng ký chúng an toàn; viết test chứng minh hành vi đúng ở cả MVC slice và context ứng dụng. Ví dụ dùng Java 17+, Spring Boot 3.5, Jakarta Servlet, JUnit Jupiter và MockMvc.

## 1. Toàn cảnh: một HTTP request đi qua những lớp nào?

Trong Spring MVC, không phải tất cả phần mở rộng nằm ở cùng một ranh giới. Khi ứng dụng Servlet nhận request, tuyến xử lý cơ bản là:

```text
HTTP client
   │
   ▼
Servlet container (Tomcat/Jetty/Undertow)
   │
   ▼
Servlet Filter chain                  ← trước/sau DispatcherServlet
   │
   ▼
DispatcherServlet
   │
   ├── HandlerMapping chọn controller/handler
   │
   ├── HandlerInterceptor.preHandle   ← sau khi tìm được handler
   │       ├── false → kết thúc nhánh gọi handler
   │       └── true  → tiếp tục
   │
   ├── HandlerAdapter
   │       ├── HandlerMethodArgumentResolver
   │       ├── Controller method
   │       └── ReturnValueHandler/HttpMessageConverter
   │
   ├── HandlerInterceptor.postHandle  ← đường xử lý đồng bộ phù hợp
   │
   └── HandlerInterceptor.afterCompletion
   │
   ▼
Servlet Filter hoàn tất phần sau chain.doFilter(...)
   │
   ▼
HTTP response
```

Sơ đồ là **đường đồng bộ điển hình**. Với exception, async request, error dispatch, static resources hoặc một Filter short-circuit, một số callback không chạy theo đúng đường bình thường. Không được coi nó là thứ tự tuyệt đối cho mọi request.

Bốn khái niệm:

| Thành phần | Phạm vi | Thời điểm | Trách nhiệm thường gặp |
| --- | --- | --- | --- |
| **Servlet Filter** | Servlet container/filter chain, có thể bao nhiều servlet | Trước và sau `chain.doFilter` | Correlation ID, encoding, request/response wrapper, CORS/security filter integration, logging an toàn |
| **HandlerInterceptor** | HandlerMapping của Spring MVC, sau khi tìm handler | `preHandle`, `postHandle`, `afterCompletion` | Kiểm tra điều kiện gắn với handler, thêm request attributes, đo thời gian xử lý MVC |
| **HandlerMethodArgumentResolver** | Chỉ tham số của handler method | Lúc Spring chuẩn bị gọi controller | Chuyển request/context thành tham số typed như `TenantId`, `CurrentUser`, paging context |
| **WebMvcConfigurer** | Cấu hình Spring MVC | Khi dựng MVC infrastructure | Đăng ký interceptor, resolver, converters, formatters, CORS, resource handlers… |

**Câu cần nhớ:** Filter hoạt động ở tầng Servlet; Interceptor hoạt động ở tầng MVC; Argument Resolver cung cấp **giá trị tham số** cho controller; WebMvcConfigurer **đăng ký phần mở rộng**, không tự xử lý từng request.

## 2. Servlet Filter: rộng hơn MVC và nằm trước DispatcherServlet

### 2.1. Filter làm gì?

Filter được quản lý bởi Servlet filter chain. Trong ứng dụng Spring Boot Servlet, một bean triển khai `jakarta.servlet.Filter` có thể được Spring Boot đăng ký với embedded Servlet container. Khi request đi qua chain:

```java
doSomethingBefore(request, response);
chain.doFilter(request, response);
doSomethingAfter(request, response);
```

Đoạn này là **pseudocode minh họa**, chưa phải class Java biên dịch độc lập.

Các use case phù hợp:

- Tạo/cấp phát request ID và đưa vào request attribute/header.
- Bọc request/response khi cần capture/caching body đúng cách.
- Đặt, rồi dọn MDC/tracing context bằng `try/finally`.
- Cấu hình cross-cutting tại tầng Servlet như `CharacterEncodingFilter`.
- Các security filters trong `SecurityFilterChain` do Spring Security quản lý.

**Một Filter có thể ngăn request đến DispatcherServlet** nếu nó không gọi `chain.doFilter`. Ví dụ chặn request quá lớn hoặc thiếu header nền tảng (nếu đó là hợp đồng). Điều này khác việc interceptor trả `false` sau khi DispatcherServlet đã tìm handler.

### 2.2. `OncePerRequestFilter` và những giới hạn

Spring cung cấp `OncePerRequestFilter` để hỗ trợ một lần thực thi logic filter theo cơ chế đánh dấu request của nó. Đây là lớp thuận tiện để tránh xử lý trùng trong các đường dispatch mà filter được áp dụng.

```java
public final class RequestIdFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        // Validate or generate request ID...
        chain.doFilter(request, response);
    }
}
```

Đây là **khung rút gọn**; class chạy đầy đủ ở phần 5.

Cần hiểu chính xác:

- “Once” có liên quan vòng đời **request dispatch**, không có nghĩa mỗi yêu cầu nghiệp vụ trong toàn hệ thống chỉ được gọi một lần.
- `ASYNC`/`ERROR` dispatch có quy tắc khác nhau; `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()` cho phép điều chỉnh trong tình huống cần thiết.
- Khi dùng wrapper, input stream hay output stream, phải bảo đảm không tiêu thụ body khiến controller không đọc được.
- Nếu ghi response header **sau** `chain.doFilter`, response có thể đã commit; muốn header luôn sẵn sàng, đặt trước khi chain tiếp tục.
- Filter không tự biết controller method nào sẽ được chọn, nên không hợp để xây logic phụ thuộc annotation cụ thể của handler.

### 2.3. Cách đăng ký Filter trong Spring Boot

Các lựa chọn thường gặp:

1. Khai báo `@Component` trên Filter hoặc `@Bean Filter`, để Spring Boot đăng ký theo cơ chế Servlet filter beans.
2. Dùng `FilterRegistrationBean<SomeFilter>` nếu cần URL patterns, dispatcher types, order, enabled flag và registration chính xác.
3. Với Spring Security, cấu hình filter trong `SecurityFilterChain` tại vị trí phù hợp; **không vô tình đăng ký cùng instance Filter hai lần** (vừa auto-register như Servlet Filter vừa add vào security chain).

Minh họa khi muốn giới hạn URL:

```java
@Bean
FilterRegistrationBean<RequestIdFilter> requestIdRegistration() {
    FilterRegistrationBean<RequestIdFilter> registration =
            new FilterRegistrationBean<>();
    registration.setFilter(new RequestIdFilter());
    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
```

Đây là **mẫu config độc lập để lựa chọn**, không đặt thêm vào dự án phần 5 khi đang có `@Bean RequestIdFilter`, vì bạn không nên tạo hai đường đăng ký filter cho một trách nhiệm. Nếu dùng mẫu này cần import `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.context.annotation.Bean` và class `RequestIdFilter`.

**Lưu ý:** Filter URL pattern (`/api/*`) là cơ chế Servlet, khác với pattern của Spring MVC interceptor (`/api/**`). Đừng áp dụng máy móc cùng cú pháp pattern cho hai API.

## 3. HandlerInterceptor: vòng đời gắn với handler MVC

`HandlerInterceptor` được Spring MVC gọi quanh handler đã được chọn bởi `HandlerMapping`:

- **`preHandle(request,response,handler)`:** trước khi gọi controller. Trả `true` để xử lý tiếp; trả `false` để dừng luồng gọi handler. Nếu trả `false`, interceptor tự chịu trách nhiệm đáp ứng hợp lý (ví dụ đặt status) và không chờ controller xử lý.
- **`postHandle(request,response,handler,modelAndView)`:** sau khi handler chạy thành công ở đường xử lý đồng bộ phù hợp, trước khi render view. Với `@ResponseBody`/`@RestController`, body có thể đã được ghi qua `HttpMessageConverter` trước callback, nên không dựa vào `postHandle` để thay JSON/body hoặc header đã commit.
- **`afterCompletion(request,response,handler,exception)`:** callback hoàn tất sau xử lý phù hợp; hữu ích cho cleanup/metrics của MVC. Nếu `preHandle` của chính interceptor trả `false`, nó **không nhận afterCompletion cho handler invocation ấy** như khi đã được kích hoạt đầy đủ. Async/error paths có quy tắc riêng.

Những interceptor được đăng ký theo thứ tự có thể tạo **thứ tự callback ngược** khi xử lý trả về. Nếu nghiệp vụ cần một thứ tự chính xác, hãy kiểm tra behavior bằng test, không dựa vào giả định từ danh sách mã nguồn.

### 3.1. Khi nào nên dùng interceptor?

Phù hợp: chuẩn hóa request-scoped metadata sau khi mapping, đo thời gian thực hiện controller, ràng buộc request theo một API path, quyết định routing/application-level guard nếu không phải core authorization.

Không lý tưởng: thay thế **authentication và authorization** của Spring Security. Tài liệu Spring khuyên không dùng interceptor làm lớp security chính vì khác biệt path matching với security filter chain. Với multi-tenant, **header tự khai báo không chứng minh danh tính/ quyền truy cập tenant**. Nếu tenant ID là yếu tố cấp quyền, phải đối chiếu với principal, JWT claims và quy tắc truy cập tại security/service layer. Ví dụ dưới chỉ **kiểm tra định dạng header để minh họa cơ chế**, không triển khai multi-tenant authorization thật.

### 3.2. Pattern khớp URL

Trong `WebMvcConfigurer`:

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new TenantInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**");
}
```

Đoạn này chỉ minh họa pattern. Spring MVC path matching chịu cấu hình phiên bản/framework; nếu cần bảo vệ routing, dùng các pattern được kiểm chứng trên các endpoint thật và viết test cho include/exclude. Nếu interceptor được thêm qua Java MVC config, nó áp dụng cho các `HandlerMapping` được cấu hình bởi cơ chế MVC đó; `MappedInterceptor` bean có cách phát hiện rộng hơn qua các handler mappings phù hợp.

## 4. HandlerMethodArgumentResolver: biến request context thành tham số typed

Không nên để mọi controller lặp lại:

```java
String tenant = request.getHeader("X-Tenant-Id");
// Validate, normalize, map to domain object...
```

Với custom `@CurrentTenant TenantId tenant`, Spring MVC có thể tự phân giải giá trị trước khi gọi method controller.

Interface `HandlerMethodArgumentResolver` có hai trách nhiệm:

```java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory)
        throws Exception;
```

Đây là chữ ký API minh họa, không phải một file source độc lập.

- `supportsParameter` phải **hẹp và chính xác**, chẳng hạn chỉ tham số có annotation `@CurrentTenant` và type `TenantId`; nếu “đón” tất cả `String` sẽ dễ đè/chặn cơ chế binding khác.
- `resolveArgument` lấy giá trị đã xác thực/chuẩn hóa trong request hoặc security context và tạo domain object phù hợp.
- Không nên tự truy vấn DB/remote service cho mọi request trong resolver nếu không có lý do thiết kế; nó làm binding khó đoán, chậm và khó test.
- Resolver cung cấp argument, **không thay thế validation nghiệp vụ, security policy hoặc data authorization**.
- Resolver thông thường được thêm qua `WebMvcConfigurer#addArgumentResolvers`; cách này **bổ sung** những resolver chuẩn, không xóa hỗ trợ `@RequestBody`, `@RequestParam`, `@PathVariable`.
- Nếu cần thay hành vi của một resolver built-in, có thể phải cấu hình sâu hơn `RequestMappingHandlerAdapter`; không kỳ vọng thêm resolver custom sẽ tự override toàn bộ built-ins.

### 4.1. Vì sao typed value tốt hơn raw string?

`TenantId` record giúp controller thể hiện rõ contract:

```java
public record TenantId(String value) {}

@GetMapping("/api/context")
public ContextPayload inspect(@CurrentTenant TenantId tenant,
                              HttpServletRequest request) {
    // tenant đã được resolver tạo từ request-scoped data.
}
```

Đây là đoạn minh họa rút gọn; app đầy đủ ở phần 5. Một domain wrapper như `TenantId` giảm nguy cơ nhầm tenant với request ID, order ID hoặc các chuỗi khác. Tuy nhiên việc có type `TenantId` **không có nghĩa tenant đã được xác thực danh tính**; đó là trách nhiệm riêng.

## 5. Cấu hình MVC với `WebMvcConfigurer`

`WebMvcConfigurer` cho phép ứng dụng bổ sung hành vi MVC trong Spring Boot mà vẫn tận dụng Boot MVC auto-configuration. Các callback thường gặp:

| Phương thức | Dùng cho |
| --- | --- |
| `addInterceptors` | Thêm HandlerInterceptor, URL patterns |
| `addArgumentResolvers` | Bổ sung custom handler method arguments |
| `addFormatters` | Converter/Formatter cho dữ liệu request |
| `addCorsMappings` | CORS policy ở tầng MVC |
| `addResourceHandlers` | Static resources và cache controls |
| `addViewControllers` | Mapping đơn giản tới view |
| `extendMessageConverters` | Mở rộng/chỉnh các converters hiện có |
| `configureMessageConverters` | Cấu hình converters; có thể thay tập defaults tùy cơ chế |
| `configureAsyncSupport` | MVC async configuration, timeout, executor |
| `configurePathMatch` | Tùy chỉnh path matching |

**Quan trọng:** Trong Spring Boot, thường chỉ cần một `@Configuration` triển khai `WebMvcConfigurer`. **Đừng tự thêm `@EnableWebMvc` nếu không cố ý nắm toàn quyền cấu hình MVC**, vì nó thay đổi cách Boot MVC auto-configuration được áp dụng. Rất nhiều lỗi mất JSON/static resources/custom converters xuất phát từ việc bật `@EnableWebMvc` chỉ để thêm một interceptor.

Phân biệt:

- `@Configuration + WebMvcConfigurer`: bổ sung/tùy biến dựa trên MVC infrastructure hiện hành.
- `@EnableWebMvc`: chỉ dùng khi chủ động nhận toàn bộ trách nhiệm cấu hình Spring MVC.
- `@Import(MvcSupportConfiguration.class)` trong slice test: đảm bảo custom MVC config cần test được nạp, kể cả khi slice không tự import một `@Configuration` tùy ý.
- `@AutoConfigureMockMvc`: cấp `MockMvc` khi dùng `@SpringBootTest(MOCK)` và Spring MVC; **không** mở embedded HTTP listener.

## 6. Dự án Maven chạy được: filter → interceptor → resolver → controller

Ví dụ hoàn chỉnh dùng **Java 17, Spring Boot 3.5.0, Spring MVC/Servlet**, không cần database, cloud account hoặc service bên ngoài. API trả về JSON về tenant và request ID, đủ để test từng điểm mở rộng.

### 6.1. Hợp đồng của API

Endpoint: `GET /api/context`.

- Request phải mang header `X-Tenant-Id` với định dạng `[a-z][a-z0-9-]{2,15}`. Ví dụ `tenant-a` hợp lệ.
- `TenantInterceptor` kiểm tra **định dạng** và đặt giá trị đã kiểm tra vào request attribute `validatedTenant`. Thiếu/sai định dạng → **400 Bad Request**, controller không được gọi.
- `TenantArgumentResolver` đọc `validatedTenant` và tạo `TenantId` cho tham số `@CurrentTenant`.
- `RequestIdFilter` nhận `X-Request-Id` khi khớp `[A-Za-z0-9-]{1,64}`. Thiếu/sai định dạng → tạo UUID mới. Filter đặt request attribute `requestId` và response header `X-Request-Id`.
- `InspectionController` gọi `InspectionService` để tạo greeting; response JSON chứa tenant, request ID và greeting.
- Interceptor đặt response header `X-Tenant-Checked=true` trong `preHandle`.

Ví dụ request hợp lệ:

```http
GET /api/context HTTP/1.1
Host: localhost:8080
X-Tenant-Id: tenant-a
X-Request-Id: req-42
```

Kết quả mong đợi của **ứng dụng thật**:

```http
HTTP/1.1 200 OK
X-Request-Id: req-42
X-Tenant-Checked: true
Content-Type: application/json

{"tenant":"tenant-a","requestId":"req-42","greeting":"Hello, tenant-a"}
```

Đây là **minh họa phần response contract**, không khẳng định thứ tự thực tế của HTTP headers/JSON fields hoặc các headers mặc định khác. Khi thiếu tenant, kỳ vọng status 400; body của `sendError` có thể khác theo chế độ MockMvc/server nên test không khóa vào JSON lỗi cố định.

### 6.2. Cấu trúc thư mục

```text
mvc-extension-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcext/
    │   │   ├── MvcExtensionApplication.java
    │   │   ├── TenantId.java
    │   │   ├── CurrentTenant.java
    │   │   ├── RequestIdFilter.java
    │   │   ├── TenantInterceptor.java
    │   │   ├── TenantArgumentResolver.java
    │   │   ├── MvcSupportConfiguration.java
    │   │   ├── InspectionService.java
    │   │   ├── ContextPayload.java
    │   │   └── InspectionController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/com/example/mvcext/
        │   ├── InspectionMvcSliceTest.java
        │   ├── InspectionFullContextTest.java
        │   └── InspectionHttpServerTest.java
        └── resources/
            └── application-test.yml
```

Đặt từng public type vào đúng tệp cùng tên trong package `com.example.mvcext`. Cấu hình filter/interceptor/resolver được khai báo **duy nhất một nơi** để tránh đăng ký trùng.

### 6.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-extension-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` cung cấp Spring MVC và Jakarta Servlet API qua embedded server (Tomcat mặc định cho starter chuẩn). `spring-boot-starter-test` mang JUnit Jupiter, MockMvc, Mockito và Spring Test. Trong test chạy qua MockMvc, **không** có embedded listening HTTP socket; test `RANDOM_PORT` sẽ mở server thật.

### 6.4. Application entrypoint, records và annotation

```java
// src/main/java/com/example/mvcext/MvcExtensionApplication.java
package com.example.mvcext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcExtensionApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcExtensionApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/mvcext/TenantId.java
package com.example.mvcext;

public record TenantId(String value) {}
```

```java
// src/main/java/com/example/mvcext/CurrentTenant.java
package com.example.mvcext;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {}
```

```java
// src/main/java/com/example/mvcext/ContextPayload.java
package com.example.mvcext;

public record ContextPayload(
        String tenant, String requestId, String greeting) {}
```

`@CurrentTenant` chỉ hợp lệ trên method parameter và tồn tại ở runtime để `HandlerMethodArgumentResolver` phát hiện. `TenantId` và `ContextPayload` là Java records, giúp JSON output/Mockito equality xác định được.

### 6.5. Filter tạo request ID

```java
// src/main/java/com/example/mvcext/RequestIdFilter.java
package com.example.mvcext;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String incoming = request.getHeader("X-Request-Id");

        String id = incoming != null
                && SAFE_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        request.setAttribute("requestId", id);
        response.setHeader("X-Request-Id", id);

        chain.doFilter(request, response);
    }
}
```

Filter đặt response header **trước** khi gọi chain nên controller/exception handling có thể thấy correlation ID. Khi request ID vắng mặt, UUID ngẫu nhiên khiến test **không được hard-code expected ID**; phải kiểm tra định dạng hợp lệ và sự nhất quán header ↔ JSON.

Regex ở đây chỉ là biện pháp cơ bản chống dữ liệu log/header không hợp lệ; trong hệ thống thực cần xét độ dài, format chuẩn, tính tin cậy của client-supplied trace ID, chống log injection và cách tích hợp distributed tracing. **Request ID không phải access token.**

### 6.6. Interceptor kiểm tra tenant header và chặn trước controller

```java
// src/main/java/com/example/mvcext/TenantInterceptor.java
package com.example.mvcext;

import java.io.IOException;
import java.util.regex.Pattern;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.servlet.HandlerInterceptor;

public final class TenantInterceptor implements HandlerInterceptor {

    private static final Pattern TENANT =
            Pattern.compile("[a-z][a-z0-9-]{2,15}");

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws IOException {

        String rawTenant = request.getHeader("X-Tenant-Id");

        if (rawTenant == null
                || !TENANT.matcher(rawTenant).matches()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST,
                    "Invalid X-Tenant-Id");
            return false;
        }

        request.setAttribute("validatedTenant", rawTenant);
        response.setHeader("X-Tenant-Checked", "true");
        return true;
    }
}
```

Vì `preHandle` trả `false` khi thiếu tenant, MVC không gọi controller hoặc `TenantArgumentResolver` trong nhánh lỗi. **Đây chỉ là validation định dạng**; không đủ để bảo vệ dữ liệu multi-tenant. Với authorization, đối chiếu tenant với authenticated principal tại lớp security/business.

`TenantInterceptor` không được đánh dấu `@Component` trong project này. Nó do `MvcSupportConfiguration` đăng ký, tránh hai đường cấu hình khó kiểm soát.

### 6.7. Resolver đọc giá trị đã kiểm tra

```java
// src/main/java/com/example/mvcext/TenantArgumentResolver.java
package com.example.mvcext;

import org.springframework.core.MethodParameter;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

public final class TenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
                && TenantId.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer mavContainer,
            NativeWebRequest webRequest,
            WebDataBinderFactory binderFactory) {

        Object value = webRequest.getAttribute(
                "validatedTenant", RequestAttributes.SCOPE_REQUEST);

        if (!(value instanceof String tenant)) {
            throw new IllegalStateException(
                    "TenantInterceptor did not validate tenant");
        }

        return new TenantId(tenant);
    }
}
```

Resolver có `supportsParameter` **hẹp**: không chiếm những tham số `String` hoặc `TenantId` không được gắn `@CurrentTenant`. Nó chỉ đọc **request attribute do interceptor tạo**, không tin trực tiếp vào header chưa kiểm tra. Nếu người cấu hình quên interceptor, resolver fail rõ ràng thay vì âm thầm dùng tenant rỗng.

Về tổng quát, `resolveArgument` có thể được gọi cho request đã tìm thấy handler phù hợp; nó **không xử lý tất cả các HTTP requests** và không nhận trách nhiệm của Filter.

### 6.8. Cấu hình MVC tường minh, không dùng `@EnableWebMvc`

```java
// src/main/java/com/example/mvcext/MvcSupportConfiguration.java
package com.example.mvcext;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcSupportConfiguration implements WebMvcConfigurer {

    private final TenantInterceptor tenantInterceptor =
            new TenantInterceptor();

    private final TenantArgumentResolver tenantArgumentResolver =
            new TenantArgumentResolver();

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(tenantInterceptor)
                .addPathPatterns("/api/**");
    }

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(tenantArgumentResolver);
    }

    @Bean
    RequestIdFilter requestIdFilter() {
        return new RequestIdFilter();
    }
}
```

Đây là lựa chọn **có chủ đích**:

- `MvcSupportConfiguration` là một Spring configuration; trong full application context nó được component scan.
- `WebMvcConfigurer#addInterceptors` đăng ký `TenantInterceptor` cho `/api/**`.
- `WebMvcConfigurer#addArgumentResolvers` thêm `TenantArgumentResolver` vào Spring MVC argument handling.
- `@Bean RequestIdFilter` đưa filter vào Spring context; Boot và MockMvc test auto-configuration có thể đăng ký filter trong Servlet/filter test chain phù hợp.
- Không có `@EnableWebMvc` nên Boot MVC auto-configuration không bị vô hiệu chỉ để thêm hai callback.
- Interceptor/resolver là các đối tượng **stateless**, được giữ riêng trong config. Không cần expose chúng thành bean bổ sung cho ví dụ này; nếu cần inject collaborators vào chúng trong ứng dụng thật, hãy tạo bean và constructor-inject một cách rõ ràng.

Khi chạy `@WebMvcTest`, ta sẽ thêm `@Import(MvcSupportConfiguration.class)` để đảm bảo custom MVC config được kiểm tra thực sự nằm trong test context. Chỉ nhìn thấy class này trong `src/main/java` không phải bằng chứng slice đã tự nạp nó.

### 6.9. Service và controller sử dụng typed argument

```java
// src/main/java/com/example/mvcext/InspectionService.java
package com.example.mvcext;

import org.springframework.stereotype.Service;

@Service
public class InspectionService {
    public String greet(TenantId tenant) {
        return "Hello, " + tenant.value();
    }
}
```

```java
// src/main/java/com/example/mvcext/InspectionController.java
package com.example.mvcext;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class InspectionController {

    private final InspectionService service;

    public InspectionController(InspectionService service) {
        this.service = service;
    }

    @GetMapping("/context")
    public ContextPayload inspect(
            @CurrentTenant TenantId tenant,
            HttpServletRequest request) {

        String requestId =
                (String) request.getAttribute("requestId");

        return new ContextPayload(
                tenant.value(),
                requestId,
                service.greet(tenant));
    }
}
```

Controller không gọi `request.getHeader("X-Tenant-Id")`; nó nhận `TenantId` đã được Resolver tạo. Service chỉ dùng tenant như dữ liệu cho greeting minh họa. Trong production, **không dùng tenant được lấy từ client header làm quyền truy cập dữ liệu**, kể cả khi đã khớp regex.

### 6.10. Cấu hình test riêng

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: mvc-extension-lab
```

```yaml
# src/test/resources/application-test.yml
app:
  test-marker: isolated
```

Các test có Spring context sẽ dùng `@ActiveProfiles("test")`. Marker `app.test-marker=isolated` chỉ chứng minh config test được nạp; nó không tự cô lập mọi outbound connections. Dự án mẫu không có database/remote client nên không cần credentials.

## 7. Kiểm thử bằng `@WebMvcTest`: mock service, custom MVC vẫn chạy thật

`@WebMvcTest(InspectionController.class)` chỉ nạp lát MVC và auto-configure `MockMvc`. `InspectionService` thông thường không tự được nạp vì là `@Service` ngoài slice, nên dùng `@MockitoBean`. Custom configuration được đưa vào bằng `@Import`.

```java
// src/test/java/com/example/mvcext/InspectionMvcSliceTest.java
package com.example.mvcext;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InspectionController.class)
@Import(MvcSupportConfiguration.class)
@ActiveProfiles("test")
class InspectionMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    InspectionService service;

    @Test
    void runsFilterInterceptorAndResolverBeforeController()
            throws Exception {
        TenantId tenant = new TenantId("tenant-a");
        when(service.greet(tenant)).thenReturn("stub-tenant-a");

        mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant-a")
                        .header("X-Request-Id", "req-42"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", "req-42"))
                .andExpect(header().string("X-Tenant-Checked", "true"))
                .andExpect(jsonPath("$.tenant").value("tenant-a"))
                .andExpect(jsonPath("$.requestId").value("req-42"))
                .andExpect(jsonPath("$.greeting").value("stub-tenant-a"));

        verify(service).greet(tenant);
    }

    @Test
    void missingTenantStopsBeforeController() throws Exception {
        mvc.perform(get("/api/context")
                        .header("X-Request-Id", "req-43"))
                .andExpect(status().isBadRequest())
                .andExpect(header().string("X-Request-Id", "req-43"));

        verifyNoInteractions(service);
    }

    @Test
    void malformedTenantIsRejected() throws Exception {
        mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant_invalid")
                        .header("X-Request-Id", "req-44"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void missingRequestIdGeneratesUuidAndEchoesIt() throws Exception {
        TenantId tenant = new TenantId("tenant-a");
        when(service.greet(tenant)).thenReturn("stub-tenant-a");

        MvcResult result = mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant-a"))
                .andExpect(status().isOk())
                .andReturn();

        String requestId =
                result.getResponse().getHeader("X-Request-Id");

        assertNotNull(requestId);
        assertEquals(requestId,
                UUID.fromString(requestId).toString());

        String body = result.getResponse().getContentAsString();
        assertEquals(requestId,
                mapper.readTree(body)
                        .path("requestId").asText());
    }
}
```

**Những assertion này bảo vệ gì?**

1. Test thành công kiểm tra **ba mốc**: filter đặt request ID, interceptor đặt header đã kiểm tra, resolver cấp đúng `TenantId` khiến service mock nhận đúng argument.
2. Khi thiếu/sai tenant, `preHandle` trả `false`; status 400 và `verifyNoInteractions(service)` chứng minh controller không gọi service.
3. Khi thiếu request ID, filter cấp UUID. Test **không hard-code** một ID ngẫu nhiên; nó xác nhận parse được theo canonical UUID string và JSON trả lại đúng cùng giá trị ở response header.
4. Service ở đây là **Mockito mock**; chuỗi `stub-tenant-a` có chủ đích khác output thật để bạn không ngộ nhận test slice đã chạy logic business của `InspectionService`.
5. `@Import` giữ extension configuration trong phạm vi test. Nếu bỏ import mà slice không tự nạp config, những assertion về header/tenant sẽ đỏ, giúp phát hiện thiếu wiring.

**Điều test chưa chứng minh:** embedded HTTP server đã lắng nghe, servlet container xử lý network I/O, cấu hình production thực hoặc auth quyền tenant. `MockMvc.perform` hoạt động trong Spring MVC test infrastructure, không mở TCP socket.

## 8. `@SpringBootTest(MOCK)`: config MVC thật và business service thật

Để kiểm tra tích hợp MVC → interceptor → resolver → controller → service **thật**, không mock service. `@SpringBootTest` nạp context ứng dụng theo các conditions hiện hành; trong project này `MvcSupportConfiguration` và `InspectionService` được scan.

```java
// src/test/java/com/example/mvcext/InspectionFullContextTest.java
package com.example.mvcext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mockingDetails;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class InspectionFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InspectionService service;

    @Autowired
    Environment environment;

    @Test
    void appContextUsesRealServiceAndCustomMvcComponents()
            throws Exception {
        assertFalse(mockingDetails(service).isMock());
        assertEquals("isolated",
                environment.getProperty("app.test-marker"));

        mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant-a")
                        .header("X-Request-Id", "req-99"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", "req-99"))
                .andExpect(header().string("X-Tenant-Checked", "true"))
                .andExpect(jsonPath("$.tenant").value("tenant-a"))
                .andExpect(jsonPath("$.greeting")
                        .value("Hello, tenant-a"));
    }

    @Test
    void invalidTenantStillFailsInFullContext() throws Exception {
        mvc.perform(get("/api/context"))
                .andExpect(status().isBadRequest());
    }
}
```

**So sánh với slice:**

- Cùng endpoint `/api/context`, cùng Filter/Interceptor/Resolver đã cấu hình.
- Slice dùng `InspectionService` **mock** và expected `stub-tenant-a`.
- Full context dùng `InspectionService` **thật** và expected `Hello, tenant-a`.
- Cả hai dùng `MockMvc` nên không có embedded listener. Chữ `MOCK` trong `webEnvironment` **không** có nghĩa service được Mockito mock.
- Full context có thể tự khởi tạo thêm bean ngoài mục tiêu của test nếu dự án thật nhiều dependencies; phải dùng test-only profile, database sandbox và stub/fake outbound ports.

## 9. `@SpringBootTest(RANDOM_PORT)`: kiểm tra thêm HTTP server thực

Nếu mục tiêu còn bao gồm registration của Filter trong embedded Servlet container và transport HTTP thực, chạy server trên cổng ngẫu nhiên, rồi dùng Java 17 `HttpClient` gửi request qua loopback:

```java
// src/test/java/com/example/mvcext/InspectionHttpServerTest.java
package com.example.mvcext;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class InspectionHttpServerTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    @Test
    void httpRequestPassesThroughRealServletContainer()
            throws Exception {

        assertTrue(port > 0);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/context");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Tenant-Id", "tenant-a")
                .header("X-Request-Id", "req-net-1")
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("req-net-1",
                response.headers()
                        .firstValue("X-Request-Id").orElseThrow());
        assertEquals("true",
                response.headers()
                        .firstValue("X-Tenant-Checked").orElseThrow());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("tenant-a", body.path("tenant").asText());
        assertEquals("req-net-1", body.path("requestId").asText());
        assertEquals("Hello, tenant-a",
                body.path("greeting").asText());
    }
}
```

Điểm khác biệt là `HttpClient` **thực sự kết nối TCP** tới embedded server, trong khi `MockMvc` dựng mock Servlet request/response nội bộ. Cả hai đều kiểm tra custom MVC logic; HTTP test bao phủ thêm việc embedded server khởi động và Filter được đăng ký trong Servlet container.

**Không hard-code localhost:8080 trong `RANDOM_PORT`.** Cổng được cấp bởi OS và chỉ biết khi context đã startup, qua `@LocalServerPort`.

### 9.1. Vì sao Filter phải được kiểm tra ở hai mức?

- `MockMvc` có khả năng nạp các Filter beans từ application context khi auto-configure với `addFilters=true` (mặc định), nhưng nó **không** kiểm tra mọi chi tiết mapping/dispatcher types/order của Servlet container thật.
- HTTP server test giúp phát hiện lỗi filter registration, URL pattern và behavior trong embedded container của project test.
- Nếu production chạy sau reverse proxy/API gateway, test loopback vẫn chưa chứng minh toàn bộ proxy/TLS/ingress behavior. Bổ sung E2E/staging theo mức rủi ro.

## 10. Chạy project và đối chiếu kết quả

Dùng JDK 17+ và Maven với quyền resolve dependencies. Từ thư mục chứa `pom.xml`:

```bash
java -version
mvn -version

mvn test

mvn -Dtest=InspectionMvcSliceTest test
mvn -Dtest=InspectionFullContextTest test
mvn -Dtest=InspectionHttpServerTest test
```

**Bộ test minh họa có 7 phương thức `@Test`**: `InspectionMvcSliceTest` có 4, `InspectionFullContextTest` có 2, `InspectionHttpServerTest` có 1, tổng **4 + 2 + 1 = 7**. Nếu bạn thêm test khác, số lượt chạy sẽ thay đổi.

Kết quả mong đợi là các assertion pass; Maven có thể in `BUILD SUCCESS` khi tất cả pass. Log Spring, thời gian build, thứ tự test và cổng `RANDOM_PORT` thay đổi theo máy nên **không có stdout cố định**.

Chạy application thật bằng lệnh:

```bash
mvn spring-boot:run
```

Trong terminal khác, sau khi server khởi động ở port mặc định và không bị override:

```bash
curl -i \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/api/context
```

Kỳ vọng status 200, hai response headers như ở hợp đồng và JSON body chứa tenant, request ID và greeting. Lệnh `curl` chạy với **ứng dụng thật**; `mvn test` trong chế độ MockMvc không cần server đang lắng nghe. Nếu port 8080 đã được process khác sử dụng, hãy chọn port khác qua config runtime.

## 11. Phân biệt Filter, Interceptor và Resolver qua những yêu cầu thường gặp

| Yêu cầu | Nên đặt ở đâu? | Lý do |
| --- | --- | --- |
| Gán correlation ID cho mọi Servlet request | Filter | Chạy trước DispatcherServlet, kể cả một số đường không vào controller |
| Kiểm tra định dạng header chỉ cho `/api/**` | Interceptor (như ví dụ) hoặc filter với mapping thích hợp | Gắn với API handlers; cần giới hạn scope |
| Inject `TenantId` vào tham số `@CurrentTenant` | HandlerMethodArgumentResolver | Trách nhiệm đúng là argument binding |
| Định nghĩa interceptor patterns và resolver | WebMvcConfigurer | Tập trung cấu hình MVC |
| Authorization/role/tenant permission | Spring Security + service policy | Không tin raw headers và path matching của interceptor làm security boundary |
| Thay đổi request body trước controller | Filter + wrapper có kiểm soát, hoặc HttpMessageConverter/RequestBodyAdvice phù hợp | Phụ thuộc mục tiêu và tầng tác động |
| Tùy chỉnh JSON serialize/deserialize | Jackson module, HttpMessageConverter config | Không lạm dụng interceptor để sửa JSON string |
| Format/parse date hay domain identifier từ query/path | Converter/Formatter, `@InitBinder` tùy case | Built-in MVC binding pipeline |
| Tạo standardized error JSON | `@RestControllerAdvice`/`@ExceptionHandler` | Chuyển exceptions thành HTTP error contract |
| Kiểm soát CORS | Spring MVC CORS và/hoặc Security CORS config | Tránh tự viết CORS phản hồi bằng interceptor không đồng nhất |
| Logging/timing end-to-end Servlet | Filter + try/finally/observability | Bao phủ trước/sau MVC, bảo đảm cleanup |
| Logging/timing handler cụ thể | HandlerInterceptor | Biết handler nào được chọn, annotations cụ thể |

**Không bắt buộc chỉ một công cụ cho mỗi use case.** Correlation ID có thể dùng Micrometer/OpenTelemetry thay custom Filter. Với một hệ thống đã có observation/tracing, ưu tiên tích hợp chính thức thay vì sáng tạo một chuẩn ID xung đột.

## 12. Các cạm bẫy cụ thể khi thiết kế và kiểm thử

### 12.1. `@WebMvcTest` có thể không tự nạp custom config như mong đợi

Một `@Configuration` thông thường đặt trong ứng dụng không nhất thiết xuất hiện ở MVC slice. Vì thế một test Controller có thể báo không resolve được `@CurrentTenant` hoặc thiếu interceptor. **Giải pháp trong project mẫu:** khai báo `@Import(MvcSupportConfiguration.class)` trên test slice.

Ngược lại, `@SpringBootTest` nạp config app rộng và thường scan class đó. Đừng đọc tên annotation rồi suy ra bean graph; kiểm tra endpoint behavior hoặc bean registry.

### 12.2. Quên `@AutoConfigureMockMvc` trong `@SpringBootTest`

`@SpringBootTest` tạo context nhưng không nhất thiết có sẵn `MockMvc` để inject. Với Spring MVC và `webEnvironment=MOCK`, thêm:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ExampleTest {
    @Autowired
    MockMvc mvc;
}
```

Đoạn này minh họa annotation và field; cần imports và method test để thành test hoàn chỉnh. `@WebMvcTest` tự auto-configure MockMvc.

### 12.3. Tạo Filter hai lần

Ví dụ vừa `@Component RequestIdFilter` vừa tự tạo `new RequestIdFilter()` trong `FilterRegistrationBean` hoặc thêm Filter vào Security chain mà vẫn auto-register như Servlet filter. Kết quả có thể là request header/log/logic bị xử lý trùng hoặc thứ tự bất ngờ. Chọn **một registration path** cho một trách nhiệm, có test kiểm chứng.

### 12.4. Dùng interceptor để thay Spring Security

Header `X-Tenant-Id=tenant-a` không chứng minh caller có quyền truy cập tenant-a. Validate regex chỉ kiểm tra **hình thức**. Với auth, dùng authenticated principal/claim, xác minh membership/role và kiểm soát truy vấn dữ liệu ở service/repository. Không đặt quyền truy cập vào một interceptor không bao phủ tất cả HandlerMappings/dispatch paths.

### 12.5. Trông đợi `afterCompletion` luôn chạy

Nếu `preHandle` trả false, callback sau của chính interceptor không chạy như luồng handler bình thường. Với async processing, lifecycle khác; có `AsyncHandlerInterceptor#afterConcurrentHandlingStarted` và dispatch tiếp. Nếu cần cleanup ThreadLocal/MDC sau mọi Servlet invocation, Filter với `try/finally` và dispatcher type phù hợp thường dễ kiểm soát hơn, nhưng cũng phải xử lý async/error đúng.

### 12.6. Tự tin rằng Filter luôn chạy cho mọi URL

Filter registration có URL patterns, dispatcher types và order. MVC Interceptor cũng chỉ được gọi khi tìm thấy handler phù hợp; lỗi trước HandlerMapping hoặc request không đi qua DispatcherServlet có thể không gọi. Test toàn bộ endpoint/path cần bảo vệ, kể cả route miss, async/error nếu thuộc yêu cầu.

### 12.7. Interceptor ghi response body quá muộn

Với `@RestController`, response body có thể đã được viết trước `postHandle`. Không dựa vào `postHandle` để sửa serialization hoặc header khi response đã commit. Dùng `ResponseBodyAdvice`, exception handler hoặc wrapper ở tầng phù hợp.

### 12.8. `@EnableWebMvc` vô hiệu hóa cấu hình Boot mong muốn

`@EnableWebMvc` trao quyền cấu hình MVC đầy đủ theo Framework, có thể làm ứng dụng mất Boot MVC auto-configuration tiện ích. Để thêm Filter/Interceptor/Resolver, dùng `WebMvcConfigurer` là đủ. Nếu buộc dùng `@EnableWebMvc`, phải tự quản các phần cấu hình tương ứng và có integration tests rõ ràng.

### 12.9. Custom resolver nhận quá rộng

Một resolver `supportsParameter` trả true với mọi `String` có thể gây tác dụng ngoài ý muốn. Dùng annotation **và type** cụ thể, như `@CurrentTenant TenantId`. Có case test cho một endpoint thông thường dùng `@RequestParam String` để bảo đảm không bị can thiệp khi cần.

### 12.10. Dùng raw request header như trusted context

Trong mẫu, interceptor đặt `validatedTenant` sau khi kiểm tra regex. Cái tên “validated” chỉ nói đã kiểm tra format; nó **không** nói đã xác thực quyền. Trong production, nếu resolver đọc principal hoặc signed claims, hãy tách contract đó rõ ràng và test cả mismatch/cross-tenant denial.

### 12.11. Chỉ đếm filter invocation, không kiểm tra output

`verify(filter).doFilter(...)` có thể được gọi đúng một lần nhưng request ID vẫn sai, header không có, hoặc resolver lấy dữ liệu không đúng. Test nên assert **response header, request-derived JSON, 400/200, service interaction** theo contract. Không assert số callback nội bộ khi không cần.

### 12.12. Lạm dụng test slice cho behavior container

`MockMvc` mô phỏng Servlet request/response trong process. Nếu cần chứng minh `FilterRegistrationBean` URL patterns/dispatcher types trong container, network sockets hoặc TLS, cần test `RANDOM_PORT` hoặc staging có hạ tầng gần production. Đừng suy ra server lắng nghe chỉ từ việc MockMvc trả 200.

## 13. Test nâng cao: order, async, error dispatch và observability

### 13.1. Thứ tự Filter và Interceptor

Nếu ứng dụng có nhiều Filter, thứ tự có thể quyết định MDC, security, request wrapper hoặc CORS. Có thể dùng `@Order` cho Filter bean hoặc `FilterRegistrationBean#setOrder`, nhưng **không giả định** tất cả filters của framework sẽ đứng đúng vị trí nếu không đọc cấu hình chain hiện có.

Trong Spring Security, filter chain có thứ tự nội bộ và `DelegatingFilterProxy` ở tầng Servlet. Một custom Servlet Filter bên ngoài security chain không tương đương custom Spring Security Filter bên trong chain. Test phải xác nhận kết quả ở ranh giới mong muốn, không chỉ số thứ tự.

### 13.2. Kiểm tra lifecycle callback

Khi cần kiểm tra đúng thứ tự callback, có thể tạo `TraceRecorder` lưu các mốc:

```text
filter.before
interceptor.preHandle
resolver.resolveArgument
controller.handle
interceptor.postHandle
interceptor.afterCompletion
filter.after
```

Đây là **thứ tự kỳ vọng cho một trường hợp MVC đồng bộ thành công được instrument phù hợp**, không phải stdout của project mẫu. Dùng một recording fake theo request/correlation ID, không dùng static list toàn cục khi test chạy parallel. Tránh làm test phụ thuộc chính xác những callback không thuộc hợp đồng cần bảo vệ.

### 13.3. `preHandle=false` và exception

Nếu interceptor tự đặt 400 rồi trả `false`, controller/resolver không chạy. Với exception trong controller, `postHandle` thông thường không chạy; `afterCompletion` được gọi sau khi dispatcher hoàn tất trong điều kiện lifecycle phù hợp. Nếu cần mapping exception sang JSON ổn định, sử dụng `@ControllerAdvice` hoặc `@RestControllerAdvice` phù hợp thay vì trông chờ interceptor sửa body.

Trong project mẫu, chỉ assert status 400 cho `sendError`, không gắn chặt test với error JSON tùy container/framework.

### 13.4. Async requests

`Callable`, `DeferredResult` hoặc xử lý async có thể gây dispatch bổ sung:

- `OncePerRequestFilter` có logic điều khiển ASYNC/ERROR dispatch và cần hiểu filter registration.
- Interceptor có thể nhận `afterConcurrentHandlingStarted` nếu triển khai `AsyncHandlerInterceptor`, rồi các callback trên dispatch tiếp theo.
- `MockMvc` async test có thể cần `asyncDispatch` sau khi `asyncStarted`.
- Với state trong ThreadLocal/MDC, phải dọn/reset theo đúng vòng đời; request attribute thích hợp cho dữ liệu request-scoped khi có nhiều thread.

Không bật/thử async chỉ bằng `Thread.sleep` cố định. Dùng công cụ phối hợp completion/lifecycle được Spring cung cấp.

### 13.5. CORS, converter và resource handlers trong cùng config

`WebMvcConfigurer` còn có:

```java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.test")
            .allowedMethods("GET");
}
```

Đoạn này minh họa (cần import `CorsRegistry`); **không thêm vào project chạy được nếu không có yêu cầu CORS**. Nếu có Spring Security, phải phối hợp policy CORS của Security chain để preflight thực sự hoạt động.

Đối với Jackson JSON, dùng các module/converters được quản lý trong Spring Boot thay vì tự thay toàn bộ `HttpMessageConverter` list thiếu mặc định. Đối với static assets, cấu hình `addResourceHandlers` có chủ đích và test URL/resource thực. Mỗi callback là một điểm extension **riêng**, không nên tập trung mọi request logic vào một WebMvcConfigurer lớn.

## 14. Các lỗi thường gặp khi kiểm thử custom MVC

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| `@CurrentTenant TenantId` không được resolve | Resolver chưa được thêm qua `addArgumentResolvers` hoặc config không nạp trong slice | `@Import` config vào `@WebMvcTest`, assert JSON tenant |
| Missing tenant vẫn trả 200 | Interceptor chưa đăng ký/mapping không khớp | Assert status 400, verify service không được gọi |
| Request ID không có trong header | Filter bean không được đăng ký hoặc MockMvc không add filters | Đảm bảo `@Bean Filter`, `@AutoConfigureMockMvc(addFilters=true)` nếu cần |
| Controller trả 200 trong MVC slice nhưng service tính sai ở runtime | Service đã `@MockitoBean` | Thêm unit/full-context test cho service thật |
| Filter chạy hai lần | Nhiều registration paths hoặc dispatch/async | Kiểm tra bean registration, dispatcher types, test behavior |
| HTTP client gọi 8080 trong `@SpringBootTest(MOCK)` bị connection refused | MOCK không mở listener | Dùng MockMvc hoặc `RANDOM_PORT`/`@LocalServerPort` |
| Bật `@EnableWebMvc` rồi JSON/CORS/resource mapping lỗi | Boot MVC auto-config không còn như trước | Gỡ annotation nếu chỉ cần extension bằng WebMvcConfigurer |
| Security trả 401/403 trước interceptor | Security filter chain xử lý sớm | Dùng Spring Security test config/users/CSRF theo contract |
| Header tự do chứa newline hoặc dữ liệu quá dài | Thiếu input validation | Validate whitelist/size, tránh log injection |
| `afterCompletion` không chạy khi preHandle=false | Đường lifecycle bị short-circuit | Cleanup đúng nơi, không trông chờ callback đó |
| Test flake do generated UUID | Assert UUID cố định hoặc state shared | Parse/so sánh header với body, không hard-code random |
| Test ảnh hưởng dữ liệu production | Full context tạo outbound beans thật | Profile test, fake adapters, sandbox DB, CI egress/credentials controls |

Để debug, ưu tiên xác nhận **(1)** bean/config có nạp không, **(2)** request có đi qua đúng chain không, **(3)** pattern có match không, **(4)** callback có chạy trước controller không, **(5)** data được truyền có đúng không. Đừng khắc phục bằng cách import toàn bộ production config vào MVC slice.

## 15. Checklist trước khi merge

- [ ] Filter, Interceptor và Argument Resolver được dùng đúng ranh giới.
- [ ] `RequestIdFilter` đăng ký đúng **một lần**, có URL pattern/order khi cần.
- [ ] `TenantInterceptor` được đăng ký rõ bằng `WebMvcConfigurer#addInterceptors` cho route thích hợp.
- [ ] `preHandle` trả `false` thì đã đặt response status/response hợp lý.
- [ ] Resolver có `supportsParameter` đủ hẹp, dùng annotation + type, không chiếm built-in args.
- [ ] Resolver lấy request-scoped value từ nguồn đáng tin cậy đã xác định, không gộp format validation với authorization.
- [ ] Không thêm `@EnableWebMvc` chỉ để mở rộng MVC trong ứng dụng Spring Boot.
- [ ] Trong `@WebMvcTest` đã import config/custom beans cần kiểm thử, mock business dependencies đúng mục tiêu.
- [ ] Trong full-context test đã kiểm tra logic service thật khi đó là yêu cầu.
- [ ] Test đã assert status/header/JSON và tình huống invalid input, không chỉ đếm callback.
- [ ] Với generated IDs/timestamp, test kiểm tra đặc tính và tính nhất quán, không hard-code.
- [ ] Có test HTTP `RANDOM_PORT` nếu cần kiểm tra Servlet container filter registration/network.
- [ ] Hiểu `postHandle`, `afterCompletion`, async/error dispatch không luôn chạy giống request đồng bộ.
- [ ] Hạn chế quyền production và bảo vệ dữ liệu nhạy cảm nếu config MVC liên quan authorization/tenant.
- [ ] Khi có Spring Security, filter order/CORS/auth được kiểm tra độc lập.

## 16. Bài tập và câu hỏi tự kiểm tra

**1.** Khi cần thêm request ID cho cả route MVC và request lỗi trước khi vào controller, nên chọn gì?

**Đáp án:** Servlet Filter là vị trí tự nhiên vì nằm trước DispatcherServlet; phải cấu hình registration/mapping/dispatcher types phù hợp. Không chắc Interceptor sẽ chạy khi chưa tìm được handler.

**2.** Với controller method `inspect(@CurrentTenant TenantId tenant)`, ai tạo `TenantId`?

**Đáp án:** `HandlerMethodArgumentResolver` được đăng ký qua `WebMvcConfigurer#addArgumentResolvers`; `supportsParameter` chọn tham số phù hợp, `resolveArgument` tạo đối tượng.

**3.** `@WebMvcTest` báo controller thiếu service bean; có nghĩa custom interceptor sai không?

**Đáp án:** Không nhất thiết. Business `@Service` nằm ngoài slice theo mặc định; dùng `@MockitoBean` cho service, còn custom MVC config có thể cần `@Import`.

**4.** Filter đã tạo `X-Request-Id`, nhưng response body ghi requestId khác, test nên bắt bằng cách nào?

**Đáp án:** Assert header và body phải bằng nhau, không chỉ `header().exists(...)`. Khi ID sinh bằng UUID ngẫu nhiên, không hard-code expected string.

**5.** Spring Security nên đặt ở interceptor hay filter chain?

**Đáp án:** Dùng cơ chế `SecurityFilterChain` và business authorization. MVC interceptor không phải lớp security chính vì khác biệt path matching và không bao phủ toàn bộ security semantics.

**6.** `@SpringBootTest(webEnvironment=MOCK)` có thể test Filter và Interceptor không, và đã có server TCP chưa?

**Đáp án:** Có thể kiểm tra chúng bằng `MockMvc` khi được cấu hình; **không** có embedded HTTP listener. Muốn chứng minh network/registration thực, dùng `RANDOM_PORT` và HTTP client.

**7.** Vì sao không dùng `@EnableWebMvc` chỉ để thêm `TenantArgumentResolver`?

**Đáp án:** `WebMvcConfigurer` là extension point đúng. `@EnableWebMvc` trao quyền MVC configuration rộng và có thể làm thay đổi Boot auto-configuration mong muốn.

**8.** `preHandle` trả `false`; liệu controller còn chạy, và `afterCompletion` của chính interceptor có chắc chạy không?

**Đáp án:** Controller bị chặn và `afterCompletion` không được gọi theo đường handler đã hoàn tất của interceptor đó như khi preHandle trả true. Cleanup cần đặt ở lifecycle phù hợp; xem xét async/error riêng.

**9.** Vì sao test `@WebMvcTest` pass không chứng minh production tenant authorization an toàn?

**Đáp án:** Test minh họa chỉ kiểm tra header format và MVC binding; multi-tenant permissions phải dựa trên authenticated principal/policy và được test tại security/business/data layers.

**10.** Khi cần một header response thêm sau khi JSON body đã viết, `postHandle` có phù hợp không?

**Đáp án:** Không thể trông chờ response chưa commit ở thời điểm đó. Đặt header trước chain/controller, hoặc dùng extension phù hợp như `ResponseBodyAdvice`/response wrapper tùy yêu cầu.

## 17. Tài liệu tham khảo

- [Spring Framework 6.2 – Servlet Filters và HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/filters.html): Servlet filter chain và MVC integration.
- [Spring Framework 6.2 – MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `InterceptorRegistry` và cảnh báo không dùng interceptor làm security layer.
- [Spring Framework – `WebMvcConfigurer`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html): các callback mở rộng MVC, `addArgumentResolvers`, `addInterceptors`.
- [Spring Framework – `HandlerMethodArgumentResolver`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/method/support/HandlerMethodArgumentResolver.html): `supportsParameter` và `resolveArgument`.
- [Spring Framework – `OncePerRequestFilter`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): request dispatch, async/error behavior.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest`, `MockMvc`.
- [Spring Boot 3.5 – Spring MVC Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html#web.servlet.spring-mvc.auto-configuration): `WebMvcConfigurer` và ảnh hưởng của `@EnableWebMvc`.

**Kết luận:** **Filter** bao quanh Servlet chain, **Interceptor** bao quanh handler MVC, **Argument Resolver** cung cấp tham số typed, còn **WebMvcConfigurer** đăng ký và tùy chỉnh những cơ chế đó. Test phải xác minh **status, headers, dữ liệu được phân giải và hậu quả của nhánh bị chặn**, đồng thời chọn `@WebMvcTest`, `@SpringBootTest(MOCK)` hoặc `RANDOM_PORT` theo ranh giới thực sự cần bảo vệ.