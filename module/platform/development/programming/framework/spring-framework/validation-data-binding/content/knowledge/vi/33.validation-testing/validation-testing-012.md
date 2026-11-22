# WebTestClient cho WebFlux và lỗi trong luồng phản ứng

## Mục tiêu và phạm vi

Trong Spring WebFlux, một handler có thể trả một giá trị `Mono<T>`, một chuỗi `Flux<T>`, hoặc một stream không kết thúc như Server-Sent Events (SSE). Khi kiểm thử, chỉ xác nhận HTTP status chưa đủ: chúng ta còn cần biết **lỗi xảy ra trước hay sau khi response bắt đầu**, publisher đã phát giá trị nào, có phát tín hiệu `onError` hay không, luồng có hoàn thành hoặc được hủy đúng cách không, và lỗi validation có được chuyển thành phản hồi HTTP thích hợp không.

**WebTestClient** là HTTP testing client của Spring, hoạt động được với WebFlux mock server hoặc server thật. **StepVerifier** thuộc `reactor-test` kiểm tra thứ tự tín hiệu Reactive Streams trên `Mono`/`Flux`. Hai công cụ bổ trợ, không thay thế nhau.

Sau bài này, bạn sẽ:

1. Chọn đúng giữa `WebTestClient.bindToController`, `bindToApplicationContext`, `bindToRouterFunction` và `bindToServer`.
2. Kiểm tra status, headers, JSON body, response errors và body trống với `exchange()`, `expectStatus()`, `expectHeader()`, `expectBody()`.
3. Phân biệt `WebExchangeBindException`, `HandlerMethodValidationException` và `ServerWebInputException` trong pipeline WebFlux.
4. Kiểm thử lỗi một field, lỗi toàn object và nested validation paths bằng `@Valid @RequestBody`.
5. Dùng `FluxExchangeResult<T>` cùng `StepVerifier` để nhận stream `text/event-stream` mà không thu thập vô hạn.
6. Viết test cho `onNext`, `onComplete`, `onError`, `onErrorResume`, hủy stream (`cancel`), timeout và virtual time.
7. Giải thích tại sao lỗi **trước khi response được commit** có thể được map thành HTTP 4xx/5xx, còn lỗi sau khi đã phát bytes thì không thể bảo đảm đổi status/header.
8. Chạy một project Java 17+ / Spring Boot 3.5.7 với annotated WebFlux controllers, Bean Validation, SSE, domain errors và test HTTP/service/slice.
9. Phân biệt kiểm thử luồng phản ứng với kiểm thử security, data binding, backpressure và resource cleanup; tránh `block()` trong handler và tránh test không bao giờ kết thúc.

## 1. WebFlux và Reactive Streams: những điều test phải quan sát

Spring WebFlux là web stack phản ứng của Spring, hoạt động với Reactor/Reactive Streams. Khi gọi một endpoint:

~~~text
HTTP request
     |
     v
WebFilter / DispatcherHandler
     |
     v
HttpMessageReader (JSON/form/body)
     |
     v
Binding + Jakarta Bean Validation
     |
     v
Controller -> Mono<T> hoặc Flux<T>
     |
     v
HttpMessageWriter -> HTTP response
                  |
                  +-- status/headers
                  +-- 0..N chunks/events
                  +-- complete hoặc error/cancel
~~~

Ở cấp Publisher có bốn loại tín hiệu cần quan sát:

- `onSubscribe`: thiết lập subscription và yêu cầu demand.
- `onNext(value)`: có một phần tử hợp lệ được phát.
- `onComplete`: publisher kết thúc thành công; chỉ phát một lần sau mọi `onNext`.
- `onError(exception)`: publisher kết thúc vì lỗi; loại trừ `onComplete` cho subscription ấy.

**Cancellation** do subscriber yêu cầu không phải là `onComplete` hay `onError`: khi client ngắt kết nối hoặc test gọi `thenCancel()`, publisher phải dừng nếu tuân thủ cancellation. Với stream vô hạn, đòi `verifyComplete()` không có điều kiện dừng là cách tạo test treo.

### 1.1. Mono và Flux khác thế nào trong test?

| Kiểu | Số giá trị | Kiểm thử thường dùng |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | `expectNext(value).verifyComplete()`, `verifyError(...)` |
| `Flux<T>` hữu hạn | 0..N | `expectNext(...)`, `expectNextCount(...)`, `verifyComplete()` |
| `Flux<T>` vô hạn | không có complete theo thiết kế | `expectNextCount(n).thenCancel().verify(...)` |
| `Flux<T>` có lỗi giữa chừng | vài `onNext` rồi `onError` | `expectNext(...).expectError(...).verify(...)` |
| `Flux<T>` đã phục hồi lỗi | `onErrorResume` thay chuỗi lỗi bằng fallback | `expectNext(...).expectNext(fallback).verifyComplete()` |

Không đánh đồng kết quả HTTP 200 và publisher thành công hoàn toàn. Với streaming response, HTTP status có thể đã gửi trước khi publisher phát lỗi. Ngược lại, nếu lỗi xảy ra trước khi response commit, Spring vẫn có cơ hội render một phản hồi 400/404/500 có cấu trúc.

## 2. Bốn chế độ khởi tạo WebTestClient

`org.springframework.test.web.reactive.server.WebTestClient` cung cấp nhiều cách gắn server-under-test.

### 2.1. Bind trực tiếp controller: nhanh, cô lập

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ExampleController())
        .build();
~~~

Không mở cổng mạng, sử dụng WebFlux mock request/response và cơ sở hạ tầng tương ứng. Nếu controller có dependency như service, cần tự truyền dependency thật/giả. Cấu hình global `@ControllerAdvice`, codecs, validation, filters tùy biến từ application thật **không tự động giống production**: hãy đăng ký các thành phần cần thiết trong builder khi test cô lập.

Ví dụ bổ sung một advice:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ExampleController())
        .controllerAdvice(new ExampleErrorAdvice())
        .build();
~~~

Đây là snippet khi đã định nghĩa hai classes. Không phải mọi object tự tạo đều có Bean Validation/MessageSource auto-configuration giống full Spring Boot context.

### 2.2. Bind vào ApplicationContext: giữ cấu hình, không cần server thật

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("/api")
        .build();
~~~

Thường dùng với `@SpringBootTest` + `@AutoConfigureWebTestClient` hoặc một slice `@WebFluxTest`. Không cần mở network port nhưng có đầy đủ những beans thực sự nạp trong context đó. Cần phân biệt **context thực** và **slice**: slice chỉ load web-related components nên service/repository có thể chưa tồn tại.

### 2.3. Bind vào functional RouterFunction

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route()
                .GET("/ping", request ->
                        ServerResponse.ok()
                                .bodyValue("pong"))
                .build();

WebTestClient client = WebTestClient
        .bindToRouterFunction(route)
        .build();
~~~

Đây là snippet dùng imports `RouterFunctions`, `RouterFunction`, `ServerResponse`. Hữu ích cho WebFlux.fn (functional endpoints) thay vì annotated `@RestController`.

### 2.4. Bind tới server HTTP đang chạy

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Kiểm thử end-to-end qua HTTP thật, có ảnh hưởng của Netty, serialization, network connection, cancellation và streaming flush. Với Spring Boot 3.5, `@SpringBootTest(webEnvironment = RANDOM_PORT)` có thể inject một `WebTestClient` kết nối tới test server, khi WebFlux và hạ tầng test phù hợp có trên classpath.

| Chế độ | Server socket | Test phù hợp | Giới hạn |
| --- | --- | --- | --- |
| `bindToController` | Không | Controller nhỏ, mapping, response | Phải đăng ký advice/filter/validator cần thiết |
| `bindToApplicationContext` | Không | Web handler chain, cấu hình web | Không kiểm network-level behavior |
| `bindToRouterFunction` | Không | Functional routing | Không tự kiểm toàn ứng dụng |
| `bindToServer` | Có | HTTP thực, SSE, hủy kết nối | Chậm hơn, cần lifecycle/port và timeout |

## 3. Những assertion phổ biến của WebTestClient

### 3.1. Kiểm tra status và JSON body

~~~java
client.post()
        .uri("/api/reads")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(validRequest)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.result").isEqualTo("accepted")
        .jsonPath("$.lineCount").isEqualTo(1);
~~~

Đây là snippet nếu `client` và `validRequest` đã được định nghĩa. `exchange()` thực thi request, trả một `ResponseSpec` để assert. `jsonPath(...)` kiểm cấu trúc, không phụ thuộc khoảng trắng hay thứ tự object keys.

### 3.2. Body rỗng và một object

~~~java
client.delete().uri("/api/reads/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
~~~

Nếu response là JSON object:

~~~java
Receipt receipt = client.get().uri("/api/reads/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Receipt.class)
        .returnResult()
        .getResponseBody();
~~~

Hai snippets dùng controller/DTO tương ứng. `expectBody(Receipt.class)` decode và **thu thập** body, hợp với finite JSON response. Với `Flux` vô hạn, đừng dùng cách này để đợi toàn bộ response.

### 3.3. Generic types

Khi JSON là danh sách hoặc container có generic type:

~~~java
ParameterizedTypeReference<List<Receipt>> type =
        new ParameterizedTypeReference<>() {};

List<Receipt> list = client.get()
        .uri("/api/reads/all")
        .exchange()
        .expectStatus().isOk()
        .expectBody(type)
        .returnResult()
        .getResponseBody();
~~~

Snippet cần endpoint `/all` tương ứng và imports của Spring. WebTestClient còn có `expectBodyList(Receipt.class)` cho danh sách thông thường. Dùng `ParameterizedTypeReference` giúp giữ thông tin generic khi decoding.

### 3.4. expectAll và chẩn đoán khi test fail

~~~java
client.get().uri("/api/reads/1")
        .exchange()
        .expectAll(
            spec -> spec.expectStatus().isOk(),
            spec -> spec.expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
~~~

`expectAll(...)` hữu ích khi muốn kiểm nhiều assertion trong cùng response, thay vì dừng ngay ở lỗi đầu tiên. Có thể dùng `returnResult()` để inspect raw response hoặc `expectBody().consumeWith(...)` để thực hiện custom assertions, nhưng không log body chứa token, mật khẩu hay dữ liệu riêng tư.

## 4. Validation trong WebFlux: exception khác Spring MVC

Đây là chỗ quan trọng của module validation-data-binding.

### 4.1. @Valid @RequestBody object thông thường

~~~java
@PostMapping("/reads")
public Mono<Receipt> create(
        @Valid @RequestBody ReadRequest request) {
    return Mono.just(new Receipt("accepted", 1));
}
~~~

Khi JSON đọc được và các Jakarta constraints trên `ReadRequest` thất bại, **Spring WebFlux** thường tạo `org.springframework.web.bind.support.WebExchangeBindException`. Exception chứa `BindingResult` và được map mặc định sang HTTP **400 Bad Request**. <u>Đừng chép handler `MethodArgumentNotValidException` của Spring MVC rồi nghĩ đó là class tương đương trong WebFlux.</u>

### 4.2. @Valid @RequestBody Mono<ReadRequest>

~~~java
@PostMapping("/reads/async")
public Mono<Receipt> createAsync(
        @Valid @RequestBody Mono<ReadRequest> input) {
    return input.map(request ->
            new Receipt("accepted", request.lines().size()));
}
~~~

Với `Mono<ReadRequest>`, body decoding và validation là các bước xảy ra qua publisher được subscribe. Nếu dữ liệu sai, publisher có thể phát `onError(WebExchangeBindException)`. Bạn có thể để lỗi lan đến WebFlux exception handling, hoặc dùng operator để xây phản hồi có status cụ thể.

**Không** viết `BindingResult` ngay sau `Mono<ReadRequest>` như thể body đã giải quyết đồng bộ; Spring WebFlux docs lưu ý tham số `Errors` dùng với body object không bọc trong `Mono`. Test riêng cả đường đồng bộ và đường publisher để chắc chắn hệ thống xử lý đúng.

### 4.3. Method validation khác object validation

Spring Framework 6.1+ hỗ trợ controller method validation tích hợp cho direct constraints:

~~~java
@GetMapping("/limits")
public Mono<String> limits(
        @RequestParam @Min(1) int count) {
    return Mono.just("limit=" + count);
}
~~~

Constraint trực tiếp `@Min(1)` trên method parameter có thể gây `HandlerMethodValidationException` khi sai. Trường hợp này khác `WebExchangeBindException`, vì validation áp dụng cho method parameters thay vì chỉ một command object. `@Valid` tự nó không phải constraint; thêm direct `@NotNull` hoặc `@Min` vào method signature có thể thay đổi đường validation.

Nếu dùng class-level `@Validated` trên controller, một số phiên bản có thể chuyển sang AOP method validation thay vì cơ chế native mới; hãy đối chiếu Spring version và test exception type thực tế.

### 4.4. JSON hỏng xảy ra trước Bean Validation

Ví dụ:

~~~text
{"reader":
~~~

JSON chưa hợp lệ, hoặc giá trị ngày `"not-a-date"` không thể deserialize thành `LocalDate`, thường gây `ServerWebInputException` hoặc lỗi decoding được WebFlux wrap, **không** có `BindingResult` đầy đủ của bean validation. Vì `WebExchangeBindException extends ServerWebInputException`, custom advice có thể định nghĩa hai handler và Spring chọn handler cụ thể hơn cho binding.

Không test tất cả bad requests bằng cách assert chỉ `"VALIDATION_FAILED"`: malformed input và field constraint violations là hai giai đoạn khác nhau.

### 4.5. FieldError, ObjectError và nested paths

Với DTO có `@NotBlank reader`, `@ValidAddress` nested bean và `@ValidPeriod` class-level constraint, `BindingResult` phân biệt:

~~~text
FieldError: reader
FieldError: shippingAddress.city
FieldError: lines[0].sku
ObjectError: readRequest (class-level @ValidWindow)
~~~

`FieldError` là subclass `ObjectError`; `getAllErrors()` chứa cả field lẫn global. Để có JSON client dùng dễ dàng, lấy `getFieldErrors()` và `getGlobalErrors()` riêng, sắp xếp path/code nếu cần stable contract. Không serialize `rejectedValue` vì có thể chứa thông tin nhạy cảm.

## 5. Hai loại lỗi khác nhau trên một chuỗi phản ứng

### 5.1. Lỗi trước khi HTTP response được commit

~~~text
GET /api/reads/999
        |
        v
service.find(999) => Mono.error(NotFound)
        |
        v
@ControllerAdvice / WebExceptionHandler
        |
        v
HTTP 404 + application/problem+json
~~~

Nếu chưa có headers/body được gửi, WebFlux có thể chọn status 404 và một body `ProblemDetail`. Với `@Valid`, status 400 cũng thường được xác định trước khi handler phát response data.

### 5.2. Lỗi sau khi stream đã bắt đầu phát

~~~text
GET /api/reads/events?mode=fail-late
        |
        v
HTTP 200 + Content-Type: text/event-stream
        |
        v
data: first

        |
        v
upstream => onError(UpstreamUnavailableException)
        |
        v
Không thể đảm bảo đổi HTTP status thành 500/503
sau khi headers/body đã committed.
~~~

Server có thể đóng kết nối, báo transport error, ghi log hoặc kích hoạt cơ chế error handler đặc thù khi response chưa committed. Với HTTP streaming, sau khi đã gửi headers/data, **đừng mong `@ExceptionHandler` tạo một JSON 500 để thay thế đoạn stream đã gửi**. Hành vi cụ thể của Netty, proxy, buffering và client decoder có thể khác nhau; không nên viết test cứng “sau phần tử đầu chắc chắn nhận 500” hoặc “chắc chắn sẽ nhận một JSON ProblemDetail”.

Đây là khác biệt cốt lõi giữa **error response** và **error signal trong response stream**.

### 5.3. Chủ động thiết kế giao thức lỗi của stream

Nếu protocol cho phép, có thể phát một SSE event tường minh báo lỗi thay vì để publisher kết thúc đột ngột:

~~~text
event: reading
data: first

event: error
data: {"code":"SOURCE_UNAVAILABLE"}

~~~

Một event tên `error` trong SSE là **data frame do ứng dụng định nghĩa**, không phải HTTP status và không phải Reactive Streams `onError`. Nếu bạn dùng `onErrorResume` để trả event đó, publisher có thể kết thúc bằng `onComplete` sau khi phát event fallback. Client cần hiểu contract và có thể phải quyết định retry từ checkpoint/last event ID.

Đừng đưa raw exception message hay stack trace vào SSE error event. Với stream vô hạn, cân nhắc `timeout`, heartbeat, giới hạn số event, cancellation và backpressure.

## 6. StepVerifier kiểm tra Reactive Streams

`reactor.test.StepVerifier` kiểm tra đúng thứ tự signals:

~~~java
StepVerifier.create(Flux.just("A", "B"))
        .expectNext("A", "B")
        .verifyComplete();
~~~

`verifyComplete()` thực thi test và yêu cầu `onComplete`. Nếu chỉ xây pipeline assertion mà không gọi `verify()`/`verifyComplete()`, test có thể không subscribe và không kiểm tra gì.

### 6.1. Lỗi sau hai giá trị

~~~java
Flux<String> stream = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("boom")));

StepVerifier.create(stream)
        .expectNext("A", "B")
        .expectError(IllegalStateException.class)
        .verify(Duration.ofSeconds(2));
~~~

Test này kiểm tra đúng **publisher contract** của service. Nó không tự kiểm HTTP status hay việc một proxy đã flush chunk nào.

### 6.2. Phục hồi lỗi trong pipeline

~~~java
Flux<String> recovered = Flux.concat(
        Flux.just("A"),
        Flux.<String>error(new IllegalStateException("boom")))
        .onErrorResume(IllegalStateException.class,
                ex -> Flux.just("fallback"));

StepVerifier.create(recovered)
        .expectNext("A", "fallback")
        .verifyComplete();
~~~

`onErrorResume` bắt đúng loại lỗi và thay phần còn lại của chuỗi bằng publisher fallback. Không được dùng `onErrorContinue` tràn lan cho lỗi nghiệp vụ: nó có semantics đặc biệt tùy operator và có thể vô tình bỏ qua dữ liệu mà không báo cho client.

### 6.3. Flux vô hạn và thenCancel

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(50));

StepVerifier.create(ticks)
        .expectNextCount(3)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Không gọi `verifyComplete()` với `Flux.interval` vô hạn trừ khi đã đặt `take(n)` hoặc có termination rule rõ ràng. `thenCancel()` giúp test kết thúc và giải phóng subscription. Với server thật, cancellation còn tương ứng client đóng/kết thúc subscription nên cần kiểm resource cleanup nếu có socket/file/database cursor.

### 6.4. Virtual time cho những publisher phụ thuộc thời gian

~~~java
StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofDays(1)))
        .expectSubscription()
        .thenAwait(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
~~~

`withVirtualTime` nhận **Supplier** tạo publisher sau khi virtual scheduler được cài đặt. Nếu tạo `Mono.delay` trước rồi đưa publisher đã tạo vào lambda, test có thể vẫn dùng scheduler cũ. Virtual time phù hợp để test Reactor operator logic; nó **không tua nhanh đồng hồ của một server Netty thật hoặc network IO**.

### 6.5. Tránh test không giới hạn thời gian

`StepVerifier.verify()` mặc định có thể đợi vô hạn. Trong test suite CI nên dùng:

~~~java
.verify(Duration.ofSeconds(3));
~~~

hoặc cấu hình default timeout. Timeout được chọn đủ thực tế cho môi trường CI; đừng biến test thành flaky bằng cách đòi một event network phải đến chính xác trong vài mili giây.

## 7. Project chạy được: Java 17+ / Spring Boot 3.5.7 / WebFlux

Demo này dùng **spring-boot-starter-webflux**, không thêm `spring-boot-starter-web` để tránh Boot mặc định chọn MVC khi cả hai stack cùng trên classpath. Ứng dụng có:

- `POST /api/reads`: body DTO thông thường; `@Valid` kiểm tra một field, nested objects/list và class-level constraint; thành công trả 201, lỗi trả 400.
- `POST /api/reads/async`: body dạng `Mono<ReadRequest>`, cũng kiểm tra validation.
- `GET /api/reads/{id}`: `1` tồn tại, ID khác phát domain error trước khi response, advice trả 404 ProblemDetail.
- `GET /api/reads/limits?count=0`: direct `@Min` được native method validation kiểm tra và trả 400.
- `GET /api/reads/events?mode=normal`: SSE hữu hạn phát `first`/`second`.
- `GET /api/reads/events?mode=recover`: service phát `first`, upstream lỗi rồi `onErrorResume` phát `fallback`.
- `GET /api/reads/events?mode=fail-late`: service phát `first` rồi `onError`. Test tầng service chốt tín hiệu, không assert một HTTP 500 “sau commit”.
- `GET /api/reads/ticks`: SSE vô hạn dùng để thử `thenCancel()`.

### 7.1. Cấu trúc dự án

~~~text
webflux-validation-streams/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/reactive/
    │   │   ├── Application.java
    │   │   ├── ShippingAddress.java
    │   │   ├── ReadLine.java
    │   │   ├── ReadRequest.java
    │   │   ├── ValidWindow.java
    │   │   ├── ValidWindowValidator.java
    │   │   ├── Receipt.java
    │   │   ├── ReadingNotFoundException.java
    │   │   ├── UpstreamUnavailableException.java
    │   │   ├── ReadingService.java
    │   │   ├── ReadingController.java
    │   │   └── ApiErrorAdvice.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactive/
            ├── ReadingHttpTest.java
            ├── ReadingServiceTest.java
            └── ReadingSliceTest.java
~~~

### 7.2. pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>webflux-validation-streams</artifactId>
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

`reactor-test` được khai báo trực tiếp để các `StepVerifier` tests có dependency rõ ràng. Spring Boot parent quản lý versions; không ép một phiên bản Reactor tùy ý khác BOM. `spring-boot-starter-webflux` kéo WebFlux, Reactor Netty và codecs cần thiết, `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider.

### 7.3. Application.java

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 7.4. ShippingAddress.java

~~~java
package com.example.reactive;

import jakarta.validation.constraints.NotBlank;

public record ShippingAddress(
        @NotBlank String city) {
}
~~~

### 7.5. ReadLine.java

~~~java
package com.example.reactive;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ReadLine(
        @NotBlank String sku,
        @Min(1) int quantity) {
}
~~~

### 7.6. ReadRequest.java

~~~java
package com.example.reactive;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;
import java.util.List;

@ValidWindow
public record ReadRequest(
        @NotBlank String reader,
        @NotNull @Valid ShippingAddress shippingAddress,
        @NotEmpty List<@NotNull @Valid ReadLine> lines,
        @NotNull LocalDate fromDate,
        @NotNull LocalDate toDate) {
}
~~~

Quy tắc:

- `reader=""` → `FieldError` có path `reader`.
- `shippingAddress.city=""` → nested path `shippingAddress.city`.
- `lines[0].sku=""` → nested list path `lines[0].sku`.
- `fromDate`/`toDate` null → `@NotNull` tại field tương ứng.
- `toDate` trước `fromDate` → `@ValidWindow` class-level rule, thông thường là `ObjectError` global.

`@Valid` trên cạnh nested là quan trọng. `@NotNull` không tự làm cascade; ngược lại `@Valid` không biến null thành validation error nếu không có `@NotNull` phù hợp.

### 7.7. ValidWindow.java

~~~java
package com.example.reactive;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidWindowValidator.class)
public @interface ValidWindow {
    String message() default "toDate must be on or after fromDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

### 7.8. ValidWindowValidator.java

~~~java
package com.example.reactive;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class ValidWindowValidator
        implements ConstraintValidator<ValidWindow, ReadRequest> {

    @Override
    public boolean isValid(
            ReadRequest value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.fromDate() == null
                || value.toDate() == null) {
            return true;
        }

        return !value.toDate().isBefore(value.fromDate());
    }
}
~~~

Không gọi `addPropertyNode(...)`, nên default violation của class-level constraint nằm ở root object. Khi hai ngày null, class-level validator trả true để `@NotNull` của các fields báo lỗi mà không xảy ra `NullPointerException`.

### 7.9. Receipt.java

~~~java
package com.example.reactive;

public record Receipt(
        String result,
        int lineCount) {
}
~~~

### 7.10. ReadingNotFoundException.java

~~~java
package com.example.reactive;

public final class ReadingNotFoundException
        extends RuntimeException {
}
~~~

### 7.11. UpstreamUnavailableException.java

~~~java
package com.example.reactive;

public final class UpstreamUnavailableException
        extends RuntimeException {

    public UpstreamUnavailableException() {
        super("upstream unavailable");
    }
}
~~~

Đây là exception mô phỏng lỗi của nguồn dữ liệu upstream. Phần message chỉ sử dụng trong unit test tầng service, không xuất nguyên văn cho HTTP client.

### 7.12. ReadingService.java

~~~java
package com.example.reactive;

import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;

@Service
public class ReadingService {

    public Mono<Receipt> find(long id) {
        if (id == 1L) {
            return Mono.just(new Receipt("found", 1));
        }
        return Mono.error(new ReadingNotFoundException());
    }

    public Flux<String> raw(String mode) {
        return switch (mode) {
            case "normal" -> Flux.just("first", "second");

            case "recover" -> Flux.concat(
                    Flux.just("first"),
                    Flux.<String>error(
                            new UpstreamUnavailableException()))
                    .onErrorResume(
                            UpstreamUnavailableException.class,
                            error -> Flux.just("fallback"));

            case "fail-late" -> Flux.concat(
                    Flux.just("first"),
                    Flux.<String>error(
                            new UpstreamUnavailableException()));

            default -> Flux.error(
                    new IllegalArgumentException(
                            "Unsupported stream mode"));
        };
    }

    public Flux<ServerSentEvent<String>> events(String mode) {
        return raw(mode).map(value ->
                ServerSentEvent.<String>builder(value)
                        .event("reading")
                        .build());
    }

    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofMillis(40))
                .map(index ->
                        ServerSentEvent.<String>builder(
                                        "tick-" + index)
                                .event("tick")
                                .build());
    }
}
~~~

Đặc điểm quan trọng:

- `normal` phát hai giá trị rồi complete.
- `recover` phát `first` rồi có lỗi upstream, nhưng `onErrorResume` biến lỗi thành `fallback` và complete.
- `fail-late` phát `first` rồi **onError**. Đường này dùng trong StepVerifier test tầng service, không assert status 500 từ một stream HTTP đã có thể commit.
- `ticks` là stream vô hạn. Không dùng `collectList()` trong controller; test chỉ đọc ba events rồi cancel.

`Flux.interval` dùng scheduler của Reactor chứ không cần gọi `Thread.sleep`. Với hệ thống thật, nguồn stream có thể là R2DBC, event bus hoặc `WebClient`; cần xử lý resource cleanup khi subscriber cancel.

### 7.13. ReadingController.java

~~~java
package com.example.reactive;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reads")
public class ReadingController {

    private final ReadingService service;

    public ReadingController(ReadingService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Receipt>> create(
            @Valid @RequestBody ReadRequest request) {

        return Mono.just(
                ResponseEntity.status(HttpStatus.CREATED)
                        .body(new Receipt(
                                "accepted",
                                request.lines().size())));
    }

    @PostMapping(
            path = "/async",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Receipt> createAsync(
            @Valid @RequestBody Mono<ReadRequest> request) {

        return request.map(value ->
                new Receipt(
                        "accepted",
                        value.lines().size()));
    }

    @GetMapping("/{id}")
    public Mono<Receipt> find(@PathVariable long id) {
        return service.find(id);
    }

    @GetMapping("/limits")
    public Mono<String> limits(
            @RequestParam @Min(1) int count) {

        return Mono.just("limit=" + count);
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(
            @RequestParam(defaultValue = "normal")
            String mode) {

        return service.events(mode);
    }

    @GetMapping(
            path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return service.ticks();
    }
}
~~~

Chú ý:

- `create` nhận body object, validation lỗi sẽ được xử lý trước khi tạo receipt.
- `createAsync` nhận body Mono, validation lỗi có thể xuất hiện như một tín hiệu lỗi khi subscribe.
- `find` trả `Mono.error(ReadingNotFoundException)` cho ID khác 1; vẫn chưa có body data đã phát, nên advice có cơ hội trả HTTP 404.
- `limits` có direct `@Min(1)`; Spring 6.1+ có thể ném `HandlerMethodValidationException`. Không thêm class-level `@Validated` lên controller nếu muốn test native method validation ở 6.2.
- `events` phát SSE `text/event-stream` và `ticks` không tự hoàn thành. Không gọi `block()` hoặc `subscribe()` trong handler; WebFlux quản lý subscription theo HTTP lifecycle.

### 7.14. ApiErrorAdvice.java

~~~java
package com.example.reactive;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.server.ServerWebInputException;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record FieldIssue(String path, String code) {
    }

    public record ValidationReport(
            String code,
            List<FieldIssue> fieldErrors,
            List<String> globalErrors) {
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ValidationReport> invalid(
            WebExchangeBindException ex) {

        List<FieldIssue> fields = ex.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(
                                error.getCode(), "invalid")))
                .sorted(Comparator
                        .comparing(FieldIssue::path)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<String> globals = ex.getGlobalErrors()
                .stream()
                .map(error -> Objects.toString(
                        error.getCode(), "invalid"))
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationReport(
                        "VALIDATION_FAILED",
                        fields,
                        globals));
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> badInput(
            ServerWebInputException ex) {

        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request input cannot be decoded or bound.");

        p.setType(URI.create(
                "https://example.org/problems/invalid-input"));
        p.setTitle("Invalid request");
        p.setProperty("code", "INVALID_INPUT");

        return ResponseEntity.badRequest().body(p);
    }

    @ExceptionHandler(ReadingNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ReadingNotFoundException ex) {

        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested reading was not found.");

        p.setType(URI.create(
                "https://example.org/problems/reading-not-found"));
        p.setTitle("Reading not found");
        p.setProperty("code", "READING_NOT_FOUND");

        return ResponseEntity.status(
                HttpStatus.NOT_FOUND).body(p);
    }
}
~~~

Giải thích từng handler:

1. `WebExchangeBindException` có thông tin field/global errors trong `BindingResult`. Sắp xếp path/code để JSON contract ổn định, không dựa vào thứ tự violations từ Bean Validation provider.
2. `ServerWebInputException` bao gồm lỗi đầu vào WebFlux. Vì `WebExchangeBindException` là subclass, Spring chọn handler cụ thể hơn cho validation. Handler đầu vào này cố ý trả message an toàn, không lộ raw decoder/exception trace.
3. `ReadingNotFoundException` được map thành `ProblemDetail` HTTP 404 khi lỗi xảy ra trước khi response bắt đầu.
4. **Không** có handler `UpstreamUnavailableException` cho SSE đang chạy. Với lỗi sau phần tử đầu, một `@ExceptionHandler` cũng không thể bảo đảm sửa status/headers đã gửi; chính service quyết định `recover` hay `fail-late`.

Mã `FieldError` được lấy từ Spring `BindingResult`, không trả rejected values. `ProblemDetail` được Jackson viết thành media type `application/problem+json` theo framework hỗ trợ. URI `example.org` chỉ là namespace ví dụ, sản phẩm thật nên dùng domain tài liệu API của mình.

### 7.15. application.properties

~~~properties
server.port=8080
spring.webflux.problemdetails.enabled=false
server.error.include-message=never
~~~

Ta có custom advice, nên không cần Boot tạo thêm `ResponseEntityExceptionHandler` tự động cạnh tranh. **Tắt Boot auto Problem Details không vô hiệu hóa class `ProblemDetail`** hoặc khả năng dùng nó trong advice. Nếu chọn cách dùng Boot auto-advice `spring.webflux.problemdetails.enabled=true`, xem xét order của custom advice và test exception mapping theo version cụ thể.

## 8. Test HTTP qua WebTestClient kết nối Netty thật

Tạo `src/test/java/com/example/reactive/ReadingHttpTest.java`. Sử dụng `@SpringBootTest(webEnvironment = RANDOM_PORT)` để WebTestClient đi qua HTTP server thật; điều này có ý nghĩa với SSE/cancellation. Thay `@AutoConfigureWebTestClient`/mock binding nếu chỉ muốn kiểm tra web handler không mở socket.

### 8.1. Full test class

~~~java
package com.example.reactive;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReadingHttpTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ObjectMapper mapper;

    private ObjectNode valid() {
        ObjectNode root = mapper.createObjectNode();
        root.put("reader", "Lan");

        root.putObject("shippingAddress")
                .put("city", "Ho Chi Minh City");

        ArrayNode lines = root.putArray("lines");
        lines.addObject()
                .put("sku", "BOOK-1")
                .put("quantity", 2);

        root.put("fromDate", "2026-11-01");
        root.put("toDate", "2026-11-03");

        return root;
    }

    private WebTestClient.ResponseSpec post(
            String path, ObjectNode body) {

        return client.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange();
    }

    @Test
    void validBodyReturnsCreated() {
        post("/api/reads", valid())
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.result").isEqualTo("accepted")
                .jsonPath("$.lineCount").isEqualTo(1);
    }

    @Test
    void blankReaderIsFieldError() {
        ObjectNode body = valid();
        body.put("reader", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("reader")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotBlank")
                .jsonPath("$.globalErrors.length()")
                    .isEqualTo(0);
    }

    @Test
    void classLevelRuleIsGlobalError() {
        ObjectNode body = valid();
        body.put("toDate", "2026-10-31");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors.length()")
                    .isEqualTo(0)
                .jsonPath("$.globalErrors[0]")
                    .isEqualTo("ValidWindow");
    }

    @Test
    void nestedAddressFieldRetainsFullPath() {
        ObjectNode body = valid();
        ((ObjectNode) body.get("shippingAddress"))
                .put("city", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("shippingAddress.city")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotBlank");
    }

    @Test
    void listElementErrorIncludesIndex() {
        ObjectNode body = valid();
        ArrayNode lines = (ArrayNode) body.get("lines");
        ((ObjectNode) lines.get(0))
                .put("sku", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("lines[0].sku")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotBlank");
    }

    @Test
    void missingNestedObjectIsDifferentFromBlankCity() {
        ObjectNode body = valid();
        body.putNull("shippingAddress");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("shippingAddress")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotNull");
    }

    @Test
    void mixedErrorsKeepFieldAndGlobalGroups() {
        ObjectNode body = valid();
        body.put("reader", "");
        body.put("toDate", "2026-10-31");

        ((ObjectNode) body.get("shippingAddress"))
                .put("city", "");

        ((ObjectNode) body.withArray("lines").get(0))
                .put("sku", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors.length()")
                    .isEqualTo(3)
                .jsonPath("$.globalErrors.length()")
                    .isEqualTo(1)
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("lines[0].sku")
                .jsonPath("$.fieldErrors[1].path")
                    .isEqualTo("reader")
                .jsonPath("$.fieldErrors[2].path")
                    .isEqualTo("shippingAddress.city")
                .jsonPath("$.globalErrors[0]")
                    .isEqualTo("ValidWindow");
    }

    @Test
    void reactiveMonoBodyValidationAlsoFails() {
        ObjectNode body = valid();
        body.put("reader", "");

        post("/api/reads/async", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo(
                        "VALIDATION_FAILED")
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("reader");
    }

    @Test
    void malformedJsonIsNotBeanConstraintError() {
        client.post()
                .uri("/api/reads")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_INPUT");
    }

    @Test
    void directMethodConstraintIsBadRequest() {
        client.get()
                .uri("/api/reads/limits?count=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void notFoundBeforeBodyBecomesProblemDetail() {
        client.get()
                .uri("/api/reads/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code")
                    .isEqualTo("READING_NOT_FOUND");
    }

    private FluxExchangeResult<ServerSentEvent<String>>
    stream(String mode) {

        return client.get()
                .uri("/api/reads/events?mode={mode}", mode)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                            ServerSentEvent<String>>() {});
    }

    @Test
    void finiteSseStreamCompletes() {
        var response = stream("normal");

        StepVerifier.create(response.getResponseBody())
                .assertNext(event ->
                        assertEquals("first", event.data()))
                .assertNext(event ->
                        assertEquals("second", event.data()))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void recoveredSseStreamContainsFallback() {
        var response = stream("recover");

        StepVerifier.create(response.getResponseBody())
                .assertNext(event -> {
                    assertEquals("reading", event.event());
                    assertEquals("first", event.data());
                })
                .assertNext(event ->
                        assertEquals("fallback", event.data()))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void infiniteSseStreamCanBeCancelled() {
        var response = client.get()
                .uri("/api/reads/ticks")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                            ServerSentEvent<String>>() {});

        StepVerifier.create(response.getResponseBody())
                .expectNextCount(3)
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

Giải thích:

- `@SpringBootTest(RANDOM_PORT)` tạo server thật và client được Spring Boot cấu hình để gửi request đến port đó.
- `ObjectNode` làm dữ liệu test thay vì `String.replace` chuỗi JSON; điều này không phụ thuộc whitespace.
- `WebTestClient.ResponseSpec` cho phép các hàm `post(...)` trả một response chưa assert cụ thể.
- `jsonPath("$.fieldErrors.length()")` kiểm số lỗi; `FieldError.getCode()` ổn định hơn default message có thể thay đổi theo locale.
- `mixedErrors...` assert thứ tự sau khi **advice chủ động sort theo path**; không dựa vào thứ tự ngẫu nhiên của Bean Validation provider.
- `@Valid @RequestBody Mono<ReadRequest>` phải được test riêng vì lỗi có thể xuất hiện tại reactive signal resolution.
- `stream(...)` dùng `returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {})` để lấy `FluxExchangeResult`. Không dùng `expectBodyList` cho SSE đang chạy.
- `verify(Duration.ofSeconds(5))` đặt giới hạn thời gian và `thenCancel()` dừng infinite subscription.

**Giới hạn:** Các test streaming phụ thuộc môi trường HTTP/Netty của test. Với mạng bị proxy, thời gian gửi/chặn buffering và cancellation có thể khác nhau; đừng biến những kiểm tra transport implementation-specific thành bảo đảm về HTTP status sau commit.

## 9. Unit test raw publishers: lỗi sau onNext không phải HTTP 500

File `src/test/java/com/example/reactive/ReadingServiceTest.java`:

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import java.time.Duration;

class ReadingServiceTest {

    private final ReadingService service =
            new ReadingService();

    @Test
    void normalPublisherCompletes() {
        StepVerifier.create(service.raw("normal"))
                .expectNext("first", "second")
                .expectComplete()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void sourceFailureIsRecovered() {
        StepVerifier.create(service.raw("recover"))
                .expectNext("first", "fallback")
                .expectComplete()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void lateFailureStillEmitsOnError() {
        StepVerifier.create(service.raw("fail-late"))
                .expectNext("first")
                .expectError(
                        UpstreamUnavailableException.class)
                .verify(Duration.ofSeconds(2));
    }
}
~~~

Đây là test unit nhanh, không cần Spring context. Nó xác minh chính xác `onNext→onError` và `onErrorResume→onComplete`. **Không** biến `lateFailureStillEmitsOnError` thành assertion rằng WebTestClient phải nhận HTTP 500 sau SSE đầu tiên. Tầng service có một Reactive Streams signal; tầng HTTP có một response có thể đã commit. Hai contract khác nhau.

## 10. @WebFluxTest: test slice không mở server

Một cách nhanh để kiểm mapping/advice mà không mở HTTP socket là `@WebFluxTest`. Đặt file `src/test/java/com/example/reactive/ReadingSliceTest.java`:

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(ReadingController.class)
class ReadingSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReadingService service;

    @Test
    void controllerAndAdviceHandleDomainNotFound() {
        when(service.find(999L))
                .thenReturn(Mono.error(
                        new ReadingNotFoundException()));

        client.get()
                .uri("/api/reads/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("READING_NOT_FOUND");
    }
}
~~~

Trong Spring Boot 3.5, `@WebFluxTest` quét các web components phù hợp như controller/advice nhưng **không** tự load mọi `@Service`; `@MockitoBean` của Spring Framework 6.2 cung cấp mock `ReadingService`. Đây là điểm khác với `@SpringBootTest` toàn ứng dụng.

Nếu advice/filter/formatter/validator được tùy biến phức tạp mà slice không quét, hãy đăng ký chúng bằng `@Import`/cấu hình test phù hợp, hoặc dùng full context tests. Đừng xem một slice test pass là bằng chứng mọi security filter, database transaction và external integration đã chạy.

### 10.1. So sánh mock server và real server

Một `@WebFluxTest` có WebTestClient “HTTP-like”, nhưng không chứng minh thực tế TCP connection đã đóng, HTTP/2 flow control hay Netty chunk flush. Nếu bài toán liên quan **lỗi sau commit**, **SSE disconnect** hoặc tài nguyên được giải phóng khi client cancel, hãy thêm integration test với `RANDOM_PORT` như mục 8 hoặc test observability tương ứng.

Mỗi lựa chọn có giá trị:

- Slice/controller unit: nhanh, cô lập web mapping.
- Full WebFlux context mock: kiểm kết nối beans/advice nhưng không network.
- Full HTTP real server: kiểm codec, headers và stream/cancellation có thật.
- StepVerifier service: kiểm từng signal của publisher.

## 11. Chạy các tests và thử HTTP

Dùng JDK 17+ và Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Các lớp tests:

~~~bash
mvn -Dtest=ReadingHttpTest test
mvn -Dtest=ReadingServiceTest test
mvn -Dtest=ReadingSliceTest test
~~~

Ví dụ gửi body hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/reads \
  -H "Content-Type: application/json" \
  -d '{
    "reader":"Lan",
    "shippingAddress":{"city":"Ho Chi Minh City"},
    "lines":[{"sku":"BOOK-1","quantity":2}],
    "fromDate":"2026-11-01",
    "toDate":"2026-11-03"
  }'
~~~

Kết quả dự kiến HTTP **201 Created**:

~~~json
{
  "result": "accepted",
  "lineCount": 1
}
~~~

Body sai:

~~~bash
curl -i -X POST http://localhost:8080/api/reads \
  -H "Content-Type: application/json" \
  -d '{
    "reader":"",
    "shippingAddress":{"city":""},
    "lines":[{"sku":"","quantity":2}],
    "fromDate":"2026-11-03",
    "toDate":"2026-11-01"
  }'
~~~

Response HTTP **400 Bad Request**, body về cấu trúc do custom advice định nghĩa:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {"path": "lines[0].sku", "code": "NotBlank"},
    {"path": "reader", "code": "NotBlank"},
    {"path": "shippingAddress.city", "code": "NotBlank"}
  ],
  "globalErrors": ["ValidWindow"]
}
~~~

Các errors được sort theo path/code. Khi dùng câu thông báo đa ngữ thật, bổ sung `MessageSource` ở response layer nhưng giữ `fieldErrors[].code` ổn định để client xử lý.

Thử SSE hữu hạn, có `-N` để tắt curl buffering phía client:

~~~bash
curl -N -H "Accept: text/event-stream" \
  "http://localhost:8080/api/reads/events?mode=normal"
~~~

Ví dụ ý nghĩa dữ liệu:

~~~text
event: reading
data: first

event: reading
data: second

~~~

Thử phục hồi:

~~~bash
curl -N -H "Accept: text/event-stream" \
  "http://localhost:8080/api/reads/events?mode=recover"
~~~

~~~text
event: reading
data: first

event: reading
data: fallback

~~~

Lệnh `curl -N ...mode=fail-late` có thể nhận event `first` rồi kết nối bị kết thúc/báo lỗi tùy network stack. **Không dự đoán rằng HTTP status tự chuyển thành 500 sau khi event đã xuất hiện**. Để kiểm `onError` một cách quyết định, dùng test `ReadingServiceTest.lateFailureStillEmitsOnError`.

## 12. Bẫy kiểm thử streaming và cách tránh

### 12.1. expectBodyList trên Flux vô hạn

Sai:

~~~java
client.get().uri("/api/reads/ticks")
        .exchange()
        .expectBodyList(String.class);
~~~

`expectBodyList` cố gắng thu thập response trước khi assert; stream không có termination bình thường. Thay bằng `returnResult(...)` và `StepVerifier.thenCancel()`.

### 12.2. Đòi status 500 sau khi đã có onNext

Sai về kỳ vọng:

~~~text
Server đã gửi HTTP 200 / event thứ nhất
Sau đó Flux phát onError
Test đòi nhận một HTTP response mới status 500
~~~

HTTP không có cơ chế “thay lại status line” của cùng một response đã commit. Hãy kiểm publisher error ở service và thiết kế stream fallback/error-event contract. Dùng network test để quan sát disconnect/terminal behavior theo stack mà không hardcode status không bảo đảm.

### 12.3. Gọi subscribe() hoặc block() trong controller

Anti-pattern:

~~~java
@GetMapping("/bad")
public String bad() {
    return service.raw("normal").blockFirst();
}
~~~

`block()`/`blockFirst()` trong WebFlux event-loop có thể gây lỗi hoặc giảm throughput, thậm chí bị Spring/Reactor chặn trên nonblocking threads. Trả trực tiếp `Mono`/`Flux` để framework quản lý subscription. Test service bằng StepVerifier thay vì tự subscribe rồi dùng sleeps.

### 12.4. Dùng Thread.sleep để đợi event

Sai:

~~~java
Thread.sleep(1000);
assertEquals(3, events.size());
~~~

Time-based tests dễ flaky vì scheduling/CI khác nhau. Với Publisher thuần, dùng virtual time; với WebTestClient streaming, dùng `StepVerifier.expectNextCount(n)` cùng timeout và cancel.

### 12.5. Chỉ kiểm status cho validation

Nếu test chỉ assert HTTP 400, bạn không biết lỗi là JSON malformed, thiếu field, class-level constraint hay nested path. Assert response error code, path và global errors, nhưng không lệ thuộc default English validation messages có thể đổi theo locale.

### 12.6. @Valid thiếu cascade

Root `@Valid ReadRequest` không tự validate tất cả nested beans nếu property không được gắn `@Valid`. Cần `@NotNull @Valid ShippingAddress` và `List<@Valid ReadLine>` nếu muốn có `shippingAddress.city`, `lines[0].sku`. Test nested path là cách phát hiện thiếu cascade.

### 12.7. Mạo nhận WebFlux trong project MVC

Nếu cùng thêm `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường ưu tiên MVC application type. Dù WebTestClient có thể dùng với MVC mock server, exception classes và reactive execution model của MVC khác WebFlux. Demo chỉ dùng starter WebFlux; kiểm log/`spring.main.web-application-type=reactive` khi cấu hình phức tạp.

### 12.8. Bỏ qua lỗi decoder và memory limits

WebFlux HTTP codecs có in-memory buffer limits (ví dụ `spring.codec.max-in-memory-size` trong Boot). Body JSON rất lớn hoặc stream chunk quá lớn có thể dẫn đến codec/buffering error trước Bean Validation. Test rejection/limit policy riêng, không cố convert mọi codec exception thành “@NotBlank failed”.

### 12.9. Sai đường xử lý ResponseEntityExceptionHandler

Spring WebFlux `ResponseEntityExceptionHandler` thuộc:

~~~java
org.springframework.web.reactive.result.method.annotation
        .ResponseEntityExceptionHandler
~~~

đừng import bản MVC:

~~~java
org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler
~~~

Hai dòng trên chỉ là định danh class trình bày có xuống dòng để đọc; trong Java thực tế phải dùng import một dòng chính xác. Spring Boot `spring.webflux.problemdetails.enabled` cũng khác `spring.mvc.problemdetails.enabled`. Với custom advice, hãy test thứ tự handler khi bật Boot auto Problem Details.

## 13. Lỗi trước subscribe, sau subscribe và terminal signals

### 13.1. Assembly vs subscription

Publisher có thể được **assembly** mà chưa thực thi logic I/O. Ví dụ:

~~~java
Mono<String> source = Mono.defer(() -> {
    return Mono.error(
            new IllegalStateException("failure at subscribe"));
});
~~~

`Mono.defer` trì hoãn việc tạo publisher con đến khi có subscriber. Khi test gọi `StepVerifier.create(source)` và `verify()`, publisher mới phát lỗi. Phân biệt lỗi **ném đồng bộ khi gọi method** (trước khi trả Publisher) với **lỗi tín hiệu onError** xảy ra sau khi subscribe. Hai đường có thể đi qua handler/logging khác nhau.

### 13.2. onErrorResume, onErrorMap và doOnError

- `onErrorResume`: chuyển lỗi sang một Publisher fallback.
- `onErrorMap`: biến lỗi thành loại exception khác để downstream xử lý.
- `doOnError`: side effect để ghi metrics/log; **không nuốt lỗi**.
- `retryWhen`: subscribe lại upstream theo policy; nếu tác vụ không idempotent có thể tạo duplicate writes.

Ví dụ:

~~~java
Flux<String> source = Flux.concat(
        Flux.just("first"),
        Flux.<String>error(
                new IllegalStateException("temporary")));

Flux<String> mapped = source.onErrorMap(
        IllegalStateException.class,
        ex -> new UpstreamUnavailableException());
~~~

Sau `first`, subscriber nhận `onError(UpstreamUnavailableException)`. Mapping lỗi không tự thay HTTP status sau commit.

### 13.3. Error event là dữ liệu, không phải onError

Nếu giao thức SSE chủ động gửi:

~~~text
event: error
data: {"code":"UNAVAILABLE"}

~~~

thì `Flux<ServerSentEvent<?>>` có thể vẫn kết thúc bằng `onComplete`. Client phải hiểu trường `event` là `"error"`. Đây là **application protocol** khác với transport failure hoặc Reactive Streams error signal.

## 14. Validation groups và reactive argument semantics

`@Validated(Group.class)` cho phép chọn constraint groups. Nếu endpoint tạo draft khác endpoint submit chính thức, có thể cần:

~~~java
public interface FinalSubmit {
}
~~~

~~~java
@NotBlank(groups = FinalSubmit.class)
private String approvalReason;
~~~

Trong Spring WebFlux, `@Validated(FinalSubmit.class) @RequestBody ReadRequest` chọn group khi phù hợp với argument-level validation; tuy nhiên với `Mono<ReadRequest>` và method-level constraints, hãy kiểm chính xác behavior theo Spring version. Một bài test không thấy rule vì sai group là failure của fixture/config, không có nghĩa validator không chạy.

Trong test nên tách:

- Rule test bằng `jakarta.validation.Validator.validate(dto, Group.class)`.
- WebFlux integration test bằng WebTestClient theo endpoint, request content type và group.
- Validation error response test theo path/code đã hợp đồng hóa.

Dự án có nhiều policies nên tránh dùng cùng một DTO với hàng chục groups làm quyền ghi/authorization bị trộn; validation groups không thay security checks.

## 15. Thiết kế các trường hợp lỗi để test có giá trị

| Tình huống | Test tốt cần kiểm |
| --- | --- |
| JSON hợp lệ | 201/200 và output được decode đúng |
| Reader trống | 400, `fieldErrors[].path=reader`, `code=NotBlank` |
| Nested city trống | 400, `shippingAddress.city` (có `@Valid` cascade) |
| Item list có SKU trống | 400, `lines[0].sku` |
| Class-level window sai | 400, `globalErrors` có `ValidWindow` |
| Nhiều lỗi đồng thời | Nhiều field + global đúng nhóm, không mất lỗi |
| JSON hỏng/invalid LocalDate | 400 `INVALID_INPUT`, không giả thành Bean Validation |
| Mono body invalid | 400 sau publisher validation, advice xử lý |
| Direct @Min trên query | 400 với method validation (6.1+) |
| Domain missing | 404 ProblemDetail trước khi response stream gửi |
| Stream finite | SSE first/second rồi complete |
| Stream recover | SSE first/fallback rồi complete |
| Stream fail late | StepVerifier upstream first rồi onError, **không** assert HTTP 500 |
| Infinite stream | Nhận N events rồi cancel, test kết thúc |
| Security thiếu quyền | 401/403 đúng security config, không bypass business checks |
| Resource cleanup khi cancel | Publisher doFinally(CANCEL) / integration teardown được test riêng |

### 15.1. Kiểm thử side effects khi request invalid

Giả sử endpoint ghi vào database hoặc message broker. Một test 400 nên xác nhận **không có record được lưu, không có event được publish**, nếu validation được thiết kế trước side effect. Với reactive chain, lưu ý operator `doOnNext`, `flatMap(save)` và `retry` có thể gây side effect. Dùng mocks hoặc testcontainers integration để khẳng định service save không được gọi khi input invalid.

### 15.2. Cancellation và cleanup

Với publisher nắm giữ resource, có thể quan sát `doFinally(signalType)`:

~~~java
AtomicReference<SignalType> termination =
        new AtomicReference<>();

Flux<Long> stream = Flux.interval(
                Duration.ofMillis(20))
        .doFinally(termination::set);
~~~

Sau khi `StepVerifier...thenCancel()` hoàn tất, `termination` có thể nhận `SignalType.CANCEL`. Đây là snippet test đơn vị, không chứng minh một TCP socket đã đóng ở server thật. Với R2DBC, file, WebClient hay message subscription, kiểm tra cleanup phù hợp ở integration tests và áp dụng `usingWhen` khi cần quản lý reactive resource lifecycle.

### 15.3. Backpressure

StepVerifier mặc định có thể request nhiều phần tử; nếu muốn kiểm demand cụ thể, dùng `StepVerifierOptions.create().initialRequest(0)` rồi `thenRequest(n)`. Điều này kiểm publisher respect backpressure ở tầng Reactor; không thay cho kiểm thử network/codec buffering. Đừng tạo Flux vô hạn với vòng lặp CPU mà không có backpressure/cancellation.

### 15.4. Context và correlation ID

Reactor `Context` khác `ThreadLocal` truyền thống. Khi request qua asynchronous boundaries, đừng giả định request-id/security context được giữ đúng chỉ bằng static/ThreadLocal. Test propagation bằng Reactor Context/WebFilter nếu nghiệp vụ cần correlation/authorization, và không log tokens hoặc dữ liệu riêng tư.

## 16. Bộ câu hỏi ôn tập

**1.** WebTestClient và StepVerifier có vai trò gì khác nhau?  
WebTestClient quan sát response HTTP (status, headers, content, stream), còn StepVerifier quan sát chuỗi tín hiệu của Publisher. Thường dùng cùng nhau khi kiểm SSE.

**2.** Vì sao `expectBodyList()` không phù hợp với stream vô hạn?  
Nó thu thập toàn body và chờ kết thúc; stream vô hạn không kết thúc theo thiết kế. Dùng `returnResult()` + StepVerifier + `thenCancel()`.

**3.** Khi `@Valid @RequestBody ReadRequest` lỗi trong Spring WebFlux, exception nào thường được ném?  
`WebExchangeBindException`. Bản MVC dùng `MethodArgumentNotValidException` ở trường hợp tương tự.

**4.** Khi `@RequestParam @Min(1) int count` sai ở Spring 6.1+, lỗi đi theo đường nào?  
Native controller method validation, thường `HandlerMethodValidationException` thay vì object argument `WebExchangeBindException`.

**5.** Vì sao JSON sai cú pháp có thể không có `BindingResult`?  
HTTP message reader/Jackson thất bại khi decode trước khi Bean Validation chạy, thường theo `ServerWebInputException`.

**6.** Một FieldError nested có path như thế nào?  
Ví dụ `shippingAddress.city` hoặc `lines[0].sku`, không chỉ `city`/`sku`.

**7.** Nếu stream đã gửi event đầu, có đảm bảo sửa HTTP 200 thành 500 không?  
Không. Sau khi headers/body được commit, response status không thể thay thế. Phải xử lý lỗi theo stream protocol, fallback hoặc disconnect policy.

**8.** `onErrorResume` khác `doOnError` ở đâu?  
`onErrorResume` thay chuỗi lỗi bằng fallback Publisher, trong khi `doOnError` chỉ thực hiện side effect và lỗi vẫn được truyền tiếp.

**9.** Vì sao `StepVerifier.withVirtualTime` dùng Supplier?  
Để Publisher được tạo sau khi scheduler ảo được cài đặt; nếu tạo trước, việc tua thời gian có thể không có tác dụng.

**10.** `thenCancel()` kiểm gì?  
Kiểm subscription có thể dừng sau N events và test không đợi `onComplete`. Trong integration cần thêm test resource cleanup nếu liên quan tài nguyên thật.

**11.** Vì sao `@WebFluxTest` cần `@MockitoBean`?  
Slice không tự nạp mọi service/repository; controller dependencies phải được cung cấp qua mock/import/beans phù hợp.

**12.** Kiểm thử SSE bằng mock server có giống Netty server thật không?  
Không hoàn toàn. Mock tests kiểm response logic; real HTTP tests cần thiết cho chunk flush, disconnection, proxy buffering và cancellation transport.

## 17. Checklist trước khi merge WebFlux tests

1. Tài liệu/implementation đang dùng đúng Spring Framework 6.2 và Boot 3.5 (hoặc version dự án), không trộn API của Web MVC.
2. Project thực sự chạy WebFlux, không bị `spring-boot-starter-web` đẩy sang MVC.
3. Có `spring-boot-starter-validation` để chạy Jakarta Bean Validation.
4. Với nested objects/collections, có `@Valid` ở cạnh cần cascade.
5. Có test field error, global error, nested path và mixed errors.
6. Lỗi JSON parse được phân biệt với lỗi constraint.
7. `WebExchangeBindException` và `HandlerMethodValidationException` được xử lý hoặc ít nhất test status/contract phù hợp.
8. Test HTTP 400/404 kiểm cả status và mã lỗi có cấu trúc.
9. Streaming dùng `returnResult(...)` + StepVerifier, không thu thập vô hạn.
10. Test hữu hạn có `verifyComplete()` hoặc `expectComplete().verify(timeout)`.
11. Test không kết thúc dùng `thenCancel()` và giới hạn thời gian.
12. Kiểm lỗi sau `onNext` ở service Publisher mà không ép status HTTP không thể bảo đảm.
13. Không gọi `block()`, `subscribe()` thủ công hoặc `Thread.sleep` trong handler/test khi không cần.
14. Có test recovery branch và phân biệt fallback SSE event với `onError` terminal.
15. Errors không chứa raw rejected values, token, stack trace hoặc SQL.
16. Có test timeout/cancellation/resource cleanup nếu kết nối giữ lâu.
17. Với nhiều test suites, chọn mock/slice/full-server đúng mục tiêu, không dùng full HTTP server cho mọi unit test.
18. CI có đủ thời gian và không phụ thuộc tuyệt đối vào network scheduling vài milliseconds.

## Kết luận

Sơ đồ tổng kết:

~~~text
HTTP WebFlux
   |
   +-- @Valid @RequestBody object/Mono
   |         |
   |         +-- WebExchangeBindException -> 400
   |         +-- JSON decode failure      -> ServerWebInputException -> 400
   |
   +-- Method @Min / @NotBlank (6.1+)
   |         |
   |         '-- HandlerMethodValidationException -> thường 400
   |
   +-- Mono.error(domain exception), trước response commit
   |         |
   |         '-- @ControllerAdvice -> HTTP 4xx/5xx + error body
   |
   '-- Flux<ServerSentEvent<?>> đang streaming
             |
             +-- onNext -> HTTP chunk/SSE event
             +-- onErrorResume -> fallback event / complete
             +-- onError sau commit -> không sửa được HTTP status
             '-- cancel -> kết thúc subscription, cleanup
~~~

**WebTestClient trả lời “client HTTP nhận được gì?”, còn StepVerifier trả lời “Publisher phát những tín hiệu gì và kết thúc thế nào?”.** Hãy kết hợp hai công cụ, kiểm tra validation theo đúng exception WebFlux, dùng stream assertions có timeout và hủy subscription, đồng thời phân biệt một HTTP error response trước commit với reactive error signal sau khi streaming đã bắt đầu.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 — Testing WebFlux Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework 6.2 — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux Error Responses/RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — WebExchangeBindException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Framework 6.2 — WebTestClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.ResponseSpec.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Error Handling Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Backpressure and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
