# HandlerAdapter: gọi thành phần xử lý và hỗ trợ chữ ký phương thức trong Spring MVC

## 1. HandlerAdapter giải quyết vấn đề gì?

Khi một HTTP request đến ứng dụng **Spring Web MVC**, `DispatcherServlet` là điểm điều phối trung tâm. Nó tìm ra *handler* phù hợp với request rồi cần gọi handler ấy. Tuy nhiên, handler có thể được biểu diễn theo nhiều kiểu: một phương thức controller có `@GetMapping`, một đối tượng triển khai `HttpRequestHandler`, hoặc kiểu controller cũ triển khai `Controller`.

`DispatcherServlet` không nên tự viết riêng logic gọi cho từng kiểu handler. Spring tách hai trách nhiệm:

- **`HandlerMapping`:** quyết định *request này khớp với handler nào?*; thường trả một `HandlerExecutionChain` chứa handler và các interceptor liên quan.
- **`HandlerAdapter`:** quyết định *có gọi được handler này không và gọi như thế nào?*; nếu hỗ trợ, nó thực hiện lời gọi với ngữ cảnh HTTP phù hợp, rồi trả kết quả cho bước xử lý tiếp theo.

Với annotated controller hiện đại, implementation thường gặp nhất là **`RequestMappingHandlerAdapter`**. Nó hỗ trợ nhiều chữ ký phương thức controller: tham số từ URI, query, header, body, model, session, Servlet API; chuyển đổi kiểu, binding, validation; và xử lý giá trị trả về thành view, response body hoặc phản hồi bất đồng bộ.

**Ý chính:** `HandlerAdapter` là lớp cầu nối giữa handler do mapping chọn và cơ chế thực thi handler. Nó không có nhiệm vụ tự tìm URL mapping hay thực hiện nghiệp vụ thay controller.

## 2. Vị trí trong vòng đời một request MVC

Ví dụ:

~~~http
GET /api/orders/42?details=true HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Luồng cơ bản:

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
Filter chain
    |
    v
DispatcherServlet
    |
    | (1) hỏi các HandlerMapping
    v
RequestMappingHandlerMapping
    |
    | trả HandlerExecutionChain:
    |   HandlerMethod + các HandlerInterceptor
    v
DispatcherServlet
    |
    | (2) chọn HandlerAdapter có supports(handler) == true
    v
RequestMappingHandlerAdapter
    |
    | (3) giải tham số:
    |     @PathVariable id       <- "42" -> long
    |     @RequestParam details   <- "true" -> boolean
    |     HttpServletRequest...  <- ngữ cảnh request
    | (4) gọi phương thức controller
    | (5) xử lý giá trị trả về:
    |     record/Object -> JSON body, hoặc ModelAndView -> view
    v
DispatcherServlet
    |
    | hoàn tất interceptor, exception handling/rendering nếu cần
    v
HTTP response
~~~

Đây là sơ đồ *luồng logic*; nó lược bỏ một số nhánh như multipart, async dispatch, lỗi và tối ưu HTTP cache. Với `@ResponseBody` hoặc `@RestController`, adapter cùng return-value handler thường ghi response body trực tiếp qua converter; không cần tìm view HTML.

Một cách nhìn rõ ràng hơn:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| `Filter` (Servlet) | Request/response cần xử lý gì trước khi vào MVC? | Security filter, logging |
| `DispatcherServlet` | Ai điều phối pipeline của request? | `doDispatch(...)` |
| `HandlerMapping` | Handler nào phù hợp URI, HTTP method, headers...? | `RequestMappingHandlerMapping` |
| `HandlerInterceptor` | Có cần xử lý trước/sau handler? | `preHandle`, `postHandle` |
| `HandlerAdapter` | Gọi handler đã chọn bằng cách nào? | `RequestMappingHandlerAdapter` |
| `HandlerMethodArgumentResolver` | Tạo từng đối số method từ đâu? | `@PathVariable`, `@RequestParam` |
| `HandlerMethodReturnValueHandler` | Kết quả method sẽ đi đâu? | JSON response, view/model |
| `HttpMessageConverter` | Chuyển body HTTP ↔ Java object như thế nào? | JSON converter dùng Jackson |
| `HandlerExceptionResolver` | Nếu phát sinh lỗi, chuyển thành xử lý/phản hồi nào? | `@ExceptionHandler`, resolver mặc định |
| `ViewResolver` | Tên view tương ứng view nào? | Thymeleaf template |

**Không nhầm `HandlerMapping` và `HandlerAdapter`:** “tìm phương thức controller” và “chuẩn bị đối số rồi gọi phương thức” là hai công việc khác nhau. `HandlerAdapter` nhận handler đã được chọn, chứ không tự chọn endpoint bằng URL.

## 3. Hợp đồng HandlerAdapter

Trong Spring MVC, contract chính nằm tại `org.springframework.web.servlet.HandlerAdapter`. Dạng rút gọn để hiểu ý nghĩa:

~~~java
public interface HandlerAdapter {
    boolean supports(Object handler);

    ModelAndView handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception;

    long getLastModified(HttpServletRequest request, Object handler);
}
~~~

Đoạn trên minh họa hình dạng contract trên nhánh Spring Framework 6.x; nó không phải một file cần chép vào ứng dụng. Cần các import Jakarta Servlet và `ModelAndView` tương ứng.

- **`supports(handler)`:** báo adapter có hỗ trợ kiểu handler mà mapping trả ra hay không. `DispatcherServlet` có thể có nhiều adapter, và chọn adapter thích hợp.
- **`handle(request, response, handler)`:** thực hiện việc xử lý handler. Với annotated method, quá trình bao gồm chuẩn bị argument, invoke method, rồi xử lý return value.
- **`getLastModified(...)`:** một điểm mở rộng liên quan HTTP cache/Last-Modified của handler; không phải API dùng để chọn mapping. Với annotated `@RequestMapping`, Spring thường sử dụng các cơ chế conditional request chuyên biệt như `WebRequest.checkNotModified(...)`.

Kiểu trả về `ModelAndView` của `handle` có thể **null** khi response đã được xử lý trực tiếp (ví dụ controller trả JSON qua `@ResponseBody`). Điều này **không có nghĩa request thất bại**.

Không nên tự triển khai `HandlerAdapter` cho một `@RestController` bình thường. Spring MVC đã cấu hình những adapter tiêu chuẩn. Tùy biến chữ ký phương thức thông thường chỉ cần thêm **argument resolver** hoặc thành phần hỗ trợ khác.

## 4. Những HandlerAdapter thường gặp

| Handler do HandlerMapping trả về | Adapter hỗ trợ | Mục đích |
| --- | --- | --- |
| `HandlerMethod` của phương thức `@RequestMapping` / `@GetMapping` ... | `RequestMappingHandlerAdapter` | Luồng controller annotation hiện đại |
| Đối tượng thực thi `HttpRequestHandler` | `HttpRequestHandlerAdapter` | Gọi contract `handleRequest(request, response)` |
| Đối tượng thực thi `org.springframework.web.servlet.mvc.Controller` kiểu cũ | `SimpleControllerHandlerAdapter` | Gọi contract `handleRequest(...)` legacy |

`RequestMappingHandlerMapping` thường ánh xạ tới một **`HandlerMethod`**, là đối tượng mô tả bean/controller cùng Java method đã được tìm thấy. Nó khác với việc “đưa nguyên controller class vào adapter”.

Ví dụ cùng ứng dụng có thể có controller REST annotated và handler chuyên dụng cho resource. `DispatcherServlet` sử dụng abstraction adapter để hai kiểu được gọi thống nhất. Tuy nhiên, khi học Spring MVC mới, trọng tâm là `RequestMappingHandlerAdapter`; hai adapter còn lại giúp hiểu vì sao interface này tồn tại.

### Chọn adapter có phải là chọn controller?

Không. Việc chọn endpoint dựa vào mapping đã xảy ra trước đó. Nếu có:

~~~java
@GetMapping("/items/{id}")
public Item getItem(@PathVariable long id) { ... }
~~~

thì `RequestMappingHandlerMapping` đối chiếu path và method rồi trả `HandlerMethod` trỏ tới `getItem`. `RequestMappingHandlerAdapter` nhận `HandlerMethod` ấy, suy ra cách cung cấp `id` và gọi method. Nó **không chạy thuật toán tìm URL lần nữa**.

### Một adapter có thể phục vụ nhiều chữ ký method

Những phương thức sau đều có thể dùng cùng `RequestMappingHandlerAdapter`:

~~~java
@GetMapping("/hello")
String hello(@RequestParam(defaultValue = "Guest") String name) { ... }

@PostMapping("/orders")
ResponseEntity<Order> create(@Valid @RequestBody NewOrder request) { ... }

@GetMapping("/report")
ModelAndView report(Model model) { ... }
~~~

Các dấu `...` là phần thân minh họa nên **không thể biên dịch riêng**. Sự đa dạng tham số/return type được xử lý bằng các danh sách resolver/handler chuyên trách, chứ không phải mỗi chữ ký method cần một implementation `HandlerAdapter` riêng.

## 5. Bên trong RequestMappingHandlerAdapter

Một nhánh điển hình cho annotated method:

~~~text
HandlerMethod
    |
    v
RequestMappingHandlerAdapter
    |
    v
ServletInvocableHandlerMethod / cơ chế invocation
    |
    +-- Argument resolvers (theo từng tham số)
    |     @PathVariable -> URI template variable
    |     @RequestParam  -> query/form parameter
    |     @RequestHeader -> HTTP header
    |     @RequestBody   -> HttpMessageConverter -> Java object
    |     @ModelAttribute -> binder/converter/validator
    |     Servlet request/model/session -> ngữ cảnh framework
    |
    +-- Controller method được gọi với argument đã resolve
    |
    +-- Return-value handlers (theo kiểu trả về/annotation)
          @ResponseBody -> HttpMessageConverter -> HTTP body
          ResponseEntity -> status + header + body
          String view name -> ModelAndView/view rendering
          Callable / DeferredResult -> async processing tương ứng
~~~

Tên class nội bộ hữu ích khi đọc stack trace, nhưng **không phải API mà ứng dụng phải tự gọi**. Spring quản lý chúng cho hầu hết annotated controllers.

### 5.1 Argument resolver lựa chọn theo gì?

Một `HandlerMethodArgumentResolver` có hai thao tác chính:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

Đây là trích lược signature để đọc hiểu; không phải file interface hoàn chỉnh.

`supportsParameter` hỏi resolver có biết tạo giá trị cho một tham số cụ thể không, dựa vào annotation, kiểu Java và metadata. `resolveArgument` lấy dữ liệu từ HTTP request và/hoặc binder để tạo object truyền vào phương thức controller.

Ví dụ cụ thể:

| Chữ ký controller | Nguồn và bước giải đối số |
| --- | --- |
| `@PathVariable long id` | Lấy biến path rồi chuyển String → long |
| `@RequestParam int page` | Lấy query/form parameter, convert sang int |
| `@RequestHeader("X-Trace-ID") String traceId` | Đọc HTTP header |
| `@RequestBody OrderRequest input` | Chọn message converter theo content type và target type; parse body thành object |
| `@Valid @RequestBody OrderRequest input` | Sau deserialization, chạy validation khi cấu hình provider tương ứng |
| `Model model` | Cấp model phục vụ view hoặc xử lý request |
| `HttpServletRequest request` | Truy cập native Servlet request |

**Quá trình chọn resolver diễn ra cho từng tham số.** Một method có thể đồng thời nhận `@PathVariable`, `@RequestParam`, `@RequestBody` và những dependency context khác.

Với kiểu parameter đơn giản **không có annotation**, MVC có thể dùng fallback xem như request parameter; kiểu phức tạp có thể xem như model attribute. Vì mục tiêu dễ bảo trì, nên dùng annotation tường minh khi nguồn dữ liệu có ý nghĩa.

### 5.2 Binding, conversion và validation nằm ở đâu?

Giả sử request:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"item":"Sổ tay","quantity":2}
~~~

Controller khai báo:

~~~java
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest input) { ... }
~~~

Trình tự khái quát:

1. Resolver nhận ra tham số có `@RequestBody`.
2. Dựa vào `Content-Type: application/json` và target Java type, một `HttpMessageConverter` phù hợp (thường Jackson JSON converter) chuyển bytes thành `CreateOrderRequest`.
3. Có `@Valid` và Bean Validation provider phù hợp thì dữ liệu được kiểm tra ràng buộc.
4. Nếu không có lỗi, method controller nhận object đã có dữ liệu.
5. Nếu deserialize/convert/validate lỗi, framework có thể phát exception trước khi body method chạy; pipeline exception resolver quyết định response.

**Không nhầm vai trò:** `HandlerAdapter` điều phối; argument resolver hiểu nguồn tham số; `HttpMessageConverter` đọc/ghi HTTP body; `WebDataBinder` và hệ thống convert/validate xử lý binding/validation theo từng trường hợp.

`@Valid` cần dependency/provider Jakarta Bean Validation trong project (với Spring Boot thường thêm `spring-boot-starter-validation`). Nếu quên, không được giả định ràng buộc `@NotBlank`/`@Min` đã có hiệu lực.

### 5.3 Return value được diễn giải như thế nào?

| Controller trả về | Xử lý thường gặp |
| --- | --- |
| `OrderResponse` bên trong `@RestController` | Serialize object thành response body (thường JSON) |
| `ResponseEntity<OrderResponse>` | Ghi status/header/body theo response entity |
| `String` từ method của `@Controller` không có `@ResponseBody` | Thường là logical view name |
| `String` từ `@RestController` | Text response body, không phải view name |
| `ModelAndView` | Model và view cho bước rendering |
| `void` / một số giá trị rỗng | Tùy annotation, response state và contract method |
| `Callable<T>`, `DeferredResult<T>` | Tích hợp async Servlet, có dispatch xử lý kết quả ở thời điểm sau |

Các method return-value handler chọn cách diễn giải **theo annotation và type**, vì vậy chỉ xem kiểu Java `String` chưa đủ để suy ra server trả tên view hay chuỗi raw body.

Một số class giúp tìm hiểu internals: `HandlerMethodReturnValueHandler`, `RequestResponseBodyMethodProcessor` và `HttpEntityMethodProcessor`.

## 6. Ví dụ chạy được: nhiều chữ ký method và custom argument resolver

Ví dụ độc lập dưới đây sử dụng **Java 17**, **Spring Boot 3.3.5** (Spring Framework 6.1.x), web stack **Spring MVC**, Jackson và Bean Validation.

Các endpoint:

- `GET /api/orders/{id}?verbose=true`: `@PathVariable`, `@RequestParam` và một tham số tùy biến `@CurrentRequestId` lấy từ header.
- `POST /api/orders`: `@Valid @RequestBody` tạo object, trả `ResponseEntity` với status `201`, header `Location` và JSON body.
- Tham số custom minh họa điểm mở rộng tự nhiên của `RequestMappingHandlerAdapter`: **`HandlerMethodArgumentResolver`**.

Bài demo giữ dữ liệu cố định, không có database, để quan sát riêng cơ chế MVC.

### 6.1 Gradle configuration

Tạo một project Spring Boot riêng, ví dụ `handler-adapter-demo`.

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'handler-adapter-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Cần JDK 17+ và Gradle tương thích với Spring Boot plugin. Nếu dự án có Gradle Wrapper, dùng wrapper để chạy.

### 6.2 Java source hoàn chỉnh

Tạo tệp `src/main/java/example/web/HandlerAdapterDemoApplication.java`:

~~~java
package example.web;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class HandlerAdapterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HandlerAdapterDemoApplication.class, args);
    }

    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface CurrentRequestId {
    }

    public record OrderInfo(long id, String requestId, boolean verbose) {
    }

    public record CreateOrderRequest(
            @NotBlank String item,
            @Min(1) int quantity) {
    }

    public record CreatedOrder(long id, String item, int quantity) {
    }

    @RestController
    @RequestMapping("/api/orders")
    public static class OrderController {

        @GetMapping("/{id}")
        public OrderInfo get(
                @PathVariable long id,
                @RequestParam(defaultValue = "false") boolean verbose,
                @CurrentRequestId String requestId) {

            return new OrderInfo(id, requestId, verbose);
        }

        @PostMapping
        public ResponseEntity<CreatedOrder> create(
                @Valid @RequestBody CreateOrderRequest input) {

            CreatedOrder created = new CreatedOrder(
                    101L, input.item(), input.quantity());

            return ResponseEntity
                    .created(URI.create("/api/orders/101"))
                    .body(created);
        }
    }

    @Configuration
    public static class MvcConfiguration implements WebMvcConfigurer {

        @Override
        public void addArgumentResolvers(
                List<HandlerMethodArgumentResolver> resolvers) {
            resolvers.add(new CurrentRequestIdResolver());
        }
    }

    public static class CurrentRequestIdResolver
            implements HandlerMethodArgumentResolver {

        @Override
        public boolean supportsParameter(MethodParameter parameter) {
            return parameter.hasParameterAnnotation(CurrentRequestId.class)
                    && parameter.getParameterType() == String.class;
        }

        @Override
        public Object resolveArgument(
                MethodParameter parameter,
                ModelAndViewContainer mavContainer,
                NativeWebRequest webRequest,
                WebDataBinderFactory binderFactory) {

            String id = webRequest.getHeader("X-Request-ID");
            if (id == null || id.isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Missing X-Request-ID");
            }
            return id;
        }
    }
}
~~~

**Điểm đáng quan sát:** controller không có code tự parse header trong method `get`. `RequestMappingHandlerAdapter` sử dụng danh sách argument resolver, trong đó có resolver ta đăng ký thông qua `WebMvcConfigurer#addArgumentResolvers`. Khi thấy `@CurrentRequestId String`, resolver đọc header rồi cung cấp tham số thứ ba.

Custom resolver này hoạt động **trong Spring MVC annotated controller**. Nó không phải một Servlet filter, không thay đổi URL mapping và không bắt buộc viết một `HandlerAdapter` mới.

### 6.3 Chạy ứng dụng

Trong thư mục project, với Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có wrapper thì cần Gradle tương thích đã cài; lệnh tương đương là `gradle bootRun`. Mặc định server lắng nghe `http://localhost:8080` nếu cổng chưa được ứng dụng khác sử dụng.

**Thử GET:**

~~~bash
curl -i -H "X-Request-ID: abc-123" \
  "http://localhost:8080/api/orders/42?verbose=true"
~~~

Trên Windows PowerShell, có thể viết một dòng với `curl.exe` để tránh alias và dấu nối dòng shell:

~~~powershell
curl.exe -i -H "X-Request-ID: abc-123" "http://localhost:8080/api/orders/42?verbose=true"
~~~

Kết quả body kỳ vọng khi request thành công:

~~~json
{"id":42,"requestId":"abc-123","verbose":true}
~~~

Status là `200 OK` và body là JSON. Các bước mà adapter phối hợp:

1. `@PathVariable` tạo `long id = 42L`.
2. `@RequestParam` tạo `boolean verbose = true`.
3. Custom `CurrentRequestIdResolver` tạo `String requestId = "abc-123"`.
4. Method `OrderController#get` được gọi bằng ba argument này.
5. Vì `@RestController`, return value handler ghi JSON của `OrderInfo`.

**Thử thiếu header:**

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Custom resolver ném `ResponseStatusException(HttpStatus.BAD_REQUEST, ...)`, nên status kỳ vọng là `400 Bad Request`. Body lỗi cụ thể phụ thuộc cách Spring Boot cấu hình error response; không cần đoán một JSON cố định.

**Thử POST hợp lệ:**

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"item":"Notebook","quantity":2}'
~~~

Status kỳ vọng: `201 Created`, header `Location: /api/orders/101`, body:

~~~json
{"id":101,"item":"Notebook","quantity":2}
~~~

Đây là dữ liệu demo hard-code; không có thao tác ghi database thật. `@RequestBody` được deserialize rồi `@Valid` kiểm tra record theo annotation.

**Thử POST không hợp lệ:**

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"item":"","quantity":0}'
~~~

`@NotBlank` và `@Min(1)` đều bị vi phạm. Khi starter validation được cấu hình như trên, request phải bị từ chối với status `400 Bad Request` trước khi vào body method `create`. Không suy đoán thứ tự hay format các thông điệp lỗi: chúng có thể thay đổi theo cấu hình error handling.

### 6.4 Vì sao không tự gọi controller bằng Java reflection?

Framework sử dụng reflection/method invocation nội bộ nhưng còn thực hiện nhiều thứ trước/sau lời gọi, như tạo argument, type conversion, validation, async state, ghi status/header/body và exception routing. Nếu tự gọi:

~~~java
// Minh họa ý tưởng, KHÔNG phải cách xử lý HTTP trong ứng dụng:
controller.get(42L, true, "abc-123");
~~~

thì chỉ chạy trực tiếp method Java với các đối số có sẵn; nó **không** tự đọc `@PathVariable`, `@RequestParam` hay header từ `HttpServletRequest`. Đó chính là giá trị của pipeline mà `RequestMappingHandlerAdapter` điều phối.

## 7. Lỗi thường gặp khi chữ ký controller không được giải được

Không phải mọi kiểu parameter đều được giải như lập trình viên dự đoán. Bảng dưới đây giúp phân biệt lỗi mapping, argument resolution, body conversion và validation.

| Triệu chứng | Nguyên nhân có thể | Nơi điều tra đầu tiên |
| --- | --- | --- |
| `404 Not Found` | Request không khớp handler mapping; hoặc static resource xử lý khác | URI, HTTP method, path pattern, mapping registration |
| `405 Method Not Allowed` | Path có mapping nhưng HTTP method không phù hợp | `@GetMapping`/`@PostMapping` và client method |
| `400` do không đọc được query/path value | Thiếu tham số bắt buộc hoặc type conversion thất bại | `@RequestParam`, `@PathVariable` và converter |
| `400` do JSON sai/thiếu body | Jackson parse/conversion lỗi hoặc missing required body | `@RequestBody` và `HttpMessageConverter` |
| `400` do validation | Constraint trên bean/request không đạt | `@Valid`, Bean Validation provider, error handling |
| `415 Unsupported Media Type` | Body có `Content-Type` không được endpoint/converter hỗ trợ | `consumes`, content type, converter |
| `406 Not Acceptable` | Không tạo được response phù hợp `Accept` | `produces`, converter, response negotiation |
| Trả về tên view thay vì text | Method thuộc `@Controller` và không có `@ResponseBody` | Return-value handler/view resolver |
| Không thấy custom resolver chạy | Annotation/type không được `supportsParameter` nhận; sai web stack hoặc cấu hình | `WebMvcConfigurer` và resolver registration |
| Exception trước khi vào method | Adapter không resolve được một argument | Log exception, argument resolver, binder/converter |

**Cần phân biệt:** `HandlerMapping` chọn phương thức trước; lỗi trong bước **lựa chọn handler** khác với lỗi khi **adapter đang chuẩn bị argument hoặc xử lý return value**. Status cuối cùng còn có thể bị ảnh hưởng bởi `HandlerExceptionResolver` hay `@ControllerAdvice`.

### Trường hợp BindingResult

Trong MVC, nếu muốn thu thập lỗi binding/validation ở controller thay vì để exception đi theo đường xử lý mặc định, `BindingResult` / `Errors` phải đặt **ngay sau** argument liên quan:

~~~java
@PostMapping("/forms")
String submit(@Valid @ModelAttribute OrderForm form,
              BindingResult result) {
    if (result.hasErrors()) {
        return "order-form";
    }
    return "order-success";
}
~~~

Đoạn này chỉ minh họa cấu trúc method; `OrderForm` và hai view template chưa được định nghĩa nên không phải chương trình chạy độc lập.

## 8. Tùy biến đúng điểm mở rộng

Khi muốn hỗ trợ chữ ký method mới, hãy chọn điểm mở rộng phù hợp:

- **Thêm loại argument riêng:** triển khai `HandlerMethodArgumentResolver` rồi đăng ký bằng `WebMvcConfigurer.addArgumentResolvers(...)`. Ví dụ `@CurrentTenant`, `@CurrentRequestId`, giá trị đọc từ security context đã xác minh.
- **Thêm chuyển đổi giữa kiểu dữ liệu:** dùng `Converter`, `Formatter` hoặc `ConversionService` khi muốn biến chuỗi/tham số thành kiểu ứng dụng.
- **Thêm quy tắc binding/validation:** sử dụng `@InitBinder`, Bean Validation và các cấu hình binder phù hợp.
- **Xử lý request/response body đặc biệt:** cấu hình hoặc bổ sung `HttpMessageConverter` khi media type và serialization yêu cầu.
- **Tùy biến lỗi controller:** `@ExceptionHandler`, `@RestControllerAdvice` hoặc exception resolver phù hợp.
- **Thêm logic trước/sau handler:** `HandlerInterceptor` nếu thuộc MVC, `Filter` nếu cần tác động ở Servlet layer.
- **Hỗ trợ một kiểu handler hoàn toàn khác:** mới cân nhắc tự viết `HandlerAdapter`/`HandlerMapping` riêng; đây là nhu cầu hạ tầng rất hiếm trong ứng dụng thông thường.

**Một ranh giới quan trọng:** thêm `HandlerMethodArgumentResolver` có thể chưa đủ nếu một built-in resolver được chọn trước cho đúng kiểu/annotation. Cần chọn annotation/kiểu riêng đủ đặc trưng và test thứ tự resolution. Không tùy tiện thay thế toàn bộ danh sách argument resolver/return-value handler vì có thể làm mất những hỗ trợ mặc định của framework.

## 9. Async return value có còn đi qua HandlerAdapter không?

**Có.** Spring MVC sử dụng Servlet async cho một số kiểu return value như `Callable<T>` hoặc `DeferredResult<T>`. Adapter xử lý kết quả ban đầu, tích hợp quản lý async; request có thể được dispatch lại khi dữ liệu sẵn sàng. Cần phân biệt:

- Method controller thực hiện trên thread nào và trả về sớm hay không.
- Async processing có giải phóng thread Servlet ban đầu trong lúc chờ hay không.
- Công việc bên trong `Callable` có thể vẫn blocking trên worker thread.
- Response chưa nhất thiết hoàn thành tại thời điểm method controller lần đầu trả về.

Ví dụ ký hiệu:

~~~java
@GetMapping("/slow")
Callable<String> slow() {
    return () -> service.loadResult();
}
~~~

Đây là đoạn minh họa phụ thuộc `service` chưa khai báo. Nó diễn đạt việc Spring MVC có thể xử lý async return type; không chứng minh `service.loadResult()` là non-blocking.

**Không nhầm với Spring WebFlux.** WebFlux sử dụng một mô hình reactive với pipeline các publisher; dù cũng có annotated controller, internal request handling của WebFlux không dùng chính Servlet MVC `RequestMappingHandlerAdapter` nói ở bài này. Tên khái niệm giống nhau không có nghĩa các class và execution model giống hệt.

## 10. Quan hệ với Interceptor, Filter và ExceptionResolver

Một request MVC có thể có nhiều điểm mở rộng, nhưng mỗi điểm ở vị trí khác nhau:

~~~text
Servlet Filter (bao ngoài)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping tìm handler + interceptor chain
    |
    +-- interceptor.preHandle(...)
    |
    +-- HandlerAdapter.handle(...)
    |      +-- argument resolution
    |      +-- controller invocation
    |      +-- return-value handling
    |
    +-- interceptor.postHandle(...) (nếu áp dụng)
    |
    +-- render View (nếu có)
    |
    +-- interceptor.afterCompletion(...) (khi vòng xử lý hoàn tất)
    |
    v
Filter chain hoàn tất
~~~

Nếu xảy ra exception, `HandlerExceptionResolver` có thể can thiệp và xử lý lỗi; với async flow, callbacks và các lần dispatch cũng khác luồng đồng bộ rút gọn ở trên. `postHandle` có thể không thay đổi được body JSON đã được ghi bởi response-body handler.

Một ví dụ ứng dụng: cần **request ID** trong controller thì ưu tiên `@RequestHeader` hoặc custom argument resolver (như phần 6); cần **bảo mật toàn hệ thống** nên dùng security filter chain tương ứng; cần **kiểm tra điều kiện của handler** có thể dùng interceptor; cần **lỗi API nhất quán** có thể dùng `@RestControllerAdvice`.

Không đưa logic xác thực phân quyền quan trọng vào custom argument resolver chỉ vì nó đọc header dễ dàng: header do client tự gửi không mặc nhiên đáng tin.

## 11. Debug HandlerAdapter bằng chứng cứ quan sát được

Khi có lỗi “mapping đã nhận nhưng method không chạy”, nên debug theo thứ tự:

1. **Xác nhận URL/method đã được mapping:** xem endpoint mappings và log/request details phù hợp. Nếu không có mapping, tập trung vào `HandlerMapping`, không phải adapter.
2. **Xác nhận handler kiểu gì:** với annotated controller, handler thường là `HandlerMethod`; adapter điển hình là `RequestMappingHandlerAdapter`.
3. **Xác nhận từng đối số:** so sánh `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` với URL, headers, content type và actual payload.
4. **Kiểm tra converter/validation:** type conversion, Jackson, ràng buộc Jakarta Bean Validation, thông báo lỗi sớm.
5. **Nếu method chạy nhưng response sai:** xem `@ResponseBody`/`@RestController`, `ResponseEntity`, `Accept`/`produces`, message converter, view resolver.
6. **Nếu ném exception:** theo luồng `HandlerExceptionResolver` hoặc `@ControllerAdvice`; status cuối cùng có thể không phải status phát sinh trực tiếp từ controller.
7. **Nếu async:** phân biệt lần request đầu, việc chạy task và lần dispatch hoàn thành.

Một số tên class hữu ích khi đọc stack trace Spring MVC 6.x:

~~~text
DispatcherServlet
RequestMappingHandlerMapping
RequestMappingHandlerAdapter
ServletInvocableHandlerMethod
InvocableHandlerMethod
HandlerMethodArgumentResolverComposite
HandlerMethodReturnValueHandlerComposite
RequestResponseBodyMethodProcessor
HttpEntityMethodProcessor
HandlerExceptionResolver
~~~

Không cần thuộc hết tên class. Quan trọng là biết lỗi xảy ra tại **mapping**, **argument conversion/binding**, **invocation**, **return-value conversion** hay **exception rendering**.

### Cách kiểm thử đúng cấp độ

- **`@WebMvcTest` + `MockMvc`:** kiểm tra mapping, các built-in argument resolver, validation và response code; import cấu hình custom resolver nếu cần.
- **Integration test với server:** kiểm tra Servlet filter/security, JSON converter, validation provider và wiring như production.
- **Unit test cho custom resolver:** `supportsParameter` với đúng/sai annotation và type, header có/thiếu.
- **Negative tests:** missing header, invalid number, malformed JSON, failed validation và unacceptable media type.

Nên xác nhận trạng thái HTTP và nội dung body theo hợp đồng ứng dụng; tránh test dựa vào chuỗi error mặc định có thể thay đổi theo bản Spring Boot và cấu hình.

## 12. Những ngộ nhận cần tránh

| Ngộ nhận | Điều đúng cần nhớ |
| --- | --- |
| “DispatcherServlet trực tiếp gọi tất cả loại controller” | DispatcherServlet chọn `HandlerAdapter`; adapter biết cách gọi kiểu handler tương ứng |
| “HandlerAdapter quyết định URL nào khớp” | `HandlerMapping` xác định handler |
| “Mỗi method signature cần một HandlerAdapter riêng” | `RequestMappingHandlerAdapter` dùng argument resolvers/return-value handlers |
| “`@PathVariable` tự đọc request trong controller” | Resolver chuẩn bị đối số trước khi controller được gọi |
| “`@RequestBody` chỉ là ép kiểu bằng reflection” | Nó thường dùng `HttpMessageConverter` để deserialize HTTP body, có thể kèm validation |
| “Controller trả `String` luôn là JSON/text” | Với `@Controller` thường là view name; với `@RestController` thường là response body |
| “Response JSON phải qua ViewResolver” | `@ResponseBody` được ghi trực tiếp qua return-value handler/converter |
| “HTTP 400 từ @Valid là logic trong method” | Validation có thể thất bại trước khi method được gọi |
| “Custom resolver luôn được gọi đầu tiên” | Resolver được chọn theo support và thứ tự cấu hình |
| “Muốn thêm parameter phải tự viết HandlerAdapter” | Thường chỉ cần `HandlerMethodArgumentResolver` |
| “WebFlux cũng chạy Servlet RequestMappingHandlerAdapter này” | WebFlux có stack và adapter implementation riêng |
| “Async nghĩa là mọi I/O không còn blocking” | Async Servlet và non-blocking I/O là hai khái niệm khác nhau |

## 13. Bài tập áp dụng

**Bài 1 — Phân loại trách nhiệm.** Với request `GET /api/products/9?currency=VND` và controller:

~~~java
@GetMapping("/api/products/{id}")
ProductView read(@PathVariable long id,
                 @RequestParam String currency) { ... }
~~~

Hãy chỉ ra thành phần nào (a) xác định method `read`, (b) cung cấp `id` và `currency`, (c) serialize `ProductView` khi method nằm trong `@RestController`.

**Gợi ý:** (a) `RequestMappingHandlerMapping`, (b) các argument resolver do `RequestMappingHandlerAdapter` phối hợp, (c) return-value handler + HTTP message converter.

**Bài 2 — Chẩn đoán status 400.** Client gửi `GET /api/products/abc` nhưng method yêu cầu `@PathVariable long id`. Vì sao body method có thể không chạy?

**Gợi ý:** path khớp nhưng argument resolver không convert được `"abc"` thành `long`, dẫn tới luồng exception handling trước invocation.

**Bài 3 — Mở rộng chữ ký method.** Bạn muốn mọi endpoint nhận `@CurrentTenant Tenant tenant`. Hãy liệt kê tối thiểu phần cần thiết để dùng trong MVC.

**Gợi ý:** annotation dành riêng cho parameter, resolver chọn bằng annotation/type, lấy tenant từ ngữ cảnh đã xác thực, đăng ký resolver với `WebMvcConfigurer` và test đủ trường hợp có/thiếu tenant. Không tin giá trị tenant được gửi trực tiếp từ một header chưa xác thực.

**Bài 4 — Chọn điểm mở rộng.** Muốn log request trước khi controller chạy, muốn trả cùng format JSON lỗi và muốn convert query `sort=NEWEST` sang enum. Nên dùng cùng một HandlerAdapter custom hay ba điểm mở rộng phù hợp?

**Gợi ý:** Filter/Interceptor cho log tùy phạm vi, `@RestControllerAdvice` hoặc exception resolver cho lỗi, converter/enum conversion cho query. Không cần tự viết adapter.

## 14. Checklist khi đọc một chữ ký controller MVC

- [ ] Mapping đã xác định đúng handler và HTTP method.
- [ ] Handler phù hợp `RequestMappingHandlerAdapter` hay adapter khác.
- [ ] Từng parameter có nguồn dữ liệu rõ ràng (path/query/header/body/model/context).
- [ ] Type conversion và binding đúng, không phụ thuộc vào fallback mơ hồ.
- [ ] `@Valid` có provider tương ứng và error handling đã được kiểm thử.
- [ ] `Content-Type` của request phù hợp input converter; `Accept` phù hợp response output.
- [ ] Return type và annotation được hiểu đúng: view, body, status/header hay async.
- [ ] Custom argument resolver được đăng ký và có test cho thứ tự hỗ trợ.
- [ ] Không đặt logic nghiệp vụ hoặc authentication tùy tiện trong adapter/resolver.
- [ ] Khi lỗi, phân biệt `HandlerMapping`, `HandlerAdapter`, converter, validator và exception resolver.

**Kết luận vận dụng:** `HandlerAdapter` cho phép `DispatcherServlet` gọi nhiều kiểu handler mà không phụ thuộc trực tiếp vào cách mỗi handler nhận dữ liệu hoặc trả kết quả. Trong Spring MVC hiện đại, `RequestMappingHandlerAdapter` là trung tâm thực thi annotated controller: nó phối hợp **argument resolvers → controller invocation → return-value handlers**. Hiểu ba bước này giúp thiết kế method signature rõ ràng, thêm tham số đúng điểm mở rộng và debug nhanh nguyên nhân controller chưa chạy hoặc response bị chuyển đổi sai.

### Tài liệu tham khảo chính thức

- [Spring Framework — DispatcherServlet Processing](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/sequence.html)
- [Spring Framework — Special Bean Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html)
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework — MVC Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework — MVC HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — MVC Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html)
- [Spring Framework — RequestMappingHandlerAdapter API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.html)
