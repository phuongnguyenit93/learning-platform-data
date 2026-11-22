# HandlerAdapter và gọi phương thức xử lý yêu cầu trong Spring MVC

## 1. Bức tranh tổng quan

Trong Spring MVC, **DispatcherServlet** là bộ điều phối trung tâm cho HTTP request, **HandlerMapping** tìm đối tượng xử lý phù hợp, còn **HandlerAdapter** biết cách *thực thi* đối tượng xử lý đó theo hợp đồng của framework. Với controller dùng @RequestMapping, @GetMapping, @PostMapping hoặc các annotation tương tự, adapter được dùng thông thường là **RequestMappingHandlerAdapter**.

Nhờ tầng adapter, DispatcherServlet không phải biết cụ thể một controller nhận bao nhiêu tham số, dùng @PathVariable hay @RequestBody, trả một DTO JSON hay ModelAndView. Nó chỉ cần tìm HandlerAdapter hỗ trợ đối tượng handler do HandlerMapping trả về, rồi yêu cầu adapter xử lý request.

Điểm cần phân biệt:

- **Mapping** là quyết định “request này thuộc handler nào?”.
- **Adapter** là quyết định “framework gọi handler đó như thế nào?”.
- **HandlerMethod** mô tả bean và method được chọn, chưa phải kết quả thực thi method.
- **Argument resolver** tạo giá trị các tham số Java từ request/context.
- **Return value handler** diễn giải giá trị Java trả về để tạo model/view, HTTP body, status/header hoặc cơ chế async.
- **HttpMessageConverter** đọc/ghi body, thường ở giữa JSON request/response và object Java; nó không thay thế HandlerAdapter.

Bài trình bày cơ chế của Spring MVC trên Servlet stack, ví dụ chạy được bằng **Java 17+, Spring Boot 3.3.x / Spring Framework 6.1.x**. Spring WebFlux có dispatcher và handler adapter theo kiến trúc reactive khác; không được trộn lẫn chỉ vì annotation controller giống nhau.

## 2. Vị trí HandlerAdapter trong luồng HTTP request

Sơ đồ đơn giản:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet Filter chain / Security filters"]
    B --> C["DispatcherServlet"]
    C --> D["HandlerMapping"]
    D --> E["HandlerExecutionChain: handler + interceptors"]
    E --> F["DispatcherServlet chọn HandlerAdapter"]
    F --> G["HandlerInterceptor.preHandle"]
    G --> H["HandlerAdapter.handle"]
    H --> I["Resolve arguments / bind / validate"]
    I --> J["Invoke controller method"]
    J --> K["Handle return value"]
    K --> L["Response body hoặc ModelAndView"]
    L --> M["DispatcherServlet hoàn tất response"]
    M --> N["HandlerInterceptor.afterCompletion"]
~~~

Đây là sơ đồ cho luồng **đồng bộ thành công**. Trong thực tế còn có xử lý exception, early response, cache/conditional request và asynchronous dispatch. Không phải mọi request đều chạy đủ các mũi tên trên.

Một chuỗi thao tác điển hình khi gọi GET /api/books/42:

1. Tomcat/Servlet container tiếp nhận request rồi đi qua Servlet Filters (ví dụ Spring Security nếu đã cấu hình).
2. DispatcherServlet hỏi các HandlerMapping theo thứ tự.
3. RequestMappingHandlerMapping tìm được HandlerMethod tương ứng một @GetMapping("/api/books/{id}").
4. DispatcherServlet nhận HandlerExecutionChain gồm handler và các interceptors.
5. DispatcherServlet tìm HandlerAdapter hỗ trợ HandlerMethod; thông thường là RequestMappingHandlerAdapter.
6. Các HandlerInterceptor.preHandle được gọi; nếu một interceptor trả false thì không tiếp tục đến controller theo luồng bình thường.
7. Adapter phân giải giá trị id thành long, tạo các đối số còn lại rồi gọi controller method.
8. Giá trị trả về được handler thích hợp xử lý: ResponseEntity, @ResponseBody, model/view hoặc async.
9. DispatcherServlet hoàn thiện request/response; với view-based MVC nó có thể render view. Interceptor lifecycle kết thúc theo trạng thái thực thi.

Một HTTP response có thể được ghi trực tiếp trong bước xử lý return value, ví dụ JSON body qua HttpMessageConverter, và lúc đó không còn bước template rendering truyền thống.

## 3. HandlerMapping, HandlerExecutionChain và HandlerAdapter khác nhau thế nào?

### 3.1 HandlerMapping

HandlerMapping trả lời “handler nào phù hợp với request này?”. Với annotation controller, **RequestMappingHandlerMapping** lập bản đồ mapping từ thông tin @RequestMapping và các annotation chuyên biệt như @GetMapping.

Nó xét điều kiện phù hợp như HTTP method, path, params, headers, consumes và produces. Nếu method không phù hợp, framework có thể trả 405; nếu Content-Type không phù hợp có thể là 415; nếu Accept không thỏa mãn produces có thể là 406. Không nên gộp mọi tình huống không match thành “không có HandlerAdapter”.

Ví dụ:

~~~java
@GetMapping(path = "/api/books/{id}", produces = "application/json")
public BookResponse find(@PathVariable long id) {
    return service.find(id);
}
~~~

Annotation nói cách **chọn method** cho request; việc phân giải id và gọi method là công việc ở giai đoạn adapter.

### 3.2 HandlerExecutionChain

HandlerMapping thường trả **HandlerExecutionChain**, chứa:

- Một handler thực tế (với annotation controller thường là HandlerMethod).
- Danh sách HandlerInterceptor áp dụng cho request.
- Thông tin phục vụ áp dụng preHandle, postHandle, afterCompletion.

Interceptor nằm cùng execution chain, nhưng **không phải HandlerAdapter**. Nó cung cấp hook trước/sau handler; DispatcherServlet điều phối các hook đó xung quanh adapter.

### 3.3 HandlerAdapter

HandlerAdapter là tầng thực thi một loại handler được framework hỗ trợ. Các phương thức cốt lõi có ý nghĩa:

~~~java
boolean supports(Object handler);

ModelAndView handle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception;
~~~

Đây là **trích đoạn API để minh họa**, không phải định nghĩa interface đầy đủ hoặc file Java có thể compile riêng. Hợp đồng HandlerAdapter cũng có API liên quan đến xử lý last-modified/conditional request ở phiên bản tương ứng.

- supports xác nhận adapter hiểu loại handler này.
- handle thực thi logic cần thiết và trả ModelAndView (có thể null nếu response đã được xử lý hoặc request chuyển sang async).
- DispatcherServlet duyệt danh sách adapter để tìm adapter đầu tiên hỗ trợ handler.

**DispatcherServlet không tự dùng Java reflection để gọi mọi controller method**. Phần hỗ trợ HandlerMethod và cơ chế gọi method được triển khai trong adapter chuyên trách.

## 4. Các HandlerAdapter thường gặp trong Spring MVC

| HandlerAdapter | Kiểu handler chính | Khi nào thường gặp |
| --- | --- | --- |
| RequestMappingHandlerAdapter | HandlerMethod từ annotation @RequestMapping | Hầu hết REST controller và MVC annotation controller hiện đại |
| HttpRequestHandlerAdapter | org.springframework.web.HttpRequestHandler | Một số handler hạ tầng, xử lý resource hoặc handler theo giao diện đặc thù |
| SimpleControllerHandlerAdapter | org.springframework.web.servlet.mvc.Controller | Controller-style interface truyền thống |
| Adapter do ứng dụng tự cung cấp | Kiểu handler do thư viện hoặc ứng dụng định nghĩa | Trường hợp tích hợp framework hoặc legacy đặc biệt |

Đừng nhầm **SimpleControllerHandlerAdapter** với @Controller annotation. SimpleControllerHandlerAdapter phục vụ interface org.springframework.web.servlet.mvc.Controller đời cũ; trong khi @Controller dùng @RequestMapping thông thường đi qua RequestMappingHandlerAdapter.

Đừng tự tạo HandlerAdapter để giải quyết nhu cầu thông thường như nhận một header mới, chuyển đổi JSON, phân trang, validate dữ liệu hay tùy chỉnh response. Spring MVC đã có **argument resolver**, **converter**, **return value handler**, **ControllerAdvice**, **WebMvcConfigurer** và các extension point hẹp hơn, phù hợp hơn.

## 5. RequestMappingHandlerAdapter: từ HandlerMethod đến lời gọi Java

Trong luồng annotation controller, thành phần quan trọng nhất là **org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter**.

Dưới góc nhìn khái niệm:

~~~text
DispatcherServlet
  -> HandlerMapping trả về HandlerMethod
  -> RequestMappingHandlerAdapter.handle(...)
     -> chuẩn bị WebDataBinderFactory và ModelFactory
     -> tạo ServletInvocableHandlerMethod
     -> resolve các đối số của method
     -> bind/convert/validate dữ liệu đầu vào khi cần
     -> invoke controller Java method
     -> xử lý giá trị trả về
     -> ModelAndView hoặc response đã được ghi/async
  -> DispatcherServlet hoàn tất request
~~~

Ở mức implementation trong Spring Framework 6.1, RequestMappingHandlerAdapter mở rộng AbstractHandlerMethodAdapter và sử dụng **ServletInvocableHandlerMethod** cho việc gọi phương thức xử lý request. Nó được tích hợp với HandlerMethodArgumentResolverComposite và HandlerMethodReturnValueHandlerComposite.

Cần tránh hiểu lầm rằng adapter chỉ gọi handlerMethod.invoke(...) với một mảng tham số có sẵn. Trước khi gọi, Spring MVC phải biết tham số nào lấy từ URL, query string, HTTP header, body, model, session, Servlet request/response và các context khác; sau lời gọi, nó phải biết giá trị trả về sẽ được biểu diễn như thế nào.

## 6. HandlerMethod là gì?

HandlerMethod là mô tả liên kết giữa:

- **Bean/controller** được Spring quản lý.
- **Method** Java sẽ được gọi.
- **Method parameters**, annotations, return type và metadata hỗ trợ xử lý request.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    public BookDto get(@PathVariable long id,
                       @RequestParam(defaultValue = "false") boolean upper) {
        return service.get(id, upper);
    }
}
~~~

Giả sử request GET /api/books/42?upper=true, HandlerMapping có thể chọn HandlerMethod đại diện cho BookController.get(long, boolean). Ở thời điểm đó, method chưa nhất thiết được thực thi. Adapter cần tạo đối số 42 và true, gọi method thực tế và tiếp tục xử lý BookDto trả về.

Spring thường quản lý controller dưới dạng singleton bean. Mỗi HTTP request có dữ liệu argument riêng; vì vậy không nên lưu path variable, request body hoặc request state thay đổi theo từng request vào field mutable của controller singleton.

## 7. Phân giải tham số: HandlerMethodArgumentResolver

### 7.1 Quy tắc chung

Spring MVC sử dụng các **HandlerMethodArgumentResolver** để trả lời:

> “Với một tham số Java cụ thể, framework có biết tạo giá trị từ request/context hiện tại hay không?”

Mỗi resolver có hai thao tác khái niệm:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

Đoạn trên mô tả chữ ký cốt lõi của HandlerMethodArgumentResolver, không phải file Java độc lập và bỏ qua các annotation nullable trong Javadoc.

RequestMappingHandlerAdapter phối hợp nhiều resolver và chọn resolver phù hợp với tham số. Nếu không có resolver nào hỗ trợ, request có thể thất bại trong lúc chuẩn bị lời gọi method; một số kiểu không có annotation có thể được cơ chế binding mặc định xử lý, nên không thể suy luận đơn giản rằng mọi tham số không gắn annotation đều bị lỗi.

### 7.2 Các tham số phổ biến

| Tham số trong controller | Nguồn dữ liệu | Cơ chế tiêu biểu |
| --- | --- | --- |
| @PathVariable long id | Biến trong route /books/{id} | Path variable resolver và type conversion |
| @RequestParam int page | Query/form parameter | Request-param resolver và type conversion |
| @RequestHeader String traceId | HTTP header | Header resolver |
| @CookieValue String token | HTTP cookie | Cookie-value resolver |
| @RequestBody CreateBookRequest request | HTTP body, thường JSON | RequestResponseBodyMethodProcessor + HttpMessageConverter |
| @ModelAttribute SearchForm form | Query/form fields và model binding | Model-attribute resolver + WebDataBinder |
| HttpServletRequest, HttpServletResponse | Servlet request/response | Servlet-specific argument resolver |
| Model, ModelMap | MVC model | Model argument resolver |
| Principal | Servlet/security principal khi có | Principal resolver |
| BindingResult | Kết quả bind/validation của đối tượng liền trước | BindingResult-related resolver |
| @RequestPart MultipartFile file | Multipart request | Request-part/multipart resolution |

Bảng chỉ nêu luồng điển hình; một số annotation có quy tắc bổ sung về required, default value, multipart và nội dung request.

### 7.3 Giá trị đến từ đâu?

Với:

~~~java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> get(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean upper,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId) {
    // ...
}
~~~

Request:

~~~http
GET /books/42?upper=true HTTP/1.1
Host: localhost:8080
X-Trace-Id: req-7
~~~

Đối số Java về mặt ý nghĩa là:

~~~text
id      = 42L
upper   = true
traceId = "req-7"
~~~

Việc chuyển chuỗi "42" thành long và "true" thành boolean thường sử dụng hệ thống conversion/binding tích hợp. Nếu id không thể chuyển thành long, controller method không được gọi thành công như yêu cầu hợp lệ; Spring MVC có thể tạo response 400 thông qua exception handling mặc định.

Đừng tự parse tất cả request parameter bằng request.getParameter trong controller nếu Spring MVC đã có resolver phù hợp.

## 8. @RequestBody, JSON và HttpMessageConverter

Khi tham số được khai báo @RequestBody, Spring MVC thường dùng **RequestResponseBodyMethodProcessor** và một **HttpMessageConverter** phù hợp để đọc body HTTP.

Luồng điển hình:

~~~text
POST /api/books
Content-Type: application/json
body: {"title":"Spring MVC"}

@RequestBody CreateBookRequest input
  -> chọn converter hỗ trợ media type và Java type
  -> đọc bytes / JSON thành Java object
  -> kiểm tra @Valid khi được yêu cầu
  -> truyền object làm tham số method
~~~

Với Spring Boot web starter mặc định và Jackson trong classpath, MappingJackson2HttpMessageConverter thường xử lý JSON.

**HttpMessageConverter không tự gọi controller method**: nó chỉ biến đổi giữa body HTTP và Java object. RequestMappingHandlerAdapter orchestrate argument resolution và invocation, còn message converter là một thành phần được resolver/return handler sử dụng.

Trường hợp cần phân biệt:

- **Content-Type** thể hiện định dạng body client gửi; khi không hỗ trợ có thể dẫn đến 415 Unsupported Media Type.
- Body không phải JSON hợp lệ hoặc không deserialize được có thể dẫn đến 400 Bad Request.
- Không có body khi @RequestBody(required = true) có thể dẫn đến 400.
- @Valid áp dụng Bean Validation cho đối tượng phù hợp; nếu không đạt và không xử lý BindingResult trực tiếp, thường sinh MethodArgumentNotValidException.
- Đừng đọc Servlet request input stream thủ công trước rồi mong @RequestBody đọc lại mà không có wrapper; body stream thông thường không thể đọc nhiều lần tùy ý.

**@RequestBody và @ModelAttribute không tương đương.** @RequestBody đọc payload thông qua message converter; @ModelAttribute dùng binding từ request parameters và model, thường hợp với form/query.

## 9. WebDataBinder, @InitBinder và Bean Validation

Sau khi argument resolver xác định nguồn dữ liệu, quá trình binding/conversion có thể dùng **WebDataBinder** và ConversionService. @InitBinder cho phép tùy chỉnh binding hoặc validator trong phạm vi controller/@ControllerAdvice khi có lý do rõ ràng.

Ví dụ:

~~~java
@InitBinder
public void configureBinder(WebDataBinder binder) {
    binder.setDisallowedFields("admin");
}
~~~

Đoạn trên chỉ minh họa hook binding và **chưa phải một class độc lập**. Đây không phải phương án bảo vệ duy nhất trước mass assignment; thiết kế request DTO chỉ gồm field cho phép chỉnh sửa thường rõ ràng và an toàn hơn. Không bind trực tiếp object domain chứa những field nhạy cảm rồi dựa hoàn toàn vào blacklist.

Bean Validation:

~~~java
public record CreateBookRequest(@NotBlank String title) {
}
~~~

Khi dùng:

~~~java
@PostMapping
public ResponseEntity<BookDto> create(
        @Valid @RequestBody CreateBookRequest input) {
    // ...
}
~~~

Spring MVC validate input theo Jakarta Validation nếu provider và các dependency cần thiết có mặt. Spring Boot 3.x thường cần **spring-boot-starter-validation** nếu ứng dụng muốn dùng @NotBlank và validation provider một cách đầy đủ.

Trường hợp validate không đạt:

- **MethodArgumentNotValidException** thường áp dụng khi validate @RequestBody hoặc @ModelAttribute mà lỗi không được xử lý qua BindingResult liền kề.
- **HandlerMethodValidationException** có thể liên quan đến method validation trong Spring Framework 6.1, ví dụ ràng buộc trực tiếp trên tham số/return value.
- **BindingResult** phải đặt đúng ngay sau tham số cần nhận kết quả binding/validation trong các trường hợp được hỗ trợ.

Không gộp mọi validation error thành một class exception cố định; phiên bản framework, annotation và kiểu constraint quyết định đường đi.

## 10. Gọi phương thức handler thực sự

Sau khi các tham số được phân giải, ServletInvocableHandlerMethod (trong hạ tầng MVC annotation controller) sẽ gọi method Java đã chọn. Quá trình đó có thể đi qua proxy và cơ chế Spring khác khi bean được quản lý qua AOP, tùy cấu hình.

Ví dụ:

~~~java
@GetMapping("/books/{id}")
public BookDto find(@PathVariable long id) {
    return catalog.find(id);
}
~~~

Ở đây:

1. DispatcherServlet đã xác định HandlerMethod.
2. RequestMappingHandlerAdapter chọn và phân giải tham số id.
3. Framework gọi BookController.find(42L) trên đối tượng controller được quản lý.
4. Controller có thể gọi service, repository hoặc client khác.
5. BookDto được trao lại cho return value handler.
6. Vì controller có @RestController, return value được xử lý theo ý nghĩa @ResponseBody và thường serialize thành JSON.

Nếu service throw exception, adapter không thể hoàn tất đường thành công bình thường; exception được chuyển đến chuỗi error handling của DispatcherServlet. Không nên mặc định rằng mọi exception đều được bắt bởi một try/catch nằm trong controller.

### Bean singleton và thread safety

Controller bean thường là singleton: nhiều request có thể đồng thời gọi cùng instance. Dữ liệu request nên nằm trong method parameter/local variable, hoặc trong scoped abstraction phù hợp. Một field như currentId dùng chung cho tất cả request có thể gây race condition.

Tùy stack và Servlet async, method invocation ban đầu thường diễn ra trên Servlet request thread; nếu controller trả async type, kết quả có thể hoàn thành trên thread khác. Đừng suy diễn một thread luôn xử lý từ đầu đến cuối cho mọi request.

### @Transactional và proxy

@Transactional không phải một bước do HandlerAdapter tự cài. Nếu method gọi tới một Spring service proxy có transaction interceptor, transaction boundary có thể chạy quanh method của service theo cơ chế AOP. Việc argument binding và JSON serialization không tự nằm trong cùng transaction chỉ vì controller gọi service. Hãy đặt transaction ở tầng ứng dụng cần thiết và tránh để logic blocking/transaction kéo dài qua thời gian chờ I/O.

## 11. Xử lý giá trị trả về: HandlerMethodReturnValueHandler

Sau khi method trả một giá trị, Spring MVC sử dụng **HandlerMethodReturnValueHandler** phù hợp để quyết định cách tạo HTTP response.

Các tình huống:

| Return type hoặc annotation | Cách diễn giải |
| --- | --- |
| @ResponseBody BookDto, hoặc BookDto trong @RestController | Serialize object vào HTTP body nhờ HttpMessageConverter |
| ResponseEntity<BookDto> | Áp dụng status/header/body theo ResponseEntity, thường dùng converter cho body |
| String từ @Controller không có @ResponseBody | Thường là tên view để ViewResolver xử lý |
| ModelAndView | Cung cấp model + view cho DispatcherServlet |
| void + đã ghi HttpServletResponse | Có thể được coi là response đã xử lý; phụ thuộc annotation/context |
| Callable<T>, DeferredResult<T> | Bắt đầu xử lý bất đồng bộ trên Servlet stack |
| CompletionStage<T>, reactive type được framework hỗ trợ | Có thể được thích nghi vào xử lý async của Spring MVC |
| @ResponseStatus | Đặt HTTP status theo cấu hình annotation khi áp dụng |

Cần phân biệt:

~~~java
@Controller
class PageController {

    @GetMapping("/home")
    public String home() {
        return "home"; // tên view, không nhất thiết là HTTP body "home"
    }
}
~~~

với:

~~~java
@RestController
class ApiController {

    @GetMapping("/home")
    public String home() {
        return "home"; // body HTTP "home"
    }
}
~~~

Hai snippet ở đây chỉ minh họa semantics, không phải hai file compile độc lập với imports đầy đủ. @RestController tương đương @Controller kết hợp @ResponseBody ở mức xử lý return value.

Đối với JSON, **RequestResponseBodyMethodProcessor** có thể xử lý cả @RequestBody parameter và @ResponseBody return value. Với ResponseEntity, **HttpEntityMethodProcessor** là một thành phần return-value/argument handling thường gặp.

Với REST API, response body thường đã được ghi bởi return-value handling; DispatcherServlet không tiếp tục render JSP/Thymeleaf. Với web MVC view-based, adapter có thể trả ModelAndView để DispatcherServlet chọn ViewResolver và render.

## 12. HTTP status, header và content negotiation

Ví dụ:

~~~java
return ResponseEntity
        .created(URI.create("/api/books/101"))
        .header("X-Source", "catalog")
        .body(book);
~~~

Ở mức ý nghĩa:

- Status là 201 Created.
- Header Location chứa URI /api/books/101.
- X-Source là custom response header.
- book được serialize theo converter và media type đã đàm phán.

RequestMappingHandlerAdapter không quyết định đường URL cho mọi request một mình. HandlerMapping xét điều kiện consumes/produces; return-value handling và message converters cũng tham gia xác định media type cho body. Nếu Accept: application/xml nhưng ứng dụng chỉ có converter JSON và không thể thỏa mãn, kết quả có thể là 406 Not Acceptable.

Đặt @ResponseStatus(HttpStatus.CREATED) cũng có thể mô tả status trong trường hợp phù hợp; ResponseEntity hữu ích khi muốn chủ động kiểm soát cả header và body.

## 13. Interceptor được gọi trước và sau adapter thế nào?

HandlerInterceptor cung cấp ba hook quen thuộc:

~~~java
boolean preHandle(HttpServletRequest request,
                  HttpServletResponse response, Object handler);

void postHandle(HttpServletRequest request,
                HttpServletResponse response, Object handler,
                ModelAndView modelAndView);

void afterCompletion(HttpServletRequest request,
                     HttpServletResponse response, Object handler,
                     Exception ex);
~~~

Đây là chữ ký khái niệm (bỏ bớt các throws/annotation), không phải file Java hoàn chỉnh.

- **preHandle**: sau khi tìm được handler, trước khi adapter thực thi controller. Trả false để dừng execution chain theo nhánh thông thường; interceptor phải đảm bảo response phù hợp nếu nó tự chặn.
- **postHandle**: sau khi adapter xử lý handler thành công, trước khi DispatcherServlet render view. ModelAndView có thể null, đặc biệt REST body response.
- **afterCompletion**: callback hoàn tất ở cuối xử lý đồng bộ đối với các interceptor đã preHandle thành công; được gọi ngay cả khi exception có liên quan trong quá trình dispatch theo điều kiện framework.

Nếu một interceptor preHandle trả false, không phải tất cả hook trên cùng interceptor đều sẽ chạy như luồng thành công. Nếu controller chuyển sang Servlet async, có **AsyncHandlerInterceptor.afterConcurrentHandlingStarted** thay cho các hook kết thúc đồng bộ tại lượt dispatch đầu; một dispatch tiếp theo có thể kích hoạt lại các hook ở những thời điểm khác.

**Lưu ý bảo mật:** HandlerInterceptor không thay thế Servlet Filter chain/Spring Security. Các request như static resources, preflight, exception dispatch hoặc đường đi khác có thể có phạm vi áp dụng khác; authentication/authorization nên dùng cơ chế bảo mật được thiết kế cho Servlet stack.

## 14. Xử lý exception từ adapter/controller

Một controller có thể throw exception khi service chạy, khi validate tham số, khi parse request body hoặc khi ghi response. DispatcherServlet điều phối các **HandlerExceptionResolver** đã đăng ký để chuyển exception thành response hoặc view phù hợp.

Các thành phần phổ biến:

- **ExceptionHandlerExceptionResolver**: hỗ trợ @ExceptionHandler trong controller và @ControllerAdvice/@RestControllerAdvice.
- **ResponseStatusExceptionResolver**: hỗ trợ các tín hiệu status từ annotation hoặc ResponseStatusException.
- **DefaultHandlerExceptionResolver**: xử lý những exception Spring MVC chuẩn bằng HTTP status tương ứng khi có thể.

Ví dụ:

~~~java
@RestControllerAdvice
class ErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", ex.getMessage()));
    }
}
~~~

Đoạn này được trình bày như phần của ứng dụng ví dụ bên dưới, nơi các class, import và dependency đầy đủ được cung cấp.

Những lỗi thường gặp:

| Lỗi | Giai đoạn thường gặp | Phản hồi có thể có |
| --- | --- | --- |
| Không tìm thấy route | HandlerMapping | 404 |
| HTTP method không được mapping hỗ trợ | Mapping conditions | 405 |
| Content-Type không được hỗ trợ | Mapping/message conversion | 415 |
| Accept không có representation phù hợp | Negotiation/return handling | 406 |
| @PathVariable long id nhưng nhận chuỗi không parse được | Argument conversion | 400 |
| JSON body malformed | HttpMessageConverter đọc request | 400 |
| @Valid @RequestBody vi phạm constraint | Argument validation | 400 |
| Controller chủ động throw BookNotFoundException | Handler invocation | Tùy @ExceptionHandler; trong ví dụ là 404 |
| Không có HandlerAdapter hỗ trợ loại handler | DispatcherServlet chọn adapter | Lỗi cấu hình framework/handler; không sửa bằng @RequestBody |

Đừng bắt mọi exception thành 200 OK để tránh “lỗi HTTP”. HTTP status phải phản ánh kết quả thật; log nội bộ không nên đưa stack trace hoặc thông tin nhạy cảm cho client.

## 15. Async handler và sự thay đổi của luồng DispatcherServlet

Spring MVC hỗ trợ xử lý bất đồng bộ trên nền Servlet. HandlerAdapter có thể khởi động xử lý async khi controller trả Callable, DeferredResult hoặc các kiểu được adapter hỗ trợ.

Ví dụ minh họa:

~~~java
@GetMapping("/slow")
public Callable<ResponseEntity<String>> slow() {
    return () -> ResponseEntity.ok("done");
}
~~~

Đây là method có thể đặt trong @RestController với imports tương ứng. Framework có thể bắt đầu Servlet async, giải phóng request thread ban đầu, thực thi Callable qua task executor rồi dispatch lại khi kết quả sẵn sàng. Method vẫn thuộc **Spring MVC/DispatcherServlet**, không biến thành WebFlux.

Những điểm cần nhớ:

1. Thread và timing của HandlerInterceptor có thể khác so với request đồng bộ.
2. Return-value handler và WebAsyncManager hợp tác trong orchestration.
3. Async timeout và exception resolver vẫn cần được thiết kế/test.
4. Thread pool cho Callable phải phù hợp với blocking work; async không tự biến blocking operation thành non-blocking I/O.
5. Không giả định postHandle và afterCompletion luôn chạy ngay tại lần dispatch đầu.
6. Với reactive return type như Mono/Flux được MVC hỗ trợ, Spring MVC có adapter để tích hợp async; Servlet stack vẫn là stack xử lý HTTP.

Phân biệt **async request handling** và **Spring WebFlux**: MVC async được dựng trên Servlet async processing; WebFlux sử dụng reactive HTTP abstraction và DispatcherHandler.

## 16. Ví dụ hoàn chỉnh có thể chạy bằng Spring Boot 3.3 và Java 17

Ta xây dựng API quản lý sách đơn giản để kiểm chứng đầy đủ các bước:

- GET /api/books/{id} nhận @PathVariable, @RequestParam, @RequestHeader.
- POST /api/books nhận @Valid @RequestBody JSON.
- Controller gọi service; service trả DTO hoặc throw custom exception.
- Return value là ResponseEntity có status/header/body.
- @RestControllerAdvice xử lý ngoại lệ.
- HandlerInterceptor bổ sung header để quan sát preHandle.
- Integration test dùng MockMvc để xác minh mapping/binding/response.

### 16.1 Cấu trúc thư mục

~~~text
mvc-handler-adapter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mvcdemo/
    │   ├── MvcDemoApplication.java
    │   ├── BookController.java
    │   ├── BookCatalog.java
    │   ├── ErrorAdvice.java
    │   └── WebFlowConfig.java
    └── test/java/com/example/mvcdemo/
        └── BookControllerTest.java
~~~

### 16.2 settings.gradle

~~~groovy
rootProject.name = 'mvc-handler-adapter-demo'
~~~

### 16.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

spring-boot-starter-web cung cấp Spring MVC và Tomcat embedded thông thường; spring-boot-starter-validation cung cấp Jakarta Bean Validation; spring-boot-starter-test cho JUnit 5, Spring Test và MockMvc. Nếu bạn dùng Gradle wrapper, thay gradle bằng ./gradlew trên Linux/macOS hoặc gradlew.bat trên Windows.

### 16.4 MvcDemoApplication.java

~~~java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

### 16.5 BookCatalog.java

~~~java
package com.example.mvcdemo;

import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {

    private final Map<Long, String> books =
            new ConcurrentHashMap<>(Map.of(42L, "Spring MVC"));
    private final AtomicLong nextId = new AtomicLong(100);

    public BookResponse find(long id, boolean upper, String traceId) {
        String name = books.get(id);
        if (name == null) {
            throw new BookNotFoundException(id);
        }
        String displayName = upper ? name.toUpperCase(Locale.ROOT) : name;
        return new BookResponse(id, displayName, traceId);
    }

    public BookResponse create(CreateBookRequest request) {
        long id = nextId.incrementAndGet();
        books.put(id, request.title());
        return new BookResponse(id, request.title(), null);
    }
}

class BookNotFoundException extends RuntimeException {

    BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}

record BookResponse(long id, String title, String traceId) {
}
~~~

ConcurrentHashMap và AtomicLong chỉ phục vụ ví dụ in-memory đồng thời; ứng dụng production cần database và chiến lược cấp ID thích hợp. Record BookResponse được Jackson trong Spring Boot 3.3 serialize thành các field tương ứng.

### 16.6 BookController.java

~~~java
package com.example.mvcdemo;

import java.net.URI;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookResponse> find(
            @PathVariable long id,
            @RequestParam(defaultValue = "false") boolean upper,
            @RequestHeader(name = "X-Trace-Id", required = false)
                    String traceId) {

        BookResponse book = catalog.find(id, upper, traceId);
        return ResponseEntity.ok()
                .header("X-Source", "catalog")
                .body(book);
    }

    @PostMapping
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        BookResponse created = catalog.create(request);
        return ResponseEntity
                .created(URI.create("/api/books/" + created.id()))
                .body(created);
    }
}

record CreateBookRequest(@NotBlank String title) {
}
~~~

Dòng @PathVariable long id yêu cầu Spring MVC phân giải id từ route; @RequestParam boolean upper đọc query parameter rồi chuyển kiểu; @RequestHeader lấy header tùy chọn. Với POST, @RequestBody + Jackson chuyển JSON thành record CreateBookRequest và @Valid chạy validator trước khi gọi method create.

### 16.7 ErrorAdvice.java

~~~java
package com.example.mvcdemo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<Map<String, String>> bookNotFound(
            BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidBody(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "title must not be blank"));
    }
}
~~~

Ví dụ chỉ có một constraint @NotBlank nên error message cố định giúp kiểm thử dễ. Trong hệ thống thật, nên xây error response có mã lỗi ổn định, field errors cần thiết và tránh lộ dữ liệu nhạy cảm.

### 16.8 WebFlowConfig.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFlowConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerTraceInterceptor())
                .addPathPatterns("/api/**");
    }

    static class HandlerTraceInterceptor implements HandlerInterceptor {

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {
            response.addHeader("X-Handler-Interceptor", "preHandle");
            return true;
        }
    }
}
~~~

Đây là demonstration của hook preHandle trong execution chain, không phải hệ thống tracing production. Header xuất hiện khi interceptor tham gia request có đường dẫn /api/** và response chưa commit; với controller thông thường, có thể dùng nó để thấy quá trình request đã đi qua bước interceptor trước lời gọi handler.

### 16.9 Build và chạy

Tại thư mục project:

~~~bash
gradle clean test bootRun
~~~

Trong terminal khác, gọi:

~~~bash
curl -i -H 'X-Trace-Id: req-7' \
  'http://localhost:8080/api/books/42?upper=true'
~~~

Kỳ vọng HTTP 200, có header X-Source: catalog, X-Handler-Interceptor: preHandle, và JSON body tương đương:

~~~json
{"id":42,"title":"SPRING MVC","traceId":"req-7"}
~~~

Thứ tự các JSON field và các header hạ tầng có thể khác, nên không so sánh byte-for-byte toàn bộ response.

Tạo book mới:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Web Layer"}'
~~~

Khi chạy một instance mới chưa có POST trước đó, response dự kiến HTTP 201, header Location: /api/books/101 và body tương đương:

~~~json
{"id":101,"title":"Web Layer","traceId":null}
~~~

Nếu ứng dụng đã có POST request trước đó, id có thể khác 101 do counter in-memory.

Dữ liệu không hợp lệ:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":""}'
~~~

Dự kiến HTTP 400 và body:

~~~json
{"error":"title must not be blank"}
~~~

Bởi vì @Valid từ chối input trước khi controller create chạy, @ExceptionHandler trong ErrorAdvice tạo response 400.

Book không tồn tại:

~~~bash
curl -i 'http://localhost:8080/api/books/9999'
~~~

Dự kiến HTTP 404 và body tương đương:

~~~json
{"error":"Book 9999 not found"}
~~~

Các kết quả trên là **kỳ vọng được suy ra từ mã ví dụ**, không phải log thực thi đã được chạy sẵn trong tài liệu.

### 16.10 BookControllerTest.java

~~~java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void resolvesArgumentsAndWritesResponse() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42L)
                .param("upper", "true")
                .header("X-Trace-Id", "test-1"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Source", "catalog"))
            .andExpect(header().string(
                    "X-Handler-Interceptor", "preHandle"))
            .andExpect(jsonPath("$.title").value("SPRING MVC"))
            .andExpect(jsonPath("$.traceId").value("test-1"));
    }

    @Test
    void validatesRequestBodyBeforeInvocation() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                    .value("title must not be blank"));
    }

    @Test
    void resolvesControllerException() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 9999L))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error")
                    .value("Book 9999 not found"));
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

MockMvc gọi Spring MVC dispatcher và handler pipeline thông qua mock Servlet request/response, **không cần khởi động một listening socket trên port 8080** trong cấu hình test này. Test giúp kiểm chứng mapping, argument resolution, validation, controller invocation, exception resolution và response processing. Nếu muốn test thực trên TCP, dùng @SpringBootTest(webEnvironment = RANDOM_PORT) cùng HTTP client/test phù hợp.

## 17. Extension point: khi cần thêm argument resolver tùy chỉnh

Một ứng dụng có thể muốn controller nhận một kiểu đặc thù, ví dụ ClientTag từ header X-Client-Tag:

~~~java
record ClientTag(String value) {
}
~~~

Có thể triển khai HandlerMethodArgumentResolver hỗ trợ đúng kiểu ClientTag rồi đăng ký qua WebMvcConfigurer#addArgumentResolvers.

Mẫu logic minh họa:

~~~java
@Override
public boolean supportsParameter(MethodParameter parameter) {
    return parameter.getParameterType().equals(ClientTag.class);
}

@Override
public Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer container,
        NativeWebRequest request,
        WebDataBinderFactory binderFactory) {
    String header = request.getHeader("X-Client-Tag");
    return new ClientTag(header == null ? "anonymous" : header);
}
~~~

Các method trên **chỉ là phần implementation minh họa**, không phải file Java tự biên dịch được: cần một class implements HandlerMethodArgumentResolver, imports và đăng ký bean. WebMvcConfigurer có hook:

~~~java
@Override
public void addArgumentResolvers(
        List<HandlerMethodArgumentResolver> resolvers) {
    resolvers.add(new ClientTagArgumentResolver());
}
~~~

Mẫu này cũng chỉ là một method minh họa trong WebMvcConfigurer, chưa phải class đầy đủ.

Lưu ý về thứ tự: WebMvcConfigurer#addArgumentResolvers bổ sung resolver bên cạnh các resolver chuẩn; resolver built-in dựa annotation và các nhóm khác có thể được ưu tiên theo thứ tự framework. Nếu muốn thay đổi hẳn danh sách hoặc override resolver chuẩn, RequestMappingHandlerAdapter có API setArgumentResolvers/setCustomArgumentResolvers, nhưng sửa toàn bộ danh sách có thể làm mất hỗ trợ @PathVariable, @RequestBody hoặc @RequestParam.

Chỉ xây custom resolver khi có nhiều endpoint lặp cùng cách lấy dữ liệu đặc thù. Với một tham số đơn giản lấy từ header, @RequestHeader thường rõ ràng và ít rủi ro hơn.

## 18. Extension point: tùy chỉnh return value

HandlerMethodReturnValueHandler có hai thao tác ý nghĩa:

~~~java
boolean supportsReturnType(MethodParameter returnType);

void handleReturnValue(
        Object returnValue,
        MethodParameter returnType,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest) throws Exception;
~~~

Đoạn trên minh họa API và bỏ qua annotation nullable. Tùy biến return handler hợp lý khi ứng dụng có một kiểu response wrapper đặc thù thực sự cần được framework hiểu như return type.

Nhưng trong đa số REST API:

- Dùng ResponseEntity để điều khiển status/header/body.
- Dùng @RestControllerAdvice để chuẩn hóa lỗi.
- Dùng ResponseBodyAdvice để tác động đến body trong các tình huống phù hợp.
- Dùng HttpMessageConverter hoặc Jackson configuration cho serialization.
- Dùng Filter/interceptor khi mục tiêu là request lifecycle, không phải return type.

RequestMappingHandlerAdapter có thể đăng ký custom return-value handlers, nhưng thứ tự với built-in handlers rất quan trọng. Không tự thay thế toàn bộ danh sách nếu chưa hiểu hệ quả tới HTTP entity, @ResponseBody, view name, async return và các kiểu xử lý đặc biệt.

## 19. Cách debug HandlerAdapter và method invocation

### 19.1 Bật log có chọn lọc

Trong application.properties của môi trường local/test:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter=TRACE
~~~

Mức TRACE có thể tạo nhiều log. Chỉ bật có kiểm soát, tránh bật log dữ liệu nhạy cảm trong production. Tùy phiên bản/config, log mapping và argument detail được Spring che bớt; đừng cố bật mọi log request body khi chưa có quy trình bảo vệ dữ liệu.

### 19.2 Kiểm tra endpoint đã mapping chưa

Khi GET /api/books/42 trả 404:

1. Xem controller có được component scan không.
2. Kiểm tra @RequestMapping ở class và @GetMapping ở method.
3. Đối chiếu request path, Servlet context path, path matching và HTTP method.
4. Kiểm tra interceptor/filter có chặn request trước controller không.
5. Đọc mapping log/Actuator mappings nếu Actuator đã được cài và endpoint được cho phép.
6. Chỉ khi đã tìm được handler mới điều tra adapter/argument resolution.

Không có HandlerAdapter hiếm khi là nguyên nhân 404 trong dự án dùng annotation controller bình thường.

### 19.3 Controller đã mapping nhưng method không chạy?

Kiểm tra:

- preHandle có trả false không?
- Argument resolver có throw exception trước khi gọi method không?
- @RequestBody JSON có đúng định dạng và Content-Type không?
- Binding/validation có từ chối dữ liệu không?
- Controller bean có được proxy như mong đợi không?
- ExceptionHandler có “nuốt” exception rồi trả status khác không?
- Có async dispatch khiến breakpoint/log xuất hiện trên thread khác không?

### 19.4 Breakpoint để hiểu thật pipeline

Với mã nguồn Spring Framework đúng phiên bản trong IDE, đặt breakpoint tại các điểm sau:

~~~text
DispatcherServlet.doDispatch
DispatcherServlet.getHandler
DispatcherServlet.getHandlerAdapter
RequestMappingHandlerAdapter.handleInternal
RequestMappingHandlerAdapter.invokeHandlerMethod
ServletInvocableHandlerMethod.invokeAndHandle
InvocableHandlerMethod.getMethodArgumentValues
HandlerMethodArgumentResolverComposite.resolveArgument
HandlerMethodReturnValueHandlerComposite.handleReturnValue
~~~

Không phải mọi method được gọi với cùng stack frame hoặc thứ tự cứng trên các phiên bản; đây là **địa điểm quan sát gợi ý**. Gắn debugger với phiên bản thư viện đang chạy và theo dõi HandlerMethod, argument values, return value và exception.

## 20. FAQ và những nhầm lẫn thường gặp

**Q1. HandlerMapping đã chọn controller thì HandlerAdapter còn làm gì?**

HandlerMapping chỉ chọn handler. HandlerAdapter chuyển handler thành lời gọi có tham số được bind/validate và diễn giải return value. Với annotation controller, RequestMappingHandlerAdapter thực hiện công việc orchestration này.

**Q2. HandlerAdapter có phải là HttpMessageConverter?**

Không. Converter đọc/ghi body, còn adapter tổ chức toàn bộ invocation pipeline và sử dụng converter khi resolver/return handler yêu cầu.

**Q3. @GetMapping tự gọi method Java đúng không?**

Không. @GetMapping góp metadata mapping, còn method được gọi thông qua hạ tầng HandlerMethod/RequestMappingHandlerAdapter sau khi request đã match và arguments được chuẩn bị.

**Q4. @RestController và @Controller có HandlerAdapter khác nhau?**

Không nhất thiết. Cả hai đều thường đi qua RequestMappingHandlerAdapter khi dùng @RequestMapping. Khác biệt quan trọng là semantics của @ResponseBody và return value handling.

**Q5. Vì sao một method đã match nhưng vẫn nhận 400?**

Argument conversion, JSON deserialization hoặc validation có thể lỗi trước khi method được gọi. Xem exception gốc và các tham số controller.

**Q6. Có thể dùng Mono/Flux trong Spring MVC?**

Một số reactive return type có thể được Spring MVC thích nghi vào cơ chế async Servlet. Điều đó không chuyển server từ DispatcherServlet sang WebFlux DispatcherHandler.

**Q7. Vì sao postHandle không sửa JSON response như mong muốn?**

Với @ResponseBody, body có thể đã được viết bởi return-value handler trước khi postHandle chạy. Dùng ResponseBodyAdvice hoặc thiết kế response layer thích hợp thay vì sửa bytes trong postHandle.

**Q8. Có nên thay RequestMappingHandlerAdapter bean mặc định để log mọi request?**

Thường không. Hãy dùng logging/tracing, Servlet Filter, HandlerInterceptor, ControllerAdvice hoặc observation framework đúng mục tiêu. Thay bean nền tảng có thể làm hỏng resolver/converter/async pipeline của Boot.

**Q9. Khi nào HandlerExceptionResolver hoạt động?**

Khi exception phát sinh trong chuỗi dispatch và được chuyển đến cơ chế error resolution tương ứng. Không phải mọi lỗi đều đi qua nó: một số lỗi bị chặn ở Servlet Filter, container, proxy hoặc xảy ra sau khi response đã commit.

**Q10. Nếu không có adapter hỗ trợ handler thì sao?**

DispatcherServlet không thể gọi loại handler đó qua pipeline MVC và sẽ báo lỗi cấu hình/dispatch tương ứng. Với HandlerMethod từ @RequestMapping trong ứng dụng Boot MVC bình thường, RequestMappingHandlerAdapter được framework tự đăng ký, nên tình huống này hiếm trừ khi tùy biến cấu hình làm mất thành phần chuẩn.

## 21. Checklist thực hành

1. Xác định ứng dụng thật sự chạy **Spring MVC/Servlet** chứ không phải WebFlux server.
2. Kiểm tra request đã qua Servlet Filter/Security đến DispatcherServlet.
3. Xác minh HandlerMapping chọn đúng HandlerMethod.
4. Xem HandlerExecutionChain có interceptor nào chặn bằng preHandle false.
5. Xác minh DispatcherServlet tìm được adapter hỗ trợ handler.
6. Theo dõi tham số được argument resolver tạo từ path/query/header/body.
7. Xem ConversionService, WebDataBinder và @Valid khi có conversion/validation error.
8. Đặt breakpoint trong controller/service để biết method thực sự được gọi.
9. Theo dõi HandlerMethodReturnValueHandler và converter để xác định status/header/body hoặc view.
10. Khi có exception, kiểm tra @ExceptionHandler và HandlerExceptionResolver thay vì chỉ xem HTTP code.
11. Đối với async, kiểm tra Servlet async lifecycle và thread/timeout.
12. Kiểm thử bằng MockMvc và HTTP client với cả happy path lẫn 400/404/415/406 khi cần.

## 22. Tóm tắt kiến thức

Spring MVC tách **định tuyến** và **thực thi** HTTP handler. DispatcherServlet nhận request; HandlerMapping chọn handler cùng interceptor chain; HandlerAdapter — thường là RequestMappingHandlerAdapter với annotation controller — chuẩn bị dữ liệu đầu vào, gọi controller method và xử lý giá trị trả về. Cơ chế argument resolver, data binding/validation, message converter, return value handler và exception resolver phối hợp để biến HTTP request thành một lời gọi Java an toàn, dễ mở rộng và có thể kiểm thử.

**Muốn debug việc “controller method có được gọi hay không”, hãy lần theo HandlerMapping → HandlerExecutionChain/preHandle → HandlerAdapter → argument resolver → method invocation → return-value/exception handling.** Đừng sửa một tầng khác khi chưa xác định lỗi xuất hiện tại tầng nào.

## 23. Tài liệu tham khảo

- Spring Framework 6.1 — DispatcherServlet Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/DispatcherServlet.html
- Spring Framework 6.1 — RequestMappingHandlerAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.html
- Spring Framework — MVC DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html
- Spring Framework — Handler Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — Handler Method Return Values: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
