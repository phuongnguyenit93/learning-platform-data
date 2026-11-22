# Kết nối `HttpHandler` với máy chủ hỗ trợ không chặn trong Spring WebFlux

## 1. `HttpHandler` nằm ở đâu trong kiến trúc WebFlux?

Spring WebFlux cần một điểm giao tiếp chung giữa **logic xử lý HTTP của Spring** và **máy chủ HTTP thực tế**. `HttpHandler` là abstraction cấp thấp của Spring cho vòng đời một request/response. Máy chủ nhận kết nối và dữ liệu mạng; adapter chuyển request/response native của máy chủ sang các abstraction của Spring; `HttpHandler` thực hiện xử lý reactive và trả về một `Mono<Void>` đại diện cho quá trình hoàn thành response.

Một kiến trúc điển hình với Reactor Netty:

```text
HTTP client
    |
    | TCP / HTTP
    v
Reactor Netty HttpServer
    |
    | HttpServerRequest / HttpServerResponse
    v
ReactorHttpHandlerAdapter
    |
    | chuyển sang ServerHttpRequest / ServerHttpResponse
    v
Spring HttpHandler
    |
    | nếu dùng WebFlux stack
    v
HttpWebHandlerAdapter
    |
    | WebFilter, exception handling, WebHandler
    v
RouterFunction / annotated Controller / WebHandler
    |
    v
Mono<Void> hoàn tất response
```

Các thành phần có trách nhiệm khác nhau:

- **`HttpServer`** là máy chủ Reactor Netty: bind cổng, nhận kết nối, quản lý I/O non-blocking và gọi handler cho request.
- **`ReactorHttpHandlerAdapter`** là cầu nối giữa API request/response của Reactor Netty và interface `HttpHandler` của Spring.
- **`HttpHandler`** là hợp đồng xử lý HTTP của Spring, không tự mở socket hoặc lắng nghe cổng.
- **`HttpWebHandlerAdapter`** là adapter ở tầng WebFlux, chuyển `ServerHttpRequest`/`ServerHttpResponse` thành `ServerWebExchange` để gọi `WebHandler`.
- **`WebHandler`** là abstraction xử lý một `ServerWebExchange`; các WebFilter, xử lý exception, session, codec và controller có thể được ghép quanh tầng này.

Vì vậy, kết nối `HttpHandler` với server nghĩa là **đưa một implementation của `HttpHandler` vào adapter mà server hiểu**, để server gọi nó mỗi khi nhận request. Không cần để business controller biết chi tiết về socket hay API riêng của Reactor Netty.

## 2. Hợp đồng của `HttpHandler`

Interface `org.springframework.http.server.reactive.HttpHandler` có phương thức cốt lõi:

```java
public interface HttpHandler {
    Mono<Void> handle(
            ServerHttpRequest request,
            ServerHttpResponse response
    );
}
```

Đây là chữ ký API để tham khảo. `ServerHttpRequest` cung cấp method, URI, headers và body; `ServerHttpResponse` cho phép thiết lập status/header và ghi body.

`Mono<Void>` có ý nghĩa quan trọng:

- Hoàn tất (`onComplete`) khi xử lý request và ghi response hoàn tất.
- Phát `onError` khi quá trình xử lý thất bại.
- Có thể bị hủy (`cancel`) khi kết nối/request không còn được tiêu thụ.
- Không phát một giá trị `Void` như body; `Void` chỉ biểu thị hoàn tất.

Một handler đơn giản có thể trả về một body cố định:

```java
HttpHandler handler = (request, response) -> {
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
    byte[] bytes = "Hello from WebFlux".getBytes(StandardCharsets.UTF_8);

    DataBuffer buffer = response.bufferFactory().wrap(bytes);
    return response.writeWith(Mono.just(buffer));
};
```

Đây là đoạn code minh họa, cần import các kiểu Spring và Reactor. Handler không tự gọi `.subscribe()`: nó trả `Mono<Void>` cho server adapter để framework quản lý lifecycle, lỗi, hủy và ghi response.

## 3. Adapter kết nối Spring với Reactor Netty

Trong Spring Framework, `ReactorHttpHandlerAdapter` triển khai callback mà Reactor Netty có thể gọi. Về mặt sử dụng, việc kết nối gồm ba bước:

1. Tạo `HttpHandler` của Spring.
2. Bọc nó trong `ReactorHttpHandlerAdapter`.
3. Đăng ký adapter với `HttpServer.handle(...)`, rồi bind server vào địa chỉ/cổng.

```java
HttpHandler httpHandler = ...;

ReactorHttpHandlerAdapter adapter =
        new ReactorHttpHandlerAdapter(httpHandler);

DisposableServer server = HttpServer.create()
        .host("127.0.0.1")
        .port(8080)
        .handle(adapter)
        .bindNow();
```

`handle(adapter)` cung cấp callback xử lý request/response cho Reactor Netty. Khi request đến, adapter chuyển các đối tượng native của Netty thành abstraction tương ứng của Spring, gọi `HttpHandler.handle(...)` và trả kết quả reactive lại cho server.

**Adapter không phải là một server riêng.** Nó không bind cổng, không quản lý socket và không tự chạy vòng đời server. `HttpServer` mới là thành phần lắng nghe kết nối; adapter chỉ làm nhiệm vụ tương thích hai API.

Ngoài Reactor Netty, Spring WebFlux có thể tích hợp với một số server khác thông qua adapter tương ứng. Lựa chọn server phụ thuộc runtime/dependency và cách triển khai ứng dụng. Phần business logic ở tầng `HttpHandler`/`WebHandler` không nên phụ thuộc vào API riêng của một server nếu không thật sự cần.

## 4. Ghép `WebHandler` thành `HttpHandler` bằng `WebHttpHandlerBuilder`

Trong ứng dụng WebFlux đầy đủ, ta thường không tự viết toàn bộ tầng HTTP. `WebHandler` xử lý `ServerWebExchange`, còn `WebHttpHandlerBuilder` ghép các thành phần hạ tầng của Spring để tạo `HttpHandler`.

Một `WebHandler` tối giản:

```java
WebHandler webHandler = exchange -> {
    exchange.getResponse().setStatusCode(HttpStatus.OK);
    exchange.getResponse().getHeaders()
            .setContentType(MediaType.TEXT_PLAIN);

    byte[] bytes = "Hello from WebHandler"
            .getBytes(StandardCharsets.UTF_8);

    DataBuffer buffer = exchange.getResponse()
            .bufferFactory()
            .wrap(bytes);

    return exchange.getResponse().writeWith(Mono.just(buffer));
};
```

Có thể xây `HttpHandler` từ nó:

```java
HttpHandler httpHandler =
        WebHttpHandlerBuilder.webHandler(webHandler).build();
```

Sau đó đưa `httpHandler` vào `ReactorHttpHandlerAdapter` như mục trước. Trong ứng dụng dùng `ApplicationContext`, có thể dùng builder từ context để tự tìm và ghép các bean hạ tầng WebFlux phù hợp:

```java
HttpHandler httpHandler =
        WebHttpHandlerBuilder.applicationContext(applicationContext).build();
```

Builder có thể kết hợp các `WebFilter`, `WebExceptionHandler`, `WebSessionManager`, codec và thành phần hạ tầng khác đã được cấu hình. Cách xây từ `ApplicationContext` thường phù hợp hơn với ứng dụng Spring thực tế vì không bỏ sót cấu hình WebFlux.

Phân biệt ba abstraction:

| Kiểu | Đầu vào | Vai trò |
|---|---|---|
| `HttpHandler` | `ServerHttpRequest`, `ServerHttpResponse` | Hợp đồng HTTP cấp thấp của Spring |
| `WebHandler` | `ServerWebExchange` | Xử lý request/response ở tầng WebFlux |
| `ReactorHttpHandlerAdapter` | Request/response native của Reactor Netty | Chuyển API server thành lời gọi `HttpHandler` |

## 5. Chương trình Java 17+ chạy được: tự kết nối `HttpHandler` với Reactor Netty

Ví dụ sau không cần Spring Boot. Ta dùng trực tiếp Spring `HttpHandler`, adapter Reactor Netty và server `HttpServer` để thấy rõ ranh giới tích hợp.

Cấu trúc thư mục:

```text
http-handler-reactor-netty/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>http-handler-reactor-netty</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor.netty</groupId>
            <artifactId>reactor-netty-http</artifactId>
            <version>1.1.24</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.http.server.reactive.ReactorHttpHandlerAdapter;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

public final class Main {
    public static void main(String[] args) {
        HttpHandler httpHandler = (request, response) -> {
            response.getHeaders().setContentType(
                    new MediaType("text", "plain", StandardCharsets.UTF_8)
            );

            String body = "Hello from HttpHandler\n";
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

            DataBuffer buffer = response.bufferFactory().wrap(bytes);
            return response.writeWith(Mono.just(buffer));
        };

        ReactorHttpHandlerAdapter adapter =
                new ReactorHttpHandlerAdapter(httpHandler);

        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(8080)
                .handle(adapter)
                .bindNow();

        System.out.println(
                "Listening on http://127.0.0.1:" + server.port()
        );

        // Chờ server dừng trên main thread; không block event-loop thread.
        server.onDispose().block();
    }
}
```

Từ thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Console của server hiển thị:

```text
Listening on http://127.0.0.1:8080
```

Mở terminal khác và gọi:

```bash
curl -i http://127.0.0.1:8080/
```

Response body:

```text
Hello from HttpHandler
```

Có thể nhận header HTTP `200 OK` và `Content-Type: text/plain;charset=UTF-8` (cách hiển thị header có thể khác theo client/server). Nhấn `Ctrl+C` ở terminal chạy server để dừng chương trình.

**Đọc chương trình theo trách nhiệm:**

1. Lambda `HttpHandler` nhận request và response abstraction của Spring.
2. Handler thiết lập `Content-Type`, tạo `DataBuffer` từ byte UTF-8 và trả `response.writeWith(...)`.
3. `ReactorHttpHandlerAdapter` biến handler của Spring thành callback mà Reactor Netty hiểu.
4. `HttpServer.create()` cấu hình host/port; `.handle(adapter)` đăng ký callback; `.bindNow()` bắt đầu lắng nghe.
5. `server.onDispose().block()` giữ `main` chờ server dừng. Đây là chờ lifecycle trên **main thread của chương trình console**, không phải gọi `block()` bên trong handler hoặc event loop.

Ví dụ này sử dụng các phiên bản Spring Framework 6.1.14 và Reactor Netty 1.1.24 làm bộ phiên bản minh họa tương thích với Java 17. Trong dự án thật, ưu tiên quản lý phiên bản đồng bộ bằng Spring Boot BOM hoặc dependency management của dự án, tránh nâng riêng lẻ các thư viện nền tảng mà không kiểm tra tương thích.

## 6. Vòng đời bind, xử lý request và shutdown

Một server tích hợp theo cách thủ công thường có vòng đời:

```text
Tạo HttpHandler
     |
     v
Tạo ReactorHttpHandlerAdapter
     |
     v
HttpServer.create()
     |
     | handle(adapter)
     v
bindNow()
     |
     v
Server đang lắng nghe
     |
     +---- request A -> adapter -> HttpHandler -> Mono<Void>
     |
     +---- request B -> adapter -> HttpHandler -> Mono<Void>
     |
     v
dispose / process shutdown
```

Các phương thức lifecycle thường gặp:

- **`bind()`**: bắt đầu bind theo API reactive và trả Publisher của server khi bind hoàn tất.
- **`bindNow()`**: chờ bind hoàn tất và trả `DisposableServer`; tiện cho chương trình bootstrap đơn giản.
- **`onDispose()`**: Publisher hoàn tất khi server được dispose.
- **`dispose()`**: yêu cầu dừng server.
- **`disposeNow()`**: yêu cầu dừng và chờ theo API đồng bộ.

Ví dụ dừng có kiểm soát:

```java
server.dispose();
server.onDispose().block();
```

Chỉ dùng thao tác chờ đồng bộ ở luồng bootstrap/lifecycle phù hợp, không gọi nó trong request handler. Ứng dụng thực tế nên tích hợp shutdown với lifecycle của framework để đóng server và các tài nguyên liên quan theo đúng thứ tự.

Khi `bindNow()` thất bại (ví dụ cổng đã được tiến trình khác sử dụng), ứng dụng cần báo lỗi startup và không giả vờ server đã sẵn sàng. Trong môi trường triển khai, readiness probe nên chỉ thành công khi server đã bind và ứng dụng có thể phục vụ request.

## 7. Non-blocking server không có nghĩa mọi code đều non-blocking

Reactor Netty sử dụng event loop và I/O non-blocking để phục vụ nhiều kết nối với số lượng thread tương đối nhỏ. Tuy nhiên, handler vẫn có thể làm nghẽn event loop nếu gọi một API đồng bộ:

```java
// PHẢN VÍ DỤ: lệnh đồng bộ chạy ngay trên thread xử lý request.
HttpHandler handler = (request, response) -> {
    LegacyDao dao = ...;
    Customer customer = dao.loadCustomer(); // có thể chặn I/O
    return writeCustomer(response, customer);
};
```

Server non-blocking **không tự biến** `dao.loadCustomer()` thành bất đồng bộ. Khi event-loop thread bị chặn, các kết nối khác chia sẻ event loop có thể chậm theo.

Ưu tiên API reactive thực sự cho I/O, ví dụ WebClient hoặc R2DBC. Nếu bắt buộc tích hợp thư viện đồng bộ, cô lập chính lời gọi đó:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyDao.loadCustomer()
).subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` trì hoãn lời gọi; `subscribeOn(boundedElastic)` chuyển việc thực thi nguồn sang scheduler phù hợp với tác vụ có thể chặn. Sau đó ghép `Mono<Customer>` vào response pipeline. Không gọi `.block()` để lấy Customer trong handler; hãy tiếp tục bằng `map`, `flatMap` và trả `Mono<Void>` cuối cùng.

Ngoài ra, không dùng `Schedulers.boundedElastic()` như năng lực vô hạn. Cần timeout cho client/DAO, giới hạn concurrency và giám sát tải của hệ thống ngoài.

## 8. `DataBuffer` và ghi response đúng cách

Spring dùng `DataBuffer` để biểu diễn dữ liệu byte trong request/response. `ServerHttpResponse.writeWith(Publisher<? extends DataBuffer>)` cho phép ghi một chuỗi buffer reactive:

```java
Flux<DataBuffer> body = Flux.just("first\n", "second\n")
        .map(text -> response.bufferFactory().wrap(
                text.getBytes(StandardCharsets.UTF_8)
        ));

return response.writeWith(body);
```

Đây là đoạn minh họa cần biến `response` và import `Flux`. Dùng `Flux<DataBuffer>` phù hợp khi response được tạo dần theo từng phần, chẳng hạn stream nội dung hoặc sự kiện.

Một số điểm cần lưu ý:

- **Đừng gom toàn bộ body lớn vào một `byte[]` hoặc `List<DataBuffer>`** nếu mục tiêu là streaming; phát từng buffer theo nhu cầu phù hợp.
- `writeWith` trả `Mono<Void>` đại diện cho quá trình ghi, vì vậy phải trả Publisher đó từ handler.
- Không tự gọi `.subscribe()` lên body rồi trả `Mono.empty()`; cách đó tách việc ghi khỏi lifecycle response, dễ gây response kết thúc quá sớm hoặc lỗi không được framework quản lý.
- Buffer có thể dùng cơ chế reference-count tùy implementation. Khi tự cấp phát, giữ lại, discard hoặc xử lý buffer ngoài flow chuẩn, phải tuân thủ quy tắc retain/release của implementation; tránh giải phóng buffer hai lần hoặc giải phóng trước khi server ghi xong.
- Nếu xử lý body streaming, hãy thiết kế error/cancel và cleanup phù hợp; client ngắt kết nối có thể khiến việc ghi bị hủy.

## 9. Xử lý lỗi ở tầng `HttpHandler`

Vì `HttpHandler` trả `Mono<Void>`, lỗi có thể được biểu diễn reactive:

```java
HttpHandler handler = (request, response) ->
        Mono.error(new IllegalStateException("Cannot serve request"));
```

Đây là ví dụ cố tình phát lỗi, không phải handler hoàn chỉnh. Trong WebFlux stack được ghép bằng `WebHttpHandlerBuilder`, `WebExceptionHandler` và các thành phần xử lý lỗi có thể tham gia xử lý exception. Nếu tự triển khai `HttpHandler` trực tiếp, hãy xác định rõ cách ánh xạ lỗi sang status/body và bảo đảm response chưa bị commit trước khi cố ghi error response.

Ví dụ recovery có chủ đích cho lỗi nghiệp vụ:

```java
return service.load()
        .flatMap(value -> writeOkResponse(response, value))
        .onErrorResume(NotFoundException.class, error -> {
            response.setStatusCode(HttpStatus.NOT_FOUND);
            return response.setComplete();
        });
```

Đây là mã minh họa phụ thuộc `service`, `writeOkResponse` và `NotFoundException`. Khi response đã được commit một phần, không phải lúc nào cũng có thể thay status hoặc ghi body lỗi mới. Tránh bắt mọi lỗi rồi trả `200 OK` với body rỗng; giữ semantics HTTP đúng và log/trace lỗi ở ranh giới phù hợp.

## 10. Tích hợp với Spring Boot WebFlux: khi nào cần tự tạo adapter?

Trong ứng dụng Spring Boot thông thường, dependency `spring-boot-starter-webflux` cung cấp WebFlux và một server reactive mặc định (thường là Reactor Netty nếu không chọn server khác). Spring Boot tự cấu hình server, tạo adapter và quản lý lifecycle.

Một controller có thể đơn giản trả `Mono`:

```java
@RestController
class HelloController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello from WebFlux");
    }
}
```

Trong luồng này, developer không cần tự tạo `HttpServer`, `ReactorHttpHandlerAdapter` hay gọi `bindNow()`. Framework ghép controller thành handler chain và server adapter ở phía dưới.

Tự kết nối `HttpHandler` hữu ích khi:

- Viết ứng dụng server nhỏ không dùng toàn bộ auto-configuration của Boot.
- Tích hợp Spring HTTP handling với một Reactor Netty server đã được quản lý bên ngoài.
- Viết integration test hoặc adapter tùy biến ở ranh giới server.
- Tìm hiểu cách request đi từ server native vào Spring WebFlux.

Không nên tự khởi tạo một Reactor Netty server thứ hai trong ứng dụng Boot chỉ để xử lý một endpoint. Điều đó có thể mở cổng ngoài ý muốn, tách cấu hình TLS/port/metrics, gây khó quản lý shutdown và tạo hai server lifecycle trong cùng một ứng dụng.

Nếu cần tùy chỉnh server của Spring Boot, ưu tiên extension point và cấu hình chính thức của Boot. Chỉ tự quản lý `HttpServer` khi ứng dụng thực sự cần sở hữu lifecycle đó.

## 11. Kiểm thử `HttpHandler` mà không mở cổng thật

Với Spring WebFlux, có thể kiểm thử handler qua `WebTestClient` mà không cần bind server thật. `WebTestClient` hỗ trợ bind trực tiếp vào `HttpHandler`:

```java
WebTestClient client = WebTestClient.bindToHttpHandler(httpHandler).build();

client.get()
        .uri("/")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello from HttpHandler");
```

Đây là đoạn test minh họa. Cần dependency `spring-test` phù hợp và import `org.springframework.test.web.reactive.server.WebTestClient`. Cách này kiểm tra status và body ở ranh giới `HttpHandler` mà không phải chiếm cổng TCP. Nếu cần xác minh adapter Reactor Netty, cấu hình server thật, TLS, timeout hoặc network behavior, hãy bổ sung integration test trên cổng test phù hợp.

Kiểm thử nên bao gồm:

1. Request hợp lệ trả status/header/body mong đợi.
2. Path hoặc method không hỗ trợ trả status phù hợp.
3. Publisher body hoàn tất đúng, không subscribe lồng hoặc kết thúc response sớm.
4. Lỗi trong handler được ánh xạ đúng status/exception handler.
5. Client cancel/ngắt kết nối không làm rò tài nguyên.
6. Server bind/shutdown đúng lifecycle khi chạy integration test.

## 12. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Coi `HttpHandler` là máy chủ HTTP | Không có thành phần bind port hoặc nhận socket | Dùng server như Reactor Netty và adapter tương ứng |
| Đưa trực tiếp API Netty vào mọi service/controller | Business code bị khóa vào một server | Giữ logic ở `HttpHandler`/`WebHandler` hoặc tầng cao hơn |
| Quên bọc `HttpHandler` bằng adapter trước `HttpServer.handle` | Sai kiểu callback hoặc thiếu cầu nối giữa hai API | Dùng `new ReactorHttpHandlerAdapter(httpHandler)` |
| Handler tự gọi `.subscribe()` rồi trả `Mono.empty()` | Lifecycle ghi response tách rời, lỗi/cancel khó quản lý | Trả trực tiếp `Mono<Void>` từ `writeWith` hoặc pipeline cuối |
| Gọi `block()` trong handler | Chặn event-loop thread | Ghép Publisher bằng `map`/`flatMap`; cô lập blocking bằng `fromCallable` + `boundedElastic` |
| Tạo `DataBuffer` nhưng không trả Publisher ghi nó | Response có thể rỗng hoặc kết thúc sai | Trả `response.writeWith(Mono.just(buffer))` hoặc Flux buffer |
| Dùng `Mono.just(legacyDao.read())` | Lệnh blocking chạy eager trên thread hiện tại | `Mono.fromCallable(...).subscribeOn(boundedElastic())` |
| Tự tạo server riêng trong Spring Boot mà không quản lý shutdown | Cổng, TLS, metrics và lifecycle không đồng bộ | Ưu tiên auto-configuration/extension point của Boot |
| Nghĩ server non-blocking tự bảo vệ khỏi code blocking | Event loop vẫn có thể bị nghẽn | Dùng I/O reactive, timeout và scheduler phù hợp |
| Xử lý lỗi sau khi response đã commit | Không thể thay status/body một cách an toàn | Thiết kế error boundary trước khi commit, xử lý/log đúng trạng thái response |

## 13. Bài tập tự kiểm tra

**Câu 1.** `HttpHandler` có tự mở cổng 8080 và nhận kết nối TCP không?

**Đáp án:** Không. Nó chỉ là hợp đồng xử lý request/response của Spring. `HttpServer` hoặc một server khác mới lắng nghe cổng.

**Câu 2.** `ReactorHttpHandlerAdapter` có nhiệm vụ gì?

**Đáp án:** Chuyển request/response native của Reactor Netty thành abstraction Spring và gọi `HttpHandler`, rồi chuyển kết quả reactive lại cho server.

**Câu 3.** Vì sao `HttpHandler.handle(...)` trả `Mono<Void>`?

**Đáp án:** Để biểu diễn bất đồng bộ quá trình xử lý và hoàn tất response; nó phát complete/error/cancel chứ không phát một giá trị body kiểu `Void`.

**Câu 4.** `WebHandler` khác `HttpHandler` ở đâu?

**Đáp án:** `WebHandler` nhận một `ServerWebExchange`; `HttpHandler` nhận trực tiếp `ServerHttpRequest` và `ServerHttpResponse`. `HttpWebHandlerAdapter` ghép tầng WebFlux với hợp đồng HTTP cấp thấp.

**Câu 5.** Tại sao không gọi `.block()` trong `HttpHandler`?

**Đáp án:** Handler có thể chạy trên event-loop thread; block sẽ giữ thread đó trong lúc chờ và làm giảm khả năng phục vụ các request khác. Trả Publisher để server quản lý.

**Câu 6.** `server.onDispose().block()` trong `main()` có giống block trong request handler không?

**Đáp án:** Không. Trong ví dụ bootstrap, main thread chờ lifecycle server; request handler vẫn reactive. Không chuyển cách chờ đó vào event-loop thread.

**Câu 7.** Khi nào nên tự tạo `ReactorHttpHandlerAdapter` trong Spring Boot?

**Đáp án:** Chỉ khi ứng dụng thực sự tự sở hữu/tích hợp server lifecycle hoặc cần custom adapter. Với ứng dụng WebFlux Boot bình thường, framework đã cấu hình server và adapter.

## 14. Quy tắc áp dụng

- Giữ rõ ranh giới: **server nhận mạng → adapter chuyển API → `HttpHandler` xử lý reactive**.
- Dùng `ReactorHttpHandlerAdapter` để nối `HttpHandler` với Reactor Netty `HttpServer`.
- Dùng `WebHttpHandlerBuilder` khi cần ghép `WebHandler` với các thành phần hạ tầng WebFlux thành `HttpHandler`.
- Trả `Mono<Void>` cuối cùng từ response write; không tự subscribe bên trong handler.
- Giữ event loop không bị blocking; ưu tiên reactive client/driver, hoặc cô lập legacy blocking bằng `fromCallable` + `boundedElastic`.
- Quản lý bind, shutdown, timeout, DataBuffer và lỗi theo đúng lifecycle của server.
- Trong Spring Boot, ưu tiên auto-configuration; chỉ tự tạo server adapter khi cần quản lý tích hợp ở mức thấp.

**Ghi nhớ:** `HttpHandler` là hợp đồng HTTP reactive của Spring, còn `ReactorHttpHandlerAdapter` là cầu nối để Reactor Netty gọi hợp đồng đó. Máy chủ thực sự nhận kết nối và quản lý I/O; handler trả `Mono<Void>` để toàn bộ quá trình ghi response, lỗi và hủy được điều phối theo lifecycle reactive.
