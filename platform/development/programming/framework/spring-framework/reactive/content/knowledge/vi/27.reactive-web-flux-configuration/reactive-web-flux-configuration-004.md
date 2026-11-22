# Phân giải media type và đăng ký đối số handler tùy biến

Trong Spring WebFlux, một endpoint có thể nhận nhiều định dạng request và trả nhiều định dạng response. Spring phải xác định client gửi body theo định dạng nào, client muốn nhận định dạng nào, codec nào có thể đọc hoặc ghi định dạng đó và controller cần những đối số nào.

Hai cơ chế thường xuất hiện cùng nhau trong cấu hình WebFlux nhưng giải quyết hai việc khác nhau:

- **Phân giải media type** xác định định dạng response mà client yêu cầu, thường dựa trên header `Accept`. Với annotated controller, WebFlux mặc định chỉ xét `Accept`; có thể bổ sung chiến lược query parameter như `?format=json` bằng `RequestedContentTypeResolverBuilder`.
- **Handler method argument resolver** tạo giá trị cho một tham số trong method controller. Ví dụ, ứng dụng có thể tạo `TenantContext` từ header `X-Tenant-Id` và inject vào tham số được đánh dấu `@CurrentTenant`.

Cần phân biệt hai cơ chế trên với `Content-Type` của request, `consumes`/`produces` trong mapping và HTTP message codecs. Media type resolver quyết định client muốn nhận gì; codec đọc/ghi body; custom argument resolver chuẩn bị một tham số cho controller.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Content-Type` và `Accept`.
2. Giải thích vai trò của `consumes`, `produces`, `HttpMessageReader` và `HttpMessageWriter`.
3. Mô tả cách WebFlux chọn requested media type cho annotated controller.
4. Dùng `RequestedContentTypeResolverBuilder` để ưu tiên query parameter hoặc header.
5. Hiểu thứ tự resolver và ý nghĩa của `MediaType.ALL`.
6. Phân biệt content type resolver với codec và argument resolver.
7. Triển khai `HandlerMethodArgumentResolver` reactive của WebFlux.
8. Đăng ký custom resolver bằng `WebFluxConfigurer.configureArgumentResolvers` và `ArgumentResolverConfigurer`.
9. Thiết kế annotation cho một tham số controller tùy biến.
10. Xử lý thiếu header, lỗi validation và lookup bất đồng bộ mà không block event loop.
11. Biết khi nào nên dùng Converter/Formatter, `@RequestBody`, codec hoặc custom argument resolver.
12. Kiểm thử Accept, query format, 406, 415 và custom argument bằng WebTestClient.

## 2. Media type trong HTTP

Media type mô tả định dạng nội dung HTTP. Một media type có dạng:

~~~text
type/subtype; parameter=value
~~~

Ví dụ:

~~~http
Content-Type: application/json
Accept: application/json
~~~

Một số media type phổ biến:

| Media type | Nội dung thường gặp |
| --- | --- |
| `application/json` | JSON object hoặc array |
| `application/xml` | XML document |
| `text/plain` | Văn bản thuần |
| `text/html` | HTML |
| `application/octet-stream` | Dữ liệu nhị phân |
| `application/x-www-form-urlencoded` | Form URL-encoded |
| `multipart/form-data` | Form nhiều part, có thể có file |
| `text/event-stream` | Server-Sent Events |
| `application/x-ndjson` | Các JSON record phân tách bằng newline |

Media type có thể có tham số, ví dụ `application/json;charset=UTF-8`. HTTP layer và codec cần xử lý đúng media type cùng các tham số tương thích.

### 2.1. Content-Type: client đã gửi gì?

`Content-Type` mô tả định dạng của request body:

~~~http
POST /api/messages
Content-Type: application/json

{"text":"hello"}
~~~

WebFlux dùng thông tin này để chọn `HttpMessageReader` phù hợp với kiểu tham số controller. Với `@RequestBody Message`, JSON reader có thể giải mã byte JSON thành object `Message`.

Nếu endpoint khai báo `consumes = "application/json"` nhưng client gửi `text/plain`, request không thỏa điều kiện mapping và thường nhận `415 Unsupported Media Type`.

`Content-Type` không phải header dùng để chọn định dạng response.

### 2.2. Accept: client muốn nhận gì?

`Accept` mô tả các media type mà client có thể nhận:

~~~http
GET /api/messages/42
Accept: application/json
~~~

WebFlux dùng requested media types để chọn mapping `produces` và định dạng response. Khi controller trả object, `HttpMessageWriter` tương ứng sẽ encode object thành body.

Nếu endpoint chỉ tạo được `application/json` mà client yêu cầu `text/csv`, request có thể nhận `406 Not Acceptable`.

`Accept` không mô tả định dạng body của request. Một request POST có thể gửi JSON bằng `Content-Type` nhưng yêu cầu response bằng một media type khác qua `Accept`.

### 2.3. Bảng phân biệt

| Thành phần | Câu hỏi | Nơi sử dụng |
| --- | --- | --- |
| `Content-Type` | Request body đang ở định dạng nào? | Đọc request body |
| `Accept` | Client muốn nhận response định dạng nào? | Content negotiation cho response |
| `consumes` | Handler chấp nhận request body dạng nào? | Điều kiện chọn handler |
| `produces` | Handler có thể tạo response dạng nào? | Điều kiện chọn handler |
| `HttpMessageReader` | Đọc byte request thành object nào? | Decode request |
| `HttpMessageWriter` | Encode object thành byte response ra sao? | Ghi response |
| `RequestedContentTypeResolver` | Requested media types của response là gì? | Annotated controller |
| `HandlerMethodArgumentResolver` | Giá trị của tham số controller được tạo thế nào? | Gọi handler method |

## 3. Luồng xử lý media type trong WebFlux

Ở mức khái quát, annotated controller đi qua các bước:

~~~text
HTTP request
   |
   +--> path, method, params, headers
   |
   +--> Content-Type + consumes
   |       |
   |       +--> chọn handler phù hợp
   |
   +--> Accept / requested media type
   |       |
   |       +--> produces condition
   |       |
   |       +--> chọn response representation
   |
   +--> HandlerMethodArgumentResolver
   |       |
   |       +--> tạo các tham số controller
   |
   +--> Controller method
   |
   +--> HttpMessageWriter
           |
           +--> encode response theo media type đã chọn
~~~

Đây là sơ đồ rút gọn. Việc chọn handler còn xét HTTP method, path, query conditions và header conditions. Các đối số controller được resolve theo từng tham số. Request body thường do resolver tích hợp với `HttpMessageReader` xử lý; response body được ghi bằng `HttpMessageWriter`.

### 3.1. RequestMapping: consumes và produces

Ví dụ:

~~~java
@PostMapping(
    path = "/messages",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Message> create(@RequestBody Mono<Message> body) {
    return body;
}
~~~

- `consumes` giới hạn media type của request body.
- `produces` mô tả media type mà handler có thể trả.
- `@RequestBody` dùng message reader để giải mã request.
- `Mono<Message>` được ghi qua message writer phù hợp.

Một endpoint có thể khai báo nhiều media type:

~~~java
@GetMapping(
    path = "/export",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.TEXT_PLAIN_VALUE
    }
)
~~~

Tuy nhiên, khai báo `produces` không tự cài đặt codec. Phải có writer hỗ trợ kiểu Java và media type được chọn. Nếu không có writer phù hợp, response không thể được encode.

### 3.2. 406 và 415

| Status | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| 406 Not Acceptable | Không có representation phù hợp với Accept/produces hoặc writer không hỗ trợ | Accept, produces, writer |
| 415 Unsupported Media Type | Content-Type không được consumes hoặc không có reader hỗ trợ | Content-Type, consumes, reader |
| 400 Bad Request | Body không hợp lệ hoặc argument validation thất bại | JSON syntax, conversion, validation |
| 500 Internal Server Error | Lỗi không được xử lý trong resolver/controller/codec | Exception gốc và error handler |

Không nên xử lý mọi lỗi media type bằng cách tăng danh sách codec một cách tùy tiện. Trước hết xác định lỗi nằm ở request mapping, content negotiation hay khả năng encode/decode.

## 4. RequestedContentTypeResolver trong WebFlux

WebFlux sử dụng `RequestedContentTypeResolver` để xác định danh sách media type mà client yêu cầu cho response của annotated controller.

Mặc định, resolver kiểm tra header `Accept`. Nếu request không gửi Accept cụ thể, kết quả có thể là `MediaType.ALL`, nghĩa là client không giới hạn định dạng response.

WebFlux dùng các kiểu thuộc package:

~~~text
org.springframework.web.reactive.accept
~~~

Các thành phần quan trọng:

- `RequestedContentTypeResolver`: hợp đồng resolve requested media types từ `ServerWebExchange`.
- `HeaderContentTypeResolver`: đọc header Accept.
- `ParameterContentTypeResolver`: đọc query parameter và ánh xạ key sang MediaType.
- `FixedContentTypeResolver`: trả về danh sách media type cố định.
- `RequestedContentTypeResolverBuilder`: ghép nhiều resolver theo thứ tự.

### 4.1. Mặc định chỉ dùng Accept

Nếu không cấu hình resolver riêng, builder mặc định thêm `HeaderContentTypeResolver`. Vì vậy client có thể yêu cầu:

~~~http
Accept: application/json
~~~

Nếu client không gửi Accept cụ thể, resolver thường trả `MediaType.ALL`. Điều này cho phép handler chọn một representation phù hợp với mapping và writer hiện có.

### 4.2. Thêm query parameter format

Một số API muốn chọn định dạng bằng query parameter:

~~~text
GET /api/report?format=json
~~~

WebFlux cung cấp `parameterResolver()` để ánh xạ giá trị query parameter sang media type:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureContentTypeResolver(
            RequestedContentTypeResolverBuilder builder) {

        builder.parameterResolver()
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON)
            .mediaType("txt", MediaType.TEXT_PLAIN);

        builder.headerResolver();
    }
}
~~~

Ở đây `format=json` được ánh xạ sang `application/json` và `format=txt` sang `text/plain`. Nếu query parameter không cung cấp một media type cụ thể, resolver tiếp theo là header resolver có thể xử lý Accept.

**Lưu ý thứ tự:** builder là một composite resolver. Resolver đầu tiên trả về danh sách media type cụ thể, không phải chỉ `MediaType.ALL`, sẽ được dùng. Ví dụ trên ưu tiên query parameter trước header Accept. Nếu muốn Accept ưu tiên, đăng ký `headerResolver()` trước `parameterResolver()`.

Khi đã tự thêm resolver, hãy khai báo cả những chiến lược mà ứng dụng vẫn muốn hỗ trợ. Đừng mặc định rằng header resolver luôn được tự động thêm sau một resolver tùy biến.

### 4.3. Cấu hình thứ tự có chủ đích

Ưu tiên Accept:

~~~java
@Override
public void configureContentTypeResolver(
        RequestedContentTypeResolverBuilder builder) {

    builder.headerResolver();

    builder.parameterResolver()
        .parameterName("format")
        .mediaType("json", MediaType.APPLICATION_JSON)
        .mediaType("txt", MediaType.TEXT_PLAIN);
}
~~~

Ưu tiên query parameter:

~~~java
@Override
public void configureContentTypeResolver(
        RequestedContentTypeResolverBuilder builder) {

    builder.parameterResolver()
        .parameterName("format")
        .mediaType("json", MediaType.APPLICATION_JSON)
        .mediaType("txt", MediaType.TEXT_PLAIN);

    builder.headerResolver();
}
~~~

Hai cấu hình có thể cho kết quả khác nhau khi request đồng thời có `?format=json` và `Accept: text/plain`. Hãy chọn một chính sách và kiểm thử rõ ràng.

### 4.4. Query parameter resolver nên dùng allowlist

Nên map các key được phép:

~~~java
builder.parameterResolver()
    .parameterName("format")
    .mediaType("json", MediaType.APPLICATION_JSON)
    .mediaType("txt", MediaType.TEXT_PLAIN);
~~~

Client gửi key đã đăng ký như `json` hoặc `txt`. Không nên nhận một chuỗi bất kỳ rồi parse trực tiếp thành media type tùy ý. Allowlist giúp API có hợp đồng ổn định và tránh việc client yêu cầu một định dạng mà server không hỗ trợ.

### 4.5. Không nhầm format query với request body Content-Type

`?format=json` là một chiến lược chọn requested response media type khi đã cấu hình. Nó không biến request body thành JSON và không thay thế header Content-Type.

Ví dụ:

~~~http
POST /api/messages?format=json
Content-Type: application/x-www-form-urlencoded
Accept: text/plain

text=hello
~~~

Body vẫn là form URL-encoded. Query format có thể tham gia chọn response media type theo thứ tự resolver đã cấu hình. `Content-Type` vẫn mô tả body form.

## 5. Media type, codec và message reader/writer

Content type resolver không giải mã JSON và cũng không encode response. Việc chuyển đổi byte/object thuộc HTTP message codecs.

### 5.1. Request: HttpMessageReader

Một request body đi vào WebFlux dưới dạng byte stream. Reader phù hợp được chọn dựa trên kiểu tham số và Content-Type:

~~~text
HTTP request bytes
      |
      v
Content-Type: application/json
      |
      v
HttpMessageReader<Message>
      |
      v
Message object
      |
      v
Controller
~~~

Ví dụ:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<Message> create(@RequestBody Mono<Message> message) {
    return message;
}
~~~

JSON reader giải mã body thành `Message`. Nếu cần định dạng mới, đăng ký codec/reader tương ứng bằng `ServerCodecConfigurer`; chỉ thêm media type vào content resolver là chưa đủ.

### 5.2. Response: HttpMessageWriter

Response đi theo chiều ngược lại:

~~~text
Controller result
      |
      v
Requested media type
      |
      v
HttpMessageWriter<Message>
      |
      v
HTTP response bytes
~~~

Ví dụ controller trả `Mono<Message>` và client yêu cầu application/json. JSON writer encode object thành JSON bytes.

### 5.3. Ba cấu hình giải quyết ba bài toán

| API cấu hình | Trách nhiệm |
| --- | --- |
| `configureContentTypeResolver` | Xác định requested media type của response |
| `configureHttpMessageCodecs` | Đăng ký/cấu hình reader và writer để đọc/ghi body |
| `configureArgumentResolvers` | Đăng ký resolver cho tham số custom trong controller |

Ví dụ codec:

~~~java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {

    configurer.defaultCodecs()
        .maxInMemorySize(512 * 1024);
}
~~~

Ví dụ argument resolver:

~~~java
@Override
public void configureArgumentResolvers(
        ArgumentResolverConfigurer configurer) {

    configurer.addCustomResolver(
        new CurrentTenantArgumentResolver()
    );
}
~~~

Không dùng custom argument resolver chỉ để thêm một JSON codec; cũng không dùng content type resolver để inject một đối tượng request context.

## 6. HandlerMethodArgumentResolver của WebFlux

Controller method có thể nhận path variable, request parameter, header, principal, session, request body, exchange hoặc một kiểu ứng dụng riêng.

Spring có sẵn các argument resolver cho kiểu phổ biến. Khi cần kiểu đặc thù của ứng dụng, có thể triển khai `HandlerMethodArgumentResolver` của WebFlux.

Interface reactive của WebFlux nằm tại:

~~~java
org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver
~~~

Hai phương thức chính:

~~~java
boolean supportsParameter(MethodParameter parameter);

Mono<Object> resolveArgument(
    MethodParameter parameter,
    BindingContext bindingContext,
    ServerWebExchange exchange
);
~~~

### 6.1. supportsParameter

Phương thức này quyết định resolver có chịu trách nhiệm cho tham số đang xét hay không.

Nên kiểm tra thật cụ thể:

- Annotation đánh dấu tham số.
- Kiểu Java chính xác mà resolver hỗ trợ.
- Generic type nếu resolver hỗ trợ collection hoặc reactive wrapper.

Không viết resolver nhận mọi tham số kiểu Object hoặc String. Resolver quá rộng có thể tranh quyền với resolver mặc định hoặc làm hành vi controller khó dự đoán.

### 6.2. resolveArgument

Phương thức này tạo giá trị cho tham số và trả về `Mono<Object>`.

Nguồn dữ liệu có thể là header/query parameter, request attribute, principal/session, reactive repository/service hoặc giá trị được tính từ `ServerWebExchange`.

Nếu cần gọi service reactive, trả publisher của service. Không gọi `block()` để đợi dữ liệu. Nếu thiếu dữ liệu bắt buộc, trả `Mono.error(...)` với exception phù hợp; không trả object giả hoặc dùng `Mono.empty()` khi controller cần một giá trị không-null.

### 6.3. BindingContext và ServerWebExchange

`ServerWebExchange` cung cấp request, response, attributes, session và thông tin liên quan tới request hiện tại.

`BindingContext` cung cấp ngữ cảnh data binding cho controller invocation. Một resolver đơn giản chỉ đọc header có thể không cần dùng bindingContext; vẫn phải khai báo tham số theo đúng SPI.

### 6.4. Đăng ký qua ArgumentResolverConfigurer

Dùng `WebFluxConfigurer.configureArgumentResolvers`:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}
~~~

`addCustomResolver` thêm resolver hỗ trợ các tham số tùy biến. Đây là cơ chế bổ sung custom resolver, không phải cách thay thế các resolver built-in hiện có.

Nếu cần thay đổi cách Spring resolve một kiểu đối số built-in, phải xem xét advanced WebFlux configuration và `RequestMappingHandlerAdapter`; không dùng custom resolver thông thường với kỳ vọng nó ghi đè resolver mặc định.

### 6.5. Không dùng nhầm SPI của Spring MVC

Spring MVC và Spring WebFlux có interface cùng tên nhưng thuộc package khác nhau.

| Stack | Interface |
| --- | --- |
| Spring MVC | `org.springframework.web.method.support.HandlerMethodArgumentResolver` |
| Spring WebFlux | `org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver` |

SPI MVC trả giá trị đồng bộ và nhận `NativeWebRequest`/`ModelAndViewContainer`. SPI WebFlux trả `Mono<Object>` và nhận `BindingContext`/`ServerWebExchange`.

Dùng nhầm interface sẽ không biên dịch với `ArgumentResolverConfigurer` của WebFlux hoặc không hoạt động theo lifecycle reactive.

## 7. Thiết kế custom argument resolver

Ví dụ ứng dụng cần lấy tenant hiện tại từ header `X-Tenant-Id`. Nhiều controller cần cùng một đối tượng `TenantContext`.

Nếu controller nào cũng tự đọc header, kiểm tra rỗng và chuẩn hóa tenant ID, logic đó sẽ bị lặp. Custom argument resolver cho phép controller khai báo:

~~~java
@GetMapping("/greeting")
Mono<Greeting> greeting(@CurrentTenant TenantContext tenant) {
    return Mono.just(new Greeting("hello", tenant.id()));
}
~~~

### 7.1. Annotation đánh dấu

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface CurrentTenant {}
~~~

Annotation chỉ áp dụng cho tham số method và cần runtime retention để resolver đọc được khi chạy.

### 7.2. Kiểu dữ liệu domain

~~~java
record TenantContext(String id) {}
~~~

Kiểu này đại diện tenant đã được chuẩn hóa. Ứng dụng thực tế có thể chứa tenant ID, display name hoặc metadata đã xác minh.

### 7.3. Resolver

~~~java
final class CurrentTenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
            && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String tenantId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Tenant-Id");

            if (tenantId == null || tenantId.isBlank()) {
                return Mono.error(
                    new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"
                    )
                );
            }

            TenantContext tenant =
                new TenantContext(tenantId.trim());

            return Mono.just((Object) tenant);
        });
    }
}
~~~

Resolver thực hiện các việc:

1. Chỉ nhận tham số có annotation `@CurrentTenant` và kiểu `TenantContext`.
2. Đọc header từ request hiện tại.
3. Kiểm tra header có tồn tại và không rỗng.
4. Chuẩn hóa khoảng trắng.
5. Trả TenantContext trong Mono.
6. Nếu thiếu header, phát lỗi 400 qua ResponseStatusException.

`Mono.defer` bảo đảm thao tác đọc/kiểm tra được thực hiện khi publisher được subscribe. Resolver không lưu dữ liệu request vào field của object dùng chung giữa các request.

### 7.4. Đăng ký resolver

~~~java
@Configuration
class TenantWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}
~~~

Trong ứng dụng lớn, có thể đăng ký resolver như một bean để inject service hoặc repository. Resolver có thể gọi service reactive:

~~~java
return tenantDirectory.findById(tenantId)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(
            HttpStatus.NOT_FOUND,
            "Unknown tenant"
        )
    ))
    .cast(Object.class);
~~~

`tenantDirectory.findById` ở đây là API reactive minh họa của ứng dụng. Nếu dùng database hoặc network lookup, hãy để publisher tiếp tục bất đồng bộ. Không gọi repository blocking trên event-loop.

### 7.5. Controller dùng đối số tùy biến

~~~java
record Greeting(String message, String tenantId) {}

@RestController
@RequestMapping("/api")
class GreetingController {

    @GetMapping(
        path = "/greeting",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Greeting> greeting(
            @CurrentTenant TenantContext tenant) {

        return Mono.just(
            new Greeting("hello", tenant.id())
        );
    }
}
~~~

Controller không cần biết tenant ID đến từ header hay repository. Nó nhận một kiểu đã được resolver chuẩn bị.

### 7.6. Không coi header tenant là bằng chứng authorization

Header do client gửi có thể bị giả mạo. Resolver chỉ chuẩn hóa hoặc tra cứu giá trị; nó không tự xác minh người dùng có quyền truy cập tenant đó.

Trong production:

- Xác thực principal bằng Spring Security.
- Kiểm tra tenant thuộc phạm vi mà principal được phép truy cập.
- Nếu tenant được xác định từ JWT claim hoặc security context, ưu tiên nguồn đã được xác thực thay vì tin header tự do.
- Không dùng tenant ID từ client để quyết định quyền truy cập database nếu chưa authorization.
- Trả lỗi 401/403 phù hợp khi principal hoặc quyền không hợp lệ.

Custom argument resolver là điểm thuận tiện để inject context đã xác minh, nhưng quy tắc bảo mật phải được thực hiện ở service/security layer có đủ thông tin.

## 8. Khi nào dùng argument resolver, converter hay codec?

Không phải mọi tham số tùy biến đều cần resolver mới.

| Nhu cầu | Cơ chế nên xem xét |
| --- | --- |
| Chuyển String thành enum/ID/value object | `Converter` hoặc `Formatter` qua `addFormatters` |
| Bind query/form field vào DTO | `@ModelAttribute` và WebDataBinder |
| Đọc header cụ thể | `@RequestHeader` |
| Đọc query parameter | `@RequestParam` |
| Đọc request body JSON/XML | `@RequestBody` và HttpMessageReader |
| Thêm định dạng body mới | `ServerCodecConfigurer` và custom codec |
| Inject request-scoped context theo annotation | `HandlerMethodArgumentResolver` |
| Inject principal hiện tại | Resolver có sẵn hoặc Spring Security |
| Thêm dữ liệu vào exchange trước controller | WebFilter và exchange attributes |

### 8.1. Dùng Converter/Formatter khi chỉ cần chuyển kiểu

Nếu tham số nguồn đã được Spring resolve nhưng cần chuyển đổi String sang kiểu ứng dụng, dùng converter:

~~~java
registry.addConverter(
    String.class,
    TenantId.class,
    TenantId::new
);
~~~

Đây là snippet minh họa; `TenantId` cần là kiểu value object phù hợp. Converter tập trung vào chuyển đổi giá trị. Nó không phải nơi thích hợp để truy cập request, authorization hoặc gọi repository.

### 8.2. Dùng codec khi xử lý body

Nếu cần hỗ trợ media type mới như định dạng JSON vendor hoặc binary riêng, hãy xây dựng encoder/decoder và đăng ký vào `ServerCodecConfigurer`. Custom argument resolver không nên tự đọc raw request body vì body là stream có lifecycle một lần và codec đã chịu trách nhiệm decode.

### 8.3. Dùng WebFilter khi cần request context chung

Nếu mọi request cần tenant/correlation ID và không cần annotation ở controller, có thể dùng `WebFilter` để xác thực/đọc header rồi lưu vào exchange attributes hoặc Reactor Context theo thiết kế phù hợp.

Custom argument resolver hữu ích khi muốn controller khai báo rõ tham số có ý nghĩa domain. WebFilter hữu ích khi xử lý cross-cutting ở tầng request pipeline.

## 9. Tương tác giữa media type resolver và argument resolver

Hai resolver có thể cùng được đăng ký trong một `WebFluxConfigurer`:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureContentTypeResolver(
            RequestedContentTypeResolverBuilder builder) {

        builder.parameterResolver()
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON);

        builder.headerResolver();
    }

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}
~~~

Chúng không tranh cùng một loại dữ liệu:

- Content type resolver xem query parameter hoặc Accept để xác định response media type.
- Argument resolver xem MethodParameter và ServerWebExchange để tạo TenantContext.
- Codec xử lý request/response body.
- Request mapping dùng consumes/produces để chọn handler tương thích.

Một controller có thể dùng cả hai:

~~~java
@GetMapping(
    path = "/greeting",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Greeting> greeting(
        @CurrentTenant TenantContext tenant) {
    return Mono.just(new Greeting("hello", tenant.id()));
}
~~~

Client có thể gọi:

~~~http
GET /api/greeting?format=json
X-Tenant-Id: acme
Accept: */*
~~~

Query parameter chọn requested media type; header tenant được custom argument resolver chuyển thành TenantContext. Response body được JSON writer encode.

## 10. Ví dụ Java 17 chạy được với Spring Boot WebFlux

Ví dụ hoàn chỉnh dùng Java 17, Spring Boot 3.3.5 và WebFlux. Ứng dụng có query parameter `format=json` được ánh xạ sang application/json, Accept header làm fallback, `@CurrentTenant` inject TenantContext vào controller và `@RequestBody` dùng JSON reader để echo Message.

### 10.1. Cấu trúc dự án

~~~text
webflux-media-argument-demo/
├── build.gradle
└── src/
    ├── main/java/demo/MediaTypeDemoApplication.java
    └── test/java/demo/MediaTypeDemoTest.java
~~~

### 10.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

Spring Boot quản lý phiên bản Spring Framework và Reactor tương thích thông qua dependency management. Ví dụ cố định Boot 3.3.5 để có baseline dễ tái hiện; dự án mới nên chọn patch version còn được hỗ trợ.

### 10.3. MediaTypeDemoApplication.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.BindingContext;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.accept.RequestedContentTypeResolverBuilder;
import org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver;
import org.springframework.web.reactive.result.method.annotation.ArgumentResolverConfigurer;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class MediaTypeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MediaTypeDemoApplication.class, args);
    }
}

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface CurrentTenant {}

record TenantContext(String id) {}
record Greeting(String message, String tenantId) {}
record Message(String text) {}

final class CurrentTenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
            && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String tenantId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Tenant-Id");

            if (tenantId == null || tenantId.isBlank()) {
                return Mono.error(
                    new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"
                    )
                );
            }

            return Mono.just(
                (Object) new TenantContext(tenantId.trim())
            );
        });
    }
}

@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureContentTypeResolver(
            RequestedContentTypeResolverBuilder builder) {

        builder.parameterResolver()
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON);

        builder.headerResolver();
    }

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {

        configurer.addCustomResolver(
            new CurrentTenantArgumentResolver()
        );
    }
}

@RestController
@RequestMapping("/api")
class ApiController {

    @GetMapping(
        path = "/greeting",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Greeting> greeting(
            @CurrentTenant TenantContext tenant) {

        return Mono.just(
            new Greeting("hello", tenant.id())
        );
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Message> echo(@RequestBody Mono<Message> message) {
        return message;
    }
}
~~~

Các type phụ được khai báo package-private trong cùng file để giữ ví dụ gọn. Trong dự án thực tế, có thể tách annotation, resolver, DTO, config và controller thành các file riêng.

### 10.4. MediaTypeDemoTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class MediaTypeDemoTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptHeaderSelectsJsonResponse() {
        client.get()
            .uri("/api/greeting")
            .header("X-Tenant-Id", "acme")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("hello")
            .jsonPath("$.tenantId").isEqualTo("acme");
    }

    @Test
    void queryFormatCanSelectJsonWhenAcceptIsWildcard() {
        client.get()
            .uri("/api/greeting?format=json")
            .header("X-Tenant-Id", "team-a")
            .accept(MediaType.ALL)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.tenantId").isEqualTo("team-a");
    }

    @Test
    void unsupportedAcceptReturnsNotAcceptable() {
        client.get()
            .uri("/api/greeting")
            .header("X-Tenant-Id", "acme")
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isEqualTo(406);
    }

    @Test
    void missingTenantHeaderReturnsBadRequest() {
        client.get()
            .uri("/api/greeting")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void requestBodyReaderDecodesJson() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new Message("hello reactive"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello reactive");
    }

    @Test
    void unsupportedRequestContentTypeReturnsUnsupportedMediaType() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.TEXT_PLAIN)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue("hello")
            .exchange()
            .expectStatus().isEqualTo(415);
    }
}
~~~

### 10.5. Chạy test

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Test xác minh:

1. Accept application/json chọn response JSON.
2. Query parameter format=json có thể chọn JSON khi Accept là wildcard.
3. Accept text/plain không phù hợp produces JSON nên trả 406.
4. Thiếu X-Tenant-Id khiến custom argument resolver trả 400.
5. Request JSON được message reader giải mã thành Message.
6. Request text/plain không thỏa consumes JSON nên trả 415.

Đây là kiểm thử tích hợp bằng WebTestClient; ví dụ không cần gọi dịch vụ bên ngoài. Nếu thay đổi resolver order, hãy bổ sung test có cả format query và Accept cụ thể để xác nhận chính sách ưu tiên.

## 11. Kiểm tra thứ tự và hành vi content resolver

### 11.1. Resolver đầu tiên trả media type cụ thể sẽ thắng

Giả sử cấu hình query resolver trước header resolver:

~~~java
builder.parameterResolver()
    .parameterName("format")
    .mediaType("json", MediaType.APPLICATION_JSON);

builder.headerResolver();
~~~

Request:

~~~http
GET /api/greeting?format=json
Accept: text/plain
~~~

Query resolver được chạy trước và trả application/json. Header resolver không được dùng nếu resolver trước đã trả danh sách media type cụ thể.

Nếu đổi thứ tự, Accept text/plain sẽ được chọn trước. Vì handler chỉ produces JSON, request có thể trả 406.

### 11.2. MediaType.ALL cho phép fallback

Nếu query parameter không có hoặc resolver không thể xác định một định dạng cụ thể, kết quả có thể là MediaType.ALL. Composite resolver tiếp tục thử resolver kế tiếp.

Đây là lý do nên hiểu cả thứ tự và kết quả fallback thay vì chỉ nhìn danh sách resolver đã đăng ký.

### 11.3. Chất lượng q và wildcard

Accept có thể chứa nhiều media type cùng q-value:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5, */*;q=0.1
~~~

Requested content type resolver trả danh sách media type theo độ cụ thể và quality. Mapping và writer tiếp tục xét các media type tương thích. Không tự parse Accept bằng cách split chuỗi theo dấu phẩy; hãy dùng API MediaType và resolver của Spring để xử lý wildcard, parameter và q-value.

## 12. Cấu hình media type an toàn và dễ vận hành

### 12.1. Hạn chế format được hỗ trợ

Nếu API chỉ hỗ trợ JSON, không cần thêm query resolver. Dùng Accept header và khai báo produces rõ ràng.

Nếu cần query parameter, chỉ map các format mà server thật sự có writer. Không công bố XML/CSV nếu chưa có codec/writer và test tương ứng.

### 12.2. Cẩn thận với cache

Nếu response thay đổi theo Accept, cache trung gian cần phân biệt representation theo header Accept; cân nhắc header `Vary: Accept` theo hợp đồng caching.

Nếu response thay đổi theo query parameter như format, URL khác nhau thường đã tạo cache key khác. Vẫn cần kiểm tra cấu hình CDN/proxy thực tế.

### 12.3. Không dùng path extension như cơ chế mặc định

Không nên giả định URL kết thúc bằng `.json` tự động chọn JSON trong WebFlux. Mặc định hiện đại dùng Accept header; nếu cần query parameter, cấu hình rõ bằng `parameterResolver()`. Path extension có thể gây nhập nhằng với routing, file name và security filter.

### 12.4. Không để query format thay thế authorization

Format chỉ chọn cách biểu diễn response. Nó không nên quyết định quyền truy cập dữ liệu hoặc bật một endpoint quản trị. Authorization vẫn phải dựa trên principal, role, scope và policy server-side.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm Content-Type với Accept | Đọc request sai hoặc chọn response sai | Content-Type cho request body; Accept cho response |
| Nghĩ consumes chọn response format | Handler bị từ chối dù response writer có thể hỗ trợ | Dùng produces cho response |
| Nghĩ produces tự đăng ký codec | Có mapping nhưng không có writer encode kiểu Java | Đăng ký codec qua ServerCodecConfigurer |
| Cấu hình parameterResolver nhưng quên headerResolver | Accept không còn là fallback theo ý định | Thêm headerResolver theo đúng thứ tự |
| Đăng ký resolver sai thứ tự | Query hoặc Accept luôn thắng ngoài dự kiến | Viết test cho request có cả hai |
| Dùng format value tùy ý | Client yêu cầu representation không được hỗ trợ | Dùng allowlist mapping |
| Dùng HandlerMethodArgumentResolver của MVC | Sai signature, không tương thích WebFlux | Dùng interface trong org.springframework.web.reactive.result.method |
| Resolver hỗ trợ mọi String/Object | Tranh quyền với resolver built-in | Kiểm tra annotation và kiểu cụ thể |
| Nghĩ addCustomResolver ghi đè built-in | Resolver mặc định vẫn được chọn cho kiểu built-in | Dùng custom annotation/type riêng; advanced config nếu thật sự cần override |
| Dùng resolver để đọc JSON body | Lặp lại codec và có thể tiêu thụ body hai lần | Dùng @RequestBody và HttpMessageReader |
| Gọi block trong resolver | Chặn event loop | Trả Mono từ service reactive |
| Trả Mono.empty cho đối số bắt buộc | Controller có thể nhận null/không có giá trị | Trả Mono.error cho input thiếu |
| Lưu request data vào field của resolver | Dữ liệu giữa các request có thể rò lẫn | Đọc từ exchange mỗi lần resolve; resolver stateless |
| Tin X-Tenant-Id là authorization | Người dùng có thể giả tenant | Xác minh principal và quyền tenant |
| Không test 406/415 | Lỗi negotiation chỉ xuất hiện khi client thật gọi | Test Accept, Content-Type, consumes, produces |
| Thêm @EnableWebFlux trong Spring Boot chỉ để thêm resolver | Có thể làm mất một số auto-configuration của Boot | Dùng WebFluxConfigurer không có @EnableWebFlux khi dùng Boot |

## 14. Checklist review WebFlux configuration

Trước khi đưa cấu hình vào ứng dụng, kiểm tra:

1. **Request media type:** Content-Type có khớp consumes và reader không?
2. **Response media type:** Accept hoặc query format có được resolve theo thứ tự mong muốn không?
3. **Mapping:** produces có phản ánh các representation thật sự hỗ trợ không?
4. **Codec:** có reader/writer tương ứng với Java type và media type không?
5. **Fallback:** khi query parameter vắng mặt hoặc không cụ thể, resolver kế tiếp có hoạt động không?
6. **Quality:** wildcard và q-value có được xử lý bằng API Spring không?
7. **Custom argument:** supportsParameter có kiểm tra annotation và kiểu chính xác không?
8. **Reactive:** resolveArgument có trả Mono và không block không?
9. **Errors:** missing value trả lỗi rõ ràng và status phù hợp chưa?
10. **Security:** tenant/user context đã được xác thực và authorization chưa?
11. **Registration:** resolver được đăng ký qua configureArgumentResolvers chưa?
12. **Built-in:** custom resolver có vô tình tranh quyền với resolver mặc định không?
13. **Tests:** WebTestClient có kiểm tra Accept, query format, 406, 415 và custom argument chưa?
14. **Boot:** có giữ Spring Boot auto-configuration bằng cách tránh @EnableWebFlux không cần thiết không?

**Ghi nhớ:** WebFlux mặc định resolve requested media type từ Accept cho annotated controller. Có thể bổ sung query parameter bằng RequestedContentTypeResolverBuilder và phải chủ động chọn thứ tự resolver. Content-Type/consumes điều khiển việc đọc request; Accept/produces điều khiển representation response; codecs thực hiện encode/decode. Custom HandlerMethodArgumentResolver của WebFlux trả Mono<Object>, nhận BindingContext và ServerWebExchange, được đăng ký qua ArgumentResolverConfigurer. Dùng nó để inject một kiểu request context rõ ràng, còn chuyển đổi kiểu đơn giản và đọc body nên giao cho Converter/Formatter và HttpMessageReader.

## Tài liệu tham khảo

- Spring Framework — WebFlux Configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — RequestedContentTypeResolverBuilder API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/accept/RequestedContentTypeResolverBuilder.html
- Spring Framework — WebFluxConfigurer API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html
- Spring Framework — ArgumentResolverConfigurer API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ArgumentResolverConfigurer.html
- Spring Framework — WebFlux HandlerMethodArgumentResolver API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/HandlerMethodArgumentResolver.html
- Spring Framework — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — HTTP Message Codecs and Data Buffers: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
