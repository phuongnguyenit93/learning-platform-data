# Đăng ký ControllerAdvice, converter và Validator

**Ngữ cảnh:** Spring Framework Testing → Thiết lập MockMvc.

Khi kiểm thử Spring MVC bằng MockMvc, một request đi qua nhiều thành phần trước khi controller trả về response. Spring phải tìm handler phù hợp, chuyển đổi dữ liệu đầu vào, gọi controller, xử lý lỗi và chuyển đổi kết quả thành HTTP response. Vì vậy, một bài test chỉ khởi tạo controller có thể bỏ sót những hành vi quan trọng của ứng dụng.

Ba nhóm thành phần thường cần đăng ký rõ ràng khi thiết lập MockMvc là:

- **ControllerAdvice:** xử lý ngoại lệ và các mối quan tâm dùng chung cho nhiều controller.
- **Converter và HttpMessageConverter:** chuyển đổi giá trị request thành kiểu Java hoặc chuyển đối tượng Java thành nội dung response.
- **Validator:** kiểm tra dữ liệu đầu vào theo quy tắc Bean Validation hoặc quy tắc nghiệp vụ.

Cách đăng ký phụ thuộc vào việc test dùng **standaloneSetup** hay **webAppContextSetup**. Chọn đúng cách giúp test phản ánh chính xác phạm vi mà nó muốn kiểm tra.

## 1. MockMvc cần những thành phần nào?

MockMvc mô phỏng quá trình xử lý request của Spring MVC trong môi trường kiểm thử. Nó gọi DispatcherServlet và các thành phần MVC đã cấu hình, sau đó cho phép kiểm tra status, header, body và các kết quả xử lý khác mà không cần mở cổng HTTP thật.

Một request có thể đi qua luồng khái quát sau:

~~~text
MockMvc request
      |
      v
DispatcherServlet
      |
      v
HandlerMapping tìm Controller method
      |
      v
HandlerAdapter chuẩn bị tham số
      |
      +--> HttpMessageConverter đọc request body
      |
      +--> ConversionService chuyển đổi path/query/form value
      |
      +--> Validator kiểm tra dữ liệu được yêu cầu validate
      |
      v
Controller method
      |
      +--> Exception? ----> ControllerAdvice / HandlerExceptionResolver
      |
      v
HttpMessageConverter ghi response body
      |
      v
MockMvc ResultActions và assertions
~~~

Đây là luồng khái quát. Các bước cụ thể phụ thuộc vào loại tham số, annotation trên handler method và cấu hình MVC.

Nếu một thành phần không được đưa vào cấu hình MockMvc, test có thể không thể hiện hành vi của ứng dụng thật. Ví dụ, controller chạy bình thường nhưng lỗi nghiệp vụ không được ánh xạ thành HTTP 404 vì advice chưa được đăng ký; hoặc query parameter status=paid không chuyển được thành enum vì converter tùy chỉnh chưa được thêm.

## 2. Hai cách thiết lập MockMvc và ảnh hưởng đến việc đăng ký

Spring Test cung cấp hai cách thiết lập thường dùng.

| Cách thiết lập | Cách tạo MVC infrastructure | Khi nào phù hợp |
|---|---|---|
| standaloneSetup(...) | Tạo cấu hình MVC tối thiểu cho controller được chỉ định | Test tập trung vào một hoặc vài controller, chủ động khai báo dependency MVC |
| webAppContextSetup(context) | Dùng WebApplicationContext đã được cấu hình | Test tích hợp các controller với cấu hình MVC thực tế của ứng dụng |

### 2.1. standaloneSetup

Ví dụ:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .build();
~~~

Cách này không khởi động toàn bộ application context. MockMvc tạo hạ tầng cần thiết cho controller được truyền vào. Đây là lựa chọn nhanh cho controller test, nhưng các thành phần tùy chỉnh của ứng dụng cần được cung cấp tường minh khi test phụ thuộc vào chúng.

Các phương thức cấu hình quan trọng gồm:

- setControllerAdvice(...)
- setMessageConverters(...)
- setConversionService(...)
- setValidator(...)
- setCustomArgumentResolvers(...)
- setHandlerExceptionResolvers(...)

Không cần đăng ký tất cả trong mọi test. Chỉ đăng ký thành phần mà request của test cần sử dụng.

### 2.2. webAppContextSetup

Ví dụ:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
~~~

Cách này sử dụng các bean và MVC infrastructure trong WebApplicationContext. Nếu ControllerAdvice, WebMvcConfigurer, converter và validator đã được cấu hình đúng trong context, MockMvc có thể sử dụng chúng như ứng dụng MVC đã cấu hình.

Một test Spring Framework thuần có thể nạp web context bằng:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MvcTestConfig.class)
class OrderControllerWebMvcTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }
}
~~~

**@WebAppConfiguration** yêu cầu Spring Test tạo WebApplicationContext. **@ContextConfiguration** chỉ định cấu hình để tạo context; cấu hình đó phải đăng ký controller và các thành phần MVC cần kiểm thử.

Nếu mục tiêu là kiểm tra việc đăng ký thành phần trong cấu hình ứng dụng, webAppContextSetup thường phù hợp hơn vì nó đi qua cùng cấu hình MVC mà ứng dụng sử dụng. Nếu mục tiêu là kiểm tra riêng hành vi controller với một cấu hình nhỏ, standaloneSetup giúp test tập trung hơn.

## 3. Đăng ký ControllerAdvice

### 3.1. ControllerAdvice giải quyết vấn đề gì?

**@ControllerAdvice** định nghĩa các thành phần dùng chung cho nhiều controller. Những chức năng thường dùng gồm:

- Xử lý ngoại lệ bằng @ExceptionHandler.
- Đăng ký phương thức @InitBinder để tùy chỉnh data binding.
- Cung cấp dữ liệu dùng chung bằng @ModelAttribute.

**@RestControllerAdvice** kết hợp @ControllerAdvice và @ResponseBody, phù hợp khi handler trả dữ liệu trong response body, chẳng hạn JSON.

Ví dụ một advice ánh xạ lỗi không tìm thấy đơn hàng thành HTTP 404:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        exception.getMessage()
                ));
    }
}

record ApiError(String code, String message) {}
~~~

Khi controller ném OrderNotFoundException, Spring tìm exception handler phù hợp và tạo response. Test cần gửi request qua MockMvc để xác nhận toàn bộ quá trình ánh xạ ngoại lệ, thay vì gọi trực tiếp phương thức handleOrderNotFound.

### 3.2. Đăng ký advice với standaloneSetup

Với standaloneSetup, truyền advice vào builder:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setControllerAdvice(new ApiExceptionHandler())
        .build();
~~~

Có thể truyền nhiều advice:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setControllerAdvice(
                new ApiExceptionHandler(),
                new ValidationExceptionHandler()
        )
        .build();
~~~

Đối tượng truyền vào cần là instance có annotation và phương thức handler phù hợp. Vì standalone setup không quét toàn bộ component của ứng dụng, chỉ việc đánh dấu class bằng @ControllerAdvice không có nghĩa instance đó tự động được phát hiện trong cấu hình standalone.

Nếu controller phụ thuộc service, hãy truyền mock hoặc fake dependency vào constructor/controller theo cách dự án đang tổ chức. Không cần tạo application context chỉ để đăng ký một advice cho một controller test.

### 3.3. Đăng ký advice với webAppContextSetup

Trong cấu hình dùng WebApplicationContext, advice phải là bean được context quản lý. Có thể khai báo bean tường minh:

~~~java
@Configuration
@EnableWebMvc
class MvcTestConfig {

    @Bean
    OrderController orderController() {
        return new OrderController();
    }

    @Bean
    ApiExceptionHandler apiExceptionHandler() {
        return new ApiExceptionHandler();
    }
}
~~~

Hoặc dùng component scan ở package chứa controller và advice:

~~~java
@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = {
        OrderController.class,
        ApiExceptionHandler.class
})
class MvcTestConfig {
}
~~~

Sau khi context khởi tạo, tạo MockMvc:

~~~java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
~~~

Không cần gọi thêm setControllerAdvice nếu advice đã được đăng ký đúng trong context. Nếu truyền lại một advice instance khác, test có thể đang kiểm tra một cấu hình khác với cấu hình bean thực tế.

### 3.4. Chọn phạm vi áp dụng của ControllerAdvice

Mặc định, @ControllerAdvice có thể áp dụng cho nhiều controller trong ứng dụng. Có thể giới hạn phạm vi bằng các thuộc tính:

- basePackages hoặc basePackageClasses: áp dụng theo package.
- assignableTypes: áp dụng cho controller thuộc các kiểu được chỉ định.
- annotations: áp dụng cho controller mang annotation được chỉ định.

Ví dụ:

~~~java
@RestControllerAdvice(basePackageClasses = PublicApiMarker.class)
class PublicApiExceptionHandler {
    // Các exception handler chỉ áp dụng cho nhóm controller tương ứng.
}
~~~

Khi có nhiều advice, thứ tự có thể được điều khiển bằng @Order hoặc Ordered. Controller-level @ExceptionHandler được xét trước global advice. Trong một advice, exception match trực tiếp thường được ưu tiên hơn match qua cause. Vì thứ tự giữa nhiều advice ảnh hưởng handler nào được chọn, test nên xác nhận rõ response khi có các handler có thể cùng khớp.

Không nên tạo nhiều advice có phạm vi chồng lấn nếu chúng xử lý cùng một loại exception mà không có quy tắc thứ tự rõ ràng.

### 3.5. Kiểm thử kết quả của ControllerAdvice

Ví dụ:

~~~java
@Test
void mapsOrderNotFoundToNotFoundResponse() throws Exception {
    mockMvc.perform(get("/orders/404"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
~~~

Test này kiểm tra ba điều:

1. Request đi đến controller và tạo ra ngoại lệ dự kiến.
2. Advice xử lý ngoại lệ đó và trả HTTP 404.
3. Response body được serialize thành JSON với mã lỗi mong đợi.

Nếu test chỉ gọi controller.findOrder(404) và xác nhận exception bị ném, nó chưa kiểm tra ControllerAdvice hoặc quá trình tạo HTTP response.

## 4. Phân biệt Converter và HttpMessageConverter

Trong Spring MVC, từ “converter” thường chỉ hai nhóm khác nhau. Cần phân biệt chúng khi đăng ký và khi viết test.

| Thành phần | Công việc | Ví dụ |
|---|---|---|
| HttpMessageConverter<T> | Đọc hoặc ghi toàn bộ HTTP message body | JSON thành DTO, DTO thành JSON |
| Converter<S, T> | Chuyển một giá trị từ kiểu nguồn sang kiểu đích | Chuỗi paid thành enum OrderStatus |
| Formatter<T> | Chuyển đổi giá trị theo định dạng, thường có hỗ trợ locale | Chuỗi ngày tháng thành LocalDate |

HttpMessageConverter làm việc với body và media type như application/json. Converter và Formatter thường tham gia vào quá trình binding các giá trị từ path variable, query parameter hoặc form field.

Đăng ký một Converter<String, OrderStatus> không thay thế Jackson message converter. Ngược lại, cấu hình Jackson không tự đăng ký quy tắc chuyển query parameter thành enum theo định dạng riêng của ứng dụng.

## 5. Đăng ký HttpMessageConverter

### 5.1. Vai trò của HttpMessageConverter

Spring MVC dùng HttpMessageConverter để:

- Đọc request body thành đối tượng Java cho @RequestBody.
- Ghi đối tượng Java thành response body cho @ResponseBody hoặc @RestController.
- Chọn cách đọc/ghi dựa trên media type, chẳng hạn JSON hoặc XML.

Với Jackson trên classpath, MappingJackson2HttpMessageConverter thường đảm nhiệm JSON. Các ứng dụng có thể cần converter riêng cho định dạng hoặc kiểu dữ liệu đặc thù.

Ví dụ một endpoint nhận JSON:

~~~java
@PostMapping("/orders")
ResponseEntity<OrderResponse> create(
        @RequestBody CreateOrderRequest request) {
    // Xử lý yêu cầu và trả về OrderResponse.
}
~~~

Nếu converter JSON không được đăng ký hoặc không hỗ trợ media type của request, Spring có thể trả lỗi 415 Unsupported Media Type hoặc lỗi đọc body tùy tình huống.

### 5.2. Đăng ký trong standaloneSetup

Dùng setMessageConverters(...):

~~~java
MappingJackson2HttpMessageConverter jsonConverter =
        new MappingJackson2HttpMessageConverter();

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setMessageConverters(jsonConverter)
        .build();
~~~

Lưu ý: khi gọi setMessageConverters, danh sách converter được cung cấp trở thành danh sách converter mà standalone builder sử dụng. Nếu ứng dụng cần thêm converter cho String, byte array, XML hoặc loại body khác, test phải cung cấp những converter cần thiết. Không giả định danh sách converter mặc định của MVC vẫn tự động được nối thêm.

Nếu cần cấu hình Jackson giống ứng dụng thật, hãy truyền ObjectMapper đã cấu hình:

~~~java
ObjectMapper objectMapper = new ObjectMapper();
// Đăng ký module và cấu hình serialization cần thiết của ứng dụng.

MappingJackson2HttpMessageConverter jsonConverter =
        new MappingJackson2HttpMessageConverter(objectMapper);
~~~

Với Java Time, module Jackson phù hợp cần có trong classpath và được đăng ký theo cấu hình của dự án. Trong test tích hợp dùng webAppContextSetup, converter do MVC configuration tạo ra sẽ được sử dụng thay vì phải dựng lại riêng trong từng test.

### 5.3. Đăng ký trong WebMvcConfigurer

Với cấu hình Spring MVC, có hai điểm mở rộng thường gặp:

- configureMessageConverters(...): cấu hình danh sách converter; khi thêm converter vào danh sách này, bạn chịu trách nhiệm về danh sách được sử dụng.
- extendMessageConverters(...): sửa đổi hoặc bổ sung converter sau khi danh sách mặc định được tạo.

Nếu chỉ muốn thêm một converter tùy chỉnh và giữ các converter mặc định, extendMessageConverters thường phù hợp:

~~~java
@Configuration
@EnableWebMvc
class MvcConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {

        converters.add(0, new CustomReportMessageConverter());
    }
}
~~~

Vị trí trong danh sách có thể ảnh hưởng converter được chọn khi nhiều converter cùng hỗ trợ media type và kiểu dữ liệu. Đặt converter chuyên biệt trước converter tổng quát khi đó là yêu cầu có chủ đích. Không thêm converter trùng lặp hoặc làm thay đổi thứ tự mà không hiểu tác động.

### 5.4. Kiểm thử request và response body

Ví dụ kiểm tra endpoint nhận JSON:

~~~java
@Test
void readsJsonRequestAndWritesJsonResponse() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "An"
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.customerName").value("An"));
}
~~~

contentType mô tả định dạng body gửi lên; accept mô tả định dạng response mà client mong muốn. jsonPath xác nhận cấu trúc JSON đã được ghi ra.

Để kiểm tra converter thực sự được dùng, cần gửi body qua MockMvcRequestBuilders và để Spring đọc body. Việc tự gọi ObjectMapper.readValue trong test không kiểm tra đăng ký HttpMessageConverter của MVC.

## 6. Đăng ký Converter và Formatter cho data binding

### 6.1. Converter chuyển đổi giá trị đơn

Giả sử API nhận query parameter status=paid, nhưng enum trong Java dùng PAID:

~~~java
enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Tạo converter:

~~~java
final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.valueOf(
                source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Converter này chuẩn hóa chuỗi đầu vào rồi chuyển thành enum. Locale.ROOT giúp việc chuyển chữ hoa không phụ thuộc locale mặc định của máy chạy test.

Nếu chuỗi không khớp giá trị enum, valueOf ném IllegalArgumentException; Spring binding có thể chuyển lỗi đó thành lỗi type mismatch. Nếu API cần thông báo thân thiện hoặc mã lỗi riêng, có thể bổ sung exception handling phù hợp.

### 6.2. Đăng ký Converter trong standaloneSetup

Standalone builder nhận FormattingConversionService:

~~~java
DefaultFormattingConversionService conversionService =
        new DefaultFormattingConversionService();

conversionService.addConverter(new StringToOrderStatusConverter());

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setConversionService(conversionService)
        .build();
~~~

DefaultFormattingConversionService cung cấp các chuyển đổi định dạng thông dụng và cho phép thêm converter tùy chỉnh. Khi truyền conversion service riêng, test cần bảo đảm nó có đủ formatter và converter mà handler cần.

### 6.3. Đăng ký Converter trong WebMvcConfigurer

Với MVC context, đăng ký qua addFormatters:

~~~java
@Configuration
@EnableWebMvc
class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderStatusConverter());
    }
}
~~~

Spring MVC sử dụng conversion service để chuyển đổi các giá trị binding như:

- @PathVariable
- @RequestParam
- @ModelAttribute
- Các trường của form object

Ví dụ controller:

~~~java
@GetMapping("/orders")
Map<String, String> findByStatus(
        @RequestParam OrderStatus status) {

    return Map.of("status", status.name());
}
~~~

Test:

~~~java
@Test
void convertsLowercaseQueryParameterToEnum() throws Exception {
    mockMvc.perform(get("/orders").param("status", "paid"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"));
}
~~~

Nếu converter không được đăng ký, chuỗi paid có thể không chuyển được thành enum và request thất bại trước khi controller method được gọi. Test qua MockMvc giúp xác nhận cả bước binding tham số.

### 6.4. Khi nào nên dùng Formatter?

Formatter<T> phù hợp khi chuyển đổi một kiểu dữ liệu có quy tắc hiển thị/nhập liệu và có thể phụ thuộc locale. Ví dụ định dạng ngày tháng nhập từ form.

~~~java
final class LocalDateFormatter implements Formatter<LocalDate> {

    private final DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/yyyy");

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, formatter);
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return formatter.format(object);
    }
}
~~~

Đăng ký bằng:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new LocalDateFormatter());
}
~~~

Trong ứng dụng thực tế, nếu định dạng phụ thuộc locale, formatter nên sử dụng locale được truyền vào thay vì cố định một định dạng. Ví dụ trên minh họa điểm đăng ký và có thể được mở rộng theo quy tắc nhập liệu của ứng dụng.

## 7. Đăng ký Validator

### 7.1. Validator có nhiệm vụ gì?

Validator kiểm tra dữ liệu đã được bind hoặc deserialize có thỏa mãn quy tắc hay không. Spring hỗ trợ:

- Spring org.springframework.validation.Validator.
- Jakarta Bean Validation thông qua các annotation như @NotBlank, @Size, @Email, @Min.
- Các validation group và quy tắc tùy chỉnh.

Với Spring Framework 6 và Spring Boot 3, Bean Validation sử dụng package jakarta.validation.*. Dự án cần có implementation của Jakarta Bean Validation, thường là Hibernate Validator, trên classpath. Chỉ có annotation mà không có provider phù hợp thì không đủ để thực thi validation.

Ví dụ request DTO:

~~~java
public record CreateOrderRequest(
        @NotBlank
        @Size(max = 100)
        String customerName
) {}
~~~

Controller yêu cầu validate:

~~~java
@PostMapping("/orders")
ResponseEntity<Map<String, String>> create(
        @Valid @RequestBody CreateOrderRequest request) {

    return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(Map.of("customerName", request.customerName()));
}
~~~

@Valid yêu cầu Spring thực hiện validation trên đối tượng được tạo từ request body. Nếu có lỗi, Spring MVC phát sinh MethodArgumentNotValidException trước khi gọi phần thân controller method.

### 7.2. Đăng ký Validator trong standaloneSetup

Có thể dùng LocalValidatorFactoryBean làm validator:

~~~java
LocalValidatorFactoryBean validator =
        new LocalValidatorFactoryBean();

validator.afterPropertiesSet();

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setValidator(validator)
        .build();
~~~

LocalValidatorFactoryBean kết nối Jakarta Bean Validation với giao diện org.springframework.validation.Validator của Spring. Trong ví dụ standalone, cần khởi tạo bean trước khi truyền vào builder.

Nếu dự án dùng validator tùy chỉnh triển khai Spring Validator, có thể truyền trực tiếp instance đó. Validator phải hỗ trợ đúng kiểu đối tượng mà controller cần kiểm tra.

### 7.3. Đăng ký Validator trong WebMvcConfigurer

Trong cấu hình MVC, override getValidator():

~~~java
@Configuration
@EnableWebMvc
class MvcConfig implements WebMvcConfigurer {

    @Bean
    LocalValidatorFactoryBean mvcValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Override
    public Validator getValidator() {
        return mvcValidator();
    }
}
~~~

MVC infrastructure sử dụng validator này cho quá trình data binding và validation. Trong cấu hình thật, hãy bảo đảm bean được tạo và quản lý bởi Spring context. Nếu không cần validator tùy chỉnh, Spring MVC có thể cấu hình validator mặc định khi Bean Validation provider hiện diện.

Một cách khác là đăng ký validator theo từng binder qua @InitBinder. Điều này hữu ích khi quy tắc chỉ áp dụng cho một nhóm controller hoặc một loại form cụ thể.

### 7.4. Dùng @InitBinder để bổ sung validator

Ví dụ:

~~~java
@ControllerAdvice
class OrderBindingAdvice {

    @InitBinder
    void configureOrderBinder(WebDataBinder binder) {
        binder.addValidators(new OrderBusinessValidator());
    }
}
~~~

addValidators thêm validator vào binder hiện có. Nếu dùng setValidator, validator chính của binder có thể bị thay thế; hãy chọn đúng phương thức theo ý định và kiểm tra xem Bean Validation mặc định có cần được giữ lại không.

@InitBinder cũng có thể đăng ký property editor hoặc cấu hình binding. Khi đặt trong @ControllerAdvice, phương thức binder có thể áp dụng cho nhiều controller thuộc phạm vi advice.

### 7.5. Phân biệt lỗi validation với lỗi binding

Hai nhóm lỗi này có liên quan nhưng không giống nhau:

- **Validation error:** dữ liệu đã được chuyển thành đối tượng, nhưng vi phạm quy tắc như tên rỗng hoặc độ dài vượt giới hạn.
- **Binding/conversion error:** Spring không thể chuyển giá trị đầu vào sang kiểu đích, ví dụ status=unknown không thể chuyển thành OrderStatus.

Với @Valid @RequestBody, lỗi Bean Validation thường được biểu diễn bằng MethodArgumentNotValidException. Với request parameter hoặc model attribute, lỗi chuyển đổi có thể được thể hiện dưới dạng MethodArgumentTypeMismatchException, BindException hoặc lỗi binding tương ứng.

Spring Framework 6.1 còn có cơ chế method validation cho constraint đặt trực tiếp trên tham số hoặc giá trị trả về của handler method; lỗi có thể được biểu diễn bằng HandlerMethodValidationException. Khi xây dựng API error response thống nhất, cần xử lý đúng các loại exception mà ứng dụng thực sự phát sinh.

### 7.6. Kiểm thử validation

Ví dụ request không hợp lệ:

~~~java
@Test
void rejectsBlankCustomerName() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": " "
                            }
                            """))
            .andExpect(status().isBadRequest());
}
~~~

Để kiểm tra response lỗi do advice chuẩn hóa, có thể bổ sung handler:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<ApiError> handleValidation(
        MethodArgumentNotValidException exception) {

    String detail = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> error.getField() + ": "
                    + error.getDefaultMessage())
            .findFirst()
            .orElse("Invalid request");

    return ResponseEntity
            .badRequest()
            .body(new ApiError("VALIDATION_FAILED", detail));
}
~~~

Sau đó test response:

~~~java
@Test
void returnsStandardErrorWhenRequestValidationFails()
        throws Exception {

    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": ""
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.message")
                    .value(org.hamcrest.Matchers.containsString(
                            "customerName")));
}
~~~

Test này xác nhận cả ba thành phần phối hợp: Jackson đọc JSON, Validator kiểm tra DTO và ControllerAdvice ánh xạ lỗi thành response theo hợp đồng API.

## 8. Ví dụ kết hợp cả ba thành phần trong standalone MockMvc

Phần này ghép các ý trên thành một cấu hình test tập trung cho OrderController.

Giả sử controller có các hành vi:

- GET /orders?status=paid: nhận enum qua query parameter.
- GET /orders/404: ném OrderNotFoundException.
- POST /orders: nhận JSON và yêu cầu customerName không được để trống.

### 8.1. Controller và kiểu dữ liệu

~~~java
enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}

record CreateOrderRequest(
        @NotBlank
        @Size(max = 100)
        String customerName
) {}

record ApiError(String code, String message) {}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}

@RestController
class OrderController {

    @GetMapping("/orders")
    Map<String, String> findByStatus(
            @RequestParam OrderStatus status) {

        return Map.of("status", status.name());
    }

    @GetMapping("/orders/{id}")
    Map<String, Long> findById(@PathVariable long id) {
        if (id == 404) {
            throw new OrderNotFoundException(id);
        }
        return Map.of("id", id);
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody CreateOrderRequest request) {

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(Map.of("customerName", request.customerName()));
    }
}
~~~

### 8.2. Advice và converter

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        exception.getMessage()
                ));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {

        String detail = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> error.getField() + ": "
                        + error.getDefaultMessage())
                .findFirst()
                .orElse("Invalid request");

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_FAILED", detail));
    }
}

final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.valueOf(
                source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

### 8.3. Tạo MockMvc và đăng ký thành phần

~~~java
class OrderControllerMockMvcTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        LocalValidatorFactoryBean validator =
                new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();
        conversionService.addConverter(
                new StringToOrderStatusConverter()
        );

        MappingJackson2HttpMessageConverter jsonConverter =
                new MappingJackson2HttpMessageConverter();

        mockMvc = MockMvcBuilders
                .standaloneSetup(new OrderController())
                .setControllerAdvice(new ApiExceptionHandler())
                .setMessageConverters(jsonConverter)
                .setConversionService(conversionService)
                .setValidator(validator)
                .build();
    }

    @Test
    void convertsQueryParameter() throws Exception {
        mockMvc.perform(get("/orders").param("status", "paid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PAID"));
    }

    @Test
    void handlesControllerException() throws Exception {
        mockMvc.perform(get("/orders/404"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("ORDER_NOT_FOUND"));
    }

    @Test
    void validatesJsonRequest() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": ""
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"));
    }

    @Test
    void acceptsValidJsonRequest() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": "An"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.customerName").value("An"));
    }
}
~~~

Ví dụ sử dụng setMessageConverters với một Jackson converter vì các endpoint minh họa chỉ trao đổi JSON. Nếu controller cần String, multipart, XML hoặc các loại body khác, hãy bổ sung converter phù hợp. Trong dự án thực tế, có thể tái sử dụng ObjectMapper và validator đã được cấu hình theo ứng dụng để tránh test dùng quy tắc serialization khác production.

Đoạn test minh họa việc đăng ký thành phần trong standalone builder. Nó không chứng minh cấu hình WebMvcConfigurer trong application context đã đúng. Muốn xác nhận cấu hình context, hãy dùng webAppContextSetup và đăng ký các bean qua cấu hình MVC.

## 9. Kết hợp các thành phần trong WebApplicationContext

Khi cần kiểm tra cách ứng dụng thật đăng ký các thành phần, cấu hình MVC có thể tập trung trong WebMvcConfigurer:

~~~java
@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = {
        OrderController.class,
        ApiExceptionHandler.class
})
class MvcTestConfig implements WebMvcConfigurer {

    @Bean
    LocalValidatorFactoryBean mvcValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Override
    public Validator getValidator() {
        return mvcValidator();
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new StringToOrderStatusConverter()
        );
    }
}
~~~

Nếu có converter HTTP tùy chỉnh, thêm qua extendMessageConverters để giữ các converter mặc định:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {

    converters.add(0, new CustomReportMessageConverter());
}
~~~

Test sử dụng context:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MvcTestConfig.class)
class OrderControllerWebMvcTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void usesMvcConfiguredConverterAndAdvice() throws Exception {
        mockMvc.perform(get("/orders").param("status", "paid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Trong ví dụ này:

- Component scan đăng ký controller và advice thành bean.
- addFormatters thêm converter vào conversion service của MVC.
- getValidator cung cấp validator cho MVC infrastructure.
- Converter HTTP tùy chỉnh được bổ sung qua extendMessageConverters.
- webAppContextSetup sử dụng các thành phần đã cấu hình trong context.

@EnableWebMvc bật cấu hình Spring MVC. Nếu ứng dụng dùng Spring Boot, auto-configuration có thể chịu trách nhiệm cho MVC infrastructure; không nên thêm @EnableWebMvc một cách tùy tiện vì annotation này chuyển ứng dụng sang cấu hình MVC tường minh và có thể làm thay đổi một số hành vi auto-configuration. Với test slice Spring Boot như @WebMvcTest, cần xem các bean và cấu hình nào được đưa vào slice thay vì mặc định rằng toàn bộ application context đã được nạp.

## 10. Các lỗi thường gặp khi đăng ký

### Advice không xử lý exception

Kiểm tra:

- Standalone builder đã gọi setControllerAdvice chưa?
- Advice đã là bean trong WebApplicationContext chưa?
- Component scan có bao phủ package của advice không?
- Selector của advice có loại controller đang test ra ngoài không?
- Có controller-level handler hoặc advice có thứ tự cao hơn xử lý exception trước không?
- Exception thực tế có đúng kiểu hoặc quan hệ cause như handler khai báo không?

Nếu response vẫn là HTTP 500, hãy xem exception gốc và các HandlerExceptionResolver tham gia xử lý.

### Converter tùy chỉnh không được gọi

Xác định dữ liệu đang được chuyển đổi ở lớp nào:

- JSON body: kiểm tra HttpMessageConverter.
- Query parameter, path variable hoặc form field: kiểm tra ConversionService, Converter hoặc Formatter.

Sau đó kiểm tra converter đã được đăng ký đúng builder/context chưa và kiểu nguồn, kiểu đích có khớp với handler method không.

### Converter JSON bị thiếu sau khi cấu hình

Trong standalone mode, setMessageConverters nhận danh sách converter do test cung cấp. Nếu chỉ thêm converter tùy chỉnh, các converter mặc định có thể không còn trong danh sách. Hãy cung cấp đầy đủ converter cần thiết hoặc chuyển sang webAppContextSetup để sử dụng MVC configuration.

Trong WebMvcConfigurer, dùng extendMessageConverters khi cần bổ sung mà vẫn giữ danh sách mặc định.

### Validator không chạy

Kiểm tra:

- DTO có annotation validation phù hợp không?
- Handler parameter có @Valid hoặc @Validated khi cần không?
- Bean Validation provider có trên classpath không?
- Standalone builder đã gọi setValidator chưa?
- MVC context có validator phù hợp không?
- Request body có deserialize thành công trước khi validation bắt đầu không?

Nếu JSON sai định dạng hoặc không deserialize được, lỗi có thể xảy ra trước bước Bean Validation.

### Test nhận status code đúng nhưng response body sai

Một status code đúng không bảo đảm response body đúng hợp đồng. Hãy xác nhận thêm content type, các trường JSON quan trọng và mã lỗi ổn định. Tránh chỉ so sánh toàn bộ JSON nếu thứ tự thuộc tính không phải một phần của hợp đồng.

### Test standalone thành công nhưng ứng dụng thật thất bại

Standalone setup chỉ dùng cấu hình được truyền vào builder và các mặc định của nó. Nó không tự động phản ánh mọi WebMvcConfigurer, bean advice, validator hoặc converter trong ứng dụng. Khi lỗi chỉ xuất hiện ở môi trường tích hợp, tạo một test webAppContextSetup để kiểm tra cấu hình MVC thực tế.

## 11. Cách chọn phạm vi kiểm thử

Có thể chia test theo mục tiêu:

| Mục tiêu | Thiết lập phù hợp | Thành phần cần xác nhận |
|---|---|---|
| Một controller xử lý lỗi nghiệp vụ | standaloneSetup | ControllerAdvice và response error |
| Binding query/path parameter | standaloneSetup hoặc webAppContextSetup | Converter/Formatter |
| JSON request/response | Cả hai | HttpMessageConverter |
| Bean Validation của request DTO | Cả hai | Validator và @Valid |
| Cấu hình MVC của ứng dụng | webAppContextSetup | Advice, converters, conversion service và validator đã đăng ký trong context |
| Tương tác nhiều controller và cấu hình MVC | webAppContextSetup | Luồng request qua MVC infrastructure |

Không nhất thiết mọi test controller đều phải khởi động toàn bộ application context. Test nhỏ giúp xác định hành vi cụ thể; test tích hợp context xác nhận các thành phần được kết nối đúng trong cấu hình ứng dụng.

Khi có nhiều test dùng chung cấu hình standalone, có thể tạo factory hoặc cấu hình test dùng chung cho nhóm controller tương tự. Tuy nhiên, cần giữ rõ các thành phần được đăng ký để người đọc biết test đang mô phỏng cấu hình nào.

## 12. Nguyên tắc thực hành

1. Phân biệt HttpMessageConverter với Converter và Formatter trước khi cấu hình.
2. Với standaloneSetup, đăng ký tường minh advice, message converter, conversion service và validator mà test cần.
3. Với webAppContextSetup, để Spring context quản lý các thành phần MVC và kiểm tra đúng cấu hình ứng dụng.
4. Dùng extendMessageConverters khi muốn thêm converter mà vẫn giữ danh sách mặc định.
5. Dùng addFormatters để đăng ký converter/formatter phục vụ data binding.
6. Dùng getValidator hoặc setValidator theo kiểu thiết lập MockMvc đang sử dụng.
7. Dùng @Valid hoặc @Validated đúng vị trí để yêu cầu validation.
8. Kiểm tra request và response qua MockMvc để chứng minh các thành phần thực sự tham gia xử lý.
9. Kiểm tra status, content type và các trường response quan trọng, nhất là khi advice chuẩn hóa lỗi.
10. Không suy luận rằng standalone test đã xác nhận toàn bộ cấu hình MVC trong application context.

Một bài kiểm thử MockMvc đáng tin cậy phải tạo được request đi qua đúng các thành phần mà phạm vi test muốn xác nhận. ControllerAdvice quyết định cách lỗi trở thành HTTP response; converter quyết định cách dữ liệu đi qua ranh giới HTTP và kiểu Java; validator bảo đảm dữ liệu đáp ứng quy tắc trước khi nghiệp vụ được thực thi. Đăng ký đúng ba nhóm thành phần này giúp test phản ánh rõ hành vi thực tế của Spring MVC và phát hiện lỗi cấu hình ngay trong quá trình phát triển.

