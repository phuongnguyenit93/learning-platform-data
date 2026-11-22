# Quan hệ giữa spring.mvc.*, spring.web.* và cấu hình Spring MVC bằng Java

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot dùng **Spring MVC (Servlet stack)**, một hành vi HTTP có thể được điều chỉnh bằng ba lớp khác nhau:

1. **`spring.mvc.*`**: các property dành riêng cho Spring MVC như định dạng tham số ngày/giờ, content negotiation, mapping của tài nguyên tĩnh, cấu hình DispatcherServlet và xử lý lỗi theo MVC.
2. **`spring.web.*`**: các property web dùng ở phạm vi rộng hơn, nổi bật là locale và hệ thống tài nguyên tĩnh (vị trí file, cache HTTP, resource chain). Một số nhóm được cả MVC và WebFlux sử dụng.
3. **Cấu hình Java**: `@Configuration`, `WebMvcConfigurer`, `Converter`, `Formatter`, `HttpMessageConverter`, `HandlerInterceptor`, `WebMvcRegistrations` và các bean mở rộng cụ thể.

Ba lớp **không phải ba cơ chế cạnh tranh độc lập**. Spring Boot đọc property, tạo các bean auto-configuration, rồi cùng Spring Framework tổng hợp các cấu hình Java để dựng hạ tầng MVC. Hai thiết lập tưởng giống nhau có thể bổ sung, ghi đè, hoặc không ảnh hưởng nhau, tùy **thành phần và thứ tự cấu hình**.

Để minh họa nhất quán, ví dụ chạy được bên dưới dùng **Spring Boot 3.5.x, Spring MVC, Java 17+**. Đối với Spring Boot 4.x, nhiều tên property vẫn tồn tại nhưng starter và một số package của Boot đã thay đổi; cần đối chiếu tài liệu của phiên bản đang sử dụng.

## 2. Bản đồ các namespace cấu hình

| Nhóm property | Đối tượng chịu tác động chính | Ví dụ | Có thể mở rộng bằng Java |
|---|---|---|---|
| `spring.mvc.*` | Spring MVC và DispatcherServlet | `spring.mvc.format.date`, `spring.mvc.static-path-pattern`, `spring.mvc.contentnegotiation.*` | `WebMvcConfigurer`, `ConversionService`, `WebMvcRegistrations` |
| `spring.web.locale*` | Locale mặc định và cách xác định locale của request | `spring.web.locale`, `spring.web.locale-resolver` | Bean `LocaleResolver`, interceptor và cấu hình i18n |
| `spring.web.resources.*` | Xử lý tài nguyên tĩnh và HTTP caching | `spring.web.resources.static-locations`, `spring.web.resources.cache.period` | `WebMvcConfigurer.addResourceHandlers`, `ResourceHandlerRegistry` |
| `spring.webflux.*` | Spring WebFlux/reactive | `spring.webflux.static-path-pattern`, `spring.webflux.base-path` | `WebFluxConfigurer`; **không phải WebMvcConfigurer** |
| `server.*` | Embedded HTTP server và Servlet container | `server.port`, `server.servlet.context-path` | `WebServerFactoryCustomizer`, filter, servlet registration |
| `spring.servlet.multipart.*` | Cấu hình upload multipart | `spring.servlet.multipart.max-file-size` | `MultipartConfigElement` và các bean chuyên trách khi thật sự cần |
| `spring.jackson.*` trong Boot 3.5 | Cấu hình JSON serialization/deserialization bằng Jackson | `spring.jackson.default-property-inclusion` | `ObjectMapper`, `Jackson2ObjectMapperBuilderCustomizer` theo phiên bản |
| Các bean cấu hình ứng dụng | Logic riêng | `@Bean Converter<...>`, `WebMvcConfigurer` | Spring Framework gọi các hook tương ứng |

**Không phân loại chỉ dựa vào tên có chữ “web”:** `spring.mvc.static-path-pattern` quyết định **URL public** của file tĩnh trong MVC, còn `spring.web.resources.static-locations` quyết định **nơi tìm file**. Hai property phối hợp với nhau; không phải tên cũ và tên mới của cùng một tính năng.

`spring.web.resources.*` có thể phục vụ cả Servlet MVC và WebFlux, nhưng URL mapping lại tách riêng: MVC dùng `spring.mvc.static-path-pattern`, WebFlux dùng `spring.webflux.static-path-pattern`. Một ứng dụng MVC có WebClient không tự biến thành WebFlux; đừng cấu hình `spring.webflux.*` rồi kỳ vọng nó điều chỉnh `DispatcherServlet`.

## 3. Spring Boot biến property thành hạ tầng MVC như thế nào?

Một luồng cấu hình khái quát:

~~~text
application.properties / application.yaml / ENV / CLI
                  |
                  v
             Spring Environment
                  |
                  v
       @ConfigurationProperties binding
         WebMvcProperties / WebProperties
                  |
                  v
          WebMvcAutoConfiguration
              + Spring MVC
                  |
                  +-- các WebMvcConfigurer của Boot
                  +-- các WebMvcConfigurer do ứng dụng tạo
                  +-- các bean Converter / Formatter / ...
                  |
                  v
     RequestMappingHandlerMapping, HandlerAdapter,
     ConversionService, ResourceHttpRequestHandler,
     HandlerExceptionResolver, ...
                  |
                  v
             DispatcherServlet
                  |
                  v
             HTTP request/response
~~~

Trong Spring Boot 3.5, `WebMvcAutoConfiguration` dùng các điều kiện liên quan tới Servlet application, sự hiện diện của `DispatcherServlet` và `WebMvcConfigurer`, đồng thời chỉ áp dụng khi không có `WebMvcConfigurationSupport` do ứng dụng thay thế. Nó sử dụng cấu hình đã bind từ các lớp như `WebMvcProperties` và `WebProperties`.

Có thể hình dung các giai đoạn:

1. **Đọc và hợp nhất nguồn cấu hình** theo quy tắc externalized configuration của Boot. Profile, biến môi trường và CLI có thể thay đổi giá trị property mà không sửa source.
2. **Binding**: giá trị như `spring.mvc.static-path-pattern=/assets/**` được gán vào lớp property tương ứng. Nếu có lỗi binding nghiêm trọng, ứng dụng có thể không khởi động.
3. **Auto-configuration**: Boot thêm quy ước mặc định cùng những hook framework; các bean có điều kiện vẫn phụ thuộc classpath và application type.
4. **Java customization**: Spring MVC gọi các `WebMvcConfigurer` và các bean mở rộng. Tùy callback, chúng có thể thêm logic hoặc điều chỉnh cùng đối tượng từng được Boot cấu hình.
5. **Runtime verification**: chỉ quan sát request thực tế, bean đã tạo và HTTP response mới xác nhận kết quả cuối cùng.

**Không có quy tắc tổng quát “Java thắng property” hay “property thắng Java”.** Thứ tự áp dụng và điểm mở rộng quyết định kết quả. Cấu hình Java có thể bổ sung ở một khu vực không xung đột, ví dụ thêm interceptor, trong khi `spring.mvc.format.date` vẫn điều chỉnh conversion.

## 4. spring.mvc.*: những phần đặc trưng của MVC

### 4.1. Formatting của request parameters và model binding

~~~properties
spring.mvc.format.date=dd/MM/yyyy
spring.mvc.format.time=HH:mm:ss
spring.mvc.format.date-time=dd/MM/yyyy HH:mm:ss
~~~

Các pattern là quy ước formatting cho những kiểu date/time tương ứng khi Spring MVC bind/convert dữ liệu từ request vào tham số hoặc model, ví dụ `@RequestParam LocalDate`. Chúng **không mặc nhiên đổi JSON date format** của `@RequestBody` hoặc mọi giá trị do `ObjectMapper` serialize.

Ví dụ controller:

~~~java
@GetMapping("/api/day")
public String day(@RequestParam("value") java.time.LocalDate value) {
    return value.toString();
}
~~~

Với `spring.mvc.format.date=dd/MM/yyyy`, input `value=31/12/2026` có thể bind thành `LocalDate.of(2026, 12, 31)`, rồi method trả `2026-12-31`. Đoạn method là trích đoạn minh họa cần được đặt trong class `@RestController`.

Nếu muốn một endpoint dùng format khác mà không đổi toàn ứng dụng, có thể dùng annotation như `@DateTimeFormat` trên tham số; nếu muốn chuyển một kiểu domain từ String, có thể thêm `Converter` qua `WebMvcConfigurer.addFormatters`.

**Hai ConversionService khác nhau:** Spring MVC có conversion service riêng cho request binding; `@ConfigurationProperties` sử dụng cơ chế chuyển đổi cấu hình khác. Vì vậy không nên coi property dùng cho `Duration`, `DataSize` trong config là tương đương với cách parse request parameter MVC.

### 4.2. Content negotiation

Ví dụ cho phép client yêu cầu representation bằng query parameter khi thật sự cần:

~~~properties
spring.mvc.contentnegotiation.favor-parameter=true
spring.mvc.contentnegotiation.parameter-name=format
spring.mvc.contentnegotiation.media-types.markdown=text/markdown
~~~

Khi đó client có thể gửi `?format=markdown`; Spring MVC sẽ dùng content negotiation để lựa chọn media type theo cấu hình và những representation mà handler/converter thực sự hỗ trợ. **Property không tự tạo converter Markdown.** Nếu ứng dụng chỉ có JSON converter mà không có handler tạo `text/markdown`, thêm mapping media type không đủ để đáp ứng request dạng Markdown.

Mặc định Spring MVC ưu tiên `Accept` header để xác định requested media type. Nên hạn chế cách suy diễn content type từ phần mở rộng file trong URL vì dễ mơ hồ và có hệ quả bảo mật.

Tương đương bằng Java, có thể dùng:

~~~java
@Override
public void configureContentNegotiation(
        org.springframework.web.servlet.config.annotation.ContentNegotiationConfigurer configurer) {
    configurer.favorParameter(true)
            .parameterName("format")
            .mediaType("markdown", org.springframework.http.MediaType.parseMediaType("text/markdown"));
}
~~~

Đây chỉ là **đoạn method** cho class `WebMvcConfigurer`, không phải ứng dụng đầy đủ. Nếu viết cả property và Java config cho đúng cùng một thiết lập, cần xem cách mỗi configurer áp dụng và thứ tự cấu hình; không nên dùng hai nguồn tương phản chỉ để dự đoán một nguồn sẽ thắng.

### 4.3. Servlet path và static resource URL

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

Từ đó `src/main/resources/static/logo.svg` thường được phục vụ ở `/assets/logo.svg`, nếu các default static locations còn được dùng. Property **không đổi các controller mappings** như `@GetMapping("/api/status")`.

Ngoài ra có:

~~~properties
spring.mvc.servlet.path=/
~~~

Nó liên quan tới đường mapping của `DispatcherServlet`, **khác** `server.servlet.context-path` (context root của ứng dụng trong Servlet container) và khác `spring.mvc.static-path-pattern` (URL matching cho resource handler). Đặc biệt ở Boot 3.5, dùng `spring.mvc.servlet.path` khác mặc định có ràng buộc tương thích với chiến lược `PathPatternParser`; hãy theo đúng tài liệu về path matching khi cần thay servlet path.

### 4.4. Một số property MVC khác

| Property ở Spring Boot 3.5 | Ý nghĩa |
|---|---|
| `spring.mvc.pathmatch.matching-strategy` | Chọn cách match mapping của request; mặc định `path-pattern-parser` |
| `spring.mvc.async.request-timeout` | Timeout xử lý request bất đồng bộ của MVC |
| `spring.mvc.hiddenmethod.filter.enabled` | Bật/tắt HiddenHttpMethodFilter cho việc override method của form |
| `spring.mvc.formcontent.filter.enabled` | Bật/tắt FormContentFilter cho body dạng form ở các HTTP method thích hợp |
| `spring.mvc.problemdetails.enabled` | Hỗ trợ Problem Details khi xử lý một số lỗi theo MVC |
| `spring.mvc.message-codes-resolver-format` | Cách tạo message codes cho binding errors |
| `spring.mvc.view.prefix` và `spring.mvc.view.suffix` | Phục vụ cách resolve view name phù hợp, không điều chỉnh `@ResponseBody` |
| `spring.mvc.log-request-details` | Cho phép log chi tiết request ở DEBUG/TRACE; có thể chứa dữ liệu nhạy cảm, không bật vô tội vạ |

Những property này là ví dụ, không phải danh sách bất biến cho mọi Boot version. Các cơ chế MVC có thể bị thay đổi nếu ứng dụng tự khai báo những bean infrastructure có tác dụng thay thế.

## 5. spring.web.*: locale và tài nguyên dùng chung

### 5.1. Locale

~~~properties
spring.web.locale=vi_VN
spring.web.locale-resolver=accept-header
~~~

Theo mặc định, `accept-header` ưu tiên giá trị từ HTTP `Accept-Language`; locale đã cấu hình là giá trị dự phòng. Nếu muốn luôn cố định locale bất kể header:

~~~properties
spring.web.locale=vi_VN
spring.web.locale-resolver=fixed
~~~

Hai cách xử lý tương ứng với chính sách khác nhau: đa ngôn ngữ theo client hoặc giao diện dùng một locale cố định. `spring.web.locale` không tự dịch những string mà controller đã hard-code. Muốn i18n thật, cần message bundles, `MessageSource`, khả năng resolve locale và cách tạo message theo locale.

Có thể đăng ký bean `LocaleResolver` riêng trong Java khi cần policy phức tạp, nhưng khi đó phải rà soát việc bean tùy chỉnh tương tác với auto-configuration của Boot. Không khai báo một bean custom rồi vẫn kỳ vọng mọi tùy chọn `spring.web.locale-resolver` chắc chắn quyết định hành vi cuối.

### 5.2. Physical locations của file tĩnh

~~~properties
spring.web.resources.static-locations=classpath:/site/
~~~

Đây là **vị trí tìm file trên classpath**, không phải URL. Thuộc tính này thay thế danh sách location mặc định; theo tài liệu Servlet Boot, root của ServletContext cũng có thể được thêm như một location. Các location mặc định thông thường là `classpath:/META-INF/resources/`, `classpath:/resources/`, `classpath:/static/` và `classpath:/public/`.

Nếu thư mục `src/main/resources/site/` có `hello.txt`, và `spring.mvc.static-path-pattern=/assets/**`, Spring MVC có thể phục vụ tài nguyên tại `GET /assets/hello.txt`. Ngược lại, `GET /site/hello.txt` không phải URL được bảo đảm chỉ vì thư mục bên trong tên `site`.

### 5.3. Cache và resource chain

~~~properties
spring.web.resources.cache.period=3600s
spring.web.resources.cache.cachecontrol.cache-public=true
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
~~~

Các property điều chỉnh xử lý **static resources** qua handler được Boot cấu hình: cache headers, chiến lược version theo nội dung và resource chain. Chúng không tự thiết lập cache cho mọi API JSON của controller.

Lưu ý:

- `spring.web.resources.cache.period` là thời gian caching; nếu có `cache.cachecontrol.*`, cấu hình Cache-Control chi tiết có thể ghi đè behavior của period.
- `spring.web.resources.chain.strategy.content.enabled=true` giúp resource handling có chiến lược version theo content. Việc rewrite URL trong HTML/template còn cần cơ chế tích hợp template/filter phù hợp; không tự suy ra URL trong bất kỳ chuỗi HTML nào đều được sửa.
- `spring.web.resources.add-mappings=false` tắt **default static resource mappings** do Boot tạo. Một `WebMvcConfigurer.addResourceHandlers` viết thủ công vẫn có thể đăng ký resource handler riêng.
- Nếu tự đăng ký handler cho đúng một pattern đã được Boot quản lý, cần kiểm tra kết quả và thứ tự; config Java có thể làm Boot bỏ qua mapping mặc định cho pattern đó, khiến cache/locations từ property không còn tự được áp dụng như bạn tưởng.

### 5.4. WebFlux dùng lại phần tài nguyên nhưng Java config khác

Ứng dụng WebFlux cũng sử dụng `spring.web.resources.static-locations` cho việc tìm file. Tuy nhiên URL mapping của WebFlux dùng `spring.webflux.static-path-pattern` và extension API là `WebFluxConfigurer`, không phải `WebMvcConfigurer`. Vì thế:

- `spring.web.resources.static-locations` không phải property chỉ dành riêng cho Spring MVC.
- `spring.mvc.static-path-pattern` chỉ áp dụng cho Spring MVC.
- `spring.webflux.static-path-pattern` chỉ áp dụng cho reactive WebFlux.
- Đừng nhìn thấy Netty trong classpath rồi quyết định ứng dụng đang chạy WebFlux; HTTP client Netty có thể tồn tại bên cạnh Spring MVC Servlet stack.

## 6. Cấu hình Java: ba mức độ can thiệp

### Mức 1 — Bean hoặc WebMvcConfigurer bổ sung

Khi muốn thêm interceptor, formatter, CORS mapping, view controller hay resource mapping mới:

~~~java
@Configuration(proxyBeanMethods = false)
public class MyMvcConfiguration implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MyInterceptor())
                .addPathPatterns("/api/**");
    }
}
~~~

Đây là trích đoạn, cần class `MyInterceptor` và imports tương ứng. Boot tiếp tục quản lý MVC defaults. **Không đặt `@EnableWebMvc`** chỉ để thêm `WebMvcConfigurer`.

Một số hook thường dùng:

| Hook trong WebMvcConfigurer | Mục tiêu | Lưu ý |
|---|---|---|
| `addInterceptors` | Thêm `HandlerInterceptor` trước/sau handler | Không thay thế Spring Security filter chain |
| `addFormatters` | Thêm `Converter`/`Formatter` | Cẩn thận định dạng toàn cục ảnh hưởng binding |
| `addCorsMappings` | Cấu hình CORS cho MVC handlers | Không thay thế kiểm soát xác thực/phân quyền |
| `addArgumentResolvers` | Thêm đối số controller tùy chỉnh | Không được thiết kế để thay thế toàn bộ built-in resolvers |
| `addResourceHandlers` | Bổ sung mapping file tĩnh | Tránh trùng URL patterns với mappings hiện có |
| `configureContentNegotiation` | Thay cơ chế chọn media type | Có thể tác động cùng cấu hình `spring.mvc.contentnegotiation.*` |
| `extendMessageConverters` | Chỉnh danh sách converters hiện có | Thường an toàn hơn thao tác thay thế toàn bộ |
| `configureMessageConverters` | Cấu hình danh sách converters | Hiểu rõ cách Boot góp defaults trước khi thay cả danh sách |
| `addViewControllers` | Tạo route đơn giản tới view hoặc redirect | Không áp dụng khi cần business logic phức tạp |

### Mức 2 — Thay một phần hạ tầng bằng bean chuyên biệt

Nếu muốn thay một implementation chính như `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter` hoặc `ExceptionHandlerExceptionResolver` mà vẫn giữ các tùy chỉnh Spring Boot, tài liệu gợi ý `WebMvcRegistrations` ở những trường hợp phù hợp. Các component được tạo vẫn chịu xử lý tiếp bởi Spring MVC và các customizer.

Đây là lựa chọn nâng cao. Khi thay một bean hạ tầng, không được giả định property binding và mọi hook giữ nguyên như khi dùng class mặc định. Đặc biệt cần test handler mappings, validation, formatters, error handling, resource serving và startup.

### Mức 3 — Toàn quyền MVC với @EnableWebMvc

~~~java
@Configuration
@EnableWebMvc
public class FullControlMvcConfiguration implements WebMvcConfigurer {
    // Ứng dụng tự chịu trách nhiệm cấu hình MVC cần thiết.
}
~~~

**Đây là ví dụ về thay đổi cơ chế, không phải cấu hình khuyến nghị cho dự án Spring Boot phổ thông.** `@EnableWebMvc` đưa `WebMvcConfigurationSupport` vào context và làm `WebMvcAutoConfiguration` của Boot nhường chỗ. Ứng dụng phải chủ động rà soát nhiều tính năng Boot từng thiết lập như default resource handlers, conversion, view resolvers và converter customization. MVC của Spring Framework vẫn có những default riêng, vì vậy không nói rằng mọi handler hoặc JSON converter chắc chắn biến mất; nhưng **các bổ sung của Boot không còn được giữ nguyên tự động**.

Nếu chỉ cần một interceptor, converter hay path mapping, dùng `WebMvcConfigurer` **không kèm `@EnableWebMvc`**.

## 7. “Property hay Java ưu tiên hơn?” — giải quyết theo cơ chế, không theo khẩu hiệu

| Tình huống | Kết luận an toàn |
|---|---|
| Đặt `spring.mvc.format.date=dd/MM/yyyy`, Java chỉ thêm interceptor | Hai cấu hình thường cùng hoạt động vì tác động khác thành phần |
| Đặt `spring.web.resources.static-locations`, Java thêm resource mapping **khác** pattern | Default resource mapping và custom mapping có thể cùng tồn tại |
| Đặt `spring.mvc.static-path-pattern=/assets/**`, Java lại đăng ký chính `/assets/**` | Có khả năng xung đột hoặc một mapping được chọn; kiểm tra registry và HTTP thực tế |
| Đặt `spring.web.locale-resolver=fixed` và tự tạo bean `LocaleResolver` | Custom bean có thể làm thay đổi cơ chế được Boot chọn; kiểm tra bean thực tế |
| Đặt `spring.mvc.contentnegotiation.*` và Java cũng đổi content negotiation | Kết quả tùy cách các configurer bổ sung/override và thứ tự |
| Khai báo `@EnableWebMvc` trong ứng dụng Boot | Boot MVC auto-configuration nhường chỗ; không mặc định áp dụng đầy đủ `spring.mvc.*` và `spring.web.resources.*` như trước |
| Đặt `server.port=9090` và Java `WebMvcConfigurer` | WebMvcConfigurer không phải công cụ đổi cổng embedded server; `server.port` thuộc tầng server |
| Đổi JSON field naming bằng `spring.mvc.format.date` | Sai tầng; cần cấu hình JSON serialization/deserialization riêng |

**Hai kiểu “ưu tiên” khác nhau:**

1. **Ưu tiên giữa nguồn external config**: `application.properties`, profile, environment variables, command line, test properties... được Spring Boot hợp nhất theo thứ tự ưu tiên cấu hình.
2. **Ưu tiên giữa các thành phần Java và auto-configuration**: Spring sử dụng conditional bean creation, callback ordering và API registration. Đây không phải quy tắc nguồn property trên thắng một `@Bean` dưới.

Khi gặp xung đột thực tế, hãy xác định **bean/hook nào tạo behavior** rồi kiểm tra runtime; đừng kết luận chỉ từ việc nhìn thấy hai dòng config.

## 8. Ví dụ hoàn chỉnh: Boot 3.5 + Java 17 + property và WebMvcConfigurer

Ví dụ này dùng các thành phần bổ sung không xung đột để minh họa rõ ba lớp:

- `spring.mvc.format.date` định dạng request parameter kiểu `LocalDate`.
- `spring.mvc.static-path-pattern` chọn URL cho các file tĩnh mặc định.
- `spring.web.resources.static-locations` chọn thư mục chứa file.
- `spring.web.resources.cache.period` điều chỉnh cache mặc định của tài nguyên tĩnh.
- Java `WebMvcConfigurer` thêm interceptor cho API và thêm **một** resource mapping khác để chứng minh Java có thể bổ sung mà không phá mapping do properties tạo.

### 8.1. Cấu trúc project

~~~text
mvc-config-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcdemo/
    │   │   ├── MvcDemoApplication.java
    │   │   ├── DayController.java
    │   │   └── ExtraMvcConfiguration.java
    │   └── resources/
    │       ├── application.properties
    │       ├── site/info.txt
    │       └── manual/extra.txt
    └── test/
        └── java/com/example/mvcdemo/
            └── MvcConfigurationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-config-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là ví dụ theo Boot 3.5.x; không sử dụng cùng các import/cấu trúc starter này một cách máy móc khi nâng lên 4.x.

### 8.3. application.properties

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.mvc.format.date=dd/MM/yyyy
spring.mvc.static-path-pattern=/assets/**

spring.web.resources.static-locations=classpath:/site/
spring.web.resources.cache.period=3600s
~~~

Bốn property sau `server.port` thuộc hai namespace nhưng cùng tham gia một ứng dụng MVC. File `src/main/resources/site/info.txt` chứa:

~~~text
assets-ok
~~~

File `src/main/resources/manual/extra.txt` chứa:

~~~text
manual-ok
~~~

Nội dung text file có thể chứa newline cuối file; các test bên dưới dùng kiểm tra substring, không phụ thuộc ký tự xuống dòng đó.

### 8.4. Spring Boot entry point

File `src/main/java/com/example/mvcdemo/MvcDemoApplication.java`:

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

### 8.5. Controller: request parameter theo spring.mvc.format.date

File `src/main/java/com/example/mvcdemo/DayController.java`:

~~~java
package com.example.mvcdemo;

import java.time.LocalDate;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DayController {
    @GetMapping("/api/day")
    String day(@RequestParam("value") LocalDate value) {
        return value.toString();
    }

    @GetMapping("/api/status")
    String status() {
        return "mvc-config-ok";
    }
}
~~~

Spring MVC chuyển chuỗi query theo format `dd/MM/yyyy` đã cấu hình. `LocalDate.toString()` dùng chuẩn ISO `yyyy-MM-dd`; đây là **định dạng output do controller tự tạo**, không phải cách serialize JSON.

### 8.6. Java config: thêm interceptor và resource handler riêng

File `src/main/java/com/example/mvcdemo/ExtraMvcConfiguration.java`:

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler) {
                response.setHeader("X-App-Mvc", "on");
                return true;
            }
        }).addPathPatterns("/api/**");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manual/**")
                .addResourceLocations("classpath:/manual/")
                .setCachePeriod(300);
    }
}
~~~

Giải thích:

- `ExtraMvcConfiguration` không có `@EnableWebMvc`, nên không cố ý thay `WebMvcAutoConfiguration`.
- `addInterceptors` thêm HTTP header `X-App-Mvc: on` cho controller mappings `/api/**`. Nó không thay đổi format query parameter và không tự động chặn request trái phép.
- `addResourceHandlers` đăng ký riêng `/manual/**` → `classpath:/manual/`. Pattern khác `/assets/**` nên không giành cùng mapping của Boot.
- Cache 300 giây được đặt trực tiếp cho resource mapping thủ công. Trong khi đó `spring.web.resources.cache.period=3600s` được dùng khi Boot tạo resource mapping mặc định cho `/assets/**`. Không giả định mapping viết tay được thừa hưởng toàn bộ `spring.web.resources.*`.

### 8.7. Chạy dự án và kiểm tra thủ công

Yêu cầu Maven và JDK 17+. Tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Sau khi server khởi động trên cổng 8080, gửi:

~~~bash
curl -i "http://localhost:8080/api/status"
curl -i "http://localhost:8080/api/day?value=31/12/2026"
curl -i "http://localhost:8080/assets/info.txt"
curl -i "http://localhost:8080/manual/extra.txt"
~~~

Các HTTP body do controller tạo một cách xác định:

~~~text
/api/status          -> mvc-config-ok
/api/day?value=31/12/2026 -> 2026-12-31
~~~

Trong ví dụ trên, dòng bên phải của `->` là body kỳ vọng; đây không phải stdout nguyên văn của lệnh `curl -i`. Hai request file tĩnh trả nội dung file tương ứng: `assets-ok` và `manual-ok`, có thể kèm newline ở cuối file. Header `X-App-Mvc: on` có trên những request API đã match interceptor. Header cache và những header server khác có thể thay đổi theo phiên bản/cấu hình runtime.

Nếu gọi `/static/info.txt`, `/site/info.txt` hoặc `/info.txt`, đừng cho rằng URL đó hợp lệ chỉ vì file tồn tại trong classpath: mapping tĩnh của ví dụ đang là `/assets/**`.

### 8.8. Integration tests với MockMvc

File `src/test/java/com/example/mvcdemo/MvcConfigurationTest.java`:

~~~java
package com.example.mvcdemo;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcConfigurationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void propertiesAndJavaConfigurerCoexist() throws Exception {
        mvc.perform(get("/api/day").param("value", "31/12/2026"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-App-Mvc", "on"))
                .andExpect(content().string("2026-12-31"));
    }

    @Test
    void bootStaticResourceMappingUsesMvcAndWebProperties() throws Exception {
        mvc.perform(get("/assets/info.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("assets-ok")));
    }

    @Test
    void javaResourceHandlerIsAdditional() throws Exception {
        mvc.perform(get("/manual/extra.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("manual-ok")));
    }

    @Test
    void invalidDateIsNotAccepted() throws Exception {
        mvc.perform(get("/api/day").param("value", "not-a-date"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Nếu project có Maven Wrapper, dùng `./mvnw test` (Windows: `mvnw.cmd test`). Các test chứng minh cùng một application context kết hợp `spring.mvc.format.date`, `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, `WebMvcConfigurer.addInterceptors` và `addResourceHandlers`.

`MockMvc` không mở TCP server thật. Với `@SpringBootTest` và `@AutoConfigureMockMvc` (Boot 3.5), nó kiểm tra xử lý request MVC trong test context; để xác minh trực tiếp cổng, proxy, TLS và caching qua mạng, hãy bổ sung `RANDOM_PORT` integration test.

## 9. Khi Java config chạm đúng điểm Boot đang điều khiển

### 9.1. Thêm mapping khác pattern: thường an toàn

Ví dụ ở mục 8 chọn `/assets/**` cho Boot và `/manual/**` cho Java, nhờ vậy có thể dễ dàng dự đoán từng request đi qua handler nào.

### 9.2. Thêm mapping trùng pattern: cần kiểm tra thật

Nếu thay `/manual/**` thành `/assets/**` trong `addResourceHandlers`, bạn đang yêu cầu Java cấu hình cùng một pattern với `spring.mvc.static-path-pattern`. Boot có logic tránh đăng ký hai handler giống pattern theo thứ tự, nên custom mapping có thể chặn mặc định hoặc gây kết quả khó đoán khi bạn không hiểu registration order. **Không giả định** `spring.web.resources.static-locations` và cache từ property vẫn được áp dụng nguyên vẹn lên handler được tạo thủ công.

### 9.3. Thêm Converter: không phải thay toàn bộ MVC

Trường hợp request có `@RequestParam OrderId id`, một `Converter<String, OrderId>` có thể được đăng ký qua `addFormatters`, hoặc trong Spring Boot là bean `Converter` được auto-detect. Không cần `@EnableWebMvc` chỉ để parse một kiểu dữ liệu mới.

### 9.4. configureMessageConverters và extendMessageConverters

Khi tự kiểm soát danh sách `HttpMessageConverter` mà không hiểu cách Boot thêm defaults, bạn có thể làm JSON/XML/string response thay đổi ngoài mong đợi. Nếu chỉ cần bổ sung hay điều chỉnh một converter cụ thể, cân nhắc `extendMessageConverters`, bean converter hoặc các customizer mà phiên bản Boot đang hỗ trợ. `@ResponseBody` và `@RequestBody` dùng message conversion; chúng không tự chịu ảnh hưởng của `spring.mvc.format.date` như request parameter.

### 9.5. CORS và security

CORS có thể được cấu hình trong Java:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/public/**")
            .allowedOrigins("https://client.example")
            .allowedMethods("GET", "POST");
}
~~~

Đây là đoạn method minh họa cho `WebMvcConfigurer`, không phải phần của project hoàn chỉnh ở mục 8. Khi dùng Spring Security, phải cấu hình CORS integration phù hợp với security filter chain, vì request preflight có thể bị filter chặn trước khi đến MVC. CORS không phải authorization; một client ngoài browser vẫn có thể gọi HTTP endpoint nếu không bị cơ chế xác thực/phân quyền chặn.

## 10. Nâng từ Spring Boot 3.x lên 4.x: điều gì cần xét lại?

Các property như `spring.mvc.static-path-pattern`, `spring.mvc.format.date`, `spring.web.resources.static-locations` và `spring.web.locale-resolver` còn xuất hiện trong bảng Common Application Properties của Spring Boot 4.1. Điều đó **không có nghĩa nâng cấp chỉ việc đổi version**:

- **Starter:** ở 3.5 thường dùng `spring-boot-starter-web` cho Spring MVC. Ở 4.1, starter `spring-boot-starter-webmvc` được ưu tiên; `spring-boot-starter-web` cũ đã deprecated.
- **Module/package:** Boot 4 được modularize, các class auto-configuration và một số API liên quan Boot đã đổi package; code import trực tiếp `org.springframework.boot.autoconfigure...` có thể cần cập nhật.
- **Java/Servlet/Framework:** yêu cầu runtime và API của từng dòng khác nhau; phải kiểm tra BOM và System Requirements của version cụ thể.
- **MVC core:** `WebMvcConfigurer` thuộc Spring Framework và tiếp tục là cơ chế extension chính; nhưng vẫn phải so lại những hook/options đã thay đổi theo Spring Framework 7.
- **Properties:** kiểm tra trực tiếp appendix của Boot 4.1 khi migrate, không dựa vào metadata của dự án 3.5 hoặc tài liệu 2.x.
- **Test:** tổ chức các starter test/module có thay đổi ở Boot 4; các import test của ví dụ Boot 3.5 không mặc định được bảo đảm dùng nguyên trong mọi project 4.x.

Trong migration review nên lập bảng **property hiện có → thành phần runtime → Java config liên quan → integration test**. Đặc biệt kiểm tra static resources, đường dẫn, locale, JSON/formatting và CORS vì chúng ảnh hưởng trực tiếp đến hành vi HTTP.

## 11. Debug khi property có mà hành vi không như dự kiến

### 11.1. Xác minh nguồn và giá trị property hiệu lực

Kiểm tra `application.properties`/`application.yaml`, profile `application-prod.yaml`, biến môi trường, system properties và command-line arguments. Ví dụ `--spring.mvc.static-path-pattern=/public/**` có thể ghi đè giá trị trong file tùy nguồn cấu hình đang được áp dụng.

Nếu dùng Actuator `env` và `configprops`, chỉ bật/cho phép xem trên môi trường và quyền truy cập phù hợp; những endpoint này có thể tiết lộ cấu hình nhạy cảm nếu cấu hình security sai.

### 11.2. Xác minh Boot MVC auto-configuration còn chạy hay không

Bật debug để xem Condition Evaluation Report:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Cú pháp trên dành cho Maven plugin của project đã cấu hình; cũng có thể chạy jar với `java -jar app.jar --debug` nếu đã package. Tìm mục `WebMvcAutoConfiguration` và điều kiện matched/not matched; nếu thêm `@EnableWebMvc`, các điều kiện liên quan `WebMvcConfigurationSupport` thường là manh mối trực tiếp.

### 11.3. Kiểm tra URL trước khi kiểm tra file

Nếu `GET /assets/info.txt` trả 404:

1. Kiểm tra `spring.mvc.static-path-pattern` có thực sự bằng `/assets/**` không.
2. Kiểm tra `spring.web.resources.static-locations` có trỏ tới `classpath:/site/` không.
3. Kiểm tra file được copy vào build output/JAR ở đúng đường dẫn.
4. Kiểm tra `spring.web.resources.add-mappings` có đang false hay không.
5. Kiểm tra `@EnableWebMvc`, `addResourceHandlers` và trùng mapping.
6. Kiểm tra security filter, reverse proxy và servlet context path; 404 có thể xuất phát từ tầng khác.

**404 không chứng minh file trên đĩa không tồn tại**; phải phân biệt URL mapping, physical resource location, packaging và request routing.

### 11.4. Kiểm tra format request và JSON tách biệt

Nếu `/api/day?value=31/12/2026` bị 400, kiểm tra conversion service, định dạng ngày `spring.mvc.format.date`, annotation `@DateTimeFormat` trên controller, format thực tế được URL-encode và các converter tùy chỉnh. Nếu `@RequestBody` JSON có ngày khác kỳ vọng, kiểm tra Jackson và các `HttpMessageConverter` thay vì vội thay `spring.mvc.format.date`.

### 11.5. Kiểm tra interceptor và filter

`HandlerInterceptor` chạy trong Spring MVC handler execution; Servlet `Filter` hoạt động ở tầng trước đó. Interceptor không thay được Spring Security filters, không bao trùm tất cả servlet khác, và có thể bị giới hạn theo URL pattern. Nếu header `X-App-Mvc` không thấy ở file tĩnh trong ví dụ, đó là do interceptor chỉ áp dụng `/api/**`, không phải bằng chứng cấu hình Java hỏng.

## 12. Các hiểu nhầm và sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
|---|---|
| `spring.mvc.*` và `spring.web.*` là hai kiểu viết cùng một namespace | Hai nhóm cấu hình tác động đến các đối tượng khác nhau; cần đọc property cụ thể |
| `spring.web.resources.static-locations` quyết định URL công khai | Nó quyết định nơi tìm file; URL thuộc `spring.mvc.static-path-pattern` trong MVC |
| `spring.mvc.static-path-pattern` thay luôn URL controller | Nó chỉ xử lý pattern resource mapping; controller dùng `@RequestMapping` |
| `spring.mvc.format.date` đổi định dạng JSON của mọi DTO | Nó chủ yếu cấu hình MVC formatting/binding; JSON dùng message conversion |
| `WebMvcConfigurer` làm Boot auto-configuration tắt | `WebMvcConfigurer` không kèm `@EnableWebMvc` là đường mở rộng được khuyến nghị |
| `@EnableWebMvc` chỉ bật thêm MVC và không có tác dụng phụ | Nó nhận quyền cấu hình MVC và làm Boot WebMvcAutoConfiguration nhường chỗ |
| Java config luôn thắng application.properties | Không có quy tắc tổng quát; xem binding, bean condition, registration và order |
| `spring.web.resources.add-mappings=false` ngăn mọi Java resource handler | Nó tắt default mappings của Boot; ứng dụng vẫn có thể thêm handler riêng |
| Có `spring.web.resources.cache.period` thì JSON controller có Cache-Control | Property chủ yếu áp dụng static resource handling, không tự áp dụng mọi API |
| WebFlux có thể được mở rộng bằng WebMvcConfigurer | WebFlux sử dụng API riêng như `WebFluxConfigurer` |
| CORS config tương đương authentication/authorization | CORS là cơ chế của browser, không phải kiểm soát truy cập backend |
| Chỉ cần test status 200 là biết cấu hình đúng | Còn phải test body, headers, routing, MIME, cache, security và nguồn dữ liệu |

## 13. Quy trình chọn phương thức tùy chỉnh

1. **Xác định tầng:** điều chỉnh HTTP listener (`server.*`), MVC (`spring.mvc.*`), static resources/locale (`spring.web.*`), JSON serialization, hay nghiệp vụ?
2. **Tra property chính thức của đúng Boot version**. Ưu tiên property cho cấu hình chuẩn; chúng dễ quản lý theo môi trường hơn sửa code.
3. **Nếu thiếu property phù hợp, dùng WebMvcConfigurer** để bổ sung interceptor, formatter, mapping, CORS hay argument resolver, tránh thay cả MVC infrastructure.
4. **Khi dùng Java, lựa chọn extension hook nhỏ nhất**. Không tùy tiện tự thay `RequestMappingHandlerAdapter` hoặc bật `@EnableWebMvc`.
5. **Tránh cấu hình trùng chức năng ở nhiều nơi**; nếu buộc phải kết hợp, ghi rõ ownership và thứ tự.
6. **Viết integration test cho hành vi**, ví dụ HTTP path của resource, input format, locale fallback, header của interceptor và response content type.
7. **Khi nâng cấp Boot**, rà soát BOM/starter/package, property metadata, Condition Evaluation Report và tất cả test quan trọng.

**Kết luận:** `spring.mvc.*` xác định nhiều quy ước dành riêng cho Spring MVC, `spring.web.*` cung cấp những chính sách web chung như locale và tài nguyên tĩnh, còn Java config là cơ chế mở rộng hoặc thay thế ở những điểm cần kiểm soát lập trình. Trong dự án Spring Boot thông thường, mô hình ít rủi ro nhất là **giữ auto-configuration + dùng properties cho quy ước chuẩn + bổ sung WebMvcConfigurer cho hành vi đặc thù**, chỉ chuyển sang `@EnableWebMvc` khi thật sự chủ động gánh toàn bộ MVC configuration.

## Tài liệu chính thức

- Spring Boot 3.5 — Servlet Web Applications, MVC Auto-configuration, formatting, static content và content negotiation: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties, `spring.mvc.*` và `spring.web.*`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.1 — Common Application Properties: https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html
- Spring Boot 4.1 — Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — How-to, Spring MVC customization: https://docs.spring.io/spring-boot/how-to/spring-mvc.html
- Spring Boot — Reactive Web Applications, static content: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework — Enable MVC Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html
- Spring Framework — Static Resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Framework — Content Types/Negotiation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html
- Spring Framework — WebMvcConfigurer API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
