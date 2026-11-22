# Tiêu chí chọn thiết lập độc lập hoặc dựa trên context

`MockMvc` cho phép kiểm thử luồng xử lý Spring MVC mà không cần mở HTTP server. Khi tạo `MockMvc`, Spring Test cung cấp hai cách thiết lập thường gặp: `standaloneSetup(...)` và `webAppContextSetup(...)`.

`standaloneSetup(...)` tạo môi trường MVC tối thiểu xoay quanh controller được truyền trực tiếp vào builder. `webAppContextSetup(...)` dùng một `WebApplicationContext` đã được Spring nạp, vì vậy test có thể sử dụng cấu hình MVC và các bean thực tế trong context đó.

Tiêu chí chọn nằm ở phạm vi cần xác nhận. Nếu câu hỏi tập trung vào hành vi của một controller với các phụ thuộc được cung cấp rõ ràng, thiết lập độc lập thường gọn và nhanh. Nếu cần xác nhận controller hoạt động cùng cấu hình MVC và các bean trong web context, hãy dùng thiết lập dựa trên context.

## 1. MockMvc làm gì trong kiểm thử Spring MVC?

Trong ứng dụng chạy thật, request HTTP đi qua Servlet container, đến `DispatcherServlet`, rồi được Spring MVC định tuyến đến controller. Controller có thể dùng argument resolver để chuyển request thành tham số Java, gọi service, sau đó Spring MVC chuyển kết quả thành response thông qua message converter hoặc view resolver.

`MockMvc` mô phỏng phần xử lý request/response của Spring MVC trong cùng tiến trình test. Test tạo request, gửi qua `DispatcherServlet` được cấu hình cho môi trường test, rồi kiểm tra status, header, body, model hoặc view. Không cần mở cổng mạng hay gửi request qua socket.

Ví dụ một test thường có dạng:

```java
mockMvc.perform(get("/greetings/Lan"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.message").value("Hello, Lan"));
```

Phần khác nhau giữa hai kiểu thiết lập là cách `MockMvc` nhận controller và hạ tầng MVC để xử lý request đó.

## 2. Thiết lập độc lập với standaloneSetup

`MockMvcBuilders.standaloneSetup(controller)` nhận một hoặc nhiều controller trực tiếp. Spring Test tạo hạ tầng MVC cần thiết cho test quanh các controller đó, mà không nạp `WebApplicationContext` của ứng dụng.

Ví dụ controller và các kiểu dữ liệu dùng chung:

```java
public class GreetingResponse {

    private final String message;

    public GreetingResponse(String message) {
        this.message = message;
    }

    public String getMessage() {
        return message;
    }
}

public interface GreetingService {
    GreetingResponse greet(String name);
}

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greetings/{name}")
    public GreetingResponse greet(@PathVariable String name) {
        return greetingService.greet(name);
    }
}
```

Test độc lập có thể dùng Mockito để cung cấp service:

```java
@ExtendWith(MockitoExtension.class)
class GreetingControllerStandaloneTest {

    @Mock
    private GreetingService greetingService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        GreetingController controller = new GreetingController(greetingService);

        mockMvc = MockMvcBuilders
                .standaloneSetup(controller)
                .build();
    }

    @Test
    void returnsGreetingAsJson() throws Exception {
        when(greetingService.greet("Lan"))
                .thenReturn(new GreetingResponse("Hello, Lan"));

        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

Ở đây, test tự tạo `GreetingController`, truyền mock service vào constructor và đưa controller cho `standaloneSetup`. Không có component scan, cấu hình ứng dụng hoặc Spring application context của dự án được nạp. Test vẫn chạy các bước xử lý MVC cần thiết để ánh xạ URL, gọi controller và ghi response.

### Hạ tầng được thiết lập đến đâu?

Standalone builder cung cấp các thành phần MVC mặc định cần thiết để chạy controller test. Nó cũng cho phép tùy chỉnh nhiều phần của hạ tầng đó, ví dụ:

- `setControllerAdvice(...)` để đăng ký `@ControllerAdvice` hoặc `@RestControllerAdvice` cần dùng trong test.
- `setMessageConverters(...)` để cấu hình cách chuyển object thành JSON/XML hoặc đọc request body.
- `setValidator(...)` để dùng validator cụ thể khi kiểm tra `@Valid`.
- `setConversionService(...)` để cấu hình chuyển đổi kiểu dữ liệu.
- `addInterceptors(...)` để thêm interceptor.
- `addFilters(...)` để thêm servlet filter vào chuỗi xử lý của MockMvc.
- `setCustomArgumentResolvers(...)` để đăng ký argument resolver riêng.
- `setViewResolvers(...)` để cấu hình cách phân giải view trong test MVC kiểu server-side rendering.

Các tùy chọn cụ thể phụ thuộc phiên bản Spring Framework. Điểm chung là test phải đăng ký tường minh các thành phần tùy biến mà nó cần. Standalone builder không tự dò tìm tất cả bean cấu hình trong ứng dụng.

### Khi nào standaloneSetup phù hợp?

Chọn thiết lập độc lập khi muốn kiểm tra hành vi của một controller hoặc một nhóm nhỏ controller, chẳng hạn:

- URL và HTTP method có được ánh xạ đúng đến handler method không.
- `@PathVariable`, `@RequestParam`, `@RequestBody` có được bind đúng trong cấu hình MVC đang dùng cho test không.
- Controller gọi service với dữ liệu cần thiết và tạo response đúng không.
- Status, header và JSON response có đúng không.
- Controller xử lý exception như mong đợi khi test đăng ký exception advice tương ứng.
- Validation hoặc converter cụ thể có hoạt động đúng khi test cung cấp chính validator/converter đó.

Đây là lựa chọn hữu ích cho controller test tập trung, có ít phụ thuộc và cần chạy nhanh. Nó cũng làm rõ các phụ thuộc của controller vì test phải tự cung cấp chúng.

## 3. Thiết lập dựa trên WebApplicationContext

`MockMvcBuilders.webAppContextSetup(webApplicationContext)` nhận một `WebApplicationContext` đã được Spring tạo. Spring Test dùng context này để cấu hình `DispatcherServlet` và các thành phần Spring MVC đã đăng ký trong context.

Ví dụ cấu hình MVC tối giản:

```java
@Configuration
@EnableWebMvc
public class WebMvcTestConfig {

    @Bean
    GreetingService greetingService() {
        return name -> new GreetingResponse("Hello, " + name);
    }

    @Bean
    GreetingController greetingController(GreetingService greetingService) {
        return new GreetingController(greetingService);
    }
}
```

Test nạp cấu hình này thành `WebApplicationContext`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcTestConfig.class)
class GreetingControllerContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void usesMvcConfigurationFromWebApplicationContext() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

`@WebAppConfiguration` yêu cầu Spring Test tạo môi trường web cho test và liên kết `WebApplicationContext` với `MockServletContext`. `@ContextConfiguration` chỉ định cấu hình được dùng để nạp context. `@EnableWebMvc` đăng ký hạ tầng Spring MVC, còn các bean trong cấu hình cung cấp controller và service.

Trong dự án thực tế, cấu hình được nạp có thể là cấu hình MVC production, cấu hình test được tinh giản, hoặc một context slice do Spring Boot tạo. Mấu chốt là `webAppContextSetup` dùng bean và hạ tầng MVC đã có trong context thay vì tự tạo một cấu hình MVC riêng quanh controller.

### Những gì được dùng từ context?

Tùy cấu hình được nạp, cách này có thể bao gồm:

- Controller và các bean được đăng ký trong `WebApplicationContext`.
- `HandlerMapping` và `HandlerAdapter` của Spring MVC.
- Message converter và cấu hình nội dung request/response.
- Formatter, converter và validator được cấu hình trong MVC.
- Interceptor, controller advice và exception resolver đã đăng ký.
- View resolver và các thành phần MVC khác trong context.
- Các bean phụ thuộc được inject vào controller và các thành phần web.

Vì vậy, test có thể phát hiện lỗi ở khâu ghép cấu hình MVC và các bean, chẳng hạn thiếu một converter tùy chỉnh hoặc không đăng ký đúng controller advice. Nếu test dùng một context test được giản lược, nó chỉ xác nhận cấu hình giản lược đó; muốn xác nhận cấu hình production thì phải nạp đúng cấu hình production cần kiểm tra.

### Context-based không tự động có nghĩa mọi Servlet Filter đều được chạy

`webAppContextSetup` dùng web application context để cấu hình Spring MVC. Nếu test cần một servlet filter cụ thể trong chuỗi request của MockMvc, hãy đăng ký filter đó theo cách phù hợp, ví dụ bằng `addFilters(...)` hoặc cơ chế tích hợp của thư viện liên quan. Với Spring Security, dự án thường dùng cấu hình test tương ứng như `springSecurity()` từ Spring Security Test.

Đừng suy luận rằng một filter đã được khai báo ở môi trường triển khai thì tự động được đưa vào mọi bài test MockMvc. Hãy xác nhận test setup thực sự thêm filter hoặc security filter chain cần kiểm tra.

## 4. So sánh hai cách thiết lập

| Tiêu chí | `standaloneSetup(...)` | `webAppContextSetup(...)` |
| --- | --- | --- |
| Đầu vào | Controller được truyền trực tiếp | `WebApplicationContext` đã được nạp |
| Khởi tạo application context | Không nạp context của ứng dụng | Dùng context do Spring Test tạo hoặc được cung cấp |
| Hạ tầng MVC | Builder tạo hạ tầng cần thiết và cho phép tùy chỉnh | Dùng hạ tầng MVC đã đăng ký trong context |
| Controller | Test chỉ định controller | Controller được lấy từ context qua cấu hình MVC |
| Controller advice, converter, validator, interceptor | Thường cần đăng ký rõ trong builder nếu test cần | Được dùng nếu đã đăng ký trong context |
| Dependency của controller | Test truyền trực tiếp, thường qua mock hoặc fake | Spring inject từ context |
| Phạm vi xác nhận | Tập trung vào controller và cấu hình được khai báo trong builder | Tích hợp controller với web context và cấu hình MVC đã nạp |
| Tốc độ và độ cô lập | Thường nhanh và cô lập hơn | Thường cần thời gian tạo context, có thể được Spring cache |
| Lỗi cấu hình context | Không nhằm phát hiện lỗi cấu hình context của ứng dụng | Có thể phát hiện lỗi trong context được nạp |

Cả hai cách đều dùng request/response mô phỏng của Spring Test. Cả hai đều không khởi chạy Servlet container thật và không kiểm tra việc mở cổng HTTP, TLS, deploy WAR hoặc xử lý request qua connector mạng.

## 5. Tiêu chí quyết định: cần kiểm tra điều gì?

Hãy diễn đạt mục tiêu test thành một câu hỏi cụ thể trước khi chọn builder.

| Câu hỏi cần trả lời | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Controller có gọi service và trả JSON đúng với đầu vào này không? | `standaloneSetup` | Chỉ cần controller và các phụ thuộc được kiểm soát trong test |
| Controller có trả status và header đúng khi service báo lỗi không? | `standaloneSetup` nếu đăng ký advice cần thiết | Có thể kiểm soát kết quả service và exception handler được test đưa vào |
| Controller có hoạt động với converter hoặc formatter production đã cấu hình không? | `webAppContextSetup` | Cần dùng cấu hình MVC từ context |
| `@ControllerAdvice` được khai báo trong ứng dụng có xử lý exception đúng không? | `webAppContextSetup` | Cần xác nhận advice được context đăng ký và áp dụng |
| Interceptor hoặc argument resolver tùy chỉnh có tham gia xử lý request không? | `webAppContextSetup` | Cần dùng thành phần đã cấu hình trong MVC context |
| Một controller đơn lẻ có hoạt động mà không cần nạp toàn bộ cấu hình ứng dụng không? | `standaloneSetup` | Phạm vi nhỏ, dễ cô lập và chạy nhanh |
| Nhiều thành phần MVC có phối hợp đúng trong cấu hình web đã nạp không? | `webAppContextSetup` | Phù hợp để kiểm tra tích hợp trong Spring web context |
| Ứng dụng có nhận request HTTP thực trên cổng mạng không? | Embedded server hoặc container thật | Cả hai builder đều chạy trong môi trường mock |

Không có quy tắc rằng một loại test luôn tốt hơn loại kia. Lựa chọn phụ thuộc vào rủi ro mà test cần phát hiện. Nếu một lỗi có thể nằm trong cấu hình MVC production, bài test chỉ dùng standalone builder sẽ không cung cấp đủ bằng chứng.

## 6. Ví dụ cùng một controller được kiểm tra theo hai mục tiêu

Giả sử `GreetingController` trả lời `GET /greetings/{name}` bằng cách gọi `GreetingService`.

### Mục tiêu A: kiểm tra quyết định của controller

Ta muốn xác nhận controller chuyển đúng tên vào service và trả kết quả service dưới dạng JSON. Không cần kiểm tra component scan hoặc converter tùy chỉnh của ứng dụng. Khi đó:

```java
@ExtendWith(MockitoExtension.class)
class GreetingControllerBehaviorTest {

    @Mock
    GreetingService greetingService;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController(greetingService))
                .build();
    }

    @Test
    void passesPathVariableToService() throws Exception {
        when(greetingService.greet("Lan"))
                .thenReturn(new GreetingResponse("Hello, Lan"));

        mockMvc.perform(get("/greetings/Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));

        verify(greetingService).greet("Lan");
    }
}
```

Test này xác nhận request mô phỏng được ánh xạ đến controller đã cung cấp, tham số đường dẫn được bind và controller gọi service đúng. Vì service là mock, test không xác nhận service hoặc database hoạt động đúng.

### Mục tiêu B: kiểm tra cấu hình MVC đã nạp

Giả sử ứng dụng đăng ký một `@RestControllerAdvice` để chuyển `GreetingNotFoundException` thành response HTTP 404. Muốn kiểm tra advice thực sự được phát hiện và áp dụng từ cấu hình Spring, hãy nạp context có controller cùng advice rồi dùng `webAppContextSetup`.

```java
class GreetingNotFoundException extends RuntimeException {

    GreetingNotFoundException(String name) {
        super(name);
    }
}

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(GreetingNotFoundException.class)
    ResponseEntity<Map<String, String>> handleNotFound(
            GreetingNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("error", exception.getMessage()));
    }
}
```

```java
@Configuration
@EnableWebMvc
class GreetingWebConfig {

    @Bean
    GreetingService greetingService() {
        return name -> {
            throw new GreetingNotFoundException(name);
        };
    }

    @Bean
    GreetingController greetingController(GreetingService service) {
        return new GreetingController(service);
    }

    @Bean
    ApiExceptionHandler apiExceptionHandler() {
        return new ApiExceptionHandler();
    }
}
```

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = GreetingWebConfig.class)
class GreetingControllerMvcConfigurationTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void appliesControllerAdviceFromWebContext() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Lan"));
    }
}
```

Trong ví dụ này, service cố ý ném exception để test tập trung vào cách Spring MVC xử lý exception. `ApiExceptionHandler` là bean trong web context; test xác nhận exception resolver của Spring MVC dùng advice đó để tạo response 404.

Nếu chuyển test này sang `standaloneSetup(new GreetingController(service))` mà không gọi `.setControllerAdvice(new ApiExceptionHandler())`, advice không tự được phát hiện từ cấu hình ứng dụng vì application context không được nạp. Test có thể nhận response khác với cấu hình production. Đây là ví dụ điển hình cho việc chọn builder dựa trên phạm vi cần kiểm tra.

## 7. Dùng các kiểu test của Spring Boot

Trong ứng dụng Spring Boot, có một số annotation giúp chuẩn bị `MockMvc` mà không cần tự viết toàn bộ cấu hình.

### `@WebMvcTest`

`@WebMvcTest` tạo một Spring MVC test slice, tập trung vào các thành phần web được chọn. Nó thường phù hợp khi muốn kiểm tra controller cùng cấu hình MVC được Boot tự động thiết lập nhưng không cần khởi tạo toàn bộ service, repository và các thành phần ứng dụng khác.

Các phụ thuộc ngoài slice thường được cung cấp bằng mock bean hoặc cấu hình test phù hợp với phiên bản Spring Boot đang dùng. `@WebMvcTest` là kiểm thử dựa trên Spring context; nó không tương đương với việc tự truyền controller cho `standaloneSetup`.

### `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`

Nếu cần nhiều bean và cấu hình ứng dụng cùng tham gia, có thể dùng:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApplicationMvcIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesConfiguredEndpoint() throws Exception {
        mockMvc.perform(get("/health-view"))
                .andExpect(status().isOk());
    }
}
```

Đây là cách kiểm thử Spring context rộng hơn với MockMvc. Nếu chỉ cần một lát cắt MVC, `@WebMvcTest` thường tiết kiệm hơn. Nếu chỉ cần kiểm tra một controller và không cần cấu hình ứng dụng, standalone setup có thể đủ.

Khi cần kiểm tra HTTP qua cổng mạng, dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` hoặc triển khai ứng dụng vào container mục tiêu rồi gửi request HTTP thực. `@AutoConfigureMockMvc` vẫn dùng môi trường mock; nó không tự biến test thành kiểm thử qua network.

## 8. Các lỗi chọn setup thường gặp

### Dùng standalone nhưng kỳ vọng component scan tự tìm bean

Standalone builder chỉ nhận các controller được truyền vào và các thành phần được đăng ký qua builder. Nó không quét package để tự tìm controller advice, interceptor, converter hoặc validator của ứng dụng. Nếu mục tiêu là kiểm tra các thành phần được phát hiện từ cấu hình Spring, dùng context-based setup hoặc đăng ký chúng tường minh trong standalone test.

### Dùng webAppContextSetup nhưng nạp context thiếu cấu hình cần kiểm tra

`webAppContextSetup` chỉ dùng những gì context được cung cấp đã nạp. Nếu test context bỏ qua một converter, security configuration hoặc controller advice production, test không thể xác nhận thành phần đó. Hãy kiểm tra cấu hình test có phản ánh đúng phần ứng dụng mà mục tiêu test yêu cầu hay không.

### Dùng full application context cho mọi controller test

Nạp toàn bộ ứng dụng có thể làm test chậm, tăng phụ thuộc vào database hoặc dịch vụ ngoài và khiến lỗi khó khoanh vùng. Nếu mục tiêu chỉ là binding, status và response của một controller, một standalone test có thể cung cấp phản hồi nhanh hơn. Dành context test rộng cho các hành vi cần tích hợp thực sự.

### Cho rằng MockMvc chứng minh container triển khai đúng

Cả standalone và context-based đều xử lý request mô phỏng. Chúng không kiểm tra connector HTTP, TLS, deployment descriptor, context path thực tế hoặc startup lifecycle của Tomcat/Jetty/Undertow. Dùng embedded server hoặc container thật cho các yêu cầu đó.

### Kiểm tra quá nhiều lời gọi nội bộ trong standalone test

Mock service giúp kiểm soát dữ liệu và xác nhận tương tác cần thiết. Tuy nhiên, test controller nên ưu tiên hành vi HTTP quan sát được. Chỉ xác minh lời gọi service khi việc truyền tham số hoặc lựa chọn thao tác là một phần quan trọng của hành vi; tránh ràng buộc test với mọi chi tiết triển khai.

## 9. Quy trình chọn và tổ chức test

Có thể áp dụng quy trình sau cho mỗi nhóm controller:

1. Viết rõ điều cần chứng minh: hành vi riêng của controller, tích hợp với cấu hình MVC, hay HTTP runtime thực.
2. Liệt kê thành phần bắt buộc tham gia: controller, service, advice, converter, validator, interceptor, filter, security chain và các bean khác.
3. Nếu chỉ cần controller cùng phụ thuộc kiểm soát được, bắt đầu bằng `standaloneSetup`.
4. Nếu cần các bean và cấu hình đã đăng ký trong Spring web context, dùng `webAppContextSetup` hoặc test slice phù hợp của Spring Boot.
5. Nếu cần xác nhận request đi qua cổng HTTP hoặc hành vi của container, dùng embedded server hay container triển khai thật.
6. Giữ test ở phạm vi nhỏ nhất có thể trả lời đầy đủ câu hỏi; bổ sung test context rộng cho những rủi ro mà test độc lập không thể phát hiện.

| Phạm vi | Loại test gợi ý |
| --- | --- |
| Một controller, service được mock, response JSON | Standalone MockMvc |
| Controller cùng controller advice, converter, interceptor đã cấu hình | Context-based MockMvc |
| MVC slice trong Spring Boot | `@WebMvcTest` |
| Nhiều tầng ứng dụng cùng tham gia nhưng vẫn dùng request mock | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Request HTTP thực qua embedded server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Deployment trên container bên ngoài | Test trên container mục tiêu |

## 10. Kết luận

`standaloneSetup(...)` phù hợp khi muốn kiểm tra controller trong một môi trường MVC nhỏ, do test chủ động cung cấp controller, dependency và các cấu hình bổ sung. `webAppContextSetup(...)` phù hợp khi muốn kiểm tra controller trong `WebApplicationContext` cùng hạ tầng MVC và bean đã được nạp.

Hãy chọn theo thành phần cần tham gia và loại lỗi cần phát hiện. Standalone giúp test controller cô lập, nhanh và rõ phụ thuộc; context-based giúp xác nhận cấu hình MVC và sự phối hợp giữa các bean trong web context. Khi yêu cầu liên quan đến HTTP network hoặc Servlet container thực, cần một cấp kiểm thử có server/container thật vì cả hai cách thiết lập MockMvc đều chạy trong môi trường mô phỏng.
