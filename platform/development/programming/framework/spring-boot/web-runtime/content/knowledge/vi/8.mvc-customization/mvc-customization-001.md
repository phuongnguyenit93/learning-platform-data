# Những thành phần Spring Boot tự cấu hình cho Spring MVC

Một ứng dụng dùng `spring-boot-starter-web` có thể khai báo `@RestController`, `@GetMapping` và trả JSON ngay khi khởi động, dù chúng ta chưa tự tạo `DispatcherServlet`, `RequestMappingHandlerMapping` hay `HttpMessageConverter`. Lý do là **Spring Framework cung cấp cơ chế Spring MVC**, còn **Spring Boot nhận diện điều kiện runtime và lắp ráp cấu hình mặc định phù hợp**. Hiểu rõ ranh giới này giúp mở rộng MVC đúng điểm mà không vô tình tắt các tiện ích Boot đang cung cấp.

Bài tập trung vào **ứng dụng Servlet/Spring MVC trên Spring Boot 3.3.x, Java 17+**: những thành phần được chuẩn bị, vai trò của chúng trong luồng HTTP, điều kiện tự cấu hình, cơ chế thay thế mặc định và cách tùy chỉnh an toàn. Một số thành phần chỉ xuất hiện khi dependency hoặc property tương ứng có mặt; “tự cấu hình” không có nghĩa mọi bean luôn tồn tại trong mọi dự án.

## 1. Ba tầng trách nhiệm

| Tầng | Trách nhiệm | Ví dụ |
|---|---|---|
| **Spring Framework MVC** | Định nghĩa hợp đồng và cơ chế xử lý HTTP | `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, `HandlerExceptionResolver`, `HttpMessageConverter`, `ViewResolver` |
| **Spring Boot auto-configuration** | Chọn cấu hình mặc định theo classpath, property, loại ứng dụng và bean hiện có | `WebMvcAutoConfiguration`, `DispatcherServletAutoConfiguration`, `ErrorMvcAutoConfiguration`, `HttpMessageConvertersAutoConfiguration` |
| **Mã ứng dụng** | Định nghĩa endpoint và chính sách riêng, hoặc bổ sung/thay thế cấu hình | `@RestController`, `@ControllerAdvice`, `WebMvcConfigurer`, cấu hình `spring.mvc.*` |

Spring MVC không phải là một servlet container. Servlet container như Tomcat nhận kết nối và chuyển request vào servlet; trong ứng dụng MVC, servlet đầu mối là `DispatcherServlet`. Bên trong nó, Spring MVC tìm handler phù hợp, gọi controller, chuyển đổi tham số và xử lý kết quả.

Spring Boot giảm khối lượng cấu hình bằng cách đăng ký servlet, kết nối các chiến lược MVC và cấu hình tài nguyên/error handling khi điều kiện thỏa. Trách nhiệm viết logic nghiệp vụ vẫn thuộc ứng dụng.

## 2. Điều kiện để Spring Boot tự cấu hình Spring MVC

Khi thêm dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Starter này thường đưa vào Spring MVC, Jackson cho JSON và Tomcat embedded. Khi chạy, Boot nhận diện môi trường **Servlet web application** rồi xét những auto-configuration tương ứng.

Về mặt khái niệm, `WebMvcAutoConfiguration` được kích hoạt khi:
- Các class Servlet và Spring MVC cần thiết có trên classpath.
- Ứng dụng đang chạy với `WebApplicationType.SERVLET`.
- Ứng dụng chưa cung cấp cấu hình MVC đầy đủ kiểu `WebMvcConfigurationSupport` làm Boot phải nhường quyền điều khiển.

Cơ chế điều kiện thường được biểu diễn bằng `@ConditionalOnClass`, `@ConditionalOnWebApplication`, `@ConditionalOnMissingBean` và các điều kiện liên quan. Auto-configuration chỉ tạo những bean phù hợp sau khi đánh giá điều kiện.

**Back-off** là quy tắc quan trọng: nếu ứng dụng đã cung cấp bean ở điểm mở rộng được Boot hỗ trợ, auto-configuration tương ứng có thể không tạo bean mặc định hoặc sử dụng bean của ứng dụng. Tuy nhiên, mức độ back-off khác nhau theo từng cấu hình; không nên cho rằng chỉ cần khai báo bất kỳ bean cùng interface là toàn bộ MVC auto-configuration sẽ biến mất.

Nếu chỉ có `spring-boot-starter-webflux` và runtime là Reactive, ứng dụng sử dụng chuỗi xử lý WebFlux; các khái niệm tương đương như codec/handler của WebFlux không phải cấu hình MVC Servlet. Khi cả MVC và WebFlux có mặt, Boot thường chọn Servlet theo mặc định. Cần kiểm tra web stack thực tế trước khi sửa cấu hình.

## 3. Bản đồ luồng xử lý request

Một request MVC điển hình đi qua các lớp sau:

~~~text
Client HTTP
     |
Embedded servlet container (Tomcat / Jetty / Undertow)
     |
Servlet Filter chain
     |
DispatcherServlet
     |
HandlerMapping  -> tìm controller/handler
     |
HandlerAdapter  -> đọc tham số, binder/converter, gọi handler
     |
Controller/handler
     |
     +--> @ResponseBody / ResponseEntity
     |       -> HttpMessageConverter -> JSON/text/bytes
     |
     +--> tên view / ModelAndView
             -> ViewResolver -> View -> HTML
     |
HTTP response

Nếu xảy ra exception:
HandlerExceptionResolver / @ExceptionHandler / @ControllerAdvice
     hoặc cơ chế error dispatch của container -> /error
~~~

Đây là sơ đồ **trách nhiệm xử lý**, không phải dấu hiệu mọi bean đều do Boot tự viết. Những implementation như `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter` là hạ tầng của Spring MVC; Boot khởi tạo và kết nối chúng thông qua cấu hình phù hợp.

## 4. DispatcherServlet và đăng ký với Servlet container

`DispatcherServlet` là front controller của Spring MVC. Mọi request đi vào servlet này đều được chuyển qua các chiến lược MVC: tìm mapping, gọi handler, xử lý kết quả và exception.

Spring Boot có `DispatcherServletAutoConfiguration` để cung cấp `DispatcherServlet` và bean đăng ký servlet khi phù hợp. Trong ứng dụng MVC thông thường:
- `DispatcherServlet` là servlet trung tâm.
- `DispatcherServletRegistrationBean` giúp đăng ký servlet với container.
- `ServletWebServerApplicationContext` phối hợp với embedded server factory để khởi động môi trường Servlet.

Boot mặc định đăng ký DispatcherServlet ở mapping root `/` của servlet context. Điều này khác với URL public thực tế khi có `server.servlet.context-path` hoặc `spring.mvc.servlet.path`.

Ví dụ:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /shop

spring:
  mvc:
    servlet:
      path: /
~~~

Với mapping controller `@GetMapping("/api/items")`, URL bên ngoài sẽ bắt đầu bằng `/shop/api/items`. Property context path thuộc Servlet container; property servlet path điều chỉnh mapping của DispatcherServlet. Không nên đổi các giá trị này khi chưa xét reverse proxy, đường dẫn static assets và strategy path matching.

Khi cần servlet thứ hai, hãy đăng ký có chủ đích bằng `ServletRegistrationBean` hoặc cơ chế được Boot hỗ trợ. Một servlet do ứng dụng tự tạo không mặc nhiên thay thế DispatcherServlet đang quản lý MVC.

## 5. HandlerMapping: chọn đúng handler

`HandlerMapping` chọn handler cho request. Thành phần thường gặp nhất cho controller annotation là `RequestMappingHandlerMapping`.

Nó dựa trên metadata:
- HTTP method: `@GetMapping`, `@PostMapping`, ...
- URL path và path variable.
- Điều kiện `params`, `headers`.
- `consumes`: định dạng request được chấp nhận.
- `produces`: định dạng response handler có thể cung cấp.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping(path = "/{id}", produces = "application/json")
    ItemResponse find(@PathVariable long id) {
        return new ItemResponse(id, "Book");
    }
}

record ItemResponse(long id, String name) {}
~~~

Spring MVC xây mapping từ annotation; khi request `GET /api/items/7` đến, nó chọn method tương ứng rồi chuyển việc gọi method cho HandlerAdapter.

Trong Boot 3.3, chiến lược path matching mặc định là `PathPatternParser`. Cần lưu ý:
- Pattern path có các quy tắc cụ thể; một số pattern kiểu Ant cũ không tương thích.
- Mặc định **không** dựa vào suffix `.json` trong URL để tự chọn handler/media type.
- Có thể cấu hình `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` khi thực sự cần behavior tương thích.
- Tài liệu Boot cảnh báo việc dùng `PathPatternParser` đồng thời prefix servlet path (`spring.mvc.servlet.path`) có giới hạn tương thích.

Không nên sửa toàn bộ strategy chỉ để giải quyết một endpoint chưa đúng mapping. Hãy xác định URL, HTTP method, annotation và server context path trước.

## 6. HandlerAdapter: gọi controller và chuyển đổi tham số

Sau khi tìm handler, `HandlerAdapter` chịu trách nhiệm biết cách gọi handler đó. Với annotation controller, thành phần chính là `RequestMappingHandlerAdapter`.

Nó phối hợp nhiều extension point của Spring MVC:
- `HandlerMethodArgumentResolver`: phân giải `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` và các kiểu argument khác.
- `WebDataBinder` và `ConversionService`: ràng buộc/đổi giá trị request thành kiểu Java.
- `HttpMessageConverter`: deserialize request body và serialize response body.
- `HandlerMethodReturnValueHandler`: xử lý `@ResponseBody`, `ResponseEntity`, `ModelAndView`, response async và kiểu trả về được hỗ trợ.
- Validation, exception handling và cấu hình khác theo dependency.

Ví dụ `GET /api/items/7` không gửi một đối tượng `long` trên wire. Giá trị path variable `"7"` là text; cơ chế binder/conversion chuyển nó thành `long` trước khi method được gọi.

Khi request path có giá trị không chuyển được sang kiểu đích, Spring MVC thường báo lỗi binding/type mismatch và trả HTTP 400 theo cơ chế exception resolution mặc định. Ngược lại, khi body JSON không hợp lệ, lỗi đọc body liên quan đến message converter.

## 7. HttpMessageConverters: đọc request và ghi response

Spring MVC sử dụng interface `HttpMessageConverter<T>`. Spring Boot cấu hình tập converter hợp lý dựa trên dependency và bean hiện có.

Ví dụ thường gặp:

| HTTP body | Converter/thư viện có thể liên quan | Cách sử dụng |
|---|---|---|
| `application/json` | Jackson JSON converter khi Jackson có mặt | `@RequestBody` DTO; `@RestController` trả record/object |
| `text/plain` | `StringHttpMessageConverter` | Đọc/ghi chuỗi |
| Nhị phân | `ByteArrayHttpMessageConverter` | `byte[]` |
| `application/x-www-form-urlencoded` | Converter form và cơ chế request parameters | Form fields |
| XML | Converter XML khi dependency tương ứng có mặt | DTO XML |

Spring MVC áp dụng hai header quan trọng:
- `Content-Type` cho biết **body client gửi** có định dạng nào.
- `Accept` cho biết client **muốn nhận** những định dạng nào.

Bên cạnh việc chọn handler theo `consumes` và `produces`, converter cũng phải đọc/ghi được media type và kiểu Java.

Ví dụ:

~~~java
@PostMapping(
    path = "/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ItemResponse create(@RequestBody CreateItemRequest input) {
    return new ItemResponse(10L, input.name());
}
~~~

Khi client gửi JSON hợp lệ, Jackson thường tạo `CreateItemRequest` từ body rồi ghi `ItemResponse` thành JSON. Nếu thiếu Jackson hoặc converter phù hợp, việc chỉ khai báo `produces="application/json"` không tự tạo khả năng serialize.

**Phân biệt hai hệ chuyển đổi:** Spring MVC `ConversionService` xử lý các giá trị như query/path/form sang kiểu Java; `HttpMessageConverter` xử lý body HTTP. MVC conversion service cũng **khác** conversion service dùng để bind `application.yml` vào `@ConfigurationProperties`. Không nên giả định converter Duration/DataSize dành cho configuration properties tự xuất hiện trong MVC binder.

Để mở rộng converter:
- Khai báo một `HttpMessageConverter<?>` bean khi phù hợp, để Boot đưa nó vào danh sách.
- Với thay đổi toàn bộ danh sách, có thể dùng các hook của `WebMvcConfigurer` như `extendMessageConverters` để bổ sung/điều chỉnh trong phạm vi MVC.
- Chỉ dùng `configureMessageConverters` khi thật sự muốn kiểm soát danh sách, vì có nguy cơ thay thế các converter mặc định tùy cách cấu hình.

## 8. Formatter, Converter, binding và MessageCodesResolver

Spring Boot tự đăng ký các bean `Converter`, `GenericConverter` và `Formatter` vào MVC conversion service khi được cung cấp theo cơ chế tương ứng. Điều này giúp:
- Chuẩn hóa cách đọc một kiểu domain từ query/path parameter.
- Thống nhất parse và format ngày, giờ hoặc số.
- Giảm mã chuyển đổi lặp lại ở controller.

Có thể đăng ký formatter/converter riêng bằng `WebMvcConfigurer.addFormatters`. Với format thời gian, Boot hỗ trợ một số thuộc tính `spring.mvc.format.*`.

Ví dụ:

~~~yaml
spring:
  mvc:
    format:
      date: iso
      date-time: iso
~~~

Hai property trên chỉ tác động **định dạng binding/format của Spring MVC theo phạm vi hỗ trợ**; chúng không tự sửa serializer Jackson cho JSON body. Định dạng JSON có thể được cấu hình qua Jackson hoặc annotation như `@JsonFormat` khi thích hợp.

`WebBindingInitializer` khởi tạo `WebDataBinder` cho request. Nếu ứng dụng cung cấp một bean `ConfigurableWebBindingInitializer`, Boot có cơ chế dùng bean đó để cấu hình Spring MVC.

`MessageCodesResolver` tạo mã lỗi cho binding/validation, giúp view hoặc bộ xử lý lỗi tra cứu thông điệp. Spring Boot có thể tạo resolver tương ứng khi đặt:

~~~properties
spring.mvc.message-codes-resolver-format=PREFIX_ERROR_CODE
~~~

Đây là cấu hình **mã lỗi binding**, không phải cấu hình status code HTTP, cũng không quyết định response JSON có body gì.

## 9. ViewResolver: khi controller trả view HTML

Không phải controller nào cũng trả JSON. Controller có `@Controller` có thể trả tên logical view:

~~~java
@Controller
class HomeController {

    @GetMapping("/home")
    String home() {
        return "home";
    }
}
~~~

Khi đó MVC dùng `ViewResolver` để tìm view tương ứng. Boot có thể cấu hình:
- `BeanNameViewResolver`: tìm bean `View` có tên khớp logical view.
- `ContentNegotiatingViewResolver`: phối hợp các resolver khác và việc thương lượng representation theo header `Accept`, khi điều kiện phù hợp.
- `InternalResourceViewResolver`: giải quyết resource/JSP theo prefix/suffix trong cấu hình hỗ trợ.
- Resolver của template engine như Thymeleaf hoặc FreeMarker khi starter/template dependency có mặt.

Ví dụ thêm dependency `spring-boot-starter-thymeleaf`, rồi tạo `src/main/resources/templates/home.html`:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Trang chủ</title></head>
<body><h1>Spring MVC</h1></body>
</html>
~~~

Controller trả `"home"` sẽ được view resolver Thymeleaf ánh xạ đến template tương ứng khi cấu hình mặc định còn hiệu lực.

**Phân biệt quan trọng:** `ContentNegotiatingViewResolver` dành cho cơ chế trả về **View**. Trường hợp `@RestController` trả object JSON thường sử dụng `HttpMessageConverter` qua return-value handler, không cần template engine hay view resolver. Vì vậy “có view resolver” không giải thích đầy đủ JSON serialization.

Để tùy chỉnh view, có thể khai báo bean ViewResolver phù hợp hoặc dùng `WebMvcConfigurer.addViewControllers` cho các tuyến đơn giản. Cẩn trọng với thứ tự resolver nếu có nhiều công nghệ view.

## 10. Static resources, WebJars, favicon và welcome page

Spring Boot tự cấu hình static resource handling cho ứng dụng MVC khi các mapping mặc định được bật.

Những thư mục classpath được hỗ trợ mặc định gồm:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
~~~

Một file `src/main/resources/static/css/site.css` thường truy cập qua `GET /css/site.css`. File `index.html` ở static locations có thể trở thành welcome page. Boot cũng hỗ trợ template `index` làm welcome page khi static index không tồn tại và template engine phù hợp có mặt.

Các tài nguyên tĩnh được phục vụ thông qua Spring MVC `ResourceHttpRequestHandler` và resource handler mapping. WebJars có convention `/webjars/**` khi resource được đóng gói đúng cách. Favicon `favicon.ico` trong static locations cũng được hỗ trợ.

Có thể thay đổi URL của static assets mà không phải tự thay toàn bộ MVC:

~~~yaml
spring:
  mvc:
    static-path-pattern: /assets/**
  web:
    resources:
      static-locations:
        - classpath:/static/
~~~

Sau cấu hình này, file `static/css/site.css` có thể truy cập tại `/assets/css/site.css`. `static-locations` thay danh sách location mặc định; hãy liệt kê đầy đủ các location muốn dùng.

Để tắt mapping static tự động:

~~~properties
spring.web.resources.add-mappings=false
~~~

Đừng tắt mapping chỉ vì `GET /api/unknown` trả 404 mà không có `NoHandlerFoundException`. Khi static handler được map vào `/**`, nó có thể khớp URL rồi báo `NoResourceFoundException` vì không tìm thấy file; hành vi này khác với không tìm được handler ngay từ đầu.

Welcome page là fallback: mapping controller thật, nếu có, được ưu tiên theo thứ tự handler mapping trước welcome page. Không nên xem `index.html` như endpoint có mức ưu tiên cao hơn controller.

Ngoài ra, `src/main/webapp` không phải nơi phù hợp để đặt static resources cho mọi executable JAR; nên dùng classpath locations được Spring Boot hỗ trợ.

## 11. Xử lý lỗi: exception resolver và /error

Trong request MVC có hai tầng lỗi:

**Tầng Spring MVC** xử lý exception phát sinh trong quá trình gọi handler:
- `HandlerExceptionResolver` là hợp đồng chọn cách xử lý exception.
- `@ExceptionHandler` trên controller hoặc `@ControllerAdvice` xử lý lỗi theo quy tắc Spring Framework.
- Spring Framework có resolver mặc định cho nhiều lỗi như body sai cú pháp, validation, HTTP method hoặc media type không phù hợp.

**Tầng Spring Boot** bổ sung luồng lỗi Servlet/application:
- `ErrorMvcAutoConfiguration` cấu hình xử lý lỗi mặc định khi điều kiện thỏa.
- `BasicErrorController` xử lý mapping `/error`.
- `ErrorAttributes` cung cấp thông tin lỗi theo cấu hình.
- Servlet container có thể chuyển đến error page tương ứng khi xảy ra lỗi không được xử lý theo luồng bình thường.

Mặc định, nội dung lỗi phụ thuộc client và cấu hình; máy khách nhận biểu diễn phù hợp (thường JSON), trình duyệt có thể thấy trang HTML lỗi khi chưa có view tùy chỉnh. Không nên giả định mọi response lỗi luôn chứa stack trace hoặc chi tiết exception; Boot có các thuộc tính `server.error.*` để kiểm soát mức tiết lộ thông tin.

Spring Boot 3.3 có hỗ trợ bật Problem Details theo RFC 9457:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Khi bật, các lỗi MVC được hỗ trợ có thể dùng `application/problem+json`. Ứng dụng có thể tùy chỉnh thông qua `ProblemDetail` và cơ chế exception handling phù hợp.

Để thay đổi cấu trúc lỗi mà vẫn giữ pipeline Boot, có thể cung cấp `ErrorAttributes` tùy chỉnh hoặc `@RestControllerAdvice` cho lỗi nghiệp vụ. Chỉ thay `ErrorController` nếu thật sự muốn sở hữu toàn bộ endpoint xử lý lỗi.

**Chẩn đoán:** Nếu REST endpoint có `@ExceptionHandler` nhưng response lỗi lại đi qua `/error`, hãy kiểm tra exception có được resolver xử lý không, request có được container error-dispatch không và response đã được commit hay chưa.

## 12. Multipart, form data và validation theo điều kiện

Nếu ứng dụng có Servlet MVC và multipart support phù hợp, `MultipartAutoConfiguration` giúp cấu hình xử lý multipart theo các property:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 10MB
~~~

Controller có thể nhận tệp với `MultipartFile`:

~~~java
@PostMapping(path = "/files", consumes = "multipart/form-data")
String upload(@RequestParam("file") MultipartFile file) {
    return file.getOriginalFilename();
}
~~~

Tuy nhiên, cơ chế multipart không chứng minh ứng dụng đã thiết lập mọi giới hạn bảo mật cho upload. Vẫn cần kiểm tra tên file, kích thước thực tế, định dạng, nơi lưu, kiểm soát quyền và nội dung độc hại nếu bài toán yêu cầu.

Validation của body hoặc tham số phụ thuộc API và thư viện validation có mặt. Ví dụ `@Valid` từ Jakarta Validation hoạt động khi có implementation tương ứng. Không nên khẳng định chỉ cần `spring-boot-starter-web` là mọi ràng buộc `@NotBlank` đều hoạt động; thông thường cần `spring-boot-starter-validation` cho Bean Validation.

## 13. CORS, interceptor và filter: phân biệt các điểm mở rộng

Spring MVC hỗ trợ:
- `@CrossOrigin` trên controller/method.
- CORS toàn cục qua `WebMvcConfigurer.addCorsMappings`.
- HandlerInterceptor qua `WebMvcConfigurer.addInterceptors`.
- Servlet Filter ở tầng Servlet container, chạy trước/sau DispatcherServlet theo filter chain.

Ví dụ CORS toàn cục giới hạn một origin:

~~~java
@Configuration(proxyBeanMethods = false)
class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example")
            .allowedMethods("GET", "POST");
    }
}
~~~

Đây là **cấu hình riêng của ứng dụng** thông qua extension point được Boot giữ mở; Boot không tự biết domain frontend và không tự tạo chính sách CORS cho mọi API.

Interceptor nằm trong luồng MVC, thường dùng cho quan sát, bổ sung request context hoặc logic chung gắn với handler. Nó không thay thế cơ chế xác thực/phân quyền đầy đủ của Spring Security. Servlet Filter phù hợp để can thiệp ở mức HTTP/Servlet, chẳng hạn encoding hoặc security filter chain.

Khi thêm một Filter làm bean trong Boot embedded server, bean có thể được đăng ký với servlet container. Nếu đã đăng ký qua `FilterRegistrationBean` hoặc một cơ chế khác, cần kiểm tra tránh đăng ký hai lần và thứ tự filter không đúng. Đặc biệt, security filter có thể ảnh hưởng CORS preflight; chính sách CORS cần đồng bộ với cấu hình bảo mật.

## 14. Những property MVC phổ biến

Spring Boot cung cấp nhiều điểm tùy chỉnh qua cấu hình; dưới đây là một số ví dụ có ý nghĩa rõ trong ứng dụng Servlet MVC:

| Property | Ảnh hưởng |
|---|---|
| `spring.mvc.servlet.path` | Path mapping của DispatcherServlet |
| `spring.mvc.static-path-pattern` | Pattern URL phục vụ tài nguyên tĩnh |
| `spring.web.resources.static-locations` | Danh sách nguồn chứa static resources |
| `spring.web.resources.add-mappings` | Bật/tắt resource mapping mặc định |
| `spring.mvc.pathmatch.matching-strategy` | Chiến lược so khớp URL controller |
| `spring.mvc.contentnegotiation.favor-parameter` | Cho phép thương lượng media type qua query parameter khi cấu hình |
| `spring.mvc.contentnegotiation.parameter-name` | Tên query parameter dùng khi favor-parameter bật |
| `spring.mvc.format.date` / `date-time` | Cách parse/format date/time trong MVC |
| `spring.mvc.message-codes-resolver-format` | Cách đặt message code của binding |
| `spring.mvc.problemdetails.enabled` | Bật Problem Details cho xử lý lỗi MVC được hỗ trợ |
| `spring.servlet.multipart.max-file-size` | Giới hạn kích thước một file multipart |
| `spring.servlet.multipart.max-request-size` | Giới hạn tổng kích thước multipart |

Cần phân biệt các namespace:
- `server.*` điều khiển Servlet container và môi trường web server.
- `spring.mvc.*` điều khiển phần lớn chiến lược Spring MVC.
- `spring.web.resources.*` điều khiển static resource support.
- `spring.servlet.multipart.*` điều khiển multipart support.
- `spring.jackson.*` và custom Jackson configuration điều khiển serialization/deserialization JSON trong phạm vi tương ứng.

Những namespace này liên quan với nhau, nhưng không thể dùng một property ở tầng server để thay việc đăng ký MVC converter hoặc ngược lại.

## 15. Ba mức tùy chỉnh Spring MVC

### Mức 1: chỉnh property

Ví dụ đổi static path, format date, cấu hình error response, giới hạn upload. Đây là mức ít can thiệp nhất và thường giữ nguyên cơ chế auto-configuration.

### Mức 2: thêm WebMvcConfigurer

Khi muốn thêm interceptor, converter, formatter, CORS hoặc view controller, hãy đăng ký `WebMvcConfigurer` mà **không** thêm `@EnableWebMvc`. Spring MVC và Boot vẫn quản lý cấu hình nền; callback của bạn bổ sung vào các điểm mở rộng.

~~~java
@Configuration(proxyBeanMethods = false)
class MyMvcConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/old-home", "/home");
    }
}
~~~

Một bean `WebMvcConfigurer` không có nghĩa mọi default MVC bean bị xóa. Phần lớn trường hợp không cần extends `WebMvcConfigurationSupport` và không cần tự khai báo `RequestMappingHandlerAdapter`.

### Mức 3: thay thế thành phần lõi hoặc sở hữu toàn bộ MVC

Nếu cần thay hẳn `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter` hoặc `ExceptionHandlerExceptionResolver` nhưng vẫn muốn Boot tiếp tục tùy chỉnh MVC, hãy cân nhắc `WebMvcRegistrations` để cung cấp instance theo hợp đồng Boot.

Nếu muốn **hoàn toàn điều khiển** cấu hình MVC, ứng dụng có thể thêm `@EnableWebMvc` hoặc một cấu hình kế thừa `DelegatingWebMvcConfiguration`. Khi đó `WebMvcAutoConfiguration` của Boot nhường quyền vì điều kiện auto-configuration không còn thỏa; bạn phải tự phục hồi các behavior mong muốn như static resources, message converter, view resolver, formatter và các thành phần khác.

Lưu ý: `@EnableWebMvc` không xóa toàn bộ Spring Boot và không vô hiệu hóa embedded web server hay các auto-configuration không liên quan; tác động chính là cách cấu hình Spring MVC. Vì thế, nếu ứng dụng đang chạy bình thường mà chỉ cần thêm một interceptor, `@EnableWebMvc` thường là lựa chọn quá rộng và dễ gây regression.

## 16. Ví dụ hoàn chỉnh: Boot cấu hình MVC, ứng dụng chỉ mở rộng đúng chỗ

Giả sử tạo một project Spring Boot 3.3.x / Java 17+ có dependency `spring-boot-starter-web`. Trong file `src/main/java/com/example/demo/MvcAutoConfigurationDemo.java` đặt toàn bộ mã sau. Đây là **mã ứng dụng chạy trong project Spring Boot**, cần dependency/framework; không phải ví dụ Java thuần để biên dịch độc lập bằng `javac`.

~~~java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class MvcAutoConfigurationDemo {
    public static void main(String[] args) {
        SpringApplication.run(MvcAutoConfigurationDemo.class, args);
    }
}

record ItemId(long value) {}
record ItemResponse(long id, String name) {}
record CreateItemRequest(String name) {}

@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemResponse find(@PathVariable ItemId id) {
        return new ItemResponse(id.value(), "Book");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemResponse create(@RequestBody CreateItemRequest input) {
        return new ItemResponse(10L, input.name());
    }
}

@Configuration(proxyBeanMethods = false)
class CustomMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            String.class,
            ItemId.class,
            value -> new ItemId(Long.parseLong(value))
        );
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request,
                    HttpServletResponse response, Object handler) {
                response.addHeader("X-MVC-Demo", "enabled");
                return true;
            }
        }).addPathPatterns("/api/**");
    }
}
~~~

**Vai trò của từng phần:**
- `SpringApplication.run` mở ứng dụng; Boot đăng ký DispatcherServlet và wiring MVC.
- `ItemController` được component scan phát hiện; Spring MVC tạo handler mapping cho GET/POST.
- `CustomMvcConfiguration` là cấu hình của ứng dụng; `addFormatters` bổ sung converter từ path variable String sang `ItemId`.
- `addInterceptors` bổ sung một header cho response tại các endpoint `/api/**`.
- JSON request/response sử dụng converter Jackson do Boot hỗ trợ khi Jackson có trên classpath.
- Ví dụ không dùng `@EnableWebMvc`, nên giữ nguyên auto-configuration MVC của Boot.

Chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Kiểm tra GET:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/7
~~~

Response điển hình:

~~~http
HTTP/1.1 200
Content-Type: application/json
X-MVC-Demo: enabled

{"id":7,"name":"Book"}
~~~

Thứ tự header, thông tin `charset` và những header phụ có thể thay đổi theo server. Cấu trúc JSON/body và header `X-MVC-Demo` là điều ví dụ cần minh họa.

Kiểm tra POST:

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Pen"}'
~~~

Body dự kiến:

~~~json
{"id":10,"name":"Pen"}
~~~

Kiểm tra lỗi chuyển kiểu:

~~~bash
curl -i http://localhost:8080/api/items/not-a-number
~~~

Giá trị `not-a-number` không chuyển thành `long` được; Spring MVC sẽ xử lý lỗi argument conversion và thông thường trả **400 Bad Request**. Nội dung body lỗi phụ thuộc `server.error.*`, Problem Details và các exception handler tùy chỉnh nếu có.

Để minh họa static resource auto-configuration, tạo file `src/main/resources/static/hello.txt` với nội dung `Static hello` rồi chạy:

~~~bash
curl -i http://localhost:8080/hello.txt
~~~

Không cần tự tạo controller phục vụ file này khi static resource mapping mặc định còn bật.

## 17. Thêm kiểm thử đảm bảo auto-configuration vẫn hoạt động

Project cần dependency test phù hợp, ví dụ `spring-boot-starter-test`. Một integration test MVC có thể kiểm tra controller mapping, converter và interceptor đã cấu hình:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcAutoConfigurationDemoTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldUseConverterControllerAndInterceptor() throws Exception {
        mockMvc.perform(get("/api/items/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Book"))
            .andExpect(header().string("X-MVC-Demo", "enabled"));
    }
}
~~~

Đặt test trong `src/test/java/com/example/demo/MvcAutoConfigurationDemoTest.java`. Với project Gradle đã cấu hình JUnit Platform, chạy:

~~~bash
./gradlew test
~~~

Một test `@WebMvcTest` sẽ nạp **slice MVC** thay vì toàn bộ application context. Nó hữu ích khi muốn kiểm tra controller và MVC components cô lập; còn `@SpringBootTest` với `@AutoConfigureMockMvc` phù hợp khi cần kiểm tra wiring của ứng dụng rộng hơn. Không nên suy luận từ một slice test rằng toàn bộ server configuration trong production chắc chắn giống hệt.

## 18. Cách kiểm tra chính xác những bean đã được Boot cấu hình

Khi một thành phần không như dự kiến, hãy kiểm tra theo thứ tự:

1. **Dependency/classpath.** Có `spring-boot-starter-web`, Jackson, validation, template engine tương ứng không?
2. **WebApplicationType.** Ứng dụng thật đang chạy Servlet hay Reactive?
3. **Dấu hiệu giành quyền MVC.** Có `@EnableWebMvc` hoặc cấu hình `WebMvcConfigurationSupport` ở đâu không?
4. **Bean tùy chỉnh.** Có bean `HttpMessageConverter`, `ViewResolver`, `ErrorAttributes`, `ConfigurableWebBindingInitializer` hoặc `WebMvcRegistrations` nào đã thay default?
5. **Property.** Có thay `spring.mvc.*`, `spring.web.resources.*`, `server.*` không?
6. **Condition evaluation report.** Kiểm tra lý do một auto-configuration được áp dụng hoặc bị loại.
7. **Runtime request.** Dùng curl/MockMvc xác nhận HTTP method, URL, content negotiation, response status, header và body.

Chạy Boot với debug để xem condition evaluation:

~~~bash
./gradlew bootRun --args="--debug"
~~~

Có thể bật log web chi tiết hơn cho tình huống cụ thể:

~~~properties
logging.level.org.springframework.web=DEBUG
~~~

Chỉ bật mức log này khi cần chẩn đoán vì request log có thể nhiều, nhất là môi trường tải lớn hoặc có dữ liệu nhạy cảm.

Nếu có Spring Boot Actuator và endpoint beans/conditions/mappings được bật, cấp quyền và expose phù hợp, chúng có thể giúp quan sát:
- `/actuator/beans`: các bean thực tế trong context.
- `/actuator/conditions`: đánh giá điều kiện auto-configuration.
- `/actuator/mappings`: các handler mapping.
Không nên expose các endpoint quản trị này công khai mà không có kiểm soát truy cập.

## 19. Những lỗi tùy chỉnh thường gặp

1. **Thêm `@EnableWebMvc` chỉ để đăng ký một interceptor.** Có thể khiến `WebMvcAutoConfiguration` nhường quyền, mất một phần Boot defaults. Dùng `WebMvcConfigurer` trước.
2. **Nhầm Spring MVC mặc định và Spring Boot auto-configuration.** Framework định nghĩa `HandlerMapping`, `HandlerAdapter`; Boot cung cấp wiring và behavior bổ sung theo điều kiện.
3. **Tự thay toàn bộ message converters để sửa một định dạng.** Dễ mất JSON/text converter mặc định. Ưu tiên thêm bean hoặc mở rộng danh sách đúng cách.
4. **Nhầm formatter của MVC với Jackson.** Parse path/query parameter và serialize JSON body nằm ở hai cơ chế khác nhau.
5. **Tưởng mọi template engine có sẵn.** Thymeleaf, FreeMarker và những engine khác chỉ hoạt động khi dependency/cấu hình phù hợp.
6. **Đặt static file sai vị trí.** Classpath `/static` là lựa chọn phổ biến cho executable JAR; `src/main/webapp` không phù hợp cho mọi cách đóng gói.
7. **Xem mọi 404 đều là NoHandlerFoundException.** Static resource handler `/**` có thể bắt path rồi báo NoResourceFoundException.
8. **Tự khai báo lỗi mà quên luồng `/error`.** Exception resolver và servlet error dispatch phục vụ những trường hợp khác nhau.
9. **Cấu hình CORS mà quên security filter chain.** Preflight có thể bị lớp security chặn trước khi vào controller.
10. **Trông chờ Boot tự triển khai nghiệp vụ.** Auto-configuration không tự tạo route API, validation domain, CORS origin hoặc cách phân quyền cho ứng dụng.

## 20. Ghi nhớ và tài liệu tham khảo

- Spring Boot tự cấu hình **môi trường Spring MVC** theo classpath, loại ứng dụng, property và bean hiện có.
- `DispatcherServlet` là front controller; `HandlerMapping` chọn handler; `HandlerAdapter` gọi handler và phối hợp binder, converter, return value handler.
- `HttpMessageConverter` xử lý body HTTP; `Converter`/`Formatter` của MVC xử lý binding các giá trị; `ViewResolver` xử lý view HTML; resource handler phục vụ static assets.
- Boot cung cấp hỗ trợ view resolver, resources, welcome page, error controller và các tiện ích binding/formatting; từng phần có điều kiện riêng.
- `WebMvcConfigurer` là cách thường dùng để **mở rộng MVC mà giữ Boot defaults**.
- `WebMvcRegistrations` dành cho tình huống cần thay một số thành phần lõi mà vẫn giữ hệ thống Boot cấu hình.
- `@EnableWebMvc` là quyết định nhận quyền cấu hình MVC đầy đủ; phải tự kiểm tra những behavior cần bảo toàn.
- Kiểm tra behavior qua dependency, condition report, mappings, bean list và HTTP test thay vì đoán từ annotation.

**Tài liệu chính thức để tra cứu tiếp:**
- Spring Boot 3.3, [Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Spring MVC auto-configuration, formatter/converter, view resolver, static content, error handling và mở rộng MVC.
- Spring Boot 3.3, [WebMvcAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html): lớp cấu hình và các thành phần liên quan.
- Spring Framework, [Web MVC reference](https://docs.spring.io/spring-framework/reference/web/webmvc.html): contract và cơ chế của DispatcherServlet, mapping, adapter, MVC configuration.

Nắm được sự khác biệt giữa **cơ chế MVC của Spring Framework**, **mặc định do Spring Boot tạo** và **cấu hình mà ứng dụng tự sở hữu** là nền tảng để tùy chỉnh Spring MVC có kiểm soát, tránh thay thế cả một pipeline chỉ vì cần thêm một tính năng nhỏ.
