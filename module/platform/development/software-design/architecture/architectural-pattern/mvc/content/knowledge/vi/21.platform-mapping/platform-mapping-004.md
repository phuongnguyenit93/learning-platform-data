# Ánh xạ Front Controller trong Spring MVC

## Mục tiêu

Front Controller là mẫu kiến trúc đặt một điểm tiếp nhận tập trung trước các handler của ứng dụng web. Điểm tiếp nhận này nhận request, áp dụng những bước xử lý dùng chung, tìm handler phù hợp, điều phối việc thực thi và chuyển kết quả thành response. Trong Spring MVC, vai trò đó được đảm nhiệm bởi DispatcherServlet.

Khi hiểu DispatcherServlet, người phát triển có thể theo dõi một request đi qua servlet container, filter, Spring Security, HandlerMapping, HandlerAdapter, Controller, bộ chuyển đổi dữ liệu, bộ xử lý exception và ViewResolver. Các thành phần này phối hợp để Controller tập trung vào hành vi của endpoint, còn những công việc chung được thực hiện tại đúng ranh giới.

Bài học này giải thích Front Controller pattern và cách Spring MVC ánh xạ request đến handler. Ví dụ sử dụng Spring Boot và Spring MVC trên Servlet stack.

Sau khi học, người học có thể:

- Giải thích mục đích của Front Controller và vai trò của DispatcherServlet.
- Phân biệt servlet container, Filter, DispatcherServlet và Controller.
- Mô tả vòng đời xử lý request trong Spring MVC.
- Giải thích vai trò của HandlerMapping và HandlerAdapter.
- Nhận diện cách Spring phân giải tham số, đọc request body và xử lý kiểu trả về.
- Phân biệt xử lý View với trả response body cho REST API.
- Giải thích Interceptor, HandlerExceptionResolver và ViewResolver.
- Hiểu luồng async request và cách cấu hình MVC mở rộng.
- Kiểm thử việc ánh xạ request bằng MockMvc và integration test.

## 1. Front Controller là gì?

Front Controller là một mẫu thiết kế trong đó các request đi vào ứng dụng qua một điểm điều phối trung tâm. Điểm này tiếp nhận request, áp dụng các bước xử lý chung và chuyển request đến thành phần chuyên trách xử lý nghiệp vụ hoặc endpoint.

Nếu không có điểm điều phối chung, mỗi handler có thể phải tự thực hiện những việc lặp lại như xác định loại request, kiểm tra một số quy tắc chung, chọn handler, xử lý lỗi và tạo response. Điều đó khiến chính sách dễ bị triển khai không nhất quán.

Front Controller tập trung các trách nhiệm giao tiếp chung như:

- Tiếp nhận request và xác định luồng xử lý.
- Kết nối request với handler phù hợp.
- Phối hợp các thành phần xử lý trước và sau handler.
- Chuyển exception thành response phù hợp.
- Hỗ trợ việc render View hoặc ghi response body.
- Tạo một nơi thống nhất để mở rộng và quan sát luồng HTTP.

Front Controller không nên chứa quy tắc nghiệp vụ cụ thể của từng chức năng. Nó điều phối request; Controller chuyên trách xử lý endpoint; application service và domain model thực hiện use case và quy tắc nghiệp vụ.

### Một luồng khái quát

    Browser / API Client
             |
             | HTTP request
             v
       Front Controller
             |
             | tìm handler và điều phối
             v
       Specific Controller
             |
             v
       Application Service
             |
             v
       Domain / Repository
             |
             v
       Result
             |
             v
       Front Controller
             |
             | render / write response
             v
       HTTP response

Trong Spring MVC, DispatcherServlet là Front Controller. Controller thường là một class có các method được ánh xạ bằng annotation như RequestMapping, GetMapping hoặc PostMapping.

## 2. Vì sao Spring MVC dùng DispatcherServlet?

Một ứng dụng web có nhiều endpoint nhưng vẫn cần một cách xử lý nhất quán. Ví dụ:

- GET /courses hiển thị danh sách khóa học.
- GET /courses/42 hiển thị chi tiết.
- POST /courses tạo khóa học.
- PATCH /courses/42 cập nhật.
- GET /api/courses/42 trả dữ liệu JSON.

Mỗi endpoint có handler riêng, nhưng chúng vẫn cần một số cơ chế dùng chung như routing, content negotiation, binding, validation, xử lý lỗi và hỗ trợ các loại response.

DispatcherServlet cung cấp một điểm điều phối cho các thành phần MVC. Nó không cần biết chi tiết nghiệp vụ của khóa học hoặc hồ sơ; nó biết cách tìm và gọi handler phù hợp thông qua các chiến lược của Spring MVC.

### Lợi ích

**Tập trung luồng request:** Các bước điều phối chung có một nơi thực hiện, giúp hành vi giữa các endpoint nhất quán.

**Tách routing khỏi nghiệp vụ:** DispatcherServlet tìm handler; Controller xử lý endpoint; service/domain xử lý nghiệp vụ.

**Mở rộng theo chiến lược:** Spring MVC cho phép thay hoặc bổ sung HandlerMapping, HandlerAdapter, argument resolver, message converter, exception resolver và ViewResolver.

**Hỗ trợ nhiều kiểu response:** Cùng cơ chế dispatch có thể phục vụ HTML, JSON, XML hoặc các kiểu representation khác tùy cấu hình.

**Dễ kiểm thử:** Có thể kiểm tra mapping và response qua MockMvc mà không cần mở cổng HTTP thật cho phần lớn MVC test.

### Chi phí và giới hạn

Điểm điều phối trung tâm làm tăng một lớp gián tiếp. Khi cấu hình sai, lỗi có thể nằm ở filter, mapping, adapter, converter, resolver hoặc Controller. Vì vậy, người phát triển cần hiểu thứ tự xử lý và biết cách quan sát từng bước.

DispatcherServlet cũng không tự làm ứng dụng an toàn hoặc có cấu trúc tốt. Authentication, authorization, validation, transaction và quy tắc nghiệp vụ vẫn cần được đặt ở các thành phần phù hợp.

## 3. Vị trí của DispatcherServlet trong Servlet stack

Spring MVC chạy trên Servlet API. Servlet container như Tomcat, Jetty hoặc Undertow tiếp nhận kết nối HTTP, tạo servlet request/response và gọi filter cùng servlet theo cấu hình.

Một request thường đi qua các lớp sau:

    HTTP Client
        |
        v
    Servlet Container
        |
        v
    Servlet Filter Chain
        |
        +---- Encoding / Logging / Correlation
        |
        +---- Spring Security Filter Chain
        |
        v
    DispatcherServlet
        |
        v
    Spring MVC Infrastructure
        |
        v
    Controller / View / Response Body
        |
        v
    Servlet Container
        |
        v
    HTTP Response

Servlet container chịu trách nhiệm vòng đời servlet và kết nối HTTP. Filter có thể xử lý request/response trước và sau servlet. DispatcherServlet là servlet của Spring MVC, điều phối request đến handler. Controller là handler cụ thể cho endpoint.

### Spring Security nằm ở đâu?

Trong ứng dụng Servlet thông thường, Spring Security được tích hợp thông qua DelegatingFilterProxy và FilterChainProxy. Vì vậy, security filter chain thường chạy trước DispatcherServlet.

Luồng khái quát:

1. Request đi vào servlet container.
2. Filter chain được gọi.
3. Spring Security xác thực request và áp dụng các quy tắc bảo vệ ở filter chain.
4. Nếu request được phép tiếp tục, DispatcherServlet nhận request.
5. Spring MVC tìm handler và gọi Controller.

Một request bị Spring Security từ chối có thể kết thúc trước khi Controller chạy. Vì vậy, không phải mọi response 401 hoặc 403 đều xuất phát từ Controller hoặc HandlerExceptionResolver của MVC.

### Filter khác Interceptor

| Thành phần | Vị trí | Phạm vi thường gặp |
|---|---|---|
| Servlet Filter | Trước/sau servlet trong filter chain | Request đến servlet hoặc nhóm URL được map |
| Spring HandlerInterceptor | Quanh quá trình thực thi handler của Spring MVC | Request đã được DispatcherServlet ánh xạ đến handler |
| Controller | Handler cụ thể | Một endpoint hoặc nhóm endpoint |
| Application Service | Application layer | Một use case |

Filter có thể áp dụng cho request không đi qua Spring MVC nếu URL được map tới filter. Interceptor hoạt động trong cơ chế handler của Spring MVC và thường có thông tin về handler đã được chọn.

Không dùng Interceptor thay cho Spring Security để bảo vệ tài nguyên. Security filter chain là ranh giới bảo mật phù hợp cho authentication và các quy tắc truy cập web; authorization theo tài nguyên vẫn cần được bảo vệ ở application/domain layer.

## 4. DispatcherServlet và các chiến lược của Spring MVC

DispatcherServlet điều phối request thông qua các thành phần chiến lược. Các thành phần này thường được đăng ký tự động từ Spring MVC configuration.

| Thành phần | Nhiệm vụ |
|---|---|
| HandlerMapping | Tìm handler phù hợp với request |
| HandlerAdapter | Gọi handler đã được tìm thấy |
| HandlerInterceptor | Thực hiện xử lý trước/sau handler |
| HandlerMethodArgumentResolver | Tạo giá trị cho tham số method của Controller |
| HttpMessageConverter | Đọc request body hoặc ghi response body |
| HandlerMethodReturnValueHandler | Xử lý giá trị trả về từ Controller |
| HandlerExceptionResolver | Chuyển exception thành kết quả xử lý |
| ViewResolver | Tìm View từ tên View logic |
| MultipartResolver | Hỗ trợ phân tích request multipart nếu được cấu hình |
| LocaleResolver | Xác định locale cho request |
| FlashMapManager | Quản lý flash attributes trong redirect |

Không phải mọi request đều sử dụng tất cả các thành phần. Ví dụ, một REST endpoint trả ResponseEntity thường dùng message converter để ghi JSON và không cần ViewResolver. Một request tải file tĩnh có thể được xử lý bởi ResourceHttpRequestHandler thay vì Controller nghiệp vụ.

## 5. Vòng đời request trong DispatcherServlet

Một request MVC thông thường có thể được mô tả theo trình tự:

    Servlet Container
          |
          v
    Filter Chain
          |
          v
    DispatcherServlet
          |
          v
    Kiểm tra multipart request
          |
          v
    HandlerMapping
          |
          v
    HandlerExecutionChain
          |
          v
    Interceptor preHandle
          |
          v
    HandlerAdapter
          |
          v
    Controller method
          |
          v
    Return value handling
          |
          +---- response body
          |
          +---- Model + View
          |
          v
    Interceptor postHandle
          |
          v
    Render View / hoàn tất response
          |
          v
    Interceptor afterCompletion
          |
          v
    HTTP Response

Đây là luồng khái quát. Khi exception xảy ra, DispatcherServlet chuyển sang cơ chế xử lý lỗi. Khi request chuyển sang xử lý bất đồng bộ, luồng servlet ban đầu có thể kết thúc trước khi response cuối cùng được hoàn tất.

### Các bước chính

1. Servlet container gọi DispatcherServlet sau filter chain.
2. DispatcherServlet chuẩn bị request context và kiểm tra request multipart nếu có.
3. DispatcherServlet yêu cầu HandlerMapping tìm handler.
4. HandlerMapping trả về handler cùng các interceptor liên quan, thường dưới dạng HandlerExecutionChain.
5. Interceptor có thể chạy preHandle.
6. HandlerAdapter gọi handler phù hợp.
7. Controller thực hiện xử lý và trả về một giá trị.
8. Return-value handler xử lý giá trị trả về; có thể ghi response body hoặc chuẩn bị ModelAndView.
9. Nếu cần View, ViewResolver tìm View và View render response.
10. Interceptor thực hiện các callback phù hợp; sau khi hoàn tất, response được trả về container.

### HandlerExecutionChain

HandlerExecutionChain kết hợp handler được chọn với danh sách interceptor áp dụng cho request đó. DispatcherServlet dùng chain này để chạy các callback trước, sau và khi hoàn tất.

Nếu một interceptor trả false trong preHandle, quá trình gọi handler dừng lại. Interceptor đó phải tự hoàn tất response hoặc chuyển hướng theo chính sách. Những interceptor đã chạy trước đó được xử lý callback hoàn tất phù hợp theo quy tắc của framework.

## 6. HandlerMapping: ánh xạ request đến handler

HandlerMapping chịu trách nhiệm xác định handler nào phù hợp với request hiện tại. Nó có thể dựa trên path, HTTP method, header, parameter, content type, request condition hoặc loại handler.

Trong ứng dụng annotation-based phổ biến, RequestMappingHandlerMapping phát hiện các method Controller được đánh dấu bằng RequestMapping và các biến thể như GetMapping, PostMapping, PutMapping, PatchMapping, DeleteMapping.

Ví dụ:

    @Controller
    @RequestMapping("/courses")
    public class CourseController {

        @GetMapping
        public String list(Model model) {
            model.addAttribute("courses", courseQuery.list());
            return "courses/list";
        }

        @GetMapping("/{courseId}")
        public String detail(
                @PathVariable UUID courseId,
                Model model) {
            model.addAttribute(
                    "course",
                    courseQuery.getDetails(courseId));
            return "courses/detail";
        }

        @PostMapping
        public String create(
                @Valid @ModelAttribute CourseForm form,
                BindingResult errors) {
            if (errors.hasErrors()) {
                return "courses/new";
            }

            courseCommand.create(form);
            return "redirect:/courses";
        }
    }

Các annotation tạo ra điều kiện mapping. Request GET /courses/42 có thể khớp method detail nếu UUID có thể được chuyển đổi. Request POST /courses có thể khớp method create.

### Nhiều điều kiện mapping

Có thể ràng buộc endpoint theo:

- Path: /courses/{courseId}.
- Method: GET, POST, PATCH hoặc DELETE.
- Params: yêu cầu hoặc loại trừ request parameter.
- Headers: yêu cầu header cụ thể.
- Consumes: loại media type request body được chấp nhận.
- Produces: loại media type response có thể tạo.

Ví dụ:

    @PostMapping(
            path = "/api/courses",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public CourseResponse createApi(
            @RequestBody @Valid CreateCourseRequest request) {
        return courseService.create(request);
    }

Nếu request không khớp điều kiện mapping, Spring có thể trả lỗi như 404 hoặc 405 tùy trường hợp và cấu hình. Nếu path khớp nhưng Content-Type không được hỗ trợ, kết quả có thể là 415 Unsupported Media Type. Nếu Accept không tương thích với representation được cung cấp, có thể xảy ra 406 Not Acceptable.

### Path variable và query parameter

Path variable thường xác định tài nguyên:

    GET /courses/42

Query parameter thường bổ sung điều kiện truy vấn:

    GET /courses?page=2&size=20&status=OPEN

Controller có thể khai báo:

    @GetMapping
    public String search(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String status,
            Model model) {
        model.addAttribute(
                "result",
                courseQuery.search(page, size, status));
        return "courses/list";
    }

Không dùng query parameter hoặc path variable làm bằng chứng xác thực hay quyền sở hữu. Giá trị do client gửi phải được validate và authorization theo dữ liệu đáng tin cậy.

### Mapping xung đột

Hai method có điều kiện mapping trùng nhau có thể làm ứng dụng không khởi động hoặc gây lỗi ánh xạ không rõ ràng. Hãy thiết kế path và method rõ ràng, tránh hai handler cùng khớp một request với điều kiện tương đương.

## 7. HandlerAdapter: gọi handler theo cách thống nhất

HandlerMapping tìm handler nhưng không trực tiếp quyết định cách gọi mọi loại handler. HandlerAdapter cung cấp cơ chế gọi handler theo loại mà adapter hỗ trợ.

Trong Spring MVC hiện đại, RequestMappingHandlerAdapter gọi các method Controller được ánh xạ bằng annotation. Nó phối hợp:

- Tạo đối số method từ request.
- Binding và validation.
- Gọi method Controller.
- Xử lý giá trị trả về.
- Chuyển lỗi phát sinh trong quá trình xử lý đến cơ chế thích hợp.

Việc tách HandlerMapping và HandlerAdapter giúp DispatcherServlet không cần biết chi tiết cách gọi từng loại handler.

### Ví dụ về vai trò adapter

HandlerMapping có thể trả về một HandlerMethod đại diện cho method trong CourseController. DispatcherServlet tìm HandlerAdapter hỗ trợ HandlerMethod đó, thường là RequestMappingHandlerAdapter. Adapter phân giải tham số, gọi method và xử lý kết quả.

Trong ứng dụng cũ hoặc cấu hình đặc biệt, có thể có loại handler và adapter khác. Phần lớn ứng dụng Spring Boot không cần tự tạo HandlerAdapter.

## 8. HandlerMethodArgumentResolver: tạo tham số cho Controller

Controller method có thể nhận nhiều loại tham số. Spring MVC dùng các argument resolver để tạo giá trị tương ứng từ request hoặc context.

Ví dụ:

    @GetMapping("/courses/{courseId}")
    public String detail(
            @PathVariable UUID courseId,
            @RequestParam(required = false) String tab,
            @RequestHeader("Accept-Language") Locale locale,
            Principal principal,
            Model model) {
        // xử lý request
        return "courses/detail";
    }

Một số nguồn tham số thường gặp:

| Annotation / kiểu | Nguồn dữ liệu |
|---|---|
| PathVariable | Biến trong URI template |
| RequestParam | Query parameter hoặc form parameter |
| RequestHeader | HTTP request header |
| CookieValue | Cookie |
| ModelAttribute | Request parameter được bind vào object |
| RequestBody | HTTP request body qua message converter |
| RequestPart | Một phần của multipart request |
| Principal | Danh tính đã xác thực nếu có |
| AuthenticationPrincipal | Principal được Spring Security cung cấp qua integration |
| Model | Model dùng để đưa dữ liệu sang View |
| HttpServletRequest | Servlet request hiện tại |

Spring cũng hỗ trợ custom HandlerMethodArgumentResolver khi ứng dụng có một kiểu tham số chuyên biệt. Chỉ nên tạo resolver khi nó biểu diễn một quy tắc phân giải dùng chung; không dùng resolver để che giấu việc gọi nghiệp vụ phức tạp.

### Binding và validation

Với ModelAttribute, Spring có thể bind request parameter vào object. Annotation Valid hoặc Validated kích hoạt validation theo cấu hình.

Ví dụ:

    public record CourseForm(
            @NotBlank
            @Size(max = 120)
            String title,

            @Min(1)
            @Max(100)
            int capacity) {
    }

    @PostMapping("/courses")
    public String create(
            @Valid @ModelAttribute("form") CourseForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "courses/new";
        }

        courseCommand.create(form);
        return "redirect:/courses";
    }

BindingResult phải đứng ngay sau tham số được validate để Controller nhận lỗi binding/validation theo cách thông thường. Không coi dữ liệu đã bind là đáng tin cậy; validation cấu trúc không thay thế authorization hoặc kiểm tra quy tắc domain.

### Custom argument resolver

Có thể tạo annotation riêng để lấy actor hoặc tenant từ một context đã được xác thực. Tuy nhiên, cần bảo đảm nguồn dữ liệu đó đáng tin cậy và không để client tự khai báo danh tính hoặc tenant rồi được resolver chấp nhận.

## 9. HttpMessageConverter: đọc và ghi HTTP body

HttpMessageConverter chuyển đổi giữa HTTP message body và object Java. Nó thường được dùng khi Controller nhận RequestBody hoặc trả ResponseBody.

Ví dụ JSON request:

    @PostMapping(
            path = "/api/courses",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CourseResponse> create(
            @RequestBody @Valid CreateCourseRequest request) {

        CourseResponse result = courseCommand.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

Một converter JSON như MappingJackson2HttpMessageConverter có thể đọc JSON thành CreateCourseRequest và ghi CourseResponse thành JSON. Converter cụ thể phụ thuộc dependency và cấu hình ứng dụng.

### Content-Type và Accept

- Content-Type mô tả định dạng body mà client gửi.
- Accept mô tả định dạng response mà client có thể nhận.

Nếu client gửi JSON nhưng endpoint không chấp nhận media type đó, có thể nhận 415. Nếu client chỉ chấp nhận một kiểu response mà server không thể tạo, có thể nhận 406.

### Converter khác ViewResolver

HttpMessageConverter ghi hoặc đọc message body. ViewResolver tìm View để render template. REST endpoint dùng ResponseBody thường không cần ViewResolver; Controller server-rendered trả tên template thường đi qua ViewResolver.

### Custom converter

Chỉ thêm converter khi ứng dụng cần một media type hoặc định dạng chưa được hỗ trợ phù hợp. Thứ tự converter và media type có thể ảnh hưởng converter nào được chọn. Cấu hình converter tùy tiện có thể khiến JSON hoặc String được xử lý khác mong đợi.

## 10. HandlerMethodReturnValueHandler: xử lý kết quả Controller

Sau khi Controller chạy xong, Spring cần xác định cách diễn giải giá trị trả về. HandlerMethodReturnValueHandler xử lý những kiểu kết quả khác nhau.

Một số kiểu phổ biến:

| Kiểu trả về | Ý nghĩa thường gặp |
|---|---|
| String trong Controller server-side | Tên View logic hoặc redirect |
| ModelAndView | View cùng Model |
| Model / Map | Dữ liệu đưa vào Model, tùy kiểu method |
| ResponseEntity | HTTP status, header và body |
| Object với ResponseBody | Ghi object thành response body |
| void | Có thể đã tự ghi response hoặc phụ thuộc cấu hình |
| Callable / DeferredResult | Xử lý request bất đồng bộ |
| Streaming response | Ghi dữ liệu theo luồng |

### Trả tên View

    @GetMapping("/courses")
    public String list(Model model) {
        model.addAttribute("courses", courseQuery.list());
        return "courses/list";
    }

Chuỗi courses/list là tên View logic. Spring chuyển nó qua ViewResolver để tìm template phù hợp.

### Trả ResponseEntity

    @GetMapping("/api/courses/{id}")
    public ResponseEntity<CourseResponse> detail(
            @PathVariable UUID id) {

        return ResponseEntity.ok(courseQuery.getDetails(id));
    }

ResponseEntity cho phép chỉ định status, header và body. Khi body là object và endpoint dùng cơ chế response body, message converter ghi dữ liệu ra HTTP response.

### Tránh nhầm tên View với nội dung response

Trong Controller server-side, String thường là tên View, không phải văn bản sẽ gửi trực tiếp cho browser. Nếu muốn trả chuỗi làm body, cần dùng ResponseBody hoặc ResponseEntity<String> theo hợp đồng endpoint.

## 11. ViewResolver: tìm template để render HTML

Khi Controller trả tên View logic, DispatcherServlet phối hợp ViewResolver để tìm View phù hợp. View chịu trách nhiệm render Model thành response, thường là HTML.

Ví dụ Controller trả:

    return "courses/detail";

Với Thymeleaf, Spring Boot có thể cấu hình template resolver để tìm file tương ứng trong thư mục template theo quy ước của ứng dụng. Tên và vị trí chính xác phụ thuộc cấu hình prefix/suffix.

### Model và View

Model chứa dữ liệu trình bày, chẳng hạn:

    model.addAttribute("course", courseDetails);
    model.addAttribute("canEdit", accessPolicy.canEdit(actor, course));

Template dùng những thuộc tính được cung cấp để render HTML. View không nên tự truy cập repository hoặc thực hiện thay đổi nghiệp vụ.

### Redirect và forward

Một Controller có thể trả redirect để browser gửi request mới:

    return "redirect:/courses";

Redirect thường hữu ích sau POST để áp dụng Post/Redirect/Get, giảm nguy cơ gửi lại form khi refresh.

Forward chuyển request nội bộ đến tài nguyên khác trong server mà không tạo một HTTP request mới từ browser. Hai cơ chế có semantics khác nhau về URL, request lifecycle và cách browser quan sát response.

### Không phải mọi Controller đều dùng ViewResolver

REST controller thường trả response body. Trong trường hợp đó, return-value handler và message converter xử lý body; ViewResolver không cần tham gia.

## 12. HandlerExceptionResolver: xử lý exception tập trung

Exception có thể xảy ra khi binding, gọi Controller, thực hiện use case hoặc render View. Spring MVC dùng HandlerExceptionResolver để thử chuyển exception thành một ModelAndView hoặc một response đã được xử lý.

Các resolver phổ biến trong cấu hình MVC gồm:

- ExceptionHandlerExceptionResolver: xử lý method có ExceptionHandler và ControllerAdvice.
- ResponseStatusExceptionResolver: xử lý một số exception có metadata status hoặc ResponseStatus.
- DefaultHandlerExceptionResolver: ánh xạ một số exception MVC chuẩn thành HTTP status.

Thứ tự và cấu hình cụ thể có thể thay đổi theo phiên bản hoặc custom configuration.

### Xử lý tập trung bằng ControllerAdvice

    @ControllerAdvice
    public class WebExceptionHandler {

        @ExceptionHandler(CourseNotFoundException.class)
        public String handleNotFound(
                CourseNotFoundException exception,
                Model model) {

            model.addAttribute(
                    "message",
                    "Không tìm thấy khóa học được yêu cầu.");
            return "errors/not-found";
        }
    }

Với API, có thể dùng RestControllerAdvice để trả một error DTO hoặc Problem Details. Thông báo công khai cần được kiểm soát; không trả stack trace, câu SQL hoặc exception message thô.

### Exception trong Filter và ngoài MVC

Exception phát sinh trước khi DispatcherServlet được gọi, ví dụ trong một security filter, không nhất thiết đi qua HandlerExceptionResolver. Tương tự, lỗi trong servlet container hoặc trong quá trình ghi response có thể nằm ngoài luồng exception handling thông thường của Controller.

Vì vậy, cần cấu hình error handling ở đúng lớp: filter/security entry point, MVC advice, servlet error handling hoặc tầng vận hành tùy nơi lỗi phát sinh.

## 13. HandlerInterceptor: xử lý quanh handler

HandlerInterceptor cho phép chạy logic trước và sau handler được chọn. Một interceptor thường có ba callback:

- preHandle: chạy trước khi handler được gọi; trả false để dừng luồng.
- postHandle: chạy sau khi handler hoàn tất nhưng trước khi View render trong luồng đồng bộ thông thường.
- afterCompletion: chạy sau khi request hoàn tất xử lý trong DispatcherServlet.

Ví dụ ghi nhận thời gian xử lý:

    public class RequestTimingInterceptor
            implements HandlerInterceptor {

        private static final String START =
                RequestTimingInterceptor.class.getName() + ".START";

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {

            request.setAttribute(START, System.nanoTime());
            return true;
        }

        @Override
        public void afterCompletion(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                Exception exception) {

            Long start = (Long) request.getAttribute(START);
            if (start != null) {
                long durationNanos = System.nanoTime() - start;
                // ghi metric hoặc log theo chính sách
            }
        }
    }

Đăng ký interceptor:

    @Configuration
    public class WebConfig implements WebMvcConfigurer {

        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(new RequestTimingInterceptor())
                    .addPathPatterns("/**")
                    .excludePathPatterns("/assets/**");
        }
    }

Trong ứng dụng thật, interceptor nên được quản lý như bean nếu nó cần dependency injection hoặc cấu hình phức tạp.

### Khi nào dùng Filter, khi nào dùng Interceptor?

Dùng Filter khi logic cần áp dụng ở ranh giới servlet, trước khi Spring MVC chọn handler, ví dụ xử lý encoding, correlation ID hoặc tích hợp security theo filter chain.

Dùng Interceptor khi logic cần biết handler nào được chọn hoặc cần gắn với các endpoint MVC, ví dụ metadata, timing theo handler hoặc một số chính sách giao diện.

Không đặt toàn bộ authentication/authorization vào interceptor. Interceptor có thể hữu ích cho một số kiểm tra bổ sung, nhưng không thay thế Spring Security filter chain và kiểm tra quyền ở application layer.

### Async interceptor callbacks

Với request async, postHandle và afterCompletion có thể không diễn ra theo thời điểm của thread ban đầu. AsyncHandlerInterceptor cung cấp callback afterConcurrentHandlingStarted để xử lý khi request chuyển sang chế độ concurrent. Khi container redispatch request để hoàn tất, interceptor có thể được gọi lại theo lifecycle của request.

Không giả định một request async chỉ chạy qua interceptor đúng một lần.

## 14. MultipartResolver và upload file

Khi endpoint nhận file upload qua multipart/form-data, Spring MVC cần phân tích multipart request. MultipartResolver hoặc cơ chế multipart của Servlet container hỗ trợ chuyển request thành các phần có thể truy cập trong Controller.

Ví dụ:

    @PostMapping(
            path = "/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public String upload(
            @RequestParam("file") MultipartFile file) {

        documentService.store(file);
        return "redirect:/documents";
    }

Upload file cần thêm kiểm tra:

- Giới hạn kích thước request và file.
- Xác thực loại nội dung bằng dữ liệu thực tế khi cần, không chỉ tin filename hoặc Content-Type do client gửi.
- Đổi tên file theo ID do server tạo.
- Lưu file ngoài thư mục thực thi web nếu phù hợp.
- Ngăn path traversal và thực thi nội dung tải lên.
- Kiểm tra quyền upload và quyền truy cập file.
- Xử lý file tạm và dọn dẹp khi request thất bại.

DispatcherServlet có thể phối hợp multipart resolver, nhưng chính sách bảo mật file vẫn thuộc ứng dụng và hạ tầng lưu trữ.

## 15. LocaleResolver, FlashMap và các thành phần hỗ trợ

Spring MVC có một số thành phần hỗ trợ trải nghiệm request–response.

### LocaleResolver

LocaleResolver xác định locale của request để ứng dụng chọn ngôn ngữ và định dạng phù hợp. Có thể dựa trên header, cookie, session hoặc cơ chế cấu hình khác.

Controller và View có thể dùng locale để hiển thị message phù hợp. Không nên coi locale do client gửi là dữ liệu có thể ảnh hưởng đến quyền hoặc nghiệp vụ.

### Flash attributes

Flash attribute là dữ liệu ngắn hạn được giữ qua một lần redirect. Ví dụ sau khi tạo khóa học thành công, Controller có thể đưa thông báo vào RedirectAttributes để hiển thị ở request kế tiếp.

    @PostMapping("/courses")
    public String create(
            @Valid @ModelAttribute CourseForm form,
            BindingResult errors,
            RedirectAttributes redirect) {

        if (errors.hasErrors()) {
            return "courses/new";
        }

        courseCommand.create(form);
        redirect.addFlashAttribute(
                "notice",
                "Đã tạo khóa học thành công.");

        return "redirect:/courses";
    }

FlashMapManager phối hợp lưu và lấy flash attributes qua redirect. Không dùng flash attributes làm nơi lưu dữ liệu nhạy cảm hoặc trạng thái nghiệp vụ dài hạn.

## 16. Xử lý request bất đồng bộ

Một số endpoint cần chờ tác vụ tốn thời gian hoặc gọi dịch vụ bên ngoài. Spring MVC hỗ trợ async request để servlet thread ban đầu có thể được giải phóng trong khi kết quả đang được xử lý.

Ví dụ với Callable:

    @GetMapping("/reports/monthly")
    public Callable<ReportViewModel> monthlyReport() {
        return reportService::generateMonthlyReport;
    }

Ví dụ với DeferredResult:

    @GetMapping("/reports/status")
    public DeferredResult<ResponseEntity<ReportStatus>> status() {
        DeferredResult<ResponseEntity<ReportStatus>> result =
                new DeferredResult<>(10_000L);

        reportService.loadStatusAsync()
                .whenComplete((value, error) -> {
                    if (error != null) {
                        result.setErrorResult(error);
                    } else {
                        result.setResult(ResponseEntity.ok(value));
                    }
                });

        return result;
    }

Các ví dụ cần executor và timeout policy phù hợp trong ứng dụng thực tế.

### Luồng async khái quát

1. DispatcherServlet nhận request và gọi Controller.
2. Controller trả một async return type hoặc bắt đầu async processing.
3. Servlet request chuyển sang trạng thái async; thread ban đầu được giải phóng.
4. Công việc hoàn tất trên executor hoặc callback.
5. Kết quả được đưa vào async context.
6. Servlet container redispatch request để hoàn tất response qua Spring MVC.

Không giữ transaction database mở trong suốt một tác vụ async dài nếu không cần thiết. Transaction thường nên được mở quanh từng đơn vị persistence cụ thể.

### ThreadLocal và SecurityContext

Request async có thể tiếp tục trên thread khác. Không giả định ThreadLocal, MDC hoặc context tự động được truyền qua mọi executor. Nếu công việc cần actor hoặc trace context, hãy truyền dữ liệu cần thiết rõ ràng hoặc dùng cơ chế context propagation đã được cấu hình.

## 17. Static resources và DefaultServletHttpRequestHandler

Không phải request nào cũng cần Controller nghiệp vụ. CSS, JavaScript, ảnh và font thường được phục vụ qua resource handler.

Spring MVC có thể ánh xạ static resources bằng ResourceHttpRequestHandler. Ví dụ cấu hình:

    @Configuration
    public class StaticResourceConfig implements WebMvcConfigurer {

        @Override
        public void addResourceHandlers(
                ResourceHandlerRegistry registry) {

            registry.addResourceHandler("/assets/**")
                    .addResourceLocations("classpath:/static/assets/");
        }
    }

Khi request khớp /assets/**, Spring MVC có thể chọn resource handler thay vì Controller thông thường. Tùy cấu hình, DefaultServletHttpRequestHandler có thể chuyển request không được MVC xử lý sang default servlet của container.

Cần tránh mapping Controller quá rộng làm che khuất static resource. Dùng URL namespace rõ như /assets/** cho tài nguyên tĩnh và kiểm thử cache/header cho tài nguyên được phục vụ.

## 18. Cấu hình Spring MVC trong Spring Boot

Spring Boot tự động cấu hình nhiều thành phần MVC khi có dependency phù hợp. Ứng dụng thường chỉ cần khai báo Controller, template engine và các cấu hình tùy chỉnh cần thiết.

Có thể mở rộng qua WebMvcConfigurer:

    @Configuration
    public class MvcConfig implements WebMvcConfigurer {

        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(new RequestTimingInterceptor())
                    .addPathPatterns("/**");
        }

        @Override
        public void addFormatters(FormatterRegistry registry) {
            registry.addFormatter(new CourseCodeFormatter());
        }
    }

Trong Spring Boot, triển khai WebMvcConfigurer thường cho phép bổ sung cấu hình trong khi giữ auto-configuration. Thêm @EnableWebMvc thay đổi cách Boot cấu hình MVC và thường làm ứng dụng chuyển sang cấu hình MVC do người phát triển kiểm soát nhiều hơn. Chỉ dùng khi chủ động muốn thay đổi hành vi auto-configuration; không thêm annotation này chỉ để đăng ký một interceptor hoặc formatter.

### Khi cần custom strategy

Có thể mở rộng:

- Interceptor.
- Formatter và Converter.
- HandlerMethodArgumentResolver.
- HttpMessageConverter.
- ResourceHandler.
- ViewResolver.
- CORS mapping.

Trước khi thay một strategy mặc định, hãy kiểm tra xem WebMvcConfigurer hoặc cấu hình chuyên biệt đã đủ chưa. Thay toàn bộ danh sách converter hoặc resolver có thể vô tình loại bỏ hỗ trợ mặc định của framework.

## 19. Kiểm thử Front Controller và request mapping

MockMvc cho phép gửi request mô phỏng qua Spring MVC infrastructure và kiểm tra status, header, model hoặc response body. Nó hữu ích cho Controller test mà không cần mở HTTP server thật.

### Kiểm tra mapping và response

    @WebMvcTest(CourseController.class)
    class CourseControllerTest {

        @Autowired
        MockMvc mockMvc;

        @MockBean
        CourseQuery courseQuery;

        @Test
        void returnsCourseDetails() throws Exception {
            when(courseQuery.getDetails(any()))
                    .thenReturn(new CourseDetails(
                            UUID.fromString(
                                    "00000000-0000-0000-0000-000000000042"),
                            "Spring MVC"));

            mockMvc.perform(get("/courses/00000000-0000-0000-0000-000000000042"))
                    .andExpect(status().isOk())
                    .andExpect(view().name("courses/detail"))
                    .andExpect(model().attributeExists("course"));
        }
    }

Đây là ví dụ server-rendered. Với REST endpoint, có thể kiểm tra content type và JSON body:

    mockMvc.perform(get("/api/courses/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON));

### Những trường hợp mapping nên kiểm tra

- Path đúng và HTTP method đúng.
- Path không tồn tại trả kết quả 404 phù hợp.
- Method không được hỗ trợ có kết quả 405 phù hợp.
- Request Content-Type không hợp lệ có kết quả 415.
- Accept không được hỗ trợ có kết quả 406 khi phù hợp.
- Path variable không chuyển đổi được được xử lý đúng.
- Request parameter thiếu hoặc sai kiểu có lỗi binding phù hợp.
- Validation lỗi trả lại form hoặc error response đúng.
- Controller trả View logic đúng hoặc body đúng.
- Interceptor áp dụng đúng pattern và loại trừ đúng URL.
- Exception được ánh xạ qua ControllerAdvice.
- Security filter từ chối request trước Controller khi cần.

### Slice test và full integration test

@WebMvcTest tập trung vào MVC slice, thường phù hợp để kiểm tra mapping, binding, converter, controller advice và một phần security tùy cấu hình test.

@SpringBootTest kết hợp @AutoConfigureMockMvc kiểm tra nhiều cấu hình ứng dụng hơn, gồm các bean và filter chain thực tế được load trong test context.

Nếu cần xác nhận servlet container, async dispatch, multipart limits hoặc cookie/session behavior ở mức container, hãy bổ sung integration test chạy với embedded server thay vì chỉ dựa vào MockMvc.

## 20. Quan sát request qua Front Controller

DispatcherServlet là điểm thuận lợi để quan sát request MVC, nhưng cần kết hợp log, metric và trace ở nhiều lớp.

Một request có thể được gắn các thông tin:

- Request ID hoặc trace ID.
- HTTP method và route template.
- Handler class/method đã được chọn.
- Application version và instance ID.
- Response status và thời gian xử lý.
- Exception category nếu có.
- Loại response: View render, JSON, file hoặc async.

Không log toàn bộ request body mặc định vì có thể chứa password, token hoặc dữ liệu cá nhân. Không đưa ID có cardinality cao vào metric label nếu làm tăng số chuỗi thời gian quá lớn.

### Phân biệt lỗi trước và sau DispatcherServlet

Nếu request bị từ chối trong security filter, Controller không chạy. Nếu lỗi mapping xảy ra trong DispatcherServlet, handler có thể chưa được gọi. Nếu lỗi trong application service, Controller đã bắt đầu thực thi. Nếu lỗi khi render template, use case có thể đã hoàn thành nhưng response HTML thất bại.

Log nên ghi đủ ngữ cảnh để phân biệt các giai đoạn này. Request ID giúp nối log từ filter, MVC và application service.

## 21. Các sai lầm thường gặp

### Nhầm DispatcherServlet với Controller

DispatcherServlet là Front Controller điều phối request. Controller là handler cụ thể cho một endpoint. Đưa logic nghiệp vụ vào DispatcherServlet hoặc cố tạo một Controller duy nhất xử lý mọi request sẽ làm mất ranh giới trách nhiệm.

### Nghĩ mọi request đều đi qua Controller annotation

Static resources có thể được phục vụ bởi resource handler. Security filter có thể từ chối request trước MVC. Một số request có thể được chuyển tiếp hoặc xử lý async. Hãy xác định handler thực tế được chọn.

### Dùng Interceptor thay cho Security Filter

Interceptor chạy trong luồng MVC sau khi handler mapping. Nó không bao phủ mọi request ở servlet layer và không thay thế security filter chain. Dùng Spring Security cho authentication và authorization ở ranh giới web.

### Cho rằng mọi String return đều là response body

Trong Controller server-side, String thường là tên View. Dùng ResponseBody hoặc ResponseEntity nếu muốn trả body dạng text.

### Cấu hình lại toàn bộ MVC không cần thiết

Thêm @EnableWebMvc hoặc thay danh sách converter có thể làm mất auto-configuration. Chỉ tùy chỉnh strategy thực sự cần thiết và kiểm thử hành vi mặc định quan trọng.

### Đặt nghiệp vụ vào HandlerInterceptor

Interceptor phù hợp với cross-cutting behavior quanh handler, không phải nơi điều phối use case hoặc chứa domain rule. Đưa nghiệp vụ vào application service/domain layer.

### Không kiểm thử content negotiation

Endpoint có thể hoạt động với browser nhưng thất bại với API client vì Accept hoặc Content-Type khác. Hãy kiểm thử các media type thuộc hợp đồng endpoint.

### Giả định async chạy trên cùng thread

Async request có thể đổi thread và redispatch. Không dựa vào ThreadLocal nếu chưa cấu hình context propagation.

## 22. Quy trình lần theo một request khi debug

Khi endpoint không hoạt động như mong đợi, hãy lần theo các câu hỏi:

1. Request có đến servlet container và đúng context path không?
2. Filter nào đã xử lý hoặc từ chối request?
3. Spring Security có cho request tiếp tục không?
4. DispatcherServlet nào nhận request?
5. HandlerMapping có tìm được handler không?
6. HandlerExecutionChain có interceptor nào?
7. HandlerAdapter nào hỗ trợ handler?
8. Argument resolver có bind đúng path, query, header và body không?
9. Controller có được gọi không?
10. Application service/domain/repository có hoàn tất không?
11. Return-value handler chọn body hay View?
12. Nếu là View, ViewResolver có tìm được template không?
13. Exception resolver hoặc error handler nào xử lý lỗi?
14. Response cuối cùng có status, content type và body như mong đợi không?

Cách lần theo này giúp xác định lỗi ở đúng tầng thay vì sửa Controller khi request chưa bao giờ đến Controller.

## 23. Checklist khi ánh xạ Front Controller trong Spring MVC

- DispatcherServlet được đăng ký và nhận đúng URL mapping.
- Servlet filter chain và Spring Security được cấu hình theo thứ tự mong muốn.
- HandlerMapping ánh xạ path, method và media type rõ ràng.
- Không có mapping xung đột.
- HandlerAdapter hỗ trợ loại handler đang dùng.
- Controller method có tham số và binding phù hợp.
- Validation được thực hiện trước khi use case thay đổi dữ liệu.
- HttpMessageConverter hỗ trợ media type của API.
- Return-value handler xử lý đúng View, ResponseEntity hoặc async result.
- ViewResolver tìm được template logic.
- HandlerExceptionResolver và ControllerAdvice trả lỗi an toàn.
- Filter và Interceptor được dùng đúng phạm vi.
- Static resources không bị mapping nghiệp vụ che khuất.
- Async context và timeout có chính sách rõ.
- MockMvc và integration test bao phủ luồng request quan trọng.
- Log/trace có request ID và thông tin handler mà không lộ dữ liệu nhạy cảm.

## Kết luận

Front Controller cung cấp một điểm tiếp nhận và điều phối request dùng chung. Trong Spring MVC, DispatcherServlet thực hiện vai trò này bằng cách phối hợp HandlerMapping, HandlerAdapter, interceptor, argument resolver, message converter, return-value handler, exception resolver và ViewResolver.

Controller vẫn chịu trách nhiệm cho endpoint cụ thể; application service và domain model thực hiện use case; View hoặc message converter tạo representation trả về. Filter và Spring Security xử lý những mối quan tâm ở ranh giới servlet trước khi request đến MVC. Khi hiểu đúng thứ tự và trách nhiệm của từng thành phần, người phát triển có thể lần theo request, mở rộng cấu hình có kiểm soát và kiểm thử hành vi MVC một cách chính xác.
