# Những thành phần Spring Boot tự cấu hình cho WebFlux

## 1. Mục tiêu bài học và phạm vi

Khi một ứng dụng Spring Boot sử dụng **Spring WebFlux**, lập trình viên thường chỉ cần khai báo `spring-boot-starter-webflux`, viết `@RestController` hoặc `RouterFunction` và chạy `@SpringBootApplication`. Spring Boot sẽ kiểm tra classpath, web application type, những bean đã có và các thuộc tính cấu hình, sau đó lắp ráp phần lớn hạ tầng phục vụ HTTP reactive.

Bài học làm rõ:

- **Spring Boot tự cấu hình thành phần nào**, thành phần nào vốn được **Spring Framework WebFlux** cung cấp, và thành phần nào chỉ xuất hiện nếu có dependency phù hợp.
- Mối liên hệ giữa embedded reactive web server, `HttpHandler`, `DispatcherHandler`, `HandlerMapping`, codec, `WebFilter`, static resources, template engine và error handling.
- Cách thêm cấu hình với `WebFluxConfigurer` mà vẫn giữ phần tự cấu hình của Boot.
- Những trường hợp dùng `@EnableWebFlux`, tự định nghĩa bean hoặc thêm Spring MVC làm auto-configuration thay đổi.
- Cách kiểm tra hạ tầng thực sự hoạt động và tránh blocking trên event loop.

**Phạm vi ví dụ:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**. Spring Boot 4.x có thể chuyển package, starter hoặc tên property; hãy đối chiếu reference/Javadoc của đúng phiên bản trước khi sao chép cấu hình phụ thuộc version.

## 2. Auto-configuration là gì?

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`, cho phép Boot nhập các cấu hình điều kiện (`@AutoConfiguration`) dựa vào dependency, cấu hình và bean đã được người dùng khai báo.

Các annotation điều kiện thường gặp:

- `@ConditionalOnClass`: chỉ kích hoạt khi thư viện/lớp cần thiết có mặt.
- `@ConditionalOnWebApplication(type = REACTIVE)`: chỉ áp dụng khi ApplicationContext thuộc loại web reactive.
- `@ConditionalOnMissingBean`: lùi lại nếu người dùng đã cung cấp một bean có kiểu phù hợp.
- `@ConditionalOnProperty`: tùy chọn bật/tắt một tính năng theo property.

Ví dụ trong Spring Boot 3.5, `WebFluxAutoConfiguration` yêu cầu ứng dụng thuộc loại `REACTIVE`, lớp `WebFluxConfigurer` có mặt, và không có `WebFluxConfigurationSupport` do ứng dụng đã tự định nghĩa. Nó hoạt động sau một số auto-configuration như reactive web server, codecs và validation.

Điều này không có nghĩa rằng một bean cứ có tên giống với lớp của Boot là được tạo trong mọi project. **Auto-configuration có điều kiện**, và Boot thường cố gắng không ghi đè customization mà ứng dụng đã chủ động cung cấp.

## 3. Điều kiện để Spring Boot chọn WebFlux

Dependency Maven phổ biến:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Starter đưa Spring WebFlux, Project Reactor và runtime web server mặc định thường là **Reactor Netty** vào classpath.

Những tình huống chính:

| Classpath / cấu hình | Loại ứng dụng thường được chọn | Tác động |
|---|---|---|
| Có `spring-boot-starter-webflux`, không có MVC starter | `REACTIVE` | WebFlux server và hạ tầng reactive được cấu hình |
| Có `spring-boot-starter-web` | `SERVLET` | Thường Spring MVC |
| Có **cả** `spring-boot-starter-web` và `spring-boot-starter-webflux` | `SERVLET` theo mặc định | Boot ưu tiên MVC; WebClient vẫn dùng được |
| Không có hạ tầng web cần thiết | `NONE` | Không khởi động HTTP web server như ứng dụng web |
| Cấu hình rõ `spring.main.web-application-type=reactive` | `REACTIVE`, nếu dependency hỗ trợ | Buộc lựa chọn reactive web application type |

Ví dụ chọn tường minh:

```properties
spring.main.web-application-type=reactive
```

Đây không phải cách thay thế đầy đủ cho việc quản lý dependency. Dự án chủ động chọn WebFlux nên loại bỏ MVC starter không cần thiết để tránh các bean/auto-configuration không mong muốn.

**Phân biệt:** Chỉ dùng `WebClient` trong một ứng dụng MVC **không biến ứng dụng đó thành WebFlux server**. Việc có `spring-webflux` trên classpath và việc Spring Boot chạy theo web application type `REACTIVE` là hai điều khác nhau.

## 4. Toàn cảnh luồng HTTP reactive

Sơ đồ khái quát khi dùng Reactor Netty:

```text
HTTP client
    |
    v
Reactor Netty (embedded reactive web server)
    |
    v
HttpHandler / WebHttpHandlerBuilder
    |-- WebFilter chain
    |-- WebExceptionHandler chain
    |-- WebSessionManager / locale / codec-related context
    |
    v
DispatcherHandler (front controller WebFlux)
    |
    +--> HandlerMapping
    |      |-- annotated @RequestMapping/@GetMapping
    |      |-- RouterFunction functional endpoints
    |      |-- resource handler mappings
    |
    v
HandlerAdapter -> Controller/HandlerFunction
    |
    v
HandlerResultHandler
    |-- ResponseBodyResultHandler
    |-- ServerResponseResultHandler
    |-- ViewResolutionResultHandler
    |
    v
HttpMessageWriter / View render
    |
    v
HTTP response
```

Một request có thể được giải mã bởi `HttpMessageReader`, được controller hoặc functional handler xử lý, sau đó được ghi ra response qua `HttpMessageWriter`. Với response HTML, `ViewResolutionResultHandler` và template engine có thể tham gia.

**`DispatcherHandler` là front controller của Spring WebFlux**; còn `DispatcherServlet` thuộc Spring MVC. WebFlux dùng `ServerWebExchange` thay cho việc yêu cầu ứng dụng thao tác trực tiếp với `HttpServletRequest`/`HttpServletResponse` ở API WebFlux tiêu chuẩn.

## 5. Nhóm thành phần: Boot tự cấu hình và Framework cung cấp

| Nhóm | Thành phần điển hình | Nguồn trách nhiệm | Điều kiện/chú ý |
|---|---|---|---|
| ApplicationContext | Reactive web application context | Spring Boot tích hợp | Ứng dụng loại `REACTIVE` |
| Embedded web server | `ReactiveWebServerFactory`, mặc định thường `NettyReactiveWebServerFactory` | Spring Boot | Phụ thuộc runtime server trên classpath |
| HTTP handler adaptation | `HttpHandler`, `WebHttpHandlerBuilder` | Framework cung cấp; Boot lắp ráp/tùy chỉnh | Tích hợp server với WebFlux |
| Front controller | `DispatcherHandler` | Spring WebFlux infrastructure | Được tạo qua WebFlux configuration |
| Request routing | `RequestMappingHandlerMapping`, `RouterFunctionMapping`, resource mapping | Spring WebFlux infrastructure | Annotated và functional styles |
| Handler execution | `RequestMappingHandlerAdapter`, `HandlerFunctionAdapter` | Spring WebFlux infrastructure | Gọi handler phù hợp |
| Result writing | `ResponseBodyResultHandler`, `ServerResponseResultHandler`, `ViewResolutionResultHandler` | Spring WebFlux infrastructure | Chọn cách ghi response |
| Data conversion | `HttpMessageReader`, `HttpMessageWriter`, `ServerCodecConfigurer` | Framework mặc định; Boot bổ sung codecs/Jackson customization | Phụ thuộc thư viện JSON/XML trên classpath |
| Static resources | `ResourceWebHandler` và resource mapping | WebFlux + Boot property/configuration | Có `/static`, `/public`, WebJars nếu hiện diện |
| Template engine | Thymeleaf, FreeMarker, Mustache view integrations | Boot hỗ trợ auto-config nếu có starter | Không phải project REST nào cũng có |
| Error response | `WebExceptionHandler`, `ErrorWebExceptionHandler`, error attributes | Boot cung cấp xử lý lỗi mặc định trên nền Framework | Có thể tùy chỉnh |
| Web filters | `WebFilter`, `WebFilterChain` | Framework; Boot tự nhận bean và có thể thêm filter | Security filter chỉ có khi dependency/config phù hợp |
| HTTP client | `WebClient.Builder` prototype, connector customization | Spring Boot auto-configuration phía client | Có WebFlux trên classpath; không chứng minh server reactive |
| Security, Actuator | Reactive security chain, metrics, health, observations | Auto-config có điều kiện từ starter liên quan | Không mặc nhiên có nếu không thêm dependency |

Bảng phân biệt **trách nhiệm tạo cấu hình** với **nguồn gốc API**. Không phải tất cả các bean liệt kê đều được trực tiếp khai báo trong `WebFluxAutoConfiguration`; nhiều bean do `WebFluxConfigurationSupport` của Spring Framework khởi tạo, còn Boot cung cấp điều kiện, property binding và customization.

## 6. Embedded reactive server: Reactor Netty và các lựa chọn khác

`spring-boot-starter-webflux` thường chọn Reactor Netty làm HTTP server mặc định. Boot dùng `ReactiveWebServerFactoryAutoConfiguration` để thiết lập factory tương ứng và cung cấp các tùy chọn server phổ biến.

Cấu hình qua `application.properties`:

```properties
server.port=8080
server.address=127.0.0.1
server.compression.enabled=true
```

Khi bật `server.address=127.0.0.1`, ứng dụng chỉ lắng nghe loopback; với container hoặc môi trường triển khai cần truy cập từ bên ngoài, không nên sao chép cấu hình này mà thiếu điều chỉnh.

Các tính năng web server có thể gồm:

- Cổng và địa chỉ bind: `server.port`, `server.address`.
- TLS/HTTPS với `server.ssl.*` khi kết nối TLS kết thúc tại ứng dụng.
- Compression: `server.compression.*`.
- HTTP/2: `server.http2.enabled`, với điều kiện transport/server hỗ trợ.
- Server-specific settings, ví dụ `server.netty.*` khi dùng Reactor Netty.

Spring Boot cũng hỗ trợ các embedded reactive server khác như Tomcat hoặc Jetty trong cấu hình phù hợp, bằng cách **thay dependency server**, không đơn thuần đổi một property.

Nếu cần can thiệp sâu:

- `WebServerFactoryCustomizer<...>` cho factory phù hợp.
- `NettyReactiveWebServerFactory` và cơ chế customization Netty khi runtime hiện hành hỗ trợ.
- `ReactorResourceFactory` cho HTTP resources như event loop và connection pool; các resource có thể được chia sẻ giữa server và `WebClient` dùng Reactor Netty do Boot cấu hình.

Customizer của factory được gọi **trước lúc server được tạo**, không phải API thay đổi cổng HTTP đang lắng nghe ở runtime. Ưu tiên property chuẩn trước khi can thiệp API cấp thấp.

## 7. DispatcherHandler và các thành phần định tuyến

Hạ tầng WebFlux được Spring Framework cung cấp thông qua `WebFluxConfigurationSupport` / `DelegatingWebFluxConfiguration`, và được Spring Boot kích hoạt/tinh chỉnh khi auto-configuration đủ điều kiện.

Các thành phần quan trọng:

- **`DispatcherHandler`**: nhận `ServerWebExchange`, phối hợp handler mapping, adapter và result handler.
- **`RequestMappingHandlerMapping`**: chọn `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`...
- **`RequestMappingHandlerAdapter`**: gọi annotated controller methods.
- **`RouterFunctionMapping`**: tìm handler cho functional routes `RouterFunction`.
- **`HandlerFunctionAdapter`**: thực thi một `HandlerFunction`.
- **`ResponseBodyResultHandler`**: chọn writer cho `@ResponseBody` hoặc `@RestController`.
- **`ResponseEntityResultHandler`**: xử lý kết quả dạng `ResponseEntity`.
- **`ServerResponseResultHandler`**: viết `ServerResponse` cho functional endpoint.
- **`ViewResolutionResultHandler`**: điều phối view khi render giao diện phía server.
- **`ResourceWebHandler`**: phục vụ static content.

Một ứng dụng có thể dùng **cả annotated controllers lẫn functional endpoints**. Cần quản lý mapping và thứ tự route rõ ràng để tránh xung đột, nhưng không phải cài đặt tay các bean hạ tầng nêu trên chỉ để tạo API cơ bản.

## 8. HTTP codecs: HttpMessageReader, HttpMessageWriter và Jackson

WebFlux không dùng `HttpMessageConverter` của Spring MVC để xử lý reactive body theo cách thông thường. Các interface chính là:

- `HttpMessageReader<T>`: đọc/giải mã request body.
- `HttpMessageWriter<T>`: mã hóa và ghi response body.
- `CodecConfigurer` / `ServerCodecConfigurer`: tổ chức và tùy chỉnh codec.
- Các codec JSON của Jackson, codec chuỗi, bytes và những kiểu khác, được lựa chọn theo dependency.

Spring Boot bổ sung codec auto-configuration, tự kết hợp thư viện có trên classpath và `CodecCustomizer`. Một số thiết lập Jackson từ `spring.jackson.*` được áp dụng cho JSON codec.

**Property cho Spring Boot 3.5:**

```properties
spring.http.codecs.max-in-memory-size=512KB
```

Property này điều chỉnh giới hạn bộ nhớ khi codec cần gom dữ liệu đầu vào và áp dụng cho **WebFlux server và các WebClient được Boot tự cấu hình**. Nếu không thiết lập, mỗi codec dùng giới hạn mặc định riêng, nhiều codec thường khoảng 256KB. Nó **không phải giới hạn tổng dung lượng upload hay số byte HTTP request trên dây**.

Nếu decoder cố gom vượt giới hạn trong một trường hợp được áp dụng, có thể gặp lỗi như `DataBufferLimitException`. Đừng nâng ngưỡng tới hàng GB thay vì xem xét streaming, phân trang, file upload hoặc lưu dữ liệu ngoài bộ nhớ.

Ví dụ dùng `WebFluxConfigurer` để chỉnh codec về mặt nguyên lý:

```java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
```

Đoạn trên là **method minh họa bên trong class implements `WebFluxConfigurer`**, cần import `org.springframework.http.codec.ServerCodecConfigurer`. Với nhu cầu đơn giản, dùng property `spring.http.codecs.max-in-memory-size` để tránh lặp cấu hình.

**Không gọi `registerDefaults(false)` tùy tiện**. Tắt toàn bộ default codecs có thể khiến JSON, text hoặc một loại body đang hoạt động mất khả năng encode/decode; chỉ dùng khi cần tự quản lý codec theo kiến trúc đã kiểm chứng.

## 9. Static resources và WebJars được tự cấu hình

Spring Boot hỗ trợ WebFlux phục vụ tài nguyên tĩnh từ các thư mục classpath mặc định, thường là:

```text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
```

Ví dụ đặt file `src/main/resources/static/hello.txt`:

```text
Hello from static
```

Sau khi ứng dụng chạy, có thể kiểm tra:

```bash
curl -i http://localhost:8080/hello.txt
```

Nếu tài nguyên được đóng gói và mapping mặc định không bị đổi, body response chứa `Hello from static`.

Spring WebFlux dùng `ResourceWebHandler`; Boot bổ sung cấu hình path/resource locations. Các property:

```properties
# Đổi prefix URL từ /** sang /assets/**
spring.webflux.static-path-pattern=/assets/**
```

Khi đó URL tương ứng sẽ là `/assets/hello.txt` thay vì `/hello.txt`, trong điều kiện không có route khác chiếm path và file tồn tại.

```properties
# Thay thế danh sách vị trí static mặc định
spring.web.resources.static-locations=classpath:/custom-static/
```

Thuộc tính `static-locations` **thay thế** vị trí mặc định, không tự cộng dồn. Nếu dùng đường dẫn mới cần đặt resource đúng nơi và kiểm tra mapping của welcome page.

Spring Boot còn hỗ trợ WebJars theo đường dẫn cấu hình phù hợp; điều đó không đồng nghĩa mọi thư viện frontend tự động xuất hiện trong classpath. Nếu không có WebJar dependency thì không có resource đó để phục vụ.

Đây là lý do không nên thêm `@EnableWebFlux` chỉ để đổi static path: việc làm đó có thể khiến auto-config phần static resource của Boot ngừng được áp dụng.

## 10. HTML template engines và view resolution

WebFlux không chỉ phục vụ JSON API; nó cũng có thể render HTML qua `ViewResolver` reactive.

Spring Boot hỗ trợ auto-configuration cho các template engine nếu dependency tương ứng được thêm vào:

- Thymeleaf.
- FreeMarker.
- Mustache.

Template thường được tìm trong:

```text
src/main/resources/templates/
```

Ví dụ controller WebFlux trả tên view:

```java
@Controller
public class WelcomePageController {

    @GetMapping("/welcome")
    public String welcome(Model model) {
        model.addAttribute("name", "Lan");
        return "welcome";
    }
}
```

Với template engine reactive tương thích và file `templates/welcome.html`, hệ thống render HTML theo view name. Đoạn Java chỉ minh họa logic controller, cần các import `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.GetMapping`, `org.springframework.ui.Model`.

**Không nhầm `@RestController` với `@Controller`.** `@RestController` trả response body thay vì view name thông thường. `@EnableWebFlux` cũng không tự cài Thymeleaf hoặc tạo template HTML; cần đúng dependency và resource.

Một số tính năng của FreeMarker trong WebFlux khác Servlet stack. Khi sử dụng HTML templates, hãy xem hỗ trợ reactive của engine và phiên bản đang dùng.

## 11. Error handling: WebExceptionHandler, ErrorAttributes và Problem Details

Spring Boot cung cấp error handling mặc định cho WebFlux dựa trên hệ thống `WebExceptionHandler`. Các thành phần có thể bao gồm:

- `ErrorAttributes`: tập hợp thông tin lỗi để hiển thị.
- `ErrorWebExceptionHandler`: xử lý lỗi ở cấp reactive web exchange.
- `DefaultErrorWebExceptionHandler`: triển khai mặc định của Boot trong những cấu hình phù hợp.
- `AbstractErrorWebExceptionHandler`: lớp nền để xây dựng cách xử lý lỗi riêng.
- `@RestControllerAdvice` và `@ExceptionHandler`: xử lý lỗi gần controller, cho những lỗi nằm trong phạm vi handler được hỗ trợ.

Khi một request không được mapping hoặc xảy ra exception, Boot có thể tạo JSON response cho API client hoặc HTML error page cho browser tùy request và cách thương lượng nội dung. Body lỗi cụ thể không ổn định giữa mọi bản Boot; đừng viết application test chỉ dựa vào chuỗi thông điệp lỗi mặc định.

Spring Boot 3.5 có hỗ trợ bật RFC 9457 Problem Details:

```properties
spring.webflux.problemdetails.enabled=true
```

Khi cơ chế này được áp dụng, lỗi phù hợp có thể trả `application/problem+json` với các field `type`, `title`, `status`, `detail`, `instance`. Không nên tiết lộ stacktrace, SQL query, token hoặc bí mật vận hành trong thông tin lỗi cho client.

Muốn tùy chỉnh thông tin lỗi mặc định, cân nhắc bean `ErrorAttributes`. Nếu cần điều khiển hoàn toàn error flow, mới viết `ErrorWebExceptionHandler` phù hợp. Đăng ký nhiều handler toàn cục sai thứ tự có thể làm mất response format chuẩn hoặc khiến lỗi bị nuốt mà không được giám sát.

## 12. WebFilter và chuỗi HttpHandler

Spring WebFlux cung cấp `WebFilter` để can thiệp request/response ở mức reactive exchange. Các bean `WebFilter` do ứng dụng khai báo được Spring Boot tìm và đưa vào HTTP handler chain thích hợp.

Ví dụ filter nhẹ:

```java
package com.example.webfluxdemo;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
@Order(10)
public class TraceHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {
        exchange.getResponse().getHeaders()
                .add("X-Demo-Filter", "webflux");
        return chain.filter(exchange);
    }
}
```

Lớp này có thể dùng trong project WebFlux đang chạy và thêm header `X-Demo-Filter: webflux` vào response. Trong production, việc gắn header cần xét thêm bảo mật, cơ chế phản hồi lỗi và khả năng response đã commit.

- `@Order` / `Ordered` giúp điều khiển thứ tự filter.
- Filter nên trả một `Mono<Void>` hợp lệ, không gọi `block()` trên event loop.
- Không dùng `javax.servlet.Filter` hoặc `jakarta.servlet.Filter` để thay thế `WebFilter` trong API WebFlux tiêu chuẩn.

**`WebHttpHandlerBuilderCustomizer`** là hook của Boot để tùy chỉnh cách dựng `WebHttpHandlerBuilder`/ `HttpHandler`, khi cần điều chỉnh sâu hơn cấu hình WebFlux mặc định. Đây không phải lựa chọn đầu tiên cho logic request phổ thông; ưu tiên `WebFilter` hoặc `WebFluxConfigurer` khi đủ dùng.

## 13. WebClient.Builder: cấu hình phía client là nhóm riêng

Với `spring-webflux` trên classpath, Spring Boot có thể auto-configure một bean `WebClient.Builder` được chuẩn bị sẵn và dùng làm khuôn để tạo `WebClient`.

Ví dụ:

```java
package com.example.webfluxdemo;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class UpstreamService {

    private final WebClient webClient;

    public UpstreamService(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://api.example.org")
                .build();
    }

    public Mono<String> fetch(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

Ví dụ chỉ minh họa kỹ thuật, `https://api.example.org` là URL giả định; cần dùng một upstream thực tế trước khi gọi. Không có output cố định được cam kết.

Cần phân biệt:

- `WebClient.Builder` phục vụ HTTP request **outbound**.
- `ReactiveWebServerFactory` và `DispatcherHandler` phục vụ HTTP request **inbound**.
- Spring MVC có thể sử dụng `WebClient.Builder` nếu WebFlux nằm trên classpath; điều đó **không** khiến app tự đổi sang Reactive.
- Dùng `WebClient.create()` trực tiếp có thể bỏ qua các `WebClientCustomizer` và tùy chỉnh do Boot áp dụng cho builder.
- Với Reactor Netty/Jetty, resource factory có thể ảnh hưởng cả server và các client do Boot cấu hình, tùy công nghệ và cách dựng client.

Không gọi `.block()` trong handler reactive của WebFlux chỉ để lấy kết quả đồng bộ từ `WebClient`; hãy trả publisher từ pipeline và dùng toán tử reactive.

## 14. Auto-configuration bổ sung chỉ khi có dependency

**Spring Security:** nếu thêm `spring-boot-starter-security` và reactive security modules phù hợp, Spring Boot/Spring Security sẽ tạo hoặc tích hợp security filter chain cho ứng dụng reactive. Trong WebFlux, các interface thường gặp là `SecurityWebFilterChain` và `WebFilterChainProxy`, không phải `SecurityFilterChain` Servlet.

**Actuator:** nếu thêm `spring-boot-starter-actuator`, Boot có thể tự cấu hình health, metrics, HTTP observations và các endpoint quản trị tương ứng, tùy actuator version, property và dependency. Không nên suy ra rằng tất cả management endpoints đều được public qua HTTP.

**Validation:** nếu có Jakarta Bean Validation implementation (ví dụ starter validation) và cấu hình thích hợp, Spring có thể kết hợp validator cho reactive controller/model binding. Chỉ có WebFlux starter không đảm bảo mọi validation annotation sẽ hoạt động như mong đợi nếu thiếu provider.

**WebSocket:** WebFlux và server/runtime có thể hỗ trợ WebSocket khi các module/tính năng cần thiết được khai báo, nhưng không phải chỉ thêm starter là có một WebSocket endpoint; cần handler mapping và ứng dụng cụ thể.

**Data access:** R2DBC, Spring Data Reactive, Mongo reactive repositories và các tài nguyên database là các auto-configuration **khác** khi dependency tương ứng có mặt. Chúng không phải thành phần do `WebFluxAutoConfiguration` tự tạo chỉ vì server chọn REACTIVE.

Nguyên tắc: **"Spring Boot hỗ trợ auto-configure" không đồng nghĩa "mọi thứ có sẵn trong mọi WebFlux app"**. Luôn kiểm tra starter, auto-configuration condition report và bean được khởi tạo thực tế.

## 15. Tùy chỉnh nhưng vẫn giữ tự cấu hình bằng WebFluxConfigurer

Spring Boot khuyến nghị tạo `@Configuration` **implements `WebFluxConfigurer`**, không thêm `@EnableWebFlux`, để giữ các tính năng Boot đang tự cấu hình.

Ví dụ cấu hình CORS cho endpoint API từ frontend cụ thể:

File `src/main/java/com/example/webfluxdemo/WebFluxCorsConfiguration.java`:

```java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFluxCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example.org")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization");
    }
}
```

Đoạn này là một class đầy đủ; `https://frontend.example.org` là origin ví dụ và phải thay bằng origin đáng tin cậy của hệ thống. Nếu có Spring Security, cần kiểm tra cấu hình CORS phối hợp với security chain. Không sao chép `.allowedOrigins("*")` một cách tùy tiện, đặc biệt khi có credentials.

`WebFluxConfigurer` có thể dùng để bổ sung:

- `addCorsMappings`: CORS policy theo URL.
- `addFormatters`: conversion/formatting.
- `addResourceHandlers`: static resources tùy biến.
- `configureHttpMessageCodecs`: codec settings/custom codecs.
- `configureViewResolvers`: view resolution.
- `configurePathMatching`: một số quy tắc xử lý đường dẫn.
- Các callback khác có ở phiên bản Spring Framework tương ứng.

Khi chỉ cần đổi property như cổng, static path hoặc giới hạn codec, ưu tiên cấu hình `.properties`/`.yaml`; tránh Java config không cần thiết.

### Trường hợp @EnableWebFlux

`@EnableWebFlux` kích hoạt cấu hình WebFlux do Spring Framework cung cấp nhưng đồng thời thể hiện mong muốn **tự nắm quyền kiểm soát cấu hình WebFlux**. Nó có thể khiến `WebFluxAutoConfiguration` của Boot không còn được áp dụng vì một `WebFluxConfigurationSupport` đã tồn tại.

Điều đó không có nghĩa là ứng dụng lập tức ngừng hoạt động hoặc mọi hạ tầng biến mất; Spring Framework vẫn cấu hình các thành phần WebFlux cơ bản. Nhưng **các tùy chỉnh mà Boot bổ sung** (static resources, codecs, property bindings, welcome page và những hook tương ứng) có thể thay đổi hoặc mất hiệu lực nếu bạn không thiết lập lại.

Chỉ dùng `@EnableWebFlux` khi muốn kiểm soát toàn bộ cấu hình và chấp nhận trách nhiệm tạo/tùy chỉnh lại những phần cần dùng. Đừng thêm annotation này chỉ để CORS hoặc đổi formatter.

## 16. Ví dụ chạy được: annotated endpoint + functional endpoint

Giả sử project Maven Spring Boot 3.5 và Java 17 đã có parent hoặc dependency management của Boot. Thêm `spring-boot-starter-webflux`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Không thêm `spring-boot-starter-web` vào ví dụ này.

Cấu trúc file:

```text
src/main/java/com/example/webfluxdemo/
    WebFluxDemoApplication.java
    HelloController.java
    FunctionalRoutes.java
src/main/resources/
    application.properties
    static/hello.txt
```

### 16.1. Lớp khởi động

File `src/main/java/com/example/webfluxdemo/WebFluxDemoApplication.java`:

```java
package com.example.webfluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxDemoApplication.class, args);
    }
}
```

### 16.2. Annotated controller

File `src/main/java/com/example/webfluxdemo/HelloController.java`:

```java
package com.example.webfluxdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Mono<Greeting> hello() {
        return Mono.just(new Greeting("Hello WebFlux"));
    }

    public record Greeting(String message) {
    }
}
```

Jackson auto-configuration và reactive JSON codecs giúp serialize record thành JSON trong cấu hình starter thông thường.

### 16.3. Functional routing

File `src/main/java/com/example/webfluxdemo/FunctionalRoutes.java`:

```java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> pingRoute() {
        return route(GET("/functional/ping"), request ->
                ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("pong"));
    }
}
```

Boot/WebFlux phát hiện bean `RouterFunction` và dùng functional routing infrastructure; không cần tự tạo `DispatcherHandler` hay `HandlerFunctionAdapter`.

### 16.4. Cấu hình và file tĩnh

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.http.codecs.max-in-memory-size=512KB
spring.webflux.problemdetails.enabled=true
```

File `src/main/resources/static/hello.txt`:

```text
Hello static WebFlux
```

Trong project Maven có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Thử bằng `curl`:

```bash
curl -s http://localhost:8080/api/hello
curl -s http://localhost:8080/functional/ping
curl -s http://localhost:8080/hello.txt
```

Body mong đợi của ba lệnh theo thứ tự:

```text
{"message":"Hello WebFlux"}
pong
Hello static WebFlux
```

Lưu ý mỗi lệnh `curl -s` có thể in body mà không thêm newline, nên khi chạy ba lệnh liên tiếp trong terminal có thể thấy các chuỗi nối nhau. Nội dung trên trình bày **từng body trên từng dòng cho dễ đọc**, không phải transcript byte-for-byte của terminal.

Ví dụ này chứng minh ba cơ chế cùng hoạt động: annotated WebFlux handler → JSON codec, functional routing → String writer, và Boot static resource mapping. Cần project Boot thực tế để chạy; các file Java không thể `javac` độc lập chỉ với JDK vì còn dependency Spring/Reactor/Jackson.

## 17. Kiểm thử WebFlux bằng WebTestClient

Spring Boot hỗ trợ `@WebFluxTest` để tạo một test slice tập trung vào WebFlux controllers, cũng như `WebTestClient` để gửi request giả lập hoặc tới server thật.

Thêm test dependency trong project Maven đã có dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ test slice cho annotated controller, file `src/test/java/com/example/webfluxdemo/HelloControllerTest.java`:

```java
package com.example.webfluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = HelloController.class)
class HelloControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void returnsGreetingAsJson() {
        webTestClient.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        org.springframework.http.MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello WebFlux");
    }
}
```

`@WebFluxTest` tạo môi trường WebFlux test giới hạn, không auto-scan mọi `@Service` hoặc repository của ứng dụng. Nếu controller phụ thuộc service, dùng mock/test config phù hợp. Test slice này không chứng minh toàn bộ embedded server đã lắng nghe thật.

Để test tích hợp cả server và routing, có thể dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` và WebTestClient được thiết lập cho embedded server; cần cấu hình phù hợp với phiên bản Boot. Chọn test slice để kiểm tra mapping/codec đơn giản, chọn integration test cho TLS/server/resource behavior thực tế.

Chạy test:

```bash
./mvnw test
```

Không có stdout nghiệp vụ cố định cho `mvnw test`; output Maven phụ thuộc dependency cache, test report và cấu hình dự án.

## 18. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân phổ biến | Hướng điều tra |
|---|---|---|
| Có WebFlux starter nhưng app chạy MVC | Cả `starter-web` và `starter-webflux` trên classpath | Kiểm tra dependency tree và `WebApplicationType` |
| Có `WebClient.Builder` nên tưởng app là WebFlux server | Client auto-config độc lập với server stack | Xác nhận `ReactiveWebServerApplicationContext` và embedded server |
| `@EnableWebFlux` khiến static file/codec config không như trước | Boot WebFlux auto-config bị thay thế một phần | Bỏ `@EnableWebFlux` nếu chỉ mở rộng; dùng `WebFluxConfigurer` |
| `/hello.txt` trả 404 | File sai thư mục, `static-locations` thay thế defaults, static path pattern thay đổi | Kiểm tra runtime classpath và URL |
| JSON 406/415 hoặc không serialize được | Converter/codec, `Accept`, `Content-Type`, phụ thuộc JSON | Kiểm tra reader/writer, media types và mapping |
| `DataBufferLimitException` | Decoder phải gom nhiều dữ liệu hơn giới hạn in-memory | Giảm dữ liệu, streaming hoặc chỉnh `spring.http.codecs.max-in-memory-size` có kiểm soát |
| API chậm, event loop bị nghẽn | Gọi JDBC, `Thread.sleep`, `.block()` trong handler | Dùng I/O non-blocking; isolate blocking theo scheduler thích hợp khi bắt buộc |
| Bộ lọc Servlet không chạy như mong đợi | Dùng `Filter` thay vì `WebFilter` trong API reactive | Chuyển sang `WebFilter` phù hợp |
| Error response thiếu chi tiết mong muốn | Boot default error handler, Problem Details hoặc `@ExceptionHandler` | Kiểm tra error configuration; không log bí mật |
| Mất auth hoặc actuator endpoint không xuất hiện | Thiếu starter security/actuator, property hoặc bean khác | Xem dependency, `SecurityWebFilterChain`, endpoint exposure |
| Đổi server nhưng customizer không áp dụng | Factory generic gắn cứng vào Reactor Netty/Tomcat | Chọn factory đúng loại hoặc API chung |
| `@WebFluxTest` thiếu bean dịch vụ | Test slice chỉ load một phần context | Cung cấp mock hoặc dùng `@SpringBootTest` |

Điểm dễ nhầm nhất là gọi mọi thứ là **Boot tự tạo**. Nhiều bean cốt lõi thực sự do Spring Framework WebFlux định nghĩa; Boot quyết định khi nào dùng chúng, thêm cấu hình tiện lợi và kết nối chúng với hạ tầng runtime.

## 19. Xem các auto-configuration thực sự được áp dụng

Trong lúc debug, có thể khởi động project với debug flag:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc thêm property tạm thời:

```properties
debug=true
```

Spring Boot in **Condition Evaluation Report** thể hiện các auto-configurations matched hoặc did not match và lý do liên quan. Hãy tìm tên như:

- `WebFluxAutoConfiguration`.
- `ReactiveWebServerFactoryAutoConfiguration`.
- `CodecsAutoConfiguration`.
- `WebClientAutoConfiguration`.
- `ErrorWebFluxAutoConfiguration`.
- Auto-configuration của Spring Security, Actuator nếu dependency có mặt.

Tên class và cấu trúc package có thể thay đổi theo phiên bản Boot; không xây dashboard kiểm tra chỉ phụ thuộc string classname cố định qua các major version.

Nếu Actuator được bật và security/exposure cho phép, endpoint `/actuator/conditions` có thể giúp xem báo cáo tương ứng. Đây là endpoint chẩn đoán có thể tiết lộ chi tiết cấu hình; **không mở công khai trên Internet**.

Lệnh kiểm tra dependency:

```bash
./mvnw dependency:tree
```

Với project Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Ngoài ra có thể:

1. Xem startup log để biết embedded server là Netty hay loại khác.
2. Kiểm tra class `ApplicationContext` có phải reactive context không.
3. Đặt breakpoint tại controller/functional handler/filter.
4. Kiểm thử endpoint annotated, functional, static resource và error response.
5. Dùng thread dump/metrics để phát hiện blocking operation trên event loop.
6. Xem property source hiệu lực khi một giá trị cấu hình không được áp dụng.
7. So sánh auto-config conditions trước và sau khi thêm starter hoặc `@EnableWebFlux`.

## 20. Checklist khi tùy chỉnh một ứng dụng WebFlux

- [ ] Dependency thể hiện chủ đích chạy WebFlux, không vô tình kéo cả MVC starter vào.
- [ ] App được xác định là `WebApplicationType.REACTIVE`.
- [ ] Nhận biết embedded server đang sử dụng và property `server.*` có hiệu lực.
- [ ] Phân biệt `DispatcherHandler` WebFlux với `DispatcherServlet` MVC.
- [ ] Hiểu annotated controllers, functional routing, codec và static resources.
- [ ] Tùy chỉnh nhẹ bằng `WebFluxConfigurer` **không có** `@EnableWebFlux`.
- [ ] Chỉ dùng `@EnableWebFlux` khi muốn kiểm soát cấu hình WebFlux sâu và chấp nhận tự quản lý những phần Boot đã hỗ trợ.
- [ ] Biết `spring.http.codecs.max-in-memory-size` khác HTTP request body size.
- [ ] Dùng `WebFilter`, không nhầm với Servlet filter.
- [ ] Phân biệt `WebClient.Builder` phía outbound với embedded web server phía inbound.
- [ ] Kiểm tra các tính năng điều kiện như Security, Actuator, Validation và template engines.
- [ ] Có test cho controller, functional routes, error handling và static resource nếu tính năng sử dụng.
- [ ] Đọc Condition Evaluation Report thay vì tự đoán rằng auto-configuration đã chạy.
- [ ] Không blocking event loop nếu muốn tận dụng lợi thế I/O non-blocking.

## 21. Kết luận

Spring Boot tự cấu hình môi trường WebFlux bằng cách lựa chọn reactive web application context, embedded reactive HTTP server, cấu hình codecs, error handling, static resource mapping, template engines khi dependency có mặt và những cơ chế tích hợp bổ sung. Hạ tầng `DispatcherHandler`, `HandlerMapping`, `HandlerAdapter`, `HandlerResultHandler`, `ServerCodecConfigurer` phần lớn đến từ **Spring Framework WebFlux**, còn Boot kích hoạt và tinh chỉnh theo điều kiện.

Nguyên tắc bảo trì quan trọng nhất: **thêm `WebFluxConfigurer` để mở rộng, không thêm `@EnableWebFlux` nếu vẫn muốn giữ Boot WebFlux auto-configuration**. Với từng tính năng, xác định rõ đó là cấu hình mặc định của Boot, cấu trúc nền tảng của Framework, hay một tính năng chỉ có khi thêm starter/bean.

## 22. Tài liệu tham khảo

- Spring Boot 3.5 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — WebFluxAutoConfiguration Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html
- Spring Boot 3.5 — Testing WebFlux: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot — Calling REST Services / WebClient: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Framework — WebFlux configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework — WebFlux.fn functional endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Project Reactor — Reference Guide: https://projectreactor.io/docs/core/release/reference/
