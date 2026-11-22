# `webAppContextSetup` với cấu hình MVC thật

`MockMvc` cho phép kiểm thử request và response của Spring MVC mà không cần khởi động máy chủ HTTP. Khi tạo `MockMvc` bằng `MockMvcBuilders.webAppContextSetup(webApplicationContext)`, bài test sử dụng `WebApplicationContext` đã được Spring nạp cùng cấu hình web thực tế của ứng dụng. Request đi qua `DispatcherServlet` và các thành phần MVC được đăng ký trong context, vì vậy có thể kiểm tra cách controller phối hợp với mapping, converter, validator, interceptor, exception handler và view resolver.

Đây là lựa chọn phù hợp khi mục tiêu là kiểm tra hành vi của toàn bộ cấu hình Spring MVC trong môi trường test. Bài test vẫn chạy trong mock servlet environment; nó không mở cổng mạng và không kiểm tra hành vi riêng của một servlet container đang chạy thật.

## `webAppContextSetup` hoạt động như thế nào?

`MockMvcBuilders` cung cấp hai cách dựng phổ biến:

| Cách dựng | Context được sử dụng | Phạm vi kiểm thử |
|---|---|---|
| `standaloneSetup(controller)` | Các controller được truyền trực tiếp cùng cấu hình test tùy chọn | Tập trung vào controller; test tự cấu hình những thành phần MVC cần thiết |
| `webAppContextSetup(wac)` | `WebApplicationContext` của ứng dụng | Sử dụng cấu hình Spring MVC đã được nạp trong context |

Với `webAppContextSetup`, Spring Test khởi tạo `DispatcherServlet` trong môi trường servlet mô phỏng dựa trên `WebApplicationContext` được cung cấp. Khi request được thực hiện, `DispatcherServlet` sử dụng các thành phần MVC mà context cung cấp hoặc phát hiện, chẳng hạn:

- `HandlerMapping` để tìm handler phù hợp với URL, HTTP method và điều kiện mapping.
- `HandlerAdapter` để gọi controller hoặc handler tương ứng.
- `HandlerExceptionResolver` và `@ControllerAdvice` để xử lý exception phát sinh trong quá trình xử lý request.
- `HttpMessageConverter` để đọc request body và ghi response body, ví dụ chuyển JSON thành object hoặc ngược lại.
- `ConversionService`, `Formatter` và `Validator` để chuyển đổi, định dạng và kiểm tra dữ liệu đầu vào.
- `HandlerInterceptor` để chạy logic trước và sau handler theo cấu hình MVC.
- `ViewResolver` để tìm view khi controller trả về tên view thay vì response body.

Những thành phần này được dùng theo cấu hình đã nạp. Ví dụ, nếu ứng dụng đăng ký converter JSON riêng, cấu hình CORS, interceptor kiểm tra locale, hoặc `@RestControllerAdvice`, test có thể quan sát tác động của chúng qua request và response.

Điều kiện quan trọng là đối tượng truyền vào phải là `WebApplicationContext` chứa cấu hình MVC phù hợp. Một `ApplicationContext` thông thường không có ngữ cảnh web không thể thay thế cho nó.

## Nạp WebApplicationContext trong Spring thuần

Với ứng dụng Spring MVC không dùng Spring Boot, Spring Test có thể nạp cấu hình Java bằng `@ContextConfiguration` và tạo servlet context mô phỏng bằng `@WebAppConfiguration`.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcConfig.class)
class ProductControllerMvcTest {

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
    void returnsProductAsJson() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                        .accept("application/json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

`WebMvcConfig` trong ví dụ là cấu hình MVC của ứng dụng, không phải một cấu hình dựng controller riêng cho `MockMvc`. Cấu hình đó thường bật Spring MVC và đăng ký controller cùng các thành phần cần thiết:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan(basePackages = "com.example.web")
class WebMvcConfig implements WebMvcConfigurer {
    // Đăng ký interceptor, formatter, converter, CORS... nếu ứng dụng cần.
}
```

Các service, repository và dependency mà controller cần cũng phải có mặt trong context hoặc trong context cha. Trong ứng dụng phân chia root context và servlet context, root context thường chứa service/repository, còn servlet context chứa controller và cấu hình MVC. Khi dùng `@ContextHierarchy`, hãy bảo đảm `WebApplicationContext` được inject là context gắn với `DispatcherServlet` cần kiểm thử, để test sử dụng đúng cấu hình handler và MVC.

`@WebAppConfiguration` báo cho Spring Test rằng test cần một web application context và một `MockServletContext`. Nếu thiếu annotation này trong một test cấu hình Spring thuần, context có thể không phải `WebApplicationContext`, khiến việc inject hoặc dựng `MockMvc` thất bại.

## Nạp cấu hình thật trong Spring Boot

Với ứng dụng Spring Boot, `@SpringBootTest` nạp application context của ứng dụng và các cấu hình MVC được Boot tự động cấu hình hoặc được dự án tùy chỉnh. Có thể dựng `MockMvc` thủ công từ `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.http.MediaType;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ProductControllerIntegrationTest {

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
    void returnsProductUsingApplicationMvcConfiguration() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

`WebEnvironment.MOCK` tạo môi trường servlet mô phỏng thay vì khởi động server thật. Đây là môi trường phù hợp để dùng `webAppContextSetup`. Nếu muốn kiểm thử qua HTTP thực tế, bao gồm server và network stack, hãy dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và một HTTP client; đó là một kiểu kiểm thử khác.

Spring Boot cũng cung cấp `@AutoConfigureMockMvc` để tự cấu hình và inject `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductControllerAutoConfiguredTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsProduct() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42L))
                .andExpect(status().isOk());
    }
}
```

Khi dùng `@AutoConfigureMockMvc`, không cần tự gọi `webAppContextSetup`. Annotation này hữu ích nếu muốn để Spring Boot quản lý việc dựng MockMvc và áp dụng các customizer của Boot. Bài học này tập trung vào cách dựng thủ công để thấy rõ `WebApplicationContext` được truyền vào builder như thế nào.

## Kiểm tra các thành phần MVC thật

Điểm mạnh của `webAppContextSetup` thể hiện rõ khi test đi qua nhiều lớp cấu hình. Một request có thể được ánh xạ bằng `RequestMappingHandlerMapping`, dữ liệu JSON được xử lý bởi converter, validation chạy trên tham số controller và exception được chuyển thành response bởi `@ControllerAdvice`.

Ví dụ, controller có thể nhận DTO từ JSON và dùng Bean Validation:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    ResponseEntity<ProductDto> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductDto created = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Test qua MockMvc có thể xác nhận cả status và response khi dữ liệu hợp lệ hoặc không hợp lệ:

```java
mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"Keyboard"}
                        """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Keyboard"));

mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":""}
                        """))
        .andExpect(status().isBadRequest());
```

Các request trên chỉ là ví dụ minh họa; DTO phải có constraint phù hợp và controller phải được cấu hình để validation hoạt động. Khi dùng context thật, test có thể phát hiện lỗi cấu hình như thiếu validation provider, converter không hỗ trợ kiểu dữ liệu, mapping không đúng hoặc advice không được đăng ký.

Với controller trả về view, có thể kiểm tra tên view và model:

```java
mockMvc.perform(get("/products/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(view().name("products/detail"))
        .andExpect(model().attributeExists("product"));
```

Nếu ứng dụng dùng `ViewResolver` tùy chỉnh, `webAppContextSetup` giúp test kiểm tra kết quả theo cấu hình đã nạp thay vì phải tự dựng resolver cho từng controller.

## Interceptor và servlet Filter

`HandlerInterceptor` là một phần của Spring MVC. Khi interceptor được đăng ký qua `WebMvcConfigurer#addInterceptors`, nó thuộc cấu hình MVC được `DispatcherServlet` sử dụng trong `webAppContextSetup`. Test có thể xác nhận hành vi của interceptor bằng cách gửi request bình thường và kiểm tra status, header, model hoặc side effect phù hợp.

Servlet `Filter` nằm ở lớp servlet trước `DispatcherServlet`. Khi tự dựng MockMvc bằng `webAppContextSetup`, cần thêm các filter muốn chạy vào builder:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .addFilters(characterEncodingFilter, requestAuditFilter)
        .build();
```

Đưa filter vào builder giúp filter tham gia chuỗi xử lý request của MockMvc. Việc một filter tồn tại dưới dạng bean trong application context không đồng nghĩa mọi cách dựng MockMvc thủ công đều tự động thêm filter đó. Hãy đăng ký rõ các filter mà bài test cần đi qua.

Với Spring Security, nếu dự án dùng `spring-security-test`, có thể áp dụng cấu hình bảo mật vào builder:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` kết nối chuỗi filter bảo mật được cấu hình trong context với MockMvc. Sau đó test có thể dùng các request post processor như `user("alice")`, `csrf()` hoặc kiểm tra response khi chưa đăng nhập:

```java
mockMvc.perform(get("/api/account").with(user("alice")))
        .andExpect(status().isOk());

mockMvc.perform(post("/api/account")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isOk());
```

Khi dùng `.apply(springSecurity())`, không thêm cùng `springSecurityFilterChain` lần nữa bằng `.addFilters(...)`, vì điều đó có thể làm chuỗi bảo mật chạy lặp. Với filter tự viết, hãy thêm các filter cần thiết một cách có chủ đích.

## Tùy chỉnh builder

`webAppContextSetup` trả về builder, vì vậy có thể thêm thiết lập dùng chung cho toàn bộ request của test suite:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .defaultRequest(get("/").accept(MediaType.APPLICATION_JSON))
        .alwaysExpect(status().isOk())
        .build();
```

Chỉ đặt `alwaysExpect` cho điều kiện thật sự đúng với mọi request. Ví dụ trên chỉ phù hợp nếu tất cả request trong test class đều được kỳ vọng trả về `200 OK`; nó không phù hợp với test kiểm tra `400`, `401`, `404` hoặc `201`.

Một số tùy chỉnh hữu ích khác:

- `addFilters(...)` thêm servlet filter vào chuỗi request.
- `defaultRequest(...)` thiết lập mặc định như header hoặc request attribute.
- `alwaysDo(...)` áp dụng một `ResultHandler` cho mọi request, ví dụ ghi request/response khi debug.
- `alwaysExpect(...)` áp dụng một `ResultMatcher` chung.
- `apply(...)` áp dụng cấu hình bổ sung, chẳng hạn `springSecurity()`.

Có thể gọi `andDo(print())` trên một request cụ thể để xem chi tiết request và response khi test thất bại:

```java
mockMvc.perform(get("/api/products/{id}", 42L))
        .andDo(print())
        .andExpect(status().isOk());
```

Trong test suite ổn định, thường nên tạo `MockMvc` một lần cho mỗi test class hoặc tái sử dụng instance đã dựng từ context. Spring Test có cơ chế cache application context; việc dựng builder không yêu cầu khởi động lại toàn bộ context cho mỗi request.

## Những giới hạn cần hiểu đúng

`webAppContextSetup` kiểm thử Spring MVC trong mock servlet environment. Nó xử lý request thông qua `DispatcherServlet` và các thành phần được đăng ký, nhưng không thực hiện một số hoạt động của server thật:

- Không mở socket, không bind port và không truyền request qua network stack.
- Không xác nhận cấu hình connector, TLS, reverse proxy, giới hạn request của server hoặc hành vi riêng của Tomcat/Jetty/Undertow.
- Không tự động chứng minh mọi servlet filter của môi trường triển khai đã được đăng ký; filter cần thiết phải có trong MockMvc chain.
- Không thay thế kiểm thử tích hợp qua HTTP thật khi cần xác minh cấu hình triển khai hoặc tương tác với hạ tầng mạng.

Ngoài ra, `webAppContextSetup` dùng đúng context được truyền vào. Nếu test nạp nhầm context, chẳng hạn chỉ nạp root context mà bỏ qua servlet context chứa MVC configuration, handler mapping hoặc converter có thể không xuất hiện như mong đợi. Hãy kiểm tra cấu trúc context của ứng dụng trước khi điều chỉnh builder.

`@WebMvcTest` trong Spring Boot là một MVC test slice: nó chỉ nạp một tập thành phần được chọn cho web layer và thường cần mock các dependency ngoài phạm vi slice. Nếu dùng `WebApplicationContext` của slice với `webAppContextSetup`, builder vẫn sử dụng context đó, nhưng phạm vi cấu hình vẫn là slice. Muốn kiểm tra cấu hình ứng dụng đầy đủ, hãy nạp application context thích hợp, ví dụ bằng `@SpringBootTest`.

## Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không inject được `WebApplicationContext` hoặc context không phải web context | Test Spring thuần thiếu `@WebAppConfiguration`, hoặc cấu hình nạp sai loại context | Dùng `@WebAppConfiguration` và nạp cấu hình MVC |
| Request trả `404` dù controller tồn tại | Controller không được component scan/import vào context; sai servlet context hoặc URL mapping | Kiểm tra cấu hình scan, mapping và context được inject |
| Không chuyển đổi được JSON | Converter hoặc Jackson configuration không có trong context | Nạp cấu hình MVC thực tế và kiểm tra dependency/converter |
| Validation không chạy | Thiếu validation provider, constraint hoặc cấu hình cần thiết | Kiểm tra Bean Validation dependency và cấu hình MVC |
| `@ControllerAdvice` không xử lý exception | Advice không được phát hiện trong context đang dùng | Đưa advice vào component scan hoặc import cấu hình tương ứng |
| Interceptor không chạy | Interceptor chưa được đăng ký trong MVC config đang nạp | Kiểm tra `WebMvcConfigurer#addInterceptors` |
| Filter không chạy | Filter chưa được thêm vào MockMvc builder | Dùng `.addFilters(...)` hoặc cơ chế cấu hình MockMvc phù hợp |
| Spring Security filter chạy hai lần | Vừa `.apply(springSecurity())` vừa thêm cùng filter chain thủ công | Chỉ đăng ký chuỗi bảo mật một lần |
| Test pass nhưng triển khai thực tế vẫn lỗi ở server | MockMvc không chạy network stack hoặc servlet container thật | Bổ sung kiểm thử HTTP với server thật khi phạm vi yêu cầu điều đó |

## Khi nào nên chọn `webAppContextSetup`?

Chọn `webAppContextSetup` khi bài test cần xác minh controller hoạt động cùng cấu hình MVC của ứng dụng: mapping, converter, formatter, validator, interceptor, advice, view resolver hoặc cấu hình bảo mật được nối vào MockMvc. Đây cũng là lựa chọn tốt khi muốn kiểm tra nhiều controller trong cùng một cấu hình web context.

Nếu chỉ cần kiểm tra logic của một controller với một tập dependency nhỏ và muốn cấu hình nhanh, `standaloneSetup` có thể phù hợp hơn. Nếu cần kiểm tra server, cổng mạng, TLS hoặc hành vi servlet container, hãy chạy ứng dụng trong môi trường server thật và gửi HTTP request. Việc chọn đúng cách dựng giúp bài test chứng minh chính xác phần hành vi mà nó được thiết kế để kiểm tra.
