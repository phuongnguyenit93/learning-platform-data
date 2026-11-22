# HttpServiceProxyFactory và adapter cho RestClient hoặc WebClient

## 1. Tổng quan: HTTP Service Client là gì?

Trong Spring Framework, **HTTP Service Client** là cách khai báo API HTTP từ xa bằng một **Java interface**. Mỗi phương thức interface được gắn annotation mô tả HTTP method, URL, headers, request body và kiểu response. **HttpServiceProxyFactory** tạo một proxy triển khai interface; khi ứng dụng gọi phương thức, proxy chuyển thành request thật qua một HTTP client đã được **adapter** bọc lại.

Ví dụ một endpoint GET /api/books/7 trả JSON:

~~~json
{"id":7,"title":"Spring in Action"}
~~~

Có thể viết interface:

~~~java
@HttpExchange(url = "/api/books", accept = MediaType.APPLICATION_JSON_VALUE)
public interface BookApi {
    @GetExchange("/{id}")
    Book findById(@PathVariable("id") long id);
}
~~~

Đến lúc gọi **bookApi.findById(7L)**, Spring tạo GET request phù hợp, decode JSON thành **Book** và trả cho caller. **Book** có thể là Java record:

~~~java
public record Book(long id, String title) {}
~~~

Đây là HTTP client **phía người gọi**. Nó không tự sinh endpoint cho server, không thay cho authentication, timeout, retry hay service discovery. Remote server vẫn phải có API đúng contract.

~~~text
Mã nghiệp vụ: bookApi.findById(7)
                  |
                  v
        Interface @HttpExchange
                  |
          HttpServiceProxyFactory
                  |
       Proxy đọc method + argument
                  |
           HttpExchangeAdapter
            /             \
 RestClientAdapter   WebClientAdapter
       |                    |
   RestClient            WebClient
    sync                 reactive
       \                    /
         HTTP request đến server
                  |
         JSON response -> Book
~~~

Ba khái niệm phải phân biệt:

- **HTTP service interface:** mô tả hợp đồng HTTP, cung cấp API typed cho code Java gọi.
- **HttpServiceProxyFactory:** phân tích annotation/chữ ký method, tạo proxy ở runtime; không phải HTTP transport.
- **Adapter:** cầu nối từ proxy xuống client cụ thể. **RestClientAdapter** dùng RestClient đồng bộ; **WebClientAdapter** dùng WebClient reactive.

Cách tiếp cận này giảm lặp URI, serialization, boilerplate và tập trung khai báo contract. Khi cần xử lý HTTP chi tiết bất thường, vẫn có thể gọi RestClient/WebClient fluent API trực tiếp.

### Phiên bản API

Bài dùng **Java 17+**, tập trung vào **Spring Framework 6.2.x**; ý tưởng và các lời gọi phổ biến còn dùng trong Spring Framework 7.x. Có thể chạy ví dụ với **Spring Boot 3.5.x** (nền Spring 6.2).

- HttpServiceProxyFactory và WebClientAdapter xuất hiện từ Spring 6.0.
- RestClient và RestClientAdapter có từ Spring 6.1.
- Với Spring 6.1+, ưu tiên **HttpServiceProxyFactory.builderFor(adapter)** và **WebClientAdapter.create(webClient)**.
- Ví dụ cũ dùng **HttpServiceProxyFactory.builder(adapter)** hoặc **WebClientAdapter.forClient(webClient)** thuộc API đã deprecate; mã mới tránh dùng.

## 2. Khai báo HTTP interface chính xác

Giả sử hệ thống catalog có:

| HTTP request | Body/response | Nghiệp vụ |
| --- | --- | --- |
| GET /api/books/{id} | JSON Book | Tra một sách |
| GET /api/books?keyword=java | JSON array Book | Tìm sách |
| POST /api/books | JSON CreateBook, trả HTTP 201 và Book | Tạo sách |
| DELETE /api/books/{id} | Không cần body response | Xóa sách |

Các kiểu dữ liệu:

~~~java
public record Book(long id, String title) {}
public record CreateBook(String title) {}
~~~

Interface đồng bộ:

~~~java
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/books",
              accept = MediaType.APPLICATION_JSON_VALUE)
public interface BookService {
    @GetExchange("/{id}")
    Book findById(@PathVariable("id") long id);

    @GetExchange
    List<Book> search(@RequestParam("keyword") String keyword);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Book> create(
        @RequestHeader("X-Request-Id") String requestId,
        @RequestBody CreateBook request);

    @DeleteExchange("/{id}")
    void delete(@PathVariable("id") long id);
}
~~~

Đây là mẫu minh họa hợp đồng. Các top-level **public** type phải được đặt trong các file Java cùng tên, hoặc chuyển thành nested type như ví dụ hoàn chỉnh ở mục 8. API server thực tế quyết định đường dẫn, status và JSON.

Chú ý:
- **@HttpExchange** trên interface khai báo URL prefix dùng chung; annotation trên method như **@GetExchange("/{id}")** bổ sung path và xác định method.
- **@PathVariable("id")** lấy đối số Java chèn vào URI template.
- **@RequestParam("keyword")** thông thường thành query parameter. Với request **application/x-www-form-urlencoded**, request parameters được đưa vào form body.
- **@RequestBody** là dữ liệu Java cần serialize ra request (ví dụ JSON).
- **@RequestHeader** thêm header theo từng lời gọi, thích hợp cho correlation ID hoặc token được truyền theo request.
- **ResponseEntity<Book>** cho phép đọc cả status, headers và body. Chỉ khai báo **Book** khi thực sự chỉ cần body.
- **void** thực hiện request nhưng không trả body. Nếu API trả nội dung cần dùng, đừng bỏ qua bằng kiểu void.
- Các shortcut khác gồm **@PutExchange**, **@PatchExchange**, **@DeleteExchange**.
- **@GetExchange** trong HTTP interface thuộc **org.springframework.web.service.annotation**, khác annotation controller **@GetMapping**.

**Accept** là định dạng phản hồi client mong nhận; **Content-Type** là định dạng request body được gửi đi. Đặt **accept = application/json** không có nghĩa mọi request cũng phải có Content-Type JSON.

Có thể dùng **@HttpExchange** ngay trên method (kèm method/url) nếu cần cách khai báo tổng quát hơn, nhưng annotation theo method thường gọn và dễ hiểu.

### Tên tham số và kiểu generic

Dùng **@PathVariable("id")**, **@RequestParam("keyword")** với tên tường minh giúp tránh phụ thuộc hoàn toàn vào metadata parameter name của compiler. Interface method khai báo **List<Book>** giữ được thông tin kiểu phần tử qua chữ ký phản chiếu; message converter biết giải mã list của Book, khác với dùng raw **List**.

**Đừng xem HTTP interface như REST controller**. Cùng một annotation family có thể được dùng ở phía server trong một số cấu hình Spring, nhưng tạo proxy bằng HttpServiceProxyFactory là công việc ở phía client.

## 3. Dùng HttpServiceProxyFactory với RestClientAdapter

**RestClient** là HTTP client đồng bộ của Spring Framework. Cách dùng khi tạo proxy:

~~~java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.org")
    .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(adapter).build();

BookService books = factory.createClient(BookService.class);

Book book = books.findById(7L);
~~~

**catalog.example.org** chỉ là hostname minh họa. Giả sử server thật có endpoint tương ứng, **findById(7L)** phát GET đến **https://catalog.example.org/api/books/7**, chờ response, decode JSON rồi trả Book. Nếu server lỗi/không tồn tại, lời gọi có thể ném exception.

RestClientAdapter thực thi hợp đồng **HttpExchangeAdapter**, phù hợp với return type đồng bộ:
- **void**.
- **HttpHeaders**, **Book** hoặc một **T** cụ thể.
- **List<Book>** hoặc **ResponseEntity<Book>**, **ResponseEntity<List<Book>>**.
- **ResponseEntity<Void>** nếu cần status và headers nhưng không cần response body.

Một trường hợp thực tế:

~~~java
Book found = books.findById(7);
List<Book> matches = books.search("java");
ResponseEntity<Book> created =
    books.create("req-123", new CreateBook("Spring Cookbook"));

System.out.println(found.title());
System.out.println(created.getStatusCode());
~~~

Đây chỉ là đoạn sử dụng khi đã có API catalog; **stdout phụ thuộc server** nên không khẳng định một chuỗi kết quả cụ thể.

### Chọn RestClientAdapter khi nào?

RestClientAdapter phù hợp với tầng nghiệp vụ xử lý đồng bộ, ứng dụng Spring MVC truyền thống, job/batch tuần tự, command line và tích hợp có số lượng HTTP call kiểm soát được. Thread caller chờ I/O; vì vậy phải cấu hình connection pool, concurrency và timeout phù hợp.

Không khai báo **Mono<Book>** hay **Flux<Book>** làm kiểu trả về rồi bọc interface bằng RestClientAdapter. Nó không cung cấp reactive exchange tương đương WebClient. Nếu cần luồng bất đồng bộ, hãy dùng WebClientAdapter và khai báo interface phản ánh semantics đó.

## 4. Dùng HttpServiceProxyFactory với WebClientAdapter

**WebClient** hỗ trợ I/O non-blocking/reactive. WebClientAdapter thực hiện **ReactorHttpExchangeAdapter**, cho phép HTTP service interface trả về Reactor **Mono** hoặc **Flux**.

Interface reactive tương ứng:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/books",
              accept = MediaType.APPLICATION_JSON_VALUE)
public interface ReactiveBookService {
    @GetExchange("/{id}")
    Mono<Book> findById(@PathVariable("id") long id);

    @GetExchange
    Flux<Book> list();

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Book>> create(@RequestBody CreateBook request);
}
~~~

Tạo client, adapter, factory, proxy:

~~~java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.org")
    .build();

WebClientAdapter adapter = WebClientAdapter.create(webClient);

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(adapter).build();

ReactiveBookService books =
    factory.createClient(ReactiveBookService.class);

Mono<Book> result = books.findById(7L);
~~~

**result** ở đây là publisher mô tả thao tác HTTP. Request được thực thi khi có subscription. Trong Spring WebFlux controller, **return result** để framework subscribe/cancel/quản lý lỗi; không cần **subscribe()** tùy tiện. Chỉ gọi **result.block()** ở ranh giới đồng bộ có kiểm soát (ví dụ main/test), không gọi block() bên trong event-loop.

### Flux, streaming và kiểu trả về

Một HTTP service method có thể khai báo:

~~~java
@GetExchange(url = "/events",
             accept = MediaType.APPLICATION_NDJSON_VALUE)
Flux<Book> streamBooks();
~~~

Method này minh họa trường hợp remote server trả **application/x-ndjson**, mỗi dòng là một JSON record. Flux phát các Book khi decoder nhận đủ record. Nếu server thực tế trả **text/event-stream**, hãy dùng Content-Type phù hợp và có thể dùng **Flux<ServerSentEvent<Book>>** nếu cần id/event/retry metadata.

Không suy ra API là realtime chỉ vì kiểu trả về là Flux. Dữ liệu có đến dần không còn phụ thuộc framing, codec, khả năng flush của server/proxy và subscription. Tránh gọi **collectList()** trên stream vô hạn.

### Có thể dùng return type đồng bộ với WebClientAdapter?

Spring hỗ trợ cả các return type đồng bộ như **Book** hoặc **ResponseEntity<Book>** khi dùng WebClientAdapter, nhưng để trả Book trực tiếp proxy phải chờ response. Vì vậy chọn **Mono/Flux** nếu toàn bộ call chain cần non-blocking.

Không cần cố chia sẻ cùng một Java interface giữa client sync và reactive khi API sử dụng khác nhau. Một cặp interface thể hiện rõ hợp đồng:

~~~text
BookService.findById(id)          -> Book
ReactiveBookService.findById(id)  -> Mono<Book>
~~~

Chúng có thể trỏ đến cùng endpoint nhưng kiểu kết quả phản ánh mô hình xử lý khác nhau.

## 5. Bảng so sánh chọn adapter

| Tiêu chí | RestClientAdapter | WebClientAdapter |
| --- | --- | --- |
| Client được bọc | RestClient | WebClient |
| Loại adapter | HttpExchangeAdapter | ReactorHttpExchangeAdapter |
| Cách dùng điển hình | Đồng bộ (blocking caller) | Reactive, non-blocking |
| Kiểu trả về tự nhiên | Book, List<Book>, ResponseEntity<Book>, void | Mono<Book>, Flux<Book>, Mono<ResponseEntity<Book>> |
| Có dùng kiểu đồng bộ được? | Có | Có, nhưng cần chờ response |
| Stream dài hạn | Không phải mục tiêu chính | Phù hợp hơn với Flux |
| Error/status policy | RestClient Builder/request factory | WebClient Builder/connector |
| Tình huống phù hợp | MVC, batch và tầng tích hợp đồng bộ | WebFlux, nhiều I/O đồng thời, stream |

**HttpServiceProxyFactory không tự biến một method đồng bộ thành reactive.** Adapter và return type mới xác định cách request vận hành. Việc đổi adapter mà giữ nguyên toàn bộ interface có thể sai với kiểu phản hồi mong muốn.

## 6. Đăng ký proxy làm bean trong Spring Boot

Đặt cấu hình client/proxy tại **@Configuration**, rồi inject interface vào service. Cách này hỗ trợ dùng lại HTTP client, cấu hình theo môi trường và kiểm thử dễ dàng. Trong ứng dụng Spring Boot có cả **RestClient.Builder** và **WebClient.Builder**:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
public class RemoteClientConfig {

    @Bean
    BookService bookService(RestClient.Builder builder) {
        RestClient http = builder
            .baseUrl("https://catalog.example.org")
            .build();
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(http))
            .build()
            .createClient(BookService.class);
    }

    @Bean
    ReactiveBookService reactiveBookService(WebClient.Builder builder) {
        WebClient http = builder
            .baseUrl("https://catalog.example.org")
            .build();
        return HttpServiceProxyFactory
            .builderFor(WebClientAdapter.create(http))
            .build()
            .createClient(ReactiveBookService.class);
    }
}
~~~

Các interface/record thuộc package tương thích với cấu hình (hoặc có import đúng package). URL trong ví dụ là host minh họa. Cấu hình thực tế nên lấy từ **application.properties** hoặc **@ConfigurationProperties**, ví dụ:

~~~properties
catalog.base-url=https://catalog.example.org
~~~

Với **@Value** hoặc type-safe configuration properties, inject giá trị trên vào bean factory method thay vì hard-code hostname. Nên tạo các client riêng khi host, thông tin xác thực, base URL, timeout hoặc trust policy khác nhau; nếu nhiều interface cùng host và policy, một factory có thể **createClient** nhiều interface.

**Quan trọng:** Spring Boot chỉ tự cung cấp bean WebClient.Builder khi dependency WebFlux phù hợp trên classpath; trong ứng dụng không có WebFlux, cần thêm dependency/client configuration tương ứng. Dùng WebClient để gọi API **không bắt buộc toàn bộ ứng dụng phải là WebFlux server**.

### Những thứ cần cấu hình ở underlying HTTP client

- **baseUrl**, default headers, phương án gắn authorization cho mỗi request.
- Connection pool, TLS, HTTP proxy, timeout kết nối/đọc/response.
- Jackson converters hoặc WebFlux codecs, kích thước buffer và media types.
- Interceptors/filters cho logging có redact dữ liệu nhạy cảm, tracing và metrics.
- HTTP status handler, mapping 404/5xx, retry policy và circuit breaker theo nghiệp vụ.

Những thông số này thuộc **RestClient.Builder**, **WebClient.Builder** hoặc connector/request factory; **HttpServiceProxyFactory** đảm nhiệm việc chuyển interface invocation thành HTTP exchange.

## 7. Return type, xử lý lỗi và một số tùy chỉnh nâng cao

### 7.1 Return type do adapter quyết định

Với RestClientAdapter, các return type thường gặp:

~~~java
void delete(long id);
Book findById(long id);
ResponseEntity<Book> getWithHeaders(long id);
List<Book> findAll();
~~~

Với WebClientAdapter:

~~~java
Mono<Void> deleteReactive(long id);
Mono<Book> findByIdReactive(long id);
Flux<Book> stream();
Mono<ResponseEntity<Book>> getWithHeadersReactive(long id);
~~~

Spring còn hỗ trợ **Mono<ResponseEntity<Flux<T>>>** khi cần status + stream body ở adapter reactive. Khai báo đúng generic type ở phương thức giúp decoder tạo đúng DTO. **Mono<List<Book>>** trả một list khi giải mã xong; **Flux<Book>** phát từng Book. **ResponseEntity** đem lại status và headers, còn DTO thuần chỉ là body.

### 7.2 Mapping lỗi HTTP

Mặc định, RestClient xử lý HTTP status lỗi thành các loại **RestClientException** (ví dụ **RestClientResponseException** với status/body), WebClient thường phát **WebClientResponseException** trong reactive pipeline. Không khẳng định lỗi network, decode JSON và HTTP 4xx/5xx là một loại lỗi duy nhất.

Ví dụ cấu hình handler 404 cho RestClient:

~~~java
RestClient rest = RestClient.builder()
    .baseUrl("https://catalog.example.org")
    .defaultStatusHandler(
        status -> status.value() == 404,
        (request, response) -> {
            throw new IllegalStateException("Không tìm thấy sách");
        })
    .build();
~~~

Ví dụ tương ứng cho WebClient:

~~~java
WebClient web = WebClient.builder()
    .baseUrl("https://catalog.example.org")
    .defaultStatusHandler(
        status -> status.value() == 404,
        response -> Mono.just(
            new IllegalStateException("Không tìm thấy sách")))
    .build();
~~~

Hai đoạn code trên là **fragment cấu hình**, không phải chương trình chạy độc lập; cần import RestClient/WebClient/Mono. RestClient status handler có signature handler đồng bộ nhận request và response; WebClient handler nhận response và trả Publisher chứa Throwable. Không copy nguyên lambda của client này sang client kia.

Lỗi cần thiết kế theo nghiệp vụ: 404 đôi khi được ánh xạ thành Optional/không có dữ liệu, 409 cần xử lý conflict, 429 có thể retry theo Retry-After. Đừng tự động nuốt mọi 4xx để trả DTO null; việc đó có thể che mất lỗi cấu hình hoặc bảo mật.

### 7.3 Timeout, retry và lifecycle

- Đồng bộ: đặt timeout ở HTTP client/request factory. Không để thread chờ không giới hạn khi downstream lỗi.
- Reactive: đặt timeout network trên connector và timeout nghiệp vụ trong Reactor khi cần; lưu ý timeout giữa các phần tử có thể làm hỏng stream hợp lệ.
- **WebClientAdapter** có thể hỗ trợ block timeout cho trường hợp phương thức trả kiểu đồng bộ, nhưng cấu hình ở HTTP client bên dưới thường rõ hơn.
- Retry với POST tạo resource có thể gây tạo trùng; chỉ retry an toàn khi có cơ chế idempotency hoặc hợp đồng rõ.
- Reactive Mono/Flux cần subscription; controller WebFlux nên return publisher. Không gọi **block()** ở event-loop.
- Với stream dài hạn, quản lý cancellation, buffering, error signal, backpressure và khả năng server flush.

### 7.4 Tùy chỉnh resolver cho object tham số

Khi API yêu cầu ba query parameter nhưng Java muốn một object **SearchFilter**, có thể tạo **HttpServiceArgumentResolver**:

~~~java
public record SearchFilter(String owner, String language, String term) {}

public class SearchFilterResolver
        implements HttpServiceArgumentResolver {

    @Override
    public boolean resolve(
            Object argument,
            MethodParameter parameter,
            HttpRequestValues.Builder values) {
        if (!SearchFilter.class.equals(parameter.getParameterType())) {
            return false;
        }

        SearchFilter filter = (SearchFilter) argument;
        values.addRequestParameter("owner", filter.owner());
        values.addRequestParameter("language", filter.language());
        values.addRequestParameter("term", filter.term());
        return true;
    }
}
~~~

Các import còn cần là **org.springframework.core.MethodParameter**, **org.springframework.web.service.invoker.HttpServiceArgumentResolver**, **org.springframework.web.service.invoker.HttpRequestValues**. Ví dụ resolver này là fragment tách từ hệ thống có interface; nó cho thấy cách ánh xạ một object thành query, không phải một main độc lập.

Gắn resolver:

~~~java
HttpServiceProxyFactory factory = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .customArgumentResolver(new SearchFilterResolver())
    .build();
~~~

Spring gọi resolver tùy biến trước resolver mặc định; nếu không hỗ trợ kiểu tham số, phải trả **false** để các resolver khác tiếp tục. Builder còn cho phép **conversionService(...)** để chuyển giá trị thành String và **embeddedValueResolver(...)** cho giá trị nhúng trong metadata của HTTP service.

### 7.5 Header, URI và multipart

Interface còn hỗ trợ **@CookieValue**, **@RequestPart**, tham số **URI** (ghi đè URL được khai báo) và một số argument khác. Ví dụ multipart request:

~~~java
@PostExchange(
    url = "/files",
    contentType = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<Void> upload(
    @RequestPart("description") String description,
    @RequestPart("file") Resource file);
~~~

Import **org.springframework.core.io.Resource**. Phía gọi truyền **FileSystemResource** của tệp có thật; tên part và media type phải đúng hợp đồng server. Multipart upload không tự động nghĩa response cũng là multipart: nếu server trả JSON, khai báo DTO response JSON như bình thường.

## 8. Ví dụ hoàn chỉnh Java 17: một API, hai adapter

Demo dưới đây khởi chạy HTTP server tối giản trên loopback bằng JDK, sau đó gọi cùng endpoint thông qua **RestClientAdapter** và **WebClientAdapter**. Không cần server internet; Maven tải dependency Spring cần thiết khi chạy lần đầu.

Cấu trúc:

~~~text
http-interface-demo/
  pom.xml
  src/main/java/demo/HttpInterfaceDemo.java
~~~

**pom.xml** dùng Spring Boot 3.5.0 để quản lý phiên bản Spring 6.2.x:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>http-interface-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/HttpInterfaceDemo.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpServer;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import reactor.core.publisher.Mono;

public class HttpInterfaceDemo {

    public record Book(long id, String title) {}

    @HttpExchange(url = "/api/books",
                  accept = MediaType.APPLICATION_JSON_VALUE)
    public interface BlockingBooks {
        @GetExchange("/{id}")
        Book find(@PathVariable("id") long id);
    }

    @HttpExchange(url = "/api/books",
                  accept = MediaType.APPLICATION_JSON_VALUE)
    public interface ReactiveBooks {
        @GetExchange("/{id}")
        Mono<Book> find(@PathVariable("id") long id);
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/books/1", HttpInterfaceDemo::respond);
        server.start();

        try {
            String baseUrl =
                "http://127.0.0.1:" + server.getAddress().getPort();

            RestClient rest = RestClient.builder()
                .baseUrl(baseUrl)
                .build();

            BlockingBooks blocking = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(rest))
                .build()
                .createClient(BlockingBooks.class);

            WebClient web = WebClient.builder()
                .baseUrl(baseUrl)
                .build();

            ReactiveBooks reactive = HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(web))
                .build()
                .createClient(ReactiveBooks.class);

            System.out.println("RestClient -> " +
                blocking.find(1).title());
            System.out.println("WebClient -> " +
                reactive.find(1).block().title());
        } finally {
            server.stop(0);
        }
    }

    private static void respond(com.sun.net.httpserver.HttpExchange exchange)
            throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            exchange.sendResponseHeaders(405, -1);
            exchange.close();
            return;
        }

        byte[] body = "{\"id\":1,\"title\":\"Spring\"}"
            .getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "application/json");
        exchange.sendResponseHeaders(200, body.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
    }
}
~~~

**Chạy** trong thư mục **http-interface-demo**, yêu cầu JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.HttpInterfaceDemo
~~~

**Kết quả mà chương trình in ra stdout** khi chạy thành công:

~~~text
RestClient -> Spring
WebClient -> Spring
~~~

Diễn giải:
1. JDK HttpServer tạo GET /api/books/1 và trả **{"id":1,"title":"Spring"}**. Cổng ngẫu nhiên được chọn khi bind port **0**.
2. RestClient và WebClient có cùng base URL nhưng dùng adapter và interface riêng.
3. Lệnh **blocking.find(1)** phát request đồng bộ, trả Book.
4. **reactive.find(1)** trả Mono; **block()** chỉ được dùng để minh họa ở main đồng bộ, khiến publisher subscribe và đọc JSON.
5. **server.stop(0)** trong finally kết thúc server, kể cả khi lời gọi HTTP thất bại.

Không có đầu ra HTTP cố định nào khác cần đoán. Khi chạy bằng Maven có thể xuất hiện log/cảnh báo của công cụ tùy môi trường; hai dòng trên là các dòng do chính chương trình **System.out.println** phát ra.

## 9. Kiểm thử hợp đồng và lỗi thường gặp

### Hai tầng kiểm thử nên tách

**Kiểm thử proxy + HTTP contract**: dùng server giả như WireMock, MockWebServer hoặc JDK HttpServer để kiểm tra request method, path, query, header, request JSON, status và deserialize response. Ví dụ Java main ở mục 8 kiểm thử một GET thành công của cả hai adapter.

**Kiểm thử business logic**: mock chính Java interface **BookService**/**ReactiveBookService** trong unit test của service, không nhất thiết tạo HTTP proxy khi test chỉ kiểm tra điều phối. Hai loại test bổ sung nhau.

Các tình huống thêm cho contract tests: server trả 404/500, body sai schema, content type khác dự kiến, token thiếu, server chậm, hủy subscription và retry thao tác có side effect.

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy builder(adapter), forClient(...) | Lẫn ví dụ Spring 6.0 và 6.1+/6.2 | Dùng builderFor và create tương ứng với phiên bản |
| Mono/Flux không hỗ trợ | Interface reactive đi với RestClientAdapter | Dùng WebClientAdapter |
| Treo hoặc lỗi block() trong handler WebFlux | Phương thức trả đồng bộ hoặc block trên event-loop | Giữ pipeline Mono/Flux và return publisher |
| 404 dù host đúng | baseUrl và @HttpExchange/@GetExchange ghép sai path | Kiểm tra đường dẫn thực, path variables |
| Không resolve path variable | Tên tham số không trùng placeholder | Ghi rõ @PathVariable("id") |
| Lỗi JSON / ClassCastException | Kiểu return không khớp JSON, dùng raw types | Khai báo DTO/generic chính xác |
| Flux không nhận dữ liệu | Chưa subscribe, server không flush, sai media type | Xác minh NDJSON/SSE, subscriber và flush |
| 401 hoặc token bị log lộ | Auth header sai cách hoặc logging không redact | Áp dụng auth policy đúng, ẩn token khỏi log |
| POST bị nhân đôi sau retry | Không có idempotency key | Thiết kế retry an toàn |
| HTTP 4xx/5xx khó xử lý | Chưa có status handler | Cấu hình ở RestClient/WebClient |
| Khó giải thích timeout | Timeout chưa đặt ở HTTP connector | Đặt rõ connect/read/response timeout |

**Một số giới hạn cần nhớ:** HTTP interface không tự động xử lý mọi biến thể protocol. Những request đặc biệt có thể cần **customArgumentResolver** hoặc đi trực tiếp vào fluent client API. **RequestEntity** thường không được hỗ trợ như một tham số HTTP service method vì đã mang toàn bộ HTTP request; thay bằng các tham số annotation cụ thể.

## 10. Checklist áp dụng vào dự án

1. Viết contract Java interface với đúng method, URL, tham số, request/response type.
2. Chọn RestClientAdapter nếu caller đồng bộ, WebClientAdapter nếu kết quả cần Mono/Flux và ứng dụng xử lý reactive.
3. Tạo RestClient/WebClient có base URL, auth, timeout, converter/codec và error policy phù hợp.
4. Tạo proxy bằng **HttpServiceProxyFactory.builderFor(adapter).build().createClient(Interface.class)**.
5. Đăng ký interface dưới dạng bean và inject nơi sử dụng.
6. Xác nhận HTTP thực tế qua contract test, không chỉ compile Java.
7. Với reactive, giữ subscription, hủy, retry và backpressure đúng ngữ cảnh. Tránh block trên event-loop.

### Câu hỏi ôn tập

- Vì sao **@HttpExchange** interface vẫn cần **HttpServiceProxyFactory** và **adapter**?
- Có thể đổi RestClientAdapter sang WebClientAdapter mà giữ nguyên interface **Mono<Book>** hay không?
- Khi nào dùng **Book**, **ResponseEntity<Book>**, **Mono<Book>**, **Flux<Book>**?
- Nếu remote API trả JSON array, vì sao **List<Book>** tốt hơn raw **List**?
- Authentication, timeout, status handler nên được đặt ở factory hay underlying client?
- Khi một HTTP service method nhận **SearchFilter** tùy biến, dùng annotation có sẵn hay **HttpServiceArgumentResolver**?

## Tài liệu chính thức

- [Spring Framework 6.2 – REST Clients, HTTP Interface](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html)
- [Spring Framework – tài liệu REST Clients hiện hành](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [HttpServiceProxyFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html)
- [RestClientAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/support/RestClientAdapter.html)
- [WebClientAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/client/support/WebClientAdapter.html)
