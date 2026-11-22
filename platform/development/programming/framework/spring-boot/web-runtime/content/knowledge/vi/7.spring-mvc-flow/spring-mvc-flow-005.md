# HandlerMethodArgumentResolver và cơ chế tạo đối số đầu vào trong Spring MVC

## 1. Mục tiêu của bài học

Trong Spring MVC, một request HTTP không tự biến thành các tham số Java của controller. Spring Framework phải **tìm đúng handler method**, hiểu từng tham số trong chữ ký hàm, lấy dữ liệu từ path/query/header/body/session/request context rồi chuyển thành đối tượng có kiểu tương ứng. Cơ chế đó dựa trên các `HandlerMethodArgumentResolver`.

Sau bài này có thể:

- Giải thích vị trí của `HandlerMethodArgumentResolver` trong luồng `DispatcherServlet` → `RequestMappingHandlerAdapter` → gọi controller.
- Phân biệt hai phương thức `supportsParameter` và `resolveArgument`, cách chọn resolver và khả năng cache resolver theo tham số.
- Nhận biết các resolver chuẩn của Spring MVC: `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@RequestBody`, `@ModelAttribute`, `Principal`, `HttpServletRequest`, `BindingResult`, v.v.
- Viết và đăng ký một resolver riêng bằng `WebMvcConfigurer.addArgumentResolvers`, kiểm thử thành công và lỗi.
- Chọn đúng giải pháp giữa resolver, `Converter`, `HttpMessageConverter`, `WebDataBinder`, validation, `@RequestAttribute` và Spring Security.
- Tránh lỗi tương thích Spring MVC/WebFlux, lạm dụng resolver cho xác thực, hoặc thay thế nhầm các resolver mặc định.

Phạm vi ví dụ chạy được: **Spring Boot 3.5.x + Spring MVC + Java 17+** (Servlet/Jakarta), dùng Maven và JUnit Jupiter. Các API nền tảng ở đây tiếp tục có trong những dòng Spring Framework mới, nhưng starter, package và cách cấu hình test của Boot 4.x có thể khác; luôn đối chiếu tài liệu đúng phiên bản.

## 2. Cơ chế trong luồng xử lý request

Giả sử controller:

~~~java
@GetMapping("/orders/{orderId}")
String read(@PathVariable("orderId") long orderId,
            @RequestParam(name = "verbose", defaultValue = "false") boolean verbose,
            @RequestHeader("X-Trace-Id") String traceId) {
    return orderId + ":" + verbose + ":" + traceId;
}
~~~

Một HTTP request có thể là:

~~~http
GET /orders/42?verbose=true HTTP/1.1
Host: localhost:8080
X-Trace-Id: req-123
~~~

Trước khi gọi `read(42L, true, "req-123")`, Spring MVC phải giải quyết lần lượt ba đối số, gồm cả chuyển chuỗi `"42"` thành `long` và `"true"` thành `boolean`.

Luồng rút gọn:

~~~text
HTTP request
    |
    v
DispatcherServlet
    |
    v
HandlerMapping (thường là RequestMappingHandlerMapping)
    | xác định HandlerMethod từ URL, HTTP method, v.v.
    v
RequestMappingHandlerAdapter
    |
    v
ServletInvocableHandlerMethod
    |
    v
HandlerMethodArgumentResolverComposite
    |-- tham số 0 -> resolver cho @PathVariable -> 42L
    |-- tham số 1 -> resolver cho @RequestParam  -> true
    |-- tham số 2 -> resolver cho @RequestHeader -> "req-123"
    |
    v
Gọi phương thức Java read(...)
    |
    v
HandlerMethodReturnValueHandler / HttpMessageConverter thích hợp
    |
    v
HTTP response
~~~

**Phân biệt hai việc:** `HandlerMapping` chọn **phương thức controller**; `HandlerMethodArgumentResolver` tạo **giá trị đối số cho phương thức đã chọn**. Đây là hai pha khác nhau của Spring MVC. `HandlerMethodReturnValueHandler` xử lý giá trị **trả về**, không phải đầu vào.

`RequestMappingHandlerAdapter` là bộ phận phổ biến điều phối controller `@RequestMapping`/`@GetMapping`. Nó cung cấp nhiều resolver tạo thành một `HandlerMethodArgumentResolverComposite`, rồi dùng composite đó khi chuẩn bị các tham số của handler method.

## 3. Hợp đồng HandlerMethodArgumentResolver

Interface của MVC nằm ở:

~~~java
org.springframework.web.method.support.HandlerMethodArgumentResolver
~~~

Nó có hai phương thức chính (viết rút gọn, bỏ các annotation nullability phụ thuộc phiên bản):

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

### 3.1. supportsParameter: xác định mình có xử lý được tham số không

`supportsParameter(MethodParameter)` nhìn vào **metadata của tham số**, không phải request cụ thể:

- Kiểu Java: `TenantId.class`, `String.class`, `Principal.class`, v.v.
- Annotation: `@RequestParam`, `@RequestBody`, annotation riêng như `@CurrentTenant`.
- Khai báo generic, nested type, vị trí tham số và method chứa nó khi cần.

Ví dụ một resolver chuyên xử lý `@CurrentTenant TenantId` nên chỉ trả `true` khi tham số **có annotation đó và đúng kiểu TenantId**. Nếu chỉ trả `true` với mọi `String`, resolver rất dễ bắt nhầm tham số của controller khác.

Phương thức này nên **nhanh, quyết định theo chữ ký hàm và không có side effect**. Đừng đọc header trong `supportsParameter`: chưa có `NativeWebRequest` nào được truyền vào và việc chọn resolver không phải việc lặp lại cho từng request giống như việc tạo đối số.

### 3.2. resolveArgument: tạo đối tượng Java cho request hiện tại

Nếu resolver được chọn, `resolveArgument(...)` tạo **giá trị thực tế**:

- `parameter`: metadata của tham số cần giải quyết.
- `mavContainer`: trạng thái model/view khi xử lý handler method, hữu ích cho những resolver liên quan model.
- `webRequest`: truy cập header, query parameter, locale, request attributes, và có thể lấy native Servlet request khi cần.
- `binderFactory`: tạo `WebDataBinder` phục vụ bind/convert/validate cho những resolver cần; **không phải mọi resolver đều phải sử dụng**.

Resolver trả về `Object` có kiểu phù hợp với khai báo tham số; một số resolver có thể trả `null` khi hợp đồng và nullability cho phép. Nếu dữ liệu không hợp lệ, nên tạo exception phù hợp để request kết thúc bằng lỗi HTTP có thể dự đoán, thay vì truyền đối tượng sai vào controller.

Một resolver riêng dạng stateless thường được dùng chung giữa nhiều request. **Không lưu dữ liệu request vào field của resolver**: như vậy có nguy cơ rò dữ liệu giữa request và race condition khi nhiều luồng chạy đồng thời.

## 4. Composite chọn resolver và tính thứ tự

`HandlerMethodArgumentResolverComposite` duyệt một danh sách resolver có thứ tự. Với mỗi `MethodParameter`, nó tìm resolver đầu tiên có `supportsParameter(...) == true`; resolver đó được gọi để tạo đối số.

Các implementation hiện hành cache quan hệ **method parameter → resolver đã chọn** để tránh lặp lại việc tìm kiếm ở những request sau. Cache này **không** lưu giá trị đầu vào của request, nên một resolver có thể được chọn từ cache nhưng vẫn đọc header mới trong `resolveArgument` mỗi lần.

Hệ quả:

1. `supportsParameter` phải phản ánh **khả năng xử lý kiểu/annotation**, không phụ thuộc vào user/session/HTTP header của từng request.
2. Nếu hai resolver cùng nhận một tham số, **resolver đứng trước** sẽ được chọn; resolver sau không có cơ hội xử lý tham số đó.
3. Nếu không có resolver hợp lệ, Spring MVC có thể báo lỗi tham số không được hỗ trợ hoặc áp dụng resolver fallback cho simple type/`@ModelAttribute`. Đừng khẳng định một parameter không rõ annotation chắc chắn bị bỏ qua.
4. Nếu một resolver nhận xử lý tham số nhưng `resolveArgument` thất bại, framework không tự tìm resolver khác để “thử lại”; cần xử lý exception đúng nơi.

Trong cấu hình MVC mặc định, các resolver xử lý annotation tích hợp sẵn như `@RequestParam` và `@PathVariable` được ưu tiên theo quy tắc của framework. Custom resolver thêm qua `WebMvcConfigurer.addArgumentResolvers` phục vụ **kiểu tham số mới**, không phải cách thay thế resolver cho annotation chuẩn. Muốn can thiệp vào hành vi built-in là thao tác ở tầng `RequestMappingHandlerAdapter`, phức tạp và cần được kiểm thử riêng.

## 5. Các đối số Spring MVC hỗ trợ sẵn

| Controller parameter | Nguồn dữ liệu / cách tạo đối số | Ghi chú |
|---|---|---|
| `@PathVariable("id") Long id` | Biến đường dẫn từ URI template | Chuyển `String → Long`, sai định dạng có thể trả 400 |
| `@RequestParam("page") int page` | Query parameter hoặc form parameter trong Servlet request | Hỗ trợ defaultValue, required, `Optional` |
| `@RequestHeader("X-Id") String id` | HTTP header | Có hỗ trợ type conversion cho nhiều kiểu |
| `@CookieValue("lang") String lang` | HTTP cookie | Có required/defaultValue |
| `@RequestBody CreateOrder body` | HTTP request body qua `HttpMessageConverter` | JSON thường được đọc bằng converter dựa trên Jackson |
| `@RequestPart("file") MultipartFile file` | Một phần multipart | `@RequestPart` có thể dùng message converter với body của part |
| `@ModelAttribute SearchForm form` | Model và Servlet data binding | Bind vào object, validation nếu cấu hình |
| `HttpServletRequest request` | Native Servlet request | Chỉ Servlet/MVC; không cần annotation |
| `Principal principal` | Principal hiện tại | Phụ thuộc cấu hình xác thực/security |
| `Locale locale` | Locale resolver của request | Không phải chỉ đọc một header thô |
| `Model model` hoặc `BindingResult errors` | MVC model và trạng thái binding | `BindingResult` phải nằm đúng vị trí sau đối số được bind/validate |
| `@RequestAttribute("x") Object x` | Attribute do filter/interceptor/server thêm vào request | Thường đủ nếu chỉ cần truyền một context có sẵn |

Ví dụ dùng nhiều resolver chuẩn:

~~~java
@GetMapping("/search/{group}")
public String search(
        @PathVariable("group") String group,
        @RequestParam(name = "page", defaultValue = "1") int page,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId,
        java.util.Locale locale) {
    return group + ":" + page + ":" + traceId + ":" + locale.toLanguageTag();
}
~~~

Đây là **trích đoạn method minh họa**, không phải chương trình tự chạy độc lập. Method cho thấy cùng một request có thể dùng nhiều resolver khác nhau; không phải bạn phải viết resolver riêng cho từng kiểu dữ liệu.

### Type conversion, binding và validation không phải cùng một cơ chế

- **`HandlerMethodArgumentResolver`** quyết định cách *lấy và chuẩn bị* một đối số.
- **`ConversionService`/`Converter`/`Formatter`** chuyển đổi giá trị, ví dụ từ chuỗi query `"42"` sang `Long`. Một resolver như `RequestParamMethodArgumentResolver` có thể gọi binder/conversion để hoàn thành công việc.
- **`WebDataBinder`** bind request values lên object, xử lý lỗi chuyển đổi và tạo `BindingResult`.
- **`HttpMessageConverter`** đọc body theo content type rồi deserialize, ví dụ JSON thành `CreateOrder` cho `@RequestBody`.
- **Bean Validation** kiểm tra constraint sau quá trình bind/deserialize trong những điều kiện được Spring MVC hỗ trợ, ví dụ `@Valid @RequestBody`.

`@RequestBody` không đồng nghĩa `@ModelAttribute`. Đối với JSON, `@RequestBody` sử dụng HTTP message conversion; với form/query/path và model object, `@ModelAttribute` đi theo cơ chế data binding. `@Valid` không “biến” custom resolver thành một auto-validator; nếu resolver tự tạo object, hãy xác định rõ có cần validate bằng tay hoặc tích hợp `Validator` không.

## 6. Khi nào cần tự tạo HandlerMethodArgumentResolver?

Các trường hợp hợp lý:

- Controller lặp lại nhiều logic lấy và chuyển đổi **request context** thành một kiểu domain rõ nghĩa.
- Muốn truyền một đối tượng như `@CurrentTenant TenantId`, `@CurrentUser UserContext` hoặc `@ClientLocale ClientLocale` mà không lặp logic ở từng controller.
- Đối số cần kết hợp nhiều nguồn HTTP/request attributes, qua bước kiểm tra có điều kiện hoặc lookup có kiểm soát.
- Cần một cơ chế tập trung kiểm tra cú pháp, đưa lỗi 400 nhất quán và giảm việc controller phụ thuộc Servlet API.

Trước khi viết resolver riêng, xem có thể dùng cơ chế sẵn có không:

| Mong muốn | Giải pháp thường đơn giản hơn |
|---|---|
| Đọc một header dạng String | `@RequestHeader` |
| Chuyển chuỗi ID sang value object | `Converter<String, ID>` + annotation nguồn phù hợp |
| Bind form/query vào DTO | `@ModelAttribute`, `WebDataBinder` |
| Deserialize JSON | `@RequestBody` + `HttpMessageConverter` |
| Lấy request attribute do filter tạo | `@RequestAttribute` |
| Lấy user đã đăng nhập | `Principal`, `Authentication`, `@AuthenticationPrincipal` (Spring Security) |
| Chặn request chưa được xác thực | Spring Security filter chain, không phải resolver thay thế |

Ở ví dụ kế tiếp, việc lấy một header duy nhất thực ra có thể làm bằng `@RequestHeader`. Dùng custom resolver chủ yếu để minh họa cách đóng gói logic và tạo kiểu đối số riêng. **Không tin một header do client tự gửi để cấp quyền truy cập tài nguyên tenant**; phải xác thực identity/tenant membership trong tầng bảo mật phù hợp.

## 7. Ví dụ Spring Boot 3.5 + Java 17+: annotation @CurrentTenant

Xây dựng endpoint:

~~~http
GET /api/tenants/42/message?text=hi HTTP/1.1
Host: localhost:8080
X-Tenant-Id: acme_01
~~~

Controller nhận `@CurrentTenant TenantId tenant`, dù không có Spring annotation chuẩn nào tên `@CurrentTenant`. Resolver riêng sẽ đọc `X-Tenant-Id`, kiểm tra syntax, tạo record `TenantId`, rồi truyền cho controller. Ví dụ này **không thực hiện xác thực**; header chỉ là dữ liệu đầu vào và không được dùng để cấp quyền.

### 7.1. pom.xml

Tạo Maven project và lưu file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>argument-resolver-demo</artifactId>
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
~~~

Ví dụ khóa parent ở 3.5.0 để giải thích cùng một bộ API; dự án thực tế nên dùng **bản patch đã được kiểm thử và cập nhật bảo mật** của dòng được lựa chọn. Maven parent quản lý các dependency tương thích, không tự gắn version cho từng starter.

### 7.2. Entry point

File `src/main/java/com/example/resolverdemo/ResolverDemoApplication.java`:

~~~java
package com.example.resolverdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResolverDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResolverDemoApplication.class, args);
    }
}
~~~

### 7.3. Annotation mới

File `src/main/java/com/example/resolverdemo/CurrentTenant.java`:

~~~java
package com.example.resolverdemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {
}
~~~

`ElementType.PARAMETER` giới hạn nơi sử dụng; `RetentionPolicy.RUNTIME` cho phép Spring đọc annotation qua reflection trên `MethodParameter`.

### 7.4. Kiểu đối số đích

File `src/main/java/com/example/resolverdemo/TenantId.java`:

~~~java
package com.example.resolverdemo;

public record TenantId(String value) {
}
~~~

`record` có trong Java 17. Đối tượng immutable phù hợp để chuyển dữ liệu đã kiểm tra cú pháp cho controller; việc được tạo thành record **không có nghĩa nó được xác thực về mặt bảo mật**.

### 7.5. Resolver implementation

File `src/main/java/com/example/resolverdemo/CurrentTenantArgumentResolver.java`:

~~~java
package com.example.resolverdemo;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;

public final class CurrentTenantArgumentResolver
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

        String raw = webRequest.getHeader("X-Tenant-Id");
        if (raw == null || raw.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Missing X-Tenant-Id");
        }

        String normalized = raw.trim();
        if (!normalized.matches("[A-Za-z0-9][A-Za-z0-9_-]{0,31}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid X-Tenant-Id");
        }

        return new TenantId(normalized);
    }
}
~~~

Điểm cần quan sát:

1. `supportsParameter` chỉ dựa trên **annotation + kiểu Java**, không phụ thuộc request hiện tại.
2. `resolveArgument` nhận `NativeWebRequest` và lấy header **cho từng request**.
3. Kiểm tra header không rỗng và phải là 1–32 ký tự ASCII theo biểu thức trên; các giá trị như `acme_01` hợp lệ, `tenant with spaces` không hợp lệ.
4. `ResponseStatusException(HttpStatus.BAD_REQUEST, ...)` báo 400 khi thiếu hoặc sai header. Response body lỗi cụ thể tùy phiên bản và error-handling config.
5. Không dùng `mavContainer` hay `binderFactory` vì logic này không cần model/data binding. Điều đó hợp lệ với interface.
6. Không lưu `raw` hay `normalized` vào biến instance; resolver không giữ trạng thái của request.

Với hệ thống nhiều tenant thật, không được dùng cách đọc header này để xác định quyền truy cập. Có thể thay logic lấy header bằng đọc tenant đã xác thực từ Spring Security context hoặc request attribute do gateway/filter đáng tin cậy thiết lập, và **bắt buộc kiểm tra quyền truy cập tenant**.

### 7.6. Đăng ký với WebMvcConfigurer

File `src/main/java/com/example/resolverdemo/ResolverWebConfig.java`:

~~~java
package com.example.resolverdemo;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ResolverWebConfig implements WebMvcConfigurer {

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new CurrentTenantArgumentResolver());
    }
}
~~~

Đây là đường tích hợp được Spring MVC hỗ trợ cho **custom controller method argument types**. Trong Spring Boot, không cần thêm `@EnableWebMvc` cho ví dụ này; thêm annotation đó làm Spring Boot nhường quyền cấu hình MVC mặc định cho ứng dụng, dễ mất các tiện ích auto-configured ngoài ý muốn.

`addArgumentResolvers` **bổ sung** resolver; nó không gỡ bỏ `@RequestParam`, `@RequestBody`, `@PathVariable` hay những resolver chuẩn khác. Vì thế controller có thể vừa dùng `@CurrentTenant` vừa dùng tham số tích hợp sẵn.

### 7.7. Controller sử dụng cả custom và built-in resolver

File `src/main/java/com/example/resolverdemo/TenantMessageController.java`:

~~~java
package com.example.resolverdemo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TenantMessageController {

    @GetMapping("/api/tenants/{id}/message")
    public String message(
            @CurrentTenant TenantId tenant,
            @PathVariable("id") long id,
            @RequestParam(name = "text", defaultValue = "hello") String text,
            HttpServletRequest request) {

        return text + " | tenant=" + tenant.value()
                + " | id=" + id
                + " | method=" + request.getMethod();
    }
}
~~~

Trong cùng một lần gọi:

- `@CurrentTenant TenantId` → `CurrentTenantArgumentResolver`.
- `@PathVariable("id") long` → resolver hỗ trợ path variable và type conversion.
- `@RequestParam("text") String` → resolver hỗ trợ request parameter.
- `HttpServletRequest` → resolver tích hợp sẵn cho Servlet API.

Không có đoạn code nào trong controller tự parse `X-Tenant-Id`. Controller tập trung xử lý nghiệp vụ với đối số Java đã được chuẩn bị.

### 7.8. Chạy và kiểm tra kết quả

Cài JDK 17+ và Maven; chạy tại thư mục project có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Nếu dự án có Maven Wrapper thì tương đương `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`). Khi server đã lắng nghe cổng 8080 mặc định và không bị process khác chiếm:

~~~bash
curl -sS -H "X-Tenant-Id: acme_01" "http://localhost:8080/api/tenants/42/message?text=hi"
~~~

Response body chính xác:

~~~text
hi | tenant=acme_01 | id=42 | method=GET
~~~

Body do controller trả về không chứa ký tự xuống dòng; shell có thể hiển thị prompt ngay phía sau. Các dòng log Spring Boot và response headers có thể thay đổi theo môi trường.

Thử thiếu header:

~~~bash
curl -i "http://localhost:8080/api/tenants/42/message"
~~~

Dự kiến HTTP **400 Bad Request**, không gọi vào thân phương thức controller vì resolver đã ném `ResponseStatusException`.

Thử header sai định dạng:

~~~bash
curl -i -H "X-Tenant-Id: tenant with spaces" "http://localhost:8080/api/tenants/42/message"
~~~

Dự kiến HTTP **400 Bad Request**. Với query `text` không có giá trị, default `hello` được dùng; còn header `X-Tenant-Id` không có default vì resolver tự quy định rằng nó bắt buộc.

## 8. Kiểm thử MockMvc: xác nhận resolver được thực sự gọi

`MockMvc` cho phép thực thi chuỗi Spring MVC mà không phải mở TCP port thật. Với project Boot 3.5 vừa tạo, `spring-boot-starter-test` cung cấp công cụ test cần thiết.

File `src/test/java/com/example/resolverdemo/TenantMessageControllerTest.java`:

~~~java
package com.example.resolverdemo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TenantMessageControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void resolvesCustomAndBuiltInArguments() throws Exception {
        mockMvc.perform(get("/api/tenants/42/message")
                        .header("X-Tenant-Id", "acme_01")
                        .param("text", "hi"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "hi | tenant=acme_01 | id=42 | method=GET"));
    }

    @Test
    void rejectsMissingTenantHeader() throws Exception {
        mockMvc.perform(get("/api/tenants/42/message"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidTenantHeader() throws Exception {
        mockMvc.perform(get("/api/tenants/42/message")
                        .header("X-Tenant-Id", "tenant with spaces"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Nếu project có Maven Wrapper, dùng `./mvnw test` hoặc `mvnw.cmd test`. Ba phép kiểm tra lần lượt xác minh: (1) resolver tạo đúng `TenantId` cùng với built-in resolvers; (2) header thiếu gây 400; (3) header sai định dạng gây 400.

**Phạm vi của test:** test này kiểm tra cú pháp, việc đăng ký và thực thi resolver, **không kiểm tra an ninh đa tenant**. Muốn test xác thực/phân quyền phải bổ sung Spring Security, principal thật và các tình huống user không có quyền xem tenant của người khác.

## 9. Tương tác với @ModelAttribute, @RequestBody và validation

### 9.1. @RequestBody đọc body theo content type

Ví dụ:

~~~java
@PostMapping("/orders")
ResponseEntity<Void> create(@Valid @RequestBody CreateOrder request) {
    // Xử lý sau khi HttpMessageConverter đọc JSON và framework kiểm tra validation
    return ResponseEntity.noContent().build();
}
~~~

Đây là **method minh họa**, không phải phần của project hoàn chỉnh ở mục 7. Nó cần class `CreateOrder`, các import Spring/Validation và dependency hỗ trợ Bean Validation (ví dụ starter validation) trong project thật.

`RequestResponseBodyMethodProcessor` là một trong các argument resolver được Spring MVC dùng cho `@RequestBody`; nó cộng tác với `HttpMessageConverter` để deserialize body, rồi có thể áp dụng validation. Không nên tự viết resolver chỉ để đọc một JSON DTO thông thường, vì như vậy dễ phải làm lại xử lý content type, encoding, validation và lỗi HTTP.

Một `HttpMessageConverter` khác `HandlerMethodArgumentResolver`: converter biết **đọc/ghi representation**, còn resolver quyết định **tham số Java nào nhận representation đó**.

### 9.2. @ModelAttribute và WebDataBinder

Ví dụ:

~~~java
@GetMapping("/orders")
String list(@ModelAttribute OrderFilter filter, BindingResult errors) {
    if (errors.hasErrors()) {
        return "invalid";
    }
    return filter.toString();
}
~~~

Đây cũng là trích đoạn method cần class `OrderFilter`. `@ModelAttribute` có thể tạo/bind object từ request parameters và các nguồn phù hợp, thông qua `WebDataBinder`. `BindingResult` hoặc `Errors` phải đặt **ngay sau** tham số được bind/validate thì framework mới gắn đúng trạng thái lỗi.

Spring MVC có thể xử lý đối số complex không có annotation như implicit `@ModelAttribute`, nhưng viết rõ annotation giúp chủ động và rõ nghĩa hơn, đặc biệt trong ứng dụng cần native-image/AOT. Về bảo mật, tránh bind trực tiếp vào entity có các field nhạy cảm; dùng DTO dành riêng cho request, constructor binding hoặc allowed fields nếu cho phép property binding.

### 9.3. Validation và lỗi của tham số

Với `@Valid @RequestBody` hoặc `@Valid @ModelAttribute`, lỗi validation thông thường có thể dẫn tới `MethodArgumentNotValidException` và HTTP 400, hoặc được truyền vào `BindingResult` khi khai báo đúng vị trí. Nếu có constraint trực tiếp lên tham số method, Spring MVC có cơ chế method validation và `HandlerMethodValidationException`.

Resolver riêng không tự động có cùng cơ chế validation như các built-in resolver. Ví dụ `CurrentTenantArgumentResolver` chủ động kiểm tra regex và ném `ResponseStatusException(400)`. Với một value object có constraint phức tạp, cần xác định nơi validate và error contract rõ ràng thay vì nghĩ `@Valid` sẽ luôn được gọi tự động.

## 10. Một số vấn đề thiết kế và bảo mật

### 10.1. Đừng dùng request header làm identity đáng tin

`X-Tenant-Id` trong ví dụ hoàn toàn do client cung cấp. Kẻ tấn công có thể đổi header tùy ý nếu không có cơ chế xác thực/ràng buộc ở nơi khác. Với ứng dụng production:

- Xác thực qua Spring Security, token hoặc session theo kiến trúc hệ thống.
- Kiểm tra tenant ID yêu cầu có thuộc quyền của principal đã được xác thực hay không.
- Nếu cần truyền thông tin từ gateway, phải có mô hình trust boundary rõ ràng và loại bỏ/ghi đè header không đáng tin ở gateway.
- Có thể đọc `SecurityContextHolder`/`@AuthenticationPrincipal` hoặc request attribute **đã được tầng bảo mật kiểm tra**; resolver chỉ giúp chuyển context thành đối số, không thay thế authorization.

### 10.2. Thread safety

Resolver thường là singleton và được dùng cho rất nhiều request song song. Chỉ giữ dependency thread-safe/immutable trong field; không lưu tenant ID, token, locale, payload hay request hiện tại ở mutable field. Đọc thông tin theo từng request từ `NativeWebRequest`.

### 10.3. Không nuốt hoặc đọc body tùy tiện

Dùng `@RequestBody` để framework xử lý request body. Nếu custom resolver tự đọc `InputStream` rồi controller lại dùng `@RequestBody`, body có thể đã bị tiêu thụ, gây lỗi parse hoặc body rỗng. Với form data, Servlet API còn có quy tắc parse parameter ảnh hưởng tới stream; không kết hợp đọc thủ công tùy tiện.

### 10.4. Dấu @EnableWebMvc trong Spring Boot

Chỉ khai báo `@Configuration implements WebMvcConfigurer` thường đủ để thêm custom resolver mà vẫn giữ auto-configuration MVC của Boot. Thêm `@EnableWebMvc` chuyển phần lớn trách nhiệm cấu hình MVC sang ứng dụng, có thể làm các thiết lập khác của Boot thay đổi ngoài ý muốn. Không dùng `@EnableWebMvc` chỉ để giải quyết chuyện thêm resolver.

### 10.5. Spring MVC không phải Spring WebFlux

Bài này nói về **Servlet MVC**: `org.springframework.web.method.support.HandlerMethodArgumentResolver` và `WebMvcConfigurer`. Spring WebFlux có các SPI và lifecycle reactive riêng, trong đó có các resolver trả publisher và `ServerWebExchange`. Không copy cùng một implementation MVC sang WebFlux rồi giả định sẽ được gọi.

### 10.6. Cấu hình kiểm thử thay đổi theo bản Spring Boot

Ví dụ ở mục 7–8 cố định ở Boot 3.5 để package `@AutoConfigureMockMvc`, `@SpringBootTest`, starter test và imports nhất quán. Với Boot 4.x, một số module/starter và package auto-configuration/test đã được tổ chức lại; phải kiểm tra reference và javadoc của đúng version thay vì sao chép không chỉnh sửa.

## 11. Lỗi thường gặp, triệu chứng và hướng kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Resolver không được gọi | `supportsParameter` trả false; annotation không giữ runtime; config không được scan | Kiểm tra `@Retention(RUNTIME)`, generic/type, package và `WebMvcConfigurer` |
| Controller nhận object như form/model thay vì custom | Resolver không được đăng ký, nên implicit `@ModelAttribute` nhận tham số complex | Thêm custom resolver, dùng annotation riêng, test đúng controller |
| Custom resolver “đè” những method khác | `supportsParameter` quá rộng, như nhận mọi `String` | Match annotation + kiểu Java cụ thể |
| Muốn override `@RequestParam` nhưng không thành công | `addArgumentResolvers` không được thiết kế để thay resolver annotation chuẩn | Ưu tiên custom `Converter`/`Formatter`; chỉ sửa HandlerAdapter trong trường hợp đặc biệt |
| Lỗi 400 khi parse input | Type conversion/binding/validation hoặc exception do resolver ném | Kiểm tra parameter, header, path, error logs và kiểu exception |
| HTTP 415 Unsupported Media Type | Content-Type không phù hợp `HttpMessageConverter` cho `@RequestBody` | Gửi đúng JSON/Content-Type hoặc cấu hình converter |
| HTTP 400 khi JSON body sai cú pháp | `@RequestBody` không deserialize được | Kiểm tra JSON, DTO và exception handler |
| Validation không chạy trên custom value object | Resolver tự tạo object nhưng không tích hợp validator | Kiểm tra constraint bằng code hoặc cơ chế Validator rõ ràng |
| Dữ liệu tenant của request A xuất hiện ở B | Lưu dữ liệu request trong field shared của resolver | Thiết kế resolver stateless, chỉ đọc request hiện tại |
| `BindingResult` không hoạt động | Vị trí param không ngay sau đối tượng liên quan hoặc dùng sai flow | Đặt liền sau `@ModelAttribute`/`@RequestBody` phù hợp |
| Native-image/AOT lỗi binding | Dùng implicit `@ModelAttribute`, thiếu reflection hints | Annotation rõ ràng và kiểm tra cấu hình AOT |
| Boot MVC config bị thay đổi nhiều | Thêm `@EnableWebMvc` để đăng ký custom resolver | Bỏ `@EnableWebMvc`, dùng `WebMvcConfigurer` |

Nếu cần debug cơ chế chọn resolver, đặt breakpoint trong `supportsParameter`, `resolveArgument` và `HandlerMethodArgumentResolverComposite.getArgumentResolver` hoặc bật logger phù hợp; kiểm tra breakpoint của resolver riêng trước khi điều tra cách framework fallback sang `@ModelAttribute`.

## 12. Checklist khi đưa custom argument resolver vào dự án

1. Controller thật sự cần **đối số mới** hay chỉ cần `@RequestHeader`, `@RequestAttribute`, `Converter` hoặc `@AuthenticationPrincipal`?
2. `supportsParameter` có giới hạn đủ hẹp bằng annotation/type/generic và không phụ thuộc request không?
3. `resolveArgument` có trả đúng kiểu, xử lý thiếu/không hợp lệ và không giữ mutable request state không?
4. Có dùng đúng `WebMvcConfigurer.addArgumentResolvers`, không bật `@EnableWebMvc` chỉ vì thêm resolver không?
5. Có bảo đảm dữ liệu identity/tenant được xác thực và phân quyền tại tầng bảo mật, không tin input từ client không?
6. Có kiểm thử request đúng, thiếu dữ liệu, sai định dạng và các endpoint không liên quan không?
7. Có tránh đọc request body hai lần, tránh làm việc nặng/blocking không cần thiết và đo hiệu năng khi resolver phải lookup service không?
8. Có kiểm tra phiên bản Spring Boot/Framework và phân biệt Servlet MVC với WebFlux không?

**Kết luận:** `HandlerMethodArgumentResolver` là mắt xích biến **metadata của tham số handler** và **dữ liệu của từng request** thành **giá trị Java** mà controller nhận. Spring MVC có sẵn nhiều resolver mạnh; custom resolver nên được dùng để diễn đạt một kiểu tham số miền ứng dụng mới, với hợp đồng lựa chọn rõ ràng, xử lý lỗi nhất quán và kiểm thử đầy đủ.

## Tài liệu chính thức

- Spring Framework — MVC Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — `@RequestBody` và `HttpMessageConverter`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — `@ModelAttribute` & binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — Controller Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `WebMvcConfigurer` API, `addArgumentResolvers`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Framework — MVC Configuration (`@EnableWebMvc`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html
- Spring Framework — `HandlerMethodArgumentResolver` API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/method/support/HandlerMethodArgumentResolver.html
- Spring Framework — `HandlerMethodArgumentResolverComposite` API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/method/support/HandlerMethodArgumentResolverComposite.html
- Spring Boot 3.5 — Servlet Web Applications và `WebMvcConfigurer`: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
