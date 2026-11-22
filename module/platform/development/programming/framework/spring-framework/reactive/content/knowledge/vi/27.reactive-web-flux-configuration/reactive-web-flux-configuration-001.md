# @EnableWebFlux, WebFluxConfigurer và cấu hình hạ tầng

## 1. Mục tiêu của cấu hình WebFlux

Spring WebFlux là web framework reactive của Spring. Nó hỗ trợ hai cách xây dựng endpoint:

- **Annotated controllers:** dùng `@RestController`, `@Controller`, `@RequestMapping`, `@GetMapping`, `@PostMapping` và các annotation liên quan.
- **Functional endpoints:** dùng `RouterFunction`, `RequestPredicate`, `HandlerFunction` và `ServerResponse` để tách routing khỏi handler.

Khi một request đi vào ứng dụng, WebFlux phải tìm handler phù hợp, chuyển request thành tham số Java, gọi handler, rồi encode kết quả thành HTTP response. Cấu hình WebFlux quyết định những thành phần hạ tầng nào tham gia quy trình đó và cách chúng hoạt động.

Có ba khái niệm cần phân biệt:

1. `@EnableWebFlux` kích hoạt Java configuration của Spring WebFlux trong ứng dụng tự cấu hình.
2. `WebFluxConfigurer` cung cấp các callback để tùy chỉnh những phần cụ thể của cấu hình WebFlux.
3. Spring Boot WebFlux auto-configuration tự đăng ký cấu hình mặc định và tích hợp thêm codec, static resources, server và các tính năng của Boot.

Trong ứng dụng Spring Boot thông thường, lựa chọn quan trọng là dùng `WebFluxConfigurer` mà không thêm `@EnableWebFlux` để giữ các tùy chỉnh do Boot cung cấp. Chỉ dùng `@EnableWebFlux` khi muốn chịu trách nhiệm đầy đủ về cấu hình WebFlux.

## 2. @EnableWebFlux và WebFluxConfigurer khác nhau thế nào?

### 2.1. @EnableWebFlux

Trong ứng dụng Spring Framework không dùng Spring Boot, có thể kích hoạt WebFlux bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class WebConfig {
}
~~~

`@EnableWebFlux` import `DelegatingWebFluxConfiguration`. Cấu hình này đăng ký hạ tầng mặc định cho WebFlux và tìm các bean triển khai `WebFluxConfigurer` để áp dụng callback tùy chỉnh.

Hạ tầng được cấu hình hỗ trợ annotated controllers và functional endpoints, đồng thời đăng ký các thành phần cần thiết dựa trên dependency có trong classpath, chẳng hạn codec JSON hoặc XML.

### 2.2. WebFluxConfigurer

`WebFluxConfigurer` là interface callback. Các phương thức đều có triển khai mặc định, vì vậy chỉ cần override phần cần tùy chỉnh:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebConfig implements WebFluxConfigurer {

    // Override only the configuration hooks that are needed.
}
~~~

`WebFluxConfigurer` không tự tạo toàn bộ hạ tầng nếu ứng dụng chưa bật WebFlux configuration. Với Spring Boot, auto-configuration đã đảm nhận phần đó.

### 2.3. Quy tắc quan trọng khi dùng Spring Boot

Trong Spring Boot, hãy viết:

~~~java
@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Không thêm `@EnableWebFlux` vào cấu hình trên nếu muốn giữ các tính năng WebFlux auto-configured của Boot. Boot cung cấp cấu hình cho codec, static resources và các thành phần hạ tầng khác. Khi `@EnableWebFlux` được bật, cấu hình WebFlux của Boot sẽ nhường quyền cho cấu hình do ứng dụng kiểm soát.

Bảng quyết định:

| Môi trường | Cách cấu hình thường dùng |
| --- | --- |
| Spring Framework thuần, tự dựng application context | `@EnableWebFlux` và tùy chọn `WebFluxConfigurer` |
| Spring Boot WebFlux, chỉ cần thêm vài tùy chỉnh | `WebFluxConfigurer`, không thêm `@EnableWebFlux` |
| Spring Boot WebFlux, muốn kiểm soát toàn bộ hạ tầng | `@EnableWebFlux` và tự chịu trách nhiệm các phần cấu hình |
| Cần thay bean hạ tầng sâu mà callback không đáp ứng | Chế độ nâng cao với `DelegatingWebFluxConfiguration` |

### 2.4. Khi nào dùng DelegatingWebFluxConfiguration?

Spring Framework cho phép mở rộng trực tiếp `DelegatingWebFluxConfiguration` khi cần override bean declarations của cấu hình nền:

~~~java
@Configuration
public class AdvancedWebConfig
        extends DelegatingWebFluxConfiguration {

    // Override selected infrastructure bean declarations here.
}
~~~

Đây là lựa chọn nâng cao. Nó đòi hỏi hiểu rõ vòng đời và quan hệ giữa các bean hạ tầng của WebFlux. Trong ứng dụng Boot thông thường, ưu tiên callback của `WebFluxConfigurer` và các extension point riêng của Boot trước khi thay cấu hình nền.

## 3. Vòng đời xử lý request và các bean hạ tầng

### 3.1. Request đi qua WebFlux như thế nào?

`HttpHandler` là abstraction xử lý HTTP request/response ở tầng server. Adapter của server nhúng chuyển request từ Reactor Netty, Tomcat hoặc Jetty vào mô hình HTTP của Spring.

`DispatcherHandler` là front controller của WebFlux. Nó phối hợp các thành phần sau:

- `HandlerMapping` tìm handler phù hợp với request.
- `HandlerAdapter` gọi handler theo loại handler tương ứng.
- `HandlerResultHandler` xử lý giá trị trả về và ghi response.
- `WebExceptionHandler` xử lý exception phát sinh trong quá trình xử lý request.
- `HttpMessageReader` đọc và decode request body.
- `HttpMessageWriter` encode và ghi response body.

~~~text
Client
  |
  v
Reactive Web Server
(Reactor Netty / Tomcat / Jetty)
  |
  v
HttpHandler
  |
  v
WebFilter chain
  |
  v
DispatcherHandler
  |
  +--> HandlerMapping
  |       |
  |       v
  |    Handler
  |
  +--> HandlerAdapter
  |       |
  |       v
  |    Mono / Flux / result
  |
  +--> HandlerResultHandler
  |       |
  |       v
  |    HttpMessageWriter / View
  |
  +--> WebExceptionHandler (error path)
  |
  v
HTTP Response
~~~

### 3.2. HandlerMapping

`HandlerMapping` ánh xạ request tới handler. WebFlux có thể dùng nhiều kiểu mapping, ví dụ:

- `RequestMappingHandlerMapping` tìm các method trong `@Controller` hoặc `@RestController`.
- `RouterFunctionMapping` tìm route được khai báo bằng `RouterFunction`.
- Resource handler mapping phục vụ static resources.
- Các mapping khác có thể được thêm cho WebSocket hoặc tích hợp chuyên biệt.

Thứ tự giữa các HandlerMapping có ý nghĩa khi nhiều mapping có thể xử lý cùng một URL. Không nên tạo route chồng lấn nếu không có quy tắc ưu tiên rõ ràng.

### 3.3. HandlerAdapter và HandlerResultHandler

`HandlerAdapter` biết cách gọi một loại handler cụ thể. Ví dụ, adapter cho annotated controller hiểu cách bind path variable, request parameter, header, body và validation.

`HandlerResultHandler` biết cách ghi kết quả. Kết quả có thể là:

- `ResponseEntity<T>` hoặc `Mono<ResponseEntity<T>>`.
- `@ResponseBody` hoặc object được serialize.
- `Flux<T>` cho response streaming.
- `Rendering` hoặc view name cho HTML.
- `ServerResponse` của functional endpoints.

### 3.4. Codec và ReactiveAdapterRegistry

`ReactiveAdapterRegistry` cho phép WebFlux làm việc với nhiều abstraction reactive khác nhau. Codec chuyển đổi giữa byte stream và Java object.

`ServerCodecConfigurer` quản lý các reader/writer mặc định và custom codec. Codec phù hợp được lựa chọn dựa trên kiểu dữ liệu, media type và dependency trên classpath.

### 3.5. WebFilter và WebExceptionHandler

`WebFilter` can thiệp vào HTTP exchange trước/sau handler. Nó phù hợp với concern xuyên suốt như security, correlation ID, request logging và kiểm tra header.

`WebExceptionHandler` xử lý lỗi ở tầng WebFlux. Trong Spring Boot, error handling auto-configured thường đã cung cấp response lỗi phù hợp. Có thể mở rộng qua cơ chế Error Attributes, Problem Details hoặc handler tùy chỉnh khi cần.

Lưu ý: `WebFluxConfigurer` tùy chỉnh cấu hình hạ tầng; `WebFilter` tham gia vào từng request/response exchange. Hai cơ chế có vai trò khác nhau.

## 4. Các callback quan trọng của WebFluxConfigurer

Các phương thức callback phổ biến trong Spring Framework 6.2:

| Callback | Mục đích |
| --- | --- |
| `configureHttpMessageCodecs` | Thêm hoặc tùy chỉnh reader/writer cho request và response body |
| `addFormatters` | Đăng ký Converter và Formatter cho binding |
| `getValidator` | Cung cấp Validator toàn cục |
| `getMessageCodesResolver` | Tùy chỉnh message code cho data binding |
| `addCorsMappings` | Cấu hình CORS toàn cục |
| `configureContentTypeResolver` | Tùy chỉnh cách xác định media type từ request |
| `configurePathMatching` | Tùy chỉnh quy tắc khớp đường dẫn |
| `configureArgumentResolvers` | Thêm resolver cho tham số controller tùy chỉnh |
| `configureViewResolvers` | Cấu hình view resolver |
| `addResourceHandlers` | Đăng ký static resource handler |
| `configureBlockingExecution` | Cấu hình executor cho controller method được nhận diện là blocking |
| `getWebSocketService` | Tùy chỉnh WebSocket handshake service |
| `addErrorResponseInterceptors` | Thêm interceptor cho RFC 9457 Problem Details |

Các callback này có default implementation. Chỉ override những gì ứng dụng thật sự cần.

`configureApiVersioning` thuộc Spring Framework 7.0; không đưa phương thức đó vào code mẫu Spring Boot 3.5.x sử dụng Spring Framework 6.2.

## 5. Cấu hình HTTP message codecs

### 5.1. Codec làm nhiệm vụ gì?

WebFlux sử dụng:

- `HttpMessageReader` để đọc request body và decode thành Java object.
- `HttpMessageWriter` để encode Java object và ghi response body.

Ví dụ, request có `Content-Type: application/json` và body là JSON. Jackson decoder có thể chuyển JSON thành record hoặc DTO. Khi trả object với `produces = application/json`, Jackson encoder chuyển object thành JSON response.

### 5.2. Giới hạn dung lượng bộ nhớ khi decode

Một số codec cần aggregate dữ liệu vào bộ nhớ trước khi tạo object. Có thể giới hạn kích thước bằng `ServerCodecConfigurer`:

~~~java
@Configuration(proxyBeanMethods = false)
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Ví dụ đặt giới hạn 2 MiB cho các codec mặc định có hành vi aggregate.

Giới hạn này giúp ngăn một số request body lớn làm bộ nhớ tăng ngoài dự kiến. Nó không phải giới hạn kích thước tổng quát cho mọi upload streaming hoặc mọi dữ liệu đi qua server. File lớn nên được xử lý theo stream/chunk và có chính sách giới hạn riêng ở tầng nghiệp vụ/server/gateway.

### 5.3. Thêm hoặc thay thế codec

`ServerCodecConfigurer` cho phép:

- Đăng ký custom reader/writer.
- Tùy chỉnh default codec.
- Thay thế bộ codec mặc định.
- Đăng ký codec chỉ dành cho một media type hoặc kiểu dữ liệu.

Ví dụ minh họa thêm codec:

~~~java
@Override
public void configureHttpMessageCodecs(
    ServerCodecConfigurer configurer
) {
    configurer.customCodecs().register(new MyCustomHttpMessageReader());
    configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
}
~~~

`MyCustomHttpMessageReader` là implementation do ứng dụng cung cấp; đoạn này là ví dụ extension point, không phải class có sẵn trong Spring.

Không gọi `registerDefaults(false)` nếu mục tiêu chỉ là thêm một codec. Lệnh đó tắt các codec mặc định và khiến ứng dụng phải tự đăng ký lại những reader/writer cần thiết.

### 5.4. CodecCustomizer trong Spring Boot

Spring Boot có `CodecCustomizer` để tùy chỉnh codec được auto-configured:

~~~java
@Bean
CodecCustomizer applicationCodecCustomizer() {
    return configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
}
~~~

Chọn một cách cấu hình phù hợp với cấu trúc ứng dụng. `WebFluxConfigurer.configureHttpMessageCodecs` là extension point của Spring Framework; `CodecCustomizer` là extension point của Boot.

## 6. Conversion, Formatter và validation

### 6.1. Conversion và formatting

WebFlux cần chuyển String từ path variable, query parameter hoặc form field thành kiểu Java. `Converter` chuyển đổi một kiểu sang kiểu khác; `Formatter` hỗ trợ parse/print theo định dạng và locale.

Ví dụ đặt format ngày giờ theo ISO:

~~~java
@Configuration
public class FormattingConfiguration implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();

        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

Spring WebFlux cũng hỗ trợ annotation như `@DateTimeFormat`, `@NumberFormat` và `@DurationFormat` trên field hoặc tham số phù hợp.

### 6.2. Validator toàn cục và validator cục bộ

Nếu Bean Validation có trên classpath, WebFlux có thể đăng ký validator mặc định cho `@Valid` và `@Validated` trên tham số controller.

Có thể cung cấp validator toàn cục bằng `getValidator()`:

~~~java
@Override
public Validator getValidator() {
    return customValidator;
}
~~~

`customValidator` là bean được ứng dụng quản lý. Nếu chỉ một controller hoặc một request cần quy tắc riêng, dùng `@InitBinder` để đăng ký validator cục bộ thường rõ ràng hơn.

Không override validator mặc định chỉ để thay một rule đơn lẻ nếu có thể xử lý ở DTO hoặc controller.

### 6.3. MessageCodesResolver

`MessageCodesResolver` quyết định các mã thông báo lỗi được tạo cho data binding/validation. Tùy chỉnh nó khi ứng dụng cần quy ước mã lỗi riêng để ánh xạ sang message đa ngôn ngữ hoặc API error contract.

## 7. Cấu hình CORS

### 7.1. CORS là gì?

CORS (Cross-Origin Resource Sharing) là cơ chế trình duyệt dùng để kiểm soát JavaScript truy cập tài nguyên ở origin khác. Origin gồm scheme, host và port.

WebFlux hỗ trợ CORS ở tầng `HandlerMapping`. Khi request được ánh xạ tới handler, HandlerMapping kiểm tra cấu hình CORS. Preflight request có thể được xử lý trực tiếp trước khi controller chạy.

### 7.2. CORS toàn cục bằng CorsRegistry

~~~java
@Configuration
public class CorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Ý nghĩa:

- `addMapping` xác định URL pattern được áp dụng.
- `allowedOrigins` giới hạn origin được phép gọi.
- `allowedMethods` liệt kê HTTP method được phép.
- `allowedHeaders` cho phép các request header.
- `exposedHeaders` cho phép JavaScript đọc các response header được nêu.
- `allowCredentials` cho phép request có credentials khi chính sách bảo mật cho phép.
- `maxAge` là thời gian trình duyệt có thể cache kết quả preflight.

Khi bật credentials, không dùng `allowedOrigins("*")`. Cấu hình origin cụ thể hoặc `allowedOriginPatterns` phù hợp với yêu cầu bảo mật.

### 7.3. CORS tại controller

Có thể dùng `@CrossOrigin` trên controller hoặc method:

~~~java
@CrossOrigin(origins = "https://frontend.example.com")
@RestController
@RequestMapping("/reports")
public class ReportController {
}
~~~

Cấu hình toàn cục và cục bộ có thể kết hợp. Nếu cần policy thống nhất cho toàn API, dùng global mapping; nếu chỉ một endpoint có ngoại lệ rõ ràng, dùng annotation tại handler.

### 7.4. CorsWebFilter và Spring Security

`CorsWebFilter` là lựa chọn khác, đặc biệt phù hợp với functional endpoints. Nếu ứng dụng dùng Spring Security, nên tích hợp CORS theo cơ chế Spring Security hỗ trợ để tránh cấu hình hai nơi gây header trùng hoặc thứ tự filter sai.

Không bật đồng thời nhiều cơ chế CORS trên cùng route nếu không có chủ đích.

## 8. Static resources và cache

### 8.1. Vị trí static resource mặc định

Spring Boot WebFlux thường phục vụ static resource từ các vị trí classpath như:

- `/static`
- `/public`
- `/resources`
- `/META-INF/resources`

Ví dụ file `src/main/resources/static/index.html` có thể được phục vụ như static content theo cấu hình mặc định.

### 8.2. Thay đổi URL mapping và resource location

Dùng `addResourceHandlers` khi cần route static resource riêng:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .setCacheControl(CacheControl.maxAge(7, TimeUnit.DAYS));
}
~~~

Request `/assets/logo.svg` sẽ tìm file tương ứng trong thư mục classpath đã khai báo.

### 8.3. Cache và versioning

Resource handler hỗ trợ:

- Cache-Control và Last-Modified.
- `ResourceResolver` để tìm resource.
- `ResourceTransformer` để biến đổi resource.
- `VersionResourceResolver` để tạo URL có version hoặc content hash.

Khi dùng versioned assets, browser có thể cache lâu vì URL thay đổi khi nội dung thay đổi. Cần chọn chính sách cache phù hợp với quy trình build/deploy frontend.

### 8.4. Cấu hình qua Spring Boot properties

Có thể thay đổi static path pattern bằng:

~~~properties
spring.webflux.static-path-pattern=/resources/**
~~~

Và thay resource locations bằng:

~~~properties
spring.web.resources.static-locations=classpath:/public/,classpath:/assets/
~~~

Khi thay danh sách locations, giá trị mới thay thế danh sách mặc định. Nếu không còn thư mục chứa welcome page, trang index mặc định có thể không được phát hiện như trước.

## 9. Content negotiation và ViewResolver

### 9.1. Content negotiation

WebFlux quyết định media type response dựa trên requested content type resolver. Mặc định, header `Accept` là nguồn chính.

Có thể tùy chỉnh bằng `configureContentTypeResolver` nếu ứng dụng có quy tắc media type đặc biệt, chẳng hạn query parameter hoặc chiến lược nội bộ. Tránh thêm nhiều cơ chế chọn định dạng nếu không có yêu cầu tương thích rõ ràng.

### 9.2. ViewResolver

Nếu WebFlux render HTML template thay vì chỉ trả JSON, `ViewResolverRegistry` dùng để đăng ký view technology như FreeMarker hoặc custom ViewResolver.

Ví dụ:

~~~java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    registry.freeMarker();
}
~~~

Để chạy được, project cần dependency và cấu hình FreeMarker tương ứng. Ví dụ trên chỉ đăng ký view resolver, không tự tạo template engine hoặc template file.

Có thể đăng ký default view dựa trên `HttpMessageWriterView` để render định dạng khác như JSON/XML qua codec. Với REST API thuần JSON, thường không cần cấu hình view resolver.

## 10. Path matching và custom argument resolver

### 10.1. PathMatchConfigurer

`configurePathMatching` tùy chỉnh cách URL được ánh xạ tới annotated controller. Ví dụ thêm prefix `/api` cho các controller có annotation `@RestController`:

~~~java
@Override
public void configurePathMatching(PathMatchConfigurer configurer) {
    configurer.addPathPrefix(
        "/api",
        HandlerTypePredicate.forAnnotation(RestController.class)
    );
}
~~~

Nếu controller có `@RequestMapping("/orders")`, route thực tế sẽ có prefix `/api/orders`.

Prefix này được áp dụng dựa trên predicate. Hãy chọn predicate đủ hẹp nếu ứng dụng có controller dành cho health, admin hoặc internal route cần path khác.

WebFlux sử dụng `RequestPath` đã parse để xử lý path segment và matrix variable. Cách xử lý path của WebFlux không hoàn toàn giống Spring MVC; không sao chép máy móc các thiết lập path matching từ MVC.

### 10.2. Custom argument resolver

`configureArgumentResolvers` cho phép thêm resolver cho kiểu tham số controller riêng:

~~~java
@Override
public void configureArgumentResolvers(
    ArgumentResolverConfigurer configurer
) {
    configurer.addCustomResolver(new CurrentTenantArgumentResolver());
}
~~~

`CurrentTenantArgumentResolver` là class do ứng dụng tự triển khai từ `HandlerMethodArgumentResolver`. Resolver có thể đọc header, security context hoặc request exchange để tạo một object domain cho tham số controller.

Chỉ thêm custom resolver khi một kiểu tham số thực sự được dùng rộng rãi. Với một vài endpoint, đọc header hoặc dùng argument annotation có sẵn thường đơn giản hơn.

## 11. Blocking execution, WebSocket và error response

### 11.1. BlockingExecutionConfigurer

Spring Framework 6.1+ cho phép cấu hình executor cho controller method được nhận diện là blocking thông qua `configureBlockingExecution`.

Cơ chế này giúp tách một số method blocking khỏi luồng xử lý reactive chính. Nó không biến code blocking thành non-blocking và không phải lý do để gọi `block()` trong pipeline. Với I/O blocking, ưu tiên API reactive hoặc cô lập phần blocking trên scheduler/executor phù hợp.

### 11.2. WebSocketService

`getWebSocketService` cho phép cung cấp WebSocket service tùy chỉnh. Một trường hợp dùng là cấu hình server-specific request upgrade strategy hoặc idle timeout cho WebSocket handshake.

Nếu ứng dụng chỉ dùng HTTP REST và SSE, thường không cần override phương thức này.

### 11.3. ErrorResponse interceptor

Spring Framework 6.2 bổ sung callback `addErrorResponseInterceptors` để thêm interceptor khi render error response theo RFC 9457 Problem Details.

Có thể dùng để thêm metadata chung như error code, trace ID hoặc thông tin mở rộng đã được chuẩn hóa. Không đưa stack trace, secret hoặc dữ liệu nội bộ nhạy cảm vào response cho client.

### 11.4. Boot error handling

Spring Boot WebFlux có `WebExceptionHandler` auto-configured. Có thể mở rộng error response bằng cơ chế Error Attributes, Problem Details hoặc `ErrorWebExceptionHandler` khi cần kiểm soát sâu hơn.

Trước khi tự viết handler mức thấp, kiểm tra xem `@ExceptionHandler`, `@ControllerAdvice` hoặc Problem Details đã đáp ứng use case chưa.

## 12. Các extension point riêng của Spring Boot

### 12.1. WebFluxAutoConfiguration

Spring Boot cung cấp `WebFluxAutoConfiguration` khi ứng dụng chạy ở reactive web application type và có WebFlux trên classpath.

Auto-configuration thường bổ sung:

- Codec defaults cho `HttpMessageReader` và `HttpMessageWriter`.
- Static resources và WebJars.
- Error handling.
- Cấu hình embedded reactive server.
- Các integration khác của Boot.

Boot dùng điều kiện bean để tránh tạo cấu hình WebFlux nền khi ứng dụng đã cung cấp cấu hình thay thế. Đây là lý do thêm `@EnableWebFlux` có thể khiến các tính năng auto-configured của Boot không còn được áp dụng theo cách mặc định.

### 12.2. CodecCustomizer

Dùng `CodecCustomizer` nếu muốn cấu hình codec theo cơ chế Boot:

~~~java
@Bean
CodecCustomizer codecCustomizer() {
    return configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
}
~~~

### 12.3. WebHttpHandlerBuilderCustomizer

Nếu cần chỉnh `HttpHandler` đã được Boot auto-configured, có thể khai báo bean `WebHttpHandlerBuilderCustomizer`. Đây là extension point thấp hơn WebFluxConfigurer, dùng cho những thành phần xử lý HTTP exchange mà callback WebFluxConfigurer không bao phủ.

Không dùng customizer thấp tầng để thay một tùy chỉnh đơn giản đã có callback tương ứng.

### 12.4. Reactive web server

Spring Boot hỗ trợ embedded reactive server như Reactor Netty, Tomcat và Jetty. Các thuộc tính phổ biến có thể cấu hình trong `application.properties`:

~~~properties
server.port=8080
server.address=0.0.0.0
~~~

Cấu hình riêng cho server như SSL, compression hoặc Netty-specific settings thuộc namespace server tương ứng. Nếu cần tùy chỉnh bằng code, dùng `WebServerFactoryCustomizer` với `ConfigurableReactiveWebServerFactory` hoặc factory chuyên biệt.

### 12.5. Tránh nhầm WebFlux với WebClient

`spring-boot-starter-webflux` có thể được thêm vào ứng dụng Spring MVC chỉ để dùng `WebClient`. Nếu cùng có `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot mặc định chọn Spring MVC làm server application type.

Muốn chạy server reactive, cần bảo đảm application type là REACTIVE và dependency/server phù hợp. Việc có WebClient trong classpath không có nghĩa ứng dụng đang chạy WebFlux server.

## 13. WebFluxConfigurer, WebFilter và Spring Security

| Cơ chế | Phạm vi | Ví dụ |
| --- | --- | --- |
| `WebFluxConfigurer` | Tùy chỉnh hạ tầng và chính sách mapping/codec | CORS, codec, resource handler, path prefix |
| `WebFilter` | Bao quanh từng HTTP exchange | Correlation ID, security, logging, request timing |
| `@ControllerAdvice` | Xử lý lỗi và binding ở controller layer | Ánh xạ exception thành API response |
| `WebExceptionHandler` | Error handling ở tầng WebFlux | Xử lý lỗi tổng quát ngoài controller |

`WebFilter` có thể được khai báo thành bean và tự động tham gia filter chain. Khi thứ tự filter quan trọng, dùng `Ordered` hoặc `@Order`.

Nếu dùng Spring Security, filter chain của Security cũng nằm trong quá trình xử lý request. Cấu hình CORS, authentication và authorization phải thống nhất giữa WebFlux và Security để tránh xử lý hai lần hoặc bỏ sót preflight request.

## 14. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Ví dụ tạo một API greeting để minh họa:

- `WebFluxConfigurer` tùy chỉnh codec và giới hạn in-memory.
- CORS cho một frontend origin cụ thể.
- Path prefix `/api` cho controller.
- Static resource mapping.
- `WebTestClient` kiểm thử route prefix và CORS preflight.

Ví dụ dùng Spring Boot 3.5.7 và Java 17. Cấu hình chính không gắn `@EnableWebFlux` để giữ Boot auto-configuration.

### 14.1. Cấu trúc project

~~~text
webflux-config-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── static/assets/
│       └── app.css
├── src/main/java/example/config/
│   ├── WebFluxConfigApplication.java
│   ├── ApiWebConfiguration.java
│   ├── GreetingController.java
│   └── GreetingRequest.java
└── src/test/java/example/config/
    └── GreetingControllerTest.java
~~~

### 14.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 14.3. application.properties

~~~properties
server.port=8080
spring.http.codecs.max-in-memory-size=2MB
~~~

### 14.4. WebFluxConfigApplication.java

~~~java
package example.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxConfigApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxConfigApplication.class, args);
    }
}
~~~

### 14.5. ApiWebConfiguration.java

~~~java
package example.config;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.method.HandlerTypePredicate;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.PathMatchConfigurer;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiWebConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }

    @Override
    public void configurePathMatching(PathMatchConfigurer configurer) {
        configurer.addPathPrefix(
            "/api",
            HandlerTypePredicate.forAnnotation(RestController.class)
        );
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(CacheControl.maxAge(7, TimeUnit.DAYS));
    }
}
~~~

Giải thích:

- Codec mặc định có giới hạn aggregate in-memory 2 MiB.
- CORS chỉ cho phép origin frontend đã khai báo, với GET và POST.
- Tất cả controller có `@RestController` được thêm prefix `/api`.
- Static assets trong `classpath:/static/assets/` được phục vụ dưới `/assets/**` và có Cache-Control 7 ngày.

Nếu không muốn prefix áp dụng cho mọi RestController, hãy thay predicate bằng predicate cụ thể hơn, chẳng hạn package hoặc annotation riêng.

### 14.6. GreetingRequest.java

~~~java
package example.config;

import jakarta.validation.constraints.NotBlank;

public record GreetingRequest(
    @NotBlank String name
) {
}
~~~

### 14.7. GreetingController.java

~~~java
package example.config;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/greetings")
public class GreetingController {

    public record Greeting(
        String message,
        String requestId
    ) {
    }

    @GetMapping("/{name}")
    public Mono<Greeting> getGreeting(
        @PathVariable String name,
        @RequestHeader(
            value = "X-Request-Id",
            required = false
        ) String requestId
    ) {
        return Mono.just(new Greeting(
            "Xin chào, " + name,
            requestId
        ));
    }

    @PostMapping
    @org.springframework.web.bind.annotation.ResponseStatus(
        HttpStatus.CREATED
    )
    public Mono<Greeting> createGreeting(
        @Valid @RequestBody GreetingRequest request,
        @RequestHeader(
            value = "X-Request-Id",
            required = false
        ) String requestId
    ) {
        return Mono.just(new Greeting(
            "Xin chào, " + request.name(),
            requestId
        ));
    }
}
~~~

Vì cấu hình thêm prefix `/api`, URL thực tế là:

- `GET /api/greetings/{name}`
- `POST /api/greetings`

### 14.8. app.css

~~~css
body {
    font-family: sans-serif;
    margin: 2rem;
}
~~~

File này có thể được truy cập tại `/assets/app.css`.

### 14.9. GreetingControllerTest.java

~~~java
package example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class GreetingControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void routePrefixAndCorsHeadersAreApplied() {
        client.get()
            .uri("/api/greetings/Linh")
            .header("Origin", "https://frontend.example.com")
            .header("X-Request-Id", "req-42")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://frontend.example.com"
            )
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào, Linh")
            .jsonPath("$.requestId").isEqualTo("req-42");
    }

    @Test
    void corsPreflightIsAccepted() {
        client.options()
            .uri("/api/greetings/Linh")
            .header("Origin", "https://frontend.example.com")
            .header("Access-Control-Request-Method", "GET")
            .header("Access-Control-Request-Headers", "X-Request-Id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://frontend.example.com"
            )
            .expectHeader()
            .exists("Access-Control-Allow-Methods");
    }
}
~~~

Test thứ nhất xác minh route prefix, JSON response và CORS response header. Test thứ hai gửi preflight OPTIONS request để kiểm tra policy CORS trước khi browser gửi request thực tế.

### 14.10. Chạy ứng dụng và test

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Gọi API:

~~~bash
curl -i http://localhost:8080/api/greetings/Linh
~~~

Response body dự kiến:

~~~json
{
  "message": "Xin chào, Linh",
  "requestId": null
}
~~~

Gọi với request ID:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/api/greetings/Linh
~~~

Response body dự kiến:

~~~json
{
  "message": "Xin chào, Linh",
  "requestId": "req-42"
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Hai test xác minh cấu hình route và CORS ở mức HTTP integration. Test không chỉ kiểm tra controller method được gọi mà còn đi qua WebFlux infrastructure của ứng dụng.

## 15. Kiểm thử cấu hình WebFlux

### 15.1. @WebFluxTest

`@WebFluxTest` phù hợp để kiểm tra slice WebFlux, ví dụ controller, controller advice, converter, formatter và `WebFluxConfigurer`.

Ví dụ:

~~~java
@WebFluxTest(GreetingController.class)
@Import(ApiWebConfiguration.class)
class GreetingSliceTest {
    @Autowired
    WebTestClient client;
}
~~~

Slice test khởi tạo một phần hạ tầng WebFlux và giới hạn các bean được scan. Nếu controller phụ thuộc service, dùng mock bean hoặc import thành phần cần thiết.

### 15.2. @SpringBootTest và WebTestClient

`@SpringBootTest(webEnvironment = RANDOM_PORT)` kiểm tra ứng dụng trong một server nhúng thật. Nó phù hợp để xác minh:

- Route prefix và path matching.
- CORS preflight và actual request.
- Codec serialization/deserialization.
- Static resource mapping.
- Security filter chain và WebFilter order.
- Error handling tích hợp.

### 15.3. Kiểm thử từng cấu hình có ý nghĩa

Không chỉ test status 200. Với cấu hình hạ tầng, hãy kiểm tra hành vi mà cấu hình cần bảo đảm:

- Codec: payload đúng media type, vượt giới hạn aggregate có response lỗi phù hợp.
- CORS: origin được phép và origin không được phép.
- Path matching: URL có prefix hoạt động và URL cũ không bị map nhầm.
- Static resource: URL đúng trả file và Cache-Control đúng.
- Validation: input không hợp lệ trả lỗi API theo contract.
- Error handler: exception được ánh xạ thành status và Problem Details mong muốn.

## 16. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — Thêm @EnableWebFlux vào ứng dụng Boot chỉ để thêm CORS.** Boot auto-configuration có thể nhường quyền và các cấu hình mặc định khác bị mất. Implement WebFluxConfigurer mà không thêm annotation.

**Lỗi 2 — Nghĩ WebFluxConfigurer tự kích hoạt WebFlux.** Interface này chỉ cung cấp callback. Ứng dụng thuần cần @EnableWebFlux; Boot WebFlux đã có auto-configuration.

**Lỗi 3 — Nhầm WebFluxConfigurer với WebMvcConfigurer.** Import nhầm package servlet khiến callback không được gọi bởi WebFlux. Kiểm tra package org.springframework.web.reactive.config.

**Lỗi 4 — Cùng thêm spring-boot-starter-web và spring-boot-starter-webflux rồi nghĩ server chạy reactive.** Boot mặc định chọn MVC. Xác định rõ application type và server stack.

**Lỗi 5 — Thay toàn bộ codec mặc định khi chỉ muốn thêm một codec.** Có thể làm mất JSON, String, form hoặc resource reader/writer. Chỉ tắt registerDefaults(false) khi chủ động tự đăng ký toàn bộ codec cần dùng.

**Lỗi 6 — Đặt maxInMemorySize quá cao.** Nhiều request đồng thời có thể tạo áp lực bộ nhớ. Chọn giới hạn theo payload thật và streaming file lớn.

**Lỗi 7 — Cho rằng maxInMemorySize là giới hạn upload tổng thể.** Nó áp dụng cho các thao tác codec cần aggregate; upload streaming và giới hạn request tổng thể cần chính sách riêng.

**Lỗi 8 — CORS dùng wildcard cùng credentials.** Browser không chấp nhận cấu hình allow-origin wildcard khi allow-credentials bật. Khai báo origin cụ thể hoặc origin pattern phù hợp.

**Lỗi 9 — Cấu hình CORS ở nhiều tầng.** CorsWebFilter, HandlerMapping và Spring Security có thể tạo policy/header chồng lấn. Chọn một cơ chế chính và tích hợp Security đúng thứ tự.

**Lỗi 10 — Chỉ test actual GET mà không test preflight.** Browser có thể gửi OPTIONS trước request thật. Viết test OPTIONS với Origin, Access-Control-Request-Method và Access-Control-Request-Headers.

**Lỗi 11 — Static resource không tìm thấy sau khi đổi static-locations.** Danh sách mới thay thế mặc định. Kiểm tra đường dẫn classpath và mapping URL.

**Lỗi 12 — Path prefix áp dụng quá rộng.** Tất cả controller khớp predicate có thể bị thêm prefix. Dùng annotation/package predicate đủ hẹp.

**Lỗi 13 — Custom argument resolver thay thế resolver mặc định.** Chỉ thêm resolver tùy chỉnh qua ArgumentResolverConfigurer, không tự dựng lại toàn bộ danh sách resolver nếu không có nhu cầu.

**Lỗi 14 — Dùng configureBlockingExecution để hợp thức hóa code blocking.** Executor riêng chỉ tách một số controller method được nhận diện blocking. Ưu tiên API non-blocking và không block event loop.

**Lỗi 15 — Cấu hình ViewResolver nhưng thiếu template engine.** Đăng ký resolver không tự thêm dependency hoặc template loader. Kiểm tra dependency và vị trí template.

**Lỗi 16 — Tự tạo WebFluxConfigurationSupport khi Boot đã auto-configure.** Có thể tạo cấu hình trùng hoặc làm auto-configuration back off. Chỉ dùng advanced mode khi hiểu rõ bean graph.

**Lỗi 17 — Dùng WebFluxConfigurer để cấu hình port/TLS/Netty.** Các phần đó thuộc server properties hoặc WebServerFactoryCustomizer.

**Lỗi 18 — Dùng WebFluxConfigurer để viết logging cho từng request.** Dùng WebFilter cho HTTP exchange; giữ WebFluxConfigurer cho cấu hình hạ tầng.

**Lỗi 19 — Cấu hình path prefix nhưng test URL cũ.** Route thực tế đã đổi. Kiểm tra HandlerTypePredicate và URL được tạo sau khi prefix áp dụng.

**Lỗi 20 — Chỉ kiểm tra controller unit test rồi kết luận CORS/codec đã đúng.** Hãy dùng WebTestClient với hạ tầng thật hoặc WebFlux test slice phù hợp.

## 17. Checklist trước khi đưa cấu hình WebFlux vào production

1. Ứng dụng đang chạy đúng WebApplicationType: REACTIVE hay SERVLET?
2. Có đồng thời starter-web và starter-webflux không?
3. Nếu dùng Spring Boot, có thật sự cần @EnableWebFlux không?
4. Các WebFluxConfigurer chỉ override callback cần thiết chưa?
5. Codec có default reader/writer phù hợp và memory limit hợp lý không?
6. CORS có origin, method, header và credentials đúng yêu cầu không?
7. CORS preflight có được test không?
8. Static resource location, URL mapping và cache policy có đúng không?
9. Path prefix có áp dụng đúng controller predicate không?
10. Custom argument resolver có được thêm mà không làm mất resolver mặc định không?
11. Blocking controller method có được tách khỏi event loop không?
12. WebFilter và Spring Security có thứ tự hợp lý không?
13. Error response có tuân theo API contract và không lộ dữ liệu nội bộ không?
14. WebSocket service hoặc server-specific customizer có cần thiết không?
15. Có integration test cho route, CORS, codec, static resource và error handling không?
16. Các cấu hình Boot properties có bị ghi đè ngoài ý muốn bởi custom bean không?

## 18. Bài tập tự kiểm tra

1. `@EnableWebFlux` làm gì? **Import cấu hình hạ tầng WebFlux mặc định thông qua DelegatingWebFluxConfiguration.**
2. `WebFluxConfigurer` là gì? **Interface callback để tùy chỉnh các phần của cấu hình WebFlux.**
3. Trong Spring Boot, khi chỉ cần tăng max in-memory size, nên dùng cách nào? **Implement WebFluxConfigurer không thêm @EnableWebFlux, hoặc dùng CodecCustomizer/property phù hợp.**
4. Vì sao @EnableWebFlux có thể làm mất một số Boot defaults? **WebFlux auto-configuration nhường quyền khi ứng dụng tự cung cấp WebFluxConfigurationSupport.**
5. HandlerMapping làm gì? **Tìm handler phù hợp với request.**
6. HandlerAdapter làm gì? **Gọi handler tương ứng.**
7. HandlerResultHandler làm gì? **Xử lý giá trị trả về và ghi response.**
8. HttpMessageReader và HttpMessageWriter khác nhau thế nào? **Reader decode request; Writer encode response.**
9. Callback nào cấu hình codec? **configureHttpMessageCodecs.**
10. Callback nào đăng ký CORS toàn cục? **addCorsMappings.**
11. Callback nào thêm static resource mapping? **addResourceHandlers.**
12. Callback nào thêm prefix cho controller? **configurePathMatching.**
13. Vì sao CORS credentials không nên dùng origin wildcard? **Browser không chấp nhận wildcard origin cùng Access-Control-Allow-Credentials true.**
14. maxInMemorySize có phải giới hạn upload toàn bộ không? **Không; nó giới hạn các codec operation cần aggregate vào memory.**
15. WebFilter khác WebFluxConfigurer ở đâu? **WebFilter tham gia mỗi HTTP exchange; WebFluxConfigurer tùy chỉnh hạ tầng.**
16. Vì sao không nên block event loop? **Nó làm chậm nhiều request đang chia sẻ event-loop thread.**
17. WebFlux Boot mặc định chọn server nào? **Phụ thuộc reactive server dependency; Reactor Netty thường là lựa chọn mặc định khi starter tương ứng có mặt.**
18. Khi nào dùng WebHttpHandlerBuilderCustomizer? **Khi cần tùy chỉnh HttpHandler auto-configured ở tầng thấp hơn WebFluxConfigurer.**

## 19. Ghi nhớ và tài liệu tham khảo

- `@EnableWebFlux` import `DelegatingWebFluxConfiguration` và bật cấu hình hạ tầng WebFlux.
- `WebFluxConfigurer` cho phép tùy chỉnh codec, CORS, conversion, validation, path matching, static resources, view và blocking execution.
- Trong Spring Boot, implement `WebFluxConfigurer` mà không thêm `@EnableWebFlux` để giữ auto-configuration khi chỉ cần bổ sung tùy chỉnh.
- `DispatcherHandler` phối hợp HandlerMapping, HandlerAdapter và HandlerResultHandler để xử lý request.
- Codec reader decode request; codec writer encode response. Đặt giới hạn aggregate in-memory phù hợp.
- CORS cần origin/method/header rõ ràng; credentials không đi cùng origin wildcard.
- Static resources có thể được map qua ResourceHandlerRegistry hoặc cấu hình Boot properties.
- WebFilter xử lý từng HTTP exchange; WebFluxConfigurer tùy chỉnh hạ tầng.
- Cấu hình server port/TLS/Netty thuộc server properties và WebServerFactoryCustomizer.
- Kiểm thử cấu hình bằng WebTestClient và integration test, đặc biệt là CORS preflight, route prefix và codec limit.

Tài liệu chính thức:

1. [Spring Framework 6.2 Reference — WebFlux Config](https://docs.spring.io/spring/reference/6.2/web/webflux/config.html): @EnableWebFlux, WebFluxConfigurer, codec, path matching, static resources, view resolver và blocking execution.
2. [Spring Boot 3.5 Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux auto-configuration, codec customizer, static content, error handling và reactive server.
3. [Spring Framework 6.2 Reference — WebFlux CORS](https://docs.spring.io/spring/reference/6.2/web/webflux-cors.html): preflight, global CORS, @CrossOrigin và CorsWebFilter.
4. [Spring Framework 6.2 Javadoc — WebFluxConfigurer](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html): callback contract và các phương thức cấu hình.
5. [Spring Boot 3.5 Testing Reference — WebFlux Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @WebFluxTest, test slice và WebTestClient.
6. [Spring Framework 6.2 Javadoc — DelegatingWebFluxConfiguration](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/DelegatingWebFluxConfiguration.html): cấu hình nâng cao và cơ chế delegate WebFluxConfigurer.
