# standaloneSetup với controller được chọn

Khi kiểm thử một controller Spring MVC, đôi khi ta chỉ muốn tập trung vào một hoặc một vài controller cụ thể. Ta cần gửi request qua cơ chế xử lý MVC để kiểm tra URL mapping, binding tham số, chuyển đổi dữ liệu và response HTTP, nhưng không cần nạp toàn bộ cấu hình web của ứng dụng. `MockMvcBuilders.standaloneSetup(...)` được thiết kế cho phạm vi đó.

`standaloneSetup` nhận các instance controller do bài kiểm thử cung cấp, tạo hạ tầng Spring MVC tối thiểu quanh chúng và trả về builder để cấu hình `MockMvc`. Controller vẫn được xử lý qua `DispatcherServlet` trong môi trường servlet giả lập. Vì vậy, test có thể kiểm tra hành vi HTTP ở tầng MVC mà không cần khởi động Tomcat, Jetty hoặc một server thật.

Điểm cần chủ động là các dependency và thành phần MVC nằm ngoài controller được chọn. Test tự tạo controller, cung cấp service giả hoặc dependency cần thiết, rồi đăng ký thêm `@ControllerAdvice`, converter, validator, interceptor hay filter nếu hành vi đang kiểm thử phụ thuộc vào chúng.

## 1. `standaloneSetup` giải quyết phạm vi kiểm thử nào?

Một controller Spring MVC có thể nhận request thông qua nhiều bước: Spring tìm handler phù hợp, chuyển đổi dữ liệu đầu vào, gọi phương thức controller, xử lý exception và chuyển kết quả thành HTTP response. Gọi trực tiếp phương thức Java chỉ kiểm tra logic bên trong controller; nó bỏ qua các bước HTTP và MVC này.

Ví dụ, lời gọi trực tiếp:

```java
ProductResponse response = controller.getById(42L);
```

không xác nhận rằng đường dẫn `/api/products/42` được ánh xạ đúng, `42` được bind vào `@PathVariable`, hoặc response được serialize thành JSON.

Với `standaloneSetup`, test gửi request qua `MockMvc`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .build();

mockMvc.perform(get("/api/products/42"))
        .andExpect(status().isOk());
```

Builder tạo một môi trường MVC tối thiểu dành cho các controller được truyền vào. Môi trường đó có các thành phần cần thiết để đăng ký handler, gọi controller và ghi nhận response. Các cấu hình ứng dụng không được tự động nạp chỉ vì controller có annotation Spring.

Phương pháp này phù hợp khi muốn:

- Kiểm tra một controller được chọn mà không phải khởi tạo toàn bộ application context.
- Kiểm tra request mapping, path variable, query parameter, header và request body.
- Kiểm tra status, response header, content type và JSON response.
- Kiểm tra cách controller xử lý exception, validation hoặc chuyển đổi dữ liệu khi ta cung cấp cấu hình tương ứng.
- Giữ test tập trung, chạy nhanh và ít phụ thuộc vào cấu hình toàn ứng dụng.

## 2. Tạo `MockMvc` từ một controller

Giả sử API có controller trả về thông tin sản phẩm. Controller phụ thuộc một service để lấy dữ liệu.

Khai báo kiểu dữ liệu trả về:

```java
public record ProductResponse(long id, String name) {
}
```

Khai báo service:

```java
public interface ProductService {
    ProductResponse findById(long id);
}
```

Controller sử dụng constructor injection:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public ProductResponse getById(@PathVariable long id) {
        return productService.findById(id);
    }
}
```

Trong test, ta tạo mock cho service rồi truyền mock đó vào constructor của controller. Sau đó truyền instance controller cho `standaloneSetup`.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class ProductControllerTest {

    @Mock
    private ProductService productService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        ProductController controller = new ProductController(productService);

        mockMvc = MockMvcBuilders
                .standaloneSetup(controller)
                .build();
    }

    @Test
    void shouldReturnProductAsJson() throws Exception {
        when(productService.findById(42L))
                .thenReturn(new ProductResponse(42L, "Mechanical Keyboard"));

        mockMvc.perform(get("/api/products/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Mechanical Keyboard"));

        verify(productService).findById(42L);
    }
}
```

Các bước trong test có ý nghĩa riêng:

1. `@ExtendWith(MockitoExtension.class)` khởi tạo và quản lý các mock của Mockito cho test JUnit Jupiter.
2. `@Mock ProductService` tạo dependency giả để test kiểm soát dữ liệu mà controller nhận được.
3. `new ProductController(productService)` tạo controller với dependency đã được cung cấp tường minh.
4. `standaloneSetup(controller)` đăng ký controller được chọn vào môi trường MVC độc lập.
5. `build()` tạo `MockMvc` để test thực hiện request.
6. `perform(get(...))` gửi request giả lập; các `andExpect(...)` kiểm tra HTTP response.
7. `verify(...)` xác nhận controller đã gọi service với đúng id.

`standaloneSetup` không component scan package và không tự tìm service để inject như một application context đầy đủ. Vì vậy, constructor injection là cách thuận tiện để tạo controller với dependency rõ ràng. Nếu controller dùng field injection hoặc setter injection, test phải cung cấp các giá trị đó theo cách phù hợp trước khi đưa instance vào builder; không nên giả định builder sẽ thực hiện toàn bộ quá trình autowire của ứng dụng.

## 3. Chọn một hoặc nhiều controller

Tên phương thức `standaloneSetup` thể hiện rõ cách sử dụng: truyền vào controller nào thì môi trường MVC của test đăng ký controller đó.

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(productController)
        .build();
```

Có thể truyền nhiều controller khi một bài test cần xác nhận các endpoint thuộc một nhóm nhỏ:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(productController, categoryController)
        .build();
```

Các controller này cùng được đăng ký trong môi trường MVC do builder tạo. Cần bảo đảm mapping của chúng không xung đột ngoài ý muốn. Nếu hai controller cùng khai báo một HTTP method và một đường dẫn có thể khớp với cùng request, việc đăng ký handler có thể gây lỗi mapping mơ hồ hoặc khiến test không thể khởi tạo.

Việc chọn controller cũng giúp giới hạn trách nhiệm của test. Chẳng hạn, test `ProductController` có thể kiểm tra `/api/products/{id}` mà không phải nạp controller quản lý người dùng, cấu hình bảo mật, repository hoặc datasource của ứng dụng. Những dependency mà controller đang kiểm thử thực sự sử dụng vẫn cần được cung cấp, thường dưới dạng mock hoặc fake.

## 4. Kiểm tra nhiều dạng request và response

`MockMvc` cung cấp các request builder và result matcher để kiểm tra hợp đồng HTTP. `standaloneSetup` vẫn dùng các quy tắc Spring MVC cho controller đã đăng ký, vì vậy có thể kiểm tra binding và serialization thay vì chỉ gọi phương thức Java.

### Path variable và query parameter

Với endpoint:

```java
@GetMapping
public List<ProductResponse> search(@RequestParam String keyword) {
    return productService.search(keyword);
}

@GetMapping("/{id}")
public ProductResponse getById(@PathVariable long id) {
    return productService.findById(id);
}
```

Test có thể gửi query parameter hoặc path variable:

```java
mockMvc.perform(get("/api/products")
                .queryParam("keyword", "keyboard"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/products/{id}", 42L))
        .andExpect(status().isOk());
```

Spring MVC thực hiện binding chuỗi từ URL vào kiểu tham số tương ứng. Test có thể xác nhận cả trường hợp hợp lệ và không hợp lệ, ví dụ truyền một chuỗi không chuyển được thành `long`.

### Header và content negotiation

Request có thể khai báo `Accept` để yêu cầu kiểu response:

```java
mockMvc.perform(get("/api/products/{id}", 42L)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON));
```

Tương tự, khi gửi request body, dùng `contentType(...)` để khai báo định dạng đầu vào. Những assertion này giúp phát hiện trường hợp endpoint trả sai media type hoặc không có converter phù hợp.

### Request body

Với endpoint tạo sản phẩm:

```java
public record CreateProductRequest(String name) {
}

@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public ProductResponse create(@RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

Test gửi JSON:

```java
mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"Mechanical Keyboard"}
                        """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Mechanical Keyboard"));
```

Để đoạn test chạy được, môi trường test cần có JSON `HttpMessageConverter` tương ứng, thường là Jackson converter trong ứng dụng Spring Boot có dependency web mặc định. Nếu dự án không có converter đó hoặc đang dùng converter riêng, hãy đăng ký converter cần thiết trong builder.

## 5. Đăng ký `@ControllerAdvice` khi cần

`standaloneSetup` không tự tìm tất cả lớp `@ControllerAdvice` trong dự án. Nếu test muốn xác nhận cách ứng dụng xử lý exception toàn cục, hãy truyền advice cần thiết vào builder bằng `setControllerAdvice(...)`.

Ví dụ exception:

```java
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(long id) {
        super("Product " + id + " was not found");
    }
}
```

Advice chuyển exception thành response có status 404:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

public record ApiError(String message) {
}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ApiError handleProductNotFound(ProductNotFoundException exception) {
        return new ApiError(exception.getMessage());
    }
}
```

Đăng ký advice khi xây dựng `MockMvc`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new ApiExceptionHandler())
        .build();
```

Nếu service ném `ProductNotFoundException`, test có thể xác nhận response:

```java
when(productService.findById(404L))
        .thenThrow(new ProductNotFoundException(404L));

mockMvc.perform(get("/api/products/{id}", 404L))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.message").value("Product 404 was not found"));
```

Một controller cũng có thể tự khai báo `@ExceptionHandler` trong chính lớp đó. Các handler thuộc controller được chọn có thể được phát hiện khi đăng ký controller. Advice bên ngoài controller cần được cung cấp tường minh.

## 6. Bổ sung validator, converter và các thành phần MVC

Builder cung cấp các phương thức để tùy chỉnh hạ tầng MVC cho đúng hành vi mà test cần xác nhận. Chỉ nên bổ sung thành phần liên quan trực tiếp đến phạm vi kiểm thử; nếu phải sao chép gần như toàn bộ cấu hình ứng dụng vào test, đó là dấu hiệu cho thấy nên cân nhắc `webAppContextSetup` hoặc một test slice của Spring Boot.

### Validation

Nếu controller dùng `@Valid` trên request body, test cần một validator tương ứng và Bean Validation provider trên test runtime classpath.

```java
public record CreateProductRequest(
        @NotBlank String name
) {
}

@PostMapping
public ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

Có thể cung cấp `LocalValidatorFactoryBean`:

```java
LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
validator.afterPropertiesSet();

mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setValidator(validator)
        .build();
```

`LocalValidatorFactoryBean` triển khai giao diện validator của Spring và tích hợp với Bean Validation. Trong ví dụ thực tế, cần import `jakarta.validation.Valid`, `jakarta.validation.constraints.NotBlank` và `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`; dependency provider như Hibernate Validator cũng phải có mặt. Nếu không có provider, các constraint có thể không được thực thi như mong đợi.

### Message converter

Khi cần kiểm tra converter riêng, có thể đăng ký qua `setMessageConverters(...)`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setMessageConverters(new MappingJackson2HttpMessageConverter(objectMapper))
        .build();
```

`MappingJackson2HttpMessageConverter` sử dụng `ObjectMapper` được truyền vào. Điều này hữu ích khi ứng dụng cấu hình naming strategy, date format, module hoặc serialization rule riêng. Cần lưu ý rằng khi tự chỉ định danh sách converter, hãy cung cấp đầy đủ các converter mà endpoint trong test cần, chẳng hạn converter JSON hoặc converter cho định dạng khác.

### Conversion service và argument resolver

Controller có thể nhận kiểu dữ liệu tùy chỉnh trong path hoặc query parameter, hoặc sử dụng `HandlerMethodArgumentResolver` riêng. Builder cho phép cung cấp `FormattingConversionService` và custom argument resolver:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setConversionService(conversionService)
        .setCustomArgumentResolvers(customArgumentResolver)
        .build();
```

Hãy dùng cùng quy tắc chuyển đổi mà endpoint yêu cầu. Nếu không đăng ký formatter hoặc resolver tùy chỉnh, test standalone có thể thất bại dù ứng dụng thật đã cấu hình chúng trong `WebMvcConfigurer`.

### Interceptor và filter

Interceptor có thể được thêm bằng `addInterceptors(...)`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .addInterceptors(requestAuditInterceptor)
        .build();
```

Filter thuộc servlet filter chain và có thể được thêm bằng `addFilters(...)`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .addFilters(requestLoggingFilter)
        .build();
```

Đăng ký một filter hoặc interceptor cụ thể giúp kiểm tra tương tác của nó với controller. Tuy nhiên, việc thêm thủ công một thành phần không đồng nghĩa toàn bộ thứ tự filter, điều kiện đăng ký và cấu hình bảo mật của ứng dụng đã được kiểm tra. Nếu cần xác nhận chính xác filter chain thực tế, nên nạp cấu hình web của ứng dụng.

### View resolver và thành phần khác

Với controller trả về view name thay vì JSON, test có thể cần đăng ký `ViewResolver` phù hợp bằng builder. Tương tự, nếu kết quả phụ thuộc locale resolver, content negotiation manager, flash map manager hoặc cấu hình async, hãy cung cấp cấu hình tương ứng. Mục tiêu là làm rõ thành phần nào đang tham gia vào test để kết quả có thể giải thích và lặp lại.

## 7. Kiểm tra controller bất đồng bộ

Controller có thể trả về `Callable`, `DeferredResult` hoặc một kiểu kết quả bất đồng bộ khác. Trong trường hợp đó, request đầu tiên có thể kết thúc ở trạng thái async đã bắt đầu; test cần lấy `MvcResult` rồi dispatch kết quả bất đồng bộ để kiểm tra response cuối cùng.

```java
MvcResult result = mockMvc.perform(get("/api/products/async/42"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
```

Đoạn này cần static import `asyncDispatch` từ `MockMvcRequestBuilders`, `asyncStarted` từ `MockMvcResultMatchers.request` và kiểu `MvcResult`. Nếu controller dùng executor hoặc timeout tùy chỉnh, builder có thể cấu hình async request timeout phù hợp. Test cũng cần tránh phụ thuộc vào thời gian thực thi ngẫu nhiên của tác vụ nền.

## 8. `standaloneSetup` khác gì với `webAppContextSetup` và `@WebMvcTest`?

Ba cách tạo test có mục tiêu gần nhau nhưng mức cấu hình được nạp khác nhau.

| Cách kiểm thử | Nguồn controller và cấu hình | Phù hợp khi |
| --- | --- | --- |
| `standaloneSetup(controller)` | Controller instance được truyền trực tiếp; hạ tầng MVC tối thiểu do builder tạo; các collaborator bổ sung được đăng ký tường minh. | Tập trung vào một controller hoặc một nhóm nhỏ controller. |
| `webAppContextSetup(wac)` | `WebApplicationContext` đã nạp cùng cấu hình MVC và bean của ứng dụng. | Cần kiểm tra sự phối hợp của controller với cấu hình web thực tế. |
| `@WebMvcTest` | Spring Boot tạo MVC test slice và chọn các thành phần web phù hợp. | Dự án dùng Spring Boot và muốn test controller trong slice do Boot cấu hình. |

Với `standaloneSetup`, controller được tạo trực tiếp, dependency được truyền vào tường minh và các thành phần ngoài phạm vi mặc định phải được thêm khi cần. Với `webAppContextSetup`, test sử dụng context đã được cấu hình, vì vậy component scan, MVC config, advice và các bean tương ứng có thể tham gia theo cấu hình đó. `@WebMvcTest` là lựa chọn tiện lợi của Spring Boot để tạo MVC slice; nó vẫn là một Spring test context và có cơ chế chọn bean riêng.

`standaloneSetup` không phải kiểm thử đơn vị thuần túy vì request vẫn đi qua Spring MVC và `DispatcherServlet` giả lập. Nó cũng không phải kiểm thử tích hợp toàn ứng dụng vì không nạp tự động cấu hình và bean của toàn bộ ứng dụng.

## 9. Những điều test standalone xác nhận được và giới hạn của nó

Một test dùng `standaloneSetup` có thể xác nhận:

- Mapping của controller được chọn với HTTP method và URL.
- Spring bind path variable, query parameter, header và request body.
- Controller nhận đúng dữ liệu đã bind và gọi dependency với tham số mong đợi.
- Response status, header, content type và body được tạo đúng.
- Validation, exception handler, converter, interceptor hoặc filter đã được đăng ký cho test hoạt động đúng trong phạm vi cấu hình đó.

Test không tự xác nhận:

- Component scan của ứng dụng có tìm thấy controller trong runtime hay không.
- Các bean được inject và cấu hình đúng trong application context thật.
- `WebMvcConfigurer`, `@ControllerAdvice`, filter hoặc security chain của ứng dụng đã được đăng ký đầy đủ và theo đúng thứ tự thực tế, trừ khi test tự cấu hình những thành phần ấy.
- Cấu hình datasource, transaction, repository hoặc tích hợp với hệ thống ngoài hoạt động đúng.
- Server thật có khởi động, bind port và nhận request qua mạng thành công hay không.

Ranh giới này rất quan trọng khi diễn giải kết quả. Một test standalone thành công cho biết controller cùng hạ tầng MVC đã dựng cho test xử lý request đúng. Nó không chứng minh ứng dụng production đã nạp cùng controller hoặc cùng cấu hình đó.

## 10. Lỗi thường gặp

**Truyền class thay vì instance controller.**

`standaloneSetup` nhận controller instance. Hãy tạo controller với dependency cần thiết rồi truyền instance vào builder.

**Quên cung cấp dependency của controller.**

Nếu controller dùng constructor injection, hãy tạo mock hoặc fake cho dependency và truyền vào constructor. Một controller được tạo bằng `new` không tự nhận service từ Spring application context.

**Cho rằng component scan vẫn được chạy.**

Builder đăng ký controller được chỉ định. Các controller khác trong package không tự động được phát hiện. Nếu request đến controller chưa đăng ký, mapping sẽ không tồn tại trong môi trường test.

**Không đăng ký `@ControllerAdvice`.**

Advice toàn cục không tự động được quét từ dự án. Truyền advice qua `setControllerAdvice(...)` nếu test cần kiểm tra exception handling đó.

**Thiếu converter hoặc validator.**

Request JSON, response JSON hoặc `@Valid` có thể không hoạt động như mong đợi nếu dependency hoặc cấu hình cần thiết không có trong test. Kiểm tra test runtime classpath và đăng ký converter/validator phù hợp.

**Test đang sao chép quá nhiều cấu hình của ứng dụng.**

Nếu phải đăng ký nhiều converter, resolver, interceptor, filter và bean để tái tạo gần như toàn bộ MVC config, test có thể không còn lợi ích về phạm vi nhỏ. Cân nhắc dùng `webAppContextSetup` hoặc `@WebMvcTest` để kiểm tra cấu hình đã được khai báo tại nguồn.

**Nhầm `MockMvc` với HTTP server thật.**

`MockMvc` thực hiện request trong môi trường servlet giả lập. Nó không mở cổng TCP và không kiểm tra mạng, reverse proxy hoặc cấu hình server. Dùng kiểm thử với server thật khi các yếu tố đó thuộc mục tiêu cần xác nhận.

## 11. Quy trình xây dựng test với controller được chọn

Một quy trình thực tế có thể thực hiện theo thứ tự sau:

1. Xác định controller và endpoint cần kiểm thử; chỉ chọn những controller có liên quan trực tiếp.
2. Tạo mock hoặc fake cho dependency của controller.
3. Khởi tạo controller bằng constructor hoặc factory của test.
4. Gọi `MockMvcBuilders.standaloneSetup(controller)` để tạo builder.
5. Đăng ký advice, validator, converter, resolver, interceptor hoặc filter nếu hành vi đang kiểm tra cần chúng.
6. Gọi `build()` để tạo `MockMvc`.
7. Gửi request đại diện cho tình huống cần kiểm thử.
8. Kiểm tra status, header, body và lời gọi dependency.
9. Khi cần xác nhận cấu hình MVC thật của ứng dụng, chuyển sang test dùng `WebApplicationContext` hoặc MVC slice của Spring Boot.

Ví dụ khởi tạo tối giản:

```java
ProductController controller = new ProductController(productService);

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new ApiExceptionHandler())
        .build();
```

Ví dụ này thể hiện rõ hai quyết định của test: controller nào được kiểm thử và advice nào được đưa vào môi trường MVC. Các quyết định cấu hình còn lại có thể bổ sung theo nhu cầu của endpoint.

## Kết luận

`MockMvcBuilders.standaloneSetup(...)` tạo `MockMvc` quanh một hoặc nhiều controller instance được chọn. Đây là cách phù hợp để kiểm tra hành vi HTTP và MVC của controller trong phạm vi nhỏ, với dependency và thành phần mở rộng được cung cấp tường minh.

Test standalone có thể kiểm tra mapping, binding, serialization, response và cách controller phối hợp với các collaborator đã đăng ký. Khi mục tiêu chuyển sang xác nhận component scan, wiring bean hoặc toàn bộ MVC configuration của ứng dụng, hãy dùng `webAppContextSetup` hoặc test slice phù hợp để kiểm tra chính context đó.
