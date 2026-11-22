# @HttpExchange và khai báo hợp đồng HTTP bằng interface

## 1. Mục tiêu và bối cảnh

Khi ứng dụng Java gọi một REST API khác, mã gọi thường phải lặp lại URL, HTTP method, path variable, query parameter, header, request body và kiểu response. **HTTP Service Client** của Spring Framework cho phép diễn tả các thông tin đó thành **một interface Java có annotation**, sau đó Spring tạo proxy thực hiện HTTP request qua client được cấu hình. Cơ chế này có từ Spring Framework 6.0; trong Spring Framework 6.1+ có thể dùng **RestClient**, còn **WebClient** hỗ trợ hướng reactive.

Sau bài này, bạn có thể:
- Định nghĩa hợp đồng HTTP rõ ràng bằng @HttpExchange, @GetExchange, @PostExchange, @PutExchange, @PatchExchange và @DeleteExchange.
- Truyền đúng path variable, query parameter, header và JSON body; chọn return type phù hợp.
- Dùng HttpServiceProxyFactory tạo proxy dựa trên RestClientAdapter hoặc WebClientAdapter.
- Hiểu luồng gọi HTTP, xử lý status/error, timeout, auth và các giới hạn của hợp đồng dạng interface.
- Chạy được ví dụ Java 17 + Spring Boot 3.3.x gọi một HTTP server cục bộ, không cần server bên ngoài.

**Ý tưởng:** interface định nghĩa “ứng dụng này cần gọi endpoint nào và trao đổi dữ liệu gì”; RestClient/WebClient chịu trách nhiệm **thực thi request thật**. Interface và proxy không tự triển khai business logic ở remote server.

## 2. Từ lời gọi thủ công đến hợp đồng interface

Lời gọi RestClient trực tiếp (ví dụ tích hợp, giả định BookDto tồn tại):

~~~java
BookDto book = restClient.get()
    .uri("/api/books/{id}", 42L)
    .header("Accept-Language", "vi")
    .retrieve()
    .body(BookDto.class);
~~~

Khi các lời gọi tăng lên, việc lặp lại chuỗi đường dẫn, tên header và cách giải mã dễ gây sai lệch. Một interface tập trung contract:

~~~java
@HttpExchange(url = "/api/books", accept = MediaType.APPLICATION_JSON_VALUE)
public interface BookHttpClient {

    @GetExchange("/{id}")
    BookDto findById(@PathVariable("id") long id,
                     @RequestHeader("Accept-Language") String language);

    @GetExchange
    List<BookDto> search(@RequestParam("q") String keyword);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    BookDto create(@RequestBody CreateBookRequest body);
}
~~~

Các kiểu BookDto và CreateBookRequest thuộc ứng dụng. Đây là **interface contract**, chưa phải client có thể gọi: phải tạo RestClient/WebClient, adapter và proxy ở phần sau. So với mã thủ công, caller chỉ cần gọi:

~~~java
BookDto book = bookHttpClient.findById(42L, "vi");
~~~

Proxy đọc annotation và đối số của method để dựng HTTP request. Hợp đồng interface mang lại type checking tại thời điểm biên dịch cho chữ ký Java, nhưng **không đảm bảo remote endpoint thật sự tồn tại hoặc response luôn khớp DTO**. Những điều đó chỉ được xác minh bằng kiểm thử tích hợp hoặc khi chạy.

### Phân biệt các khái niệm

| Thành phần | Trách nhiệm |
| --- | --- |
| @HttpExchange / @GetExchange / @PostExchange | Khai báo HTTP method, URL, media type và mapping tham số |
| Interface Java | API phía client nhìn thấy, kiểu input/output và tên method |
| HttpServiceProxyFactory | Tạo đối tượng proxy triển khai interface ở runtime |
| RestClientAdapter | Nối proxy với **RestClient** đồng bộ |
| WebClientAdapter | Nối proxy với **WebClient** hỗ trợ reactive |
| RestClient / WebClient | Gửi request, encode/decode dữ liệu, xử lý transport, status và filters/interceptors |
| Remote server | Thực thi logic, kiểm tra quyền và trả response |

Không nhầm @HttpExchange với HTTP server do chính interface này tự khởi chạy. Spring MVC/WebFlux cũng có thể dùng interface @HttpExchange trên một @Controller triển khai contract, nhưng đó là **một cơ chế ánh xạ server khác**, không biến client proxy thành controller.

## 3. Annotation và quy tắc tạo URL

### 3.1. @HttpExchange và shortcut annotation

@HttpExchange dùng trên **type** để đặt phần cấu hình dùng chung; dùng trên **method** để khai báo một endpoint cụ thể. Thuộc tính tiêu biểu:
- **url** hoặc alias **value**: URI template hoặc path, ví dụ "/api/books/{id}".
- **method**: HTTP method (GET, POST, PUT, PATCH, DELETE, ...).
- **accept**: giá trị Accept mà client mong nhận.
- **contentType**: Content-Type của request body được gửi đi.

Các annotation chuyên biệt giúp dễ đọc hơn:

| Annotation | Method gửi đi | Ví dụ mục đích |
| --- | --- | --- |
| @GetExchange | GET | Tìm một tài nguyên, truy vấn danh sách |
| @PostExchange | POST | Tạo tài nguyên hoặc thực hiện command |
| @PutExchange | PUT | Thay thế trạng thái tài nguyên |
| @PatchExchange | PATCH | Cập nhật từng phần theo contract |
| @DeleteExchange | DELETE | Xóa tài nguyên |

Ví dụ sau minh họa vài dạng chữ ký; các kiểu request/response do ứng dụng định nghĩa:

~~~java
@HttpExchange(url = "/api/books", accept = MediaType.APPLICATION_JSON_VALUE)
interface BookClient {
    @GetExchange("/{id}")
    BookDto get(@PathVariable("id") long id);

    @PutExchange(url = "/{id}", contentType = MediaType.APPLICATION_JSON_VALUE)
    BookDto replace(@PathVariable("id") long id,
                    @RequestBody ReplaceBookRequest body);

    @PatchExchange(url = "/{id}", contentType = MediaType.APPLICATION_JSON_VALUE)
    BookDto patch(@PathVariable("id") long id,
                  @RequestBody PatchBookRequest body);

    @DeleteExchange("/{id}")
    void delete(@PathVariable("id") long id);
}
~~~

Các path trên tương đối với baseUrl của HTTP client. Chẳng hạn RestClient có baseUrl là "https://catalog.example" và interface khai báo "/api/books": GET "/{id}" với id=42 gửi GET tới "https://catalog.example/api/books/42". **Không tự cộng URL bằng string trong mã nghiệp vụ** khi đã có URI template và resolver.

Một method cũng có thể dùng @HttpExchange(method = "OPTIONS", url = "/api/books") nếu cần method không có shortcut. Các giá trị accept/contentType trên method có thể tinh chỉnh hoặc ghi đè cấu hình chung. Với request không có body, đừng đặt Content-Type chỉ vì response là JSON: Content-Type mô tả nội dung **request**, còn Accept mô tả response muốn nhận.

### 3.2. Truyền đối số

| Kiểu tham số | Tác dụng | Ví dụ |
| --- | --- | --- |
| @PathVariable("id") | Thay "{id}" trong URI template | /books/42 |
| @RequestParam("page") | Query parameter hoặc form parameter tùy Content-Type | ?page=2 |
| @RequestHeader("Authorization") | Thêm header | Bearer token |
| @RequestBody | Encode đối tượng thành body | JSON khi converter/encoder hỗ trợ |
| @CookieValue | Thêm cookie | locale=vi |
| @RequestPart | Một phần của multipart request | File hoặc metadata |
| URI | Cho phép truyền URI động, thay annotation URL | Endpoint tính ở runtime |
| HttpMethod | Cho phép chọn HTTP method ở runtime | GET/HEAD theo caller |

Ví dụ:

~~~java
@GetExchange("/search")
List<BookDto> search(
    @RequestParam("keyword") String keyword,
    @RequestParam("page") int page,
    @RequestHeader("X-Correlation-Id") String correlationId);
~~~

Một lời gọi search("spring web", 2, "trace-9") tạo request có query được encode thành tham số keyword, page và header tương ứng. **Không tự encode string query trước khi đưa vào @RequestParam** nếu URI builder/client đã làm công việc đó; encode hai lần gây sai dữ liệu.

Tham số tùy chọn phải được khai báo phù hợp với cơ chế Spring hỗ trợ, ví dụ @RequestParam(required = false) hoặc Optional<T> khi resolver chấp nhận. Đối với giá trị null, đừng mặc định nghĩ Spring sẽ tự loại bỏ tùy ý: resolver có quy tắc về required/optional, và một tham số bắt buộc null có thể gây lỗi.

**@RequestBody trên client** hướng dẫn serialize body của HTTP request; nó không tự kiểm tra ràng buộc nghiệp vụ ở phía server. Việc validation, Content-Type và JSON mapping phải thống nhất với remote API.

## 4. Tạo proxy từ RestClient hoặc WebClient

### 4.1. RestClient: lời gọi đồng bộ

Spring Framework 6.1+:

~~~java
RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example")
    .defaultHeader("Accept", "application/json")
    .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);

HttpServiceProxyFactory factory = HttpServiceProxyFactory
    .builderFor(adapter)
    .build();

BookHttpClient books = factory.createClient(BookHttpClient.class);
BookDto book = books.findById(42L, "vi");
~~~

Đây là đoạn tích hợp: BookHttpClient, BookDto phải có định nghĩa tương ứng. **Gọi books.findById(...) sẽ thực hiện HTTP request đồng bộ trên thread gọi**. RestClient nên được tạo/cấu hình một lần và sử dụng lại qua proxy, ví dụ đăng ký dưới dạng Spring bean. Không tạo client/factory mới cho từng request nghiệp vụ nếu không có lý do rõ ràng.

Ví dụ cấu hình Spring @Configuration sử dụng interface BookHttpClient của ứng dụng:

~~~java
@Configuration
class CatalogClientConfig {

    @Bean
    BookHttpClient bookHttpClient(RestClient.Builder builder) {
        RestClient client = builder
            .baseUrl("https://catalog.example")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(client))
            .build()
            .createClient(BookHttpClient.class);
    }
}
~~~

RestClient.Builder có thể được Spring Boot cung cấp khi có cấu hình/phụ thuộc phù hợp. Nếu ứng dụng không dùng Spring Boot, có thể gọi RestClient.builder() trực tiếp. Trong Spring Boot 3.3, **khai báo interface có annotation không mặc nhiên biến nó thành bean**: bạn vẫn cần tạo proxy hoặc một cơ chế đăng ký được cấu hình riêng.

### 4.2. WebClient: kiểu reactive

Nếu ứng dụng dùng Reactor và cần non-blocking I/O, tạo WebClientAdapter:

~~~java
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example")
    .build();

HttpServiceProxyFactory factory = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build();

ReactiveBookClient books = factory.createClient(ReactiveBookClient.class);
Mono<BookDto> response = books.findById(42L);
~~~

Interface tương ứng:

~~~java
@HttpExchange("/api/books")
interface ReactiveBookClient {
    @GetExchange("/{id}")
    Mono<BookDto> findById(@PathVariable("id") long id);

    @GetExchange
    Flux<BookDto> streamBooks();
}
~~~

Đây là các đoạn tích hợp minh họa: BookDto và các biến thuộc ứng dụng; import cần thiết nằm trong org.springframework.web.reactive.function.client.* và reactor.core.publisher.*.

Với WebClient, Mono/Flux biểu diễn pipeline reactive; HTTP request thường được thực hiện **khi có subscriber**. Trong controller WebFlux, nên trả Mono/Flux cho framework thay vì gọi block() trên event-loop. Flux chỉ phù hợp khi API/protocol và decoder thực sự hỗ trợ luồng phần tử (ví dụ NDJSON hoặc SSE phù hợp); không mặc định rằng mọi endpoint trả JSON đều streaming.

**Chọn return type phải phù hợp với adapter.** RestClientAdapter dành cho kết quả synchronous như BookDto, ResponseEntity<BookDto>, HttpHeaders hoặc void; không dùng return type Mono/Flux với adapter chỉ hỗ trợ synchronous. WebClientAdapter hỗ trợ các kiểu reactive như Mono<T>, Flux<T> và các biến thể ResponseEntity, đồng thời có thể xử lý một số kiểu đồng bộ theo adapter, nhưng gọi đồng bộ trên reactive stack có thể gây blocking không mong muốn.

## 5. Chọn kiểu trả về theo contract

| Return type | Khi sử dụng |
| --- | --- |
| BookDto | Chỉ cần body đã decode; thích hợp client đồng bộ |
| List<BookDto> | Endpoint trả một JSON array và decoder hỗ trợ generic |
| ResponseEntity<BookDto> | Cần status, headers và body |
| ResponseEntity<Void> | Cần status/headers của response không có body |
| HttpHeaders | Chỉ cần header |
| void | Không dùng response body |
| Mono<BookDto> | Một kết quả bất đồng bộ trên WebClientAdapter |
| Flux<BookDto> | Luồng phần tử khi server và codec hỗ trợ |
| Mono<ResponseEntity<BookDto>> | Phản hồi reactive có status, headers và body |

Ví dụ chấp nhận 204 No Content từ DELETE:

~~~java
@DeleteExchange("/{id}")
ResponseEntity<Void> delete(@PathVariable("id") long id);
~~~

Caller có thể kiểm tra status. Tuy nhiên với status 4xx/5xx, **client mặc định phát exception**, vì vậy đừng nghĩ ResponseEntity sẽ tự động trả về mọi mã lỗi. Muốn xử lý error status theo contract phải cấu hình underlying RestClient/WebClient.

Với collection hoặc generic kiểu List<BookDto>, proxy lấy được generic return type từ chữ ký interface. Nếu gọi thủ công bằng client fluent, bạn có thể cần ParameterizedTypeReference ở những chỗ generic không thể suy ra từ Class. Một DTO record/class cần Jackson hoặc codec tương thích để mapping JSON. Không thể đảm bảo mọi trường hợp dữ liệu lạ, thiếu field hoặc sai kiểu đều được deserialize thành công chỉ vì interface biên dịch.

## 6. Demo Java 17 chạy được: GET, POST, path, query, header và JSON

Ví dụ tự dựng HTTP server nhỏ ngay trong JVM, nên có thể chạy offline đối với API đích sau khi Maven đã tải dependency. Dùng **Java 17+**, **Maven** và **Spring Boot 3.3.13** (bao gồm Spring Framework 6.1.x). Với dự án đang phát triển mới, chọn phiên bản Spring Boot còn được hỗ trợ theo chính sách của đội ngũ; version này được ghim chỉ để minh họa API Spring 6.1.

Cấu trúc:

~~~text
http-exchange-demo/
├── pom.xml
└── src/main/java/demo/HttpExchangeDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>http-exchange-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/HttpExchangeDemo.java**:

~~~java
package demo;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public class HttpExchangeDemo {

    public record Item(long id, String name) {}
    public record NewItem(String name) {}

    @HttpExchange(url = "/api/items", accept = MediaType.APPLICATION_JSON_VALUE)
    public interface ItemHttpClient {

        @GetExchange("/{id}")
        Item findById(@PathVariable("id") long id,
                      @RequestParam("lang") String lang);

        @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
        Item create(@RequestBody NewItem body,
                    @RequestHeader("X-Request-Id") String requestId);
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger received = new AtomicInteger();
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/api/items", exchange -> {
            received.incrementAndGet();
            String method = exchange.getRequestMethod();
            String path = exchange.getRequestURI().getPath();
            String query = exchange.getRequestURI().getRawQuery();
            String json;
            int status;

            if ("GET".equals(method)
                    && "/api/items/42".equals(path)
                    && "lang=vi".equals(query)) {
                status = 200;
                json = "{\"id\":42,\"name\":\"Notebook\"}";
            } else if ("POST".equals(method)
                    && "/api/items".equals(path)
                    && "op-001".equals(
                        exchange.getRequestHeaders().getFirst("X-Request-Id"))
                    && !new String(exchange.getRequestBody().readAllBytes(),
                                  StandardCharsets.UTF_8).isBlank()) {
                status = 201;
                json = "{\"id\":99,\"name\":\"Notebook\"}";
            } else {
                status = 404;
                json = "{\"error\":\"Not found\"}";
            }

            byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();

        try {
            RestClient restClient = RestClient.builder()
                .baseUrl("http://127.0.0.1:" + server.getAddress().getPort())
                .build();

            ItemHttpClient api = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build()
                .createClient(ItemHttpClient.class);

            Item found = api.findById(42L, "vi");
            Item created = api.create(new NewItem("Notebook"), "op-001");

            System.out.println("GET: " + found);
            System.out.println("POST: " + created);
            System.out.println("HTTP requests: " + received.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q compile
mvn -q exec:java -Dexec.mainClass=demo.HttpExchangeDemo
~~~

**Các dòng stdout do chương trình in:**

~~~text
GET: Item[id=42, name=Notebook]
POST: Item[id=99, name=Notebook]
HTTP requests: 2
~~~

Maven hoặc thư viện có thể xuất thêm log tùy môi trường. Bài demo đã mô tả tường minh hai response của HTTP server cục bộ để kết quả nghiệp vụ xác định. Cổng được hệ điều hành cấp động để tránh xung đột cổng. Không có Spring Boot application context trong ví dụ: đây là **Spring HTTP client chạy từ main Java**. Request đầu dùng URI template /api/items/{id}, query param lang=vi; request sau gửi POST JSON body và X-Request-Id. Proxy dùng RestClientAdapter và Jackson (qua starter-web) để encode/decode record.

Một điểm cần lưu ý: trong demo, header X-Request-Id **chỉ là dấu hiệu cho phép server demo nhận request**; nó chưa tạo khả năng chống trùng POST ở server thực. Muốn chống trùng tác dụng phụ phải triển khai idempotency contract với lưu trạng thái và kiểm soát đồng thời, không chỉ gửi header.

### Quan sát luồng thực thi

~~~mermaid
sequenceDiagram
    participant App as Java caller
    participant Proxy as ItemHttpClient proxy
    participant Client as RestClientAdapter + RestClient
    participant Server as HTTP Server
    App->>Proxy: findById(42, "vi")
    Proxy->>Client: GET /api/items/42?lang=vi
    Client->>Server: HTTP GET
    Server-->>Client: 200 + JSON Item
    Client-->>Proxy: decode Item
    Proxy-->>App: Item(42, "Notebook")
    App->>Proxy: create(NewItem, "op-001")
    Proxy->>Client: POST /api/items + JSON + header
    Client->>Server: HTTP POST
    Server-->>Client: 201 + JSON Item
    Client-->>App: Item(99, "Notebook")
~~~

Phần **Proxy → Client** ở sơ đồ là lời gọi nội bộ cùng JVM; chỉ mũi tên **Client → Server** đi qua HTTP. Annotation không phải code chạy ở server; server chỉ nhìn thấy HTTP request thông thường.

## 7. Lỗi, status, timeout và bảo mật

### 7.1. Không che mất status lỗi

Khi dùng RestClientAdapter, xử lý status tuân theo **RestClient**. Mặc định 4xx/5xx thường dẫn đến RestClientResponseException hoặc subclass tương ứng (chẳng hạn HttpClientErrorException). Với WebClientAdapter, WebClient có WebClientResponseException trên lỗi HTTP (theo cơ chế mặc định). Các lỗi mạng/timeout và lỗi JSON mapping có nhóm exception khác.

Chủ động cấu hình handler cho RestClient nếu muốn ánh xạ status thành lỗi nghiệp vụ. Ví dụ **snippet tích hợp**:

~~~java
RestClient client = RestClient.builder()
    .baseUrl("https://catalog.example")
    .defaultStatusHandler(
        status -> status.value() == 404,
        (request, response) -> {
            throw new CatalogItemNotFoundException(request.getURI().toString());
        })
    .build();
~~~

CatalogItemNotFoundException là custom runtime exception của ứng dụng. Đoạn này không phải chương trình độc lập. Với WebClient, có thể dùng WebClient.Builder.defaultStatusHandler(...). Quan trọng là cấu hình ở underlying client được proxy sử dụng; interface @HttpExchange **không tự động có cơ chế retry, fallback hoặc status mapping riêng**.

### 7.2. Những trách nhiệm vận hành cần cấu hình

- **Timeout:** dùng timeout của transport/HTTP client phù hợp, đồng thời cân đối thời gian tối đa của nghiệp vụ. Tránh request vô hạn trên đường gọi đồng bộ.
- **Retry:** chỉ retry lỗi tạm thời và thao tác an toàn để lặp. GET thường là ứng viên, nhưng POST tạo đơn/thanh toán có thể gây tác dụng phụ trùng nếu response mất.
- **Idempotency:** nếu phải retry POST, server cần cơ chế xử lý trùng như Idempotency-Key + unique constraint/transaction/deduplication; header tự nó không đảm bảo exactly-once.
- **Authentication:** cung cấp token/API key qua filter/interceptor, @RequestHeader hoặc cơ chế bảo mật được cấu hình. Không hardcode secret vào interface, source code hay log.
- **Observability:** record HTTP method, host/service, status, độ trễ, correlation ID và số lần retry; che thông tin nhạy cảm.
- **URI/baseUrl:** kiểm soát target host. Tham số URI động lấy từ input không tin cậy phải kiểm tra để tránh gọi sang địa chỉ nội bộ không được phép.
- **Connection pool và giới hạn:** client dùng lại kết nối, giới hạn số request đồng thời, timeout và retry budget theo tải thực tế.
- **Serialization:** phải có converter/codec phù hợp (Jackson cho JSON thường gặp), cấu hình naming/date formats thống nhất với server.

Không đưa retry vào mọi lời gọi của interface chỉ vì nhìn thấy cùng một annotation: retry policy phụ thuộc phương thức và hợp đồng nghiệp vụ.

## 8. Thiết kế interface theo API thực tế

Một HTTP interface tốt thường đại diện cho một **remote service hoặc nhóm endpoint liên quan** với tên method thể hiện kết quả rõ ràng. Đặt baseUrl/host trong cấu hình, giữ path và contract trong interface; DTO thể hiện wire format, tách khỏi entity JPA và model nội bộ khi vòng đời thay đổi độc lập.

Ví dụ tổ chức:

~~~text
client/catalog/
├── CatalogHttpClient.java   # @HttpExchange contract
├── CatalogClientConfig.java # proxy, baseUrl, auth, timeout
├── dto/
│   ├── BookDto.java
│   └── CreateBookRequest.java
└── CatalogFacade.java       # nghiệp vụ gọi remote, error mapping
~~~

Mã gọi trong CatalogFacade phụ thuộc **CatalogHttpClient** nên có thể test bằng fake/mock interface hoặc kiểm thử proxy với mock HTTP server. Chỉ mock interface đơn thuần **không chứng minh URL, HTTP method, query, header và JSON thực tế đúng**; cần integration test kiểm tra request mà client sinh ra.

Các lựa chọn thiết kế:
1. **RestClient + synchronous return type**: phù hợp ứng dụng MVC, batch, service đồng bộ với luồng xử lý blocking đã được cân nhắc.
2. **WebClient + Mono/Flux**: phù hợp luồng WebFlux, tác vụ concurrent hoặc streaming với end-to-end reactive.
3. **RestClient/WebClient fluent trực tiếp**: phù hợp khi cần request động không tự nhiên dưới một interface (method/URI/body quá linh hoạt), hoặc số call ít.
4. **@HttpExchange interface**: phù hợp remote API có contract tương đối ổn định, nhiều endpoint và cần API Java rõ ràng, thống nhất.

Không nên biến mọi URL thành một method generic nhận Object rồi đánh mất type safety. Ngược lại, interface cũng không nên chứa retry logic, cache policy, xử lý database và điều phối nghiệp vụ; để những phần đó ở client configuration/service layer.

## 9. Lỗi phổ biến và cách tự kiểm tra

| Sai sót | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ khai báo interface mà không tạo proxy | Không có bean để inject hoặc không thể gọi thực | Tạo adapter + factory + createClient hoặc cấu hình đăng ký chính thức |
| Dùng Mono<T> với RestClientAdapter | Return type không phù hợp adapter đồng bộ | Chuyển sang WebClientAdapter hoặc dùng T/ResponseEntity<T> |
| Thiếu @PathVariable cho "{id}" | URI template không được mở rộng đúng | Khai báo @PathVariable("id") rõ ràng |
| Trộn Accept với Content-Type | Server có thể giải mã sai body | Accept cho response mong muốn; Content-Type cho request body |
| Dùng @RequestParam cho JSON object body | Body không theo contract | Dùng @RequestBody và converter JSON |
| Tưởng ResponseEntity<T> nhận mọi 404/500 | Client ném exception khi gặp lỗi | Cấu hình status handling theo hợp đồng |
| Bật retry tự động cho POST ghi | Có thể tạo nhiều đơn hoặc giao dịch | Áp dụng idempotency được server thực thi |
| Gọi block() trong reactive request handler | Chặn event loop, gây suy giảm throughput | Trả Mono/Flux |
| Dùng chung DTO entity DB với wire model | Thay schema nội bộ làm vỡ remote contract | Tạo DTO theo phiên bản HTTP API |
| Chỉ viết unit test mock interface | Không phát hiện URI/header/body mapping sai | Test proxy thật với mock HTTP server |
| Coi @HttpExchange là tự tạo remote endpoint | Server không thực sự tồn tại | Phân biệt client proxy với @Controller implementation |

**Checklist kiểm thử tối thiểu:** xác nhận HTTP method và URL; path/query chứa ký tự đặc biệt; headers/auth; serialization và mapping response; 2xx/204; 400/401/404/429/5xx; transport timeout; trường hợp body lỗi schema; request retry khi có/không có idempotency; tạo proxy/bean khi ứng dụng khởi động. Với WebClient, kiểm thử subscriber/cancellation và không block event loop khi thích hợp.

## 10. Kết luận kiến thức

@HttpExchange biến một remote HTTP contract thành **Java interface dễ đọc và dễ dùng**; HttpServiceProxyFactory sinh proxy để thực thi contract trên **RestClient** hoặc **WebClient**. Annotation mô tả request, adapter quyết định cơ chế gọi, DTO mô tả dữ liệu, còn server và client configuration mới quyết định xác thực, xử lý lỗi, timeout, retry và tính an toàn của tác dụng phụ. Vì thế, type-safe interface làm mã gọi gọn và nhất quán nhưng vẫn cần test HTTP thực và hợp đồng nghiệp vụ đáng tin cậy.

## Tài liệu chính thức

- Spring Framework Reference, HTTP Service Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface
- Spring Framework 6.1 API, @HttpExchange: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html
- Spring Framework 6.1 API, HttpServiceProxyFactory: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 API, RestClientAdapter: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/support/RestClientAdapter.html
- Spring Framework Reference, WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
