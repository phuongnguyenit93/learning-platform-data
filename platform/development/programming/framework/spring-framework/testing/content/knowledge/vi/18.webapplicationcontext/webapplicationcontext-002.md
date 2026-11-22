# Nạp cấu hình Spring MVC cho kiểm thử tích hợp

Khi kiểm thử một controller Spring MVC, ta thường muốn gửi request giả lập qua đúng các thành phần mà ứng dụng sử dụng khi chạy: `DispatcherServlet`, handler mapping, controller, argument resolver, message converter, exception resolver, interceptor và các bean liên quan. Nếu chỉ tạo controller rồi truyền trực tiếp vào `MockMvcBuilders.standaloneSetup(...)`, bài kiểm thử có thể xác nhận logic của controller nhưng chưa chứng minh cấu hình Spring MVC của ứng dụng được nạp và phối hợp đúng.

Spring Test cung cấp `WebApplicationContext` và `MockMvcBuilders.webAppContextSetup(...)` để xây dựng kiểm thử tích hợp ở tầng web. `WebApplicationContext` chứa cấu hình dành cho ứng dụng web, bao gồm các bean MVC và `ServletContext`. Khi truyền context này cho `webAppContextSetup`, Spring Test tạo một `MockMvc` sử dụng cấu hình đã nạp để xử lý request bằng servlet API giả lập.

## 1. Vì sao cần nạp `WebApplicationContext`?

Trong ứng dụng Spring MVC, request HTTP đi qua một chuỗi thành phần trước khi đến phương thức controller:

```text
HTTP request
    |
    v
Servlet container
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping tìm handler phù hợp
    |
    +--> HandlerInterceptor xử lý trước handler
    |
    +--> HandlerAdapter gọi controller
    |
    +--> ArgumentResolver chuyển request thành tham số Java
    |
    +--> Controller xử lý request
    |
    +--> ReturnValueHandler / HttpMessageConverter tạo response
    |
    +--> ExceptionResolver xử lý exception nếu có
    v
HTTP response
```

Các thành phần này được cấu hình và kết nối với nhau trong môi trường Spring MVC. Ví dụ, một controller có thể hoạt động đúng khi được gọi trực tiếp nhưng route thực tế lại không được đăng ký do component scan sai package. Một endpoint trả về DTO có thể chạy được với converter mặc định nhưng thất bại khi ứng dụng dùng converter hoặc cấu hình Jackson tùy chỉnh. Một exception có thể được xử lý bởi `@ControllerAdvice`, nhưng bài kiểm thử tạo controller độc lập sẽ không nạp advice đó.

Nạp `WebApplicationContext` giúp bài kiểm thử đi qua cấu hình MVC đã khai báo trong ứng dụng. Ta có thể kiểm tra các mối liên hệ giữa controller và hạ tầng web, thay vì chỉ kiểm tra một đối tượng Java tách rời.

`WebApplicationContext` mở rộng `ApplicationContext` và bổ sung khả năng làm việc với `ServletContext`. Trong Spring TestContext Framework, annotation `@WebAppConfiguration` cho Spring biết rằng test cần một web application context. Annotation `@ContextConfiguration` chỉ ra cấu hình nguồn để nạp các bean.

## 2. Phân biệt `standaloneSetup` và `webAppContextSetup`

Spring MVC Test cung cấp hai cách phổ biến để tạo `MockMvc`:

| Cách tạo | Cấu hình được sử dụng | Mục đích phù hợp |
| --- | --- | --- |
| `MockMvcBuilders.standaloneSetup(controller)` | Tạo hạ tầng MVC tối thiểu cho controller được truyền vào; có thể tùy chỉnh thêm một số thành phần. | Kiểm thử controller tập trung, nhanh, ít phụ thuộc cấu hình ứng dụng. |
| `MockMvcBuilders.webAppContextSetup(wac)` | Sử dụng `WebApplicationContext` đã nạp, bao gồm cấu hình MVC và các bean của web application. | Kiểm thử tích hợp cấu hình web, mapping, converter, advice, interceptor và wiring của bean. |

Hai cách đều dùng `MockMvc` và đều có thể thực hiện request mà không khởi động một HTTP server thật. Điểm khác nhau nằm ở nguồn cấu hình mà `MockMvc` sử dụng.

Ví dụ `standaloneSetup`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .build();
```

Controller được tạo trực tiếp. Nếu ứng dụng có `@ControllerAdvice`, interceptor hoặc message converter tùy chỉnh, test cần đăng ký những thành phần đó riêng nếu muốn kiểm tra chúng. Cấu hình MVC của ứng dụng không tự động được nạp chỉ vì controller có annotation `@RestController`.

Với `webAppContextSetup`, ta truyền context đã được Spring Test khởi tạo:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

`MockMvc` sử dụng các thành phần Spring MVC từ context đó. Đây là lựa chọn thích hợp khi mục tiêu của test là xác nhận cấu hình web thực tế hoạt động cùng controller.

## 3. Khai báo cấu hình Spring MVC cho test

Ví dụ dưới đây sử dụng Java configuration. `@EnableWebMvc` bật hạ tầng Spring MVC; `@ComponentScan` tìm controller và các bean web liên quan trong package được chỉ định.

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = GreetingController.class)
class WebConfig implements WebMvcConfigurer {
}
```

`basePackageClasses` giúp xác định package scan dựa trên một class marker. Cách này tránh viết tên package dạng chuỗi, vốn dễ bị lỗi khi package được đổi tên. Trong ứng dụng thực tế, có thể dùng marker thuộc package gốc chứa các controller, hoặc khai báo phạm vi scan rõ ràng theo cấu trúc dự án.

Controller ví dụ:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
class GreetingController {

    @GetMapping("/{name}")
    GreetingResponse greeting(@PathVariable String name) {
        return new GreetingResponse("Hello, " + name);
    }
}

record GreetingResponse(String message) {
}
```

Khi Jackson có trên classpath, cấu hình MVC mặc định có thể dùng JSON message converter để chuyển record thành JSON. Ứng dụng có cấu hình converter riêng thì test tích hợp sẽ sử dụng cấu hình đó, miễn là cấu hình ấy được nạp vào context.

Nếu controller phụ thuộc service, service phải là bean trong context. Có thể để component scan phát hiện `@Service`, hoặc khai báo bean trong cấu hình. Điều này giúp Spring thực hiện dependency injection giống cách ứng dụng được cấu hình.

## 4. Dùng `@WebAppConfiguration` và `@ContextConfiguration`

Với JUnit Jupiter, có thể dùng `SpringExtension` để tích hợp Spring TestContext Framework với JUnit 5. `@WebAppConfiguration` yêu cầu Spring tạo `WebApplicationContext`, còn `@ContextConfiguration` cung cấp lớp cấu hình dùng để nạp context.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.WebApplicationContext;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebConfig.class)
class GreetingControllerWebTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void contextIsLoaded() {
        // Có thể sử dụng webApplicationContext để xây dựng MockMvc.
    }
}
```

Các annotation có trách nhiệm riêng:

- `@ExtendWith(SpringExtension.class)` kết nối vòng đời test của JUnit Jupiter với Spring TestContext Framework. Spring quản lý việc tạo context và inject dependency vào test.
- `@WebAppConfiguration` yêu cầu loại context dành cho web. Spring tạo `WebApplicationContext` cùng `ServletContext` giả lập.
- `@ContextConfiguration(classes = WebConfig.class)` chỉ định Java configuration cần nạp. Có thể dùng `locations` nếu cấu hình nằm trong XML.
- `@Autowired WebApplicationContext` lấy context mà Spring Test đã tạo và quản lý.

Nếu dùng XML configuration, có thể khai báo:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(locations = "classpath:test-mvc-context.xml")
class GreetingControllerWebTest {
    // ...
}
```

Không cần khai báo đồng thời `classes` và `locations` cho cùng một cấu hình trừ khi có chủ đích kết hợp các nguồn cấu hình. Hãy bảo đảm đường dẫn XML tồn tại trên test classpath và chứa các bean MVC mà test cần.

`@WebAppConfiguration` có thuộc tính `value` để chỉ định resource base path cho web application. Mặc định là `src/main/webapp`. Nếu test cần truy cập tài nguyên web ở vị trí khác, có thể khai báo rõ, ví dụ `@WebAppConfiguration("src/test/webapp")` hoặc dùng một vị trí classpath phù hợp. Resource base path này liên quan đến tài nguyên web, không thay thế cấu hình bean được khai báo qua `@ContextConfiguration`.

## 5. Xây dựng `MockMvc` từ context đã nạp

Sau khi Spring tạo `WebApplicationContext`, dùng `MockMvcBuilders.webAppContextSetup(...)` để tạo đối tượng gửi request giả lập.

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

// Trong lớp test:
private MockMvc mockMvc;

@BeforeEach
void setUp() {
    mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
}
```

`webAppContextSetup` nhận context do Spring quản lý. Khi gọi `build()`, Spring MVC Test chuẩn bị môi trường `MockMvc` dựa trên web context đó. Request được chuyển qua `DispatcherServlet` trong môi trường servlet giả lập, rồi được xử lý bằng các mapping và handler của ứng dụng.

Một test hoàn chỉnh có thể gửi request GET và kiểm tra response:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

@Test
void shouldReturnGreetingAsJson() throws Exception {
    mockMvc.perform(get("/api/greetings/Lan")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello, Lan"));
}
```

Test này xác nhận nhiều lớp cùng hoạt động:

1. Handler mapping tìm được endpoint `/api/greetings/{name}`.
2. Spring chuyển giá trị `Lan` vào tham số `@PathVariable`.
3. Controller trả về `GreetingResponse`.
4. Message converter chuyển kết quả thành JSON.
5. `MockMvc` ghi nhận HTTP status và response body để assertion kiểm tra.

Nếu route không được đăng ký, test thường nhận status 404. Nếu converter không thể ghi response theo media type yêu cầu, lỗi có thể xuất hiện khi xử lý response. Những lỗi này giúp phát hiện vấn đề trong cấu hình web mà test gọi trực tiếp controller không thể hiện.

## 6. Kiểm tra các thành phần MVC được nạp từ context

Giá trị của `webAppContextSetup` thể hiện rõ hơn khi ứng dụng có các thành phần dùng chung. Chẳng hạn, một `@ControllerAdvice` có thể chuẩn hóa response khi controller ném exception.

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    ErrorResponse handleIllegalArgument(IllegalArgumentException exception) {
        return new ErrorResponse(exception.getMessage());
    }
}

record ErrorResponse(String message) {
}
```

Controller có thể ném exception:

```java
@GetMapping("/validate")
GreetingResponse validate() {
    throw new IllegalArgumentException("Invalid greeting request");
}
```

Nếu component scan hoặc cấu hình import đã đưa `ApiExceptionHandler` vào `WebApplicationContext`, test có thể kiểm tra kết quả xử lý exception:

```java
mockMvc.perform(get("/api/greetings/validate"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.message").value("Invalid greeting request"));
```

Tương tự, một context MVC đầy đủ có thể nạp và kết nối:

- `HandlerInterceptor` để xử lý trước và sau controller.
- `WebMvcConfigurer` để đăng ký formatter, converter, interceptor, CORS mapping hoặc resource handler.
- `@ControllerAdvice` để xử lý exception và binding result trên nhiều controller.
- Validator và cấu hình validation cho request model.
- Argument resolver và return value handler tùy chỉnh.
- Các bean được controller sử dụng thông qua dependency injection.

Ví dụ cấu hình interceptor. Giả sử interceptor đã được khai báo thành bean, chẳng hạn bằng `@Component`:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
class RequestAuditInterceptor implements HandlerInterceptor {
}
```

Sau đó đăng ký bean trong MVC configuration:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = GreetingController.class)
class WebConfig implements WebMvcConfigurer {

    private final RequestAuditInterceptor requestAuditInterceptor;

    WebConfig(RequestAuditInterceptor requestAuditInterceptor) {
        this.requestAuditInterceptor = requestAuditInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(requestAuditInterceptor)
                .addPathPatterns("/api/**");
    }
}
```

Khi test dùng `webAppContextSetup`, interceptor đã đăng ký trong MVC config được sử dụng trong quá trình xử lý request. Nếu test cần xác nhận hành vi interceptor, hãy gửi request đi qua `MockMvc` và kiểm tra tác động quan sát được, thay vì chỉ kiểm tra bean tồn tại.

## 7. Root context và servlet context trong ứng dụng nhiều tầng

Một ứng dụng Spring MVC truyền thống có thể chia context thành hai tầng:

- Root application context chứa các bean dùng chung như service, repository và cấu hình hạ tầng.
- Servlet application context là context con chứa controller, handler mapping và cấu hình MVC dành cho một `DispatcherServlet`.

Context con có thể truy cập bean ở context cha. Cách tổ chức này hữu ích khi ứng dụng có nhiều servlet hoặc cần tách cấu hình web khỏi dịch vụ nghiệp vụ.

Spring TestContext hỗ trợ cấu trúc đó bằng `@ContextHierarchy`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "mvc", classes = WebConfig.class)
})
class GreetingControllerWebTest {

    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Trong ví dụ này, `RootConfig` đại diện cho cấu hình cha và `WebConfig` đại diện cho cấu hình web con. `WebConfig` có thể scan controller và inject service từ context cha. Khi dùng context hierarchy, hãy giữ rõ ranh giới bean: controller và cấu hình MVC thường thuộc context servlet; service và repository dùng chung thường thuộc root context.

Không phải ứng dụng nào cũng cần hierarchy. Với ứng dụng nhỏ hoặc cấu hình Java hiện đại, một `WebApplicationContext` duy nhất thường đủ. Chỉ sử dụng nhiều tầng khi kiến trúc ứng dụng thực sự có ranh giới root/servlet hoặc nhiều servlet context.

## 8. Dùng cấu hình Spring Boot trong kiểm thử MVC

Trong ứng dụng Spring Boot, việc nạp cấu hình thường được thực hiện thông qua các annotation kiểm thử Boot. Cần phân biệt hai lựa chọn thường gặp:

**`@SpringBootTest` kết hợp `@AutoConfigureMockMvc`** nạp application context của ứng dụng và cấu hình `MockMvc` tự động. Đây là lựa chọn phù hợp khi muốn kiểm tra tích hợp rộng hơn, bao gồm cấu hình web và các bean ứng dụng thực tế.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerBootIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldHandleGreetingRequest() throws Exception {
        mockMvc.perform(get("/api/greetings/Lan"))
                .andExpect(status().isOk());
    }
}
```

Mặc định `@SpringBootTest` dùng web environment dạng mock khi ứng dụng có web application type phù hợp. `MockMvc` gửi request qua hạ tầng servlet giả lập, không cần mở cổng HTTP.

**`@WebMvcTest`** tạo một MVC test slice, tập trung vào các thành phần web được chọn như controller, controller advice, converter và MVC configuration phù hợp. Các service hoặc repository không tự động được nạp như trong full application context; nếu controller phụ thuộc service, test thường cung cấp mock bean cho dependency đó.

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(GreetingController.class)
class GreetingControllerSliceTest {
    // MockMvc được Boot cấu hình cho MVC slice.
}
```

`@WebMvcTest` hữu ích khi muốn tập trung vào hợp đồng HTTP của controller. `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` phù hợp khi cần xác nhận nhiều cấu hình và bean cùng phối hợp. Với Spring Framework không dùng Boot, cặp `@WebAppConfiguration` và `@ContextConfiguration` cùng `webAppContextSetup` là cách cấu hình trực tiếp.

Không nên trộn annotation theo kiểu máy móc. Hãy chọn một cơ chế tạo context phù hợp với loại ứng dụng và phạm vi test. Khi đã dùng Boot test slice, không cần tự tạo một `WebApplicationContext` thứ hai chỉ để xây dựng `MockMvc`.

## 9. Filter và Spring Security trong `MockMvc`

`WebApplicationContext` chứa các bean Spring, còn servlet filter là thành phần thuộc chuỗi servlet. Nếu ứng dụng có filter cần được kiểm tra, phải bảo đảm filter đó được đăng ký trong cấu hình `MockMvc` hoặc được cơ chế kiểm thử đang dùng tự cấu hình.

Với Spring Security, test MVC thường cần tích hợp filter chain bảo mật. Trong cấu hình Spring Security Test, có thể áp dụng `springSecurity()` khi dựng `MockMvc` từ web context:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

Đoạn trên cần import `SecurityMockMvcConfigurers.springSecurity` và có cấu hình Spring Security tương ứng trong context cùng dependency kiểm thử Spring Security. Nếu bỏ qua filter chain, một test có thể truy cập endpoint thành công trong khi request thật sẽ bị yêu cầu xác thực hoặc phân quyền.

Với Spring Boot, `@AutoConfigureMockMvc` mặc định đăng ký các filter trong application context; thuộc tính `addFilters` có thể điều chỉnh hành vi này. Nếu cố ý tắt filter trong test, hãy hiểu rằng test đang bỏ qua một phần của chuỗi xử lý HTTP.

## 10. Context được tái sử dụng và cách giữ test ổn định

Spring TestContext Framework có cơ chế cache application context. Các test dùng cùng cấu hình context có thể chia sẻ context đã khởi tạo, giúp giảm thời gian chạy test. Vì vậy, không cần tự khởi tạo lại `WebApplicationContext` trong từng phương thức test.

`MockMvc` có thể được tạo một lần trong `@BeforeEach` hoặc lưu thành field dùng chung nếu cấu hình không thay đổi. Cách tạo nào phù hợp phụ thuộc vào customizer và trạng thái mà test thiết lập. Hãy tránh sửa trực tiếp singleton bean hoặc trạng thái dùng chung trong context khiến test phụ thuộc thứ tự chạy.

`@DirtiesContext` đánh dấu context cần loại khỏi cache và được tạo lại sau đó. Chỉ dùng khi test thực sự làm thay đổi trạng thái hoặc cấu hình context theo cách không thể khôi phục. Dùng annotation này tràn lan làm test chậm và thường che giấu vấn đề thiết kế trạng thái dùng chung.

Một số nguyên tắc giúp kiểm thử tích hợp ổn định:

1. Dùng cấu hình test rõ ràng và chỉ nạp những package cần thiết.
2. Đảm bảo controller, advice, converter và interceptor nằm trong phạm vi scan hoặc được import.
3. Kiểm tra request qua URL, method, header và body như một client HTTP thực hiện.
4. Assertion trên status, header và response body; khi cần, kiểm tra cả side effect ở service hoặc persistence layer.
5. Tránh để test phụ thuộc dữ liệu hoặc trạng thái còn lại từ test trước.
6. Chỉ dùng context hierarchy khi ứng dụng thực sự có root context và servlet context riêng.

## 11. Các lỗi thường gặp khi nạp cấu hình MVC

**Không khai báo `@WebAppConfiguration`.**

Khi test cần `WebApplicationContext` nhưng chỉ dùng `@ContextConfiguration` thông thường, Spring có thể tạo application context không phải web context. Việc inject `WebApplicationContext` hoặc xây dựng `MockMvc` theo web context khi đó không đúng loại context. Hãy khai báo `@WebAppConfiguration` cho kiểm thử Spring MVC thuần.

**Có `@WebAppConfiguration` nhưng thiếu nguồn cấu hình.**

Annotation này xác định loại context và môi trường web giả lập; nó không tự tìm mọi controller trong dự án. Cần khai báo `@ContextConfiguration` với Java config hoặc XML config phù hợp.

**Component scan sai package.**

Context được tạo thành công nhưng controller không được đăng ký, dẫn đến request trả 404. Kiểm tra package của marker class, phạm vi `@ComponentScan` và annotation của controller.

**Không bật hoặc không nạp cấu hình MVC.**

Với Java configuration thuần, cấu hình thường cần `@EnableWebMvc` cùng `WebMvcConfigurer` nếu muốn tùy chỉnh MVC. Với XML, cần khai báo namespace và thành phần MVC tương ứng. Không giả định rằng chỉ cần tạo `WebApplicationContext` là toàn bộ MVC infrastructure đã được đăng ký.

**Dùng `standaloneSetup` trong test được kỳ vọng kiểm tra cấu hình toàn ứng dụng.**

`standaloneSetup` tạo hạ tầng tối thiểu quanh controller được truyền vào. Nếu cần xác nhận `@ControllerAdvice`, converter, interceptor hoặc handler mapping từ cấu hình ứng dụng, hãy dùng `webAppContextSetup` hoặc cơ chế test tương ứng của Spring Boot.

**Thiếu dependency hoặc converter cần thiết.**

Một controller trả JSON cần message converter tương ứng. Kiểm tra dependency Jackson hoặc converter tùy chỉnh có mặt trên test runtime classpath và đã được cấu hình trong context.

**Bỏ qua filter trong test.**

Request qua `MockMvc` có thể không phản ánh bảo mật hoặc filter thực tế nếu filter chain chưa được đăng ký. Kiểm tra cấu hình filter và Spring Security khi endpoint phụ thuộc chúng.

**Nhầm `MockMvc` với server đang chạy.**

`webAppContextSetup` sử dụng servlet API giả lập và `DispatcherServlet` trong môi trường test. Nó không tự khởi động Tomcat, Jetty hoặc một server thật, cũng không kiểm tra việc bind cổng hay kết nối qua mạng. Nếu cần xác nhận toàn bộ ứng dụng qua HTTP thật, hãy dùng test với web environment phù hợp, chẳng hạn `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` trong Spring Boot.

## 12. Quy trình chọn và triển khai kiểm thử

Khi viết một bài kiểm thử Spring MVC, trước tiên xác định điều muốn xác nhận:

| Mục tiêu | Hướng triển khai |
| --- | --- |
| Kiểm tra logic của một controller với cấu hình tối thiểu | `standaloneSetup(controller)` |
| Kiểm tra controller cùng MVC config, advice, converter và interceptor | Nạp `WebApplicationContext`, sau đó dùng `webAppContextSetup(wac)` |
| Kiểm tra MVC slice của ứng dụng Spring Boot | `@WebMvcTest` |
| Kiểm tra tích hợp rộng với application context của Spring Boot qua MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Kiểm tra ứng dụng qua HTTP thật và server thật | Spring Boot test với `RANDOM_PORT` hoặc môi trường triển khai kiểm thử tương ứng |

Với kiểm thử Spring MVC thuần, trình tự triển khai thường là:

1. Tạo Java configuration hoặc XML configuration chứa MVC setup của ứng dụng.
2. Gắn `@ExtendWith(SpringExtension.class)` để tích hợp JUnit Jupiter với Spring Test.
3. Gắn `@WebAppConfiguration` để yêu cầu Spring tạo web application context.
4. Khai báo `@ContextConfiguration` để chỉ định nguồn cấu hình cần nạp.
5. Inject `WebApplicationContext` vào test.
6. Dùng `MockMvcBuilders.webAppContextSetup(webApplicationContext).build()` để tạo `MockMvc`.
7. Gửi request bằng `perform(...)` và kiểm tra status, header, body cùng các tác động liên quan.

Khi test thất bại, hãy đọc lỗi theo tầng: context có khởi tạo được không; controller có được đăng ký không; route có khớp không; request có bind được không; converter có ghi được response không; exception có được advice xử lý không; filter có chặn request không. Cách phân tầng này giúp xác định cấu hình nào chưa được nạp hoặc chưa được kết nối.

## Kết luận

`WebApplicationContext` là môi trường Spring dành cho ứng dụng web, chứa các bean MVC và gắn với `ServletContext`. Trong Spring Framework Testing, kết hợp `@WebAppConfiguration`, `@ContextConfiguration` và `MockMvcBuilders.webAppContextSetup(...)` giúp kiểm tra request qua cấu hình Spring MVC đã nạp.

Phương pháp này phù hợp khi cần xác nhận nhiều thành phần web phối hợp đúng: mapping, controller, converter, exception advice, interceptor và dependency injection. `MockMvc` vẫn chạy trong môi trường servlet giả lập, vì vậy nó kiểm tra tích hợp Spring MVC mà không thay thế một bài kiểm thử HTTP trên server thật. Hãy chọn `standaloneSetup`, web application context, Boot MVC slice hoặc full Boot context theo đúng phạm vi cần xác nhận.
