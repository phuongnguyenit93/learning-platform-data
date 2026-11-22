# HandlerResultHandler và ghi kết quả vào phản hồi

Trong Spring WebFlux, việc tìm controller và gọi method chỉ là **một nửa đường đi của HTTP request**. Sau khi handler chạy, framework phải hiểu kiểu giá trị trả về — một DTO, `Mono<DTO>`, `Flux<DTO>`, `ResponseEntity<?>`, view name, hoặc `ServerResponse` của functional endpoint — rồi chuyển kết quả thành **HTTP status, headers và response body**.

Thành phần trung tâm của bước này là giao diện **`org.springframework.web.reactive.HandlerResultHandler`**. Nó xử lý đối tượng `HandlerResult` do `HandlerAdapter` tạo ra và hoàn tất phản hồi thông qua `ServerWebExchange`. Bài học giải thích cơ chế chọn result handler, các implementation mặc định, reactive publisher, nội dung JSON/SSE/NDJSON, thời điểm response được commit, lỗi khi đang ghi và cách kiểm thử.

Phạm vi: **Spring Boot 3.3.x + Spring Framework 6.1.x + Spring WebFlux**, Java 21. Đây là **reactive WebFlux stack**, không phải Spring MVC Servlet stack. Ví dụ dùng `spring-boot-starter-webflux` mà không thêm `spring-boot-starter-web`, vì khi cả hai starter cùng hiện diện Spring Boot thường ưu tiên Servlet/MVC nếu không cấu hình lựa chọn stack khác.

## 1. Vị trí của HandlerResultHandler trong luồng WebFlux

Sơ đồ khái quát một request WebFlux với annotated controller hoặc functional route:

~~~text
HTTP client
   |
   v
Reactive HTTP server (Reactor Netty mặc định với starter-webflux)
   |
   v
HttpHandler / WebHttpHandlerBuilder
   |
   v
WebFilter chain -> WebHandler
   |
   v
DispatcherHandler
   |
   +-- HandlerMapping: tìm handler phù hợp
   |      +-- RequestMappingHandlerMapping (@Controller)
   |      +-- RouterFunctionMapping (functional endpoints)
   |
   +-- HandlerAdapter: gọi handler theo kiểu phù hợp
   |      +-- RequestMappingHandlerAdapter
   |      +-- HandlerFunctionAdapter
   |
   +-- HandlerResult: chứa return value + type + binding context...
   |
   +-- HandlerResultHandler: xử lý kiểu kết quả đã trả
          +-- ResponseEntityResultHandler
          +-- ServerResponseResultHandler
          +-- ResponseBodyResultHandler
          +-- ViewResolutionResultHandler
                      |
                      v
          ServerWebExchange.getResponse()
                      |
             status / headers / codecs / views
                      |
               Mono<Void> completion
                      |
                      v
              HTTP response đến client
~~~

Điều cần phân biệt:

- **`HandlerMapping`** quyết định request được ánh xạ đến handler nào.
- **`HandlerAdapter`** biết cách thực thi handler đó: resolve tham số controller, gọi method hoặc function rồi đóng gói kết quả.
- **`HandlerResult`** mô tả kết quả invocation và metadata cần thiết.
- **`HandlerResultHandler`** biết cách biến một loại kết quả thành response thực tế.
- **`ServerHttpResponse`** là HTTP response abstraction; việc ghi byte ra mạng cuối cùng do runtime/codec phụ trách.

`DispatcherHandler` phối hợp những thành phần này. Nó không tự serialize từng DTO thành JSON bằng cách hard-code Jackson; công việc ghi body được chuyển cho các result handler và HTTP message writers thích hợp.

## 2. Giao diện HandlerResultHandler có hai phương thức

Về mặt khái niệm, contract:

~~~java
package org.springframework.web.reactive;

import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public interface HandlerResultHandler {
    boolean supports(HandlerResult result);
    Mono<Void> handleResult(ServerWebExchange exchange, HandlerResult result);
}
~~~

Đây là **hình dạng API để minh họa**, không phải mã cần sao chép vào project vì interface đã có trong thư viện Spring WebFlux.

**`supports(HandlerResult)`** trả `true` khi implementation hiểu loại kết quả. Ví dụ, một handler dành cho `ResponseEntity` kiểm tra kiểu return phù hợp; một handler cho `@ResponseBody` quan tâm cả annotation của handler method.

**`handleResult(ServerWebExchange, HandlerResult)`** có thể thiết lập status/headers, chọn codec/view và ghi response body. Kết quả của phương thức là **`Mono<Void>`**: tín hiệu hoàn tất bất đồng bộ hoặc lỗi, **không phải** body gửi đến client. Giá trị return của controller và giá trị return của result handler là hai tầng khác nhau.

Ví dụ:

~~~text
Controller returns: Mono<Message>
        |
        v
HandlerResult(returnValue = Mono<Message>, returnType = ...)
        |
        v
ResponseBodyResultHandler.handleResult(...)
        |
        v
Mono<Void>  <-- hoàn tất khi pipeline ghi response xong
~~~

Không tự gọi `subscribe()` bên trong controller chỉ để response được gửi. Spring WebFlux runtime đăng ký và điều phối subscription của pipeline request/response. Tự subscribe làm việc ngoài response pipeline có thể khiến lỗi, cancellation và backpressure không còn được xử lý theo vòng đời request.

## 3. HandlerResult mang những thông tin nào?

`HandlerResult` không đơn giản chỉ là Java object. Nó giữ những thông tin cần để framework diễn giải return value:

- Handler đã được gọi (ví dụ controller method).
- Return value thực tế (có thể là DTO, `Mono`, `Flux`, `ResponseEntity`, `ServerResponse` hoặc `null`).
- Kiểu trả về và thông tin generic type, thường biểu diễn qua `ResolvableType`.
- `BindingContext` và các dữ liệu liên quan đến model/binding.
- Trong trường hợp phù hợp, cơ chế `DispatchExceptionHandler` mà adapter có thể gắn vào result để xử lý lỗi ở bước ghi.

Đặc biệt với generic type, `Flux<Message>` cần được hiểu là stream các `Message` để chọn writer phù hợp. Nếu chỉ dựa trên `Object.getClass()` thì sẽ nhìn thấy lớp publisher của Reactor, không tự suy ra cấu trúc dữ liệu hay media type.

Có hai trường hợp khác nhau:

~~~java
Mono<Message>                  // body được tạo bất đồng bộ
Mono<ResponseEntity<Message>>  // status + headers + body cũng xác định bất đồng bộ
~~~

Trong trường hợp đầu, hạ tầng response body sử dụng reactive adapter, codec và content negotiation để ghi DTO. Trong trường hợp thứ hai, kết quả cuối cùng phải được diễn giải theo `ResponseEntity` để lấy status và headers trước khi ghi body.

`HandlerResult` là abstraction nội bộ của WebFlux request handling; ứng dụng thường không cần tự tạo đối tượng này để viết controller bình thường.

## 4. WebFlux chọn result handler như thế nào?

WebFlux lấy tập bean thực hiện `HandlerResultHandler` từ application context, sắp xếp theo thứ tự (`Ordered` / `@Order`), rồi chọn **result handler đầu tiên mà `supports(result)` trả true**.

Bảng implementation mặc định trong WebFlux config:

| Implementation | Dạng kết quả thường được xử lý | Default order |
| --- | --- | ---: |
| `ResponseEntityResultHandler` | `ResponseEntity` và các dạng reactive tương ứng từ annotated controller | `0` |
| `ServerResponseResultHandler` | `ServerResponse` của functional endpoint | `0` |
| `ResponseBodyResultHandler` | Method `@ResponseBody` hoặc class `@RestController`, gồm reactive values | `100` |
| `ViewResolutionResultHandler` | View name, `View`, `Rendering`, model và các giá trị dạng MVC view | `Integer.MAX_VALUE` |

**Hai result handler cùng order 0 không có nghĩa chúng đều ghi response.** Chúng có `supports` khác nhau, vì vậy thông thường chỉ một handler được chọn cho một `HandlerResult`.

Tại sao `ResponseEntityResultHandler` có thứ tự trước `ResponseBodyResultHandler`? Vì một method trong `@RestController` vẫn có thể trả `ResponseEntity<Message>`. Framework phải xử lý đó là HTTP response đầy đủ (status/headers/body), thay vì biến toàn bộ `ResponseEntity` thành một DTO JSON thông thường.

Tại sao `ViewResolutionResultHandler` có thứ tự cuối? Nó hỗ trợ nhiều dạng kết quả rộng nên cần nhường các handler cụ thể phía trước.

**Không phải pipeline ghi nối tiếp qua bốn result handlers.** `DispatcherHandler` chọn handler thích hợp đầu tiên, để handler đó hoàn tất kết quả. Đừng suy luận “ResponseBodyResultHandler chạy rồi ViewResolutionResultHandler lại chạy”.

## 5. ResponseBodyResultHandler: DTO và @RestController

Khi method có `@ResponseBody` hoặc nằm trong `@RestController`:

~~~java
@RestController
class GreetingController {
    @GetMapping("/api/greeting")
    Mono<Greeting> greeting() {
        return Mono.just(new Greeting("Xin chào"));
    }
}

record Greeting(String message) {}
~~~

Đây là đoạn minh họa annotation/return type, chưa phải project hoàn chỉnh. `ResponseBodyResultHandler` nhận kết quả từ annotated controller, dùng cấu hình message writers để chuyển `Greeting` thành JSON khi content negotiation chọn `application/json`.

Trình tự khái quát:

~~~text
Mono<Greeting>
   |
   +-- ReactiveAdapterRegistry hỗ trợ nhận biết kiểu reactive
   |
   +-- ResolvableType: dữ liệu phần tử là Greeting
   |
   +-- RequestedContentTypeResolver: thương lượng media type
   |
   +-- HttpMessageWriter phù hợp (ví dụ JSON encoder)
   |
   +-- ServerHttpResponse ghi DataBuffer / bytes
   |
   +-- Mono<Void> hoàn tất hoặc phát lỗi
~~~

Trong WebFlux, thành phần ghi response body là **`HttpMessageWriter`**, không phải `HttpMessageConverter` như cách mô tả điển hình của Spring MVC Servlet. Các codecs đọc và ghi có thể dùng Jackson, encoder/decoder khác hoặc writer cho text, binary, resource và media type cụ thể.

### 5.1. Mono, Flux và kiểu giá trị thường

| Controller return | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| `Greeting` | Đã có DTO | Encode thành body theo media type |
| `Mono<Greeting>` | 0 hoặc 1 DTO phát sinh async | Chờ publisher và encode DTO |
| `Flux<Greeting>` | Nhiều DTO | Encode nhiều phần tử; cách framing phụ thuộc media type |
| `Mono<Void>` | Công việc async không tạo dữ liệu trả về | Hoàn tất response theo contract endpoint |
| `ResponseEntity<Greeting>` | Status/headers/body trực tiếp | Handler chuyên về ResponseEntity |
| `Mono<ResponseEntity<Greeting>>` | Status/headers/body được xác định sau khi publisher phát giá trị | Handler ResponseEntity chờ kết quả |
| `ResponseEntity<Flux<Greeting>>` | Status/headers xác định sớm, body là stream | Ghi stream body với status/headers đã xác lập |

**`Mono.empty()` không tự động có nghĩa 404.** Với một endpoint trả `Mono<DTO>`, nếu không thiết lập chính sách khác, empty publisher không tự suy ra “resource không tồn tại”. Khi muốn 404, có thể dùng `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` hoặc trả `Mono<ResponseEntity<...>>` với nhánh 404.

### 5.2. Content negotiation: Accept và produces

Nếu client gửi `Accept: application/json` và endpoint trả DTO, WebFlux tìm writer có thể tạo representation tương ứng. Nếu không có representation chấp nhận được, server có thể trả **406 Not Acceptable**. `@GetMapping(produces=...)` giới hạn media types mà mapping hỗ trợ.

`Content-Type` nói về định dạng body đang gửi; `Accept` nói về định dạng body mà client có thể nhận. Nhầm hai header này dễ dẫn đến 406/415 khi testing.

### 5.3. Streaming không chỉ là đổi return type thành Flux

Một `Flux<T>` có thể được render như JSON array, newline-delimited JSON hoặc Server-Sent Events, tùy media type và encoder. Streaming qua mạng, flushing từng phần tử và độ trễ client quan sát được phụ thuộc codec, transport, proxy và media type, không phải riêng kiểu `Flux`.

Để truyền nhiều JSON object theo từng record, có thể dùng `application/x-ndjson`. Để push sự kiện tới browser qua HTTP, có thể dùng `text/event-stream`. Tránh dùng `application/json` rồi giả định client nhận từng object riêng lẻ ngay khi server phát phần tử.

## 6. ResponseEntityResultHandler: status, headers và body

`ResponseEntity` mô tả response gồm status/headers/body. WebFlux hỗ trợ nhiều dạng async:

~~~java
ResponseEntity<MyDto>
ResponseEntity<Mono<MyDto>>
ResponseEntity<Flux<MyDto>>
Mono<ResponseEntity<MyDto>>
Mono<ResponseEntity<Flux<MyDto>>>
~~~

Phân biệt thời điểm biết metadata:

- **`ResponseEntity<Flux<T>>`**: handler biết status và headers ngay khi method trả `ResponseEntity`; body vẫn được publish/encode sau.
- **`Mono<ResponseEntity<T>>`**: chưa biết status/headers cho tới khi publisher phát một `ResponseEntity`. Phù hợp khi kết quả truy vấn quyết định 200 hay 404.
- **`ResponseEntity<Mono<T>>`**: metadata có sớm, còn body chờ một giá trị.
- **`Mono<ResponseEntity<Flux<T>>>`**: metadata được xác định async, và body tiếp tục là một stream.

Ví dụ khi tài nguyên có thể vắng mặt:

~~~java
@GetMapping("/api/users/{id}")
Mono<ResponseEntity<UserView>> find(@PathVariable long id) {
    return userService.find(id)
        .map(user -> ResponseEntity.ok(new UserView(user.name())))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Đây là **đoạn minh họa trong controller**; giả định `userService.find(id)` trả `Mono<User>` và `UserView` được khai báo. Ý tưởng là 200 khi tìm được và 404 khi không thấy; không phải code độc lập để `javac` chạy nếu thiếu service/model.

Với body rỗng theo chủ đích, `ResponseEntity.noContent().build()` biểu đạt **204 No Content** rõ ràng hơn việc trả một DTO `null` và mong framework tự suy ra 204.

### 6.1. Không thay đổi status sau khi đã commit

Trước khi response được commit, result handler còn có thể thiết lập status và headers. Sau khi header đã được gửi/commit, việc đổi status từ 200 thành 500 thường không thể có hiệu lực đối với cùng response. Đây là lý do exception giữa một stream đã bắt đầu cần được xử lý khác với exception xảy ra trước khi ghi body.

## 7. ServerResponseResultHandler: functional endpoints

Spring WebFlux ngoài annotation controller còn hỗ trợ router function:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route(
    RequestPredicates.GET("/fn/hello"),
    request -> ServerResponse.ok().bodyValue(Map.of("kind", "functional"))
);
~~~

Đoạn trên là ví dụ cấu trúc API; ở project hoàn chỉnh bên dưới router được đăng ký làm `@Bean`.

`RouterFunctionMapping` chọn handler function, `HandlerFunctionAdapter` thực thi function và đưa kết quả vào luồng dispatch. `ServerResponseResultHandler` nhận `ServerResponse` và để response đó ghi status, headers, body bằng các message writers/view resolvers cần thiết.

Trong functional endpoints, `ServerResponse` là abstraction phản hồi của **WebFlux functional API**. Không nhầm nó với `org.springframework.web.reactive.function.client.ClientResponse` của WebClient, hoặc `ServerResponse` thuộc Spring MVC functional API ở package khác.

Ví dụ khác biệt:

~~~java
// Annotated controller:
@GetMapping("/api/hello")
Mono<Map<String, String>> hello() { ... }

// Functional handler function:
request -> ServerResponse.ok().bodyValue(Map.of("hello", "webflux"))
~~~

Chúng có thể tạo HTTP JSON tương đương nhưng được chuyển tới **những result handlers khác nhau**.

## 8. ViewResolutionResultHandler: trả HTML/view thay vì JSON body

Một `@Controller` dùng MVC-style view name:

~~~java
@Controller
class PageController {
    @GetMapping("/page")
    String page(Model model) {
        model.addAttribute("title", "Reactive page");
        return "home";
    }
}
~~~

Với view technology và `ViewResolver` phù hợp được cấu hình, `ViewResolutionResultHandler` diễn giải `"home"` là **logical view name**, tìm `View`, đưa model vào view và render response (ví dụ HTML).

Nhưng nếu dùng `@RestController` và trả `String`:

~~~java
@RestController
class TextController {
    @GetMapping("/text")
    String text() {
        return "home";
    }
}
~~~

`"home"` là **response body**, không phải tên view; `ResponseBodyResultHandler` được ưu tiên.

Lưu ý: chỉ có `spring-boot-starter-webflux` không đồng nghĩa hệ thống đã có template engine và template `home.html`. Nếu muốn render HTML, phải thêm và cấu hình view technology phù hợp (ví dụ Thymeleaf reactive integration) cùng template cần thiết. Nếu thiếu resolver/template, endpoint view có thể lỗi thay vì tự trả `"home"` dưới dạng plain text.

WebFlux không hỗ trợ `forward:` Servlet dispatch như Spring MVC Servlet. Hãy dùng redirect/view mechanism được WebFlux hỗ trợ nếu cần điều hướng.

## 9. Từ một publisher đến các byte trên HTTP response

Dù result handler chọn body khác nhau, các thao tác ghi response thường đi qua những abstraction:

| Thành phần | Ý nghĩa |
| --- | --- |
| `ServerWebExchange` | Ngữ cảnh request/response ở WebFlux, gồm `ServerHttpRequest`, `ServerHttpResponse` và exchange attributes |
| `ServerHttpResponse` | Thiết lập status, headers, cookie và ghi response body |
| `HttpMessageWriter<T>` | Mã hóa đối tượng thành representation thích hợp (JSON, text, binary, SSE...) |
| `Encoder` | Biến đối tượng thành dữ liệu `DataBuffer`/byte stream đối với những writer phù hợp |
| `DataBuffer` | Buffer chứa dữ liệu sẽ được ghi theo reactive pipeline |
| `Mono<Void>` | Đại diện completion/error của hoạt động ghi HTTP |
| `MediaType` | Định dạng representation và cách framing mà client/server thỏa thuận |

Các thao tác ở tầng thấp `ServerHttpResponse` gồm:

~~~java
response.setStatusCode(HttpStatus.OK);
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
return response.writeWith(publisherOfDataBuffers);
~~~

Đây chỉ là **mã minh họa trong một WebHandler/custom result handler**, giả định có `response` và `publisherOfDataBuffers` hợp lệ. Trong controller thông thường, nên trả DTO/`ResponseEntity` để WebFlux tự chọn writers thay vì tự tạo `DataBuffer`.

Một `HttpMessageWriter` có thể lựa chọn cách encode theo type, generic type, media type, hints và cấu hình codec. Không nên giả định mọi Java object đều tự động chuyển thành JSON; Jackson/codec tương ứng phải có trên classpath và request có media type phù hợp.

### 9.1. setComplete khác writeWith

- `response.setComplete()` trả về một publisher completion, phù hợp khi response đã thiết lập metadata và không cần body thêm.
- `response.writeWith(Publisher<? extends DataBuffer>)` ghi một publisher dữ liệu.
- `response.writeAndFlushWith(Publisher<? extends Publisher<? extends DataBuffer>>)` cho phép mô tả các nhóm dữ liệu cần flush (khi tầng transport hỗ trợ).
- `response.beforeCommit(Supplier<? extends Mono<Void>>)` đăng ký callback trước khi commit; callback cần trả publisher và phù hợp cho công việc trước commit.

Không gọi `writeWith` rồi một lần nữa gọi `setComplete` như một “bước bắt buộc” trong business controller. Mỗi thao tác phải được phối hợp đúng trong reactive pipeline; response chỉ được commit/hoàn tất theo vòng đời mà result handler quản lý.

### 9.2. Khi nào response đã commit?

Response được commit khi hạ tầng bắt đầu ghi kết quả ra client hoặc chủ động hoàn tất response; tại thời điểm đó status/headers không còn có thể được thay tùy ý. `ServerHttpResponse.isCommitted()` có thể dùng khi viết hạ tầng xử lý lỗi.

Đừng dựa vào thời điểm controller method `return` để suy rằng HTTP response đã commit. Với `Mono<ResponseEntity<T>>`, method có thể return publisher trước rất lâu so với lúc publisher phát giá trị và status được xác định.

### 9.3. Backpressure và cancellation

WebFlux dùng Reactive Streams để truyền dữ liệu theo tín hiệu demand giữa các tầng. Khi client đọc chậm, pipeline có thể phát ít dữ liệu hơn hoặc bị chậm lại; nhưng điều đó **không đảm bảo** mọi nguồn dữ liệu đều tự động backpressure-aware hoặc không buffering.

Khi client ngắt kết nối, phần ghi response có thể nhận cancellation/error. Tránh thao tác không thể hủy trong publisher, và quản lý tài nguyên qua các operator phù hợp như `usingWhen`, `doFinally` khi thật sự cần.

## 10. Ví dụ runnable: Spring Boot WebFlux với bốn dạng kết quả

Ví dụ dưới đây cho thấy cùng một ứng dụng có:

- REST controller trả `Mono<DTO>` → `ResponseBodyResultHandler`.
- REST controller trả `Mono<ResponseEntity<DTO>>` hoặc `ResponseEntity<Void>` → `ResponseEntityResultHandler`.
- REST controller trả `Flux<DTO>` với NDJSON hoặc `Flux<ServerSentEvent<String>>` → response body streaming.
- Functional route trả `Mono<ServerResponse>` → `ServerResponseResultHandler`.

Không thêm starter Servlet để tránh ứng dụng mặc định chuyển sang Spring MVC. Ví dụ cần JDK 21 và Gradle wrapper tương thích.

~~~text
webflux-result-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/resultdemo/
    │   ├── ResultDemoApplication.java
    │   ├── ResultController.java
    │   └── FunctionalRoutes.java
    └── test/java/com/example/resultdemo/
        └── ResultControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'webflux-result-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-webflux` thông thường kéo Reactor Netty làm web server mặc định. `reactor-test` được thêm tường minh nếu sau này cần `StepVerifier`; test ở đây dùng `WebTestClient`. Dependency versions do Spring Boot dependency management quản lý.

### 10.1. Main application

**src/main/java/com/example/resultdemo/ResultDemoApplication.java**

~~~java
package com.example.resultdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResultDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResultDemoApplication.class, args);
    }
}
~~~

### 10.2. Controller với các return types

**src/main/java/com/example/resultdemo/ResultController.java**

~~~java
package com.example.resultdemo;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ResultController {

    public record Message(String text) {
    }

    @GetMapping("/message")
    public Mono<Message> message() {
        return Mono.just(new Message("hello"));
    }

    @GetMapping("/accepted")
    public Mono<ResponseEntity<Message>> accepted() {
        return Mono.just(
            ResponseEntity.status(HttpStatus.ACCEPTED)
                .header("X-Result", "async")
                .body(new Message("queued"))
        );
    }

    @GetMapping("/empty")
    public ResponseEntity<Void> empty() {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/lookup/{id}")
    public Mono<ResponseEntity<Message>> lookup(@PathVariable long id) {
        // Dữ liệu giả để minh họa status động, không gọi database.
        return Mono.justOrEmpty(id == 1L ? new Message("found") : null)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(value = "/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Message> stream() {
        return Flux.fromIterable(List.of(
            new Message("first"), new Message("second")));
    }

    @GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.just("alpha", "beta")
            .map(value -> ServerSentEvent.<String>builder()
                .event("item")
                .data(value)
                .build());
    }
}
~~~

Đặc điểm của các endpoint:

| URL | Kiểu return | Kết quả dự kiến |
| --- | --- | --- |
| `GET /api/message` | `Mono<Message>` | 200 JSON có `text="hello"` |
| `GET /api/accepted` | `Mono<ResponseEntity<Message>>` | 202 Accepted, header `X-Result: async`, JSON |
| `GET /api/empty` | `ResponseEntity<Void>` | 204 No Content, không body |
| `GET /api/lookup/1` | `Mono<ResponseEntity<Message>>` | 200 JSON |
| `GET /api/lookup/2` | `Mono<ResponseEntity<Message>>` | 404 Not Found |
| `GET /api/stream` | `Flux<Message>` + NDJSON | 200, mỗi object thành một JSON record |
| `GET /api/events` | `Flux<ServerSentEvent<String>>` | 200 SSE, hai sự kiện |

`lookup` dùng dữ liệu giả để minh họa kết quả đồng bộ/async; trong service thật, Mono từ database/client reactive có thể quyết định kết quả. `Flux.just(...)` và `Flux.fromIterable(...)` kết thúc hữu hạn, giúp lệnh `curl` chạy xong; một SSE stream thật có thể kéo dài vô thời hạn.

### 10.3. Functional router

**src/main/java/com/example/resultdemo/FunctionalRoutes.java**

~~~java
package com.example.resultdemo;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> exampleRoutes() {
        return route(GET("/fn/hello"),
            request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("kind", "functional")));
    }
}
~~~

Functional handler tạo `Mono<ServerResponse>` thông qua `ServerResponse.ok().bodyValue(...)`. WebFlux chọn result handler phù hợp cho kiểu `ServerResponse` thay vì xử lý function như một `@RestController`.

### 10.4. Chạy ứng dụng

Nếu đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Nếu mới tạo project thủ công và đã cài Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Trên Windows PowerShell, dùng `.\gradlew.bat bootRun`. Với không có override, Spring Boot WebFlux thường mở port 8080; nếu port bận hoặc cấu hình khác, hãy kiểm tra startup log.

Thử các endpoint bằng `curl`:

~~~bash
curl -i http://localhost:8080/api/message
curl -i http://localhost:8080/api/accepted
curl -i http://localhost:8080/api/empty
curl -i http://localhost:8080/api/lookup/1
curl -i http://localhost:8080/api/lookup/2
curl -i http://localhost:8080/fn/hello
~~~

Kỳ vọng:

- `/api/message`: HTTP **200**, JSON `{"text":"hello"}`.
- `/api/accepted`: HTTP **202**, header `X-Result: async`, JSON `{"text":"queued"}`.
- `/api/empty`: HTTP **204**, không có response body.
- `/api/lookup/1`: HTTP **200**, JSON `{"text":"found"}`.
- `/api/lookup/2`: HTTP **404**; body lỗi có thể thay đổi theo error handling mặc định.
- `/fn/hello`: HTTP **200**, JSON `{"kind":"functional"}`.

Thứ tự response headers, server header và định dạng body lỗi không được đảm bảo giống nhau ở mọi môi trường. Những kết quả trên là **kỳ vọng từ code**, không phải transcript một lần chạy thực tế.

### 10.5. NDJSON và SSE

NDJSON:

~~~bash
curl -i -N -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/stream
~~~

Body kỳ vọng:

~~~text
{"text":"first"}
{"text":"second"}
~~~

Mỗi dòng là một JSON object hoàn chỉnh; proxy/network có thể ảnh hưởng thời điểm nhận từng chunk. Không hiểu hai dòng này là một JSON array.

SSE:

~~~bash
curl -i -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/events
~~~

Các sự kiện dự kiến có dạng:

~~~text
event:item
data:alpha

event:item
data:beta

~~~

Cấu trúc event/data phù hợp chuẩn SSE; thứ tự một số metadata và cách flush phụ thuộc writer/transport. Với endpoint SSE liên tục, connection có thể tồn tại lâu; cần tính đến cancellation, resource cleanup và proxy timeouts.

## 11. Kiểm thử response status, header và JSON bằng WebTestClient

**src/test/java/com/example/resultdemo/ResultControllerTest.java**

~~~java
package com.example.resultdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = ResultController.class)
class ResultControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void bodyResultHandlerWritesJson() {
        client.get().uri("/api/message")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello");
    }

    @Test
    void responseEntityResultHandlerWritesStatusAndHeader() {
        client.get().uri("/api/accepted")
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader().valueEquals("X-Result", "async")
            .expectBody()
            .jsonPath("$.text").isEqualTo("queued");
    }

    @Test
    void noContentHasNoBody() {
        client.get().uri("/api/empty")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void missingResourceBecomes404() {
        client.get().uri("/api/lookup/2")
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

`@WebFluxTest` tạo WebFlux test slice cho controller; `WebTestClient` gửi request vào WebFlux test chain mà không nhất thiết khởi động server lắng nghe socket. Đoạn này không cố kiểm tra functional router vì `@WebFluxTest` chỉ đưa các bean thích hợp của slice vào context, thường không bao gồm tất cả `@Configuration`/route beans của ứng dụng.

Muốn test **functional route** độc lập, có thể bind `WebTestClient` trực tiếp với `RouterFunction` trong unit/slice test, hoặc sử dụng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và client HTTP để kiểm tra cả application context và runtime server thực tế.

Test trên chứng minh controller trả response đúng. Nó không chứng minh Netty flush chunk tại một thời điểm cụ thể, hay ứng dụng chịu tải thực tế tốt. Streaming/backpressure cần test riêng bằng `StepVerifier`, client nhận nhiều chunks và test cancellation.

## 12. Ghi status, headers và response body: thứ tự hợp lệ

Trong reactive HTTP server, status/headers cần được xác định **trước khi response commit**. Trình tự an toàn về mặt ý tưởng:

~~~text
HandlerResult
    |
    v
Chọn HandlerResultHandler
    |
    v
Xác định status, headers, content type
    |
    v
Chọn HttpMessageWriter hoặc View
    |
    v
Subscribe / produce body buffers
    |
    v
Commit response, write chunks, flush theo media type
    |
    v
Complete hoặc error/cancel
~~~

Không giả định mọi response chỉ commit sau khi toàn bộ body được tạo. Với streaming, status có thể đã gửi trước khi item cuối cùng được publish.

### 12.1. ResponseBodyResultHandler có tự đặt status không?

Nó phụ trách serialize body và xử lý những thông tin response liên quan. Status có thể đến từ annotation như `@ResponseStatus`, exception handling hoặc custom logic khác; nếu không có override, HTTP 200 là giá trị thông thường cho response thành công có body.

Muốn status rõ ràng và nhất quán, trả `ResponseEntity` hoặc dùng annotation/status mechanism thích hợp. Không trông chờ việc `Mono.empty()` tự suy ra HTTP 404.

### 12.2. HEAD và 204 không ghi body thông thường

HTTP **HEAD** yêu cầu server không gửi representation body, dù có thể có representation headers. Với **204 No Content**, response không mang message body; nên chọn `ResponseEntity.noContent().build()` thay vì mã hóa một chuỗi rỗng không rõ nghĩa.

### 12.3. Đừng viết response hai lần

Một lỗi trong custom `WebFilter` hoặc `WebExceptionHandler` là ghi body và đồng thời để downstream tiếp tục ghi thêm body vào cùng response. Sau commit, các nỗ lực sửa status/headers hoặc ghi thêm byte có thể thất bại.

Khi can thiệp pipeline, biết rõ ai **sở hữu** completion. Với controller thông thường, return publisher và để result handler của framework thực hiện việc ghi là cách dễ bảo trì nhất.

## 13. Lỗi khi return value là reactive publisher

Lỗi có thể xảy ra:

1. Ngay khi handler method đang được gọi.
2. Khi publisher được subscribe và phát tín hiệu lỗi trước giá trị đầu tiên.
3. Khi encoder/codec serialize data.
4. Sau khi streaming response đã bắt đầu và vài phần tử đã được ghi.
5. Khi client disconnect hoặc transport gặp lỗi.

Mức độ có thể thay đổi response khác nhau:

| Thời điểm lỗi | Điều thường còn có thể làm |
| --- | --- |
| Trước khi status/headers được commit | Ánh xạ lỗi sang status/body khác theo exception handling |
| Trong lúc chọn codec/content negotiation | Thường còn có thể trả lỗi nếu chưa commit |
| Sau khi body đã bắt đầu stream | Không thể thay HTTP status đã gửi; thường phải kết thúc/lỗi stream |
| Khi client đã ngắt kết nối | Không thể gửi response mới cho client; cleanup tài nguyên và log đúng mức |

Spring WebFlux hỗ trợ xử lý exception qua annotated `@ExceptionHandler`, `@ControllerAdvice`/`@RestControllerAdvice`, `DispatchExceptionHandler` và tầng `WebExceptionHandler`. Chúng **không thể đảo ngược** response đã commit. Một lỗi cuối stream không tự biến HTTP 200 đã gửi thành 500.

Ví dụ ứng dụng muốn trả 404 khi Mono không có giá trị:

~~~java
return service.find(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)));
~~~

Đây là code fragment giả định có `service` và `id` phù hợp. Nếu `service.find(id)` không có dữ liệu, lỗi được phát trước body; WebFlux có cơ hội phản hồi 404. Nếu body stream đang chạy và đã gửi data, handler lỗi không thể thay phần header cũ.

### 13.1. Operator onErrorResume và response commit

`onErrorResume` dùng để chuyển lỗi sang fallback publisher trong **reactive chain**. Đặt fallback phù hợp trước giai đoạn ghi giúp ứng dụng chủ động kiểm soát output. Nhưng nếu trong quá trình serialize stream, những phần tử đã gửi ra client thì không thể rút lại; fallback có thể biến thành thêm dữ liệu trong stream, không phải response HTTP mới với status khác.

### 13.2. Không tự subscribe hoặc block trên event-loop

Trong controller reactive:

~~~java
// Sai hướng xử lý:
var value = remoteCall.block();

// Cũng không nên fire-and-forget để tạo body:
remoteCall.subscribe();
return Mono.empty();
~~~

Đây là ví dụ phản diện, không phải chương trình hoàn chỉnh. `block()` trên event-loop có thể gây lỗi hoặc làm nghẽn khả năng phục vụ. `subscribe()` tự phát có thể tách công việc khỏi lifecycle request, mất cancellation và error propagation.

Nên compose:

~~~java
return remoteCall.map(this::toResponse);
~~~

Khi phải tích hợp I/O blocking legacy, dùng scheduler/adapter phù hợp và giới hạn mức song song, hoặc chọn Servlet/MVC khi workload thiên về blocking. Không coi `publishOn`/`subscribeOn` là công cụ sửa tự động cho mọi bottleneck.

## 14. SSE, NDJSON, JSON array và byte stream: chọn kiểu phản hồi

| Định dạng | Content-Type thường dùng | Dạng payload | Gợi ý |
| --- | --- | --- | --- |
| JSON đơn | `application/json` | Một JSON object | `Mono<DTO>` |
| JSON array | `application/json` | JSON array của nhiều phần tử | `Flux<DTO>` có thể được encoder viết thành array |
| NDJSON | `application/x-ndjson` | Mỗi dòng một JSON object | `Flux<DTO>` với produces NDJSON |
| SSE | `text/event-stream` | Các sự kiện `event:`/`data:` | `Flux<ServerSentEvent<T>>` |
| Text | `text/plain` | Chuỗi ký tự | `Mono<String>` hoặc body string |
| Binary | `application/octet-stream` | Byte/buffer stream | `DataBuffer`/`Resource` tùy endpoint |

Một HTTP client cần biết cách đọc format tương ứng. Ví dụ, JavaScript `EventSource` hiểu SSE, nhưng không dùng nó để đọc NDJSON như một stream SSE. Ngược lại, một JSON parser thông thường không coi nhiều dòng JSON objects độc lập là **một JSON document**.

### 14.1. Streaming có overhead thực tế

Một stream kéo dài giữ client connection lâu và yêu cầu xử lý heartbeat, proxy idle timeout, cancellation và số lượng subscriber. Không dùng SSE cho mọi endpoint chỉ vì muốn “reactive”.

### 14.2. Response encoding và memory

Dù `Flux` phát từng phần tử, một codec có thể cần buffering/framing tùy content type. Nếu một endpoint dùng `collectList()` để đợi toàn bộ Flux rồi mới trả, lợi ích streaming bị thay đổi và memory có thể tăng theo số phần tử. Cần thiết kế API đáp ứng kích thước dữ liệu và cách client consume.

### 14.3. Charset và binary

Với text, writer cần charset phù hợp; UTF-8 thường được sử dụng. Với binary/stream, cần quản lý DataBuffer và tài nguyên để tránh memory leak, đặc biệt khi tự xử lý buffer ngoài abstraction của framework. Nếu chỉ trả JSON hoặc text thông thường, dùng codec mặc định thay vì tự quản lý byte array.

## 15. So sánh với Spring MVC Servlet stack

| Tiêu chí | Spring WebFlux | Spring MVC |
| --- | --- | --- |
| Front controller | `DispatcherHandler` | `DispatcherServlet` |
| Kết quả sau khi gọi handler | `HandlerResult` | MVC return-value handling |
| Bước viết response | `HandlerResultHandler` + `HttpMessageWriter`/view | `HandlerMethodReturnValueHandler` + `HttpMessageConverter`/view |
| Server API | `ServerWebExchange` / `ServerHttpResponse` | Servlet `HttpServletRequest`/`HttpServletResponse` |
| Reactive type | Hỗ trợ chính thức trong toàn WebFlux pipeline | Có hỗ trợ reactive return types trong một số controller method |
| Model I/O | Reactive/non-blocking khi dependency và runtime hỗ trợ | Mặc định Servlet stack và synchronous API |
| Streaming | Flux, SSE/NDJSON, Reactive Streams | Servlet async/streaming tùy cơ chế |
| Hạ tầng mặc định của Boot starter | Reactor Netty (`starter-webflux`) | Tomcat (`starter-web`) |

**Không dùng `HttpMessageConverter` như tên chung cho mọi Spring web response.** Trong WebFlux, `HttpMessageWriter` là abstraction đặc trưng ở bước ghi reactive.

Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng xuất hiện, Boot thường tạo Servlet application type, khiến request được đi qua `DispatcherServlet` chứ không phải `DispatcherHandler`. Hãy xem classpath và startup logs trước khi debug “HandlerResultHandler không được gọi”.

## 16. Khi nào cần custom HandlerResultHandler?

Framework đã xử lý phần lớn return types phổ biến. Chỉ cân nhắc tự viết `HandlerResultHandler` khi ứng dụng cần một **return type đặc biệt** được hỗ trợ có kiểm soát trên toàn hệ thống, chẳng hạn một response wrapper/định dạng riêng mà cấu hình codec hay `ResponseEntity` không giải quyết tốt.

Ví dụ skeleton (chỉ minh họa contract, không phải một implementation hoàn chỉnh):

~~~java
import org.springframework.web.reactive.HandlerResult;
import org.springframework.web.reactive.HandlerResultHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class CustomResultHandler implements HandlerResultHandler {
    @Override
    public boolean supports(HandlerResult result) {
        // Chỉ nhận kiểu trả về đặc thù mà mình thực sự sở hữu.
        return false;
    }

    @Override
    public Mono<Void> handleResult(
            ServerWebExchange exchange, HandlerResult result) {
        // Khi tự ghi response, phải quản lý status, headers,
        // codec / DataBuffer, error, commit và cancellation.
        return exchange.getResponse().setComplete();
    }
}
~~~

Đây là **skeleton API nhằm học cách phân vai**, không đăng ký bean và cố ý không xử lý kết quả nào (`supports=false`). Không nên chép code này vào project và kỳ vọng nó tạo ra response cho controller.

Một custom handler thực tế phải:

1. Chỉ match return type của mình; tránh chiếm luôn kết quả `@RestController` thông thường.
2. Xác định `Ordered`/`@Order` thích hợp để không ghi đè các handler built-in ngoài ý định.
3. Tôn trọng negotiated content type và codec/buffer ownership.
4. Xử lý async completion, cancellation, lỗi trước/sau commit.
5. Kiểm thử nhiều return types và khả năng kết hợp với WebFlux config mặc định.

Nếu chỉ cần thay định dạng JSON hoặc thêm codec, **cấu hình HTTP message codecs** thường hợp lý hơn viết result handler. Nếu chỉ cần status/header khác, **`ResponseEntity`** là lựa chọn đơn giản hơn.

## 17. Những lỗi và hiểu nhầm thường gặp

### 17.1. “HandlerResultHandler là HandlerAdapter”

Sai. Adapter **thực thi handler**; result handler **xử lý kết quả** đã được adapter đóng gói. Một controller method có thể được gọi đúng nhưng client vẫn nhận lỗi do thiếu codec hoặc không có result handler phù hợp.

### 17.2. “Bốn result handler lần lượt ghi response”

Sai. Dispatcher chọn **handler đầu tiên hỗ trợ** kết quả theo order; không chạy nối tiếp bốn writer cho cùng một value.

### 17.3. “Mono<Void> là HTTP body rỗng của mọi endpoint”

Sai. `Mono<Void>` là kiểu completion signal của `HandlerResultHandler.handleResult`. Controller cũng có thể trả `Mono<Void>` trong những cách xử lý cụ thể, nhưng hai contract ở hai tầng khác nhau.

### 17.4. “Mono.empty() sẽ trả 404”

Không tự động. Hãy quy định 404 qua `ResponseEntity.notFound()` hoặc `ResponseStatusException` và chain thích hợp.

### 17.5. “Return String lúc nào cũng là plain text”

Sai. Trong `@Controller` không có `@ResponseBody`, String có thể là **view name**. Trong `@RestController`, String là **body**.

### 17.6. “Có Flux là client sẽ nhận từng object ngay lập tức”

Không chắc. Media type, codec, batching, flush behavior, proxy và client buffering đều ảnh hưởng. Dùng NDJSON/SSE khi cần framing streaming được định nghĩa rõ.

### 17.7. “Có thể đổi status 200 thành 500 sau khi đã stream một phần”

Không. Status/headers đã commit không thể bị thay hồi tố. Xử lý lỗi stream cần chiến lược giao thức và cleanup riêng.

### 17.8. “Không có @RequestBody thì response không thể là JSON”

`@RequestBody` liên quan **đọc request body**, còn `@ResponseBody`/`@RestController` liên quan **ghi response body**. Trộn lẫn input decoding với output encoding sẽ khiến debug sai chỗ.

### 17.9. “Spring WebFlux cũng dùng HttpMessageConverter giống MVC”

Sai khi mô tả WebFlux native: dùng `HttpMessageWriter`/`HttpMessageReader` và reactive codecs.

### 17.10. “ServerResponse của functional endpoint giống ResponseEntity”

Cả hai diễn đạt HTTP response, nhưng thuộc hai API với cách result handling khác nhau. `ServerResponse` của WebFlux functional API được xử lý bởi `ServerResponseResultHandler`; `ResponseEntity` từ annotated controller bởi `ResponseEntityResultHandler`.

### 17.11. “Cần tự subscribe() cho mọi Mono trả từ controller”

Không. Hạ tầng WebFlux subscribe và theo dõi lifecycle của HTTP response. Tự subscribe fire-and-forget dễ làm mất cancellation, tracing và error handling.

### 17.12. “WebFlux luôn nhanh hơn MVC”

Không có đảm bảo như vậy. Nếu nguồn dữ liệu blocking, gọi `block()` trên event-loop hoặc dùng database driver blocking không được xử lý đúng cách, throughput và latency có thể tệ hơn. Chọn stack theo workload và khả năng non-blocking end-to-end.

### 17.13. “Chỉ cần xem HTTP 200 là đủ để kiểm tra response writer”

Chưa đủ. Kiểm tra cả Content-Type, schema JSON, status trong trường hợp empty/error, header, cancellation, dạng framing của stream và behavior trước/sau response commit.

## 18. Checklist tự đánh giá kết quả WebFlux

1. Ứng dụng thực sự chạy **WebFlux REACTIVE** hay đang là MVC SERVLET vì có cả hai starter?
2. Request được tìm bởi HandlerMapping nào: annotated controller hay functional route?
3. HandlerAdapter trả `HandlerResult` với return value/type như mong đợi không?
4. Result handler nào có `supports(result)` đúng: ResponseEntity, ServerResponse, ResponseBody hay View?
5. Return type có `Mono`, `Flux`, `ResponseEntity` bọc ngoài/bên trong reactive publisher không?
6. Status/headers được quyết định trước hay sau khi publisher phát giá trị?
7. Media type được chọn theo `Accept`, `produces` và writers nào?
8. JSON, NDJSON, SSE hoặc HTML view có định dạng và framing đúng không?
9. Có tự `subscribe()` hoặc `block()` không cần thiết trong request pipeline không?
10. Lỗi được phát trước khi response commit hay sau khi đã gửi data?
11. Error handler có đang cố đổi response khi `isCommitted()` đã true không?
12. Có phát sinh DataBuffer leak/buffering không giới hạn, đặc biệt trong stream lớn không?
13. Khi client ngắt kết nối, reactive pipeline có dọn tài nguyên không?
14. Test đã kiểm tra status, headers, body, empty case và error case chưa?
15. Test streaming đã phân biệt content type, flush và consumption ở client chưa?
16. Khi cần custom result type, đã xem codec/ResponseEntity trước khi viết custom result handler chưa?

**Kết luận:** Trong Spring WebFlux, `HandlerResultHandler` là mắt xích biến kết quả gọi handler thành HTTP response. `ResponseBodyResultHandler` ghi DTO/reactive body; `ResponseEntityResultHandler` xử lý status, headers và body của `ResponseEntity`; `ServerResponseResultHandler` phục vụ functional endpoints; `ViewResolutionResultHandler` render view/model. Cách chọn handler dựa trên hỗ trợ return type và thứ tự, còn việc encode/ghi response dựa vào message writers, media type và reactive pipeline. Hiểu ranh giới **mapping → adaptation → result handling → response write/commit** giúp giải thích vì sao controller chạy đúng mà response vẫn sai, và giúp thiết kế xử lý lỗi/streaming có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring Framework — DispatcherHandler, Result Handling](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): các HandlerResultHandler, thứ tự và exception handling.
- [Spring Framework 6.1 — HandlerResultHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html): `supports`, `handleResult`, `Mono<Void>`.
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): body encoding bằng `HttpMessageWriter`.
- [Spring Framework — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): nested Mono/Flux và status/headers.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, ServerResponse.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): cấu hình và mở rộng HTTP codecs.
