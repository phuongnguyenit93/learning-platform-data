# WebFluxConfigurer: bổ sung cấu hình và giữ lại mặc định Spring Boot

## 1. Mục tiêu của bài

Trong ứng dụng Spring Boot sử dụng **Spring WebFlux**, nhiều thành phần xử lý HTTP đã được Boot cấu hình tự động: đăng ký annotated controllers và functional routes, các HTTP message readers/writers, static resources, WebJars, trang welcome và tích hợp những thư viện có trên classpath. Phần lớn dự án cần **bổ sung** một vài quy tắc như CORS, formatter, đường dẫn tài nguyên tĩnh hoặc giới hạn bộ nhớ của codec, chứ không muốn tự dựng lại toàn bộ WebFlux infrastructure.

**WebFluxConfigurer** là extension point dành cho tình huống đó. Quy tắc quan trọng nhất trong Spring Boot:

> Tạo một bean **@Configuration implements WebFluxConfigurer**, chỉ override các phương thức thực sự cần thiết, **không thêm @EnableWebFlux** nếu muốn giữ các tính năng WebFlux auto-configuration của Spring Boot.

Đây là hướng dẫn được nêu trực tiếp trong tài liệu Spring Boot Reactive Web Applications. @EnableWebFlux dành cho trường hợp chủ động nắm toàn quyền cấu hình Spring WebFlux; dùng annotation này chỉ để thêm một CORS mapping hoặc static handler là một thay đổi kiến trúc không cần thiết.

Bài sử dụng **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+** làm mốc cho package và API. Với Spring Boot 4.x hoặc phiên bản khác, cần so lại tài liệu, đặc biệt nếu cấu trúc module/package đã thay đổi.

## 2. Bức tranh tổng quát: Boot auto-configuration và WebFluxConfigurer

Luồng điển hình:

~~~text
spring-boot-starter-webflux trên classpath
                 |
                 v
Spring Boot xác định WebApplicationType.REACTIVE
                 |
                 v
WebFluxAutoConfiguration được đánh giá theo điều kiện
                 |
                 +--> Tạo / tinh chỉnh WebFlux infrastructure
                 |    (HandlerMapping, HandlerAdapter, codecs...)
                 |
                 +--> Static resource mapping, WebJars,
                 |    welcome page và Boot-specific conventions
                 |
                 +--> Nhận các bean WebFluxConfigurer do app cung cấp
                                 |
                                 v
                 addCorsMappings, addFormatters,
                 addResourceHandlers, configureHttpMessageCodecs...
                                 |
                                 v
                 HTTP server sử dụng cấu hình đã tổng hợp
~~~

WebFluxConfigurer là một **interface có các default methods**. Bạn chỉ cần override những điểm muốn thay đổi; các phương thức không override giữ cách xử lý bình thường của framework và Spring Boot.

Ví dụ cấu hình đúng cho Spring Boot:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class ReactiveWebConfiguration implements WebFluxConfigurer {
    // Chỉ override những callback cần thiết.
}
~~~

Đoạn trên minh họa cấu trúc một configuration class; code chạy hoàn chỉnh được trình bày ở phần 7.

### Ba lựa chọn cấu hình và hệ quả

| Cách làm | Điều gì xảy ra? | Nên dùng khi nào? |
|---|---|---|
| @Configuration + WebFluxConfigurer, **không @EnableWebFlux** | Bổ sung vào WebFlux infrastructure đang được Boot cấu hình tự động | **Mặc định nên chọn** khi chỉ cần CORS, codec, resource, formatter... |
| @Configuration + @EnableWebFlux | Kích hoạt cơ chế WebFlux configuration do framework tự quản lý, khiến phần WebFlux auto-configuration của Boot lùi lại | Chủ động muốn tự kiểm soát cấu hình WebFlux toàn diện và chấp nhận khôi phục những phần Boot đã cung cấp |
| Tự mở rộng WebFluxConfigurationSupport / DelegatingWebFluxConfiguration | Kiểm soát sâu các bean nền của WebFlux; cần hiểu thứ tự và điều kiện tạo bean | Trường hợp framework extension API không đáp ứng được, rất hiếm trong ứng dụng thông thường |

**Không nên hiểu rằng @EnableWebFlux làm toàn bộ Spring Boot tắt**: Boot vẫn có thể khởi tạo ApplicationContext và embedded server. Tác động chính là Boot không còn bổ sung một số cấu hình WebFlux ở tầng framework theo đường auto-configuration chuẩn. Điều đó có thể biểu hiện bằng thay đổi static-resource mapping, codecs, view handling hoặc những convention đã quen dùng.

## 3. Xác nhận ứng dụng thực sự chạy WebFlux

Để ví dụ có đúng ý nghĩa, dự án nên dùng spring-boot-starter-webflux và reactive web application type.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Starter này thường đưa Reactor Netty vào làm embedded reactive HTTP server. WebFlux có thể chạy với các server phù hợp khác; **WebFluxConfigurer** cấu hình xử lý request của WebFlux chứ không trực tiếp chọn HTTP server hoặc cổng lắng nghe.

Khi có đồng thời spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot thông thường chọn **Spring MVC (Servlet application)**. Điều này có chủ đích: nhiều dự án MVC chỉ thêm starter-webflux để dùng WebClient. Vì vậy, không thể thấy Mono/Flux trên classpath rồi kết luận WebFluxConfigurer của ứng dụng đang điều khiển MVC runtime.

Nếu cần chạy reactive thật sự, ưu tiên chọn starter đúng mục đích. Khi bắt buộc có cả hai dependency, có thể chủ động cấu hình:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Hãy thử nghiệm với cả các thư viện khác trong dependency graph. Trong reactive application, dùng các lớp thuộc org.springframework.web.reactive.config.*; WebMvcConfigurer và các servlet HandlerInterceptor không phải API để mở rộng WebFlux.

## 4. Những phương thức WebFluxConfigurer thường sử dụng

| Callback | Tác dụng | Trường hợp dùng |
|---|---|---|
| addCorsMappings(CorsRegistry) | Đăng ký CORS theo URL cho WebFlux handler mappings phù hợp | Frontend khác origin gọi API |
| addFormatters(FormatterRegistry) | Bổ sung Converter/Formatter phục vụ binding tham số của annotated controllers | ISO date, custom value type |
| addResourceHandlers(ResourceHandlerRegistry) | Bổ sung đường dẫn phục vụ static resources | /manual-assets/** |
| configureHttpMessageCodecs(ServerCodecConfigurer) | Tùy chỉnh HTTP message readers/writers và codec mặc định | Giới hạn buffer, thêm codec đặc thù |
| configurePathMatching(PathMatchConfigurer) | Điều chỉnh matching hoặc prefix cho annotated controllers | Quy ước prefix /api cho nhóm controller |
| configureContentTypeResolver(RequestedContentTypeResolverBuilder) | Tùy chỉnh cách chọn response media type | Content negotiation đặc thù |
| configureViewResolvers(ViewResolverRegistry) | Cấu hình view resolution cho ứng dụng trả HTML | Thymeleaf, FreeMarker và view engine |
| configureArgumentResolvers(ArgumentResolverConfigurer) | Đăng ký custom argument resolvers cho annotated controllers | Tham số request đặc thù |
| configureBlockingExecution(BlockingExecutionConfigurer) | Điều chỉnh cơ chế thực thi phương thức controller có tính blocking | Tích hợp phương thức legacy, cần executor phù hợp |

Các callback có phạm vi tác dụng khác nhau. Ví dụ, cấu hình path prefix cho annotated @RestController **không tự động đổi path của mọi RouterFunction**. Những HTTP codecs có thể được dùng cả khi xử lý annotated controllers lẫn functional endpoints, còn CORS với RouterFunction nên được kiểm tra trên chính endpoint thực tế; khi dùng functional routes, CorsWebFilter có thể là lựa chọn phù hợp.

Bổ sung configurer không tự biến mã JDBC hoặc blocking I/O thành non-blocking. Phải lựa chọn scheduling và client non-blocking đúng cách để giữ tính chất phản ứng của WebFlux.

## 5. CORS: bổ sung một quy tắc mà không thay Boot defaults

Một ứng dụng web ở https://frontend.example.test cần gọi API từ browser sang server khác origin. Có thể đăng ký CORS trong WebFluxConfigurer:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.test")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization")
            .maxAge(3600);
}
~~~

Ý nghĩa:

- /api/** giới hạn phạm vi CORS; không tự mở quyền cho mọi URL của ứng dụng.
- allowedOrigins chứa **origin** gồm scheme, host và port nếu có. Đây là origin mẫu; phải thay bằng domain thật của frontend khi triển khai.
- allowedMethods xác định những HTTP method mà browser có thể sử dụng theo cơ chế CORS.
- allowedHeaders giới hạn headers trong preflight; thêm các header theo nhu cầu thực tế.
- maxAge(3600) cho phép browser cache kết quả preflight trong thời gian được cấu hình, chịu giới hạn của browser.

CORS **không phải authentication hoặc authorization**. Một API có CORS cho phép một origin gọi vẫn cần Spring Security hoặc logic kiểm soát quyền nếu dữ liệu không công khai. CORS là chính sách browser; HTTP client như curl không chịu chính sách same-origin giống trình duyệt.

Không bật allowCredentials(true) rồi kết hợp với wildcard allowedOrigins("*"). Khi cho phép credentials, origin cần được xác định rõ hoặc dùng allowedOriginPatterns với quy tắc phù hợp. Hãy kiểm tra chặt chẽ wildcard subdomain để tránh vô tình cấp phép cho host không đáng tin.

Nếu dự án dùng Spring Security WebFlux, cần phối hợp CORS với SecurityWebFilterChain; khi security xử lý preflight trước cấu hình CORS, request OPTIONS có thể bị từ chối. Kiểm thử một preflight thực tế có Origin và Access-Control-Request-Method thay vì chỉ kiểm tra method GET không có header.

### @CrossOrigin so với WebFluxConfigurer

@CrossOrigin phù hợp khi chính sách chỉ gắn với một controller hoặc một method. addCorsMappings thích hợp để áp dụng chính sách chung cho một nhóm URL. Hai cách có thể kết hợp theo quy tắc cấu hình CORS của Spring; tránh khai báo trái ngược hoặc quá rộng ở nhiều tầng.

Nếu dùng functional endpoints với RouterFunction, có thể dùng CorsWebFilter cho chính sách bao quát. Đừng giả định rằng mọi cấu hình annotation-level đều tự tác dụng với functional route.

## 6. Formatter và conversion: bổ sung vào registry

Spring WebFlux có sẵn conversion service cho nhiều kiểu dữ liệu, bao gồm số và một số kiểu ngày giờ. Khi cần ràng buộc định dạng ISO rõ ràng trong annotated controllers:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
~~~

Các import:

~~~java
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
~~~

Đây là cách **bổ sung** formatter vào FormattingConversionService đang được framework dùng. Không cần tự khai báo toàn bộ ConversionService bean chỉ để xử lý LocalDate.

Spring Boot cũng có properties như spring.webflux.format.date, spring.webflux.format.time và spring.webflux.format.date-time. Khi yêu cầu chỉ là quy định format quen thuộc, nên ưu tiên property để cấu hình dễ quản trị. Ví dụ:

~~~yaml
spring:
  webflux:
    format:
      date: yyyy-MM-dd
~~~

Đây là cấu hình thay thế theo nhu cầu, không cần bật song song với custom registrar nếu hai cách có thể cạnh tranh. Trường hợp hỗ trợ custom domain type mới là lý do thường gặp để đăng ký Formatter/Converter bằng Java.

Nội dung validation và cách serialize JSON không đồng nghĩa với formatting tham số URL. Một Formatter cho @RequestParam LocalDate chưa chắc thay đổi ObjectMapper của JSON body. Để điều chỉnh JSON serialization/deserialization, xem cấu hình Jackson và codec phù hợp.

## 7. Static resource handler: bổ sung đường dẫn và giữ mapping mặc định

Spring Boot WebFlux có sẵn static resource support cho các vị trí classpath thông thường:

- classpath:/static/
- classpath:/public/
- classpath:/resources/
- classpath:/META-INF/resources/

Trong cấu hình thường dùng, Boot ánh xạ các tài nguyên tĩnh trên /** và có thêm hỗ trợ WebJars. Nếu chỉ cần **thêm** một đường dẫn tùy chỉnh, có thể dùng:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/manual-assets/**")
            .addResourceLocations("classpath:/manual-assets/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(15)).cachePublic()
            );
}
~~~

Với tệp src/main/resources/manual-assets/help.css, URL tương ứng là /manual-assets/help.css. Cache-Control tối đa 15 phút phù hợp với ví dụ minh họa, không phải giá trị bắt buộc cho mọi asset.

Khi giữ WebFlux auto-configuration của Boot, một custom handler hẹp như /manual-assets/** có thể cùng tồn tại với static resource mapping mặc định. Điều cần kiểm thử chính là **cả URL mới lẫn file mặc định vẫn hoạt động**.

Ví dụ hai tệp:

~~~text
src/main/resources/manual-assets/help.css
src/main/resources/static/default.txt
~~~

Sau khi startup đúng, kỳ vọng:

~~~text
GET /manual-assets/help.css -> nội dung help.css
GET /default.txt           -> nội dung default.txt do Boot mapping mặc định
~~~

Nếu thêm @EnableWebFlux và không tự phục hồi cấu hình static resources của Boot, hành vi mặc định có thể thay đổi. Đó là lỗi regression đặc biệt dễ bị bỏ sót nếu chỉ kiểm thử đường dẫn custom mới.

### Properties liên quan

Spring Boot hỗ trợ:

~~~yaml
spring:
  webflux:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "classpath:/public/"
~~~

Lưu ý:

- spring.webflux.static-path-pattern đổi URL pattern của **mapping static mặc định do Boot quản lý**.
- spring.web.resources.static-locations thay danh sách static locations mặc định bằng danh sách chỉ định; nếu muốn giữ một vị trí, phải liệt kê nó.
- Các custom handler được đăng ký riêng qua WebFluxConfigurer có pattern/location do chính ứng dụng đặt.
- Đừng dùng spring.mvc.static-path-pattern cho ứng dụng reactive; đó là cấu hình thuộc Spring MVC.
- Không đặt static resource handler vào thư mục chứa secret, file cấu hình hoặc dữ liệu upload chưa qua kiểm tra.

Việc đăng ký cùng /** cho nhiều resource handlers hoặc trùng path với API có thể gây conflict khó giải thích. Ưu tiên prefix riêng và test các route quan trọng.

## 8. HTTP codecs và giới hạn bộ nhớ

WebFlux dùng HttpMessageReader/HttpMessageWriter để giải mã request body và mã hóa response body. Spring Boot chọn và tùy chỉnh các codec theo classpath và các CodecCustomizer, bao gồm tích hợp Jackson khi có thư viện tương ứng.

Nếu chỉ cần tăng giới hạn phần dữ liệu phải aggregate trong bộ nhớ, tùy chỉnh nhẹ bằng WebFluxConfigurer:

~~~java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
~~~

Mẫu này điều chỉnh **default codecs đang có**, không xóa tập codecs mặc định. Các trường hợp cần thêm reader/writer riêng có thể dùng customCodecs().register(...) tùy API và codec tương ứng. Hạn chế gọi registerDefaults(false) vì nó làm mất các codecs mặc định và có thể phá vỡ JSON, String, form body hoặc các định dạng khác nếu chưa đăng ký thay thế đầy đủ.

**Giới hạn maxInMemorySize không phải giới hạn tổng dung lượng của mọi stream.** Nó quan trọng khi một decoder/reader cần buffer dữ liệu để tạo một phần tử, ví dụ JSON body được gom trước khi parse. Với payload lớn, việc tăng giới hạn vô tội vạ có thể tăng rủi ro memory pressure. Tùy codec và đường đọc, vượt ngưỡng có thể dẫn đến DataBufferLimitException.

Trong Spring Boot 3.5, khi chỉ cần cấu hình giá trị này, có thể ưu tiên property dành cho HTTP codecs:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
~~~

Thuộc tính này áp dụng cho các WebFlux server và WebClient được Boot tự cấu hình theo mô tả của phiên bản. Đây là lựa chọn **thay thế** cho override Java nếu cả hai chỉ nhằm thay cùng một giới hạn. Không đặt các giá trị mâu thuẫn ở cả property và WebFluxConfigurer rồi giả định thứ tự ưu tiên luôn giống nhau qua mọi phiên bản.

Khi điều chỉnh Jackson, hãy dùng các cơ chế cấu hình của Boot như spring.jackson.* hoặc customizer phù hợp trước khi thay thế toàn bộ JSON reader/writer. Nếu bỏ hết default codecs, bạn phải tự kiểm tra khả năng xử lý application/json, text/plain, multipart và những định dạng mà ứng dụng sử dụng.

## 9. Ví dụ Spring Boot hoàn chỉnh: thêm CORS, formatter, codec và resource

### 9.1. Dependencies và cấu trúc tệp

Ví dụ dùng Spring Boot **3.5.x**, Java **17+**, Maven và ba dependency:

~~~xml
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
~~~

Đây là đoạn dependencies dành cho một Maven project Spring Boot có parent/BOM để quản lý các versions tương thích. Không tự copy vào một POM thiếu Spring Boot dependency management mà bỏ qua khai báo version.

Các tệp:

~~~text
src/main/java/example/webflux/
    ReactiveDemoApplication.java
    ReactiveWebConfiguration.java
    DemoApiController.java
src/main/resources/
    static/default.txt
    manual-assets/help.css
src/test/java/example/webflux/
    ReactiveWebConfigurationTest.java
~~~

Thư mục package trong source đúng với package declaration của các class, để component scanning tìm được controller và configuration.

### 9.2. Lớp ứng dụng

Tệp src/main/java/example/webflux/ReactiveDemoApplication.java:

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemoApplication.class, args);
    }
}
~~~

Không thêm @EnableWebFlux. Spring Boot sẽ đánh giá auto-configuration theo classpath và web application type.

### 9.3. ReactiveWebConfiguration

Tệp src/main/java/example/webflux/ReactiveWebConfiguration.java:

~~~java
package example.webflux;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.http.CacheControl;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ReactiveWebConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .maxAge(3600);
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manual-assets/**")
                .addResourceLocations("classpath:/manual-assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(15))
                                .cachePublic()
                );
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

**Điểm cốt lõi nằm ở việc không có @EnableWebFlux.** Bốn callback thêm cấu hình cần thiết và để hạ tầng WebFlux được Boot tự quản lý theo cách thông thường.

Lớp ví dụ vừa thiết lập giới hạn codec vừa đăng ký formatter. Trong dự án thực tế, nếu chỉ cần một thông số có property tương đương, thường nên cấu hình ở application.yaml cho đơn giản.

### 9.4. Annotated reactive controller

Tệp src/main/java/example/webflux/DemoApiController.java:

~~~java
package example.webflux;

import java.time.LocalDate;
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoApiController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of("message", "hello"));
    }

    @GetMapping("/date")
    public Mono<Map<String, String>> date(
            @RequestParam("day") LocalDate day) {
        return Mono.just(Map.of("day", day.toString()));
    }

    @PostMapping("/echo")
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<Map<String, String>> requestBody) {
        return requestBody.map(payload ->
                Map.of("message", payload.getOrDefault("message", "")));
    }
}
~~~

Phần này minh họa ba năng lực:

- GET /api/hello trả JSON được codec mặc định xử lý.
- GET /api/date?day=2026-11-07 dùng conversion/formatter cho tham số LocalDate.
- POST /api/echo đọc JSON body thành Mono<Map<...>> rồi phản hồi JSON tương ứng.

Ví dụ không có blocking I/O. Mono.just chỉ tạo dữ liệu đơn giản; với nghiệp vụ thực, lời gọi database/network cần chọn reactive driver/client hoặc cô lập phần blocking đúng cách.

### 9.5. Tài nguyên tĩnh

Tệp src/main/resources/manual-assets/help.css:

~~~css
body {
    color: #345678;
}
~~~

Tệp src/main/resources/static/default.txt:

~~~text
boot-default-still-works
~~~

Tệp thứ nhất phải được phục vụ qua handler /manual-assets/** do ứng dụng đăng ký. Tệp thứ hai phải tiếp tục được phục vụ qua Boot static mapping mặc định. Đây là cách quan sát trực tiếp rằng việc bổ sung configurer không phá vỡ static handling mà Boot vốn có.

### 9.6. Chạy thử

Nếu dự án có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với cấu hình mặc định thông thường, server lắng nghe cổng 8080. Nếu port đã bị override, cần đổi URL của curl tương ứng.

Kiểm tra endpoint JSON:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Response được mong đợi là HTTP 200 với JSON tương đương:

~~~json
{"message":"hello"}
~~~

Các header khác, thứ tự header và cách định dạng JSON có thể khác theo runtime. Không mặc định đây là toàn bộ raw HTTP response.

Kiểm tra LocalDate:

~~~bash
curl -i "http://localhost:8080/api/date?day=2026-11-07"
~~~

JSON body tương đương:

~~~json
{"day":"2026-11-07"}
~~~

Kiểm tra POST JSON:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
    -H "Content-Type: application/json" \
    -d '{"message":"sample"}'
~~~

Body dự kiến:

~~~json
{"message":"sample"}
~~~

Kiểm tra asset mới và asset mặc định:

~~~bash
curl -i http://localhost:8080/manual-assets/help.css
curl -i http://localhost:8080/default.txt
~~~

Đường dẫn custom trả CSS; đường dẫn mặc định trả nội dung boot-default-still-works. Cần xác nhận cả hai hoạt động thay vì chỉ test resource handler mới.

### 9.7. Kiểm tra CORS preflight

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/echo \
    -H "Origin: https://frontend.example.test" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Content-Type"
~~~

Nếu CORS và endpoint được map đúng, response preflight hợp lệ dự kiến có Access-Control-Allow-Origin với origin đã cho và cho phép POST. Hành vi HTTP status và các header chi tiết có thể khác tùy phiên bản/server/security, nên cần xem response thực.

Lệnh curl chỉ quan sát CORS response; trình duyệt mới thực thi chính sách CORS khi JavaScript gọi qua cross-origin.

## 10. Kiểm thử hồi quy bằng WebTestClient

Spring WebFlux dùng WebTestClient để kiểm thử handler và response ở tầng reactive HTTP. Để kiểm tra cả Boot embedded-server configuration lẫn custom WebFluxConfigurer, có thể chạy full context với random port.

Tệp src/test/java/example/webflux/ReactiveWebConfigurationTest.java:

~~~java
package example.webflux;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveWebConfigurationTest {

    @Autowired
    WebTestClient client;

    @Test
    void jsonStillWorks() {
        client.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void localDateParameterIsConverted() {
        client.get()
                .uri("/api/date?day=2026-11-07")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.day").isEqualTo("2026-11-07");
    }

    @Test
    void preflightForConfiguredOriginIsAllowed() {
        client.options()
                .uri("/api/echo")
                .header(HttpHeaders.ORIGIN,
                        "https://frontend.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "Content-Type")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://frontend.example.test");
    }

    @Test
    void customResourceHandlerWorks() {
        client.get()
                .uri("/manual-assets/help.css")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body).contains("#345678"));
    }

    @Test
    void bootDefaultStaticResourceStillWorks() {
        client.get()
                .uri("/default.txt")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body)
                        .contains("boot-default-still-works"));
    }
}
~~~

Với Maven Wrapper:

~~~bash
./mvnw test
~~~

Từ Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

Cách đọc các test:

- jsonStillWorks xác nhận codec JSON mặc định vẫn hoạt động.
- localDateParameterIsConverted kiểm tra formatter/argument binding.
- preflightForConfiguredOriginIsAllowed kiểm tra chính sách CORS thực.
- customResourceHandlerWorks xác nhận phần bổ sung mới.
- bootDefaultStaticResourceStillWorks là regression test cho tính năng Boot vốn có.

Nếu xóa test cho default.txt, dự án có thể vô tình chuyển sang full WebFlux control và mất tài nguyên mặc định mà bộ test không phát hiện.

Các test này dựa trên project Spring Boot 3.5.x cùng tệp resource đã nêu. Nếu có Spring Security, custom WebFilter hoặc reverse proxy, cần test các policy và phần infrastructure bổ sung; một HTTP status 401/403 từ security không tự chứng minh rằng CORS mapping hoặc resource handler sai.

## 11. WebFluxConfigurer so với các extension point khác

Không phải mọi chỉnh sửa trong reactive stack đều thuộc WebFluxConfigurer.

| Nhu cầu | API/configuration nên cân nhắc |
|---|---|
| CORS theo URL của annotated controllers | WebFluxConfigurer.addCorsMappings hoặc @CrossOrigin |
| CORS xuyên nhiều handler/functional routes | CorsWebFilter hoặc security CORS integration phù hợp |
| Filter chung trước/sau request reactive | WebFilter, WebFilterChain |
| Xác thực, phân quyền, CSRF | Spring Security WebFlux và SecurityWebFilterChain |
| Định dạng input/output của controller | Formatter/Converter, codec config và Jackson customization |
| Custom HTTP error response | WebExceptionHandler / ErrorWebExceptionHandler hoặc cấu hình Problem Details |
| Embedded server bind, port, threads/network | server.*, WebServerFactoryCustomizer và Netty/Tomcat-specific config |
| Thay đổi auto-configured HttpHandler builder | WebHttpHandlerBuilderCustomizer bean theo Spring Boot |
| Viết functional endpoint | RouterFunction, HandlerFunction và RouterFunctions |
| Thay toàn bộ MVC/Servlet configuration | Không dùng WebFluxConfigurer; chọn đúng stack hoặc WebMvcConfigurer nếu thực sự là MVC |

Ví dụ, nếu bạn cần log mọi request kể cả functional routes, WebFilter có thể phù hợp hơn việc tìm một MVC HandlerInterceptor. Nếu bạn cần điều chỉnh port server từ 8080 sang 9090, dùng server.port hoặc factory customizer; WebFluxConfigurer không cấu hình server socket.

Đừng dùng ServerWebExchange trong Servlet MVC code với giả định hai mô hình có cùng vòng đời. WebFlux dùng reactive abstractions; MVC dùng Servlet API. Khác biệt này ảnh hưởng filter, exception handling và cách kiểm thử.

## 12. Khi nào có thể dùng @EnableWebFlux?

@EnableWebFlux có ý nghĩa trong ứng dụng Spring Framework chạy không có Spring Boot hoặc trong dự án Boot **cố tình tự kiểm soát toàn bộ WebFlux configuration**.

Chuyển từ:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {
}
~~~

sang:

~~~java
@Configuration
@EnableWebFlux
class WebConfig implements WebFluxConfigurer {
}
~~~

không đơn thuần là bật thêm một tính năng. WebFlux auto-configuration của Spring Boot có điều kiện lùi lại khi @EnableWebFlux được dùng. Các thiết lập Boot cung cấp phải được xem lại hoặc đăng ký thủ công nếu còn cần.

Nếu thật sự cần @EnableWebFlux, lập danh sách những hành vi mà ứng dụng phụ thuộc:

1. JSON, text, multipart và các codecs thực sự cần.
2. Static resource mappings, WebJars và welcome page.
3. HTTP error handling, Problem Details và exception mapping.
4. Formatter, validator, view resolver, CORS.
5. Tích hợp Spring Security, WebFilters và observability.
6. Các config properties đang sử dụng và đã được auto-configuration bind như thế nào.

Chỉ chọn full-control mode khi có lợi ích cụ thể và đã viết test bảo toàn các hành vi quan trọng. Cấu hình lại thủ công là công việc bảo trì lâu dài, đặc biệt khi nâng cấp Spring Boot.

## 13. Những lỗi hiểu nhầm phổ biến

### Lỗi 1: thêm @EnableWebFlux để “kích hoạt reactive”

Spring Boot có thể tự cấu hình WebFlux khi dependency và web application type phù hợp. Dùng @EnableWebFlux trong Boot chỉ để nhận được reactive controller là không cần thiết và có thể làm mất Boot WebFlux customizations.

**Cách sửa:** bỏ @EnableWebFlux, giữ @Configuration implements WebFluxConfigurer nếu chỉ bổ sung quy tắc.

### Lỗi 2: implements WebMvcConfigurer trong ứng dụng WebFlux

WebMvcConfigurer thuộc servlet MVC. Reactive web application không dùng các MVC registries cho request processing.

**Cách sửa:** chọn org.springframework.web.reactive.config.WebFluxConfigurer và kiểm tra Boot đã thực sự chọn WebApplicationType.REACTIVE chưa.

### Lỗi 3: có cả starter-web và starter-webflux nhưng cho rằng WebFlux luôn được chọn

Spring Boot thường chọn MVC nếu có cả hai. Code WebFluxConfigurer có thể không điều chỉnh stack mà developer tưởng đang sử dụng.

**Cách sửa:** xem dependency tree, auto-configuration condition report và application type. Chọn một web stack rõ ràng.

### Lỗi 4: tắt default codecs để thêm một codec

Gọi registerDefaults(false) rồi chỉ đăng ký một reader có thể làm API JSON, text hoặc các body khác không hoạt động như trước.

**Cách sửa:** ưu tiên defaultCodecs() và customCodecs().register(...) phù hợp; chỉ tắt defaults khi đã thay thế trọn bộ reader/writer cần thiết.

### Lỗi 5: tăng maxInMemorySize và cho rằng mọi response stream bị giới hạn tổng 512KB

Max in-memory size giới hạn việc aggregate/buffer trong các codec; không phải tổng bytes truyền qua mọi reactive stream.

**Cách sửa:** hiểu semantics của codec đang dùng, kiểm thử payload lớn và đặt policy về request size, proxy, multipart, rate limit riêng khi cần.

### Lỗi 6: ghi đè danh sách static-locations rồi mất tài nguyên của Boot

spring.web.resources.static-locations thay vị trí mặc định. Nếu chỉ khai báo một thư mục mới, các thư mục mặc định không được ngầm giữ lại.

**Cách sửa:** dùng addResourceHandlers cho prefix mới hoặc liệt kê rõ các vị trí cũ cần giữ trong property; thêm regression test cho /default.txt.

### Lỗi 7: dùng addCorsMappings như security policy

CORS điều khiển browser cross-origin behavior. Không kiểm soát ai có quyền đọc dữ liệu khi client không tuân same-origin policy.

**Cách sửa:** dùng Spring Security WebFlux cho access control và kiểm thử CORS + authentication/authorization kết hợp.

### Lỗi 8: dùng path prefix của annotated controller rồi mong RouterFunction tự được đổi

configurePathMatching phục vụ những phạm vi mapping nhất định và không tự rewrite mọi RouterFunction URI.

**Cách sửa:** định nghĩa path prefix cho functional routes bằng RouterFunctions/route predicates và viết test từng loại handler.

### Lỗi 9: tài nguyên phục vụ đúng local nhưng lỗi khi đóng gói JAR

Tệp static nằm sai thư mục, bị loại khỏi build hoặc custom resource location trỏ tới file path không tồn tại trong container.

**Cách sửa:** đặt tài nguyên dưới src/main/resources phù hợp, kiểm tra nội dung JAR và chạy integration test qua bản đóng gói.

### Lỗi 10: bỏ qua thứ tự của nhiều WebFluxConfigurer

Một dự án lớn có thể có nhiều configurers và customizers cùng tác động vào registry/codecs. Quy tắc chồng chéo làm hành vi khó dự đoán, đặc biệt với CORS và JSON codec.

**Cách sửa:** tổ chức cấu hình theo trách nhiệm, hạn chế nhiều nguồn điều khiển cùng một thuộc tính, và xác minh kết quả hiệu lực bằng integration tests.

## 14. Checklist thực hành và xác minh

Trước khi merge một thay đổi WebFluxConfigurer:

1. Kiểm tra ứng dụng đang là reactive stack và có starter WebFlux tương ứng.
2. Không thêm @EnableWebFlux nếu chỉ muốn bổ sung configuration.
3. Dùng properties trước khi viết code khi một property đáp ứng đầy đủ yêu cầu.
4. Khi thêm CORS, giới hạn origins/methods/headers; kiểm thử preflight và security.
5. Khi thêm formatters, kiểm tra cả successful binding và invalid input.
6. Khi chỉnh codec, giữ default readers/writers và test JSON/streaming cần thiết.
7. Khi thêm static handlers, dùng path prefix riêng và kiểm thử cả static resources mặc định.
8. Khi thay path matching, xác định ảnh hưởng tới annotated controllers, functional routes và resource mappings.
9. Khi dùng WebFilter, không chặn event-loop bằng I/O blocking trong request path.
10. Dùng WebTestClient kiểm tra HTTP responses và các default capabilities trước/sau thay đổi.
11. Nếu có nhiều configurers, ghi rõ trách nhiệm của từng lớp và kiểm thử khi chúng cùng tác động.
12. Khi nâng cấp Spring Boot, đọc changelog về WebFlux auto-configuration và package/API của đúng version.

## 15. Tài liệu chính thức

- [Spring Boot 3.5 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): hướng dẫn WebFluxConfigurer không @EnableWebFlux, codecs, static resources và reactive server.
- [Spring Framework 6.2 – WebFlux Config](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): các callback như addFormatters, configureHttpMessageCodecs, addResourceHandlers, configurePathMatching.
- [Spring Framework 6.2 – CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html): global CORS configuration, allowed origins và credentials.
- [Spring Framework 6.2 – WebFluxConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html): phạm vi và chữ ký các phương thức cấu hình.
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): spring.http.codecs.max-in-memory-size, spring.webflux.static-path-pattern và các properties liên quan.

**Ghi nhớ:** Trong Spring Boot WebFlux, **@Configuration implements WebFluxConfigurer không có @EnableWebFlux** là cách tự nhiên để thêm CORS, formatter, codec và static resource handler mà vẫn tận dụng mặc định Boot. Hãy chứng minh điều này bằng test cho cả chức năng mới và các chức năng tự cấu hình sẵn có, đặc biệt JSON codecs và static resources.