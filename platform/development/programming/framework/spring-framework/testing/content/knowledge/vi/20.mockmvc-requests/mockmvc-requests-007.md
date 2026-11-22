# Locale và kiểm thử thông báo được bản địa hóa

Trong ứng dụng Spring MVC, cùng một request có thể cần trả thông báo bằng nhiều ngôn ngữ. Ví dụ, `/api/greeting` trả `Hello` khi người dùng chọn tiếng Anh và `Bonjour` khi request sử dụng tiếng Pháp. Khi kiểm thử bằng MockMvc, cần xác nhận cả hai bước: Spring chọn đúng locale cho request và `MessageSource` tìm đúng bản dịch cho locale đó.

Locale là thông tin về ngôn ngữ và quy ước vùng miền, chẳng hạn `fr`, `fr-CA`, `en-US`. Nó ảnh hưởng đến việc chọn resource bundle, định dạng số/ngày tháng và nội dung thông báo. Locale không đồng nghĩa với timezone; một người dùng có thể dùng locale `en-GB` nhưng timezone ở một khu vực khác.

## Luồng xử lý locale trong Spring MVC

Một request được bản địa hóa thường đi qua các bước sau:

1. Request mang thông tin ngôn ngữ ưu tiên, thường qua HTTP `Accept-Language`, hoặc locale đã được lưu trong session/cookie.
2. `DispatcherServlet` dùng `LocaleResolver` của ứng dụng để xác định locale cho request.
3. Spring gắn locale context vào request hiện tại; `LocaleContextHolder` cho phép code đang chạy trong request lấy locale đó.
4. Controller hoặc service truyền locale vào `MessageSource` để lấy thông báo phù hợp.
5. Controller trả kết quả đã được bản địa hóa; MockMvc kiểm tra nội dung response.

Hai thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `LocaleResolver` | Xác định locale được sử dụng cho request và, tùy implementation, có thể lưu thay đổi locale |
| `MessageSource` | Tìm nội dung thông báo theo message code, tham số và locale |

Nếu resolver chọn sai locale, `MessageSource` có thể hoạt động đúng nhưng vẫn trả bản dịch không mong muốn. Ngược lại, resolver có thể chọn đúng locale nhưng resource bundle thiếu khóa tương ứng. Vì vậy, test nên kiểm tra response cuối cùng thay vì chỉ kiểm tra một trong hai thành phần.

## Chuẩn bị resource bundle

Spring thường dùng các file properties làm resource bundle. Giả sử ứng dụng có các file trong `src/main/resources/i18n/`:

`messages.properties`:

```properties
greeting.message=Hello
greeting.welcome=Welcome, {0}.
product.name.required=Product name is required.
```

`messages_fr.properties`:

```properties
greeting.message=Bonjour
greeting.welcome=Bienvenue, {0}.
product.name.required=Le nom du produit est obligatoire.
```

`messages_fr_CA.properties`:

```properties
greeting.message=Allô
greeting.welcome=Bienvenue, {0}.
```

Tên file biểu diễn locale: `messages_fr.properties` dành cho tiếng Pháp nói chung, còn `messages_fr_CA.properties` dành cho tiếng Pháp tại Canada. Khi locale là `fr-CA`, resource bundle cụ thể có thể được chọn trước; nếu một khóa không tồn tại ở bundle cụ thể, cơ chế fallback của resource bundle có thể tìm khóa ở bundle ngôn ngữ cha rồi đến bundle mặc định.

`MessageSource` hỗ trợ tham số theo cú pháp `MessageFormat`. Ví dụ `greeting.welcome=Welcome, {0}.` cho phép truyền tên người dùng khi lấy thông báo. Nội dung bản dịch cần giữ đúng số lượng và thứ tự placeholder để tránh hiển thị sai dữ liệu.

### Cấu hình MessageSource trong Spring Boot

Spring Boot có thể tự cấu hình `MessageSource` từ các thuộc tính:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Nên có `messages.properties` làm bundle mặc định để cơ chế tự cấu hình message source của Boot được kích hoạt. Đặt `fallback-to-system-locale=false` giúp kết quả test không phụ thuộc locale của máy đang chạy test. Nếu không tắt fallback này, môi trường có system locale khác nhau có thể làm thay đổi bundle được chọn khi không tìm thấy bản dịch cụ thể.

### Cấu hình MessageSource trong Spring MVC thuần

Với ứng dụng không dùng Spring Boot, đăng ký bean có tên `messageSource`:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ResourceBundleMessageSource;

@Configuration
class MessageConfig {

    @Bean
    MessageSource messageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("i18n/messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }
}
```

Tên bean `messageSource` có ý nghĩa đặc biệt trong ApplicationContext: Spring dùng bean này làm nguồn thông báo mặc định. Khi đổi basename, hãy bảo đảm đường dẫn tương ứng với vị trí resource trên classpath và không thêm đuôi `.properties` vào basename.

## Chọn locale bằng Accept-Language

Với ứng dụng stateless, cách phổ biến là dùng `AcceptHeaderLocaleResolver`. Resolver đọc locale ưu tiên của request, vốn được servlet container cung cấp dựa trên header `Accept-Language`. Có thể cấu hình danh sách locale được hỗ trợ và locale mặc định:

```java
import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
class WebLocaleConfig {

    @Bean
    LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        resolver.setSupportedLocales(List.of(
                Locale.ENGLISH,
                Locale.FRENCH,
                Locale.CANADA_FRENCH
        ));
        return resolver;
    }
}
```

Spring MVC tìm resolver theo bean name `localeResolver`. Nếu không khai báo resolver riêng, chiến lược mặc định của `DispatcherServlet` là `AcceptHeaderLocaleResolver`. Khi cần hành vi xác định cho test, nên khai báo rõ resolver, danh sách locale được hỗ trợ và locale mặc định.

`AcceptHeaderLocaleResolver` không hỗ trợ thay đổi locale bằng cách gọi `setLocale`, vì header là thông tin do client gửi. Nếu ứng dụng cần cho người dùng đổi ngôn ngữ bằng một tham số như `?lang=fr` và lưu lựa chọn đó cho request tiếp theo, hãy dùng resolver có trạng thái như `SessionLocaleResolver` hoặc `CookieLocaleResolver`.

### Lấy locale trong controller hoặc service

`DispatcherServlet` thiết lập locale context trong thời gian xử lý request. Code có thể đọc locale hiện tại bằng `LocaleContextHolder`:

```java
import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    private final MessageSource messages;

    GreetingController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/api/greeting")
    GreetingResponse greeting() {
        Locale locale = LocaleContextHolder.getLocale();
        String message = messages.getMessage(
                "greeting.message", null, locale);
        return new GreetingResponse(message);
    }
}

record GreetingResponse(String message) {}
```

`LocaleContextHolder` dùng context gắn với request hiện tại khi request được xử lý bởi Spring MVC. Không nên tự đặt locale vào static holder trong test rồi quên khôi phục, vì giá trị đó có thể ảnh hưởng test khác hoặc request khác trên cùng thread. Hãy để `DispatcherServlet` thiết lập và dọn locale context theo vòng đời request.

## Kiểm thử locale bằng MockMvc

Khi dùng MockMvc, phương thức `.locale(...)` trên request builder đặt các locale ưu tiên của mock servlet request. Đây là cách ổn định để mô phỏng locale mà `HttpServletRequest#getLocale()` cung cấp cho `AcceptHeaderLocaleResolver`.

Ví dụ sau dùng application context của Spring Boot và dựng MockMvc trực tiếp từ `WebApplicationContext`:

```java
import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest
class GreetingLocaleMvcTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = webAppContextSetup(webApplicationContext).build();
    }

    @Test
    void returnsFrenchMessage() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .locale(Locale.FRENCH)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Bonjour"));
    }

    @Test
    void returnsCanadianFrenchMessage() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .locale(Locale.CANADA_FRENCH))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Allô"));
    }

    @Test
    void usesDefaultLocaleForUnsupportedLanguage() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .locale(Locale.JAPANESE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello"));
    }
}
```

Các assertion kiểm tra message cuối cùng được trả về. Test thứ ba xác nhận hành vi khi locale không nằm trong danh sách hỗ trợ: resolver dùng locale mặc định đã cấu hình là tiếng Anh.

`.locale(Locale.FRENCH)` thiết lập preferred locale ở lớp mock servlet request; nó không phải là một bài kiểm thử parser HTTP của servlet container đối với chuỗi header thô, bao gồm cả trọng số `q`. Nếu cần kiểm tra việc container thực sự diễn giải `Accept-Language` trên HTTP, hãy bổ sung kiểm thử chạy ứng dụng trên server thật. Với kiểm thử MVC qua MockMvc, `.locale(...)` là cách trực tiếp để xác nhận cách Spring xử lý locale đã được servlet request phân giải.

## Kiểm thử tham số trong thông báo

Thông báo thường có placeholder để chèn tên, số lượng hoặc giá trị nghiệp vụ. Controller có thể truyền đối số vào `MessageSource`:

```java
@GetMapping("/api/greeting/{name}")
GreetingResponse greeting(@PathVariable String name) {
    Locale locale = LocaleContextHolder.getLocale();
    String message = messages.getMessage(
            "greeting.welcome", new Object[]{name}, locale);
    return new GreetingResponse(message);
}
```

MockMvc kiểm tra cả bản dịch và tham số đã được thay thế:

```java
mockMvc.perform(get("/api/greeting/{name}", "Mai")
                .locale(Locale.FRENCH))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.message")
                .value("Bienvenue, Mai."));
```

Nên dùng tên người dùng hoặc giá trị test ổn định để assertion không phụ thuộc dữ liệu bên ngoài. Khi bản dịch dùng dấu nháy đơn hoặc cú pháp `MessageFormat`, cần kiểm tra quy tắc escape của `MessageFormat`; một dấu nháy đơn chưa escape có thể làm thay đổi cách diễn giải placeholder.

## Đổi locale bằng session và LocaleChangeInterceptor

Một số ứng dụng cho phép người dùng chọn ngôn ngữ từ giao diện. Trong trường hợp đó, `LocaleChangeInterceptor` có thể đọc tham số request và yêu cầu `LocaleResolver` cập nhật locale. `SessionLocaleResolver` lưu lựa chọn trong HTTP session để request sau tiếp tục dùng locale đó.

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
class SessionLocaleConfig implements WebMvcConfigurer {

    @Bean
    LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }

    @Bean
    LocaleChangeInterceptor localeChangeInterceptor() {
        LocaleChangeInterceptor interceptor =
                new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        return interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(localeChangeInterceptor());
    }
}
```

Trong cấu hình này, request có `?lang=fr` yêu cầu chuyển sang tiếng Pháp. `LocaleChangeInterceptor` gọi `setLocale` trên resolver. Vì resolver là `SessionLocaleResolver`, lựa chọn được lưu trong session. Không dùng cấu hình này cùng `AcceptHeaderLocaleResolver`, vì resolver dựa trên header không thể ghi đè locale do client gửi.

MockMvc có thể kiểm tra trạng thái locale qua hai request dùng chung một `MockHttpSession`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void keepsSelectedLocaleInSession() throws Exception {
    MockHttpSession session = new MockHttpSession();

    // Request đầu tiên yêu cầu đổi locale và lưu lựa chọn vào session.
    mockMvc.perform(get("/api/greeting")
                    .param("lang", "fr")
                    .session(session))
            .andExpect(status().isOk());

    // Request tiếp theo dùng cùng session nên nhận locale tiếng Pháp.
    mockMvc.perform(get("/api/greeting").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Bonjour"));
}
```

Điểm cần giữ nguyên trong test là cùng một đối tượng session được gắn vào cả hai request. Nếu tạo session mới cho request thứ hai, test không còn kiểm tra việc lưu locale qua session. Cũng nên kiểm tra locale ở request tiếp theo, vì đó là bằng chứng rõ ràng rằng resolver đã lưu lựa chọn và sử dụng lại nó.

`CookieLocaleResolver` là lựa chọn khác khi muốn lưu lựa chọn locale trong cookie thay vì session. Với resolver này, test cần gửi cookie nhận được từ response trước vào request tiếp theo, đồng thời kiểm tra thuộc tính cookie nếu đó là một phần của hợp đồng ứng dụng.

## Kiểm thử thông báo validation được bản địa hóa

Thông báo validation cũng cần đúng locale. Ví dụ DTO khai báo message code thay vì viết cứng câu tiếng Anh:

```java
import jakarta.validation.constraints.NotBlank;

class CreateProductRequest {

    @NotBlank(message = "{product.name.required}")
    private String name;

    // Constructor, getter và setter theo yêu cầu của ứng dụng.
}
```

Khi dùng Spring MVC thuần, có thể cấu hình `LocalValidatorFactoryBean` để lấy thông báo từ cùng `MessageSource`:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ValidationMessageConfig implements WebMvcConfigurer {

    private final LocalValidatorFactoryBean validator;

    ValidationMessageConfig(MessageSource messageSource) {
        validator = new LocalValidatorFactoryBean();
        validator.setValidationMessageSource(messageSource);
    }

    @Bean
    LocalValidatorFactoryBean applicationValidator() {
        return validator;
    }

    @Override
    public Validator getValidator() {
        return validator;
    }
}
```

Trong Spring Boot, validation thường được cấu hình tự động khi có validation provider trên classpath. Nếu muốn chắc chắn message code của Bean Validation lấy từ bundle ứng dụng, hãy cấu hình tích hợp `LocalValidatorFactoryBean` với `MessageSource` theo cấu hình validator của dự án.

Controller có thể nhận DTO với `@Valid` và chuyển lỗi validation thành response thông qua `@RestControllerAdvice`. Ví dụ response lỗi có trường `message` chứa nội dung đã bản địa hóa. Test gửi request không hợp lệ với locale tiếng Pháp:

```java
mockMvc.perform(post("/api/products")
                .locale(Locale.FRENCH)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":""}
                        """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.message")
                .value("Le nom du produit est obligatoire."));
```

Assertion này giả định exception handler của ứng dụng trả lỗi theo cấu trúc JSON có trường `message`. Nếu ứng dụng trả danh sách lỗi theo field, hãy assert vào đúng đường dẫn JSON, ví dụ `$.errors[0].message`. Điều quan trọng là kiểm tra câu thông báo thực tế mà client nhận được.

## Locale ảnh hưởng đến định dạng dữ liệu

Thông báo không phải phần duy nhất được bản địa hóa. Một số API hoặc trang HTML có thể hiển thị số, tiền tệ và ngày tháng theo locale. Ví dụ số thập phân có thể dùng dấu phẩy trong locale Pháp và dấu chấm trong locale Anh. Khi ứng dụng chủ động định dạng giá trị theo locale, hãy kiểm thử kết quả ở ranh giới response:

```java
NumberFormat formatter = NumberFormat.getNumberInstance(locale);
String formatted = formatter.format(1234.5);
```

Không nên giả định mọi client muốn nhận số đã định dạng trong JSON. Với API, kiểu số JSON thường nên giữ nguyên giá trị số để client tự định dạng; chỉ kiểm tra chuỗi định dạng khi đó là hợp đồng response có chủ ý của ứng dụng. Với HTML hoặc thông báo văn bản, định dạng theo locale thường phù hợp hơn.

Locale cũng không tự thay đổi timezone. Nếu thông báo chứa thời điểm, hãy xác định rõ ứng dụng dùng timezone nào và kiểm thử timezone riêng với locale. Tránh để test phụ thuộc timezone mặc định của máy.

## Lỗi thường gặp khi kiểm thử locale

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Request tiếng Pháp vẫn trả thông báo tiếng Anh | Resolver không nhận locale mong muốn hoặc locale không nằm trong danh sách hỗ trợ | Kiểm tra `LocaleResolver`, danh sách supported locales và request builder `.locale(...)` |
| Locale đúng nhưng message không được dịch | Thiếu file bundle hoặc message code không khớp | Kiểm tra basename, tên file và khóa message |
| Test khác nhau giữa máy local và CI | Fallback theo system locale hoặc timezone mặc định | Cấu hình fallback rõ ràng và đặt timezone test có chủ ý |
| Tham số trong thông báo không xuất hiện đúng | Placeholder hoặc đối số `MessageFormat` không khớp | Kiểm tra `{0}`, `{1}` và escape dấu nháy |
| `LocaleChangeInterceptor` ném lỗi khi đổi locale | Đang dùng `AcceptHeaderLocaleResolver` | Chọn `SessionLocaleResolver`, `CookieLocaleResolver` hoặc resolver hỗ trợ `setLocale` |
| Request thứ hai trở về locale mặc định | Test tạo session mới hoặc không gửi lại cookie | Dùng lại cùng `MockHttpSession` hoặc gửi cookie của request trước |
| Validation luôn hiện thông báo mặc định | Validator chưa tích hợp với `MessageSource` hoặc message code không tồn tại | Cấu hình `LocalValidatorFactoryBean` và bundle validation |
| Test tự đặt `LocaleContextHolder` làm test khác bị ảnh hưởng | Locale context không được khôi phục | Để `DispatcherServlet` quản lý context trong MockMvc request |

## Cách tổ chức test suite

Nên tách test theo cơ chế chọn locale và theo kết quả bản địa hóa cần bảo vệ:

- Với `AcceptHeaderLocaleResolver`, kiểm tra locale được hỗ trợ, locale vùng miền cụ thể và locale mặc định khi request gửi ngôn ngữ không hỗ trợ.
- Với `SessionLocaleResolver` hoặc `CookieLocaleResolver`, kiểm tra lựa chọn được lưu và dùng lại ở request tiếp theo.
- Với `MessageSource`, kiểm tra các message code quan trọng, tham số thay thế và fallback bundle.
- Với validation hoặc exception handler, gửi request lỗi và xác nhận response chứa thông báo đúng ngôn ngữ.
- Với ngày, giờ và số đã định dạng, kiểm tra locale và timezone theo hợp đồng hiển thị của ứng dụng.

Một bài MockMvc test tốt đi qua `DispatcherServlet` với cấu hình locale và message source của application context, gửi request có locale xác định, rồi kiểm tra nội dung response mà người dùng thực sự nhận được. Cách này phát hiện được cả lỗi chọn locale lẫn lỗi tra cứu bản dịch trong cùng luồng xử lý MVC.
