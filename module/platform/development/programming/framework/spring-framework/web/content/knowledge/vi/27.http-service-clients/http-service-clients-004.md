# HTTP Service Client: Kiểu trả về đồng bộ, reactive và phản hồi ResponseEntity

## Mục tiêu

Spring Framework cho phép khai báo lời gọi HTTP từ xa dưới dạng **Java interface** có `@HttpExchange`, `@GetExchange`, `@PostExchange`… rồi tạo implementation bằng `HttpServiceProxyFactory`. Interface không chứa code tự gọi HTTP; **adapter** sẽ quyết định dùng `RestClient`, `RestTemplate` hoặc `WebClient`.

Sau bài này, bạn có thể:
- Chọn **kiểu trả về đồng bộ** như `Book`, `List<Book>`, `void`, `HttpHeaders`, `ResponseEntity<Book>`.
- Chọn **kiểu trả về reactive** như `Mono<Book>`, `Flux<Book>`, `Mono<Void>`, `Mono<ResponseEntity<Book>>` và `Mono<ResponseEntity<Flux<Book>>>`.
- Hiểu lúc nào thực sự có HTTP I/O, lúc nào body đã được giải mã, và cách xem status/header.
- Thiết kế API client đúng ngữ nghĩa, xử lý lỗi 4xx/5xx, tránh block nhầm event loop và tránh nhầm kiểu return của HTTP client với return của Spring MVC/WebFlux controller.

Phạm vi là **HTTP Interface Client phía gọi dịch vụ** trong Spring Framework 6.1–6.2, Java 17+, không phải một bài tổng quan tất cả kiểu return của controller.

## 1. Tại sao kiểu trả về phụ thuộc HTTP adapter?

Ví dụ cùng endpoint `GET /books/7`, hai interface sau có thể cùng đọc một body JSON, nhưng có cách sử dụng rất khác:

```java
interface SyncBooks {
    @GetExchange("/books/{id}")
    Book getBook(@PathVariable("id") long id);
}

interface ReactiveBooks {
    @GetExchange("/books/{id}")
    Mono<Book> getBook(@PathVariable("id") long id);
}
```

`Book` là DTO, ví dụ `record Book(long id, String title) {}`.

- `SyncBooks.getBook(7)`: lời gọi chỉ trả về `Book` sau khi đã hoàn thành phần HTTP I/O/đọc body, hoặc ném exception. Luồng thực thi của caller **chờ kết quả**.
- `ReactiveBooks.getBook(7)`: lời gọi lập tức cung cấp một `Mono<Book>` mô tả xử lý HTTP. **Subscription** bắt đầu pipeline và sau đó phát body hoặc tín hiệu lỗi. Không được hiểu `Mono<Book>` là `Book` đã có sẵn.
- Nếu cần status/header bên cạnh body, dùng `ResponseEntity<Book>` hoặc `Mono<ResponseEntity<Book>>`, tùy adapter và mô hình thực thi.

`HttpServiceProxyFactory` là thành phần tạo proxy, còn adapter gắn proxy vào client thực. Ký hiệu khái quát:

```text
Interface @GetExchange/@PostExchange
           |
           v
HttpServiceProxyFactory -> dynamic proxy
           |
           +-- RestClientAdapter / RestTemplateAdapter
           |       -> HTTP I/O đồng bộ -> T, HttpHeaders, ResponseEntity<T>, ...
           |
           +-- WebClientAdapter
                   -> HTTP I/O reactive -> Mono<T>, Flux<T>,
                      Mono<ResponseEntity<T>>, ...
```

**Quy tắc cốt lõi:** Kiểu return phải được **adapter bên dưới hỗ trợ**. Không thể khai báo tùy ý `Mono<Book>` rồi dùng `RestClientAdapter` với kỳ vọng Spring tự biến request thành non-blocking. `WebClientAdapter` ngoài reactive còn hỗ trợ kiểu đồng bộ, nhưng đồng bộ trên client reactive vẫn phải chờ kết quả; thường nên dùng dạng reactive khi ứng dụng đang chạy trên WebFlux.

## 2. Khởi tạo HTTP Service Client

### 2.1. Interface chỉ mô tả hợp đồng HTTP

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;

record Book(long id, String title) {}

interface BookHttpApi {
    @GetExchange("/books/{id}")
    ResponseEntity<Book> getBook(@PathVariable("id") long id);
}
```

`@GetExchange` đánh dấu HTTP GET và URI template; `@PathVariable` cung cấp biến `id`. Java interface có thể chứa nhiều phương thức cho các endpoint khác nhau. Các annotation khai báo request, không quyết định blocking/reactive một cách độc lập.

### 2.2. Adapter đồng bộ với RestClient

```java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

BookHttpApi api = HttpServiceProxyFactory
        .builderFor(RestClientAdapter.create(restClient))
        .build()
        .createClient(BookHttpApi.class);

ResponseEntity<Book> response = api.getBook(7);
```

Đây là code **minh họa đặt trong method/configuration**, không phải một Java file chạy độc lập. `RestClientAdapter` có từ Spring Framework 6.1, sử dụng `HttpExchangeAdapter` và hỗ trợ kiểu return đồng bộ.

### 2.3. Adapter reactive với WebClient

```java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

ReactiveBookApi api = HttpServiceProxyFactory
        .builderFor(WebClientAdapter.create(webClient))
        .build()
        .createClient(ReactiveBookApi.class);
```

Ở ví dụ trên, `ReactiveBookApi` là interface riêng với phương thức trả về `Mono`/`Flux`; nó được định nghĩa trong phần tiếp theo. `WebClientAdapter` hỗ trợ `ReactorHttpExchangeAdapter`. Nếu project đang dùng Spring 6.0, một số builder factory APIs khác với ví dụ Spring 6.1+; kiểm tra Javadoc của phiên bản thực tế.

Trong Spring Boot, ưu tiên builder do framework cung cấp để nhận cấu hình chung, codecs và customizers. Nếu chỉ sử dụng `RestClient`, dùng dependency Spring Web tương ứng; nếu dùng `WebClient` và Reactor, thường cần `spring-boot-starter-webflux`. Việc dùng WebClient làm HTTP client không bắt buộc controller phía server phải chạy WebFlux.

## 3. Nhóm kiểu trả về đồng bộ

Adapter của `RestClient` hoặc `RestTemplate` hỗ trợ những kiểu return sau:

| Kiểu trả về của interface | Ý nghĩa sau khi method kết thúc | Khi nên dùng |
| --- | --- | --- |
| `void` | Request đã được thực hiện; bỏ qua nội dung response | Lệnh không cần body/status |
| `HttpHeaders` | Có response headers; không giữ body làm kết quả | Chỉ cần ETag, content type hoặc metadata |
| `T` | Response body đã được giải mã thành `T` | Chỉ cần dữ liệu nghiệp vụ |
| `ResponseEntity<Void>` | Có HTTP status + headers, không cần body | DELETE/POST/HEAD cần kiểm tra status |
| `ResponseEntity<T>` | Có status + headers + body `T` | Cần cả payload lẫn metadata HTTP |

Ví dụ:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.annotation.RequestBody;

interface SyncBookApi {
    @GetExchange("/books/{id}")
    Book getBook(@PathVariable("id") long id);

    @GetExchange("/books")
    java.util.List<Book> listBooks();

    @GetExchange("/books/{id}")
    HttpHeaders getBookHeaders(@PathVariable("id") long id);

    @GetExchange("/books/{id}")
    ResponseEntity<Book> getBookResponse(@PathVariable("id") long id);

    @DeleteExchange("/books/{id}")
    ResponseEntity<Void> deleteBook(@PathVariable("id") long id);

    @PostExchange("/books/refresh")
    void requestRefresh();
}
```

Đoạn này là **hợp đồng minh họa**: backend phải thực sự cung cấp các endpoint. `Book` đã là DTO ở phần trước, `List<Book>` diễn đạt một JSON array khi codec hỗ trợ. Chú ý `void` chỉ nói không có giá trị trả về ở Java; HTTP vẫn thực sự có status và có thể báo lỗi.

### 3.1. T (DTO, String, List<T>)

```java
Book book = api.getBook(7);
System.out.println(book.title());
```

Với `T`, code gọi nhận body trực tiếp sau khi request hoàn tất. Nếu server trả HTTP 204 hoặc body rỗng, không nên giả định một DTO hợp lệ luôn tồn tại; kết quả thiếu body phải được xử lý theo hợp đồng endpoint. Tránh dereference `book.title()` khi có khả năng kết quả null.

Đối với collection/generic body, proxy có thể dùng thông tin generic ở chữ ký method để codec giải mã đúng `List<Book>`; đừng dùng `Object`/raw `List` nếu cần kiểm soát cấu trúc dữ liệu.

### 3.2. void và HttpHeaders

`void` phù hợp khi thành công/thất bại của HTTP call là điều duy nhất caller quan tâm, ví dụ kích hoạt thao tác không trả dữ liệu. `HttpHeaders` phù hợp khi chỉ muốn metadata, ví dụ:

```java
HttpHeaders headers = syncApi.getBookHeaders(7);
String etag = headers.getETag();
```

Điều này không có nghĩa bạn luôn biết status cụ thể. Nếu cần phân biệt HTTP 200 và 202 hoặc kiểm tra `Location` kèm status 201, chọn `ResponseEntity<Void>` hoặc `ResponseEntity<T>`.

### 3.3. ResponseEntity<T> và ResponseEntity<Void>

`org.springframework.http.ResponseEntity<T>` là đối tượng chứa ba phần:

```text
ResponseEntity<T>
  - statusCode : HttpStatusCode
  - headers    : HttpHeaders
  - body       : T, có thể null
```

Ví dụ:

```java
ResponseEntity<Book> response = syncApi.getBookResponse(7);

int status = response.getStatusCode().value();
String etag = response.getHeaders().getETag();
Book body = response.getBody();
```

`ResponseEntity<Void>` là lựa chọn rõ ý cho endpoint không cần payload:

```java
ResponseEntity<Void> response = syncApi.deleteBook(7);
boolean noContent = response.getStatusCode().value() == 204;
```

**Lưu ý:** `ResponseEntity` nhận từ HTTP client là **phản hồi của dịch vụ ở xa**. Nó không tự được gửi tiếp cho trình duyệt. Khi trả từ một controller, Spring MVC/WebFlux lại dùng `ResponseEntity` để **xây phản hồi server của ứng dụng mình**. Hai ngữ cảnh có cùng class nhưng trách nhiệm khác nhau.

## 4. Nhóm kiểu trả về reactive

Với `WebClientAdapter`, các kiểu đồng bộ ở phần trước **vẫn có thể dùng**, đồng thời có các kiểu reactive sau:

| Kiểu | Dữ liệu và thời điểm có sẵn | Trường hợp sử dụng |
| --- | --- | --- |
| `Mono<Void>` | Tín hiệu hoàn tất/lỗi, không phát giá trị body | Lệnh không cần dữ liệu |
| `Mono<HttpHeaders>` | Headers xuất hiện bất đồng bộ | Chỉ đọc metadata |
| `Mono<T>` | 0 hoặc 1 body object được giải mã | Một resource |
| `Flux<T>` | Nhiều item theo reactive stream | Danh sách/stream |
| `Mono<ResponseEntity<Void>>` | Status + headers bất đồng bộ, không cần body | Thao tác cần quan sát status |
| `Mono<ResponseEntity<T>>` | Status + headers + body `T` bất đồng bộ | Đọc một body + status |
| `Mono<ResponseEntity<Flux<T>>>` | Status + headers bất đồng bộ, kèm stream body `Flux<T>` | Cần metadata trước/đồng thời đọc stream nhiều item |

Một interface minh họa:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

interface ReactiveBookApi {
    @GetExchange("/books/{id}")
    Mono<Book> getBook(@PathVariable("id") long id);

    @GetExchange("/books")
    Flux<Book> streamBooks();

    @GetExchange("/books/{id}")
    Mono<HttpHeaders> getBookHeaders(@PathVariable("id") long id);

    @GetExchange("/books/{id}")
    Mono<ResponseEntity<Book>> getBookResponse(@PathVariable("id") long id);

    @GetExchange("/books")
    Mono<ResponseEntity<Flux<Book>>> streamWithResponse();

    @DeleteExchange("/books/{id}")
    Mono<ResponseEntity<Void>> deleteBook(@PathVariable("id") long id);
}
```

Không phải endpoint JSON nào cũng phát item liên tục. `Flux<Book>` là kiểu phản ứng nhiều phần tử; việc truyền dữ liệu tuần tự trong quá trình tải phụ thuộc server, media type và codec. JSON array thường có thể được giải mã thành Flux các phần tử, nhưng nếu cần streaming thực sự trong thời gian dài, cần một giao thức/media type thích hợp như NDJSON hoặc SSE.

### 4.1. Mono<T> và Flux<T>

```java
Mono<Book> one = reactiveApi.getBook(7);
Flux<Book> many = reactiveApi.streamBooks();

Mono<String> name = one.map(Book::title);
Mono<java.util.List<Book>> collected = many.collectList();
```

`one` và `many` chỉ là publisher; không có giá trị ở đây để sử dụng đồng bộ. Khi trong WebFlux controller:

```java
@GetMapping("/my-books/{id}")
public Mono<Book> fetch(@PathVariable long id) {
    return reactiveApi.getBook(id)
            .map(book -> new Book(book.id(), book.title()));
}
```

Đoạn controller này chỉ minh họa cách trả publisher, cần import `org.springframework.web.bind.annotation.GetMapping` và khai báo bên trong controller thực tế. Framework sẽ điều phối subscription; không cần `block()` ở đây.

- `Mono.empty()` biểu diễn hoàn tất không có item, **không giống** `Mono.just(null)` (Reactor không chấp nhận phần tử null).
- `Flux<T>` có thể hoàn thành, báo lỗi hoặc kéo dài vô hạn tùy server.
- `flatMap` dùng khi bước tiếp theo lại trả publisher, trong khi `map` dùng khi phép biến đổi trả giá trị thường.
- Khi gặp lỗi, publisher phát `onError`; kiểu trả về `Mono<T>` không biến HTTP 404 thành “có dữ liệu rỗng” theo mặc định.

### 4.2. Mono<Void> là tín hiệu hoàn tất

```java
interface ReactiveCommandApi {
    @PostExchange("/refresh")
    Mono<Void> refresh();
}
```

`Mono<Void>` không phát DTO; nó cho phép đợi request hoàn tất, phối hợp nhiều thao tác và nhận lỗi:

```java
Mono<Void> next = commandApi.refresh()
        .then(Mono.fromRunnable(() ->
                System.out.println("Refresh request completed")));
```

Trong đoạn trên, dòng in chỉ xảy ra khi publisher được subscribe và request kết thúc thành công. Nếu cần status 202 hay header `Retry-After`, nên dùng `Mono<ResponseEntity<Void>>`.

## 5. ResponseEntity trong reactive: chọn thứ tự bọc cho đúng

Đây là điểm dễ sai nhất vì các kiểu trông gần giống nhau.

### 5.1. Mono<ResponseEntity<T>>

```java
Mono<ResponseEntity<Book>> pending = reactiveApi.getBookResponse(7);

Mono<String> summary = pending.map(entity ->
        "status=" + entity.getStatusCode().value()
                + ", title=" + entity.getBody().title());
```

Phần tử do `Mono` phát ra là **một ResponseEntity đã có status/headers và body Book được giải mã**. `getBody()` vẫn có thể null nếu endpoint không trả body; code ví dụ trên giả định HTTP 200 có JSON hợp lệ. Dùng `Mono<ResponseEntity<T>>` khi muốn đồng thời xử lý body và status.

### 5.2. Mono<ResponseEntity<Flux<T>>>

```java
Mono<ResponseEntity<Flux<Book>>> pending =
        reactiveApi.streamWithResponse();

Mono<Integer> count = pending.flatMap(entity -> {
    int status = entity.getStatusCode().value();
    Flux<Book> body = entity.getBody();
    if (status != 200 || body == null) {
        return Mono.error(new IllegalStateException(
                "Unexpected status or missing body"));
    }
    return body.count().map(Long::intValue);
});
```

**Hai tầng bất đồng bộ:** `Mono` ngoài phát `ResponseEntity` có status/headers; `Flux<Book>` bên trong đại diện phần body có thể được tiêu thụ theo luồng. Đây là kiểu hữu ích khi cần truy cập metadata của response **mà không thu thập toàn bộ stream thành một danh sách trước**. Vì nó có thể stream, tránh `collectList()` trên luồng rất lớn/vô hạn nếu không có giới hạn.

### 5.3. Vì sao không mặc định dùng ResponseEntity<Mono<T>>?

Ở **WebFlux controller** (server), kiểu như `ResponseEntity<Mono<Book>>` hoặc `Mono<ResponseEntity<Book>>` có ý nghĩa khác nhau theo việc status/headers có sẵn trước hay sau publisher. Tuy nhiên, **kiểu return do proxy HTTP Interface Client hỗ trợ phụ thuộc tài liệu của HTTP adapter**. Với `WebClientAdapter`, chọn các kiểu chính thức được hỗ trợ như `Mono<ResponseEntity<T>>` hoặc `Mono<ResponseEntity<Flux<T>>>`; không bê nguyên bảng return của WebFlux controller sang interface client và mặc định mọi kiểu đều được hỗ trợ.

## 6. Ví dụ Java 17+ chạy được: so sánh cùng một server

Demo bên dưới chạy HTTP server nội bộ bằng JDK rồi gọi bằng cả `RestClientAdapter` và `WebClientAdapter`. Server có hai endpoint:

- `GET /books/7`: trả một `Book` cùng header `X-Source`.
- `GET /books`: trả JSON array hai cuốn sách.

Demo kiểm chứng `Book`, `ResponseEntity<Book>`, `Mono<Book>`, `Mono<ResponseEntity<Book>>` và `Flux<Book>`. Chương trình console được phép dùng `block(Duration)` để chờ kết quả cuối cùng; ứng dụng reactive thông thường nên tiếp tục trả publisher.

**Cấu trúc:**

```text
http-service-client-demo/
  build.gradle
  src/main/java/demo/HttpServiceReturnDemo.java
```

**build.gradle**:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.6')
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}

application {
    mainClass = 'demo.HttpServiceReturnDemo'
}
```

**src/main/java/demo/HttpServiceReturnDemo.java**:

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

public class HttpServiceReturnDemo {
    public record Book(long id, String title) {}

    interface SyncBooks {
        @GetExchange("/books/{id}")
        Book getBook(@PathVariable("id") long id);

        @GetExchange("/books/{id}")
        ResponseEntity<Book> getResponse(@PathVariable("id") long id);
    }

    interface ReactiveBooks {
        @GetExchange("/books/{id}")
        Mono<Book> getBook(@PathVariable("id") long id);

        @GetExchange("/books/{id}")
        Mono<ResponseEntity<Book>> getResponse(
                @PathVariable("id") long id);

        @GetExchange("/books")
        Flux<Book> getAllBooks();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/books", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                String json;
                int status;

                if (!"GET".equals(exchange.getRequestMethod())) {
                    json = "{\"error\":\"method not allowed\"}";
                    status = 405;
                } else if ("/books/7".equals(path)) {
                    json = "{\"id\":7,\"title\":\"Reactive Java\"}";
                    status = 200;
                } else if ("/books".equals(path)) {
                    json = "[{\"id\":7,\"title\":\"Reactive Java\"},"
                            + "{\"id\":8,\"title\":\"Spring HTTP\"}]";
                    status = 200;
                } else {
                    json = "{\"error\":\"not found\"}";
                    status = 404;
                }

                byte[] data = json.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders()
                        .set("Content-Type", "application/json");
                exchange.getResponseHeaders().set("X-Source", "local-api");
                exchange.sendResponseHeaders(status, data.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(data);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            RestClient restClient = RestClient.builder()
                    .baseUrl(baseUrl)
                    .build();
            SyncBooks sync = HttpServiceProxyFactory
                    .builderFor(RestClientAdapter.create(restClient))
                    .build()
                    .createClient(SyncBooks.class);

            WebClient webClient = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();
            ReactiveBooks reactive = HttpServiceProxyFactory
                    .builderFor(WebClientAdapter.create(webClient))
                    .build()
                    .createClient(ReactiveBooks.class);

            Book direct = sync.getBook(7);
            System.out.println("sync=" + direct.id()
                    + "/" + direct.title());

            ResponseEntity<Book> syncResponse = sync.getResponse(7);
            System.out.println("sync status="
                    + syncResponse.getStatusCode().value()
                    + ", source="
                    + syncResponse.getHeaders().getFirst("X-Source"));

            Mono<Book> pending = reactive.getBook(7);
            Book asyncBook = pending.block(Duration.ofSeconds(5));
            System.out.println("reactive=" + asyncBook.id()
                    + "/" + asyncBook.title());

            ResponseEntity<Book> asyncResponse = reactive
                    .getResponse(7)
                    .block(Duration.ofSeconds(5));
            System.out.println("reactive status="
                    + asyncResponse.getStatusCode().value());

            List<Book> allBooks = reactive.getAllBooks()
                    .collectList()
                    .block(Duration.ofSeconds(5));
            System.out.println("books=" + allBooks.size());
        } finally {
            server.stop(0);
        }
    }
}
```

Để chạy: cài JDK 17+ và Gradle; ở thư mục `http-service-client-demo` chạy:

```bash
gradle run
```

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew run` trên Unix/macOS hoặc `gradlew.bat run` trên Windows.

**Các dòng chương trình in ra stdout** (không tính log tải dependency/Gradle):

```text
sync=7/Reactive Java
sync status=200, source=local-api
reactive=7/Reactive Java
reactive status=200
books=2
```

Giải thích:

1. `sync.getBook(7)` dùng `RestClient` và trả về đối tượng `Book` sau lời gọi HTTP đồng bộ.
2. `sync.getResponse(7)` trả thêm status 200 và header `X-Source: local-api`.
3. `reactive.getBook(7)` trả `Mono<Book>`; `block` ở `main` kích hoạt pipeline rồi đợi giá trị.
4. `reactive.getResponse(7)` bọc toàn bộ phản hồi trong `Mono<ResponseEntity<Book>>`.
5. `reactive.getAllBooks()` trả `Flux<Book>`, `collectList` gom thành hai phần tử. Điều này hợp lý cho ví dụ hai item; với stream lớn, giữ cách xử lý từng item.

Demo dùng `HttpServer` của JDK; không cần chạy Spring Boot server riêng. URL được tạo bằng cổng hệ điều hành cấp phát nên không phụ thuộc một cổng cố định.

## 7. Khi nào chọn kiểu return nào?

| Nhu cầu thực tế | Adapter thích hợp | Kiểu return gợi ý |
| --- | --- | --- |
| Ứng dụng xử lý tuần tự, cần một DTO | `RestClientAdapter` | `Book` |
| Gọi API để trigger, bỏ qua body | `RestClientAdapter` | `void` |
| Chỉ cần headers đồng bộ | `RestClientAdapter` | `HttpHeaders` |
| DELETE cần kiểm tra 204 | `RestClientAdapter` | `ResponseEntity<Void>` |
| Đọc body và metadata HTTP đồng bộ | `RestClientAdapter` | `ResponseEntity<Book>` |
| WebFlux service đọc một DTO | `WebClientAdapter` | `Mono<Book>` |
| WebFlux đọc stream nhiều item | `WebClientAdapter` | `Flux<Book>` |
| WebFlux gọi lệnh chỉ quan tâm hoàn tất | `WebClientAdapter` | `Mono<Void>` |
| WebFlux cần status/header kèm một DTO | `WebClientAdapter` | `Mono<ResponseEntity<Book>>` |
| WebFlux cần status/header trước khi tiêu thụ stream body | `WebClientAdapter` | `Mono<ResponseEntity<Flux<Book>>>` |

Cách chọn dựa trên ba câu hỏi: (1) caller đang chạy đồng bộ hay reactive? (2) cần chỉ body hay cả status/header? (3) response gồm 0, 1 hay nhiều phần tử, và có cần streaming thật không?

**Không tự biến reactive thành blocking** chỉ vì muốn return `Book`. Nếu tầng trên đang dùng `Mono`/`Flux`, giữ chuỗi reactive đến biên hệ thống. Nếu ứng dụng cần đồng bộ, `RestClient` thường đơn giản hơn `WebClient` với kiểu return đồng bộ.

## 8. Lỗi HTTP, timeout và phạm vi ResponseEntity

### 8.1. ResponseEntity không đồng nghĩa chấp nhận mọi status

Với cấu hình mặc định, HTTP 4xx/5xx thường được client phát thành exception/tín hiệu lỗi:

- `RestClientAdapter`: thông qua `RestClient`, lỗi HTTP thông thường được phản ánh bằng `RestClientResponseException` và các subtype liên quan.
- `WebClientAdapter`: thông qua `WebClient`, lỗi HTTP thông thường được phản ánh bằng `WebClientResponseException` trên reactive error channel.

Điều này vẫn đúng khi khai báo `ResponseEntity<T>`; đừng kỳ vọng `ResponseEntity<Book>` sẽ tự động chứa body lỗi 404 trong mọi trường hợp. Muốn mapping status khác, hãy cấu hình **error/status handler trên HTTP client gốc** hoặc xử lý lỗi có chủ đích ở tầng service.

Ví dụ xử lý lỗi reactive mà vẫn giữ `Mono<Book>`:

```java
Mono<Book> book = reactiveApi.getBook(7)
        .onErrorResume(
                org.springframework.web.reactive.function.client
                        .WebClientResponseException.NotFound.class,
                notFound -> Mono.empty());
```

Ở đây 404 được chủ động chuyển thành hoàn tất rỗng. Không áp dụng chung cho mọi endpoint: có API dùng 404 để báo lỗi cấu hình hoặc quyền truy cập mà không nên âm thầm bỏ qua.

Ví dụ đồng bộ:

```java
try {
    Book book = syncApi.getBook(7);
} catch (org.springframework.web.client.HttpClientErrorException.NotFound ex) {
    // Xử lý riêng khi server trả HTTP 404.
}
```

Các đoạn xử lý lỗi trên giả định `syncApi`/`reactiveApi` được tạo bằng cấu hình client mặc định. Loại exception thực tế phụ thuộc adapter và status handler.

### 8.2. Timeout và blocking

Với `RestClientAdapter`, lời gọi sync chặn đến khi hoàn tất hoặc xảy ra timeout/lỗi cấu hình. Với `WebClientAdapter`, `Mono`/`Flux` không buộc thread của caller chờ; nhưng **kiểu đồng bộ** được dùng với adapter reactive sẽ phải đợi kết quả. Việc này có thể làm tắc event-loop và đánh mất lợi ích reactive.

Chọn connect/read/response timeout thích hợp ở HTTP client bên dưới. Với `WebClientAdapter`, Spring cũng hỗ trợ cấu hình timeout cho các lời gọi blocking, nhưng thường nên cấu hình timeout thực tế của HTTP connector để kiểm soát việc kết nối/đọc tốt hơn. `Mono.timeout(Duration)` áp dụng tại reactive pipeline nhưng không thay thế tất cả cấu hình mạng.

Đừng gọi `block()` trong WebFlux controller, Netty event loop hoặc code giữ vai trò xử lý reactive liên tục. Nếu cần tương tác với thư viện blocking, cân nhắc tách ranh giới và chuyển công việc blocking sang scheduler chuyên dụng; điều đó **không biến thư viện blocking thành non-blocking**.

### 8.3. Retry và số lần HTTP request

Một publisher reactive lạnh có thể phát lại request khi subscribe lại hoặc khi dùng `retry(...)`. Với GET idempotent, retry giới hạn có thể phù hợp cho một số lỗi mạng/transient; với POST tạo bản ghi/đơn hàng, cần hợp đồng idempotency rõ ràng. Không retry mù quáng 4xx và không đồng nhất tín hiệu `Mono.empty()` với HTTP 404.

## 9. Những nhầm lẫn phổ biến

1. **Khai báo `Mono<T>` nhưng dùng RestClientAdapter.** Adapter sync không hỗ trợ reactive return như WebClientAdapter; chọn adapter/return type nhất quán.
2. **Nghĩ WebClient luôn non-blocking khi return là `T`.** Một method sync vẫn phải chờ giá trị; reactive client hỗ trợ sync return không đồng nghĩa mọi luồng thực thi đều non-blocking.
3. **Nghĩ `Mono<T>` là kết quả đã có.** Nó là publisher, thường chưa có HTTP I/O trước subscription.
4. **Dùng `ResponseEntity<T>` khi chỉ cần body.** Lấy `T` hoặc `Mono<T>` trực tiếp để giảm coupling với chi tiết HTTP.
5. **Bỏ status/header khi workflow cần ETag, Location hoặc 202.** Dùng `ResponseEntity<T>`, `ResponseEntity<Void>` hoặc biến thể reactive tương ứng.
6. **Nhầm `Mono<ResponseEntity<T>>` với `ResponseEntity<Mono<T>>`.** Thứ tự bọc quyết định status/headers xuất hiện lúc nào; bảng return của controller không phải hợp đồng hỗ trợ của HTTP Interface Client.
7. **Dùng `Flux<T>` đồng nghĩa server luôn streaming.** Cần media type/codec và endpoint phù hợp; JSON array nhỏ có thể được gửi như một response hoàn chỉnh.
8. **Bỏ qua response rỗng.** `Mono<Void>` và `ResponseEntity<Void>` có ý nghĩa riêng; `getBody()` có thể null.
9. **Dùng ResponseEntity để “bắt” lỗi 404 trong mọi trường hợp.** Error handler mặc định của underlying client có thể đã biến 404 thành exception.
10. **Block ở event-loop hoặc retry POST không kiểm soát.** Cần tôn trọng mô hình xử lý và tính idempotent.
11. **Đọc quá nhiều dữ liệu vào bộ nhớ bằng `collectList()`.** Hữu ích cho danh sách nhỏ, nhưng không phù hợp với stream vô hạn hoặc payload lớn.
12. **Lẫn server controller với HTTP interface proxy.** `ResponseEntity` bên client mang phản hồi từ dịch vụ khác; bên controller dùng để xây HTTP response từ chính ứng dụng.

## 10. Bài tập ứng dụng

**Bài tập 1 — Chọn kiểu:** Endpoint `DELETE /jobs/{id}` trả 204 và header `X-Audit-Id`. Viết một phương thức đồng bộ và một phương thức reactive vẫn đọc được status/header. Gợi ý: `ResponseEntity<Void>` và `Mono<ResponseEntity<Void>>`.

**Bài tập 2 — So sánh return:** Trong demo, thêm vào `SyncBooks` một phương thức `HttpHeaders getHeaders(long id)` và in `X-Source`. Sau đó thêm `Mono<HttpHeaders>` tương ứng vào `ReactiveBooks`. Giải thích cách truy cập headers khác với giải mã body.

**Bài tập 3 — Status và stream:** Giả sử endpoint `/books` trả rất nhiều sách qua NDJSON và bạn cần đọc `X-Next-Cursor`. Giải thích vì sao `Mono<ResponseEntity<Flux<Book>>>` diễn đạt nhu cầu tốt hơn `Mono<List<Book>>`, và vì sao phải tránh `collectList()` với stream vô hạn.

**Bài tập 4 — Debug lỗi:** Thay `/books/7` bằng `/books/404` trong demo. Server sẽ trả HTTP 404. Quan sát sự khác biệt: method sync ném exception tại lời gọi, trong khi reactive `Mono` phát lỗi khi được subscribe. Vì sao việc return `ResponseEntity<Book>` không tự đảm bảo rằng bạn có thể đọc status 404 như response thành công?

## Tài liệu tham khảo chính thức

- Spring Framework 6.2, REST Clients / HTTP Interface / Return Values: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring WebClient: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html
- WebClientAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/function/client/support/WebClientAdapter.html
- RestClientAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/client/support/RestClientAdapter.html
