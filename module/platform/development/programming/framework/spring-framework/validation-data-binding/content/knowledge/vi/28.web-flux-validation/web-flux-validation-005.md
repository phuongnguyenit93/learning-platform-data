# Kiểm tra body được bọc trong Mono theo kiểu tham số hỗ trợ — Spring WebFlux

Trong **Spring WebFlux**, controller có thể nhận body JSON qua `@RequestBody` dưới dạng một DTO thông thường hoặc một **reactive wrapper** như `Mono<Dto>`. Với cú pháp **`@Valid @RequestBody Mono<CreateOrderRequest>`**, WebFlux không chỉ đọc và giải mã HTTP body bất đồng bộ: framework còn có thể áp dụng **Jakarta Bean Validation lên đối tượng `CreateOrderRequest` được phát ra bên trong `Mono`**.

Một handler tiêu biểu:

~~~java
@PostMapping("/orders")
public Mono<OrderResult> create(
        @Valid @RequestBody Mono<CreateOrderRequest> requestMono) {
    return requestMono.map(request ->
        new OrderResult(request.code(), request.quantity()));
}
~~~

Đây là đoạn **minh họa chữ ký**, cần DTO và imports phù hợp; chương trình đầy đủ có ở phần 5. Nếu object sau khi giải mã vi phạm `@NotBlank` hay `@Min`, WebFlux thường phát **`WebExchangeBindException`** trên error channel của `Mono`. Nếu không xử lý, Spring mặc định trả HTTP **400 Bad Request**. Nếu muốn phục hồi ngay trong handler, có thể dùng `onErrorResume(WebExchangeBindException.class, ...)`.

Trọng tâm của bài là cụm **“theo kiểu tham số hỗ trợ”**: không phải mọi tham số method đều có thể tùy ý bọc trong `Mono`. `@RequestBody Mono<T>` được hỗ trợ vì giải mã request body là hoạt động bất đồng bộ; một `@RequestParam Mono<Integer>` không đương nhiên là chữ ký hợp lệ theo cùng quy tắc.

**Phiên bản áp dụng:** Spring Framework 6.2, Spring Boot 3.5, Java 17+, WebFlux trên reactive stack. Với Spring MVC trên Servlet stack, argument resolution và loại exception validation có khác biệt; không sao chép tùy tiện.

## 1. Chuỗi xử lý request body trong WebFlux

Ví dụ HTTP request:

~~~http
POST /api/orders/local HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"code":"ORD-7","quantity":2}
~~~

Các thành phần tham gia:

1. `DispatcherHandler` chọn handler theo `@RequestMapping` / `@PostMapping`.
2. Argument resolver của `@RequestBody` dùng **`HttpMessageReader`** và cấu hình message codecs để chuyển JSON bytes thành `CreateOrderRequest`.
3. Nếu tham số gắn `@Valid` (hoặc Spring `@Validated` phù hợp), framework dùng Jakarta Validation provider kiểm tra object đã decode.
4. Nếu hợp lệ, publisher phát `onNext(CreateOrderRequest)` rồi `onComplete`, cho phép các operator `map`/`flatMap` xử lý.
5. Nếu constraint thất bại, publisher phát `onError(WebExchangeBindException)` thay vì chuyển object sai xuống nhánh xử lý bình thường.

~~~text
HTTP body: application/json
            |
            v
@RequestBody argument resolver (WebFlux)
            |
            v
HttpMessageReader / JSON decoder
            |
            +---- malformed JSON ----> lỗi đọc/giải mã
            |
            v
CreateOrderRequest
            |
            v
@Valid -> Jakarta Validator
            |
     +------+------+
     |             |
   Hợp lệ       Không hợp lệ
     |             |
     v             v
Mono.onNext     Mono.onError(
    DTO          WebExchangeBindException)
     |             |
     v             +---- WebFlux default HTTP 400
map / flatMap     hoặc onErrorResume
     |
     v
Response
~~~

Sơ đồ mang tính **khái niệm**; chi tiết class nội bộ và thời điểm subscription thuộc framework. Bản chất quan trọng là **lỗi xảy ra như một tín hiệu của reactive publisher**, khác với một method body Java ném exception đồng bộ ngay khi gọi `map(...)`.

**Không nên làm những việc sau trong controller:** gọi `requestMono.block()` để lấy DTO, tự `subscribe()` rồi trả response rỗng, dùng `Thread.sleep(...)` chờ body, hay coi `Mono` là DTO có method `code()`. Các cách đó có thể phá vỡ non-blocking flow và gây khó kiểm thử.

## 2. “Kiểu tham số hỗ trợ” là điều kiện bắt buộc

Spring WebFlux công bố bảng **supported controller method arguments**. Reactive wrapper được hỗ trợ cho những argument resolver có nhiệm vụ bất đồng bộ, điển hình việc đọc body. **Không có quy tắc chung rằng mọi parameter Java đều được chuyển thành `Mono<...>`.**

| Chữ ký handler | Có phù hợp không? | Nhận xét |
|---|---|---|
| `@Valid @RequestBody Mono<OrderDto> body` | **Có** | Dạng trọng tâm: decode một body thành DTO, validate và phát trong `Mono` |
| `@Valid @RequestBody OrderDto body` | **Có** | DTO trực tiếp; framework phải resolve/validate trước khi gọi handler |
| `@RequestBody Flux<MessageDto> messages` | Có, khi content type và codec hỗ trợ nhiều phần tử | Không tự suy ra cơ chế validation từng phần tử giống hệt `Mono` |
| `@Valid @RequestPart("metadata") Mono<MetaDto> metadata` | Có khi multipart part được decode như DTO | Đây là request part có tên, khác request body JSON đơn |
| `@RequestParam("page") int page` | Có | WebFlux lấy **query parameter**, không cần `Mono<Integer>` |
| `@PathVariable("id") long id` | Có | URI template variable thường được resolve trực tiếp |
| `@RequestHeader("X-Id") String id` | Có | HTTP header không cần một reactive wrapper |
| `@RequestParam("page") Mono<Integer> page` | **Không nên giả định** | Resolver của query parameter không vì thế có cách resolve Mono giống body |
| `Mono<ResponseEntity<T>>` làm **return type** | Có | Cho phép quyết định status và body khi xử lý bất đồng bộ hoàn tất |
| `ResponseEntity<Mono<T>>` làm **return type** | Có | Status/headers được quyết định sớm hơn nội dung body |

**Vì sao `@RequestBody` khác `@RequestParam`?** Body có thể cần đọc bytes theo non-blocking I/O và giải mã qua `HttpMessageReader`. Query/path/header thường đã sẵn có từ request metadata và có resolver đồng bộ về mặt kiểu argument. WebFlux còn có `ConversionService`, nhưng **type conversion không đồng nghĩa với hỗ trợ `Mono` cho mọi annotation**.

### `Mono<T>` hay `Flux<T>`?

- `Mono<T>` phát **0 hoặc 1** giá trị: phù hợp cho **một JSON object**.
- `Flux<T>` phát **0 đến nhiều** giá trị: phù hợp cho stream khi HTTP codec/content type và API contract được thiết kế cho nhiều phần tử.
- Một JSON array thông thường và một stream NDJSON không nhất thiết có cùng encoding/decoding contract. Đừng đổi sang `Flux<T>` chỉ vì muốn trả danh sách, cũng không coi `Mono<List<T>>` tự validate từng phần tử nếu chưa thiết kế constraint/cascade phù hợp.

Tài liệu Spring WebFlux nêu rõ support reactive types ở `@RequestBody` và các kiểu argument cần đọc bất đồng bộ; đây là **khả năng theo từng resolver**, không phải đặc tính mặc định của Java generics.

## 3. `@Valid` đặt trên tham số nhưng kiểm tra đối tượng bên trong Mono

Cú pháp chuẩn được Spring WebFlux mô tả:

~~~java
@PostMapping("/accounts")
public Mono<AccountResult> handle(
        @Valid @RequestBody Mono<AccountRequest> accountMono) {
    return accountMono.map(this::toResult);
}
~~~

Giải thích:

- `@RequestBody` chọn source là **HTTP request body**, không phải query string.
- `Mono<AccountRequest>` nói rằng dữ liệu decode sẽ đến qua **single-value publisher**.
- `@Valid` trên **method parameter** kích hoạt validation của `AccountRequest` do resolver tạo ra.
- Constraint như `@NotBlank`/`@Min` nằm trong **định nghĩa DTO**, không phải gắn trực tiếp lên class `Mono`.
- `accountMono.map(this::toResult)` chỉ nhận DTO **sau khi đã được phát**.

Đừng dùng `@Valid` như một phép thử “input không null”: `@Valid` là **cascade marker**, không phải `@NotNull`. Sự có mặt của một body bắt buộc lại do `@RequestBody(required=true)` và argument resolution kiểm soát. Các quy tắc “body không được thiếu”, “field không được null” và “mã phải hợp lệ nghiệp vụ” là ba yêu cầu khác nhau.

### Nếu quên `@Valid`?

~~~java
@PostMapping("/unchecked")
public Mono<OrderResult> unchecked(
        @RequestBody Mono<CreateOrderRequest> body) {
    return body.map(this::toResult);
}
~~~

Đây là snippet minh họa. Nếu không có validation được kích hoạt ở tầng khác, object có `code=""` vẫn có thể được phát và đưa vào logic xử lý, dù `CreateOrderRequest` có khai báo `@NotBlank`. **Việc DTO có annotation không làm một phép gọi publisher `Mono.just(dto)` tự kích hoạt Jakarta Validation.**

### Nếu chỉ có JSON parse error?

Body `{` không tạo ra DTO hợp lệ về cú pháp. Nó bị decoder từ chối **trước bước Bean Validation**. Vì vậy error có thể là một exception đọc/giải mã input khác `WebExchangeBindException`; không dùng `getFieldErrors()` để phân tích lỗi JSON sai cú pháp.

## 4. Lỗi validation với body reactive khác body trực tiếp

### DTO trực tiếp

~~~java
@PostMapping("/direct")
public OrderResult direct(
        @Valid @RequestBody CreateOrderRequest request) {
    return service.process(request);
}
~~~

WebFlux resolve DTO và kiểm tra trước khi gọi handler. Nếu không hợp lệ, handler thường **không được gọi**; exception được xử lý qua error pipeline ngoài method hoặc một `@ExceptionHandler`/`@ControllerAdvice` thích hợp.

### DTO bên trong Mono

~~~java
@PostMapping("/reactive")
public Mono<OrderResult> reactive(
        @Valid @RequestBody Mono<CreateOrderRequest> body) {

    return body
        .map(service::process)
        .onErrorResume(
            WebExchangeBindException.class,
            ex -> Mono.just(OrderResult.invalid(
                ex.getFieldErrorCount())));
}
~~~

Đây là snippet minh họa, cần các class và service phù hợp. Với `Mono<Dto>`, controller **có thể xây pipeline trước khi body phát ra giá trị hoặc lỗi**. Do đó `onErrorResume` đặt trong pipeline có thể xử lý một validation failure khi nó được phát.

**Cảnh báo HTTP status:** ví dụ `Mono<OrderResult>` phía trên tạo một fallback value và có thể làm response thành HTTP **200** nếu không đặt status. Nếu muốn input sai trả **400**, dùng `Mono<ResponseEntity<OrderResult>>` như chương trình đầy đủ ở phần 5, hoặc để exception đi tới global error handler.

### Tại sao không dùng try/catch?

~~~java
// Phản ví dụ: không bắt được lỗi bất đồng bộ phát trong Mono.
try {
    return body.map(service::process);
} catch (WebExchangeBindException ex) {
    return Mono.just(fallback);
}
~~~

`map(...)` xây dựng pipeline, trong khi lỗi có thể được phát **sau khi method trả về** và framework subscribe. Dùng Reactor operators:

| Operator | Ý nghĩa | Cần nhớ |
|---|---|---|
| `onErrorResume(WebExchangeBindException.class, handler)` | Phục hồi lỗi bằng một publisher khác | Thích hợp để tạo response 400 có cấu trúc |
| `onErrorMap(...)` | Đổi loại lỗi rồi tiếp tục error channel | Không tự làm response thành công |
| `doOnError(...)` | Quan sát/log lỗi | Không tiêu thụ lỗi |
| `onErrorReturn(...)` | Trả fallback cố định | Không thích hợp nếu cần field errors |
| `switchIfEmpty(...)` | Xử lý publisher **hoàn thành rỗng** | Empty không phải error signal |

Không dùng `onErrorResume(Exception.class,...)` để nuốt tất cả lỗi decoder, lỗi lập trình, lỗi kết nối DB và lỗi validation rồi trả 200. Ranh giới lỗi nên rõ: constraint DTO, malformed JSON, thiếu body và domain/service failure thường cần phản hồi khác nhau.

## 5. Chương trình Spring Boot chạy được: ba cách nhận body

Ví dụ dùng **Spring Boot 3.5.x + Spring Framework 6.2.x + Java 17+** với **chỉ WebFlux starter**, không thêm Servlet MVC starter. Có ba endpoint:

- `POST /api/orders/local` nhận `Mono<DTO>` và xử lý `WebExchangeBindException` ngay trong publisher, trả **201** hoặc **400**.
- `POST /api/orders/default` cũng nhận `Mono<DTO>` nhưng để WebFlux xử lý validation error mặc định thành **400**.
- `POST /api/orders/direct` nhận DTO trực tiếp, chứng minh validation có thể xảy ra trước lời gọi handler.

### 5.1. Gradle dependencies

Trong project Spring Boot đã có plugin và dependency version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

WebFlux starter cung cấp reactive web stack và Reactor; validation starter cung cấp Jakarta Validation implementation. Các file Java dưới đây cần classpath Spring/Boot: **không thể biên dịch chỉ bằng JDK `javac` thuần**. Dùng Gradle wrapper của project Boot hiện hữu hoặc project tạo bằng Spring Initializr.

Đừng thêm `spring-boot-starter-web` vào demo này: khi đồng thời có WebFlux và Spring MVC, Boot thông thường ưu tiên Servlet web application type, và bài toán validation sẽ không còn dùng WebFlux pipeline như mô tả.

### 5.2. `MonoBodyApplication.java`

Tạo `src/main/java/com/example/webfluxmono/MonoBodyApplication.java`:

~~~java
package com.example.webfluxmono;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MonoBodyApplication {

    public static void main(String[] args) {
        SpringApplication.run(MonoBodyApplication.class, args);
    }
}
~~~

### 5.3. `CreateOrderRequest.java`

Tạo `src/main/java/com/example/webfluxmono/CreateOrderRequest.java`:

~~~java
package com.example.webfluxmono;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String code,
    @Min(1) int quantity
) {
}
~~~

DTO có hai constraint: `code` phải có nội dung khác whitespace, `quantity` phải ≥1. Request:

~~~json
{"code":"","quantity":0}
~~~

decode được thành record, nhưng **vi phạm hai constraints**. Cả hai lỗi là `FieldError` tương ứng, không có constraint cấp class trong demo.

### 5.4. `CreateOrderController.java`

Tạo `src/main/java/com/example/webfluxmono/CreateOrderController.java`:

~~~java
package com.example.webfluxmono;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class CreateOrderController {

    @PostMapping(
        path = "/local",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<OrderReply>> createLocally(
            @Valid @RequestBody Mono<CreateOrderRequest> body) {

        return body.map(request ->
                ResponseEntity.status(HttpStatus.CREATED).body(
                    new OrderReply(
                        true, request.code(), request.quantity(), 0)))
            .onErrorResume(
                WebExchangeBindException.class,
                ex -> Mono.just(
                    ResponseEntity.badRequest().body(
                        new OrderReply(
                            false, null, 0,
                            ex.getFieldErrorCount()))));
    }

    @PostMapping(
        path = "/default",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<OrderReply> createWithDefaultError(
            @Valid @RequestBody Mono<CreateOrderRequest> body) {

        return body.map(request ->
            new OrderReply(
                true, request.code(), request.quantity(), 0));
    }

    @PostMapping(
        path = "/direct",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderReply createWithDirectBody(
            @Valid @RequestBody CreateOrderRequest request) {

        return new OrderReply(
            true, request.code(), request.quantity(), 0);
    }

    public record OrderReply(
        boolean accepted,
        String code,
        int quantity,
        int errorCount
    ) {
    }
}
~~~

**Giải thích đường reactive `/local`:**

1. `@Valid @RequestBody Mono<CreateOrderRequest>` là một handler argument **được WebFlux hỗ trợ**.
2. Nếu decode và validate thành công, `map` chạy, tạo `ResponseEntity` có status **201 Created** và `OrderReply(accepted=true,...)`.
3. Nếu validation thất bại, `map` không nhận DTO; `onErrorResume(WebExchangeBindException.class,...)` trả `Mono.just(ResponseEntity.badRequest().body(...))`.
4. `getFieldErrorCount()` trả số field errors. Với `code=""` và `quantity=0` trong demo, kết quả là **2**.
5. `Mono<ResponseEntity<OrderReply>>` cho phép status **được chọn sau khi biết kết quả**. Không dùng `ResponseEntity<Mono<OrderReply>>` nếu phải đổi status sau validation.
6. Handler không gọi `block()`/`subscribe()`. Framework quản lý subscription và response rendering.

**Đường `/default`** không dùng error recovery, nên WebFlux có thể tự trả HTTP 400 cho `WebExchangeBindException`. Body lỗi mặc định có thể khác theo cấu hình Spring Boot, do đó không cố định một JSON cụ thể.

**Đường `/direct`** nhận DTO trực tiếp; nếu validation thất bại, method không được gọi để tạo `OrderReply`. Đây là điều khác biệt quan trọng với cơ hội xử lý bằng Reactor operators trong handler có `Mono` input.

### 5.5. Chạy và thử bằng curl

Từ thư mục project Spring Boot có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu cổng mặc định chưa đổi, thử request hợp lệ:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/local" \
  -H "Content-Type: application/json" \
  -d '{"code":"ORD-7","quantity":2}'
~~~

Kỳ vọng HTTP **201 Created**, JSON (thứ tự key không phải hợp đồng):

~~~json
{
  "accepted": true,
  "code": "ORD-7",
  "quantity": 2,
  "errorCount": 0
}
~~~

Thử request decode được nhưng sai cả hai constraints:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/local" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Kỳ vọng HTTP **400 Bad Request**, JSON do ứng dụng tự thiết kế:

~~~json
{
  "accepted": false,
  "code": null,
  "quantity": 0,
  "errorCount": 2
}
~~~

Gửi cùng dữ liệu tới `/default`:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/default" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Kỳ vọng **HTTP 400** của framework; không có cam kết rằng body mặc định sẽ có field `accepted` hay `errorCount`.

Gửi tới `/direct`:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/direct" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Kỳ vọng **HTTP 400** do DTO validation, nhưng handler trực tiếp không có `Mono` input để gắn `onErrorResume`.

JSON sai cú pháp:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/local" \
  -H "Content-Type: application/json" \
  -d '{'
~~~

Kỳ vọng **400** do decoder/input error, **không phải** response JSON `OrderReply` từ nhánh `WebExchangeBindException`. Không có DTO đã được tạo hợp lệ nên chưa có field constraints để xét.

Không gửi body cho `@RequestBody` với `required=true` (mặc định) thường cũng khiến WebFlux từ chối request với HTTP 400 ở bước đọc/resolve input, không phải tự tạo `CreateOrderRequest` trống.

## 6. Kiểm thử bằng WebTestClient

Để kiểm chứng thực sự `@Valid @RequestBody Mono<T>` đi qua **argument resolver, JSON decoder, validator và reactive error channel**, nên dùng HTTP integration test. Một unit test gọi `controller.createLocally(Mono.just(dto))` trực tiếp không bao gồm Spring request-body validation, nên có thể cho kết quả sai lệch.

File `src/test/java/com/example/webfluxmono/CreateOrderControllerTest.java`:

~~~java
package com.example.webfluxmono;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CreateOrderControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void validMonoBodyProducesCreatedResponse() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("ORD-7", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo(true)
            .jsonPath("$.code").isEqualTo("ORD-7")
            .jsonPath("$.quantity").isEqualTo(2)
            .jsonPath("$.errorCount").isEqualTo(0);
    }

    @Test
    void invalidMonoBodyCanBeRecoveredLocally() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo(false)
            .jsonPath("$.errorCount").isEqualTo(2);
    }

    @Test
    void invalidMonoBodyDefaultsToBadRequest() {
        client.post()
            .uri("/api/orders/default")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void directDtoIsAlsoValidated() {
        client.post()
            .uri("/api/orders/direct")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void malformedJsonIsADecodingError() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void missingRequiredBodyIsBadRequest() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Với Spring Boot 3.5/WebFlux/Validation starters và cấu hình mặc định, sáu test kỳ vọng **PASS**. `RANDOM_PORT` chạy server thực; `WebTestClient` gửi HTTP requests thay vì gọi method Java trực tiếp. Các test cố ý **không** kiểm tra body lỗi mặc định `/default`, vì error JSON của Boot/ProblemDetail có thể thay đổi; chỉ response do `/local` tự tạo được kiểm tra field values cụ thể.

## 7. Vì sao `Errors` hoặc `BindingResult` không theo sau `Mono<Dto>`?

Tài liệu Spring WebFlux cho phép dùng `Errors`/`BindingResult` cho body argument **không bọc Mono**, với điều kiện method signature phù hợp:

~~~java
@PostMapping("/form")
public AccountReply form(
        @Valid @RequestBody AccountRequest request,
        org.springframework.validation.Errors errors) {

    if (errors.hasErrors()) {
        return AccountReply.invalid(errors.getErrorCount());
    }
    return AccountReply.success(request);
}
~~~

Đây là **snippet minh họa**, cần `AccountRequest`/`AccountReply` được định nghĩa. Khi body là DTO trực tiếp, framework có thể resolve và validate trước khi gọi method rồi cung cấp `Errors` đồng bộ.

Không sao chép thành:

~~~java
// Phản ví dụ về ý định xử lý lỗi:
@PostMapping("/wrong")
public Mono<AccountReply> wrong(
        @Valid @RequestBody Mono<AccountRequest> accountMono,
        org.springframework.validation.BindingResult errors) {
    // Không thể giả định errors đã chứa kết quả
    // của một Mono<AccountRequest> chưa phát dữ liệu.
}
~~~

Với `Mono<Dto>`, body và validation errors có thể được phát **sau khi handler đã được gọi**. `BindingResult` đồng bộ đặt cạnh reactive argument không cung cấp hợp đồng xử lý như với DTO trực tiếp. Spring nêu rõ muốn nhận `Errors` ngay sau `@RequestBody` thì **body không được là Mono**.

Đúng cách cho một Mono body:

~~~java
return accountMono
    .map(AccountReply::success)
    .onErrorResume(
        WebExchangeBindException.class,
        ex -> Mono.just(
            AccountReply.invalid(ex.getErrorCount())));
~~~

Đây là snippet tùy chọn; nó có thể tạo body lỗi nhưng **không tự chuyển HTTP status thành 400** khi kiểu trả về chỉ là `Mono<AccountReply>`. Hãy dùng `Mono<ResponseEntity<AccountReply>>` hoặc để lỗi truyền tới global error handling nếu HTTP status là một phần của contract.

## 8. Hiểu `WebExchangeBindException` và các lỗi khác

`WebExchangeBindException` nằm tại:

~~~java
import org.springframework.web.bind.support.WebExchangeBindException;
~~~

Nó đại diện lỗi binding/validation trên một method argument và chứa thông tin kiểu `BindingResult`. Một số API hữu ích:

~~~java
int allErrors = ex.getErrorCount();
int fieldErrors = ex.getFieldErrorCount();

for (var error : ex.getFieldErrors()) {
    String field = error.getField();
    String messageCode = error.getCode();
    String defaultMessage = error.getDefaultMessage();
}
~~~

Đoạn trên là snippet trong một handler có biến `ex`. Nên dùng field/message codes để tạo response ổn định và đa ngôn ngữ; không dựa vào thứ tự các errors hay nội dung message đã dịch.

| API | Ý nghĩa |
|---|---|
| `getErrorCount()` | Tổng lỗi field + global/object |
| `getFieldErrorCount()` | Số field error entries, **không nhất thiết bằng số field khác nhau** |
| `getFieldErrors()` | Các lỗi gắn vào field cụ thể |
| `getGlobalErrors()` | Các lỗi ở cấp object |
| `getFieldError("code")` | Một lỗi liên quan `code` nếu có |
| `getAllErrors()` | Lỗi có thể xử lý qua Spring message resolution |

Nếu một field vi phạm hai constraints, có thể có hai `FieldError` cho cùng field. Nếu DTO khai báo class-level constraint, có thể có **global error**. Vì thế không nên nói “số lượng field sai chính là `getFieldErrorCount()`” cho mọi dự án.

### Phân biệt lỗi decode với validation

| Dữ liệu HTTP | Pha | Hành vi thường gặp |
|---|---|---|
| `{"code":"ORD-7","quantity":2}` | Decode → validate OK | `Mono` phát DTO |
| `{"code":"","quantity":0}` | Bean Validation thất bại | `WebExchangeBindException`, mặc định HTTP 400 |
| `{` | JSON decode thất bại | Lỗi đọc/giải mã, thường HTTP 400 |
| Body thiếu với `@RequestBody(required=true)` | Required-body check | Thường HTTP 400 |
| JSON type không tương thích với Java property | Decode/convert | Input error trước constraint |
| DTO hợp lệ nhưng chính sách nghiệp vụ từ chối | Service/domain policy | Exception/status do ứng dụng thiết kế |
| Direct constraint trên một handler parameter khác | Method validation | Có thể phát `HandlerMethodValidationException` |

Một `onErrorResume(WebExchangeBindException.class, ...)` **không** nên xử lý mọi lỗi được liệt kê. Nó chỉ thể hiện trách nhiệm phục hồi các lỗi mà nó bắt đúng kiểu. Khi cần trả response đồng nhất cho nhiều loại lỗi, triển khai Spring WebFlux `@RestControllerAdvice` với các handlers riêng hoặc dùng cơ chế `ErrorResponse`/ProblemDetail phù hợp.

### Global advice hay phục hồi cục bộ?

Nếu chỉ một endpoint cần một response lỗi riêng, local recovery tiện và có thể kiểm soát status khi return `Mono<ResponseEntity<T>>`. Nếu nhiều controllers phải dùng chung JSON errors, có thể để exception thoát khỏi publisher và dùng `@RestControllerAdvice`/`@ExceptionHandler(WebExchangeBindException.class)`. **Lỗi đã phục hồi cục bộ sẽ không tiếp tục tới global advice**. Chọn một thiết kế có chủ đích.

## 9. Phân biệt `WebExchangeBindException` với method validation

Spring WebFlux 6.1+ còn có **built-in method validation**. `@Valid` trên DTO là cascade marker, **không phải direct constraint**. Nếu handler chỉ có `@Valid @RequestBody Mono<Dto>`, trường hợp thông thường là validation một argument riêng và `WebExchangeBindException`.

Nếu handler có constraint trực tiếp như `@Min`/`@NotBlank` trên một parameter khác:

~~~java
@PostMapping("/submit")
public Mono<OrderReply> submit(
        @Valid @RequestBody Mono<CreateOrderRequest> body,
        @RequestParam("channel")
        @NotBlank String channel) {
    return body.map(this::toReply);
}
~~~

đây là **snippet minh họa khác** với ứng dụng demo. Direct constraint trên `channel` có thể kích hoạt **method validation**, theo đó loại lỗi là **`HandlerMethodValidationException`** khi cơ chế built-in tương ứng áp dụng. Đừng giả định chỉ cần catch `WebExchangeBindException` là đủ cho mọi chữ ký có `Mono<Dto>`.

Nếu controller có **class-level Spring `@Validated`**, method validation có thể được chạy qua **AOP proxy** thay vì cơ chế built-in WebFlux/MVC 6.1+; loại lỗi và thời điểm xử lý cũng có thể khác. Không thêm `@Validated` cấp class vô cớ vào demo muốn minh họa validation của `@RequestBody Mono<Dto>`.

So sánh:

| Môi trường | Validation body DTO | Lỗi thông thường |
|---|---|---|
| Spring WebFlux `@Valid @RequestBody Mono<Dto>` | Reactive body resolver + Jakarta Validation | `WebExchangeBindException` trong publisher |
| Spring WebFlux `@Valid @RequestBody Dto` | Argument-level validation | `WebExchangeBindException` ở bước resolve |
| Spring MVC `@Valid @RequestBody Dto` | Servlet MVC argument validation | `MethodArgumentNotValidException` |
| WebFlux/MVC built-in method validation | Direct method constraints + cascade liên quan | `HandlerMethodValidationException` |
| Spring AOP service method validation | Bean `@Validated` qua proxy | Thường `ConstraintViolationException` mặc định |

**Điểm kiểm tra quan trọng:** nếu test `@Valid @RequestBody Mono<Dto>` mà lại dựa trên `MethodArgumentNotValidException` từ ví dụ Spring MVC, bạn đang dùng sai web stack hoặc đang nhầm đường validation.

## 10. Hiệu năng, non-blocking và bảo mật

### 10.1. Validation chưa phải là xác thực quyền

`@NotBlank` và `@Min` chỉ bảo vệ hình dạng dữ liệu. Một đơn hàng có code hợp lệ vẫn có thể bị từ chối vì người dùng không có quyền, mã trùng hoặc hàng hết tồn. Authorization và domain validation phải nằm ở service/security layer, không chỉ ở DTO constraint.

### 10.2. Tránh blocking custom validators

`ConstraintValidator.isValid(...)` thuộc Jakarta Validation là API **đồng bộ**. Nếu một custom validator gọi JDBC hoặc HTTP client blocking, nó có thể làm nghẽn Reactor event loop ngay cả khi handler trả `Mono`. Giữ các constraint cấu trúc nhanh; chuyển các business checks cần I/O bất đồng bộ vào `flatMap(service::check)` với driver/client reactive hoặc scheduler phù hợp.

### 10.3. Không log rejected secrets

`WebExchangeBindException` có thể chứa rejected values. Không ghi toàn bộ request body, password hay token ra log hoặc phản hồi công khai. Dùng field names/message codes và correlation ID đã được rà soát.

### 10.4. Không biến Mono thành bảo đảm streaming body lớn

Một JSON object rất lớn vẫn cần được decoder dựng thành DTO theo codec/buffer limits. `Mono<Dto>` không tự động giảm memory cost chỉ vì được bọc reactive. Nếu cần stream liên tục, thiết kế HTTP content type và `Flux<T>` thích hợp, xác định cách validate từng phần tử và cách xử lý lỗi khi response đã bắt đầu.

## 11. Lỗi phổ biến và cách kiểm tra

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `@Valid @RequestBody Mono<Dto>` không kiểm tra field | Thiếu provider, annotation sai vị trí, DTO không có constraint | Cài validation starter; kiểm tra `jakarta.validation.*` |
| DTO sai vẫn đi vào service | Chưa kích hoạt validation của body resolver | Đặt `@Valid` trên handler parameter; test qua WebTestClient |
| `onErrorResume(WebExchangeBindException.class, ...)` không bắt body `{` | Lỗi JSON decoding, chưa có DTO | Xử lý decoder error riêng hoặc để WebFlux trả lỗi |
| Dùng `try/catch` quanh `map` nhưng lỗi lọt ra | Lỗi được phát khi subscribe publisher | Dùng Reactor error operators |
| JSON invalid được trả HTTP 200 kèm `accepted=false` | Chỉ trả fallback DTO không đổi status | Trả `Mono<ResponseEntity<...>>` hoặc global error handling |
| `BindingResult` sau `Mono<Dto>` không hoạt động như mong đợi | Kết quả validate chưa có đồng bộ | Dùng `onErrorResume` trong pipeline |
| `block()` gây lỗi hoặc làm chậm server | Chặn reactive event loop | Không block; trả publisher và dùng map/flatMap |
| Lỗi query constraint không phải `WebExchangeBindException` | Direct method constraint kích hoạt method validation | Xem `HandlerMethodValidationException` |
| Spring Boot vào MVC thay vì WebFlux | Có cả starter web và webflux | Dùng WebFlux-only hoặc chọn application type có chủ đích |
| Bài test gọi method Java trực tiếp không phát lỗi validation | Bỏ qua argument resolver + HTTP pipeline | Dùng WebTestClient integration |
| Test body lỗi mặc định thay đổi | Framework/locale/problem details config khác | Test status và contract do app định nghĩa |
| FieldErrorCount khác số field sai | Một field có nhiều violations hoặc object-level errors | Duyệt `getFieldErrors()`/`getGlobalErrors()` |
| `@RequestParam Mono<Integer>` không resolve | Không phải mọi argument support reactive wrapper | Đọc bảng supported method arguments |
| Lỗi sau custom constraint I/O làm app ì | Validator blocking trong reactive pipeline | Tách business I/O sang reactive service |
| Global exception advice không chạy | Local `onErrorResume` đã phục hồi lỗi | Chọn một boundary xử lý nhất quán |

**Trình tự debug:** xác nhận WebFlux stack → dependency Jakarta provider → handler argument được hỗ trợ → `@Valid` đúng vị trí → JSON decode có thành công không → có `WebExchangeBindException` trên error channel không → `onErrorResume`/global handler ở đâu → status được quyết định trước hay sau publisher → test end-to-end bằng WebTestClient.

## 12. Câu hỏi luyện tập

**1. Tại sao Spring WebFlux hỗ trợ `@Valid @RequestBody Mono<Dto>` mà không bảo đảm `@RequestParam Mono<Integer>` cũng hoạt động?**

Vì hỗ trợ reactive wrapper là đặc tính của **từng HandlerMethodArgumentResolver**; đọc body có I/O bất đồng bộ, còn query param được resolve theo cơ chế riêng.

**2. `@Valid` có kiểm tra chính `Mono` không?**

Trong use case này, framework validate **DTO được decoder tạo ra bên trong Mono**, không phải kiểm tra `Mono` như một JavaBean chứa field `code`.

**3. `Mono.just(dto)` trong unit test có tự kiểm tra `@NotBlank` không?**

Không. Reactor không tự chạy Bean Validation. Phải có bước validation do WebFlux resolver, service hoặc `jakarta.validation.Validator` kích hoạt.

**4. Với body `{"code":"","quantity":0}`, lỗi nào được kỳ vọng?**

`WebExchangeBindException` vì DTO decode được nhưng vi phạm cả `@NotBlank` và `@Min(1)`.

**5. Với body `{`, có phải `WebExchangeBindException` không?**

Không nhất thiết. Body sai cú pháp có thể bị JSON decoder từ chối **trước validation**.

**6. Vì sao `BindingResult` không nên đặt ngay sau `Mono<Dto>`?**

Vì validation của object trong publisher có thể diễn ra bất đồng bộ. Dùng `onErrorResume` thay cho kết quả lỗi đồng bộ.

**7. Sự khác nhau giữa `Mono<ResponseEntity<T>>` và `ResponseEntity<Mono<T>>` là gì?**

Kiểu đầu cho phép quyết định cả status/body **sau khi** publisher có kết quả; kiểu sau thường xác định status/headers **trước khi** inner publisher phát body.

**8. Khi nào nên dùng `flatMap`?**

Khi downstream action trả publisher, chẳng hạn `service.createReactive(request)`. `map` phù hợp cho biến đổi đồng bộ nhẹ không trả reactive type.

**9. Thêm direct `@NotBlank` trên query parameter sẽ luôn ném `WebExchangeBindException` không?**

Không. Built-in method validation có thể được kích hoạt và đưa tới `HandlerMethodValidationException`.

**10. Vì sao test bằng WebTestClient tốt hơn gọi handler trực tiếp?**

Nó đi qua HTTP codecs, argument resolver, body validation, Reactor error channel và response handling thực tế, thay vì chỉ chạy Java method body.

## 13. Checklist triển khai

- [ ] Ứng dụng thật sự chạy Spring WebFlux với validation provider tương thích Spring 6/Boot 3.
- [ ] Request chứa một JSON object: dùng `Mono<Dto>` và `@RequestBody` tại handler parameter.
- [ ] Đặt `@Valid` hoặc `@Validated` đúng vị trí, constraint nằm trong DTO.
- [ ] Không tùy ý bọc query/path/header arguments bằng Mono nếu resolver không hỗ trợ.
- [ ] Phân biệt lỗi decode, thiếu body và lỗi Bean Validation.
- [ ] Xử lý `WebExchangeBindException` qua Reactor operators hoặc global error handler, không dựa vào `try/catch` thông thường.
- [ ] Không sử dụng synchronous `BindingResult` sau body argument có `Mono`.
- [ ] Nếu status phụ thuộc validation, dùng `Mono<ResponseEntity<T>>`.
- [ ] Không dùng `block()`/`subscribe()` trong controller.
- [ ] Kiểm tra direct method constraints khác có thể dẫn tới `HandlerMethodValidationException`.
- [ ] Giữ authorization/domain policy tách khỏi DTO structure constraints.
- [ ] Kiểm thử HTTP hợp lệ, invalid DTO, malformed JSON, body thiếu và default error với WebTestClient.

**Ghi nhớ:** `@Valid @RequestBody Mono<T>` là chữ ký **được Spring WebFlux hỗ trợ**. Framework decode body bằng `HttpMessageReader`, kiểm tra `T` qua Jakarta Validation, sau đó đưa giá trị hoặc `WebExchangeBindException` vào reactive pipeline. Xử lý lỗi bằng **`onErrorResume` hoặc global handler**, không dùng `BindingResult` đồng bộ sau `Mono`; lựa chọn `Mono<ResponseEntity<T>>` giúp giữ đúng HTTP status.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Supported Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html)
- [Spring API — WebExchangeBindException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Project Reactor — Error Handling Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
