# Chuyển đổi query, path, header và dữ liệu form trong Spring WebFlux

## 1. Bức tranh tổng thể: cùng là chuỗi HTTP nhưng khác nguồn dữ liệu

Trong **Spring WebFlux** (reactive web stack), HTTP request có thể đưa dữ liệu cho một handler thông qua nhiều nơi:

- **Query parameters**: `GET /orders?size=20&active=true`.
- **Path variables**: `GET /orders/123` với route `/orders/{id}`.
- **Request headers**: `X-Retry: 2`, `Accept-Language: vi-VN`.
- **Form fields** trong body `application/x-www-form-urlencoded`: `name=Lan&age=26`.
- **Multipart form**: các text field và file part trong `multipart/form-data`.

Để handler nhận giá trị kiểu Java như `int`, `long`, `UUID`, `boolean`, `LocalDate`, `enum` hoặc một form DTO, WebFlux cần hai bước: **chọn đúng nguồn dữ liệu** rồi **chuyển chuỗi/giá trị thô thành kiểu đích** bằng `ConversionService`, `Converter`, `Formatter` hoặc WebFlux data binding.

Điểm dễ nhầm nhất khi đã quen Spring MVC: **trong WebFlux, `@RequestParam` chỉ đọc query parameters**. Servlet MVC có request parameter map gộp query, form và có thể multipart; WebFlux **phân biệt** chúng tại `ServerWebExchange`. Để bind cả query, form và multipart vào một command object, dùng `@ModelAttribute`/data binding; để đọc form data trực tiếp dùng `ServerWebExchange#getFormData()`. Đó là hợp đồng được Spring WebFlux ghi rõ, không phải hành vi suy đoán từ Spring MVC.

Ví dụ HTTP:

~~~http
POST /api/convert/form-query?name=Mai
Content-Type: application/x-www-form-urlencoded

name=Lan&age=26
~~~

Trong WebFlux, `@RequestParam("name")` nhận `"Mai"` từ **query**. `exchange.getFormData()` nhận `"Lan"` từ **form body**. Không nên giả định hai nguồn bị tự động gộp vào một map như servlet request parameters.

## 2. Bảng chọn annotation/API theo nguồn

| Nguồn HTTP | Annotation hoặc API WebFlux | Kiểu đích có thể chuyển | Lưu ý |
| --- | --- | --- | --- |
| Query `?page=3` | `@RequestParam("page") int page` | String → int, enum, UUID, list... | **Chỉ query**, không tự lấy form body. |
| Path `/orders/{id}` | `@PathVariable("id") UUID id` | String → UUID | Phải khớp route template; thiếu/sai kiểu thường dẫn tới 4xx. |
| Header `X-Retry: 2` | `@RequestHeader("X-Retry") int retry` | String → int, enum, collection... | Header do client gửi, không mặc nhiên đáng tin. |
| Cookie `sessionHint=...` | `@CookieValue("sessionHint") String hint` | String → kiểu được hỗ trợ | Dùng annotation riêng, không nhầm header/query. |
| Form-urlencoded | `@ModelAttribute FormDto form` hoặc `exchange.getFormData()` | Các field → bean properties/constructor args; hoặc `MultiValueMap<String,String>` | `getFormData()` trả `Mono<MultiValueMap<String,String>>`. |
| Multipart | `@ModelAttribute FormDto` hoặc `@RequestPart("file") FilePart`; `exchange.getMultipartData()` | Form fields, `FilePart`/`Part` | `FilePart` khác `MultipartFile` của Servlet MVC. |
| JSON body | `@RequestBody Dto dto` hoặc `Mono<Dto>` | JSON → DTO qua `HttpMessageReader`/codec | **Không** phải property binding của `@RequestParam`. |
| Raw request context | `ServerWebExchange` | Query `MultiValueMap`, headers, path, reactive form/multipart | Dùng khi cần kiểm soát nguồn chi tiết. |

Một handler có thể kết hợp các nguồn:

~~~java
@GetMapping("/orders/{id}")
String detail(@PathVariable UUID id,
              @RequestParam(defaultValue = "1") int page,
              @RequestHeader(name = "X-Retry",
                             defaultValue = "0") int retry) {
    return id + "|" + page + "|" + retry;
}
~~~

Đây là **snippet**, cần nằm trong `@RestController` cùng imports. WebFlux resolve từng argument riêng: `id` lấy từ path, `page` từ query, `retry` từ header; sau đó conversion cho từng kiểu. Không phải cả ba cùng đọc một parameter map.

## 3. `@RequestParam`: chuyển đổi **query parameters** trong WebFlux

Giả sử URL:

~~~http
GET /search?keyword=spring&page=3&active=true&tag=java&tag=reactor
~~~

Handler:

~~~java
@GetMapping("/search")
String search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "false") boolean active,
        @RequestParam(name = "tag", required = false)
                List<String> tags) {

    return keyword + ":" + page + ":" + active + ":" + tags;
}
~~~

Đây là snippet trong controller với `List` import. `keyword` là chuỗi, `page` được chuyển thành `int`, `active` thành `boolean`, `tags` có thể nhận các giá trị lặp. Với request ở trên, logic trả dạng `spring:3:true:[java, reactor]` theo cách `List#toString()` của dữ liệu ví dụ. Dữ liệu lặp không nên rút thành giá trị đầu nếu business logic cần đủ mọi giá trị.

### `required`, `defaultValue` và `Optional`

- `@RequestParam("page") int page`: theo mặc định `required=true`; nếu thiếu, handler không chạy và WebFlux thường trả HTTP 400.
- `@RequestParam(name="page", required=false) Integer page`: cho phép vắng mặt, thường nhận null. Dùng wrapper thay vì primitive nếu thiếu thực sự có nghĩa.
- `@RequestParam(defaultValue="1") int page`: đặt giá trị dự phòng; khai báo default cũng làm tham số không bắt buộc.
- `@RequestParam Optional<Integer> page`: thể hiện có/không có; cần import `java.util.Optional`.
- Với chuỗi rỗng được conversion thành null (chẳng hạn `UUID` hoặc wrapper type theo converter), Spring có thể xem đó là thiếu giá trị. Hãy đặt `required=false` hoặc kiểu nullable khi hợp đồng chấp nhận.

Một pattern rõ ràng cho phân trang:

~~~java
@GetMapping("/products")
String products(@RequestParam(defaultValue = "0") int page,
                @RequestParam(defaultValue = "20") int size) {
    return "page=" + page + ", size=" + size;
}
~~~

Việc chuyển đổi thành `int` **không tự bảo đảm** `page >= 0` hoặc `size <= 100`. Cần validation/range check nghiệp vụ nếu có giới hạn. Không đánh đồng *type conversion* với *validation*.

### Map nhiều query parameters

`@RequestParam MultiValueMap<String,String> params` (không chỉ rõ tên) có thể lấy tất cả query values, bao gồm các tên lặp. `Map<String,String>` phù hợp khi chỉ cần một giá trị cho mỗi key. Dùng `MultiValueMap` khi có tag/filter lặp hoặc cần phân biệt số phần tử. Không tự parse URL bằng `split("&")` vì percent-encoding và ký tự đặc biệt cần được framework xử lý.

## 4. `@PathVariable`: chuyển path thành kiểu Java

Route mẫu:

~~~java
@GetMapping("/orders/{orderId}")
String order(@PathVariable("orderId") UUID id) {
    return "ORDER:" + id;
}
~~~

Request:

~~~http
GET /orders/123e4567-e89b-12d3-a456-426614174000
~~~

WebFlux lấy phần `{orderId}` từ route đã match, rồi `ConversionService` chuyển `String` thành `java.util.UUID`. Tên trong `@PathVariable("orderId")` là tên **biến template**, còn tên Java `id` có thể khác. Chỉ dùng `@PathVariable UUID id` không chỉ rõ tên khi chắc chắn tên parameter được biên dịch/khám phá đúng.

Các trường hợp:

- `/orders/not-a-uuid`: route vẫn có thể match chuỗi path, nhưng conversion thất bại → thường HTTP 400.
- `/orders/`: **không match** route `/orders/{orderId}`; thường HTTP 404, không phải lỗi "UUID invalid" của handler đó.
- `/orders/123?orderId=xyz`: path variable lấy từ **path**, không bị query parameter cùng tên ghi đè.
- Nếu muốn path segment ngày, dùng `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` trên `LocalDate` để quy định định dạng.

Ví dụ ngày:

~~~java
@GetMapping("/calendar/{day}")
String calendar(
        @PathVariable("day")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate day) {
    return "DAY:" + day;
}
~~~

`/calendar/2026-11-06` tạo `LocalDate.of(2026,11,6)`. `/calendar/not-a-date` không thể convert theo ISO date → HTTP 400 với cấu hình mặc định. Dùng `@DateTimeFormat`/formatter thay vì tự tách ngày, tháng, năm bằng chuỗi trong handler.

Lưu ý route matching và conversion là **hai bước**: path phải match mapping trước, sau đó mới convert argument. Với path variable có kiểu `UUID` hoặc `int`, framework không tự thay route thành một regular expression chỉ vì Java type của argument.

## 5. `@RequestHeader`: header là nguồn riêng, vẫn chuyển kiểu được

Ví dụ request:

~~~http
GET /api/convert/orders/123e4567-e89b-12d3-a456-426614174000?page=3
X-Retry: 2
Accept-Language: vi-VN,vi;q=0.9
~~~

Handler:

~~~java
@GetMapping("/retry")
String retry(@RequestHeader(name = "X-Retry",
                            defaultValue = "0") int attempts) {
    return "retry=" + attempts;
}
~~~

`X-Retry: 2` được chuyển thành `int` bằng conversion đã cấu hình. `X-Retry: abc` không thể chuyển thành `int`, thường HTTP 400 khi argument resolution thất bại.

Có thể khai báo `@RequestHeader("Accept") List<String> types`; Spring có cơ chế chuyển chuỗi header có dấu phẩy thành array/collection khi type converter hỗ trợ. Nếu cần toàn bộ header, dùng `@RequestHeader HttpHeaders headers` hoặc `ServerWebExchange#getRequest().getHeaders()`. Nếu cần một header nhiều giá trị, `getValuesAsList("Accept")` hay `get("Accept")` của `HttpHeaders` có semantics riêng; đừng giả định một header line luôn chỉ có một giá trị.

**Vấn đề bảo mật:** headers có thể do browser, client, CDN hoặc reverse proxy đặt/sửa. Không dựa vào một custom header như `X-User-Id` để xác thực danh tính nếu không có boundary tin cậy và cơ chế authentication. `@RequestHeader` chỉ đọc/chuyển kiểu; nó không quyết định header đó có đáng tin hay không. Headers không được tự động xem là query hoặc form.

### Request attribute và cookie không phải header binding

- `@CookieValue` nhận cookie theo tên; cookie truyền qua HTTP Cookie header nhưng có annotation riêng.
- `@RequestAttribute` lấy attribute đã được server-side filter/interceptor đặt vào request exchange; không phải tham số do client gửi.
- `@RequestHeader` không cần `@ModelAttribute` để chuyển đổi các giá trị đơn lẻ.

## 6. Dữ liệu form trong WebFlux: `@ModelAttribute` và `getFormData()`

### 6.1. Không nhầm form body với query map

Trong Servlet MVC, `HttpServletRequest#getParameterMap()` kết hợp query/form theo Servlet API. Trong Spring WebFlux:

~~~java
MultiValueMap<String, String> query =
        exchange.getRequest().getQueryParams();

Mono<MultiValueMap<String, String>> form =
        exchange.getFormData();
~~~

Đây là snippet trong method có `ServerWebExchange exchange` và imports phù hợp, không phải file độc lập. Hai nguồn **tách riêng**:

- `getQueryParams()`: giá trị trên URL, sẵn có dạng `MultiValueMap<String,String>`.
- `getFormData()`: nội dung `application/x-www-form-urlencoded` được `FormHttpMessageReader` parse, trả về **`Mono<MultiValueMap<String,String>>`**. Kết quả có thể được WebFlux cache cho việc đọc lại qua API form data.
- `getMultipartData()`: dữ liệu multipart, trả về `Mono<MultiValueMap<String,Part>>`. Không dùng `getFormData()` để lấy file part.
- Trong reactive code, gọi `.map(...)`, `.flatMap(...)` hoặc trả `Mono` cho WebFlux subscriber; **không gọi `.block()` trong handler trên event-loop** để ép lấy form synchronously.

Ví dụ handler đọc cả hai nguồn một cách tường minh:

~~~java
@PostMapping(path = "/form-query",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
Mono<String> compare(
        @RequestParam(name = "name", required = false)
        String queryName,
        ServerWebExchange exchange) {

    return exchange.getFormData().map(values -> {
        String query = queryName == null ? "none" : queryName;
        String formName = values.getFirst("name");
        return "QUERY:" + query + "|FORM:" + formName;
    });
}
~~~

Đây là snippet trong `@RestController`; ví dụ chạy hoàn chỉnh ở phần 9. Với URL `/form-query?name=Mai`, body `name=Lan`, output **`QUERY:Mai|FORM:Lan`**. Với URL không có query `name`, output **`QUERY:none|FORM:Lan`**. Khác biệt này giúp tránh bug khi port code MVC sang WebFlux.

**Không nên trộn nhiều cách tiêu thụ raw body**: sau khi body đã được decode/cached như form data, đừng cố đọc raw `Flux<DataBuffer>` lần thứ hai và kỳ vọng body còn nguyên để parse tiếp. Chọn pipeline rõ ràng.

### 6.2. `@ModelAttribute` bind form vào command object

Khi muốn nhiều field có kiểu được bind thành form object:

~~~java
@PostMapping("/form")
ResponseEntity<?> save(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body("FORM_INVALID");
    }
    return ResponseEntity.ok("OK");
}
~~~

Đây là snippet controller, không phải chương trình độc lập. `@ModelAttribute` trong WebFlux có thể bind **form data, query parameters, URI path variables và request headers** vào model object. Theo tài liệu, **form và query parameters ưu tiên hơn URI variables và headers**; URI/header values chỉ được bổ sung nếu không ghi đè các input parameters trùng tên. Header name có thể được chuẩn hóa bỏ dấu gạch ngang.

`WebDataBinder` thực hiện constructor/property binding cùng conversion service và formatter. Đường dẫn lồng như `address.city`, `items[0].quantity` có thể được xử lý nếu target/property path và cấu hình binder phù hợp.

Đặt `BindingResult` **ngay sau** `@ModelAttribute` (không chen tham số khác vào giữa) nếu muốn xử lý lỗi trực tiếp. Với form `age=abc` khi property `age` là Integer, Spring có thể tạo `FieldError` mã `typeMismatch` trong `BindingResult`. Nếu có `@Valid` và constraint trên DTO, lỗi Bean Validation cũng được đưa vào `BindingResult`. Nếu không xử lý cục bộ, WebFlux thường ném **`WebExchangeBindException`** và phản hồi HTTP 400.

**Reactive wrapper:** Spring WebFlux cũng hỗ trợ `@ModelAttribute Mono<Form>` ở những ngữ cảnh phù hợp, nhưng nếu muốn dùng `BindingResult` parameter liền kề thì model attribute nên được khai báo không bọc `Mono`. Với dạng reactive, lỗi cần xử lý trong pipeline thay vì qua `BindingResult` liền kề.

### 6.3. `@ModelAttribute` với query/path/header cũng cần chính sách nguồn

Giả sử `@PostMapping("/orders/{ownerId}/update")` có form object chứa `ownerId`, `name`. WebFlux có thể lấy `ownerId` từ URI variable nếu request values chưa có tên đó. Tuy nhiên, nếu client có thể gửi `ownerId` trong form/query, value từ request có thể được ưu tiên. **Đừng dùng form-bound ownerId làm bằng chứng rằng client được phép sửa resource đó.** Nên lấy owner identity từ authentication context và kiểm tra quyền riêng.

Tương tự, header `X-Role: ADMIN` không phải là nguồn sự thật để cập nhật thuộc tính role. Nên có DTO chuyên dụng và whitelist fields.

### 6.4. Form field markers/defaults và nested properties

`WebDataBinder` có hỗ trợ xử lý HTML checkbox markers như `_subscribed` khi checkbox không được gửi, cũng như field defaults `!age`. Với form:

~~~html
<input type="hidden" name="_newsletter" value="present">
<input type="checkbox" name="newsletter" value="true">
~~~

Nếu user bỏ tick checkbox, chỉ marker được gửi; binder có thể reset field boolean thành `false` thay vì giữ lại giá trị cũ. Đây là chức năng của **data binding**, không áp dụng tương tự cho một `@RequestParam boolean` chỉ đọc query. Marker không phải bảo mật; client hoàn toàn có thể giả mạo tên/value trong form.

## 7. Multipart trong WebFlux không giống Servlet MVC

Trường hợp upload qua `multipart/form-data`:

- WebFlux dùng `org.springframework.http.codec.multipart.Part` và `FilePart` (không phải Servlet `MultipartFile`).
- `@RequestPart("file") FilePart file` nhận part được chọn theo tên.
- Một command object `@ModelAttribute` có thể chứa `FilePart` và các form fields.
- `ServerWebExchange#getMultipartData()` trả `Mono<MultiValueMap<String, Part>>`.
- `@RequestPart("metadata") Metadata metadata` có thể dùng message reader/codec deserialize một part JSON theo Content-Type của part.

Snippet upload:

~~~java
@PostMapping(path = "/files",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(@RequestPart("file") FilePart file) {
    // Tại đây chỉ minh họa tên file; production cần xử lý nội dung an toàn.
    return Mono.just("FILE:" + file.filename());
}
~~~

Ví dụ chưa lưu file; đây là snippet minh họa trong controller. **Không xem `file.filename()` là đường dẫn tin cậy** và không ghép nó trực tiếp vào đường dẫn lưu filesystem. Cần xác thực/giới hạn kích thước, loại file, content scanning, xử lý stream và giải phóng DataBuffer đúng hợp đồng.

Nếu chỉ cần nhiều giá trị text form-urlencoded thì dùng `getFormData()`, không dùng multipart. Nếu có JSON body thuần, `@RequestBody` đi qua `HttpMessageReader`, không phải `@ModelAttribute`/query conversion. Với `@Valid @RequestBody`, lỗi validation thường là `WebExchangeBindException`; lỗi parse JSON (body sai cú pháp) thuộc bước đọc message.

## 8. ConversionService, Formatter và Converter: cơ chế chuyển kiểu

### 8.1. Conversion tự động cho argument đơn

`@RequestParam`, `@PathVariable`, `@RequestHeader`, `@CookieValue` và những argument dựa trên text đều có thể được Spring WebFlux chuyển từ `String` sang target Java type. Các kiểu cơ bản như `int`, `long`, `boolean`, enum hoặc `UUID` có conversion phù hợp tùy registration/configuration.

Ví dụ:

~~~java
@GetMapping("/demo/{id}")
String demo(@PathVariable UUID id,
            @RequestParam int count,
            @RequestHeader("X-Retry") Integer retry) {
    return id + "|" + count + "|" + retry;
}
~~~

`UUID` cần chuỗi hợp lệ; `count=not-an-integer` hoặc `X-Retry: abc` gây lỗi type conversion và thường HTTP 400. Không cần `Integer.parseInt`/`UUID.fromString` trong controller nếu có conversion service.

### 8.2. Định dạng ngày giờ bằng `@DateTimeFormat`

Với HTML form hay path/query date, cách chỉ rõ ISO:

~~~java
@GetMapping("/calendar/{day}")
String calendar(@PathVariable("day")
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                LocalDate day) {
    return "DAY:" + day;
}
~~~

`@DateTimeFormat` ảnh hưởng cách Spring chuyển **textual request values** thành Java date/time; nếu giá trị nằm trong **JSON body**, mapping chủ yếu do codec/Jackson và cấu hình serializer/deserializer tương ứng, không mặc nhiên dùng cùng formatter của WebDataBinder.

### 8.3. Custom Converter cho enum alias

Giả sử client gửi `level=exp` nhưng backend muốn enum `ShippingLevel.EXPRESS`. Thay vì so sánh chuỗi trong mỗi handler, đăng ký `Converter<String,ShippingLevel>` qua `WebFluxConfigurer#addFormatters(FormatterRegistry)`:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, ShippingLevel.class,
            text -> switch (text.trim().toLowerCase(Locale.ROOT)) {
                case "standard", "std" -> ShippingLevel.STANDARD;
                case "express", "exp" -> ShippingLevel.EXPRESS;
                default -> throw new IllegalArgumentException(
                        "Unsupported shipping level");
            });
}
~~~

Đây là snippet trong `WebFluxConfigurer`, đầy đủ source ở phần 9. Khi đã đăng ký, handler có thể khai báo `@RequestParam ShippingLevel level`; Spring dùng converter. Nếu user nhập giá trị không biết, converter báo lỗi chuyển kiểu, và WebFlux thường trả 400 (không trả 500 nếu argument resolution nhận diện lỗi conversion).

**Đừng lạm dụng global converter:** converter được dùng ở nhiều nơi cần cùng type `ShippingLevel`. Nếu alias chỉ dành cho một endpoint, cân nhắc đổi input contract hoặc dùng DTO/formatter có phạm vi rõ ràng. Converter nên stateless, deterministic, không gọi blocking I/O.

### 8.4. `@InitBinder` so với `WebFluxConfigurer`

- `WebFluxConfigurer#addFormatters`: đăng ký converter/formatter dùng trên phạm vi WebFlux conversion service; phù hợp chuẩn hóa chuyển kiểu cho nhiều controller.
- `@InitBinder` trong `@Controller`/`@ControllerAdvice`: điều chỉnh `WebDataBinder` cho những model objects/argument tương ứng, ví dụ `setAllowedFields` hoặc custom editors.
- `Validator`/`@Valid`: kiểm tra **giá trị sau conversion**, không tự chịu trách nhiệm parse text.
- `HttpMessageReader`/codec: đọc **JSON body, raw body, multipart parts**; cùng một DTO JSON có thể có quy tắc mapping khác form binder.

Theo Spring WebFlux config, formatters cho số và ngày giờ được đăng ký mặc định ở nhiều tình huống; có thể tùy chỉnh qua `@DateTimeFormat` và `addFormatters`. Cần xác định chính xác locale/zone khi ngày giờ có múi giờ, và test trong các locale thực tế.

## 9. Ví dụ hoàn chỉnh Java 17+ và Spring Boot WebFlux: query, path, header, form

Ví dụ hướng tới một dự án **Spring Boot 3.x**, **Java 17+**, Maven, chỉ dùng **Spring WebFlux** (không thêm `spring-boot-starter-web` để tránh vô tình chọn Servlet MVC). Khi dự án có parent/BOM của Spring Boot, thêm các dependencies sau vào `pom.xml`:

~~~xml
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
~~~

Tạo các file trong package `com.example.webfluxbinding` theo đúng tên. Đảm bảo Spring Boot Maven plugin đã được cấu hình trong project chuẩn, và dùng đồng nhất các dependency do Boot BOM quản lý.

### 9.1. `WebFluxBindingApplication.java`

File `src/main/java/com/example/webfluxbinding/WebFluxBindingApplication.java`:

~~~java
package com.example.webfluxbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxBindingApplication.class, args);
    }
}
~~~

### 9.2. `ShippingLevel.java`

File `src/main/java/com/example/webfluxbinding/ShippingLevel.java`:

~~~java
package com.example.webfluxbinding;

public enum ShippingLevel {
    STANDARD,
    EXPRESS
}
~~~

### 9.3. `WebFluxConversionConfig.java`

File `src/main/java/com/example/webfluxbinding/WebFluxConversionConfig.java`:

~~~java
package com.example.webfluxbinding;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import java.util.Locale;

@Configuration
public class WebFluxConversionConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                ShippingLevel.class,
                value -> switch (
                        value.trim().toLowerCase(Locale.ROOT)) {
                    case "standard", "std" -> ShippingLevel.STANDARD;
                    case "express", "exp" -> ShippingLevel.EXPRESS;
                    default -> throw new IllegalArgumentException(
                            "Unsupported shipping level: " + value);
                });
    }
}
~~~

Trong trường hợp thực, cân nhắc không đưa raw input vào exception/log nếu input nhạy cảm; `ShippingLevel` là ví dụ enum không nhạy cảm. Converter không có mutable state nên có thể dùng chung. `WebFluxConfigurer` và `@Configuration` được Spring Boot WebFlux nhận khi application khởi động.

### 9.4. `RegistrationForm.java`

File `src/main/java/com/example/webfluxbinding/RegistrationForm.java`:

~~~java
package com.example.webfluxbinding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    private boolean newsletter;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public boolean isNewsletter() {
        return newsletter;
    }

    public void setNewsletter(boolean newsletter) {
        this.newsletter = newsletter;
    }
}
~~~

`@NotBlank` và `@NotNull @Min(18)` là **validation**; chúng không tự chuyển String thành Integer. `WebDataBinder` làm conversion trước; nếu `age=abc`, lỗi binding có thể xuất hiện trước khi constraint tuổi được đánh giá.

### 9.5. `WebFluxBindingController.java`

File `src/main/java/com/example/webfluxbinding/WebFluxBindingController.java`:

~~~java
package com.example.webfluxbinding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.time.LocalDate;
import java.util.UUID;

@RestController
@RequestMapping("/api/convert")
public class WebFluxBindingController {

    @GetMapping("/orders/{orderId}")
    public String order(
            @PathVariable("orderId") UUID id,
            @RequestParam("page") int page,
            @RequestParam(name = "active",
                          defaultValue = "false") boolean active,
            @RequestHeader(name = "X-Retry",
                           defaultValue = "0") int retry) {

        return "ORDER:" + id
                + "|page=" + page
                + "|active=" + active
                + "|retry=" + retry;
    }

    @GetMapping("/day/{day}")
    public String day(
            @PathVariable("day")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day) {

        return "DAY:" + day;
    }

    @GetMapping("/shipping")
    public String shipping(
            @RequestParam("level") ShippingLevel level) {
        return "LEVEL:" + level;
    }

    @PostMapping(path = "/form-query",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> compareFormAndQuery(
            @RequestParam(name = "name", required = false)
            String queryName,
            ServerWebExchange exchange) {

        // @RequestParam: chỉ lấy query string của URL.
        // getFormData(): đọc riêng form-urlencoded body.
        return exchange.getFormData().map(values -> {
            String query = queryName == null
                    ? "none" : queryName;
            return "QUERY:" + query
                    + "|FORM:" + values.getFirst("name");
        });
    }

    @InitBinder("registration")
    public void configureRegistrationBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "newsletter");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("registration")
            RegistrationForm registration,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length != 0) {
            return ResponseEntity.badRequest()
                    .body("FORM_INVALID");
        }

        return ResponseEntity.ok(
                "FORM:" + registration.getName()
                + ":" + registration.getAge()
                + ":" + registration.isNewsletter());
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public String json(
            @Valid @RequestBody JsonRegistration body) {
        return "JSON:" + body.name() + ":" + body.age();
    }

    public record JsonRegistration(
            @NotBlank String name,
            @NotNull @Min(18) Integer age) {
    }
}
~~~

Các điểm chính của chương trình:

1. `order` nhận ba nguồn: `id` từ route template, `page`/`active` từ query, `X-Retry` từ header; mọi tham số typed được Spring chuyển trước khi gọi thân phương thức.
2. `day` minh họa `@DateTimeFormat` trên một path variable. Không cần tự parse `LocalDate`.
3. `shipping` dùng custom Converter `String → ShippingLevel`: client có thể gửi `level=exp` và handler nhận `ShippingLevel.EXPRESS`.
4. `compareFormAndQuery` chứng minh `@RequestParam` **không** đọc form body của WebFlux, trong khi `getFormData()` đọc form data **bất đồng bộ** và không cần `block()`.
5. `form` nhận `RegistrationForm` qua `@ModelAttribute`. `@InitBinder` chỉ cho phép ba field; `BindingResult` ngay sau form nhận lỗi conversion/validation. Method tự trả 400 khi có lỗi hoặc có suppressed fields.
6. `json` dùng **`@RequestBody` và HTTP message reader**; record `JsonRegistration` là request DTO tách biệt, không chịu whitelist property binding của form.
7. `@RestController` khiến `String` trả về được ghi vào response body. Các ví dụ trả plain text để test dễ thấy nguồn dữ liệu, không phải template view.

**Vì sao import `@Min` ở controller?** Nó chỉ phục vụ annotation của record `JsonRegistration`. Không có constraint `@Min` trực tiếp trên `@RequestParam page` trong demo để không trộn chủ đề chuyển kiểu với cơ chế method validation; nếu muốn `page >= 1`, phải thiết kế và kiểm thử validation riêng.

## 10. Kiểm thử WebTestClient: kết quả có thể quan sát

Tạo file `src/test/java/com/example/webfluxbinding/WebFluxBindingApplicationTest.java`:

~~~java
package com.example.webfluxbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxBindingApplicationTest {

    private static final String ID =
            "123e4567-e89b-12d3-a456-426614174000";

    @Autowired
    WebTestClient client;

    @Test
    void convertsPathQueryAndHeader() {
        client.get()
                .uri("/api/convert/orders/" + ID
                        + "?page=3&active=true")
                .header("X-Retry", "2")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ORDER:" + ID
                        + "|page=3|active=true|retry=2");
    }

    @Test
    void usesDefaultsWhenOptionalQueryAndHeaderMissing() {
        client.get()
                .uri("/api/convert/orders/" + ID + "?page=1")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ORDER:" + ID
                        + "|page=1|active=false|retry=0");
    }

    @Test
    void missingRequiredQueryIsBadRequest() {
        client.get()
                .uri("/api/convert/orders/" + ID)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidPathUuidIsBadRequest() {
        client.get()
                .uri("/api/convert/orders/not-a-uuid?page=1")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidHeaderNumberIsBadRequest() {
        client.get()
                .uri("/api/convert/orders/" + ID + "?page=1")
                .header("X-Retry", "not-a-number")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void convertsIsoDateFromPath() {
        client.get()
                .uri("/api/convert/day/2026-11-06")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("DAY:2026-11-06");
    }

    @Test
    void invalidDateIsBadRequest() {
        client.get()
                .uri("/api/convert/day/not-a-date")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void customConverterHandlesAlias() {
        client.get()
                .uri("/api/convert/shipping?level=exp")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("LEVEL:EXPRESS");
    }

    @Test
    void unsupportedEnumValueIsBadRequest() {
        client.get()
                .uri("/api/convert/shipping?level=unknown")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void requestParamDoesNotReadFormBody() {
        client.post()
                .uri("/api/convert/form-query")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("QUERY:none|FORM:Lan");
    }

    @Test
    void queryAndFormSameKeyStaySeparate() {
        client.post()
                .uri("/api/convert/form-query?name=Mai")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("QUERY:Mai|FORM:Lan");
    }

    @Test
    void bindsValidFormToModelAttribute() {
        client.post()
                .uri("/api/convert/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "26")
                        .with("newsletter", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("FORM:Lan:26:true");
    }

    @Test
    void badFormNumberIsHandledViaBindingResult() {
        client.post()
                .uri("/api/convert/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "not-a-number"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("FORM_INVALID");
    }

    @Test
    void disallowedFormFieldIsRejected() {
        client.post()
                .uri("/api/convert/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "26")
                        .with("admin", "true"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("FORM_INVALID");
    }

    @Test
    void jsonUsesMessageReaderInsteadOfFormBinder() {
        client.post()
                .uri("/api/convert/json")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"Lan","age":26}
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("JSON:Lan:26");
    }

    @Test
    void invalidJsonDtoIsBadRequest() {
        client.post()
                .uri("/api/convert/json")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"","age":16}
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Chạy từ root của dự án Maven:

~~~bash
./mvnw test -Dtest=WebFluxBindingApplicationTest
~~~

Trên Windows dùng `mvnw.cmd test -Dtest=WebFluxBindingApplicationTest`; nếu đã cài Maven có thể dùng `mvn test -Dtest=WebFluxBindingApplicationTest`. Với Spring Boot 3.x WebFlux, Bean Validation và test starter theo setup trên, **16 test được thiết kế để pass**. Chúng kiểm tra HTTP status thực tế của handler và body do ứng dụng tự trả, không phụ thuộc text lỗi mặc định của Spring.

Tóm tắt các kết quả chính:

| Input | HTTP status | Kết quả ứng dụng mong đợi |
| --- | --- | --- |
| `/orders/{UUID}?page=3&active=true`, `X-Retry: 2` | 200 | `ORDER:{UUID}|page=3|active=true|retry=2` |
| `/orders/{UUID}?page=1` không có optional values | 200 | `active=false|retry=0` |
| Thiếu `page` | 400 | Lỗi required query parameter. |
| UUID path sai cú pháp | 400 | Lỗi conversion path. |
| Header `X-Retry` không phải số | 400 | Lỗi conversion header. |
| `/day/2026-11-06` | 200 | `DAY:2026-11-06` |
| Ngày không theo ISO | 400 | Lỗi chuyển ngày. |
| `/shipping?level=exp` | 200 | `LEVEL:EXPRESS` |
| `/shipping?level=unknown` | 400 | Custom converter không nhận alias. |
| POST form body `name=Lan`, không query name | 200 | `QUERY:none|FORM:Lan` |
| POST query `name=Mai` và form `name=Lan` | 200 | `QUERY:Mai|FORM:Lan` |
| POST form hợp lệ `name=Lan&age=26&newsletter=true` | 200 | `FORM:Lan:26:true` |
| POST form `age=not-a-number` | 400 | `FORM_INVALID` do BindingResult. |
| POST form có `admin=true` ngoài allowlist | 400 | `FORM_INVALID` do suppressed field. |
| POST JSON hợp lệ | 200 | `JSON:Lan:26` |
| POST JSON vi phạm `@NotBlank`/`@Min` | 400 | `WebExchangeBindException` xử lý mặc định. |

**Giới hạn khi áp dụng:** test sử dụng cấu hình Spring Boot WebFlux mặc định, chưa thêm Spring Security. Nếu thêm CSRF, authentication, custom `@ControllerAdvice` hoặc codec configuration, status/response behavior có thể cần cập nhật. Khi muốn test riêng controller không mở cổng, cũng có thể dùng `WebTestClient.bindToController(...)` hoặc `bindToApplicationContext(...)` theo mục tiêu; ở đây integration test dùng `RANDOM_PORT` để kiểm tra đường đi WebFlux thực tế.

### Gửi request thật bằng curl

Khi chạy app bằng `./mvnw spring-boot:run`:

~~~bash
curl -i "http://localhost:8080/api/convert/orders/123e4567-e89b-12d3-a456-426614174000?page=3&active=true" \
  -H "X-Retry: 2"

curl -i -X POST "http://localhost:8080/api/convert/form-query?name=Mai" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan"

curl -i -X POST "http://localhost:8080/api/convert/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan&age=26&newsletter=true"

curl -i "http://localhost:8080/api/convert/shipping?level=exp"
~~~

Đây là ví dụ shell Unix. Trên PowerShell, dùng `curl.exe` và điều chỉnh quoting/line-continuation; không dùng alias `curl` của phiên bản PowerShell cũ rồi mặc định nó hỗ trợ các flags giống GNU curl.

## 11. Error handling: conversion khác validation và đọc body

Không phải tất cả HTTP 400 đều có cùng nguyên nhân:

| Lỗi | Vị trí lỗi trong pipeline WebFlux | Biểu hiện điển hình |
| --- | --- | --- |
| Thiếu query required `page` | Argument resolution của `@RequestParam` | 400, exception thuộc nhóm input/required value. |
| Path `{id}` không chuyển thành UUID | `ConversionService`/argument resolver | 400, lỗi chuyển kiểu. |
| Header `X-Retry: abc` → `int` | `ConversionService`/argument resolver | 400, lỗi chuyển kiểu. |
| Form `age=abc` → Integer | `WebDataBinder`/`BindingResult` | Field error `typeMismatch`; controller nhận `BindingResult` hoặc `WebExchangeBindException`. |
| Form object có `@NotBlank` fail | Bean Validation trên `@ModelAttribute` | `WebExchangeBindException` nếu không được xử lý cục bộ. |
| JSON body hỏng | `HttpMessageReader`/JSON codec | Lỗi đọc/giải mã HTTP body trước khi Bean Validation có object. |
| JSON deserialize thành công nhưng `@Valid` fail | Validation trên `@RequestBody` | `WebExchangeBindException`, thường HTTP 400. |
| Method có constraints trực tiếp trên tham số/return | Method validation | Có thể `HandlerMethodValidationException` tùy signature/version Spring. |
| Không có handler match path | Route matching | 404, khác conversion failure trên path variable đã match. |

Ví dụ lỗi form cục bộ:

~~~java
@PostMapping("/form")
ResponseEntity<String> submit(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        result.getFieldErrors().forEach(error ->
                System.out.println(error.getField()
                        + ":" + error.getCode()));
        return ResponseEntity.badRequest()
                .body("FORM_INVALID");
    }

    return ResponseEntity.ok("OK");
}
~~~

Đây là snippet cần imports và DTO phù hợp, không phải method thứ hai có cùng mapping với demo. Trong production dùng structured logger thay vì in raw input. Không trả `FieldError#getRejectedValue()` ra client khi field có thể chứa password, token, email hoặc thông tin nhạy cảm.

### Tại sao `@RequestParam` không nên dùng để đọc form?

Vì trong WebFlux, parser cho query đã tách riêng với `getFormData()`. Nếu ứng dụng chuyển từ MVC sang WebFlux và giữ ý tưởng "`@RequestParam` luôn nhận form fields", endpoint có thể nhận null hoặc báo required parameter missing dù body có field. Sửa bằng cách dùng `@ModelAttribute` cho form DTO hoặc `ServerWebExchange#getFormData()` khi cần map trực tiếp.

### Khi nào dùng `@RequestBody`?

Khi client gửi **JSON** hoặc một body representation khác cần `HttpMessageReader`/codec. Với JSON, không cần gửi từng field bằng `@RequestParam`; dùng `@RequestBody JsonRegistration` hoặc `Mono<JsonRegistration>` và áp dụng `@Valid`/`@Validated` khi muốn Bean Validation. Đừng trộn body JSON vào form-data binder rồi kỳ vọng behavior giống JSON decoder. Với form-urlencoded, `@ModelAttribute` thường là lựa chọn đơn giản hơn.

## 12. Bảo mật, hiệu năng và vận hành reactive

### 12.1. Mass assignment và dữ liệu không đáng tin

Form binder có thể gán property bằng tên do client cung cấp. Nếu bind thẳng entity chứa `role`, `admin`, `ownerId`, `accountBalance`, user có thể cố gửi các field đó, kể cả trong nested path. Cách giảm rủi ro:

- Dùng **input DTO** có đúng field client được phép sửa; không bind trực tiếp entity persistence nhạy cảm.
- Với property binding, đặt `@InitBinder` và `setAllowedFields(...)` phù hợp; kiểm tra `BindingResult#getSuppressedFields()` nếu muốn chủ động từ chối input ngoài hợp đồng.
- Với constructor binding/immutable DTO, kiểm tra rõ constructor arguments, vì chúng cũng là nguồn dữ liệu từ client; `setAllowedFields` chủ yếu kiểm soát setter/property binding chứ không tự cho phép/không cho phép mọi constructor argument.
- Validation (ví dụ `@NotNull`, `@Min`) không thay thế **authorization**. Quyền sửa entity phải kiểm tra ở service boundary.
- Header, query, path và form đều là untrusted user input, không nên dùng làm trust anchor cho authentication/tenant/role.

### 12.2. Không block event loop

WebFlux hoạt động trên reactive I/O. Các phương thức như `getFormData()`, `getMultipartData()` trả `Mono` vì body cần được decode bất đồng bộ. Không gọi `.block()` ở request handling/event-loop thread để lấy ngay form data; hãy trả `Mono` hoặc kết hợp pipeline bằng `flatMap`.

Custom Converter/Formatter nên nhanh, deterministic, không gọi blocking database hoặc HTTP service. Nếu phải kiểm tra quy tắc nghiệp vụ cần I/O, thực hiện sau bước conversion ở reactive service với API bất đồng bộ, không nhét tác vụ chờ mạng vào converter.

### 12.3. Multipart và giới hạn tài nguyên

Upload file lớn cần quan tâm memory/buffer limits, multipart parser limits, filename/path sanitization, loại file và lifecycle của `DataBuffer`. Không đưa cả file vào `String` hoặc lưu `FilePart` trong singleton. Với `Flux<PartEvent>` streaming, phải tiêu thụ/giải phóng buffers đúng hợp đồng; chỉ dùng streaming API khi thực sự cần.

### 12.4. Locale và chuẩn hóa

`DateTimeFormat`, `NumberFormat` và converter toàn cục có thể chịu ảnh hưởng locale hoặc định dạng nguồn. Với API machine-to-machine, ưu tiên ISO date/time và định dạng số có hợp đồng cố định. Với HTML form cho người dùng, cân nhắc locale/time zone và test input thực tế, không hardcode một format chung nếu UX cần bản địa hóa.

## 13. Checklist chọn đúng nguồn dữ liệu

- [ ] Với `@RequestParam` trong WebFlux: nguồn là **query**, không tự lấy form.
- [ ] Với `@PathVariable`: tên phải khớp URI template và route match trước conversion.
- [ ] Với `@RequestHeader`: tên header phải chính xác, dùng default/optional khi thiếu được phép và không coi header là trusted identity.
- [ ] Với form-urlencoded: chọn `@ModelAttribute` để bind typed DTO, hoặc `ServerWebExchange#getFormData()` để lấy `Mono<MultiValueMap<String,String>>`.
- [ ] Với multipart: dùng `FilePart`/`Part`, `@RequestPart` hoặc `getMultipartData()`; không dùng `MultipartFile` kiểu Servlet trong WebFlux.
- [ ] Với JSON: dùng `@RequestBody` và codec, không kỳ vọng JSON tự biến thành query parameter.
- [ ] Có `@Valid`/`@Validated` nếu cần constraint validation; xử lý `BindingResult` và `WebExchangeBindException` đúng nơi.
- [ ] Có converter/formatter cho `UUID`, `LocalDate`, enum alias hoặc kiểu nghiệp vụ và test input sai kiểu.
- [ ] Không dùng `block()` trên reactive request path; converter/formatter không làm I/O blocking.
- [ ] Form DTO/constructor binding/allowed fields hạn chế mass assignment; quyền cập nhật được kiểm tra riêng.
- [ ] Integration tests bao gồm query/path/header, missing/default, date format, custom Converter, query-vs-form cùng tên, form validation và JSON body.

**Tóm tắt một câu:** Trong Spring WebFlux, **chọn đúng HTTP source trước, rồi mới chuyển kiểu**: `@RequestParam` chỉ đọc query, `@PathVariable` đọc route, `@RequestHeader` đọc header, còn form body dùng `@ModelAttribute` hoặc `getFormData()`. Sự tách biệt nguồn này là khác biệt quan trọng so với Servlet MVC.

## Tài liệu tham khảo

- Spring Framework Reference — WebFlux `@RequestParam` (query-only): https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework Reference — WebFlux `@RequestHeader`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestheader.html
- Spring Framework Reference — WebFlux `@ModelAttribute` và binding form/query/path/header: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — WebFlux Type Conversion: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html
- Spring Framework Reference — Reactive Core, Form/MultiPart Data: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework Reference — WebFlux Multipart and `FilePart`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework Reference — WebFlux Config, `WebFluxConfigurer#addFormatters`: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework Reference — WebFlux `@RequestBody` và validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
