# Tùy chỉnh formatter, argument resolver và nội dung phản hồi trong Spring WebFlux

## 1. Mục tiêu học tập và ba tầng cần phân biệt

Spring WebFlux cung cấp các điểm mở rộng cho quá trình chuyển HTTP request thành lời gọi Java và biến kết quả Java thành HTTP response. Ba nhu cầu tưởng giống nhau nhưng phải giải quyết ở **ba tầng khác nhau**:

1. **Formatter / Converter**: chuyển đổi **giá trị** giữa String và kiểu Java, chẳng hạn path variable "ord-0042" thành OrderCode("ORD-0042"), hoặc hiển thị ngày/giờ theo quy tắc. Hook điển hình là WebFluxConfigurer.addFormatters(FormatterRegistry).
2. **HandlerMethodArgumentResolver**: cung cấp **toàn bộ đối số** cho một method controller, chẳng hạn @TenantHeader TenantContext được tạo từ header X-Tenant. Hook điển hình là WebFluxConfigurer.configureArgumentResolvers(ArgumentResolverConfigurer).
3. **Nội dung phản hồi**: quyết định HTTP status, headers, Content-Type và body được serialize/stream ra sao. Tùy nhu cầu, dùng ResponseEntity, @ResponseStatus, ServerResponse, Jackson annotation/ObjectMapper, HttpMessageWriter/codec, WebFilter.beforeCommit hoặc HandlerResultHandler chuyên biệt.

Đừng mặc định viết một custom HandlerAdapter hay thay DispatcherHandler cho những nhu cầu trên. Trong hầu hết ứng dụng, WebFluxConfigurer và các extension point được cung cấp sẵn đã đủ.

Bài học áp dụng cho **Spring Boot 3.3.x, Spring Framework 6.1.x và Java 17+**, tập trung vào **Spring WebFlux**. Spring MVC có nhiều annotation tương tự nhưng tên method cấu hình và interface argument resolver khác; không lấy ví dụ MVC rồi thay import sang WebFlux một cách máy móc.

Sau bài học, người đọc có thể đăng ký một Formatter riêng, xây custom reactive HandlerMethodArgumentResolver, kiểm soát body JSON và response headers, viết ứng dụng hoạt động độc lập và kiểm thử được cả thành công lẫn lỗi.

## 2. Yêu cầu đầu tiên: ứng dụng thật sự chạy Spring WebFlux

Dependency Gradle thường dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Spring Boot thường sử dụng Reactor Netty làm embedded server khi chỉ thêm starter-webflux. Nếu cùng có spring-boot-starter-web và spring-boot-starter-webflux, Boot **mặc định ưu tiên Servlet/Spring MVC**. Khi đó WebFluxConfigurer sẽ không phải điểm cấu hình server controller mà bạn mong đợi.

Với dự án chỉ dùng starter-webflux, không cần ép loại ứng dụng. Nếu bắt buộc có cả hai starter và thực sự muốn reactive server, có thể khai báo:

~~~properties
spring.main.web-application-type=reactive
~~~

Cấu hình này chọn reactive web application type; nó không làm JDBC, Thread.sleep hay các thư viện đồng bộ tự trở thành non-blocking.

Luồng xử lý tóm lược:

~~~mermaid
flowchart TD
    A["HTTP request / Reactor Netty"] --> B["HttpHandler và WebFilter chain"]
    B --> C["DispatcherHandler"]
    C --> D["HandlerMapping chọn HandlerMethod"]
    D --> E["RequestMappingHandlerAdapter (WebFlux)"]
    E --> F["Argument resolution"]
    F --> G["FormattingConversionService"]
    F --> H["Custom HandlerMethodArgumentResolver"]
    G --> I["Gọi controller method"]
    H --> I
    I --> J["HandlerResultHandler"]
    J --> K["HttpMessageWriter / Jackson codec"]
    K --> L["ServerHttpResponse"]
    L --> M["HTTP status + headers + body"]
~~~

Không phải request nào cũng qua tất cả nhánh. HandlerMapping có thể không tìm thấy route; WebFilter có thể chặn; custom resolver có thể trả Mono.error; controller có thể trả ResponseEntity, ServerResponse hoặc stream; error handling có thể ghi response trước khi result handler thường chạy.

### Ba từ khóa để nhớ

- **Parse/print**: formatter và conversion service.
- **Create method argument**: argument resolver.
- **Write response representation**: result handler và HTTP message codecs.

## 3. Bảng chọn điểm mở rộng

| Nhu cầu | Điểm mở rộng phù hợp | Không nên chọn đầu tiên |
| --- | --- | --- |
| Chuyển String path/query thành mã định danh có kiểu | Formatter hoặc Converter | Đọc HttpServletRequest hoặc custom HandlerAdapter |
| Parse ngày theo Locale trong request parameter | Formatter/FormatterRegistrar | Jackson serializer |
| Tạo tham số controller từ header/metadata do ứng dụng định nghĩa | Reactive HandlerMethodArgumentResolver | Custom body codec |
| Map JSON request body thành DTO | @RequestBody + HttpMessageReader/Jackson | Formatter |
| Validate input DTO | Jakarta Validation + @Valid, validation framework | WebFilter tự parse JSON |
| Chỉnh status và header trên một endpoint | ResponseEntity/ResponseStatusException | Thay DispatcherHandler |
| Chỉnh tên field của một JSON DTO | @JsonProperty / @JsonFormat hoặc Jackson config | Formatter |
| Cấu hình giới hạn aggregation body hoặc readers/writers | ServerCodecConfigurer | Custom argument resolver |
| Bổ sung response header cho nhiều endpoint | WebFilter hoặc công cụ response handling phù hợp | Serializer riêng |
| Nội dung response cần chuẩn hóa theo contract | DTO, mapper, ResponseEntity, Jackson | Regex thay chuỗi JSON sau serialization |
| Định dạng media type hoàn toàn mới | HttpMessageReader/HttpMessageWriter, Encoder/Decoder | Formatter cho kiểu path variable |
| Hợp đồng return type hoàn toàn mới | HandlerResultHandler có cân nhắc thứ tự | Sửa tất cả controller cho workaround |

Mỗi điểm mở rộng nên nhận **ít trách nhiệm nhất đủ dùng**. Điều đó giúp bảo trì và kiểm thử thuận lợi hơn.

## 4. Formatter, Converter và ConversionService khác nhau như thế nào?

### 4.1 Converter<S,T>

org.springframework.core.convert.converter.Converter<S,T> đổi một kiểu Java nguồn S sang T. Ví dụ Converter<String, OrderCode> phù hợp khi không cần Locale hoặc khả năng in ngược.

~~~java
public final class OrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        return new OrderCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Đây là **minh họa một class rút gọn**: cần imports và nên validate format của source. Converter thường đủ cho các mã ID, enum chuyển đặc thù hoặc chuyển đổi value object một chiều.

### 4.2 Formatter<T>

org.springframework.format.Formatter<T> kết hợp **Printer<T>** và **Parser<T>** với chữ ký:

~~~java
String print(T object, Locale locale);
T parse(String text, Locale locale) throws ParseException;
~~~

Trong đó Locale cho phép định dạng/parse theo ngôn ngữ-vùng miền. Formatter thích hợp cho những giá trị như số tiền, tỷ lệ, ngày tháng hoặc kiểu nghiệp vụ có biểu diễn văn bản.

Với mã đơn hàng dùng format cố định, ta vẫn có thể dùng Formatter để thấy đầy đủ cơ chế parse/print. Nhưng khi mã không phụ thuộc Locale, Converter có thể đơn giản hơn.

### 4.3 FormattingConversionService

Spring Framework kết nối các Formatter, Converter và các cơ chế chuẩn trong FormattingConversionService. WebFlux cấu hình dịch vụ này cho annotation controller argument binding.

Ví dụ phương thức:

~~~java
@GetMapping("/orders/{code}")
public Mono<OrderView> find(@PathVariable OrderCode code) {
    // ...
}
~~~

Khi URL chứa /orders/ord-0042, framework cần đổi String raw path variable thành OrderCode. Formatter đã đăng ký có thể làm việc đó trước khi controller được gọi.

**Giới hạn quan trọng:** Formatter **không** tự động thay đổi cách Jackson serialize một DTO JSON. Jackson sử dụng serializer/annotations/config riêng. Một ResponseEntity<OrderView> trả JSON không đi qua Formatter<OrderCode> chỉ vì DTO chứa một OrderCode.

## 5. Viết Formatter cho mã đơn hàng

Giả sử định dạng nghiệp vụ là ORD-0001, ORD-0042, ORD-9999. Ta chấp nhận input chữ thường rồi chuẩn hóa thành chữ hoa.

~~~java
package com.example.customwebflux;

public record OrderCode(String value) {
}
~~~

Một file OrderCode.java với public record ở trên có thể biên dịch trên Java 17+.

File OrderCodeFormatter.java:

~~~java
package com.example.customwebflux;

import java.text.ParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class OrderCodeFormatter implements Formatter<OrderCode> {

    @Override
    public OrderCode parse(String text, Locale locale)
            throws ParseException {

        if (text == null) {
            throw new ParseException("Order code is required", 0);
        }

        String normalized = text.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("ORD-[0-9]{4}")) {
            throw new ParseException(
                    "Expected order code such as ORD-0042", 0);
        }

        return new OrderCode(normalized);
    }

    @Override
    public String print(OrderCode object, Locale locale) {
        return object.value();
    }
}
~~~

Giải thích:

1. parse nhận String từ HTTP request parameter/path variable.
2. Dùng Locale.ROOT cho uppercase vì định dạng mã là bất biến giữa các ngôn ngữ; không dùng Locale.getDefault dễ dẫn đến hành vi không mong đợi ở một số locale.
3. Regex yêu cầu chính xác ORD- và bốn chữ số.
4. ParseException báo input sai định dạng; Spring WebFlux có thể chuyển lỗi bind/conversion thành 400 Bad Request theo pipeline mặc định.
5. print trả biểu diễn văn bản của object. Trong luồng khác, Spring formatting system có thể dùng nó để biến kiểu Java thành String; JSON body vẫn theo codec/serializer.

Đừng cho rằng parse luôn chỉ chạy trên event loop hoặc chỉ chạy một lần trong mọi kiểu request. Nó cần là hàm nhỏ, không có side effect và thread-safe. Không gọi database hoặc network bên trong formatter.

### Chỗ nào không nên dùng Formatter?

- Đọc cả HTTP header + cookie + token để tạo TenantContext: đây là công việc argument resolver.
- Chuyển request body JSON sang record OrderCreateRequest: đây là công việc message reader.
- Áp dụng quy tắc đổi tên field JSON từ orderCode sang order_code: đây là công việc Jackson serialization.
- Chèn một header X-Trace vào mọi response: đây là response/filter concern.

## 6. Đăng ký formatter với WebFluxConfigurer

Spring WebFlux có interface:

~~~java
org.springframework.web.reactive.config.WebFluxConfigurer
~~~

Để đăng ký formatter, override:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new OrderCodeFormatter());
}
~~~

Đoạn trên được đặt trong một class @Configuration implements WebFluxConfigurer; **không phải một file Java độc lập**.

Spring Boot thường tự cấu hình WebFlux. Khi muốn bổ sung formatter, sử dụng:

~~~java
@Configuration
public class WebConfig implements WebFluxConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new OrderCodeFormatter());
    }
}
~~~

Snip này minh họa cấu trúc lớp và cần imports. Bản code đầy đủ được cung cấp ở mục 15.

**Không thêm @EnableWebFlux chỉ để đăng ký formatter.** Trong Spring Boot, @EnableWebFlux chuyển mức độ kiểm soát cấu hình framework sang ứng dụng và có thể khiến một số WebFlux auto-configuration của Boot không được áp dụng như trước. Với nhu cầu tùy chỉnh nhỏ, @Configuration + implements WebFluxConfigurer là lựa chọn thông thường.

### Các kiểu format mặc định

Spring hỗ trợ nhiều conversion/formatter cho enum, number, date/time, các annotation như @DateTimeFormat. Chỉ viết custom formatter khi input contract thực sự đặc biệt.

Ví dụ:

~~~java
@GetMapping("/report")
public Mono<String> report(
        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return Mono.just(date.toString());
}
~~~

Snippet trên cần import LocalDate, DateTimeFormat và annotation WebFlux tương ứng. Nếu format ISO đã đáp ứng yêu cầu, không cần custom Formatter<LocalDate> riêng.

## 7. Khi nào phải dùng HandlerMethodArgumentResolver?

Controller method đôi khi cần một tham số **không trực tiếp tương ứng một giá trị String**. Ví dụ mọi endpoint nội bộ đều muốn nhận:

~~~java
@TenantHeader TenantContext tenant
~~~

tenant được xác định từ header X-Tenant-Id. Nếu tự lặp @RequestHeader ở hàng trăm endpoint rồi parse/validate mỗi lần, code vừa dài vừa dễ không nhất quán. Một custom resolver có thể:

- Nhận diện tham số có annotation @TenantHeader và đúng kiểu TenantContext.
- Đọc header từ ServerWebExchange.
- Kiểm tra required/format.
- Trả một Mono chứa TenantContext.
- Gửi reactive error nếu input không hợp lệ.

Đây là trường hợp phù hợp với **org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver**, không phải interface cùng tên của Spring MVC.

### API quan trọng của WebFlux

~~~java
boolean supportsParameter(MethodParameter parameter);

Mono<Object> resolveArgument(
        MethodParameter parameter,
        BindingContext bindingContext,
        ServerWebExchange exchange);
~~~

Trong WebFlux, resolveArgument trả **Mono<Object>**. Spring MVC Servlet dùng API argument resolver khác và thông thường trả trực tiếp Object từ NativeWebRequest/WebDataBinderFactory. Không sao chép interface MVC sang package reactive.

### Vì sao trả Mono<Object>?

Một argument resolver có thể cần lấy thông tin từ reactive request context mà chưa có ngay. Publisher cho framework khả năng kết hợp lời giải nhiều arguments mà không bắt buộc blocking thread. Trong ví dụ header đơn giản, Mono.just hoặc Mono.defer đủ. Đối với nguồn I/O bất đồng bộ, cần giữ hoàn toàn reactive; không .block() để “biến Mono thành Object”.

## 8. Xây annotation và kiểu TenantContext

File TenantHeader.java:

~~~java
package com.example.customwebflux;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface TenantHeader {
}
~~~

Ý nghĩa:

- @Target(PARAMETER) giới hạn annotation cho method parameter.
- @Retention(RUNTIME) để HandlerMethodArgumentResolver đọc được annotation trong lúc chạy.
- Không đặt logic authenticate/authorize chỉ bằng việc khai báo annotation; annotation chỉ là metadata.

File TenantContext.java:

~~~java
package com.example.customwebflux;

public record TenantContext(String id) {
}
~~~

Record immutable phù hợp cho dữ liệu request-scoped. Thông tin tenant nên được xác định **sau khi** hệ bảo mật xác thực nguồn header nếu ứng dụng nhiều tenant yêu cầu trust boundary nghiêm ngặt. Ví dụ ở đây chỉ minh họa kỹ thuật resolver, **không tự chứng minh tenant từ header là danh tính đã xác thực**.

## 9. Xây custom reactive argument resolver

File TenantHeaderResolver.java:

~~~java
package com.example.customwebflux;

import java.util.Locale;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.BindingContext;
import org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class TenantHeaderResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(TenantHeader.class)
                && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String header = exchange.getRequest().getHeaders()
                    .getFirst("X-Tenant-Id");

            if (header == null || header.isBlank()) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"));
            }

            String tenantId = header.trim().toLowerCase(Locale.ROOT);

            if (!tenantId.matches("[a-z0-9-]{1,24}")) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Invalid X-Tenant-Id"));
            }

            return Mono.just((Object) new TenantContext(tenantId));
        });
    }
}
~~~

Đây là class độc lập, đủ imports cho Spring WebFlux/Spring Boot 3.3 và Reactor. Nó không đọc body và không gọi subscribe().

Các điểm cần hiểu:

1. supportsParameter kiểm tra **cả annotation lẫn kiểu**; nếu chỉ so tên tham số, resolver có thể vô tình nhận cả những phương thức không có chủ đích.
2. Mono.defer để logic đọc header và kiểm tra được thực hiện khi framework subscribe. Trong trường hợp header đơn giản, dùng Mono.just cũng có thể đủ; Mono.defer giúp giữ semantics lazy dễ hiểu.
3. Mono.error chuyển lỗi tham số thành reactive error signal; ResponseStatusException có thể dẫn đến HTTP 400 qua handler lỗi WebFlux mặc định.
4. Chỉ validate định dạng ở ví dụ; **đừng tin header tenant đến từ client công cộng nếu không có authentication, authorization và kiểm tra tenant access**.
5. Argument resolver nên tránh blocking lookup. Nếu cần kiểm tra tenant trong database, ưu tiên reactive repository hoặc thực hiện ở service/security layer theo kiến trúc.
6. Giá trị TenantContext được tạo mới cho từng lần giải quyết tham số; không lưu tenant của request hiện tại trong một mutable singleton field.

### Đăng ký resolver

Hook đúng trên Spring WebFlux:

~~~java
@Override
public void configureArgumentResolvers(
        ArgumentResolverConfigurer configurer) {
    configurer.addCustomResolver(new TenantHeaderResolver());
}
~~~

ArgumentResolverConfigurer ở package:

~~~text
org.springframework.web.reactive.result.method.annotation.ArgumentResolverConfigurer
~~~

Không nhầm với WebMvcConfigurer.addArgumentResolvers(List<HandlerMethodArgumentResolver>) ở Spring MVC. Trong WebFlux, **WebFluxConfigurer.configureArgumentResolvers** mới là method của cấu hình WebFlux.

Custom resolvers được thêm vào hạ tầng xử lý annotated controller của WebFlux. Không nên dựa vào custom resolver này để tự động xử lý tham số của functional HandlerFunction<ServerResponse>: functional routing có API ServerRequest, headers, attributes và filter riêng.

## 10. Thứ tự resolver và những trường hợp khó

RequestMappingHandlerAdapter trong Spring WebFlux dùng các argument resolvers được framework xây dựng để hỗ trợ @PathVariable, @RequestParam, @RequestBody, ServerWebExchange, Model, validation và nhiều kiểu built-in.

Custom resolver không nhất thiết là **resolver đầu tiên** được hỏi cho mọi tham số. Vì thế:

- Chọn một annotation và Java type riêng biệt để tránh xung đột built-in.
- Đừng cố ghi đè @RequestBody hoặc @RequestParam bằng resolver có supportsParameter quá rộng.
- Nếu một built-in resolver nhận tham số trước, resolver custom có thể không được gọi.
- Khi ứng dụng được cập nhật phiên bản Spring, kiểm tra lại thứ tự, các resolver built-in mới và test.
- Nếu không có resolver hỗ trợ một tham số, controller có thể không được gọi và framework phát lỗi argument resolution.

Đừng đòi custom resolver phải có quyền gọi trực tiếp một bean Controller bất kỳ. Công việc của nó là cung cấp **một giá trị tham số**, còn handler invocation do RequestMappingHandlerAdapter điều phối.

### Một alternative đơn giản hơn

Nếu chỉ cần chuỗi từ một header và không có logic dùng lại:

~~~java
@GetMapping("/who")
public Mono<String> who(
        @RequestHeader("X-Tenant-Id") String tenantId) {
    return Mono.just(tenantId);
}
~~~

Phương án built-in là đủ. Custom resolver có giá trị khi cần abstraction rõ ràng, validation/normalization lặp lại và khả năng test độc lập.

## 11. Nội dung phản hồi WebFlux được tạo như thế nào?

Spring WebFlux tách việc controller **trả giá trị** và việc framework **ghi bytes** tới client.

Ví dụ annotated controller:

~~~java
@GetMapping("/status")
public Mono<ResponseEntity<StatusView>> status() {
    return Mono.just(ResponseEntity.ok(
            new StatusView("READY", "reactive")));
}
~~~

Các bước điển hình:

1. DispatcherHandler tìm HandlerMethod.
2. WebFlux RequestMappingHandlerAdapter giải quyết tham số và gọi controller.
3. Controller trả Mono<ResponseEntity<StatusView>>.
4. ReactiveAdapterRegistry và result handling thích hợp thích nghi kiểu reactive.
5. HandlerResultHandler (ví dụ ResponseEntityResultHandler) áp dụng status/header rồi chuyển body tới HttpMessageWriter.
6. Encoder/codec (thường Jackson với JSON) biến StatusView thành dữ liệu response; ServerHttpResponse ghi dữ liệu.
7. Mono<Void> ở tầng HTTP handler hoàn tất khi response processing kết thúc.

Đoạn trên minh họa method; StatusView cần được định nghĩa ở class ứng dụng để biên dịch.

### Những yếu tố độc lập

- **HTTP status**: 200, 201, 204, 400, 404...
- **HTTP headers**: Location, Cache-Control, ETag, X-Request-Id, Content-Type...
- **Media type**: application/json, text/plain, application/problem+json...
- **Representation body**: DTO JSON, String, DataBuffer, Server-Sent Events...
- **Lỗi**: @ExceptionHandler, ResponseStatusException, WebExceptionHandler...
- **Timing/streaming**: Mono, Flux, cancellation, response commit.

Chỉnh một yếu tố không có nghĩa tự động chỉnh các yếu tố còn lại.

## 12. ResponseEntity, @ResponseStatus và functional ServerResponse

### 12.1 ResponseEntity

Khi muốn điều khiển status + header + body:

~~~java
return Mono.just(
        ResponseEntity.status(HttpStatus.CREATED)
                .header("Location", "/api/orders/ORD-0042")
                .body(new OrderView("ORD-0042", "shop-a", "created")));
~~~

Đoạn này là snippet return trong một method có chữ ký phù hợp.

ResponseEntity thường là lựa chọn đầu tiên trong annotated REST controller; không cần tự tạo HttpMessageWriter để đặt status 201.

### 12.2 @ResponseStatus

Đối với status cố định:

~~~java
@ResponseStatus(HttpStatus.NO_CONTENT)
@DeleteMapping("/{id}")
public Mono<Void> delete(@PathVariable String id) {
    return Mono.empty();
}
~~~

Snippet cần đặt trong controller với imports. @ResponseStatus thuận tiện khi handler luôn trả cùng status, nhưng để thay đổi response theo tình huống hoặc kiểm soát headers, ResponseEntity rõ ràng hơn.

### 12.3 Functional ServerResponse

Functional endpoint dùng:

~~~java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(view);
~~~

Đoạn này là kết quả của HandlerFunction<ServerResponse> trong RouterFunction. Functional routing không dùng annotation argument resolver của RequestMappingHandlerAdapter; handler nhận ServerRequest và tự chọn dữ liệu từ request context.

Đừng nhầm ServerResponse với Servlet HttpServletResponse. ServerResponse thuộc API functional endpoints của Spring WebFlux.

## 13. JSON body: Jackson và WebFlux HTTP codecs

WebFlux sử dụng **HttpMessageReader / HttpMessageWriter** và Encoder/Decoder. Với Spring MVC, tên phổ biến là HttpMessageConverter. Cùng nhu cầu JSON nhưng extension APIs khác.

Khi controller nhận:

~~~java
@PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<EchoView> echo(@RequestBody Mono<EchoRequest> input) {
    return input.map(v -> new EchoView(v.message()));
}
~~~

Jackson decoder có thể đọc JSON thành EchoRequest. Khi controller trả EchoView, Jackson encoder có thể ghi JSON response.

**Formatter không điều khiển cách JSON được serialize**. Muốn đổi tên field, định dạng ngày, ẩn trường, đặt null inclusion, hoặc chính sách serializer toàn cục, nên dùng DTO/Jackson annotations và ObjectMapper configuration phù hợp.

### @JsonProperty điều khiển tên field

~~~java
record OrderView(
        @JsonProperty("order_code") String orderCode,
        String tenant,
        String status) {
}
~~~

Với Jackson mặc định trong Boot 3.3, JSON có dạng:

~~~json
{"order_code":"ORD-0042","tenant":"shop-a","status":"ready"}
~~~

Ví dụ trên cần import com.fasterxml.jackson.annotation.JsonProperty và định nghĩa record cùng package. @JsonProperty thay biểu diễn JSON, nhưng **không** làm path variable "/api/orders/ord-0042" tự convert thành OrderCode. Đó là việc formatter.

### Trường hợp cần formatter trên JSON?

Formatter có thể tham gia dữ liệu đã được MVC/WebFlux bind qua ConversionService trong một số cơ chế đặc thù, nhưng JSON body đọc bằng Jackson theo contract codec thì không nên dựa vào FormatterRegistry như một giải pháp serialization chung. Phân biệt hai pipeline là nguyên tắc quan trọng nhất của bài.

## 14. Cấu hình ServerCodecConfigurer

WebFluxConfigurer cung cấp:

~~~java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(256 * 1024);
}
~~~

Đây là method đầy đủ khi nằm trong một class WebFluxConfigurer với import org.springframework.http.codec.ServerCodecConfigurer.

- maxInMemorySize cấu hình giới hạn bộ nhớ mặc định cho những codec thực hiện buffering/aggregation, theo cách từng codec áp dụng.
- Nó giúp giảm rủi ro giữ quá nhiều dữ liệu trong memory khi deserialize body lớn.
- Nó **không phải giới hạn tuyệt đối cho mọi request body/Flux streaming**; một endpoint chủ động stream có thể xử lý lượng dữ liệu lớn hơn mà không aggregate thành một object.
- Nếu body vượt giới hạn khi codec cần aggregate, lỗi có thể liên quan DataBufferLimitException; phản hồi HTTP cụ thể tùy framework, error mapping và cấu hình.
- Kiểm tra cả proxy/gateway, kích thước header và multipart limits nếu thiết kế API có upload lớn.

Trong Boot, cũng có cấu hình:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Thông thường hãy dùng property cho giới hạn đơn giản theo môi trường. Không cần đồng thời đặt property và code cho cùng một giá trị nếu không có lý do rõ ràng về thứ tự ưu tiên.

### Custom codecs cho format mới

ServerCodecConfigurer cho phép đăng ký thêm decoder/encoder hoặc HttpMessageReader/Writer. Chỉ nên làm khi media type/schema thực sự chưa được framework hỗ trợ.

Khi custom codec:

1. Xác định media type và ResolvableType được hỗ trợ.
2. Phân biệt stream versus single-value aggregation.
3. Xử lý backpressure, cancellation và DataBuffer lifecycle đúng cách.
4. Không log body chứa token hoặc dữ liệu nhạy cảm.
5. Test Content-Type/Accept, lỗi decode, encoding, giới hạn memory và thứ tự codec.
6. Tránh thay toàn bộ danh sách default codecs vì dễ mất JSON, String hoặc form/multipart support.

API configurer.defaultCodecs() cho phép chỉnh nhiều codec built-in; configurer.customCodecs() có các phương thức đăng ký codec tùy phiên bản. Không đoán tên method của dòng Spring 7 rồi dùng nguyên trong Boot 3.3/Spring 6.1.

### Ví dụ Jackson đặc thù

Có thể dùng @JsonProperty/@JsonFormat trên DTO, hoặc config ObjectMapper/Jackson2ObjectMapperBuilderCustomizer khi muốn policy toàn cục. Với Spring Boot, ưu tiên cấu hình Jackson qua Boot để không vô tình làm mất modules mà framework đang quản lý (Java Time, Kotlin, JDK8...), thay vì new ObjectMapper() rồi thay tất cả codec.

## 15. Ứng dụng hoàn chỉnh Java 17+: ba tùy chỉnh cùng hoạt động

Ví dụ có:

- Spring Boot WebFlux + Reactor Netty, không có starter-web.
- Formatter chuyển mã path variable không phân biệt chữ hoa-thường thành OrderCode chuẩn.
- Custom @TenantHeader + TenantHeaderResolver đọc X-Tenant-Id.
- ResponseEntity kiểm soát status/header/body.
- @JsonProperty điều chỉnh key JSON.
- WebFilter.beforeCommit thêm header chung trước khi response commit.
- ServerCodecConfigurer giới hạn aggregation memory.
- WebTestClient integration test dùng RANDOM_PORT.

### 15.1 Cấu trúc thư mục

~~~text
webflux-custom-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/customwebflux/
    │       ├── CustomWebFluxApplication.java
    │       ├── OrderCode.java
    │       ├── OrderCodeFormatter.java
    │       ├── TenantHeader.java
    │       ├── TenantContext.java
    │       ├── TenantHeaderResolver.java
    │       ├── WebFluxCustomConfig.java
    │       ├── OrderController.java
    │       └── ResponseHeadersFilter.java
    └── test/
        └── java/com/example/customwebflux/
            └── WebFluxCustomizationTests.java
~~~

### 15.2 settings.gradle

~~~groovy
rootProject.name = 'webflux-custom-demo'
~~~

### 15.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tất cả class trong ví dụ dùng package com.example.customwebflux. Cần cài Gradle tương thích Spring Boot 3.3.x, hoặc sử dụng Gradle wrapper nếu project có wrapper. Không ép Reactor/Netty phiên bản khác với BOM của Boot trong ví dụ.

### 15.4 CustomWebFluxApplication.java

~~~java
package com.example.customwebflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomWebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomWebFluxApplication.class, args);
    }
}
~~~

### 15.5 OrderCode.java và OrderCodeFormatter.java

OrderCode.java:

~~~java
package com.example.customwebflux;

public record OrderCode(String value) {
}
~~~

OrderCodeFormatter.java:

~~~java
package com.example.customwebflux;

import java.text.ParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class OrderCodeFormatter implements Formatter<OrderCode> {

    @Override
    public OrderCode parse(String text, Locale locale)
            throws ParseException {

        if (text == null) {
            throw new ParseException("Order code is required", 0);
        }

        String normalized = text.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("ORD-[0-9]{4}")) {
            throw new ParseException(
                    "Expected order code such as ORD-0042", 0);
        }

        return new OrderCode(normalized);
    }

    @Override
    public String print(OrderCode object, Locale locale) {
        return object.value();
    }
}
~~~

### 15.6 TenantHeader.java và TenantContext.java

TenantHeader.java:

~~~java
package com.example.customwebflux;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface TenantHeader {
}
~~~

TenantContext.java:

~~~java
package com.example.customwebflux;

public record TenantContext(String id) {
}
~~~

### 15.7 TenantHeaderResolver.java

~~~java
package com.example.customwebflux;

import java.util.Locale;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.BindingContext;
import org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class TenantHeaderResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(TenantHeader.class)
                && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String header = exchange.getRequest().getHeaders()
                    .getFirst("X-Tenant-Id");

            if (header == null || header.isBlank()) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"));
            }

            String tenantId = header.trim().toLowerCase(Locale.ROOT);

            if (!tenantId.matches("[a-z0-9-]{1,24}")) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Invalid X-Tenant-Id"));
            }

            return Mono.just((Object) new TenantContext(tenantId));
        });
    }
}
~~~

Resolver này mang tính học thuật, **không thay authentication/authorization**: một client có thể tự gửi X-Tenant-Id giả nếu server không xác thực. Trong production, tenant context nên được suy ra/đối chiếu từ principal đã xác thực và chính sách truy cập phù hợp.

### 15.8 WebFluxCustomConfig.java

~~~java
package com.example.customwebflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.result.method.annotation.ArgumentResolverConfigurer;

@Configuration
public class WebFluxCustomConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new OrderCodeFormatter());
    }

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {
        configurer.addCustomResolver(new TenantHeaderResolver());
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Chúng ta không dùng @EnableWebFlux: lớp @Configuration triển khai WebFluxConfigurer bổ sung tính năng mà không chủ động thay cách Spring Boot áp dụng auto-configuration thông thường.

Ba method là ba extension point độc lập, không nên hiểu configureArgumentResolvers có quyền thay đổi mọi codec hoặc addFormatters có thể chỉnh JSON field.

### 15.9 OrderController.java

~~~java
package com.example.customwebflux;

import com.fasterxml.jackson.annotation.JsonProperty;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(
            path = "/{code}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<OrderView>> find(
            @PathVariable("code") OrderCode code,
            @TenantHeader TenantContext tenant) {

        OrderView view =
                new OrderView(code.value(), tenant.id(), "ready");

        return Mono.just(ResponseEntity.ok()
                .header("X-Handler", "orders")
                .body(view));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<EchoView>> echo(
            @RequestBody Mono<EchoRequest> input,
            @TenantHeader TenantContext tenant) {

        return input.map(request -> {
            if (request.message() == null
                    || request.message().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "message is required");
            }

            EchoView view = new EchoView(
                    tenant.id(), request.message().trim());

            return ResponseEntity.status(HttpStatus.CREATED)
                    .header("X-Handler", "orders")
                    .body(view);
        });
    }
}

record OrderView(
        @JsonProperty("order_code") String orderCode,
        String tenant,
        String status) {
}

record EchoRequest(String message) {
}

record EchoView(String tenant, String message) {
}
~~~

Ở GET:

- Path "ord-0042" được Formatter đổi thành OrderCode("ORD-0042").
- @TenantHeader lấy header X-Tenant-Id: Shop-A và tạo TenantContext("shop-a").
- Controller trả ResponseEntity status 200, header X-Handler và OrderView.
- Jackson dùng @JsonProperty("order_code") để đặt tên field JSON.

Ở POST:

- @RequestBody Mono<EchoRequest> được WebFlux JSON reader xử lý, **không** đi qua OrderCodeFormatter.
- Custom TenantHeaderResolver vẫn tạo tenant argument.
- Nếu message null hoặc blank, ResponseStatusException dẫn đến HTTP 400 trước khi tạo EchoView.
- Nếu hợp lệ, controller trả HTTP 201 cùng body JSON sau khi trim.

### 15.10 ResponseHeadersFilter.java

~~~java
package com.example.customwebflux;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class ResponseHeadersFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-WebFlux-Custom", "enabled");
            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
~~~

WebFilter này chỉ điều chỉnh response header, không đọc body và không tự subscribe.

**beforeCommit** đăng ký callback được chạy trước khi response commit. Đối với status/header chung hoặc correlation data, cách này hợp lý hơn việc cố sửa bytes JSON sau khi Jackson đã encode. Callback không được thực hiện blocking I/O.

## 16. Chạy ví dụ và xem kết quả

### 16.1 Build và khởi động

Trong thư mục project:

~~~bash
gradle clean test bootRun
~~~

Lệnh giả định đã cài Gradle tương thích với Spring Boot 3.3. Với project có Gradle wrapper, thay gradle bằng ./gradlew hoặc gradlew.bat.

### 16.2 GET với formatter và resolver

~~~bash
curl -i 'http://127.0.0.1:8080/api/orders/ord-0042' \
  -H 'X-Tenant-Id: Shop-A'
~~~

HTTP status kỳ vọng: 200 OK.

Các header ứng dụng kỳ vọng:

~~~text
X-Handler: orders
X-WebFlux-Custom: enabled
~~~

JSON body tương đương:

~~~json
{"order_code":"ORD-0042","tenant":"shop-a","status":"ready"}
~~~

Không khẳng định thứ tự các JSON fields hay tất cả HTTP headers của Reactor Netty vì codec/server có thể quyết định cách ghi.

### 16.3 POST với JSON reader và status 201

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/orders/echo' \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: shop-a' \
  -d '{"message":"  hello WebFlux  "}'
~~~

Kỳ vọng HTTP 201 Created và body tương đương:

~~~json
{"tenant":"shop-a","message":"hello WebFlux"}
~~~

Thao tác trim trong controller diễn ra **sau** khi body JSON được decoded thành EchoRequest. Đây không phải công việc của FormatterRegistry.

### 16.4 Thiếu header tenant

~~~bash
curl -i 'http://127.0.0.1:8080/api/orders/ord-0042'
~~~

Kỳ vọng HTTP 400 Bad Request vì custom argument resolver trả Mono.error(ResponseStatusException). Body lỗi mặc định của Boot thay đổi theo config và phiên bản; không dự đoán chính xác JSON error body khi chưa cấu hình error contract.

### 16.5 Mã đơn hàng sai định dạng

~~~bash
curl -i 'http://127.0.0.1:8080/api/orders/nope' \
  -H 'X-Tenant-Id: shop-a'
~~~

Kỳ vọng HTTP 400 Bad Request từ lỗi chuyển kiểu path variable trước controller. Không cần tạo OrderController.find(...) để nhận chuỗi "nope" rồi tự validate ở đó.

### 16.6 JSON body sai định dạng hoặc Content-Type

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/orders/echo' \
  -H 'Content-Type: text/plain' \
  -H 'X-Tenant-Id: shop-a' \
  -d 'plain text'
~~~

Endpoint khai báo consumes=application/json, nên request dạng text/plain thường nhận 415 Unsupported Media Type theo cơ chế matching/content type của WebFlux.

Các status này là **kết quả dự kiến suy ra từ mã và cấu hình**, không phải log của một lần chạy đã được thực thi trong tài liệu.

## 17. Integration test có thể chạy trên port động

File WebFluxCustomizationTests.java:

~~~java
package com.example.customwebflux;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebFluxCustomizationTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void formatterResolverAndJsonResponseWorkTogether() {
        client().get()
                .uri("/api/orders/ord-0042")
                .header("X-Tenant-Id", "Shop-A")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Handler", "orders")
                .expectHeader().valueEquals(
                        "X-WebFlux-Custom", "enabled")
                .expectBody()
                .jsonPath("$.order_code").isEqualTo("ORD-0042")
                .jsonPath("$.tenant").isEqualTo("shop-a")
                .jsonPath("$.status").isEqualTo("ready");
    }

    @Test
    void missingCustomArgumentGetsBadRequest() {
        client().get()
                .uri("/api/orders/ord-0042")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidFormattedPathGetsBadRequest() {
        client().get()
                .uri("/api/orders/nope")
                .header("X-Tenant-Id", "shop-a")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void jsonBodyAndResponseStatusCanBeCustomized() {
        client().post()
                .uri("/api/orders/echo")
                .header("X-Tenant-Id", "shop-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "  hello WebFlux  "))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueEquals("X-Handler", "orders")
                .expectHeader().valueEquals(
                        "X-WebFlux-Custom", "enabled")
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("shop-a")
                .jsonPath("$.message").isEqualTo("hello WebFlux");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

- WebTestClient.bindToServer gửi request thật qua HTTP tới embedded server; test kiểm chứng cả formatter, custom argument resolver, Jackson JSON và response headers.
- RANDOM_PORT tránh va chạm cố định với port 8080 trong CI.
- Test kiểm chứng dữ liệu không nên phụ thuộc thứ tự JSON fields.
- Một test chỉ dùng bindToController hoặc mock context có thể xác minh logic WebFlux nhưng **không** kiểm chứng network adapter thực tế.
- Nếu ứng dụng dùng spring-boot-starter-web và Boot chọn Servlet MVC, cần sửa dependency/web application type trước khi kết luận điểm cấu hình WebFlux bị lỗi.

## 18. Tùy chỉnh response content theo phạm vi nhỏ hơn

### 18.1 Trên từng endpoint: DTO và ResponseEntity

Cách dễ bảo trì nhất:

- Tạo DTO riêng cho public API, tránh expose entity persistence trực tiếp.
- Dùng ResponseEntity khi cần status và headers.
- Dùng Jackson annotations cho tên field, định dạng timestamp hoặc thuộc tính cần ẩn.
- Dùng trường hợp thành công/lỗi có contract riêng, không chèn thông tin vào JSON bằng string concatenation.

Ví dụ:

~~~java
record PublicOrder(
        @JsonProperty("order_code") String orderCode,
        @JsonProperty("display_name") String displayName) {
}
~~~

Snippet này cần import JsonProperty; bản thân DTO không phải server hay endpoint. Formatter<OrderCode> sẽ không tự chỉnh tên JSON field.

### 18.2 Với mọi endpoint: policy ở JSON mapper/codec

Nếu ứng dụng muốn áp dụng quy tắc null inclusion, naming strategy hoặc Java Time format nhất quán, ưu tiên cấu hình Jackson/Boot theo mục tiêu đó. Có thể dùng properties như:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

Tên property và khả năng tương thích cần được đối chiếu với Spring Boot đang dùng. Việc loại null field trong JSON khác với thay đổi cách format query/path parameter; đừng dùng FormatterRegistry để đạt mục tiêu serialization.

### 18.3 Thêm một HTTP header chung

Dùng WebFilter hoặc một thành phần server response được thiết kế riêng. Ví dụ ở mục 15 dùng beforeCommit. Nếu chỉ một controller cần header, ResponseEntity là đủ; không cần filter toàn cục.

### 18.4 Response wrapper

Nếu cần mọi response có cấu trúc như data/error/meta, hãy cân nhắc:

- Dùng response DTO rõ ràng ở service/controller boundary.
- Tạo helper/factory để giảm lặp ResponseEntity.
- Với API functional, dùng ServerResponse rõ ràng.
- Chỉ xây một HandlerResultHandler chuyên biệt nếu contract return type thực sự mới và bạn có thể kiểm soát precedence so với built-in handlers.

**Spring WebFlux không nên được giả định có ResponseBodyAdvice của Spring MVC với cùng cơ chế.** Đừng lấy mẫu ResponseBodyAdvice từ org.springframework.web.servlet rồi coi đó là hook tổng quát cho WebFlux. Nếu cần biến đổi JSON body toàn cục, đánh giá chiến lược ở DTO/serialization/codec layer hoặc wrapper return type phù hợp, tránh filter đọc-ghi lại toàn bộ body.

### 18.5 Vì sao không nên sửa JSON body bằng WebFilter?

Response body trên WebFlux là reactive stream DataBuffer. Muốn intercept và sửa bytes phải decorate ServerHttpResponse rồi xử lý:

- Content-Length và transfer encoding.
- Media type và charset.
- Streaming, SSE, chunked data, compression.
- DataBuffer pooled memory và release/retain.
- Backpressure, cancellation và error signal.
- Trường hợp response đã commit.

Đây là bài toán hạ tầng nâng cao, **không phù hợp** cho một policy đơn giản như đổi tên field JSON hoặc thêm header. Cách đó vừa tăng memory/latency vừa có nguy cơ hỏng payload.

## 19. Nội dung trả về dạng streaming

Ví dụ endpoint Server-Sent Events:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> events() {
    return Flux.just("one", "two", "three");
}
~~~

Đây là method minh họa trong @RestController với imports Flux, GetMapping và MediaType.

Với text/event-stream, framework dùng message writers phù hợp để stream dữ liệu theo quy tắc của media type. Đừng thay thế codec hoặc wrapper sao cho nó buộc tập hợp toàn bộ Flux thành một List mới trả, vì sẽ mất khả năng streaming và ảnh hưởng backpressure.

Nếu cần status/header cho stream:

~~~java
public Mono<ResponseEntity<Flux<String>>> eventsWithHeaders() {
    return Mono.just(ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(Flux.just("one", "two")));
}
~~~

Đoạn này mô tả cách điều khiển response metadata trước body streaming; chưa phải một class độc lập. Thực tế có thể dùng ResponseEntity<Flux<String>> trực tiếp hoặc Mono<ResponseEntity<Flux<String>>> theo API mong muốn.

Một Formatter hay custom argument resolver không đảm bảo thứ tự/chunk hoặc termination của stream. Phần đó thuộc Publisher, codecs và ServerHttpResponse.

## 20. Validation và exception handling khi tùy chỉnh

### 20.1 Bad request từ formatting

Khi OrderCodeFormatter.parse từ chối URL không hợp lệ, framework có thể gửi 400 do type conversion error. Cần kiểm tra error resolution thực tế trong ứng dụng có @ControllerAdvice hay WebExceptionHandler riêng.

### 20.2 Bad request từ argument resolver

TenantHeaderResolver trong ví dụ dùng ResponseStatusException(BAD_REQUEST). Điều này rõ ràng hơn throw IllegalStateException chung rồi kỳ vọng framework luôn suy ra 400.

### 20.3 Validation của JSON body

Trong WebFlux, @Valid @RequestBody DTO có thể kích hoạt Jakarta Bean Validation nếu có provider. Với Spring Boot, khi cần hỗ trợ Jakarta validation, thường thêm:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Không mặc định starter-webflux luôn bao gồm đầy đủ validation provider. Với @RequestBody Mono<DTO>, cách áp dụng validation trong reactive pipeline có những quy tắc riêng; cần test cả trường hợp invalid và xem exception cụ thể theo Spring Framework version.

### 20.4 Error contract

@RestControllerAdvice và @ExceptionHandler xử lý những lỗi phù hợp với annotated controllers; WebExceptionHandler có thể dùng cho một số lỗi ở WebHandler chain. Đừng expose internal exception message chứa token hoặc thông tin hạ tầng.

Nếu response headers đã commit, exception handler không thể tùy ý đổi status hoặc dựng một JSON lỗi mới mà không gây response hỏng. Đặc biệt với Flux streaming, phải xem cả cancellation/error behavior.

## 21. Debug khi formatter hoặc resolver không chạy

### 21.1 Formatter có được gọi không?

Kiểm tra:

1. Ứng dụng có đúng WebFlux reactive stack?
2. Lớp @Configuration implements WebFluxConfigurer có nằm trong component scan?
3. addFormatters có thực sự đăng ký đúng Formatter<T>?
4. Controller argument là đúng kiểu T, và input đi qua cơ chế data binding/conversion?
5. Có Converter khác chiếm precedence hoặc annotation built-in xử lý trước không?
6. Đầu vào path/query có đúng regex, Locale và quy tắc trim?
7. Lỗi xảy ra khi mapping hay khi convert sau mapping?
8. Test bằng WebTestClient với cả input hợp lệ và sai định dạng.

### 21.2 Custom argument resolver có được gọi không?

Kiểm tra:

1. Dùng đúng interface reactive HandlerMethodArgumentResolver.
2. Overridden method là WebFluxConfigurer.configureArgumentResolvers, không phải WebMvcConfigurer.addArgumentResolvers.
3. Đúng package ArgumentResolverConfigurer của Spring WebFlux.
4. supportsParameter trả true cho tham số thực tế.
5. Controller có @TenantHeader và TenantContext đúng kiểu.
6. Resolver có bị built-in resolver khác nhận tham số trước không?
7. Mono<Object> có trả đúng đối tượng, không subscribe() thủ công và không block()?
8. Header X-Tenant-Id có được proxy/security layer chuyển qua không?
9. Authorization policy có tin cậy giá trị tenant không?

### 21.3 JSON output không đổi như mong muốn?

Kiểm tra:

1. Controller có @RestController/@ResponseBody hoặc return type thích hợp?
2. ResponseEntity có status/header/body đúng?
3. Media type của request Accept và endpoint produces có tương thích?
4. Jackson có trên classpath và DTO annotations có đúng?
5. @JsonProperty đang áp vào field/getter/record component phù hợp?
6. ObjectMapper do Boot tạo có bị custom codec thay thế không?
7. Response đã commit trước khi filter định đặt header chưa?
8. Có reverse proxy hoặc WebFilter sửa header/body sau đó không?
9. Có custom serializer, Jackson mixin, JSON view hoặc naming strategy ảnh hưởng không?
10. Với stream, codec có đang buffer/aggregate ngoài ý muốn không?

### Log và breakpoint

Trong môi trường local/test, có thể xem:

~~~properties
logging.level.org.springframework.web.reactive.DispatcherHandler=DEBUG
logging.level.org.springframework.web.reactive.result.method.annotation=TRACE
logging.level.org.springframework.web.server.adapter.HttpWebHandlerAdapter=DEBUG
~~~

Khi cần xác minh chính xác thứ tự resolution, đặt breakpoint trong RequestMappingHandlerAdapter, InvocableHandlerMethod và custom OrderCodeFormatter/TenantHeaderResolver của bạn. TRACE có thể lộ thông tin request metadata; không bật tràn lan ở production.

## 22. Những lỗi thiết kế cần tránh

- **Dùng WebMvcConfigurer trong một ứng dụng muốn chạy WebFlux**: phương thức và SPI có thể không áp dụng cho WebFlux server.
- **Thêm @EnableWebFlux vô điều kiện**: làm thay đổi quyền kiểm soát cấu hình của Boot, dễ mất một số auto-configuration mong đợi.
- **Dùng Formatter để chỉnh JSON**: FormatterRegistry chủ yếu phục vụ type conversion/binding, còn JSON do HTTP codecs/Jackson quản lý.
- **Custom resolver trả Object thay vì Mono<Object>**: không khớp interface WebFlux.
- **supportsParameter quá rộng**: có thể đụng built-in resolver, làm hỏng method arguments khác.
- **Gọi .block() trong argument resolver**: gây nghẽn event loop, giảm khả năng mở rộng.
- **Lấy X-Tenant-Id từ client rồi coi đó là authorization**: dễ mở lỗi truy cập chéo tenant.
- **Tự subscribe() vào body hoặc response**: tách Publisher khỏi request lifecycle, gây race và mất error/cancellation propagation.
- **Thay toàn bộ codecs** để chỉnh một JSON field: rủi ro mất form/multipart/string readers-writers.
- **Tưởng maxInMemorySize là giới hạn toàn bộ HTTP request**: nó phụ thuộc hoạt động buffering của từng codec.
- **Giữ DataBuffer sau khi response commit**: có thể gây memory leak hoặc đọc buffer đã release.
- **Sửa status/header sau commit**: có thể không còn hiệu lực hoặc gây lỗi.
- **Áp dụng Servlet ResponseBodyAdvice như một hook WebFlux tương đương**: nhầm stack và extension semantics.
- **So sánh JSON bằng thứ tự field**: JSON object key order không phải contract nên test theo giá trị từng field.
- **Chỉ test bằng direct controller call**: không kiểm chứng binding, argument resolver, codecs và HTTP result handling.

## 23. Checklist triển khai

1. Xác nhận Boot đang dùng **WebApplicationType.REACTIVE** và server đúng stack.
2. Chọn Formatter/Converter cho chuyển đổi giá trị path/query/field đơn giản.
3. Chọn custom reactive HandlerMethodArgumentResolver cho đối số cần phối hợp request metadata.
4. Đặt annotation và kiểu đối số riêng biệt; tránh chiếm built-in arguments.
5. Đăng ký cả hai qua WebFluxConfigurer, không dùng nhầm MVC SPI.
6. Dùng DTO/ResponseEntity/Jackson để xác định status, headers và body contract.
7. Dùng ServerCodecConfigurer cho codec settings; ưu tiên properties của Boot nếu đủ.
8. Chỉ dùng WebFilter khi tính năng thật sự là cross-cutting middleware.
9. Không tự subscribe/block hoặc nuốt reactive errors.
10. Tách validation định dạng khỏi authorization nghiệp vụ.
11. Test với WebTestClient, cả valid/invalid inputs và response headers.
12. Kiểm thử streaming và large body khi đổi codec/memory settings.
13. Kiểm tra Content-Type/Accept, HTTP 400/415/406 và response commit.
14. Theo dõi latency, blocking và memory khi thêm custom extension.
15. Giữ configuration nhỏ, có chủ đích và documented theo đúng phiên bản Spring đang chạy.

## 24. Tóm tắt

Trong Spring WebFlux, **FormatterRegistry** xử lý việc chuyển đổi một giá trị request sang kiểu Java; **ArgumentResolverConfigurer** thêm logic tạo một tham số controller từ ServerWebExchange; còn **HandlerResultHandler và HTTP message codecs** chịu trách nhiệm biểu diễn kết quả thành HTTP response.

Ví dụ OrderCodeFormatter, TenantHeaderResolver và OrderController cho thấy cả ba có thể phối hợp mà không thay DispatcherHandler, không tự tạo HttpHandler và không cần custom Reactor Netty server. Nơi nào cần chỉnh status/header thì dùng ResponseEntity/WebFilter; nơi nào cần chỉnh JSON thì dùng DTO/Jackson hoặc codec khi thực sự cần. Khi hiểu ranh giới các tầng, việc tùy chỉnh sẽ có thể kiểm thử độc lập, tránh side effect và giữ nguyên tính reactive của request pipeline.

## 25. Tài liệu tham khảo

- Spring Framework 6.1 — WebFlux Config: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/config.html
- Spring Framework 6.1 — WebFluxConfigurer Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html
- Spring Framework 6.1 — ArgumentResolverConfigurer Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/method/annotation/ArgumentResolverConfigurer.html
- Spring Framework 6.1 — Reactive HandlerMethodArgumentResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/method/HandlerMethodArgumentResolver.html
- Spring Framework — WebFlux Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework — WebFlux HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/config.html#webflux-config-message-codecs
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
