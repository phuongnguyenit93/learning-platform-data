# Spring WebFlux — @EnableWebFlux, WebFluxConfigurer và cấu hình hạ tầng

## 1. Mục tiêu bài học

Khi xây API phản ứng bằng Spring WebFlux, các controller `@RestController` và functional routes chỉ là phần dễ nhìn thấy. Phía dưới còn một hạ tầng gồm handler mappings, handler adapters, result handlers, HTTP message readers/writers, converters, CORS, static resource handling, exception handling và những cầu nối tới web server.

Spring Framework cung cấp `@EnableWebFlux` và interface `WebFluxConfigurer` để bật/tùy chỉnh hạ tầng ấy. **Spring Boot lại có auto-configuration riêng** nên cách dùng hai thành phần này trong ứng dụng Boot khác với cách viết một Spring Framework application thuần.

**Nguyên tắc cần nhớ ngay từ đầu:**

- Với **Spring Boot WebFlux**: mặc định chỉ dùng `spring-boot-starter-webflux` và properties. Muốn thêm cấu hình thì viết `@Configuration implements WebFluxConfigurer` nhưng **không thêm `@EnableWebFlux`**, để giữ tiện ích Boot.
- Với **Spring Framework cấu hình thủ công** hoặc khi muốn chịu trách nhiệm quản lý hạ tầng WebFlux: dùng `@EnableWebFlux`. Trong Boot, điều này chuyển hướng quyền kiểm soát và làm nhiều phần auto-configuration WebFlux của Boot không còn được áp dụng như trước; phải tự bảo đảm các hành vi cần thiết.
- Khi cần thay thế những infrastructure beans sâu hơn API `WebFluxConfigurer`: tìm hiểu `DelegatingWebFluxConfiguration`/`WebFluxConfigurationSupport` và Boot-specific customization hooks, chỉ dùng khi có lý do rõ.

Bài này giúp bạn:

1. Vẽ đúng request processing flow WebFlux, phân biệt nó với DispatcherServlet/Spring MVC.
2. Hiểu vai trò và mức độ can thiệp của `@EnableWebFlux`, `WebFluxConfigurer` và Spring Boot auto-configuration.
3. Cấu hình formatters/converters, CORS, codecs, static resources, path matching, content negotiation, view resolvers và blocking execution.
4. Hiểu cấu hình nào thuộc WebFlux infrastructure, cấu hình nào thuộc Reactor Netty, WebClient, Spring Security hoặc Spring Boot.
5. Tránh các lỗi điển hình như tự bật `@EnableWebFlux` rồi mất mapping static, custom codec vô tình xóa JSON defaults, mở CORS wildcard với credentials hay block Netty event-loop.
6. Có một ví dụ **Java 17 / Spring Boot 3.5.0 / Maven** có thể dựng lại độc lập, cùng `WebTestClient` kiểm tra API, CORS và static resources.
7. Biết các tiêu chí quyết định khi nào chỉ dùng properties, khi nào implement `WebFluxConfigurer`, khi nào cần customizer/advanced config.

**Phạm vi:** Spring Framework 6.2, Spring Boot 3.5, Reactor trên WebFlux reactive application. Không dùng tên lớp `WebMvcConfigurer`, `@EnableWebMvc`, `DispatcherServlet` hoặc `HandlerInterceptor` của Servlet MVC như vật thay thế cho hạ tầng WebFlux.

## 2. Spring WebFlux hoạt động ở tầng nào?

### 2.1. Request flow

Mô hình được đơn giản hóa:

~~~text
Client HTTP
   |
   v
Server: Reactor Netty / supported runtime
   |
   v
HttpHandler
   |
   v
WebHttpHandlerBuilder-built processing chain
   |-- WebFilter(s)
   |-- WebExceptionHandler(s)
   |-- WebSession / locale-related handling
   |
   v
DispatcherHandler
   |
   +-- HandlerMapping: tìm handler
   |
   +-- HandlerAdapter: gọi handler
   |
   +-- HandlerResultHandler: ghi kết quả
   |       |
   |       +-- HttpMessageWriter -> JSON/text/streaming
   |       +-- View rendering
   |
   v
Reactive HTTP response (Publisher/Mono<Void>)
~~~

Tên lớp chính:

| Thành phần | Vai trò |
| --- | --- |
| `HttpHandler` | Hợp đồng mức thấp giữa web server runtime và framework |
| `HttpWebHandlerAdapter` | Adapter HTTP request/response vào WebHandler chain |
| `WebFilter` | Filter reactive trước/sau web handling (không phải Servlet Filter) |
| `WebExceptionHandler` | Xử lý lỗi trong reactive WebHandler chain |
| `DispatcherHandler` | Dispatcher chính của Spring WebFlux |
| `HandlerMapping` | Chọn controller, functional route hoặc resource handler |
| `HandlerAdapter` | Thực thi handler thích hợp |
| `HandlerResultHandler` | Render kết quả handler; có body writers và view handlers |
| `ServerCodecConfigurer` | Cấu hình các HTTP readers/writers |
| `ConversionService` | Chuyển đổi string/number/date/value cho binding |
| `RequestedContentTypeResolver` | Chọn media type phản hồi dựa trên request/config |
| `ResourceWebHandler` | Phục vụ static resources |

**Sự khác biệt với Spring MVC:** WebFlux dùng `DispatcherHandler`, không phải `DispatcherServlet`. `WebFilter` xử lý reactive request, không dựa vào Servlet FilterChain. Trong WebFlux, blocking operations trên event-loop làm suy giảm throughput, dù controller có trả về `Mono`.

### 2.2. Annotated controller và functional endpoint đều thuộc WebFlux

WebFlux hỗ trợ hai phong cách:

- Annotated: `@RestController`, `@GetMapping`, `@RequestBody Mono<T>`, `Flux<T>`.
- Functional: `RouterFunction<ServerResponse>`, `HandlerFunction<ServerResponse>`.

Các cấu hình ở WebFlux hạ tầng có thể ảnh hưởng annotated handlers, functional endpoints, static resources hoặc một nhóm nhỏ tùy hook. Ví dụ path prefix bằng `PathMatchConfigurer.addPathPrefix` chủ yếu dành cho annotated controller mappings; không được tự động suy ra nó đổi mọi `RouterFunction` path.

### 2.3. Reactive không đồng nghĩa phép màu không blocking

Một controller trả `Mono.fromCallable(() -> jdbcRepository.findAll())` vẫn gọi JDBC đồng bộ bên trong. Nếu không offload đúng chỗ, nó có thể block event-loop. WebFlux cho phép các adapters non-blocking (R2DBC, reactive WebClient), nhưng chúng không tự biến mọi SDK/JPA/JDBC blocking thành reactive.

## 3. @EnableWebFlux thực sự làm gì?

Khi dùng Spring Framework Java config thuần:

~~~java
@Configuration
@EnableWebFlux
public class ReactiveWebConfiguration {
}
~~~

Annotation `@EnableWebFlux` import `DelegatingWebFluxConfiguration`. Nó cung cấp những WebFlux infrastructure beans, phát hiện các bean triển khai `WebFluxConfigurer` và áp dụng tùy chỉnh.

Điểm chính:

- Kích hoạt cấu hình cần thiết cho annotated controllers và phần liên quan của WebFlux.
- Đăng ký handler mappings/adapters/result handlers và các mặc định thích hợp tùy dependencies trên classpath.
- Cho phép các `WebFluxConfigurer` tham gia tùy chỉnh.
- Không đồng nghĩa tự tạo Reactor Netty server hoặc mọi chức năng Boot. Việc khởi động web server, management, config binding và vận hành là trách nhiệm tầng runtime/Boot nếu sử dụng.

### 3.1. Tại sao Boot thường không cần @EnableWebFlux?

Spring Boot phát hiện reactive web application khi dùng `spring-boot-starter-webflux` (và không bị MVC starter chọn ưu tiên), rồi tự cấu hình WebFlux phù hợp:

- HTTP codecs, Jackson và các Boot `CodecCustomizer`.
- Static resource locations, mapping và welcome page.
- Error handling mặc định.
- Các properties liên quan formatters, static assets, reactive paths và một số infrastructure integration.
- Server/runtime management do Boot kết hợp.

Nếu muốn thêm CORS, converters, path matching hoặc codec cap, bạn không cần giành quyền cấu hình toàn bộ hệ thống.

**Cách được Spring Boot tài liệu khuyến nghị:**

~~~java
@Configuration
class MyWebFluxConfiguration implements WebFluxConfigurer {
    // override những methods cần thiết
    // KHÔNG gắn @EnableWebFlux
}
~~~

Đây là một phần class minh họa; ví dụ chạy đầy đủ ở mục 12.

### 3.2. Điều gì xảy ra khi thêm @EnableWebFlux trong Boot?

Trong ứng dụng Boot, `@EnableWebFlux` biểu thị mong muốn **take complete control** đối với WebFlux configuration. Boot WebFlux auto-configuration có cơ chế lùi lại khi hạ tầng đã do người dùng khai báo (không còn tự áp đặt các customizations mặc định theo cùng đường đi).

Hệ quả có thể thấy:

- Các tùy biến codec/mapping/static resources của Boot không còn được tự động áp dụng giống trước.
- Properties và auto-configuration dành cho Boot WebFlux có thể không còn điều khiển các hạ tầng tương ứng như trước; phải tự xác minh.
- Một static `index.html` vốn hoạt động trước có thể mất mapping/welcome behavior nếu chưa đăng ký lại resource handlers.
- Việc tích hợp Jackson, view resolution, exception handling hoặc argument resolvers có thể khác; cần test lại.
- Spring Security, Reactor Netty và Actuator thuộc những cấu hình liên quan khác: không nên khẳng định cứ bật `@EnableWebFlux` là mọi thứ của Boot đều biến mất. Ảnh hưởng chính là **WebFlux framework auto-configuration** và các customizations của nó.

Không phải `@EnableWebFlux` là annotation “sai”. Nó phù hợp khi kiến trúc cần full control và đội phát triển chấp nhận bảo trì/tái cấu hình hạ tầng tương ứng.

### 3.3. Bảng lựa chọn ba cấp độ

| Mục tiêu | Cách ưu tiên | Mức độ kiểm soát |
| --- | --- | --- |
| API WebFlux thông thường | Starter + Boot properties | Giữ auto-config gần như trọn vẹn |
| Thêm CORS/Converter/resource/codec limit/path rules | `@Configuration implements WebFluxConfigurer`, **không @EnableWebFlux** | Tùy chỉnh API chính thống |
| Cấu hình codec tương thích Boot trên nhiều layers | `CodecCustomizer` Bean hoặc Boot properties | Bổ sung vào Boot hạ tầng |
| Tùy chỉnh HttpHandler xây dựng bởi Boot | `WebHttpHandlerBuilderCustomizer` | Boot-specific hook chuyên biệt |
| Thay framework WebFlux infrastructure mạnh | `@EnableWebFlux`, custom config | Tự chịu trách nhiệm defaults |
| Overriding bean declarations ở mức framework | Extend `DelegatingWebFluxConfiguration` hoặc nghiên cứu `WebFluxConfigurationSupport` | Advanced, cần kiểm tra tương thích |

### 3.4. Spring Boot chọn MVC hay WebFlux thế nào?

Nếu ứng dụng có đồng thời:

~~~xml
<artifactId>spring-boot-starter-web</artifactId>
<artifactId>spring-boot-starter-webflux</artifactId>
~~~

Spring Boot thường chọn **Spring MVC** cho web application type. Điều này hữu ích khi ứng dụng MVC chỉ muốn dùng reactive `WebClient`. Nhưng nếu bài tập kỳ vọng `DispatcherHandler`, `WebFilter` và reactive server, hai starters có thể khiến kết quả sai.

Với một demo WebFlux thuần, **chỉ đưa `spring-boot-starter-webflux`**, không thêm `spring-boot-starter-web`. Nếu có lý do bắt buộc giữ cả hai, có thể ép reactive application type qua Boot API/config, nhưng phải kiểm tra toàn bộ auto-configuration, libraries và tests. Tránh ép chỉ để “cho lỗi biến mất”.

## 4. WebFluxConfigurer: interface tùy chỉnh hạ tầng

Import:

~~~java
import org.springframework.web.reactive.config.WebFluxConfigurer;
~~~

Một class có thể implement:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        // Configure route-specific CORS...
    }
}
~~~

Methods của interface có default implementations; chỉ override những phần bạn muốn. Có thể tạo **nhiều WebFluxConfigurer beans** và framework phối hợp áp dụng. Tuy nhiên những registrations của nhiều modules có thể tương tác, trùng path hoặc conflict; trong dự án lớn nên quản trị ownership và kiểm thử thứ tự/kết quả thực tế.

### 4.1. Các extension points quan trọng

| Method | Mục đích | Thời điểm dùng |
| --- | --- | --- |
| `addFormatters(FormatterRegistry)` | Đăng ký converters/formatters cho argument/data binding | Custom ID, date-time, locale |
| `addCorsMappings(CorsRegistry)` | CORS theo URL patterns | Browser frontend khác origin |
| `configurePathMatching(PathMatchConfigurer)` | Đường dẫn, prefix cho annotated controllers | Thêm API prefix có chọn lọc |
| `configureHttpMessageCodecs(ServerCodecConfigurer)` | Readers/writers, memory cap, codecs | JSON/body/streaming |
| `configureContentTypeResolver(RequestedContentTypeResolverBuilder)` | Media type negotiation | Content negotiation policy |
| `addResourceHandlers(ResourceHandlerRegistry)` | Định tuyến static assets và cache policy | CSS/JS/images/docs |
| `configureViewResolvers(ViewResolverRegistry)` | Render HTML/templates | SSR với FreeMarker/Thymeleaf |
| `configureArgumentResolvers(ArgumentResolverConfigurer)` | Thêm resolver cho custom controller args | TenantContext/auth context |
| `getValidator()` | Cung cấp Validator khi cần | Validation integration |
| `getMessageCodesResolver()` | Thay resolution của validation error codes | Form/validation messages |
| `configureBlockingExecution(BlockingExecutionConfigurer)` | Chọn executor và predicate cho blocking controller methods | Legacy blocking handlers |
| `getWebSocketService()` | Điều chỉnh service xử lý WebSocket handshake | WebSocket infra chuyên biệt |

**Lưu ý version:** Bảng nhắm Spring Framework 6.2. Những APIs thêm ở phiên bản mới hơn không mặc nhiên tồn tại ở Boot 3.5/Framework 6.2. Khi copy từ trang “current” của Spring Framework 7, cần kiểm API phiên bản.

### 4.2. addFormatters: custom conversion

Giả sử HTTP route dùng:

~~~text
GET /api/books/42
~~~

Bạn muốn `@PathVariable BookId` được parse thành một Java record:

~~~java
record BookId(long value) {}
~~~

Cấu hình:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, BookId.class,
            text -> new BookId(Long.parseLong(text)));
}
~~~

Cần `org.springframework.format.FormatterRegistry`. Khi controller khai báo:

~~~java
@GetMapping("/books/{id}")
Mono<BookDto> get(@PathVariable BookId id) {
    return Mono.just(new BookDto(id.value(), "Book"));
}
~~~

Đây là fragment trong cấu hình/controller. Khi `id` là chuỗi không parse được, binding có thể phát lỗi 400 theo framework exception handling; đừng map parse error thành 500 hoặc chấp nhận overflow mù quáng. Trong thực tế có thể dùng converter riêng, validate range ID và test invalid values.

Không tự viết parser custom cho `LocalDate`/`Instant` nếu Java time formatters hoặc `@DateTimeFormat(iso=...)` đã phù hợp. Với form fields, format theo Locale có thể khác ISO JSON serialization — hai tầng khác nhau.

### 4.3. addCorsMappings: quyền cross-origin của browser

Ví dụ:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com",
                    "http://localhost:5173")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization")
            .exposedHeaders("X-Request-ID")
            .allowCredentials(true)
            .maxAge(1800);
}
~~~

Một credentialed CORS response cần `Access-Control-Allow-Origin` tương ứng **một origin cụ thể**, không thể dùng `allowedOrigins("*")` cùng `allowCredentials(true)`. Spring Framework có `allowedOriginPatterns` nhưng một pattern quá rộng như `"*"` có thể mở credentialed CORS cho origins không đáng tin. Cho phép origin ≠ cho phép user: API vẫn cần authentication, authorization, CSRF/cookie security.

**Quan trọng:** CORS không giải quyết server-to-server authorization. `curl` không thực thi browser same-origin policy. Với Spring Security reactive, cần thiết kế thứ tự WebFilterChain và Security CORS integration để preflight OPTIONS không bị yêu cầu session/cookie; không copy cấu hình Servlet `HttpSecurity` vào WebFlux (phải dùng `ServerHttpSecurity`).

### 4.4. configurePathMatching: thêm prefix một cách có chọn lọc

Ví dụ:

~~~java
@Override
public void configurePathMatching(PathMatchConfigurer configurer) {
    configurer.addPathPrefix(
            "/api",
            HandlerTypePredicate.forAnnotation(RestController.class));
}
~~~

Import `org.springframework.web.method.HandlerTypePredicate` và `org.springframework.web.bind.annotation.RestController`.

Controller khai báo:

~~~java
@RestController
class BookController {
    @GetMapping("/books/{id}")
    Mono<BookDto> find(@PathVariable long id) {
        return Mono.just(new BookDto(id, "Book"));
    }
}
~~~

Tuyến truy cập thực tế trở thành:

~~~text
GET /api/books/42
~~~

**Đừng thêm `/api` hai lần**: nếu controller đã khai báo `@RequestMapping("/api")` và configurer lại gắn prefix `/api`, route có thể thành `/api/api/...`. Hãy chọn một owner cho prefix.

Phương thức `addPathPrefix` áp dụng theo predicate của **controller type**, không tự biến đổi mọi router function/static resource. Spring WebFlux dùng parsed `RequestPath`/`PathPatternParser` semantics; đừng mang thói quen suffix `.json` matching, `AntPathMatcher` và legacy URL decode flags của MVC vào WebFlux.

### 4.5. configureHttpMessageCodecs: giới hạn bộ nhớ và readers/writers

Codecs chuyển request body thành object và object thành body. Trong WebFlux, đọc/ghi qua:

~~~text
HTTP request Flux<DataBuffer>
   -> HttpMessageReader / Decoder
   -> DTO/Mono<T>

DTO/Flux<T>
   -> Encoder / HttpMessageWriter
   -> HTTP response body
~~~

Để đặt giới hạn buffering cho phần lớn default codecs:

~~~java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(256 * 1024);
}
~~~

Import `org.springframework.http.codec.ServerCodecConfigurer`.

Mốc này giới hạn lượng bytes được aggregate trong memory theo codec operations nhất định; **không phải** overall server RAM limit, request concurrency limit, Netty receive buffer size hoặc một cách thay thế upload quota. Với payload vượt mức, bạn có thể gặp `DataBufferLimitException` khi có operation buffer/aggregate. Cần xác minh exception/status/error contract và tests, không tự giả định mọi request 300KB chắc chắn HTTP 413 trong mọi codec path.

**Không dùng**:

~~~java
configurer.registerDefaults(false);
~~~

chỉ để “tăng giới hạn” hoặc “tối ưu hiệu năng”: call này vô hiệu default readers/writers, dễ làm JSON request/response fail vì không có codec phù hợp. Chỉ thay thế toàn bộ defaults khi bạn hiểu và tự đăng ký bộ codecs cần thiết.

### 4.6. Boot CodecCustomizer và properties

Spring Boot 3.5 cũng hỗ trợ `CodecCustomizer` và properties dưới `spring.http.codecs.*`, cùng tích hợp Jackson. Nếu nhu cầu đã có property Boot tương đương, nên ưu tiên property để giảm code và tránh nhiều layers cùng set giá trị.

Đây là fragment minh họa một customizer:

~~~java
@Bean
CodecCustomizer codecLimits() {
    return configurer ->
            configurer.defaultCodecs().maxInMemorySize(256 * 1024);
}
~~~

Trong Spring Boot 3.5, kiểu `CodecCustomizer` được cung cấp trong package phù hợp phiên bản Boot; khi dùng cần kiểm import Javadoc của chính version dependency, không copy nhầm từ Boot 4.0/4.1 vì packages đã thay đổi ở một số module. Nếu project đã có `WebFluxConfigurer.configureHttpMessageCodecs` cho cùng settings, chỉ chọn **một owner** để dễ kiểm soát precedence.

### 4.7. configureContentTypeResolver: content negotiation

Trong annotated controllers, framework dùng requested content type resolver từ HTTP request. Thông thường nên dựa trên `Accept` header và `produces/consumes`:

~~~http
GET /api/books/42
Accept: application/json
~~~

Controller:

~~~java
@GetMapping(path = "/books/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
Mono<BookDto> get(@PathVariable long id) { ... }
~~~

Trong config:

~~~java
@Override
public void configureContentTypeResolver(
        RequestedContentTypeResolverBuilder builder) {
    // Chỉ thêm policy thật sự được thiết kế.
}
~~~

Đây là fragment (cần import `org.springframework.web.reactive.accept.RequestedContentTypeResolverBuilder`), không phải ví dụ runnable độc lập. Không vội bật path-extension negotiation (`.json`/`.xml`) nếu có thể dùng Accept vì có rủi ro liên quan URL format/ambiguity và cache behavior. Kiểm 406 Not Acceptable/415 Unsupported Media Type trong API tests khi customize.

### 4.8. addResourceHandlers: static assets có cache

Ví dụ:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/guide/**")
            .addResourceLocations("classpath:/guide-assets/")
            .setCacheControl(CacheControl
                    .maxAge(Duration.ofMinutes(5))
                    .cachePublic());
}
~~~

Imports cần có: `java.time.Duration`, `org.springframework.http.CacheControl`, `org.springframework.web.reactive.config.ResourceHandlerRegistry`.

Giả sử file:

~~~text
src/main/resources/guide-assets/intro.txt
~~~

HTTP route:

~~~text
GET /guide/intro.txt
~~~

được `ResourceWebHandler` xử lý, không cần controller.

Chỉ phục vụ các classpath/static locations đã chọn; không map tùy tiện file system root (`file:/`) hoặc upload directory chứa PII. Với static JS/CSS versioned URLs, có thể dùng ResourceResolver/VersionResourceResolver và cache dài hơn; nếu file name không versioned mà vẫn cache một năm, người dùng có thể thấy phiên bản cũ sau deploy.

### 4.9. configureViewResolvers và template rendering

WebFlux không chỉ phục vụ JSON. Với Thymeleaf/FreeMarker/Mustache hoặc HTML responses, view resolvers có thể được cấu hình:

~~~java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    // Thêm view resolver khi thực sự cần, hoặc dùng Boot auto-config.
}
~~~

Đây là fragment không có resolver đăng ký cụ thể. Với Spring Boot, thêm template starter phù hợp và đặt HTML templates trong `src/main/resources/templates` thường đủ. Không viết resolver thủ công nếu chỉ muốn mặc định.

### 4.10. configureArgumentResolvers: custom method arguments

Một ứng dụng multi-tenant có thể muốn:

~~~java
@GetMapping("/me")
Mono<ProfileDto> me(CurrentTenant tenant) { ... }
~~~

Muốn WebFlux tự resolve `CurrentTenant`, có thể đăng ký custom `HandlerMethodArgumentResolver` qua:

~~~java
@Override
public void configureArgumentResolvers(
        ArgumentResolverConfigurer configurer) {
    configurer.addCustomResolver(new TenantArgumentResolver());
}
~~~

Fragment này cần implement `TenantArgumentResolver` của WebFlux, không dùng servlet `HandlerMethodArgumentResolver` từ MVC package. Resolver phải non-blocking, không tin request header tenant tùy ý mà thiếu authentication/authorization. Dùng `ReactiveSecurityContextHolder` hoặc service/lookup được tin cậy.

### 4.11. Validator và validation

WebFlux có thể validate input models qua Jakarta Bean Validation nếu provider phù hợp nằm trên classpath. `WebFluxConfigurer#getValidator()` có thể dùng khi cần Validator riêng, nhưng trong Boot thường chỉ cần dependency starter validation và annotations.

Ví dụ:

~~~java
record CreateBookRequest(
        @NotBlank String title
) {}
~~~

Controller:

~~~java
@PostMapping("/books")
Mono<BookDto> create(@Valid @RequestBody Mono<CreateBookRequest> input) {
    return input.map(this::save);
}
~~~

Đây là fragment minh họa: phương thức `save`, imports/validation provider cần tồn tại. Với reactive arguments, cơ chế validation và exception types phụ thuộc cách khai báo signature; kiểm `WebExchangeBindException`/validation exception semantics trước khi map status/error payload.

**Đừng thay Validator** nếu chỉ muốn dùng `@NotBlank` thông thường. Kiểm validation error messages không trả rejected secret values cho client.

### 4.12. configureBlockingExecution: bridge cho blocking controller methods

Spring Framework 6.2 có:

~~~java
@Override
public void configureBlockingExecution(
        BlockingExecutionConfigurer configurer) {
    configurer.setExecutor(myAsyncTaskExecutor);
}
~~~

Fragment: `myAsyncTaskExecutor` là một `AsyncTaskExecutor` được quản lý. Framework cho phép cấu hình executor và predicate xác định những controller methods được xem là blocking (mặc định liên quan reactive adapter registry và return types).

Điểm quan trọng:

- **Không đồng nghĩa mọi blocking call trong `Mono.map` tự được offload.**
- Nếu bạn dùng JDBC/SDK blocking trong reactor chain, cần cân nhắc `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` hoặc chuyển sang non-blocking library.
- Blocking execution executor phải có limits, thread-name, metrics, shutdown policy và timeout; không tạo thread-per-request vô hạn.
- `WebFluxConfigurer.configureBlockingExecution` cấu hình handler invocation cho các methods được nhận diện, **không phải thay thế cho Reactor scheduler strategy**.

### 4.13. WebSocket service

`WebFluxConfigurer#getWebSocketService()` hỗ trợ customization của WebSocket handshake service trong WebFlux. Đừng cố cấu hình WebSocket qua CORS mappings như một biện pháp an ninh duy nhất. WebSocket có Origin validation, authentication và message-level auth riêng; Spring Security reactive và gateway/proxy rules cũng quan trọng.

## 5. WebFluxConfigurer không quản lý mọi thứ

Một lỗi kiến trúc là dồn bất cứ thiết lập WebFlux/Netty nào vào WebFluxConfigurer, dù chúng thuộc các tầng khác.

| Nhu cầu | Tầng phù hợp |
| --- | --- |
| Controller routing / converters / CORS | `WebFluxConfigurer` |
| HTTP body codecs | `WebFluxConfigurer.configureHttpMessageCodecs`, `CodecCustomizer`, Boot properties |
| Client-side WebClient timeouts | `WebClient.Builder`, Reactor Netty HttpClient, connector |
| Server port/TLS/compression | Boot server properties, `NettyReactiveWebServerFactory`/customizer |
| Authentication/authorization | Spring Security `SecurityWebFilterChain` |
| Cross-cutting request filter | `WebFilter` |
| Correlation/tracing/logging | Observability/Micrometer, Reactor Context/WebFilter |
| Business caching | Service/repository cache, HTTP headers/cache rules |
| Functional routes | `RouterFunction` bean, RouterFunctions DSL |
| Global errors | `@RestControllerAdvice`, `ErrorWebExceptionHandler` |
| Backpressure and scheduling | Reactor operators/Schedulers, source design |
| Reactive DB transaction | R2DBC/reactive transaction manager |
| Proxy forwarding | Forwarded header transformer/trusted proxy + Boot config |

**Chọn cấu hình ở đúng tầng.** Ví dụ WebFluxConfigurer CORS không cấp auth, một Netty timeout không tương đương Mono.timeout cho toàn bộ pipeline, và Reactor Context không giống Servlet ThreadLocal.

## 6. Cấu trúc cấu hình hạ tầng và thứ tự xử lý

### 6.1. Multiple WebFluxConfigurer beans

Framework có thể nhận nhiều `WebFluxConfigurer`. Ví dụ:

~~~java
@Configuration
class CorsWebConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com");
    }
}

@Configuration
class CodecWebConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

Hai đoạn config này là fragments có imports tương ứng. Tuy framework tổng hợp customizers, bạn vẫn phải kiểm các xung đột:

- Cùng một path có nhiều CORS definitions khó hiểu.
- Một bean đặt limit 256KB, bean khác 1MB; final value có thể phụ thuộc thứ tự applied registrations.
- Hai pathPrefix rules dẫn tới route bất ngờ hoặc conflict.
- Custom codec thay default readers/writers mà một module khác dựa vào.
- Nhiều handler mappings/predicates đè nhau khiến route khó tìm.

Với cấu hình rủi ro bảo mật, tốt nhất có **một owner được kiểm soát**, hợp nhất policy rõ và regression tests.

### 6.2. @Order không phải lời giải cho mọi xung đột

Spring hỗ trợ ordering cho một số config beans và handler/filter chains, nhưng chỉ thêm `@Order(0)` không tự giải thích semantics khi nhiều customizers cùng sửa mutable config. Điều quan trọng là kiểm final HandlerMapping/codec/CORS policy và hành vi HTTP thực, không đoán "config cuối cùng thắng".

### 6.3. Request mapping và ResourceHandlerMapping

Các `HandlerMapping` được đăng ký bởi WebFlux infrastructure có ordering nhằm chọn annotated controllers, functional routes, resource handling, view/welcome page. Resource handlers thường là fallback để không chiếm route API. Nhưng một broad mapping như `/**` hoặc custom RouterFunction có thể tạo bất ngờ nếu ordering không được kiểm.

Không đăng ký một `RouterFunction` bắt mọi path chỉ để thêm metrics, khiến static/error handlers mất cơ hội chạy. Cross-cutting concern nên dùng `WebFilter`/observation layer phù hợp.

## 7. Spring Boot properties thường gặp

Một số cấu hình Boot 3.5:

~~~properties
# Server:
server.port=8080

# Static assets:
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/

# Formatters (tuỳ nhu cầu):
spring.webflux.format.date=iso
spring.webflux.format.time=iso
spring.webflux.format.date-time=iso
~~~

Đây là **ví dụ minh họa properties**, không phải file properties áp dụng trong demo ở mục 12. Nếu dùng `spring.webflux.static-path-pattern=/assets/**` thì mặc định static resources sẽ nằm dưới `/assets/**` thay vì `/**`. Nếu dùng `spring.web.resources.static-locations`, danh sách custom sẽ thay default locations; phải kiểm welcome page và file locations.

**Lưu ý:** Giá trị `iso` cho Spring Boot format properties cần được kiểm theo Boot 3.5 configuration binding/format settings của version bạn dùng; với APIs quan trọng, sử dụng DateTimeFormatterRegistrar rõ ràng hoặc test parse input. Không dùng `spring.mvc.*` để cấu hình reactive WebFlux routes.

### 7.1. Codec configuration properties

Spring Boot 3.5 documentation mô tả nhóm `spring.http.codecs.*`, các `CodecCustomizer` và Jackson config liên quan. Trong các dự án nâng cấp từ Boot 2.x/3.x, có thể gặp property keys cũ; đối chiếu **configuration metadata của đúng phiên bản Boot** thay vì đoán giá trị nào đang có hiệu lực.

Nếu cần limit aggregation trong demo, Java API ở mục 12 đảm bảo cấu hình được áp dụng qua `WebFluxConfigurer` mà không phụ thuộc property key/version alias.

### 7.2. global WebFlux base path vs controller prefix

Boot có thể cung cấp cấu hình application base path riêng với annotated controller prefix. Khi chọn base path ở tầng server/framework, nó có thể ảnh hưởng các loại mappings khác như static assets/functional routes. Còn:

~~~java
configurer.addPathPrefix(
    "/api",
    HandlerTypePredicate.forAnnotation(RestController.class));
~~~

chỉ nhắm controller types khớp predicate. Đừng dùng **cả hai** cho cùng một mục tiêu và dẫn đến `/api/api/...`. Ghi rõ ai quản lý public mount prefix: reverse proxy, Boot base path hay controller mapping.

## 8. CORS + Security trong WebFlux

CORS được xử lý theo browser protocol: Origin, preflight OPTIONS và response headers. `WebFluxConfigurer#addCorsMappings` thường cung cấp chính sách cho WebFlux HandlerMapping; khi thêm Spring Security reactive cần kiểm preflight không bị ngăn quá sớm.

### 8.1. Origin cụ thể và credentials

Ví dụ safe-ish cho SPA được tin:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type", "Authorization")
        .allowCredentials(true);
~~~

**Phải hiểu rằng:** với cookie session credentials, CORS cho phép một origin đọc response khi user có credentials hợp lệ. Nó **không tự bảo vệ CSRF**. Cần cookie SameSite/Secure/HttpOnly, server auth/authz và CSRF policy. Đừng dùng `allowedOriginPatterns("*")` để “né” lỗi wildcard+credentials.

### 8.2. Reactive security khác Servlet security

Với WebFlux, code security cơ bản dùng `ServerHttpSecurity` và `SecurityWebFilterChain`, không phải `HttpSecurity` và `SecurityFilterChain` của Servlet.

Fragment:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .cors(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/**").authenticated()
                    .anyExchange().permitAll())
            .build();
}
~~~

Fragment **không runnable độc lập**, cần `spring-boot-starter-security`, auth provider, CSRF policy và imports `ServerHttpSecurity`/`SecurityWebFilterChain`/`Customizer`. Không thêm fragment này vào demo ở mục 12 nếu chưa thiết kế cơ chế login, vì khi có starter-security, endpoints có thể bị chặn khác kỳ vọng.

### 8.3. Preflight không có cookie auth

Browser preflight OPTIONS không mang credentials của actual request theo cách thông thường, nên yêu cầu session cho mọi OPTIONS trước CORS handling có thể trả 401/403. Hãy để reactive CORS handling chạy đúng thứ tự với security, không “sửa” bằng cách tắt authorization toàn bộ API.

### 8.4. Vary, exposed headers và HTTP caching

Nếu server trả ACAO khác nhau theo Origin, cần `Vary: Origin` để shared caches không tái dùng response với origin khác sai. Khi frontend cần đọc `X-Request-ID` ngoài response header safelist, dùng `exposedHeaders("X-Request-ID")`. Đừng coi exposure của header là authentication permission.

## 9. Codecs, streaming và memory safety

### 9.1. Giới hạn maxInMemorySize có mục đích gì?

WebFlux có thể đọc JSON/XML/aggregated text bodies bằng codecs. Nếu không giới hạn, nhiều concurrent requests lớn sẽ tiêu tốn direct/heap memory. Cấu hình:

~~~java
configurer.defaultCodecs().maxInMemorySize(256 * 1024);
~~~

giúp một số operations không aggregate payload vượt ngưỡng đã định. Không có nghĩa server **không thể stream file 1GB**: nếu streaming giữ dữ liệu trong chunks và không buffer toàn bộ, policy khác. Nếu upload/file/JSON sâu cần những giới hạn riêng:

- Reverse proxy body size.
- Netty/body decoder limits.
- Memory aggregation cap.
- Business validation/JSON nesting depth.
- Concurrency and rate limits.
- Per-user quotas và multipart configuration.

### 9.2. Pooled DataBuffer ownership

Nếu bạn custom `HttpMessageReader`/`HttpMessageWriter` hoặc trực tiếp xử lý `Flux<DataBuffer>`, một số DataBuffers dựa trên pooled reference-counted Netty buffers. Chỉ release khi ứng dụng sở hữu chúng, dùng `DataBufferUtils.release(...)` và discard policies thích hợp. **Không double-release** buffers mà framework còn cần/đã tự release.

Đừng custom toàn bộ codecs chỉ vì muốn đổi một JSON property name. Sử dụng Jackson annotations, Boot `spring.jackson.*` hoặc Jackson configuration ở nơi phù hợp.

### 9.3. SSE và Flux<DataBuffer>

WebFlux hỗ trợ streaming response `Flux<ServerSentEvent<T>>` và raw binary streams. `ServerCodecConfigurer` ảnh hưởng writers/encoders của một số media types. Khi custom codecs hoặc message readers, cần test:

- `application/json` 200/400/415/406.
- `text/event-stream` streaming không bị buffer vô hạn.
- Error handling trước và sau response commit.
- Cancellation và pooled DataBuffer release.
- Slow client/backpressure và proxy buffering.

Một codec override có thể hoạt động với GET JSON nhỏ nhưng làm SSE hoặc multipart hỏng; test đa dạng payload.

## 10. Spring WebFlux static assets

### 10.1. Mặc định trong Boot

Spring Boot WebFlux thông thường hỗ trợ static files trong classpath locations:

~~~text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
~~~

Ví dụ đặt:

~~~text
src/main/resources/static/index.html
src/main/resources/static/app.js
~~~

là cách đơn giản để phục vụ welcome page/static assets nếu auto-config còn nguyên và routing không trùng.

### 10.2. Custom resource handler

Một custom handler bổ sung:

~~~java
registry.addResourceHandler("/guide/**")
        .addResourceLocations("classpath:/guide-assets/")
        .setCacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePublic());
~~~

Chỉ tạo file ở `src/main/resources/guide-assets/intro.txt`, không cần controller. Với cache, nên tách:

- Versioned immutable JS/CSS: public long max-age.
- Unversioned docs có thể đổi: short max-age/no-cache + validators.
- Private files: **không đưa vào public static handler**; phục vụ qua authenticated controller/service có policy.

### 10.3. Security và path traversal

Framework resource handling hỗ trợ path normalization và location protections, nhưng đừng mở `file:/` tới cả filesystem hay một thư mục upload có tài liệu người dùng riêng tư. Không dựa vào file extension hoặc CORS để bảo vệ file nhạy cảm.

### 10.4. Static resources sau @EnableWebFlux

Nếu thêm `@EnableWebFlux` để “bật WebFlux” trong Boot và static `/index.html` bắt đầu 404, nguyên nhân có thể là Boot auto-config static mapping/welcome page đã không còn áp dụng. Cần quay về Boot defaults hoặc khai báo resource handlers theo mong muốn. **Đừng sửa bằng cách thêm controller GET /** nếu chỉ muốn phục hồi static auto configuration.

## 11. Advanced configuration và WebHttpHandlerBuilderCustomizer

### 11.1. Khi WebFluxConfigurer chưa đủ

`WebFluxConfigurer` giúp thêm registry-based configuration mà không phải biết từng infrastructure bean. Nhưng khi cần override sâu hơn:

- Cách tạo/tùy chỉnh HandlerMappings hoặc HandlerAdapters.
- Thứ tự WebExceptionHandler hoặc WebFilter chain.
- Tùy chỉnh HttpHandler building logic.
- Custom framework object registration và behavior ngoài interface extension points.

Spring Framework cho phép lấy quyền sâu hơn bằng `DelegatingWebFluxConfiguration` hoặc `WebFluxConfigurationSupport`. Tuy nhiên **đây không phải cách mặc định** trong Boot, có thể làm thay đổi baseline auto-config và tăng maintenance cost.

### 11.2. WebHttpHandlerBuilderCustomizer trong Boot

Tài liệu Spring Boot WebFlux cung cấp `WebHttpHandlerBuilderCustomizer` khi muốn tùy chỉnh `HttpHandler` đã được auto-configured. Đây là Hook Boot-specific, khác WebFluxConfigurer. Nên xem exact API và thứ tự filter/error handler trước khi can thiệp.

Không tự dựng một `HttpHandler` khác hoặc đổi adapter Netty ở production chỉ để log một header; dùng WebFilter/observability trước.

### 11.3. WebFilter, WebExceptionHandler

- `WebFilter` là reactive cross-cutting filter, thích hợp cho header/correlation/context và chính sách yêu cầu.
- `WebExceptionHandler` là low-level error handler.
- `@RestControllerAdvice` xử lý lỗi controller rõ ràng, gần API contract hơn.

Không xử lý exceptions bằng cách subscribe fire-and-forget trong filter; return Publisher để framework quản lý cancellation và backpressure. Khi HTTP response committed, handler không thể đổi status/headers đã gửi.

### 11.4. Không override framework internals tùy tiện

WebFlux infrastructure tự thay đổi theo Spring versions. Nếu override beans từ `DelegatingWebFluxConfiguration` bằng custom subclasses, cần kiểm:

- Bean names/types và conditional auto-config.
- Ordering handler mappings/result handlers.
- Codec availability (JSON, SSE, multipart).
- Reactive Security integration.
- Static resources, CORS, views.
- Error handling, observability.
- Upgrade path từ Framework 6.2 sang 7.x.

Chỉ thực hiện khi có tests hồi quy cho mọi lớp liên quan và team chấp nhận maintenance.

## 12. Dự án Java 17 / Spring Boot 3.5.0 chạy được

Ứng dụng minh họa nhiều extension points trong **một cấu hình WebFluxConfigurer không có @EnableWebFlux**:

- `configurePathMatching` thêm `/api` cho annotated REST controllers.
- `addFormatters` chuyển path string sang `BookId`.
- `addCorsMappings` giới hạn trusted frontend origins.
- `configureHttpMessageCodecs` đặt maxInMemorySize 256KiB cho default codecs.
- `addResourceHandlers` phục vụ `/guide/intro.txt` từ `classpath:/guide-assets/`.
- Giữ Boot static default: `/boot-health.txt` từ `classpath:/static/`.
- Controller trả JSON, nhận POST JSON và một header `X-Request-ID`.
- Tests `WebTestClient` kiểm route prefix/converter, CORS preflight, resource handler, preserved Boot static behavior.

Không thêm `spring-boot-starter-web`, không thêm `@EnableWebFlux`. Đây là điểm quan trọng của ví dụ.

### 12.1. Cấu trúc

~~~text
webflux-infrastructure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/WebFluxInfrastructureApplication.java
    │   └── resources/
    │       ├── static/boot-health.txt
    │       └── guide-assets/intro.txt
    └── test/java/demo/WebFluxInfrastructureTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-infrastructure-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

### 12.3. WebFluxInfrastructureApplication.java

Lưu **toàn bộ** code dưới đây vào `src/main/java/demo/WebFluxInfrastructureApplication.java`. Chỉ class khởi động là public top-level; các record/class còn lại package-private nên đặt chung file hợp lệ trong Java 17.

~~~java
package demo;

import java.time.Duration;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.method.HandlerTypePredicate;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.PathMatchConfigurer;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxInfrastructureApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxInfrastructureApplication.class, args);
    }
}

record BookId(long value) {
}

record BookResponse(long id, String title) {
}

record CreateBookRequest(String title) {
}

@Configuration(proxyBeanMethods = false)
class MyWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void configurePathMatching(PathMatchConfigurer configurer) {
        configurer.addPathPrefix(
                "/api",
                HandlerTypePredicate.forAnnotation(RestController.class));
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, BookId.class,
                source -> new BookId(Long.parseLong(source)));
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com",
                        "http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(true)
                .maxAge(1800);
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/guide/**")
                .addResourceLocations("classpath:/guide-assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}

@RestController
class BookController {

    @GetMapping(path = "/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<BookResponse> book(@PathVariable BookId id) {
        if (id.value() <= 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ID must be positive"));
        }
        return Mono.just(
                new BookResponse(id.value(), "Book #" + id.value()));
    }

    @PostMapping(path = "/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<BookResponse>> create(
            @RequestBody Mono<CreateBookRequest> request) {
        return request.map(input -> {
            if (input.title() == null || input.title().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Title required");
            }

            return ResponseEntity.status(HttpStatus.CREATED)
                    .header("X-Request-ID",
                            UUID.randomUUID().toString())
                    .body(new BookResponse(1001L, input.title()));
        });
    }
}
~~~

**Giải thích runnable code:**

1. `@SpringBootApplication` chọn Boot auto-configuration và khởi động Reactor Netty web server từ starter-webflux.
2. `MyWebFluxConfig implements WebFluxConfigurer` nhưng **không @EnableWebFlux** giữ Boot baseline.
3. `@GetMapping("/books/{id}")` được prefix thành `/api/books/{id}` do `HandlerTypePredicate.forAnnotation(RestController.class)`.
4. `BookId` là value object, converter parse string path variable bằng `Long.parseLong`.
5. CORS chỉ áp dụng `/api/**`, GET/POST và trusted origins; credentials yêu cầu origin cụ thể.
6. `ServerCodecConfigurer` giới hạn một số aggregation operations; default JSON codecs vẫn được giữ.
7. `ResourceHandlerRegistry` bổ sung `/guide/**`, không tự xóa static mapping mặc định của Boot.
8. POST sinh `X-Request-ID` và expose header cho JavaScript cross-origin được phép, nhưng UUID demo không thay distributed tracing thực.
9. 1001L là ID giả cố định để minh họa, **không phải persistence**; muốn API thực cần repository, transactions và uniqueness.
10. Code không thêm Spring Security để tests có thể tập trung vào WebFlux infrastructure; production bắt buộc thiết kế auth/authz/CSRF phù hợp.

### 12.4. Tạo static files

`src/main/resources/guide-assets/intro.txt`:

~~~text
WebFlux infrastructure guide
~~~

`src/main/resources/static/boot-health.txt`:

~~~text
Boot static resource remains available
~~~

Hai files không được đặt trong `src/main/webapp`. Spring Boot reactive app dùng classpath static resources thay vì cấu trúc WAR Servlet truyền thống.

### 12.5. Khởi chạy

Trong thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Gọi:

~~~bash
curl -i http://localhost:8080/api/books/42
~~~

Response body tương đương:

~~~json
{"id":42,"title":"Book #42"}
~~~

Gọi URL **không có prefix**:

~~~bash
curl -i http://localhost:8080/books/42
~~~

Dự kiến không khớp controller mapping; 404 được trả về theo default routing (có thể có static handler fallback).

Thử POST:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  --data '{"title":"Reactive Spring"}'
~~~

Response HTTP 201, một header X-Request-ID được server tạo, body:

~~~json
{"id":1001,"title":"Reactive Spring"}
~~~

Đọc static guide:

~~~bash
curl -i http://localhost:8080/guide/intro.txt
~~~

Body:

~~~text
WebFlux infrastructure guide
~~~

Đọc Boot static mặc định:

~~~bash
curl -i http://localhost:8080/boot-health.txt
~~~

Body:

~~~text
Boot static resource remains available
~~~

Đây là tiêu chí test hữu ích để chứng minh Boot auto-configuration vẫn còn khi không dùng `@EnableWebFlux`.

### 12.6. Curl kiểm CORS preflight

Một browser SPA trên `http://localhost:5173` gửi POST JSON có thể dùng OPTIONS preflight:

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/books \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Response thường có:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

Headers có thể khác thứ tự/casing; đừng so raw text cứng. Khi Origin không được phép:

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/books \
  -H 'Origin: https://attacker.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Spring WebFlux CORS processing thường từ chối preflight (ví dụ 403). Browser không gửi actual POST khi preflight không thành công, nhưng `curl` vẫn nhận HTTP response vì curl không thực thi SOP.

## 13. Kiểm thử WebTestClient

Tạo file `src/test/java/demo/WebFluxInfrastructureTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxInfrastructureTest {

    @Autowired
    WebTestClient http;

    @Test
    void prefixedControllerAndConverterWork() {
        http.get().uri("/api/books/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(42)
                .jsonPath("$.title").isEqualTo("Book #42");
    }

    @Test
    void invalidIdGetsBadRequest() {
        http.get().uri("/api/books/0").exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void postJsonKeepsDefaultCodec() {
        http.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateBookRequest("Reactive"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("X-Request-ID")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactive");
    }

    @Test
    void trustedOriginPreflightIsAllowed() {
        http.options().uri("/api/books")
                .header(HttpHeaders.ORIGIN,
                        "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173")
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true");
    }

    @Test
    void untrustedOriginPreflightIsRejected() {
        http.options().uri("/api/books")
                .header(HttpHeaders.ORIGIN,
                        "https://attacker.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void customStaticResourceWorks() {
        http.get().uri("/guide/intro.txt")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "max-age=300")
                .expectBody(String.class)
                .value(body -> org.junit.jupiter.api.Assertions.assertTrue(
                        body.contains("WebFlux infrastructure guide")));
    }

    @Test
    void bootDefaultStaticResourceIsStillAvailable() {
        http.get().uri("/boot-health.txt")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> org.junit.jupiter.api.Assertions.assertTrue(
                        body.contains("Boot static resource remains available")));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Vì sao chọn WebTestClient với RANDOM_PORT?** Bộ kiểm thử kết nối tới HTTP server được Boot khởi động, qua reactive network runtime, nên phù hợp để kiểm hạ tầng, static files và CORS thực tế hơn việc chỉ tự gọi controller method. `WebTestClient` còn có mode bindToApplicationContext cho slice/unit tests khi không cần socket.

**Giới hạn:** Sample dùng `spring-boot-starter-test`, không tích hợp gateway hoặc Spring Security; tests không thay thế security integration, reverse proxy CORS/headers và production traffic validation. Các imports dư trong ví dụ test nếu IDE báo warning có thể được gỡ mà không ảnh hưởng test behavior.

### 13.1. Một lỗi dễ bỏ qua ở test CORS

Test OPTIONS preflight cần cả:

- `Origin`.
- `Access-Control-Request-Method`.
- `Access-Control-Request-Headers` nếu actual request gửi custom/non-safelisted headers.

Chỉ gửi `Origin` cùng method OPTIONS có thể bị hiểu thành một actual cross-origin OPTIONS request, không phải preflight. Test phải phản ánh browser behavior.

### 13.2. Kiểm giới hạn codec

Muốn test `maxInMemorySize`, tạo payload thực sự cần được aggregate/decoded vượt giới hạn, rồi kiểm exception/status theo setup. Đừng hardcode assert 413 nếu framework default error mapping của phiên bản đang dùng không cam kết status ấy. Với production, quyết định một error contract rõ (ví dụ HTTP 413 khi body vượt giới hạn policy) và test integration.

### 13.3. Test negative cases

Bên cạnh happy-path, nên bổ sung:

- `/books/42` không tự được map khi đã prefix `/api`.
- Origin `https://attacker.example` không được cấp ACAO.
- POST JSON thiếu title trả 400 chứ không 500.
- Converter ID `abc` trả 400 (tùy binding semantics đã cấu hình).
- Unsupported content type POST trả 415; Accept không phù hợp có thể trả 406.
- File ngoài `guide-assets` không được route công khai.
- Body vượt memory cap theo codec aggregate path.
- Nếu thêm Spring Security, preflight/actual auth, CSRF và 401/403 đều đúng.
- Nếu thêm `@EnableWebFlux`, static resource regression test có thể phơi ra Boot auto-config loss.

## 14. So sánh với @EnableWebFlux: ví dụ cấu hình thay thế

Một Spring Framework app không dựa vào Boot WebFlux auto-config có thể định nghĩa:

~~~java
@Configuration
@EnableWebFlux
class StandaloneWebFluxConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com");
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Đây là **phương án thay thế**, **không thêm vào demo mục 12**. Nếu bạn copy cấu hình này vào Boot app, có thể thay đổi baseline static/resource/codec configurations do Boot cung cấp. Để giữ Boot defaults, bỏ annotation `@EnableWebFlux` và chỉ giữ WebFluxConfigurer.

### 14.1. Khi thật sự cần full control

Dùng khi:

- Framework integration rất đặc thù không đáp ứng bởi Boot properties/WebFluxConfigurer.
- Ứng dụng xây môi trường runtime riêng không dùng Boot autoconfig.
- Cần thay thế hạ tầng beans và chấp nhận bảo trì regression tests.
- Security/compliance demands dẫn tới một custom exact infrastructure configuration đã được kiểm toán.

Không dùng khi chỉ muốn thêm một converter hoặc CORS mapping.

### 14.2. DelegatingWebFluxConfiguration và WebFluxConfigurationSupport

`@EnableWebFlux` nhập `DelegatingWebFluxConfiguration`, cấu hình này kế thừa `WebFluxConfigurationSupport` và áp dụng các `WebFluxConfigurer` implementations.

Trong advanced mode, có thể trực tiếp extend `DelegatingWebFluxConfiguration` và override infrastructure bean declarations khi cần. Nhưng:

- Đây là thay đổi sâu vào framework lifecycle.
- Dễ mất Boot defaults nếu trộn sai.
- Cần đọc Javadoc cho exact version.
- Override chỉ được xác nhận an toàn sau khi kiểm path mapping, codecs, errors, security, static resources, blocking handlers và HTTP integration.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Tự thêm @EnableWebFlux, static index.html biến mất | Boot WebFlux auto-config không còn cung cấp defaults giống trước | Bỏ @EnableWebFlux nếu không cần full control |
| @EnableWebFlux rồi JSON codec behavior khác | Boot CodecCustomizer/properties không còn áp dụng như mong đợi | Cấu hình lại hoặc trả về Boot managed config |
| API GET có /api/api/... | Prefix tại configurer và controller cùng khai báo | Chọn một owner cho prefix |
| CORS preflight 403 | Origin/method/header không có trong policy | Kiểm đúng preflight headers |
| CORS preflight 401 khi có Security | Reactive security filter chạy trước CORS handling phù hợp | Integrate CORS đúng với ServerHttpSecurity |
| Wildcard Origin + credentials error | Cấu hình CORS không hợp lệ | Exact allowlist; tránh pattern quá rộng |
| Dùng WebMvcConfigurer nhưng không có tác dụng | App chạy WebFlux, không phải MVC | Dùng WebFluxConfigurer |
| Có cả starter-web và starter-webflux nhưng handler không reactive | Boot chọn MVC theo default selection | Chỉ dùng starter-webflux hoặc chọn app type có chủ đích |
| JSON body lớn ném DataBufferLimitException | Codec aggregation vượt giới hạn | Review cap/payload/streaming/413 policy |
| Gọi registerDefaults(false) và mất JSON | Vô hiệu default codecs | Chỉ bổ sung codec cần, giữ defaults |
| Static asset 404 | File không nằm classpath/route mismatch | Kiểm resource location/path pattern |
| CORS đúng nhưng cookie không gửi | SameSite/Secure/cross-site restrictions | Debug browser cookies, not CORS alone |
| Blocking JDBC làm request chậm hàng loạt | Chặn event-loop | Native reactive DB hoặc boundedElastic |
| @Order không giải quyết codec conflict | Hai configs thay cùng mutable setting | Một owner, test final behavior |
| WebFilter đọc ServletRequest không được | Dùng sai stack abstraction | WebFlux ServerWebExchange/WebFilter |
| 500 sau khi streaming response bắt đầu | Response committed, không thay status được | In-band error or cancel/log |
| App gọi Codecs từ Boot 4 docs trong Boot 3.5 | Khác packages/property API | Đọc Javadocs đúng version |
| Async cancel không dọn resource | Resource không scope theo subscription | using/usingWhen/doFinally và tests |

## 16. Checklist code review / vận hành

- [ ] Ứng dụng thật sự được Boot chọn **REACTIVE** chứ không vô tình MVC.
- [ ] Không thêm `@EnableWebFlux` trong Boot chỉ để bật WebFlux.
- [ ] Configurer bổ sung những chức năng cụ thể; không override mọi thứ.
- [ ] Các Boot properties được dùng đúng phiên bản và tests chứng minh chúng có hiệu lực.
- [ ] Codec memory cap, body size/codec limits, concurrency quotas và backpressure được xem xét.
- [ ] CORS origin/method/header allowlist đủ hẹp; Security/CSRF/cookies tách trách nhiệm.
- [ ] API prefix chỉ có một owner và không làm mất static/functional routes.
- [ ] Converter/formatters xử lý invalid input thành lỗi phù hợp.
- [ ] Static assets nằm ở đúng classpath, có cache policy, không lộ private uploads.
- [ ] View resolvers/Jackson serializers giữ behavior sau customization.
- [ ] Không đặt blocking I/O trên event-loop; có executor/scheduler policy.
- [ ] Error handler không gửi stacktrace/secrets cho client, xử lý committed response đúng.
- [ ] Multi-configurer conflicts được quản trị bằng ownership và integration tests.
- [ ] WebTestClient kiểm positive/negative routes, CORS, static resources, codecs.
- [ ] Nên có observability: HTTP latency/status, route, scheduler blocking, buffer memory và server resource usage.
- [ ] Nếu chọn full-control @EnableWebFlux, có regression suite rộng và tài liệu lý do.

## 17. Bài tập tự luyện

**Bài 1 — Ba lựa chọn:** Khi nào chỉ dùng Boot properties? Khi nào implement WebFluxConfigurer? Khi nào dùng @EnableWebFlux? Nêu trade-off của mỗi mức.

**Bài 2 — Startup behavior:** Một project có cả starter-web và starter-webflux. Vì sao WebFluxConfigurer không tạo ra reactive dispatcher? Cách sửa dependency?

**Bài 3 — CORS:** Viết addCorsMappings chỉ cho https://app.example.com gọi GET/POST /api/** với credentials. Tại sao allowedOrigins("*") không phù hợp?

**Bài 4 — Prefix:** Controller có @GetMapping("/books/{id}"), configurer addPathPrefix("/api", RestController). URL public là gì? Nếu controller đã /api/books thì sao?

**Bài 5 — Converter:** Tạo record BookId(long value) và converter String->BookId. Test GET /api/books/42 và invalid negative ID.

**Bài 6 — Codecs:** Dùng configureHttpMessageCodecs đặt 256KiB. Test một request body phải aggregate >256KiB và phân tích DataBufferLimitException, không mặc định status luôn 413.

**Bài 7 — Static resources:** Thêm /guide/** từ classpath:/guide-assets/ và cache 5 phút, đồng thời giữ /boot-health.txt mặc định từ Boot.

**Bài 8 — Security:** Dùng ServerHttpSecurity để bảo vệ /api/**, kết hợp CORS preflight, cookie CSRF và 401/403 handling.

**Bài 9 — @EnableWebFlux regression:** Thêm @EnableWebFlux vào demo, chạy tests, ghi lại những behavior Boot từng quản lý bị ảnh hưởng. Thiết kế lựa chọn bỏ annotation hoặc tái tạo mapping hợp lệ.

**Bài 10 — Functional routing:** Tạo một RouterFunction GET /fn/ping và kiểm configurePathMatching addPathPrefix không tự động áp cùng prefix cho functional route.

**Bài 11 — Blocking:** Có một legacy JDBC call trong controller Mono chain. So sánh configureBlockingExecution và Mono.fromCallable(...).subscribeOn(boundedElastic()).

**Bài 12 — Observability:** Khi API trả 500 do codecs config sai hoặc path rewrite sai, những metrics/logs nào giúp phân biệt config errors và business errors?

**Bài 13 — Custom codecs:** Tại sao registerDefaults(false) nguy hiểm? Khi muốn custom Jackson date format, nên bắt đầu từ đâu thay vì xóa toàn bộ readers/writers?

**Bài 14 — Multi-configurer:** Hai beans cùng set maxInMemorySize khác nhau. Thiết kế cơ chế ownership/centralized property/test để tránh behavior phụ thuộc ordering.

## 18. Ghi nhớ

- **WebFlux infrastructure** quản lý handler mappings/adapters/result handlers, codecs, converters, CORS, resource handling và exception processing.
- **@EnableWebFlux** import `DelegatingWebFluxConfiguration` để cung cấp cấu hình Framework; trong Boot chỉ dùng khi muốn kiểm soát toàn bộ WebFlux setup.
- **WebFluxConfigurer** là extension point để thêm từng cấu hình; với Boot thường implement dưới `@Configuration` **không @EnableWebFlux**.
- Boot starter và auto-config mang theo static resources, codecs, Jackson, error handling và tiện ích production; không bỏ chúng vì một annotation không cần thiết.
- `configureHttpMessageCodecs` chỉnh HTTP readers/writers; `defaultCodecs().maxInMemorySize` không phải toàn bộ request/server memory quota.
- `addCorsMappings` chỉ là policy browser cross-origin, **không thay authentication, authorization hoặc CSRF**.
- `configurePathMatching` cho annotated controllers, không tự gắn prefix mọi functional route/static resource.
- `addResourceHandlers` giúp custom static assets; security/caching strategy cần rõ.
- Reactor Netty, WebClient, Security, cancellation/backpressure và blocking execution có tầng cấu hình riêng.
- Chỉ nâng lên `@EnableWebFlux`/advanced config khi có lý do được kiểm chứng và regression tests.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): @EnableWebFlux, WebFluxConfigurer, formatters, codecs, resources, path matching, blocking execution và advanced mode.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): Boot WebFlux auto-config, Boot-specific properties, customizers, static resources, Security/error handling.
- [Spring Framework 6.2 — WebFlux Overview](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html).
- [Spring Framework 6.2 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): HandlerMapping/HandlerAdapter/HandlerResultHandler.
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html).
- [WebFluxConfigurer 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html).
- [ServerCodecConfigurer 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html).
- [Spring Boot 3.5 — Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html).
- [Spring Framework 6.2 — Path Matching](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html#webflux-config-path-matching).
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html).
