# @WebMvcTest và phạm vi Controller, advice, converter, filter trong Spring Boot

## 1. Mục tiêu: kiểm thử tầng Spring MVC mà không nạp cả ứng dụng

Khi xây dựng REST API bằng Spring Boot, controller chịu trách nhiệm nhận HTTP request, ánh xạ URL và tham số, đọc JSON request body, kích hoạt validation, gọi một service, rồi tạo HTTP status/headers/JSON response. Những hành vi đó có thể sai **ngay cả khi unit test của service đã xanh**: ví dụ sai `@PathVariable`, không chuyển đổi kiểu, quên `@Valid`, exception bị trả 500 thay vì 404, hoặc bộ lọc chặn request trước khi controller được gọi.

`@WebMvcTest` là **test slice** dành cho tầng Spring MVC. Thay vì khởi động toàn bộ ứng dụng, nó cấu hình một `ApplicationContext` tập trung vào các thành phần web cần để chạy controller qua `MockMvc`:

- Controller được chọn và các thành phần MVC liên quan.
- `@ControllerAdvice`/`@RestControllerAdvice` xử lý exception hay áp dụng xử lý chung.
- Chuyển đổi kiểu cho tham số request và JSON HTTP message converters theo cấu hình được nạp.
- Các `Filter`, `HandlerInterceptor`, `WebMvcConfigurer` và các thành phần web hỗ trợ khác tùy phạm vi quét/configuration.
- Infrastructure của Spring MVC, chẳng hạn `DispatcherServlet`, argument resolvers và validation khi có provider thích hợp.

**Giới hạn quan trọng:** `@WebMvcTest` không tự nạp các `@Service`, `@Repository` và toàn bộ business/data layer như một `@SpringBootTest`. Dependency của controller thường cần được thay bằng mock/fake hoặc được đăng ký rõ. Một test `@WebMvcTest` đạt chứng minh **HTTP contract/MVC path trong slice đã nạp**, không tự chứng minh SQL, database, transaction hay toàn bộ hệ thống chạy đúng.

## 2. Luồng xử lý một request trong MVC slice

Một request kiểm thử có thể đi qua các tầng:

```text
MockMvc.perform(GET /api/products/42)
        |
        v
Servlet Filter chain              <-- nếu đã được đăng ký vào MockMvc
        |
        v
DispatcherServlet
        |
        +--> HandlerMapping chọn @Controller/@GetMapping
        |
        +--> ArgumentResolver + Converter
        |      (path/query/header/body -> tham số Java)
        |
        +--> Validation (nếu @Valid, provider tương ứng)
        |
        +--> ProductController thật
        |         |
        |         +--> ProductService mock (nếu thay bean)
        |
        +--> @ControllerAdvice nếu có exception
        |
        +--> HttpMessageConverter (Java object <-> JSON)
        |
        v
HTTP status + headers + response body
```

Sơ đồ mô tả các giai đoạn có thể xảy ra, **không phải cam kết một filter/interceptor cụ thể luôn được nạp**. Ví dụ, filter chỉ tham gia nếu có bean/filter registration được tìm thấy và `MockMvc` được cấu hình sử dụng nó. Security filter có thể dừng request trước controller, còn `@ExceptionHandler` chỉ xử lý những exception mà cấu hình cho phép.

Trong bài test, cần phân biệt ba kết quả:

1. **Request được dispatch thành công:** URL, HTTP method và tham số tới đúng handler.
2. **Controller contract đúng:** status, header, JSON, validation và mapping exception đúng.
3. **Phụ thuộc được gọi đúng:** dùng Mockito `verify(...)` để xác nhận controller chuyển đúng đầu vào cho service mock.

Cả ba **không tự động chứng minh business service thật đã chạy**, bởi mock có thể trả dữ liệu được lập trình qua `when(...).thenReturn(...)`.

## 3. @WebMvcTest chọn bean nào?

Khai báo thường gặp:

```java
@WebMvcTest(controllers = ProductController.class)
class ProductControllerWebMvcTest {
    // @Autowired MockMvc ...
}
```

Đoạn này là mẫu khai báo: `ProductController` phải tồn tại và test có dependency Spring Boot test tương ứng. Chỉ định `controllers` giúp hạn chế **controller được chọn** thay vì quét tất cả controller; nó không có nghĩa context chỉ chứa đúng một bean. Infrastructure và các thành phần web được phép qua filter của slice vẫn có thể có mặt.

### 3.1. Những thành phần thường nằm trong web slice

| Thành phần | Vai trò | Lưu ý về phạm vi |
|---|---|---|
| `@Controller`, `@RestController` | Mapping HTTP tới handler method | Có thể giới hạn bằng `controllers = ...` |
| `@ControllerAdvice`, `@RestControllerAdvice` | `@ExceptionHandler`, xử lý và áp dụng quy tắc chung | Advice liên quan có thể được tìm thấy cả khi chọn một controller |
| `Converter`, `GenericConverter` | Chuyển đổi chuỗi request, path/query parameter sang kiểu Java | Phải được đăng ký vào `ConversionService` mà MVC sử dụng |
| `HttpMessageConverter` | Đọc/ghi body, ví dụ JSON qua Jackson | Phụ thuộc classpath và cấu hình Boot/MVC đang nạp |
| `@JsonComponent` | Serializer/deserializer Jackson tùy biến | Chỉ áp dụng nếu component được tìm thấy/đăng ký trong slice |
| `Filter`, `FilterRegistrationBean` | Logic Servlet trước/sau DispatcherServlet | Cần phân biệt bean trong context và filter thực sự được gắn vào MockMvc |
| `HandlerInterceptor` | Trước/sau controller handler | Đăng ký qua MVC config thích hợp |
| `HandlerMethodArgumentResolver` | Gán một tham số controller theo quy tắc tùy biến | Có thể cần `WebMvcConfigurer`/registration |
| `WebMvcConfigurer` | Tùy chỉnh formatters, converters, interceptors, CORS... | Chỉ cấu hình được tải mới có hiệu lực |
| `SecurityFilterChain` nếu Spring Security hiện diện | Xác thực/ủy quyền HTTP | Có thể làm request trả 401/403 trước controller |

Đây là **các loại thành phần mà Spring Boot MVC slice có thể giữ lại**, không phải danh sách chắc chắn mọi bean đều xuất hiện trong mọi dự án và mọi phiên bản. Các điều kiện như component scan, exclude/include filters, `@Import`, test configuration, classpath và auto-configuration quyết định context cuối cùng.

### 3.2. Những phần không mặc định thuộc web slice

- `@Service`, `@Repository` và các `@Component` nghiệp vụ không nằm trong nhóm được giữ lại.
- JPA `EntityManager`, transaction manager, DataSource và repository thực không mặc nhiên được nạp chỉ vì controller tham chiếu tới chúng.
- HTTP server socket thật **không** được khởi động cho `MockMvc`; dispatch diễn ra trong ứng dụng test.
- Toàn bộ `@SpringBootApplication` cùng business configuration không được nạp như một full application context.
- Hành vi của external HTTP service, database, message broker và file storage không được kiểm chứng nếu đã bị thay bằng mock.

Nếu controller constructor cần `ProductService` nhưng slice không có bean đó, Spring có thể báo `UnsatisfiedDependencyException` hoặc `NoSuchBeanDefinitionException` và test thất bại **trước khi vào phương thức `@Test`**. Cách giải quyết thường là khai báo mock/fake tương ứng, không phải chuyển tất cả web tests sang `@SpringBootTest` theo phản xạ.

## 4. Chọn @MockitoBean, @MockBean hoặc fake đúng phiên bản

Trong **Spring Boot 3.4+ cùng Spring Framework 6.2+**, có thể dùng:

```java
@MockitoBean
ProductService products;
```

Import: `org.springframework.test.context.bean.override.mockito.MockitoBean`.

Annotation tạo/thay một bean bằng Mockito mock trong **Spring TestContext**, để controller thật nhận nó qua Dependency Injection. Test định nghĩa kết quả dịch vụ bằng `when(...)` và kiểm tra controller đã gọi bằng `verify(...)`.

Phân biệt:

| Cách tạo giả lập | Có được controller Spring inject tự động không? | Phù hợp |
|---|---|---|
| `@Mock` trong một JUnit Mockito unit test | **Không tự động** trong Spring context | Tạo controller bằng `new Controller(mockService)` và test thuần Java |
| `@MockitoBean` | Có, qua cơ chế bean override của Spring TestContext | `@WebMvcTest`/Spring context test trên version hỗ trợ |
| `@MockBean` cũ của Spring Boot | Có trong các phiên bản Boot tương ứng | Dự án Boot cũ; ở Boot 3.4 đã bị đánh dấu deprecated |
| `@TestConfiguration` + `@Bean` fake service | Có nếu cấu hình được nạp | Fake có state hoặc hành vi tùy biến, không cần Mockito |

Không trộn import `@MockitoBean` của Spring Framework mới vào một dự án Boot cũ không có annotation đó. Ví dụ runnable bên dưới **chủ đích nhắm Spring Boot 3.4/3.5 với Java 17+**; với phiên bản khác cần đối chiếu API và tọa độ dependency. Nếu có nhiều implementation cùng kiểu, cần dùng tên bean/qualifier rõ ràng; mock nhầm bean có thể gây test không đi qua dependency mong muốn.

**Không mock chính controller khi kiểm tra MVC mapping.** Khi controller là mock, code annotation/handler thực chưa chắc còn được thực thi như dự kiến; mục tiêu MVC slice là giữ controller thật, giả lập các phụ thuộc nghiệp vụ phía sau.

## 5. Ví dụ Java 17+ hoàn chỉnh: Controller + Advice + Converter + Filter

### 5.1. Hợp đồng API cần bảo vệ

Một API quản lý sản phẩm cung cấp:

- `GET /api/products/{id}` trả `200` và JSON sản phẩm nếu tồn tại.
- Khi service báo không tìm thấy, `@RestControllerAdvice` trả `404` cùng JSON `{"code":"PRODUCT_NOT_FOUND"}`.
- `GET /api/products/sku/{code}` nhận SKU ở path; `Converter<String, Sku>` chuẩn hóa chữ hoa trước khi gọi service.
- `POST /api/products` nhận JSON `{"name":"Keyboard","price":75000}`, yêu cầu tên không trống và giá dương, trả `201` với JSON sản phẩm được tạo.
- JSON không hợp lệ về dữ liệu (`name` trống/`price <= 0`) phải trả `400`; service không được gọi.
- Một `Filter` của MVC slice thêm response header `X-Slice-Filter: applied` để test xác nhận filter thực sự chạy.

Ví dụ dùng `spring-boot-starter-web`, `spring-boot-starter-validation` và `spring-boot-starter-test`. **Không đưa Spring Security starter vào ví dụ tối giản**: nếu dependency security được thêm, cần xác thực/CSRF/filter chain đúng cách (mục 9); nếu không, những request vô danh có thể bị chặn trước controller.

### 5.2. Cấu hình phụ thuộc test

Đoạn Gradle Groovy DSL minh họa trong một dự án đã có Spring Boot plugin, dependency management, Java 17+ và Maven Central:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.4/3.5 sử dụng `jakarta.validation` và `jakarta.servlet`; đừng dùng nhầm `javax.validation`/`javax.servlet` của các thế hệ cũ. Ví dụ dùng `@MockitoBean` nên cần Spring Framework 6.2+.

Cấu trúc source:

```text
src/main/java/com/example/webslice/
    WebSliceDemoApplication.java
    ProductController.java
    ProductService.java
    ProductView.java
    CreateProductRequest.java
    Sku.java
    SkuConverter.java
    ProductNotFoundException.java
    ApiExceptionAdvice.java
    SliceMarkerFilter.java

src/test/java/com/example/webslice/
    ProductControllerWebMvcTest.java
```

### 5.3. Spring Boot application class

Tệp `src/main/java/com/example/webslice/WebSliceDemoApplication.java`:

```java
package com.example.webslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSliceDemoApplication.class, args);
    }
}
```

Lớp này giúp Spring Boot tìm package base cho component scan. **`@WebMvcTest` vẫn giới hạn slice**, không tự dùng toàn bộ cơ chế quét bean như khi chạy application thật.

### 5.4. DTO, contract service và exception nghiệp vụ

Tệp `src/main/java/com/example/webslice/ProductView.java`:

```java
package com.example.webslice;

public record ProductView(long id, String name, int price) {}
```

Tệp `src/main/java/com/example/webslice/CreateProductRequest.java`:

```java
package com.example.webslice;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive int price) {}
```

Tệp `src/main/java/com/example/webslice/ProductService.java`:

```java
package com.example.webslice;

public interface ProductService {
    ProductView findById(long id);
    ProductView findBySku(String sku);
    ProductView create(CreateProductRequest request);
}
```

Tệp `src/main/java/com/example/webslice/ProductNotFoundException.java`:

```java
package com.example.webslice;

public final class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(String message) {
        super(message);
    }
}
```

Đây là các kiểu dữ liệu **thật**, không mock. ProductService chỉ có contract; trong web slice nó được thay bằng `@MockitoBean`. Record tạo `equals` theo nội dung, hữu ích khi dùng `verify(products).create(new CreateProductRequest(...))`.

### 5.5. Kiểu SKU và Converter dành cho @PathVariable

Tệp `src/main/java/com/example/webslice/Sku.java`:

```java
package com.example.webslice;

public record Sku(String value) {}
```

Tệp `src/main/java/com/example/webslice/SkuConverter.java`:

```java
package com.example.webslice;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class SkuConverter implements Converter<String, Sku> {

    @Override
    public Sku convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("SKU is blank");
        }
        return new Sku(source.trim().toUpperCase(Locale.ROOT));
    }
}
```

`Converter<String, Sku>` phục vụ **conversion service** khi MVC gán chuỗi path/query parameter vào kiểu `Sku`. Nó không phải Jackson `HttpMessageConverter`, không chịu trách nhiệm parse JSON body.

Trong ví dụ, converter là component thuộc nhóm web-related có thể được MVC slice tìm thấy và đăng ký. Nếu dự án áp dụng quy tắc scan khác hoặc cần custom converter nằm ngoài package base, phải thêm `@Import(SkuConverter.class)` hoặc `WebMvcConfigurer#addFormatters` phù hợp rồi xác minh test thực sự dùng converter đó. Không khẳng định mọi `@Component` bất kỳ đều được quét trong `@WebMvcTest`.

### 5.6. Controller thật

Tệp `src/main/java/com/example/webslice/ProductController.java`:

```java
package com.example.webslice;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService products;

    public ProductController(ProductService products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    public ProductView findById(@PathVariable("id") long id) {
        return products.findById(id);
    }

    @GetMapping("/sku/{code}")
    public ProductView findBySku(@PathVariable("code") Sku sku) {
        return products.findBySku(sku.value());
    }

    @PostMapping
    public ResponseEntity<ProductView> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductView created = products.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Phân biệt:
- `@GetMapping("/{id}")` đọc path segment và chuyển thành `long`.
- `@GetMapping("/sku/{code}")` chuyển path segment sang `Sku`, sau đó controller truyền `sku.value()` cho service.
- `@Valid @RequestBody` kích hoạt Bean Validation **khi đã có validation provider** và request object được binding thành công; không đơn thuần chỉ vì có annotation.
- `ResponseEntity.status(CREATED)` yêu cầu `201`; các trường của ProductView được HTTP message converter phù hợp (thường Jackson JSON) serialize thành response body.

Không có `@Service` implementation trong ví dụ: `ProductService` là interface, `@MockitoBean` sẽ cung cấp mock bean cho controller ở test context.

### 5.7. Controller advice: 404 và lỗi validation 400

Tệp `src/main/java/com/example/webslice/ApiExceptionAdvice.java`:

```java
package com.example.webslice;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(
            MethodArgumentNotValidException exception) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_REQUEST"));
    }
}
```

`@RestControllerAdvice` là `@ControllerAdvice` kết hợp `@ResponseBody`. Nó giúp tập trung phản hồi lỗi. Trong ví dụ, JSON error chỉ chứa `code` để test có hợp đồng rõ; ứng dụng thật có thể cần `message`, chi tiết field validation, trace ID hoặc Problem Details.

`@WebMvcTest(ProductController.class)` có thể tự nạp các `@ControllerAdvice` thuộc phạm vi quét web, **kể cả advice dùng chung của ứng dụng**. Vì vậy, một advice toàn cục không liên quan có thể làm test context phát sinh dependency hoặc mapping conflict. Nếu advice đang cần nằm ngoài phạm vi quét, `@Import(ApiExceptionAdvice.class)` là một cách đăng ký tường minh.

Không viết test chỉ gọi trực tiếp `new ApiExceptionAdvice().notFound(...)` rồi kết luận Spring MVC đã map exception đúng; bài test cần đi qua `MockMvc` để kiểm tra `@ExceptionHandler` thực sự được dùng.

### 5.8. Filter: quan sát một response header từ Servlet chain

Tệp `src/main/java/com/example/webslice/SliceMarkerFilter.java`:

```java
package com.example.webslice;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class SliceMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        response.setHeader("X-Slice-Filter", "applied");
        filterChain.doFilter(request, response);
    }
}
```

`OncePerRequestFilter` là lớp nền Servlet filter tiện dụng của Spring. Một filter được tìm thấy trong MVC slice có thể được auto-registered vào MockMvc. Ví dụ **giữ filters được bật** (cấu hình mặc định của `@AutoConfigureMockMvc`) và assert header trên response, vì có bean filter trong context **chưa đủ** để chứng minh filter đã chạy trong đường `MockMvc.perform`.

Cũng lưu ý: filter có thể thay status, ghi response, yêu cầu token hoặc gọi dependency bên ngoài. Nếu test chỉ muốn mapping controller, đôi khi cần kiểm soát chúng; nhưng vô hiệu hóa toàn bộ filter chain là thay đổi phạm vi bằng chứng, không nên che giấu trong test bảo vệ security.

### 5.9. Test đầy đủ với MockMvc và service mock

Tệp `src/test/java/com/example/webslice/ProductControllerWebMvcTest.java`:

```java
package com.example.webslice;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = ProductController.class)
class ProductControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService products;

    @Test
    void getUsesJsonMessageConverterAndRunsFilter() throws Exception {
        when(products.findById(41L)).thenReturn(
                new ProductView(41L, "Mouse", 125_000));

        mvc.perform(get("/api/products/41")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Slice-Filter", "applied"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.name").value("Mouse"))
                .andExpect(jsonPath("$.price").value(125_000));

        verify(products).findById(41L);
    }

    @Test
    void customPathVariableConverterNormalizesSku() throws Exception {
        when(products.findBySku("AB-7")).thenReturn(
                new ProductView(7L, "Adapter", 19_000));

        mvc.perform(get("/api/products/sku/ab-7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.name").value("Adapter"));

        verify(products).findBySku("AB-7");
    }

    @Test
    void adviceMapsDomainExceptionTo404() throws Exception {
        when(products.findById(404L)).thenThrow(
                new ProductNotFoundException("missing product"));

        mvc.perform(get("/api/products/404"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(
                        "PRODUCT_NOT_FOUND"));

        verify(products).findById(404L);
    }

    @Test
    void invalidBodyReturns400BeforeServiceCall() throws Exception {
        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","price":0}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        verifyNoInteractions(products);
    }

    @Test
    void postDeserializesJsonAndReturnsCreatedDto() throws Exception {
        when(products.create(any(CreateProductRequest.class)))
                .thenReturn(new ProductView(
                        72L, "Keyboard", 75_000));

        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Keyboard","price":75000}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(72))
                .andExpect(jsonPath("$.name").value("Keyboard"))
                .andExpect(jsonPath("$.price").value(75_000));

        verify(products).create(
                new CreateProductRequest("Keyboard", 75_000));
    }
}
```

### 5.10. Các assertion minh chứng điều gì?

| Test method | Hành vi thực được kiểm tra | Điều chưa được chứng minh |
|---|---|---|
| `getUsesJsonMessageConverterAndRunsFilter` | GET mapping, serialize JSON, content type và Filter được thực thi | Service thật truy vấn database đúng |
| `customPathVariableConverterNormalizesSku` | MVC chuyển `ab-7` thành `AB-7` trước khi gọi service | Tìm sản phẩm theo SKU thật đúng |
| `adviceMapsDomainExceptionTo404` | Exception từ mock service đi qua advice, tạo status và JSON 404 | Ngoại lệ từ repository thật có đúng loại hay không |
| `invalidBodyReturns400BeforeServiceCall` | JSON body được bind, Bean Validation từ chối dữ liệu và advice trả 400 | Database constraint hoặc validation ở service thật |
| `postDeserializesJsonAndReturnsCreatedDto` | Request JSON → record, service invocation, HTTP 201 và response JSON | Giao dịch tạo sản phẩm đã commit |

Ở cấu hình nêu trên (Spring Boot 3.4/3.5, Spring MVC Servlet stack, validation provider/Jackson trên classpath, không có security starter và các component cùng package được quét), **năm test được thiết kế để đạt**. Không có `System.out.println` nên không đưa stdout giả; để kết luận thực tế phải chạy lớp test và đọc report.

**Quan trọng:** `@WebMvcTest` không khởi động embedded HTTP server để nghe cổng thật. `MockMvc` đưa request giả lập qua Spring MVC infrastructure **trong process test**, nên đây là MVC slice test, không phải end-to-end HTTP network test.

### 5.11. Lệnh chạy test

Gradle (Linux/macOS):

```bash
./gradlew test --tests "com.example.webslice.ProductControllerWebMvcTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.webslice.ProductControllerWebMvcTest"
```

Maven (Linux/macOS):

```bash
./mvnw -Dtest=ProductControllerWebMvcTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=ProductControllerWebMvcTest test
```

Dùng đúng wrapper của dự án và bảo đảm build đã có Spring Boot plugin/dependency management, JUnit Jupiter runner, Java 17+. Gradle convention thường tạo báo cáo ở `build/reports/tests/test/index.html`; Maven Surefire ở `target/surefire-reports/`. Với project đa module, xem report của module đã chạy.

## 6. Advice trong web slice: phạm vi quét, thứ tự và test exception

`@ControllerAdvice` có thể cung cấp:

- `@ExceptionHandler` ánh xạ exception thành HTTP response.
- `@ModelAttribute` hoặc `@InitBinder` dùng chung cho nhiều controller.
- `ResponseBodyAdvice` và các interceptor liên quan tới body nếu được đăng ký.

Trong một ứng dụng lớn, có thể có nhiều advice cùng bắt exception. Thứ tự xử lý phụ thuộc khả năng match, selector của advice và `@Order`/mức ưu tiên theo Spring MVC. Nếu test trả mã status không mong muốn, hãy kiểm tra **handler exception nào được chọn**; đừng chỉ suy luận từ annotation ở một class.

Khi đặt `@WebMvcTest(controllers = ProductController.class)`, tham số `controllers` giới hạn controller chứ không nhất thiết giới hạn toàn bộ advice toàn cục. Một advice ở package khác ngoài scan base có thể không xuất hiện. Có thể dùng `@Import(SpecificAdvice.class)` để kiểm soát rõ khi cần.

**Đừng chỉ assert status.** Nếu hợp đồng lỗi yêu cầu `{"code":"PRODUCT_NOT_FOUND"}`, hãy assert cả JSON code, content type và field công khai cần thiết. Tránh assert những message exception nội bộ có thể lộ dữ liệu nhạy cảm hoặc thay đổi khi refactor.

Validation thường xảy ra trong argument resolution **trước khi controller body chạy**. `MethodArgumentNotValidException` thường liên quan `@Valid @RequestBody` có ràng buộc bị vi phạm; còn JSON malformed có thể ném `HttpMessageNotReadableException`. Đây là hai nhánh khác nhau: nếu API yêu cầu cùng error schema, cần xử lý/test cả hai; ví dụ ở mục 5 chỉ định nghĩa advice cho validation và domain not found.

## 7. Converter trong MVC khác HttpMessageConverter

Hai tên gần nhau dễ gây nhầm:

| Loại | Đầu vào/đầu ra | Tình huống |
|---|---|---|
| `Converter<String, T>` của Spring Core | Một giá trị Java → kiểu Java khác | `@PathVariable`, `@RequestParam`, binding field |
| `GenericConverter` | Conversion linh hoạt theo source/target descriptors | Binding nhiều kiểu hoặc conversion rule tùy biến |
| `HttpMessageConverter` | HTTP request/response body ↔ Java object | JSON request body tới DTO, DTO tới JSON response |
| Jackson `JsonSerializer`/`JsonDeserializer` | Kiểm soát nội dung JSON của một kiểu | Định dạng/ngữ nghĩa JSON tùy biến |

Ví dụ `SkuConverter` thực hiện `String -> Sku` **cho path parameter**; trong khi record `CreateProductRequest` được Jackson deserialize từ JSON body. `@WebMvcTest` cùng `MockMvc` có thể kiểm tra cả hai đường đi với cấu hình phù hợp.

Nếu controller có `@RequestParam LocalDate date`, Spring có thể dùng định dạng/converter chuẩn hoặc formatter tùy chỉnh. Một unit test gọi trực tiếp `controller.find(date)` sẽ **không chạy argument resolver và conversion service của MVC**, nên không phát hiện lỗi parse request. Đây là lý do cần một web slice test khi lỗi thuộc HTTP contract.

**Lưu ý về đăng ký:** Một `Converter` annotated `@Component` trong phạm vi quét MVC có thể được Boot nhận và áp dụng; nhưng nếu bạn tự định nghĩa một `ConversionService` hoặc `WebMvcConfigurer` phức tạp, cần kiểm tra cấu hình đã thực sự được nạp vào slice. Test nên assert giá trị **sau conversion ở lời gọi service mock**, như `verify(products).findBySku("AB-7")`, thay vì chỉ assert response 200.

## 8. Filter trong MockMvc: bean có mặt chưa chắc filter đã chạy

Servlet `Filter` đứng ở ranh giới trước `DispatcherServlet`. Nó có thể đọc/cấp correlation ID, kiểm tra header, chuyển encoding, xử lý CORS, hoặc chặn request trước khi controller gọi. Nhưng test phải phân biệt:

- **Filter bean có trong context:** có nghĩa Spring đã tạo/đăng ký bean.
- **Filter được đưa vào MockMvc filter chain:** phụ thuộc cấu hình `MockMvc`, registration và filter selection.
- **Filter thật sự thực thi cho request:** chỉ rõ bằng response header, captured invocation hoặc trạng thái quan sát được của request.

`@WebMvcTest` kết hợp `@AutoConfigureMockMvc` thường tự cấu hình `MockMvc`, theo mặc định có thể đăng ký các Servlet filters trong context. Dùng `@AutoConfigureMockMvc(addFilters = false)` khi muốn **cố ý** thử controller mapping mà bỏ qua filters; điều này không có nghĩa những filter beans bị xóa khỏi context.

Ví dụ cấu hình **cố ý bỏ qua filter execution** (không phải test bảo vệ filter):

```java
@WebMvcTest(ProductController.class)
@AutoConfigureMockMvc(addFilters = false)
class ControllerMappingOnlyTest {
    // ...
}
```

Đoạn trên cần imports, controller và body test thích hợp; không phải file độc lập. Nếu bạn viết test security, authentication, audit filter hoặc correlation ID, **đừng dùng addFilters=false** rồi kết luận hành vi filter đúng.

Filter còn có thể chạy với request error/async dispatch tùy cấu hình. `OncePerRequestFilter` giúp kiểm soát việc thực thi theo dispatch type; không đơn giản đồng nghĩa mọi HTTP request tổng thể chỉ có đúng một callback trong mọi tình huống. Khi hành vi liên quan async/error dispatch, cần test trường hợp riêng.

## 9. Spring Security có mặt: vì sao API test bất ngờ trả 401/403?

Trong dự án có Spring Security trên classpath và security configuration phù hợp, `@WebMvcTest` có thể auto-config security và đăng ký `SecurityFilterChain` với MockMvc. Khi đó:

- GET không authentication có thể trả **401** hoặc redirect tới login thay vì 200.
- POST không CSRF token có thể bị **403** (đặc biệt với session-based CSRF mặc định), kể cả test đã có `@WithMockUser`.
- Request bị filter chặn trước controller, nên `verifyNoInteractions(service)` có thể đúng nhưng **không chứng minh validation đã chạy**.
- Mock service thay dependency của controller không đồng nghĩa filter chain và method security đều được test như production.

Chiến lược test:

1. **Kiểm tra MVC contract dưới security thực:** Giữ filters, cấu hình authentication/authority phù hợp và CSRF cho request có trạng thái. Có thể dùng `spring-security-test` và `@WithMockUser` hoặc `SecurityMockMvcRequestPostProcessors.user(...)` / `csrf()` khi được hỗ trợ. Đừng giả định `@WithMockUser` thay được mọi chính sách JWT/OAuth2/custom filter thực tế.
2. **Chỉ quan tâm mapping/JSON trong một lớp test riêng:** Có thể dùng `@AutoConfigureMockMvc(addFilters=false)` một cách có chủ đích, nhưng đánh dấu rõ phạm vi **không kiểm chứng security/filter**; duy trì những security tests khác.
3. **Controller dựa vào `Authentication`, `Principal` hoặc `@AuthenticationPrincipal`:** Phải cấp security context/dữ liệu giả đúng định dạng; bỏ filter một cách mù quáng có thể làm controller nhận `null` và test sai lệch.
4. **Method security nằm trên service thật:** Nếu dùng `@MockitoBean` thay cả service, test không tự chứng minh `@PreAuthorize` trên implementation service hoạt động. Cần test riêng giữ service thật với method security enabled.

Ví dụ **đoạn minh họa** khi đã có Spring Security test dependency:

```java
mvc.perform(post("/api/products")
        .with(user("editor").roles("EDITOR"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"name":"Keyboard","price":75000}
                """))
    .andExpect(status().isCreated());
```

Imports cần có `SecurityMockMvcRequestPostProcessors.user`, `csrf`; request chỉ đạt `201` nếu security rules, bean dependencies và service stub tương ứng cho phép. Đây **không phải ví dụ độc lập**; không khẳng định nó luôn chạy thành công với mọi SecurityFilterChain.

Muốn test controller trả 403 đúng khi thiếu quyền, phải để filter chain thực tế xử lý, tạo người dùng có/không đủ quyền và assert status lẫn việc controller/service có bị gọi hay không theo yêu cầu.

## 10. @WebMvcTest và @SpringBootTest khác nhau thế nào?

| Câu hỏi | @WebMvcTest | @SpringBootTest |
|---|---|---|
| Mục tiêu | HTTP contract của controller trong MVC slice | Tích hợp nhiều tầng/ứng dụng Boot rộng hơn |
| Controller và DispatcherServlet | Có cho thành phần được chọn | Có khi web environment/config phù hợp |
| MockMvc | Thường được auto-config | Cần `@AutoConfigureMockMvc` trong test MVC MockMvc |
| @ControllerAdvice | Có thể được nạp theo phạm vi slice | Có thể được nạp theo application context |
| Converter và Jackson | MVC infrastructure/bean phù hợp | Cấu hình MVC đầy đủ hơn theo app |
| Filter/Security | Có thể có; phụ thuộc cấu hình và MockMvc registration | Có thể có theo application context |
| @Service/@Repository | Không mặc nhiên | Thường có nếu component scan/auto-config cung cấp |
| JPA transaction/database | Không mặc nhiên | Có thể có với dependency/data source phù hợp |
| HTTP server thật | Không | Chỉ với `RANDOM_PORT`/`DEFINED_PORT` |
| Tốc độ/phạm vi | Thường nhanh và dễ cô lập lỗi hơn | Thường rộng và chi phí khởi tạo lớn hơn |
| Bằng chứng về business logic thật | Chỉ nếu thật sự nạp/call implementation cần thiết | Có thể kiểm tra, tùy những bean được giữ thật/mock |

Nếu muốn kiểm thử **response JSON khi service đã trả dữ liệu cụ thể**, `@WebMvcTest` phù hợp. Nếu muốn chứng minh **controller → service → repository → database** hoạt động với mapping JPA và transaction thật, dùng integration test có datasource, thường là `@SpringBootTest` cùng database test thích hợp. Nếu cần xác minh HTTP stack end-to-end qua socket, dùng `webEnvironment = RANDOM_PORT` và HTTP client.

Đừng dùng `@SpringBootTest` cho mọi test chỉ vì `@WebMvcTest` báo thiếu `ProductService`; hãy thay dependency có chủ đích. Ngược lại, đừng cưỡng ép nạp hàng loạt service/repository thật vào slice chỉ để tránh viết integration test.

## 11. Những lỗi thường gặp khi @WebMvcTest không chạy như mong đợi

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| `Failed to load ApplicationContext`, thiếu ProductService | Service không thuộc slice, controller cần constructor dependency | Thêm `@MockitoBean` hoặc fake bean đúng kiểu/tên |
| GET nhận 404 thay vì 200 | Controller không được chọn, sai `@GetMapping`, sai URL, context path/route khác | Kiểm tra selected controller và MockMvc URL |
| POST trả 403 thay vì 201 | Security filter/CSRF, không phải lỗi JSON | Kiểm tra authentication, CSRF và filter chain |
| GET trả 401/redirect | Spring Security yêu cầu login | Thêm security context phù hợp hoặc test riêng phạm vi không filter |
| Validation invalid body vẫn được chấp nhận | Thiếu `@Valid`, thiếu provider, DTO annotation đặt sai | Kiểm tra starter-validation, `@RequestBody`, constraints |
| JSON request trả 400 dù dữ liệu hợp lệ | Jackson deserialize lỗi, content-type, constructor DTO, unknown type | Đọc exception `HttpMessageNotReadableException`/nested cause |
| Exception nghiệp vụ trả 500 | Advice không được quét/import, `@ExceptionHandler` không khớp, mapping conflict | Xác nhận advice bean và JSON/status thực |
| Custom converter không chạy | `Converter` không được đăng ký, MVC config bị loại, route sai | Assert argument service nhận sau conversion, import converter khi cần |
| Filter header không xuất hiện | Filter không được đưa vào MockMvc, addFilters=false, registration khác | Kiểm tra filter bean/registration và test response |
| Web slice nạp quá nhiều bean | Broad component scan, `@Import`/custom config kéo theo dependency | Giảm cấu hình, mock phụ thuộc, tránh scan toàn app |
| `@MockitoBean` không nhận diện annotation | Spring Framework version quá cũ | Dùng annotation tương thích với Boot version |
| Test web xanh nhưng endpoint thật lỗi database | Service đã bị mock và persistence chưa chạy | Bổ sung integration test tại đúng tầng |
| Một test chạy riêng xanh nhưng suite đỏ | Shared context/bean mutable, filter/security config trùng, stubbing/caching | Tách fixture và quản lý test context/cache đúng cách |

Lỗi khởi tạo context xảy ra **trước khi test method chạy** có thể liên quan bean override, filter cần dependency, advice constructor hoặc auto-configuration. Tìm `Caused by` sâu nhất có thông tin hành động được, tránh sửa assertion khi controller còn chưa được tạo.

## 12. Viết bộ test MVC slice đáng tin cậy

Một chiến lược thực tế là kết hợp nhiều góc kiểm tra, mỗi test xác nhận đúng phần giao diện HTTP:

- **Happy path:** GET/POST/PUT/PATCH/DELETE cần thiết; assert HTTP status, content type, headers và JSON fields.
- **Mapping và binding:** path variable, query parameter, enum/date/UUID/custom converter; kiểm tra argument mà mock service nhận.
- **Validation:** missing/blank/negative/out-of-range fields, error payload, đảm bảo không gọi service khi request chưa hợp lệ.
- **Exception advice:** not-found, conflict và lỗi nghiệp vụ; assert status và schema lỗi, tránh phụ thuộc stack trace trong response.
- **JSON converters:** serialization/deserialization của record/DTO, formatting ngày giờ, snake_case/camelCase, nullable fields và các Jackson customizers theo hợp đồng.
- **Filters/interceptors:** khi nằm trong phạm vi test, assert tác dụng quan sát được; không chỉ assert filter bean tồn tại.
- **Security:** tách ca anonymous/authorized/forbidden/CSRF theo SecurityFilterChain thực; không vô hiệu hóa filters trong test tự nhận kiểm tra bảo mật.
- **Isolation:** mock dependencies có dữ liệu riêng từng test, không mock controller, không vô tình nạp database hoặc scheduler ngoài phạm vi.

Một endpoint chỉ trả `200` nhưng JSON sai field hoặc filter không chạy có thể vẫn gây lỗi cho client. Ngược lại, một test chỉ dùng `verify(service).findById(41L)` không chứng minh response JSON đúng. **Kết hợp assertions trên HTTP response và interactions nghiệp vụ đầu vào** là cách đánh giá đầy đủ phạm vi MVC slice.

## 13. Checklist trước khi kết luận @WebMvcTest đạt

- [ ] Đã chọn đúng controller trong `@WebMvcTest(controllers=...)`, biết những MVC-related beans nào được nạp.
- [ ] Controller là implementation thật; dependency ngoài slice được cung cấp bằng `@MockitoBean`/fake phù hợp phiên bản.
- [ ] Đã kiểm tra URL, HTTP method, path/query binding và JSON request/response qua `MockMvc.perform`.
- [ ] Đã phân biệt `Converter` cho tham số request và `HttpMessageConverter` cho HTTP body.
- [ ] Đã kiểm tra `@RestControllerAdvice` xử lý đúng exception/status/error JSON.
- [ ] Validation có `@Valid`, constraint và provider; test invalid input không gọi service.
- [ ] Nếu filter thuộc hợp đồng, đã xác minh filter **thực thi**, không chỉ có bean.
- [ ] Nếu Spring Security hiện diện, đã xác định filter chain, authentication và CSRF; không vô tình dùng `addFilters=false` trong security test.
- [ ] Không coi kết quả của service mock là bằng chứng business/database/transaction thật.
- [ ] Đã tách những rủi ro ngoài MVC slice sang integration test như `@SpringBootTest`, JPA test hoặc HTTP end-to-end.
- [ ] Đã chạy đúng lớp test và xem báo cáo của build runner trước khi khẳng định PASS trên dự án thực tế.

**Kết luận:** `@WebMvcTest` tập trung kiểm tra **cách Spring MVC xử lý một request**: controller mapping, argument conversion, JSON message conversion, validation, exception advice và filters được đăng ký. Giữ **controller thật**, mock/fake **dependency ngoài slice**, và assert cả response lẫn lời gọi service sẽ cho bài test nhanh, rõ và đáng tin cậy. Tuy nhiên, sự hiện diện của advice/converter/filter tùy phạm vi cấu hình thực tế; security có thể chặn request trước controller; và các hành vi database, transaction hay HTTP server thật cần test tích hợp riêng.