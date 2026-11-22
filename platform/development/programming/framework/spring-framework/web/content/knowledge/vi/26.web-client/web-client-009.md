# Dùng WebClient trong Spring MVC: chọn vị trí block và tránh chặn event loop

## 1. Bối cảnh: WebClient là reactive, Spring MVC là servlet-based

`WebClient` là HTTP client sử dụng API reactive (`Mono`/`Flux`), thực hiện HTTP I/O theo hướng bất đồng bộ và hỗ trợ non-blocking khi connector phù hợp (thường là Reactor Netty). `Spring MVC` chạy trên Servlet stack; controller đồng bộ thường được gọi bởi thread từ pool của Servlet container (chẳng hạn `http-nio-8080-exec-*` trên Tomcat). Servlet stack cho phép controller gọi API blocking, nhưng thread bị giữ trong suốt lúc chờ.

Vì vậy, dùng WebClient trong MVC **hoàn toàn hợp lệ**. Quyết định quan trọng là: endpoint hiện tại cần trả về một giá trị Java đồng bộ hay có thể trả một publisher cho Spring MVC xử lý bất đồng bộ?

- **Đồng bộ:** nhận `Mono<T>` rồi gọi `block()` **một lần ở ranh giới imperative**, ví dụ một phương thức service đồng bộ được controller MVC gọi trên servlet worker. Cách này dễ phối hợp với code đồng bộ sẵn có nhưng dùng một servlet thread cho mỗi request đang đợi upstream.
- **Bất đồng bộ:** controller MVC trả trực tiếp `Mono<T>`/`Mono<ResponseEntity<T>>`. Spring MVC thích ứng publisher thành cơ chế Servlet async (tương tự `DeferredResult`); request không giữ servlet worker liên tục trong lúc WebClient chờ upstream.
- **Streaming:** MVC có thể thích ứng `Flux` sang kiểu ghi response bất đồng bộ với media type thích hợp, nhưng việc **ghi ra HTTP response ở Servlet stack vẫn là blocking** và cần một `AsyncTaskExecutor` phù hợp. Chỉ thêm `WebClient` không biến toàn bộ ứng dụng MVC thành WebFlux server.

Điều cần tránh nhất là gọi `block()` trên Reactor event-loop (`reactor-http-nio-*`) hoặc scheduler non-blocking. Khi đó bạn có thể gặp `IllegalStateException` hoặc làm nghẽn luồng xử lý I/O. **HTTP client non-blocking không tự bảo đảm mọi phần của pipeline đều non-blocking**: đoạn code của bạn ở `map`, `flatMap` hay callback vẫn có thể chạy trên event-loop.

### Sơ đồ hai mô hình

~~~text
A. MVC đồng bộ
client HTTP --> Servlet worker --> service --> WebClient: Mono<T>
                     |                           |
                     |-- block() chờ ------------|--> Reactor Netty event-loop
                     |                                (đọc/ghi socket, không block)
                     <-- giá trị T ----------------|
                     --> ghi response MVC

B. MVC bất đồng bộ
client HTTP --> Servlet worker --> controller trả Mono<T>
                     |                 |
                     |            MVC đăng ký Servlet async
                 worker rảnh           |
                                      WebClient chạy I/O trên event-loop
                                            |
                                         kết quả T
                                            |
                                 MVC dispatch/ghi response
~~~

`block()` ở luồng servlet **không khiến Reactor Netty thực hiện I/O blocking**; nó chỉ khiến chính servlet thread đứng chờ tín hiệu từ publisher. Đây là khác biệt giữa **blocking caller** và **blocking event-loop**.

## 2. Khi nào được block, khi nào nên trả Mono?

| Tình huống | Khuyến nghị | Lý do |
| --- | --- | --- |
| MVC controller/service có hợp đồng đồng bộ `T get(...)`, dùng JDBC/JPA hoặc code imperative | Có thể `block()` tại điểm kết thúc lời gọi từ servlet worker | Hợp đồng synchronous; ranh giới rõ ràng, dễ xử lý lỗi. |
| MVC controller có thể trả `Mono<T>` | Ưu tiên trả publisher trực tiếp | MVC hỗ trợ Servlet async, tiết kiệm servlet threads đang chờ I/O. |
| Controller WebFlux hoặc callback đang chạy trên Reactor event-loop | **Không gọi `block()`** | Chặn event-loop, Reactor có thể báo `IllegalStateException`. |
| Trong `map`/`doOnNext`/`flatMap` của chuỗi WebClient | Không block trực tiếp | Callback có thể chạy trên non-blocking thread; dùng tổ hợp publisher thay vì nested blocking. |
| Gọi đồng thời nhiều upstream HTTP endpoints | Tạo các `Mono`, dùng `zip`/`flatMap` rồi mới block **nếu thật sự cần** | Tránh đợi tuần tự; tối đa một lần block ở cuối ở caller đồng bộ. |
| Chuỗi reactive bắt buộc gọi thư viện blocking như JDBC cũ | Offload **phần blocking đó** bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` | Giữ event-loop thông thoáng; giới hạn công việc chặn qua scheduler. |
| Ứng dụng MVC thuần synchronous không cần reactive/streaming | Cân nhắc `RestClient` | API imperative rõ ràng, không cần tạo pipeline để block. |

Không có yêu cầu bắt buộc phải chọn cách thứ hai cho mọi ứng dụng: với tải vừa, nhiều thao tác đồng bộ khác và độ phức tạp thấp, việc block trên servlet worker có thể là quyết định thực tế. Nhưng khi upstream có latency cao và concurrency lớn, số servlet threads đang chờ có thể là nút thắt; nên đo throughput, active threads, queue và timeout trước khi chọn kiến trúc.

## 3. Cách dùng WebClient ở ranh giới đồng bộ của MVC

Trong service synchronous, giữ publisher chưa subscribe cho đến lúc cuối, sau đó block một lần:

~~~java
@Service
public class CustomerService {
    private final WebClient client;

    public CustomerService(WebClient.Builder builder) {
        this.client = builder.baseUrl("https://api.example.com").build();
    }

    public CustomerDto find(long id) {
        return client.get()
                .uri("/customers/{id}", id)
                .retrieve()
                .bodyToMono(CustomerDto.class)
                .block(Duration.ofSeconds(3));
    }
}
~~~

Đây là **đoạn minh họa tích hợp**, giả sử `CustomerDto` đã được định nghĩa và upstream tồn tại. `block(Duration)` chờ tối đa khoảng thời gian chỉ định; nếu publisher rỗng, kết quả có thể là `null`. Thường cần phân biệt “không có body” với tài nguyên không tồn tại, ví dụ dùng `switchIfEmpty(Mono.error(...))` và chính sách 404 rõ ràng. `retrieve()` mặc định biến HTTP 4xx/5xx thành `WebClientResponseException` khi publisher được subscribe.

Vị trí hợp lý là **một điểm cuối trong service đồng bộ**, được gọi từ servlet worker. Không gọi `block()` trong lambda của `map`/`flatMap` rồi lại gọi tiếp `block()` ở ngoài; đó là nested blocking.

Ví dụ controller MVC đồng bộ gọi service:

~~~java
@RestController
class CustomerController {
    private final CustomerService customers;

    CustomerController(CustomerService customers) {
        this.customers = customers;
    }

    @GetMapping("/customers/{id}")
    CustomerDto get(@PathVariable long id) {
        return customers.find(id);
    }
}
~~~

Khi request đến `/customers/42`, servlet thread đang xử lý controller đứng đợi upstream; khi hoàn tất, MVC serialize `CustomerDto` ra JSON. Đặt timeout bảo vệ đường chờ và xử lý lỗi nhất quán; nếu upstream chậm hơn số servlet threads đáp ứng được, ứng dụng có thể bị giảm throughput dù WebClient dùng kết nối bất đồng bộ.

### Nhiều HTTP call: dựng các Mono trước, chờ một lần

~~~java
Mono<CustomerDto> customer = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class);

Mono<OrderDto[]> orders = client.get()
        .uri("/customers/42/orders")
        .retrieve()
        .bodyToMono(OrderDto[].class);

CustomerPage result = Mono.zip(
        customer, orders,
        (c, o) -> new CustomerPage(c, List.of(o))
).block(Duration.ofSeconds(5));
~~~

Giả sử `OrderDto` và `CustomerPage` được định nghĩa. Khi `zip` được subscribe, hai request có thể cùng tiến triển; trong khi đó hai lời gọi `customer.block()` rồi `orders.block()` sẽ chờ tuần tự. Nếu một nguồn lỗi/rỗng, `zip` tuân theo semantics Reactor (có thể lỗi hoặc hoàn thành rỗng và hủy nguồn khác); cần chính sách lỗi/rỗng rõ ràng.

**Không block lặp lại trên cùng một `Mono` nguồn nếu chỉ muốn lấy một response**: nhiều lần `block()` thường tạo nhiều subscription và có thể phát sinh nhiều HTTP requests, vì WebClient publisher mặc định là cold.

## 4. Cách dùng không block: MVC trả Mono trực tiếp

MVC có thể trả một `Mono` từ controller; framework đăng ký xử lý bất đồng bộ và hoàn tất HTTP response khi publisher phát kết quả:

~~~java
@RestController
class AsyncCustomerController {
    private final WebClient client;

    AsyncCustomerController(WebClient.Builder builder) {
        this.client = builder.baseUrl("https://api.example.com").build();
    }

    @GetMapping("/async-customers/{id}")
    Mono<CustomerDto> get(@PathVariable long id) {
        return client.get()
                .uri("/customers/{id}", id)
                .retrieve()
                .bodyToMono(CustomerDto.class)
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

Đây vẫn là **Spring MVC controller**, không phải WebFlux handler. Caller không tự gọi `subscribe()`: Spring MVC subscribe thông qua adapter để quản lý lifecycle của response. Phương thức controller trả nhanh, còn servlet request ở trạng thái async đến khi response kết thúc hoặc timeout/hủy.

Spring MVC cũng hỗ trợ reactive trả về nhiều phần tử, nhưng cần chọn media type và cách ghi response phù hợp; chẳng hạn `text/event-stream` để stream hoặc `application/json` thường gom nhiều phần tử thành một collection để serialize. Đừng mặc định `Flux` trên MVC server đồng nghĩa ghi socket non-blocking.

### Ghép request mà không block

~~~java
@GetMapping("/overview/{id}")
Mono<CustomerPage> overview(@PathVariable long id) {
    Mono<CustomerDto> profile = client.get()
            .uri("/customers/{id}", id)
            .retrieve()
            .bodyToMono(CustomerDto.class);

    Mono<OrderDto[]> orders = client.get()
            .uri("/customers/{id}/orders", id)
            .retrieve()
            .bodyToMono(OrderDto[].class);

    return Mono.zip(profile, orders,
            (customer, items) -> new CustomerPage(
                    customer, List.of(items)))
            .timeout(Duration.ofSeconds(5));
}
~~~

`Mono.zip` mô tả song song về mặt subscribe. Với các API phụ thuộc nhau, dùng `flatMap`:

~~~java
Mono<OrderDto[]> result = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .flatMap(customer -> client.get()
                .uri("/customers/{id}/orders", customer.id())
                .retrieve()
                .bodyToMono(OrderDto[].class));
~~~

Hai ví dụ này giả sử các DTO và bean `client` tồn tại; không phải file Java độc lập. Đặc biệt, `flatMap` nhận publisher; không cần `block()` để lấy `customer` bên trong lambda.

## 5. Demo hoàn chỉnh Java 17+: một app MVC, hai endpoint

Demo chạy local mà không phụ thuộc dịch vụ Internet. Ứng dụng Spring Boot 3.x sử dụng **Spring MVC với Tomcat** và WebClient gọi một HTTP server giả lập độc lập chạy trên port ngẫu nhiên của JDK. Có hai API:

- `GET /sync`: Spring MVC controller gọi `block(Duration)` trên servlet thread.
- `GET /async`: controller trả `Mono<Quote>` để Spring MVC xử lý bằng Servlet async.

Mục tiêu là quan sát hai **ranh giới thực thi**; kết quả JSON giống nhau không có nghĩa hai endpoint giữ servlet worker như nhau.

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>mvc-webclient</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` có mặt, Spring Boot 3.x mặc định cấu hình **Spring MVC web application**; starter WebFlux cung cấp WebClient/Reactor Netty client và những thành phần reactive cần thiết. Điều này **không tự thay server MVC bằng Netty/WebFlux**.

### `src/main/java/demo/MvcWebClientApplication.java`

~~~java
package demo;

import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class MvcWebClientApplication {

    public static void main(String[] args) throws Exception {
        HttpServer upstream = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        upstream.createContext("/quote", exchange -> {
            byte[] payload = "{\"text\":\"hello\"}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, payload.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        });
        upstream.start();

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> upstream.stop(0)));

        SpringApplication app = new SpringApplication(
                MvcWebClientApplication.class);
        app.setDefaultProperties(Map.of(
                "demo.upstream-url",
                "http://127.0.0.1:" + upstream.getAddress().getPort()));
        app.run(args);
    }

    @Bean
    WebClient upstreamClient(
            WebClient.Builder builder,
            @Value("${demo.upstream-url}") String upstreamUrl) {
        return builder.baseUrl(upstreamUrl).build();
    }

    public record Quote(String text) {}

    @RestController
    static class GatewayController {
        private final WebClient client;

        GatewayController(WebClient upstreamClient) {
            this.client = upstreamClient;
        }

        @GetMapping("/sync")
        Quote sync() {
            return client.get()
                    .uri("/quote")
                    .retrieve()
                    .bodyToMono(Quote.class)
                    .block(Duration.ofSeconds(3));
        }

        @GetMapping("/async")
        Mono<Quote> async() {
            return client.get()
                    .uri("/quote")
                    .retrieve()
                    .bodyToMono(Quote.class)
                    .timeout(Duration.ofSeconds(3));
        }
    }
}
~~~

Chạy ở thư mục chứa `pom.xml` (JDK 17+, Maven):

~~~bash
mvn spring-boot:run
~~~

Mở terminal khác:

~~~bash
curl -s http://127.0.0.1:8080/sync
curl -s http://127.0.0.1:8080/async
~~~

Cả hai lệnh đều có body dự kiến (mỗi lệnh một dòng):

~~~json
{"text":"hello"}
~~~

Đối với ứng dụng Boot dùng cấu hình cổng mặc định, server MVC lắng nghe ở `8080`; port upstream do OS cấp động. `HttpServer` giả lập upstream xử lý request độc lập nên không tạo vòng lặp tự gọi vào cùng một MVC server. Dừng `mvn spring-boot:run` sẽ đóng ứng dụng, shutdown hook dừng upstream.

Kết quả giống nhau về JSON, nhưng khác cách tiêu thụ servlet worker: `sync` chờ trên thread nhận request; `async` trả `Mono` để MVC đăng ký async processing. Đây là demo hành vi, **không phải benchmark**; cần công cụ đo luồng và tải để đánh giá khả năng mở rộng.

## 6. Vì sao block trong Reactor event-loop nguy hiểm?

Reactor Netty thường dùng một số event-loop threads để xử lý sự kiện socket cho rất nhiều request. Nếu một trong các threads này đang chờ I/O đồng bộ hoặc `Thread.sleep` lâu, các kết nối khác do nó phụ trách cũng bị chậm. Reactor đánh dấu nhiều thread xử lý non-blocking bằng marker `NonBlocking`; gọi `block()`/`blockFirst()`/`blockLast()` ở đó thường bị ngăn bằng exception kiểu:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Tên thread có thể khác theo môi trường. Không nên dựa **chỉ** vào tên thread để quyết định an toàn; `Schedulers.isInNonBlockingThread()` cho biết thread hiện tại có được Reactor đánh dấu không được block.

### Sai: nested block bên trong operator

~~~java
Mono<CustomerPage> bad = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .map(customer -> {
            // Sai: map có thể chạy trên Reactor Netty event-loop.
            OrderDto[] orders = client.get()
                    .uri("/customers/{id}/orders", customer.id())
                    .retrieve()
                    .bodyToMono(OrderDto[].class)
                    .block();
            return new CustomerPage(customer, List.of(orders));
        });
~~~

Khi chạy dưới một subscriber, lambda `map` có thể được gọi trên event-loop của HTTP response, nên `block()` lồng bên trong vi phạm threading model. **Đúng:** dùng `flatMap` để diễn tả HTTP call thứ hai bằng publisher:

~~~java
Mono<CustomerPage> good = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .flatMap(customer -> client.get()
                .uri("/customers/{id}/orders", customer.id())
                .retrieve()
                .bodyToMono(OrderDto[].class)
                .map(orders -> new CustomerPage(
                        customer, List.of(orders))));
~~~

### Sai: gọi thư viện blocking thẳng trong pipeline

~~~java
Mono<String> wrong = client.get()
        .uri("/quote")
        .retrieve()
        .bodyToMono(String.class)
        .map(body -> legacyFileApi.readAndStore(body)); // Chặn thread đang chạy map!
~~~

Nếu code thực sự phải gọi API blocking mà bạn không thể thay thế, bọc **chỉ đoạn blocking** bằng scheduler phù hợp:

~~~java
Mono<String> right = client.get()
        .uri("/quote")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(body -> Mono.fromCallable(
                    () -> legacyFileApi.readAndStore(body))
                .subscribeOn(Schedulers.boundedElastic()));
~~~

Hai đoạn này là code minh họa; cần import `reactor.core.scheduler.Schedulers` và có `legacyFileApi` thực tế. `boundedElastic` dành cho tác vụ blocking có giới hạn; nó không làm API legacy thành non-blocking hay tạo throughput vô hạn. Nếu toàn bộ pipeline chỉ là WebClient reactive, **không cần** `subscribeOn(boundedElastic())` để “biến WebClient thành async”: WebClient đã có cơ chế I/O bất đồng bộ.

Mẹo sai thường gặp: gắn `publishOn(Schedulers.boundedElastic())` vào Mono rồi gọi `block()` ngay bên ngoài **không chuyển chính thread gọi `block()` sang boundedElastic**. Thread caller vẫn bị chặn. Chỉ dùng offload khi tác vụ blocking thực sự nằm **bên trong** publisher mà scheduler điều khiển.

## 7. Timeout, lỗi, hủy request và vòng đời body

### Phân biệt timeout

- `block(Duration.ofSeconds(3))`: timeout thời gian thread caller chờ tín hiệu từ publisher; chỉ thích hợp ở ranh giới synchronous đã cho phép block. Khi timeout, subscription bị hủy.
- `mono.timeout(Duration.ofSeconds(3))`: thiết lập giới hạn ở cấp pipeline reactive; phù hợp cho MVC controller trả `Mono`. Timeout sinh tín hiệu lỗi và hủy upstream.
- Timeout kết nối TCP, nhận response hoặc acquire connection là các cấu hình HTTP client/connection pool; chúng không hoàn toàn đồng nghĩa hai loại timeout trên.
- Spring MVC Servlet async cũng có timeout ở tầng web MVC; cấu hình và ánh xạ lỗi sao cho không có tầng chờ vô hạn, đồng thời cân nhắc timeout tổng thể theo SLA.

Không nên chỉ tăng mọi timeout để xử lý cạn servlet threads. Quan sát thời gian chờ upstream, connection pool, max threads và số request đồng thời. Timeout không phải bảo đảm request được upstream dừng xử lý hoàn toàn: cancel client không nhất thiết rollback hoạt động ở server.

### Xử lý lỗi có chủ đích

`retrieve()` mặc định phát lỗi khi HTTP 4xx hoặc 5xx; kết nối lỗi/không kết nối thường phát `WebClientRequestException`, thời gian chờ có thể tạo loại lỗi khác theo API chọn. Với MVC synchronous, lỗi từ `block()` xuất hiện tại call stack đồng bộ; với MVC reactive return, lỗi là tín hiệu trên publisher và do pipeline/MVC exception infrastructure xử lý. Thiết kế `@ExceptionHandler`, response status và log phù hợp, không bắt toàn bộ lỗi rồi trả 200 với dữ liệu giả.

Ví dụ xử lý upstream 404 theo nghiệp vụ mà không block trong callback:

~~~java
Mono<CustomerDto> customer = client.get()
        .uri("/customers/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                        new CustomerNotFoundException(42)))
        .bodyToMono(CustomerDto.class);
~~~

Đây là code minh họa giả định exception tùy biến tồn tại. `onStatus` phải trả `Mono<? extends Throwable>` phù hợp. Với các nhánh tự xử lý `ClientResponse` bằng `exchangeToMono`, luôn đọc hoặc giải phóng response body đúng cách; tránh giữ lại `ClientResponse` để sử dụng sau khi callback kết thúc. Nếu luồng đã bị cancel giữa chừng, connection pool có thể phải loại socket HTTP/1.1 khỏi pool; đừng khẳng định mọi request bị hủy đều tái sử dụng được kết nối.

### Context và transaction qua thread boundary

Ở MVC synchronous, `ThreadLocal` như MDC, `RequestContextHolder` hoặc transaction có thể tồn tại trên servlet worker. Nhưng callback WebClient chạy ở luồng khác, vì thế **không mặc định** mang đủ servlet context/transaction sang reactive callback. Nếu cần tracing/security context propagation, dùng cơ chế context propagation được Spring/Micrometer hỗ trợ và kiểm thử thực tế. Không giữ JDBC transaction mở chỉ để đợi remote HTTP lâu nếu có thể tách lại ranh giới transaction.

## 8. Lỗi phổ biến và cách sửa

1. **Gọi `block()` trong WebFlux controller hoặc callback WebClient:** chuyển sang trả `Mono`/`Flux` và dùng `flatMap`/`zip`; nếu có thư viện blocking không tránh được, offload riêng phần đó.
2. **Gọi `subscribe()` thủ công trong MVC controller rồi trả kết quả trống:** bỏ subscription thủ công; trả publisher để MVC quản lý request và lỗi. `subscribe()` có thể làm request chạy ngoài lifecycle HTTP và lỗi bị bỏ sót.
3. **Gọi `block()` hai lần trên một publisher HTTP:** tạo hai subscriptions có thể gửi request hai lần. Dựng pipeline rồi subscribe/block ở đúng ranh giới một lần; cache chỉ khi có chủ đích và hiểu trade-off.
4. **Gọi hai upstream lần lượt bằng `block()`:** dựng hai `Mono` trước, kết hợp `zip` nếu độc lập, rồi mới block một lần khi cần đồng bộ.
5. **Cho rằng có WebClient thì MVC thành hoàn toàn non-blocking:** MVC vẫn dựa trên Servlet container; render/write response có thể dùng blocking executor, tùy kiểu trả về và media type.
6. **Không giới hạn timeout/concurrency trong endpoint synchronous:** servlet workers có thể bị chiếm hết. Thiết lập thời hạn, capacity phù hợp; cân nhắc trả `Mono` và theo dõi metrics.
7. **Dùng `boundedElastic` tràn lan:** chỉ offload tác vụ legacy blocking; nó có giới hạn và có thể tạo queue.
8. **Đọc status nhưng quên response body:** `retrieve().bodyToMono(...)` hoặc `toBodilessEntity()`; với `exchangeToMono` hãy hoàn thiện xử lý/release body để connection pool không giữ tài nguyên lâu.
9. **Thử gọi HTTP trở lại chính cùng ứng dụng trong demo/tải nặng:** nếu servlet workers đều chờ các request nội bộ cần servlet worker khác, bạn có thể tự gây starvation. Tách upstream thực sự và giới hạn concurrency.

## 9. Checklist chọn ranh giới

Trước khi gọi WebClient từ Spring MVC, tự trả lời:

- **Ai đang gọi?** Servlet worker có thể block, Reactor event-loop thì không.
- **Hợp đồng trả về là gì?** Nếu có thể trả `Mono<T>`, hãy để MVC quản lý async; nếu hợp đồng `T` đồng bộ là bắt buộc, block một lần ở cuối trên thread được phép.
- **Có mấy HTTP calls?** Gộp các publishers độc lập bằng `zip` để giảm chờ tuần tự; dùng `flatMap` cho chuỗi có phụ thuộc.
- **Có mã blocking trong callback không?** Thay bằng API reactive hoặc offload phần legacy bằng `boundedElastic`.
- **Có timeout, xử lý lỗi, cancel, body cleanup rõ ràng không?** Đảm bảo request kết thúc và không giữ servlet thread/connection vô hạn.
- **Đo được bottleneck không?** Quan sát servlet busy threads, async requests, Reactor Netty connection pool, response latency và lỗi timeout dưới tải.

**Nguyên tắc:** Với MVC đồng bộ, `block()` được phép ở ranh giới imperative trên servlet worker nhưng có chi phí. Với MVC bất đồng bộ, trả `Mono` là lựa chọn tự nhiên. Bên trong chuỗi WebClient/reactive hoặc trên event-loop, giữ tất cả xử lý non-blocking và kết hợp publishers thay vì gọi `block()`.

## 10. Tài liệu tham khảo

- Spring Framework — WebClient Synchronous Use: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Framework — Spring MVC Asynchronous Requests, Reactive Types: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Concurrency Model in Spring MVC and WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Boot — Calling REST Services / WebClient: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Spring Framework — WebClient retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
